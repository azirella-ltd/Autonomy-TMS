"""
Oversight Schedule Service — Business-Hours-Aware Write-back Delay.

Computes when a decision becomes eligible for ERP write-back,
accounting for:
  - Tenant operating schedule (business hours per day-of-week)
  - Holiday calendar (no oversight on holidays)
  - Timezone (IANA)
  - Urgent bypass (high urgency skips hours)
  - Max calendar delay cap (prevents indefinite hold over long weekends)

Core method: compute_eligible_at()
  Given a required delay of N business-minutes, returns the datetime
  when those N minutes of business time will have elapsed.

Example:
  - Decision at 4:50pm Friday, delay = 30 business-minutes
  - Business hours: Mon-Fri 08:00-17:00
  - 10 minutes remain Friday (4:50-5:00)
  - 20 minutes needed Monday morning
  - eligible_at = Monday 08:20am
"""

import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Default schedule: Mon-Fri 08:00-17:00
DEFAULT_SCHEDULE = {
    0: ("08:00", "17:00"),  # Monday
    1: ("08:00", "17:00"),  # Tuesday
    2: ("08:00", "17:00"),  # Wednesday
    3: ("08:00", "17:00"),  # Thursday
    4: ("08:00", "17:00"),  # Friday
    # 5 and 6 (Sat/Sun) absent = non-operating
}


def _parse_time(t: str) -> time:
    """Parse 'HH:MM' to time object."""
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def _minutes_in_window(
    current: datetime,
    window_start: time,
    window_end: time,
) -> int:
    """Minutes remaining in today's business window from current time."""
    now_time = current.time()
    if now_time >= window_end:
        return 0
    if now_time < window_start:
        # Haven't started yet — full window available
        start_dt = current.replace(hour=window_start.hour, minute=window_start.minute, second=0)
        end_dt = current.replace(hour=window_end.hour, minute=window_end.minute, second=0)
        return int((end_dt - start_dt).total_seconds() / 60)
    # In the middle of the window
    end_dt = current.replace(hour=window_end.hour, minute=window_end.minute, second=0)
    return max(0, int((end_dt - current).total_seconds() / 60))


def _next_window_start(
    current: datetime,
    window_start: time,
) -> datetime:
    """Return the datetime when the current day's window starts (or started)."""
    return current.replace(hour=window_start.hour, minute=window_start.minute, second=0, microsecond=0)


def compute_eligible_at(
    delay_minutes: int,
    now: datetime,
    schedule: Dict[int, Tuple[str, str]],
    holidays: List[date],
    tz_name: str = "UTC",
    respect_business_hours: bool = True,
    max_calendar_hours: int = 72,
) -> datetime:
    """Compute when delay_minutes of business time will have elapsed.

    Args:
        delay_minutes: Required business-minutes of delay
        now: Current UTC datetime
        schedule: Dict of day_of_week (0=Mon) → (start_time, end_time) strings
        holidays: List of holiday dates
        tz_name: IANA timezone name
        respect_business_hours: If False, just add raw minutes
        max_calendar_hours: Cap on total calendar time (prevents infinite hold)

    Returns:
        UTC datetime when the decision becomes eligible for write-back
    """
    if not respect_business_hours or delay_minutes <= 0:
        return now + timedelta(minutes=delay_minutes)

    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        logger.warning("Invalid timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")

    # Convert to local time for schedule comparison
    local_now = now.astimezone(tz)
    max_deadline = now + timedelta(hours=max_calendar_hours)
    remaining = delay_minutes
    cursor = local_now

    # Walk forward day by day, consuming business minutes
    max_iterations = max_calendar_hours * 2  # Safety: don't loop forever
    iterations = 0

    while remaining > 0 and iterations < max_iterations:
        iterations += 1
        dow = cursor.weekday()  # 0=Monday
        cursor_date = cursor.date()

        # Check if today is a holiday
        is_holiday = cursor_date in holidays
        # Check if today is an operating day
        day_schedule = schedule.get(dow) if not is_holiday else None

        if day_schedule is None:
            # Non-operating day — skip to next day start
            cursor = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            continue

        window_start = _parse_time(day_schedule[0])
        window_end = _parse_time(day_schedule[1])

        # If we're before today's window, jump to window start
        if cursor.time() < window_start:
            cursor = cursor.replace(
                hour=window_start.hour, minute=window_start.minute,
                second=0, microsecond=0,
            )

        # If we're past today's window, skip to next day
        if cursor.time() >= window_end:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            continue

        # How many business minutes left today?
        available = _minutes_in_window(cursor, window_start, window_end)

        if available >= remaining:
            # Enough time today — compute exact eligible time
            eligible_local = cursor + timedelta(minutes=remaining)
            # Convert back to UTC
            eligible_utc = eligible_local.astimezone(timezone.utc)
            # Apply max calendar cap
            return min(eligible_utc, max_deadline)
        else:
            # Consume today's remaining minutes, move to next day
            remaining -= available
            cursor = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    # Exhausted iterations or remaining — fall back to max deadline
    logger.warning(
        "Business hours delay calculation exhausted: remaining=%d minutes, "
        "returning max deadline",
        remaining,
    )
    return max_deadline


async def load_tenant_schedule(
    db: AsyncSession,
    tenant_id: int,
) -> Tuple[Dict[int, Tuple[str, str]], List[date], str, dict]:
    """Load operating schedule, holidays, timezone, and oversight config.

    Returns:
        (schedule_dict, holiday_list, timezone_name, oversight_config_dict)
    """
    schedule = dict(DEFAULT_SCHEDULE)  # Start with defaults
    holidays = []
    tz_name = "UTC"
    oversight_config = {
        "respect_business_hours": True,
        "urgent_bypass_enabled": True,
        "urgent_bypass_threshold": 0.85,
        "extend_delay_over_weekends": True,
        "max_calendar_delay_hours": 72,
        "oncall_enabled": False,
        "oncall_user_id": None,
    }

    try:
        # Load operating schedule
        result = await db.execute(
            sql_text("""
                SELECT day_of_week, start_time, end_time, is_operating
                FROM tenant_operating_schedule
                WHERE tenant_id = :tenant_id
                ORDER BY day_of_week
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()
        if rows:
            # Override defaults with tenant-specific schedule
            schedule = {}
            for row in rows:
                if row.is_operating:
                    schedule[row.day_of_week] = (row.start_time, row.end_time)

        # Load holidays
        result = await db.execute(
            sql_text("""
                SELECT holiday_date, recurring
                FROM tenant_holiday_calendar
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id},
        )
        for row in result.fetchall():
            if row.holiday_date:
                hd = row.holiday_date
                if isinstance(hd, datetime):
                    hd = hd.date()
                holidays.append(hd)

        # Load oversight config
        result = await db.execute(
            sql_text("""
                SELECT timezone, respect_business_hours, urgent_bypass_enabled,
                       urgent_bypass_threshold, extend_delay_over_weekends,
                       max_calendar_delay_hours, oncall_enabled, oncall_user_id
                FROM tenant_oversight_config
                WHERE tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id},
        )
        row = result.fetchone()
        if row:
            tz_name = row.timezone or "UTC"
            oversight_config = {
                "respect_business_hours": row.respect_business_hours,
                "urgent_bypass_enabled": row.urgent_bypass_enabled,
                "urgent_bypass_threshold": row.urgent_bypass_threshold,
                "extend_delay_over_weekends": row.extend_delay_over_weekends,
                "max_calendar_delay_hours": row.max_calendar_delay_hours,
                "oncall_enabled": row.oncall_enabled,
                "oncall_user_id": row.oncall_user_id,
            }
        else:
            # Try to get timezone from Company
            result = await db.execute(
                sql_text("""
                    SELECT c.time_zone
                    FROM company c
                    JOIN supply_chain_configs sc ON sc.tenant_id = :tenant_id AND sc.is_active = true
                    LIMIT 1
                """),
                {"tenant_id": tenant_id},
            )
            row = result.fetchone()
            if row and row.time_zone:
                tz_name = row.time_zone

    except Exception as e:
        logger.debug("Could not load tenant schedule (tables may not exist): %s", e)

    return schedule, holidays, tz_name, oversight_config


async def compute_writeback_eligible_at_with_hours(
    db: AsyncSession,
    tenant_id: int,
    delay_minutes: int,
    urgency: float,
    now: Optional[datetime] = None,
) -> datetime:
    """Full computation: load schedule + compute eligible_at.

    If urgency exceeds bypass threshold and bypass is enabled,
    ignores business hours (but still applies the delay).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    schedule, holidays, tz_name, config = await load_tenant_schedule(db, tenant_id)

    respect_hours = config["respect_business_hours"]

    # Urgent bypass check
    if (config["urgent_bypass_enabled"]
            and urgency >= config["urgent_bypass_threshold"]):
        respect_hours = False
        logger.info(
            "Urgent bypass: urgency=%.2f >= threshold=%.2f, ignoring business hours",
            urgency, config["urgent_bypass_threshold"],
        )

    return compute_eligible_at(
        delay_minutes=delay_minutes,
        now=now,
        schedule=schedule,
        holidays=[h for h in holidays],
        tz_name=tz_name,
        respect_business_hours=respect_hours,
        max_calendar_hours=config["max_calendar_delay_hours"],
    )

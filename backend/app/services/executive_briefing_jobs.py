"""
Executive Briefing Scheduler Jobs

Registers an hourly APScheduler job that checks briefing_schedules
and generates briefings for tenants whose schedule matches the current time.

Pattern follows backend/app/services/retention_jobs.py exactly.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)

# Day-of-week mapping for schedule matching
DOW_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def register_executive_briefing_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """Register the hourly briefing schedule check job."""
    scheduler = scheduler_service._scheduler

    if not scheduler:
        logger.warning("Scheduler not available — skipping briefing job registration")
        return

    scheduler.add_job(
        func=_run_briefing_check,
        trigger=CronTrigger(minute=5),  # Every hour at :05
        id="executive_briefing_check",
        name="Executive Briefing: Schedule Check (hourly)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered executive briefing schedule check (hourly at :05)")


def _run_briefing_check() -> None:
    """
    Check all enabled briefing schedules and generate briefings
    for tenants whose schedule matches the current time.
    """
    from app.db.session import sync_session_factory

    logger.debug("Starting executive briefing schedule check")
    now = datetime.utcnow()

    db = sync_session_factory()
    try:
        from app.models.executive_briefing import BriefingSchedule
        from sqlalchemy import select

        result = db.execute(
            select(BriefingSchedule).where(BriefingSchedule.enabled == True)
        )
        schedules = result.scalars().all()

        if not schedules:
            logger.debug("No enabled briefing schedules found")
            return

        for schedule in schedules:
            if _schedule_matches_now(schedule, now):
                logger.info(
                    "Generating scheduled %s briefing for tenant %d",
                    schedule.briefing_type, schedule.tenant_id,
                )
                try:
                    asyncio.run(_generate_for_tenant(schedule.tenant_id, schedule.briefing_type))
                    logger.info(
                        "Scheduled briefing completed for tenant %d",
                        schedule.tenant_id,
                    )
                except Exception as e:
                    logger.error(
                        "Scheduled briefing failed for tenant %d: %s",
                        schedule.tenant_id, e,
                    )

    except Exception as e:
        logger.error("Briefing schedule check failed: %s", e)
    finally:
        db.close()


def _schedule_matches_now(schedule: 'BriefingSchedule', now: datetime) -> bool:
    """Check if the schedule's cron fields match the current time."""
    # Hour and minute must match
    if now.hour != schedule.cron_hour or now.minute != schedule.cron_minute:
        return False

    briefing_type = schedule.briefing_type
    if hasattr(briefing_type, 'value'):
        briefing_type = briefing_type.value

    if briefing_type == "daily":
        return True
    elif briefing_type == "weekly":
        target_dow = DOW_MAP.get(schedule.cron_day_of_week.lower(), 0)
        return now.weekday() == target_dow
    elif briefing_type == "monthly":
        return now.day == 1
    return False


async def _generate_for_tenant(tenant_id: int, briefing_type: str) -> None:
    """Generate a briefing for a specific tenant."""
    from app.db.session import sync_session_factory
    from app.services.executive_briefing_service import ExecutiveBriefingService

    db = sync_session_factory()
    try:
        service = ExecutiveBriefingService(db)
        bt = briefing_type.value if hasattr(briefing_type, 'value') else briefing_type
        await service.generate_briefing(tenant_id, bt, requested_by=None)
    finally:
        db.close()

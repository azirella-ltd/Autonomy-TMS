"""Virtual clock — tenant-aware "today" for demo reproducibility.

Production tenants always use the real current date.
Demo tenants can freeze "today" at a historical reference date so all
time-sensitive business logic operates as if the calendar hadn't advanced.

This is critical for:
- SAP Demo (frozen Nov 2025 to align with the SAP CAL FAA reference date)
- Any other pre-built demo tenant we want to remain reproducible over time

See docs/internal/VIRTUAL_CLOCK_ARCHITECTURE.md for the full design.

Usage:
    from app.core.clock import tenant_today, tenant_today_sync

    # Async context (FastAPI endpoints, async services)
    today = await tenant_today(tenant_id, db)

    # Sync context (background jobs, training scripts)
    today = tenant_today_sync(tenant_id, sync_db)

    # No tenant context (startup, global jobs) — always real today
    from datetime import date
    today = date.today()

What MUST use tenant_today:
  - Planning horizons ("next N weeks from today")
  - Inventory aging / expiry
  - Decision urgency decay
  - Forecast generation windows
  - CDC delta detection
  - Decision Stream chart time windows
  - SLA / order age calculations

What MUST NOT use tenant_today (always real time):
  - Audit log timestamps (SOC II)
  - JWT / session expiry
  - Rate limiting
  - Cron triggers (still fire on real time)
  - Monitoring / health checks
  - created_at / updated_at columns (system time)

Rule: if it's about supply-chain time, use tenant_today.
      If it's about system time or security, use real time.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# In-process cache of (tenant_id → (time_mode, virtual_today))
# Cleared on any tenant update via invalidate_cache().
# Small footprint (tenants are few), avoids a DB hit on every date call.
_tenant_clock_cache: dict[int, tuple[str, Optional[date]]] = {}


def invalidate_cache(tenant_id: Optional[int] = None) -> None:
    """Clear cached clock state. Call after a tenant's time_mode or virtual_today changes."""
    if tenant_id is None:
        _tenant_clock_cache.clear()
    else:
        _tenant_clock_cache.pop(tenant_id, None)


async def tenant_today(tenant_id: Optional[int], db: AsyncSession) -> date:
    """Return the tenant's current 'today' — real today for live tenants,
    frozen reference date for demo tenants.

    If tenant_id is None (global / no tenant context), returns real today.
    If the tenant is not found, returns real today (safe default).
    """
    if tenant_id is None or tenant_id <= 0:
        return date.today()

    cached = _tenant_clock_cache.get(tenant_id)
    if cached is not None:
        mode, vtoday = cached
        if mode == "frozen" and vtoday is not None:
            return vtoday
        return date.today()

    try:
        result = await db.execute(
            text("SELECT time_mode, virtual_today FROM tenants WHERE id = :tid"),
            {"tid": tenant_id},
        )
        row = result.fetchone()
    except Exception as e:
        # Table not migrated yet, or DB error — fall back to real today.
        logger.debug("tenant_today: DB lookup failed (%s), using real today", e)
        return date.today()

    if row is None:
        return date.today()

    mode = row[0] or "live"
    vtoday = row[1]
    _tenant_clock_cache[tenant_id] = (mode, vtoday)

    if mode == "frozen" and vtoday is not None:
        return vtoday
    return date.today()


def tenant_today_sync(tenant_id: Optional[int], db: Session) -> date:
    """Sync variant of tenant_today for background jobs and training scripts."""
    if tenant_id is None or tenant_id <= 0:
        return date.today()

    cached = _tenant_clock_cache.get(tenant_id)
    if cached is not None:
        mode, vtoday = cached
        if mode == "frozen" and vtoday is not None:
            return vtoday
        return date.today()

    try:
        row = db.execute(
            text("SELECT time_mode, virtual_today FROM tenants WHERE id = :tid"),
            {"tid": tenant_id},
        ).fetchone()
    except Exception as e:
        logger.debug("tenant_today_sync: DB lookup failed (%s), using real today", e)
        return date.today()

    if row is None:
        return date.today()

    mode = row[0] or "live"
    vtoday = row[1]
    _tenant_clock_cache[tenant_id] = (mode, vtoday)

    if mode == "frozen" and vtoday is not None:
        return vtoday
    return date.today()


async def tenant_now(tenant_id: Optional[int], db: AsyncSession) -> datetime:
    """Return tenant's current 'now' as a datetime.

    For frozen tenants, uses virtual_today combined with the real wall-clock time
    of day — this preserves hour-of-day behavior (e.g., "after business hours")
    while keeping the calendar date fixed.
    """
    t = await tenant_today(tenant_id, db)
    if t == date.today():
        return datetime.now()
    # Frozen date but preserve wall-clock time
    now_time = datetime.now().time()
    return datetime.combine(t, now_time)


def tenant_now_sync(tenant_id: Optional[int], db: Session) -> datetime:
    """Sync variant of tenant_now."""
    t = tenant_today_sync(tenant_id, db)
    if t == date.today():
        return datetime.now()
    now_time = datetime.now().time()
    return datetime.combine(t, now_time)


async def resolve_tenant_from_config(config_id: int, db: AsyncSession) -> Optional[int]:
    """Resolve tenant_id from a supply chain config_id.

    Many services have config_id but not tenant_id in their context.
    """
    try:
        result = await db.execute(
            text("SELECT tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        )
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def resolve_tenant_from_config_sync(config_id: int, db: Session) -> Optional[int]:
    """Sync variant."""
    try:
        row = db.execute(
            text("SELECT tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


async def config_today(config_id: int, db: AsyncSession) -> date:
    """Convenience: get tenant's today by config_id."""
    tid = await resolve_tenant_from_config(config_id, db)
    return await tenant_today(tid, db)


def config_today_sync(config_id: int, db: Session) -> date:
    """Sync variant."""
    tid = resolve_tenant_from_config_sync(config_id, db)
    return tenant_today_sync(tid, db)

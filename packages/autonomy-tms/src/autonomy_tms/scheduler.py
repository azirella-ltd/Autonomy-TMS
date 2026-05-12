"""TMS plane scheduler-registration shim (AD-13).

Today the TMS plane carries one scheduler-relevant concern that has to
fire in production under the unified backend: the daily
``external_signal_refresh`` that runs ``refresh_all_tenants`` with
``TMS_SEEDING_PROFILE`` so TMS-licensed tenants get DAT / SONAR /
Greenscreens / MarineTraffic / Drewry / Xeneta / Inrix / OAG /
CargoMetrics paid feeds seeded against their transport-mode tags.

Pre-AD-13 this was attached to the standalone TMS backend's
``@app.on_event("startup")``; under the unified backend it registers
through the ``autonomy_app.plane_schedulers`` entry-point group.

The job id is *TMS-prefixed* (``tms_external_signal_refresh``)
because SCP already owns the unprefixed ``external_signal_refresh``
id and the shared APScheduler jobstore would otherwise have the
second registration overwrite the first.

TMS's other relearning_jobs registrations (outcome collection,
escalation arbiter, CDC retraining etc.) overlap by id with SCP's
and stay deliberately unwired here — those job loops are SCP-owned
substrate that TMS reuses, not separate TMS-specific jobs. Adding
them again under TMS ids would double-fire the same logic.
"""
from __future__ import annotations

import logging

import autonomy_tms  # noqa: F401 — sys.path bootstrap for autonomy_tms_app

log = logging.getLogger(__name__)


def _run_tms_external_signal_refresh() -> None:
    """Daily refresh of TMS-flavoured external market intelligence.

    Calls ``autonomy_tms_app.services.external_signal_service.refresh_all_tenants``
    which iterates active tenants and seeds signals using
    ``TMS_SEEDING_PROFILE`` (transport-mode axis: trucking, ocean,
    air, rail, cold-chain, cross-border).
    """
    import asyncio

    log.info("Starting TMS external signal daily refresh")

    async def _refresh():
        from autonomy_tms_app.db.session import async_session_factory
        async with async_session_factory() as db:
            try:
                from autonomy_tms_app.services.external_signal_service import (
                    refresh_all_tenants,
                )
                stats = await refresh_all_tenants(db)
                log.info(
                    "TMS external signal refresh: %s tenants, %s signals",
                    stats.get("tenants_processed"),
                    stats.get("signals_collected"),
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("TMS external signal refresh failed: %s", exc)

    try:
        asyncio.run(_refresh())
    except Exception as exc:  # noqa: BLE001
        log.error("TMS external signal refresh job failed: %s", exc)


def register_jobs(scheduler_service) -> None:
    """Register TMS's periodic jobs against the shared scheduler."""
    from apscheduler.triggers.cron import CronTrigger

    scheduler = scheduler_service._scheduler
    if scheduler is None:
        log.warning("TMS: scheduler not available; skipping job registration")
        return

    # Daily at 05:40 — ten minutes after SCP's :30, five after DP's :35.
    # Staggering keeps the external-API call rate sane.
    scheduler.add_job(
        func=_run_tms_external_signal_refresh,
        trigger=CronTrigger(hour=5, minute=40),
        id="tms_external_signal_refresh",
        name="TMS: External Signal Refresh (daily, TMS_SEEDING_PROFILE)",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    log.info("TMS: registered tms_external_signal_refresh (daily at 05:40)")

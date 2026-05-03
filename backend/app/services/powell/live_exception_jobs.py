"""APScheduler registration for the §3.29 Group A live exception
detector.

Wires :class:`LiveExceptionService` to a 15-minute cron tick that:

  1. Discovers active PRODUCTION + BASELINE-config tenants (same
     filter as :mod:`l3_cascade_jobs` and :mod:`lifecycle_aggregator_jobs`).
  2. For each tenant, calls
     :meth:`LiveExceptionService.detect_exceptions` with
     ``since=last_checkpoint``, ``until=now``.
  3. Persists the exceptions as ``AgentDecision`` rows via
     :meth:`LiveExceptionService.apply_to_decision_stream` (Slice 2).
  4. Optionally emits one :class:`HiveSignal` per exception so
     in-process TRM consumers can react in the same tick (zero
     impact when no signal-bus is configured).

The 15-minute cadence matches the §3.29 Group A draft: real-time
visibility events arrive continuously but a 15-minute tick is fast
enough for human-grade dispatcher response and slow enough to
amortise the SQL scan cost.

Per-tenant try/except: one tenant's bad config must not stop the
cron from servicing the rest.

Checkpointing strategy
----------------------

This first cut uses an in-memory ``_LAST_RUN_AT`` checkpoint dict
keyed by ``tenant_id``. Restarts therefore re-process the
``CHECKPOINT_LOOKBACK_MINUTES`` window — duplicate AgentDecision
rows are filtered downstream by Decision Stream's own dedupe
(item_code + decision_type + window). A persistent checkpoint
table is a follow-on (§3.29 Group A Phase 3).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict

from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService


logger = logging.getLogger(__name__)


_LIVE_EXCEPTION_JOB_ID = "live_exception_detector_15min"
_TICK_INTERVAL_MINUTES = 15
_CHECKPOINT_LOOKBACK_MINUTES = 30
_MISFIRE_GRACE_SECONDS = 600  # 10 minutes


# In-memory checkpoint per tenant. Restarts lose these and re-scan the
# CHECKPOINT_LOOKBACK_MINUTES window — Decision Stream dedupes on
# (item_code, decision_type) so duplicates surface as no-ops.
_LAST_RUN_AT: Dict[int, datetime] = {}


def register_live_exception_jobs(
    scheduler_service: "SyncSchedulerService",
) -> None:
    """Register the live-exception detector as a 15-minute cron job.

    Idempotent: ``replace_existing=True`` lets this be called on every
    app start without piling up duplicate triggers.
    """
    scheduler = scheduler_service._scheduler
    if scheduler is None:
        logger.warning(
            "Scheduler not available — live exception detector job not registered",
        )
        return

    scheduler.add_job(
        func=_run_detector_for_all_tenants,
        trigger=CronTrigger(minute=f"*/{_TICK_INTERVAL_MINUTES}"),
        id=_LIVE_EXCEPTION_JOB_ID,
        name=f"Live exception detector (every {_TICK_INTERVAL_MINUTES} min)",
        replace_existing=True,
        misfire_grace_time=_MISFIRE_GRACE_SECONDS,
    )
    logger.info(
        "Registered live exception detector job (every %d min, id=%s, "
        "lookback=%d min)",
        _TICK_INTERVAL_MINUTES, _LIVE_EXCEPTION_JOB_ID,
        _CHECKPOINT_LOOKBACK_MINUTES,
    )


# ---------------------------------------------------------------------------
# Job body
# ---------------------------------------------------------------------------


def _run_detector_for_all_tenants() -> None:
    """Run the live-exception detector across every active production
    tenant.

    Per-tenant failure is logged and skipped; the cron continues.
    """
    from app.db.session import sync_session_factory
    from app.services.powell.live_exception_service import (
        LiveExceptionService,
    )

    started_at = _utcnow()
    logger.info(
        "Live exception detector — tick starting (lookback=%d min)",
        _CHECKPOINT_LOOKBACK_MINUTES,
    )

    service = LiveExceptionService()

    n_ok = n_failed = 0
    total_exceptions = 0
    total_decisions_written = 0

    with sync_session_factory() as discovery_db:
        tenant_ids = _discover_active_tenants(discovery_db)

    for tenant_id in tenant_ids:
        since = _LAST_RUN_AT.get(
            tenant_id,
            started_at - timedelta(minutes=_CHECKPOINT_LOOKBACK_MINUTES),
        )
        try:
            with sync_session_factory() as tenant_db:
                exceptions = service.detect_exceptions(
                    tenant_db,
                    tenant_id=tenant_id,
                    since=since,
                    until=started_at,
                )
                decision_ids = service.apply_to_decision_stream(
                    tenant_db, exceptions
                )
                tenant_db.commit()
            _emit_signals(exceptions)
            _LAST_RUN_AT[tenant_id] = started_at
            total_exceptions += len(exceptions)
            total_decisions_written += len(decision_ids)
            n_ok += 1
            if exceptions:
                logger.info(
                    "Live exception detector OK — tenant=%s exceptions=%d "
                    "decisions_written=%d since=%s",
                    tenant_id, len(exceptions), len(decision_ids),
                    since.isoformat(),
                )
        except Exception:
            n_failed += 1
            logger.exception(
                "Live exception detector — failure for tenant=%s "
                "(continuing with next tenant)",
                tenant_id,
            )

    duration = (_utcnow() - started_at).total_seconds()
    logger.info(
        "Live exception detector — tick complete (tenants_ok=%d failed=%d "
        "exceptions=%d decisions_written=%d duration_s=%.1f)",
        n_ok, n_failed, total_exceptions, total_decisions_written, duration,
    )


# ---------------------------------------------------------------------------
# HiveSignal emission
# ---------------------------------------------------------------------------


def _emit_signals(exceptions) -> None:
    """Emit one :class:`HiveSignal` per exception, if a process-level
    signal bus is registered.

    Imported lazily so the cron registration path doesn't pay the
    HiveSignal import cost when the bus isn't wired in this process.
    """
    bus = _get_process_signal_bus()
    if bus is None:
        return

    from app.services.powell.hive_signal import (
        HiveSignal,
        HiveSignalType,
    )
    from app.services.powell.live_exception_service import ExceptionType

    type_map = {
        ExceptionType.LATE_ARRIVAL_DETECTED: HiveSignalType.LATE_ARRIVAL_DETECTED,
        ExceptionType.DWELL_BREACH_ALERT: HiveSignalType.DWELL_BREACH_ALERT,
    }

    for exc in exceptions:
        signal_type = type_map.get(exc.exception_type)
        if signal_type is None:
            continue
        try:
            bus.emit(HiveSignal(
                source_trm="live_exception_service",
                signal_type=signal_type,
                urgency=exc.urgency,
                direction="risk",
                magnitude=float(exc.urgency),
                payload={
                    "tracked_entity_id": exc.tracked_entity_id,
                    "tenant_id": exc.tenant_id,
                    "aiio_mode": exc.aiio_mode.value,
                    "source_event_id": exc.source_event_id,
                    "source_eta_id": exc.source_eta_id,
                    "reason_text": exc.reason_text[:255],
                },
                # Visibility signals are short-lived — a 15-min half-life
                # matches the cron tick interval, so a stale exception
                # decays before the next tick re-emits it.
                half_life_minutes=15.0,
            ))
        except Exception:
            logger.exception(
                "Failed to emit HiveSignal for exception type=%s entity=%d",
                exc.exception_type.value, exc.tracked_entity_id,
            )


def _get_process_signal_bus():
    """Return the process-level :class:`HiveSignalBus` if the app
    keeps one, else ``None``.

    Resolved lazily / defensively because the bus is optional and
    not every deployment wires one up.
    """
    try:
        from app.services.powell import get_process_signal_bus
    except ImportError:
        return None
    try:
        return get_process_signal_bus()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _discover_active_tenants(db) -> list:
    """Return ``[tenant_id]`` for every active PRODUCTION tenant with
    at least one active BASELINE supply-chain config.

    Same filter as :mod:`l3_cascade_jobs._discover_active_tenants` and
    :mod:`lifecycle_aggregator_jobs._discover_active_tenants` —
    duplicated rather than imported because each cron job is an
    independent registration unit.
    """
    from azirella_data_model.master.config import SupplyChainConfig
    from azirella_data_model.tenant import Tenant, TenantMode

    rows = (
        db.query(Tenant.id)
        .join(
            SupplyChainConfig,
            SupplyChainConfig.tenant_id == Tenant.id,
        )
        .filter(
            Tenant.status == "ACTIVE",
            Tenant.mode == TenantMode.PRODUCTION,
            SupplyChainConfig.is_active.is_(True),
            SupplyChainConfig.scenario_type == "BASELINE",
        )
        .distinct()
        .all()
    )
    return [tid for (tid,) in rows]


__all__ = [
    "register_live_exception_jobs",
]

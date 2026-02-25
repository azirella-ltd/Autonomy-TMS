"""
Powell Relearning Job Registration

Registers CDC relearning loop jobs with APScheduler:
- Hourly at :30: Outcome collection for TRM decisions (SiteAgentDecision path)
- Hourly at :32: TRM outcome collection for all 11 powell_*_decisions tables
- Hourly at :35: CDT calibration (incremental, after outcomes collected)
- Every 6h at :45: CDC-triggered retraining evaluation

Part of the Powell SDAM feedback loop:
  Decision → Wait → Observe outcome → Compute reward → Calibrate CDT → Retrain if warranted
"""

from typing import TYPE_CHECKING
import logging
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)


def register_relearning_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """
    Register Powell relearning loop jobs with the scheduler.

    Jobs:
    - outcome_collector: Hourly at :30 — compute actual outcomes (SiteAgentDecision)
    - trm_outcome_collector: Hourly at :32 — compute outcomes for all 11 powell_*_decisions
    - cdt_calibration: Hourly at :35 — incremental CDT calibration from new outcomes
    - cdc_retraining: Every 6h at :45 — evaluate and execute retraining if warranted
    """
    scheduler = scheduler_service._scheduler

    if not scheduler:
        logger.warning("Scheduler not available, relearning jobs not registered")
        return

    # Hourly: Outcome collection — SiteAgentDecision path (at :30)
    scheduler.add_job(
        func=_run_outcome_collection,
        trigger=CronTrigger(minute=30),
        id="powell_outcome_collector",
        name="Powell: Outcome Collection (hourly)",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered Powell outcome collection job (hourly at :30)")

    # Hourly: TRM outcome collection — all 11 powell_*_decisions tables (at :32)
    scheduler.add_job(
        func=_run_trm_outcome_collection,
        trigger=CronTrigger(minute=32),
        id="powell_trm_outcome_collector",
        name="Powell: TRM Outcome Collection (hourly)",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered Powell TRM outcome collection job (hourly at :32)")

    # Hourly: CDT calibration — after outcomes are collected (at :35)
    scheduler.add_job(
        func=_run_cdt_calibration,
        trigger=CronTrigger(minute=35),
        id="powell_cdt_calibration",
        name="Powell: CDT Calibration (hourly)",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered Powell CDT calibration job (hourly at :35)")

    # Every 6 hours: Retraining evaluation (at :45)
    scheduler.add_job(
        func=_run_cdc_retraining,
        trigger=CronTrigger(hour="0,6,12,18", minute=45),
        id="powell_cdc_retraining",
        name="Powell: CDC Retraining Evaluation (every 6h)",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered Powell CDC retraining job (every 6h at :45)")


# ---------------------------------------------------------------------------
# Job execution functions
# ---------------------------------------------------------------------------

def _run_outcome_collection() -> None:
    """Collect outcomes for TRM decisions across all sites (SiteAgentDecision path)."""
    from app.db.session import SessionLocal

    logger.info("Starting scheduled outcome collection")

    db = SessionLocal()
    try:
        from app.services.powell.outcome_collector import OutcomeCollectorService

        service = OutcomeCollectorService(db)
        stats = service.collect_outcomes()
        logger.info(
            f"Outcome collection completed: "
            f"{stats['succeeded']} computed, {stats['failed']} failed "
            f"out of {stats['processed']} processed"
        )
    except Exception as e:
        logger.error(f"Outcome collection job failed: {e}")
    finally:
        db.close()


def _run_trm_outcome_collection() -> None:
    """Collect outcomes for all 11 powell_*_decisions tables."""
    from app.db.session import SessionLocal

    logger.info("Starting scheduled TRM outcome collection")

    db = SessionLocal()
    try:
        from app.services.powell.outcome_collector import OutcomeCollectorService

        service = OutcomeCollectorService(db)
        stats = service.collect_trm_outcomes()
        logger.info(
            f"TRM outcome collection completed: "
            f"{stats['succeeded']} computed, {stats['failed']} failed "
            f"out of {stats['processed']} processed"
        )
    except Exception as e:
        logger.error(f"TRM outcome collection job failed: {e}")
    finally:
        db.close()


def _run_cdt_calibration() -> None:
    """Incrementally calibrate CDT wrappers from newly collected outcomes."""
    from app.db.session import SessionLocal

    logger.info("Starting scheduled CDT calibration")

    db = SessionLocal()
    try:
        from app.services.powell.cdt_calibration_service import CDTCalibrationService

        service = CDTCalibrationService(db)
        stats = service.calibrate_incremental()
        total_added = sum(s.get("added", 0) for s in stats.values())
        calibrated = sum(
            1 for s in stats.values() if s.get("is_calibrated", False)
        )
        logger.info(
            f"CDT calibration: {total_added} new pairs, "
            f"{calibrated}/11 agents calibrated"
        )
    except Exception as e:
        logger.error(f"CDT calibration job failed: {e}")
    finally:
        db.close()


def _run_cdc_retraining() -> None:
    """Evaluate retraining need for all sites with recent CDC triggers."""
    from app.db.session import SessionLocal

    logger.info("Starting scheduled CDC retraining evaluation")

    db = SessionLocal()
    try:
        from app.models.powell_decision import CDCTriggerLog, SiteAgentCheckpoint
        from app.services.powell.cdc_retraining_service import CDCRetrainingService
        from datetime import timedelta

        now = datetime.utcnow()

        # Find distinct site_keys that have had CDC triggers in the last 24h
        recent_sites = (
            db.query(CDCTriggerLog.site_key)
            .filter(
                CDCTriggerLog.triggered == True,
                CDCTriggerLog.timestamp > now - timedelta(hours=24),
            )
            .distinct()
            .all()
        )

        site_keys = [row[0] for row in recent_sites if row[0]]

        if not site_keys:
            logger.info("No sites with recent CDC triggers, skipping retraining")
            return

        trained = 0
        skipped = 0
        failed = 0

        for site_key in site_keys:
            try:
                svc = CDCRetrainingService(db=db, site_key=site_key, customer_id=0)
                if svc.evaluate_retraining_need():
                    result = svc.execute_retraining()
                    if result and result.final_loss < float("inf"):
                        trained += 1
                        logger.info(
                            f"Retrained {site_key}: loss={result.final_loss:.4f}"
                        )
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Retraining failed for {site_key}: {e}")

        logger.info(
            f"CDC retraining evaluation: {trained} trained, "
            f"{skipped} skipped, {failed} failed "
            f"across {len(site_keys)} sites"
        )
    except Exception as e:
        logger.error(f"CDC retraining job failed: {e}")
    finally:
        db.close()

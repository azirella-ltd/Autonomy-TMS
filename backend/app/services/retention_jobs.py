"""
Retention Job Registration

Registers retention jobs with APScheduler:
- Daily: HOT -> WARM promotion (2:00 AM)
- Weekly: WARM -> COLD promotion (Sunday 3:00 AM)
- Monthly: Collapse intermediates (1st of month 4:00 AM)
- Monthly: Archive closed cycles (1st of month 5:00 AM)

Part of the Planning Cycle Management system.
"""

from typing import TYPE_CHECKING
import logging
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)


def register_retention_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """
    Register retention jobs with the scheduler.

    Args:
        scheduler_service: The sync scheduler service instance
    """
    scheduler = scheduler_service._scheduler

    if not scheduler:
        logger.warning("Scheduler not available, retention jobs not registered")
        return

    # Daily job: HOT -> WARM (2:00 AM UTC)
    scheduler.add_job(
        func=_run_daily_retention,
        trigger=CronTrigger(hour=2, minute=0),
        id="retention_daily",
        name="Daily Retention: HOT -> WARM",
        replace_existing=True,
        misfire_grace_time=3600  # 1 hour grace
    )
    logger.info("Registered daily retention job (2:00 AM UTC)")

    # Weekly job: WARM -> COLD (Sunday 3:00 AM UTC)
    scheduler.add_job(
        func=_run_weekly_retention,
        trigger=CronTrigger(day_of_week='sun', hour=3, minute=0),
        id="retention_weekly",
        name="Weekly Retention: WARM -> COLD",
        replace_existing=True,
        misfire_grace_time=3600
    )
    logger.info("Registered weekly retention job (Sunday 3:00 AM UTC)")

    # Monthly job: Collapse (1st of month 4:00 AM UTC)
    scheduler.add_job(
        func=_run_monthly_collapse,
        trigger=CronTrigger(day=1, hour=4, minute=0),
        id="retention_monthly_collapse",
        name="Monthly Collapse: Intermediate Snapshots",
        replace_existing=True,
        misfire_grace_time=3600
    )
    logger.info("Registered monthly collapse job (1st of month 4:00 AM UTC)")

    # Monthly job: Archive closed cycles (1st of month 5:00 AM UTC)
    scheduler.add_job(
        func=_run_archive_closed_cycles,
        trigger=CronTrigger(day=1, hour=5, minute=0),
        id="retention_monthly_archive",
        name="Monthly Archive: Closed Cycles",
        replace_existing=True,
        misfire_grace_time=3600
    )
    logger.info("Registered monthly archive job (1st of month 5:00 AM UTC)")


def _run_daily_retention() -> None:
    """Execute daily retention job."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    logger.info("Starting scheduled daily retention job")

    db = SessionLocal()
    try:
        service = RetentionService(db)
        result = service.run_daily_retention()
        logger.info(f"Daily retention completed: {result}")
    except Exception as e:
        logger.error(f"Daily retention job failed: {e}")
    finally:
        db.close()


def _run_weekly_retention() -> None:
    """Execute weekly retention job."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    logger.info("Starting scheduled weekly retention job")

    db = SessionLocal()
    try:
        service = RetentionService(db)
        result = service.run_weekly_retention()
        logger.info(f"Weekly retention completed: {result}")
    except Exception as e:
        logger.error(f"Weekly retention job failed: {e}")
    finally:
        db.close()


def _run_monthly_collapse() -> None:
    """Execute monthly collapse job."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    logger.info("Starting scheduled monthly collapse job")

    db = SessionLocal()
    try:
        service = RetentionService(db)
        result = service.run_monthly_collapse()
        logger.info(f"Monthly collapse completed: {result}")
    except Exception as e:
        logger.error(f"Monthly collapse job failed: {e}")
    finally:
        db.close()


def _run_archive_closed_cycles() -> None:
    """Execute monthly archive job."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    logger.info("Starting scheduled monthly archive job")

    db = SessionLocal()
    try:
        service = RetentionService(db)
        result = service.run_archive_closed_cycles()
        logger.info(f"Monthly archive completed: {result}")
    except Exception as e:
        logger.error(f"Monthly archive job failed: {e}")
    finally:
        db.close()


# Manual trigger functions for admin use

def trigger_daily_retention_now() -> dict:
    """Manually trigger daily retention."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    db = SessionLocal()
    try:
        service = RetentionService(db)
        return service.run_daily_retention()
    finally:
        db.close()


def trigger_weekly_retention_now() -> dict:
    """Manually trigger weekly retention."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    db = SessionLocal()
    try:
        service = RetentionService(db)
        return service.run_weekly_retention()
    finally:
        db.close()


def trigger_monthly_collapse_now() -> dict:
    """Manually trigger monthly collapse."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    db = SessionLocal()
    try:
        service = RetentionService(db)
        return service.run_monthly_collapse()
    finally:
        db.close()


def trigger_archive_now() -> dict:
    """Manually trigger archive job."""
    from app.db.session import SessionLocal
    from app.services.retention_service import RetentionService

    db = SessionLocal()
    try:
        service = RetentionService(db)
        return service.run_archive_closed_cycles()
    finally:
        db.close()

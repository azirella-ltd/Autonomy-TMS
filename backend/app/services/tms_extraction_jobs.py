"""
TMS Extraction Job Registration

Registers periodic TMS data extraction jobs with APScheduler:

- Every 15 min: Incremental shipment + exception extraction (near-real-time)
- Every hour: Incremental load + appointment extraction
- Daily 1:00 AM: Full carrier + rate refresh
- Daily 2:00 AM: Port intelligence sync to LaneProfile risk scores
- Weekly Sunday 4:00 AM: Historical extraction summary + data quality report

Jobs extract from all active ERPConnections that have a TMS-compatible
erp_type (sap_tm, oracle_otm, blue_yonder, manhattan). Each job iterates
over active connections and runs the appropriate adapter extraction.

See docs/TMS_ERP_INTEGRATION.md for the architecture.
"""

from typing import TYPE_CHECKING
import logging
import asyncio
from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)

# ERP types that support TMS extraction
TMS_ERP_TYPES = {"sap", "sap_s4hana", "sap_tm", "oracle_otm", "blue_yonder", "manhattan"}


def register_tms_extraction_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """
    Register TMS extraction jobs with the scheduler.

    Args:
        scheduler_service: The sync scheduler service instance
    """
    scheduler = scheduler_service._scheduler

    if not scheduler:
        logger.warning("Scheduler not available, TMS extraction jobs not registered")
        return

    # ── Near-real-time: shipments + exceptions (every 15 min) ────────────
    scheduler.add_job(
        func=_run_shipment_sync,
        trigger=IntervalTrigger(minutes=15),
        id="tms_shipment_sync",
        name="TMS: Incremental shipment + exception sync (15 min)",
        replace_existing=True,
        misfire_grace_time=600,  # 10 min grace
    )
    logger.info("Registered TMS shipment sync job (every 15 min)")

    # ── Hourly: loads + appointments ─────────────────────────────────────
    scheduler.add_job(
        func=_run_load_sync,
        trigger=IntervalTrigger(hours=1),
        id="tms_load_sync",
        name="TMS: Incremental load + appointment sync (hourly)",
        replace_existing=True,
        misfire_grace_time=1800,  # 30 min grace
    )
    logger.info("Registered TMS load sync job (hourly)")

    # ── Daily: carrier + rate refresh (1:00 AM UTC) ──────────────────────
    scheduler.add_job(
        func=_run_carrier_rate_refresh,
        trigger=CronTrigger(hour=1, minute=0),
        id="tms_carrier_rate_refresh",
        name="TMS: Daily carrier + rate refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered TMS carrier/rate refresh job (daily 1:00 AM UTC)")

    # ── Daily: port intelligence sync (2:00 AM UTC) ──────────────────────
    scheduler.add_job(
        func=_run_port_intelligence_sync,
        trigger=CronTrigger(hour=2, minute=0),
        id="tms_port_intelligence_sync",
        name="TMS: Daily port intelligence → LaneProfile sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered TMS port intelligence sync job (daily 2:00 AM UTC)")


# ── Job Implementations ──────────────────────────────────────────────────────

def _run_shipment_sync():
    """Near-real-time sync: shipments + exceptions from all active TMS connections."""
    asyncio.get_event_loop().run_until_complete(_async_shipment_sync())


async def _async_shipment_sync():
    """Async implementation of shipment sync."""
    from app.db.session import async_session_factory
    from app.services.tms_extraction_service import TMSExtractionService
    from sqlalchemy import select
    from app.models.erp_connection import ERPConnection

    logger.info("TMS shipment sync: starting")

    async with async_session_factory() as db:
        # Find all active TMS-compatible connections
        stmt = select(ERPConnection).where(
            ERPConnection.is_active == True,
            ERPConnection.erp_type.in_(TMS_ERP_TYPES),
        )
        result = await db.execute(stmt)
        connections = result.scalars().all()

        if not connections:
            logger.debug("TMS shipment sync: no active TMS connections")
            return

        service = TMSExtractionService(db)
        since = datetime.utcnow() - timedelta(minutes=20)  # 15 min interval + 5 min overlap

        for conn in connections:
            try:
                result = await service.run_extraction(
                    connection_id=conn.id,
                    tenant_id=conn.tenant_id,
                    entity_types=["shipments", "exceptions"],
                    mode="incremental",
                    since=since,
                )
                total = sum(
                    r.get("records_extracted", 0)
                    for r in result.get("results", [])
                )
                if total > 0:
                    logger.info(
                        f"TMS shipment sync [{conn.name}]: "
                        f"{total} records extracted"
                    )
            except Exception as e:
                logger.error(
                    f"TMS shipment sync [{conn.name}] failed: {e}"
                )

        await db.commit()

    logger.info("TMS shipment sync: completed")


def _run_load_sync():
    """Hourly sync: loads + appointments."""
    asyncio.get_event_loop().run_until_complete(_async_load_sync())


async def _async_load_sync():
    """Async implementation of load sync."""
    from app.db.session import async_session_factory
    from app.services.tms_extraction_service import TMSExtractionService
    from sqlalchemy import select
    from app.models.erp_connection import ERPConnection

    logger.info("TMS load sync: starting")

    async with async_session_factory() as db:
        stmt = select(ERPConnection).where(
            ERPConnection.is_active == True,
            ERPConnection.erp_type.in_(TMS_ERP_TYPES),
        )
        result = await db.execute(stmt)
        connections = result.scalars().all()

        if not connections:
            return

        service = TMSExtractionService(db)
        since = datetime.utcnow() - timedelta(hours=1, minutes=10)

        for conn in connections:
            try:
                result = await service.run_extraction(
                    connection_id=conn.id,
                    tenant_id=conn.tenant_id,
                    entity_types=["loads", "appointments"],
                    mode="incremental",
                    since=since,
                )
                total = sum(
                    r.get("records_extracted", 0)
                    for r in result.get("results", [])
                )
                if total > 0:
                    logger.info(f"TMS load sync [{conn.name}]: {total} records")
            except Exception as e:
                logger.error(f"TMS load sync [{conn.name}] failed: {e}")

        await db.commit()

    logger.info("TMS load sync: completed")


def _run_carrier_rate_refresh():
    """Daily full refresh of carrier master + rates."""
    asyncio.get_event_loop().run_until_complete(_async_carrier_rate_refresh())


async def _async_carrier_rate_refresh():
    """Async implementation of carrier/rate refresh."""
    from app.db.session import async_session_factory
    from app.services.tms_extraction_service import TMSExtractionService
    from sqlalchemy import select
    from app.models.erp_connection import ERPConnection

    logger.info("TMS carrier/rate refresh: starting")

    async with async_session_factory() as db:
        stmt = select(ERPConnection).where(
            ERPConnection.is_active == True,
            ERPConnection.erp_type.in_(TMS_ERP_TYPES),
        )
        result = await db.execute(stmt)
        connections = result.scalars().all()

        if not connections:
            return

        service = TMSExtractionService(db)

        for conn in connections:
            try:
                result = await service.run_extraction(
                    connection_id=conn.id,
                    tenant_id=conn.tenant_id,
                    entity_types=["carriers", "rates"],
                    mode="full",
                )
                total = sum(
                    r.get("records_extracted", 0)
                    for r in result.get("results", [])
                )
                logger.info(
                    f"TMS carrier/rate refresh [{conn.name}]: {total} records"
                )
            except Exception as e:
                logger.error(
                    f"TMS carrier/rate refresh [{conn.name}] failed: {e}"
                )

        await db.commit()

    logger.info("TMS carrier/rate refresh: completed")


def _run_port_intelligence_sync():
    """Daily port intelligence → LaneProfile risk score sync via p44."""
    asyncio.get_event_loop().run_until_complete(_async_port_intelligence_sync())


async def _async_port_intelligence_sync():
    """Async implementation of port intelligence sync."""
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.models.erp_connection import ERPConnection

    logger.info("TMS port intelligence sync: starting")

    async with async_session_factory() as db:
        # This uses p44, not the ERP adapter — but runs on the same schedule
        # because it updates LaneProfile risk scores that the TRMs consume.
        try:
            from app.integrations.project44.config_service import P44ConfigService
            config_svc = P44ConfigService()

            # Get all tenants with p44 enabled
            # (simplified — in production, iterate tenants from the DB)
            from app.models.tenant import Tenant
            stmt = select(Tenant)
            result = await db.execute(stmt)
            tenants = result.scalars().all()

            for tenant in tenants:
                try:
                    p44_config = await config_svc.get_config(tenant.id, db)
                    if not p44_config.get("enabled"):
                        continue

                    from app.integrations.project44.connector import P44Connector
                    from app.integrations.project44.tracking_service import P44TrackingService

                    connector = P44Connector(
                        client_id=p44_config.get("client_id", ""),
                        client_secret=p44_config.get("client_secret_encrypted", ""),
                        use_sandbox=p44_config.get("environment") == "sandbox",
                    )
                    tracking_svc = P44TrackingService(connector)

                    result = await tracking_svc.sync_port_intelligence_to_lane_profiles(
                        db_session=db,
                        tenant_id=tenant.id,
                    )
                    if result.get("profiles_updated", 0) > 0:
                        logger.info(
                            f"Port intelligence sync [tenant {tenant.id}]: "
                            f"{result['profiles_updated']} lane profiles updated"
                        )
                except Exception as e:
                    logger.error(
                        f"Port intelligence sync [tenant {tenant.id}] failed: {e}"
                    )

            await db.commit()

        except ImportError:
            logger.debug("p44 integration not available, skipping port intelligence sync")
        except Exception as e:
            logger.error(f"Port intelligence sync failed: {e}")

    logger.info("TMS port intelligence sync: completed")

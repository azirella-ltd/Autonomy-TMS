"""
SAP Data Staging Scheduled Jobs

Registers CDC/delta sync jobs with APScheduler:
- Every 6h at :15: Incremental SAP staging (delta extract → map → upsert)
- Daily at 01:00: Full reconciliation report

Requires an active SAP connection with 'auto_sync' enabled.
"""

from typing import TYPE_CHECKING
import logging
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)


def register_sap_staging_jobs(scheduler_service: 'SyncSchedulerService') -> None:
    """Register SAP staging jobs with the scheduler."""
    scheduler = scheduler_service._scheduler

    if not scheduler:
        logger.warning("Scheduler not available, SAP staging jobs not registered")
        return

    # Incremental staging: every 6 hours at :15
    scheduler.add_job(
        _run_incremental_staging,
        trigger=CronTrigger(hour="*/6", minute=15),
        id="sap_incremental_staging",
        replace_existing=True,
        name="SAP Incremental Staging (6h)",
        kwargs={"scheduler_service": scheduler_service},
    )

    # Daily reconciliation: 01:00
    scheduler.add_job(
        _run_daily_reconciliation,
        trigger=CronTrigger(hour=1, minute=0),
        id="sap_daily_reconciliation",
        replace_existing=True,
        name="SAP Daily Reconciliation",
        kwargs={"scheduler_service": scheduler_service},
    )

    logger.info("SAP staging jobs registered: incremental (6h at :15), reconciliation (daily 01:00)")


async def _run_incremental_staging(scheduler_service: 'SyncSchedulerService'):
    """
    Run incremental SAP staging for all tenants with auto-sync connections.

    Finds active SAP connections, extracts delta data, and upserts into
    the staging tables via SAPDataStagingService.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import select, text as sql_text
    from app.models.sap_connection import SAPConnection

    logger.info("Starting incremental SAP staging run")

    async with async_session_factory() as db:
        try:
            # Find all active, validated SAP connections
            result = await db.execute(
                select(SAPConnection).where(
                    SAPConnection.is_active == True,  # noqa: E712
                    SAPConnection.is_validated == True,  # noqa: E712
                )
            )
            connections = result.scalars().all()

            if not connections:
                logger.debug("No active SAP connections found, skipping incremental staging")
                return

            for conn in connections:
                try:
                    await _stage_connection(db, conn)
                except Exception as e:
                    logger.error(
                        f"Incremental staging failed for connection {conn.id} "
                        f"(tenant {conn.tenant_id}): {e}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(f"Incremental staging job failed: {e}", exc_info=True)


async def _stage_connection(db, conn):
    """Run incremental staging for a single SAP connection."""
    from app.services.sap_data_staging_service import SAPDataStagingService
    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod
    from app.integrations.sap.delta_loader import DeltaLoadTracker, DeltaLoadConfig
    from sqlalchemy import text as sql_text
    from pathlib import Path
    import pandas as pd

    connection = SAPConnectionConfig.from_db(conn)
    tenant_id = conn.tenant_id

    # Find active config for this tenant
    result = await db.execute(
        sql_text("""
            SELECT id, company_id FROM supply_chain_configs
            WHERE tenant_id = :tid AND is_active = true
            ORDER BY id DESC LIMIT 1
        """),
        {"tid": tenant_id},
    )
    active_row = result.mappings().first()
    if not active_row:
        logger.debug(f"No active config for tenant {tenant_id}, skipping")
        return

    config_id = active_row["id"]
    company_id = active_row.get("company_id")

    # Extract data based on connection method
    sap_data = {}

    if connection.connection_method == ConnectionMethod.CSV:
        csv_dir = Path(connection.csv_directory) if connection.csv_directory else None
        if not csv_dir or not csv_dir.exists():
            return

        # Read all available CSV files
        file_mapping = conn.file_table_mapping or []
        for entry in file_mapping:
            if not entry.get("confirmed"):
                continue
            table_name = entry.get("table", "").upper()
            filename = entry.get("filename", "")
            filepath = csv_dir / filename
            if filepath.exists():
                try:
                    df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
                    df.columns = [c.strip().upper() for c in df.columns]
                    sap_data[table_name] = df
                except Exception as e:
                    logger.warning(f"Failed to read CSV {filepath}: {e}")

    elif connection.connection_method in (
        ConnectionMethod.ODATA, ConnectionMethod.HANA_DB, ConnectionMethod.RFC,
    ):
        # Use unified extractors for live connections
        try:
            from app.integrations.sap.extractors import create_extractor
            extractor = create_extractor(connection)
            # Extract key delta tables
            delta_tables = [
                "MARD", "MARA", "MARC", "EKKO", "EKPO", "VBAK", "VBAP",
                "AFKO", "AFPO", "LIKP", "LIPS", "PBED",
            ]
            for table in delta_tables:
                try:
                    df = await extractor.extract_table(table)
                    if df is not None and not df.empty:
                        sap_data[table] = df
                except Exception:
                    pass  # Table may not exist or access denied
        except ImportError:
            logger.warning("Extractor not available for live connection")
            return

    if not sap_data:
        logger.debug(f"No delta data for connection {conn.id}")
        return

    # Run staging
    staging_service = SAPDataStagingService(
        db=db,
        tenant_id=tenant_id,
        config_id=config_id,
        company_id=company_id,
    )
    result = await staging_service.stage_all(sap_data)

    logger.info(
        f"Incremental staging for tenant {tenant_id} config {config_id}: "
        f"{result.total_records} records ({len(result.entity_results)} entities)"
    )

    await db.commit()


async def _run_daily_reconciliation(scheduler_service: 'SyncSchedulerService'):
    """
    Run daily reconciliation for all tenants with active SAP connections.

    Logs mismatches between SAP source and Postgres staging counts.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.models.sap_connection import SAPConnection

    logger.info("Starting daily SAP reconciliation")

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(SAPConnection).where(
                    SAPConnection.is_active == True,  # noqa: E712
                    SAPConnection.is_validated == True,  # noqa: E712
                )
            )
            connections = result.scalars().all()

            for conn in connections:
                try:
                    await _reconcile_connection(db, conn)
                except Exception as e:
                    logger.error(
                        f"Reconciliation failed for connection {conn.id}: {e}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(f"Daily reconciliation job failed: {e}", exc_info=True)


async def _reconcile_connection(db, conn):
    """Run reconciliation for a single connection."""
    from app.services.sap_data_staging_service import SAPDataStagingService
    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod
    from sqlalchemy import text as sql_text
    from pathlib import Path
    import pandas as pd

    connection = SAPConnectionConfig.from_db(conn)
    tenant_id = conn.tenant_id

    result = await db.execute(
        sql_text("""
            SELECT id FROM supply_chain_configs
            WHERE tenant_id = :tid AND is_active = true
            ORDER BY id DESC LIMIT 1
        """),
        {"tid": tenant_id},
    )
    active_row = result.mappings().first()
    if not active_row:
        return

    config_id = active_row["id"]

    # Quick extraction for reconciliation (just counts/keys, not full data)
    sap_data = {}
    if connection.connection_method == ConnectionMethod.CSV:
        csv_dir = Path(connection.csv_directory) if connection.csv_directory else None
        if not csv_dir or not csv_dir.exists():
            return
        file_mapping = conn.file_table_mapping or []
        for entry in file_mapping:
            if not entry.get("confirmed"):
                continue
            table_name = entry.get("table", "").upper()
            filepath = csv_dir / entry.get("filename", "")
            if filepath.exists():
                try:
                    df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
                    df.columns = [c.strip().upper() for c in df.columns]
                    sap_data[table_name] = df
                except Exception:
                    pass

    if not sap_data:
        return

    staging_service = SAPDataStagingService(
        db=db, tenant_id=tenant_id, config_id=config_id,
    )
    recon = await staging_service.reconcile(sap_data)

    # Log mismatches
    for entity, status in recon.items():
        if not status.get("match"):
            logger.warning(
                f"Reconciliation mismatch for tenant {tenant_id} "
                f"entity={entity}: SAP={status['sap_count']} "
                f"DB={status['db_count']} delta={status['delta']}"
            )

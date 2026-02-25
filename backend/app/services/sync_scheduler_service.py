"""
Sync Scheduler Service

Manages APScheduler integration for SAP data sync jobs:
- Initialize scheduler with SQLAlchemy job store
- Register/update/delete sync jobs from config
- Handle job execution with retry logic
- Trigger workflow chain on completion

Part of the SAP Data Import Cadence System.
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import logging
import asyncio
from functools import wraps

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED,
    EVENT_JOB_ADDED, EVENT_JOB_REMOVED, JobExecutionEvent
)
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import (
    SyncJobConfig, SyncJobExecution, SyncTableResult,
    SyncStatus, SyncDataType, DEFAULT_SYNC_CADENCES,
    WorkflowTriggerType
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class SyncSchedulerService:
    """
    Service for managing SAP sync job scheduling using APScheduler.

    Implements singleton pattern to ensure only one scheduler instance.
    """

    _instance: Optional['SyncSchedulerService'] = None
    _scheduler: Optional[BackgroundScheduler] = None
    _is_initialized: bool = False

    def __init__(self, db_url: str):
        """
        Initialize the scheduler service.

        Args:
            db_url: Database URL for job store persistence
        """
        self.db_url = db_url
        self._job_listeners: Dict[str, Callable] = {}

    @classmethod
    def get_instance(cls, db_url: Optional[str] = None) -> 'SyncSchedulerService':
        """
        Get singleton instance of scheduler service.

        Args:
            db_url: Database URL (required on first call)

        Returns:
            SyncSchedulerService instance
        """
        if cls._instance is None:
            if db_url is None:
                db_url = settings.DATABASE_URL
            cls._instance = cls(db_url)
        return cls._instance

    def initialize(self) -> None:
        """Initialize the APScheduler with SQLAlchemy job store."""
        if self._is_initialized:
            logger.info("Scheduler already initialized")
            return

        try:
            # Configure job stores
            jobstores = {
                'default': SQLAlchemyJobStore(
                    url=self.db_url,
                    tablename='apscheduler_jobs'
                )
            }

            # Configure job defaults
            job_defaults = {
                'coalesce': True,  # Combine missed executions into one
                'max_instances': 1,  # Prevent concurrent executions of same job
                'misfire_grace_time': 60 * 15  # 15 minute grace period for missed jobs
            }

            # Create scheduler (using BackgroundScheduler for sync execution)
            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                job_defaults=job_defaults,
                timezone='UTC'
            )

            # Add event listeners
            self._scheduler.add_listener(
                self._on_job_executed,
                EVENT_JOB_EXECUTED
            )
            self._scheduler.add_listener(
                self._on_job_error,
                EVENT_JOB_ERROR
            )
            self._scheduler.add_listener(
                self._on_job_missed,
                EVENT_JOB_MISSED
            )

            self._is_initialized = True
            logger.info("Sync scheduler initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}")
            raise

    def start(self) -> None:
        """Start the scheduler."""
        if not self._is_initialized:
            self.initialize()

        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Sync scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the scheduler gracefully.

        Args:
            wait: Wait for running jobs to complete
        """
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Sync scheduler shutdown complete")

    def pause(self) -> None:
        """Pause all scheduled jobs."""
        if self._scheduler:
            self._scheduler.pause()
            logger.info("Sync scheduler paused")

    def resume(self) -> None:
        """Resume all scheduled jobs."""
        if self._scheduler:
            self._scheduler.resume()
            logger.info("Sync scheduler resumed")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._scheduler is not None and self._scheduler.running

    def register_job(self, db: Session, config: SyncJobConfig) -> str:
        """
        Register a sync job with the scheduler.

        Args:
            db: Database session
            config: Sync job configuration

        Returns:
            Job ID string
        """
        job_id = f"sync_{config.customer_id}_{config.data_type.value}"

        # Remove existing job if present
        existing_job = self._scheduler.get_job(job_id)
        if existing_job:
            self._scheduler.remove_job(job_id)
            logger.info(f"Removed existing job: {job_id}")

        if not config.is_enabled:
            logger.info(f"Job {job_id} is disabled, not scheduling")
            # Update config with null job ID
            config.apscheduler_job_id = None
            db.commit()
            return job_id

        try:
            # Parse cron expression
            trigger = CronTrigger.from_crontab(
                config.cron_expression,
                timezone=config.timezone or 'UTC'
            )

            # Add job to scheduler
            self._scheduler.add_job(
                func=self._execute_sync_job_wrapper,
                trigger=trigger,
                id=job_id,
                args=[config.id],
                name=f"SAP Sync: {config.data_type.value} (Customer {config.customer_id})",
                replace_existing=True
            )

            # Update config with job ID
            config.apscheduler_job_id = job_id
            db.commit()

            logger.info(f"Registered sync job: {job_id} with cron '{config.cron_expression}'")
            return job_id

        except Exception as e:
            logger.error(f"Failed to register job {job_id}: {e}")
            raise

    def unregister_job(self, db: Session, config: SyncJobConfig) -> None:
        """
        Unregister a sync job from the scheduler.

        Args:
            db: Database session
            config: Sync job configuration
        """
        job_id = config.apscheduler_job_id or f"sync_{config.customer_id}_{config.data_type.value}"

        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info(f"Unregistered sync job: {job_id}")

        config.apscheduler_job_id = None
        db.commit()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a scheduled job.

        Args:
            job_id: Job ID

        Returns:
            Job status dict or None if not found
        """
        job = self._scheduler.get_job(job_id)
        if not job:
            return None

        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'pending': job.pending
        }

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all scheduled jobs.

        Returns:
            List of job status dicts
        """
        jobs = self._scheduler.get_jobs()
        return [
            {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            }
            for job in jobs
        ]

    def trigger_job_now(self, db: Session, config_id: int, triggered_by: Optional[int] = None) -> SyncJobExecution:
        """
        Trigger a sync job to run immediately.

        Args:
            db: Database session
            config_id: Sync job config ID
            triggered_by: User ID who triggered the job

        Returns:
            SyncJobExecution record
        """
        config = db.query(SyncJobConfig).filter_by(id=config_id).first()
        if not config:
            raise ValueError(f"Sync config {config_id} not found")

        # Create execution record
        execution = SyncJobExecution(
            config_id=config_id,
            execution_mode="manual",
            triggered_by=triggered_by,
            status=SyncStatus.PENDING,
            load_mode="delta" if config.use_delta_load else "full"
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        # Run job in background thread
        import threading
        thread = threading.Thread(
            target=self._execute_sync_job,
            args=(config_id, execution.id)
        )
        thread.start()

        logger.info(f"Manually triggered sync job for config {config_id}, execution {execution.id}")
        return execution

    def _execute_sync_job_wrapper(self, config_id: int) -> None:
        """
        Wrapper for scheduled job execution.
        Creates execution record and calls main executor.
        """
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            config = db.query(SyncJobConfig).filter_by(id=config_id).first()
            if not config:
                logger.error(f"Sync config {config_id} not found")
                return

            # Create execution record
            execution = SyncJobExecution(
                config_id=config_id,
                apscheduler_job_id=config.apscheduler_job_id,
                execution_mode="scheduled",
                status=SyncStatus.PENDING,
                load_mode="delta" if config.use_delta_load else "full"
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)

            # Execute sync
            self._execute_sync_job(config_id, execution.id)

        except Exception as e:
            logger.error(f"Error in scheduled sync job {config_id}: {e}")
        finally:
            db.close()

    def _execute_sync_job(self, config_id: int, execution_id: int) -> None:
        """
        Execute a sync job.

        Args:
            config_id: Sync job config ID
            execution_id: Execution record ID
        """
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            config = db.query(SyncJobConfig).filter_by(id=config_id).first()
            execution = db.query(SyncJobExecution).filter_by(id=execution_id).first()

            if not config or not execution:
                logger.error(f"Config {config_id} or execution {execution_id} not found")
                return

            # Update status to running
            execution.status = SyncStatus.RUNNING
            execution.started_at = datetime.utcnow()
            db.commit()

            try:
                # Run the actual sync
                self._run_sync(db, config, execution)

                # Trigger workflow if configured
                if config.trigger_workflow and execution.status == SyncStatus.COMPLETED:
                    self._trigger_post_sync_workflow(db, config, execution)

            except Exception as e:
                execution.status = SyncStatus.FAILED
                execution.error_message = str(e)
                execution.completed_at = datetime.utcnow()
                if execution.started_at:
                    execution.duration_seconds = (
                        execution.completed_at - execution.started_at
                    ).total_seconds()

                # Handle retry
                if execution.retry_count < config.max_retries:
                    self._schedule_retry(db, config, execution)

                logger.error(f"Sync job {config_id} failed: {e}")
                raise

            db.commit()

        except Exception as e:
            logger.error(f"Error executing sync job {config_id}: {e}")
            db.rollback()
        finally:
            db.close()

    def _run_sync(self, db: Session, config: SyncJobConfig, execution: SyncJobExecution) -> None:
        """
        Run the actual SAP sync operation.

        Args:
            db: Database session
            config: Sync job configuration
            execution: Execution record
        """
        from app.integrations.sap.intelligent_loader import (
            IntelligentSAPLoader, LoadConfig, create_intelligent_loader
        )
        from app.integrations.sap.s4hana_connector import S4HANAConnector

        logger.info(f"Starting sync for config {config.id}, execution {execution.id}")

        try:
            # Create intelligent loader
            load_config = LoadConfig(
                mode="daily" if config.use_delta_load else "initial",
                connection_type="rfc",
                use_claude_ai=False,  # Disable for scheduled jobs (performance)
                enable_delta=config.use_delta_load
            )

            loader = create_intelligent_loader(
                mode=load_config.mode,
                connection_type=load_config.connection_type,
                use_claude=load_config.use_claude_ai,
                enable_delta=load_config.enable_delta
            )

            # Get SAP connection (use group config or override)
            connector = self._get_sap_connector(config)

            # Set delta timestamp
            if config.use_delta_load:
                execution.delta_from_timestamp = datetime.utcnow() - timedelta(days=config.lookback_days)
                execution.delta_to_timestamp = datetime.utcnow()

            # Load each configured table
            for table_name in config.sap_tables or []:
                table_result = SyncTableResult(
                    execution_id=execution.id,
                    table_name=table_name,
                    started_at=datetime.utcnow(),
                    status="running"
                )
                db.add(table_result)
                db.commit()

                try:
                    # Load table data
                    df, load_result = loader.load_table(table_name, connector)

                    # Update table result
                    table_result.records_extracted = load_result.records_loaded
                    table_result.records_loaded = len(df) if df is not None else 0

                    if hasattr(load_result, 'delta_result') and load_result.delta_result:
                        table_result.records_new = load_result.delta_result.new_records
                        table_result.records_updated = load_result.delta_result.changed_records
                        table_result.records_deleted = load_result.delta_result.deleted_records

                    table_result.status = "completed"
                    table_result.completed_at = datetime.utcnow()
                    table_result.duration_seconds = (
                        table_result.completed_at - table_result.started_at
                    ).total_seconds()

                    # Update execution totals
                    execution.total_records += table_result.records_extracted
                    execution.new_records += table_result.records_new
                    execution.updated_records += table_result.records_updated
                    execution.deleted_records += table_result.records_deleted

                    # Store Z-fields if found
                    if hasattr(load_result, 'z_fields') and load_result.z_fields:
                        if execution.z_fields_found is None:
                            execution.z_fields_found = []
                        execution.z_fields_found.extend(load_result.z_fields)

                    logger.info(f"Synced table {table_name}: {table_result.records_loaded} records")

                except Exception as e:
                    table_result.status = "failed"
                    table_result.error_message = str(e)
                    table_result.completed_at = datetime.utcnow()
                    execution.failed_records += 1
                    logger.error(f"Failed to sync table {table_name}: {e}")

                db.commit()

            # Determine final status
            failed_tables = db.query(SyncTableResult).filter(
                SyncTableResult.execution_id == execution.id,
                SyncTableResult.status == "failed"
            ).count()

            if failed_tables == 0:
                execution.status = SyncStatus.COMPLETED
            elif failed_tables < len(config.sap_tables or []):
                execution.status = SyncStatus.PARTIAL
            else:
                execution.status = SyncStatus.FAILED

            execution.completed_at = datetime.utcnow()
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()

            db.commit()

            logger.info(
                f"Sync completed for config {config.id}: "
                f"{execution.total_records} records, status={execution.status.value}"
            )

        except Exception as e:
            execution.status = SyncStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            db.commit()
            raise

    def _get_sap_connector(self, config: SyncJobConfig):
        """
        Get SAP connector for the sync job.

        Args:
            config: Sync job configuration

        Returns:
            SAP connector instance
        """
        from app.integrations.sap.s4hana_connector import S4HANAConnector, S4HANAConnectionConfig

        # Use config override or fall back to environment settings
        conn_config = config.connection_config or {}

        sap_config = S4HANAConnectionConfig(
            ashost=conn_config.get('ashost', settings.SAP_HOST),
            sysnr=conn_config.get('sysnr', settings.SAP_SYSNR),
            client=conn_config.get('client', settings.SAP_CLIENT),
            user=conn_config.get('user', settings.SAP_USER),
            passwd=conn_config.get('passwd', settings.SAP_PASSWORD),
        )

        return S4HANAConnector(sap_config)

    def _trigger_post_sync_workflow(
        self,
        db: Session,
        config: SyncJobConfig,
        execution: SyncJobExecution
    ) -> None:
        """
        Trigger workflow after sync completion.

        Args:
            db: Database session
            config: Sync job configuration
            execution: Completed execution record
        """
        try:
            from app.services.workflow_service import WorkflowService

            workflow_service = WorkflowService(db)
            workflow_exec = workflow_service.trigger_post_sync_workflow(
                config=config,
                sync_execution=execution
            )

            execution.workflow_triggered = True
            execution.workflow_execution_id = workflow_exec.id
            db.commit()

            logger.info(f"Triggered workflow {workflow_exec.id} after sync {execution.id}")

        except Exception as e:
            logger.error(f"Failed to trigger post-sync workflow: {e}")
            # Don't fail the sync just because workflow failed

    def _schedule_retry(
        self,
        db: Session,
        config: SyncJobConfig,
        execution: SyncJobExecution
    ) -> None:
        """
        Schedule a retry for failed sync job.

        Args:
            db: Database session
            config: Sync job configuration
            execution: Failed execution record
        """
        execution.retry_count += 1
        execution.status = SyncStatus.RETRYING

        # Calculate retry time
        retry_delay = timedelta(seconds=config.retry_delay_seconds)
        retry_time = datetime.utcnow() + retry_delay

        # Schedule one-time retry job
        retry_job_id = f"retry_{execution.id}"

        self._scheduler.add_job(
            func=self._execute_sync_job,
            trigger='date',
            run_date=retry_time,
            id=retry_job_id,
            args=[config.id, execution.id],
            name=f"Retry: {config.data_type.value} (Attempt {execution.retry_count})",
            replace_existing=True
        )

        db.commit()

        logger.info(
            f"Scheduled retry {execution.retry_count}/{config.max_retries} "
            f"for execution {execution.id} at {retry_time}"
        )

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle successful job execution event."""
        logger.debug(f"Job executed successfully: {event.job_id}")

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handle job execution error event."""
        logger.error(f"Job execution error: {event.job_id}, exception: {event.exception}")

    def _on_job_missed(self, event: JobExecutionEvent) -> None:
        """Handle missed job execution event."""
        logger.warning(f"Job missed: {event.job_id}, scheduled_run_time: {event.scheduled_run_time}")


def seed_default_sync_configs(db: Session, customer_id: int) -> List[SyncJobConfig]:
    """
    Seed default sync job configurations for a customer.

    Args:
        db: Database session
        customer_id: Customer ID to create configs for

    Returns:
        List of created SyncJobConfig records
    """
    configs = []

    for data_type, defaults in DEFAULT_SYNC_CADENCES.items():
        # Check if config already exists
        existing = db.query(SyncJobConfig).filter(
            SyncJobConfig.customer_id == customer_id,
            SyncJobConfig.data_type == data_type
        ).first()

        if existing:
            continue

        config = SyncJobConfig(
            customer_id=customer_id,
            data_type=data_type,
            name=defaults.get('name', f"{data_type.value} Sync"),
            cron_expression=defaults['cron'],
            lookback_days=defaults['delta_days'],
            sap_tables=defaults['tables'],
            is_enabled=False,  # Disabled by default, admin must enable
            use_delta_load=True,
            trigger_workflow=True
        )
        db.add(config)
        configs.append(config)

    db.commit()

    logger.info(f"Seeded {len(configs)} default sync configs for customer {customer_id}")
    return configs

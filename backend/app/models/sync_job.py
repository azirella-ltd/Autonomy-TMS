"""
Sync Job Models for SAP Data Import Scheduling

Provides:
- Configurable sync cadence per data type
- Job execution tracking and history
- Failure handling with retry configuration

Part of the SAP Data Import Cadence System.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Boolean,
    Float, Enum, Index, Text, LargeBinary
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base


class SyncDataType(str, enum.Enum):
    """Types of data that can be synced from SAP"""
    # Master Data (daily cadence)
    MATERIAL_MASTER = "material_master"     # MARA, MARC
    VENDOR_MASTER = "vendor_master"         # LFA1, LFM1
    CUSTOMER_MASTER = "customer_master"     # KNA1, KNB1
    BOM_MASTER = "bom_master"               # STKO, STPO
    ROUTING_MASTER = "routing_master"       # PLAS, PLPO

    # Transactional Data (15-30 min cadence)
    INVENTORY = "inventory"                 # MARD, MBEW
    PURCHASE_ORDERS = "purchase_orders"     # EKKO, EKPO
    SALES_ORDERS = "sales_orders"           # VBAK, VBAP
    PRODUCTION_ORDERS = "production_orders" # AFKO, AFPO
    DELIVERIES = "deliveries"               # LIKP, LIPS
    RESERVATIONS = "reservations"           # RESB

    # Planning Data (hourly cadence)
    DEMAND_FORECAST = "demand_forecast"     # /SAPAPO/TSDFCP
    SUPPLY_PLAN = "supply_plan"             # /SAPAPO/MATLOC
    ATP_DATA = "atp_data"                   # ATP-related tables


class SyncStatus(str, enum.Enum):
    """Status of sync job execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"       # Some records failed
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class SyncJobConfig(Base):
    """
    Sync Job Configuration

    Defines cadence and parameters for each data type sync.
    Supports group-level configuration for multi-tenant scenarios.
    """
    __tablename__ = "sync_job_configs"

    id = Column(Integer, primary_key=True, index=True)

    # Scope
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    data_type = Column(Enum(SyncDataType, name="syncdatatype"), nullable=False, index=True)
    name = Column(String(100), nullable=True)  # Human-readable name
    description = Column(Text, nullable=True)

    # Cadence Configuration
    cron_expression = Column(String(100), nullable=False)  # e.g., "*/15 * * * *" for every 15 min
    timezone = Column(String(50), default="UTC")
    is_enabled = Column(Boolean, default=True, nullable=False)

    # Sync Parameters
    use_delta_load = Column(Boolean, default=True)
    lookback_days = Column(Integer, default=1)  # For delta loading
    max_records_per_batch = Column(Integer, default=10000)
    connection_config = Column(JSON, nullable=True)  # Override group-level SAP connection

    # Table Mapping (which SAP tables to sync)
    sap_tables = Column(JSON, nullable=False)  # ["MARA", "MARC", "MAKT"]

    # Field Mapping (optional custom field mappings)
    field_mappings = Column(JSON, nullable=True)

    # Retry Configuration
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=300)  # 5 minutes

    # Workflow Trigger
    trigger_workflow = Column(Boolean, default=True)
    workflow_template_id = Column(Integer, ForeignKey("workflow_templates.id", ondelete="SET NULL"), nullable=True)
    workflow_chain = Column(JSON, nullable=True)  # ["validate", "analytics", "insights", "notify"]

    # Notifications
    notify_on_failure = Column(Boolean, default=True)
    notify_on_success = Column(Boolean, default=False)
    notification_emails = Column(JSON, nullable=True)  # ["admin@company.com"]

    # APScheduler job reference
    apscheduler_job_id = Column(String(100), nullable=True, unique=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    group = relationship("Group", back_populates="sync_job_configs")
    executions = relationship("SyncJobExecution", back_populates="config", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_sync_job_config_group_type", "group_id", "data_type", unique=True),
        Index("ix_sync_job_config_enabled", "is_enabled"),
    )

    def __repr__(self):
        return f"<SyncJobConfig(id={self.id}, group={self.group_id}, type={self.data_type.value})>"


class SyncJobExecution(Base):
    """
    Sync Job Execution Record

    Tracks each execution of a sync job with detailed metrics.
    """
    __tablename__ = "sync_job_executions"

    id = Column(Integer, primary_key=True, index=True)

    # Job Reference
    config_id = Column(Integer, ForeignKey("sync_job_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    apscheduler_job_id = Column(String(100), nullable=True, index=True)

    # Execution Metadata
    execution_mode = Column(String(20), default="scheduled")  # scheduled, manual, retry
    triggered_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # For manual

    # Status
    status = Column(Enum(SyncStatus, name="syncstatus"), default=SyncStatus.PENDING, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Metrics
    total_records = Column(Integer, default=0)
    new_records = Column(Integer, default=0)
    updated_records = Column(Integer, default=0)
    deleted_records = Column(Integer, default=0)
    unchanged_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)

    # Load Type
    load_mode = Column(String(20))  # full, delta
    delta_from_timestamp = Column(DateTime, nullable=True)
    delta_to_timestamp = Column(DateTime, nullable=True)

    # Data Quality
    validation_issues = Column(Integer, default=0)
    validation_warnings = Column(Integer, default=0)
    z_fields_found = Column(JSON, nullable=True)  # List of Z-fields encountered

    # Error Handling
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)  # Stack trace, failed records

    # Workflow Triggering
    workflow_triggered = Column(Boolean, default=False)
    workflow_execution_id = Column(Integer, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True)

    # Planning Integration
    planning_cycle_id = Column(Integer, ForeignKey("planning_cycles.id", ondelete="SET NULL"), nullable=True)
    snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    config = relationship("SyncJobConfig", back_populates="executions")
    table_results = relationship("SyncTableResult", back_populates="execution", cascade="all, delete-orphan")
    trigger_user = relationship("User", foreign_keys=[triggered_by])

    __table_args__ = (
        Index("ix_sync_job_exec_status_created", "status", "created_at"),
        Index("ix_sync_job_exec_config_created", "config_id", "created_at"),
        Index("ix_sync_job_exec_config_status", "config_id", "status"),
    )

    def __repr__(self):
        return f"<SyncJobExecution(id={self.id}, config={self.config_id}, status={self.status.value})>"

    @property
    def success_rate(self) -> float:
        """Calculate success rate of sync execution"""
        total = self.total_records or 0
        failed = self.failed_records or 0
        if total == 0:
            return 0.0
        return ((total - failed) / total) * 100


class SyncTableResult(Base):
    """
    Per-table sync result within an execution.

    Tracks individual SAP table sync metrics within a job execution.
    """
    __tablename__ = "sync_table_results"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("sync_job_executions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Table Info
    table_name = Column(String(50), nullable=False)  # e.g., "MARA"

    # Metrics
    records_extracted = Column(Integer, default=0)
    records_loaded = Column(Integer, default=0)
    records_new = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_deleted = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Status
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)

    # Delta Tracking
    last_change_timestamp = Column(DateTime, nullable=True)  # For next delta
    delta_state_key = Column(String(100), nullable=True)  # Key in delta state file

    # Data Quality
    validation_issues = Column(JSON, nullable=True)  # List of validation issues

    # Relationships
    execution = relationship("SyncJobExecution", back_populates="table_results")

    __table_args__ = (
        Index("ix_sync_table_result_exec_table", "execution_id", "table_name"),
    )

    def __repr__(self):
        return f"<SyncTableResult(id={self.id}, table={self.table_name}, status={self.status})>"


class APSchedulerJob(Base):
    """
    APScheduler SQLAlchemy Job Store Table

    Required for APScheduler persistence. Schema matches APScheduler's expectations.
    This table is managed by APScheduler, but we define it here for migration purposes.
    """
    __tablename__ = "apscheduler_jobs"

    id = Column(String(191), primary_key=True)
    next_run_time = Column(Float, index=True)
    job_state = Column(LargeBinary, nullable=False)


# Default cadence configurations for seeding
DEFAULT_SYNC_CADENCES = {
    SyncDataType.MATERIAL_MASTER: {
        "cron": "0 2 * * *",  # Daily at 2 AM
        "delta_days": 2,
        "tables": ["MARA", "MARC", "MAKT"],
        "name": "Material Master Sync"
    },
    SyncDataType.VENDOR_MASTER: {
        "cron": "0 3 * * *",  # Daily at 3 AM
        "delta_days": 2,
        "tables": ["LFA1", "LFM1"],
        "name": "Vendor Master Sync"
    },
    SyncDataType.CUSTOMER_MASTER: {
        "cron": "0 3 * * *",  # Daily at 3 AM
        "delta_days": 2,
        "tables": ["KNA1", "KNB1"],
        "name": "Customer Master Sync"
    },
    SyncDataType.BOM_MASTER: {
        "cron": "0 4 * * *",  # Daily at 4 AM
        "delta_days": 2,
        "tables": ["STKO", "STPO"],
        "name": "BOM Master Sync"
    },
    SyncDataType.INVENTORY: {
        "cron": "*/15 * * * *",  # Every 15 minutes
        "delta_days": 1,
        "tables": ["MARD"],
        "name": "Inventory Sync"
    },
    SyncDataType.PURCHASE_ORDERS: {
        "cron": "*/30 * * * *",  # Every 30 minutes
        "delta_days": 7,
        "tables": ["EKKO", "EKPO"],
        "name": "Purchase Orders Sync"
    },
    SyncDataType.SALES_ORDERS: {
        "cron": "*/30 * * * *",  # Every 30 minutes
        "delta_days": 30,
        "tables": ["VBAK", "VBAP"],
        "name": "Sales Orders Sync"
    },
    SyncDataType.PRODUCTION_ORDERS: {
        "cron": "*/30 * * * *",  # Every 30 minutes
        "delta_days": 14,
        "tables": ["AFKO", "AFPO"],
        "name": "Production Orders Sync"
    },
    SyncDataType.DELIVERIES: {
        "cron": "*/30 * * * *",  # Every 30 minutes
        "delta_days": 14,
        "tables": ["LIKP", "LIPS"],
        "name": "Deliveries Sync"
    },
    SyncDataType.DEMAND_FORECAST: {
        "cron": "0 * * * *",  # Hourly
        "delta_days": 7,
        "tables": ["/SAPAPO/TSDFCP"],
        "name": "Demand Forecast Sync"
    },
    SyncDataType.SUPPLY_PLAN: {
        "cron": "0 * * * *",  # Hourly
        "delta_days": 7,
        "tables": ["/SAPAPO/MATLOC"],
        "name": "Supply Plan Sync"
    },
}

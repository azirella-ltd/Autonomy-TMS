"""
Planning Cycle & Snapshot Models

Git-like versioning for planning data:
- PlanningCycle: Weekly/monthly planning cycles with status workflow
- PlanningSnapshot: Point-in-time snapshots with parent chain
- SnapshotDelta: Incremental changes for efficient storage

Follows patterns from ConfigDelta and ConfigLineage models.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Boolean,
    Enum, Text, Index, Float, Date
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base


class CycleType(str, enum.Enum):
    """Planning cycle types"""
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    AD_HOC = "ad_hoc"


class CycleStatus(str, enum.Enum):
    """Planning cycle status workflow"""
    DRAFT = "draft"                       # Initial creation, data gathering
    DATA_COLLECTION = "data_collection"   # Syncing data from SAP
    PLANNING = "planning"                 # Active planning in progress
    REVIEW = "review"                     # Under management review
    APPROVED = "approved"                 # Approved by stakeholders
    PUBLISHED = "published"               # Released for execution
    CLOSED = "closed"                     # Cycle complete
    ARCHIVED = "archived"                 # Moved to cold storage


class SnapshotType(str, enum.Enum):
    """Types of planning snapshots"""
    BASELINE = "baseline"         # Official baseline (frozen SAP state)
    WORKING = "working"           # Work in progress
    CHECKPOINT = "checkpoint"     # Manual save point
    AUTO = "auto"                 # Automated checkpoint (post-sync)
    PUBLISHED = "published"       # Published/approved version
    ARCHIVED = "archived"         # Archived snapshot


class SnapshotTier(str, enum.Enum):
    """Storage tier for retention policy"""
    HOT = "hot"           # Active, full detail (0-30 days)
    WARM = "warm"         # Recent, compressed (30-90 days)
    COLD = "cold"         # Archived, minimal (90+ days)


class DeltaOperation(str, enum.Enum):
    """Operations for snapshot deltas"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class DeltaEntityType(str, enum.Enum):
    """Entity types for snapshot deltas"""
    DEMAND_PLAN = "demand_plan"
    SUPPLY_PLAN = "supply_plan"
    INVENTORY = "inventory"
    FORECAST = "forecast"
    SAFETY_STOCK = "safety_stock"
    KPI = "kpi"
    RECOMMENDATION = "recommendation"
    CONFIG = "config"


class PlanningCycle(Base):
    """
    Planning Cycle

    Represents a planning period (e.g., weekly S&OP cycle).
    Manages snapshots and decisions within the cycle.
    """
    __tablename__ = "planning_cycles"

    id = Column(Integer, primary_key=True, index=True)

    # Identification
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, index=True)  # e.g., "2026-W05"
    cycle_type = Column(Enum(CycleType, name="cycle_type"), nullable=False)
    description = Column(Text, nullable=True)

    # Scope
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)

    # Planning Horizon
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    planning_horizon_weeks = Column(Integer, default=52)

    # Status Workflow
    status = Column(Enum(CycleStatus, name="cycle_status"), default=CycleStatus.DRAFT, nullable=False, index=True)
    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status_notes = Column(Text, nullable=True)

    # Key Snapshot References
    baseline_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)
    current_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)
    published_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Metrics Summary (aggregated from snapshots)
    metrics_summary = Column(JSON, nullable=True)
    # {
    #   "total_snapshots": 15,
    #   "total_decisions": 42,
    #   "ai_recommendations": 38,
    #   "human_overrides": 4,
    #   "kpis": {"OTIF": 0.95, "inventory_turns": 8.2}
    # }

    # Timeline Tracking
    data_collection_started_at = Column(DateTime, nullable=True)
    data_collection_completed_at = Column(DateTime, nullable=True)
    planning_started_at = Column(DateTime, nullable=True)
    planning_completed_at = Column(DateTime, nullable=True)
    review_started_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    # Approval
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Retention
    retention_tier = Column(Enum(SnapshotTier, name="snapshot_tier"), default=SnapshotTier.HOT)
    archived_at = Column(DateTime, nullable=True)

    # Previous/Next Cycle Links
    previous_cycle_id = Column(Integer, ForeignKey("planning_cycles.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    group = relationship("Group", back_populates="planning_cycles")
    config = relationship("SupplyChainConfig")
    snapshots = relationship("PlanningSnapshot",
                            foreign_keys="PlanningSnapshot.cycle_id",
                            back_populates="cycle",
                            cascade="all, delete-orphan")
    decisions = relationship("PlanningDecision", back_populates="cycle", cascade="all, delete-orphan")
    baseline_snapshot = relationship("PlanningSnapshot", foreign_keys=[baseline_snapshot_id], post_update=True)
    current_snapshot = relationship("PlanningSnapshot", foreign_keys=[current_snapshot_id], post_update=True)
    published_snapshot = relationship("PlanningSnapshot", foreign_keys=[published_snapshot_id], post_update=True)
    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])
    previous_cycle = relationship("PlanningCycle", remote_side=[id], foreign_keys=[previous_cycle_id])

    __table_args__ = (
        Index("ix_planning_cycle_group_period", "group_id", "period_start", "period_end"),
        Index("ix_planning_cycle_group_code", "group_id", "code", unique=True),
        Index("ix_planning_cycle_status", "status"),
        Index("ix_planning_cycle_type_status", "cycle_type", "status"),
    )

    def __repr__(self):
        return f"<PlanningCycle(id={self.id}, code={self.code}, status={self.status.value})>"

    @property
    def snapshot_count(self) -> int:
        """Number of snapshots in cycle"""
        return len(self.snapshots) if self.snapshots else 0

    @property
    def decision_count(self) -> int:
        """Number of decisions in cycle"""
        return len(self.decisions) if self.decisions else 0


class PlanningSnapshot(Base):
    """
    Planning Snapshot

    Git-like point-in-time snapshot with parent chain.
    Supports both full materialization and delta storage.
    """
    __tablename__ = "planning_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    # Cycle Reference
    cycle_id = Column(Integer, ForeignKey("planning_cycles.id", ondelete="CASCADE"), nullable=False, index=True)

    # Version Chain (git-like)
    version = Column(Integer, nullable=False)
    parent_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)
    base_snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Metadata
    snapshot_type = Column(Enum(SnapshotType, name="snapshot_type"), nullable=False, index=True)
    commit_message = Column(String(500), nullable=True)  # Git-style commit message
    tags = Column(JSON, nullable=True)  # ["weekly-review", "approved", "v1.0"]

    # Source Tracking
    sync_execution_id = Column(Integer, ForeignKey("sync_job_executions.id", ondelete="SET NULL"), nullable=True)
    workflow_execution_id = Column(Integer, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True)

    # Storage Configuration
    storage_tier = Column(Enum(SnapshotTier, name="snapshot_tier"), default=SnapshotTier.HOT, nullable=False, index=True)
    uses_delta_storage = Column(Boolean, default=True)
    is_materialized = Column(Boolean, default=False)  # Full data stored

    # Snapshot Data (for materialized/collapsed snapshots)
    demand_plan_data = Column(JSON, nullable=True)      # Demand forecast snapshot
    supply_plan_data = Column(JSON, nullable=True)      # Supply plan snapshot
    inventory_data = Column(JSON, nullable=True)        # Inventory levels
    forecast_data = Column(JSON, nullable=True)         # Forecast data
    kpi_data = Column(JSON, nullable=True)              # KPI metrics at snapshot time

    # Metrics Summary
    record_counts = Column(JSON, nullable=True)
    # {"demand_records": 1500, "supply_records": 800, "inventory_records": 2000}

    # Data Quality
    validation_status = Column(String(20), nullable=True)  # passed, warnings, failed
    validation_issues = Column(JSON, nullable=True)

    # Size Tracking
    data_size_bytes = Column(Integer, nullable=True)
    compressed_size_bytes = Column(Integer, nullable=True)
    delta_count = Column(Integer, default=0)  # Number of deltas from parent

    # Integrity
    data_hash = Column(String(64), nullable=True)  # SHA-256 for verification

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Retention
    expires_at = Column(DateTime, nullable=True, index=True)  # For automated cleanup
    collapsed_at = Column(DateTime, nullable=True)  # When intermediate data was collapsed
    collapsed_to_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    cycle = relationship("PlanningCycle", foreign_keys=[cycle_id], back_populates="snapshots")
    parent_snapshot = relationship("PlanningSnapshot",
                                   remote_side=[id],
                                   foreign_keys=[parent_snapshot_id],
                                   backref="child_snapshots")
    base_snapshot = relationship("PlanningSnapshot",
                                remote_side=[id],
                                foreign_keys=[base_snapshot_id])
    collapsed_to = relationship("PlanningSnapshot",
                               remote_side=[id],
                               foreign_keys=[collapsed_to_id])
    decisions = relationship("PlanningDecision",
                            foreign_keys="PlanningDecision.snapshot_id",
                            back_populates="snapshot")
    deltas = relationship("SnapshotDelta", back_populates="snapshot", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_snapshot_cycle_version", "cycle_id", "version", unique=True),
        Index("ix_snapshot_parent", "parent_snapshot_id"),
        Index("ix_snapshot_tier_expires", "storage_tier", "expires_at"),
        Index("ix_snapshot_type_created", "snapshot_type", "created_at"),
    )

    def __repr__(self):
        return f"<PlanningSnapshot(id={self.id}, cycle={self.cycle_id}, v{self.version}, type={self.snapshot_type.value})>"

    @property
    def is_baseline(self) -> bool:
        return self.snapshot_type == SnapshotType.BASELINE

    @property
    def is_published(self) -> bool:
        return self.snapshot_type == SnapshotType.PUBLISHED

    @property
    def has_parent(self) -> bool:
        return self.parent_snapshot_id is not None


class SnapshotDelta(Base):
    """
    Incremental changes between snapshots.

    Follows ConfigDelta pattern for efficient storage.
    Stores only what changed from parent snapshot.
    """
    __tablename__ = "snapshot_deltas"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)

    # Delta Identification
    entity_type = Column(Enum(DeltaEntityType, name="delta_entity_type"), nullable=False, index=True)
    entity_key = Column(String(200), nullable=True, index=True)  # e.g., "product_id|site_id|period"
    operation = Column(Enum(DeltaOperation, name="delta_operation"), nullable=False)

    # Data
    delta_data = Column(JSON, nullable=False)  # Full data for create, changed fields for update
    changed_fields = Column(JSON, nullable=True)  # List of field names that changed
    original_values = Column(JSON, nullable=True)  # Original values before change (for rollback)

    # Context
    change_reason = Column(String(200), nullable=True)  # Brief reason for change
    decision_id = Column(Integer, ForeignKey("planning_decisions.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    snapshot = relationship("PlanningSnapshot", back_populates="deltas")
    decision = relationship("PlanningDecision")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_snapshot_delta_entity", "snapshot_id", "entity_type", "entity_key"),
        Index("ix_snapshot_delta_operation", "snapshot_id", "operation"),
    )

    def __repr__(self):
        return f"<SnapshotDelta(id={self.id}, snapshot={self.snapshot_id}, entity={self.entity_type.value}, op={self.operation.value})>"


class SnapshotLineage(Base):
    """
    Ancestor tree for snapshots enabling efficient ancestor queries.

    Similar to ConfigLineage - stores all ancestor relationships
    for efficient traversal.
    """
    __tablename__ = "snapshot_lineage"

    # Composite primary key
    snapshot_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="CASCADE"), primary_key=True)
    ancestor_id = Column(Integer, ForeignKey("planning_snapshots.id", ondelete="CASCADE"), primary_key=True)

    # Distance from snapshot to ancestor
    depth = Column(Integer, nullable=False)  # 0=self, 1=parent, 2=grandparent, etc.

    # Relationships
    snapshot = relationship("PlanningSnapshot", foreign_keys=[snapshot_id])
    ancestor = relationship("PlanningSnapshot", foreign_keys=[ancestor_id])

    __table_args__ = (
        Index("ix_snapshot_lineage_ancestor", "ancestor_id"),
        Index("ix_snapshot_lineage_depth", "snapshot_id", "depth"),
    )

    def __repr__(self):
        return f"<SnapshotLineage(snapshot={self.snapshot_id}, ancestor={self.ancestor_id}, depth={self.depth})>"

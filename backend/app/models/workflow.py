"""
Workflow Models for Post-Import Processing

Event-driven workflow chain:
Sync -> Validate -> Analytics -> Insights -> Notify

Part of the SAP Data Import Cadence System.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Boolean,
    Enum, Text, Index, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base


class WorkflowStatus(str, enum.Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class WorkflowStepType(str, enum.Enum):
    """Types of workflow steps"""
    VALIDATE = "validate"              # Data validation
    TRANSFORM = "transform"            # Data transformation
    ANALYTICS = "analytics"            # Run analytics/calculations
    INSIGHTS = "insights"              # Generate AI insights
    NOTIFY = "notify"                  # Send notifications
    PLAN_UPDATE = "plan_update"        # Update planning data
    SNAPSHOT = "snapshot"              # Create planning snapshot
    ATP_REFRESH = "atp_refresh"        # Refresh ATP cache
    RECONCILE = "reconcile"            # Post-sync reconciliation
    CUSTOM = "custom"                  # Custom step handler


class WorkflowTriggerType(str, enum.Enum):
    """Types of workflow triggers"""
    SYNC_COMPLETED = "sync_completed"      # After SAP sync
    MANUAL = "manual"                      # Manual trigger
    SCHEDULED = "scheduled"                # Time-based
    EVENT = "event"                        # Event-driven
    THRESHOLD = "threshold"                # Metric threshold exceeded
    APPROVAL = "approval"                  # After approval


class WorkflowTemplate(Base):
    """
    Workflow Template Definition

    Defines the chain of steps to execute after data import.
    """
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Identification
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Scope
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    is_global = Column(Boolean, default=False)  # Available to all tenants

    # Trigger Configuration
    trigger_types = Column(JSON, nullable=True)  # List of WorkflowTriggerType values
    trigger_data_types = Column(JSON, nullable=True)  # List of SyncDataType values

    # Steps Configuration
    steps = Column(JSON, nullable=False)
    # [
    #   {"type": "validate", "config": {...}, "continue_on_failure": false, "timeout_seconds": 300},
    #   {"type": "analytics", "config": {...}, "continue_on_failure": true},
    #   {"type": "insights", "config": {"model": "claude-sonnet"}},
    #   {"type": "notify", "config": {"channels": ["email", "webhook"]}}
    # ]

    # Execution Settings
    timeout_minutes = Column(Integer, default=60)
    max_concurrent_executions = Column(Integer, default=1)
    retry_on_failure = Column(Boolean, default=False)
    max_retries = Column(Integer, default=0)

    # Notifications
    notify_on_start = Column(Boolean, default=False)
    notify_on_completion = Column(Boolean, default=True)
    notify_on_failure = Column(Boolean, default=True)
    notification_config = Column(JSON, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default for trigger type

    # Versioning
    version = Column(Integer, default=1)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    executions = relationship("WorkflowExecution", back_populates="template")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_workflow_template_code_tenant", "code", "tenant_id", unique=True),
        Index("ix_workflow_template_active", "is_active"),
    )

    def __repr__(self):
        return f"<WorkflowTemplate(id={self.id}, code={self.code})>"

    @property
    def step_count(self) -> int:
        """Number of steps in workflow"""
        return len(self.steps) if self.steps else 0


class WorkflowExecution(Base):
    """
    Workflow Execution Instance

    Tracks execution of a workflow template.
    """
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)

    # Template Reference
    template_id = Column(Integer, ForeignKey("workflow_templates.id", ondelete="SET NULL"), nullable=True)
    template_code = Column(String(50), nullable=False, index=True)  # Denormalized for history
    template_version = Column(Integer, nullable=True)

    # Trigger Context
    trigger_type = Column(Enum(WorkflowTriggerType, name="workflowtriggertype"), nullable=False, index=True)
    trigger_source_id = Column(Integer, nullable=True)  # e.g., SyncJobExecution.id
    trigger_source_type = Column(String(50), nullable=True)  # e.g., "sync_execution"
    trigger_metadata = Column(JSON, nullable=True)  # Additional trigger context

    # Scope
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    planning_cycle_id = Column(Integer, ForeignKey("planning_cycles.id", ondelete="SET NULL"), nullable=True)

    # Status
    status = Column(Enum(WorkflowStatus, name="workflow_status"), default=WorkflowStatus.PENDING, nullable=False, index=True)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=False)

    # Timing
    scheduled_at = Column(DateTime, nullable=True)  # If scheduled for later
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    timeout_at = Column(DateTime, nullable=True)

    # Results
    output_data = Column(JSON, nullable=True)  # Aggregated output from steps
    summary = Column(Text, nullable=True)  # Human-readable summary

    # Error Handling
    error_message = Column(Text, nullable=True)
    error_step = Column(Integer, nullable=True)  # Which step failed
    retry_count = Column(Integer, default=0)

    # Triggered By
    triggered_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    template = relationship("WorkflowTemplate", back_populates="executions")
    steps = relationship("WorkflowStepExecution", back_populates="workflow", cascade="all, delete-orphan",
                        order_by="WorkflowStepExecution.step_number")
    tenant = relationship("Tenant")
    trigger_user = relationship("User", foreign_keys=[triggered_by])

    __table_args__ = (
        Index("ix_workflow_exec_status_created", "status", "created_at"),
        Index("ix_workflow_exec_tenant_created", "tenant_id", "created_at"),
        Index("ix_workflow_exec_template_status", "template_id", "status"),
        Index("ix_workflow_exec_trigger", "trigger_type", "trigger_source_type", "trigger_source_id"),
    )

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, template={self.template_code}, status={self.status.value})>"

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage"""
        if self.total_steps == 0:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == WorkflowStatus.COMPLETED)
        return (completed / self.total_steps) * 100


class WorkflowStepExecution(Base):
    """
    Individual step execution within a workflow.
    """
    __tablename__ = "workflow_step_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Step Info
    step_number = Column(Integer, nullable=False)
    step_name = Column(String(100), nullable=True)  # Optional human-readable name
    step_type = Column(Enum(WorkflowStepType, name="workflowsteptype"), nullable=False)
    step_config = Column(JSON, nullable=True)

    # Execution Settings
    timeout_seconds = Column(Integer, nullable=True)
    continue_on_failure = Column(Boolean, default=False)

    # Status
    status = Column(Enum(WorkflowStatus, name="workflow_status"), default=WorkflowStatus.PENDING, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Results
    input_data = Column(JSON, nullable=True)  # Input from previous steps
    output_data = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)  # Step-specific metrics

    # Error Handling
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)

    # Relationships
    workflow = relationship("WorkflowExecution", back_populates="steps")

    __table_args__ = (
        Index("ix_workflow_step_workflow_number", "workflow_id", "step_number", unique=True),
    )

    def __repr__(self):
        return f"<WorkflowStepExecution(id={self.id}, step={self.step_number}, type={self.step_type.value})>"


# Default workflow templates for seeding
DEFAULT_WORKFLOW_TEMPLATES = {
    "post_sync_standard": {
        "name": "Standard Post-Sync Workflow",
        "description": "Default workflow triggered after SAP sync: validate, analyze, generate insights, notify",
        "trigger_types": [WorkflowTriggerType.SYNC_COMPLETED.value],
        "steps": [
            {
                "type": WorkflowStepType.VALIDATE.value,
                "name": "Data Validation",
                "config": {
                    "rules": ["completeness", "consistency", "referential_integrity"]
                },
                "continue_on_failure": False,
                "timeout_seconds": 300
            },
            {
                "type": WorkflowStepType.ANALYTICS.value,
                "name": "Run Analytics",
                "config": {
                    "calculations": ["inventory_projection", "supply_demand_match", "risk_analysis"]
                },
                "continue_on_failure": True,
                "timeout_seconds": 600
            },
            {
                "type": WorkflowStepType.INSIGHTS.value,
                "name": "Generate AI Insights",
                "config": {
                    "model": "claude-sonnet",
                    "max_recommendations": 10
                },
                "continue_on_failure": True,
                "timeout_seconds": 300
            },
            {
                "type": WorkflowStepType.SNAPSHOT.value,
                "name": "Create Planning Snapshot",
                "config": {
                    "snapshot_type": "auto",
                    "include_metrics": True
                },
                "continue_on_failure": True,
                "timeout_seconds": 120
            },
            {
                "type": WorkflowStepType.NOTIFY.value,
                "name": "Send Notifications",
                "config": {
                    "channels": ["email"],
                    "include_summary": True
                },
                "continue_on_failure": True,
                "timeout_seconds": 60
            }
        ],
        "timeout_minutes": 30
    },
    "post_sync_minimal": {
        "name": "Minimal Post-Sync Workflow",
        "description": "Lightweight workflow for frequent syncs: validate and snapshot only",
        "trigger_types": [WorkflowTriggerType.SYNC_COMPLETED.value],
        "steps": [
            {
                "type": WorkflowStepType.VALIDATE.value,
                "name": "Quick Validation",
                "config": {
                    "rules": ["completeness"]
                },
                "continue_on_failure": True,
                "timeout_seconds": 60
            },
            {
                "type": WorkflowStepType.SNAPSHOT.value,
                "name": "Auto Snapshot",
                "config": {
                    "snapshot_type": "auto",
                    "include_metrics": False
                },
                "continue_on_failure": True,
                "timeout_seconds": 60
            }
        ],
        "timeout_minutes": 5
    },
    "post_sync_analytics": {
        "name": "Analytics-Focused Workflow",
        "description": "Deep analytics workflow for daily syncs: full validation, analytics, reconciliation",
        "trigger_types": [WorkflowTriggerType.SYNC_COMPLETED.value],
        "steps": [
            {
                "type": WorkflowStepType.VALIDATE.value,
                "name": "Full Data Validation",
                "config": {
                    "rules": ["completeness", "consistency", "referential_integrity", "business_rules"]
                },
                "continue_on_failure": False,
                "timeout_seconds": 600
            },
            {
                "type": WorkflowStepType.RECONCILE.value,
                "name": "Data Reconciliation",
                "config": {
                    "compare_with": "previous_sync",
                    "tolerance_percent": 5
                },
                "continue_on_failure": True,
                "timeout_seconds": 300
            },
            {
                "type": WorkflowStepType.ANALYTICS.value,
                "name": "Comprehensive Analytics",
                "config": {
                    "calculations": [
                        "inventory_projection",
                        "supply_demand_match",
                        "risk_analysis",
                        "bullwhip_detection",
                        "cost_variance"
                    ]
                },
                "continue_on_failure": True,
                "timeout_seconds": 900
            },
            {
                "type": WorkflowStepType.INSIGHTS.value,
                "name": "Generate AI Insights",
                "config": {
                    "model": "claude-sonnet",
                    "max_recommendations": 20,
                    "include_root_cause": True
                },
                "continue_on_failure": True,
                "timeout_seconds": 600
            },
            {
                "type": WorkflowStepType.SNAPSHOT.value,
                "name": "Create Baseline Snapshot",
                "config": {
                    "snapshot_type": "checkpoint",
                    "include_metrics": True,
                    "include_analytics": True
                },
                "continue_on_failure": False,
                "timeout_seconds": 300
            },
            {
                "type": WorkflowStepType.NOTIFY.value,
                "name": "Send Daily Report",
                "config": {
                    "channels": ["email"],
                    "include_summary": True,
                    "include_recommendations": True
                },
                "continue_on_failure": True,
                "timeout_seconds": 60
            }
        ],
        "timeout_minutes": 60
    }
}

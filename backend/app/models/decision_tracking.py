"""
Decision Tracking Models for Agent Performance Metrics

Tracks agent decisions and user responses for calculating:
- Agent Performance Score: Quality of agent decisions vs outcomes (-100 to +100)
- Human Override Rate: % of decisions overridden by humans

These metrics are core to the Powell Framework demonstration.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON,
    Boolean, Enum as SAEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .tenant import Tenant


class DecisionType(str, Enum):
    """Type of decision being tracked."""
    DEMAND_FORECAST = "demand_forecast"
    SUPPLY_PLAN = "supply_plan"
    INVENTORY_REBALANCE = "inventory_rebalance"
    PURCHASE_ORDER = "purchase_order"
    PRODUCTION_ORDER = "production_order"
    ATP_ALLOCATION = "atp_allocation"
    SAFETY_STOCK = "safety_stock"
    REPLENISHMENT = "replenishment"
    EXCEPTION_RESOLUTION = "exception_resolution"


class DecisionStatus(str, Enum):
    """Status of the decision in the workflow."""
    PENDING = "pending"           # Awaiting user action
    ACCEPTED = "accepted"         # User accepted agent recommendation
    REJECTED = "rejected"         # User rejected (overrode) agent recommendation
    AUTO_EXECUTED = "auto_executed"  # Autonomous mode - auto-executed
    EXPIRED = "expired"           # Decision window passed


class DecisionUrgency(str, Enum):
    """Urgency level of the decision."""
    URGENT = "urgent"
    STANDARD = "standard"
    LOW = "low"


class AgentDecision(Base):
    """
    Tracks individual decisions made by AI agents.

    Used for:
    - Copilot mode: Shows recommendations user can accept/reject
    - Autonomous mode: Records auto-executed decisions
    - Agent Performance calculation: Tracks decision quality outcomes
    - Human Override tracking: Tracks override rates
    """
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Context
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Decision identification
    decision_type: Mapped[DecisionType] = mapped_column(
        SAEnum(DecisionType, name="decision_type_enum"), nullable=False, index=True
    )
    item_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # The issue/recommendation
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)
    impact_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    impact_description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Agent's recommendation
    agent_recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1

    # Numeric recommendation (if applicable)
    recommended_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    previous_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status and urgency
    status: Mapped[DecisionStatus] = mapped_column(
        SAEnum(DecisionStatus, name="decision_status_enum"),
        nullable=False,
        default=DecisionStatus.PENDING,
        index=True
    )
    urgency: Mapped[DecisionUrgency] = mapped_column(
        SAEnum(DecisionUrgency, name="decision_urgency_enum"),
        nullable=False,
        default=DecisionUrgency.STANDARD
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # User response (for copilot mode)
    user_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # accept, reject, modify
    user_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # If user modified
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Outcome tracking (for Agent Performance)
    outcome_measured: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # -100 to +100
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Override effectiveness (filled by OutcomeCollector when outcome measured)
    agent_counterfactual_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    human_actual_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_classification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Agent metadata
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, default="trm")
    agent_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Planning cycle reference
    planning_cycle: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)

    # Additional context as JSON
    context_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index('ix_agent_decisions_tenant_status', 'tenant_id', 'status'),
        Index('ix_agent_decisions_tenant_type_cycle', 'tenant_id', 'decision_type', 'planning_cycle'),
        Index('ix_agent_decisions_user_status', 'user_id', 'status'),
    )

    def __repr__(self):
        return f"<AgentDecision {self.id} {self.decision_type.value} {self.status.value}>"

    def to_dict(self):
        return {
            "id": self.id,
            "decision_type": self.decision_type.value,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "category": self.category,
            "issue_summary": self.issue_summary,
            "impact_value": self.impact_value,
            "impact_description": self.impact_description,
            "agent_recommendation": self.agent_recommendation,
            "agent_reasoning": self.agent_reasoning,
            "agent_confidence": self.agent_confidence,
            "recommended_value": self.recommended_value,
            "status": self.status.value,
            "urgency": self.urgency.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "user_action": self.user_action,
            "override_reason": self.override_reason,
            "outcome_quality_score": self.outcome_quality_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PerformanceMetric(Base):
    """
    Aggregated Agent Performance metrics by time period.

    Pre-calculated for dashboard performance.
    """
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Time period
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly

    # Optional category breakdown
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    decision_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Decision counts
    total_decisions: Mapped[int] = mapped_column(Integer, default=0)
    agent_decisions: Mapped[int] = mapped_column(Integer, default=0)
    planner_decisions: Mapped[int] = mapped_column(Integer, default=0)  # Manual/overridden

    # Agent Performance scores (-100 to +100 scale, higher is better)
    agent_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    planner_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Human Override Rate - % of decisions overridden by humans
    override_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    override_count: Mapped[int] = mapped_column(Integer, default=0)

    # Automation metrics
    automation_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Override effectiveness aggregates
    override_effectiveness_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # % beneficial
    override_net_delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Cumulative reward delta

    # Active resources
    active_agents: Mapped[int] = mapped_column(Integer, default=0)
    active_planners: Mapped[int] = mapped_column(Integer, default=0)

    # SKU metrics
    total_skus: Mapped[int] = mapped_column(Integer, default=0)
    skus_per_planner: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_performance_metrics_tenant_period', 'tenant_id', 'period_start', 'period_type'),
    )

    def to_dict(self):
        return {
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_type": self.period_type,
            "category": self.category,
            "total_decisions": self.total_decisions,
            "agent_decisions": self.agent_decisions,
            "planner_decisions": self.planner_decisions,
            "agent_score": self.agent_score,
            "planner_score": self.planner_score,
            "override_rate": self.override_rate,
            "automation_percentage": self.automation_percentage,
            "active_agents": self.active_agents,
            "active_planners": self.active_planners,
            "skus_per_planner": self.skus_per_planner,
        }


class SOPWorklistItem(Base):
    """
    S&OP Worklist items for tactical decision-making.

    Higher-level than AgentDecision - represents strategic/tactical issues
    that require S&OP Director attention.
    """
    __tablename__ = "sop_worklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Item identification
    item_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Issue details
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)  # PORTFOLIO, CAPACITY, etc.
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Impact
    impact_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    impact_description: Mapped[str] = mapped_column(String(255), nullable=False)
    impact_type: Mapped[str] = mapped_column(String(20), default="negative")  # negative, positive, trade-off

    # Timeline
    due_description: Mapped[str] = mapped_column(String(50), nullable=False)  # "EOD", "Friday", "48 hours"
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    urgency: Mapped[DecisionUrgency] = mapped_column(
        SAEnum(DecisionUrgency, name="decision_urgency_enum"),
        nullable=False,
        default=DecisionUrgency.STANDARD
    )

    # AI recommendation
    agent_recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[DecisionStatus] = mapped_column(
        SAEnum(DecisionStatus, name="decision_status_enum"),
        nullable=False,
        default=DecisionStatus.PENDING
    )

    # User response
    resolved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index('ix_sop_worklist_tenant_status', 'tenant_id', 'status'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "category": self.category,
            "issue_type": self.issue_type,
            "issue_summary": self.issue_summary,
            "impact_value": self.impact_value,
            "impact_description": self.impact_description,
            "impact_type": self.impact_type,
            "due_description": self.due_description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "urgency": self.urgency.value,
            "agent_recommendation": self.agent_recommendation,
            "agent_reasoning": self.agent_reasoning,
            "status": self.status.value,
            "resolution_action": self.resolution_action,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

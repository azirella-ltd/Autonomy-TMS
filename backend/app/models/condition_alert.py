"""
Condition Alert Models - Persistent Condition Tracking

Stores information about detected conditions and their resolution.
Provides audit trail for condition detection, escalation, and resolution.

Part of the AIIO Framework for agent transparency and accountability.
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Boolean,
    Float, Enum, Index, Text
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List
import enum

from .base import Base


class ConditionType(str, enum.Enum):
    """Types of conditions that can be monitored."""
    # Supply-side conditions
    ATP_SHORTFALL = "atp_shortfall"
    ATP_CRITICAL = "atp_critical"
    INVENTORY_BELOW_SAFETY = "inventory_below_safety"
    INVENTORY_BELOW_TARGET = "inventory_below_target"
    INVENTORY_ABOVE_MAX = "inventory_above_max"

    # Demand-side conditions
    DEMAND_SPIKE = "demand_spike"
    FORECAST_DEVIATION = "forecast_deviation"

    # Capacity conditions
    CAPACITY_OVERLOAD = "capacity_overload"
    CAPACITY_CONSTRAINT = "capacity_constraint"

    # Order conditions
    ORDER_PAST_DUE = "order_past_due"
    ORDER_AT_RISK = "order_at_risk"

    # Network conditions
    MULTI_SITE_SHORTFALL = "multi_site_shortfall"
    SUPPLY_CHAIN_BOTTLENECK = "supply_chain_bottleneck"


class ConditionSeverity(str, enum.Enum):
    """Severity levels based on duration and impact."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ConditionResolution(str, enum.Enum):
    """How a condition was resolved."""
    SELF_RESOLVED = "self_resolved"
    AGENT_RESOLVED = "agent_resolved"
    HUMAN_RESOLVED = "human_resolved"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"


class ConditionAlert(Base):
    """
    Persistent storage for detected conditions.

    Tracks the full lifecycle of a condition from detection through resolution,
    including severity escalation and agent/human actions taken.
    """
    __tablename__ = "condition_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Scope
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    condition_type: Mapped[ConditionType] = mapped_column(
        Enum(ConditionType, name="conditiontype"), nullable=False, index=True
    )

    # Entity context
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # product, site, order
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    severity: Mapped[ConditionSeverity] = mapped_column(
        Enum(ConditionSeverity, name="conditionseverity"), default=ConditionSeverity.INFO, nullable=False
    )

    # Timing
    first_detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    duration_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Values
    current_value: Mapped[float] = mapped_column(Float, nullable=True)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=True)
    deviation_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Context (JSON storage for flexible metadata)
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Related conditions (for network-wide patterns)
    related_condition_ids: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    # Resolution
    resolution: Mapped[Optional[ConditionResolution]] = mapped_column(
        Enum(ConditionResolution, name="conditionresolution"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_agent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Actions taken
    actions_triggered: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    scenario_evaluation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scenario_evaluations.id", ondelete="SET NULL"), nullable=True
    )

    # Supply requests (for inter-agent communication)
    supply_requests: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    # S&OP escalation
    triggered_soop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    soop_cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("planning_cycles.id", ondelete="SET NULL"), nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    customer = relationship("Customer")
    resolved_by_user = relationship("User", foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        Index("ix_condition_alert_customer_type", "customer_id", "condition_type"),
        Index("ix_condition_alert_entity", "entity_type", "entity_id"),
        Index("ix_condition_alert_active_severity", "is_active", "severity"),
        Index("ix_condition_alert_customer_active", "customer_id", "is_active"),
    )

    def __repr__(self):
        return f"<ConditionAlert(id={self.id}, type={self.condition_type.value}, entity={self.entity_id}, severity={self.severity.value})>"


class ScenarioEvaluation(Base):
    """
    Persistent storage for scenario evaluations.

    Records the scenarios evaluated, their scorecards, and the final recommendation.
    Provides audit trail for agent decision-making.
    """
    __tablename__ = "scenario_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Scope
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Triggering context
    triggered_by_condition_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("condition_alerts.id", ondelete="SET NULL"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)  # condition, manual, soop
    trigger_entity_type: Mapped[str] = mapped_column(String(50), nullable=True)
    trigger_entity_id: Mapped[str] = mapped_column(String(100), nullable=True)

    # Scenarios evaluated
    scenarios_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scenario_definitions: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    scenario_results: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    # Recommendation
    recommended_scenario_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommended_scenario_name: Mapped[str] = mapped_column(String(200), nullable=True)
    recommendation_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    recommendation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Balanced scorecard summary
    recommended_overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    recommended_service_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_total_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    probability_of_success: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_at_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Trade-offs identified
    trade_offs: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    # Rankings by perspective
    ranking_overall: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    ranking_financial: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    ranking_customer: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    ranking_operational: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)

    # Action taken
    action_taken: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # accepted, rejected, modified
    action_taken_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action_taken_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    action_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Linked agent action
    agent_action_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("agent_action.id", ondelete="SET NULL"), nullable=True
    )

    # Execution metrics
    evaluation_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    simulations_run: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Audit
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    customer = relationship("Customer")
    triggering_condition = relationship(
        "ConditionAlert",
        foreign_keys=[triggered_by_condition_id],
        back_populates="scenario_evaluation"
    )
    action_taken_by = relationship("User", foreign_keys=[action_taken_by_user_id])
    agent_action = relationship("AgentAction", foreign_keys=[agent_action_id])

    __table_args__ = (
        Index("ix_scenario_eval_customer", "customer_id"),
        Index("ix_scenario_eval_trigger", "trigger_type", "trigger_entity_id"),
        Index("ix_scenario_eval_time", "evaluated_at"),
    )

    def __repr__(self):
        return f"<ScenarioEvaluation(id={self.id}, scenarios={self.scenarios_count}, recommended={self.recommended_scenario_name})>"


class SupplyRequest(Base):
    """
    Inter-agent supply request tracking.

    Records when one agent/site requests supply assistance from another.
    Enables collaborative agent behavior.
    """
    __tablename__ = "supply_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Scope
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Participants
    requesting_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # site, agent
    requesting_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requested_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Product and quantity
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_needed: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_available: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity_fulfilled: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timing
    needed_by: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Status
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # 1=highest
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, accepted, rejected, fulfilled

    # Triggering condition
    condition_alert_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("condition_alerts.id", ondelete="SET NULL"), nullable=True
    )

    # Context
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    customer = relationship("Customer")
    condition_alert = relationship("ConditionAlert")

    __table_args__ = (
        Index("ix_supply_request_requesting", "requesting_entity_type", "requesting_entity_id"),
        Index("ix_supply_request_requested", "requested_entity_type", "requested_entity_id"),
        Index("ix_supply_request_status", "status"),
        Index("ix_supply_request_customer_status", "customer_id", "status"),
    )

    def __repr__(self):
        return f"<SupplyRequest(id={self.id}, from={self.requesting_entity_id}, to={self.requested_entity_id}, qty={self.quantity_needed})>"


# Add back-reference to ConditionAlert
ConditionAlert.scenario_evaluation = relationship(
    "ScenarioEvaluation",
    foreign_keys=[ScenarioEvaluation.triggered_by_condition_id],
    back_populates="triggering_condition",
    uselist=False
)

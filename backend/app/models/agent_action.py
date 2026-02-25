"""
Agent Action Model - AIIO Framework Implementation

This module implements the Automate, Inform, Inspect, Override (AIIO) framework
for tracking AI agent decisions with full transparency and audit trail.

AIIO Framework:
- AUTOMATE: Agent executes action automatically, no user notification required
- INFORM: Agent executes action and notifies user (acknowledgment workflow)
- INSPECT: User capability to drill into any action and see explanation/alternatives
- OVERRIDE: User capability to change a decision (requires reason for audit/learning)

Key Principles:
1. Every agent action is recorded with full explanation
2. Users can always understand WHY an action was taken
3. Users can override with mandatory reason tracking
4. Hierarchy context enables drill-down by site/product/time
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime, Text,
    ForeignKey, Index, Enum as SAEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .base import Base
from .planning_hierarchy import SiteHierarchyLevel, ProductHierarchyLevel, TimeBucketType


class ActionMode(str, Enum):
    """How the agent handled this action - agent-initiated modes."""
    AUTOMATE = "automate"  # Executed automatically, no notification
    INFORM = "inform"      # Executed, user notified for acknowledgment


class ActionCategory(str, Enum):
    """Categories of agent actions for filtering and grouping."""
    INVENTORY = "inventory"       # Rebalancing, safety stock adjustments
    PROCUREMENT = "procurement"   # PO creation, vendor selection
    DEMAND = "demand"            # Forecast adjustments, demand sensing
    PRODUCTION = "production"     # Production scheduling, capacity allocation
    LOGISTICS = "logistics"       # Shipment routing, carrier selection
    PRICING = "pricing"          # Dynamic pricing, promotion recommendations
    RISK = "risk"                # Risk mitigation actions
    ALLOCATION = "allocation"    # ATP/CTP allocation decisions
    OTHER = "other"              # Uncategorized actions


class ExecutionResult(str, Enum):
    """Result status of action execution."""
    SUCCESS = "success"      # Action completed successfully
    PARTIAL = "partial"      # Action partially completed
    FAILED = "failed"        # Action failed to execute
    PENDING = "pending"      # Action scheduled but not yet executed


class AgentAction(Base):
    """
    Record of an action taken or proposed by an AI agent.

    AIIO Framework:
    - Automate/Inform: Agent-initiated, stored for audit trail
    - Inspect/Override: User-initiated on any stored action

    Hierarchy Context:
    - Each action is tagged with site/product/time hierarchy keys
    - Enables drill-down from company-wide view to specific SKU/site
    - Supports aggregation of metrics across hierarchy levels

    Example:
        AgentAction(
            action_mode=ActionMode.INFORM,
            action_type="rebalance",
            category=ActionCategory.INVENTORY,
            title="Rebalanced 500 units from DC-East to DC-West",
            explanation="DC-West projected to stockout in 3 days based on...",
            site_key="SITE_DC-West",
            product_key="PRODUCT_Lager-6pk",
            ...
        )
    """
    __tablename__ = "agent_action"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)

    # Action classification
    action_mode: Mapped[ActionMode] = mapped_column(
        SAEnum(ActionMode, name="action_mode_enum"),
        nullable=False,
        comment="AUTOMATE or INFORM - how agent handled this action"
    )
    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Specific action type: rebalance, po_create, forecast_adjust, etc."
    )
    category: Mapped[ActionCategory] = mapped_column(
        SAEnum(ActionCategory, name="action_category_enum"),
        nullable=False,
        default=ActionCategory.OTHER,
        comment="Action category for grouping and filtering"
    )

    # What was done
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Human-readable summary of the action"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Detailed description of the action"
    )

    # EXPLANATION - Critical for AIIO (the "why")
    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="WHY this action was taken - must be human-readable"
    )
    reasoning_chain: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Structured reasoning steps: [{step, input, output, confidence}]"
    )
    alternatives_considered: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Other options agent evaluated: [{alternative, score, why_not_chosen}]"
    )

    # Hierarchy context (for drill-down)
    site_hierarchy_level: Mapped[SiteHierarchyLevel] = mapped_column(
        SAEnum(SiteHierarchyLevel, name="site_hierarchy_level_enum", create_constraint=False),
        nullable=False,
        default=SiteHierarchyLevel.SITE,
        comment="Granularity level of site context"
    )
    site_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Site identifier at the specified level: REGION_Americas, SITE_DC-West"
    )
    product_hierarchy_level: Mapped[ProductHierarchyLevel] = mapped_column(
        SAEnum(ProductHierarchyLevel, name="product_hierarchy_level_enum", create_constraint=False),
        nullable=False,
        default=ProductHierarchyLevel.PRODUCT,
        comment="Granularity level of product context"
    )
    product_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Product identifier at the specified level: FAMILY_Beverage, PRODUCT_Product-6pk"
    )
    time_bucket: Mapped[TimeBucketType] = mapped_column(
        SAEnum(TimeBucketType, name="time_bucket_type_enum", create_constraint=False),
        nullable=False,
        default=TimeBucketType.DAY,
        comment="Time granularity: HOUR, DAY, WEEK, MONTH"
    )
    time_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Time period: 2026-02, 2026-W05, 2026-02-03"
    )

    # Impact metrics (before/after comparison)
    metric_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Primary metric being affected: inventory_level, service_level, cost"
    )
    metric_before: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Metric value before action"
    )
    metric_after: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Metric value after action"
    )
    estimated_impact: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Estimated impact: {cost_saved, risk_reduced, service_level_improvement}"
    )

    # Execution details
    executed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="When the action was executed"
    )
    execution_result: Mapped[ExecutionResult] = mapped_column(
        SAEnum(ExecutionResult, name="execution_result_enum"),
        nullable=False,
        default=ExecutionResult.SUCCESS,
        comment="Outcome of action execution"
    )
    execution_details: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Additional execution details: {entities_affected, transaction_ids, etc.}"
    )

    # User interaction tracking (for INFORM mode)
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether user has acknowledged this INFORM action"
    )
    acknowledged_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        comment="User who acknowledged this action"
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="When the action was acknowledged"
    )

    # Override tracking (for user corrections)
    is_overridden: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether user has overridden this action"
    )
    overridden_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        comment="User who overrode this action"
    )
    overridden_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="When the action was overridden"
    )
    override_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="REQUIRED when overriding - reason for the override (for audit/learning)"
    )
    override_action: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="What the user did instead: {new_quantity, new_target, etc.}"
    )

    # Agent identification
    agent_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Which agent: trm_atp, trm_rebalance, gnn_allocation, llm_planner"
    )
    agent_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Agent model version for reproducibility"
    )

    # Related entities (optional links)
    related_entity_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Type of related entity: purchase_order, transfer_order, forecast, etc."
    )
    related_entity_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="ID of related entity for navigation"
    )

    # =========================================================================
    # CONFORMAL PREDICTION - Calibrated Uncertainty Quantification
    # =========================================================================
    # These fields enable calibrated predictions with uncertainty bounds,
    # allowing users to understand the likelihood of predicted outcomes.

    # Predicted outcome with confidence interval
    predicted_outcome: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Point estimate of the predicted outcome (e.g., expected service level)"
    )
    prediction_interval_lower: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Lower bound of prediction interval (e.g., P10)"
    )
    prediction_interval_upper: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Upper bound of prediction interval (e.g., P90)"
    )
    confidence_level: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Confidence level for the interval (0.80 = 80% confidence)"
    )

    # Calibration metrics - how reliable is this prediction?
    calibration_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Historical calibration accuracy (0-1, how often intervals contain true value)"
    )
    nonconformity_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="How unusual this prediction context is vs training data (lower = more typical)"
    )

    # Outcome tracking - for feedback loop and recalibration
    actual_outcome: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Actual observed outcome after action was executed (for learning)"
    )
    outcome_within_interval: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        comment="Whether actual_outcome fell within prediction interval (calibration feedback)"
    )
    outcome_measured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="When the actual outcome was measured"
    )

    # Belief state reference - link to Powell uncertainty quantification
    belief_state_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("powell_belief_state.id", ondelete="SET NULL"),
        comment="Link to powell_belief_state for full uncertainty context"
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    customer = relationship("Customer")
    acknowledger = relationship("User", foreign_keys=[acknowledged_by])
    overrider = relationship("User", foreign_keys=[overridden_by])
    belief_state = relationship("PowellBeliefState", foreign_keys=[belief_state_id])

    __table_args__ = (
        Index('idx_agent_action_customer_time', 'customer_id', 'executed_at'),
        Index('idx_agent_action_hierarchy', 'site_key', 'product_key', 'time_key'),
        Index('idx_agent_action_mode', 'action_mode', 'is_acknowledged'),
        Index('idx_agent_action_category', 'category', 'customer_id'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "action_mode": self.action_mode.value,
            "action_type": self.action_type,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "explanation": self.explanation,
            "reasoning_chain": self.reasoning_chain,
            "alternatives_considered": self.alternatives_considered,
            "site_hierarchy_level": self.site_hierarchy_level.value,
            "site_key": self.site_key,
            "product_hierarchy_level": self.product_hierarchy_level.value,
            "product_key": self.product_key,
            "time_bucket": self.time_bucket.value,
            "time_key": self.time_key,
            "metric_name": self.metric_name,
            "metric_before": self.metric_before,
            "metric_after": self.metric_after,
            "estimated_impact": self.estimated_impact,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_result": self.execution_result.value,
            "execution_details": self.execution_details,
            "is_acknowledged": self.is_acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "is_overridden": self.is_overridden,
            "overridden_by": self.overridden_by,
            "overridden_at": self.overridden_at.isoformat() if self.overridden_at else None,
            "override_reason": self.override_reason,
            "override_action": self.override_action,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            # Conformal prediction fields
            "predicted_outcome": self.predicted_outcome,
            "prediction_interval_lower": self.prediction_interval_lower,
            "prediction_interval_upper": self.prediction_interval_upper,
            "confidence_level": self.confidence_level,
            "calibration_score": self.calibration_score,
            "nonconformity_score": self.nonconformity_score,
            "actual_outcome": self.actual_outcome,
            "outcome_within_interval": self.outcome_within_interval,
            "outcome_measured_at": self.outcome_measured_at.isoformat() if self.outcome_measured_at else None,
            "belief_state_id": self.belief_state_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary for list views."""
        return {
            "id": self.id,
            "action_mode": self.action_mode.value,
            "action_type": self.action_type,
            "category": self.category.value,
            "title": self.title,
            "explanation": self.explanation[:200] + "..." if len(self.explanation) > 200 else self.explanation,
            "site_key": self.site_key,
            "product_key": self.product_key,
            "time_key": self.time_key,
            "metric_name": self.metric_name,
            "metric_before": self.metric_before,
            "metric_after": self.metric_after,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_result": self.execution_result.value,
            "is_acknowledged": self.is_acknowledged,
            "is_overridden": self.is_overridden,
            "agent_id": self.agent_id,
            # Key conformal prediction fields for summary view
            "predicted_outcome": self.predicted_outcome,
            "prediction_interval_lower": self.prediction_interval_lower,
            "prediction_interval_upper": self.prediction_interval_upper,
            "confidence_level": self.confidence_level,
            "nonconformity_score": self.nonconformity_score,
        }

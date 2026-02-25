"""
TRM Training Data Models

Stores transactional data for TRM training:
1. Expert Decision Logs - actual planner decisions with full context
2. Outcome Tracking - what happened after each decision
3. Replay Buffer - (state, action, reward, next_state) tuples for RL
4. Continuous Learning - feedback loop for model improvement

Each TRM type has different state/action/reward structures.
"""

from enum import Enum
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime, Date,
    ForeignKey, Enum as SAEnum, Text, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base


class DecisionSource(str, Enum):
    """Source of the decision"""
    EXPERT_HUMAN = "expert_human"  # Human planner made decision
    AI_ACCEPTED = "ai_accepted"  # AI recommended, human accepted
    AI_MODIFIED = "ai_modified"  # AI recommended, human modified
    AI_REJECTED = "ai_rejected"  # AI recommended, human rejected
    AI_AUTONOMOUS = "ai_autonomous"  # AI made decision autonomously
    SYNTHETIC = "synthetic"  # Generated for training


class OutcomeStatus(str, Enum):
    """Status of outcome measurement"""
    PENDING = "pending"  # Outcome not yet known
    MEASURED = "measured"  # Outcome measured
    PARTIAL = "partial"  # Partial outcome (still in progress)


# =============================================================================
# ATP Executor Training Data
# =============================================================================

class ATPDecisionLog(Base):
    """
    Expert decision log for ATP (Available-to-Promise) decisions.

    Records what planner decided when fulfilling customer orders.
    """
    __tablename__ = "trm_atp_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    site_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Order context
    order_id: Mapped[Optional[str]] = mapped_column(String(100))
    customer_id: Mapped[Optional[str]] = mapped_column(String(100))
    requested_qty: Mapped[float] = mapped_column(Float, nullable=False)
    requested_date: Mapped[date] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=highest, 5=lowest

    # State at decision time (normalized features)
    state_inventory: Mapped[float] = mapped_column(Float)  # On-hand
    state_pipeline: Mapped[float] = mapped_column(Float)  # In-transit
    state_backlog: Mapped[float] = mapped_column(Float)  # Existing backlog
    state_allocated: Mapped[float] = mapped_column(Float)  # Already allocated
    state_available_atp: Mapped[float] = mapped_column(Float)  # Available to promise
    state_demand_forecast: Mapped[float] = mapped_column(Float)  # Expected demand
    state_other_orders_pending: Mapped[int] = mapped_column(Integer)  # Queue depth
    state_features: Mapped[Dict] = mapped_column(JSON, default=dict)  # Additional features

    # Decision made
    action_type: Mapped[str] = mapped_column(String(50))  # fulfill, partial, defer, reserve, reject
    action_qty_fulfilled: Mapped[float] = mapped_column(Float)
    action_qty_backordered: Mapped[float] = mapped_column(Float, default=0)
    action_promise_date: Mapped[Optional[date]] = mapped_column(Date)
    action_allocation_tier: Mapped[Optional[int]] = mapped_column(Integer)  # Which priority tier used
    action_reason: Mapped[Optional[str]] = mapped_column(Text)  # Planner's reasoning

    # Decision metadata
    source: Mapped[DecisionSource] = mapped_column(
        SAEnum(DecisionSource, name="decision_source_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=DecisionSource.EXPERT_HUMAN
    )
    decision_maker_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    ai_recommendation: Mapped[Optional[Dict]] = mapped_column(JSON)  # What AI suggested
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_atp_decision_customer_date', 'customer_id', 'decision_date'),
    )


class ATPOutcome(Base):
    """
    Outcome tracking for ATP decisions.

    Records what actually happened after the decision.
    """
    __tablename__ = "trm_atp_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trm_atp_decision_log.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Outcome status
    status: Mapped[OutcomeStatus] = mapped_column(
        SAEnum(OutcomeStatus, name="outcome_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=OutcomeStatus.PENDING
    )
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # What actually happened
    actual_qty_shipped: Mapped[Optional[float]] = mapped_column(Float)
    actual_ship_date: Mapped[Optional[date]] = mapped_column(Date)
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date)

    # Outcome metrics
    on_time: Mapped[Optional[bool]] = mapped_column(Boolean)
    in_full: Mapped[Optional[bool]] = mapped_column(Boolean)
    otif: Mapped[Optional[bool]] = mapped_column(Boolean)  # On-time in-full
    days_late: Mapped[Optional[int]] = mapped_column(Integer)
    fill_rate: Mapped[Optional[float]] = mapped_column(Float)  # actual/requested

    # Impact on downstream
    customer_satisfaction_impact: Mapped[Optional[float]] = mapped_column(Float)  # -1 to +1
    revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    cost_impact: Mapped[Optional[float]] = mapped_column(Float)  # Expediting, penalties

    # Calculated reward for RL
    reward: Mapped[Optional[float]] = mapped_column(Float)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state (for RL transition)
    next_state_inventory: Mapped[Optional[float]] = mapped_column(Float)
    next_state_backlog: Mapped[Optional[float]] = mapped_column(Float)
    next_state_features: Mapped[Dict] = mapped_column(JSON, default=dict)


# =============================================================================
# Inventory Rebalancing Training Data
# =============================================================================

class RebalancingDecisionLog(Base):
    """
    Expert decision log for inventory rebalancing decisions.

    Records transfer decisions between locations.
    """
    __tablename__ = "trm_rebalancing_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Network state at decision time
    state_site_inventories: Mapped[Dict] = mapped_column(JSON)  # {site_id: qty}
    state_site_backlogs: Mapped[Dict] = mapped_column(JSON)  # {site_id: qty}
    state_site_demands: Mapped[Dict] = mapped_column(JSON)  # {site_id: forecast}
    state_transit_matrix: Mapped[Dict] = mapped_column(JSON)  # {(from,to): qty_in_transit}
    state_network_imbalance: Mapped[float] = mapped_column(Float)  # Coefficient of variation
    state_features: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Decision made
    action_type: Mapped[str] = mapped_column(String(50))  # transfer, hold, expedite
    action_from_site_id: Mapped[Optional[int]] = mapped_column(Integer)
    action_to_site_id: Mapped[Optional[int]] = mapped_column(Integer)
    action_qty: Mapped[float] = mapped_column(Float, default=0)
    action_urgency: Mapped[str] = mapped_column(String(20), default="normal")  # normal, expedite
    action_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Decision metadata
    source: Mapped[DecisionSource] = mapped_column(
        SAEnum(DecisionSource, name="decision_source_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=DecisionSource.EXPERT_HUMAN
    )
    decision_maker_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    ai_recommendation: Mapped[Optional[Dict]] = mapped_column(JSON)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RebalancingOutcome(Base):
    """Outcome tracking for rebalancing decisions."""
    __tablename__ = "trm_rebalancing_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trm_rebalancing_decision_log.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    status: Mapped[OutcomeStatus] = mapped_column(
        SAEnum(OutcomeStatus, name="outcome_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=OutcomeStatus.PENDING
    )
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # What happened
    actual_transfer_qty: Mapped[Optional[float]] = mapped_column(Float)
    actual_arrival_date: Mapped[Optional[date]] = mapped_column(Date)
    transfer_completed: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Impact
    from_site_stockout_prevented: Mapped[Optional[bool]] = mapped_column(Boolean)
    to_site_stockout_prevented: Mapped[Optional[bool]] = mapped_column(Boolean)
    service_level_before: Mapped[Optional[float]] = mapped_column(Float)
    service_level_after: Mapped[Optional[float]] = mapped_column(Float)
    transfer_cost: Mapped[Optional[float]] = mapped_column(Float)
    holding_cost_delta: Mapped[Optional[float]] = mapped_column(Float)

    # Reward
    reward: Mapped[Optional[float]] = mapped_column(Float)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state
    next_state_site_inventories: Mapped[Dict] = mapped_column(JSON, default=dict)
    next_state_network_imbalance: Mapped[Optional[float]] = mapped_column(Float)


# =============================================================================
# PO Creation Training Data
# =============================================================================

class PODecisionLog(Base):
    """
    Expert decision log for Purchase Order creation decisions.

    Records when and how much to order.
    """
    __tablename__ = "trm_po_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    site_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # State at decision time
    state_inventory: Mapped[float] = mapped_column(Float)
    state_pipeline: Mapped[float] = mapped_column(Float)  # On order
    state_backlog: Mapped[float] = mapped_column(Float)
    state_reorder_point: Mapped[float] = mapped_column(Float)
    state_safety_stock: Mapped[float] = mapped_column(Float)
    state_days_of_supply: Mapped[float] = mapped_column(Float)
    state_demand_forecast: Mapped[List[float]] = mapped_column(JSON)  # Next N periods
    state_demand_variability: Mapped[float] = mapped_column(Float)
    state_supplier_lead_time: Mapped[float] = mapped_column(Float)
    state_supplier_reliability: Mapped[float] = mapped_column(Float)
    state_features: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Decision made
    action_type: Mapped[str] = mapped_column(String(50))  # order, defer, expedite, cancel
    action_order_qty: Mapped[float] = mapped_column(Float, default=0)
    action_requested_date: Mapped[Optional[date]] = mapped_column(Date)
    action_expedite: Mapped[bool] = mapped_column(Boolean, default=False)
    action_reason: Mapped[Optional[str]] = mapped_column(Text)

    # PO details if created
    po_number: Mapped[Optional[str]] = mapped_column(String(100))
    po_unit_cost: Mapped[Optional[float]] = mapped_column(Float)

    # Decision metadata
    source: Mapped[DecisionSource] = mapped_column(
        SAEnum(DecisionSource, name="decision_source_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=DecisionSource.EXPERT_HUMAN
    )
    decision_maker_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    ai_recommendation: Mapped[Optional[Dict]] = mapped_column(JSON)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class POOutcome(Base):
    """Outcome tracking for PO decisions."""
    __tablename__ = "trm_po_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trm_po_decision_log.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    status: Mapped[OutcomeStatus] = mapped_column(
        SAEnum(OutcomeStatus, name="outcome_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=OutcomeStatus.PENDING
    )
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # What happened
    actual_receipt_qty: Mapped[Optional[float]] = mapped_column(Float)
    actual_receipt_date: Mapped[Optional[date]] = mapped_column(Date)
    lead_time_actual: Mapped[Optional[int]] = mapped_column(Integer)  # Days

    # Impact
    stockout_occurred: Mapped[Optional[bool]] = mapped_column(Boolean)
    stockout_days: Mapped[Optional[int]] = mapped_column(Integer)
    excess_inventory_cost: Mapped[Optional[float]] = mapped_column(Float)
    expedite_cost: Mapped[Optional[float]] = mapped_column(Float)
    dos_at_receipt: Mapped[Optional[float]] = mapped_column(Float)  # Days of supply

    # Reward
    reward: Mapped[Optional[float]] = mapped_column(Float)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state
    next_state_inventory: Mapped[Optional[float]] = mapped_column(Float)
    next_state_days_of_supply: Mapped[Optional[float]] = mapped_column(Float)


# =============================================================================
# Order Tracking Training Data
# =============================================================================

class OrderTrackingDecisionLog(Base):
    """
    Expert decision log for order tracking exception handling.

    Records how planners respond to detected exceptions.
    """
    __tablename__ = "trm_order_tracking_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(50))  # PO, TO, SO
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Exception detected
    exception_type: Mapped[str] = mapped_column(String(50))  # late, short, damaged, quality, cancelled
    exception_severity: Mapped[str] = mapped_column(String(20))  # low, medium, high, critical
    days_from_expected: Mapped[Optional[int]] = mapped_column(Integer)  # Negative = early
    qty_variance: Mapped[Optional[float]] = mapped_column(Float)  # Actual - expected

    # State at decision time
    state_order_status: Mapped[str] = mapped_column(String(50))
    state_order_qty: Mapped[float] = mapped_column(Float)
    state_expected_date: Mapped[date] = mapped_column(Date)
    state_inventory_position: Mapped[float] = mapped_column(Float)
    state_other_pending_orders: Mapped[int] = mapped_column(Integer)
    state_customer_impact: Mapped[str] = mapped_column(String(50))  # none, low, medium, high
    state_features: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Decision made
    action_type: Mapped[str] = mapped_column(String(50))  # expedite, reorder, accept, escalate, cancel
    action_new_expected_date: Mapped[Optional[date]] = mapped_column(Date)
    action_reorder_qty: Mapped[Optional[float]] = mapped_column(Float)
    action_escalated_to: Mapped[Optional[str]] = mapped_column(String(100))
    action_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Decision metadata
    source: Mapped[DecisionSource] = mapped_column(
        SAEnum(DecisionSource, name="decision_source_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=DecisionSource.EXPERT_HUMAN
    )
    decision_maker_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    ai_recommendation: Mapped[Optional[Dict]] = mapped_column(JSON)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderTrackingOutcome(Base):
    """Outcome tracking for order tracking decisions."""
    __tablename__ = "trm_order_tracking_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trm_order_tracking_decision_log.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    status: Mapped[OutcomeStatus] = mapped_column(
        SAEnum(OutcomeStatus, name="outcome_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=OutcomeStatus.PENDING
    )
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Resolution result
    exception_resolved: Mapped[Optional[bool]] = mapped_column(Boolean)
    resolution_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    final_order_status: Mapped[Optional[str]] = mapped_column(String(50))

    # Impact
    customer_notified: Mapped[Optional[bool]] = mapped_column(Boolean)
    customer_satisfied: Mapped[Optional[bool]] = mapped_column(Boolean)
    additional_cost: Mapped[Optional[float]] = mapped_column(Float)
    service_recovery_successful: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Reward
    reward: Mapped[Optional[float]] = mapped_column(Float)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state
    next_state_order_status: Mapped[Optional[str]] = mapped_column(String(50))


# =============================================================================
# Safety Stock Decision Log
# =============================================================================

class SafetyStockDecisionLog(Base):
    """Decision log for safety stock TRM adjustments."""
    __tablename__ = "trm_safety_stock_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)

    # Product-Location
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    location_id: Mapped[Optional[str]] = mapped_column(String(100))
    decision_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # State: baseline from engine
    state_baseline_ss: Mapped[float] = mapped_column(Float, nullable=False)
    state_policy_type: Mapped[Optional[str]] = mapped_column(String(20))
    state_current_dos: Mapped[Optional[float]] = mapped_column(Float)
    state_current_on_hand: Mapped[Optional[float]] = mapped_column(Float)

    # State: demand context
    state_demand_cv: Mapped[Optional[float]] = mapped_column(Float)
    state_avg_daily_demand: Mapped[Optional[float]] = mapped_column(Float)
    state_demand_trend: Mapped[Optional[float]] = mapped_column(Float)
    state_seasonal_index: Mapped[Optional[float]] = mapped_column(Float)

    # State: performance history
    state_recent_stockout_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    state_recent_excess_days: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    state_forecast_bias: Mapped[Optional[float]] = mapped_column(Float)

    # State: lead time
    state_lead_time_days: Mapped[Optional[float]] = mapped_column(Float)
    state_lead_time_cv: Mapped[Optional[float]] = mapped_column(Float)

    # Full state features
    state_features: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Action: adjustment
    action_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    action_adjusted_ss: Mapped[float] = mapped_column(Float, nullable=False)
    action_reason: Mapped[Optional[str]] = mapped_column(String(50))

    # Metadata
    source: Mapped[Optional[DecisionSource]] = mapped_column(
        SAEnum(DecisionSource, name="decision_source_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=DecisionSource.SYNTHETIC
    )
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)


class SafetyStockOutcome(Base):
    """Outcome tracking for safety stock adjustment decisions."""
    __tablename__ = "trm_safety_stock_outcome"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trm_safety_stock_decision_log.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    status: Mapped[OutcomeStatus] = mapped_column(
        SAEnum(OutcomeStatus, name="outcome_status_enum", values_callable=lambda obj: [e.value for e in obj]),
        default=OutcomeStatus.PENDING
    )
    measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Actual results after review period
    actual_stockout_occurred: Mapped[Optional[bool]] = mapped_column(Boolean)
    actual_stockout_days: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    actual_dos_at_end: Mapped[Optional[float]] = mapped_column(Float)
    actual_excess_inventory_cost: Mapped[Optional[float]] = mapped_column(Float)
    actual_service_level: Mapped[Optional[float]] = mapped_column(Float)

    # Reward
    reward: Mapped[Optional[float]] = mapped_column(Float)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state
    next_state_dos: Mapped[Optional[float]] = mapped_column(Float)
    next_state_demand_cv: Mapped[Optional[float]] = mapped_column(Float)


# =============================================================================
# Unified Replay Buffer
# =============================================================================

class TRMReplayBuffer(Base):
    """
    Unified replay buffer for all TRM types.

    Stores (state, action, reward, next_state, done) tuples
    for experience replay during RL training.
    """
    __tablename__ = "trm_replay_buffer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)

    # Site (for per-site training filtering)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    # TRM type
    trm_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Link to original decision
    decision_log_id: Mapped[Optional[int]] = mapped_column(Integer)
    decision_log_table: Mapped[Optional[str]] = mapped_column(String(100))

    # State (vectorized features)
    state_vector: Mapped[List[float]] = mapped_column(JSON, nullable=False)
    state_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    # Action (can be discrete index or continuous vector)
    action_discrete: Mapped[Optional[int]] = mapped_column(Integer)
    action_continuous: Mapped[Optional[List[float]]] = mapped_column(JSON)
    action_dim: Mapped[int] = mapped_column(Integer, default=1)

    # Reward
    reward: Mapped[float] = mapped_column(Float, nullable=False)
    reward_components: Mapped[Dict] = mapped_column(JSON, default=dict)

    # Next state
    next_state_vector: Mapped[Optional[List[float]]] = mapped_column(JSON)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quality metrics
    is_expert: Mapped[bool] = mapped_column(Boolean, default=False)  # From human expert
    override_effectiveness: Mapped[Optional[str]] = mapped_column(String(20))  # BENEFICIAL/NEUTRAL/DETRIMENTAL
    priority: Mapped[float] = mapped_column(Float, default=1.0)  # For prioritized replay
    td_error: Mapped[Optional[float]] = mapped_column(Float)  # For prioritized replay

    # Timestamps
    transition_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Sampling metadata
    times_sampled: Mapped[int] = mapped_column(Integer, default=0)
    last_sampled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        Index('idx_replay_buffer_trm_type_date', 'trm_type', 'transition_date'),
        Index('idx_replay_buffer_priority', 'trm_type', 'priority'),
        Index('idx_replay_buffer_site_trm', 'site_id', 'trm_type'),
    )

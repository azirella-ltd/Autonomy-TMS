"""
Powell Framework — TRM Execution Decision Records

ORM models for the 10 powell_*_decisions tables. These tables store the
execution-layer audit trail for narrow TRM decisions:
  - ATP, rebalancing, PO creation, order tracking (original 4)
  - MO execution, TO execution, quality disposition, maintenance scheduling,
    subcontracting routing, forecast adjustment (6 new TRMs)

Separate from the richer trm_*_decision_log tables in trm_training_data.py
which are designed for RL training (state/action/reward/next_state tuples).
These are simpler execution records for the demo, dashboard, and audit trail.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, ForeignKey, Index,
)
from sqlalchemy.sql import func

from .base import Base


class HiveSignalMixin:
    """Mixin adding hive signal context columns to decision tables.

    All columns are nullable so existing records are unaffected.

    AIIO Status (Mar 2026)
    ----------------------
    The agent always acts and informs a prioritised list; the human inspects
    selectively and only overrides if warranted. No approval workflow.

    - ACTIONED: Agent executed the decision (default — born this way)
    - INFORMED: Decision surfaced to a human via the Decision Stream
    - INSPECTED: Human reviewed the reasoning, agent action stands
    - OVERRIDDEN: Human rejected and provided an alternative with structured reasoning

    Decision Level
    --------------
    Which Powell layer produced this decision:
    - execution: TRM narrow decisions (<10ms, per-order/per-product)
    - tactical: Site tGNN or Network tGNN (daily, multi-site)
    - strategic: S&OP GraphSAGE (weekly/monthly, network-wide policy)

    Economic Impact Columns (Mar 2026)
    -----------------------------------
    Three-dimensional decision routing grounded in Kahneman & Tversky's
    Prospect Theory (1979): humans weight losses ~2x heavier than equivalent
    gains, so loss-prevention decisions (high urgency) must be prioritized
    above gain-capture opportunities (high benefit) even at equal dollar value.

    - cost_of_inaction: $/period cost of doing nothing (loss exposure)
    - time_pressure: 0-1 scalar, how fast the window closes
    - expected_benefit: $ net gain from the recommended action (gain capture)

    Urgency = cost_of_inaction × time_pressure (normalized 0-1 for routing)
    Likelihood = TRM confidence (existing ``confidence`` column)
    Benefit = expected_benefit (absolute $, display + routing)

    Routing formula:
      routing_score = urgency × (1 - likelihood) + benefit_norm × likelihood
      surface_to_human = routing_score > per_trm_threshold

    Queue sort: urgency DESC (Kahneman loss aversion), then benefit DESC,
    then likelihood ASC (where human judgment adds most value).
    """
    # ── AIIO status ───────────────────────────────────────────────────────
    # Agent always acts. Human reacts (or doesn't).
    # Default ACTIONED — the agent executed. No approval required.
    status = Column(
        String(20), nullable=False, default="ACTIONED", server_default="ACTIONED",
        index=True, comment="AIIO: ACTIONED|INFORMED|INSPECTED|OVERRIDDEN",
    )
    decision_level = Column(
        String(20), nullable=False, default="execution", server_default="execution",
        index=True, comment="Powell layer: execution|tactical|strategic",
    )

    signal_context = Column(JSON, nullable=True)        # Snapshot of signals read before decision
    urgency_at_time = Column(Float, nullable=True)       # Urgency vector value for this TRM at decision time
    triggered_by = Column(String(200), nullable=True)    # Comma-separated signal types that influenced decision
    signals_emitted = Column(JSON, nullable=True)        # List of signal types emitted after decision
    cycle_phase = Column(String(50), nullable=True)      # DecisionCyclePhase name (SENSE..REFLECT)
    cycle_id = Column(String(100), nullable=True)        # UUID of the decision cycle run

    # Decision reasoning — full English explanation captured at decision time
    # Eliminates need for LLM to infer reasoning at query time
    decision_reasoning = Column(Text, nullable=True)

    # ── Economic impact columns (Kahneman-informed 3D routing) ──────────
    # cost_of_inaction: Dollar cost per period of NOT acting on this decision.
    #   Combines magnitude of potential loss with the rate of deterioration.
    #   E.g., stockout_cost × expected_shortage_qty, or downtime_cost × P(breakdown).
    cost_of_inaction = Column(Float, nullable=True, comment="$/period cost of doing nothing")

    # time_pressure: 0-1 scalar indicating how fast the decision window closes.
    #   1.0 = must act now (overdue, customer waiting); 0.0 = weeks of runway.
    #   E.g., max(0, 1 - days_remaining / decision_horizon).
    time_pressure = Column(Float, nullable=True, comment="0-1 how fast the window closes")

    # expected_benefit: Net dollar value of taking the recommended action.
    #   = value_created_by_action - cost_of_action.
    #   E.g., (stockout_cost_avoided - procurement_cost) for a PO decision.
    expected_benefit = Column(Float, nullable=True, comment="$ net gain from recommended action")

    # Override tracking — populated by act_on_decision() when user modifies or cancels
    override_action = Column(String(20), nullable=True)       # 'modify' or 'cancel'
    override_values = Column(JSON, nullable=True)              # Dict of user-modified values (for modify)
    original_values = Column(JSON, nullable=True)              # Snapshot of TRM recommendation before modify
    override_reason_code = Column(String(50), nullable=True)   # MARKET_INTELLIGENCE, CAPACITY_CONSTRAINT, etc.
    override_reason_text = Column(Text, nullable=True)         # Free-text explanation
    override_user_id = Column(Integer, nullable=True)          # User who overrode
    override_at = Column(DateTime, nullable=True)              # When the override happened

    def _signal_dict(self) -> dict:
        """Return signal fields for to_dict()."""
        return {
            "status": self.status,
            "decision_level": self.decision_level,
            "signal_context": self.signal_context,
            "urgency_at_time": self.urgency_at_time,
            "triggered_by": self.triggered_by,
            "signals_emitted": self.signals_emitted,
            "cycle_phase": self.cycle_phase,
            "cycle_id": self.cycle_id,
            "decision_reasoning": self.decision_reasoning,
            "cost_of_inaction": self.cost_of_inaction,
            "time_pressure": self.time_pressure,
            "expected_benefit": self.expected_benefit,
            "override_action": self.override_action,
            "override_values": self.override_values,
            "override_reason_code": self.override_reason_code,
            "override_reason_text": self.override_reason_text,
        }


class PowellATPDecision(HiveSignalMixin, Base):
    """ATP decision history for TRM training and audit trail."""
    __tablename__ = "powell_atp_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(String(100), nullable=False)

    # Request
    product_id = Column(String(100), nullable=False)
    location_id = Column(String(100), nullable=False)
    requested_qty = Column(Float, nullable=False)
    order_priority = Column(Integer, nullable=False)

    # Decision
    can_fulfill = Column(Boolean, nullable=False)
    promised_qty = Column(Float, nullable=False)
    consumption_breakdown = Column(JSON, nullable=True)  # {priority: qty}

    # Context (state features for TRM)
    state_features = Column(JSON, nullable=True)
    decision_method = Column(String(50), nullable=True)  # 'trm', 'heuristic'
    confidence = Column(Float, nullable=True)
    reason = Column(String(100), nullable=True)  # Short reason code: full_fulfill/partial_fulfill/cannot_fulfill/stock_reserved

    # Outcome (for training)
    was_committed = Column(Boolean, nullable=True)
    actual_fulfilled_qty = Column(Float, nullable=True)
    fulfillment_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_atp_config_order", "config_id", "order_id"),
        Index("idx_atp_product_loc", "product_id", "location_id"),
        Index("idx_atp_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "order_id": self.order_id,
            "product_id": self.product_id,
            "location_id": self.location_id,
            "requested_qty": self.requested_qty,
            "order_priority": self.order_priority,
            "can_fulfill": self.can_fulfill,
            "promised_qty": self.promised_qty,
            "consumption_breakdown": self.consumption_breakdown,
            "decision_method": self.decision_method,
            "confidence": self.confidence,
            "reason": self.reason,
            "was_committed": self.was_committed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellRebalanceDecision(HiveSignalMixin, Base):
    """Rebalancing decision history for TRM training and audit trail."""
    __tablename__ = "powell_rebalance_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Transfer details
    product_id = Column(String(100), nullable=False)
    from_site = Column(String(100), nullable=False)
    to_site = Column(String(100), nullable=False)
    recommended_qty = Column(Float, nullable=False)

    # Context
    reason = Column(String(50), nullable=False)
    urgency = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    # Expected impact
    source_dos_before = Column(Float, nullable=True)
    source_dos_after = Column(Float, nullable=True)
    dest_dos_before = Column(Float, nullable=True)
    dest_dos_after = Column(Float, nullable=True)
    expected_cost = Column(Float, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_qty = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)
    service_impact = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_rebalance_config", "config_id"),
        Index("idx_rebalance_product", "product_id"),
        Index("idx_rebalance_sites", "from_site", "to_site"),
        Index("idx_rebalance_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "product_id": self.product_id,
            "from_site": self.from_site,
            "to_site": self.to_site,
            "recommended_qty": self.recommended_qty,
            "reason": self.reason,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "source_dos": {"before": self.source_dos_before, "after": self.source_dos_after},
            "dest_dos": {"before": self.dest_dos_before, "after": self.dest_dos_after},
            "expected_cost": self.expected_cost,
            "was_executed": self.was_executed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellPODecision(HiveSignalMixin, Base):
    """PO creation decision history for TRM training and audit trail."""
    __tablename__ = "powell_po_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # PO details
    product_id = Column(String(100), nullable=False)
    location_id = Column(String(100), nullable=False)
    supplier_id = Column(String(100), nullable=False)
    recommended_qty = Column(Float, nullable=False)

    # Context
    trigger_reason = Column(String(50), nullable=False)
    urgency = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=True)

    # Inventory state at decision
    inventory_position = Column(Float, nullable=True)
    days_of_supply = Column(Float, nullable=True)
    forecast_30_day = Column(Float, nullable=True)

    # Expected outcome
    expected_receipt_date = Column(Date, nullable=True)
    expected_cost = Column(Float, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_qty = Column(Float, nullable=True)
    actual_receipt_date = Column(Date, nullable=True)
    actual_cost = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_powell_po_config", "config_id"),
        Index("idx_powell_po_product_loc", "product_id", "location_id"),
        Index("idx_powell_po_supplier", "supplier_id"),
        Index("idx_powell_po_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "product_id": self.product_id,
            "location_id": self.location_id,
            "supplier_id": self.supplier_id,
            "recommended_qty": self.recommended_qty,
            "trigger_reason": self.trigger_reason,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "inventory_position": self.inventory_position,
            "days_of_supply": self.days_of_supply,
            "expected_receipt_date": self.expected_receipt_date.isoformat() if self.expected_receipt_date else None,
            "expected_cost": self.expected_cost,
            "was_executed": self.was_executed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellOrderException(HiveSignalMixin, Base):
    """Order tracking exception history for TRM training and audit trail."""
    __tablename__ = "powell_order_exceptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(String(100), nullable=False)

    # Order context
    order_type = Column(String(50), nullable=False)
    order_status = Column(String(50), nullable=False)

    # Exception details
    exception_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    recommended_action = Column(String(50), nullable=False)

    # Context
    description = Column(Text, nullable=True)
    impact_assessment = Column(Text, nullable=True)
    estimated_impact_cost = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    reason = Column(String(100), nullable=True)  # Short reason code: late_shipment/qty_mismatch/quality_hold/carrier_delay

    # State features for TRM
    state_features = Column(JSON, nullable=True)

    # Outcome
    action_taken = Column(String(50), nullable=True)
    resolution_time_hours = Column(Float, nullable=True)
    actual_impact_cost = Column(Float, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_exception_config_order", "config_id", "order_id"),
        Index("idx_exception_type", "exception_type"),
        Index("idx_exception_severity", "severity"),
        Index("idx_exception_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "order_id": self.order_id,
            "order_type": self.order_type,
            "order_status": self.order_status,
            "exception_type": self.exception_type,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
            "description": self.description,
            "estimated_impact_cost": self.estimated_impact_cost,
            "confidence": self.confidence,
            "reason": self.reason,
            "action_taken": self.action_taken,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellMODecision(HiveSignalMixin, Base):
    """Manufacturing Order execution decision history for TRM training and audit trail."""
    __tablename__ = "powell_mo_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # MO details
    production_order_id = Column(String(100), nullable=False)
    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    planned_qty = Column(Float, nullable=False)

    # Decision
    decision_type = Column(String(50), nullable=False)  # release/sequence/split/expedite/defer
    sequence_position = Column(Integer, nullable=True)
    priority_override = Column(Integer, nullable=True)

    # Resource context
    resource_id = Column(String(100), nullable=True)
    setup_time_hours = Column(Float, nullable=True)
    run_time_hours = Column(Float, nullable=True)

    # Context
    confidence = Column(Float, nullable=True)
    reason = Column(String(100), nullable=True)  # Short reason code: schedule_adherence/capacity_available/demand_pull/expedite_request
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_completion_date = Column(DateTime, nullable=True)
    actual_qty = Column(Float, nullable=True)
    actual_yield_pct = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_mo_config", "config_id"),
        Index("idx_mo_product_site", "product_id", "site_id"),
        Index("idx_mo_production_order", "production_order_id"),
        Index("idx_mo_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "production_order_id": self.production_order_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "planned_qty": self.planned_qty,
            "decision_type": self.decision_type,
            "sequence_position": self.sequence_position,
            "priority_override": self.priority_override,
            "resource_id": self.resource_id,
            "setup_time_hours": self.setup_time_hours,
            "run_time_hours": self.run_time_hours,
            "confidence": self.confidence,
            "reason": self.reason,
            "was_executed": self.was_executed,
            "actual_completion_date": self.actual_completion_date.isoformat() if self.actual_completion_date else None,
            "actual_qty": self.actual_qty,
            "actual_yield_pct": self.actual_yield_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellTODecision(HiveSignalMixin, Base):
    """Transfer Order execution decision history for TRM training and audit trail."""
    __tablename__ = "powell_to_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # TO details
    transfer_order_id = Column(String(100), nullable=False)
    product_id = Column(String(100), nullable=False)
    source_site_id = Column(String(100), nullable=False)
    dest_site_id = Column(String(100), nullable=False)
    planned_qty = Column(Float, nullable=False)

    # Decision
    decision_type = Column(String(50), nullable=False)  # release/expedite/reroute/consolidate/defer
    transportation_mode = Column(String(50), nullable=True)
    estimated_transit_days = Column(Float, nullable=True)
    priority = Column(Integer, nullable=True)
    trigger_reason = Column(String(50), nullable=True)  # mrp_planned/rebalancing/stockout_prevention/demand_shift

    # Context
    confidence = Column(Float, nullable=True)
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_ship_date = Column(Date, nullable=True)
    actual_receipt_date = Column(Date, nullable=True)
    actual_qty = Column(Float, nullable=True)
    actual_transit_days = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_powell_to_config", "config_id"),
        Index("idx_powell_to_product", "product_id"),
        Index("idx_powell_to_source_dest", "source_site_id", "dest_site_id"),
        Index("idx_powell_to_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "transfer_order_id": self.transfer_order_id,
            "product_id": self.product_id,
            "source_site_id": self.source_site_id,
            "dest_site_id": self.dest_site_id,
            "planned_qty": self.planned_qty,
            "decision_type": self.decision_type,
            "transportation_mode": self.transportation_mode,
            "estimated_transit_days": self.estimated_transit_days,
            "priority": self.priority,
            "trigger_reason": self.trigger_reason,
            "confidence": self.confidence,
            "was_executed": self.was_executed,
            "actual_ship_date": self.actual_ship_date.isoformat() if self.actual_ship_date else None,
            "actual_receipt_date": self.actual_receipt_date.isoformat() if self.actual_receipt_date else None,
            "actual_qty": self.actual_qty,
            "actual_transit_days": self.actual_transit_days,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellQualityDecision(HiveSignalMixin, Base):
    """Quality disposition decision history for TRM training and audit trail."""
    __tablename__ = "powell_quality_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Quality order details
    quality_order_id = Column(String(100), nullable=False)
    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    lot_number = Column(String(100), nullable=True)

    # Inspection context
    inspection_type = Column(String(50), nullable=True)
    inspection_qty = Column(Float, nullable=True)
    defect_rate = Column(Float, nullable=True)
    defect_category = Column(String(100), nullable=True)
    severity_level = Column(String(20), nullable=True)

    # Decision
    disposition = Column(String(50), nullable=False)  # accept/reject/rework/scrap/use_as_is/return_to_vendor
    disposition_reason = Column(Text, nullable=True)
    rework_cost_estimate = Column(Float, nullable=True)
    scrap_cost_estimate = Column(Float, nullable=True)
    service_risk_if_accepted = Column(Float, nullable=True)

    # Context
    confidence = Column(Float, nullable=True)
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_disposition = Column(String(50), nullable=True)
    actual_rework_cost = Column(Float, nullable=True)
    actual_scrap_cost = Column(Float, nullable=True)
    customer_complaints_after = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_quality_config", "config_id"),
        Index("idx_quality_product_site", "product_id", "site_id"),
        Index("idx_quality_order", "quality_order_id"),
        Index("idx_quality_lot", "lot_number"),
        Index("idx_quality_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "quality_order_id": self.quality_order_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "lot_number": self.lot_number,
            "inspection_type": self.inspection_type,
            "inspection_qty": self.inspection_qty,
            "defect_rate": self.defect_rate,
            "defect_category": self.defect_category,
            "severity_level": self.severity_level,
            "disposition": self.disposition,
            "disposition_reason": self.disposition_reason,
            "rework_cost_estimate": self.rework_cost_estimate,
            "scrap_cost_estimate": self.scrap_cost_estimate,
            "service_risk_if_accepted": self.service_risk_if_accepted,
            "confidence": self.confidence,
            "was_executed": self.was_executed,
            "actual_disposition": self.actual_disposition,
            "actual_rework_cost": self.actual_rework_cost,
            "actual_scrap_cost": self.actual_scrap_cost,
            "customer_complaints_after": self.customer_complaints_after,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellMaintenanceDecision(HiveSignalMixin, Base):
    """Maintenance scheduling decision history for TRM training and audit trail."""
    __tablename__ = "powell_maintenance_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Maintenance order details
    maintenance_order_id = Column(String(100), nullable=False)
    asset_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    maintenance_type = Column(String(50), nullable=False)

    # Decision
    decision_type = Column(String(50), nullable=False)  # schedule/defer/expedite/combine/outsource
    scheduled_date = Column(Date, nullable=True)
    deferred_to_date = Column(Date, nullable=True)
    estimated_downtime_hours = Column(Float, nullable=True)
    production_impact_units = Column(Float, nullable=True)
    spare_parts_available = Column(Boolean, nullable=True)
    priority = Column(Integer, nullable=True)
    risk_score_if_deferred = Column(Float, nullable=True)

    # Context
    confidence = Column(Float, nullable=True)
    reason = Column(String(100), nullable=True)  # Short reason code: preventive_due/condition_based/breakdown_risk/production_window
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_start_date = Column(DateTime, nullable=True)
    actual_completion_date = Column(DateTime, nullable=True)
    actual_downtime_hours = Column(Float, nullable=True)
    breakdown_occurred = Column(Boolean, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_maintenance_config", "config_id"),
        Index("idx_maintenance_asset", "asset_id"),
        Index("idx_maintenance_site", "site_id"),
        Index("idx_maintenance_type", "maintenance_type"),
        Index("idx_maintenance_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "maintenance_order_id": self.maintenance_order_id,
            "asset_id": self.asset_id,
            "site_id": self.site_id,
            "maintenance_type": self.maintenance_type,
            "decision_type": self.decision_type,
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "deferred_to_date": self.deferred_to_date.isoformat() if self.deferred_to_date else None,
            "estimated_downtime_hours": self.estimated_downtime_hours,
            "production_impact_units": self.production_impact_units,
            "spare_parts_available": self.spare_parts_available,
            "priority": self.priority,
            "risk_score_if_deferred": self.risk_score_if_deferred,
            "confidence": self.confidence,
            "reason": self.reason,
            "was_executed": self.was_executed,
            "actual_start_date": self.actual_start_date.isoformat() if self.actual_start_date else None,
            "actual_completion_date": self.actual_completion_date.isoformat() if self.actual_completion_date else None,
            "actual_downtime_hours": self.actual_downtime_hours,
            "breakdown_occurred": self.breakdown_occurred,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellSubcontractingDecision(HiveSignalMixin, Base):
    """Subcontracting routing decision history for TRM training and audit trail."""
    __tablename__ = "powell_subcontracting_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Subcontracting details
    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    subcontractor_id = Column(String(100), nullable=True)
    required_qty = Column(Float, nullable=True)
    planned_qty = Column(Float, nullable=True)

    # Decision
    decision_type = Column(String(50), nullable=True)  # route_external/keep_internal/split/change_vendor
    routing_decision = Column(String(50), nullable=True)  # synonym for decision_type (legacy)
    reason = Column(String(50), nullable=True)  # capacity_constraint/cost_optimization/lead_time/quality/specialization

    # Context
    internal_capacity_pct = Column(Float, nullable=True)
    subcontractor_lead_time_days = Column(Float, nullable=True)
    subcontractor_cost_per_unit = Column(Float, nullable=True)
    internal_cost_per_unit = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    on_time_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_executed = Column(Boolean, nullable=True)
    actual_qty = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)
    actual_lead_time_days = Column(Float, nullable=True)
    quality_passed = Column(Boolean, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_subcontracting_config", "config_id"),
        Index("idx_subcontracting_product_site", "product_id", "site_id"),
        Index("idx_subcontracting_vendor", "subcontractor_id"),
        Index("idx_subcontracting_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "subcontractor_id": self.subcontractor_id,
            "planned_qty": self.planned_qty,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "internal_capacity_pct": self.internal_capacity_pct,
            "subcontractor_lead_time_days": self.subcontractor_lead_time_days,
            "subcontractor_cost_per_unit": self.subcontractor_cost_per_unit,
            "internal_cost_per_unit": self.internal_cost_per_unit,
            "quality_score": self.quality_score,
            "on_time_score": self.on_time_score,
            "confidence": self.confidence,
            "was_executed": self.was_executed,
            "actual_qty": self.actual_qty,
            "actual_cost": self.actual_cost,
            "actual_lead_time_days": self.actual_lead_time_days,
            "quality_passed": self.quality_passed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellForecastAdjustmentDecision(HiveSignalMixin, Base):
    """Forecast adjustment decision history for TRM training and audit trail."""
    __tablename__ = "powell_forecast_adjustment_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Signal details
    product_id = Column(String(100), nullable=False)
    site_id = Column(String(100), nullable=False)
    signal_source = Column(String(50), nullable=False)  # email/voice/market_intelligence/news/customer_feedback/sales_input
    signal_type = Column(String(50), nullable=False)  # demand_increase/demand_decrease/new_product/discontinuation/seasonal/promotion/disruption
    signal_text = Column(Text, nullable=True)
    signal_confidence = Column(Float, nullable=True)

    # Current state
    current_forecast_value = Column(Float, nullable=True)

    # Decision
    adjustment_direction = Column(String(20), nullable=False)  # up/down/no_change
    adjustment_magnitude = Column(Float, nullable=True)
    adjustment_pct = Column(Float, nullable=True)
    adjusted_forecast_value = Column(Float, nullable=True)
    time_horizon_periods = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)

    # Context
    confidence = Column(Float, nullable=True)
    state_features = Column(JSON, nullable=True)

    # Outcome
    was_applied = Column(Boolean, nullable=True)
    actual_demand = Column(Float, nullable=True)
    forecast_error_before = Column(Float, nullable=True)
    forecast_error_after = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_forecast_adj_config", "config_id"),
        Index("idx_forecast_adj_product_site", "product_id", "site_id"),
        Index("idx_forecast_adj_signal_source", "signal_source"),
        Index("idx_forecast_adj_signal_type", "signal_type"),
        Index("idx_forecast_adj_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "product_id": self.product_id,
            "site_id": self.site_id,
            "signal_source": self.signal_source,
            "signal_type": self.signal_type,
            "signal_text": self.signal_text,
            "signal_confidence": self.signal_confidence,
            "current_forecast_value": self.current_forecast_value,
            "adjustment_direction": self.adjustment_direction,
            "adjustment_magnitude": self.adjustment_magnitude,
            "adjustment_pct": self.adjustment_pct,
            "adjusted_forecast_value": self.adjusted_forecast_value,
            "time_horizon_periods": self.time_horizon_periods,
            "reason": self.reason,
            "confidence": self.confidence,
            "was_applied": self.was_applied,
            "actual_demand": self.actual_demand,
            "forecast_error_before": self.forecast_error_before,
            "forecast_error_after": self.forecast_error_after,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


class PowellBufferDecision(HiveSignalMixin, Base):
    """Inventory buffer adjustment decision history for TRM training and audit trail.

    NOTE: Renamed from PowellSSDecision (Feb 2026). Table renamed from
    powell_safety_stock_decisions to powell_buffer_decisions to reflect
    that buffers are uncertainty absorbers, not hard MRP demand targets.
    """
    __tablename__ = "powell_buffer_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Product-location
    product_id = Column(String(100), nullable=False)
    location_id = Column(String(100), nullable=False)

    # Decision
    baseline_ss = Column(Float, nullable=False)
    multiplier = Column(Float, nullable=False)
    adjusted_ss = Column(Float, nullable=False)
    reason = Column(String(50), nullable=False)  # SSAdjustmentReason value

    # Context
    confidence = Column(Float, nullable=True)
    demand_cv = Column(Float, nullable=True)
    current_dos = Column(Float, nullable=True)
    seasonal_index = Column(Float, nullable=True)
    recent_stockout_count = Column(Integer, nullable=True)
    state_features = Column(JSON, nullable=True)

    # Outcome (filled by outcome collector)
    was_applied = Column(Boolean, nullable=True)
    actual_stockout_occurred = Column(Boolean, nullable=True)
    actual_dos_after = Column(Float, nullable=True)
    excess_holding_cost = Column(Float, nullable=True)
    actual_service_level = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_buffer_config", "config_id"),
        Index("idx_buffer_product_loc", "product_id", "location_id"),
        Index("idx_buffer_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "product_id": self.product_id,
            "location_id": self.location_id,
            "baseline_ss": self.baseline_ss,
            "multiplier": self.multiplier,
            "adjusted_ss": self.adjusted_ss,
            "reason": self.reason,
            "confidence": self.confidence,
            "demand_cv": self.demand_cv,
            "current_dos": self.current_dos,
            "seasonal_index": self.seasonal_index,
            "recent_stockout_count": self.recent_stockout_count,
            "was_applied": self.was_applied,
            "actual_stockout_occurred": self.actual_stockout_occurred,
            "actual_dos_after": self.actual_dos_after,
            "excess_holding_cost": self.excess_holding_cost,
            "actual_service_level": self.actual_service_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            **self._signal_dict(),
        }


# Backward-compatible alias
PowellSSDecision = PowellBufferDecision

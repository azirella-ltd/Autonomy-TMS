"""
Powell Framework — TRM Execution Decision Records

ORM models for the 4 powell_*_decisions tables created by migration
20260202_powell_allocation_tables.py. These tables store the execution-layer
audit trail for narrow TRM decisions (ATP, rebalancing, PO creation,
order tracking).

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


class PowellATPDecision(Base):
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
            "was_committed": self.was_committed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PowellRebalanceDecision(Base):
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
        }


class PowellPODecision(Base):
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
        }


class PowellOrderException(Base):
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
            "action_taken": self.action_taken,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

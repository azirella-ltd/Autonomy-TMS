"""
Round Metric Database Model

Stores per-round metrics for simulation execution tracking.
Replaces ParticipantRound for execution-based simulations.

Terminology (Feb 2026):
# Terminology: scenario_id (was game_id)
- player_id -> scenario_user_id
"""

from sqlalchemy import (
    Column,
    Integer,
    Double,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    Index,
    text,
)
from datetime import datetime
from .base import Base


class RoundMetric(Base):
    """
    Round-level metrics for simulation execution.

    Tracks inventory, backlog, costs, and KPIs for each site in each round.
    Used by the SimulationExecutionEngine to calculate performance metrics.
    """
    __tablename__ = "round_metric"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Scenario and round identification
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    site_id = Column(Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id", ondelete="SET NULL"), nullable=True)

    # Inventory metrics
    inventory = Column(Double, server_default=text("0.0"), nullable=False)
    backlog = Column(Double, server_default=text("0.0"), nullable=False)
    pipeline_qty = Column(Double, server_default=text("0.0"), nullable=False)  # On order to upstream
    in_transit_qty = Column(Double, server_default=text("0.0"), nullable=False)  # Shipments arriving

    # Cost metrics (classic simulation)
    holding_cost = Column(Double, server_default=text("0.0"), nullable=False)  # inventory * holding_cost_per_unit
    backlog_cost = Column(Double, server_default=text("0.0"), nullable=False)  # backlog * backlog_cost_per_unit
    total_cost = Column(Double, server_default=text("0.0"), nullable=False)  # holding_cost + backlog_cost
    cumulative_cost = Column(Double, server_default=text("0.0"), nullable=False)  # Sum of all prior rounds

    # KPI metrics
    fill_rate = Column(Double, nullable=True)  # orders_fulfilled / orders_received
    service_level = Column(Double, nullable=True)  # units_fulfilled / units_requested
    orders_received = Column(Integer, server_default=text("0"), nullable=False)
    orders_fulfilled = Column(Integer, server_default=text("0"), nullable=False)

    # Order flow metrics
    incoming_order_qty = Column(Double, server_default=text("0.0"), nullable=False)  # Demand from downstream
    outgoing_order_qty = Column(Double, server_default=text("0.0"), nullable=False)  # Order placed to upstream
    shipment_qty = Column(Double, server_default=text("0.0"), nullable=False)  # Shipped to downstream

    # Audit
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('scenario_id', 'round_number', 'site_id', name='uq_round_metric_scenario_round_site'),
        Index('idx_round_metric_scenario', 'scenario_id'),
        Index('idx_round_metric_round', 'scenario_id', 'round_number'),
        Index('idx_round_metric_site', 'site_id'),
        Index('idx_round_metric_scenario_user', 'scenario_user_id'),
    )

    def __repr__(self):
        return (
            f"<RoundMetric("
            f"scenario_id={self.scenario_id}, "
            f"round={self.round_number}, "
            f"site_id={self.site_id}, "
            f"inventory={self.inventory}, "
            f"backlog={self.backlog}, "
            f"cost={self.total_cost}"
            f")>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'scenario_id': self.scenario_id,
            'round_number': self.round_number,
            'site_id': self.site_id,
            'scenario_user_id': self.scenario_user_id,
            'inventory': self.inventory,
            'backlog': self.backlog,
            'pipeline_qty': self.pipeline_qty,
            'in_transit_qty': self.in_transit_qty,
            'holding_cost': self.holding_cost,
            'backlog_cost': self.backlog_cost,
            'total_cost': self.total_cost,
            'cumulative_cost': self.cumulative_cost,
            'fill_rate': self.fill_rate,
            'service_level': self.service_level,
            'orders_received': self.orders_received,
            'orders_fulfilled': self.orders_fulfilled,
            'incoming_order_qty': self.incoming_order_qty,
            'outgoing_order_qty': self.outgoing_order_qty,
            'shipment_qty': self.shipment_qty,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

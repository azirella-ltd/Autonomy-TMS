"""
Period Metric Database Model

Stores per-period metrics for simulation execution tracking.
Replaces ParticipantPeriod for execution-based simulations.
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


class PeriodMetric(Base):
    """
    Period-level metrics for simulation execution.

    Tracks inventory, backlog, costs, and KPIs for each site in each period.
    Used by the SimulationExecutionEngine to calculate performance metrics.
    """
    __tablename__ = "period_metric"

    id = Column(Integer, primary_key=True, autoincrement=True)

    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    period_number = Column(Integer, nullable=False)
    site_id = Column(Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id", ondelete="SET NULL"), nullable=True)

    inventory = Column(Double, server_default=text("0.0"), nullable=False)
    backlog = Column(Double, server_default=text("0.0"), nullable=False)
    pipeline_qty = Column(Double, server_default=text("0.0"), nullable=False)
    in_transit_qty = Column(Double, server_default=text("0.0"), nullable=False)

    holding_cost = Column(Double, server_default=text("0.0"), nullable=False)
    backlog_cost = Column(Double, server_default=text("0.0"), nullable=False)
    total_cost = Column(Double, server_default=text("0.0"), nullable=False)
    cumulative_cost = Column(Double, server_default=text("0.0"), nullable=False)

    fill_rate = Column(Double, nullable=True)
    service_level = Column(Double, nullable=True)
    orders_received = Column(Integer, server_default=text("0"), nullable=False)
    orders_fulfilled = Column(Integer, server_default=text("0"), nullable=False)

    incoming_order_qty = Column(Double, server_default=text("0.0"), nullable=False)
    outgoing_order_qty = Column(Double, server_default=text("0.0"), nullable=False)
    shipment_qty = Column(Double, server_default=text("0.0"), nullable=False)

    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('scenario_id', 'period_number', 'site_id', name='uq_period_metric_scenario_period_site'),
        Index('idx_period_metric_scenario', 'scenario_id'),
        Index('idx_period_metric_period', 'scenario_id', 'period_number'),
        Index('idx_period_metric_site', 'site_id'),
        Index('idx_period_metric_scenario_user', 'scenario_user_id'),
    )

    def __repr__(self):
        return (
            f"<PeriodMetric("
            f"scenario_id={self.scenario_id}, "
            f"period={self.period_number}, "
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
            'period_number': self.period_number,
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

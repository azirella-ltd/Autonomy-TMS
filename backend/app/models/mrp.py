"""
MRP (Material Requirements Planning) Database Models

Stores MRP run results, requirements, and execution history.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Double,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    Text,
    Index,
)
from sqlalchemy.dialects.mysql import JSON
from datetime import datetime
from .base import Base


class MRPRun(Base):
    """MRP execution run"""
    __tablename__ = "mrp_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(100), unique=True, nullable=False, index=True)
    mps_plan_id = Column(Integer, ForeignKey("mps_plans.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))

    # Run parameters
    planning_horizon_weeks = Column(Integer)
    explode_bom_levels = Column(Integer)  # NULL = all levels
    generate_orders = Column(Boolean, default=True)

    # Status
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)

    # Summary statistics
    total_components = Column(Integer, default=0)
    total_requirements = Column(Integer, default=0)
    total_net_requirements = Column(Double, default=0.0)
    total_planned_orders = Column(Integer, default=0)
    total_exceptions = Column(Integer, default=0)
    total_cost_estimate = Column(Double, default=0.0)

    # Aggregated results (JSON)
    exceptions_by_severity = Column(JSON)  # {"high": 2, "medium": 1, "low": 0}
    orders_by_type = Column(JSON)  # {"po_request": 10, "to_request": 3, "mo_request": 2}

    # Audit
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Error tracking
    error_message = Column(Text)

    __table_args__ = (
        Index('idx_mrp_run_mps_plan', 'mps_plan_id'),
        Index('idx_mrp_run_status', 'status'),
        Index('idx_mrp_run_config', 'config_id'),
        Index('idx_mrp_run_customer', 'customer_id'),
        Index('idx_mrp_run_started', 'started_at'),
    )


class MRPRequirement(Base):
    """Individual component requirement from MRP explosion"""
    __tablename__ = "mrp_requirement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mrp_run_id = Column(Integer, ForeignKey("mrp_run.id", ondelete="CASCADE"), nullable=False)

    # Component details
    component_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    parent_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # BOM hierarchy
    bom_level = Column(Integer, nullable=False)

    # Time period
    period_number = Column(Integer, nullable=False)
    period_start_date = Column(Date, nullable=False)
    period_end_date = Column(Date, nullable=False)

    # Requirements calculation
    gross_requirement = Column(Double, nullable=False, default=0.0)
    scheduled_receipts = Column(Double, default=0.0)
    projected_available = Column(Double, default=0.0)
    net_requirement = Column(Double, default=0.0)
    planned_order_receipt = Column(Double, default=0.0)
    planned_order_release = Column(Double, default=0.0)

    # Sourcing
    source_type = Column(String(20))  # buy, transfer, manufacture
    source_site_id = Column(Integer, ForeignKey("site.id"))
    lead_time_days = Column(Integer)

    # Demand source tracing (full-level pegging)
    demand_source_type = Column(String(50))   # customer_order, forecast, inter_site
    demand_source_id = Column(String(100))    # FK to originating demand record
    demand_chain_id = Column(String(64))      # Pegging chain ID for traceability

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_mrp_req_run', 'mrp_run_id'),
        Index('idx_mrp_req_component', 'component_id'),
        Index('idx_mrp_req_site', 'site_id'),
        Index('idx_mrp_req_period', 'period_number'),
    )


class MRPException(Base):
    """MRP planning exception"""
    __tablename__ = "mrp_exception"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mrp_run_id = Column(Integer, ForeignKey("mrp_run.id", ondelete="CASCADE"), nullable=False)

    # Exception details
    exception_type = Column(String(50), nullable=False)  # no_sourcing_rule, stockout, late_order, excess_inventory
    severity = Column(String(20), nullable=False)  # high, medium, low

    # Component/site
    component_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Time period
    period_number = Column(Integer, nullable=False)
    period_start_date = Column(Date, nullable=False)

    # Exception message and recommendation
    message = Column(Text, nullable=False)
    recommended_action = Column(Text)

    # Quantitative data
    quantity_shortfall = Column(Double)

    # Resolution tracking
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by_id = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_mrp_exc_run', 'mrp_run_id'),
        Index('idx_mrp_exc_type', 'exception_type'),
        Index('idx_mrp_exc_severity', 'severity'),
        Index('idx_mrp_exc_component', 'component_id'),
        Index('idx_mrp_exc_resolved', 'is_resolved'),
    )

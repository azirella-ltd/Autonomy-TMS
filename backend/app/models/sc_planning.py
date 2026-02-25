"""
Supply Chain Planning Models

Active models for planning-specific tables that extend the core SC entities.
Core SC entity models (Forecast, SupplyPlan, ProductBom, ProductionProcess,
SourcingRules, InvPolicy, InvLevel, OutboundOrderLine, InboundOrderLine,
VendorLeadTime, SupplyPlanningParameters, TradingPartner, VendorProduct)
are defined in sc_entities.py (canonical source).

This file contains: ProductionCapacity, OrderAggregationPolicy,
AggregatedOrder, SourcingSchedule, SourcingScheduleDetails.

Updated 2026-01-11: Added customer_id foreign keys for multi-tenancy support.
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
    Index,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from datetime import datetime
from typing import Optional, Dict, Any
from .base import Base


# Re-export InboundOrderLine for backward compatibility with services that import from sc_planning.
from app.models.sc_entities import InboundOrderLine  # noqa: F401


class ProductionCapacity(Base):
    """Production/transfer capacity limits per site (Phase 3 - Capacity Constraints)

    Tracks capacity constraints for sites, preventing unlimited production/transfers.
    Used to enforce realistic capacity limits in simulation execution.

    Key Fields:
    - max_capacity_per_period: Maximum units that can be produced/transferred per period
    - current_capacity_used: Currently allocated capacity (resets each period)
    - capacity_type: Type of capacity (production, transfer, storage)

    Example:
        Factory capacity = 100 units/week
        If Factory receives orders for 120 units, only 100 can be fulfilled,
        20 units overflow to next period or get rejected.
    """
    __tablename__ = "production_capacity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"))  # NULL = applies to all products

    # Capacity limits
    max_capacity_per_period = Column(Double, nullable=False)  # Max units per period (week)
    current_capacity_used = Column(Double, default=0.0)  # Currently allocated
    capacity_uom = Column(String(20), default='CASES')  # Unit of measure

    # Capacity type and metadata
    capacity_type = Column(String(20), default='production')  # production, transfer, storage
    capacity_period = Column(String(20), default='week')  # week, day, month
    utilization_target = Column(Double)  # Target utilization % (e.g., 0.85 = 85%)

    # Overflow handling
    allow_overflow = Column(Boolean, default=False)  # Allow exceeding capacity?
    overflow_cost_multiplier = Column(Double, default=1.5)  # Cost multiplier for overflow

    # Multi-tenancy and time range
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    effective_start_date = Column(Date)
    effective_end_date = Column(Date)

    # Timestamps
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    # Phase 5: Stochastic distribution fields
    capacity_dist = Column(JSON, nullable=True, comment='Stochastic distribution for capacity')

    __table_args__ = (
        Index('idx_capacity_site_product', 'site_id', 'product_id'),
        Index('idx_capacity_customer_config', 'customer_id', 'config_id'),
        Index('idx_capacity_config', 'config_id'),
        Index('idx_capacity_type', 'capacity_type'),
    )


class OrderAggregationPolicy(Base):
    """Order Aggregation and Scheduling Policies (Phase 3 - Sprint 3)

    Defines policies for aggregating multiple orders and scheduling constraints.
    Enables batching orders to same upstream site for efficiency and cost savings.

    Key Features:
    - Periodic Ordering: Order every N days instead of every period
    - Time Windows: Restrict when orders can be placed
    - Min/Max Quantities: Enforce order size constraints
    - Order Multiples: Enforce pallet/container quantities

    Example:
        Policy: Order from Factory every Monday (period=7 days)
        Min order: 50 units, Max order: 200 units, Multiple: 10 units
        Time window: 8:00 AM - 5:00 PM
    """
    __tablename__ = "order_aggregation_policy"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Policy scope
    from_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Ordering site
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Supplier site
    product_id = Column(String(100), ForeignKey("product.id"))  # NULL = all products

    # Periodic ordering
    ordering_period_days = Column(Integer, default=1)  # Order every N days (1 = daily)
    ordering_day_of_week = Column(Integer)  # 1=Monday, 7=Sunday (NULL = any day)
    ordering_day_of_month = Column(Integer)  # 1-31 (NULL = any day)

    # Time windows
    order_window_start_hour = Column(Integer)  # 0-23 (NULL = no restriction)
    order_window_end_hour = Column(Integer)  # 0-23 (NULL = no restriction)

    # Quantity constraints
    min_order_quantity = Column(Double)  # Minimum order size (NULL = no minimum)
    max_order_quantity = Column(Double)  # Maximum order size (NULL = no maximum)
    order_multiple = Column(Double, default=1.0)  # Must order in multiples of this

    # Aggregation settings
    aggregate_within_period = Column(Boolean, default=True)  # Aggregate orders in same period
    aggregation_window_days = Column(Integer, default=1)  # Days to aggregate over

    # Cost savings
    fixed_order_cost = Column(Double)  # Fixed cost per order (encourages aggregation)
    variable_cost_per_unit = Column(Double)  # Variable cost per unit

    # Policy status
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=100)  # Higher priority policies evaluated first

    # Multi-tenancy
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

    # Effective date range
    effective_start_date = Column(Date)
    effective_end_date = Column(Date)

    # Timestamps
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_agg_policy_sites', 'from_site_id', 'to_site_id'),
        Index('idx_agg_policy_product', 'product_id'),
        Index('idx_agg_policy_customer_config', 'customer_id', 'config_id'),
        Index('idx_agg_policy_active', 'is_active'),
    )


class AggregatedOrder(Base):
    """Aggregated Orders (Phase 3 - Sprint 3)

    Tracks aggregated orders that combine multiple individual order requests.
    Used to optimize ordering costs and reduce administrative overhead.

    Example:
        3 individual orders: 20, 30, 25 units
        Aggregated order: 75 units (rounded to 80 due to order_multiple=10)
        Cost savings: 2 * fixed_order_cost
    """
    __tablename__ = "aggregated_order"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Aggregation details
    policy_id = Column(Integer, ForeignKey("order_aggregation_policy.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    round_number = Column(Integer, nullable=False)

    # Sites and product
    from_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # Quantities
    total_quantity = Column(Double, nullable=False)  # Total aggregated quantity
    adjusted_quantity = Column(Double)  # After applying order_multiple
    num_orders_aggregated = Column(Integer, default=1)  # Number of orders combined

    # Individual order references (JSON array of order IDs)
    source_order_ids = Column(String(500))  # Comma-separated IDs

    # Dates
    aggregation_date = Column(Date, nullable=False)
    scheduled_order_date = Column(Date)  # When order will be placed

    # Cost tracking
    fixed_cost_saved = Column(Double, default=0.0)  # Cost saved by aggregation
    total_order_cost = Column(Double)

    # Status
    status = Column(String(20), default='pending')  # pending, placed, fulfilled

    # Multi-tenancy
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

    # Timestamps
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_agg_order_scenario_round', 'scenario_id', 'round_number'),
        Index('idx_agg_order_sites', 'from_site_id', 'to_site_id'),
        Index('idx_agg_order_status', 'status'),
        Index('idx_agg_order_scheduled', 'scheduled_order_date'),
    )


class SourcingSchedule(Base):
    """Sourcing schedule configuration for periodic ordering

    SC standard entity for defining when orders can be placed.
    Supports periodic review inventory systems where orders are only
    placed on specific days (e.g., weekly on Mondays, monthly on 1st).

    Periodic ordering reduces ordering frequency and can consolidate
    shipments for cost savings. Often paired with order_up_to_level
    inventory policies.

    Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
    """
    __tablename__ = "sourcing_schedule"

    id = Column(String(100), primary_key=True)  # sourcing_schedule_id
    description = Column(String(255))
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Destination site
    tpartner_id = Column(String(100), ForeignKey("trading_partners.id"))  # For 'buy' type schedules
    from_site_id = Column(Integer, ForeignKey("site.id"))  # For 'transfer' type schedules
    schedule_type = Column(String(50))  # 'daily', 'weekly', 'monthly', 'custom'
    is_active = Column(String(10), server_default='true')
    eff_start_date = Column(DateTime, server_default='1900-01-01 00:00:00')
    eff_end_date = Column(DateTime, server_default='9999-12-31 23:59:59')
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_sourcing_schedule_site', 'to_site_id'),
        Index('idx_sourcing_schedule_customer_config', 'customer_id', 'config_id'),
        Index('idx_sourcing_schedule_config', 'config_id'),
    )


class SourcingScheduleDetails(Base):
    """Sourcing schedule time details - defines specific ordering days

    Specifies which days/times orders can be placed for a sourcing schedule.
    Can define schedules at multiple levels of granularity:
    - Daily: Every day
    - Weekly: Specific day(s) of week (0=Sunday, 1=Monday, ..., 6=Saturday)
    - Monthly: Specific week of month + day of week
    - Custom: Specific dates

    Examples:
    - Weekly on Mondays: day_of_week=1
    - Bi-weekly on Thursdays: day_of_week=4, week_of_month=1,3
    - Monthly on 1st: schedule_date for each month's first day
    """
    __tablename__ = "sourcing_schedule_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sourcing_schedule_id = Column(String(100), ForeignKey("sourcing_schedule.id"), nullable=False)

    # Hierarchical override fields
    company_id = Column(String(100))  # Company-level schedule
    product_group_id = Column(String(100))  # Product group schedule
    product_id = Column(String(100), ForeignKey("product.id"))  # Product-specific schedule

    # Scheduling fields
    schedule_date = Column(Date)  # Specific date (for custom schedules)
    day_of_week = Column(Integer)  # 0=Sun, 1=Mon, ..., 6=Sat (for weekly schedules)
    week_of_month = Column(Integer)  # 1-5 (for monthly schedules)

    is_active = Column(String(10), server_default='true')
    eff_start_date = Column(DateTime, server_default='1900-01-01 00:00:00')
    eff_end_date = Column(DateTime, server_default='9999-12-31 23:59:59')
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_sourcing_schedule_details_schedule', 'sourcing_schedule_id'),
        Index('idx_sourcing_schedule_details_product', 'product_id'),
        Index('idx_sourcing_schedule_details_customer_config', 'customer_id', 'config_id'),
        Index('idx_sourcing_schedule_details_config', 'config_id'),
    )

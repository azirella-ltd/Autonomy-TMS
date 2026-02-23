"""
Supply Chain Planning Models

Simplified models that match the actual database schema created by migrations.
These models are specifically for the planning logic and align with the tables
created in 20260110_planning_tables.py migration.

Updated 2026-01-11: Added group_id foreign keys for multi-tenancy support.
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
from sqlalchemy.dialects.mysql import DECIMAL, JSON
from datetime import datetime
from typing import Optional, Dict, Any
from .base import Base


# NOTE: Forecast is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class Forecast(Base):
#     """Demand forecasts"""
#     __tablename__ = "forecast"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     forecast_date = Column(Date, nullable=False)
#     forecast_quantity = Column(Double)
#     forecast_p50 = Column(Double)
#     forecast_p10 = Column(Double)
#     forecast_p90 = Column(Double)
#     user_override_quantity = Column(Double)
#     is_active = Column(String(10))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     game_id = Column(Integer, ForeignKey("games.id"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#
#     # Phase 5: Stochastic distribution fields
#     demand_dist = Column(JSON, nullable=True, comment='Stochastic distribution for demand')
#     forecast_error_dist = Column(JSON, nullable=True, comment='Stochastic distribution for forecast error')
#
#     __table_args__ = (
#         Index('idx_forecast_lookup', 'product_id', 'site_id', 'forecast_date'),
#         Index('idx_forecast_group_config', 'group_id', 'config_id'),
#         Index('idx_forecast_config', 'config_id'),
#         Index('idx_forecast_game', 'game_id'),
#     )


# NOTE: SupplyPlan is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class SupplyPlan(Base):
#     """Supply plan recommendations (PO/TO/MO requests)"""
#     __tablename__ = "supply_plan"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     plan_type = Column(String(20), nullable=False)  # po_request, to_request, mo_request
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     destination_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     source_site_id = Column(Integer, ForeignKey("site.id"))
#     vendor_id = Column(String(100))
#     production_process_id = Column(String(100), ForeignKey("production_process.id"))
#     planned_order_quantity = Column(Double, nullable=False)
#     planned_order_date = Column(Date, nullable=False)
#     planned_receipt_date = Column(Date, nullable=False)
#     lead_time_days = Column(Integer)
#     unit_cost = Column(Double)
#     planning_run_id = Column(String(100))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     game_id = Column(Integer, ForeignKey("games.id"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#
#     __table_args__ = (
#         Index('idx_supply_plan_lookup', 'product_id', 'destination_site_id', 'planned_order_date'),
#         Index('idx_supply_plan_group_config', 'group_id', 'config_id'),
#         Index('idx_supply_plan_config', 'config_id'),
#         Index('idx_supply_plan_game', 'game_id'),
#     )


# NOTE: ProductBom is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class ProductBom(Base):
#     """Bill of materials"""
#     __tablename__ = "product_bom"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     component_product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     component_quantity = Column(Double, nullable=False)
#     production_process_id = Column(String(100), ForeignKey("production_process.id"))
#     alternate_group = Column(Integer, server_default='0')
#     priority = Column(Integer, server_default='1')
#     scrap_percentage = Column(Double, server_default='0.0')
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     # Phase 5: Stochastic distribution fields
#     scrap_rate_dist = Column(JSON, nullable=True, comment='Stochastic distribution for scrap rate percentage')
#
#     __table_args__ = (
#         Index('idx_bom_product', 'product_id'),
#         Index('idx_bom_component', 'component_product_id'),
#         Index('idx_bom_group_config', 'group_id', 'config_id'),
#         Index('idx_bom_config', 'config_id'),
#     )


# NOTE: ProductionProcess is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class ProductionProcess(Base):
#     """Manufacturing process definitions with SC advanced features"""
#     __tablename__ = "production_process"
#
#     id = Column(String(100), primary_key=True)
#     description = Column(String(500))
#     site_id = Column(Integer, ForeignKey("site.id"))
#     manufacturing_leadtime = Column(Integer)
#     cycle_time = Column(Integer)
#     yield_percentage = Column(Double, server_default='100.0')
#     capacity_units = Column(Double)
#     capacity_period = Column(String(20))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     # SC Advanced Features
#     frozen_horizon_days = Column(Integer)  # Lock production orders within this horizon
#     setup_time = Column(Integer)  # Setup time in minutes/hours before production
#     changeover_time = Column(Integer)  # Time to switch between products
#     changeover_cost = Column(DECIMAL(10, 2))  # Cost per changeover
#     min_batch_size = Column(DECIMAL(10, 2))  # Minimum production quantity
#     max_batch_size = Column(DECIMAL(10, 2))  # Maximum production quantity
#
#     # Phase 5: Stochastic distribution fields
#     mfg_lead_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for manufacturing lead time')
#     cycle_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for cycle time')
#     yield_dist = Column(JSON, nullable=True, comment='Stochastic distribution for yield percentage')
#     setup_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for setup time')
#     changeover_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for changeover time')
#
#     __table_args__ = (
#         Index('idx_prod_process_site', 'site_id'),
#         Index('idx_prod_process_group_config', 'group_id', 'config_id'),
#         Index('idx_prod_process_config', 'config_id'),
#     )


# NOTE: SourcingRules is now defined in sc_entities.py (canonical SC file)
# Commenting out duplicate definition to avoid SQLAlchemy metadata conflict
# class SourcingRules(Base):
#     """Sourcing rules with priority and allocation
#
#     SC standard sourcing rules with support for buy/transfer/manufacture.
#     Includes FK references to trading partners, lanes, and production processes.
#     """
#     __tablename__ = "sourcing_rules"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     supplier_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     priority = Column(Integer, nullable=False)
#     sourcing_rule_type = Column(String(50), nullable=False)  # transfer, buy, manufacture
#     allocation_percent = Column(DECIMAL(5, 2), nullable=False)
#     min_qty = Column(DECIMAL(10, 2))
#     max_qty = Column(DECIMAL(10, 2))
#     qty_multiple = Column(DECIMAL(10, 2))
#     lead_time = Column(Integer)
#     unit_cost = Column(DECIMAL(10, 2))
#     eff_start_date = Column(DateTime, nullable=False, server_default='1900-01-01 00:00:00')
#     eff_end_date = Column(DateTime, nullable=False, server_default='9999-12-31 23:59:59')
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#     updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     # SC Foreign Key References
#     tpartner_id = Column(String(100), ForeignKey("trading_partners.id"))  # For 'buy' type rules (INT to match trading_partner.id)
#     transportation_lane_id = Column(String(100))  # For 'transfer' type rules
#     production_process_id = Column(String(100), ForeignKey("production_process.id"))  # For 'manufacture' type rules
#
#     # SC Hierarchical override fields (3-level hierarchy)
#     product_group_id = Column(String(100))  # Level 2 - Product group
#     company_id = Column(String(100))  # Level 3 - Company (lowest priority)
#
#     # Phase 5: Stochastic distribution fields
#     sourcing_lead_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for sourcing lead time')


# NOTE: InvPolicy is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class InvPolicy(Base):
#     """Inventory policy configuration with SC standard fields"""
#     __tablename__ = "inv_policy"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     policy_type = Column(String(50), nullable=False, server_default='base_stock')
#     target_qty = Column(DECIMAL(10, 2))
#     min_qty = Column(DECIMAL(10, 2))
#     max_qty = Column(DECIMAL(10, 2))
#     reorder_point = Column(DECIMAL(10, 2))
#     order_qty = Column(DECIMAL(10, 2))
#     review_period = Column(Integer)
#     service_level = Column(DECIMAL(5, 2))
#     holding_cost = Column(DECIMAL(10, 2))
#     backlog_cost = Column(DECIMAL(10, 2))
#     selling_price = Column(DECIMAL(10, 2))
#     eff_start_date = Column(DateTime, nullable=False, server_default='1900-01-01 00:00:00')
#     eff_end_date = Column(DateTime, nullable=False, server_default='9999-12-31 23:59:59')
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#     updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     # SC Hierarchical override fields (6-level hierarchy)
#     product_group_id = Column(String(100))  # Level 2 - Product group
#     dest_geo_id = Column(String(100))  # Level 4 - Destination geography
#     segment_id = Column(String(100))  # Level 5 - Market segment
#     company_id = Column(String(100))  # Level 6 - Company (lowest priority)
#
#     # SC Safety Stock Policy Type fields
#     # Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
#     ss_policy = Column(String(20))  # Safety stock policy: abs_level, doc_dem, doc_fcst, sl
#     ss_days = Column(Integer)  # Days of coverage for doc_dem/doc_fcst policies
#     ss_quantity = Column(Double)  # Absolute quantity for abs_level policy
#     policy_value = Column(Double)  # Generic policy value field
#
#     # SC Periodic Review Policy Field
#     # Used with sourcing schedules for order-up-to systems
#     # Formula: order_qty = order_up_to_level - (on_hand + on_order)
#     order_up_to_level = Column(DECIMAL(10, 2))  # Target inventory level for periodic review


# NOTE: InvLevel is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class InvLevel(Base):
#     """Inventory level snapshots"""
#     __tablename__ = "inv_level"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     on_hand_qty = Column(DECIMAL(10, 2), server_default='0')
#     available_qty = Column(DECIMAL(10, 2), server_default='0')
#     reserved_qty = Column(DECIMAL(10, 2), server_default='0')
#     in_transit_qty = Column(DECIMAL(10, 2), server_default='0')
#     backorder_qty = Column(DECIMAL(10, 2), server_default='0')
#     safety_stock_qty = Column(DECIMAL(10, 2))
#     reorder_point_qty = Column(DECIMAL(10, 2))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     snapshot_date = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#     updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))


# NOTE: Reservation is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class Reservation(Base):
#     """Inventory reservations"""
#     __tablename__ = "reservation"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#     reservation_date = Column(Date, nullable=False)
#     reserved_quantity = Column(Double, nullable=False)
#     reservation_type = Column(String(50))
#     reference_id = Column(String(100))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     game_id = Column(Integer, ForeignKey("games.id"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#
#     __table_args__ = (
#         Index('idx_reservation_lookup', 'product_id', 'site_id', 'reservation_date'),
#         Index('idx_reservation_group_config', 'group_id', 'config_id'),
#         Index('idx_reservation_config', 'config_id'),
#     )


# NOTE: OutboundOrderLine is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class OutboundOrderLine(Base):
#     """Customer orders (actual demand) - execution entity
#
#     Tracks orders FROM customers TO sites (demand fulfillment).
#     Used for recording actual customer demand in Beer Game execution.
#
#     Key Fields:
#     - quantity_delivered: Actual fulfilled quantity (primary)
#     - quantity_promised: Committed quantity to customer
#     - final_quantity_requested: Final requested quantity after changes
#     - actual_delivery_date: When order was actually delivered
#     """
#     __tablename__ = "outbound_order_line"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     order_id = Column(String(100), nullable=False)
#     line_number = Column(Integer, nullable=False)
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
#
#     # Order quantities (execution tracking)
#     init_quantity_requested = Column(Double)  # Original order quantity
#     final_quantity_requested = Column(Double, nullable=False)  # Final quantity after changes
#     quantity_promised = Column(Double)  # Quantity promised to customer
#     quantity_delivered = Column(Double)  # Actual delivered quantity (PRIMARY)
#
#     # Dates (execution timeline)
#     order_date = Column(Date)
#     requested_delivery_date = Column(Date, nullable=False)
#     promised_delivery_date = Column(Date)
#     actual_delivery_date = Column(Date)  # When actually delivered
#
#     # Status and metadata
#     status = Column(String(50))  # Order status (open, delivered, cancelled)
#     ship_from_site_id = Column(Integer, ForeignKey("site.id"))
#     ship_to_site_id = Column(Integer, ForeignKey("site.id"))
#
#     # Multi-tenancy and game context
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     game_id = Column(Integer, ForeignKey("games.id"))
#     round_number = Column(Integer)  # Which game round this order belongs to
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#
#     __table_args__ = (
#         Index('idx_outbound_order_lookup', 'product_id', 'site_id', 'requested_delivery_date'),
#         Index('idx_outbound_order_group_config', 'group_id', 'config_id'),
#         Index('idx_outbound_order_config', 'config_id'),
#         Index('idx_outbound_order_game_round', 'game_id', 'round_number'),
#     )


# NOTE: InboundOrderLine is defined in sc_entities.py (canonical AWS SC model).
# Re-exported here for backward compatibility with services that import from sc_planning.
from app.models.sc_entities import InboundOrderLine  # noqa: F401


class ProductionCapacity(Base):
    """Production/transfer capacity limits per site (Phase 3 - Capacity Constraints)

    Tracks capacity constraints for sites, preventing unlimited production/transfers.
    Used to enforce realistic capacity limits in Beer Game execution.

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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
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
        Index('idx_capacity_group_config', 'group_id', 'config_id'),
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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
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
        Index('idx_agg_policy_group_config', 'group_id', 'config_id'),
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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
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


# NOTE: VendorLeadTime is now defined in supplier.py with full SC compliance
# Commenting out to avoid SQLAlchemy metadata conflict
# class VendorLeadTime(Base):
#     """Vendor lead times with hierarchical override"""
#     __tablename__ = "vendor_lead_time"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     vendor_id = Column(String(100), nullable=False)
#     product_id = Column(String(100), ForeignKey("product.id"))
#     product_group_id = Column(String(100))
#     site_id = Column(Integer, ForeignKey("site.id"))
#     geo_id = Column(String(100))
#     segment_id = Column(String(100))  # Added for full 5-level hierarchy
#     company_id = Column(String(100))
#     lead_time_days = Column(Integer, nullable=False)
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     # Phase 5: Stochastic distribution fields
#     lead_time_dist = Column(JSON, nullable=True, comment='Stochastic distribution for vendor lead time')
#
#     __table_args__ = (
#         Index('idx_vendor_lt_override', 'product_id', 'product_group_id', 'site_id', 'geo_id', 'company_id'),
#         Index('idx_vendor_lt_group_config', 'group_id', 'config_id'),
#         Index('idx_vendor_lt_config', 'config_id'),
#     )


# NOTE: SupplyPlanningParameters is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class SupplyPlanningParameters(Base):
#     """Supply planning configuration parameters"""
#     __tablename__ = "supply_planning_parameters"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     product_id = Column(String(100), ForeignKey("product.id"))
#     site_id = Column(Integer, ForeignKey("site.id"))
#     planning_time_fence = Column(Integer)
#     lot_size_rule = Column(String(50))
#     lot_size_value = Column(Double)
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#
#     __table_args__ = (
#         Index('idx_spp_lookup', 'product_id', 'site_id'),
#         Index('idx_spp_group_config', 'group_id', 'config_id'),
#     )


# NOTE: TradingPartner is now defined in sc_entities.py (canonical SC file)
# Commenting out duplicate definition to avoid SQLAlchemy metadata conflict
# class TradingPartner(Base):
#     """Trading partners (vendors/suppliers) in the supply chain
#
#     SC standard entity for managing external suppliers and vendors.
#     Used in sourcing_rules and vendor_product relationships.
#
#     Note: This table already exists from 20260107_aws_standard_entities.py migration.
#     Model definition matches existing schema.
#
#     Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
#     """
#     __tablename__ = "trading_partner"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)  # Trading partner ID
#     description = Column(String(255))  # Partner name
#     country = Column(String(100))
#     eff_start_date = Column(DateTime, server_default='1900-01-01 00:00:00')
#     eff_end_date = Column(DateTime, server_default='9999-12-31 23:59:59')
#     time_zone = Column(String(50))
#     is_active = Column(Integer)  # tinyint(1) in MySQL
#     tpartner_type = Column(String(50), server_default='SCN_RESERVED_NO_VALUE_PROVIDED')
#     geo_id = Column(Integer, ForeignKey("geography.id"))
#     address_1 = Column(String(255))
#     address_2 = Column(String(255))
#     city = Column(String(100))
#     state_prov = Column(String(100))
#     postal_code = Column(String(20))
#     phone_number = Column(String(50))
#     email = Column(String(255))
#     website = Column(String(255))
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#     updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
#
#     __table_args__ = (
#         Index('ix_trading_partner_id', 'id'),
#         Index('ix_trading_partner_geo_id', 'geo_id'),
#         Index('ix_trading_partner_type', 'tpartner_type'),
#         Index('ix_trading_partner_is_active', 'is_active'),
#         Index('idx_trading_partner_group_config', 'group_id', 'config_id'),
#     )


# NOTE: VendorProduct is now defined in sc_entities.py (canonical SC file)
# Commenting out to avoid SQLAlchemy metadata conflict
# class VendorProduct(Base):
#     """Vendor-specific product information (pricing, lead times, MOQ)
#
#     SC standard entity for vendor-product relationships.
#     Stores unit costs, lead times, and ordering constraints per vendor.
#
#     Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
#     """
#     __tablename__ = "vendor_product"
#
#     id = Column(Integer, primary_key=True, autoincrement=True)
#     tpartner_id = Column(Integer, ForeignKey("trading_partners.id"), nullable=False)  # INT to match trading_partner.id
#     product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
#     vendor_product_id = Column(String(100))  # Vendor's SKU/part number
#     unit_cost = Column(DECIMAL(10, 2))  # Cost per unit from this vendor
#     currency_code = Column(String(10))
#     lead_time_days = Column(Integer)  # Vendor-specific lead time
#     min_order_qty = Column(DECIMAL(10, 2))  # Minimum order quantity
#     order_multiple = Column(DECIMAL(10, 2))  # Must order in multiples of this
#     max_order_qty = Column(DECIMAL(10, 2))  # Maximum order quantity
#     is_preferred = Column(String(10), server_default='false')
#     is_active = Column(String(10), server_default='true')
#     eff_start_date = Column(DateTime, server_default='1900-01-01 00:00:00')
#     eff_end_date = Column(DateTime, server_default='9999-12-31 23:59:59')
#     group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
#     created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
#     updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
#
#     __table_args__ = (
#         Index('idx_vendor_product_lookup', 'tpartner_id', 'product_id'),
#         Index('idx_vendor_product_group_config', 'group_id', 'config_id'),
#         Index('idx_vendor_product_config', 'config_id'),
#     )


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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_sourcing_schedule_site', 'to_site_id'),
        Index('idx_sourcing_schedule_group_config', 'group_id', 'config_id'),
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
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_sourcing_schedule_details_schedule', 'sourcing_schedule_id'),
        Index('idx_sourcing_schedule_details_product', 'product_id'),
        Index('idx_sourcing_schedule_details_group_config', 'group_id', 'config_id'),
        Index('idx_sourcing_schedule_details_config', 'config_id'),
    )

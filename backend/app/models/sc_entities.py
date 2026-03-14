"""
Supply Chain Data Model Entities

This module implements core supply chain data entities following
industry-standard supply chain planning architecture.

Entities include: Company, Site, Product, Inventory, Forecasts, and Supply Plans.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Double,
    ForeignKey,
    DateTime,
    Date,
    Boolean,
    JSON,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.orm import relationship
from datetime import datetime, date
from typing import Optional
from .base import Base


# ============================================================================
# Organization Entities
# ============================================================================

class Company(Base):
    """
    Company/organization information
    SC Entity: company
    """
    __tablename__ = "company"

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    address_1 = Column(String(255))
    address_2 = Column(String(255))
    address_3 = Column(String(255))
    city = Column(String(100))
    state_prov = Column(String(100))
    postal_code = Column(String(50))
    country = Column(String(100))
    phone_number = Column(String(50))
    time_zone = Column(String(50))
    calendar_id = Column(String(100))

    # Relationships
    geographies = relationship("Geography", back_populates="company")
    sites = relationship("Site", back_populates="company")
    products = relationship("Product", back_populates="company")
    sourcing_rules = relationship("SourcingRules", back_populates="company")


class Geography(Base):
    """
    Geographical hierarchies for regional planning and filtering
    SC Entity: geography
    """
    __tablename__ = "geography"

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))
    parent_geo_id = Column(String(100), ForeignKey("geography.id"))
    address_1 = Column(String(255))
    address_2 = Column(String(255))
    address_3 = Column(String(255))
    city = Column(String(100))
    state_prov = Column(String(100))
    postal_code = Column(String(50))
    country = Column(String(100))
    phone_number = Column(String(50))
    time_zone = Column(String(50))
    latitude = Column(Double)
    longitude = Column(Double)
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Relationships
    company = relationship("Company", back_populates="geographies")
    parent = relationship("Geography", remote_side=[id], backref="children")
    sites = relationship("Site", back_populates="geography")


class TradingPartner(Base):
    """
    Suppliers, customers, carriers, and other trading partners
    SC Entity: trading_partner

    SIMPLIFIED for simulation: Single column PK instead of composite PK
    Standard model uses composite PK (id, tpartner_type, geo_id, eff_start_date, eff_end_date)
    but simulation doesn't need temporal tracking, so we use a surrogate key.

    Table name: trading_partners (pluralized for consistency with other platform tables)
    """
    __tablename__ = "trading_partners"

    # Surrogate PK for simplicity (allows simple foreign key references)
    _id = Column(Integer, primary_key=True, autoincrement=True)

    # Standard supply chain fields (id is now unique but not part of PK)
    id = Column(String(100), nullable=False, unique=True, index=True)  # Business key
    tpartner_type = Column(String(50), nullable=False)  # vendor, customer, 3PL, carrier
    geo_id = Column(String(100), ForeignKey("geography.id"), nullable=True)
    eff_start_date = Column(DateTime, nullable=True)  # Optional for simulation
    eff_end_date = Column(DateTime, nullable=True)  # Optional for simulation

    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))
    is_active = Column(String(10), default="true")  # 'true' or 'false'
    address_1 = Column(String(255))
    address_2 = Column(String(255))
    address_3 = Column(String(255))
    city = Column(String(100))
    state_prov = Column(String(100))
    postal_code = Column(String(50))
    country = Column(String(100))
    phone_number = Column(String(50))
    time_zone = Column(String(50))
    latitude = Column(Double)
    longitude = Column(Double)
    os_id = Column(String(100))  # Open Supplier Hub organizational ID
    duns_number = Column(String(20))  # Dun & Bradstreet 9-digit ID
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Relationships
    geography = relationship("Geography")
    # Vendor relationships (imported from supplier module)
    vendor_products = relationship("VendorProduct", back_populates="trading_partner")
    vendor_lead_times = relationship("VendorLeadTime", back_populates="trading_partner")
    performance_records = relationship("SupplierPerformance", back_populates="supplier")


# ============================================================================
# Network Entities
# ============================================================================
# NOTE: Site and TransportationLane are now defined in supply_chain_config.py
# with Integer PKs for platform compatibility. Import from there:
#   from app.models.supply_chain_config import Site, TransportationLane


# ============================================================================
# Product Entities
# ============================================================================

class ProductHierarchy(Base):
    """
    Product groups with hierarchical structure
    SC Entity: product_hierarchy
    """
    __tablename__ = "product_hierarchy"

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))
    parent_product_group_id = Column(String(100), ForeignKey("product_hierarchy.id"))
    level = Column(Integer)
    sort_order = Column(Integer)
    is_active = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("ProductHierarchy", remote_side=[id], backref="children")
    products = relationship("Product", back_populates="product_group")


class Product(Base):
    """
    Individual SKUs with extensive attributes
    SC Entity: product
    Extended from existing 'items' table
    """
    __tablename__ = "product"

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))
    product_group_id = Column(String(100), ForeignKey("product_hierarchy.id"))
    unit_cost = Column(Double)
    unit_price = Column(Double)
    product_type = Column(String(50))
    item_type = Column(String(50))  # standard, phantom, kit
    base_uom = Column(String(20))  # EA, CS, PAL
    weight = Column(Double)
    weight_uom = Column(String(20))
    volume = Column(Double)
    volume_uom = Column(String(20))
    is_active = Column(String(10))
    is_deleted = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    priority = Column(Integer)
    unit_cost_range = Column(JSON)

    # Product hierarchy fields (for breadcrumb display)
    # Format: Category > Family > Group > Product
    category = Column(String(100), nullable=True, comment="Top-level category (e.g., Frozen, Refrigerated)")
    family = Column(String(100), nullable=True, comment="Product family (e.g., Proteins, Dairy)")
    product_group_name = Column("product_group", String(100), nullable=True, comment="Product group (e.g., Chicken, Beef)")

    # Relationships
    company = relationship("Company", back_populates="products")
    product_group = relationship("ProductHierarchy", back_populates="products")
    config = relationship("SupplyChainConfig")
    bom_entries = relationship("ProductBom", foreign_keys="ProductBom.product_id", back_populates="product")
    component_of = relationship("ProductBom", foreign_keys="ProductBom.component_product_id", back_populates="component")
    inv_policies = relationship("InvPolicy", back_populates="product")
    inv_levels = relationship("InvLevel", back_populates="product")


# ============================================================================
# Supply Planning Entities
# ============================================================================

class SourcingRules(Base):
    """
    Network topology (transfer/buy/manufacture) with priorities and ratios
    SC Entity: sourcing_rules
    Replaces lanes + item_node_suppliers
    """
    __tablename__ = "sourcing_rules"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    product_group_id = Column(String(100), ForeignKey("product_hierarchy.id"))
    from_site_id = Column(Integer, ForeignKey("site.id"))
    to_site_id = Column(Integer, ForeignKey("site.id"))
    tpartner_id = Column(String(100))  # For buy type - FK to trading_partner
    sourcing_rule_type = Column(String(20))  # transfer, buy, manufacture
    sourcing_priority = Column(Integer)  # Smaller = higher priority
    sourcing_ratio = Column(Double)  # For multi-sourcing allocation
    min_quantity = Column(Double)
    max_quantity = Column(Double)
    lot_size = Column(Double)
    transportation_lane_id = Column(Integer, ForeignKey("transportation_lane.id"))  # For transfer type
    production_process_id = Column(String(100), ForeignKey("production_process.id"))  # For manufacture type
    eff_start_date = Column(DateTime)
    eff_end_date = Column(DateTime)
    is_active = Column(String(10))
    is_deleted = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    # Relationships
    company = relationship("Company", back_populates="sourcing_rules")
    product = relationship("Product")
    product_group = relationship("ProductHierarchy")
    from_site = relationship("Site", foreign_keys=[from_site_id])
    to_site = relationship("Site", foreign_keys=[to_site_id])
    transportation_lane = relationship("TransportationLane")
    production_process = relationship("ProductionProcess", back_populates="sourcing_rules")
    config = relationship("SupplyChainConfig")

    # Override logic index: product_id > product_group_id > company_id
    __table_args__ = (
        Index('idx_sourcing_override', 'product_id', 'product_group_id', 'company_id'),
    )


class InvPolicy(Base):
    """
    Safety stock policies (abs_level, doc_dem, doc_fcst, sl, conformal)
    SC Entity: inv_policy
    Refactored from item_node_configs

    Policy Types:
    - abs_level: Fixed quantity safety stock
    - doc_dem: Days of coverage (demand-based)
    - doc_fcst: Days of coverage (forecast-based)
    - sl: Service level (probabilistic with z-score)
    - conformal: Conformal prediction-based (distribution-free guarantees)
    """
    __tablename__ = "inv_policy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    site_id = Column(Integer, ForeignKey("site.id"))
    geo_id = Column(String(100), ForeignKey("geography.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    product_group_id = Column(String(100), ForeignKey("product_hierarchy.id"))
    segment_id = Column(String(100))

    ss_policy = Column(String(20))  # abs_level, doc_dem, doc_fcst, sl, conformal
    ss_quantity = Column(Double)  # For abs_level
    ss_days = Column(Integer)  # For doc_dem, doc_fcst
    service_level = Column(Double)  # For sl (0-1)

    # Conformal prediction policy fields (ss_policy = 'conformal')
    conformal_demand_coverage = Column(Double, default=0.90)  # 0.90 = 90% coverage guarantee
    conformal_lead_time_coverage = Column(Double, default=0.90)  # 0.90 = 90% coverage guarantee

    review_period = Column(Integer)  # Days
    order_up_to_level = Column(Double)
    reorder_point = Column(Double)
    min_order_quantity = Column(Double)
    max_order_quantity = Column(Double)
    fixed_order_quantity = Column(Double)

    eff_start_date = Column(DateTime)
    eff_end_date = Column(DateTime)
    is_active = Column(String(10))
    is_deleted = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    inventory_target_range = Column(JSON)
    initial_inventory_range = Column(JSON)
    holding_cost_range = Column(JSON)
    backlog_cost_range = Column(JSON)
    selling_price_range = Column(JSON)

    # Relationships
    site = relationship("Site", back_populates="inv_policies")
    geography = relationship("Geography")
    product = relationship("Product", back_populates="inv_policies")
    product_group = relationship("ProductHierarchy")
    config = relationship("SupplyChainConfig")

    # Override logic index: product_id > product_group_id > site_id > geo_id > segment_id > company_id
    __table_args__ = (
        Index('idx_inv_policy_override', 'product_id', 'product_group_id', 'site_id', 'geo_id', 'segment_id', 'company_id'),
    )


class InvLevel(Base):
    """
    Inventory snapshots with lot tracking
    SC Entity: inv_level
    """
    __tablename__ = "inv_level"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"))
    inventory_date = Column(Date)

    on_hand_qty = Column(Double)
    in_transit_qty = Column(Double)
    on_order_qty = Column(Double)
    allocated_qty = Column(Double)
    available_qty = Column(Double)
    reserved_qty = Column(Double)

    lot_number = Column(String(100))
    lot_expiration_date = Column(Date)

    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    round_number = Column(Integer)
    backorder_qty = Column(Double)       # Unfulfilled demand carried as backorder
    safety_stock_qty = Column(Double)    # Safety stock level (snapshot from inv_policy)

    # Relationships
    product = relationship("Product", back_populates="inv_levels")
    site = relationship("Site", back_populates="inv_levels")
    config = relationship("SupplyChainConfig")
    scenario = relationship("Scenario")

    __table_args__ = (
        Index('idx_inv_level_lookup', 'product_id', 'site_id', 'inventory_date'),
    )


# ============================================================================
# NOTE: VendorProduct and VendorLeadTime are defined in supplier.py
# ============================================================================


class SupplyPlanningParameters(Base):
    """
    Planner assignments to products
    SC Entity: supply_planning_parameters
    """
    __tablename__ = "supply_planning_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    planner_name = Column(String(100))
    planner_email = Column(String(255))
    is_active = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Relationships
    product = relationship("Product")


# ============================================================================
# Manufacturing Entities
# ============================================================================

class ProductBom(Base):
    """
    Bill of materials with component ratios
    SC Entity: product_bom
    Extracted from Node.attributes JSON
    """
    __tablename__ = "product_bom"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    component_product_id = Column(String(100), ForeignKey("product.id"))
    production_process_id = Column(String(100), ForeignKey("production_process.id"))

    component_quantity = Column(Double)
    component_uom = Column(String(20))
    scrap_percentage = Column(Double)
    alternate_group = Column(Integer)  # For alternate components
    priority = Column(Integer)  # Within alternate group

    eff_start_date = Column(DateTime)
    eff_end_date = Column(DateTime)
    is_active = Column(String(10))
    is_deleted = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    # MPS Key Material Extension
    # Flag indicating if this component is a key/critical material that should be
    # included in MPS rough-cut planning. Key materials are typically:
    # - Long lead time items (>4 weeks)
    # - Bottleneck/constrained resources
    # - High-value components
    # - Strategic materials with limited suppliers
    is_key_material = Column(String(10), default='false')  # 'true' or 'false' string values

    # Relationships
    product = relationship("Product", foreign_keys=[product_id], back_populates="bom_entries")
    component = relationship("Product", foreign_keys=[component_product_id], back_populates="component_of")
    production_process = relationship("ProductionProcess", back_populates="bom_entries")
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_bom_lookup', 'product_id', 'component_product_id'),
    )


class ProductionProcess(Base):
    """
    Manufacturing lead times and setup times
    SC Entity: production_process
    """
    __tablename__ = "production_process"
    __table_args__ = (
        Index("idx_production_process_site", "site_id"),
        Index("idx_production_process_config", "config_id"),
    )

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))
    site_id = Column(Integer, ForeignKey("site.id"))
    process_type = Column(String(50))
    operation_time = Column(Double)  # Hours
    setup_time = Column(Double)  # Hours
    lot_size = Column(Double)
    yield_percentage = Column(Double)
    is_active = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Extension: Stochastic distribution parameters (from SAP operational stats)
    # JSON format: {"type": "lognormal", "mean_log": ..., "stddev_log": ..., "min": ..., "max": ...}
    # NULL = use deterministic base field value
    operation_time_dist = Column(JSON, nullable=True)
    setup_time_dist = Column(JSON, nullable=True)
    yield_dist = Column(JSON, nullable=True)
    mtbf_dist = Column(JSON, nullable=True)   # Mean time between failures (days)
    mttr_dist = Column(JSON, nullable=True)   # Mean time to repair (hours)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    manufacturing_leadtime = Column(Integer, default=0)
    manufacturing_capacity_hours = Column(Double)

    # Relationships
    site = relationship("Site")
    config = relationship("SupplyChainConfig")
    bom_entries = relationship("ProductBom", back_populates="production_process")
    sourcing_rules = relationship("SourcingRules", back_populates="production_process")


# ============================================================================
# Planning Output Entities
# ============================================================================

class SupplyPlan(Base):
    """
    Generated supply recommendations (PO/TO/MO requests)
    SC Entity: supply_plan
    """
    __tablename__ = "supply_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"))
    plan_date = Column(Date)

    plan_type = Column(String(50))  # po_request, mo_request, to_request
    planning_group = Column(String(100))

    forecast_quantity = Column(Double)
    demand_quantity = Column(Double)
    supply_quantity = Column(Double)
    opening_inventory = Column(Double)
    closing_inventory = Column(Double)
    safety_stock = Column(Double)
    reorder_point = Column(Double)

    planned_order_quantity = Column(Double)
    planned_order_date = Column(Date)
    planned_receipt_date = Column(Date)

    supplier_id = Column(String(100))  # FK to trading_partner
    from_site_id = Column(Integer, ForeignKey("site.id"))
    planner_name = Column(String(100))
    order_cost = Column(Double)

    plan_version = Column(String(50))
    created_dttm = Column(DateTime, default=datetime.utcnow)
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    round_number = Column(Integer)

    # Conformal prediction metadata — interval bounds used to generate this plan
    demand_lower = Column(Double, nullable=True)       # Lower demand bound
    demand_upper = Column(Double, nullable=True)       # Upper demand bound
    demand_coverage = Column(Double, nullable=True)    # Coverage guarantee (e.g., 0.90)
    lead_time_lower = Column(Double, nullable=True)    # Earliest arrival (days)
    lead_time_upper = Column(Double, nullable=True)    # Latest arrival (days)
    lead_time_coverage = Column(Double, nullable=True) # LT coverage guarantee
    joint_coverage = Column(Double, nullable=True)     # demand_coverage × lead_time_coverage
    conformal_method = Column(String(50), nullable=True)  # "adaptive", "split", "stored_percentiles"

    # Relationships
    product = relationship("Product")
    site = relationship("Site", foreign_keys=[site_id])
    from_site = relationship("Site", foreign_keys=[from_site_id])
    config = relationship("SupplyChainConfig")
    scenario = relationship("Scenario")

    __table_args__ = (
        Index('idx_supply_plan_lookup', 'product_id', 'site_id', 'plan_date'),
    )


class Forecast(Base):
    """
    Demand forecasts (deterministic & stochastic with P10/P50/P90)
    SC Entity: forecast
    Refactored from MarketDemand
    """
    __tablename__ = "forecast"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"))
    customer_id = Column(String(100))  # FK to trading_partner
    forecast_date = Column(Date)

    forecast_type = Column(String(50))  # statistical, consensus, override
    forecast_level = Column(String(50))  # product, product_group, site, region
    forecast_method = Column(String(50))  # moving_average, exponential_smoothing, arima, ml

    forecast_quantity = Column(Double)
    forecast_p10 = Column(Double)  # 10th percentile (optimistic)
    forecast_p50 = Column(Double)  # 50th percentile (median)
    forecast_median = Column(Double)  # Explicit median forecast (mirrors p50)
    forecast_p90 = Column(Double)  # 90th percentile (pessimistic)
    forecast_std_dev = Column(Double)
    forecast_confidence = Column(Double)  # 0-1
    forecast_error = Column(Double)
    forecast_bias = Column(Double)

    user_override_quantity = Column(Double)
    override_reason = Column(String(500))
    created_by = Column(String(100))
    created_dttm = Column(DateTime, default=datetime.utcnow)
    is_active = Column(String(10))
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Simulation extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    demand_pattern = Column(JSON)  # Classic simulation demand patterns

    # Relationships
    product = relationship("Product")
    site = relationship("Site")
    config = relationship("SupplyChainConfig")
    scenario = relationship("Scenario")

    __table_args__ = (
        Index('idx_forecast_lookup', 'product_id', 'site_id', 'forecast_date'),
    )


class Reservation(Base):
    """Inventory reservations for component requirements"""
    __tablename__ = "reservation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    reservation_date = Column(Date, nullable=False)
    reserved_quantity = Column(Double, nullable=False)
    reservation_type = Column(String(50))  # component, customer_order, transfer
    reference_id = Column(String(100))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_reservation_lookup', 'product_id', 'site_id', 'reservation_date'),
    )


class OutboundOrderLine(Base):
    """
    Customer orders (actual demand)

    Extended for simulation execution with fulfillment tracking:
    - promised_quantity: ATP-promised amount
    - shipped_quantity: Fulfilled so far
    - backlog_quantity: Unfulfilled amount
    - status: Order lifecycle tracking
    - priority_code: VIP vs STANDARD ordering
    """
    __tablename__ = "outbound_order_line"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), nullable=False)
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    ordered_quantity = Column(Double, nullable=False)
    requested_delivery_date = Column(Date, nullable=False)
    order_date = Column(Date)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))

    # Simulation execution extensions
    promised_quantity = Column(Double)  # ATP-promised quantity
    shipped_quantity = Column(Double, server_default=text("0.0"), nullable=False)  # Fulfilled amount
    backlog_quantity = Column(Double, server_default=text("0.0"), nullable=False)  # Unfulfilled amount
    status = Column(String(20), server_default=text("'DRAFT'"), nullable=False)  # DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED, CANCELLED
    priority_code = Column(String(20), server_default=text("'STANDARD'"), nullable=False)  # VIP, HIGH, STANDARD, LOW
    promised_delivery_date = Column(Date)  # ATP-promised delivery date
    first_ship_date = Column(Date)  # First partial shipment date
    last_ship_date = Column(Date)  # Final shipment date
    market_demand_site_id = Column(Integer, ForeignKey("site.id"))  # Customer site (for simulation)

    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_outbound_order_lookup', 'product_id', 'site_id', 'requested_delivery_date'),
        Index('idx_outbound_status', 'status'),
        Index('idx_outbound_priority', 'priority_code'),
        Index('idx_outbound_backlog', 'backlog_quantity'),
        Index('idx_outbound_order_date_priority', 'order_date', 'priority_code'),
    )


# ============================================================================
# Shipment & Logistics Entities
# ============================================================================

class Shipment(Base):
    """
    Shipment tracking for in-transit inventory
    SC Entity: shipment (Material Visibility)
    Tracks shipments from source to destination with real-time status
    """
    __tablename__ = "shipment"

    id = Column(String(100), primary_key=True)
    description = Column(String(500))
    company_id = Column(String(100), ForeignKey("company.id"))

    # Order references
    order_id = Column(String(100), nullable=False, index=True)
    order_line_number = Column(Integer)

    # Product and quantity
    product_id = Column(String(100), nullable=False, index=True)
    quantity = Column(Double, nullable=False)
    uom = Column(String(20))

    # Sites
    from_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Transportation
    transportation_lane_id = Column(Integer, ForeignKey("transportation_lane.id"))
    carrier_id = Column(String(100))  # FK to trading_partner
    carrier_name = Column(String(200))
    tracking_number = Column(String(100), index=True)

    # Status and dates
    status = Column(String(20), nullable=False)  # planned, in_transit, delivered, delayed, exception, cancelled
    ship_date = Column(DateTime)
    expected_delivery_date = Column(DateTime, index=True)
    actual_delivery_date = Column(DateTime)

    # Location tracking
    current_location = Column(String(200))
    current_location_lat = Column(Double)
    current_location_lon = Column(Double)
    last_tracking_update = Column(DateTime)

    # Risk assessment
    delivery_risk_score = Column(Double)  # 0-100, higher = more risk
    risk_level = Column(String(20))  # LOW, MEDIUM, HIGH, CRITICAL
    risk_factors = Column(JSON)  # {"weather": 0.3, "carrier_performance": 0.5}

    # Event history
    tracking_events = Column(JSON)  # [{"timestamp": "...", "location": "...", "event": "..."}]

    # Mitigation
    recommended_actions = Column(JSON)  # [{"action": "expedite", "impact": "...", "cost": "..."}]
    mitigation_status = Column(String(20))  # none, recommended, in_progress, completed

    # Config / tenant context
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    # Standard metadata
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    from_site = relationship("Site", foreign_keys=[from_site_id])
    to_site = relationship("Site", foreign_keys=[to_site_id])
    transportation_lane = relationship("TransportationLane", foreign_keys=[transportation_lane_id])
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_shipment_status', 'status', 'expected_delivery_date'),
        Index('idx_shipment_risk', 'risk_level', 'status'),
        Index('idx_shipment_tracking', 'tracking_number', 'carrier_id'),
        Index('idx_shipment_config', 'config_id'),
    )


# ============================================================================
# Inbound Order Entities
# ============================================================================

class InboundOrder(Base):
    """
    Purchase orders and transfer receipts
    SC Entity: inbound_order
    Tracks orders placed on suppliers and inter-site transfers.
    """
    __tablename__ = "inbound_order"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    order_type = Column(String(50), nullable=False)  # PURCHASE, TRANSFER, RETURN
    supplier_id = Column(String(100))  # FK to trading_partner
    supplier_name = Column(String(200))

    # Sites
    ship_from_site_id = Column(Integer, ForeignKey("site.id"))
    ship_to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Status
    status = Column(String(30), nullable=False, server_default=text("'DRAFT'"))
    # DRAFT, CONFIRMED, PARTIALLY_RECEIVED, RECEIVED, CANCELLED

    # Dates
    order_date = Column(Date, nullable=False)
    requested_delivery_date = Column(Date)
    promised_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Totals
    total_ordered_qty = Column(Double, server_default=text("0.0"))
    total_received_qty = Column(Double, server_default=text("0.0"))
    total_value = Column(Double)
    currency = Column(String(10), server_default=text("'USD'"))

    # References
    reference_number = Column(String(100))  # Vendor PO number
    contract_id = Column(String(100))

    # Config
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    # Metadata
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    ship_from_site = relationship("Site", foreign_keys=[ship_from_site_id])
    ship_to_site = relationship("Site", foreign_keys=[ship_to_site_id])
    lines = relationship("InboundOrderLine", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_inbound_order_status', 'status', 'order_type'),
        Index('idx_inbound_order_supplier', 'supplier_id'),
        Index('idx_inbound_order_site', 'ship_to_site_id', 'requested_delivery_date'),
    )


class InboundOrderLine(Base):
    """
    Line items on inbound orders
    SC Entity: inbound_order_line
    """
    __tablename__ = "inbound_order_line"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), ForeignKey("inbound_order.id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)

    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    ordered_quantity = Column(Double, nullable=False)
    received_quantity = Column(Double, server_default=text("0.0"))
    open_quantity = Column(Double)  # ordered - received
    unit_price = Column(Double)
    uom = Column(String(20))

    # Dates
    requested_delivery_date = Column(Date)
    promised_delivery_date = Column(Date)
    actual_receipt_date = Column(Date)

    # Status
    status = Column(String(30), server_default=text("'OPEN'"))
    # OPEN, PARTIALLY_RECEIVED, RECEIVED, CANCELLED

    # Lot tracking
    lot_number = Column(String(100))
    batch_id = Column(String(100))

    # Quality
    inspection_status = Column(String(30))  # PENDING, PASSED, FAILED, WAIVED

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    order = relationship("InboundOrder", back_populates="lines")
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_inbound_line_product', 'product_id', 'site_id', 'requested_delivery_date'),
        Index('idx_inbound_line_order', 'order_id'),
        Index('idx_inbound_line_status', 'status'),
    )


class InboundOrderLineSchedule(Base):
    """
    Delivery schedule for inbound order lines (split deliveries)
    SC Entity: inbound_order_line_schedule
    """
    __tablename__ = "inbound_order_line_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_line_id = Column(Integer, ForeignKey("inbound_order_line.id", ondelete="CASCADE"), nullable=False)

    schedule_number = Column(Integer, nullable=False)
    scheduled_quantity = Column(Double, nullable=False)
    received_quantity = Column(Double, server_default=text("0.0"))
    scheduled_date = Column(Date, nullable=False)
    actual_date = Column(Date)
    status = Column(String(30), server_default=text("'SCHEDULED'"))
    # SCHEDULED, IN_TRANSIT, RECEIVED, DELAYED, CANCELLED

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_inbound_schedule_line', 'order_line_id'),
        Index('idx_inbound_schedule_date', 'scheduled_date', 'status'),
    )


# ============================================================================
# Shipment Detail Entities
# ============================================================================

class ShipmentStop(Base):
    """
    Intermediate stops in multi-leg shipments
    SC Entity: shipment_stop
    """
    __tablename__ = "shipment_stop"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(String(100), ForeignKey("shipment.id", ondelete="CASCADE"), nullable=False)

    stop_number = Column(Integer, nullable=False)
    stop_type = Column(String(30), nullable=False)  # PICKUP, DELIVERY, CROSS_DOCK, CUSTOMS
    site_id = Column(Integer, ForeignKey("site.id"))
    location_name = Column(String(200))
    location_lat = Column(Double)
    location_lon = Column(Double)

    # Dates
    planned_arrival = Column(DateTime)
    actual_arrival = Column(DateTime)
    planned_departure = Column(DateTime)
    actual_departure = Column(DateTime)

    # Status
    status = Column(String(20), server_default=text("'PLANNED'"))
    # PLANNED, ARRIVED, DEPARTED, SKIPPED

    dwell_time_hours = Column(Double)

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    shipment = relationship("Shipment")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_shipment_stop_shipment', 'shipment_id', 'stop_number'),
    )


class ShipmentLot(Base):
    """
    Lot-level tracking within shipments (pharma, food traceability)
    SC Entity: shipment_lot
    """
    __tablename__ = "shipment_lot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(String(100), ForeignKey("shipment.id", ondelete="CASCADE"), nullable=False)

    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    lot_number = Column(String(100), nullable=False)
    batch_id = Column(String(100))
    quantity = Column(Double, nullable=False)
    uom = Column(String(20))

    # Lot details
    manufacture_date = Column(Date)
    expiration_date = Column(Date)
    shelf_life_days = Column(Integer)

    # Quality
    quality_status = Column(String(30), server_default=text("'RELEASED'"))
    # RELEASED, QUARANTINE, REJECTED, RECALL
    certificate_of_analysis = Column(String(200))

    # Traceability
    origin_site_id = Column(Integer, ForeignKey("site.id"))
    country_of_origin = Column(String(10))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    shipment = relationship("Shipment")
    product = relationship("Product")
    origin_site = relationship("Site")

    __table_args__ = (
        Index('idx_shipment_lot_shipment', 'shipment_id'),
        Index('idx_shipment_lot_product', 'product_id', 'lot_number'),
        Index('idx_shipment_lot_expiry', 'expiration_date'),
    )


# ============================================================================
# Outbound Fulfillment Entities
# ============================================================================

class OutboundShipment(Base):
    """
    Outbound shipment against customer orders
    SC Entity: outbound_shipment
    """
    __tablename__ = "outbound_shipment"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    order_id = Column(String(100), nullable=False, index=True)
    order_line_number = Column(Integer)
    shipment_id = Column(String(100), ForeignKey("shipment.id"))

    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    customer_site_id = Column(Integer, ForeignKey("site.id"))

    shipped_quantity = Column(Double, nullable=False)
    uom = Column(String(20))

    # Dates
    ship_date = Column(DateTime, nullable=False)
    expected_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)

    # Status
    status = Column(String(20), nullable=False, server_default=text("'SHIPPED'"))
    # SHIPPED, IN_TRANSIT, DELIVERED, RETURNED

    # Carrier
    carrier_id = Column(String(100))
    tracking_number = Column(String(100))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site", foreign_keys=[site_id])
    customer_site = relationship("Site", foreign_keys=[customer_site_id])

    __table_args__ = (
        Index('idx_outbound_shipment_order', 'order_id'),
        Index('idx_outbound_shipment_status', 'status', 'ship_date'),
    )


# ============================================================================
# Segmentation Entity
# ============================================================================

class Segmentation(Base):
    """
    Customer/product segmentation for differentiated planning
    SC Entity: segmentation
    Referenced by InvPolicy.segment_id
    """
    __tablename__ = "segmentation"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    name = Column(String(200), nullable=False)
    segment_type = Column(String(50), nullable=False)  # CUSTOMER, PRODUCT, CHANNEL
    description = Column(String(500))

    # Classification
    classification = Column(String(10))  # A, B, C (ABC analysis)
    priority = Column(Integer)  # 1=highest
    service_level_target = Column(Double)  # Target SL for this segment

    # Criteria
    criteria = Column(JSON)  # {"revenue_min": 100000, "order_frequency": "weekly"}

    is_active = Column(String(10), server_default=text("'true'"))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_segmentation_type', 'segment_type', 'classification'),
    )


# ============================================================================
# Supplementary Planning Entities
# ============================================================================

class SupplementaryTimeSeries(Base):
    """
    External signals for demand sensing (market intel, weather, promotions)
    SC Entity: supplementary_time_series
    Used by ForecastAdjustmentTRM for signal-driven forecast modifications.
    """
    __tablename__ = "supplementary_time_series"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    series_name = Column(String(200), nullable=False)
    series_type = Column(String(50), nullable=False)
    # PROMOTION, WEATHER, MARKET_INDEX, SOCIAL_MEDIA, ECONOMIC_INDICATOR, COMPETITOR, EMAIL_SIGNAL, VOICE_SIGNAL

    product_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"))

    # Time series data
    observation_date = Column(Date, nullable=False)
    value = Column(Double, nullable=False)
    unit = Column(String(50))

    # Signal metadata
    confidence = Column(Double)  # 0.0-1.0
    source_channel = Column(String(50))  # email, voice, market_feed, weather_api
    signal_direction = Column(String(20))  # UP, DOWN, NEUTRAL
    magnitude = Column(Double)  # Percentage impact estimate

    # Processing
    is_processed = Column(Boolean, server_default=text("false"))
    processed_at = Column(DateTime)
    forecast_impact = Column(Double)  # Actual impact after processing

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_supp_ts_lookup', 'product_id', 'site_id', 'observation_date'),
        Index('idx_supp_ts_type', 'series_type', 'observation_date'),
        Index('idx_supp_ts_unprocessed', 'is_processed', 'series_type'),
    )


# ============================================================================
# Manufacturing Operations Entities
# ============================================================================

class ProcessHeader(Base):
    """
    Manufacturing process routing header
    SC Entity: process_header
    Groups operations into a routing sequence.
    """
    __tablename__ = "process_header"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    process_id = Column(String(100), ForeignKey("production_process.id"))
    description = Column(String(500))
    version = Column(Integer, server_default=text("1"))
    status = Column(String(20), server_default=text("'ACTIVE'"))  # ACTIVE, OBSOLETE, DRAFT

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    operations = relationship("ProcessOperation", back_populates="header", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_process_header_process', 'process_id'),
    )


class ProcessOperation(Base):
    """
    Individual manufacturing operation step
    SC Entity: process_operation
    """
    __tablename__ = "process_operation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    header_id = Column(String(100), ForeignKey("process_header.id", ondelete="CASCADE"), nullable=False)

    operation_number = Column(Integer, nullable=False)
    operation_name = Column(String(200), nullable=False)
    work_center_id = Column(String(100))
    resource_id = Column(String(100))

    # Times (hours)
    setup_time = Column(Double, server_default=text("0.0"))
    run_time_per_unit = Column(Double, nullable=False)
    teardown_time = Column(Double, server_default=text("0.0"))
    queue_time = Column(Double, server_default=text("0.0"))
    move_time = Column(Double, server_default=text("0.0"))

    # Capacity
    max_units_per_hour = Column(Double)
    min_lot_size = Column(Double)
    max_lot_size = Column(Double)

    # Quality
    yield_percentage = Column(Double, server_default=text("100.0"))
    scrap_percentage = Column(Double, server_default=text("0.0"))

    is_subcontracted = Column(Boolean, server_default=text("false"))
    vendor_id = Column(String(100))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    header = relationship("ProcessHeader", back_populates="operations")

    __table_args__ = (
        Index('idx_process_op_header', 'header_id', 'operation_number'),
    )


class ProcessProduct(Base):
    """
    Products consumed/produced by a manufacturing process
    SC Entity: process_product
    """
    __tablename__ = "process_product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    header_id = Column(String(100), ForeignKey("process_header.id", ondelete="CASCADE"), nullable=False)
    operation_id = Column(Integer, ForeignKey("process_operation.id"))

    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    product_type = Column(String(20), nullable=False)  # INPUT, OUTPUT, BYPRODUCT, CO_PRODUCT
    quantity = Column(Double, nullable=False)
    uom = Column(String(20))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")

    __table_args__ = (
        Index('idx_process_product_header', 'header_id'),
        Index('idx_process_product_product', 'product_id'),
    )


class CustomerCost(Base):
    """
    Customer-specific cost/pricing structures
    SC Entity: customer_cost
    """
    __tablename__ = "customer_cost"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    customer_id = Column(String(100), nullable=False)  # FK to trading_partner
    product_id = Column(String(100), ForeignKey("product.id"))
    site_id = Column(Integer, ForeignKey("site.id"))

    cost_type = Column(String(50), nullable=False)  # UNIT_PRICE, SHIPPING, HANDLING, DISCOUNT
    amount = Column(Double, nullable=False)
    currency = Column(String(10), server_default=text("'USD'"))
    uom = Column(String(20))

    # Validity
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date)
    min_quantity = Column(Double)
    max_quantity = Column(Double)

    # Contract reference
    contract_id = Column(String(100))

    # Metadata
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_customer_cost_lookup', 'customer_id', 'product_id', 'effective_date'),
    )


# ============================================================================
# SC Entity: InventoryProjection (ATP/CTP)
# ============================================================================

class InventoryProjection(Base):
    """
    Time-phased inventory projection for Available-to-Promise (ATP)
    and Capable-to-Promise (CTP) calculations.

    SC Entity: inventory_projection

    Each row represents projected inventory for a product-site-period
    combination, enabling forward-looking order promising.

    SC Core Fields:
    - company_id, site_id, product_id, period_start, period_end
    - gross_requirements, scheduled_receipts, projected_on_hand
    - atp_quantity, ctp_quantity

    Extensions:
    - P10/P50/P90 probabilistic projections for stochastic planning
    - supply_plan_id linking to the supply plan that generated this projection
    """
    __tablename__ = "inventory_projection"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # Time bucket
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(20), server_default=text("'WEEKLY'"))  # DAILY, WEEKLY, MONTHLY

    # Projection components
    beginning_on_hand = Column(Double, server_default=text("0"))
    gross_requirements = Column(Double, server_default=text("0"))
    scheduled_receipts = Column(Double, server_default=text("0"))
    planned_receipts = Column(Double, server_default=text("0"))  # From MRP/supply plan
    projected_on_hand = Column(Double, server_default=text("0"))

    # ATP/CTP
    atp_quantity = Column(Double, server_default=text("0"))  # Available-to-Promise
    ctp_quantity = Column(Double)  # Capable-to-Promise (considers production capacity)
    cumulative_atp = Column(Double, server_default=text("0"))  # Cumulative ATP across periods

    # Safety stock
    safety_stock = Column(Double, server_default=text("0"))
    projected_available = Column(Double, server_default=text("0"))  # On-hand minus safety stock

    # Stochastic projections (Extension)
    projected_on_hand_p10 = Column(Double)  # 10th percentile
    projected_on_hand_p50 = Column(Double)  # Median
    projected_on_hand_p90 = Column(Double)  # 90th percentile
    atp_p10 = Column(Double)
    atp_p90 = Column(Double)

    # Linkage
    supply_plan_id = Column(Integer)  # FK deferred — links to supply_plan when generated

    # Source tracking
    source = Column(String(100))  # MRP, MPS, MANUAL
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_inv_projection_lookup', 'site_id', 'product_id', 'period_start'),
        Index('idx_inv_projection_product_period', 'product_id', 'period_start'),
        UniqueConstraint('site_id', 'product_id', 'period_start', 'source', name='uq_inv_projection_unique'),
    )


# ============================================================================
# SC Entity: FulfillmentOrder
# ============================================================================

class FulfillmentOrder(Base):
    """
    Fulfillment order tracking the PICK → PACK → SHIP → DELIVER lifecycle.

    SC Entity: fulfillment_order

    Represents the execution of an outbound customer order through warehouse
    operations and delivery.

    SC Core Fields:
    - company_id, order_id, order_line_id, site_id, product_id
    - status, quantity, promised_date, ship_date, delivery_date

    Extensions:
    - wave_id: Warehouse wave grouping
    - carrier/tracking: Shipment tracking
    - priority: Fulfillment priority for allocation
    """
    __tablename__ = "fulfillment_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    fulfillment_order_id = Column(String(100), unique=True, nullable=False, index=True)

    # Order reference
    order_id = Column(String(100), nullable=False, index=True)  # Customer/outbound order ID
    order_line_id = Column(String(100))

    # Location and product
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    quantity = Column(Double, nullable=False)
    uom = Column(String(20), server_default=text("'EA'"))

    # Lifecycle status: CREATED → ALLOCATED → PICKED → PACKED → SHIPPED → DELIVERED → CLOSED
    status = Column(String(20), nullable=False, server_default=text("'CREATED'"))

    # Dates
    created_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    promised_date = Column(DateTime)
    allocated_date = Column(DateTime)
    pick_date = Column(DateTime)
    pack_date = Column(DateTime)
    ship_date = Column(DateTime)
    delivery_date = Column(DateTime)  # Actual delivery

    # Fulfillment details
    allocated_quantity = Column(Double, server_default=text("0"))
    picked_quantity = Column(Double, server_default=text("0"))
    shipped_quantity = Column(Double, server_default=text("0"))
    delivered_quantity = Column(Double, server_default=text("0"))
    short_quantity = Column(Double, server_default=text("0"))  # Unfulfilled

    # Warehouse operations (Extension)
    wave_id = Column(String(100))
    pick_location = Column(String(100))
    pack_station = Column(String(50))

    # Shipment tracking (Extension)
    carrier = Column(String(100))
    tracking_number = Column(String(200))
    ship_method = Column(String(50))  # GROUND, EXPRESS, AIR, OCEAN

    # Priority and customer (Extension)
    priority = Column(Integer, server_default=text("3"))  # 1=highest, 5=lowest
    customer_id = Column(String(100))  # FK to trading_partner

    # Source tracking
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_fulfillment_order_lookup', 'order_id', 'status'),
        Index('idx_fulfillment_site_product', 'site_id', 'product_id', 'status'),
    )


# ============================================================================
# SC Entity: ConsensusDemand
# ============================================================================

class ConsensusDemand(Base):
    """
    Consensus demand plan from S&OP process.

    SC Entity: consensus_demand

    Represents the agreed-upon demand after reconciliation between
    sales forecasts, statistical forecasts, and management adjustments.

    SC Core Fields:
    - company_id, product_id, site_id, period_start, period_end
    - statistical_forecast, sales_forecast, consensus_quantity
    - adjustment_reason, approved_by
    """
    __tablename__ = "consensus_demand"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"))
    customer_id = Column(String(100))  # Optional customer-level consensus

    # Time bucket
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(20), server_default=text("'MONTHLY'"))  # WEEKLY, MONTHLY, QUARTERLY

    # Demand components
    statistical_forecast = Column(Double)  # From forecasting engine
    sales_forecast = Column(Double)  # From sales team
    marketing_forecast = Column(Double)  # From marketing (promotions, launches)
    management_override = Column(Double)  # Executive adjustment

    # Consensus result
    consensus_quantity = Column(Double, nullable=False)  # Agreed demand
    confidence_level = Column(Double)  # 0-1 confidence in consensus

    # Probabilistic (Extension)
    consensus_p10 = Column(Double)
    consensus_p50 = Column(Double)
    consensus_p90 = Column(Double)

    # Adjustment tracking
    adjustment_reason = Column(String(500))
    adjustment_type = Column(String(50))  # PROMOTION, SEASON, NEW_PRODUCT, PHASE_OUT, EXECUTIVE
    approved_by = Column(String(100))
    approval_date = Column(DateTime)

    # S&OP cycle reference
    sop_cycle_id = Column(String(100))  # Which S&OP meeting produced this
    version = Column(Integer, server_default=text("1"))

    # Source tracking
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")

    __table_args__ = (
        Index('idx_consensus_demand_lookup', 'product_id', 'site_id', 'period_start'),
        UniqueConstraint('product_id', 'site_id', 'period_start', 'version', name='uq_consensus_demand'),
    )


# ============================================================================
# SC Entity: Backorder
# ============================================================================

class Backorder(Base):
    """
    Backorder tracking with lifecycle management.

    SC Entity: backorder

    Formalizes unfulfilled demand that was not met by available inventory.
    Each backorder is linked to the original outbound order line and tracks
    the full lifecycle: CREATED → ALLOCATED → PARTIALLY_FULFILLED → FULFILLED → CLOSED.

    Backorders are distinct from backlog_quantity on OutboundOrderLine:
    - OutboundOrderLine.backlog_quantity is a running balance
    - Backorder is a formal entity with lifecycle, priority, and aging

    SC Core Fields:
    - company_id, order_id, product_id, site_id, backorder_quantity
    - status, requested_delivery_date, expected_fill_date

    Extensions:
    - aging_days: Days since backorder creation
    - priority: Inherited from originating order
    - allocated_supply_plan_id: Link to planned supply
    """
    __tablename__ = "backorder"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    backorder_id = Column(String(100), unique=True, nullable=False, index=True)

    # Order reference
    order_id = Column(String(100), nullable=False, index=True)
    order_line_id = Column(Integer, ForeignKey("outbound_order_line.id"))

    # Product and location
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    customer_id = Column(String(100))  # FK to trading_partner

    # Quantities
    backorder_quantity = Column(Double, nullable=False)
    allocated_quantity = Column(Double, server_default=text("0"))
    fulfilled_quantity = Column(Double, server_default=text("0"))

    # Lifecycle: CREATED → ALLOCATED → PARTIALLY_FULFILLED → FULFILLED → CLOSED → CANCELLED
    status = Column(String(20), nullable=False, server_default=text("'CREATED'"))

    # Dates
    requested_delivery_date = Column(Date)
    expected_fill_date = Column(Date)  # When supply is expected
    created_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    allocated_date = Column(DateTime)
    fulfilled_date = Column(DateTime)
    closed_date = Column(DateTime)

    # Priority (Extension: inherited from originating order)
    priority = Column(Integer, server_default=text("3"))  # 1=highest, 5=lowest
    priority_code = Column(String(20), server_default=text("'STANDARD'"))

    # Aging (Extension)
    aging_days = Column(Integer, server_default=text("0"))

    # Supply linkage (Extension)
    allocated_supply_plan_id = Column(Integer)  # FK to supply_plan
    supply_commit_id = Column(Integer)  # FK to planning cascade supply commit

    # Config/scenario context
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))

    # Source tracking
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product")
    site = relationship("Site")
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_backorder_lookup', 'product_id', 'site_id', 'status'),
        Index('idx_backorder_order', 'order_id'),
        Index('idx_backorder_priority', 'priority', 'created_date'),
        Index('idx_backorder_aging', 'aging_days', 'status'),
    )


# ============================================================================
# SC Entity: FinalAssemblySchedule (FAS)
# ============================================================================

class FinalAssemblySchedule(Base):
    """
    Final Assembly Schedule for configure-to-order (CTO) and assemble-to-order (ATO) products.

    SC Entity: final_assembly_schedule

    The FAS bridges between MPS (which plans common sub-assemblies at an aggregate
    level) and customer orders that specify the exact configuration. The FAS is
    created when a customer order for a CTO/ATO product is received, and it
    schedules the final assembly operations to meet the promised delivery date.

    Key concepts:
    - MPS plans at the option/module level (e.g., "laptop base model")
    - FAS plans at the configured product level (e.g., "laptop with 16GB RAM + 1TB SSD")
    - FAS consumes MPS planned orders for common components
    - Lead time = final assembly time (typically short, 1-5 days)

    SC Core Fields:
    - company_id, product_id, site_id, order_id
    - configuration, assembly_quantity, assembly_date

    Extensions:
    - option_selections: JSON of selected options/features
    - mps_consumption: Links to MPS planned orders consumed
    """
    __tablename__ = "final_assembly_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    fas_id = Column(String(100), unique=True, nullable=False, index=True)

    # Order reference (the customer order driving FAS)
    order_id = Column(String(100), nullable=False, index=True)
    order_line_id = Column(String(100))

    # Product (the configured end-product)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    base_product_id = Column(String(100), ForeignKey("product.id"))  # MPS-planned base model
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Configuration (Extension: JSON of selected options)
    option_selections = Column(JSON)  # e.g., {"ram": "16GB", "storage": "1TB_SSD", "color": "silver"}
    configuration_code = Column(String(200))  # Encoded config string

    # Schedule
    assembly_quantity = Column(Double, nullable=False)
    assembly_start_date = Column(Date, nullable=False)
    assembly_end_date = Column(Date, nullable=False)
    promised_delivery_date = Column(Date)

    # Lead times
    assembly_lead_time_days = Column(Integer, server_default=text("1"))
    testing_lead_time_days = Column(Integer, server_default=text("0"))

    # Lifecycle: PLANNED → RELEASED → IN_PROGRESS → COMPLETED → SHIPPED → CLOSED
    status = Column(String(20), nullable=False, server_default=text("'PLANNED'"))

    # MPS consumption (Extension: which MPS orders this FAS consumes)
    mps_consumption = Column(JSON)  # [{"mps_order_id": "...", "product_id": "...", "qty": ...}]

    # BOM for final assembly (Extension: only the final-level BOM, not full explosion)
    assembly_bom = Column(JSON)  # [{"component_id": "...", "qty": ..., "available": true}]

    # Capacity
    production_process_id = Column(String(100), ForeignKey("production_process.id"))
    work_center_id = Column(String(100))
    estimated_hours = Column(Double)

    # Priority
    priority = Column(Integer, server_default=text("3"))

    # Config/scenario context
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    # Source tracking
    source = Column(String(100))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    product = relationship("Product", foreign_keys=[product_id])
    base_product = relationship("Product", foreign_keys=[base_product_id])
    site = relationship("Site")
    production_process = relationship("ProductionProcess")
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_fas_lookup', 'product_id', 'site_id', 'status'),
        Index('idx_fas_order', 'order_id'),
        Index('idx_fas_schedule', 'assembly_start_date', 'assembly_end_date'),
    )

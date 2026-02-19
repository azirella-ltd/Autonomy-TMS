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

    SIMPLIFIED for Beer Game: Single column PK instead of composite PK
    Standard model uses composite PK (id, tpartner_type, geo_id, eff_start_date, eff_end_date)
    but Beer Game doesn't need temporal tracking, so we use a surrogate key.

    Table name: trading_partners (pluralized for consistency with other Beer Game tables)
    """
    __tablename__ = "trading_partners"

    # Surrogate PK for Beer Game simplicity (allows simple foreign key references)
    _id = Column(Integer, primary_key=True, autoincrement=True)

    # Standard supply chain fields (id is now unique but not part of PK)
    id = Column(String(100), nullable=False, unique=True, index=True)  # Business key
    tpartner_type = Column(String(50), nullable=False)  # vendor, customer, 3PL, carrier
    geo_id = Column(String(100), ForeignKey("geography.id"), nullable=True)
    eff_start_date = Column(DateTime, nullable=True)  # Optional for Beer Game
    eff_end_date = Column(DateTime, nullable=True)  # Optional for Beer Game

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
# with Integer PKs for Beer Game compatibility. Import from there:
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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    priority = Column(Integer)
    unit_cost_range = Column(JSON)

    # Product hierarchy fields (for breadcrumb display)
    # Format: Category > Family > Group > Product
    category = Column(String(100), nullable=True, comment="Top-level category (e.g., Frozen, Refrigerated)")
    family = Column(String(100), nullable=True, comment="Product family (e.g., Proteins, Dairy)")
    product_group = Column(String(100), nullable=True, comment="Product group (e.g., Chicken, Beef)")

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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

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

    # Simulation extensions (Beer Game)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    round_number = Column(Integer)

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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

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
    __table_args__ = {"extend_existing": True}

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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    round_number = Column(Integer)

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

    # Beer Game extensions
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    demand_pattern = Column(JSON)  # Classic Beer Game demand patterns

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
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index('idx_reservation_lookup', 'product_id', 'site_id', 'reservation_date'),
    )


class OutboundOrderLine(Base):
    """
    Customer orders (actual demand)

    Extended for Beer Game execution with fulfillment tracking:
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
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))

    # Beer Game execution extensions
    promised_quantity = Column(Double)  # ATP-promised quantity
    shipped_quantity = Column(Double, server_default=text("0.0"), nullable=False)  # Fulfilled amount
    backlog_quantity = Column(Double, server_default=text("0.0"), nullable=False)  # Unfulfilled amount
    status = Column(String(20), server_default=text("'DRAFT'"), nullable=False)  # DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED, CANCELLED
    priority_code = Column(String(20), server_default=text("'STANDARD'"), nullable=False)  # VIP, HIGH, STANDARD, LOW
    promised_delivery_date = Column(Date)  # ATP-promised delivery date
    first_ship_date = Column(Date)  # First partial shipment date
    last_ship_date = Column(Date)  # Final shipment date
    market_demand_site_id = Column(Integer, ForeignKey("site.id"))  # Customer site (for Beer Game)

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

    __table_args__ = (
        Index('idx_shipment_status', 'status', 'expected_delivery_date'),
        Index('idx_shipment_risk', 'risk_level', 'status'),
        Index('idx_shipment_tracking', 'tracking_number', 'carrier_id'),
    )

"""
Planning Hierarchy Models for AWS Supply Chain Compliance

This module implements hierarchical planning structures aligned with AWS Supply Chain
data model and Warren B. Powell's Sequential Decision Analytics framework.

Three Dimensions of Hierarchy:
1. Geographic/Site Hierarchy: Company → Region → Country → Site
2. Product Hierarchy: Category → Family → Group → Product (SKU)
3. Time Bucket Hierarchy: Year → Quarter → Month → Week → Day → Hour

Planning Level Configuration:
- Strategic/Network Design: Monthly buckets, 2-5 year horizon, region × category
- S&OP: Monthly buckets, 18-24 month horizon, country × family
- MPS: Weekly buckets, 13-26 week horizon, site × group
- MRP/Execution: Daily/hourly buckets, 1-13 week horizon, site × SKU

Powell Framework Alignment:
- Higher hierarchy levels → CFA (Cost Function Approximation) with aggregated θ
- Lower hierarchy levels → VFA (Value Function Approximation) with detailed Q(s,a)
- Hierarchical consistency: V_lower ≈ E[V_higher | disaggregation]
"""

from enum import Enum
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Float, Double, Boolean, JSON, DateTime, Date,
    ForeignKey, UniqueConstraint, Index, Enum as SAEnum, Text
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base


# ============================================================================
# Hierarchy Level Enums
# ============================================================================

class SiteHierarchyLevel(str, Enum):
    """Geographic/Site hierarchy levels"""
    COMPANY = "company"         # Highest - entire organization
    REGION = "region"           # Geographic region (APAC, EMEA, Americas)
    COUNTRY = "country"         # Country level
    STATE = "state"             # State/Province level
    SITE = "site"               # Individual site (warehouse, factory, DC)


class ProductHierarchyLevel(str, Enum):
    """Product hierarchy levels"""
    CATEGORY = "category"       # Highest - product category (Electronics, Apparel)
    FAMILY = "family"           # Product family (Phones, Laptops)
    GROUP = "group"             # Product group (iPhone, Galaxy)
    PRODUCT = "product"         # SKU level (iPhone 15 Pro 256GB Space Black)


class TimeBucketType(str, Enum):
    """Time bucket granularity"""
    HOUR = "hour"               # Execution/ATP - 1 hour
    DAY = "day"                 # MRP/Short-term - 1 day
    WEEK = "week"               # MPS - 1 week
    MONTH = "month"             # S&OP - 1 month
    QUARTER = "quarter"         # Strategic - 3 months
    YEAR = "year"               # Long-term - 1 year


class PlanningType(str, Enum):
    """Types of planning activities"""
    EXECUTION = "execution"             # ATP/CTP, real-time decisions
    MRP = "mrp"                         # Material Requirements Planning
    MPS = "mps"                         # Master Production Scheduling
    SOP = "sop"                         # Sales & Operations Planning
    CAPACITY = "capacity"               # Capacity Planning
    INVENTORY = "inventory"             # Inventory Optimization
    NETWORK = "network"                 # Network Design / Strategic


# ============================================================================
# Planning Hierarchy Configuration
# ============================================================================

class PlanningHierarchyConfig(Base):
    """
    Configures which hierarchy levels to use for different planning types.
    This is a tenant-level configuration set by tenant administrators.

    Example configurations:
    - S&OP: site_level=COUNTRY, product_level=FAMILY, time_bucket=MONTH, horizon_months=24
    - MPS: site_level=SITE, product_level=GROUP, time_bucket=WEEK, horizon_months=6
    - Execution: site_level=SITE, product_level=PRODUCT, time_bucket=HOUR, horizon_months=1

    Powell Framework:
    - Higher levels (S&OP) → CFA parameters θ computed via SOPGraphSAGE
    - Lower levels (Execution) → VFA decisions Q(s,a) via ExecutionTemporalGNN
    """
    __tablename__ = "planning_hierarchy_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))

    # Planning type this configuration applies to
    planning_type: Mapped[PlanningType] = mapped_column(
        SAEnum(PlanningType, name="planning_type_enum"),
        nullable=False
    )

    # Site/Geographic hierarchy level for aggregation
    site_hierarchy_level: Mapped[SiteHierarchyLevel] = mapped_column(
        SAEnum(SiteHierarchyLevel, name="site_hierarchy_level_enum"),
        nullable=False,
        default=SiteHierarchyLevel.SITE
    )

    # Product hierarchy level for aggregation
    product_hierarchy_level: Mapped[ProductHierarchyLevel] = mapped_column(
        SAEnum(ProductHierarchyLevel, name="product_hierarchy_level_enum"),
        nullable=False,
        default=ProductHierarchyLevel.PRODUCT
    )

    # Time bucket configuration
    time_bucket: Mapped[TimeBucketType] = mapped_column(
        SAEnum(TimeBucketType, name="time_bucket_type_enum"),
        nullable=False,
        default=TimeBucketType.WEEK
    )

    # Planning horizon in months
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)

    # Frozen horizon in periods (no changes allowed within this window)
    frozen_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Slushy horizon in periods (changes require approval)
    slushy_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Update frequency (how often to refresh this plan)
    update_frequency_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=168)  # Weekly default

    # Powell framework settings
    # For S&OP/MPS: Use CFA (compute policy parameters)
    # For Execution: Use VFA (make real-time decisions)
    powell_policy_class: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="vfa",
        comment="Powell policy class: pfa, cfa, vfa, dla"
    )

    # GNN model configuration
    gnn_model_type: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="sop_graphsage, execution_tgnn, hybrid"
    )
    gnn_checkpoint_path: Mapped[Optional[str]] = mapped_column(String(500))

    # Hierarchical consistency settings
    # Ensures lower-level plans respect higher-level constraints
    parent_planning_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Planning type that provides constraints (e.g., S&OP constrains MPS)"
    )
    consistency_tolerance: Mapped[float] = mapped_column(
        Float,
        default=0.10,
        comment="Max deviation from parent plan (Powell hierarchical consistency)"
    )

    # Display settings
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Relationships
    tenant = relationship("Tenant")
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'planning_type', 'config_id', name='uq_planning_hierarchy_type'),
        Index('idx_planning_hierarchy_tenant', 'tenant_id', 'is_active'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "config_id": self.config_id,
            "planning_type": self.planning_type.value,
            "site_hierarchy_level": self.site_hierarchy_level.value,
            "product_hierarchy_level": self.product_hierarchy_level.value,
            "time_bucket": self.time_bucket.value,
            "horizon_months": self.horizon_months,
            "frozen_periods": self.frozen_periods,
            "slushy_periods": self.slushy_periods,
            "update_frequency_hours": self.update_frequency_hours,
            "powell_policy_class": self.powell_policy_class,
            "gnn_model_type": self.gnn_model_type,
            "parent_planning_type": self.parent_planning_type,
            "consistency_tolerance": self.consistency_tolerance,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
        }


# ============================================================================
# Site Hierarchy Extensions
# ============================================================================

class SiteHierarchyNode(Base):
    """
    Extends Geography model with explicit hierarchy levels and aggregation support.

    This provides a unified view of the site hierarchy that can be used for:
    - S&OP planning at region level
    - MPS planning at site level
    - Network design at country level

    AWS SC Alignment: Extends geography table with planning-specific attributes.
    """
    __tablename__ = "site_hierarchy_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to existing geography or site
    geography_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("geography.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))

    # Hierarchy structure
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site_hierarchy_node.id"))
    hierarchy_level: Mapped[SiteHierarchyLevel] = mapped_column(
        SAEnum(SiteHierarchyLevel, name="site_hierarchy_level_enum"),
        nullable=False
    )

    # Node identification
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Aggregation path (materialized for fast queries)
    # Format: "company_id/region_id/country_id/state_id/site_id"
    hierarchy_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Planning attributes
    is_plannable: Mapped[bool] = mapped_column(Boolean, default=True)
    default_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer)
    default_capacity: Mapped[Optional[float]] = mapped_column(Float)

    # GNN node features (cached for performance)
    gnn_node_features: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("SiteHierarchyNode", remote_side=[id], backref="children")
    geography = relationship("Geography")
    site = relationship("Site")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('idx_site_hierarchy_path', 'hierarchy_path'),
        Index('idx_site_hierarchy_level', 'hierarchy_level', 'tenant_id'),
    )


# ============================================================================
# Product Hierarchy Extensions
# ============================================================================

class ProductHierarchyNode(Base):
    """
    Extends ProductHierarchy with explicit levels and aggregation support.

    This provides a unified view of the product hierarchy that can be used for:
    - S&OP planning at family level
    - MPS planning at group level
    - MRP/Execution at SKU level

    AWS SC Alignment: Extends product_hierarchy table with planning-specific attributes.
    """
    __tablename__ = "product_hierarchy_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to existing product hierarchy or product
    product_hierarchy_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product_hierarchy.id"))
    product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))

    # Hierarchy structure
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("product_hierarchy_node.id"))
    hierarchy_level: Mapped[ProductHierarchyLevel] = mapped_column(
        SAEnum(ProductHierarchyLevel, name="product_hierarchy_level_enum"),
        nullable=False
    )

    # Node identification
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Aggregation path (materialized for fast queries)
    # Format: "category_id/family_id/group_id/product_id"
    hierarchy_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Planning attributes
    is_plannable: Mapped[bool] = mapped_column(Boolean, default=True)
    default_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer)
    base_demand_pattern: Mapped[Optional[str]] = mapped_column(String(50))  # constant, seasonal, trending

    # Aggregation factors for demand disaggregation
    demand_split_factors: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="How to split parent demand to children: {child_id: split_ratio}"
    )

    # GNN node features (cached for performance)
    gnn_node_features: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("ProductHierarchyNode", remote_side=[id], backref="children")
    product_hierarchy = relationship("ProductHierarchy")
    product = relationship("Product")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('idx_product_hierarchy_path', 'hierarchy_path'),
        Index('idx_product_hierarchy_level', 'hierarchy_level', 'tenant_id'),
    )


# ============================================================================
# Time Bucket Configuration
# ============================================================================

class TimeBucketConfig(Base):
    """
    Configures time bucket hierarchies for planning.

    Time buckets define how planning periods are structured:
    - Execution: Hourly buckets for ATP/CTP
    - MRP: Daily buckets for detailed planning
    - MPS: Weekly buckets for production scheduling
    - S&OP: Monthly buckets for strategic planning

    Supports fiscal calendars and custom period definitions.
    """
    __tablename__ = "time_bucket_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Bucket type
    bucket_type: Mapped[TimeBucketType] = mapped_column(
        SAEnum(TimeBucketType, name="time_bucket_type_enum"),
        nullable=False
    )

    # Calendar configuration
    calendar_type: Mapped[str] = mapped_column(
        String(50),
        default="gregorian",
        comment="gregorian, fiscal_445, fiscal_454, custom"
    )

    # Fiscal year settings (if applicable)
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)  # 1=January
    fiscal_year_start_day: Mapped[int] = mapped_column(Integer, default=1)

    # Week configuration
    week_start_day: Mapped[int] = mapped_column(Integer, default=1)  # 1=Monday, 7=Sunday

    # Custom period definitions (for irregular calendars)
    custom_periods: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Custom period definitions for non-standard calendars"
    )

    # Display settings
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'bucket_type', name='uq_time_bucket_type'),
    )


# ============================================================================
# Planning Horizon Definitions
# ============================================================================

class PlanningHorizonTemplate(Base):
    """
    Pre-defined planning horizon templates that can be applied to planning configurations.

    Common templates:
    - EXECUTION: 1 week horizon, hourly buckets, SKU × Site
    - MRP: 13 weeks horizon, daily buckets, SKU × Site
    - MPS: 26 weeks horizon, weekly buckets, Group × Site
    - S&OP: 24 months horizon, monthly buckets, Family × Country
    - STRATEGIC: 5 years horizon, quarterly buckets, Category × Region

    Powell Framework:
    - Shorter horizons → VFA (real-time decisions)
    - Longer horizons → CFA (policy parameters) + DLA (lookahead)
    """
    __tablename__ = "planning_horizon_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Template identification
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Planning type this template is designed for
    planning_type: Mapped[PlanningType] = mapped_column(
        SAEnum(PlanningType, name="planning_type_enum"),
        nullable=False
    )

    # Hierarchy levels
    site_hierarchy_level: Mapped[SiteHierarchyLevel] = mapped_column(
        SAEnum(SiteHierarchyLevel, name="site_hierarchy_level_enum"),
        nullable=False
    )
    product_hierarchy_level: Mapped[ProductHierarchyLevel] = mapped_column(
        SAEnum(ProductHierarchyLevel, name="product_hierarchy_level_enum"),
        nullable=False
    )

    # Time configuration
    time_bucket: Mapped[TimeBucketType] = mapped_column(
        SAEnum(TimeBucketType, name="time_bucket_type_enum"),
        nullable=False
    )
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_periods: Mapped[int] = mapped_column(Integer, default=0)
    slushy_periods: Mapped[int] = mapped_column(Integer, default=0)

    # Update frequency
    update_frequency_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    # Powell settings
    powell_policy_class: Mapped[str] = mapped_column(String(20), nullable=False)
    gnn_model_type: Mapped[Optional[str]] = mapped_column(String(50))

    # Hierarchical relationship
    parent_template_code: Mapped[Optional[str]] = mapped_column(String(50))
    consistency_tolerance: Mapped[float] = mapped_column(Float, default=0.10)

    # System template (not editable by users)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================================
# Aggregated Plan Storage
# ============================================================================

class AggregatedPlan(Base):
    """
    Stores plans at aggregated hierarchy levels.

    When planning at FAMILY × COUNTRY level, we need to:
    1. Aggregate SKU-level demand to family level
    2. Generate plan at family level
    3. Disaggregate back to SKU level for execution

    This table stores the intermediate aggregated plans.

    Powell Framework:
    - CFA θ parameters are computed at this level
    - Lower-level VFA decisions must respect these aggregated constraints
    """
    __tablename__ = "aggregated_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Plan identification
    plan_id: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)

    # Hierarchy references
    planning_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("planning_hierarchy_config.id"))
    site_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("site_hierarchy_node.id"))
    product_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_hierarchy_node.id"))

    # Time period
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    bucket_type: Mapped[TimeBucketType] = mapped_column(
        SAEnum(TimeBucketType, name="time_bucket_type_enum"),
        nullable=False
    )

    # Plan quantities (aggregated)
    demand_quantity: Mapped[float] = mapped_column(Double, default=0)
    supply_quantity: Mapped[float] = mapped_column(Double, default=0)
    production_quantity: Mapped[float] = mapped_column(Double, default=0)
    inventory_target: Mapped[float] = mapped_column(Double, default=0)

    # Statistical measures (for aggregated demand)
    demand_mean: Mapped[Optional[float]] = mapped_column(Double)
    demand_std: Mapped[Optional[float]] = mapped_column(Double)
    demand_p10: Mapped[Optional[float]] = mapped_column(Double)
    demand_p50: Mapped[Optional[float]] = mapped_column(Double)
    demand_p90: Mapped[Optional[float]] = mapped_column(Double)

    # Powell CFA parameters (θ) computed by S&OP GraphSAGE
    safety_stock_multiplier: Mapped[Optional[float]] = mapped_column(Double)
    criticality_score: Mapped[Optional[float]] = mapped_column(Double)
    bottleneck_risk: Mapped[Optional[float]] = mapped_column(Double)
    concentration_risk: Mapped[Optional[float]] = mapped_column(Double)

    # GNN embeddings (cached structural embeddings from S&OP model)
    gnn_structural_embedding: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft, approved, executed
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Ownership
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    planning_config = relationship("PlanningHierarchyConfig")
    site_node = relationship("SiteHierarchyNode")
    product_node = relationship("ProductHierarchyNode")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('idx_aggregated_plan_period', 'plan_id', 'period_start', 'period_end'),
        Index('idx_aggregated_plan_hierarchy', 'site_node_id', 'product_node_id', 'period_start'),
    )


# ============================================================================
# Default Templates
# ============================================================================

DEFAULT_PLANNING_TEMPLATES = [
    {
        "code": "EXECUTION",
        "name": "Real-time Execution",
        "description": "ATP/CTP real-time order promising with hourly granularity",
        "planning_type": PlanningType.EXECUTION,
        "site_hierarchy_level": SiteHierarchyLevel.SITE,
        "product_hierarchy_level": ProductHierarchyLevel.PRODUCT,
        "time_bucket": TimeBucketType.HOUR,
        "horizon_months": 1,
        "frozen_periods": 0,
        "slushy_periods": 0,
        "update_frequency_hours": 1,
        "powell_policy_class": "vfa",
        "gnn_model_type": "execution_tgnn",
        "parent_template_code": "MRP",
        "consistency_tolerance": 0.05,
        "is_system": True,
    },
    {
        "code": "MRP",
        "name": "Material Requirements Planning",
        "description": "Daily MRP with 13-week horizon for detailed component planning",
        "planning_type": PlanningType.MRP,
        "site_hierarchy_level": SiteHierarchyLevel.SITE,
        "product_hierarchy_level": ProductHierarchyLevel.PRODUCT,
        "time_bucket": TimeBucketType.DAY,
        "horizon_months": 3,
        "frozen_periods": 7,  # 1 week frozen
        "slushy_periods": 14,  # 2 weeks slushy
        "update_frequency_hours": 24,
        "powell_policy_class": "vfa",
        "gnn_model_type": "execution_tgnn",
        "parent_template_code": "MPS",
        "consistency_tolerance": 0.08,
        "is_system": True,
    },
    {
        "code": "MPS",
        "name": "Master Production Scheduling",
        "description": "Weekly MPS with 6-month horizon for production scheduling",
        "planning_type": PlanningType.MPS,
        "site_hierarchy_level": SiteHierarchyLevel.SITE,
        "product_hierarchy_level": ProductHierarchyLevel.GROUP,
        "time_bucket": TimeBucketType.WEEK,
        "horizon_months": 6,
        "frozen_periods": 4,  # 4 weeks frozen
        "slushy_periods": 8,  # 8 weeks slushy
        "update_frequency_hours": 168,  # Weekly
        "powell_policy_class": "cfa",
        "gnn_model_type": "hybrid",
        "parent_template_code": "SOP",
        "consistency_tolerance": 0.10,
        "is_system": True,
    },
    {
        "code": "SOP",
        "name": "Sales & Operations Planning",
        "description": "Monthly S&OP with 24-month horizon for demand-supply balancing",
        "planning_type": PlanningType.SOP,
        "site_hierarchy_level": SiteHierarchyLevel.COUNTRY,
        "product_hierarchy_level": ProductHierarchyLevel.FAMILY,
        "time_bucket": TimeBucketType.MONTH,
        "horizon_months": 24,
        "frozen_periods": 3,  # 3 months frozen
        "slushy_periods": 6,  # 6 months slushy
        "update_frequency_hours": 720,  # Monthly
        "powell_policy_class": "cfa",
        "gnn_model_type": "sop_graphsage",
        "parent_template_code": "STRATEGIC",
        "consistency_tolerance": 0.15,
        "is_system": True,
    },
    {
        "code": "CAPACITY",
        "name": "Capacity Planning",
        "description": "Monthly capacity planning with resource leveling",
        "planning_type": PlanningType.CAPACITY,
        "site_hierarchy_level": SiteHierarchyLevel.SITE,
        "product_hierarchy_level": ProductHierarchyLevel.GROUP,
        "time_bucket": TimeBucketType.MONTH,
        "horizon_months": 18,
        "frozen_periods": 1,
        "slushy_periods": 3,
        "update_frequency_hours": 720,
        "powell_policy_class": "cfa",
        "gnn_model_type": "sop_graphsage",
        "parent_template_code": "SOP",
        "consistency_tolerance": 0.10,
        "is_system": True,
    },
    {
        "code": "INVENTORY",
        "name": "Inventory Optimization",
        "description": "Monthly inventory target setting and safety stock optimization",
        "planning_type": PlanningType.INVENTORY,
        "site_hierarchy_level": SiteHierarchyLevel.SITE,
        "product_hierarchy_level": ProductHierarchyLevel.GROUP,
        "time_bucket": TimeBucketType.MONTH,
        "horizon_months": 12,
        "frozen_periods": 0,
        "slushy_periods": 3,
        "update_frequency_hours": 720,
        "powell_policy_class": "cfa",
        "gnn_model_type": "sop_graphsage",
        "parent_template_code": "SOP",
        "consistency_tolerance": 0.12,
        "is_system": True,
    },
    {
        "code": "STRATEGIC",
        "name": "Strategic Planning / Network Design",
        "description": "Quarterly strategic planning with 5-year horizon for network design",
        "planning_type": PlanningType.NETWORK,
        "site_hierarchy_level": SiteHierarchyLevel.REGION,
        "product_hierarchy_level": ProductHierarchyLevel.CATEGORY,
        "time_bucket": TimeBucketType.QUARTER,
        "horizon_months": 60,  # 5 years
        "frozen_periods": 2,  # 2 quarters frozen
        "slushy_periods": 4,  # 1 year slushy
        "update_frequency_hours": 2160,  # Quarterly
        "powell_policy_class": "dla",  # Direct lookahead for strategic
        "gnn_model_type": "sop_graphsage",
        "parent_template_code": None,
        "consistency_tolerance": 0.20,
        "is_system": True,
    },
]

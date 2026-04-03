from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Enum,
    JSON,
    Boolean,
    UniqueConstraint,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr
from enum import Enum as PyEnum
from typing import Optional, TYPE_CHECKING
import datetime
from .base import Base
from app.core.time_buckets import TimeBucket

if TYPE_CHECKING:
    from .tenant import Tenant
    from .scenario import Scenario
    from .sc_entities import Product, TradingPartner

class NodeType(str, PyEnum):
    # AWS SC DM internal site types
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"
    WAREHOUSE = "WAREHOUSE"
    MANUFACTURING_PLANT = "MANUFACTURING_PLANT"
    INVENTORY = "INVENTORY"           # generic inventory site
    MANUFACTURER = "MANUFACTURER"     # generic manufacturer site
    SUPPLIER = "SUPPLIER"
    # External trading partners — represented by TradingPartner records, not internal sites.
    # These values are retained for backward compatibility with existing DB rows during migration.
    # New code must use Site.is_external=True + Site.trading_partner_id instead.
    VENDOR = "VENDOR"       # replaces VENDOR
    CUSTOMER = "CUSTOMER"   # replaces CUSTOMER
    # Legacy TBG types — retained for backward compatibility with existing DB rows.
    # New configs should use DISTRIBUTION_CENTER, WAREHOUSE, MANUFACTURING_PLANT.
    RETAILER = "RETAILER"
    WHOLESALER = "WHOLESALER"
    DISTRIBUTOR = "DISTRIBUTOR"

def _default_site_type_definitions() -> list:
    """Return the default ordered list of site type definitions.

    External parties (vendors and customers) are represented by TradingPartner records
    linked via Site.trading_partner_id on is_external=True site entries.
    """
    return [
        {
            "type": NodeType.CUSTOMER.value,
            "label": "Customer",
            "order": 0,
            "is_required": True,
            "is_external": True,
            "tpartner_type": "customer",
        },
        {
            "type": "DISTRIBUTION_CENTER",
            "label": "Distribution Center",
            "order": 1,
            "is_required": False,
            "is_external": False,
            "master_type": "inventory",
        },
        {
            "type": "WAREHOUSE",
            "label": "Warehouse",
            "order": 2,
            "is_required": False,
            "is_external": False,
            "master_type": "inventory",
        },
        {
            "type": "MANUFACTURING_PLANT",
            "label": "Manufacturing Plant",
            "order": 3,
            "is_required": False,
            "is_external": False,
            "master_type": "manufacturer",
        },
        {
            "type": NodeType.VENDOR.value,
            "label": "Vendor",
            "order": 4,
            "is_required": True,
            "is_external": True,
            "tpartner_type": "vendor",
        },
    ]


class SupplyChainConfig(Base):
    """Core configuration for the supply chain"""
    __tablename__ = "supply_chain_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="Default Configuration")
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    time_bucket = Column(Enum(TimeBucket, name="timebucket"), nullable=False, default=TimeBucket.WEEK)

    # Scenario Branching Fields (git-like configuration inheritance)
    parent_config_id = Column(Integer, ForeignKey('supply_chain_configs.id', ondelete='SET NULL'), nullable=True)
    base_config_id = Column(Integer, ForeignKey('supply_chain_configs.id', ondelete='SET NULL'), nullable=True)
    scenario_type = Column(String(20), nullable=False, default='BASELINE')  # BASELINE, WORKING, SIMULATION
    uses_delta_storage = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    snapshot_data = Column(JSON, nullable=True)  # Full snapshot for materialized configs
    attributes = Column(JSON, nullable=True, default=dict)  # Flexible metadata (build state, extraction audit, etc.)
    branched_at = Column(DateTime, nullable=True)
    committed_at = Column(DateTime, nullable=True)

    # Relationships
    # NOTE: items relationship removed - use Product table from sc_entities instead
    sites = relationship("Site", back_populates="config", cascade="all, delete-orphan")
    transportation_lanes = relationship("TransportationLane", back_populates="config", cascade="all, delete-orphan")
    # markets and market_demands relationships removed — tables dropped (TBG legacy)
    # Demand data now comes from Forecast table (AWS SC DM)
    tenant = relationship("Tenant", back_populates="supply_chain_configs")
    # Scenarios using this configuration
    scenarios = relationship(
        "Scenario",
        back_populates="supply_chain_config",
        passive_deletes=True,
    )
    risk_alerts = relationship(
        "RiskAlert",
        back_populates="config",
        cascade="all, delete-orphan"
    )
    # NOTE: monte_carlo_runs relationship temporarily commented out due to circular import
    # Access via: db.query(MonteCarloRun).filter_by(supply_chain_config_id=config.id)
    # monte_carlo_runs = relationship(
    #     "MonteCarloRun",
    #     back_populates="supply_chain_config",
    #     cascade="all, delete-orphan"
    # )

    # Config-level operating mode: 'production' or 'learning'
    # Mirrors the tenant mode for configs that belong to the tenant, or 'learning'
    # for learning configs that have been migrated to a production tenant.
    mode = Column(String(20), nullable=False, default='production')

    # Validation metadata
    validation_status = Column(String(20), nullable=False, default="unchecked")  # unchecked, valid, invalid
    validation_errors = Column(JSON, nullable=True)  # List of validation error messages
    validated_at = Column(DateTime, nullable=True)

    # Gartner SCOR metric hierarchy configuration (per-config overrides)
    # Resolved via app.models.metrics_hierarchy.get_metric_config(metric_config)
    # Keys: sop_weights, tgnn_weights, trm_weights — all optional (defaults used when absent)
    metric_config = Column(
        JSON,
        nullable=True,
        comment="Gartner SCOR metric config overrides. Keys: sop_weights, tgnn_weights, trm_weights.",
    )

    # Stochastic pipeline configuration (per-config tuning)
    # Surfaced in admin UI; controls SAP extraction thresholds and distribution fitting.
    # Keys: min_observations (int), min_rows_sufficiency (int),
    #        fit_threshold_cv (float), default_distribution_type (str)
    stochastic_config = Column(
        JSON,
        nullable=True,
        comment="Stochastic pipeline tuning: min_observations, min_rows_sufficiency, etc.",
    )

    # Training metadata
    needs_training = Column(Boolean, nullable=False, default=True)
    training_status = Column(String(50), nullable=False, default="pending")
    trained_at = Column(DateTime, nullable=True)
    trained_model_path = Column(String(255), nullable=True)
    last_trained_config_hash = Column(String(128), nullable=True)
    site_type_definitions = Column(
        JSON,
        nullable=False,
        default=_default_site_type_definitions,
    )

    training_artifacts = relationship(
        "SupplyChainTrainingArtifact",
        back_populates="config",
        cascade="all, delete-orphan",
    )
    mps_plans = relationship(
        "MPSPlan",
        back_populates="supply_chain_config",
        cascade="all, delete-orphan",
    )
    capacity_plans = relationship(
        "CapacityPlan",
        back_populates="supply_chain_config",
        cascade="all, delete-orphan",
    )

    # Scenario Branching Relationships
    parent_config = relationship(
        "SupplyChainConfig",
        remote_side=[id],
        foreign_keys=[parent_config_id],
        backref="child_configs"
    )
    base_config = relationship(
        "SupplyChainConfig",
        remote_side=[id],
        foreign_keys=[base_config_id],
        backref="branched_configs"
    )
    deltas = relationship(
        "ConfigDelta",
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="ConfigDelta.created_at"
    )
    lineage = relationship(
        "ConfigLineage",
        foreign_keys="ConfigLineage.config_id",
        cascade="all, delete-orphan"
    )

# =============================================================================
# REMOVED: Item class - migrated to Product table in sc_entities.py
# Use app.models.sc_entities.Product instead (SC compliant with String PK)
# =============================================================================
# class Item(Base):
#     """Products in the supply chain"""
#     __tablename__ = "items"
#
#     id = Column(Integer, primary_key=True, index=True)
#     config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
#     name = Column(String(100), nullable=False)
#     description = Column(String(500))
#     priority = Column(Integer, nullable=True)
#     unit_cost_range = Column(JSON, default={"min": 0, "max": 100})
#     product_group_id = Column(String(100), nullable=True)
#     config = relationship("SupplyChainConfig", back_populates="items")
#     node_configs = relationship("ItemNodeConfig", back_populates="item", cascade="all, delete-orphan")
# =============================================================================

class Site(Base):
    """AWS SC DM: Sites in the supply chain.

    Internal sites (is_external=False): company-controlled locations — warehouses, factories,
    distribution centres, retail stores. These are planned and managed by Autonomy.

    External sites (is_external=True): network endpoints representing TradingPartner entities
    (vendors or customers) that are outside the company's authority. Each external site carries
    a mandatory trading_partner_id FK linking it to the corresponding TradingPartner record.
    The tpartner_type field mirrors TradingPartner.tpartner_type for fast filtering without a JOIN.

    Note: external site rows are transitional proxy records that allow DAG lane connectivity
    to work while planning logic migrates to direct TradingPartner references.
    """
    __tablename__ = "site"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(100), nullable=False)
    # DAG identity (e.g., retailer, wholesaler, distributor)
    dag_type = Column(String(100), nullable=True)
    # Master processing type for internal sites: "inventory", "manufacturer"
    # For external sites this is None — use tpartner_type instead.
    master_type = Column(String(100), nullable=True)

    # External party flags (Phase 1 of Site/TradingPartner refactor)
    # is_external=True marks vendor/customer network endpoints (was VENDOR/CUSTOMER).
    is_external = Column(Boolean, nullable=False, default=False)
    # FK to TradingPartner._id — mandatory when is_external=True.
    trading_partner_id = Column(Integer, ForeignKey("trading_partners._id"), nullable=True)
    # Mirrors TradingPartner.tpartner_type for fast filtering: "vendor" or "customer".
    # Only set when is_external=True.
    tpartner_type = Column(String(50), nullable=True)

    priority = Column(Integer, nullable=True)
    order_aging = Column(Integer, nullable=False, default=0)
    lost_sale_cost = Column(Float, nullable=True)
    attributes = Column(JSON, default=dict)  # Flexible metadata per node type

    # Geographic coordinates (WGS84)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # SC Hierarchical fields
    geo_id = Column(String(100), ForeignKey("geography.id"), nullable=True)  # Geographic region
    segment_id = Column(String(100), nullable=True)  # Market segment
    company_id = Column(String(100), ForeignKey("company.id"), nullable=True)  # Company/organization

    # Relationships
    config = relationship("SupplyChainConfig", back_populates="sites")
    company = relationship("Company", back_populates="sites")
    geography = relationship("Geography", back_populates="sites")
    trading_partner = relationship("TradingPartner", foreign_keys=[trading_partner_id])
    upstream_lanes = relationship("TransportationLane", foreign_keys="TransportationLane.to_site_id", back_populates="downstream_site")
    downstream_lanes = relationship("TransportationLane", foreign_keys="TransportationLane.from_site_id", back_populates="upstream_site")
    # SC Planning relationships (from sc_entities.py)
    inv_policies = relationship("InvPolicy", back_populates="site")
    inv_levels = relationship("InvLevel", back_populates="site")

def _default_supply_lead_time() -> dict:
    return {"type": "deterministic", "value": 1}
def _default_demand_lead_time() -> dict:
    return {"type": "deterministic", "value": 1}


class TransportationLane(Base):
    """AWS SC DM: Transportation lanes in the supply chain network.

    A lane connects two network endpoints. Each endpoint is either an internal Site
    (site_id columns) or an external TradingPartner (partner_id columns).
    Exactly one of (from_site_id, from_partner_id) must be set; same for the to-side.

    Internal-to-internal:  from_site_id + to_site_id          (transfer order)
    Vendor-to-internal:    from_partner_id + to_site_id        (purchase order / inbound)
    Internal-to-customer:  from_site_id + to_partner_id        (fulfillment / outbound)
    """
    __tablename__ = "transportation_lane"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)

    # Internal-site endpoints (nullable — external lanes use partner FKs instead)
    from_site_id = Column(Integer, ForeignKey("site.id"), nullable=True)
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=True)

    # External trading-partner endpoints (nullable — internal lanes use site FKs instead)
    from_partner_id = Column(Integer, ForeignKey("trading_partners._id"), nullable=True)
    to_partner_id = Column(Integer, ForeignKey("trading_partners._id"), nullable=True)

    # Capacity in units per day
    capacity = Column(Integer, nullable=False)

    # Deprecated classic lead time range retained for backwards compatibility
    lead_time_days = Column(JSON, default={"min": 1, "max": 5})

    # Information flow lead time (orders moving upstream)
    demand_lead_time = Column(JSON, default=_default_demand_lead_time)

    # Material flow lead time (shipments moving downstream)
    # For vendor lanes: prefer VendorLeadTime records over this value.
    supply_lead_time = Column(JSON, default=_default_supply_lead_time)

    # Stochastic lead time distribution parameters (JSON)
    # NULL = use deterministic value from base field
    # Format: {"type": "normal|lognormal|triangular|...", "mean": 7, "stddev": 1.5, "min": 3, "max": 12}
    supply_lead_time_dist = Column(JSON, nullable=True)
    demand_lead_time_dist = Column(JSON, nullable=True)

    # Relationships
    config = relationship("SupplyChainConfig", back_populates="transportation_lanes")
    upstream_site = relationship("Site", foreign_keys=[from_site_id], back_populates="downstream_lanes")
    downstream_site = relationship("Site", foreign_keys=[to_site_id], back_populates="upstream_lanes")
    upstream_partner = relationship("TradingPartner", foreign_keys=[from_partner_id])
    downstream_partner = relationship("TradingPartner", foreign_keys=[to_partner_id])

    # Unique constraint covers all four endpoint columns (NULLs are distinct in Postgres)
    __table_args__ = (
        UniqueConstraint('from_site_id', 'to_site_id', 'from_partner_id', 'to_partner_id',
                         name='_lane_endpoints_uc'),
    )

# ProductSiteConfig merged into InvPolicy (see sc_entities.py)
# Migration: 20260211_merge_item_node_configs_into_inv_policy.py


class MarketDemand(Base):
    """Demand pattern configuration per product per customer (TradingPartner).

    Replaces the old market_id FK with trading_partner_id pointing to a
    TradingPartner record with tpartner_type='customer'.  The legacy market_id
    column is retained as nullable during migration; new rows must use
    trading_partner_id.
    """
    __tablename__ = "market_demands"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # Phase 4: TradingPartner(customer) replaces Market as the demand-owner entity.
    # New rows must set trading_partner_id.  Legacy rows that still reference
    # market_id are migrated by 20260311_site_trading_partner_refactor.py.
    trading_partner_id = Column(Integer, ForeignKey("trading_partners._id"), nullable=True)
    # Deprecated: retained for migration compatibility only — prefer trading_partner_id.
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=True)

    # Demand pattern configuration
    demand_pattern = Column(JSON, default={
        "demand_type": "classic",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
        "params": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
    })

    # Relationships
    config = relationship("SupplyChainConfig")
    product = relationship("Product")
    trading_partner = relationship("TradingPartner", foreign_keys=[trading_partner_id])
    market = relationship("Market")


class Market(Base):
    """DEPRECATED: Demand pools replaced by TradingPartner(tpartner_type='customer').

    Retained for migration compatibility.  All new demand owners must be
    TradingPartner records, not Market rows.  This table will be dropped once
    all market_demands.market_id references are migrated to trading_partner_id.
    """

    __tablename__ = "markets"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    company = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("config_id", "name", name="uq_market_name_per_config"),
    )

    # Relationships
    config = relationship("SupplyChainConfig")
    demands = relationship("MarketDemand", cascade="all, delete-orphan")


class SupplyChainTrainingArtifact(Base):
    """Records the generated dataset and trained model for a supply chain configuration."""

    __tablename__ = "supply_chain_training_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    dataset_name = Column(String(255), nullable=False)
    model_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    config = relationship("SupplyChainConfig", back_populates="training_artifacts")


class ConfigDelta(Base):
    """
    Stores incremental changes (deltas) for supply chain configurations.

    Enables git-like scenario branching with copy-on-write semantics:
    - create: New entity added in child config
    - update: Entity modified from parent config
    - delete: Entity removed from parent config

    Delta data structure:
    - For create: Full entity data
    - For update: Only changed fields + entity ID
    - For delete: Entity ID only
    """
    __tablename__ = "config_deltas"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Entity being changed
    entity_type = Column(String(30), nullable=False)  # node, lane, market_demand, bom, item, config
    entity_id = Column(Integer, nullable=True)  # NULL for create operations (ID not yet assigned)

    # Operation type
    operation = Column(String(10), nullable=False)  # create, update, delete

    # Delta data (JSON)
    delta_data = Column(JSON, nullable=False)  # Full data for create, partial for update, minimal for delete

    # For update operations: store only changed fields
    changed_fields = Column(JSON, nullable=True)  # List of field names that changed

    # Original values for rollback (update/delete only)
    original_values = Column(JSON, nullable=True)  # Full original entity data for rollback

    # Audit fields
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    created_by = Column(String(36), nullable=True)
    description = Column(String(500), nullable=True)  # Human-readable description of change

    # Relationships
    config = relationship("SupplyChainConfig", back_populates="deltas")


class ConfigLineage(Base):
    """
    Stores the ancestor tree for supply chain configurations.

    Enables efficient ancestor queries for delta merging:
    - depth=0: Self reference (config points to itself)
    - depth=1: Direct parent
    - depth=2: Grandparent
    - depth=N: Nth generation ancestor

    Example:
    TBG Root (id=1)
    ├─ Case TBG (id=2, parent=1)
    │  └─ Six-Pack TBG (id=3, parent=2)

    Lineage for Six-Pack TBG (id=3):
    - (3, 3, 0) - self
    - (3, 2, 1) - parent (Case TBG)
    - (3, 1, 2) - grandparent (TBG Root)
    """
    __tablename__ = "config_lineage"

    # Override Base class id column
    id = None

    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), primary_key=True)
    ancestor_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), primary_key=True)
    depth = Column(Integer, primary_key=True, nullable=False)  # 0=self, 1=parent, 2=grandparent, etc.

    # Relationships
    # Note: No back_populates to avoid circular reference complexity
    # Access via: db.query(ConfigLineage).filter_by(config_id=X)


class DecisionProposal(Base):
    """
    Decision proposals for approval workflows.

    Enables agents and humans to propose actions that require approval,
    simulate impact in child scenarios, and present business cases.

    Use Cases:
    1. Strategic scenario-based proposals:
       - Network redesign, acquisition scenarios, operating model changes
       - Uses scenario_id for simulation linkage

    2. Operational simulation-based override proposals (Phase 2 Copilot Mode):
       - Override of agent recommendations in supply chain simulation
       - Uses alternative_id for simulation linkage, decision_type for override type
       - metadata stores scenario user context (scenario_user_id, role, period, quantities)

    Examples:
    - Strategic: Network redesign, acquisition scenarios, operating model changes
    - Tactical: Safety stock adjustments, sourcing rule changes, capacity expansions
    - Operational: Expedite requests, emergency purchases, allocation overrides
    """
    __tablename__ = "decision_proposals"

    id = Column(Integer, primary_key=True, index=True)

    # Scenario linkage (child scenario created for simulation)
    # Nullable for game-based override proposals that don't use scenarios
    scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True)
    parent_scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)

    # Proposal metadata
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    proposed_by = Column(String(100), nullable=True)  # User ID or Agent ID (legacy)
    proposed_by_type = Column(String(20), nullable=True)  # 'human' or 'agent' (legacy)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # User who created

    # Action details
    action_type = Column(String(50), nullable=True)  # 'expedite', 'increase_safety_stock', etc.
    decision_type = Column(String(50), nullable=True)  # 'override_fulfillment', 'override_replenishment'
    action_params = Column(JSON, nullable=True)  # Action-specific parameters
    proposal_metadata = Column(JSON, nullable=True)  # Flexible metadata (player context, quantities, etc.)

    # Authority and approval
    authority_level_required = Column(String(50), nullable=True)  # 'manager', 'director', 'vp'
    requires_approval_from = Column(String(100), nullable=True)  # User ID or role
    status = Column(String(20), nullable=False, default='pending')  # pending, approved, rejected, executed

    # Business case (calculated from scenario simulation)
    business_case = Column(JSON, nullable=True)

    # Impact metrics (from scenario comparison)
    financial_impact = Column(JSON, nullable=True)  # total_cost, revenue, roi with P10/P50/P90
    operational_impact = Column(JSON, nullable=True)  # otif, fill_rate, inventory_turns
    strategic_impact = Column(JSON, nullable=True)  # flexibility, supplier_reliability, co2
    risk_metrics = Column(JSON, nullable=True)  # risk distributions

    # Approval tracking
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(1000), nullable=True)

    # Audit fields
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    # Relationships
    scenario = relationship("SupplyChainConfig", foreign_keys=[scenario_id], backref="proposals")
    parent_scenario = relationship("SupplyChainConfig", foreign_keys=[parent_scenario_id])
    impact_snapshots = relationship("BusinessImpactSnapshot", back_populates="proposal", cascade="all, delete-orphan")


class AuthorityDefinition(Base):
    """
    Defines authority levels for agents and humans.

    Specifies which actions require approval and from whom.
    Supports hierarchical overrides: Agent-specific > Role-based > Config-wide > Tenant-wide
    """
    __tablename__ = "authority_definitions"

    id = Column(Integer, primary_key=True, index=True)

    # Scope
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=True)

    # Agent/User scope
    agent_id = Column(String(100), nullable=True)  # Specific agent
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    role = Column(String(50), nullable=True)  # Role-based (e.g., 'planner', 'manager')

    # Authority details
    action_type = Column(String(50), nullable=False)
    max_value = Column(Float, nullable=True)  # Monetary or quantity threshold
    requires_approval = Column(Boolean, nullable=False, default=True)
    approval_authority = Column(String(50), nullable=True)  # Required authority level

    # Constraints
    conditions = Column(JSON, nullable=True)  # Additional conditions

    # Audit
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    config = relationship("SupplyChainConfig")


class BusinessImpactSnapshot(Base):
    """
    Stores computed business impact metrics for decision proposals.

    Contains probabilistic balanced scorecard metrics computed from
    scenario simulation (parent vs child comparison).
    """
    __tablename__ = "business_impact_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    # Linkage
    proposal_id = Column(Integer, ForeignKey("decision_proposals.id", ondelete="CASCADE"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Snapshot metadata
    snapshot_type = Column(String(20), nullable=False)  # 'before', 'after', 'comparison'
    planning_horizon = Column(Integer, nullable=False)  # Weeks simulated
    simulation_runs = Column(Integer, nullable=True)  # Number of Monte Carlo runs

    # Probabilistic Balanced Scorecard
    financial_metrics = Column(JSON, nullable=False)  # total_cost, revenue, roi with P10/P50/P90
    customer_metrics = Column(JSON, nullable=False)  # otif, fill_rate, backlog with distributions
    operational_metrics = Column(JSON, nullable=False)  # inventory_turns, dos, cycle_time
    strategic_metrics = Column(JSON, nullable=False)  # flexibility, supplier_reliability, co2

    # Computed at
    computed_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    # Relationships
    proposal = relationship("DecisionProposal", back_populates="impact_snapshots")
    scenario = relationship("SupplyChainConfig")


# =============================================================================
# Backward compatibility alias (DEPRECATED - use TransportationLane)
# =============================================================================
Lane = TransportationLane  # DEPRECATED: Use TransportationLane

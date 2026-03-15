"""
Synthetic Data Generator for Supply Chain Planning

Generates realistic synthetic data for testing planning and execution capabilities.
Supports three primary company archetypes:

1. RETAILER: Multi-channel retail operations
   - No manufacturing, buys FG from distributors/manufacturers
   - Multiple sales channels (in-store, online)
   - Geographic distribution (regions, stores)
   - Focus: Availability, inventory optimization

2. DISTRIBUTOR: Wholesale distribution operations
   - Minimal manufacturing (bundling, kitting, palletization)
   - Sells to retailers, buys from manufacturers
   - Regional distribution networks
   - Focus: OTIF, inventory optimization

3. MANUFACTURER: Production-focused operations
   - 1-3 layers of manufacturing
   - Sells to distributors and some direct
   - Regional and local DCs
   - Multiple suppliers
   - Focus: Profitability, OTIF, inventory management

Each archetype includes sensible defaults for:
- Network topology (nodes, lanes)
- Lead times, quantities, costs
- Demand patterns and distributions
- Inventory policies
- Agent configurations
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime, timedelta
import random
import math
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane, Market
from app.models.sc_entities import (
    Product, ProductHierarchy, Geography, TradingPartner,
    Forecast, InvLevel, InvPolicy, SourcingRules
)
from app.models.supplier import VendorProduct, VendorLeadTime
# Backward compatibility alias: Item was migrated to Product in sc_entities.py
Item = Product
from app.models.planning_hierarchy import (
    PlanningHierarchyConfig, SiteHierarchyNode, ProductHierarchyNode,
    PlanningType, SiteHierarchyLevel, ProductHierarchyLevel, TimeBucketType,
    DEFAULT_PLANNING_TEMPLATES
)
from app.models.tenant import Tenant
from app.models.user import User
from app.models.agent_config import AgentConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class CompanyArchetype(str, Enum):
    """Primary company role determining supply chain structure."""
    RETAILER = "retailer"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"


class AgentMode(str, Enum):
    """AI agent operational mode."""
    NONE = "none"  # No AI assistance
    COPILOT = "copilot"  # AI suggestions, human approval
    AUTONOMOUS = "autonomous"  # AI makes decisions within guardrails


class DemandPattern(str, Enum):
    """Demand pattern types."""
    CONSTANT = "constant"
    SEASONAL = "seasonal"
    TRENDING = "trending"
    PROMOTIONAL = "promotional"
    RANDOM = "random"


class DistributionType(str, Enum):
    """Statistical distribution types."""
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    POISSON = "poisson"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"


# ============================================================================
# Archetype Configuration Templates
# ============================================================================

@dataclass
class NodeTemplate:
    """Template for creating supply chain nodes."""
    name_prefix: str
    node_type: str
    master_type: str
    count: int
    initial_inventory_range: Tuple[int, int]
    capacity_range: Tuple[int, int]
    holding_cost_range: Tuple[float, float]
    shortage_cost_range: Tuple[float, float]


@dataclass
class LaneTemplate:
    """Template for creating lanes between nodes."""
    source_type: str
    target_type: str
    lead_time_range: Tuple[int, int]  # days
    cost_range: Tuple[float, float]
    reliability_range: Tuple[float, float]


@dataclass
class ProductTemplate:
    """Template for creating products."""
    name_prefix: str
    category: str
    family: str
    base_price_range: Tuple[float, float]
    base_cost_range: Tuple[float, float]
    demand_mean_range: Tuple[int, int]
    demand_cv_range: Tuple[float, float]  # Coefficient of variation


@dataclass
class ArchetypeConfig:
    """Complete configuration for a company archetype."""
    archetype: CompanyArchetype
    description: str

    # Network structure
    node_templates: List[NodeTemplate]
    lane_templates: List[LaneTemplate]

    # Product structure
    product_categories: int
    product_families_per_category: int
    products_per_family: int
    product_template: ProductTemplate

    # Geographic structure
    regions: int
    countries_per_region: int
    sites_per_country: int

    # Default policies
    default_safety_stock_days: int
    default_service_level: float
    default_review_period_days: int

    # Demand characteristics
    demand_pattern: DemandPattern
    demand_distribution: DistributionType
    seasonality_amplitude: float  # 0-1, 0=no seasonality

    # Agent configuration
    recommended_agent_mode: AgentMode
    agent_strategies: List[str]

    # Planning focus areas
    primary_kpis: List[str]


# Pre-defined archetype configurations
RETAILER_CONFIG = ArchetypeConfig(
    archetype=CompanyArchetype.RETAILER,
    description="Multi-channel retail operations with focus on availability and inventory optimization",

    node_templates=[
        NodeTemplate("CDC", "Central DC", "INVENTORY", 2, (50000, 100000), (500000, 1000000), (0.3, 0.5), (2.0, 4.0)),
        NodeTemplate("RDC", "Regional DC", "INVENTORY", 6, (10000, 30000), (100000, 300000), (0.4, 0.6), (2.5, 4.5)),
        NodeTemplate("STORE", "Retail Store", "INVENTORY", 50, (500, 2000), (5000, 15000), (0.5, 0.8), (3.0, 5.0)),
        NodeTemplate("ONLINE", "Online Fulfillment", "INVENTORY", 3, (5000, 15000), (50000, 100000), (0.35, 0.55), (2.5, 4.0)),
        NodeTemplate("SUPP", "Supplier", "VENDOR", 10, (0, 0), (1000000, 5000000), (0, 0), (0, 0)),
        NodeTemplate("CUST", "Customer", "CUSTOMER", 1, (0, 0), (0, 0), (0, 0), (0, 0)),
    ],

    lane_templates=[
        LaneTemplate("VENDOR", "Central DC", (7, 21), (0.02, 0.05), (0.85, 0.98)),
        LaneTemplate("Central DC", "Regional DC", (2, 5), (0.01, 0.03), (0.92, 0.99)),
        LaneTemplate("Regional DC", "Retail Store", (1, 3), (0.005, 0.02), (0.95, 0.99)),
        LaneTemplate("Regional DC", "Online Fulfillment", (1, 2), (0.008, 0.025), (0.94, 0.99)),
        LaneTemplate("Retail Store", "CUSTOMER", (0, 0), (0, 0), (1.0, 1.0)),
        LaneTemplate("Online Fulfillment", "CUSTOMER", (1, 3), (0.01, 0.03), (0.90, 0.98)),
    ],

    product_categories=5,
    product_families_per_category=4,
    products_per_family=10,
    product_template=ProductTemplate("SKU", "Retail", "General", (5.0, 200.0), (2.0, 100.0), (10, 500), (0.2, 0.6)),

    regions=3,
    countries_per_region=2,
    sites_per_country=10,

    default_safety_stock_days=14,
    default_service_level=0.95,
    default_review_period_days=7,

    demand_pattern=DemandPattern.SEASONAL,
    demand_distribution=DistributionType.NORMAL,
    seasonality_amplitude=0.3,

    recommended_agent_mode=AgentMode.COPILOT,
    agent_strategies=["conservative", "ml_forecast", "optimizer"],

    primary_kpis=["fill_rate", "inventory_turns", "stockout_rate", "days_of_supply"]
)


DISTRIBUTOR_CONFIG = ArchetypeConfig(
    archetype=CompanyArchetype.DISTRIBUTOR,
    description="Wholesale distribution with focus on OTIF and efficient inventory management",

    node_templates=[
        NodeTemplate("NDC", "National DC", "INVENTORY", 2, (100000, 250000), (1000000, 2500000), (0.25, 0.4), (1.5, 3.0)),
        NodeTemplate("RDC", "Regional DC", "INVENTORY", 8, (25000, 75000), (250000, 750000), (0.3, 0.5), (2.0, 3.5)),
        NodeTemplate("LDC", "Local DC", "INVENTORY", 20, (5000, 20000), (50000, 150000), (0.35, 0.55), (2.5, 4.0)),
        NodeTemplate("KITTING", "Kitting Center", "MANUFACTURER", 4, (2000, 8000), (20000, 60000), (0.4, 0.6), (2.0, 3.5)),
        NodeTemplate("MFG", "Manufacturer", "VENDOR", 15, (0, 0), (2000000, 10000000), (0, 0), (0, 0)),
        NodeTemplate("RETAIL", "Retailer Customer", "CUSTOMER", 100, (0, 0), (0, 0), (0, 0), (0, 0)),
    ],

    lane_templates=[
        LaneTemplate("VENDOR", "National DC", (14, 35), (0.015, 0.04), (0.88, 0.97)),
        LaneTemplate("National DC", "Regional DC", (3, 7), (0.008, 0.02), (0.93, 0.99)),
        LaneTemplate("National DC", "Kitting Center", (1, 3), (0.005, 0.015), (0.95, 0.99)),
        LaneTemplate("Kitting Center", "Regional DC", (1, 2), (0.01, 0.025), (0.94, 0.99)),
        LaneTemplate("Regional DC", "Local DC", (1, 3), (0.006, 0.018), (0.94, 0.99)),
        LaneTemplate("Local DC", "CUSTOMER", (1, 5), (0.01, 0.03), (0.90, 0.98)),
    ],

    product_categories=8,
    product_families_per_category=6,
    products_per_family=15,
    product_template=ProductTemplate("DIST", "Distribution", "Wholesale", (10.0, 500.0), (5.0, 300.0), (50, 2000), (0.25, 0.5)),

    regions=4,
    countries_per_region=3,
    sites_per_country=8,

    default_safety_stock_days=10,
    default_service_level=0.97,
    default_review_period_days=5,

    demand_pattern=DemandPattern.TRENDING,
    demand_distribution=DistributionType.LOGNORMAL,
    seasonality_amplitude=0.2,

    recommended_agent_mode=AgentMode.COPILOT,
    agent_strategies=["conservative", "ml_forecast", "reactive"],

    primary_kpis=["otif", "inventory_turns", "order_fill_rate", "cycle_time"]
)


MANUFACTURER_CONFIG = ArchetypeConfig(
    archetype=CompanyArchetype.MANUFACTURER,
    description="Production-focused operations with multi-tier manufacturing and supplier management",

    node_templates=[
        NodeTemplate("PLANT", "Manufacturing Plant", "MANUFACTURER", 3, (50000, 150000), (500000, 1500000), (0.2, 0.35), (3.0, 6.0)),
        NodeTemplate("SUBASSY", "Sub-Assembly", "MANUFACTURER", 6, (20000, 60000), (200000, 600000), (0.25, 0.4), (2.5, 5.0)),
        NodeTemplate("COMP", "Component Mfg", "MANUFACTURER", 8, (10000, 40000), (100000, 400000), (0.3, 0.45), (2.0, 4.0)),
        NodeTemplate("FG_DC", "Finished Goods DC", "INVENTORY", 4, (30000, 100000), (300000, 1000000), (0.28, 0.42), (2.0, 4.0)),
        NodeTemplate("RDC", "Regional DC", "INVENTORY", 10, (10000, 40000), (100000, 400000), (0.32, 0.48), (2.5, 4.5)),
        NodeTemplate("RAW", "Raw Material Supplier", "VENDOR", 25, (0, 0), (5000000, 20000000), (0, 0), (0, 0)),
        NodeTemplate("TIER1", "Tier 1 Supplier", "VENDOR", 15, (0, 0), (2000000, 10000000), (0, 0), (0, 0)),
        NodeTemplate("DIST", "Distributor Customer", "CUSTOMER", 50, (0, 0), (0, 0), (0, 0), (0, 0)),
        NodeTemplate("DIRECT", "Direct Customer", "CUSTOMER", 20, (0, 0), (0, 0), (0, 0), (0, 0)),
    ],

    lane_templates=[
        LaneTemplate("VENDOR", "Component Mfg", (21, 60), (0.01, 0.03), (0.85, 0.95)),
        LaneTemplate("VENDOR", "Sub-Assembly", (14, 45), (0.012, 0.035), (0.87, 0.96)),
        LaneTemplate("Component Mfg", "Sub-Assembly", (3, 10), (0.005, 0.015), (0.92, 0.98)),
        LaneTemplate("Sub-Assembly", "Manufacturing Plant", (2, 7), (0.004, 0.012), (0.93, 0.99)),
        LaneTemplate("Manufacturing Plant", "Finished Goods DC", (1, 3), (0.003, 0.01), (0.95, 0.99)),
        LaneTemplate("Finished Goods DC", "Regional DC", (2, 5), (0.006, 0.018), (0.94, 0.99)),
        LaneTemplate("Regional DC", "CUSTOMER", (2, 7), (0.008, 0.025), (0.92, 0.98)),
        LaneTemplate("Finished Goods DC", "CUSTOMER", (3, 10), (0.01, 0.03), (0.90, 0.97)),
    ],

    product_categories=4,
    product_families_per_category=5,
    products_per_family=8,
    product_template=ProductTemplate("MFG", "Manufactured", "Industrial", (50.0, 2000.0), (25.0, 1200.0), (20, 500), (0.3, 0.6)),

    regions=3,
    countries_per_region=4,
    sites_per_country=6,

    default_safety_stock_days=7,
    default_service_level=0.93,
    default_review_period_days=7,

    demand_pattern=DemandPattern.PROMOTIONAL,
    demand_distribution=DistributionType.LOGNORMAL,
    seasonality_amplitude=0.15,

    recommended_agent_mode=AgentMode.AUTONOMOUS,
    agent_strategies=["optimizer", "ml_forecast", "llm"],

    primary_kpis=["gross_margin", "otif", "inventory_turns", "production_efficiency", "supplier_otif"]
)


ARCHETYPE_CONFIGS = {
    CompanyArchetype.RETAILER: RETAILER_CONFIG,
    CompanyArchetype.DISTRIBUTOR: DISTRIBUTOR_CONFIG,
    CompanyArchetype.MANUFACTURER: MANUFACTURER_CONFIG
}


# ============================================================================
# Synthetic Data Generator
# ============================================================================

@dataclass
class GenerationRequest:
    """Request for synthetic data generation."""
    tenant_name: str
    archetype: CompanyArchetype
    company_name: str
    admin_email: str
    admin_name: str

    # Customization (optional - uses defaults if not specified)
    num_products: Optional[int] = None
    num_sites: Optional[int] = None
    num_suppliers: Optional[int] = None
    num_customers: Optional[int] = None

    # Agent configuration
    agent_mode: AgentMode = AgentMode.COPILOT
    enable_gnn: bool = True
    enable_llm: bool = True
    enable_trm: bool = True

    # Time range for forecasts
    forecast_horizon_months: int = 12
    history_months: int = 6

    # Seed for reproducibility
    random_seed: Optional[int] = None


@dataclass
class GenerationResult:
    """Result of synthetic data generation."""
    tenant_id: int
    config_id: int
    admin_user_id: int

    sites_created: int
    lanes_created: int
    products_created: int
    forecasts_created: int
    policies_created: int

    summary: Dict[str, Any]


class SyntheticDataGenerator:
    """
    Generates complete synthetic data sets for supply chain planning.

    Usage:
        generator = SyntheticDataGenerator(db)
        result = await generator.generate(GenerationRequest(
            tenant_name="ACME Corp",
            archetype=CompanyArchetype.MANUFACTURER,
            company_name="ACME Manufacturing",
            admin_email="admin@acme.com",
            admin_name="John Admin"
        ))
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config: Optional[ArchetypeConfig] = None
        self.request: Optional[GenerationRequest] = None

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        Generate complete synthetic data set based on request.

        This creates:
        1. Customer and admin user
        2. Supply chain configuration (nodes, lanes, items)
        3. Product and site hierarchies
        4. Forecasts and inventory levels
        5. Inventory policies
        6. Planning hierarchy configurations
        7. Agent configurations
        """
        self.request = request
        self.config = ARCHETYPE_CONFIGS[request.archetype]

        if request.random_seed:
            random.seed(request.random_seed)

        logger.info(f"Generating synthetic data for {request.archetype.value}: {request.company_name}")

        # 1. Create tenant
        tenant = await self._create_tenant()

        # 2. Create admin user
        admin_user = await self._create_admin_user(tenant.id)

        # 3. Create supply chain config
        sc_config = await self._create_supply_chain_config(tenant.id)

        # 4. Create sites
        sites = await self._create_sites(sc_config.id)

        # 5. Create transportation lanes
        lanes = await self._create_lanes(sc_config.id, sites)

        # 6. Create products/items
        items = await self._create_items(sc_config.id)

        # 7. Create hierarchies
        await self._create_site_hierarchy(tenant.id, sites)
        await self._create_product_hierarchy(tenant.id, items)

        # 8. Create forecasts
        forecasts = await self._create_forecasts(tenant.id, sites, items)

        # 9. Create inventory levels and policies
        policies = await self._create_inventory_policies(tenant.id, sites, items)

        # 10. Create planning hierarchy configurations
        await self._create_planning_configs(tenant.id, sc_config.id)

        # 11. Create agent configurations
        await self._create_agent_configs(tenant.id, sc_config.id)

        await self.db.commit()

        return GenerationResult(
            tenant_id=tenant.id,
            config_id=sc_config.id,
            admin_user_id=admin_user.id,
            sites_created=len(sites),
            lanes_created=len(lanes),
            products_created=len(items),
            forecasts_created=len(forecasts),
            policies_created=len(policies),
            summary={
                "archetype": request.archetype.value,
                "company_name": request.company_name,
                "primary_kpis": self.config.primary_kpis,
                "recommended_agent_mode": self.config.recommended_agent_mode.value,
                "agent_strategies": self.config.agent_strategies
            }
        )

    async def _create_tenant(self) -> Tenant:
        """Create the tenant (organization)."""
        tenant = Tenant(
            name=self.request.tenant_name,
            description=f"{self.config.description} - {self.request.company_name}",
            is_active=True
        )
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def _create_admin_user(self, tenant_id: int) -> User:
        """Create the tenant administrator user."""
        from app.core.security import get_password_hash
        from app.services.bootstrap import DEFAULT_ADMIN_PASSWORD

        user = User(
            email=self.request.admin_email,
            hashed_password=get_password_hash(DEFAULT_ADMIN_PASSWORD),
            full_name=self.request.admin_name,
            is_active=True,
            is_superuser=False,
            tenant_id=tenant_id
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def _create_supply_chain_config(self, tenant_id: int) -> SupplyChainConfig:
        """Create the supply chain configuration."""
        config = SupplyChainConfig(
            name=f"{self.request.company_name} SC",
            description=self.config.description,
            tenant_id=tenant_id,
            is_active=True
        )
        self.db.add(config)
        await self.db.flush()
        return config

    async def _create_sites(self, config_id: int) -> List[Site]:
        """Create supply chain sites based on archetype templates."""
        sites = []

        for template in self.config.node_templates:
            count = self.request.num_sites if template.master_type == "INVENTORY" and self.request.num_sites else template.count
            if template.master_type == "VENDOR" and self.request.num_suppliers:
                count = self.request.num_suppliers
            if template.master_type == "CUSTOMER" and self.request.num_customers:
                count = self.request.num_customers

            for i in range(count):
                site = Site(
                    config_id=config_id,
                    name=f"{template.name_prefix}_{i+1:03d}",
                    node_type=template.node_type,
                    master_type=template.master_type,
                    initial_inventory=random.randint(*template.initial_inventory_range),
                    capacity=random.randint(*template.capacity_range),
                    holding_cost=round(random.uniform(*template.holding_cost_range), 2),
                    shortage_cost=round(random.uniform(*template.shortage_cost_range), 2),
                    is_active=True
                )
                self.db.add(site)
                sites.append(site)

        await self.db.flush()
        return sites

    async def _create_lanes(self, config_id: int, sites: List[Site]) -> List[TransportationLane]:
        """Create transportation lanes between sites based on archetype templates."""
        lanes = []

        # Group sites by type
        sites_by_type = {}
        for site in sites:
            if site.node_type not in sites_by_type:
                sites_by_type[site.node_type] = []
            sites_by_type[site.node_type].append(site)

        for template in self.config.lane_templates:
            source_sites = sites_by_type.get(template.source_type, [])
            target_sites = sites_by_type.get(template.target_type, [])

            # Create connections (not fully connected - use reasonable topology)
            for source in source_sites:
                # Each source connects to a subset of targets
                num_targets = min(len(target_sites), max(1, len(target_sites) // 3))
                targets = random.sample(target_sites, num_targets)

                for target in targets:
                    lane = TransportationLane(
                        config_id=config_id,
                        from_site_id=source.id,
                        to_site_id=target.id,
                        lead_time=random.randint(*template.lead_time_range),
                        cost=round(random.uniform(*template.cost_range), 4),
                        reliability=round(random.uniform(*template.reliability_range), 3),
                        is_active=True
                    )
                    self.db.add(lane)
                    lanes.append(lane)

        await self.db.flush()
        return lanes

    async def _create_items(self, config_id: int) -> List[Item]:
        """Create products/items based on archetype configuration."""
        items = []
        template = self.config.product_template

        total_products = (
            self.request.num_products or
            self.config.product_categories *
            self.config.product_families_per_category *
            self.config.products_per_family
        )

        for i in range(total_products):
            item = Item(
                config_id=config_id,
                name=f"{template.name_prefix}_{i+1:05d}",
                description=f"Product {i+1}",
                unit_price=round(random.uniform(*template.base_price_range), 2),
                unit_cost=round(random.uniform(*template.base_cost_range), 2),
                is_active=True
            )
            self.db.add(item)
            items.append(item)

        await self.db.flush()
        return items

    async def _create_site_hierarchy(self, tenant_id: int, sites: List[Site]):
        """Create site hierarchy nodes."""
        # Create company level
        company = SiteHierarchyNode(
            tenant_id=tenant_id,
            code=f"COMPANY_{tenant_id}",
            name=self.request.company_name,
            hierarchy_level=SiteHierarchyLevel.COMPANY,
            hierarchy_path=f"COMPANY_{tenant_id}",
            depth=0,
            is_plannable=True
        )
        self.db.add(company)
        await self.db.flush()

        # Create regions
        regions = []
        region_names = ["AMERICAS", "EMEA", "APAC", "LATAM"][:self.config.regions]
        for i, name in enumerate(region_names):
            region = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=f"REG_{name}",
                name=name,
                parent_id=company.id,
                hierarchy_level=SiteHierarchyLevel.REGION,
                hierarchy_path=f"{company.code}/{name}",
                depth=1,
                is_plannable=True
            )
            self.db.add(region)
            regions.append(region)

        await self.db.flush()

        # Create countries under each region
        countries = []
        country_names = {
            "AMERICAS": ["USA", "CANADA", "MEXICO", "BRAZIL"],
            "EMEA": ["UK", "GERMANY", "FRANCE", "SPAIN"],
            "APAC": ["JAPAN", "CHINA", "INDIA", "AUSTRALIA"],
            "LATAM": ["ARGENTINA", "CHILE", "COLOMBIA", "PERU"]
        }

        for region in regions:
            region_countries = country_names.get(region.name, [])[:self.config.countries_per_region]
            for cname in region_countries:
                country = SiteHierarchyNode(
                    tenant_id=tenant_id,
                    code=f"CTY_{cname}",
                    name=cname,
                    parent_id=region.id,
                    hierarchy_level=SiteHierarchyLevel.COUNTRY,
                    hierarchy_path=f"{region.hierarchy_path}/{cname}",
                    depth=2,
                    is_plannable=True
                )
                self.db.add(country)
                countries.append(country)

        await self.db.flush()

        # Assign sites to countries
        inventory_sites = [s for s in sites if s.master_type in ("INVENTORY", "MANUFACTURER")]
        sites_per_country = max(1, len(inventory_sites) // len(countries))

        for i, sc_site in enumerate(inventory_sites):
            country = countries[i % len(countries)]
            hierarchy_node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=sc_site.name,
                name=sc_site.name,
                site_id=sc_site.id,
                parent_id=country.id,
                hierarchy_level=SiteHierarchyLevel.SITE,
                hierarchy_path=f"{country.hierarchy_path}/{sc_site.name}",
                depth=3,
                is_plannable=True,
                default_capacity=sc_site.capacity
            )
            self.db.add(hierarchy_node)

        await self.db.flush()

    async def _create_product_hierarchy(self, tenant_id: int, items: List[Item]):
        """Create product hierarchy nodes."""
        categories = []
        families = []

        # Create categories
        category_names = ["Electronics", "Apparel", "Food", "Industrial", "Consumer",
                         "Automotive", "Healthcare", "Home"][:self.config.product_categories]

        for i, name in enumerate(category_names):
            category = ProductHierarchyNode(
                tenant_id=tenant_id,
                code=f"CAT_{name.upper()}",
                name=name,
                hierarchy_level=ProductHierarchyLevel.CATEGORY,
                hierarchy_path=f"CAT_{name.upper()}",
                depth=0,
                is_plannable=True
            )
            self.db.add(category)
            categories.append(category)

        await self.db.flush()

        # Create families under each category
        family_names = ["Premium", "Standard", "Value", "Professional", "Consumer", "Entry"]

        for category in categories:
            for i in range(self.config.product_families_per_category):
                fname = family_names[i % len(family_names)]
                family = ProductHierarchyNode(
                    tenant_id=tenant_id,
                    code=f"FAM_{category.name[:3].upper()}_{fname.upper()}",
                    name=f"{category.name} - {fname}",
                    parent_id=category.id,
                    hierarchy_level=ProductHierarchyLevel.FAMILY,
                    hierarchy_path=f"{category.hierarchy_path}/{fname}",
                    depth=1,
                    is_plannable=True
                )
                self.db.add(family)
                families.append(family)

        await self.db.flush()

        # Create groups and assign products
        groups = []
        group_suffixes = ["A", "B", "C", "D", "E"]

        for family in families:
            for i in range(min(5, self.config.products_per_family // 2)):
                suffix = group_suffixes[i % len(group_suffixes)]
                group = ProductHierarchyNode(
                    tenant_id=tenant_id,
                    code=f"GRP_{family.code}_{suffix}",
                    name=f"{family.name} - Group {suffix}",
                    parent_id=family.id,
                    hierarchy_level=ProductHierarchyLevel.GROUP,
                    hierarchy_path=f"{family.hierarchy_path}/{suffix}",
                    depth=2,
                    is_plannable=True
                )
                self.db.add(group)
                groups.append(group)

        await self.db.flush()

        # Assign items to groups
        items_per_group = max(1, len(items) // len(groups))
        for i, item in enumerate(items):
            group = groups[i % len(groups)]
            product = ProductHierarchyNode(
                tenant_id=tenant_id,
                code=item.name,
                name=item.name,
                product_id=str(item.id),
                parent_id=group.id,
                hierarchy_level=ProductHierarchyLevel.PRODUCT,
                hierarchy_path=f"{group.hierarchy_path}/{item.name}",
                depth=3,
                is_plannable=True
            )
            self.db.add(product)

        await self.db.flush()

    async def _create_forecasts(self, tenant_id: int, sites: List[Site], items: List[Item]) -> List[Forecast]:
        """Create demand forecasts."""
        forecasts = []
        demand_sites = [s for s in sites if s.master_type == "CUSTOMER"]
        inventory_sites = [s for s in sites if s.master_type == "INVENTORY"]

        template = self.config.product_template
        start_date = date.today()

        # Create forecasts for each inventory site and item
        for site in inventory_sites[:min(20, len(inventory_sites))]:  # Limit for performance
            for item in items[:min(50, len(items))]:  # Limit for performance
                # Generate monthly forecasts
                for month in range(self.request.forecast_horizon_months):
                    forecast_date = start_date + timedelta(days=month * 30)

                    # Base demand
                    mean_demand = random.uniform(*template.demand_mean_range)

                    # Apply seasonality
                    if self.config.demand_pattern == DemandPattern.SEASONAL:
                        seasonality = 1 + self.config.seasonality_amplitude * math.sin(
                            2 * math.pi * (month / 12)
                        )
                        mean_demand *= seasonality

                    # Apply trend
                    if self.config.demand_pattern == DemandPattern.TRENDING:
                        trend = 1 + 0.02 * month  # 2% monthly growth
                        mean_demand *= trend

                    # Calculate percentiles
                    cv = random.uniform(*template.demand_cv_range)
                    std = mean_demand * cv

                    forecast = Forecast(
                        site_id=site.id,
                        product_id=str(item.id),
                        forecast_date=forecast_date,
                        forecast_quantity=round(mean_demand),
                        forecast_p10=round(max(0, mean_demand - 1.28 * std)),
                        forecast_p50=round(mean_demand),
                        forecast_p90=round(mean_demand + 1.28 * std),
                        connection_id=tenant_id
                    )
                    self.db.add(forecast)
                    forecasts.append(forecast)

        await self.db.flush()
        return forecasts

    async def _create_inventory_policies(self, tenant_id: int, sites: List[Site], items: List[Item]) -> List[InvPolicy]:
        """Create inventory policies."""
        policies = []
        inventory_sites = [s for s in sites if s.master_type == "INVENTORY"]

        for site in inventory_sites:
            for item in items[:min(20, len(items))]:
                policy = InvPolicy(
                    site_id=site.id,
                    product_id=str(item.id),
                    policy_type="doc_dem",  # Days of coverage based on demand
                    safety_stock_days=self.config.default_safety_stock_days,
                    target_service_level=self.config.default_service_level,
                    review_period_days=self.config.default_review_period_days,
                    min_order_qty=10,
                    max_order_qty=10000,
                    connection_id=tenant_id
                )
                self.db.add(policy)
                policies.append(policy)

        await self.db.flush()
        return policies

    async def _create_planning_configs(self, tenant_id: int, config_id: int):
        """Create planning hierarchy configurations."""
        for template in DEFAULT_PLANNING_TEMPLATES:
            config = PlanningHierarchyConfig(
                tenant_id=tenant_id,
                config_id=config_id,
                planning_type=template["planning_type"],
                site_hierarchy_level=template["site_hierarchy_level"],
                product_hierarchy_level=template["product_hierarchy_level"],
                time_bucket=template["time_bucket"],
                horizon_months=template["horizon_months"],
                frozen_periods=template["frozen_periods"],
                slushy_periods=template["slushy_periods"],
                update_frequency_hours=template["update_frequency_hours"],
                powell_policy_class=template["powell_policy_class"],
                gnn_model_type=template.get("gnn_model_type"),
                parent_planning_type=template.get("parent_template_code"),
                consistency_tolerance=template["consistency_tolerance"],
                name=template["name"],
                description=template.get("description"),
                is_active=True
            )
            self.db.add(config)

        await self.db.flush()

    async def _create_agent_configs(self, tenant_id: int, config_id: int):
        """Create AI agent configurations."""
        for strategy in self.config.agent_strategies:
            agent_config = AgentConfig(
                name=f"{strategy.title()} Agent",
                strategy=strategy,
                config_id=config_id,
                is_active=True,
                parameters={
                    "mode": self.request.agent_mode.value,
                    "enable_gnn": self.request.enable_gnn,
                    "enable_llm": self.request.enable_llm,
                    "enable_trm": self.request.enable_trm
                }
            )
            self.db.add(agent_config)

        await self.db.flush()


# ============================================================================
# Convenience Functions
# ============================================================================

def get_archetype_info(archetype: CompanyArchetype) -> Dict[str, Any]:
    """Get information about a company archetype."""
    config = ARCHETYPE_CONFIGS[archetype]
    return {
        "archetype": archetype.value,
        "description": config.description,
        "recommended_agent_mode": config.recommended_agent_mode.value,
        "agent_strategies": config.agent_strategies,
        "primary_kpis": config.primary_kpis,
        "default_safety_stock_days": config.default_safety_stock_days,
        "default_service_level": config.default_service_level,
        "node_types": [t.node_type for t in config.node_templates],
        "product_categories": config.product_categories,
        "regions": config.regions
    }


def list_archetypes() -> List[Dict[str, Any]]:
    """List all available company archetypes."""
    return [get_archetype_info(a) for a in CompanyArchetype]

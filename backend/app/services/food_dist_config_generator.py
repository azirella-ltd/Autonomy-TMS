"""
Food Dist Supply Chain Configuration Generator

Creates a realistic foodservice distributor supply chain configuration.

Key Characteristics:
- Volume-based business model
- Multi-temperature distribution (frozen, refrigerated, dry)
- 2-4 day delivery to customers
- Weekly, multi-temperature delivery system
- "One Order, One Truck, One Delivery" model
- Serves restaurants, retailers, institutions, convenience stores

Network Structure:
- 1 DC (Distribution Center) - West Valley City, UT
- 10 Customers in AZ, CA, OR, WA (NW and SW regions)
- 10 Suppliers (5 with 2 items, 5 with 3 items = 25 total items)
- 5 Product Groups with 5 items each

Geographic Hierarchy:
- USA (country)
  - NW (region): OR, WA
  - SW (region): AZ, CA, UT
  - Central (region): IL, MN, TX, AR (suppliers)
  - NE (region): PA, NY (suppliers)
  - SE (region): GA (suppliers)
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
import random
import math
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Import all models first to ensure relationships are properly configured
# This ensures SQLAlchemy can resolve all forward references
import app.models  # noqa: F401 - ensures all models are loaded

from app.models.supply_chain_config import SupplyChainConfig, Node, TransportationLane, Market
from app.models.sc_entities import Product, Forecast, InvLevel, InvPolicy, TradingPartner, Geography
from app.models.planning_hierarchy import (
    SiteHierarchyNode, ProductHierarchyNode,
    SiteHierarchyLevel, ProductHierarchyLevel
)
from app.models.tenant import Tenant, TenantMode, ClockMode
from app.models.user import User
from app.models.agent_config import AgentConfig
from app.models.supplier import VendorProduct, VendorLeadTime

logger = logging.getLogger(__name__)


# ============================================================================
# Temperature Categories for Foodservice Distribution
# ============================================================================

class TemperatureCategory(str, Enum):
    """Product temperature requirements - affects storage and shipping."""
    FROZEN = "frozen"           # -10°F to 0°F
    REFRIGERATED = "refrigerated"  # 33°F to 40°F
    DRY = "dry"                 # Room temperature


# ============================================================================
# Product Group Definitions (Based on Food Dist Categories)
# ============================================================================

@dataclass
class ProductDefinition:
    """Definition of a specific product."""
    sku: str
    name: str
    description: str
    unit_size: str           # e.g., "10 lb", "1 gal", "5 lb block"
    cases_per_pallet: int
    temperature: TemperatureCategory
    shelf_life_days: int     # Important for food distribution
    unit_cost: float         # Purchase cost
    unit_price: float        # Selling price
    weekly_demand_mean: int  # Average weekly demand in cases
    demand_cv: float         # Coefficient of variation (0.2-0.6)
    min_order_qty: int       # MOQ from supplier


@dataclass
class ProductGroupDefinition:
    """Definition of a product group/family."""
    code: str
    name: str
    category: str
    temperature: TemperatureCategory
    products: List[ProductDefinition]


@dataclass
class SupplierDefinition:
    """Definition of a supplier."""
    code: str
    name: str
    description: str
    location: str
    lead_time_days: int
    lead_time_variability: float  # CV of lead time
    reliability: float            # On-time delivery rate
    min_order_value: float        # Minimum order $ amount
    product_skus: List[str]       # SKUs this supplier provides
    latitude: float = 0.0
    longitude: float = 0.0


@dataclass
class CustomerDefinition:
    """Definition of a customer."""
    code: str
    name: str
    segment: str              # restaurant, retail, institution, etc.
    size: str                 # small, medium, large
    delivery_frequency: str   # weekly, bi-weekly
    order_lead_time_days: int # Days from order to required delivery
    credit_limit: float
    avg_order_value: float
    demand_multiplier: float  # Relative to base product demand
    latitude: float = 0.0
    longitude: float = 0.0
    city: str = ""
    state: str = ""
    region: str = "NW"        # NW or SW — determines which RDC serves this customer


@dataclass
class RDCDefinition:
    """Definition of a Regional Distribution Center."""
    code: str
    name: str
    location: str
    region: str               # NW or SW
    latitude: float
    longitude: float
    city: str
    state: str
    capacity: int = 100000    # Cases
    frozen_capacity: int = 30000
    refrigerated_capacity: int = 40000
    dry_capacity: int = 30000


# ============================================================================
# Food Dist Specific Configuration
# ============================================================================

# Product Group 1: Frozen Proteins
FROZEN_PROTEINS = ProductGroupDefinition(
    code="FRZ_PROTEIN",
    name="Frozen Proteins",
    category="Meat & Poultry",
    temperature=TemperatureCategory.FROZEN,
    products=[
        ProductDefinition(
            sku="FP001", name="Chicken Breast IQF", description="Individually quick frozen boneless skinless chicken breast",
            unit_size="10 lb case", cases_per_pallet=80, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=28.50, unit_price=34.99, weekly_demand_mean=150, demand_cv=0.35, min_order_qty=10
        ),
        ProductDefinition(
            sku="FP002", name="Beef Patties 80/20", description="Frozen ground beef patties 4oz each",
            unit_size="10 lb case", cases_per_pallet=72, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=270, unit_cost=45.00, unit_price=54.99, weekly_demand_mean=120, demand_cv=0.40, min_order_qty=10
        ),
        ProductDefinition(
            sku="FP003", name="Pork Chops Bone-In", description="Frozen center-cut bone-in pork chops",
            unit_size="10 lb case", cases_per_pallet=80, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=300, unit_cost=32.00, unit_price=39.99, weekly_demand_mean=80, demand_cv=0.45, min_order_qty=8
        ),
        ProductDefinition(
            sku="FP004", name="Turkey Breast Deli", description="Frozen turkey breast for deli slicing",
            unit_size="8 lb case", cases_per_pallet=96, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=38.00, unit_price=46.99, weekly_demand_mean=60, demand_cv=0.30, min_order_qty=6
        ),
        ProductDefinition(
            sku="FP005", name="Seafood Mix Premium", description="Frozen premium seafood blend - shrimp, scallops, calamari",
            unit_size="5 lb case", cases_per_pallet=120, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=55.00, unit_price=69.99, weekly_demand_mean=40, demand_cv=0.50, min_order_qty=5
        ),
    ]
)

# Product Group 2: Refrigerated Dairy
REFRIGERATED_DAIRY = ProductGroupDefinition(
    code="REF_DAIRY",
    name="Refrigerated Dairy",
    category="Dairy & Cheese",
    temperature=TemperatureCategory.REFRIGERATED,
    products=[
        ProductDefinition(
            sku="RD001", name="Cheddar Block Sharp", description="Sharp cheddar cheese block for slicing",
            unit_size="5 lb block", cases_per_pallet=100, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=180, unit_cost=15.50, unit_price=19.99, weekly_demand_mean=200, demand_cv=0.25, min_order_qty=20
        ),
        ProductDefinition(
            sku="RD002", name="Mozzarella Block LMPS", description="Low moisture part-skim mozzarella block",
            unit_size="5 lb block", cases_per_pallet=100, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=150, unit_cost=14.00, unit_price=18.49, weekly_demand_mean=250, demand_cv=0.30, min_order_qty=20
        ),
        ProductDefinition(
            sku="RD003", name="Cream Cheese Block", description="Philadelphia-style cream cheese block",
            unit_size="3 lb block", cases_per_pallet=120, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=120, unit_cost=8.50, unit_price=11.49, weekly_demand_mean=180, demand_cv=0.25, min_order_qty=24
        ),
        ProductDefinition(
            sku="RD004", name="Greek Yogurt Plain", description="Nonfat Greek yogurt plain bulk",
            unit_size="32 oz tub", cases_per_pallet=144, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=45, unit_cost=4.25, unit_price=5.99, weekly_demand_mean=300, demand_cv=0.35, min_order_qty=48
        ),
        ProductDefinition(
            sku="RD005", name="Butter Salted Grade AA", description="Grade AA salted butter",
            unit_size="1 lb stick (36ct)", cases_per_pallet=80, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=120, unit_cost=85.00, unit_price=99.99, weekly_demand_mean=100, demand_cv=0.20, min_order_qty=5
        ),
    ]
)

# Product Group 3: Dry Goods/Pantry
DRY_PANTRY = ProductGroupDefinition(
    code="DRY_PANTRY",
    name="Dry Goods Pantry",
    category="Pasta, Grains & Staples",
    temperature=TemperatureCategory.DRY,
    products=[
        ProductDefinition(
            sku="DP001", name="Pasta Penne Rigate", description="Premium durum wheat penne pasta",
            unit_size="20 lb case", cases_per_pallet=60, temperature=TemperatureCategory.DRY,
            shelf_life_days=730, unit_cost=18.00, unit_price=23.99, weekly_demand_mean=200, demand_cv=0.25, min_order_qty=10
        ),
        ProductDefinition(
            sku="DP002", name="Rice Long Grain", description="Premium long grain white rice",
            unit_size="25 lb bag", cases_per_pallet=50, temperature=TemperatureCategory.DRY,
            shelf_life_days=1095, unit_cost=22.00, unit_price=28.99, weekly_demand_mean=180, demand_cv=0.30, min_order_qty=10
        ),
        ProductDefinition(
            sku="DP003", name="Flour All Purpose", description="Enriched all-purpose flour",
            unit_size="50 lb bag", cases_per_pallet=40, temperature=TemperatureCategory.DRY,
            shelf_life_days=365, unit_cost=18.00, unit_price=24.99, weekly_demand_mean=150, demand_cv=0.25, min_order_qty=8
        ),
        ProductDefinition(
            sku="DP004", name="Sugar Granulated", description="Fine granulated pure cane sugar",
            unit_size="25 lb bag", cases_per_pallet=56, temperature=TemperatureCategory.DRY,
            shelf_life_days=730, unit_cost=15.00, unit_price=19.99, weekly_demand_mean=160, demand_cv=0.20, min_order_qty=10
        ),
        ProductDefinition(
            sku="DP005", name="Coffee Ground Medium", description="Medium roast ground coffee",
            unit_size="5 lb bag", cases_per_pallet=80, temperature=TemperatureCategory.DRY,
            shelf_life_days=365, unit_cost=35.00, unit_price=44.99, weekly_demand_mean=120, demand_cv=0.35, min_order_qty=12
        ),
    ]
)

# Product Group 4: Frozen Desserts
FROZEN_DESSERTS = ProductGroupDefinition(
    code="FRZ_DESSERT",
    name="Frozen Desserts",
    category="Desserts & Bakery",
    temperature=TemperatureCategory.FROZEN,
    products=[
        ProductDefinition(
            sku="FD001", name="Ice Cream Vanilla Premium", description="Premium vanilla bean ice cream",
            unit_size="3 gallon tub", cases_per_pallet=36, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=28.00, unit_price=35.99, weekly_demand_mean=80, demand_cv=0.40, min_order_qty=6
        ),
        ProductDefinition(
            sku="FD002", name="Sorbet Mango", description="All-natural mango sorbet",
            unit_size="3 gallon tub", cases_per_pallet=36, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=32.00, unit_price=41.99, weekly_demand_mean=40, demand_cv=0.50, min_order_qty=4
        ),
        ProductDefinition(
            sku="FD003", name="Gelato Chocolate", description="Italian-style chocolate gelato",
            unit_size="2.5 gallon tub", cases_per_pallet=48, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=365, unit_cost=38.00, unit_price=48.99, weekly_demand_mean=50, demand_cv=0.45, min_order_qty=4
        ),
        ProductDefinition(
            sku="FD004", name="Pie Apple 10 inch", description="Pre-baked apple pie 10 inch",
            unit_size="6 ct case", cases_per_pallet=60, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=270, unit_cost=42.00, unit_price=52.99, weekly_demand_mean=60, demand_cv=0.35, min_order_qty=5
        ),
        ProductDefinition(
            sku="FD005", name="Cake Chocolate Layer", description="3-layer chocolate cake 10 inch",
            unit_size="4 ct case", cases_per_pallet=48, temperature=TemperatureCategory.FROZEN,
            shelf_life_days=270, unit_cost=55.00, unit_price=69.99, weekly_demand_mean=35, demand_cv=0.40, min_order_qty=4
        ),
    ]
)

# Product Group 5: Beverages
BEVERAGES = ProductGroupDefinition(
    code="BEV",
    name="Beverages",
    category="Juices & Beverages",
    temperature=TemperatureCategory.REFRIGERATED,
    products=[
        ProductDefinition(
            sku="BV001", name="Orange Juice Premium", description="100% premium not-from-concentrate OJ",
            unit_size="1 gallon (4ct)", cases_per_pallet=60, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=60, unit_cost=18.00, unit_price=23.99, weekly_demand_mean=220, demand_cv=0.30, min_order_qty=15
        ),
        ProductDefinition(
            sku="BV002", name="Apple Juice Organic", description="Organic apple juice from concentrate",
            unit_size="1 gallon (4ct)", cases_per_pallet=60, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=90, unit_cost=15.00, unit_price=19.99, weekly_demand_mean=150, demand_cv=0.25, min_order_qty=15
        ),
        ProductDefinition(
            sku="BV003", name="Lemonade Fresh", description="Fresh-squeezed style lemonade",
            unit_size="1 gallon (4ct)", cases_per_pallet=60, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=45, unit_cost=12.00, unit_price=16.49, weekly_demand_mean=180, demand_cv=0.40, min_order_qty=15
        ),
        ProductDefinition(
            sku="BV004", name="Iced Tea Sweet", description="Southern-style sweet iced tea",
            unit_size="1 gallon (4ct)", cases_per_pallet=60, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=60, unit_cost=10.00, unit_price=13.99, weekly_demand_mean=200, demand_cv=0.35, min_order_qty=15
        ),
        ProductDefinition(
            sku="BV005", name="Kombucha Ginger", description="Organic ginger kombucha",
            unit_size="16 oz (12ct)", cases_per_pallet=100, temperature=TemperatureCategory.REFRIGERATED,
            shelf_life_days=90, unit_cost=28.00, unit_price=38.99, weekly_demand_mean=60, demand_cv=0.50, min_order_qty=10
        ),
    ]
)

ALL_PRODUCT_GROUPS = [FROZEN_PROTEINS, REFRIGERATED_DAIRY, DRY_PANTRY, FROZEN_DESSERTS, BEVERAGES]


# ============================================================================
# Supplier Definitions (5 with 2 items, 5 with 3 items = 25 items)
# ============================================================================

SUPPLIERS = [
    # Suppliers with 2 items each (10 items total)
    SupplierDefinition(
        code="TYSON", name="Tyson Foods Inc", description="Leading protein producer",
        location="Springdale, AR", lead_time_days=7, lead_time_variability=0.20,
        reliability=0.95, min_order_value=2000.00, product_skus=["FP001", "FP004"],
        latitude=36.1544, longitude=-94.1537,
    ),
    SupplierDefinition(
        code="KRAFT", name="Kraft Heinz Company", description="Major food manufacturer",
        location="Pittsburgh, PA", lead_time_days=10, lead_time_variability=0.15,
        reliability=0.97, min_order_value=1500.00, product_skus=["RD001", "RD003"],
        latitude=40.4545, longitude=-79.9909,
    ),
    SupplierDefinition(
        code="GENMILLS", name="General Mills Foodservice", description="Staples and baking products",
        location="Minneapolis, MN", lead_time_days=8, lead_time_variability=0.18,
        reliability=0.96, min_order_value=1200.00, product_skus=["DP001", "DP003"],
        latitude=44.9800, longitude=-93.2650,
    ),
    SupplierDefinition(
        code="NESTLE", name="Nestle Professional", description="Frozen desserts and beverages",
        location="Glendale, CA", lead_time_days=12, lead_time_variability=0.22,
        reliability=0.94, min_order_value=2500.00, product_skus=["FD001", "FD002"],
        latitude=34.1899, longitude=-118.2437,
    ),
    SupplierDefinition(
        code="TROP", name="Tropicana Brands Group", description="Premium juice manufacturer",
        location="Chicago, IL", lead_time_days=5, lead_time_variability=0.15,
        reliability=0.98, min_order_value=1000.00, product_skus=["BV001", "BV003"],
        latitude=41.8881, longitude=-87.6180,
    ),

    # Suppliers with 3 items each (15 items total)
    SupplierDefinition(
        code="SYSCOMEAT", name="Sysco Protein Solutions", description="Full-line protein supplier",
        location="Houston, TX", lead_time_days=9, lead_time_variability=0.20,
        reliability=0.94, min_order_value=3000.00, product_skus=["FP002", "FP003", "FP005"],
        latitude=29.7437, longitude=-95.3643,
    ),
    SupplierDefinition(
        code="LANDOLAKES", name="Land O'Lakes Foodservice", description="Dairy cooperative",
        location="Arden Hills, MN", lead_time_days=6, lead_time_variability=0.12,
        reliability=0.97, min_order_value=1500.00, product_skus=["RD002", "RD004", "RD005"],
        latitude=45.0253, longitude=-93.1864,
    ),
    SupplierDefinition(
        code="CONAGRA", name="Conagra Foodservice", description="Diversified food company",
        location="Chicago, IL", lead_time_days=8, lead_time_variability=0.18,
        reliability=0.95, min_order_value=1800.00, product_skus=["DP002", "DP004", "DP005"],
        latitude=41.8881, longitude=-87.6180,
    ),
    SupplierDefinition(
        code="RICHPROD", name="Rich Products Corporation", description="Frozen dessert specialist",
        location="Buffalo, NY", lead_time_days=10, lead_time_variability=0.20,
        reliability=0.95, min_order_value=2000.00, product_skus=["FD003", "FD004", "FD005"],
        latitude=42.8864, longitude=-78.8784,
    ),
    SupplierDefinition(
        code="COCACOLA", name="Coca-Cola Foodservice", description="Beverage industry leader",
        location="Atlanta, GA", lead_time_days=4, lead_time_variability=0.10,
        reliability=0.99, min_order_value=1200.00, product_skus=["BV002", "BV004", "BV005"],
        latitude=33.7695, longitude=-84.3964,
    ),
]


# ============================================================================
# Customer Definitions (10 customers - mix of foodservice segments)
# ============================================================================

RDCS = [
    RDCDefinition(
        code="RDC_NW", name="Regional DC - Seattle",
        location="Seattle, WA", region="NW",
        latitude=47.6062, longitude=-122.3321,
        city="Seattle", state="WA",
        capacity=120000, frozen_capacity=35000,
        refrigerated_capacity=45000, dry_capacity=40000,
    ),
    RDCDefinition(
        code="RDC_SW", name="Regional DC - Riverside",
        location="Riverside, CA", region="SW",
        latitude=33.9533, longitude=-117.3962,
        city="Riverside", state="CA",
        capacity=150000, frozen_capacity=45000,
        refrigerated_capacity=55000, dry_capacity=50000,
    ),
]

CUSTOMERS = [
    # NW Region - Oregon (served by RDC_NW)
    CustomerDefinition(
        code="CUST_PDX", name="Restaurant Supply Co", segment="Full Service Restaurant",
        size="large", delivery_frequency="weekly", order_lead_time_days=3,
        credit_limit=50000.00, avg_order_value=8500.00, demand_multiplier=1.5,
        latitude=45.5152, longitude=-122.6784, city="Portland", state="OR", region="NW",
    ),
    CustomerDefinition(
        code="CUST_EUG", name="Campus Dining Services", segment="Higher Education",
        size="medium", delivery_frequency="weekly", order_lead_time_days=4,
        credit_limit=35000.00, avg_order_value=6500.00, demand_multiplier=1.2,
        latitude=44.0521, longitude=-123.0868, city="Eugene", state="OR", region="NW",
    ),
    CustomerDefinition(
        code="CUST_SAL", name="Salem Wholesale Foods", segment="Wholesale",
        size="medium", delivery_frequency="weekly", order_lead_time_days=3,
        credit_limit=30000.00, avg_order_value=5000.00, demand_multiplier=1.0,
        latitude=44.9429, longitude=-123.0351, city="Salem", state="OR", region="NW",
    ),
    # NW Region - Washington (served by RDC_NW)
    CustomerDefinition(
        code="CUST_SEA", name="Downtown Deli Group", segment="QSR Deli",
        size="small", delivery_frequency="weekly", order_lead_time_days=2,
        credit_limit=15000.00, avg_order_value=2200.00, demand_multiplier=0.6,
        latitude=47.6062, longitude=-122.3321, city="Seattle", state="WA", region="NW",
    ),
    CustomerDefinition(
        code="CUST_TAC", name="Premier Catering Services", segment="Catering",
        size="medium", delivery_frequency="weekly", order_lead_time_days=3,
        credit_limit=30000.00, avg_order_value=5000.00, demand_multiplier=1.1,
        latitude=47.2529, longitude=-122.4443, city="Tacoma", state="WA", region="NW",
    ),
    CustomerDefinition(
        code="CUST_SPO", name="Inland Pacific Foods", segment="Institutional",
        size="medium", delivery_frequency="weekly", order_lead_time_days=4,
        credit_limit=25000.00, avg_order_value=4200.00, demand_multiplier=0.8,
        latitude=47.6588, longitude=-117.4260, city="Spokane", state="WA", region="NW",
    ),
    # SW Region - California (served by RDC_SW)
    CustomerDefinition(
        code="CUST_LAX", name="Metro Grocery Chain", segment="Retail Grocery",
        size="large", delivery_frequency="weekly", order_lead_time_days=4,
        credit_limit=75000.00, avg_order_value=12000.00, demand_multiplier=2.0,
        latitude=34.0522, longitude=-118.2437, city="Los Angeles", state="CA", region="SW",
    ),
    CustomerDefinition(
        code="CUST_SFO", name="Coastal Healthcare System", segment="Healthcare",
        size="medium", delivery_frequency="bi-weekly", order_lead_time_days=5,
        credit_limit=40000.00, avg_order_value=5500.00, demand_multiplier=0.9,
        latitude=37.7749, longitude=-122.4194, city="San Francisco", state="CA", region="SW",
    ),
    CustomerDefinition(
        code="CUST_SDG", name="School District Foods", segment="K-12 Education",
        size="large", delivery_frequency="weekly", order_lead_time_days=5,
        credit_limit=45000.00, avg_order_value=7500.00, demand_multiplier=1.4,
        latitude=32.7157, longitude=-117.1611, city="San Diego", state="CA", region="SW",
    ),
    CustomerDefinition(
        code="CUST_SAC", name="Family Restaurant Inc", segment="Casual Dining",
        size="medium", delivery_frequency="weekly", order_lead_time_days=3,
        credit_limit=25000.00, avg_order_value=4500.00, demand_multiplier=1.0,
        latitude=38.5816, longitude=-121.4944, city="Sacramento", state="CA", region="SW",
    ),
    # SW Region - Arizona (served by RDC_SW)
    CustomerDefinition(
        code="CUST_PHX", name="Quick Serve Foods LLC", segment="Quick Service",
        size="large", delivery_frequency="weekly", order_lead_time_days=2,
        credit_limit=60000.00, avg_order_value=9500.00, demand_multiplier=1.8,
        latitude=33.4484, longitude=-112.0740, city="Phoenix", state="AZ", region="SW",
    ),
    CustomerDefinition(
        code="CUST_TUS", name="Green Valley Markets", segment="Natural/Specialty Retail",
        size="small", delivery_frequency="bi-weekly", order_lead_time_days=4,
        credit_limit=20000.00, avg_order_value=3500.00, demand_multiplier=0.7,
        latitude=32.2226, longitude=-110.9747, city="Tucson", state="AZ", region="SW",
    ),
    CustomerDefinition(
        code="CUST_MES", name="Mesa Convention Services", segment="Convention/Events",
        size="medium", delivery_frequency="weekly", order_lead_time_days=3,
        credit_limit=35000.00, avg_order_value=6000.00, demand_multiplier=1.1,
        latitude=33.4152, longitude=-111.8315, city="Mesa", state="AZ", region="SW",
    ),
]


# ============================================================================
# Distribution Center Configuration
# ============================================================================

@dataclass
class DCConfiguration:
    """Configuration for the Distribution Center."""
    code: str = "CDC_WEST"
    name: str = "Food Dist Western Distribution Center"
    location: str = "West Valley City, UT"
    latitude: float = 40.6916
    longitude: float = -112.0011

    # Capacity (in cases)
    frozen_capacity: int = 150000
    refrigerated_capacity: int = 200000
    dry_capacity: int = 300000

    # Operating parameters
    operating_hours_per_day: int = 18
    pick_rate_cases_per_hour: int = 500
    receiving_docks: int = 12
    shipping_docks: int = 20

    # Cost parameters
    frozen_holding_cost_pct: float = 0.35      # 35% annually (higher due to refrigeration)
    refrigerated_holding_cost_pct: float = 0.28  # 28% annually
    dry_holding_cost_pct: float = 0.20          # 20% annually

    # Service parameters
    target_fill_rate: float = 0.98             # 98% target fill rate
    target_otif: float = 0.95                  # 95% on-time in-full
    delivery_lead_time_days: int = 2           # 2-4 day delivery standard


DC_CONFIG = DCConfiguration()


# ============================================================================
# Main Generator Class
# ============================================================================

class FoodDistConfigGenerator:
    """
    Generates the complete Food Dist supply chain configuration.

    Creates a training group with realistic foodservice distribution parameters
    based on the Food Dist business model.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.tenant: Optional[Tenant] = None
        self.sc_config: Optional[SupplyChainConfig] = None
        self.products: Dict[str, Product] = {}
        self.nodes: Dict[str, Node] = {}

    async def generate(
        self,
        tenant_name: str = "Food Dist",
        admin_email: str = "admin@distdemo.com",
        admin_name: str = "Food Dist Admin",
        random_seed: Optional[int] = 42,
        existing_tenant_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate the complete Food Dist configuration.

        Args:
            tenant_name: Name of the tenant
            admin_email: Email for the tenant admin
            admin_name: Name for the tenant admin
            random_seed: Seed for reproducible random generation
            existing_tenant_id: If provided, skip tenant/admin creation and use this tenant

        Returns:
            Summary of created entities
        """
        if random_seed:
            random.seed(random_seed)

        logger.info(f"Generating Food Dist configuration: {tenant_name}")

        # 1. Create or load tenant
        admin = None
        if existing_tenant_id:
            # Use existing tenant — skip admin/tenant creation
            result = await self.db.execute(
                select(Tenant).where(Tenant.id == existing_tenant_id)
            )
            self.tenant = result.scalar_one_or_none()
            if not self.tenant:
                raise ValueError(f"Tenant with id={existing_tenant_id} not found")
            logger.info(f"Using existing tenant: {self.tenant.name} (ID: {self.tenant.id})")
        else:
            admin, self.tenant = await self._create_admin_and_tenant(tenant_name, admin_email, admin_name)

        # 2b. Check if config already exists for this tenant
        existing_config = await self.db.execute(
            select(SupplyChainConfig).where(
                SupplyChainConfig.tenant_id == self.tenant.id,
                SupplyChainConfig.name == "Food Dist Distribution Network",
            )
        )
        existing_config = existing_config.scalar_one_or_none()
        if existing_config:
            logger.info(f"SC config already exists for tenant {self.tenant.id}: {existing_config.name} (ID: {existing_config.id})")
            return {
                "tenant_id": self.tenant.id,
                "tenant_name": self.tenant.name,
                "admin_user_id": admin.id if admin else None,
                "config_id": existing_config.id,
                "dc_node_id": None,
                "suppliers_created": 0,
                "customers_created": 0,
                "products_created": 0,
                "lanes_created": 0,
                "vendor_products_created": 0,
                "forecasts_created": 0,
                "policies_created": 0,
                "summary": {"status": "already_exists"},
            }

        # 3. Create supply chain config
        self.sc_config = await self._create_sc_config()

        # 4. Create DC node
        dc_node = await self._create_dc_node()

        # 4b. Create RDC nodes
        rdc_nodes = await self._create_rdc_nodes()

        # 5. Create supplier nodes (external trading partners)
        supplier_nodes = await self._create_supplier_nodes()

        # 6. Create customer nodes (external trading partners)
        customer_nodes = await self._create_customer_nodes()

        # 6b. Create geography records and link to sites
        geographies = await self._create_geographies(dc_node, supplier_nodes, customer_nodes, rdc_nodes)

        # 7. Create products
        products = await self._create_products()

        # 8. Create lanes (supplier -> CDC -> RDC -> customer)
        lanes = await self._create_lanes(dc_node, rdc_nodes, supplier_nodes, customer_nodes)

        # 9. Create trading partners and vendor-product relationships
        trading_partners = await self._create_trading_partners(supplier_nodes)
        vendor_products = await self._create_vendor_products(supplier_nodes, products, trading_partners)

        # 9b. Create customer trading partners
        customer_trading_partners = await self._create_customer_trading_partners(customer_nodes)

        await self.db.commit()

        # 10. Generate 2-year transactional history
        history_counts = {}
        try:
            from app.services.food_dist_history_generator import FoodDistHistoryGenerator
            history_gen = FoodDistHistoryGenerator(
                db=self.db,
                config_id=self.sc_config.id,
                tenant_id=self.tenant.id,
            )
            history_counts = await history_gen.generate_history(days=730)
            logger.info(f"Generated {history_counts.get('total', 0):,} history records")
        except Exception:
            logger.exception("History generation failed — config created without history")

        return {
            "tenant_id": self.tenant.id,
            "tenant_name": tenant_name,
            "admin_user_id": admin.id if admin else None,
            "config_id": self.sc_config.id,
            "dc_node_id": dc_node.id,
            "suppliers_created": len(supplier_nodes),
            "customers_created": len(customer_nodes),
            "products_created": len(products),
            "lanes_created": len(lanes),
            "vendor_products_created": len(vendor_products),
            "rdcs_created": len(rdc_nodes),
            "history": history_counts,
            "summary": {
                "product_groups": len(ALL_PRODUCT_GROUPS),
                "products_per_group": 5,
                "total_products": 25,
                "temperature_mix": {
                    "frozen": 10,  # 5 proteins + 5 desserts
                    "refrigerated": 10,  # 5 dairy + 5 beverages
                    "dry": 5,  # 5 pantry
                },
                "internal_sites": 3,  # 1 CDC + 2 RDCs
                "external_suppliers": len(supplier_nodes),
                "external_customers": len(customer_nodes),
                "network_structure": "Hub and Spoke (1 CDC → 2 RDCs → 13 Customers)",
                "delivery_model": "Weekly multi-temperature",
            }
        }

    async def _create_admin_and_tenant(self, tenant_name: str, email: str, name: str) -> tuple[User, Tenant]:
        """Create the Food Dist tenant and admin user together.

        Note: Tenant requires admin_id, admin requires tenant_id - we handle this
        by creating admin first without tenant_id, then tenant with admin_id,
        then updating admin with tenant_id.
        """
        from app.core.security import get_password_hash
        from app.services.bootstrap import DEFAULT_ADMIN_PASSWORD

        # 1. Create admin user first (without tenant_id initially)
        user = User(
            email=email,
            hashed_password=get_password_hash(DEFAULT_ADMIN_PASSWORD),
            full_name=name,
            is_active=True,
            is_superuser=False,
            user_type="TENANT_ADMIN",
        )
        self.db.add(user)
        await self.db.flush()
        logger.info(f"Created admin user: {user.email} (ID: {user.id})")

        # 2. Create tenant with admin_id
        tenant = Tenant(
            name=tenant_name,
            description="Food Dist Learning Environment - Foodservice redistribution simulation",
            admin_id=user.id,
            mode=TenantMode.LEARNING,
            clock_mode=ClockMode.TURN_BASED,
        )
        self.db.add(tenant)
        await self.db.flush()
        logger.info(f"Created tenant: {tenant.name} (ID: {tenant.id})")

        # 3. Update user with tenant_id
        user.tenant_id = tenant.id
        await self.db.flush()

        return user, tenant

    async def _create_sc_config(self) -> SupplyChainConfig:
        """Create the supply chain configuration."""
        config = SupplyChainConfig(
            name="Food Dist Distribution Network",
            description="Foodservice redistribution network - "
                       "Multi-temperature distribution with 2-4 day delivery capability",
            tenant_id=self.tenant.id,
            is_active=True,
            site_type_definitions=[
                {"type": "market_supply", "label": "Supplier", "order": 3, "is_required": True, "master_type": "market_supply"},
                {"type": "CDC", "label": "Central DC", "order": 2, "is_required": False, "master_type": "inventory"},
                {"type": "RDC", "label": "Regional DC", "order": 1, "is_required": False, "master_type": "inventory"},
                {"type": "market_demand", "label": "Customer", "order": 0, "is_required": True, "master_type": "market_demand"},
            ],
        )
        self.db.add(config)
        await self.db.flush()
        logger.info(f"Created SC config: {config.name}")
        return config

    async def _create_dc_node(self) -> Node:
        """Create the distribution center node."""
        dc = Node(
            config_id=self.sc_config.id,
            name=DC_CONFIG.code,
            type="Central Distribution Center",  # Human-readable type
            dag_type="CDC",  # DAG identity
            master_type="INVENTORY",  # Master processing type
            attributes={
                "initial_inventory": 50000,
                "capacity": DC_CONFIG.frozen_capacity + DC_CONFIG.refrigerated_capacity + DC_CONFIG.dry_capacity,
                "holding_cost": 0.25,
                "shortage_cost": 5.00,
                "frozen_capacity": DC_CONFIG.frozen_capacity,
                "refrigerated_capacity": DC_CONFIG.refrigerated_capacity,
                "dry_capacity": DC_CONFIG.dry_capacity,
                "location": DC_CONFIG.location,
            }
        )
        self.db.add(dc)
        await self.db.flush()
        self.nodes[DC_CONFIG.code] = dc
        logger.info(f"Created DC node: {dc.name}")
        return dc

    async def _create_rdc_nodes(self) -> List[Node]:
        """Create Regional Distribution Center nodes (internal sites)."""
        rdc_nodes = []
        for rdc_def in RDCS:
            node = Node(
                config_id=self.sc_config.id,
                name=rdc_def.code,
                type=f"Regional Distribution Center - {rdc_def.city}, {rdc_def.state}",
                dag_type="RDC",
                master_type="INVENTORY",
                is_external=False,
                attributes={
                    "initial_inventory": 20000,
                    "capacity": rdc_def.capacity,
                    "frozen_capacity": rdc_def.frozen_capacity,
                    "refrigerated_capacity": rdc_def.refrigerated_capacity,
                    "dry_capacity": rdc_def.dry_capacity,
                    "location": rdc_def.location,
                    "region": rdc_def.region,
                },
            )
            self.db.add(node)
            rdc_nodes.append(node)
            self.nodes[rdc_def.code] = node

        await self.db.flush()
        logger.info(f"Created {len(rdc_nodes)} RDC nodes")
        return rdc_nodes

    async def _create_supplier_nodes(self) -> List[Node]:
        """Create supplier nodes (external trading partners, not internal sites)."""
        supplier_nodes = []

        for supplier_def in SUPPLIERS:
            node = Node(
                config_id=self.sc_config.id,
                name=supplier_def.code,
                type=f"Supplier - {supplier_def.name}",
                dag_type="market_supply",
                master_type="MARKET_SUPPLY",
                is_external=True,
                tpartner_type="vendor",
                attributes={
                    "description": supplier_def.description,
                    "location": supplier_def.location,
                    "lead_time_days": supplier_def.lead_time_days,
                    "reliability": supplier_def.reliability,
                    "min_order_value": supplier_def.min_order_value,
                },
            )
            self.db.add(node)
            supplier_nodes.append(node)
            self.nodes[supplier_def.code] = node

        await self.db.flush()
        logger.info(f"Created {len(supplier_nodes)} supplier nodes")
        return supplier_nodes

    async def _create_customer_nodes(self) -> List[Node]:
        """Create customer demand nodes (external trading partners, not internal sites)."""
        customer_nodes = []

        for customer_def in CUSTOMERS:
            node = Node(
                config_id=self.sc_config.id,
                name=customer_def.code,
                type=f"Customer - {customer_def.city}, {customer_def.state}",
                dag_type="market_demand",
                master_type="MARKET_DEMAND",
                is_external=True,
                tpartner_type="customer",
                attributes={
                    "customer_name": customer_def.name,
                    "segment": customer_def.segment,
                    "size": customer_def.size,
                    "delivery_frequency": customer_def.delivery_frequency,
                    "order_lead_time_days": customer_def.order_lead_time_days,
                    "credit_limit": customer_def.credit_limit,
                    "avg_order_value": customer_def.avg_order_value,
                    "demand_multiplier": customer_def.demand_multiplier,
                    "region": customer_def.region,
                },
            )
            self.db.add(node)
            customer_nodes.append(node)
            self.nodes[customer_def.code] = node

        await self.db.flush()
        logger.info(f"Created {len(customer_nodes)} customer nodes")
        return customer_nodes

    async def _create_geographies(
        self,
        dc_node: Node,
        supplier_nodes: List[Node],
        customer_nodes: List[Node],
        rdc_nodes: Optional[List[Node]] = None,
    ) -> List[Geography]:
        """Create hierarchical Geography records (Country→Region→State→City) and link to sites.

        Hierarchy:
            USA (country)
            ├── NW (region): OR, WA
            ├── SW (region): AZ, CA, UT
            ├── Central (region): IL, MN, TX, AR
            ├── NE (region): PA, NY
            └── SE (region): GA
        """
        geographies = []
        prefix = f"CFG{self.sc_config.id}_"

        STATE_TO_REGION = {
            "OR": "NW", "WA": "NW",
            "AZ": "SW", "CA": "SW", "UT": "SW",
            "IL": "CENTRAL", "MN": "CENTRAL", "TX": "CENTRAL", "AR": "CENTRAL",
            "PA": "NE", "NY": "NE",
            "GA": "SE",
        }
        REGION_NAMES = {
            "NW": "Northwest", "SW": "Southwest", "CENTRAL": "Central",
            "NE": "Northeast", "SE": "Southeast",
        }
        STATE_NAMES = {
            "OR": "Oregon", "WA": "Washington", "AZ": "Arizona", "CA": "California",
            "UT": "Utah", "IL": "Illinois", "MN": "Minnesota", "TX": "Texas",
            "AR": "Arkansas", "PA": "Pennsylvania", "NY": "New York", "GA": "Georgia",
        }

        # 1. Country level: USA
        usa_geo = Geography(
            id=f"{prefix}GEO_USA",
            description="United States",
            country="USA",
        )
        self.db.add(usa_geo)
        geographies.append(usa_geo)
        await self.db.flush()

        # 2. Region level
        region_geos = {}
        for region_code, region_name in REGION_NAMES.items():
            geo = Geography(
                id=f"{prefix}GEO_REG_{region_code}",
                description=f"{region_name} Region",
                country="USA",
                parent_geo_id=usa_geo.id,
            )
            self.db.add(geo)
            geographies.append(geo)
            region_geos[region_code] = geo
        await self.db.flush()

        # 3. State level
        state_geos = {}
        states_needed = set()

        # Collect all states from DC, suppliers, customers
        dc_state = DC_CONFIG.location.split(", ")[-1]
        states_needed.add(dc_state)
        for s in SUPPLIERS:
            states_needed.add(s.location.split(", ")[-1])
        for c in CUSTOMERS:
            states_needed.add(c.state)

        for state_abbr in sorted(states_needed):
            region_code = STATE_TO_REGION.get(state_abbr)
            if not region_code:
                continue
            geo = Geography(
                id=f"{prefix}GEO_ST_{state_abbr}",
                description=STATE_NAMES.get(state_abbr, state_abbr),
                state_prov=state_abbr,
                country="USA",
                parent_geo_id=region_geos[region_code].id,
            )
            self.db.add(geo)
            geographies.append(geo)
            state_geos[state_abbr] = geo
        await self.db.flush()

        # 4. City-level (site) geographies as children of states

        # DC geography
        dc_city, dc_state_abbr = DC_CONFIG.location.split(", ")
        dc_geo = Geography(
            id=f"{prefix}GEO_{DC_CONFIG.code}",
            description=f"{DC_CONFIG.name} - {DC_CONFIG.location}",
            city=dc_city,
            state_prov=dc_state_abbr,
            country="USA",
            latitude=DC_CONFIG.latitude,
            longitude=DC_CONFIG.longitude,
            parent_geo_id=state_geos[dc_state_abbr].id,
        )
        self.db.add(dc_geo)
        geographies.append(dc_geo)
        await self.db.flush()
        dc_node.geo_id = dc_geo.id

        # RDC geographies
        if rdc_nodes:
            for rdc_def, rdc_node in zip(RDCS, rdc_nodes):
                geo = Geography(
                    id=f"{prefix}GEO_{rdc_def.code}",
                    description=f"{rdc_def.name} - {rdc_def.location}",
                    city=rdc_def.city,
                    state_prov=rdc_def.state,
                    country="USA",
                    latitude=rdc_def.latitude,
                    longitude=rdc_def.longitude,
                    parent_geo_id=state_geos[rdc_def.state].id,
                )
                self.db.add(geo)
                geographies.append(geo)
                rdc_node.geo_id = geo.id
            await self.db.flush()

        # Supplier geographies
        for supplier_def, supplier_node in zip(SUPPLIERS, supplier_nodes):
            city = supplier_def.location.split(", ")[0]
            state = supplier_def.location.split(", ")[1]
            geo = Geography(
                id=f"{prefix}GEO_{supplier_def.code}",
                description=f"{supplier_def.name} - {supplier_def.location}",
                city=city,
                state_prov=state,
                country="USA",
                latitude=supplier_def.latitude,
                longitude=supplier_def.longitude,
                parent_geo_id=state_geos[state].id,
            )
            self.db.add(geo)
            geographies.append(geo)
            supplier_node.geo_id = geo.id

        await self.db.flush()

        # Customer geographies
        for customer_def, customer_node in zip(CUSTOMERS, customer_nodes):
            geo = Geography(
                id=f"{prefix}GEO_{customer_def.code}",
                description=f"{customer_def.name} - {customer_def.city}, {customer_def.state}",
                city=customer_def.city,
                state_prov=customer_def.state,
                country="USA",
                latitude=customer_def.latitude,
                longitude=customer_def.longitude,
                parent_geo_id=state_geos[customer_def.state].id,
            )
            self.db.add(geo)
            geographies.append(geo)
            customer_node.geo_id = geo.id

        await self.db.flush()
        logger.info(f"Created {len(geographies)} geography records (hierarchical: country→region→state→city)")
        return geographies

    async def _create_products(self) -> List[Product]:
        """Create all products from product groups."""
        products = []
        # Add config prefix to make product IDs unique per config
        prefix = f"CFG{self.sc_config.id}_"

        for group_def in ALL_PRODUCT_GROUPS:
            for product_def in group_def.products:
                product_id = f"{prefix}{product_def.sku}"
                product = Product(
                    id=product_id,  # Config-prefixed SKU as ID
                    description=f"{product_def.name} - {product_def.description}",
                    unit_price=product_def.unit_price,
                    unit_cost=product_def.unit_cost,
                    config_id=self.sc_config.id,
                    is_active="true",  # SC uses string 'true'/'false'
                    category=group_def.category,
                    family=group_def.name,
                    product_group_name=group_def.code,
                )
                self.db.add(product)
                products.append(product)
                # Store with original SKU for lookup, but product.id has prefix
                self.products[product_def.sku] = product

        await self.db.flush()
        logger.info(f"Created {len(products)} products")
        return products

    async def _create_lanes(
        self,
        dc_node: Node,
        rdc_nodes: List[Node],
        supplier_nodes: List[Node],
        customer_nodes: List[Node],
    ) -> List[TransportationLane]:
        """Create transportation lanes: Supplier → CDC → RDC → Customer."""
        lanes = []
        rdc_by_region = {rdc_def.region: rdc_node for rdc_def, rdc_node in zip(RDCS, rdc_nodes)}

        # Supplier → CDC lanes
        for supplier_def, supplier_node in zip(SUPPLIERS, supplier_nodes):
            lt = supplier_def.lead_time_days
            lt_var = int(lt * supplier_def.lead_time_variability)
            lane = TransportationLane(
                config_id=self.sc_config.id,
                from_site_id=supplier_node.id,
                to_site_id=dc_node.id,
                capacity=10000,
                lead_time_days={"min": max(1, lt - lt_var), "max": lt + lt_var},
                supply_lead_time={"type": "deterministic", "value": lt},
                demand_lead_time={"type": "deterministic", "value": 1},
            )
            self.db.add(lane)
            lanes.append(lane)

        # CDC → RDC lanes
        for rdc_def, rdc_node in zip(RDCS, rdc_nodes):
            lane = TransportationLane(
                config_id=self.sc_config.id,
                from_site_id=dc_node.id,
                to_site_id=rdc_node.id,
                capacity=20000,
                lead_time_days={"min": 1, "max": 3},
                supply_lead_time={"type": "deterministic", "value": 2},
                demand_lead_time={"type": "deterministic", "value": 1},
            )
            self.db.add(lane)
            lanes.append(lane)

        # RDC → Customer lanes (routed by region)
        for customer_def, customer_node in zip(CUSTOMERS, customer_nodes):
            rdc_node = rdc_by_region.get(customer_def.region)
            if not rdc_node:
                logger.warning("No RDC for region %s, skipping customer %s", customer_def.region, customer_def.code)
                continue
            lt = customer_def.order_lead_time_days
            lane = TransportationLane(
                config_id=self.sc_config.id,
                from_site_id=rdc_node.id,
                to_site_id=customer_node.id,
                capacity=5000,
                lead_time_days={"min": max(1, lt - 1), "max": lt + 1},
                supply_lead_time={"type": "deterministic", "value": lt},
                demand_lead_time={"type": "deterministic", "value": 1},
            )
            self.db.add(lane)
            lanes.append(lane)

        await self.db.flush()
        logger.info(f"Created {len(lanes)} lanes")
        return lanes

    async def _create_trading_partners(self, supplier_nodes: List[Node]) -> Dict[str, TradingPartner]:
        """Create TradingPartner records for suppliers."""
        trading_partners = {}
        # Add config prefix to make partner IDs unique per config
        prefix = f"CFG{self.sc_config.id}_"

        for supplier_def, supplier_node in zip(SUPPLIERS, supplier_nodes):
            tp_id = f"{prefix}{supplier_def.code}"
            tp = TradingPartner(
                id=tp_id,  # Config-prefixed business key
                description=supplier_def.name,
                tpartner_type="vendor",
                is_active="true",
                city=supplier_def.location.split(", ")[0] if ", " in supplier_def.location else supplier_def.location,
                state_prov=supplier_def.location.split(", ")[1] if ", " in supplier_def.location else "",
                country="USA",
            )
            self.db.add(tp)
            trading_partners[supplier_def.code] = tp
            # Link the site node to its trading partner
            supplier_node.trading_partner_id = tp_id

        await self.db.flush()
        logger.info(f"Created {len(trading_partners)} supplier trading partners")
        return trading_partners

    async def _create_customer_trading_partners(self, customer_nodes: List[Node]) -> Dict[str, TradingPartner]:
        """Create TradingPartner records for customers."""
        trading_partners = {}
        prefix = f"CFG{self.sc_config.id}_"

        for customer_def, customer_node in zip(CUSTOMERS, customer_nodes):
            tp_id = f"{prefix}{customer_def.code}"
            tp = TradingPartner(
                id=tp_id,
                description=customer_def.name,
                tpartner_type="customer",
                is_active="true",
                city=customer_def.city,
                state_prov=customer_def.state,
                country="USA",
            )
            self.db.add(tp)
            trading_partners[customer_def.code] = tp
            # Link the site node to its trading partner
            customer_node.trading_partner_id = tp_id

        await self.db.flush()
        logger.info(f"Created {len(trading_partners)} customer trading partners")
        return trading_partners

    async def _create_vendor_products(
        self,
        supplier_nodes: List[Node],
        products: List[Product],
        trading_partners: Dict[str, TradingPartner],
    ) -> List[VendorProduct]:
        """Create vendor-product relationships."""
        vendor_products = []

        for supplier_def, supplier_node in zip(SUPPLIERS, supplier_nodes):
            tp = trading_partners.get(supplier_def.code)
            if not tp:
                continue

            for sku in supplier_def.product_skus:
                if sku in self.products:
                    product = self.products[sku]

                    # Find product definition for pricing
                    product_def = None
                    for group in ALL_PRODUCT_GROUPS:
                        for p in group.products:
                            if p.sku == sku:
                                product_def = p
                                break

                    if product_def:
                        vp = VendorProduct(
                            tpartner_id=tp.id,  # References TradingPartner.id (business key)
                            product_id=product.id,  # Product.id is the SKU
                            vendor_product_id=f"{supplier_def.code}-{sku}",
                            vendor_unit_cost=product_def.unit_cost,
                            currency="USD",
                            minimum_order_quantity=product_def.min_order_qty,
                            is_primary=True,
                            is_active="true",
                            priority=1,
                        )
                        self.db.add(vp)
                        vendor_products.append(vp)

                        # Create lead time record
                        lt = VendorLeadTime(
                            tpartner_id=tp.id,
                            product_id=product.id,
                            lead_time_days=supplier_def.lead_time_days,
                            lead_time_variability_days=supplier_def.lead_time_days * supplier_def.lead_time_variability,
                        )
                        self.db.add(lt)

        await self.db.flush()
        logger.info(f"Created {len(vendor_products)} vendor-product relationships")
        return vendor_products

    async def _create_site_hierarchy(
        self,
        dc_node: Node,
        supplier_nodes: List[Node],
        customer_nodes: List[Node],
    ):
        """Create site hierarchy."""
        # Company level
        company = SiteHierarchyNode(
            tenant_id=self.tenant.id,
            code="FOODDIST_CORP",
            name="Food Dist Corporation",
            hierarchy_level=SiteHierarchyLevel.COMPANY,
            hierarchy_path="FOODDIST_CORP",
            depth=0,
            is_plannable=True,
        )
        self.db.add(company)
        await self.db.flush()

        # Build region→state→site hierarchy from customer/DC/supplier locations
        # Regions: NW (OR, WA), SW (AZ, CA, UT), Central (IL, MN, TX, AR), NE (PA, NY), SE (GA)
        region_defs = {
            "NW": {"name": "Northwest", "states": {}},
            "SW": {"name": "Southwest", "states": {}},
            "CENTRAL": {"name": "Central", "states": {}},
            "NE": {"name": "Northeast", "states": {}},
            "SE": {"name": "Southeast", "states": {}},
        }

        STATE_TO_REGION = {
            "OR": "NW", "WA": "NW",
            "AZ": "SW", "CA": "SW", "UT": "SW",
            "IL": "CENTRAL", "MN": "CENTRAL", "TX": "CENTRAL", "AR": "CENTRAL",
            "PA": "NE", "NY": "NE",
            "GA": "SE",
        }

        STATE_NAMES = {
            "OR": "Oregon", "WA": "Washington", "AZ": "Arizona", "CA": "California",
            "UT": "Utah", "IL": "Illinois", "MN": "Minnesota", "TX": "Texas",
            "AR": "Arkansas", "PA": "Pennsylvania", "NY": "New York", "GA": "Georgia",
        }

        # Collect all sites by state
        all_site_entries = []  # (state_abbr, site_node, site_label)

        # DC
        dc_state = DC_CONFIG.location.split(", ")[-1]  # "UT"
        all_site_entries.append((dc_state, dc_node, DC_CONFIG.name))

        # Suppliers
        for supplier_def, supplier_node in zip(SUPPLIERS, supplier_nodes):
            state = supplier_def.location.split(", ")[-1]
            all_site_entries.append((state, supplier_node, supplier_def.name))

        # Customers
        for customer_def, customer_node in zip(CUSTOMERS, customer_nodes):
            all_site_entries.append((customer_def.state, customer_node, customer_def.name))

        # Group by region → state → sites
        for state_abbr, site_node, site_label in all_site_entries:
            region_code = STATE_TO_REGION.get(state_abbr)
            if not region_code:
                continue
            if state_abbr not in region_defs[region_code]["states"]:
                region_defs[region_code]["states"][state_abbr] = []
            region_defs[region_code]["states"][state_abbr].append((site_node, site_label))

        # Create hierarchy nodes
        region_nodes = {}
        state_nodes = {}

        for region_code, region_info in region_defs.items():
            if not region_info["states"]:
                continue  # skip empty regions

            region_node = SiteHierarchyNode(
                tenant_id=self.tenant.id,
                code=f"REG_{region_code}",
                name=f"{region_info['name']} Region",
                parent_id=company.id,
                hierarchy_level=SiteHierarchyLevel.REGION,
                hierarchy_path=f"FOODDIST_CORP/{region_code}",
                depth=1,
                is_plannable=True,
            )
            self.db.add(region_node)
            await self.db.flush()
            region_nodes[region_code] = region_node

            for state_abbr, sites in region_info["states"].items():
                state_node = SiteHierarchyNode(
                    tenant_id=self.tenant.id,
                    code=f"ST_{state_abbr}",
                    name=STATE_NAMES.get(state_abbr, state_abbr),
                    parent_id=region_node.id,
                    hierarchy_level=SiteHierarchyLevel.COUNTRY,  # reuse COUNTRY level for state
                    hierarchy_path=f"FOODDIST_CORP/{region_code}/{state_abbr}",
                    depth=2,
                    is_plannable=True,
                )
                self.db.add(state_node)
                await self.db.flush()
                state_nodes[state_abbr] = state_node

                for site_node_obj, site_label in sites:
                    site_hier = SiteHierarchyNode(
                        tenant_id=self.tenant.id,
                        code=site_node_obj.name,
                        name=site_label,
                        site_id=site_node_obj.id,
                        parent_id=state_node.id,
                        hierarchy_level=SiteHierarchyLevel.SITE,
                        hierarchy_path=f"FOODDIST_CORP/{region_code}/{state_abbr}/{site_node_obj.name}",
                        depth=3,
                        is_plannable=True,
                        default_capacity=getattr(site_node_obj, 'capacity', None),
                    )
                    self.db.add(site_hier)

        await self.db.flush()
        logger.info(f"Created site hierarchy: {len(region_nodes)} regions, {len(state_nodes)} states")

    async def _create_product_hierarchy(self, products: List[Product]):
        """Create product hierarchy."""
        # Category level nodes
        category_nodes = {}

        for i, group_def in enumerate(ALL_PRODUCT_GROUPS):
            # Category (temperature based)
            cat_code = f"CAT_{group_def.temperature.value.upper()}"
            if cat_code not in category_nodes:
                category = ProductHierarchyNode(
                    tenant_id=self.tenant.id,
                    code=cat_code,
                    name=f"{group_def.temperature.value.title()} Products",
                    hierarchy_level=ProductHierarchyLevel.CATEGORY,
                    hierarchy_path=cat_code,
                    depth=0,
                    is_plannable=True,
                )
                self.db.add(category)
                await self.db.flush()
                category_nodes[cat_code] = category

            category = category_nodes[cat_code]

            # Family (product group)
            family = ProductHierarchyNode(
                tenant_id=self.tenant.id,
                code=group_def.code,
                name=group_def.name,
                parent_id=category.id,
                hierarchy_level=ProductHierarchyLevel.FAMILY,
                hierarchy_path=f"{cat_code}/{group_def.code}",
                depth=1,
                is_plannable=True,
            )
            self.db.add(family)
            await self.db.flush()

            # Products
            for product_def in group_def.products:
                if product_def.sku in self.products:
                    product = self.products[product_def.sku]
                    prod_node = ProductHierarchyNode(
                        tenant_id=self.tenant.id,
                        code=product_def.sku,
                        name=product_def.name,
                        product_id=str(product.id),
                        parent_id=family.id,
                        hierarchy_level=ProductHierarchyLevel.PRODUCT,
                        hierarchy_path=f"{cat_code}/{group_def.code}/{product_def.sku}",
                        depth=2,
                        is_plannable=True,
                    )
                    self.db.add(prod_node)

        await self.db.flush()
        logger.info("Created product hierarchy")

    async def _create_forecasts(self, dc_node: Node, products: List[Product]) -> List[Forecast]:
        """Create demand forecasts for each product."""
        forecasts = []
        start_date = date.today()

        for group_def in ALL_PRODUCT_GROUPS:
            for product_def in group_def.products:
                if product_def.sku in self.products:
                    product = self.products[product_def.sku]

                    # Generate 52 weeks of forecasts
                    for week in range(52):
                        forecast_date = start_date + timedelta(weeks=week)

                        # Base demand
                        base_demand = product_def.weekly_demand_mean

                        # Apply seasonality (foodservice has seasonal patterns)
                        # Higher demand in spring/summer, lower in winter
                        month = (forecast_date.month - 1) / 12
                        seasonality = 1 + 0.15 * math.sin(2 * math.pi * (month - 0.25))

                        # Apply slight growth trend (2% annually)
                        trend = 1 + 0.02 * (week / 52)

                        mean_demand = base_demand * seasonality * trend
                        std_demand = mean_demand * product_def.demand_cv

                        forecast = Forecast(
                            site_id=dc_node.id,
                            product_id=product.id,  # Product.id is already the SKU string
                            forecast_date=forecast_date,
                            forecast_type="statistical",
                            forecast_level="product",
                            forecast_quantity=round(mean_demand),
                            forecast_p10=round(max(0, mean_demand - 1.28 * std_demand)),
                            forecast_p50=round(mean_demand),
                            forecast_p90=round(mean_demand + 1.28 * std_demand),
                            forecast_std_dev=round(std_demand, 2),
                            config_id=self.sc_config.id,
                        )
                        self.db.add(forecast)
                        forecasts.append(forecast)

        await self.db.flush()
        logger.info(f"Created {len(forecasts)} forecasts")
        return forecasts

    async def _create_inventory_policies(self, dc_node: Node, products: List[Product]) -> List[InvPolicy]:
        """Create inventory policies for each product."""
        policies = []

        for group_def in ALL_PRODUCT_GROUPS:
            for product_def in group_def.products:
                if product_def.sku in self.products:
                    product = self.products[product_def.sku]

                    # Set safety stock based on shelf life and demand variability
                    # Shorter shelf life = less safety stock (avoid spoilage)
                    if product_def.shelf_life_days < 60:
                        safety_stock_days = 7
                    elif product_def.shelf_life_days < 180:
                        safety_stock_days = 14
                    else:
                        safety_stock_days = 21

                    # Higher demand variability = more safety stock
                    if product_def.demand_cv > 0.4:
                        safety_stock_days = int(safety_stock_days * 1.3)

                    policy = InvPolicy(
                        site_id=dc_node.id,
                        product_id=product.id,  # Product.id is already the SKU string
                        ss_policy="doc_fcst",  # Days of coverage based on forecast
                        ss_days=safety_stock_days,
                        service_level=DC_CONFIG.target_fill_rate,
                        review_period=7,  # Weekly review
                        min_order_quantity=product_def.min_order_qty,
                        max_order_quantity=product_def.min_order_qty * 50,
                        is_active="true",
                        config_id=self.sc_config.id,
                    )
                    self.db.add(policy)
                    policies.append(policy)

        await self.db.flush()
        logger.info(f"Created {len(policies)} inventory policies")
        return policies

    async def _create_initial_inventory(self, dc_node: Node, products: List[Product]) -> List[InvLevel]:
        """Create initial inventory levels."""
        inv_levels = []

        for group_def in ALL_PRODUCT_GROUPS:
            for product_def in group_def.products:
                if product_def.sku in self.products:
                    product = self.products[product_def.sku]

                    # Initial inventory = 3 weeks of average demand
                    initial_qty = product_def.weekly_demand_mean * 3

                    inv_level = InvLevel(
                        site_id=dc_node.id,
                        product_id=product.id,  # Product.id is already the SKU string
                        inventory_date=date.today(),
                        on_hand_qty=initial_qty,
                        available_qty=initial_qty,
                        allocated_qty=0,
                        in_transit_qty=0,
                        config_id=self.sc_config.id,
                    )
                    self.db.add(inv_level)
                    inv_levels.append(inv_level)

        await self.db.flush()
        logger.info(f"Created {len(inv_levels)} initial inventory levels")
        return inv_levels

    async def _create_agent_configs(self):
        """Create AI agent configurations."""
        strategies = ["conservative", "ml_forecast", "optimizer"]

        for strategy in strategies:
            agent = AgentConfig(
                name=f"Food Dist {strategy.title()} Agent",
                strategy=strategy,
                config_id=self.sc_config.id,
                is_active=True,
                parameters={
                    "mode": "copilot",
                    "enable_gnn": True,
                    "enable_llm": True,
                    "enable_trm": True,
                    "service_level_target": DC_CONFIG.target_fill_rate,
                    "otif_target": DC_CONFIG.target_otif,
                }
            )
            self.db.add(agent)

        await self.db.flush()
        logger.info("Created agent configurations")


# ============================================================================
# Convenience function
# ============================================================================

async def generate_food_dist_config(
    db: AsyncSession,
    tenant_name: str = "Food Dist",
    admin_email: str = "admin@distdemo.com",
    admin_name: str = "Food Dist Admin",
    existing_tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Convenience function to generate Food Dist configuration.

    Usage:
        from app.services.food_dist_config_generator import generate_food_dist_config
        result = await generate_food_dist_config(db)

        # Or with existing tenant:
        result = await generate_food_dist_config(db, existing_tenant_id=14)
    """
    generator = FoodDistConfigGenerator(db)
    return await generator.generate(
        tenant_name=tenant_name,
        admin_email=admin_email,
        admin_name=admin_name,
        existing_tenant_id=existing_tenant_id,
    )


# ============================================================================
# Synchronous Helper for Planning Cascade
# ============================================================================

class FoodDistCascadeDataGenerator:
    """
    Synchronous data generator for the Planning Cascade.

    Provides data in the format expected by CascadeOrchestrator.run_cascade_for_food_dist().
    Does not require database access - generates sample data based on the
    Food Dist product catalog defined above.
    """

    def __init__(self, seed: Optional[int] = 42):
        """Initialize with optional random seed for reproducibility."""
        if seed is not None:
            random.seed(seed)

    def generate_inventory_and_demand_data(
        self,
        planning_horizon_days: int = 28,
        base_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Generate inventory and demand data for the planning cascade.

        Returns:
            Dict containing:
            - products: List of product inventory states
            - suppliers_by_sku: Dict mapping SKU to supplier options
            - demand_forecast: Daily demand forecast by SKU
            - demand_by_segment: Demand breakdown by customer segment
        """
        if base_date is None:
            base_date = date.today()

        products_data = []
        suppliers_by_sku = {}
        demand_forecast = {}
        demand_by_segment = {"strategic": {}, "standard": {}, "transactional": {}}

        # Process all products from the defined groups
        for group_def in ALL_PRODUCT_GROUPS:
            for product_def in group_def.products:
                # Base daily demand (weekly / 7)
                base_daily_demand = product_def.weekly_demand_mean / 7
                demand_std = base_daily_demand * product_def.demand_cv

                # Current inventory position
                dos_target = random.uniform(14, 28)
                on_hand = int(base_daily_demand * dos_target * random.uniform(0.8, 1.2))
                in_transit = int(base_daily_demand * random.uniform(3, 7))
                committed = int(base_daily_demand * random.uniform(1, 3))

                products_data.append({
                    "sku": product_def.sku,
                    "name": product_def.name,
                    "category": group_def.code.lower(),
                    "on_hand": on_hand,
                    "in_transit": in_transit,
                    "committed": committed,
                    "avg_daily_demand": round(base_daily_demand, 1),
                    "demand_std": round(demand_std, 1),
                    "unit_cost": product_def.unit_cost,
                    "selling_price": product_def.unit_price,
                    "min_order_qty": product_def.min_order_qty,
                    "shelf_life_days": product_def.shelf_life_days,
                    "temperature": group_def.temperature.value,
                })

                # Find eligible suppliers for this product
                eligible_suppliers = [
                    s for s in SUPPLIERS if product_def.sku in s.product_skus
                ]

                suppliers_by_sku[product_def.sku] = [
                    {
                        "supplier_id": s.code,
                        "supplier_name": s.name,
                        "lead_time_days": s.lead_time_days,
                        "lead_time_variability": s.lead_time_variability,
                        "reliability": s.reliability,
                        "min_order_value": s.min_order_value,
                        "unit_cost": round(product_def.unit_cost * random.uniform(0.95, 1.05), 2),
                    }
                    for s in eligible_suppliers
                ]

                # Generate daily demand forecast with seasonality
                daily_forecast = []
                for day in range(planning_horizon_days):
                    # Weekly seasonality (higher on Tue-Thu)
                    day_of_week = (base_date + timedelta(days=day)).weekday()
                    weekday_factor = 1.0 + 0.15 * math.sin((day_of_week - 1) * math.pi / 3)

                    # Monthly trend (slight growth)
                    trend_factor = 1.0 + 0.002 * day

                    # Random noise
                    noise = random.gauss(0, demand_std * 0.5)

                    forecast = max(0, base_daily_demand * weekday_factor * trend_factor + noise)
                    daily_forecast.append(round(forecast, 1))

                demand_forecast[product_def.sku] = daily_forecast

                # Break down demand by segment
                weekly_demand = sum(daily_forecast[:7])
                segment_shares = {
                    "strategic": (0.30, 0.99),  # share, otif_target
                    "standard": (0.50, 0.95),
                    "transactional": (0.20, 0.90),
                }
                for segment, (share, _) in segment_shares.items():
                    demand_by_segment[segment][product_def.sku] = round(weekly_demand * share, 1)

        return {
            "products": products_data,
            "suppliers_by_sku": suppliers_by_sku,
            "demand_forecast": demand_forecast,
            "demand_by_segment": demand_by_segment,
            "planning_horizon_days": planning_horizon_days,
            "base_date": base_date.isoformat(),
        }

    def generate_sop_parameters(self) -> Dict[str, Any]:
        """
        Generate default S&OP parameters for Food Dist.

        Returns parameters in the format expected by the Planning Cascade.
        """
        return {
            "service_tiers": [
                {"segment": "strategic", "otif_floor": 0.99, "fill_rate_target": 0.99},
                {"segment": "standard", "otif_floor": 0.95, "fill_rate_target": 0.98},
                {"segment": "transactional", "otif_floor": 0.90, "fill_rate_target": 0.95},
            ],
            "category_policies": [
                {"category": "frz_protein", "safety_stock_wos": 2.0, "dos_ceiling": 21, "expedite_cap": 15000},
                {"category": "ref_dairy", "safety_stock_wos": 1.5, "dos_ceiling": 14, "expedite_cap": 10000},
                {"category": "dry_pantry", "safety_stock_wos": 3.0, "dos_ceiling": 45, "expedite_cap": 5000},
                {"category": "frz_dessert", "safety_stock_wos": 2.0, "dos_ceiling": 28, "expedite_cap": 8000},
                {"category": "bev", "safety_stock_wos": 2.5, "dos_ceiling": 35, "expedite_cap": 6000},
            ],
            "financial_guardrails": {
                "total_inventory_cap": 2500000,
                "gmroi_target": 3.0,
                "max_expedite_total": 50000,
            },
        }


# Alias for backward compatibility with cascade orchestrator
FoodDistConfigGenerator_Sync = FoodDistCascadeDataGenerator

#!/usr/bin/env python3
"""
Seed Food Dist Planning & Execution Demo Data

Generates comprehensive demo data for the Food Dist Production Customer so that
every Planning and Execution dashboard renders meaningful information.

Data Generated:
  - 52-week forecasts (P10/P50/P90) for all 25 products at DC
  - Inventory policies (doc_dem) per product at DC
  - Current inventory levels per product at DC
  - Supply plans (PO requests) from suppliers
  - MPS plan with weekly quantities and capacity checks
  - Planning cycles with snapshots
  - 12 months of agent performance metrics
  - S&OP worklist items (8 items)
  - Agent decisions (30+ records)
  - Purchase orders with line items
  - Inventory optimization records

Prerequisites:
  - Run seed_dot_foods_demo.py first (creates customer + users)
  - Run seed_food_dist_hierarchies.py first (creates SC config, sites, products)

Usage:
    docker compose exec backend python scripts/seed_food_dist_planning_data.py

    # Or directly:
    cd backend && python scripts/seed_food_dist_planning_data.py
"""

import sys
import random
import math
from pathlib import Path
from datetime import datetime, date, timedelta

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from app.db.session import sync_engine
from app.models.tenant import Tenant, TenantMode
from app.models.user import User
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import (
    Product, Forecast, InvPolicy, InvLevel, SupplyPlan,
)
from app.models.mps import MPSPlan, MPSPlanItem, MPSCapacityCheck, MPSStatus
from app.models.planning_cycle import (
    PlanningCycle, PlanningSnapshot, CycleType, CycleStatus, SnapshotType,
)
from app.models.decision_tracking import (
    PerformanceMetric, SOPWorklistItem, AgentDecision,
    DecisionType, DecisionStatus, DecisionUrgency,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.analytics import InventoryOptimization
from app.models.trm_training_data import (
    TRMReplayBuffer, ATPDecisionLog, ATPOutcome,
    RebalancingDecisionLog, RebalancingOutcome,
    PODecisionLog, POOutcome,
    OrderTrackingDecisionLog, OrderTrackingOutcome,
    DecisionSource, OutcomeStatus,
)

# Attempt to import optional models
try:
    from app.models.mps import MPSKeyMaterialRequirement
    HAS_KEY_MATERIALS = True
except ImportError:
    HAS_KEY_MATERIALS = False

try:
    from app.models.production_order import ProductionOrder
    HAS_PRODUCTION_ORDERS = True
except ImportError:
    HAS_PRODUCTION_ORDERS = False

try:
    from app.models.planning_cycle import PlanningDecision
    HAS_PLANNING_DECISIONS = True
except ImportError:
    HAS_PLANNING_DECISIONS = False

try:
    from app.models.supply_plan import SupplyPlanRequest, SupplyPlanResult, PlanStatus
    HAS_SUPPLY_PLAN_REQUESTS = True
except ImportError:
    HAS_SUPPLY_PLAN_REQUESTS = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED = 42
random.seed(SEED)

TODAY = date.today()
# Start forecasts from the beginning of the current week (Monday)
FORECAST_START = TODAY - timedelta(days=TODAY.weekday())
FORECAST_HISTORY_WEEKS = 104
FORECAST_FUTURE_WEEKS = 52

# Product demand profiles (cases/week P50)
# Maps SKU suffix -> (weekly_mean, cv, seasonality_amplitude)
PRODUCT_DEMAND_PROFILES = {
    # Frozen Proteins - steady demand
    "FP001": (120, 0.15, 0.08),  # Chicken Breast IQF
    "FP002": (80, 0.12, 0.05),   # Beef Patties
    "FP003": (60, 0.18, 0.10),   # Pork Chops
    "FP004": (45, 0.20, 0.06),   # Turkey Breast
    "FP005": (35, 0.25, 0.04),   # Seafood Mix
    # Refrigerated Dairy - higher volume, seasonal
    "RD001": (250, 0.10, 0.12),  # Cheddar Block
    "RD002": (200, 0.12, 0.10),  # Mozzarella Block
    "RD003": (180, 0.14, 0.08),  # Cream Cheese
    "RD004": (300, 0.08, 0.15),  # Greek Yogurt
    "RD005": (100, 0.16, 0.06),  # Butter
    # Dry Goods - stable demand
    "DP001": (160, 0.10, 0.05),  # Pasta
    "DP002": (140, 0.12, 0.04),  # Rice
    "DP003": (120, 0.14, 0.03),  # Flour
    "DP004": (130, 0.11, 0.06),  # Sugar
    "DP005": (180, 0.09, 0.08),  # Coffee
    # Frozen Desserts - highly seasonal
    "FD001": (70, 0.20, 0.35),   # Ice Cream
    "FD002": (40, 0.25, 0.30),   # Sorbet
    "FD003": (50, 0.22, 0.28),   # Gelato
    "FD004": (55, 0.18, 0.20),   # Pie
    "FD005": (45, 0.20, 0.22),   # Cake
    # Beverages - very seasonal
    "BV001": (180, 0.12, 0.25),  # Orange Juice
    "BV002": (100, 0.15, 0.20),  # Apple Juice
    "BV003": (80, 0.18, 0.30),   # Lemonade
    "BV004": (150, 0.10, 0.35),  # Iced Tea
    "BV005": (60, 0.22, 0.15),   # Kombucha
}

# Supplier -> product category mapping
SUPPLIER_PRODUCT_MAP = {
    "TYSON": ["FP001", "FP002", "FP004"],       # Proteins
    "KRAFT": ["RD001", "RD002", "RD003"],         # Dairy
    "GENMILLS": ["DP001", "DP003", "DP004"],      # Dry goods
    "NESTLE": ["RD004", "DP005", "FD003"],        # Mixed
    "TROP": ["BV001", "BV002", "BV003"],          # Juices
    "SYSCOMEAT": ["FP003", "FP005"],              # Meats
    "LANDOLAKES": ["RD005"],                       # Butter
    "CONAGRA": ["DP002", "FD004", "FD005"],       # Mixed
    "RICHPROD": ["FD001", "FD002"],               # Frozen desserts
    "COCACOLA": ["BV004", "BV005"],               # Beverages
}

# S&OP Worklist item definitions
WORKLIST_ITEMS = [
    {
        "item_code": "SOP-001",
        "item_name": "Frozen Protein Portfolio Review",
        "category": "Portfolio",
        "issue_type": "PORTFOLIO",
        "issue_summary": "Chicken Breast IQF (FP001) demand trending 15% above forecast. Consider increasing safety stock from 7 to 10 days coverage.",
        "impact_value": 45000.0,
        "impact_description": "$45K potential stockout cost if not adjusted",
        "impact_type": "negative",
        "due_description": "Friday",
        "urgency": "URGENT",
        "agent_recommendation": "Increase safety stock to 10 DOS and place expedite PO for 500 cases from Tyson Foods",
        "agent_reasoning": "Demand has exceeded P90 forecast in 3 of last 4 weeks. Current safety stock covers only 5.2 days at elevated demand rate. Tyson has 98% on-time delivery, enabling reliable 1-day replenishment.",
    },
    {
        "item_code": "SOP-002",
        "item_name": "DC Capacity Utilization Alert",
        "category": "Capacity",
        "issue_type": "CAPACITY",
        "issue_summary": "Salt Lake City DC at 92% capacity utilization. Frozen storage approaching max at 94%. Risk of receiving delays.",
        "impact_value": 120000.0,
        "impact_description": "$120K risk from receiving delays and spoilage",
        "impact_type": "negative",
        "due_description": "48 hours",
        "urgency": "URGENT",
        "agent_recommendation": "Reduce frozen inbound by 8% for next 2 weeks and expedite outbound to high-velocity customers",
        "agent_reasoning": "Frozen capacity at 141,000/150,000 cases. Three large Tyson and Sysco POs arriving this week. Historical data shows >93% utilization correlates with 2.5x receiving delay risk.",
    },
    {
        "item_code": "SOP-003",
        "item_name": "New Product Introduction: Organic Kombucha",
        "category": "New Product",
        "issue_type": "NPI",
        "issue_summary": "BV005 Kombucha Ginger launch exceeding plan by 40%. Need to secure additional supply from vendor.",
        "impact_value": 28000.0,
        "impact_description": "$28K incremental revenue opportunity",
        "impact_type": "positive",
        "due_description": "EOD",
        "urgency": "STANDARD",
        "agent_recommendation": "Increase BV005 forecast by 35% for next 8 weeks and negotiate volume discount with Coca-Cola",
        "agent_reasoning": "NPI curve analysis shows BV005 tracking 'fast adopter' pattern. Similar launches (BV003 Lemonade) stabilized at 1.3x initial forecast. Coca-Cola has confirmed capacity for 40% uplift.",
    },
    {
        "item_code": "SOP-004",
        "item_name": "Summer Promotion: Frozen Desserts Bundle",
        "category": "Promotion",
        "issue_type": "PROMO",
        "issue_summary": "Q3 frozen desserts promotion starting in 6 weeks. Need to build inventory for Ice Cream, Sorbet, and Gelato SKUs.",
        "impact_value": 85000.0,
        "impact_description": "$85K expected incremental sales",
        "impact_type": "positive",
        "due_description": "Next S&OP",
        "urgency": "STANDARD",
        "agent_recommendation": "Pre-build 3 weeks of promotional inventory starting now; increase FD001/FD002/FD003 orders by 60% for 4 weeks",
        "agent_reasoning": "Historical summer promotions show 55-75% demand uplift for frozen desserts. 6-week lead time requires immediate action. Rich Products confirmed 60% capacity increase is feasible.",
    },
    {
        "item_code": "SOP-005",
        "item_name": "Greek Yogurt Safety Stock Policy Review",
        "category": "Inventory",
        "issue_type": "POLICY",
        "issue_summary": "RD004 Greek Yogurt has had 0 stockouts in 16 weeks with 12 DOS safety stock. Conformal analysis suggests 8 DOS sufficient for 95% SL.",
        "impact_value": 35000.0,
        "impact_description": "$35K inventory holding cost reduction opportunity",
        "impact_type": "positive",
        "due_description": "Next review",
        "urgency": "LOW",
        "agent_recommendation": "Reduce RD004 safety stock from 12 to 9 DOS (gradual step-down to validate conformal prediction)",
        "agent_reasoning": "Conformal prediction model calibrated on 52 weeks shows 9 DOS provides 96.2% coverage. Current 12 DOS is over-stocked by ~$35K annually. Recommend gradual reduction to validate model accuracy.",
    },
    {
        "item_code": "SOP-006",
        "item_name": "Western Region Delivery Performance",
        "category": "Network",
        "issue_type": "NETWORK",
        "issue_summary": "On-time delivery to Portland (PDX) and Eugene (EUG) declining from 96% to 89%. Carrier capacity constraints on I-84 corridor.",
        "impact_value": 62000.0,
        "impact_description": "$62K at-risk revenue from customer service issues",
        "impact_type": "negative",
        "due_description": "This week",
        "urgency": "URGENT",
        "agent_recommendation": "Add secondary carrier for Portland/Eugene routes and increase forward stock at nearest relay point",
        "agent_reasoning": "I-84 construction causing 4-6 hour delays. Primary carrier (XPO) at 98% capacity on this lane. Adding secondary carrier (ODFL) would cost 8% more per shipment but restore 95%+ OTIF within 1 week.",
    },
    {
        "item_code": "SOP-007",
        "item_name": "Flour SKU Rationalization",
        "category": "SKU Rationalization",
        "issue_type": "DISCONTINUATION",
        "issue_summary": "DP003 Flour All Purpose has declining margins (18% -> 12%) and below-average velocity. Consider replacing with higher-margin specialty flour.",
        "impact_value": 15000.0,
        "impact_description": "$15K margin improvement potential",
        "impact_type": "trade-off",
        "due_description": "Q3 planning",
        "urgency": "LOW",
        "agent_recommendation": "Phase out standard flour over 8 weeks; introduce organic all-purpose flour at 22% margin",
        "agent_reasoning": "DP003 velocity 22% below category average. Customer survey shows 68% of foodservice accounts prefer organic options. Similar transitions in other categories yielded 4-6% margin improvement.",
    },
    {
        "item_code": "SOP-008",
        "item_name": "Cold Chain CapEx: Refrigerated Expansion",
        "category": "CapEx",
        "issue_type": "CAPEX",
        "issue_summary": "Refrigerated dairy demand growing 8% YoY. Current refrigerated capacity will reach 95% by Q4. Expansion business case needed.",
        "impact_value": 250000.0,
        "impact_description": "$250K CapEx investment for 40% capacity increase",
        "impact_type": "trade-off",
        "due_description": "Board review",
        "urgency": "STANDARD",
        "agent_recommendation": "Approve Phase 1 expansion (20% capacity increase at $125K) with Phase 2 contingent on Q4 demand validation",
        "agent_reasoning": "Phased approach reduces risk. Phase 1 ROI: 18 months at current growth rate. Monte Carlo analysis shows 78% probability of needing Phase 2 within 12 months of Phase 1 completion.",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def seasonal_demand(week_num: int, mean: float, cv: float, amplitude: float) -> float:
    """Generate seasonal demand with noise. Peak in summer (weeks 22-34)."""
    # Seasonal component: peak around week 28 (mid-July)
    seasonal = amplitude * math.sin(2 * math.pi * (week_num - 10) / 52)
    base = mean * (1 + seasonal)
    # Add random noise
    noise = random.gauss(0, mean * cv * 0.5)
    return max(10, round(base + noise, 1))


def generate_forecast_week(week_num: int, sku: str) -> dict:
    """Generate P10/P50/P90 forecast values for a given week and SKU."""
    profile = PRODUCT_DEMAND_PROFILES.get(sku)
    if not profile:
        return {"p10": 50, "p50": 100, "p90": 150}
    mean, cv, amplitude = profile
    p50 = seasonal_demand(week_num, mean, cv, amplitude)
    spread = p50 * cv
    p10 = max(5, round(p50 - 1.28 * spread, 1))
    p90 = round(p50 + 1.28 * spread, 1)
    return {"p10": p10, "p50": p50, "p90": p90}


def _market_bucket_for_site(site: Site) -> str:
    """Infer market bucket from site geography code."""
    geo = ((site.geo_id or "") + " " + (site.name or "")).upper()
    if any(code in geo for code in ("_REG_SW", "_CA", "_AZ", "LAX", "SFO", "SDG", "SAC", "PHX", "TUS", "MES")):
        return "SW"
    if any(code in geo for code in ("_REG_NW", "_OR", "_WA", "PDX", "EUG", "SAL", "SEA", "TAC", "SPO")):
        return "NW"
    return "MTN"


def _triangular_parameters_from_baseline(
    baseline_forecast: float,
    sku: str,
    market_bucket: str,
) -> dict:
    """
    Build triangular demand parameters around current product-site baseline forecast.
    Returns min/median/max and mapped p10/p50/p90 values.
    """
    # Product adjustments (skew + variance)
    product_adjustments = {
        "FP": {"vol": 1.05, "left": 1.00, "right": 1.10},  # proteins: moderate right skew
        "RD": {"vol": 0.90, "left": 1.00, "right": 0.95},  # dairy: tighter spread
        "DP": {"vol": 0.80, "left": 0.95, "right": 0.90},  # dry: most stable
        "FD": {"vol": 1.35, "left": 0.90, "right": 1.35},  # frozen desserts: strong right skew
        "BV": {"vol": 1.25, "left": 0.95, "right": 1.30},  # beverages: high seasonal spikes
    }
    market_adjustments = {
        "NW": {"vol": 0.95, "left": 1.00, "right": 1.00},
        "SW": {"vol": 1.15, "left": 1.05, "right": 1.20},
        "MTN": {"vol": 0.85, "left": 0.90, "right": 0.90},
    }

    base_profile = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.16, 0.08))
    base_cv = max(0.08, float(base_profile[1]))
    product_key = sku[:2]
    p_adj = product_adjustments.get(product_key, {"vol": 1.0, "left": 1.0, "right": 1.0})
    m_adj = market_adjustments.get(market_bucket, {"vol": 1.0, "left": 1.0, "right": 1.0})

    down_pct = base_cv * p_adj["vol"] * m_adj["vol"] * p_adj["left"] * m_adj["left"]
    up_pct = base_cv * p_adj["vol"] * m_adj["vol"] * p_adj["right"] * m_adj["right"]

    median_val = max(0.0, float(baseline_forecast))
    min_val = max(0.0, round(median_val * (1.0 - down_pct), 1))
    max_val = round(max(median_val, median_val * (1.0 + up_pct)), 1)
    if max_val <= min_val:
        max_val = round(min_val + max(1.0, median_val * 0.05), 1)

    return {
        "min": min_val,
        "median": round(median_val, 1),
        "max": max_val,
        "market_bucket": market_bucket,
    }


def _forecast_history_is_sufficient(
    db: Session,
    config_id: int,
    site_id: int,
    products: list,
) -> bool:
    """Return True only when each product/site has at least 2 years of weekly history."""
    history_cutoff = FORECAST_START
    for product in products:
        history_rows = db.query(Forecast).filter(
            Forecast.config_id == config_id,
            Forecast.site_id == site_id,
            Forecast.product_id == product.id,
            Forecast.forecast_date < history_cutoff,
        ).count()
        if history_rows < FORECAST_HISTORY_WEEKS:
            return False
    return True


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def seed_forecasts(db: Session, config: SupplyChainConfig, dc_site: Site,
                   products: list, company_id: str) -> int:
    """Generate 2 years history + 52-week forward forecasts for all products at the DC."""
    print("\n1. Seeding Forecasts (104 history + 52 forward weeks × products)...")

    existing = db.query(Forecast).filter(
        Forecast.config_id == config.id,
        Forecast.site_id == dc_site.id,
    ).count()

    if existing > 0 and _forecast_history_is_sufficient(db, config.id, dc_site.id, products):
        print(f"   Forecasts already exist ({existing} records) with >=2 years history. Skipping.")
        return existing

    if existing > 0:
        print(f"   Existing forecast rows found ({existing}) but history < 2 years. Rebuilding...")
        db.query(Forecast).filter(
            Forecast.config_id == config.id,
            Forecast.site_id == dc_site.id,
        ).delete(synchronize_session=False)
        db.flush()

    count = 0
    market_bucket = _market_bucket_for_site(dc_site)
    for product in products:
        sku = product.id.split("_")[-1]  # Extract SKU suffix like FP001
        for week in range(-FORECAST_HISTORY_WEEKS, FORECAST_FUTURE_WEEKS):
            forecast_date = FORECAST_START + timedelta(weeks=week)
            vals = generate_forecast_week(week, sku)
            tri = _triangular_parameters_from_baseline(vals["p50"], sku, market_bucket)

            forecast = Forecast(
                company_id=company_id,
                product_id=product.id,
                site_id=dc_site.id,
                forecast_date=forecast_date,
                forecast_type="statistical",
                forecast_level="product",
                forecast_method="exponential_smoothing",
                forecast_quantity=tri["median"],
                forecast_p10=tri["min"],
                forecast_p50=tri["median"],
                forecast_median=tri["median"],
                forecast_p90=tri["max"],
                forecast_std_dev=round((tri["max"] - tri["min"]) / 2.56, 2),
                forecast_confidence=round(random.uniform(0.78, 0.95), 3),
                forecast_error=round(random.uniform(-0.08, 0.12), 4),
                forecast_bias=round(random.uniform(-0.05, 0.05), 4),
                is_active="Y",
                config_id=config.id,
                demand_pattern={
                    "distribution": {
                        "type": "triangular",
                        "min": tri["min"],
                        "mode": tri["median"],
                        "median": tri["median"],
                        "max": tri["max"],
                    },
                    "drivers": {
                        "market_bucket": tri["market_bucket"],
                        "product_family": sku[:2],
                    },
                },
                source="seed_food_dist_planning_data",
                source_update_dttm=datetime.now(),
                created_dttm=datetime.now(),
            )
            db.add(forecast)
            count += 1

    db.flush()
    print(f"   Created {count} forecast records.")
    return count


def seed_inventory_policies(db: Session, config: SupplyChainConfig, dc_site: Site,
                            products: list, company_id: str) -> int:
    """Generate inventory policies (doc_dem) per product at DC."""
    print("\n2. Seeding Inventory Policies...")

    existing = db.query(InvPolicy).filter(
        InvPolicy.config_id == config.id,
        InvPolicy.site_id == str(dc_site.id),
    ).count()
    if existing > 0:
        print(f"   Inventory policies already exist ({existing} records). Skipping.")
        return existing

    # Policy parameters by product category
    CATEGORY_POLICIES = {
        "FP": {"ss_days": 10, "review_period": 7, "service_level": 0.95},   # Frozen Proteins
        "RD": {"ss_days": 7, "review_period": 3, "service_level": 0.97},    # Refrigerated Dairy (short shelf life)
        "DP": {"ss_days": 14, "review_period": 7, "service_level": 0.93},   # Dry Goods (stable)
        "FD": {"ss_days": 10, "review_period": 7, "service_level": 0.94},   # Frozen Desserts
        "BV": {"ss_days": 5, "review_period": 3, "service_level": 0.96},    # Beverages (fresh)
    }

    count = 0
    for product in products:
        sku = product.id.split("_")[-1]
        cat_prefix = sku[:2]
        policy_params = CATEGORY_POLICIES.get(cat_prefix, {"ss_days": 7, "review_period": 7, "service_level": 0.95})
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]

        policy = InvPolicy(
            company_id=company_id,
            site_id=dc_site.id,
            product_id=product.id,
            ss_policy="doc_dem",
            ss_days=policy_params["ss_days"],
            service_level=policy_params["service_level"],
            review_period=policy_params["review_period"],
            reorder_point=round(mean_demand * policy_params["ss_days"] / 7 * 1.2, 0),
            order_up_to_level=round(mean_demand * (policy_params["ss_days"] + policy_params["review_period"]) / 7 * 1.3, 0),
            min_order_quantity=round(mean_demand * 0.5, 0),
            max_order_quantity=round(mean_demand * 4, 0),
            eff_start_date=datetime(2026, 1, 1),
            is_active="true",
            is_deleted="false",
            config_id=config.id,
            source="seed_food_dist_planning_data",
            source_update_dttm=datetime.now(),
        )
        db.add(policy)
        count += 1

    db.flush()
    print(f"   Created {count} inventory policy records.")
    return count


def seed_inventory_levels(db: Session, config: SupplyChainConfig, dc_site: Site,
                          products: list, company_id: str) -> int:
    """Generate current inventory level snapshots at the DC."""
    print("\n3. Seeding Inventory Levels...")

    existing = db.query(InvLevel).filter(
        InvLevel.config_id == config.id,
        InvLevel.site_id == str(dc_site.id),
    ).count()
    if existing > 0:
        print(f"   Inventory levels already exist ({existing} records). Skipping.")
        return existing

    count = 0
    for product in products:
        sku = product.id.split("_")[-1]
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]

        # Inventory = roughly 2 weeks of demand +/- some variation
        on_hand = round(mean_demand * random.uniform(1.2, 3.0), 0)
        in_transit = round(mean_demand * random.uniform(0.3, 1.0), 0)
        on_order = round(mean_demand * random.uniform(0.5, 1.5), 0)
        allocated = round(on_hand * random.uniform(0.1, 0.3), 0)
        available = max(0, on_hand - allocated)

        inv_level = InvLevel(
            company_id=company_id,
            product_id=product.id,
            site_id=dc_site.id,
            inventory_date=TODAY,
            on_hand_qty=on_hand,
            in_transit_qty=in_transit,
            on_order_qty=on_order,
            allocated_qty=allocated,
            available_qty=available,
            reserved_qty=0,
            config_id=config.id,
            source="seed_food_dist_planning_data",
            source_update_dttm=datetime.now(),
        )
        db.add(inv_level)
        count += 1

    db.flush()
    print(f"   Created {count} inventory level records.")
    return count


def seed_supply_plans(db: Session, config: SupplyChainConfig, dc_site: Site,
                      site_map: dict, products: list, company_id: str) -> int:
    """Generate 13-week supply plans (PO requests from suppliers)."""
    print("\n4. Seeding Supply Plans (13-week horizon)...")

    existing = db.query(SupplyPlan).filter(
        SupplyPlan.config_id == config.id,
    ).count()
    if existing > 0:
        print(f"   Supply plans already exist ({existing} records). Skipping.")
        return existing

    # Build reverse map: SKU -> supplier site name
    sku_to_supplier = {}
    for supplier_name, skus in SUPPLIER_PRODUCT_MAP.items():
        for sku in skus:
            sku_to_supplier[sku] = supplier_name

    count = 0
    for product in products:
        sku = product.id.split("_")[-1]
        profile = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))
        mean_demand = profile[0]
        supplier_name = sku_to_supplier.get(sku)
        supplier_site = site_map.get(supplier_name)

        for week in range(13):
            plan_date = FORECAST_START + timedelta(weeks=week)
            vals = generate_forecast_week(week, sku)
            demand = vals["p50"]
            safety_stock = round(mean_demand * 1.5, 0)
            opening_inv = round(mean_demand * random.uniform(1.5, 2.5), 0)
            closing_inv = max(0, round(opening_inv - demand + mean_demand, 0))
            planned_qty = max(0, round(demand + safety_stock - opening_inv, 0))

            sp = SupplyPlan(
                company_id=company_id,
                product_id=product.id,
                site_id=dc_site.id,
                plan_date=plan_date,
                plan_type="po_request",
                planning_group="FoodDist_Weekly",
                forecast_quantity=demand,
                demand_quantity=demand,
                supply_quantity=planned_qty,
                opening_inventory=opening_inv,
                closing_inventory=closing_inv,
                safety_stock=safety_stock,
                reorder_point=round(mean_demand * 1.2, 0),
                planned_order_quantity=planned_qty,
                planned_order_date=plan_date - timedelta(days=random.randint(1, 3)),
                planned_receipt_date=plan_date,
                from_site_id=supplier_site.id if supplier_site else None,
                planner_name="AI Agent (TRM)",
                order_cost=round(planned_qty * (product.unit_cost or 25.0), 2),
                plan_version="v2026-W06",
                config_id=config.id,
                source="seed_food_dist_planning_data",
                source_update_dttm=datetime.now(),
            )
            db.add(sp)
            count += 1

    db.flush()
    print(f"   Created {count} supply plan records.")
    return count


def seed_mps_plan(db: Session, config: SupplyChainConfig, dc_site: Site,
                  products: list, user: User) -> int:
    """Create an MPS plan with weekly quantities and capacity checks."""
    print("\n5. Seeding MPS Plan...")

    existing = db.query(MPSPlan).filter(
        MPSPlan.supply_chain_config_id == config.id,
    ).count()
    if existing > 0:
        print(f"   MPS plan already exists ({existing} plans). Skipping.")
        return existing

    # Create MPS Plan
    plan_start = datetime.combine(FORECAST_START, datetime.min.time())
    plan_end = plan_start + timedelta(weeks=52)

    mps_plan = MPSPlan(
        name="Food Dist Annual Plan 2026",
        description="52-week master production schedule for Food Dist Distribution Network",
        supply_chain_config_id=config.id,
        planning_horizon_weeks=52,
        bucket_size_days=7,
        start_date=plan_start,
        end_date=plan_end,
        status=MPSStatus.APPROVED,
        created_by=user.id,
        approved_by=user.id,
        approved_at=datetime.now() - timedelta(days=3),
        created_at=datetime.now() - timedelta(days=7),
        updated_at=datetime.now() - timedelta(days=3),
    )
    db.add(mps_plan)
    db.flush()
    print(f"   Created MPS Plan: {mps_plan.name} (ID: {mps_plan.id})")

    # Create MPS Plan Items (one per product)
    item_count = 0
    for product in products:
        sku = product.id.split("_")[-1]
        profile = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))

        # Generate 52 weekly quantities
        weekly_qtys = []
        for week in range(52):
            vals = generate_forecast_week(week, sku)
            # MPS quantity = slightly above P50 to buffer
            qty = round(vals["p50"] * random.uniform(1.02, 1.10), 1)
            weekly_qtys.append(qty)

        item = MPSPlanItem(
            plan_id=mps_plan.id,
            product_id=product.id,
            site_id=dc_site.id,  # Integer FK
            weekly_quantities=weekly_qtys,
            lot_size_rule="EOQ",
            lot_size_value=round(profile[0] * 2, 0),
        )
        db.add(item)
        item_count += 1

    # Create capacity checks
    resources = [
        ("Frozen Storage", 150000, 0.92),
        ("Refrigerated Storage", 200000, 0.85),
        ("Dry Storage", 300000, 0.68),
        ("Receiving Dock", 50000, 0.78),
        ("Shipping Dock", 50000, 0.82),
    ]
    cap_count = 0
    for week in range(13):  # 13-week capacity check
        period_start = plan_start + timedelta(weeks=week)
        period_end = period_start + timedelta(days=6)
        for res_name, capacity, base_util in resources:
            utilization = base_util + random.uniform(-0.05, 0.08)
            required = round(capacity * utilization, 0)
            cap_check = MPSCapacityCheck(
                plan_id=mps_plan.id,
                resource_name=res_name,
                site_id=dc_site.id,  # Integer FK
                period_start=period_start,
                period_end=period_end,
                required_capacity=required,
                available_capacity=capacity,
                utilization_percent=round(utilization * 100, 1),
                is_overloaded=utilization > 0.95,
                overload_amount=max(0, round(required - capacity, 0)),
            )
            db.add(cap_check)
            cap_count += 1

    db.flush()
    print(f"   Created {item_count} MPS plan items and {cap_count} capacity checks.")
    return item_count


def seed_planning_cycles(db: Session, config: SupplyChainConfig, tenant: Tenant,
                         user: User) -> int:
    """Create S&OP planning cycles with snapshots."""
    print("\n6. Seeding Planning Cycles...")

    existing = db.query(PlanningCycle).filter(
        PlanningCycle.tenant_id == tenant.id,
    ).count()
    if existing > 0:
        print(f"   Planning cycles already exist ({existing} cycles). Skipping.")
        return existing

    count = 0
    # Create 6 weekly cycles (last 6 weeks)
    for i in range(6):
        weeks_ago = 5 - i
        cycle_start = TODAY - timedelta(weeks=weeks_ago)
        cycle_end = cycle_start + timedelta(days=6)
        week_num = cycle_start.isocalendar()[1]

        # Older cycles are closed, recent ones are in various states
        if weeks_ago >= 3:
            status = CycleStatus.CLOSED
        elif weeks_ago == 2:
            status = CycleStatus.APPROVED
        elif weeks_ago == 1:
            status = CycleStatus.REVIEW
        else:
            status = CycleStatus.PLANNING

        cycle = PlanningCycle(
            name=f"S&OP Week {week_num}",
            code=f"2026-W{week_num:02d}",
            cycle_type=CycleType.WEEKLY,
            description=f"Weekly S&OP planning cycle for week {week_num}",
            tenant_id=tenant.id,
            config_id=config.id,
            period_start=cycle_start,
            period_end=cycle_end,
            planning_horizon_weeks=52,
            status=status,
            metrics_summary={
                "total_snapshots": random.randint(2, 5),
                "total_decisions": random.randint(8, 25),
                "ai_recommendations": random.randint(15, 40),
                "human_overrides": random.randint(2, 8),
                "kpis": {
                    "forecast_accuracy": round(random.uniform(0.82, 0.94), 3),
                    "otif": round(random.uniform(0.91, 0.97), 3),
                    "inventory_dos": round(random.uniform(8, 14), 1),
                },
            },
            created_at=datetime.combine(cycle_start, datetime.min.time()),
            updated_at=datetime.combine(cycle_end, datetime.min.time()),
        )
        if status in (CycleStatus.APPROVED, CycleStatus.CLOSED):
            cycle.approved_by = user.id
            cycle.approved_at = datetime.combine(cycle_end, datetime.min.time())

        db.add(cycle)
        db.flush()

        # Create baseline snapshot for each cycle
        snapshot = PlanningSnapshot(
            cycle_id=cycle.id,
            version=1,
            snapshot_type=SnapshotType.BASELINE,
            storage_tier="hot",
            uses_delta_storage=False,
            is_materialized=True,
            demand_plan_data={
                "total_demand_p50": round(random.uniform(45000, 55000), 0),
                "products_forecasted": 25,
                "method": "exponential_smoothing",
            },
            supply_plan_data={
                "total_po_value": round(random.uniform(800000, 1200000), 0),
                "total_planned_orders": random.randint(150, 250),
            },
            inventory_data={
                "total_on_hand": round(random.uniform(200000, 300000), 0),
                "avg_dos": round(random.uniform(9, 13), 1),
            },
            kpi_data={
                "otif": round(random.uniform(0.91, 0.97), 3),
                "fill_rate": round(random.uniform(0.94, 0.99), 3),
                "inventory_turns": round(random.uniform(18, 26), 1),
            },
            validation_status="passed",
            data_size_bytes=random.randint(50000, 150000),
            created_at=datetime.combine(cycle_start, datetime.min.time()),
        )
        db.add(snapshot)
        count += 1

    db.flush()
    print(f"   Created {count} planning cycles with snapshots.")
    return count


def seed_performance_metrics(db: Session, tenant: Tenant) -> int:
    """Generate 12 months of agent performance metrics."""
    print("\n7. Seeding Performance Metrics (12 months)...")

    existing = db.query(PerformanceMetric).filter(
        PerformanceMetric.tenant_id == tenant.id,
    ).count()
    if existing > 0:
        print(f"   Performance metrics already exist ({existing} records). Skipping.")
        return existing

    categories = [
        "Frozen Proteins", "Refrigerated Dairy", "Dry Goods",
        "Frozen Desserts", "Beverages",
    ]

    count = 0
    for month_offset in range(12):
        month_start = datetime(2025, 3, 1) + timedelta(days=30 * month_offset)
        month_end = month_start + timedelta(days=29)

        # Simulate improvement trajectory over 12 months
        progress = month_offset / 11.0  # 0 -> 1

        # Overall metrics (no category)
        agent_score_val = round(10 + 65 * progress + random.uniform(-5, 5), 1)
        planner_score_val = round(6 + 39 * progress + random.uniform(-4, 4), 1)
        override_rate_val = round(100 - 75 * progress + random.uniform(-3, 3), 1)
        total_decisions = random.randint(400, 600)
        automation_pct = round(20 + 55 * progress + random.uniform(-3, 3), 1)
        active_planners = max(10, int(25 - 7 * progress))
        total_skus = 25
        agent_decisions_count = int(total_decisions * automation_pct / 100)

        overall = PerformanceMetric(
            tenant_id=tenant.id,
            period_start=month_start,
            period_end=month_end,
            period_type="monthly",
            category=None,  # overall
            total_decisions=total_decisions,
            agent_decisions=agent_decisions_count,
            planner_decisions=total_decisions - agent_decisions_count,
            agent_score=agent_score_val,
            planner_score=planner_score_val,
            override_rate=override_rate_val,
            override_count=int(total_decisions * (1 - automation_pct / 100) * 0.6),
            automation_percentage=automation_pct,
            active_agents=3,
            active_planners=active_planners,
            total_skus=total_skus,
            skus_per_planner=round(total_skus / active_planners, 1),
            created_at=month_end,
        )
        db.add(overall)
        count += 1

        # Per-category metrics
        for cat in categories:
            cat_decisions = random.randint(60, 140)
            cat_auto = round(automation_pct + random.uniform(-10, 10), 1)
            cat_agent_count = int(cat_decisions * min(100, cat_auto) / 100)

            cat_metric = PerformanceMetric(
                tenant_id=tenant.id,
                period_start=month_start,
                period_end=month_end,
                period_type="monthly",
                category=cat,
                total_decisions=cat_decisions,
                agent_decisions=cat_agent_count,
                planner_decisions=cat_decisions - cat_agent_count,
                agent_score=round(agent_score_val + random.uniform(-10, 10), 1),
                planner_score=round(planner_score_val + random.uniform(-8, 8), 1),
                override_rate=round(override_rate_val + random.uniform(-8, 8), 1),
                override_count=random.randint(2, 15),
                automation_percentage=cat_auto,
                active_agents=random.randint(1, 3),
                active_planners=random.randint(2, 5),
                total_skus=5,
                skus_per_planner=round(5 / random.randint(2, 5), 1),
                created_at=month_end,
            )
            db.add(cat_metric)
            count += 1

    db.flush()
    print(f"   Created {count} performance metric records.")
    return count


def seed_sop_worklist(db: Session, tenant: Tenant) -> int:
    """Generate S&OP worklist items."""
    print("\n8. Seeding S&OP Worklist Items...")

    existing = db.query(SOPWorklistItem).filter(
        SOPWorklistItem.tenant_id == tenant.id,
    ).count()
    if existing > 0:
        print(f"   Worklist items already exist ({existing} records). Skipping.")
        return existing

    count = 0
    for item_def in WORKLIST_ITEMS:
        urgency_map = {"URGENT": DecisionUrgency.URGENT, "STANDARD": DecisionUrgency.STANDARD, "LOW": DecisionUrgency.LOW}

        item = SOPWorklistItem(
            tenant_id=tenant.id,
            item_code=item_def["item_code"],
            item_name=item_def["item_name"],
            category=item_def["category"],
            issue_type=item_def["issue_type"],
            issue_summary=item_def["issue_summary"],
            impact_value=item_def["impact_value"],
            impact_description=item_def["impact_description"],
            impact_type=item_def.get("impact_type", "negative"),
            due_description=item_def["due_description"],
            urgency=urgency_map.get(item_def["urgency"], DecisionUrgency.STANDARD),
            agent_recommendation=item_def.get("agent_recommendation"),
            agent_reasoning=item_def.get("agent_reasoning"),
            status=DecisionStatus.PENDING,
            created_at=datetime.now() - timedelta(hours=random.randint(1, 72)),
        )
        db.add(item)
        count += 1

    db.flush()
    print(f"   Created {count} worklist items.")
    return count


def seed_agent_decisions(db: Session, tenant: Tenant, products: list) -> int:
    """Generate agent decision records."""
    print("\n9. Seeding Agent Decisions...")

    existing = db.query(AgentDecision).filter(
        AgentDecision.tenant_id == tenant.id,
    ).count()
    if existing > 0:
        print(f"   Agent decisions already exist ({existing} records). Skipping.")
        return existing

    decision_templates = [
        {
            "type": DecisionType.INVENTORY_REBALANCE,
            "summary_template": "Rebalance {product} inventory: transfer {qty} cases",
            "rec_template": "Transfer {qty} cases from overflow to forward pick area to optimize pick efficiency",
            "reasoning_template": "Current forward pick for {product} at {pct}% capacity. Rebalancing reduces pick time by ~12% and prevents stockout in forward area within 2 days.",
        },
        {
            "type": DecisionType.PURCHASE_ORDER,
            "summary_template": "Replenishment PO needed for {product}: {qty} cases",
            "rec_template": "Create PO for {qty} cases of {product} from primary supplier with standard lead time",
            "reasoning_template": "Projected stockout in {days} days at current consumption rate. Safety stock will be breached in {ss_days} days. Recommended order covers {weeks} weeks of demand.",
        },
        {
            "type": DecisionType.SAFETY_STOCK,
            "summary_template": "Safety stock adjustment for {product}: {direction}",
            "rec_template": "{direction} safety stock from {old_ss} to {new_ss} cases",
            "reasoning_template": "Demand variability for {product} has {trend} by {pct}% over last 8 weeks. Conformal prediction interval width {width_change}. Adjusted safety stock maintains {sl}% service level.",
        },
        {
            "type": DecisionType.ATP_ALLOCATION,
            "summary_template": "ATP allocation for {product}: {qty} cases to priority {priority}",
            "rec_template": "Allocate {qty} cases to priority {priority} orders consuming from tiers {tiers}",
            "reasoning_template": "Order at priority {priority} requires {qty} cases. AATP consumption sequence: own tier first, then bottom-up. Available after allocation: {remaining} cases.",
        },
        {
            "type": DecisionType.DEMAND_FORECAST,
            "summary_template": "Forecast adjustment for {product}: {direction} {pct}%",
            "rec_template": "Adjust {product} forecast {direction} by {pct}% for next 4 weeks based on trend detection",
            "reasoning_template": "Last 4 weeks actual demand for {product}: {actuals}. Trend: {trend_desc}. Statistical test p-value: {p_value}. Adjustment aligns forecast with observed pattern.",
        },
    ]

    categories = ["Frozen Proteins", "Refrigerated Dairy", "Dry Goods", "Frozen Desserts", "Beverages"]
    statuses = [DecisionStatus.PENDING, DecisionStatus.ACCEPTED, DecisionStatus.ACCEPTED,
                DecisionStatus.ACCEPTED, DecisionStatus.REJECTED, DecisionStatus.AUTO_EXECUTED,
                DecisionStatus.AUTO_EXECUTED, DecisionStatus.AUTO_EXECUTED]

    count = 0
    for i in range(35):
        product = random.choice(products)
        sku = product.id.split("_")[-1]
        cat_prefix = sku[:2]
        cat_map = {"FP": "Frozen Proteins", "RD": "Refrigerated Dairy", "DP": "Dry Goods",
                   "FD": "Frozen Desserts", "BV": "Beverages"}
        category = cat_map.get(cat_prefix, "General")
        template = random.choice(decision_templates)
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
        qty = random.randint(int(mean_demand * 0.3), int(mean_demand * 2))
        status = random.choice(statuses)

        # Populate template variables
        vars_dict = {
            "product": product.description or sku,
            "qty": qty,
            "pct": random.randint(5, 25),
            "days": random.randint(3, 12),
            "ss_days": random.randint(2, 5),
            "weeks": random.randint(2, 6),
            "direction": random.choice(["Increase", "Decrease"]),
            "old_ss": random.randint(50, 200),
            "new_ss": random.randint(60, 250),
            "trend": random.choice(["increased", "decreased"]),
            "width_change": random.choice(["widened 8%", "narrowed 12%", "stable"]),
            "sl": random.choice([95, 96, 97]),
            "priority": random.randint(1, 4),
            "tiers": random.choice(["[2,5,4,3]", "[1,5,4,3,2]", "[3,5,4]"]),
            "remaining": random.randint(20, 500),
            "actuals": str([random.randint(int(mean_demand * 0.8), int(mean_demand * 1.3)) for _ in range(4)]),
            "trend_desc": random.choice(["upward", "downward", "seasonal uplift"]),
            "p_value": round(random.uniform(0.001, 0.05), 4),
        }

        decision = AgentDecision(
            tenant_id=tenant.id,
            decision_type=template["type"],
            item_code=product.id,
            item_name=product.description or sku,
            category=category,
            issue_summary=template["summary_template"].format(**vars_dict),
            impact_value=round(qty * (product.unit_cost or 25.0) * random.uniform(0.5, 1.5), 2),
            impact_description=f"${round(qty * (product.unit_cost or 25.0), 0):,.0f} order value impact",
            agent_recommendation=template["rec_template"].format(**vars_dict),
            agent_reasoning=template["reasoning_template"].format(**vars_dict),
            agent_confidence=round(random.uniform(0.72, 0.98), 3),
            recommended_value=float(qty),
            previous_value=float(random.randint(int(qty * 0.6), int(qty * 1.4))),
            status=status,
            urgency=random.choice([DecisionUrgency.URGENT, DecisionUrgency.STANDARD, DecisionUrgency.STANDARD, DecisionUrgency.LOW]),
            agent_type="trm",
            agent_version="1.2.0",
            planning_cycle=f"2026-W{random.randint(3, 8):02d}",
            created_at=datetime.now() - timedelta(hours=random.randint(1, 240)),
        )

        if status in (DecisionStatus.ACCEPTED, DecisionStatus.REJECTED):
            decision.action_timestamp = decision.created_at + timedelta(hours=random.randint(1, 24))
            decision.user_action = "accept" if status == DecisionStatus.ACCEPTED else "reject"
            if status == DecisionStatus.REJECTED:
                decision.override_reason = random.choice([
                    "Supplier confirmed delay, adjusting timing",
                    "Customer requested hold on this order",
                    "Manual review required - unusual demand pattern",
                    "Budget constraint - deferring to next cycle",
                ])

        if status == DecisionStatus.AUTO_EXECUTED:
            decision.action_timestamp = decision.created_at + timedelta(minutes=random.randint(1, 30))
            decision.outcome_measured = True
            decision.outcome_value = float(qty * random.uniform(0.9, 1.1))
            decision.outcome_quality_score = round(random.uniform(30, 85), 1)

        db.add(decision)
        count += 1

    db.flush()
    print(f"   Created {count} agent decision records.")
    return count


# ---------------------------------------------------------------------------
# TRM Worklist Decisions — per-specialist demo data
# ---------------------------------------------------------------------------

# Reason codes matching TRMDecisionWorklist.jsx REASON_CODES
TRM_REASON_CODES = [
    "MARKET_INTELLIGENCE", "CUSTOMER_COMMITMENT", "CAPACITY_CONSTRAINT",
    "SUPPLIER_ISSUE", "QUALITY_CONCERN", "COST_OPTIMIZATION",
    "SERVICE_LEVEL", "SAFETY_STOCK", "DEMAND_CHANGE",
    "EXPEDITE_REQUIRED", "RISK_MITIGATION", "OTHER",
]

# TRM specialist user emails (from seed_dot_foods_demo.py)
TRM_SPECIALIST_USERS = {
    "atp": "atp@distdemo.com",
    "rebalancing": "rebalancing@distdemo.com",
    "po_creation": "po@distdemo.com",
    "order_tracking": "ordertracking@distdemo.com",
}

# Per-TRM-type decision templates
# Each entry: (summary, recommendation, reasoning, context_extras, override_scenario)
ATP_DECISION_TEMPLATES = [
    {
        "summary": "ATP fulfillment for {product}: {qty} cases to priority {priority} customer",
        "recommendation": "FULFILL {qty} cases from tier {priority} allocation. Consuming from tiers [{tiers}].",
        "reasoning": "Customer order #{order_id} at priority {priority} requests {qty} cases of {product}. AATP check: {available} available in tier {priority}, {total_atp} total ATP. Consumption sequence: own tier first, bottom-up. Post-allocation: {remaining} remaining.",
        "context": {"order_id": None, "priority": None, "available_atp": None, "consumption_tiers": None},
        "override": {"reason_code": "CUSTOMER_COMMITMENT", "reason_text": "Strategic customer — override to full fill from reserve allocation. Customer has annual commitment contract.", "override_key": "qty_fulfilled"},
    },
    {
        "summary": "ATP partial fill: {product} — only {partial_qty}/{qty} available",
        "recommendation": "PARTIAL fill {partial_qty} cases, backorder {backorder_qty} with ETA {eta}.",
        "reasoning": "Order #{order_id} requests {qty} but only {partial_qty} available across all tiers. Backorder {backorder_qty} cases. Next replenishment ETA: {eta}. Customer segment: {segment}.",
        "context": {"order_id": None, "fill_rate": None, "eta": None},
        "override": {"reason_code": "SERVICE_LEVEL", "reason_text": "Override to DEFER entire order — customer prefers complete shipment over partial. Confirmed via phone call.", "override_key": "action_type"},
    },
    {
        "summary": "ATP rejection: {product} — insufficient allocation for P{priority}",
        "recommendation": "REJECT order #{order_id}. No allocation available at priority {priority}. Suggest requoting for next week.",
        "reasoning": "All {product} allocation tiers consumed. Priority {priority} has 0 remaining. Next allocation refresh: {refresh_date}. Alternative: cross-dock from {alt_site} at +2 days lead time.",
        "context": {"order_id": None, "alt_site": None, "refresh_date": None},
        "override": {"reason_code": "EXPEDITE_REQUIRED", "reason_text": "Override to FULFILL from safety stock reserve. Critical customer at risk of switching to competitor.", "override_key": "action_type"},
    },
    {
        "summary": "ATP allocation: {product} reserve for strategic segment",
        "recommendation": "RESERVE {qty} cases of {product} for strategic customer tier. Reduces general pool by {pct}%.",
        "reasoning": "Strategic segment utilization at {util}%. Based on order patterns, reserving {qty} for next 48hr window prevents downstream backorders. Service level impact: {sl_impact}.",
        "context": {"segment": "strategic", "utilization_pct": None},
        "override": {"reason_code": "DEMAND_CHANGE", "reason_text": "Reduce reserve by 30% — demand signal shows customer delaying their seasonal buy.", "override_key": "qty_reserved"},
    },
]

REBALANCING_DECISION_TEMPLATES = [
    {
        "summary": "Transfer {qty} cases of {product} from {from_site} to {to_site}",
        "recommendation": "Transfer {qty} cases via standard route. Expected transit: {transit_days} days. DOS improvement at target: {dos_before} → {dos_after}.",
        "reasoning": "{from_site} has {from_dos} DOS ({from_inv} cases) while {to_site} at critical {to_dos} DOS ({to_inv} cases). Network imbalance CV: {cv}. Transfer reduces CV to {cv_after} and prevents stockout at {to_site} within {stockout_days} days.",
        "context": {"from_site_id": None, "to_site_id": None, "network_cv": None},
        "override": {"reason_code": "CAPACITY_CONSTRAINT", "reason_text": "Reduce transfer qty by 40% — receiving dock at target site is at capacity this week due to seasonal volume surge.", "override_key": "transfer_qty"},
    },
    {
        "summary": "Hold: no rebalancing needed for {product} across network",
        "recommendation": "HOLD — all sites within target DOS range. Network CV: {cv} (threshold: 0.15).",
        "reasoning": "All {num_sites} sites for {product} are between {min_dos} and {max_dos} DOS. Network coefficient of variation {cv} is below threshold. No transfer recommended this cycle.",
        "context": {"network_cv": None, "all_site_dos": None},
        "override": {"reason_code": "MARKET_INTELLIGENCE", "reason_text": "Override to TRANSFER 200 cases to Eastern DC. Large customer order expected next week per sales team intel.", "override_key": "action_type"},
    },
    {
        "summary": "Expedite transfer: {product} from {from_site} to {to_site} (urgent)",
        "recommendation": "EXPEDITE transfer {qty} cases. Use premium carrier for 1-day transit vs standard {transit_days}-day.",
        "reasoning": "{to_site} will stockout in {stockout_hours}h at current burn rate. Standard transfer takes {transit_days} days — too slow. Expedite cost: ${expedite_cost}. Stockout cost avoided: ${stockout_cost}.",
        "context": {"urgency": "expedite", "expedite_cost": None, "stockout_cost_avoided": None},
        "override": {"reason_code": "COST_OPTIMIZATION", "reason_text": "Override to standard transit — can absorb 1 day of low stock by deferring 3 lower-priority orders. Saves $800 expedite cost.", "override_key": "urgency"},
    },
]

PO_CREATION_DECISION_TEMPLATES = [
    {
        "summary": "Replenishment PO for {product}: {qty} cases from {supplier}",
        "recommendation": "Create PO for {qty} cases of {product} from {supplier}. Lead time: {lt} days. Expected receipt: {receipt_date}.",
        "reasoning": "Current DOS: {dos} (target: {target_dos}). Projected stockout in {stockout_days} days at current consumption. Safety stock breach in {ss_breach_days} days. Order covers {coverage_weeks} weeks of demand at P50 forecast.",
        "context": {"supplier": None, "lead_time_days": None, "dos_current": None},
        "override": {"reason_code": "SUPPLIER_ISSUE", "reason_text": "Switch to backup supplier (Hormel). Primary supplier Tyson has quality hold on this SKU per FDA alert issued yesterday.", "override_key": "supplier_id"},
    },
    {
        "summary": "PO timing: defer {product} order by {defer_days} days",
        "recommendation": "DEFER PO for {product} by {defer_days} days. Current inventory sufficient. Ordering now would exceed DOS ceiling.",
        "reasoning": "Current DOS: {dos} vs ceiling: {dos_ceiling}. Ordering now would push to {dos_if_order} DOS, exceeding ceiling by {excess_pct}%. Deferral saves ${holding_savings} in holding costs.",
        "context": {"dos_ceiling": None, "holding_cost_saved": None},
        "override": {"reason_code": "RISK_MITIGATION", "reason_text": "Override to ORDER NOW — hurricane forecast for supplier region. Pre-positioning inventory to avoid supply disruption.", "override_key": "action_type"},
    },
    {
        "summary": "Expedite PO for {product}: qty {qty} from {supplier}",
        "recommendation": "EXPEDITE existing PO #{po_number}. Change from standard to rush delivery (+${expedite_cost}). New ETA: {new_eta}.",
        "reasoning": "Demand spike detected: actual {actual_demand} vs forecast {forecast_demand} ({spike_pct}% above P90). Current inventory will not last until standard PO arrives on {orig_eta}. Expedite cost justified: stockout cost ${stockout_cost} > expedite cost ${expedite_cost}.",
        "context": {"po_number": None, "original_eta": None, "demand_spike_pct": None},
        "override": {"reason_code": "SAFETY_STOCK", "reason_text": "Override: do NOT expedite. Increase safety stock target instead — this demand spike is recurring seasonal pattern, not an anomaly.", "override_key": "action_type"},
    },
]

ORDER_TRACKING_DECISION_TEMPLATES = [
    {
        "summary": "Late PO: {product} from {supplier} — {days_late} days overdue",
        "recommendation": "ESCALATE to supplier account manager. Current status: {status}. Demand impact: {impact}.",
        "reasoning": "PO #{po_number} for {qty} cases was due {due_date}. Now {days_late} days late. Supplier last update: '{last_update}'. Inventory position: {inv_position} cases ({dos} DOS). At current burn, stockout in {stockout_days} days without this receipt.",
        "context": {"po_number": None, "supplier_status": None, "last_update_text": None},
        "override": {"reason_code": "SUPPLIER_ISSUE", "reason_text": "Override to REORDER from backup supplier. Called Tyson — their plant has extended shutdown. No ETA for resumption.", "override_key": "action_type"},
    },
    {
        "summary": "Short shipment: {product} received {received}/{expected} cases",
        "recommendation": "ACCEPT short shipment. File claim for {shortage} shortage. Place supplemental PO for {shortage} cases.",
        "reasoning": "PO #{po_number} received {received} of {expected} cases ({fill_pct}% fill). Shortage of {shortage} cases. Current inventory can absorb {buffer_days} days at reduced level. Recommend supplemental order from same supplier with expedite flag.",
        "context": {"po_number": None, "fill_pct": None, "buffer_days": None},
        "override": {"reason_code": "COST_OPTIMIZATION", "reason_text": "Override: do NOT place supplemental PO. Redistribute from central stock instead. Cheaper than new PO + expedite.", "override_key": "action_type"},
    },
    {
        "summary": "Quality hold: {product} from {supplier} — batch {batch} flagged",
        "recommendation": "QUARANTINE batch {batch} ({qty} cases). Notify QA. Do not allocate pending inspection. ETA for clearance: {clearance_days} days.",
        "reasoning": "Receiving inspection flagged batch {batch}: {quality_issue}. {qty} cases affected. This represents {pct_inv}% of current {product} inventory. If quarantine holds, DOS drops from {dos} to {dos_after}.",
        "context": {"batch_id": None, "quality_issue": None, "quarantine_qty": None},
        "override": {"reason_code": "QUALITY_CONCERN", "reason_text": "Override to REJECT entire batch and file supplier corrective action request (SCAR). Prior batch from same lot had confirmed listeria.", "override_key": "action_type"},
    },
    {
        "summary": "Carrier delay: {product} shipment from {supplier} — ETA revised +{delay_days}d",
        "recommendation": "MONITOR. Revised ETA: {new_eta}. No action needed — inventory buffer sufficient for {buffer_days} days.",
        "reasoning": "Carrier reported {delay_days}-day delay on shipment #{tracking}. Original ETA: {orig_eta}, revised: {new_eta}. Cause: {delay_cause}. Current {product} inventory covers {buffer_days} days. No stockout risk.",
        "context": {"tracking_number": None, "delay_cause": None, "carrier": None},
        "override": {"reason_code": "EXPEDITE_REQUIRED", "reason_text": "Override to EXPEDITE — switch to air freight. This shipment contains items for customer's grand opening event, hard deadline.", "override_key": "action_type"},
    },
]


def seed_trm_worklist_decisions(
    db: Session, tenant: Tenant, config: SupplyChainConfig,
    dc_site: Site, site_map: dict, products: list,
) -> int:
    """
    Generate TRM-specific worklist decisions for each of the 4 TRM specialist users.

    Creates a realistic mix of decisions per TRM type:
    - PENDING (proposed, awaiting review)
    - ACCEPTED (accepted by specialist user)
    - OVERRIDDEN (with structured reason_code + reason_text)
    - REJECTED (agent re-evaluates)
    - AUTO_EXECUTED (high confidence, touchless)

    Also writes expert overrides to trm_replay_buffer with is_expert=True.
    """
    print("\n14. Seeding TRM Worklist Decisions (per specialist)...")

    # Check for existing TRM-specialist decisions (avoid duplicates)
    existing = db.query(AgentDecision).filter(
        AgentDecision.tenant_id == tenant.id,
        AgentDecision.agent_type == "trm_specialist",
    ).count()
    if existing > 0:
        print(f"   TRM worklist decisions already exist ({existing} records). Skipping.")
        return existing

    # Look up TRM specialist users
    specialist_users = {}
    for trm_type, email in TRM_SPECIALIST_USERS.items():
        user = db.query(User).filter(User.email == email).first()
        if user:
            specialist_users[trm_type] = user
        else:
            print(f"   WARNING: TRM specialist user {email} not found. Skipping {trm_type}.")

    if not specialist_users:
        print("   ERROR: No TRM specialist users found. Run seed_food_dist_demo.py first.")
        return 0

    # Map TRM types to decision types and templates
    trm_config = {
        "atp": {
            "decision_type": DecisionType.ATP_ALLOCATION,
            "templates": ATP_DECISION_TEMPLATES,
            "agent_version": "1.3.0-atp",
        },
        "rebalancing": {
            "decision_type": DecisionType.INVENTORY_REBALANCE,
            "templates": REBALANCING_DECISION_TEMPLATES,
            "agent_version": "1.3.0-rebal",
        },
        "po_creation": {
            "decision_type": DecisionType.PURCHASE_ORDER,
            "templates": PO_CREATION_DECISION_TEMPLATES,
            "agent_version": "1.3.0-po",
        },
        "order_tracking": {
            "decision_type": DecisionType.EXCEPTION_RESOLUTION,
            "templates": ORDER_TRACKING_DECISION_TEMPLATES,
            "agent_version": "1.3.0-ot",
        },
    }

    # Status distribution per TRM type (realistic)
    # (status, user_action, is_override)
    status_mix = [
        (DecisionStatus.PENDING, None, False),           # 3 pending
        (DecisionStatus.PENDING, None, False),
        (DecisionStatus.PENDING, None, False),
        (DecisionStatus.ACCEPTED, "accept", False),      # 3 accepted
        (DecisionStatus.ACCEPTED, "accept", False),
        (DecisionStatus.ACCEPTED, "accept", False),
        (DecisionStatus.REJECTED, "override", True),     # 3 overridden
        (DecisionStatus.REJECTED, "override", True),
        (DecisionStatus.REJECTED, "override", True),
        (DecisionStatus.REJECTED, "reject", False),      # 1 rejected
        (DecisionStatus.AUTO_EXECUTED, None, False),      # 2 auto-executed
        (DecisionStatus.AUTO_EXECUTED, None, False),
    ]

    # Supplier names for templates
    supplier_names = list(SUPPLIER_PRODUCT_MAP.keys())
    site_names = [s.name for s in db.query(Site).filter(
        Site.config_id == config.id,
        Site.master_type == "INVENTORY",
    ).all()] or ["DC-Chicago", "DC-Indianapolis"]

    total_decisions = 0
    total_replay = 0
    total_logs = 0

    for trm_type, trm_cfg in trm_config.items():
        user = specialist_users.get(trm_type)
        if not user:
            continue

        templates = trm_cfg["templates"]
        decision_type = trm_cfg["decision_type"]
        agent_version = trm_cfg["agent_version"]

        print(f"   {trm_type}: {user.email} ({len(status_mix)} decisions)...")

        for i, (status, user_action, is_override) in enumerate(status_mix):
            template = templates[i % len(templates)]
            product = random.choice(products)
            sku = product.id.split("_")[-1]
            cat_prefix = sku[:2]
            cat_map = {"FP": "Frozen Proteins", "RD": "Refrigerated Dairy", "DP": "Dry Goods",
                       "FD": "Frozen Desserts", "BV": "Beverages"}
            category = cat_map.get(cat_prefix, "General")
            mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
            qty = random.randint(int(mean_demand * 0.3), int(mean_demand * 2))

            # Template variables
            vars_dict = {
                "product": product.description or sku,
                "qty": qty,
                "partial_qty": int(qty * random.uniform(0.4, 0.8)),
                "backorder_qty": int(qty * random.uniform(0.2, 0.5)),
                "priority": random.randint(1, 4),
                "tiers": random.choice(["2,5,4,3", "1,5,4,3,2", "3,5,4"]),
                "order_id": f"ORD-{random.randint(10000,99999)}",
                "available": random.randint(50, 500),
                "total_atp": random.randint(200, 1500),
                "remaining": random.randint(10, 400),
                "segment": random.choice(["strategic", "standard", "transactional"]),
                "eta": (TODAY + timedelta(days=random.randint(2, 10))).strftime("%b %d"),
                "refresh_date": (TODAY + timedelta(days=random.randint(1, 5))).strftime("%b %d"),
                "alt_site": random.choice(site_names),
                "util": random.randint(65, 95),
                "sl_impact": f"+{random.uniform(0.5, 2.0):.1f}% OTIF",
                "pct": random.randint(5, 25),
                "from_site": random.choice(site_names),
                "to_site": random.choice(site_names),
                "from_dos": round(random.uniform(15, 25), 1),
                "to_dos": round(random.uniform(2, 5), 1),
                "from_inv": random.randint(300, 800),
                "to_inv": random.randint(20, 100),
                "dos_before": round(random.uniform(2, 5), 1),
                "dos_after": round(random.uniform(7, 12), 1),
                "transit_days": random.randint(1, 4),
                "cv": round(random.uniform(0.18, 0.35), 2),
                "cv_after": round(random.uniform(0.08, 0.14), 2),
                "stockout_days": random.randint(2, 8),
                "stockout_hours": random.randint(12, 72),
                "num_sites": random.randint(3, 6),
                "min_dos": round(random.uniform(6, 9), 1),
                "max_dos": round(random.uniform(11, 16), 1),
                "expedite_cost": random.randint(200, 1200),
                "stockout_cost": random.randint(2000, 8000),
                "supplier": random.choice(supplier_names),
                "lt": random.randint(2, 7),
                "receipt_date": (TODAY + timedelta(days=random.randint(3, 14))).strftime("%b %d"),
                "dos": round(random.uniform(3, 8), 1),
                "target_dos": round(random.uniform(8, 14), 1),
                "ss_breach_days": random.randint(1, 4),
                "coverage_weeks": random.randint(2, 6),
                "dos_ceiling": random.randint(18, 25),
                "dos_if_order": random.randint(22, 30),
                "excess_pct": random.randint(8, 25),
                "holding_savings": random.randint(500, 3000),
                "defer_days": random.randint(3, 10),
                "po_number": f"PO-DF-2026-{random.randint(1000,1999)}",
                "actual_demand": random.randint(int(mean_demand * 1.2), int(mean_demand * 1.8)),
                "forecast_demand": int(mean_demand),
                "spike_pct": random.randint(15, 45),
                "orig_eta": (TODAY + timedelta(days=random.randint(5, 12))).strftime("%b %d"),
                "new_eta": (TODAY + timedelta(days=random.randint(2, 6))).strftime("%b %d"),
                "days_late": random.randint(1, 7),
                "due_date": (TODAY - timedelta(days=random.randint(1, 7))).strftime("%b %d"),
                "status": random.choice(["In Transit", "At Origin", "Customs Hold"]),
                "last_update": random.choice([
                    "Shipment delayed at port",
                    "Awaiting carrier pickup",
                    "Weather delay - rerouting",
                    "Partial load, awaiting consolidation",
                ]),
                "inv_position": random.randint(50, 300),
                "received": int(qty * random.uniform(0.6, 0.9)),
                "expected": qty,
                "shortage": int(qty * random.uniform(0.1, 0.4)),
                "fill_pct": random.randint(60, 90),
                "buffer_days": random.randint(2, 7),
                "batch": f"BATCH-{random.randint(100000, 999999)}",
                "quality_issue": random.choice([
                    "Temperature excursion during transit",
                    "Packaging damage on 15% of cases",
                    "Labeling discrepancy (allergen info)",
                    "Short shelf life (< 50% remaining)",
                ]),
                "pct_inv": random.randint(10, 40),
                "dos_after_quarantine": round(random.uniform(3, 7), 1),
                "clearance_days": random.randint(1, 5),
                "tracking": f"TRK-{random.randint(100000, 999999)}",
                "delay_days": random.randint(1, 4),
                "delay_cause": random.choice([
                    "Weather delay on I-70",
                    "Driver hours of service limit",
                    "Mechanical issue on trailer",
                    "Port congestion at origin",
                ]),
                "impact": random.choice(["LOW", "MEDIUM", "HIGH"]),
            }

            # Safe format: only use keys present in the template string
            try:
                summary = template["summary"].format(**vars_dict)
            except KeyError:
                summary = template["summary"]
            try:
                recommendation = template["recommendation"].format(**vars_dict)
            except KeyError:
                recommendation = template["recommendation"]
            try:
                reasoning = template["reasoning"].format(**vars_dict)
            except KeyError:
                reasoning = template["reasoning"]

            # Confidence: higher for auto-executed, lower for those needing review
            if status == DecisionStatus.AUTO_EXECUTED:
                confidence = round(random.uniform(0.92, 0.99), 3)
            elif status == DecisionStatus.PENDING:
                confidence = round(random.uniform(0.65, 0.85), 3)
            else:
                confidence = round(random.uniform(0.72, 0.93), 3)

            created_hours_ago = random.randint(1, 168)  # Up to 1 week
            created_at = datetime.now() - timedelta(hours=created_hours_ago)

            # Build context_data
            context_data = {
                "trm_type": trm_type,
                "site_key": dc_site.name,
                "product_sku": sku,
            }

            decision = AgentDecision(
                tenant_id=tenant.id,
                decision_type=decision_type,
                item_code=product.id,
                item_name=product.description or sku,
                category=category,
                issue_summary=summary,
                impact_value=round(qty * (product.unit_cost or 25.0) * random.uniform(0.5, 1.5), 2),
                impact_description=f"${round(qty * (product.unit_cost or 25.0), 0):,.0f} impact",
                agent_recommendation=recommendation,
                agent_reasoning=reasoning,
                agent_confidence=confidence,
                recommended_value=float(qty),
                previous_value=float(random.randint(int(qty * 0.6), int(qty * 1.4))),
                status=status,
                urgency=random.choice([DecisionUrgency.URGENT, DecisionUrgency.STANDARD, DecisionUrgency.STANDARD, DecisionUrgency.LOW]),
                agent_type="trm_specialist",
                agent_version=agent_version,
                planning_cycle=f"2026-W{random.randint(3, 8):02d}",
                context_data=context_data,
                created_at=created_at,
            )

            # Apply user action for non-PENDING statuses
            if status == DecisionStatus.ACCEPTED:
                decision.user_id = user.id
                decision.user_action = "accept"
                decision.action_timestamp = created_at + timedelta(hours=random.randint(1, 12))

            elif status == DecisionStatus.REJECTED and user_action == "override":
                override_info = template["override"]
                reason_code = override_info["reason_code"]
                reason_text = override_info["reason_text"]
                decision.user_id = user.id
                decision.user_action = "override"
                decision.action_timestamp = created_at + timedelta(hours=random.randint(1, 8))
                decision.override_reason = f"[{reason_code}] {reason_text}"
                decision.user_value = float(int(qty * random.uniform(0.5, 1.5)))
                # Store structured override in context_data
                decision.context_data = {
                    **context_data,
                    "reason_code": reason_code,
                    "override_values": {
                        override_info["override_key"]: decision.user_value,
                    },
                }

            elif status == DecisionStatus.REJECTED and user_action == "reject":
                decision.user_id = user.id
                decision.user_action = "reject"
                decision.action_timestamp = created_at + timedelta(hours=random.randint(1, 6))
                reject_reason = random.choice(TRM_REASON_CODES[:6])
                decision.override_reason = f"[{reject_reason}] Rejected — agent should re-evaluate with updated context"
                decision.context_data = {**context_data, "reason_code": reject_reason}

            elif status == DecisionStatus.AUTO_EXECUTED:
                decision.action_timestamp = created_at + timedelta(minutes=random.randint(1, 15))
                decision.outcome_measured = True
                decision.outcome_value = float(qty * random.uniform(0.92, 1.08))
                decision.outcome_quality_score = round(random.uniform(45, 90), 1)

            db.add(decision)
            db.flush()  # Get the ID for replay buffer
            total_decisions += 1

            # Write overridden decisions to TRM replay buffer
            if is_override:
                override_info = template["override"]
                state_vector = [
                    float(decision.recommended_value or 0),
                    float(decision.previous_value or 0),
                    float(decision.agent_confidence or 0),
                ]
                replay_entry = TRMReplayBuffer(
                    tenant_id=tenant.id,
                    config_id=config.id,
                    trm_type=trm_type,
                    decision_log_id=decision.id,
                    decision_log_table="agent_decisions",
                    state_vector=state_vector,
                    state_dim=len(state_vector),
                    action_discrete=1,  # 0=accept, 1=override, 2=reject
                    action_dim=1,
                    reward=-0.5,  # Override = agent was wrong
                    reward_components={
                        "expert_signal": -0.5,
                        "reason_code": override_info["reason_code"],
                    },
                    is_expert=True,
                    priority=2.0,  # Expert samples get higher priority
                    transition_date=TODAY - timedelta(days=random.randint(0, 7)),
                    created_at=decision.action_timestamp or datetime.now(),
                )
                db.add(replay_entry)
                total_replay += 1

    db.flush()
    print(f"   Created {total_decisions} TRM worklist decisions + {total_replay} replay buffer entries.")
    return total_decisions


def seed_trm_decision_logs(
    db: Session, tenant: Tenant, config: SupplyChainConfig,
    dc_site: Site, products: list,
) -> int:
    """
    Seed TRM-specific decision log tables (ATPDecisionLog, RebalancingDecisionLog, etc.)
    with realistic entries showing both AI-recommended and human-overridden decisions.
    """
    print("\n15. Seeding TRM Decision Logs (4 types)...")

    # Check for existing
    existing_atp = db.query(ATPDecisionLog).filter(
        ATPDecisionLog.tenant_id == tenant.id,
    ).count()
    if existing_atp > 0:
        print(f"   TRM decision logs already exist ({existing_atp} ATP records). Skipping.")
        return existing_atp

    # Look up specialist users
    specialist_users = {}
    for trm_type, email in TRM_SPECIALIST_USERS.items():
        user = db.query(User).filter(User.email == email).first()
        if user:
            specialist_users[trm_type] = user

    total = 0

    # --- ATP Decision Logs ---
    atp_user = specialist_users.get("atp")
    for i in range(8):
        product = random.choice(products)
        sku = product.id.split("_")[-1]
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
        qty = random.randint(int(mean_demand * 0.3), int(mean_demand * 1.5))
        days_ago = random.randint(1, 30)

        # Alternate between AI-accepted and human-override sources
        if i < 3:
            source = DecisionSource.AI_ACCEPTED
        elif i < 6:
            source = DecisionSource.AI_MODIFIED
        else:
            source = DecisionSource.EXPERT_HUMAN

        inv = random.randint(100, 800)
        pipeline = random.randint(50, 300)
        backlog = random.randint(0, 50)
        allocated = random.randint(20, 200)
        available = max(0, inv - allocated)
        fulfilled = min(qty, available) if source != DecisionSource.AI_MODIFIED else int(qty * random.uniform(0.5, 0.9))

        log_entry = ATPDecisionLog(
            tenant_id=tenant.id,
            config_id=config.id,
            site_id=dc_site.id,
            product_id=int(product.id.split("_")[-1].replace("FP", "1").replace("RD", "2").replace("DP", "3").replace("FD", "4").replace("BV", "5")[:3]) if product.id.split("_")[-1][:2].isalpha() else 1,
            decision_date=TODAY - timedelta(days=days_ago),
            order_id=f"ORD-{random.randint(10000, 99999)}",
            customer_id=f"CUST-{random.randint(100, 999)}",
            requested_qty=float(qty),
            requested_date=TODAY - timedelta(days=days_ago - 1),
            priority=random.randint(1, 4),
            state_inventory=float(inv),
            state_pipeline=float(pipeline),
            state_backlog=float(backlog),
            state_allocated=float(allocated),
            state_available_atp=float(available),
            state_demand_forecast=float(mean_demand),
            state_other_orders_pending=random.randint(2, 15),
            state_features={"dos": round(inv / mean_demand * 7, 1)},
            action_type="fulfill" if fulfilled >= qty else "partial",
            action_qty_fulfilled=float(fulfilled),
            action_qty_backordered=float(max(0, qty - fulfilled)),
            action_promise_date=TODAY - timedelta(days=days_ago - 2),
            action_allocation_tier=random.randint(1, 3),
            action_reason="AATP consumption sequence applied" if source == DecisionSource.AI_ACCEPTED else "Manual override: strategic customer priority",
            source=source,
            decision_maker_id=atp_user.id if atp_user and source != DecisionSource.AI_ACCEPTED else None,
            ai_recommendation={"action": "fulfill", "qty": qty, "tier": 2},
            ai_confidence=round(random.uniform(0.75, 0.96), 3),
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        db.add(log_entry)
        db.flush()

        # Add outcome for older decisions
        if days_ago > 5:
            outcome = ATPOutcome(
                decision_id=log_entry.id,
                status=OutcomeStatus.MEASURED,
                measured_at=datetime.now() - timedelta(days=days_ago - 3),
                actual_qty_shipped=float(fulfilled),
                actual_ship_date=TODAY - timedelta(days=days_ago - 1),
                actual_delivery_date=TODAY - timedelta(days=days_ago - 3),
                on_time=random.random() > 0.15,
                in_full=fulfilled >= qty,
                otif=random.random() > 0.2,
                days_late=0 if random.random() > 0.15 else random.randint(1, 3),
                fill_rate=round(fulfilled / qty, 3) if qty > 0 else 1.0,
                customer_satisfaction_impact=round(random.uniform(-0.2, 0.5), 2),
                revenue_impact=round(fulfilled * (product.unit_cost or 25.0), 2),
                reward=round(random.uniform(0.3, 0.9), 3),
                reward_components={"otif": 0.5, "fill_rate": 0.3, "timeliness": 0.2},
            )
            db.add(outcome)

        total += 1

    # --- Rebalancing Decision Logs ---
    rebal_user = specialist_users.get("rebalancing")
    for i in range(6):
        product = random.choice(products)
        sku = product.id.split("_")[-1]
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
        days_ago = random.randint(1, 21)
        transfer_qty = random.randint(50, 300)

        source = DecisionSource.AI_MODIFIED if i < 3 else DecisionSource.AI_ACCEPTED

        log_entry = RebalancingDecisionLog(
            tenant_id=tenant.id,
            config_id=config.id,
            product_id=i + 1,
            decision_date=TODAY - timedelta(days=days_ago),
            state_site_inventories={"DC-Chicago": random.randint(200, 600), "DC-Indianapolis": random.randint(30, 100)},
            state_site_backlogs={"DC-Chicago": 0, "DC-Indianapolis": random.randint(10, 40)},
            state_site_demands={"DC-Chicago": int(mean_demand * 0.6), "DC-Indianapolis": int(mean_demand * 0.4)},
            state_transit_matrix={},
            state_network_imbalance=round(random.uniform(0.15, 0.40), 3),
            state_features={"num_sites": 2, "season": "Q1"},
            action_type="transfer" if i < 5 else "hold",
            action_from_site_id=dc_site.id,
            action_to_site_id=dc_site.id + 1,
            action_qty=float(transfer_qty) if i < 5 else 0,
            action_urgency="expedite" if i == 2 else "normal",
            action_reason="Rebalance to prevent stockout" if source == DecisionSource.AI_ACCEPTED else "Adjusted qty per dock capacity constraint",
            source=source,
            decision_maker_id=rebal_user.id if rebal_user and source == DecisionSource.AI_MODIFIED else None,
            ai_recommendation={"action": "transfer", "qty": transfer_qty + 50, "urgency": "normal"},
            ai_confidence=round(random.uniform(0.70, 0.95), 3),
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        db.add(log_entry)
        db.flush()

        if days_ago > 5:
            outcome = RebalancingOutcome(
                decision_id=log_entry.id,
                status=OutcomeStatus.MEASURED,
                measured_at=datetime.now() - timedelta(days=days_ago - 3),
                actual_transfer_qty=float(transfer_qty) if i < 5 else 0,
                actual_arrival_date=TODAY - timedelta(days=days_ago - 2),
                transfer_completed=True,
                to_site_stockout_prevented=random.random() > 0.3,
                service_level_before=round(random.uniform(0.82, 0.90), 3),
                service_level_after=round(random.uniform(0.92, 0.98), 3),
                transfer_cost=round(transfer_qty * random.uniform(0.5, 2.0), 2),
                reward=round(random.uniform(0.4, 0.85), 3),
                reward_components={"sl_improvement": 0.5, "cost_efficiency": 0.3, "stockout_prevention": 0.2},
            )
            db.add(outcome)

        total += 1

    # --- PO Decision Logs ---
    po_user = specialist_users.get("po_creation")
    for i in range(8):
        product = random.choice(products)
        sku = product.id.split("_")[-1]
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
        days_ago = random.randint(1, 28)
        order_qty = random.randint(int(mean_demand * 0.8), int(mean_demand * 3))

        source = DecisionSource.AI_MODIFIED if i % 3 == 0 else DecisionSource.AI_ACCEPTED

        log_entry = PODecisionLog(
            tenant_id=tenant.id,
            config_id=config.id,
            site_id=dc_site.id,
            product_id=i + 1,
            supplier_id=random.randint(1, 10),
            decision_date=TODAY - timedelta(days=days_ago),
            state_inventory=float(random.randint(50, 300)),
            state_pipeline=float(random.randint(0, 200)),
            state_backlog=float(random.randint(0, 30)),
            state_reorder_point=float(round(mean_demand * 1.5, 0)),
            state_safety_stock=float(round(mean_demand * 1.0, 0)),
            state_days_of_supply=round(random.uniform(3, 12), 1),
            state_demand_forecast=[float(int(mean_demand * random.uniform(0.9, 1.1))) for _ in range(4)],
            state_demand_variability=round(random.uniform(0.08, 0.25), 3),
            state_supplier_lead_time=float(random.randint(2, 7)),
            state_supplier_reliability=round(random.uniform(0.88, 0.98), 3),
            state_features={"category": sku[:2], "moq": round(mean_demand * 0.5)},
            action_type="order" if i < 6 else "defer",
            action_order_qty=float(order_qty) if i < 6 else 0,
            action_requested_date=TODAY - timedelta(days=days_ago) + timedelta(days=random.randint(3, 10)),
            action_expedite=i == 2,
            action_reason="Standard replenishment" if source == DecisionSource.AI_ACCEPTED else "Switched supplier per quality hold",
            po_number=f"PO-DF-2026-{2500 + i}",
            po_unit_cost=float(product.unit_cost or 25.0),
            source=source,
            decision_maker_id=po_user.id if po_user and source == DecisionSource.AI_MODIFIED else None,
            ai_recommendation={"action": "order", "qty": order_qty, "supplier": "primary"},
            ai_confidence=round(random.uniform(0.78, 0.97), 3),
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        db.add(log_entry)
        db.flush()

        if days_ago > 7:
            stockout = random.random() < 0.1
            outcome = POOutcome(
                decision_id=log_entry.id,
                status=OutcomeStatus.MEASURED,
                measured_at=datetime.now() - timedelta(days=days_ago - 5),
                actual_receipt_qty=float(order_qty * random.uniform(0.95, 1.02)) if i < 6 else None,
                actual_receipt_date=TODAY - timedelta(days=days_ago - random.randint(3, 8)) if i < 6 else None,
                lead_time_actual=random.randint(2, 8),
                stockout_occurred=stockout,
                stockout_days=random.randint(1, 3) if stockout else 0,
                excess_inventory_cost=round(random.uniform(0, 500), 2),
                expedite_cost=round(random.uniform(100, 500), 2) if i == 2 else 0,
                dos_at_receipt=round(random.uniform(5, 15), 1),
                reward=round(random.uniform(0.3, 0.9), 3),
                reward_components={"timing_accuracy": 0.4, "qty_accuracy": 0.3, "cost_efficiency": 0.3},
            )
            db.add(outcome)

        total += 1

    # --- Order Tracking Decision Logs ---
    ot_user = specialist_users.get("order_tracking")
    for i in range(6):
        days_ago = random.randint(1, 21)
        exc_types = ["late", "short", "damaged", "quality"]
        exc_type = exc_types[i % len(exc_types)]

        source = DecisionSource.AI_MODIFIED if i < 2 else DecisionSource.AI_ACCEPTED

        log_entry = OrderTrackingDecisionLog(
            tenant_id=tenant.id,
            config_id=config.id,
            order_id=f"PO-DF-2026-{1000 + random.randint(0, 19)}",
            order_type="PO",
            decision_date=TODAY - timedelta(days=days_ago),
            exception_type=exc_type,
            exception_severity=random.choice(["low", "medium", "high"]),
            days_from_expected=random.randint(1, 7) if exc_type == "late" else 0,
            qty_variance=float(-random.randint(10, 100)) if exc_type == "short" else 0,
            state_order_status=random.choice(["In Transit", "At Origin", "Receiving"]),
            state_order_qty=float(random.randint(80, 400)),
            state_expected_date=TODAY - timedelta(days=days_ago + random.randint(1, 5)),
            state_inventory_position=float(random.randint(50, 300)),
            state_other_pending_orders=random.randint(2, 8),
            state_customer_impact=random.choice(["none", "low", "medium", "high"]),
            state_features={"supplier": random.choice(["TYSON", "KRAFT", "NESTLE"]), "lane": "I-70"},
            action_type="escalate" if i < 2 else random.choice(["accept", "reorder", "expedite"]),
            action_new_expected_date=TODAY - timedelta(days=days_ago) + timedelta(days=random.randint(2, 7)),
            action_reorder_qty=float(random.randint(50, 200)) if i >= 2 else None,
            action_escalated_to="Supplier Account Manager" if i < 2 else None,
            action_reason="Escalated per critical customer impact" if source == DecisionSource.AI_MODIFIED else "Standard exception handling",
            source=source,
            decision_maker_id=ot_user.id if ot_user and source == DecisionSource.AI_MODIFIED else None,
            ai_recommendation={"action": "monitor", "severity": "medium"},
            ai_confidence=round(random.uniform(0.70, 0.92), 3),
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        db.add(log_entry)
        db.flush()

        if days_ago > 5:
            outcome = OrderTrackingOutcome(
                decision_id=log_entry.id,
                status=OutcomeStatus.MEASURED,
                measured_at=datetime.now() - timedelta(days=days_ago - 3),
                exception_resolved=random.random() > 0.1,
                resolution_time_hours=round(random.uniform(2, 48), 1),
                final_order_status="Received" if random.random() > 0.2 else "Partially Received",
                customer_notified=random.random() > 0.5,
                customer_satisfied=random.random() > 0.3,
                additional_cost=round(random.uniform(0, 500), 2),
                service_recovery_successful=random.random() > 0.2,
                reward=round(random.uniform(0.2, 0.8), 3),
                reward_components={"resolution_speed": 0.4, "customer_impact": 0.3, "cost_control": 0.3},
            )
            db.add(outcome)

        total += 1

    db.flush()
    print(f"   Created {total} TRM decision log entries with outcomes.")
    return total


def seed_purchase_orders(db: Session, config: SupplyChainConfig, dc_site: Site,
                         site_map: dict, products: list, tenant: Tenant) -> int:
    """Generate purchase orders with line items."""
    print("\n10. Seeding Purchase Orders...")

    existing = db.query(PurchaseOrder).filter(
        PurchaseOrder.config_id == config.id,
    ).count()
    if existing > 0:
        print(f"   Purchase orders already exist ({existing} records). Skipping.")
        return existing

    # Build reverse map: SKU -> supplier site name
    sku_to_supplier = {}
    for supplier_name, skus in SUPPLIER_PRODUCT_MAP.items():
        for sku in skus:
            sku_to_supplier[sku] = supplier_name

    statuses = ["DRAFT", "APPROVED", "SENT", "ACKNOWLEDGED", "RECEIVED", "RECEIVED"]
    po_count = 0
    line_count = 0

    for po_idx in range(20):
        # Pick a random supplier
        supplier_name = random.choice(list(SUPPLIER_PRODUCT_MAP.keys()))
        supplier_site = site_map.get(supplier_name)
        if not supplier_site:
            continue

        days_ago = random.randint(1, 60)
        order_date = TODAY - timedelta(days=days_ago)
        delivery_offset = random.randint(3, 14)
        status = statuses[min(po_idx % len(statuses), len(statuses) - 1)]

        po = PurchaseOrder(
            po_number=f"PO-DF-2026-{1000 + po_idx}",
            vendor_id=supplier_name,
            supplier_site_id=supplier_site.id,
            destination_site_id=dc_site.id,
            config_id=config.id,
            tenant_id=tenant.id,
            order_type="po",
            status=status,
            order_date=order_date,
            requested_delivery_date=order_date + timedelta(days=delivery_offset),
            promised_delivery_date=order_date + timedelta(days=delivery_offset + random.randint(-1, 2)),
            source="seed_food_dist_planning_data",
            source_update_dttm=datetime.now(),
            created_at=datetime.combine(order_date, datetime.min.time()),
        )

        if status == "RECEIVED":
            po.actual_delivery_date = order_date + timedelta(days=delivery_offset + random.randint(-1, 3))

        db.add(po)
        db.flush()
        po_count += 1

        # Add line items for products this supplier provides
        supplier_skus = SUPPLIER_PRODUCT_MAP.get(supplier_name, [])
        for line_num, sku in enumerate(supplier_skus, 1):
            # Find product matching this SKU
            product = None
            for p in products:
                if p.id.endswith(f"_{sku}"):
                    product = p
                    break
            if not product:
                continue

            mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
            qty = round(mean_demand * random.uniform(1.0, 3.0), 0)

            line = PurchaseOrderLineItem(
                po_id=po.id,
                line_number=line_num,
                product_id=product.id,
                quantity=qty,
                received_quantity=qty if status == "RECEIVED" else 0,
                unit_price=product.unit_cost or 25.0,
                line_total=round(qty * (product.unit_cost or 25.0), 2),
                requested_delivery_date=po.requested_delivery_date,
                promised_delivery_date=po.promised_delivery_date,
                actual_delivery_date=po.actual_delivery_date,
                created_at=datetime.combine(order_date, datetime.min.time()),
            )
            db.add(line)
            line_count += 1

    db.flush()
    print(f"   Created {po_count} purchase orders with {line_count} line items.")
    return po_count


def seed_inventory_optimization(db: Session, dc_site: Site, products: list,
                                company_id: str) -> int:
    """Generate inventory optimization recommendation records."""
    print("\n11. Seeding Inventory Optimization Records...")

    existing = db.query(InventoryOptimization).filter(
        InventoryOptimization.site_id == str(dc_site.id),
    ).count()
    if existing > 0:
        print(f"   Optimization records already exist ({existing} records). Skipping.")
        return existing

    methods = ["newsvendor", "base_stock", "ss_rop", "monte_carlo"]
    statuses = ["pending", "approved", "approved", "applied"]

    count = 0
    for product in products:
        sku = product.id.split("_")[-1]
        profile = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))
        mean_demand, cv, _ = profile

        current_ss = round(mean_demand * 1.5, 0)
        recommended_ss = round(mean_demand * random.uniform(0.8, 1.4), 0)
        current_rop = round(mean_demand * 2.0, 0)
        recommended_rop = round(mean_demand * random.uniform(1.5, 2.2), 0)

        opt = InventoryOptimization(
            company_id=company_id,
            site_id=dc_site.id,
            product_id=product.id,
            optimization_date=TODAY - timedelta(days=random.randint(1, 14)),
            optimization_method=random.choice(methods),
            current_safety_stock=current_ss,
            current_reorder_point=current_rop,
            current_service_level=round(random.uniform(0.90, 0.98), 3),
            current_holding_cost=round(current_ss * (product.unit_cost or 25.0) * 0.25 / 52, 2),
            recommended_safety_stock=recommended_ss,
            recommended_reorder_point=recommended_rop,
            expected_service_level=round(random.uniform(0.93, 0.98), 3),
            expected_holding_cost=round(recommended_ss * (product.unit_cost or 25.0) * 0.25 / 52, 2),
            expected_stockout_cost=round(random.uniform(100, 2000), 2),
            expected_total_cost=round(recommended_ss * (product.unit_cost or 25.0) * 0.25 / 52 + random.uniform(100, 1000), 2),
            demand_mean=mean_demand,
            demand_std_dev=round(mean_demand * cv, 2),
            lead_time_mean=round(random.uniform(1.5, 5.0), 1),
            lead_time_std_dev=round(random.uniform(0.2, 1.0), 2),
            safety_stock_p10=round(recommended_ss * 0.75, 0),
            safety_stock_p50=recommended_ss,
            safety_stock_p90=round(recommended_ss * 1.30, 0),
            service_level_weight=0.6,
            cost_weight=0.4,
            status=random.choice(statuses),
        )
        db.add(opt)
        count += 1

    db.flush()
    print(f"   Created {count} inventory optimization records.")
    return count


def seed_supply_plan_requests(db: Session, config: SupplyChainConfig, tenant: Tenant,
                              user: User) -> int:
    """Generate supply plan request/result records (async plan generation history)."""
    if not HAS_SUPPLY_PLAN_REQUESTS:
        print("\n12. Skipping Supply Plan Requests (model not available).")
        return 0

    print("\n12. Seeding Supply Plan Requests & Results...")

    existing = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.config_id == config.id,
    ).count()
    if existing > 0:
        print(f"   Supply plan requests already exist ({existing} records). Skipping.")
        return existing

    strategies = ["trm", "naive", "pid"]
    count = 0

    for i in range(4):
        days_ago = [21, 14, 7, 1][i]
        created_at = datetime.now() - timedelta(days=days_ago)

        request = SupplyPlanRequest(
            config_id=config.id,
            config_name=config.name,
            user_id=user.id,
            agent_strategy=strategies[i % len(strategies)],
            num_scenarios=1000,
            planning_horizon=52,
            stochastic_params={
                "demand_model": "normal",
                "demand_variability": 0.15,
                "lead_time_model": "normal",
                "lead_time_variability": 0.10,
                "supplier_reliability": 0.95,
            },
            objectives={
                "primary_objective": "min_cost",
                "service_level_target": 0.95,
                "service_level_confidence": 0.90,
                "inventory_dos_min": 5,
                "inventory_dos_max": 20,
            },
            status=PlanStatus.COMPLETED,
            progress=1.0,
            created_at=created_at,
            started_at=created_at + timedelta(seconds=5),
            completed_at=created_at + timedelta(minutes=random.randint(2, 8)),
        )
        db.add(request)
        db.flush()

        # Create matching result
        result = SupplyPlanResult(
            request_id=request.id,
            scorecard={
                "financial": {
                    "total_cost": {
                        "expected": round(random.uniform(800000, 1200000), 0),
                        "p10": round(random.uniform(700000, 900000), 0),
                        "p90": round(random.uniform(1100000, 1400000), 0),
                    },
                    "holding_cost": {"expected": round(random.uniform(80000, 150000), 0)},
                    "ordering_cost": {"expected": round(random.uniform(40000, 80000), 0)},
                    "stockout_cost": {"expected": round(random.uniform(10000, 50000), 0)},
                },
                "customer": {
                    "otif": {
                        "expected": round(random.uniform(0.92, 0.97), 3),
                        "probability_above_target": round(random.uniform(0.80, 0.95), 3),
                    },
                    "fill_rate": {"expected": round(random.uniform(0.95, 0.99), 3)},
                },
                "operational": {
                    "inventory_turns": {"expected": round(random.uniform(18, 28), 1)},
                    "avg_dos": {"expected": round(random.uniform(8, 14), 1)},
                    "bullwhip_ratio": {"expected": round(random.uniform(1.1, 1.6), 2)},
                },
                "strategic": {
                    "flexibility_score": round(random.uniform(0.70, 0.90), 2),
                    "supplier_reliability": round(random.uniform(0.92, 0.98), 3),
                },
            },
            recommendations=[
                {
                    "type": "safety_stock",
                    "severity": "medium",
                    "metric": "inventory_turns",
                    "message": "Safety stock for Frozen Proteins can be reduced 10% while maintaining 95% SL",
                    "recommendation": "Reduce frozen protein safety stock from 10 to 9 DOS",
                },
                {
                    "type": "sourcing",
                    "severity": "low",
                    "metric": "supplier_reliability",
                    "message": "Consider dual-sourcing for Beverages category",
                    "recommendation": "Add secondary supplier for BV001-BV003 to reduce concentration risk",
                },
            ],
            total_cost_expected=round(random.uniform(800000, 1200000), 0),
            total_cost_p10=round(random.uniform(700000, 900000), 0),
            total_cost_p90=round(random.uniform(1100000, 1400000), 0),
            otif_expected=round(random.uniform(0.92, 0.97), 3),
            otif_probability_above_target=round(random.uniform(0.80, 0.95), 3),
            fill_rate_expected=round(random.uniform(0.95, 0.99), 3),
            inventory_turns_expected=round(random.uniform(18, 28), 1),
            bullwhip_ratio_expected=round(random.uniform(1.1, 1.6), 2),
            created_at=request.completed_at,
        )
        db.add(result)
        count += 1

    db.flush()
    print(f"   Created {count} supply plan request/result pairs.")
    return count


def seed_production_orders(db: Session, config: SupplyChainConfig, dc_site: Site,
                           products: list, user: User) -> int:
    """Generate production orders (for distribution operations like kitting/repack)."""
    if not HAS_PRODUCTION_ORDERS:
        print("\n13. Skipping Production Orders (model not available).")
        return 0

    print("\n13. Seeding Production Orders...")

    existing = db.query(ProductionOrder).filter(
        ProductionOrder.config_id == config.id,
    ).count()
    if existing > 0:
        print(f"   Production orders already exist ({existing} records). Skipping.")
        return existing

    statuses_data = [
        ("PLANNED", 4), ("RELEASED", 3), ("IN_PROGRESS", 2),
        ("COMPLETED", 8), ("COMPLETED", 0), ("COMPLETED", 0),
    ]

    count = 0
    for i in range(15):
        product = random.choice(products)
        sku = product.id.split("_")[-1]
        mean_demand = PRODUCT_DEMAND_PROFILES.get(sku, (100, 0.15, 0.05))[0]
        qty = round(mean_demand * random.uniform(1.0, 3.0), 0)
        status_name, days_offset = statuses_data[i % len(statuses_data)]

        planned_start = TODAY - timedelta(days=random.randint(1, 30))
        planned_completion = planned_start + timedelta(days=random.randint(1, 5))

        prod_order = ProductionOrder(
            order_number=f"PRD-DF-2026-{2000 + i}",
            item_id=product.id,
            site_id=dc_site.id,  # Integer FK
            config_id=config.id,
            status=status_name,
            planned_quantity=int(qty),
            planned_start_date=datetime.combine(planned_start, datetime.min.time()),
            planned_completion_date=datetime.combine(planned_completion, datetime.min.time()),
            setup_cost=round(random.uniform(50, 200), 2),
            unit_cost=product.unit_cost or 25.0,
            total_cost=round(qty * (product.unit_cost or 25.0), 2),
            created_at=datetime.combine(planned_start - timedelta(days=3), datetime.min.time()),
        )

        if status_name in ("RELEASED", "IN_PROGRESS", "COMPLETED"):
            prod_order.released_date = datetime.combine(planned_start - timedelta(days=1), datetime.min.time())
        if status_name in ("IN_PROGRESS", "COMPLETED"):
            prod_order.actual_start_date = datetime.combine(planned_start + timedelta(days=random.randint(0, 1)), datetime.min.time())
        if status_name == "COMPLETED":
            prod_order.actual_completion_date = datetime.combine(planned_completion + timedelta(days=random.randint(-1, 2)), datetime.min.time())
            prod_order.actual_quantity = int(qty * random.uniform(0.95, 1.02))
            prod_order.scrap_quantity = int(qty * random.uniform(0, 0.03))
            prod_order.yield_percentage = round((prod_order.actual_quantity / qty) * 100, 1)

        db.add(prod_order)
        count += 1

    db.flush()
    print(f"   Created {count} production orders.")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Food Dist Planning & Execution Demo Data Seeder")
    print("=" * 70)

    SessionLocal = sessionmaker(bind=sync_engine)
    db = SessionLocal()

    try:
        # --- Find Food Dist customer ---
        tenant = db.query(Tenant).filter(Tenant.name == "Food Dist").first()
        if not tenant:
            print("\nERROR: Food Dist tenant not found!")
            print("Run seed_dot_foods_demo.py first.")
            return

        print(f"\nFound customer: {tenant.name} (ID: {tenant.id}, Mode: {tenant.mode})")

        # --- Find SC config ---
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.tenant_id == tenant.id,
            SupplyChainConfig.name.ilike("%Food Dist%"),
        ).first()
        if not config:
            # Try any config in this customer
            config = db.query(SupplyChainConfig).filter(
                SupplyChainConfig.tenant_id == tenant.id,
            ).first()
        if not config:
            print("\nERROR: No supply chain config found for Food Dist customer!")
            print("Run seed_food_dist_hierarchies.py first.")
            return

        print(f"Found config: {config.name} (ID: {config.id})")

        # --- Find DC site ---
        dc_site = db.query(Site).filter(
            Site.config_id == config.id,
            Site.name == "FOODDIST_DC",
        ).first()
        if not dc_site:
            dc_site = db.query(Site).filter(
                Site.config_id == config.id,
                Site.master_type == "INVENTORY",
            ).first()
        if not dc_site:
            print("\nERROR: DC site not found!")
            return

        print(f"Found DC site: {dc_site.name} (ID: {dc_site.id})")

        # --- Build site map ---
        all_sites = db.query(Site).filter(Site.config_id == config.id).all()
        site_map = {s.name: s for s in all_sites}
        print(f"Found {len(all_sites)} sites in config")

        # --- Find products ---
        products = db.query(Product).filter(Product.config_id == config.id).all()
        if not products:
            print("\nERROR: No products found for this config!")
            print("Run seed_food_dist_hierarchies.py first.")
            return

        print(f"Found {len(products)} products")

        # --- Find company ---
        company_id = f"FD_CORP_{tenant.id}"

        # --- Find demo user ---
        user = db.query(User).filter(User.email == "demo@distdemo.com").first()
        if not user:
            user = db.query(User).filter(User.email == "admin@distdemo.com").first()
        if not user:
            user = db.query(User).first()
        print(f"Using user: {user.email} (ID: {user.id})")

        # --- Generate all data ---
        total = 0
        total += seed_forecasts(db, config, dc_site, products, company_id)
        total += seed_inventory_policies(db, config, dc_site, products, company_id)
        total += seed_inventory_levels(db, config, dc_site, products, company_id)
        total += seed_supply_plans(db, config, dc_site, site_map, products, company_id)
        total += seed_mps_plan(db, config, dc_site, products, user)
        total += seed_planning_cycles(db, config, tenant, user)
        total += seed_performance_metrics(db, tenant)
        total += seed_sop_worklist(db, tenant)
        total += seed_agent_decisions(db, tenant, products)
        total += seed_purchase_orders(db, config, dc_site, site_map, products, tenant)
        total += seed_inventory_optimization(db, dc_site, products, company_id)
        total += seed_supply_plan_requests(db, config, tenant, user)
        total += seed_production_orders(db, config, dc_site, products, user)
        total += seed_trm_worklist_decisions(db, tenant, config, dc_site, site_map, products)
        total += seed_trm_decision_logs(db, tenant, config, dc_site, products)

        db.commit()

        print("\n" + "=" * 70)
        print(f"SUCCESS: Created {total} total records")
        print("=" * 70)
        print("\nDashboard Data Coverage:")
        print("  Planning:")
        print("    - Demand Planning: 52-week forecasts (P10/P50/P90)")
        print("    - Supply Planning: 13-week supply plans + request/result history")
        print("    - MPS: Approved 52-week plan with capacity checks")
        print("    - Inventory Optimization: Safety stock recommendations")
        print("    - S&OP: 6 weekly planning cycles with snapshots")
        print("  Execution:")
        print("    - Purchase Orders: 20 POs with line items")
        print("    - Production Orders: 15 orders in various statuses")
        print("  TRM Worklists:")
        print("    - ATP Worklist: 12 decisions (3 pending, 3 accepted, 3 overridden, 1 rejected, 2 auto)")
        print("    - Rebalancing Worklist: 12 decisions (same mix)")
        print("    - PO Worklist: 12 decisions (same mix)")
        print("    - Order Tracking Worklist: 12 decisions (same mix)")
        print("    - TRM Replay Buffer: 12 expert override entries (is_expert=True)")
        print("    - TRM Decision Logs: 28 entries (ATP=8, Rebal=6, PO=8, OT=6) with outcomes")
        print("  Insights & Analytics:")
        print("    - Agent Performance: 12 months of improvement trajectory")
        print("    - S&OP Worklist: 8 realistic items with agent reasoning")
        print("    - Agent Decisions: 35 decisions across all categories")
        print("    - Inventory Optimization: 25 product-level recommendations")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()

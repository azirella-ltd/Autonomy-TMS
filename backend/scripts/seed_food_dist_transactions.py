#!/usr/bin/env python3
"""
Seed Food Dist Transaction Data (AWS SC DM Compliant)

Creates realistic transaction records for the Food Dist demo:
- Forecasts with P10/P50/P90 percentiles
- Inventory levels (current stock)
- Inventory policies (safety stock rules)
- Sourcing rules (supplier priorities)

Uses AWS SC Data Model tables and field names.
"""

import sys
import os
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create sync database session
sync_url = str(settings.DATABASE_URL).replace('+asyncpg', '').replace('asyncpg', 'psycopg2')
if '+psycopg2' not in sync_url and 'psycopg2' not in sync_url:
    sync_url = sync_url.replace('postgresql://', 'postgresql+psycopg2://')

print(f"Using PostgreSQL database at: {sync_url.split('@')[1].split('/')[0]}/{sync_url.split('/')[-1]}")

engine = create_engine(sync_url)
SessionLocal = sessionmaker(bind=engine)

from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import (
    Product,
    Geography,
    ProductHierarchy,
    Company,
    Forecast,
    InvLevel,
    InvPolicy,
    SourcingRules,
)


# ============================================================================
# Constants for realistic Food Dist data
# ============================================================================

FOOD_DIST_CONFIG_ID = 22
FORECAST_HISTORY_WEEKS = 104
FORECAST_FUTURE_WEEKS = 52

# Demand patterns by product category (weekly units)
DEMAND_PATTERNS = {
    "FRZ_PROTEIN": {"base": 500, "variance": 0.25, "seasonality": 1.1},   # Higher winter
    "FRZ_DESSERT": {"base": 300, "variance": 0.30, "seasonality": 1.2},   # Higher summer
    "REF_DAIRY": {"base": 800, "variance": 0.15, "seasonality": 1.0},     # Stable
    "BEV": {"base": 600, "variance": 0.20, "seasonality": 1.3},           # Higher summer
    "DRY_PANTRY": {"base": 400, "variance": 0.20, "seasonality": 1.0},    # Stable
}

# Inventory policy parameters by category
INVENTORY_POLICIES = {
    "FRZ_PROTEIN": {"ss_policy": "doc_fcst", "ss_days": 14, "service_level": 0.95},
    "FRZ_DESSERT": {"ss_policy": "doc_fcst", "ss_days": 10, "service_level": 0.92},
    "REF_DAIRY": {"ss_policy": "sl", "ss_days": 7, "service_level": 0.98},
    "BEV": {"ss_policy": "doc_dem", "ss_days": 10, "service_level": 0.95},
    "DRY_PANTRY": {"ss_policy": "doc_dem", "ss_days": 21, "service_level": 0.90},
}

# Lead times by supplier state (days)
SUPPLIER_LEAD_TIMES = {
    "CO": {"min": 2, "avg": 3, "max": 5},    # Colorado - close
    "NV": {"min": 2, "avg": 3, "max": 4},    # Nevada - close
    "ID": {"min": 3, "avg": 4, "max": 6},    # Idaho - medium
    "WY": {"min": 2, "avg": 3, "max": 5},    # Wyoming - close
    "AZ": {"min": 3, "avg": 5, "max": 7},    # Arizona - farther
}

MARKET_VOLATILITY = {
    "NW": {"vol": 0.95, "left": 1.00, "right": 1.00},
    "SW": {"vol": 1.15, "left": 1.05, "right": 1.20},
    "MTN": {"vol": 0.85, "left": 0.90, "right": 0.90},
}

PRODUCT_SKEW = {
    "FRZ_PROTEIN": {"vol": 1.05, "left": 1.00, "right": 1.10},
    "FRZ_DESSERT": {"vol": 1.35, "left": 0.90, "right": 1.35},
    "REF_DAIRY": {"vol": 0.90, "left": 1.00, "right": 0.95},
    "BEV": {"vol": 1.25, "left": 0.95, "right": 1.30},
    "DRY_PANTRY": {"vol": 0.80, "left": 0.95, "right": 0.90},
}


def get_config_and_data(db):
    """Get Food Dist config and related data."""
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == FOOD_DIST_CONFIG_ID
    ).first()

    if not config:
        raise ValueError(f"Food Dist config (ID={FOOD_DIST_CONFIG_ID}) not found")

    sites = db.query(Site).filter(Site.config_id == config.id).all()
    products = db.query(Product).filter(Product.config_id == config.id).all()
    lanes = db.query(TransportationLane).filter(TransportationLane.config_id == config.id).all()

    return config, sites, products, lanes


def get_product_category(product):
    """Determine product category from product_group_id or name."""
    if product.product_group_id:
        group_id = product.product_group_id.upper()
        for cat in DEMAND_PATTERNS.keys():
            if cat in group_id:
                return cat
    # Fallback based on name
    name = (product.name or "").upper()
    if "FROZEN" in name or "ICE" in name:
        return "FRZ_DESSERT"
    if "BEEF" in name or "CHICKEN" in name or "PORK" in name or "SEAFOOD" in name:
        return "FRZ_PROTEIN"
    if "MILK" in name or "CHEESE" in name or "YOGURT" in name or "BUTTER" in name:
        return "REF_DAIRY"
    if "SODA" in name or "JUICE" in name or "WATER" in name or "ENERGY" in name:
        return "BEV"
    return "DRY_PANTRY"


def get_market_bucket(site) -> str:
    """Map customer site geography to market bucket."""
    geo = ((site.geo_id or "") + " " + (site.name or "")).upper()
    if any(code in geo for code in ("_REG_SW", "_CA", "_AZ", "LAX", "SFO", "SDG", "SAC", "PHX", "TUS", "MES")):
        return "SW"
    if any(code in geo for code in ("_REG_NW", "_OR", "_WA", "PDX", "EUG", "SAL", "SEA", "TAC", "SPO")):
        return "NW"
    return "MTN"


def triangular_from_baseline(p50: float, variance: float, category: str, market_bucket: str) -> dict:
    """Compute triangular min/median/max from current product-site baseline forecast."""
    p_adj = PRODUCT_SKEW.get(category, {"vol": 1.0, "left": 1.0, "right": 1.0})
    m_adj = MARKET_VOLATILITY.get(market_bucket, {"vol": 1.0, "left": 1.0, "right": 1.0})
    base_var = max(0.08, float(variance))

    down_pct = base_var * p_adj["vol"] * m_adj["vol"] * p_adj["left"] * m_adj["left"]
    up_pct = base_var * p_adj["vol"] * m_adj["vol"] * p_adj["right"] * m_adj["right"]

    median_val = max(0.0, float(p50))
    min_val = max(0.0, round(median_val * (1.0 - down_pct), 1))
    max_val = round(max(median_val, median_val * (1.0 + up_pct)), 1)
    if max_val <= min_val:
        max_val = round(min_val + max(1.0, median_val * 0.05), 1)
    return {"min": min_val, "median": round(median_val, 1), "max": max_val}


def create_forecasts(db, config, sites, products):
    """Create demand forecasts with P10/P50/P90 percentiles."""
    print("\n1. Creating Forecasts (AWS SC: forecast table)...")

    # Get customer sites (where demand occurs)
    customer_sites = [s for s in sites if s.master_type == "MARKET_DEMAND"]
    if not customer_sites:
        # Fallback to sites that look like customers
        customer_sites = [s for s in sites if "Customer" in (s.name or "") or "Store" in (s.name or "")]

    if not customer_sites:
        print("   Warning: No customer sites found for forecasts")
        return 0

    # Validate at least 2 years history per product/site; rebuild if insufficient
    existing = db.query(Forecast).filter(Forecast.config_id == config.id).count()
    if existing > 0:
        needs_rebuild = False
        history_cutoff = datetime.now().date()
        for product in products:
            for site in customer_sites:
                history_rows = db.query(Forecast).filter(
                    Forecast.config_id == config.id,
                    Forecast.product_id == product.id,
                    Forecast.site_id == site.id,
                    Forecast.forecast_date < history_cutoff,
                ).count()
                if history_rows < FORECAST_HISTORY_WEEKS:
                    needs_rebuild = True
                    break
            if needs_rebuild:
                break

        if not needs_rebuild:
            print(f"   Forecasts already exist ({existing} records) with >=2 years history")
            return existing

        print(f"   Existing forecast rows ({existing}) have <2 years history. Rebuilding...")
        db.query(Forecast).filter(Forecast.config_id == config.id).delete(synchronize_session=False)
        db.flush()

    forecast_count = 0
    today = datetime.now().date()

    # Create 2 years history + 1 year forward
    for week_offset in range(-FORECAST_HISTORY_WEEKS, FORECAST_FUTURE_WEEKS):
        forecast_date = today + timedelta(weeks=week_offset)

        for product in products:
            category = get_product_category(product)
            pattern = DEMAND_PATTERNS.get(category, DEMAND_PATTERNS["DRY_PANTRY"])

            # Seasonal adjustment (simple sine wave)
            month = forecast_date.month
            if category in ["FRZ_DESSERT", "BEV"]:
                # Higher in summer (June-Aug)
                seasonal = 1.0 + 0.3 * max(0, 1 - abs(month - 7) / 3)
            elif category == "FRZ_PROTEIN":
                # Higher in winter (Nov-Feb)
                seasonal = 1.0 + 0.2 * max(0, 1 - min(abs(month - 1), abs(month - 12)) / 2)
            else:
                seasonal = 1.0

            for site in customer_sites:
                market_bucket = get_market_bucket(site)
                # Base demand with variance
                base = pattern["base"] * seasonal
                variance = pattern["variance"]

                # Baseline current product-site forecast (median)
                p50 = int(base * (0.9 + random.random() * 0.2))
                tri = triangular_from_baseline(p50, variance, category, market_bucket)

                forecast = Forecast(
                    config_id=config.id,
                    product_id=product.id,
                    site_id=site.id,
                    forecast_date=forecast_date,
                    forecast_quantity=float(tri["median"]),
                    forecast_p10=float(tri["min"]),
                    forecast_p50=float(tri["median"]),
                    forecast_median=float(tri["median"]),
                    forecast_p90=float(tri["max"]),
                    forecast_std_dev=float((tri["max"] - tri["min"]) / 2.56),
                    forecast_confidence=0.85,
                    forecast_type="STATISTICAL",
                    forecast_level="product",
                    forecast_method="exponential_smoothing",
                    is_active="true",
                    demand_pattern={
                        "distribution": {
                            "type": "triangular",
                            "min": tri["min"],
                            "mode": tri["median"],
                            "median": tri["median"],
                            "max": tri["max"],
                        },
                        "drivers": {
                            "market_bucket": market_bucket,
                            "product_category": category,
                        },
                    },
                    created_dttm=datetime.now(),
                )
                db.add(forecast)
                forecast_count += 1

    db.flush()
    print(
        f"   Created {forecast_count} forecast records "
        f"({FORECAST_HISTORY_WEEKS} history + {FORECAST_FUTURE_WEEKS} forward weeks x {len(products)} products x {len(customer_sites)} sites)"
    )
    return forecast_count


def create_inventory_levels(db, config, sites, products):
    """Create current inventory levels."""
    print("\n2. Creating Inventory Levels (AWS SC: inv_level table)...")

    existing = db.query(InvLevel).filter(InvLevel.config_id == config.id).count()
    if existing > 0:
        print(f"   Inventory levels already exist ({existing} records)")
        return existing

    # Inventory held at DC and customer sites
    inventory_sites = [s for s in sites if s.master_type in ("INVENTORY", "MARKET_DEMAND")]

    inv_count = 0
    today = datetime.now()

    for site in inventory_sites:
        for product in products:
            category = get_product_category(product)
            pattern = DEMAND_PATTERNS.get(category, DEMAND_PATTERNS["DRY_PANTRY"])
            policy = INVENTORY_POLICIES.get(category, INVENTORY_POLICIES["DRY_PANTRY"])

            # Calculate target inventory based on demand and DOC
            weekly_demand = pattern["base"]
            daily_demand = weekly_demand / 7
            target_inv = int(daily_demand * policy["ss_days"])

            # Current inventory is 70-130% of target
            current_inv = int(target_inv * (0.7 + random.random() * 0.6))
            in_transit = int(daily_demand * 3)   # ~3 days in transit
            on_order = int(weekly_demand)         # ~1 week on order
            allocated = int(current_inv * 0.05)  # 5% allocated
            available = current_inv - allocated

            inv_level = InvLevel(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                inventory_date=today.date(),
                on_hand_qty=float(current_inv),
                available_qty=float(available),
                allocated_qty=float(allocated),
                in_transit_qty=float(in_transit),
                on_order_qty=float(on_order),
                reserved_qty=0.0,
            )
            db.add(inv_level)
            inv_count += 1

    db.flush()
    print(f"   Created {inv_count} inventory level records")
    return inv_count


def create_inventory_policies(db, config, sites, products):
    """Create inventory policies (safety stock rules)."""
    print("\n3. Creating Inventory Policies (AWS SC: inv_policy table)...")

    existing = db.query(InvPolicy).filter(InvPolicy.config_id == config.id).count()
    if existing > 0:
        print(f"   Inventory policies already exist ({existing} records)")
        return existing

    # Policies apply to DC and customer sites
    policy_sites = [s for s in sites if s.master_type in ("INVENTORY", "MARKET_DEMAND")]

    policy_count = 0

    for site in policy_sites:
        for product in products:
            category = get_product_category(product)
            policy_params = INVENTORY_POLICIES.get(category, INVENTORY_POLICIES["DRY_PANTRY"])
            pattern = DEMAND_PATTERNS.get(category, DEMAND_PATTERNS["DRY_PANTRY"])

            # Calculate safety stock based on policy type
            weekly_demand = pattern["base"]
            daily_demand = weekly_demand / 7

            if policy_params["ss_policy"] == "sl":
                # Service level based - z-score calculation
                z_score = 1.65 if policy_params["service_level"] >= 0.95 else 1.28
                safety_stock = int(z_score * (pattern["variance"] * daily_demand) * 3)  # 3-day lead time
            else:
                # DOC based
                safety_stock = int(daily_demand * policy_params["ss_days"] * 0.3)  # 30% of DOC as safety

            reorder_point = int(safety_stock + daily_demand * 3)  # Safety + lead time demand
            max_inventory = int(reorder_point + weekly_demand)     # ROP + 1 week order

            inv_policy = InvPolicy(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                ss_policy=policy_params["ss_policy"],
                service_level=policy_params["service_level"],
                ss_days=policy_params["ss_days"],
                ss_quantity=float(safety_stock),
                reorder_point=float(reorder_point),
                order_up_to_level=float(max_inventory),
                min_order_quantity=float(int(pattern["base"] * 0.25)),
                max_order_quantity=float(int(pattern["base"] * 4)),
                review_period=7,  # Weekly review
                is_active="true",
                eff_start_date=datetime.now(),
            )
            db.add(inv_policy)
            policy_count += 1

    db.flush()
    print(f"   Created {policy_count} inventory policy records")
    return policy_count


def create_sourcing_rules(db, config, sites, products, lanes):
    """Create sourcing rules (supplier priorities)."""
    print("\n4. Creating Sourcing Rules (AWS SC: sourcing_rules table)...")

    existing = db.query(SourcingRules).filter(SourcingRules.config_id == config.id).count()
    if existing > 0:
        print(f"   Sourcing rules already exist ({existing} records)")
        return existing

    # Find DC (destination) and suppliers (sources)
    dc_sites = [s for s in sites if s.master_type == "INVENTORY" and "DC" in (s.name or "").upper()]
    supplier_sites = [s for s in sites if s.master_type == "MARKET_SUPPLY"]

    if not dc_sites:
        dc_sites = [s for s in sites if s.master_type == "INVENTORY"][:1]

    if not dc_sites or not supplier_sites:
        print("   Warning: Missing DC or supplier sites for sourcing rules")
        return 0

    rule_count = 0

    for dc in dc_sites:
        for product in products:
            # Find suppliers that can supply this product (via lanes)
            supplying_sites = []
            for lane in lanes:
                if lane.to_site_id == dc.id:
                    supplier = next((s for s in supplier_sites if s.id == lane.from_site_id), None)
                    if supplier:
                        supplying_sites.append((supplier, lane))

            # If no lanes found, use all suppliers
            if not supplying_sites:
                supplying_sites = [(s, None) for s in supplier_sites]

            # Create prioritized sourcing rules
            for priority, (supplier, lane) in enumerate(supplying_sites, start=1):
                # Allocation ratio (primary gets more)
                if priority == 1:
                    ratio = 0.60
                elif priority == 2:
                    ratio = 0.30
                else:
                    ratio = 0.10

                # Minimum order quantity based on category
                category = get_product_category(product)
                pattern = DEMAND_PATTERNS.get(category, DEMAND_PATTERNS["DRY_PANTRY"])
                min_order = int(pattern["base"] * 0.25)  # 25% of weekly demand

                # Generate unique ID for sourcing rule
                rule_id = f"SR_{config.id}_{dc.id}_{supplier.id}_{product.id}"[:100]

                sourcing_rule = SourcingRules(
                    id=rule_id,
                    config_id=config.id,
                    product_id=product.id,
                    from_site_id=supplier.id,
                    to_site_id=dc.id,
                    sourcing_rule_type="buy",  # Purchase from supplier
                    sourcing_priority=priority,
                    sourcing_ratio=ratio,
                    min_quantity=float(min_order),
                    max_quantity=float(min_order * 10),
                    is_active="true",
                    eff_start_date=datetime.now(),
                    transportation_lane_id=lane.id if lane else None,
                )
                db.add(sourcing_rule)
                rule_count += 1

    db.flush()
    print(f"   Created {rule_count} sourcing rules")
    return rule_count


def main():
    """Main entry point."""
    print("=" * 70)
    print("Seeding Food Dist Transaction Data (AWS SC DM Compliant)")
    print("=" * 70)

    db = SessionLocal()

    try:
        # Get config and related data
        config, sites, products, lanes = get_config_and_data(db)
        print(f"\nConfig: {config.name} (ID: {config.id})")
        print(f"Sites: {len(sites)}, Products: {len(products)}, Lanes: {len(lanes)}")

        # Create transaction records
        forecast_count = create_forecasts(db, config, sites, products)
        inv_level_count = create_inventory_levels(db, config, sites, products)
        inv_policy_count = create_inventory_policies(db, config, sites, products)
        sourcing_count = create_sourcing_rules(db, config, sites, products, lanes)

        db.commit()

        # Summary
        print("\n" + "=" * 70)
        print("Food Dist Transaction Data Complete!")
        print("=" * 70)
        print(f"\nConfig: {config.name} (ID: {config.id})")
        print(f"\nAWS SC DM Transaction Tables:")
        print(f"  forecast: {forecast_count} records (52-week horizon with P10/P50/P90)")
        print(f"  inv_level: {inv_level_count} records (current stock levels)")
        print(f"  inv_policy: {inv_policy_count} records (safety stock policies)")
        print(f"  sourcing_rules: {sourcing_count} records (supplier priorities)")
        print("\n" + "=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

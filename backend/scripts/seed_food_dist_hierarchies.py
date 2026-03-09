#!/usr/bin/env python3
"""
Seed Food Dist Hierarchies - AWS SC DM Compliant

Creates complete hierarchies for the Food Dist demo using AWS SC DM tables:

Geography Hierarchy (AWS SC: geography table with parent_geo_id):
- Level 0: Company (Food Dist Corp)
- Level 1: Region (NW, SW, MTN)
- Level 2: State (OR, WA, CA, AZ, UT)
- Level 3: City (Portland, Seattle, Los Angeles, Phoenix, etc.)

Product Hierarchy (AWS SC: product_hierarchy table with parent_product_group_id):
- Level 0: Category (FROZEN, REFRIGERATED, DRY)
- Level 1: Family (FRZ_PROTEIN, REF_DAIRY, DRY_PANTRY, etc.)
- Level 2: Customer (linked to products via product_group_id)

DC Location: Salt Lake City, Utah (central hub serving NW and SW regions)
Suppliers: Located in neighboring states (CO, NV, ID, WY, AZ)

Usage:
    docker compose exec backend python scripts/seed_food_dist_hierarchies.py
"""

import sys
from pathlib import Path
from datetime import datetime

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from app.db.session import sync_engine
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import Product, Geography, ProductHierarchy, Company
from app.models.tenant import Tenant

# =============================================================================
# Geographic Hierarchy Configuration (AWS SC: geography table)
# =============================================================================

DC_CONFIG = {
    "code": "CDC_WEST",
    "name": "Food Dist Utah Distribution Center",
    "city": "Salt Lake City",
    "state": "UT",
    "location": "Salt Lake City, UT",
    "lat": 40.7608,
    "lon": -111.8910,
}

# Geographic hierarchy: Company → Region → State → City
GEOGRAPHY_HIERARCHY = {
    "NW": {
        "name": "Northwest Region",
        "states": {
            "OR": {
                "name": "Oregon",
                "cities": [
                    {"code": "PDX", "name": "Portland", "lat": 45.5152, "lon": -122.6784},
                    {"code": "EUG", "name": "Eugene", "lat": 44.0521, "lon": -123.0868},
                    {"code": "SAL", "name": "Salem", "lat": 44.9429, "lon": -123.0351},
                ]
            },
            "WA": {
                "name": "Washington",
                "cities": [
                    {"code": "SEA", "name": "Seattle", "lat": 47.6062, "lon": -122.3321},
                    {"code": "TAC", "name": "Tacoma", "lat": 47.2529, "lon": -122.4443},
                    {"code": "SPO", "name": "Spokane", "lat": 47.6588, "lon": -117.4260},
                ]
            },
        }
    },
    "SW": {
        "name": "Southwest Region",
        "states": {
            "CA": {
                "name": "California",
                "cities": [
                    {"code": "LAX", "name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
                    {"code": "SFO", "name": "San Francisco", "lat": 37.7749, "lon": -122.4194},
                    {"code": "SDG", "name": "San Diego", "lat": 32.7157, "lon": -117.1611},
                    {"code": "SAC", "name": "Sacramento", "lat": 38.5816, "lon": -121.4944},
                ]
            },
            "AZ": {
                "name": "Arizona",
                "cities": [
                    {"code": "PHX", "name": "Phoenix", "lat": 33.4484, "lon": -112.0740},
                    {"code": "TUS", "name": "Tucson", "lat": 32.2226, "lon": -110.9747},
                    {"code": "MES", "name": "Mesa", "lat": 33.4152, "lon": -111.8315},
                ]
            },
        }
    },
    "MTN": {
        "name": "Mountain Region (HQ)",
        "states": {
            "UT": {
                "name": "Utah",
                "cities": [
                    {"code": "SLC", "name": "Salt Lake City", "lat": 40.7608, "lon": -111.8910},
                ]
            },
        }
    },
}

# Suppliers in Utah's neighboring states
SUPPLIER_LOCATIONS = {
    "TYSON": {"name": "Tyson Foods Inc", "city": "Denver", "state": "CO", "distance_miles": 530, "lead_time_days": 1},
    "KRAFT": {"name": "Kraft Heinz Company", "city": "Boise", "state": "ID", "distance_miles": 340, "lead_time_days": 1},
    "GENMILLS": {"name": "General Mills Foodservice", "city": "Denver", "state": "CO", "distance_miles": 530, "lead_time_days": 1},
    "NESTLE": {"name": "Nestle Professional", "city": "Las Vegas", "state": "NV", "distance_miles": 420, "lead_time_days": 1},
    "TROP": {"name": "Tropicana Brands Group", "city": "Phoenix", "state": "AZ", "distance_miles": 660, "lead_time_days": 2},
    "SYSCOMEAT": {"name": "Sysco Protein Solutions", "city": "Cheyenne", "state": "WY", "distance_miles": 440, "lead_time_days": 1},
    "LANDOLAKES": {"name": "Land O'Lakes Foodservice", "city": "Boise", "state": "ID", "distance_miles": 340, "lead_time_days": 1},
    "CONAGRA": {"name": "Conagra Foodservice", "city": "Denver", "state": "CO", "distance_miles": 530, "lead_time_days": 1},
    "RICHPROD": {"name": "Rich Products Corporation", "city": "Reno", "state": "NV", "distance_miles": 520, "lead_time_days": 1},
    "COCACOLA": {"name": "Coca-Cola Foodservice", "city": "Las Vegas", "state": "NV", "distance_miles": 420, "lead_time_days": 1},
}

# Delivery times from SLC DC
DELIVERY_TIMES = {
    "PDX": 2, "EUG": 2, "SAL": 2, "SEA": 2, "TAC": 2, "SPO": 1,
    "LAX": 2, "SFO": 2, "SDG": 2, "SAC": 2, "PHX": 2, "TUS": 2, "MES": 2,
}

# =============================================================================
# Product Hierarchy Configuration (AWS SC: product_hierarchy table)
# =============================================================================

# Product hierarchy: Category → Family → (Products link via product_group_id)
PRODUCT_HIERARCHY = {
    "FROZEN": {
        "name": "Frozen Products",
        "level": 0,
        "families": {
            "FRZ_PROTEIN": {"name": "Frozen Proteins", "skus": ["FP001", "FP002", "FP003", "FP004", "FP005"]},
            "FRZ_DESSERT": {"name": "Frozen Desserts", "skus": ["FD001", "FD002", "FD003", "FD004", "FD005"]},
        }
    },
    "REFRIGERATED": {
        "name": "Refrigerated Products",
        "level": 0,
        "families": {
            "REF_DAIRY": {"name": "Refrigerated Dairy", "skus": ["RD001", "RD002", "RD003", "RD004", "RD005"]},
            "BEV": {"name": "Beverages", "skus": ["BV001", "BV002", "BV003", "BV004", "BV005"]},
        }
    },
    "DRY": {
        "name": "Dry Goods",
        "level": 0,
        "families": {
            "DRY_PANTRY": {"name": "Dry Goods Pantry", "skus": ["DP001", "DP002", "DP003", "DP004", "DP005"]},
        }
    },
}

# Product pricing (USD)
PRODUCT_PRICING = {
    "FP001": {"name": "Chicken Breast IQF", "unit_cost": 28.50, "unit_price": 34.99},
    "FP002": {"name": "Beef Patties 80/20", "unit_cost": 45.00, "unit_price": 54.99},
    "FP003": {"name": "Pork Chops Bone-In", "unit_cost": 32.00, "unit_price": 39.99},
    "FP004": {"name": "Turkey Breast Deli", "unit_cost": 38.00, "unit_price": 46.99},
    "FP005": {"name": "Seafood Mix Premium", "unit_cost": 55.00, "unit_price": 69.99},
    "RD001": {"name": "Cheddar Block Sharp", "unit_cost": 15.50, "unit_price": 19.99},
    "RD002": {"name": "Mozzarella Block LMPS", "unit_cost": 14.00, "unit_price": 18.49},
    "RD003": {"name": "Cream Cheese Block", "unit_cost": 8.50, "unit_price": 11.49},
    "RD004": {"name": "Greek Yogurt Plain", "unit_cost": 4.25, "unit_price": 5.99},
    "RD005": {"name": "Butter Salted Grade AA", "unit_cost": 85.00, "unit_price": 99.99},
    "DP001": {"name": "Pasta Penne Rigate", "unit_cost": 18.00, "unit_price": 23.99},
    "DP002": {"name": "Rice Long Grain", "unit_cost": 22.00, "unit_price": 28.99},
    "DP003": {"name": "Flour All Purpose", "unit_cost": 18.00, "unit_price": 24.99},
    "DP004": {"name": "Sugar Granulated", "unit_cost": 15.00, "unit_price": 19.99},
    "DP005": {"name": "Coffee Ground Medium", "unit_cost": 35.00, "unit_price": 44.99},
    "FD001": {"name": "Ice Cream Vanilla Premium", "unit_cost": 28.00, "unit_price": 35.99},
    "FD002": {"name": "Sorbet Mango", "unit_cost": 32.00, "unit_price": 41.99},
    "FD003": {"name": "Gelato Chocolate", "unit_cost": 38.00, "unit_price": 48.99},
    "FD004": {"name": "Pie Apple 10 inch", "unit_cost": 42.00, "unit_price": 52.99},
    "FD005": {"name": "Cake Chocolate Layer", "unit_cost": 55.00, "unit_price": 69.99},
    "BV001": {"name": "Orange Juice Premium", "unit_cost": 18.00, "unit_price": 23.99},
    "BV002": {"name": "Apple Juice Organic", "unit_cost": 15.00, "unit_price": 19.99},
    "BV003": {"name": "Lemonade Fresh", "unit_cost": 12.00, "unit_price": 16.49},
    "BV004": {"name": "Iced Tea Sweet", "unit_cost": 10.00, "unit_price": 13.99},
    "BV005": {"name": "Kombucha Ginger", "unit_cost": 28.00, "unit_price": 38.99},
}


def find_food_dist_tenant(db: Session) -> Tenant:
    """Find the Food Dist tenant (handles 'Food Dist' vs 'Food Distributor' naming)."""
    tenant = db.query(Tenant).filter(Tenant.name.ilike("Food Dist%")).first()
    if not tenant:
        raise ValueError("Food Dist tenant not found. Run seed_food_dist_demo.py first.")
    return tenant


def find_or_create_company(db: Session, tenant: Tenant) -> Company:
    """Find or create the Food Dist company record (AWS SC: company table)."""
    company_id = f"DF_CORP_{tenant.id}"
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        print(f"   Found existing company: {company.description}")
        return company

    company = Company(
        id=company_id,
        description="Food Dist Corporation",
        city="Mount Sterling",
        state_prov="IL",
        postal_code="62353",
        country="USA",
        time_zone="America/Chicago",
    )
    db.add(company)
    db.flush()
    print(f"   Created company: {company.description} (ID: {company.id})")
    return company


def create_geography_hierarchy(db: Session, company: Company) -> dict:
    """Create AWS SC DM geography hierarchy (Company → Region → State → City)."""
    print("\n1. Creating Geography Hierarchy (AWS SC: geography table)...")

    geo_map = {}  # Maps geo_id to Geography object

    # Check if already exists
    existing = db.query(Geography).filter(Geography.company_id == company.id).first()
    if existing:
        print("   Geography hierarchy already exists for this company")
        # Load existing into map
        all_geos = db.query(Geography).filter(Geography.company_id == company.id).all()
        for g in all_geos:
            geo_map[g.id] = g
        return geo_map

    # Level 0: Company-level geo (root)
    root_geo_id = f"GEO_{company.id}_ROOT"
    root_geo = Geography(
        id=root_geo_id,
        description="Food Dist - All Regions",
        company_id=company.id,
        parent_geo_id=None,
        country="USA",
    )
    db.add(root_geo)
    geo_map[root_geo_id] = root_geo
    print(f"   Created root: {root_geo.description}")

    # Level 1: Regions
    for region_code, region_data in GEOGRAPHY_HIERARCHY.items():
        region_geo_id = f"GEO_{company.id}_REG_{region_code}"
        region_geo = Geography(
            id=region_geo_id,
            description=region_data["name"],
            company_id=company.id,
            parent_geo_id=root_geo_id,
            country="USA",
        )
        db.add(region_geo)
        geo_map[region_geo_id] = region_geo
        print(f"   Created region: {region_data['name']}")

        # Level 2: States
        for state_code, state_data in region_data["states"].items():
            state_geo_id = f"GEO_{company.id}_{state_code}"
            state_geo = Geography(
                id=state_geo_id,
                description=state_data["name"],
                company_id=company.id,
                parent_geo_id=region_geo_id,
                state_prov=state_code,
                country="USA",
            )
            db.add(state_geo)
            geo_map[state_geo_id] = state_geo
            print(f"      Created state: {state_data['name']} ({state_code})")

            # Level 3: Cities
            for city_data in state_data["cities"]:
                city_geo_id = f"GEO_{company.id}_{city_data['code']}"
                city_geo = Geography(
                    id=city_geo_id,
                    description=f"{city_data['name']}, {state_code}",
                    company_id=company.id,
                    parent_geo_id=state_geo_id,
                    city=city_data["name"],
                    state_prov=state_code,
                    country="USA",
                    latitude=city_data["lat"],
                    longitude=city_data["lon"],
                )
                db.add(city_geo)
                geo_map[city_geo_id] = city_geo
                print(f"         Created city: {city_data['name']}")

    db.flush()
    print(f"   Total geography records: {len(geo_map)}")
    return geo_map


def create_product_hierarchy(db: Session, company: Company) -> dict:
    """Create AWS SC DM product hierarchy (Category → Family)."""
    print("\n2. Creating Product Hierarchy (AWS SC: product_hierarchy table)...")

    hierarchy_map = {}  # Maps hierarchy_id to ProductHierarchy object

    # Check if already exists
    existing = db.query(ProductHierarchy).filter(ProductHierarchy.company_id == company.id).first()
    if existing:
        print("   Product hierarchy already exists for this company")
        all_ph = db.query(ProductHierarchy).filter(ProductHierarchy.company_id == company.id).all()
        for ph in all_ph:
            hierarchy_map[ph.id] = ph
        return hierarchy_map

    sort_order = 0
    for cat_code, cat_data in PRODUCT_HIERARCHY.items():
        # Level 0: Category
        cat_id = f"PH_{company.id}_CAT_{cat_code}"
        category = ProductHierarchy(
            id=cat_id,
            description=cat_data["name"],
            company_id=company.id,
            parent_product_group_id=None,
            level=0,
            sort_order=sort_order,
            is_active="true",
        )
        db.add(category)
        hierarchy_map[cat_id] = category
        sort_order += 1
        print(f"   Created category: {cat_data['name']}")

        # Level 1: Families
        for fam_code, fam_data in cat_data["families"].items():
            fam_id = f"PH_{company.id}_FAM_{fam_code}"
            family = ProductHierarchy(
                id=fam_id,
                description=fam_data["name"],
                company_id=company.id,
                parent_product_group_id=cat_id,
                level=1,
                sort_order=sort_order,
                is_active="true",
            )
            db.add(family)
            hierarchy_map[fam_id] = family
            sort_order += 1
            print(f"      Created family: {fam_data['name']}")

    db.flush()
    print(f"   Total product hierarchy records: {len(hierarchy_map)}")
    return hierarchy_map


def find_or_create_config(db: Session, tenant: Tenant, company: Company) -> SupplyChainConfig:
    """Find or create supply chain config."""
    config = db.query(SupplyChainConfig).filter(SupplyChainConfig.tenant_id == tenant.id).first()
    if config:
        print(f"\n3. Found existing config: {config.name} (ID: {config.id})")
        return config

    print("\n3. Creating Supply Chain Config...")
    config = SupplyChainConfig(
        name="Food Dist Distribution Network",
        description="AWS SC DM compliant foodservice redistribution network",
        tenant_id=tenant.id,
        is_active=True,
    )
    db.add(config)
    db.flush()
    print(f"   Created config: {config.name} (ID: {config.id})")
    return config


def create_sites(db: Session, config: SupplyChainConfig, company: Company, geo_map: dict) -> dict:
    """Create sites (DC, suppliers, customers) linked to geography."""
    print("\n4. Creating Sites (linked to Geography via geo_id)...")

    site_map = {}

    # Check if sites exist
    existing = db.query(Site).filter(Site.config_id == config.id).first()
    if existing:
        print("   Sites already exist for this config")
        all_sites = db.query(Site).filter(Site.config_id == config.id).all()
        for s in all_sites:
            site_map[s.name] = s
        return site_map

    # DC in Salt Lake City
    slc_geo_id = f"GEO_{company.id}_SLC"
    dc = Site(
        config_id=config.id,
        name="CDC_WEST",
        type="Distribution Center",
        dag_type="DISTRIBUTOR",
        master_type="INVENTORY",
        geo_id=slc_geo_id,
        company_id=company.id,
        attributes={
            "location": DC_CONFIG["location"],
            "capacity": 650000,
            "holding_cost": 0.25,
        }
    )
    db.add(dc)
    site_map["CDC_WEST"] = dc
    print(f"   Created DC: {dc.name} (geo: {slc_geo_id})")

    # Suppliers (no geo linking for now - external to company)
    for supp_code, supp_data in SUPPLIER_LOCATIONS.items():
        supplier = Site(
            config_id=config.id,
            name=supp_code,
            type=f"Supplier - {supp_data['name']}",
            dag_type="SUPPLIER",
            master_type="MARKET_SUPPLY",
            attributes={
                "description": supp_data["name"],
                "location": f"{supp_data['city']}, {supp_data['state']}",
                "distance_from_dc_miles": supp_data["distance_miles"],
                "lead_time_days": supp_data["lead_time_days"],
            }
        )
        db.add(supplier)
        site_map[supp_code] = supplier
    print(f"   Created {len(SUPPLIER_LOCATIONS)} suppliers")

    # Customers - linked to city geography
    customer_count = 0
    for region_code, region_data in GEOGRAPHY_HIERARCHY.items():
        for state_code, state_data in region_data["states"].items():
            for city_data in state_data["cities"]:
                city_geo_id = f"GEO_{company.id}_{city_data['code']}"
                customer = Site(
                    config_id=config.id,
                    name=f"CUST_{city_data['code']}",
                    type=f"Customer - {city_data['name']}, {state_code}",
                    dag_type="RETAILER",
                    master_type="MARKET_DEMAND",
                    geo_id=city_geo_id,
                    company_id=company.id,
                    attributes={
                        "delivery_time_days": DELIVERY_TIMES.get(city_data["code"], 2),
                    }
                )
                db.add(customer)
                site_map[f"CUST_{city_data['code']}"] = customer
                customer_count += 1
    print(f"   Created {customer_count} customers (linked to geography)")

    db.flush()
    return site_map


def create_transportation_lanes(db: Session, config: SupplyChainConfig, site_map: dict):
    """Create transportation lanes."""
    print("\n5. Creating Transportation Lanes...")

    existing = db.query(TransportationLane).filter(TransportationLane.config_id == config.id).first()
    if existing:
        print("   Lanes already exist")
        return

    dc = site_map.get("CDC_WEST")
    if not dc:
        print("   ERROR: DC not found")
        return

    lane_count = 0

    # Supplier → DC
    for supp_code, supp_data in SUPPLIER_LOCATIONS.items():
        supplier = site_map.get(supp_code)
        if supplier:
            lt = supp_data["lead_time_days"]
            lane = TransportationLane(
                config_id=config.id,
                from_site_id=supplier.id,
                to_site_id=dc.id,
                capacity=10000,
                lead_time_days={"min": lt, "max": lt + 1},
                supply_lead_time={"type": "deterministic", "value": lt},
            )
            db.add(lane)
            lane_count += 1

    # DC → Customers
    for site_name, site in site_map.items():
        if site_name.startswith("CUST_"):
            city_code = site_name.replace("CUST_", "")
            lt = DELIVERY_TIMES.get(city_code, 2)
            lane = TransportationLane(
                config_id=config.id,
                from_site_id=dc.id,
                to_site_id=site.id,
                capacity=5000,
                lead_time_days={"min": lt, "max": lt + 1},
                supply_lead_time={"type": "deterministic", "value": lt},
            )
            db.add(lane)
            lane_count += 1

    db.flush()
    print(f"   Created {lane_count} lanes")


def create_products(db: Session, config: SupplyChainConfig, company: Company, hierarchy_map: dict):
    """Create products linked to product_hierarchy via product_group_id."""
    print("\n6. Creating Products (linked to ProductHierarchy)...")

    existing = db.query(Product).filter(Product.config_id == config.id).first()
    if existing:
        print("   Products already exist, updating hierarchy links...")

    product_count = 0
    for cat_code, cat_data in PRODUCT_HIERARCHY.items():
        cat_id = f"PH_{company.id}_CAT_{cat_code}"

        for fam_code, fam_data in cat_data["families"].items():
            fam_id = f"PH_{company.id}_FAM_{fam_code}"

            for sku in fam_data["skus"]:
                pricing = PRODUCT_PRICING.get(sku, {})
                product_id = f"CFG{config.id}_{sku}"

                # Check if exists
                product = db.query(Product).filter(Product.id == product_id).first()
                if product:
                    # Update existing
                    product.product_group_id = fam_id
                    product.category = cat_data["name"]
                    product.family = fam_data["name"]
                    product.unit_cost = pricing.get("unit_cost", product.unit_cost)
                    product.unit_price = pricing.get("unit_price", product.unit_price)
                else:
                    # Create new
                    product = Product(
                        id=product_id,
                        description=pricing.get("name", sku),
                        company_id=company.id,
                        product_group_id=fam_id,
                        category=cat_data["name"],
                        family=fam_data["name"],
                        unit_cost=pricing.get("unit_cost"),
                        unit_price=pricing.get("unit_price"),
                        config_id=config.id,
                        is_active="true",
                    )
                    db.add(product)
                product_count += 1

    db.flush()
    print(f"   Created/updated {product_count} products")


def print_summary(db: Session, tenant: Tenant, config: SupplyChainConfig, company: Company):
    """Print summary."""
    print("\n" + "=" * 70)
    print("Food Dist AWS SC DM Hierarchy Setup Complete!")
    print("=" * 70)

    geo_count = db.query(Geography).filter(Geography.company_id == company.id).count()
    ph_count = db.query(ProductHierarchy).filter(ProductHierarchy.company_id == company.id).count()
    site_count = db.query(Site).filter(Site.config_id == config.id).count()
    product_count = db.query(Product).filter(Product.config_id == config.id).count()
    lane_count = db.query(TransportationLane).filter(TransportationLane.config_id == config.id).count()

    print(f"\nGroup: {tenant.name} (ID: {tenant.id})")
    print(f"Company: {company.description} (ID: {company.id})")
    print(f"Config: {config.name} (ID: {config.id})")

    print(f"\nAWS SC DM Tables:")
    print(f"  geography: {geo_count} records (Company → Region → State → City)")
    print(f"  product_hierarchy: {ph_count} records (Category → Family)")
    print(f"  site: {site_count} records (DC + suppliers + customers)")
    print(f"  product: {product_count} records (linked via product_group_id)")
    print(f"  transportation_lane: {lane_count} records")

    print("\nGeography Hierarchy (3 levels):")
    print("  Regions: NW, SW, MTN")
    print("  States: OR, WA, CA, AZ, UT")
    print("  Cities: Portland, Seattle, Los Angeles, Phoenix, Salt Lake City, etc.")

    print("\nProduct Hierarchy (2 levels + SKUs):")
    print("  Categories: FROZEN, REFRIGERATED, DRY")
    print("  Families: FRZ_PROTEIN, REF_DAIRY, DRY_PANTRY, FRZ_DESSERT, BEV")
    print("  Products: 25 SKUs with USD pricing")

    print("\n" + "=" * 70)


def main():
    """Main function."""
    print("=" * 70)
    print("Seeding Food Dist Hierarchies (AWS SC DM Compliant)")
    print("=" * 70)

    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SyncSessionLocal()

    try:
        tenant = find_food_dist_tenant(db)
        print(f"\nFound tenant: {tenant.name} (ID: {tenant.id})")

        company = find_or_create_company(db, tenant)
        geo_map = create_geography_hierarchy(db, company)
        hierarchy_map = create_product_hierarchy(db, company)
        config = find_or_create_config(db, tenant, company)
        site_map = create_sites(db, config, company, geo_map)
        create_transportation_lanes(db, config, site_map)
        create_products(db, config, company, hierarchy_map)

        db.commit()
        print_summary(db, tenant, config, company)

    except Exception as e:
        print(f"\nError: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

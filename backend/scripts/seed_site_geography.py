#!/usr/bin/env python3
"""
Seed geography data for Beer Game sites using AWS SC DM approach.

Creates realistic geography records based on site types:
- Retailers: Major retail/grocery chain locations
- Wholesalers: Regional distribution hubs
- Distributors: Major logistics DC locations
- Manufacturers/Factories: Brewery/manufacturing facilities
- Market Supply: Raw material supplier regions
- Market Demand: Consumer market metropolitan areas

Uses hierarchical geography structure per AWS SC DM:
  Company -> Region -> State -> City -> Site
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings
from app.models.sc_entities import Geography
from app.models.supply_chain_config import Site, SupplyChainConfig


# Realistic geography data by site type
# Using actual business locations for authenticity

GEOGRAPHY_DATA = {
    # ============================================================
    # RETAILER LOCATIONS - Major grocery/retail chain locations
    # ============================================================
    "retailer": {
        "name": "Retailer",
        "description": "Kroger - Cincinnati HQ Store",
        "address_1": "1014 Vine Street",
        "city": "Cincinnati",
        "state_prov": "OH",
        "postal_code": "45202",
        "country": "USA",
        "latitude": 39.1031,
        "longitude": -84.5120,
        "time_zone": "America/New_York",
    },

    # ============================================================
    # WHOLESALER LOCATIONS - Regional distribution hubs
    # ============================================================
    "wholesaler": {
        "name": "Wholesaler",
        "description": "McLane Company - Temple TX Hub",
        "address_1": "4747 McLane Parkway",
        "city": "Temple",
        "state_prov": "TX",
        "postal_code": "76504",
        "country": "USA",
        "latitude": 31.1171,
        "longitude": -97.3428,
        "time_zone": "America/Chicago",
    },

    # ============================================================
    # DISTRIBUTOR LOCATIONS - Major logistics DC hubs
    # ============================================================
    "distributor": {
        "name": "Distributor",
        "description": "Food Dist - Mt Sterling IL DC",
        "address_1": "1 Dot Way",
        "city": "Mt Sterling",
        "state_prov": "IL",
        "postal_code": "62353",
        "country": "USA",
        "latitude": 39.9872,
        "longitude": -90.7632,
        "time_zone": "America/Chicago",
    },

    # ============================================================
    # FACTORY/MANUFACTURER LOCATIONS - Brewing/production facilities
    # ============================================================
    "factory": {
        "name": "Factory",
        "description": "Anheuser-Busch - St. Louis Brewery",
        "address_1": "1 Busch Place",
        "city": "St. Louis",
        "state_prov": "MO",
        "postal_code": "63118",
        "country": "USA",
        "latitude": 38.5990,
        "longitude": -90.2090,
        "time_zone": "America/Chicago",
    },
    "case_mfg": {
        "name": "Case Mfg",
        "description": "International Paper - Memphis Plant",
        "address_1": "6400 Poplar Avenue",
        "city": "Memphis",
        "state_prov": "TN",
        "postal_code": "38197",
        "country": "USA",
        "latitude": 35.1175,
        "longitude": -89.9711,
        "time_zone": "America/Chicago",
    },
    "six_pack_mfg": {
        "name": "Six-Pack Mfg",
        "description": "Graphic Packaging - Atlanta Plant",
        "address_1": "1500 Riveredge Parkway",
        "city": "Atlanta",
        "state_prov": "GA",
        "postal_code": "30328",
        "country": "USA",
        "latitude": 33.9304,
        "longitude": -84.3733,
        "time_zone": "America/New_York",
    },
    "bottle_mfg": {
        "name": "Bottle Mfg",
        "description": "O-I Glass - Perrysburg Plant",
        "address_1": "1 Michael Owens Way",
        "city": "Perrysburg",
        "state_prov": "OH",
        "postal_code": "43551",
        "country": "USA",
        "latitude": 41.5570,
        "longitude": -83.6271,
        "time_zone": "America/New_York",
    },

    # ============================================================
    # MARKET SUPPLY - Raw material supplier regions
    # ============================================================
    "market_supply": {
        "name": "Market Supply",
        "description": "Cargill - Minneapolis Grain Hub",
        "address_1": "15407 McGinty Road West",
        "city": "Wayzata",
        "state_prov": "MN",
        "postal_code": "55391",
        "country": "USA",
        "latitude": 44.9740,
        "longitude": -93.5066,
        "time_zone": "America/Chicago",
    },

    # ============================================================
    # MARKET DEMAND - Consumer market metropolitan areas
    # ============================================================
    "market_demand": {
        "name": "Market Demand",
        "description": "Chicago Metropolitan Market",
        "address_1": "Chicago Metro Area",
        "city": "Chicago",
        "state_prov": "IL",
        "postal_code": "60601",
        "country": "USA",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "time_zone": "America/Chicago",
    },

    # ============================================================
    # COMPONENT SUPPLIERS - For Complex_SC config
    # ============================================================
    "component_supplier": {
        "name": "Component Supplier",
        "description": "Industrial Components - Cleveland",
        "address_1": "1200 Industrial Parkway",
        "city": "Cleveland",
        "state_prov": "OH",
        "postal_code": "44114",
        "country": "USA",
        "latitude": 41.4993,
        "longitude": -81.6944,
        "time_zone": "America/New_York",
    },

    # ============================================================
    # PLANT - Manufacturing plants
    # ============================================================
    "plant": {
        "name": "Plant",
        "description": "Manufacturing Plant - Indianapolis",
        "address_1": "500 Manufacturing Drive",
        "city": "Indianapolis",
        "state_prov": "IN",
        "postal_code": "46204",
        "country": "USA",
        "latitude": 39.7684,
        "longitude": -86.1581,
        "time_zone": "America/New_York",
    },
}

# Alternative locations for sites with same type (to avoid all same locations)
ALTERNATIVE_LOCATIONS = {
    "retailer": [
        {"city": "Dallas", "state_prov": "TX", "latitude": 32.7767, "longitude": -96.7970, "desc": "Kroger - Dallas Division"},
        {"city": "Denver", "state_prov": "CO", "latitude": 39.7392, "longitude": -104.9903, "desc": "King Soopers - Denver"},
        {"city": "Atlanta", "state_prov": "GA", "latitude": 33.7490, "longitude": -84.3880, "desc": "Kroger - Atlanta Division"},
        {"city": "Phoenix", "state_prov": "AZ", "latitude": 33.4484, "longitude": -112.0740, "desc": "Fry's Food - Phoenix"},
        {"city": "Seattle", "state_prov": "WA", "latitude": 47.6062, "longitude": -122.3321, "desc": "QFC - Seattle"},
    ],
    "wholesaler": [
        {"city": "Carrollton", "state_prov": "TX", "latitude": 32.9537, "longitude": -96.8903, "desc": "McLane - Carrollton DC"},
        {"city": "Rocky Mount", "state_prov": "NC", "latitude": 35.9382, "longitude": -77.7905, "desc": "McLane - Rocky Mount DC"},
        {"city": "Northfield", "state_prov": "MN", "latitude": 44.4583, "longitude": -93.1616, "desc": "SuperValu - Northfield"},
    ],
    "distributor": [
        {"city": "Modesto", "state_prov": "CA", "latitude": 37.6391, "longitude": -120.9969, "desc": "Food Dist - Modesto DC"},
        {"city": "Vidalia", "state_prov": "GA", "latitude": 32.2177, "longitude": -82.4135, "desc": "Food Dist - Vidalia DC"},
        {"city": "Williamsport", "state_prov": "MD", "latitude": 39.6012, "longitude": -77.8203, "desc": "Food Dist - Williamsport DC"},
    ],
    "component_supplier": [
        {"city": "Detroit", "state_prov": "MI", "latitude": 42.3314, "longitude": -83.0458, "desc": "Auto Parts Supplier - Detroit"},
        {"city": "Pittsburgh", "state_prov": "PA", "latitude": 40.4406, "longitude": -79.9959, "desc": "Steel Components - Pittsburgh"},
        {"city": "Chicago", "state_prov": "IL", "latitude": 41.8781, "longitude": -87.6298, "desc": "Industrial Supply - Chicago"},
        {"city": "Milwaukee", "state_prov": "WI", "latitude": 43.0389, "longitude": -87.9065, "desc": "Manufacturing Parts - Milwaukee"},
        {"city": "Toledo", "state_prov": "OH", "latitude": 41.6528, "longitude": -83.5379, "desc": "Glass Components - Toledo"},
        {"city": "Grand Rapids", "state_prov": "MI", "latitude": 42.9634, "longitude": -85.6681, "desc": "Furniture Parts - Grand Rapids"},
        {"city": "Fort Wayne", "state_prov": "IN", "latitude": 41.0793, "longitude": -85.1394, "desc": "Electronics Components - Fort Wayne"},
        {"city": "Columbus", "state_prov": "OH", "latitude": 39.9612, "longitude": -82.9988, "desc": "Logistics Parts - Columbus"},
        {"city": "Louisville", "state_prov": "KY", "latitude": 38.2527, "longitude": -85.7585, "desc": "Appliance Parts - Louisville"},
        {"city": "Nashville", "state_prov": "TN", "latitude": 36.1627, "longitude": -86.7816, "desc": "Auto Components - Nashville"},
    ],
}


def create_geography_id(config_id: int, site_type: str, index: int = 0) -> str:
    """Generate a unique geography ID following AWS SC DM conventions."""
    type_abbrev = site_type.upper().replace("_", "")[:6]
    return f"GEO_BG_{config_id}_{type_abbrev}_{index:02d}"


def get_location_for_site(site_type: str, index: int = 0) -> dict:
    """Get location data for a site type, using alternatives for duplicates."""
    dag_type = site_type.lower()

    # Get base location
    if dag_type in GEOGRAPHY_DATA:
        base = GEOGRAPHY_DATA[dag_type].copy()
    else:
        # Default to a generic location
        base = GEOGRAPHY_DATA.get("distributor", {}).copy()
        base["description"] = f"Generic Location - {site_type}"

    # If we have alternatives and this isn't the first site, use alternative
    if dag_type in ALTERNATIVE_LOCATIONS and index > 0:
        alts = ALTERNATIVE_LOCATIONS[dag_type]
        alt_idx = (index - 1) % len(alts)
        alt = alts[alt_idx]
        base["city"] = alt["city"]
        base["state_prov"] = alt["state_prov"]
        base["latitude"] = alt["latitude"]
        base["longitude"] = alt["longitude"]
        base["description"] = alt["desc"]
        base["postal_code"] = ""  # Clear postal code for alternates

    return base


def seed_geography_for_config(db: Session, config: SupplyChainConfig) -> int:
    """Seed geography records for all sites in a configuration."""
    print(f"\nProcessing config: {config.name} (ID: {config.id})")

    # Get all sites for this config
    sites = db.query(Site).filter(Site.config_id == config.id).all()

    if not sites:
        print(f"  No sites found for config {config.id}")
        return 0

    # Track site type counts for alternates
    type_counts = {}
    created_count = 0

    for site in sites:
        dag_type = (site.dag_type or site.type or "unknown").lower()

        # Skip if already has geography
        if site.geo_id:
            print(f"  Site '{site.name}' already has geo_id: {site.geo_id}")
            continue

        # Get index for this type (for alternates)
        type_counts[dag_type] = type_counts.get(dag_type, 0)
        index = type_counts[dag_type]
        type_counts[dag_type] += 1

        # Generate geography ID
        geo_id = create_geography_id(config.id, dag_type, index)

        # Check if geography already exists
        existing_geo = db.query(Geography).filter(Geography.id == geo_id).first()

        if not existing_geo:
            # Get location data
            loc = get_location_for_site(dag_type, index)

            # Create geography record
            geo = Geography(
                id=geo_id,
                description=f"{loc.get('description', site.name)} - {config.name}",
                address_1=loc.get("address_1"),
                city=loc.get("city"),
                state_prov=loc.get("state_prov"),
                postal_code=loc.get("postal_code"),
                country=loc.get("country", "USA"),
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
                time_zone=loc.get("time_zone", "America/Chicago"),
            )
            db.add(geo)
            print(f"  Created geography: {geo_id} ({loc.get('city')}, {loc.get('state_prov')})")
            created_count += 1
        else:
            print(f"  Geography already exists: {geo_id}")

        # Link site to geography
        site.geo_id = geo_id
        print(f"  Linked site '{site.name}' -> {geo_id}")

    return created_count


def main():
    """Main entry point."""
    print("=" * 60)
    print("Seeding Site Geography Data (AWS SC DM Approach)")
    print("=" * 60)

    # Create sync engine and session
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        try:
            # Get all supply chain configs
            configs = db.query(SupplyChainConfig).order_by(SupplyChainConfig.id).all()

            total_created = 0
            for config in configs:
                created = seed_geography_for_config(db, config)
                total_created += created

            # Commit all changes
            db.commit()

            print("\n" + "=" * 60)
            print(f"SUCCESS: Created {total_created} geography records")
            print("=" * 60)

            # Show summary
            geo_count = db.query(Geography).count()
            linked_sites = db.query(Site).filter(Site.geo_id.isnot(None)).count()
            total_sites = db.query(Site).count()

            print(f"\nSummary:")
            print(f"  Total geography records: {geo_count}")
            print(f"  Sites with geography: {linked_sites}/{total_sites}")

        except Exception as e:
            print(f"\nERROR: {e}")
            db.rollback()
            raise


if __name__ == "__main__":
    main()

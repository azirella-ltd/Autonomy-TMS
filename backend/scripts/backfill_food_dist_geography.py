#!/usr/bin/env python3
"""
Backfill hierarchical Geography records for existing Food Dist sites.

Creates a proper Country → Region → State → City hierarchy using parent_geo_id,
updates site coordinates to new locations (DC in Utah, customers in AZ/CA/OR/WA),
and renames DOTFOODS_DC site to CDC_WEST.

Safe to re-run - updates existing records and creates missing ones.

Usage:
    docker compose exec backend python scripts/backfill_food_dist_geography.py
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text
from app.db.session import sync_engine, sync_session_factory
from app.models.sc_entities import Geography
from app.models.supply_chain_config import SupplyChainConfig, Site


# ============================================================================
# Geographic hierarchy definitions
# ============================================================================

STATE_TO_REGION = {
    "OR": "NW", "WA": "NW",
    "AZ": "SW", "CA": "SW", "UT": "SW",
    "IL": "CENTRAL", "MN": "CENTRAL", "TX": "CENTRAL", "AR": "CENTRAL",
    "PA": "NE", "NY": "NE",
    "GA": "SE",
}

REGION_NAMES = {
    "NW": "Northwest",
    "SW": "Southwest",
    "CENTRAL": "Central",
    "NE": "Northeast",
    "SE": "Southeast",
}

STATE_NAMES = {
    "OR": "Oregon", "WA": "Washington", "AZ": "Arizona", "CA": "California",
    "UT": "Utah", "IL": "Illinois", "MN": "Minnesota", "TX": "Texas",
    "AR": "Arkansas", "PA": "Pennsylvania", "NY": "New York", "GA": "Georgia",
}

# Site coordinates: code -> (city, state, lat, lon)
SITE_COORDINATES = {
    # DC - West Valley City, UT
    "CDC_WEST": ("West Valley City", "UT", 40.6916, -112.0011),
    # Also match old name for migration
    "DOTFOODS_DC": ("West Valley City", "UT", 40.6916, -112.0011),
    # Suppliers (real HQ locations)
    "TYSON": ("Springdale", "AR", 36.1544, -94.1537),
    "KRAFT": ("Pittsburgh", "PA", 40.4545, -79.9909),
    "GENMILLS": ("Minneapolis", "MN", 44.9800, -93.2650),
    "NESTLE": ("Glendale", "CA", 34.1899, -118.2437),
    "TROP": ("Chicago", "IL", 41.8881, -87.6180),
    "SYSCOMEAT": ("Houston", "TX", 29.7437, -95.3643),
    "LANDOLAKES": ("Arden Hills", "MN", 45.0253, -93.1864),
    "CONAGRA": ("Chicago", "IL", 41.8881, -87.6180),
    "RICHPROD": ("Buffalo", "NY", 42.8864, -78.8784),
    "COCACOLA": ("Atlanta", "GA", 33.7695, -84.3964),
    # Customers (AZ, CA, OR, WA)
    "RESTSUPPLY": ("Portland", "OR", 45.5152, -122.6784),
    "CAMPUSDINE": ("Eugene", "OR", 44.0521, -123.0868),
    "DWNTWNDELI": ("Seattle", "WA", 47.6062, -122.3321),
    "PREMCATER": ("Tacoma", "WA", 47.2529, -122.4443),
    "METROGRO": ("Los Angeles", "CA", 34.0522, -118.2437),
    "COASTHLTH": ("San Francisco", "CA", 37.7749, -122.4194),
    "FAMREST": ("Sacramento", "CA", 38.5816, -121.4944),
    "SCHLDFOOD": ("San Diego", "CA", 32.7157, -117.1611),
    "QUICKSERV": ("Phoenix", "AZ", 33.4484, -112.0740),
    "GREENVAL": ("Tucson", "AZ", 32.2226, -110.9747),
}

# Rename map for sites: old_name -> new_name
SITE_RENAMES = {
    "DOTFOODS_DC": "CDC_WEST",
}


def _get_or_create_geo(db, geo_id, **kwargs):
    """Get existing geography or create new one. Returns (geo, created)."""
    existing = db.query(Geography).filter(Geography.id == geo_id).first()
    if existing:
        # Update fields if changed
        changed = False
        for k, v in kwargs.items():
            if v is not None and getattr(existing, k, None) != v:
                setattr(existing, k, v)
                changed = True
        return existing, False, changed
    geo = Geography(id=geo_id, **kwargs)
    db.add(geo)
    db.flush()
    return geo, True, False


def main():
    db = sync_session_factory()
    try:
        # Find Food Dist SC configs (match both old and new names)
        configs = (
            db.query(SupplyChainConfig)
            .filter(
                SupplyChainConfig.name.ilike("%Food Dist%")
                | SupplyChainConfig.name.ilike("%DotFoods%")
            )
            .all()
        )

        if not configs:
            print("No Food Dist SC config found. Nothing to backfill.")
            return

        # Also rename configs with old names
        for config in configs:
            if "DotFoods" in config.name:
                old_name = config.name
                config.name = config.name.replace("DotFoods", "Food Dist")
                print(f"  RENAME config: '{old_name}' -> '{config.name}'")
            if "Dot Foods" in (config.description or ""):
                config.description = config.description.replace("Dot Foods", "Food Dist")

        stats = {"hierarchy_created": 0, "site_geo_created": 0, "updated": 0, "linked": 0, "renamed": 0}

        for config in configs:
            prefix = f"CFG{config.id}_"
            print(f"\nProcessing config: {config.name} (ID: {config.id})")

            # --- Step 0: Rename sites with old names ---
            for old_name, new_name in SITE_RENAMES.items():
                site = db.query(Site).filter(
                    Site.config_id == config.id,
                    Site.name == old_name,
                ).first()
                if site:
                    site.name = new_name
                    stats["renamed"] += 1
                    print(f"  RENAME site: {old_name} -> {new_name}")

            # --- Step 1: Delete old flat geography records ---
            old_geos = db.query(Geography).filter(
                Geography.id.like(f"{prefix}GEO_%")
            ).all()
            if old_geos:
                # Unlink sites first
                sites = db.query(Site).filter(Site.config_id == config.id).all()
                for site in sites:
                    if site.geo_id and site.geo_id.startswith(prefix):
                        site.geo_id = None
                db.flush()

                # Delete old geos (children first, then parents)
                # Sort by id length descending to delete children before parents
                for geo in sorted(old_geos, key=lambda g: len(g.id), reverse=True):
                    db.delete(geo)
                db.flush()
                print(f"  Cleaned up {len(old_geos)} old flat geography records")

            # --- Step 2: Create hierarchical geography ---

            # Country: USA
            usa_id = f"{prefix}GEO_USA"
            usa_geo, created, _ = _get_or_create_geo(db, usa_id,
                description="United States", country="USA")
            if created:
                stats["hierarchy_created"] += 1

            # Regions
            region_geos = {}
            for region_code, region_name in REGION_NAMES.items():
                geo_id = f"{prefix}GEO_REG_{region_code}"
                geo, created, _ = _get_or_create_geo(db, geo_id,
                    description=f"{region_name} Region",
                    country="USA",
                    parent_geo_id=usa_geo.id)
                if created:
                    stats["hierarchy_created"] += 1
                region_geos[region_code] = geo
            db.flush()

            # States (only for states we have sites in)
            state_geos = {}
            states_needed = set()
            sites = db.query(Site).filter(Site.config_id == config.id).all()
            for site in sites:
                coords = SITE_COORDINATES.get(site.name)
                if coords:
                    states_needed.add(coords[1])  # state abbreviation

            for state_abbr in sorted(states_needed):
                region_code = STATE_TO_REGION.get(state_abbr)
                if not region_code or region_code not in region_geos:
                    continue
                geo_id = f"{prefix}GEO_ST_{state_abbr}"
                geo, created, _ = _get_or_create_geo(db, geo_id,
                    description=STATE_NAMES.get(state_abbr, state_abbr),
                    state_prov=state_abbr,
                    country="USA",
                    parent_geo_id=region_geos[region_code].id)
                if created:
                    stats["hierarchy_created"] += 1
                state_geos[state_abbr] = geo
            db.flush()

            # --- Step 3: Create city-level (site) geographies ---
            for site in sites:
                coords = SITE_COORDINATES.get(site.name)
                if not coords:
                    print(f"  SKIP: {site.name} (no coordinates defined)")
                    continue

                city, state, lat, lon = coords
                geo_id = f"{prefix}GEO_{site.name}"
                parent_state = state_geos.get(state)

                geo, created, changed = _get_or_create_geo(db, geo_id,
                    description=f"{site.name} - {city}, {state}",
                    city=city,
                    state_prov=state,
                    country="USA",
                    latitude=lat,
                    longitude=lon,
                    parent_geo_id=parent_state.id if parent_state else None)

                if created:
                    stats["site_geo_created"] += 1
                    print(f"  CREATE: {site.name} -> {city}, {state} ({lat}, {lon})")
                elif changed:
                    stats["updated"] += 1
                    print(f"  UPDATE: {site.name} -> {city}, {state} ({lat}, {lon})")

                # Link site to geography
                if site.geo_id != geo_id:
                    site.geo_id = geo_id
                    stats["linked"] += 1

            db.flush()

        db.commit()
        print(f"\nDone:")
        print(f"  {stats['renamed']} sites renamed")
        print(f"  {stats['hierarchy_created']} hierarchy nodes created (country/region/state)")
        print(f"  {stats['site_geo_created']} site geography records created")
        print(f"  {stats['updated']} geography records updated")
        print(f"  {stats['linked']} sites linked to geography")

    finally:
        db.close()


if __name__ == "__main__":
    main()

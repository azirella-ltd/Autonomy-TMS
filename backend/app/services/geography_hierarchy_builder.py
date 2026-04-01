"""
Geography Hierarchy Builder — AWS SC DM geography table population.

Builds the geographic hierarchy (Country → Region → State → City) from
site and trading partner address data. Runs during provisioning warm_start
to ensure all views have geography-based drilldown.

Sources of address data (in priority order):
  1. Existing geography records (from ERP extraction, e.g., SAP ADRC)
  2. Site latitude/longitude (reverse-geocoded or mapped to nearest city)
  3. Trading partner address fields (city, state_prov, country)
  4. Site name patterns (e.g., "CUST_LAX" → Los Angeles, CA)

The builder is idempotent — re-running updates existing records.

Region assignment uses US Census Bureau divisions:
  - Pacific (WA, OR, CA, HI, AK)
  - Mountain (MT, ID, WY, NV, UT, CO, AZ, NM)
  - West North Central (ND, SD, NE, KS, MN, IA, MO)
  - East North Central (WI, MI, IL, IN, OH)
  - New England (ME, NH, VT, MA, RI, CT)
  - Mid-Atlantic (NY, NJ, PA)
  - South Atlantic (DE, MD, DC, VA, WV, NC, SC, GA, FL)
  - East South Central (KY, TN, AL, MS)
  - West South Central (AR, LA, OK, TX)

For non-US countries, regions are derived from state_prov groupings.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# US state → Census region mapping
US_STATE_REGION = {
    'WA': 'Pacific', 'OR': 'Pacific', 'CA': 'Pacific', 'HI': 'Pacific', 'AK': 'Pacific',
    'MT': 'Mountain', 'ID': 'Mountain', 'WY': 'Mountain', 'NV': 'Mountain',
    'UT': 'Mountain', 'CO': 'Mountain', 'AZ': 'Mountain', 'NM': 'Mountain',
    'ND': 'West North Central', 'SD': 'West North Central', 'NE': 'West North Central',
    'KS': 'West North Central', 'MN': 'West North Central', 'IA': 'West North Central',
    'MO': 'West North Central',
    'WI': 'East North Central', 'MI': 'East North Central', 'IL': 'East North Central',
    'IN': 'East North Central', 'OH': 'East North Central',
    'ME': 'New England', 'NH': 'New England', 'VT': 'New England',
    'MA': 'New England', 'RI': 'New England', 'CT': 'New England',
    'NY': 'Mid-Atlantic', 'NJ': 'Mid-Atlantic', 'PA': 'Mid-Atlantic',
    'DE': 'South Atlantic', 'MD': 'South Atlantic', 'DC': 'South Atlantic',
    'VA': 'South Atlantic', 'WV': 'South Atlantic', 'NC': 'South Atlantic',
    'SC': 'South Atlantic', 'GA': 'South Atlantic', 'FL': 'South Atlantic',
    'KY': 'East South Central', 'TN': 'East South Central',
    'AL': 'East South Central', 'MS': 'East South Central',
    'AR': 'West South Central', 'LA': 'West South Central',
    'OK': 'West South Central', 'TX': 'West South Central',
}


def build_geography_hierarchy(
    db: Session,
    config_id: int,
    company_id: str,
) -> Dict[str, Any]:
    """Build geography hierarchy from site/trading partner address data.

    Idempotent — can be called multiple times safely.

    Returns summary of what was created.
    """
    result = {"countries": 0, "regions": 0, "states": 0, "cities": 0, "sites_linked": 0}

    # Collect all address data from sites and trading partners
    addresses = _collect_addresses(db, config_id, company_id)
    if not addresses:
        logger.info("No address data found for config %d — geography hierarchy skipped", config_id)
        return result

    # Group by country → region → state → city
    hierarchy = _build_hierarchy(addresses)

    # Create geography records
    geo_ids = {}  # key → geo_id

    for country, regions in hierarchy.items():
        country_id = f"{company_id}-{country}"
        _upsert_geo(db, country_id, country, company_id, country=country)
        geo_ids[country] = country_id
        result["countries"] += 1

        for region, states in regions.items():
            region_id = f"{company_id}-{country}-{region.replace(' ', '_')[:20]}"
            _upsert_geo(db, region_id, f"{region} Region", company_id,
                        country=country, parent_id=country_id)
            geo_ids[f"{country}-{region}"] = region_id
            result["regions"] += 1

            for state, cities in states.items():
                state_id = f"{company_id}-{country}-{state}"
                state_name = state  # Could be resolved to full name
                _upsert_geo(db, state_id, state_name, company_id,
                            state=state, country=country, parent_id=region_id)
                geo_ids[f"{country}-{state}"] = state_id
                result["states"] += 1

                for city in cities:
                    city_id = f"{company_id}-{country}-{state}-{city.replace(' ', '_')[:20]}"
                    _upsert_geo(db, city_id, city, company_id,
                                city=city, state=state, country=country, parent_id=state_id)
                    geo_ids[f"{country}-{state}-{city}"] = city_id
                    result["cities"] += 1

    # Link sites to their city geography
    sites_linked = _link_sites_to_geography(db, config_id, geo_ids, addresses)
    result["sites_linked"] = sites_linked

    db.flush()
    logger.info(
        "Geography hierarchy: %d countries, %d regions, %d states, %d cities, %d sites linked (config %d)",
        result["countries"], result["regions"], result["states"], result["cities"],
        result["sites_linked"], config_id,
    )
    return result


def _collect_addresses(db: Session, config_id: int, company_id: str) -> List[Dict]:
    """Collect address data from sites and trading partners."""
    addresses = []

    # From sites
    rows = db.execute(text("""
        SELECT id, name, type, city, state_prov, country, geo_id
        FROM site s
        LEFT JOIN geography g ON g.id = s.geo_id
        WHERE s.config_id = :cfg
    """), {"cfg": config_id}).fetchall()

    for r in rows:
        # Try existing geography first, then site's own address fields
        city = r[3] or None
        state = r[4] or None
        country = r[5] or None

        # If no direct address, try to infer from trading partner
        if not city and not state:
            tp = db.execute(text("""
                SELECT city, state_prov, country FROM trading_partners
                WHERE company_id = :cid AND description ILIKE :pattern
                LIMIT 1
            """), {"cid": company_id, "pattern": f"%{r[1]}%"}).fetchone()
            if tp:
                city, state, country = tp[0], tp[1], tp[2]

        if city or state or country:
            addresses.append({
                "site_id": r[0], "site_name": r[1], "site_type": r[2],
                "city": city, "state": state, "country": country or "US",
            })

    # From trading partners (for any not already covered)
    tp_rows = db.execute(text("""
        SELECT id, description, city, state_prov, country
        FROM trading_partners WHERE company_id = :cid
        AND (city IS NOT NULL OR state_prov IS NOT NULL)
    """), {"cid": company_id}).fetchall()

    existing_cities = {(a["city"], a["state"]) for a in addresses if a["city"]}
    for tp in tp_rows:
        if (tp[2], tp[3]) not in existing_cities and tp[2]:
            addresses.append({
                "site_id": None, "site_name": tp[1], "site_type": "trading_partner",
                "city": tp[2], "state": tp[3], "country": tp[4] or "US",
            })
            existing_cities.add((tp[2], tp[3]))

    return addresses


def _build_hierarchy(addresses: List[Dict]) -> Dict:
    """Group addresses into Country → Region → State → City hierarchy."""
    hierarchy = {}

    for addr in addresses:
        country = (addr.get("country") or "US").upper()
        state = (addr.get("state") or "").upper().strip()
        city = (addr.get("city") or "").strip()

        if not state and not city:
            continue

        # Determine region
        if country == "US":
            region = US_STATE_REGION.get(state, "Other")
        else:
            # For non-US, use state as region if available
            region = state if state else "Other"

        hierarchy.setdefault(country, {}).setdefault(region, {}).setdefault(state or "Unknown", set())
        if city:
            hierarchy[country][region][state or "Unknown"].add(city)

    # Convert sets to sorted lists
    for country in hierarchy:
        for region in hierarchy[country]:
            for state in hierarchy[country][region]:
                hierarchy[country][region][state] = sorted(hierarchy[country][region][state])

    return hierarchy


def _upsert_geo(
    db: Session, geo_id: str, description: str, company_id: str,
    city: str = None, state: str = None, country: str = None, parent_id: str = None,
):
    """Insert or update a geography record."""
    db.execute(text("""
        INSERT INTO geography (id, description, company_id, city, state_prov, country, parent_geo_id, source)
        VALUES (:id, :desc, :cid, :city, :state, :country, :pid, 'hierarchy_builder')
        ON CONFLICT (id) DO UPDATE SET
            description = EXCLUDED.description,
            city = COALESCE(EXCLUDED.city, geography.city),
            state_prov = COALESCE(EXCLUDED.state_prov, geography.state_prov),
            country = COALESCE(EXCLUDED.country, geography.country),
            parent_geo_id = COALESCE(EXCLUDED.parent_geo_id, geography.parent_geo_id)
    """), {
        "id": geo_id, "desc": description, "cid": company_id,
        "city": city, "state": state, "country": country, "pid": parent_id,
    })


def _link_sites_to_geography(
    db: Session, config_id: int, geo_ids: Dict[str, str], addresses: List[Dict],
) -> int:
    """Link sites to their most specific geography node (city level)."""
    linked = 0
    for addr in addresses:
        site_id = addr.get("site_id")
        if not site_id:
            continue

        country = (addr.get("country") or "US").upper()
        state = (addr.get("state") or "").upper().strip()
        city = (addr.get("city") or "").strip()

        # Find most specific geo_id: city → state → country
        geo_id = (
            geo_ids.get(f"{country}-{state}-{city}")
            or geo_ids.get(f"{country}-{state}")
            or geo_ids.get(country)
        )

        if geo_id:
            db.execute(text(
                "UPDATE site SET geo_id = :gid WHERE id = :sid"
            ), {"gid": geo_id, "sid": site_id})
            linked += 1

    return linked

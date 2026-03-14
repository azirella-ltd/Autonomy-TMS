"""
Geocoding Service

Converts addresses to latitude/longitude coordinates using the OpenStreetMap
Nominatim API. Used by the SAP ingestion pipeline to populate Geography
records and as a standalone backfill for existing records missing coordinates.

Also provides Haversine-based distance calculation and geo-derived transport
lead time computation for transportation lanes with geocoded endpoints.

Rate-limited to 1 request/second per Nominatim usage policy.
Uses in-memory deduplication to avoid redundant API calls for repeated addresses.
Supports SAP-style 2-letter country codes (DE, US, etc.) via countrycodes parameter.
"""

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AutonomyPlatform/1.0 (supply-chain-planning)"

# In-memory cache: address key → (lat, lon) or None
_geocode_cache: Dict[str, Optional[Tuple[float, float]]] = {}

# Flag: whether we've loaded the DB cache into memory this process
_db_cache_loaded = False


async def _load_db_cache() -> int:
    """Load all geocode_cache rows into the in-memory cache (once per process)."""
    global _db_cache_loaded
    if _db_cache_loaded:
        return 0

    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as db:
            rows = (await db.execute(text(
                "SELECT city, state, country, postal_code, latitude, longitude "
                "FROM geocode_cache"
            ))).fetchall()

        loaded = 0
        for r in rows:
            key = _cache_key(city=r[0], state=r[1], country=r[2], postal_code=r[3])
            if r[4] is not None and r[5] is not None:
                _geocode_cache[key] = (r[4], r[5])
            else:
                _geocode_cache[key] = None
            loaded += 1

        _db_cache_loaded = True
        logger.info(f"Loaded {loaded} entries from geocode_cache table")
        return loaded
    except Exception as e:
        # Table may not exist yet (pre-migration) — not fatal
        logger.debug(f"Could not load geocode_cache table: {e}")
        _db_cache_loaded = True
        return 0


async def _persist_to_db_cache(
    city: str, state: str, country: str, postal_code: str,
    lat: Optional[float], lon: Optional[float],
) -> None:
    """Persist a geocode result to the DB cache (upsert)."""
    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as db:
            await db.execute(text("""
                INSERT INTO geocode_cache (city, state, country, postal_code, latitude, longitude)
                VALUES (:city, :state, :country, :postal_code, :lat, :lon)
                ON CONFLICT (city, state, country, postal_code)
                DO UPDATE SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
            """), {
                "city": city.strip().lower(),
                "state": state.strip().lower(),
                "country": country.strip().lower(),
                "postal_code": postal_code.strip().lower(),
                "lat": lat, "lon": lon,
            })
            await db.commit()
    except Exception as e:
        logger.debug(f"Could not persist geocode result: {e}")

# ISO 3166-1 alpha-2 codes (SAP commonly uses these)
_ISO_COUNTRY_CODES = {
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BR", "BS", "BT", "BV", "BW", "BY", "BZ",
    "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO",
    "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO",
    "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM",
    "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL", "GM",
    "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM", "HN",
    "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS",
    "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN", "KP",
    "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT",
    "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK", "ML",
    "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX",
    "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR",
    "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM", "PN",
    "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW", "SA",
    "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN",
    "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF", "TG",
    "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ",
    "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI", "VN",
    "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
}


def _cache_key(
    city: str = "", state: str = "", country: str = "",
    postal_code: str = "", street: str = "",
) -> str:
    """Build a normalized cache key from address components."""
    return "|".join(
        s.strip().lower() for s in [street, city, state, country, postal_code]
    )


def _is_country_code(value: str) -> bool:
    """Check if value looks like an ISO 3166-1 alpha-2 country code."""
    return value.strip().upper() in _ISO_COUNTRY_CODES


async def geocode_address(
    *,
    city: str = "",
    state: str = "",
    country: str = "",
    postal_code: str = "",
    street: str = "",
) -> Optional[Tuple[float, float]]:
    """
    Geocode a single address to (latitude, longitude).

    Handles SAP-style 2-letter country codes by using Nominatim's
    countrycodes parameter for better results.
    Returns None if geocoding fails.
    """
    key = _cache_key(city=city, state=state, country=country,
                     postal_code=postal_code, street=street)
    if key in _geocode_cache:
        return _geocode_cache[key]

    # Build structured query params
    parts = {}
    if street and street.strip():
        parts["street"] = street.strip()
    if city and city.strip():
        parts["city"] = city.strip()
    if state and state.strip():
        parts["state"] = state.strip()
    if postal_code and postal_code.strip():
        parts["postalcode"] = postal_code.strip()

    # Handle country: if it's a 2-letter ISO code, use countrycodes param
    country_code = ""
    if country and country.strip():
        c = country.strip()
        if _is_country_code(c):
            country_code = c.lower()
            parts["countrycodes"] = country_code
        else:
            parts["country"] = c

    if not parts or (len(parts) == 1 and "countrycodes" in parts):
        # Only a country code with no other info — geocode to country center
        if country_code:
            parts["q"] = country_code
        else:
            _geocode_cache[key] = None
            return None

    params = {**parts, "format": "json", "limit": "1"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            results = resp.json()

            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                _geocode_cache[key] = (lat, lon)
                return (lat, lon)

            # Fallback: free-form query (only if we have city or postal_code)
            if city or postal_code:
                free_form = ", ".join(
                    v for v in [street, city, state, postal_code, country] if v and v.strip()
                )
                if free_form:
                    await asyncio.sleep(1.0)  # Rate limit
                    fallback_params = {"q": free_form, "format": "json", "limit": "1"}
                    if country_code:
                        fallback_params["countrycodes"] = country_code
                    resp2 = await client.get(
                        NOMINATIM_URL,
                        params=fallback_params,
                        headers={"User-Agent": USER_AGENT},
                    )
                    resp2.raise_for_status()
                    results2 = resp2.json()
                    if results2:
                        result = (float(results2[0]["lat"]), float(results2[0]["lon"]))
                        _geocode_cache[key] = result
                        return result

    except Exception as e:
        logger.warning(f"Geocoding failed for {params}: {e}")

    _geocode_cache[key] = None
    return None


async def geocode_batch(
    records: List[Dict[str, str]],
    progress_callback=None,
) -> List[Optional[Tuple[float, float]]]:
    """
    Geocode a batch of address records with deduplication and rate limiting.

    Duplicate addresses (same city/state/country/postal_code/street) are
    resolved from cache without making additional API calls.

    Each record should have keys: city, state, country, postal_code, street (all optional).
    progress_callback: async fn(index, total, label, status) called per address.
        status is "completed", "failed", "in_progress", or "cached".
    Returns a list of (lat, lon) tuples or None for each record.
    """
    # Load persistent DB cache into memory on first call
    await _load_db_cache()

    results: List[Optional[Tuple[float, float]]] = []
    api_calls = 0
    cache_hits = 0

    def _label(rec: Dict[str, str]) -> str:
        """Build a human-readable address label."""
        parts = [rec.get("city", ""), rec.get("state", ""), rec.get("country", "")]
        return ", ".join(p.strip() for p in parts if p and p.strip()) or rec.get("street", "") or "Unknown"

    for i, rec in enumerate(records):
        key = _cache_key(
            city=rec.get("city", ""),
            state=rec.get("state", ""),
            country=rec.get("country", ""),
            postal_code=rec.get("postal_code", ""),
            street=rec.get("street", ""),
        )

        if key in _geocode_cache:
            results.append(_geocode_cache[key])
            cache_hits += 1
            if progress_callback:
                status = "completed" if _geocode_cache[key] else "failed"
                await progress_callback(i, len(records), _label(rec), status)
            continue

        # Report in_progress before the API call
        if progress_callback:
            await progress_callback(i, len(records), _label(rec), "in_progress")

        # Rate limit only for actual API calls
        if api_calls > 0:
            await asyncio.sleep(1.1)  # Nominatim: max 1 request/second
        api_calls += 1

        coords = await geocode_address(
            city=rec.get("city", ""),
            state=rec.get("state", ""),
            country=rec.get("country", ""),
            postal_code=rec.get("postal_code", ""),
            street=rec.get("street", ""),
        )
        results.append(coords)

        # Persist to DB cache for future runs
        await _persist_to_db_cache(
            city=rec.get("city", ""),
            state=rec.get("state", ""),
            country=rec.get("country", ""),
            postal_code=rec.get("postal_code", ""),
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
        )

        if coords:
            logger.info(f"Geocoded [{i+1}/{len(records)}] {rec.get('city', '')} → {coords}")
        else:
            logger.warning(f"No result [{i+1}/{len(records)}] for {rec}")

        if progress_callback:
            await progress_callback(i, len(records), _label(rec), "completed" if coords else "failed")

    logger.info(
        f"Geocoding complete: {len(records)} records, "
        f"{api_calls} API calls, {cache_hits} cache hits"
    )
    return results


# ============================================================================
# Haversine Distance & Geo-Based Transport Lead Time
# ============================================================================

_EARTH_RADIUS_MILES = 3958.8


def haversine_distance_miles(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Great-circle distance between two points in miles."""
    rlat1, rlon1, rlat2, rlon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


# Trucking model parameters (road miles ≈ 1.3× great-circle for US highways)
_ROAD_FACTOR = 1.3
_AVG_TRUCK_SPEED_MPH = 45
_DRIVING_HOURS_PER_DAY = 10
_OVERHEAD_DAYS = 0.5  # Loading/unloading/dwell


def geo_transport_lead_time(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> Dict[str, Any]:
    """Calculate transport lead time distribution from two geocoded endpoints.

    Uses a trucking model: road_miles / (speed × hours/day) + overhead.
    CV scales with distance: 0.15 base + 0.0001 per mile (longer routes = more variability).
    Returns a lognormal distribution dict suitable for supply_lead_time_dist or
    agent_stochastic_params.distribution.
    """
    gc_miles = haversine_distance_miles(lat1, lon1, lat2, lon2)
    road_miles = gc_miles * _ROAD_FACTOR
    driving_days = road_miles / (_AVG_TRUCK_SPEED_MPH * _DRIVING_HOURS_PER_DAY)
    mean_days = max(round(driving_days + _OVERHEAD_DAYS, 2), 0.5)

    # CV increases with distance: short hauls more predictable than cross-country
    cv = min(0.15 + 0.0001 * road_miles, 0.45)

    stddev = mean_days * cv
    var = stddev ** 2
    mu_log = math.log(mean_days ** 2 / math.sqrt(var + mean_days ** 2))
    sigma_log = math.sqrt(math.log(1 + var / mean_days ** 2))

    return {
        "type": "lognormal",
        "mean_log": round(mu_log, 6),
        "stddev_log": round(sigma_log, 6),
        "mean": round(mean_days, 2),
        "stddev": round(stddev, 2),
        "min": round(max(mean_days * 0.3, 0.5), 2),
        "max": round(mean_days * 2.5, 2),
        "source": "geo_calculated",
        "distance_miles": round(road_miles, 1),
    }


def calculate_geo_lead_times_for_config(db, config_id: int) -> Dict[str, Any]:
    """Calculate and apply geo-based transport lead times for all lanes in a config.

    For each TransportationLane where both endpoints have geocoded Geography records,
    calculates a lognormal lead time distribution based on Haversine distance.

    Updates:
      1. TransportationLane.supply_lead_time_dist — per-lane distribution
      2. TransportationLane.supply_lead_time — deterministic mean (JSON {"value": N, "unit": "day"})
      3. AgentStochasticParam rows for transport_lead_time — site-specific overrides

    Returns summary dict with counts and per-lane details.
    """
    from app.models.supply_chain_config import TransportationLane, Site
    from app.models.sc_entities import Geography
    from app.models.agent_stochastic_param import AgentStochasticParam, TRM_PARAM_MAP

    sites = db.query(Site).filter(Site.config_id == config_id).all()
    site_map = {s.id: s for s in sites}

    # Build site_id → (lat, lon) mapping
    geo_ids = [s.geo_id for s in sites if s.geo_id]
    geos = {}
    if geo_ids:
        for g in db.query(Geography).filter(Geography.id.in_(geo_ids)).all():
            if g.latitude and g.longitude:
                geos[g.id] = (g.latitude, g.longitude)

    site_coords = {}
    for s in sites:
        if s.geo_id and s.geo_id in geos:
            site_coords[s.id] = geos[s.geo_id]

    lanes = db.query(TransportationLane).filter(
        TransportationLane.config_id == config_id,
    ).all()

    updated_lanes = 0
    lane_details = []

    # Get tenant_id from config
    from app.models.supply_chain_config import SupplyChainConfig
    config = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
    if not config:
        return {"updated_lanes": 0, "details": []}
    tenant_id = config.tenant_id

    for lane in lanes:
        src_coords = site_coords.get(lane.from_site_id)
        dst_coords = site_coords.get(lane.to_site_id)
        if not src_coords or not dst_coords:
            continue

        dist = geo_transport_lead_time(
            src_coords[0], src_coords[1], dst_coords[0], dst_coords[1],
        )

        # Update lane distribution
        lane.supply_lead_time_dist = dist
        lane.supply_lead_time = {"value": dist["mean"], "unit": "day"}
        updated_lanes += 1

        src_name = site_map.get(lane.from_site_id)
        dst_name = site_map.get(lane.to_site_id)
        lane_details.append({
            "lane_id": lane.id,
            "source": src_name.name if src_name else str(lane.from_site_id),
            "destination": dst_name.name if dst_name else str(lane.to_site_id),
            "distance_miles": dist["distance_miles"],
            "mean_days": dist["mean"],
        })

    # Create site-specific agent_stochastic_params for transport_lead_time
    # Group lanes by destination site to get weighted average inbound lead time
    site_inbound: Dict[int, List[Dict]] = {}
    for lane in lanes:
        dst = lane.to_site_id
        if dst in site_coords and lane.supply_lead_time_dist:
            site_inbound.setdefault(dst, []).append(lane.supply_lead_time_dist)

    # TRM types that use transport_lead_time
    transport_trms = [
        trm for trm, params in TRM_PARAM_MAP.items()
        if "transport_lead_time" in params
    ]

    stochastic_count = 0
    for site_id, dists_list in site_inbound.items():
        # Average inbound lead time for this site
        avg_mean = sum(d["mean"] for d in dists_list) / len(dists_list)
        avg_cv = sum(d.get("stddev", d["mean"] * 0.2) / d["mean"] for d in dists_list) / len(dists_list)
        site_dist = geo_transport_lead_time(0, 0, 0, 0)  # placeholder
        # Rebuild properly from averaged values
        stddev = avg_mean * avg_cv
        var = stddev ** 2
        mu_log = math.log(avg_mean ** 2 / math.sqrt(var + avg_mean ** 2))
        sigma_log = math.sqrt(math.log(1 + var / avg_mean ** 2))
        site_dist = {
            "type": "lognormal",
            "mean_log": round(mu_log, 6),
            "stddev_log": round(sigma_log, 6),
            "mean": round(avg_mean, 2),
            "stddev": round(stddev, 2),
            "min": round(max(avg_mean * 0.3, 0.5), 2),
            "max": round(avg_mean * 2.5, 2),
            "source": "geo_calculated",
        }

        for trm_type in transport_trms:
            existing = db.query(AgentStochasticParam).filter(
                AgentStochasticParam.config_id == config_id,
                AgentStochasticParam.site_id == site_id,
                AgentStochasticParam.trm_type == trm_type,
                AgentStochasticParam.param_name == "transport_lead_time",
            ).first()

            if existing:
                if existing.source in ("industry_default", "geo_calculated"):
                    existing.distribution = site_dist
                    existing.source = "geo_calculated"
                    existing.is_default = True
                    stochastic_count += 1
            else:
                db.add(AgentStochasticParam(
                    config_id=config_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    trm_type=trm_type,
                    param_name="transport_lead_time",
                    distribution=site_dist,
                    is_default=True,
                    source="geo_calculated",
                ))
                stochastic_count += 1

    db.flush()
    return {
        "updated_lanes": updated_lanes,
        "stochastic_params_created": stochastic_count,
        "details": lane_details,
    }

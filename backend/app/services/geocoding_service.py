"""
Geocoding Service

Converts addresses to latitude/longitude coordinates using the OpenStreetMap
Nominatim API. Used by the SAP ingestion pipeline to populate Geography
records and as a standalone backfill for existing records missing coordinates.

Rate-limited to 1 request/second per Nominatim usage policy.
Uses in-memory deduplication to avoid redundant API calls for repeated addresses.
Supports SAP-style 2-letter country codes (DE, US, etc.) via countrycodes parameter.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AutonomyPlatform/1.0 (supply-chain-planning)"

# In-memory cache: address key → (lat, lon) or None
_geocode_cache: Dict[str, Optional[Tuple[float, float]]] = {}

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

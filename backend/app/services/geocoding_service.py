"""
Geocoding Service

Converts addresses to latitude/longitude coordinates using the OpenStreetMap
Nominatim API. Used by the SAP ingestion pipeline to populate Geography
records and as a standalone backfill for existing records missing coordinates.

Rate-limited to 1 request/second per Nominatim usage policy.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AutonomyPlatform/1.0 (supply-chain-planning)"


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

    Tries structured query first, falls back to free-form if no result.
    Returns None if geocoding fails.
    """
    parts = {
        "street": street,
        "city": city,
        "state": state,
        "country": country,
        "postalcode": postal_code,
    }
    params = {k: v for k, v in parts.items() if v and v.strip()}
    if not params:
        return None

    params["format"] = "json"
    params["limit"] = "1"

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
                return (lat, lon)

            # Fallback: free-form query
            free_form = ", ".join(
                v for v in [street, city, state, postal_code, country] if v and v.strip()
            )
            if free_form:
                await asyncio.sleep(1.0)  # Rate limit
                resp2 = await client.get(
                    NOMINATIM_URL,
                    params={"q": free_form, "format": "json", "limit": "1"},
                    headers={"User-Agent": USER_AGENT},
                )
                resp2.raise_for_status()
                results2 = resp2.json()
                if results2:
                    return (float(results2[0]["lat"]), float(results2[0]["lon"]))

    except Exception as e:
        logger.warning(f"Geocoding failed for {params}: {e}")

    return None


async def geocode_batch(
    records: List[Dict[str, str]],
) -> List[Optional[Tuple[float, float]]]:
    """
    Geocode a batch of address records sequentially (1 req/sec rate limit).

    Each record should have keys: city, state, country, postal_code, street (all optional).
    Returns a list of (lat, lon) tuples or None for each record.
    """
    results: List[Optional[Tuple[float, float]]] = []
    for i, rec in enumerate(records):
        if i > 0:
            await asyncio.sleep(1.1)  # Nominatim: max 1 request/second
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
    return results

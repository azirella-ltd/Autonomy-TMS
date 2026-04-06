"""
Dynamic Geography Hierarchy Resolver — tenant-specific, never hardcoded.

Builds a geo_id → region_name mapping from the tenant's actual geography
table by walking the parent_geo_id chain. Works for any depth:
  - 3+ level (city → state → region → country): groups by region (2nd from top)
  - 2-level (city → region): groups by region (top)
  - 1-level (flat): groups by country
  - No geo: groups by site name

Every mapping is derived from the tenant's data. No STATE_TO_REGION
hardcoded dicts anywhere.
"""

from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _find_region(geo_id: str, geo_data: dict) -> str:
    """Walk parent chain and pick the best grouping level.

    Strategy:
      - chain length 1 (flat): use country, fall back to description
      - chain length 2 (city → region): use the top (region)
      - chain length 3+ (city → state → region → ...): use the second-from-top
        (the "region" level, not the country root)
    """
    visited = set()
    current = geo_id
    chain = []
    while current and current in geo_data and current not in visited:
        visited.add(current)
        chain.append(current)
        parent = geo_data[current].get("parent_geo_id")
        if parent and parent in geo_data:
            current = parent
        else:
            break

    if not chain:
        return "Other"

    if len(chain) == 1:
        # Flat — use country as grouping
        d = geo_data.get(chain[0], {})
        return d.get("country") or d.get("description") or "Other"

    if len(chain) == 2:
        # 2-level — top is the region
        d = geo_data.get(chain[-1], {})
        return d.get("description") or d.get("country") or "Other"

    # 3+ levels — second-from-top is the region (top is country/root)
    region_node = chain[-2]
    d = geo_data.get(region_node, {})
    return d.get("description") or d.get("country") or "Other"


def _build_mapping_from_data(site_rows, geo_data: dict) -> Dict[str, str]:
    """Build geo_id → region_name mapping from loaded data."""
    mapping = {}
    for row in site_rows:
        site_geo_id = str(row[0])
        geo_id = str(row[1]) if row[1] else site_geo_id
        region = _find_region(geo_id, geo_data)
        mapping[site_geo_id] = region
        if row[1]:
            mapping[str(row[1])] = region
    return mapping


def _load_ancestors(execute_fn, geo_data: dict) -> None:
    """Walk parent_geo_id chains until all ancestors are loaded."""
    to_load = {
        g["parent_geo_id"]
        for g in geo_data.values()
        if g["parent_geo_id"] and g["parent_geo_id"] not in geo_data
    }
    depth = 0
    while to_load and depth < 10:
        depth += 1
        parent_rows = execute_fn(
            """
            SELECT id, description, country, state_prov, parent_geo_id
            FROM geography WHERE id = ANY(:ids)
            """,
            {"ids": list(to_load)},
        )
        next_load = set()
        for row in parent_rows:
            gid = str(row[0])
            geo_data[gid] = {
                "description": row[1],
                "country": row[2],
                "state_prov": row[3],
                "parent_geo_id": str(row[4]) if row[4] else None,
            }
            if row[4] and str(row[4]) not in geo_data:
                next_load.add(str(row[4]))
        to_load = next_load


def resolve_geo_regions_sync(db: Session, config_id: int) -> Dict[str, str]:
    """Build geo_id → region_name mapping (sync)."""
    rows = db.execute(
        sql_text("""
            SELECT DISTINCT s.geo_id, g.id, g.description, g.country,
                   g.state_prov, g.parent_geo_id
            FROM site s
            LEFT JOIN geography g ON g.id = s.geo_id
            WHERE s.config_id = :cid AND s.geo_id IS NOT NULL
        """),
        {"cid": config_id},
    ).fetchall()

    if not rows:
        return {}

    geo_data = {}
    for row in rows:
        geo_id = str(row[1]) if row[1] else str(row[0])
        geo_data[geo_id] = {
            "description": row[2],
            "country": row[3],
            "state_prov": row[4],
            "parent_geo_id": str(row[5]) if row[5] else None,
        }

    def _exec(sql, params):
        return db.execute(sql_text(sql), params).fetchall()

    _load_ancestors(_exec, geo_data)
    mapping = _build_mapping_from_data(rows, geo_data)

    logger.debug(
        "Geo resolved config %d: %d ids → %d regions",
        config_id, len(mapping), len(set(mapping.values())),
    )
    return mapping


async def resolve_geo_regions_async_impl(
    db: AsyncSession, config_id: int,
) -> Dict[str, str]:
    """Build geo_id → region_name mapping (async)."""
    result = await db.execute(sql_text("""
        SELECT DISTINCT s.geo_id, g.id, g.description, g.country,
               g.state_prov, g.parent_geo_id
        FROM site s
        LEFT JOIN geography g ON g.id = s.geo_id
        WHERE s.config_id = :cid AND s.geo_id IS NOT NULL
    """), {"cid": config_id})
    site_rows = result.fetchall()

    if not site_rows:
        return {}

    geo_data = {}
    for row in site_rows:
        geo_id = str(row[1]) if row[1] else str(row[0])
        geo_data[geo_id] = {
            "description": row[2],
            "country": row[3],
            "state_prov": row[4],
            "parent_geo_id": str(row[5]) if row[5] else None,
        }

    # Async ancestor loading
    to_load = {
        g["parent_geo_id"]
        for g in geo_data.values()
        if g["parent_geo_id"] and g["parent_geo_id"] not in geo_data
    }
    depth = 0
    while to_load and depth < 10:
        depth += 1
        r = await db.execute(sql_text("""
            SELECT id, description, country, state_prov, parent_geo_id
            FROM geography WHERE id = ANY(:ids)
        """), {"ids": list(to_load)})
        next_load = set()
        for row in r.fetchall():
            gid = str(row[0])
            geo_data[gid] = {
                "description": row[1],
                "country": row[2],
                "state_prov": row[3],
                "parent_geo_id": str(row[4]) if row[4] else None,
            }
            if row[4] and str(row[4]) not in geo_data:
                next_load.add(str(row[4]))
        to_load = next_load

    mapping = _build_mapping_from_data(site_rows, geo_data)

    logger.debug(
        "Geo resolved config %d: %d ids → %d regions",
        config_id, len(mapping), len(set(mapping.values())),
    )
    return mapping

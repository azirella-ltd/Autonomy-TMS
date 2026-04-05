"""External Signal Service — Orchestrates outside-in planning intelligence.

Daily refresh pipeline:
1. For each tenant's active ExternalSignalSource, instantiate the connector
2. Fetch new signals since last refresh
3. Deduplicate against existing signals (signal_key unique constraint)
4. Score relevance using tenant's industry/region/product tags
5. Generate embedding text for RAG injection
6. Persist to external_signals table
7. Update source refresh metadata

RAG integration:
- get_relevant_signals() returns recent, high-relevance signals for Azirella chat
- Signals are formatted as context paragraphs injected into the LLM system prompt
- Tenant-scoped: each tenant only sees signals from their configured sources
"""

import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy import select, and_, or_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.external_signal import (
    ExternalSignal, ExternalSignalSource,
    SIGNAL_CATEGORIES, SOURCE_REGISTRY, SIGNAL_SC_IMPACT,
)
from app.services.external_signal_connectors import (
    get_connector, ExternalSignalData, CONNECTOR_REGISTRY,
)

logger = logging.getLogger(__name__)


class ExternalSignalService:
    """Tenant-scoped orchestrator for external signal intelligence."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # ── Source Management ─────────────────────────────────────────────────

    async def list_sources(self) -> List[dict]:
        """List all configured sources for this tenant."""
        result = await self.db.execute(
            select(ExternalSignalSource)
            .where(ExternalSignalSource.tenant_id == self.tenant_id)
            .order_by(ExternalSignalSource.source_key)
        )
        sources = result.scalars().all()
        return [self._source_to_dict(s) for s in sources]

    async def get_or_create_source(
        self,
        source_key: str,
        config_id: Optional[int] = None,
        source_params: Optional[dict] = None,
        industry_tags: Optional[list] = None,
        region_tags: Optional[list] = None,
        product_tags: Optional[list] = None,
    ) -> ExternalSignalSource:
        """Get or create an external signal source for this tenant."""
        registry = SOURCE_REGISTRY.get(source_key)
        if not registry:
            raise ValueError(f"Unknown source key: {source_key}")

        result = await self.db.execute(
            select(ExternalSignalSource).where(
                ExternalSignalSource.tenant_id == self.tenant_id,
                ExternalSignalSource.source_key == source_key,
                ExternalSignalSource.config_id == config_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update if params provided
            if source_params is not None:
                existing.source_params = source_params
            if industry_tags is not None:
                existing.industry_tags = industry_tags
            if region_tags is not None:
                existing.region_tags = region_tags
            if product_tags is not None:
                existing.product_tags = product_tags
            await self.db.flush()
            return existing

        source = ExternalSignalSource(
            tenant_id=self.tenant_id,
            config_id=config_id,
            source_key=source_key,
            source_name=registry["name"],
            is_active=True,
            source_params=source_params or {},
            industry_tags=industry_tags or [],
            region_tags=region_tags or [],
            product_tags=product_tags or [],
            refresh_cadence=registry.get("refresh_cadence", "daily"),
        )
        self.db.add(source)
        await self.db.flush()
        return source

    async def activate_default_sources(self, config_id: Optional[int] = None) -> List[dict]:
        """Activate default sources for a tenant, auto-configured from the DAG.

        Reads the tenant's supply chain topology to auto-populate:
        - Open-Meteo locations from site coordinates (warehouses, DCs, factories)
        - NWS alert states from site state_prov fields
        - DOT disruption states + major freight route keywords
        - GDELT keywords from tenant industry + supplier countries
        - Google Trends keywords from product family names
        - openFDA product types from product categories

        These are free sources that don't require API keys (or have free keys).
        """
        # ── Read DAG topology ──────────────────────────────────────────────
        dag_info = await self._read_dag_topology(config_id)
        site_locations = dag_info.get("locations", [])
        site_states = dag_info.get("states", [])
        product_families = dag_info.get("product_families", [])
        product_keywords = dag_info.get("product_keywords", [])
        industry_tags = dag_info.get("industry_tags", [])
        region_tags = dag_info.get("region_tags", [])
        supplier_countries = dag_info.get("supplier_countries", [])

        import os

        # ── Build source-specific params from DAG ──────────────────────────
        source_configs = []

        # 1. FRED — always useful, add if key available
        if os.getenv("FRED_API_KEY"):
            source_configs.append(("fred", {
                "industry_tags": industry_tags,
                "region_tags": region_tags,
            }, industry_tags, region_tags, product_families))

        # 2. Open-Meteo — weather at DAG site locations
        if site_locations:
            source_configs.append(("open_meteo", {
                "locations": site_locations,
            }, industry_tags, region_tags, product_families))
        else:
            source_configs.append(("open_meteo", {}, industry_tags, region_tags, product_families))

        # 3. NWS Alerts — severe weather warnings for states where sites are
        if site_states:
            source_configs.append(("nws_alerts", {
                "states": list(set(site_states)),
            }, industry_tags, region_tags, product_families))

        # 4. DOT Disruptions — road closures along freight corridors
        corridors = dag_info.get("corridors", [])
        if site_states or corridors:
            # Include corridor-specific keywords (origin→dest pairs)
            corridor_keywords = []
            for c in corridors[:5]:
                if c.get("origin_state") and c.get("dest_state") and c["origin_state"] != c["dest_state"]:
                    corridor_keywords.append(f"{c['origin_state']} {c['dest_state']} freight")
                if c.get("mode") == "ocean":
                    corridor_keywords.append(f"{c.get('origin', '')} port congestion")
            source_configs.append(("dot_disruptions", {
                "states": list(set(site_states)),
                "route_keywords": dag_info.get("route_keywords", []) + corridor_keywords,
                "corridors": corridors[:10],
            }, industry_tags, region_tags, product_families))

        # 5. GDELT — geopolitical events
        gdelt_keywords = ["supply chain disruption", "port strike", "food safety recall"]
        if supplier_countries:
            for country in supplier_countries[:3]:
                gdelt_keywords.append(f"{country} trade")
        if industry_tags:
            for tag in industry_tags[:2]:
                gdelt_keywords.append(f"{tag.replace('_', ' ')} disruption")
        source_configs.append(("gdelt", {
            "keywords": gdelt_keywords,
            "countries": supplier_countries[:5] if supplier_countries else [],
            "industry_tags": industry_tags,  # For sentiment keyword expansion
        }, industry_tags, region_tags, product_families))

        # 6. EIA — energy prices (if key available)
        if os.getenv("EIA_API_KEY"):
            source_configs.append(("eia", {}, industry_tags, region_tags, product_families))

        # 7. Google Trends — product demand signals
        if product_keywords:
            source_configs.append(("google_trends", {
                "keywords": product_keywords[:10],
            }, industry_tags, region_tags, product_families))

        # 8. Reddit — industry subreddit sentiment (auto-selects subreddits from industry)
        source_configs.append(("reddit_sentiment", {
            "industry_tags": industry_tags,
        }, industry_tags, region_tags, product_families))

        # 9. openFDA — regulatory signals (product-type aware)
        fda_types = ["food"]  # Default for food distribution
        if any("pharma" in t or "drug" in t for t in industry_tags):
            fda_types = ["drug"]
        elif any("device" in t or "medical" in t for t in industry_tags):
            fda_types = ["device"]
        source_configs.append(("openfda", {
            "product_types": fda_types,
            "keywords": ["recall", "warning"] + product_keywords[:3],
        }, industry_tags, region_tags, product_families))

        # ── Create sources ─────────────────────────────────────────────────
        created = []
        for source_key, params, ind_tags, reg_tags, prod_tags in source_configs:
            source = await self.get_or_create_source(
                source_key,
                config_id=config_id,
                source_params=params,
                industry_tags=ind_tags,
                region_tags=reg_tags,
                product_tags=prod_tags,
            )
            created.append(self._source_to_dict(source))

        await self.db.commit()
        logger.info(
            f"Activated {len(created)} default sources for tenant {self.tenant_id} "
            f"(config {config_id}): {[c['source_key'] for c in created]}"
        )
        return created

    async def _read_dag_topology(self, config_id: Optional[int] = None) -> dict:
        """Extract location, product, and industry context from the DAG.

        Used to auto-configure external signal sources with tenant-specific
        parameters (site coordinates for weather, state codes for NWS/DOT, etc.).
        """
        result = {
            "locations": [],
            "states": [],
            "product_families": [],
            "product_keywords": [],
            "industry_tags": [],
            "region_tags": [],
            "supplier_countries": [],
            "route_keywords": [],
        }

        if not config_id:
            # Try to find the tenant's active config
            from sqlalchemy import text as _t
            cfg_result = await self.db.execute(
                _t("SELECT id FROM supply_chain_configs WHERE tenant_id = :tid AND is_active = true ORDER BY id LIMIT 1"),
                {"tid": self.tenant_id},
            )
            row = cfg_result.fetchone()
            if row:
                config_id = row[0]
            else:
                return result

        try:
            from sqlalchemy import text as _t

            # ── Sites: extract coordinates, states, regions ──────────────
            site_rows = await self.db.execute(
                _t("""
                    SELECT name, type, latitude, longitude, attributes
                    FROM site
                    WHERE config_id = :cid AND latitude IS NOT NULL AND longitude IS NOT NULL
                """),
                {"cid": config_id},
            )
            for row in site_rows.fetchall():
                name, site_type, lat, lon, attrs = row
                if lat and lon:
                    region = "unknown"
                    state = None
                    # Extract state from attributes JSON if available
                    if isinstance(attrs, dict):
                        state = attrs.get("state") or attrs.get("state_prov")
                        region = attrs.get("region", "unknown")

                    # Infer state from coordinates if not in attributes
                    if not state:
                        state = self._state_from_coords(lat, lon)

                    result["locations"].append({
                        "lat": round(lat, 4),
                        "lon": round(lon, 4),
                        "name": name,
                        "region": region,
                    })
                    if state:
                        result["states"].append(state)
                        # Infer region tags from states
                        region_tag = self._region_from_state(state)
                        if region_tag:
                            result["region_tags"].append(region_tag)

            result["states"] = list(set(result["states"]))
            result["region_tags"] = list(set(result["region_tags"]))

            # ── Major highway routes from state coverage ─────────────────
            state_routes = {
                "WA": ["I-5", "I-90", "I-82"],
                "OR": ["I-5", "I-84", "I-82"],
                "CA": ["I-5", "I-10", "I-15", "I-80", "I-405"],
                "AZ": ["I-10", "I-17", "I-40"],
                "UT": ["I-15", "I-80", "I-70"],
                "TX": ["I-10", "I-35", "I-45"],
                "IL": ["I-90", "I-55", "I-94"],
                "PA": ["I-76", "I-80", "I-95"],
                "NY": ["I-87", "I-95", "I-90"],
                "GA": ["I-75", "I-85", "I-20"],
            }
            for state in result["states"]:
                routes = state_routes.get(state, [])
                result["route_keywords"].extend(routes)
            result["route_keywords"] = list(set(result["route_keywords"]))

            # ── Products: extract family names and keywords ──────────────
            prod_rows = await self.db.execute(
                _t("""
                    SELECT DISTINCT description, product_group_id
                    FROM product
                    WHERE config_id = :cid
                    LIMIT 100
                """),
                {"cid": config_id},
            )
            family_set = set()
            keyword_set = set()
            for row in prod_rows.fetchall():
                desc, group_id = row
                if group_id:
                    family_set.add(str(group_id))
                if desc:
                    # Extract meaningful keywords from product descriptions
                    words = desc.lower().split()
                    for w in words:
                        if len(w) > 3 and w not in {"case", "each", "pack", "unit", "premium", "grade"}:
                            keyword_set.add(w)

            result["product_families"] = list(family_set)[:20]
            result["product_keywords"] = list(keyword_set)[:15]

            # ── Transportation Lanes: corridors, distances, modes ────────
            # Lanes define the actual freight corridors we need to monitor
            # for road closures, weather, and persistent disruptions.
            lane_rows = await self.db.execute(
                _t("""
                    SELECT
                        tl.id,
                        tl.capacity,
                        tl.supply_lead_time,
                        fs.name   AS from_site_name,
                        fs.latitude  AS from_lat,
                        fs.longitude AS from_lon,
                        fs.attributes AS from_attrs,
                        ts.name   AS to_site_name,
                        ts.latitude  AS to_lat,
                        ts.longitude AS to_lon,
                        ts.attributes AS to_attrs,
                        fp.description AS from_partner_name,
                        fp.latitude    AS from_partner_lat,
                        fp.longitude   AS from_partner_lon,
                        fp.state_prov  AS from_partner_state,
                        fp.country     AS from_partner_country,
                        tp.description AS to_partner_name,
                        tp.latitude    AS to_partner_lat,
                        tp.longitude   AS to_partner_lon,
                        tp.state_prov  AS to_partner_state,
                        tp.country     AS to_partner_country
                    FROM transportation_lane tl
                    LEFT JOIN site fs ON fs.id = tl.from_site_id
                    LEFT JOIN site ts ON ts.id = tl.to_site_id
                    LEFT JOIN trading_partners fp ON fp._id = tl.from_partner_id
                    LEFT JOIN trading_partners tp ON tp._id = tl.to_partner_id
                    WHERE tl.config_id = :cid
                """),
                {"cid": config_id},
            )
            corridors = []
            for row in lane_rows.fetchall():
                # Determine origin
                origin_name = row[3] or row[11] or "Unknown"
                origin_lat = row[4] or row[12]
                origin_lon = row[5] or row[13]
                origin_state = None
                if row[6] and isinstance(row[6], dict):
                    origin_state = row[6].get("state") or row[6].get("state_prov")
                if not origin_state and row[14]:
                    origin_state = row[14]
                if not origin_state and origin_lat and origin_lon:
                    origin_state = self._state_from_coords(origin_lat, origin_lon)

                # Determine destination
                dest_name = row[7] or row[16] or "Unknown"
                dest_lat = row[8] or row[17]
                dest_lon = row[9] or row[18]
                dest_state = None
                if row[10] and isinstance(row[10], dict):
                    dest_state = row[10].get("state") or row[10].get("state_prov")
                if not dest_state and row[19]:
                    dest_state = row[19]
                if not dest_state and dest_lat and dest_lon:
                    dest_state = self._state_from_coords(dest_lat, dest_lon)

                # Add states from lane endpoints
                if origin_state:
                    result["states"].append(origin_state)
                if dest_state:
                    result["states"].append(dest_state)

                # Add partner countries for international supply
                partner_country = row[15] or row[20]
                if partner_country and partner_country not in ("US", "USA", "United States"):
                    result["supplier_countries"].append(partner_country)

                # Infer transport mode from lead time and capacity
                supply_lt = row[2]
                capacity = row[1] or 0
                lt_days = 1
                if isinstance(supply_lt, dict):
                    lt_days = supply_lt.get("mean", supply_lt.get("min", 1))
                elif isinstance(supply_lt, (int, float)):
                    lt_days = supply_lt

                # Heuristic mode inference:
                # Short lead time + high capacity → truck (ground)
                # Long lead time + any capacity → rail or ocean
                # Very long lead time + international → ocean/air
                mode = "truck"
                if lt_days > 14 and partner_country and partner_country not in ("US", "USA"):
                    mode = "ocean"
                elif lt_days > 7:
                    mode = "rail_or_intermodal"

                corridor = {
                    "origin": origin_name,
                    "destination": dest_name,
                    "origin_state": origin_state,
                    "dest_state": dest_state,
                    "mode": mode,
                    "lead_time_days": lt_days,
                    "capacity": capacity,
                }
                if origin_lat and origin_lon:
                    corridor["origin_lat"] = round(origin_lat, 4)
                    corridor["origin_lon"] = round(origin_lon, 4)
                if dest_lat and dest_lon:
                    corridor["dest_lat"] = round(dest_lat, 4)
                    corridor["dest_lon"] = round(dest_lon, 4)

                corridors.append(corridor)

            result["corridors"] = corridors

            # Add midpoint locations for weather monitoring along corridors
            for c in corridors:
                if all(k in c for k in ("origin_lat", "origin_lon", "dest_lat", "dest_lon")):
                    mid_lat = (c["origin_lat"] + c["dest_lat"]) / 2
                    mid_lon = (c["origin_lon"] + c["dest_lon"]) / 2
                    result["locations"].append({
                        "lat": round(mid_lat, 4),
                        "lon": round(mid_lon, 4),
                        "name": f"{c['origin']}→{c['destination']} midpoint",
                        "region": c.get("origin_state", "unknown"),
                    })

            # Deduplicate states after adding lane-derived states
            result["states"] = list(set(result["states"]))

            # ── Trading partners: supplier countries ─────────────────────
            try:
                tp_rows = await self.db.execute(
                    _t("""
                        SELECT DISTINCT country
                        FROM trading_partners
                        WHERE country IS NOT NULL AND country != ''
                        LIMIT 20
                    """),
                )
                for row in tp_rows.fetchall():
                    if row[0]:
                        result["supplier_countries"].append(row[0])
            except Exception:
                try:
                    await self.db.rollback()
                except Exception:
                    pass

            # ── Infer industry tags from product families ────────────────
            all_descs = " ".join(result["product_keywords"]).lower()
            if any(w in all_descs for w in ["chicken", "beef", "pork", "seafood", "protein", "meat"]):
                result["industry_tags"].append("food_distribution")
                result["industry_tags"].append("protein")
            if any(w in all_descs for w in ["dairy", "cheese", "yogurt", "butter", "cream"]):
                result["industry_tags"].append("dairy")
            if any(w in all_descs for w in ["frozen", "ice cream", "gelato"]):
                result["industry_tags"].append("frozen_foods")
            if any(w in all_descs for w in ["beverage", "juice", "coffee", "tea"]):
                result["industry_tags"].append("beverage")
            if not result["industry_tags"]:
                result["industry_tags"].append("manufacturing")

            result["industry_tags"] = list(set(result["industry_tags"]))

        except Exception as e:
            logger.warning(f"DAG topology read failed (non-fatal): {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

        return result

    @staticmethod
    def _state_from_coords(lat: float, lon: float) -> Optional[str]:
        """Approximate US state from lat/lon (rough bounding boxes for major states)."""
        # Simplified state inference — covers the most common US logistics states
        if 46.0 <= lat <= 49.0 and -125.0 <= lon <= -117.0:
            return "WA"
        if 42.0 <= lat <= 46.3 and -124.6 <= lon <= -116.5:
            return "OR"
        if 32.5 <= lat <= 42.0 and -124.5 <= lon <= -114.1:
            return "CA"
        if 31.3 <= lat <= 37.0 and -114.8 <= lon <= -109.0:
            return "AZ"
        if 37.0 <= lat <= 42.0 and -114.1 <= lon <= -109.0:
            return "UT"
        if 25.8 <= lat <= 36.5 and -106.6 <= lon <= -93.5:
            return "TX"
        if 36.0 <= lat <= 42.5 and -91.5 <= lon <= -87.5:
            return "IL"
        if 39.7 <= lat <= 42.3 and -80.6 <= lon <= -74.7:
            return "PA"
        if 40.5 <= lat <= 45.0 and -79.8 <= lon <= -71.9:
            return "NY"
        if 30.4 <= lat <= 35.0 and -85.6 <= lon <= -80.8:
            return "GA"
        if 44.0 <= lat <= 47.5 and -97.2 <= lon <= -89.5:
            return "MN"
        return None

    @staticmethod
    def _region_from_state(state: str) -> Optional[str]:
        """Map state code to supply chain planning region."""
        REGION_MAP = {
            "WA": "us_northwest", "OR": "us_northwest", "ID": "us_northwest",
            "CA": "us_west", "NV": "us_west", "AZ": "us_southwest", "UT": "us_west",
            "TX": "us_south", "OK": "us_south", "LA": "us_south", "AR": "us_south",
            "IL": "us_midwest", "IN": "us_midwest", "OH": "us_midwest", "MI": "us_midwest",
            "MN": "us_midwest", "WI": "us_midwest", "IA": "us_midwest",
            "NY": "us_northeast", "PA": "us_northeast", "NJ": "us_northeast",
            "GA": "us_southeast", "FL": "us_southeast", "NC": "us_southeast", "SC": "us_southeast",
        }
        return REGION_MAP.get(state)

    async def toggle_source(self, source_id: int, is_active: bool) -> dict:
        """Enable or disable a source."""
        result = await self.db.execute(
            select(ExternalSignalSource).where(
                ExternalSignalSource.id == source_id,
                ExternalSignalSource.tenant_id == self.tenant_id,
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source {source_id} not found for tenant {self.tenant_id}")

        source.is_active = is_active
        await self.db.commit()
        return self._source_to_dict(source)

    # ── Signal Collection ─────────────────────────────────────────────────

    async def _is_frozen(self) -> bool:
        """Return True if this tenant is in frozen/snapshot mode (no live refresh)."""
        from sqlalchemy import text as _sqt
        mode_row = await self.db.execute(
            _sqt("SELECT time_mode, external_data_mode FROM tenants WHERE id = :tid"),
            {"tid": self.tenant_id},
        )
        row = mode_row.fetchone()
        if row is None:
            return False
        return row[0] == "frozen" or row[1] == "snapshot"

    async def refresh_source(self, source_id: int) -> dict:
        """Refresh signals from a single source.

        Frozen tenants: NOP. Their signals are historical playback data.
        """
        if await self._is_frozen():
            return {"new_signals": 0, "skipped": True, "reason": "tenant in frozen/snapshot mode"}

        result = await self.db.execute(
            select(ExternalSignalSource).where(
                ExternalSignalSource.id == source_id,
                ExternalSignalSource.tenant_id == self.tenant_id,
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source {source_id} not found")

        return await self._collect_from_source(source)

    async def refresh_all_sources(self) -> dict:
        """Refresh all active sources for this tenant. Called by daily scheduler.

        Frozen tenants: NOP. Their signals are historical playback data.
        """
        if await self._is_frozen():
            return {
                "sources_processed": 0,
                "signals_collected": 0,
                "errors": 0,
                "skipped": True,
                "reason": "tenant in frozen/snapshot mode",
            }

        result = await self.db.execute(
            select(ExternalSignalSource).where(
                ExternalSignalSource.tenant_id == self.tenant_id,
                ExternalSignalSource.is_active == True,
            )
        )
        sources = result.scalars().all()

        stats = {"sources_processed": 0, "signals_collected": 0, "errors": 0}
        for source in sources:
            try:
                result = await self._collect_from_source(source)
                stats["sources_processed"] += 1
                stats["signals_collected"] += result.get("new_signals", 0)
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Source {source.source_key} refresh failed: {e}")

        return stats

    async def _collect_from_source(self, source: ExternalSignalSource) -> dict:
        """Fetch and persist signals from a single source."""
        connector = get_connector(source.source_key)
        if not connector:
            source.last_refresh_status = "error"
            source.last_refresh_error = f"No connector for {source.source_key}"
            await self.db.flush()
            return {"new_signals": 0, "error": source.last_refresh_error}

        since = None
        if source.last_refresh_at:
            since = source.last_refresh_at.date()

        try:
            raw_signals = await connector.fetch_signals(
                params=source.source_params or {},
                since_date=since,
            )
        except Exception as e:
            source.last_refresh_status = "error"
            source.last_refresh_error = str(e)[:500]
            source.last_refresh_at = datetime.utcnow()
            await self.db.flush()
            return {"new_signals": 0, "error": str(e)}

        # Persist signals with dedup
        new_count = 0
        for sig_data in raw_signals:
            try:
                # Adjust relevance based on tenant tags
                adjusted = self._adjust_relevance(sig_data, source)
                signal = await self._upsert_signal(adjusted, source)
                if signal:
                    new_count += 1
            except Exception as e:
                logger.warning(f"Failed to persist signal {sig_data.signal_key}: {e}")

        source.last_refresh_at = datetime.utcnow()
        source.last_refresh_status = "success"
        source.last_refresh_error = None
        source.signals_collected = (source.signals_collected or 0) + new_count
        await self.db.commit()

        logger.info(
            f"Source {source.source_key} (tenant {self.tenant_id}): "
            f"{new_count} new signals from {len(raw_signals)} fetched"
        )
        return {"new_signals": new_count, "total_fetched": len(raw_signals)}

    def _adjust_relevance(self, sig: ExternalSignalData, source: ExternalSignalSource) -> ExternalSignalData:
        """Boost or dampen relevance based on tenant's industry/region/product tags."""
        boost = 0.0

        # Check product tag overlap
        if source.product_tags and sig.affected_product_tags:
            overlap = set(source.product_tags) & set(sig.affected_product_tags)
            if overlap:
                boost += 0.15

        # Check region tag overlap
        if source.region_tags and sig.affected_region_tags:
            overlap = set(source.region_tags) & set(sig.affected_region_tags)
            if overlap:
                boost += 0.15

        # Check industry tag overlap
        if source.industry_tags:
            industry_set = set(source.industry_tags)
            # Some heuristic matching
            if "food" in industry_set or "food_distribution" in industry_set:
                if sig.signal_type in ("regulatory_recall", "cpi_change", "severe_weather"):
                    boost += 0.1
            if "manufacturing" in industry_set:
                if sig.signal_type in ("oil_price_spike", "commodity_price_change", "manufacturing_cost_change"):
                    boost += 0.1

        sig.relevance_score = min(sig.relevance_score + boost, 1.0)
        return sig

    async def _upsert_signal(self, sig: ExternalSignalData, source: ExternalSignalSource) -> Optional[ExternalSignal]:
        """Insert signal if not exists (dedup by signal_key)."""
        # Check for duplicate
        existing = await self.db.execute(
            select(ExternalSignal.id).where(
                ExternalSignal.tenant_id == self.tenant_id,
                ExternalSignal.signal_key == sig.signal_key,
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Build embedding text for RAG
        embedding_text = (
            f"[{sig.category.upper()}] {sig.title}. "
            f"{sig.summary} "
            f"Date: {sig.signal_date.isoformat()}. "
            f"SC Impact: {', '.join(sig.affected_trm_types) if sig.affected_trm_types else 'general'}. "
            f"Planning layer: {sig.planning_layer or 'tactical'}."
        )

        signal = ExternalSignal(
            tenant_id=self.tenant_id,
            config_id=source.config_id,
            source_id=source.id,
            source_key=sig.source_key,
            category=sig.category,
            signal_type=sig.signal_type,
            signal_key=sig.signal_key,
            title=sig.title[:500],
            summary=sig.summary,
            signal_date=sig.signal_date,
            raw_value=sig.raw_value,
            raw_unit=sig.raw_unit,
            change_pct=sig.change_pct,
            change_direction=sig.change_direction,
            reference_period=sig.reference_period,
            previous_value=sig.previous_value,
            relevance_score=sig.relevance_score,
            urgency_score=sig.urgency_score,
            magnitude_score=sig.magnitude_score,
            affected_trm_types=sig.affected_trm_types,
            planning_layer=sig.planning_layer,
            affected_product_tags=sig.affected_product_tags,
            affected_region_tags=sig.affected_region_tags,
            embedding_text=embedding_text,
            is_embedded=False,
            expires_at=sig.expires_at,
            is_active=True,
        )
        self.db.add(signal)
        await self.db.flush()
        return signal

    # ── RAG Context Retrieval ─────────────────────────────────────────────

    async def get_relevant_signals(
        self,
        categories: Optional[List[str]] = None,
        min_relevance: float = 0.3,
        max_age_days: int = 14,
        limit: int = 15,
    ) -> List[dict]:
        """Get recent, relevant signals for RAG injection into Azirella chat context.

        Returns signals formatted for LLM consumption, sorted by relevance × recency.

        Virtual clock semantics:
        - Live tenants: window is [real_today - max_age_days, real_today]
        - Frozen tenants: window is [virtual_today - max_age_days, virtual_today]
          This is the playback mode — a demo frozen at 2025-11-20 will see
          exactly the external signals that were captured around Nov 2025,
          replaying the market context that existed at the reference date.

        See docs/internal/VIRTUAL_CLOCK_ARCHITECTURE.md
        """
        from app.core.clock import tenant_today as _tenant_today

        tenant_ref = await _tenant_today(self.tenant_id, self.db)
        cutoff = tenant_ref - timedelta(days=max_age_days)
        # Expiry check uses real wall-clock time (a storm that expired in
        # reality shouldn't magically be "active" in a frozen demo).
        now = datetime.utcnow()
        conditions = [
            ExternalSignal.tenant_id == self.tenant_id,
            ExternalSignal.is_active == True,
            ExternalSignal.signal_date >= cutoff,
            ExternalSignal.signal_date <= tenant_ref,  # Never show "future" signals to frozen tenants
            ExternalSignal.relevance_score >= min_relevance,
            # Exclude expired signals — yesterday's storm is not relevant for planning
            or_(
                ExternalSignal.expires_at == None,
                ExternalSignal.expires_at > now,
            ),
        ]
        if categories:
            conditions.append(ExternalSignal.category.in_(categories))

        result = await self.db.execute(
            select(ExternalSignal)
            .where(and_(*conditions))
            .order_by(
                ExternalSignal.relevance_score.desc(),
                ExternalSignal.signal_date.desc(),
            )
            .limit(limit)
        )
        signals = result.scalars().all()
        return [self._signal_to_dict(s) for s in signals]

    async def get_signals_for_chat_context(
        self,
        max_signals: int = 10,
        max_age_days: int = 7,
    ) -> str:
        """Generate a formatted context block for Azirella's system prompt.

        Returns a markdown-like text block summarizing the most relevant
        external signals for the tenant.
        """
        signals = await self.get_relevant_signals(
            min_relevance=0.4,
            max_age_days=max_age_days,
            limit=max_signals,
        )

        if not signals:
            return ""

        lines = ["## External Market Intelligence (Outside-In Signals)", ""]

        # Group by category
        by_category: Dict[str, list] = {}
        for sig in signals:
            cat = sig["category"]
            by_category.setdefault(cat, []).append(sig)

        category_labels = {
            "economic": "Economic Indicators",
            "weather": "Weather & Climate",
            "energy": "Energy Markets",
            "geopolitical": "Geopolitical Events",
            "sentiment": "Consumer Sentiment",
            "regulatory": "Regulatory & Compliance",
            "commodity": "Commodity Markets",
            "trade": "Trade & Logistics",
        }

        for cat, cat_signals in by_category.items():
            lines.append(f"### {category_labels.get(cat, cat.title())}")
            for sig in cat_signals[:3]:
                date_str = sig["signal_date"]
                direction = ""
                if sig.get("change_direction") and sig["change_direction"] != "stable":
                    arrow = "↑" if sig["change_direction"] == "up" else "↓"
                    direction = f" {arrow}{abs(sig.get('change_pct', 0)):.1f}%"
                lines.append(f"- **{sig['title']}** ({date_str}){direction}")
                lines.append(f"  {sig['summary']}")
            lines.append("")

        return "\n".join(lines)

    # ── Signal Querying ───────────────────────────────────────────────────

    async def list_signals(
        self,
        category: Optional[str] = None,
        source_key: Optional[str] = None,
        since: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List signals with filtering and pagination."""
        conditions = [
            ExternalSignal.tenant_id == self.tenant_id,
            ExternalSignal.is_active == True,
        ]
        if category:
            conditions.append(ExternalSignal.category == category)
        if source_key:
            conditions.append(ExternalSignal.source_key == source_key)
        if since:
            conditions.append(ExternalSignal.signal_date >= since)

        # Count
        count_q = select(func.count()).select_from(ExternalSignal).where(and_(*conditions))
        total = (await self.db.execute(count_q)).scalar_one()

        # Fetch
        result = await self.db.execute(
            select(ExternalSignal)
            .where(and_(*conditions))
            .order_by(ExternalSignal.signal_date.desc(), ExternalSignal.relevance_score.desc())
            .limit(limit)
            .offset(offset)
        )
        signals = result.scalars().all()

        return {
            "signals": [self._signal_to_dict(s) for s in signals],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_dashboard_stats(self) -> dict:
        """Dashboard summary statistics."""
        # Sources
        src_result = await self.db.execute(
            select(
                ExternalSignalSource.source_key,
                ExternalSignalSource.is_active,
                ExternalSignalSource.last_refresh_status,
                ExternalSignalSource.signals_collected,
                ExternalSignalSource.last_refresh_at,
            ).where(ExternalSignalSource.tenant_id == self.tenant_id)
        )
        sources = src_result.all()

        # Signals by category (last 30 days)
        cutoff = date.today() - timedelta(days=30)
        cat_result = await self.db.execute(
            select(ExternalSignal.category, func.count())
            .where(
                ExternalSignal.tenant_id == self.tenant_id,
                ExternalSignal.signal_date >= cutoff,
            )
            .group_by(ExternalSignal.category)
        )
        by_category = dict(cat_result.all())

        # High-relevance count
        high_rel = await self.db.execute(
            select(func.count())
            .select_from(ExternalSignal)
            .where(
                ExternalSignal.tenant_id == self.tenant_id,
                ExternalSignal.signal_date >= cutoff,
                ExternalSignal.relevance_score >= 0.6,
            )
        )

        return {
            "sources": [
                {
                    "source_key": s[0],
                    "is_active": s[1],
                    "last_status": s[2],
                    "signals_collected": s[3] or 0,
                    "last_refresh": s[4].isoformat() if s[4] else None,
                }
                for s in sources
            ],
            "signals_by_category": by_category,
            "total_signals_30d": sum(by_category.values()),
            "high_relevance_signals": high_rel.scalar_one(),
            "available_sources": list(SOURCE_REGISTRY.keys()),
        }

    async def cleanup_expired(self) -> int:
        """Deactivate expired signals.

        Frozen tenants: NOP. Their signals are historical playback data; the
        `expires_at` column reflects real-time expiry which is irrelevant to a
        tenant replaying Nov 2025 market context in Apr 2026.
        """
        from sqlalchemy import text as _sqt
        mode_row = await self.db.execute(
            _sqt("SELECT time_mode, external_data_mode FROM tenants WHERE id = :tid"),
            {"tid": self.tenant_id},
        )
        row = mode_row.fetchone()
        if row and (row[0] == "frozen" or row[1] == "snapshot"):
            return 0

        result = await self.db.execute(
            update(ExternalSignal)
            .where(
                ExternalSignal.tenant_id == self.tenant_id,
                ExternalSignal.expires_at < datetime.utcnow(),
                ExternalSignal.is_active == True,
            )
            .values(is_active=False)
        )
        await self.db.commit()
        return result.rowcount

    # ── Serialization ─────────────────────────────────────────────────────

    def _signal_to_dict(self, sig: ExternalSignal) -> dict:
        return {
            "id": sig.id,
            "source_key": sig.source_key,
            "category": sig.category,
            "signal_type": sig.signal_type,
            "title": sig.title,
            "summary": sig.summary,
            "signal_date": sig.signal_date.isoformat() if sig.signal_date else None,
            "raw_value": sig.raw_value,
            "raw_unit": sig.raw_unit,
            "change_pct": sig.change_pct,
            "change_direction": sig.change_direction,
            "relevance_score": sig.relevance_score,
            "urgency_score": sig.urgency_score,
            "magnitude_score": sig.magnitude_score,
            "affected_trm_types": sig.affected_trm_types,
            "planning_layer": sig.planning_layer,
            "created_at": sig.created_at.isoformat() if sig.created_at else None,
        }

    def _source_to_dict(self, src: ExternalSignalSource) -> dict:
        return {
            "id": src.id,
            "source_key": src.source_key,
            "source_name": src.source_name,
            "is_active": src.is_active,
            "source_params": src.source_params,
            "industry_tags": src.industry_tags,
            "region_tags": src.region_tags,
            "product_tags": src.product_tags,
            "refresh_cadence": src.refresh_cadence,
            "last_refresh_at": src.last_refresh_at.isoformat() if src.last_refresh_at else None,
            "last_refresh_status": src.last_refresh_status,
            "signals_collected": src.signals_collected or 0,
            "available_params": SOURCE_REGISTRY.get(src.source_key, {}),
        }


# ── Standalone refresh for scheduler (sync wrapper) ──────────────────────────

async def refresh_all_tenants(db: AsyncSession) -> dict:
    """Refresh all active sources across all tenants. Called by APScheduler daily job.

    Virtual clock semantics:
    - Live tenants (production + live demos): call external APIs for fresh data
    - Frozen tenants (SAP Demo, etc.): SKIP refresh entirely — they replay the
      historical signals that were already captured at their virtual reference
      date. Calling live APIs would pollute their snapshot with current data.

    See docs/internal/VIRTUAL_CLOCK_ARCHITECTURE.md
    """
    from sqlalchemy import distinct, text as _sqt

    result = await db.execute(
        select(distinct(ExternalSignalSource.tenant_id)).where(
            ExternalSignalSource.is_active == True
        )
    )
    tenant_ids = [row[0] for row in result.all()]

    # Resolve each tenant's time_mode so we can skip frozen ones up-front
    if tenant_ids:
        mode_rows = await db.execute(
            _sqt(
                "SELECT id, time_mode, external_data_mode, virtual_today "
                "FROM tenants WHERE id = ANY(:ids)"
            ),
            {"ids": tenant_ids},
        )
        tenant_modes = {row[0]: (row[1], row[2], row[3]) for row in mode_rows.all()}
    else:
        tenant_modes = {}

    total_stats = {
        "tenants_processed": 0,
        "tenants_skipped_frozen": 0,
        "signals_collected": 0,
        "errors": 0,
    }

    for tid in tenant_ids:
        mode_info = tenant_modes.get(tid, ("live", "live", None))
        time_mode, ext_mode, virt_today = mode_info

        # Skip frozen tenants — they play back from signal history, never refresh live
        if time_mode == "frozen" or ext_mode == "snapshot":
            logger.info(
                "External signal refresh: skipping tenant %d "
                "(time_mode=%s, external_data_mode=%s, virtual_today=%s)",
                tid, time_mode, ext_mode, virt_today,
            )
            total_stats["tenants_skipped_frozen"] += 1
            continue

        try:
            service = ExternalSignalService(db, tid)

            # Clean up expired signals FIRST — yesterday's storm is not relevant
            expired_count = await service.cleanup_expired()
            if expired_count:
                logger.info(f"Tenant {tid}: deactivated {expired_count} expired signals")

            stats = await service.refresh_all_sources()
            total_stats["tenants_processed"] += 1
            total_stats["signals_collected"] += stats.get("signals_collected", 0)
            total_stats["errors"] += stats.get("errors", 0)
        except Exception as e:
            total_stats["errors"] += 1
            logger.error(f"Tenant {tid} external signal refresh failed: {e}")

    logger.info(
        f"External signal daily refresh: {total_stats['tenants_processed']} tenants refreshed, "
        f"{total_stats['tenants_skipped_frozen']} frozen tenants skipped, "
        f"{total_stats['signals_collected']} signals, {total_stats['errors']} errors"
    )
    return total_stats

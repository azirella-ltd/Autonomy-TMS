"""
SC Config RAG Indexer — Auto-generates knowledge base documents from supply chain configs.

When a supply chain configuration is created or updated, this service generates
natural-language documents describing the network topology, sites, lanes, products,
and demand patterns, then embeds them into the tenant's knowledge base for RAG retrieval.

The indexer requires two database sessions:
  - main_db: Sync session for the main database (supply_chain_configs, sites, etc.)
  - kb_db: Async session for the knowledge base database (KBDocument, KBChunk)

Usage:
    from app.services.sc_config_indexer import ScConfigIndexer
    indexer = ScConfigIndexer(kb_db=kb_session, tenant_id=tenant_id)
    await indexer.index_config(config_id)
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from app.models.supply_chain_config import (
    SupplyChainConfig,
    TransportationLane,
    MarketDemand,
    Market,
    Site,
)
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

SC_CONFIG_CATEGORY = "supply_chain_config"


def _config_tag(config_id: int) -> str:
    return f"config_id:{config_id}"


def _lead_time_str(lt_json) -> str:
    """Format a lead time JSON field into a readable string."""
    if not lt_json:
        return "unknown"
    if isinstance(lt_json, dict):
        lt_type = lt_json.get("type", "deterministic")
        if lt_type == "deterministic":
            return f"{lt_json.get('value', '?')} days"
        return f"{lt_type}(mean={lt_json.get('mean', lt_json.get('value', '?'))})"
    return str(lt_json)


class ScConfigIndexer:
    """Generates and indexes supply chain config documents into the tenant knowledge base."""

    def __init__(self, kb_db: AsyncSession, tenant_id: int):
        self.kb_db = kb_db
        self.tenant_id = tenant_id
        self.kb = KnowledgeBaseService(db=kb_db, tenant_id=tenant_id)

    async def index_config(self, config_id: int, uploaded_by: Optional[int] = None) -> dict:
        """Index a supply chain config into the knowledge base.

        Loads config from the main database (sync), generates a natural-language
        document, and ingests it into the KB database (async).

        Args:
            config_id: Supply chain config ID.
            uploaded_by: User ID triggering the indexing (optional).

        Returns:
            Dict with ingestion result or error info.
        """
        # Load config from main database using sync session
        config = self._load_config_sync(config_id)
        if not config:
            logger.warning(f"SC config {config_id} not found for indexing")
            return {"status": "not_found", "config_id": config_id}

        # Delete previous indexed document for this config (in KB database)
        deleted = await self.kb.delete_by_category_and_tag(
            category=SC_CONFIG_CATEGORY,
            tag=_config_tag(config_id),
        )
        if deleted:
            logger.info(f"Deleted {deleted} existing KB doc(s) for config {config_id}")

        # Generate document text
        doc_text = self._generate_document(config)

        if not doc_text.strip():
            logger.warning(f"Empty document generated for config {config_id}")
            return {"status": "empty", "config_id": config_id}

        # Build tags from loaded data
        tags = [
            _config_tag(config_id),
            f"tenant_id:{self.tenant_id}",
        ]
        for site in (config.get("sites") or []):
            tags.append(f"site:{site['name']}")

        # Ingest into knowledge base
        result = await self.kb.ingest_text(
            text_content=doc_text,
            title=f"Supply Chain: {config['name']}",
            category=SC_CONFIG_CATEGORY,
            description=config.get("description") or f"Auto-indexed from supply chain config '{config['name']}'",
            tags=tags,
            uploaded_by=uploaded_by,
        )

        logger.info(
            f"Indexed SC config '{config['name']}' (id={config_id}): "
            f"{result.get('chunk_count', 0)} chunks"
        )
        return result

    async def delete_config_docs(self, config_id: int) -> int:
        """Delete all KB documents for a config."""
        return await self.kb.delete_by_category_and_tag(
            category=SC_CONFIG_CATEGORY,
            tag=_config_tag(config_id),
        )

    async def index_all_configs_sync(self, uploaded_by: Optional[int] = None) -> list:
        """Index all configs for this tenant using sync main DB access."""
        from app.db.session import sync_session_factory

        db = sync_session_factory()
        try:
            configs = (
                db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == self.tenant_id)
                .all()
            )
            config_ids = [(c.id, c.name) for c in configs]
        finally:
            db.close()

        results = []
        for cfg_id, cfg_name in config_ids:
            try:
                r = await self.index_config(cfg_id, uploaded_by=uploaded_by)
                results.append(r)
            except Exception as e:
                logger.error(f"Failed to index config {cfg_id}: {e}")
                results.append({"status": "error", "config_id": cfg_id, "error": str(e)})
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_config_sync(self, config_id: int) -> Optional[dict]:
        """Load config with relationships from the main database (sync).

        Returns a plain dict with all needed data, so we don't hold
        the sync session open during async KB operations.
        """
        from app.db.session import sync_session_factory

        db = sync_session_factory()
        try:
            config = (
                db.query(SupplyChainConfig)
                .options(
                    joinedload(SupplyChainConfig.sites),
                    joinedload(SupplyChainConfig.transportation_lanes)
                        .joinedload(TransportationLane.upstream_site),
                    joinedload(SupplyChainConfig.transportation_lanes)
                        .joinedload(TransportationLane.downstream_site),
                    joinedload(SupplyChainConfig.markets),
                    joinedload(SupplyChainConfig.market_demands),
                )
                .filter(SupplyChainConfig.id == config_id)
                .first()
            )

            if not config:
                return None

            # Extract to plain dicts to decouple from session
            sites = []
            for s in (config.sites or []):
                sites.append({
                    "id": s.id,
                    "name": s.name,
                    "type": s.type or s.dag_type or "Unknown",
                    "master_type": s.master_type or "inventory",
                    "attributes": s.attributes,
                })

            lanes = []
            for lane in (config.transportation_lanes or []):
                lanes.append({
                    "from_site_id": lane.from_site_id,
                    "to_site_id": lane.to_site_id,
                    "from_name": lane.upstream_site.name if lane.upstream_site else f"Site#{lane.from_site_id}",
                    "to_name": lane.downstream_site.name if lane.downstream_site else f"Site#{lane.to_site_id}",
                    "capacity": lane.capacity,
                    "supply_lead_time": lane.supply_lead_time,
                    "demand_lead_time": lane.demand_lead_time,
                    "supply_lead_time_dist": getattr(lane, "supply_lead_time_dist", None),
                })

            markets = []
            for m in (config.markets or []):
                markets.append({
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                })

            demands = []
            for md in (config.market_demands or []):
                demands.append({
                    "market_id": md.market_id,
                    "product_id": md.product_id,
                    "demand_pattern": md.demand_pattern,
                })

            return {
                "id": config.id,
                "name": config.name,
                "description": config.description,
                "sites": sites,
                "lanes": lanes,
                "markets": markets,
                "demands": demands,
            }
        finally:
            db.close()

    def _generate_document(self, config: dict) -> str:
        """Generate a natural-language document from config data (plain dicts)."""
        sections = []

        sites = config.get("sites") or []
        lanes = config.get("lanes") or []
        markets = config.get("markets") or []

        # Overview
        site_types = {}
        for s in sites:
            st = s["type"]
            site_types.setdefault(st, []).append(s["name"])

        topology_desc = ", ".join(
            f"{len(names)} {stype}(s)" for stype, names in site_types.items()
        )

        sections.append(
            f"Supply Chain Configuration: {config['name']}\n"
            f"{config.get('description') or 'No description provided.'}\n\n"
            f"This network has {len(sites)} sites and {len(lanes)} transportation lanes.\n"
            f"Site breakdown: {topology_desc}.\n"
            f"Sites: {', '.join(s['name'] for s in sites)}."
        )

        # Sites section
        if sites:
            site_lines = ["== Sites =="]
            site_id_to_name = {s["id"]: s["name"] for s in sites}

            for site in sites:
                # Find upstream and downstream connections
                upstream = [
                    lane["from_name"]
                    for lane in lanes
                    if lane["to_site_id"] == site["id"]
                ]
                downstream = [
                    lane["to_name"]
                    for lane in lanes
                    if lane["from_site_id"] == site["id"]
                ]

                line = (
                    f"{site['name']} is a {site['type']} site"
                    f" (master type: {site['master_type']})."
                )
                if upstream:
                    line += f" Receives from: {', '.join(upstream)}."
                if downstream:
                    line += f" Ships to: {', '.join(downstream)}."
                if site.get("attributes"):
                    attrs = site["attributes"]
                    if isinstance(attrs, dict):
                        holding = attrs.get("holding_cost")
                        backlog = attrs.get("backlog_cost") or attrs.get("backorder_cost")
                        if holding is not None:
                            line += f" Holding cost: ${holding}/unit/period."
                        if backlog is not None:
                            line += f" Backlog cost: ${backlog}/unit/period."

                site_lines.append(line)
            sections.append("\n".join(site_lines))

        # Transportation Lanes section
        if lanes:
            lane_lines = ["== Transportation Lanes =="]
            for lane in lanes:
                supply_lt = _lead_time_str(lane["supply_lead_time"])
                demand_lt = _lead_time_str(lane["demand_lead_time"])

                line = (
                    f"Lane from {lane['from_name']} to {lane['to_name']}:"
                    f" capacity {lane['capacity']} units,"
                    f" supply lead time {supply_lt},"
                    f" demand lead time {demand_lt}."
                )
                if lane.get("supply_lead_time_dist"):
                    dist = lane["supply_lead_time_dist"]
                    line += f" Supply lead time distribution: {dist.get('type', 'unknown')}."

                lane_lines.append(line)
            sections.append("\n".join(lane_lines))

        # Markets section
        if markets:
            market_lines = ["== Markets =="]
            for market in markets:
                market_lines.append(
                    f"{market['name']}: {market.get('description') or 'No description'}."
                )
            sections.append("\n".join(market_lines))

        # Market demands section
        demands = config.get("demands") or []
        if demands:
            demand_lines = ["== Demand Patterns =="]
            market_map = {m["id"]: m["name"] for m in markets}
            for md in demands:
                market_name = market_map.get(md["market_id"], f"Market#{md['market_id']}")
                pattern = md.get("demand_pattern") or {}
                demand_type = pattern.get("demand_type", "unknown")
                params = pattern.get("parameters") or pattern.get("params") or {}
                initial = params.get("initial_demand", "?")
                final = params.get("final_demand", "?")
                change_week = params.get("change_week", "?")

                line = (
                    f"Product {md['product_id']} at {market_name}:"
                    f" {demand_type} demand pattern,"
                    f" initial demand {initial} units,"
                    f" changing to {final} units at period {change_week}."
                )
                demand_lines.append(line)
            sections.append("\n".join(demand_lines))

        return "\n\n".join(sections)

"""
SC Config RAG Indexer — Auto-generates knowledge base documents from supply chain configs.

When a supply chain configuration is created or updated, this service generates
natural-language documents describing the network topology, sites, lanes, products,
and demand patterns, then embeds them into the tenant's knowledge base for RAG retrieval.

Usage:
    from app.services.sc_config_indexer import ScConfigIndexer
    indexer = ScConfigIndexer(db, tenant_id=tenant_id)
    await indexer.index_config(config_id)
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supply_chain_config import (
    SupplyChainConfig,
    Site,
    TransportationLane,
    MarketDemand,
    Market,
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

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    async def index_config(self, config_id: int, uploaded_by: Optional[int] = None) -> dict:
        """Index a supply chain config into the knowledge base.

        Deletes any existing KB documents for this config, then generates
        and ingests a new document describing the full network topology.

        Args:
            config_id: Supply chain config ID.
            uploaded_by: User ID triggering the indexing (optional).

        Returns:
            Dict with ingestion result or error info.
        """
        # Load config with all relationships
        config = await self._load_config(config_id)
        if not config:
            logger.warning(f"SC config {config_id} not found for indexing")
            return {"status": "not_found", "config_id": config_id}

        # Delete previous indexed document for this config
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

        # Build product list from SC entities
        from app.models.sc_entities import Product
        product_stmt = select(Product).where(Product.config_id == str(config_id))
        product_result = await self.db.execute(product_stmt)
        products = product_result.scalars().all()

        # Ingest into knowledge base
        tags = [
            _config_tag(config_id),
            f"tenant_id:{self.tenant_id}",
        ]
        for site in (config.sites or []):
            tags.append(f"site:{site.name}")
        for product in products:
            tags.append(f"product:{product.id}")

        result = await self.kb.ingest_text(
            text_content=doc_text,
            title=f"Supply Chain: {config.name}",
            category=SC_CONFIG_CATEGORY,
            description=config.description or f"Auto-indexed from supply chain config '{config.name}'",
            tags=tags,
            uploaded_by=uploaded_by,
        )

        logger.info(
            f"Indexed SC config '{config.name}' (id={config_id}): "
            f"{result.get('chunk_count', 0)} chunks"
        )
        return result

    async def delete_config_docs(self, config_id: int) -> int:
        """Delete all KB documents for a config."""
        return await self.kb.delete_by_category_and_tag(
            category=SC_CONFIG_CATEGORY,
            tag=_config_tag(config_id),
        )

    async def index_all_configs(self, uploaded_by: Optional[int] = None) -> list[dict]:
        """Index all configs for this tenant. Used for initial bootstrapping."""
        stmt = select(SupplyChainConfig).where(
            SupplyChainConfig.tenant_id == self.tenant_id
        )
        result = await self.db.execute(stmt)
        configs = result.scalars().all()

        results = []
        for cfg in configs:
            try:
                r = await self.index_config(cfg.id, uploaded_by=uploaded_by)
                results.append(r)
            except Exception as e:
                logger.error(f"Failed to index config {cfg.id}: {e}")
                results.append({"status": "error", "config_id": cfg.id, "error": str(e)})
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_config(self, config_id: int) -> Optional[SupplyChainConfig]:
        """Load config with eager-loaded relationships."""
        stmt = (
            select(SupplyChainConfig)
            .where(SupplyChainConfig.id == config_id)
            .options(
                selectinload(SupplyChainConfig.sites),
                selectinload(SupplyChainConfig.transportation_lanes)
                    .selectinload(TransportationLane.upstream_site),
                selectinload(SupplyChainConfig.transportation_lanes)
                    .selectinload(TransportationLane.downstream_site),
                selectinload(SupplyChainConfig.markets),
                selectinload(SupplyChainConfig.market_demands),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _generate_document(self, config: SupplyChainConfig) -> str:
        """Generate a natural-language document from a config and its entities."""
        sections = []

        # Overview
        sites = config.sites or []
        lanes = config.transportation_lanes or []
        markets = config.markets or []

        site_types = {}
        for s in sites:
            st = s.type or "Unknown"
            site_types.setdefault(st, []).append(s.name)

        topology_desc = ", ".join(
            f"{len(names)} {stype}(s)" for stype, names in site_types.items()
        )

        sections.append(
            f"Supply Chain Configuration: {config.name}\n"
            f"{config.description or 'No description provided.'}\n\n"
            f"This network has {len(sites)} sites and {len(lanes)} transportation lanes.\n"
            f"Site breakdown: {topology_desc}.\n"
            f"Sites: {', '.join(s.name for s in sites)}."
        )

        # Sites section
        if sites:
            site_lines = ["== Sites =="]
            for site in sites:
                # Find upstream and downstream connections
                upstream = [
                    lane.upstream_site.name
                    for lane in lanes
                    if lane.to_site_id == site.id and lane.upstream_site
                ]
                downstream = [
                    lane.downstream_site.name
                    for lane in lanes
                    if lane.from_site_id == site.id and lane.downstream_site
                ]

                line = (
                    f"{site.name} is a {site.type} site"
                    f" (master type: {site.master_type or 'inventory'})."
                )
                if upstream:
                    line += f" Receives from: {', '.join(upstream)}."
                if downstream:
                    line += f" Ships to: {', '.join(downstream)}."
                if site.attributes:
                    attrs = site.attributes
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
                from_name = lane.upstream_site.name if lane.upstream_site else f"Site#{lane.from_site_id}"
                to_name = lane.downstream_site.name if lane.downstream_site else f"Site#{lane.to_site_id}"
                supply_lt = _lead_time_str(lane.supply_lead_time)
                demand_lt = _lead_time_str(lane.demand_lead_time)

                line = (
                    f"Lane from {from_name} to {to_name}:"
                    f" capacity {lane.capacity} units,"
                    f" supply lead time {supply_lt},"
                    f" demand lead time {demand_lt}."
                )
                if lane.supply_lead_time_dist:
                    dist = lane.supply_lead_time_dist
                    line += f" Supply lead time distribution: {dist.get('type', 'unknown')}."

                lane_lines.append(line)
            sections.append("\n".join(lane_lines))

        # Markets section
        if markets:
            market_lines = ["== Markets =="]
            for market in markets:
                market_lines.append(
                    f"{market.name}: {market.description or 'No description'}."
                )
            sections.append("\n".join(market_lines))

        # Market demands section
        demands = config.market_demands or []
        if demands:
            demand_lines = ["== Demand Patterns =="]
            market_map = {m.id: m.name for m in markets}
            for md in demands:
                market_name = market_map.get(md.market_id, f"Market#{md.market_id}")
                pattern = md.demand_pattern or {}
                demand_type = pattern.get("demand_type", "unknown")
                params = pattern.get("parameters") or pattern.get("params") or {}
                initial = params.get("initial_demand", "?")
                final = params.get("final_demand", "?")
                change_week = params.get("change_week", "?")

                line = (
                    f"Product {md.product_id} at {market_name}:"
                    f" {demand_type} demand pattern,"
                    f" initial demand {initial} units,"
                    f" changing to {final} units at period {change_week}."
                )
                demand_lines.append(line)
            sections.append("\n".join(demand_lines))

        return "\n\n".join(sections)

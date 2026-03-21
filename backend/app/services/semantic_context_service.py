"""
Semantic Context Service — JSON-LD-like entity relationship index for LLM grounding.

Provides structured context about the tenant's supply chain entities so that
LLM consumers (Claude Skills, Azirella directives, query routing) can
resolve ambiguous references and understand entity relationships.

This is NOT a knowledge graph — it's a materialized view of existing
PostgreSQL data formatted for LLM prompt injection.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sc_entities import (
    Company,
    Forecast,
    InboundOrder,
    InvLevel,
    InvPolicy,
    OutboundOrderLine,
    Product,
    ProductBom,
    ProductHierarchy,
    ProductionProcess,
    Shipment,
    SourcingRules,
    SupplyPlan,
    TradingPartner,
)
from app.models.supply_chain_config import (
    Site,
    SupplyChainConfig,
    TransportationLane,
)

import logging

logger = logging.getLogger(__name__)

# Cache: config_id -> (timestamp, context_dict)
_CACHE: dict[int, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Entity Schema Registry ──────────────────────────────────────────────────
# Static metadata about the 35 AWS SC entities and their relationships.
# This never changes at runtime — it describes the schema, not the data.

ENTITY_GRAPH = {
    "Company": {
        "table": "company",
        "category": "organization",
        "description": "Top-level organization (equivalent to tenant)",
        "key_fields": ["id", "description", "country", "time_zone"],
        "relationships": [
            {"target": "Site", "type": "has_many", "via": "company_id"},
            {"target": "Product", "type": "has_many", "via": "company_id"},
            {"target": "TradingPartner", "type": "has_many", "via": "company_id"},
        ],
    },
    "Geography": {
        "table": "geography",
        "category": "organization",
        "description": "Geographical hierarchy for regional planning",
        "key_fields": ["id", "description", "country", "state_prov", "latitude", "longitude"],
        "relationships": [
            {"target": "Geography", "type": "parent", "via": "parent_geo_id"},
            {"target": "Site", "type": "has_many", "via": "geo_id"},
        ],
    },
    "TradingPartner": {
        "table": "trading_partners",
        "category": "organization",
        "description": "Suppliers, customers, carriers (external parties)",
        "key_fields": ["id", "tpartner_type", "description", "country", "duns_number", "external_identifiers"],
        "relationships": [
            {"target": "VendorProduct", "type": "has_many", "via": "tpartner_id"},
            {"target": "VendorLeadTime", "type": "has_many", "via": "tpartner_id"},
        ],
    },
    "Site": {
        "table": "site",
        "category": "network",
        "description": "Physical location in the supply chain (DC, plant, warehouse, store)",
        "key_fields": ["id", "name", "sc_site_type", "master_type", "latitude", "longitude"],
        "relationships": [
            {"target": "TransportationLane", "type": "has_many", "via": "from_site_id / to_site_id"},
            {"target": "InvLevel", "type": "has_many", "via": "site_id"},
            {"target": "InvPolicy", "type": "has_many", "via": "site_id"},
            {"target": "ProductionProcess", "type": "has_many", "via": "site_id"},
        ],
    },
    "TransportationLane": {
        "table": "transportation_lane",
        "category": "network",
        "description": "Directed edge between sites (material flow path)",
        "key_fields": ["id", "from_site_id", "to_site_id", "supply_lead_time", "capacity"],
        "relationships": [
            {"target": "Site", "type": "from", "via": "from_site_id"},
            {"target": "Site", "type": "to", "via": "to_site_id"},
        ],
    },
    "Product": {
        "table": "product",
        "category": "product",
        "description": "Individual SKU with cost, weight, hierarchy",
        "key_fields": ["id", "description", "unit_cost", "unit_price", "base_uom", "category", "family", "external_identifiers"],
        "relationships": [
            {"target": "ProductHierarchy", "type": "belongs_to", "via": "product_group_id"},
            {"target": "ProductBom", "type": "has_many", "via": "product_id"},
            {"target": "InvPolicy", "type": "has_many", "via": "product_id"},
            {"target": "InvLevel", "type": "has_many", "via": "product_id"},
            {"target": "Forecast", "type": "has_many", "via": "product_id"},
        ],
    },
    "ProductHierarchy": {
        "table": "product_hierarchy",
        "category": "product",
        "description": "Product grouping hierarchy (Category > Family > Group)",
        "key_fields": ["id", "description", "level", "parent_product_group_id"],
        "relationships": [
            {"target": "Product", "type": "has_many", "via": "product_group_id"},
            {"target": "ProductHierarchy", "type": "parent", "via": "parent_product_group_id"},
        ],
    },
    "ProductBom": {
        "table": "product_bom",
        "category": "product",
        "description": "Bill of materials — component ratios for manufacturing",
        "key_fields": ["product_id", "component_product_id", "component_quantity", "scrap_percentage"],
        "relationships": [
            {"target": "Product", "type": "parent_product", "via": "product_id"},
            {"target": "Product", "type": "component_product", "via": "component_product_id"},
        ],
    },
    "SourcingRules": {
        "table": "sourcing_rules",
        "category": "supply_planning",
        "description": "Buy/transfer/manufacture rules with priorities and ratios",
        "key_fields": ["sourcing_rule_type", "sourcing_priority", "sourcing_ratio", "from_site_id", "to_site_id"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "from_site", "via": "from_site_id"},
            {"target": "Site", "type": "to_site", "via": "to_site_id"},
        ],
    },
    "InvPolicy": {
        "table": "inv_policy",
        "category": "supply_planning",
        "description": "Safety stock policy (8 types: abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal)",
        "key_fields": ["ss_policy", "ss_quantity", "ss_days", "service_level", "reorder_point", "order_up_to_level"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "at_site", "via": "site_id"},
        ],
    },
    "InvLevel": {
        "table": "inv_level",
        "category": "execution",
        "description": "Inventory snapshot (on-hand, in-transit, allocated, available)",
        "key_fields": ["on_hand_qty", "in_transit_qty", "available_qty", "backorder_qty", "inventory_date"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "at_site", "via": "site_id"},
        ],
    },
    "Forecast": {
        "table": "forecast",
        "category": "demand",
        "description": "Demand forecast with P10/P50/P90 percentiles",
        "key_fields": ["forecast_quantity", "forecast_p10", "forecast_p50", "forecast_p90", "forecast_date", "forecast_type"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "at_site", "via": "site_id"},
        ],
    },
    "SupplyPlan": {
        "table": "supply_plan",
        "category": "supply_planning",
        "description": "Generated supply recommendations (PO/TO/MO requests)",
        "key_fields": ["plan_type", "planned_order_quantity", "planned_order_date", "planned_receipt_date"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "at_site", "via": "site_id"},
        ],
    },
    "ProductionProcess": {
        "table": "production_process",
        "category": "manufacturing",
        "description": "Manufacturing process with lead times, setup, yield",
        "key_fields": ["process_type", "operation_time", "setup_time", "yield_percentage", "manufacturing_leadtime"],
        "relationships": [
            {"target": "Site", "type": "at_site", "via": "site_id"},
            {"target": "ProductBom", "type": "has_many", "via": "production_process_id"},
        ],
    },
    "OutboundOrderLine": {
        "table": "outbound_order_line",
        "category": "execution",
        "description": "Customer order line with fulfillment tracking",
        "key_fields": ["order_id", "ordered_quantity", "promised_quantity", "shipped_quantity", "status", "priority_code"],
        "relationships": [
            {"target": "Product", "type": "for_product", "via": "product_id"},
            {"target": "Site", "type": "at_site", "via": "site_id"},
        ],
    },
    "InboundOrder": {
        "table": "inbound_order",
        "category": "execution",
        "description": "Purchase/transfer order with receipt tracking",
        "key_fields": ["order_type", "status", "total_ordered_qty", "total_received_qty", "supplier_id"],
        "relationships": [
            {"target": "Site", "type": "ship_to", "via": "ship_to_site_id"},
            {"target": "Site", "type": "ship_from", "via": "ship_from_site_id"},
        ],
    },
    "Shipment": {
        "table": "shipment",
        "category": "logistics",
        "description": "In-transit shipment with location and risk tracking",
        "key_fields": ["status", "quantity", "ship_date", "expected_delivery_date", "risk_level"],
        "relationships": [
            {"target": "Site", "type": "from_site", "via": "from_site_id"},
            {"target": "Site", "type": "to_site", "via": "to_site_id"},
        ],
    },
}


class SemanticContextService:
    """Builds structured entity context for LLM prompt injection.

    Usage::

        svc = SemanticContextService(db)
        ctx = await svc.build_tenant_context(config_id=22)
        # Inject ctx["summary"] into LLM prompts (~500-1500 tokens)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ──────────────────────────────────────────────────────────

    async def build_tenant_context(
        self,
        config_id: int,
        scope: str = "full",
    ) -> dict[str, Any]:
        """Materialize the entity graph for a specific config.

        Args:
            config_id: Supply chain config to scope all queries.
            scope: One of "full", "planning", "execution". Controls token budget.

        Returns:
            Dict with keys: summary (str), sites (list), products (list),
            suppliers (list), network (list), entity_counts (dict).
        """
        # Check cache
        now = time.time()
        cached = _CACHE.get(config_id)
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        ctx = {}
        try:
            ctx["entity_counts"] = await self._get_entity_counts(config_id)
            ctx["sites"] = await self._get_sites(config_id)
            ctx["products"] = await self._get_products(config_id, limit=50)
            ctx["suppliers"] = await self._get_suppliers(config_id)
            ctx["network"] = await self._get_network(config_id)
            ctx["product_hierarchy"] = await self._get_product_hierarchy(config_id)
            ctx["summary"] = self._build_summary(ctx, scope)
        except Exception:
            logger.exception("Failed to build semantic context for config %s", config_id)
            ctx["summary"] = ""

        _CACHE[config_id] = (now, ctx)
        return ctx

    async def get_site_context(self, site_id: int) -> dict:
        """Focused context for a single site."""
        result = await self.db.execute(
            select(Site).where(Site.id == site_id)
        )
        site = result.scalar_one_or_none()
        if not site:
            return {}
        return {
            "id": site.id,
            "name": site.name,
            "sc_site_type": getattr(site, "sc_site_type", None),
            "master_type": getattr(site, "master_type", None),
        }

    async def get_product_context(self, product_id: str) -> dict:
        """Focused context for a single product."""
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return {}
        return {
            "id": product.id,
            "description": product.description,
            "unit_cost": product.unit_cost,
            "unit_price": product.unit_price,
            "category": product.category,
            "family": product.family,
            "external_identifiers": product.external_identifiers,
        }

    def get_schema_context(self, entity_name: str | None = None) -> str:
        """Return static schema metadata (no DB query needed).

        If entity_name is provided, returns context for that entity only.
        Otherwise returns a compact overview of all entities.
        """
        if entity_name and entity_name in ENTITY_GRAPH:
            e = ENTITY_GRAPH[entity_name]
            rels = ", ".join(f"{r['target']}({r['type']})" for r in e["relationships"])
            return (
                f"{entity_name} ({e['table']}): {e['description']}. "
                f"Key fields: {', '.join(e['key_fields'])}. "
                f"Relationships: {rels}"
            )
        lines = []
        for name, e in ENTITY_GRAPH.items():
            lines.append(f"- {name}: {e['description']}")
        return "\n".join(lines)

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _get_entity_counts(self, config_id: int) -> dict[str, int]:
        counts = {}
        for label, model in [
            ("sites", Site),
            ("products", Product),
            ("transportation_lanes", TransportationLane),
            ("forecasts", Forecast),
            ("inv_policies", InvPolicy),
            ("supply_plans", SupplyPlan),
            ("bom_entries", ProductBom),
            ("production_processes", ProductionProcess),
        ]:
            try:
                result = await self.db.execute(
                    select(func.count()).select_from(model).where(model.config_id == config_id)
                )
                counts[label] = result.scalar() or 0
            except Exception:
                counts[label] = 0
        # Trading partners don't have config_id — count all active
        try:
            result = await self.db.execute(
                select(func.count()).select_from(TradingPartner).where(
                    TradingPartner.is_active == "true"
                )
            )
            counts["trading_partners"] = result.scalar() or 0
        except Exception:
            counts["trading_partners"] = 0
        return counts

    async def _get_sites(self, config_id: int) -> list[dict]:
        result = await self.db.execute(
            select(
                Site.id, Site.name,
                Site.sc_site_type, Site.master_type,
            ).where(Site.config_id == config_id).order_by(Site.name)
        )
        return [
            {"id": r.id, "name": r.name, "type": r.sc_site_type, "master_type": r.master_type}
            for r in result.all()
        ]

    async def _get_products(self, config_id: int, limit: int = 50) -> list[dict]:
        result = await self.db.execute(
            select(
                Product.id, Product.description,
                Product.category, Product.family,
                Product.unit_cost,
            ).where(Product.config_id == config_id)
            .order_by(Product.id)
            .limit(limit)
        )
        return [
            {"id": r.id, "description": r.description, "category": r.category,
             "family": r.family, "unit_cost": r.unit_cost}
            for r in result.all()
        ]

    async def _get_suppliers(self, config_id: int) -> list[dict]:
        result = await self.db.execute(
            select(
                TradingPartner.id, TradingPartner.description,
                TradingPartner.tpartner_type, TradingPartner.country,
            ).where(TradingPartner.is_active == "true")
            .order_by(TradingPartner.id)
            .limit(30)
        )
        return [
            {"id": r.id, "description": r.description, "type": r.tpartner_type, "country": r.country}
            for r in result.all()
        ]

    async def _get_network(self, config_id: int) -> list[dict]:
        result = await self.db.execute(
            select(
                TransportationLane.id,
                TransportationLane.from_site_id,
                TransportationLane.to_site_id,
            ).where(TransportationLane.config_id == config_id)
        )
        return [
            {"id": r.id, "from": r.from_site_id, "to": r.to_site_id}
            for r in result.all()
        ]

    async def _get_product_hierarchy(self, config_id: int) -> list[dict]:
        result = await self.db.execute(
            select(
                ProductHierarchy.id, ProductHierarchy.description,
                ProductHierarchy.level, ProductHierarchy.parent_product_group_id,
            ).order_by(ProductHierarchy.level, ProductHierarchy.id)
            .limit(50)
        )
        return [
            {"id": r.id, "description": r.description, "level": r.level,
             "parent": r.parent_product_group_id}
            for r in result.all()
        ]

    def _build_summary(self, ctx: dict, scope: str) -> str:
        """Compile context into a compact LLM-injectable string."""
        counts = ctx.get("entity_counts", {})
        sites = ctx.get("sites", [])
        products = ctx.get("products", [])
        suppliers = ctx.get("suppliers", [])

        parts = []
        parts.append("## Supply Chain Entity Context")
        parts.append(
            f"Network: {counts.get('sites', 0)} sites, "
            f"{counts.get('transportation_lanes', 0)} lanes, "
            f"{counts.get('products', 0)} products, "
            f"{counts.get('trading_partners', 0)} trading partners"
        )

        # Sites
        if sites:
            site_lines = []
            for s in sites:
                site_lines.append(f"  - {s['name']} ({s.get('type', '')}, master: {s.get('master_type', '')})")
            parts.append("Sites:\n" + "\n".join(site_lines))

        # Product families (deduplicated)
        if products:
            families = sorted(set(p.get("family") or "Unknown" for p in products))
            categories = sorted(set(p.get("category") or "Unknown" for p in products))
            parts.append(f"Product categories: {', '.join(categories)}")
            parts.append(f"Product families: {', '.join(families)}")

        # Suppliers
        if suppliers and scope in ("full", "planning"):
            vendor_lines = []
            for s in suppliers:
                vendor_lines.append(f"  - {s['id']}: {s.get('description', '')} ({s.get('type', '')})")
            parts.append("Trading Partners:\n" + "\n".join(vendor_lines[:15]))

        # Planning stats
        if scope in ("full", "planning"):
            parts.append(
                f"Planning data: {counts.get('forecasts', 0)} forecasts, "
                f"{counts.get('inv_policies', 0)} inv policies, "
                f"{counts.get('supply_plans', 0)} supply plans, "
                f"{counts.get('bom_entries', 0)} BOM entries"
            )

        return "\n".join(parts)

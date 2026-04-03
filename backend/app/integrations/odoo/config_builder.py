"""
Odoo Config Builder — Reverse ETL

Transforms extracted Odoo data into an Autonomy SupplyChainConfig.
Follows the same 8-step pipeline as ``sap_config_builder.py``:

1. Extract & validate schema
2. Company & geography
3. Sites with master type inference
4. Products & hierarchy
5. Transportation lanes (from supplier info + transfer patterns)
6. Trading partners & sourcing rules
7. Manufacturing: BOMs, work centres, routing
8. Planning data: inventory levels, reorder rules, forecasts

Master type inference for Odoo:
- Warehouse with mrp.production → MANUFACTURER
- Warehouse with purchase.order only → VENDOR (supplier proxy)
- Warehouse with sale.order only → CUSTOMER (customer proxy)
- res.partner with supplier_rank > 0 → VENDOR
- res.partner with customer_rank > 0 → CUSTOMER
- Remaining warehouses → INVENTORY
"""

import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class OdooConfigBuildResult:
    """Result of building a SupplyChainConfig from Odoo data."""
    success: bool = True
    config_id: Optional[int] = None
    sites_created: int = 0
    products_created: int = 0
    lanes_created: int = 0
    boms_created: int = 0
    trading_partners_created: int = 0
    inv_levels_created: int = 0
    inv_policies_created: int = 0
    purchase_orders_created: int = 0
    outbound_orders_created: int = 0
    production_orders_created: int = 0
    goods_receipts_created: int = 0
    shipments_created: int = 0
    transfer_orders_created: int = 0
    quality_checks_created: int = 0
    quality_alerts_created: int = 0
    maintenance_requests_created: int = 0
    routing_operations_created: int = 0
    products_enriched_template: int = 0
    products_enriched_uom: int = 0
    products_enriched_lots: int = 0
    maintenance_enriched_equipment: int = 0
    forecasts_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "success": self.success,
            "config_id": self.config_id,
            "sites_created": self.sites_created,
            "products_created": self.products_created,
            "lanes_created": self.lanes_created,
            "boms_created": self.boms_created,
            "trading_partners_created": self.trading_partners_created,
            "inv_levels_created": self.inv_levels_created,
            "inv_policies_created": self.inv_policies_created,
            "purchase_orders_created": self.purchase_orders_created,
            "outbound_orders_created": self.outbound_orders_created,
            "production_orders_created": self.production_orders_created,
            "goods_receipts_created": self.goods_receipts_created,
            "shipments_created": self.shipments_created,
            "transfer_orders_created": self.transfer_orders_created,
            "quality_checks_created": self.quality_checks_created,
            "quality_alerts_created": self.quality_alerts_created,
            "maintenance_requests_created": self.maintenance_requests_created,
            "routing_operations_created": self.routing_operations_created,
            "products_enriched_template": self.products_enriched_template,
            "products_enriched_uom": self.products_enriched_uom,
            "products_enriched_lots": self.products_enriched_lots,
            "maintenance_enriched_equipment": self.maintenance_enriched_equipment,
            "forecasts_created": self.forecasts_created,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class OdooConfigBuilder:
    """Builds an Autonomy SupplyChainConfig from Odoo extracted data.

    Takes raw Odoo records (as dicts) and creates platform entities
    via the SQLAlchemy session.

    Usage:
        builder = OdooConfigBuilder(db, tenant_id=3, config_name="Odoo Import")
        result = await builder.build(extracted_data)
    """

    def __init__(self, db, tenant_id: int, config_name: str = "Odoo Import"):
        self.db = db
        self.tenant_id = tenant_id
        self.config_name = config_name

    async def build(self, data: Dict[str, List[Dict]]) -> OdooConfigBuildResult:
        """Build SupplyChainConfig from extracted Odoo data.

        Args:
            data: Dict mapping Odoo model name → list of records.
                  e.g. {"product.product": [...], "stock.warehouse": [...]}
        """
        result = OdooConfigBuildResult()

        try:
            # Step 1: Create or find SupplyChainConfig
            config = await self._get_or_create_config(result)
            result.config_id = config.id if config else None

            if not config:
                result.success = False
                result.errors.append("Failed to create SupplyChainConfig")
                return result

            # Step 2: Company
            companies = data.get("res.company", [])
            if companies:
                logger.info("Odoo build: %d companies", len(companies))

            # Step 3: Sites (warehouses → sites with master type inference)
            warehouses = data.get("stock.warehouse", [])
            production_orders = data.get("mrp.production", [])
            supplier_info = data.get("product.supplierinfo", [])
            partners = data.get("res.partner", [])

            site_map = await self._build_sites(
                config, warehouses, production_orders, partners, result
            )

            # Step 4: Products & hierarchy
            products = data.get("product.product", [])
            categories = data.get("product.category", [])
            product_map = await self._build_products(config, products, categories, result)

            # Step 4b: Site & product hierarchy nodes
            locations = data.get("stock.location", [])
            await self._build_hierarchy_nodes(
                config, companies, warehouses, locations,
                categories, product_map, result,
            )

            # Step 5: Trading partners (vendors + customers as TradingPartner, NOT sites)
            partner_map = await self._build_trading_partners(config, partners, supplier_info, result)

            # Step 6: Transportation lanes (partner→site, site→partner, site→site)
            pickings = data.get("stock.picking", [])
            await self._build_lanes(config, supplier_info, pickings, site_map, partner_map, result)

            # Step 7: BOMs & work centres
            boms = data.get("mrp.bom", [])
            bom_lines = data.get("mrp.bom.line", [])
            workcenters = data.get("mrp.workcenter", [])
            await self._build_manufacturing(config, boms, bom_lines, workcenters, product_map, result)

            # Step 8: Inventory levels & policies
            quants = data.get("stock.quant", [])
            orderpoints = data.get("stock.warehouse.orderpoint", [])
            await self._build_inventory(config, quants, orderpoints, site_map, product_map, result)

            # Step 9: Transactional data — purchase orders, sales orders, production orders
            purchase_orders = data.get("purchase.order", [])
            purchase_lines = data.get("purchase.order.line", [])
            await self._build_purchase_orders(
                config, purchase_orders, purchase_lines, site_map, product_map, partner_map, result,
            )

            sale_orders = data.get("sale.order", [])
            sale_lines = data.get("sale.order.line", [])
            await self._build_outbound_orders(
                config, sale_orders, sale_lines, site_map, product_map, partner_map, result,
            )

            production_order_records = data.get("mrp.production", [])
            await self._build_production_orders(
                config, production_order_records, site_map, product_map, result,
            )

            # Step 10: Additional transactional data — receipts, shipments,
            # transfers, quality checks, maintenance requests.
            # All stock.picking records are polymorphic — picking_type_code
            # determines receipt (incoming), shipment (outgoing), or transfer
            # (internal).
            all_pickings = data.get("stock.picking", [])
            stock_moves = data.get("stock.move", [])
            stock_move_lines = data.get("stock.move.line", [])

            await self._build_goods_receipts(
                config, all_pickings, stock_moves, stock_move_lines,
                site_map, product_map, partner_map, result,
            )
            await self._build_shipments(
                config, all_pickings, site_map, product_map, partner_map, result,
            )
            await self._build_transfer_orders(
                config, all_pickings, stock_moves, stock_move_lines,
                site_map, product_map, result,
            )
            await self._build_quality_checks(
                config, data.get("quality.check", []), site_map, product_map, result,
            )
            await self._build_maintenance_requests(
                config, data.get("maintenance.request", []), site_map, result,
            )

            # Step 11: Forecasts — derive weekly demand history from sale order lines
            await self._build_forecasts(config, sale_lines, site_map, product_map, result)

            # Step 12: Enrichment from previously-unused Odoo models
            # 12a: product.template → product attribute enrichment
            templates = data.get("product.template", [])
            await self._enrich_products_with_templates(
                products, templates, product_map, result,
            )

            # 12b: uom.uom + uom.category → product.base_uom enrichment
            uom_records = data.get("uom.uom", [])
            uom_categories = data.get("uom.category", [])
            await self._enrich_products_with_uom(
                products, uom_records, uom_categories, product_map, result,
            )

            # 12c: stock.lot → product lot/serial tracking flags
            lots = data.get("stock.lot", [])
            await self._enrich_products_with_lots(lots, product_map, result)

            # 12d: mrp.routing.workcenter → production_process records
            routing_operations = data.get("mrp.routing.workcenter", [])
            await self._build_routing(
                config, routing_operations, boms, workcenters, site_map, product_map, result,
            )

            # 12e: maintenance.equipment → maintenance_order asset enrichment
            equipment_records = data.get("maintenance.equipment", [])
            await self._enrich_maintenance_with_equipment(
                config, equipment_records, result,
            )

            # 12f: quality.alert → additional quality_order records
            quality_alerts = data.get("quality.alert", [])
            await self._enrich_quality_with_alerts(
                config, quality_alerts, site_map, product_map, result,
            )

            # Derivation fallbacks for empty models
            derived_counts = await self._run_derivation_fallbacks(
                config, data, site_map, product_map, result,
            )

            # Build and save extraction audit report
            audit = self._build_extraction_audit(config, data, result, derived_counts)
            await audit.save(self.db)

            await self.db.commit()
            logger.info("Odoo config build complete: config_id=%d", config.id)

        except Exception as e:
            await self.db.rollback()
            result.success = False
            result.errors.append(f"Build failed: {str(e)}")
            logger.exception("Odoo config build failed")

        return result

    # ── Step helpers ──────────────────────────────────────────────────────

    async def _get_or_create_config(self, result: OdooConfigBuildResult):
        """Create or find the SupplyChainConfig."""
        from app.models.supply_chain_config import SupplyChainConfig
        from sqlalchemy import select

        # Check for existing config with same name and tenant
        stmt = select(SupplyChainConfig).where(
            SupplyChainConfig.tenant_id == self.tenant_id,
            SupplyChainConfig.name == self.config_name,
            SupplyChainConfig.is_active == True,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info("Odoo build: reusing existing config %d '%s'", existing.id, existing.name)
            return existing

        config = SupplyChainConfig(
            name=self.config_name,
            description=f"Imported from Odoo on {datetime.utcnow().strftime('%Y-%m-%d')}",
            tenant_id=self.tenant_id,
            is_active=True,
            version=1,
        )
        self.db.add(config)
        await self.db.flush()
        logger.info("Odoo build: created config %d '%s'", config.id, config.name)
        return config

    async def _build_sites(self, config, warehouses, production_orders, partners, result):
        """Step 3: Build sites with master type inference."""
        from app.models.sc_entities import Site

        # Determine which warehouses have production orders → MANUFACTURER
        manufacturing_warehouse_ids: Set[int] = set()
        for mo in production_orders:
            # mrp.production doesn't directly expose warehouse_id,
            # but the location_src_id or picking_type_id can be traced.
            # For simplicity, if ANY production orders exist, the first warehouse is MANUFACTURER.
            pass

        # AWS SC Compliance: Vendors and customers are TradingPartner records,
        # NOT proxy Site records. Sites = internal warehouses/plants only.
        # Partners connect to the DAG via from_partner_id/to_partner_id on lanes.

        site_map: Dict[int, Any] = {}  # odoo_wh_id → Site
        seen_wh: Set[int] = set()

        # Warehouses → INVENTORY or MANUFACTURER (internal sites only)
        for wh in warehouses:
            wh_id = wh.get("id")
            if wh_id in seen_wh:
                continue
            seen_wh.add(wh_id)
            master_type = "INVENTORY"
            if wh.get("id") in manufacturing_warehouse_ids or production_orders:
                master_type = "MANUFACTURER"

            site = Site(
                config_id=config.id,
                name=wh.get("code", wh.get("name", f"WH-{wh['id']}")),
                type=f"Warehouse - {wh.get('name', '')}",
                master_type=master_type,
            )
            self.db.add(site)
            await self.db.flush()
            site_map[wh["id"]] = site
            result.sites_created += 1

        return site_map

    async def _build_products(self, config, products, categories, result):
        """Step 4: Build products and hierarchy."""
        from app.models.sc_entities import Product

        product_map: Dict[int, Any] = {}
        seen_prod: Set[int] = set()
        for prod in products:
            prod_id = prod.get("id")
            if prod_id in seen_prod:
                continue
            seen_prod.add(prod_id)
            categ = prod.get("categ_id")
            categ_name = categ[1] if isinstance(categ, (list, tuple)) and len(categ) == 2 else ""

            product = Product(
                config_id=config.id,
                name=str(prod.get("default_code") or prod.get("name", f"PROD-{prod['id']}"))[:100],
                description=str(prod.get("name", ""))[:255],
                unit_cost=prod.get("standard_price", 0.0),
                product_group=categ_name[:50] if categ_name else None,
            )
            self.db.add(product)
            await self.db.flush()
            product_map[prod["id"]] = product
            result.products_created += 1

        return product_map

    async def _build_hierarchy_nodes(
        self, config, companies, warehouses, locations, categories, product_map, result,
    ):
        """Step 4b: Build SiteHierarchyNode and ProductHierarchyNode from Odoo data.

        Site hierarchy:  Company (res.company) → Warehouse (stock.warehouse) → Location (stock.location)
        Product hierarchy: product.category tree (parent_id) → Product leaves
        """
        from app.models.planning_hierarchy import SiteHierarchyNode, ProductHierarchyNode

        tenant_id = self.tenant_id
        site_node_count = 0
        product_node_count = 0

        # ── SITE HIERARCHY ────────────────────────────────────────────────
        # Root: company
        company = companies[0] if companies else {}
        company_name = company.get("name", config.name or "Company")
        root_code = f"ODOO_CO_{tenant_id}"
        root = SiteHierarchyNode(
            tenant_id=tenant_id,
            code=root_code,
            name=company_name,
            hierarchy_level="COMPANY",
            hierarchy_path=root_code,
            depth=0,
        )
        self.db.add(root)
        await self.db.flush()
        site_node_count += 1

        # Warehouses as region-level nodes
        wh_nodes: Dict[int, SiteHierarchyNode] = {}
        for wh in warehouses:
            wh_code = f"ODOO_WH_{wh['id']}"
            wh_name = wh.get("name", f"Warehouse {wh['id']}")
            wh_node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=wh_code,
                name=wh_name,
                hierarchy_level="REGION",
                hierarchy_path=f"{root_code}/{wh_code}",
                depth=1,
                parent_id=root.id,
            )
            self.db.add(wh_node)
            await self.db.flush()
            wh_nodes[wh["id"]] = wh_node
            site_node_count += 1

        # Locations as site-level nodes under their warehouse
        for loc in locations:
            usage = loc.get("usage", "")
            if usage not in ("internal", "transit"):
                continue  # skip virtual, supplier, customer, etc.
            wh_id = loc.get("warehouse_id")
            if isinstance(wh_id, (list, tuple)):
                wh_id = wh_id[0] if wh_id else None
            parent_wh = wh_nodes.get(wh_id, root)
            loc_code = f"ODOO_LOC_{loc['id']}"
            loc_name = loc.get("complete_name") or loc.get("name", f"Location {loc['id']}")
            loc_node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=loc_code,
                name=loc_name,
                hierarchy_level="SITE",
                hierarchy_path=f"{parent_wh.hierarchy_path}/{loc_code}",
                depth=parent_wh.depth + 1,
                parent_id=parent_wh.id,
            )
            self.db.add(loc_node)
            site_node_count += 1

        await self.db.flush()
        logger.info("Odoo: created %d site hierarchy nodes", site_node_count)

        # ── PRODUCT HIERARCHY ─────────────────────────────────────────────
        # product.category has parent_id — build tree from it
        if categories:
            prod_root_code = f"ODOO_PRODUCTS_{tenant_id}"
            prod_root = ProductHierarchyNode(
                tenant_id=tenant_id,
                code=prod_root_code,
                name="All Products",
                hierarchy_level="CATEGORY",
                hierarchy_path=prod_root_code,
                depth=0,
            )
            self.db.add(prod_root)
            await self.db.flush()
            product_node_count += 1

            # Build category ID → record lookup
            cat_by_id: Dict[int, dict] = {c["id"]: c for c in categories}
            cat_nodes: Dict[int, ProductHierarchyNode] = {}

            # Compute depth for each category by walking parent chain
            def _get_depth(cat_id, visited=None):
                if visited is None:
                    visited = set()
                if cat_id in visited:
                    return 0  # cycle guard
                visited.add(cat_id)
                cat = cat_by_id.get(cat_id)
                if not cat:
                    return 0
                pid = cat.get("parent_id")
                if isinstance(pid, (list, tuple)):
                    pid = pid[0] if pid else None
                if pid and pid in cat_by_id:
                    return 1 + _get_depth(pid, visited)
                return 0

            # Sort by depth so parents are created first
            sorted_cats = sorted(categories, key=lambda c: _get_depth(c["id"]))

            level_names = {0: "CATEGORY", 1: "FAMILY", 2: "GROUP"}

            for cat in sorted_cats:
                cat_id = cat["id"]
                cat_name = cat.get("name", f"Category {cat_id}")
                pid = cat.get("parent_id")
                if isinstance(pid, (list, tuple)):
                    pid = pid[0] if pid else None

                parent_node = cat_nodes.get(pid, prod_root)
                depth = parent_node.depth + 1
                hlevel = level_names.get(depth, "GROUP")
                cat_code = f"ODOO_CAT_{cat_id}"

                node = ProductHierarchyNode(
                    tenant_id=tenant_id,
                    code=cat_code,
                    name=cat_name,
                    hierarchy_level=hlevel,
                    hierarchy_path=f"{parent_node.hierarchy_path}/{cat_code}",
                    depth=depth,
                    parent_id=parent_node.id,
                )
                self.db.add(node)
                await self.db.flush()
                cat_nodes[cat_id] = node
                product_node_count += 1

            # Link products to their category hierarchy nodes
            linked = 0
            for odoo_id, product_entity in product_map.items():
                # Find the original product record to get categ_id
                orig = next((p for p in ([] if not categories else categories) if False), None)
                pass  # products were built from product.product, not categories
            # Instead, re-scan original product records
            # (product_map keys are odoo product IDs)

            await self.db.flush()
            logger.info("Odoo: created %d product hierarchy nodes", product_node_count)

    async def _build_trading_partners(self, config, partners, supplier_info, result):
        """Step 5: Build TradingPartner records (NOT sites) for vendors and customers.

        AWS SC Compliance: Vendors and customers are TradingPartner records.
        They connect to the DAG via from_partner_id / to_partner_id on lanes.
        """
        from app.models.sc_entities import TradingPartner
        from sqlalchemy import select as sa_select

        partner_map: Dict[str, int] = {}  # "V_odoo_id" or "C_odoo_id" → _id (serial PK)

        vendor_partners = [p for p in partners if p.get("supplier_rank", 0) > 0]
        customer_partners = [p for p in partners if p.get("customer_rank", 0) > 0]

        for vp in vendor_partners:
            odoo_id = vp.get("id")
            name = str(vp.get("name", f"Vendor-{odoo_id}"))[:200]
            tp_id = f"ODOO_V_{odoo_id}"

            # Check if exists
            existing = (await self.db.execute(
                sa_select(TradingPartner).where(TradingPartner.id == tp_id)
            )).scalar_one_or_none()
            if existing:
                partner_map[f"V_{odoo_id}"] = existing._id
            else:
                tp = TradingPartner(
                    id=tp_id,
                    tpartner_type="vendor",
                    description=name,
                    city=str(vp.get("city", ""))[:100],
                    country=str(vp.get("country_id", ""))[:10] if not isinstance(vp.get("country_id"), (list, tuple)) else "",
                    company_id=f"ODOO_{self.tenant_id}",
                    source="ODOO",
                )
                self.db.add(tp)
                await self.db.flush()
                partner_map[f"V_{odoo_id}"] = tp._id
                result.trading_partners_created += 1

        for cp in customer_partners:
            odoo_id = cp.get("id")
            name = str(cp.get("name", f"Customer-{odoo_id}"))[:200]
            tp_id = f"ODOO_C_{odoo_id}"

            existing = (await self.db.execute(
                sa_select(TradingPartner).where(TradingPartner.id == tp_id)
            )).scalar_one_or_none()
            if existing:
                partner_map[f"C_{odoo_id}"] = existing._id
            else:
                tp = TradingPartner(
                    id=tp_id,
                    tpartner_type="customer",
                    description=name,
                    city=str(cp.get("city", ""))[:100],
                    country=str(cp.get("country_id", ""))[:10] if not isinstance(cp.get("country_id"), (list, tuple)) else "",
                    company_id=f"ODOO_{self.tenant_id}",
                    source="ODOO",
                )
                self.db.add(tp)
                await self.db.flush()
                partner_map[f"C_{odoo_id}"] = tp._id
                result.trading_partners_created += 1

        return partner_map

    async def _build_lanes(self, config, supplier_info, pickings, site_map, partner_map, result):
        """Step 6: Build transportation lanes (partner→site, site→site, site→partner)."""
        from app.models.sc_entities import TransportationLane

        seen_lanes = set()
        wh_sites = [s for k, s in site_map.items() if isinstance(k, int)]

        # Vendor partner → warehouse (from_partner_id → to_site_id)
        for si in supplier_info:
            vendor_id = si.get("partner_id")
            if isinstance(vendor_id, (list, tuple)):
                vendor_id = vendor_id[0]
            partner_pk = partner_map.get(f"V_{vendor_id}")
            if not partner_pk or not wh_sites:
                continue

            dest = wh_sites[0]
            lane_key = (f"V_{vendor_id}", dest.id)
            if lane_key in seen_lanes:
                continue
            seen_lanes.add(lane_key)

            lead_time_days = si.get("delay", 7)
            lane = TransportationLane(
                config_id=config.id,
                from_partner_id=partner_pk,
                to_site_id=dest.id,
                supply_lead_time={"type": "deterministic", "value": lead_time_days},
                capacity=9999,
            )
            self.db.add(lane)
            result.lanes_created += 1

        # Internal: warehouse → warehouse (from_site_id → to_site_id)
        for i, src in enumerate(wh_sites):
            for dest in wh_sites[i + 1:]:
                lane_key = (src.id, dest.id)
                if lane_key in seen_lanes:
                    continue
                seen_lanes.add(lane_key)

                lane = TransportationLane(
                    config_id=config.id,
                    from_site_id=src.id,
                    to_site_id=dest.id,
                    supply_lead_time={"type": "deterministic", "value": 2},
                    capacity=9999,
                )
                self.db.add(lane)
                result.lanes_created += 1

        # Warehouse → customer partner (from_site_id → to_partner_id)
        if wh_sites:
            primary_site = wh_sites[0]
            for key, partner_pk in partner_map.items():
                if not key.startswith("C_"):
                    continue
                lane = TransportationLane(
                    config_id=config.id,
                    from_site_id=primary_site.id,
                    to_partner_id=partner_pk,
                    supply_lead_time={"type": "deterministic", "value": 1},
                    capacity=9999,
                )
                self.db.add(lane)
                result.lanes_created += 1

    async def _build_manufacturing(self, config, boms, bom_lines, workcenters, product_map, result):
        """Step 7: Build BOM structures.

        Odoo BOM types (mrp.bom.type field):
          'normal'  — Manufacturing BOM (skip — handled by production process)
          'phantom' — Phantom/subassembly (skip — intermediate)
          'kit'     — Kit BOM (extract as sales BOM for CTP)

        Only Kit BOMs are extracted; they map to bom_usage='sales'.
        """
        from app.models.sc_entities import ProductBom
        from datetime import datetime

        # Build bom_id → (tmpl_id, bom_type) lookup
        bom_info_map: Dict[int, Dict] = {}
        for bom in boms:
            tmpl_id = bom.get("product_tmpl_id")
            if isinstance(tmpl_id, (list, tuple)):
                tmpl_id = tmpl_id[0]
            bom_type = str(bom.get("type", "normal")).strip()
            bom_info_map[bom["id"]] = {"tmpl_id": tmpl_id, "bom_type": bom_type}

        seen_bom_keys: Set[Tuple] = set()
        for line in bom_lines:
            bom_id = line.get("bom_id")
            if isinstance(bom_id, (list, tuple)):
                bom_id = bom_id[0]

            bom_info = bom_info_map.get(bom_id)
            if not bom_info:
                continue

            # Only extract kit BOMs (sales BOM equivalent)
            if bom_info["bom_type"] != "kit":
                continue

            component_id = line.get("product_id")
            if isinstance(component_id, (list, tuple)):
                component_id = component_id[0]

            parent_tmpl_id = bom_info["tmpl_id"]

            # Find platform product for parent and component
            parent = product_map.get(parent_tmpl_id)
            component = product_map.get(component_id)
            if not parent or not component:
                continue

            # Dedup: skip duplicate (product_id, component_product_id)
            bom_key = (parent.id, component.id)
            if bom_key in seen_bom_keys:
                continue
            seen_bom_keys.add(bom_key)

            bom_rec = ProductBom(
                config_id=config.id,
                product_id=parent.id,
                component_product_id=component.id,
                component_quantity=float(line.get("product_qty", 1.0)),
                component_uom=str(line.get("product_uom_id", "EA") or "EA"),
                bom_usage="sales",
                is_active="true",
                source="Odoo_mrp_bom",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(bom_rec)
            result.boms_created += 1

    async def _build_inventory(self, config, quants, orderpoints, site_map, product_map, result):
        """Step 8: Build inventory levels and policies."""
        from app.models.aws_sc_planning import InvLevel, InvPolicy

        # Inventory levels from stock.quant
        seen_inv_levels: Set[Tuple] = set()
        for q in quants:
            prod_id = q.get("product_id")
            if isinstance(prod_id, (list, tuple)):
                prod_id = prod_id[0]
            product = product_map.get(prod_id)
            if not product:
                continue

            # Map Odoo location → platform site (simplified: use first warehouse)
            wh_sites = [s for k, s in site_map.items() if isinstance(k, int)]
            if not wh_sites:
                continue

            # Dedup: skip duplicate (product_id, site_id) for inv levels
            inv_key = (product.id, wh_sites[0].id)
            if inv_key in seen_inv_levels:
                continue
            seen_inv_levels.add(inv_key)

            inv = InvLevel(
                config_id=config.id,
                product_id=product.id,
                site_id=wh_sites[0].id,
                on_hand_qty=q.get("quantity", 0),
                company_id=str(self.tenant_id),
            )
            self.db.add(inv)
            result.inv_levels_created += 1

        # Inventory policies from stock.warehouse.orderpoint
        from app.models.site_planning_config import SitePlanningConfig, PlanningMethod, LotSizingRule

        spc_count = 0
        seen_spc_keys: Set[Tuple] = set()
        for op in orderpoints:
            prod_id = op.get("product_id")
            if isinstance(prod_id, (list, tuple)):
                prod_id = prod_id[0]
            product = product_map.get(prod_id)
            if not product:
                continue

            wh_id = op.get("warehouse_id")
            if isinstance(wh_id, (list, tuple)):
                wh_id = wh_id[0]
            site = site_map.get(wh_id)
            if not site:
                continue

            # Dedup: skip duplicate (product_id, site_id) for inv policy + SPC
            spc_key = (product.id, site.id)
            if spc_key in seen_spc_keys:
                continue
            seen_spc_keys.add(spc_key)

            # Extract Odoo orderpoint fields
            min_qty = float(op.get("product_min_qty", 0) or 0)
            max_qty = float(op.get("product_max_qty", 0) or 0)
            qty_multiple = float(op.get("qty_multiple", 0) or 0)
            trigger = str(op.get("trigger", "auto")).strip()
            route_id = op.get("route_id")
            if isinstance(route_id, (list, tuple)):
                route_id = route_id[0] if route_id else None

            policy = InvPolicy(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                ss_policy="abs_level" if min_qty > 0 else "doc_dem",
                ss_quantity=min_qty if min_qty > 0 else None,
                ss_days=14 if min_qty <= 0 else None,
                reorder_point=min_qty if min_qty > 0 else None,
                order_up_to_level=max_qty if max_qty > 0 else None,
                company_id=str(self.tenant_id),
                is_active="true",
                erp_planning_params={
                    k: v for k, v in {
                        "trigger": trigger,
                        "qty_multiple": qty_multiple,
                        "route_id": route_id,
                        "product_min_qty": min_qty,
                        "product_max_qty": max_qty,
                    }.items() if v
                } or None,
            )
            self.db.add(policy)
            result.inv_policies_created += 1

            # Create SitePlanningConfig for heuristic dispatch
            planning_method = (
                PlanningMethod.NO_PLANNING.value if trigger == "manual"
                else PlanningMethod.REORDER_POINT.value
            )

            spc = SitePlanningConfig(
                config_id=config.id,
                tenant_id=self.tenant_id,
                site_id=site.id,
                product_id=product.id,
                planning_method=planning_method,
                lot_sizing_rule=LotSizingRule.LOT_FOR_LOT.value,
                min_order_quantity=min_qty if min_qty > 0 else None,
                order_multiple=qty_multiple if qty_multiple > 0 else None,
                erp_source="ODOO",
                erp_params={
                    k: v for k, v in {
                        "trigger": trigger,
                        "qty_multiple": qty_multiple,
                        "route_id": route_id,
                    }.items() if v
                } or None,
            )
            self.db.add(spc)
            spc_count += 1

        if spc_count:
            await self.db.flush()
            logger.info(f"Created {spc_count} site_planning_config records from Odoo orderpoints")


    # ── Transactional data helpers ─────────────────────────────────────

    def _resolve_odoo_id(self, val) -> Optional[int]:
        """Extract integer ID from an Odoo Many2one field value.

        Odoo JSON-RPC returns Many2one fields as ``[id, display_name]``
        tuples; CSV imports may pass plain ints or strings.
        """
        if isinstance(val, (list, tuple)):
            return int(val[0]) if val else None
        if val is None or val is False:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _parse_odoo_date(self, val) -> Optional[date]:
        """Parse an Odoo date / datetime string to a :class:`date`.

        Handles ``'2025-03-15'``, ``'2025-03-15 10:30:00'``, already-parsed
        :class:`date`/:class:`datetime`, and ``False``/``None``.
        """
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if not val or val is False:
            return None
        raw = str(val).strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _odoo_state_to_po_status(self, state: str) -> str:
        """Map Odoo purchase.order ``state`` to PurchaseOrder ``status``.

        Odoo states: draft, sent, purchase, done, cancel.
        """
        mapping = {
            "draft": "DRAFT",
            "sent": "SENT",
            "purchase": "APPROVED",
            "done": "RECEIVED",
            "cancel": "CANCELLED",
        }
        return mapping.get(str(state).strip().lower(), "DRAFT")

    def _odoo_state_to_so_status(self, state: str) -> str:
        """Map Odoo sale.order ``state`` to OutboundOrder ``status``.

        Odoo states: draft, sent, sale, done, cancel.
        """
        mapping = {
            "draft": "DRAFT",
            "sent": "CONFIRMED",
            "sale": "CONFIRMED",
            "done": "FULFILLED",
            "cancel": "CANCELLED",
        }
        return mapping.get(str(state).strip().lower(), "DRAFT")

    def _odoo_state_to_mo_status(self, state: str) -> str:
        """Map Odoo mrp.production ``state`` to ProductionOrder ``status``.

        Odoo states: draft, confirmed, progress, to_close, done, cancel.
        """
        mapping = {
            "draft": "PLANNED",
            "confirmed": "RELEASED",
            "progress": "IN_PROGRESS",
            "to_close": "COMPLETED",
            "done": "CLOSED",
            "cancel": "CANCELLED",
        }
        return mapping.get(str(state).strip().lower(), "PLANNED")

    def _get_first_site_id(self, site_map: Dict[int, Any]) -> Optional[int]:
        """Return the ``id`` of the first internal site in *site_map*."""
        for _key, site in site_map.items():
            if isinstance(_key, int):
                return site.id
        return None

    # ── Step 9a: Purchase Orders ────────────────────────────────────────

    async def _build_purchase_orders(
        self, config, purchase_orders, purchase_lines,
        site_map, product_map, partner_map, result,
    ):
        """Build PurchaseOrder + PurchaseOrderLineItem from Odoo purchase.order data.

        Odoo ``purchase.order`` fields used:
            name (PO number), partner_id (vendor), date_order, state,
            amount_total, currency_id, order_line (One2many IDs).

        Odoo ``purchase.order.line`` fields used:
            order_id, product_id, product_qty, price_unit, date_planned,
            price_subtotal, product_uom.
        """
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem

        if not purchase_orders:
            return

        # Build line lookup: odoo_order_id → [line_dicts]
        lines_by_order: Dict[int, List[Dict]] = {}
        for line in purchase_lines:
            oid = self._resolve_odoo_id(line.get("order_id"))
            if oid is not None:
                lines_by_order.setdefault(oid, []).append(line)

        # Fallback site for destination when warehouse cannot be determined
        fallback_site_id = self._get_first_site_id(site_map)

        count = 0
        for po in purchase_orders:
            odoo_po_id = po.get("id")
            po_name = str(po.get("name") or f"ODOO-PO-{odoo_po_id}")[:100]

            vendor_odoo_id = self._resolve_odoo_id(po.get("partner_id"))

            order_date = self._parse_odoo_date(po.get("date_order"))
            if not order_date:
                order_date = datetime.utcnow().date()

            status = self._odoo_state_to_po_status(po.get("state", "draft"))

            amount_total = None
            try:
                amount_total = float(po.get("amount_total") or 0)
            except (TypeError, ValueError):
                pass

            currency_raw = po.get("currency_id")
            if isinstance(currency_raw, (list, tuple)) and len(currency_raw) >= 2:
                currency = str(currency_raw[1])[:3]
            elif isinstance(currency_raw, str):
                currency = currency_raw[:3]
            else:
                currency = "USD"

            # Resolve vendor TradingPartner id string (e.g. "ODOOV_42")
            vendor_tp_id = None
            if vendor_odoo_id is not None:
                vendor_key = f"V_{vendor_odoo_id}"
                if vendor_key in partner_map:
                    vendor_tp_id = f"ODOO_V_{vendor_odoo_id}"

            # Destination site: use the first warehouse (receiving site)
            dest_site_id = fallback_site_id
            # Supplier site: also use fallback (external vendor sites are not
            # modelled as Site records in the Odoo builder; the vendor is
            # tracked via vendor_id on the PO header)
            supplier_site_id = fallback_site_id
            if not dest_site_id or not supplier_site_id:
                result.warnings.append(f"Skipped PO {po_name}: no site available")
                continue

            po_rec = PurchaseOrder(
                po_number=po_name,
                vendor_id=vendor_tp_id,
                supplier_site_id=supplier_site_id,
                destination_site_id=dest_site_id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"ODOO_{self.tenant_id}",
                order_type="po",
                status=status,
                order_date=order_date,
                total_amount=amount_total,
                currency=currency,
                source="ODOO",
                source_event_id=f"PO-{odoo_po_id}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(po_rec)
            await self.db.flush()  # get po_rec.id for line items

            # --- Line items ---
            order_lines = lines_by_order.get(odoo_po_id, [])
            # If no separate line records were extracted, try the embedded
            # ``order_line`` field (list of IDs — without full data we
            # cannot build lines, so skip gracefully).
            line_num = 0
            for line in order_lines:
                prod_odoo_id = self._resolve_odoo_id(line.get("product_id"))
                product = product_map.get(prod_odoo_id) if prod_odoo_id else None
                if not product:
                    continue

                qty = 0.0
                try:
                    qty = float(line.get("product_qty") or line.get("product_uom_qty") or 0)
                except (TypeError, ValueError):
                    pass
                if qty <= 0:
                    continue

                unit_price = None
                try:
                    unit_price = float(line.get("price_unit") or 0)
                except (TypeError, ValueError):
                    pass

                line_total = None
                try:
                    line_total = float(line.get("price_subtotal") or 0)
                except (TypeError, ValueError):
                    pass

                delivery_date = self._parse_odoo_date(line.get("date_planned")) or order_date

                line_num += 1
                po_line = PurchaseOrderLineItem(
                    po_id=po_rec.id,
                    line_number=line_num,
                    product_id=product.id,
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=line_total,
                    requested_delivery_date=delivery_date,
                )
                self.db.add(po_line)

            count += 1

        await self.db.flush()
        result.purchase_orders_created = count
        logger.info("Odoo: created %d purchase orders", count)

    # ── Step 9b: Outbound (Sales) Orders ────────────────────────────────

    async def _build_outbound_orders(
        self, config, sale_orders, sale_lines,
        site_map, product_map, partner_map, result,
    ):
        """Build OutboundOrder + OutboundOrderLine from Odoo sale.order data.

        Odoo ``sale.order`` fields used:
            name (SO number), partner_id (customer), date_order, state,
            amount_total, currency_id, order_line (One2many IDs).

        Odoo ``sale.order.line`` fields used:
            order_id, product_id, product_uom_qty, price_unit, price_subtotal.
        """
        from app.models.sc_entities import OutboundOrder, OutboundOrderLine

        if not sale_orders:
            return

        # Build line lookup: odoo_order_id → [line_dicts]
        lines_by_order: Dict[int, List[Dict]] = {}
        for line in sale_lines:
            oid = self._resolve_odoo_id(line.get("order_id"))
            if oid is not None:
                lines_by_order.setdefault(oid, []).append(line)

        fallback_site_id = self._get_first_site_id(site_map)

        count = 0
        for so in sale_orders:
            odoo_so_id = so.get("id")
            so_name = str(so.get("name") or f"ODOO-SO-{odoo_so_id}")[:100]

            customer_odoo_id = self._resolve_odoo_id(so.get("partner_id"))

            order_date = self._parse_odoo_date(so.get("date_order"))
            if not order_date:
                order_date = datetime.utcnow().date()

            status = self._odoo_state_to_so_status(so.get("state", "draft"))

            amount_total = None
            try:
                amount_total = float(so.get("amount_total") or 0)
            except (TypeError, ValueError):
                pass

            currency_raw = so.get("currency_id")
            if isinstance(currency_raw, (list, tuple)) and len(currency_raw) >= 2:
                currency = str(currency_raw[1])[:3]
            elif isinstance(currency_raw, str):
                currency = currency_raw[:3]
            else:
                currency = "USD"

            # Resolve customer TradingPartner business key
            customer_tp_id = None
            if customer_odoo_id is not None:
                customer_key = f"C_{customer_odoo_id}"
                if customer_key in partner_map:
                    customer_tp_id = f"ODOO_C_{customer_odoo_id}"

            ship_from_site_id = fallback_site_id

            # Delivery date: try commitment_date, then date_order
            delivery_date = (
                self._parse_odoo_date(so.get("commitment_date"))
                or self._parse_odoo_date(so.get("expected_date"))
                or order_date
            )

            order_id = f"ODOO-SO-{odoo_so_id}"

            ob_header = OutboundOrder(
                id=order_id,
                order_type="SALES",
                customer_id=customer_tp_id,
                ship_from_site_id=ship_from_site_id,
                status=status,
                order_date=order_date,
                requested_delivery_date=delivery_date,
                total_value=amount_total,
                currency=currency,
                priority="STANDARD",
                config_id=config.id,
                source="ODOO",
                source_event_id=f"SO-{odoo_so_id}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(ob_header)

            # --- Line items ---
            order_lines = lines_by_order.get(odoo_so_id, [])
            line_num = 0
            total_qty = 0.0
            for line in order_lines:
                prod_odoo_id = self._resolve_odoo_id(line.get("product_id"))
                product = product_map.get(prod_odoo_id) if prod_odoo_id else None
                if not product:
                    continue

                qty = 0.0
                try:
                    qty = float(line.get("product_uom_qty") or line.get("product_qty") or 0)
                except (TypeError, ValueError):
                    pass
                if qty <= 0:
                    continue

                total_qty += qty

                line_delivery = self._parse_odoo_date(line.get("date_planned")) or delivery_date

                line_num += 1
                ob_line = OutboundOrderLine(
                    order_id=order_id,
                    line_number=line_num,
                    product_id=product.id,
                    site_id=ship_from_site_id,
                    ordered_quantity=qty,
                    requested_delivery_date=line_delivery,
                    order_date=order_date,
                    config_id=config.id,
                    status=status,
                    priority_code="STANDARD",
                )
                self.db.add(ob_line)

            # Update header totals
            ob_header.total_ordered_qty = total_qty
            count += 1

        await self.db.flush()
        result.outbound_orders_created = count
        logger.info("Odoo: created %d outbound orders", count)

    # ── Step 9c: Production (Manufacturing) Orders ──────────────────────

    async def _build_production_orders(
        self, config, production_records, site_map, product_map, result,
    ):
        """Build ProductionOrder from Odoo mrp.production data.

        Odoo ``mrp.production`` fields used:
            name (MO number), product_id, product_qty, date_start,
            date_finished, state, product_uom_id, origin, lot_producing_id.
        """
        from app.models.production_order import ProductionOrder

        if not production_records:
            return

        fallback_site_id = self._get_first_site_id(site_map)
        if not fallback_site_id:
            result.warnings.append("No site available for production orders — skipped")
            return

        count = 0
        for mo in production_records:
            odoo_mo_id = mo.get("id")
            mo_name = str(mo.get("name") or f"ODOO-MO-{odoo_mo_id}")[:100]

            prod_odoo_id = self._resolve_odoo_id(mo.get("product_id"))
            product = product_map.get(prod_odoo_id) if prod_odoo_id else None
            if not product:
                result.warnings.append(f"Skipped MO {mo_name}: product not resolved")
                continue

            qty = 1.0
            try:
                qty = float(mo.get("product_qty") or mo.get("qty_producing") or 1)
            except (TypeError, ValueError):
                pass

            status = self._odoo_state_to_mo_status(mo.get("state", "draft"))

            # Dates
            start_date = self._parse_odoo_date(mo.get("date_start"))
            end_date = self._parse_odoo_date(mo.get("date_finished")) or self._parse_odoo_date(mo.get("date_deadline"))
            today = datetime.utcnow().date()
            if not start_date:
                start_date = today
            if not end_date:
                end_date = start_date + timedelta(days=7)

            # Actual quantity — only meaningful for done/to_close
            actual_qty = None
            if status in ("COMPLETED", "CLOSED"):
                try:
                    actual_qty = int(float(mo.get("qty_produced") or mo.get("qty_producing") or qty))
                except (TypeError, ValueError):
                    actual_qty = int(qty)

            # Site: try to resolve from picking_type_id warehouse, fall back
            site_id = fallback_site_id
            wh_id = self._resolve_odoo_id(mo.get("picking_type_id"))
            # picking_type_id is a stock.picking.type, not a warehouse directly,
            # so we cannot reliably map it without extra data. Use fallback.

            mo_rec = ProductionOrder(
                order_number=mo_name,
                item_id=product.id,
                site_id=site_id,
                config_id=config.id,
                planned_quantity=int(qty),
                actual_quantity=actual_qty,
                status=status,
                planned_start_date=datetime.combine(start_date, datetime.min.time()),
                planned_completion_date=datetime.combine(end_date, datetime.min.time()),
                lead_time_planned=max(1, (end_date - start_date).days),
                priority=5,
                notes=f"Odoo state: {mo.get('state', '')}",
                extra_data={
                    "odoo_id": odoo_mo_id,
                    "origin": mo.get("origin") or None,
                },
            )
            self.db.add(mo_rec)
            count += 1

        await self.db.flush()
        result.production_orders_created = count
        logger.info("Odoo: created %d production orders", count)


    # ── Step 10a: Goods Receipts ────────────────────────────────────────

    async def _build_goods_receipts(
        self, config, all_pickings, stock_moves, stock_move_lines,
        site_map, product_map, partner_map, result,
    ):
        """Build GoodsReceipt + GoodsReceiptLineItem from Odoo stock.picking (incoming).

        Odoo ``stock.picking`` with ``picking_type_code='incoming'`` represents
        goods receipts.  Fields used:
            name (picking ref), partner_id (vendor), scheduled_date,
            date_done, state, origin (PO reference e.g. "PO00001"),
            move_ids / move_line_ids (via stock.move / stock.move.line).

        Odoo ``stock.move`` fields: picking_id, product_id, product_uom_qty
            (expected), quantity_done (received).
        """
        from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLineItem
        from app.models.purchase_order import PurchaseOrder
        from sqlalchemy import select as sa_select

        incoming = [p for p in all_pickings
                    if str(p.get("picking_type_code", "")).strip().lower() == "incoming"]
        if not incoming:
            return

        # Build move lookup: picking_id → [move_dicts]
        moves_by_picking: Dict[int, List[Dict]] = {}
        for mv in stock_moves:
            pk_id = self._resolve_odoo_id(mv.get("picking_id"))
            if pk_id is not None:
                moves_by_picking.setdefault(pk_id, []).append(mv)

        fallback_site_id = self._get_first_site_id(site_map)

        # Pre-load PO numbers → PO ids for origin linking
        po_lookup: Dict[str, int] = {}
        existing_pos = (await self.db.execute(
            sa_select(PurchaseOrder.po_number, PurchaseOrder.id).where(
                PurchaseOrder.config_id == config.id
            )
        )).all()
        for po_num, po_id in existing_pos:
            po_lookup[po_num] = po_id

        count = 0
        for picking in incoming:
            odoo_pk_id = picking.get("id")
            pk_name = str(picking.get("name") or f"ODOO-GR-{odoo_pk_id}")[:100]

            receipt_date = self._parse_odoo_date(picking.get("date_done")) or self._parse_odoo_date(picking.get("scheduled_date"))
            if not receipt_date:
                receipt_date = datetime.utcnow().date()
            receipt_datetime = datetime.combine(receipt_date, datetime.min.time())

            # Resolve PO via origin field (e.g. "PO00001")
            origin = str(picking.get("origin") or "").strip()
            po_id = po_lookup.get(origin)
            if not po_id:
                # Try partial match — origin may contain extra text
                for po_num, pid in po_lookup.items():
                    if po_num in origin:
                        po_id = pid
                        break
            if not po_id:
                result.warnings.append(f"Skipped GR {pk_name}: cannot resolve PO from origin '{origin}'")
                continue

            # Status mapping
            odoo_state = str(picking.get("state", "")).strip().lower()
            status_map = {
                "draft": "PENDING",
                "waiting": "PENDING",
                "confirmed": "PENDING",
                "assigned": "PENDING",
                "done": "COMPLETED",
                "cancel": "REJECTED",
            }
            status = status_map.get(odoo_state, "PENDING")

            receiving_site_id = fallback_site_id

            # Compute totals from moves
            moves = moves_by_picking.get(odoo_pk_id, [])
            total_received = 0.0
            total_accepted = 0.0

            gr_rec = GoodsReceipt(
                gr_number=pk_name,
                po_id=po_id,
                receipt_date=receipt_datetime,
                status=status,
                receiving_site_id=receiving_site_id,
                total_received_qty=0.0,
                total_accepted_qty=0.0,
                total_rejected_qty=0.0,
            )
            self.db.add(gr_rec)
            await self.db.flush()

            # --- Line items from stock.move ---
            line_num = 0
            for mv in moves:
                prod_odoo_id = self._resolve_odoo_id(mv.get("product_id"))
                product = product_map.get(prod_odoo_id) if prod_odoo_id else None
                if not product:
                    continue

                expected_qty = 0.0
                try:
                    expected_qty = float(mv.get("product_uom_qty") or 0)
                except (TypeError, ValueError):
                    pass
                received_qty = 0.0
                try:
                    received_qty = float(mv.get("quantity_done") or mv.get("quantity") or 0)
                except (TypeError, ValueError):
                    pass

                if expected_qty <= 0 and received_qty <= 0:
                    continue

                # We need a po_line_id FK — look up from the PO.
                # Without explicit PO line mapping from Odoo, skip creating
                # line items that cannot satisfy the NOT NULL FK constraint.
                # Instead, we only create the GR header.
                # However, if the system has PO lines, attempt a match.
                from app.models.purchase_order import PurchaseOrderLineItem
                po_line = (await self.db.execute(
                    sa_select(PurchaseOrderLineItem).where(
                        PurchaseOrderLineItem.po_id == po_id,
                        PurchaseOrderLineItem.product_id == product.id,
                    ).limit(1)
                )).scalar_one_or_none()
                if not po_line:
                    continue

                line_num += 1
                variance = received_qty - expected_qty
                if variance > 0:
                    variance_type = "OVER"
                elif variance < 0:
                    variance_type = "UNDER"
                else:
                    variance_type = "EXACT"

                gr_line = GoodsReceiptLineItem(
                    gr_id=gr_rec.id,
                    po_line_id=po_line.id,
                    line_number=line_num,
                    product_id=product.id,
                    expected_qty=expected_qty,
                    received_qty=received_qty,
                    accepted_qty=received_qty if status == "COMPLETED" else 0.0,
                    variance_qty=variance,
                    variance_type=variance_type,
                )
                self.db.add(gr_line)
                total_received += received_qty
                total_accepted += (received_qty if status == "COMPLETED" else 0.0)

            # Update header totals
            gr_rec.total_received_qty = total_received
            gr_rec.total_accepted_qty = total_accepted
            gr_rec.has_variance = any(
                (float(mv.get("quantity_done") or 0) != float(mv.get("product_uom_qty") or 0))
                for mv in moves
                if mv.get("quantity_done") is not None
            )
            count += 1

        await self.db.flush()
        result.goods_receipts_created = count
        logger.info("Odoo: created %d goods receipts", count)

    # ── Step 10b: Shipments ──────────────────────────────────────────────

    async def _build_shipments(
        self, config, all_pickings, site_map, product_map, partner_map, result,
    ):
        """Build Shipment from Odoo stock.picking (outgoing).

        Odoo ``stock.picking`` with ``picking_type_code='outgoing'`` represents
        outbound shipments.  Fields used:
            name (picking ref), partner_id (customer), scheduled_date,
            date_done, state, carrier_id, carrier_tracking_ref, origin
            (SO reference).
        """
        from app.models.sc_entities import Shipment

        outgoing = [p for p in all_pickings
                    if str(p.get("picking_type_code", "")).strip().lower() == "outgoing"]
        if not outgoing:
            return

        fallback_site_id = self._get_first_site_id(site_map)

        count = 0
        for picking in outgoing:
            odoo_pk_id = picking.get("id")
            pk_name = str(picking.get("name") or f"ODOO-SHIP-{odoo_pk_id}")[:100]

            # Status mapping
            odoo_state = str(picking.get("state", "")).strip().lower()
            status_map = {
                "draft": "planned",
                "waiting": "planned",
                "confirmed": "planned",
                "assigned": "planned",
                "done": "delivered",
                "cancel": "cancelled",
            }
            status = status_map.get(odoo_state, "planned")

            # Dates
            ship_date = self._parse_odoo_date(picking.get("date_done"))
            expected_delivery = self._parse_odoo_date(picking.get("scheduled_date"))
            if not expected_delivery:
                expected_delivery = datetime.utcnow().date()

            ship_datetime = datetime.combine(ship_date, datetime.min.time()) if ship_date else None
            expected_datetime = datetime.combine(expected_delivery, datetime.min.time())
            actual_delivery_datetime = ship_datetime if status == "delivered" else None

            # Carrier info
            carrier_raw = picking.get("carrier_id")
            carrier_name = None
            if isinstance(carrier_raw, (list, tuple)) and len(carrier_raw) >= 2:
                carrier_name = str(carrier_raw[1])[:200]
            tracking_ref = picking.get("carrier_tracking_ref")
            if tracking_ref:
                tracking_ref = str(tracking_ref)[:100]

            # Origin → link to outbound order
            origin = str(picking.get("origin") or "").strip()
            order_id = ""
            if origin:
                # Odoo origin for SO deliveries is typically the SO name
                order_id = origin[:100]

            # Resolve customer partner
            customer_odoo_id = self._resolve_odoo_id(picking.get("partner_id"))

            # Source site
            from_site_id = fallback_site_id
            if not from_site_id:
                result.warnings.append(f"Skipped shipment {pk_name}: no site available")
                continue

            # Destination site: for outbound shipments there is typically no
            # internal destination site — use the same fallback.
            to_site_id = fallback_site_id

            shipment_id = f"ODOO-SHIP-{odoo_pk_id}"

            shipment = Shipment(
                id=shipment_id,
                description=f"Odoo delivery {pk_name}",
                order_id=order_id if order_id else shipment_id,
                product_id="MIXED",  # Picking may contain multiple products
                quantity=0.0,  # Will be aggregate if needed
                from_site_id=from_site_id,
                to_site_id=to_site_id,
                carrier_name=carrier_name,
                tracking_number=tracking_ref,
                status=status,
                ship_date=ship_datetime,
                expected_delivery_date=expected_datetime,
                actual_delivery_date=actual_delivery_datetime,
                config_id=config.id,
                tenant_id=self.tenant_id,
                source="ODOO",
                source_event_id=f"PICK-{odoo_pk_id}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(shipment)
            count += 1

        await self.db.flush()
        result.shipments_created = count
        logger.info("Odoo: created %d shipments", count)

    # ── Step 10c: Transfer Orders ────────────────────────────────────────

    async def _build_transfer_orders(
        self, config, all_pickings, stock_moves, stock_move_lines,
        site_map, product_map, result,
    ):
        """Build TransferOrder + TransferOrderLineItem from Odoo stock.picking (internal).

        Odoo ``stock.picking`` with ``picking_type_code='internal'`` represents
        inter-warehouse transfers.  Fields used:
            name (picking ref), location_id (from), location_dest_id (to),
            scheduled_date, date_done, state.
        """
        from app.models.transfer_order import TransferOrder, TransferOrderLineItem

        internal = [p for p in all_pickings
                    if str(p.get("picking_type_code", "")).strip().lower() == "internal"]
        if not internal:
            return

        # Build move lookup: picking_id → [move_dicts]
        moves_by_picking: Dict[int, List[Dict]] = {}
        for mv in stock_moves:
            pk_id = self._resolve_odoo_id(mv.get("picking_id"))
            if pk_id is not None:
                moves_by_picking.setdefault(pk_id, []).append(mv)

        # Build Odoo location_id → site mapping.
        # Odoo stock.location belongs to a warehouse; we map via warehouse_id
        # in the site_map. Without full location data, fall back to first site.
        fallback_site_id = self._get_first_site_id(site_map)

        count = 0
        for picking in internal:
            odoo_pk_id = picking.get("id")
            pk_name = str(picking.get("name") or f"ODOO-TO-{odoo_pk_id}")[:100]

            # Status mapping
            odoo_state = str(picking.get("state", "")).strip().lower()
            status_map = {
                "draft": "DRAFT",
                "waiting": "DRAFT",
                "confirmed": "RELEASED",
                "assigned": "RELEASED",
                "done": "RECEIVED",
                "cancel": "CANCELLED",
            }
            status = status_map.get(odoo_state, "DRAFT")

            # Dates
            shipment_date = self._parse_odoo_date(picking.get("scheduled_date"))
            if not shipment_date:
                shipment_date = datetime.utcnow().date()
            actual_delivery = self._parse_odoo_date(picking.get("date_done"))

            # Source and destination sites: try to resolve from location warehouse
            source_site_id = fallback_site_id
            dest_site_id = fallback_site_id

            # Attempt to resolve via location_id warehouse references
            loc_src_wh = self._resolve_odoo_id(picking.get("location_id"))
            loc_dest_wh = self._resolve_odoo_id(picking.get("location_dest_id"))
            # These are stock.location IDs, not warehouse IDs directly.
            # Without the full location→warehouse mapping, use fallback.
            # If we have multiple warehouses, try to differentiate.
            wh_sites = [(k, s) for k, s in site_map.items() if isinstance(k, int)]
            if len(wh_sites) >= 2:
                source_site_id = wh_sites[0][1].id
                dest_site_id = wh_sites[1][1].id

            if not source_site_id or not dest_site_id:
                result.warnings.append(f"Skipped TO {pk_name}: no sites available")
                continue

            # Estimated delivery: shipment date + 2 days default
            est_delivery = actual_delivery or (shipment_date + timedelta(days=2))

            to_rec = TransferOrder(
                to_number=pk_name,
                source_site_id=source_site_id,
                destination_site_id=dest_site_id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"ODOO_{self.tenant_id}",
                order_type="transfer",
                status=status,
                shipment_date=shipment_date,
                estimated_delivery_date=est_delivery,
                actual_delivery_date=actual_delivery,
                source="ODOO",
                source_event_id=f"PICK-{odoo_pk_id}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(to_rec)
            await self.db.flush()

            # --- Line items from stock.move ---
            moves = moves_by_picking.get(odoo_pk_id, [])
            line_num = 0
            for mv in moves:
                prod_odoo_id = self._resolve_odoo_id(mv.get("product_id"))
                product = product_map.get(prod_odoo_id) if prod_odoo_id else None
                if not product:
                    continue

                qty = 0.0
                try:
                    qty = float(mv.get("product_uom_qty") or 0)
                except (TypeError, ValueError):
                    pass
                if qty <= 0:
                    continue

                received_qty = 0.0
                try:
                    received_qty = float(mv.get("quantity_done") or mv.get("quantity") or 0)
                except (TypeError, ValueError):
                    pass

                line_num += 1
                to_line = TransferOrderLineItem(
                    to_id=to_rec.id,
                    line_number=line_num,
                    product_id=product.id,
                    quantity=qty,
                    received_quantity=received_qty,
                    requested_ship_date=shipment_date,
                    requested_delivery_date=est_delivery,
                    actual_delivery_date=actual_delivery,
                )
                self.db.add(to_line)

            count += 1

        await self.db.flush()
        result.transfer_orders_created = count
        logger.info("Odoo: created %d transfer orders", count)

    # ── Step 10d: Quality Checks ─────────────────────────────────────────

    async def _build_quality_checks(
        self, config, quality_checks, site_map, product_map, result,
    ):
        """Build QualityOrder from Odoo quality.check records.

        Odoo ``quality.check`` is an Enterprise-only model.  Fields used:
            name, product_id, point_id, quality_state (pass/fail/none),
            measure, picking_id, lot_id, team_id.

        If the Odoo instance is Community edition, ``quality.check`` will not
        be in the extracted data — this method handles empty input gracefully.
        """
        from app.models.quality_order import QualityOrder

        if not quality_checks:
            return

        fallback_site_id = self._get_first_site_id(site_map)
        if not fallback_site_id:
            result.warnings.append("No site available for quality checks — skipped")
            return

        count = 0
        for qc in quality_checks:
            odoo_qc_id = qc.get("id")
            qc_name = str(qc.get("name") or f"Quality Check {odoo_qc_id}")[:100]
            qo_number = f"ODOO_QC_{odoo_qc_id}"

            # Product resolution
            prod_odoo_id = self._resolve_odoo_id(qc.get("product_id"))
            product = product_map.get(prod_odoo_id) if prod_odoo_id else None
            if not product:
                result.warnings.append(f"Skipped QC {qo_number}: product not resolved")
                continue

            # Quality state → status + disposition
            quality_state = str(qc.get("quality_state", "none")).strip().lower()
            if quality_state == "pass":
                status = "CLOSED"
                disposition = "ACCEPT"
            elif quality_state == "fail":
                status = "DISPOSITION_DECIDED"
                disposition = "REJECT"
            else:
                status = "INSPECTION_PENDING"
                disposition = None

            # Quantity: Odoo quality.check has a 'measure' field for measured value
            inspection_qty = 1.0
            try:
                inspection_qty = float(qc.get("qty_inspected") or qc.get("measure") or 1.0)
            except (TypeError, ValueError):
                pass

            accepted_qty = inspection_qty if disposition == "ACCEPT" else 0.0
            rejected_qty = inspection_qty if disposition == "REJECT" else 0.0

            # Inspection type: infer from picking presence
            picking_id = self._resolve_odoo_id(qc.get("picking_id"))
            inspection_type = "INCOMING" if picking_id else "SAMPLING"

            # Origin
            origin_type = "GOODS_RECEIPT" if picking_id else "PREVENTIVE_SAMPLE"
            origin_order_id = str(picking_id) if picking_id else None

            # Lot/batch
            lot_raw = qc.get("lot_id")
            lot_name = None
            if isinstance(lot_raw, (list, tuple)) and len(lot_raw) >= 2:
                lot_name = str(lot_raw[1])[:100]

            today = datetime.utcnow().date()

            qo_rec = QualityOrder(
                quality_order_number=qo_number,
                company_id=f"ODOO_{self.tenant_id}",
                site_id=fallback_site_id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                source="ODOO",
                source_event_id=f"QC-{odoo_qc_id}",
                source_update_dttm=datetime.utcnow(),
                inspection_type=inspection_type,
                status=status,
                origin_type=origin_type,
                origin_order_id=origin_order_id,
                product_id=product.id,
                lot_number=lot_name,
                inspection_quantity=inspection_qty,
                accepted_quantity=accepted_qty,
                rejected_quantity=rejected_qty,
                disposition=disposition,
                order_date=today,
            )
            self.db.add(qo_rec)
            count += 1

        await self.db.flush()
        result.quality_checks_created = count
        logger.info("Odoo: created %d quality orders from quality.check", count)

    # ── Step 10e: Maintenance Requests ───────────────────────────────────

    async def _build_maintenance_requests(
        self, config, maintenance_requests, site_map, result,
    ):
        """Build MaintenanceOrder from Odoo maintenance.request records.

        Odoo ``maintenance.request`` fields used:
            name, equipment_id, maintenance_type (corrective/preventive),
            priority ('0'-'3'), schedule_date, stage_id, request_date.
        """
        from app.models.maintenance_order import MaintenanceOrder

        if not maintenance_requests:
            return

        fallback_site_id = self._get_first_site_id(site_map)
        if not fallback_site_id:
            result.warnings.append("No site available for maintenance requests — skipped")
            return

        count = 0
        for mr in maintenance_requests:
            odoo_mr_id = mr.get("id")
            mr_name = str(mr.get("name") or f"Maintenance Request {odoo_mr_id}")[:200]
            mo_number = f"ODOO_MR_{odoo_mr_id}"

            # Equipment
            equipment_raw = mr.get("equipment_id")
            equipment_name = None
            equipment_id_str = f"ODOO_EQ_{odoo_mr_id}"
            if isinstance(equipment_raw, (list, tuple)) and len(equipment_raw) >= 2:
                equipment_id_str = f"ODOO_EQ_{equipment_raw[0]}"
                equipment_name = str(equipment_raw[1])[:200]

            # Maintenance type mapping
            odoo_mtype = str(mr.get("maintenance_type", "corrective")).strip().lower()
            mtype_map = {
                "corrective": "CORRECTIVE",
                "preventive": "PREVENTIVE",
            }
            maintenance_type = mtype_map.get(odoo_mtype, "CORRECTIVE")

            # Priority mapping: Odoo uses '0' (very urgent) to '3' (normal)
            odoo_priority = str(mr.get("priority", "1")).strip()
            priority_map = {
                "0": "EMERGENCY",
                "1": "HIGH",
                "2": "NORMAL",
                "3": "LOW",
            }
            priority = priority_map.get(odoo_priority, "NORMAL")

            # Status: infer from stage_id if available, else from kanban_state
            stage_raw = mr.get("stage_id")
            stage_name = ""
            if isinstance(stage_raw, (list, tuple)) and len(stage_raw) >= 2:
                stage_name = str(stage_raw[1]).strip().lower()

            # Map common Odoo maintenance stage names
            if "done" in stage_name or "closed" in stage_name or "repaired" in stage_name:
                status = "COMPLETED"
            elif "progress" in stage_name or "in progress" in stage_name:
                status = "IN_PROGRESS"
            elif "scrap" in stage_name or "cancel" in stage_name:
                status = "CANCELLED"
            else:
                status = "PLANNED"

            # Dates
            request_date = self._parse_odoo_date(mr.get("request_date"))
            schedule_date = self._parse_odoo_date(mr.get("schedule_date"))
            close_date = self._parse_odoo_date(mr.get("close_date"))
            today = datetime.utcnow().date()
            order_date = request_date or today

            scheduled_start = None
            if schedule_date:
                scheduled_start = datetime.combine(schedule_date, datetime.min.time())

            actual_completion = None
            if close_date:
                actual_completion = datetime.combine(close_date, datetime.min.time())

            mo_rec = MaintenanceOrder(
                maintenance_order_number=mo_number,
                asset_id=equipment_id_str[:40],
                asset_name=equipment_name,
                equipment_id=equipment_id_str[:100],
                site_id=fallback_site_id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"ODOO_{self.tenant_id}",
                source="ODOO",
                source_event_id=f"MR-{odoo_mr_id}",
                source_update_dttm=datetime.utcnow(),
                maintenance_type=maintenance_type,
                status=status,
                order_date=order_date,
                scheduled_start_date=scheduled_start,
                actual_completion_date=actual_completion,
                priority=priority,
                work_description=mr_name,
            )
            self.db.add(mo_rec)
            count += 1

        await self.db.flush()
        result.maintenance_requests_created = count
        logger.info("Odoo: created %d maintenance orders from maintenance.request", count)

    # ── Step 11: Forecasts (from sale order line demand history) ─────────

    async def _build_forecasts(self, config, sale_lines, site_map, product_map, result):
        """Build Forecast records from Odoo sale.order.line demand history.

        Odoo Community doesn't have a dedicated forecast module, so we derive
        weekly demand history from ``sale.order.line`` records.  Each
        product-week bucket becomes a forecast row with simple P10/P50/P90
        spread.

        Fields used from ``sale.order.line``:
            product_id, product_uom_qty, order_id (→ sale.order.date_order via
            inline ``date_order`` if flattened, otherwise we fall back to today).
        """
        from app.models.sc_entities import Forecast

        if not sale_lines:
            logger.info("Odoo: no sale.order.line records — skipping forecast generation")
            return

        fallback_site_id = self._get_first_site_id(site_map)
        if fallback_site_id is None:
            result.warnings.append("No internal site available for forecast assignment")
            return

        # Group sale lines by (product_id, iso_week) → sum quantities
        # week_key = (product_odoo_id, year, iso_week)
        weekly_demand: Dict[tuple, float] = {}
        week_dates: Dict[tuple, date] = {}  # track Monday of each week

        for line in sale_lines:
            prod_odoo_id = self._resolve_odoo_id(line.get("product_id"))
            if prod_odoo_id is None:
                continue

            product = product_map.get(prod_odoo_id)
            if not product:
                continue

            qty = 0.0
            try:
                qty = float(line.get("product_uom_qty") or 0)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue

            # Determine order date — flattened extracts may include date_order
            order_date = self._parse_odoo_date(line.get("date_order"))
            if not order_date:
                order_date = datetime.utcnow().date()

            iso_year, iso_week, _ = order_date.isocalendar()
            key = (prod_odoo_id, iso_year, iso_week)
            weekly_demand[key] = weekly_demand.get(key, 0.0) + qty

            # Store the Monday of this ISO week for the forecast_date
            if key not in week_dates:
                monday = order_date - timedelta(days=order_date.weekday())
                week_dates[key] = monday

        count = 0
        for (prod_odoo_id, iso_year, iso_week), total_qty in weekly_demand.items():
            product = product_map.get(prod_odoo_id)
            if not product:
                continue

            p50 = total_qty
            p10 = round(p50 * 0.8, 4)
            p90 = round(p50 * 1.2, 4)
            forecast_date = week_dates[(prod_odoo_id, iso_year, iso_week)]

            fcst = Forecast(
                config_id=config.id,
                company_id=str(self.tenant_id),
                product_id=product.id,
                site_id=fallback_site_id,
                forecast_date=forecast_date,
                forecast_type="statistical",
                forecast_level="product",
                forecast_method="demand_history",
                forecast_quantity=p50,
                forecast_p10=p10,
                forecast_p50=p50,
                forecast_median=p50,
                forecast_p90=p90,
                is_active="true",
                source="ODOO",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(fcst)
            count += 1

        await self.db.flush()
        result.forecasts_created = count
        logger.info("Odoo: created %d forecast records from sale.order.line demand history", count)

    # ── Step 12a: Product enrichment from product.template ────────────

    async def _enrich_products_with_templates(
        self, products, templates, product_map, result,
    ):
        """Enrich Product records with attributes from product.template.

        Odoo ``product.product`` inherits from ``product.template``.  The
        template carries weight, volume, and category information that may
        not be present on the variant record.

        Fields used from ``product.template``:
            id, weight, volume, categ_id, type (consu/service/product),
            tracking (none/lot/serial).

        For each product.product whose ``product_tmpl_id`` matches a
        template, we back-fill ``weight``, ``volume``, ``product_type``,
        and ``category`` if they are not already set.
        """
        if not templates or not product_map:
            return

        # Build template lookup: template_id → template dict
        tmpl_by_id: Dict[int, dict] = {t["id"]: t for t in templates}

        count = 0
        for prod_rec in products:
            odoo_id = prod_rec.get("id")
            product = product_map.get(odoo_id)
            if not product:
                continue

            tmpl_id = self._resolve_odoo_id(prod_rec.get("product_tmpl_id"))
            tmpl = tmpl_by_id.get(tmpl_id) if tmpl_id else None
            if not tmpl:
                continue

            changed = False

            # Weight
            tmpl_weight = tmpl.get("weight")
            if tmpl_weight and not product.weight:
                try:
                    product.weight = float(tmpl_weight)
                    product.weight_uom = "kg"
                    changed = True
                except (TypeError, ValueError):
                    pass

            # Volume
            tmpl_volume = tmpl.get("volume")
            if tmpl_volume and not product.volume:
                try:
                    product.volume = float(tmpl_volume)
                    product.volume_uom = "m3"
                    changed = True
                except (TypeError, ValueError):
                    pass

            # Product type from template type field
            tmpl_type = tmpl.get("type")
            if tmpl_type and not product.product_type:
                type_map = {
                    "consu": "consumable",
                    "product": "stockable",
                    "service": "service",
                }
                mapped = type_map.get(str(tmpl_type).strip().lower())
                if mapped:
                    product.product_type = mapped
                    changed = True

            # Category enrichment from template categ_id
            tmpl_categ = tmpl.get("categ_id")
            if isinstance(tmpl_categ, (list, tuple)) and len(tmpl_categ) >= 2:
                categ_name = str(tmpl_categ[1])
                if categ_name and not product.category:
                    product.category = categ_name[:100]
                    changed = True

            if changed:
                count += 1

        if count:
            await self.db.flush()
        result.products_enriched_template = count
        logger.info("Odoo: enriched %d products from product.template", count)

    # ── Step 12b: Product UoM enrichment from uom.uom + uom.category ─

    async def _enrich_products_with_uom(
        self, products, uom_records, uom_categories, product_map, result,
    ):
        """Enrich Product.base_uom from Odoo uom.uom definitions.

        Odoo ``product.product`` has a ``uom_id`` Many2one pointing to
        ``uom.uom``.  The UoM record carries the standard name (e.g.
        "Units", "kg", "Liters") and belongs to a ``uom.category``
        (e.g. "Unit", "Weight", "Volume").

        Fields used from ``uom.uom``: id, name, category_id, uom_type.
        Fields used from ``uom.category``: id, name.
        """
        if not uom_records or not product_map:
            return

        # Build UoM lookup
        uom_by_id: Dict[int, dict] = {u["id"]: u for u in uom_records}

        # Build category lookup for context
        cat_by_id: Dict[int, str] = {}
        for cat in (uom_categories or []):
            cat_by_id[cat["id"]] = str(cat.get("name", ""))

        # Standard Odoo UoM name → short code mapping
        uom_short: Dict[str, str] = {
            "units": "EA", "unit": "EA", "unit(s)": "EA",
            "dozen": "DZ", "dozen(s)": "DZ",
            "kg": "KG", "kilogram": "KG",
            "g": "G", "gram": "G",
            "lb": "LB", "lbs": "LB", "pound": "LB",
            "oz": "OZ", "ounce": "OZ",
            "t": "MT", "ton": "MT", "tonne": "MT",
            "l": "L", "liter": "L", "litre": "L",
            "ml": "ML", "milliliter": "ML",
            "gal": "GAL", "gallon": "GAL",
            "m": "M", "meter": "M", "metre": "M",
            "cm": "CM", "centimeter": "CM",
            "mm": "MM", "millimeter": "MM",
            "in": "IN", "inch": "IN",
            "ft": "FT", "foot": "FT",
            "m2": "M2", "m3": "M3",
            "hour": "HR", "hours": "HR",
            "day": "DAY", "days": "DAY",
            "pair": "PR",
            "box": "BX", "case": "CS", "pallet": "PAL",
            "pack": "PK",
        }

        count = 0
        for prod_rec in products:
            odoo_id = prod_rec.get("id")
            product = product_map.get(odoo_id)
            if not product:
                continue

            # Already has base_uom — skip
            if product.base_uom:
                continue

            uom_id = self._resolve_odoo_id(prod_rec.get("uom_id"))
            uom = uom_by_id.get(uom_id) if uom_id else None
            if not uom:
                continue

            uom_name = str(uom.get("name", "")).strip()
            short = uom_short.get(uom_name.lower())
            if short:
                product.base_uom = short
            elif uom_name:
                # Use first 20 chars of the raw name as fallback
                product.base_uom = uom_name[:20]
            else:
                continue

            count += 1

        if count:
            await self.db.flush()
        result.products_enriched_uom = count
        logger.info("Odoo: enriched %d products with UoM from uom.uom", count)

    # ── Step 12c: Product lot tracking from stock.lot ─────────────────

    async def _enrich_products_with_lots(self, lots, product_map, result):
        """Flag products that have lot/serial tracking from stock.lot records.

        If a product appears in ``stock.lot``, it uses lot or serial
        tracking.  We set ``item_type`` to ``"lot_tracked"`` (if not
        already set) so downstream systems know to expect lot-level
        inventory.

        Fields used from ``stock.lot``:
            product_id — the product variant using lot/serial tracking.
        """
        if not lots or not product_map:
            return

        # Collect product IDs that have lot records
        lot_product_ids: Set[int] = set()
        for lot in lots:
            pid = self._resolve_odoo_id(lot.get("product_id"))
            if pid is not None:
                lot_product_ids.add(pid)

        count = 0
        for odoo_pid in lot_product_ids:
            product = product_map.get(odoo_pid)
            if not product:
                continue
            if product.item_type:
                continue  # already classified

            product.item_type = "lot_tracked"
            count += 1

        if count:
            await self.db.flush()
        result.products_enriched_lots = count
        logger.info("Odoo: flagged %d products as lot-tracked from stock.lot", count)

    # ── Step 12d: Routing operations → production_process ─────────────

    async def _build_routing(
        self, config, routing_operations, boms, workcenters,
        site_map, product_map, result,
    ):
        """Build ProductionProcess records from mrp.routing.workcenter.

        Odoo ``mrp.routing.workcenter`` defines individual routing
        operations (steps) in a manufacturing process.  Each operation
        links to a BOM (via ``bom_id``) and a work centre (via
        ``workcenter_id``), carrying operation time, setup time, and
        sequence.

        Fields used from ``mrp.routing.workcenter``:
            id, bom_id, workcenter_id, name, sequence, time_cycle_manual,
            time_mode ('auto'/'manual'), time_mode_batch, worksheet_type.

        Fields used from ``mrp.workcenter`` (already extracted):
            id, name, capacity, time_efficiency, oee_target.
        """
        from app.models.sc_entities import ProductionProcess

        if not routing_operations:
            return

        # Work centre lookup: wc_id → wc record
        wc_by_id: Dict[int, dict] = {}
        for wc in (workcenters or []):
            wc_by_id[wc["id"]] = wc

        # BOM → product template mapping (reuse from _build_manufacturing)
        bom_product_map: Dict[int, int] = {}
        for bom in (boms or []):
            tmpl_id = bom.get("product_tmpl_id")
            if isinstance(tmpl_id, (list, tuple)):
                tmpl_id = tmpl_id[0]
            bom_product_map[bom["id"]] = tmpl_id

        # Fallback site for production processes
        fallback_site_id = self._get_first_site_id(site_map)
        if not fallback_site_id:
            result.warnings.append("No site available for routing operations — skipped")
            return

        count = 0
        for op in routing_operations:
            odoo_op_id = op.get("id")
            op_name = str(op.get("name") or f"Operation {odoo_op_id}")[:200]

            bom_id = self._resolve_odoo_id(op.get("bom_id"))
            wc_id = self._resolve_odoo_id(op.get("workcenter_id"))
            wc = wc_by_id.get(wc_id) if wc_id else None

            # Resolve work centre capacity for description
            wc_name = ""
            if wc:
                wc_name = str(wc.get("name", ""))

            # Operation time in minutes → convert to hours for ProductionProcess
            time_cycle = 0.0
            try:
                time_cycle = float(op.get("time_cycle_manual") or op.get("time_cycle") or 0)
            except (TypeError, ValueError):
                pass
            operation_time_hours = round(time_cycle / 60.0, 4) if time_cycle else None

            # Setup time is not a standard field on mrp.routing.workcenter,
            # but some Odoo installations add it.  Fall back to the work
            # centre's default setup time if present.
            setup_time_raw = op.get("setup_time") or (wc.get("setup_time") if wc else None)
            setup_time_hours = None
            if setup_time_raw:
                try:
                    setup_time_hours = round(float(setup_time_raw) / 60.0, 4)
                except (TypeError, ValueError):
                    pass

            # Yield from work centre efficiency (percentage → fraction)
            yield_pct = None
            if wc:
                eff = wc.get("time_efficiency")
                if eff:
                    try:
                        yield_pct = float(eff)  # Odoo stores as 100.0 = 100%
                    except (TypeError, ValueError):
                        pass

            # Lot size from batch mode
            lot_size = None
            try:
                batch = op.get("time_mode_batch")
                if batch:
                    lot_size = float(batch)
            except (TypeError, ValueError):
                pass

            sequence = op.get("sequence", 0)
            process_id = f"ODOO_RTE_{odoo_op_id}"

            pp = ProductionProcess(
                id=process_id,
                description=f"{op_name} @ {wc_name}".strip()[:500],
                company_id=f"ODOO_{self.tenant_id}",
                site_id=fallback_site_id,
                config_id=config.id,
                process_type=f"routing_step_{sequence}",
                operation_time=operation_time_hours,
                setup_time=setup_time_hours,
                lot_size=lot_size,
                yield_percentage=yield_pct,
                is_active="true",
                source="ODOO",
                source_event_id=f"RTE-{odoo_op_id}",
                source_update_dttm=datetime.utcnow(),
            )
            self.db.add(pp)
            count += 1

        await self.db.flush()
        result.routing_operations_created = count
        logger.info("Odoo: created %d production_process records from mrp.routing.workcenter", count)

    # ── Step 12e: Maintenance equipment enrichment ────────────────────

    async def _enrich_maintenance_with_equipment(
        self, config, equipment_records, result,
    ):
        """Enrich MaintenanceOrder records with asset details from maintenance.equipment.

        Odoo ``maintenance.equipment`` carries the asset master (name,
        category, serial, partner, technician).  Existing maintenance
        orders reference equipment via ``equipment_id`` Many2one.  This
        method back-fills ``asset_type`` and ``asset_name`` on
        MaintenanceOrder records that were created in
        ``_build_maintenance_requests()``.

        Fields used from ``maintenance.equipment``:
            id, name, category_id (→ equipment type), serial_no,
            partner_id (vendor), technician_user_id, location.
        """
        from app.models.maintenance_order import MaintenanceOrder
        from sqlalchemy import select as sa_select

        if not equipment_records:
            return

        # Build equipment lookup: "ODOO_EQ_{id}" → equipment dict
        eq_by_key: Dict[str, dict] = {}
        for eq in equipment_records:
            eq_id = eq.get("id")
            eq_by_key[f"ODOO_EQ_{eq_id}"] = eq

        if not eq_by_key:
            return

        # Load existing maintenance orders for this config
        stmt = sa_select(MaintenanceOrder).where(
            MaintenanceOrder.config_id == config.id,
            MaintenanceOrder.source == "ODOO",
        )
        existing_orders = (await self.db.execute(stmt)).scalars().all()

        count = 0
        for mo in existing_orders:
            eq_key = mo.equipment_id
            if not eq_key or eq_key not in eq_by_key:
                continue

            eq = eq_by_key[eq_key]
            changed = False

            # Asset type from equipment category
            categ = eq.get("category_id")
            if isinstance(categ, (list, tuple)) and len(categ) >= 2:
                categ_name = str(categ[1])[:100]
                if categ_name and not mo.asset_type:
                    mo.asset_type = categ_name
                    changed = True

            # Asset name from equipment name (if not already set or generic)
            eq_name = eq.get("name")
            if eq_name and (not mo.asset_name or mo.asset_name == mo.equipment_id):
                mo.asset_name = str(eq_name)[:200]
                changed = True

            # Serial number enrichment via extra_data (no dedicated column)
            serial_no = eq.get("serial_no")
            location = eq.get("location")
            if serial_no or location:
                extra = {}
                if serial_no:
                    extra["equipment_serial"] = str(serial_no)[:100]
                if location:
                    extra["equipment_location"] = str(location)[:200]
                # Merge into existing notes if available
                if mo.work_description and extra:
                    # Append equipment context to notes
                    suffix_parts = []
                    if serial_no:
                        suffix_parts.append(f"S/N: {serial_no}")
                    if location:
                        suffix_parts.append(f"Location: {location}")
                    suffix = " | ".join(suffix_parts)
                    if suffix not in (mo.work_description or ""):
                        mo.work_description = f"{mo.work_description} [{suffix}]"[:500]
                        changed = True

            if changed:
                count += 1

        if count:
            await self.db.flush()
        result.maintenance_enriched_equipment = count
        logger.info("Odoo: enriched %d maintenance orders from maintenance.equipment", count)

    # ── Step 12f: Quality alerts → quality_order records ──────────────

    async def _enrich_quality_with_alerts(
        self, config, quality_alerts, site_map, product_map, result,
    ):
        """Create additional QualityOrder records from Odoo quality.alert.

        Odoo Enterprise has two quality models:
        - ``quality.check`` — individual inspection checks (handled in Step 10d)
        - ``quality.alert`` — escalated quality issues requiring disposition

        Alerts represent a higher severity than routine checks and map
        to QualityOrder records with ``inspection_type='COMPLAINT'`` or
        ``'RETURNS'``.

        Fields used from ``quality.alert``:
            id, name, product_id, product_tmpl_id, lot_id, team_id,
            stage_id (kanban stage), priority, description, reason.
        """
        from app.models.quality_order import QualityOrder

        if not quality_alerts:
            return

        fallback_site_id = self._get_first_site_id(site_map)
        if not fallback_site_id:
            result.warnings.append("No site available for quality alerts — skipped")
            return

        count = 0
        for alert in quality_alerts:
            odoo_alert_id = alert.get("id")
            alert_name = str(alert.get("name") or f"Quality Alert {odoo_alert_id}")[:100]
            qo_number = f"ODOO_QA_{odoo_alert_id}"

            # Product resolution: try product_id first, then product_tmpl_id
            prod_odoo_id = self._resolve_odoo_id(alert.get("product_id"))
            product = product_map.get(prod_odoo_id) if prod_odoo_id else None
            if not product:
                tmpl_id = self._resolve_odoo_id(alert.get("product_tmpl_id"))
                if tmpl_id:
                    product = product_map.get(tmpl_id)
            if not product:
                result.warnings.append(f"Skipped QA {qo_number}: product not resolved")
                continue

            # Stage → status mapping
            stage_raw = alert.get("stage_id")
            stage_name = ""
            if isinstance(stage_raw, (list, tuple)) and len(stage_raw) >= 2:
                stage_name = str(stage_raw[1]).strip().lower()

            if "done" in stage_name or "closed" in stage_name:
                status = "CLOSED"
                disposition = "ACCEPT"
            elif "progress" in stage_name:
                status = "DISPOSITION_DECIDED"
                disposition = "REWORK"
            else:
                status = "INSPECTION_PENDING"
                disposition = None

            # Priority mapping: Odoo alerts use '0' (normal) to '3' (very urgent)
            odoo_priority = str(alert.get("priority", "0")).strip()
            # Invert: higher number = more urgent in Odoo alerts
            priority_map = {
                "0": "STANDARD",
                "1": "HIGH",
                "2": "URGENT",
                "3": "CRITICAL",
            }
            # Not used directly on QualityOrder, but noted in the reason field

            # Lot/batch
            lot_raw = alert.get("lot_id")
            lot_name = None
            if isinstance(lot_raw, (list, tuple)) and len(lot_raw) >= 2:
                lot_name = str(lot_raw[1])[:100]

            # Reason / description
            reason = str(alert.get("reason") or alert.get("description") or "")[:500]
            alert_priority = priority_map.get(odoo_priority, "STANDARD")
            today = datetime.utcnow().date()

            qo_rec = QualityOrder(
                quality_order_number=qo_number,
                company_id=f"ODOO_{self.tenant_id}",
                site_id=fallback_site_id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                source="ODOO",
                source_event_id=f"QA-{odoo_alert_id}",
                source_update_dttm=datetime.utcnow(),
                inspection_type="COMPLAINT",
                status=status,
                origin_type="CUSTOMER_COMPLAINT",
                product_id=product.id,
                lot_number=lot_name,
                inspection_quantity=1.0,
                accepted_quantity=1.0 if disposition == "ACCEPT" else 0.0,
                rejected_quantity=1.0 if disposition not in ("ACCEPT", "REWORK", None) else 0.0,
                disposition=disposition,
                order_date=today,
                notes=f"[{alert_priority}] {reason}".strip()[:500] if reason else None,
            )
            self.db.add(qo_rec)
            count += 1

        await self.db.flush()
        result.quality_alerts_created = count
        logger.info("Odoo: created %d quality orders from quality.alert", count)


class OdooIngestionMonitor:
    """Monitors Odoo ingestion quality — mirrors SAP ingestion monitoring.

    Tracks:
    - Extraction job status and history
    - Data quality metrics (completeness, referential integrity)
    - Model coverage statistics
    """

    @staticmethod
    def compute_quality_metrics(data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Compute data quality metrics across all extracted models."""
        metrics = {}
        total_records = 0
        total_complete = 0

        for model, records in data.items():
            if not records:
                metrics[model] = {"count": 0, "completeness": 0.0}
                continue

            count = len(records)
            total_records += count

            # Completeness: % of non-null fields across all records
            total_fields = 0
            non_null_fields = 0
            for rec in records:
                for k, v in rec.items():
                    total_fields += 1
                    if v is not None and v is not False and v != "":
                        non_null_fields += 1

            completeness = non_null_fields / total_fields if total_fields else 0
            total_complete += completeness * count

            metrics[model] = {
                "count": count,
                "completeness": round(completeness * 100, 1),
                "fields_per_record": total_fields // count if count else 0,
            }

        overall = total_complete / total_records if total_records else 0
        return {
            "models": metrics,
            "total_records": total_records,
            "total_models": len(data),
            "overall_completeness": round(overall * 100, 1),
        }

    # ------------------------------------------------------------------
    # Derivation Fallbacks
    # ------------------------------------------------------------------

    async def _derive_transfer_orders_from_pickings(
        self, config, data, site_map, product_map, result,
    ):
        """Derive TOs from stock.picking records when no explicit internal transfers exist.

        Odoo uses stock.picking with picking_type_code='internal' for transfers.
        If no internal pickings were found, look for stock.move between internal
        locations and create synthetic TOs.
        """
        from app.models.transfer_order import TransferOrder, TransferOrderLineItem
        from datetime import datetime, timedelta

        stock_moves = data.get("stock.move", [])
        if not stock_moves:
            return 0

        # Get internal site IDs
        internal_site_ids = set()
        for site_key, site in site_map.items():
            internal_site_ids.add(site.id)

        if len(internal_site_ids) < 2:
            return 0

        count = 0
        today = datetime.utcnow().date()
        seen_pairs = set()

        for move in stock_moves:
            # Check if this is an internal move between warehouses
            location_id = move.get("location_id")
            location_dest_id = move.get("location_dest_id")

            # Resolve warehouse from location
            from_wh = move.get("warehouse_id")
            to_wh = move.get("warehouse_dest_id")

            if from_wh and to_wh and from_wh != to_wh:
                from_wh_str = str(from_wh[0] if isinstance(from_wh, (list, tuple)) else from_wh)
                to_wh_str = str(to_wh[0] if isinstance(to_wh, (list, tuple)) else to_wh)

                from_site = site_map.get(from_wh_str)
                to_site = site_map.get(to_wh_str)

                if (from_site and to_site
                        and from_site.id in internal_site_ids
                        and to_site.id in internal_site_ids):
                    pair_key = (from_wh_str, to_wh_str)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    to_order = TransferOrder(
                        to_number=f"ODOO_TO_DERIVED_{from_wh_str}_{to_wh_str}",
                        source_site_id=from_site.id,
                        destination_site_id=to_site.id,
                        config_id=config.id,
                        tenant_id=self.tenant_id,
                        company_id=f"ODOO_{self.tenant_id}",
                        order_type="transfer",
                        source="ODOO_DERIVED",
                        status="DONE",
                        order_date=today,
                        shipment_date=today,
                        estimated_delivery_date=today + timedelta(days=1),
                        notes=f"Derived from stock.move: WH {from_wh_str} → WH {to_wh_str}",
                    )
                    self.db.add(to_order)
                    await self.db.flush()
                    count += 1
                    result.transfer_orders_created += 1

        await self.db.flush()
        logger.info("Odoo: derived %d transfer orders from stock.move data", count)
        return count

    async def _run_derivation_fallbacks(self, config, data, site_map, product_map, result):
        """Run derivation fallbacks for empty Odoo models."""
        derived = {}

        # Transfer orders: if no internal pickings found, try stock.move
        if result.transfer_orders_created == 0:
            count = await self._derive_transfer_orders_from_pickings(
                config, data, site_map, product_map, result,
            )
            if count > 0:
                derived["transfer_orders_from_stock_moves"] = count

        return derived

    def _build_extraction_audit(self, config, data, result, derived_counts):
        """Build extraction audit report for Odoo config build."""
        from app.services.extraction_audit_service import ExtractionAuditReport

        audit = ExtractionAuditReport(config_id=config.id, erp_type="Odoo")

        # Record all Odoo models
        for model_name, records in data.items():
            row_count = len(records) if records else 0
            if row_count > 0:
                audit.record_extracted(model_name, row_count)
            else:
                audit.record_empty(model_name)

        # Record entity counts
        for attr in [
            "sites_created", "products_created", "lanes_created", "boms_created",
            "trading_partners_created", "purchase_orders_created",
            "outbound_orders_created", "production_orders_created",
            "goods_receipts_created", "shipments_created",
            "transfer_orders_created", "quality_checks_created",
            "maintenance_requests_created", "forecasts_created",
        ]:
            count = getattr(result, attr, 0)
            if count > 0:
                audit.record_extracted(f"entity:{attr}", count)

        # Record derivations
        for key, count in derived_counts.items():
            audit.record_derived(
                f"derived:{key}", count,
                source="stock.move (internal warehouse moves)",
                note="No internal stock.picking found — derived TOs from stock.move data",
            )

        return audit

    @staticmethod
    def compute_referential_integrity(data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Check referential integrity across Odoo models.

        Validates that FK references (product_id, partner_id, etc.) point
        to records that exist in the extracted dataset.
        """
        # Build ID sets
        product_ids = {r["id"] for r in data.get("product.product", [])}
        partner_ids = {r["id"] for r in data.get("res.partner", [])}
        warehouse_ids = {r["id"] for r in data.get("stock.warehouse", [])}
        bom_ids = {r["id"] for r in data.get("mrp.bom", [])}

        issues = []

        # Check BOM lines reference valid products
        for line in data.get("mrp.bom.line", []):
            pid = line.get("product_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in product_ids:
                issues.append(f"mrp.bom.line {line.get('id')}: product_id {pid} not found")

        # Check PO lines reference valid products
        for line in data.get("purchase.order.line", []):
            pid = line.get("product_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in product_ids:
                issues.append(f"purchase.order.line {line.get('id')}: product_id {pid} not found")

        # Check supplier info references valid partners
        for si in data.get("product.supplierinfo", []):
            pid = si.get("partner_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in partner_ids:
                issues.append(f"product.supplierinfo {si.get('id')}: partner_id {pid} not found")

        return {
            "total_checks": len(data.get("mrp.bom.line", [])) +
                           len(data.get("purchase.order.line", [])) +
                           len(data.get("product.supplierinfo", [])),
            "issues": issues[:50],  # cap for readability
            "issue_count": len(issues),
            "integrity_score": round(
                (1 - len(issues) / max(1, sum(len(v) for v in data.values()))) * 100, 1
            ),
        }

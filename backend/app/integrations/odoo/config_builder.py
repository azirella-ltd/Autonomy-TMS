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
from typing import Dict, List, Optional, Any, Set
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

        # Warehouses → INVENTORY or MANUFACTURER (internal sites only)
        for wh in warehouses:
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
        for prod in products:
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
        """Step 7: Build BOM structures."""
        from app.models.sc_entities import ProductBOM

        bom_product_map: Dict[int, int] = {}
        for bom in boms:
            tmpl_id = bom.get("product_tmpl_id")
            if isinstance(tmpl_id, (list, tuple)):
                tmpl_id = tmpl_id[0]
            bom_product_map[bom["id"]] = tmpl_id

        for line in bom_lines:
            bom_id = line.get("bom_id")
            if isinstance(bom_id, (list, tuple)):
                bom_id = bom_id[0]

            component_id = line.get("product_id")
            if isinstance(component_id, (list, tuple)):
                component_id = component_id[0]

            parent_tmpl_id = bom_product_map.get(bom_id)
            if not parent_tmpl_id:
                continue

            # Find platform product for parent and component
            parent = product_map.get(parent_tmpl_id)
            component = product_map.get(component_id)
            if not parent or not component:
                continue

            bom_rec = ProductBOM(
                config_id=config.id,
                parent_product_id=parent.id,
                child_product_id=component.id,
                quantity_per=line.get("product_qty", 1.0),
            )
            self.db.add(bom_rec)
            result.boms_created += 1

    async def _build_inventory(self, config, quants, orderpoints, site_map, product_map, result):
        """Step 8: Build inventory levels and policies."""
        from app.models.aws_sc_planning import InvLevel, InvPolicy

        # Inventory levels from stock.quant
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

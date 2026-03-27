"""
D365 Config Builder — Reverse ETL

Transforms extracted D365 F&O data into an Autonomy SupplyChainConfig.
Follows the same pipeline pattern as ``sap_config_builder.py`` and
``odoo/config_builder.py``.

Key D365 entities → Autonomy mapping:

Master data:
- LegalEntities          → Tenant/Company
- OperationalSites       → Site (INVENTORY/MANUFACTURER)
- Warehouses             → Site attributes
- StorageLocations       → Site sub-locations
- ReleasedProductsV2     → Product
- ProductCategoryHierarchies → ProductHierarchyNode (tree containers)
- ProductCategories      → ProductHierarchyNode (tree nodes)
- ItemCoverageSettings   → SitePlanningConfig + InvPolicy

Transactional data:
- PurchaseOrderHeadersV2 / PurchaseOrderLinesV2 → PurchaseOrder + PurchaseOrderLineItem
- SalesOrderHeadersV2 / SalesOrderLinesV2       → OutboundOrder + OutboundOrderLine
- ProductionOrderHeaders                         → ProductionOrder
- DemandForecastEntries                          → Forecast
"""

import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class D365ConfigBuildResult:
    """Result of building a SupplyChainConfig from D365 data."""
    success: bool = True
    config_id: Optional[int] = None
    sites_created: int = 0
    products_created: int = 0
    site_hierarchy_nodes: int = 0
    product_hierarchy_nodes: int = 0
    lanes_created: int = 0
    boms_created: int = 0
    trading_partners_created: int = 0
    inv_levels_created: int = 0
    inv_policies_created: int = 0
    purchase_orders_created: int = 0
    purchase_order_lines_created: int = 0
    outbound_orders_created: int = 0
    outbound_order_lines_created: int = 0
    production_orders_created: int = 0
    forecasts_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class D365ConfigBuilder:
    """Builds an Autonomy SupplyChainConfig from D365 extracted data.

    Usage:
        builder = D365ConfigBuilder(db, tenant_id=24, config_name="D365 Import")
        result = await builder.build(extracted_data)
    """

    def __init__(self, db, tenant_id: int, config_name: str = "D365 Import"):
        self.db = db
        self.tenant_id = tenant_id
        self.config_name = config_name

    async def build(self, data: Dict[str, List[Dict]]) -> D365ConfigBuildResult:
        """Build SupplyChainConfig from extracted D365 data.

        Args:
            data: Dict mapping D365 entity name → list of records.
                  e.g. {"ReleasedProductsV2": [...], "OperationalSites": [...]}
        """
        result = D365ConfigBuildResult()

        try:
            # Step 1: Create config
            config = await self._get_or_create_config(result)
            if not config:
                result.success = False
                return result
            result.config_id = config.id

            # Step 2: Sites from OperationalSites + Warehouses
            sites_data = data.get("OperationalSites", [])
            warehouses_data = data.get("Warehouses", [])
            site_map = await self._build_sites(config, sites_data, warehouses_data, result)

            # Step 3: Products from ReleasedProductsV2
            products_data = data.get("ReleasedProductsV2", [])
            product_map = await self._build_products(config, products_data, result)

            # Step 4: Hierarchy nodes
            legal_entities = data.get("LegalEntities", [])
            storage_locs = data.get("StorageLocations", [])
            cat_hierarchies = data.get("ProductCategoryHierarchies", [])
            cat_nodes = data.get("ProductCategories", [])
            await self._build_hierarchy_nodes(
                config, legal_entities, sites_data, warehouses_data,
                storage_locs, cat_hierarchies, cat_nodes, product_map, result,
            )

            # Step 5: Trading partners from Vendors + CustomersV3
            vendors = data.get("Vendors", [])
            customers = data.get("CustomersV3", [])
            await self._build_trading_partners(config, vendors, customers, result)

            # Step 6: BOMs
            bom_headers = data.get("BillOfMaterialsHeaders", [])
            bom_lines = data.get("BillOfMaterialsLines", [])
            await self._build_boms(config, bom_headers, bom_lines, product_map, result)

            # Step 7: Inventory & planning
            inv_onhand = data.get("InventWarehouseOnHandEntity", [])
            coverage = data.get("ItemCoverageSettings", [])
            order_setups = data.get("InventItemOrderSetups", [])
            await self._build_inventory(
                config, inv_onhand, coverage, order_setups,
                site_map, product_map, result,
            )

            # Step 8: Purchase orders (inbound)
            po_headers = data.get("PurchaseOrderHeadersV2", [])
            po_lines = data.get("PurchaseOrderLinesV2", [])
            await self._build_purchase_orders(
                config, po_headers, po_lines, site_map, product_map, result,
            )

            # Step 9: Outbound orders (sales)
            so_headers = data.get("SalesOrderHeadersV2", [])
            so_lines = data.get("SalesOrderLinesV2", [])
            await self._build_outbound_orders(
                config, so_headers, so_lines, site_map, product_map, result,
            )

            # Step 10: Production orders
            prod_order_headers = data.get("ProductionOrderHeaders", [])
            await self._build_production_orders(
                config, prod_order_headers, site_map, product_map, result,
            )

            # Step 11: Forecasts
            forecast_entries = data.get("DemandForecastEntries", [])
            await self._build_forecasts(
                config, forecast_entries, site_map, product_map, result,
            )

            await self.db.commit()
            logger.info("D365 config build complete: config_id=%d", config.id)

        except Exception as e:
            await self.db.rollback()
            result.success = False
            result.errors.append(str(e))
            logger.exception("D365 config build failed: %s", e)

        return result

    # ------------------------------------------------------------------
    # Step 1: Config
    # ------------------------------------------------------------------

    async def _get_or_create_config(self, result):
        from app.models.supply_chain_config import SupplyChainConfig
        from app.models.tenant import Tenant

        tenant = (await self.db.execute(
            __import__("sqlalchemy").select(Tenant).where(Tenant.id == self.tenant_id)
        )).scalar_one_or_none()
        if not tenant:
            result.errors.append(f"Tenant {self.tenant_id} not found")
            return None

        config = SupplyChainConfig(
            name=self.config_name,
            tenant_id=self.tenant_id,
            is_active=True,
            scenario_type="PRODUCTION",
        )
        self.db.add(config)
        await self.db.flush()
        return config

    # ------------------------------------------------------------------
    # Step 2: Sites
    # ------------------------------------------------------------------

    async def _build_sites(self, config, sites_data, warehouses_data, result):
        from app.models.supply_chain_config import Site

        site_map: Dict[str, Any] = {}  # SiteId → Site

        for s in sites_data:
            site_id = s.get("SiteId", "")
            site = Site(
                config_id=config.id,
                name=site_id,
                type=s.get("SiteName", site_id),
                master_type="INVENTORY",
                attributes={
                    "d365_site_id": site_id,
                    "d365_site_name": s.get("SiteName", ""),
                },
            )
            self.db.add(site)
            await self.db.flush()
            site_map[site_id] = site
            result.sites_created += 1

        return site_map

    # ------------------------------------------------------------------
    # Step 3: Products
    # ------------------------------------------------------------------

    async def _build_products(self, config, products_data, result):
        from app.models.sc_entities import Product

        product_map: Dict[str, Any] = {}  # ItemNumber → Product

        for p in products_data:
            item_no = p.get("ItemNumber", "")
            product = Product(
                config_id=config.id,
                name=item_no[:100],
                description=p.get("ProductName", item_no)[:255],
                product_type=p.get("ProductType", ""),
                category=p.get("ProductGroupId", ""),
            )
            self.db.add(product)
            await self.db.flush()
            product_map[item_no] = product
            result.products_created += 1

        return product_map

    # ------------------------------------------------------------------
    # Step 4: Hierarchy Nodes
    # ------------------------------------------------------------------

    async def _build_hierarchy_nodes(
        self, config, legal_entities, sites_data, warehouses_data,
        storage_locs, cat_hierarchies, cat_nodes, product_map, result,
    ):
        """Build SiteHierarchyNode and ProductHierarchyNode from D365 data.

        Site hierarchy:  LegalEntity → OperationalSite → Warehouse → StorageLocation
        Product hierarchy: ProductCategoryHierarchy → ProductCategories (tree via ParentCategoryId)
        """
        from app.models.planning_hierarchy import SiteHierarchyNode, ProductHierarchyNode

        tenant_id = self.tenant_id

        # ── SITE HIERARCHY ────────────────────────────────────────────────
        # Root: Legal entity
        le = legal_entities[0] if legal_entities else {}
        company_name = le.get("Name", config.name or "Company")
        root_code = f"D365_LE_{tenant_id}"
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
        result.site_hierarchy_nodes += 1

        # Sites as region-level
        site_nodes: Dict[str, SiteHierarchyNode] = {}
        for s in sites_data:
            sid = s.get("SiteId", "")
            scode = f"D365_SITE_{sid}"
            snode = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=scode,
                name=s.get("SiteName", sid),
                hierarchy_level="REGION",
                hierarchy_path=f"{root_code}/{scode}",
                depth=1,
                parent_id=root.id,
            )
            self.db.add(snode)
            await self.db.flush()
            site_nodes[sid] = snode
            result.site_hierarchy_nodes += 1

        # Warehouses under sites
        wh_nodes: Dict[str, SiteHierarchyNode] = {}
        for wh in warehouses_data:
            wh_id = wh.get("WarehouseId", "")
            wh_site = wh.get("SiteId", "")
            parent = site_nodes.get(wh_site, root)
            wh_code = f"D365_WH_{wh_id}"
            wh_node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=wh_code,
                name=wh.get("WarehouseName", wh_id),
                hierarchy_level="COUNTRY",  # Using COUNTRY level for warehouses
                hierarchy_path=f"{parent.hierarchy_path}/{wh_code}",
                depth=parent.depth + 1,
                parent_id=parent.id,
            )
            self.db.add(wh_node)
            await self.db.flush()
            wh_nodes[wh_id] = wh_node
            result.site_hierarchy_nodes += 1

        # Storage locations under warehouses
        for sl in storage_locs:
            sl_id = sl.get("StorageLocationId", "")
            sl_site = sl.get("SiteId", "")
            sl_wh = sl.get("WarehouseId", "")
            parent = wh_nodes.get(sl_wh) or site_nodes.get(sl_site, root)
            sl_code = f"D365_SL_{sl_site}_{sl_id}"
            sl_node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=sl_code,
                name=sl.get("StorageLocationName", sl_id),
                hierarchy_level="SITE",
                hierarchy_path=f"{parent.hierarchy_path}/{sl_code}",
                depth=parent.depth + 1,
                parent_id=parent.id,
            )
            self.db.add(sl_node)
            result.site_hierarchy_nodes += 1

        await self.db.flush()
        logger.info("D365: created %d site hierarchy nodes", result.site_hierarchy_nodes)

        # ── PRODUCT HIERARCHY ─────────────────────────────────────────────
        if cat_nodes:
            prod_root_code = f"D365_PRODUCTS_{tenant_id}"
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
            result.product_hierarchy_nodes += 1

            # D365 ProductCategories have CategoryId and ParentCategoryId
            cat_by_id: Dict[str, dict] = {
                str(c.get("CategoryId", "")): c for c in cat_nodes
            }
            cat_node_map: Dict[str, ProductHierarchyNode] = {}

            # Sort by hierarchy depth (walk parent chain)
            def _depth(cid, visited=None):
                if visited is None:
                    visited = set()
                if cid in visited:
                    return 0
                visited.add(cid)
                cat = cat_by_id.get(cid)
                if not cat:
                    return 0
                pid = str(cat.get("ParentCategoryId", ""))
                if pid and pid in cat_by_id:
                    return 1 + _depth(pid, visited)
                return 0

            sorted_cats = sorted(cat_nodes, key=lambda c: _depth(str(c.get("CategoryId", ""))))
            level_names = {0: "CATEGORY", 1: "FAMILY", 2: "GROUP"}

            for cat in sorted_cats:
                cid = str(cat.get("CategoryId", ""))
                cname = cat.get("CategoryName", f"Category {cid}")
                pid = str(cat.get("ParentCategoryId", ""))

                parent_node = cat_node_map.get(pid, prod_root)
                depth = parent_node.depth + 1
                hlevel = level_names.get(depth, "GROUP")
                ccode = f"D365_CAT_{cid}"

                node = ProductHierarchyNode(
                    tenant_id=tenant_id,
                    code=ccode,
                    name=cname,
                    hierarchy_level=hlevel,
                    hierarchy_path=f"{parent_node.hierarchy_path}/{ccode}",
                    depth=depth,
                    parent_id=parent_node.id,
                )
                self.db.add(node)
                await self.db.flush()
                cat_node_map[cid] = node
                result.product_hierarchy_nodes += 1

            logger.info("D365: created %d product hierarchy nodes", result.product_hierarchy_nodes)

    # ------------------------------------------------------------------
    # Step 5: Trading Partners
    # ------------------------------------------------------------------

    async def _build_trading_partners(self, config, vendors, customers, result):
        from app.models.sc_entities import TradingPartner

        for v in vendors:
            tp = TradingPartner(
                id=f"D365_V_{v.get('VendorAccountNumber', '')}",
                tpartner_type="vendor",
                description=v.get("VendorOrganizationName", v.get("VendorAccountNumber", ""))[:200],
                company_id=f"D365_{self.tenant_id}",
                source="D365",
            )
            self.db.add(tp)
            result.trading_partners_created += 1

        for c in customers:
            tp = TradingPartner(
                id=f"D365_C_{c.get('CustomerAccount', '')}",
                tpartner_type="customer",
                description=c.get("CustomerName", c.get("CustomerAccount", ""))[:200],
                company_id=f"D365_{self.tenant_id}",
                source="D365",
            )
            self.db.add(tp)
            result.trading_partners_created += 1

        await self.db.flush()

    # ------------------------------------------------------------------
    # Step 6: BOMs
    # ------------------------------------------------------------------

    async def _build_boms(self, config, bom_headers, bom_lines, product_map, result):
        from app.models.sc_entities import ProductBom

        header_map = {h.get("BOMId"): h for h in bom_headers}

        for line in bom_lines:
            bom_id = line.get("BOMId")
            header = header_map.get(bom_id, {})
            parent_item = header.get("ItemNumber", "")
            child_item = line.get("ItemNumber", "")
            parent_prod = product_map.get(parent_item)
            child_prod = product_map.get(child_item)
            if parent_prod and child_prod:
                bom = ProductBom(
                    product_id=parent_prod.id,
                    component_product_id=child_prod.id,
                    quantity=float(line.get("Quantity", 1)),
                    config_id=config.id,
                )
                self.db.add(bom)
                result.boms_created += 1

        await self.db.flush()

    # ------------------------------------------------------------------
    # Step 7: Inventory & Planning
    # ------------------------------------------------------------------

    async def _build_inventory(
        self, config, inv_onhand, coverage, order_setups,
        site_map, product_map, result,
    ):
        from app.models.sc_entities import InvLevel, InvPolicy

        # On-hand inventory
        for inv in inv_onhand:
            item = inv.get("ItemNumber", "")
            product = product_map.get(item)
            if not product:
                continue
            level = InvLevel(
                product_id=product.id,
                config_id=config.id,
                on_hand_quantity=float(inv.get("AvailableOnHandQuantity", 0)),
                source="D365",
            )
            self.db.add(level)
            result.inv_levels_created += 1

        # Coverage settings → inventory policies
        for cs in coverage:
            item = cs.get("ItemNumber", "")
            product = product_map.get(item)
            if not product:
                continue
            coverage_code = cs.get("CoverageCode", "")
            policy = InvPolicy(
                product_id=product.id,
                config_id=config.id,
                policy_type="doc_dem",  # default, refined by coverage code
                erp_planning_params={
                    "erp_source": "d365",
                    "coverage_code": coverage_code,
                    "coverage_time_fence": cs.get("CoverageTimeFenceDays"),
                    "min_inventory": cs.get("MinimumInventoryQuantity"),
                    "max_inventory": cs.get("MaximumInventoryQuantity"),
                },
                source="D365",
            )
            self.db.add(policy)
            result.inv_policies_created += 1

        await self.db.flush()

    # ------------------------------------------------------------------
    # Step 8: Purchase Orders
    # ------------------------------------------------------------------

    # D365 PurchaseOrderStatus → AWS SC purchase_order.status mapping
    _PO_STATUS_MAP: Dict[str, str] = {
        "Confirmed": "APPROVED",
        "Received": "RECEIVED",
        "Invoiced": "RECEIVED",
        "Canceled": "CANCELLED",
        "Draft": "DRAFT",
        "InExternalReview": "SENT",
        "": "DRAFT",
    }

    async def _build_purchase_orders(
        self, config, po_headers, po_lines, site_map, product_map, result,
    ):
        """Map D365 PurchaseOrderHeadersV2 + PurchaseOrderLinesV2 → purchase_order + purchase_order_line_item.

        D365 CSV columns (headers):
            PurchaseOrderNumber, VendorAccountNumber, OrderDate, DeliveryDate,
            PurchaseOrderStatus, CurrencyCode, TotalOrderAmount, dataAreaId

        D365 CSV columns (lines):
            PurchaseOrderNumber, LineNumber, ItemNumber, PurchasedQuantity,
            ReceivedQuantity, PurchasePrice, DeliveryDate, dataAreaId
        """
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem

        # Index lines by PO number for efficient lookup
        lines_by_po: Dict[str, List[Dict]] = {}
        for line in po_lines:
            po_num = line.get("PurchaseOrderNumber", "")
            if po_num:
                lines_by_po.setdefault(po_num, []).append(line)

        # We need at least one site for supplier/destination references.
        # Use the first site from site_map as the default destination.
        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping purchase orders")
            return

        for header in po_headers:
            po_number = header.get("PurchaseOrderNumber", "")
            if not po_number:
                continue

            vendor_account = header.get("VendorAccountNumber", "")
            if not vendor_account:
                result.warnings.append(f"PO {po_number}: missing VendorAccountNumber — skipped")
                continue

            order_date_str = header.get("OrderDate", "")
            order_date = self._parse_d365_date(order_date_str)
            if not order_date:
                result.warnings.append(f"PO {po_number}: invalid OrderDate '{order_date_str}' — skipped")
                continue

            delivery_date_str = header.get("DeliveryDate", "")
            delivery_date = self._parse_d365_date(delivery_date_str)

            d365_status = header.get("PurchaseOrderStatus", "")
            status = self._PO_STATUS_MAP.get(d365_status, "DRAFT")

            currency = header.get("CurrencyCode", "USD") or "USD"
            total_amount = self._safe_float(header.get("TotalOrderAmount"))

            vendor_tp_id = f"D365V_{vendor_account}"

            po = PurchaseOrder(
                po_number=po_number,
                vendor_id=vendor_tp_id,
                supplier_site_id=default_site.id,  # Vendor site — resolved to first config site
                destination_site_id=default_site.id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"D365_{self.tenant_id}",
                order_type="po",
                source="D365_CONTOSO",
                status=status,
                order_date=order_date,
                requested_delivery_date=delivery_date,
                total_amount=total_amount,
                currency=currency[:3] if currency else "USD",
            )
            self.db.add(po)
            await self.db.flush()  # Get auto-generated po.id
            result.purchase_orders_created += 1

            # Build line items for this PO
            for line in lines_by_po.get(po_number, []):
                item_number = line.get("ItemNumber", "")
                product_id = f"CFG{config.id}_{item_number}"
                product = product_map.get(item_number)
                if not product:
                    result.warnings.append(
                        f"PO {po_number} line: ItemNumber '{item_number}' not in product map — skipped"
                    )
                    continue

                line_number_str = line.get("LineNumber", "0")
                # D365 line numbers can be padded: "00001"
                try:
                    line_number = int(line_number_str)
                except (ValueError, TypeError):
                    line_number = 0

                quantity = self._safe_float(line.get("PurchasedQuantity"))
                if quantity is None or quantity <= 0:
                    continue

                received_qty = self._safe_float(line.get("ReceivedQuantity")) or 0.0
                unit_price = self._safe_float(line.get("PurchasePrice"))

                line_delivery_str = line.get("DeliveryDate", "")
                line_delivery = self._parse_d365_date(line_delivery_str) or delivery_date or order_date

                po_line = PurchaseOrderLineItem(
                    po_id=po.id,
                    line_number=line_number,
                    product_id=product_id,
                    quantity=quantity,
                    received_quantity=received_qty,
                    unit_price=unit_price,
                    line_total=(unit_price * quantity) if unit_price else None,
                    requested_delivery_date=line_delivery,
                )
                self.db.add(po_line)
                result.purchase_order_lines_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d purchase orders, %d line items",
            result.purchase_orders_created, result.purchase_order_lines_created,
        )

    # ------------------------------------------------------------------
    # Step 9: Outbound Orders (Sales Orders)
    # ------------------------------------------------------------------

    # D365 SalesOrderStatus → AWS SC outbound_order.status mapping
    _SO_STATUS_MAP: Dict[str, str] = {
        "Confirmed": "CONFIRMED",
        "Delivered": "FULFILLED",
        "Invoiced": "FULFILLED",
        "Canceled": "CANCELLED",
        "Open": "DRAFT",
        "": "DRAFT",
    }

    async def _build_outbound_orders(
        self, config, so_headers, so_lines, site_map, product_map, result,
    ):
        """Map D365 SalesOrderHeadersV2 + SalesOrderLinesV2 → outbound_order + outbound_order_line.

        D365 CSV columns (headers):
            SalesOrderNumber, CustomerAccountNumber, OrderDate, RequestedShipDate,
            SalesOrderStatus, CurrencyCode, TotalOrderAmount, dataAreaId

        D365 CSV columns (lines):
            SalesOrderNumber, LineNumber, ItemNumber, OrderedSalesQuantity,
            DeliveredQuantity, SalesPrice, dataAreaId
        """
        from app.models.sc_entities import OutboundOrder, OutboundOrderLine

        # Index lines by SO number
        lines_by_so: Dict[str, List[Dict]] = {}
        for line in so_lines:
            so_num = line.get("SalesOrderNumber", "")
            if so_num:
                lines_by_so.setdefault(so_num, []).append(line)

        # Default ship-from site
        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping outbound orders")
            return

        for header in so_headers:
            so_number = header.get("SalesOrderNumber", "")
            if not so_number:
                continue

            customer_account = header.get("CustomerAccountNumber", "")
            if not customer_account:
                result.warnings.append(f"SO {so_number}: missing CustomerAccountNumber — skipped")
                continue

            order_date_str = header.get("OrderDate", "")
            order_date = self._parse_d365_date(order_date_str)
            if not order_date:
                result.warnings.append(f"SO {so_number}: invalid OrderDate '{order_date_str}' — skipped")
                continue

            requested_ship_str = header.get("RequestedShipDate", "")
            requested_ship_date = self._parse_d365_date(requested_ship_str)

            d365_status = header.get("SalesOrderStatus", "")
            status = self._SO_STATUS_MAP.get(d365_status, "DRAFT")

            currency = header.get("CurrencyCode", "USD") or "USD"
            total_amount = self._safe_float(header.get("TotalOrderAmount"))

            customer_tp_id = f"D365C_{customer_account}"
            order_id = f"D365_SO_{so_number}"

            # Compute totals from lines
            so_line_data = lines_by_so.get(so_number, [])
            total_ordered = sum(
                self._safe_float(l.get("OrderedSalesQuantity")) or 0.0
                for l in so_line_data
            )
            total_delivered = sum(
                self._safe_float(l.get("DeliveredQuantity")) or 0.0
                for l in so_line_data
            )

            order = OutboundOrder(
                id=order_id,
                company_id=f"D365_{self.tenant_id}",
                order_type="SALES",
                customer_id=customer_tp_id,
                ship_from_site_id=default_site.id,
                status=status,
                order_date=order_date,
                requested_delivery_date=requested_ship_date,
                total_ordered_qty=total_ordered,
                total_fulfilled_qty=total_delivered,
                total_value=total_amount,
                currency=currency[:10] if currency else "USD",
                config_id=config.id,
                source="D365_CONTOSO",
            )
            self.db.add(order)
            result.outbound_orders_created += 1

            # Build order lines
            for line in so_line_data:
                item_number = line.get("ItemNumber", "")
                product_id = f"CFG{config.id}_{item_number}"
                product = product_map.get(item_number)
                if not product:
                    result.warnings.append(
                        f"SO {so_number} line: ItemNumber '{item_number}' not in product map — skipped"
                    )
                    continue

                line_number_str = line.get("LineNumber", "0")
                # D365 LineNumber can be like "000010" — parse as int
                try:
                    line_number = int(line_number_str)
                except (ValueError, TypeError):
                    line_number = 0

                ordered_qty = self._safe_float(line.get("OrderedSalesQuantity"))
                if ordered_qty is None or ordered_qty <= 0:
                    continue

                delivered_qty = self._safe_float(line.get("DeliveredQuantity")) or 0.0

                # Determine line status from quantities
                if delivered_qty >= ordered_qty:
                    line_status = "FULFILLED"
                elif delivered_qty > 0:
                    line_status = "PARTIALLY_FULFILLED"
                else:
                    line_status = status  # Inherit from header

                order_line = OutboundOrderLine(
                    order_id=order_id,
                    line_number=line_number,
                    product_id=product_id,
                    site_id=default_site.id,
                    ordered_quantity=ordered_qty,
                    shipped_quantity=delivered_qty,
                    backlog_quantity=max(0.0, ordered_qty - delivered_qty),
                    requested_delivery_date=requested_ship_date or order_date,
                    order_date=order_date,
                    config_id=config.id,
                    status=line_status,
                )
                self.db.add(order_line)
                result.outbound_order_lines_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d outbound orders, %d line items",
            result.outbound_orders_created, result.outbound_order_lines_created,
        )

    # ------------------------------------------------------------------
    # Step 10: Production Orders
    # ------------------------------------------------------------------

    # D365 ProductionStatus → AWS SC production_orders.status mapping
    _PROD_STATUS_MAP: Dict[str, str] = {
        "Created": "PLANNED",
        "Estimated": "PLANNED",
        "Scheduled": "PLANNED",
        "Released": "RELEASED",
        "Started": "IN_PROGRESS",
        "ReportedAsFinished": "COMPLETED",
        "Ended": "CLOSED",
        "": "PLANNED",
    }

    async def _build_production_orders(
        self, config, prod_headers, site_map, product_map, result,
    ):
        """Map D365 ProductionOrderHeaders → production_orders.

        D365 CSV columns:
            ProductionOrderNumber, ItemNumber, ProductionQuantity,
            ProductionStatus, ScheduledStartDate, ScheduledEndDate,
            SiteId, dataAreaId
        """
        from app.models.production_order import ProductionOrder
        from datetime import datetime as dt

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping production orders")
            return

        for header in prod_headers:
            prod_order_num = header.get("ProductionOrderNumber", "")
            if not prod_order_num:
                continue

            item_number = header.get("ItemNumber", "")
            product_id = f"CFG{config.id}_{item_number}"
            product = product_map.get(item_number)
            if not product:
                result.warnings.append(
                    f"ProdOrder {prod_order_num}: ItemNumber '{item_number}' not in product map — skipped"
                )
                continue

            quantity = self._safe_float(header.get("ProductionQuantity"))
            if quantity is None or quantity <= 0:
                result.warnings.append(
                    f"ProdOrder {prod_order_num}: invalid ProductionQuantity — skipped"
                )
                continue

            d365_status = header.get("ProductionStatus", "")
            status = self._PROD_STATUS_MAP.get(d365_status, "PLANNED")

            # Resolve site from D365 SiteId
            d365_site_id = header.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            # Parse scheduled dates — D365 uses YYYYMMDD format, "00000000" means not set
            start_date_str = header.get("ScheduledStartDate", "")
            end_date_str = header.get("ScheduledEndDate", "")
            planned_start = self._parse_d365_date(start_date_str)
            planned_end = self._parse_d365_date(end_date_str)

            # Both dates are required by the model — use fallback from each other or today
            now = dt.utcnow()
            if not planned_start:
                planned_start = planned_end or now
            if not planned_end:
                planned_end = planned_start or now
            # Ensure start <= end
            if planned_start > planned_end:
                planned_start, planned_end = planned_end, planned_start

            prod_order = ProductionOrder(
                order_number=prod_order_num,
                item_id=product_id,
                site_id=site.id,
                config_id=config.id,
                planned_quantity=int(quantity),
                status=status,
                planned_start_date=planned_start,
                planned_completion_date=planned_end,
            )
            self.db.add(prod_order)
            result.production_orders_created += 1

        await self.db.flush()
        logger.info("D365: created %d production orders", result.production_orders_created)

    # ------------------------------------------------------------------
    # Step 11: Forecasts
    # ------------------------------------------------------------------

    async def _build_forecasts(
        self, config, forecast_entries, site_map, product_map, result,
    ):
        """Map D365 DemandForecastEntries → forecast.

        D365 CSV columns:
            ItemNumber, SiteId, WarehouseId, ForecastQuantity,
            ForecastDate, ForecastModel, dataAreaId
        """
        from app.models.sc_entities import Forecast

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping forecasts")
            return

        for entry in forecast_entries:
            item_number = entry.get("ItemNumber", "")
            product_id = f"CFG{config.id}_{item_number}"
            product = product_map.get(item_number)
            if not product:
                # Skip silently — many forecast entries reference items not in product master
                continue

            forecast_date_str = entry.get("ForecastDate", "")
            forecast_date = self._parse_d365_date(forecast_date_str)
            if not forecast_date:
                continue

            quantity = self._safe_float(entry.get("ForecastQuantity"))
            if quantity is None:
                continue
            # Allow zero-quantity forecasts (explicit zero demand)

            # Resolve site from D365 SiteId
            d365_site_id = entry.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            forecast_model = entry.get("ForecastModel", "")

            forecast = Forecast(
                product_id=product_id,
                site_id=site.id,
                company_id=f"D365_{self.tenant_id}",
                forecast_date=forecast_date,
                forecast_quantity=quantity,
                forecast_p50=quantity,
                forecast_type="statistical",
                forecast_level="product",
                forecast_method=forecast_model[:50] if forecast_model else "erp_import",
                is_active="Y",
                config_id=config.id,
                source="D365_CONTOSO",
            )
            self.db.add(forecast)
            result.forecasts_created += 1

        await self.db.flush()
        logger.info("D365: created %d forecasts", result.forecasts_created)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_d365_date(date_str: str):
        """Parse D365 date strings in YYYYMMDD or YYYY-MM-DD format.

        Returns a ``date`` object or ``None`` if the string is empty,
        all-zeros, or otherwise unparseable.
        """
        from datetime import date as d, datetime as dt

        if not date_str or date_str.strip() in ("", "00000000", "0"):
            return None

        date_str = date_str.strip()

        # YYYYMMDD (common D365 export format)
        if len(date_str) == 8 and date_str.isdigit():
            try:
                return d(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                return None

        # YYYY-MM-DD (ISO format)
        if len(date_str) >= 10 and date_str[4] == "-":
            try:
                return dt.strptime(date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                return None

        return None

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Convert a value to float, returning ``None`` on failure."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

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
- PurchaseOrderReceiptJournal                    → GoodsReceipt + GoodsReceiptLineItem
- ShipmentHeaders / ShipmentLines                → Shipment
- TransferOrderHeaders / TransferOrderLines      → TransferOrder + TransferOrderLineItem
- QualityOrders                                  → QualityOrder + QualityOrderLineItem
- MaintenanceWorkOrders                          → MaintenanceOrder
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
    goods_receipts_created: int = 0
    goods_receipt_lines_created: int = 0
    shipments_created: int = 0
    transfer_orders_created: int = 0
    transfer_order_lines_created: int = 0
    quality_orders_created: int = 0
    quality_order_lines_created: int = 0
    maintenance_orders_created: int = 0
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
            # D365 OData uses "OperationalSites", CSV exports use "Sites"
            sites_data = data.get("OperationalSites", data.get("Sites", []))
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

            # Step 12: Goods receipts
            gr_data = data.get("PurchaseOrderReceiptJournal", [])
            await self._build_goods_receipts(
                config, gr_data, site_map, product_map, result,
            )

            # Step 13: Shipments
            shipment_headers = data.get("ShipmentHeaders", [])
            shipment_lines = data.get("ShipmentLines", [])
            await self._build_shipments(
                config, shipment_headers, shipment_lines, site_map, product_map, result,
            )

            # Step 14: Transfer orders
            to_headers = data.get("TransferOrderHeaders", [])
            to_lines = data.get("TransferOrderLines", [])
            await self._build_transfer_orders(
                config, to_headers, to_lines, site_map, product_map, result,
            )

            # Step 15: Quality orders
            quality_data = data.get("QualityOrders", [])
            await self._build_quality_orders(
                config, quality_data, site_map, product_map, result,
            )

            # Step 16: Maintenance orders
            maintenance_data = data.get("MaintenanceWorkOrders", [])
            await self._build_maintenance_orders(
                config, maintenance_data, site_map, result,
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
    # Step 12: Goods Receipts
    # ------------------------------------------------------------------

    async def _build_goods_receipts(
        self, config, gr_data, site_map, product_map, result,
    ):
        """Map D365 PurchaseOrderReceiptJournal → goods_receipt + goods_receipt_line_item.

        D365 CSV columns:
            PurchaseOrderNumber, LineNumber, PostingDate, ReceiptQuantity,
            ProductNumber, InventSiteId, PackingSlipId, dataAreaId

        GR number format: D365_GR_{PurchaseOrderNumber}_{PostingDate}
        Links to purchase_order via po_number matching.
        """
        from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLineItem
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
        import sqlalchemy as sa

        if not gr_data:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping goods receipts")
            return

        # Pre-load PO id lookup: po_number → PurchaseOrder.id
        po_numbers = {r.get("PurchaseOrderNumber", "") for r in gr_data if r.get("PurchaseOrderNumber")}
        po_id_map: Dict[str, int] = {}
        if po_numbers:
            rows = (await self.db.execute(
                sa.select(PurchaseOrder.id, PurchaseOrder.po_number).where(
                    PurchaseOrder.config_id == config.id,
                    PurchaseOrder.po_number.in_(po_numbers),
                )
            )).all()
            po_id_map = {r.po_number: r.id for r in rows}

        # Pre-load PO line id lookup: (po_id, line_number) → PurchaseOrderLineItem.id
        po_line_id_map: Dict[tuple, int] = {}
        if po_id_map:
            po_line_rows = (await self.db.execute(
                sa.select(
                    PurchaseOrderLineItem.id,
                    PurchaseOrderLineItem.po_id,
                    PurchaseOrderLineItem.line_number,
                ).where(
                    PurchaseOrderLineItem.po_id.in_(list(po_id_map.values())),
                )
            )).all()
            po_line_id_map = {(r.po_id, r.line_number): r.id for r in po_line_rows}

        # Group receipt lines by (PurchaseOrderNumber, PostingDate) to form GR headers
        gr_groups: Dict[str, List[Dict]] = {}
        for row in gr_data:
            po_num = row.get("PurchaseOrderNumber", "")
            posting_date_str = row.get("PostingDate", "")
            if not po_num or not posting_date_str:
                continue
            gr_key = f"{po_num}_{posting_date_str}"
            gr_groups.setdefault(gr_key, []).append(row)

        for gr_key, lines in gr_groups.items():
            first = lines[0]
            po_num = first.get("PurchaseOrderNumber", "")
            posting_date_str = first.get("PostingDate", "")
            posting_date = self._parse_d365_date(posting_date_str)
            if not posting_date:
                result.warnings.append(f"GR {gr_key}: invalid PostingDate '{posting_date_str}' — skipped")
                continue

            po_id = po_id_map.get(po_num)
            if not po_id:
                result.warnings.append(f"GR {gr_key}: PO '{po_num}' not found in config — skipped")
                continue

            gr_number = f"D365_GR_{po_num}_{posting_date_str}"
            packing_slip = first.get("PackingSlipId", "")

            # Resolve receiving site
            d365_site_id = first.get("InventSiteId", "")
            site = site_map.get(d365_site_id, default_site)

            total_received = sum(self._safe_float(l.get("ReceiptQuantity")) or 0.0 for l in lines)

            gr = GoodsReceipt(
                gr_number=gr_number,
                po_id=po_id,
                receipt_date=posting_date,
                delivery_note_number=packing_slip[:100] if packing_slip else None,
                status="COMPLETED",
                receiving_site_id=site.id,
                total_received_qty=total_received,
                total_accepted_qty=total_received,
            )
            self.db.add(gr)
            await self.db.flush()
            result.goods_receipts_created += 1

            # Build line items
            for idx, line in enumerate(lines, start=1):
                item_number = line.get("ProductNumber", "")
                product = product_map.get(item_number)
                if not product:
                    result.warnings.append(
                        f"GR {gr_number} line: ProductNumber '{item_number}' not in product map — skipped"
                    )
                    continue

                receipt_qty = self._safe_float(line.get("ReceiptQuantity"))
                if receipt_qty is None or receipt_qty <= 0:
                    continue

                line_number_str = line.get("LineNumber", "0")
                try:
                    line_number = int(line_number_str)
                except (ValueError, TypeError):
                    line_number = idx

                product_id = f"CFG{config.id}_{item_number}"

                # Resolve PO line id for cross-reference
                po_line_id = po_line_id_map.get((po_id, line_number))
                if not po_line_id:
                    # Try first PO line as fallback only if there's exactly one line
                    matching = [v for k, v in po_line_id_map.items() if k[0] == po_id]
                    if len(matching) == 1:
                        po_line_id = matching[0]
                    else:
                        result.warnings.append(
                            f"GR {gr_number} line {line_number}: no matching PO line — skipped"
                        )
                        continue

                gr_line = GoodsReceiptLineItem(
                    gr_id=gr.id,
                    po_line_id=po_line_id,
                    line_number=line_number,
                    product_id=product_id,
                    expected_qty=receipt_qty,
                    received_qty=receipt_qty,
                    accepted_qty=receipt_qty,
                    variance_qty=0.0,
                    variance_type="EXACT",
                )
                self.db.add(gr_line)
                result.goods_receipt_lines_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d goods receipts, %d line items",
            result.goods_receipts_created, result.goods_receipt_lines_created,
        )

    # ------------------------------------------------------------------
    # Step 13: Shipments
    # ------------------------------------------------------------------

    async def _build_shipments(
        self, config, shipment_headers, shipment_lines, site_map, product_map, result,
    ):
        """Map D365 ShipmentHeaders + ShipmentLines → shipment.

        D365 CSV columns (headers):
            ShipmentNumber, ShipDate, CarrierName, TrackingNumber,
            ShipFromSite, ShipToCustomer, ShipmentStatus, dataAreaId

        D365 CSV columns (lines):
            ShipmentNumber, ItemNumber, ShippedQuantity, LineNumber, dataAreaId

        Shipment ID format: D365_SH_{ShipmentNumber}
        """
        from app.models.sc_entities import Shipment

        if not shipment_headers:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping shipments")
            return

        # Index lines by shipment number
        lines_by_sh: Dict[str, List[Dict]] = {}
        for line in shipment_lines:
            sh_num = line.get("ShipmentNumber", "")
            if sh_num:
                lines_by_sh.setdefault(sh_num, []).append(line)

        _SH_STATUS_MAP: Dict[str, str] = {
            "Shipped": "in_transit",
            "Delivered": "delivered",
            "Cancelled": "cancelled",
            "Open": "planned",
            "InTransit": "in_transit",
            "": "planned",
        }

        for header in shipment_headers:
            sh_number = header.get("ShipmentNumber", "")
            if not sh_number:
                continue

            ship_date_str = header.get("ShipDate", "")
            ship_date = self._parse_d365_date(ship_date_str)

            # Resolve from-site
            d365_from_site = header.get("ShipFromSite", "")
            from_site = site_map.get(d365_from_site, default_site)

            # To-site: try ShipToSite first, fall back to default
            d365_to_site = header.get("ShipToSite", "")
            to_site = site_map.get(d365_to_site, default_site)

            carrier_name = header.get("CarrierName", "")
            tracking_number = header.get("TrackingNumber", "")
            d365_status = header.get("ShipmentStatus", "")
            status = _SH_STATUS_MAP.get(d365_status, "planned")

            shipment_id = f"D365_SH_{sh_number}"

            # Determine product and quantity from lines
            sh_lines = lines_by_sh.get(sh_number, [])

            if sh_lines:
                # Create one shipment record per line (each has distinct product)
                for line in sh_lines:
                    item_number = line.get("ItemNumber", "")
                    product = product_map.get(item_number)
                    if not product:
                        continue

                    shipped_qty = self._safe_float(line.get("ShippedQuantity"))
                    if shipped_qty is None or shipped_qty <= 0:
                        continue

                    product_id = f"CFG{config.id}_{item_number}"
                    line_num = line.get("LineNumber", "1")
                    line_shipment_id = f"{shipment_id}_{line_num}"

                    shipment = Shipment(
                        id=line_shipment_id,
                        company_id=f"D365_{self.tenant_id}",
                        order_id=sh_number,
                        order_line_number=int(line_num) if str(line_num).isdigit() else 1,
                        product_id=product_id,
                        quantity=shipped_qty,
                        from_site_id=from_site.id,
                        to_site_id=to_site.id,
                        carrier_name=carrier_name[:200] if carrier_name else None,
                        tracking_number=tracking_number[:100] if tracking_number else None,
                        status=status,
                        ship_date=ship_date,
                        config_id=config.id,
                        tenant_id=self.tenant_id,
                        source="D365_CONTOSO",
                    )
                    self.db.add(shipment)
                    result.shipments_created += 1
            else:
                # Header-only shipment (no lines) — create a placeholder
                # Need a product_id — skip if we can't determine one
                result.warnings.append(
                    f"Shipment {sh_number}: no ShipmentLines found — skipped"
                )

        await self.db.flush()
        logger.info("D365: created %d shipments", result.shipments_created)

    # ------------------------------------------------------------------
    # Step 14: Transfer Orders
    # ------------------------------------------------------------------

    _TO_STATUS_MAP: Dict[str, str] = {
        "Created": "DRAFT",
        "Shipped": "SHIPPED",
        "Received": "RECEIVED",
        "Cancelled": "CANCELLED",
        "": "DRAFT",
    }

    async def _build_transfer_orders(
        self, config, to_headers, to_lines, site_map, product_map, result,
    ):
        """Map D365 TransferOrderHeaders + TransferOrderLines → transfer_order + transfer_order_line_item.

        D365 CSV columns (headers):
            TransferNumber, FromWarehouse, ToWarehouse, TransferDate,
            TransferStatus, dataAreaId

        D365 CSV columns (lines):
            TransferNumber, ItemNumber, Quantity, LineNumber,
            ShippedQuantity, ReceivedQuantity, dataAreaId

        TO ID format: D365_TO_{TransferNumber}
        """
        from app.models.transfer_order import TransferOrder, TransferOrderLineItem

        if not to_headers:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping transfer orders")
            return

        # Index lines by transfer number
        lines_by_to: Dict[str, List[Dict]] = {}
        for line in to_lines:
            to_num = line.get("TransferNumber", "")
            if to_num:
                lines_by_to.setdefault(to_num, []).append(line)

        for header in to_headers:
            transfer_number = header.get("TransferNumber", "")
            if not transfer_number:
                continue

            transfer_date_str = header.get("TransferDate", "")
            transfer_date = self._parse_d365_date(transfer_date_str)
            if not transfer_date:
                result.warnings.append(
                    f"TO {transfer_number}: invalid TransferDate '{transfer_date_str}' — skipped"
                )
                continue

            # Resolve source and destination sites from warehouse IDs
            from_wh = header.get("FromWarehouse", "")
            to_wh = header.get("ToWarehouse", "")
            source_site = site_map.get(from_wh, default_site)
            dest_site = site_map.get(to_wh, default_site)

            d365_status = header.get("TransferStatus", "")
            status = self._TO_STATUS_MAP.get(d365_status, "DRAFT")

            to_number = f"D365_TO_{transfer_number}"

            to_order = TransferOrder(
                to_number=to_number,
                source_site_id=source_site.id,
                destination_site_id=dest_site.id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"D365_{self.tenant_id}",
                order_type="transfer",
                source="D365_CONTOSO",
                status=status,
                order_date=transfer_date,
                shipment_date=transfer_date,
                estimated_delivery_date=transfer_date,  # D365 may not provide separate delivery date
            )
            self.db.add(to_order)
            await self.db.flush()
            result.transfer_orders_created += 1

            # Build line items
            for line in lines_by_to.get(transfer_number, []):
                item_number = line.get("ItemNumber", "")
                product = product_map.get(item_number)
                if not product:
                    result.warnings.append(
                        f"TO {to_number} line: ItemNumber '{item_number}' not in product map — skipped"
                    )
                    continue

                quantity = self._safe_float(line.get("Quantity"))
                if quantity is None or quantity <= 0:
                    continue

                line_number_str = line.get("LineNumber", "0")
                try:
                    line_number = int(line_number_str)
                except (ValueError, TypeError):
                    line_number = 0

                product_id = f"CFG{config.id}_{item_number}"
                shipped_qty = self._safe_float(line.get("ShippedQuantity")) or 0.0
                received_qty = self._safe_float(line.get("ReceivedQuantity")) or 0.0

                to_line = TransferOrderLineItem(
                    to_id=to_order.id,
                    line_number=line_number,
                    product_id=product_id,
                    quantity=quantity,
                    shipped_quantity=shipped_qty,
                    received_quantity=received_qty,
                    requested_ship_date=transfer_date,
                    requested_delivery_date=transfer_date,
                )
                self.db.add(to_line)
                result.transfer_order_lines_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d transfer orders, %d line items",
            result.transfer_orders_created, result.transfer_order_lines_created,
        )

    # ------------------------------------------------------------------
    # Step 15: Quality Orders
    # ------------------------------------------------------------------

    _QO_STATUS_MAP: Dict[str, str] = {
        "Open": "CREATED",
        "InProgress": "IN_INSPECTION",
        "Validated": "DISPOSITION_DECIDED",
        "Closed": "CLOSED",
        "Cancelled": "CANCELLED",
        "": "CREATED",
    }

    _QO_DISPOSITION_MAP: Dict[str, str] = {
        "Accept": "ACCEPT",
        "Reject": "REJECT",
        "Rework": "REWORK",
        "Scrap": "SCRAP",
        "": None,
    }

    async def _build_quality_orders(
        self, config, quality_data, site_map, product_map, result,
    ):
        """Map D365 QualityOrders → quality_order + quality_order_line_item.

        D365 CSV columns:
            QualityOrderNumber, ItemNumber, InspectionQuantity, AcceptedQuantity,
            RejectedQuantity, Status, SiteId, DispositionCode, OriginType,
            OriginOrderNumber, TestGroupId, dataAreaId

        QO number format: D365_QI_{QualityOrderNumber}
        """
        from app.models.quality_order import QualityOrder, QualityOrderLineItem
        from datetime import date as d

        if not quality_data:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping quality orders")
            return

        for row in quality_data:
            qo_number_raw = row.get("QualityOrderNumber", "")
            if not qo_number_raw:
                continue

            item_number = row.get("ItemNumber", "")
            product = product_map.get(item_number)
            if not product:
                result.warnings.append(
                    f"QO {qo_number_raw}: ItemNumber '{item_number}' not in product map — skipped"
                )
                continue

            inspection_qty = self._safe_float(row.get("InspectionQuantity"))
            if inspection_qty is None or inspection_qty <= 0:
                result.warnings.append(
                    f"QO {qo_number_raw}: invalid InspectionQuantity — skipped"
                )
                continue

            product_id = f"CFG{config.id}_{item_number}"
            qo_number = f"D365_QI_{qo_number_raw}"

            # Resolve site
            d365_site_id = row.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            d365_status = row.get("Status", "")
            status = self._QO_STATUS_MAP.get(d365_status, "CREATED")

            accepted_qty = self._safe_float(row.get("AcceptedQuantity")) or 0.0
            rejected_qty = self._safe_float(row.get("RejectedQuantity")) or 0.0

            disposition_code = row.get("DispositionCode", "")
            disposition = self._QO_DISPOSITION_MAP.get(disposition_code)

            origin_type_raw = row.get("OriginType", "GOODS_RECEIPT")
            origin_order = row.get("OriginOrderNumber", "")

            # Map D365 origin type to our enum
            origin_map = {
                "Purchase": "GOODS_RECEIPT",
                "Production": "PRODUCTION_ORDER",
                "Transfer": "TRANSFER_RECEIPT",
                "Customer": "CUSTOMER_COMPLAINT",
            }
            origin_type = origin_map.get(origin_type_raw, "GOODS_RECEIPT")

            order_date_str = row.get("OrderDate", "")
            order_date = self._parse_d365_date(order_date_str) or d.today()

            qo = QualityOrder(
                quality_order_number=qo_number,
                site_id=site.id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"D365_{self.tenant_id}",
                source="D365_CONTOSO",
                inspection_type="INCOMING",
                status=status,
                origin_type=origin_type,
                origin_order_id=origin_order[:100] if origin_order else None,
                product_id=product_id,
                inspection_quantity=inspection_qty,
                accepted_quantity=accepted_qty,
                rejected_quantity=rejected_qty,
                disposition=disposition,
                order_date=order_date,
            )
            self.db.add(qo)
            await self.db.flush()
            result.quality_orders_created += 1

            # Create a single summary line item per quality order
            test_group = row.get("TestGroupId", "")
            qo_line = QualityOrderLineItem(
                quality_order_id=qo.id,
                line_number=1,
                characteristic_name=test_group[:200] if test_group else "General Inspection",
                characteristic_type="ATTRIBUTE",
                result="PASS" if rejected_qty == 0.0 and accepted_qty > 0 else (
                    "FAIL" if rejected_qty > 0 else None
                ),
                defect_count=int(rejected_qty) if rejected_qty > 0 else 0,
            )
            self.db.add(qo_line)
            result.quality_order_lines_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d quality orders, %d line items",
            result.quality_orders_created, result.quality_order_lines_created,
        )

    # ------------------------------------------------------------------
    # Step 16: Maintenance Orders
    # ------------------------------------------------------------------

    _MAINT_STATUS_MAP: Dict[str, str] = {
        "Created": "PLANNED",
        "Scheduled": "SCHEDULED",
        "InProgress": "IN_PROGRESS",
        "Completed": "COMPLETED",
        "Cancelled": "CANCELLED",
        "": "PLANNED",
    }

    _MAINT_TYPE_MAP: Dict[str, str] = {
        "Preventive": "PREVENTIVE",
        "Corrective": "CORRECTIVE",
        "Predictive": "PREDICTIVE",
        "Emergency": "EMERGENCY",
        "Routine": "ROUTINE",
        "": "CORRECTIVE",
    }

    _MAINT_PRIORITY_MAP: Dict[str, str] = {
        "1": "CRITICAL",
        "2": "HIGH",
        "3": "NORMAL",
        "4": "LOW",
        "5": "LOW",
        "Critical": "CRITICAL",
        "High": "HIGH",
        "Normal": "NORMAL",
        "Low": "LOW",
        "": "NORMAL",
    }

    async def _build_maintenance_orders(
        self, config, maintenance_data, site_map, result,
    ):
        """Map D365 MaintenanceWorkOrders → maintenance_order.

        D365 CSV columns:
            WorkOrderNumber, EquipmentNumber, MaintenanceType, Priority,
            ScheduledDate, Status, SiteId, Description, EquipmentName,
            EstimatedHours, dataAreaId

        MO number format: D365_MO_{WorkOrderNumber}
        """
        from app.models.maintenance_order import MaintenanceOrder
        from datetime import date as d

        if not maintenance_data:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping maintenance orders")
            return

        for row in maintenance_data:
            wo_number = row.get("WorkOrderNumber", "")
            if not wo_number:
                continue

            equipment_id = row.get("EquipmentNumber", "")
            if not equipment_id:
                result.warnings.append(f"MaintOrder {wo_number}: missing EquipmentNumber — skipped")
                continue

            # Resolve site
            d365_site_id = row.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            d365_type = row.get("MaintenanceType", "")
            maintenance_type = self._MAINT_TYPE_MAP.get(d365_type, "CORRECTIVE")

            d365_status = row.get("Status", "")
            status = self._MAINT_STATUS_MAP.get(d365_status, "PLANNED")

            d365_priority = row.get("Priority", "")
            priority = self._MAINT_PRIORITY_MAP.get(str(d365_priority), "NORMAL")

            scheduled_date_str = row.get("ScheduledDate", "")
            scheduled_date = self._parse_d365_date(scheduled_date_str)

            order_date = scheduled_date or d.today()

            description = row.get("Description", "")
            equipment_name = row.get("EquipmentName", "")
            estimated_hours = self._safe_float(row.get("EstimatedHours"))

            mo_number = f"D365_MO_{wo_number}"

            maint_order = MaintenanceOrder(
                maintenance_order_number=mo_number,
                asset_id=equipment_id[:40],
                asset_name=equipment_name[:200] if equipment_name else None,
                equipment_id=equipment_id[:100],
                site_id=site.id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"D365_{self.tenant_id}",
                source="D365_CONTOSO",
                maintenance_type=maintenance_type,
                status=status,
                priority=priority,
                order_date=order_date,
                scheduled_start_date=scheduled_date,
                work_description=description[:2000] if description else f"Maintenance for {equipment_id}",
                estimated_labor_hours=estimated_hours,
            )
            self.db.add(maint_order)
            result.maintenance_orders_created += 1

        await self.db.flush()
        logger.info("D365: created %d maintenance orders", result.maintenance_orders_created)

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

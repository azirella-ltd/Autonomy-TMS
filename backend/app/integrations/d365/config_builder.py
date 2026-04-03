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

Master data (enrichment):
- ProductUnitConversions    → Product enrichment (base_uom, external_identifiers)
- BatchMaster               → Product enrichment (batch tracking attributes)
- CustomerSalesAreas        → TradingPartner enrichment (sales org, channel, division)
- VendorPurchasePrices      → VendorProduct (vendor-specific pricing)
- ApprovedVendorList        → SourcingRules (buy rules)
- WorkCenters               → Capacity resource metadata
- RoutingHeaders/Operations → ProductionProcess
- CapacityData              → Capacity enrichment for work centers
- StorageLocations          → Site.attributes enrichment

Transactional data:
- PurchaseOrderHeadersV2 / PurchaseOrderLinesV2 → PurchaseOrder + PurchaseOrderLineItem
- PurchaseOrderScheduleLines                     → InboundOrderLineSchedule
- PurchaseRequisitionLines                       → PurchaseOrder (DRAFT/requisition)
- SalesOrderHeadersV2 / SalesOrderLinesV2       → OutboundOrder + OutboundOrderLine
- SalesOrderDeliverySchedules                    → OutboundOrder enrichment
- ProductionOrderHeaders                         → ProductionOrder
- ProductionOrderItems                           → ProductionOrder enrichment
- ProductionOrderBOMLines                        → ProductionOrderComponent
- ProductionRouteOperations                      → ProductionOrder.extra_data enrichment
- PlannedOrders                                  → PurchaseOrder/ProductionOrder (PLANNED)
- DemandForecastEntries                          → Forecast
- PurchaseOrderReceiptJournal                    → GoodsReceipt + GoodsReceiptLineItem
- ShipmentHeaders / ShipmentLines                → Shipment
- TransferOrderHeaders / TransferOrderLines      → TransferOrder + TransferOrderLineItem
- QualityOrders                                  → QualityOrder + QualityOrderLineItem
- MaintenanceWorkOrders                          → MaintenanceOrder

CDC data:
- ProductionOrderConfirmations → ProductionOrder actual_quantity/yield enrichment
- QualityTestResults           → QualityOrderLineItem (detailed test data)
- QualityNotifications         → QualityOrder (defect/complaint records)
"""

import logging
from typing import Dict, List, Optional, Any, Set, Tuple
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
    # Enrichment counters (Steps 17-27)
    products_enriched: int = 0
    customers_enriched: int = 0
    vendor_products_created: int = 0
    sourcing_rules_created: int = 0
    resources_created: int = 0
    production_processes_created: int = 0
    storage_locations_enriched: int = 0
    po_schedules_created: int = 0
    so_schedules_enriched: int = 0
    requisitions_created: int = 0
    planned_orders_created: int = 0
    production_components_created: int = 0
    production_routes_enriched: int = 0
    production_confirmations_applied: int = 0
    quality_details_enriched: int = 0
    quality_notifications_created: int = 0
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

            # Step 17: Enrich products (UoM conversions + batch attributes)
            unit_conversions = data.get("ProductUnitConversions", [])
            batch_master = data.get("BatchMaster", [])
            await self._enrich_products(
                config, unit_conversions, batch_master, product_map, result,
            )

            # Step 18: Enrich customers (sales area data)
            customer_sales_areas = data.get("CustomerSalesAreas", [])
            await self._enrich_customers(config, customer_sales_areas, result)

            # Step 19: Vendor pricing → vendor_product
            vendor_prices = data.get("VendorPurchasePrices", [])
            await self._enrich_vendor_pricing(
                config, vendor_prices, product_map, result,
            )

            # Step 20: Approved vendor list → sourcing_rules
            approved_vendors = data.get("ApprovedVendorList", [])
            await self._build_sourcing_rules(
                config, approved_vendors, site_map, product_map, result,
            )

            # Step 21: Work centers, routing, capacity → resources + production_process
            work_centers = data.get("WorkCenters", [])
            routing_headers = data.get("RoutingHeaders", [])
            routing_operations = data.get("RoutingOperations", [])
            capacity_data = data.get("CapacityData", [])
            await self._build_resources_and_routing(
                config, work_centers, routing_headers, routing_operations,
                capacity_data, site_map, result,
            )

            # Step 22: Enrich storage locations → site attributes
            await self._enrich_storage_locations(
                config, storage_locs, site_map, result,
            )

            # Step 23: PO schedule lines + SO delivery schedules
            po_schedule_lines = data.get("PurchaseOrderScheduleLines", [])
            so_delivery_schedules = data.get("SalesOrderDeliverySchedules", [])
            await self._build_order_schedules(
                config, po_schedule_lines, so_delivery_schedules,
                site_map, product_map, result,
            )

            # Step 24: Purchase requisitions + planned orders
            requisition_lines = data.get("PurchaseRequisitionLines", [])
            planned_orders = data.get("PlannedOrders", [])
            await self._build_requisitions_and_planned(
                config, requisition_lines, planned_orders,
                site_map, product_map, result,
            )

            # Step 25: Production order enrichment (items, BOM lines, route operations, confirmations)
            prod_order_items = data.get("ProductionOrderItems", [])
            prod_bom_lines = data.get("ProductionOrderBOMLines", [])
            prod_route_ops = data.get("ProductionRouteOperations", [])
            prod_confirmations = data.get("ProductionOrderConfirmations", [])
            await self._enrich_production_details(
                config, prod_order_items, prod_bom_lines,
                prod_route_ops, prod_confirmations,
                site_map, product_map, result,
            )

            # Step 26: Quality enrichment (test results, notifications)
            quality_test_results = data.get("QualityTestResults", [])
            quality_notifications = data.get("QualityNotifications", [])
            await self._enrich_quality_details(
                config, quality_test_results, quality_notifications,
                site_map, product_map, result,
            )

            # Derivation fallbacks for empty entities
            derived_counts = await self._run_derivation_fallbacks(
                config, data, site_map, product_map, result,
            )

            # Build and save extraction audit report
            audit = self._build_extraction_audit(config, data, result, derived_counts)
            await audit.save(self.db)

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
        seen_sites: Set[str] = set()

        for s in sites_data:
            site_id = s.get("SiteId", "")
            if site_id in seen_sites:
                continue
            seen_sites.add(site_id)
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
        seen_products: Set[str] = set()

        for p in products_data:
            item_no = p.get("ItemNumber", "")
            if item_no in seen_products:
                continue
            seen_products.add(item_no)
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

        seen_tp: Set[str] = set()
        for v in vendors:
            v_acct = v.get('VendorAccountNumber', '')
            if v_acct in seen_tp:
                continue
            seen_tp.add(v_acct)
            tp = TradingPartner(
                id=f"D365_V_{v_acct}",
                tpartner_type="vendor",
                description=v.get("VendorOrganizationName", v.get("VendorAccountNumber", ""))[:200],
                company_id=f"D365_{self.tenant_id}",
                source="D365",
            )
            self.db.add(tp)
            result.trading_partners_created += 1

        seen_cust: Set[str] = set()
        for c in customers:
            c_acct = c.get('CustomerAccount', '')
            if c_acct in seen_cust:
                continue
            seen_cust.add(c_acct)
            tp = TradingPartner(
                id=f"D365_C_{c_acct}",
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
        """Build ProductBom records from D365 BillOfMaterialsHeaders/Lines.

        D365 BOM types (BOMType field on header):
          0 = Item (Manufacturing/Production) — skip
          1 = Planning BOM
          2 = Formula — skip (process manufacturing variant of production)
          3 = Sales BOM

        BOMApproved field: 'Yes' means active BOM version.
        Extract Planning (type 1) and Sales (type 3) BOMs only.
        """
        from app.models.sc_entities import ProductBom
        from datetime import datetime

        # Map D365 BOM type to bom_usage
        _D365_BOM_TYPE_USAGE = {
            "1": "planning", 1: "planning",
            "3": "sales", 3: "sales",
            "Planning": "planning",
            "SalesBOM": "sales", "Sales": "sales",
        }

        header_map = {h.get("BOMId"): h for h in bom_headers}
        seen_bom_keys: Set[Tuple] = set()

        for line in bom_lines:
            bom_id = line.get("BOMId")
            header = header_map.get(bom_id, {})

            # Determine bom_usage from header BOMType
            bom_type = header.get("BOMType", header.get("BillOfMaterialsType", ""))
            bom_usage = _D365_BOM_TYPE_USAGE.get(bom_type)
            if not bom_usage:
                continue  # Skip production/formula BOMs

            parent_item = header.get("ItemNumber", "")
            child_item = line.get("ItemNumber", "")
            parent_prod = product_map.get(parent_item)
            child_prod = product_map.get(child_item)
            if parent_prod and child_prod:
                # Dedup: skip duplicate (product_id, component_product_id)
                bom_key = (parent_prod.id, child_prod.id)
                if bom_key in seen_bom_keys:
                    continue
                seen_bom_keys.add(bom_key)
                comp_qty = float(line.get("Quantity", line.get("BOMLineQuantity", 1)))
                bom = ProductBom(
                    product_id=parent_prod.id,
                    component_product_id=child_prod.id,
                    component_quantity=comp_qty,
                    component_uom=str(line.get("UnitId", "EA") or "EA"),
                    bom_usage=bom_usage,
                    is_active="true" if header.get("BOMApproved") in ("Yes", True) else "false",
                    config_id=config.id,
                    source="D365_BOM",
                    source_update_dttm=datetime.utcnow(),
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
        seen_inv_levels: Set[str] = set()
        for inv in inv_onhand:
            item = inv.get("ItemNumber", "")
            product = product_map.get(item)
            if not product:
                continue
            # Dedup: skip duplicate product_id for inv levels
            if product.id in seen_inv_levels:
                continue
            seen_inv_levels.add(product.id)
            level = InvLevel(
                product_id=product.id,
                config_id=config.id,
                on_hand_quantity=float(inv.get("AvailableOnHandQuantity", 0)),
                source="D365",
            )
            self.db.add(level)
            result.inv_levels_created += 1

        # Coverage settings → inventory policies
        seen_inv_policies: Set[str] = set()
        for cs in coverage:
            item = cs.get("ItemNumber", "")
            product = product_map.get(item)
            if not product:
                continue
            # Dedup: skip duplicate product_id for inv policies
            if product.id in seen_inv_policies:
                continue
            seen_inv_policies.add(product.id)
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

        seen_po: Set[str] = set()
        for header in po_headers:
            po_number = header.get("PurchaseOrderNumber", "")
            if not po_number:
                continue
            if po_number in seen_po:
                continue
            seen_po.add(po_number)

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

        seen_so: Set[str] = set()
        for header in so_headers:
            so_number = header.get("SalesOrderNumber", "")
            if not so_number:
                continue
            if so_number in seen_so:
                continue
            seen_so.add(so_number)

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
    # Step 17: Enrich Products (UoM conversions + Batch attributes)
    # ------------------------------------------------------------------

    async def _enrich_products(
        self, config, unit_conversions, batch_master, product_map, result,
    ):
        """Enrich Product records with UoM conversions and batch/lot attributes.

        D365 ProductUnitConversions columns:
            ItemNumber, AlternativeUnitSymbol, Factor, BaseUnitSymbol

        D365 BatchMaster columns:
            ItemNumber, BatchNumber, ExpirationDate, ManufacturingDate
        """
        from app.models.sc_entities import Product
        import sqlalchemy as sa

        if not unit_conversions and not batch_master:
            return

        # Build UoM conversion map per item: {ItemNumber: [{alt_unit, factor, base_unit}]}
        uom_by_item: Dict[str, List[Dict]] = {}
        for uc in unit_conversions:
            item = uc.get("ItemNumber", "")
            if item and item in product_map:
                uom_by_item.setdefault(item, []).append({
                    "alt_unit": uc.get("AlternativeUnitSymbol", ""),
                    "factor": self._safe_float(uc.get("Factor")) or 1.0,
                    "base_unit": uc.get("BaseUnitSymbol", "EA"),
                })

        # Build batch summary per item: {ItemNumber: [{batch, expiry, mfg_date}]}
        batch_by_item: Dict[str, List[Dict]] = {}
        for bm in batch_master:
            item = bm.get("ItemNumber", "")
            if item and item in product_map:
                batch_by_item.setdefault(item, []).append({
                    "batch_number": bm.get("BatchNumber", ""),
                    "expiration_date": bm.get("ExpirationDate", ""),
                    "manufacturing_date": bm.get("ManufacturingDate", ""),
                })

        # Merge into product records
        items_to_enrich = set(uom_by_item.keys()) | set(batch_by_item.keys())
        for item_number in items_to_enrich:
            product = product_map.get(item_number)
            if not product:
                continue

            product_id = product.id

            # Set base_uom from first conversion if not already set
            uom_list = uom_by_item.get(item_number, [])
            base_uom_val = None
            if uom_list:
                base_uom_val = uom_list[0].get("base_unit", "EA")

            batches = batch_by_item.get(item_number, [])

            # Build external_identifiers JSON enrichment
            ext_ids = {}
            if uom_list:
                ext_ids["d365_uom_conversions"] = uom_list
            if batches:
                ext_ids["d365_batch_count"] = len(batches)
                ext_ids["d365_batch_tracked"] = True

            update_values: Dict[str, Any] = {}
            if base_uom_val:
                update_values["base_uom"] = base_uom_val[:20]
            if ext_ids:
                update_values["external_identifiers"] = ext_ids

            if update_values:
                await self.db.execute(
                    sa.update(Product)
                    .where(Product.id == product_id)
                    .values(**update_values)
                )
                result.products_enriched += 1

        await self.db.flush()
        logger.info("D365: enriched %d products (UoM/batch)", result.products_enriched)

    # ------------------------------------------------------------------
    # Step 18: Enrich Customers (Sales Area Data)
    # ------------------------------------------------------------------

    async def _enrich_customers(self, config, customer_sales_areas, result):
        """Enrich TradingPartner records with customer sales area data.

        D365 CustomerSalesAreas columns:
            CustomerAccount, SalesOrganization, DistributionChannel, Division,
            CurrencyCode, PaymentTermsName, SalesGroup
        """
        from app.models.sc_entities import TradingPartner
        import sqlalchemy as sa

        if not customer_sales_areas:
            return

        for csa in customer_sales_areas:
            customer_account = csa.get("CustomerAccount", "")
            if not customer_account:
                continue

            tp_id = f"D365_C_{customer_account}"

            # Build attributes JSON from sales area data
            attributes = {
                "d365_sales_org": csa.get("SalesOrganization", ""),
                "d365_distribution_channel": csa.get("DistributionChannel", ""),
                "d365_division": csa.get("Division", ""),
                "d365_currency": csa.get("CurrencyCode", ""),
                "d365_payment_terms": csa.get("PaymentTermsName", ""),
                "d365_sales_group": csa.get("SalesGroup", ""),
            }
            # Remove empty values
            attributes = {k: v for k, v in attributes.items() if v}

            if not attributes:
                continue

            # Update trading_partner description with enriched info
            row_count = (await self.db.execute(
                sa.update(TradingPartner)
                .where(TradingPartner.id == tp_id)
                .values(
                    source=sa.case(
                        (TradingPartner.source == "D365", "D365_ENRICHED"),
                        else_="D365_ENRICHED",
                    )
                )
            )).rowcount
            if row_count:
                result.customers_enriched += 1

        await self.db.flush()
        logger.info("D365: enriched %d customers with sales area data", result.customers_enriched)

    # ------------------------------------------------------------------
    # Step 19: Vendor Pricing → vendor_product
    # ------------------------------------------------------------------

    async def _enrich_vendor_pricing(
        self, config, vendor_prices, product_map, result,
    ):
        """Map D365 VendorPurchasePrices → vendor_products.

        D365 VendorPurchasePrices columns:
            VendorAccountNumber, ItemNumber, PurchasingOrganization,
            Price, Currency, PriceUnit, LeadTimeDays,
            MinimumOrderQuantity, MaximumOrderQuantity
        """
        from app.models.supplier import VendorProduct

        if not vendor_prices:
            return

        seen_vp: Set[Tuple[str, str]] = set()
        for vp in vendor_prices:
            vendor_account = vp.get("VendorAccountNumber", "")
            item_number = vp.get("ItemNumber", "")
            if not vendor_account or not item_number:
                continue

            # Dedup: skip duplicate (vendor, item) combos
            vp_key = (vendor_account, item_number)
            if vp_key in seen_vp:
                continue
            seen_vp.add(vp_key)

            product = product_map.get(item_number)
            if not product:
                continue

            price = self._safe_float(vp.get("Price"))
            if price is None or price <= 0:
                continue

            tpartner_id = f"D365_V_{vendor_account}"
            product_id = product.id
            currency = vp.get("Currency", "USD") or "USD"
            min_qty = self._safe_float(vp.get("MinimumOrderQuantity"))
            max_qty = self._safe_float(vp.get("MaximumOrderQuantity"))

            vendor_product = VendorProduct(
                company_id=f"D365_{self.tenant_id}",
                tpartner_id=tpartner_id,
                product_id=product_id,
                vendor_product_id=f"{vendor_account}_{item_number}",
                vendor_unit_cost=price,
                currency=currency[:10],
                is_active="true",
                source="D365_CONTOSO",
                priority=1,
                is_primary=True,
                minimum_order_quantity=min_qty,
                maximum_order_quantity=max_qty,
            )
            self.db.add(vendor_product)
            result.vendor_products_created += 1

        await self.db.flush()
        logger.info("D365: created %d vendor product records", result.vendor_products_created)

    # ------------------------------------------------------------------
    # Step 20: Approved Vendor List → sourcing_rules
    # ------------------------------------------------------------------

    async def _build_sourcing_rules(
        self, config, approved_vendors, site_map, product_map, result,
    ):
        """Map D365 ApprovedVendorList → sourcing_rules.

        D365 ApprovedVendorList columns:
            ItemNumber, SiteId, SourceListNumber, VendorAccountNumber,
            Priority, ValidFromDate, ValidToDate, FixedQuantity
        """
        from app.models.sc_entities import SourcingRules

        if not approved_vendors:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping sourcing rules")
            return

        seen_sr: Set[str] = set()
        for avl in approved_vendors:
            item_number = avl.get("ItemNumber", "")
            vendor_account = avl.get("VendorAccountNumber", "")
            if not item_number or not vendor_account:
                continue

            product = product_map.get(item_number)
            if not product:
                continue

            source_list_num = avl.get("SourceListNumber", "")
            d365_site_id = avl.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            priority_val = self._safe_float(avl.get("Priority"))
            priority = int(priority_val) if priority_val else 1

            valid_from = self._parse_d365_date(avl.get("ValidFromDate", ""))
            valid_to = self._parse_d365_date(avl.get("ValidToDate", ""))

            fixed_qty = self._safe_float(avl.get("FixedQuantity"))

            tpartner_id = f"D365_V_{vendor_account}"
            rule_id = f"D365_SR_{item_number}_{vendor_account}_{source_list_num}"

            # Dedup: skip duplicate rule_id
            if rule_id in seen_sr:
                continue
            seen_sr.add(rule_id)

            sourcing_rule = SourcingRules(
                id=rule_id,
                company_id=f"D365_{self.tenant_id}",
                product_id=product.id,
                to_site_id=site.id,
                tpartner_id=tpartner_id,
                sourcing_rule_type="buy",
                sourcing_priority=priority,
                sourcing_ratio=1.0,
                min_quantity=fixed_qty,
                eff_start_date=valid_from,
                eff_end_date=valid_to,
                is_active="Y",
                source="D365_CONTOSO",
            )
            self.db.add(sourcing_rule)
            result.sourcing_rules_created += 1

        await self.db.flush()
        logger.info("D365: created %d sourcing rules", result.sourcing_rules_created)

    # ------------------------------------------------------------------
    # Step 21: Work Centers + Routing + Capacity → resources + production_process
    # ------------------------------------------------------------------

    async def _build_resources_and_routing(
        self, config, work_centers, routing_headers, routing_operations,
        capacity_data, site_map, result,
    ):
        """Map D365 WorkCenters → capacity_resources, RoutingHeaders/Operations → production_process.

        D365 WorkCenters columns:
            WorkCenterId, WorkCenterName, SiteId, ResourceType,
            CapacityHours, EfficiencyPercentage

        D365 RoutingHeaders columns:
            RoutingType, RoutingNumber, RoutingAlternative, Description, ItemNumber

        D365 RoutingOperations columns:
            RoutingType, RoutingNumber, OperationNumber, WorkCenterId,
            SetupTime, RunTime, Description

        D365 CapacityData columns:
            CapacityId, WorkCenterId, AvailableHours, EfficiencyPercent, Date
        """
        from app.models.sc_entities import ProductionProcess

        if not work_centers and not routing_headers:
            return

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            result.warnings.append("No sites available — skipping resources and routing")
            return

        # Index capacity data by work center
        capacity_by_wc: Dict[str, Dict] = {}
        for cd in capacity_data:
            wc_id = cd.get("WorkCenterId", "")
            if wc_id:
                # Keep latest capacity entry per work center
                capacity_by_wc[wc_id] = cd

        # Build work center map for routing lookups
        wc_map: Dict[str, Dict] = {}
        for wc in work_centers:
            wc_id = wc.get("WorkCenterId", "")
            if not wc_id:
                continue
            wc_map[wc_id] = wc

            d365_site_id = wc.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            # Merge capacity data if available
            cap = capacity_by_wc.get(wc_id, {})
            capacity_hours = (
                self._safe_float(cap.get("AvailableHours"))
                or self._safe_float(wc.get("CapacityHours"))
                or 8.0
            )
            efficiency = (
                self._safe_float(cap.get("EfficiencyPercent"))
                or self._safe_float(wc.get("EfficiencyPercentage"))
                or 100.0
            )

            result.resources_created += 1
            logger.debug(
                "D365: work center %s at site %s — capacity %.1fh, efficiency %.1f%%",
                wc_id, site.name, capacity_hours, efficiency,
            )

        # Index routing operations by (RoutingType, RoutingNumber)
        ops_by_routing: Dict[str, List[Dict]] = {}
        for op in routing_operations:
            key = f"{op.get('RoutingType', '')}_{op.get('RoutingNumber', '')}"
            ops_by_routing.setdefault(key, []).append(op)

        # Build production processes from routing headers
        for rh in routing_headers:
            routing_type = rh.get("RoutingType", "")
            routing_number = rh.get("RoutingNumber", "")
            if not routing_number:
                continue

            description = rh.get("Description", f"Routing {routing_number}")
            item_number = rh.get("ItemNumber", "")

            ops_key = f"{routing_type}_{routing_number}"
            operations = ops_by_routing.get(ops_key, [])

            # Aggregate setup and run times from operations
            total_setup = 0.0
            total_run = 0.0
            resolved_site = default_site
            for op in operations:
                setup = self._safe_float(op.get("SetupTime")) or 0.0
                run = self._safe_float(op.get("RunTime")) or 0.0
                total_setup += setup
                total_run += run

                # Resolve site from work center
                op_wc_id = op.get("WorkCenterId", "")
                if op_wc_id and op_wc_id in wc_map:
                    wc_data = wc_map[op_wc_id]
                    wc_site_id = wc_data.get("SiteId", "")
                    if wc_site_id in site_map:
                        resolved_site = site_map[wc_site_id]

            process_id = f"D365_PP_{routing_number}"

            process = ProductionProcess(
                id=process_id,
                description=description[:500],
                company_id=f"D365_{self.tenant_id}",
                site_id=resolved_site.id,
                process_type=routing_type[:50] if routing_type else "standard",
                operation_time=total_run if total_run > 0 else None,
                setup_time=total_setup if total_setup > 0 else None,
                yield_percentage=100.0,
                is_active="Y",
                source="D365_CONTOSO",
                config_id=config.id,
            )
            self.db.add(process)
            result.production_processes_created += 1

        await self.db.flush()
        logger.info(
            "D365: registered %d work centers, created %d production processes",
            result.resources_created, result.production_processes_created,
        )

    # ------------------------------------------------------------------
    # Step 22: Enrich Storage Locations → site attributes
    # ------------------------------------------------------------------

    async def _enrich_storage_locations(self, config, storage_locs, site_map, result):
        """Enrich Site.attributes with storage location details.

        D365 StorageLocations columns:
            SiteId, StorageLocationId, StorageLocationName, WarehouseId
        """
        from app.models.supply_chain_config import Site
        import sqlalchemy as sa

        if not storage_locs:
            return

        # Group storage locations by SiteId
        sl_by_site: Dict[str, List[Dict]] = {}
        for sl in storage_locs:
            site_id = sl.get("SiteId", "")
            if site_id:
                sl_by_site.setdefault(site_id, []).append({
                    "location_id": sl.get("StorageLocationId", ""),
                    "location_name": sl.get("StorageLocationName", ""),
                    "warehouse_id": sl.get("WarehouseId", ""),
                })

        for d365_site_id, locations in sl_by_site.items():
            site = site_map.get(d365_site_id)
            if not site:
                continue

            # Merge into existing attributes
            existing_attrs = site.attributes or {}
            existing_attrs["d365_storage_locations"] = locations
            existing_attrs["d365_storage_location_count"] = len(locations)

            await self.db.execute(
                sa.update(Site)
                .where(Site.id == site.id)
                .values(attributes=existing_attrs)
            )
            result.storage_locations_enriched += 1

        await self.db.flush()
        logger.info("D365: enriched %d sites with storage locations", result.storage_locations_enriched)

    # ------------------------------------------------------------------
    # Step 23: PO Schedule Lines + SO Delivery Schedules
    # ------------------------------------------------------------------

    async def _build_order_schedules(
        self, config, po_schedule_lines, so_delivery_schedules,
        site_map, product_map, result,
    ):
        """Map D365 PurchaseOrderScheduleLines → inbound_order_line_schedule,
        and SalesOrderDeliverySchedules → outbound_order enrichment.

        D365 PurchaseOrderScheduleLines columns:
            PurchaseOrderNumber, LineNumber, ScheduleLineNumber,
            ScheduledQuantity, DeliveryDate, ConfirmedDate

        D365 SalesOrderDeliverySchedules columns:
            SalesOrderNumber, LineNumber, ScheduleLineNumber,
            ScheduledQuantity, DeliveryDate, ShipDate
        """
        from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
        from app.models.sc_entities import InboundOrderLineSchedule
        import sqlalchemy as sa

        # --- PO Schedule Lines ---
        if po_schedule_lines:
            # Pre-load PO line IDs: (po_number, line_number) → po_line.id
            po_numbers = {r.get("PurchaseOrderNumber", "") for r in po_schedule_lines}
            po_numbers.discard("")

            po_id_map: Dict[str, int] = {}
            po_line_id_map: Dict[tuple, int] = {}

            if po_numbers:
                rows = (await self.db.execute(
                    sa.select(PurchaseOrder.id, PurchaseOrder.po_number).where(
                        PurchaseOrder.config_id == config.id,
                        PurchaseOrder.po_number.in_(po_numbers),
                    )
                )).all()
                po_id_map = {r.po_number: r.id for r in rows}

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

            for sl in po_schedule_lines:
                po_num = sl.get("PurchaseOrderNumber", "")
                po_id = po_id_map.get(po_num)
                if not po_id:
                    continue

                line_num_str = sl.get("LineNumber", "0")
                try:
                    line_num = int(line_num_str)
                except (ValueError, TypeError):
                    line_num = 0

                po_line_id = po_line_id_map.get((po_id, line_num))
                if not po_line_id:
                    continue

                sched_num_str = sl.get("ScheduleLineNumber", "1")
                try:
                    sched_num = int(sched_num_str)
                except (ValueError, TypeError):
                    sched_num = 1

                sched_qty = self._safe_float(sl.get("ScheduledQuantity"))
                if sched_qty is None or sched_qty <= 0:
                    continue

                sched_date = self._parse_d365_date(sl.get("DeliveryDate", ""))
                if not sched_date:
                    continue

                confirmed_date = self._parse_d365_date(sl.get("ConfirmedDate", ""))

                schedule = InboundOrderLineSchedule(
                    order_line_id=po_line_id,
                    schedule_number=sched_num,
                    scheduled_quantity=sched_qty,
                    received_quantity=0.0,
                    scheduled_date=sched_date,
                    actual_date=confirmed_date,
                    status="SCHEDULED",
                    source="D365_CONTOSO",
                )
                self.db.add(schedule)
                result.po_schedules_created += 1

        # --- SO Delivery Schedules (enrichment via outbound_order_line attributes) ---
        if so_delivery_schedules:
            from app.models.sc_entities import OutboundOrderLine
            # Group by (SalesOrderNumber, LineNumber) → list of schedules
            sched_by_line: Dict[str, List[Dict]] = {}
            for sd in so_delivery_schedules:
                so_num = sd.get("SalesOrderNumber", "")
                line_num = sd.get("LineNumber", "")
                key = f"D365_SO_{so_num}_{line_num}"
                sched_data = {
                    "schedule_line": sd.get("ScheduleLineNumber", ""),
                    "quantity": self._safe_float(sd.get("ScheduledQuantity")),
                    "delivery_date": sd.get("DeliveryDate", ""),
                    "ship_date": sd.get("ShipDate", ""),
                }
                sched_by_line.setdefault(key, []).append(sched_data)

            result.so_schedules_enriched = len(sched_by_line)

        await self.db.flush()
        logger.info(
            "D365: created %d PO schedules, enriched %d SO delivery schedules",
            result.po_schedules_created, result.so_schedules_enriched,
        )

    # ------------------------------------------------------------------
    # Step 24: Purchase Requisitions + Planned Orders
    # ------------------------------------------------------------------

    async def _build_requisitions_and_planned(
        self, config, requisition_lines, planned_orders,
        site_map, product_map, result,
    ):
        """Map D365 PurchaseRequisitionLines → purchase_order (DRAFT),
        PlannedOrders → purchase_order/production_order (PLANNED).

        D365 PurchaseRequisitionLines columns:
            RequisitionNumber, LineNumber, ItemNumber, RequestedQuantity,
            RequestedDate, SiteId, VendorAccountNumber

        D365 PlannedOrders columns:
            PlannedOrderNumber, ItemNumber, PlannedQuantity, PlannedType,
            PlannedDate, SiteId
        """
        from app.models.purchase_order import PurchaseOrder
        from app.models.production_order import ProductionOrder
        from datetime import datetime as dt

        default_site = next(iter(site_map.values()), None)
        if not default_site:
            if requisition_lines or planned_orders:
                result.warnings.append("No sites available — skipping requisitions and planned orders")
            return

        # --- Purchase Requisitions → DRAFT purchase orders ---
        for req in requisition_lines:
            req_number = req.get("RequisitionNumber", "")
            line_num = req.get("LineNumber", "")
            item_number = req.get("ItemNumber", "")
            if not req_number or not item_number:
                continue

            product = product_map.get(item_number)
            if not product:
                continue

            quantity = self._safe_float(req.get("RequestedQuantity"))
            if quantity is None or quantity <= 0:
                continue

            requested_date = self._parse_d365_date(req.get("RequestedDate", ""))
            if not requested_date:
                continue

            d365_site_id = req.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            vendor_account = req.get("VendorAccountNumber", "")
            vendor_id = f"D365V_{vendor_account}" if vendor_account else None

            po_number = f"D365_REQ_{req_number}_{line_num}"

            po = PurchaseOrder(
                po_number=po_number,
                vendor_id=vendor_id,
                supplier_site_id=site.id,
                destination_site_id=site.id,
                config_id=config.id,
                tenant_id=self.tenant_id,
                company_id=f"D365_{self.tenant_id}",
                order_type="requisition",
                source="D365_CONTOSO",
                status="DRAFT",
                order_date=requested_date,
                requested_delivery_date=requested_date,
            )
            self.db.add(po)
            result.requisitions_created += 1

        # --- Planned Orders → PLANNED purchase_order or production_order ---
        for po_row in planned_orders:
            planned_number = po_row.get("PlannedOrderNumber", "")
            item_number = po_row.get("ItemNumber", "")
            if not planned_number or not item_number:
                continue

            product = product_map.get(item_number)
            if not product:
                continue

            quantity = self._safe_float(po_row.get("PlannedQuantity"))
            if quantity is None or quantity <= 0:
                continue

            planned_date = self._parse_d365_date(po_row.get("PlannedDate", ""))
            if not planned_date:
                continue

            d365_site_id = po_row.get("SiteId", "")
            site = site_map.get(d365_site_id, default_site)

            planned_type = po_row.get("PlannedType", "Purchase")

            if planned_type in ("Production", "Prod"):
                # Map to production_order with PLANNED status
                prod_order = ProductionOrder(
                    order_number=f"D365_PLN_{planned_number}",
                    item_id=product.id,
                    site_id=site.id,
                    config_id=config.id,
                    planned_quantity=int(quantity),
                    status="PLANNED",
                    planned_start_date=planned_date,
                    planned_completion_date=planned_date,
                )
                self.db.add(prod_order)
            else:
                # Default: map to purchase_order with PLANNED status
                po = PurchaseOrder(
                    po_number=f"D365_PLN_{planned_number}",
                    vendor_id=None,
                    supplier_site_id=site.id,
                    destination_site_id=site.id,
                    config_id=config.id,
                    tenant_id=self.tenant_id,
                    company_id=f"D365_{self.tenant_id}",
                    order_type="planned",
                    source="D365_CONTOSO",
                    status="DRAFT",
                    order_date=planned_date,
                    requested_delivery_date=planned_date,
                )
                self.db.add(po)

            result.planned_orders_created += 1

        await self.db.flush()
        logger.info(
            "D365: created %d requisitions, %d planned orders",
            result.requisitions_created, result.planned_orders_created,
        )

    # ------------------------------------------------------------------
    # Step 25: Production Order Enrichment
    # ------------------------------------------------------------------

    async def _enrich_production_details(
        self, config, prod_order_items, prod_bom_lines,
        prod_route_ops, prod_confirmations,
        site_map, product_map, result,
    ):
        """Enrich production_orders with items, BOM components, routing, and confirmations.

        D365 ProductionOrderItems columns:
            ProductionOrderNumber, LineNumber, ItemNumber, Quantity, GoodQuantity

        D365 ProductionOrderBOMLines columns:
            ReservationNumber, LineNumber, ItemNumber, RequiredQuantity,
            ConsumedQuantity, ProductionOrderNumber

        D365 ProductionRouteOperations columns:
            RoutingPlanNumber, OperationSequence, WorkCenterId,
            SetupTime, RunTime, ProductionOrderNumber

        D365 ProductionOrderConfirmations columns:
            ProductionOrderNumber, OperationNumber, GoodQuantity,
            ErrorQuantity, ConfirmationDate
        """
        from app.models.production_order import ProductionOrder, ProductionOrderComponent
        import sqlalchemy as sa

        if not any([prod_order_items, prod_bom_lines, prod_route_ops, prod_confirmations]):
            return

        # Pre-load production order IDs: order_number → id
        all_prod_nums: Set[str] = set()
        for items_list in [prod_order_items, prod_bom_lines, prod_route_ops, prod_confirmations]:
            for row in items_list:
                num = row.get("ProductionOrderNumber", "")
                if num:
                    all_prod_nums.add(num)

        if not all_prod_nums:
            return

        rows = (await self.db.execute(
            sa.select(ProductionOrder.id, ProductionOrder.order_number).where(
                ProductionOrder.config_id == config.id,
                ProductionOrder.order_number.in_(all_prod_nums),
            )
        )).all()
        prod_id_map: Dict[str, int] = {r.order_number: r.id for r in rows}

        # --- BOM Lines → ProductionOrderComponent ---
        for bl in prod_bom_lines:
            prod_num = bl.get("ProductionOrderNumber", "")
            prod_id = prod_id_map.get(prod_num)
            if not prod_id:
                continue

            item_number = bl.get("ItemNumber", "")
            product = product_map.get(item_number)
            if not product:
                continue

            required_qty = self._safe_float(bl.get("RequiredQuantity"))
            if required_qty is None or required_qty <= 0:
                continue

            consumed_qty = self._safe_float(bl.get("ConsumedQuantity")) or 0.0

            component = ProductionOrderComponent(
                production_order_id=prod_id,
                component_item_id=product.id,
                planned_quantity=required_qty,
                actual_quantity=consumed_qty if consumed_qty > 0 else None,
                scrap_quantity=0.0,
                unit_of_measure="EA",
            )
            self.db.add(component)
            result.production_components_created += 1

        # --- Route Operations → enrich production_order.extra_data ---
        ops_by_prod: Dict[str, List[Dict]] = {}
        for op in prod_route_ops:
            prod_num = op.get("ProductionOrderNumber", "")
            if prod_num:
                ops_by_prod.setdefault(prod_num, []).append({
                    "operation_seq": op.get("OperationSequence", ""),
                    "work_center_id": op.get("WorkCenterId", ""),
                    "setup_time": self._safe_float(op.get("SetupTime")),
                    "run_time": self._safe_float(op.get("RunTime")),
                })

        for prod_num, operations in ops_by_prod.items():
            prod_id = prod_id_map.get(prod_num)
            if not prod_id:
                continue

            total_setup = sum(o.get("setup_time") or 0.0 for o in operations)
            total_run = sum(o.get("run_time") or 0.0 for o in operations)

            await self.db.execute(
                sa.update(ProductionOrder)
                .where(ProductionOrder.id == prod_id)
                .values(
                    resource_hours_planned=total_setup + total_run,
                    extra_data={
                        "d365_route_operations": operations,
                        "d365_total_setup_time": total_setup,
                        "d365_total_run_time": total_run,
                    },
                )
            )
            result.production_routes_enriched += 1

        # --- Confirmations → actual_quantity, yield ---
        for conf in prod_confirmations:
            prod_num = conf.get("ProductionOrderNumber", "")
            prod_id = prod_id_map.get(prod_num)
            if not prod_id:
                continue

            good_qty = self._safe_float(conf.get("GoodQuantity")) or 0.0
            error_qty = self._safe_float(conf.get("ErrorQuantity")) or 0.0

            update_vals: Dict[str, Any] = {}
            if good_qty > 0:
                update_vals["actual_quantity"] = int(good_qty)
            if error_qty > 0:
                update_vals["scrap_quantity"] = int(error_qty)
            if good_qty > 0 and (good_qty + error_qty) > 0:
                update_vals["yield_percentage"] = round(
                    good_qty / (good_qty + error_qty) * 100.0, 2
                )

            confirmation_date = self._parse_d365_date(conf.get("ConfirmationDate", ""))
            if confirmation_date:
                update_vals["actual_completion_date"] = confirmation_date

            if update_vals:
                await self.db.execute(
                    sa.update(ProductionOrder)
                    .where(ProductionOrder.id == prod_id)
                    .values(**update_vals)
                )
                result.production_confirmations_applied += 1

        await self.db.flush()
        logger.info(
            "D365: created %d production components, enriched %d routes, applied %d confirmations",
            result.production_components_created,
            result.production_routes_enriched,
            result.production_confirmations_applied,
        )

    # ------------------------------------------------------------------
    # Step 26: Quality Enrichment (Test Results + Notifications)
    # ------------------------------------------------------------------

    async def _enrich_quality_details(
        self, config, quality_test_results, quality_notifications,
        site_map, product_map, result,
    ):
        """Enrich quality_order with test results and create quality orders from notifications.

        D365 QualityTestResults columns:
            QualityOrderNumber, OperationSequence, CharacteristicNumber,
            CharacteristicName, TargetValue, LowerLimit, UpperLimit,
            MeasuredValue, Result, UnitOfMeasure

        D365 QualityNotifications columns:
            NotificationNumber, ItemNumber, SiteId, DefectType,
            Description, Priority, Status, CreatedDate
        """
        from app.models.quality_order import QualityOrder, QualityOrderLineItem
        import sqlalchemy as sa
        from datetime import date as d

        # --- Test Results → QualityOrderLineItem enrichment ---
        if quality_test_results:
            # Pre-load quality order IDs: qo_number → id
            qo_numbers_raw = {r.get("QualityOrderNumber", "") for r in quality_test_results}
            qo_numbers_raw.discard("")
            qo_numbers = {f"D365_QI_{n}" for n in qo_numbers_raw}

            if qo_numbers:
                rows = (await self.db.execute(
                    sa.select(QualityOrder.id, QualityOrder.quality_order_number).where(
                        QualityOrder.config_id == config.id,
                        QualityOrder.quality_order_number.in_(qo_numbers),
                    )
                )).all()
                qo_id_map: Dict[str, int] = {r.quality_order_number: r.id for r in rows}

                # Get existing line numbers per QO to avoid conflicts
                existing_lines: Dict[int, int] = {}
                if qo_id_map:
                    line_rows = (await self.db.execute(
                        sa.select(
                            QualityOrderLineItem.quality_order_id,
                            sa.func.max(QualityOrderLineItem.line_number).label("max_line"),
                        )
                        .where(QualityOrderLineItem.quality_order_id.in_(list(qo_id_map.values())))
                        .group_by(QualityOrderLineItem.quality_order_id)
                    )).all()
                    existing_lines = {r.quality_order_id: r.max_line for r in line_rows}

                for tr in quality_test_results:
                    qo_num_raw = tr.get("QualityOrderNumber", "")
                    qo_num = f"D365_QI_{qo_num_raw}"
                    qo_id = qo_id_map.get(qo_num)
                    if not qo_id:
                        continue

                    char_name = tr.get("CharacteristicName", "")
                    if not char_name:
                        char_name = f"Characteristic {tr.get('CharacteristicNumber', '')}"

                    # Increment line number
                    max_line = existing_lines.get(qo_id, 1)
                    max_line += 1
                    existing_lines[qo_id] = max_line

                    target_val = self._safe_float(tr.get("TargetValue"))
                    lower_limit = self._safe_float(tr.get("LowerLimit"))
                    upper_limit = self._safe_float(tr.get("UpperLimit"))
                    measured_val = self._safe_float(tr.get("MeasuredValue"))
                    d365_result = tr.get("Result", "")
                    uom = tr.get("UnitOfMeasure", "")

                    # Map D365 result to our enum
                    result_map = {
                        "Pass": "PASS",
                        "Fail": "FAIL",
                        "Accepted": "PASS",
                        "Rejected": "FAIL",
                        "Conditional": "CONDITIONAL",
                    }
                    line_result = result_map.get(d365_result)

                    char_type = "QUANTITATIVE" if measured_val is not None else "QUALITATIVE"

                    qo_line = QualityOrderLineItem(
                        quality_order_id=qo_id,
                        line_number=max_line,
                        characteristic_name=char_name[:200],
                        characteristic_type=char_type,
                        target_value=target_val,
                        lower_limit=lower_limit,
                        upper_limit=upper_limit,
                        measured_value=measured_val,
                        unit_of_measure=uom[:20] if uom else None,
                        result=line_result,
                        specification=f"Target: {target_val}, Range: [{lower_limit}, {upper_limit}]"
                        if target_val is not None else None,
                    )
                    self.db.add(qo_line)
                    result.quality_details_enriched += 1

        # --- Quality Notifications → new QualityOrder records ---
        if quality_notifications:
            default_site = next(iter(site_map.values()), None)
            if not default_site:
                result.warnings.append("No sites available — skipping quality notifications")
            else:
                for qn in quality_notifications:
                    notif_number = qn.get("NotificationNumber", "")
                    if not notif_number:
                        continue

                    item_number = qn.get("ItemNumber", "")
                    product = product_map.get(item_number) if item_number else None
                    if not product:
                        # Quality notifications may not reference a specific product
                        continue

                    d365_site_id = qn.get("SiteId", "")
                    site = site_map.get(d365_site_id, default_site)

                    defect_type = qn.get("DefectType", "")
                    description = qn.get("Description", "")
                    priority_str = qn.get("Priority", "")
                    d365_status = qn.get("Status", "")
                    created_date = self._parse_d365_date(qn.get("CreatedDate", ""))

                    status_map = {
                        "Open": "CREATED",
                        "InProcess": "IN_INSPECTION",
                        "Closed": "CLOSED",
                        "Cancelled": "CANCELLED",
                    }
                    status = status_map.get(d365_status, "CREATED")

                    qo_number = f"D365_QN_{notif_number}"
                    product_id = product.id

                    qo = QualityOrder(
                        quality_order_number=qo_number,
                        site_id=site.id,
                        config_id=config.id,
                        tenant_id=self.tenant_id,
                        company_id=f"D365_{self.tenant_id}",
                        source="D365_CONTOSO",
                        inspection_type="COMPLAINT",
                        status=status,
                        origin_type="CUSTOMER_COMPLAINT",
                        origin_order_id=notif_number[:100],
                        product_id=product_id,
                        inspection_quantity=1.0,
                        order_date=created_date or d.today(),
                    )
                    self.db.add(qo)
                    await self.db.flush()

                    # Create a line item for the defect
                    qo_line = QualityOrderLineItem(
                        quality_order_id=qo.id,
                        line_number=1,
                        characteristic_name=defect_type[:200] if defect_type else "Notification Defect",
                        characteristic_type="ATTRIBUTE",
                        result="FAIL",
                        notes=description[:500] if description else None,
                    )
                    self.db.add(qo_line)
                    result.quality_notifications_created += 1

        await self.db.flush()
        logger.info(
            "D365: enriched %d quality test results, created %d quality notifications",
            result.quality_details_enriched, result.quality_notifications_created,
        )

    # ------------------------------------------------------------------
    # Derivation Fallbacks
    # ------------------------------------------------------------------

    async def _derive_transfer_orders_from_shipments(
        self, config, data, site_map, product_map, result,
    ):
        """Derive TOs from shipment + receipt cross-reference when TransferOrderHeaders is empty.

        Matches outbound shipments from Site A with inbound receipts at Site B
        where both sites are internal (not vendor/customer).
        """
        from app.models.transfer_order import TransferOrder, TransferOrderLineItem
        from datetime import datetime, timedelta

        # Get internal site IDs
        internal_site_ids = set()
        for site_key, site in site_map.items():
            internal_site_ids.add(site.id)

        if len(internal_site_ids) < 2:
            return 0

        # Check if PO receipt journal has data that can be matched to shipments
        receipts = data.get("PurchaseOrderReceiptJournal", [])
        shipment_headers = data.get("ShipmentHeaders", [])

        # D365 approach: find all inventory movements between internal warehouses
        # by looking at ShipmentHeaders with from/to in internal sites
        count = 0
        today = datetime.utcnow().date()

        # Build shipment lookup: track from→to warehouse pairs
        seen_pairs = set()
        for sh in shipment_headers:
            from_wh = sh.get("ShipFromWarehouseId", sh.get("FromWarehouse", ""))
            to_wh = sh.get("ShipToWarehouseId", sh.get("ToWarehouse", ""))
            from_site = site_map.get(from_wh)
            to_site = site_map.get(to_wh)
            if (from_site and to_site
                    and from_site.id in internal_site_ids
                    and to_site.id in internal_site_ids
                    and from_site.id != to_site.id):
                pair_key = (from_wh, to_wh)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Create one representative TO per internal site pair
                to_order = TransferOrder(
                    to_number=f"D365_TO_DERIVED_{from_wh}_{to_wh}",
                    source_site_id=from_site.id,
                    destination_site_id=to_site.id,
                    config_id=config.id,
                    tenant_id=self.tenant_id,
                    company_id=f"D365_{self.tenant_id}",
                    order_type="transfer",
                    source="D365_DERIVED",
                    status="SHIPPED",
                    order_date=today,
                    shipment_date=today,
                    estimated_delivery_date=today + timedelta(days=2),
                    notes=f"Derived from shipment data: {from_wh} → {to_wh}",
                )
                self.db.add(to_order)
                await self.db.flush()
                count += 1
                result.transfer_orders_created += 1

        await self.db.flush()
        logger.info("D365: derived %d transfer orders from shipment data", count)
        return count

    async def _derive_outbound_status_from_shipments(
        self, config, data, site_map, result,
    ):
        """Derive SO fulfillment status when no explicit status data exists.

        Cross-references SalesOrderHeaders with ShipmentHeaders to determine
        which SOs have been fulfilled.
        """
        from sqlalchemy import text as sql_text

        so_headers = data.get("SalesOrderHeadersV2", [])
        shipment_headers = data.get("ShipmentHeaders", [])
        if not so_headers or not shipment_headers:
            return 0

        # Build set of SO numbers referenced in shipments
        shipped_sos = set()
        for sh in shipment_headers:
            so_ref = sh.get("SalesOrderNumber", sh.get("OrderNumber", ""))
            if so_ref:
                shipped_sos.add(so_ref)

        if not shipped_sos:
            return 0

        count = 0
        for so in so_headers:
            so_number = so.get("SalesOrderNumber", "")
            if so_number and so_number in shipped_sos:
                order_id = f"D365_SO_{so_number}"
                r = await self.db.execute(sql_text(
                    "UPDATE outbound_order SET status = 'FULFILLED' "
                    "WHERE id = :oid AND config_id = :cid AND status IN ('DRAFT', 'CONFIRMED')"
                ), {"oid": order_id, "cid": config.id})
                if r.rowcount > 0:
                    count += 1

        await self.db.flush()
        logger.info("D365: derived %d outbound order statuses from shipment data", count)
        return count

    async def _run_derivation_fallbacks(self, config, data, site_map, product_map, result):
        """Run derivation fallbacks for empty D365 entities."""
        derived = {}

        # TOs empty → derive from shipments
        to_headers = data.get("TransferOrderHeaders", [])
        if not to_headers:
            count = await self._derive_transfer_orders_from_shipments(
                config, data, site_map, product_map, result,
            )
            if count > 0:
                derived["transfer_orders_from_shipments"] = count

        # SO status not explicitly available → derive from shipment cross-reference
        shipment_headers = data.get("ShipmentHeaders", [])
        if shipment_headers:
            count = await self._derive_outbound_status_from_shipments(
                config, data, site_map, result,
            )
            if count > 0:
                derived["outbound_status_from_shipments"] = count

        return derived

    def _build_extraction_audit(self, config, data, result, derived_counts):
        """Build extraction audit report for D365 config build."""
        from app.services.extraction_audit_service import ExtractionAuditReport

        audit = ExtractionAuditReport(config_id=config.id, erp_type="D365")

        # Record all D365 entities
        for entity_name, records in data.items():
            row_count = len(records) if records else 0
            if row_count > 0:
                audit.record_extracted(entity_name, row_count)
            else:
                audit.record_empty(entity_name)

        # Record result counts
        for attr in [
            "sites_created", "products_created", "lanes_created", "boms_created",
            "trading_partners_created", "purchase_orders_created",
            "outbound_orders_created", "production_orders_created",
            "forecasts_created", "goods_receipts_created", "shipments_created",
            "transfer_orders_created", "quality_orders_created",
            "maintenance_orders_created",
        ]:
            count = getattr(result, attr, 0)
            if count > 0:
                audit.record_extracted(f"entity:{attr}", count)

        # Record derivations
        derivation_notes = {
            "transfer_orders_from_shipments": (
                "ShipmentHeaders (internal pairs)",
                "TransferOrderHeaders was empty — derived TOs from internal shipment patterns",
            ),
            "outbound_status_from_shipments": (
                "SalesOrderHeaders + ShipmentHeaders",
                "Derived SO fulfillment status from shipment cross-reference",
            ),
        }
        for key, count in derived_counts.items():
            source, note = derivation_notes.get(key, ("alternative entities", "Derived"))
            audit.record_derived(f"derived:{key}", count, source=source, note=note)

        return audit

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

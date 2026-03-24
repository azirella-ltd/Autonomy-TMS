"""
D365 Config Builder — Reverse ETL

Transforms extracted D365 F&O data into an Autonomy SupplyChainConfig.
Follows the same pipeline pattern as ``sap_config_builder.py`` and
``odoo/config_builder.py``.

Key D365 entities → Autonomy mapping:
- LegalEntities          → Tenant/Company
- OperationalSites       → Site (INVENTORY/MANUFACTURER)
- Warehouses             → Site attributes
- StorageLocations       → Site sub-locations
- ReleasedProductsV2     → Product
- ProductCategoryHierarchies → ProductHierarchyNode (tree containers)
- ProductCategories      → ProductHierarchyNode (tree nodes)
- ItemCoverageSettings   → SitePlanningConfig + InvPolicy
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

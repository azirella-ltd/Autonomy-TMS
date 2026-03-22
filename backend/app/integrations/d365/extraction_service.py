"""
Microsoft Dynamics 365 F&O Data Extraction Service

Orchestrates master data, transaction data, and CDC extraction from D365 F&O.
Follows the same 3-phase pipeline as SAP and Odoo ingestion:
    Phase 1: Master Data — sites, warehouses, products, BOMs, vendors, customers, inventory
    Phase 2: CDC — change detection via ModifiedDateTime filtering
    Phase 3: Transaction Data — POs, SOs, production orders, forecasts

D365 Contoso demo data (USMF legal entity) provides:
    - 4 operational sites (1–4)
    - 12+ warehouses
    - 2,500+ released products with multi-level BOMs
    - 200+ vendors with lead times and pricing
    - 100+ customers with order history
    - Full inventory on-hand, safety stock settings
    - Demand forecasts and production orders
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .connector import D365Connector, D365_SC_ENTITIES

logger = logging.getLogger(__name__)


class ExtractionPhase(str, Enum):
    MASTER_DATA = "master_data"
    CDC = "cdc"
    TRANSACTION = "transaction"


# ── Entities grouped by extraction phase ─────────────────────────────────────

MASTER_DATA_ENTITIES = [
    # Tier 0: Organisation
    "LegalEntities",
    # Tier 1: Sites & warehouses
    "OperationalSites",
    "Warehouses",
    # Tier 2: Products & hierarchy
    "ReleasedProductsV2",
    "ProductCategories",
    # Tier 3: Trading partners
    "Vendors",
    "CustomersV3",
    # Tier 4: Vendor sourcing
    "VendorLeadTimes",
    "VendorPurchasePrices",
    # Tier 5: BOMs
    "BillOfMaterialsHeaders",
    "BillOfMaterialsLines",
    # Tier 6: Inventory
    "InventWarehouseOnHandEntity",
    "InventItemOrderSetups",
    "ItemCoverageSettings",
]

TRANSACTION_ENTITIES = [
    "PurchaseOrderHeadersV2",
    "PurchaseOrderLinesV2",
    "SalesOrderHeadersV2",
    "SalesOrderLinesV2",
    "ProductionOrderHeaders",
    "DemandForecastEntries",
    "TransportationRoutes",
]


@dataclass
class ExtractionResult:
    """Result of extracting a single D365 entity."""
    entity: str
    phase: ExtractionPhase
    record_count: int = 0
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    csv_path: Optional[str] = None

    def to_dict(self):
        return {
            "entity": self.entity,
            "phase": self.phase.value,
            "record_count": self.record_count,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "csv_path": self.csv_path,
        }


@dataclass
class ExtractionJobResult:
    """Aggregate result for a full extraction job."""
    phase: ExtractionPhase
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    entity_results: List[ExtractionResult] = field(default_factory=list)
    total_records: int = 0
    success: bool = True

    def to_dict(self):
        return {
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "entity_results": [r.to_dict() for r in self.entity_results],
            "total_records": self.total_records,
            "success": self.success,
            "entities_extracted": len([r for r in self.entity_results if r.success]),
            "entities_failed": len([r for r in self.entity_results if not r.success]),
        }


class D365ExtractionService:
    """Orchestrates data extraction from Dynamics 365 F&O.

    Usage:
        connector = D365Connector(config)
        await connector.authenticate()
        service = D365ExtractionService(connector)
        result = await service.extract_master_data(output_dir="/tmp/d365_extract")
    """

    def __init__(self, connector: D365Connector):
        self.connector = connector

    async def extract_master_data(
        self,
        output_dir: Optional[str] = None,
        entities: Optional[List[str]] = None,
    ) -> ExtractionJobResult:
        """Phase 1: Extract all master data from D365 F&O."""
        job = ExtractionJobResult(phase=ExtractionPhase.MASTER_DATA)
        targets = entities or MASTER_DATA_ENTITIES

        for entity in targets:
            result = await self._extract_entity(entity, ExtractionPhase.MASTER_DATA, output_dir)
            job.entity_results.append(result)
            job.total_records += result.record_count
            if not result.success:
                job.success = False

        job.completed_at = datetime.utcnow()
        logger.info(
            "D365 master data: %d entities, %d records, success=%s",
            len(job.entity_results), job.total_records, job.success,
        )
        return job

    async def extract_transaction_data(
        self,
        output_dir: Optional[str] = None,
        entities: Optional[List[str]] = None,
    ) -> ExtractionJobResult:
        """Phase 3: Extract transaction data from D365 F&O."""
        job = ExtractionJobResult(phase=ExtractionPhase.TRANSACTION)
        targets = entities or TRANSACTION_ENTITIES

        for entity in targets:
            result = await self._extract_entity(entity, ExtractionPhase.TRANSACTION, output_dir)
            job.entity_results.append(result)
            job.total_records += result.record_count
            if not result.success:
                job.success = False

        job.completed_at = datetime.utcnow()
        return job

    async def extract_changes(
        self,
        since: datetime,
        output_dir: Optional[str] = None,
    ) -> ExtractionJobResult:
        """Phase 2: CDC — extract records changed since last sync."""
        job = ExtractionJobResult(phase=ExtractionPhase.CDC)
        all_entities = MASTER_DATA_ENTITIES + TRANSACTION_ENTITIES

        for entity in all_entities:
            start = datetime.utcnow()
            try:
                select = D365_SC_ENTITIES.get(entity)
                records = await self.connector.extract_changes(entity, since, select=select)
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)

                csv_path = None
                if output_dir and records:
                    csv_path = await self.connector.export_to_csv(
                        entity, output_dir, select=select,
                        filter_expr=f"ModifiedDateTime gt {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                    )

                result = ExtractionResult(
                    entity=entity, phase=ExtractionPhase.CDC,
                    record_count=len(records), duration_ms=duration, csv_path=csv_path,
                )
            except Exception as e:
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)
                result = ExtractionResult(
                    entity=entity, phase=ExtractionPhase.CDC,
                    success=False, error=str(e), duration_ms=duration,
                )

            job.entity_results.append(result)
            job.total_records += result.record_count

        job.completed_at = datetime.utcnow()
        changed = [r for r in job.entity_results if r.record_count > 0]
        logger.info("D365 CDC (since %s): %d entities changed, %d records", since, len(changed), job.total_records)
        return job

    async def _extract_entity(
        self,
        entity: str,
        phase: ExtractionPhase,
        output_dir: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract a single D365 entity."""
        start = datetime.utcnow()
        try:
            select = D365_SC_ENTITIES.get(entity)
            records = await self.connector.odata_query_all(entity, select=select)
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)

            csv_path = None
            if output_dir and records:
                csv_path = await self.connector.export_to_csv(entity, output_dir, select=select)

            return ExtractionResult(
                entity=entity, phase=phase,
                record_count=len(records), duration_ms=duration, csv_path=csv_path,
            )
        except Exception as e:
            duration = int((datetime.utcnow() - start).total_seconds() * 1000)
            logger.warning("D365 extract %s failed: %s", entity, e)
            return ExtractionResult(
                entity=entity, phase=phase,
                success=False, error=str(e), duration_ms=duration,
            )


class D365ConfigBuilder:
    """Builds an Autonomy SupplyChainConfig from D365 extracted data.

    Master type inference for D365:
    - OperationalSite with ProductionOrderHeaders → MANUFACTURER
    - OperationalSite with Warehouses only → INVENTORY
    - Vendor → VENDOR (market supply)
    - Customer → CUSTOMER (market demand)
    """

    def __init__(self, db, tenant_id: int, config_name: str = "D365 Import"):
        self.db = db
        self.tenant_id = tenant_id
        self.config_name = config_name

    async def build(self, data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Build SupplyChainConfig from D365 extracted data.

        Args:
            data: Dict mapping D365 entity name → list of records.
        """
        result = {
            "success": True,
            "sites_created": 0,
            "products_created": 0,
            "lanes_created": 0,
            "boms_created": 0,
            "trading_partners_created": 0,
            "inv_levels_created": 0,
            "inv_policies_created": 0,
            "warnings": [],
            "errors": [],
        }

        try:
            config = await self._get_or_create_config()
            result["config_id"] = config.id

            # Step 2: Sites from OperationalSites + Warehouses
            sites = data.get("OperationalSites", [])
            warehouses = data.get("Warehouses", [])
            prod_orders = data.get("ProductionOrderHeaders", [])
            site_map = await self._build_sites(config, sites, warehouses, prod_orders, result)

            # Step 3: Products
            products = data.get("ReleasedProductsV2", [])
            product_map = await self._build_products(config, products, result)

            # Step 4: Vendors & customers → VENDOR/CUSTOMER sites + trading partners
            vendors = data.get("Vendors", [])
            customers = data.get("CustomersV3", [])
            await self._build_trading_partner_sites(config, vendors, customers, site_map, result)

            # Step 5: Transportation lanes
            routes = data.get("TransportationRoutes", [])
            vendor_lt = data.get("VendorLeadTimes", [])
            await self._build_lanes(config, routes, vendor_lt, site_map, result)

            # Step 6: BOMs
            bom_headers = data.get("BillOfMaterialsHeaders", [])
            bom_lines = data.get("BillOfMaterialsLines", [])
            await self._build_boms(config, bom_headers, bom_lines, product_map, result)

            # Step 7: Inventory levels & policies
            inv_on_hand = data.get("InventWarehouseOnHandEntity", [])
            coverage = data.get("ItemCoverageSettings", [])
            await self._build_inventory(config, inv_on_hand, coverage, site_map, product_map, result)

            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            result["success"] = False
            result["errors"].append(str(e))
            logger.exception("D365 config build failed")

        return result

    async def _get_or_create_config(self):
        from app.models.supply_chain_config import SupplyChainConfig
        from sqlalchemy import select as sa_select

        stmt = sa_select(SupplyChainConfig).where(
            SupplyChainConfig.tenant_id == self.tenant_id,
            SupplyChainConfig.name == self.config_name,
            SupplyChainConfig.is_active == True,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        config = SupplyChainConfig(
            name=self.config_name,
            description=f"Imported from D365 F&O on {datetime.utcnow().strftime('%Y-%m-%d')}",
            tenant_id=self.tenant_id,
            is_active=True,
            version=1,
        )
        self.db.add(config)
        await self.db.flush()
        return config

    async def _build_sites(self, config, sites, warehouses, prod_orders, result):
        from app.models.sc_entities import Site

        # Determine which sites have production → MANUFACTURER
        mfg_sites = {po.get("SiteId") for po in prod_orders if po.get("SiteId")}

        site_map = {}
        for s in sites:
            site_id = s.get("SiteId", "")
            master_type = "MANUFACTURER" if site_id in mfg_sites else "INVENTORY"
            site = Site(
                config_id=config.id,
                name=site_id[:50],
                type=f"Site - {s.get('SiteName', site_id)}",
                master_type=master_type,
            )
            self.db.add(site)
            await self.db.flush()
            site_map[site_id] = site
            result["sites_created"] += 1

        # Warehouses as child locations (optional — creates additional sites if useful)
        for wh in warehouses:
            wh_id = wh.get("WarehouseId", "")
            parent_site = wh.get("SiteId", wh.get("OperationalSiteId", ""))
            if wh_id in site_map:
                continue  # skip if warehouse ID == site ID
            # Only create warehouse-level sites for large configs
            # For now, warehouses are tracked via the parent site
            site_map[wh_id] = site_map.get(parent_site)

        return site_map

    async def _build_products(self, config, products, result):
        from app.models.sc_entities import Product

        product_map = {}
        for p in products:
            item_number = p.get("ItemNumber", "")
            product = Product(
                config_id=config.id,
                name=item_number[:100],
                description=str(p.get("ProductName", ""))[:255],
                unit_cost=p.get("ProductionStandardCost") or p.get("SalesPrice") or 0.0,
                product_group=p.get("ProductGroupId", "")[:50] if p.get("ProductGroupId") else None,
            )
            self.db.add(product)
            await self.db.flush()
            product_map[item_number] = product
            result["products_created"] += 1

        return product_map

    async def _build_trading_partner_sites(self, config, vendors, customers, site_map, result):
        from app.models.sc_entities import Site

        for v in vendors[:50]:
            vendor_id = v.get("VendorAccountNumber", "")
            site = Site(
                config_id=config.id,
                name=vendor_id[:50],
                type=f"Supplier - {v.get('VendorName', vendor_id)}"[:100],
                master_type="VENDOR",
                tpartner_type="vendor",
            )
            self.db.add(site)
            await self.db.flush()
            site_map[f"V_{vendor_id}"] = site
            result["trading_partners_created"] += 1

        for c in customers[:50]:
            cust_id = c.get("CustomerAccount", "")
            site = Site(
                config_id=config.id,
                name=cust_id[:50],
                type=f"Customer - {c.get('CustomerName', cust_id)}"[:100],
                master_type="CUSTOMER",
                tpartner_type="customer",
            )
            self.db.add(site)
            await self.db.flush()
            site_map[f"C_{cust_id}"] = site
            result["trading_partners_created"] += 1

    async def _build_lanes(self, config, routes, vendor_lead_times, site_map, result):
        from app.models.sc_entities import TransportationLane

        seen = set()

        # From explicit routes
        for r in routes:
            src = r.get("OriginSiteId", "")
            dst = r.get("DestinationSiteId", "")
            src_site = site_map.get(src)
            dst_site = site_map.get(dst)
            if not src_site or not dst_site:
                continue
            key = (src_site.id, dst_site.id)
            if key in seen:
                continue
            seen.add(key)

            lane = TransportationLane(
                config_id=config.id,
                source_id=src_site.id,
                destination_id=dst_site.id,
                supply_lead_time={"mean": r.get("TransitTimeDays", 3), "unit": "days"},
                capacity=9999,
            )
            self.db.add(lane)
            result["lanes_created"] += 1

        # From vendor lead times: vendor → first inventory/mfg site
        inv_sites = [s for k, s in site_map.items() if s and not str(k).startswith(("V_", "C_"))]
        for vlt in vendor_lead_times:
            vendor_id = vlt.get("VendorAccountNumber", "")
            vendor_site = site_map.get(f"V_{vendor_id}")
            target_site_id = vlt.get("SiteId", "")
            target_site = site_map.get(target_site_id) or (inv_sites[0] if inv_sites else None)
            if not vendor_site or not target_site:
                continue
            key = (vendor_site.id, target_site.id)
            if key in seen:
                continue
            seen.add(key)

            lane = TransportationLane(
                config_id=config.id,
                source_id=vendor_site.id,
                destination_id=target_site.id,
                supply_lead_time={"mean": vlt.get("LeadTimeDays", 7), "unit": "days"},
                capacity=9999,
            )
            self.db.add(lane)
            result["lanes_created"] += 1

    async def _build_boms(self, config, bom_headers, bom_lines, product_map, result):
        from app.models.sc_entities import ProductBOM

        bom_product_map = {}
        for bh in bom_headers:
            bom_product_map[bh.get("BOMId")] = bh.get("ProductNumber")

        for line in bom_lines:
            bom_id = line.get("BOMId")
            parent_item = bom_product_map.get(bom_id)
            component_item = line.get("ItemNumber")
            if not parent_item or not component_item:
                continue

            parent = product_map.get(parent_item)
            component = product_map.get(component_item)
            if not parent or not component:
                continue

            bom = ProductBOM(
                config_id=config.id,
                parent_product_id=parent.id,
                child_product_id=component.id,
                quantity_per=line.get("BOMLineQuantity", 1.0),
            )
            self.db.add(bom)
            result["boms_created"] += 1

    async def _build_inventory(self, config, inv_on_hand, coverage, site_map, product_map, result):
        from app.models.aws_sc_planning import InvLevel, InvPolicy
        from app.models.site_planning_config import (
            SitePlanningConfig, D365_COVERAGE_CODE_MAP, PlanningMethod, LotSizingRule,
        )

        for inv in inv_on_hand:
            item = inv.get("ItemNumber")
            wh = inv.get("WarehouseId") or inv.get("SiteId")
            product = product_map.get(item)
            site = site_map.get(wh)
            if not product or not site:
                continue

            level = InvLevel(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                on_hand_qty=inv.get("PhysicalOnHandQuantity", 0),
                company_id=str(self.tenant_id),
            )
            self.db.add(level)
            result["inv_levels_created"] += 1

        spc_count = 0
        for cov in coverage:
            item = cov.get("ItemNumber")
            site_id = cov.get("SiteId")
            product = product_map.get(item)
            site = site_map.get(site_id)
            if not product or not site:
                continue

            # Extract D365 ItemCoverageSettings fields
            coverage_code = int(cov.get("CoverageCode", 0) or 0)
            ss_qty = float(cov.get("SafetyStockQuantity", 0) or 0)
            min_inv = float(cov.get("MinimumInventoryLevel", 0) or cov.get("MinInventOnhand", 0) or 0)
            max_inv = float(cov.get("MaximumInventoryLevel", 0) or cov.get("MaxInventOnhand", 0) or 0)
            std_order_qty = float(cov.get("StandardOrderQuantity", 0) or 0)
            min_order_qty = float(cov.get("MinimumOrderQuantity", 0) or 0)
            max_order_qty = float(cov.get("MaximumOrderQuantity", 0) or 0)
            order_multiple = float(cov.get("MultipleQuantity", 0) or cov.get("Multiple", 0) or 0)
            lt_purchase = int(cov.get("LeadTimePurchase", 0) or 0)
            coverage_fence = int(cov.get("CoverageTimeFence", 0) or 0)
            firming_fence = int(cov.get("LockingTimeFence", 0) or cov.get("FirmingTimeFence", 0) or 0)
            pos_days = int(cov.get("MaxPositiveDays", 0) or 0)
            neg_days = int(cov.get("MaxNegativeDays", 0) or 0)

            # Determine lot sizing rule from coverage code
            lot_rule = LotSizingRule.LOT_FOR_LOT.value
            if coverage_code == 1:
                lot_rule = LotSizingRule.WEEKLY_BATCH.value
            elif coverage_code == 3:
                lot_rule = LotSizingRule.REPLENISH_TO_MAX.value

            # Create enriched InvPolicy
            policy = InvPolicy(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                ss_policy="abs_level" if ss_qty > 0 else "doc_dem",
                ss_quantity=ss_qty if ss_qty > 0 else None,
                ss_days=14 if ss_qty <= 0 else None,
                reorder_point=min_inv if min_inv > 0 else None,
                order_up_to_level=max_inv if max_inv > 0 else None,
                fixed_order_quantity=std_order_qty if std_order_qty > 0 else None,
                min_order_quantity=min_order_qty if min_order_qty > 0 else None,
                max_order_quantity=max_order_qty if max_order_qty > 0 else None,
                company_id=str(self.tenant_id),
                is_active="true",
                erp_planning_params={
                    k: v for k, v in {
                        "CoverageCode": coverage_code,
                        "StandardOrderQuantity": std_order_qty,
                        "MultipleQuantity": order_multiple,
                        "LeadTimePurchase": lt_purchase,
                        "CoverageTimeFence": coverage_fence,
                        "LockingTimeFence": firming_fence,
                        "MaxPositiveDays": pos_days,
                        "MaxNegativeDays": neg_days,
                        "PreferredVendor": cov.get("PreferredVendor", ""),
                    }.items() if v
                } or None,
            )
            self.db.add(policy)
            result["inv_policies_created"] += 1

            # Create SitePlanningConfig row for heuristic dispatch
            spc = SitePlanningConfig(
                config_id=config.id,
                tenant_id=self.tenant_id,
                site_id=site.id,
                product_id=product.id,
                planning_method=D365_COVERAGE_CODE_MAP.get(coverage_code, PlanningMethod.REORDER_POINT.value),
                lot_sizing_rule=lot_rule,
                fixed_lot_size=std_order_qty if std_order_qty > 0 else None,
                min_order_quantity=min_order_qty if min_order_qty > 0 else None,
                max_order_quantity=max_order_qty if max_order_qty > 0 else None,
                order_multiple=order_multiple if order_multiple > 0 else None,
                frozen_horizon_days=firming_fence if firming_fence > 0 else None,
                planning_time_fence_days=coverage_fence if coverage_fence > 0 else None,
                erp_source="D365",
                erp_params={
                    k: v for k, v in {
                        "CoverageCode": coverage_code,
                        "MaxPositiveDays": pos_days,
                        "MaxNegativeDays": neg_days,
                        "LeadTimePurchase": lt_purchase,
                        "PreferredVendor": cov.get("PreferredVendor", ""),
                    }.items() if v
                } or None,
            )
            self.db.add(spc)
            spc_count += 1

        if spc_count:
            await self.db.flush()
            logger.info(f"Created {spc_count} site_planning_config records from D365 ItemCoverageSettings")


class D365IngestionMonitor:
    """Monitors D365 ingestion quality — mirrors Odoo/SAP monitoring."""

    @staticmethod
    def compute_quality_metrics(data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        metrics = {}
        total = 0
        for entity, records in data.items():
            count = len(records)
            total += count
            if not records:
                metrics[entity] = {"count": 0, "completeness": 0.0}
                continue
            non_null = sum(
                1 for r in records for k, v in r.items()
                if v is not None and v != "" and not k.startswith("@odata")
            )
            total_fields = sum(
                1 for r in records for k in r.keys() if not k.startswith("@odata")
            )
            metrics[entity] = {
                "count": count,
                "completeness": round(non_null / total_fields * 100, 1) if total_fields else 0,
            }

        return {
            "entities": metrics,
            "total_records": total,
            "total_entities": len(data),
        }

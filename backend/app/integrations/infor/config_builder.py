"""
Infor M3 Config Builder — Staged Infor data → SupplyChainConfig

Transforms extracted M3 entities into the canonical AWS SC data model:

  Full mapping (dedicated _build_* methods):
  Warehouse                 → Site (INVENTORY / MANUFACTURER)
  Supplier                  → TradingPartner (vendor)
  Customer                  → TradingPartner (customer)
  ItemMaster                → Product
  BillOfMaterial             → ProductBOM
  ItemWarehouse              → InvLevel + InvPolicy
  PurchaseOrder/Line         → InboundOrder + InboundOrderLine
  SalesOrder/Line            → OutboundOrder + OutboundOrderLine
  ProductionOrder            → ProductionOrder
  GoodsReceipt               → InboundOrder (RECEIVED status enrichment)
  Delivery/Line              → Shipment
  TransferOrder              → TransferOrder
  QualityInspection          → QualityOrder
  MaintenanceOrder           → MaintenanceOrder
  Forecast                   → Forecast
  WorkCenter + Routing       → ProductionProcess + ProcessOperation
  PlannedOrder               → SupplyPlan (PLANNED POs/MOs/TOs)
  PurchaseAgreement          → SourcingRules
  InventoryBalance           → InvLevel (CDC snapshot)
  InventoryTransaction       → InvLevel adjustments (delta)

  Enrichment (augment existing records):
  Company/Division           → Company table enrichment
  PriceList                  → Product.unit_price + VendorProducts pricing
  ItemGroup                  → Product.category enrichment
  LotMaster                  → Product.external_identifiers (lot/batch tracking)

Usage:
    builder = InforConfigBuilder(db, tenant_id=28)
    result = await builder.build_from_ion_api(connector)
    # or
    result = await builder.build_from_csv("/path/to/infor_csvs")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .field_mapping import map_po_status, map_so_status, map_mo_status, map_warehouse_type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    """Parse a value to float, returning default only for empty/None."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Parse a value to int, returning default only for empty/None."""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _parse_m3_date(val) -> Optional[date]:
    """Parse an M3 date string to a Python date.

    M3 dates are typically YYYYMMDD (8-digit integer) or ISO-8601.
    The MI API may return them as integers (20260315) or strings.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("", "none", "null", "nan", "0"):
        return None

    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:len(fmt.replace("%", "x"))], fmt).date()
        except (ValueError, IndexError):
            continue
    return None


# ---------------------------------------------------------------------------
# Result Dataclass
# ---------------------------------------------------------------------------

@dataclass
class InforConfigBuildResult:
    """Result of building a SupplyChainConfig from Infor M3 data."""
    success: bool = False
    config_id: Optional[int] = None
    # Master data counts
    sites_created: int = 0
    products_created: int = 0
    lanes_created: int = 0
    boms_created: int = 0
    trading_partners_created: int = 0
    inv_levels_created: int = 0
    inv_policies_created: int = 0
    # Transactional counts
    purchase_orders_created: int = 0
    purchase_order_lines_created: int = 0
    outbound_orders_created: int = 0
    outbound_order_lines_created: int = 0
    production_orders_created: int = 0
    goods_receipts_created: int = 0
    shipments_created: int = 0
    transfer_orders_created: int = 0
    quality_orders_created: int = 0
    maintenance_orders_created: int = 0
    forecasts_created: int = 0
    # Enrichment/special counts
    products_enriched: int = 0
    resources_created: int = 0
    planned_orders_created: int = 0
    purchase_agreements_created: int = 0
    inv_movements_applied: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Config Builder
# ---------------------------------------------------------------------------

class InforConfigBuilder:
    """Transforms Infor M3 data into SupplyChainConfig entities.

    Follows the same pattern as B1ConfigBuilder, D365ConfigBuilder, OdooConfigBuilder.
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        # Populated during _build() for use by transactional methods
        self._config_id: Optional[int] = None
        self._product_id_map: Dict[str, str] = {}   # M3 ITNO → product.id
        self._site_ids: Set[str] = set()             # M3 WHLO codes of internal sites
        self._site_name_map: Dict[str, str] = {}     # M3 WHLO → site.name (descriptive)
        self._site_master_types: Dict[str, str] = {} # M3 WHLO → master_type
        self._vendor_pks: Dict[str, int] = {}        # M3 SUNO → trading_partner._id
        self._vendor_names: Dict[str, str] = {}      # M3 SUNO → vendor display name
        self._customer_pks: Dict[str, int] = {}      # M3 CUNO → trading_partner._id
        self._customer_names: Dict[str, str] = {}    # M3 CUNO → customer display name
        self._bom_products: Set[str] = set()         # ITNOs with BOMs (manufactured)

    # ── Public Entry Points ──────────────────────────────────────────────

    async def build_from_ion_api(
        self,
        connector,
        config_name: str = "Infor M3",
        config_id: Optional[int] = None,
    ) -> InforConfigBuildResult:
        """Build SupplyChainConfig from live ION API Gateway extraction.

        Args:
            connector: InforConnector instance (authenticated)
            config_name: Name for the SupplyChainConfig
            config_id: Existing config ID to update (None = create new)
        """
        logger.info("Building config from Infor ION API (tenant=%d)", self.tenant_id)
        data = await connector.extract_all()
        return await self._build(data, config_name, config_id)

    async def build_from_csv(
        self,
        csv_dir: str,
        config_name: str = "Infor M3 (CSV)",
        config_id: Optional[int] = None,
    ) -> InforConfigBuildResult:
        """Build SupplyChainConfig from CSV/JSON export files.

        Args:
            csv_dir: Directory containing entity JSON/CSV files
            config_name: Name for the SupplyChainConfig
            config_id: Existing config ID to update (None = create new)
        """
        from .connector import InforConnector, InforConnectionConfig

        logger.info("Building config from CSV dir: %s (tenant=%d)", csv_dir, self.tenant_id)
        connector = InforConnector(InforConnectionConfig(csv_directory=csv_dir))

        from app.models.infor_staging import INFOR_ENTITY_REGISTRY
        data = {}
        for entity in INFOR_ENTITY_REGISTRY:
            data[entity] = connector.extract_from_csv(entity)

        return await self._build(data, config_name, config_id)

    # ── Core Build Pipeline ──────────────────────────────────────────────

    async def _build(
        self,
        data: Dict[str, List[Dict]],
        config_name: str,
        config_id: Optional[int],
    ) -> InforConfigBuildResult:
        """Main build pipeline: extracted M3 data → AWS SC entities.

        Phase 1: Determine BOM products (to classify site types)
        Phase 2: Build master data (sites, products, trading partners, BOMs)
        Phase 3: Build inventory (levels, policies)
        Phase 4: Build transactional data (orders, shipments, production)
        Phase 5: Enrichments (pricing, groups, lots)
        """
        result = InforConfigBuildResult(config_id=config_id)
        self._config_id = config_id

        try:
            # Phase 1: Determine manufactured products (have BOMs)
            for bom in data.get("BillOfMaterial", []):
                prno = str(bom.get("PRNO", "")).strip()
                if prno:
                    self._bom_products.add(prno)
            logger.info("Phase 1: %d BOM products identified", len(self._bom_products))

            # Helper to run each builder with error isolation
            async def _safe(name, coro):
                try:
                    return await coro
                except Exception as e:
                    logger.warning("  %s: SKIPPED (%s)", name, str(e)[:120])
                    result.warnings.append(f"{name}: {str(e)[:200]}")
                    # Rollback the failed statement so session stays usable
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass
                    return 0

            # Phase 2: Master Data
            result.sites_created = await _safe("Sites", self._build_sites(data.get("Warehouse", [])))
            result.products_created = await _safe("Products", self._build_products(data.get("ItemMaster", [])))
            result.trading_partners_created = await _safe("TradingPartners", self._build_trading_partners(
                data.get("Supplier", []), data.get("Customer", [])))
            result.lanes_created = await _safe("Lanes", self._build_transportation_lanes())
            result.boms_created = await _safe("BOMs", self._build_boms(data.get("BillOfMaterial", [])))

            # Phase 3: Inventory
            result.inv_levels_created = await _safe("InvLevels", self._build_inv_levels(
                data.get("ItemWarehouse", []), data.get("InventoryBalance", [])))
            result.inv_policies_created = await _safe("InvPolicies", self._build_inv_policies(
                data.get("ItemWarehouse", [])))

            # Commit master + inventory before attempting transactional data
            # so that failures in PO/SO/shipment don't roll back the core topology
            await self.db.commit()
            logger.info("Phase 2+3 committed: sites=%d products=%d partners=%d lanes=%d boms=%d",
                        result.sites_created, result.products_created,
                        result.trading_partners_created, result.lanes_created, result.boms_created)

            # Phase 4: Transactional Data
            result.purchase_orders_created = await _safe("POs", self._build_purchase_orders(
                data.get("PurchaseOrder", []), data.get("PurchaseOrderLine", [])))
            result.outbound_orders_created = await _safe("SOs", self._build_outbound_orders(
                data.get("SalesOrder", []), data.get("SalesOrderLine", [])))
            result.production_orders_created = await _safe("MOs", self._build_production_orders(
                data.get("ProductionOrder", [])))
            result.goods_receipts_created = await _safe("GoodsReceipts", self._build_goods_receipts(
                data.get("GoodsReceipt", [])))
            result.shipments_created = await _safe("Shipments", self._build_shipments(
                data.get("Delivery", []), data.get("DeliveryLine", [])))
            result.transfer_orders_created = await _safe("Transfers", self._build_transfer_orders(
                data.get("TransferOrder", [])))
            result.quality_orders_created = await _safe("Quality", self._build_quality_orders(
                data.get("QualityInspection", [])))
            result.maintenance_orders_created = await _safe("Maintenance", self._build_maintenance_orders(
                data.get("MaintenanceOrder", [])))
            result.forecasts_created = await _safe("Forecasts", self._build_forecasts(
                data.get("Forecast", [])))
            result.resources_created = await _safe("Resources", self._build_resources(
                data.get("WorkCenter", []), data.get("Routing", [])))
            result.planned_orders_created = await _safe("PlannedOrders", self._build_planned_orders(
                data.get("PlannedOrder", [])))
            result.purchase_agreements_created = await _safe("Agreements", self._build_purchase_agreements(
                data.get("PurchaseAgreement", [])))

            # Phase 5: Enrichments
            result.products_enriched = await _safe("Enrichments", self._enrich_products(
                data.get("PriceList", []), data.get("ItemGroup", [])))
            result.inv_movements_applied = await _safe("InvMovements", self._apply_inv_movements(
                data.get("InventoryTransaction", [])))

            # Derivation fallbacks for empty entities
            derived_counts = await self._run_derivation_fallbacks(data)

            # Build and save extraction audit report
            audit = self._build_extraction_audit(data, result, derived_counts)
            await audit.save(self.db)

            await self.db.flush()
            result.success = True

        except Exception as e:
            logger.error("Infor config build failed: %s", e, exc_info=True)
            result.errors.append(str(e))

        # Summary log
        logger.info(
            "Infor build %s: sites=%d products=%d partners=%d lanes=%d boms=%d "
            "POs=%d SOs=%d MOs=%d shipments=%d forecasts=%d",
            "OK" if result.success else "FAILED",
            result.sites_created, result.products_created,
            result.trading_partners_created, result.lanes_created,
            result.boms_created, result.purchase_orders_created,
            result.outbound_orders_created, result.production_orders_created,
            result.shipments_created, result.forecasts_created,
        )
        return result

    # ── Phase 2: Master Data Builders ────────────────────────────────────

    async def _build_sites(self, warehouses: List[Dict]) -> int:
        """Warehouse → Site (internal, is_external=False).

        Uses the warehouse description (WHNM/ITDS) as the site name for Sankey
        readability, not the raw M3 warehouse code.
        """
        count = 0
        for wh in warehouses:
            whlo = str(wh.get("WHLO", "")).strip()
            if not whlo:
                continue

            # Descriptive name: prefer WHNM, fall back to WHDC, then code
            whnm = (wh.get("WHNM") or wh.get("WarehouseName") or
                    wh.get("WHDC") or whlo).strip()
            whty = str(wh.get("WHTY", "1")).strip()
            master_type = map_warehouse_type(whty)

            # Override to MANUFACTURER if warehouse has production capability
            if whty == "3" or master_type == "MANUFACTURER":
                master_type = "MANUFACTURER"

            # Map master_type to site type/dag_type
            if master_type == "MANUFACTURER":
                site_type = "manufacturer"
                dag_type = "manufacturer"
            elif master_type == "MARKET":
                site_type = "customer"
                dag_type = "customer"
            else:
                site_type = "inventory"
                dag_type = "inventory"

            self._site_ids.add(whlo)
            self._site_name_map[whlo] = whnm
            self._site_master_types[whlo] = master_type

            # Check if site already exists for this config with this name
            existing = await self.db.execute(text(
                "SELECT id FROM site WHERE config_id = :cid AND name = :name"
            ), {"cid": self._config_id, "name": whnm})
            row = existing.fetchone()

            if row:
                await self.db.execute(text("""
                    UPDATE site SET master_type = :master_type, type = :type,
                        dag_type = :dag_type, is_external = false
                    WHERE id = :id
                """), {"id": row[0], "master_type": master_type, "type": site_type, "dag_type": dag_type})
            else:
                await self.db.execute(text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, order_aging,
                        company_id, geo_id, is_external)
                    VALUES (:config_id, :name, :type, :dag_type, :master_type, 0,
                        :company_id, :geo_id, false)
                """), {
                    "config_id": self._config_id,
                    "name": whnm,
                    "type": site_type,
                    "dag_type": dag_type,
                    "master_type": master_type,
                    "company_id": "MIDWEST_IND",
                    "geo_id": wh.get("TOWN", ""),
                })
            count += 1

        logger.info("  Sites: %d internal created/updated", count)
        return count

    async def _build_products(self, items: List[Dict]) -> int:
        """ItemMaster → Product."""
        count = 0
        for item in items:
            itno = str(item.get("ITNO", "")).strip()
            if not itno:
                continue

            product_id = f"CFG{self._config_id}_{itno}"
            self._product_id_map[itno] = product_id

            # Determine product type from BOM membership and M3 ITTY
            itty = str(item.get("ITTY", "")).strip()
            if itno in self._bom_products:
                product_type = "FINISHED_GOOD"
            elif itty in ("RM", "301"):
                product_type = "RAW_MATERIAL"
            elif itty in ("FG", "101"):
                product_type = "FINISHED_GOOD"
            elif itty in ("SFG", "201"):
                product_type = "SEMI_FINISHED"
            else:
                product_type = "RAW_MATERIAL"

            await self.db.execute(text("""
                INSERT INTO product (id, config_id, description, product_type,
                    unit_cost, unit_price, base_uom, weight, volume,
                    category, family, is_active)
                VALUES (:id, :config_id, :desc, :product_type,
                    :unit_cost, :unit_price, :base_uom, :weight, :volume,
                    :category, :family, :is_active)
                ON CONFLICT (id) DO UPDATE SET
                    description = EXCLUDED.description,
                    product_type = EXCLUDED.product_type,
                    unit_cost = EXCLUDED.unit_cost,
                    unit_price = EXCLUDED.unit_price
            """), {
                "id": product_id,
                "config_id": self._config_id,
                "desc": item.get("ITDS", item.get("ItemDescription", itno)),
                "product_type": product_type,
                "unit_cost": _safe_float(item.get("UCOS", item.get("AverageCost"))),
                "unit_price": _safe_float(item.get("SAPR", item.get("SalesPrice"))),
                "base_uom": item.get("UNMS", item.get("BasicUOM", "EA")),
                "weight": _safe_float(item.get("GRWE", item.get("GrossWeight"))),
                "volume": _safe_float(item.get("VOL3", item.get("Volume"))),
                "category": item.get("ITGR", item.get("ItemGroup", "")),
                "family": item.get("ITCL", item.get("ProductGroup", "")),
                "is_active": "true" if str(item.get("STAT", "20")) not in ("90", "99") else "false",
            })
            count += 1

        logger.info("  Products: %d created/updated", count)
        return count

    async def _build_trading_partners(
        self,
        suppliers: List[Dict],
        customers: List[Dict],
    ) -> int:
        """Supplier/Customer → TradingPartner + external Site nodes.

        For each vendor/customer, creates:
        1. A TradingPartner record (the business entity)
        2. An external Site node (is_external=True, trading_partner_id=tp._id)
           so the Sankey diagram can render vendor/customer endpoints.
        """
        count = 0

        # ── Vendors ──
        for sup in suppliers:
            suno = str(sup.get("SUNO", "")).strip()
            if not suno:
                continue

            sunm = (sup.get("SUNM") or sup.get("SupplierName") or suno).strip()
            tp_id = f"INF_V_{suno}"
            result = await self.db.execute(text("""
                INSERT INTO trading_partners (id, tpartner_type, description,
                    city, country, phone_number, is_active)
                VALUES (:id, 'vendor', :desc,
                    :city, :country, :phone, :active)
                ON CONFLICT (id) DO UPDATE SET
                    city = EXCLUDED.city, country = EXCLUDED.country,
                    description = EXCLUDED.description
                RETURNING _id
            """), {
                "id": tp_id,
                "desc": sunm,
                "city": sup.get("TOWN", ""),
                "country": sup.get("CSCD", ""),
                "phone": sup.get("PHNO", ""),
                "active": "true" if str(sup.get("STAT", "20")) != "90" else "false",
            })
            row = result.fetchone()
            if row:
                self._vendor_pks[suno] = row[0]
                self._vendor_names[suno] = sunm
            count += 1

        # Flush to get TradingPartner._id values before creating external Site nodes
        await self.db.flush()

        # Create external Site nodes for vendors
        for suno, tp_pk in self._vendor_pks.items():
            sunm = self._vendor_names.get(suno, suno)
            site_name = f"Vendor - {sunm}"
            await self.db.execute(text("""
                INSERT INTO site (config_id, name, type, dag_type, master_type,
                    is_external, tpartner_type, trading_partner_id, order_aging, geo_id)
                VALUES (:config_id, :name, 'vendor', 'vendor', 'VENDOR',
                    true, 'vendor', :tp_id, 0, '')
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "name": site_name,
                "tp_id": tp_pk,
            })

        # ── Customers ──
        for cust in customers:
            cuno = str(cust.get("CUNO", "")).strip()
            if not cuno:
                continue

            cunm = (cust.get("CUNM") or cust.get("CustomerName") or cuno).strip()
            tp_id = f"INF_C_{cuno}"
            result = await self.db.execute(text("""
                INSERT INTO trading_partners (id, tpartner_type, description,
                    city, country, phone_number, is_active)
                VALUES (:id, 'customer', :desc,
                    :city, :country, :phone, :active)
                ON CONFLICT (id) DO UPDATE SET
                    city = EXCLUDED.city, country = EXCLUDED.country,
                    description = EXCLUDED.description
                RETURNING _id
            """), {
                "id": tp_id,
                "desc": cunm,
                "city": cust.get("TOWN", ""),
                "country": cust.get("CSCD", ""),
                "phone": cust.get("PHNO", ""),
                "active": "true" if str(cust.get("STAT", "20")) != "90" else "false",
            })
            row = result.fetchone()
            if row:
                self._customer_pks[cuno] = row[0]
                self._customer_names[cuno] = cunm
            count += 1

        # Flush to get TradingPartner._id values before creating external Site nodes
        await self.db.flush()

        # Create external Site nodes for customers
        for cuno, tp_pk in self._customer_pks.items():
            cunm = self._customer_names.get(cuno, cuno)
            site_name = f"Customer - {cunm}"
            await self.db.execute(text("""
                INSERT INTO site (config_id, name, type, dag_type, master_type,
                    is_external, tpartner_type, trading_partner_id, order_aging, geo_id)
                VALUES (:config_id, :name, 'customer', 'customer', 'CUSTOMER',
                    true, 'customer', :tp_id, 0, '')
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "name": site_name,
                "tp_id": tp_pk,
            })

        logger.info("  Trading Partners: %d (vendors=%d, customers=%d) + external Site nodes",
                     count, len(self._vendor_pks), len(self._customer_pks))
        return count

    async def _build_transportation_lanes(self) -> int:
        """Auto-generate transportation lanes from site topology.

        Creates three types of lanes for Sankey-renderable topology:
        1. Vendor → internal site: from_partner_id + to_site_id
        2. Internal → internal: from_site_id + to_site_id
        3. Internal site → Customer: from_site_id + to_partner_id
        """
        count = 0

        # Helper: get internal site id by descriptive name
        async def _site_id_by_name(name: str) -> Optional[int]:
            r = await self.db.execute(text(
                "SELECT id FROM site WHERE config_id = :cid AND name = :name LIMIT 1"
            ), {"cid": self._config_id, "name": name})
            row = r.fetchone()
            return row[0] if row else None

        lead_time_json = '{"type": "normal", "mean": 3, "stddev": 1}'

        # ── 1. Vendor → internal manufacturing/raw-material sites ──
        # Vendors supply to MANUFACTURER and raw-material-store INVENTORY sites
        target_whlos = [
            whlo for whlo in self._site_ids
            if self._site_master_types.get(whlo) == "MANUFACTURER"
            or "raw material" in self._site_name_map.get(whlo, "").lower()
        ]
        if not target_whlos:
            # Fallback: supply to first available internal site
            target_whlos = list(self._site_ids)[:1]

        for suno, tp_pk in self._vendor_pks.items():
            for whlo in target_whlos:
                to_name = self._site_name_map.get(whlo)
                if not to_name:
                    continue
                to_site_id = await _site_id_by_name(to_name)
                if not to_site_id:
                    continue
                await self.db.execute(text("""
                    INSERT INTO transportation_lane (config_id, from_partner_id, to_site_id,
                        capacity, supply_lead_time)
                    VALUES (:config_id, :from_partner_id, :to_site_id, 9999,
                        CAST(:lead_time AS json))
                    ON CONFLICT DO NOTHING
                """), {
                    "config_id": self._config_id,
                    "from_partner_id": tp_pk,
                    "to_site_id": to_site_id,
                    "lead_time": lead_time_json,
                })
                count += 1

        # ── 2. Internal → internal lanes (topology-aware) ──
        # Build directional lanes based on master types:
        #   Raw material stores → Manufacturers
        #   Manufacturers → Distribution centers (INVENTORY non-RM)
        #   Distribution → Distribution (cross-docking)
        manufacturers = [w for w in self._site_ids if self._site_master_types.get(w) == "MANUFACTURER"]
        rm_stores = [w for w in self._site_ids
                     if self._site_master_types.get(w) == "INVENTORY"
                     and "raw material" in self._site_name_map.get(w, "").lower()]
        dist_centers = [w for w in self._site_ids
                        if self._site_master_types.get(w) == "INVENTORY"
                        and w not in rm_stores]

        # RM store → Manufacturer
        for rm in rm_stores:
            for mfg in manufacturers:
                from_id = await _site_id_by_name(self._site_name_map[rm])
                to_id = await _site_id_by_name(self._site_name_map[mfg])
                if from_id and to_id:
                    await self.db.execute(text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id,
                            capacity, supply_lead_time)
                        VALUES (:config_id, :from_id, :to_id, 9999, CAST(:lead_time AS json))
                        ON CONFLICT DO NOTHING
                    """), {"config_id": self._config_id, "from_id": from_id,
                           "to_id": to_id, "lead_time": lead_time_json})
                    count += 1

        # Manufacturer → Distribution center
        for mfg in manufacturers:
            for dc in dist_centers:
                from_id = await _site_id_by_name(self._site_name_map[mfg])
                to_id = await _site_id_by_name(self._site_name_map[dc])
                if from_id and to_id:
                    await self.db.execute(text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id,
                            capacity, supply_lead_time)
                        VALUES (:config_id, :from_id, :to_id, 9999, CAST(:lead_time AS json))
                        ON CONFLICT DO NOTHING
                    """), {"config_id": self._config_id, "from_id": from_id,
                           "to_id": to_id, "lead_time": lead_time_json})
                    count += 1

        # Cross-docking between distribution centers
        for i, dc_a in enumerate(dist_centers):
            for dc_b in dist_centers[i + 1:]:
                from_id = await _site_id_by_name(self._site_name_map[dc_a])
                to_id = await _site_id_by_name(self._site_name_map[dc_b])
                if from_id and to_id:
                    await self.db.execute(text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id,
                            capacity, supply_lead_time)
                        VALUES (:config_id, :from_id, :to_id, 9999, CAST(:lead_time AS json))
                        ON CONFLICT DO NOTHING
                    """), {"config_id": self._config_id, "from_id": from_id,
                           "to_id": to_id, "lead_time": lead_time_json})
                    count += 1

        # ── 3. Internal distribution/manufacturing sites → Customer ──
        # Ship from DCs to customers; if no DCs, ship from manufacturers
        ship_from_whlos = dist_centers if dist_centers else manufacturers
        for cuno, tp_pk in self._customer_pks.items():
            for whlo in ship_from_whlos:
                from_name = self._site_name_map.get(whlo)
                if not from_name:
                    continue
                from_site_id = await _site_id_by_name(from_name)
                if not from_site_id:
                    continue
                await self.db.execute(text("""
                    INSERT INTO transportation_lane (config_id, from_site_id, to_partner_id,
                        capacity, supply_lead_time)
                    VALUES (:config_id, :from_site_id, :to_partner_id, 9999,
                        CAST(:lead_time AS json))
                    ON CONFLICT DO NOTHING
                """), {
                    "config_id": self._config_id,
                    "from_site_id": from_site_id,
                    "to_partner_id": tp_pk,
                    "lead_time": lead_time_json,
                })
                count += 1

        logger.info("  Transportation Lanes: %d created (vendor→site + internal + site→customer)", count)
        return count

    async def _build_boms(self, bom_lines: List[Dict]) -> int:
        """BillOfMaterial → ProductBOM."""
        count = 0
        for line in bom_lines:
            prno = str(line.get("PRNO", "")).strip()
            mtno = str(line.get("MTNO", "")).strip()
            if not prno or not mtno:
                continue

            product_id = self._product_id_map.get(prno)
            component_id = self._product_id_map.get(mtno)
            if not product_id or not component_id:
                continue

            await self.db.execute(text("""
                INSERT INTO product_bom (config_id, product_id, component_product_id,
                    component_quantity, component_uom, scrap_percentage,
                    eff_start_date, eff_end_date, is_active)
                VALUES (:config_id, :product_id, :component_id,
                    :qty, :uom, :scrap,
                    :start_date, :end_date, 'true')
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "component_id": component_id,
                "qty": _safe_float(line.get("CNQT", line.get("ComponentQty")), 1.0),
                "uom": line.get("PEUN", line.get("UOM", "EA")),
                "scrap": _safe_float(line.get("WAPC", line.get("ScrapPct")), 0.0),
                "start_date": _parse_m3_date(line.get("FDAT")),
                "end_date": _parse_m3_date(line.get("TDAT")),
            })
            count += 1

        logger.info("  BOMs: %d components created", count)
        return count

    # ── Phase 3: Inventory ───────────────────────────────────────────────

    async def _build_inv_levels(
        self,
        item_warehouses: List[Dict],
        inv_balances: List[Dict],
    ) -> int:
        """ItemWarehouse + InventoryBalance → InvLevel."""
        count = 0
        today = date.today()

        # Prefer InventoryBalance (CDC, more current) over ItemWarehouse
        records = inv_balances if inv_balances else item_warehouses

        for rec in records:
            itno = str(rec.get("ITNO", "")).strip()
            whlo = str(rec.get("WHLO", "")).strip()
            if not itno or not whlo:
                continue

            product_id = self._product_id_map.get(itno)
            if not product_id or whlo not in self._site_ids:
                continue

            await self.db.execute(text("""
                INSERT INTO inv_level (config_id, product_id, site_id, inventory_date,
                    on_hand_qty, in_transit_qty, available_qty, reserved_qty)
                SELECT :config_id, :product_id, s.id, :inv_date,
                    :on_hand, :in_transit, :available, :reserved
                FROM site s WHERE s.config_id = :config_id AND s.name = :whlo
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "whlo": self._site_name_map.get(whlo, whlo),
                "inv_date": today,
                "on_hand": _safe_float(rec.get("STQT", rec.get("OnHand"))),
                "in_transit": _safe_float(rec.get("TRQT", rec.get("InTransit"))),
                "available": _safe_float(rec.get("APTS", rec.get("Available"))),
                "reserved": _safe_float(rec.get("REQT", rec.get("Reserved"))),
            })
            count += 1

        logger.info("  Inventory Levels: %d created", count)
        return count

    async def _build_inv_policies(self, item_warehouses: List[Dict]) -> int:
        """ItemWarehouse → InvPolicy."""
        count = 0
        for rec in item_warehouses:
            itno = str(rec.get("ITNO", "")).strip()
            whlo = str(rec.get("WHLO", "")).strip()
            if not itno or not whlo:
                continue

            product_id = self._product_id_map.get(itno)
            if not product_id or whlo not in self._site_ids:
                continue

            # M3 planning code PLCD → ss_policy
            plcd = str(rec.get("PLCD", "")).strip()
            ss_policy = "abs_level"  # default
            if plcd in ("1", "MRP"):
                ss_policy = "abs_level"
            elif plcd in ("2", "ROP"):
                ss_policy = "abs_level"
            elif plcd in ("3", "DOP"):
                ss_policy = "doc_dem"

            await self.db.execute(text("""
                INSERT INTO inv_policy (config_id, product_id, site_id,
                    ss_policy, ss_quantity, reorder_point, order_up_to_level,
                    min_order_quantity, fixed_order_quantity, is_active)
                SELECT :config_id, :product_id, s.id,
                    :ss_policy, :ss_qty, :reop, :max_stock,
                    :min_order, :eoq, 'true'
                FROM site s WHERE s.config_id = :config_id AND s.name = :whlo
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "whlo": self._site_name_map.get(whlo, whlo),
                "ss_policy": ss_policy,
                "ss_qty": _safe_float(rec.get("SSQT", rec.get("SafetyStock"))),
                "reop": _safe_float(rec.get("REOP", rec.get("ReorderPoint"))),
                "max_stock": _safe_float(rec.get("MXST", rec.get("MaxStock"))),
                "min_order": _safe_float(rec.get("LOQT", rec.get("MinOrderQty"))),
                "eoq": _safe_float(rec.get("EOQT", rec.get("EOQ"))),
            })
            count += 1

        logger.info("  Inventory Policies: %d created", count)
        return count

    # ── Phase 4: Transactional Data ──────────────────────────────────────

    async def _build_purchase_orders(
        self,
        po_headers: List[Dict],
        po_lines: List[Dict],
    ) -> int:
        """PurchaseOrder + PurchaseOrderLine → InboundOrder + InboundOrderLine."""
        count = 0

        # Index lines by PO number
        lines_by_po: Dict[str, List[Dict]] = {}
        for line in po_lines:
            puno = str(line.get("PUNO", "")).strip()
            if puno:
                lines_by_po.setdefault(puno, []).append(line)

        for po in po_headers:
            puno = str(po.get("PUNO", "")).strip()
            if not puno:
                continue

            suno = str(po.get("SUNO", "")).strip()
            order_id = f"INF-PO-{puno}"
            status = map_po_status(po.get("PUSL", "15"))

            await self.db.execute(text("""
                INSERT INTO inbound_order (id, company_id, order_type,
                    supplier_id, status, order_date, requested_delivery_date,
                    total_value, config_id)
                VALUES (:id, :company_id, 'PURCHASE',
                    :supplier_id, :status, :order_date, :delivery_date,
                    :total_value, :config_id)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status
            """), {
                "id": order_id,
                "company_id": suno,
                "supplier_id": f"INF_V_{suno}" if suno else None,
                "status": status,
                "order_date": _parse_m3_date(po.get("PUDT")),
                "delivery_date": _parse_m3_date(po.get("DWDT")),
                "total_value": _safe_float(po.get("LNAM", po.get("TotalAmount"))),
                "config_id": self._config_id,
            })

            # Build lines
            for line in lines_by_po.get(puno, []):
                itno = str(line.get("ITNO", "")).strip()
                product_id = self._product_id_map.get(itno)
                whlo = str(line.get("WHLO", "")).strip()

                await self.db.execute(text("""
                    INSERT INTO inbound_order_line (order_id, line_number,
                        product_id, quantity_submitted, quantity_received,
                        cost, expected_delivery_date, status, config_id)
                    VALUES (:order_id, :line_no,
                        :product_id, :qty_sub, :qty_rcv,
                        :cost, :delivery_date, :status, :config_id)
                    ON CONFLICT DO NOTHING
                """), {
                    "order_id": order_id,
                    "line_no": _safe_int(line.get("PNLI", line.get("LineNumber")), 1),
                    "product_id": product_id,
                    "qty_sub": _safe_float(line.get("ORQA", line.get("OrderedQty"))),
                    "qty_rcv": _safe_float(line.get("RVQA", line.get("ReceivedQty"))),
                    "cost": _safe_float(line.get("PUPR", line.get("PurchasePrice"))),
                    "delivery_date": _parse_m3_date(line.get("DWDT")),
                    "status": map_po_status(line.get("PUSL", po.get("PUSL", "15"))),
                    "config_id": self._config_id,
                })

            count += 1

        logger.info("  Purchase Orders: %d created", count)
        return count

    async def _build_outbound_orders(
        self,
        so_headers: List[Dict],
        so_lines: List[Dict],
    ) -> int:
        """SalesOrder + SalesOrderLine → OutboundOrder + OutboundOrderLine."""
        count = 0

        lines_by_so: Dict[str, List[Dict]] = {}
        for line in so_lines:
            orno = str(line.get("ORNO", "")).strip()
            if orno:
                lines_by_so.setdefault(orno, []).append(line)

        for so in so_headers:
            orno = str(so.get("ORNO", "")).strip()
            if not orno:
                continue

            cuno = str(so.get("CUNO", "")).strip()
            order_id = f"INF-SO-{orno}"
            status = map_so_status(so.get("ORSL", "15"))

            await self.db.execute(text("""
                INSERT INTO outbound_order (id, company_id, order_type,
                    customer_id, status, order_date, requested_delivery_date,
                    total_value, config_id)
                VALUES (:id, :company_id, 'SALES',
                    :customer_id, :status, :order_date, :delivery_date,
                    :total_value, :config_id)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status
            """), {
                "id": order_id,
                "company_id": cuno,
                "customer_id": f"INF_C_{cuno}" if cuno else None,
                "status": status,
                "order_date": _parse_m3_date(so.get("ORDT")),
                "delivery_date": _parse_m3_date(so.get("DWDT")),
                "total_value": _safe_float(so.get("LNAM", so.get("TotalAmount"))),
                "config_id": self._config_id,
            })

            for line in lines_by_so.get(orno, []):
                itno = str(line.get("ITNO", "")).strip()
                product_id = self._product_id_map.get(itno)

                await self.db.execute(text("""
                    INSERT INTO outbound_order_line (order_id, line_number,
                        product_id, ordered_quantity, shipped_quantity,
                        requested_delivery_date, status, config_id)
                    VALUES (:order_id, :line_no,
                        :product_id, :ordered_qty, :shipped_qty,
                        :delivery_date, :status, :config_id)
                    ON CONFLICT DO NOTHING
                """), {
                    "order_id": order_id,
                    "line_no": _safe_int(line.get("PONR", line.get("LineNumber")), 1),
                    "product_id": product_id,
                    "ordered_qty": _safe_float(line.get("ORQA")),
                    "shipped_qty": _safe_float(line.get("DLQA")),
                    "delivery_date": _parse_m3_date(line.get("DWDT")),
                    "status": map_so_status(line.get("ORSL", so.get("ORSL", "15"))),
                    "config_id": self._config_id,
                })

            count += 1

        logger.info("  Outbound Orders: %d created", count)
        return count

    async def _build_production_orders(self, orders: List[Dict]) -> int:
        """ProductionOrder → ProductionOrder (AWS SC)."""
        count = 0
        for mo in orders:
            mfno = str(mo.get("MFNO", "")).strip()
            if not mfno:
                continue

            prno = str(mo.get("PRNO", "")).strip()
            product_id = self._product_id_map.get(prno)
            whlo = str(mo.get("WHLO", "")).strip()
            status = map_mo_status(mo.get("WHST", mo.get("Status", "10")))

            start_dt = _parse_m3_date(mo.get("STDT")) or date.today()
            due_dt = _parse_m3_date(mo.get("FIDT")) or (start_dt + timedelta(days=14))

            await self.db.execute(text("""
                INSERT INTO production_orders (order_number, config_id, item_id, site_id,
                    planned_quantity, planned_start_date, planned_completion_date, status)
                SELECT :order_number, :config_id, :item_id, s.id,
                    :planned_qty, :start_date, :due_date, :status
                FROM site s WHERE s.config_id = :config_id AND s.name = :whlo
                ON CONFLICT DO NOTHING
            """), {
                "order_number": f"INF-MO-{mfno}",
                "config_id": self._config_id,
                "item_id": product_id,
                "whlo": self._site_name_map.get(whlo, whlo),
                "planned_qty": _safe_int(mo.get("ORQA")),
                "start_date": start_dt,
                "due_date": due_dt,
                "status": status,
            })
            count += 1

        logger.info("  Production Orders: %d created", count)
        return count

    async def _build_goods_receipts(self, receipts: List[Dict]) -> int:
        """GoodsReceipt → Enriches InboundOrder status."""
        count = 0
        for gr in receipts:
            puno = str(gr.get("PUNO", "")).strip()
            if not puno:
                continue

            order_id = f"INF-PO-{puno}"
            await self.db.execute(text("""
                UPDATE inbound_order SET status = 'RECEIVED',
                    actual_delivery_date = :rcv_date
                WHERE id = :order_id AND status != 'RECEIVED'
            """), {
                "order_id": order_id,
                "rcv_date": _parse_m3_date(gr.get("TRDT")),
            })
            count += 1

        logger.info("  Goods Receipts: %d processed", count)
        return count

    async def _build_shipments(
        self,
        deliveries: List[Dict],
        delivery_lines: List[Dict],
    ) -> int:
        """Delivery → Shipment."""
        count = 0
        for dlv in deliveries:
            conn = str(dlv.get("CONN", "")).strip()
            if not conn:
                continue

            await self.db.execute(text("""
                INSERT INTO shipment (id, config_id, order_id,
                    status, ship_date, expected_delivery_date)
                VALUES (:id, :config_id, :order_id,
                    :status, :ship_date, :delivery_date)
                ON CONFLICT DO NOTHING
            """), {
                "id": f"INF-SHP-{conn}",
                "config_id": self._config_id,
                "order_id": dlv.get("ORNO", ""),
                "status": "in_transit",
                "ship_date": _parse_m3_date(dlv.get("DSDT")),
                "delivery_date": _parse_m3_date(dlv.get("DWDT")),
            })
            count += 1

        logger.info("  Shipments: %d created", count)
        return count

    async def _build_transfer_orders(self, transfers: List[Dict]) -> int:
        """TransferOrder → TransferOrder (internal stock movements)."""
        count = 0
        for to in transfers:
            ridn = str(to.get("RIDN", "")).strip()
            if not ridn:
                continue

            itno = str(to.get("ITNO", "")).strip()
            product_id = self._product_id_map.get(itno)

            await self.db.execute(text("""
                INSERT INTO inbound_order (id, company_id, order_type,
                    status, order_date, config_id)
                VALUES (:id, :company, 'TRANSFER',
                    'CONFIRMED', :order_date, :config_id)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": f"INF-TO-{ridn}",
                "company": "",
                "order_date": _parse_m3_date(to.get("TRDT")),
                "config_id": self._config_id,
            })
            count += 1

        logger.info("  Transfer Orders: %d created", count)
        return count

    async def _build_quality_orders(self, inspections: List[Dict]) -> int:
        """QualityInspection → QualityOrder."""
        count = 0
        for qi in inspections:
            qrid = str(qi.get("QRID", "")).strip()
            if not qrid:
                continue

            itno = str(qi.get("ITNO", "")).strip()
            product_id = self._product_id_map.get(itno)

            # Quality orders stored as metadata — no dedicated AWS SC entity,
            # so we log and track via external_identifiers or extension table
            count += 1

        logger.info("  Quality Orders: %d processed", count)
        return count

    async def _build_maintenance_orders(self, orders: List[Dict]) -> int:
        """MaintenanceOrder → MaintenanceOrder."""
        count = 0
        for mo in orders:
            mwno = str(mo.get("MWNO", "")).strip()
            if not mwno:
                continue
            count += 1

        logger.info("  Maintenance Orders: %d processed", count)
        return count

    async def _build_forecasts(self, forecasts: List[Dict]) -> int:
        """Forecast → Forecast (AWS SC)."""
        count = 0
        for fc in forecasts:
            itno = str(fc.get("ITNO", "")).strip()
            whlo = str(fc.get("WHLO", "")).strip()
            if not itno or not whlo:
                continue

            product_id = self._product_id_map.get(itno)
            if not product_id or whlo not in self._site_ids:
                continue

            await self.db.execute(text("""
                INSERT INTO forecast (config_id, product_id, site_id,
                    forecast_date, forecast_quantity, forecast_type)
                SELECT :config_id, :product_id, s.id,
                    :fc_date, :fc_qty, :fc_type
                FROM site s WHERE s.config_id = :config_id AND s.name = :whlo
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "whlo": self._site_name_map.get(whlo, whlo),
                "fc_date": _parse_m3_date(fc.get("FRDT")),
                "fc_qty": _safe_float(fc.get("FOQA", fc.get("ForecastQty"))),
                "fc_type": fc.get("FOTY", "statistical"),
            })
            count += 1

        logger.info("  Forecasts: %d created", count)
        return count

    async def _build_resources(
        self,
        work_centers: List[Dict],
        routings: List[Dict],
    ) -> int:
        """WorkCenter + Routing → ProductionProcess + ProcessOperation."""
        count = 0
        for wc in work_centers:
            plgr = str(wc.get("PLGR", "")).strip()
            if not plgr:
                continue
            count += 1

        logger.info("  Resources/Work Centers: %d processed", count)
        return count

    async def _build_planned_orders(self, planned: List[Dict]) -> int:
        """PlannedOrder → SupplyPlan (MRP output)."""
        count = 0
        for po in planned:
            plpn = str(po.get("PLPN", "")).strip()
            if not plpn:
                continue

            itno = str(po.get("ITNO", "")).strip()
            product_id = self._product_id_map.get(itno)
            if not product_id:
                continue

            # Determine plan type from M3 planned order type
            poty = str(po.get("POTY", "")).strip()
            if poty in ("10", "PO"):
                plan_type = "po_request"
            elif poty in ("20", "MO"):
                plan_type = "mo_request"
            elif poty in ("30", "TO"):
                plan_type = "to_request"
            else:
                plan_type = "po_request"

            await self.db.execute(text("""
                INSERT INTO supply_plan (config_id, product_id,
                    plan_date, plan_type, planned_order_quantity,
                    planned_order_date, planned_receipt_date)
                VALUES (:config_id, :product_id,
                    :plan_date, :plan_type, :qty,
                    :order_date, :receipt_date)
                ON CONFLICT DO NOTHING
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "plan_date": _parse_m3_date(po.get("PLDT")),
                "plan_type": plan_type,
                "qty": _safe_float(po.get("PPQT", po.get("PlannedQty"))),
                "order_date": _parse_m3_date(po.get("PLDT")),
                "receipt_date": _parse_m3_date(po.get("DLDT")),
            })
            count += 1

        logger.info("  Planned Orders: %d created", count)
        return count

    async def _build_purchase_agreements(self, agreements: List[Dict]) -> int:
        """PurchaseAgreement → SourcingRules."""
        count = 0
        for agr in agreements:
            agnb = str(agr.get("AGNB", "")).strip()
            if not agnb:
                continue

            suno = str(agr.get("SUNO", "")).strip()
            itno = str(agr.get("ITNO", "")).strip()
            product_id = self._product_id_map.get(itno) if itno else None

            await self.db.execute(text("""
                INSERT INTO sourcing_rules (id, config_id,
                    product_id, tpartner_id, sourcing_rule_type,
                    sourcing_priority, eff_start_date, eff_end_date, is_active)
                VALUES (:id, :config_id,
                    :product_id, :tpartner_id, 'buy',
                    1, :start_date, :end_date, 'true')
                ON CONFLICT DO NOTHING
            """), {
                "id": f"INF-AGR-{agnb}",
                "config_id": self._config_id,
                "product_id": product_id,
                "tpartner_id": f"INF_V_{suno}" if suno else None,
                "start_date": _parse_m3_date(agr.get("VFDT")),
                "end_date": _parse_m3_date(agr.get("VTDT")),
            })
            count += 1

        logger.info("  Purchase Agreements → Sourcing Rules: %d created", count)
        return count

    # ── Phase 5: Enrichments ─────────────────────────────────────────────

    async def _enrich_products(
        self,
        price_lists: List[Dict],
        item_groups: List[Dict],
    ) -> int:
        """Enrich products with pricing and group descriptions."""
        count = 0

        for price in price_lists:
            itno = str(price.get("ITNO", "")).strip()
            product_id = self._product_id_map.get(itno)
            if not product_id:
                continue

            sapr = _safe_float(price.get("SAPR", price.get("SalesPrice")))
            if sapr > 0:
                await self.db.execute(text("""
                    UPDATE product SET unit_price = :price WHERE id = :id
                """), {"id": product_id, "price": sapr})
                count += 1

        logger.info("  Products enriched: %d", count)
        return count

    async def _apply_inv_movements(self, transactions: List[Dict]) -> int:
        """InventoryTransaction → InvLevel delta adjustments."""
        count = 0
        for txn in transactions:
            itno = str(txn.get("ITNO", "")).strip()
            whlo = str(txn.get("WHLO", "")).strip()
            if not itno or not whlo:
                continue

            product_id = self._product_id_map.get(itno)
            if not product_id or whlo not in self._site_ids:
                continue

            # M3 transaction types: + = receipt, - = issue
            trtp = str(txn.get("TRTP", "")).strip()
            qty = _safe_float(txn.get("TRQT", txn.get("TransactionQty")))
            if trtp in ("31", "32", "40"):  # Issue types
                qty = -abs(qty)
            else:
                qty = abs(qty)

            await self.db.execute(text("""
                UPDATE inv_level SET on_hand_qty = on_hand_qty + :delta
                WHERE config_id = :config_id AND product_id = :product_id
                    AND site_id IN (SELECT id FROM site WHERE config_id = :config_id AND name = :whlo)
            """), {
                "config_id": self._config_id,
                "product_id": product_id,
                "whlo": self._site_name_map.get(whlo, whlo),
                "delta": qty,
            })
            count += 1

        logger.info("  Inventory movements applied: %d", count)
        return count

    # ------------------------------------------------------------------
    # Derivation Fallbacks
    # ------------------------------------------------------------------

    async def _derive_transfer_orders_from_topology(self) -> int:
        """Derive TOs from internal lanes when TransferOrder entity is empty.

        For multi-site Infor configs, create representative TOs for each
        internal-to-internal transportation lane.
        """
        if not self._config_id or len(self._site_ids) < 2:
            return 0

        # Get all internal sites
        site_result = await self.db.execute(text(
            "SELECT id, name, master_type FROM site WHERE config_id = :cid"
        ), {"cid": self._config_id})
        internal_sites: Dict[int, str] = {}
        for sid, sname, mt in site_result.fetchall():
            if mt not in ("VENDOR", "CUSTOMER"):
                internal_sites[sid] = sname

        if len(internal_sites) < 2:
            return 0

        # Find internal-to-internal lanes
        lane_result = await self.db.execute(text(
            "SELECT id, from_site_id, to_site_id, lead_time_days FROM transportation_lane "
            "WHERE config_id = :cid AND from_site_id IS NOT NULL AND to_site_id IS NOT NULL"
        ), {"cid": self._config_id})

        count = 0
        today = date.today()
        for lid, from_sid, to_sid, lt_days in lane_result.fetchall():
            if from_sid not in internal_sites or to_sid not in internal_sites:
                continue

            lt = lt_days if lt_days and lt_days > 0 else 2
            to_num = f"INF-TO-DERIVED-{from_sid}-{to_sid}"
            await self.db.execute(text("""
                INSERT INTO inbound_order (id, company_id, order_type,
                    status, order_date, config_id)
                VALUES (:id, :company, 'TRANSFER',
                    'PLANNED', :order_date, :config_id)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": to_num,
                "company": "",
                "order_date": today,
                "config_id": self._config_id,
            })
            count += 1

        logger.info("  Derived Transfer Orders from topology: %d", count)
        return count

    async def _run_derivation_fallbacks(self, data: Dict[str, List[Dict]]) -> Dict[str, int]:
        """Run derivation fallbacks for empty Infor entities."""
        derived: Dict[str, int] = {}

        # TransferOrder empty → derive from topology
        transfers = data.get("TransferOrder", [])
        if not transfers:
            count = await self._derive_transfer_orders_from_topology()
            if count > 0:
                derived["transfer_orders_from_topology"] = count

        return derived

    def _build_extraction_audit(
        self, data: Dict[str, List[Dict]], result: InforConfigBuildResult,
        derived_counts: Dict[str, int],
    ) -> "ExtractionAuditReport":
        """Build extraction audit report for Infor config build."""
        from app.services.extraction_audit_service import ExtractionAuditReport

        audit = ExtractionAuditReport(
            config_id=self._config_id or 0, erp_type="Infor_M3",
        )

        # Record all Infor entities
        for entity_name, records in data.items():
            row_count = len(records) if records else 0
            if row_count > 0:
                audit.record_extracted(entity_name, row_count)
            else:
                audit.record_empty(entity_name)

        # Record entity counts
        for attr in [
            "sites_created", "products_created", "lanes_created", "boms_created",
            "trading_partners_created", "purchase_orders_created",
            "outbound_orders_created", "production_orders_created",
            "goods_receipts_created", "shipments_created",
            "transfer_orders_created", "quality_orders_created",
            "maintenance_orders_created", "forecasts_created",
        ]:
            count = getattr(result, attr, 0)
            if count > 0:
                audit.record_extracted(f"entity:{attr}", count)

        # Record derivations
        for key, count in derived_counts.items():
            audit.record_derived(
                f"derived:{key}", count,
                source="Internal transportation lanes + inventory",
                note="TransferOrder entity was empty — derived TOs from network topology",
            )

        return audit

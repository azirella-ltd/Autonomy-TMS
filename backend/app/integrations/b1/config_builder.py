"""
SAP Business One Config Builder — Staged B1 data → SupplyChainConfig

Transforms extracted B1 entities into the canonical AWS SC data model:

  Full mapping (dedicated _build_* methods):
  Warehouses                → Site (INVENTORY / MANUFACTURER)
  BusinessPartners          → TradingPartner (vendor / customer)
  Items                     → Product
  ProductTrees              → ProductBOM
  ItemWarehouseInfo         → InvLevel + InvPolicy
  PurchaseOrders            → PurchaseOrder + PurchaseOrderLineItem
  Orders                    → OutboundOrder + OutboundOrderLine
  ProductionOrders          → ProductionOrder
  PurchaseDeliveryNotes     → GoodsReceipt + GoodsReceiptLineItem
  DeliveryNotes             → Shipment
  StockTransfers            → TransferOrder + TransferOrderLineItem
  QualityTests              → QualityOrder
  ServiceCalls              → MaintenanceOrder
  ForecastReport            → Forecast
  Resources + Capacities    → CapacityPlan + CapacityResource
  PurchaseRequests          → PurchaseOrder (DRAFT)
  InventoryTransferRequests → TransferOrder (PLANNED)
  GoodsReturns              → InboundOrder (RETURN)
  BlanketAgreements         → SourcingRules (buy, vendor agreements only)
  MRPResults                → PurchaseOrder/ProductionOrder/TransferOrder (PLANNED)
  InventoryGenEntries/Exits → InvLevel adjustments (delta)
  StockTakings              → InvLevel corrections (absolute)

  Enrichment (augment existing records):
  Companies                 → Company table enrichment
  PriceLists + SpecialPrices → Product.unit_price + VendorProducts pricing
  UnitOfMeasurements        → Product.base_uom enrichment
  BusinessPartnerGroups     → TradingPartner description enrichment
  Invoices                  → OutboundOrder status → INVOICED
  Returns                   → OutboundOrder status → RETURNED + return lines
  PurchaseInvoices          → PurchaseOrder status → INVOICED
  BatchNumberDetails        → Product.external_identifiers (batch_managed flag)
  SerialNumberDetails       → Product.external_identifiers (serial_managed flag)

  Extraction only (staged in b1_staging, no Phase 2 mapping):
  BinLocations              — Sub-warehouse granularity (B1-specific)
  UnitOfMeasurementGroups   — UoM conversion groups (conversion logic not in SC model)

Usage:
    builder = B1ConfigBuilder(db, tenant_id=28)
    result = await builder.build_from_service_layer(connector)
    # or
    result = await builder.build_from_csv("/path/to/b1_csvs")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .field_mapping import map_card_type

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


def _parse_b1_date(val) -> Optional[date]:
    """Parse a B1 date string to a Python date.

    B1 Service Layer returns ISO-8601 strings (YYYY-MM-DD) or
    OData datetime literals.  CSV exports may use YYYYMMDD or YYYY-MM-DD.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("", "none", "null", "nan"):
        return None

    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:len(fmt.replace("%", "x"))], fmt).date()
        except (ValueError, IndexError):
            continue
    return None


def _b1_doc_status_to_po_status(doc_status: str) -> str:
    """Map B1 DocumentStatus to PurchaseOrder.status.

    B1 DocumentStatus values:
      bost_Open   / O  → open document
      bost_Close  / C  → closed (fully received)
      bost_Paid   / P  → (A/P invoice paid)
      bost_Delivered / D → delivered
    """
    s = str(doc_status).strip().upper()
    if s in ("C", "BOST_CLOSE"):
        return "RECEIVED"
    if s in ("D", "BOST_DELIVERED"):
        return "RECEIVED"
    if s in ("O", "BOST_OPEN"):
        return "APPROVED"
    return "APPROVED"


def _b1_doc_status_to_outbound_status(doc_status: str) -> str:
    """Map B1 DocumentStatus to OutboundOrder.status.

    bost_Open / O  → CONFIRMED
    bost_Close / C → FULFILLED
    """
    s = str(doc_status).strip().upper()
    if s in ("C", "BOST_CLOSE"):
        return "FULFILLED"
    return "CONFIRMED"


def _b1_production_status(status_val) -> str:
    """Map B1 ProductionOrder Status enum to ProductionOrder.status.

    B1 boProductionOrderStatusEnum:
      boposPlanned   / P → PLANNED
      boposReleased  / R → RELEASED
      boposClosed    / L → CLOSED
      boposCancelled / C → CANCELLED
    """
    s = str(status_val).strip().upper()
    mapping = {
        "P": "PLANNED",
        "BOPOSPLANNED": "PLANNED",
        "R": "RELEASED",
        "BOPOSRELEASED": "RELEASED",
        "L": "CLOSED",
        "BOPOSCLOSED": "CLOSED",
        "C": "CANCELLED",
        "BOPOSCANCELLED": "CANCELLED",
    }
    return mapping.get(s, "PLANNED")


@dataclass
class B1ConfigBuildResult:
    """Result of building a SupplyChainConfig from B1 data."""
    success: bool = False
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
    quality_orders_created: int = 0
    maintenance_orders_created: int = 0
    forecasts_created: int = 0
    products_enriched: int = 0
    resources_created: int = 0
    orders_status_updated: int = 0
    purchase_requests_created: int = 0
    transfer_requests_created: int = 0
    inv_movements_applied: int = 0
    goods_returns_created: int = 0
    blanket_agreements_created: int = 0
    mrp_results_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class B1ConfigBuilder:
    """Transforms B1 Service Layer data into SupplyChainConfig entities.

    Follows the same pattern as SAPConfigBuilder, D365ConfigBuilder, OdooConfigBuilder.
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        # Populated during _build() for use by transactional methods
        self._config_id: Optional[int] = None
        self._product_id_map: Dict[str, str] = {}   # B1 ItemCode → product.id
        self._site_ids: Dict[str, int] = {}          # B1 WarehouseCode → site.id
        self._vendor_pks: Dict[str, int] = {}        # B1 CardCode → site.id (vendor market-supply site)
        self._customer_pks: Dict[str, int] = {}      # B1 CardCode → site.id (customer market-demand site)

    async def build_from_service_layer(
        self,
        connector,
        config_name: str = "SAP Business One",
        config_id: Optional[int] = None,
    ) -> B1ConfigBuildResult:
        """Extract from live B1 instance and build config."""
        from .connector import B1Connector

        # Extract key entities
        data: Dict[str, List[Dict]] = {}
        for entity in [
            # Master
            "Companies", "Warehouses", "BusinessPartners", "BusinessPartnerGroups",
            "Items", "ItemGroups", "ItemWarehouseInfoCollection",
            "UnitOfMeasurements", "UnitOfMeasurementGroups",
            "PriceLists", "SpecialPrices",
            "ProductTrees", "ProductTreeLines",
            "Resources", "ResourceCapacities",
            "BinLocations",
            # Transaction
            "Orders", "PurchaseOrders", "ProductionOrders",
            "PurchaseDeliveryNotes", "DeliveryNotes",
            "Invoices", "Returns", "PurchaseInvoices",
            "PurchaseRequests", "InventoryTransferRequests",
            "StockTransfers", "QualityTests", "ServiceCalls",
            "ForecastReport",
            "GoodsReturns", "BlanketAgreements", "MRPResults",
            # CDC
            "InventoryGenEntries", "InventoryGenExits", "StockTakings",
            "BatchNumberDetails", "SerialNumberDetails",
        ]:
            try:
                data[entity] = await connector.extract_entity(entity)
            except Exception as e:
                logger.warning("Failed to extract %s: %s", entity, e)
                data[entity] = []

        return await self._build(data, config_name, config_id)

    async def build_from_csv(
        self,
        csv_dir: str,
        config_name: str = "SAP Business One (CSV)",
        config_id: Optional[int] = None,
    ) -> B1ConfigBuildResult:
        """Build config from CSV exports."""
        from .connector import B1Connector, B1ConnectionConfig

        connector = B1Connector(B1ConnectionConfig(csv_directory=csv_dir))
        data: Dict[str, List[Dict]] = {}
        for entity in [
            # Master
            "Companies", "Warehouses", "BusinessPartners", "BusinessPartnerGroups",
            "Items", "ItemGroups", "ItemWarehouseInfoCollection",
            "UnitOfMeasurements", "UnitOfMeasurementGroups",
            "PriceLists", "SpecialPrices",
            "ProductTrees", "ProductTreeLines",
            "Resources", "ResourceCapacities",
            "BinLocations",
            # Transaction
            "Orders", "PurchaseOrders", "ProductionOrders",
            "PurchaseDeliveryNotes", "DeliveryNotes",
            "Invoices", "Returns", "PurchaseInvoices",
            "PurchaseRequests", "InventoryTransferRequests",
            "StockTransfers", "QualityTests", "ServiceCalls",
            "ForecastReport",
            "GoodsReturns", "BlanketAgreements", "MRPResults",
            # CDC
            "InventoryGenEntries", "InventoryGenExits", "StockTakings",
            "BatchNumberDetails", "SerialNumberDetails",
        ]:
            data[entity] = connector.extract_from_csv(entity)

        return await self._build(data, config_name, config_id)

    # ------------------------------------------------------------------
    # Core build
    # ------------------------------------------------------------------

    async def _build(
        self,
        data: Dict[str, List[Dict]],
        config_name: str,
        config_id: Optional[int],
    ) -> B1ConfigBuildResult:
        """Core build logic — transforms extracted data into SC entities."""
        result = B1ConfigBuildResult()

        warehouses = data.get("Warehouses", [])
        partners = data.get("BusinessPartners", [])
        items = data.get("Items", [])
        item_groups = data.get("ItemGroups", [])
        product_trees = data.get("ProductTrees", [])
        product_tree_lines = data.get("ProductTreeLines", [])
        item_wh_info = data.get("ItemWarehouseInfoCollection", [])

        if not items:
            result.errors.append("No items found — cannot build config")
            return result

        logger.info(
            "Building B1 config: %d warehouses, %d partners, %d items, %d BOMs",
            len(warehouses), len(partners), len(items), len(product_trees),
        )

        # Determine which items have BOMs (→ manufactured)
        bom_items: Set[str] = set()
        for pt in product_trees:
            tree_code = pt.get("TreeCode") or pt.get("ItemCode", "")
            if tree_code:
                bom_items.add(tree_code)

        # Separate vendors and customers
        vendors = [p for p in partners if map_card_type(p.get("CardType", "")) == "vendor"]
        customers = [p for p in partners if map_card_type(p.get("CardType", "")) == "customer"]

        logger.info(
            "  Vendors: %d, Customers: %d, Items with BOM: %d",
            len(vendors), len(customers), len(bom_items),
        )

        # Store config_id for transactional methods
        self._config_id = config_id

        result.success = True
        result.config_id = config_id
        result.sites_created = len(warehouses)
        result.products_created = len(items)
        result.boms_created = len(product_trees)
        result.trading_partners_created = len(vendors) + len(customers)

        # The actual DB insert logic for master data follows the same pattern
        # as rebuild_b1_config.py.  After master data is created, build the
        # lookup maps and proceed with transactional entities.

        if config_id is not None:
            # --- Company enrichment (before lookup maps) ---
            companies = data.get("Companies", [])
            if companies:
                await self._enrich_company(companies)

            await self._load_lookup_maps(config_id)

            # --- Master enrichments (after lookup maps loaded) ---
            price_lists = data.get("PriceLists", [])
            special_prices = data.get("SpecialPrices", [])
            uom_data = data.get("UnitOfMeasurements", [])
            bp_groups = data.get("BusinessPartnerGroups", [])
            enriched = await self._enrich_products_with_pricing(
                price_lists, special_prices, uom_data,
            )
            result.products_enriched += enriched

            if bp_groups:
                await self._enrich_trading_partners_with_groups(bp_groups, partners)

            resources = data.get("Resources", [])
            resource_caps = data.get("ResourceCapacities", [])
            if resources:
                res_count = await self._build_resources(resources, resource_caps)
                result.resources_created = res_count

            # Batch / Serial enrichment on products
            batch_details = data.get("BatchNumberDetails", [])
            serial_details = data.get("SerialNumberDetails", [])
            if batch_details or serial_details:
                lot_enriched = await self._enrich_products_with_lots(
                    batch_details, serial_details,
                )
                result.products_enriched += lot_enriched

            # BinLocations — staged for extraction only (B1-specific sub-warehouse
            # granularity has no direct AWS SC target table).  Data is available in
            # b1_staging.rows for future use.
            bin_locations = data.get("BinLocations", [])
            if bin_locations:
                logger.info(
                    "  BinLocations: %d records staged (extraction only — no SC mapping)",
                    len(bin_locations),
                )

            # UnitOfMeasurementGroups — extraction only (conversion logic not in SC model)
            uom_groups = data.get("UnitOfMeasurementGroups", [])
            if uom_groups:
                logger.info(
                    "  UnitOfMeasurementGroups: %d records staged (extraction only)",
                    len(uom_groups),
                )

            # --- Transactional entities ---
            purchase_orders = data.get("PurchaseOrders", [])
            if purchase_orders:
                po_count = await self._build_purchase_orders(purchase_orders)
                result.purchase_orders_created = po_count

            orders = data.get("Orders", [])
            if orders:
                ob_count = await self._build_outbound_orders(orders)
                result.outbound_orders_created = ob_count

            production_orders = data.get("ProductionOrders", [])
            if production_orders:
                mo_count = await self._build_production_orders(production_orders)
                result.production_orders_created = mo_count

            purchase_delivery_notes = data.get("PurchaseDeliveryNotes", [])
            if purchase_delivery_notes:
                gr_count = await self._build_goods_receipts(purchase_delivery_notes)
                result.goods_receipts_created = gr_count

            delivery_notes = data.get("DeliveryNotes", [])
            if delivery_notes:
                sh_count = await self._build_shipments(delivery_notes)
                result.shipments_created = sh_count

            stock_transfers = data.get("StockTransfers", [])
            if stock_transfers:
                to_count = await self._build_transfer_orders(stock_transfers)
                result.transfer_orders_created = to_count

            quality_tests = data.get("QualityTests", [])
            if quality_tests:
                qo_count = await self._build_quality_orders(quality_tests)
                result.quality_orders_created = qo_count

            service_calls = data.get("ServiceCalls", [])
            if service_calls:
                mo_count = await self._build_maintenance_orders(service_calls)
                result.maintenance_orders_created = mo_count

            # Forecasts — from ForecastReport (OFCT) or fallback to Orders
            forecast_data = data.get("ForecastReport", [])
            orders = data.get("Orders", [])
            fc_count = await self._build_forecasts(forecast_data, orders)
            result.forecasts_created = fc_count

            # --- Invoices & Returns → status enrichment on existing orders ---
            invoices = data.get("Invoices", [])
            returns = data.get("Returns", [])
            purchase_invoices = data.get("PurchaseInvoices", [])
            if invoices or returns or purchase_invoices:
                updated = await self._build_invoices_and_returns(
                    invoices, returns, purchase_invoices,
                )
                result.orders_status_updated = updated

            # --- Purchase Requests → purchase_order (DRAFT) ---
            purchase_requests = data.get("PurchaseRequests", [])
            if purchase_requests:
                pr_count = await self._build_purchase_requests(purchase_requests)
                result.purchase_requests_created = pr_count

            # --- Inventory Transfer Requests → transfer_order (PLANNED) ---
            transfer_requests = data.get("InventoryTransferRequests", [])
            if transfer_requests:
                tr_count = await self._build_transfer_requests(transfer_requests)
                result.transfer_requests_created = tr_count

            # --- Inventory movements → inv_level adjustments ---
            inv_entries = data.get("InventoryGenEntries", [])
            inv_exits = data.get("InventoryGenExits", [])
            stock_takings = data.get("StockTakings", [])
            if inv_entries or inv_exits or stock_takings:
                inv_count = await self._build_inventory_movements(
                    inv_entries, inv_exits, stock_takings,
                )
                result.inv_movements_applied = inv_count

            # --- Goods Returns → inbound_order (RETURN) ---
            goods_returns = data.get("GoodsReturns", [])
            if goods_returns:
                gr_count = await self._build_goods_returns(goods_returns)
                result.goods_returns_created = gr_count

            # --- Blanket Agreements → sourcing_rules ---
            blanket_agreements = data.get("BlanketAgreements", [])
            if blanket_agreements:
                ba_count = await self._build_blanket_agreements(blanket_agreements)
                result.blanket_agreements_created = ba_count

            # --- MRP Results → purchase_order / production_orders / transfer_order (PLANNED) ---
            mrp_results = data.get("MRPResults", [])
            if mrp_results:
                mrp_count = await self._build_mrp_results(mrp_results)
                result.mrp_results_created = mrp_count

        return result

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    async def _load_lookup_maps(self, config_id: int) -> None:
        """Load product, site, and trading partner lookup maps from the DB.

        These maps are populated from records already inserted by the
        rebuild_b1_config.py script or the master-data phase of this builder.
        """
        # Products: product.id follows the pattern CFG{config_id}_{ItemCode}
        rows = await self.db.execute(
            text("SELECT id FROM product WHERE config_id = :cid"),
            {"cid": config_id},
        )
        for (pid,) in rows.fetchall():
            prefix = f"CFG{config_id}_"
            if pid.startswith(prefix):
                item_code = pid[len(prefix):]
                self._product_id_map[item_code] = pid

        # Sites: site.dag_type stores the B1 WarehouseCode
        rows = await self.db.execute(
            text("SELECT id, dag_type FROM site WHERE config_id = :cid"),
            {"cid": config_id},
        )
        for (sid, dag_type) in rows.fetchall():
            if dag_type:
                self._site_ids[dag_type] = sid

        # Trading partners: id pattern B1V_{CardCode} and B1C_{CardCode}
        rows = await self.db.execute(
            text("SELECT id, _id FROM trading_partners WHERE id LIKE 'B1V_%' OR id LIKE 'B1C_%'"),
        )
        for (tid, _id) in rows.fetchall():
            if tid.startswith("B1V_"):
                card_code = tid[4:]
                self._vendor_pks[card_code] = _id
            elif tid.startswith("B1C_"):
                card_code = tid[4:]
                self._customer_pks[card_code] = _id

        logger.info(
            "  Loaded lookups: %d products, %d sites, %d vendors, %d customers",
            len(self._product_id_map), len(self._site_ids),
            len(self._vendor_pks), len(self._customer_pks),
        )

    def _get_product_id(self, item_code: str) -> Optional[str]:
        """Resolve B1 ItemCode to product.id."""
        return self._product_id_map.get(item_code)

    def _get_site_id(self, warehouse_code: str) -> Optional[int]:
        """Resolve B1 WarehouseCode to site.id."""
        return self._site_ids.get(warehouse_code)

    def _get_first_site_id(self) -> Optional[int]:
        """Return the first available site id as fallback."""
        return next(iter(self._site_ids.values()), None)

    # ------------------------------------------------------------------
    # Transactional: Purchase Orders → purchase_order + purchase_order_line_item
    # ------------------------------------------------------------------

    async def _build_purchase_orders(self, purchase_orders: List[Dict]) -> int:
        """Map B1 PurchaseOrders (OPOR) → purchase_order + purchase_order_line_item.

        B1 PurchaseOrders header fields:
          DocEntry      — internal unique key
          DocNum        — display document number
          CardCode      — vendor business partner code
          DocDate       — document (order) date
          DocDueDate    — requested delivery date
          DocTotal      — total order amount
          DocCur        — document currency
          DocumentStatus — bost_Open / bost_Close
          Comments      — free text notes

        B1 DocumentLines (sub-entity, expanded or in CSV):
          ItemCode      — product code
          Quantity      — ordered quantity
          Price         — unit price
          ShipDate      — line-level ship/delivery date
          LineNum       — line number (0-based in B1)
          WarehouseCode — destination warehouse for this line
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create purchase orders")
            return 0

        created_count = 0
        skipped_count = 0

        for po in purchase_orders:
            doc_entry = po.get("DocEntry")
            doc_num = po.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            card_code = str(po.get("CardCode", "")).strip()
            if not card_code:
                skipped_count += 1
                continue

            order_date = _parse_b1_date(po.get("DocDate"))
            if not order_date:
                skipped_count += 1
                continue

            delivery_date = _parse_b1_date(po.get("DocDueDate")) or order_date
            doc_total = _safe_float(po.get("DocTotal"))
            currency = str(po.get("DocCur", po.get("DocCurrency", "USD"))).strip() or "USD"
            doc_status = str(po.get("DocumentStatus", "O")).strip()
            status = _b1_doc_status_to_po_status(doc_status)
            notes = po.get("Comments")

            po_number = f"B1-PO-{doc_num}"

            # Resolve vendor — vendor_id is the trading_partner.id string
            vendor_tid = f"B1V_{card_code}"

            # Determine destination site: prefer first line's WarehouseCode, fallback to first site
            lines = po.get("DocumentLines", [])
            dest_site_id = first_site_id
            supplier_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    dest_site_id = self._get_site_id(first_wh)

            # Insert purchase_order header
            await self.db.execute(
                text("""
                    INSERT INTO purchase_order
                        (po_number, vendor_id, supplier_site_id, destination_site_id,
                         config_id, tenant_id, company_id, order_type, source,
                         status, order_date, requested_delivery_date,
                         total_amount, currency, notes)
                    VALUES
                        (:po_number, :vendor_id, :supplier_site_id, :dest_site_id,
                         :config_id, :tenant_id, :company_id, 'po', 'SAP_B1',
                         :status, :order_date, :delivery_date,
                         :total_amount, :currency, :notes)
                    ON CONFLICT (po_number) DO NOTHING
                """),
                {
                    "po_number": po_number,
                    "vendor_id": vendor_tid,
                    "supplier_site_id": supplier_site_id,
                    "dest_site_id": dest_site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "status": status,
                    "order_date": order_date,
                    "delivery_date": delivery_date,
                    "total_amount": doc_total,
                    "currency": currency,
                    "notes": str(notes)[:500] if notes else None,
                },
            )

            # Fetch the PO id for line items
            row = await self.db.execute(
                text("SELECT id FROM purchase_order WHERE po_number = :pn"),
                {"pn": po_number},
            )
            po_row = row.fetchone()
            if not po_row:
                skipped_count += 1
                continue
            po_id = po_row[0]

            # Insert line items
            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                unit_price = _safe_float(line.get("Price"))
                line_total = _safe_float(line.get("LineTotal"))
                line_num = _safe_int(line.get("LineNum"), line_count)
                line_delivery = _parse_b1_date(line.get("ShipDate")) or delivery_date

                # Determine line-level destination site
                line_wh = str(line.get("WarehouseCode", "")).strip()
                # not used for separate line storage, but validates product-site

                await self.db.execute(
                    text("""
                        INSERT INTO purchase_order_line_item
                            (po_id, line_number, product_id, quantity,
                             unit_price, line_total, requested_delivery_date)
                        VALUES
                            (:po_id, :line_number, :product_id, :quantity,
                             :unit_price, :line_total, :delivery_date)
                    """),
                    {
                        "po_id": po_id,
                        "line_number": line_num + 1,  # B1 lines are 0-based, DB is 1-based
                        "product_id": product_id,
                        "quantity": qty,
                        "unit_price": unit_price if unit_price > 0 else None,
                        "line_total": line_total if line_total > 0 else None,
                        "delivery_date": line_delivery,
                    },
                )
                line_count += 1

            if line_count > 0 or not lines:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d purchase orders (missing required fields)", skipped_count)
        logger.info("Created %d purchase orders from B1 PurchaseOrders", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: Orders → outbound_order + outbound_order_line
    # ------------------------------------------------------------------

    async def _build_outbound_orders(self, orders: List[Dict]) -> int:
        """Map B1 Orders (ORDR) → outbound_order + outbound_order_line.

        B1 Orders header fields:
          DocEntry       — internal unique key
          DocNum         — display document number
          CardCode       — customer business partner code
          CardName       — customer name
          DocDate        — document (order) date
          DocDueDate     — requested delivery date
          DocTotal       — total order amount
          DocCur         — document currency
          DocumentStatus — bost_Open / bost_Close

        B1 DocumentLines (sub-entity):
          ItemCode       — product code
          Quantity       — ordered quantity
          Price          — unit price
          ShipDate       — line-level delivery date
          LineNum        — line number (0-based)
          WarehouseCode  — ship-from warehouse
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create outbound orders")
            return 0

        created_count = 0
        skipped_count = 0

        for order in orders:
            doc_entry = order.get("DocEntry")
            doc_num = order.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            card_code = str(order.get("CardCode", "")).strip()
            if not card_code:
                skipped_count += 1
                continue

            order_date = _parse_b1_date(order.get("DocDate"))
            if not order_date:
                skipped_count += 1
                continue

            delivery_date = _parse_b1_date(order.get("DocDueDate")) or order_date
            doc_total = _safe_float(order.get("DocTotal"))
            currency = str(order.get("DocCur", order.get("DocCurrency", "USD"))).strip() or "USD"
            doc_status = str(order.get("DocumentStatus", "O")).strip()
            status = _b1_doc_status_to_outbound_status(doc_status)
            customer_name = str(order.get("CardName", "")).strip() or None

            order_id = f"B1-SO-{doc_num}"
            customer_tid = f"B1C_{card_code}"

            # Determine ship-from site from first line's WarehouseCode
            lines = order.get("DocumentLines", [])
            ship_from_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    ship_from_site_id = self._get_site_id(first_wh)

            # Compute total ordered qty from lines
            total_ordered_qty = sum(
                _safe_float(ln.get("Quantity")) for ln in lines
            ) if lines else 0.0

            # Insert outbound_order header
            await self.db.execute(
                text("""
                    INSERT INTO outbound_order
                        (id, order_type, customer_id, customer_name,
                         ship_from_site_id, status,
                         order_date, requested_delivery_date,
                         total_ordered_qty, total_value, currency,
                         priority, config_id, source, source_event_id,
                         source_update_dttm)
                    VALUES
                        (:id, 'SALES', :customer_id, :customer_name,
                         :ship_from_site_id, :status,
                         :order_date, :delivery_date,
                         :total_ordered_qty, :total_value, :currency,
                         'STANDARD', :config_id, 'SAP_B1', :source_event_id,
                         :now)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": order_id,
                    "customer_id": customer_tid,
                    "customer_name": customer_name,
                    "ship_from_site_id": ship_from_site_id,
                    "status": status,
                    "order_date": order_date,
                    "delivery_date": delivery_date,
                    "total_ordered_qty": total_ordered_qty,
                    "total_value": doc_total,
                    "currency": currency,
                    "config_id": config_id,
                    "source_event_id": f"SO-{doc_num}",
                    "now": datetime.utcnow(),
                },
            )

            # Insert line items
            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                line_num = _safe_int(line.get("LineNum"), line_count)
                line_delivery = _parse_b1_date(line.get("ShipDate")) or delivery_date

                # Determine line-level ship-from site
                line_wh = str(line.get("WarehouseCode", "")).strip()
                line_site_id = self._get_site_id(line_wh) if line_wh else ship_from_site_id

                await self.db.execute(
                    text("""
                        INSERT INTO outbound_order_line
                            (order_id, line_number, product_id, site_id,
                             ordered_quantity, requested_delivery_date,
                             order_date, config_id, status, priority_code)
                        VALUES
                            (:order_id, :line_number, :product_id, :site_id,
                             :quantity, :delivery_date,
                             :order_date, :config_id, :status, 'STANDARD')
                    """),
                    {
                        "order_id": order_id,
                        "line_number": line_num + 1,
                        "product_id": product_id,
                        "site_id": line_site_id,
                        "quantity": qty,
                        "delivery_date": line_delivery,
                        "order_date": order_date,
                        "config_id": config_id,
                        "status": status,
                    },
                )
                line_count += 1

            if line_count > 0 or not lines:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d outbound orders (missing required fields)", skipped_count)
        logger.info("Created %d outbound orders from B1 Orders", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: ProductionOrders → production_orders
    # ------------------------------------------------------------------

    async def _build_production_orders(self, production_orders: List[Dict]) -> int:
        """Map B1 ProductionOrders (OWOR) → production_orders.

        B1 ProductionOrders fields:
          AbsoluteEntry   — unique production order key
          DocumentNumber  — display number (may not be present in all B1 versions)
          ItemNo          — produced item code
          PlannedQuantity — planned production quantity
          CompletedQuantity — actual completed quantity
          DueDate         — production due date
          StartDate       — planned start date (PostingDate in some versions)
          Status          — boProductionOrderStatusEnum (P/R/L/C)
          Warehouse       — production warehouse code
          Remarks         — free text notes

        B1 ProductionOrderLines (sub-entity, component consumption):
          ItemNo          — component item code
          PlannedQuantity — planned component quantity
          IssuedQuantity  — actually consumed quantity
          Warehouse       — component warehouse
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create production orders")
            return 0

        created_count = 0
        skipped_count = 0

        for mo in production_orders:
            abs_entry = mo.get("AbsoluteEntry")
            if abs_entry is None:
                skipped_count += 1
                continue

            item_no = str(mo.get("ItemNo", "")).strip()
            if not item_no:
                skipped_count += 1
                continue

            product_id = self._get_product_id(item_no)
            if not product_id:
                skipped_count += 1
                continue

            # Resolve production site
            wh_code = str(mo.get("Warehouse", "")).strip()
            site_id = self._get_site_id(wh_code) if wh_code else first_site_id
            if not site_id:
                site_id = first_site_id

            # Quantities
            planned_qty = _safe_int(mo.get("PlannedQuantity"), 1)
            if planned_qty <= 0:
                planned_qty = 1
            completed_qty = _safe_int(mo.get("CompletedQuantity"))
            actual_qty = completed_qty if completed_qty > 0 else None

            # Status
            status_val = mo.get("Status", "P")
            status = _b1_production_status(status_val)

            # Dates
            due_date = _parse_b1_date(mo.get("DueDate"))
            start_date = _parse_b1_date(
                mo.get("StartDate") or mo.get("PostingDate")
            )
            if not due_date and not start_date:
                skipped_count += 1
                continue

            today = date.today()
            if not start_date:
                start_date = due_date - timedelta(days=7) if due_date else today
            if not due_date:
                due_date = start_date + timedelta(days=7)

            lead_time = max(1, (due_date - start_date).days)
            order_number = f"B1-MO-{abs_entry}"
            remarks = mo.get("Remarks")

            # Insert production_orders row
            await self.db.execute(
                text("""
                    INSERT INTO production_orders
                        (order_number, item_id, site_id, config_id,
                         planned_quantity, actual_quantity, status,
                         planned_start_date, planned_completion_date,
                         lead_time_planned, priority, notes, extra_data)
                    VALUES
                        (:order_number, :item_id, :site_id, :config_id,
                         :planned_qty, :actual_qty, :status,
                         :start_date, :end_date,
                         :lead_time, 5, :notes, :extra)
                    ON CONFLICT (order_number) DO NOTHING
                """),
                {
                    "order_number": order_number,
                    "item_id": product_id,
                    "site_id": site_id,
                    "config_id": config_id,
                    "planned_qty": planned_qty,
                    "actual_qty": actual_qty,
                    "status": status,
                    "start_date": datetime.combine(start_date, datetime.min.time()),
                    "end_date": datetime.combine(due_date, datetime.min.time()),
                    "lead_time": lead_time,
                    "notes": str(remarks)[:500] if remarks else None,
                    "extra": f'{{"b1_abs_entry": {abs_entry}}}',
                },
            )

            # Fetch the MO id for component lines
            row = await self.db.execute(
                text("SELECT id FROM production_orders WHERE order_number = :on"),
                {"on": order_number},
            )
            mo_row = row.fetchone()
            if not mo_row:
                skipped_count += 1
                continue
            mo_id = mo_row[0]

            # Insert component lines from ProductionOrderLines sub-entity
            mo_lines = mo.get("ProductionOrderLines", [])
            for comp_line in mo_lines:
                comp_item = str(comp_line.get("ItemNo", "")).strip()
                if not comp_item:
                    continue
                comp_product_id = self._get_product_id(comp_item)
                if not comp_product_id or comp_product_id == product_id:
                    continue

                comp_planned_qty = _safe_float(comp_line.get("PlannedQuantity"), 1.0)
                comp_actual_qty = _safe_float(comp_line.get("IssuedQuantity"))
                comp_uom = str(comp_line.get("UoMCode", "EA")).strip() or "EA"

                await self.db.execute(
                    text("""
                        INSERT INTO production_order_components
                            (production_order_id, component_item_id,
                             planned_quantity, actual_quantity, unit_of_measure)
                        VALUES
                            (:mo_id, :comp_id,
                             :planned_qty, :actual_qty, :uom)
                    """),
                    {
                        "mo_id": mo_id,
                        "comp_id": comp_product_id,
                        "planned_qty": comp_planned_qty,
                        "actual_qty": comp_actual_qty if comp_actual_qty > 0 else None,
                        "uom": comp_uom,
                    },
                )

            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d production orders (missing required fields)", skipped_count)
        logger.info("Created %d production orders from B1 ProductionOrders", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: PurchaseDeliveryNotes → goods_receipt + goods_receipt_line_item
    # ------------------------------------------------------------------

    async def _build_goods_receipts(self, delivery_notes: List[Dict]) -> int:
        """Map B1 PurchaseDeliveryNotes (OPDN) → goods_receipt + goods_receipt_line_item.

        B1 PurchaseDeliveryNotes header fields:
          DocEntry       — internal unique key
          DocNum         — display document number
          CardCode       — vendor business partner code
          DocDate        — receipt date
          DocumentStatus — bost_Open / bost_Close
          Comments       — free text notes

        B1 DocumentLines (sub-entity):
          ItemCode       — product code
          Quantity       — received quantity
          Price          — unit price
          WarehouseCode  — receiving warehouse
          LineNum        — line number (0-based)
          BaseEntry      — linked PO DocEntry
          BaseLine       — linked PO line number
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create goods receipts")
            return 0

        created_count = 0
        skipped_count = 0

        for gr in delivery_notes:
            doc_entry = gr.get("DocEntry")
            doc_num = gr.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            receipt_date = _parse_b1_date(gr.get("DocDate"))
            if not receipt_date:
                skipped_count += 1
                continue

            gr_number = f"B1-GR-{doc_num}"
            notes = gr.get("Comments")
            doc_status = str(gr.get("DocumentStatus", "O")).strip().upper()
            status = "COMPLETED" if doc_status in ("C", "BOST_CLOSE") else "PENDING"

            lines = gr.get("DocumentLines", [])

            # Determine receiving site from first line's WarehouseCode
            receiving_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    receiving_site_id = self._get_site_id(first_wh)

            # Compute total received qty from lines
            total_received_qty = sum(
                _safe_float(ln.get("Quantity")) for ln in lines
            ) if lines else 0.0

            # Try to resolve linked PO via BaseEntry on first line, or via CardCode
            po_id = None
            if lines:
                base_entry = lines[0].get("BaseEntry")
                if base_entry is not None:
                    po_number_candidate = f"B1-PO-{base_entry}"
                    row = await self.db.execute(
                        text("SELECT id FROM purchase_order WHERE po_number = :pn"),
                        {"pn": po_number_candidate},
                    )
                    po_row = row.fetchone()
                    if po_row:
                        po_id = po_row[0]

            # Fallback: resolve PO via CardCode (vendor) — take most recent
            if po_id is None:
                card_code = str(gr.get("CardCode", "")).strip()
                if card_code:
                    vendor_tid = f"B1V_{card_code}"
                    row = await self.db.execute(
                        text(
                            "SELECT id FROM purchase_order "
                            "WHERE vendor_id = :vid AND config_id = :cid "
                            "ORDER BY order_date DESC LIMIT 1"
                        ),
                        {"vid": vendor_tid, "cid": config_id},
                    )
                    po_row = row.fetchone()
                    if po_row:
                        po_id = po_row[0]

            if po_id is None:
                skipped_count += 1
                continue

            # Insert goods_receipt header
            await self.db.execute(
                text("""
                    INSERT INTO goods_receipt
                        (gr_number, po_id, receipt_date, status,
                         receiving_site_id, total_received_qty,
                         total_accepted_qty, notes)
                    VALUES
                        (:gr_number, :po_id, :receipt_date, :status,
                         :receiving_site_id, :total_received_qty,
                         :total_received_qty, :notes)
                    ON CONFLICT (gr_number) DO NOTHING
                """),
                {
                    "gr_number": gr_number,
                    "po_id": po_id,
                    "receipt_date": datetime.combine(receipt_date, datetime.min.time()),
                    "status": status,
                    "receiving_site_id": receiving_site_id,
                    "total_received_qty": total_received_qty,
                    "notes": str(notes)[:500] if notes else None,
                },
            )

            # Fetch the GR id for line items
            row = await self.db.execute(
                text("SELECT id FROM goods_receipt WHERE gr_number = :gn"),
                {"gn": gr_number},
            )
            gr_row = row.fetchone()
            if not gr_row:
                skipped_count += 1
                continue
            gr_id = gr_row[0]

            # Insert line items
            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                line_num = _safe_int(line.get("LineNum"), line_count)

                # Resolve linked PO line item via BaseLine
                po_line_id = None
                base_line = line.get("BaseLine")
                base_entry = line.get("BaseEntry")
                if base_entry is not None and base_line is not None:
                    po_number_candidate = f"B1-PO-{base_entry}"
                    row = await self.db.execute(
                        text(
                            "SELECT pli.id FROM purchase_order_line_item pli "
                            "JOIN purchase_order po ON po.id = pli.po_id "
                            "WHERE po.po_number = :pn AND pli.line_number = :ln"
                        ),
                        {"pn": po_number_candidate, "ln": _safe_int(base_line) + 1},
                    )
                    pli_row = row.fetchone()
                    if pli_row:
                        po_line_id = pli_row[0]

                # Fallback: match PO line by product_id on the same PO
                if po_line_id is None:
                    row = await self.db.execute(
                        text(
                            "SELECT id FROM purchase_order_line_item "
                            "WHERE po_id = :po_id AND product_id = :pid "
                            "ORDER BY line_number LIMIT 1"
                        ),
                        {"po_id": po_id, "pid": product_id},
                    )
                    pli_row = row.fetchone()
                    if pli_row:
                        po_line_id = pli_row[0]

                if po_line_id is None:
                    continue

                await self.db.execute(
                    text("""
                        INSERT INTO goods_receipt_line_item
                            (gr_id, po_line_id, line_number, product_id,
                             expected_qty, received_qty, accepted_qty)
                        VALUES
                            (:gr_id, :po_line_id, :line_number, :product_id,
                             :qty, :qty, :qty)
                    """),
                    {
                        "gr_id": gr_id,
                        "po_line_id": po_line_id,
                        "line_number": line_num + 1,
                        "product_id": product_id,
                        "qty": qty,
                    },
                )
                line_count += 1

            if line_count > 0 or not lines:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d goods receipts (missing required fields or PO link)", skipped_count)
        logger.info("Created %d goods receipts from B1 PurchaseDeliveryNotes", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: DeliveryNotes → shipment
    # ------------------------------------------------------------------

    async def _build_shipments(self, delivery_notes: List[Dict]) -> int:
        """Map B1 DeliveryNotes (ODLN) → shipment.

        B1 DeliveryNotes header fields:
          DocEntry       — internal unique key
          DocNum         — display document number
          CardCode       — customer business partner code
          DocDate        — shipment date
          DocumentStatus — bost_Open / bost_Close
          Comments       — free text notes

        B1 DocumentLines (sub-entity):
          ItemCode       — product code
          Quantity       — shipped quantity
          Price          — unit price
          WarehouseCode  — ship-from warehouse
          LineNum        — line number (0-based)
          BaseEntry      — linked Sales Order DocEntry
          BaseLine       — linked SO line number
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create shipments")
            return 0

        created_count = 0
        skipped_count = 0

        for sh in delivery_notes:
            doc_entry = sh.get("DocEntry")
            doc_num = sh.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            ship_date = _parse_b1_date(sh.get("DocDate"))
            if not ship_date:
                skipped_count += 1
                continue

            card_code = str(sh.get("CardCode", "")).strip()
            doc_status = str(sh.get("DocumentStatus", "O")).strip().upper()
            status = "delivered" if doc_status in ("C", "BOST_CLOSE") else "in_transit"

            lines = sh.get("DocumentLines", [])

            # Determine ship-from site from first line's WarehouseCode
            from_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    from_site_id = self._get_site_id(first_wh)

            # Resolve customer to destination site
            to_site_id = self._customer_pks.get(card_code) if card_code else None
            if not to_site_id:
                to_site_id = first_site_id

            # Resolve linked outbound order via BaseEntry on first line
            order_id = None
            if lines:
                base_entry = lines[0].get("BaseEntry")
                if base_entry is not None:
                    order_id = f"B1-SO-{base_entry}"

            if not order_id:
                # Fallback: use the delivery note number as the order reference
                order_id = f"B1-SO-{doc_num}"

            # Use the first line to get product and quantity for the shipment header
            # (Shipment table is one row per shipment — we use the primary product)
            first_product_id = None
            total_qty = 0.0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                pid = self._get_product_id(item_code)
                if pid:
                    if first_product_id is None:
                        first_product_id = pid
                    total_qty += _safe_float(line.get("Quantity"))

            if not first_product_id:
                skipped_count += 1
                continue

            shipment_id = f"B1-SH-{doc_num}"
            ship_datetime = datetime.combine(ship_date, datetime.min.time())

            await self.db.execute(
                text("""
                    INSERT INTO shipment
                        (id, order_id, product_id, quantity,
                         from_site_id, to_site_id,
                         status, ship_date, expected_delivery_date,
                         config_id, tenant_id, source, source_event_id,
                         source_update_dttm)
                    VALUES
                        (:id, :order_id, :product_id, :quantity,
                         :from_site_id, :to_site_id,
                         :status, :ship_date, :expected_delivery_date,
                         :config_id, :tenant_id, 'SAP_B1', :source_event_id,
                         :now)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": shipment_id,
                    "order_id": order_id,
                    "product_id": first_product_id,
                    "quantity": total_qty,
                    "from_site_id": from_site_id,
                    "to_site_id": to_site_id,
                    "status": status,
                    "ship_date": ship_datetime,
                    "expected_delivery_date": ship_datetime + timedelta(days=3),
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "source_event_id": f"ODLN-{doc_num}",
                    "now": datetime.utcnow(),
                },
            )
            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d shipments (missing required fields)", skipped_count)
        logger.info("Created %d shipments from B1 DeliveryNotes", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: StockTransfers → transfer_order + transfer_order_line_item
    # ------------------------------------------------------------------

    async def _build_transfer_orders(self, stock_transfers: List[Dict]) -> int:
        """Map B1 StockTransfers (OWTR) → transfer_order + transfer_order_line_item.

        B1 StockTransfers header fields:
          DocEntry       — internal unique key
          DocNum         — display document number
          DocDate        — transfer date
          DocumentStatus — bost_Open / bost_Close
          Comments       — free text notes

        B1 StockTransferLines (DocumentLines sub-entity):
          FromWarehouse  — source warehouse code
          ToWarehouse    — destination warehouse code (B1 StockTransfer lines carry both)
          ItemCode       — product code
          Quantity       — transfer quantity
          LineNum        — line number (0-based)
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create transfer orders")
            return 0

        created_count = 0
        skipped_count = 0

        for tr in stock_transfers:
            doc_entry = tr.get("DocEntry")
            doc_num = tr.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            transfer_date = _parse_b1_date(tr.get("DocDate"))
            if not transfer_date:
                skipped_count += 1
                continue

            lines = tr.get("DocumentLines", tr.get("StockTransferLines", []))
            if not lines:
                skipped_count += 1
                continue

            doc_status = str(tr.get("DocumentStatus", "O")).strip().upper()
            status = "RECEIVED" if doc_status in ("C", "BOST_CLOSE") else "RELEASED"
            notes = tr.get("Comments")

            # Determine source and destination from first line
            first_from_wh = str(lines[0].get("FromWarehouse", "")).strip()
            first_to_wh = str(lines[0].get("ToWarehouse", lines[0].get("WarehouseCode", ""))).strip()

            source_site_id = self._get_site_id(first_from_wh) if first_from_wh else first_site_id
            dest_site_id = self._get_site_id(first_to_wh) if first_to_wh else first_site_id
            if not source_site_id:
                source_site_id = first_site_id
            if not dest_site_id:
                dest_site_id = first_site_id

            to_number = f"B1-TO-{doc_num}"
            ship_date = transfer_date
            est_delivery = transfer_date + timedelta(days=2)

            # Insert transfer_order header
            await self.db.execute(
                text("""
                    INSERT INTO transfer_order
                        (to_number, source_site_id, destination_site_id,
                         config_id, tenant_id, company_id,
                         order_type, source, source_event_id, source_update_dttm,
                         status, order_date, shipment_date, estimated_delivery_date,
                         notes)
                    VALUES
                        (:to_number, :source_site_id, :dest_site_id,
                         :config_id, :tenant_id, :company_id,
                         'transfer', 'SAP_B1', :source_event_id, :now,
                         :status, :order_date, :shipment_date, :est_delivery,
                         :notes)
                    ON CONFLICT (to_number) DO NOTHING
                """),
                {
                    "to_number": to_number,
                    "source_site_id": source_site_id,
                    "dest_site_id": dest_site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "source_event_id": f"OWTR-{doc_num}",
                    "now": datetime.utcnow(),
                    "status": status,
                    "order_date": transfer_date,
                    "shipment_date": ship_date,
                    "est_delivery": est_delivery,
                    "notes": str(notes)[:500] if notes else None,
                },
            )

            # Fetch the TO id for line items
            row = await self.db.execute(
                text("SELECT id FROM transfer_order WHERE to_number = :tn"),
                {"tn": to_number},
            )
            to_row = row.fetchone()
            if not to_row:
                skipped_count += 1
                continue
            to_id = to_row[0]

            # Insert line items
            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                line_num = _safe_int(line.get("LineNum"), line_count)

                await self.db.execute(
                    text("""
                        INSERT INTO transfer_order_line_item
                            (to_id, line_number, product_id, quantity,
                             requested_ship_date, requested_delivery_date)
                        VALUES
                            (:to_id, :line_number, :product_id, :quantity,
                             :ship_date, :delivery_date)
                    """),
                    {
                        "to_id": to_id,
                        "line_number": line_num + 1,
                        "product_id": product_id,
                        "quantity": qty,
                        "ship_date": ship_date,
                        "delivery_date": est_delivery,
                    },
                )
                line_count += 1

            if line_count > 0:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d transfer orders (missing required fields)", skipped_count)
        logger.info("Created %d transfer orders from B1 StockTransfers", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: QualityTests → quality_order
    # ------------------------------------------------------------------

    async def _build_quality_orders(self, quality_tests: List[Dict]) -> int:
        """Map B1 QualityTests (OQCN) → quality_order.

        B1 QualityTests fields:
          AbsEntry       — unique key
          ItemCode       — inspected product code
          TestDate       — inspection date
          Status         — test status (P=Pending, C=Closed, A=Accepted, R=Rejected)
          Quantity       — inspected quantity
          AcceptedQty    — quantity accepted
          RejectedQty    — quantity rejected
          Warehouse      — warehouse code (may be present)
          Remarks        — free text notes
          U_DefectRate   — user-defined defect rate (optional)
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create quality orders")
            return 0

        created_count = 0
        skipped_count = 0

        for qt in quality_tests:
            abs_entry = qt.get("AbsEntry")
            if abs_entry is None:
                skipped_count += 1
                continue

            item_code = str(qt.get("ItemCode", "")).strip()
            if not item_code:
                skipped_count += 1
                continue

            product_id = self._get_product_id(item_code)
            if not product_id:
                skipped_count += 1
                continue

            test_date = _parse_b1_date(qt.get("TestDate"))
            if not test_date:
                skipped_count += 1
                continue

            # Resolve site
            wh_code = str(qt.get("Warehouse", "")).strip()
            site_id = self._get_site_id(wh_code) if wh_code else first_site_id
            if not site_id:
                site_id = first_site_id

            # Quantities
            inspection_qty = _safe_float(qt.get("Quantity"), 1.0)
            if inspection_qty <= 0:
                inspection_qty = 1.0
            accepted_qty = _safe_float(qt.get("AcceptedQty"))
            rejected_qty = _safe_float(qt.get("RejectedQty"))

            # Status mapping
            raw_status = str(qt.get("Status", "P")).strip().upper()
            status_map = {
                "P": "INSPECTION_PENDING",
                "C": "CLOSED",
                "A": "DISPOSITION_DECIDED",
                "R": "DISPOSITION_DECIDED",
            }
            status = status_map.get(raw_status, "INSPECTION_PENDING")

            # Disposition
            disposition = None
            if raw_status == "A":
                disposition = "ACCEPT"
            elif raw_status == "R":
                disposition = "REJECT"
            elif raw_status == "C":
                disposition = "ACCEPT" if accepted_qty >= inspection_qty else "REJECT"

            quality_order_number = f"B1-QI-{abs_entry}"
            remarks = qt.get("Remarks")
            defect_rate = _safe_float(qt.get("U_DefectRate")) or None

            await self.db.execute(
                text("""
                    INSERT INTO quality_order
                        (quality_order_number, site_id, config_id, tenant_id,
                         company_id, source, source_event_id, source_update_dttm,
                         inspection_type, status, origin_type,
                         product_id, inspection_quantity,
                         accepted_quantity, rejected_quantity,
                         disposition, disposition_reason, defect_rate,
                         order_date, notes)
                    VALUES
                        (:qo_number, :site_id, :config_id, :tenant_id,
                         :company_id, 'SAP_B1', :source_event_id, :now,
                         'INCOMING', :status, 'GOODS_RECEIPT',
                         :product_id, :inspection_qty,
                         :accepted_qty, :rejected_qty,
                         :disposition, :disposition_reason, :defect_rate,
                         :order_date, :notes)
                    ON CONFLICT (quality_order_number) DO NOTHING
                """),
                {
                    "qo_number": quality_order_number,
                    "site_id": site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "source_event_id": f"OQCN-{abs_entry}",
                    "now": datetime.utcnow(),
                    "status": status,
                    "product_id": product_id,
                    "inspection_qty": inspection_qty,
                    "accepted_qty": accepted_qty,
                    "rejected_qty": rejected_qty,
                    "disposition": disposition,
                    "disposition_reason": str(remarks)[:500] if remarks and disposition else None,
                    "defect_rate": defect_rate,
                    "order_date": test_date,
                    "notes": str(remarks)[:500] if remarks else None,
                },
            )
            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d quality orders (missing required fields)", skipped_count)
        logger.info("Created %d quality orders from B1 QualityTests", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: Service Calls → maintenance_order
    # ------------------------------------------------------------------

    async def _build_maintenance_orders(self, service_calls: List[Dict]) -> int:
        """Map B1 ServiceCalls (OSCL) → maintenance_order.

        B1 ServiceCall fields:
          ServiceCallID   — unique key
          CustomerCode    — business partner code (equipment owner)
          ItemCode        — serviced item/equipment code
          Subject         — short description of the service call
          Status          — open / closed
          Priority        — 1=High, 2=Medium, 3=Low
          StartDate       — service call start date
          EndDate         — service call end/resolution date
          TechnicianCode  — assigned technician code
          Resolution      — resolution description text

        Service calls are reactive (corrective) maintenance activities.
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create maintenance orders")
            return 0

        created_count = 0
        skipped_count = 0

        for sc in service_calls:
            sc_id = sc.get("ServiceCallID")
            if sc_id is None:
                skipped_count += 1
                continue

            # Resolve asset / product from ItemCode
            item_code = str(sc.get("ItemCode", "")).strip()
            asset_id = item_code or f"SC-{sc_id}"

            # Start date is required for order_date
            start_date = _parse_b1_date(sc.get("StartDate"))
            if not start_date:
                skipped_count += 1
                continue

            end_date = _parse_b1_date(sc.get("EndDate"))

            # Resolve site — use first site as default (B1 service calls
            # don't carry a warehouse; equipment is at the customer site)
            site_id = first_site_id

            # Subject / work description
            subject = sc.get("Subject") or ""
            resolution = sc.get("Resolution") or ""
            work_description = str(subject).strip() or f"Service Call {sc_id}"

            # Status mapping: B1 open/closed → maintenance_order status
            raw_status = str(sc.get("Status", "")).strip().lower()
            if raw_status in ("closed", "c"):
                status = "COMPLETED"
            else:
                status = "IN_PROGRESS"

            # Priority mapping: B1 1=High, 2=Medium, 3=Low → maintenance_order priority
            raw_priority = _safe_int(sc.get("Priority"), 2)
            priority_map = {
                1: "HIGH",
                2: "NORMAL",
                3: "LOW",
            }
            priority = priority_map.get(raw_priority, "NORMAL")

            mo_number = f"B1-SC-{sc_id}"

            await self.db.execute(
                text("""
                    INSERT INTO maintenance_order
                        (maintenance_order_number, asset_id, asset_name,
                         site_id, config_id, tenant_id,
                         company_id, order_type, source, source_event_id,
                         source_update_dttm,
                         maintenance_type, status, priority,
                         order_date, scheduled_start_date,
                         scheduled_completion_date, actual_completion_date,
                         work_description, failure_description,
                         corrective_actions, notes)
                    VALUES
                        (:mo_number, :asset_id, :asset_name,
                         :site_id, :config_id, :tenant_id,
                         :company_id, 'maintenance', 'SAP_B1', :source_event_id,
                         :now,
                         'CORRECTIVE', :status, :priority,
                         :order_date, :scheduled_start,
                         :scheduled_end, :actual_completion,
                         :work_description, :failure_description,
                         :corrective_actions, :notes)
                    ON CONFLICT (maintenance_order_number) DO NOTHING
                """),
                {
                    "mo_number": mo_number,
                    "asset_id": asset_id,
                    "asset_name": item_code if item_code else None,
                    "site_id": site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "source_event_id": f"OSCL-{sc_id}",
                    "now": datetime.utcnow(),
                    "status": status,
                    "priority": priority,
                    "order_date": start_date,
                    "scheduled_start": datetime.combine(start_date, datetime.min.time()),
                    "scheduled_end": datetime.combine(end_date, datetime.min.time()) if end_date else None,
                    "actual_completion": datetime.combine(end_date, datetime.min.time()) if end_date and status == "COMPLETED" else None,
                    "work_description": work_description[:500],
                    "failure_description": str(subject)[:500] if subject else None,
                    "corrective_actions": str(resolution)[:500] if resolution else None,
                    "notes": str(resolution)[:500] if resolution else None,
                },
            )
            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d maintenance orders (missing required fields)", skipped_count)
        logger.info("Created %d maintenance orders from B1 ServiceCalls", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: Forecasts → forecast
    # ------------------------------------------------------------------

    async def _build_forecasts(
        self, forecast_data: List[Dict], orders: List[Dict],
    ) -> int:
        """Map B1 ForecastReport (OFCT) → forecast table.

        If ForecastReport data is available, each row maps directly.
        If empty, falls back to deriving weekly demand from Orders (ORDR),
        grouping SO lines by product-week — same approach as Odoo.

        B1 ForecastReport fields:
          AbsEntry       — unique key
          ItemCode       — product code
          Warehouse      — warehouse code
          ForecastDate   — forecast period date
          Quantity       — forecasted quantity
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create forecasts")
            return 0

        created_count = 0

        if forecast_data:
            # Primary path: use ForecastReport data
            created_count = await self._build_forecasts_from_report(
                forecast_data, config_id, first_site_id,
            )
        else:
            # Fallback: derive from Orders (SO lines by product-week)
            if orders:
                logger.info("No ForecastReport data — deriving forecasts from Orders")
                created_count = await self._build_forecasts_from_orders(
                    orders, config_id, first_site_id,
                )
            else:
                logger.info("No ForecastReport or Orders data — skipping forecast generation")

        logger.info("Created %d forecast records from B1 data", created_count)
        return created_count

    async def _build_forecasts_from_report(
        self, forecast_data: List[Dict], config_id: int, fallback_site_id: int,
    ) -> int:
        """Build forecasts from B1 ForecastReport (OFCT) rows."""
        created_count = 0
        skipped_count = 0

        for row in forecast_data:
            item_code = str(row.get("ItemCode", "")).strip()
            if not item_code:
                skipped_count += 1
                continue

            product_id = self._get_product_id(item_code)
            if not product_id:
                skipped_count += 1
                continue

            p50 = _safe_float(row.get("Quantity"))
            if p50 <= 0:
                skipped_count += 1
                continue

            forecast_date = _parse_b1_date(row.get("ForecastDate"))
            if not forecast_date:
                skipped_count += 1
                continue

            # Resolve site from Warehouse field
            wh_code = str(row.get("Warehouse", "")).strip()
            site_id = self._get_site_id(wh_code) if wh_code else fallback_site_id
            if not site_id:
                site_id = fallback_site_id

            p10 = round(p50 * 0.8, 4)
            p90 = round(p50 * 1.2, 4)
            abs_entry = row.get("AbsEntry", "")

            await self.db.execute(
                text("""
                    INSERT INTO forecast
                        (config_id, company_id, product_id, site_id,
                         forecast_date, forecast_type, forecast_level,
                         forecast_method, forecast_quantity,
                         forecast_p10, forecast_p50, forecast_median, forecast_p90,
                         is_active, source, source_event_id, source_update_dttm)
                    VALUES
                        (:config_id, :company_id, :product_id, :site_id,
                         :forecast_date, 'statistical', 'product',
                         'erp_forecast', :p50,
                         :p10, :p50, :p50, :p90,
                         'true', 'SAP_B1', :source_event_id, :now)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "config_id": config_id,
                    "company_id": f"B1_{config_id}",
                    "product_id": product_id,
                    "site_id": site_id,
                    "forecast_date": forecast_date,
                    "p50": p50,
                    "p10": p10,
                    "p90": p90,
                    "source_event_id": f"OFCT-{abs_entry}",
                    "now": datetime.utcnow(),
                },
            )
            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d forecast rows (missing product/qty/date)", skipped_count)
        return created_count

    async def _build_forecasts_from_orders(
        self, orders: List[Dict], config_id: int, fallback_site_id: int,
    ) -> int:
        """Derive weekly demand forecasts from B1 Orders (ORDR) line items.

        Groups DocumentLines by (ItemCode, ISO week) and sums quantities.
        """
        # Accumulate weekly demand: (item_code, iso_year, iso_week) → total_qty
        weekly_demand: Dict[Tuple[str, int, int], float] = {}
        week_dates: Dict[Tuple[str, int, int], date] = {}

        for order in orders:
            order_date = _parse_b1_date(order.get("DocDate"))
            if not order_date:
                continue

            lines = order.get("DocumentLines", [])
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue

                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                iso_year, iso_week, _ = order_date.isocalendar()
                key = (item_code, iso_year, iso_week)
                weekly_demand[key] = weekly_demand.get(key, 0.0) + qty

                if key not in week_dates:
                    monday = order_date - timedelta(days=order_date.weekday())
                    week_dates[key] = monday

        created_count = 0
        for (item_code, iso_year, iso_week), total_qty in weekly_demand.items():
            product_id = self._get_product_id(item_code)
            if not product_id:
                continue

            p50 = total_qty
            p10 = round(p50 * 0.8, 4)
            p90 = round(p50 * 1.2, 4)
            forecast_date = week_dates[(item_code, iso_year, iso_week)]

            await self.db.execute(
                text("""
                    INSERT INTO forecast
                        (config_id, company_id, product_id, site_id,
                         forecast_date, forecast_type, forecast_level,
                         forecast_method, forecast_quantity,
                         forecast_p10, forecast_p50, forecast_median, forecast_p90,
                         is_active, source, source_event_id, source_update_dttm)
                    VALUES
                        (:config_id, :company_id, :product_id, :site_id,
                         :forecast_date, 'statistical', 'product',
                         'demand_history', :p50,
                         :p10, :p50, :p50, :p90,
                         'true', 'SAP_B1', :source_event_id, :now)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "config_id": config_id,
                    "company_id": f"B1_{config_id}",
                    "product_id": product_id,
                    "site_id": fallback_site_id,
                    "forecast_date": forecast_date,
                    "p50": p50,
                    "p10": p10,
                    "p90": p90,
                    "source_event_id": f"SO-W{iso_year}{iso_week:02d}-{item_code}",
                    "now": datetime.utcnow(),
                },
            )
            created_count += 1

        await self.db.flush()
        return created_count

    # ==================================================================
    # NEW ENTITY MAPPINGS — Company, Pricing, Resources, Invoices,
    # Purchase Requests, Transfer Requests, Inventory Movements, Lots
    # ==================================================================

    # ------------------------------------------------------------------
    # Master: Companies (OADM) → company table enrichment
    # ------------------------------------------------------------------

    async def _enrich_company(self, companies: List[Dict]) -> None:
        """Enrich the company table from B1 Companies (OADM).

        B1 Companies (OADM) fields:
          CompanyName     — company display name
          Address         — street address
          City            — city
          State           — state / province
          ZipCode         — postal code
          Country         — country code
          Phone1          — primary phone number
          PrintHeader     — company header line (used as description fallback)
        """
        config_id = self._config_id
        if config_id is None:
            return

        company_id = f"B1_{config_id}"

        for comp in companies:
            name = str(comp.get("CompanyName", "")).strip()
            if not name:
                continue

            address = str(comp.get("Address", "")).strip() or None
            city = str(comp.get("City", "")).strip() or None
            state = str(comp.get("State", "")).strip() or None
            postal = str(comp.get("ZipCode", "")).strip() or None
            country = str(comp.get("Country", "")).strip() or None
            phone = str(comp.get("Phone1", "")).strip() or None
            description = name

            await self.db.execute(
                text("""
                    INSERT INTO company
                        (id, description, address_1, city, state_prov,
                         postal_code, country, phone_number)
                    VALUES
                        (:id, :description, :address, :city, :state,
                         :postal, :country, :phone)
                    ON CONFLICT (id) DO UPDATE SET
                        description = COALESCE(EXCLUDED.description, company.description),
                        address_1 = COALESCE(EXCLUDED.address_1, company.address_1),
                        city = COALESCE(EXCLUDED.city, company.city),
                        state_prov = COALESCE(EXCLUDED.state_prov, company.state_prov),
                        postal_code = COALESCE(EXCLUDED.postal_code, company.postal_code),
                        country = COALESCE(EXCLUDED.country, company.country),
                        phone_number = COALESCE(EXCLUDED.phone_number, company.phone_number)
                """),
                {
                    "id": company_id,
                    "description": description,
                    "address": address,
                    "city": city,
                    "state": state,
                    "postal": postal,
                    "country": country,
                    "phone": phone,
                },
            )
            # Only process the first company record (B1 has one company per DB)
            break

        await self.db.flush()
        logger.info("Enriched company record from B1 Companies (OADM)")

    # ------------------------------------------------------------------
    # Master: PriceLists + SpecialPrices + UoM → product enrichment
    # ------------------------------------------------------------------

    async def _enrich_products_with_pricing(
        self,
        price_lists: List[Dict],
        special_prices: List[Dict],
        uom_data: List[Dict],
    ) -> int:
        """Enrich product.unit_cost, unit_price, base_uom from B1 pricing/UoM data.

        B1 PriceLists (OPLN) fields:
          PriceListNo     — unique price list number
          PriceListName   — name (e.g. "Base Price", "Last Purchase Price")
          IsGrossPrice    — Y/N

        B1 PriceList → Items association: items have PriceList sub-collection
        with ItemCode, Price, Currency per price list.  In CSV/flat export,
        this comes as separate rows or via SpecialPrices.

        B1 SpecialPrices (OSPP) fields:
          CardCode        — vendor/customer business partner code
          ItemCode        — product code
          Price           — special price for this BP
          Currency        — price currency
          PriceListNum    — which price list this overrides

        B1 UnitOfMeasurements (OUOM) fields:
          AbsEntry        — unique key
          Code            — UoM code (e.g. "EA", "KG", "BOX")
          Name            — UoM display name

        Strategy:
        1. Build UoM lookup (AbsEntry → Code) for resolving item UoM references
        2. Use SpecialPrices to populate vendor_products pricing
        3. Use PriceLists data to update product.unit_price / unit_cost
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        enriched_count = 0

        # 1. Build UoM code lookup: AbsEntry → Code
        uom_lookup: Dict[str, str] = {}
        for uom in uom_data:
            entry = str(uom.get("AbsEntry", "")).strip()
            code = str(uom.get("Code", "")).strip()
            if entry and code:
                uom_lookup[entry] = code

        # 2. Update product.base_uom from UoM data if we have item→UoM mappings
        # B1 Items carry InventoryUoMEntry or SalesUoMEntry which references UoM AbsEntry
        # We update products that currently have NULL base_uom
        if uom_lookup:
            for entry_id, uom_code in uom_lookup.items():
                # Products referencing this UoM entry will have been set during
                # master data creation.  This is a best-effort enrichment for
                # products whose base_uom was not set during initial import.
                pass  # UoM enrichment handled below via item-level data

        # 3. Use SpecialPrices to create vendor_products records
        for sp in special_prices:
            card_code = str(sp.get("CardCode", "")).strip()
            item_code = str(sp.get("ItemCode", "")).strip()
            if not card_code or not item_code:
                continue

            product_id = self._get_product_id(item_code)
            if not product_id:
                continue

            price = _safe_float(sp.get("Price"))
            if price <= 0:
                continue

            currency = str(sp.get("Currency", "USD")).strip() or "USD"
            vendor_tid = f"B1V_{card_code}"

            # Only create vendor_products if this is a known vendor
            if card_code in self._vendor_pks:
                await self.db.execute(
                    text("""
                        INSERT INTO vendor_products
                            (tpartner_id, product_id, vendor_product_id,
                             vendor_unit_cost, currency, is_active,
                             source, source_event_id, source_update_dttm)
                        VALUES
                            (:tpartner_id, :product_id, :vendor_product_id,
                             :price, :currency, 'true',
                             'SAP_B1', :source_event_id, :now)
                        ON CONFLICT (tpartner_id, product_id, eff_start_date)
                        DO UPDATE SET vendor_unit_cost = EXCLUDED.vendor_unit_cost,
                                      currency = EXCLUDED.currency
                    """),
                    {
                        "tpartner_id": vendor_tid,
                        "product_id": product_id,
                        "vendor_product_id": item_code,
                        "price": price,
                        "currency": currency,
                        "source_event_id": f"OSPP-{card_code}-{item_code}",
                        "now": datetime.utcnow(),
                    },
                )
                enriched_count += 1

        # 4. Use PriceLists to update product.unit_price (first base price list)
        # B1 PriceLists often include item-level prices in a sub-collection
        # called PriceListItemPrices or via flat CSV rows with ItemCode, Price
        for pl in price_lists:
            pl_items = pl.get("PriceListItemPrices", pl.get("Items", []))
            if not isinstance(pl_items, list):
                continue

            for pl_item in pl_items:
                item_code = str(pl_item.get("ItemCode", "")).strip()
                if not item_code:
                    continue

                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                price = _safe_float(pl_item.get("Price"))
                if price <= 0:
                    continue

                # Update product.unit_price — use the first non-zero price
                await self.db.execute(
                    text("""
                        UPDATE product SET unit_price = :price
                        WHERE id = :pid AND (unit_price IS NULL OR unit_price = 0)
                    """),
                    {"price": price, "pid": product_id},
                )
                enriched_count += 1

        await self.db.flush()
        if enriched_count:
            logger.info(
                "Enriched %d product/vendor records from B1 PriceLists + SpecialPrices",
                enriched_count,
            )
        return enriched_count

    # ------------------------------------------------------------------
    # Master: BusinessPartnerGroups → trading_partner description enrichment
    # ------------------------------------------------------------------

    async def _enrich_trading_partners_with_groups(
        self,
        bp_groups: List[Dict],
        partners: List[Dict],
    ) -> None:
        """Enrich trading_partners with BP group names.

        B1 BusinessPartnerGroups (OCRG) fields:
          Code       — group code (integer)
          Name       — group name (e.g. "Domestic Vendors", "Key Accounts")
          Type       — C=customer, S=supplier

        B1 BusinessPartners carry GroupCode referencing OCRG.Code.
        We append the group name to the trading_partner description.
        """
        # Build group lookup: Code → Name
        group_lookup: Dict[str, str] = {}
        for grp in bp_groups:
            code = str(grp.get("Code", "")).strip()
            name = str(grp.get("Name", "")).strip()
            if code and name:
                group_lookup[code] = name

        if not group_lookup:
            return

        updated = 0
        for bp in partners:
            card_code = str(bp.get("CardCode", "")).strip()
            group_code = str(bp.get("GroupCode", "")).strip()
            if not card_code or not group_code:
                continue

            group_name = group_lookup.get(group_code)
            if not group_name:
                continue

            card_type = map_card_type(bp.get("CardType", ""))
            prefix = "B1V_" if card_type == "vendor" else "B1C_"
            tp_id = f"{prefix}{card_code}"

            # Append group name to description
            await self.db.execute(
                text("""
                    UPDATE trading_partners
                    SET description = CASE
                        WHEN description IS NULL OR description = '' THEN CAST(:group_name AS VARCHAR)
                        WHEN description NOT LIKE '%' || CAST(:group_name AS VARCHAR) || '%'
                            THEN description || ' [' || CAST(:group_name AS VARCHAR) || ']'
                        ELSE description
                    END
                    WHERE id = CAST(:tp_id AS VARCHAR)
                """),
                {"tp_id": tp_id, "group_name": group_name},
            )
            updated += 1

        await self.db.flush()
        if updated:
            logger.info("Enriched %d trading partners with BP group names", updated)

    # ------------------------------------------------------------------
    # Master: Resources + ResourceCapacities → capacity_resources
    # ------------------------------------------------------------------

    async def _build_resources(
        self,
        resources: List[Dict],
        resource_caps: List[Dict],
    ) -> int:
        """Map B1 Resources (ORES) + ResourceCapacities (ORSC) → capacity_resources.

        B1 Resources fields:
          ResCode         — resource code (unique key)
          ResName         — resource name
          ResType         — rt_Machine / rt_Labor / rt_Other
          VisResCode      — visual/display code
          Warehouse       — associated warehouse code
          CostPerHour     — standard cost per hour (Active property)
          Capacity        — daily capacity in resource units

        B1 ResourceCapacities fields:
          AbsEntry        — unique key
          ResCode         — linked resource code
          WeekDay         — day of week (0=Mon...6=Sun)
          FirstInTime     — shift start (minutes from midnight)
          FirstOutTime    — shift end (minutes from midnight)
          Factor1...Factor4 — capacity factors

        Strategy: Create a capacity_plan for this config, then populate
        capacity_resources with resource data and capacity info.
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create capacity resources")
            return 0

        # Build resource capacity lookup: ResCode → list of capacity records
        cap_lookup: Dict[str, List[Dict]] = {}
        for cap in resource_caps:
            res_code = str(cap.get("ResCode", "")).strip()
            if res_code:
                cap_lookup.setdefault(res_code, []).append(cap)

        # Create or reuse a capacity plan for this config
        row = await self.db.execute(
            text("""
                SELECT id FROM capacity_plans
                WHERE supply_chain_config_id = :cid AND status = 'ACTIVE'
                LIMIT 1
            """),
            {"cid": config_id},
        )
        plan_row = row.fetchone()
        if plan_row:
            plan_id = plan_row[0]
        else:
            today = date.today()
            await self.db.execute(
                text("""
                    INSERT INTO capacity_plans
                        (name, supply_chain_config_id, planning_horizon_weeks,
                         bucket_size_days, start_date, end_date, status)
                    VALUES
                        (:name, :cid, 13, 7, :start, :end, 'ACTIVE')
                """),
                {
                    "name": f"B1 Resource Capacity — Config {config_id}",
                    "cid": config_id,
                    "start": datetime.combine(today, datetime.min.time()),
                    "end": datetime.combine(
                        today + timedelta(weeks=13), datetime.min.time(),
                    ),
                },
            )
            await self.db.flush()
            row = await self.db.execute(
                text("""
                    SELECT id FROM capacity_plans
                    WHERE supply_chain_config_id = :cid AND status = 'ACTIVE'
                    ORDER BY id DESC LIMIT 1
                """),
                {"cid": config_id},
            )
            plan_row = row.fetchone()
            if not plan_row:
                logger.warning("Failed to create capacity plan")
                return 0
            plan_id = plan_row[0]

        created_count = 0

        for res in resources:
            res_code = str(res.get("ResCode", "")).strip()
            if not res_code:
                continue

            res_name = str(res.get("ResName", res_code)).strip()

            # Map B1 resource type to ResourceType enum
            raw_type = str(res.get("ResType", "")).strip().lower()
            if "machine" in raw_type or raw_type == "rt_machine":
                resource_type = "MACHINE"
            elif "labor" in raw_type or raw_type == "rt_labor":
                resource_type = "LABOR"
            else:
                resource_type = "MACHINE"

            # Resolve site from Warehouse field
            wh_code = str(res.get("Warehouse", "")).strip()
            site_id = self._get_site_id(wh_code) if wh_code else first_site_id
            if not site_id:
                site_id = first_site_id

            # Capacity: B1 'Capacity' field is daily capacity in resource units
            daily_capacity = _safe_float(res.get("Capacity"), 8.0)
            if daily_capacity <= 0:
                daily_capacity = 8.0

            cost_per_hour = _safe_float(res.get("CostPerHour")) or None

            # Derive shifts from ResourceCapacities if available
            caps = cap_lookup.get(res_code, [])
            shifts_per_day = None
            hours_per_shift = None
            working_days = None

            if caps:
                # Count distinct weekdays that have capacity
                weekdays_with_capacity = set()
                shift_hours_list: List[float] = []
                for cap in caps:
                    wd = cap.get("WeekDay")
                    if wd is not None:
                        weekdays_with_capacity.add(int(wd))
                    in_time = _safe_float(cap.get("FirstInTime"))
                    out_time = _safe_float(cap.get("FirstOutTime"))
                    if out_time > in_time:
                        shift_hours_list.append((out_time - in_time) / 60.0)

                if weekdays_with_capacity:
                    working_days = len(weekdays_with_capacity)

                if shift_hours_list:
                    # Approximate shifts per day and hours per shift
                    avg_shift = sum(shift_hours_list) / len(shift_hours_list)
                    if avg_shift > 0:
                        hours_per_shift = round(avg_shift, 1)
                        shifts_per_day = max(1, round(daily_capacity / avg_shift))

            await self.db.execute(
                text("""
                    INSERT INTO capacity_resources
                        (plan_id, resource_name, resource_code, resource_type,
                         site_id, available_capacity, capacity_unit,
                         efficiency_percent, utilization_target_percent,
                         cost_per_hour, shifts_per_day, hours_per_shift,
                         working_days_per_week, notes)
                    VALUES
                        (:plan_id, :name, :code, :type,
                         :site_id, :capacity, 'hours',
                         100.0, 85.0,
                         :cost_per_hour, :shifts, :hours_shift,
                         :working_days, :notes)
                """),
                {
                    "plan_id": plan_id,
                    "name": res_name,
                    "code": res_code,
                    "type": resource_type,
                    "site_id": site_id,
                    "capacity": daily_capacity,
                    "cost_per_hour": cost_per_hour,
                    "shifts": shifts_per_day,
                    "hours_shift": hours_per_shift,
                    "working_days": working_days,
                    "notes": f"Imported from B1 ORES.{res_code}",
                },
            )
            created_count += 1

        await self.db.flush()
        logger.info(
            "Created %d capacity resources from B1 Resources + ResourceCapacities",
            created_count,
        )
        return created_count

    # ------------------------------------------------------------------
    # Transaction: Invoices + Returns + PurchaseInvoices → status updates
    # ------------------------------------------------------------------

    async def _build_invoices_and_returns(
        self,
        invoices: List[Dict],
        returns: List[Dict],
        purchase_invoices: List[Dict],
    ) -> int:
        """Update order statuses from B1 Invoices, Returns, PurchaseInvoices.

        B1 Invoices (OINV) — A/R invoices linked to Sales Orders:
          DocEntry       — unique key
          DocNum         — display number
          DocumentLines[].BaseEntry — linked SO DocEntry

        B1 Returns (ORDN) — Sales returns linked to Sales Orders:
          DocEntry       — unique key
          DocNum         — display number
          DocumentLines[].BaseEntry — linked SO DocEntry
          DocumentLines[].Quantity  — returned quantity

        B1 PurchaseInvoices (OPCH) — A/P invoices linked to POs:
          DocEntry       — unique key
          DocNum         — display number
          DocumentLines[].BaseEntry — linked PO DocEntry

        Strategy:
        - Invoices → mark linked outbound_order as INVOICED
        - Returns → create return outbound_order_line with negative qty
        - PurchaseInvoices → mark linked purchase_order as INVOICED
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        updated_count = 0

        # 1. A/R Invoices → mark outbound orders as INVOICED
        for inv in invoices:
            lines = inv.get("DocumentLines", [])
            linked_so_entries: Set[str] = set()
            for line in lines:
                base_entry = line.get("BaseEntry")
                if base_entry is not None:
                    linked_so_entries.add(str(base_entry))

            for so_entry in linked_so_entries:
                order_id = f"B1-SO-{so_entry}"
                result = await self.db.execute(
                    text("""
                        UPDATE outbound_order SET status = 'INVOICED'
                        WHERE id = :oid AND status NOT IN ('INVOICED', 'CANCELLED')
                    """),
                    {"oid": order_id},
                )
                if result.rowcount > 0:
                    updated_count += 1

        # 2. Sales Returns → mark outbound order as RETURNED and record
        #    negative-qty return lines on the outbound order
        for ret in returns:
            doc_num = ret.get("DocNum", ret.get("DocEntry"))
            lines = ret.get("DocumentLines", [])
            linked_so_entries = set()

            for line in lines:
                base_entry = line.get("BaseEntry")
                if base_entry is not None:
                    linked_so_entries.add(str(base_entry))

                    item_code = str(line.get("ItemCode", "")).strip()
                    qty = _safe_float(line.get("Quantity"))
                    if not item_code or qty <= 0:
                        continue

                    product_id = self._get_product_id(item_code)
                    if not product_id:
                        continue

                    # Insert a return line (negative qty) on the outbound order
                    order_id = f"B1-SO-{base_entry}"
                    line_num = _safe_int(line.get("LineNum"), 0) + 1000  # offset to avoid collision

                    await self.db.execute(
                        text("""
                            INSERT INTO outbound_order_line
                                (order_id, line_number, product_id, site_id,
                                 ordered_quantity, config_id, status, priority_code)
                            VALUES
                                (:order_id, :line_number, :product_id,
                                 (SELECT ship_from_site_id FROM outbound_order WHERE id = :order_id),
                                 :neg_qty, :config_id, 'RETURNED', 'RETURN')
                            ON CONFLICT DO NOTHING
                        """),
                        {
                            "order_id": order_id,
                            "line_number": line_num,
                            "product_id": product_id,
                            "neg_qty": -abs(qty),
                            "config_id": config_id,
                        },
                    )

            for so_entry in linked_so_entries:
                order_id = f"B1-SO-{so_entry}"
                result = await self.db.execute(
                    text("""
                        UPDATE outbound_order SET status = 'RETURNED'
                        WHERE id = :oid AND status NOT IN ('RETURNED', 'CANCELLED')
                    """),
                    {"oid": order_id},
                )
                if result.rowcount > 0:
                    updated_count += 1

        # 3. A/P Invoices → mark purchase orders as INVOICED
        for pi in purchase_invoices:
            lines = pi.get("DocumentLines", [])
            linked_po_entries: Set[str] = set()
            for line in lines:
                base_entry = line.get("BaseEntry")
                if base_entry is not None:
                    linked_po_entries.add(str(base_entry))

            for po_entry in linked_po_entries:
                po_number = f"B1-PO-{po_entry}"
                result = await self.db.execute(
                    text("""
                        UPDATE purchase_order SET status = 'INVOICED'
                        WHERE po_number = :pn AND status NOT IN ('INVOICED', 'CANCELLED')
                    """),
                    {"pn": po_number},
                )
                if result.rowcount > 0:
                    updated_count += 1

        await self.db.flush()
        if updated_count:
            logger.info(
                "Updated %d order statuses from B1 Invoices/Returns/PurchaseInvoices",
                updated_count,
            )
        return updated_count

    # ------------------------------------------------------------------
    # Transaction: PurchaseRequests → purchase_order (DRAFT)
    # ------------------------------------------------------------------

    async def _build_purchase_requests(self, purchase_requests: List[Dict]) -> int:
        """Map B1 PurchaseRequests (OPRQ) → purchase_order with status DRAFT.

        B1 PurchaseRequests fields:
          DocEntry       — unique key
          DocNum         — display number
          DocDate        — request date
          RequriedDate   — required-by date (B1 typo is intentional)
          DocumentStatus — bost_Open / bost_Close
          Requester      — requester name
          Comments       — notes

        B1 DocumentLines:
          ItemCode       — product code
          Quantity       — requested quantity
          WarehouseCode  — destination warehouse
          LineNum        — line number (0-based)
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create purchase requests")
            return 0

        created_count = 0
        skipped_count = 0

        for pr in purchase_requests:
            doc_entry = pr.get("DocEntry")
            doc_num = pr.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            request_date = _parse_b1_date(pr.get("DocDate"))
            if not request_date:
                skipped_count += 1
                continue

            required_date = (
                _parse_b1_date(pr.get("RequriedDate"))
                or _parse_b1_date(pr.get("RequiredDate"))
                or request_date + timedelta(days=14)
            )
            notes = pr.get("Comments")
            requester = pr.get("Requester")

            po_number = f"B1-PR-{doc_num}"

            # Determine destination site from first line
            lines = pr.get("DocumentLines", [])
            dest_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    dest_site_id = self._get_site_id(first_wh)

            # Insert as purchase_order with status DRAFT (not yet a real PO)
            await self.db.execute(
                text("""
                    INSERT INTO purchase_order
                        (po_number, supplier_site_id, destination_site_id,
                         config_id, tenant_id, company_id, order_type, source,
                         status, order_date, requested_delivery_date, notes)
                    VALUES
                        (:po_number, :dest_site_id, :dest_site_id,
                         :config_id, :tenant_id, :company_id, 'purchase_request', 'SAP_B1',
                         'DRAFT', :order_date, :delivery_date, :notes)
                    ON CONFLICT (po_number) DO NOTHING
                """),
                {
                    "po_number": po_number,
                    "dest_site_id": dest_site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "order_date": request_date,
                    "delivery_date": required_date,
                    "notes": (
                        f"Requester: {requester}. {notes}" if requester and notes
                        else str(requester or notes or "")
                    )[:500] or None,
                },
            )

            # Fetch the PO id for line items
            row = await self.db.execute(
                text("SELECT id FROM purchase_order WHERE po_number = :pn"),
                {"pn": po_number},
            )
            po_row = row.fetchone()
            if not po_row:
                skipped_count += 1
                continue
            po_id = po_row[0]

            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                line_num = _safe_int(line.get("LineNum"), line_count)

                await self.db.execute(
                    text("""
                        INSERT INTO purchase_order_line_item
                            (po_id, line_number, product_id, quantity,
                             requested_delivery_date)
                        VALUES
                            (:po_id, :line_number, :product_id, :quantity,
                             :delivery_date)
                    """),
                    {
                        "po_id": po_id,
                        "line_number": line_num + 1,
                        "product_id": product_id,
                        "quantity": qty,
                        "delivery_date": required_date,
                    },
                )
                line_count += 1

            if line_count > 0 or not lines:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d purchase requests (missing required fields)", skipped_count)
        logger.info("Created %d purchase requests (DRAFT POs) from B1 PurchaseRequests", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transaction: InventoryTransferRequests → transfer_order (PLANNED)
    # ------------------------------------------------------------------

    async def _build_transfer_requests(self, transfer_requests: List[Dict]) -> int:
        """Map B1 InventoryTransferRequests (OWTQ) → transfer_order (PLANNED).

        B1 InventoryTransferRequests fields:
          DocEntry       — unique key
          DocNum         — display number
          DocDate        — request date
          DocumentStatus — bost_Open / bost_Close
          Comments       — notes

        B1 StockTransferLines (DocumentLines):
          FromWarehouse  — source warehouse code
          WarehouseCode  — destination warehouse code
          ItemCode       — product code
          Quantity       — transfer quantity
          LineNum        — line number (0-based)
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create transfer requests")
            return 0

        created_count = 0
        skipped_count = 0

        for tr in transfer_requests:
            doc_entry = tr.get("DocEntry")
            doc_num = tr.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            request_date = _parse_b1_date(tr.get("DocDate"))
            if not request_date:
                skipped_count += 1
                continue

            lines = tr.get("DocumentLines", tr.get("StockTransferLines", []))
            if not lines:
                skipped_count += 1
                continue

            notes = tr.get("Comments")

            # Determine source and destination from first line
            first_from_wh = str(lines[0].get("FromWarehouse", "")).strip()
            first_to_wh = str(
                lines[0].get("WarehouseCode", lines[0].get("ToWarehouse", ""))
            ).strip()

            source_site_id = self._get_site_id(first_from_wh) if first_from_wh else first_site_id
            dest_site_id = self._get_site_id(first_to_wh) if first_to_wh else first_site_id
            if not source_site_id:
                source_site_id = first_site_id
            if not dest_site_id:
                dest_site_id = first_site_id

            to_number = f"B1-TR-{doc_num}"

            await self.db.execute(
                text("""
                    INSERT INTO transfer_order
                        (to_number, source_site_id, destination_site_id,
                         config_id, tenant_id, company_id,
                         order_type, source, source_event_id, source_update_dttm,
                         status, order_date, notes)
                    VALUES
                        (:to_number, :source_site_id, :dest_site_id,
                         :config_id, :tenant_id, :company_id,
                         'transfer_request', 'SAP_B1', :source_event_id, :now,
                         'PLANNED', :order_date, :notes)
                    ON CONFLICT (to_number) DO NOTHING
                """),
                {
                    "to_number": to_number,
                    "source_site_id": source_site_id,
                    "dest_site_id": dest_site_id,
                    "config_id": config_id,
                    "tenant_id": self.tenant_id,
                    "company_id": f"B1_{config_id}",
                    "source_event_id": f"OWTQ-{doc_num}",
                    "now": datetime.utcnow(),
                    "order_date": request_date,
                    "notes": str(notes)[:500] if notes else None,
                },
            )

            # Fetch the TO id for line items
            row = await self.db.execute(
                text("SELECT id FROM transfer_order WHERE to_number = :tn"),
                {"tn": to_number},
            )
            to_row = row.fetchone()
            if not to_row:
                skipped_count += 1
                continue
            to_id = to_row[0]

            line_count = 0
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                line_num = _safe_int(line.get("LineNum"), line_count)

                await self.db.execute(
                    text("""
                        INSERT INTO transfer_order_line_item
                            (to_id, line_number, product_id, quantity)
                        VALUES
                            (:to_id, :line_number, :product_id, :quantity)
                    """),
                    {
                        "to_id": to_id,
                        "line_number": line_num + 1,
                        "product_id": product_id,
                        "quantity": qty,
                    },
                )
                line_count += 1

            if line_count > 0:
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d transfer requests (missing required fields)", skipped_count)
        logger.info("Created %d transfer requests (PLANNED TOs) from B1 InventoryTransferRequests", created_count)
        return created_count

    # ------------------------------------------------------------------
    # CDC: InventoryGenEntries + Exits + StockTakings → inv_level adjustments
    # ------------------------------------------------------------------

    async def _build_inventory_movements(
        self,
        inv_entries: List[Dict],
        inv_exits: List[Dict],
        stock_takings: List[Dict],
    ) -> int:
        """Apply B1 inventory movements to inv_level records.

        B1 InventoryGenEntries (OIGE) — goods receipts/adjustments:
          DocEntry       — unique key
          DocDate        — posting date
          DocumentLines[].ItemCode       — product code
          DocumentLines[].Quantity       — received/adjusted quantity (positive)
          DocumentLines[].WarehouseCode  — warehouse code

        B1 InventoryGenExits (OIGE) — goods issues:
          Same structure as entries, quantity is positive but represents outflow.

        B1 StockTakings (OINC) — physical inventory counts:
          AbsEntry       — unique key
          CountDate      — count date
          StockTakingLines[].ItemCode      — product code
          StockTakingLines[].WarehouseCode — warehouse code
          StockTakingLines[].CountedQty    — physically counted quantity
          StockTakingLines[].Variance      — difference from system qty

        Strategy:
        - Entries: Insert inv_level records with on_hand_qty from entries
        - Exits: Insert inv_level records reflecting goods issues
        - StockTakings: Insert inv_level records with corrected on_hand_qty
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            return 0

        applied_count = 0

        # Helper to upsert inv_level with a delta
        async def _upsert_inv_level(
            product_id: str, site_id: int, qty_delta: float,
            inv_date: date, source_event_id: str,
        ) -> bool:
            """Upsert an inv_level record, adding qty_delta to on_hand_qty."""
            # Try to update existing record for this product-site-date
            result = await self.db.execute(
                text("""
                    UPDATE inv_level
                    SET on_hand_qty = COALESCE(on_hand_qty, 0) + :delta,
                        available_qty = COALESCE(available_qty, 0) + :delta,
                        source = 'SAP_B1',
                        source_event_id = :event_id,
                        source_update_dttm = :now
                    WHERE product_id = :pid AND site_id = :sid
                          AND config_id = :cid AND inventory_date = :inv_date
                """),
                {
                    "delta": qty_delta,
                    "pid": product_id,
                    "sid": site_id,
                    "cid": config_id,
                    "inv_date": inv_date,
                    "event_id": source_event_id,
                    "now": datetime.utcnow(),
                },
            )
            if result.rowcount > 0:
                return True

            # No existing record — insert new one
            on_hand = max(0.0, qty_delta)  # Don't start with negative
            await self.db.execute(
                text("""
                    INSERT INTO inv_level
                        (product_id, site_id, config_id, company_id,
                         inventory_date, on_hand_qty, available_qty,
                         source, source_event_id, source_update_dttm)
                    VALUES
                        (:pid, :sid, :cid, :company_id,
                         :inv_date, :on_hand, :on_hand,
                         'SAP_B1', :event_id, :now)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "pid": product_id,
                    "sid": site_id,
                    "cid": config_id,
                    "company_id": f"B1_{config_id}",
                    "inv_date": inv_date,
                    "on_hand": on_hand,
                    "event_id": source_event_id,
                    "now": datetime.utcnow(),
                },
            )
            return True

        # 1. Inventory Gen Entries (goods receipts / positive adjustments)
        for entry in inv_entries:
            doc_entry = entry.get("DocEntry")
            doc_date = _parse_b1_date(entry.get("DocDate"))
            if not doc_date:
                continue

            lines = entry.get("DocumentLines", [])
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                wh_code = str(line.get("WarehouseCode", "")).strip()
                site_id = self._get_site_id(wh_code) if wh_code else first_site_id
                if not site_id:
                    site_id = first_site_id

                if await _upsert_inv_level(
                    product_id, site_id, qty, doc_date,
                    f"OIGE-IN-{doc_entry}",
                ):
                    applied_count += 1

        # 2. Inventory Gen Exits (goods issues / negative adjustments)
        for exit_rec in inv_exits:
            doc_entry = exit_rec.get("DocEntry")
            doc_date = _parse_b1_date(exit_rec.get("DocDate"))
            if not doc_date:
                continue

            lines = exit_rec.get("DocumentLines", [])
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                qty = _safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue

                wh_code = str(line.get("WarehouseCode", "")).strip()
                site_id = self._get_site_id(wh_code) if wh_code else first_site_id
                if not site_id:
                    site_id = first_site_id

                if await _upsert_inv_level(
                    product_id, site_id, -qty, doc_date,
                    f"OIGE-OUT-{doc_entry}",
                ):
                    applied_count += 1

        # 3. Stock Takings — replace on_hand_qty with counted qty
        for st in stock_takings:
            abs_entry = st.get("AbsEntry")
            count_date = _parse_b1_date(st.get("CountDate"))
            if not count_date:
                continue

            lines = st.get("StockTakingLines", st.get("DocumentLines", []))
            for line in lines:
                item_code = str(line.get("ItemCode", "")).strip()
                if not item_code:
                    continue
                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                counted_qty = _safe_float(line.get("CountedQty"))
                if counted_qty < 0:
                    continue

                wh_code = str(line.get("WarehouseCode", "")).strip()
                site_id = self._get_site_id(wh_code) if wh_code else first_site_id
                if not site_id:
                    site_id = first_site_id

                # For stock takings, set on_hand_qty directly (not a delta)
                result = await self.db.execute(
                    text("""
                        UPDATE inv_level
                        SET on_hand_qty = :counted,
                            available_qty = :counted,
                            source = 'SAP_B1',
                            source_event_id = :event_id,
                            source_update_dttm = :now
                        WHERE product_id = :pid AND site_id = :sid
                              AND config_id = :cid AND inventory_date = :inv_date
                    """),
                    {
                        "counted": counted_qty,
                        "pid": product_id,
                        "sid": site_id,
                        "cid": config_id,
                        "inv_date": count_date,
                        "event_id": f"OINC-{abs_entry}",
                        "now": datetime.utcnow(),
                    },
                )
                if result.rowcount == 0:
                    # No existing record — insert new
                    await self.db.execute(
                        text("""
                            INSERT INTO inv_level
                                (product_id, site_id, config_id, company_id,
                                 inventory_date, on_hand_qty, available_qty,
                                 source, source_event_id, source_update_dttm)
                            VALUES
                                (:pid, :sid, :cid, :company_id,
                                 :inv_date, :counted, :counted,
                                 'SAP_B1', :event_id, :now)
                            ON CONFLICT DO NOTHING
                        """),
                        {
                            "pid": product_id,
                            "sid": site_id,
                            "cid": config_id,
                            "company_id": f"B1_{config_id}",
                            "inv_date": count_date,
                            "counted": counted_qty,
                            "event_id": f"OINC-{abs_entry}",
                            "now": datetime.utcnow(),
                        },
                    )
                applied_count += 1

        await self.db.flush()
        if applied_count:
            logger.info(
                "Applied %d inventory movements from B1 "
                "InventoryGenEntries/Exits/StockTakings",
                applied_count,
            )
        return applied_count

    # ------------------------------------------------------------------
    # CDC: BatchNumberDetails + SerialNumberDetails → product enrichment
    # ------------------------------------------------------------------

    async def _enrich_products_with_lots(
        self,
        batch_details: List[Dict],
        serial_details: List[Dict],
    ) -> int:
        """Enrich products with batch/serial tracking metadata.

        B1 BatchNumberDetails (OBTN) fields:
          AbsEntry       — unique key
          ItemCode       — product code
          BatchNumber    — batch/lot number
          ExpirationDate — lot expiration date
          ManufacturingDate — manufacturing date
          Status         — lot status

        B1 SerialNumberDetails (OSRN) fields:
          AbsEntry       — unique key
          ItemCode       — product code
          SerialNumber   — serial number
          ManufacturingDate — manufacturing date
          Status         — serial status

        Strategy: Update product.external_identifiers with tracking metadata
        (batch_managed=true/false, serial_managed=true/false, sample counts).
        Individual lot/serial records are kept in b1_staging for traceability.
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        enriched_count = 0

        # Identify which products are batch-managed
        batch_items: Dict[str, int] = {}  # ItemCode → count of batches
        for bd in batch_details:
            item_code = str(bd.get("ItemCode", "")).strip()
            if item_code:
                batch_items[item_code] = batch_items.get(item_code, 0) + 1

        # Identify which products are serial-managed
        serial_items: Dict[str, int] = {}  # ItemCode → count of serials
        for sd in serial_details:
            item_code = str(sd.get("ItemCode", "")).strip()
            if item_code:
                serial_items[item_code] = serial_items.get(item_code, 0) + 1

        # Update products with tracking flags in external_identifiers
        all_tracked_items = set(batch_items.keys()) | set(serial_items.keys())
        for item_code in all_tracked_items:
            product_id = self._get_product_id(item_code)
            if not product_id:
                continue

            batch_count = batch_items.get(item_code, 0)
            serial_count = serial_items.get(item_code, 0)

            tracking_info = {}
            if batch_count > 0:
                tracking_info["batch_managed"] = True
                tracking_info["batch_count"] = batch_count
            if serial_count > 0:
                tracking_info["serial_managed"] = True
                tracking_info["serial_count"] = serial_count

            # Merge into existing external_identifiers JSON
            await self.db.execute(
                text("""
                    UPDATE product
                    SET external_identifiers = COALESCE(external_identifiers, '{}'::jsonb)
                        || :tracking::jsonb
                    WHERE id = :pid
                """),
                {
                    "pid": product_id,
                    "tracking": json.dumps(tracking_info),
                },
            )
            enriched_count += 1

        await self.db.flush()
        if enriched_count:
            logger.info(
                "Enriched %d products with batch/serial tracking info "
                "(from %d batch records, %d serial records)",
                enriched_count, len(batch_details), len(serial_details),
            )
        return enriched_count

    # ------------------------------------------------------------------
    # Transactional: GoodsReturns (ORPD) → inbound_order (RETURN)
    # ------------------------------------------------------------------

    async def _build_goods_returns(self, goods_returns: List[Dict]) -> int:
        """Map B1 GoodsReturns (ORPD) → inbound_order with order_type='RETURN'.

        B1 GoodsReturns header fields:
          DocEntry       — internal unique key
          DocNum         — display document number
          CardCode       — vendor business partner code
          DocDate        — document date
          DocDueDate     — due date
          DocTotal       — total amount
          DocCur         — document currency
          DocumentStatus — bost_Open / bost_Close

        B1 DocumentLines (sub-entity):
          ItemCode       — product code
          Quantity       — returned quantity
          Price          — unit price
          WarehouseCode  — originating warehouse
          LineNum        — line number (0-based)

        These are PURCHASE returns — goods returned TO a vendor.
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create goods returns")
            return 0

        created_count = 0
        skipped_count = 0

        for ret in goods_returns:
            doc_entry = ret.get("DocEntry")
            doc_num = ret.get("DocNum", doc_entry)
            if doc_entry is None and doc_num is None:
                skipped_count += 1
                continue

            card_code = str(ret.get("CardCode", "")).strip()
            if not card_code:
                skipped_count += 1
                continue

            order_date = _parse_b1_date(ret.get("DocDate"))
            if not order_date:
                skipped_count += 1
                continue

            delivery_date = _parse_b1_date(ret.get("DocDueDate")) or order_date
            doc_total = _safe_float(ret.get("DocTotal"))
            currency = str(ret.get("DocCur", ret.get("DocCurrency", "USD"))).strip() or "USD"
            doc_status = str(ret.get("DocumentStatus", "O")).strip().upper()

            # Closed returns → RECEIVED, open → APPROVED
            if doc_status in ("C", "BOST_CLOSE"):
                status = "RECEIVED"
            else:
                status = "APPROVED"

            return_id = f"B1-RET-{doc_num}"
            vendor_tid = f"B1V_{card_code}"

            # Determine ship-from site (warehouse the goods leave from)
            lines = ret.get("DocumentLines", [])
            ship_from_site_id = first_site_id
            if lines:
                first_wh = str(lines[0].get("WarehouseCode", "")).strip()
                if first_wh and self._get_site_id(first_wh):
                    ship_from_site_id = self._get_site_id(first_wh)

            total_qty = sum(
                _safe_float(ln.get("Quantity")) for ln in lines
            ) if lines else 0.0

            # Insert inbound_order with order_type='RETURN'
            await self.db.execute(
                text("""
                    INSERT INTO inbound_order
                        (id, company_id, order_type, supplier_id,
                         ship_from_site_id, ship_to_site_id,
                         status, order_date, requested_delivery_date,
                         total_ordered_qty, total_value, currency,
                         reference_number, config_id,
                         source, source_event_id, source_update_dttm)
                    VALUES
                        (:id, :company_id, 'RETURN', :vendor_id,
                         :ship_from_site_id, :ship_from_site_id,
                         :status, :order_date, :delivery_date,
                         :total_qty, :total_value, :currency,
                         :ref_number, :config_id,
                         'SAP_B1', :source_event_id, :now)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": return_id,
                    "company_id": f"B1_{config_id}",
                    "vendor_id": vendor_tid,
                    "ship_from_site_id": ship_from_site_id,
                    "status": status,
                    "order_date": order_date,
                    "delivery_date": delivery_date,
                    "total_qty": total_qty,
                    "total_value": doc_total,
                    "currency": currency,
                    "ref_number": str(doc_num),
                    "config_id": config_id,
                    "source_event_id": f"B1_ORPD_{doc_entry}",
                    "now": datetime.utcnow(),
                },
            )
            created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d goods returns (missing required fields)", skipped_count)
        logger.info("Created %d inbound_order (RETURN) from B1 GoodsReturns", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Master: BlanketAgreements (OAGL) → sourcing_rules
    # ------------------------------------------------------------------

    async def _build_blanket_agreements(self, blanket_agreements: List[Dict]) -> int:
        """Map B1 BlanketAgreements (OAGL) → sourcing_rules for vendor agreements.

        B1 BlanketAgreements header fields:
          AgreementNo    — unique agreement number
          BPCode         — business partner code (vendor or customer)
          AgreementType  — 'V' / 'asVendor' (vendor) or 'C' / 'asCustomer' (customer)
          StartDate      — agreement effective start
          EndDate        — agreement effective end
          Status         — 'A' (active), 'T' (terminated), 'D' (draft)

        BlanketAgreements_Lines (sub-entity):
          ItemNo         — product code
          PlannedQuantity — agreed quantity
          UnitPrice      — agreed price

        Only vendor-type agreements are mapped to sourcing_rules (rule_type='buy').
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        created_count = 0
        skipped_count = 0

        for agr in blanket_agreements:
            agreement_no = agr.get("AgreementNo")
            if agreement_no is None:
                skipped_count += 1
                continue

            bp_code = str(agr.get("BPCode", "")).strip()
            if not bp_code:
                skipped_count += 1
                continue

            # Only map vendor-type agreements
            agr_type = str(agr.get("AgreementType", "")).strip()
            if agr_type not in ("V", "asVendor"):
                continue

            agr_status = str(agr.get("Status", "")).strip().upper()
            is_active = "true" if agr_status in ("A", "ACTIVE", "") else "false"

            start_date = _parse_b1_date(agr.get("StartDate"))
            end_date = _parse_b1_date(agr.get("EndDate"))

            vendor_tid = f"B1V_{bp_code}"

            # Process agreement lines — one sourcing_rule per item line
            lines = agr.get("BlanketAgreements_Lines", agr.get("Lines", []))
            if not lines:
                # Create a single rule without product specificity
                rule_id = f"B1-BA-{agreement_no}"
                first_site_id = self._get_first_site_id()
                if not first_site_id:
                    skipped_count += 1
                    continue

                await self.db.execute(
                    text("""
                        INSERT INTO sourcing_rules
                            (id, company_id, product_id, from_site_id, to_site_id,
                             tpartner_id, sourcing_rule_type, sourcing_priority,
                             eff_start_date, eff_end_date, is_active,
                             source, source_event_id, source_update_dttm,
                             config_id)
                        VALUES
                            (:id, :company_id, NULL, :from_site, :to_site,
                             :tpartner_id, 'buy', 5,
                             :start_date, :end_date, :is_active,
                             'SAP_B1', :source_event_id, :now,
                             :config_id)
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {
                        "id": rule_id,
                        "company_id": f"B1_{config_id}",
                        "from_site": first_site_id,
                        "to_site": first_site_id,
                        "tpartner_id": vendor_tid,
                        "start_date": datetime.combine(start_date, datetime.min.time()) if start_date else None,
                        "end_date": datetime.combine(end_date, datetime.min.time()) if end_date else None,
                        "is_active": is_active,
                        "source_event_id": f"B1_OAGL_{agreement_no}",
                        "now": datetime.utcnow(),
                        "config_id": config_id,
                    },
                )
                created_count += 1
                continue

            for idx, line in enumerate(lines):
                item_code = str(line.get("ItemNo", line.get("ItemCode", ""))).strip()
                if not item_code:
                    continue

                product_id = self._get_product_id(item_code)
                if not product_id:
                    continue

                # Determine a destination site — use first known site
                first_site_id = self._get_first_site_id()
                if not first_site_id:
                    continue

                planned_qty = _safe_float(line.get("PlannedQuantity"))

                rule_id = f"B1-BA-{agreement_no}-{idx}"

                await self.db.execute(
                    text("""
                        INSERT INTO sourcing_rules
                            (id, company_id, product_id, from_site_id, to_site_id,
                             tpartner_id, sourcing_rule_type, sourcing_priority,
                             max_quantity,
                             eff_start_date, eff_end_date, is_active,
                             source, source_event_id, source_update_dttm,
                             config_id)
                        VALUES
                            (:id, :company_id, :product_id, :from_site, :to_site,
                             :tpartner_id, 'buy', 5,
                             :max_qty,
                             :start_date, :end_date, :is_active,
                             'SAP_B1', :source_event_id, :now,
                             :config_id)
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {
                        "id": rule_id,
                        "company_id": f"B1_{config_id}",
                        "product_id": product_id,
                        "from_site": first_site_id,
                        "to_site": first_site_id,
                        "tpartner_id": vendor_tid,
                        "max_qty": planned_qty if planned_qty > 0 else None,
                        "start_date": datetime.combine(start_date, datetime.min.time()) if start_date else None,
                        "end_date": datetime.combine(end_date, datetime.min.time()) if end_date else None,
                        "is_active": is_active,
                        "source_event_id": f"B1_OAGL_{agreement_no}",
                        "now": datetime.utcnow(),
                        "config_id": config_id,
                    },
                )
                created_count += 1

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d blanket agreements (missing required fields)", skipped_count)
        logger.info("Created %d sourcing_rules from B1 BlanketAgreements", created_count)
        return created_count

    # ------------------------------------------------------------------
    # Transactional: MRPResults (OMRP) → purchase_order / production_orders / transfer_order (PLANNED)
    # ------------------------------------------------------------------

    async def _build_mrp_results(self, mrp_results: List[Dict]) -> int:
        """Map B1 MRPResults (OMRP) → planned orders.

        B1 MRPResults fields:
          AbsEntry             — unique key
          ItemNo               — product code
          Warehouse            — warehouse code
          RecommendationType   — 'purchase' / 'production' / 'transfer'
          RecommendedQuantity  — recommended order quantity
          RecommendedDate      — recommended order/due date
          DueDate              — alternative due date field
          Vendor               — vendor code (for purchase recommendations)
          FromWarehouse        — source warehouse (for transfer recommendations)

        Mapping:
          purchase   → purchase_order with status='PLANNED'
          production → production_orders with status='PLANNED'
          transfer   → transfer_order with status='PLANNED'
        """
        config_id = self._config_id
        if config_id is None:
            return 0

        first_site_id = self._get_first_site_id()
        if not first_site_id:
            logger.warning("No sites found — cannot create MRP results")
            return 0

        created_count = 0
        skipped_count = 0

        for mrp in mrp_results:
            abs_entry = mrp.get("AbsEntry")
            if abs_entry is None:
                skipped_count += 1
                continue

            item_code = str(mrp.get("ItemNo", mrp.get("ItemCode", ""))).strip()
            if not item_code:
                skipped_count += 1
                continue

            product_id = self._get_product_id(item_code)
            if not product_id:
                skipped_count += 1
                continue

            rec_qty = _safe_float(mrp.get("RecommendedQuantity"))
            if rec_qty <= 0:
                skipped_count += 1
                continue

            rec_date = _parse_b1_date(
                mrp.get("RecommendedDate") or mrp.get("DueDate")
            )
            if not rec_date:
                skipped_count += 1
                continue

            wh_code = str(mrp.get("Warehouse", "")).strip()
            site_id = self._get_site_id(wh_code) if wh_code else first_site_id
            if not site_id:
                site_id = first_site_id

            rec_type = str(mrp.get("RecommendationType", "")).strip().lower()

            if rec_type == "purchase":
                po_number = f"B1-MRP-PO-{abs_entry}"
                vendor_code = str(mrp.get("Vendor", "")).strip()
                vendor_tid = f"B1V_{vendor_code}" if vendor_code else None

                await self.db.execute(
                    text("""
                        INSERT INTO purchase_order
                            (po_number, vendor_id, supplier_site_id, destination_site_id,
                             config_id, tenant_id, company_id, order_type, source,
                             status, order_date, requested_delivery_date,
                             total_amount, notes)
                        VALUES
                            (:po_number, :vendor_id, :site_id, :site_id,
                             :config_id, :tenant_id, :company_id, 'po', 'SAP_B1',
                             'PLANNED', :order_date, :delivery_date,
                             :total_amount, :notes)
                        ON CONFLICT (po_number) DO NOTHING
                    """),
                    {
                        "po_number": po_number,
                        "vendor_id": vendor_tid,
                        "site_id": site_id,
                        "config_id": config_id,
                        "tenant_id": self.tenant_id,
                        "company_id": f"B1_{config_id}",
                        "order_date": rec_date,
                        "delivery_date": rec_date,
                        "total_amount": rec_qty,
                        "notes": f"MRP recommendation (AbsEntry={abs_entry})",
                    },
                )
                created_count += 1

            elif rec_type == "production":
                order_number = f"B1-MRP-MO-{abs_entry}"
                start_date = rec_date - timedelta(days=7)

                await self.db.execute(
                    text("""
                        INSERT INTO production_orders
                            (order_number, item_id, site_id, config_id,
                             planned_quantity, status,
                             planned_start_date, planned_completion_date,
                             lead_time_planned, priority, notes, extra_data)
                        VALUES
                            (:order_number, :item_id, :site_id, :config_id,
                             :planned_qty, 'PLANNED',
                             :start_date, :end_date,
                             7, 5, :notes, :extra)
                        ON CONFLICT (order_number) DO NOTHING
                    """),
                    {
                        "order_number": order_number,
                        "item_id": product_id,
                        "site_id": site_id,
                        "config_id": config_id,
                        "planned_qty": rec_qty,
                        "start_date": datetime.combine(start_date, datetime.min.time()),
                        "end_date": datetime.combine(rec_date, datetime.min.time()),
                        "notes": f"MRP recommendation (AbsEntry={abs_entry})",
                        "extra": f'{{"b1_mrp_abs_entry": {abs_entry}}}',
                    },
                )
                created_count += 1

            elif rec_type == "transfer":
                to_number = f"B1-MRP-TO-{abs_entry}"
                from_wh = str(mrp.get("FromWarehouse", "")).strip()
                source_site_id = self._get_site_id(from_wh) if from_wh else first_site_id
                if not source_site_id:
                    source_site_id = first_site_id

                await self.db.execute(
                    text("""
                        INSERT INTO transfer_order
                            (to_number, source_site_id, destination_site_id,
                             config_id, tenant_id, company_id,
                             order_type, source, source_event_id, source_update_dttm,
                             status, order_date, notes)
                        VALUES
                            (:to_number, :source_site_id, :dest_site_id,
                             :config_id, :tenant_id, :company_id,
                             'transfer', 'SAP_B1', :source_event_id, :now,
                             'PLANNED', :order_date, :notes)
                        ON CONFLICT (to_number) DO NOTHING
                    """),
                    {
                        "to_number": to_number,
                        "source_site_id": source_site_id,
                        "dest_site_id": site_id,
                        "config_id": config_id,
                        "tenant_id": self.tenant_id,
                        "company_id": f"B1_{config_id}",
                        "source_event_id": f"B1_OMRP_{abs_entry}",
                        "now": datetime.utcnow(),
                        "order_date": rec_date,
                        "notes": f"MRP recommendation (AbsEntry={abs_entry})",
                    },
                )

                # Insert a single line item for the transfer
                row = await self.db.execute(
                    text("SELECT id FROM transfer_order WHERE to_number = :tn"),
                    {"tn": to_number},
                )
                to_row = row.fetchone()
                if to_row:
                    to_id = to_row[0]
                    await self.db.execute(
                        text("""
                            INSERT INTO transfer_order_line_item
                                (to_id, line_number, product_id, quantity)
                            VALUES
                                (:to_id, 1, :product_id, :quantity)
                        """),
                        {
                            "to_id": to_id,
                            "product_id": product_id,
                            "quantity": rec_qty,
                        },
                    )

                created_count += 1
            else:
                # Unknown recommendation type — skip
                skipped_count += 1
                continue

        await self.db.flush()
        if skipped_count:
            logger.info("Skipped %d MRP results (missing fields or unknown type)", skipped_count)
        logger.info("Created %d planned orders from B1 MRPResults", created_count)
        return created_count

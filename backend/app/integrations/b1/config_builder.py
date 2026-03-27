"""
SAP Business One Config Builder — Staged B1 data → SupplyChainConfig

Transforms extracted B1 entities into the canonical AWS SC data model:
  Warehouses        → Site (INVENTORY / MANUFACTURER)
  BusinessPartners  → TradingPartner (vendor / customer)
  Items             → Product
  ProductTrees      → ProductBOM
  ItemWarehouseInfo → InvLevel + InvPolicy
  PurchaseOrders    → PurchaseOrder + PurchaseOrderLineItem
  Orders            → OutboundOrder + OutboundOrderLine
  ProductionOrders  → ProductionOrder

Usage:
    builder = B1ConfigBuilder(db, tenant_id=28)
    result = await builder.build_from_service_layer(connector)
    # or
    result = await builder.build_from_csv("/path/to/b1_csvs")
"""

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
            "Warehouses", "BusinessPartners", "Items", "ItemGroups",
            "ProductTrees", "ItemWarehouseInfoCollection",
            "Orders", "PurchaseOrders", "ProductionOrders",
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
            "Warehouses", "BusinessPartners", "Items", "ItemGroups",
            "ProductTrees", "ItemWarehouseInfoCollection",
            "Orders", "PurchaseOrders", "ProductionOrders",
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
            await self._load_lookup_maps(config_id)

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

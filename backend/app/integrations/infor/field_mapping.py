"""
Infor M3 → AWS SC Data Model Field Mapping

Three-tier mapping:
  Tier 1 — Exact: M3 MI field → AWS SC entity.field (static dict)
  Tier 2 — Pattern: Regex on OAGIS/M3 field names
  Tier 3 — AI/Fuzzy: Claude API fallback for unknown fields (not in this file)

M3 MI programs use abbreviated field names (max 6 chars):
  ITNO = Item Number, ITDS = Item Description, WHLO = Warehouse,
  SUNO = Supplier Number, CUNO = Customer Number, etc.

OAGIS nouns use long descriptive field names:
  ItemMaster/ItemID, Location/LocationID, PurchaseOrder/DocumentID, etc.

Public OAGIS schemas: https://schema.infor.com/InforOAGIS/Nouns/
"""

from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Tier 1: Exact field mappings
# M3 MI entity → { M3 field → (AWS SC entity, AWS SC field) }
# ---------------------------------------------------------------------------

INFOR_FIELD_MAPPINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "ItemMaster": {
        "ITNO": ("product", "id"),
        "ITDS": ("product", "description"),
        "ITTY": ("product", "product_type"),
        "UCOS": ("product", "unit_cost"),
        "SAPR": ("product", "unit_price"),
        "UNMS": ("product", "base_uom"),
        "GRWE": ("product", "weight"),
        "VOL3": ("product", "volume"),
        "ITGR": ("product", "category"),
        "ITCL": ("product", "family"),
        "STAT": ("product", "is_active"),
    },
    "Warehouse": {
        "WHLO": ("site", "id"),
        "WHNM": ("site", "name"),
        "TOWN": ("site", "city"),
        "CSCD": ("site", "country"),
        "PNOD": ("site", "state"),
        "WHTY": ("site", "master_type"),
    },
    "Supplier": {
        "SUNO": ("trading_partner", "id"),
        "SUNM": ("trading_partner", "description"),
        "TOWN": ("trading_partner", "city"),
        "CSCD": ("trading_partner", "country"),
        "PHNO": ("trading_partner", "phone_number"),
        "STAT": ("trading_partner", "is_active"),
    },
    "Customer": {
        "CUNO": ("trading_partner", "id"),
        "CUNM": ("trading_partner", "description"),
        "TOWN": ("trading_partner", "city"),
        "CSCD": ("trading_partner", "country"),
        "PHNO": ("trading_partner", "phone_number"),
        "STAT": ("trading_partner", "is_active"),
    },
    "PurchaseOrder": {
        "PUNO": ("inbound_order", "id"),
        "SUNO": ("inbound_order", "vendor_id"),
        "PUDT": ("inbound_order", "order_date"),
        "DWDT": ("inbound_order", "expected_delivery_date"),
        "PUSL": ("inbound_order", "status"),
        "LNAM": ("inbound_order", "total_value"),
    },
    "PurchaseOrderLine": {
        "PUNO": ("inbound_order_line", "order_id"),
        "PNLI": ("inbound_order_line", "line_number"),
        "ITNO": ("inbound_order_line", "product_id"),
        "ORQA": ("inbound_order_line", "quantity_submitted"),
        "RVQA": ("inbound_order_line", "quantity_received"),
        "WHLO": ("inbound_order_line", "to_site_id"),
        "PUPR": ("inbound_order_line", "cost"),
        "DWDT": ("inbound_order_line", "expected_delivery_date"),
        "PUSL": ("inbound_order_line", "status"),
    },
    "SalesOrder": {
        "ORNO": ("outbound_order", "id"),
        "CUNO": ("outbound_order", "customer_id"),
        "ORDT": ("outbound_order", "order_date"),
        "DWDT": ("outbound_order", "requested_delivery_date"),
        "ORSL": ("outbound_order", "status"),
        "LNAM": ("outbound_order", "total_value"),
    },
    "SalesOrderLine": {
        "ORNO": ("outbound_order_line", "order_id"),
        "PONR": ("outbound_order_line", "line_number"),
        "ITNO": ("outbound_order_line", "product_id"),
        "ORQA": ("outbound_order_line", "ordered_quantity"),
        "DLQA": ("outbound_order_line", "shipped_quantity"),
        "WHLO": ("outbound_order_line", "site_id"),
        "SAPR": ("outbound_order_line", "unit_price"),
        "DWDT": ("outbound_order_line", "requested_delivery_date"),
        "ORSL": ("outbound_order_line", "status"),
    },
    "ProductionOrder": {
        "MFNO": ("production_order", "id"),
        "PRNO": ("production_order", "product_id"),
        "ORQA": ("production_order", "planned_quantity"),
        "STDT": ("production_order", "start_date"),
        "FIDT": ("production_order", "due_date"),
        "WHST": ("production_order", "status"),
        "WHLO": ("production_order", "site_id"),
    },
    "BillOfMaterial": {
        "PRNO": ("product_bom", "product_id"),
        "MTNO": ("product_bom", "component_product_id"),
        "CNQT": ("product_bom", "component_quantity"),
        "PEUN": ("product_bom", "component_uom"),
        "WAPC": ("product_bom", "scrap_percentage"),
        "FDAT": ("product_bom", "eff_start_date"),
        "TDAT": ("product_bom", "eff_end_date"),
    },
    "InventoryBalance": {
        "ITNO": ("inv_level", "product_id"),
        "WHLO": ("inv_level", "site_id"),
        "STQT": ("inv_level", "on_hand_qty"),
        "APTS": ("inv_level", "available_qty"),
        "REQT": ("inv_level", "reserved_qty"),
        "ORDT": ("inv_level", "inventory_date"),
    },
    "InventoryPolicy": {
        "ITNO": ("inv_policy", "product_id"),
        "WHLO": ("inv_policy", "site_id"),
        "SSQT": ("inv_policy", "ss_quantity"),
        "REOP": ("inv_policy", "reorder_point"),
        "MXST": ("inv_policy", "order_up_to_level"),
        "LOQT": ("inv_policy", "min_order_quantity"),
        "EOQT": ("inv_policy", "fixed_order_quantity"),
        "PLCD": ("inv_policy", "ss_policy"),
    },
    "Shipment": {
        "CONN": ("shipment", "id"),
        "ORNO": ("shipment", "order_id"),
        "ITNO": ("shipment", "product_id"),
        "DLQA": ("shipment", "quantity"),
        "WHLO": ("shipment", "from_site_id"),
        "MODL": ("shipment", "transportation_mode"),
        "DLIX": ("shipment", "tracking_number"),
        "DSDT": ("shipment", "ship_date"),
        "DWDT": ("shipment", "expected_delivery_date"),
    },
    "GoodsReceipt": {
        "REPN": ("goods_receipt", "id"),
        "PUNO": ("goods_receipt", "order_id"),
        "ITNO": ("goods_receipt", "product_id"),
        "RVQA": ("goods_receipt", "quantity"),
        "WHLO": ("goods_receipt", "site_id"),
        "TRDT": ("goods_receipt", "receipt_date"),
    },
    "TransferOrder": {
        "RIDN": ("transfer_order", "id"),
        "ITNO": ("transfer_order", "product_id"),
        "TRQA": ("transfer_order", "quantity"),
        "TWLO": ("transfer_order", "from_site_id"),
        "WHLO": ("transfer_order", "to_site_id"),
        "TRDT": ("transfer_order", "transfer_date"),
        "TTYP": ("transfer_order", "transfer_type"),
    },
    "Forecast": {
        "ITNO": ("forecast", "product_id"),
        "WHLO": ("forecast", "site_id"),
        "FRDT": ("forecast", "forecast_date"),
        "FOQA": ("forecast", "forecast_quantity"),
        "FOTY": ("forecast", "forecast_type"),
    },
    "WorkCenter": {
        "PLGR": ("work_center", "id"),
        "PLNM": ("work_center", "name"),
        "WHLO": ("work_center", "site_id"),
        "PCAP": ("work_center", "capacity_hours"),
    },
    "MaintenanceOrder": {
        "MWNO": ("maintenance_order", "id"),
        "PRNO": ("maintenance_order", "equipment_id"),
        "STDT": ("maintenance_order", "start_date"),
        "FIDT": ("maintenance_order", "due_date"),
        "ORST": ("maintenance_order", "status"),
        "WHLO": ("maintenance_order", "site_id"),
    },
    "QualityInspection": {
        "QRID": ("quality_order", "id"),
        "ITNO": ("quality_order", "product_id"),
        "WHLO": ("quality_order", "site_id"),
        "QRDT": ("quality_order", "inspection_date"),
        "QRST": ("quality_order", "status"),
    },
}


# ---------------------------------------------------------------------------
# Tier 2: Pattern-based mapping (M3 abbreviated field names)
# ---------------------------------------------------------------------------

INFOR_FIELD_PATTERNS = [
    (r".*ITNO.*", ("product", "id")),
    (r".*SUNO.*", ("trading_partner", "id")),      # supplier
    (r".*CUNO.*", ("trading_partner", "id")),      # customer
    (r".*WHLO.*", ("site", "id")),                 # warehouse
    (r".*ORQA.*|.*DLQA.*|.*RVQA.*", None),         # quantity — context dependent
    (r".*SAPR.*|.*UCOS.*|.*PUPR.*", None),         # price/cost
    (r".*DWDT.*|.*ORDT.*|.*STDT.*", None),         # dates
]


# ---------------------------------------------------------------------------
# M3 Status Code → AWS SC Status Mapping
# ---------------------------------------------------------------------------

# M3 Purchase Order status (PUSL)
INFOR_PO_STATUS_MAP = {
    "05": "DRAFT",          # Entered
    "10": "DRAFT",          # Printed
    "15": "APPROVED",       # Activated / Authorized
    "20": "APPROVED",       # Confirmed
    "25": "APPROVED",       # Confirmed with changes
    "35": "PARTIALLY_RECEIVED",  # Partially received
    "45": "RECEIVED",       # Received (fully)
    "50": "RECEIVED",       # Received / invoiced
    "75": "RECEIVED",       # Closed / complete
    "85": "CANCELLED",      # Cancelled
    "99": "RECEIVED",       # Closed
}

# M3 Customer Order status (ORSL)
INFOR_SO_STATUS_MAP = {
    "05": "DRAFT",          # Registered
    "15": "CONFIRMED",      # Order ready
    "22": "CONFIRMED",      # Partially allocated
    "33": "CONFIRMED",      # Allocated
    "44": "PARTIALLY_FULFILLED",  # Partially delivered
    "55": "PARTIALLY_FULFILLED",  # Delivered, not invoiced
    "66": "FULFILLED",      # Invoiced
    "77": "FULFILLED",      # Closed
    "85": "CANCELLED",      # Cancelled
    "99": "FULFILLED",      # Closed
}

# M3 Production Order status (WHST)
INFOR_MO_STATUS_MAP = {
    "10": "PLANNED",        # Planned
    "20": "PLANNED",        # Tentative
    "30": "PLANNED",        # Firm planned
    "40": "RELEASED",       # Released
    "50": "RELEASED",       # Started / Active
    "60": "RELEASED",       # Partially reported
    "70": "CLOSED",         # Reported / completed
    "80": "CLOSED",         # Closed
    "90": "CANCELLED",      # Cancelled
    "99": "CLOSED",         # Archived
}

# M3 Warehouse type (WHTY) → DAG master type
INFOR_WHTY_MAP = {
    "1": "INVENTORY",           # Normal warehouse → DC/Inventory
    "2": "INVENTORY",           # Distribution center
    "3": "MANUFACTURER",        # Manufacturing warehouse
    "4": "INVENTORY",           # External / 3PL
    "5": "INVENTORY",           # Consignment
    "9": "MARKET",              # Customer/Market location
}


def map_po_status(m3_status: str) -> str:
    """Convert M3 PUSL to InboundOrder.status."""
    return INFOR_PO_STATUS_MAP.get(str(m3_status).strip(), "APPROVED")


def map_so_status(m3_status: str) -> str:
    """Convert M3 ORSL to OutboundOrder.status."""
    return INFOR_SO_STATUS_MAP.get(str(m3_status).strip(), "CONFIRMED")


def map_mo_status(m3_status: str) -> str:
    """Convert M3 WHST to ProductionOrder.status."""
    return INFOR_MO_STATUS_MAP.get(str(m3_status).strip(), "PLANNED")


def map_warehouse_type(m3_whty: str) -> str:
    """Convert M3 warehouse type to DAG master type."""
    return INFOR_WHTY_MAP.get(str(m3_whty).strip(), "INVENTORY")


def get_field_mapping(
    entity: str,
    field: str,
) -> Optional[Tuple[str, str]]:
    """Look up the AWS SC mapping for an Infor entity.field.

    Returns (aws_entity, aws_field) or None if no mapping exists.
    """
    entity_map = INFOR_FIELD_MAPPINGS.get(entity, {})
    return entity_map.get(field)

"""
SAP Business One → AWS SC Data Model Field Mapping

Three-tier mapping:
  Tier 1 — Exact: B1 entity.field → AWS SC entity.field (static dict)
  Tier 2 — Pattern: Regex on field names (e.g., *Qty → quantity)
  Tier 3 — AI/Fuzzy: Claude API fallback for unknown fields (not in this file)

B1 Service Layer entity names are used (not DB table names):
  Items (OITM), BusinessPartners (OCRD), ProductTrees (OITT),
  Orders (ORDR), PurchaseOrders (OPOR), Warehouses (OWHS), etc.
"""

from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Tier 1: Exact field mappings
# B1 entity → { B1 field → (AWS SC entity, AWS SC field) }
# ---------------------------------------------------------------------------

B1_FIELD_MAPPINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "Items": {
        "ItemCode": ("product", "id"),
        "ItemName": ("product", "description"),
        "ItemType": ("product", "product_type"),
        "AvgStdPrice": ("product", "unit_cost"),
        "SalesUnit": ("product", "base_uom"),
        "SWeight1": ("product", "weight"),
        "SVolume": ("product", "volume"),
        "ItmsGrpCod": ("product", "category"),
    },
    "BusinessPartners": {
        "CardCode": ("trading_partner", "id"),
        "CardName": ("trading_partner", "description"),
        "CardType": ("trading_partner", "tpartner_type"),  # cSupplier/cCustomer
        "City": ("trading_partner", "city"),
        "Country": ("trading_partner", "country"),
        "Phone1": ("trading_partner", "phone_number"),
    },
    "Warehouses": {
        "WarehouseCode": ("site", "id"),
        "WarehouseName": ("site", "name"),
        "City": ("site", "city"),
        "Country": ("site", "country"),
    },
    "ProductTrees": {
        "TreeCode": ("product_bom", "product_id"),
        "Qauntity": ("product_bom", "component_quantity"),  # B1 typo is real
        "TreeType": ("product_bom", "bom_usage"),  # Extension: btt_SalesTree → sales, btt_TemplateTree → template
    },
    "Orders": {
        "DocEntry": ("outbound_order", "id"),
        "CardCode": ("outbound_order", "customer_id"),
        "DocDate": ("outbound_order", "order_date"),
        "DocDueDate": ("outbound_order", "requested_delivery_date"),
        "DocTotal": ("outbound_order", "order_total"),
    },
    "PurchaseOrders": {
        "DocEntry": ("inbound_order", "id"),
        "CardCode": ("inbound_order", "vendor_id"),
        "DocDate": ("inbound_order", "order_date"),
        "DocDueDate": ("inbound_order", "expected_delivery_date"),
        "DocTotal": ("inbound_order", "order_total"),
    },
    "ProductionOrders": {
        "AbsoluteEntry": ("production_order", "id"),
        "ItemNo": ("production_order", "product_id"),
        "PlannedQuantity": ("production_order", "planned_quantity"),
        "DueDate": ("production_order", "due_date"),
        "Status": ("production_order", "status"),
        "Warehouse": ("production_order", "site_id"),
    },
    "ItemWarehouseInfoCollection": {
        "ItemCode": ("inv_level", "product_id"),
        "WarehouseCode": ("inv_level", "site_id"),
        "InStock": ("inv_level", "on_hand_qty"),
        "Ordered": ("inv_level", "in_transit_qty"),
        "MinimalStock": ("inv_policy", "reorder_point"),
        "MaximalStock": ("inv_policy", "order_up_to_level"),
        "MinimalOrder": ("inv_policy", "min_order_quantity"),
    },
}


# ---------------------------------------------------------------------------
# Tier 2: Pattern-based mapping
# ---------------------------------------------------------------------------

# B1 field name patterns → (AWS SC entity, AWS SC field)
B1_FIELD_PATTERNS = [
    (r".*ItemCode.*", ("product", "id")),
    (r".*CardCode.*", ("trading_partner", "id")),
    (r".*WarehouseCode.*|.*WhsCode.*", ("site", "id")),
    (r".*DocEntry.*", None),  # context-dependent
    (r".*Quantity.*|.*Qty.*", None),  # needs entity context
    (r".*Price.*|.*Cost.*", None),
    (r".*Date.*", None),
]


# ---------------------------------------------------------------------------
# B1 CardType → AWS SC TradingPartner type
# ---------------------------------------------------------------------------

B1_CARD_TYPE_MAP = {
    "cSupplier": "vendor",
    "cCustomer": "customer",
    "L": "vendor",      # Legacy enum value
    "C": "customer",    # Legacy enum value
    "S": "vendor",      # Alternative
}


def map_card_type(b1_card_type: str) -> str:
    """Convert B1 CardType to AWS SC tpartner_type."""
    return B1_CARD_TYPE_MAP.get(b1_card_type, "vendor")


def get_field_mapping(
    entity: str,
    field: str,
) -> Optional[Tuple[str, str]]:
    """Look up the AWS SC mapping for a B1 entity.field.

    Returns (aws_entity, aws_field) or None if no mapping exists.
    """
    entity_map = B1_FIELD_MAPPINGS.get(entity, {})
    return entity_map.get(field)

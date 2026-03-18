"""
Microsoft Dynamics 365 F&O → AWS Supply Chain Data Model Field Mapping

Comprehensive mapping of D365 OData entity fields to AWS SC entities.
Follows the same 3-tier pattern as the SAP and Odoo field mapping services.

D365 uses PascalCase entity names and field names (e.g. ReleasedProductsV2.ItemNumber).
All mappings target AWS SC entities as defined in ``backend/app/models/sc_entities.py``.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Exact Entity+Field → (AWS SC entity, AWS SC field) Mapping
# ─────────────────────────────────────────────────────────────────────────────

D365_ENTITY_FIELD_MAPPINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    # ── Company / Legal Entity ───────────────────────────────────────────
    "LegalEntities": {
        "DataArea": ("company", "company_id"),
        "Name": ("company", "company_name"),
        "AddressCountryRegionId": ("company", "country"),
        "CurrencyCode": ("company", "currency"),
    },
    # ── Sites ────────────────────────────────────────────────────────────
    "OperationalSites": {
        "SiteId": ("site", "site_id"),
        "SiteName": ("site", "site_name"),
    },
    "Warehouses": {
        "WarehouseId": ("site", "warehouse_id"),
        "WarehouseName": ("site", "site_name"),
        "SiteId": ("site", "site_id"),
        "OperationalSiteId": ("site", "parent_site_id"),
        "IsInventoryManaged": ("site", "is_active"),
        "WarehouseType": ("site", "site_type"),
    },
    # ── Products ─────────────────────────────────────────────────────────
    "ReleasedProductsV2": {
        "ItemNumber": ("product", "product_id"),
        "ProductName": ("product", "product_name"),
        "ProductType": ("product", "product_type"),
        "ProductSubType": ("product", "product_subtype"),
        "ProductGroupId": ("product", "product_group"),
        "InventoryUnitSymbol": ("product", "base_uom"),
        "SalesPrice": ("product", "list_price"),
        "ProductionStandardCost": ("product", "unit_cost"),
        "NetWeight": ("product", "weight"),
        "GrossWeight": ("product", "gross_weight"),
        "NetVolume": ("product", "volume"),
        "BarcodeId": ("product", "ean_upc"),
    },
    "ProductCategories": {
        "CategoryId": ("product_hierarchy", "hierarchy_id"),
        "CategoryName": ("product_hierarchy", "hierarchy_name"),
        "ParentCategoryId": ("product_hierarchy", "parent_id"),
        "CategoryHierarchyName": ("product_hierarchy", "hierarchy_type"),
    },
    # ── Bill of Materials ────────────────────────────────────────────────
    "BillOfMaterialsHeaders": {
        "BOMId": ("product_bom", "bom_id"),
        "ProductNumber": ("product_bom", "product_id"),
        "SiteId": ("product_bom", "site_id"),
        "BOMName": ("product_bom", "bom_name"),
        "IsActive": ("product_bom", "is_active"),
        "BOMQuantity": ("product_bom", "bom_quantity"),
        "BOMUnitSymbol": ("product_bom", "bom_uom"),
    },
    "BillOfMaterialsLines": {
        "BOMId": ("product_bom", "bom_id"),
        "LineNumber": ("product_bom", "line_number"),
        "ItemNumber": ("product_bom", "component_id"),
        "BOMLineQuantity": ("product_bom", "component_quantity"),
        "BOMLineQuantityUnitSymbol": ("product_bom", "component_uom"),
        "ScrapPercentage": ("product_bom", "scrap_rate"),
    },
    # ── Vendors (Suppliers) ──────────────────────────────────────────────
    "Vendors": {
        "VendorAccountNumber": ("trading_partner", "partner_id"),
        "VendorName": ("trading_partner", "partner_name"),
        "VendorGroupId": ("trading_partner", "partner_group"),
        "AddressCountryRegionId": ("trading_partner", "country"),
        "AddressCity": ("trading_partner", "city"),
        "AddressZipCode": ("trading_partner", "postal_code"),
        "PrimaryContactPhone": ("trading_partner", "phone"),
        "PrimaryContactEmail": ("trading_partner", "email"),
    },
    # ── Customers ────────────────────────────────────────────────────────
    "CustomersV3": {
        "CustomerAccount": ("trading_partner", "partner_id"),
        "CustomerName": ("trading_partner", "partner_name"),
        "CustomerGroupId": ("trading_partner", "partner_group"),
        "AddressCountryRegionId": ("trading_partner", "country"),
        "AddressCity": ("trading_partner", "city"),
        "AddressZipCode": ("trading_partner", "postal_code"),
        "PrimaryContactPhone": ("trading_partner", "phone"),
        "PrimaryContactEmail": ("trading_partner", "email"),
    },
    # ── Vendor Lead Times & Pricing ──────────────────────────────────────
    "VendorLeadTimes": {
        "VendorAccountNumber": ("vendor_lead_time", "vendor_id"),
        "ItemNumber": ("vendor_lead_time", "product_id"),
        "SiteId": ("vendor_lead_time", "site_id"),
        "LeadTimeDays": ("vendor_lead_time", "lead_time_days"),
    },
    "VendorPurchasePrices": {
        "VendorAccountNumber": ("vendor_product", "vendor_id"),
        "ItemNumber": ("vendor_product", "product_id"),
        "UnitPrice": ("vendor_product", "unit_price"),
        "Currency": ("vendor_product", "currency"),
        "MinimumQuantity": ("vendor_product", "min_order_quantity"),
        "EffectiveDate": ("vendor_product", "valid_from"),
    },
    # ── Inventory Levels ─────────────────────────────────────────────────
    "InventWarehouseOnHandEntity": {
        "ItemNumber": ("inv_level", "product_id"),
        "WarehouseId": ("inv_level", "warehouse_id"),
        "SiteId": ("inv_level", "site_id"),
        "PhysicalOnHandQuantity": ("inv_level", "on_hand_qty"),
        "ReservedQuantity": ("inv_level", "reserved_qty"),
        "AvailableQuantity": ("inv_level", "available_qty"),
    },
    # ── Inventory Policies ───────────────────────────────────────────────
    "InventItemOrderSetups": {
        "ItemNumber": ("inv_policy", "product_id"),
        "SiteId": ("inv_policy", "site_id"),
        "WarehouseId": ("inv_policy", "warehouse_id"),
        "MinimumOrderQuantity": ("inv_policy", "min_order_quantity"),
        "MaximumOrderQuantity": ("inv_policy", "max_order_quantity"),
        "StandardOrderQuantity": ("inv_policy", "fixed_order_quantity"),
        "LeadTimePurchasing": ("inv_policy", "planned_delivery_time"),
    },
    "ItemCoverageSettings": {
        "ItemNumber": ("inv_policy", "product_id"),
        "SiteId": ("inv_policy", "site_id"),
        "WarehouseId": ("inv_policy", "warehouse_id"),
        "MinimumInventoryLevel": ("inv_policy", "reorder_point"),
        "MaximumInventoryLevel": ("inv_policy", "order_up_to_level"),
        "SafetyStockQuantity": ("inv_policy", "ss_quantity"),
        "CoveragePlanGroupId": ("inv_policy", "planning_group"),
    },
    # ── Purchase Orders (Inbound) ────────────────────────────────────────
    "PurchaseOrderHeadersV2": {
        "PurchaseOrderNumber": ("inbound_order", "order_number"),
        "VendorAccountNumber": ("inbound_order", "vendor_id"),
        "OrderDate": ("inbound_order", "order_date"),
        "DeliveryDate": ("inbound_order", "expected_delivery_date"),
        "PurchaseOrderStatus": ("inbound_order", "order_status"),
        "CurrencyCode": ("inbound_order", "currency"),
        "TotalOrderAmount": ("inbound_order", "order_total"),
    },
    "PurchaseOrderLinesV2": {
        "PurchaseOrderNumber": ("inbound_order_line", "order_number"),
        "LineNumber": ("inbound_order_line", "line_number"),
        "ItemNumber": ("inbound_order_line", "product_id"),
        "PurchasedQuantity": ("inbound_order_line", "ordered_qty"),
        "ReceivedQuantity": ("inbound_order_line", "received_qty"),
        "PurchasePrice": ("inbound_order_line", "unit_price"),
        "DeliveryDate": ("inbound_order_line", "expected_date"),
    },
    # ── Sales Orders (Outbound) ──────────────────────────────────────────
    "SalesOrderHeadersV2": {
        "SalesOrderNumber": ("outbound_order", "order_number"),
        "CustomerAccountNumber": ("outbound_order", "customer_id"),
        "OrderDate": ("outbound_order", "order_date"),
        "RequestedShipDate": ("outbound_order", "requested_delivery_date"),
        "SalesOrderStatus": ("outbound_order", "order_status"),
        "CurrencyCode": ("outbound_order", "currency"),
        "TotalOrderAmount": ("outbound_order", "order_total"),
    },
    "SalesOrderLinesV2": {
        "SalesOrderNumber": ("outbound_order_line", "order_number"),
        "LineNumber": ("outbound_order_line", "line_number"),
        "ItemNumber": ("outbound_order_line", "product_id"),
        "OrderedSalesQuantity": ("outbound_order_line", "ordered_qty"),
        "DeliveredQuantity": ("outbound_order_line", "shipped_qty"),
        "SalesPrice": ("outbound_order_line", "unit_price"),
    },
    # ── Production Orders ────────────────────────────────────────────────
    "ProductionOrderHeaders": {
        "ProductionOrderNumber": ("production_order", "order_number"),
        "ItemNumber": ("production_order", "product_id"),
        "ProductionQuantity": ("production_order", "planned_qty"),
        "ProductionStatus": ("production_order", "order_status"),
        "ScheduledStartDate": ("production_order", "planned_start"),
        "ScheduledEndDate": ("production_order", "planned_end"),
        "SiteId": ("production_order", "site_id"),
    },
    # ── Demand Forecasts ─────────────────────────────────────────────────
    "DemandForecastEntries": {
        "ItemNumber": ("forecast", "product_id"),
        "SiteId": ("forecast", "site_id"),
        "WarehouseId": ("forecast", "warehouse_id"),
        "ForecastQuantity": ("forecast", "forecast_quantity"),
        "ForecastDate": ("forecast", "forecast_date"),
        "ForecastModel": ("forecast", "forecast_model"),
    },
    # ── Transportation Routes ────────────────────────────────────────────
    "TransportationRoutes": {
        "RouteId": ("transportation_lane", "lane_id"),
        "RouteName": ("transportation_lane", "lane_name"),
        "OriginSiteId": ("transportation_lane", "source_site_id"),
        "DestinationSiteId": ("transportation_lane", "dest_site_id"),
        "TransitTimeDays": ("transportation_lane", "lead_time_days"),
        "TransportMode": ("transportation_lane", "transport_mode"),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Pattern-based matching for custom / extension fields
# ─────────────────────────────────────────────────────────────────────────────

D365_FIELD_PATTERNS: List[Tuple[str, str, str]] = [
    (r"(?i)ItemNumber|ProductNumber|ProductId", "product", "product_id"),
    (r"(?i)ProductName|ItemName", "product", "product_name"),
    (r"(?i)SiteId|OperationalSiteId", "site", "site_id"),
    (r"(?i)WarehouseId", "site", "warehouse_id"),
    (r"(?i)VendorAccount|VendorId", "trading_partner", "partner_id"),
    (r"(?i)CustomerAccount|CustomerId", "trading_partner", "partner_id"),
    (r"(?i)BOMId", "product_bom", "bom_id"),
    (r"(?i).*Quantity|.*Qty", "inv_level", "quantity"),
    (r"(?i).*Price|.*Cost|.*Amount", "product", "unit_cost"),
    (r"(?i).*Weight", "product", "weight"),
    (r"(?i).*Volume", "product", "volume"),
    (r"(?i)LeadTime|TransitTime", "vendor_lead_time", "lead_time_days"),
    (r"(?i)OrderDate|OrderingDate", "inbound_order", "order_date"),
    (r"(?i)DeliveryDate|ShipDate|RequestedDate", "inbound_order", "expected_delivery_date"),
    (r"(?i)Status|State", "inbound_order", "order_status"),
    (r"(?i)CurrencyCode|Currency", "company", "currency"),
    (r"(?i)dataAreaId|LegalEntity", "company", "company_id"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Mapping Service
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class D365FieldMatch:
    """Result of matching a D365 field to AWS SC field."""
    d365_entity: str
    d365_field: str
    d365_field_type: str = ""
    aws_sc_entity: Optional[str] = None
    aws_sc_field: Optional[str] = None
    confidence: float = 0.0
    match_source: str = "none"

    def to_dict(self):
        return {
            "d365_entity": self.d365_entity,
            "d365_field": self.d365_field,
            "d365_field_type": self.d365_field_type,
            "aws_sc_entity": self.aws_sc_entity,
            "aws_sc_field": self.aws_sc_field,
            "confidence": self.confidence,
            "match_source": self.match_source,
        }


class D365FieldMappingService:
    """Maps D365 F&O entity fields to AWS SC entities."""

    def map_field(self, entity: str, field_name: str, field_type: str = "") -> D365FieldMatch:
        result = D365FieldMatch(
            d365_entity=entity,
            d365_field=field_name,
            d365_field_type=field_type,
        )

        # Tier 1: exact
        entity_map = D365_ENTITY_FIELD_MAPPINGS.get(entity, {})
        if field_name in entity_map:
            sc_entity, sc_field = entity_map[field_name]
            result.aws_sc_entity = sc_entity
            result.aws_sc_field = sc_field
            result.confidence = 1.0
            result.match_source = "exact"
            return result

        # Tier 2: pattern
        for pattern, sc_entity, sc_field in D365_FIELD_PATTERNS:
            if re.match(pattern, field_name):
                result.aws_sc_entity = sc_entity
                result.aws_sc_field = sc_field
                result.confidence = 0.75
                result.match_source = "pattern"
                return result

        # Tier 3: simple fuzzy
        best = _fuzzy_match_d365(field_name)
        if best:
            result.aws_sc_entity = best[0]
            result.aws_sc_field = best[1]
            result.confidence = best[2]
            result.match_source = "fuzzy"

        return result

    def map_entity(self, entity: str, fields: List[str]) -> List[D365FieldMatch]:
        return [self.map_field(entity, f) for f in fields]

    def get_mapping_summary(self, entity: str, fields: List[str]) -> Dict:
        matches = self.map_entity(entity, fields)
        mapped = [m for m in matches if m.aws_sc_entity]
        return {
            "entity": entity,
            "total_fields": len(matches),
            "mapped_fields": len(mapped),
            "coverage_pct": round(len(mapped) / len(matches) * 100, 1) if matches else 0,
            "exact": sum(1 for m in mapped if m.match_source == "exact"),
            "pattern": sum(1 for m in mapped if m.match_source == "pattern"),
            "fuzzy": sum(1 for m in mapped if m.match_source == "fuzzy"),
            "unmapped": [m.d365_field for m in matches if not m.aws_sc_entity],
        }


def _fuzzy_match_d365(field_name: str):
    """Simple fuzzy matching for D365 fields against AWS SC fields."""
    # Flatten all known mappings into a lookup
    all_targets = set()
    for entity_map in D365_ENTITY_FIELD_MAPPINGS.values():
        for sc_entity, sc_field in entity_map.values():
            all_targets.add((sc_entity, sc_field))

    field_lower = field_name.lower().replace("_", "")
    best_score = 0.0
    best_match = None
    for sc_entity, sc_field in all_targets:
        sc_lower = sc_field.lower().replace("_", "")
        # Simple overlap
        if field_lower == sc_lower:
            return (sc_entity, sc_field, 0.9)
        if field_lower in sc_lower or sc_lower in field_lower:
            score = 0.6
            if score > best_score:
                best_score = score
                best_match = (sc_entity, sc_field, score)

    return best_match if best_score > 0.4 else None

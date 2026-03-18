"""
Odoo → AWS Supply Chain Data Model Field Mapping

Comprehensive mapping of Odoo model fields to AWS SC entities.
Follows the same pattern as ``sap_field_mapping_service.py`` but with
Odoo-specific model names, field names, and type conversions.

Mapping tiers:
1. Exact mapping (ODOO_MODEL_FIELD_MAPPINGS) — highest priority
2. Pattern-based matching (ODOO_FIELD_PATTERNS) — regex on field names
3. Fuzzy / AI matching — fallback for custom fields

All mappings target AWS SC entities as defined in
``backend/app/models/sc_entities.py``.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Exact Model+Field → (AWS SC entity, AWS SC field) Mapping
# ─────────────────────────────────────────────────────────────────────────────

ODOO_MODEL_FIELD_MAPPINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    # ── Company & Organisation ───────────────────────────────────────────
    "res.company": {
        "id": ("company", "company_id"),
        "name": ("company", "company_name"),
        "country_id": ("company", "country"),
        "currency_id": ("company", "currency"),
        "street": ("company", "address"),
        "city": ("company", "city"),
        "zip": ("company", "postal_code"),
        "phone": ("company", "phone"),
        "vat": ("company", "tax_id"),
    },
    # ── Sites (Warehouses) ───────────────────────────────────────────────
    "stock.warehouse": {
        "id": ("site", "site_id"),
        "name": ("site", "site_name"),
        "code": ("site", "site_code"),
        "partner_id": ("site", "address_ref"),
        "company_id": ("site", "company_id"),
        "active": ("site", "is_active"),
    },
    "stock.location": {
        "id": ("site", "location_id"),
        "name": ("site", "storage_location"),
        "complete_name": ("site", "storage_location_name"),
        "usage": ("site", "location_type"),
        "warehouse_id": ("site", "site_id"),
        "company_id": ("site", "company_id"),
    },
    # ── Products ─────────────────────────────────────────────────────────
    "product.product": {
        "id": ("product", "product_id"),
        "name": ("product", "product_name"),
        "default_code": ("product", "product_code"),
        "type": ("product", "product_type"),
        "categ_id": ("product", "product_group"),
        "uom_id": ("product", "base_uom"),
        "list_price": ("product", "list_price"),
        "standard_price": ("product", "unit_cost"),
        "weight": ("product", "weight"),
        "volume": ("product", "volume"),
        "barcode": ("product", "ean_upc"),
        "active": ("product", "is_active"),
        "create_date": ("product", "created_date"),
        "write_date": ("product", "last_changed_date"),
    },
    "product.template": {
        "id": ("product", "template_id"),
        "name": ("product", "product_name"),
        "default_code": ("product", "product_code"),
        "type": ("product", "product_type"),
        "categ_id": ("product", "product_group"),
        "uom_id": ("product", "base_uom"),
        "list_price": ("product", "list_price"),
        "standard_price": ("product", "unit_cost"),
        "weight": ("product", "weight"),
        "volume": ("product", "volume"),
        "sale_ok": ("product", "is_sellable"),
        "purchase_ok": ("product", "is_purchasable"),
    },
    "product.category": {
        "id": ("product_hierarchy", "hierarchy_id"),
        "name": ("product_hierarchy", "hierarchy_name"),
        "complete_name": ("product_hierarchy", "full_path"),
        "parent_id": ("product_hierarchy", "parent_id"),
    },
    # ── Bill of Materials ────────────────────────────────────────────────
    "mrp.bom": {
        "id": ("product_bom", "bom_id"),
        "product_tmpl_id": ("product_bom", "product_id"),
        "product_qty": ("product_bom", "bom_quantity"),
        "product_uom_id": ("product_bom", "bom_uom"),
        "type": ("product_bom", "bom_type"),
        "code": ("product_bom", "bom_code"),
        "active": ("product_bom", "is_active"),
        "company_id": ("product_bom", "company_id"),
    },
    "mrp.bom.line": {
        "id": ("product_bom", "bom_line_id"),
        "bom_id": ("product_bom", "bom_id"),
        "product_id": ("product_bom", "component_id"),
        "product_qty": ("product_bom", "component_quantity"),
        "product_uom_id": ("product_bom", "component_uom"),
    },
    # ── Work Centers (Production Resources) ──────────────────────────────
    "mrp.workcenter": {
        "id": ("production_process", "workcenter_id"),
        "name": ("production_process", "workcenter_name"),
        "capacity": ("production_process", "capacity"),
        "time_efficiency": ("production_process", "efficiency"),
        "oee_target": ("production_process", "oee_target"),
        "costs_hour": ("production_process", "cost_per_hour"),
        "company_id": ("production_process", "company_id"),
    },
    # ── Trading Partners (Vendors & Customers) ───────────────────────────
    "res.partner": {
        "id": ("trading_partner", "partner_id"),
        "name": ("trading_partner", "partner_name"),
        "country_id": ("trading_partner", "country"),
        "state_id": ("trading_partner", "region"),
        "city": ("trading_partner", "city"),
        "zip": ("trading_partner", "postal_code"),
        "street": ("trading_partner", "address"),
        "phone": ("trading_partner", "phone"),
        "email": ("trading_partner", "email"),
        "supplier_rank": ("trading_partner", "supplier_rank"),
        "customer_rank": ("trading_partner", "customer_rank"),
        "company_type": ("trading_partner", "partner_type"),
        "vat": ("trading_partner", "tax_id"),
    },
    # ── Vendor-Product (Supplier Info) ───────────────────────────────────
    "product.supplierinfo": {
        "id": ("vendor_product", "supplierinfo_id"),
        "partner_id": ("vendor_product", "vendor_id"),
        "product_tmpl_id": ("vendor_product", "product_id"),
        "min_qty": ("vendor_product", "min_order_quantity"),
        "price": ("vendor_product", "unit_price"),
        "delay": ("vendor_lead_time", "lead_time_days"),
        "currency_id": ("vendor_product", "currency"),
        "date_start": ("vendor_product", "valid_from"),
        "date_end": ("vendor_product", "valid_to"),
        "company_id": ("vendor_product", "company_id"),
    },
    # ── Inventory Levels ─────────────────────────────────────────────────
    "stock.quant": {
        "id": ("inv_level", "quant_id"),
        "product_id": ("inv_level", "product_id"),
        "location_id": ("inv_level", "site_id"),
        "quantity": ("inv_level", "on_hand_qty"),
        "reserved_quantity": ("inv_level", "reserved_qty"),
        "company_id": ("inv_level", "company_id"),
        "write_date": ("inv_level", "inventory_date"),
    },
    # ── Inventory Policy (Reorder Rules) ─────────────────────────────────
    "stock.warehouse.orderpoint": {
        "id": ("inv_policy", "orderpoint_id"),
        "product_id": ("inv_policy", "product_id"),
        "warehouse_id": ("inv_policy", "site_id"),
        "product_min_qty": ("inv_policy", "reorder_point"),
        "product_max_qty": ("inv_policy", "order_up_to_level"),
        "qty_multiple": ("inv_policy", "fixed_order_quantity"),
        "lead_days_date": ("inv_policy", "lead_time_date"),
        "company_id": ("inv_policy", "company_id"),
    },
    # ── Purchase Orders (Inbound) ────────────────────────────────────────
    "purchase.order": {
        "id": ("inbound_order", "order_id"),
        "name": ("inbound_order", "order_number"),
        "partner_id": ("inbound_order", "vendor_id"),
        "date_order": ("inbound_order", "order_date"),
        "date_planned": ("inbound_order", "expected_delivery_date"),
        "state": ("inbound_order", "order_status"),
        "amount_total": ("inbound_order", "order_total"),
        "currency_id": ("inbound_order", "currency"),
        "company_id": ("inbound_order", "company_id"),
        "picking_type_id": ("inbound_order", "receiving_site_id"),
    },
    "purchase.order.line": {
        "id": ("inbound_order_line", "line_id"),
        "order_id": ("inbound_order_line", "order_id"),
        "product_id": ("inbound_order_line", "product_id"),
        "product_qty": ("inbound_order_line", "ordered_qty"),
        "qty_received": ("inbound_order_line", "received_qty"),
        "price_unit": ("inbound_order_line", "unit_price"),
        "date_planned": ("inbound_order_line", "expected_date"),
    },
    # ── Sales Orders (Outbound) ──────────────────────────────────────────
    "sale.order": {
        "id": ("outbound_order", "order_id"),
        "name": ("outbound_order", "order_number"),
        "partner_id": ("outbound_order", "customer_id"),
        "date_order": ("outbound_order", "order_date"),
        "commitment_date": ("outbound_order", "requested_delivery_date"),
        "state": ("outbound_order", "order_status"),
        "amount_total": ("outbound_order", "order_total"),
        "currency_id": ("outbound_order", "currency"),
        "company_id": ("outbound_order", "company_id"),
        "warehouse_id": ("outbound_order", "ship_from_site_id"),
    },
    "sale.order.line": {
        "id": ("outbound_order_line", "line_id"),
        "order_id": ("outbound_order_line", "order_id"),
        "product_id": ("outbound_order_line", "product_id"),
        "product_uom_qty": ("outbound_order_line", "ordered_qty"),
        "qty_delivered": ("outbound_order_line", "shipped_qty"),
        "price_unit": ("outbound_order_line", "unit_price"),
    },
    # ── Manufacturing Orders ─────────────────────────────────────────────
    "mrp.production": {
        "id": ("production_order", "order_id"),
        "name": ("production_order", "order_number"),
        "product_id": ("production_order", "product_id"),
        "product_qty": ("production_order", "planned_qty"),
        "qty_produced": ("production_order", "produced_qty"),
        "bom_id": ("production_order", "bom_id"),
        "state": ("production_order", "order_status"),
        "date_start": ("production_order", "planned_start"),
        "date_finished": ("production_order", "actual_finish"),
        "company_id": ("production_order", "company_id"),
    },
    # ── Stock Transfers (Internal Movements) ─────────────────────────────
    "stock.picking": {
        "id": ("shipment", "picking_id"),
        "name": ("shipment", "shipment_number"),
        "origin": ("shipment", "source_document"),
        "partner_id": ("shipment", "partner_id"),
        "picking_type_id": ("shipment", "operation_type"),
        "location_id": ("shipment", "source_site_id"),
        "location_dest_id": ("shipment", "dest_site_id"),
        "state": ("shipment", "status"),
        "scheduled_date": ("shipment", "scheduled_date"),
        "date_done": ("shipment", "actual_date"),
        "company_id": ("shipment", "company_id"),
    },
    "stock.move": {
        "id": ("shipment_line", "move_id"),
        "picking_id": ("shipment_line", "picking_id"),
        "product_id": ("shipment_line", "product_id"),
        "product_uom_qty": ("shipment_line", "planned_qty"),
        "quantity": ("shipment_line", "actual_qty"),
        "location_id": ("shipment_line", "source_site_id"),
        "location_dest_id": ("shipment_line", "dest_site_id"),
        "state": ("shipment_line", "status"),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Pattern-based matching for custom / unknown fields
# ─────────────────────────────────────────────────────────────────────────────

ODOO_FIELD_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex_pattern, aws_sc_entity, aws_sc_field)
    (r"^product_id$|^product_tmpl_id$", "product", "product_id"),
    (r"^partner_id$", "trading_partner", "partner_id"),
    (r"^company_id$", "company", "company_id"),
    (r"^warehouse_id$", "site", "site_id"),
    (r"^location_id$", "site", "location_id"),
    (r"^categ_id$", "product_hierarchy", "hierarchy_id"),
    (r"^uom_id$|^product_uom_id$|^product_uom$", "product", "base_uom"),
    (r"^currency_id$", "company", "currency"),
    (r"^bom_id$", "product_bom", "bom_id"),
    (r"(?i)qty|quantity", "inv_level", "quantity"),
    (r"(?i)price|cost", "product", "unit_cost"),
    (r"(?i)weight", "product", "weight"),
    (r"(?i)volume", "product", "volume"),
    (r"(?i)barcode|ean|upc", "product", "ean_upc"),
    (r"(?i)lead.*time|delay", "vendor_lead_time", "lead_time_days"),
    (r"(?i)date_order|order_date", "inbound_order", "order_date"),
    (r"(?i)date_planned|planned_date|expected", "inbound_order", "expected_delivery_date"),
    (r"(?i)state|status", "inbound_order", "order_status"),
    (r"(?i)create_date|created", "product", "created_date"),
    (r"(?i)write_date|modified|changed", "product", "last_changed_date"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Tier 3: AWS SC target field definitions (same as SAP mapping service)
# ─────────────────────────────────────────────────────────────────────────────

AWS_SC_ENTITIES = {
    "company": ["company_id", "company_name", "country", "currency", "address", "city", "postal_code"],
    "site": ["site_id", "site_name", "site_code", "company_id", "is_active", "storage_location"],
    "product": ["product_id", "product_name", "product_code", "product_type", "product_group",
                 "base_uom", "unit_cost", "list_price", "weight", "volume", "ean_upc"],
    "product_bom": ["bom_id", "product_id", "component_id", "component_quantity", "bom_quantity"],
    "production_process": ["workcenter_id", "workcenter_name", "capacity", "cost_per_hour"],
    "trading_partner": ["partner_id", "partner_name", "country", "city", "address", "phone"],
    "vendor_product": ["vendor_id", "product_id", "unit_price", "min_order_quantity"],
    "vendor_lead_time": ["vendor_id", "product_id", "lead_time_days"],
    "inv_level": ["product_id", "site_id", "on_hand_qty", "reserved_qty"],
    "inv_policy": ["product_id", "site_id", "reorder_point", "order_up_to_level"],
    "inbound_order": ["order_id", "order_number", "vendor_id", "order_date", "order_status"],
    "inbound_order_line": ["line_id", "order_id", "product_id", "ordered_qty", "unit_price"],
    "outbound_order": ["order_id", "order_number", "customer_id", "order_date", "order_status"],
    "outbound_order_line": ["line_id", "order_id", "product_id", "ordered_qty", "unit_price"],
    "production_order": ["order_id", "product_id", "planned_qty", "order_status"],
    "shipment": ["picking_id", "shipment_number", "source_site_id", "dest_site_id", "status"],
    "shipment_line": ["move_id", "picking_id", "product_id", "planned_qty"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Mapping Service
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OdooFieldMatch:
    """Result of matching an Odoo field to AWS SC field."""
    odoo_model: str
    odoo_field: str
    odoo_field_type: str
    aws_sc_entity: Optional[str] = None
    aws_sc_field: Optional[str] = None
    confidence: float = 0.0
    match_source: str = "none"  # "exact", "pattern", "fuzzy"

    def to_dict(self):
        return {
            "odoo_model": self.odoo_model,
            "odoo_field": self.odoo_field,
            "odoo_field_type": self.odoo_field_type,
            "aws_sc_entity": self.aws_sc_entity,
            "aws_sc_field": self.aws_sc_field,
            "confidence": self.confidence,
            "match_source": self.match_source,
        }


class OdooFieldMappingService:
    """Maps Odoo model fields to AWS SC entities.

    Three-tier matching: exact → pattern → fuzzy.
    """

    def map_field(self, model: str, field_name: str, field_type: str = "") -> OdooFieldMatch:
        """Map a single Odoo field to AWS SC."""
        result = OdooFieldMatch(
            odoo_model=model,
            odoo_field=field_name,
            odoo_field_type=field_type,
        )

        # Tier 1: exact
        model_map = ODOO_MODEL_FIELD_MAPPINGS.get(model, {})
        if field_name in model_map:
            entity, sc_field = model_map[field_name]
            result.aws_sc_entity = entity
            result.aws_sc_field = sc_field
            result.confidence = 1.0
            result.match_source = "exact"
            return result

        # Tier 2: pattern
        for pattern, entity, sc_field in ODOO_FIELD_PATTERNS:
            if re.match(pattern, field_name):
                result.aws_sc_entity = entity
                result.aws_sc_field = sc_field
                result.confidence = 0.75
                result.match_source = "pattern"
                return result

        # Tier 3: fuzzy (simple string similarity)
        best_score = 0.0
        for entity, fields in AWS_SC_ENTITIES.items():
            for sc_field in fields:
                score = _simple_similarity(field_name, sc_field)
                if score > best_score and score > 0.5:
                    best_score = score
                    result.aws_sc_entity = entity
                    result.aws_sc_field = sc_field
                    result.confidence = score * 0.8  # discount fuzzy
                    result.match_source = "fuzzy"

        return result

    def map_model(self, model: str, fields: Dict[str, Dict]) -> List[OdooFieldMatch]:
        """Map all fields of an Odoo model to AWS SC."""
        results = []
        for field_name, field_info in fields.items():
            if field_name.startswith("__") or field_name in ("id",):
                continue
            ftype = field_info.get("type", "") if isinstance(field_info, dict) else ""
            results.append(self.map_field(model, field_name, ftype))
        return results

    def get_mapping_summary(self, model: str, fields: Dict[str, Dict]) -> Dict:
        """Get mapping coverage summary for a model."""
        matches = self.map_model(model, fields)
        mapped = [m for m in matches if m.aws_sc_entity]
        return {
            "model": model,
            "total_fields": len(matches),
            "mapped_fields": len(mapped),
            "coverage_pct": round(len(mapped) / len(matches) * 100, 1) if matches else 0,
            "exact_matches": sum(1 for m in mapped if m.match_source == "exact"),
            "pattern_matches": sum(1 for m in mapped if m.match_source == "pattern"),
            "fuzzy_matches": sum(1 for m in mapped if m.match_source == "fuzzy"),
            "unmapped": [m.odoo_field for m in matches if not m.aws_sc_entity],
        }


def _simple_similarity(a: str, b: str) -> float:
    """Simple string similarity for fuzzy matching."""
    a, b = a.lower().replace("_", ""), b.lower().replace("_", "")
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.7
    # character overlap
    common = len(set(a) & set(b))
    total = len(set(a) | set(b))
    return common / total if total else 0.0

"""
SAP Z-Table/Z-Field Mapping Service with Fuzzy Matching

Provides intelligent mapping of custom SAP tables (Z-tables) and fields (Z-fields)
to AWS Supply Chain entities using:
1. Fuzzy string matching for field names
2. AI-powered semantic analysis for complex mappings
3. Pattern recognition for common SAP naming conventions
4. Learning from user-confirmed mappings

Key Features:
- Auto-detect Z-tables and Z-fields from SAP metadata
- Fuzzy matching using Levenshtein distance and token-based similarity
- Claude AI-powered suggestions for ambiguous mappings
- Mapping history and learning from corrections
- Batch mapping with confidence scoring
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import asyncio
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MatchConfidence(str, Enum):
    """Confidence level for field mapping."""
    HIGH = "high"        # >90% confidence - auto-map
    MEDIUM = "medium"    # 70-90% - suggest with review
    LOW = "low"          # 50-70% - needs user input
    NONE = "none"        # <50% - no suggestion


class MappingSource(str, Enum):
    """Source of the mapping decision."""
    AUTO_EXACT = "auto_exact"         # Exact name match
    AUTO_FUZZY = "auto_fuzzy"         # Fuzzy string match
    AUTO_PATTERN = "auto_pattern"     # Pattern-based match
    AI_SUGGESTED = "ai_suggested"     # AI/Claude suggested
    USER_CONFIRMED = "user_confirmed" # User manually confirmed
    USER_CREATED = "user_created"     # User manually created
    LEARNED = "learned"               # Learned from history


@dataclass
class FieldMatchResult:
    """Result of matching a SAP field to AWS SC field."""
    sap_field: str
    sap_field_description: str
    sap_field_type: str
    is_z_field: bool

    # Best match
    aws_sc_entity: Optional[str] = None
    aws_sc_field: Optional[str] = None
    aws_sc_field_type: Optional[str] = None

    # Match quality
    confidence: MatchConfidence = MatchConfidence.NONE
    confidence_score: float = 0.0
    match_source: MappingSource = MappingSource.AUTO_FUZZY

    # Alternative matches
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    # AI analysis
    ai_rationale: Optional[str] = None
    ai_transform_suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sap_field": self.sap_field,
            "sap_field_description": self.sap_field_description,
            "sap_field_type": self.sap_field_type,
            "is_z_field": self.is_z_field,
            "aws_sc_entity": self.aws_sc_entity,
            "aws_sc_field": self.aws_sc_field,
            "aws_sc_field_type": self.aws_sc_field_type,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "match_source": self.match_source.value,
            "alternatives": self.alternatives,
            "ai_rationale": self.ai_rationale,
            "ai_transform_suggestion": self.ai_transform_suggestion,
        }


@dataclass
class ZTableAnalysis:
    """Analysis of a Z-table for mapping purposes."""
    table_name: str
    description: str
    field_count: int
    z_field_count: int

    # Suggested target
    suggested_entity: Optional[str] = None
    entity_confidence: float = 0.0

    # Field mappings
    field_mappings: List[FieldMatchResult] = field(default_factory=list)

    # Completeness
    mappable_fields: int = 0
    mapped_fields: int = 0
    unmapped_required: int = 0

    # AI analysis
    ai_purpose_analysis: Optional[str] = None
    ai_integration_guidance: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "description": self.description,
            "field_count": self.field_count,
            "z_field_count": self.z_field_count,
            "suggested_entity": self.suggested_entity,
            "entity_confidence": self.entity_confidence,
            "field_mappings": [f.to_dict() for f in self.field_mappings],
            "mappable_fields": self.mappable_fields,
            "mapped_fields": self.mapped_fields,
            "unmapped_required": self.unmapped_required,
            "ai_purpose_analysis": self.ai_purpose_analysis,
            "ai_integration_guidance": self.ai_integration_guidance,
        }


# ---------------------------------------------------------------------------
# Comprehensive TABLE-SPECIFIC SAP → Autonomy field mappings.
# Keyed by SAP table name → { SAP_FIELD: (autonomy_entity, autonomy_field) }
# This takes absolute priority over pattern/fuzzy matching because the same
# SAP field (e.g. MATNR) maps to different Autonomy fields depending on which
# SAP table it appears in.
# ---------------------------------------------------------------------------

SAP_TABLE_FIELD_MAPPINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    # ── Company & Org Structure ──────────────────────────────────────────
    "T001": {
        "BUKRS": ("company", "company_id"),
        "BUTXT": ("company", "company_name"),
        "LAND1": ("company", "country"),
        "WAERS": ("company", "currency"),
        "SPRAS": ("company", "language"),
    },
    "T001W": {
        "WERKS": ("site", "site_id"),
        "NAME1": ("site", "site_name"),
        "BWKEY": ("site", "valuation_area"),
        "VKORG": ("site", "sales_org"),
        "EKORG": ("site", "purchasing_org"),
        "FABKL": ("site", "factory_calendar"),
        "STRAS": ("site", "address"),
        "ORT01": ("site", "city"),
        "PSTLZ": ("site", "postal_code"),
        "REGIO": ("site", "region"),
        "LAND1": ("site", "country"),
        "ADRNR": ("site", "address_number"),
    },
    "T001L": {
        "WERKS": ("site", "site_id"),
        "LGORT": ("site", "storage_location"),
        "LGOBE": ("site", "storage_location_name"),
    },
    "ADRC": {
        "ADDRNUMBER": ("site", "address_number"),
        "NAME1": ("site", "site_name"),
        "CITY1": ("site", "city"),
        "POST_CODE1": ("site", "postal_code"),
        "REGION": ("site", "region"),
        "COUNTRY": ("site", "country"),
        "STREET": ("site", "address"),
        "HOUSE_NUM1": ("site", "house_number"),
        "TEL_NUMBER": ("site", "phone"),
        "FAX_NUMBER": ("site", "fax"),
    },
    # ── Material / Product Master ────────────────────────────────────────
    "MARA": {
        "MATNR": ("product", "product_id"),
        "MTART": ("product", "product_type"),
        "MEINS": ("product", "base_uom"),
        "MATKL": ("product", "product_group"),
        "BRGEW": ("product", "weight"),
        "NTGEW": ("product", "net_weight"),
        "GEWEI": ("product", "weight_uom"),
        "VOLUM": ("product", "volume"),
        "VOLEH": ("product", "volume_uom"),
        "MBRSH": ("product", "industry_sector"),
        "ERSDA": ("product", "created_date"),
        "LAEDA": ("product", "last_changed_date"),
        "EAN11": ("product", "ean_upc"),
        "NUMTP": ("product", "ean_type"),
        "PRDHA": ("product", "product_hierarchy"),
    },
    "MAKT": {
        "MATNR": ("product", "product_id"),
        "SPRAS": ("product", "language"),
        "MAKTX": ("product", "product_name"),
    },
    "MARC": {
        "MATNR": ("inv_policy", "product_id"),
        "WERKS": ("inv_policy", "site_id"),
        "EKGRP": ("inv_policy", "purchasing_group"),
        "DISMM": ("inv_policy", "mrp_type"),
        "DISPO": ("inv_policy", "mrp_controller"),
        "DISLS": ("inv_policy", "lot_size_procedure"),
        "MINBE": ("inv_policy", "reorder_point"),
        "EISBE": ("inv_policy", "ss_quantity"),
        "BSTRF": ("inv_policy", "fixed_order_quantity"),
        "BSTMI": ("inv_policy", "min_order_quantity"),
        "BSTMA": ("inv_policy", "max_order_quantity"),
        "BESKZ": ("inv_policy", "procurement_type"),
        "SOBSL": ("inv_policy", "special_procurement"),
        "PLIFZ": ("inv_policy", "planned_delivery_time"),
        "WEBAZ": ("inv_policy", "gr_processing_time"),
        "FHORI": ("inv_policy", "scheduling_margin_key"),
        "MABST": ("inv_policy", "order_up_to_level"),
        "LOSGR": ("inv_policy", "lot_size"),
        "FXHOR": ("inv_policy", "planning_time_fence"),
        "VRMOD": ("inv_policy", "consumption_mode"),
        "VINT1": ("inv_policy", "consumption_fwd_periods"),
        "VINT2": ("inv_policy", "consumption_bwd_periods"),
        "STRGR": ("inv_policy", "planning_strategy_group"),
        "LGPRO": ("inv_policy", "production_storage_location"),
        "LGFSB": ("inv_policy", "external_procurement_sloc"),
        "PRCTR": ("inv_policy", "profit_center"),
    },
    "MARD": {
        "MATNR": ("inv_level", "product_id"),
        "WERKS": ("inv_level", "site_id"),
        "LGORT": ("inv_level", "storage_location"),
        "LABST": ("inv_level", "quantity"),
        "UMLME": ("inv_level", "transfer_stock"),
        "INSME": ("inv_level", "quality_inspection_stock"),
        "EINME": ("inv_level", "restricted_stock"),
        "SPEME": ("inv_level", "blocked_stock"),
        "RETME": ("inv_level", "returns_stock"),
    },
    "MARM": {
        "MATNR": ("product", "product_id"),
        "MEINH": ("product", "alt_uom"),
        "UMREZ": ("product", "uom_numerator"),
        "UMREN": ("product", "uom_denominator"),
        "BRGEW": ("product", "weight"),
        "VOLUM": ("product", "volume"),
    },
    "MBEW": {
        "MATNR": ("product", "product_id"),
        "BWKEY": ("product", "valuation_area"),
        "BKLAS": ("product", "valuation_class"),
        "VPRSV": ("product", "price_control"),
        "VERPR": ("product", "moving_avg_price"),
        "STPRS": ("product", "standard_price"),
        "PEINH": ("product", "price_unit"),
        "SALK3": ("product", "total_stock_value"),
        "LBKUM": ("product", "total_valuated_stock"),
    },
    "MVKE": {
        "MATNR": ("product", "product_id"),
        "VKORG": ("product", "sales_org"),
        "VTWEG": ("product", "distribution_channel"),
        "PRODH": ("product", "product_hierarchy"),
        "KONDM": ("product", "material_pricing_group"),
        "KTGRM": ("product", "account_assignment_group"),
        "MTPOS": ("product", "item_category_group"),
    },
    # ── Trading Partners (Vendors & Customers) ───────────────────────────
    "LFA1": {
        "LIFNR": ("trading_partner", "partner_id"),
        "NAME1": ("trading_partner", "partner_name"),
        "NAME2": ("trading_partner", "partner_name_2"),
        "LAND1": ("trading_partner", "country"),
        "REGIO": ("trading_partner", "region"),
        "ORT01": ("trading_partner", "city"),
        "PSTLZ": ("trading_partner", "postal_code"),
        "STRAS": ("trading_partner", "address"),
        "TELF1": ("trading_partner", "phone"),
        "ADRNR": ("trading_partner", "address_number"),
    },
    "KNA1": {
        "KUNNR": ("trading_partner", "partner_id"),
        "NAME1": ("trading_partner", "partner_name"),
        "NAME2": ("trading_partner", "partner_name_2"),
        "LAND1": ("trading_partner", "country"),
        "REGIO": ("trading_partner", "region"),
        "ORT01": ("trading_partner", "city"),
        "PSTLZ": ("trading_partner", "postal_code"),
        "STRAS": ("trading_partner", "address"),
        "TELF1": ("trading_partner", "phone"),
        "ADRNR": ("trading_partner", "address_number"),
        "KTOKD": ("trading_partner", "account_group"),
    },
    # ── Purchasing Info Records ───────────────────────────────────────────
    "EINA": {
        "INFNR": ("trading_partner", "info_record_id"),
        "MATNR": ("trading_partner", "product_id"),
        "LIFNR": ("trading_partner", "partner_id"),
        "LOEKZ": ("trading_partner", "deletion_indicator"),
        "ERDAT": ("trading_partner", "created_date"),
        "TXZ01": ("trading_partner", "short_text"),
        "MEINS": ("trading_partner", "order_uom"),
    },
    "EINE": {
        "INFNR": ("trading_partner", "info_record_id"),
        "EKORG": ("trading_partner", "purchasing_org"),
        "WERKS": ("trading_partner", "site_id"),
        "ESOKZ": ("trading_partner", "info_category"),
        "NETPR": ("trading_partner", "net_price"),
        "PEINH": ("trading_partner", "price_unit"),
        "WAERS": ("trading_partner", "currency"),
        "APLFZ": ("trading_partner", "planned_delivery_time"),
        "NORBM": ("trading_partner", "standard_quantity"),
        "MINBM": ("trading_partner", "minimum_quantity"),
        "UEBTO": ("trading_partner", "over_delivery_tolerance"),
        "UNTTO": ("trading_partner", "under_delivery_tolerance"),
    },
    "EORD": {
        "MATNR": ("trading_partner", "product_id"),
        "WERKS": ("trading_partner", "site_id"),
        "ZEORD": ("trading_partner", "source_list_number"),
        "VDATU": ("trading_partner", "valid_from"),
        "BDATU": ("trading_partner", "valid_to"),
        "LIFNR": ("trading_partner", "partner_id"),
        "FLIFN": ("trading_partner", "fixed_vendor"),
        "NOTKZ": ("trading_partner", "order_assignment"),
        "EKORG": ("trading_partner", "purchasing_org"),
        "EORTP": ("trading_partner", "source_type"),
    },
    # ── Purchase Requisitions ─────────────────────────────────────────────
    "EBAN": {
        "BANFN": ("purchase_requisition", "requisition_id"),
        "BNFPO": ("purchase_requisition", "line_number"),
        "BSART": ("purchase_requisition", "requisition_type"),
        "MATNR": ("purchase_requisition", "product_id"),
        "WERKS": ("purchase_requisition", "site_id"),
        "LGORT": ("purchase_requisition", "storage_location"),
        "MENGE": ("purchase_requisition", "quantity"),
        "MEINS": ("purchase_requisition", "uom"),
        "PREIS": ("purchase_requisition", "price"),
        "PEINH": ("purchase_requisition", "price_unit"),
        "EKGRP": ("purchase_requisition", "purchasing_group"),
        "FRGKZ": ("purchase_requisition", "release_indicator"),
        "FRGZU": ("purchase_requisition", "release_status"),
        "LOEKZ": ("purchase_requisition", "deletion_indicator"),
        "BADAT": ("purchase_requisition", "requisition_date"),
        "LFDAT": ("purchase_requisition", "delivery_date"),
    },
    # ── Purchase Orders ───────────────────────────────────────────────────
    "EKKO": {
        "EBELN": ("inbound_order", "order_id"),
        "BSART": ("inbound_order", "order_type"),
        "BSTYP": ("inbound_order", "order_category"),
        "LIFNR": ("inbound_order", "supplier_id"),
        "EKORG": ("inbound_order", "purchasing_org"),
        "EKGRP": ("inbound_order", "purchasing_group"),
        "BUKRS": ("inbound_order", "company_id"),
        "ERNAM": ("inbound_order", "created_by"),
        "AEDAT": ("inbound_order", "changed_date"),
        "BEDAT": ("inbound_order", "order_date"),
        "WAERS": ("inbound_order", "currency"),
    },
    "EKPO": {
        "EBELN": ("inbound_order", "order_id"),
        "EBELP": ("inbound_order", "line_number"),
        "MATNR": ("inbound_order", "product_id"),
        "WERKS": ("inbound_order", "site_id"),
        "LGORT": ("inbound_order", "storage_location"),
        "MENGE": ("inbound_order", "quantity"),
        "MEINS": ("inbound_order", "uom"),
        "NETPR": ("inbound_order", "net_price"),
        "PEINH": ("inbound_order", "price_unit"),
        "NETWR": ("inbound_order", "net_value"),
        "BPRME": ("inbound_order", "order_price_uom"),
        "BSTYP": ("inbound_order", "order_category"),
        "KNTTP": ("inbound_order", "account_assignment"),
        "PSTYP": ("inbound_order", "item_category"),
        "ELIKZ": ("inbound_order", "delivery_complete"),
    },
    "EKET": {
        "EBELN": ("inbound_order", "order_id"),
        "EBELP": ("inbound_order", "line_number"),
        "ETENR": ("inbound_order", "schedule_line"),
        "EINDT": ("inbound_order", "delivery_date"),
        "MENGE": ("inbound_order", "scheduled_quantity"),
        "WEMNG": ("inbound_order", "goods_received_quantity"),
        "WAMNG": ("inbound_order", "goods_issued_quantity"),
        "SLFDT": ("inbound_order", "stat_delivery_date"),
    },
    # ── Sales Orders ──────────────────────────────────────────────────────
    "VBAK": {
        "VBELN": ("outbound_order", "order_id"),
        "AUART": ("outbound_order", "order_type"),
        "VKORG": ("outbound_order", "sales_org"),
        "VTWEG": ("outbound_order", "distribution_channel"),
        "SPART": ("outbound_order", "division"),
        "KUNNR": ("outbound_order", "customer_id"),
        "ERDAT": ("outbound_order", "order_date"),
        "VDATU": ("outbound_order", "requested_date"),
        "BSTNK": ("outbound_order", "customer_po"),
        "WAERK": ("outbound_order", "currency"),
        "NETWR": ("outbound_order", "net_value"),
        "KNUMV": ("outbound_order", "pricing_doc"),
        "GBSTK": ("outbound_order", "overall_status"),
    },
    "VBAP": {
        "VBELN": ("outbound_order", "order_id"),
        "POSNR": ("outbound_order", "line_number"),
        "MATNR": ("outbound_order", "product_id"),
        "WERKS": ("outbound_order", "ship_from_site_id"),
        "KWMENG": ("outbound_order", "quantity"),
        "MEINS": ("outbound_order", "uom"),
        "NETPR": ("outbound_order", "net_price"),
        "NETWR": ("outbound_order", "net_value"),
        "WAERK": ("outbound_order", "currency"),
        "LFREL": ("outbound_order", "delivery_relevant"),
        "ABGRU": ("outbound_order", "rejection_reason"),
        "PSTYV": ("outbound_order", "item_category"),
    },
    "VBEP": {
        "VBELN": ("outbound_order", "order_id"),
        "POSNR": ("outbound_order", "line_number"),
        "ETENR": ("outbound_order", "schedule_line"),
        "EDATU": ("outbound_order", "delivery_date"),
        "WMENG": ("outbound_order", "ordered_quantity"),
        "BMENG": ("outbound_order", "confirmed_quantity"),
        "LMENG": ("outbound_order", "delivered_quantity"),
        "MEINS": ("outbound_order", "uom"),
    },
    "VBUK": {
        "VBELN": ("outbound_order", "order_id"),
        "LFSTK": ("outbound_order", "delivery_status"),
        "WBSTK": ("outbound_order", "goods_movement_status"),
        "FKSTK": ("outbound_order", "billing_status"),
        "GBSTK": ("outbound_order", "overall_status"),
        "ABSTK": ("outbound_order", "rejection_status"),
        "KOSTK": ("outbound_order", "overall_picking_status"),
    },
    "VBUP": {
        "VBELN": ("outbound_order", "order_id"),
        "POSNR": ("outbound_order", "line_number"),
        "LFSTA": ("outbound_order", "delivery_status"),
        "WBSTA": ("outbound_order", "goods_movement_status"),
        "FKSTA": ("outbound_order", "billing_status"),
        "GBSTA": ("outbound_order", "overall_status"),
        "ABSTA": ("outbound_order", "rejection_status"),
        "KOSTA": ("outbound_order", "overall_picking_status"),
    },
    # ── Deliveries ────────────────────────────────────────────────────────
    "LIKP": {
        "VBELN": ("outbound_order", "delivery_id"),
        "LFART": ("outbound_order", "delivery_type"),
        "WADAT": ("outbound_order", "planned_goods_issue_date"),
        "WADAT_IST": ("outbound_order", "actual_goods_issue_date"),
        "LDDAT": ("outbound_order", "loading_date"),
        "LFDAT": ("outbound_order", "delivery_date"),
        "ROUTE": ("outbound_order", "route"),
        "BTGEW": ("outbound_order", "gross_weight"),
        "NTGEW": ("outbound_order", "net_weight"),
        "VOLUM": ("outbound_order", "volume"),
        "GEWEI": ("outbound_order", "weight_uom"),
        "VOLEH": ("outbound_order", "volume_uom"),
        "KUNNR": ("outbound_order", "customer_id"),
        "LIFNR": ("outbound_order", "vendor_id"),
        "VSTEL": ("outbound_order", "shipping_point"),
        "VKORG": ("outbound_order", "sales_org"),
    },
    "LIPS": {
        "VBELN": ("outbound_order", "delivery_id"),
        "POSNR": ("outbound_order", "delivery_line"),
        "MATNR": ("outbound_order", "product_id"),
        "WERKS": ("outbound_order", "ship_from_site_id"),
        "LGORT": ("outbound_order", "storage_location"),
        "LFIMG": ("outbound_order", "delivered_quantity"),
        "MEINS": ("outbound_order", "uom"),
        "VGBEL": ("outbound_order", "reference_order_id"),
        "VGPOS": ("outbound_order", "reference_line"),
        "PSTYV": ("outbound_order", "item_category"),
    },
    # ── Production Orders ─────────────────────────────────────────────────
    "AFKO": {
        "AUFNR": ("production_order", "order_id"),
        "RSNUM": ("production_order", "reservation_number"),
        "PLNBEZ": ("production_order", "product_id"),
        "GAMNG": ("production_order", "order_quantity"),
        "GMEIN": ("production_order", "uom"),
        "GSTRS": ("production_order", "scheduled_start"),
        "GSTRP": ("production_order", "scheduled_start_date"),
        "FTRMS": ("production_order", "scheduled_release"),
        "GLTRP": ("production_order", "end_date"),
        "GLTRS": ("production_order", "scheduled_finish"),
        "PLNTY": ("production_order", "task_list_type"),
        "PLNNR": ("production_order", "routing_number"),
    },
    "AFPO": {
        "AUFNR": ("production_order", "order_id"),
        "POSNR": ("production_order", "line_number"),
        "MATNR": ("production_order", "product_id"),
        "MEINS": ("production_order", "uom"),
        "PSMNG": ("production_order", "order_quantity"),
        "WEMNG": ("production_order", "goods_received_quantity"),
        "LTRMI": ("production_order", "end_date"),
        "LTRMP": ("production_order", "start_date"),
    },
    "AFVC": {
        "AUFPL": ("production_order", "routing_number"),
        "APLZL": ("production_order", "operation_counter"),
        "VORNR": ("production_order", "operation_number"),
        "ARBID": ("production_order", "work_center_id"),
        "WERKS": ("production_order", "site_id"),
        "STEUS": ("production_order", "control_key"),
        "LTXA1": ("production_order", "operation_description"),
        "LIFNR": ("production_order", "subcontractor_id"),
        "PREIS": ("production_order", "external_processing_price"),
        "WAERS": ("production_order", "currency"),
    },
    "AUFK": {
        "AUFNR": ("production_order", "order_id"),
        "AUART": ("production_order", "order_type"),
        "AUTYP": ("production_order", "order_category"),
        "WERKS": ("production_order", "site_id"),
        "ERDAT": ("production_order", "created_date"),
        "BUKRS": ("production_order", "company_id"),
        "KTEXT": ("production_order", "description"),
        "OBJNR": ("production_order", "object_number"),
        "WAERS": ("production_order", "currency"),
    },
    "RESB": {
        "RSNUM": ("production_order", "reservation_number"),
        "RSPOS": ("production_order", "reservation_item"),
        "MATNR": ("production_order", "component_id"),
        "WERKS": ("production_order", "site_id"),
        "LGORT": ("production_order", "storage_location"),
        "BDMNG": ("production_order", "required_quantity"),
        "MEINS": ("production_order", "uom"),
        "BDTER": ("production_order", "requirement_date"),
        "AUFNR": ("production_order", "order_id"),
        "XWAOK": ("production_order", "goods_movement_complete"),
        "ENMNG": ("production_order", "withdrawn_quantity"),
    },
    # ── BOM ────────────────────────────────────────────────────────────────
    "STKO": {
        "STLNR": ("product", "bom_id"),
        "STLAL": ("product", "bom_alternative"),
        "STLTY": ("product", "bom_type"),
        "STLST": ("product", "bom_status"),
        "BMENG": ("product", "base_quantity"),
        "BMEIN": ("product", "base_uom"),
        "STKTX": ("product", "bom_description"),
        "DATUV": ("product", "valid_from"),
        "LOEKZ": ("product", "deletion_indicator"),
    },
    "STPO": {
        "STLNR": ("product", "bom_id"),
        "STLKN": ("product", "bom_node"),
        "STPOZ": ("product", "bom_item_counter"),
        "IDNRK": ("product", "component_id"),
        "MENGE": ("product", "component_quantity"),
        "MEINS": ("product", "component_uom"),
        "POSTP": ("product", "item_category"),
        "POSNR": ("product", "bom_item_number"),
        "SORTF": ("product", "sort_string"),
        "AUSCH": ("product", "scrap_rate"),
    },
    # ── Routings / Production Process ─────────────────────────────────────
    "PLKO": {
        "PLNTY": ("production_order", "task_list_type"),
        "PLNNR": ("production_order", "routing_number"),
        "PLNAL": ("production_order", "routing_group_counter"),
        "WERKS": ("production_order", "site_id"),
        "STATU": ("production_order", "routing_status"),
        "LOEKZ": ("production_order", "deletion_indicator"),
        "PLNME": ("production_order", "routing_uom"),
        "VERWE": ("production_order", "routing_usage"),
        "KTEXT": ("production_order", "routing_description"),
    },
    "PLPO": {
        "PLNTY": ("production_order", "task_list_type"),
        "PLNNR": ("production_order", "routing_number"),
        "PLNKN": ("production_order", "routing_node"),
        "VORNR": ("production_order", "operation_number"),
        "ARBID": ("production_order", "work_center_id"),
        "STEUS": ("production_order", "control_key"),
        "VGW01": ("production_order", "setup_time"),
        "VGW02": ("production_order", "machine_time"),
        "VGW03": ("production_order", "labor_time"),
        "VGE01": ("production_order", "setup_time_uom"),
        "VGE02": ("production_order", "machine_time_uom"),
        "VGE03": ("production_order", "labor_time_uom"),
        "BMSCH": ("production_order", "base_quantity"),
    },
    "CRHD": {
        "OBJID": ("production_order", "work_center_id"),
        "ARBPL": ("production_order", "work_center_name"),
        "WERKS": ("production_order", "site_id"),
        "VERWE": ("production_order", "work_center_usage"),
        "OBJTY": ("production_order", "object_type"),
    },
    # ── Forecasts / PIR ───────────────────────────────────────────────────
    "PBIM": {
        "BDZEI": ("forecast", "forecast_id"),
        "BEDAE": ("forecast", "requirements_type"),
        "VERSB": ("forecast", "forecast_version"),
        "MATNR": ("forecast", "product_id"),
        "WERKS": ("forecast", "site_id"),
        "PBDNR": ("forecast", "requirement_plan_number"),
    },
    "PBED": {
        "BDZEI": ("forecast", "forecast_id"),
        "PDATU": ("forecast", "forecast_date"),
        "PLNMG": ("forecast", "forecast_quantity"),
        "MEINS": ("forecast", "uom"),
        "ENTMG": ("forecast", "consumed_quantity"),
    },
    # ── MRP / Planned Orders ──────────────────────────────────────────────
    "PLAF": {
        "PLNUM": ("supply_plan", "plan_id"),
        "MATNR": ("supply_plan", "product_id"),
        "PLWRK": ("supply_plan", "site_id"),
        "GSMNG": ("supply_plan", "planned_order_quantity"),
        "MEINS": ("supply_plan", "uom"),
        "PEDTR": ("supply_plan", "planned_order_date"),
        "PSTTR": ("supply_plan", "planned_receipt_date"),
        "STLFX": ("supply_plan", "is_firmed"),
        "PAART": ("supply_plan", "plan_type"),
        "BESKZ": ("supply_plan", "procurement_type"),
        "PLNTY": ("supply_plan", "task_list_type"),
        "DISPO": ("supply_plan", "mrp_controller"),
    },
    # ── Transfer Orders ───────────────────────────────────────────────────
    "LTAK": {
        "TANUM": ("transfer_order", "order_id"),
        "LGNUM": ("transfer_order", "warehouse_number"),
        "TBNUM": ("transfer_order", "transfer_requirement"),
        "BWART": ("transfer_order", "movement_type"),
        "BWLVS": ("transfer_order", "wm_movement_type"),
        "BDATU": ("transfer_order", "requirement_date"),
        "BZEIT": ("transfer_order", "requirement_time"),
        "LZNUM": ("transfer_order", "group_number"),
        "BETYP": ("transfer_order", "reference_type"),
        "BENUM": ("transfer_order", "reference_number"),
        "TRART": ("transfer_order", "transfer_type"),
        "STDAT": ("transfer_order", "start_date"),
        "ENDAT": ("transfer_order", "end_date"),
    },
    "LTAP": {
        "LGNUM": ("transfer_order", "warehouse_number"),
        "TANUM": ("transfer_order", "order_id"),
        "TAPOS": ("transfer_order", "line_number"),
        "MATNR": ("transfer_order", "product_id"),
        "WERKS": ("transfer_order", "site_id"),
        "LGORT": ("transfer_order", "storage_location"),
        "VLTYP": ("transfer_order", "source_bin_type"),
        "VLPLA": ("transfer_order", "source_bin"),
        "NLTYP": ("transfer_order", "destination_bin_type"),
        "NLPLA": ("transfer_order", "destination_bin"),
        "VSOLM": ("transfer_order", "source_target_quantity"),
        "NSOLM": ("transfer_order", "destination_target_quantity"),
        "VISTM": ("transfer_order", "source_actual_quantity"),
        "NISTM": ("transfer_order", "destination_actual_quantity"),
        "MEINS": ("transfer_order", "uom"),
    },
    # ── Quality Management ────────────────────────────────────────────────
    "QMEL": {
        "QMNUM": ("quality_order", "order_id"),
        "QMART": ("quality_order", "inspection_type"),
        "MATNR": ("quality_order", "product_id"),
        "ERDAT": ("quality_order", "created_date"),
        "PRIOK": ("quality_order", "priority"),
        "STRMN": ("quality_order", "planned_start"),
        "LTRMN": ("quality_order", "planned_end"),
        "QMTXT": ("quality_order", "description"),
        "AUFNR": ("quality_order", "production_order_ref"),
    },
    "QALS": {
        "PRUEFLOS": ("quality_order", "lot_number"),
        "MATNR": ("quality_order", "product_id"),
        "WERK": ("quality_order", "site_id"),
        "ART": ("quality_order", "inspection_type"),
        "HERKUNFT": ("quality_order", "origin"),
        "BEARBSTATU": ("quality_order", "status"),
        "ENSTEHDAT": ("quality_order", "inspection_date"),
        "ENTSTEZEIT": ("quality_order", "inspection_time"),
        "PASTRTERM": ("quality_order", "planned_start"),
        "PAENDTERM": ("quality_order", "planned_end"),
        "LOSMENGE": ("quality_order", "lot_size"),
        "MENGENEINH": ("quality_order", "uom"),
        "AUFNR": ("quality_order", "production_order_ref"),
        "CHARG": ("quality_order", "batch"),
        "INSMK": ("quality_order", "stock_posting"),
    },
    "QASE": {
        "PRUEFLOS": ("quality_order", "lot_number"),
        "VORGLFNR": ("quality_order", "operation_number"),
        "MERKNR": ("quality_order", "characteristic_number"),
        "MESSWERT": ("quality_order", "measured_value"),
        "MBEWERTG": ("quality_order", "valuation"),
        "ANZFEHLER": ("quality_order", "defect_count"),
        "CODE1": ("quality_order", "code"),
        "VERSION1": ("quality_order", "catalog_version"),
        "ERSTELLDAT": ("quality_order", "created_date"),
        "PRUEFER": ("quality_order", "inspector"),
    },
    # ── Maintenance / Equipment ───────────────────────────────────────────
    "EQUI": {
        "EQUNR": ("maintenance_order", "asset_id"),
        "EQART": ("maintenance_order", "equipment_type"),
        "ERDAT": ("maintenance_order", "created_date"),
        "ANSDT": ("maintenance_order", "startup_date"),
        "ANSWT": ("maintenance_order", "acquisition_value"),
        "WAERS": ("maintenance_order", "currency"),
        "HERST": ("maintenance_order", "manufacturer"),
        "SERGE": ("maintenance_order", "serial_number"),
        "TYPBZ": ("maintenance_order", "model_number"),
        "BRGEW": ("maintenance_order", "weight"),
        "GEWEI": ("maintenance_order", "weight_uom"),
    },
    # ── Goods Movements ───────────────────────────────────────────────────
    "MKPF": {
        "MBLNR": ("inv_level", "document_number"),
        "MJAHR": ("inv_level", "document_year"),
        "BLDAT": ("inv_level", "document_date"),
        "BUDAT": ("inv_level", "posting_date"),
        "BKTXT": ("inv_level", "header_text"),
        "USNAM": ("inv_level", "user_name"),
        "XBLNR": ("inv_level", "reference_document"),
    },
    "MSEG": {
        "MBLNR": ("inv_level", "document_number"),
        "MJAHR": ("inv_level", "document_year"),
        "ZEILE": ("inv_level", "line_number"),
        "BWART": ("inv_level", "movement_type"),
        "MATNR": ("inv_level", "product_id"),
        "WERKS": ("inv_level", "site_id"),
        "LGORT": ("inv_level", "storage_location"),
        "MENGE": ("inv_level", "quantity"),
        "MEINS": ("inv_level", "uom"),
        "SHKZG": ("inv_level", "debit_credit"),
        "AUFNR": ("inv_level", "order_reference"),
        "EBELN": ("inv_level", "po_number"),
        "EBELP": ("inv_level", "po_line"),
        "LIFNR": ("inv_level", "vendor_id"),
        "KUNNR": ("inv_level", "customer_id"),
        "KDAUF": ("inv_level", "sales_order"),
        "SOBKZ": ("inv_level", "special_stock"),
        "DMBTR": ("inv_level", "amount_local_currency"),
        "BUDAT_MKPF": ("inv_level", "posting_date"),
    },
    # ── Status / Support ──────────────────────────────────────────────────
    "JEST": {
        "OBJNR": ("production_order", "object_number"),
        "STAT": ("production_order", "status_code"),
        "INACT": ("production_order", "status_inactive"),
    },
    "TJ02T": {
        "ISTAT": ("production_order", "status_code"),
        "SPRAS": ("production_order", "language"),
        "TXT04": ("production_order", "status_short_text"),
        "TXT30": ("production_order", "status_long_text"),
    },
}


# Common SAP field name patterns and their AWS SC equivalents
SAP_FIELD_PATTERNS = {
    # Material/Product patterns
    r"^(Z_)?MAT(NR|ERIAL)?$": ("product", "product_id"),
    r"^(Z_)?MAKTX?$": ("product", "product_name"),
    r"^(Z_)?MATKL$": ("product", "product_group"),
    r"^(Z_)?MEINS$": ("product", "base_uom"),

    # Plant/Site patterns
    r"^(Z_)?WERKS?$": ("site", "site_id"),
    r"^(Z_)?PLANT$": ("site", "site_id"),
    r"^(Z_)?NAME1?$": ("site", "site_name"),
    r"^(Z_)?LAND1?$": ("site", "country"),

    # Quantity/Inventory patterns
    r"^(Z_)?LABST$": ("inv_level", "quantity"),
    r"^(Z_)?(QUAN|QTY|MENGE)$": ("inv_level", "quantity"),
    r"^(Z_)?STOCK$": ("inv_level", "quantity"),
    r"^(Z_)?LGORT$": ("inv_level", "storage_location"),

    # Vendor/Customer patterns
    r"^(Z_)?LIFNR$": ("trading_partner", "partner_id"),
    r"^(Z_)?KUNNR$": ("trading_partner", "partner_id"),
    r"^(Z_)?VENDOR$": ("trading_partner", "partner_id"),
    r"^(Z_)?CUSTOMER$": ("trading_partner", "partner_id"),

    # Order patterns
    r"^(Z_)?EBELN$": ("inbound_order", "order_id"),
    r"^(Z_)?VBELN$": ("outbound_order", "order_id"),
    r"^(Z_)?AUFNR$": ("production_order", "order_id"),
    r"^(Z_)?BSTNR$": ("inbound_order", "customer_po"),

    # Date patterns
    r"^(Z_)?(ERDAT|AEDAT|BEDAT)$": ("*", "order_date"),
    r"^(Z_)?LFDAT$": ("*", "delivery_date"),
    r"^(Z_)?EINDT$": ("*", "requested_date"),

    # Company patterns
    r"^(Z_)?BUKRS$": ("company", "company_id"),
    r"^(Z_)?VKORG$": ("company", "sales_org"),

    # Transfer Order patterns
    r"^(Z_)?LGNUM$": ("transfer_order", "warehouse_number"),
    r"^(Z_)?TESSION$": ("transfer_order", "order_id"),
    r"^(Z_)?NLTYP$": ("transfer_order", "destination_bin_type"),
    r"^(Z_)?VLTYP$": ("transfer_order", "source_bin_type"),

    # Quality Order patterns
    r"^(Z_)?QMNUM$": ("quality_order", "order_id"),
    r"^(Z_)?QMART$": ("quality_order", "inspection_type"),
    r"^(Z_)?QMGRP$": ("quality_order", "code_group"),
    r"^(Z_)?QMCOD$": ("quality_order", "code"),
    r"^(Z_)?PRIOK$": ("quality_order", "priority"),
    r"^(Z_)?RKMNG$": ("quality_order", "defect_quantity"),
    r"^(Z_)?MGEIN$": ("quality_order", "complaint_uom"),

    # Maintenance Order patterns
    r"^(Z_)?EQUNR$": ("maintenance_order", "asset_id"),
    r"^(Z_)?ILART$": ("maintenance_order", "maintenance_type"),
    r"^(Z_)?IWERK$": ("maintenance_order", "site_id"),
    r"^(Z_)?WARPL$": ("maintenance_order", "maintenance_plan"),
    r"^(Z_)?ANLNR$": ("maintenance_order", "fixed_asset_number"),

    # Subcontracting patterns
    r"^(Z_)?BSART$": ("subcontracting_order", "order_type"),
    r"^(Z_)?REPOS$": ("subcontracting_order", "invoice_receipt"),
    r"^(Z_)?MKAL$": ("subcontracting_order", "production_version"),
    r"^(Z_)?LOHNV$": ("subcontracting_order", "subcontracting_flag"),

    # --- Config Builder patterns ---

    # Purchasing Info Record / Vendor Product patterns
    r"^(Z_)?INFNR$": ("vendor_product", "info_record"),
    r"^(Z_)?NETPR$": ("vendor_product", "net_price"),
    r"^(Z_)?APLFZ$": ("vendor_lead_time", "planned_delivery_time"),
    r"^(Z_)?NORBM$": ("vendor_product", "standard_order_qty"),
    r"^(Z_)?MINBM$": ("vendor_product", "min_order_qty"),
    r"^(Z_)?EKORG$": ("vendor_lead_time", "purchasing_org"),

    # Source List / Sourcing Rules patterns
    r"^(Z_)?NOTKZ$": ("sourcing_rules", "source_usage"),
    r"^(Z_)?FLIFN$": ("sourcing_rules", "fixed_vendor"),
    r"^(Z_)?BESKZ$": ("sourcing_rules", "procurement_type"),
    r"^(Z_)?SOBSL$": ("sourcing_rules", "special_procurement_type"),

    # Company / Address patterns
    r"^(Z_)?BUTXT$": ("company", "company_name"),
    r"^(Z_)?ADDRNUMBER$": ("geography", "address_id"),
    r"^(Z_)?POST_CODE1?$": ("geography", "postal_code"),
    r"^(Z_)?CITY1?$": ("geography", "city"),
    r"^(Z_)?REGION$": ("geography", "region"),
    r"^(Z_)?COUNTRY$": ("geography", "country"),

    # Product Hierarchy / Sales Data patterns
    r"^(Z_)?PRODH$": ("product", "product_hierarchy"),
    r"^(Z_)?MVKE$": ("product", "sales_data"),
    r"^(Z_)?KONDM$": ("product", "pricing_group"),

    # Routing / Production Process patterns
    r"^(Z_)?PLNTY$": ("production_process", "task_list_type"),
    r"^(Z_)?PLNNR$": ("production_process", "process_id"),
    r"^(Z_)?PLNKN$": ("production_process", "operation_number"),
    r"^(Z_)?ARBID$": ("production_process", "work_center_id"),
    r"^(Z_)?ARBPL$": ("production_process", "work_center_name"),
    r"^(Z_)?VGW01$": ("production_process", "setup_time"),
    r"^(Z_)?VGW02$": ("production_process", "machine_time"),
    r"^(Z_)?VGW03$": ("production_process", "labor_time"),
    r"^(Z_)?STEUS$": ("production_process", "control_key"),

    # BOM Header patterns
    r"^(Z_)?STLNR$": ("product_bom", "bom_number"),
    r"^(Z_)?STLAL$": ("product_bom", "alternative"),
    r"^(Z_)?BMENG$": ("product_bom", "base_quantity"),

    # UOM Conversion patterns
    r"^(Z_)?MEINH$": ("product", "alt_uom"),
    r"^(Z_)?UMREZ$": ("product", "uom_numerator"),
    r"^(Z_)?UMREN$": ("product", "uom_denominator"),

    # Transportation Lane / APO patterns
    r"^(Z_)?LOCFR$": ("transportation_lane", "source_site_id"),
    r"^(Z_)?LOCTO$": ("transportation_lane", "destination_site_id"),
    r"^(Z_)?TRANSTIME$": ("transportation_lane", "lead_time_days"),
    r"^(Z_)?TRANSCOST$": ("transportation_lane", "cost_per_unit"),
    r"^(Z_)?TRANSMODE$": ("transportation_lane", "transport_mode"),

    # Resource Capacity patterns
    r"^(Z_)?OBJID$": ("resource_capacity", "resource_id"),

    # Customer Segmentation / Market patterns
    r"^(Z_)?KDGRP$": ("market", "customer_group"),
    r"^(Z_)?BZIRK$": ("market", "sales_district"),
    r"^(Z_)?VTWEG$": ("market", "distribution_channel"),
    r"^(Z_)?SPART$": ("market", "division"),

    # --- MRP Planning patterns (MDKP, MDTB, PLAF) ---
    r"^(Z_)?DTART$": ("supply_plan", "mrp_type"),
    r"^(Z_)?PLNUM$": ("supply_plan", "plan_id"),
    r"^(Z_)?DELKZ$": ("supply_plan", "mrp_element_indicator"),
    r"^(Z_)?DESSION$": ("supply_plan", "mrp_element_type"),
    r"^(Z_)?GTEFH$": ("supply_plan", "planned_order_date"),
    r"^(Z_)?PEDTR$": ("supply_plan", "planned_order_date"),
    r"^(Z_)?PSTTR$": ("supply_plan", "planned_receipt_date"),
    r"^(Z_)?PLAUF$": ("supply_plan", "planned_order_quantity"),
    r"^(Z_)?GESSION$": ("supply_plan", "planned_order_quantity"),
    r"^(Z_)?VEESSION$": ("supply_plan", "plan_version"),
    r"^(Z_)?STLFX$": ("supply_plan", "is_firmed"),
    r"^(Z_)?UMESSION$": ("supply_plan", "conversion_status"),

    # Purchase Requisition patterns (EBAN)
    r"^(Z_)?BANFN$": ("purchase_requisition", "requisition_id"),
    r"^(Z_)?BNFPO$": ("purchase_requisition", "line_number"),
    r"^(Z_)?EKGRP$": ("purchase_requisition", "purchasing_group"),
    r"^(Z_)?FRGKZ$": ("purchase_requisition", "release_indicator"),
    r"^(Z_)?FRGZU$": ("purchase_requisition", "release_status"),
    r"^(Z_)?LOEKZ$": ("purchase_requisition", "deletion_indicator"),
    r"^(Z_)?BADAT$": ("purchase_requisition", "requisition_date"),
    r"^(Z_)?PREIS$": ("purchase_requisition", "price"),

    # MARC MRP / Inventory Policy patterns
    r"^(Z_)?DISMM$": ("inv_policy", "mrp_type"),
    r"^(Z_)?DISPO$": ("inv_policy", "mrp_controller"),
    r"^(Z_)?DISLS$": ("inv_policy", "lot_size_procedure"),
    r"^(Z_)?EISBE$": ("inv_policy", "ss_quantity"),
    r"^(Z_)?MINBE$": ("inv_policy", "reorder_point"),
    r"^(Z_)?BSTRF$": ("inv_policy", "fixed_order_quantity"),
    r"^(Z_)?BSTMI$": ("inv_policy", "min_order_quantity"),
    r"^(Z_)?BSTMA$": ("inv_policy", "max_order_quantity"),
    r"^(Z_)?PLIFZ$": ("inv_policy", "planned_delivery_time"),
    r"^(Z_)?WEBAZ$": ("inv_policy", "gr_processing_time"),
    r"^(Z_)?FHORI$": ("inv_policy", "scheduling_margin_key"),
    r"^(Z_)?MABST$": ("inv_policy", "order_up_to_level"),

    # Forecast Table patterns (PBIM, MPOP)
    r"^(Z_)?BEDAE$": ("forecast", "requirements_type"),
    r"^(Z_)?VERSB$": ("forecast", "forecast_version"),
    r"^(Z_)?BESSION$": ("forecast", "forecast_quantity"),
    r"^(Z_)?PRESSION$": ("forecast", "forecast_profile"),
    r"^(Z_)?MODELL$": ("forecast", "forecast_method"),
    r"^(Z_)?PERTYP$": ("forecast", "period_type"),
    r"^(Z_)?PEESSION$": ("forecast", "period_length"),
    r"^(Z_)?PESSION$": ("forecast", "num_periods"),
    r"^(Z_)?KOESSION$": ("forecast", "correction_factor"),

    # Supporting table patterns (T001L, MAKT, T024E)
    r"^(Z_)?SPRAS$": ("product", "language_key"),
    r"^(Z_)?LGOBE$": ("site", "storage_location_desc"),

    # User / Authorization patterns (SAP user import)
    r"^(Z_)?BNAME$": ("sap_user", "sap_username"),
    r"^(Z_)?SMTP_ADDR$": ("sap_user", "email"),
    r"^(Z_)?NAME_FIRST$": ("sap_user", "first_name"),
    r"^(Z_)?NAME_LAST$": ("sap_user", "last_name"),
    r"^(Z_)?USTYP$": ("sap_user", "user_type"),
    r"^(Z_)?GLTGV$": ("sap_user", "valid_from"),
    r"^(Z_)?GLTGB$": ("sap_user", "valid_to"),
    r"^(Z_)?CLASS$": ("sap_user", "account_class"),
    r"^(Z_)?AGR_NAME$": ("sap_role", "role_name"),
    r"^(Z_)?AGR_TEXT$": ("sap_role", "role_description"),
    r"^(Z_)?FROM_DAT$": ("sap_role", "valid_from"),
    r"^(Z_)?TO_DAT$": ("sap_role", "valid_to"),
    r"^(Z_)?OBJECT$": ("sap_authorization", "auth_object"),
    r"^(Z_)?TCODE$": ("sap_authorization", "tcode"),
    r"^(Z_)?LOW$": ("sap_authorization", "value_low"),
    r"^(Z_)?HIGH$": ("sap_authorization", "value_high"),
}

# AWS SC entity field definitions (expanded)
AWS_SC_FIELDS = {
    "product": {
        "product_id": {"type": "string", "required": True, "description": "Unique product identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "product_name": {"type": "string", "required": False, "description": "Product name/description"},
        "description": {"type": "string", "required": False, "description": "Long description"},
        "product_group": {"type": "string", "required": False, "description": "Product group/category"},
        "base_uom": {"type": "string", "required": False, "description": "Base unit of measure"},
        "status": {"type": "string", "required": False, "description": "Product status"},
        "weight": {"type": "decimal", "required": False, "description": "Product weight"},
        "volume": {"type": "decimal", "required": False, "description": "Product volume"},
    },
    "site": {
        "site_id": {"type": "string", "required": True, "description": "Unique site identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_name": {"type": "string", "required": False, "description": "Site name"},
        "site_type": {"type": "string", "required": False, "description": "Type of site (DC, Plant, etc.)"},
        "address": {"type": "string", "required": False, "description": "Street address"},
        "city": {"type": "string", "required": False, "description": "City"},
        "country": {"type": "string", "required": False, "description": "Country code"},
        "region": {"type": "string", "required": False, "description": "Region/state"},
    },
    "inv_level": {
        "site_id": {"type": "string", "required": True, "description": "Site identifier"},
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "quantity": {"type": "decimal", "required": True, "description": "Inventory quantity"},
        "uom": {"type": "string", "required": False, "description": "Unit of measure"},
        "storage_location": {"type": "string", "required": False, "description": "Storage location"},
        "snapshot_date": {"type": "date", "required": True, "description": "Snapshot date"},
        "lot_number": {"type": "string", "required": False, "description": "Lot/batch number"},
    },
    "trading_partner": {
        "partner_id": {"type": "string", "required": True, "description": "Partner identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "partner_type": {"type": "string", "required": True, "description": "Vendor or Customer"},
        "partner_name": {"type": "string", "required": False, "description": "Partner name"},
        "address": {"type": "string", "required": False, "description": "Address"},
        "country": {"type": "string", "required": False, "description": "Country"},
    },
    "inbound_order": {
        "order_id": {"type": "string", "required": True, "description": "Order identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "order_type": {"type": "string", "required": True, "description": "Order type (PO, STO, etc.)"},
        "supplier_id": {"type": "string", "required": True, "description": "Supplier identifier"},
        "site_id": {"type": "string", "required": True, "description": "Receiving site"},
        "order_date": {"type": "date", "required": True, "description": "Order creation date"},
        "delivery_date": {"type": "date", "required": False, "description": "Expected delivery"},
        "customer_po": {"type": "string", "required": False, "description": "Customer PO reference"},
    },
    "outbound_order": {
        "order_id": {"type": "string", "required": True, "description": "Order identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "customer_id": {"type": "string", "required": True, "description": "Customer identifier"},
        "ship_from_site_id": {"type": "string", "required": True, "description": "Shipping site"},
        "order_date": {"type": "date", "required": True, "description": "Order creation date"},
        "requested_date": {"type": "date", "required": False, "description": "Customer requested date"},
    },
    "forecast": {
        "site_id": {"type": "string", "required": True, "description": "Site identifier"},
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "forecast_date": {"type": "date", "required": True, "description": "Forecast period date"},
        "forecast_quantity": {"type": "decimal", "required": True, "description": "Forecasted quantity"},
        "forecast_p10": {"type": "decimal", "required": False, "description": "10th percentile"},
        "forecast_p50": {"type": "decimal", "required": False, "description": "50th percentile (median)"},
        "forecast_p90": {"type": "decimal", "required": False, "description": "90th percentile"},
    },
    "production_order": {
        "order_id": {"type": "string", "required": True, "description": "Production order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_id": {"type": "string", "required": True, "description": "Production site"},
        "product_id": {"type": "string", "required": True, "description": "Product being produced"},
        "order_quantity": {"type": "decimal", "required": True, "description": "Order quantity"},
        "start_date": {"type": "date", "required": False, "description": "Planned start"},
        "end_date": {"type": "date", "required": False, "description": "Planned finish"},
    },
    "transfer_order": {
        "order_id": {"type": "string", "required": True, "description": "Transfer order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "source_site_id": {"type": "string", "required": True, "description": "Source site/warehouse"},
        "destination_site_id": {"type": "string", "required": True, "description": "Destination site/warehouse"},
        "product_id": {"type": "string", "required": True, "description": "Product being transferred"},
        "quantity": {"type": "decimal", "required": True, "description": "Transfer quantity"},
        "status": {"type": "string", "required": False, "description": "Order status"},
        "ship_date": {"type": "date", "required": False, "description": "Shipment date"},
        "arrival_date": {"type": "date", "required": False, "description": "Expected arrival date"},
        "transportation_mode": {"type": "string", "required": False, "description": "Mode of transport"},
        "warehouse_number": {"type": "string", "required": False, "description": "Warehouse complex number"},
    },
    "quality_order": {
        "order_id": {"type": "string", "required": True, "description": "Quality notification/order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_id": {"type": "string", "required": True, "description": "Inspection site"},
        "product_id": {"type": "string", "required": True, "description": "Product being inspected"},
        "inspection_type": {"type": "string", "required": True, "description": "Type of inspection (incoming/in-process/final)"},
        "lot_number": {"type": "string", "required": False, "description": "Inspection lot number"},
        "lot_size": {"type": "decimal", "required": False, "description": "Total lot size"},
        "sample_size": {"type": "decimal", "required": False, "description": "Sample size inspected"},
        "defect_count": {"type": "integer", "required": False, "description": "Number of defects found"},
        "defect_quantity": {"type": "decimal", "required": False, "description": "Defective quantity"},
        "disposition": {"type": "string", "required": False, "description": "Disposition decision"},
        "status": {"type": "string", "required": False, "description": "Order status"},
        "priority": {"type": "string", "required": False, "description": "Priority level"},
        "inspection_date": {"type": "date", "required": False, "description": "Inspection date"},
        "code_group": {"type": "string", "required": False, "description": "Catalog code group"},
        "code": {"type": "string", "required": False, "description": "Catalog code"},
    },
    "maintenance_order": {
        "order_id": {"type": "string", "required": True, "description": "Maintenance order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_id": {"type": "string", "required": True, "description": "Maintenance plant"},
        "asset_id": {"type": "string", "required": True, "description": "Equipment/functional location"},
        "maintenance_type": {"type": "string", "required": True, "description": "Activity type (preventive/corrective/predictive)"},
        "priority": {"type": "string", "required": False, "description": "Priority level"},
        "status": {"type": "string", "required": False, "description": "Order status"},
        "planned_start": {"type": "date", "required": False, "description": "Planned start date"},
        "planned_end": {"type": "date", "required": False, "description": "Planned end date"},
        "actual_start": {"type": "date", "required": False, "description": "Actual start date"},
        "actual_end": {"type": "date", "required": False, "description": "Actual end date"},
        "estimated_duration_hours": {"type": "decimal", "required": False, "description": "Estimated duration"},
        "cost": {"type": "decimal", "required": False, "description": "Total cost"},
        "maintenance_plan": {"type": "string", "required": False, "description": "Linked maintenance plan ID"},
        "fixed_asset_number": {"type": "string", "required": False, "description": "Fixed asset reference"},
    },
    "subcontracting_order": {
        "order_id": {"type": "string", "required": True, "description": "Subcontracting order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_id": {"type": "string", "required": True, "description": "Ordering plant"},
        "subcontractor_id": {"type": "string", "required": True, "description": "Subcontractor vendor ID"},
        "product_id": {"type": "string", "required": True, "description": "Finished product"},
        "quantity": {"type": "decimal", "required": True, "description": "Order quantity"},
        "status": {"type": "string", "required": False, "description": "Order status"},
        "order_date": {"type": "date", "required": False, "description": "Order creation date"},
        "due_date": {"type": "date", "required": False, "description": "Due date for goods receipt"},
        "material_sent_date": {"type": "date", "required": False, "description": "Date components sent to subcontractor"},
        "goods_received_date": {"type": "date", "required": False, "description": "Date finished goods received back"},
        "unit_cost": {"type": "decimal", "required": False, "description": "Unit cost from subcontractor"},
        "order_type": {"type": "string", "required": False, "description": "PO category (L=subcontracting)"},
        "production_version": {"type": "string", "required": False, "description": "Production version reference"},
    },
    # --- Planning Entity Types ---
    "supply_plan": {
        "plan_id": {"type": "string", "required": True, "description": "Plan element identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "site_id": {"type": "string", "required": True, "description": "Site/plant identifier"},
        "plan_date": {"type": "date", "required": True, "description": "Planning date"},
        "plan_type": {"type": "string", "required": True, "description": "Plan type (po_request, mo_request, to_request, planned_order)"},
        "planned_order_quantity": {"type": "decimal", "required": False, "description": "Planned order quantity"},
        "planned_order_date": {"type": "date", "required": False, "description": "Planned order start date"},
        "planned_receipt_date": {"type": "date", "required": False, "description": "Planned receipt/finish date"},
        "demand_quantity": {"type": "decimal", "required": False, "description": "Gross demand quantity"},
        "supply_quantity": {"type": "decimal", "required": False, "description": "Confirmed supply quantity"},
        "opening_inventory": {"type": "decimal", "required": False, "description": "Opening inventory for period"},
        "closing_inventory": {"type": "decimal", "required": False, "description": "Projected closing inventory"},
        "safety_stock": {"type": "decimal", "required": False, "description": "Safety stock level"},
        "supplier_id": {"type": "string", "required": False, "description": "Preferred supplier"},
        "from_site_id": {"type": "string", "required": False, "description": "Source site for transfers"},
        "mrp_type": {"type": "string", "required": False, "description": "MRP type (PD, VB, VV, etc.)"},
        "mrp_controller": {"type": "string", "required": False, "description": "MRP controller code"},
        "lot_size_procedure": {"type": "string", "required": False, "description": "Lot sizing procedure"},
        "order_status": {"type": "string", "required": False, "description": "Plan element status"},
        "plan_version": {"type": "string", "required": False, "description": "Planning version"},
        "mrp_element_indicator": {"type": "string", "required": False, "description": "MRP element type indicator (DELKZ)"},
        "mrp_element_type": {"type": "string", "required": False, "description": "MRP element type description"},
        "is_firmed": {"type": "string", "required": False, "description": "Whether planned order is firmed"},
        "conversion_status": {"type": "string", "required": False, "description": "Conversion status to production/purchase order"},
    },
    "inv_policy": {
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "site_id": {"type": "string", "required": True, "description": "Site/plant identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "ss_policy": {"type": "string", "required": True, "description": "Safety stock policy type (abs_level, doc_dem, doc_fcst, sl)"},
        "ss_quantity": {"type": "decimal", "required": False, "description": "Safety stock quantity (EISBE)"},
        "ss_days": {"type": "integer", "required": False, "description": "Safety stock days of coverage"},
        "service_level": {"type": "decimal", "required": False, "description": "Target service level (0-1)"},
        "reorder_point": {"type": "decimal", "required": False, "description": "Reorder point (MINBE)"},
        "min_order_quantity": {"type": "decimal", "required": False, "description": "Minimum lot size (BSTMI)"},
        "max_order_quantity": {"type": "decimal", "required": False, "description": "Maximum lot size (BSTMA)"},
        "fixed_order_quantity": {"type": "decimal", "required": False, "description": "Rounding value/fixed lot (BSTRF)"},
        "order_up_to_level": {"type": "decimal", "required": False, "description": "Maximum stock level (MABST)"},
        "review_period": {"type": "integer", "required": False, "description": "Planning cycle in days"},
        "mrp_type": {"type": "string", "required": False, "description": "MRP type (DISMM - PD, VB, VV, etc.)"},
        "mrp_controller": {"type": "string", "required": False, "description": "MRP controller (DISPO)"},
        "lot_size_procedure": {"type": "string", "required": False, "description": "Lot sizing procedure (DISLS)"},
        "planned_delivery_time": {"type": "integer", "required": False, "description": "Planned delivery time in days (PLIFZ)"},
        "gr_processing_time": {"type": "integer", "required": False, "description": "Goods receipt processing time in days (WEBAZ)"},
        "scheduling_margin_key": {"type": "string", "required": False, "description": "Scheduling margin key (FHORI)"},
    },
    "purchase_requisition": {
        "requisition_id": {"type": "string", "required": True, "description": "Purchase requisition number (BANFN)"},
        "line_number": {"type": "string", "required": True, "description": "Line item number (BNFPO)"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "product_id": {"type": "string", "required": True, "description": "Material number"},
        "site_id": {"type": "string", "required": True, "description": "Plant"},
        "quantity": {"type": "decimal", "required": True, "description": "Requisition quantity"},
        "delivery_date": {"type": "date", "required": False, "description": "Requested delivery date"},
        "release_date": {"type": "date", "required": False, "description": "Release date"},
        "requisition_type": {"type": "string", "required": False, "description": "Document type"},
        "purchasing_group": {"type": "string", "required": False, "description": "Purchasing group (EKGRP)"},
        "purchasing_org": {"type": "string", "required": False, "description": "Purchasing organization"},
        "supplier_id": {"type": "string", "required": False, "description": "Preferred vendor"},
        "price": {"type": "decimal", "required": False, "description": "Valuation price"},
        "status": {"type": "string", "required": False, "description": "Processing status"},
        "source_plan_id": {"type": "string", "required": False, "description": "Source planned order reference"},
        "release_indicator": {"type": "string", "required": False, "description": "Release indicator (FRGKZ)"},
        "release_status": {"type": "string", "required": False, "description": "Release status (FRGZU)"},
        "deletion_indicator": {"type": "string", "required": False, "description": "Deletion indicator (LOEKZ)"},
        "requisition_date": {"type": "date", "required": False, "description": "Requisition date (BADAT)"},
    },
    # --- SAP User / Role / Authorization entities (SC-filtered import) ---
    "sap_user": {
        "sap_username": {"type": "string", "required": True, "description": "SAP username (BNAME from USR02)"},
        "email": {"type": "string", "required": False, "description": "Email address (SMTP_ADDR from ADRP)"},
        "first_name": {"type": "string", "required": False, "description": "First name (NAME_FIRST from ADRP)"},
        "last_name": {"type": "string", "required": False, "description": "Last name (NAME_LAST from ADRP)"},
        "user_type": {"type": "string", "required": False, "description": "SAP user type: A=Dialog, B=System, C=Comms, S=Service (USTYP)"},
        "valid_from": {"type": "date", "required": False, "description": "Account valid from date (GLTGV)"},
        "valid_to": {"type": "date", "required": False, "description": "Account valid to date (GLTGB)"},
        "account_class": {"type": "string", "required": False, "description": "User group/class (CLASS from USR02)"},
    },
    "sap_role": {
        "role_name": {"type": "string", "required": True, "description": "SAP role name (AGR_NAME from AGR_DEFINE)"},
        "role_description": {"type": "string", "required": False, "description": "Role description text (TEXT from AGR_DEFINE)"},
        "assigned_user": {"type": "string", "required": False, "description": "Assigned user (UNAME from AGR_USERS)"},
        "valid_from": {"type": "date", "required": False, "description": "Assignment valid from (FROM_DAT)"},
        "valid_to": {"type": "date", "required": False, "description": "Assignment valid to (TO_DAT)"},
    },
    "sap_authorization": {
        "role_name": {"type": "string", "required": True, "description": "Role containing this authorization (AGR_NAME)"},
        "auth_object": {"type": "string", "required": False, "description": "Authorization object name (OBJECT from AGR_1251)"},
        "field_name": {"type": "string", "required": False, "description": "Auth object field name (FIELD from AGR_1251)"},
        "value_low": {"type": "string", "required": False, "description": "Lower bound value (LOW from AGR_1251)"},
        "value_high": {"type": "string", "required": False, "description": "Upper bound value (HIGH from AGR_1251)"},
        "tcode": {"type": "string", "required": False, "description": "Transaction code (TCODE from AGR_TCODES)"},
    },
}


class SAPFieldMappingService:
    """
    Service for intelligent mapping of SAP fields to AWS SC entities.

    Uses multiple strategies:
    1. Exact match - Direct field name matching
    2. Pattern match - Regex patterns for common SAP conventions
    3. Fuzzy match - String similarity for variations
    4. AI analysis - Claude for complex/ambiguous cases
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self._mapping_history: Dict[str, str] = {}  # sap_field -> aws_field
        self._learned_mappings: Dict[str, Tuple[str, str]] = {}  # sap_field -> (entity, field)
        self._openai_client = None

    async def _get_openai_client(self):
        """Get or create OpenAI-compatible async client for AI-powered suggestions."""
        if self._openai_client is None:
            try:
                from openai import AsyncOpenAI
                import os
                base_url = os.environ.get("LLM_API_BASE")
                api_key = (
                    os.environ.get("LLM_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                    or "not-needed"
                )
                kwargs = {"api_key": api_key}
                if base_url:
                    kwargs["base_url"] = base_url
                if base_url or api_key != "not-needed":
                    self._openai_client = AsyncOpenAI(**kwargs)
            except ImportError:
                logger.warning("openai package not available for AI-powered field mapping")
        return self._openai_client

    # -------------------------------------------------------------------------
    # Fuzzy String Matching
    # -------------------------------------------------------------------------

    def _levenshtein_ratio(self, s1: str, s2: str) -> float:
        """Calculate Levenshtein similarity ratio between two strings."""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _token_similarity(self, s1: str, s2: str) -> float:
        """Calculate token-based similarity."""
        # Split by underscores, camelCase, or other separators
        def tokenize(s: str) -> set:
            # Handle camelCase and underscore separation
            tokens = re.split(r'[_\s]', s.lower())
            # Also split camelCase
            expanded = []
            for t in tokens:
                expanded.extend(re.findall(r'[a-z]+|[A-Z][a-z]*|\d+', t))
            return set(t.lower() for t in expanded if len(t) > 1)

        tokens1 = tokenize(s1)
        tokens2 = tokenize(s2)

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        return len(intersection) / len(union) if union else 0.0

    def _combined_similarity(self, sap_field: str, aws_field: str,
                            sap_desc: str = "", aws_desc: str = "") -> float:
        """Calculate combined similarity score."""
        # Field name similarity (weighted higher)
        name_sim = self._levenshtein_ratio(sap_field, aws_field)
        token_sim = self._token_similarity(sap_field, aws_field)

        # Description similarity if available
        desc_sim = 0.0
        if sap_desc and aws_desc:
            desc_sim = self._token_similarity(sap_desc, aws_desc)

        # Weighted combination
        if desc_sim > 0:
            return 0.4 * name_sim + 0.3 * token_sim + 0.3 * desc_sim
        else:
            return 0.5 * name_sim + 0.5 * token_sim

    # -------------------------------------------------------------------------
    # Pattern Matching
    # -------------------------------------------------------------------------

    def _match_by_pattern(self, sap_field: str) -> Optional[Tuple[str, str, float]]:
        """Try to match SAP field using known patterns."""
        for pattern, (entity, field) in SAP_FIELD_PATTERNS.items():
            if re.match(pattern, sap_field, re.IGNORECASE):
                return entity, field, 0.95
        return None

    def _is_z_field(self, field_name: str) -> bool:
        """Check if a field is a Z-field (custom SAP field)."""
        return field_name.upper().startswith(('Z_', 'ZZ_', 'Y_'))

    def _is_z_table(self, table_name: str) -> bool:
        """Check if a table is a Z-table (custom SAP table)."""
        return table_name.upper().startswith(('Z', 'Y'))

    # -------------------------------------------------------------------------
    # Field Matching
    # -------------------------------------------------------------------------

    async def match_field(
        self,
        sap_field: str,
        sap_field_type: str = "",
        sap_field_description: str = "",
        target_entity: Optional[str] = None,
        source_table: Optional[str] = None,
        use_ai: bool = True
    ) -> FieldMatchResult:
        """
        Match a single SAP field to the best Autonomy SC field.

        Args:
            sap_field: SAP field name
            sap_field_type: SAP data type
            sap_field_description: Field description from SAP
            target_entity: If specified, only match to fields in this entity
            source_table: SAP source table name (enables table-specific mapping)
            use_ai: Whether to use AI for difficult mappings

        Returns:
            FieldMatchResult with best match and alternatives
        """
        result = FieldMatchResult(
            sap_field=sap_field,
            sap_field_description=sap_field_description,
            sap_field_type=sap_field_type,
            is_z_field=self._is_z_field(sap_field),
        )

        # 1. Check table-specific explicit mappings first (highest priority)
        if source_table:
            table_key = source_table.upper()
            table_mappings = SAP_TABLE_FIELD_MAPPINGS.get(table_key, {})
            field_upper = sap_field.strip().upper()
            if field_upper in table_mappings:
                entity, field = table_mappings[field_upper]
                result.aws_sc_entity = entity
                result.aws_sc_field = field
                result.confidence = MatchConfidence.HIGH
                result.confidence_score = 0.95
                result.match_source = MappingSource.AUTO_PATTERN
                return result

        # 2. Check learned mappings
        if sap_field in self._learned_mappings:
            entity, field = self._learned_mappings[sap_field]
            result.aws_sc_entity = entity
            result.aws_sc_field = field
            result.confidence = MatchConfidence.HIGH
            result.confidence_score = 0.98
            result.match_source = MappingSource.LEARNED
            return result

        # 3. Try pattern matching (cross-entity patterns)
        pattern_match = self._match_by_pattern(sap_field)
        if pattern_match:
            entity, field, score = pattern_match
            # Accept if no target_entity constraint, or entity matches, or wildcard
            if entity == "*" or target_entity is None or target_entity == entity:
                if entity != "*":
                    result.aws_sc_entity = entity
                    result.aws_sc_field = field
                    result.confidence = MatchConfidence.HIGH
                    result.confidence_score = score
                    result.match_source = MappingSource.AUTO_PATTERN
                    return result

        # 4. Fuzzy match — only for fields NOT covered by table-specific mapping.
        # When source_table is set, search ALL entities (not just target_entity)
        # since the table-specific mapping already handled entity routing.
        if source_table:
            entities_to_check = AWS_SC_FIELDS.keys()
        else:
            entities_to_check = AWS_SC_FIELDS.keys() if target_entity is None else [target_entity]

        all_matches = []
        for entity in entities_to_check:
            if entity not in AWS_SC_FIELDS:
                continue

            for aws_field, field_info in AWS_SC_FIELDS[entity].items():
                # Calculate similarity
                score = self._combined_similarity(
                    sap_field, aws_field,
                    sap_field_description, field_info.get("description", "")
                )

                if score > 0.5:  # Threshold raised — only meaningful matches
                    all_matches.append({
                        "entity": entity,
                        "field": aws_field,
                        "field_type": field_info["type"],
                        "score": score,
                        "required": field_info.get("required", False),
                    })

        # Sort by score
        all_matches.sort(key=lambda x: x["score"], reverse=True)

        if all_matches:
            best = all_matches[0]
            result.aws_sc_entity = best["entity"]
            result.aws_sc_field = best["field"]
            result.aws_sc_field_type = best["field_type"]
            result.confidence_score = best["score"]

            # Set confidence level
            if best["score"] >= 0.9:
                result.confidence = MatchConfidence.HIGH
            elif best["score"] >= 0.7:
                result.confidence = MatchConfidence.MEDIUM
            elif best["score"] >= 0.5:
                result.confidence = MatchConfidence.LOW
            else:
                result.confidence = MatchConfidence.NONE

            result.match_source = MappingSource.AUTO_FUZZY

            # Add alternatives
            result.alternatives = all_matches[1:5]  # Top 4 alternatives

        # If confidence is low and AI is enabled, get AI suggestion
        if result.confidence in (MatchConfidence.LOW, MatchConfidence.NONE) and use_ai:
            ai_suggestion = await self._get_ai_suggestion(
                sap_field, sap_field_type, sap_field_description, target_entity
            )
            if ai_suggestion:
                result.ai_rationale = ai_suggestion.get("rationale")
                result.ai_transform_suggestion = ai_suggestion.get("transform")

                if ai_suggestion.get("entity") and ai_suggestion.get("field"):
                    result.aws_sc_entity = ai_suggestion["entity"]
                    result.aws_sc_field = ai_suggestion["field"]
                    result.confidence = MatchConfidence.MEDIUM
                    result.confidence_score = ai_suggestion.get("confidence", 0.75)
                    result.match_source = MappingSource.AI_SUGGESTED

        return result

    async def match_fields_batch(
        self,
        fields: List[Dict[str, str]],
        target_entity: Optional[str] = None,
        source_table: Optional[str] = None,
        use_ai: bool = True
    ) -> List[FieldMatchResult]:
        """
        Match multiple fields in batch.

        Args:
            fields: List of dicts with 'name', 'type', 'description'
            target_entity: Optional entity to constrain matches
            source_table: SAP source table name (enables table-specific mapping)
            use_ai: Whether to use AI for difficult mappings

        Returns:
            List of FieldMatchResult
        """
        results = []

        for field_info in fields:
            result = await self.match_field(
                sap_field=field_info.get("name", ""),
                sap_field_type=field_info.get("type", ""),
                sap_field_description=field_info.get("description", ""),
                target_entity=target_entity,
                source_table=source_table,
                use_ai=use_ai
            )
            results.append(result)

        return results

    # -------------------------------------------------------------------------
    # Z-Table Analysis
    # -------------------------------------------------------------------------

    async def analyze_z_table(
        self,
        table_name: str,
        table_description: str,
        fields: List[Dict[str, str]],
        use_ai: bool = True
    ) -> ZTableAnalysis:
        """
        Analyze a Z-table and suggest entity mapping and field mappings.

        Args:
            table_name: SAP table name (e.g., ZSCM_CUSTOM)
            table_description: Table description
            fields: List of field definitions
            use_ai: Whether to use AI for analysis

        Returns:
            ZTableAnalysis with suggested mappings
        """
        analysis = ZTableAnalysis(
            table_name=table_name,
            description=table_description,
            field_count=len(fields),
            z_field_count=sum(1 for f in fields if self._is_z_field(f.get("name", ""))),
        )

        # First, determine the likely target entity
        entity_scores = await self._infer_target_entity(fields, table_description)

        if entity_scores:
            best_entity = max(entity_scores, key=entity_scores.get)
            analysis.suggested_entity = best_entity
            analysis.entity_confidence = entity_scores[best_entity]

        # Match all fields
        field_results = await self.match_fields_batch(
            fields,
            target_entity=analysis.suggested_entity,
            use_ai=use_ai
        )
        analysis.field_mappings = field_results

        # Calculate completeness
        if analysis.suggested_entity and analysis.suggested_entity in AWS_SC_FIELDS:
            required_fields = {f for f, info in AWS_SC_FIELDS[analysis.suggested_entity].items()
                             if info.get("required")}
            mapped_required = {r.aws_sc_field for r in field_results
                             if r.confidence in (MatchConfidence.HIGH, MatchConfidence.MEDIUM)}

            analysis.mappable_fields = len(AWS_SC_FIELDS[analysis.suggested_entity])
            analysis.mapped_fields = len(mapped_required & set(AWS_SC_FIELDS[analysis.suggested_entity].keys()))
            analysis.unmapped_required = len(required_fields - mapped_required)

        # Get AI analysis if enabled
        if use_ai:
            ai_analysis = await self._get_ai_table_analysis(
                table_name, table_description, fields, analysis.suggested_entity
            )
            if ai_analysis:
                analysis.ai_purpose_analysis = ai_analysis.get("purpose")
                analysis.ai_integration_guidance = ai_analysis.get("guidance")

        return analysis

    async def _infer_target_entity(
        self,
        fields: List[Dict[str, str]],
        table_description: str
    ) -> Dict[str, float]:
        """Infer the most likely target entity based on field patterns."""
        entity_scores: Dict[str, float] = {entity: 0.0 for entity in AWS_SC_FIELDS}

        for field_info in fields:
            field_name = field_info.get("name", "")

            # Check pattern matches
            pattern_match = self._match_by_pattern(field_name)
            if pattern_match and pattern_match[0] != "*":
                entity_scores[pattern_match[0]] += pattern_match[2]

            # Fuzzy match contribution
            for entity, entity_fields in AWS_SC_FIELDS.items():
                for aws_field in entity_fields:
                    score = self._levenshtein_ratio(field_name, aws_field)
                    if score > 0.6:
                        entity_scores[entity] += score * 0.5

        # Add description-based scoring
        desc_keywords = {
            "product": ["material", "item", "product", "sku", "article"],
            "site": ["plant", "location", "warehouse", "dc", "site"],
            "inv_level": ["stock", "inventory", "quantity", "level"],
            "trading_partner": ["vendor", "supplier", "customer", "partner"],
            "inbound_order": ["purchase", "po", "procurement", "inbound"],
            "outbound_order": ["sales", "so", "order", "shipment", "outbound"],
            "forecast": ["forecast", "demand", "prediction", "plan"],
            "production_order": ["production", "manufacturing", "work order"],
            "transfer_order": ["transfer", "sto", "warehouse movement", "stock transport"],
            "quality_order": ["quality", "inspection", "qm", "defect", "notification"],
            "maintenance_order": ["maintenance", "pm", "equipment", "preventive", "corrective", "breakdown"],
            "subcontracting_order": ["subcontracting", "toll", "external manufacturing", "outsource"],
            "supply_plan": ["mrp", "planned order", "requirements planning", "supply plan", "netting", "planning run"],
            "inv_policy": ["safety stock", "reorder", "lot size", "mrp type", "inventory policy", "replenishment"],
            "purchase_requisition": ["purchase requisition", "banf", "procurement request", "requisition", "buy request"],
            "sap_user": ["user", "bname", "logon", "username", "person", "email", "smtp"],
            "sap_role": ["role", "agr_name", "composite", "profile", "activity group"],
            "sap_authorization": ["authorization", "auth object", "tcode", "transaction code", "actvt"],
        }

        desc_lower = table_description.lower()
        for entity, keywords in desc_keywords.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    entity_scores[entity] += 1.0

        # Normalize scores
        max_score = max(entity_scores.values()) if entity_scores else 1.0
        if max_score > 0:
            entity_scores = {k: v / max_score for k, v in entity_scores.items()}

        return {k: v for k, v in entity_scores.items() if v > 0.1}

    # -------------------------------------------------------------------------
    # AI-Powered Analysis
    # -------------------------------------------------------------------------

    async def _get_ai_suggestion(
        self,
        sap_field: str,
        sap_field_type: str,
        sap_field_description: str,
        target_entity: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Get AI suggestion for a field mapping."""
        client = await self._get_openai_client()
        if not client:
            return None

        try:
            # Build available fields context
            if target_entity and target_entity in AWS_SC_FIELDS:
                available_fields = AWS_SC_FIELDS[target_entity]
            else:
                available_fields = {f"{e}.{f}": info for e, fields in AWS_SC_FIELDS.items()
                                   for f, info in fields.items()}

            # Retrieve RAG context for AWS SC data model knowledge (tenant-scoped)
            from app.services.rag_context import get_rag_context
            kb_context = await get_rag_context(
                f"AWS supply chain data model {sap_field} {sap_field_description} SAP field mapping",
                tenant_id=self.tenant_id, top_k=3, max_tokens=1500, category="supply_chain_planning",
            )
            kb_section = ""
            if kb_context:
                kb_section = f"\nReference Knowledge:\n{kb_context}\n"

            prompt = f"""Analyze this SAP field and suggest the best AWS Supply Chain field mapping:

SAP Field: {sap_field}
Type: {sap_field_type}
Description: {sap_field_description}
Is Custom (Z-field): {self._is_z_field(sap_field)}
{kb_section}
Available target fields:
{json.dumps(available_fields, indent=2)}

Respond in JSON format:
{{
    "entity": "entity_name or null",
    "field": "field_name or null",
    "confidence": 0.0-1.0,
    "rationale": "explanation of why this mapping makes sense",
    "transform": "any transformation needed (e.g., 'uppercase', 'date_format:YYYYMMDD', 'lookup:table_name')"
}}
"""

            model = os.environ.get("LLM_MODEL_NAME") or os.environ.get("AUTONOMY_LLM_MODEL") or "qwen3-8b"
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an SAP-to-AWS Supply Chain field mapping expert. Use the provided reference knowledge to ground your mapping suggestions in the actual AWS SC data model."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"AI suggestion failed: {e}")
            return None

    async def _get_ai_table_analysis(
        self,
        table_name: str,
        table_description: str,
        fields: List[Dict[str, str]],
        suggested_entity: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Get AI analysis of a Z-table's purpose and integration guidance."""
        client = await self._get_openai_client()
        if not client:
            return None

        try:
            field_summary = "\n".join([
                f"- {f.get('name', '')}: {f.get('type', '')} - {f.get('description', '')}"
                for f in fields[:20]  # Limit to first 20 fields
            ])

            # Retrieve RAG context for SAP integration knowledge (tenant-scoped)
            from app.services.rag_context import get_rag_context
            kb_context = await get_rag_context(
                f"AWS supply chain data model SAP Z-table {table_name} {table_description} integration",
                tenant_id=self.tenant_id, top_k=3, max_tokens=1500, category="supply_chain_planning",
            )
            kb_section = ""
            if kb_context:
                kb_section = f"\nReference Knowledge:\n{kb_context}\n"

            prompt = f"""Analyze this custom SAP table (Z-table) for AWS Supply Chain integration:

Table: {table_name}
Description: {table_description}
Suggested Entity: {suggested_entity or 'Unknown'}
{kb_section}
Fields:
{field_summary}

Provide analysis in JSON format:
{{
    "purpose": "Brief description of what this table likely stores and its business purpose",
    "guidance": "Specific guidance for integrating this table with AWS Supply Chain, including any data transformations or special handling needed for Z-fields"
}}
"""

            model = os.environ.get("LLM_MODEL_NAME") or os.environ.get("AUTONOMY_LLM_MODEL") or "qwen3-8b"
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an SAP integration expert helping migrate data to AWS Supply Chain. Use the provided reference knowledge to ground your analysis in the actual AWS SC data model."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"AI table analysis failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # Learning and Feedback
    # -------------------------------------------------------------------------

    async def confirm_mapping(
        self,
        sap_field: str,
        aws_entity: str,
        aws_field: str
    ) -> None:
        """
        Confirm a mapping, adding it to learned mappings.

        This allows the system to learn from user corrections.
        """
        self._learned_mappings[sap_field] = (aws_entity, aws_field)
        logger.info(f"Learned mapping: {sap_field} -> {aws_entity}.{aws_field}")

    async def reject_mapping(self, sap_field: str) -> None:
        """Reject a learned mapping."""
        if sap_field in self._learned_mappings:
            del self._learned_mappings[sap_field]

    async def get_mapping_statistics(self) -> Dict[str, Any]:
        """Get statistics about current mappings."""
        return {
            "learned_mappings_count": len(self._learned_mappings),
            "pattern_count": len(SAP_FIELD_PATTERNS),
            "supported_entities": list(AWS_SC_FIELDS.keys()),
            "total_aws_fields": sum(len(fields) for fields in AWS_SC_FIELDS.values()),
        }

    async def export_mappings(self) -> Dict[str, Any]:
        """Export all learned mappings for persistence."""
        return {
            "version": "1.0",
            "tenant_id": self.tenant_id,
            "timestamp": datetime.utcnow().isoformat(),
            "learned_mappings": {
                k: {"entity": v[0], "field": v[1]}
                for k, v in self._learned_mappings.items()
            },
        }

    async def import_mappings(self, data: Dict[str, Any]) -> int:
        """Import previously exported mappings."""
        imported = 0
        mappings = data.get("learned_mappings", {})

        for sap_field, mapping in mappings.items():
            entity = mapping.get("entity")
            field = mapping.get("field")
            if entity and field:
                self._learned_mappings[sap_field] = (entity, field)
                imported += 1

        logger.info(f"Imported {imported} learned mappings")
        return imported


# Convenience function
def create_field_mapping_service(db: AsyncSession, tenant_id: int) -> SAPFieldMappingService:
    """Create a field mapping service for a customer."""
    return SAPFieldMappingService(db, tenant_id)

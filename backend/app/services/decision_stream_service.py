"""
Decision Stream Service — TMS subclass of Core's BaseDecisionStreamService.

Registers TMS's 11 Powell TRM decision tables, GNN directive reviews,
governance decisions, and provides TMS-specific hooks for:
  - Collecting pending decisions from all Powell tables
  - Building human-readable summaries per TRM type
  - Supply plan adjustments on action
  - Experiential knowledge extraction from overrides
  - Context enrichment (DAG topology, BSC, external signals, EK)
  - Rich LLM chat with SC glossary
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from azirella_data_model.decision_stream import (
    BaseDecisionStreamService,
    BaseDecisionStreamConfig,
    DecisionTableEntry,
    urgency_label,
    likelihood_label,
    safe_float,
    fmt_qty_int,
    consolidate_decisions,
    humanize_ids,
    get_editable_values,
    apply_override_values,
    snapshot_original_values,
    mark_executed,
    safe_effective_from,
    safe_period_days,
    get_reason,
    get_effective_dates,
    ConversationCache,
    DigestCache,
    default_conversation_cache,
    default_digest_cache,
    get_role_filter,
    DateExtractor,
)

from app.models.powell_decisions import (
    PowellATPDecision,
    PowellRebalanceDecision,
    PowellPODecision,
    PowellOrderException,
    PowellMODecision,
    PowellTODecision,
    PowellQualityDecision,
    PowellMaintenanceDecision,
    PowellSubcontractingDecision,
    PowellForecastAdjustmentDecision,
    PowellBufferDecision,
)
from app.models.gnn_directive_review import GNNDirectiveReview
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.sc_entities import Product, Forecast, InvLevel, InvPolicy
from app.models.planning_hierarchy import (
    SiteHierarchyNode, SiteHierarchyLevel,
    ProductHierarchyNode, ProductHierarchyLevel,
)
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
_ALERT_LOOKBACK_HOURS = 48
_CDC_TRIGGER_LIMIT = 10
_DECISION_LOOKBACK_DAYS = 30
_DECISIONS_PER_TABLE = 50  # Per TRM table; total is uncapped — frontend paginates
_REBALANCE_COOLDOWN_HOURS = int(os.environ.get("REBALANCE_COOLDOWN_HOURS", 24))
_ENRICHMENT_HISTORY_WINDOW = 4
_INVENTORY_FETCH_LIMIT = 20
_FORECAST_FETCH_LIMIT = 20
_FORECAST_PERIODS_PER_PRODUCT = 4
_FORECAST_DISPLAY_MAX = 8
_POLICY_FETCH_LIMIT = 20
_FORECAST_CHANGE_ALERT_PCT = 20.0
_DEFAULT_CONFIDENCE = 0.5
_DIGEST_SUMMARY_MAX_DECISIONS = 5
_CURRENCY_SYMBOL = os.environ.get("DECISION_STREAM_CURRENCY", "$")

# Decision quality guardrails (preserved for backward-compat test imports)
_ABANDON_COMBINED_THRESHOLD = float(
    os.environ.get("DECISION_STREAM_ABANDON_THRESHOLD", 0.5)
)

# ---------------------------------------------------------------------------
# TMS Decision Tables
# ---------------------------------------------------------------------------
DECISION_TABLES = [
    (PowellATPDecision, "atp"),
    (PowellRebalanceDecision, "rebalancing"),
    (PowellPODecision, "po_creation"),
    (PowellOrderException, "order_tracking"),
    (PowellMODecision, "mo_execution"),
    (PowellTODecision, "to_execution"),
    (PowellQualityDecision, "quality"),
    (PowellMaintenanceDecision, "maintenance"),
    (PowellSubcontractingDecision, "subcontracting"),
    (PowellForecastAdjustmentDecision, "forecast_adjustment"),
    (PowellBufferDecision, "inventory_buffer"),
]

# Map type_key -> DB table name
DECISION_TYPE_TABLE_MAP = {
    "atp": "powell_atp_decisions",
    "rebalancing": "powell_rebalance_decisions",
    "po_creation": "powell_po_decisions",
    "order_tracking": "powell_order_exceptions",
    "mo_execution": "powell_mo_decisions",
    "to_execution": "powell_to_decisions",
    "quality": "powell_quality_decisions",
    "maintenance": "powell_maintenance_decisions",
    "subcontracting": "powell_subcontracting_decisions",
    "forecast_adjustment": "powell_forecast_adjustment_decisions",
    "inventory_buffer": "powell_buffer_decisions",
    "demand_adjustment": "powell_demand_adjustment_decisions",
    "inventory_adjustment": "powell_inventory_adjustment_decisions",
    "supply_adjustment": "powell_supply_adjustment_decisions",
    "rccp_adjustment": "powell_rccp_adjustment_decisions",
    "sop_policy": "gnn_directive_reviews",
    "execution_directive": "gnn_directive_reviews",
    "allocation_refresh": "gnn_directive_reviews",
}

# Deep-link mapping for each decision type -> frontend route
DEEP_LINK_MAP = {
    "atp": "/planning/execution/atp-worklist",
    "rebalancing": "/planning/execution/rebalancing-worklist",
    "po_creation": "/planning/execution/po-worklist",
    "order_tracking": "/planning/execution/order-tracking-worklist",
    "mo_execution": "/planning/execution/mo-worklist",
    "to_execution": "/planning/execution/to-worklist",
    "quality": "/planning/execution/quality-worklist",
    "maintenance": "/planning/execution/maintenance-worklist",
    "subcontracting": "/planning/execution/subcontracting-worklist",
    "forecast_adjustment": "/planning/demand",
    "inventory_buffer": "/planning/inventory-optimization",
    "email_signal": "/admin/email-signals",
}

# Decision level mapping
DECISION_LEVEL = {
    "directive": "governance",
    "guardrail_change": "governance",
    "policy_envelope_change": "governance",
    "sop_policy": "strategic",
    "site_coordination": "operational",
    "execution_directive": "tactical",
    "network_directive": "tactical",
    "allocation_refresh": "tactical",
    "atp": "execution",
    "rebalancing": "execution",
    "po_creation": "execution",
    "order_tracking": "execution",
    "mo_execution": "execution",
    "to_execution": "execution",
    "quality": "execution",
    "maintenance": "execution",
    "subcontracting": "execution",
    "forecast_adjustment": "execution",
    "inventory_buffer": "execution",
    "demand_adjustment": "execution",
    "inventory_adjustment": "execution",
    "supply_adjustment": "execution",
    "rccp_adjustment": "execution",
}

# Role-based level filtering
ROLE_DEFAULT_LEVELS = {
    "SC_VP": {"default_levels": {"governance", "strategic"}, "escalation_from": "tactical"},
    "EXECUTIVE": {"default_levels": {"governance", "strategic"}, "escalation_from": "tactical"},
    "SOP_DIRECTOR": {"default_levels": {"strategic"}, "escalation_from": "tactical"},
    "MPS_MANAGER": {"default_levels": {"tactical"}, "escalation_from": "execution"},
    "ALLOCATION_MANAGER": {"default_levels": {"tactical"}, "escalation_from": "execution"},
    "ORDER_PROMISE_MANAGER": {"default_levels": {"execution"}, "escalation_from": None},
    "ATP_ANALYST": {"default_levels": {"execution"}, "escalation_from": None},
    "REBALANCING_ANALYST": {"default_levels": {"execution"}, "escalation_from": None},
    "PO_ANALYST": {"default_levels": {"execution"}, "escalation_from": None},
    "ORDER_TRACKING_ANALYST": {"default_levels": {"execution"}, "escalation_from": None},
    "DEMO_ALL": {"default_levels": {"governance", "strategic", "tactical", "execution"}, "escalation_from": None},
}

ROLE_TYPE_FILTER = {
    "ALLOCATION_MANAGER": {"execution_directive", "allocation_refresh", "atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    "ATP_ANALYST": {"atp"},
    "REBALANCING_ANALYST": {"rebalancing"},
    "PO_ANALYST": {"po_creation"},
    "ORDER_TRACKING_ANALYST": {"order_tracking"},
}

ROLE_RELEVANCE = {
    "SC_VP": None,
    "EXECUTIVE": None,
    "SOP_DIRECTOR": None,
    "MPS_MANAGER": None,
    "ALLOCATION_MANAGER": {"execution_directive", "allocation_refresh", "atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    "ATP_ANALYST": {"atp"},
    "REBALANCING_ANALYST": {"rebalancing"},
    "PO_ANALYST": {"po_creation"},
    "ORDER_TRACKING_ANALYST": {"order_tracking"},
    "DEMO_ALL": None,
}

# Editable fields per decision type
EDITABLE_FIELDS_MAP: Dict[str, List[Dict[str, str]]] = {
    "atp": [
        {"key": "allocated_qty", "label": "Allocated Qty", "type": "number", "db_col": "promised_qty"},
    ],
    "rebalancing": [
        {"key": "qty", "label": "Transfer Qty", "type": "number", "db_col": "recommended_qty"},
    ],
    "po_creation": [
        {"key": "qty", "label": "Order Qty", "type": "number", "db_col": "recommended_qty"},
        {"key": "supplier_id", "label": "Supplier", "type": "text", "db_col": "supplier_id"},
        {"key": "due_date", "label": "Due Date", "type": "date", "db_col": "expected_receipt_date"},
    ],
    "order_tracking": [
        {"key": "recommended_action", "label": "Action", "type": "select", "db_col": "recommended_action",
         "options": "find_alternate,expedite,cancel,split,reroute,accept_delay"},
    ],
    "mo_execution": [
        {"key": "qty", "label": "Planned Qty", "type": "number", "db_col": "planned_qty"},
        {"key": "priority", "label": "Priority", "type": "number", "db_col": "priority_override"},
    ],
    "to_execution": [
        {"key": "qty", "label": "Planned Qty", "type": "number", "db_col": "planned_qty"},
    ],
    "quality": [
        {"key": "disposition", "label": "Disposition", "type": "select", "db_col": "disposition",
         "options": "accept,reject,rework,scrap,use_as_is,return_to_vendor"},
    ],
    "maintenance": [
        {"key": "scheduled_date", "label": "Schedule Date", "type": "date", "db_col": "scheduled_date"},
        {"key": "action", "label": "Action", "type": "select", "db_col": "decision_type",
         "options": "schedule,defer,expedite,combine,outsource"},
    ],
    "subcontracting": [
        {"key": "routing", "label": "Routing", "type": "select", "db_col": "decision_type",
         "options": "route_external,keep_internal,split,change_vendor"},
        {"key": "qty", "label": "Planned Qty", "type": "number", "db_col": "planned_qty"},
    ],
    "forecast_adjustment": [
        {"key": "direction", "label": "Direction", "type": "select", "db_col": "adjustment_direction",
         "options": "up,down,no_change"},
        {"key": "magnitude_pct", "label": "Adjustment %", "type": "number", "db_col": "adjustment_pct"},
    ],
    "inventory_buffer": [
        {"key": "buffer_qty", "label": "Buffer Qty", "type": "number", "db_col": "adjusted_ss"},
        {"key": "multiplier", "label": "Multiplier", "type": "number", "db_col": "multiplier"},
    ],
}

# Tables with no product_id column
_NO_PRODUCT_TABLES = {"order_tracking", "maintenance"}

# Business-friendly labels for digest text
_DIGEST_TYPE_LABELS = {
    "atp_executor": "ATP Fulfillment",
    "atp": "ATP Fulfillment",
    "rebalancing": "Inventory Rebalancing",
    "po_creation": "Procurement",
    "order_tracking": "Order Exception",
    "mo_execution": "Production",
    "to_execution": "Transfer",
    "quality": "Quality",
    "quality_disposition": "Quality",
    "maintenance": "Maintenance",
    "maintenance_scheduling": "Maintenance",
    "subcontracting": "Make-vs-Buy",
    "forecast_adjustment": "Demand Forecast",
    "inventory_buffer": "Inventory Buffer",
    "sop_policy": "Strategic Policy",
    "execution_directive": "Planning Directive",
    "allocation_refresh": "Allocation Update",
    "site_coordination": "Site Coordination",
    "directive": "Executive Directive",
}

# TMS-specific date extractors
def _po_date_extractor(decision, default_from):
    receipt = getattr(decision, "expected_receipt_date", None)
    if receipt:
        lead_days = (receipt - default_from).days if hasattr(receipt, "__sub__") else 0
        return default_from.isoformat(), max(lead_days, 7)
    return default_from.isoformat(), 14

def _forecast_date_extractor(decision, default_from):
    periods = getattr(decision, "time_horizon_periods", None)
    if periods and isinstance(periods, int):
        return default_from.isoformat(), periods * 7
    return default_from.isoformat(), 28

def _to_date_extractor(decision, default_from):
    transit = getattr(decision, "estimated_transit_days", None)
    if transit:
        try:
            return default_from.isoformat(), max(int(float(transit)) + 7, 7)
        except (TypeError, ValueError):
            pass
    return default_from.isoformat(), 7

def _maintenance_date_extractor(decision, default_from):
    sched = getattr(decision, "scheduled_date", None)
    if sched:
        return sched.isoformat() if hasattr(sched, "isoformat") else str(sched), 7
    return default_from.isoformat(), 7

TMS_DATE_EXTRACTORS: Dict[str, DateExtractor] = {
    "po_creation": _po_date_extractor,
    "rebalancing": lambda d, df: (df.isoformat(), 7),
    "forecast_adjustment": _forecast_date_extractor,
    "mo_execution": lambda d, df: (df.isoformat(), 14),
    "to_execution": _to_date_extractor,
    "maintenance": _maintenance_date_extractor,
    "inventory_buffer": lambda d, df: (df.isoformat(), 28),
}

TMS_REASON_COLUMN_MAP = {
    "po_creation": "trigger_reason",
    "to_execution": "trigger_reason",
    "quality": "disposition_reason",
}

# Role descriptions for LLM system prompt
_ROLE_DESCRIPTIONS = {
    "SC_VP": {
        "title": "VP of Supply Chain",
        "scope": "strategic network-wide performance, risk assessment, and executive KPIs",
        "can_do": "review strategic decisions, assess network risk, ask about KPIs and trends, inspect any decision",
        "cannot_do": "create orders, modify forecasts, change safety stock, approve plans, override agent decisions",
    },
    "EXECUTIVE": {
        "title": "Supply Chain Executive",
        "scope": "strategic insights, decision review, and risk assessment across the network",
        "can_do": "review all decisions, inspect agent reasoning, ask about performance and trends",
        "cannot_do": "create orders, modify forecasts, change safety stock, approve plans, override agent decisions",
    },
    "SOP_DIRECTOR": {
        "title": "S&OP Director",
        "scope": "S&OP policy parameters, tactical allocation directives, and demand/supply balancing",
        "can_do": "review S&OP decisions, adjust policy parameters, issue strategic directives, inspect decisions",
        "cannot_do": "create purchase orders, modify site-level inventory, manage users",
    },
    "MPS_MANAGER": {
        "title": "MPS/Execution Manager",
        "scope": "master production scheduling, capacity planning, and execution-level decisions",
        "can_do": "review tactical decisions, approve/override execution decisions, manage worklists, create orders",
        "cannot_do": "change S&OP policy parameters, modify network topology, manage users",
    },
    "DEMO_ALL": {
        "title": "Demo User (All Access)",
        "scope": "full platform visibility for demonstration purposes",
        "can_do": "view all decisions at all levels, inspect reasoning, explore the platform",
        "cannot_do": "nothing restricted in demo mode",
    },
}

_ROLE_METRICS = {
    "SC_VP": (
        "When this user asks about 'performance', 'how are we doing', or 'best/worst', "
        "they mean STRATEGIC metrics: Revenue growth, EBIT margin, ROCS (Return on Capital), "
        "Gross Margin, OTIF, C2C cycle time, and Cost to Serve. "
        "Present comparisons as a ranked table with the BSC composite score."
    ),
    "EXECUTIVE": (
        "When this user asks about 'performance', they mean the EXECUTIVE DASHBOARD view: "
        "OTIF, fill rate, margin, cost/order, agent ROI metrics, revenue at risk. "
        "Compare across regions x product groups using the balanced scorecard. "
        "Lead with the headline number, then break down by dimension."
    ),
    "SOP_DIRECTOR": (
        "When this user asks about 'performance', they mean S&OP TACTICAL metrics: "
        "Perfect Order Fulfillment (POF = OTD x IF x DF x DA), demand forecast accuracy (MAPE), "
        "supply plan adherence, inventory turns, and S&OP worklist resolution rate."
    ),
    "MPS_MANAGER": (
        "When this user asks about 'performance', they mean OPERATIONAL metrics: "
        "Schedule adherence, capacity utilization, production yield, on-time delivery, "
        "order cycle time, and exception resolution rate."
    ),
    "DEMO_ALL": (
        "This user has full access. When they ask about 'performance', start with the "
        "executive view (OTIF, fill rate, margin, cost) then offer to drill into "
        "tactical or operational metrics."
    ),
}

# ---------------------------------------------------------------------------
# Module-level caches (backward-compatible with endpoint imports)
# ---------------------------------------------------------------------------
_tms_digest_cache = default_digest_cache


def invalidate_digest_cache(tenant_id: Optional[int] = None, config_id: Optional[int] = None):
    """Invalidate digest cache entries. Called when new decisions are persisted."""
    _tms_digest_cache.invalidate(tenant_id=tenant_id, config_id=config_id)


# ---------------------------------------------------------------------------
# TMS CONFIG
# ---------------------------------------------------------------------------
TMS_CONFIG = BaseDecisionStreamConfig(
    decision_tables=[DecisionTableEntry(cls, key) for cls, key in DECISION_TABLES],
    deep_link_map=DEEP_LINK_MAP,
    decision_type_table_map=DECISION_TYPE_TABLE_MAP,
    decision_level_map=DECISION_LEVEL,
    editable_fields_map=EDITABLE_FIELDS_MAP,
    role_default_levels=ROLE_DEFAULT_LEVELS,
    role_type_filter=ROLE_TYPE_FILTER,
    role_relevance=ROLE_RELEVANCE,
    reason_column_map=TMS_REASON_COLUMN_MAP,
    date_extractors=TMS_DATE_EXTRACTORS,
    digest_type_labels=_DIGEST_TYPE_LABELS,
    no_product_tables=_NO_PRODUCT_TABLES,
    role_descriptions=_ROLE_DESCRIPTIONS,
    role_metrics=_ROLE_METRICS,
)


# ---------------------------------------------------------------------------
# TMS Decision Stream Service
# ---------------------------------------------------------------------------

class DecisionStreamService(BaseDecisionStreamService):
    """TMS-specific Decision Stream — subclasses Core's BaseDecisionStreamService."""

    CONFIG = TMS_CONFIG

    def __init__(self, db: AsyncSession, tenant_id: int, tenant_name: str = "", user=None):
        super().__init__(
            db=db,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            user=user,
            config=TMS_CONFIG,
            conversation_cache=default_conversation_cache,
            digest_cache=_tms_digest_cache,
        )
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # User scope resolution
    # ------------------------------------------------------------------

    async def _resolve_user_scope(self) -> Tuple[Optional[set], Optional[set]]:
        """Resolve user's hierarchy scope to raw site names and product IDs."""
        from app.services.user_scope_service import resolve_user_scope
        return await resolve_user_scope(self.db, self.user)

    # ------------------------------------------------------------------
    # Hook: site filter
    # ------------------------------------------------------------------

    def _site_filter(self, type_key: str, model_class: Any, sites: set):
        """Build a SQLAlchemy filter clause for site scope per TRM type."""
        if type_key in ("atp", "po_creation", "inventory_buffer"):
            return model_class.location_id.in_(sites)
        elif type_key == "rebalancing":
            return or_(model_class.from_site.in_(sites), model_class.to_site.in_(sites))
        elif type_key == "to_execution":
            return or_(model_class.source_site_id.in_(sites), model_class.dest_site_id.in_(sites))
        elif type_key in ("mo_execution", "quality", "maintenance", "subcontracting", "forecast_adjustment"):
            return model_class.site_id.in_(sites)
        return None

    # ------------------------------------------------------------------
    # Hook: decision summary
    # ------------------------------------------------------------------

    def _build_decision_summary(self, decision: Any, decision_type: str, name_cache: dict = None) -> str:
        """Build a human-readable one-line summary for any TMS decision type."""
        raw_product = getattr(decision, "product_id", None) or ""
        raw_location = (
            getattr(decision, "location_id", None)
            or getattr(decision, "site_id", None)
            or getattr(decision, "from_site", None)
            or ""
        )
        cache = name_cache or {}
        product = cache.get("products", {}).get(raw_product, raw_product)
        location = cache.get("sites", {}).get(str(raw_location), str(raw_location))

        if product == raw_product and "_" in product:
            parts = product.split("_", 1)
            if parts[0].startswith("CFG"):
                product = parts[1]

        sites = cache.get("sites", {})

        if decision_type == "atp":
            qty = fmt_qty_int(getattr(decision, "requested_qty", None))
            return f"ATP: Fulfill {qty} units of {product} at {location}"
        elif decision_type == "rebalancing":
            qty = fmt_qty_int(getattr(decision, "recommended_qty", None))
            raw_src = str(getattr(decision, "from_site", "?"))
            raw_dest = str(getattr(decision, "to_site", "?"))
            return f"Rebalance: Transfer {qty} of {product} from {sites.get(raw_src, raw_src)} to {sites.get(raw_dest, raw_dest)}"
        elif decision_type == "po_creation":
            qty = fmt_qty_int(getattr(decision, "recommended_qty", None))
            return f"PO: Order {qty} units of {product} at {location}"
        elif decision_type == "order_tracking":
            desc_text = getattr(decision, "description", "") or ""
            order_id = getattr(decision, "order_id", "?")
            if desc_text:
                return f"{desc_text} ({order_id})"
            severity = getattr(decision, "severity", "INFO")
            exc_type = getattr(decision, "exception_type", "")
            return f"Order Exception ({severity}): {exc_type} on {order_id}"
        elif decision_type == "mo_execution":
            dt = getattr(decision, "decision_type", "release")
            return f"MO {dt}: {product} at {location}"
        elif decision_type == "to_execution":
            dt = getattr(decision, "decision_type", "release")
            raw_src = str(getattr(decision, "source_site_id", None) or raw_location)
            raw_dest = str(getattr(decision, "dest_site_id", None) or "")
            src = sites.get(raw_src, raw_src)
            dest = sites.get(raw_dest, raw_dest)
            if src and dest:
                return f"TO {dt}: {product} from {src} to {dest}"
            return f"TO {dt}: {product} at {src or dest or location}"
        elif decision_type == "quality":
            disposition = getattr(decision, "disposition", "?")
            return f"Quality {disposition}: {product} at {location}"
        elif decision_type == "maintenance":
            dt = getattr(decision, "decision_type", "schedule")
            asset = getattr(decision, "asset_id", "?")
            return f"Maintenance {dt}: Asset {asset} at {location}"
        elif decision_type == "subcontracting":
            routing = getattr(decision, "routing_decision", "?")
            return f"Subcontracting {routing}: {product}"
        elif decision_type == "forecast_adjustment":
            direction = getattr(decision, "adjustment_direction", "?")
            pct = getattr(decision, "adjustment_pct", "?")
            return f"Forecast {direction} {pct}%: {product}"
        elif decision_type == "inventory_buffer":
            reason_text = getattr(decision, "reason", "adjust")
            base = getattr(decision, "baseline_ss", None)
            adj = getattr(decision, "adjusted_ss", None)
            if base and adj:
                return f"Buffer {reason_text}: {product} at {location} ({base:.0f} -> {adj:.0f})"
            return f"Buffer {reason_text}: {product} at {location}"
        return f"{decision_type}: {product} at {location}"

    # ------------------------------------------------------------------
    # Hook: suggested action
    # ------------------------------------------------------------------

    def _get_suggested_action(self, decision: Any, decision_type: str) -> str:
        """Extract the suggested action text from a TMS decision."""
        pid = getattr(decision, "product_id", "") or ""
        short_pid = pid.split("_", 1)[1] if "_" in pid and pid.startswith("CFG") else pid

        if decision_type == "atp":
            promised = getattr(decision, "promised_qty", None)
            requested = getattr(decision, "requested_qty", None)
            if getattr(decision, "can_fulfill", False):
                return f"Fulfill {fmt_qty_int(promised)} units of {short_pid}" if promised is not None else "Fulfill order"
            if promised is not None and requested is not None:
                return f"Partial fill {short_pid} — {fmt_qty_int(promised)} of {fmt_qty_int(requested)} units"
            return "Cannot fulfill — review order"
        elif decision_type == "rebalancing":
            qty = getattr(decision, "recommended_qty", None)
            return f"Transfer {fmt_qty_int(qty)} units of {short_pid}" if qty is not None else "Transfer units"
        elif decision_type == "po_creation":
            qty = getattr(decision, "recommended_qty", None)
            trigger = getattr(decision, "trigger_reason", "") or ""
            return f"{'Expedite' if trigger == 'expedite' else 'Order'} {fmt_qty_int(qty)} units of {short_pid}" if qty is not None else "Create PO"
        elif decision_type == "order_tracking":
            action = getattr(decision, "recommended_action", "Review exception")
            desc_text = getattr(decision, "description", "") or ""
            if desc_text:
                return f"{action.replace('_', ' ').title()}: {desc_text}"
            return action
        elif decision_type == "mo_execution":
            dt = getattr(decision, 'decision_type', 'Release').title()
            qty = fmt_qty_int(getattr(decision, "planned_qty", None) or getattr(decision, "order_qty", None))
            return f"{dt} MO: {short_pid} ({qty} units)" if qty else f"{dt} MO: {short_pid}"
        elif decision_type == "to_execution":
            dt = getattr(decision, 'decision_type', 'Release').title()
            qty = fmt_qty_int(getattr(decision, "transfer_qty", None))
            return f"{dt} TO: {short_pid} ({qty} units)" if qty else f"{dt} TO: {short_pid}"
        elif decision_type == "quality":
            disposition = getattr(decision, 'disposition', 'Review').title()
            qty = fmt_qty_int(getattr(decision, "inspection_qty", None) or getattr(decision, "lot_size", None))
            return f"{disposition}: {short_pid} ({qty} units)" if qty else f"{disposition}: {short_pid}"
        elif decision_type == "maintenance":
            dt = getattr(decision, 'decision_type', 'Schedule').title()
            asset = getattr(decision, "asset_id", None) or getattr(decision, "equipment_id", None) or ""
            return f"{dt} maintenance for {asset or short_pid}"
        elif decision_type == "subcontracting":
            routing = getattr(decision, 'routing_decision', 'internal')
            qty = fmt_qty_int(getattr(decision, "order_qty", None))
            return f"Route {short_pid} via {routing}" + (f" ({qty} units)" if qty else "")
        elif decision_type == "forecast_adjustment":
            direction = getattr(decision, "adjustment_direction", "")
            pct = getattr(decision, "adjustment_pct", "")
            cur = getattr(decision, "current_forecast_value", None)
            adj = getattr(decision, "adjusted_forecast_value", None)
            sid = getattr(decision, "site_id", "")
            horizon = getattr(decision, "planning_horizon", None) or getattr(decision, "adjustment_horizon", None)
            horizon_str = f" over {horizon}" if horizon else ""
            if cur and adj:
                return f"Adjust forecast {direction} {pct}% for {pid} @ {sid}{horizon_str} ({cur:.0f} -> {adj:.0f} units/wk)"
            return f"Adjust forecast {direction} {pct}% for {pid} @ {sid}{horizon_str}"
        elif decision_type == "inventory_buffer":
            base = getattr(decision, "baseline_ss", None)
            adj = getattr(decision, "adjusted_ss", None)
            mult = getattr(decision, "multiplier", None)
            if base and adj:
                return f"Adjust buffer {base:.0f} -> {adj:.0f} ({mult:.2f}x)"
            return f"Adjust buffer ({getattr(decision, 'reason', 'review')})"
        return "Review decision"

    # ------------------------------------------------------------------
    # Hook: plan adjustment
    # ------------------------------------------------------------------

    async def _create_plan_adjustment(
        self, decision: Any, decision_type: str, override_values: Optional[Dict[str, Any]],
    ) -> None:
        """Persist a supply plan record reflecting the actioned TMS decision."""
        if decision_type not in (
            "rebalancing", "po_creation", "mo_execution", "to_execution",
            "inventory_buffer", "forecast_adjustment",
        ):
            return

        from app.models.sc_entities import SupplyPlan

        config_id = getattr(decision, "config_id", None)
        if not config_id:
            return

        action_date = datetime.utcnow().date()
        plan_type_map = {
            "rebalancing": "to_request",
            "po_creation": "po_request",
            "mo_execution": "mo_request",
            "to_execution": "to_request",
            "inventory_buffer": "ss_adjustment",
            "forecast_adjustment": "forecast_adjustment",
        }
        plan_type = plan_type_map.get(decision_type, "adjustment")

        ov = override_values or {}
        qty = (
            ov.get("qty") or ov.get("allocated_qty") or ov.get("buffer_qty")
            or getattr(decision, "recommended_qty", None)
            or getattr(decision, "qty", None) or 0
        )
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 0

        product_id = getattr(decision, "product_id", None)
        site_id = (
            getattr(decision, "location_id", None)
            or getattr(decision, "site_id", None)
            or getattr(decision, "to_site", None)
        )
        from_site = getattr(decision, "from_site", None) or getattr(decision, "source_site_id", None)
        supplier_id = getattr(decision, "supplier_id", None) or ov.get("supplier_id")

        plan = SupplyPlan(
            config_id=config_id,
            product_id=str(product_id) if product_id else None,
            site_id=int(site_id) if site_id and str(site_id).isdigit() else None,
            plan_date=action_date,
            plan_type=plan_type,
            planned_order_quantity=qty,
            planned_order_date=action_date,
            supplier_id=str(supplier_id) if supplier_id else None,
            from_site_id=int(from_site) if from_site and str(from_site).isdigit() else None,
            planner_name="decision_stream",
            source="decision_action",
            source_event_id=f"{decision_type}:{decision.id}",
            plan_version="live",
        )
        self.db.add(plan)
        await self.db.commit()
        logger.info(
            "Supply plan adjustment created: type=%s decision=%s qty=%.1f",
            plan_type, decision.id, qty,
        )

    # ------------------------------------------------------------------
    # Hook: EK extraction
    # ------------------------------------------------------------------

    def _extract_ek_from_override(
        self, decision_type: str, decision_id: int, reason_text: str, reason_code: Optional[str],
    ) -> None:
        """Fire-and-forget: extract experiential knowledge from override text."""
        try:
            asyncio.get_event_loop().run_in_executor(
                None,
                _extract_ek_background,
                self.tenant_id, decision_type, decision_id, reason_text, reason_code,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Hook: forward-rolling decision impact
    # ------------------------------------------------------------------

    async def _evaluate_decision_impact(
        self, decisions: List[Dict], config_id: Optional[int],
    ) -> List[Dict]:
        """Remove decisions made redundant by earlier higher-priority decisions."""
        try:
            from app.services.decision_impact_ledger import DecisionImpactLedger
            ledger = DecisionImpactLedger(self.db, config_id or 0)
            return await ledger.evaluate_decisions(decisions)
        except Exception as e:
            logger.warning("Forward-rolling decision evaluation failed: %s", e)
            return decisions

    # ------------------------------------------------------------------
    # Hook: display identifiers
    # ------------------------------------------------------------------

    async def _get_display_identifiers(self) -> str:
        """Load tenant display preference from BSC config."""
        try:
            from app.db.session import sync_session_factory
            from app.models.bsc_config import TenantBscConfig as _Bsc
            _sync = sync_session_factory()
            try:
                _bsc = _sync.query(_Bsc).filter(_Bsc.tenant_id == self.tenant_id).first()
                if _bsc:
                    return getattr(_bsc, "display_identifiers", "name") or "name"
            finally:
                _sync.close()
        except Exception:
            pass
        return "name"

    # ------------------------------------------------------------------
    # Hook: tenant thresholds
    # ------------------------------------------------------------------

    def _load_tenant_thresholds(
        self,
    ) -> Tuple[float, float, float, Dict[str, Dict[str, float]]]:
        """Load urgency/likelihood/benefit thresholds from BSC config."""
        urgency_thresh = 0.65
        likelihood_thresh = 0.70
        benefit_thresh = 0.0
        per_trm_overrides: dict = {}

        try:
            from app.db.session import sync_session_factory
            from app.models.bsc_config import TenantBscConfig, TenantDecisionThreshold
            sync_db = sync_session_factory()
            try:
                bsc = sync_db.query(TenantBscConfig).filter(
                    TenantBscConfig.tenant_id == self.tenant_id
                ).first()
                if bsc:
                    urgency_thresh = bsc.urgency_threshold
                    likelihood_thresh = bsc.likelihood_threshold
                    benefit_thresh = getattr(bsc, "benefit_threshold", 0.0) or 0.0
                else:
                    logger.warning(
                        "No tenant_bsc_config for tenant %d — using defaults. Run provisioning.",
                        self.tenant_id,
                    )

                overrides = sync_db.query(TenantDecisionThreshold).filter(
                    TenantDecisionThreshold.tenant_id == self.tenant_id
                ).all()
                for ov in overrides:
                    per_trm_overrides[ov.trm_type] = {
                        "urgency": ov.urgency_threshold,
                        "likelihood": ov.likelihood_threshold,
                        "benefit": ov.benefit_threshold,
                    }
            finally:
                sync_db.close()
        except Exception:
            logger.warning("Failed to load tenant thresholds for tenant %d", self.tenant_id)

        return urgency_thresh, likelihood_thresh, benefit_thresh, per_trm_overrides

    # ------------------------------------------------------------------
    # Hook: persisted digest
    # ------------------------------------------------------------------

    async def _load_persisted_digest(
        self, config_id: int, decision_level: Optional[str], expected_count: Optional[int] = None,
    ) -> Optional[str]:
        """Load digest from decision_stream_digests table."""
        try:
            from app.db.session import sync_session_factory
            from sqlalchemy import text as sa_text
            role_clause = "AND powell_role = :role" if decision_level else "AND powell_role IS NULL"
            params: dict = {"cid": config_id, "tid": self.tenant_id}
            if decision_level:
                params["role"] = decision_level
            sync_db = sync_session_factory()
            try:
                result = sync_db.execute(
                    sa_text(
                        f"SELECT digest_text, total_pending FROM decision_stream_digests "
                        f"WHERE config_id = :cid AND tenant_id = :tid {role_clause} "
                        f"ORDER BY created_at DESC LIMIT 1"
                    ),
                    params,
                ).first()
                if result:
                    if expected_count is not None and result[1] != expected_count:
                        logger.info("Digest count mismatch (cached=%s, current=%s) — regenerating",
                                    result[1], expected_count)
                        return None
                    return result[0]
            finally:
                sync_db.close()
        except Exception as e:
            logger.debug("Digest DB load failed: %s", e)
        return None

    async def _persist_digest(
        self, config_id: int, decision_level: Optional[str],
        digest_text: str, decisions: list, alerts: list,
    ):
        """Persist digest to decision_stream_digests table (upsert)."""
        try:
            from app.db.session import sync_session_factory
            import json as _json
            from sqlalchemy import text as sa_text

            dec_json = _json.dumps(
                [{"id": d.get("id"), "decision_type": d.get("decision_type"),
                  "summary": d.get("summary"), "urgency": d.get("urgency")}
                 for d in decisions[:30]]
            )
            alerts_json = _json.dumps(alerts[:10] if alerts else [])

            sync_db = sync_session_factory()
            try:
                sync_db.execute(
                    sa_text("""
                        INSERT INTO decision_stream_digests
                            (config_id, tenant_id, powell_role, digest_text, decisions, alerts, total_pending, created_at)
                        VALUES (:cid, :tid, :role, :digest, CAST(:decs AS jsonb), CAST(:alerts AS jsonb), :total, CURRENT_TIMESTAMP)
                        ON CONFLICT (config_id, tenant_id, powell_role)
                        DO UPDATE SET digest_text = EXCLUDED.digest_text,
                                      decisions = EXCLUDED.decisions,
                                      alerts = EXCLUDED.alerts,
                                      total_pending = EXCLUDED.total_pending,
                                      created_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "cid": config_id, "tid": self.tenant_id, "role": decision_level,
                        "digest": digest_text, "decs": dec_json, "alerts": alerts_json,
                        "total": len(decisions),
                    },
                )
                sync_db.commit()
                logger.info("Digest persisted to DB (config=%d, role=%s)", config_id, decision_level)
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning("Digest persist failed: %s", e)

    async def _persist_digest_in_background(
        self, config_id: int, decision_level: Optional[str],
        digest_text: str, decisions: list, alerts: list,
    ) -> None:
        """Persist digest from background task using a fresh session."""
        try:
            from app.db.session import async_session_factory
            async with async_session_factory() as db:
                svc = DecisionStreamService(db=db, tenant_id=self.tenant_id, tenant_name=self.tenant_name)
                await svc._persist_digest(config_id, decision_level, digest_text, decisions, alerts)
        except Exception as e:
            logger.warning("Background digest persist failed: %s", e)

    # ------------------------------------------------------------------
    # Hook: alerts
    # ------------------------------------------------------------------

    async def _collect_alerts(self, config_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Collect CDC triggers and condition alerts from the last 48 hours."""
        alerts = []
        cutoff = datetime.utcnow() - timedelta(hours=_ALERT_LOOKBACK_HOURS)

        try:
            from app.models.powell_framework import PowellCDCTriggerLog
            query = select(PowellCDCTriggerLog).where(
                PowellCDCTriggerLog.triggered_at >= cutoff,
            ).order_by(desc(PowellCDCTriggerLog.triggered_at)).limit(_CDC_TRIGGER_LIMIT)

            result = await self.db.execute(query)
            rows = result.scalars().all()
            for row in rows:
                alerts.append({
                    "id": row.id,
                    "alert_type": getattr(row, "trigger_reason", "CDC_TRIGGER"),
                    "message": f"CDC trigger: {getattr(row, 'trigger_reason', 'unknown')} for {getattr(row, 'site_key', 'unknown site')}",
                    "severity": "warning",
                    "source": "cdc",
                    "created_at": row.triggered_at.isoformat() if row.triggered_at else None,
                    "context": {
                        "site_key": getattr(row, "site_key", None),
                        "action": getattr(row, "replan_action", None),
                    },
                })
        except Exception as e:
            logger.warning(f"Failed to query CDC triggers: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

        return alerts

    # ------------------------------------------------------------------
    # Hook: collect pending decisions (the big method)
    # ------------------------------------------------------------------

    async def _collect_pending_decisions(
        self,
        config_id: Optional[int] = None,
        decision_level: Optional[str] = None,
        level_override: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str]]:
        """Query powell_*_decisions tables + gnn_directive_reviews + governance sources."""
        # Level-based role filtering
        allowed_levels, type_filter, escalation_from = _get_role_filter_tms(decision_level, level_override)

        if allowed_levels is not None:
            relevant_types = set()
            for type_key, level in DECISION_LEVEL.items():
                if level in allowed_levels:
                    if type_filter is None or type_key in type_filter:
                        relevant_types.add(type_key)
            if escalation_from:
                for type_key, level in DECISION_LEVEL.items():
                    if level == escalation_from:
                        relevant_types.add(type_key)
        else:
            relevant_types = type_filter

        all_decisions = []
        cutoff = datetime.utcnow() - timedelta(days=_DECISION_LOOKBACK_DAYS)

        # Find config_ids for this tenant
        config_filter = None
        if config_id:
            try:
                result = await self.db.execute(
                    select(SupplyChainConfig.id).where(
                        SupplyChainConfig.id == config_id,
                        SupplyChainConfig.tenant_id == self.tenant_id,
                    )
                )
                row = result.first()
                config_filter = [config_id] if row else []
            except Exception:
                config_filter = []
        else:
            try:
                result = await self.db.execute(
                    select(SupplyChainConfig.id).where(
                        SupplyChainConfig.tenant_id == self.tenant_id,
                        SupplyChainConfig.is_active == True,
                    )
                )
                config_filter = [row[0] for row in result.fetchall()]
            except Exception as e:
                logger.warning(f"Failed to fetch tenant configs: {e}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass
                return [], {}, {}

        if not config_filter:
            return [], {}, {}

        # Resolve user's site/product scope
        allowed_sites, allowed_products = await self._resolve_user_scope()

        # Build product/site name lookup
        product_names: Dict[str, str] = {}
        site_names: Dict[str, str] = {}
        try:
            result = await self.db.execute(
                select(Product.id, Product.description).where(Product.config_id.in_(config_filter))
            )
            for pid, pdesc in result.fetchall():
                if pid and pdesc:
                    short_name = pdesc.split("[")[0].strip() if "[" in pdesc else pdesc
                    product_names[str(pid)] = short_name
                    spid = str(pid)
                    if "_" in spid:
                        suffix = spid.split("_", 1)[1]
                        if suffix not in product_names:
                            product_names[suffix] = short_name
        except Exception:
            pass

        try:
            result = await self.db.execute(
                select(Site.id, Site.name, Site.type).where(Site.config_id.in_(config_filter))
            )
            for sid, sname, stype in result.fetchall():
                display_name = stype if stype else sname
                if sname:
                    site_names[str(sname)] = display_name or sname
                    if sid is not None:
                        site_names[str(sid)] = display_name or sname
        except Exception as e:
            logger.warning(f"Failed to load site names: {e}")

        # Trading partner names
        partner_names: Dict[str, str] = {}
        try:
            from app.models.sc_entities import TradingPartner as _TP
            tp_result = await self.db.execute(select(_TP.id, _TP.description, _TP.tpartner_type))
            for tp_id, tp_desc, tp_type in tp_result.fetchall():
                if tp_id and tp_desc:
                    partner_names[str(tp_id)] = tp_desc
        except Exception as e:
            logger.warning(f"Failed to load trading partner names: {e}")

        name_cache = {"products": product_names, "sites": site_names}

        # Geography path cache for DecisionCard breadcrumb (Core v1.10.4)
        # Walk parent_geo_id chain per site → root-to-leaf path
        geo_paths: Dict[int, List[str]] = {}
        try:
            from app.models.sc_entities import Geography
            geo_rows = await self.db.execute(
                text("""
                    SELECT s.id AS site_id, s.name, s.geo_id,
                           g.id AS gid, g.description, g.country,
                           g.state_prov, g.parent_geo_id
                    FROM site s
                    LEFT JOIN geography g ON g.id = s.geo_id
                    WHERE s.config_id = ANY(:cids)
                """),
                {"cids": list(config_filter)},
            )
            # Build geo_data for chain walking
            geo_data: Dict[str, dict] = {}
            site_geo_map: Dict[int, str] = {}
            site_name_map: Dict[int, str] = {}
            for row in geo_rows.fetchall():
                sid, sname, sgeo, gid, gdesc, gcountry, gstate, gparent = row
                if gid:
                    geo_data[str(gid)] = {
                        "description": gdesc, "country": gcountry,
                        "state_prov": gstate,
                        "parent_geo_id": str(gparent) if gparent else None,
                    }
                if sid and sgeo:
                    site_geo_map[sid] = str(sgeo)
                if sid and sname:
                    site_name_map[sid] = sname

            # Load ancestor geography nodes
            to_load = {
                g["parent_geo_id"] for g in geo_data.values()
                if g["parent_geo_id"] and g["parent_geo_id"] not in geo_data
            }
            depth = 0
            while to_load and depth < 10:
                depth += 1
                anc_rows = await self.db.execute(
                    text("""
                        SELECT id, description, country, state_prov, parent_geo_id
                        FROM geography WHERE id = ANY(:ids)
                    """),
                    {"ids": list(to_load)},
                )
                next_load = set()
                for arow in anc_rows.fetchall():
                    gid = str(arow[0])
                    geo_data[gid] = {
                        "description": arow[1], "country": arow[2],
                        "state_prov": arow[3],
                        "parent_geo_id": str(arow[4]) if arow[4] else None,
                    }
                    if arow[4] and str(arow[4]) not in geo_data:
                        next_load.add(str(arow[4]))
                to_load = next_load

            # Build root-to-leaf path per site
            for sid, geo_id in site_geo_map.items():
                chain = []
                visited = set()
                current = geo_id
                while current and current in geo_data and current not in visited:
                    visited.add(current)
                    desc_label = geo_data[current].get("description") or geo_data[current].get("country") or current
                    chain.append(desc_label)
                    current = geo_data[current].get("parent_geo_id")
                chain.reverse()  # root → leaf
                # Append site name as the leaf
                if sid in site_name_map:
                    chain.append(site_name_map[sid])
                geo_paths[sid] = chain
        except Exception as e:
            logger.debug(f"Geography path build skipped: {e}")

        # Query all 11 TRM tables
        for model_class, type_key in DECISION_TABLES:
            if relevant_types is not None and type_key not in relevant_types:
                continue

            try:
                query = select(model_class).where(
                    and_(model_class.config_id.in_(config_filter), model_class.created_at >= cutoff)
                )
                if allowed_sites is not None:
                    site_clause = self._site_filter(type_key, model_class, allowed_sites)
                    if site_clause is not None:
                        query = query.where(site_clause)
                if allowed_products is not None and type_key not in _NO_PRODUCT_TABLES:
                    query = query.where(model_class.product_id.in_(allowed_products))

                urgency_col = getattr(model_class, "urgency_at_time", None)
                benefit_col = getattr(model_class, "expected_benefit", None)
                if urgency_col is not None and benefit_col is not None:
                    query = query.order_by(
                        desc(func.coalesce(urgency_col, 0)),
                        desc(func.coalesce(benefit_col, 0)),
                        desc(model_class.created_at),
                    )
                else:
                    query = query.order_by(desc(model_class.created_at))
                query = query.limit(_DECISIONS_PER_TABLE)

                result = await self.db.execute(query)
                rows = result.scalars().all()

                for row in rows:
                    # Extract site_id per table schema
                    if type_key == "rebalancing":
                        site_id = getattr(row, "from_site", None)
                    elif type_key == "order_tracking":
                        site_id = None
                    elif type_key in ("mo_execution", "quality", "maintenance", "subcontracting", "forecast_adjustment"):
                        site_id = getattr(row, "site_id", None)
                    elif type_key == "to_execution":
                        site_id = getattr(row, "source_site_id", None)
                    else:
                        site_id = getattr(row, "location_id", None)

                    pid = getattr(row, "product_id", None)
                    raw_reasoning = getattr(row, "decision_reasoning", None)
                    raw_cost = safe_float(getattr(row, "cost_of_inaction", None)) or 0.0
                    raw_tp = safe_float(getattr(row, "time_pressure", None)) or 0.0
                    raw_benefit = safe_float(getattr(row, "expected_benefit", None)) or 0.0

                    if raw_cost > 0 and raw_tp > 0:
                        computed_urgency = min(1.0, raw_cost * raw_tp / 1000.0)
                    else:
                        computed_urgency = safe_float(
                            getattr(row, "urgency_at_time", None) or getattr(row, "urgency", None)
                        )

                    raw_customer = getattr(row, "customer_id", None)
                    raw_vendor = getattr(row, "tpartner_id", None) or getattr(row, "vendor_id", None)
                    customer_name = partner_names.get(str(raw_customer)) if raw_customer else None
                    vendor_name = partner_names.get(str(raw_vendor)) if raw_vendor else None
                    row_status = getattr(row, "status", "ACTIONED") or "ACTIONED"
                    row_level = getattr(row, "decision_level", None) or DECISION_LEVEL.get(type_key, "execution")

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "status": row_status,
                        "decision_level": row_level,
                        "summary": humanize_ids(
                            self._build_decision_summary(row, type_key, name_cache=name_cache),
                            product_names, site_names,
                        ),
                        "product_id": pid,
                        "product_name": product_names.get(str(pid)) if pid else None,
                        "site_id": site_id,
                        "site_name": site_names.get(str(site_id)) if site_id else None,
                        "customer_name": customer_name,
                        "vendor_name": vendor_name,
                        "urgency": urgency_label(computed_urgency),
                        "urgency_score": computed_urgency,
                        "likelihood": likelihood_label(safe_float(getattr(row, "confidence", None))),
                        "likelihood_score": safe_float(getattr(row, "confidence", None)),
                        "cost_of_inaction": raw_cost if raw_cost > 0 else None,
                        "time_pressure": raw_tp if raw_tp > 0 else None,
                        "expected_benefit": raw_benefit if raw_benefit > 0 else None,
                        "economic_impact": raw_benefit if raw_benefit > 0 else None,
                        "reason": get_reason(row, type_key, TMS_REASON_COLUMN_MAP),
                        "decision_reasoning": humanize_ids(raw_reasoning, product_names, site_names) if raw_reasoning else None,
                        "suggested_action": humanize_ids(self._get_suggested_action(row, type_key), product_names, site_names),
                        "deep_link": DEEP_LINK_MAP.get(type_key, "/insights/actions"),
                        "effective_from": safe_effective_from(row, type_key, TMS_DATE_EXTRACTORS),
                        "period_days": safe_period_days(row, type_key, TMS_DATE_EXTRACTORS),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "geography_path": geo_paths.get(site_id) if site_id else None,
                        "editable_values": get_editable_values(row, type_key, EDITABLE_FIELDS_MAP),
                        "context": {
                            "config_id": row.config_id,
                            "decision_method": getattr(row, "decision_method", None),
                            "triggered_by": getattr(row, "triggered_by", None),
                            "from_site_id": getattr(row, "from_site", None) or getattr(row, "source_site_id", None),
                            "to_site_id": getattr(row, "to_site", None) or getattr(row, "dest_site_id", None),
                        },
                    })

                    # Enrich ATP/PO with pegging chain
                    if type_key in ("atp", "po_creation") and pid:
                        try:
                            pegging_chain = await self._get_pegging_chain(row.config_id, pid, str(site_id) if site_id else None)
                            if pegging_chain:
                                all_decisions[-1]["pegging_chain"] = pegging_chain
                        except Exception:
                            pass

            except Exception as e:
                import traceback
                logger.warning(f"Failed to query {type_key} decisions: {e}\n{traceback.format_exc()}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # Query GNN Directive Reviews
        gnn_types = {"sop_policy", "execution_directive", "network_directive", "allocation_refresh", "site_coordination"}
        if relevant_types is None or gnn_types & relevant_types:
            try:
                gnn_query = select(GNNDirectiveReview).where(
                    and_(GNNDirectiveReview.config_id.in_(config_filter), GNNDirectiveReview.created_at >= cutoff)
                )
                if relevant_types is not None:
                    active_gnn = gnn_types & relevant_types
                    if active_gnn:
                        scope_map = {t: t for t in gnn_types}
                        scopes = [scope_map[t] for t in active_gnn if t in scope_map]
                        gnn_query = gnn_query.where(GNNDirectiveReview.directive_scope.in_(scopes))

                gnn_query = gnn_query.order_by(desc(GNNDirectiveReview.created_at)).limit(20)
                gnn_result = await self.db.execute(gnn_query)
                gnn_rows = gnn_result.scalars().all()

                for row in gnn_rows:
                    scope = row.directive_scope
                    type_key = scope
                    level = getattr(row, "decision_level", None) or DECISION_LEVEL.get(type_key, "tactical")
                    confidence = row.model_confidence or 0.5

                    # Vertical Urgency Propagation
                    propagated = safe_float(getattr(row, "propagated_urgency", None))
                    if propagated and propagated > 0:
                        gnn_urgency = propagated
                    else:
                        proposed = row.proposed_values or {}
                        if scope == "sop_policy":
                            gnn_urgency = max(proposed.get("bottleneck_risk", 0), proposed.get("concentration_risk", 0), 0.3)
                        elif scope == "execution_directive":
                            exc_prob = proposed.get("exception_probability", [0, 0, 1])
                            gnn_urgency = max(exc_prob[0] if isinstance(exc_prob, list) and len(exc_prob) > 0 else 0, 0.3)
                        else:
                            gnn_urgency = 0.5

                    proposed = row.proposed_values or {}
                    source_signals = getattr(row, "source_signals", None) or []
                    blocked_by = getattr(row, "local_resolution_blocked_by", None)
                    revenue = safe_float(getattr(row, "revenue_at_risk", None))
                    cost_delay = safe_float(getattr(row, "cost_of_delay_per_day", None))
                    site_display = site_names.get(str(row.site_key), row.site_key)

                    summary, action = self._build_gnn_summary(
                        scope, proposed, site_display, product_names, site_names,
                    )

                    # Enrich reasoning with escalation context
                    reasoning_parts = []
                    if row.proposed_reasoning:
                        reasoning_parts.append(row.proposed_reasoning)
                    if source_signals:
                        sig_descs = []
                        for sig in source_signals[:3]:
                            agent_key = sig.get('agent_type', sig.get('trm_type', '?'))
                            agent_label = _DIGEST_TYPE_LABELS.get(agent_key, agent_key.replace('_', ' ').title())
                            sig_descs.append(
                                f"{agent_label}: {sig.get('observation', sig.get('signal_type', '?'))}"
                                f" (urgency {sig.get('urgency', 0):.0%})"
                            )
                        reasoning_parts.append("Escalated from: " + "; ".join(sig_descs))
                    if blocked_by:
                        reasoning_parts.append(f"Local resolution blocked: {blocked_by}")
                    if revenue and revenue > 0:
                        reasoning_parts.append(f"Revenue at risk: ${revenue:,.0f}")
                    if cost_delay and cost_delay > 0:
                        reasoning_parts.append(f"Cost of delay: ${cost_delay:,.0f}/day")
                    _alloc_qty = proposed.get("quantity", 0) if proposed else 0
                    if not revenue and not cost_delay and _alloc_qty:
                        try:
                            qty_val = float(_alloc_qty)
                            reasoning_parts.append(
                                f"**Financial impact**: Holding cost exposure ~${qty_val * 2.0:,.0f}/week, "
                                f"stockout cost exposure ~${qty_val * 5.0:,.0f}/week"
                            )
                        except (TypeError, ValueError):
                            pass

                    enriched_reasoning = " | ".join(reasoning_parts) if reasoning_parts else None
                    gnn_pid = proposed.get("product_id")
                    gnn_pname = product_names.get(str(gnn_pid)) if gnn_pid else None
                    gnn_eff_from = row.created_at.date().isoformat() if row.created_at else None
                    gnn_period = 14
                    if scope == "sop_policy":
                        gnn_period = 28
                    elif scope == "site_coordination":
                        gnn_period = 7

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "decision_level": level,
                        "summary": summary,
                        "product_id": gnn_pid,
                        "product_name": gnn_pname,
                        "site_id": row.site_key,
                        "site_name": site_display,
                        "urgency": urgency_label(gnn_urgency),
                        "urgency_score": gnn_urgency,
                        "likelihood": likelihood_label(confidence),
                        "likelihood_score": confidence,
                        "cost_of_inaction": cost_delay if cost_delay and cost_delay > 0 else None,
                        "time_pressure": None,
                        "expected_benefit": None,
                        "economic_impact": revenue if revenue and revenue > 0 else None,
                        "reason": enriched_reasoning,
                        "decision_reasoning": enriched_reasoning,
                        "suggested_action": action,
                        "deep_link": "/admin/powell" if scope == "sop_policy" else "/insights/actions",
                        "effective_from": gnn_eff_from,
                        "period_days": gnn_period,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "editable_values": row.proposed_values,
                        "context": {
                            "config_id": row.config_id,
                            "model_type": row.model_type,
                            "directive_scope": scope,
                            "gnn_status": row.status,
                            "source_signals": source_signals if source_signals else None,
                            "local_resolution_blocked_by": blocked_by,
                            "escalation_id": getattr(row, "escalation_id", None),
                            "from_site_id": proposed.get("from_site"),
                            "to_site_id": proposed.get("to_site"),
                        },
                    })
            except Exception as e:
                logger.warning(f"Failed to query GNN directives: {e}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # Query Governance Decisions
        governance_types = {"directive", "guardrail_change", "policy_envelope_change"}
        if relevant_types is None or governance_types & relevant_types:
            try:
                from app.models.user_directive import UserDirective
                dir_query = select(UserDirective).where(
                    and_(
                        UserDirective.config_id.in_(config_filter),
                        UserDirective.created_at >= cutoff,
                        UserDirective.parsed_intent == "directive",
                    )
                ).order_by(desc(UserDirective.created_at)).limit(10)
                dir_result = await self.db.execute(dir_query)
                dir_rows = dir_result.scalars().all()

                for row in dir_rows:
                    layer = getattr(row, "target_layer", "strategic")
                    metric = getattr(row, "parsed_metric", "")
                    direction = getattr(row, "parsed_direction", "")
                    magnitude = getattr(row, "parsed_magnitude_pct", None)

                    summary_parts = []
                    if direction:
                        summary_parts.append(direction.capitalize())
                    if metric:
                        summary_parts.append(metric.replace("_", " "))
                    if magnitude:
                        summary_parts.append(f"{magnitude:.0f}%")
                    summary = f"Directive: {' '.join(summary_parts)}" if summary_parts else f"Directive: {row.raw_text[:60]}"

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": "directive",
                        "decision_level": "governance",
                        "summary": summary,
                        "product_id": None,
                        "product_name": None,
                        "site_id": None,
                        "site_name": "Network-wide" if layer == "strategic" else (
                            ", ".join(row.target_site_keys) if row.target_site_keys else None
                        ),
                        "urgency": "Medium",
                        "urgency_score": 0.5,
                        "likelihood": "Certain",
                        "likelihood_score": 1.0,
                        "cost_of_inaction": None,
                        "time_pressure": None,
                        "expected_benefit": None,
                        "economic_impact": None,
                        "reason": row.raw_text,
                        "decision_reasoning": f"User directive routed to {layer} layer. {row.reason_code or ''}",
                        "suggested_action": f"Routed to {layer}: {', '.join(row.target_trm_types) if row.target_trm_types else 'all agents'}",
                        "deep_link": "/directives",
                        "effective_from": row.created_at.date().isoformat() if row.created_at else None,
                        "period_days": 28,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "editable_values": row.parsed_scope,
                        "context": {
                            "config_id": row.config_id,
                            "directive_type": row.directive_type,
                            "target_layer": layer,
                            "status": row.status,
                            "user_id": row.user_id,
                        },
                    })
            except Exception as e:
                logger.warning(f"Failed to query governance decisions: {e}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # Rebalancing cooldown dedup
        if _REBALANCE_COOLDOWN_HOURS > 0:
            seen_rebalance: dict = {}
            deduped = []
            for d in all_decisions:
                if d.get("decision_type") == "rebalancing":
                    ev = d.get("editable_values") or {}
                    key = f"{d.get('product_id')}|{ev.get('from_site_id')}|{ev.get('to_site_id')}"
                    prev = seen_rebalance.get(key)
                    if prev is None:
                        seen_rebalance[key] = d
                        deduped.append(d)
                    else:
                        if (d.get("urgency_score") or 0) > (prev.get("urgency_score") or 0):
                            deduped = [x for x in deduped if x is not prev]
                            seen_rebalance[key] = d
                            deduped.append(d)
                else:
                    deduped.append(d)
            all_decisions = deduped

        # Post-filter: escalation passthrough
        if allowed_levels and escalation_from:
            filtered = []
            for d in all_decisions:
                d_level = d.get("decision_level", "execution")
                if d_level in allowed_levels:
                    filtered.append(d)
                elif d_level == escalation_from:
                    ctx = d.get("context", {})
                    has_escalation = (
                        ctx.get("source_signals") or ctx.get("escalation_id")
                        or (d.get("urgency_score") or 0) >= 0.75
                    )
                    if has_escalation:
                        filtered.append(d)
            all_decisions = filtered

        # Consolidate per-period decisions
        all_decisions = consolidate_decisions(all_decisions, product_names, site_names)

        return all_decisions, product_names, site_names

    # ------------------------------------------------------------------
    # GNN summary builder (extracted for readability)
    # ------------------------------------------------------------------

    def _build_gnn_summary(
        self, scope: str, proposed: dict,
        site_display: str, product_names: dict, site_names: dict,
    ) -> Tuple[str, str]:
        """Build summary and action text for a GNN directive review."""
        if scope == "sop_policy":
            policy_action = proposed.get("action", "")
            policy_param = proposed.get("policy_parameter", "")
            proposed_val = proposed.get("proposed_value")
            change_pct = proposed.get("change_pct")
            ss_mult = proposed.get("safety_stock_multiplier", None)

            if policy_action:
                action_desc = policy_action.replace("_", " ").title()
                return f"Strategic Policy: {action_desc} at {site_display}", f"Review: {action_desc}"
            elif policy_param and proposed_val is not None:
                param_label = policy_param.replace("_", " ").title()
                change_str = f" ({change_pct:+.1f}%)" if change_pct else ""
                return f"Strategic Policy: {param_label} -> {proposed_val}{change_str}", f"Review {param_label} adjustment"
            elif ss_mult and ss_mult != 1.0:
                return (
                    f"Strategic Policy: Safety stock adjustment to {ss_mult:.2f}x at {site_display}",
                    f"Review safety stock multiplier {ss_mult:.2f}x",
                )
            else:
                return f"Strategic Policy Review at {site_display}", "Review strategic policy recommendation"

        elif scope == "execution_directive":
            alloc_action = proposed.get("allocation_action", "")
            alloc_qty = proposed.get("quantity", 0)
            from_site = proposed.get("from_site", "")
            to_site = proposed.get("to_site", "")
            alloc_pid = proposed.get("product_id", "")
            alloc_pdesc = product_names.get(str(alloc_pid), alloc_pid) if alloc_pid else ""
            order_rec = proposed.get("order_recommendation", 0)
            demand_fcst = proposed.get("demand_forecast", None)
            alloc = proposed.get("allocation", None)
            coord_action = proposed.get("coordination_action", "")

            if alloc_action and alloc_qty:
                _action_labels = {
                    "pre_position": "Transfer", "reallocate": "Reallocate",
                    "demand_shift": "Redirect", "rebalance": "Rebalance",
                    "expedite": "Expedite", "consolidate": "Consolidate",
                }
                action_label = _action_labels.get(alloc_action, alloc_action.replace("_", " ").title())
                from_display = site_names.get(str(from_site), from_site) if from_site else "?"
                to_display = site_names.get(str(to_site), to_site) if to_site else "?"
                summary = f"{action_label} {int(alloc_qty)} units of {alloc_pdesc} from {from_display} to {to_display}"
                return summary, f"{action_label} {int(alloc_qty)} units from {from_display} -> {to_display}"
            elif coord_action:
                action_label = coord_action.replace("_", " ").title()
                return f"Site Coordination: {action_label} at {site_display}", f"Review: {action_label}"
            elif order_rec and order_rec > 0:
                return f"Planning Directive: {order_rec:.0f} units at {site_display}", f"Execute {order_rec:.0f} unit order"
            elif demand_fcst:
                return f"Demand Forecast Update at {site_display}", f"Review demand forecast: {demand_fcst}"
            elif alloc:
                return f"Allocation Directive at {site_display}", "Review allocation adjustment"
            else:
                return f"Planning Directive at {site_display}", "Review planning recommendation"

        return f"Allocation Update at {site_display}", "Review and approve allocation changes"

    # ------------------------------------------------------------------
    # Hook: pegging chain
    # ------------------------------------------------------------------

    async def _get_pegging_chain(
        self, config_id: int, product_id: str, site_id: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Look up the pegging chain for a product at a site."""
        try:
            from app.models.pegging import SupplyDemandPegging
            query = select(SupplyDemandPegging).where(
                and_(
                    SupplyDemandPegging.config_id == config_id,
                    SupplyDemandPegging.product_id == product_id,
                    SupplyDemandPegging.is_active == True,
                )
            ).order_by(SupplyDemandPegging.chain_depth).limit(10)

            result = await self.db.execute(query)
            rows = result.scalars().all()
            if not rows:
                return None

            return [
                {
                    "depth": r.chain_depth,
                    "demand_type": r.demand_type if isinstance(r.demand_type, str) else r.demand_type.value,
                    "demand_id": r.demand_id,
                    "supply_type": r.supply_type if isinstance(r.supply_type, str) else r.supply_type.value,
                    "supply_id": r.supply_id,
                    "pegged_qty": r.pegged_quantity,
                    "status": r.pegging_status if isinstance(r.pegging_status, str) else r.pegging_status.value,
                    "chain_id": r.chain_id,
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug("Pegging chain lookup failed for %s: %s", product_id, e)
            return None

    # ------------------------------------------------------------------
    # Hook: DAG topology
    # ------------------------------------------------------------------

    async def _get_dag_topology(self, config_id: Optional[int] = None) -> str:
        """Load the SC config DAG topology + product catalog for LLM context."""
        if not config_id:
            return ""
        try:
            from app.models.sc_entities import Product as _Prod, TradingPartner

            prefix = f"CFG{config_id}_"
            parts = []

            result = await self.db.execute(
                select(Site.name, Site.type, Site.master_type, Site.attributes).where(Site.config_id == config_id)
            )
            sites = result.fetchall()
            if sites:
                internal_lines, vendor_lines, customer_lines = [], [], []
                for s_name, s_type, s_master, s_attrs in sites:
                    display = s_name
                    if s_attrs and isinstance(s_attrs, dict):
                        display = s_attrs.get("customer_name") or s_attrs.get("supplier_name") or s_attrs.get("name") or s_name
                    elif s_type and " - " in str(s_type):
                        display = str(s_type).split(" - ", 1)[-1]

                    if s_master == "INVENTORY":
                        internal_lines.append(f"{s_name}: {s_type or display}")
                    elif s_master == "VENDOR":
                        vendor_lines.append(f"{s_name}: {display}")
                    elif s_master == "CUSTOMER":
                        customer_lines.append(f"{s_name}: {display}")

                if internal_lines:
                    parts.append(f"INTERNAL SITES:\n" + "\n".join(f"  {l}" for l in internal_lines))
                if vendor_lines:
                    parts.append(f"SUPPLIERS ({len(vendor_lines)}):\n" + "\n".join(f"  {l}" for l in sorted(vendor_lines)))
                if customer_lines:
                    parts.append(f"CUSTOMERS ({len(customer_lines)}):\n" + "\n".join(f"  {l}" for l in sorted(customer_lines)))

            result = await self.db.execute(
                select(_Prod.product_group_name).where(
                    _Prod.config_id == config_id, _Prod.product_group_name.isnot(None),
                ).distinct().limit(30)
            )
            groups = [r[0] for r in result.fetchall() if r[0]]
            if groups:
                parts.append(f"Product categories: {', '.join(sorted(groups))}")

            result = await self.db.execute(
                select(_Prod.id, _Prod.description, _Prod.product_group_name, _Prod.unit_of_measure).where(
                    _Prod.config_id == config_id
                ).order_by(_Prod.id).limit(500)
            )
            all_products = result.fetchall()
            if all_products:
                product_lines = []
                for p_id, p_desc, p_group, p_uom in all_products:
                    sku = p_id.replace(prefix, "") if p_id.startswith(prefix) else p_id
                    line = f"  {sku}: {p_desc or 'N/A'}"
                    if p_group:
                        line += f" [{p_group}]"
                    product_lines.append(line)
                parts.append(f"PRODUCT CATALOG ({len(all_products)} products):\n" + "\n".join(product_lines))

            try:
                from app.models.supplier import VendorProduct
                vp_result = await self.db.execute(
                    select(VendorProduct.product_id, VendorProduct.tpartner_id).where(
                        VendorProduct.product_id.like(f"{prefix}%")
                    ).limit(200)
                )
                vp_rows = vp_result.fetchall()
                if vp_rows:
                    vp_map: dict = {}
                    for p_id, vendor in vp_rows:
                        sku = p_id.replace(prefix, "")
                        vendor_name = vendor.replace(prefix, "") if vendor and vendor.startswith(prefix) else vendor
                        vp_map.setdefault(vendor_name, []).append(sku)
                    vp_lines = [f"  {v}: {', '.join(skus)}" for v, skus in sorted(vp_map.items())]
                    parts.append(f"SUPPLIER-PRODUCT MAPPING:\n" + "\n".join(vp_lines))
            except Exception:
                pass

            for tp_type, label in [("vendor", "Vendors"), ("customer", "Customers")]:
                result = await self.db.execute(
                    select(TradingPartner.id, TradingPartner.description).where(
                        TradingPartner.id.like(f"{prefix}%"),
                        TradingPartner.tpartner_type == tp_type,
                    ).limit(50)
                )
                tp_rows = result.fetchall()
                if tp_rows:
                    tp_list = [f"{r[0].replace(prefix, '')}: {r[1]}" if r[1] else r[0].replace(prefix, "") for r in tp_rows]
                    parts.append(f"{label}: {', '.join(tp_list)}")

            if parts:
                return "=== SUPPLY CHAIN TOPOLOGY & PRODUCT CATALOG ===\n" + "\n".join(parts) + "\n=== END TOPOLOGY ==="
            return ""
        except Exception as e:
            logger.debug("DAG topology load failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Hook: BSC context
    # ------------------------------------------------------------------

    async def _get_bsc_context(self, config_id: Optional[int] = None) -> str:
        """Load balanced scorecard data for performance comparisons."""
        if not config_id:
            return ""
        try:
            from sqlalchemy import text as _t
            parts = []

            result = await self.db.execute(
                _t("""
                    SELECT category, decision_type,
                           total_decisions, agent_decisions, planner_decisions,
                           agent_score, planner_score, override_rate,
                           automation_percentage, active_agents
                    FROM performance_metrics
                    WHERE tenant_id = :tid AND period_type = 'weekly'
                    ORDER BY period_end DESC, category
                    LIMIT 20
                """),
                {"tid": self.tenant_id},
            )
            rows = result.fetchall()
            if rows:
                metrics = []
                for r in rows:
                    cat = r[0] or "Overall"
                    agent_s = f"agent score: {r[5]}" if r[5] else ""
                    auto_pct = f"automation: {r[8]:.0f}%" if r[8] else ""
                    override = f"override rate: {r[7]:.0f}%" if r[7] else ""
                    detail = ", ".join(filter(None, [agent_s, auto_pct, override]))
                    metrics.append(f"  {cat}: {r[2]} decisions ({detail})")
                parts.append("Weekly Performance (latest):\n" + "\n".join(metrics))

            cid = config_id or 0
            result = await self.db.execute(
                _t("""
                    SELECT 'ATP Agent' as agent, COUNT(*) as decisions, AVG(confidence) as avg_confidence
                    FROM powell_atp_decisions WHERE config_id = :cid
                    UNION ALL SELECT 'Procurement Agent', COUNT(*), AVG(confidence) FROM powell_po_decisions WHERE config_id = :cid
                    UNION ALL SELECT 'Rebalancing Agent', COUNT(*), AVG(confidence) FROM powell_rebalance_decisions WHERE config_id = :cid
                    UNION ALL SELECT 'Demand Agent', COUNT(*), AVG(confidence) FROM powell_forecast_adjustment_decisions WHERE config_id = :cid
                    UNION ALL SELECT 'Inventory Agent', COUNT(*), AVG(confidence) FROM powell_buffer_decisions WHERE config_id = :cid
                """),
                {"cid": cid},
            )
            rows = result.fetchall()
            if rows:
                agent_lines = []
                for r in rows:
                    if r[1] and r[1] > 0:
                        conf = f" (avg confidence: {r[2]:.0%})" if r[2] else ""
                        agent_lines.append(f"  {r[0]}: {r[1]} decisions{conf}")
                if agent_lines:
                    parts.append("Agent Decision Summary:\n" + "\n".join(agent_lines))

            result = await self.db.execute(
                _t("""
                    SELECT s.name, s.type, COUNT(DISTINCT il.product_id) as products, SUM(il.on_hand_qty) as total_on_hand
                    FROM inv_level il JOIN site s ON s.id = il.site_id
                    WHERE il.config_id = :cid GROUP BY s.name, s.type ORDER BY total_on_hand DESC
                """),
                {"cid": cid},
            )
            rows = result.fetchall()
            if rows:
                inv_lines = [f"  {r[0]} ({r[1]}): {r[2]} products, {r[3]:,.0f} units on hand" for r in rows]
                parts.append("Inventory by Site:\n" + "\n".join(inv_lines))

            if parts:
                return "=== BALANCED SCORECARD & KPI DATA ===\n" + "\n\n".join(parts) + "\n=== END BSC ==="
            return ""
        except Exception as e:
            logger.debug("BSC context load failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Hook: external signals
    # ------------------------------------------------------------------

    async def _get_external_signals_context(self) -> str:
        """Load recent external market intelligence."""
        try:
            from app.services.external_signal_service import ExternalSignalService
            service = ExternalSignalService(self.db, self.tenant_id)
            return await service.get_signals_for_chat_context(max_signals=8, max_age_days=7)
        except Exception as e:
            logger.debug("External signals context load failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Hook: experiential knowledge
    # ------------------------------------------------------------------

    async def _get_experiential_knowledge_context(self) -> str:
        """Load active experiential knowledge for planner behavioral patterns."""
        try:
            from app.services.experiential_knowledge_service import ExperientialKnowledgeService
            from app.db.session import sync_session_factory
            sync_db = sync_session_factory()
            try:
                service = ExperientialKnowledgeService(
                    db=sync_db, tenant_id=self.tenant_id,
                    config_id=getattr(self, "config_id", None),
                )
                return service.get_knowledge_for_chat_context(max_entities=8)
            finally:
                sync_db.close()
        except Exception as e:
            logger.debug("Experiential knowledge context load failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Hook: RAG retrieval
    # ------------------------------------------------------------------

    async def _retrieve_context(self, query: str) -> list:
        """Retrieve RAG context from knowledge base."""
        try:
            results = await self.kb.search(query=query, top_k=3)
            return results
        except Exception as e:
            logger.warning(f"RAG search failed (non-fatal): {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return []

    # ------------------------------------------------------------------
    # Hook: enrichment from message
    # ------------------------------------------------------------------

    async def _enrich_from_message(
        self, message: str, history: List[Dict[str, str]], config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Detect referenced decisions/products and fetch real data for inline display."""
        data_blocks: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        product_lookup, site_lookup = await self._load_tenant_vocabulary(config_id)

        texts_to_scan = [message]
        for m in history[-_ENRICHMENT_HISTORY_WINDOW:]:
            texts_to_scan.append(m.get("content", ""))
        combined_lower = " ".join(texts_to_scan).lower()

        product_ids = {canonical for token, canonical in product_lookup.items() if token in combined_lower}
        site_ids = {canonical for token, canonical in site_lookup.items() if token in combined_lower}

        clarifications = []

        async def _product_options(product_id_set=None):
            q = select(Product.id, Product.description).order_by(Product.id).limit(50)
            if product_id_set:
                q = q.where(Product.id.in_(list(product_id_set)))
            else:
                q = q.where(Product.config_id == config_id)
            result = await self.db.execute(q)
            return [f"{r[0].replace(f'CFG{config_id}_', '')} — {r[1] or 'N/A'}" for r in result.fetchall()]

        async def _site_options(site_name_set=None, master_type=None):
            q = select(Site.name, Site.type, Site.attributes).where(Site.config_id == config_id).order_by(Site.name)
            if master_type:
                q = q.where(Site.master_type == master_type)
            result = await self.db.execute(q)
            options = []
            for sname, stype, sattrs in result.fetchall():
                if site_name_set and sname not in site_name_set:
                    continue
                display = sname
                if sattrs and isinstance(sattrs, dict):
                    display = sattrs.get("customer_name") or sattrs.get("supplier_name") or sname
                elif stype and " - " in str(stype):
                    display = str(stype).split(" - ", 1)[-1]
                options.append(f"{sname} — {display}")
            return options

        if len(product_ids) > 3:
            clarifications.append({
                "field": "product", "question": "Which of these PRODUCTS do you mean?",
                "category": "PRODUCTS", "type": "select",
                "options": await _product_options(product_ids),
                "searchable": True, "none_option": True, "required": True,
            })

        if len(site_ids) > 3:
            clarifications.append({
                "field": "site", "question": "Which of these SITES do you mean?",
                "category": "SITES", "type": "select",
                "options": await _site_options(site_ids),
                "searchable": True, "none_option": True, "required": True,
            })

        if not product_ids and any(kw in combined_lower for kw in (
            "product", "sku", "item", "beef", "chicken", "pork", "dairy",
            "cheese", "yogurt", "butter", "juice", "ice cream", "pasta",
            "wagyu", "wagu", "seafood", "turkey",
        )):
            opts = await _product_options()
            if opts:
                clarifications.append({
                    "field": "product", "question": "Which of these PRODUCTS do you mean?",
                    "category": "PRODUCTS", "type": "select", "options": opts,
                    "searchable": True, "none_option": True, "required": True,
                })

        if not site_ids and any(kw in combined_lower for kw in (
            "site", "warehouse", "dc", "customer", "supplier", "location", "region", "store", "deliver",
        )):
            if any(kw in combined_lower for kw in ("customer", "deliver", "store")):
                category, master = "CUSTOMERS", "CUSTOMER"
            elif any(kw in combined_lower for kw in ("supplier", "vendor")):
                category, master = "SUPPLIERS", "VENDOR"
            else:
                category, master = "SITES", None
            opts = await _site_options(master_type=master)
            if opts:
                clarifications.append({
                    "field": "site", "question": f"Which of these {category} do you mean?",
                    "category": category, "type": "select", "options": opts,
                    "searchable": True, "none_option": True, "required": False,
                })

        decision_type_hint = None
        if "forecast" in combined_lower:
            decision_type_hint = "forecast_adjustment"
        elif "rebalanc" in combined_lower:
            decision_type_hint = "rebalancing"
        elif "atp" in combined_lower or "fulfill" in combined_lower:
            decision_type_hint = "atp"
        elif any(k in combined_lower for k in ("po ", "purchase", "order qty")):
            decision_type_hint = "po_creation"
        elif "buffer" in combined_lower or "safety stock" in combined_lower:
            decision_type_hint = "inventory_buffer"
        elif "maintenance" in combined_lower:
            decision_type_hint = "maintenance"
        elif "quality" in combined_lower:
            decision_type_hint = "quality"
        elif "subcontract" in combined_lower:
            decision_type_hint = "subcontracting"

        if not product_ids and not site_ids:
            return {"data_blocks": [], "context_text": "", "clarifications": clarifications}

        try:
            inv_data = await self._fetch_inventory_data(product_ids, site_ids, config_id)
            if inv_data:
                data_blocks.append({
                    "block_type": "table", "title": "Current Inventory Position",
                    "data": {"columns": ["Product", "Site", "On Hand", "In Transit", "Allocated", "Available", "Safety Stock"], "rows": inv_data["rows"]},
                })
                context_parts.append("=== LIVE INVENTORY DATA ===\n" + inv_data["text"] + "\n=== END INVENTORY ===")

            fcst_data = await self._fetch_forecast_data(product_ids, site_ids, config_id)
            if fcst_data:
                data_blocks.append({
                    "block_type": "table", "title": "Forecast (Next 4 Periods)",
                    "data": {"columns": ["Product", "Period", "P10", "P50 (Base)", "P90", "Method"], "rows": fcst_data["rows"]},
                })
                context_parts.append("=== LIVE FORECAST DATA ===\n" + fcst_data["text"] + "\n=== END FORECAST ===")

            policy_data = await self._fetch_policy_data(product_ids, site_ids, config_id)
            if policy_data:
                data_blocks.append({"block_type": "metrics_row", "title": "Inventory Policy", "data": {"metrics": policy_data["metrics"]}})
                context_parts.append("=== INVENTORY POLICY ===\n" + policy_data["text"] + "\n=== END POLICY ===")

            decision_detail = await self._fetch_decision_detail(product_ids, decision_type_hint, config_id)
            if decision_detail:
                data_blocks.append({"block_type": "metrics_row", "title": "Decision Detail", "data": {"metrics": decision_detail["metrics"]}})
                context_parts.append("=== DECISION DETAIL ===\n" + decision_detail["text"] + "\n=== END DETAIL ===")
        except Exception as e:
            logger.warning(f"Data enrichment failed (non-fatal): {e}")

        return {"data_blocks": data_blocks, "context_text": "\n\n".join(context_parts), "clarifications": clarifications}

    # ------------------------------------------------------------------
    # Data fetchers for enrichment
    # ------------------------------------------------------------------

    async def _fetch_inventory_data(self, product_ids: set, site_ids: set, config_id: Optional[int]) -> Optional[Dict]:
        """Fetch current inventory levels for mentioned products."""
        try:
            query = select(InvLevel).where(InvLevel.product_id.in_(product_ids))
            if config_id:
                query = query.where(InvLevel.config_id == config_id)
            query = query.order_by(desc(InvLevel.inventory_date)).limit(_INVENTORY_FETCH_LIMIT)
            result = await self.db.execute(query)
            rows_raw = result.scalars().all()
            if not rows_raw:
                return None

            seen = set()
            rows, text_lines = [], []
            for r in rows_raw:
                key = (r.product_id, r.site_id)
                if key in seen:
                    continue
                seen.add(key)
                on_hand = r.on_hand_qty or 0
                in_transit = r.in_transit_qty or 0
                allocated = r.allocated_qty or 0
                available = r.available_qty or (on_hand - allocated)
                ss = r.safety_stock_qty or 0
                rows.append([str(r.product_id), str(r.site_id or ""),
                            f"{on_hand:,.0f}", f"{in_transit:,.0f}", f"{allocated:,.0f}", f"{available:,.0f}", f"{ss:,.0f}"])
                text_lines.append(f"  {r.product_id} @ site {r.site_id}: on_hand={on_hand:.0f}, in_transit={in_transit:.0f}, allocated={allocated:.0f}, available={available:.0f}, safety_stock={ss:.0f}")
            return {"rows": rows, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Inventory data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_forecast_data(self, product_ids: set, site_ids: set, config_id: Optional[int]) -> Optional[Dict]:
        """Fetch recent forecasts for mentioned products."""
        try:
            query = select(Forecast).where(Forecast.product_id.in_(product_ids))
            if config_id:
                query = query.where(Forecast.config_id == config_id)
            query = query.order_by(desc(Forecast.forecast_date)).limit(_FORECAST_FETCH_LIMIT)
            result = await self.db.execute(query)
            rows_raw = result.scalars().all()
            if not rows_raw:
                return None

            seen_count: Dict[str, int] = {}
            deduped = []
            for r in rows_raw:
                p = r.product_id or ""
                seen_count[p] = seen_count.get(p, 0) + 1
                if seen_count[p] <= _FORECAST_PERIODS_PER_PRODUCT:
                    deduped.append(r)

            rows, text_lines = [], []
            for r in deduped[:_FORECAST_DISPLAY_MAX]:
                p10 = r.forecast_p10 or 0
                p50 = r.forecast_p50 or r.forecast_quantity or 0
                p90 = r.forecast_p90 or 0
                method = r.forecast_method or "unknown"
                period = str(r.forecast_date) if r.forecast_date else "?"
                rows.append([str(r.product_id), period, f"{p10:,.0f}", f"{p50:,.0f}", f"{p90:,.0f}", method])
                text_lines.append(f"  {r.product_id} period {period}: P10={p10:.0f}, P50={p50:.0f}, P90={p90:.0f}, method={method}")
            return {"rows": rows, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Forecast data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_policy_data(self, product_ids: set, site_ids: set, config_id: Optional[int]) -> Optional[Dict]:
        """Fetch inventory policies for mentioned products."""
        try:
            query = select(InvPolicy).where(InvPolicy.product_id.in_(product_ids))
            if config_id:
                query = query.where(InvPolicy.config_id == config_id)
            query = query.limit(_POLICY_FETCH_LIMIT)
            result = await self.db.execute(query)
            rows_raw = result.scalars().all()
            if not rows_raw:
                return None

            seen = set()
            metrics, text_lines = [], []
            for r in rows_raw:
                if r.product_id in seen:
                    continue
                seen.add(r.product_id)
                policy_type = r.ss_policy or "unknown"
                ss_qty = r.ss_quantity or 0
                ss_days = r.ss_days or 0
                sl = r.service_level or 0
                metrics.append({"label": "Policy", "value": policy_type})
                if ss_qty:
                    metrics.append({"label": "Safety Stock", "value": f"{ss_qty:,.0f}", "unit": "units"})
                if ss_days:
                    metrics.append({"label": "SS Days", "value": str(ss_days), "unit": "days"})
                if sl:
                    metrics.append({"label": "SL Target", "value": f"{sl*100:.0f}", "unit": "%"})
                text_lines.append(f"  {r.product_id}: policy={policy_type}, ss_qty={ss_qty:.0f}, ss_days={ss_days}, service_level={sl:.2f}")
            return {"metrics": metrics, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Policy data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_decision_detail(self, product_ids: set, decision_type: Optional[str], config_id: Optional[int]) -> Optional[Dict]:
        """Fetch the specific decision record with full detail."""
        if not decision_type:
            return None

        model_class = None
        for cls, type_key in DECISION_TABLES:
            if type_key == decision_type:
                model_class = cls
                break
        if not model_class:
            return None

        try:
            query = select(model_class).where(model_class.product_id.in_(product_ids))
            if config_id:
                query = query.where(model_class.config_id == config_id)
            query = query.order_by(desc(model_class.created_at)).limit(1)
            result = await self.db.execute(query)
            row = result.scalar_one_or_none()
            if not row:
                return None

            metrics, text_parts = [], []

            if decision_type == "forecast_adjustment":
                cur = getattr(row, "current_forecast_value", None)
                adj = getattr(row, "adjusted_forecast_value", None)
                pct = getattr(row, "adjustment_pct", None)
                direction = getattr(row, "adjustment_direction", "?")
                signal = getattr(row, "signal_source", "?")
                conf = getattr(row, "confidence", None)
                reason_text = getattr(row, "reason", None)
                if cur: metrics.append({"label": "Current Forecast", "value": f"{cur:,.0f}", "unit": "units"})
                if adj: metrics.append({"label": "Adjusted Forecast", "value": f"{adj:,.0f}", "unit": "units"})
                if pct: metrics.append({"label": "Change", "value": f"{pct:+.1f}", "unit": "%", "status": "destructive" if abs(pct) > _FORECAST_CHANGE_ALERT_PCT else "warning"})
                if conf: metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(f"Forecast adjustment {direction} {pct}% for {row.product_id}. Signal source: {signal}. Current={cur}, Adjusted={adj}. Confidence={conf}. Reason: {reason_text}")
            elif decision_type == "rebalancing":
                qty = getattr(row, "recommended_qty", None)
                src = getattr(row, "from_site", None)
                dst = getattr(row, "to_site", None)
                src_dos = getattr(row, "source_dos_before", None)
                dst_dos = getattr(row, "dest_dos_before", None)
                cost = getattr(row, "expected_cost", None)
                if qty: metrics.append({"label": "Transfer Qty", "value": f"{qty:,.0f}", "unit": "units"})
                if src_dos: metrics.append({"label": f"Source DOS ({src})", "value": f"{src_dos:.1f}", "unit": "days"})
                if dst_dos: metrics.append({"label": f"Dest DOS ({dst})", "value": f"{dst_dos:.1f}", "unit": "days"})
                if cost: metrics.append({"label": "Est. Cost", "value": f"{_CURRENCY_SYMBOL}{cost:,.0f}"})
                text_parts.append(f"Transfer {qty} of {row.product_id} from {src} to {dst}. Source DOS={src_dos}, Dest DOS={dst_dos}, cost={_CURRENCY_SYMBOL}{cost}")
            elif decision_type == "atp":
                req = getattr(row, "requested_qty", None)
                promised = getattr(row, "promised_qty", None)
                can = getattr(row, "can_fulfill", None)
                priority = getattr(row, "order_priority", None)
                conf = getattr(row, "confidence", None)
                if req: metrics.append({"label": "Requested", "value": f"{req:,.0f}", "unit": "units"})
                if promised: metrics.append({"label": "Promised", "value": f"{promised:,.0f}", "unit": "units"})
                metrics.append({"label": "Can Fulfill", "value": "Yes" if can else "No", "status": "success" if can else "destructive"})
                if priority: metrics.append({"label": "Priority", "value": str(priority)})
                if conf: metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(f"ATP: requested={req}, promised={promised}, can_fulfill={can}, priority={priority}, confidence={conf}")
            elif decision_type == "po_creation":
                qty = getattr(row, "recommended_qty", None)
                inv_pos = getattr(row, "inventory_position", None)
                dos = getattr(row, "days_of_supply", None)
                fcst_30 = getattr(row, "forecast_30_day", None)
                trigger = getattr(row, "trigger_reason", None)
                cost = getattr(row, "expected_cost", None)
                if qty: metrics.append({"label": "Order Qty", "value": f"{qty:,.0f}", "unit": "units"})
                if inv_pos: metrics.append({"label": "Inventory Position", "value": f"{inv_pos:,.0f}", "unit": "units"})
                if dos: metrics.append({"label": "Days of Supply", "value": f"{dos:.1f}", "unit": "days"})
                if fcst_30: metrics.append({"label": "30-Day Forecast", "value": f"{fcst_30:,.0f}", "unit": "units"})
                if cost: metrics.append({"label": "Est. Cost", "value": f"{_CURRENCY_SYMBOL}{cost:,.0f}"})
                text_parts.append(f"PO: qty={qty}, inv_position={inv_pos}, DOS={dos}, forecast_30d={fcst_30}, trigger={trigger}, cost={_CURRENCY_SYMBOL}{cost}")
            elif decision_type == "order_tracking":
                order_id = getattr(row, "order_id", None)
                exc_type = getattr(row, "exception_type", None)
                severity = getattr(row, "severity", None)
                rec_action = getattr(row, "recommended_action", None)
                description = getattr(row, "description", None)
                impact = getattr(row, "estimated_impact_cost", None)
                conf = getattr(row, "confidence", None)
                if order_id: metrics.append({"label": "Order", "value": order_id})
                if exc_type: metrics.append({"label": "Exception", "value": exc_type})
                if severity:
                    sev_status = {"high": "destructive", "medium": "warning", "low": "info"}.get(severity, "info")
                    metrics.append({"label": "Severity", "value": severity.title(), "status": sev_status})
                if rec_action: metrics.append({"label": "Action", "value": rec_action})
                if impact: metrics.append({"label": "Est. Impact", "value": f"{_CURRENCY_SYMBOL}{impact:,.0f}"})
                if conf: metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(f"Order exception {exc_type} on {order_id} ({severity}). Recommended: {rec_action}. Impact: {_CURRENCY_SYMBOL}{impact}. Description: {description}")
            elif decision_type == "inventory_buffer":
                base = getattr(row, "baseline_ss", None)
                mult = getattr(row, "multiplier", None)
                adj = getattr(row, "adjusted_ss", None)
                reason_text = getattr(row, "reason", None)
                demand_cv = getattr(row, "demand_cv", None)
                cur_dos = getattr(row, "current_dos", None)
                conf = getattr(row, "confidence", None)
                if base: metrics.append({"label": "Baseline SS", "value": f"{base:,.0f}", "unit": "units"})
                if adj: metrics.append({"label": "Adjusted SS", "value": f"{adj:,.0f}", "unit": "units"})
                if mult: metrics.append({"label": "Multiplier", "value": f"{mult:.2f}x"})
                if cur_dos: metrics.append({"label": "Current DOS", "value": f"{cur_dos:.1f}", "unit": "days"})
                if demand_cv: metrics.append({"label": "Demand CV", "value": f"{demand_cv:.2f}"})
                if conf: metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(f"Buffer adjustment for {row.product_id} at {getattr(row, 'location_id', '?')}: baseline={base}, adjusted={adj}, multiplier={mult}. Reason: {reason_text}. DOS={cur_dos}, demand_cv={demand_cv}")

            return {"metrics": metrics, "text": "\n".join(text_parts)} if metrics else None
        except Exception as e:
            logger.warning(f"Decision detail fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # Tenant vocabulary loader
    # ------------------------------------------------------------------

    async def _load_tenant_vocabulary(self, config_id: Optional[int] = None) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Load product IDs and site names for the tenant's DAG."""
        product_lookup: Dict[str, str] = {}
        site_lookup: Dict[str, str] = {}

        try:
            if config_id:
                cfg_ids = [config_id]
            else:
                result = await self.db.execute(
                    select(SupplyChainConfig.id).where(
                        SupplyChainConfig.tenant_id == self.tenant_id,
                        SupplyChainConfig.is_active == True,
                    )
                )
                cfg_ids = [row[0] for row in result.fetchall()]

            if not cfg_ids:
                return product_lookup, site_lookup

            result = await self.db.execute(
                select(Product.id, Product.description, Product.product_group_name).where(Product.config_id.in_(cfg_ids))
            )
            for pid, desc_text, group in result.fetchall():
                product_lookup[pid.lower()] = pid
                for prefix_id in cfg_ids:
                    base = pid.replace(f"CFG{prefix_id}_", "")
                    if base != pid:
                        product_lookup[base.lower()] = pid
                if desc_text:
                    product_lookup[desc_text.lower()] = pid
                    desc_words = []
                    for word in desc_text.split():
                        w = word.strip(",.()-").lower()
                        if len(w) >= 3:
                            product_lookup[w] = pid
                            desc_words.append(w)
                    for i in range(len(desc_words) - 1):
                        product_lookup[f"{desc_words[i]} {desc_words[i+1]}"] = pid
                if group:
                    product_lookup[group.lower()] = pid

            result = await self.db.execute(
                select(Site.name, Site.type, Site.attributes, Site.master_type).where(Site.config_id.in_(cfg_ids))
            )
            for sname, stype, sattrs, smaster in result.fetchall():
                site_lookup[sname.lower()] = sname
                if sattrs and isinstance(sattrs, dict):
                    for key in ("customer_name", "supplier_name", "name"):
                        display = sattrs.get(key)
                        if display:
                            site_lookup[display.lower()] = sname
                            for word in display.split():
                                w = word.strip(",.()-").lower()
                                if len(w) >= 3:
                                    site_lookup[w] = sname
                    for key in ("region", "city", "state", "segment"):
                        val = sattrs.get(key)
                        if val and len(str(val)) >= 2:
                            site_lookup[str(val).lower()] = sname
                if stype and " - " in str(stype):
                    display = str(stype).split(" - ", 1)[-1]
                    site_lookup[display.lower()] = sname
                    for part in display.split(","):
                        p = part.strip().lower()
                        if len(p) >= 3:
                            site_lookup[p] = sname
                if sname.startswith("RDC_"):
                    region = sname.replace("RDC_", "").lower()
                    site_lookup[region] = sname
                    region_names = {"nw": "northwest", "sw": "southwest", "ne": "northeast", "se": "southeast"}
                    if region in region_names:
                        site_lookup[region_names[region]] = sname
                if smaster == "CUSTOMER":
                    site_lookup[f"customer {sname.replace('CUST_', '').lower()}"] = sname

        except Exception as e:
            logger.warning(f"Vocabulary load failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

        return product_lookup, site_lookup

    # ------------------------------------------------------------------
    # Hook: chat system prompt (TMS-specific with SC glossary)
    # ------------------------------------------------------------------

    def _build_chat_system_prompt(self, decision_level: Optional[str] = None) -> str:
        """Build the system prompt with TMS-specific SC glossary and role context."""
        role_info = _ROLE_DESCRIPTIONS.get(decision_level, {})
        role_title = role_info.get("title", "Supply Chain Planner")
        role_scope = role_info.get("scope", "supply chain planning and decision review")
        role_can = role_info.get("can_do", "view and inspect decisions")
        role_cannot = role_info.get("cannot_do", "")

        system_prompt = (
            f"You are an AI supply chain planning assistant for {self.tenant_name}. "
            f"The user is logged in as a **{role_title}**. "
            f"Their scope is: {role_scope}. "
            "You help planners inspect and understand decisions made by Autonomy agents. "
            "IMPORTANT: You have access to live supply chain data (inventory, forecasts, policies, "
            "decision details) injected below. Use this actual data to answer questions with "
            "specific numbers and facts. Do NOT tell the user to navigate to another page — "
            "the data is already here. Reference specific values from the data context. "
            "Keep answers concise and actionable.\n\n"
            "CRITICAL: If the data context below says 'No recent agent decisions' or contains "
            "limited data, DO NOT fabricate numbers or say 'your inventory is 0'. Instead, "
            "summarize what you DO have (market intelligence, BSC data, topology) and "
            "suggest what the user should look at based on the available context. "
            "Never invent metrics, quantities, or inventory levels that aren't in the data.\n\n"
            "CLARIFICATION PROTOCOL: When the user's question is ambiguous or could apply to "
            "multiple entities (sites, products, regions, vendors, customers), you MUST:\n"
            "1. Ask for clarification by offering the VALID OPTIONS from the SUPPLY CHAIN TOPOLOGY "
            "section in the data context below. Never guess or hallucinate options.\n"
            "2. Present options as a concise list.\n"
            "3. If the user gives an invalid value, respond with the valid options.\n"
            "4. If the topology section is missing, say so.\n"
            "5. For product queries, offer product groups first, then specific products.\n"
            "6. Keep clarification questions short — one question at a time."
        )

        system_prompt += (
            "\n\nSUPPLY CHAIN GLOSSARY — interpret user language using these definitions:\n"
            "- 'best performing' / 'top performing' = highest balanced scorecard composite "
            "(OTIF x fill rate x margin, weighted by revenue).\n"
            "- 'worst performing' = lowest BSC composite.\n"
            "- 'region' = customer delivery region (demand side), NOT internal site.\n"
            "- 'site' / 'DC' / 'warehouse' = internal operational location (supply side).\n"
            "- 'product group' / 'category' / 'family' = product hierarchy category.\n"
            "- 'margin' = gross margin % from the balanced scorecard.\n"
            "- 'service level' = OTIF unless specified otherwise.\n"
            "- 'fill rate' = order fill rate.\n"
            "- 'DOS' / 'days of supply' = on-hand inventory / average daily demand.\n"
            "- 'C2C' / 'cash-to-cash' = DIO + DSO - DPO.\n"
            "- 'cost to serve' = total SC cost per unit delivered.\n"
            "- 'bullwhip' = demand amplification ratio.\n"
            "- 'lead time' = supplier delivery LT (procurement) or customer promise time (sales).\n"
            "- 'safety stock' / 'buffer' = inventory held for uncertainty.\n"
            "- 'reorder point' = inventory level triggering replenishment.\n"
            "- 'ATP' = Available-to-Promise. 'CTP' = Capable-to-Promise.\n"
            "- 'MO' = Manufacturing Order. 'PO' = Purchase Order. 'TO' = Transfer Order.\n"
            "- 'override' = human planner changed an agent's recommendation.\n"
            "- 'touchless rate' = % decisions handled autonomously.\n"
            "- 'MPS' = Master Production Schedule. 'MRP' = Material Requirements Planning.\n"
            "- 'BOM' = Bill of Materials. 'WIP' = Work in Process. 'FG' = Finished Goods.\n"
            "- 'MAPE' = Mean Absolute Percentage Error. 'POF' = Perfect Order Fulfillment.\n"
            "- 'EOQ' = Economic Order Quantity. 'MOQ' = Minimum Order Quantity.\n"
            "\nCONVERSATIONAL EXPRESSIONS:\n"
            "- 'we're running low' = inventory approaching or below safety stock\n"
            "- 'we're out' = stockout, ATP = 0\n"
            "- 'we're behind' = production or shipments behind schedule\n"
            "- 'bump the forecast' = increase demand forecast\n"
            "- 'cut the forecast' = decrease demand forecast\n"
            "- 'push out the order' = delay/de-expedite\n"
            "- 'pull in the order' = expedite/bring forward\n"
            "- 'the line is down' = unplanned production downtime\n"
            "- 'we're overstocked' = inventory above max level\n"
            "- 'hot order' = urgent, high-priority order\n"
            "- 'we're on allocation' = supply constrained, rationing\n"
            "- 'firm it up' = lock planned order from MRP changes\n"
            "- 'release it' = authorize for execution\n"
            "- 'best performing' = highest BSC composite score\n"
        )

        role_metrics = _ROLE_METRICS.get(decision_level, _ROLE_METRICS.get("DEMO_ALL", ""))
        if role_metrics:
            system_prompt += f"\n\nMETRIC INTERPRETATION FOR THIS USER'S ROLE:\n{role_metrics}\n"

        if role_cannot and decision_level not in ("DEMO_ALL", "MPS_MANAGER"):
            system_prompt += (
                f"\n\nROLE BOUNDARIES: The user CAN: {role_can}. "
                f"The user CANNOT: {role_cannot}. "
                "If the user asks to perform an action outside their role, "
                "politely explain what they CAN do and suggest who to contact."
            )

        return system_prompt


# ---------------------------------------------------------------------------
# Module-level helpers (backward compat)
# ---------------------------------------------------------------------------

def _get_role_filter_tms(decision_level: Optional[str], level_override: Optional[str] = None):
    """Compute which decision types and levels a role should see (TMS-specific)."""
    if not decision_level:
        return None, None, None

    role_config = ROLE_DEFAULT_LEVELS.get(decision_level)
    if not role_config:
        return None, ROLE_RELEVANCE.get(decision_level), None

    levels = role_config["default_levels"].copy()
    escalation_from = role_config.get("escalation_from")

    if level_override:
        levels = {level_override}
        escalation_from = None

    type_filter = ROLE_TYPE_FILTER.get(decision_level)
    return levels, type_filter, escalation_from


def _extract_ek_background(
    tenant_id: int, decision_type: str, decision_id: int,
    reason_text: str, reason_code: Optional[str],
) -> None:
    """Background: extract experiential knowledge candidate from rich override text."""
    try:
        from app.db.session import sync_session_factory
        from app.services.experiential_knowledge_service import ExperientialKnowledgeService
        db = sync_session_factory()
        try:
            logger.debug(
                "EK extraction candidate: tenant=%d type=%s decision=%d reason=%s",
                tenant_id, decision_type, decision_id, reason_text[:80],
            )
        finally:
            db.close()
    except Exception as e:
        logger.debug("EK extraction failed (non-critical): %s", e)

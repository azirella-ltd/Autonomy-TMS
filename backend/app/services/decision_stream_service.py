"""
Decision Stream Service — LLM-First UI with Decision-Back Planning

Orchestrates the Decision Stream "inbox" by:
  1. Collecting pending decisions from all 11 powell_*_decisions tables
  2. Collecting CDC trigger alerts and condition monitor signals
  3. Prioritizing decisions by urgency, confidence, and economic impact
  4. Synthesizing a natural-language digest via LLM
  5. Supporting conversational chat with decision-context injection
  6. Dispatching accept/override/reject actions to appropriate services

Follows BriefingDataCollector safe-rollback pattern from executive_briefing_service.py
and AssistantService conversation pattern from assistant_service.py.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.sc_entities import Product, Forecast, InvLevel, InvPolicy
from app.models.planning_hierarchy import (
    SiteHierarchyNode, SiteHierarchyLevel,
    ProductHierarchyNode, ProductHierarchyLevel,
)
from app.services.knowledge_base_service import KnowledgeBaseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants (extracted from inline magic numbers)
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = int(os.environ.get("DECISION_STREAM_CACHE_TTL", 1800))
_MAX_CACHE_SIZE = int(os.environ.get("DECISION_STREAM_MAX_CACHE", 200))
_DIGEST_MAX_DECISIONS = 20
_ALERT_LOOKBACK_HOURS = 48
_CDC_TRIGGER_LIMIT = 10
_LLM_SUMMARY_MAX_DECISIONS = 10
_LLM_SUMMARY_MAX_ALERTS = 5
_RAG_RELEVANCE_THRESHOLD = 0.3
_RAG_EXCERPT_MAX_LENGTH = 200
_MAX_HISTORY_SIZE = 20
_LLM_CONTEXT_HISTORY_WINDOW = 10
_ENRICHMENT_HISTORY_WINDOW = 4
_INVENTORY_FETCH_LIMIT = 20
_FORECAST_FETCH_LIMIT = 20
_FORECAST_PERIODS_PER_PRODUCT = 4
_FORECAST_DISPLAY_MAX = 8
_POLICY_FETCH_LIMIT = 20
_FORECAST_CHANGE_ALERT_PCT = 20.0
_DEFAULT_CONFIDENCE = 0.5
_FINAL_RESPONSE_MAX_SOURCES = 5
_DECISION_LOOKBACK_DAYS = 30
_DECISIONS_PER_TABLE = 10
_SUGGESTED_FOLLOWUP_MAX = 3
_DIGEST_SUMMARY_MAX_DECISIONS = 5
_CURRENCY_SYMBOL = os.environ.get("DECISION_STREAM_CURRENCY", "$")

# ---------------------------------------------------------------------------
# Decision quality guardrails
# ---------------------------------------------------------------------------
# Abandon decisions where BOTH urgency AND likelihood are low — not worth
# anyone's time.  The combined score (urgency + likelihood) must exceed this
# threshold to survive.  A sliding scale: the lower the urgency, the higher
# the likelihood must be.  High-urgency decisions are NEVER abandoned because
# that is exactly where human judgment creates real value.
#
# Examples at default 0.5:
#   urgency=0.8, likelihood=0.1 → 0.9 → keep  (human needed — clock ticking)
#   urgency=0.3, likelihood=0.3 → 0.6 → keep
#   urgency=0.1, likelihood=0.2 → 0.3 → abandon
#   urgency=0.2, likelihood=0.1 → 0.3 → abandon
_ABANDON_COMBINED_THRESHOLD = float(
    os.environ.get("DECISION_STREAM_ABANDON_THRESHOLD", 0.5)
)

# In-memory conversation cache (same pattern as AssistantService)
_STREAM_CONVERSATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()

# Digest-level cache: keyed by (tenant_id, config_id, powell_role) → full digest response
_DIGEST_CACHE: Dict[str, Dict[str, Any]] = {}
_DIGEST_CACHE_TTL = int(os.environ.get("DECISION_STREAM_DIGEST_CACHE_TTL", 300))  # 5 min


def invalidate_digest_cache(tenant_id: Optional[int] = None, config_id: Optional[int] = None):
    """Invalidate digest cache entries. Called when new decisions are persisted.

    If tenant_id is provided, only entries for that tenant are cleared.
    If neither is provided, the entire cache is cleared.
    """
    if tenant_id is None and config_id is None:
        _DIGEST_CACHE.clear()
        return
    prefix = f"digest:{tenant_id}:" if tenant_id else "digest:"
    keys_to_remove = [k for k in _DIGEST_CACHE if k.startswith(prefix)]
    if config_id is not None:
        keys_to_remove = [k for k in keys_to_remove if f":{config_id}:" in k]
    for k in keys_to_remove:
        _DIGEST_CACHE.pop(k, None)

# Deep-link mapping for each decision type -> frontend Console route
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

# Decision table registry: (model_class, type_key, summary_builder)
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

# Map type_key → DB table name for direct SQL lookups (e.g., ask-why endpoint)
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
    # Planning TRM decision types
    "demand_adjustment":    "powell_demand_adjustment_decisions",
    "inventory_adjustment": "powell_inventory_adjustment_decisions",
    "supply_adjustment":    "powell_supply_adjustment_decisions",
    "rccp_adjustment":      "powell_rccp_adjustment_decisions",
}

# Role relevance filter: which decision types each powell_role cares about
ROLE_RELEVANCE = {
    "SC_VP": {"atp", "rebalancing", "po_creation", "order_tracking", "forecast_adjustment", "inventory_buffer", "email_signal"},
    "EXECUTIVE": {"atp", "rebalancing", "po_creation", "order_tracking", "forecast_adjustment", "inventory_buffer", "email_signal"},
    "SOP_DIRECTOR": {"po_creation", "rebalancing", "forecast_adjustment", "inventory_buffer", "mo_execution", "to_execution", "email_signal"},
    "MPS_MANAGER": {"atp", "po_creation", "rebalancing", "order_tracking", "mo_execution", "to_execution", "quality", "maintenance", "subcontracting", "email_signal"},
    "ALLOCATION_MANAGER": {"atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    # TRM specialist roles — narrow scope
    "ATP_ANALYST": {"atp"},
    "REBALANCING_ANALYST": {"rebalancing"},
    "PO_ANALYST": {"po_creation"},
    "ORDER_TRACKING_ANALYST": {"order_tracking"},
    "DEMO_ALL": None,  # None = all types
}

# Per-table site column filter builder: type_key -> (model, allowed_site_names) -> filter clause or None
def _site_filter(type_key, model_class, sites):
    """Build a SQLAlchemy filter clause for site scope on the given decision table."""
    if type_key in ("atp", "po_creation", "inventory_buffer"):
        return model_class.location_id.in_(sites)
    elif type_key == "rebalancing":
        return or_(model_class.from_site.in_(sites), model_class.to_site.in_(sites))
    elif type_key == "to_execution":
        return or_(model_class.source_site_id.in_(sites), model_class.dest_site_id.in_(sites))
    elif type_key in ("mo_execution", "quality", "maintenance", "subcontracting", "forecast_adjustment"):
        return model_class.site_id.in_(sites)
    # order_tracking has no site column — skip
    return None

# Tables that have NO product_id column
_NO_PRODUCT_TABLES = {"order_tracking", "maintenance"}


def _evict_stale():
    """Remove expired conversations from cache."""
    now = time.time()
    keys_to_remove = [
        k for k, v in _STREAM_CONVERSATION_CACHE.items()
        if now - v.get("last_access", 0) > _CACHE_TTL_SECONDS
    ]
    for k in keys_to_remove:
        _STREAM_CONVERSATION_CACHE.pop(k, None)
    while len(_STREAM_CONVERSATION_CACHE) > _MAX_CACHE_SIZE:
        _STREAM_CONVERSATION_CACHE.popitem(last=False)


def _safe_float(v) -> Optional[float]:
    """Convert a value to float, returning None for non-numeric strings."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _urgency_label(score: Optional[float]) -> Optional[str]:
    """Convert urgency score (0-1) to 5-stage English label."""
    if score is None:
        return None
    if score >= 0.85:
        return "Critical"
    if score >= 0.65:
        return "High"
    if score >= 0.40:
        return "Medium"
    if score >= 0.20:
        return "Low"
    return "Routine"


def _likelihood_label(score: Optional[float]) -> Optional[str]:
    """Convert likelihood score (0-1) to 5-stage English label."""
    if score is None:
        return None
    if score >= 0.85:
        return "Certain"
    if score >= 0.65:
        return "Likely"
    if score >= 0.40:
        return "Possible"
    if score >= 0.20:
        return "Unlikely"
    return "Never"


def _humanize_ids(text: str, product_names: Dict[str, str]) -> str:
    """Replace raw product IDs (e.g. CFG22_RD005) with human names in text.

    Scans for every product ID key and replaces with the short name.
    Longer IDs are replaced first to avoid partial-match issues.
    """
    if not text or not product_names:
        return text
    # Sort by key length descending to avoid partial replacements
    for pid, name in sorted(product_names.items(), key=lambda x: -len(x[0])):
        if pid in text:
            text = text.replace(pid, name)
    return text


def _fmt_qty(val) -> str:
    """Format a quantity as a rounded integer string, or '?' if missing."""
    if val is None:
        return "?"
    try:
        return f"{int(round(float(val))):,}"
    except (ValueError, TypeError):
        return str(val)


def _build_decision_summary(decision, decision_type: str) -> str:
    """Build a human-readable one-line summary for any decision type.

    Column names must match the actual DB schema in powell_*_decisions tables.
    """
    product = getattr(decision, "product_id", None) or ""
    location = (
        getattr(decision, "location_id", None)
        or getattr(decision, "site_id", None)
        or getattr(decision, "from_site", None)
        or ""
    )

    if decision_type == "atp":
        qty = _fmt_qty(getattr(decision, "requested_qty", None))
        return f"ATP: Fulfill {qty} units of {product} at {location}"
    elif decision_type == "rebalancing":
        qty = _fmt_qty(getattr(decision, "recommended_qty", None))
        src = getattr(decision, "from_site", "?")
        dest = getattr(decision, "to_site", "?")
        return f"Rebalance: Transfer {qty} of {product} from {src} to {dest}"
    elif decision_type == "po_creation":
        qty = _fmt_qty(getattr(decision, "recommended_qty", None))
        return f"PO: Order {qty} units of {product} at {location}"
    elif decision_type == "order_tracking":
        severity = getattr(decision, "severity", "INFO")
        order_id = getattr(decision, "order_id", "?")
        exc_type = getattr(decision, "exception_type", "")
        return f"Order Exception ({severity}): {exc_type} on {order_id}"
    elif decision_type == "mo_execution":
        dt = getattr(decision, "decision_type", "release")
        return f"MO {dt}: {product} at {location}"
    elif decision_type == "to_execution":
        dt = getattr(decision, "decision_type", "release")
        src = getattr(decision, "source_site_id", None) or location
        dest = getattr(decision, "dest_site_id", None) or ""
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
        reason = getattr(decision, "reason", "adjust")
        mult = getattr(decision, "multiplier", None)
        base = getattr(decision, "baseline_ss", None)
        adj = getattr(decision, "adjusted_ss", None)
        if base and adj:
            return f"Buffer {reason}: {product} at {location} ({base:.0f} -> {adj:.0f})"
        return f"Buffer {reason}: {product} at {location}"
    return f"{decision_type}: {product} at {location}"


def _get_suggested_action(decision, decision_type: str) -> str:
    """Extract the suggested action text from a decision.

    Column names must match the actual DB schema in powell_*_decisions tables.
    """
    if decision_type == "atp":
        promised = getattr(decision, "promised_qty", None)
        requested = getattr(decision, "requested_qty", None)
        if getattr(decision, "can_fulfill", False):
            return f"Fulfill {_fmt_qty(promised)} units" if promised is not None else "Fulfill order"
        if promised is not None and requested is not None:
            return f"Cannot fulfill — suggest partial ({_fmt_qty(promised)} of {_fmt_qty(requested)})"
        return "Cannot fulfill — review order"
    elif decision_type == "rebalancing":
        qty = getattr(decision, "recommended_qty", None)
        return f"Transfer {_fmt_qty(qty)} units" if qty is not None else "Transfer units"
    elif decision_type == "po_creation":
        qty = getattr(decision, "recommended_qty", None)
        return f"Order {_fmt_qty(qty)} units" if qty is not None else "Order units"
    elif decision_type == "order_tracking":
        return getattr(decision, "recommended_action", "Review exception")
    elif decision_type == "mo_execution":
        return f"{getattr(decision, 'decision_type', 'Release').title()} manufacturing order"
    elif decision_type == "to_execution":
        return f"{getattr(decision, 'decision_type', 'Release').title()} transfer order"
    elif decision_type == "quality":
        return f"{getattr(decision, 'disposition', 'Review').title()} quality order"
    elif decision_type == "maintenance":
        return f"{getattr(decision, 'decision_type', 'Schedule').title()} maintenance"
    elif decision_type == "subcontracting":
        return f"Route via {getattr(decision, 'routing_decision', 'internal')}"
    elif decision_type == "forecast_adjustment":
        direction = getattr(decision, "adjustment_direction", "")
        pct = getattr(decision, "adjustment_pct", "")
        cur = getattr(decision, "current_forecast_value", None)
        adj = getattr(decision, "adjusted_forecast_value", None)
        if cur and adj:
            return f"Adjust forecast {direction} {pct}% ({cur:.0f} -> {adj:.0f})"
        return f"Adjust forecast {direction} {pct}%"
    elif decision_type == "inventory_buffer":
        base = getattr(decision, "baseline_ss", None)
        adj = getattr(decision, "adjusted_ss", None)
        mult = getattr(decision, "multiplier", None)
        if base and adj:
            return f"Adjust buffer {base:.0f} -> {adj:.0f} ({mult:.2f}x)"
        return f"Adjust buffer ({getattr(decision, 'reason', 'review')})"
    return "Review decision"


def _get_reason(decision, decision_type: str) -> Optional[str]:
    """Extract the short reason code/text from a decision.

    Column names vary per table — some use 'reason', others 'trigger_reason'
    or 'disposition_reason'. Tables that already had a reason column before
    the migration keep their original column name.
    """
    if decision_type in ("po_creation", "to_execution"):
        return getattr(decision, "trigger_reason", None)
    elif decision_type == "quality":
        return getattr(decision, "disposition_reason", None)
    # All others use 'reason' (existing or newly added):
    # rebalancing, subcontracting, forecast_adjustment, inventory_buffer (existing)
    # atp, order_tracking, mo_execution, maintenance (added by migration)
    return getattr(decision, "reason", None)


# ---------------------------------------------------------------------------
# Editable values: decision-type-specific fields users can modify on override
# ---------------------------------------------------------------------------
# Maps decision_type → list of {key, label, type, db_col}
# key = frontend field name, db_col = SQLAlchemy column to read/write
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


def _get_editable_values(row, decision_type: str) -> Optional[Dict[str, Any]]:
    """Extract current decision values that the user can modify during override."""
    fields = EDITABLE_FIELDS_MAP.get(decision_type)
    if not fields:
        return None
    result = {}
    for f in fields:
        val = getattr(row, f["db_col"], None)
        # Serialize date/datetime to ISO string
        if val is not None and hasattr(val, "isoformat"):
            val = val.isoformat()
        result[f["key"]] = val
    return result


def _snapshot_original_values(decision, decision_type: str) -> Dict[str, Any]:
    """Snapshot the TRM's original recommendation before user overwrite."""
    fields = EDITABLE_FIELDS_MAP.get(decision_type, [])
    snapshot = {}
    for f in fields:
        val = getattr(decision, f["db_col"], None)
        if val is not None and hasattr(val, "isoformat"):
            val = val.isoformat()
        snapshot[f["key"]] = val
    return snapshot


def _apply_override_values(decision, decision_type: str, values: Dict[str, Any]):
    """Apply user-modified values to the decision record columns."""
    from datetime import date as _date
    fields = EDITABLE_FIELDS_MAP.get(decision_type, [])
    field_map = {f["key"]: f for f in fields}
    for user_key, user_val in values.items():
        spec = field_map.get(user_key)
        if not spec:
            continue
        db_col = spec["db_col"]
        if not hasattr(decision, db_col):
            continue
        # Type coercion
        if spec["type"] == "number" and user_val is not None:
            try:
                user_val = float(user_val)
            except (TypeError, ValueError):
                continue
        elif spec["type"] == "date" and isinstance(user_val, str):
            try:
                user_val = _date.fromisoformat(user_val)
            except ValueError:
                continue
        setattr(decision, db_col, user_val)


def _mark_executed(decision, executed: bool):
    """Set the execution/commitment flag based on action."""
    if hasattr(decision, "was_committed"):
        decision.was_committed = executed
    if hasattr(decision, "was_executed"):
        decision.was_executed = executed
    if hasattr(decision, "was_applied"):
        decision.was_applied = executed


class DecisionStreamService:
    """LLM-First Decision Stream with Decision-Back Planning."""

    def __init__(self, db: AsyncSession, tenant_id: int, tenant_name: str = "", user=None):
        self.db = db
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name or f"Tenant {tenant_id}"
        self.user = user
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    async def _resolve_user_scope(self) -> Tuple[Optional[set], Optional[set]]:
        """Resolve user's hierarchy scope keys to raw site names and product IDs.

        Uses site_hierarchy_node and product_hierarchy_node to traverse the
        hierarchy and find all leaf-level site names and product IDs that
        fall within the user's scope.

        Returns:
            (allowed_site_names, allowed_product_ids) — None means full access.
        """
        if not self.user:
            return None, None

        has_full_sites = getattr(self.user, "has_full_site_scope", True)
        has_full_products = getattr(self.user, "has_full_product_scope", True)

        if has_full_sites and has_full_products:
            return None, None

        allowed_sites = None
        if not has_full_sites:
            site_scope = getattr(self.user, "site_scope", None) or []
            allowed_sites = set()
            for scope_key in site_scope:
                try:
                    result = await self.db.execute(
                        select(SiteHierarchyNode).where(SiteHierarchyNode.code == scope_key)
                    )
                    scope_node = result.scalar_one_or_none()
                    if not scope_node:
                        continue

                    if scope_node.hierarchy_level == SiteHierarchyLevel.SITE:
                        # Leaf node — get the site name directly via FK
                        if scope_node.site_id:
                            site_result = await self.db.execute(
                                select(Site.name).where(Site.id == scope_node.site_id)
                            )
                            site_name = site_result.scalar_one_or_none()
                            if site_name:
                                allowed_sites.add(site_name)
                    else:
                        # Non-leaf — find ALL descendant SITE nodes via hierarchy_path prefix
                        descendants = await self.db.execute(
                            select(Site.name).join(
                                SiteHierarchyNode, SiteHierarchyNode.site_id == Site.id
                            ).where(
                                SiteHierarchyNode.hierarchy_path.like(f"{scope_node.hierarchy_path}%"),
                                SiteHierarchyNode.hierarchy_level == SiteHierarchyLevel.SITE,
                                SiteHierarchyNode.site_id.isnot(None),
                            )
                        )
                        for row in descendants.fetchall():
                            allowed_sites.add(row[0])
                except Exception as e:
                    logger.warning(f"Failed to resolve site scope key {scope_key}: {e}")
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass

            if not allowed_sites:
                allowed_sites = None  # No resolvable sites — don't filter (graceful degradation)

        allowed_products = None
        if not has_full_products:
            product_scope = getattr(self.user, "product_scope", None) or []
            allowed_products = set()
            for scope_key in product_scope:
                try:
                    result = await self.db.execute(
                        select(ProductHierarchyNode).where(ProductHierarchyNode.code == scope_key)
                    )
                    scope_node = result.scalar_one_or_none()
                    if not scope_node:
                        continue

                    if scope_node.hierarchy_level == ProductHierarchyLevel.PRODUCT:
                        if scope_node.product_id:
                            allowed_products.add(scope_node.product_id)
                    else:
                        # Non-leaf — find ALL descendant PRODUCT nodes
                        descendants = await self.db.execute(
                            select(ProductHierarchyNode.product_id).where(
                                ProductHierarchyNode.hierarchy_path.like(f"{scope_node.hierarchy_path}%"),
                                ProductHierarchyNode.hierarchy_level == ProductHierarchyLevel.PRODUCT,
                                ProductHierarchyNode.product_id.isnot(None),
                            )
                        )
                        for row in descendants.fetchall():
                            if row[0]:
                                allowed_products.add(row[0])
                except Exception as e:
                    logger.warning(f"Failed to resolve product scope key {scope_key}: {e}")
                    try:
                        await self.db.rollback()
                    except Exception:
                        pass

            if not allowed_products:
                allowed_products = None  # Graceful degradation

        return allowed_sites, allowed_products

    async def get_decision_digest(
        self,
        powell_role: Optional[str] = None,
        config_id: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Collect pending decisions, alerts, and return digest.

        Returns dict matching DecisionDigestResponse schema.

        Three-tier lookup:
        1. In-memory cache (fastest, volatile)
        2. DB-persisted digest (survives restarts, computed at decision time)
        3. LLM synthesis (fallback, writes result to DB for future loads)
        """
        # --- Tier 1: Check in-memory cache ---
        cache_key = f"digest:{self.tenant_id}:{config_id}:{powell_role}"
        if not force_refresh:
            cached = _DIGEST_CACHE.get(cache_key)
            if cached:
                age = time.time() - cached["_ts"]
                if age < _DIGEST_CACHE_TTL:
                    logger.debug("Digest cache hit (%s, age=%.0fs)", cache_key, age)
                    return {k: v for k, v in cached.items() if not k.startswith("_")}
                else:
                    _DIGEST_CACHE.pop(cache_key, None)

        # 1. Collect pending decisions from all 11 tables
        decisions, product_names = await self._collect_pending_decisions(config_id, powell_role)

        # 2. Prioritize
        decisions = self._prioritize_decisions(decisions)

        # 3. Collect alerts (CDC triggers + condition monitor)
        alerts = await self._collect_alerts(config_id)

        # --- Tier 2: Check DB-persisted digest ---
        digest_text = None
        if not force_refresh and config_id:
            digest_text = await self._load_persisted_digest(
                config_id, powell_role
            )

        # --- Tier 3: LLM synthesis (fire-and-forget background task) ---
        if not digest_text and decisions:
            if force_refresh:
                # Explicit refresh: user is willing to wait
                digest_text = await self._synthesize_digest(decisions, alerts, powell_role)
                digest_text = _humanize_ids(digest_text, product_names)
                if digest_text and config_id:
                    await self._persist_digest(
                        config_id, powell_role, digest_text, decisions, alerts,
                    )
            else:
                # First load: return decisions immediately, synthesize in background
                digest_text = self._build_quick_digest(decisions)
                asyncio.create_task(
                    self._background_synthesize(
                        config_id, powell_role, decisions, alerts, product_names, cache_key,
                    )
                )

        result = {
            "digest_text": digest_text,
            "decisions": decisions,
            "alerts": alerts,
            "total_pending": len(decisions),
            "config_id": config_id,
        }

        # --- Store in memory cache ---
        if digest_text:
            _DIGEST_CACHE[cache_key] = {**result, "_ts": time.time()}
        if len(_DIGEST_CACHE) > 50:
            oldest_key = min(_DIGEST_CACHE, key=lambda k: _DIGEST_CACHE[k]["_ts"])
            _DIGEST_CACHE.pop(oldest_key, None)

        return result

    def _build_quick_digest(self, decisions: List[Dict[str, Any]]) -> str:
        """Build a fast summary without LLM — counts by type + top actions."""
        from collections import Counter
        type_counts = Counter(d["decision_type"] for d in decisions)
        parts = []
        for dtype, count in type_counts.most_common(5):
            label = dtype.replace("_", " ").title()
            parts.append(f"**{label}**: {count}")
        summary = f"{len(decisions)} decisions made by Autonomy agents:\n\n" + "\n".join(
            f"- {p}" for p in parts
        )
        top_actions = [d.get("suggested_action", "") for d in decisions[:3] if d.get("suggested_action")]
        if top_actions:
            summary += "\n\n**Top actions**: " + "; ".join(top_actions[:3])
        return summary

    async def _background_synthesize(
        self,
        config_id: Optional[int],
        powell_role: Optional[str],
        decisions: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        product_names: Dict[str, str],
        cache_key: str,
    ):
        """Run LLM digest synthesis in the background and update caches."""
        try:
            digest_text = await self._synthesize_digest(decisions, alerts, powell_role)
            digest_text = _humanize_ids(digest_text, product_names)
            if digest_text and config_id:
                try:
                    from app.db.session import async_session_factory
                    async with async_session_factory() as db:
                        svc = DecisionStreamService(db=db, tenant_id=self.tenant_id, tenant_name=self.tenant_name)
                        await svc._persist_digest(config_id, powell_role, digest_text, decisions, alerts)
                except Exception as e:
                    logger.warning("Background digest persist failed: %s", e)
            if digest_text:
                cached = _DIGEST_CACHE.get(cache_key)
                if cached:
                    cached["digest_text"] = digest_text
                    cached["_ts"] = time.time()
                    _DIGEST_CACHE[cache_key] = cached
        except Exception as e:
            logger.warning("Background digest synthesis failed: %s", e)

    async def _load_persisted_digest(
        self, config_id: int, powell_role: Optional[str]
    ) -> Optional[str]:
        """Load digest from decision_stream_digests table."""
        try:
            from app.db.session import sync_session_factory
            from sqlalchemy import text as sa_text
            role_clause = "AND powell_role = :role" if powell_role else "AND powell_role IS NULL"
            params = {"cid": config_id, "tid": self.tenant_id}
            if powell_role:
                params["role"] = powell_role
            sync_db = sync_session_factory()
            try:
                result = sync_db.execute(
                    sa_text(
                        f"SELECT digest_text FROM decision_stream_digests "
                        f"WHERE config_id = :cid AND tenant_id = :tid {role_clause} "
                        f"ORDER BY created_at DESC LIMIT 1"
                    ),
                    params,
                ).first()
                if result:
                    logger.debug("Digest loaded from DB (config=%d)", config_id)
                    return result[0]
            finally:
                sync_db.close()
        except Exception as e:
            logger.debug("Digest DB load failed: %s", e)
        return None

    async def _persist_digest(
        self,
        config_id: int,
        powell_role: Optional[str],
        digest_text: str,
        decisions: list,
        alerts: list,
    ):
        """Persist digest to decision_stream_digests table (upsert).

        Uses a separate sync session to avoid asyncpg parameter syntax issues
        with raw SQL.
        """
        try:
            from app.db.session import sync_session_factory
            import json as _json

            dec_json = _json.dumps(
                [{"id": d.get("id"), "decision_type": d.get("decision_type"),
                  "summary": d.get("summary"), "urgency": d.get("urgency")}
                 for d in decisions[:30]]
            )
            alerts_json = _json.dumps(alerts[:10] if alerts else [])

            sync_db = sync_session_factory()
            try:
                from sqlalchemy import text as sa_text
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
                        "cid": config_id,
                        "tid": self.tenant_id,
                        "role": powell_role,
                        "digest": digest_text,
                        "decs": dec_json,
                        "alerts": alerts_json,
                        "total": len(decisions),
                    },
                )
                sync_db.commit()
                logger.info("Digest persisted to DB (config=%d, role=%s)", config_id, powell_role)
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning("Digest persist failed: %s", e)

    async def act_on_decision(
        self,
        decision_id: int,
        decision_type: str,
        action: str,
        override_reason_code: Optional[str] = None,
        override_reason_text: Optional[str] = None,
        override_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Accept, inspect, modify, or cancel a pending decision (AIIO model).

        - accept: Mark as ACTIONED (execute as-is)
        - inspect: Mark as INSPECTED (reviewed, no action needed)
        - modify: User changed values — snapshot originals, apply overrides, execute modified version
        - cancel: User rejects entirely — mark as not executed, no action taken
        - override/reject: Backward compat aliases for modify/cancel
        """
        # Normalize backward-compat actions
        if action == "override":
            action = "modify"
        if action == "reject":
            action = "cancel"

        # Find the model class for this decision type
        model_class = None
        for cls, type_key in DECISION_TABLES:
            if type_key == decision_type:
                model_class = cls
                break

        if not model_class:
            return {"success": False, "message": f"Unknown decision type: {decision_type}", "decision_id": decision_id, "new_status": "error"}

        status_map = {
            "accept": "ACTIONED",
            "inspect": "INSPECTED",
            "modify": "OVERRIDDEN",
            "cancel": "OVERRIDDEN",
        }
        new_status = status_map.get(action, "ACTIONED")

        try:
            result = await self.db.execute(
                select(model_class).where(model_class.id == decision_id)
            )
            decision = result.scalar_one_or_none()

            if not decision:
                return {"success": False, "message": f"Decision {decision_id} not found", "decision_id": decision_id, "new_status": "error"}

            # Common override metadata (modify or cancel)
            if action in ("modify", "cancel"):
                decision.override_action = action
                decision.override_reason_code = override_reason_code
                decision.override_reason_text = override_reason_text
                decision.override_user_id = self.user.id if self.user else None
                decision.override_at = datetime.utcnow()

                if hasattr(decision, "decision_method"):
                    decision.decision_method = "human_override"

            if action == "modify" and override_values:
                # Snapshot original TRM recommendation before overwriting
                decision.original_values = _snapshot_original_values(decision, decision_type)
                decision.override_values = override_values
                _apply_override_values(decision, decision_type, override_values)
                _mark_executed(decision, True)

            elif action == "cancel":
                decision.override_values = None
                _mark_executed(decision, False)

            elif action == "accept":
                _mark_executed(decision, True)

            elif action == "inspect":
                if hasattr(decision, "decision_method"):
                    decision.decision_method = "human_inspected"

            await self.db.commit()

            # Invalidate digest cache so the stream refreshes
            invalidate_digest_cache(tenant_id=self.tenant_id)

            return {
                "success": True,
                "message": f"Decision {decision_id} {new_status.lower()}",
                "decision_id": decision_id,
                "new_status": new_status,
            }
        except Exception as e:
            logger.error(f"Failed to act on decision {decision_id}: {e}")
            await self.db.rollback()
            return {"success": False, "message": str(e), "decision_id": decision_id, "new_status": "error"}

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        config_id: Optional[int] = None,
        powell_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a conversational message with decision context injection."""
        _evict_stale()

        # Get or create conversation
        if not conversation_id or conversation_id not in _STREAM_CONVERSATION_CACHE:
            conversation_id = str(uuid.uuid4())
            _STREAM_CONVERSATION_CACHE[conversation_id] = {
                "messages": [],
                "last_access": time.time(),
                "config_id": config_id,
            }

        conv = _STREAM_CONVERSATION_CACHE[conversation_id]
        conv["last_access"] = time.time()
        if config_id:
            conv["config_id"] = config_id

        # Add user message
        conv["messages"].append({"role": "user", "content": message})

        # RAG retrieval
        rag_results = await self._retrieve_context(message)

        # Detect referenced decision and fetch rich data
        enrichment = await self._enrich_from_message(message, conv["messages"], config_id)
        data_blocks = enrichment.get("data_blocks", [])
        enrichment_text = enrichment.get("context_text", "")
        logger.info(
            f"Chat enrichment: {len(data_blocks)} blocks, "
            f"{len(enrichment_text)} chars context"
        )

        # Collect brief decision context for the LLM
        decision_context = await self._get_brief_decision_context(config_id, powell_role)
        if enrichment_text:
            decision_context += "\n\n" + enrichment_text

        # Build prompt
        prompt = self._build_chat_prompt(message, conv["messages"], rag_results, decision_context)

        # Call LLM
        response_text = await self._call_llm(prompt)

        # Add response to history
        conv["messages"].append({"role": "assistant", "content": response_text})

        # Trim history
        if len(conv["messages"]) > _MAX_HISTORY_SIZE:
            conv["messages"] = conv["messages"][-_MAX_HISTORY_SIZE:]

        # Extract sources
        sources = []
        for r in rag_results[:_FINAL_RESPONSE_MAX_SOURCES]:
            if r.score > _RAG_RELEVANCE_THRESHOLD:
                sources.append({
                    "title": r.document_title,
                    "relevance": round(r.score, 3),
                    "excerpt": r.content[:_RAG_EXCERPT_MAX_LENGTH] + "..." if len(r.content) > _RAG_EXCERPT_MAX_LENGTH else r.content,
                })

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "sources": sources,
            "suggested_followups": self._suggest_followups(message, response_text, decision_context),
            "embedded_decisions": None,
            "data_blocks": data_blocks,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_pending_decisions(
        self,
        config_id: Optional[int] = None,
        powell_role: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Query all 11 powell_*_decisions tables for recent decisions.

        Applies three layers of filtering:
        1. Tenant scope (via config_id)
        2. Role relevance (which decision types this role sees)
        3. User scope (site + product hierarchy-based filtering)

        Returns:
            (decisions, product_names) — product_names maps product_id → short name.
        """
        # Filter decision types by role relevance
        relevant_types = ROLE_RELEVANCE.get(powell_role) if powell_role else None

        all_decisions = []
        cutoff = datetime.utcnow() - timedelta(days=_DECISION_LOOKBACK_DAYS)

        # Find config_ids for this tenant
        config_filter = None
        if config_id:
            config_filter = [config_id]
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
                return [], {}

        if not config_filter:
            return [], {}

        # Resolve user's site/product scope to actual DB values
        allowed_sites, allowed_products = await self._resolve_user_scope()

        # Build product/site name lookup dicts (single query each)
        product_names: Dict[str, str] = {}
        site_names: Dict[str, str] = {}
        try:
            result = await self.db.execute(
                select(Product.id, Product.description).where(
                    Product.config_id.in_(config_filter)
                )
            )
            for pid, pdesc in result.fetchall():
                if pid and pdesc:
                    # Extract short name: "Orange Juice Premium [REFRIGERATED/BEV/BV001]" → "Orange Juice Premium"
                    short_name = pdesc.split("[")[0].strip() if "[" in pdesc else pdesc
                    product_names[str(pid)] = short_name
                    # Also map the short suffix (e.g., "BV002" from "CFG22_BV002")
                    # so older decisions that stored truncated IDs still resolve
                    spid = str(pid)
                    if "_" in spid:
                        suffix = spid.split("_", 1)[1]
                        if suffix not in product_names:
                            product_names[suffix] = short_name
        except Exception:
            pass
        try:
            result = await self.db.execute(
                select(Site.id, Site.name).where(
                    Site.config_id.in_(config_filter)
                )
            )
            for sid, sname in result.fetchall():
                if sname:
                    site_names[str(sname)] = sname
                    # Also map numeric ID → name for decisions that stored IDs
                    if sid is not None:
                        site_names[str(sid)] = sname
        except Exception as e:
            logger.warning(f"Failed to load site names: {e}")

        # Query all 11 tables sequentially (async session cannot be shared across gather)
        for model_class, type_key in DECISION_TABLES:
            if relevant_types is not None and type_key not in relevant_types:
                continue

            try:
                query = select(model_class).where(
                    and_(
                        model_class.config_id.in_(config_filter),
                        model_class.created_at >= cutoff,
                    )
                )

                # Apply site scope filter
                if allowed_sites is not None:
                    site_clause = _site_filter(type_key, model_class, allowed_sites)
                    if site_clause is not None:
                        query = query.where(site_clause)

                # Apply product scope filter
                if allowed_products is not None and type_key not in _NO_PRODUCT_TABLES:
                    query = query.where(model_class.product_id.in_(allowed_products))

                query = query.order_by(desc(model_class.created_at)).limit(_DECISIONS_PER_TABLE)

                result = await self.db.execute(query)
                rows = result.scalars().all()

                for row in rows:
                    # Extract site_id from the correct column per table schema
                    if type_key == "rebalancing":
                        site_id = getattr(row, "from_site", None)
                    elif type_key == "order_tracking":
                        site_id = None
                    elif type_key in ("mo_execution", "quality", "maintenance",
                                      "subcontracting", "forecast_adjustment"):
                        site_id = getattr(row, "site_id", None)
                    elif type_key == "to_execution":
                        site_id = getattr(row, "source_site_id", None)
                    else:
                        site_id = getattr(row, "location_id", None)

                    pid = getattr(row, "product_id", None)
                    raw_reasoning = getattr(row, "decision_reasoning", None)
                    # ── Economic impact columns (3D routing) ────────────
                    raw_cost = _safe_float(getattr(row, "cost_of_inaction", None))
                    raw_tp = _safe_float(getattr(row, "time_pressure", None))
                    raw_benefit = _safe_float(getattr(row, "expected_benefit", None))

                    # Compute urgency: if economic columns populated, use them;
                    # otherwise fall back to legacy urgency_at_time / urgency enum.
                    if raw_cost > 0 and raw_tp > 0:
                        computed_urgency = min(1.0, raw_cost * raw_tp / 1000.0)  # normalize $/day × pressure to 0-1
                    else:
                        computed_urgency = _safe_float(
                            getattr(row, "urgency_at_time", None)
                            or getattr(row, "urgency", None)
                        )

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "summary": _humanize_ids(_build_decision_summary(row, type_key), product_names),
                        "product_id": pid,
                        "product_name": product_names.get(str(pid)) if pid else None,
                        "site_id": site_id,
                        "site_name": site_names.get(str(site_id)) if site_id else None,
                        "urgency": _urgency_label(computed_urgency),
                        "urgency_score": computed_urgency,
                        "likelihood": _likelihood_label(_safe_float(getattr(row, "confidence", None))),
                        "likelihood_score": _safe_float(getattr(row, "confidence", None)),
                        # Economic impact (3D routing — Kahneman-informed)
                        "cost_of_inaction": raw_cost if raw_cost > 0 else None,
                        "time_pressure": raw_tp if raw_tp > 0 else None,
                        "expected_benefit": raw_benefit if raw_benefit > 0 else None,
                        "economic_impact": raw_benefit if raw_benefit > 0 else None,
                        "reason": _get_reason(row, type_key),
                        "decision_reasoning": _humanize_ids(raw_reasoning, product_names) if raw_reasoning else None,
                        "suggested_action": _humanize_ids(_get_suggested_action(row, type_key), product_names),
                        "deep_link": DEEP_LINK_MAP.get(type_key, "/insights/actions"),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "editable_values": _get_editable_values(row, type_key),
                        "context": {
                            "config_id": row.config_id,
                            "decision_method": getattr(row, "decision_method", None),
                            "triggered_by": getattr(row, "triggered_by", None),
                        },
                    })
            except Exception as e:
                import traceback
                logger.warning(f"Failed to query {type_key} decisions: {e}\n{traceback.format_exc()}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        return all_decisions, product_names

    def _prioritize_decisions(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank and filter decisions for the Decision Stream.

        The stream focuses humans on decisions that need attention NOW:
        - High urgency + low likelihood → TOP (human judgment creates value)
        - High urgency + high likelihood → autonomous, shown for awareness
        - Low urgency + high likelihood → autonomous, shown for awareness
        - Low urgency + low likelihood → abandoned, excluded from stream

        Abandonment uses a sliding scale: urgency + likelihood must exceed
        _ABANDON_COMBINED_THRESHOLD.  The lower the urgency, the higher
        the likelihood must be to survive.  High-urgency decisions are
        never abandoned — that's exactly where humans are needed most.

        Abandoned decisions are excluded from the stream entirely.  They
        are available via a separate audit/training endpoint.
        """
        def _to_float(v, default=0.0):
            if v is None:
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        # ── Load per-tenant autonomy thresholds ───────────────────────────
        # Global defaults from TenantBscConfig, overridable per TRM type
        # via TenantDecisionThreshold rows.
        urgency_thresh = 0.65
        likelihood_thresh = 0.70
        benefit_thresh = 0.0
        per_trm_overrides: dict[str, dict[str, float]] = {}

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
                        "No tenant_bsc_config for tenant %d — using default thresholds "
                        "(urgency=%.2f, likelihood=%.2f, benefit=%.2f). "
                        "Run provisioning to create one.",
                        self.tenant_id, urgency_thresh, likelihood_thresh, benefit_thresh,
                    )

                # Load per-TRM-type threshold overrides
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

        # ── 3-Dimensional Routing (Kahneman-informed, Mar 2026) ─────────
        #
        # Three dimensions per decision:
        #   Urgency    = cost_of_inaction × time_pressure (loss exposure)
        #   Likelihood = agent confidence (probability of positive outcome)
        #   Benefit    = expected $ net gain from recommended action
        #
        # Routing formula:
        #   routing_score = urgency × (1 - likelihood) + benefit_norm × likelihood
        #
        # Grounded in Kahneman & Tversky's Prospect Theory (1979):
        #   "Losses loom approximately twice as large as gains."
        # Loss-prevention decisions (high urgency) are prioritized above
        # gain-capture opportunities (high benefit) even at equal dollar
        # values, matching how human planners naturally triage.
        #
        # Per-TRM-type thresholds allow quality disposition to require
        # human review more often than routine rebalancing.

        auto_count = 0
        for d in decisions:
            trm_type = d.get("decision_type", "")

            # Resolve thresholds: per-TRM override > tenant default
            ov = per_trm_overrides.get(trm_type, {})
            lik_t = ov.get("likelihood") if ov.get("likelihood") is not None else likelihood_thresh
            urg_t = ov.get("urgency") if ov.get("urgency") is not None else urgency_thresh
            ben_t = ov.get("benefit") if ov.get("benefit") is not None else benefit_thresh

            urgency = _to_float(d.get("urgency_score"), 0.0)
            likelihood = _to_float(d.get("likelihood_score"), _DEFAULT_CONFIDENCE)
            benefit = _to_float(d.get("expected_benefit"), 0.0)

            # Surface decision if ANY of these conditions hold:
            #  1. Agent is uncertain (likelihood below threshold)
            #  2. High urgency — loss exposure justifies human attention
            #     even when agent is confident (Kahneman: prevent losses first)
            #  3. Benefit is below threshold — stakes too low for autonomous
            #     execution to matter, but worth human awareness
            needs_attention = False
            if likelihood < lik_t:
                needs_attention = True   # Agent uncertain
            elif urgency >= urg_t and likelihood < (lik_t + 0.15):
                needs_attention = True   # High urgency + only moderately confident

            d["needs_attention"] = needs_attention
            d["auto_actioned"] = not needs_attention
            if not needs_attention:
                auto_count += 1

        if auto_count:
            logger.debug(
                "Decision stream: %d auto-actioned, %d need attention",
                auto_count, len(decisions) - auto_count,
            )

        kept = decisions  # Return ALL decisions — frontend filters

        # ── Sort: Kahneman-aligned ──────────────────────────────────────
        # 1. Urgency DESC (loss prevention before gain capture)
        # 2. Benefit DESC (highest value items next)
        # 3. Likelihood ASC (least confident first — where human judgment
        #    adds the most value)
        def _urgency_bucket(score: float) -> int:
            if score >= 0.85: return 4  # Critical
            if score >= 0.65: return 3  # High
            if score >= 0.40: return 2  # Medium
            if score >= 0.20: return 1  # Low
            return 0                    # Routine

        def sort_key(d):
            urgency = _to_float(d.get("urgency_score"), 0.0)
            benefit = _to_float(d.get("expected_benefit"), 0.0)
            likelihood = _to_float(d.get("likelihood_score"), _DEFAULT_CONFIDENCE)
            return (-_urgency_bucket(urgency), -benefit, likelihood)

        kept.sort(key=sort_key)
        return kept[:_DIGEST_MAX_DECISIONS]

    async def _collect_alerts(self, config_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Collect CDC triggers and condition alerts from the last 48 hours."""
        alerts = []
        cutoff = datetime.utcnow() - timedelta(hours=_ALERT_LOOKBACK_HOURS)

        # CDC trigger log
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

    async def _synthesize_digest(
        self,
        decisions: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        powell_role: Optional[str] = None,
    ) -> str:
        """Use LLM to synthesize a natural-language digest paragraph."""
        if not decisions and not alerts:
            return (
                f"Your supply chain is running smoothly. "
                f"No new decisions from Autonomy agents right now."
            )

        # Build a compact summary for the LLM
        decision_summaries = [d["summary"] for d in decisions[:_LLM_SUMMARY_MAX_DECISIONS]]
        alert_summaries = [a["message"] for a in alerts[:_LLM_SUMMARY_MAX_ALERTS]]

        role_context = ""
        if powell_role:
            role_context = f"You are addressing a {powell_role.replace('_', ' ')} user. "

        prompt = (
            f"You are an AI supply chain planning assistant for {self.tenant_name}. "
            f"{role_context}"
            f"Summarize the key agent decisions as a short markdown bulleted list for the planner. "
            f"Start with a one-line header like '**{len(decisions)} decisions** made by Autonomy agents:' "
            f"then list the 3-5 most important decisions as bullet points (use '- **Category**: details' format). "
            f"Be specific about product names, sites, and quantities. "
            f"Group related decisions where possible (e.g. combine multiple POs into one bullet). "
            f"Do NOT list all {len(decisions)} — just the highlights.\n\n"
            f"Decisions:\n"
            + "\n".join(f"- {s}" for s in decision_summaries)
            + "\n\n"
            + (f"Active alerts ({len(alerts)}):\n" + "\n".join(f"- {s}" for s in alert_summaries) if alerts else "No active alerts.")
        )

        def _template_fallback() -> str:
            lines = [f"**{len(decisions)} decisions** made by Autonomy agents:"]
            for d in decisions[:5]:
                lines.append(f"- **{d.get('decision_type', 'Decision')}**: {d['summary']}")
            if alerts:
                lines.append(f"\n**{len(alerts)} alert{'s' if len(alerts) != 1 else ''}** active.")
            return "\n".join(lines)

        try:
            llm_result = await self._call_llm(prompt)
            # Quality check: if the LLM returned a very short response (< 80 chars)
            # or didn't include any bullet/bold formatting, it's likely a poor response —
            # use the template fallback instead so the user sees a useful summary.
            if len(llm_result.strip()) < 80 or ("**" not in llm_result and "-" not in llm_result):
                logger.warning("LLM digest response too short or unformatted (%d chars), using template fallback", len(llm_result))
                return _template_fallback()
            return llm_result
        except Exception as e:
            logger.error(f"LLM digest synthesis failed: {e}")
            return _template_fallback()

    async def _load_tenant_vocabulary(
        self, config_id: Optional[int] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Load product IDs and site names for the tenant's DAG.

        Returns:
            (product_lookup, site_lookup) — both map lowercase token → canonical ID/name.
        """
        product_lookup: Dict[str, str] = {}  # lowercase → product_id
        site_lookup: Dict[str, str] = {}     # lowercase → site name

        try:
            # Get config IDs for this tenant
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

            # Load products
            result = await self.db.execute(
                select(Product.id).where(Product.config_id.in_(cfg_ids))
            )
            for (pid,) in result.fetchall():
                product_lookup[pid.lower()] = pid

            # Load sites
            result = await self.db.execute(
                select(Site.name).where(Site.config_id.in_(cfg_ids))
            )
            for (sname,) in result.fetchall():
                site_lookup[sname.lower()] = sname

        except Exception as e:
            logger.warning(f"Vocabulary load failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass

        return product_lookup, site_lookup

    async def _enrich_from_message(
        self,
        message: str,
        history: List[Dict[str, str]],
        config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Detect referenced decisions/products and fetch real data for inline display.

        Uses the tenant's DAG vocabulary (product IDs, site names) to match
        mentions in the conversation — no hardcoded patterns.

        Returns:
            dict with 'data_blocks' (structured viz data) and 'context_text' (LLM context).
        """
        data_blocks: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        # Load tenant vocabulary from DAG
        product_lookup, site_lookup = await self._load_tenant_vocabulary(config_id)

        # Collect text to scan: current message + recent history
        texts_to_scan = [message]
        for m in history[-_ENRICHMENT_HISTORY_WINDOW:]:
            texts_to_scan.append(m.get("content", ""))
        combined_text = " ".join(texts_to_scan)
        combined_lower = combined_text.lower()

        # Match product IDs and site names from the tenant vocabulary
        product_ids = set()
        site_ids = set()
        for token_lower, canonical in product_lookup.items():
            if token_lower in combined_lower:
                product_ids.add(canonical)
        for token_lower, canonical in site_lookup.items():
            if token_lower in combined_lower:
                site_ids.add(canonical)

        # Detect decision type from keywords
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
            return {"data_blocks": [], "context_text": ""}

        # Fetch real data for mentioned products/sites
        try:
            # 1. Inventory position
            inv_data = await self._fetch_inventory_data(product_ids, site_ids, config_id)
            if inv_data:
                data_blocks.append({
                    "block_type": "table",
                    "title": "Current Inventory Position",
                    "data": {
                        "columns": ["Product", "Site", "On Hand", "In Transit", "Allocated", "Available", "Safety Stock"],
                        "rows": inv_data["rows"],
                    },
                })
                context_parts.append(
                    "=== LIVE INVENTORY DATA ===\n" + inv_data["text"] + "\n=== END INVENTORY ==="
                )

            # 2. Forecast data
            fcst_data = await self._fetch_forecast_data(product_ids, site_ids, config_id)
            if fcst_data:
                data_blocks.append({
                    "block_type": "table",
                    "title": "Forecast (Next 4 Periods)",
                    "data": {
                        "columns": ["Product", "Period", "P10", "P50 (Base)", "P90", "Method"],
                        "rows": fcst_data["rows"],
                    },
                })
                context_parts.append(
                    "=== LIVE FORECAST DATA ===\n" + fcst_data["text"] + "\n=== END FORECAST ==="
                )

            # 3. Inventory policy
            policy_data = await self._fetch_policy_data(product_ids, site_ids, config_id)
            if policy_data:
                data_blocks.append({
                    "block_type": "metrics_row",
                    "title": "Inventory Policy",
                    "data": {"metrics": policy_data["metrics"]},
                })
                context_parts.append(
                    "=== INVENTORY POLICY ===\n" + policy_data["text"] + "\n=== END POLICY ==="
                )

            # 4. Decision detail — fetch the specific decision record
            decision_detail = await self._fetch_decision_detail(
                product_ids, decision_type_hint, config_id
            )
            if decision_detail:
                data_blocks.append({
                    "block_type": "metrics_row",
                    "title": "Decision Detail",
                    "data": {"metrics": decision_detail["metrics"]},
                })
                context_parts.append(
                    "=== DECISION DETAIL ===\n" + decision_detail["text"] + "\n=== END DETAIL ==="
                )

        except Exception as e:
            logger.warning(f"Data enrichment failed (non-fatal): {e}")

        return {
            "data_blocks": data_blocks,
            "context_text": "\n\n".join(context_parts),
        }

    async def _fetch_inventory_data(
        self, product_ids: set, site_ids: set, config_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
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

            # Deduplicate: keep latest per product-site
            seen = set()
            rows = []
            text_lines = []
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
                rows.append([
                    str(r.product_id), str(r.site_id or ""),
                    f"{on_hand:,.0f}", f"{in_transit:,.0f}",
                    f"{allocated:,.0f}", f"{available:,.0f}", f"{ss:,.0f}",
                ])
                text_lines.append(
                    f"  {r.product_id} @ site {r.site_id}: "
                    f"on_hand={on_hand:.0f}, in_transit={in_transit:.0f}, "
                    f"allocated={allocated:.0f}, available={available:.0f}, "
                    f"safety_stock={ss:.0f}"
                )
            return {"rows": rows, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Inventory data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_forecast_data(
        self, product_ids: set, site_ids: set, config_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
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

            # Deduplicate: keep latest 4 per product
            seen_count: Dict[str, int] = {}
            deduped = []
            for r in rows_raw:
                pid = r.product_id or ""
                seen_count[pid] = seen_count.get(pid, 0) + 1
                if seen_count[pid] <= _FORECAST_PERIODS_PER_PRODUCT:
                    deduped.append(r)

            rows = []
            text_lines = []
            for r in deduped[:_FORECAST_DISPLAY_MAX]:  # Cap for readability
                p10 = r.forecast_p10 or 0
                p50 = r.forecast_p50 or r.forecast_quantity or 0
                p90 = r.forecast_p90 or 0
                method = r.forecast_method or "unknown"
                period = str(r.forecast_date) if r.forecast_date else "?"
                rows.append([
                    str(r.product_id), period,
                    f"{p10:,.0f}", f"{p50:,.0f}", f"{p90:,.0f}", method,
                ])
                text_lines.append(
                    f"  {r.product_id} period {period}: P10={p10:.0f}, P50={p50:.0f}, "
                    f"P90={p90:.0f}, method={method}"
                )
            return {"rows": rows, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Forecast data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_policy_data(
        self, product_ids: set, site_ids: set, config_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Fetch inventory policies for mentioned products (one per product)."""
        try:
            query = select(InvPolicy).where(InvPolicy.product_id.in_(product_ids))
            if config_id:
                query = query.where(InvPolicy.config_id == config_id)
            query = query.limit(_POLICY_FETCH_LIMIT)
            result = await self.db.execute(query)
            rows_raw = result.scalars().all()
            if not rows_raw:
                return None

            # Deduplicate: keep first per product_id
            seen = set()
            metrics = []
            text_lines = []
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
                text_lines.append(
                    f"  {r.product_id}: policy={policy_type}, ss_qty={ss_qty:.0f}, "
                    f"ss_days={ss_days}, service_level={sl:.2f}"
                )
            return {"metrics": metrics, "text": "\n".join(text_lines)}
        except Exception as e:
            logger.warning(f"Policy data fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _fetch_decision_detail(
        self, product_ids: set, decision_type: Optional[str], config_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
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
            query = select(model_class).where(
                model_class.product_id.in_(product_ids)
            )
            if config_id:
                query = query.where(model_class.config_id == config_id)
            query = query.order_by(desc(model_class.created_at)).limit(1)
            result = await self.db.execute(query)
            row = result.scalar_one_or_none()
            if not row:
                return None

            metrics = []
            text_parts = []

            if decision_type == "forecast_adjustment":
                cur = getattr(row, "current_forecast_value", None)
                adj = getattr(row, "adjusted_forecast_value", None)
                pct = getattr(row, "adjustment_pct", None)
                direction = getattr(row, "adjustment_direction", "?")
                signal = getattr(row, "signal_source", "?")
                conf = getattr(row, "confidence", None)
                reason = getattr(row, "reason", None)
                if cur:
                    metrics.append({"label": "Current Forecast", "value": f"{cur:,.0f}", "unit": "units"})
                if adj:
                    metrics.append({"label": "Adjusted Forecast", "value": f"{adj:,.0f}", "unit": "units"})
                if pct:
                    metrics.append({"label": "Change", "value": f"{pct:+.1f}", "unit": "%",
                                    "status": "destructive" if abs(pct) > _FORECAST_CHANGE_ALERT_PCT else "warning"})
                if conf:
                    metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(
                    f"Forecast adjustment {direction} {pct}% for {row.product_id}. "
                    f"Signal source: {signal}. Current={cur}, Adjusted={adj}. "
                    f"Confidence={conf}. Reason: {reason}"
                )
            elif decision_type == "rebalancing":
                qty = getattr(row, "recommended_qty", None)
                src = getattr(row, "from_site", None)
                dst = getattr(row, "to_site", None)
                src_dos = getattr(row, "source_dos_before", None)
                dst_dos = getattr(row, "dest_dos_before", None)
                cost = getattr(row, "expected_cost", None)
                if qty:
                    metrics.append({"label": "Transfer Qty", "value": f"{qty:,.0f}", "unit": "units"})
                if src_dos:
                    metrics.append({"label": f"Source DOS ({src})", "value": f"{src_dos:.1f}", "unit": "days"})
                if dst_dos:
                    metrics.append({"label": f"Dest DOS ({dst})", "value": f"{dst_dos:.1f}", "unit": "days"})
                if cost:
                    metrics.append({"label": "Est. Cost", "value": f"{_CURRENCY_SYMBOL}{cost:,.0f}"})
                text_parts.append(
                    f"Transfer {qty} of {row.product_id} from {src} to {dst}. "
                    f"Source DOS={src_dos}, Dest DOS={dst_dos}, cost={_CURRENCY_SYMBOL}{cost}"
                )
            elif decision_type == "atp":
                req = getattr(row, "requested_qty", None)
                promised = getattr(row, "promised_qty", None)
                can = getattr(row, "can_fulfill", None)
                priority = getattr(row, "order_priority", None)
                conf = getattr(row, "confidence", None)
                if req:
                    metrics.append({"label": "Requested", "value": f"{req:,.0f}", "unit": "units"})
                if promised:
                    metrics.append({"label": "Promised", "value": f"{promised:,.0f}", "unit": "units"})
                metrics.append({"label": "Can Fulfill", "value": "Yes" if can else "No",
                                "status": "success" if can else "destructive"})
                if priority:
                    metrics.append({"label": "Priority", "value": str(priority)})
                if conf:
                    metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(
                    f"ATP: requested={req}, promised={promised}, can_fulfill={can}, "
                    f"priority={priority}, confidence={conf}"
                )
            elif decision_type == "po_creation":
                qty = getattr(row, "recommended_qty", None)
                inv_pos = getattr(row, "inventory_position", None)
                dos = getattr(row, "days_of_supply", None)
                fcst_30 = getattr(row, "forecast_30_day", None)
                trigger = getattr(row, "trigger_reason", None)
                cost = getattr(row, "expected_cost", None)
                if qty:
                    metrics.append({"label": "Order Qty", "value": f"{qty:,.0f}", "unit": "units"})
                if inv_pos:
                    metrics.append({"label": "Inventory Position", "value": f"{inv_pos:,.0f}", "unit": "units"})
                if dos:
                    metrics.append({"label": "Days of Supply", "value": f"{dos:.1f}", "unit": "days"})
                if fcst_30:
                    metrics.append({"label": "30-Day Forecast", "value": f"{fcst_30:,.0f}", "unit": "units"})
                if cost:
                    metrics.append({"label": "Est. Cost", "value": f"{_CURRENCY_SYMBOL}{cost:,.0f}"})
                text_parts.append(
                    f"PO: qty={qty}, inv_position={inv_pos}, DOS={dos}, "
                    f"forecast_30d={fcst_30}, trigger={trigger}, cost={_CURRENCY_SYMBOL}{cost}"
                )
            elif decision_type == "order_tracking":
                order_id = getattr(row, "order_id", None)
                exc_type = getattr(row, "exception_type", None)
                severity = getattr(row, "severity", None)
                rec_action = getattr(row, "recommended_action", None)
                description = getattr(row, "description", None)
                impact = getattr(row, "estimated_impact_cost", None)
                conf = getattr(row, "confidence", None)
                if order_id:
                    metrics.append({"label": "Order", "value": order_id})
                if exc_type:
                    metrics.append({"label": "Exception", "value": exc_type})
                if severity:
                    sev_status = {"high": "destructive", "medium": "warning", "low": "info"}.get(severity, "info")
                    metrics.append({"label": "Severity", "value": severity.title(), "status": sev_status})
                if rec_action:
                    metrics.append({"label": "Action", "value": rec_action})
                if impact:
                    metrics.append({"label": "Est. Impact", "value": f"{_CURRENCY_SYMBOL}{impact:,.0f}"})
                if conf:
                    metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(
                    f"Order exception {exc_type} on {order_id} ({severity}). "
                    f"Recommended: {rec_action}. Impact: {_CURRENCY_SYMBOL}{impact}. "
                    f"Description: {description}"
                )
            elif decision_type == "inventory_buffer":
                base = getattr(row, "baseline_ss", None)
                mult = getattr(row, "multiplier", None)
                adj = getattr(row, "adjusted_ss", None)
                reason = getattr(row, "reason", None)
                demand_cv = getattr(row, "demand_cv", None)
                cur_dos = getattr(row, "current_dos", None)
                conf = getattr(row, "confidence", None)
                if base:
                    metrics.append({"label": "Baseline SS", "value": f"{base:,.0f}", "unit": "units"})
                if adj:
                    metrics.append({"label": "Adjusted SS", "value": f"{adj:,.0f}", "unit": "units"})
                if mult:
                    metrics.append({"label": "Multiplier", "value": f"{mult:.2f}x"})
                if cur_dos:
                    metrics.append({"label": "Current DOS", "value": f"{cur_dos:.1f}", "unit": "days"})
                if demand_cv:
                    metrics.append({"label": "Demand CV", "value": f"{demand_cv:.2f}"})
                if conf:
                    metrics.append({"label": "Confidence", "value": f"{conf*100:.0f}", "unit": "%"})
                text_parts.append(
                    f"Buffer adjustment for {row.product_id} at {getattr(row, 'location_id', '?')}: "
                    f"baseline={base}, adjusted={adj}, multiplier={mult}. "
                    f"Reason: {reason}. DOS={cur_dos}, demand_cv={demand_cv}"
                )

            return {"metrics": metrics, "text": "\n".join(text_parts)} if metrics else None
        except Exception as e:
            logger.warning(f"Decision detail fetch failed: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def _get_brief_decision_context(
        self,
        config_id: Optional[int] = None,
        powell_role: Optional[str] = None,
    ) -> str:
        """Get a brief text summary of pending decisions for chat context injection."""
        try:
            decisions, _pnames = await self._collect_pending_decisions(config_id, powell_role)
            if not decisions:
                return "No recent agent decisions."
            summaries = [d["summary"] for d in decisions[:_DIGEST_SUMMARY_MAX_DECISIONS]]
            return f"Decisions made by Autonomy agents ({len(decisions)} total): " + "; ".join(summaries)
        except Exception:
            return "Unable to load decision context."

    async def _retrieve_context(self, query: str):
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

    def _build_chat_prompt(
        self,
        message: str,
        history: List[Dict[str, str]],
        rag_results: list,
        decision_context: str,
    ) -> str:
        """Build the LLM prompt with decision context, RAG, and conversation history."""
        parts = []

        # System prompt
        parts.append(
            f"You are an AI supply chain planning assistant for {self.tenant_name}. "
            "You help planners inspect and understand decisions made by Autonomy agents. "
            "IMPORTANT: You have access to live supply chain data (inventory, forecasts, policies, "
            "decision details) injected below. Use this actual data to answer questions with "
            "specific numbers and facts. Do NOT tell the user to navigate to another page — "
            "the data is already here. Reference specific values from the data context. "
            "Keep answers concise and actionable."
        )

        # Decision context
        if decision_context:
            parts.append(f"=== CURRENT DECISION CONTEXT ===\n{decision_context}\n=== END CONTEXT ===")

        # RAG context
        if rag_results:
            context_lines = []
            for r in rag_results[:_FINAL_RESPONSE_MAX_SOURCES]:
                context_lines.append(f"[Source: {r.document_title}]\n{r.content}")
            parts.append(
                "=== KNOWLEDGE BASE ===\n"
                + "\n---\n".join(context_lines)
                + "\n=== END KB ==="
            )

        # History
        recent = history[-_LLM_CONTEXT_HISTORY_WINDOW:]
        if len(recent) > 1:
            history_lines = []
            for msg in recent[:-1]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history_lines.append(f"{role}: {msg['content']}")
            parts.append(
                "=== CONVERSATION HISTORY ===\n"
                + "\n".join(history_lines)
                + "\n=== END HISTORY ==="
            )

        parts.append(f"User question: {message}")
        return "\n\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM via the existing suggestion service."""
        try:
            from app.services.llm_suggestion_service import LLMSuggestionService
            llm = LLMSuggestionService(provider="openai-compatible")
            result = await llm.generate_conversation_response(
                prompt=prompt,
                context={"tenant_id": self.tenant_id},
            )
            text = result.get("content", "I couldn't generate a response. Please try again.")
            # Strip chain-of-thought <think>...</think> tags that Qwen/Ollama models emit
            text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
            return text.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return (
                "I'm currently unable to process your question due to a service issue. "
                "Please ensure the LLM service is running and try again."
            )

    def _suggest_followups(
        self, question: str, response: str, decision_context: str
    ) -> List[str]:
        """Generate decision-aware follow-up suggestions."""
        suggestions = []
        q_lower = question.lower()

        if "why" in q_lower or "explain" in q_lower:
            suggestions.append("What would happen if I override this?")
            suggestions.append("Show me the historical data behind this decision")
        elif "accept" in q_lower or "approve" in q_lower:
            suggestions.append("What's the next highest priority decision?")
            suggestions.append("Show me the overall supply chain status")
        elif "override" in q_lower or "change" in q_lower:
            suggestions.append("What's the risk of this override?")
            suggestions.append("How have similar overrides performed in the past?")
        else:
            suggestions.append("Why is this the top priority?")
            suggestions.append("What are the key risks right now?")
            suggestions.append("Show me the supply chain dashboard")

        return suggestions[:_SUGGESTED_FOLLOWUP_MAX]

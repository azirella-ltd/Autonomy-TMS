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
# Configuration constants (extracted from inline magic numbers)
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = int(os.environ.get("DECISION_STREAM_CACHE_TTL", 1800))
_MAX_CACHE_SIZE = int(os.environ.get("DECISION_STREAM_MAX_CACHE", 200))
_DIGEST_MAX_DECISIONS = 20
_REBALANCE_COOLDOWN_HOURS = int(os.environ.get("REBALANCE_COOLDOWN_HOURS", 24))
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
_DECISIONS_PER_TABLE = 50  # Per TRM table; total is uncapped — frontend paginates
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

# Digest-level cache: keyed by (tenant_id, config_id, decision_level) → full digest response
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
    # GNN decision types (from gnn_directive_reviews table)
    "sop_policy":           "gnn_directive_reviews",
    "execution_directive":  "gnn_directive_reviews",
    "allocation_refresh":   "gnn_directive_reviews",
}

# ── Decision Level: Powell layer for each decision type ──────────────────
DECISION_LEVEL = {
    # Governance — Human directives, guardrail/target changes
    "directive": "governance",
    "guardrail_change": "governance",
    "policy_envelope_change": "governance",
    # Strategic — S&OP GraphSAGE (weekly, network-wide policy parameters)
    "sop_policy": "strategic",
    # Operational — Site tGNN (hourly, intra-site cross-TRM coordination)
    "site_coordination": "operational",
    # Tactical — Network tGNN (daily, multi-site allocation directives)
    "execution_directive": "tactical",  # legacy
    "network_directive": "tactical",
    "allocation_refresh": "tactical",
    # Execution — TRM agents (per-decision, per-role at site)
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

# ── Level-Based Role Filtering ───────────────────────────────────────────
# Each role has:
#   default_levels: what they see in the default stream view
#   escalation_from: they ALSO see decisions from this level IF escalated
#   allowed_types: fine-grained type filter within their levels (None = all at level)
#
# Principle: You see decisions at YOUR level + escalations FROM the level below.
# You don't see routine noise two levels down.

ROLE_DEFAULT_LEVELS = {
    # VP/Exec: governance + strategic. Tactical only if escalated to strategic.
    "SC_VP":                {"default_levels": {"governance", "strategic"},
                             "escalation_from": "tactical"},
    "EXECUTIVE":            {"default_levels": {"governance", "strategic"},
                             "escalation_from": "tactical"},
    # S&OP Director: strategic. Tactical only if escalated.
    "SOP_DIRECTOR":         {"default_levels": {"strategic"},
                             "escalation_from": "tactical"},
    # MPS Manager: tactical. Execution only if escalated.
    "MPS_MANAGER":          {"default_levels": {"tactical"},
                             "escalation_from": "execution"},
    # Allocation Manager: tactical (allocations + rebalancing)
    "ALLOCATION_MANAGER":   {"default_levels": {"tactical"},
                             "escalation_from": "execution"},
    # Order Promise: execution (ATP only)
    "ORDER_PROMISE_MANAGER": {"default_levels": {"execution"},
                              "escalation_from": None},
    # TRM specialists: execution only
    "ATP_ANALYST":           {"default_levels": {"execution"}, "escalation_from": None},
    "REBALANCING_ANALYST":   {"default_levels": {"execution"}, "escalation_from": None},
    "PO_ANALYST":            {"default_levels": {"execution"}, "escalation_from": None},
    "ORDER_TRACKING_ANALYST": {"default_levels": {"execution"}, "escalation_from": None},
    # Tenant admin / demo: all levels
    "DEMO_ALL":              {"default_levels": {"governance", "strategic", "tactical", "execution"},
                              "escalation_from": None},
}

# Fine-grained type filter per role (within their allowed levels)
# None = see all types at their level. Set = only those types.
ROLE_TYPE_FILTER = {
    "ALLOCATION_MANAGER": {"execution_directive", "allocation_refresh", "atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    "ATP_ANALYST": {"atp"},
    "REBALANCING_ANALYST": {"rebalancing"},
    "PO_ANALYST": {"po_creation"},
    "ORDER_TRACKING_ANALYST": {"order_tracking"},
}

# Legacy ROLE_RELEVANCE kept for backward compatibility — used as fallback
# if ROLE_DEFAULT_LEVELS doesn't have the role.
ROLE_RELEVANCE = {
    "SC_VP": None,  # None = all types (filtered by level instead)
    "EXECUTIVE": None,
    "SOP_DIRECTOR": None,
    "MPS_MANAGER": None,
    "ALLOCATION_MANAGER": {"execution_directive", "allocation_refresh",
                           "atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    "ATP_ANALYST": {"atp"},
    "REBALANCING_ANALYST": {"rebalancing"},
    "PO_ANALYST": {"po_creation"},
    "ORDER_TRACKING_ANALYST": {"order_tracking"},
    "DEMO_ALL": None,
}


def _get_role_filter(decision_level: Optional[str], level_override: Optional[str] = None):
    """Compute which decision types and levels a role should see.

    Returns (allowed_levels, allowed_types, escalation_from_level).
    - allowed_levels: set of level strings this role sees by default
    - allowed_types: set of type_keys (or None for all at level)
    - escalation_from_level: decisions from this level are ALSO shown
      if they have source_signals (i.e., they were escalated)
    """
    if not decision_level:
        return None, None, None  # No filtering

    role_config = ROLE_DEFAULT_LEVELS.get(decision_level)
    if not role_config:
        # Fallback to legacy ROLE_RELEVANCE
        return None, ROLE_RELEVANCE.get(decision_level), None

    levels = role_config["default_levels"].copy()
    escalation_from = role_config.get("escalation_from")

    # Level override from API query parameter (e.g., ?level=execution)
    if level_override:
        levels = {level_override}
        escalation_from = None  # explicit level = no escalation passthrough

    type_filter = ROLE_TYPE_FILTER.get(decision_level)
    return levels, type_filter, escalation_from

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


def _humanize_ids(text: str, product_names: Dict[str, str], site_names: Dict[str, str] = None) -> str:
    """Replace raw product IDs and site IDs with human names in text.

    Scans for every product/site ID key and replaces with the short name.
    Longer IDs are replaced first to avoid partial-match issues.
    """
    if not text:
        return text
    # Replace product IDs
    if product_names:
        for pid, name in sorted(product_names.items(), key=lambda x: -len(x[0])):
            if pid in text:
                text = text.replace(pid, name)
    # Replace site IDs (e.g. "1710" → "Plant 1 US")
    if site_names:
        for sid, name in sorted(site_names.items(), key=lambda x: -len(x[0])):
            if sid in text:
                text = text.replace(sid, name)
    return text


def _consolidate_decisions(
    decisions: List[Dict],
    product_names: Dict[str, str],
    site_names: Dict[str, str],
) -> List[Dict]:
    """Consolidate multiple decisions for the same (product, site, type) into one card.

    The decision_seed generates one row per period per TRM type, so a product
    with 20 weekly forecast adjustments shows up as 20 separate cards. This
    groups them into a single card with the net effect (range of adjustments,
    average magnitude, period span).

    Only consolidates when there are 3+ decisions for the same key. Leaves
    unique and paired decisions untouched.
    """
    from collections import defaultdict

    # Group by (product_id, site_id, decision_type)
    groups: Dict[tuple, List[Dict]] = defaultdict(list)
    ungrouped: List[Dict] = []

    for d in decisions:
        pid = d.get("product_id")
        sid = d.get("site_id")
        dtype = d.get("decision_type")
        if pid and sid and dtype:
            groups[(pid, sid, dtype)].append(d)
        else:
            ungrouped.append(d)

    result = list(ungrouped)

    for (pid, sid, dtype), group in groups.items():
        if len(group) < 3:
            # Not enough to consolidate — keep as separate cards
            result.extend(group)
            continue

        # Consolidate into a single card
        # Use the highest-urgency decision as the base
        group.sort(key=lambda d: d.get("urgency_score") or 0, reverse=True)
        base = dict(group[0])  # copy

        # Compute consolidated metrics
        p_name = base.get("product_name") or product_names.get(str(pid), str(pid))
        s_name = base.get("site_name") or site_names.get(str(sid), str(sid))
        n = len(group)

        if dtype == "forecast_adjustment":
            # Extract adjustment percentages
            pcts = []
            for d in group:
                ev = d.get("editable_values") or {}
                pct = ev.get("adjustment_pct")
                if pct is not None:
                    pcts.append(float(pct))
            if pcts:
                avg_pct = sum(pcts) / len(pcts)
                min_pct = min(pcts)
                max_pct = max(pcts)
                direction = "up" if avg_pct > 0 else "down"
                base["summary"] = (
                    f"Adjust forecast {direction} {abs(avg_pct):.0f}% avg "
                    f"(range {abs(min_pct):.0f}–{abs(max_pct):.0f}%) for "
                    f"{p_name} @ {s_name} across {n} periods"
                )
            else:
                base["summary"] = (
                    f"{n} forecast adjustments for {p_name} @ {s_name}"
                )

        elif dtype == "po_creation":
            qtys = [float((d.get("editable_values") or {}).get("order_quantity", 0) or 0) for d in group]
            total_qty = sum(qtys)
            base["summary"] = (
                f"Create {n} purchase orders totaling {total_qty:,.0f} units "
                f"for {p_name} @ {s_name}"
            )

        elif dtype in ("atp", "atp_allocation"):
            base["summary"] = (
                f"{n} ATP allocation decisions for {p_name} @ {s_name}"
            )

        elif dtype == "inventory_buffer":
            base["summary"] = (
                f"{n} buffer adjustments for {p_name} @ {s_name}"
            )

        else:
            base["summary"] = (
                f"{n} {dtype.replace('_', ' ')} decisions for {p_name} @ {s_name}"
            )

        # Keep the consolidated count and child IDs for drill-down
        base["consolidated_count"] = n
        base["consolidated_ids"] = [d["id"] for d in group]
        # Use the most recent created_at
        dates = [d.get("created_at") for d in group if d.get("created_at")]
        if dates:
            base["created_at"] = max(dates)

        result.append(base)

    # Re-sort by urgency (highest first)
    result.sort(key=lambda d: d.get("urgency_score") or 0, reverse=True)
    return result


def _fmt_qty(val) -> str:
    """Format a quantity as a rounded integer string, or '?' if missing."""
    if val is None:
        return "?"
    try:
        return f"{int(round(float(val))):,}"
    except (ValueError, TypeError):
        return str(val)


def _build_decision_summary(decision, decision_type: str, name_cache: dict = None) -> str:
    """Build a human-readable one-line summary for any decision type.

    Column names must match the actual DB schema in powell_*_decisions tables.
    Uses name_cache to resolve product_id → description and site code → site name.
    """
    raw_product = getattr(decision, "product_id", None) or ""
    raw_location = (
        getattr(decision, "location_id", None)
        or getattr(decision, "site_id", None)
        or getattr(decision, "from_site", None)
        or ""
    )

    # Resolve display names from cache
    cache = name_cache or {}
    product = cache.get("products", {}).get(raw_product, raw_product)
    location = cache.get("sites", {}).get(str(raw_location), str(raw_location))

    # Strip config prefix from product ID for cleaner display
    if product == raw_product and "_" in product:
        # CFG94_MZ-FG-C900 → MZ-FG-C900
        parts = product.split("_", 1)
        if parts[0].startswith("CFG"):
            product = parts[1]

    sites = cache.get("sites", {})

    if decision_type == "atp":
        qty = _fmt_qty(getattr(decision, "requested_qty", None))
        return f"ATP: Fulfill {qty} units of {product} at {location}"
    elif decision_type == "rebalancing":
        qty = _fmt_qty(getattr(decision, "recommended_qty", None))
        raw_src = str(getattr(decision, "from_site", "?"))
        raw_dest = str(getattr(decision, "to_site", "?"))
        src = sites.get(raw_src, raw_src)
        dest = sites.get(raw_dest, raw_dest)
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
        # Include product, site, and horizon in the summary so the
        # Decision Stream headline tells you WHAT, WHERE, and WHEN
        # without clicking into the detail.
        pid = getattr(decision, "product_id", "")
        sid = getattr(decision, "site_id", "")
        horizon = getattr(decision, "planning_horizon", None) or getattr(decision, "adjustment_horizon", None)
        horizon_str = f" over {horizon}" if horizon else ""
        if cur and adj:
            return f"Adjust forecast {direction} {pct}% for {pid} @ {sid}{horizon_str} ({cur:.0f} → {adj:.0f} units/wk)"
        return f"Adjust forecast {direction} {pct}% for {pid} @ {sid}{horizon_str}"
    elif decision_type == "inventory_buffer":
        base = getattr(decision, "baseline_ss", None)
        adj = getattr(decision, "adjusted_ss", None)
        mult = getattr(decision, "multiplier", None)
        if base and adj:
            return f"Adjust buffer {base:.0f} -> {adj:.0f} ({mult:.2f}x)"
        return f"Adjust buffer ({getattr(decision, 'reason', 'review')})"
    return "Review decision"


def _safe_effective_from(decision, decision_type: str) -> Optional[str]:
    try:
        return _get_effective_dates(decision, decision_type)[0]
    except Exception as e:
        logger.debug("effective_from failed for %s: %s", decision_type, e)
        try:
            ca = getattr(decision, "created_at", None)
            if ca and hasattr(ca, "date"):
                return ca.date().isoformat()
            if ca and hasattr(ca, "isoformat"):
                return ca.isoformat()[:10]
        except Exception:
            pass
        return None


def _safe_period_days(decision, decision_type: str) -> Optional[int]:
    try:
        return _get_effective_dates(decision, decision_type)[1]
    except Exception:
        return 7


def _get_effective_dates(decision, decision_type: str) -> Tuple[Optional[str], int]:
    """Extract the effective start date and period duration (days) for a decision.

    Returns (effective_from_iso, period_days).
    - effective_from: when the action takes effect (ISO date string)
    - period_days: how long the action spans (default 7 = one planning week)
    """
    from datetime import date as _date

    # Default: action starts today, spans 1 planning week
    created = getattr(decision, "created_at", None)
    # TODO(virtual-clock): Threading tenant_id into _get_effective_dates would require
    # refactoring all callers (~15 sites). Fallback to real today when created_at missing.
    default_from = created.date() if created and hasattr(created, "date") else _date.today()
    default_period = 7

    if decision_type == "po_creation":
        receipt = getattr(decision, "expected_receipt_date", None)
        if receipt:
            lead_days = (receipt - default_from).days if hasattr(receipt, "__sub__") else 0
            return default_from.isoformat(), max(lead_days, 7)
        return default_from.isoformat(), 14  # PO typically 2-week horizon

    elif decision_type == "rebalancing":
        # Transfer decisions: effect is immediate, transit 1-3 days
        return default_from.isoformat(), 7

    elif decision_type == "forecast_adjustment":
        periods = getattr(decision, "time_horizon_periods", None)
        if periods and isinstance(periods, int):
            return default_from.isoformat(), periods * 7  # periods are weekly
        return default_from.isoformat(), 28  # default 4 weeks for forecasts

    elif decision_type == "mo_execution":
        return default_from.isoformat(), 14  # production cycle ~2 weeks

    elif decision_type == "to_execution":
        transit = getattr(decision, "estimated_transit_days", None)
        if transit:
            try:
                return default_from.isoformat(), max(int(float(transit)) + 7, 7)
            except (TypeError, ValueError):
                pass
        return default_from.isoformat(), 7

    elif decision_type == "maintenance":
        sched = getattr(decision, "scheduled_date", None)
        if sched:
            return sched.isoformat() if hasattr(sched, "isoformat") else str(sched), 7
        return default_from.isoformat(), 7

    elif decision_type == "inventory_buffer":
        return default_from.isoformat(), 28  # buffer adjustments span ~4 weeks

    return default_from.isoformat(), default_period


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


async def _create_supply_plan_adjustment(
    db: "AsyncSession",
    decision: Any,
    decision_type: str,
    override_values: Optional[Dict[str, Any]],
) -> None:
    """Persist a supply plan record reflecting the actioned decision.

    When a user accepts or modifies a TRM decision, the supply plan must be
    updated from the action date forward so downstream planning (MRP, capacity)
    reflects the change.
    """
    from app.models.sc_entities import SupplyPlan

    config_id = getattr(decision, "config_id", None)
    if not config_id:
        return

    action_date = datetime.utcnow().date()

    # Build plan row from decision type
    plan_type_map = {
        "rebalancing": "to_request",
        "po_creation": "po_request",
        "mo_execution": "mo_request",
        "to_execution": "to_request",
        "inventory_buffer": "ss_adjustment",
        "forecast_adjustment": "forecast_adjustment",
    }
    plan_type = plan_type_map.get(decision_type, "adjustment")

    # Extract quantity and sites from override_values or decision attributes
    ov = override_values or {}
    qty = (
        ov.get("qty")
        or ov.get("allocated_qty")
        or ov.get("buffer_qty")
        or getattr(decision, "recommended_qty", None)
        or getattr(decision, "qty", None)
        or 0
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
    db.add(plan)
    await db.commit()
    logger.info(
        "Supply plan adjustment created: type=%s decision=%s qty=%.1f",
        plan_type, decision.id, qty,
    )


def _extract_ek_from_override(
    tenant_id: int, config_id: int, decision_type: str,
    decision_id: int, reason_text: str, reason_code: str,
) -> None:
    """Background: extract experiential knowledge candidate from rich override text.

    Fire-and-forget after overrides with detailed reason text (>30 chars).
    Creates CANDIDATE entities if the reason describes a recurring pattern.
    """
    try:
        from app.db.session import sync_session_factory
        from app.services.experiential_knowledge_service import ExperientialKnowledgeService
        db = sync_session_factory()
        try:
            svc = ExperientialKnowledgeService(db=db, tenant_id=tenant_id, config_id=config_id)
            # For now, just log — full LLM classification is Phase 2
            logger.debug(
                "EK extraction candidate: tenant=%d type=%s decision=%d reason=%s",
                tenant_id, decision_type, decision_id, reason_text[:80],
            )
        finally:
            db.close()
    except Exception as e:
        logger.debug("EK extraction failed (non-critical): %s", e)


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

        Delegates to shared user_scope_service.resolve_user_scope().
        Returns (allowed_site_names, allowed_product_ids) — None means full access.
        """
        from app.services.user_scope_service import resolve_user_scope
        return await resolve_user_scope(self.db, self.user)

    async def get_decision_digest(
        self,
        decision_level: Optional[str] = None,
        config_id: Optional[int] = None,
        force_refresh: bool = False,
        level_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect pending decisions, alerts, and return digest.

        Returns dict matching DecisionDigestResponse schema.

        Level-based filtering:
        - Each role sees their default levels + escalations from below
        - level_override: if provided, explicitly filter to one level (drill-down)

        Three-tier lookup:
        1. In-memory cache (fastest, volatile)
        2. DB-persisted digest (survives restarts, computed at decision time)
        3. LLM synthesis (fallback, writes result to DB for future loads)
        """
        # --- Tier 1: Check in-memory cache ---
        cache_key = f"digest:{self.tenant_id}:{config_id}:{decision_level}:{level_override}"
        if not force_refresh:
            cached = _DIGEST_CACHE.get(cache_key)
            if cached:
                age = time.time() - cached["_ts"]
                if age < _DIGEST_CACHE_TTL:
                    logger.debug("Digest cache hit (%s, age=%.0fs)", cache_key, age)
                    return {k: v for k, v in cached.items() if not k.startswith("_")}
                else:
                    _DIGEST_CACHE.pop(cache_key, None)

        # 1. Collect pending decisions from all tables (TRM + GNN + governance)
        decisions, product_names, site_names = await self._collect_pending_decisions(
            config_id, decision_level, level_override=level_override,
        )

        # 1b. Forward-rolling coordination: remove decisions made redundant
        #     by earlier (higher-priority) decisions targeting the same shortfall.
        #     Evaluates in chronological order — today's decisions project forward
        #     and may eliminate tomorrow's.
        try:
            from app.services.decision_impact_ledger import DecisionImpactLedger
            ledger = DecisionImpactLedger(self.db, config_id or (config_filter[0] if config_filter else 0))
            decisions = await ledger.evaluate_decisions(decisions)
        except Exception as e:
            logger.warning("Forward-rolling decision evaluation failed: %s", e)

        # 2. Prioritize
        decisions = self._prioritize_decisions(decisions)

        # 2b. Mark surfaced decisions as INFORMED (AIIO: agent acted, now human is notified)
        # Only mark ACTIONED → INFORMED; don't regress INSPECTED/OVERRIDDEN
        await self._mark_decisions_informed(decisions)

        # 3. Collect alerts (CDC triggers + condition monitor)
        alerts = await self._collect_alerts(config_id)

        # --- Tier 2: Check DB-persisted digest ---
        digest_text = None
        if not force_refresh and config_id:
            digest_text = await self._load_persisted_digest(
                config_id, decision_level
            )

        # --- Tier 3: LLM synthesis (fire-and-forget background task) ---
        if not digest_text and decisions:
            if force_refresh:
                # Explicit refresh: user is willing to wait
                digest_text = await self._synthesize_digest(decisions, alerts, decision_level)
                digest_text = _humanize_ids(digest_text, product_names, site_names)
                if digest_text and config_id:
                    await self._persist_digest(
                        config_id, decision_level, digest_text, decisions, alerts,
                    )
            else:
                # First load: return decisions immediately, synthesize in background
                digest_text = self._build_quick_digest(decisions)
                asyncio.create_task(
                    self._background_synthesize(
                        config_id, decision_level, decisions, alerts, product_names, site_names, cache_key,
                    )
                )

        # ── Load tenant display preference ────────────────────────────────
        display_identifiers = "name"
        try:
            from app.db.session import sync_session_factory
            from app.models.bsc_config import TenantBscConfig as _Bsc
            _sync = sync_session_factory()
            try:
                _bsc = _sync.query(_Bsc).filter(_Bsc.tenant_id == self.tenant_id).first()
                if _bsc:
                    display_identifiers = getattr(_bsc, "display_identifiers", "name") or "name"
            finally:
                _sync.close()
        except Exception:
            pass  # default to "name"

        # Compute level counts for frontend tabs
        level_counts = {"governance": 0, "strategic": 0, "tactical": 0, "execution": 0}
        for d in decisions:
            lvl = d.get("decision_level", "execution")
            if lvl in level_counts:
                level_counts[lvl] += 1

        result = {
            "digest_text": digest_text or "No decisions to report.",
            "decisions": decisions,
            "alerts": alerts,
            "total_pending": len(decisions),
            "config_id": config_id,
            "display_identifiers": display_identifiers,
            "level_counts": level_counts,
            "active_level": level_override,
        }

        # --- Store in memory cache ---
        if digest_text:
            _DIGEST_CACHE[cache_key] = {**result, "_ts": time.time()}
        if len(_DIGEST_CACHE) > 50:
            oldest_key = min(_DIGEST_CACHE, key=lambda k: _DIGEST_CACHE[k]["_ts"])
            _DIGEST_CACHE.pop(oldest_key, None)

        return result

    # Business-friendly labels for digest text — no tech names
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

    def _build_quick_digest(self, decisions: List[Dict[str, Any]]) -> str:
        """Build a fast summary without LLM — counts by type + top actions."""
        from collections import Counter
        type_counts = Counter(d["decision_type"] for d in decisions)
        parts = []
        for dtype, count in type_counts.most_common(5):
            label = self._DIGEST_TYPE_LABELS.get(dtype, dtype.replace("_", " ").title())
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
        decision_level: Optional[str],
        decisions: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        product_names: Dict[str, str],
        site_names: Dict[str, str],
        cache_key: str,
    ):
        """Run LLM digest synthesis in the background and update caches."""
        try:
            digest_text = await self._synthesize_digest(decisions, alerts, decision_level)
            digest_text = _humanize_ids(digest_text, product_names, site_names)
            if digest_text and config_id:
                try:
                    from app.db.session import async_session_factory
                    async with async_session_factory() as db:
                        svc = DecisionStreamService(db=db, tenant_id=self.tenant_id, tenant_name=self.tenant_name)
                        await svc._persist_digest(config_id, decision_level, digest_text, decisions, alerts)
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
        self, config_id: int, decision_level: Optional[str]
    ) -> Optional[str]:
        """Load digest from decision_stream_digests table."""
        try:
            from app.db.session import sync_session_factory
            from sqlalchemy import text as sa_text
            role_clause = "AND powell_role = :role" if decision_level else "AND powell_role IS NULL"
            params = {"cid": config_id, "tid": self.tenant_id}
            if decision_level:
                params["role"] = decision_level
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
        decision_level: Optional[str],
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
                        "role": decision_level,
                        "digest": digest_text,
                        "decs": dec_json,
                        "alerts": alerts_json,
                        "total": len(decisions),
                    },
                )
                sync_db.commit()
                logger.info("Digest persisted to DB (config=%d, role=%s)", config_id, decision_level)
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

            # ── Create supply plan adjustment from decision action ────────
            if action in ("accept", "modify") and decision_type in (
                "rebalancing", "po_creation", "mo_execution", "to_execution",
                "inventory_buffer", "forecast_adjustment",
            ):
                try:
                    await _create_supply_plan_adjustment(
                        self.db, decision, decision_type, override_values,
                    )
                except Exception as sp_err:
                    logger.warning(f"Supply plan adjustment failed for {decision_id}: {sp_err}")

            # Note: redundant decisions are removed at digest-build time by the
            # forward-rolling DecisionImpactLedger.evaluate_decisions(). The cache
            # invalidation above ensures the next digest call re-evaluates.

            # Fire-and-forget: extract experiential knowledge from rich override text
            if action in ("modify", "cancel") and override_reason_text and len(override_reason_text) > 30:
                try:
                    import asyncio
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        _extract_ek_from_override,
                        self.tenant_id, self.config_id, decision_type,
                        decision_id, override_reason_text, override_reason_code,
                    )
                except Exception:
                    pass  # Non-critical, never block the response

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
        decision_level: Optional[str] = None,
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
        clarifications = enrichment.get("clarifications", [])
        logger.info(
            f"Chat enrichment: {len(data_blocks)} blocks, "
            f"{len(enrichment_text)} chars context"
        )

        # Collect brief decision context for the LLM
        decision_context = await self._get_brief_decision_context(config_id, decision_level)
        if enrichment_text:
            decision_context += "\n\n" + enrichment_text

        # Load DAG topology so LLM can offer valid options for clarification
        dag_topology = await self._get_dag_topology(config_id)
        if dag_topology:
            decision_context += "\n\n" + dag_topology

        # Load BSC data for performance comparisons
        bsc_data = await self._get_bsc_context(config_id)
        if bsc_data:
            decision_context += "\n\n" + bsc_data

        # Load external market intelligence (outside-in signals)
        ext_signals = await self._get_external_signals_context()
        if ext_signals:
            decision_context += "\n\n" + ext_signals

        # Load experiential knowledge (planner behavioral patterns)
        ek_context = await self._get_experiential_knowledge_context()
        if ek_context:
            decision_context += "\n\n" + ek_context

        # Build prompt with role-scoped instructions
        prompt = self._build_chat_prompt(message, conv["messages"], rag_results, decision_context, decision_level)

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
            "clarifications": clarifications if clarifications else None,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_pending_decisions(
        self,
        config_id: Optional[int] = None,
        decision_level: Optional[str] = None,
        level_override: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str]]:
        """Query powell_*_decisions tables + gnn_directive_reviews + governance sources.

        Applies level-based filtering:
        1. Tenant scope (via config_id)
        2. Level filtering: each role sees their default levels + escalations from below
        3. Type filtering: fine-grained filter within allowed levels
        4. User scope (site + product hierarchy-based filtering)
        5. level_override: if provided, restricts to a single level (drill-down)

        Returns:
            (decisions, product_names, site_names) — maps IDs → display names.
        """
        # Level-based role filtering (replaces flat ROLE_RELEVANCE)
        allowed_levels, type_filter, escalation_from = _get_role_filter(decision_level, level_override)

        # For backward compatibility, compute relevant_types from levels + type_filter
        if allowed_levels is not None:
            relevant_types = set()
            for type_key, level in DECISION_LEVEL.items():
                if level in allowed_levels:
                    if type_filter is None or type_key in type_filter:
                        relevant_types.add(type_key)
            # If escalation_from is set, we'll also include escalated decisions
            # from that level in the post-filter step (not here — need to check source_signals)
            if escalation_from:
                for type_key, level in DECISION_LEVEL.items():
                    if level == escalation_from:
                        relevant_types.add(type_key)
        else:
            relevant_types = type_filter  # None = all types

        all_decisions = []
        cutoff = datetime.utcnow() - timedelta(days=_DECISION_LOOKBACK_DAYS)

        # Find config_ids for this tenant (always tenant-scoped)
        config_filter = None
        if config_id:
            # Validate that the requested config belongs to this tenant
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
                select(Site.id, Site.name, Site.type).where(
                    Site.config_id.in_(config_filter)
                )
            )
            for sid, sname, stype in result.fetchall():
                # Prefer descriptive type ("Plant 1 US") over short code ("1710")
                display_name = stype if stype else sname
                if sname:
                    site_names[str(sname)] = display_name or sname
                    # Also map numeric ID → display name for decisions that stored IDs
                    if sid is not None:
                        site_names[str(sid)] = display_name or sname
        except Exception as e:
            logger.warning(f"Failed to load site names: {e}")

        # Build TradingPartner name lookup (for customer_id / tpartner_id on decisions)
        partner_names: Dict[str, str] = {}
        try:
            from app.models.sc_entities import TradingPartner as _TP
            tp_result = await self.db.execute(
                select(_TP.id, _TP.description, _TP.tpartner_type)
            )
            for tp_id, tp_desc, tp_type in tp_result.fetchall():
                if tp_id and tp_desc:
                    partner_names[str(tp_id)] = tp_desc
        except Exception as e:
            logger.warning(f"Failed to load trading partner names: {e}")

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

                # Stack-rank by risk/impact: urgency DESC, benefit DESC, then recency
                # This ensures the per-table limit keeps the highest-risk decisions
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
                    raw_cost = _safe_float(getattr(row, "cost_of_inaction", None)) or 0.0
                    raw_tp = _safe_float(getattr(row, "time_pressure", None)) or 0.0
                    raw_benefit = _safe_float(getattr(row, "expected_benefit", None)) or 0.0

                    # Compute urgency: if economic columns populated, use them;
                    # otherwise fall back to legacy urgency_at_time / urgency enum.
                    if raw_cost > 0 and raw_tp > 0:
                        computed_urgency = min(1.0, raw_cost * raw_tp / 1000.0)  # normalize $/day × pressure to 0-1
                    else:
                        computed_urgency = _safe_float(
                            getattr(row, "urgency_at_time", None)
                            or getattr(row, "urgency", None)
                        )

                    # Resolve trading partner names (customer/vendor) if present
                    raw_customer = getattr(row, "customer_id", None)
                    raw_vendor = getattr(row, "tpartner_id", None) or getattr(row, "vendor_id", None)
                    customer_name = partner_names.get(str(raw_customer)) if raw_customer else None
                    vendor_name = partner_names.get(str(raw_vendor)) if raw_vendor else None

                    # Use AIIO status from DB if available, else default
                    row_status = getattr(row, "status", "ACTIONED") or "ACTIONED"
                    row_level = getattr(row, "decision_level", None) or DECISION_LEVEL.get(type_key, "execution")

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "status": row_status,
                        "decision_level": row_level,
                        "summary": _humanize_ids(
                            _build_decision_summary(
                                row, type_key,
                                name_cache={"products": product_names, "sites": site_names},
                            ),
                            product_names,
                            site_names,
                        ),
                        "product_id": pid,
                        "product_name": product_names.get(str(pid)) if pid else None,
                        "site_id": site_id,
                        "site_name": site_names.get(str(site_id)) if site_id else None,
                        "customer_name": customer_name,
                        "vendor_name": vendor_name,
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
                        "decision_reasoning": _humanize_ids(raw_reasoning, product_names, site_names) if raw_reasoning else None,
                        "suggested_action": _humanize_ids(_get_suggested_action(row, type_key), product_names, site_names),
                        "deep_link": DEEP_LINK_MAP.get(type_key, "/insights/actions"),
                        "effective_from": _safe_effective_from(row, type_key),
                        "period_days": _safe_period_days(row, type_key),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "editable_values": _get_editable_values(row, type_key),
                        "context": {
                            "config_id": row.config_id,
                            "decision_method": getattr(row, "decision_method", None),
                            "triggered_by": getattr(row, "triggered_by", None),
                            # Site routing for rebalancing/TO coordination
                            "from_site_id": getattr(row, "from_site", None) or getattr(row, "source_site_id", None),
                            "to_site_id": getattr(row, "to_site", None) or getattr(row, "dest_site_id", None),
                        },
                    })

                    # Enrich ATP/PO decisions with pegging chain context
                    if type_key in ("atp", "po_creation") and pid:
                        try:
                            pegging_chain = await self._get_pegging_chain(row.config_id, pid, str(site_id) if site_id else None)
                            if pegging_chain:
                                all_decisions[-1]["pegging_chain"] = pegging_chain
                        except Exception:
                            pass  # Pegging is enrichment, not critical

            except Exception as e:
                import traceback
                logger.warning(f"Failed to query {type_key} decisions: {e}\n{traceback.format_exc()}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # ── Query GNN Directive Reviews (strategic + tactical + operational) ──
        gnn_types = {"sop_policy", "execution_directive", "network_directive", "allocation_refresh", "site_coordination"}
        if relevant_types is None or gnn_types & relevant_types:
            try:
                gnn_query = select(GNNDirectiveReview).where(
                    and_(
                        GNNDirectiveReview.config_id.in_(config_filter),
                        GNNDirectiveReview.created_at >= cutoff,
                    )
                )
                # Filter by scope if role-restricted
                if relevant_types is not None:
                    active_gnn = gnn_types & relevant_types
                    if active_gnn:
                        scope_map = {
                            "sop_policy": "sop_policy",
                            "execution_directive": "execution_directive",
                            "network_directive": "network_directive",
                            "allocation_refresh": "allocation_refresh",
                            "site_coordination": "site_coordination",
                        }
                        scopes = [scope_map[t] for t in active_gnn if t in scope_map]
                        gnn_query = gnn_query.where(
                            GNNDirectiveReview.directive_scope.in_(scopes)
                        )

                gnn_query = gnn_query.order_by(desc(GNNDirectiveReview.created_at)).limit(20)
                gnn_result = await self.db.execute(gnn_query)
                gnn_rows = gnn_result.scalars().all()

                for row in gnn_rows:
                    scope = row.directive_scope
                    type_key = scope
                    level = getattr(row, "decision_level", None) or DECISION_LEVEL.get(type_key, "tactical")
                    confidence = row.model_confidence or 0.5

                    # ── Vertical Urgency Propagation ─────────────────────
                    # Priority 1: propagated_urgency — computed from lower-level
                    # signals that couldn't be resolved locally and escalated up.
                    # This is the CORRECT urgency for GNN decisions because it
                    # reflects WHY this decision is needed (execution-level pain).
                    propagated = _safe_float(getattr(row, "propagated_urgency", None))
                    if propagated and propagated > 0:
                        gnn_urgency = propagated
                    else:
                        # Priority 2: derive from model outputs
                        proposed = row.proposed_values or {}
                        if scope == "sop_policy":
                            bottleneck = proposed.get("bottleneck_risk", 0)
                            concentration = proposed.get("concentration_risk", 0)
                            gnn_urgency = max(bottleneck, concentration, 0.3)
                        elif scope == "execution_directive":
                            exc_prob = proposed.get("exception_probability", [0, 0, 1])
                            stockout_prob = exc_prob[0] if isinstance(exc_prob, list) and len(exc_prob) > 0 else 0
                            gnn_urgency = max(stockout_prob, 0.3)
                        else:
                            gnn_urgency = 0.5

                    # ── Build summary with escalation context ────────────
                    proposed = row.proposed_values or {}
                    source_signals = getattr(row, "source_signals", None) or []
                    blocked_by = getattr(row, "local_resolution_blocked_by", None)
                    revenue = _safe_float(getattr(row, "revenue_at_risk", None))
                    cost_delay = _safe_float(getattr(row, "cost_of_delay_per_day", None))
                    site_display = site_names.get(str(row.site_key), row.site_key)

                    if scope == "sop_policy":
                        # Strategic policy — describe what's changing
                        policy_action = proposed.get("action", "")
                        policy_param = proposed.get("policy_parameter", "")
                        proposed_val = proposed.get("proposed_value")
                        current_val = proposed.get("current_value")
                        change_pct = proposed.get("change_pct")
                        ss_mult = proposed.get("safety_stock_multiplier", None)

                        if policy_action:
                            action_desc = policy_action.replace("_", " ").title()
                            summary = f"Strategic Policy: {action_desc} at {site_display}"
                            action = f"Review: {action_desc}"
                        elif policy_param and proposed_val is not None:
                            param_label = policy_param.replace("_", " ").title()
                            change_str = f" ({change_pct:+.1f}%)" if change_pct else ""
                            summary = f"Strategic Policy: {param_label} → {proposed_val}{change_str}"
                            action = f"Review {param_label} adjustment"
                        elif ss_mult and ss_mult != 1.0:
                            summary = f"Strategic Policy: Safety stock adjustment to {ss_mult:.2f}x at {site_display}"
                            action = f"Review safety stock multiplier {ss_mult:.2f}x"
                        else:
                            summary = f"Strategic Policy Review at {site_display}"
                            action = "Review strategic policy recommendation"
                    elif scope == "execution_directive":
                        # Tactical/operational — describe the directive meaningfully
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
                            # Translate internal action names to clear business language
                            _action_labels = {
                                "pre_position": "Transfer",
                                "reallocate": "Reallocate",
                                "demand_shift": "Redirect",
                                "rebalance": "Rebalance",
                                "expedite": "Expedite",
                                "consolidate": "Consolidate",
                            }
                            action_label = _action_labels.get(alloc_action, alloc_action.replace("_", " ").title())
                            from_display = site_names.get(str(from_site), from_site) if from_site else "?"
                            to_display = site_names.get(str(to_site), to_site) if to_site else "?"
                            summary = f"{action_label} {int(alloc_qty)} units of {alloc_pdesc} from {from_display} to {to_display}"
                            action = f"{action_label} {int(alloc_qty)} units from {from_display} → {to_display}"
                        elif coord_action:
                            action_label = coord_action.replace("_", " ").title()
                            summary = f"Site Coordination: {action_label} at {site_display}"
                            action = f"Review: {action_label}"
                        elif order_rec and order_rec > 0:
                            summary = f"Planning Directive: {order_rec:.0f} units at {site_display}"
                            action = f"Execute {order_rec:.0f} unit order"
                        elif demand_fcst:
                            fcst_val = demand_fcst if isinstance(demand_fcst, (int, float)) else "updated"
                            summary = f"Demand Forecast Update at {site_display}"
                            action = f"Review demand forecast: {fcst_val}"
                        elif alloc:
                            summary = f"Allocation Directive at {site_display}"
                            action = "Review allocation adjustment"
                        else:
                            summary = f"Planning Directive at {site_display}"
                            action = "Review planning recommendation"
                    else:
                        summary = f"Allocation Update at {site_display}"
                        action = "Review and approve allocation changes"

                    # Enrich reasoning with vertical escalation context
                    reasoning_parts = []
                    if row.proposed_reasoning:
                        reasoning_parts.append(row.proposed_reasoning)
                    if source_signals:
                        sig_descs = []
                        for sig in source_signals[:3]:
                            # Map internal agent type to business-friendly name
                            agent_key = sig.get('agent_type', sig.get('trm_type', '?'))
                            agent_label = self._DIGEST_TYPE_LABELS.get(agent_key, agent_key.replace('_', ' ').title())
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
                    # Add financial estimate from quantity + generic cost assumptions
                    _alloc_qty = proposed.get("quantity", 0) if proposed else 0
                    if not revenue and not cost_delay and _alloc_qty:
                        try:
                            qty_val = float(_alloc_qty)
                            # Estimate: $2/unit holding cost/week, $5/unit stockout cost/week
                            holding_exp = qty_val * 2.0
                            stockout_exp = qty_val * 5.0
                            reasoning_parts.append(
                                f"**Financial impact**: Holding cost exposure ~${holding_exp:,.0f}/week, "
                                f"stockout cost exposure ~${stockout_exp:,.0f}/week"
                            )
                        except (TypeError, ValueError):
                            pass

                    enriched_reasoning = " | ".join(reasoning_parts) if reasoning_parts else None
                    site_display = site_names.get(str(row.site_key), row.site_key)

                    # Extract product_id from proposed_values for GNN directives
                    gnn_pid = proposed.get("product_id")
                    gnn_pname = product_names.get(str(gnn_pid)) if gnn_pid else None

                    # Compute effective dates for GNN directives
                    gnn_eff_from = row.created_at.date().isoformat() if row.created_at else None
                    gnn_period = 14  # tactical directives default to 2-week horizon
                    if scope == "sop_policy":
                        gnn_period = 28  # strategic = 4 weeks
                    elif scope == "site_coordination":
                        gnn_period = 7   # operational = 1 week

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "decision_level": level,
                        "summary": summary,
                        "product_id": gnn_pid,
                        "product_name": gnn_pname,
                        "site_id": row.site_key,
                        "site_name": site_display,
                        "urgency": _urgency_label(gnn_urgency),
                        "urgency_score": gnn_urgency,
                        "likelihood": _likelihood_label(confidence),
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

        # ── Query Governance Decisions (directives, policy changes) ────────
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
                        "period_days": 28,  # governance directives default 4-week horizon
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

        # ── Rebalancing cooldown dedup ────────────────────────────────────
        # Suppress duplicate rebalancing decisions for the same product+site pair
        # within the cooldown window. Keep only the most recent (highest urgency).
        if _REBALANCE_COOLDOWN_HOURS > 0:
            cooldown_cutoff = datetime.utcnow() - timedelta(hours=_REBALANCE_COOLDOWN_HOURS)
            seen_rebalance: dict[str, dict] = {}  # key → best decision
            deduped = []
            for d in all_decisions:
                if d.get("decision_type") == "rebalancing":
                    ev = d.get("editable_values") or {}
                    key = f"{d.get('product_id')}|{ev.get('from_site_id')}|{ev.get('to_site_id')}"
                    created = d.get("created_at")
                    # If an earlier decision for same route exists within cooldown, keep highest urgency
                    prev = seen_rebalance.get(key)
                    if prev is None:
                        seen_rebalance[key] = d
                        deduped.append(d)
                    else:
                        # Replace if this one has higher urgency
                        if (d.get("urgency_score") or 0) > (prev.get("urgency_score") or 0):
                            deduped = [x for x in deduped if x is not prev]
                            seen_rebalance[key] = d
                            deduped.append(d)
                        # else: suppress duplicate
                else:
                    deduped.append(d)
            all_decisions = deduped

        # ── Post-filter: escalation passthrough ──────────────────────────
        # If a role only sees "tactical" by default but has escalation_from="execution",
        # keep execution decisions ONLY if they have source_signals (i.e., were escalated).
        if allowed_levels and escalation_from:
            filtered = []
            for d in all_decisions:
                d_level = d.get("decision_level", "execution")
                if d_level in allowed_levels:
                    # Decision is at a level this role sees by default — keep
                    filtered.append(d)
                elif d_level == escalation_from:
                    # Decision is from the escalation level — only keep if escalated
                    ctx = d.get("context", {})
                    has_escalation = (
                        ctx.get("source_signals")
                        or ctx.get("escalation_id")
                        or (d.get("urgency_score") or 0) >= 0.75  # high urgency = escalation-worthy
                    )
                    if has_escalation:
                        filtered.append(d)
                    # else: routine decision at lower level — drop
                else:
                    # Decision is at a level this role doesn't see at all — drop
                    pass
            all_decisions = filtered

        # ── Consolidate: group multiple decisions for the same
        # (product, site, decision_type) into a single card showing the
        # net effect. This prevents the Decision Stream from showing N
        # cards for the same item when the seeder emits per-period rows.
        all_decisions = _consolidate_decisions(all_decisions, product_names, site_names)

        return all_decisions, product_names, site_names

    async def _get_pegging_chain(
        self, config_id: int, product_id: str, site_id: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Look up the pegging chain for a product at a site.

        Returns a list of pegging links ordered by chain_depth, showing
        the full supply-demand trace from customer order to vendor PO.
        """
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
        return kept  # No artificial cap — return all decisions; LLM summary has its own limit

    async def _mark_decisions_informed(self, decisions: List[Dict[str, Any]]) -> None:
        """Mark surfaced decisions as INFORMED in the DB (AIIO state transition).

        Only transitions ACTIONED → INFORMED. Does not regress INSPECTED or OVERRIDDEN.
        This is fire-and-forget — errors are logged but don't fail the digest.
        """
        from sqlalchemy import text as sa_text

        # Group decision IDs by their source table
        by_table: Dict[str, List[int]] = {}
        for dec in decisions:
            if dec.get("status") != "ACTIONED":
                continue  # Already INFORMED/INSPECTED/OVERRIDDEN — don't regress
            dtype = dec.get("decision_type", "")
            # Map decision_type back to table name
            table = DECISION_TYPE_TABLE_MAP.get(dtype)
            if table:
                by_table.setdefault(table, []).append(dec["id"])

        for table, ids in by_table.items():
            if not ids:
                continue
            try:
                # Batch update: ACTIONED → INFORMED
                await self.db.execute(
                    sa_text(f"""
                        UPDATE {table}
                        SET status = 'INFORMED'
                        WHERE id = ANY(:ids) AND status = 'ACTIONED'
                    """),
                    {"ids": ids},
                )
                await self.db.commit()
            except Exception as e:
                logger.warning("Failed to mark %s decisions as INFORMED: %s", table, e)
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        # Also update the in-memory decision dicts so the response reflects the new status
        for dec in decisions:
            if dec.get("status") == "ACTIONED":
                dec["status"] = "INFORMED"

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
        decision_level: Optional[str] = None,
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
        if decision_level:
            role_context = f"You are addressing a {decision_level.replace('_', ' ')} user. "

        prompt = (
            f"You are an AI supply chain planning assistant for {self.tenant_name}. "
            f"{role_context}"
            f"Summarize the key agent decisions as a short markdown bulleted list for the planner. "
            f"Start with a one-line header like '**{len(decisions)} decisions** made by Autonomy agents:' "
            f"then list the 3-5 most important decisions as bullet points (use '- **Category**: details' format). "
            f"Be specific about product names, sites, and quantities. "
            f"Group related decisions where possible (e.g. combine multiple POs into one bullet). "
            f"Do NOT list all {len(decisions)} — just the highlights. "
            f"NEVER use internal technology names (tGNN, TRM, GraphSAGE, GNN). "
            f"Use business terms: 'Strategic Policy', 'Planning Directive', 'Procurement Agent', etc.\n\n"
            f"Decisions:\n"
            + "\n".join(f"- {s}" for s in decision_summaries)
            + "\n\n"
            + (f"Active alerts ({len(alerts)}):\n" + "\n".join(f"- {s}" for s in alert_summaries) if alerts else "No active alerts.")
        )

        def _template_fallback() -> str:
            lines = [f"**{len(decisions)} decisions** made by Autonomy agents:"]
            for d in decisions[:5]:
                dtype = d.get('decision_type', 'Decision')
                label = self._DIGEST_TYPE_LABELS.get(dtype, dtype.replace('_', ' ').title())
                lines.append(f"- **{label}**: {d['summary']}")
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

            # Load products — index by ID, description, SKU, and word combinations
            result = await self.db.execute(
                select(Product.id, Product.description, Product.product_group_name).where(
                    Product.config_id.in_(cfg_ids)
                )
            )
            for pid, desc, group in result.fetchall():
                product_lookup[pid.lower()] = pid
                # Base SKU (e.g., "FP006" → CFG129_FP006)
                for prefix_id in cfg_ids:
                    base = pid.replace(f"CFG{prefix_id}_", "")
                    if base != pid:
                        product_lookup[base.lower()] = pid
                if desc:
                    # Full description
                    product_lookup[desc.lower()] = pid
                    # Every word ≥3 chars (including "frozen", "turkey", etc.)
                    desc_words = []
                    for word in desc.split():
                        w = word.strip(",.()-").lower()
                        if len(w) >= 3:
                            product_lookup[w] = pid
                            desc_words.append(w)
                    # Index 2-word combinations for phrase matching
                    # "frozen turkey" → FP004, "beef patties" → FP002, etc.
                    for i in range(len(desc_words) - 1):
                        bigram = f"{desc_words[i]} {desc_words[i+1]}"
                        product_lookup[bigram] = pid
                # Product group name
                if group:
                    product_lookup[group.lower()] = pid

            # Load sites — index by code, human name, region, city, and keywords
            result = await self.db.execute(
                select(Site.name, Site.type, Site.attributes, Site.master_type).where(
                    Site.config_id.in_(cfg_ids)
                )
            )
            for sname, stype, sattrs, smaster in result.fetchall():
                site_lookup[sname.lower()] = sname
                # Index by human-readable name from attributes
                if sattrs and isinstance(sattrs, dict):
                    for key in ("customer_name", "supplier_name", "name"):
                        display = sattrs.get(key)
                        if display:
                            site_lookup[display.lower()] = sname
                            # Index ALL words ≥3 chars (no exclusion list)
                            for word in display.split():
                                w = word.strip(",.()-").lower()
                                if len(w) >= 3:
                                    site_lookup[w] = sname
                    # Index region, city, state from attributes
                    for key in ("region", "city", "state", "segment"):
                        val = sattrs.get(key)
                        if val and len(str(val)) >= 2:
                            site_lookup[str(val).lower()] = sname
                # Index from type field (e.g., "Customer - Phoenix, AZ" or "Supplier - Tyson Foods Inc")
                if stype and " - " in str(stype):
                    display = str(stype).split(" - ", 1)[-1]
                    site_lookup[display.lower()] = sname
                    # Also index individual parts (city name without state)
                    for part in display.split(","):
                        p = part.strip().lower()
                        if len(p) >= 3:
                            site_lookup[p] = sname
                # Index by region code from site name pattern (RDC_NW → "nw", "northwest")
                if sname.startswith("RDC_"):
                    region = sname.replace("RDC_", "").lower()
                    site_lookup[region] = sname
                    region_names = {"nw": "northwest", "sw": "southwest", "ne": "northeast", "se": "southeast"}
                    if region in region_names:
                        site_lookup[region_names[region]] = sname
                # Index customer by master type shorthand
                if smaster == "CUSTOMER":
                    site_lookup[f"customer {sname.replace('CUST_', '').lower()}"] = sname

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

        # Build clarification options when matches are ambiguous.
        # Each clarification has: field, question, category (entity type label),
        # type='select', options[], searchable=True, none_option=True
        clarifications = []

        async def _product_options(product_id_set=None):
            """Build product dropdown options from a set of IDs or full catalog."""
            from app.models.sc_entities import Product as _Prod
            q = select(_Prod.id, _Prod.description).order_by(_Prod.id).limit(50)
            if product_id_set:
                q = q.where(_Prod.id.in_(list(product_id_set)))
            else:
                q = q.where(_Prod.config_id == config_id)
            result = await self.db.execute(q)
            return [
                f"{r[0].replace(f'CFG{config_id}_', '')} — {r[1] or 'N/A'}"
                for r in result.fetchall()
            ]

        async def _site_options(site_name_set=None, master_type=None):
            """Build site dropdown options, optionally filtered by master_type."""
            q = select(Site.name, Site.type, Site.attributes).where(
                Site.config_id == config_id
            ).order_by(Site.name)
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

        # If multiple products matched, narrow down with best matches
        if len(product_ids) > 3:
            clarifications.append({
                "field": "product",
                "question": "Which of these PRODUCTS do you mean?",
                "category": "PRODUCTS",
                "type": "select",
                "options": await _product_options(product_ids),
                "searchable": True,
                "none_option": True,
                "required": True,
            })

        # If multiple sites matched, determine the most likely entity type
        if len(site_ids) > 3:
            # Check if matched sites are mostly customers, suppliers, or internal
            matched_sites = [s for s in sites if s[0] in site_ids] if 'sites' in dir() else []
            customer_matches = [s for s in matched_sites if s[2] == "CUSTOMER"]
            vendor_matches = [s for s in matched_sites if s[2] == "VENDOR"]

            if len(customer_matches) > len(vendor_matches):
                category = "CUSTOMERS"
                opts = await _site_options(site_ids, "CUSTOMER")
            elif len(vendor_matches) > len(customer_matches):
                category = "SUPPLIERS"
                opts = await _site_options(site_ids, "VENDOR")
            else:
                category = "SITES"
                opts = await _site_options(site_ids)

            clarifications.append({
                "field": "site",
                "question": f"Which of these {category} do you mean?",
                "category": category,
                "type": "select",
                "options": opts,
                "searchable": True,
                "none_option": True,
                "required": True,
            })

        # If no products matched but message references one, show full catalog
        if not product_ids and any(kw in combined_lower for kw in (
            "product", "sku", "item", "beef", "chicken", "pork", "dairy",
            "cheese", "yogurt", "butter", "juice", "ice cream", "pasta",
            "wagyu", "wagu", "seafood", "turkey",
        )):
            opts = await _product_options()
            if opts:
                clarifications.append({
                    "field": "product",
                    "question": "Which of these PRODUCTS do you mean?",
                    "category": "PRODUCTS",
                    "type": "select",
                    "options": opts,
                    "searchable": True,
                    "none_option": True,
                    "required": True,
                })

        # If no sites matched but message references a location
        if not site_ids and any(kw in combined_lower for kw in (
            "site", "warehouse", "dc", "customer", "supplier", "location",
            "region", "store", "deliver",
        )):
            # Determine entity type from keywords
            if any(kw in combined_lower for kw in ("customer", "deliver", "store")):
                category, master = "CUSTOMERS", "CUSTOMER"
            elif any(kw in combined_lower for kw in ("supplier", "vendor")):
                category, master = "SUPPLIERS", "VENDOR"
            else:
                category, master = "SITES", None

            opts = await _site_options(master_type=master)
            if opts:
                clarifications.append({
                    "field": "site",
                    "question": f"Which of these {category} do you mean?",
                    "category": category,
                    "type": "select",
                    "options": opts,
                    "searchable": True,
                    "none_option": True,
                    "required": False,
                })

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
            return {"data_blocks": [], "context_text": "", "clarifications": clarifications}

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
            "clarifications": clarifications,
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
        decision_level: Optional[str] = None,
    ) -> str:
        """Get a brief text summary of pending decisions for chat context injection."""
        try:
            decisions, _pnames, _snames = await self._collect_pending_decisions(config_id, decision_level)
            if not decisions:
                return "No recent agent decisions."
            summaries = [d["summary"] for d in decisions[:_DIGEST_SUMMARY_MAX_DECISIONS]]
            return f"Decisions made by Autonomy agents ({len(decisions)} total): " + "; ".join(summaries)
        except Exception:
            return "Unable to load decision context."

    async def _get_dag_topology(self, config_id: Optional[int] = None) -> str:
        """Load the SC config DAG topology + full product catalog for LLM context.

        Returns a complete text representation of sites, products (with IDs,
        descriptions, categories, suppliers), vendors, and customers so the
        LLM can accurately identify any product or entity the user mentions.
        """
        if not config_id:
            return ""
        try:
            from app.models.supply_chain_config import Site
            from app.models.sc_entities import Product, TradingPartner

            prefix = f"CFG{config_id}_"
            parts = []

            # Sites — all sites with master type and human-readable names
            result = await self.db.execute(
                select(Site.name, Site.type, Site.master_type, Site.attributes).where(
                    Site.config_id == config_id
                )
            )
            sites = result.fetchall()
            if sites:
                internal_lines = []
                vendor_lines = []
                customer_lines = []
                for s_name, s_type, s_master, s_attrs in sites:
                    # Extract human-readable name from attributes or type
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

            # Product groups (distinct)
            result = await self.db.execute(
                select(Product.product_group_name).where(
                    Product.config_id == config_id,
                    Product.product_group_name.isnot(None),
                ).distinct().limit(30)
            )
            groups = [r[0] for r in result.fetchall() if r[0]]
            if groups:
                parts.append(f"Product categories: {', '.join(sorted(groups))}")

            # FULL product catalog — load ALL products with ID, description, group
            result = await self.db.execute(
                select(
                    Product.id, Product.description, Product.product_group_name,
                    Product.unit_of_measure,
                ).where(
                    Product.config_id == config_id,
                ).order_by(Product.id).limit(500)
            )
            all_products = result.fetchall()
            if all_products:
                product_lines = []
                for pid, desc, group, uom in all_products:
                    sku = pid.replace(prefix, "") if pid.startswith(prefix) else pid
                    line = f"  {sku}: {desc or 'N/A'}"
                    if group:
                        line += f" [{group}]"
                    product_lines.append(line)
                parts.append(f"PRODUCT CATALOG ({len(all_products)} products):\n" + "\n".join(product_lines))

            # Vendor-product mapping (which supplier carries which product)
            try:
                from app.models.supplier import VendorProduct
                vp_result = await self.db.execute(
                    select(VendorProduct.product_id, VendorProduct.tpartner_id).where(
                        VendorProduct.product_id.like(f"{prefix}%")
                    ).limit(200)
                )
                vp_rows = vp_result.fetchall()
                if vp_rows:
                    vp_map = {}
                    for pid, vendor in vp_rows:
                        sku = pid.replace(prefix, "")
                        vendor_name = vendor.replace(prefix, "") if vendor and vendor.startswith(prefix) else vendor
                        vp_map.setdefault(vendor_name, []).append(sku)
                    vp_lines = [f"  {v}: {', '.join(skus)}" for v, skus in sorted(vp_map.items())]
                    parts.append(f"SUPPLIER-PRODUCT MAPPING:\n" + "\n".join(vp_lines))
            except Exception:
                pass

            # Trading partners (config-scoped)
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

    async def _get_bsc_context(self, config_id: Optional[int] = None) -> str:
        """Load balanced scorecard data for performance comparisons.

        Provides the LLM with actual KPI values so it can answer
        questions like 'best performing region' or 'worst product group'
        without saying 'I don't have that data'.
        """
        if not config_id:
            return ""
        try:
            from sqlalchemy import text as _t

            parts = []

            # Executive dashboard KPIs (from performance_metrics, scoped by tenant)
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

            # Agent decision summary by type (using config_id for decision tables)
            cid = config_id or 0
            result = await self.db.execute(
                _t("""
                    SELECT 'ATP Agent' as agent, COUNT(*) as decisions,
                           AVG(confidence) as avg_confidence
                    FROM powell_atp_decisions WHERE config_id = :cid
                    UNION ALL
                    SELECT 'Procurement Agent', COUNT(*), AVG(confidence)
                    FROM powell_po_decisions WHERE config_id = :cid
                    UNION ALL
                    SELECT 'Rebalancing Agent', COUNT(*), AVG(confidence)
                    FROM powell_rebalance_decisions WHERE config_id = :cid
                    UNION ALL
                    SELECT 'Demand Agent', COUNT(*), AVG(confidence)
                    FROM powell_forecast_adjustment_decisions WHERE config_id = :cid
                    UNION ALL
                    SELECT 'Inventory Agent', COUNT(*), AVG(confidence)
                    FROM powell_buffer_decisions WHERE config_id = :cid
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

            # Inventory summary by site
            result = await self.db.execute(
                _t("""
                    SELECT s.name, s.type,
                           COUNT(DISTINCT il.product_id) as products,
                           SUM(il.on_hand_qty) as total_on_hand
                    FROM inv_level il
                    JOIN site s ON s.id = il.site_id
                    WHERE il.config_id = :cid
                    GROUP BY s.name, s.type
                    ORDER BY total_on_hand DESC
                """),
                {"cid": cid},
            )
            rows = result.fetchall()
            if rows:
                inv_lines = []
                for r in rows:
                    inv_lines.append(f"  {r[0]} ({r[1]}): {r[2]} products, {r[3]:,.0f} units on hand")
                parts.append("Inventory by Site:\n" + "\n".join(inv_lines))

            if parts:
                return "=== BALANCED SCORECARD & KPI DATA ===\n" + "\n\n".join(parts) + "\n=== END BSC ==="
            return ""
        except Exception as e:
            logger.debug("BSC context load failed: %s", e)
            return ""

    async def _get_external_signals_context(self) -> str:
        """Load recent external market intelligence for outside-in planning context.

        Injects weather, economic, energy, geopolitical, sentiment, and regulatory
        signals from the tenant's configured sources into the chat context.
        """
        try:
            from app.services.external_signal_service import ExternalSignalService
            service = ExternalSignalService(self.db, self.tenant_id)
            return await service.get_signals_for_chat_context(max_signals=8, max_age_days=7)
        except Exception as e:
            logger.debug("External signals context load failed: %s", e)
            return ""

    async def _get_experiential_knowledge_context(self) -> str:
        """Load active experiential knowledge for planner behavioral pattern context.

        Injects structured knowledge entities (GENUINE/COMPENSATING) from
        override pattern detection into the chat context. Based on Alicke's
        'The Planner Was the System'.
        """
        try:
            from app.services.experiential_knowledge_service import ExperientialKnowledgeService
            from app.db.session import sync_session_factory
            sync_db = sync_session_factory()
            try:
                service = ExperientialKnowledgeService(
                    db=sync_db, tenant_id=self.tenant_id, config_id=self.config_id
                )
                return service.get_knowledge_for_chat_context(max_entities=8)
            finally:
                sync_db.close()
        except Exception as e:
            logger.debug("Experiential knowledge context load failed: %s", e)
            return ""

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

    # Role descriptions for Azirella system prompt
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

    def _build_chat_prompt(
        self,
        message: str,
        history: List[Dict[str, str]],
        rag_results: list,
        decision_context: str,
        decision_level: Optional[str] = None,
    ) -> str:
        """Build the LLM prompt with decision context, RAG, role scope, and conversation history."""
        parts = []

        # System prompt with role-scoped instructions
        role_info = self._ROLE_DESCRIPTIONS.get(decision_level, {})
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
            "2. Present options as a concise list: 'Do you mean globally, or for a specific region? "
            "The regions in your network are: US, Americas, Europe, Asia.'\n"
            "3. If the user gives an invalid value (e.g., 'Moon' as a region), respond: "
            "'I don\\'t recognise \"Moon\" as a region. The valid regions are: [list from topology].'\n"
            "4. If the topology section is missing or empty, say: 'I don\\'t have the network topology "
            "loaded. Could you specify which site or product you mean?'\n"
            "5. For product queries, offer product groups first, then specific products if the group is known.\n"
            "6. Keep clarification questions short — one question at a time."
        )

        # ── Supply Chain Language Glossary ────────────────────────────────
        # Teach the LLM common SC terms so users don't need to be precise
        system_prompt += (
            "\n\nSUPPLY CHAIN GLOSSARY — interpret user language using these definitions:\n"
            "- 'best performing' / 'top performing' = highest balanced scorecard composite "
            "(OTIF × fill rate × margin, weighted by revenue). Compare across the dimension the user specifies.\n"
            "- 'worst performing' = lowest BSC composite. Flag the underperformers.\n"
            "- 'region' = customer delivery region (demand side), NOT internal site. "
            "In a distribution network: NW, SW, Central, NE, SE. In a global network: US, Americas, Europe, Asia.\n"
            "- 'site' / 'DC' / 'warehouse' = internal operational location (supply side).\n"
            "- 'product group' / 'category' / 'family' = product hierarchy category (e.g., Frozen Proteins, Beverages).\n"
            "- 'margin' = gross margin % from the balanced scorecard, NOT unit cost.\n"
            "- 'service level' = OTIF (On-Time In-Full) unless specified otherwise.\n"
            "- 'fill rate' = order fill rate (% of demand fulfilled from available inventory).\n"
            "- 'DOS' / 'days of supply' = on-hand inventory ÷ average daily demand.\n"
            "- 'C2C' / 'cash-to-cash' = DIO + DSO - DPO (inventory + receivables - payables in days).\n"
            "- 'cost to serve' = total supply chain cost per unit delivered to customer.\n"
            "- 'bullwhip' = demand amplification ratio (upstream order variance ÷ downstream demand variance).\n"
            "- 'lead time' = supplier delivery lead time (procurement context) or customer promise time (sales context).\n"
            "- 'safety stock' / 'buffer' = inventory held to absorb demand/supply uncertainty.\n"
            "- 'reorder point' = inventory level that triggers a replenishment order.\n"
            "- 'ATP' = Available-to-Promise (uncommitted inventory available for new orders).\n"
            "- 'CTP' = Capable-to-Promise (what CAN be made/procured to fulfill an order).\n"
            "- 'MO' = Manufacturing Order. 'PO' = Purchase Order. 'TO' = Transfer Order.\n"
            "- 'override' = human planner changed an agent's recommendation.\n"
            "- 'touchless rate' = % of decisions handled autonomously without human intervention.\n"
            "- 'MPS' = Master Production Schedule. 'MRP' = Material Requirements Planning.\n"
            "- 'BOM' = Bill of Materials. 'BOM explosion' = MRP calculating component needs from parent.\n"
            "- 'WIP' = Work in Process. 'FG' = Finished Goods. 'RM' = Raw Materials. 'SFG' = Semi-Finished Goods.\n"
            "- 'MTS' = Make-to-Stock. 'MTO' = Make-to-Order. 'ATO' = Assemble-to-Order.\n"
            "- 'RCCP' = Rough-Cut Capacity Planning. 'CRP' = Capacity Requirements Planning.\n"
            "- 'DRP' = Distribution Requirements Planning. 'APS' = Advanced Planning and Scheduling.\n"
            "- 'MAPE' = Mean Absolute Percentage Error (forecast accuracy). 'POF' = Perfect Order Fulfillment.\n"
            "- 'OFCT' = Order Fulfillment Cycle Time. 'TCTS' = Total Cost to Serve.\n"
            "- 'EOQ' = Economic Order Quantity. 'MOQ' = Minimum Order Quantity. 'LFL' = Lot-for-Lot.\n"
            "- 'VMI' = Vendor Managed Inventory. 'CPFR' = Collaborative Planning Forecasting & Replenishment.\n"
            "- 'DDMRP' = Demand Driven MRP. 'MEIO' = Multi-Echelon Inventory Optimization.\n"
            "\nCONVERSATIONAL EXPRESSIONS — translate planner slang to formal concepts:\n"
            "- 'we're running low' = inventory approaching or below safety stock\n"
            "- 'we're out' = stockout, ATP = 0\n"
            "- 'we're behind' = production or shipments behind schedule\n"
            "- 'we can't ship' = ATP shortfall\n"
            "- 'the supplier is late' = PO past due\n"
            "- 'bump the forecast' = increase demand forecast\n"
            "- 'cut the forecast' = decrease demand forecast\n"
            "- 'push out the order' = delay/de-expedite\n"
            "- 'pull in the order' = expedite/bring forward\n"
            "- 'the line is down' = unplanned production downtime\n"
            "- 'we're overstocked' = inventory above max level\n"
            "- 'we're loaded' = near/at capacity utilization\n"
            "- 'we've got room' = available capacity\n"
            "- 'hot order' = urgent, high-priority order\n"
            "- 'we're chasing' / 'firefighting' = reactive mode, not planning ahead\n"
            "- 'build ahead' = anticipation stock / pre-build\n"
            "- 'we're on allocation' = supply constrained, rationing to customers\n"
            "- 'firm it up' = lock the planned order from MRP changes\n"
            "- 'release it' = authorize for execution (PO/MO/TO)\n"
            "- 'net it out' = MRP netting calculation\n"
            "- 'blow up the BOM' = BOM explosion\n"
            "- 'what can we promise?' = ATP/CTP check\n"
            "- 'the plan is clean' = no exceptions. 'the plan is dirty' = many exceptions\n"
            "- 'burn down inventory' = intentional destocking\n"
            "- 'best performing' = highest BSC composite score (OTIF x fill rate x margin)\n"
        )

        # ── Role-Aware Metric Interpretation ──────────────────────────────
        # What metrics each role cares about when they say "performance"
        ROLE_METRICS = {
            "SC_VP": (
                "When this user asks about 'performance', 'how are we doing', or 'best/worst', "
                "they mean STRATEGIC metrics: Revenue growth, EBIT margin, ROCS (Return on Capital), "
                "Gross Margin, OTIF, C2C cycle time, and Cost to Serve. "
                "Present comparisons as a ranked table with the BSC composite score."
            ),
            "EXECUTIVE": (
                "When this user asks about 'performance', they mean the EXECUTIVE DASHBOARD view: "
                "OTIF, fill rate, margin, cost/order, agent ROI metrics, revenue at risk. "
                "Compare across regions × product groups using the balanced scorecard. "
                "Lead with the headline number, then break down by dimension."
            ),
            "SOP_DIRECTOR": (
                "When this user asks about 'performance', they mean S&OP TACTICAL metrics: "
                "Perfect Order Fulfillment (POF = OTD × IF × DF × DA), demand forecast accuracy (MAPE), "
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
        role_metrics = ROLE_METRICS.get(decision_level, ROLE_METRICS.get("DEMO_ALL", ""))
        if role_metrics:
            system_prompt += f"\n\nMETRIC INTERPRETATION FOR THIS USER'S ROLE:\n{role_metrics}\n"

        if role_cannot and decision_level not in ("DEMO_ALL", "MPS_MANAGER"):
            system_prompt += (
                f"\n\nROLE BOUNDARIES: The user CAN: {role_can}. "
                f"The user CANNOT: {role_cannot}. "
                "If the user asks you to perform an action outside their role, "
                "politely explain what they CAN do and suggest who to contact for the action they requested. "
                "For example: 'As a Supply Chain Executive, I can help you understand the inventory position "
                "and agent decisions. To create a purchase order, your MPS Manager or Procurement team would need to action that.' "
                "Never refuse to answer questions — only refuse to execute actions outside their scope."
            )

        parts.append(system_prompt)

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
        """Call the LLM for Azirella chat responses.

        Strategy: Claude Haiku (primary) → Qwen/vLLM (fallback).
        Claude Haiku handles the full 7K+ context prompt easily (200K window).
        Qwen 8B is the air-gapped fallback but limited to ~3.9K tokens.
        """
        import os

        # ── Try Claude first (if API key configured) ──────────────────
        claude_key = os.getenv("CLAUDE_API_KEY", "")
        if claude_key:
            try:
                import httpx
                claude_model = os.getenv("CLAUDE_MODEL_HAIKU", "claude-haiku-4-5-20251001")

                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        json={
                            "model": claude_model,
                            "max_tokens": 1500,
                            "messages": [
                                {"role": "user", "content": prompt},
                            ],
                        },
                        headers={
                            "x-api-key": claude_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                    )
                    data = resp.json()

                    if resp.status_code == 200:
                        content_blocks = data.get("content", [])
                        text = " ".join(
                            b.get("text", "") for b in content_blocks if b.get("type") == "text"
                        )
                        if text.strip():
                            return text.strip()
                    else:
                        error = data.get("error", {}).get("message", str(data))
                        logger.warning(f"Claude API error ({resp.status_code}): {error}")
            except Exception as e:
                logger.warning(f"Claude call failed, falling back to local LLM: {e}")

        # ── Fallback: local Qwen/vLLM ────────────────────────────────
        try:
            import httpx
            api_base = os.getenv("LLM_API_BASE", "http://localhost:8001/v1")
            model = os.getenv("LLM_MODEL_NAME", "qwen3-8b")
            api_key = os.getenv("LLM_API_KEY", "not-needed")

            # Truncate prompt for small context windows
            max_prompt_chars = 6000  # ~1500 tokens, leave room for response
            truncated = prompt[:max_prompt_chars] if len(prompt) > max_prompt_chars else prompt

            # Qwen3 thinking mode wastes tokens — disable with /no_think
            if "qwen" in model.lower():
                truncated += "\n\n/no_think"

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": truncated}],
                        "temperature": 0.7,
                        "max_tokens": 800,
                    },
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Strip chain-of-thought <think>...</think> tags
            text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
            return text.strip() if text.strip() else "I couldn't generate a response. Please try again."
        except Exception as e:
            logger.error(f"LLM call failed (both Claude and local): {e}")
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

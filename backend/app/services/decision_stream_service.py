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

# In-memory conversation cache (same pattern as AssistantService)
_STREAM_CONVERSATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()

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

# Role relevance filter: which decision types each powell_role cares about
ROLE_RELEVANCE = {
    "SC_VP": {"atp", "rebalancing", "po_creation", "order_tracking", "forecast_adjustment", "inventory_buffer"},
    "EXECUTIVE": {"atp", "rebalancing", "po_creation", "order_tracking", "forecast_adjustment", "inventory_buffer"},
    "SOP_DIRECTOR": {"po_creation", "rebalancing", "forecast_adjustment", "inventory_buffer", "mo_execution", "to_execution"},
    "MPS_MANAGER": {"atp", "po_creation", "rebalancing", "order_tracking", "mo_execution", "to_execution", "quality", "maintenance", "subcontracting"},
    "ALLOCATION_MANAGER": {"atp", "rebalancing", "order_tracking"},
    "ORDER_PROMISE_MANAGER": {"atp", "order_tracking"},
    "DEMO_ALL": None,  # None = all types
}


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


def _build_decision_summary(decision, decision_type: str) -> str:
    """Build a human-readable one-line summary for any decision type.

    Column names must match the actual DB schema in powell_*_decisions tables.
    """
    product = getattr(decision, "product_id", None) or ""
    location = getattr(decision, "location_id", None) or getattr(decision, "from_site", None) or ""

    if decision_type == "atp":
        qty = getattr(decision, "requested_qty", "?")
        return f"ATP: Fulfill {qty} units of {product} at {location}"
    elif decision_type == "rebalancing":
        qty = getattr(decision, "recommended_qty", "?")
        src = getattr(decision, "from_site", "?")
        dest = getattr(decision, "to_site", "?")
        return f"Rebalance: Transfer {qty} of {product} from {src} to {dest}"
    elif decision_type == "po_creation":
        qty = getattr(decision, "recommended_qty", "?")
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
        return f"TO {dt}: {product} at {location}"
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
        if getattr(decision, "can_fulfill", False):
            return f"Fulfill {getattr(decision, 'promised_qty', '?')} units"
        return f"Cannot fulfill — suggest partial ({getattr(decision, 'promised_qty', 0)} of {getattr(decision, 'requested_qty', '?')})"
    elif decision_type == "rebalancing":
        return f"Transfer {getattr(decision, 'recommended_qty', '?')} units"
    elif decision_type == "po_creation":
        return f"Order {getattr(decision, 'recommended_qty', '?')} units"
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


class DecisionStreamService:
    """LLM-First Decision Stream with Decision-Back Planning."""

    def __init__(self, db: AsyncSession, tenant_id: int, tenant_name: str = ""):
        self.db = db
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name or f"Tenant {tenant_id}"
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    async def get_decision_digest(
        self,
        powell_role: Optional[str] = None,
        config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Collect pending decisions, alerts, and synthesize an LLM digest.

        Returns dict matching DecisionDigestResponse schema.
        """
        # 1. Collect pending decisions from all 11 tables
        decisions = await self._collect_pending_decisions(config_id, powell_role)

        # 2. Prioritize
        decisions = self._prioritize_decisions(decisions)

        # 3. Collect alerts (CDC triggers + condition monitor)
        alerts = await self._collect_alerts(config_id)

        # 4. Synthesize digest text via LLM
        digest_text = await self._synthesize_digest(decisions, alerts, powell_role)

        return {
            "digest_text": digest_text,
            "decisions": decisions,
            "alerts": alerts,
            "total_pending": len(decisions),
            "config_id": config_id,
        }

    async def act_on_decision(
        self,
        decision_id: int,
        decision_type: str,
        action: str,
        override_reason_code: Optional[str] = None,
        override_reason_text: Optional[str] = None,
        override_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Accept, override, or reject a pending decision.

        Updates the status column in the appropriate powell_*_decisions table.
        """
        # Find the model class for this decision type
        model_class = None
        for cls, type_key in DECISION_TABLES:
            if type_key == decision_type:
                model_class = cls
                break

        if not model_class:
            return {"success": False, "message": f"Unknown decision type: {decision_type}", "decision_id": decision_id, "new_status": "error"}

        # Determine new status
        status_map = {
            "accept": "ACCEPTED",
            "override": "OVERRIDDEN",
            "reject": "REJECTED",
        }
        new_status = status_map.get(action, "ACCEPTED")

        # Check if model has a status-like column
        # Most decision tables don't have explicit status, but we'll check common patterns
        try:
            result = await self.db.execute(
                select(model_class).where(model_class.id == decision_id)
            )
            decision = result.scalar_one_or_none()

            if not decision:
                return {"success": False, "message": f"Decision {decision_id} not found", "decision_id": decision_id, "new_status": "error"}

            # Update fields based on action
            if hasattr(decision, "was_committed"):
                decision.was_committed = (action == "accept")
            if hasattr(decision, "decision_method"):
                if action == "override":
                    decision.decision_method = "human_override"

            await self.db.commit()

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
    ) -> List[Dict[str, Any]]:
        """Query all 11 powell_*_decisions tables for recent decisions."""
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
                return []

        if not config_filter:
            return []

        for model_class, type_key in DECISION_TABLES:
            # Skip types not relevant to this role
            if relevant_types is not None and type_key not in relevant_types:
                continue

            try:
                query = select(model_class).where(
                    and_(
                        model_class.config_id.in_(config_filter),
                        model_class.created_at >= cutoff,
                    )
                ).order_by(desc(model_class.created_at)).limit(_DECISIONS_PER_TABLE)

                result = await self.db.execute(query)
                rows = result.scalars().all()

                for row in rows:
                    # Extract site_id from the correct column per table schema
                    if type_key == "rebalancing":
                        site_id = getattr(row, "from_site", None)
                    elif type_key == "order_tracking":
                        site_id = None  # order_exceptions has order_id, not location
                    else:
                        site_id = getattr(row, "location_id", None)

                    all_decisions.append({
                        "id": row.id,
                        "decision_type": type_key,
                        "summary": _build_decision_summary(row, type_key),
                        "product_id": getattr(row, "product_id", None),
                        "product_name": None,
                        "site_id": site_id,
                        "site_name": None,
                        "urgency": getattr(row, "urgency_at_time", None),
                        "confidence": getattr(row, "confidence", None),
                        "economic_impact": None,
                        "suggested_action": _get_suggested_action(row, type_key),
                        "deep_link": DEEP_LINK_MAP.get(type_key, "/insights/actions"),
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "context": {
                            "config_id": row.config_id,
                            "decision_method": getattr(row, "decision_method", None),
                            "triggered_by": getattr(row, "triggered_by", None),
                        },
                    })
            except Exception as e:
                logger.warning(f"Failed to query {type_key} decisions: {e}")
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        return all_decisions

    def _prioritize_decisions(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort by urgency DESC, confidence ASC, then cap at 20."""
        def sort_key(d):
            urgency = d.get("urgency") or 0.0
            # Low confidence = needs human more = should appear higher
            confidence_inv = 1.0 - (d.get("confidence") or _DEFAULT_CONFIDENCE)
            return (urgency, confidence_inv)

        decisions.sort(key=sort_key, reverse=True)
        return decisions[:_DIGEST_MAX_DECISIONS]

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
                f"Good news — your supply chain is running smoothly. "
                f"No pending decisions or alerts require your attention right now."
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
            f"Synthesize a brief, conversational digest (2-4 sentences) for the planner. "
            f"Mention the count and highest-priority items. Be specific about products/sites when available. "
            f"Do NOT list all decisions — just highlight the most important ones.\n\n"
            f"Pending decisions ({len(decisions)} total):\n"
            + "\n".join(f"- {s}" for s in decision_summaries)
            + "\n\n"
            + (f"Active alerts ({len(alerts)}):\n" + "\n".join(f"- {s}" for s in alert_summaries) if alerts else "No active alerts.")
        )

        try:
            return await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"LLM digest synthesis failed: {e}")
            # Fallback to a template-based digest
            top = decisions[0] if decisions else None
            top_desc = top["summary"] if top else "no items"
            return (
                f"You have {len(decisions)} pending decision{'s' if len(decisions) != 1 else ''} "
                f"and {len(alerts)} alert{'s' if len(alerts) != 1 else ''}. "
                f"The highest priority is: {top_desc}."
            )

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
                desc = getattr(row, "description", None)
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
                    f"Description: {desc}"
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
            decisions = await self._collect_pending_decisions(config_id, powell_role)
            if not decisions:
                return "No pending decisions."
            summaries = [d["summary"] for d in decisions[:_DIGEST_SUMMARY_MAX_DECISIONS]]
            return f"Pending decisions ({len(decisions)} total): " + "; ".join(summaries)
        except Exception:
            return "Unable to load decision context."

    async def _retrieve_context(self, query: str):
        """Retrieve RAG context from knowledge base."""
        try:
            results = await self.kb.search(query=query, top_k=3)
            return results
        except Exception as e:
            logger.warning(f"RAG search failed (non-fatal): {e}")
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
            "You help planners understand and act on pending decisions in their supply chain. "
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
            return result.get("content", "I couldn't generate a response. Please try again.")
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

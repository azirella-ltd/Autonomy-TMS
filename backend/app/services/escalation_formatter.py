"""
Escalation Formatter — Bridges agent-to-agent authorization (Tier 2) with
human escalation via OpenClaw (Tier 3).

When an AuthorizationThread times out, reaches low confidence, or is explicitly
escalated, this service:
  1. Queries HiveWhatIfEngine for ranked alternatives
  2. Formats a structured message with ranked options + BSC impact
  3. Returns the formatted escalation for delivery to OpenClaw

Human responses are parsed back to resolve the thread, with override reasoning
captured for RLHF training.

Architecture reference: AGENTIC_AUTHORIZATION_PROTOCOL.md Section 8
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EscalationFormatter:
    """Formats authorization escalations for human review via OpenClaw.

    Args:
        what_if_engine: HiveWhatIfEngine instance for scoring alternatives.
    """

    def __init__(self, what_if_engine=None):
        self.what_if_engine = what_if_engine

    def format_escalation(
        self,
        thread: Any,
        alternatives: Optional[List[Dict[str, Any]]] = None,
        max_alternatives: int = 3,
    ) -> Dict[str, Any]:
        """Format an authorization thread into a human-readable escalation.

        Args:
            thread: AuthorizationThread (from authorization_service or protocol).
            alternatives: Pre-computed alternatives. If None, generates from what-if engine.
            max_alternatives: Maximum alternatives to present.

        Returns:
            Structured escalation dict ready for OpenClaw delivery.
        """
        request_data = self._extract_request(thread)
        ranked = self._rank_alternatives(request_data, alternatives, max_alternatives)

        escalation = {
            "type": "authorization_escalation",
            "thread_id": getattr(thread, "thread_id", "unknown"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "urgency": self._determine_urgency(thread),
            "summary": self._build_summary(request_data),
            "context": {
                "requesting_agent": request_data.get("requesting_agent", "unknown"),
                "target_agent": request_data.get("target_agent", "unknown"),
                "site_key": request_data.get("site_key", ""),
                "action": request_data.get("proposed_action", {}),
                "justification": request_data.get("justification", ""),
            },
            "scorecard": request_data.get("balanced_scorecard"),
            "net_benefit": request_data.get("net_benefit", 0.0),
            "benefit_threshold": request_data.get("benefit_threshold", 0.0),
            "ranked_alternatives": ranked,
            "response_options": self._build_response_options(ranked),
            "escalation_reason": self._determine_reason(thread),
        }

        return escalation

    def parse_human_response(
        self,
        escalation: Dict[str, Any],
        selected_option: int,
        override_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse a human response to an escalation.

        Args:
            escalation: The original escalation dict.
            selected_option: 1-based index of the selected option.
            override_reason: Human's reason for the override.

        Returns:
            Resolution dict to apply to the authorization thread.
        """
        options = escalation.get("response_options", [])
        if selected_option < 1 or selected_option > len(options):
            return {
                "decision": "DENY",
                "reason": "Invalid option selected",
                "resolved_by": "human",
            }

        chosen = options[selected_option - 1]
        return {
            "decision": chosen.get("decision", "AUTHORIZE"),
            "reason": override_reason or chosen.get("description", ""),
            "resolved_by": "human",
            "selected_alternative": chosen,
            "is_override": chosen.get("is_override", False),
            "rlhf_data": {
                "escalation_thread_id": escalation.get("thread_id"),
                "human_choice_index": selected_option,
                "override_reason": override_reason,
                "net_benefit_at_decision": escalation.get("net_benefit", 0.0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_request(self, thread: Any) -> Dict[str, Any]:
        """Extract request data from different thread types."""
        # Handle authorization_service.AuthorizationThread (ORM model)
        if hasattr(thread, "requesting_agent"):
            request_data: Dict[str, Any] = {
                "requesting_agent": getattr(thread, "requesting_agent", ""),
                "target_agent": getattr(thread, "target_agent", ""),
                "site_key": getattr(thread, "site_key", ""),
                "net_benefit": getattr(thread, "net_benefit", 0.0),
                "benefit_threshold": getattr(thread, "benefit_threshold", 0.0),
            }
            # Try to get proposed_action from events
            events = getattr(thread, "events", []) or []
            for event in events:
                if isinstance(event, dict) and event.get("type") == "request_submitted":
                    request_data["justification"] = event.get("justification", "")
            return request_data

        # Handle authorization_protocol.AuthorizationThread (dataclass)
        if hasattr(thread, "request") and thread.request is not None:
            req = thread.request
            return {
                "requesting_agent": req.requesting_agent.value if hasattr(req.requesting_agent, "value") else str(req.requesting_agent),
                "target_agent": req.target_agent.value if hasattr(req.target_agent, "value") else str(req.target_agent),
                "site_key": getattr(req, "site_key", ""),
                "proposed_action": {
                    "action_type": req.proposed_action.action_type,
                    "description": req.proposed_action.description,
                } if hasattr(req, "proposed_action") else {},
                "balanced_scorecard": req.balanced_scorecard.to_dict() if hasattr(req, "balanced_scorecard") and hasattr(req.balanced_scorecard, "to_dict") else None,
                "net_benefit": getattr(req, "net_benefit", 0.0),
                "benefit_threshold": getattr(req, "benefit_threshold", 0.0),
                "justification": getattr(req, "justification", ""),
            }

        return {}

    def _rank_alternatives(
        self,
        request_data: Dict[str, Any],
        alternatives: Optional[List[Dict[str, Any]]],
        max_alternatives: int,
    ) -> List[Dict[str, Any]]:
        """Rank alternatives by net benefit."""
        if alternatives:
            ranked = sorted(alternatives, key=lambda a: a.get("net_benefit", 0), reverse=True)
            return ranked[:max_alternatives]

        # Generate alternatives via what-if engine if available
        if self.what_if_engine is not None:
            return self._generate_alternatives(request_data, max_alternatives)

        # Fallback: return the original proposal as only option
        return [{
            "label": "Original proposal",
            "description": request_data.get("justification", "Proceed as requested"),
            "net_benefit": request_data.get("net_benefit", 0.0),
            "scorecard": request_data.get("balanced_scorecard"),
        }]

    def _generate_alternatives(
        self,
        request_data: Dict[str, Any],
        max_alternatives: int,
    ) -> List[Dict[str, Any]]:
        """Generate alternative scenarios via HiveWhatIfEngine."""
        results = []

        # Original proposal
        try:
            scorecard = self.what_if_engine.evaluate(variable_deltas=None)
            results.append({
                "label": "Original proposal",
                "description": request_data.get("justification", "Proceed as requested"),
                "net_benefit": scorecard.get("net_benefit", request_data.get("net_benefit", 0.0)),
                "scorecard": scorecard,
            })
        except Exception as e:
            logger.warning(f"What-if evaluation failed for original: {e}")

        # Conservative alternative (reduced scope)
        try:
            scorecard = self.what_if_engine.evaluate(
                variable_deltas={"safety_stock_multiplier": 1.2, "demand_change_pct": 0},
            )
            results.append({
                "label": "Conservative",
                "description": "Reduced scope with higher safety stock buffer",
                "net_benefit": scorecard.get("net_benefit", 0.0),
                "scorecard": scorecard,
            })
        except Exception as e:
            logger.warning(f"What-if evaluation failed for conservative: {e}")

        # Aggressive alternative (expanded scope)
        try:
            scorecard = self.what_if_engine.evaluate(
                variable_deltas={"safety_stock_multiplier": 0.8, "demand_change_pct": 5},
            )
            results.append({
                "label": "Aggressive",
                "description": "Expanded scope with tighter inventory targets",
                "net_benefit": scorecard.get("net_benefit", 0.0),
                "scorecard": scorecard,
            })
        except Exception as e:
            logger.warning(f"What-if evaluation failed for aggressive: {e}")

        return sorted(results, key=lambda r: r.get("net_benefit", 0), reverse=True)[:max_alternatives]

    def _build_summary(self, request_data: Dict[str, Any]) -> str:
        """Build a concise summary for the escalation."""
        agent_from = request_data.get("requesting_agent", "unknown")
        agent_to = request_data.get("target_agent", "unknown")
        action = request_data.get("proposed_action", {})
        action_type = action.get("action_type", "unknown action")
        nb = request_data.get("net_benefit", 0.0)

        return (
            f"{agent_from} requests authorization from {agent_to} "
            f"for '{action_type}' (net benefit: {nb:+.2f})"
        )

    def _build_response_options(
        self,
        ranked_alternatives: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build numbered response options for the human."""
        options = []
        for i, alt in enumerate(ranked_alternatives, 1):
            options.append({
                "index": i,
                "label": alt.get("label", f"Option {i}"),
                "description": alt.get("description", ""),
                "decision": "AUTHORIZE",
                "net_benefit": alt.get("net_benefit", 0.0),
                "is_override": False,
            })

        # Always add a deny option
        options.append({
            "index": len(options) + 1,
            "label": "Deny",
            "description": "Reject the request. Agent will use fallback action.",
            "decision": "DENY",
            "net_benefit": 0.0,
            "is_override": True,
        })

        return options

    def _determine_urgency(self, thread: Any) -> str:
        """Determine escalation urgency from thread state."""
        priority = getattr(thread, "priority", None)
        if priority:
            priority_val = priority.value if hasattr(priority, "value") else str(priority)
            if priority_val in ("CRITICAL", "critical"):
                return "critical"
            if priority_val in ("HIGH", "high"):
                return "high"
        # Check if SLA is expired
        if getattr(thread, "is_expired", False):
            return "high"
        return "medium"

    def _determine_reason(self, thread: Any) -> str:
        """Determine why this was escalated."""
        status = getattr(thread, "status", None)
        status_val = status.value if hasattr(status, "value") else str(status)

        if status_val in ("ESCALATED", "escalated"):
            return "Agent explicitly escalated for human review"
        if getattr(thread, "is_expired", False):
            return "SLA timeout — no agent response within deadline"

        nb = getattr(thread, "net_benefit", None)
        bt = getattr(thread, "benefit_threshold", None)
        if nb is not None and bt is not None and bt > 0:
            ratio = nb / bt
            if 0.5 <= ratio <= 2.0:
                return f"Net benefit ({nb:.2f}) near threshold ({bt:.2f}) — human judgment required"

        return "Escalated for human review"

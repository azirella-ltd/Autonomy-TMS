"""
Agentic Authorization Protocol (AAP) — Cross-Functional Decision-Making at Machine Speed.

Implements the three-phase protocol for autonomous agents to evaluate
cross-functional trade-offs and request authorization for actions outside
their authority domain.

Architecture reference: docs/AGENTIC_AUTHORIZATION_PROTOCOL.md

Three Phases:
  1. EVALUATE — Originating agent runs what-if on all options (including cross-authority)
  2. REQUEST  — Send AuthorizationRequest with full Balanced Scorecard to target agent
  3. AUTHORIZE — Target agent checks resource availability and contention, responds

Authority categories per agent:
  - Unilateral:  Execute without asking
  - Requires-Authorization:  Evaluate but need approval
  - Forbidden:   Cannot request

Net Benefit Threshold governance:
  - Well above threshold → auto-resolve
  - Near threshold → human reviews
  - Below threshold → reject
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthorizationDecision(str, Enum):
    """Possible outcomes from the target agent."""
    AUTHORIZE = "authorize"
    DENY = "deny"
    COUNTER_OFFER = "counter_offer"
    ESCALATE = "escalate"          # To human decision-maker
    TIMEOUT = "timeout"            # No response within TTL


class AuthorizationPriority(str, Enum):
    """Request priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ROUTINE = "routine"


class AuthorizationPhase(str, Enum):
    """Protocol phases for tracking."""
    EVALUATE = "evaluate"
    REQUEST = "request"
    AUTHORIZE = "authorize"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class ActionCategory(str, Enum):
    """Authority category for an action."""
    UNILATERAL = "unilateral"
    REQUIRES_AUTHORIZATION = "requires_authorization"
    FORBIDDEN = "forbidden"


class AgentRole(str, Enum):
    """Functional agent roles in the authorization network."""
    SO_ATP = "so_atp"               # Sales Order / ATP Agent
    SUPPLY = "supply"               # Supply Planning Agent
    ALLOCATION = "allocation"       # Allocation Agent
    LOGISTICS = "logistics"         # Logistics Agent
    INVENTORY = "inventory"         # Inventory Agent
    SOP = "sop"                     # S&OP Agent
    PLANT = "plant"                 # Plant / Manufacturing Agent
    QUALITY = "quality"             # Quality Agent
    MAINTENANCE = "maintenance"     # Maintenance Agent
    PROCUREMENT = "procurement"     # Procurement Agent
    SUPPLIER = "supplier"           # Supplier (external) Agent
    CHANNEL = "channel"             # Channel Agent
    DEMAND = "demand"               # Demand Agent
    FINANCE = "finance"             # Finance Agent
    SERVICE = "service"             # Service Agent
    RISK = "risk"                   # Risk Agent


# ---------------------------------------------------------------------------
# Balanced Scorecard
# ---------------------------------------------------------------------------

@dataclass
class ScorecardDelta:
    """A single metric change within the Balanced Scorecard."""
    metric: str                  # e.g. "otif_segment_a"
    quadrant: str                # "financial", "customer", "operational", "strategic"
    baseline: float = 0.0
    projected: float = 0.0
    delta: float = 0.0          # projected - baseline
    weight: float = 1.0         # From Policy Envelope
    direction: int = 1          # +1 = higher is better, -1 = lower is better
    unit: str = ""              # "%", "USD", "days", etc.

    @property
    def weighted_contribution(self) -> float:
        return self.weight * self.delta * self.direction


@dataclass
class BalancedScorecard:
    """Probabilistic Balanced Scorecard produced by the what-if engine."""
    metrics: List[ScorecardDelta] = field(default_factory=list)

    @property
    def net_benefit(self) -> float:
        """Sum of weighted deltas across all metrics."""
        return sum(m.weighted_contribution for m in self.metrics)

    def by_quadrant(self, quadrant: str) -> List[ScorecardDelta]:
        return [m for m in self.metrics if m.quadrant == quadrant]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "net_benefit": round(self.net_benefit, 4),
            "metrics": [
                {
                    "metric": m.metric,
                    "quadrant": m.quadrant,
                    "baseline": m.baseline,
                    "projected": m.projected,
                    "delta": m.delta,
                    "weight": m.weight,
                    "direction": m.direction,
                    "unit": m.unit,
                }
                for m in self.metrics
            ],
        }


# ---------------------------------------------------------------------------
# AuthorizationRequest
# ---------------------------------------------------------------------------

@dataclass
class ProposedAction:
    """The action the requesting agent wants to take."""
    action_type: str             # e.g. "expedite_order", "reallocate_inventory"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FallbackAction:
    """What happens if the request is denied."""
    description: str = ""
    net_benefit: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplementaryAction:
    """Side-action another agent should take if the request is authorized."""
    agent_role: AgentRole
    action_type: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthorizationRequest:
    """A cross-authority request from one agent to another.

    Follows the structure defined in AGENTIC_AUTHORIZATION_PROTOCOL.md §4.3.
    """
    # Identity
    request_id: str = field(default_factory=lambda: f"ar-{uuid.uuid4().hex[:12]}")
    requesting_agent: AgentRole = AgentRole.SO_ATP
    target_agent: AgentRole = AgentRole.LOGISTICS

    # Context
    site_key: str = ""
    priority: AuthorizationPriority = AuthorizationPriority.MEDIUM
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # TTL

    # Action
    proposed_action: ProposedAction = field(default_factory=ProposedAction)
    fallback_action: Optional[FallbackAction] = None
    complementary_actions: List[ComplementaryAction] = field(default_factory=list)

    # Scorecard
    balanced_scorecard: BalancedScorecard = field(default_factory=BalancedScorecard)
    benefit_threshold: float = 0.0  # From Policy Envelope

    # Justification
    justification: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def net_benefit(self) -> float:
        return self.balanced_scorecard.net_benefit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requesting_agent": self.requesting_agent.value,
            "target_agent": self.target_agent.value,
            "site_key": self.site_key,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "proposed_action": {
                "action_type": self.proposed_action.action_type,
                "description": self.proposed_action.description,
                "parameters": self.proposed_action.parameters,
            },
            "net_benefit": round(self.net_benefit, 4),
            "benefit_threshold": self.benefit_threshold,
            "justification": self.justification,
            "scorecard": self.balanced_scorecard.to_dict(),
        }


# ---------------------------------------------------------------------------
# AuthorizationResponse
# ---------------------------------------------------------------------------

@dataclass
class AuthorizationResponse:
    """Response from the target agent to an AuthorizationRequest.

    Follows AGENTIC_AUTHORIZATION_PROTOCOL.md §4.4-4.5.
    """
    request_id: str = ""
    decision: AuthorizationDecision = AuthorizationDecision.DENY
    responding_agent: AgentRole = AgentRole.LOGISTICS
    responded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # If COUNTER_OFFER
    counter_proposal: Optional[ProposedAction] = None
    revised_scorecard: Optional[BalancedScorecard] = None

    # Reasoning
    reason: str = ""
    contention_details: Dict[str, Any] = field(default_factory=dict)

    # Escalation
    escalated_to: Optional[str] = None  # Human or higher agent

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "responding_agent": self.responding_agent.value,
            "responded_at": self.responded_at.isoformat(),
            "reason": self.reason,
        }
        if self.counter_proposal:
            d["counter_proposal"] = {
                "action_type": self.counter_proposal.action_type,
                "description": self.counter_proposal.description,
                "parameters": self.counter_proposal.parameters,
            }
        if self.revised_scorecard:
            d["revised_scorecard"] = self.revised_scorecard.to_dict()
        if self.escalated_to:
            d["escalated_to"] = self.escalated_to
        return d


# ---------------------------------------------------------------------------
# AuthorizationThread — full lifecycle of one negotiation
# ---------------------------------------------------------------------------

@dataclass
class AuthorizationThread:
    """Tracks the full lifecycle of an authorization negotiation.

    EVALUATE → REQUEST → AUTHORIZE/COUNTER/DENY/ESCALATE → RESOLVED

    Each thread maps to one CollaborationScenario DB record for auditing.
    """
    thread_id: str = field(default_factory=lambda: f"at-{uuid.uuid4().hex[:12]}")
    phase: AuthorizationPhase = AuthorizationPhase.EVALUATE
    request: Optional[AuthorizationRequest] = None
    responses: List[AuthorizationResponse] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    # Resolution
    final_decision: Optional[AuthorizationDecision] = None
    resolution_source: str = ""  # "agent", "human", "timeout", "auto"

    # Audit trail
    events: List[Dict[str, Any]] = field(default_factory=list)

    def submit_request(self, request: AuthorizationRequest) -> None:
        """Phase 1→2: Submit the authorization request."""
        self.request = request
        self.phase = AuthorizationPhase.REQUEST
        self.events.append({
            "event": "request_submitted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requesting_agent": request.requesting_agent.value,
            "target_agent": request.target_agent.value,
            "net_benefit": request.net_benefit,
        })

    def add_response(self, response: AuthorizationResponse) -> None:
        """Phase 2→3: Target agent responds."""
        self.responses.append(response)
        self.phase = AuthorizationPhase.AUTHORIZE
        self.events.append({
            "event": "response_received",
            "timestamp": response.responded_at.isoformat(),
            "decision": response.decision.value,
            "reason": response.reason,
        })

        # Auto-resolve on final decisions
        if response.decision in (
            AuthorizationDecision.AUTHORIZE,
            AuthorizationDecision.DENY,
        ):
            self.resolve(response.decision, source="agent")

    def resolve(
        self,
        decision: AuthorizationDecision,
        source: str = "agent",
    ) -> None:
        """Mark thread as resolved."""
        self.final_decision = decision
        self.resolution_source = source
        self.resolved_at = datetime.now(timezone.utc)
        self.phase = AuthorizationPhase.RESOLVED
        self.events.append({
            "event": "resolved",
            "timestamp": self.resolved_at.isoformat(),
            "decision": decision.value,
            "source": source,
        })

    def check_expiry(self) -> bool:
        """Check if the request has expired (no response within TTL)."""
        if self.request and self.request.is_expired and self.phase != AuthorizationPhase.RESOLVED:
            self.resolve(AuthorizationDecision.TIMEOUT, source="timeout")
            self.phase = AuthorizationPhase.EXPIRED
            return True
        return False

    @property
    def is_resolved(self) -> bool:
        return self.phase in (AuthorizationPhase.RESOLVED, AuthorizationPhase.EXPIRED)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.resolved_at and self.created_at:
            return (self.resolved_at - self.created_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "phase": self.phase.value,
            "final_decision": self.final_decision.value if self.final_decision else None,
            "resolution_source": self.resolution_source,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_seconds": self.duration_seconds,
            "request": self.request.to_dict() if self.request else None,
            "responses": [r.to_dict() for r in self.responses],
            "events": self.events,
        }


# ---------------------------------------------------------------------------
# Authority Map — defines what each agent can do unilaterally vs. needs auth
# ---------------------------------------------------------------------------

# Maps AgentRole → dict of action_type → ActionCategory
AUTHORITY_MAP: Dict[AgentRole, Dict[str, ActionCategory]] = {
    AgentRole.SO_ATP: {
        "reallocate_within_tier": ActionCategory.UNILATERAL,
        "partial_fill": ActionCategory.UNILATERAL,
        "substitute_product": ActionCategory.UNILATERAL,
        "request_expedite": ActionCategory.REQUIRES_AUTHORIZATION,
        "cross_tier_allocation": ActionCategory.REQUIRES_AUTHORIZATION,
        "override_priority": ActionCategory.FORBIDDEN,
        "change_policy_envelope": ActionCategory.FORBIDDEN,
    },
    AgentRole.SUPPLY: {
        "adjust_order_timing": ActionCategory.UNILATERAL,
        "split_order": ActionCategory.UNILATERAL,
        "request_make_vs_buy": ActionCategory.REQUIRES_AUTHORIZATION,
        "expedite_po": ActionCategory.REQUIRES_AUTHORIZATION,
        "change_sourcing_rules": ActionCategory.FORBIDDEN,
    },
    AgentRole.ALLOCATION: {
        "fair_share_distribute": ActionCategory.UNILATERAL,
        "priority_heuristic": ActionCategory.UNILATERAL,
        "cross_channel_rebalance": ActionCategory.REQUIRES_AUTHORIZATION,
        "override_allocation_reserve": ActionCategory.FORBIDDEN,
    },
    AgentRole.LOGISTICS: {
        "consolidate_shipments": ActionCategory.UNILATERAL,
        "select_carrier": ActionCategory.UNILATERAL,
        "mode_switch": ActionCategory.REQUIRES_AUTHORIZATION,
        "cross_border_reroute": ActionCategory.REQUIRES_AUTHORIZATION,
    },
    AgentRole.INVENTORY: {
        "adjust_safety_stock_within_band": ActionCategory.UNILATERAL,
        "trigger_cycle_count": ActionCategory.UNILATERAL,
        "cross_dc_transfer": ActionCategory.REQUIRES_AUTHORIZATION,
        "write_off_excess": ActionCategory.REQUIRES_AUTHORIZATION,
    },
    AgentRole.PLANT: {
        "sequence_within_shift": ActionCategory.UNILATERAL,
        "minor_changeover": ActionCategory.UNILATERAL,
        "insert_rush_order": ActionCategory.REQUIRES_AUTHORIZATION,
        "overtime_authorization": ActionCategory.REQUIRES_AUTHORIZATION,
        "shutdown_line": ActionCategory.FORBIDDEN,
    },
    AgentRole.QUALITY: {
        "hold_lot": ActionCategory.UNILATERAL,
        "release_lot": ActionCategory.UNILATERAL,
        "rework_decision": ActionCategory.UNILATERAL,
        "use_as_is_concession": ActionCategory.REQUIRES_AUTHORIZATION,
        "scrap_above_threshold": ActionCategory.REQUIRES_AUTHORIZATION,
    },
    AgentRole.MAINTENANCE: {
        "schedule_pm": ActionCategory.UNILATERAL,
        "defer_pm_within_window": ActionCategory.UNILATERAL,
        "emergency_maintenance": ActionCategory.UNILATERAL,
        "defer_pm_beyond_window": ActionCategory.REQUIRES_AUTHORIZATION,
        "outsource_maintenance": ActionCategory.REQUIRES_AUTHORIZATION,
    },
    AgentRole.PROCUREMENT: {
        "release_blanket_po": ActionCategory.UNILATERAL,
        "spot_buy_within_budget": ActionCategory.UNILATERAL,
        "spot_buy_over_budget": ActionCategory.REQUIRES_AUTHORIZATION,
        "new_supplier_qualification": ActionCategory.REQUIRES_AUTHORIZATION,
        "change_contract_terms": ActionCategory.FORBIDDEN,
    },
    AgentRole.FINANCE: {
        "approve_within_delegation": ActionCategory.UNILATERAL,
        "budget_reallocation": ActionCategory.REQUIRES_AUTHORIZATION,
        "capex_approval": ActionCategory.FORBIDDEN,
    },
    AgentRole.SOP: {
        "adjust_policy_parameters": ActionCategory.UNILATERAL,
        "seasonal_prebuild_authorization": ActionCategory.REQUIRES_AUTHORIZATION,
        "product_rationalization": ActionCategory.REQUIRES_AUTHORIZATION,
    },
}


def get_action_category(
    agent_role: AgentRole,
    action_type: str,
) -> ActionCategory:
    """Look up the authority category for a given agent + action.

    Returns REQUIRES_AUTHORIZATION for unknown actions (safe default).
    """
    role_map = AUTHORITY_MAP.get(agent_role, {})
    return role_map.get(action_type, ActionCategory.REQUIRES_AUTHORIZATION)


def evaluate_auto_resolve(
    request: AuthorizationRequest,
    threshold_margin: float = 0.10,
) -> Optional[AuthorizationDecision]:
    """Check if a request can be auto-resolved based on net benefit threshold.

    Returns:
        AUTHORIZE if net_benefit well above threshold
        DENY if net_benefit well below threshold
        None if human review needed (near threshold)
    """
    nb = request.net_benefit
    bt = request.benefit_threshold

    if nb > bt * (1.0 + threshold_margin):
        return AuthorizationDecision.AUTHORIZE
    if nb < bt * (1.0 - threshold_margin):
        return AuthorizationDecision.DENY
    return None  # Human review zone

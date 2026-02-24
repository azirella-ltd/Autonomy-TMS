"""
Authority Boundaries — Per-agent action classification with target routing.

Extends the AUTHORITY_MAP in authorization_protocol.py with structured
AuthorityBoundary dataclasses that specify:
  - Unilateral actions (execute without asking)
  - Requires-authorization actions with target agent routing
  - Forbidden actions

Used by the authorization service to deterministically route cross-functional
requests to the correct target agent (<500ms, no LLM).

Architecture reference: docs/AGENTIC_AUTHORIZATION_PROTOCOL.md Section 3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Set

from app.services.authorization_protocol import ActionCategory, AgentRole


@dataclass(frozen=True)
class AuthorizationTarget:
    """Routing info for an action that requires authorization."""
    target_agent: AgentRole
    sla_minutes: int = 240  # Default 4-hour SLA
    auto_approve_if_no_contention: bool = False


@dataclass
class AuthorityBoundary:
    """Complete authority boundary definition for one agent role.

    Attributes:
        agent_role: The agent this boundary applies to.
        unilateral: Actions the agent can take without asking.
        requires_authorization: Actions that need approval, mapped to targets.
        forbidden: Actions the agent can never request.
    """
    agent_role: AgentRole
    unilateral: FrozenSet[str] = field(default_factory=frozenset)
    requires_authorization: Dict[str, AuthorizationTarget] = field(default_factory=dict)
    forbidden: FrozenSet[str] = field(default_factory=frozenset)

    def check_action(self, action_type: str) -> ActionCategory:
        """Classify an action for this agent."""
        if action_type in self.unilateral:
            return ActionCategory.UNILATERAL
        if action_type in self.requires_authorization:
            return ActionCategory.REQUIRES_AUTHORIZATION
        if action_type in self.forbidden:
            return ActionCategory.FORBIDDEN
        # Unknown actions default to requires_authorization
        return ActionCategory.REQUIRES_AUTHORIZATION

    def get_target(self, action_type: str) -> Optional[AuthorizationTarget]:
        """Get the authorization target for an action, or None if unilateral/forbidden."""
        return self.requires_authorization.get(action_type)


# ---------------------------------------------------------------------------
# Authority Boundary Definitions
# ---------------------------------------------------------------------------

AUTHORITY_BOUNDARIES: Dict[AgentRole, AuthorityBoundary] = {

    AgentRole.SO_ATP: AuthorityBoundary(
        agent_role=AgentRole.SO_ATP,
        unilateral=frozenset({
            "reallocate_within_tier",
            "partial_fill",
            "substitute_product",
        }),
        requires_authorization={
            "request_expedite": AuthorizationTarget(
                target_agent=AgentRole.LOGISTICS, sla_minutes=60,
            ),
            "cross_tier_allocation": AuthorizationTarget(
                target_agent=AgentRole.ALLOCATION, sla_minutes=120,
            ),
            "request_inventory_transfer": AuthorizationTarget(
                target_agent=AgentRole.INVENTORY, sla_minutes=240,
            ),
        },
        forbidden=frozenset({
            "override_priority",
            "change_policy_envelope",
        }),
    ),

    AgentRole.SUPPLY: AuthorityBoundary(
        agent_role=AgentRole.SUPPLY,
        unilateral=frozenset({
            "adjust_order_timing",
            "split_order",
        }),
        requires_authorization={
            "request_make_vs_buy": AuthorizationTarget(
                target_agent=AgentRole.PLANT, sla_minutes=240,
            ),
            "expedite_po": AuthorizationTarget(
                target_agent=AgentRole.PROCUREMENT, sla_minutes=120,
            ),
            "request_subcontracting": AuthorizationTarget(
                target_agent=AgentRole.PLANT, sla_minutes=240,
            ),
        },
        forbidden=frozenset({
            "change_sourcing_rules",
        }),
    ),

    AgentRole.ALLOCATION: AuthorityBoundary(
        agent_role=AgentRole.ALLOCATION,
        unilateral=frozenset({
            "fair_share_distribute",
            "priority_heuristic",
        }),
        requires_authorization={
            "cross_channel_rebalance": AuthorizationTarget(
                target_agent=AgentRole.CHANNEL, sla_minutes=120,
            ),
            "override_allocation_priority": AuthorizationTarget(
                target_agent=AgentRole.SOP, sla_minutes=240,
            ),
        },
        forbidden=frozenset({
            "override_allocation_reserve",
        }),
    ),

    AgentRole.LOGISTICS: AuthorityBoundary(
        agent_role=AgentRole.LOGISTICS,
        unilateral=frozenset({
            "consolidate_shipments",
            "select_carrier",
        }),
        requires_authorization={
            "mode_switch": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=240,
            ),
            "cross_border_reroute": AuthorizationTarget(
                target_agent=AgentRole.PROCUREMENT, sla_minutes=240,
            ),
            "expedite_shipment": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=60,
                auto_approve_if_no_contention=True,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.INVENTORY: AuthorityBoundary(
        agent_role=AgentRole.INVENTORY,
        unilateral=frozenset({
            "adjust_safety_stock_within_band",
            "trigger_cycle_count",
        }),
        requires_authorization={
            "cross_dc_transfer": AuthorizationTarget(
                target_agent=AgentRole.LOGISTICS, sla_minutes=240,
            ),
            "write_off_excess": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=1440,  # 24h
            ),
            "adjust_safety_stock_beyond_band": AuthorizationTarget(
                target_agent=AgentRole.SOP, sla_minutes=240,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.PLANT: AuthorityBoundary(
        agent_role=AgentRole.PLANT,
        unilateral=frozenset({
            "sequence_within_shift",
            "minor_changeover",
        }),
        requires_authorization={
            "insert_rush_order": AuthorizationTarget(
                target_agent=AgentRole.SO_ATP, sla_minutes=60,
            ),
            "overtime_authorization": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=240,
            ),
            "bom_substitution": AuthorizationTarget(
                target_agent=AgentRole.QUALITY, sla_minutes=120,
            ),
        },
        forbidden=frozenset({
            "shutdown_line",
        }),
    ),

    AgentRole.QUALITY: AuthorityBoundary(
        agent_role=AgentRole.QUALITY,
        unilateral=frozenset({
            "hold_lot",
            "release_lot",
            "rework_decision",
        }),
        requires_authorization={
            "use_as_is_concession": AuthorizationTarget(
                target_agent=AgentRole.SO_ATP, sla_minutes=120,
            ),
            "scrap_above_threshold": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=240,
            ),
            "supplier_quality_escalation": AuthorizationTarget(
                target_agent=AgentRole.PROCUREMENT, sla_minutes=240,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.MAINTENANCE: AuthorityBoundary(
        agent_role=AgentRole.MAINTENANCE,
        unilateral=frozenset({
            "schedule_pm",
            "defer_pm_within_window",
            "emergency_maintenance",
        }),
        requires_authorization={
            "defer_pm_beyond_window": AuthorizationTarget(
                target_agent=AgentRole.PLANT, sla_minutes=240,
            ),
            "outsource_maintenance": AuthorizationTarget(
                target_agent=AgentRole.PROCUREMENT, sla_minutes=1440,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.PROCUREMENT: AuthorityBoundary(
        agent_role=AgentRole.PROCUREMENT,
        unilateral=frozenset({
            "release_blanket_po",
            "spot_buy_within_budget",
        }),
        requires_authorization={
            "spot_buy_over_budget": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=240,
            ),
            "new_supplier_qualification": AuthorizationTarget(
                target_agent=AgentRole.QUALITY, sla_minutes=2880,  # 48h
            ),
            "dual_source_activation": AuthorizationTarget(
                target_agent=AgentRole.SUPPLY, sla_minutes=240,
            ),
        },
        forbidden=frozenset({
            "change_contract_terms",
        }),
    ),

    AgentRole.FINANCE: AuthorityBoundary(
        agent_role=AgentRole.FINANCE,
        unilateral=frozenset({
            "approve_within_delegation",
        }),
        requires_authorization={
            "budget_reallocation": AuthorizationTarget(
                target_agent=AgentRole.SOP, sla_minutes=1440,
            ),
        },
        forbidden=frozenset({
            "capex_approval",
        }),
    ),

    AgentRole.SOP: AuthorityBoundary(
        agent_role=AgentRole.SOP,
        unilateral=frozenset({
            "adjust_policy_parameters",
        }),
        requires_authorization={
            "seasonal_prebuild_authorization": AuthorizationTarget(
                target_agent=AgentRole.FINANCE, sla_minutes=1440,
            ),
            "product_rationalization": AuthorizationTarget(
                target_agent=AgentRole.DEMAND, sla_minutes=2880,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.DEMAND: AuthorityBoundary(
        agent_role=AgentRole.DEMAND,
        unilateral=frozenset({
            "adjust_forecast_within_band",
            "add_consensus_override",
        }),
        requires_authorization={
            "override_statistical_forecast": AuthorizationTarget(
                target_agent=AgentRole.SOP, sla_minutes=240,
            ),
            "new_product_forecast": AuthorizationTarget(
                target_agent=AgentRole.SOP, sla_minutes=1440,
            ),
        },
        forbidden=frozenset(),
    ),

    AgentRole.CHANNEL: AuthorityBoundary(
        agent_role=AgentRole.CHANNEL,
        unilateral=frozenset({
            "adjust_channel_priority",
        }),
        requires_authorization={
            "cross_channel_reallocation": AuthorizationTarget(
                target_agent=AgentRole.ALLOCATION, sla_minutes=120,
            ),
            "promotion_surge_request": AuthorizationTarget(
                target_agent=AgentRole.SUPPLY, sla_minutes=240,
            ),
        },
        forbidden=frozenset(),
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_authority_boundary(agent_role: AgentRole) -> AuthorityBoundary:
    """Get the authority boundary for an agent role.

    Returns a permissive default if the role has no explicit boundary.
    """
    return AUTHORITY_BOUNDARIES.get(
        agent_role,
        AuthorityBoundary(agent_role=agent_role),
    )


def check_action_category(
    agent_role: AgentRole,
    action_type: str,
) -> ActionCategory:
    """Quick lookup: classify an action for an agent."""
    boundary = get_authority_boundary(agent_role)
    return boundary.check_action(action_type)


def get_required_target(
    agent_role: AgentRole,
    action_type: str,
) -> Optional[AuthorizationTarget]:
    """Get the target agent for a requires-authorization action.

    Returns None if the action is unilateral, forbidden, or unknown.
    """
    boundary = get_authority_boundary(agent_role)
    return boundary.get_target(action_type)


def get_all_actions(agent_role: AgentRole) -> Dict[str, ActionCategory]:
    """Get all known actions for an agent with their categories."""
    boundary = get_authority_boundary(agent_role)
    result: Dict[str, ActionCategory] = {}
    for a in boundary.unilateral:
        result[a] = ActionCategory.UNILATERAL
    for a in boundary.requires_authorization:
        result[a] = ActionCategory.REQUIRES_AUTHORIZATION
    for a in boundary.forbidden:
        result[a] = ActionCategory.FORBIDDEN
    return result

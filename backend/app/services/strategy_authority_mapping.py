"""
Strategy Authority Mapping — maps user roles to agent roles, action types
to authority domains, and partitions actions by authority boundary.

Used by ScenarioStrategyService to determine which strategy actions the
user can execute unilaterally vs which require AAP authorization from
another agent's domain.
"""

from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.models.user import DecisionLevelEnum
from app.services.authorization_protocol import AgentRole


# ── Decision Level → Agent Role ──────────────────────────────────────────

DECISION_LEVEL_TO_AGENT: Dict[DecisionLevelEnum, AgentRole] = {
    DecisionLevelEnum.ATP_ANALYST: AgentRole.SO_ATP,
    DecisionLevelEnum.ORDER_TRACKING_ANALYST: AgentRole.SO_ATP,
    DecisionLevelEnum.ORDER_PROMISE_MANAGER: AgentRole.SO_ATP,
    DecisionLevelEnum.MPS_MANAGER: AgentRole.PLANT,
    DecisionLevelEnum.PO_ANALYST: AgentRole.PROCUREMENT,
    DecisionLevelEnum.REBALANCING_ANALYST: AgentRole.INVENTORY,
    DecisionLevelEnum.ALLOCATION_MANAGER: AgentRole.ALLOCATION,
    DecisionLevelEnum.SOP_DIRECTOR: AgentRole.SOP,
    DecisionLevelEnum.SC_VP: AgentRole.SOP,
    DecisionLevelEnum.EXECUTIVE: AgentRole.SOP,
    DecisionLevelEnum.DEMO_ALL: AgentRole.SOP,  # Full authority for demos
}

# Agent roles with broad authority (can authorize across most domains)
BROAD_AUTHORITY_ROLES: FrozenSet[AgentRole] = frozenset({
    AgentRole.SOP,
})


def map_decision_level_to_agent_role(
    decision_level: Optional[DecisionLevelEnum],
) -> AgentRole:
    """Map a user's decision level to the corresponding AAP agent role.

    Users without a decision_level (e.g., TENANT_ADMIN) default to SOP
    (broadest authority) since they have admin-level access.
    """
    if decision_level is None:
        return AgentRole.SOP
    if isinstance(decision_level, str):
        try:
            decision_level = DecisionLevelEnum(decision_level)
        except ValueError:
            return AgentRole.SOP
    return DECISION_LEVEL_TO_AGENT.get(decision_level, AgentRole.SOP)


# ── Action Type → Authority Domain ──────────────────────────────────────

# Maps strategy action types to (authority_action_name, domain_owner_agent_role)
ACTION_TO_DOMAIN: Dict[str, Tuple[str, AgentRole]] = {
    "set_priority": ("reallocate_within_tier", AgentRole.SO_ATP),
    "add_mo": ("insert_rush_order", AgentRole.PLANT),
    "expedite_po": ("expedite_po", AgentRole.PROCUREMENT),
    "transfer": ("cross_dc_transfer", AgentRole.LOGISTICS),
    "adjust_forecast": ("adjust_forecast_within_band", AgentRole.DEMAND),
}


def map_action_type_to_authority(
    action_type: str,
) -> Tuple[str, AgentRole]:
    """Map a strategy action type to its authority action name and domain owner.

    Returns:
        (authority_action_name, domain_owner_agent_role)
    """
    return ACTION_TO_DOMAIN.get(
        action_type,
        (action_type, AgentRole.SOP),  # Unknown actions require SOP approval
    )


# ── Action Partitioning ─────────────────────────────────────────────────

def partition_actions(
    user_agent_role: AgentRole,
    actions: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition strategy actions into unilateral and cross-boundary.

    An action is unilateral if:
    - The user's agent role IS the domain owner, OR
    - The user has broad authority (SOP/Executive), OR
    - The action type is unknown (default to unilateral for flexibility)

    Otherwise the action requires authorization from the domain owner.

    Returns:
        (unilateral_actions, cross_boundary_actions)
        Each cross-boundary action is annotated with 'target_agent_role'.
    """
    unilateral = []
    cross_boundary = []

    # Broad authority roles bypass all checks
    if user_agent_role in BROAD_AUTHORITY_ROLES:
        return actions, []

    for action in actions:
        action_type = action.get("type", "unknown")
        _authority_name, domain_owner = map_action_type_to_authority(action_type)

        if user_agent_role == domain_owner:
            unilateral.append(action)
        else:
            # Annotate with target for AAP thread creation
            annotated = {**action, "_target_agent_role": domain_owner}
            cross_boundary.append(annotated)

    return unilateral, cross_boundary

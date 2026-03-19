"""
Strategy Authority Mapping — maps user roles to agent roles, action types
to authority domains, and partitions actions by authority boundary.

Used by ScenarioStrategyService to determine which strategy actions the
user can execute unilaterally vs which require AAP authorization from
another agent's domain.
"""

from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.models.user import PowellRoleEnum
from app.services.authorization_protocol import AgentRole


# ── Powell Role → Agent Role ─────────────────────────────────────────────

POWELL_TO_AGENT: Dict[PowellRoleEnum, AgentRole] = {
    PowellRoleEnum.ATP_ANALYST: AgentRole.SO_ATP,
    PowellRoleEnum.ORDER_TRACKING_ANALYST: AgentRole.SO_ATP,
    PowellRoleEnum.ORDER_PROMISE_MANAGER: AgentRole.SO_ATP,
    PowellRoleEnum.MPS_MANAGER: AgentRole.PLANT,
    PowellRoleEnum.PO_ANALYST: AgentRole.PROCUREMENT,
    PowellRoleEnum.REBALANCING_ANALYST: AgentRole.INVENTORY,
    PowellRoleEnum.ALLOCATION_MANAGER: AgentRole.ALLOCATION,
    PowellRoleEnum.SOP_DIRECTOR: AgentRole.SOP,
    PowellRoleEnum.SC_VP: AgentRole.SOP,
    PowellRoleEnum.EXECUTIVE: AgentRole.SOP,
    PowellRoleEnum.DEMO_ALL: AgentRole.SOP,  # Full authority for demos
}

# Agent roles with broad authority (can authorize across most domains)
BROAD_AUTHORITY_ROLES: FrozenSet[AgentRole] = frozenset({
    AgentRole.SOP,
})


def map_powell_role_to_agent_role(
    powell_role: Optional[PowellRoleEnum],
) -> AgentRole:
    """Map a user's Powell role to the corresponding AAP agent role.

    Users without a powell_role (e.g., TENANT_ADMIN) default to SOP
    (broadest authority) since they have admin-level access.
    """
    if powell_role is None:
        return AgentRole.SOP
    if isinstance(powell_role, str):
        try:
            powell_role = PowellRoleEnum(powell_role)
        except ValueError:
            return AgentRole.SOP
    return POWELL_TO_AGENT.get(powell_role, AgentRole.SOP)


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

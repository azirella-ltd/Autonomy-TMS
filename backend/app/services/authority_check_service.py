"""
Authority Check Service

Phase 2: Agent Copilot Mode
Validates human overrides of agent recommendations and escalates to
decision proposal workflow when authority thresholds are exceeded.

Integration with Phase 0:
- Uses decision_proposals table for override proposals
- Uses authority_definitions for authority level checks
- Links to business_impact_service for probabilistic impact calculation
"""

import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.participant import Participant

from app.models.decision_proposal import DecisionProposal, ProposalStatus
from app.models.authority_definition import AuthorityDefinition, AuthorityLevel

logger = logging.getLogger(__name__)


@dataclass
class AuthorityCheckResult:
    """Result of authority check for override decision"""
    override_approved: bool  # True if within authority, False if requires approval
    requires_approval: bool  # True if exceeds authority threshold
    authority_level: str  # Participant's authority level (OPERATOR, SUPERVISOR, MANAGER, EXECUTIVE)
    threshold_exceeded: bool  # True if override percentage > threshold
    override_percentage: float  # Percentage difference from agent recommendation
    threshold_percentage: float  # Authority threshold percentage
    decision_proposal_id: Optional[int] = None  # ID of created proposal if escalated


class AuthorityCheckService:
    """
    Service for checking authority levels and creating override proposals.

    Methods:
    - check_override_authority(): Validate if override exceeds authority
    - create_override_proposal(): Create decision proposal for approval
    - calculate_override_threshold(): Get threshold based on authority level
    """

    def __init__(self, db: Session):
        self.db = db

    def check_override_authority(
        self,
        participant: Participant,
        agent_qty: int,
        human_qty: int,
        action_type: str,  # "fulfillment" or "replenishment"
    ) -> AuthorityCheckResult:
        """
        Check if human override of agent recommendation exceeds authority level.

        Args:
            participant: Participant making the decision
            agent_qty: Agent's recommended quantity
            human_qty: Human's chosen quantity
            action_type: Type of decision ("fulfillment" or "replenishment")

        Returns:
            AuthorityCheckResult with approval status and threshold info
        """
        # Get participant's authority level
        # TODO: Link to actual authority_definitions table when Participant model is extended
        # For Phase 2, use simple role-based mapping
        authority_level = self._get_authority_level_from_role(participant)

        # Calculate override percentage
        if agent_qty == 0:
            # Avoid division by zero - if agent recommends 0, any non-zero is 100% override
            override_pct = 100.0 if human_qty > 0 else 0.0
        else:
            override_pct = abs(human_qty - agent_qty) / agent_qty * 100.0

        # Get threshold for authority level
        threshold_pct = self.calculate_override_threshold(authority_level)

        # Check if threshold exceeded
        threshold_exceeded = override_pct > threshold_pct
        requires_approval = threshold_exceeded

        logger.info(
            f"Authority check for participant {participant.id}: "
            f"agent={agent_qty}, human={human_qty}, "
            f"override={override_pct:.1f}%, threshold={threshold_pct:.1f}%, "
            f"requires_approval={requires_approval}"
        )

        # If threshold exceeded, create decision proposal
        decision_proposal_id = None
        if requires_approval:
            try:
                proposal = self.create_override_proposal(
                    participant=participant,
                    agent_qty=agent_qty,
                    human_qty=human_qty,
                    action_type=action_type,
                    override_pct=override_pct,
                )
                decision_proposal_id = proposal.id
                logger.info(f"Created decision proposal {proposal.id} for override")
            except Exception as e:
                logger.error(f"Failed to create decision proposal: {e}", exc_info=True)
                # Don't block the scenario if proposal creation fails
                # Fall back to allowing the override (fail open)
                requires_approval = False

        return AuthorityCheckResult(
            override_approved=(not requires_approval),
            requires_approval=requires_approval,
            authority_level=authority_level.value,
            threshold_exceeded=threshold_exceeded,
            override_percentage=override_pct,
            threshold_percentage=threshold_pct,
            decision_proposal_id=decision_proposal_id,
        )

    def create_override_proposal(
        self,
        participant: Participant,
        agent_qty: int,
        human_qty: int,
        action_type: str,
        override_pct: float,
    ) -> DecisionProposal:
        """
        Create a decision proposal for an override that exceeds authority.

        Args:
            participant: Participant making the decision
            agent_qty: Agent's recommended quantity
            human_qty: Human's chosen quantity
            action_type: Type of decision ("fulfillment" or "replenishment")
            override_pct: Override percentage

        Returns:
            Created DecisionProposal instance
        """
        # Build proposal title and description
        title = f"{action_type.capitalize()} Override: {participant.role} Round {participant.scenario.current_round}"
        description = (
            f"Participant {participant.id} ({participant.role}) wants to override agent recommendation.\n"
            f"Agent recommended: {agent_qty} units\n"
            f"Participant wants: {human_qty} units\n"
            f"Override: {override_pct:.1f}% (exceeds authority threshold)\n"
            f"Action type: {action_type}\n"
        )

        # Create decision proposal
        proposal = DecisionProposal(
            title=title,
            description=description,
            scenario_id=participant.scenario_id,
            created_by=participant.user_id if hasattr(participant, "user_id") else None,
            status=ProposalStatus.PENDING.value,  # Use .value since model field is string
            decision_type=f"override_{action_type}",
            proposal_metadata={
                "participant_id": participant.id,
                "participant_role": participant.role,
                "round_number": participant.scenario.current_round,
                "agent_qty": agent_qty,
                "human_qty": human_qty,
                "override_pct": override_pct,
                "action_type": action_type,
            },
        )

        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)

        logger.info(
            f"Created decision proposal {proposal.id} for {action_type} override: "
            f"agent={agent_qty}, human={human_qty}, override={override_pct:.1f}%"
        )

        return proposal

    def calculate_override_threshold(self, authority_level: AuthorityLevel) -> float:
        """
        Calculate the override threshold percentage for a given authority level.

        Args:
            authority_level: Participant's authority level

        Returns:
            Threshold percentage (e.g., 20.0 means 20% deviation allowed)
        """
        # Authority thresholds (percentage deviation from agent recommendation)
        thresholds = {
            AuthorityLevel.OPERATOR: 20.0,  # Can override up to 20%
            AuthorityLevel.SUPERVISOR: 40.0,  # Can override up to 40%
            AuthorityLevel.MANAGER: 60.0,  # Can override up to 60%
            AuthorityLevel.EXECUTIVE: 100.0,  # Can override any amount
        }

        return thresholds.get(authority_level, 20.0)  # Default to 20% (OPERATOR)

    def _get_authority_level_from_role(self, participant: Participant) -> AuthorityLevel:
        """
        Get authority level from participant role (temporary implementation).

        TODO: Phase 2.5 - Link to actual authority_definitions table
        """
        # Simple role-based mapping for Phase 2
        # In Phase 2.5, this should query authority_definitions table
        role_mapping = {
            "retailer": AuthorityLevel.OPERATOR,
            "wholesaler": AuthorityLevel.SUPERVISOR,
            "distributor": AuthorityLevel.MANAGER,
            "manufacturer": AuthorityLevel.EXECUTIVE,
        }

        return role_mapping.get(participant.role.lower(), AuthorityLevel.OPERATOR)


# Factory function for creating service instances
def get_authority_check_service(db: Session) -> AuthorityCheckService:
    """Factory function to create AuthorityCheckService"""
    return AuthorityCheckService(db)

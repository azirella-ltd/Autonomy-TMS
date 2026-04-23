"""
Decision Proposal Model and Enums

Phase 2: Agent Copilot Mode
Provides ProposalStatus enum and re-exports DecisionProposal from supply_chain_config.

The DecisionProposal model supports two use cases:
1. Strategic scenario-based proposals (network redesign, acquisitions)
2. Operational scenario-based override proposals (copilot mode overrides)
"""

from enum import Enum

# Re-export DecisionProposal from supply_chain_config
from app.models.supply_chain_config import DecisionProposal

__all__ = ["DecisionProposal", "ProposalStatus"]


class ProposalStatus(str, Enum):
    """
    Status of a decision proposal in the approval workflow.

    Lifecycle:
    PENDING -> APPROVED -> EXECUTED
           -> REJECTED
    """
    PENDING = "pending"      # Awaiting approval
    APPROVED = "approved"    # Approved, ready for execution
    REJECTED = "rejected"    # Rejected by approver
    EXECUTED = "executed"    # Approved and executed

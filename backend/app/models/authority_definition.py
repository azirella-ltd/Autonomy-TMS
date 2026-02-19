"""
Authority Definition Model and Enums

Phase 2: Agent Copilot Mode
Provides AuthorityLevel enum and re-exports AuthorityDefinition from supply_chain_config.

Authority levels determine override thresholds for copilot mode:
- OPERATOR: Can override up to 20% from agent recommendation
- SUPERVISOR: Can override up to 40%
- MANAGER: Can override up to 60%
- EXECUTIVE: Can override any amount (100%)
"""

from enum import Enum

# Re-export AuthorityDefinition from supply_chain_config
from app.models.supply_chain_config import AuthorityDefinition

__all__ = ["AuthorityDefinition", "AuthorityLevel"]


class AuthorityLevel(str, Enum):
    """
    Authority levels for override approval thresholds.

    Maps to player roles in Beer Game:
    - OPERATOR: Retailer (front-line, limited authority)
    - SUPERVISOR: Wholesaler (mid-level)
    - MANAGER: Distributor (senior)
    - EXECUTIVE: Manufacturer (full authority)
    """
    OPERATOR = "operator"        # 20% override threshold
    SUPERVISOR = "supervisor"    # 40% override threshold
    MANAGER = "manager"          # 60% override threshold
    EXECUTIVE = "executive"      # 100% override threshold (unlimited)

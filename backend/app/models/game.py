"""Backward compatibility module for game models.

DEPRECATED: This module re-exports models from the new scenario.py module.
All new code should import from app.models.scenario instead.

Terminology mapping (Feb 2026):
- Game -> Scenario
- Player -> Participant
- Round -> Period
"""
# Re-export everything from scenario for backward compatibility
from .scenario import Scenario as Game, ScenarioStatus as GameStatus, Round
from .participant import (
    Participant as Player,
    ParticipantRole as PlayerRole,
    ParticipantType as PlayerType,
    ParticipantStrategy as PlayerStrategy,
    AgentMode,
)
from .supply_chain import (
    ParticipantRound as PlayerRound,
    ParticipantInventory as PlayerInventory,
    ScenarioRound as GameRound,
    RoundPhase,
    UpstreamOrderType,
    Order,
)

__all__ = [
    'Game',
    'GameStatus',
    'Player',
    'PlayerRole',
    'PlayerType',
    'PlayerStrategy',
    'PlayerRound',
    'PlayerInventory',
    'GameRound',
    'Round',
    'RoundPhase',
    'UpstreamOrderType',
    'Order',
    'AgentMode',
]

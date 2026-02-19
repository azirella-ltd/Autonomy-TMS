"""Backward compatibility module for player models.

DEPRECATED: This module re-exports models from the new participant.py module.
All new code should import from app.models.participant instead.

Terminology mapping (Feb 2026):
- Player -> Participant
"""
# Re-export from participant for backward compatibility
from .participant import (
    Participant as Player,
    ParticipantRole as PlayerRole,
    ParticipantType as PlayerType,
    ParticipantStrategy as PlayerStrategy,
    AgentMode,
)

__all__ = [
    'Player',
    'PlayerRole',
    'PlayerType',
    'PlayerStrategy',
    'AgentMode',
]

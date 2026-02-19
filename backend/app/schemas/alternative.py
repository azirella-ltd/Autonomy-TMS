"""Alternative schemas - new terminology for simulation/scenario management.

Terminology update (Feb 2026):
- Game -> Alternative
- GameStatus -> AlternativeStatus
- GameCreate -> AlternativeCreate
- GameState -> AlternativeState
- Player -> Participant (see participant.py)

This module provides the new terminology while maintaining backward compatibility
with the existing game.py schemas.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field

# Import everything from game.py and create aliases
from .game import (
    DemandPatternType,
    DemandPattern,
    GameStatus,
    PlayerRole,
    RolePricing,
    PricingConfig,
    NodePolicy,
    AutonomyLLMToggles,
    AutonomyLLMConfig,
    GameBase,
    GameCreate,
    GameUpdate,
    GameInDBBase,
    Game,
    GameInDB,
    PlayerBase,
    PlayerCreate,
    PlayerUpdate,
    PlayerInDBBase,
    Player,
    PlayerRound as PlayerRoundSchema,
    RoundBase,
    RoundCreate,
    RoundUpdate,
    Round,
    PlayerActionBase,
    PlayerActionCreate,
    PlayerActionUpdate,
    PlayerAction,
    PlayerState,
    GameState,
    OrderCreate,
    OrderResponse,
    PlayerRoundBase,
    PlayerRoundCreate,
    GameRoundBase,
    GameRoundCreate,
    GameRound,
)


# =============================================================================
# New Terminology Aliases
# =============================================================================

# Status enum alias
AlternativeStatus = GameStatus

# Role enum alias (keeping PlayerRole name as it's supply chain specific)
ParticipantRole = PlayerRole

# Base schemas
AlternativeBase = GameBase
AlternativeCreate = GameCreate
AlternativeUpdate = GameUpdate
AlternativeInDBBase = GameInDBBase
Alternative = Game
AlternativeInDB = GameInDB

# Participant schemas (formerly Player)
ParticipantBase = PlayerBase
ParticipantCreate = PlayerCreate
ParticipantUpdate = PlayerUpdate
ParticipantInDBBase = PlayerInDBBase
Participant = Player
ParticipantState = PlayerState

# Round schemas
AlternativeRoundBase = GameRoundBase
AlternativeRoundCreate = GameRoundCreate
AlternativeRound = GameRound

# Participant round schemas
ParticipantRoundBase = PlayerRoundBase
ParticipantRoundCreate = PlayerRoundCreate
ParticipantRound = PlayerRoundSchema

# Action schemas
ParticipantActionBase = PlayerActionBase
ParticipantActionCreate = PlayerActionCreate
ParticipantActionUpdate = PlayerActionUpdate
ParticipantAction = PlayerAction

# State schemas
AlternativeState = GameState


# =============================================================================
# Export all names (both old and new terminology)
# =============================================================================
__all__ = [
    # Enums
    'DemandPatternType',
    'DemandPattern',
    'AlternativeStatus',
    'GameStatus',  # Backward compat
    'ParticipantRole',
    'PlayerRole',  # Backward compat

    # Pricing
    'RolePricing',
    'PricingConfig',
    'NodePolicy',

    # LLM Config
    'AutonomyLLMToggles',
    'AutonomyLLMConfig',

    # Alternative schemas (new terminology)
    'AlternativeBase',
    'AlternativeCreate',
    'AlternativeUpdate',
    'AlternativeInDBBase',
    'Alternative',
    'AlternativeInDB',
    'AlternativeState',
    'AlternativeRoundBase',
    'AlternativeRoundCreate',
    'AlternativeRound',

    # Participant schemas (new terminology)
    'ParticipantBase',
    'ParticipantCreate',
    'ParticipantUpdate',
    'ParticipantInDBBase',
    'Participant',
    'ParticipantState',
    'ParticipantRoundBase',
    'ParticipantRoundCreate',
    'ParticipantRound',
    'ParticipantActionBase',
    'ParticipantActionCreate',
    'ParticipantActionUpdate',
    'ParticipantAction',

    # Game schemas (backward compatibility)
    'GameBase',
    'GameCreate',
    'GameUpdate',
    'GameInDBBase',
    'Game',
    'GameInDB',
    'GameState',
    'GameRoundBase',
    'GameRoundCreate',
    'GameRound',

    # Player schemas (backward compatibility)
    'PlayerBase',
    'PlayerCreate',
    'PlayerUpdate',
    'PlayerInDBBase',
    'Player',
    'PlayerState',
    'PlayerRoundBase',
    'PlayerRoundCreate',

    # Other
    'RoundBase',
    'RoundCreate',
    'RoundUpdate',
    'Round',
    'OrderCreate',
    'OrderResponse',
]

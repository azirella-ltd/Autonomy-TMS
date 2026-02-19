"""
Module to handle SQLAlchemy model relationships and avoid circular imports.

This module sets up all the relationships between models after they have been
imported to avoid circular import issues.
"""

def setup_relationships():
    """Set up all model relationships after all models are imported."""
    from sqlalchemy.orm import relationship
    
    # Import models locally to avoid circular imports
    from .user import User, RefreshToken
    from .game import Game, Round, PlayerAction
    from .player import Player
    
    # User relationships
    User.players = relationship(
        "Player", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    User.refresh_tokens = relationship(
        "RefreshToken", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Game relationships
    Game.players = relationship(
        "Player", 
        back_populates="game", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    Game.rounds = relationship(
        "Round", 
        back_populates="game", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Player relationships
    Player.game = relationship(
        "Game", 
        back_populates="players", 
        lazy="selectin",
        foreign_keys=[Player.game_id]
    )
    Player.user = relationship(
        "User", 
        back_populates="players", 
        lazy="selectin",
        foreign_keys=[Player.user_id]
    )
    Player.actions = relationship(
        "PlayerAction", 
        back_populates="player", 
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="PlayerAction.player_id"
    )
    
    # Round relationships
    Round.game = relationship(
        "Game", 
        back_populates="rounds", 
        lazy="selectin",
        foreign_keys=[Round.game_id]
    )
    Round.player_actions = relationship(
        "PlayerAction", 
        back_populates="round", 
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="PlayerAction.round_id"
    )
    
    # PlayerAction relationships
    PlayerAction.round = relationship(
        "Round", 
        back_populates="player_actions", 
        lazy="selectin",
        foreign_keys=[PlayerAction.round_id]
    )
    PlayerAction.player = relationship(
        "Player", 
        back_populates="actions", 
        lazy="selectin",
        foreign_keys=[PlayerAction.player_id]
    )
    PlayerAction.game = relationship(
        "Game", 
        lazy="selectin",
        foreign_keys=[PlayerAction.game_id]
    )
    
    # RefreshToken relationship (using string reference)
    RefreshToken.user = relationship("User", back_populates="refresh_tokens", lazy="selectin")

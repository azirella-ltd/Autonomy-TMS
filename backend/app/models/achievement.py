"""
Achievement models for gamification/simulation system.

Terminology (Feb 2026):
- player_id -> participant_id
- game_id -> scenario_id
- PlayerStats -> ParticipantStats
- PlayerAchievement -> ParticipantAchievement
- PlayerBadge -> ParticipantBadge
"""
from sqlalchemy import (
    Column, Integer, String, Text, Enum, Boolean, DECIMAL,
    TIMESTAMP, ForeignKey, BigInteger, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class Achievement(Base):
    """Available achievements in the system."""
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    category = Column(
        Enum('progression', 'performance', 'social', 'mastery', 'special', name='achievement_category'),
        nullable=False,
        default='progression'
    )
    criteria = Column(JSON, nullable=False, comment='Achievement unlock criteria')
    points = Column(Integer, nullable=False, default=10)
    icon = Column(String(100), default='trophy')
    rarity = Column(
        Enum('common', 'uncommon', 'rare', 'epic', 'legendary', name='achievement_rarity'),
        nullable=False,
        default='common'
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )

    # Relationships
    participant_achievements = relationship("ParticipantAchievement", back_populates="achievement")
    notifications = relationship("AchievementNotification", back_populates="achievement")

    __table_args__ = (
        Index('idx_category', 'category'),
        Index('idx_rarity', 'rarity'),
        Index('idx_active', 'is_active'),
    )


class ParticipantStats(Base):
    """Aggregate participant (user) statistics across all simulations."""
    __tablename__ = "participant_stats"

    participant_id = Column(Integer, ForeignKey('participants.id', ondelete='CASCADE'), primary_key=True)
    total_scenarios_played = Column(Integer, nullable=False, default=0)
    total_scenarios_won = Column(Integer, nullable=False, default=0)
    total_rounds_played = Column(Integer, nullable=False, default=0)
    total_orders_placed = Column(Integer, nullable=False, default=0)
    total_cost = Column(DECIMAL(15, 2), nullable=False, default=0.00)
    avg_service_level = Column(DECIMAL(5, 2), nullable=True)
    avg_inventory = Column(Integer, nullable=True)
    best_simulation_score = Column(DECIMAL(15, 2), nullable=True)
    worst_simulation_score = Column(DECIMAL(15, 2), nullable=True)
    total_achievements_unlocked = Column(Integer, nullable=False, default=0)
    total_points = Column(Integer, nullable=False, default=0)
    participant_level = Column(Integer, nullable=False, default=1)
    experience_points = Column(Integer, nullable=False, default=0)
    consecutive_wins = Column(Integer, nullable=False, default=0)
    longest_win_streak = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )

    # No relationships - use foreign key access

    __table_args__ = (
        Index('idx_total_points', 'total_points', postgresql_ops={'total_points': 'DESC'}),
        Index('idx_participant_level', 'participant_level', postgresql_ops={'participant_level': 'DESC'}),
        Index('idx_scenarios_played', 'total_scenarios_played', postgresql_ops={'total_scenarios_played': 'DESC'}),
        Index('idx_scenarios_won', 'total_scenarios_won', postgresql_ops={'total_scenarios_won': 'DESC'}),
    )


class ParticipantAchievement(Base):
    """Tracks participant (user) achievement unlocks."""
    __tablename__ = "participant_achievements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    achievement_id = Column(Integer, ForeignKey('achievements.id', ondelete='CASCADE'), nullable=False)
    scenario_id = Column(Integer, ForeignKey('scenarios.id', ondelete='SET NULL'), nullable=True)
    unlocked_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    progress = Column(JSON, nullable=True, comment='Progress data for multi-step achievements')

    # Relationships
    achievement = relationship("Achievement", back_populates="participant_achievements")
    # Scenario relationship removed - use foreign key access

    __table_args__ = (
        Index('unique_participant_achievement', 'participant_id', 'achievement_id', unique=True),
        Index('idx_participant_unlocked', 'participant_id', 'unlocked_at'),
        Index('idx_achievement_count', 'achievement_id'),
        Index('idx_scenario_achievements', 'scenario_id'),
    )


class Leaderboard(Base):
    """Different leaderboard types and configurations."""
    __tablename__ = "leaderboards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    leaderboard_type = Column(
        Enum('global', 'weekly', 'monthly', 'role', 'simulation_mode', name='leaderboard_type'),
        nullable=False,
        default='global'
    )
    metric = Column(
        Enum('total_points', 'win_rate', 'avg_cost', 'service_level', 'efficiency', name='leaderboard_metric'),
        nullable=False,
        default='total_points'
    )
    filter_criteria = Column(JSON, nullable=True, comment='Additional filtering criteria')
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )

    # Relationships
    entries = relationship("LeaderboardEntry", back_populates="leaderboard", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_type_active', 'leaderboard_type', 'is_active'),
    )


class LeaderboardEntry(Base):
    """Individual leaderboard rankings."""
    __tablename__ = "leaderboard_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    leaderboard_id = Column(Integer, ForeignKey('leaderboards.id', ondelete='CASCADE'), nullable=False)
    participant_id = Column(Integer, ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    rank = Column(Integer, nullable=False)
    score = Column(DECIMAL(15, 2), nullable=False)
    entry_metadata = Column('metadata', JSON, nullable=True, comment='Additional data')
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )

    # Relationships
    leaderboard = relationship("Leaderboard", back_populates="entries")
    # Participant relationship removed - use foreign key access

    __table_args__ = (
        Index('unique_leaderboard_participant', 'leaderboard_id', 'participant_id', unique=True),
        Index('idx_leaderboard_rank', 'leaderboard_id', 'rank'),
        Index('idx_participant_leaderboards', 'participant_id'),
    )


class ParticipantBadge(Base):
    """Special badges earned by participants (users)."""
    __tablename__ = "participant_badges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    badge_name = Column(String(255), nullable=False)
    badge_description = Column(Text, nullable=True)
    badge_icon = Column(String(100), default='badge')
    earned_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    expires_at = Column(TIMESTAMP, nullable=True, comment='NULL = permanent badge')
    is_displayed = Column(Boolean, nullable=False, default=True)

    # No relationships - use foreign key access

    __table_args__ = (
        Index('idx_participant_badges', 'participant_id', 'is_displayed'),
        Index('idx_active_badges', 'participant_id', 'expires_at'),
    )


class AchievementNotification(Base):
    """Queue of achievement notifications for participants (users)."""
    __tablename__ = "achievement_notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    achievement_id = Column(Integer, ForeignKey('achievements.id', ondelete='CASCADE'), nullable=False)
    notification_type = Column(
        Enum('unlock', 'progress', 'milestone', name='notification_type'),
        nullable=False,
        default='unlock'
    )
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    is_shown = Column(Boolean, nullable=False, default=False, comment='Whether displayed in UI')
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    read_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    achievement = relationship("Achievement", back_populates="notifications")
    # Participant relationship removed - use foreign key access

    __table_args__ = (
        Index('idx_participant_unread', 'participant_id', 'is_read', 'created_at'),
        Index('idx_participant_unshown', 'participant_id', 'is_shown', 'created_at'),
    )


# =============================================================================
# Backward Compatibility Aliases (DEPRECATED - will be removed in future)
# =============================================================================
# These aliases allow existing code to continue working during migration.
# All new code should use the new names.

PlayerStats = ParticipantStats
PlayerAchievement = ParticipantAchievement
PlayerBadge = ParticipantBadge

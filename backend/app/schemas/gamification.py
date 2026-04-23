"""
Pydantic schemas for gamification system.

Terminology (Feb 2026):
- Player -> ScenarioUser (in DB/code), User (in UI)
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class AchievementCategory(str, Enum):
    """Achievement categories."""
    PROGRESSION = "progression"
    PERFORMANCE = "performance"
    SOCIAL = "social"
    MASTERY = "mastery"
    SPECIAL = "special"


class AchievementRarity(str, Enum):
    """Achievement rarity levels."""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class LeaderboardType(str, Enum):
    """Leaderboard types."""
    GLOBAL = "global"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ROLE = "role"
    GAME_MODE = "game_mode"


class LeaderboardMetric(str, Enum):
    """Leaderboard ranking metrics."""
    TOTAL_POINTS = "total_points"
    WIN_RATE = "win_rate"
    AVG_COST = "avg_cost"
    SERVICE_LEVEL = "service_level"
    EFFICIENCY = "efficiency"


class NotificationType(str, Enum):
    """Achievement notification types."""
    UNLOCK = "unlock"
    PROGRESS = "progress"
    MILESTONE = "milestone"


# ============================================================================
# ACHIEVEMENT SCHEMAS
# ============================================================================

class AchievementBase(BaseModel):
    """Base achievement schema."""
    name: str = Field(..., max_length=255)
    description: str
    category: AchievementCategory = AchievementCategory.PROGRESSION
    criteria: Dict[str, Any]
    points: int = 10
    icon: str = "trophy"
    rarity: AchievementRarity = AchievementRarity.COMMON
    is_active: bool = True


class AchievementCreate(AchievementBase):
    """Schema for creating an achievement."""
    pass


class AchievementUpdate(BaseModel):
    """Schema for updating an achievement."""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[AchievementCategory] = None
    criteria: Optional[Dict[str, Any]] = None
    points: Optional[int] = None
    icon: Optional[str] = None
    rarity: Optional[AchievementRarity] = None
    is_active: Optional[bool] = None


class Achievement(AchievementBase):
    """Full achievement schema with ID and timestamps."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SCENARIO USER STATS SCHEMAS
# ============================================================================

class ScenarioUserStatsBase(BaseModel):
    """Base scenario user stats schema."""
    total_scenarios_played: int = 0
    total_scenarios_won: int = 0
    total_rounds_played: int = 0
    total_orders_placed: int = 0
    total_cost: float = 0.0
    avg_service_level: Optional[float] = None
    avg_inventory: Optional[int] = None
    best_scenario_score: Optional[float] = None
    worst_scenario_score: Optional[float] = None
    total_achievements_unlocked: int = 0
    total_points: int = 0
    scenario_user_level: int = 1
    experience_points: int = 0
    consecutive_wins: int = 0
    longest_win_streak: int = 0


class ScenarioUserStatsCreate(ScenarioUserStatsBase):
    """Schema for creating scenario user stats."""
    scenario_user_id: int


class ScenarioUserStatsUpdate(BaseModel):
    """Schema for updating scenario user stats."""
    total_scenarios_played: Optional[int] = None
    total_scenarios_won: Optional[int] = None
    total_rounds_played: Optional[int] = None
    total_orders_placed: Optional[int] = None
    total_cost: Optional[float] = None
    avg_service_level: Optional[float] = None
    avg_inventory: Optional[int] = None
    best_scenario_score: Optional[float] = None
    worst_scenario_score: Optional[float] = None
    consecutive_wins: Optional[int] = None
    longest_win_streak: Optional[int] = None


class ScenarioUserStats(ScenarioUserStatsBase):
    """Full scenario user stats with timestamps."""
    scenario_user_id: int
    created_at: datetime
    updated_at: datetime
    win_rate: Optional[float] = None  # Computed field

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SCENARIO USER ACHIEVEMENT SCHEMAS
# ============================================================================

class ScenarioUserAchievementBase(BaseModel):
    """Base scenario user achievement schema."""
    scenario_user_id: int
    achievement_id: int
    scenario_id: Optional[int] = None
    progress: Optional[Dict[str, Any]] = None


class ScenarioUserAchievementCreate(ScenarioUserAchievementBase):
    """Schema for creating scenario user achievement."""
    pass


class ScenarioUserAchievement(ScenarioUserAchievementBase):
    """Full scenario user achievement with unlock data."""
    id: int
    unlocked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScenarioUserAchievementWithDetails(ScenarioUserAchievement):
    """Scenario user achievement with full achievement details."""
    achievement: Achievement

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# LEADERBOARD SCHEMAS
# ============================================================================

class LeaderboardBase(BaseModel):
    """Base leaderboard schema."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    leaderboard_type: LeaderboardType = LeaderboardType.GLOBAL
    metric: LeaderboardMetric = LeaderboardMetric.TOTAL_POINTS
    filter_criteria: Optional[Dict[str, Any]] = None
    is_active: bool = True


class LeaderboardCreate(LeaderboardBase):
    """Schema for creating a leaderboard."""
    pass


class LeaderboardUpdate(BaseModel):
    """Schema for updating a leaderboard."""
    name: Optional[str] = None
    description: Optional[str] = None
    filter_criteria: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class Leaderboard(LeaderboardBase):
    """Full leaderboard schema."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# LEADERBOARD ENTRY SCHEMAS
# ============================================================================

class LeaderboardEntryBase(BaseModel):
    """Base leaderboard entry schema."""
    leaderboard_id: int
    scenario_user_id: int
    rank: int
    score: float
    metadata: Optional[Dict[str, Any]] = None


class LeaderboardEntryCreate(LeaderboardEntryBase):
    """Schema for creating leaderboard entry."""
    pass


class LeaderboardEntry(LeaderboardEntryBase):
    """Full leaderboard entry."""
    id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeaderboardEntryWithScenarioUser(LeaderboardEntry):
    """Leaderboard entry with scenario user details."""
    scenario_user_name: Optional[str] = None
    scenario_user_role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# BADGE SCHEMAS
# ============================================================================

class ScenarioUserBadgeBase(BaseModel):
    """Base scenario user badge schema."""
    scenario_user_id: int
    badge_name: str = Field(..., max_length=255)
    badge_description: Optional[str] = None
    badge_icon: str = "badge"
    expires_at: Optional[datetime] = None
    is_displayed: bool = True


class ScenarioUserBadgeCreate(ScenarioUserBadgeBase):
    """Schema for creating scenario user badge."""
    pass


class ScenarioUserBadge(ScenarioUserBadgeBase):
    """Full scenario user badge."""
    id: int
    earned_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# NOTIFICATION SCHEMAS
# ============================================================================

class AchievementNotificationBase(BaseModel):
    """Base achievement notification schema."""
    scenario_user_id: int
    achievement_id: int
    notification_type: NotificationType = NotificationType.UNLOCK
    message: str


class AchievementNotificationCreate(AchievementNotificationBase):
    """Schema for creating notification."""
    pass


class AchievementNotification(AchievementNotificationBase):
    """Full achievement notification."""
    id: int
    is_read: bool = False
    is_shown: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AchievementNotificationWithDetails(AchievementNotification):
    """Notification with full achievement details."""
    achievement: Achievement

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class AchievementCheckResponse(BaseModel):
    """Response from checking achievements."""
    newly_unlocked: List[Achievement] = []
    progress_updates: List[Dict[str, Any]] = []
    total_points_earned: int = 0
    level_up: bool = False
    new_level: Optional[int] = None


class ScenarioUserProgressResponse(BaseModel):
    """Scenario user progress and statistics response."""
    stats: ScenarioUserStats
    achievements: List[ScenarioUserAchievementWithDetails]
    badges: List[ScenarioUserBadge]
    notifications: List[AchievementNotificationWithDetails]
    next_level_progress: float  # Percentage to next level


class LeaderboardResponse(BaseModel):
    """Leaderboard with entries."""
    leaderboard: Leaderboard
    entries: List[LeaderboardEntryWithScenarioUser]
    total_entries: int
    scenario_user_rank: Optional[int] = None  # Requesting user's rank
    scenario_user_entry: Optional[LeaderboardEntryWithScenarioUser] = None


# =============================================================================
# Backward Compatibility Aliases (DEPRECATED - will be removed in future)
# =============================================================================


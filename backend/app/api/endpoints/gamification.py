"""
Gamification API endpoints - Achievements, leaderboards, scenario_user stats.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User, UserTypeEnum
from app.services.gamification_service import get_gamification_service
from app.schemas.gamification import (
    Achievement, AchievementCreate, AchievementUpdate,
    ScenarioUserStats, ScenarioUserStatsUpdate,
    ScenarioUserProgressResponse, AchievementCheckResponse,
    Leaderboard, LeaderboardCreate, LeaderboardUpdate, LeaderboardResponse,
    ScenarioUserBadge, AchievementNotification
)

router = APIRouter()


# ============================================================================
# PLAYER STATS ENDPOINTS
# ============================================================================

@router.get("/scenario_users/{scenario_user_id}/stats", response_model=ScenarioUserStats)
async def get_scenario_user_stats(
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scenario_user statistics."""
    service = get_gamification_service(db)
    stats = await service.get_or_create_scenario_user_stats(scenario_user_id)
    return stats


@router.get("/scenario_users/{scenario_user_id}/progress", response_model=ScenarioUserProgressResponse)
async def get_player_progress(
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete scenario_user progress including stats, achievements, badges."""
    service = get_gamification_service(db)
    progress = await service.get_player_progress(scenario_user_id)

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ScenarioUser not found"
        )

    return progress


@router.post("/scenario_users/{scenario_user_id}/scenarios/{scenario_id}/complete", response_model=ScenarioUserStats)
async def update_stats_after_scenario(
    scenario_user_id: int,
    scenario_id: int,
    won: bool = Query(..., description="Whether scenario_user won the scenario"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update scenario_user stats after scenario completion."""
    service = get_gamification_service(db)
    stats = await service.update_scenario_user_stats_after_game(scenario_user_id, scenario_id, won)
    return stats


# ============================================================================
# ACHIEVEMENT ENDPOINTS
# ============================================================================

@router.get("/achievements", response_model=List[Achievement])
async def get_all_achievements(
    active_only: bool = Query(True, description="Only return active achievements"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all available achievements."""
    from sqlalchemy import select
    from app.models.achievement import Achievement as AchievementModel

    query = select(AchievementModel)
    if active_only:
        query = query.where(AchievementModel.is_active == True)

    result = await db.execute(query)
    achievements = result.scalars().all()
    return achievements


@router.get("/achievements/{achievement_id}", response_model=Achievement)
async def get_achievement(
    achievement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific achievement."""
    from sqlalchemy import select
    from app.models.achievement import Achievement as AchievementModel

    result = await db.execute(
        select(AchievementModel).where(AchievementModel.id == achievement_id)
    )
    achievement = result.scalar_one_or_none()

    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found"
        )

    return achievement


@router.post("/achievements", response_model=Achievement, status_code=status.HTTP_201_CREATED)
async def create_achievement(
    achievement: AchievementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new achievement (admin only)."""
    # Check if user is admin
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create achievements"
        )

    from app.models.achievement import Achievement as AchievementModel

    new_achievement = AchievementModel(**achievement.dict())
    db.add(new_achievement)
    await db.commit()
    await db.refresh(new_achievement)

    return new_achievement


@router.patch("/achievements/{achievement_id}", response_model=Achievement)
async def update_achievement(
    achievement_id: int,
    achievement: AchievementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an achievement (admin only)."""
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update achievements"
        )

    from sqlalchemy import select, update
    from app.models.achievement import Achievement as AchievementModel

    result = await db.execute(
        select(AchievementModel).where(AchievementModel.id == achievement_id)
    )
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found"
        )

    update_data = achievement.dict(exclude_unset=True)
    await db.execute(
        update(AchievementModel)
        .where(AchievementModel.id == achievement_id)
        .values(**update_data)
    )
    await db.commit()

    # Fetch updated achievement
    result = await db.execute(
        select(AchievementModel).where(AchievementModel.id == achievement_id)
    )
    return result.scalar_one()


@router.post("/scenario_users/{scenario_user_id}/check-achievements", response_model=AchievementCheckResponse)
async def check_player_achievements(
    scenario_user_id: int,
    scenario_id: Optional[int] = Query(None, description="Scenario ID to check achievements for"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check and unlock achievements for a scenario_user."""
    service = get_gamification_service(db)
    result = await service.check_achievements(scenario_user_id, scenario_id)
    return result


@router.get("/scenario_users/{scenario_user_id}/achievements", response_model=List[dict])
async def get_player_achievements(
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all achievements unlocked by a scenario_user."""
    from sqlalchemy import select
    from app.models.achievement import ScenarioUserAchievement, Achievement as AchievementModel

    result = await db.execute(
        select(ScenarioUserAchievement, AchievementModel)
        .join(AchievementModel)
        .where(ScenarioUserAchievement.scenario_user_id == scenario_user_id)
        .order_by(ScenarioUserAchievement.unlocked_at.desc())
    )

    achievements = []
    for pa, ach in result.all():
        achievements.append({
            'id': pa.id,
            'scenario_user_id': pa.scenario_user_id,
            'achievement_id': pa.achievement_id,
            'scenario_id': pa.scenario_id,
            'unlocked_at': pa.unlocked_at,
            'progress': pa.progress,
            'achievement': {
                'id': ach.id,
                'name': ach.name,
                'description': ach.description,
                'category': ach.category,
                'points': ach.points,
                'icon': ach.icon,
                'rarity': ach.rarity
            }
        })

    return achievements


# ============================================================================
# LEADERBOARD ENDPOINTS
# ============================================================================

@router.get("/leaderboards", response_model=List[Leaderboard])
async def get_all_leaderboards(
    active_only: bool = Query(True, description="Only return active leaderboards"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all leaderboards."""
    service = get_gamification_service(db)
    leaderboards = await service.get_all_leaderboards(active_only)
    return leaderboards


@router.get("/leaderboards/{leaderboard_id}", response_model=LeaderboardResponse)
async def get_leaderboard(
    leaderboard_id: int,
    limit: int = Query(50, ge=1, le=500, description="Number of entries to return"),
    scenario_user_id: Optional[int] = Query(None, description="ScenarioUser ID to highlight"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get leaderboard with entries."""
    service = get_gamification_service(db)
    leaderboard = await service.get_leaderboard(leaderboard_id, limit, scenario_user_id)

    if not leaderboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leaderboard not found"
        )

    return leaderboard


@router.post("/leaderboards", response_model=Leaderboard, status_code=status.HTTP_201_CREATED)
async def create_leaderboard(
    leaderboard: LeaderboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new leaderboard (admin only)."""
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create leaderboards"
        )

    from app.models.achievement import Leaderboard as LeaderboardModel

    new_leaderboard = LeaderboardModel(**leaderboard.dict())
    db.add(new_leaderboard)
    await db.commit()
    await db.refresh(new_leaderboard)

    return new_leaderboard


@router.post("/leaderboards/{leaderboard_id}/update", status_code=status.HTTP_204_NO_CONTENT)
async def update_leaderboard_rankings(
    leaderboard_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Recalculate leaderboard rankings (admin only)."""
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update leaderboard rankings"
        )

    service = get_gamification_service(db)
    await service.update_leaderboard(leaderboard_id)


# ============================================================================
# NOTIFICATION ENDPOINTS
# ============================================================================

@router.get("/scenario_users/{scenario_user_id}/notifications", response_model=List[AchievementNotification])
async def get_player_notifications(
    scenario_user_id: int,
    limit: int = Query(10, ge=1, le=100, description="Number of notifications to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get unread achievement notifications for a scenario_user."""
    service = get_gamification_service(db)
    notifications = await service.get_unread_notifications(scenario_user_id, limit)
    return notifications


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read."""
    service = get_gamification_service(db)
    await service.mark_notification_read(notification_id)


@router.post("/notifications/{notification_id}/shown", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_shown(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as shown in UI."""
    service = get_gamification_service(db)
    await service.mark_notification_shown(notification_id)


# ============================================================================
# BADGE ENDPOINTS
# ============================================================================

@router.get("/scenario_users/{scenario_user_id}/badges", response_model=List[ScenarioUserBadge])
async def get_player_badges(
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all badges earned by a scenario_user."""
    from sqlalchemy import select
    from app.models.achievement import ScenarioUserBadge as ScenarioUserBadgeModel

    result = await db.execute(
        select(ScenarioUserBadgeModel)
        .where(ScenarioUserBadgeModel.scenario_user_id == scenario_user_id)
        .order_by(ScenarioUserBadgeModel.earned_at.desc())
    )
    badges = result.scalars().all()
    return badges

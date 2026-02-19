"""
Gamification API endpoints - Achievements, leaderboards, player stats.
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
    PlayerStats, PlayerStatsUpdate,
    PlayerProgressResponse, AchievementCheckResponse,
    Leaderboard, LeaderboardCreate, LeaderboardUpdate, LeaderboardResponse,
    PlayerBadge, AchievementNotification
)

router = APIRouter()


# ============================================================================
# PLAYER STATS ENDPOINTS
# ============================================================================

@router.get("/players/{player_id}/stats", response_model=PlayerStats)
async def get_player_stats(
    player_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get player statistics."""
    service = get_gamification_service(db)
    stats = await service.get_or_create_player_stats(player_id)
    return stats


@router.get("/players/{player_id}/progress", response_model=PlayerProgressResponse)
async def get_player_progress(
    player_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete player progress including stats, achievements, badges."""
    service = get_gamification_service(db)
    progress = await service.get_player_progress(player_id)

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found"
        )

    return progress


@router.post("/players/{player_id}/scenarios/{scenario_id}/complete", response_model=PlayerStats)
async def update_stats_after_game(
    player_id: int,
    scenario_id: int,
    won: bool = Query(..., description="Whether player won the game"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update player stats after game completion."""
    service = get_gamification_service(db)
    stats = await service.update_player_stats_after_game(player_id, game_id, won)
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
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN):
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
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN):
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


@router.post("/players/{player_id}/check-achievements", response_model=AchievementCheckResponse)
async def check_player_achievements(
    player_id: int,
    game_id: Optional[int] = Query(None, description="Game ID to check achievements for"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check and unlock achievements for a player."""
    service = get_gamification_service(db)
    result = await service.check_achievements(player_id, game_id)
    return result


@router.get("/players/{player_id}/achievements", response_model=List[dict])
async def get_player_achievements(
    player_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all achievements unlocked by a player."""
    from sqlalchemy import select
    from app.models.achievement import PlayerAchievement, Achievement as AchievementModel

    result = await db.execute(
        select(PlayerAchievement, AchievementModel)
        .join(AchievementModel)
        .where(PlayerAchievement.player_id == player_id)
        .order_by(PlayerAchievement.unlocked_at.desc())
    )

    achievements = []
    for pa, ach in result.all():
        achievements.append({
            'id': pa.id,
            'player_id': pa.player_id,
            'achievement_id': pa.achievement_id,
            'game_id': pa.game_id,
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
    player_id: Optional[int] = Query(None, description="Player ID to highlight"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get leaderboard with entries."""
    service = get_gamification_service(db)
    leaderboard = await service.get_leaderboard(leaderboard_id, limit, player_id)

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
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN):
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
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update leaderboard rankings"
        )

    service = get_gamification_service(db)
    await service.update_leaderboard(leaderboard_id)


# ============================================================================
# NOTIFICATION ENDPOINTS
# ============================================================================

@router.get("/players/{player_id}/notifications", response_model=List[AchievementNotification])
async def get_player_notifications(
    player_id: int,
    limit: int = Query(10, ge=1, le=100, description="Number of notifications to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get unread achievement notifications for a player."""
    service = get_gamification_service(db)
    notifications = await service.get_unread_notifications(player_id, limit)
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

@router.get("/players/{player_id}/badges", response_model=List[PlayerBadge])
async def get_player_badges(
    player_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all badges earned by a player."""
    from sqlalchemy import select
    from app.models.achievement import PlayerBadge as PlayerBadgeModel

    result = await db.execute(
        select(PlayerBadgeModel)
        .where(PlayerBadgeModel.player_id == player_id)
        .order_by(PlayerBadgeModel.earned_at.desc())
    )
    badges = result.scalars().all()
    return badges

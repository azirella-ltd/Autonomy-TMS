"""
Gamification Service - Achievement system, player stats, leaderboards.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, desc, text
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import math

from app.models.achievement import (
    Achievement, PlayerStats, PlayerAchievement, Leaderboard,
    LeaderboardEntry, PlayerBadge, AchievementNotification
)
from app.models.participant import Participant
from app.models.scenario import Scenario, Round as ScenarioRound
from app.models.supply_chain import ParticipantRound

# Aliases for backwards compatibility
Player = Participant
Game = Scenario
GameRound = ScenarioRound
PlayerRound = ParticipantRound
from app.schemas.gamification import (
    AchievementCheckResponse, PlayerProgressResponse,
    LeaderboardResponse, LeaderboardEntryWithPlayer
)


class GamificationService:
    """Service for managing gamification features."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.points_per_level = 10  # Level = floor(sqrt(points / 10)) + 1

    # ========================================================================
    # PLAYER STATS MANAGEMENT
    # ========================================================================

    async def get_or_create_player_stats(self, player_id: int) -> PlayerStats:
        """Get player stats, creating if doesn't exist."""
        result = await self.db.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            stats = PlayerStats(player_id=player_id)
            self.db.add(stats)
            await self.db.commit()
            await self.db.refresh(stats)

        return stats

    async def update_player_stats_after_game(
        self,
        player_id: int,
        game_id: int,
        won: bool
    ) -> PlayerStats:
        """Update player stats after game completion."""
        stats = await self.get_or_create_player_stats(player_id)

        # Get game data
        game_result = await self.db.execute(
            select(Game).where(Game.id == game_id)
        )
        game = game_result.scalar_one_or_none()

        if not game:
            return stats

        # Get player's game performance
        player_rounds_result = await self.db.execute(
            select(PlayerRound)
            .where(and_(
                PlayerRound.game_id == game_id,
                PlayerRound.player_id == player_id
            ))
        )
        player_rounds = player_rounds_result.scalars().all()

        if not player_rounds:
            return stats

        # Calculate metrics
        total_cost = sum(pr.round_cost for pr in player_rounds if pr.round_cost)
        total_rounds = len(player_rounds)
        avg_inventory = sum(pr.inventory for pr in player_rounds) / total_rounds if total_rounds > 0 else 0
        service_levels = [pr.service_level for pr in player_rounds if pr.service_level is not None]
        avg_service_level = sum(service_levels) / len(service_levels) if service_levels else None

        # Update stats
        stats.total_games_played += 1
        stats.total_games_won += 1 if won else 0
        stats.total_rounds_played += total_rounds
        stats.total_orders_placed += total_rounds
        stats.total_cost += float(total_cost)

        # Update averages
        stats.avg_inventory = int(
            ((stats.avg_inventory or 0) * (stats.total_games_played - 1) + avg_inventory) / stats.total_games_played
        )
        if avg_service_level is not None:
            current_avg = stats.avg_service_level or 0
            stats.avg_service_level = float(
                (current_avg * (stats.total_games_played - 1) + avg_service_level) / stats.total_games_played
            )

        # Update best/worst scores
        if stats.best_game_score is None or total_cost < stats.best_game_score:
            stats.best_game_score = float(total_cost)
        if stats.worst_game_score is None or total_cost > stats.worst_game_score:
            stats.worst_game_score = float(total_cost)

        # Update win streak
        if won:
            stats.consecutive_wins += 1
            if stats.consecutive_wins > stats.longest_win_streak:
                stats.longest_win_streak = stats.consecutive_wins
        else:
            stats.consecutive_wins = 0

        await self.db.commit()
        await self.db.refresh(stats)

        return stats

    def calculate_player_level(self, total_points: int) -> int:
        """Calculate player level from total points."""
        return int(math.floor(math.sqrt(total_points / self.points_per_level))) + 1

    def points_for_next_level(self, current_level: int) -> int:
        """Calculate points needed for next level."""
        return ((current_level) ** 2) * self.points_per_level

    async def get_player_progress(self, player_id: int) -> Optional[PlayerProgressResponse]:
        """Get complete player progress including stats, achievements, badges."""
        stats = await self.get_or_create_player_stats(player_id)

        # Get unlocked achievements with details
        achievements_result = await self.db.execute(
            select(PlayerAchievement, Achievement)
            .join(Achievement)
            .where(PlayerAchievement.player_id == player_id)
            .order_by(PlayerAchievement.unlocked_at.desc())
        )
        achievements = []
        for pa, ach in achievements_result.all():
            achievements.append({
                **pa.__dict__,
                'achievement': ach
            })

        # Get badges
        badges_result = await self.db.execute(
            select(PlayerBadge)
            .where(PlayerBadge.player_id == player_id)
            .order_by(PlayerBadge.earned_at.desc())
        )
        badges = badges_result.scalars().all()

        # Get unread notifications
        notifications_result = await self.db.execute(
            select(AchievementNotification, Achievement)
            .join(Achievement)
            .where(and_(
                AchievementNotification.player_id == player_id,
                AchievementNotification.is_read == False
            ))
            .order_by(AchievementNotification.created_at.desc())
            .limit(10)
        )
        notifications = []
        for notif, ach in notifications_result.all():
            notifications.append({
                **notif.__dict__,
                'achievement': ach
            })

        # Calculate progress to next level
        current_level = stats.player_level
        next_level_points = self.points_for_next_level(current_level)
        current_level_points = self.points_for_next_level(current_level - 1) if current_level > 1 else 0
        progress = (
            (stats.total_points - current_level_points) /
            (next_level_points - current_level_points) * 100
        )

        return {
            'stats': stats,
            'achievements': achievements,
            'badges': badges,
            'notifications': notifications,
            'next_level_progress': min(progress, 100.0)
        }

    # ========================================================================
    # ACHIEVEMENT CHECKING
    # ========================================================================

    async def check_achievements(
        self,
        player_id: int,
        game_id: Optional[int] = None
    ) -> AchievementCheckResponse:
        """Check and unlock achievements for a player."""
        stats = await self.get_or_create_player_stats(player_id)
        old_level = stats.player_level

        # Get all active achievements
        achievements_result = await self.db.execute(
            select(Achievement).where(Achievement.is_active == True)
        )
        all_achievements = achievements_result.scalars().all()

        # Get already unlocked achievements
        unlocked_result = await self.db.execute(
            select(PlayerAchievement.achievement_id)
            .where(PlayerAchievement.player_id == player_id)
        )
        unlocked_ids = {row[0] for row in unlocked_result.all()}

        newly_unlocked = []
        total_points_earned = 0

        # Check each achievement
        for achievement in all_achievements:
            if achievement.id in unlocked_ids:
                continue  # Already unlocked

            if await self._check_criteria(player_id, game_id, stats, achievement.criteria):
                # Unlock achievement
                player_achievement = PlayerAchievement(
                    player_id=player_id,
                    achievement_id=achievement.id,
                    game_id=game_id
                )
                self.db.add(player_achievement)
                newly_unlocked.append(achievement)
                total_points_earned += achievement.points

        if newly_unlocked:
            await self.db.commit()

        # Check for level up
        new_level = stats.player_level
        level_up = new_level > old_level

        return AchievementCheckResponse(
            newly_unlocked=newly_unlocked,
            progress_updates=[],
            total_points_earned=total_points_earned,
            level_up=level_up,
            new_level=new_level if level_up else None
        )

    async def _check_criteria(
        self,
        player_id: int,
        game_id: Optional[int],
        stats: PlayerStats,
        criteria: Dict[str, Any]
    ) -> bool:
        """Check if achievement criteria are met."""
        # Games completed
        if 'games_completed' in criteria:
            if stats.total_games_played < criteria['games_completed']:
                return False

        # Games played
        if 'games_played' in criteria:
            if stats.total_games_played < criteria['games_played']:
                return False

        # Win with cost under threshold
        if 'win_with_cost_under' in criteria and game_id:
            game_result = await self.db.execute(
                select(func.sum(PlayerRound.round_cost))
                .where(and_(
                    PlayerRound.game_id == game_id,
                    PlayerRound.player_id == player_id
                ))
            )
            total_cost = game_result.scalar() or 0
            if total_cost >= criteria['win_with_cost_under']:
                return False

        # Perfect service rounds
        if 'perfect_service_rounds' in criteria and game_id:
            rounds_result = await self.db.execute(
                select(PlayerRound.service_level)
                .where(and_(
                    PlayerRound.game_id == game_id,
                    PlayerRound.player_id == player_id
                ))
                .order_by(PlayerRound.round_id)
            )
            service_levels = [row[0] for row in rounds_result.all()]

            consecutive_perfect = 0
            max_consecutive = 0
            for sl in service_levels:
                if sl == 100.0:
                    consecutive_perfect += 1
                    max_consecutive = max(max_consecutive, consecutive_perfect)
                else:
                    consecutive_perfect = 0

            if max_consecutive < criteria['perfect_service_rounds']:
                return False

        # Win with average inventory under
        if 'win_with_avg_inventory_under' in criteria and game_id:
            avg_result = await self.db.execute(
                select(func.avg(PlayerRound.inventory))
                .where(and_(
                    PlayerRound.game_id == game_id,
                    PlayerRound.player_id == player_id
                ))
            )
            avg_inventory = avg_result.scalar() or 0
            if avg_inventory >= criteria['win_with_avg_inventory_under']:
                return False

        # Zero backlog
        if 'zero_backlog' in criteria and game_id:
            backlog_result = await self.db.execute(
                select(func.max(PlayerRound.backlog))
                .where(and_(
                    PlayerRound.game_id == game_id,
                    PlayerRound.player_id == player_id
                ))
            )
            max_backlog = backlog_result.scalar() or 0
            if max_backlog > 0:
                return False

        # Consecutive wins
        if 'consecutive_wins' in criteria:
            if stats.consecutive_wins < criteria['consecutive_wins']:
                return False

        # Player level
        if 'player_level' in criteria:
            if stats.player_level < criteria['player_level']:
                return False

        # Win with bullwhip ratio under
        if 'win_with_bullwhip_under' in criteria and game_id:
            # Would need to calculate bullwhip effect from game data
            # Placeholder for now
            pass

        return True

    # ========================================================================
    # LEADERBOARDS
    # ========================================================================

    async def get_leaderboard(
        self,
        leaderboard_id: int,
        limit: int = 50,
        player_id: Optional[int] = None
    ) -> Optional[LeaderboardResponse]:
        """Get leaderboard with entries."""
        # Get leaderboard
        leaderboard_result = await self.db.execute(
            select(Leaderboard).where(Leaderboard.id == leaderboard_id)
        )
        leaderboard = leaderboard_result.scalar_one_or_none()

        if not leaderboard:
            return None

        # Get entries with player details
        entries_result = await self.db.execute(
            select(
                LeaderboardEntry,
                Player.email.label('player_name'),
                Player.role
            )
            .join(Player, LeaderboardEntry.player_id == Player.id)
            .where(LeaderboardEntry.leaderboard_id == leaderboard_id)
            .order_by(LeaderboardEntry.rank)
            .limit(limit)
        )

        entries = []
        for entry, player_name, player_role in entries_result.all():
            entries.append(LeaderboardEntryWithPlayer(
                **entry.__dict__,
                player_name=player_name,
                player_role=player_role
            ))

        # Get total count
        count_result = await self.db.execute(
            select(func.count(LeaderboardEntry.id))
            .where(LeaderboardEntry.leaderboard_id == leaderboard_id)
        )
        total_entries = count_result.scalar()

        # Get requesting player's rank if provided
        player_rank = None
        player_entry = None
        if player_id:
            rank_result = await self.db.execute(
                select(LeaderboardEntry)
                .where(and_(
                    LeaderboardEntry.leaderboard_id == leaderboard_id,
                    LeaderboardEntry.player_id == player_id
                ))
            )
            player_entry_obj = rank_result.scalar_one_or_none()
            if player_entry_obj:
                player_rank = player_entry_obj.rank
                player_entry = LeaderboardEntryWithPlayer(**player_entry_obj.__dict__)

        return LeaderboardResponse(
            leaderboard=leaderboard,
            entries=entries,
            total_entries=total_entries,
            player_rank=player_rank,
            player_entry=player_entry
        )

    async def update_leaderboard(self, leaderboard_id: int):
        """Recalculate and update leaderboard rankings."""
        leaderboard_result = await self.db.execute(
            select(Leaderboard).where(Leaderboard.id == leaderboard_id)
        )
        leaderboard = leaderboard_result.scalar_one_or_none()

        if not leaderboard:
            return

        # Get all player stats
        stats_result = await self.db.execute(
            select(PlayerStats)
        )
        all_stats = stats_result.scalars().all()

        # Calculate scores based on metric
        metric = leaderboard.metric
        player_scores = []

        for stats in all_stats:
            score = None
            if metric == 'total_points':
                score = float(stats.total_points)
            elif metric == 'win_rate' and stats.total_games_played > 0:
                score = (stats.total_games_won / stats.total_games_played) * 100
            elif metric == 'avg_cost' and stats.total_games_played > 0:
                score = float(stats.total_cost / stats.total_games_played)
            elif metric == 'service_level':
                score = float(stats.avg_service_level or 0)

            if score is not None:
                player_scores.append((stats.player_id, score))

        # Sort and assign ranks
        ascending = metric == 'avg_cost'  # Lower is better for costs
        player_scores.sort(key=lambda x: x[1], reverse=not ascending)

        # Clear existing entries
        await self.db.execute(
            delete(LeaderboardEntry).where(LeaderboardEntry.leaderboard_id == leaderboard_id)
        )

        # Insert new entries
        for rank, (player_id, score) in enumerate(player_scores, start=1):
            entry = LeaderboardEntry(
                leaderboard_id=leaderboard_id,
                player_id=player_id,
                rank=rank,
                score=score
            )
            self.db.add(entry)

        await self.db.commit()

    async def get_all_leaderboards(self, active_only: bool = True) -> List[Leaderboard]:
        """Get all leaderboards."""
        query = select(Leaderboard)
        if active_only:
            query = query.where(Leaderboard.is_active == True)

        result = await self.db.execute(query)
        return result.scalars().all()

    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================

    async def get_unread_notifications(
        self,
        player_id: int,
        limit: int = 10
    ) -> List[AchievementNotification]:
        """Get unread notifications for a player."""
        result = await self.db.execute(
            select(AchievementNotification)
            .where(and_(
                AchievementNotification.player_id == player_id,
                AchievementNotification.is_read == False
            ))
            .order_by(AchievementNotification.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_notification_read(self, notification_id: int):
        """Mark a notification as read."""
        await self.db.execute(
            update(AchievementNotification)
            .where(AchievementNotification.id == notification_id)
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await self.db.commit()

    async def mark_notification_shown(self, notification_id: int):
        """Mark a notification as shown in UI."""
        await self.db.execute(
            update(AchievementNotification)
            .where(AchievementNotification.id == notification_id)
            .values(is_shown=True)
        )
        await self.db.commit()


# ============================================================================
# SERVICE FACTORY
# ============================================================================

def get_gamification_service(db: AsyncSession) -> GamificationService:
    """Factory function to get gamification service instance."""
    return GamificationService(db)

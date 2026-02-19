"""
Test script for gamification endpoints.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Achievement, Leaderboard  # Import from models package
from app.services.gamification_service import get_gamification_service


async def test_gamification():
    """Test gamification service and models."""
    print("=" * 80)
    print("Gamification System - Functional Test")
    print("=" * 80)

    async with SessionLocal() as db:
        # Test 1: Check achievements in database
        print("\n1. Testing Achievement Models")
        print("-" * 80)
        try:
            result = await db.execute(select(Achievement))
            achievements = result.scalars().all()
            print(f"✅ Found {len(achievements)} achievements in database")
            if achievements:
                first_ach = achievements[0]
                print(f"   Example: {first_ach.name} ({first_ach.category}, {first_ach.rarity})")
                print(f"   Description: {first_ach.description}")
                print(f"   Points: {first_ach.points}")
        except Exception as e:
            print(f"❌ Error loading achievements: {e}")
            return

        # Test 2: Check leaderboards
        print("\n2. Testing Leaderboard Models")
        print("-" * 80)
        try:
            result = await db.execute(select(Leaderboard))
            leaderboards = result.scalars().all()
            print(f"✅ Found {len(leaderboards)} leaderboards in database")
            if leaderboards:
                first_lb = leaderboards[0]
                print(f"   Example: {first_lb.name} ({first_lb.leaderboard_type})")
                print(f"   Metric: {first_lb.metric}")
        except Exception as e:
            print(f"❌ Error loading leaderboards: {e}")
            return

        # Test 3: Test GamificationService
        print("\n3. Testing GamificationService")
        print("-" * 80)
        try:
            service = get_gamification_service(db)
            print(f"✅ Service instantiated: {type(service).__name__}")
            print(f"   Points per level: {service.points_per_level}")

            # Test level calculation
            level_1 = service.calculate_player_level(0)
            level_2 = service.calculate_player_level(10)
            level_3 = service.calculate_player_level(100)
            print(f"   Level at 0 points: {level_1}")
            print(f"   Level at 10 points: {level_2}")
            print(f"   Level at 100 points: {level_3}")

            # Test points for next level
            next_level_points = service.points_for_next_level(1)
            print(f"   Points needed for level 2: {next_level_points}")
        except Exception as e:
            print(f"❌ Error with service: {e}")
            return

        # Test 4: Test getting/creating player stats
        print("\n4. Testing Player Stats")
        print("-" * 80)
        try:
            # Use player_id 1 (should exist from seed data)
            stats = await service.get_or_create_player_stats(player_id=1)
            print(f"✅ Player stats retrieved/created for player_id=1")
            print(f"   Games played: {stats.total_games_played}")
            print(f"   Games won: {stats.total_games_won}")
            print(f"   Total points: {stats.total_points}")
            print(f"   Player level: {stats.player_level}")
            print(f"   Achievements unlocked: {stats.total_achievements_unlocked}")
        except Exception as e:
            print(f"❌ Error with player stats: {e}")
            return

        # Test 5: Test achievement checking logic
        print("\n5. Testing Achievement Checking")
        print("-" * 80)
        try:
            result = await service.check_achievements(player_id=1, game_id=None)
            print(f"✅ Achievement check completed")
            print(f"   Newly unlocked: {len(result.newly_unlocked)}")
            print(f"   Points earned: {result.total_points_earned}")
            print(f"   Level up: {result.level_up}")
            if result.newly_unlocked:
                for ach in result.newly_unlocked[:3]:  # Show first 3
                    print(f"   - {ach.name}")
        except Exception as e:
            print(f"❌ Error checking achievements: {e}")
            return

        # Test 6: Test leaderboard retrieval
        print("\n6. Testing Leaderboard Retrieval")
        print("-" * 80)
        try:
            all_leaderboards = await service.get_all_leaderboards(active_only=True)
            print(f"✅ Found {len(all_leaderboards)} active leaderboards")
            if all_leaderboards:
                # Try to get first leaderboard's data
                first_lb_id = all_leaderboards[0].id
                lb_response = await service.get_leaderboard(first_lb_id, limit=10)
                if lb_response:
                    print(f"   Leaderboard: {lb_response.leaderboard.name}")
                    print(f"   Total entries: {lb_response.total_entries}")
                    print(f"   Top {len(lb_response.entries)} entries retrieved")
        except Exception as e:
            print(f"❌ Error with leaderboard retrieval: {e}")
            return

    print("\n" + "=" * 80)
    print("✅ ALL GAMIFICATION TESTS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_gamification())

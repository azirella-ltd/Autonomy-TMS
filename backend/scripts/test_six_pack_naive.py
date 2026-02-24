"""Test script to run Naive Agent Showcase for Six-Pack simulation scenario.

This will find and start the Naive Agent Showcase (Six-Pack Beer Game) scenario
to test the manufacturer site fix.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.models.scenario import Scenario, ScenarioStatus as DbScenarioStatus
from app.models.participant import Participant
from app.services.mixed_game_service import MixedGameService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TARGET_GAME_NAME = "Naive Agent Showcase (Six-Pack Beer Game)"


async def find_target_scenario(session: AsyncSession) -> Scenario | None:
    """Find the Naive Agent Showcase scenario for Six-Pack simulation."""
    result = await session.execute(
        select(Scenario).where(Scenario.name == TARGET_GAME_NAME).order_by(Scenario.id)
    )
    return result.scalar_one_or_none()


async def force_ai_participants(session: AsyncSession, scenario: Scenario) -> None:
    """Ensure all participants are AI."""
    result = await session.execute(
        select(Participant).where(Participant.scenario_id == scenario.id)
    )
    participants = result.scalars().all()
    for p in participants:
        p.is_ai = True
        session.add(p)
    await session.commit()


def ensure_unsupervised(scenario: Scenario) -> None:
    """Set progression_mode to unsupervised."""
    cfg = scenario.config or {}
    cfg["progression_mode"] = "unsupervised"
    scenario.config = cfg


async def main():
    """Run the test."""
    from app.db.session import async_session_factory

    if not async_session_factory:
        print("ERROR: async_session_factory not available")
        return 1

    async with async_session_factory() as session:
        try:
            # Find the scenario
            scenario = await find_target_scenario(session)
            if not scenario:
                print(f"ERROR: Scenario '{TARGET_GAME_NAME}' not found")
                return 1

            print(f"Found scenario {scenario.id}: {scenario.name}")
            print(f"  Status: {scenario.status}")
            print(f"  Current round: {scenario.current_round}/{scenario.max_rounds}")

            # Reset if needed
            if scenario.status != DbScenarioStatus.CREATED:
                print(f"  Resetting scenario status from {scenario.status} to CREATED...")
                scenario.status = DbScenarioStatus.CREATED
                scenario.current_round = 0
                session.add(scenario)
                await session.commit()

            # Force AI and unsupervised
            await force_ai_participants(session, scenario)
            ensure_unsupervised(scenario)
            session.add(scenario)
            await session.commit()

            print(f"Starting scenario via MixedGameService...")
            service = MixedGameService(session)

            # Start the scenario
            await service.start_game(scenario.id)
            print(f"✓ Scenario started successfully")

            # Progress through rounds
            print(f"Running rounds...")
            for round_num in range(1, min(5, scenario.max_rounds + 1)):
                print(f"  Round {round_num}...", end="", flush=True)
                try:
                    await service.start_new_round(scenario)
                    print(" ✓")
                except Exception as e:
                    print(f" ✗ Error: {e}")
                    return 1

            print(f"\n✓ Successfully completed first {min(4, scenario.max_rounds)} rounds!")
            return 0

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

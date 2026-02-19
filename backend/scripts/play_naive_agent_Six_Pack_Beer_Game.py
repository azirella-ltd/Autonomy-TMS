"""Run the Naive Agent Showcase scenario for Six-Pack Beer Game via MixedScenarioService.

- Finds the first scenario whose name contains "Naive Agent Showcase" and whose config
  SC config/template is Six-Pack Beer Game.
- Forces progression_mode to unsupervised and all participants to AI before starting.
- Starts the scenario via MixedScenarioService (same engine path as the UI start button).
"""
from __future__ import annotations

from typing import Optional

from backend.main import SessionLocal
from app.models.scenario import Scenario, ScenarioStatus as DbScenarioStatus
from app.models.participant import Participant
from app.services.mixed_scenario_service import MixedScenarioService

TARGET_GAME_NAME = "Naive Agent Showcase"
TARGET_SC_CONFIG = "six-pack beer game"  # case-insensitive match on config/template label


def _find_target_scenario(session) -> Optional[Scenario]:
    scenarios = session.query(Scenario).order_by(Scenario.id).all()
    for g in scenarios:
        if g.name and TARGET_GAME_NAME.lower() in g.name.lower() and "six-pack beer game" in g.name.lower():
            return g
    return None


def _force_ai_participants(session, scenario: Scenario) -> None:
    players = session.query(Participant).filter(Participant.scenario_id == scenario.id).all()
    for p in players:
        p.is_ai = True
        session.add(p)
    session.commit()


def _ensure_unsupervised(scenario: Scenario) -> None:
    cfg = scenario.config or {}
    cfg["progression_mode"] = "unsupervised"
    scenario.config = cfg


def main() -> None:
    session = SessionLocal()
    try:
        target = _find_target_scenario(session)
        if not target:
            print("No Naive Agent Showcase (Six-Pack Beer Game) scenario found.")
            return

        print(f"Found scenario id={target.id}, name={target.name}, status={target.status}")

        _force_ai_participants(session, target)
        _ensure_unsupervised(target)
        target.status = DbScenarioStatus.CREATED
        session.add(target)
        session.commit()

        print(f"Starting scenario...")
        svc = MixedScenarioService(session)
        svc.start_scenario(target.id)  # This is SYNC, not async
        print(f"✓ Scenario started successfully: id={target.id}, name={target.name}")

        # Refresh to see current state
        session.refresh(target)
        print(f"  Current status: {target.status}, Round: {target.current_round}/{target.max_rounds}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()

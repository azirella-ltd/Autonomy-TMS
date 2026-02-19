"""Run the Naive Agent Showcase scenario for Default Beer Game via MixedGameService.

- Finds the first scenario whose name contains "Naive Agent Showcase" and whose config
  SC config/template is Default Beer Game.
- Forces progression_mode to unsupervised and all participants to AI before starting.
- Starts the scenario via MixedGameService (same engine path as the UI start button).
"""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.main import SessionLocal
from app.models.scenario import Scenario, ScenarioStatus as DbScenarioStatus
from app.models.participant import Participant
from app.services.mixed_scenario_service import MixedGameService

TARGET_GAME_NAME = "Naive Agent Showcase"
TARGET_SC_CONFIG = "default beer game"  # case-insensitive match on config/template label


def _is_default_tbg(cfg: dict) -> bool:
    if not isinstance(cfg, dict):
        return False
    label = str(cfg.get("supply_chain_label") or cfg.get("supply_chain_template") or cfg.get("sc_config") or "").lower()
    return "default beer game" in label or TARGET_SC_CONFIG in label


def _find_target_scenario(session) -> Optional[Scenario]:
    scenarios = session.query(Scenario).order_by(Scenario.id).all()
    for g in scenarios:
        if g.name and TARGET_GAME_NAME.lower() in g.name.lower():
            cfg = g.config or {}
            if _is_default_tbg(cfg):
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


async def main() -> None:
    session = SessionLocal()
    try:
        target = _find_target_scenario(session)
        if not target:
            print("No Naive Agent Showcase (Default Beer Game) scenario found.")
            return

        _force_ai_participants(session, target)
        _ensure_unsupervised(target)
        target.status = DbScenarioStatus.CREATED
        session.add(target)
        session.commit()

        svc = MixedGameService(session)
        await svc.start_game(target.id)
        print(f"Started scenario id={target.id}, name={target.name}")
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())

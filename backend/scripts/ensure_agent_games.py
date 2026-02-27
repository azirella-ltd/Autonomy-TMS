"""Ensure showcase scenarios exist for specific agent strategies (human and AI)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.scenario import Scenario, ScenarioStatus
from app.services.supply_chain_config_service import SupplyChainConfigService
from scripts.seed_default_tenant import (
    ensure_customer,
    ensure_supply_chain_config,
    ensure_ai_agents,
    configure_human_players_for_game,
    DEFAULT_LLM_MODEL,
)

SHOWCASE_GAMES = [
    {
        "name": "The Beer Game - Human",
        "description": "Benchmark simulation scenario with human scenario_users assigned to each role.",
        "strategy": "human",
        "llm_model": None,
    },
    {
        "name": "The Beer Game - Naiive",
        "description": "Baseline simulation scenario using Naive agent strategy for all roles.",
        "strategy": "naive",
        "llm_model": None,
    },
    {
        "name": "The Beer Game - PID",
        "description": "Simulation scenario showcasing the PID heuristic controller across the supply chain.",
        "strategy": "pid_heuristic",
        "llm_model": None,
    },
    {
        "name": "The Beer Game - TRM",
        "description": "Simulation scenario using TRM (Tiny Recursive Model) agents with 7M parameter neural network and recursive refinement for fast, optimized supply chain decisions.",
        "strategy": "trm",
        "llm_model": None,
    },
]

def ensure_agent_game(
    session,
    service: SupplyChainConfigService,
    customer,
    config,
    *,
    name: str,
    description: str,
    strategy: str,
    llm_model: Optional[str],
    llm_strategy: Optional[str] = None,
) -> None:
    scenario = (
        session.query(Scenario)
        .filter(Scenario.customer_id == customer.id, Scenario.name == name)
        .first()
    )
    is_human = strategy == "human"
    if scenario is None:
        base_config = service.create_game_from_config(
            config.id,
            {
                "name": name,
                "description": description,
                "max_rounds": 40,
                "is_public": True,
            },
        )
        base_config["progression_mode"] = "unsupervised"
        scenario = Scenario(
            name=name,
            description=description,
            created_by=customer.admin_id,
            customer_id=customer.id,
            status=ScenarioStatus.CREATED,
            max_rounds=base_config.get("max_rounds", 40),
            config=base_config,
            demand_pattern=base_config.get("demand_pattern", {}),
            supply_chain_config_id=config.id,
        )
        session.add(scenario)
        session.flush()
    else:
        scenario.description = description
        if isinstance(scenario.config, str):
            try:
                scenario_config = json.loads(scenario.config)
            except json.JSONDecodeError:
                scenario_config = {}
        else:
            scenario_config = scenario.config or {}
        scenario_config["progression_mode"] = "unsupervised"
        scenario.config = json.loads(json.dumps(scenario_config))
        scenario.status = ScenarioStatus.CREATED

    if is_human:
        configure_human_players_for_game(session, customer, scenario)
        # Ensure autonomy strategy fields are cleared for human-controlled scenarios.
        if isinstance(scenario.config, str):
            try:
                config_payload = json.loads(scenario.config)
            except json.JSONDecodeError:
                config_payload = {}
        else:
            config_payload = scenario.config or {}
        autonomy_cfg = config_payload.get("autonomy") or {}
        autonomy_cfg.pop("strategy", None)
        autonomy_cfg.pop("llm_model", None)
        autonomy_cfg.pop("llm_strategy", None)
        if autonomy_cfg:
            config_payload["autonomy"] = autonomy_cfg
        elif "autonomy" in config_payload:
            config_payload.pop("autonomy", None)
        scenario.config = json.loads(json.dumps(config_payload))
        session.add(scenario)
        session.commit()
        return

    ensure_ai_agents(session, scenario, strategy, llm_model, llm_strategy)
    session.commit()

def main() -> None:
    Session = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        customer, _ = ensure_customer(session)
        config = ensure_supply_chain_config(session, customer)
        service = SupplyChainConfigService(session)

        for spec in SHOWCASE_GAMES:
            ensure_agent_game(
                session,
                service,
                customer,
                config,
                name=spec["name"],
                description=spec["description"],
                strategy=spec["strategy"],
                llm_model=spec["llm_model"],
                llm_strategy=spec.get("llm_strategy"),
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()

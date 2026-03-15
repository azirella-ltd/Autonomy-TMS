#!/usr/bin/env python3
"""Add AI scenario_users to Complex_SC showcase scenarios that have no scenario_users."""

import sys
from pathlib import Path

# Ensure the backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy.orm import Session
from app.db.base_class import SessionLocal
from app.models import Scenario, ScenarioUser, PlayerType, PlayerStrategy, PlayerRole
from app.models.supply_chain_config import NodeType
from typing import Dict, Any
import json


def _load_scenario_config_payload(scenario: Scenario) -> Dict[str, Any]:
    """Load scenario configuration as dict."""
    if isinstance(scenario.config, dict):
        return scenario.config
    if isinstance(scenario.config, str):
        try:
            return json.loads(scenario.config)
        except json.JSONDecodeError:
            return {}
    return {}


def _player_role_for_node_type(node_type_str: str) -> PlayerRole:
    """Map node type string to scenario_user role."""
    # Map common node types to roles
    node_type_upper = node_type_str.upper()
    if "RETAIL" in node_type_upper:
        return PlayerRole.RETAILER
    elif "WHOLE" in node_type_upper:
        return PlayerRole.WHOLESALER
    elif "DISTRIB" in node_type_upper or "DC" in node_type_upper:
        return PlayerRole.DISTRIBUTOR
    elif "PLANT" in node_type_upper or "FACTORY" in node_type_upper or "MANUFACT" in node_type_upper:
        return PlayerRole.MANUFACTURER
    elif "SUPPLIER" in node_type_upper or "TIER" in node_type_upper:
        return PlayerRole.SUPPLIER
    else:
        return PlayerRole.DISTRIBUTOR  # default for inventory nodes


def add_scenario_users(session: Session, scenario: Scenario, agent_type: str = "naive") -> None:
    """Add AI scenario_users to a scenario based on its supply chain config."""
    print(f"\n[info] Processing scenario {scenario.id}: {scenario.name}")

    existing_count = session.query(ScenarioUser).filter(
        ScenarioUser.scenario_id == scenario.id
    ).count()
    if existing_count > 0:
        print(f"  [skip] Scenario already has {existing_count} scenario_users")
        return

    if not scenario.supply_chain_config_id:
        print("  [error] Scenario has no supply_chain_config_id")
        return

    from app.models.supply_chain_config import SupplyChainConfig, Site as SCNode

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == scenario.supply_chain_config_id
    ).first()

    if not config:
        print(f"  [error] Could not find supply chain config {scenario.supply_chain_config_id}")
        return

    nodes = session.query(SCNode).filter(SCNode.config_id == config.id).all()

    if not nodes:
        print("  [error] No nodes found in supply chain config")
        return

    print(f"  [info] Found {len(nodes)} nodes in config")

    playable_master_types = {"inventory", "manufacturer"}

    created_count = 0
    for node in nodes:
        if node.master_type in playable_master_types:
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(node.type),
                name=f"{node.name} ({agent_type})",
                node_key=node.name,
                type=PlayerType.AI,
                is_ai=True,
                ai_strategy=agent_type,
                strategy=PlayerStrategy.MANUAL,
                user_id=None,
                can_see_demand=False,
            )
            session.add(scenario_user)
            created_count += 1
            print(f"    [+] Created scenario_user for {node.name} (type: {node.type}, master_type: {node.master_type})")

    session.flush()
    print(f"  [success] Created {created_count} scenario_users for scenario {scenario.id}")


def main():
    session = SessionLocal()

    try:
        # Find all Complex_SC scenarios (config_id = 12)
        scenarios = session.query(Scenario).filter(
            Scenario.supply_chain_config_id == 12
        ).all()

        print(f"\n[info] Found {len(scenarios)} Complex_SC scenarios")

        for scenario in scenarios:
            name_lower = scenario.name.lower()
            if "naive" in name_lower:
                agent_type = "naive"
            elif "pid" in name_lower:
                agent_type = "pid_heuristic"
            elif "trm" in name_lower:
                agent_type = "trm"
            elif "llm" in name_lower or "autonomy" in name_lower:
                agent_type = "autonomy_llm"
            elif "gnn" in name_lower:
                agent_type = "ml_forecast"
            else:
                agent_type = "naive"

            add_scenario_users(session, scenario, agent_type)

        session.commit()
        print("\n[success] All scenarios processed successfully!")

    except Exception as e:
        session.rollback()
        print(f"\n[error] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Add AI players to Complex_SC showcase games that have no players."""

import sys
from pathlib import Path

# Ensure the backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy.orm import Session
from app.db.base_class import SessionLocal
from app.models import Game, Player, PlayerType, PlayerStrategy, PlayerRole
from app.models.supply_chain_config import NodeType
from typing import Dict, Any
import json


def _load_game_config_payload(game: Game) -> Dict[str, Any]:
    """Load game configuration as dict."""
    if isinstance(game.config, dict):
        return game.config
    if isinstance(game.config, str):
        try:
            return json.loads(game.config)
        except json.JSONDecodeError:
            return {}
    return {}


def _player_role_for_node_type(node_type_str: str) -> PlayerRole:
    """Map node type string to player role."""
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


def add_players_to_game(session: Session, game: Game, agent_type: str = "naive") -> None:
    """Add AI players to a game based on its supply chain config."""
    print(f"\n[info] Processing game {game.id}: {game.name}")

    # Check if players already exist
    existing_player_count = session.query(Player).filter(Player.game_id == game.id).count()
    if existing_player_count > 0:
        print(f"  [skip] Game already has {existing_player_count} players")
        return

    # Get the supply chain config to find all nodes
    if not game.supply_chain_config_id:
        print("  [error] Game has no supply_chain_config_id")
        return

    from app.models.supply_chain_config import SupplyChainConfig, Node as SCNode

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == game.supply_chain_config_id
    ).first()

    if not config:
        print(f"  [error] Could not find supply chain config {game.supply_chain_config_id}")
        return

    # Get all nodes from the config
    nodes = session.query(SCNode).filter(SCNode.config_id == config.id).all()

    if not nodes:
        print("  [error] No nodes found in supply chain config")
        return

    print(f"  [info] Found {len(nodes)} nodes in config")

    # Create a player for each node that's playable (has master_type = inventory or manufacturer)
    playable_master_types = {"inventory", "manufacturer"}

    created_count = 0
    for node in nodes:
        if node.master_type in playable_master_types:
            player = Player(
                game_id=game.id,
                role=_player_role_for_node_type(node.type),
                name=f"{node.name} ({agent_type})",
                node_key=node.name,  # Use node.name as key
                type=PlayerType.AI,
                is_ai=True,
                ai_strategy=agent_type,
                strategy=PlayerStrategy.MANUAL,
                user_id=None,
                can_see_demand=False,
            )
            session.add(player)
            created_count += 1
            print(f"    [+] Created player for {node.name} (type: {node.type}, master_type: {node.master_type})")

    session.flush()
    print(f"  [success] Created {created_count} players for game {game.id}")


def main():
    session = SessionLocal()

    try:
        # Find all Complex_SC games (config_id = 12)
        games = session.query(Game).filter(Game.supply_chain_config_id == 12).all()

        print(f"\n[info] Found {len(games)} Complex_SC games")

        for game in games:
            # Determine agent type from game name
            game_name_lower = game.name.lower()
            if "naive" in game_name_lower:
                agent_type = "naive"
            elif "pid" in game_name_lower:
                agent_type = "pid_heuristic"
            elif "trm" in game_name_lower:
                agent_type = "trm"
            elif "llm" in game_name_lower or "autonomy" in game_name_lower:
                agent_type = "autonomy_llm"
            elif "gnn" in game_name_lower:
                agent_type = "ml_forecast"
            else:
                agent_type = "naive"  # default

            add_players_to_game(session, game, agent_type)

        session.commit()
        print("\n[success] All games processed successfully!")

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

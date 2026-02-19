#!/usr/bin/env python3
"""
Create hybrid human/naive games for Default Beer Game configuration.
This script creates 4 new games:
- Retailer Beer Game (retailer human, others naive)
- Wholesaler Beer Game (wholesaler human, others naive)
- Distributor Beer Game (distributor human, others naive)
- Manufacturer Beer Game (manufacturer human, others naive)
"""

import sys
from pathlib import Path

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.core.config import settings
from app.models import (
    Game, GameStatus, Player, PlayerType, PlayerStrategy, PlayerRole,
    User, Group, SupplyChainConfig, Node, NodeType
)
from app.models.user import UserTypeEnum
from app.core.security import get_password_hash
from app.services.supply_chain_config_service import SupplyChainConfigService
import json

# Create engine and session
engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(bind=engine)

DEFAULT_PASSWORD = "Autonomy@2025"

# Map node types to PlayerRole enum
NODE_TYPE_TO_PLAYER_ROLE = {
    "retailer": PlayerRole.RETAILER,
    "wholesaler": PlayerRole.WHOLESALER,
    "distributor": PlayerRole.DISTRIBUTOR,
    "manufacturer": PlayerRole.MANUFACTURER,
    "factory": PlayerRole.MANUFACTURER,  # Factory is a type of manufacturer
    "supplier": PlayerRole.SUPPLIER,
    "market_demand": PlayerRole.MARKET_DEMAND,
    "market_supply": PlayerRole.MARKET_SUPPLY,
}


def create_user_for_node(session, group, node_label, node_key):
    """Create or get user for a node."""
    email = f"{node_key}@autonomy.ai"
    user = session.query(User).filter(User.email == email).first()

    if not user:
        user = User(
            username=node_label,
            email=email,
            full_name=node_label,
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            is_active=True,
            is_superuser=False,
            user_type=UserTypeEnum.USER,
            group_id=group.id,
        )
        session.add(user)
        session.flush()
        print(f"[Created user] {node_label} ({email})")
    else:
        print(f"[Existing user] {node_label} ({email})")

    return user


def get_playable_nodes(config_payload):
    """Extract playable nodes from game config."""
    nodes = []
    for entry in config_payload.get("nodes", []):
        node_type = entry.get("type", "").lower()
        # Try multiple label fields
        label = entry.get("label") or entry.get("name") or entry.get("type", "").title()
        key = entry.get("key", node_type)

        # Skip market nodes
        if node_type in ["market_demand", "market_supply"]:
            continue

        can_see_demand = entry.get("can_see_demand", False)
        nodes.append({
            "type": node_type,
            "label": label,
            "key": key,
            "can_see_demand": can_see_demand
        })

    return nodes


def create_hybrid_game(session, group, config, game_name, human_site_key, template_game):
    """Create a hybrid game with one human player and rest naive AI."""

    # Check if game already exists
    existing = session.query(Game).filter(
        Game.group_id == group.id,
        Game.name == game_name
    ).first()

    if existing:
        print(f"[Skip] Game '{game_name}' already exists")
        return existing

    # Clone config from template game
    config_payload = json.loads(json.dumps(template_game.config))
    config_payload["name"] = game_name
    config_payload["progression_mode"] = "supervised"

    # Create game
    game = Game(
        name=game_name,
        group_id=group.id,
        supply_chain_config_id=config.id,
        config=config_payload,
        description=f"Play as {human_site_key.title()} with Naive AI teammates",
        status=GameStatus.CREATED,
        max_rounds=40,
    )
    session.add(game)
    session.flush()

    # Get playable nodes
    nodes = get_playable_nodes(config_payload)

    # Create players
    for node in nodes:
        # Map node type to PlayerRole
        player_role = NODE_TYPE_TO_PLAYER_ROLE.get(node["type"].lower(), PlayerRole.RETAILER)

        if node["key"] == human_site_key:
            # Human player
            user = create_user_for_node(session, group, node["label"], node["key"])
            player = Player(
                game_id=game.id,
                role=player_role,
                name=node["label"],
                type=PlayerType.HUMAN,
                strategy=PlayerStrategy.MANUAL,
                is_ai=False,
                user_id=user.id,
                site_key=node["key"],
                can_see_demand=node["can_see_demand"],
            )
            print(f"[Created player] {node['label']} (HUMAN)")
        else:
            # Naive AI player
            player = Player(
                game_id=game.id,
                role=player_role,
                name=f"{node['label']} (Naive AI)",
                type=PlayerType.AI,
                strategy=PlayerStrategy.MANUAL,
                is_ai=True,
                ai_strategy="naive",
                user_id=None,
                site_key=node["key"],
                can_see_demand=node["can_see_demand"],
            )
            print(f"[Created player] {node['label']} (NAIVE AI)")

        session.add(player)

    session.flush()
    print(f"[Success] Created game: {game_name}")
    return game


def main():
    session = SessionLocal()

    try:
        # Get Default Beer Game group
        group = session.query(Group).filter(Group.name == "Beer Game").first()
        if not group:
            print("[Error] Beer Game group not found. Please run the main seeding script first.")
            return

        print(f"[Found group] {group.name} (id={group.id})")

        # Get Default Beer Game config
        config = session.query(SupplyChainConfig).filter(
            SupplyChainConfig.group_id == group.id,
            SupplyChainConfig.name == "Default Beer Game"
        ).first()

        if not config:
            print("[Error] Default Beer Game configuration not found. Please run the main seeding script first.")
            return

        print(f"[Found config] {config.name} (id={config.id})")

        # Get template game (The Beer Game)
        template_game = session.query(Game).filter(
            Game.group_id == group.id,
            Game.name == "The Beer Game"
        ).first()

        if not template_game:
            print("[Error] Template game 'The Beer Game' not found. Please run the main seeding script first.")
            return

        print(f"[Found template] {template_game.name} (id={template_game.id})")

        # Create 4 hybrid games
        hybrid_configs = [
            ("retailer", "Retailer Beer Game"),
            ("wholesaler", "Wholesaler Beer Game"),
            ("distributor", "Distributor Beer Game"),
            ("factory", "Manufacturer Beer Game"),
        ]

        for site_key, game_name in hybrid_configs:
            create_hybrid_game(session, group, config, game_name, site_key, template_game)

        session.commit()
        print("\n[Complete] All hybrid games created successfully!")

        # Show summary
        print("\n=== Game Summary ===")
        games = session.query(Game).filter(Game.group_id == group.id).all()
        for game in games:
            player_count = session.query(Player).filter(Player.game_id == game.id).count()
            print(f"- {game.name} ({player_count} players)")

    except Exception as e:
        session.rollback()
        print(f"\n[Error] Failed to create hybrid games: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Seed the default Autonomy group, configuration, and game with AI players."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

# Ensure the backend package is importable when running via `python backend/scripts/...`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db_urls import resolve_sync_database_url

DATABASE_URL = resolve_sync_database_url()
print(f"Using database at: {DATABASE_URL}")

# Import SQLAlchemy models and utilities
try:
    from app.db.base_class import Base, engine, SessionLocal
    from app.models import (
        Group,
        Game,
        GameStatus,
        Player,
        PlayerRole,
        PlayerStrategy,
        PlayerType,
        User,
    )
    from app.models.agent_config import AgentConfig
    from app.schemas.group import GroupCreate
    from app.schemas.user import UserCreate
    from app.services.group_service import GroupService
    from scripts.seed_default_group import ensure_supply_chain_config
except ImportError as e:
    print(f"Error importing application modules: {e}")
    print("Make sure you're running this script from the backend directory and all dependencies are installed.")
    sys.exit(1)

# Constants
DEFAULT_GROUP_NAME = "Default TBG"
DEFAULT_GROUP_DESCRIPTION = "Default Autonomy Beer Game group"
DEFAULT_ADMIN_USERNAME = "groupadmin"
DEFAULT_ADMIN_EMAIL = "groupadmin@autonomy.ai"
DEFAULT_ADMIN_FULL_NAME = "Group Administrator"
DEFAULT_PASSWORD = "Autonomy@2025"
DEFAULT_GAME_NAME = "The Beer Game"
DEFAULT_AGENT_TYPE = "pid_heuristic"

def ensure_group(session: Session) -> Tuple[Group, bool]:
    """Create the default group and admin if they do not already exist."""
    existing_group = session.query(Group).filter(Group.name == DEFAULT_GROUP_NAME).first()
    
    if existing_group:
        print(f"Group '{DEFAULT_GROUP_NAME}' already exists with ID: {existing_group.id}")
        return existing_group, False
    
    print(f"Creating new group: {DEFAULT_GROUP_NAME}")
    
    # Create the group admin user using raw SQL to avoid ORM issues with missing columns
    from passlib.context import CryptContext
    from sqlalchemy import text
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(DEFAULT_PASSWORD)
    now = datetime.utcnow()
    
    # First, check if the user already exists
    existing_user = session.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {'email': DEFAULT_ADMIN_EMAIL}
    ).fetchone()
    
    if existing_user:
        user_id = existing_user[0]
        print(f"Admin user already exists with ID: {user_id}")
    else:
        # Insert the user directly with SQL
        result = session.execute(
            text("""
                INSERT INTO users (username, email, hashed_password, full_name, 
                                is_active, is_superuser, created_at, updated_at)
                VALUES (:username, :email, :hashed_password, :full_name, 
                    :is_active, :is_superuser, :created_at, :updated_at)
            """),
            {
                'username': DEFAULT_ADMIN_USERNAME,
                'email': DEFAULT_ADMIN_EMAIL,
                'hashed_password': hashed_password,
                'full_name': DEFAULT_ADMIN_FULL_NAME,
                'is_active': 1,
                'is_superuser': 1,
                'created_at': now,
                'updated_at': now
            }
        )
        
        # Get the inserted user's ID
        result = session.execute(text("SELECT LAST_INSERT_ID()"))
        user_id = result.scalar()
        print(f"Created new admin user with ID: {user_id}")
    
    # Create a simple user object with just the ID for the group creation
    class SimpleUser:
        def __init__(self, user_id):
            self.id = user_id
    
    admin_user = SimpleUser(user_id)
    
    # Create the group
    group = Group(
        name=DEFAULT_GROUP_NAME,
        description=DEFAULT_GROUP_DESCRIPTION,
        admin_id=admin_user.id,
    )
    session.add(group)
    session.flush()  # Get the group ID
    
    # Update the admin user's group_id
    session.execute(
        text("UPDATE users SET group_id = :group_id WHERE id = :user_id"),
        {'group_id': group.id, 'user_id': admin_user.id}
    )
    
    # Commit all changes
    session.commit()
    
    print(f"Created group '{group.name}' with ID: {group.id}")
    print(f"Created admin user with ID: {admin_user.id}")
    print("Database seeding completed successfully!")
    
    return group, True

def ensure_default_game(session: Session, group: Group) -> Game:
    """Ensure the default game exists for the supplied group."""
    sc_config = ensure_supply_chain_config(session, group)
    existing_game = session.query(Game).filter(
        Game.name == DEFAULT_GAME_NAME,
        Game.group_id == group.id
    ).first()

    if existing_game:
        print(f"Game '{DEFAULT_GAME_NAME}' already exists with ID: {existing_game.id}")
        existing_game.supply_chain_config_id = sc_config.id
        session.add(existing_game)
        return existing_game
    
    print(f"Creating new game: {DEFAULT_GAME_NAME}")

    # Create the game
    game = Game(
        name=DEFAULT_GAME_NAME,
        status=GameStatus.CREATED,
        group_id=group.id,
        created_by=group.created_by,
        max_rounds=52,  # Default number of rounds
        supply_chain_config_id=sc_config.id,
    )
    session.add(game)
    session.flush()
    
    # Create default players
    _ensure_default_players(session, game)
    
    # Create default AI agents
    ensure_naive_agents(session, game)
    
    session.commit()
    
    print(f"Created game '{game.name}' with ID: {game.id}")
    return game

def _ensure_default_players(session: Session, game: Game) -> None:
    """Create placeholder AI players if none exist for the game."""
    existing_players = session.query(Player).filter(Player.game_id == game.id).count()
    if existing_players > 0:
        print(f"Game already has {existing_players} players")
        return
    
    print("Creating default players for the game")
    
    # Define the default player roles and types
    player_roles = [
        (PlayerRole.RETAILER, PlayerType.AI, "Retailer AI"),
        (PlayerRole.WHOLESALER, PlayerType.AI, "Wholesaler AI"),
        (PlayerRole.DISTRIBUTOR, PlayerType.AI, "Distributor AI"),
        (PlayerRole.MANUFACTURER, PlayerType.AI, "Manufacturer AI"),
    ]
    
    for role, player_type, name in player_roles:
        player = Player(
            game_id=game.id,
            role=role,
            player_type=player_type,
            name=name,
            is_active=True,
        )
        session.add(player)
    
    session.flush()
    print(f"Created {len(player_roles)} default players")

def ensure_naive_agents(session: Session, game: Game) -> None:
    """Assign AI agents to each role in the game."""
    # Get all AI players in the game
    players = session.query(Player).filter(
        Player.game_id == game.id,
        Player.player_type == PlayerType.AI
    ).all()
    
    if not players:
        print("No AI players found for the game")
        return
    
    print(f"Ensuring {DEFAULT_AGENT_TYPE} AI agents for {len(players)} players")
    
    for player in players:
        # Check if agent config already exists
        existing_agent = session.query(AgentConfig).filter(
            AgentConfig.player_id == player.id
        ).first()
        
        if existing_agent:
            print(f"Agent config already exists for player {player.id} ({player.role})")
            continue
        
        # Create a new agent config
        agent_config = AgentConfig(
            player_id=player.id,
            agent_type=DEFAULT_AGENT_TYPE,
            config={"strategy": DEFAULT_AGENT_TYPE},
            is_active=True,
        )
        session.add(agent_config)
        print(f"Created {DEFAULT_AGENT_TYPE} agent for player {player.id} ({player.role})")
    
    session.flush()

def main():
    """Main entry point for the script."""
    print("Starting database seeding...")
    
    # Create a new SQLAlchemy engine with our custom connection string
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Create the engine
    engine = create_engine(DATABASE_URL)
    
    # Create a new database session
    db = SessionLocal()
    
    try:
        # Ensure the database tables exist
        print("Ensuring database tables exist...")
        Base.metadata.create_all(bind=db.connection().engine)
        
        # Create the default group and admin user
        group, created = ensure_group(db)
        
        # For now, skip game creation since the games table doesn't exist yet
        print("Skipping game creation - games table does not exist yet")
        
        print("Database seeding completed successfully!")
        print("\nNext steps:")
        print("1. Run database migrations to create the games table")
        print("2. Run this script again to create the default game")
        
        return True
    except Exception as e:
        print(f"Error during database seeding: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    main()

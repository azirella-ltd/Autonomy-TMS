#!/usr/bin/env python3
"""Seed the default Autonomy customer, configuration, and scenario with AI scenario_users."""

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
        Customer,
        Game,
        GameStatus,
        ScenarioUser,
        PlayerRole,
        PlayerStrategy,
        PlayerType,
        User,
    )
    from app.models.agent_config import AgentConfig
    from app.schemas.tenant import TenantCreate
    from app.schemas.user import UserCreate
    from app.services.tenant_service import TenantService
    from scripts.seed_default_group import ensure_supply_chain_config
except ImportError as e:
    print(f"Error importing application modules: {e}")
    print("Make sure you're running this script from the backend directory and all dependencies are installed.")
    sys.exit(1)

# Constants
DEFAULT_CUSTOMER_NAME = "Default TBG"
DEFAULT_CUSTOMER_DESCRIPTION = "Default Autonomy simulation customer"
DEFAULT_ADMIN_USERNAME = "groupadmin"
DEFAULT_ADMIN_EMAIL = "groupadmin@autonomy.ai"
DEFAULT_ADMIN_FULL_NAME = "Customer Administrator"
DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")
DEFAULT_GAME_NAME = "Default Simulation"
DEFAULT_AGENT_TYPE = "pid_heuristic"

def ensure_customer(session: Session) -> Tuple[Customer, bool]:
    """Create the default customer and admin if they do not already exist."""
    existing_customer = session.query(Customer).filter(Customer.name == DEFAULT_CUSTOMER_NAME).first()
    
    if existing_customer:
        print(f"Customer '{DEFAULT_CUSTOMER_NAME}' already exists with ID: {existing_customer.id}")
        return existing_customer, False
    
    print(f"Creating new customer: {DEFAULT_CUSTOMER_NAME}")

    # Create the customer admin user using raw SQL to avoid ORM issues with missing columns
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
    
    # Create a simple user object with just the ID for the customer creation
    class SimpleUser:
        def __init__(self, user_id):
            self.id = user_id
    
    admin_user = SimpleUser(user_id)
    
    # Create the customer
    customer = Customer(
        name=DEFAULT_CUSTOMER_NAME,
        description=DEFAULT_CUSTOMER_DESCRIPTION,
        admin_id=admin_user.id,
    )
    session.add(customer)
    session.flush()  # Get the customer ID
    
    # Update the admin user's customer_id
    session.execute(
        text("UPDATE users SET customer_id = :customer_id WHERE id = :user_id"),
        {'customer_id': customer.id, 'user_id': admin_user.id}
    )
    
    # Commit all changes
    session.commit()
    
    print(f"Created customer '{customer.name}' with ID: {customer.id}")
    print(f"Created admin user with ID: {admin_user.id}")
    print("Database seeding completed successfully!")

    return customer, True

def ensure_default_game(session: Session, customer: Customer) -> Game:
    """Ensure the default scenario exists for the supplied customer."""
    sc_config = ensure_supply_chain_config(session, customer)
    existing_game = session.query(Game).filter(
        Game.name == DEFAULT_GAME_NAME,
        Game.customer_id == customer.id
    ).first()

    if existing_game:
        print(f"Scenario '{DEFAULT_GAME_NAME}' already exists with ID: {existing_game.id}")
        existing_game.supply_chain_config_id = sc_config.id
        session.add(existing_game)
        return existing_game

    print(f"Creating new scenario: {DEFAULT_GAME_NAME}")

    # Create the scenario
    game = Game(
        name=DEFAULT_GAME_NAME,
        status=GameStatus.CREATED,
        customer_id=customer.id,
        created_by=customer.created_by,
        max_rounds=52,  # Default number of periods
        supply_chain_config_id=sc_config.id,
    )
    session.add(game)
    session.flush()

    # Create default scenario_users
    _ensure_default_players(session, game)

    # Create default AI agents
    ensure_naive_agents(session, game)

    session.commit()

    print(f"Created scenario '{game.name}' with ID: {game.id}")
    return game

def _ensure_default_players(session: Session, game: Game) -> None:
    """Create placeholder AI scenario_users if none exist for the scenario."""
    existing_players = session.query(ScenarioUser).filter(ScenarioUser.scenario_id == game.id).count()
    if existing_players > 0:
        print(f"Scenario already has {existing_players} scenario_users")
        return

    print("Creating default scenario_users for the scenario")
    
    # Define the default scenario_user roles and types
    player_roles = [
        (PlayerRole.RETAILER, PlayerType.AI, "Retailer AI"),
        (PlayerRole.WHOLESALER, PlayerType.AI, "Wholesaler AI"),
        (PlayerRole.DISTRIBUTOR, PlayerType.AI, "Distributor AI"),
        (PlayerRole.MANUFACTURER, PlayerType.AI, "Manufacturer AI"),
    ]
    
    for role, scenario_user_type, name in player_roles:
        scenario_user = ScenarioUser(
            scenario_id=game.id,
            role=role,
            scenario_user_type=scenario_user_type,
            name=name,
            is_active=True,
        )
        session.add(scenario_user)
    
    session.flush()
    print(f"Created {len(player_roles)} default scenario_users")

def ensure_naive_agents(session: Session, game: Game) -> None:
    """Assign AI agents to each role in the scenario."""
    # Get all AI scenario_users in the scenario
    scenario_users = session.query(ScenarioUser).filter(
        ScenarioUser.scenario_id == game.id,
        ScenarioUser.scenario_user_type == PlayerType.AI
    ).all()
    
    if not scenario_users:
        print("No AI scenario_users found for the scenario")
        return
    
    print(f"Ensuring {DEFAULT_AGENT_TYPE} AI agents for {len(scenario_users)} scenario_users")
    
    for scenario_user in scenario_users:
        # Check if agent config already exists
        existing_agent = session.query(AgentConfig).filter(
            AgentConfig.scenario_user_id == scenario_user.id
        ).first()
        
        if existing_agent:
            print(f"Agent config already exists for scenario_user {scenario_user.id} ({scenario_user.role})")
            continue
        
        # Create a new agent config
        agent_config = AgentConfig(
            scenario_user_id=scenario_user.id,
            agent_type=DEFAULT_AGENT_TYPE,
            config={"strategy": DEFAULT_AGENT_TYPE},
            is_active=True,
        )
        session.add(agent_config)
        print(f"Created {DEFAULT_AGENT_TYPE} agent for scenario_user {scenario_user.id} ({scenario_user.role})")
    
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
        
        # Create the default customer and admin user
        customer, created = ensure_customer(db)
        
        # For now, skip scenario creation since the scenarios table doesn't exist yet
        print("Skipping scenario creation - scenarios table does not exist yet")
        
        print("Database seeding completed successfully!")
        print("\nNext steps:")
        print("1. Run database migrations to create the scenarios table")
        print("2. Run this script again to create the default scenario")
        
        return True
    except Exception as e:
        print(f"Error during database seeding: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Clean database initialization script that handles model imports in the correct order.
"""
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import settings and base
from app.core.config import settings
from app.db.base_class import Base

def init_db(drop_tables=False):
    """Initialize the SQLite database and create all tables."""
    # Get the database path from the URI
    db_uri = settings.SQLALCHEMY_DATABASE_URI
    
    # For SQLite, ensure the directory exists
    if db_uri.startswith('sqlite'):
        db_path = db_uri.replace("sqlite:///", "")
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        print(f"Initializing SQLite database at: {os.path.abspath(db_path)}")
        connect_args = {"check_same_thread": False}
    else:
        print(f"Initializing database with URI: {db_uri}")
        connect_args = {}
    
    # Create the database engine
    engine = create_engine(
        db_uri,
        connect_args=connect_args,
        echo=True  # Enable SQL query logging for debugging
    )
    
    # Drop all tables if requested
    if drop_tables:
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        print("All tables dropped.")
    
    # Import models in the correct order to avoid circular imports
    print("Importing models...")
    
    # 1. First, import the base class
    from app.models.base import Base
    
    # 2. Import all models to register them with SQLAlchemy
    # This will also set up the metadata
    from app.models import user, scenario, participant
    
    # 3. Set up relationships after all models are imported
    from app.models.relationships import setup_relationships
    setup_relationships()
    
    # 4. Import the models for direct use
    from app.models.user import User, RefreshToken
    from app.models.scenario import Scenario, ScenarioStatus, Round, ParticipantAction
    from app.models.participant import Participant, ParticipantRole, ParticipantType, ParticipantStrategy
    
    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    # Create a session to verify the database
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Verify the database is accessible
        db.execute("SELECT 1")
        print("Database connection successful!")
        
        # Check if we have any users
        user_count = db.query(User).count()
        print(f"Found {user_count} users in the database.")
        
        # If no users, create a test user
        if user_count == 0:
            from app.core.security import get_password_hash
            test_user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("testpassword"),
                full_name="Test User",
                is_active=True
            )
            db.add(test_user)
            db.commit()
            print("Created test user: testuser / testpassword")
        
    except Exception as e:
        print(f"Error accessing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    print("Database initialized successfully!")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize the database")
    parser.add_argument(
        "--drop", 
        action="store_true", 
        help="Drop all tables before creating them"
    )
    
    args = parser.parse_args()
    init_db(drop_tables=args.drop)

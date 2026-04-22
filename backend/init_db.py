import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent))

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker

# Import settings and base
from app.core.config import settings
from app.db.base_class import Base

# Import models in the correct order to avoid circular dependencies
from app.models.base import Base
from app.models.user import User, RefreshToken
from app.models.scenario import Scenario, ScenarioStatus, Period, ParticipantAction
from app.models.participant import Participant, ParticipantRole, ParticipantType, ParticipantStrategy

# Import all models to ensure they're registered with SQLAlchemy
import app.models

# Set up all relationships
app.models.relationships.setup_relationships()

def drop_all_tables(engine):
    """Drop all tables in the database."""
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("All tables dropped.")

def init_db(drop_tables=False):
    """Initialize the database and create all tables."""
    db_uri = settings.SQLALCHEMY_DATABASE_URI
    print(f"Initializing database with URI: {db_uri}")
    connect_args = {}
    
    # Create the database engine with a larger pool size and timeout
    engine = create_engine(
        db_uri,
        connect_args=connect_args,
        echo=True,  # Enable SQL query logging for debugging
        pool_size=5,
        max_overflow=10,
        pool_timeout=30
    )
    
    # Drop all tables if requested
    if drop_tables:
        drop_all_tables(engine)
    
    # Create all tables in the correct order
    print("Creating database tables...")
    
    # Create all tables at once - SQLAlchemy will handle the order
    # based on the foreign key dependencies
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    # Create a session to verify the database
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Verify the database is accessible
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        print("Database connection successful!")
        
        # Check if we have any users
        user_count = db.query(User).count()
        print(f"Found {user_count} users in the database.")
        
        # If no users, attempt to create a system administrator user
        if user_count == 0:
            try:
                from app.core.security import get_password_hash
            except ModuleNotFoundError as exc:
                print(
                    "Skipping default admin creation because dependencies are missing:"
                    f" {exc}"
                )
            else:
                test_user = User(
                    username="systemadmin",
                    email="systemadmin@autonomy.ai",
                    hashed_password=get_password_hash(os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")),
                    full_name="System Admin",
                    is_active=True,
                    is_superuser=True
                )
                db.add(test_user)
                db.commit()
                print(
                    "Created system administrator user: systemadmin@autonomy.ai / Autonomy@2026"
                )
        
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

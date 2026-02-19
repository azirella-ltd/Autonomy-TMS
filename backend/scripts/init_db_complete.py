import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.db_urls import resolve_sync_database_url
from app.db.base_class import Base
from app.models.user import User
from app.core.security import get_password_hash

# Import all models to ensure they are registered with SQLAlchemy
from app.models import user, game, player, player_action, refresh_token
from app.models.supply_chain import Round  # Import Round from supply_chain

def init_db():
    print("Creating database tables...")
    
    db_url = resolve_sync_database_url()
    
    # Create database engine with connection pooling
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=5,
        max_overflow=10
    )
    
    print(f"Initializing database at: {db_url}")
    print("Creating test user...")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Create test user
        test_user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("testpassword"),
            full_name="Test User",
            is_active=True,
            is_superuser=False
        )
        db.add(test_user)
        db.commit()
        print("Test user created successfully!")
        print(f"Username: testuser")
        print(f"Password: testpassword")
    except Exception as e:
        print(f"Error creating test user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initializing database...")
    print(f"Using database: {settings.SQLALCHEMY_DATABASE_URI}")
    init_db()
    print("Database initialization complete!")

import sys
import os
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.db_urls import resolve_sync_database_url
from app.models.user import User, Base
from app.core.security import get_password_hash

def init_db():
    SQLALCHEMY_DATABASE_URI = resolve_sync_database_url()
    
    # Create database engine with connection pooling
    engine = create_engine(
        SQLALCHEMY_DATABASE_URI,
        pool_pre_ping=True,
        pool_recycle=3600
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    # Create test user if it doesn't exist
    test_user = db.query(User).filter(User.email == "test@example.com").first()
    if not test_user:
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=get_password_hash("testpassword"),
            full_name="Test User",
            is_active=True
        )
        db.add(user)
        db.commit()
        print("Test user created successfully!")
    else:
        print("Test user already exists!")
    
    db.close()

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Database initialization complete!")

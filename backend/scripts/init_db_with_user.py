import sys
import os
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.db.session import engine, Base, SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def init_db():
    """Initialize the database with required tables and a test user."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Creating test user...")
    db = SessionLocal()
    try:
        # Check if test user already exists
        user = db.query(User).filter(User.email == "test@example.com").first()
        if not user:
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
        else:
            print("Test user already exists.")
    except Exception as e:
        print(f"Error creating test user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Database initialization complete!")

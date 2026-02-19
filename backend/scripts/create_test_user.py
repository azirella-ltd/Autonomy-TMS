import sys
from pathlib import Path
from datetime import datetime

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import Table, MetaData, select
from sqlalchemy.orm import Session
from app.core.security import get_password_hash
from app.db.session import SessionLocal, engine
from app.db.base import Base

def create_test_user():
    db = SessionLocal()
    try:
        # Reflect the database tables
        metadata = MetaData()
        metadata.reflect(bind=engine)
        users_table = Table('users', metadata, autoload_with=engine)
        
        # Check if test user already exists
        with engine.connect() as conn:
            stmt = select(users_table).where(users_table.c.email == "test@example.com")
            result = conn.execute(stmt).first()
            
            if result:
                print("Test user already exists:")
                print(f"Username: {result.username}")
                print(f"Email: {result.email}")
                return
        
        # Create admin user data
        user_data = {
            'username': 'admin',
            'email': 'admin@example.com',
            'hashed_password': get_password_hash('adminpassword'),
            'full_name': 'Admin User',
            'is_active': True,
            'is_superuser': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert the test user
        with engine.connect() as conn:
            result = conn.execute(users_table.insert().values(**user_data))
            conn.commit()
            
            # Get the created user
            stmt = select(users_table).where(users_table.c.email == "test@example.com")
            db_user = conn.execute(stmt).first()
        
        print("Test user created successfully:")
        print(f"ID: {db_user.id}")
        print(f"Username: {db_user.username}")
        print(f"Email: {db_user.email}")
        
    except Exception as e:
        print(f"Error creating test user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Creating test user...")
    create_test_user()

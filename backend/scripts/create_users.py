import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import Base
from app.models.user import User
from scripts.seed_default_group import SeedOptions, seed_default_data
from app.core.db_urls import resolve_sync_database_url

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def get_or_create_systemadmin(session):
    user = session.query(User).filter(User.email == "systemadmin@autonomy.ai").first()
    if user:
        print("System administrator user already exists")
        return user
    user = User(
        username="systemadmin",
        email="systemadmin@autonomy.ai",
        hashed_password=hash_password(os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")),
        full_name="System Admin",
        is_active=True,
        is_superuser=True,
        last_login=datetime.utcnow(),
    )
    session.add(user)
    return user

def main():
    SQLALCHEMY_DATABASE_URL = resolve_sync_database_url()
    print(f"Using database: {SQLALCHEMY_DATABASE_URL}")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        systemadmin = get_or_create_systemadmin(db)
        seed_default_data(db, SeedOptions())
        db.commit()
        print(f"System administrator user ready: {systemadmin.email}")
    except Exception as e:
        print(f"Error creating system administrator: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()

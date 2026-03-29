import sys
import os
import datetime
from pathlib import Path
from enum import Enum as PyEnum

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Float, JSON
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import settings
from app.core.security import get_password_hash

# Create a base class for our models (local to this legacy script)
Base = declarative_base()

# Enums
class ScenarioStatus(str, PyEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"

class ScenarioUserRole(str, PyEnum):
    RETAILER = "retailer"
    WHOLESALER = "wholesaler"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"

# Models (local lightweight definitions for legacy init_db only)
class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    status = Column(Enum(ScenarioStatus), default=ScenarioStatus.CREATED)
    current_period = Column(Integer, default=0)
    max_periods = Column(Integer, default=52)
    demand_pattern = Column(JSON, default={
        "type": "classic",
        "params": {"initial_demand": 4, "change_week": 6, "final_demand": 8}
    })
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    scenario_users = relationship("ScenarioUser", back_populates="scenario")

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(100), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ScenarioUser(Base):
    __tablename__ = "scenario_users"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    user_id = Column(Integer, nullable=True)
    role = Column(Enum(ScenarioUserRole), nullable=False)
    name = Column(String(100), nullable=False)
    is_ai = Column(Boolean, default=False)

    scenario = relationship("Scenario", back_populates="scenario_users")

def init_db():
    try:
        from app.core.db_urls import resolve_sync_database_url
        SQLALCHEMY_DATABASE_URI = resolve_sync_database_url()
        print(f"Connecting to database at: {SQLALCHEMY_DATABASE_URI}")
        
        # Create database engine with connection pooling
        engine = create_engine(
            SQLALCHEMY_DATABASE_URI,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10
        )
        
        # Drop all tables first to ensure a clean slate
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        
        # Create all tables
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        
        # Create a session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Create default system administrator if it doesn't exist
        default_users = [
            {
                "username": "systemadmin",
                "email": "systemadmin@autonomy.ai",
                "password": os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026"),
                "full_name": "System Admin",
                "is_superuser": True,
                "is_active": True
            }
        ]

        print("Creating default users...")
        for user_data in default_users:
            user = db.query(User).filter(User.email == user_data["email"]).first()
            if not user:
                user = User(
                    username=user_data["username"],
                    email=user_data["email"],
                    hashed_password=get_password_hash(user_data["password"]),
                    full_name=user_data["full_name"],
                    is_superuser=user_data["is_superuser"],
                    is_active=user_data["is_active"]
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Created user: {user.email} (ID: {user.id})")
            else:
                print(f"User already exists: {user.email}")
        
        # Verify the users were created
        print("\nVerifying users in database:")
        users = db.query(User).all()
        for u in users:
            print(f"- {u.username} ({u.email}) - {'Admin' if u.is_superuser else 'User'}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Initializing database...")
    if init_db():
        print("✅ Database initialization completed successfully!")
    else:
        print("❌ Database initialization failed!")

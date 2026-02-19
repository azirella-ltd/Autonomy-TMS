import sys
import os
import datetime
from pathlib import Path
from enum import Enum as PyEnum

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Float, JSON
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import settings
from app.core.security import get_password_hash

# Create a base class for our models
Base = declarative_base()

# Enums
class GameStatus(str, PyEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"

class PlayerRole(str, PyEnum):
    RETAILER = "retailer"
    WHOLESALER = "wholesaler"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"

# Models
class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    status = Column(Enum(GameStatus), default=GameStatus.CREATED)
    current_round = Column(Integer, default=0)
    max_rounds = Column(Integer, default=52)
    demand_pattern = Column(JSON, default={
        "type": "classic",
        "params": {
            "initial_demand": 4,
            "change_week": 6,
            "final_demand": 8
        }
    })
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    players = relationship("Player", back_populates="game")
    rounds = relationship("GameRound", back_populates="game")
    users = relationship("User", secondary="user_games", back_populates="games")

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
    
    # Relationships
    games = relationship("Game", secondary="user_games", back_populates="users")

# Association table for many-to-many relationship between users and games
user_games = Table(
    'user_games',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('game_id', Integer, ForeignKey('games.id'), primary_key=True)
)

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    user_id = Column(Integer, nullable=True)  # Null for AI players
    role = Column(Enum(PlayerRole), nullable=False)
    name = Column(String(100), nullable=False)
    is_ai = Column(Boolean, default=False)
    
    # Relationships
    game = relationship("Game", back_populates="players")
    inventory = relationship("PlayerInventory", back_populates="player", uselist=False)
    orders = relationship("Order", back_populates="player")
    player_rounds = relationship("PlayerRound", back_populates="player")

class PlayerInventory(Base):
    __tablename__ = "player_inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    current_stock = Column(Integer, default=12)
    incoming_shipments = Column(JSON, default=[])
    backorders = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    
    # Relationships
    player = relationship("Player", back_populates="inventory")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="orders")
    game = relationship("Game")

class GameRound(Base):
    __tablename__ = "game_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    customer_demand = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    game = relationship("Game", back_populates="rounds")
    player_rounds = relationship("PlayerRound", back_populates="game_round")

class PlayerRound(Base):
    __tablename__ = "player_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    round_id = Column(Integer, ForeignKey("game_rounds.id"), nullable=False)
    order_placed = Column(Integer, nullable=False)
    order_received = Column(Integer, nullable=False)
    inventory_before = Column(Integer, nullable=False)
    inventory_after = Column(Integer, nullable=False)
    backorders_before = Column(Integer, default=0)
    backorders_after = Column(Integer, default=0)
    holding_cost = Column(Float, default=0.0)
    backorder_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    
    # Relationships
    player = relationship("Player", back_populates="player_rounds")
    game_round = relationship("GameRound", back_populates="player_rounds")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    unit_cost = Column(Float, default=0.0)

class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    parameters = Column(JSON)  # Store simulation parameters
    
    # Relationships
    steps = relationship("SimulationStep", back_populates="simulation_run")

class SimulationStep(Base):
    __tablename__ = "simulation_steps"
    
    id = Column(Integer, primary_key=True, index=True)
    simulation_run_id = Column(Integer, ForeignKey("simulation_runs.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    state = Column(JSON)  # Store the state of the simulation at this step
    
    # Relationships
    simulation_run = relationship("SimulationRun", back_populates="steps")

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
                "password": "Autonomy@2025",
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

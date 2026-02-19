from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import event
from typing import Generator

from ..core.config import settings

# Create database engine with connection pooling
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_size=5,        # Number of connections to keep open
    max_overflow=10,    # Max number of connections to create beyond pool_size
    pool_timeout=30,    # Max seconds to wait for a connection from the pool
    echo_pool=True      # Log connection pool events for debugging
)

# Create session factory with configuration
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Base class for all models
Base = declarative_base()

# Dependency to get DB session
def get_db() -> Generator:
    """
    Dependency function that yields database sessions.
    
    Handles session lifecycle including proper cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

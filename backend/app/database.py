from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.db_urls import resolve_async_database_url

# Create async engine
engine = create_async_engine(
    resolve_async_database_url(),
    echo=True,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
    poolclass=NullPool
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()

# Dependency to get DB session
async def get_db() -> AsyncSession:
    """
    Dependency function that yields db sessions
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

# For compatibility with existing code
SessionLocal = async_session_factory

import logging
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from settings
from app.core.config import settings
from app.core.db_urls import resolve_async_database_url

# Log the database connection details for debugging
raw_database_uri = settings.SQLALCHEMY_DATABASE_URI
logger.info("Using database URL from settings: %s", raw_database_uri)
db_url = make_url(raw_database_uri)
logger.info("Connecting to database with URL: %s", raw_database_uri)

is_postgresql = db_url.get_backend_name().startswith("postgresql")

if is_postgresql:
    # Use the centralized async URL resolver for PostgreSQL
    async_database_uri = resolve_async_database_url()
    sync_database_uri = raw_database_uri
    async_connect_args = {"timeout": 10}
    sync_connect_args = {"connect_timeout": 10}
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }
    logger.info("Using PostgreSQL with asyncpg driver: %s", async_database_uri.split('@')[-1] if '@' in async_database_uri else async_database_uri)
else:
    # MySQL/MariaDB (legacy support)
    async_database_uri = raw_database_uri.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
    sync_database_uri = raw_database_uri
    async_connect_args = {"connect_timeout": 10, "ssl": False}
    sync_connect_args = {"connect_timeout": 10, "ssl": False}
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }

engine = create_async_engine(
    async_database_uri,
    echo=True,
    future=True,
    connect_args=async_connect_args,
    **engine_kwargs,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

sync_engine = create_engine(
    sync_database_uri,
    connect_args=sync_connect_args,
    **engine_kwargs,
)

# Synchronous session factory for services that require sync db access
from sqlalchemy.orm import sessionmaker, Session
sync_session_factory = sessionmaker(bind=sync_engine, expire_on_commit=False)

# For backward compatibility with code that expects a synchronous session
SessionLocal = async_session_factory


def get_sync_db():
    """
    Dependency function that yields synchronous db sessions.
    Use this for services that require sync SQLAlchemy patterns (db.query()).
    """
    db = sync_session_factory()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


# Dependency to get DB session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that yields db sessions
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            await session.close()

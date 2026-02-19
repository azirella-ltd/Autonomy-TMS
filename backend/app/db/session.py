import logging
import os
from pathlib import Path
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

is_sqlite = db_url.get_backend_name().startswith("sqlite")
is_postgresql = db_url.get_backend_name().startswith("postgresql")

aiosqlite_available = True
if is_sqlite:
    try:  # pragma: no cover - optional dependency check
        import aiosqlite  # type: ignore  # noqa: F401
    except ModuleNotFoundError:
        aiosqlite_available = False
        logger.warning(
            "aiosqlite is not installed; async DB support will be disabled for the SQLite fallback."
        )

if is_sqlite and db_url.database:
    sqlite_path = Path(db_url.database)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

if is_sqlite:
    async_database_uri = raw_database_uri.replace("sqlite://", "sqlite+aiosqlite://", 1)
    sync_database_uri = raw_database_uri
    async_connect_args = {"check_same_thread": False}
    sync_connect_args = {"check_same_thread": False}
    engine_kwargs = {}
elif is_postgresql:
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

engine = None
async_session_factory = None

if (not is_sqlite) or aiosqlite_available:
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

from app.models.base import Base

if is_sqlite and not os.getenv("ALEMBIC_SKIP_SQLITE_CREATE"):
    Base.metadata.create_all(bind=sync_engine)

# Dependency to get DB session
if async_session_factory is None:

    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        """Raise a helpful error when async DB access is unavailable."""
        raise RuntimeError(
            "Async database support requires the 'aiosqlite' package when using the SQLite fallback."
        )

else:

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

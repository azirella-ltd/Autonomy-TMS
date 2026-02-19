"""Central helpers for resolving database URLs across environments."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional
import logging

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
DEFAULT_SQLITE_PATH = DATA_DIR / "autonomy_dev.db"


def _can_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    """Test if we can connect to a host:port."""
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _postgres_url(*, driver: str, user: str, password: str, host: str, port: int, db: str) -> str:
    """Construct PostgreSQL connection URL."""
    return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{db}"


def _mysql_url(*, driver: str, user: str, password: str, host: str, port: int, db: str) -> str:
    """Construct MySQL/MariaDB connection URL."""
    return f"mysql+{driver}://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"


def resolve_sync_database_url() -> str:
    """
    Return the authoritative synchronous SQLAlchemy URL.

    Priority:
    1. Explicit DATABASE_URL or SQLALCHEMY_DATABASE_URI
    2. DATABASE_TYPE environment variable (postgresql, mysql, mariadb)
    3. Auto-detect based on available environment variables
    4. Fallback to SQLite for development
    """

    # 1. Check for explicit URL
    for key in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI"):
        token = os.getenv(key)
        if token and token.strip():
            logger.info(f"Using explicit {key}")
            return token.strip()

    # 2. Check DATABASE_TYPE
    db_type = os.getenv("DATABASE_TYPE", "").lower()

    # 3. PostgreSQL configuration
    if db_type == "postgresql" or os.getenv("POSTGRESQL_HOST") or os.getenv("POSTGRES_HOST"):
        server = (
            os.getenv("POSTGRESQL_HOST")
            or os.getenv("POSTGRES_HOST")
            or ("db" if os.getenv("DOCKER_COMPOSE") else "127.0.0.1")
        )
        port = int(
            os.getenv("POSTGRESQL_PORT")
            or os.getenv("POSTGRES_PORT")
            or 5432
        )
        user = (
            os.getenv("POSTGRESQL_USER")
            or os.getenv("POSTGRES_USER")
            or "autonomy_user"
        )
        password = (
            os.getenv("POSTGRESQL_PASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
            or "autonomy_password"
        )
        database = (
            os.getenv("POSTGRESQL_DATABASE")
            or os.getenv("POSTGRES_DB")
            or "autonomy"
        )
        driver = "psycopg2"

        encoded_password = quote_plus(password)
        if _can_connect(server, port):
            logger.info(f"Using PostgreSQL at {server}:{port}/{database}")
            return _postgres_url(
                driver=driver,
                user=user,
                password=encoded_password,
                host=server,
                port=port,
                db=database,
            )

    # 4. MySQL/MariaDB configuration (legacy support)
    if db_type in ("mysql", "mariadb") or os.getenv("MARIADB_HOST") or os.getenv("MYSQL_HOST"):
        server = (
            os.getenv("MYSQL_SERVER")
            or os.getenv("MYSQL_HOST")
            or os.getenv("MARIADB_HOST")
            or ("db" if os.getenv("DOCKER_COMPOSE") else "127.0.0.1")
        )
        port = int(os.getenv("MYSQL_PORT") or os.getenv("MARIADB_PORT") or 3306)
        user = os.getenv("MYSQL_USER") or os.getenv("MARIADB_USER") or "autonomy_user"
        password = os.getenv("MYSQL_PASSWORD") or os.getenv("MARIADB_PASSWORD") or "autonomy_password"
        database = (
            os.getenv("MYSQL_DB")
            or os.getenv("MYSQL_DATABASE")
            or os.getenv("MARIADB_DATABASE")
            or "autonomy"
        )
        driver = "pymysql"

        encoded_password = quote_plus(password)
        if _can_connect(server, port):
            logger.info(f"Using MySQL/MariaDB at {server}:{port}/{database}")
            return _mysql_url(
                driver=driver,
                user=user,
                password=encoded_password,
                host=server,
                port=port,
                db=database,
            )

    # 5. Fallback to SQLite for development
    logger.warning("No database connection available, falling back to SQLite")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def resolve_async_database_url() -> str:
    """
    Return the asynchronous SQLAlchemy URL.

    Converts synchronous drivers to their async equivalents:
    - psycopg2 → asyncpg
    - pymysql → aiomysql
    - sqlite → aiosqlite
    """
    explicit = os.getenv("ASYNC_DATABASE_URL")
    if explicit and explicit.strip():
        logger.info("Using explicit ASYNC_DATABASE_URL")
        return explicit.strip()

    sync_url = resolve_sync_database_url()

    # Convert sync drivers to async drivers
    if sync_url.startswith("postgresql+psycopg2://"):
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        logger.info("Converted psycopg2 to asyncpg for async operations")
        return async_url

    if sync_url.startswith("mysql+pymysql://"):
        async_url = sync_url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
        logger.info("Converted pymysql to aiomysql for async operations")
        return async_url

    if sync_url.startswith("sqlite:///"):
        async_url = sync_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        logger.info("Converted sqlite to aiosqlite for async operations")
        return async_url

    return sync_url


# Backwards compatibility aliases
get_database_url = resolve_sync_database_url
get_async_database_url = resolve_async_database_url

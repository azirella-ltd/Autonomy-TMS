"""
Separate database session for the Knowledge Base (RAG) pgvector database.

If KB_ASYNC_DATABASE_URL is configured, KB operations use a dedicated
PostgreSQL instance with pgvector. Otherwise, falls back to the main database.

Provides both async (FastAPI endpoints) and sync (APScheduler background jobs)
session factories.
"""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Lazy-initialized — populated by init_kb_engine()
_kb_engine = None
_kb_session_factory = None
_kb_sync_engine = None
_kb_sync_session_factory = None


def _derive_sync_url(async_url: str) -> str:
    """Convert an asyncpg URL to a psycopg2 URL for sync access.

    postgresql+asyncpg://... → postgresql+psycopg2://...
    """
    return async_url.replace("+asyncpg", "+psycopg2")


def init_kb_engine() -> None:
    """Create the KB async and sync engines and session factories from settings.

    Called once during application startup.
    """
    global _kb_engine, _kb_session_factory, _kb_sync_engine, _kb_sync_session_factory

    from app.core.config import settings

    kb_url = settings.KB_ASYNC_DATABASE_URL
    if not kb_url:
        logger.info("KB_ASYNC_DATABASE_URL not set — KB will use main database")
        return

    logger.info(
        "Initializing KB database engine: %s",
        kb_url.split("@")[-1] if "@" in kb_url else kb_url,
    )

    # Async engine (FastAPI endpoints, service-to-service calls)
    _kb_engine = create_async_engine(
        kb_url,
        echo=False,
        future=True,
        connect_args={"timeout": 10},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=3,
        max_overflow=5,
    )

    _kb_session_factory = async_sessionmaker(
        bind=_kb_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    # Sync engine (APScheduler background jobs: outcome collection, CDT calibration)
    sync_url = settings.KB_DATABASE_URL or _derive_sync_url(kb_url)
    _kb_sync_engine = create_engine(
        sync_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=2,
        max_overflow=3,
    )

    _kb_sync_session_factory = sessionmaker(
        bind=_kb_sync_engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def init_kb_tables() -> None:
    """Create KB tables in the separate database (idempotent).

    Uses KBBase.metadata so only KB tables are created,
    never touching the main database schema.
    """
    init_kb_engine()

    if _kb_engine is None:
        logger.warning("KB engine not available — skipping KB table creation")
        return

    from app.models.knowledge_base import KBBase

    async with _kb_engine.begin() as conn:
        await conn.run_sync(KBBase.metadata.create_all)

    logger.info("KB tables created/verified in separate database")


@asynccontextmanager
async def get_kb_session():
    """Standalone KB session for use outside FastAPI endpoints.

    Use this when you need a KB session without FastAPI dependency injection,
    e.g. from service-to-service calls like RAG context retrieval.
    """
    global _kb_session_factory

    if _kb_session_factory is None:
        init_kb_engine()
    if _kb_session_factory is None:
        raise RuntimeError("KB database not configured (KB_ASYNC_DATABASE_URL not set)")

    session = _kb_session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_kb_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a KB database session.

    The service layer (KnowledgeBaseService) manages its own commits.
    This dependency only provides the session and handles cleanup.
    Falls back to the main async session if no separate KB database is configured.
    """
    if _kb_session_factory is not None:
        session = _kb_session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    else:
        # Fallback to main database
        from app.db.session import get_db

        async for session in get_db():
            yield session


@contextmanager
def get_sync_kb_session() -> Generator[Session, None, None]:
    """Synchronous KB session for APScheduler background jobs.

    Used by OutcomeCollectorService.collect_skill_outcomes() and other
    sync background tasks that query decision_embeddings on the KB database.
    Falls back to the main sync session if no separate KB database is configured.
    """
    global _kb_sync_session_factory

    if _kb_sync_session_factory is None:
        init_kb_engine()

    if _kb_sync_session_factory is not None:
        session = _kb_sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    else:
        # Fallback to main database sync session
        from app.db.session import sync_session_factory

        session = sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

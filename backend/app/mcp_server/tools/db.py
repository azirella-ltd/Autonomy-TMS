"""
Database session helper for MCP server tools.

Each tool call gets its own async session via this helper.
Tenant isolation is enforced by requiring tenant_id on every call.
"""

from contextlib import asynccontextmanager

from app.db.session import async_session_factory


@asynccontextmanager
async def get_db():
    """Provide an async DB session for a single tool call."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

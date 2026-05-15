"""DB session helper for TMS MCP server tools.

Each tool call opens its own async session via :func:`get_db`. Tenant
isolation is enforced at the *session* level: ``get_db`` reads the
JWT claims that :mod:`autonomy_app.mcp_auth` middleware stashed into
:data:`autonomy_app.mcp_auth.mcp_auth_var`, resolves the user via the
``auth.find_user_by_*`` SECURITY DEFINER helpers, and sets the
``app.user_id`` / ``app.tenant_id`` / ``app.config_id`` PostgreSQL
session vars before yielding the session. RLS policies on tenant-
scoped tables key off those vars, so the tool body runs inside a
session that is correctly tenant-scoped — without any need for the
tool to take ``tenant_id`` as a parameter.

Tools that still accept ``config_id`` (because the user has multiple
configs and the caller picks one) MUST verify it belongs to the
authenticated tenant via :func:`require_config` before using it.
"""

from contextlib import asynccontextmanager

from app.db.session import async_session_factory
from autonomy_app.mcp_auth import (
    McpResolvedUser,
    ensure_tenant_owns_config,
    resolve_mcp_user,
)


@asynccontextmanager
async def get_db():
    """Open a tenant-bound async DB session for a single MCP tool call.

    Yields ``(session, McpResolvedUser)`` — the session has
    ``app.tenant_id`` / ``app.config_id`` / ``app.user_id`` already
    set, and the resolved-user record is handy for tools that need
    the canonical tenant_id / config_id without re-querying.
    """
    async with async_session_factory() as session:
        try:
            user: McpResolvedUser = await resolve_mcp_user(session)
            yield session, user
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def require_config(session, user: McpResolvedUser, config_id: int) -> int:
    """Validate that ``config_id`` belongs to the authenticated tenant.

    Returns ``config_id`` on success so callers can use it inline.
    Raises :class:`PermissionError` if the config is unowned or the
    request has no tenant binding.
    """
    if user.tenant_id is None:
        raise PermissionError(
            "MCP request has no tenant binding; cannot validate config_id"
        )
    await ensure_tenant_owns_config(session, user.tenant_id, config_id)
    return int(config_id)

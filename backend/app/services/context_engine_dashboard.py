"""Shared helpers for the Context Engine admin dashboard.

The Context Engine page aggregates status for several external context
sources (Knowledge Base, Email Signals, Slack Signals, Market Intelligence).
Each source's dashboard endpoint follows a common contract so the frontend
can render consistent state badges (not_configured / inactive / active / error)
and show which SC config the status belongs to.

Every dashboard response returned to the Context Engine page must include:
    - is_configured: bool   — admin has set this feature up (config rows exist)
    - is_active:     bool   — setup is enabled and producing signals
    - active_config_id:   int | None
    - active_config_name: str | None

The `config_id` scoping matters for multi-config tenants: signals for a
learning/training config must not leak into the production config's
Context Engine view, and vice versa.
"""

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


async def resolve_active_config_async(
    db: AsyncSession, tenant_id: int,
) -> Tuple[Optional[int], Optional[str]]:
    """Return (config_id, config_name) for the tenant's active SC config.

    Returns (None, None) if the tenant has no active config — in which case
    every Context Engine source resolves to not_configured regardless of
    underlying data.
    """
    row = (
        await db.execute(
            _text("""
                SELECT id, name FROM supply_chain_configs
                WHERE tenant_id = :tid AND is_active = true
                ORDER BY id DESC LIMIT 1
            """),
            {"tid": tenant_id},
        )
    ).fetchone()
    if not row:
        return None, None
    return int(row[0]), str(row[1]) if row[1] else None


def resolve_active_config_sync(
    db: Session, tenant_id: int,
) -> Tuple[Optional[int], Optional[str]]:
    """Sync counterpart of resolve_active_config_async."""
    row = db.execute(
        _text("""
            SELECT id, name FROM supply_chain_configs
            WHERE tenant_id = :tid AND is_active = true
            ORDER BY id DESC LIMIT 1
        """),
        {"tid": tenant_id},
    ).fetchone()
    if not row:
        return None, None
    return int(row[0]), str(row[1]) if row[1] else None


def context_engine_envelope(
    config_id: Optional[int],
    config_name: Optional[str],
    is_configured: bool,
    is_active: bool,
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the standard envelope the Context Engine frontend expects.

    `metrics` is a flat dict of feature-specific fields that the frontend
    already renders (e.g., active_connections, signals_last_7d). The envelope
    wraps them with the canonical state flags.
    """
    return {
        "is_configured": is_configured,
        "is_active": is_active,
        "active_config_id": config_id,
        "active_config_name": config_name,
        **metrics,
    }

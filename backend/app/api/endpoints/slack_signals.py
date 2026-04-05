"""Slack Signal API endpoints — Supply chain signal intelligence from Slack channels.

Manages Slack connections (webhook/bot) and the resulting supply chain signals.
Signals are classified by LLM, routed to TRMs, and surfaced in Decision Stream.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_async_db
from app.models.user import User
from app.services.slack_signal_service import SlackSignalService

router = APIRouter(prefix="/slack-signals", tags=["Slack Signals"])
logger = logging.getLogger(__name__)


# ── Request / Response models ────────────────────────────────────────────────

class ConnectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connection_type: str = Field(..., pattern="^(webhook|bot)$")
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    channel_names: Optional[List[str]] = None
    allowed_signal_types: Optional[List[str]] = None
    poll_interval_minutes: int = 5
    auto_route_enabled: bool = True
    min_confidence_to_route: float = 0.6


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    channel_names: Optional[List[str]] = None
    allowed_signal_types: Optional[List[str]] = None
    poll_interval_minutes: Optional[int] = None
    auto_route_enabled: Optional[bool] = None
    min_confidence_to_route: Optional[float] = None
    is_active: Optional[bool] = None


class DismissRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


class ManualIngestRequest(BaseModel):
    connection_id: int
    channel_id: str = Field(..., min_length=1)
    channel_name: Optional[str] = None
    message_ts: str = Field(..., min_length=1)
    sender_name: Optional[str] = None
    text: str = Field(..., min_length=1)
    thread_ts: Optional[str] = None


# ── Connection endpoints ─────────────────────────────────────────────────────

@router.get("/connections")
async def list_connections(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """List Slack connections for the current tenant."""
    service = SlackSignalService(db, current_user.tenant_id)
    connections = await service.get_connections()
    return [c.to_dict() for c in connections]


@router.post("/connections")
async def create_connection(
    request: ConnectionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Create a new Slack connection."""
    service = SlackSignalService(db, current_user.tenant_id)
    conn = await service.create_connection(request.model_dump())
    await db.commit()
    return conn.to_dict()


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: int,
    request: ConnectionUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Update a Slack connection."""
    service = SlackSignalService(db, current_user.tenant_id)
    try:
        conn = await service.update_connection(connection_id, request.model_dump(exclude_unset=True))
        await db.commit()
        return conn.to_dict()
    except ValueError:
        raise HTTPException(status_code=404, detail="Connection not found")


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Delete a Slack connection."""
    service = SlackSignalService(db, current_user.tenant_id)
    deleted = await service.delete_connection(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.commit()
    return {"status": "deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Test a Slack connection (validates bot token or webhook URL)."""
    service = SlackSignalService(db, current_user.tenant_id)
    return await service.test_connection(connection_id)


@router.post("/connections/{connection_id}/poll")
async def trigger_poll(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Manually trigger a poll for new Slack messages (bot mode only)."""
    service = SlackSignalService(db, current_user.tenant_id)
    result = await service.poll_channels(connection_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Signal endpoints ─────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    config_id: Optional[int] = None,
    status: Optional[str] = None,
    signal_type: Optional[str] = None,
    channel_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List Slack signals for the current tenant."""
    service = SlackSignalService(db, current_user.tenant_id)
    signals = await service.get_signals(
        config_id=config_id,
        status=status,
        signal_type=signal_type,
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )
    return [s.to_dict() for s in signals]


@router.get("/signals/{signal_id}")
async def get_signal(
    signal_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a single Slack signal by ID."""
    from app.models.slack_signal import SlackSignal
    signal = await db.get(SlackSignal, signal_id)
    if not signal or signal.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal.to_dict()


@router.post("/signals/{signal_id}/dismiss")
async def dismiss_signal(
    signal_id: int,
    request: DismissRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Dismiss a Slack signal as not actionable."""
    service = SlackSignalService(db, current_user.tenant_id)
    signal = await service.dismiss_signal(signal_id, current_user.id, request.reason)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal.to_dict()


# ── Webhook receiver ─────────────────────────────────────────────────────────

@router.post("/webhook/{connection_id}")
async def receive_webhook(
    connection_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Receive a Slack webhook payload.

    This endpoint handles incoming Slack event payloads. It does NOT require
    user authentication since Slack sends these automatically.

    Handles Slack URL verification challenge and event callbacks.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # Look up the connection to get tenant_id
    from app.models.slack_signal import SlackConnection
    conn = await db.get(SlackConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found or inactive")

    # Handle event_callback
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        event_type = event.get("type", "")

        # Only process message events (not message_changed, message_deleted, etc.)
        if event_type == "message" and not event.get("subtype"):
            service = SlackSignalService(db, conn.tenant_id)
            await service.ingest_message(
                connection_id=connection_id,
                message={
                    "channel_id": event.get("channel", ""),
                    "channel_name": "",  # Not available in event payload; resolved later
                    "message_ts": event.get("ts", ""),
                    "sender_name": event.get("user_profile", {}).get("display_name")
                        or event.get("username"),
                    "text": event.get("text", ""),
                    "thread_ts": event.get("thread_ts"),
                },
            )

    return {"ok": True}


# ── Manual ingestion (for testing) ───────────────────────────────────────────

@router.post("/ingest-manual")
async def ingest_manual(
    request: ManualIngestRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Manually ingest a Slack message (for testing the classification pipeline)."""
    service = SlackSignalService(db, current_user.tenant_id)
    signal = await service.ingest_message(
        connection_id=request.connection_id,
        message={
            "channel_id": request.channel_id,
            "channel_name": request.channel_name or "",
            "message_ts": request.message_ts,
            "sender_name": request.sender_name,
            "text": request.text,
            "thread_ts": request.thread_ts,
        },
    )
    if not signal:
        raise HTTPException(status_code=409, detail="Duplicate message (same timestamp already ingested)")
    return signal.to_dict()


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get Slack signals dashboard summary.

    Context Engine envelope with is_configured / is_active flags scoped to
    the tenant's active SC config. Tolerant of missing slack_connections
    table (feature not yet deployed) — returns is_configured=false.
    """
    from sqlalchemy import text as _text
    from app.services.context_engine_dashboard import (
        resolve_active_config_async, context_engine_envelope,
    )

    tenant_id = current_user.tenant_id
    config_id, config_name = await resolve_active_config_async(db, tenant_id)

    # Configured = at least one slack_connections row (best-effort; table
    # may not exist if the Slack integration has not been deployed).
    is_configured = False
    active_connections = 0
    total_connections = 0
    try:
        total_connections = (await db.execute(
            _text("SELECT COUNT(*) FROM slack_connections WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )).scalar() or 0
        is_configured = total_connections > 0
        if is_configured:
            active_connections = (await db.execute(
                _text(
                    "SELECT COUNT(*) FROM slack_connections "
                    "WHERE tenant_id = :tid AND COALESCE(is_active, true) = true"
                ),
                {"tid": tenant_id},
            )).scalar() or 0
    except Exception:
        await db.rollback()

    # Best-effort stats via the service
    stats: dict = {}
    try:
        service = SlackSignalService(db, tenant_id)
        stats = await service.get_dashboard_stats()
    except Exception:
        await db.rollback()
        stats = {}

    return context_engine_envelope(
        config_id=config_id,
        config_name=config_name,
        is_configured=is_configured,
        is_active=is_configured and active_connections > 0,
        metrics={
            **stats,
            "active_connections": active_connections,
            "total_connections": total_connections,
            "channels_monitored": stats.get("channels_monitored", 0),
            "signals_last_7d": stats.get("signals_last_7d", 0),
        },
    )

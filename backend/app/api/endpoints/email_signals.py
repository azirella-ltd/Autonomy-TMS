"""Email Signal API endpoints — GDPR-safe email ingestion for SC intelligence.

Manages email connections (IMAP/Gmail) and the resulting supply chain signals.
Signals are classified by LLM, routed to TRMs, and surfaced in Decision Stream.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_async_db
from app.models.user import User
from app.models.email_signal import EmailConnection, EmailSignal
from app.services.email_signal_service import EmailSignalService

router = APIRouter(prefix="/email-signals", tags=["Email Signals"])
logger = logging.getLogger(__name__)


# ── Request / Response models ────────────────────────────────────────────────

class ConnectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connection_type: str = Field(..., pattern="^(imap|gmail)$")
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_folder: str = "INBOX"
    imap_use_ssl: bool = True
    gmail_label_filter: Optional[str] = None
    domain_allowlist: Optional[list] = None
    domain_blocklist: Optional[list] = None
    poll_interval_minutes: int = 5
    auto_route_enabled: bool = True
    min_confidence_to_route: float = 0.6


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_folder: Optional[str] = None
    gmail_label_filter: Optional[str] = None
    domain_allowlist: Optional[list] = None
    domain_blocklist: Optional[list] = None
    poll_interval_minutes: Optional[int] = None
    auto_route_enabled: Optional[bool] = None
    min_confidence_to_route: Optional[float] = None
    is_active: Optional[bool] = None


class ManualIngestRequest(BaseModel):
    config_id: int
    from_header: str = Field(..., min_length=1)
    subject: str = ""
    body: str = Field(..., min_length=10)
    received_at: Optional[str] = None  # ISO format, defaults to now


class DismissRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


# ── Connection endpoints ─────────────────────────────────────────────────────

@router.get("/connections")
async def list_connections(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """List email connections for the current tenant."""
    from sqlalchemy import select
    result = await db.execute(
        select(EmailConnection)
        .where(EmailConnection.tenant_id == current_user.tenant_id)
        .order_by(EmailConnection.created_at.desc())
    )
    connections = result.scalars().all()
    return [c.to_dict() for c in connections]


@router.post("/connections")
async def create_connection(
    request: ConnectionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Create a new email connection."""
    conn = EmailConnection(
        tenant_id=current_user.tenant_id,
        name=request.name,
        connection_type=request.connection_type,
        imap_host=request.imap_host,
        imap_port=request.imap_port,
        imap_username=request.imap_username,
        imap_password_encrypted=request.imap_password,  # TODO: encrypt
        imap_folder=request.imap_folder,
        imap_use_ssl=request.imap_use_ssl,
        gmail_label_filter=request.gmail_label_filter,
        domain_allowlist=request.domain_allowlist,
        domain_blocklist=request.domain_blocklist,
        poll_interval_minutes=request.poll_interval_minutes,
        auto_route_enabled=request.auto_route_enabled,
        min_confidence_to_route=request.min_confidence_to_route,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn.to_dict()


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: int,
    request: ConnectionUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Update an email connection."""
    conn = await db.get(EmailConnection, connection_id)
    if not conn or conn.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    for field, value in request.model_dump(exclude_unset=True).items():
        if field == "imap_password" and value is not None:
            conn.imap_password_encrypted = value  # TODO: encrypt
        elif hasattr(conn, field):
            setattr(conn, field, value)

    await db.commit()
    await db.refresh(conn)
    return conn.to_dict()


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Delete an email connection."""
    conn = await db.get(EmailConnection, connection_id)
    if not conn or conn.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()
    return {"status": "deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Test an email connection."""
    conn = await db.get(EmailConnection, connection_id)
    if not conn or conn.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        from app.services.email_connector import create_connector
        connector = create_connector(conn)
        result = await connector.test_connection()
        return result
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/connections/{connection_id}/poll")
async def trigger_poll(
    connection_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Manually trigger a poll for new emails."""
    conn = await db.get(EmailConnection, connection_id)
    if not conn or conn.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        from app.services.email_connector import create_connector
        connector = create_connector(conn)
        raw_emails = await connector.fetch_new_emails(conn.last_poll_uid)

        service = EmailSignalService(db)

        # Get config_id from tenant's first active config
        from sqlalchemy import select, text
        config_result = await db.execute(
            text("SELECT id FROM supply_chain_configs WHERE tenant_id = :tid AND is_active = true LIMIT 1"),
            {"tid": current_user.tenant_id},
        )
        config_row = config_result.fetchone()
        if not config_row:
            raise HTTPException(status_code=400, detail="No active supply chain config for tenant")
        config_id = config_row[0]

        ingested = 0
        for raw in raw_emails:
            signal = await service.ingest_email(
                tenant_id=current_user.tenant_id,
                config_id=config_id,
                connection_id=connection_id,
                email_uid=raw.message_id,
                from_header=raw.from_header,
                subject=raw.subject,
                body=raw.body_text,
                received_at=raw.received_at,
            )
            if signal:
                ingested += 1

        # Update poll state
        conn.last_poll_at = datetime.utcnow()
        if raw_emails:
            conn.last_poll_uid = raw_emails[-1].uid
        await db.commit()

        return {"fetched": len(raw_emails), "ingested": ingested}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Signal endpoints ─────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    config_id: Optional[int] = None,
    status: Optional[str] = None,
    signal_type: Optional[str] = None,
    partner_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List email signals for the current tenant."""
    service = EmailSignalService(db)
    signals = await service.get_signals(
        tenant_id=current_user.tenant_id,
        config_id=config_id,
        status=status,
        signal_type=signal_type,
        partner_type=partner_type,
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
    """Get a single email signal by ID."""
    signal = await db.get(EmailSignal, signal_id)
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
    """Dismiss a signal as not actionable."""
    service = EmailSignalService(db)
    signal = await service.dismiss_signal(
        signal_id, current_user.tenant_id, current_user.id, request.reason,
    )
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal.to_dict()


@router.post("/signals/{signal_id}/reclassify")
async def reclassify_signal(
    signal_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Re-run LLM classification on a signal."""
    signal = await db.get(EmailSignal, signal_id)
    if not signal or signal.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Signal not found")

    service = EmailSignalService(db)
    tenant_context = await service._get_tenant_context(signal.config_id)
    classification = await service._classify_email(
        signal.body_scrubbed,
        signal.subject_scrubbed or "",
        signal.partner_name or signal.sender_domain,
        signal.partner_type or "unknown",
        tenant_context,
    )

    signal.signal_type = classification.get("signal_type", signal.signal_type)
    signal.signal_direction = classification.get("direction")
    signal.signal_magnitude_pct = classification.get("magnitude_pct")
    signal.signal_confidence = classification.get("confidence", signal.signal_confidence)
    signal.signal_urgency = classification.get("urgency", signal.signal_urgency)
    signal.signal_summary = classification.get("summary", signal.signal_summary)
    signal.classified_at = datetime.utcnow()
    signal.status = "CLASSIFIED"

    await db.commit()
    await db.refresh(signal)
    return signal.to_dict()


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get email signals dashboard summary."""
    service = EmailSignalService(db)
    return await service.get_dashboard_stats(current_user.tenant_id)


# ── Manual ingestion (for testing) ───────────────────────────────────────────

@router.post("/ingest-manual")
async def ingest_manual(
    request: ManualIngestRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Manually ingest an email (paste for testing).

    This allows testing the classification pipeline without an actual
    email connection. The from_header should include a domain for
    TradingPartner resolution.
    """
    received_at = datetime.utcnow()
    if request.received_at:
        try:
            received_at = datetime.fromisoformat(request.received_at)
        except ValueError:
            pass

    import hashlib
    email_uid = hashlib.sha256(
        f"{request.from_header}:{request.subject}:{received_at.isoformat()}".encode()
    ).hexdigest()[:32]

    service = EmailSignalService(db)
    signal = await service.ingest_email(
        tenant_id=current_user.tenant_id,
        config_id=request.config_id,
        connection_id=None,
        email_uid=email_uid,
        from_header=request.from_header,
        subject=request.subject,
        body=request.body,
        received_at=received_at,
    )

    if not signal:
        raise HTTPException(status_code=409, detail="Duplicate email (same content already ingested)")

    return signal.to_dict()

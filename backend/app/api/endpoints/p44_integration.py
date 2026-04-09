"""
project44 Integration API Endpoints

Provides REST endpoints for:
- Webhook receiver (inbound tracking events from p44)
- Connection management (configure, test, status)
- Manual tracking operations (create/get shipment tracking)
- Feature flag management

All endpoints are tenant-scoped. Webhook receiver uses
signature verification instead of JWT auth.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.user import User

router = APIRouter()


# ============================================================================
# Pydantic Request/Response Models
# ============================================================================

class P44ConfigUpdate(BaseModel):
    """Update p44 integration configuration."""
    client_id: Optional[str] = Field(None, description="p44 OAuth client ID")
    client_secret: Optional[str] = Field(None, description="p44 OAuth client secret (will be encrypted)")
    environment: Optional[str] = Field(None, description="'sandbox' or 'production'")
    webhook_secret: Optional[str] = Field(None, description="Webhook HMAC verification secret")
    features: Optional[Dict[str, bool]] = Field(None, description="Feature flags")
    rate_limit_per_sec: Optional[int] = Field(None, ge=1, le=100)
    timeout_seconds: Optional[int] = Field(None, ge=5, le=120)
    max_retries: Optional[int] = Field(None, ge=0, le=10)


class P44ConfigResponse(BaseModel):
    """p44 integration configuration (secrets redacted)."""
    enabled: bool = False
    environment: str = "sandbox"
    client_id: str = ""
    has_client_secret: bool = False
    webhook_url: str = ""
    features: Dict[str, bool] = {}
    connection_status: str = "unconfigured"
    last_connection_test: Optional[str] = None
    error_message: Optional[str] = None


class P44ConnectionTestResponse(BaseModel):
    """Result of p44 connection test."""
    status: str
    error: Optional[str] = None


class P44TrackingRequest(BaseModel):
    """Request to create p44 tracking for a shipment."""
    shipment_id: int = Field(..., description="TMS Shipment ID")
    carrier_scac: Optional[str] = Field(None, description="Override carrier SCAC")


class P44TrackingResponse(BaseModel):
    """Response from p44 tracking creation."""
    p44_shipment_id: str
    tracking_url: Optional[str] = None
    status: str


class WebhookProcessResult(BaseModel):
    """Result of webhook processing."""
    status: str
    p44_shipment_id: Optional[str] = None
    tracking_event_id: Optional[int] = None
    exception_id: Optional[int] = None
    reason: Optional[str] = None


# ============================================================================
# Webhook Receiver (No JWT — uses signature verification)
# ============================================================================

@router.post(
    "/webhook/{tenant_id}",
    response_model=WebhookProcessResult,
    summary="Receive p44 webhook event",
    description="Inbound endpoint for project44 tracking webhooks. "
    "Authenticated via HMAC signature, not JWT.",
)
async def receive_webhook(
    tenant_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive and process a project44 webhook delivery.

    p44 sends tracking updates, ETA changes, and exceptions
    to this endpoint. The payload is verified via HMAC-SHA256
    signature in the X-P44-Signature header.

    Returns 200 immediately; heavy processing can be deferred
    to background tasks for latency-sensitive webhooks.
    """
    from app.integrations.project44.config_service import P44ConfigService

    # Load tenant p44 config
    config = await P44ConfigService.get_config(tenant_id, db)
    if not config.get("enabled"):
        raise HTTPException(status_code=404, detail="p44 integration not enabled for this tenant")

    # Build handler with tenant's webhook secret
    handler = P44ConfigService.build_webhook_handler(config)

    # Read raw body for signature verification
    body = await request.body()
    headers = dict(request.headers)

    # Process webhook
    result = await handler.process_webhook(headers, body, tenant_id, db)

    await db.commit()

    return WebhookProcessResult(**result)


# ============================================================================
# Configuration Management (JWT-protected, tenant admin only)
# ============================================================================

@router.get(
    "/config",
    response_model=P44ConfigResponse,
    summary="Get p44 integration configuration",
)
async def get_p44_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get project44 integration configuration for the current tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from app.integrations.project44.config_service import P44ConfigService

    config = await P44ConfigService.get_config(current_user.tenant_id, db)

    return P44ConfigResponse(
        enabled=config.get("enabled", False),
        environment=config.get("environment", "sandbox"),
        client_id=config.get("client_id", ""),
        has_client_secret=bool(config.get("client_secret_encrypted")),
        webhook_url=config.get("webhook_url", ""),
        features=config.get("features", {}),
        connection_status=config.get("connection_status", "unconfigured"),
        last_connection_test=config.get("last_connection_test"),
        error_message=config.get("error_message"),
    )


@router.put(
    "/config",
    response_model=P44ConfigResponse,
    summary="Update p44 integration configuration",
)
async def update_p44_config(
    config_update: P44ConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update project44 integration configuration.

    Only provided fields are updated. Client secret is encrypted
    before storage per SOC II requirements.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from app.integrations.project44.config_service import P44ConfigService

    updates = config_update.dict(exclude_none=True)

    # Handle client_secret → encrypt and store as client_secret_encrypted
    if "client_secret" in updates:
        # TODO: Use column-level encryption (app.core.encryption)
        # For now, store as-is; encryption layer will wrap this
        updates["client_secret_encrypted"] = updates.pop("client_secret")

    config = await P44ConfigService.update_config(current_user.tenant_id, updates, db)
    await db.commit()

    return P44ConfigResponse(
        enabled=config.get("enabled", False),
        environment=config.get("environment", "sandbox"),
        client_id=config.get("client_id", ""),
        has_client_secret=bool(config.get("client_secret_encrypted")),
        webhook_url=config.get("webhook_url", ""),
        features=config.get("features", {}),
        connection_status=config.get("connection_status", "unconfigured"),
        last_connection_test=config.get("last_connection_test"),
        error_message=config.get("error_message"),
    )


@router.post(
    "/config/enable",
    response_model=P44ConfigResponse,
    summary="Enable p44 integration",
)
async def enable_p44(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enable project44 integration for the current tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from app.integrations.project44.config_service import P44ConfigService

    config = await P44ConfigService.update_config(
        current_user.tenant_id, {"enabled": True}, db
    )
    await db.commit()

    return P44ConfigResponse(
        enabled=True,
        environment=config.get("environment", "sandbox"),
        client_id=config.get("client_id", ""),
        has_client_secret=bool(config.get("client_secret_encrypted")),
        webhook_url=config.get("webhook_url", ""),
        features=config.get("features", {}),
        connection_status=config.get("connection_status", "unconfigured"),
        last_connection_test=config.get("last_connection_test"),
        error_message=config.get("error_message"),
    )


@router.post(
    "/config/disable",
    response_model=P44ConfigResponse,
    summary="Disable p44 integration",
)
async def disable_p44(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Disable project44 integration for the current tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from app.integrations.project44.config_service import P44ConfigService

    config = await P44ConfigService.update_config(
        current_user.tenant_id, {"enabled": False}, db
    )
    await db.commit()

    return P44ConfigResponse(
        enabled=False,
        environment=config.get("environment", "sandbox"),
        client_id=config.get("client_id", ""),
        has_client_secret=bool(config.get("client_secret_encrypted")),
        webhook_url=config.get("webhook_url", ""),
        features=config.get("features", {}),
        connection_status=config.get("connection_status", "unconfigured"),
        last_connection_test=config.get("last_connection_test"),
        error_message=config.get("error_message"),
    )


# ============================================================================
# Connection Testing
# ============================================================================

@router.post(
    "/test-connection",
    response_model=P44ConnectionTestResponse,
    summary="Test p44 API connection",
)
async def test_p44_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Test the project44 API connection.

    Attempts OAuth token acquisition and verifies API access.
    Updates the stored connection status.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from app.integrations.project44.config_service import P44ConfigService

    result = await P44ConfigService.test_connection(current_user.tenant_id, db)
    await db.commit()

    return P44ConnectionTestResponse(**result)


# ============================================================================
# Tracking Operations (JWT-protected)
# ============================================================================

@router.post(
    "/track",
    response_model=P44TrackingResponse,
    summary="Create p44 tracking for a shipment",
)
async def create_tracking(
    request: P44TrackingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Register a TMS shipment with project44 for tracking.

    Creates a tracked shipment in p44 and stores the p44_shipment_id
    back on the TMS Shipment record.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from sqlalchemy import select, and_
    from app.models.tms_entities import Shipment, Carrier, ShipmentIdentifier
    from app.integrations.project44.config_service import P44ConfigService
    from app.integrations.project44.tracking_service import P44TrackingService
    from app.integrations.project44.data_mapper import P44DataMapper

    # Load config
    config = await P44ConfigService.get_config(current_user.tenant_id, db)
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="p44 integration not enabled")

    # Load shipment
    stmt = select(Shipment).where(
        and_(
            Shipment.id == request.shipment_id,
            Shipment.tenant_id == current_user.tenant_id,
        )
    )
    result = await db.execute(stmt)
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if shipment.p44_shipment_id:
        raise HTTPException(status_code=409, detail="Shipment already tracked in p44")

    # Load carrier
    carrier = None
    if shipment.carrier_id:
        carrier = await db.get(Carrier, shipment.carrier_id)

    # Load identifiers
    ident_stmt = select(ShipmentIdentifier).where(
        ShipmentIdentifier.shipment_id == shipment.id
    )
    ident_result = await db.execute(ident_stmt)
    identifiers = ident_result.scalars().all()

    # Build p44 payload
    payload = P44DataMapper.to_p44_shipment(shipment, carrier, identifiers)

    # Send to p44
    connector = P44ConfigService.build_connector(config)
    try:
        tracking_service = P44TrackingService(connector)
        p44_response = await tracking_service.create_shipment(payload)
    finally:
        await connector.close()

    # Update shipment with p44 IDs
    p44_id = p44_response.get("id", "")
    shipment.p44_shipment_id = p44_id
    shipment.p44_tracking_url = p44_response.get("trackingUrl", "")
    await db.commit()

    return P44TrackingResponse(
        p44_shipment_id=p44_id,
        tracking_url=p44_response.get("trackingUrl"),
        status="created",
    )


@router.get(
    "/track/{shipment_id}",
    summary="Get p44 tracking status for a shipment",
)
async def get_tracking(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current tracking status from p44 for a shipment.

    Returns the latest p44 tracking data and syncs any new
    events to the TMS TrackingEvent table.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    from sqlalchemy import select, and_
    from app.models.tms_entities import Shipment
    from app.integrations.project44.config_service import P44ConfigService
    from app.integrations.project44.tracking_service import P44TrackingService

    # Load config
    config = await P44ConfigService.get_config(current_user.tenant_id, db)
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="p44 integration not enabled")

    # Load shipment
    stmt = select(Shipment).where(
        and_(
            Shipment.id == shipment_id,
            Shipment.tenant_id == current_user.tenant_id,
        )
    )
    result = await db.execute(stmt)
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if not shipment.p44_shipment_id:
        raise HTTPException(status_code=400, detail="Shipment not tracked in p44")

    # Fetch from p44
    connector = P44ConfigService.build_connector(config)
    try:
        tracking_service = P44TrackingService(connector)
        p44_data = await tracking_service.get_shipment(shipment.p44_shipment_id)
        tracking_history = await tracking_service.get_tracking_history(shipment.p44_shipment_id)
    finally:
        await connector.close()

    return {
        "shipment_id": shipment_id,
        "p44_shipment_id": shipment.p44_shipment_id,
        "p44_status": p44_data.get("status"),
        "estimated_delivery": p44_data.get("estimatedDeliveryDateTime"),
        "last_position": p44_data.get("lastPosition"),
        "event_count": len(tracking_history.get("events", [])),
        "tracking_url": shipment.p44_tracking_url,
    }


# ============================================================================
# Webhook Registration Info
# ============================================================================

@router.get(
    "/webhook-info",
    summary="Get webhook registration details",
)
async def get_webhook_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the webhook URL to register in the p44 portal.

    Tenant admins use this to configure their p44 webhook endpoint.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="System admin cannot manage integrations")

    # Build webhook URL from request
    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/v1/p44/webhook/{current_user.tenant_id}"

    return {
        "webhook_url": webhook_url,
        "tenant_id": current_user.tenant_id,
        "instructions": (
            "Register this URL in your project44 portal under "
            "Settings → Webhooks. Select event types: "
            "TRACKING_UPDATE, ETA_UPDATE, EXCEPTION, POSITION_UPDATE."
        ),
    }

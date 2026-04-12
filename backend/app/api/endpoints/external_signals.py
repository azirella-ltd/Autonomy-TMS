"""External Signal Intelligence API — Outside-in planning data management.

Endpoints for managing external signal sources, viewing collected signals,
and triggering manual refreshes. Signals are automatically collected daily
by the APScheduler job.

Tenant-scoped: each tenant configures their own sources and sees only their signals.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_user
from app.services.external_signal_service import ExternalSignalService
from app.models.external_signal import (
    SOURCE_REGISTRY, SIGNAL_CATEGORIES, SIGNAL_TMS_IMPACT,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/external-signals", tags=["External Signals"])


def _get_tenant_id(user) -> int:
    """Extract tenant_id from user, raise 403 if not tenant-scoped."""
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(403, "External signals require a tenant-scoped user.")
    return tid


# ── Source Management ─────────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List configured external signal sources for the tenant."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    return {"sources": await service.list_sources()}


@router.post("/sources")
async def create_source(
    source_key: str = Query(..., description="Source key (fred, open_meteo, eia, gdelt, google_trends, openfda)"),
    config_id: Optional[int] = Query(None, description="SC config ID to scope"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add an external signal source for the tenant."""
    tid = _get_tenant_id(current_user)
    if source_key not in SOURCE_REGISTRY:
        raise HTTPException(400, f"Unknown source: {source_key}. Available: {list(SOURCE_REGISTRY.keys())}")

    service = ExternalSignalService(db, tid)
    source = await service.get_or_create_source(source_key, config_id=config_id)
    await db.commit()
    return service._source_to_dict(source)


@router.post("/sources/activate-defaults")
async def activate_defaults(
    config_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Activate default free sources (Open-Meteo, GDELT, openFDA, +FRED/EIA if keys set)."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    created = await service.activate_default_sources(config_id)
    return {"sources": created, "count": len(created)}


@router.put("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    is_active: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Enable or disable a source."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    return await service.toggle_source(source_id, is_active)


@router.put("/sources/{source_id}/params")
async def update_source_params(
    source_id: int,
    source_params: Optional[dict] = None,
    industry_tags: Optional[list] = None,
    region_tags: Optional[list] = None,
    product_tags: Optional[list] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a source's parameters and relevance tags."""
    tid = _get_tenant_id(current_user)
    from sqlalchemy import select
    from app.models.external_signal import ExternalSignalSource

    result = await db.execute(
        select(ExternalSignalSource).where(
            ExternalSignalSource.id == source_id,
            ExternalSignalSource.tenant_id == tid,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source not found")

    if source_params is not None:
        source.source_params = source_params
    if industry_tags is not None:
        source.industry_tags = industry_tags
    if region_tags is not None:
        source.region_tags = region_tags
    if product_tags is not None:
        source.product_tags = product_tags

    await db.commit()
    service = ExternalSignalService(db, tid)
    return service._source_to_dict(source)


# ── Signal Collection & Refresh ───────────────────────────────────────────────

@router.post("/refresh/{source_id}")
async def refresh_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually trigger a refresh for a specific source."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    return await service.refresh_source(source_id)


@router.post("/refresh-all")
async def refresh_all(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually trigger a refresh for all active sources."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    return await service.refresh_all_sources()


# ── Signal Querying ───────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    category: Optional[str] = Query(None, description="Filter by category"),
    source_key: Optional[str] = Query(None, description="Filter by source"),
    since: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List collected signals with filtering and pagination."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)

    since_date = None
    if since:
        try:
            since_date = date.fromisoformat(since)
        except ValueError:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    return await service.list_signals(
        category=category,
        source_key=source_key,
        since=since_date,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard summary for the Context Engine page.

    Envelope: is_configured / is_active + active SC config identity.
    Scoped to the tenant. Market Intelligence is considered configured
    when at least one external_signal_sources row exists for the tenant.
    """
    from sqlalchemy import text as _text
    from app.services.context_engine_dashboard import (
        resolve_active_config_async, context_engine_envelope,
    )

    tid = _get_tenant_id(current_user)
    config_id, config_name = await resolve_active_config_async(db, tid)

    is_configured = False
    active_sources = 0
    total_sources = 0
    try:
        row = (await db.execute(
            _text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE COALESCE(is_active, true) = true) AS active
                FROM external_signal_sources
                WHERE tenant_id = :tid
            """),
            {"tid": tid},
        )).fetchone()
        if row:
            total_sources = int(row[0] or 0)
            active_sources = int(row[1] or 0)
        is_configured = total_sources > 0
    except Exception:
        await db.rollback()

    service = ExternalSignalService(db, tid)
    try:
        stats = await service.get_dashboard_stats()
    except Exception:
        await db.rollback()
        stats = {}

    return context_engine_envelope(
        config_id=config_id,
        config_name=config_name,
        is_configured=is_configured,
        is_active=is_configured and active_sources > 0,
        metrics={
            **stats,
            "active_sources": active_sources,
            "total_sources": total_sources,
        },
    )


@router.get("/chat-context")
async def get_chat_context(
    max_signals: int = Query(10, le=20),
    max_age_days: int = Query(7, le=30),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get formatted signal context for Azirella chat injection (debug/preview)."""
    tid = _get_tenant_id(current_user)
    service = ExternalSignalService(db, tid)
    context = await service.get_signals_for_chat_context(max_signals, max_age_days)
    return {"context": context, "length": len(context)}


# ── Reference Data ────────────────────────────────────────────────────────────

@router.get("/registry")
async def source_registry(
    current_user=Depends(get_current_user),
):
    """List all available source types and their configuration options."""
    return {
        "sources": SOURCE_REGISTRY,
        "categories": SIGNAL_CATEGORIES,
        "tms_impact_types": SIGNAL_TMS_IMPACT,
    }


# ── Weather Location Sync ───────────────────────────────────────────────────

@router.post("/sources/sync-weather-locations")
async def sync_weather_locations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Auto-populate Open-Meteo and NWS location parameters from the
    tenant's active facility network and lane corridors.

    For each weather source (open_meteo, nws_alerts), this endpoint:
    1. Reads all FacilityConfig sites with lat/lon for the tenant
    2. Reads all LaneProfile origin/destination pairs
    3. Deduplicates by proximity (within 30 miles)
    4. Updates the source's source_params.locations array
    5. Returns the count of locations synced

    Idempotent: running it again replaces the locations list.
    """
    from sqlalchemy import select, text as sql_text

    tenant_id = _get_tenant_id(current_user)

    # Get all facility locations with coordinates
    rows = (await db.execute(sql_text("""
        SELECT
            s.name,
            s.latitude,
            s.longitude,
            fc.facility_type
        FROM facility_config fc
        JOIN sites s ON s.id = fc.site_id
        WHERE fc.tenant_id = :tid
          AND s.latitude IS NOT NULL
          AND s.longitude IS NOT NULL
    """), {"tid": tenant_id})).fetchall()

    locations = []
    seen_coords = set()
    for row in rows:
        # Proximity dedup: round to 0.5° (~30 miles)
        key = (round(row.latitude * 2) / 2, round(row.longitude * 2) / 2)
        if key in seen_coords:
            continue
        seen_coords.add(key)
        locations.append({
            "lat": round(float(row.latitude), 4),
            "lon": round(float(row.longitude), 4),
            "name": row.name or f"{row.facility_type}",
        })

    if not locations:
        return {
            "synced": 0,
            "message": (
                "No facility locations with coordinates found. "
                "Add lat/lon to your facilities in Network Config."
            ),
        }

    # Update weather sources
    from app.models.external_signal import ExternalSignalSource
    weather_keys = ("open_meteo", "nws_alerts")
    updated = 0
    for key in weather_keys:
        source_row = (await db.execute(
            select(ExternalSignalSource).where(
                ExternalSignalSource.tenant_id == tenant_id,
                ExternalSignalSource.source_key == key,
            )
        )).scalar_one_or_none()

        if not source_row:
            continue

        params = dict(source_row.source_params or {})
        params["locations"] = locations
        params["sync_from_network"] = True
        source_row.source_params = params
        updated += 1

    if updated:
        await db.commit()

    return {
        "synced": len(locations),
        "sources_updated": updated,
        "locations": locations,
    }

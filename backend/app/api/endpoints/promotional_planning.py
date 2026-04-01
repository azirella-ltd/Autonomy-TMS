"""Promotional Planning API — CRUD and workflow for promotions.

Integrates with AWS SC supplementary_time_series (PROMOTION) and
forecast adjustments (adjustment_type='PROMOTION').
"""

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_active_user, require_tenant_admin
from app.services.promotional_planning_service import PromotionalPlanningService

router = APIRouter(prefix="/promotions", tags=["promotional-planning"])


# ============================================================================
# Pydantic Models
# ============================================================================

class PromotionCreate(BaseModel):
    name: str
    promotion_type: str  # price_discount, bogo, bundle, display, seasonal, clearance, loyalty, new_product_launch
    start_date: date
    end_date: date
    description: Optional[str] = None
    config_id: Optional[int] = None
    product_ids: Optional[List[str]] = None  # AWS SC product.id references
    site_ids: Optional[List[int]] = None  # AWS SC site.id references
    channel_ids: Optional[List[str]] = None  # AWS SC channel references
    customer_tpartner_ids: Optional[List[str]] = None  # AWS SC trading_partner.id
    expected_uplift_pct: Optional[float] = None
    expected_cannibalization_pct: Optional[float] = None
    budget: Optional[float] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    source_event_id: Optional[str] = None


class PromotionUpdate(BaseModel):
    name: Optional[str] = None
    promotion_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    config_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    site_ids: Optional[List[int]] = None
    channel_ids: Optional[List[str]] = None
    customer_tpartner_ids: Optional[List[str]] = None
    expected_uplift_pct: Optional[float] = None
    expected_cannibalization_pct: Optional[float] = None
    actual_uplift_pct: Optional[float] = None
    actual_cannibalization_pct: Optional[float] = None
    budget: Optional[float] = None
    actual_spend: Optional[float] = None
    roi: Optional[float] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    source_event_id: Optional[str] = None


class CancelRequest(BaseModel):
    reason: str = ""


# ============================================================================
# Helper
# ============================================================================

def _promo_to_dict(p) -> dict:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "config_id": p.config_id,
        "name": p.name,
        "description": p.description,
        "promotion_type": p.promotion_type,
        "status": p.status,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "product_ids": p.product_ids,
        "site_ids": p.site_ids,
        "channel_ids": p.channel_ids,
        "customer_tpartner_ids": p.customer_tpartner_ids,
        "expected_uplift_pct": p.expected_uplift_pct,
        "expected_cannibalization_pct": p.expected_cannibalization_pct,
        "actual_uplift_pct": p.actual_uplift_pct,
        "actual_cannibalization_pct": p.actual_cannibalization_pct,
        "budget": p.budget,
        "actual_spend": p.actual_spend,
        "roi": p.roi,
        "supp_time_series_ids": p.supp_time_series_ids,
        "forecast_adjustment_ids": p.forecast_adjustment_ids,
        "created_by": p.created_by,
        "approved_by": p.approved_by,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "notes": p.notes,
        "source": p.source,
        "source_event_id": p.source_event_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _history_to_dict(h) -> dict:
    return {
        "id": h.id,
        "promotion_id": h.promotion_id,
        "action": h.action,
        "changed_by": h.changed_by,
        "changes": h.changes,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/")
async def create_promotion(
    data: PromotionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Create a new promotion (draft status)."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    promo = await svc.create_promotion(data.model_dump(exclude_none=True), current_user.id)
    return _promo_to_dict(promo)


@router.get("/")
async def list_promotions(
    status: Optional[str] = Query(None),
    promotion_type: Optional[str] = Query(None),
    start_after: Optional[date] = Query(None),
    end_before: Optional[date] = Query(None),
    config_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List promotions with optional filters."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    promos = await svc.get_promotions(
        status=status, promo_type=promotion_type,
        start_after=start_after, end_before=end_before,
        config_id=config_id, limit=limit, offset=offset,
    )
    return [_promo_to_dict(p) for p in promos]


@router.get("/calendar")
async def promotion_calendar(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get promotions overlapping a date range for calendar view."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    promos = await svc.get_calendar(start_date, end_date)
    return [_promo_to_dict(p) for p in promos]


@router.get("/dashboard")
async def promotion_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Dashboard summary statistics."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    return await svc.get_dashboard_stats()


@router.get("/{promo_id}")
async def get_promotion(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get promotion detail."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    promo = await svc.get_promotion(promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int,
    data: PromotionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Update promotion fields (draft/planned only)."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    try:
        promo = await svc.update_promotion(promo_id, data.model_dump(exclude_none=True), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.post("/{promo_id}/approve")
async def approve_promotion(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Approve a promotion."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    try:
        promo = await svc.approve_promotion(promo_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.post("/{promo_id}/activate")
async def activate_promotion(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Activate an approved promotion."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    try:
        promo = await svc.activate_promotion(promo_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.post("/{promo_id}/complete")
async def complete_promotion(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Complete an active promotion."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    try:
        promo = await svc.complete_promotion(promo_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.post("/{promo_id}/cancel")
async def cancel_promotion(
    promo_id: int,
    body: CancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    """Cancel a promotion."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    try:
        promo = await svc.cancel_promotion(promo_id, current_user.id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promo_to_dict(promo)


@router.get("/{promo_id}/history")
async def promotion_history(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get audit trail for a promotion."""
    svc = PromotionalPlanningService(db, current_user.tenant_id)
    history = await svc.get_promotion_history(promo_id)
    return [_history_to_dict(h) for h in history]

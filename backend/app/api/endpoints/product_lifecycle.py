"""Product Lifecycle API — NPI, EOL, Markdown/Clearance management.

Integrates with AWS SC entities: product, product_bom, forecast,
inv_policy, vendor_product, sourcing_rules, supplementary_time_series.
"""

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_active_user, require_tenant_admin
from app.services.product_lifecycle_service import ProductLifecycleService

router = APIRouter(prefix="/product-lifecycle", tags=["product-lifecycle"])


# ============================================================================
# Pydantic Models
# ============================================================================

class LifecycleStageUpdate(BaseModel):
    stage: str  # concept, development, launch, growth, maturity, decline, eol, discontinued
    config_id: Optional[int] = None
    notes: Optional[str] = None


class NPICreate(BaseModel):
    project_name: str
    target_launch_date: date
    project_code: Optional[str] = None
    config_id: Optional[int] = None
    lifecycle_id: Optional[int] = None
    product_ids: Optional[List[str]] = None  # AWS SC product.id references
    site_ids: Optional[List[int]] = None  # AWS SC site.id references
    channel_ids: Optional[List[str]] = None
    demand_ramp_curve: Optional[list] = None  # [10, 25, 50, 75, 100]
    initial_forecast_qty: Optional[float] = None
    supplier_qualification_status: Optional[dict] = None  # {vendor_id: status}
    quality_gates: Optional[list] = None  # [{gate, status, date}]
    investment: Optional[float] = None
    expected_revenue_yr1: Optional[float] = None
    risk_assessment: Optional[str] = None
    notes: Optional[str] = None


class NPIUpdate(BaseModel):
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    target_launch_date: Optional[date] = None
    config_id: Optional[int] = None
    lifecycle_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    site_ids: Optional[List[int]] = None
    channel_ids: Optional[List[str]] = None
    demand_ramp_curve: Optional[list] = None
    initial_forecast_qty: Optional[float] = None
    supplier_qualification_status: Optional[dict] = None
    quality_gates: Optional[list] = None
    investment: Optional[float] = None
    expected_revenue_yr1: Optional[float] = None
    risk_assessment: Optional[str] = None
    notes: Optional[str] = None


class QualityGateUpdate(BaseModel):
    gate_name: str
    status: str  # passed, failed, in_progress, pending


class EOLCreate(BaseModel):
    config_id: Optional[int] = None
    lifecycle_id: Optional[int] = None
    product_ids: Optional[List[str]] = None  # AWS SC product.id references
    successor_product_ids: Optional[List[str]] = None
    last_buy_date: Optional[date] = None
    last_manufacture_date: Optional[date] = None
    last_ship_date: Optional[date] = None
    demand_phaseout_curve: Optional[list] = None  # [90, 75, 50, 25, 10, 0]
    disposition_plan: Optional[list] = None
    estimated_write_off: Optional[float] = None
    notes: Optional[str] = None


class EOLUpdate(BaseModel):
    config_id: Optional[int] = None
    lifecycle_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    successor_product_ids: Optional[List[str]] = None
    last_buy_date: Optional[date] = None
    last_manufacture_date: Optional[date] = None
    last_ship_date: Optional[date] = None
    demand_phaseout_curve: Optional[list] = None
    disposition_plan: Optional[list] = None
    remaining_inventory: Optional[dict] = None
    notification_sent_to: Optional[dict] = None
    estimated_write_off: Optional[float] = None
    actual_write_off: Optional[float] = None
    notes: Optional[str] = None


class MarkdownCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    config_id: Optional[int] = None
    eol_plan_id: Optional[int] = None
    product_ids: Optional[List[str]] = None  # AWS SC product.id references
    site_ids: Optional[List[int]] = None  # AWS SC site.id references
    channel_ids: Optional[List[str]] = None
    markdown_schedule: Optional[list] = None  # [{week, discount_pct}]
    original_price: Optional[float] = None  # from product.unit_price
    floor_price: Optional[float] = None
    target_sell_through_pct: Optional[float] = 100
    disposition_if_unsold: Optional[str] = "scrap"
    notes: Optional[str] = None


class MarkdownUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    config_id: Optional[int] = None
    eol_plan_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    site_ids: Optional[List[int]] = None
    channel_ids: Optional[List[str]] = None
    markdown_schedule: Optional[list] = None
    original_price: Optional[float] = None
    floor_price: Optional[float] = None
    target_sell_through_pct: Optional[float] = None
    disposition_if_unsold: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# Serializers
# ============================================================================

def _lifecycle_to_dict(lc) -> dict:
    return {
        "id": lc.id,
        "tenant_id": lc.tenant_id,
        "config_id": lc.config_id,
        "product_id": lc.product_id,
        "lifecycle_stage": lc.lifecycle_stage,
        "stage_entered_at": lc.stage_entered_at.isoformat() if lc.stage_entered_at else None,
        "expected_launch_date": lc.expected_launch_date.isoformat() if lc.expected_launch_date else None,
        "actual_launch_date": lc.actual_launch_date.isoformat() if lc.actual_launch_date else None,
        "expected_eol_date": lc.expected_eol_date.isoformat() if lc.expected_eol_date else None,
        "actual_eol_date": lc.actual_eol_date.isoformat() if lc.actual_eol_date else None,
        "successor_product_id": lc.successor_product_id,
        "predecessor_product_id": lc.predecessor_product_id,
        "notes": lc.notes,
        "created_at": lc.created_at.isoformat() if lc.created_at else None,
    }


def _npi_to_dict(n) -> dict:
    return {
        "id": n.id,
        "tenant_id": n.tenant_id,
        "config_id": n.config_id,
        "lifecycle_id": n.lifecycle_id,
        "project_name": n.project_name,
        "project_code": n.project_code,
        "status": n.status,
        "target_launch_date": n.target_launch_date.isoformat() if n.target_launch_date else None,
        "actual_launch_date": n.actual_launch_date.isoformat() if n.actual_launch_date else None,
        "product_ids": n.product_ids,
        "site_ids": n.site_ids,
        "channel_ids": n.channel_ids,
        "demand_ramp_curve": n.demand_ramp_curve,
        "initial_forecast_qty": n.initial_forecast_qty,
        "supplier_qualification_status": n.supplier_qualification_status,
        "quality_gates": n.quality_gates,
        "investment": n.investment,
        "expected_revenue_yr1": n.expected_revenue_yr1,
        "risk_assessment": n.risk_assessment,
        "owner_user_id": n.owner_user_id,
        "notes": n.notes,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _eol_to_dict(e) -> dict:
    return {
        "id": e.id,
        "tenant_id": e.tenant_id,
        "config_id": e.config_id,
        "lifecycle_id": e.lifecycle_id,
        "status": e.status,
        "product_ids": e.product_ids,
        "successor_product_ids": e.successor_product_ids,
        "last_buy_date": e.last_buy_date.isoformat() if e.last_buy_date else None,
        "last_manufacture_date": e.last_manufacture_date.isoformat() if e.last_manufacture_date else None,
        "last_ship_date": e.last_ship_date.isoformat() if e.last_ship_date else None,
        "demand_phaseout_curve": e.demand_phaseout_curve,
        "disposition_plan": e.disposition_plan,
        "remaining_inventory": e.remaining_inventory,
        "notification_sent_to": e.notification_sent_to,
        "estimated_write_off": e.estimated_write_off,
        "actual_write_off": e.actual_write_off,
        "owner_user_id": e.owner_user_id,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _markdown_to_dict(m) -> dict:
    return {
        "id": m.id,
        "tenant_id": m.tenant_id,
        "config_id": m.config_id,
        "eol_plan_id": m.eol_plan_id,
        "name": m.name,
        "status": m.status,
        "product_ids": m.product_ids,
        "site_ids": m.site_ids,
        "channel_ids": m.channel_ids,
        "markdown_schedule": m.markdown_schedule,
        "current_discount_pct": m.current_discount_pct,
        "original_price": m.original_price,
        "floor_price": m.floor_price,
        "target_sell_through_pct": m.target_sell_through_pct,
        "actual_sell_through_pct": m.actual_sell_through_pct,
        "revenue_recovered": m.revenue_recovered,
        "units_sold": m.units_sold,
        "units_remaining": m.units_remaining,
        "disposition_if_unsold": m.disposition_if_unsold,
        "start_date": m.start_date.isoformat() if m.start_date else None,
        "end_date": m.end_date.isoformat() if m.end_date else None,
        "owner_user_id": m.owner_user_id,
        "notes": m.notes,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _history_to_dict(h) -> dict:
    return {
        "id": h.id,
        "entity_type": h.entity_type,
        "entity_id": h.entity_id,
        "action": h.action,
        "previous_value": h.previous_value,
        "new_value": h.new_value,
        "changed_by": h.changed_by,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


# ============================================================================
# Lifecycle Endpoints
# ============================================================================

@router.get("/lifecycles")
async def list_lifecycles(
    stage: Optional[str] = Query(None),
    config_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    items = await svc.get_all_lifecycles(stage=stage, config_id=config_id, limit=limit, offset=offset)
    return [_lifecycle_to_dict(lc) for lc in items]


@router.get("/lifecycle-summary")
async def lifecycle_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    return await svc.get_lifecycle_summary()


@router.get("/lifecycles/{product_id}")
async def get_lifecycle(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    lc = await svc.get_lifecycle(product_id)
    if not lc:
        raise HTTPException(status_code=404, detail="No lifecycle record for this product")
    return _lifecycle_to_dict(lc)


@router.put("/lifecycles/{product_id}/stage")
async def set_lifecycle_stage(
    product_id: str,
    body: LifecycleStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    try:
        lc = await svc.set_lifecycle_stage(product_id, body.stage, current_user.id, body.config_id, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _lifecycle_to_dict(lc)


# ============================================================================
# NPI Endpoints
# ============================================================================

@router.post("/npi")
async def create_npi(
    data: NPICreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    npi = await svc.create_npi_project(data.model_dump(exclude_none=True), current_user.id)
    return _npi_to_dict(npi)


@router.get("/npi")
async def list_npi(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    items = await svc.get_npi_projects(status=status, limit=limit, offset=offset)
    return [_npi_to_dict(n) for n in items]


@router.get("/npi/{npi_id}")
async def get_npi(
    npi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    npi = await svc.get_npi_project(npi_id)
    if not npi:
        raise HTTPException(status_code=404, detail="NPI project not found")
    return _npi_to_dict(npi)


@router.put("/npi/{npi_id}")
async def update_npi(
    npi_id: int,
    data: NPIUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    npi = await svc.update_npi_project(npi_id, data.model_dump(exclude_none=True), current_user.id)
    if not npi:
        raise HTTPException(status_code=404, detail="NPI project not found")
    return _npi_to_dict(npi)


@router.post("/npi/{npi_id}/quality-gate")
async def update_quality_gate(
    npi_id: int,
    body: QualityGateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    npi = await svc.update_quality_gate(npi_id, body.gate_name, body.status, current_user.id)
    if not npi:
        raise HTTPException(status_code=404, detail="NPI project not found")
    return _npi_to_dict(npi)


@router.post("/npi/{npi_id}/launch")
async def launch_npi(
    npi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    try:
        npi = await svc.launch_product(npi_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not npi:
        raise HTTPException(status_code=404, detail="NPI project not found")
    return _npi_to_dict(npi)


# ============================================================================
# EOL Endpoints
# ============================================================================

@router.post("/eol")
async def create_eol(
    data: EOLCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    eol = await svc.create_eol_plan(data.model_dump(exclude_none=True), current_user.id)
    return _eol_to_dict(eol)


@router.get("/eol")
async def list_eol(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    items = await svc.get_eol_plans(status=status, limit=limit, offset=offset)
    return [_eol_to_dict(e) for e in items]


@router.get("/eol/{eol_id}")
async def get_eol(
    eol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    eol = await svc.get_eol_plan(eol_id)
    if not eol:
        raise HTTPException(status_code=404, detail="EOL plan not found")
    return _eol_to_dict(eol)


@router.put("/eol/{eol_id}")
async def update_eol(
    eol_id: int,
    data: EOLUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    eol = await svc.update_eol_plan(eol_id, data.model_dump(exclude_none=True), current_user.id)
    if not eol:
        raise HTTPException(status_code=404, detail="EOL plan not found")
    return _eol_to_dict(eol)


@router.post("/eol/{eol_id}/approve")
async def approve_eol(
    eol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    try:
        eol = await svc.approve_eol_plan(eol_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not eol:
        raise HTTPException(status_code=404, detail="EOL plan not found")
    return _eol_to_dict(eol)


@router.post("/eol/{eol_id}/complete")
async def complete_eol(
    eol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    try:
        eol = await svc.complete_eol_plan(eol_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not eol:
        raise HTTPException(status_code=404, detail="EOL plan not found")
    return _eol_to_dict(eol)


# ============================================================================
# Markdown Endpoints
# ============================================================================

@router.post("/markdown")
async def create_markdown(
    data: MarkdownCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    md = await svc.create_markdown_plan(data.model_dump(exclude_none=True), current_user.id)
    return _markdown_to_dict(md)


@router.get("/markdown")
async def list_markdown(
    status: Optional[str] = Query(None),
    eol_plan_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    items = await svc.get_markdown_plans(status=status, eol_plan_id=eol_plan_id, limit=limit, offset=offset)
    return [_markdown_to_dict(m) for m in items]


@router.get("/markdown/{md_id}")
async def get_markdown(
    md_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    md = await svc.get_markdown_plan(md_id)
    if not md:
        raise HTTPException(status_code=404, detail="Markdown plan not found")
    return _markdown_to_dict(md)


@router.put("/markdown/{md_id}")
async def update_markdown(
    md_id: int,
    data: MarkdownUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    md = await svc.update_markdown_plan(md_id, data.model_dump(exclude_none=True), current_user.id)
    if not md:
        raise HTTPException(status_code=404, detail="Markdown plan not found")
    return _markdown_to_dict(md)


@router.post("/markdown/{md_id}/activate")
async def activate_markdown(
    md_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tenant_admin),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    try:
        md = await svc.activate_markdown(md_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not md:
        raise HTTPException(status_code=404, detail="Markdown plan not found")
    return _markdown_to_dict(md)


# ============================================================================
# Dashboard & History
# ============================================================================

@router.get("/dashboard")
async def lifecycle_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    svc = ProductLifecycleService(db, current_user.tenant_id)
    return await svc.get_dashboard()


@router.get("/history/{entity_type}/{entity_id}")
async def lifecycle_history(
    entity_type: str,
    entity_id: int,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if entity_type not in ("lifecycle", "npi", "eol", "markdown"):
        raise HTTPException(status_code=400, detail="Invalid entity_type")
    svc = ProductLifecycleService(db, current_user.tenant_id)
    items = await svc.get_history(entity_type=entity_type, entity_id=entity_id, limit=limit)
    return [_history_to_dict(h) for h in items]

"""
RCCP API Endpoints

Bill of Resources management and RCCP validation against MPS plans.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.rccp import RCCPMethod
from app.schemas.rccp import (
    BillOfResourcesCreate, BillOfResourcesUpdate, BillOfResourcesResponse,
    BillOfResourcesBulkCreate, RCCPValidateRequest, RCCPRunResponse,
    RCCPRunListResponse, RCCPMethodDetection,
)
from app.services.rccp_service import RCCPService

router = APIRouter()


# ── Bill of Resources CRUD ────────────────────────────────────────

@router.get("/bor", response_model=List[BillOfResourcesResponse])
async def list_bor_entries(
    config_id: int = Query(..., gt=0),
    site_id: int = Query(..., gt=0),
    product_id: Optional[int] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List Bill of Resources entries for a config/site."""
    svc = RCCPService(db)
    entries = svc.get_bor_entries(config_id, site_id, product_id)
    return entries


@router.post("/bor", response_model=BillOfResourcesResponse, status_code=201)
async def create_bor_entry(
    data: BillOfResourcesCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Bill of Resources entry."""
    svc = RCCPService(db)
    return svc.create_bor(data.dict())


@router.post("/bor/bulk", response_model=List[BillOfResourcesResponse], status_code=201)
async def bulk_create_bor_entries(
    bulk: BillOfResourcesBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk create Bill of Resources entries."""
    svc = RCCPService(db)
    results = []
    for entry in bulk.entries:
        results.append(svc.create_bor(entry.dict()))
    return results


@router.put("/bor/{bor_id}", response_model=BillOfResourcesResponse)
async def update_bor_entry(
    bor_id: int,
    data: BillOfResourcesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a Bill of Resources entry."""
    svc = RCCPService(db)
    result = svc.update_bor(bor_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="BoR entry not found")
    return result


@router.delete("/bor/{bor_id}", status_code=204)
async def delete_bor_entry(
    bor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a Bill of Resources entry."""
    svc = RCCPService(db)
    if not svc.delete_bor(bor_id):
        raise HTTPException(status_code=404, detail="BoR entry not found")
    return None


@router.post("/bor/auto-generate", response_model=dict)
async def auto_generate_bor(
    config_id: int = Query(..., gt=0),
    site_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-generate BoR entries from production_process data."""
    svc = RCCPService(db)
    count = svc.auto_generate_bor(config_id, site_id)
    return {"entries_created": count, "config_id": config_id, "site_id": site_id}


# ── Method Detection ──────────────────────────────────────────────

@router.get("/detect-method", response_model=RCCPMethodDetection)
async def detect_rccp_method(
    config_id: int = Query(..., gt=0),
    site_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-detect the best RCCP method for a config/site based on available BoR data."""
    svc = RCCPService(db)
    return svc.detect_method(config_id, site_id)


# ── RCCP Validation ───────────────────────────────────────────────

@router.post("/validate", response_model=RCCPRunResponse, status_code=201)
async def validate_mps(
    req: RCCPValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run RCCP validation against an MPS plan.

    Computes resource loads using the selected method (auto-detects if omitted),
    applies Glenday changeover adjustment if enabled, and evaluates all 7 decision rules.
    """
    svc = RCCPService(db)
    method = RCCPMethod(req.method) if req.method else None
    try:
        run = svc.validate_mps(
            mps_plan_id=req.mps_plan_id,
            site_id=req.site_id,
            method=method,
            planning_horizon_weeks=req.planning_horizon_weeks,
            changeover_adjusted=req.changeover_adjusted,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return run


# ── RCCP Run History ──────────────────────────────────────────────

@router.get("/runs", response_model=RCCPRunListResponse)
async def list_rccp_runs(
    config_id: int = Query(..., gt=0),
    site_id: Optional[int] = Query(None, gt=0),
    mps_plan_id: Optional[int] = Query(None, gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List RCCP validation runs."""
    svc = RCCPService(db)
    runs, total = svc.get_runs(
        config_id=config_id,
        site_id=site_id,
        mps_plan_id=mps_plan_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return RCCPRunListResponse(items=runs, total=total, page=page, page_size=page_size)


@router.get("/runs/{run_id}", response_model=RCCPRunResponse)
async def get_rccp_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific RCCP validation run."""
    svc = RCCPService(db)
    run = svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="RCCP run not found")
    return run

"""
Planning Cycles API Endpoints

CRUD operations and management for planning cycles and snapshots.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.planning_cycle import (
    PlanningCycle, PlanningSnapshot, SnapshotDelta,
    CycleStatus, CycleType, SnapshotType, SnapshotTier
)
from app.models.user import User
from app.schemas.planning_cycle import (
    PlanningCycleCreate, PlanningCycleUpdate, PlanningCycleResponse,
    PlanningCycleStatusUpdate, PlanningCycleListResponse,
    PlanningSnapshotCreate, PlanningSnapshotResponse, PlanningSnapshotDetailResponse,
    PlanningSnapshotListResponse, SnapshotDeltaResponse,
    SnapshotComparisonRequest, SnapshotComparisonResponse,
    SnapshotChainResponse, RetentionStatsResponse,
)
from app.services.planning_cycle_service import PlanningCycleService
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Planning Cycles
# ============================================================================

@router.get("", response_model=PlanningCycleListResponse)
def list_planning_cycles(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cycle_type: Optional[CycleType] = None,
    status_filter: Optional[CycleStatus] = Query(None, alias="status"),
    include_archived: bool = False,
):
    """List planning cycles for the user's customer."""
    query = db.query(PlanningCycle).filter(
        PlanningCycle.tenant_id == current_user.tenant_id
    )

    if cycle_type:
        query = query.filter(PlanningCycle.cycle_type == cycle_type)
    if status_filter:
        query = query.filter(PlanningCycle.status == status_filter)
    if not include_archived:
        query = query.filter(PlanningCycle.status != CycleStatus.ARCHIVED)

    total = query.count()
    items = query.order_by(PlanningCycle.period_start.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return PlanningCycleListResponse(
        items=[PlanningCycleResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=PlanningCycleResponse, status_code=status.HTTP_201_CREATED)
def create_planning_cycle(
    cycle_in: PlanningCycleCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new planning cycle."""
    # Verify user has access to the tenant
    cycle_tenant = getattr(cycle_in, 'tenant_id', None) or getattr(cycle_in, 'customer_id', None)
    if cycle_tenant and cycle_tenant != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create cycle for a different tenant"
        )

    service = PlanningCycleService(db)
    cycle = service.create_cycle(
        tenant_id=current_user.tenant_id,
        name=cycle_in.name,
        cycle_type=cycle_in.cycle_type,
        period_start=cycle_in.period_start,
        period_end=cycle_in.period_end,
        owner_id=cycle_in.owner_id or current_user.id,
        description=cycle_in.description,
        planning_horizon_weeks=cycle_in.planning_horizon_weeks
    )

    return PlanningCycleResponse.model_validate(cycle)


@router.get("/{cycle_id}", response_model=PlanningCycleResponse)
def get_planning_cycle(
    cycle_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a specific planning cycle."""
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    return PlanningCycleResponse.model_validate(cycle)


@router.put("/{cycle_id}", response_model=PlanningCycleResponse)
def update_planning_cycle(
    cycle_id: int,
    cycle_in: PlanningCycleUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a planning cycle."""
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    # Don't allow updates to closed/archived cycles
    if cycle.status in [CycleStatus.CLOSED, CycleStatus.ARCHIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update closed or archived cycles"
        )

    update_data = cycle_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cycle, field, value)

    cycle.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cycle)

    return PlanningCycleResponse.model_validate(cycle)


@router.put("/{cycle_id}/status", response_model=PlanningCycleResponse)
def update_cycle_status(
    cycle_id: int,
    status_update: PlanningCycleStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update the status of a planning cycle."""
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    service = PlanningCycleService(db)

    try:
        cycle = service.update_cycle_status(
            cycle_id=cycle_id,
            new_status=status_update.status,
            user_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PlanningCycleResponse.model_validate(cycle)


@router.delete("/{cycle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planning_cycle(
    cycle_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a planning cycle (only draft cycles can be deleted)."""
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    if cycle.status != CycleStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft cycles can be deleted"
        )

    db.delete(cycle)
    db.commit()


# ============================================================================
# Planning Snapshots
# ============================================================================

@router.get("/{cycle_id}/snapshots", response_model=PlanningSnapshotListResponse)
def list_cycle_snapshots(
    cycle_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    snapshot_type: Optional[SnapshotType] = None,
    storage_tier: Optional[SnapshotTier] = None,
):
    """List snapshots for a planning cycle."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    query = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id
    )

    if snapshot_type:
        query = query.filter(PlanningSnapshot.snapshot_type == snapshot_type)
    if storage_tier:
        query = query.filter(PlanningSnapshot.storage_tier == storage_tier)

    total = query.count()
    items = query.order_by(PlanningSnapshot.version.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return PlanningSnapshotListResponse(
        items=[PlanningSnapshotResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/{cycle_id}/snapshots", response_model=PlanningSnapshotResponse, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    cycle_id: int,
    snapshot_in: PlanningSnapshotCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new snapshot for a planning cycle."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    if cycle.status in [CycleStatus.CLOSED, CycleStatus.ARCHIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create snapshots for closed or archived cycles"
        )

    service = PlanningCycleService(db)
    snapshot = service.create_snapshot(
        cycle_id=cycle_id,
        snapshot_type=snapshot_in.snapshot_type,
        commit_message=snapshot_in.commit_message,
        created_by_id=current_user.id,
        demand_plan_data=snapshot_in.demand_plan_data,
        supply_plan_data=snapshot_in.supply_plan_data,
        inventory_data=snapshot_in.inventory_data,
        forecast_data=snapshot_in.forecast_data,
        kpi_data=snapshot_in.kpi_data
    )

    return PlanningSnapshotResponse.model_validate(snapshot)


@router.get("/{cycle_id}/snapshots/{version}", response_model=PlanningSnapshotDetailResponse)
def get_snapshot(
    cycle_id: int,
    version: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    materialize: bool = Query(False, description="Materialize full data from deltas"),
):
    """Get a specific snapshot by version."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    snapshot = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id,
        PlanningSnapshot.version == version
    ).first()

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found"
        )

    if materialize:
        service = PlanningCycleService(db)
        materialized = service.materialize_snapshot(snapshot.id)
        response = PlanningSnapshotDetailResponse.model_validate(snapshot)
        response.demand_plan_data = materialized.get("demand_plan_data")
        response.supply_plan_data = materialized.get("supply_plan_data")
        response.inventory_data = materialized.get("inventory_data")
        response.forecast_data = materialized.get("forecast_data")
        response.kpi_data = materialized.get("kpi_data")
        return response

    return PlanningSnapshotDetailResponse.model_validate(snapshot)


@router.get("/{cycle_id}/snapshots/{version}/chain", response_model=SnapshotChainResponse)
def get_snapshot_chain(
    cycle_id: int,
    version: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    max_depth: int = Query(10, ge=1, le=100),
):
    """Get the ancestor chain for a snapshot."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    snapshot = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id,
        PlanningSnapshot.version == version
    ).first()

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found"
        )

    # Get ancestor chain
    ancestors = []
    current = snapshot
    depth = 0

    while current.parent_snapshot_id and depth < max_depth:
        parent = db.query(PlanningSnapshot).filter(
            PlanningSnapshot.id == current.parent_snapshot_id
        ).first()
        if parent:
            ancestors.append(PlanningSnapshotResponse.model_validate(parent))
            current = parent
            depth += 1
        else:
            break

    return SnapshotChainResponse(
        snapshot_id=snapshot.id,
        ancestors=ancestors,
        total_ancestors=len(ancestors)
    )


@router.get("/{cycle_id}/snapshots/{version}/deltas", response_model=list[SnapshotDeltaResponse])
def get_snapshot_deltas(
    cycle_id: int,
    version: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get deltas for a specific snapshot."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    snapshot = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id,
        PlanningSnapshot.version == version
    ).first()

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found"
        )

    deltas = db.query(SnapshotDelta).filter(
        SnapshotDelta.snapshot_id == snapshot.id
    ).order_by(SnapshotDelta.created_at).all()

    return [SnapshotDeltaResponse.model_validate(d) for d in deltas]


@router.post("/{cycle_id}/snapshots/{version}/compare", response_model=SnapshotComparisonResponse)
def compare_snapshots(
    cycle_id: int,
    version: int,
    comparison: SnapshotComparisonRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Compare two snapshot versions."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    snapshot_a = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id,
        PlanningSnapshot.version == version
    ).first()

    snapshot_b = db.query(PlanningSnapshot).filter(
        PlanningSnapshot.cycle_id == cycle_id,
        PlanningSnapshot.version == comparison.other_version
    ).first()

    if not snapshot_a or not snapshot_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both snapshots not found"
        )

    service = PlanningCycleService(db)
    result = service.compare_snapshots(snapshot_a.id, snapshot_b.id)

    return SnapshotComparisonResponse(
        snapshot_a_id=snapshot_a.id,
        snapshot_a_version=snapshot_a.version,
        snapshot_b_id=snapshot_b.id,
        snapshot_b_version=snapshot_b.version,
        changes_summary=result.get("changes_summary", {}),
        kpi_delta=result.get("kpi_delta"),
        detailed_changes=result.get("detailed_changes") if comparison.include_details else None
    )


# ============================================================================
# Retention Management
# ============================================================================

@router.get("/retention/stats", response_model=RetentionStatsResponse)
def get_retention_stats(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get retention statistics for the user's tenant."""
    service = RetentionService(db)
    stats = service.get_retention_stats(tenant_id=current_user.tenant_id)
    return RetentionStatsResponse(**stats)


@router.post("/retention/run-daily", response_model=dict)
def trigger_daily_retention(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Manually trigger daily retention job (admin only)."""
    # This would typically be admin-only
    from app.services.retention_jobs import trigger_daily_retention_now
    result = trigger_daily_retention_now()
    return result


@router.post("/retention/run-weekly", response_model=dict)
def trigger_weekly_retention(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Manually trigger weekly retention job (admin only)."""
    from app.services.retention_jobs import trigger_weekly_retention_now
    result = trigger_weekly_retention_now()
    return result

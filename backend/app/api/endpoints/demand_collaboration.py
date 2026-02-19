"""
Demand Collaboration API Endpoints
AWS Supply Chain Entity: demand_collaboration

Manages collaborative demand planning (CPFR) with trading partners.

Key Features:
- Share demand forecasts with trading partners
- Consensus planning workflows
- Approval/rejection workflows
- Exception detection and management
- Forecast accuracy tracking

Endpoints:
- POST / - Create collaboration record
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific record
- GET /exceptions - Find exception records
- POST /{id}/submit - Submit for approval
- POST /{id}/approve - Approve collaboration
- POST /{id}/reject - Reject collaboration
- PUT /{id} - Update collaboration
- DELETE /{id} - Delete collaboration record
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date

from app.api import deps
from app.models.user import User
from app.models.demand_collaboration import DemandCollaboration, DemandCollaborationEvent
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class DemandCollaborationCreate(BaseModel):
    """Request schema for creating demand collaboration"""
    product_id: str
    site_id: Optional[str] = None
    tpartner_id: str  # Trading partner ID
    collaboration_date: date
    forecast_quantity: float = Field(gt=0)
    collaboration_type: str = Field(
        default="forecast_share",
        description="forecast_share, consensus, alert, exception"
    )
    baseline_forecast_quantity: Optional[float] = Field(None, ge=0)
    comments: Optional[str] = None


class DemandCollaborationUpdate(BaseModel):
    """Request schema for updating demand collaboration"""
    forecast_quantity: Optional[float] = Field(None, gt=0)
    collaboration_type: Optional[str] = None
    comments: Optional[str] = None
    exception_flag: Optional[bool] = None
    exception_type: Optional[str] = None


class DemandCollaborationSubmit(BaseModel):
    """Request schema for submitting collaboration for approval"""
    comments: Optional[str] = None


class DemandCollaborationApprove(BaseModel):
    """Request schema for approving collaboration"""
    comments: Optional[str] = None


class DemandCollaborationReject(BaseModel):
    """Request schema for rejecting collaboration"""
    rejection_reason: str = Field(min_length=1, max_length=500)
    comments: Optional[str] = None


class DemandCollaborationResponse(BaseModel):
    """Response schema for demand collaboration"""
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    product_id: Optional[str]
    tpartner_id: Optional[str]
    collaboration_date: date
    forecast_quantity: float
    collaboration_type: str
    status: str
    version_number: int
    baseline_forecast_quantity: Optional[float]
    variance_from_baseline: Optional[float]
    submitted_by: Optional[str]
    submitted_at: Optional[datetime]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    rejected_by: Optional[str]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    comments: Optional[str]
    exception_flag: bool
    exception_type: Optional[str]
    actual_demand: Optional[float]
    forecast_accuracy_pct: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExceptionResponse(BaseModel):
    """Exception detection response"""
    id: int
    product_id: Optional[str]
    tpartner_id: Optional[str]
    collaboration_date: date
    forecast_quantity: float
    baseline_forecast_quantity: Optional[float]
    variance_pct: float
    exception_type: str
    status: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=DemandCollaborationResponse)
@require_capabilities(["manage_demand_collaboration"])
async def create_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration: DemandCollaborationCreate
):
    """Create demand collaboration record"""
    company_id = current_user.group_id

    # Calculate variance if baseline provided
    variance = None
    if collaboration.baseline_forecast_quantity and collaboration.baseline_forecast_quantity > 0:
        variance = ((collaboration.forecast_quantity - collaboration.baseline_forecast_quantity) /
                   collaboration.baseline_forecast_quantity) * 100

    demand_collaboration = DemandCollaboration(
        company_id=company_id,
        site_id=collaboration.site_id,
        product_id=collaboration.product_id,
        tpartner_id=collaboration.tpartner_id,
        collaboration_date=collaboration.collaboration_date,
        forecast_quantity=collaboration.forecast_quantity,
        collaboration_type=collaboration.collaboration_type,
        status="draft",
        version_number=1,
        baseline_forecast_quantity=collaboration.baseline_forecast_quantity,
        variance_from_baseline=variance,
        comments=collaboration.comments,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(demand_collaboration)
    await db.commit()
    await db.refresh(demand_collaboration)

    # Create event
    event = DemandCollaborationEvent(
        demand_collaboration_id=demand_collaboration.id,
        event_type="created",
        event_by=current_user.id,
        comment=collaboration.comments
    )
    db.add(event)
    await db.commit()

    return DemandCollaborationResponse.from_orm(demand_collaboration)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_demand_collaboration"])
async def bulk_create_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaborations: List[DemandCollaborationCreate]
):
    """Bulk create demand collaboration records"""
    company_id = current_user.group_id
    created_count = 0

    for collaboration in collaborations:
        variance = None
        if collaboration.baseline_forecast_quantity and collaboration.baseline_forecast_quantity > 0:
            variance = ((collaboration.forecast_quantity - collaboration.baseline_forecast_quantity) /
                       collaboration.baseline_forecast_quantity) * 100

        demand_collaboration = DemandCollaboration(
            company_id=company_id,
            site_id=collaboration.site_id,
            product_id=collaboration.product_id,
            tpartner_id=collaboration.tpartner_id,
            collaboration_date=collaboration.collaboration_date,
            forecast_quantity=collaboration.forecast_quantity,
            collaboration_type=collaboration.collaboration_type,
            status="draft",
            version_number=1,
            baseline_forecast_quantity=collaboration.baseline_forecast_quantity,
            variance_from_baseline=variance,
            comments=collaboration.comments,
            created_by=current_user.id,
            source_update_dttm=datetime.utcnow()
        )
        db.add(demand_collaboration)
        created_count += 1

    await db.commit()

    return {
        "status": "success",
        "created_count": created_count,
        "message": f"Created {created_count} demand collaboration records"
    }


@router.get("/", response_model=List[DemandCollaborationResponse])
@require_capabilities(["view_demand_collaboration"])
async def list_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    tpartner_id: Optional[str] = None,
    collaboration_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(1000, le=10000)
):
    """List demand collaboration records with filtering"""
    stmt = select(DemandCollaboration)

    if product_id:
        stmt = stmt.where(DemandCollaboration.product_id == product_id)

    if site_id:
        stmt = stmt.where(DemandCollaboration.site_id == site_id)

    if tpartner_id:
        stmt = stmt.where(DemandCollaboration.tpartner_id == tpartner_id)

    if collaboration_type:
        stmt = stmt.where(DemandCollaboration.collaboration_type == collaboration_type)

    if status:
        stmt = stmt.where(DemandCollaboration.status == status)

    if start_date:
        stmt = stmt.where(DemandCollaboration.collaboration_date >= start_date)

    if end_date:
        stmt = stmt.where(DemandCollaboration.collaboration_date <= end_date)

    stmt = stmt.order_by(DemandCollaboration.collaboration_date.desc()).limit(limit)

    result = await db.execute(stmt)
    collaborations = result.scalars().all()

    return [DemandCollaborationResponse.from_orm(c) for c in collaborations]


@router.get("/{collaboration_id}", response_model=DemandCollaborationResponse)
@require_capabilities(["view_demand_collaboration"])
async def get_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int
):
    """Get demand collaboration by ID"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    return DemandCollaborationResponse.from_orm(collaboration)


@router.get("/exceptions/detect", response_model=List[ExceptionResponse])
@require_capabilities(["view_demand_collaboration"])
async def detect_exceptions(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    variance_threshold: float = Query(20.0, ge=0, description="Variance threshold percentage"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Detect exception records

    Returns collaboration records with large variances from baseline
    or flagged as exceptions.

    Args:
        variance_threshold: Minimum variance % to flag as exception (default: 20%)
        start_date: Filter start date
        end_date: Filter end date

    Returns:
        List of exception records
    """
    stmt = select(DemandCollaboration).where(
        or_(
            DemandCollaboration.exception_flag == True,
            and_(
                DemandCollaboration.variance_from_baseline != None,
                or_(
                    DemandCollaboration.variance_from_baseline >= variance_threshold,
                    DemandCollaboration.variance_from_baseline <= -variance_threshold
                )
            )
        )
    )

    if start_date:
        stmt = stmt.where(DemandCollaboration.collaboration_date >= start_date)

    if end_date:
        stmt = stmt.where(DemandCollaboration.collaboration_date <= end_date)

    stmt = stmt.order_by(DemandCollaboration.variance_from_baseline.desc())

    result = await db.execute(stmt)
    exceptions = result.scalars().all()

    exception_list = []
    for collab in exceptions:
        exception_type = collab.exception_type or "large_variance"

        exception_list.append(ExceptionResponse(
            id=collab.id,
            product_id=collab.product_id,
            tpartner_id=collab.tpartner_id,
            collaboration_date=collab.collaboration_date,
            forecast_quantity=collab.forecast_quantity,
            baseline_forecast_quantity=collab.baseline_forecast_quantity,
            variance_pct=collab.variance_from_baseline or 0.0,
            exception_type=exception_type,
            status=collab.status
        ))

    return exception_list


@router.post("/{collaboration_id}/submit", response_model=DemandCollaborationResponse)
@require_capabilities(["manage_demand_collaboration"])
async def submit_for_approval(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int,
    submit_data: DemandCollaborationSubmit
):
    """Submit collaboration for approval"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    if collaboration.status not in ["draft", "revised"]:
        raise HTTPException(status_code=400, detail=f"Cannot submit collaboration in status: {collaboration.status}")

    collaboration.status = "submitted"
    collaboration.submitted_by = current_user.id
    collaboration.submitted_at = datetime.utcnow()
    collaboration.updated_by = current_user.id
    collaboration.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(collaboration)

    # Create event
    event = DemandCollaborationEvent(
        demand_collaboration_id=collaboration.id,
        event_type="submitted",
        event_by=current_user.id,
        comment=submit_data.comments
    )
    db.add(event)
    await db.commit()

    return DemandCollaborationResponse.from_orm(collaboration)


@router.post("/{collaboration_id}/approve", response_model=DemandCollaborationResponse)
@require_capabilities(["approve_demand_collaboration"])
async def approve_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int,
    approve_data: DemandCollaborationApprove
):
    """Approve collaboration"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    if collaboration.status != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve collaboration in status: {collaboration.status}")

    collaboration.status = "approved"
    collaboration.approved_by = current_user.id
    collaboration.approved_at = datetime.utcnow()
    collaboration.updated_by = current_user.id
    collaboration.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(collaboration)

    # Create event
    event = DemandCollaborationEvent(
        demand_collaboration_id=collaboration.id,
        event_type="approved",
        event_by=current_user.id,
        comment=approve_data.comments
    )
    db.add(event)
    await db.commit()

    return DemandCollaborationResponse.from_orm(collaboration)


@router.post("/{collaboration_id}/reject", response_model=DemandCollaborationResponse)
@require_capabilities(["approve_demand_collaboration"])
async def reject_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int,
    reject_data: DemandCollaborationReject
):
    """Reject collaboration"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    if collaboration.status != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot reject collaboration in status: {collaboration.status}")

    collaboration.status = "rejected"
    collaboration.rejected_by = current_user.id
    collaboration.rejected_at = datetime.utcnow()
    collaboration.rejection_reason = reject_data.rejection_reason
    collaboration.updated_by = current_user.id
    collaboration.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(collaboration)

    # Create event
    event = DemandCollaborationEvent(
        demand_collaboration_id=collaboration.id,
        event_type="rejected",
        event_by=current_user.id,
        comment=f"{reject_data.rejection_reason}. {reject_data.comments or ''}"
    )
    db.add(event)
    await db.commit()

    return DemandCollaborationResponse.from_orm(collaboration)


@router.put("/{collaboration_id}", response_model=DemandCollaborationResponse)
@require_capabilities(["manage_demand_collaboration"])
async def update_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int,
    collaboration_update: DemandCollaborationUpdate
):
    """Update demand collaboration"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    # Update fields
    if collaboration_update.forecast_quantity is not None:
        old_qty = collaboration.forecast_quantity
        collaboration.forecast_quantity = collaboration_update.forecast_quantity

        # Recalculate variance
        if collaboration.baseline_forecast_quantity and collaboration.baseline_forecast_quantity > 0:
            collaboration.variance_from_baseline = (
                (collaboration.forecast_quantity - collaboration.baseline_forecast_quantity) /
                collaboration.baseline_forecast_quantity
            ) * 100

        # Increment version if quantity changed
        if old_qty != collaboration.forecast_quantity:
            collaboration.version_number += 1

    if collaboration_update.collaboration_type is not None:
        collaboration.collaboration_type = collaboration_update.collaboration_type

    if collaboration_update.comments is not None:
        collaboration.comments = collaboration_update.comments

    if collaboration_update.exception_flag is not None:
        collaboration.exception_flag = collaboration_update.exception_flag

    if collaboration_update.exception_type is not None:
        collaboration.exception_type = collaboration_update.exception_type

    collaboration.updated_by = current_user.id
    collaboration.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(collaboration)

    # Create event
    event = DemandCollaborationEvent(
        demand_collaboration_id=collaboration.id,
        event_type="revised",
        event_by=current_user.id,
        comment=collaboration_update.comments
    )
    db.add(event)
    await db.commit()

    return DemandCollaborationResponse.from_orm(collaboration)


@router.delete("/{collaboration_id}")
@require_capabilities(["manage_demand_collaboration"])
async def delete_demand_collaboration(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    collaboration_id: int
):
    """Delete demand collaboration record"""
    stmt = select(DemandCollaboration).where(DemandCollaboration.id == collaboration_id)
    result = await db.execute(stmt)
    collaboration = result.scalar_one_or_none()

    if not collaboration:
        raise HTTPException(status_code=404, detail=f"Demand collaboration {collaboration_id} not found")

    await db.delete(collaboration)
    await db.commit()

    return {"status": "success", "message": f"Demand collaboration {collaboration_id} deleted"}

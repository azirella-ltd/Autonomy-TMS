"""
Resource Capacity API Endpoints
AWS Supply Chain Entity: resource_capacity

Manages production capacity at resource level for capacity planning and bottleneck analysis.

Key Features:
- Track available vs utilized capacity
- Monitor capacity utilization
- Identify bottlenecks
- Support finite capacity planning

Endpoints:
- POST / - Create capacity record
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific record
- GET /utilization - Capacity utilization analysis
- GET /bottlenecks - Identify bottleneck resources
- PUT /{id} - Update capacity
- DELETE /{id} - Delete capacity record
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from app.api import deps
from app.models.user import User
from app.models.resource_capacity import ResourceCapacity
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ResourceCapacityCreate(BaseModel):
    """Request schema for creating resource capacity"""
    resource_id: str
    resource_name: Optional[str] = None
    resource_type: Optional[str] = Field(None, description="machine, labor, equipment, facility")
    site_id: Optional[str] = None
    capacity_date: date
    available_capacity_hours: float = Field(gt=0)
    capacity_efficiency: float = Field(default=1.0, ge=0, le=1.0)
    planned_downtime_hours: float = Field(default=0.0, ge=0)
    overtime_hours: float = Field(default=0.0, ge=0)


class ResourceCapacityUpdate(BaseModel):
    """Request schema for updating resource capacity"""
    available_capacity_hours: Optional[float] = Field(None, gt=0)
    utilized_capacity_hours: Optional[float] = Field(None, ge=0)
    capacity_efficiency: Optional[float] = Field(None, ge=0, le=1.0)
    planned_downtime_hours: Optional[float] = Field(None, ge=0)
    unplanned_downtime_hours: Optional[float] = Field(None, ge=0)


class ResourceCapacityResponse(BaseModel):
    """Response schema for resource capacity"""
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    resource_id: str
    resource_name: Optional[str]
    resource_type: Optional[str]
    capacity_date: date
    available_capacity_hours: float
    utilized_capacity_hours: float
    remaining_capacity_hours: float
    capacity_efficiency: float
    planned_downtime_hours: Optional[float]
    unplanned_downtime_hours: Optional[float]
    overtime_hours: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CapacityUtilizationResponse(BaseModel):
    """Capacity utilization analysis"""
    resource_id: str
    resource_name: Optional[str]
    total_available_hours: float
    total_utilized_hours: float
    utilization_pct: float
    bottleneck_score: float  # 0-100, higher = more constrained


class BottleneckAnalysisResponse(BaseModel):
    """Bottleneck analysis results"""
    resource_id: str
    resource_name: Optional[str]
    avg_utilization_pct: float
    days_at_capacity: int  # Days with >95% utilization
    bottleneck_severity: str  # low, medium, high, critical


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=ResourceCapacityResponse)
@require_capabilities(["manage_resource_capacity"])
async def create_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    capacity: ResourceCapacityCreate
):
    """Create resource capacity record"""
    company_id = current_user.tenant_id

    # Calculate remaining capacity
    effective_available = capacity.available_capacity_hours * capacity.capacity_efficiency
    effective_available -= capacity.planned_downtime_hours
    remaining = max(0.0, effective_available)

    resource_capacity = ResourceCapacity(
        company_id=company_id,
        site_id=capacity.site_id,
        resource_id=capacity.resource_id,
        resource_name=capacity.resource_name,
        resource_type=capacity.resource_type,
        capacity_date=capacity.capacity_date,
        available_capacity_hours=capacity.available_capacity_hours,
        utilized_capacity_hours=0.0,
        remaining_capacity_hours=remaining,
        capacity_efficiency=capacity.capacity_efficiency,
        planned_downtime_hours=capacity.planned_downtime_hours,
        overtime_hours=capacity.overtime_hours,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(resource_capacity)
    await db.commit()
    await db.refresh(resource_capacity)

    return ResourceCapacityResponse.from_orm(resource_capacity)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_resource_capacity"])
async def bulk_create_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    capacities: List[ResourceCapacityCreate]
):
    """Bulk create resource capacity records"""
    company_id = current_user.tenant_id
    created_count = 0

    for capacity in capacities:
        effective_available = capacity.available_capacity_hours * capacity.capacity_efficiency
        effective_available -= capacity.planned_downtime_hours
        remaining = max(0.0, effective_available)

        resource_capacity = ResourceCapacity(
            company_id=company_id,
            site_id=capacity.site_id,
            resource_id=capacity.resource_id,
            resource_name=capacity.resource_name,
            resource_type=capacity.resource_type,
            capacity_date=capacity.capacity_date,
            available_capacity_hours=capacity.available_capacity_hours,
            utilized_capacity_hours=0.0,
            remaining_capacity_hours=remaining,
            capacity_efficiency=capacity.capacity_efficiency,
            planned_downtime_hours=capacity.planned_downtime_hours,
            overtime_hours=capacity.overtime_hours,
            created_by=current_user.id,
            source_update_dttm=datetime.utcnow()
        )
        db.add(resource_capacity)
        created_count += 1

    await db.commit()

    return {
        "status": "success",
        "created_count": created_count,
        "message": f"Created {created_count} resource capacity records"
    }


@router.get("/", response_model=List[ResourceCapacityResponse])
@require_capabilities(["view_resource_capacity"])
async def list_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    resource_id: Optional[str] = None,
    site_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(1000, le=10000)
):
    """List resource capacity records with filtering"""
    stmt = select(ResourceCapacity)

    if resource_id:
        stmt = stmt.where(ResourceCapacity.resource_id == resource_id)

    if site_id:
        stmt = stmt.where(ResourceCapacity.site_id == site_id)

    if start_date:
        stmt = stmt.where(ResourceCapacity.capacity_date >= start_date)

    if end_date:
        stmt = stmt.where(ResourceCapacity.capacity_date <= end_date)

    stmt = stmt.order_by(ResourceCapacity.capacity_date, ResourceCapacity.resource_id).limit(limit)

    result = await db.execute(stmt)
    capacities = result.scalars().all()

    return [ResourceCapacityResponse.from_orm(c) for c in capacities]


@router.get("/{capacity_id}", response_model=ResourceCapacityResponse)
@require_capabilities(["view_resource_capacity"])
async def get_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    capacity_id: int
):
    """Get resource capacity by ID"""
    stmt = select(ResourceCapacity).where(ResourceCapacity.id == capacity_id)
    result = await db.execute(stmt)
    capacity = result.scalar_one_or_none()

    if not capacity:
        raise HTTPException(status_code=404, detail=f"Resource capacity {capacity_id} not found")

    return ResourceCapacityResponse.from_orm(capacity)


@router.get("/utilization/analysis", response_model=List[CapacityUtilizationResponse])
@require_capabilities(["view_resource_capacity"])
async def get_capacity_utilization(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_utilization: float = Query(0.0, ge=0, le=100)
):
    """
    Capacity utilization analysis

    Returns utilization metrics per resource, sorted by utilization percentage.
    Helps identify overutilized and underutilized resources.

    Args:
        start_date: Analysis start date
        end_date: Analysis end date
        min_utilization: Minimum utilization % to include

    Returns:
        List of resource utilization metrics
    """
    stmt = select(
        ResourceCapacity.resource_id,
        ResourceCapacity.resource_name,
        func.sum(ResourceCapacity.available_capacity_hours).label('total_available'),
        func.sum(ResourceCapacity.utilized_capacity_hours).label('total_utilized')
    )

    if start_date:
        stmt = stmt.where(ResourceCapacity.capacity_date >= start_date)

    if end_date:
        stmt = stmt.where(ResourceCapacity.capacity_date <= end_date)

    stmt = stmt.group_by(ResourceCapacity.resource_id, ResourceCapacity.resource_name)

    result = await db.execute(stmt)
    utilization_data = result.all()

    utilizations = []
    for row in utilization_data:
        total_available = float(row.total_available or 0)
        total_utilized = float(row.total_utilized or 0)
        utilization_pct = (total_utilized / total_available * 100) if total_available > 0 else 0.0

        if utilization_pct >= min_utilization:
            # Bottleneck score: higher utilization = higher score
            bottleneck_score = min(100.0, utilization_pct * 1.2)  # Scale up to emphasize high utilization

            utilizations.append(CapacityUtilizationResponse(
                resource_id=row.resource_id,
                resource_name=row.resource_name,
                total_available_hours=total_available,
                total_utilized_hours=total_utilized,
                utilization_pct=utilization_pct,
                bottleneck_score=bottleneck_score
            ))

    # Sort by utilization percentage descending
    utilizations.sort(key=lambda x: x.utilization_pct, reverse=True)

    return utilizations


@router.get("/bottlenecks/identify", response_model=List[BottleneckAnalysisResponse])
@require_capabilities(["view_resource_capacity"])
async def identify_bottlenecks(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    threshold_pct: float = Query(95.0, ge=0, le=100, description="Utilization threshold for bottleneck")
):
    """
    Identify bottleneck resources

    Returns resources with consistently high utilization that may constrain production.

    Args:
        start_date: Analysis start date
        end_date: Analysis end date
        threshold_pct: Utilization threshold (default: 95%)

    Returns:
        List of bottleneck resources with severity classification
    """
    stmt = select(ResourceCapacity)

    if start_date:
        stmt = stmt.where(ResourceCapacity.capacity_date >= start_date)

    if end_date:
        stmt = stmt.where(ResourceCapacity.capacity_date <= end_date)

    result = await db.execute(stmt)
    capacities = result.scalars().all()

    # Group by resource
    resource_data = {}
    for capacity in capacities:
        resource_id = capacity.resource_id
        if resource_id not in resource_data:
            resource_data[resource_id] = {
                'resource_name': capacity.resource_name,
                'utilization_pcts': [],
                'days_at_capacity': 0
            }

        # Calculate utilization for this day
        if capacity.available_capacity_hours > 0:
            util_pct = (capacity.utilized_capacity_hours / capacity.available_capacity_hours) * 100
            resource_data[resource_id]['utilization_pcts'].append(util_pct)

            if util_pct >= threshold_pct:
                resource_data[resource_id]['days_at_capacity'] += 1

    # Analyze bottlenecks
    bottlenecks = []
    for resource_id, data in resource_data.items():
        if not data['utilization_pcts']:
            continue

        avg_util = sum(data['utilization_pcts']) / len(data['utilization_pcts'])
        days_at_capacity = data['days_at_capacity']

        # Classify severity
        if avg_util >= 98 and days_at_capacity >= 5:
            severity = "critical"
        elif avg_util >= 95 and days_at_capacity >= 3:
            severity = "high"
        elif avg_util >= 90 and days_at_capacity >= 2:
            severity = "medium"
        elif avg_util >= 80:
            severity = "low"
        else:
            continue  # Not a bottleneck

        bottlenecks.append(BottleneckAnalysisResponse(
            resource_id=resource_id,
            resource_name=data['resource_name'],
            avg_utilization_pct=avg_util,
            days_at_capacity=days_at_capacity,
            bottleneck_severity=severity
        ))

    # Sort by severity and utilization
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    bottlenecks.sort(key=lambda x: (severity_order[x.bottleneck_severity], -x.avg_utilization_pct))

    return bottlenecks


@router.put("/{capacity_id}", response_model=ResourceCapacityResponse)
@require_capabilities(["manage_resource_capacity"])
async def update_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    capacity_id: int,
    capacity_update: ResourceCapacityUpdate
):
    """Update resource capacity"""
    stmt = select(ResourceCapacity).where(ResourceCapacity.id == capacity_id)
    result = await db.execute(stmt)
    capacity = result.scalar_one_or_none()

    if not capacity:
        raise HTTPException(status_code=404, detail=f"Resource capacity {capacity_id} not found")

    # Update fields
    if capacity_update.available_capacity_hours is not None:
        capacity.available_capacity_hours = capacity_update.available_capacity_hours

    if capacity_update.utilized_capacity_hours is not None:
        capacity.utilized_capacity_hours = capacity_update.utilized_capacity_hours

    if capacity_update.capacity_efficiency is not None:
        capacity.capacity_efficiency = capacity_update.capacity_efficiency

    if capacity_update.planned_downtime_hours is not None:
        capacity.planned_downtime_hours = capacity_update.planned_downtime_hours

    if capacity_update.unplanned_downtime_hours is not None:
        capacity.unplanned_downtime_hours = capacity_update.unplanned_downtime_hours

    # Recalculate remaining capacity
    effective_available = capacity.available_capacity_hours * capacity.capacity_efficiency
    effective_available -= (capacity.planned_downtime_hours or 0.0)
    effective_available -= (capacity.unplanned_downtime_hours or 0.0)
    capacity.remaining_capacity_hours = max(0.0, effective_available - capacity.utilized_capacity_hours)

    capacity.updated_by = current_user.id
    capacity.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(capacity)

    return ResourceCapacityResponse.from_orm(capacity)


@router.delete("/{capacity_id}")
@require_capabilities(["manage_resource_capacity"])
async def delete_resource_capacity(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    capacity_id: int
):
    """Delete resource capacity record"""
    stmt = select(ResourceCapacity).where(ResourceCapacity.id == capacity_id)
    result = await db.execute(stmt)
    capacity = result.scalar_one_or_none()

    if not capacity:
        raise HTTPException(status_code=404, detail=f"Resource capacity {capacity_id} not found")

    await db.delete(capacity)
    await db.commit()

    return {"status": "success", "message": f"Resource capacity {capacity_id} deleted"}

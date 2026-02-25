"""
Service Order API Endpoints
AWS Supply Chain Entity: service_order

Manages corrective maintenance and repair orders.

Key Features:
- Create and track service orders
- Priority-based scheduling
- Downtime impact tracking
- Cost tracking (labor + parts)
- SLA monitoring

Endpoints:
- POST / - Create service order
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific order
- GET /overdue - Find overdue orders
- GET /critical - Find critical priority orders
- POST /{id}/assign - Assign technician
- POST /{id}/start - Start service work
- POST /{id}/complete - Complete service
- PUT /{id} - Update order
- DELETE /{id} - Cancel order
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from app.api import deps
from app.models.user import User
from app.models.service_order import ServiceOrder
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ServiceOrderCreate(BaseModel):
    """Request schema for creating service order"""
    service_order_id: str
    resource_id: str
    site_id: Optional[str] = None
    service_order_type: str = Field(description="breakdown, repair, warranty, calibration, inspection")
    service_date: date
    priority: str = Field(default="medium", description="critical, high, medium, low")
    is_emergency: bool = Field(default=False)
    service_provider_type: str = Field(default="internal", description="internal, external_vendor, oem")
    service_provider_id: Optional[str] = None
    problem_description: Optional[str] = None
    estimated_labor_hours: Optional[float] = Field(None, ge=0)
    parts_required: Optional[str] = None


class ServiceOrderUpdate(BaseModel):
    """Request schema for updating service order"""
    status: Optional[str] = None
    problem_description: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_description: Optional[str] = None
    actual_labor_hours: Optional[float] = Field(None, ge=0)
    labor_cost: Optional[float] = Field(None, ge=0)
    parts_cost: Optional[float] = Field(None, ge=0)
    actual_downtime_hours: Optional[float] = Field(None, ge=0)
    parts_availability: Optional[str] = None


class ServiceOrderAssign(BaseModel):
    """Request schema for assigning service order"""
    assigned_technician: str
    planned_downtime_hours: Optional[float] = Field(None, ge=0)


class ServiceOrderComplete(BaseModel):
    """Request schema for completing service order"""
    completion_date: date
    root_cause: Optional[str] = None
    resolution_description: str
    actual_labor_hours: float = Field(ge=0)
    labor_cost: float = Field(ge=0)
    parts_cost: float = Field(ge=0)
    actual_downtime_hours: float = Field(ge=0)


class ServiceOrderResponse(BaseModel):
    """Response schema for service order"""
    id: int
    company_id: Optional[str]
    site_id: Optional[str]
    resource_id: str
    service_order_id: str
    service_order_type: str
    service_date: date
    completion_date: Optional[date]
    status: str
    priority: str
    is_emergency: bool
    service_provider_type: str
    service_provider_id: Optional[str]
    problem_description: Optional[str]
    root_cause: Optional[str]
    resolution_description: Optional[str]
    estimated_labor_hours: Optional[float]
    actual_labor_hours: Optional[float]
    labor_cost: Optional[float]
    parts_cost: Optional[float]
    total_cost: Optional[float]
    planned_downtime_hours: Optional[float]
    actual_downtime_hours: Optional[float]
    assigned_technician: Optional[str]
    assigned_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OverdueServiceOrderResponse(BaseModel):
    """Overdue service order summary"""
    id: int
    service_order_id: str
    resource_id: str
    service_date: date
    days_overdue: int
    priority: str
    status: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=ServiceOrderResponse)
@require_capabilities(["manage_service_orders"])
async def create_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order: ServiceOrderCreate
):
    """Create service order"""
    company_id = current_user.customer_id

    service_order = ServiceOrder(
        company_id=company_id,
        site_id=order.site_id,
        resource_id=order.resource_id,
        service_order_id=order.service_order_id,
        service_order_type=order.service_order_type,
        service_date=order.service_date,
        requested_date=date.today(),
        status="open",
        priority=order.priority,
        is_emergency=order.is_emergency,
        service_provider_type=order.service_provider_type,
        service_provider_id=order.service_provider_id,
        problem_description=order.problem_description,
        estimated_labor_hours=order.estimated_labor_hours,
        parts_required=order.parts_required,
        created_by=current_user.id,
        source_update_dttm=datetime.utcnow()
    )

    db.add(service_order)
    await db.commit()
    await db.refresh(service_order)

    return ServiceOrderResponse.from_orm(service_order)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_service_orders"])
async def bulk_create_service_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    orders: List[ServiceOrderCreate]
):
    """Bulk create service orders"""
    company_id = current_user.customer_id
    created_count = 0

    for order in orders:
        service_order = ServiceOrder(
            company_id=company_id,
            site_id=order.site_id,
            resource_id=order.resource_id,
            service_order_id=order.service_order_id,
            service_order_type=order.service_order_type,
            service_date=order.service_date,
            requested_date=date.today(),
            status="open",
            priority=order.priority,
            is_emergency=order.is_emergency,
            service_provider_type=order.service_provider_type,
            service_provider_id=order.service_provider_id,
            problem_description=order.problem_description,
            estimated_labor_hours=order.estimated_labor_hours,
            parts_required=order.parts_required,
            created_by=current_user.id,
            source_update_dttm=datetime.utcnow()
        )
        db.add(service_order)
        created_count += 1

    await db.commit()

    return {
        "status": "success",
        "created_count": created_count,
        "message": f"Created {created_count} service orders"
    }


@router.get("/", response_model=List[ServiceOrderResponse])
@require_capabilities(["view_service_orders"])
async def list_service_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    resource_id: Optional[str] = None,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    service_provider_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(1000, le=10000)
):
    """List service orders with filtering"""
    stmt = select(ServiceOrder)

    if resource_id:
        stmt = stmt.where(ServiceOrder.resource_id == resource_id)

    if site_id:
        stmt = stmt.where(ServiceOrder.site_id == site_id)

    if status:
        stmt = stmt.where(ServiceOrder.status == status)

    if priority:
        stmt = stmt.where(ServiceOrder.priority == priority)

    if service_provider_type:
        stmt = stmt.where(ServiceOrder.service_provider_type == service_provider_type)

    if start_date:
        stmt = stmt.where(ServiceOrder.service_date >= start_date)

    if end_date:
        stmt = stmt.where(ServiceOrder.service_date <= end_date)

    stmt = stmt.order_by(ServiceOrder.service_date, ServiceOrder.priority).limit(limit)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    return [ServiceOrderResponse.from_orm(o) for o in orders]


@router.get("/{order_id}", response_model=ServiceOrderResponse)
@require_capabilities(["view_service_orders"])
async def get_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """Get service order by ID"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    return ServiceOrderResponse.from_orm(order)


@router.get("/overdue/list", response_model=List[OverdueServiceOrderResponse])
@require_capabilities(["view_service_orders"])
async def get_overdue_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Find overdue service orders"""
    stmt = select(ServiceOrder).where(
        and_(
            ServiceOrder.status.in_(['open', 'assigned', 'in_progress']),
            ServiceOrder.service_date < date.today()
        )
    ).order_by(ServiceOrder.service_date)

    result = await db.execute(stmt)
    overdue_orders = result.scalars().all()

    overdue_list = []
    for order in overdue_orders:
        days_overdue = (date.today() - order.service_date).days
        overdue_list.append(OverdueServiceOrderResponse(
            id=order.id,
            service_order_id=order.service_order_id,
            resource_id=order.resource_id,
            service_date=order.service_date,
            days_overdue=days_overdue,
            priority=order.priority,
            status=order.status
        ))

    return overdue_list


@router.get("/critical/list", response_model=List[ServiceOrderResponse])
@require_capabilities(["view_service_orders"])
async def get_critical_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Find critical priority service orders"""
    stmt = select(ServiceOrder).where(
        and_(
            ServiceOrder.priority.in_(['critical', 'high']),
            ServiceOrder.status.in_(['open', 'assigned', 'in_progress'])
        )
    ).order_by(ServiceOrder.priority, ServiceOrder.service_date)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    return [ServiceOrderResponse.from_orm(o) for o in orders]


@router.post("/{order_id}/assign", response_model=ServiceOrderResponse)
@require_capabilities(["manage_service_orders"])
async def assign_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    assignment: ServiceOrderAssign
):
    """Assign service order to technician"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    if order.status not in ['open']:
        raise HTTPException(status_code=400, detail=f"Cannot assign order in status: {order.status}")

    order.assigned_technician = assignment.assigned_technician
    order.assigned_at = datetime.utcnow()
    order.planned_downtime_hours = assignment.planned_downtime_hours
    order.status = "assigned"
    order.updated_by = current_user.id
    order.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(order)

    return ServiceOrderResponse.from_orm(order)


@router.post("/{order_id}/start", response_model=ServiceOrderResponse)
@require_capabilities(["manage_service_orders"])
async def start_service_work(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """Start service work"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    if order.status not in ['assigned']:
        raise HTTPException(status_code=400, detail=f"Cannot start order in status: {order.status}")

    order.started_at = datetime.utcnow()
    order.status = "in_progress"
    order.updated_by = current_user.id
    order.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(order)

    return ServiceOrderResponse.from_orm(order)


@router.post("/{order_id}/complete", response_model=ServiceOrderResponse)
@require_capabilities(["manage_service_orders"])
async def complete_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    completion: ServiceOrderComplete
):
    """Complete service order"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    if order.status not in ['in_progress']:
        raise HTTPException(status_code=400, detail=f"Cannot complete order in status: {order.status}")

    order.completion_date = completion.completion_date
    order.completed_at = datetime.utcnow()
    order.root_cause = completion.root_cause
    order.resolution_description = completion.resolution_description
    order.actual_labor_hours = completion.actual_labor_hours
    order.labor_cost = completion.labor_cost
    order.parts_cost = completion.parts_cost
    order.total_cost = completion.labor_cost + completion.parts_cost
    order.actual_downtime_hours = completion.actual_downtime_hours
    order.status = "completed"
    order.updated_by = current_user.id
    order.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(order)

    return ServiceOrderResponse.from_orm(order)


@router.put("/{order_id}", response_model=ServiceOrderResponse)
@require_capabilities(["manage_service_orders"])
async def update_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    order_update: ServiceOrderUpdate
):
    """Update service order"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    # Update fields
    if order_update.status is not None:
        order.status = order_update.status

    if order_update.problem_description is not None:
        order.problem_description = order_update.problem_description

    if order_update.root_cause is not None:
        order.root_cause = order_update.root_cause

    if order_update.resolution_description is not None:
        order.resolution_description = order_update.resolution_description

    if order_update.actual_labor_hours is not None:
        order.actual_labor_hours = order_update.actual_labor_hours

    if order_update.labor_cost is not None:
        order.labor_cost = order_update.labor_cost

    if order_update.parts_cost is not None:
        order.parts_cost = order_update.parts_cost

    # Recalculate total cost
    if order.labor_cost is not None and order.parts_cost is not None:
        order.total_cost = order.labor_cost + order.parts_cost

    if order_update.actual_downtime_hours is not None:
        order.actual_downtime_hours = order_update.actual_downtime_hours

    if order_update.parts_availability is not None:
        order.parts_availability = order_update.parts_availability

    order.updated_by = current_user.id
    order.source_update_dttm = datetime.utcnow()

    await db.commit()
    await db.refresh(order)

    return ServiceOrderResponse.from_orm(order)


@router.delete("/{order_id}")
@require_capabilities(["manage_service_orders"])
async def cancel_service_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """Cancel service order"""
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail=f"Service order {order_id} not found")

    order.status = "cancelled"
    order.updated_by = current_user.id
    order.source_update_dttm = datetime.utcnow()

    await db.commit()

    return {"status": "success", "message": f"Service order {order_id} cancelled"}

"""
Project Orders API Endpoints
Sprint 6: Additional Order Types

Provides endpoints for project order management:
- Create and manage project orders
- Track project completion
- Manage project order line items
- Project-based material planning
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date

from app.api import deps
from app.core.clock import tenant_today
from app.models.user import User
from app.models.project_order import ProjectOrder, ProjectOrderLineItem
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ProjectOrderLineItemSchema(BaseModel):
    """Schema for project order line item"""
    line_number: int
    product_id: str
    product_description: Optional[str] = None
    quantity_required: float
    uom: str = "EA"
    required_date: date
    unit_cost: Optional[float] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ProjectOrderCreateSchema(BaseModel):
    """Schema for creating project order"""
    project_id: str = Field(..., description="Project identifier")
    project_name: str = Field(..., description="Project name")
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    site_id: str = Field(..., description="Production/execution site")
    required_completion_date: date
    project_type: Optional[str] = "MTO"
    priority: str = "NORMAL"
    contract_number: Optional[str] = None
    contract_value: Optional[float] = None
    estimated_hours: Optional[float] = None
    estimated_cost: Optional[float] = None
    description: Optional[str] = None
    special_requirements: Optional[str] = None
    milestones: Optional[List] = None
    line_items: List[ProjectOrderLineItemSchema] = []


class ProjectOrderUpdateSchema(BaseModel):
    """Schema for updating project order"""
    status: Optional[str] = None
    priority: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_completion_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_completion_date: Optional[date] = None
    completion_percentage: Optional[float] = None
    actual_hours: Optional[float] = None
    actual_cost: Optional[float] = None
    milestones: Optional[List] = None
    notes: Optional[str] = None


class ProjectOrderResponse(BaseModel):
    """Response schema for project order"""
    id: int
    project_order_number: str
    project_id: str
    project_name: str
    customer_id: Optional[str]
    customer_name: Optional[str]
    site_id: str
    status: str
    priority: str
    order_date: str
    required_completion_date: str
    actual_completion_date: Optional[str]
    completion_percentage: float
    contract_value: Optional[float]
    estimated_cost: Optional[float]
    actual_cost: Optional[float]
    milestones: List
    created_at: str

    class Config:
        from_attributes = True


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/", response_model=List[ProjectOrderResponse])
@require_capabilities(["view_project_orders"])
async def get_project_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    project_id: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(PLANNED|APPROVED|IN_PROGRESS|ON_HOLD|COMPLETED|CANCELLED)$"),
    priority: Optional[str] = Query(None, pattern="^(LOW|NORMAL|HIGH|CRITICAL)$"),
    limit: int = Query(100, le=500)
):
    """
    Get project orders with optional filtering

    Args:
        project_id: Filter by project ID
        customer_id: Filter by customer
        site_id: Filter by site
        status: Filter by status
        priority: Filter by priority
        limit: Maximum number of orders to return

    Returns:
        List of project orders sorted by required completion date
    """
    stmt = select(ProjectOrder)

    # Apply filters
    if project_id:
        stmt = stmt.where(ProjectOrder.project_id == project_id)

    if customer_id:
        stmt = stmt.where(ProjectOrder.customer_id == customer_id)

    if site_id:
        stmt = stmt.where(ProjectOrder.site_id == site_id)

    if status:
        stmt = stmt.where(ProjectOrder.status == status)

    if priority:
        stmt = stmt.where(ProjectOrder.priority == priority)

    # Order by completion date and priority
    stmt = stmt.order_by(
        ProjectOrder.required_completion_date.asc(),
        desc(ProjectOrder.priority)
    ).limit(limit)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    return [ProjectOrderResponse(**order.to_dict()) for order in orders]


@router.post("/", response_model=ProjectOrderResponse, status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_project_orders"])
async def create_project_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_data: ProjectOrderCreateSchema
):
    """
    Create new project order

    Args:
        order_data: Project order details with line items

    Returns:
        Created project order
    """
    try:
        # Generate project order number
        import uuid
        order_number = f"PROJ-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Create project order
        project_order = ProjectOrder(
            project_order_number=order_number,
            project_id=order_data.project_id,
            project_name=order_data.project_name,
            customer_id=order_data.customer_id,
            customer_name=order_data.customer_name,
            site_id=order_data.site_id,
            status="PLANNED",
            order_date=await tenant_today(current_user.tenant_id, db),
            required_completion_date=order_data.required_completion_date,
            project_type=order_data.project_type,
            priority=order_data.priority,
            contract_number=order_data.contract_number,
            contract_value=order_data.contract_value,
            estimated_hours=order_data.estimated_hours,
            estimated_cost=order_data.estimated_cost,
            description=order_data.description,
            special_requirements=order_data.special_requirements,
            milestones=order_data.milestones or [],
            completion_percentage=0.0,
            created_by_id=current_user.id
        )

        db.add(project_order)
        await db.flush()  # Get the ID

        # Create line items
        for line in order_data.line_items:
            line_item = ProjectOrderLineItem(
                project_order_id=project_order.id,
                line_number=line.line_number,
                product_id=line.product_id,
                product_description=line.product_description,
                quantity_required=line.quantity_required,
                uom=line.uom,
                required_date=line.required_date,
                unit_cost=line.unit_cost,
                notes=line.notes,
                status="PENDING"
            )
            db.add(line_item)

        await db.commit()
        await db.refresh(project_order)

        return ProjectOrderResponse(**project_order.to_dict())

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project order: {str(e)}"
        )


@router.get("/{order_id}", response_model=ProjectOrderResponse)
@require_capabilities(["view_project_orders"])
async def get_project_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """
    Get project order by ID

    Args:
        order_id: Project order ID

    Returns:
        Project order details
    """
    stmt = select(ProjectOrder).where(ProjectOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project order {order_id} not found"
        )

    return ProjectOrderResponse(**order.to_dict())


@router.put("/{order_id}", response_model=ProjectOrderResponse)
@require_capabilities(["manage_project_orders"])
async def update_project_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    order_update: ProjectOrderUpdateSchema
):
    """
    Update project order

    Args:
        order_id: Project order ID
        order_update: Fields to update

    Returns:
        Updated project order
    """
    stmt = select(ProjectOrder).where(ProjectOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project order {order_id} not found"
        )

    try:
        # Update fields
        update_data = order_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(order, field, value)

        # Auto-set timestamps based on status changes
        if order_update.status:
            if order_update.status == "APPROVED":
                order.approved_at = datetime.now()
                order.approved_by_id = current_user.id
            elif order_update.status == "IN_PROGRESS" and not order.started_at:
                order.started_at = datetime.now()
            elif order_update.status == "COMPLETED":
                order.completed_at = datetime.now()
                order.completed_by_id = current_user.id
                order.completion_percentage = 100.0

        await db.commit()
        await db.refresh(order)

        return ProjectOrderResponse(**order.to_dict())

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project order: {str(e)}"
        )


@router.post("/{order_id}/approve")
@require_capabilities(["approve_project_orders"])
async def approve_project_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """
    Approve project order

    Args:
        order_id: Project order ID

    Returns:
        Approved project order
    """
    stmt = select(ProjectOrder).where(ProjectOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project order {order_id} not found"
        )

    if order.status != "PLANNED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PLANNED orders can be approved. Current status: {order.status}"
        )

    try:
        order.status = "APPROVED"
        order.approved_at = datetime.now()
        order.approved_by_id = current_user.id

        await db.commit()
        await db.refresh(order)

        return ProjectOrderResponse(**order.to_dict())

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve project order: {str(e)}"
        )


@router.get("/{order_id}/line-items", response_model=List[ProjectOrderLineItemSchema])
@require_capabilities(["view_project_orders"])
async def get_project_order_line_items(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """
    Get project order line items

    Args:
        order_id: Project order ID

    Returns:
        List of line items
    """
    stmt = select(ProjectOrderLineItem).where(
        ProjectOrderLineItem.project_order_id == order_id
    ).order_by(ProjectOrderLineItem.line_number)

    result = await db.execute(stmt)
    line_items = result.scalars().all()

    return [ProjectOrderLineItemSchema(**item.to_dict()) for item in line_items]


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_capabilities(["manage_project_orders"])
async def delete_project_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """
    Delete (cancel) project order

    Args:
        order_id: Project order ID

    Returns:
        No content
    """
    stmt = select(ProjectOrder).where(ProjectOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project order {order_id} not found"
        )

    try:
        order.status = "CANCELLED"
        order.cancelled_at = datetime.now()
        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel project order: {str(e)}"
        )

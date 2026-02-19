"""
Production Orders API Endpoints

Manages production order lifecycle following Supply Chain data model.
Supports CRUD operations and workflow transitions (release, start, complete, close, cancel).
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.production_order import ProductionOrder, ProductionOrderComponent
from app.models.mps import MPSPlan
from app.models.supply_chain_config import Node
from app.models.sc_entities import Product
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from app.schemas.production_order import (
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionOrderResponse,
    ProductionOrderListResponse,
    ProductionOrderRelease,
    ProductionOrderStart,
    ProductionOrderComplete,
    ProductionOrderClose,
    ProductionOrderCancel,
    ProductionOrderFilters,
    ProductionOrderSummary,
    ProductionOrderComponentCreate,
    ProductionOrderComponentUpdate,
)

router = APIRouter()


# ============================================================================
# Helper Functions
# ============================================================================

def _get_production_order_or_404(
    db: Session,
    order_id: int,
    user: User,
    require_editable: bool = False
) -> ProductionOrder:
    """
    Get production order by ID or raise 404.

    Args:
        db: Database session
        order_id: Production order ID
        user: Current user
        require_editable: If True, only return if status is editable (PLANNED/RELEASED)

    Returns:
        ProductionOrder instance

    Raises:
        HTTPException: 404 if not found, 400 if not editable when required
    """
    order = db.query(ProductionOrder).filter(
        ProductionOrder.id == order_id,
        ProductionOrder.is_deleted == False
    ).options(
        joinedload(ProductionOrder.item),
        joinedload(ProductionOrder.site),
        joinedload(ProductionOrder.mps_plan),
        joinedload(ProductionOrder.components)
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")

    if require_editable and order.status not in ["PLANNED", "RELEASED"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit production order in status: {order.status}"
        )

    return order


def _generate_order_number(db: Session, site_id: int) -> str:
    """Generate unique production order number."""
    # Format: PO-{SITE_ID}-{YYYYMMDD}-{SEQ}
    today = datetime.utcnow().strftime("%Y%m%d")

    # Find highest sequence number for today at this site
    last_order = db.query(ProductionOrder).filter(
        ProductionOrder.site_id == site_id,
        ProductionOrder.order_number.like(f"PO-{site_id}-{today}-%")
    ).order_by(ProductionOrder.order_number.desc()).first()

    if last_order:
        # Extract sequence number and increment
        seq = int(last_order.order_number.split("-")[-1]) + 1
    else:
        seq = 1

    return f"PO-{site_id}-{today}-{seq:04d}"


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("/", response_model=ProductionOrderListResponse)
async def list_production_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    item_id: Optional[int] = Query(None, description="Filter by item ID"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    config_id: Optional[int] = Query(None, description="Filter by supply chain config ID"),
    mps_plan_id: Optional[int] = Query(None, description="Filter by MPS plan ID"),
    overdue_only: bool = Query(False, description="Show only overdue orders"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List production orders with filtering and pagination.

    Requires: VIEW_PRODUCTION_ORDERS capability
    """
    # Build query
    query = db.query(ProductionOrder).filter(ProductionOrder.is_deleted == False)

    # Apply filters
    if status:
        query = query.filter(ProductionOrder.status == status)
    if item_id:
        query = query.filter(ProductionOrder.item_id == item_id)
    if site_id:
        query = query.filter(ProductionOrder.site_id == site_id)
    if config_id:
        query = query.filter(ProductionOrder.config_id == config_id)
    if mps_plan_id:
        query = query.filter(ProductionOrder.mps_plan_id == mps_plan_id)
    if overdue_only:
        query = query.filter(
            and_(
                ProductionOrder.status.in_(["RELEASED", "IN_PROGRESS"]),
                ProductionOrder.planned_completion_date < datetime.utcnow()
            )
        )

    # Count total
    total = query.count()

    # Apply pagination and eager load relationships
    orders = query.options(
        joinedload(ProductionOrder.item),
        joinedload(ProductionOrder.site),
        joinedload(ProductionOrder.mps_plan)
    ).order_by(
        ProductionOrder.planned_start_date.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    return ProductionOrderListResponse(
        items=orders,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/summary", response_model=ProductionOrderSummary)
async def get_production_order_summary(
    config_id: Optional[int] = Query(None, description="Filter by supply chain config ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary statistics for production orders.

    Requires: VIEW_PRODUCTION_ORDERS capability
    """
    # Base query
    base_query = db.query(ProductionOrder).filter(ProductionOrder.is_deleted == False)
    if config_id:
        base_query = base_query.filter(ProductionOrder.config_id == config_id)

    # Count by status
    status_counts = {}
    for status in ["PLANNED", "RELEASED", "IN_PROGRESS", "COMPLETED", "CLOSED", "CANCELLED"]:
        count = base_query.filter(ProductionOrder.status == status).count()
        status_counts[status.lower()] = count

    # Overdue count
    overdue_count = base_query.filter(
        and_(
            ProductionOrder.status.in_(["RELEASED", "IN_PROGRESS"]),
            ProductionOrder.planned_completion_date < datetime.utcnow()
        )
    ).count()

    # Total quantities
    planned_qty = db.query(func.sum(ProductionOrder.planned_quantity)).filter(
        ProductionOrder.id.in_(base_query.with_entities(ProductionOrder.id))
    ).scalar() or 0

    actual_qty = db.query(func.sum(ProductionOrder.actual_quantity)).filter(
        and_(
            ProductionOrder.id.in_(base_query.with_entities(ProductionOrder.id)),
            ProductionOrder.actual_quantity.isnot(None)
        )
    ).scalar() or 0

    # Average yield
    avg_yield = db.query(func.avg(ProductionOrder.yield_percentage)).filter(
        and_(
            ProductionOrder.id.in_(base_query.with_entities(ProductionOrder.id)),
            ProductionOrder.yield_percentage.isnot(None)
        )
    ).scalar() or 0.0

    return ProductionOrderSummary(
        total_orders=base_query.count(),
        planned_count=status_counts["planned"],
        released_count=status_counts["released"],
        in_progress_count=status_counts["in_progress"],
        completed_count=status_counts["completed"],
        closed_count=status_counts["closed"],
        cancelled_count=status_counts["cancelled"],
        overdue_count=overdue_count,
        total_planned_quantity=int(planned_qty),
        total_actual_quantity=int(actual_qty),
        average_yield_percentage=float(avg_yield)
    )


@router.get("/{order_id}", response_model=ProductionOrderResponse)
async def get_production_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get production order by ID.

    Requires: VIEW_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)
    return order


@router.post("/", response_model=ProductionOrderResponse, status_code=201)
async def create_production_order(
    order_data: ProductionOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new production order.

    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    # Validate MPS plan exists if provided
    if order_data.mps_plan_id:
        mps_plan = db.query(MPSPlan).filter(MPSPlan.id == order_data.mps_plan_id).first()
        if not mps_plan:
            raise HTTPException(status_code=404, detail="MPS plan not found")

    # Validate item exists
    item = db.query(Product).filter(Item.id == order_data.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Validate site exists
    site = db.query(Node).filter(Node.id == order_data.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Generate order number
    order_number = _generate_order_number(db, order_data.site_id)

    # Create production order
    order = ProductionOrder(
        order_number=order_number,
        mps_plan_id=order_data.mps_plan_id,
        item_id=order_data.item_id,
        site_id=order_data.site_id,
        config_id=order_data.config_id,
        planned_quantity=order_data.planned_quantity,
        planned_start_date=order_data.planned_start_date,
        planned_completion_date=order_data.planned_completion_date,
        priority=order_data.priority,
        notes=order_data.notes,
        status="PLANNED",
        created_by=current_user.id,
        updated_by=current_user.id
    )

    db.add(order)
    db.flush()  # Get order.id for components

    # Create components if provided
    if order_data.components:
        for comp_data in order_data.components:
            component = ProductionOrderComponent(
                production_order_id=order.id,
                item_id=comp_data.item_id,
                planned_quantity=comp_data.planned_quantity,
                unit_of_measure=comp_data.unit_of_measure
            )
            db.add(component)

    db.commit()
    db.refresh(order)

    return order


@router.put("/{order_id}", response_model=ProductionOrderResponse)
async def update_production_order(
    order_id: int,
    order_data: ProductionOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a production order (only in PLANNED or RELEASED status).

    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user, require_editable=True)

    # Update fields
    update_data = order_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(order, field):
            setattr(order, field, value)

    order.updated_by = current_user.id
    order.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    return order


@router.delete("/{order_id}", status_code=204)
async def delete_production_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete a production order (only in PLANNED status).

    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    if order.status != "PLANNED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete production order in status: {order.status}. Use cancel instead."
        )

    order.is_deleted = True
    order.updated_by = current_user.id
    order.updated_at = datetime.utcnow()

    db.commit()

    return None


# ============================================================================
# Lifecycle Action Endpoints
# ============================================================================

@router.post("/{order_id}/release", response_model=ProductionOrderResponse)
async def release_production_order(
    order_id: int,
    release_data: ProductionOrderRelease,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Release production order to shop floor.

    Transitions: PLANNED → RELEASED
    Requires: RELEASE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    try:
        order.transition_to_released(user_id=current_user.id)

        if release_data.notes:
            order.notes = (order.notes or "") + f"\n[RELEASE] {release_data.notes}"

        order.updated_by = current_user.id
        order.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)

        return order

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/start", response_model=ProductionOrderResponse)
async def start_production_order(
    order_id: int,
    start_data: ProductionOrderStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start production on a released order.

    Transitions: RELEASED → IN_PROGRESS
    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    try:
        order.transition_to_in_progress(
            actual_start_date=start_data.actual_start_date,
            user_id=current_user.id
        )

        if start_data.notes:
            order.notes = (order.notes or "") + f"\n[START] {start_data.notes}"

        order.updated_by = current_user.id
        order.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)

        return order

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/complete", response_model=ProductionOrderResponse)
async def complete_production_order(
    order_id: int,
    complete_data: ProductionOrderComplete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Complete production with actual quantities.

    Transitions: IN_PROGRESS → COMPLETED
    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    try:
        order.transition_to_completed(
            actual_quantity=complete_data.actual_quantity,
            scrap_quantity=complete_data.scrap_quantity,
            actual_completion_date=complete_data.actual_completion_date,
            user_id=current_user.id
        )

        # Update component actual quantities if provided
        if complete_data.components:
            for comp_update in complete_data.components:
                component = db.query(ProductionOrderComponent).filter(
                    ProductionOrderComponent.id == comp_update.component_id,
                    ProductionOrderComponent.production_order_id == order.id
                ).first()

                if component:
                    component.actual_quantity = comp_update.actual_quantity

        if complete_data.notes:
            order.notes = (order.notes or "") + f"\n[COMPLETE] {complete_data.notes}"

        order.updated_by = current_user.id
        order.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)

        return order

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/close", response_model=ProductionOrderResponse)
async def close_production_order(
    order_id: int,
    close_data: ProductionOrderClose,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Close a completed production order.

    Transitions: COMPLETED → CLOSED
    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    try:
        order.transition_to_closed(user_id=current_user.id)

        if close_data.notes:
            order.notes = (order.notes or "") + f"\n[CLOSE] {close_data.notes}"

        order.updated_by = current_user.id
        order.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)

        return order

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/cancel", response_model=ProductionOrderResponse)
async def cancel_production_order(
    order_id: int,
    cancel_data: ProductionOrderCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel a production order.

    Transitions: ANY → CANCELLED (except COMPLETED, CLOSED)
    Requires: MANAGE_PRODUCTION_ORDERS capability
    """
    order = _get_production_order_or_404(db, order_id, current_user)

    try:
        order.transition_to_cancelled(
            reason=cancel_data.reason,
            user_id=current_user.id
        )

        if cancel_data.notes:
            order.notes = (order.notes or "") + f"\n[CANCEL] {cancel_data.notes}"

        order.updated_by = current_user.id
        order.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)

        return order

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

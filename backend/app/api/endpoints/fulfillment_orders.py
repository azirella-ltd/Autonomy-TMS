"""
Fulfillment Order API Endpoints
AWS Supply Chain Entity: fulfillment_order

Manages the PICK → PACK → SHIP → DELIVER lifecycle for outbound orders.

Key Features:
- Create and track fulfillment orders through warehouse operations
- Status lifecycle management (CREATED → ALLOCATED → PICKED → PACKED → SHIPPED → DELIVERED → CLOSED)
- Priority-based fulfillment
- Carrier and tracking information
- Wave management for warehouse operations
- On-time delivery monitoring

Endpoints:
- POST / - Create fulfillment order
- POST /bulk - Bulk create
- GET / - List with filtering
- GET /{id} - Get specific order
- GET /overdue - Find orders past promised date
- GET /summary - Fulfillment summary statistics
- POST /{id}/allocate - Allocate inventory
- POST /{id}/pick - Mark as picked
- POST /{id}/pack - Mark as packed
- POST /{id}/ship - Mark as shipped
- POST /{id}/deliver - Mark as delivered
- PUT /{id} - Update order
- DELETE /{id} - Cancel order
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date

from app.api import deps
from app.models.user import User
from app.models.sc_entities import FulfillmentOrder
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class FulfillmentOrderCreate(BaseModel):
    """Request schema for creating a fulfillment order."""
    fulfillment_order_id: str
    order_id: str
    order_line_id: Optional[str] = None
    site_id: int
    product_id: str
    quantity: float = Field(gt=0)
    uom: str = Field(default="EA")
    promised_date: Optional[datetime] = None
    priority: int = Field(default=3, ge=1, le=5, description="1=highest, 5=lowest")
    customer_id: Optional[str] = None
    wave_id: Optional[str] = None
    source: Optional[str] = None


class FulfillmentOrderUpdate(BaseModel):
    """Request schema for updating a fulfillment order."""
    priority: Optional[int] = Field(None, ge=1, le=5)
    promised_date: Optional[datetime] = None
    wave_id: Optional[str] = None
    carrier: Optional[str] = None
    ship_method: Optional[str] = None
    source: Optional[str] = None


class FulfillmentAllocate(BaseModel):
    """Request schema for allocating inventory to fulfillment order."""
    allocated_quantity: float = Field(gt=0)
    pick_location: Optional[str] = None


class FulfillmentShip(BaseModel):
    """Request schema for shipping a fulfillment order."""
    shipped_quantity: float = Field(gt=0)
    carrier: str
    tracking_number: Optional[str] = None
    ship_method: str = Field(default="GROUND", description="GROUND, EXPRESS, AIR, OCEAN")


class FulfillmentDeliver(BaseModel):
    """Request schema for delivery confirmation."""
    delivered_quantity: float = Field(gt=0)


class FulfillmentOrderResponse(BaseModel):
    """Response schema for fulfillment order."""
    id: int
    company_id: Optional[str]
    fulfillment_order_id: str
    order_id: str
    order_line_id: Optional[str]
    site_id: int
    product_id: str
    quantity: float
    uom: Optional[str]
    status: str
    created_date: Optional[datetime]
    promised_date: Optional[datetime]
    allocated_date: Optional[datetime]
    pick_date: Optional[datetime]
    pack_date: Optional[datetime]
    ship_date: Optional[datetime]
    delivery_date: Optional[datetime]
    allocated_quantity: Optional[float]
    picked_quantity: Optional[float]
    shipped_quantity: Optional[float]
    delivered_quantity: Optional[float]
    short_quantity: Optional[float]
    wave_id: Optional[str]
    pick_location: Optional[str]
    pack_station: Optional[str]
    carrier: Optional[str]
    tracking_number: Optional[str]
    ship_method: Optional[str]
    priority: Optional[int]
    customer_id: Optional[str]
    source: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class FulfillmentSummary(BaseModel):
    """Fulfillment summary statistics."""
    total_orders: int
    by_status: dict
    overdue_count: int
    on_time_rate: Optional[float]
    avg_cycle_time_hours: Optional[float]


# ============================================================================
# Lifecycle transition rules
# ============================================================================

VALID_TRANSITIONS = {
    "CREATED": ["ALLOCATED", "CLOSED"],
    "ALLOCATED": ["PICKED", "CREATED", "CLOSED"],
    "PICKED": ["PACKED", "ALLOCATED", "CLOSED"],
    "PACKED": ["SHIPPED", "PICKED", "CLOSED"],
    "SHIPPED": ["DELIVERED", "CLOSED"],
    "DELIVERED": ["CLOSED"],
    "CLOSED": [],
}


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=FulfillmentOrderResponse, status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_fulfillment_orders"])
async def create_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order: FulfillmentOrderCreate,
):
    """Create a new fulfillment order."""
    company_id = current_user.tenant_id

    # Check for duplicate fulfillment_order_id
    existing = await db.execute(
        select(FulfillmentOrder).where(
            FulfillmentOrder.fulfillment_order_id == order.fulfillment_order_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Fulfillment order '{order.fulfillment_order_id}' already exists",
        )

    fo = FulfillmentOrder(
        company_id=company_id,
        fulfillment_order_id=order.fulfillment_order_id,
        order_id=order.order_id,
        order_line_id=order.order_line_id,
        site_id=order.site_id,
        product_id=order.product_id,
        quantity=order.quantity,
        uom=order.uom,
        promised_date=order.promised_date,
        priority=order.priority,
        customer_id=order.customer_id,
        wave_id=order.wave_id,
        source=order.source,
    )

    db.add(fo)
    await db.commit()
    await db.refresh(fo)
    return fo


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_fulfillment_orders"])
async def bulk_create_fulfillment_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    orders: List[FulfillmentOrderCreate],
):
    """Bulk create fulfillment orders."""
    company_id = current_user.tenant_id
    created = []

    for order in orders:
        fo = FulfillmentOrder(
            company_id=company_id,
            fulfillment_order_id=order.fulfillment_order_id,
            order_id=order.order_id,
            order_line_id=order.order_line_id,
            site_id=order.site_id,
            product_id=order.product_id,
            quantity=order.quantity,
            uom=order.uom,
            promised_date=order.promised_date,
            priority=order.priority,
            customer_id=order.customer_id,
            wave_id=order.wave_id,
            source=order.source,
        )
        db.add(fo)
        created.append(fo)

    await db.commit()
    return {"created": len(created)}


@router.get("/", response_model=List[FulfillmentOrderResponse])
@require_capabilities(["view_fulfillment_orders"])
async def list_fulfillment_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: Optional[int] = Query(None),
    product_id: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[int] = Query(None, ge=1, le=5),
    customer_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
):
    """List fulfillment orders with optional filtering."""
    query = select(FulfillmentOrder).where(
        FulfillmentOrder.company_id == current_user.tenant_id
    )

    if site_id is not None:
        query = query.where(FulfillmentOrder.site_id == site_id)
    if product_id:
        query = query.where(FulfillmentOrder.product_id == product_id)
    if order_id:
        query = query.where(FulfillmentOrder.order_id == order_id)
    if status_filter:
        query = query.where(FulfillmentOrder.status == status_filter.upper())
    if priority is not None:
        query = query.where(FulfillmentOrder.priority == priority)
    if customer_id:
        query = query.where(FulfillmentOrder.customer_id == customer_id)
    if from_date:
        query = query.where(FulfillmentOrder.created_date >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.where(FulfillmentOrder.created_date <= datetime.combine(to_date, datetime.max.time()))

    query = query.order_by(FulfillmentOrder.priority.asc(), FulfillmentOrder.created_date.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/overdue", response_model=List[FulfillmentOrderResponse])
@require_capabilities(["view_fulfillment_orders"])
async def list_overdue_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """List fulfillment orders past their promised date that haven't been delivered."""
    now = datetime.utcnow()
    query = select(FulfillmentOrder).where(
        and_(
            FulfillmentOrder.company_id == current_user.tenant_id,
            FulfillmentOrder.promised_date < now,
            FulfillmentOrder.status.notin_(["DELIVERED", "CLOSED"]),
        )
    ).order_by(FulfillmentOrder.priority.asc(), FulfillmentOrder.promised_date.asc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary", response_model=FulfillmentSummary)
@require_capabilities(["view_fulfillment_orders"])
async def fulfillment_summary(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: Optional[int] = Query(None),
):
    """Get fulfillment summary statistics."""
    base_filter = [FulfillmentOrder.company_id == current_user.tenant_id]
    if site_id is not None:
        base_filter.append(FulfillmentOrder.site_id == site_id)

    # Total and by-status counts
    count_q = select(
        FulfillmentOrder.status, func.count(FulfillmentOrder.id)
    ).where(and_(*base_filter)).group_by(FulfillmentOrder.status)
    count_result = await db.execute(count_q)
    by_status = {row[0]: row[1] for row in count_result.all()}
    total = sum(by_status.values())

    # Overdue count
    now = datetime.utcnow()
    overdue_q = select(func.count(FulfillmentOrder.id)).where(
        and_(
            *base_filter,
            FulfillmentOrder.promised_date < now,
            FulfillmentOrder.status.notin_(["DELIVERED", "CLOSED"]),
        )
    )
    overdue_result = await db.execute(overdue_q)
    overdue_count = overdue_result.scalar() or 0

    # On-time delivery rate (delivered orders only)
    delivered_q = select(
        func.count(FulfillmentOrder.id),
        func.count(FulfillmentOrder.id).filter(
            FulfillmentOrder.delivery_date <= FulfillmentOrder.promised_date
        ),
    ).where(
        and_(
            *base_filter,
            FulfillmentOrder.status == "DELIVERED",
            FulfillmentOrder.delivery_date.isnot(None),
            FulfillmentOrder.promised_date.isnot(None),
        )
    )
    delivered_result = await db.execute(delivered_q)
    delivered_row = delivered_result.one_or_none()
    on_time_rate = None
    if delivered_row and delivered_row[0] > 0:
        on_time_rate = round(delivered_row[1] / delivered_row[0] * 100, 1)

    return FulfillmentSummary(
        total_orders=total,
        by_status=by_status,
        overdue_count=overdue_count,
        on_time_rate=on_time_rate,
        avg_cycle_time_hours=None,  # Requires more complex query
    )


@router.get("/{fulfillment_id}", response_model=FulfillmentOrderResponse)
@require_capabilities(["view_fulfillment_orders"])
async def get_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
):
    """Get a specific fulfillment order by ID."""
    result = await db.execute(
        select(FulfillmentOrder).where(
            and_(
                FulfillmentOrder.id == fulfillment_id,
                FulfillmentOrder.company_id == current_user.tenant_id,
            )
        )
    )
    fo = result.scalar_one_or_none()
    if not fo:
        raise HTTPException(status_code=404, detail="Fulfillment order not found")
    return fo


@router.post("/{fulfillment_id}/allocate", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def allocate_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
    body: FulfillmentAllocate,
):
    """Allocate inventory to a fulfillment order."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    _validate_transition(fo.status, "ALLOCATED")

    fo.status = "ALLOCATED"
    fo.allocated_quantity = body.allocated_quantity
    fo.allocated_date = datetime.utcnow()
    fo.pick_location = body.pick_location
    fo.short_quantity = max(0, fo.quantity - body.allocated_quantity)
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)
    return fo


@router.post("/{fulfillment_id}/pick", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def pick_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
):
    """Mark fulfillment order as picked."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    _validate_transition(fo.status, "PICKED")

    fo.status = "PICKED"
    fo.picked_quantity = fo.allocated_quantity or fo.quantity
    fo.pick_date = datetime.utcnow()
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)
    return fo


@router.post("/{fulfillment_id}/pack", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def pack_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
    pack_station: Optional[str] = Query(None),
):
    """Mark fulfillment order as packed."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    _validate_transition(fo.status, "PACKED")

    fo.status = "PACKED"
    fo.pack_date = datetime.utcnow()
    if pack_station:
        fo.pack_station = pack_station
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)
    return fo


@router.post("/{fulfillment_id}/ship", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def ship_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
    body: FulfillmentShip,
):
    """Mark fulfillment order as shipped with carrier details."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    _validate_transition(fo.status, "SHIPPED")

    fo.status = "SHIPPED"
    fo.shipped_quantity = body.shipped_quantity
    fo.ship_date = datetime.utcnow()
    fo.carrier = body.carrier
    fo.tracking_number = body.tracking_number
    fo.ship_method = body.ship_method
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)
    return fo


@router.post("/{fulfillment_id}/deliver", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def deliver_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
    body: FulfillmentDeliver,
):
    """Confirm delivery of a fulfillment order."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    _validate_transition(fo.status, "DELIVERED")

    fo.status = "DELIVERED"
    fo.delivered_quantity = body.delivered_quantity
    fo.delivery_date = datetime.utcnow()
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)

    # ─── Conformal observation: service level (fill rate) ─────
    try:
        from app.services.conformal_orchestrator import ConformalOrchestrator
        orchestrator = ConformalOrchestrator.get_instance()
        if fo.quantity and fo.quantity > 0:
            actual_fill = float(fo.delivered_quantity or 0) / float(fo.quantity)
            await orchestrator.on_service_level_observed(
                db=db, product_id=fo.product_id or "", site_id=fo.site_id or 0,
                expected_fill_rate=1.0, actual_fill_rate=min(1.0, actual_fill),
                tenant_id=current_user.tenant_id,
            )
    except Exception:
        pass  # Non-critical

    return fo


@router.put("/{fulfillment_id}", response_model=FulfillmentOrderResponse)
@require_capabilities(["manage_fulfillment_orders"])
async def update_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
    body: FulfillmentOrderUpdate,
):
    """Update fulfillment order fields."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(fo, field, value)
    fo.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fo)
    return fo


@router.delete("/{fulfillment_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_capabilities(["manage_fulfillment_orders"])
async def cancel_fulfillment_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    fulfillment_id: int,
):
    """Cancel (close) a fulfillment order."""
    fo = await _get_order(db, fulfillment_id, current_user.tenant_id)
    if fo.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Order is already closed")

    fo.status = "CLOSED"
    fo.updated_at = datetime.utcnow()
    await db.commit()


# ============================================================================
# Helpers
# ============================================================================

async def _get_order(db: AsyncSession, order_id: int, company_id: str) -> FulfillmentOrder:
    result = await db.execute(
        select(FulfillmentOrder).where(
            and_(
                FulfillmentOrder.id == order_id,
                FulfillmentOrder.company_id == company_id,
            )
        )
    )
    fo = result.scalar_one_or_none()
    if not fo:
        raise HTTPException(status_code=404, detail="Fulfillment order not found")
    return fo


def _validate_transition(current_status: str, target_status: str) -> None:
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status} to {target_status}. "
                   f"Allowed transitions: {allowed}",
        )

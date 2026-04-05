"""
Turnaround Orders API Endpoints
Sprint 6: Additional Order Types

Provides endpoints for turnaround order management (returns, repairs, refurbishment).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date

from app.api import deps
from app.core.clock import tenant_today
from app.models.user import User
from app.models.turnaround_order import TurnaroundOrder, TurnaroundOrderLineItem
from app.core.capabilities import require_capabilities

router = APIRouter()

# Schemas
class TurnaroundOrderCreateSchema(BaseModel):
    return_order_id: Optional[str] = None
    rma_number: Optional[str] = None
    customer_id: Optional[str] = None
    from_site_id: str
    to_site_id: str
    return_reason_code: str
    return_reason_description: Optional[str] = None
    turnaround_type: str
    priority: str = "NORMAL"

class TurnaroundOrderUpdateSchema(BaseModel):
    status: Optional[str] = None
    inspection_status: Optional[str] = None
    disposition: Optional[str] = None
    inspection_notes: Optional[str] = None
    product_condition: Optional[str] = None
    quality_grade: Optional[str] = None
    refurbishment_required: Optional[str] = None

# Endpoints
@router.get("/")
@require_capabilities(["view_turnaround_orders"])
async def get_turnaround_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    customer_id: Optional[str] = Query(None),
    turnaround_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    return_reason_code: Optional[str] = Query(None),
    limit: int = Query(100, le=500)
):
    stmt = select(TurnaroundOrder)
    if customer_id:
        stmt = stmt.where(TurnaroundOrder.customer_id == customer_id)
    if turnaround_type:
        stmt = stmt.where(TurnaroundOrder.turnaround_type == turnaround_type)
    if status:
        stmt = stmt.where(TurnaroundOrder.status == status)
    if return_reason_code:
        stmt = stmt.where(TurnaroundOrder.return_reason_code == return_reason_code)

    stmt = stmt.order_by(desc(TurnaroundOrder.order_date)).limit(limit)
    result = await db.execute(stmt)
    return [order.to_dict() for order in result.scalars().all()]

@router.post("/", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_turnaround_orders"])
async def create_turnaround_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_data: TurnaroundOrderCreateSchema
):
    import uuid
    order_number = f"TURN-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Auto-generate RMA if not provided
    rma_number = order_data.rma_number or f"RMA-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

    order = TurnaroundOrder(
        turnaround_order_number=order_number,
        rma_number=rma_number,
        order_date=await tenant_today(current_user.tenant_id, db),
        status="INITIATED",
        created_by_id=current_user.id,
        **order_data.dict()
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order.to_dict()

@router.get("/{order_id}")
@require_capabilities(["view_turnaround_orders"])
async def get_turnaround_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    stmt = select(TurnaroundOrder).where(TurnaroundOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.to_dict()

@router.put("/{order_id}")
@require_capabilities(["manage_turnaround_orders"])
async def update_turnaround_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    order_update: TurnaroundOrderUpdateSchema
):
    stmt = select(TurnaroundOrder).where(TurnaroundOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for field, value in order_update.dict(exclude_unset=True).items():
        setattr(order, field, value)

    # Auto-set timestamps
    if order_update.status == "RECEIVED":
        order.received_at = datetime.now()
        order.received_by_id = current_user.id
    elif order_update.status == "INSPECTED":
        order.inspected_at = datetime.now()
        order.inspected_by_id = current_user.id
    elif order_update.status == "COMPLETED":
        order.disposed_at = datetime.now()
        order.disposed_by_id = current_user.id

    await db.commit()
    await db.refresh(order)
    return order.to_dict()

@router.post("/{order_id}/approve")
@require_capabilities(["approve_turnaround_orders"])
async def approve_turnaround_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    stmt = select(TurnaroundOrder).where(TurnaroundOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "APPROVED"
    order.approved_at = datetime.now()
    order.approved_by_id = current_user.id
    await db.commit()
    await db.refresh(order)
    return order.to_dict()

@router.post("/{order_id}/inspect")
@require_capabilities(["manage_turnaround_orders"])
async def inspect_turnaround_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    inspection_status: str = Query(...),
    disposition: str = Query(...),
    inspection_notes: Optional[str] = Query(None)
):
    """Complete inspection and set disposition"""
    stmt = select(TurnaroundOrder).where(TurnaroundOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "INSPECTED"
    order.inspection_status = inspection_status
    order.disposition = disposition
    order.inspection_notes = inspection_notes
    order.inspected_at = datetime.now()
    order.inspected_by_id = current_user.id

    await db.commit()
    await db.refresh(order)
    return order.to_dict()

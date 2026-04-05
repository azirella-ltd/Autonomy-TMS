"""
Maintenance Orders API Endpoints
Sprint 6: Additional Order Types

Provides endpoints for maintenance order management with spare parts planning.
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
from app.models.maintenance_order import MaintenanceOrder, MaintenanceOrderSpare
from app.core.capabilities import require_capabilities

router = APIRouter()

# Schemas
class MaintenanceOrderCreateSchema(BaseModel):
    asset_id: str
    asset_name: Optional[str] = None
    site_id: str
    maintenance_type: str
    work_description: str
    priority: str = "NORMAL"
    scheduled_start_date: Optional[datetime] = None
    downtime_required: str = "Y"
    estimated_downtime_hours: Optional[float] = None

class MaintenanceOrderUpdateSchema(BaseModel):
    status: Optional[str] = None
    actual_completion_date: Optional[datetime] = None
    completion_notes: Optional[str] = None
    actual_downtime_hours: Optional[float] = None

# Endpoints
@router.get("/")
@require_capabilities(["view_maintenance_orders"])
async def get_maintenance_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    asset_id: Optional[str] = Query(None),
    maintenance_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500)
):
    stmt = select(MaintenanceOrder)
    if asset_id:
        stmt = stmt.where(MaintenanceOrder.asset_id == asset_id)
    if maintenance_type:
        stmt = stmt.where(MaintenanceOrder.maintenance_type == maintenance_type)
    if status:
        stmt = stmt.where(MaintenanceOrder.status == status)

    stmt = stmt.order_by(desc(MaintenanceOrder.scheduled_start_date)).limit(limit)
    result = await db.execute(stmt)
    return [order.to_dict() for order in result.scalars().all()]

@router.post("/", status_code=status.HTTP_201_CREATED)
@require_capabilities(["manage_maintenance_orders"])
async def create_maintenance_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_data: MaintenanceOrderCreateSchema
):
    import uuid
    order_number = f"MAINT-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    order = MaintenanceOrder(
        maintenance_order_number=order_number,
        order_date=await tenant_today(current_user.tenant_id, db),
        created_by_id=current_user.id,
        status="PLANNED",
        **order_data.dict()
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order.to_dict()

@router.get("/{order_id}")
@require_capabilities(["view_maintenance_orders"])
async def get_maintenance_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    stmt = select(MaintenanceOrder).where(MaintenanceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.to_dict()

@router.put("/{order_id}")
@require_capabilities(["manage_maintenance_orders"])
async def update_maintenance_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int,
    order_update: MaintenanceOrderUpdateSchema
):
    stmt = select(MaintenanceOrder).where(MaintenanceOrder.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for field, value in order_update.dict(exclude_unset=True).items():
        setattr(order, field, value)

    if order_update.status == "COMPLETED":
        order.completed_at = datetime.now()
        order.completed_by_id = current_user.id

    await db.commit()
    await db.refresh(order)

    # ─── Conformal observation: maintenance downtime ─────
    if order_update.status == "COMPLETED" and order.estimated_downtime_hours and order.actual_downtime_hours:
        try:
            from app.services.conformal_orchestrator import ConformalOrchestrator
            orchestrator = ConformalOrchestrator.get_instance()
            await orchestrator.on_maintenance_downtime_observed(
                db=db, asset_type=order.asset_type or "unknown", asset_id=order.asset_id or "",
                estimated_hours=float(order.estimated_downtime_hours),
                actual_hours=float(order.actual_downtime_hours),
                tenant_id=current_user.tenant_id,
            )
        except Exception:
            pass  # Non-critical

    return order.to_dict()

@router.post("/{order_id}/approve")
@require_capabilities(["approve_maintenance_orders"])
async def approve_maintenance_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    stmt = select(MaintenanceOrder).where(MaintenanceOrder.id == order_id)
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

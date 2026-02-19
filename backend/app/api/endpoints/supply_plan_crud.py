"""
Supply Plan CRUD API Endpoints (AWS Supply Chain Entity)

Full CRUD operations for AWS SC supply_plan entity:
- Create supply plan orders (PO/TO/MO requests)
- Read/List supply plans with filtering
- Update supply plan details
- Delete supply plans
- Approve/Execute supply plans
- Bulk operations

This is separate from the Monte Carlo supply planning endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, delete
from typing import List, Optional
from datetime import date, datetime
import logging

from app.db.session import get_db
from app.models.sc_entities import SupplyPlan, Product
from app.models.supply_chain_config import Site
from app.core.capabilities import require_capabilities
from app.api import deps
from app.models.user import User
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/supply-plan-entity", tags=["Supply Plan (AWS SC Entity)"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SupplyPlanCreate(BaseModel):
    """Create supply plan request"""
    product_id: str
    site_id: str
    plan_date: date
    plan_type: str = Field(..., pattern="^(po_request|mo_request|to_request)$")

    forecast_quantity: Optional[float] = None
    demand_quantity: Optional[float] = None
    supply_quantity: Optional[float] = None
    opening_inventory: Optional[float] = None
    closing_inventory: Optional[float] = None
    safety_stock: Optional[float] = None
    reorder_point: Optional[float] = None

    planned_order_quantity: float
    planned_order_date: date
    planned_receipt_date: date

    supplier_id: Optional[str] = None  # For PO
    from_site_id: Optional[str] = None  # For TO
    planner_name: Optional[str] = None
    order_cost: Optional[float] = None
    planning_group: Optional[str] = None


class SupplyPlanUpdate(BaseModel):
    """Update supply plan request"""
    planned_order_quantity: Optional[float] = None
    planned_order_date: Optional[date] = None
    planned_receipt_date: Optional[date] = None
    supplier_id: Optional[str] = None
    from_site_id: Optional[str] = None
    order_cost: Optional[float] = None
    plan_type: Optional[str] = None


class SupplyPlanResponse(BaseModel):
    """Supply plan response"""
    id: int
    company_id: str
    product_id: str
    site_id: str
    plan_date: date
    plan_type: str
    planning_group: Optional[str]

    forecast_quantity: Optional[float]
    demand_quantity: Optional[float]
    supply_quantity: Optional[float]
    opening_inventory: Optional[float]
    closing_inventory: Optional[float]
    safety_stock: Optional[float]
    reorder_point: Optional[float]

    planned_order_quantity: float
    planned_order_date: date
    planned_receipt_date: date

    supplier_id: Optional[str]
    from_site_id: Optional[str]
    planner_name: Optional[str]
    order_cost: Optional[float]

    plan_version: Optional[str]
    created_dttm: datetime

    class Config:
        from_attributes = True


class BulkSupplyPlanCreate(BaseModel):
    """Bulk create supply plans"""
    plans: List[SupplyPlanCreate]
    plan_version: str = "v1"


class SupplyPlanSummary(BaseModel):
    """Summary statistics for supply plans"""
    total_plans: int
    po_requests: int
    to_requests: int
    mo_requests: int
    total_order_quantity: float
    total_order_cost: float
    products_count: int
    sites_count: int
    date_range_start: Optional[date]
    date_range_end: Optional[date]


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post("/", response_model=SupplyPlanResponse)
@require_capabilities(["manage_supply_planning"])
async def create_supply_plan(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    plan: SupplyPlanCreate,
    company_id: str = Query(..., description="Company ID"),
    plan_version: str = Query("v1", description="Plan version")
):
    """
    Create a new supply plan entry

    Creates a single supply plan order (PO/TO/MO request).
    """
    try:
        # Validate product and site exist
        product = await db.get(Product, plan.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {plan.product_id} not found")

        site = await db.get(Site, plan.site_id)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site {plan.site_id} not found")

        # Create supply plan
        supply_plan = SupplyPlan(
            company_id=company_id,
            product_id=plan.product_id,
            site_id=plan.site_id,
            plan_date=plan.plan_date,
            plan_type=plan.plan_type,
            planning_group=plan.planning_group,
            forecast_quantity=plan.forecast_quantity,
            demand_quantity=plan.demand_quantity,
            supply_quantity=plan.supply_quantity,
            opening_inventory=plan.opening_inventory,
            closing_inventory=plan.closing_inventory,
            safety_stock=plan.safety_stock,
            reorder_point=plan.reorder_point,
            planned_order_quantity=plan.planned_order_quantity,
            planned_order_date=plan.planned_order_date,
            planned_receipt_date=plan.planned_receipt_date,
            supplier_id=plan.supplier_id,
            from_site_id=plan.from_site_id,
            planner_name=plan.planner_name or current_user.email,
            order_cost=plan.order_cost,
            plan_version=plan_version,
            created_dttm=datetime.utcnow()
        )

        db.add(supply_plan)
        await db.commit()
        await db.refresh(supply_plan)

        logger.info(f"Created supply plan {supply_plan.id} for {plan.product_id} at {plan.site_id}")
        return supply_plan

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating supply plan: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=dict)
@require_capabilities(["manage_supply_planning"])
async def create_supply_plans_bulk(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    bulk_request: BulkSupplyPlanCreate,
    company_id: str = Query(..., description="Company ID")
):
    """
    Bulk create supply plans

    Creates multiple supply plan entries in a single transaction.
    """
    try:
        created_plans = []

        for plan in bulk_request.plans:
            supply_plan = SupplyPlan(
                company_id=company_id,
                product_id=plan.product_id,
                site_id=plan.site_id,
                plan_date=plan.plan_date,
                plan_type=plan.plan_type,
                planning_group=plan.planning_group,
                forecast_quantity=plan.forecast_quantity,
                demand_quantity=plan.demand_quantity,
                supply_quantity=plan.supply_quantity,
                opening_inventory=plan.opening_inventory,
                closing_inventory=plan.closing_inventory,
                safety_stock=plan.safety_stock,
                reorder_point=plan.reorder_point,
                planned_order_quantity=plan.planned_order_quantity,
                planned_order_date=plan.planned_order_date,
                planned_receipt_date=plan.planned_receipt_date,
                supplier_id=plan.supplier_id,
                from_site_id=plan.from_site_id,
                planner_name=plan.planner_name or current_user.email,
                order_cost=plan.order_cost,
                plan_version=bulk_request.plan_version,
                created_dttm=datetime.utcnow()
            )
            db.add(supply_plan)
            created_plans.append(supply_plan)

        await db.commit()

        # Refresh to get IDs
        for plan in created_plans:
            await db.refresh(plan)

        logger.info(f"Bulk created {len(created_plans)} supply plans")

        return {
            "message": f"Successfully created {len(created_plans)} supply plans",
            "count": len(created_plans),
            "plan_ids": [p.id for p in created_plans]
        }

    except Exception as e:
        logger.error(f"Error in bulk create: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[SupplyPlanResponse])
@require_capabilities(["view_supply_planning"])
async def list_supply_plans(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    company_id: str = Query(..., description="Company ID"),
    product_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    plan_type: Optional[str] = Query(None, pattern="^(po_request|mo_request|to_request)$"),
    plan_date_from: Optional[date] = Query(None),
    plan_date_to: Optional[date] = Query(None),
    plan_version: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0)
):
    """
    List supply plans with filtering

    Returns paginated list of supply plans matching filter criteria.
    """
    try:
        # Build query
        stmt = select(SupplyPlan).where(SupplyPlan.company_id == company_id)

        if product_id:
            stmt = stmt.where(SupplyPlan.product_id == product_id)
        if site_id:
            stmt = stmt.where(SupplyPlan.site_id == site_id)
        if plan_type:
            stmt = stmt.where(SupplyPlan.plan_type == plan_type)
        if plan_date_from:
            stmt = stmt.where(SupplyPlan.plan_date >= plan_date_from)
        if plan_date_to:
            stmt = stmt.where(SupplyPlan.plan_date <= plan_date_to)
        if plan_version:
            stmt = stmt.where(SupplyPlan.plan_version == plan_version)

        # Order and paginate
        stmt = stmt.order_by(SupplyPlan.plan_date.desc(), SupplyPlan.id.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await db.execute(stmt)
        plans = result.scalars().all()

        return plans

    except Exception as e:
        logger.error(f"Error listing supply plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plan_id}", response_model=SupplyPlanResponse)
@require_capabilities(["view_supply_planning"])
async def get_supply_plan(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    plan_id: int
):
    """Get supply plan by ID"""
    try:
        plan = await db.get(SupplyPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Supply plan not found")
        return plan

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting supply plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{plan_id}", response_model=SupplyPlanResponse)
@require_capabilities(["manage_supply_planning"])
async def update_supply_plan(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    plan_id: int,
    update: SupplyPlanUpdate
):
    """
    Update supply plan

    Updates mutable fields of an existing supply plan.
    """
    try:
        plan = await db.get(SupplyPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Supply plan not found")

        # Update fields
        if update.planned_order_quantity is not None:
            plan.planned_order_quantity = update.planned_order_quantity
        if update.planned_order_date is not None:
            plan.planned_order_date = update.planned_order_date
        if update.planned_receipt_date is not None:
            plan.planned_receipt_date = update.planned_receipt_date
        if update.supplier_id is not None:
            plan.supplier_id = update.supplier_id
        if update.from_site_id is not None:
            plan.from_site_id = update.from_site_id
        if update.order_cost is not None:
            plan.order_cost = update.order_cost
        if update.plan_type is not None:
            plan.plan_type = update.plan_type

        plan.source_update_dttm = datetime.utcnow()

        await db.commit()
        await db.refresh(plan)

        logger.info(f"Updated supply plan {plan_id}")
        return plan

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating supply plan: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{plan_id}")
@require_capabilities(["manage_supply_planning"])
async def delete_supply_plan(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    plan_id: int
):
    """Delete supply plan"""
    try:
        plan = await db.get(SupplyPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Supply plan not found")

        await db.delete(plan)
        await db.commit()

        logger.info(f"Deleted supply plan {plan_id}")
        return {"message": "Supply plan deleted", "plan_id": plan_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting supply plan: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bulk")
@require_capabilities(["manage_supply_planning"])
async def delete_supply_plans_bulk(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    plan_ids: List[int] = Query(..., description="List of plan IDs to delete")
):
    """
    Bulk delete supply plans

    Deletes multiple supply plans in a single transaction.
    """
    try:
        stmt = delete(SupplyPlan).where(SupplyPlan.id.in_(plan_ids))
        result = await db.execute(stmt)
        deleted_count = result.rowcount

        await db.commit()

        logger.info(f"Bulk deleted {deleted_count} supply plans")
        return {
            "message": f"Deleted {deleted_count} supply plans",
            "deleted_count": deleted_count
        }

    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Analytics Endpoints
# ============================================================================

@router.get("/summary/statistics", response_model=SupplyPlanSummary)
@require_capabilities(["view_supply_planning"])
async def get_supply_plan_summary(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    company_id: str = Query(...),
    plan_date_from: Optional[date] = Query(None),
    plan_date_to: Optional[date] = Query(None),
    plan_version: Optional[str] = Query(None)
):
    """
    Get supply plan summary statistics

    Returns aggregated statistics for supply plans.
    """
    try:
        # Build base query
        where_clauses = [SupplyPlan.company_id == company_id]

        if plan_date_from:
            where_clauses.append(SupplyPlan.plan_date >= plan_date_from)
        if plan_date_to:
            where_clauses.append(SupplyPlan.plan_date <= plan_date_to)
        if plan_version:
            where_clauses.append(SupplyPlan.plan_version == plan_version)

        # Total count
        count_stmt = select(func.count(SupplyPlan.id)).where(and_(*where_clauses))
        result = await db.execute(count_stmt)
        total_plans = result.scalar() or 0

        # Count by type
        po_stmt = select(func.count(SupplyPlan.id)).where(
            and_(*where_clauses, SupplyPlan.plan_type == "po_request")
        )
        to_stmt = select(func.count(SupplyPlan.id)).where(
            and_(*where_clauses, SupplyPlan.plan_type == "to_request")
        )
        mo_stmt = select(func.count(SupplyPlan.id)).where(
            and_(*where_clauses, SupplyPlan.plan_type == "mo_request")
        )

        po_count = (await db.execute(po_stmt)).scalar() or 0
        to_count = (await db.execute(to_stmt)).scalar() or 0
        mo_count = (await db.execute(mo_stmt)).scalar() or 0

        # Total quantities and costs
        sum_stmt = select(
            func.sum(SupplyPlan.planned_order_quantity),
            func.sum(SupplyPlan.order_cost)
        ).where(and_(*where_clauses))
        result = await db.execute(sum_stmt)
        sums = result.one()

        total_quantity = float(sums[0]) if sums[0] else 0.0
        total_cost = float(sums[1]) if sums[1] else 0.0

        # Distinct counts
        products_stmt = select(func.count(func.distinct(SupplyPlan.product_id))).where(and_(*where_clauses))
        sites_stmt = select(func.count(func.distinct(SupplyPlan.site_id))).where(and_(*where_clauses))

        products_count = (await db.execute(products_stmt)).scalar() or 0
        sites_count = (await db.execute(sites_stmt)).scalar() or 0

        # Date range
        date_range_stmt = select(
            func.min(SupplyPlan.plan_date),
            func.max(SupplyPlan.plan_date)
        ).where(and_(*where_clauses))
        result = await db.execute(date_range_stmt)
        date_range = result.one()

        return SupplyPlanSummary(
            total_plans=total_plans,
            po_requests=po_count,
            to_requests=to_count,
            mo_requests=mo_count,
            total_order_quantity=total_quantity,
            total_order_cost=total_cost,
            products_count=products_count,
            sites_count=sites_count,
            date_range_start=date_range[0],
            date_range_end=date_range[1]
        )

    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-product/{product_id}", response_model=List[SupplyPlanResponse])
@require_capabilities(["view_supply_planning"])
async def get_supply_plans_by_product(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: str,
    company_id: str = Query(...),
    limit: int = Query(100, le=1000)
):
    """Get all supply plans for a specific product"""
    try:
        stmt = select(SupplyPlan).where(
            and_(
                SupplyPlan.company_id == company_id,
                SupplyPlan.product_id == product_id
            )
        ).order_by(SupplyPlan.plan_date.desc()).limit(limit)

        result = await db.execute(stmt)
        plans = result.scalars().all()

        return plans

    except Exception as e:
        logger.error(f"Error getting supply plans by product: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-site/{site_id}", response_model=List[SupplyPlanResponse])
@require_capabilities(["view_supply_planning"])
async def get_supply_plans_by_site(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: str,
    company_id: str = Query(...),
    limit: int = Query(100, le=1000)
):
    """Get all supply plans for a specific site"""
    try:
        stmt = select(SupplyPlan).where(
            and_(
                SupplyPlan.company_id == company_id,
                SupplyPlan.site_id == site_id
            )
        ).order_by(SupplyPlan.plan_date.desc()).limit(limit)

        result = await db.execute(stmt)
        plans = result.scalars().all()

        return plans

    except Exception as e:
        logger.error(f"Error getting supply plans by site: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
ATP/CTP View API Endpoints
AWS Supply Chain Entity: inv_projection (with ATP/CTP extensions)

Available-to-Promise (ATP) and Capable-to-Promise (CTP) calculations
for customer order promising and fulfillment planning.

ATP = On-Hand + Scheduled Receipts - Allocated - Backlog
CTP = ATP + Planned Production Capacity

Endpoints:
- POST /calculate - Calculate ATP/CTP for product-site-date
- POST /bulk-calculate - Bulk ATP/CTP calculation
- GET / - List ATP/CTP projections
- GET /{id} - Get specific projection
- GET /summary - Aggregated ATP/CTP availability
- GET /timeline - Time-phased ATP/CTP view
- DELETE /{id} - Delete projection
- DELETE /bulk - Bulk delete
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, distinct
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.api import deps
from app.models.user import User
from app.models.inventory_projection import InvProjection
from app.models.sc_entities import Product, SupplyPlan, InvLevel, Forecast
from app.models.supply_chain_config import Site
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ATPCTPCalculationRequest(BaseModel):
    """Request schema for ATP/CTP calculation"""
    product_id: str
    site_id: str
    projection_date: date
    planning_horizon_weeks: int = Field(default=12, ge=1, le=52, description="Planning horizon (1-52 weeks)")
    include_capacity: bool = Field(default=True, description="Include CTP (capacity-based promise)")


class BulkATPCTPCalculationRequest(BaseModel):
    """Bulk calculation request"""
    product_ids: List[str]
    site_ids: List[str]
    start_date: date
    planning_horizon_weeks: int = Field(default=12, ge=1, le=52)
    include_capacity: bool = True


class ATPCTPProjectionResponse(BaseModel):
    """Response schema for ATP/CTP projection"""
    id: int
    company_id: str
    product_id: str
    site_id: str
    projection_date: date
    planning_week: int

    # Current inventory
    on_hand_qty: float
    in_transit_qty: float
    allocated_qty: float
    available_qty: float

    # ATP/CTP
    atp_qty: float
    ctp_qty: float
    cumulative_atp: float
    cumulative_ctp: float

    # Probabilistic projections
    closing_inventory_p10: Optional[float]
    closing_inventory_p50: Optional[float]
    closing_inventory_p90: Optional[float]

    # Risk metrics
    stockout_probability: Optional[float]
    days_of_supply: Optional[float]

    # Metadata
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ATPCTPSummaryResponse(BaseModel):
    """Summary of ATP/CTP across products and sites"""
    total_products: int
    total_sites: int
    total_atp_qty: float
    total_ctp_qty: float
    avg_days_of_supply: float
    products_at_risk: int  # Products with stockout_probability > 0.5
    sites_at_risk: int


class TimelineEntry(BaseModel):
    """Single entry in ATP/CTP timeline"""
    week: int
    projection_date: date
    atp_qty: float
    ctp_qty: float
    cumulative_atp: float
    cumulative_ctp: float
    scheduled_receipts: float
    planned_shipments: float


class ATPCTPTimelineResponse(BaseModel):
    """Time-phased ATP/CTP view"""
    product_id: str
    site_id: str
    start_date: date
    timeline: List[TimelineEntry]


# ============================================================================
# Helper Functions
# ============================================================================

async def calculate_atp_ctp(
    db: AsyncSession,
    company_id: str,
    product_id: str,
    site_id: str,
    projection_date: date,
    planning_horizon_weeks: int,
    include_capacity: bool = True
) -> List[InvProjection]:
    """
    Calculate ATP/CTP for a product-site combination

    ATP = On-Hand + Scheduled Receipts - Allocated - Backlog
    CTP = ATP + Planned Production Capacity

    Returns list of InvProjection objects for each week in planning horizon
    """
    projections = []

    # Get current inventory level
    inv_level_stmt = select(InvLevel).where(
        and_(
            InvLevel.product_id == product_id,
            InvLevel.site_id == site_id
        )
    )
    result = await db.execute(inv_level_stmt)
    inv_level = result.scalar_one_or_none()

    # Starting inventory
    on_hand = float(inv_level.on_hand_qty) if inv_level else 0.0
    in_transit = float(inv_level.in_transit_qty) if inv_level else 0.0
    allocated = float(inv_level.allocated_qty) if inv_level else 0.0

    # Calculate for each week in planning horizon
    cumulative_atp = 0.0
    cumulative_ctp = 0.0

    for week in range(planning_horizon_weeks):
        week_date = projection_date + timedelta(weeks=week)

        # Get scheduled receipts for this week (supply plans)
        receipts_stmt = select(func.sum(SupplyPlan.planned_order_quantity)).where(
            and_(
                SupplyPlan.product_id == product_id,
                SupplyPlan.site_id == site_id,
                SupplyPlan.planned_receipt_date >= week_date,
                SupplyPlan.planned_receipt_date < week_date + timedelta(weeks=1),
                SupplyPlan.is_approved == "Y"
            )
        )
        result = await db.execute(receipts_stmt)
        scheduled_receipts = float(result.scalar() or 0.0)

        # Get demand forecast for this week
        forecast_stmt = select(Forecast.quantity_p50).where(
            and_(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= week_date,
                Forecast.forecast_date < week_date + timedelta(weeks=1),
                Forecast.is_active == "Y"
            )
        )
        result = await db.execute(forecast_stmt)
        forecast_rows = result.scalars().all()
        forecasted_demand = sum(float(f) for f in forecast_rows) if forecast_rows else 0.0

        # ATP calculation (discrete per period)
        if week == 0:
            # First period: on_hand + scheduled_receipts - allocated
            atp_qty = on_hand + scheduled_receipts - allocated
        else:
            # Future periods: scheduled_receipts only (discrete ATP)
            atp_qty = scheduled_receipts

        # Update cumulative ATP
        cumulative_atp += atp_qty

        # CTP calculation (includes planned production capacity)
        if include_capacity:
            # TODO: Get planned production capacity from production_process table
            # For now, assume CTP = ATP + 20% capacity buffer
            planned_capacity = scheduled_receipts * 0.2
            ctp_qty = atp_qty + planned_capacity
        else:
            ctp_qty = atp_qty

        cumulative_ctp += ctp_qty

        # Update on_hand for next period (simple projection)
        on_hand = max(0, on_hand + scheduled_receipts - forecasted_demand)

        # Calculate probabilistic projections (P10/P50/P90)
        # Using simple variance: P10 = P50 * 0.7, P90 = P50 * 1.3
        closing_p50 = on_hand
        closing_p10 = on_hand * 0.7
        closing_p90 = on_hand * 1.3

        # Calculate risk metrics
        # Stockout probability: if projected on_hand < safety stock
        # For simplicity, use threshold: if on_hand < 7 days of demand
        avg_daily_demand = forecasted_demand / 7.0 if forecasted_demand > 0 else 0.0
        safety_stock = avg_daily_demand * 7.0  # 7 days safety stock
        stockout_prob = max(0.0, min(1.0, (safety_stock - on_hand) / safety_stock)) if safety_stock > 0 else 0.0

        # Days of supply
        days_of_supply = (on_hand / avg_daily_demand) if avg_daily_demand > 0 else 999.0

        # Create projection
        projection = InvProjection(
            company_id=company_id,
            product_id=product_id,
            site_id=site_id,
            projection_date=week_date,
            planning_week=week + 1,
            on_hand_qty=on_hand,
            in_transit_qty=in_transit if week == 0 else 0.0,
            allocated_qty=allocated if week == 0 else 0.0,
            available_qty=on_hand - allocated if week == 0 else on_hand,
            atp_qty=atp_qty,
            ctp_qty=ctp_qty,
            cumulative_atp=cumulative_atp,
            cumulative_ctp=cumulative_ctp,
            closing_inventory_p10=closing_p10,
            closing_inventory_p50=closing_p50,
            closing_inventory_p90=closing_p90,
            stockout_probability=stockout_prob,
            days_of_supply=days_of_supply,
            created_at=datetime.utcnow()
        )

        projections.append(projection)

    return projections


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/calculate", response_model=List[ATPCTPProjectionResponse])
@require_capabilities(["view_atp_ctp"])
async def calculate_atp_ctp_endpoint(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: ATPCTPCalculationRequest
):
    """
    Calculate ATP/CTP for a product-site combination

    Generates time-phased ATP/CTP projections across planning horizon.
    Saves results to inv_projection table for future reference.

    Args:
        request: Calculation parameters (product, site, date, horizon)

    Returns:
        List of ATP/CTP projections for each week
    """
    company_id = current_user.group_id

    # Verify product and site exist
    product_stmt = select(Product).where(Product.id == request.product_id)
    result = await db.execute(product_stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {request.product_id} not found")

    site_stmt = select(Site).where(Site.id == request.site_id)
    result = await db.execute(site_stmt)
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {request.site_id} not found")

    # Calculate ATP/CTP
    projections = await calculate_atp_ctp(
        db,
        company_id,
        request.product_id,
        request.site_id,
        request.projection_date,
        request.planning_horizon_weeks,
        request.include_capacity
    )

    # Delete existing projections for this product-site-date range
    end_date = request.projection_date + timedelta(weeks=request.planning_horizon_weeks)
    delete_stmt = select(InvProjection).where(
        and_(
            InvProjection.product_id == request.product_id,
            InvProjection.site_id == request.site_id,
            InvProjection.projection_date >= request.projection_date,
            InvProjection.projection_date < end_date
        )
    )
    result = await db.execute(delete_stmt)
    existing = result.scalars().all()
    for proj in existing:
        await db.delete(proj)

    # Save new projections
    for proj in projections:
        db.add(proj)

    await db.commit()

    # Reload with IDs
    for proj in projections:
        await db.refresh(proj)

    return [
        ATPCTPProjectionResponse.from_orm(proj) for proj in projections
    ]


@router.post("/bulk-calculate", status_code=status.HTTP_202_ACCEPTED)
@require_capabilities(["view_atp_ctp"])
async def bulk_calculate_atp_ctp(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: BulkATPCTPCalculationRequest
):
    """
    Bulk ATP/CTP calculation for multiple product-site combinations

    Calculates ATP/CTP for all combinations of products and sites.
    This is an asynchronous operation for large datasets.

    Args:
        request: Bulk calculation parameters

    Returns:
        Summary of calculation task
    """
    company_id = current_user.group_id

    total_calculations = len(request.product_ids) * len(request.site_ids)
    completed = 0
    failed = 0

    for product_id in request.product_ids:
        for site_id in request.site_ids:
            try:
                projections = await calculate_atp_ctp(
                    db,
                    company_id,
                    product_id,
                    site_id,
                    request.start_date,
                    request.planning_horizon_weeks,
                    request.include_capacity
                )

                # Delete existing projections
                end_date = request.start_date + timedelta(weeks=request.planning_horizon_weeks)
                delete_stmt = select(InvProjection).where(
                    and_(
                        InvProjection.product_id == product_id,
                        InvProjection.site_id == site_id,
                        InvProjection.projection_date >= request.start_date,
                        InvProjection.projection_date < end_date
                    )
                )
                result = await db.execute(delete_stmt)
                existing = result.scalars().all()
                for proj in existing:
                    await db.delete(proj)

                # Save new projections
                for proj in projections:
                    db.add(proj)

                completed += 1

            except Exception as e:
                failed += 1
                print(f"Failed to calculate ATP/CTP for {product_id}/{site_id}: {e}")

    await db.commit()

    return {
        "status": "completed",
        "total_calculations": total_calculations,
        "completed": completed,
        "failed": failed,
        "message": f"Bulk calculation completed: {completed}/{total_calculations} successful"
    }


@router.get("/", response_model=List[ATPCTPProjectionResponse])
@require_capabilities(["view_atp_ctp"])
async def list_atp_ctp_projections(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_atp: Optional[float] = None,
    max_atp: Optional[float] = None,
    stockout_risk: Optional[bool] = None,  # Filter for high stockout probability
    limit: int = Query(1000, le=10000)
):
    """
    List ATP/CTP projections with filtering

    Args:
        product_id: Filter by product
        site_id: Filter by site
        start_date: Filter by projection date >= start_date
        end_date: Filter by projection date <= end_date
        min_atp: Filter by ATP >= min_atp
        max_atp: Filter by ATP <= max_atp
        stockout_risk: Filter for projections with stockout_probability > 0.5
        limit: Maximum results

    Returns:
        List of ATP/CTP projections
    """
    stmt = select(InvProjection)

    # Apply filters
    if product_id:
        stmt = stmt.where(InvProjection.product_id == product_id)

    if site_id:
        stmt = stmt.where(InvProjection.site_id == site_id)

    if start_date:
        stmt = stmt.where(InvProjection.projection_date >= start_date)

    if end_date:
        stmt = stmt.where(InvProjection.projection_date <= end_date)

    if min_atp is not None:
        stmt = stmt.where(InvProjection.atp_qty >= min_atp)

    if max_atp is not None:
        stmt = stmt.where(InvProjection.atp_qty <= max_atp)

    if stockout_risk is True:
        stmt = stmt.where(InvProjection.stockout_probability > 0.5)

    stmt = stmt.order_by(InvProjection.projection_date, InvProjection.product_id).limit(limit)

    result = await db.execute(stmt)
    projections = result.scalars().all()

    return [ATPCTPProjectionResponse.from_orm(proj) for proj in projections]


@router.get("/{projection_id}", response_model=ATPCTPProjectionResponse)
@require_capabilities(["view_atp_ctp"])
async def get_atp_ctp_projection(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    projection_id: int
):
    """Get ATP/CTP projection by ID"""
    stmt = select(InvProjection).where(InvProjection.id == projection_id)
    result = await db.execute(stmt)
    projection = result.scalar_one_or_none()

    if not projection:
        raise HTTPException(status_code=404, detail=f"Projection {projection_id} not found")

    return ATPCTPProjectionResponse.from_orm(projection)


@router.get("/summary/aggregate", response_model=ATPCTPSummaryResponse)
@require_capabilities(["view_atp_ctp"])
async def get_atp_ctp_summary(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Get aggregated ATP/CTP summary

    Returns:
        Summary statistics including total ATP/CTP, products at risk, etc.
    """
    stmt = select(InvProjection)

    if start_date:
        stmt = stmt.where(InvProjection.projection_date >= start_date)

    if end_date:
        stmt = stmt.where(InvProjection.projection_date <= end_date)

    result = await db.execute(stmt)
    projections = result.scalars().all()

    if not projections:
        return ATPCTPSummaryResponse(
            total_products=0,
            total_sites=0,
            total_atp_qty=0.0,
            total_ctp_qty=0.0,
            avg_days_of_supply=0.0,
            products_at_risk=0,
            sites_at_risk=0
        )

    # Aggregate metrics
    unique_products = set(p.product_id for p in projections)
    unique_sites = set(p.site_id for p in projections)
    total_atp = sum(p.atp_qty for p in projections)
    total_ctp = sum(p.ctp_qty for p in projections)
    avg_dos = sum(p.days_of_supply or 0.0 for p in projections) / len(projections)

    # Count products/sites at risk (stockout_probability > 0.5)
    products_at_risk = len(set(
        p.product_id for p in projections if p.stockout_probability and p.stockout_probability > 0.5
    ))
    sites_at_risk = len(set(
        p.site_id for p in projections if p.stockout_probability and p.stockout_probability > 0.5
    ))

    return ATPCTPSummaryResponse(
        total_products=len(unique_products),
        total_sites=len(unique_sites),
        total_atp_qty=total_atp,
        total_ctp_qty=total_ctp,
        avg_days_of_supply=avg_dos,
        products_at_risk=products_at_risk,
        sites_at_risk=sites_at_risk
    )


@router.get("/timeline/{product_id}/{site_id}", response_model=ATPCTPTimelineResponse)
@require_capabilities(["view_atp_ctp"])
async def get_atp_ctp_timeline(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: str,
    site_id: str,
    start_date: Optional[date] = Query(None, description="Start date (default: today)"),
    weeks: int = Query(12, ge=1, le=52, description="Number of weeks to show")
):
    """
    Get time-phased ATP/CTP timeline for a product-site

    Returns weekly ATP/CTP projections in chronological order,
    suitable for timeline charts and planning visualizations.

    Args:
        product_id: Product ID
        site_id: Site ID
        start_date: Starting date (default: today)
        weeks: Number of weeks (default: 12)

    Returns:
        Time-phased ATP/CTP timeline
    """
    if not start_date:
        start_date = date.today()

    end_date = start_date + timedelta(weeks=weeks)

    stmt = select(InvProjection).where(
        and_(
            InvProjection.product_id == product_id,
            InvProjection.site_id == site_id,
            InvProjection.projection_date >= start_date,
            InvProjection.projection_date < end_date
        )
    ).order_by(InvProjection.projection_date)

    result = await db.execute(stmt)
    projections = result.scalars().all()

    # Build timeline
    timeline = []
    for proj in projections:
        # Get scheduled receipts for this week (for display)
        receipts_stmt = select(func.sum(SupplyPlan.planned_order_quantity)).where(
            and_(
                SupplyPlan.product_id == product_id,
                SupplyPlan.site_id == site_id,
                SupplyPlan.planned_receipt_date >= proj.projection_date,
                SupplyPlan.planned_receipt_date < proj.projection_date + timedelta(weeks=1)
            )
        )
        result = await db.execute(receipts_stmt)
        scheduled_receipts = float(result.scalar() or 0.0)

        # Get planned shipments (outbound orders)
        # TODO: Add outbound_order table query
        planned_shipments = 0.0  # Placeholder

        timeline.append(TimelineEntry(
            week=proj.planning_week,
            projection_date=proj.projection_date,
            atp_qty=proj.atp_qty,
            ctp_qty=proj.ctp_qty,
            cumulative_atp=proj.cumulative_atp or 0.0,
            cumulative_ctp=proj.cumulative_ctp or 0.0,
            scheduled_receipts=scheduled_receipts,
            planned_shipments=planned_shipments
        ))

    return ATPCTPTimelineResponse(
        product_id=product_id,
        site_id=site_id,
        start_date=start_date,
        timeline=timeline
    )


@router.delete("/{projection_id}")
@require_capabilities(["manage_atp_ctp"])
async def delete_atp_ctp_projection(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    projection_id: int
):
    """Delete ATP/CTP projection"""
    stmt = select(InvProjection).where(InvProjection.id == projection_id)
    result = await db.execute(stmt)
    projection = result.scalar_one_or_none()

    if not projection:
        raise HTTPException(status_code=404, detail=f"Projection {projection_id} not found")

    await db.delete(projection)
    await db.commit()

    return {"status": "success", "message": f"Projection {projection_id} deleted"}


@router.delete("/bulk/delete")
@require_capabilities(["manage_atp_ctp"])
async def bulk_delete_projections(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    before_date: Optional[date] = None
):
    """
    Bulk delete ATP/CTP projections

    Args:
        product_id: Delete projections for this product
        site_id: Delete projections for this site
        before_date: Delete projections before this date

    Returns:
        Number of deleted projections
    """
    stmt = select(InvProjection)

    if product_id:
        stmt = stmt.where(InvProjection.product_id == product_id)

    if site_id:
        stmt = stmt.where(InvProjection.site_id == site_id)

    if before_date:
        stmt = stmt.where(InvProjection.projection_date < before_date)

    result = await db.execute(stmt)
    projections = result.scalars().all()

    deleted_count = len(projections)

    for proj in projections:
        await db.delete(proj)

    await db.commit()

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} projections"
    }

"""
Inventory Projection API Endpoints

Provides ATP/CTP calculation and order promising functionality.

Endpoints:
- Inventory Projection CRUD
- ATP Projection calculation and query
- CTP Projection calculation and query
- Order Promising (promise-to-order)
- Projection analytics and summaries
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import date, datetime, timedelta

from app.db.session import get_db
from app.models.user import User
from app.models.inventory_projection import (
    InvProjection, AtpProjection, CtpProjection, OrderPromise
)
from app.models.sc_entities import InvLevel, SupplyPlan
from app.models.production_order import ProductionOrder
from app.models.capacity_plan import CapacityPlan, CapacityResource
from app.models.supply_chain_config import Node
from app.models.sc_entities import Product
from app.schemas.inventory_projection import (
    InvProjectionCreate, InvProjectionUpdate, InvProjectionResponse, InvProjectionList,
    AtpProjectionCreate, AtpProjectionResponse, AtpProjectionList,
    CtpProjectionCreate, CtpProjectionResponse, CtpProjectionList,
    OrderPromiseCreate, OrderPromiseUpdate, OrderPromiseResponse, OrderPromiseList,
    CalculateAtpRequest, CalculateCtpRequest, OrderPromiseRequest, OrderPromiseResult,
    InvProjectionSummary, AtpAvailability, CtpAvailability,
    PromiseSource, FulfillmentType, PromiseStatus, AtpRuleType,
    AtpByDate, CtpByDate, AlternativePromise
)
from app.api.deps import get_current_user

router = APIRouter()


# ============================================================================
# Inventory Projection Endpoints
# ============================================================================

@router.post("/projections", response_model=InvProjectionResponse, status_code=status.HTTP_201_CREATED)
async def create_projection(
    projection: InvProjectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new inventory projection"""
    db_projection = InvProjection(
        **projection.model_dump(),
        created_by=current_user.id,
        updated_by=current_user.id
    )
    db.add(db_projection)
    await db.commit()
    await db.refresh(db_projection)
    return db_projection


@router.get("/projections", response_model=InvProjectionList)
async def list_projections(
    product_id: Optional[int] = None,
    site_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    scenario_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List inventory projections with filtering"""
    query = select(InvProjection)

    # Apply filters
    if product_id:
        query = query.where(InvProjection.product_id == product_id)
    if site_id:
        query = query.where(InvProjection.site_id == site_id)
    if start_date:
        query = query.where(InvProjection.projection_date >= start_date)
    if end_date:
        query = query.where(InvProjection.projection_date <= end_date)
    if scenario_id:
        query = query.where(InvProjection.scenario_id == scenario_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.order_by(InvProjection.projection_date, InvProjection.product_id)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return InvProjectionList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/projections/summary", response_model=InvProjectionSummary)
async def get_projection_summary(
    product_id: Optional[int] = None,
    site_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get summary statistics for inventory projections"""
    query = select(InvProjection)

    # Apply filters
    if product_id:
        query = query.where(InvProjection.product_id == product_id)
    if site_id:
        query = query.where(InvProjection.site_id == site_id)
    if start_date:
        query = query.where(InvProjection.projection_date >= start_date)
    if end_date:
        query = query.where(InvProjection.projection_date <= end_date)

    result = await db.execute(query)
    projections = result.scalars().all()

    if not projections:
        return InvProjectionSummary(
            total_projections=0,
            date_range="N/A",
            total_on_hand=0.0,
            total_available=0.0,
            total_atp=0.0,
            total_ctp=0.0,
            average_dos=None,
            stockout_count=0,
            high_risk_products=0
        )

    # Calculate metrics
    total_on_hand = sum(p.on_hand_qty for p in projections)
    total_available = sum(p.available_qty for p in projections)
    total_atp = sum(p.atp_qty for p in projections)
    total_ctp = sum(p.ctp_qty for p in projections)

    dos_values = [p.days_of_supply for p in projections if p.days_of_supply is not None]
    average_dos = sum(dos_values) / len(dos_values) if dos_values else None

    stockout_count = sum(1 for p in projections if p.closing_inventory <= 0)
    high_risk_count = sum(1 for p in projections
                          if p.stockout_probability and p.stockout_probability > 0.2)

    date_range = "N/A"
    if projections:
        min_date = min(p.projection_date for p in projections)
        max_date = max(p.projection_date for p in projections)
        date_range = f"{min_date} to {max_date}"

    return InvProjectionSummary(
        total_projections=len(projections),
        date_range=date_range,
        total_on_hand=total_on_hand,
        total_available=total_available,
        total_atp=total_atp,
        total_ctp=total_ctp,
        average_dos=average_dos,
        stockout_count=stockout_count,
        high_risk_products=high_risk_count
    )


@router.get("/projections/{projection_id}", response_model=InvProjectionResponse)
async def get_projection(
    projection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get single inventory projection"""
    result = await db.execute(
        select(InvProjection).where(InvProjection.id == projection_id)
    )
    projection = result.scalar_one_or_none()

    if not projection:
        raise HTTPException(status_code=404, detail="Projection not found")

    return projection


@router.patch("/projections/{projection_id}", response_model=InvProjectionResponse)
async def update_projection(
    projection_id: int,
    projection_update: InvProjectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update inventory projection"""
    result = await db.execute(
        select(InvProjection).where(InvProjection.id == projection_id)
    )
    projection = result.scalar_one_or_none()

    if not projection:
        raise HTTPException(status_code=404, detail="Projection not found")

    # Update fields
    for field, value in projection_update.model_dump(exclude_unset=True).items():
        setattr(projection, field, value)

    projection.updated_by = current_user.id
    projection.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(projection)
    return projection


@router.delete("/projections/{projection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_projection(
    projection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete inventory projection"""
    result = await db.execute(
        select(InvProjection).where(InvProjection.id == projection_id)
    )
    projection = result.scalar_one_or_none()

    if not projection:
        raise HTTPException(status_code=404, detail="Projection not found")

    await db.delete(projection)
    await db.commit()


# ============================================================================
# ATP Calculation Endpoints
# ============================================================================

@router.post("/atp/calculate", response_model=List[AtpProjectionResponse])
async def calculate_atp(
    request: CalculateAtpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate ATP (Available-to-Promise) projection

    ATP Logic:
    - Period 1: ATP = On-Hand - Allocated + Supply - Demand
    - Period N: ATP = Previous ATP + Supply - Demand
    - Cumulative ATP = Sum of all ATP through time
    """
    # Get current inventory
    inv_result = await db.execute(
        select(InvLevel)
        .where(and_(
            InvLevel.product_id == request.product_id,
            InvLevel.site_id == request.site_id
        ))
        .order_by(desc(InvLevel.inventory_date))
        .limit(1)
    )
    current_inv = inv_result.scalar_one_or_none()
    opening_balance = current_inv.on_hand_qty - current_inv.allocated_qty if current_inv else 0.0

    # Get supply plans (planned receipts)
    supply_result = await db.execute(
        select(SupplyPlan)
        .where(and_(
            SupplyPlan.product_id == request.product_id,
            SupplyPlan.site_id == request.site_id,
            SupplyPlan.plan_date >= request.start_date,
            SupplyPlan.plan_date <= request.end_date
        ))
    )
    supply_plans = supply_result.scalars().all()

    # Create ATP projections
    atp_projections = []
    cumulative_atp = opening_balance
    current_date = request.start_date

    while current_date <= request.end_date:
        # Get supply for this period
        supply_qty = sum(
            sp.planned_order_quantity for sp in supply_plans
            if sp.plan_date == current_date
        )

        # Get demand for this period (simplified - could come from forecast/orders)
        demand_qty = sum(
            sp.demand_quantity for sp in supply_plans
            if sp.plan_date == current_date
        )

        # Calculate ATP
        if current_date == request.start_date:
            # Period 1: ATP = Opening - Allocated + Supply - Demand
            atp_qty = opening_balance + supply_qty - demand_qty
        else:
            # Period N: ATP = Previous ATP + Supply - Demand
            atp_qty = supply_qty - demand_qty

        cumulative_atp += atp_qty

        # Create ATP projection
        atp_projection = AtpProjection(
            company_id=current_user.customer_id,
            product_id=request.product_id,
            site_id=request.site_id,
            atp_date=current_date,
            atp_qty=max(0.0, atp_qty),
            cumulative_atp_qty=max(0.0, cumulative_atp),
            opening_balance=opening_balance if current_date == request.start_date else cumulative_atp - atp_qty,
            supply_qty=supply_qty,
            demand_qty=demand_qty,
            allocated_qty=0.0,  # Could be calculated from orders
            customer_id=request.customer_id,
            atp_rule=request.atp_rule.value,
            config_id=request.config_id,
            scenario_id=request.scenario_id,
            created_by=current_user.id
        )

        db.add(atp_projection)
        atp_projections.append(atp_projection)

        current_date += timedelta(days=7)  # Weekly buckets

    await db.commit()

    # Refresh all projections
    for proj in atp_projections:
        await db.refresh(proj)

    return atp_projections


@router.get("/atp/availability", response_model=AtpAvailability)
async def get_atp_availability(
    product_id: int,
    site_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get ATP availability for a product-site combination"""
    query = select(AtpProjection).where(and_(
        AtpProjection.product_id == product_id,
        AtpProjection.site_id == site_id
    ))

    if start_date:
        query = query.where(AtpProjection.atp_date >= start_date)
    if end_date:
        query = query.where(AtpProjection.atp_date <= end_date)

    query = query.order_by(AtpProjection.atp_date)

    result = await db.execute(query)
    projections = result.scalars().all()

    if not projections:
        raise HTTPException(status_code=404, detail="No ATP projections found")

    # Current ATP (first period)
    current_atp = projections[0].cumulative_atp_qty

    # Future ATP by date
    future_atp = [
        AtpByDate(
            date=p.atp_date,
            atp_qty=p.atp_qty,
            cumulative_atp=p.cumulative_atp_qty
        )
        for p in projections
    ]

    # Total available
    total_available = sum(p.atp_qty for p in projections)

    return AtpAvailability(
        product_id=product_id,
        site_id=site_id,
        current_atp=current_atp,
        future_atp=future_atp,
        total_available=total_available
    )


# ============================================================================
# CTP Calculation Endpoints
# ============================================================================

@router.post("/ctp/calculate", response_model=List[CtpProjectionResponse])
async def calculate_ctp(
    request: CalculateCtpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate CTP (Capable-to-Promise) projection

    CTP Logic:
    - CTP = ATP + Available Production Capacity
    - Check component availability if requested
    - Check resource capacity if requested
    """
    # First calculate ATP
    atp_request = CalculateAtpRequest(
        product_id=request.product_id,
        site_id=request.site_id,
        start_date=request.start_date,
        end_date=request.end_date,
        config_id=request.config_id,
        scenario_id=request.scenario_id
    )
    atp_projections = await calculate_atp(atp_request, db, current_user)

    # Get production capacity if requested
    ctp_projections = []

    for atp_proj in atp_projections:
        production_capacity_qty = 0.0
        component_constrained = False
        resource_constrained = False
        constraining_component_id = None
        constraining_resource = None

        if request.include_production_capacity:
            # Get capacity plan for this period
            capacity_result = await db.execute(
                select(CapacityPlan)
                .where(and_(
                    CapacityPlan.config_id == request.config_id,
                    CapacityPlan.start_date <= atp_proj.atp_date,
                    CapacityPlan.end_date >= atp_proj.atp_date
                ))
                .limit(1)
            )
            capacity_plan = capacity_result.scalar_one_or_none()

            if capacity_plan:
                # Check resource capacity
                resource_result = await db.execute(
                    select(CapacityResource)
                    .where(CapacityResource.plan_id == capacity_plan.id)
                )
                resources = resource_result.scalars().all()

                for resource in resources:
                    utilization = (resource.required_capacity / resource.available_capacity * 100
                                   if resource.available_capacity > 0 else 0)
                    if utilization >= 95:
                        resource_constrained = True
                        constraining_resource = resource.resource_name
                        break

                # If not constrained, calculate available capacity
                if not resource_constrained and resources:
                    avg_utilization = sum(
                        r.required_capacity / r.available_capacity
                        for r in resources if r.available_capacity > 0
                    ) / len(resources)
                    # Simplified: assume 1:1 capacity to production qty
                    production_capacity_qty = sum(
                        r.available_capacity - r.required_capacity
                        for r in resources
                    ) / len(resources)

        # Calculate CTP
        ctp_qty = atp_proj.cumulative_atp_qty + production_capacity_qty

        # Create CTP projection
        ctp_projection = CtpProjection(
            company_id=current_user.customer_id,
            product_id=request.product_id,
            site_id=request.site_id,
            ctp_date=atp_proj.atp_date,
            ctp_qty=max(0.0, ctp_qty),
            atp_qty=atp_proj.cumulative_atp_qty,
            production_capacity_qty=production_capacity_qty,
            component_constrained=component_constrained,
            constraining_component_id=constraining_component_id,
            resource_constrained=resource_constrained,
            constraining_resource=constraining_resource,
            config_id=request.config_id,
            scenario_id=request.scenario_id,
            created_by=current_user.id
        )

        db.add(ctp_projection)
        ctp_projections.append(ctp_projection)

    await db.commit()

    # Refresh all projections
    for proj in ctp_projections:
        await db.refresh(proj)

    return ctp_projections


@router.get("/ctp/availability", response_model=CtpAvailability)
async def get_ctp_availability(
    product_id: int,
    site_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get CTP availability for a product-site combination"""
    query = select(CtpProjection).where(and_(
        CtpProjection.product_id == product_id,
        CtpProjection.site_id == site_id
    ))

    if start_date:
        query = query.where(CtpProjection.ctp_date >= start_date)
    if end_date:
        query = query.where(CtpProjection.ctp_date <= end_date)

    query = query.order_by(CtpProjection.ctp_date)

    result = await db.execute(query)
    projections = result.scalars().all()

    if not projections:
        raise HTTPException(status_code=404, detail="No CTP projections found")

    # Current CTP (first period)
    current_ctp = projections[0].ctp_qty

    # Future CTP by date
    future_ctp = []
    constraints = []

    for p in projections:
        constraint_reason = None
        constrained = p.component_constrained or p.resource_constrained

        if p.component_constrained:
            constraint_reason = f"Component: {p.constraining_component_id}"
            constraints.append(constraint_reason)
        if p.resource_constrained:
            constraint_reason = f"Resource: {p.constraining_resource}"
            constraints.append(constraint_reason)

        future_ctp.append(CtpByDate(
            date=p.ctp_date,
            ctp_qty=p.ctp_qty,
            constrained=constrained,
            constraint_reason=constraint_reason
        ))

    # Unique constraints
    constraints = list(set(constraints))

    return CtpAvailability(
        product_id=product_id,
        site_id=site_id,
        current_ctp=current_ctp,
        future_ctp=future_ctp,
        constraints=constraints
    )


# ============================================================================
# Order Promising Endpoints
# ============================================================================

@router.post("/promise", response_model=OrderPromiseResult)
async def promise_order(
    request: OrderPromiseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Promise an order using ATP/CTP logic

    Returns the best promise with alternatives if partial/backorder needed.
    """
    # Get ATP availability
    atp_result = await db.execute(
        select(AtpProjection)
        .where(and_(
            AtpProjection.product_id == request.product_id,
            AtpProjection.site_id == request.site_id,
            AtpProjection.atp_date >= request.requested_date
        ))
        .order_by(AtpProjection.atp_date)
        .limit(4)  # Look ahead 4 periods
    )
    atp_projections = atp_result.scalars().all()

    # Get CTP availability
    ctp_result = await db.execute(
        select(CtpProjection)
        .where(and_(
            CtpProjection.product_id == request.product_id,
            CtpProjection.site_id == request.site_id,
            CtpProjection.ctp_date >= request.requested_date
        ))
        .order_by(CtpProjection.ctp_date)
        .limit(4)
    )
    ctp_projections = ctp_result.scalars().all()

    # Try to fulfill from ATP first
    can_promise = False
    promised_quantity = 0.0
    promised_date = request.requested_date
    promise_source = PromiseSource.BACKORDER
    fulfillment_type = FulfillmentType.SINGLE
    partial_promise = False
    backorder_quantity = None
    backorder_date = None
    alternatives = []
    confidence = 0.0
    confidence_factors = []

    # Check ATP for requested date
    atp_on_date = next((p for p in atp_projections if p.atp_date == request.requested_date), None)

    if atp_on_date and atp_on_date.cumulative_atp_qty >= request.requested_quantity:
        # Full fulfillment from ATP
        can_promise = True
        promised_quantity = request.requested_quantity
        promise_source = PromiseSource.ATP
        confidence = 0.95
        confidence_factors.append("Sufficient ATP available")

    elif request.allow_partial and atp_on_date and atp_on_date.cumulative_atp_qty > 0:
        # Partial fulfillment
        can_promise = True
        promised_quantity = atp_on_date.cumulative_atp_qty
        promise_source = PromiseSource.ATP
        fulfillment_type = FulfillmentType.PARTIAL
        partial_promise = True
        backorder_quantity = request.requested_quantity - promised_quantity
        confidence = 0.75
        confidence_factors.append("Partial ATP available")

        # Find backorder date
        for proj in atp_projections[1:]:
            if proj.cumulative_atp_qty >= backorder_quantity:
                backorder_date = proj.atp_date
                break

    # If ATP insufficient, try CTP
    if not can_promise or (partial_promise and request.allow_backorder):
        ctp_on_date = next((p for p in ctp_projections if p.ctp_date == request.requested_date), None)

        if ctp_on_date and ctp_on_date.ctp_qty >= request.requested_quantity:
            can_promise = True
            promised_quantity = request.requested_quantity
            promised_date = ctp_on_date.earliest_ship_date or ctp_on_date.ctp_date
            promise_source = PromiseSource.CTP
            fulfillment_type = FulfillmentType.SINGLE
            partial_promise = False
            backorder_quantity = None
            confidence = 0.85 if not ctp_on_date.component_constrained and not ctp_on_date.resource_constrained else 0.65
            confidence_factors.append("Production capacity available")

            if ctp_on_date.component_constrained:
                confidence_factors.append("Component constraint risk")
            if ctp_on_date.resource_constrained:
                confidence_factors.append("Resource constraint risk")

    # Generate alternatives
    for i, atp_proj in enumerate(atp_projections[1:], 1):
        if atp_proj.cumulative_atp_qty >= request.requested_quantity:
            alternatives.append(AlternativePromise(
                option_type="later_date",
                product_id=request.product_id,
                quantity=request.requested_quantity,
                delivery_date=atp_proj.atp_date,
                confidence=0.90
            ))
            if len(alternatives) >= 2:
                break

    # Create order promise record
    order_promise = OrderPromise(
        order_id=request.order_id,
        order_line_number=request.order_line_number,
        company_id=current_user.customer_id,
        product_id=request.product_id,
        site_id=request.site_id,
        customer_id=request.customer_id,
        requested_quantity=request.requested_quantity,
        requested_date=request.requested_date,
        promised_quantity=promised_quantity,
        promised_date=promised_date,
        promise_source=promise_source.value,
        fulfillment_type=fulfillment_type.value,
        partial_promise=partial_promise,
        backorder_quantity=backorder_quantity,
        backorder_date=backorder_date,
        promise_status=PromiseStatus.PROPOSED.value,
        promise_confidence=confidence,
        created_by=current_user.id
    )

    db.add(order_promise)
    await db.commit()
    await db.refresh(order_promise)

    return OrderPromiseResult(
        can_promise=can_promise,
        promised_quantity=promised_quantity,
        promised_date=promised_date,
        promise_source=promise_source,
        fulfillment_type=fulfillment_type,
        partial_promise=partial_promise,
        backorder_quantity=backorder_quantity,
        backorder_date=backorder_date,
        alternatives=alternatives,
        confidence=confidence,
        confidence_factors=confidence_factors
    )


@router.get("/promises", response_model=OrderPromiseList)
async def list_order_promises(
    order_id: Optional[str] = None,
    product_id: Optional[int] = None,
    customer_id: Optional[str] = None,
    promise_status: Optional[PromiseStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List order promises with filtering"""
    query = select(OrderPromise)

    # Apply filters
    if order_id:
        query = query.where(OrderPromise.order_id == order_id)
    if product_id:
        query = query.where(OrderPromise.product_id == product_id)
    if customer_id:
        query = query.where(OrderPromise.customer_id == customer_id)
    if promise_status:
        query = query.where(OrderPromise.promise_status == promise_status.value)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Pagination
    query = query.order_by(desc(OrderPromise.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return OrderPromiseList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/promises/{promise_id}", response_model=OrderPromiseResponse)
async def get_order_promise(
    promise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get single order promise"""
    result = await db.execute(
        select(OrderPromise).where(OrderPromise.id == promise_id)
    )
    promise = result.scalar_one_or_none()

    if not promise:
        raise HTTPException(status_code=404, detail="Promise not found")

    return promise


@router.patch("/promises/{promise_id}", response_model=OrderPromiseResponse)
async def update_order_promise(
    promise_id: int,
    promise_update: OrderPromiseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update order promise (e.g., confirm, fulfill, cancel)"""
    result = await db.execute(
        select(OrderPromise).where(OrderPromise.id == promise_id)
    )
    promise = result.scalar_one_or_none()

    if not promise:
        raise HTTPException(status_code=404, detail="Promise not found")

    # Update fields
    for field, value in promise_update.model_dump(exclude_unset=True).items():
        setattr(promise, field, value)

    promise.updated_by = current_user.id
    promise.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(promise)
    return promise

"""
Lot Sizing API Endpoints

Provides lot sizing calculation and comparison capabilities.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, distinct
from typing import Dict, List, Optional
from datetime import date

from app.db.session import get_db
from app.models.user import User
from app.models.mps import MPSPlan, MPSPlanItem
from app.api.deps import get_current_user
from app.schemas.lot_sizing import (
    LotSizingInputRequest,
    LotSizingResultResponse,
    LotSizingComparisonRequest,
    LotSizingComparisonResponse,
    MPSLotSizingRequest,
    MPSLotSizingResponse,
    LotSizingVisualizationData,
    CapacityCheckRequest,
    CapacityCheckResponse,
    CapacityCheckDetail,
    ResourceRequirementRequest,
    MultiProductLotSizingRequest,
    MultiProductLotSizingResponse,
    ProductLotSizingResult,
)
from app.services.lot_sizing import (
    LotSizingInput,
    calculate_lot_size,
    compare_algorithms,
    get_best_algorithm
)
from app.services.capacity_constrained_mps import (
    CapacityConstrainedMPS,
    MPSProductionPlan,
    ResourceRequirement,
    CapacityConstrainedMPSResult,
)

router = APIRouter()


@router.post("/calculate", response_model=LotSizingResultResponse)
async def calculate_lot_sizes(
    request: LotSizingInputRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Calculate lot sizes using specified algorithm

    Supports 5 algorithms:
    - LFL: Lot-for-Lot (exact demand matching)
    - EOQ: Economic Order Quantity (Wilson's formula)
    - POQ: Period Order Quantity (EOQ adapted for periods)
    - FOQ: Fixed Order Quantity (fixed batch size)
    - PPB: Part Period Balancing (setup vs holding cost trade-off)
    """
    # Convert request to LotSizingInput
    inputs = LotSizingInput(
        demand_schedule=request.demand_schedule,
        start_date=request.start_date,
        period_days=request.period_days,
        setup_cost=request.setup_cost,
        holding_cost_per_unit_per_period=request.holding_cost_per_unit_per_period,
        unit_cost=request.unit_cost,
        min_order_quantity=request.min_order_quantity,
        max_order_quantity=request.max_order_quantity,
        order_multiple=request.order_multiple,
        annual_demand=request.annual_demand
    )

    # Calculate lot sizes
    # Default to EOQ if not specified in request (will be from path param in actual use)
    algorithm = "EOQ"  # This would come from path parameter
    kwargs = {}
    if algorithm == "FOQ" and request.fixed_quantity:
        kwargs["fixed_quantity"] = request.fixed_quantity

    result = calculate_lot_size(inputs, algorithm, **kwargs)

    return LotSizingResultResponse(
        algorithm=result.algorithm,
        order_schedule=result.order_schedule,
        total_cost=result.total_cost,
        setup_cost_total=result.setup_cost_total,
        holding_cost_total=result.holding_cost_total,
        number_of_orders=result.number_of_orders,
        average_inventory=result.average_inventory,
        service_level=result.service_level,
        inventory_turns=result.inventory_turns,
        details=result.details
    )


@router.post("/calculate/{algorithm}", response_model=LotSizingResultResponse)
async def calculate_lot_sizes_with_algorithm(
    algorithm: str,
    request: LotSizingInputRequest,
    current_user: User = Depends(get_current_user)
):
    """Calculate lot sizes using specific algorithm"""
    inputs = LotSizingInput(
        demand_schedule=request.demand_schedule,
        start_date=request.start_date,
        period_days=request.period_days,
        setup_cost=request.setup_cost,
        holding_cost_per_unit_per_period=request.holding_cost_per_unit_per_period,
        unit_cost=request.unit_cost,
        min_order_quantity=request.min_order_quantity,
        max_order_quantity=request.max_order_quantity,
        order_multiple=request.order_multiple,
        annual_demand=request.annual_demand
    )

    kwargs = {}
    if algorithm.upper() == "FOQ":
        if request.fixed_quantity:
            kwargs["fixed_quantity"] = request.fixed_quantity
        else:
            # Default to a reasonable value
            total_demand = sum(request.demand_schedule)
            kwargs["fixed_quantity"] = total_demand / len(request.demand_schedule) * 4

    try:
        result = calculate_lot_size(inputs, algorithm, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return LotSizingResultResponse(
        algorithm=result.algorithm,
        order_schedule=result.order_schedule,
        total_cost=result.total_cost,
        setup_cost_total=result.setup_cost_total,
        holding_cost_total=result.holding_cost_total,
        number_of_orders=result.number_of_orders,
        average_inventory=result.average_inventory,
        service_level=result.service_level,
        inventory_turns=result.inventory_turns,
        details=result.details
    )


@router.post("/compare", response_model=LotSizingComparisonResponse)
async def compare_lot_sizing_algorithms(
    request: LotSizingComparisonRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Compare multiple lot sizing algorithms

    Returns results for all requested algorithms with cost breakdown,
    identifies the best algorithm (lowest total cost), and calculates
    cost savings vs Lot-for-Lot baseline.
    """
    inputs = LotSizingInput(
        demand_schedule=request.demand_schedule,
        start_date=request.start_date,
        period_days=request.period_days,
        setup_cost=request.setup_cost,
        holding_cost_per_unit_per_period=request.holding_cost_per_unit_per_period,
        unit_cost=request.unit_cost,
        min_order_quantity=request.min_order_quantity,
        max_order_quantity=request.max_order_quantity,
        order_multiple=request.order_multiple,
        annual_demand=request.annual_demand
    )

    # Get algorithm names
    algorithms = [algo.value for algo in request.algorithms]

    # Compare algorithms
    results_dict = compare_algorithms(inputs, algorithms)

    # Convert to response format
    results_response = {
        algo: LotSizingResultResponse(
            algorithm=result.algorithm,
            order_schedule=result.order_schedule,
            total_cost=result.total_cost,
            setup_cost_total=result.setup_cost_total,
            holding_cost_total=result.holding_cost_total,
            number_of_orders=result.number_of_orders,
            average_inventory=result.average_inventory,
            service_level=result.service_level,
            inventory_turns=result.inventory_turns,
            details=result.details
        )
        for algo, result in results_dict.items()
    }

    # Find best algorithm
    best_algo, best_result = get_best_algorithm(inputs)
    best_cost = best_result.total_cost

    # Calculate savings vs LFL
    cost_savings_vs_lfl = None
    if "LFL" in results_dict:
        lfl_cost = results_dict["LFL"].total_cost
        if lfl_cost > 0:
            cost_savings_vs_lfl = ((lfl_cost - best_cost) / lfl_cost) * 100

    return LotSizingComparisonResponse(
        results=results_response,
        best_algorithm=best_algo,
        best_total_cost=best_cost,
        cost_savings_vs_lfl=cost_savings_vs_lfl
    )


@router.post("/mps/{plan_id}/apply", response_model=MPSLotSizingResponse)
async def apply_lot_sizing_to_mps(
    plan_id: int,
    request: MPSLotSizingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Apply lot sizing algorithm to an existing MPS plan

    Updates the MPS plan items with lot-sized quantities,
    replacing the original planned quantities.
    """
    # Get MPS plan
    result = await db.execute(
        select(MPSPlan).where(MPSPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="MPS plan not found")

    # Get plan items
    items_result = await db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == plan_id)
    )
    plan_items = items_result.scalars().all()

    if not plan_items:
        raise HTTPException(status_code=400, detail="MPS plan has no items")

    # Process each item
    items_processed = 0
    total_cost_before = 0.0
    total_cost_after = 0.0
    items_data = []

    for item in plan_items:
        # Extract demand schedule from weekly_quantities
        if not item.weekly_quantities:
            continue

        import json
        if isinstance(item.weekly_quantities, str):
            demand_schedule = json.loads(item.weekly_quantities)
        else:
            demand_schedule = item.weekly_quantities

        # Create lot sizing input
        inputs = LotSizingInput(
            demand_schedule=demand_schedule,
            start_date=plan.start_date,
            period_days=7,  # Weekly buckets
            setup_cost=request.setup_cost or 500.0,  # Default setup cost
            holding_cost_per_unit_per_period=request.holding_cost_per_unit_per_period or 0.5,
            unit_cost=request.unit_cost or 10.0,
            min_order_quantity=request.min_order_quantity,
            max_order_quantity=request.max_order_quantity,
            order_multiple=request.order_multiple
        )

        # Calculate lot sizes
        kwargs = {}
        if request.algorithm.value == "FOQ":
            kwargs["fixed_quantity"] = request.fixed_quantity or 1000

        result_before = calculate_lot_size(inputs, "LFL")  # Baseline
        result_after = calculate_lot_size(inputs, request.algorithm.value, **kwargs)

        # Update item with lot-sized quantities
        item.weekly_quantities = json.dumps(result_after.order_schedule)

        items_data.append({
            "item_id": item.item_id,
            "product_name": f"Product {item.item_id}",
            "demand_schedule": demand_schedule,
            "order_schedule_before": result_before.order_schedule,
            "order_schedule_after": result_after.order_schedule,
            "cost_before": result_before.total_cost,
            "cost_after": result_after.total_cost,
            "cost_savings": result_before.total_cost - result_after.total_cost
        })

        total_cost_before += result_before.total_cost
        total_cost_after += result_after.total_cost
        items_processed += 1

    # Save changes
    await db.commit()

    cost_savings = total_cost_before - total_cost_after
    cost_savings_percent = (cost_savings / total_cost_before * 100) if total_cost_before > 0 else 0

    return MPSLotSizingResponse(
        plan_id=plan_id,
        algorithm=request.algorithm.value,
        items_processed=items_processed,
        total_cost_before=total_cost_before,
        total_cost_after=total_cost_after,
        cost_savings=cost_savings,
        cost_savings_percent=cost_savings_percent,
        items=items_data
    )


@router.get("/visualization/{algorithm}", response_model=LotSizingVisualizationData)
async def get_lot_sizing_visualization(
    algorithm: str,
    demand_schedule: str,  # Comma-separated values
    setup_cost: float = 500.0,
    holding_cost: float = 0.5,
    current_user: User = Depends(get_current_user)
):
    """
    Get visualization data for lot sizing algorithm

    Returns period-by-period demand, orders, inventory, and cumulative costs
    for charting in the UI.
    """
    # Parse demand schedule
    try:
        demand = [float(x.strip()) for x in demand_schedule.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid demand schedule format")

    from datetime import date, timedelta

    inputs = LotSizingInput(
        demand_schedule=demand,
        start_date=date.today(),
        period_days=7,
        setup_cost=setup_cost,
        holding_cost_per_unit_per_period=holding_cost
    )

    result = calculate_lot_size(inputs, algorithm)

    # Calculate period-by-period inventory and cumulative cost
    inventory_levels = []
    cumulative_costs = []
    inventory = 0.0
    cumulative_cost = 0.0

    for period in range(len(demand)):
        # Order received
        inventory += result.order_schedule[period]
        if result.order_schedule[period] > 0:
            cumulative_cost += setup_cost

        # Demand consumed
        inventory -= demand[period]

        # Holding cost
        if inventory > 0:
            holding_cost_period = inventory * holding_cost
            cumulative_cost += holding_cost_period

        inventory_levels.append(max(0, inventory))
        cumulative_costs.append(cumulative_cost)

    # Generate period labels
    periods = [(inputs.start_date + timedelta(days=i * 7)).strftime("%Y-%m-%d")
               for i in range(len(demand))]

    return LotSizingVisualizationData(
        periods=periods,
        demand=demand,
        orders=result.order_schedule,
        inventory=inventory_levels,
        cumulative_cost=cumulative_costs
    )


# ============================================================================
# Capacity-Constrained MPS Endpoints
# ============================================================================

@router.post("/capacity-check", response_model=CapacityCheckResponse)
async def check_capacity_constraints(
    request: CapacityCheckRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Check capacity constraints for production plan using RCCP
    
    Validates production plan against resource capacity and applies
    leveling strategy if constraints are detected.
    
    Strategies:
    - level: Smooth production across periods
    - shift: Move production to earlier periods
    - reduce: Cap production at maximum feasible
    """
    # Convert request resources to ResourceRequirement objects
    resources = [
        ResourceRequirement(
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            units_per_product=r.units_per_product,
            available_capacity=r.available_capacity,
            utilization_target=r.utilization_target
        )
        for r in request.resources
    ]
    
    # Create MPS production plan
    mps_plan = MPSProductionPlan(
        product_id=request.product_id or 1,
        product_name=request.product_name or "Product",
        planned_quantities=request.production_plan.copy(),
        resource_requirements=resources
    )
    
    # Run capacity check
    rccp = CapacityConstrainedMPS(request.start_date, request.period_days)
    result = rccp.generate_feasible_plan(mps_plan, strategy=request.strategy)
    
    # Convert capacity checks to response format
    capacity_checks = [
        CapacityCheckDetail(
            period=check.period,
            period_date=check.period_date.isoformat(),
            resource_id=check.resource_id,
            resource_name=check.resource_name,
            required_capacity=check.required_capacity,
            available_capacity=check.available_capacity,
            utilization=check.utilization,
            is_constrained=check.is_constrained,
            is_over_target=check.is_over_target,
            shortage=check.shortage
        )
        for check in result.capacity_checks
    ]
    
    return CapacityCheckResponse(
        original_plan=result.original_plan,
        feasible_plan=result.feasible_plan,
        is_feasible=result.is_feasible,
        capacity_checks=capacity_checks,
        bottleneck_resources=result.bottleneck_resources,
        total_shortage=result.total_shortage,
        utilization_summary=result.utilization_summary,
        recommendations=result.recommendations
    )


@router.post("/mps/{plan_id}/capacity-check", response_model=CapacityCheckResponse)
async def check_mps_capacity(
    plan_id: int,
    resources: List[ResourceRequirementRequest],
    strategy: str = "level",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check capacity constraints for an existing MPS plan
    
    Loads the MPS plan from database and validates against provided
    resource requirements.
    """
    # Get MPS plan
    result = await db.execute(
        select(MPSPlan).where(MPSPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(status_code=404, detail="MPS plan not found")
    
    # Get plan items
    items_result = await db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == plan_id)
    )
    plan_items = items_result.scalars().all()
    
    if not plan_items:
        raise HTTPException(status_code=400, detail="MPS plan has no items")
    
    # For now, check first item only (can be extended to multi-product)
    item = plan_items[0]
    
    # Extract production schedule
    import json
    if isinstance(item.weekly_quantities, str):
        production_plan = json.loads(item.weekly_quantities)
    else:
        production_plan = item.weekly_quantities
    
    # Create capacity check request
    request = CapacityCheckRequest(
        production_plan=production_plan,
        start_date=plan.start_date,
        period_days=7,  # Weekly buckets
        resources=resources,
        strategy=strategy,
        product_id=item.product_id,
        product_name=f"Product {item.product_id}"
    )
    
    # Reuse the main capacity check endpoint logic
    return await check_capacity_constraints(request, current_user)


# ============================================================================
# Multi-Product Lot Sizing Endpoints
# ============================================================================

@router.post("/multi-product/compare", response_model=MultiProductLotSizingResponse)
async def compare_multi_product_lot_sizing(
    request: MultiProductLotSizingRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Compare lot sizing for multiple products simultaneously
    
    Optimizes batch sizes across multiple products using the same algorithm.
    Useful for production planning when multiple products share resources.
    """
    from app.schemas.lot_sizing import (
        MultiProductLotSizingResponse,
        ProductLotSizingResult,
        ProductLotSizingInput,
        MultiProductLotSizingRequest,
    )
    
    product_results = []
    total_cost = 0.0
    total_orders = 0
    
    for product_input in request.products:
        # Create lot sizing input for this product
        inputs = LotSizingInput(
            demand_schedule=product_input.demand_schedule,
            start_date=request.start_date,
            period_days=request.period_days,
            setup_cost=product_input.setup_cost,
            holding_cost_per_unit_per_period=product_input.holding_cost_per_unit_per_period,
            unit_cost=product_input.unit_cost,
            min_order_quantity=product_input.min_order_quantity,
            max_order_quantity=product_input.max_order_quantity,
            order_multiple=product_input.order_multiple,
        )
        
        # Calculate lot sizes
        kwargs = {}
        if request.algorithm.value == "FOQ" and product_input.fixed_quantity:
            kwargs["fixed_quantity"] = product_input.fixed_quantity
        
        result = calculate_lot_size(inputs, request.algorithm.value, **kwargs)
        
        # Add to results
        product_results.append(ProductLotSizingResult(
            product_id=product_input.product_id,
            product_name=product_input.product_name,
            algorithm=result.algorithm,
            order_schedule=result.order_schedule,
            total_cost=result.total_cost,
            setup_cost_total=result.setup_cost_total,
            holding_cost_total=result.holding_cost_total,
            number_of_orders=result.number_of_orders,
            average_inventory=result.average_inventory
        ))
        
        total_cost += result.total_cost
        total_orders += result.number_of_orders
    
    # Calculate summary statistics
    summary = {
        "total_cost": total_cost,
        "total_orders": total_orders,
        "avg_cost_per_product": total_cost / len(product_results) if product_results else 0,
        "avg_orders_per_product": total_orders / len(product_results) if product_results else 0,
    }
    
    return MultiProductLotSizingResponse(
        products=product_results,
        total_cost=total_cost,
        total_orders=total_orders,
        summary=summary
    )


# ============================================================================
# Export Endpoints
# ============================================================================

from fastapi.responses import StreamingResponse
import io
import csv

@router.post("/export/csv")
async def export_lot_sizing_csv(
    request: LotSizingComparisonRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Export lot sizing comparison results as CSV
    
    Returns a CSV file with comparison results for all algorithms.
    """
    # Convert request to LotSizingInput
    inputs = LotSizingInput(
        demand_schedule=request.demand_schedule,
        start_date=request.start_date,
        period_days=request.period_days,
        setup_cost=request.setup_cost,
        holding_cost_per_unit_per_period=request.holding_cost_per_unit_per_period,
        unit_cost=request.unit_cost,
        min_order_quantity=request.min_order_quantity,
        max_order_quantity=request.max_order_quantity,
        order_multiple=request.order_multiple,
        annual_demand=request.annual_demand,
    )
    
    # Compare algorithms
    results = compare_algorithms(inputs, [algo.value for algo in request.algorithms])
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Algorithm',
        'Total Cost',
        'Setup Cost',
        'Holding Cost',
        'Number of Orders',
        'Average Inventory',
        'Service Level'
    ])
    
    # Write data rows
    for algo, result in results.items():
        writer.writerow([
            algo,
            f"{result.total_cost:.2f}",
            f"{result.setup_cost_total:.2f}",
            f"{result.holding_cost_total:.2f}",
            result.number_of_orders,
            f"{result.average_inventory:.2f}",
            f"{result.service_level:.2%}"
        ])
    
    # Return as downloadable file
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lot_sizing_comparison.csv"}
    )


# ============================================================================
# Order Sizing Analysis (from live supply plan)
# ============================================================================

@router.get("/order-analysis")
async def get_order_sizing_analysis(
    config_id: int = Query(..., description="Supply chain config ID"),
    plan_version: str = Query("live", description="Plan version"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze order sizing from the live supply plan.

    Returns summary metrics, order size distribution, and per-product breakdown
    for the lot sizing analysis page.
    """
    from app.models.sc_entities import SupplyPlan, Product

    # Verify user has access to this config
    user_config_id = current_user.default_config_id if current_user else None
    if user_config_id and user_config_id != config_id:
        raise HTTPException(status_code=403, detail="Access denied to this config")

    base_filter = and_(
        SupplyPlan.config_id == config_id,
        SupplyPlan.plan_version == plan_version,
        SupplyPlan.planned_order_quantity > 0,
    )

    # --- Summary statistics ---
    summary_stmt = select(
        func.count(SupplyPlan.id).label("total_orders"),
        func.avg(SupplyPlan.planned_order_quantity).label("avg_order_qty"),
        func.min(SupplyPlan.planned_order_quantity).label("min_order_qty"),
        func.max(SupplyPlan.planned_order_quantity).label("max_order_qty"),
        func.sum(SupplyPlan.planned_order_quantity).label("total_qty"),
        func.min(SupplyPlan.plan_date).label("date_start"),
        func.max(SupplyPlan.plan_date).label("date_end"),
        func.count(distinct(SupplyPlan.product_id)).label("product_count"),
        func.count(distinct(SupplyPlan.site_id)).label("site_count"),
    ).where(base_filter)
    summary_result = await db.execute(summary_stmt)
    summary = summary_result.one()

    total_orders = summary.total_orders or 0
    if total_orders == 0:
        return {
            "summary": {
                "total_orders": 0,
                "avg_order_qty": 0,
                "min_order_qty": 0,
                "max_order_qty": 0,
                "total_qty": 0,
                "orders_per_week": 0,
                "product_count": 0,
                "site_count": 0,
            },
            "distribution": [],
            "by_product": [],
        }

    # Calculate orders per week
    date_start = summary.date_start
    date_end = summary.date_end
    weeks_span = max(1, ((date_end - date_start).days + 1) / 7)
    orders_per_week = round(total_orders / weeks_span, 1)

    # --- Order size distribution (histogram buckets) ---
    max_qty = float(summary.max_order_qty)
    min_qty = float(summary.min_order_qty)
    bucket_count = 10
    bucket_size = max(1, (max_qty - min_qty) / bucket_count)

    # Use CASE to bucket orders
    dist_stmt = select(
        func.floor((SupplyPlan.planned_order_quantity - min_qty) / bucket_size).label("bucket"),
        func.count(SupplyPlan.id).label("count"),
    ).where(base_filter).group_by("bucket").order_by("bucket")
    dist_result = await db.execute(dist_stmt)
    dist_rows = dist_result.all()

    distribution = []
    for row in dist_rows:
        bucket_idx = int(row.bucket) if row.bucket is not None else 0
        bucket_idx = min(bucket_idx, bucket_count - 1)  # Clamp max value bucket
        range_start = round(min_qty + bucket_idx * bucket_size)
        range_end = round(min_qty + (bucket_idx + 1) * bucket_size)
        distribution.append({
            "range": f"{range_start}-{range_end}",
            "range_start": range_start,
            "range_end": range_end,
            "count": row.count,
        })

    # --- Per-product breakdown ---
    product_stmt = select(
        SupplyPlan.product_id,
        func.count(SupplyPlan.id).label("order_count"),
        func.avg(SupplyPlan.planned_order_quantity).label("avg_qty"),
        func.sum(SupplyPlan.planned_order_quantity).label("total_qty"),
        func.min(SupplyPlan.planned_order_quantity).label("min_qty"),
        func.max(SupplyPlan.planned_order_quantity).label("max_qty"),
        func.min(SupplyPlan.plan_date).label("first_order"),
        func.max(SupplyPlan.plan_date).label("last_order"),
    ).where(base_filter).group_by(SupplyPlan.product_id).order_by(
        func.sum(SupplyPlan.planned_order_quantity).desc()
    )
    product_result = await db.execute(product_stmt)
    product_rows = product_result.all()

    # Resolve product names
    product_ids = [r.product_id for r in product_rows]
    product_names = {}
    if product_ids:
        name_stmt = select(Product.id, Product.product_name).where(Product.id.in_(product_ids))
        name_result = await db.execute(name_stmt)
        product_names = {r.id: r.product_name for r in name_result.all()}

    by_product = []
    for row in product_rows:
        days_span = max(1, (row.last_order - row.first_order).days) if row.order_count > 1 else 0
        avg_days_between = round(days_span / max(1, row.order_count - 1), 1) if row.order_count > 1 else 0

        # Theoretical EOQ: sqrt(2*D*S/H) — use defaults if no cost data
        annual_demand = float(row.total_qty) * (365 / max(1, days_span)) if days_span > 0 else float(row.total_qty)
        ordering_cost = 500.0  # Default ordering cost
        holding_cost_rate = 0.25  # 25% of unit value per year
        unit_cost = 50.0  # Default unit cost
        holding_cost = holding_cost_rate * unit_cost
        eoq = round(math.sqrt(2 * annual_demand * ordering_cost / holding_cost), 0) if holding_cost > 0 else 0

        by_product.append({
            "product_id": row.product_id,
            "product_name": product_names.get(row.product_id, row.product_id),
            "order_count": row.order_count,
            "avg_qty": round(float(row.avg_qty), 0),
            "total_qty": round(float(row.total_qty), 0),
            "min_qty": round(float(row.min_qty), 0),
            "max_qty": round(float(row.max_qty), 0),
            "avg_days_between": avg_days_between,
            "eoq": eoq,
        })

    return {
        "summary": {
            "total_orders": total_orders,
            "avg_order_qty": round(float(summary.avg_order_qty), 0),
            "min_order_qty": round(float(summary.min_order_qty), 0),
            "max_order_qty": round(float(summary.max_order_qty), 0),
            "total_qty": round(float(summary.total_qty), 0),
            "orders_per_week": orders_per_week,
            "product_count": summary.product_count,
            "site_count": summary.site_count,
        },
        "distribution": distribution,
        "by_product": by_product,
    }


@router.post("/capacity-check/export/csv")
async def export_capacity_check_csv(
    request: CapacityCheckRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Export capacity check results as CSV
    
    Returns a CSV file with capacity utilization details by period and resource.
    """
    # Convert request resources to ResourceRequirement objects
    resources = [
        ResourceRequirement(
            resource_id=r.resource_id,
            resource_name=r.resource_name,
            units_per_product=r.units_per_product,
            available_capacity=r.available_capacity,
            utilization_target=r.utilization_target
        )
        for r in request.resources
    ]
    
    # Create MPS production plan
    mps_plan = MPSProductionPlan(
        product_id=request.product_id or 1,
        product_name=request.product_name or "Product",
        planned_quantities=request.production_plan.copy(),
        resource_requirements=resources
    )
    
    # Run capacity check
    rccp = CapacityConstrainedMPS(request.start_date, request.period_days)
    result = rccp.generate_feasible_plan(mps_plan, strategy=request.strategy)
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write summary
    writer.writerow(['Capacity Check Summary'])
    writer.writerow(['Feasible', 'Yes' if result.is_feasible else 'No'])
    writer.writerow(['Total Shortage', f"{result.total_shortage:.2f}"])
    writer.writerow(['Bottleneck Resources', ', '.join(result.bottleneck_resources)])
    writer.writerow([])
    
    # Write capacity details header
    writer.writerow([
        'Period',
        'Date',
        'Resource',
        'Required Capacity',
        'Available Capacity',
        'Utilization %',
        'Constrained',
        'Over Target',
        'Shortage'
    ])
    
    # Write capacity details
    for check in result.capacity_checks:
        writer.writerow([
            check.period + 1,  # 1-indexed for user display
            check.period_date.strftime('%Y-%m-%d'),
            check.resource_name,
            f"{check.required_capacity:.2f}",
            f"{check.available_capacity:.2f}",
            f"{check.utilization:.1f}",
            'Yes' if check.is_constrained else 'No',
            'Yes' if check.is_over_target else 'No',
            f"{check.shortage:.2f}"
        ])
    
    # Write production plan comparison
    writer.writerow([])
    writer.writerow(['Production Plan Comparison'])
    writer.writerow(['Period', 'Original Plan', 'Feasible Plan', 'Adjustment'])
    
    for i, (orig, feas) in enumerate(zip(result.original_plan, result.feasible_plan)):
        writer.writerow([
            i + 1,
            f"{orig:.2f}",
            f"{feas:.2f}",
            f"{orig - feas:.2f}"
        ])
    
    # Return as downloadable file
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=capacity_check_results.csv"}
    )

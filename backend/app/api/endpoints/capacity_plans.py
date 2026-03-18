"""
Capacity Planning API Endpoints

Manages capacity plans (RCCP) for resource utilization analysis and bottleneck identification.
Supports what-if scenarios and capacity requirement calculations.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.capacity_plan import (
    CapacityPlan,
    CapacityResource,
    CapacityRequirement,
    CapacityPlanStatus,
    ResourceType,
)
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.production_order import ProductionOrder
from app.models.mps import MPSPlan, MPSPlanItem
from app.schemas.capacity_plan import (
    CapacityPlanCreate,
    CapacityPlanUpdate,
    CapacityPlanResponse,
    CapacityPlanListResponse,
    CapacityPlanSummary,
    CapacityResourceCreate,
    CapacityResourceUpdate,
    CapacityResourceResponse,
    CapacityRequirementCreate,
    CapacityRequirementUpdate,
    CapacityRequirementResponse,
    CalculateCapacityRequest,
    CapacityAnalysisResponse,
    BottleneckResource,
)

router = APIRouter()


# ============================================================================
# Helper Functions
# ============================================================================

def _get_capacity_plan_or_404(
    db: Session,
    plan_id: int,
    user: User,
) -> CapacityPlan:
    """Get capacity plan by ID or raise 404."""
    plan = db.query(CapacityPlan).filter(
        CapacityPlan.id == plan_id,
        CapacityPlan.is_deleted == False
    ).options(
        joinedload(CapacityPlan.supply_chain_config),
        joinedload(CapacityPlan.resources),
        joinedload(CapacityPlan.requirements)
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Capacity plan not found")

    return plan


def _calculate_requirements_from_mps(
    db: Session,
    plan: CapacityPlan,
    mps_plan_id: Optional[int] = None
) -> List[CapacityRequirement]:
    """Calculate capacity requirements from MPS plan."""
    # This is a simplified implementation - real logic would:
    # 1. Get MPS plan items
    # 2. For each item, determine required resources (from routing/BOM)
    # 3. Calculate time-phased requirements
    # 4. Create CapacityRequirement records

    requirements = []

    # Query MPS plans
    mps_query = db.query(MPSPlan).filter(
        MPSPlan.supply_chain_config_id == plan.supply_chain_config_id
    )
    if mps_plan_id:
        mps_query = mps_query.filter(MPSPlan.id == mps_plan_id)

    mps_plans = mps_query.all()

    # Load Bill of Resources for real hours-per-unit lookups
    from app.models.rccp import BillOfResources
    bor_entries = db.query(BillOfResources).filter(
        BillOfResources.config_id == plan.supply_chain_config_id,
        BillOfResources.is_active == True,
    ).all()
    # Build (product_id, resource_id) -> effective_hours map
    bor_map = {}
    bor_cpof = {}  # product_id -> overall_hours for CPOF fallback
    for bor in bor_entries:
        if bor.resource_id is not None and bor.hours_per_unit is not None:
            bor_map[(bor.product_id, bor.resource_id)] = bor.effective_hours_per_unit
        if bor.overall_hours_per_unit is not None:
            bor_cpof[bor.product_id] = bor.overall_hours_per_unit

    # Load MPS items for quantity data
    mps_items = []
    if mps_plan_id:
        mps_items = db.query(MPSPlanItem).filter(MPSPlanItem.plan_id == mps_plan_id).all()

    # For each resource in the capacity plan
    for resource in plan.resources:
        period_start = plan.start_date
        period_number = 1

        while period_start < plan.end_date:
            period_end = period_start + timedelta(days=plan.bucket_size_days)

            # Calculate required capacity from MPS items + BoR
            required = 0.0
            for item in mps_items:
                item_date = getattr(item, 'period_start', None)
                if item_date and not (period_start <= item_date < period_end):
                    continue
                qty = getattr(item, 'planned_quantity', 0) or getattr(item, 'quantity', 0) or 0
                # Look up BoR: per-resource first, then CPOF fallback
                hours = bor_map.get((item.product_id, resource.id), 0.0)
                if hours == 0.0:
                    hours = bor_cpof.get(item.product_id, 0.0)
                    if hours > 0 and len(plan.resources) > 1:
                        hours /= len(plan.resources)
                required += qty * hours

            req = CapacityRequirement(
                plan_id=plan.id,
                resource_id=resource.id,
                period_start=period_start,
                period_end=period_end,
                period_number=period_number,
                required_capacity=required,
                available_capacity=resource.effective_capacity,
                source_type="MPS",
                source_id=mps_plan_id
            )
            req.calculate_utilization()
            requirements.append(req)

            period_start = period_end
            period_number += 1

    return requirements


def _calculate_requirements_from_production_orders(
    db: Session,
    plan: CapacityPlan,
    order_ids: Optional[List[int]] = None
) -> List[CapacityRequirement]:
    """Calculate capacity requirements from production orders."""
    requirements = []

    # Query production orders
    orders_query = db.query(ProductionOrder).filter(
        ProductionOrder.config_id == plan.supply_chain_config_id,
        ProductionOrder.status.in_(["PLANNED", "RELEASED", "IN_PROGRESS"]),
        ProductionOrder.is_deleted == False
    )
    if order_ids:
        orders_query = orders_query.filter(ProductionOrder.id.in_(order_ids))

    orders = orders_query.all()

    # For each resource, aggregate requirements from orders
    for resource in plan.resources:
        # Group orders by time period
        period_start = plan.start_date
        period_number = 1

        while period_start < plan.end_date:
            period_end = period_start + timedelta(days=plan.bucket_size_days)

            # Find orders that overlap this period
            period_orders = [
                o for o in orders
                if o.site_id == resource.site_id
                and o.planned_start_date < period_end
                and o.planned_completion_date > period_start
            ]

            # Calculate required capacity from BoR
            from app.models.rccp import BillOfResources
            required = 0.0
            for o in period_orders:
                bor = db.query(BillOfResources).filter(
                    BillOfResources.config_id == plan.supply_chain_config_id,
                    BillOfResources.product_id == o.product_id,
                    BillOfResources.site_id == o.site_id,
                    BillOfResources.resource_id == resource.id,
                    BillOfResources.is_active == True,
                ).first()
                if bor:
                    required += o.planned_quantity * bor.effective_hours_per_unit
                else:
                    # CPOF fallback
                    bor_cpof = db.query(BillOfResources).filter(
                        BillOfResources.config_id == plan.supply_chain_config_id,
                        BillOfResources.product_id == o.product_id,
                        BillOfResources.site_id == o.site_id,
                        BillOfResources.resource_id == None,
                        BillOfResources.is_active == True,
                    ).first()
                    if bor_cpof and bor_cpof.overall_hours_per_unit:
                        hours = bor_cpof.overall_hours_per_unit
                        if len(plan.resources) > 1:
                            hours /= len(plan.resources)
                        required += o.planned_quantity * hours

            req = CapacityRequirement(
                plan_id=plan.id,
                resource_id=resource.id,
                period_start=period_start,
                period_end=period_end,
                period_number=period_number,
                required_capacity=required,
                available_capacity=resource.effective_capacity,
                source_type="PRODUCTION_ORDER",
                requirement_breakdown={o.order_number: o.planned_quantity for o in period_orders}
            )
            req.calculate_utilization()
            requirements.append(req)

            period_start = period_end
            period_number += 1

    return requirements


# ============================================================================
# Capacity Plan CRUD Endpoints
# ============================================================================

@router.get("/", response_model=CapacityPlanListResponse)
async def list_capacity_plans(
    status: Optional[str] = Query(None, description="Filter by status"),
    config_id: Optional[int] = Query(None, description="Filter by supply chain config ID"),
    is_scenario: Optional[bool] = Query(None, description="Filter scenarios"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List capacity plans with filtering and pagination.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Build query
    query = db.query(CapacityPlan).filter(CapacityPlan.is_deleted == False)

    # Apply filters
    if status:
        query = query.filter(CapacityPlan.status == status)
    if config_id:
        query = query.filter(CapacityPlan.supply_chain_config_id == config_id)
    if is_scenario is not None:
        query = query.filter(CapacityPlan.is_scenario == is_scenario)

    # Count total
    total = query.count()

    # Apply pagination and eager load relationships
    plans = query.options(
        joinedload(CapacityPlan.supply_chain_config)
    ).order_by(
        CapacityPlan.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    return CapacityPlanListResponse(
        items=plans,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/summary", response_model=CapacityPlanSummary)
async def get_capacity_plan_summary(
    config_id: Optional[int] = Query(None, description="Filter by supply chain config ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary statistics for capacity plans.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Base query
    base_query = db.query(CapacityPlan).filter(CapacityPlan.is_deleted == False)
    if config_id:
        base_query = base_query.filter(CapacityPlan.supply_chain_config_id == config_id)

    total_plans = base_query.count()
    active_plans = base_query.filter(CapacityPlan.status == CapacityPlanStatus.ACTIVE).count()
    scenario_plans = base_query.filter(CapacityPlan.is_scenario == True).count()

    # Average utilization
    avg_util = db.query(func.avg(CapacityPlan.avg_utilization_percent)).filter(
        CapacityPlan.id.in_(base_query.with_entities(CapacityPlan.id)),
        CapacityPlan.avg_utilization_percent.isnot(None)
    ).scalar() or 0.0

    # Feasibility counts
    feasible_plans = base_query.filter(CapacityPlan.overloaded_resources == 0).count()
    infeasible_plans = base_query.filter(CapacityPlan.overloaded_resources > 0).count()
    plans_with_bottlenecks = base_query.filter(CapacityPlan.bottleneck_identified == True).count()

    return CapacityPlanSummary(
        total_plans=total_plans,
        active_plans=active_plans,
        scenario_plans=scenario_plans,
        avg_utilization=float(avg_util),
        feasible_plans=feasible_plans,
        infeasible_plans=infeasible_plans,
        plans_with_bottlenecks=plans_with_bottlenecks
    )


@router.get("/{plan_id}", response_model=CapacityPlanResponse)
async def get_capacity_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get capacity plan by ID.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)
    return plan


@router.post("/", response_model=CapacityPlanResponse, status_code=201)
async def create_capacity_plan(
    plan_data: CapacityPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new capacity plan.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    # Resolve config: explicit or tenant's active baseline
    effective_config_id = plan_data.supply_chain_config_id
    if effective_config_id is None:
        from app.api.deps import get_active_baseline_config
        effective_config_id = get_active_baseline_config(db, current_user.tenant_id).id

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == effective_config_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Supply chain config not found")

    # Validate base plan exists if provided
    if plan_data.base_plan_id:
        base_plan = db.query(CapacityPlan).filter(
            CapacityPlan.id == plan_data.base_plan_id
        ).first()
        if not base_plan:
            raise HTTPException(status_code=404, detail="Base plan not found")

    # Create capacity plan
    plan = CapacityPlan(
        name=plan_data.name,
        description=plan_data.description,
        supply_chain_config_id=effective_config_id,
        planning_horizon_weeks=plan_data.planning_horizon_weeks,
        bucket_size_days=plan_data.bucket_size_days,
        start_date=plan_data.start_date,
        end_date=plan_data.end_date,
        is_scenario=plan_data.is_scenario,
        scenario_description=plan_data.scenario_description,
        base_plan_id=plan_data.base_plan_id,
        status=CapacityPlanStatus.DRAFT,
        created_by=current_user.id,
        updated_by=current_user.id
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan


@router.put("/{plan_id}", response_model=CapacityPlanResponse)
async def update_capacity_plan(
    plan_id: int,
    plan_data: CapacityPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a capacity plan.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Update fields
    update_data = plan_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(plan, field):
            setattr(plan, field, value)

    plan.updated_by = current_user.id
    plan.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(plan)

    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_capacity_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete a capacity plan.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    plan.is_deleted = True
    plan.updated_by = current_user.id
    plan.updated_at = datetime.utcnow()

    db.commit()

    return None


# ============================================================================
# Capacity Resource Endpoints
# ============================================================================

@router.get("/{plan_id}/resources", response_model=List[CapacityResourceResponse])
async def list_capacity_resources(
    plan_id: int,
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List capacity resources for a plan.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Build query
    query = db.query(CapacityResource).filter(
        CapacityResource.plan_id == plan_id
    )

    if site_id:
        query = query.filter(CapacityResource.site_id == site_id)
    if resource_type:
        query = query.filter(CapacityResource.resource_type == resource_type)

    resources = query.options(joinedload(CapacityResource.site)).all()
    return resources


@router.post("/{plan_id}/resources", response_model=CapacityResourceResponse, status_code=201)
async def create_capacity_resource(
    plan_id: int,
    resource_data: CapacityResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new capacity resource.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Verify site exists
    site = db.query(Site).filter(Site.id == resource_data.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Create resource
    resource = CapacityResource(
        plan_id=plan_id,
        resource_name=resource_data.resource_name,
        resource_code=resource_data.resource_code,
        resource_type=ResourceType(resource_data.resource_type),
        site_id=resource_data.site_id,
        available_capacity=resource_data.available_capacity,
        capacity_unit=resource_data.capacity_unit,
        efficiency_percent=resource_data.efficiency_percent,
        utilization_target_percent=resource_data.utilization_target_percent,
        cost_per_hour=resource_data.cost_per_hour,
        setup_time_hours=resource_data.setup_time_hours,
        shifts_per_day=resource_data.shifts_per_day,
        hours_per_shift=resource_data.hours_per_shift,
        working_days_per_week=resource_data.working_days_per_week,
        notes=resource_data.notes
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    return resource


@router.put("/resources/{resource_id}", response_model=CapacityResourceResponse)
async def update_capacity_resource(
    resource_id: int,
    resource_data: CapacityResourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a capacity resource.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    resource = db.query(CapacityResource).filter(
        CapacityResource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Update fields
    update_data = resource_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(resource, field) and field != 'resource_type':
            setattr(resource, field, value)
        elif field == 'resource_type' and value:
            resource.resource_type = ResourceType(value)

    resource.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(resource)

    return resource


@router.delete("/resources/{resource_id}", status_code=204)
async def delete_capacity_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a capacity resource.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    resource = db.query(CapacityResource).filter(
        CapacityResource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    db.delete(resource)
    db.commit()

    return None


# ============================================================================
# Capacity Requirement Endpoints
# ============================================================================

@router.get("/{plan_id}/requirements", response_model=List[CapacityRequirementResponse])
async def list_capacity_requirements(
    plan_id: int,
    resource_id: Optional[int] = Query(None, description="Filter by resource ID"),
    overloaded_only: bool = Query(False, description="Show only overloaded periods"),
    bottleneck_only: bool = Query(False, description="Show only bottleneck periods"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List capacity requirements for a plan.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Build query
    query = db.query(CapacityRequirement).filter(
        CapacityRequirement.plan_id == plan_id
    )

    if resource_id:
        query = query.filter(CapacityRequirement.resource_id == resource_id)
    if overloaded_only:
        query = query.filter(CapacityRequirement.is_overloaded == True)
    if bottleneck_only:
        query = query.filter(CapacityRequirement.is_bottleneck == True)

    requirements = query.options(
        joinedload(CapacityRequirement.resource)
    ).order_by(
        CapacityRequirement.period_start
    ).all()

    return requirements


@router.post("/{plan_id}/calculate", response_model=Dict[str, Any])
async def calculate_capacity_requirements(
    plan_id: int,
    calc_request: CalculateCapacityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate capacity requirements for a plan.

    Requires: MANAGE_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Delete existing requirements if recalculating
    if calc_request.recalculate:
        db.query(CapacityRequirement).filter(
            CapacityRequirement.plan_id == plan_id
        ).delete()

    # Calculate requirements based on source type
    requirements = []
    if calc_request.source_type == "MPS":
        source_id = calc_request.source_ids[0] if calc_request.source_ids else None
        requirements = _calculate_requirements_from_mps(db, plan, source_id)
    elif calc_request.source_type == "PRODUCTION_ORDER":
        requirements = _calculate_requirements_from_production_orders(db, plan, calc_request.source_ids)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source type: {calc_request.source_type}")

    # Save requirements
    for req in requirements:
        db.add(req)

    # Update plan summary metrics
    plan.calculate_summary_metrics()

    db.commit()

    return {
        "message": "Capacity requirements calculated successfully",
        "requirements_created": len(requirements),
        "is_feasible": plan.is_feasible,
        "overloaded_resources": plan.overloaded_resources
    }


@router.get("/{plan_id}/analysis", response_model=CapacityAnalysisResponse)
async def analyze_capacity_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform capacity analysis on a plan.

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Get all requirements
    requirements = db.query(CapacityRequirement).filter(
        CapacityRequirement.plan_id == plan_id
    ).options(joinedload(CapacityRequirement.resource)).all()

    if not requirements:
        raise HTTPException(status_code=400, detail="No requirements found. Calculate requirements first.")

    # Analyze bottlenecks
    bottleneck_resources = []
    resource_utilization = {}

    for resource in plan.resources:
        resource_reqs = [r for r in requirements if r.resource_id == resource.id]
        if not resource_reqs:
            continue

        max_util = max(r.utilization_percent for r in resource_reqs)
        avg_util = sum(r.utilization_percent for r in resource_reqs) / len(resource_reqs)
        overloaded_periods = sum(1 for r in resource_reqs if r.is_overloaded)

        resource_utilization[resource.resource_name] = avg_util

        if max_util >= 95.0:
            bottleneck_resources.append({
                "resource_id": resource.id,
                "resource_name": resource.resource_name,
                "site_id": resource.site_id,
                "site_name": resource.site.name if resource.site else "Unknown",
                "max_utilization_percent": max_util,
                "overloaded_periods": overloaded_periods,
                "avg_utilization_percent": avg_util
            })

    # Utilization by period
    utilization_by_period = []
    periods = sorted(set(r.period_number for r in requirements))

    for period_num in periods:
        period_reqs = [r for r in requirements if r.period_number == period_num]
        avg_util = sum(r.utilization_percent for r in period_reqs) / len(period_reqs)
        overloaded = sum(1 for r in period_reqs if r.is_overloaded)

        utilization_by_period.append({
            "period_number": period_num,
            "period_start": period_reqs[0].period_start.isoformat(),
            "avg_utilization": avg_util,
            "overloaded_resources": overloaded
        })

    # Generate recommendations
    recommendations = []
    if plan.overloaded_resources > 0:
        recommendations.append(f"Plan has {plan.overloaded_resources} overloaded resources. Consider adding capacity or adjusting production schedule.")
    if len(bottleneck_resources) > 0:
        recommendations.append(f"Identified {len(bottleneck_resources)} bottleneck resources with >95% utilization.")
    if plan.avg_utilization_percent < 60:
        recommendations.append("Average utilization is below 60%. Consider consolidating resources or increasing production.")

    return CapacityAnalysisResponse(
        plan_id=plan_id,
        is_feasible=plan.is_feasible,
        total_periods=len(periods),
        overloaded_periods=sum(1 for p in utilization_by_period if p["overloaded_resources"] > 0),
        bottleneck_resources=bottleneck_resources,
        utilization_by_resource=resource_utilization,
        utilization_by_period=utilization_by_period,
        recommendations=recommendations
    )


@router.get("/{plan_id}/bottlenecks", response_model=List[BottleneckResource])
async def get_bottleneck_resources(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get bottleneck resources for a plan (>95% utilization).

    Requires: VIEW_CAPACITY_PLANNING capability
    """
    # Verify plan exists
    plan = _get_capacity_plan_or_404(db, plan_id, current_user)

    # Get requirements with bottlenecks
    requirements = db.query(CapacityRequirement).filter(
        CapacityRequirement.plan_id == plan_id,
        CapacityRequirement.is_bottleneck == True
    ).options(joinedload(CapacityRequirement.resource)).all()

    # Group by resource
    bottlenecks = {}
    for req in requirements:
        if req.resource_id not in bottlenecks:
            bottlenecks[req.resource_id] = {
                "resource_id": req.resource_id,
                "resource_name": req.resource.resource_name,
                "site_id": req.resource.site_id,
                "site_name": req.resource.site.name if req.resource.site else "Unknown",
                "max_utilization_percent": req.utilization_percent,
                "overloaded_periods": 0,
                "avg_utilization_percent": req.utilization_percent,
                "count": 1
            }
        else:
            bottlenecks[req.resource_id]["max_utilization_percent"] = max(
                bottlenecks[req.resource_id]["max_utilization_percent"],
                req.utilization_percent
            )
            bottlenecks[req.resource_id]["avg_utilization_percent"] += req.utilization_percent
            bottlenecks[req.resource_id]["count"] += 1
            if req.is_overloaded:
                bottlenecks[req.resource_id]["overloaded_periods"] += 1

    # Calculate averages
    result = []
    for resource_id, data in bottlenecks.items():
        data["avg_utilization_percent"] /= data["count"]
        del data["count"]
        result.append(BottleneckResource(**data))

    return result

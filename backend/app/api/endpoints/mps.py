"""
Master Production Scheduling (MPS) API Endpoints

Provides CRUD operations and workflow management for MPS plans.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.core.capabilities import Capability
from app.services.capability_service import user_has_capability
from app.models.mps import MPSPlan, MPSPlanItem, MPSCapacityCheck, MPSStatus, MPSKeyMaterialRequirement
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.production_order import ProductionOrder
from app.models.sc_entities import Product, SourcingRules
from app.models.supplier import VendorLeadTime
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from pydantic import BaseModel, Field
import sqlalchemy as sa


# ============================================================================
# Request/Response Schemas
# ============================================================================

class MPSPlanCreate(BaseModel):
    """Request schema for creating a new MPS plan"""
    config_id: Optional[int] = Field(None, description="Supply chain config ID. If omitted, uses tenant's active baseline.")
    name: Optional[str] = Field(None, description="Plan name")
    description: Optional[str] = Field(None, description="Plan description")
    planning_horizon: int = Field(52, description="Planning horizon in weeks", ge=1, le=104)
    bucket_size_days: int = Field(7, description="Time bucket size in days", ge=1, le=30)
    user_id: Optional[int] = Field(None, description="User ID (deprecated, use current_user)")


class MPSPlanUpdate(BaseModel):
    """Request schema for updating an MPS plan"""
    name: Optional[str] = None
    description: Optional[str] = None
    planning_horizon_weeks: Optional[int] = Field(None, ge=1, le=104)
    bucket_size_days: Optional[int] = Field(None, ge=1, le=30)


class MPSPlanResponse(BaseModel):
    """Response schema for MPS plan"""
    id: int
    name: str
    description: Optional[str]
    supply_chain_config_id: int
    config_name: Optional[str]
    planning_horizon_weeks: int
    planning_horizon: int  # Alias for frontend compatibility
    bucket_size_days: int
    start_date: datetime
    end_date: datetime
    status: str
    created_by: Optional[int]
    created_by_name: Optional[str]
    approved_by: Optional[int]
    approved_by_name: Optional[str]
    approved_at: Optional[datetime]
    execution_started_at: Optional[datetime]
    execution_completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MPSPlanItemCreate(BaseModel):
    """Request schema for creating MPS plan item"""
    product_id: int
    site_id: int
    weekly_quantities: List[float] = Field(default_factory=list)
    lot_size_rule: Optional[str] = None
    lot_size_value: Optional[float] = None


class MPSPlanItemResponse(BaseModel):
    """Response schema for MPS plan item"""
    id: int
    plan_id: int
    product_id: int
    site_id: int
    weekly_quantities: List[float]
    lot_size_rule: Optional[str]
    lot_size_value: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MPSCapacityCheckResponse(BaseModel):
    """Response schema for capacity check"""
    id: int
    plan_id: int
    resource_name: str
    site_id: int
    period_start: datetime
    period_end: datetime
    required_capacity: float
    available_capacity: float
    utilization_percent: float
    is_overloaded: bool
    overload_amount: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class ProductionOrderSummary(BaseModel):
    """Summary of generated production orders"""
    order_id: int
    order_number: str
    product_id: int
    product_name: str
    site_id: int
    site_name: str
    quantity: float
    planned_start_date: datetime
    planned_completion_date: datetime
    status: str


class GenerateProductionOrdersResponse(BaseModel):
    """Response schema for production order generation"""
    plan_id: int
    plan_name: str
    total_orders_created: int
    orders: List[ProductionOrderSummary]
    start_date: datetime
    end_date: datetime


class MPSKeyMaterialResponse(BaseModel):
    """Response schema for key material requirement"""
    id: int
    plan_id: int
    mps_item_id: int
    parent_product_id: int
    parent_product_name: str
    key_material_product_id: int
    key_material_product_name: str
    key_material_site_id: int
    key_material_site_name: str
    bom_level: int
    component_quantity: float
    scrap_percentage: float
    weekly_gross_requirements: List[float]
    total_gross_requirement: float
    is_bottleneck: bool
    is_long_lead_time: bool
    is_strategic: bool
    procurement_lead_time_days: Optional[int]

    class Config:
        from_attributes = True


class ExplodeKeyMaterialsResponse(BaseModel):
    """Response schema for key material explosion"""
    plan_id: int
    plan_name: str
    total_key_materials: int
    key_materials: List[MPSKeyMaterialResponse]


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/mps", tags=["Master Production Scheduling"])


# ============================================================================
# Helper Functions
# ============================================================================

def check_mps_permission(user: User, action: str, db: Session = None) -> None:
    """Check if user has permission for MPS action"""
    required_capabilities = {
        "view": Capability.VIEW_MPS,
        "manage": Capability.MANAGE_MPS,
        "approve": Capability.APPROVE_MPS,
    }

    capability = required_capabilities.get(action)
    if not capability:
        return

    if db is None or not user_has_capability(user, capability, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have permission to {action} MPS plans"
        )


def get_mps_plan_or_404(db: Session, plan_id: int) -> MPSPlan:
    """Get MPS plan by ID or raise 404"""
    plan = db.get(MPSPlan, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MPS plan with id {plan_id} not found"
        )
    return plan


def format_mps_plan_response(plan: MPSPlan, db: Session) -> dict:
    """Format MPS plan for API response"""
    # Get config name
    config = db.get(SupplyChainConfig, plan.supply_chain_config_id)
    config_name = config.name if config else None

    # Get creator name
    created_by_name = None
    if plan.created_by:
        creator = db.get(User, plan.created_by)
        if creator:
            created_by_name = creator.full_name or creator.username or creator.email

    # Get approver name
    approved_by_name = None
    if plan.approved_by:
        approver = db.get(User, plan.approved_by)
        if approver:
            approved_by_name = approver.full_name or approver.username or approver.email

    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "supply_chain_config_id": plan.supply_chain_config_id,
        "config_name": config_name,
        "planning_horizon_weeks": plan.planning_horizon_weeks,
        "planning_horizon": plan.planning_horizon_weeks,  # Alias for frontend
        "bucket_size_days": plan.bucket_size_days,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "status": plan.status.value if isinstance(plan.status, MPSStatus) else plan.status,
        "created_by": plan.created_by,
        "created_by_name": created_by_name,
        "approved_by": plan.approved_by,
        "approved_by_name": approved_by_name,
        "approved_at": plan.approved_at,
        "execution_started_at": plan.execution_started_at,
        "execution_completed_at": plan.execution_completed_at,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def explode_key_materials_for_mps(
    db: Session,
    plan: MPSPlan,
    mps_item: MPSPlanItem,
    current_level: int = 1,
    max_levels: int = 10
) -> List[MPSKeyMaterialRequirement]:
    """
    Perform BOM explosion for key materials only (rough-cut planning).

    This function recursively explodes the BOM for a finished good (MPS item)
    but only tracks components flagged as key materials (is_key_material = 'true').

    Key materials are critical components that require planning at the MPS level:
    - Long lead time items (>4 weeks)
    - Bottleneck/constrained resources
    - High-value components
    - Strategic materials with limited suppliers

    Args:
        db: Database session
        plan: MPS plan
        mps_item: MPS plan item (finished good)
        current_level: Current BOM level (1 = direct child, 2 = grandchild, etc.)
        max_levels: Maximum BOM levels to explode (safety limit)

    Returns:
        List of MPSKeyMaterialRequirement objects (not yet committed to DB)
    """
    key_material_requirements = []

    if current_level > max_levels:
        return key_material_requirements

    # Query BOM for this product using raw SQL to avoid model import conflicts
    bom_query = sa.text("""
        SELECT component_product_id, component_quantity, scrap_percentage, is_key_material
        FROM product_bom
        WHERE product_id = :product_id
    """)
    bom_entries = db.execute(bom_query, {"product_id": str(mps_item.product_id)}).fetchall()

    for bom_entry in bom_entries:
        component_id = bom_entry[0]  # component_product_id
        component_qty = bom_entry[1]  # component_quantity
        scrap_pct = bom_entry[2] or 0.0  # scrap_percentage
        is_key_material_flag = bom_entry[3]  # is_key_material

        # Calculate time-phased gross requirements
        # Formula: MPS quantity × component quantity × (1 + scrap_percentage/100)
        scrap_multiplier = 1.0 + (scrap_pct / 100.0)
        weekly_gross_reqs = [
            float(mps_qty * component_qty * scrap_multiplier)
            for mps_qty in mps_item.weekly_quantities
        ]
        total_gross_req = sum(weekly_gross_reqs)

        # Check if this component is a key material
        is_key_material = is_key_material_flag == 'true'

        if is_key_material:
            # Get component product details
            component_product = db.get(Item, component_id)
            if not component_product:
                continue

            # Determine key material classification flags
            # Query vendor lead time to check for long lead time
            vendor_lead_time = db.execute(
                select(VendorLeadTime).where(
                    VendorLeadTime.product_id == component_id
                )
            ).scalars().first()

            procurement_lt_days = None
            is_long_lead_time = False
            if vendor_lead_time:
                procurement_lt_days = vendor_lead_time.lead_time_days
                is_long_lead_time = (procurement_lt_days or 0) > 28  # >4 weeks

            # Bottleneck: component has single-source or constrained capacity
            is_bottleneck = False
            component_sources = db.query(SourcingRules).filter(
                SourcingRules.product_id == component_id,
            ).count()
            if component_sources <= 1:
                is_bottleneck = True  # Single-sourced = bottleneck risk

            # Strategic: long lead time OR single-sourced high-value component
            is_strategic = is_long_lead_time or (is_bottleneck and total_gross_req > 0)

            # Create key material requirement record
            key_mat_req = MPSKeyMaterialRequirement(
                plan_id=plan.id,
                mps_item_id=mps_item.id,
                parent_product_id=mps_item.product_id,
                key_material_product_id=component_id,
                key_material_site_id=mps_item.site_id,  # Assume same site for now
                bom_level=current_level,
                component_quantity=component_qty,
                scrap_percentage=scrap_pct,
                weekly_gross_requirements=weekly_gross_reqs,
                total_gross_requirement=total_gross_req,
                is_bottleneck=is_bottleneck,
                is_long_lead_time=is_long_lead_time,
                is_strategic=is_strategic,
                procurement_lead_time_days=procurement_lt_days,
            )

            key_material_requirements.append(key_mat_req)

        # Recursively explode child components (both key and non-key)
        # This ensures we find key materials at all BOM levels
        # Create a temporary MPSPlanItem-like object for recursion
        class TempMPSItem:
            def __init__(self, product_id, site_id, weekly_quantities):
                self.id = mps_item.id
                self.product_id = product_id
                self.site_id = site_id
                self.weekly_quantities = weekly_quantities

        child_mps_item = TempMPSItem(
            product_id=component_id,
            site_id=mps_item.site_id,
            weekly_quantities=weekly_gross_reqs
        )

        child_key_materials = explode_key_materials_for_mps(
            db=db,
            plan=plan,
            mps_item=child_mps_item,
            current_level=current_level + 1,
            max_levels=max_levels
        )

        key_material_requirements.extend(child_key_materials)

    return key_material_requirements


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/plans", response_model=List[MPSPlanResponse])
async def list_mps_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = None,
    config_id: Optional[int] = None,
) -> List[dict]:
    """
    List all MPS plans.

    Optional filters:
    - status_filter: Filter by plan status
    - config_id: Filter by supply chain configuration
    """
    check_mps_permission(current_user, "view", db)

    # Build query
    query = select(MPSPlan)

    if status_filter:
        try:
            status_enum = MPSStatus(status_filter)
            query = query.where(MPSPlan.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )

    if config_id:
        query = query.where(MPSPlan.supply_chain_config_id == config_id)

    # Order by most recent first
    query = query.order_by(MPSPlan.created_at.desc())

    plans = db.execute(query).scalars().all()

    # Format response
    return [format_mps_plan_response(plan, db) for plan in plans]


@router.post("/plans", response_model=MPSPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_mps_plan(
    plan_data: MPSPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Create a new MPS plan.

    Initializes a draft MPS plan for the specified supply chain configuration.
    """
    check_mps_permission(current_user, "manage", db)

    # Resolve config: explicit or tenant's active baseline
    effective_config_id = plan_data.config_id
    if effective_config_id is None:
        from app.api.deps import get_active_baseline_config
        effective_config_id = get_active_baseline_config(db, current_user.tenant_id).id

    config = db.get(SupplyChainConfig, effective_config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply chain config with id {effective_config_id} not found"
        )

    # Calculate dates
    start_date = datetime.now()
    end_date = start_date + timedelta(weeks=plan_data.planning_horizon)

    # Generate name if not provided
    if not plan_data.name:
        plan_count = db.execute(
            select(MPSPlan).where(MPSPlan.supply_chain_config_id == effective_config_id)
        ).scalars().all()
        plan_data.name = f"MPS Plan {len(plan_count) + 1} - {config.name}"

    # Create plan
    new_plan = MPSPlan(
        name=plan_data.name,
        description=plan_data.description,
        supply_chain_config_id=effective_config_id,
        planning_horizon_weeks=plan_data.planning_horizon,
        bucket_size_days=plan_data.bucket_size_days,
        start_date=start_date,
        end_date=end_date,
        status=MPSStatus.DRAFT,
        created_by=current_user.id,
    )

    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)

    return format_mps_plan_response(new_plan, db)


@router.get("/plans/{plan_id}", response_model=MPSPlanResponse)
async def get_mps_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get a specific MPS plan by ID"""
    check_mps_permission(current_user, "view", db)

    plan = get_mps_plan_or_404(db, plan_id)
    return format_mps_plan_response(plan, db)


@router.put("/plans/{plan_id}", response_model=MPSPlanResponse)
async def update_mps_plan(
    plan_id: int,
    plan_data: MPSPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Update an MPS plan.

    Only DRAFT plans can be modified.
    """
    check_mps_permission(current_user, "manage", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Only draft plans can be edited
    if plan.status != MPSStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DRAFT plans can be modified"
        )

    # Update fields
    if plan_data.name is not None:
        plan.name = plan_data.name
    if plan_data.description is not None:
        plan.description = plan_data.description
    if plan_data.planning_horizon_weeks is not None:
        plan.planning_horizon_weeks = plan_data.planning_horizon_weeks
        # Recalculate end date
        plan.end_date = plan.start_date + timedelta(weeks=plan_data.planning_horizon_weeks)
    if plan_data.bucket_size_days is not None:
        plan.bucket_size_days = plan_data.bucket_size_days

    plan.updated_at = datetime.now()

    db.commit()
    db.refresh(plan)

    return format_mps_plan_response(plan, db)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mps_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete an MPS plan.

    Only DRAFT plans can be deleted.
    """
    check_mps_permission(current_user, "manage", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Only draft plans can be deleted
    if plan.status != MPSStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DRAFT plans can be deleted"
        )

    db.delete(plan)
    db.commit()


@router.post("/plans/{plan_id}/approve", response_model=MPSPlanResponse)
async def approve_mps_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Approve an MPS plan for execution.

    Changes status from PENDING_APPROVAL to APPROVED.
    """
    check_mps_permission(current_user, "approve", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Can approve DRAFT or PENDING_APPROVAL plans
    if plan.status not in [MPSStatus.DRAFT, MPSStatus.PENDING_APPROVAL]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve plan with status {plan.status.value}"
        )

    # Update status
    plan.status = MPSStatus.APPROVED
    plan.approved_by = current_user.id
    plan.approved_at = datetime.now()
    plan.updated_at = datetime.now()

    db.commit()
    db.refresh(plan)

    return format_mps_plan_response(plan, db)


@router.post("/plans/{plan_id}/cancel", response_model=MPSPlanResponse)
async def cancel_mps_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Cancel an MPS plan.

    Can cancel plans that are not yet completed.
    """
    check_mps_permission(current_user, "manage", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Cannot cancel completed plans
    if plan.status == MPSStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel completed plans"
        )

    # Update status
    plan.status = MPSStatus.CANCELLED
    plan.updated_at = datetime.now()

    db.commit()
    db.refresh(plan)

    return format_mps_plan_response(plan, db)


@router.post("/plans/{plan_id}/execute", response_model=MPSPlanResponse)
async def execute_mps_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Start execution of an approved MPS plan.

    Changes status from APPROVED to IN_EXECUTION.
    """
    check_mps_permission(current_user, "manage", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Can only execute approved plans
    if plan.status != MPSStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only execute APPROVED plans, current status: {plan.status.value}"
        )

    # Update status
    plan.status = MPSStatus.IN_EXECUTION
    plan.execution_started_at = datetime.now()
    plan.updated_at = datetime.now()

    db.commit()
    db.refresh(plan)

    return format_mps_plan_response(plan, db)


@router.get("/plans/{plan_id}/items", response_model=List[MPSPlanItemResponse])
async def list_mps_plan_items(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MPSPlanItem]:
    """Get all items for an MPS plan"""
    check_mps_permission(current_user, "view", db)

    # Verify plan exists
    get_mps_plan_or_404(db, plan_id)

    items = db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == plan_id)
    ).scalars().all()

    return items


@router.post("/plans/{plan_id}/items", response_model=MPSPlanItemResponse, status_code=status.HTTP_201_CREATED)
async def create_mps_plan_item(
    plan_id: int,
    item_data: MPSPlanItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MPSPlanItem:
    """Add an item to an MPS plan"""
    check_mps_permission(current_user, "manage", db)

    plan = get_mps_plan_or_404(db, plan_id)

    # Only draft plans can be modified
    if plan.status != MPSStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DRAFT plans can be modified"
        )

    # Create item
    new_item = MPSPlanItem(
        plan_id=plan_id,
        product_id=item_data.product_id,
        site_id=item_data.site_id,
        weekly_quantities=item_data.weekly_quantities,
        lot_size_rule=item_data.lot_size_rule,
        lot_size_value=item_data.lot_size_value,
    )

    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    return new_item


@router.get("/plans/{plan_id}/capacity", response_model=List[MPSCapacityCheckResponse])
async def list_capacity_checks(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MPSCapacityCheck]:
    """Get capacity checks for an MPS plan"""
    check_mps_permission(current_user, "view", db)

    # Verify plan exists
    get_mps_plan_or_404(db, plan_id)

    checks = db.execute(
        select(MPSCapacityCheck).where(MPSCapacityCheck.plan_id == plan_id)
    ).scalars().all()

    return checks


@router.post("/plans/{plan_id}/generate-orders", response_model=GenerateProductionOrdersResponse)
async def generate_production_orders(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Generate production orders from an approved MPS plan.

    Automatically creates production orders for each period with non-zero quantities
    in the MPS plan. Orders are created in PLANNED status and linked to the MPS plan.

    Requirements:
    - MPS plan must be in APPROVED status
    - MPS plan must have items with quantities

    Returns:
    - Summary of created production orders
    """
    check_mps_permission(current_user, "manage", db)

    # Get MPS plan
    plan = get_mps_plan_or_404(db, plan_id)

    # Validate plan status
    if plan.status != MPSStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only generate orders from APPROVED plans. Current status: {plan.status.value}"
        )

    # Get plan items
    plan_items = db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == plan_id)
    ).scalars().all()

    if not plan_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPS plan has no items. Add items before generating orders."
        )

    # Generate production orders
    created_orders = []
    order_summaries = []

    for item in plan_items:
        # Get product and site details
        product = db.get(Item, item.product_id)
        site = db.get(Site, item.site_id)

        if not product or not site:
            continue

        # Create production orders for each period with non-zero quantity
        for period_idx, quantity in enumerate(item.weekly_quantities):
            if quantity <= 0:
                continue

            # Calculate dates for this period
            period_start = plan.start_date + timedelta(weeks=period_idx)
            period_end = period_start + timedelta(days=plan.bucket_size_days - 1)

            # Generate unique order number
            order_count = len(created_orders) + 1
            order_number = f"PO-{plan.id}-{item.product_id}-{item.site_id}-{period_idx + 1:03d}"

            # Create production order
            production_order = ProductionOrder(
                mps_plan_id=plan.id,
                item_id=item.product_id,
                site_id=item.site_id,
                config_id=plan.supply_chain_config_id,
                order_number=order_number,
                planned_quantity=int(quantity),
                status="PLANNED",
                planned_start_date=period_start,
                planned_completion_date=period_end,
                lead_time_planned=plan.bucket_size_days,
                priority=5,
                created_by_id=current_user.id,
            )

            db.add(production_order)
            created_orders.append(production_order)

            # Add to summary (will be populated after commit)
            order_summaries.append({
                "product_id": item.product_id,
                "product_name": product.name if product else f"Product {item.product_id}",
                "site_id": item.site_id,
                "site_name": site.name if site else f"Site {item.site_id}",
                "quantity": quantity,
                "planned_start_date": period_start,
                "planned_completion_date": period_end,
            })

    # Commit to database
    db.commit()

    # Refresh orders to get IDs
    for order in created_orders:
        db.refresh(order)

    # Build response with order IDs
    response_orders = []
    for order, summary in zip(created_orders, order_summaries):
        response_orders.append(ProductionOrderSummary(
            order_id=order.id,
            order_number=order.order_number,
            product_id=summary["product_id"],
            product_name=summary["product_name"],
            site_id=summary["site_id"],
            site_name=summary["site_name"],
            quantity=summary["quantity"],
            planned_start_date=summary["planned_start_date"],
            planned_completion_date=summary["planned_completion_date"],
            status=order.status,
        ))

    return GenerateProductionOrdersResponse(
        plan_id=plan.id,
        plan_name=plan.name,
        total_orders_created=len(created_orders),
        orders=response_orders,
        start_date=plan.start_date,
        end_date=plan.end_date,
    )


@router.post("/plans/{plan_id}/explode-key-materials", response_model=ExplodeKeyMaterialsResponse)
async def explode_key_materials(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Explode key materials for an MPS plan (rough-cut BOM explosion).

    This endpoint performs a BOM explosion for all MPS plan items, but only
    tracks components flagged as key materials (is_key_material = 'true' in product_bom).

    Key materials are critical components that require planning at the MPS level:
    - Long lead time items (>4 weeks)
    - Bottleneck/constrained resources
    - High-value components
    - Strategic materials with limited suppliers

    This is the industry-standard rough-cut planning approach:
    - MPS: Plans finished goods + key materials (strategic/rough-cut)
    - MRP: Plans all components (tactical/detailed)

    Requirements:
    - MPS plan must exist
    - MPS plan must have items with quantities
    - Product BOMs must be configured with is_key_material flags

    Returns:
    - Summary of key material requirements across all periods
    """
    check_mps_permission(current_user, "manage", db)

    # Get MPS plan
    plan = get_mps_plan_or_404(db, plan_id)

    # Get plan items
    plan_items = db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == plan_id)
    ).scalars().all()

    if not plan_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPS plan has no items. Add items before exploding key materials."
        )

    # Clear existing key material requirements for this plan
    db.execute(
        select(MPSKeyMaterialRequirement).where(
            MPSKeyMaterialRequirement.plan_id == plan_id
        )
    ).scalars().all()
    db.query(MPSKeyMaterialRequirement).filter(
        MPSKeyMaterialRequirement.plan_id == plan_id
    ).delete()

    # Explode key materials for each MPS plan item
    all_key_materials = []
    for mps_item in plan_items:
        key_materials = explode_key_materials_for_mps(
            db=db,
            plan=plan,
            mps_item=mps_item,
            current_level=1,
            max_levels=10
        )
        all_key_materials.extend(key_materials)

    # Commit to database
    for key_mat in all_key_materials:
        db.add(key_mat)
    db.commit()

    # Refresh to get IDs
    for key_mat in all_key_materials:
        db.refresh(key_mat)

    # Build response
    key_material_responses = []
    for key_mat in all_key_materials:
        # Get product and site names
        parent_product = db.get(Item, key_mat.parent_product_id)
        key_material_product = db.get(Item, key_mat.key_material_product_id)
        key_material_site = db.get(Site, key_mat.key_material_site_id)

        key_material_responses.append(MPSKeyMaterialResponse(
            id=key_mat.id,
            plan_id=key_mat.plan_id,
            mps_item_id=key_mat.mps_item_id,
            parent_product_id=key_mat.parent_product_id,
            parent_product_name=parent_product.name if parent_product else f"Product {key_mat.parent_product_id}",
            key_material_product_id=key_mat.key_material_product_id,
            key_material_product_name=key_material_product.name if key_material_product else f"Product {key_mat.key_material_product_id}",
            key_material_site_id=key_mat.key_material_site_id,
            key_material_site_name=key_material_site.name if key_material_site else f"Site {key_mat.key_material_site_id}",
            bom_level=key_mat.bom_level,
            component_quantity=key_mat.component_quantity,
            scrap_percentage=key_mat.scrap_percentage,
            weekly_gross_requirements=key_mat.weekly_gross_requirements,
            total_gross_requirement=key_mat.total_gross_requirement,
            is_bottleneck=key_mat.is_bottleneck,
            is_long_lead_time=key_mat.is_long_lead_time,
            is_strategic=key_mat.is_strategic,
            procurement_lead_time_days=key_mat.procurement_lead_time_days,
        ))

    return ExplodeKeyMaterialsResponse(
        plan_id=plan.id,
        plan_name=plan.name,
        total_key_materials=len(key_material_responses),
        key_materials=key_material_responses,
    )


@router.get("/plans/{plan_id}/key-materials", response_model=ExplodeKeyMaterialsResponse)
async def get_key_materials(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Get existing key material requirements for an MPS plan.

    Returns previously exploded key material requirements without re-exploding.
    """
    check_mps_permission(current_user, "view", db)

    # Get MPS plan
    plan = get_mps_plan_or_404(db, plan_id)

    # Get existing key material requirements
    key_materials = db.execute(
        select(MPSKeyMaterialRequirement).where(
            MPSKeyMaterialRequirement.plan_id == plan_id
        )
    ).scalars().all()

    # Build response
    key_material_responses = []
    for key_mat in key_materials:
        # Get product and site names
        parent_product = db.get(Item, key_mat.parent_product_id)
        key_material_product = db.get(Item, key_mat.key_material_product_id)
        key_material_site = db.get(Site, key_mat.key_material_site_id)

        key_material_responses.append(MPSKeyMaterialResponse(
            id=key_mat.id,
            plan_id=key_mat.plan_id,
            mps_item_id=key_mat.mps_item_id,
            parent_product_id=key_mat.parent_product_id,
            parent_product_name=parent_product.name if parent_product else f"Product {key_mat.parent_product_id}",
            key_material_product_id=key_mat.key_material_product_id,
            key_material_product_name=key_material_product.name if key_material_product else f"Product {key_mat.key_material_product_id}",
            key_material_site_id=key_mat.key_material_site_id,
            key_material_site_name=key_material_site.name if key_material_site else f"Site {key_mat.key_material_site_id}",
            bom_level=key_mat.bom_level,
            component_quantity=key_mat.component_quantity,
            scrap_percentage=key_mat.scrap_percentage,
            weekly_gross_requirements=key_mat.weekly_gross_requirements,
            total_gross_requirement=key_mat.total_gross_requirement,
            is_bottleneck=key_mat.is_bottleneck,
            is_long_lead_time=key_mat.is_long_lead_time,
            is_strategic=key_mat.is_strategic,
            procurement_lead_time_days=key_mat.procurement_lead_time_days,
        ))

    return ExplodeKeyMaterialsResponse(
        plan_id=plan.id,
        plan_name=plan.name,
        total_key_materials=len(key_material_responses),
        key_materials=key_material_responses,
    )

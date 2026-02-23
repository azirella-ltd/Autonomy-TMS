"""
Material Requirements Planning (MRP) API Endpoints

Provides MRP functionality including:
- MRP run execution from approved MPS plans
- BOM explosion and component requirements
- Purchase Order (PO) and Transfer Order (TO) generation
- MRP results and exception reporting
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from pydantic import BaseModel, Field
import uuid

from app.api.deps import get_db, get_current_user
from app.models.user import User, UserTypeEnum
from app.models.mps import MPSPlan, MPSPlanItem, MPSStatus
from app.models.sc_entities import (
    SupplyPlan,
    ProductBom,
    SourcingRules,
    InvPolicy,
)
from app.models.supply_chain_config import SupplyChainConfig, Node
from app.models.sc_entities import Product
from app.models.mrp import (
    MRPRun as MRPRunModel,
    MRPRequirement as MRPRequirementModel,
    MRPException as MRPExceptionModel,
)


# ============================================================================
# Request/Response Schemas
# ============================================================================

class MRPRunRequest(BaseModel):
    """Request schema for running MRP"""
    mps_plan_id: int = Field(..., description="MPS plan ID to explode")
    planning_horizon_weeks: Optional[int] = Field(
        None,
        description="Override planning horizon (defaults to MPS plan horizon)",
        ge=1,
        le=104
    )
    explode_bom_levels: Optional[int] = Field(
        None,
        description="Number of BOM levels to explode (None = all levels)",
        ge=1,
        le=10
    )
    generate_orders: bool = Field(
        True,
        description="Auto-generate PO/TO orders from requirements"
    )
    run_async: bool = Field(
        False,
        description="Run MRP asynchronously in background"
    )


class MRPRequirement(BaseModel):
    """Individual component requirement"""
    component_id: int
    component_name: str
    parent_id: Optional[int]
    parent_name: Optional[str]
    bom_level: int
    period_number: int
    period_start_date: date
    period_end_date: date
    gross_requirement: float
    scheduled_receipts: float
    projected_available: float
    net_requirement: float
    planned_order_receipt: float
    planned_order_release: float
    source_type: Optional[str] = Field(
        None,
        description="buy, transfer, or manufacture"
    )
    source_site_id: Optional[int] = None
    lead_time_days: Optional[int] = None


class MRPException(BaseModel):
    """MRP planning exception"""
    exception_type: str = Field(
        ...,
        description="Type: stockout, capacity_shortage, no_sourcing_rule, late_order, excess_inventory"
    )
    severity: str = Field(..., description="high, medium, low")
    component_id: int
    component_name: str
    site_id: int
    site_name: str
    period_number: int
    period_start_date: date
    message: str
    recommended_action: Optional[str] = None
    quantity_shortfall: Optional[float] = None


class GeneratedOrder(BaseModel):
    """Generated PO/TO/MO summary"""
    order_type: str = Field(..., description="po_request, to_request, mo_request")
    component_id: int
    component_name: str
    destination_site_id: int
    destination_site_name: str
    source_site_id: Optional[int] = None
    source_site_name: Optional[str] = None
    vendor_id: Optional[str] = None
    quantity: float
    order_date: date
    receipt_date: date
    lead_time_days: int
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None


class MRPRunSummary(BaseModel):
    """Summary statistics for MRP run"""
    total_components: int
    total_requirements: int
    total_net_requirements: float
    total_planned_orders: int
    total_exceptions: int
    exceptions_by_severity: Dict[str, int]
    orders_by_type: Dict[str, int]
    total_cost_estimate: float


class MRPRunResponse(BaseModel):
    """Response schema for MRP run"""
    run_id: str
    mps_plan_id: int
    mps_plan_name: str
    status: str = Field(..., description="completed, in_progress, failed")
    started_at: datetime
    completed_at: Optional[datetime] = None
    summary: MRPRunSummary
    requirements: List[MRPRequirement]
    exceptions: List[MRPException]
    generated_orders: List[GeneratedOrder]


class MRPRunListItem(BaseModel):
    """List item for MRP runs"""
    run_id: str
    mps_plan_id: int
    mps_plan_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    total_components: int
    total_exceptions: int
    total_orders: int


class MRPExceptionListResponse(BaseModel):
    """Response for exception list endpoint"""
    run_id: str
    mps_plan_id: int
    exceptions: List[MRPException]
    total_exceptions: int


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/mrp", tags=["Material Requirements Planning"])


# ============================================================================
# Database Storage
# ============================================================================

# MRP data is now persisted to mrp_run, mrp_requirement, and mrp_exception tables


# ============================================================================
# Helper Functions
# ============================================================================

def check_mrp_permission(user: User, action: str) -> None:
    """Check if user has permission for MRP action"""
    # System admins always have permission
    if getattr(user, "user_type", None) == UserTypeEnum.SYSTEM_ADMIN:
        return

    required_permissions = {
        "view": "view_mps",  # Reuse MPS view permission
        "manage": "manage_mps",  # Reuse MPS manage permission
    }

    permission = required_permissions.get(action)
    if not permission:
        return

    has_permission = False

    # Check if roles relationship is loaded
    if hasattr(user, "roles") and user.roles:
        for role in user.roles:
            if hasattr(role, "capabilities"):
                for capability in role.capabilities:
                    if capability.key == permission:
                        has_permission = True
                        break
            if has_permission:
                break

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have permission to {action} MRP"
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


def get_bom_components(
    db: Session,
    product_id: int,
    config_id: Optional[int] = None
) -> List[ProductBom]:
    """Get BOM components for a product"""
    query = select(ProductBom).where(ProductBom.product_id == product_id)

    if config_id:
        query = query.where(ProductBom.config_id == config_id)

    return db.execute(query).scalars().all()


def get_sourcing_rules(
    db: Session,
    product_id: int,
    site_id: int,
    config_id: Optional[int] = None
) -> List[SourcingRules]:
    """Get sourcing rules for product at site, ordered by priority"""
    query = select(SourcingRules).where(
        and_(
            SourcingRules.product_id == product_id,
            SourcingRules.site_id == site_id
        )
    ).order_by(SourcingRules.priority)

    if config_id:
        query = query.where(SourcingRules.config_id == config_id)

    return db.execute(query).scalars().all()


def calculate_net_requirements(
    gross_requirement: float,
    on_hand_inventory: float,
    scheduled_receipts: float,
    safety_stock: float
) -> float:
    """Calculate net requirements using MRP logic"""
    projected_available = on_hand_inventory + scheduled_receipts

    # Net requirement = max(0, gross_req + safety_stock - projected_available)
    net_requirement = max(0, gross_requirement + safety_stock - projected_available)

    return net_requirement


def explode_bom_recursive(
    db: Session,
    mps_plan: MPSPlan,
    plan_items: List[MPSPlanItem],
    max_levels: Optional[int] = None
) -> Dict[tuple, List[Dict]]:
    """
    Recursively explode BOM to get component requirements.

    Args:
        db: Database session
        mps_plan: MPS plan being exploded
        plan_items: Top-level MPS plan items
        max_levels: Maximum BOM levels to explode (None = unlimited)

    Returns:
        {(component_id, site_id, period): [requirement_dicts]}
    """
    requirements = {}

    # Helper function to explode a level
    def explode_level(parent_items: List[tuple], current_level: int):
        """
        Explode one level of BOM.

        Args:
            parent_items: List of (product_id, site_id, period_idx, quantity, parent_product_id) tuples
            current_level: Current BOM level (0 = MPS items, 1 = first level components, etc.)
        """
        if max_levels and current_level > max_levels:
            return

        next_level_items = []

        for product_id, site_id, period_idx, parent_qty, parent_product_id in parent_items:
            if parent_qty <= 0:
                continue

            # Get BOM components for this product
            bom_items = get_bom_components(db, product_id, mps_plan.supply_chain_config_id)

            if not bom_items:
                # No BOM means it's a purchased/transferred item
                continue

            # Explode each component
            for bom in bom_items:
                component_id = bom.component_product_id
                component_qty = parent_qty * bom.component_quantity

                # Account for scrap
                if bom.scrap_percentage and bom.scrap_percentage > 0:
                    component_qty *= (1 + bom.scrap_percentage / 100)

                key = (component_id, site_id, period_idx)

                if key not in requirements:
                    requirements[key] = []

                requirements[key].append({
                    "component_id": component_id,
                    "parent_id": product_id,
                    "bom_level": current_level,
                    "period_number": period_idx,
                    "gross_requirement": component_qty,
                })

                # Queue this component for next level explosion
                next_level_items.append((
                    component_id,
                    site_id,
                    period_idx,
                    component_qty,
                    product_id
                ))

        # Recursively explode next level
        if next_level_items:
            explode_level(next_level_items, current_level + 1)

    # Start with Level 0: Top-level items from MPS
    level_0_items = []
    for mps_item in plan_items:
        for period_idx, qty in enumerate(mps_item.weekly_quantities):
            if qty > 0:
                level_0_items.append((
                    mps_item.product_id,
                    mps_item.site_id,
                    period_idx,
                    qty,
                    None  # No parent for MPS items
                ))

    # Explode from level 1 onwards
    explode_level(level_0_items, 1)

    return requirements


def generate_planned_orders(
    db: Session,
    mps_plan: MPSPlan,
    requirements: Dict[tuple, List[Dict]]
) -> List[Dict]:
    """
    Generate PO/TO/MO planned orders from net requirements.

    Returns:
        List of planned order dicts
    """
    planned_orders = []

    for (component_id, site_id, period), req_list in requirements.items():
        # Aggregate gross requirements for this component/site/period
        total_gross_req = sum(r["gross_requirement"] for r in req_list)

        # Get current inventory from inv_level table
        from app.models.sc_entities import InvLevel

        inv_level = db.execute(
            select(InvLevel).where(
                and_(
                    InvLevel.site_id == site_id,
                    InvLevel.product_id == component_id
                )
            )
        ).scalar_one_or_none()

        on_hand = float(inv_level.on_hand_quantity) if inv_level and inv_level.on_hand_quantity else 0.0

        # Get scheduled receipts from supply_plan table for this period
        period_start = mps_plan.start_date + timedelta(weeks=period)
        period_end = period_start + timedelta(weeks=1)

        scheduled = db.execute(
            select(func.sum(SupplyPlan.quantity)).where(
                and_(
                    SupplyPlan.destination_site_id == site_id,
                    SupplyPlan.product_id == component_id,
                    SupplyPlan.planned_receipt_date >= period_start,
                    SupplyPlan.planned_receipt_date < period_end,
                    SupplyPlan.status.in_(['APPROVED', 'RELEASED'])
                )
            )
        ).scalar()

        scheduled_receipts = float(scheduled) if scheduled else 0.0

        # Get safety stock from inv_policy table
        safety_stock_val = db.execute(
            select(InvPolicy.ss_quantity).where(
                and_(
                    InvPolicy.product_id == component_id,
                    InvPolicy.site_id == site_id,
                    InvPolicy.config_id == mps_plan.supply_chain_config_id
                )
            )
        ).scalar()

        safety_stock = float(safety_stock_val) if safety_stock_val else 0.0

        # Calculate net requirement
        net_req = calculate_net_requirements(
            total_gross_req,
            on_hand,
            scheduled_receipts,
            safety_stock
        )

        if net_req <= 0:
            continue

        # Get sourcing rules
        sourcing_rules = get_sourcing_rules(
            db, component_id, site_id, mps_plan.supply_chain_config_id
        )

        if not sourcing_rules:
            # Create exception for missing sourcing rule
            continue

        # Use highest priority sourcing rule
        rule = sourcing_rules[0]

        # Calculate dates
        period_start = mps_plan.start_date + timedelta(weeks=period)
        lead_time_days = rule.lead_time or 7
        order_date = period_start - timedelta(days=lead_time_days)
        receipt_date = period_start

        # Create planned order
        planned_order = {
            "order_type": f"{rule.sourcing_rule_type}_request",  # buy_request, transfer_request, manufacture_request
            "component_id": component_id,
            "destination_site_id": site_id,
            "source_site_id": rule.supplier_site_id,
            "quantity": net_req,
            "order_date": order_date,
            "receipt_date": receipt_date,
            "lead_time_days": lead_time_days,
            "unit_cost": float(rule.unit_cost) if rule.unit_cost else 0.0,
        }

        planned_orders.append(planned_order)

    return planned_orders


def detect_mrp_exceptions(
    db: Session,
    mps_plan: MPSPlan,
    requirements: Dict[tuple, List[Dict]],
    planned_orders: List[Dict]
) -> List[Dict]:
    """
    Detect MRP planning exceptions.

    Types:
    - no_sourcing_rule: Component has no sourcing rule
    - stockout: Net requirement cannot be fulfilled
    - late_order: Lead time causes late delivery
    - excess_inventory: Projected inventory too high
    """
    exceptions = []

    # Check for components without sourcing rules
    for (component_id, site_id, period), req_list in requirements.items():
        sourcing_rules = get_sourcing_rules(
            db, component_id, site_id, mps_plan.supply_chain_config_id
        )

        if not sourcing_rules:
            # Get component details
            component = db.get(Product, component_id)
            site = db.get(Node, site_id)

            period_start = mps_plan.start_date + timedelta(weeks=period)

            total_gross = sum(r["gross_requirement"] for r in req_list)

            exceptions.append({
                "exception_type": "no_sourcing_rule",
                "severity": "high",
                "component_id": component_id,
                "component_name": component.name if component else f"Item {component_id}",
                "site_id": site_id,
                "site_name": site.name if site else f"Site {site_id}",
                "period_number": period,
                "period_start_date": period_start,
                "message": f"No sourcing rule defined for {component.name if component else 'component'} at {site.name if site else 'site'}",
                "recommended_action": "Create sourcing rule (buy, transfer, or manufacture)",
                "quantity_shortfall": total_gross,
            })

    # TODO: Add more exception detection logic
    # - Check lead times vs requirement dates
    # - Check capacity constraints
    # - Check supplier reliability

    return exceptions


def persist_mrp_to_supply_plan(
    db: Session,
    run_id: str,
    mps_plan: MPSPlan,
    planned_orders: List[Dict]
) -> int:
    """
    Persist MRP planned orders to supply_plan table.

    Returns:
        Number of records created
    """
    created_count = 0

    for order in planned_orders:
        # Map order_type to plan_type
        order_type = order["order_type"]
        if order_type == "buy_request":
            plan_type = "po_request"
        elif order_type == "transfer_request":
            plan_type = "to_request"
        elif order_type == "manufacture_request":
            plan_type = "mo_request"
        else:
            plan_type = "po_request"  # Default

        supply_plan_entry = SupplyPlan(
            plan_type=plan_type,
            product_id=order["component_id"],
            destination_site_id=order["destination_site_id"],
            source_site_id=order.get("source_site_id"),
            vendor_id=order.get("vendor_id"),
            planned_order_quantity=order["quantity"],
            planned_order_date=order["order_date"],
            planned_receipt_date=order["receipt_date"],
            lead_time_days=order["lead_time_days"],
            unit_cost=order.get("unit_cost"),
            planning_run_id=run_id,
            config_id=mps_plan.supply_chain_config_id,
        )

        db.add(supply_plan_entry)
        created_count += 1

    db.commit()

    return created_count


# ============================================================================
# API Endpoints
# ============================================================================

def _execute_mrp_background(
    run_id: str,
    mps_plan_id: int,
    user_id: int,
    request_dict: dict,
):
    """
    Background task that executes MRP logic.

    This function runs in a background thread/process and updates the MRPRun
    record with status changes (RUNNING → COMPLETED/FAILED).
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Update status to RUNNING
        mrp_run = db.query(MRPRunModel).filter(MRPRunModel.run_id == run_id).first()
        if not mrp_run:
            print(f"[MRP BG] ERROR: MRP run {run_id} not found")
            return

        mrp_run.status = "RUNNING"
        db.commit()
        print(f"[MRP BG] Status updated to RUNNING for run {run_id}")

        # Get MPS plan
        mps_plan = db.get(MPSPlan, mps_plan_id)
        if not mps_plan:
            raise ValueError(f"MPS plan {mps_plan_id} not found")

        # Get MPS plan items
        plan_items = db.execute(
            select(MPSPlanItem).where(MPSPlanItem.plan_id == mps_plan_id)
        ).scalars().all()

        if not plan_items:
            raise ValueError("MPS plan has no items")

        # Step 1: Explode BOM
        print(f"[MRP BG] Starting BOM explosion for {len(plan_items)} items")
        requirements_dict = explode_bom_recursive(
            db, mps_plan, plan_items, request_dict.get("explode_bom_levels")
        )
        print(f"[MRP BG] BOM explosion complete: {len(requirements_dict)} requirements")

        # Step 2: Generate planned orders
        print(f"[MRP BG] Generating planned orders")
        planned_orders = generate_planned_orders(db, mps_plan, requirements_dict)
        print(f"[MRP BG] Generated {len(planned_orders)} planned orders")

        # Step 3: Detect exceptions
        print(f"[MRP BG] Detecting exceptions")
        exceptions = detect_mrp_exceptions(db, mps_plan, requirements_dict, planned_orders)
        print(f"[MRP BG] Found {len(exceptions)} exceptions")

        # Step 4: Build requirements list
        print(f"[MRP BG] Building requirements list")
        requirements_list = []
        for (component_id, site_id, period), req_list in requirements_dict.items():
            component = db.get(Product, component_id)

            total_gross = sum(r["gross_requirement"] for r in req_list)

            on_hand = 0.0
            scheduled = 0.0
            safety_stock = 0.0

            projected = on_hand + scheduled
            net_req = calculate_net_requirements(total_gross, on_hand, scheduled, safety_stock)

            sourcing_rules = get_sourcing_rules(db, component_id, site_id, mps_plan.supply_chain_config_id)
            source_type = sourcing_rules[0].sourcing_rule_type if sourcing_rules else None
            source_site = sourcing_rules[0].supplier_site_id if sourcing_rules else None
            lead_time = sourcing_rules[0].lead_time if sourcing_rules else None

            period_start = mps_plan.start_date + timedelta(weeks=period)
            period_end = period_start + timedelta(days=mps_plan.bucket_size_days - 1)

            parent_id = req_list[0].get("parent_id") if req_list else None

            requirements_list.append({
                "component_id": component_id,
                "bom_level": req_list[0]["bom_level"] if req_list else 1,
                "period_number": period,
                "period_start_date": period_start,
                "period_end_date": period_end,
                "gross_requirement": total_gross,
                "scheduled_receipts": scheduled,
                "projected_available": projected,
                "net_requirement": net_req,
                "planned_order_receipt": net_req if net_req > 0 else 0.0,
                "planned_order_release": net_req if net_req > 0 else 0.0,
                "source_type": source_type,
                "source_site_id": source_site,
                "lead_time_days": lead_time,
            })

        # Step 5: Compute summary statistics
        orders_by_type = {}
        for order in planned_orders:
            order_type = order["order_type"]
            orders_by_type[order_type] = orders_by_type.get(order_type, 0) + 1

        exceptions_by_severity = {}
        for exc in exceptions:
            severity = exc["severity"]
            exceptions_by_severity[severity] = exceptions_by_severity.get(severity, 0) + 1

        total_cost = sum(
            order["quantity"] * order.get("unit_cost", 0.0)
            for order in planned_orders
        )

        total_net_req = sum(r["net_requirement"] for r in requirements_list)
        unique_components = len(set(r["component_id"] for r in requirements_list))

        # Step 6: Persist to supply_plan if requested
        if request_dict.get("generate_orders", True):
            persist_mrp_to_supply_plan(db, run_id, mps_plan, planned_orders)

        completed_at = datetime.now()

        # Step 7: Update MRP run with results
        mrp_run.status = "COMPLETED"
        mrp_run.completed_at = completed_at
        mrp_run.total_components = unique_components
        mrp_run.total_requirements = len(requirements_list)
        mrp_run.total_net_requirements = total_net_req
        mrp_run.total_planned_orders = len(planned_orders)
        mrp_run.total_exceptions = len(exceptions)
        mrp_run.total_cost_estimate = total_cost
        mrp_run.exceptions_by_severity = exceptions_by_severity
        mrp_run.orders_by_type = orders_by_type

        # Step 8: Persist requirements to database
        for req in requirements_list:
            mrp_req = MRPRequirementModel(
                mrp_run_id=mrp_run.id,
                component_id=req["component_id"],
                site_id=req.get("source_site_id"),
                bom_level=req["bom_level"],
                period_number=req["period_number"],
                period_start_date=req["period_start_date"],
                period_end_date=req["period_end_date"],
                gross_requirement=req["gross_requirement"],
                scheduled_receipts=req["scheduled_receipts"],
                projected_available=req["projected_available"],
                net_requirement=req["net_requirement"],
                planned_order_receipt=req["planned_order_receipt"],
                planned_order_release=req["planned_order_release"],
                source_type=req["source_type"],
                source_site_id=req["source_site_id"],
                lead_time_days=req["lead_time_days"],
                created_at=datetime.now(),
            )
            db.add(mrp_req)

        # Step 9: Persist exceptions to database
        for exc in exceptions:
            mrp_exc = MRPExceptionModel(
                mrp_run_id=mrp_run.id,
                exception_type=exc["exception_type"],
                severity=exc["severity"],
                component_id=exc["component_id"],
                site_id=exc["site_id"],
                period_number=exc["period_number"],
                period_start_date=exc["period_start_date"],
                message=exc["message"],
                quantity_shortfall=exc.get("quantity_shortfall"),
                is_resolved=False,
                created_at=datetime.now(),
            )
            db.add(mrp_exc)

        db.commit()
        print(f"[MRP BG] MRP run {run_id} completed successfully")

    except Exception as e:
        print(f"[MRP BG] ERROR in background task: {e}")
        import traceback
        traceback.print_exc()

        # Update status to FAILED
        try:
            mrp_run = db.query(MRPRunModel).filter(MRPRunModel.run_id == run_id).first()
            if mrp_run:
                mrp_run.status = "FAILED"
                mrp_run.error_message = str(e)
                mrp_run.completed_at = datetime.now()
                db.commit()
        except Exception as commit_err:
            print(f"[MRP BG] Failed to update error status: {commit_err}")
    finally:
        db.close()


@router.post("/run")
async def run_mrp(
    request: MRPRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict:
    """
    Execute MRP for an approved MPS plan asynchronously.

    This endpoint returns immediately with a run_id. The actual MRP execution
    happens in the background. Poll GET /mrp/runs/{run_id} to check status.

    Steps (executed in background):
    1. Validate MPS plan is APPROVED
    2. Explode BOM to get component requirements
    3. Calculate net requirements (gross - on_hand - scheduled)
    4. Apply sourcing rules to determine source
    5. Generate PO/TO/MO planned orders
    6. Detect exceptions (stockouts, late orders, etc.)
    7. Optionally persist to supply_plan table

    Requirements:
    - MPS plan must be APPROVED
    - BOM data must exist for manufactured items
    - Sourcing rules must exist for purchased/transferred items

    Returns:
    - run_id: UUID for this MRP run
    - status: "PENDING" (execution starts immediately in background)
    - message: Instructions for polling status
    """
    print(f"[MRP API] Starting async MRP run for plan {request.mps_plan_id}")
    check_mrp_permission(current_user, "manage")
    print(f"[MRP API] Permission check passed")

    # Validate MPS plan
    mps_plan = get_mps_plan_or_404(db, request.mps_plan_id)
    print(f"[MRP API] Got MPS plan: {mps_plan.name}")

    if mps_plan.status != MPSStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only run MRP on APPROVED MPS plans. Current status: {mps_plan.status.value}"
        )

    # Get MPS plan items to validate
    plan_items = db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == request.mps_plan_id)
    ).scalars().all()

    if not plan_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPS plan has no items"
        )

    # Generate run ID
    run_id = str(uuid.uuid4())
    started_at = datetime.now()

    # Get group_id from supply chain config
    config = db.get(SupplyChainConfig, mps_plan.supply_chain_config_id)
    group_id = config.group_id if config else None

    # Create MRP run record with PENDING status
    mrp_run = MRPRunModel(
        run_id=run_id,
        mps_plan_id=mps_plan.id,
        config_id=mps_plan.supply_chain_config_id,
        group_id=group_id,
        status="PENDING",
        explode_bom_levels=request.explode_bom_levels,
        planning_horizon_weeks=request.planning_horizon_weeks,
        generate_orders=request.generate_orders,
        created_by_id=current_user.id,
        created_at=started_at,
        started_at=started_at,
    )
    db.add(mrp_run)
    db.commit()
    db.refresh(mrp_run)

    print(f"[MRP API] Created MRP run {run_id} with status PENDING")

    # Convert request to dict for background task
    request_dict = {
        "mps_plan_id": request.mps_plan_id,
        "planning_horizon_weeks": request.planning_horizon_weeks,
        "explode_bom_levels": request.explode_bom_levels,
        "generate_orders": request.generate_orders,
    }

    # Queue background task
    background_tasks.add_task(
        _execute_mrp_background,
        run_id=run_id,
        mps_plan_id=request.mps_plan_id,
        user_id=current_user.id,
        request_dict=request_dict,
    )

    print(f"[MRP API] Queued background task for run {run_id}")

    # Return immediately
    return {
        "run_id": run_id,
        "mps_plan_id": mps_plan.id,
        "mps_plan_name": mps_plan.name,
        "status": "PENDING",
        "started_at": started_at.isoformat(),
        "message": f"MRP execution started in background. Poll GET /api/mrp/runs/{run_id} for status updates.",
    }


@router.get("/runs", response_model=List[MRPRunListItem])
async def list_mrp_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    mps_plan_id: Optional[int] = None,
) -> List[Dict]:
    """
    List all MRP runs.

    Optional filters:
    - mps_plan_id: Filter by MPS plan
    """
    check_mrp_permission(current_user, "view")

    # Query MRP runs from database
    query = select(MRPRunModel).order_by(MRPRunModel.created_at.desc())

    if mps_plan_id:
        query = query.where(MRPRunModel.mps_plan_id == mps_plan_id)

    mrp_runs = db.execute(query).scalars().all()

    runs = []
    for mrp_run in mrp_runs:
        # Get MPS plan name
        mps_plan = db.get(MPSPlan, mrp_run.mps_plan_id)

        runs.append(MRPRunListItem(
            run_id=mrp_run.run_id,
            mps_plan_id=mrp_run.mps_plan_id,
            mps_plan_name=mps_plan.name if mps_plan else f"Plan {mrp_run.mps_plan_id}",
            status=mrp_run.status,
            started_at=mrp_run.started_at or mrp_run.created_at,
            completed_at=mrp_run.completed_at,
            total_components=mrp_run.total_components or 0,
            total_exceptions=mrp_run.total_exceptions or 0,
            total_orders=mrp_run.total_planned_orders or 0,
        ))

    return runs


@router.get("/runs/{run_id}")
async def get_mrp_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict:
    """
    Get MRP run status and results by run ID.

    For PENDING/RUNNING runs, returns minimal status information.
    For COMPLETED runs, returns full results with requirements and exceptions.
    For FAILED runs, returns error information.
    """
    check_mrp_permission(current_user, "view")

    # Query MRP run from database
    mrp_run = db.execute(
        select(MRPRunModel).where(MRPRunModel.run_id == run_id)
    ).scalar_one_or_none()

    if not mrp_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MRP run with id {run_id} not found"
        )

    # Get MPS plan
    mps_plan = db.get(MPSPlan, mrp_run.mps_plan_id)

    # Base response for all statuses
    response = {
        "run_id": mrp_run.run_id,
        "mps_plan_id": mrp_run.mps_plan_id,
        "mps_plan_name": mps_plan.name if mps_plan else f"Plan {mrp_run.mps_plan_id}",
        "status": mrp_run.status.lower(),
        "started_at": mrp_run.started_at.isoformat() if mrp_run.started_at else None,
        "completed_at": mrp_run.completed_at.isoformat() if mrp_run.completed_at else None,
    }

    # If PENDING or RUNNING, return minimal response
    if mrp_run.status in ["PENDING", "RUNNING"]:
        response["message"] = f"MRP execution is {mrp_run.status.lower()}. Poll this endpoint for updates."
        response["summary"] = {
            "total_components": 0,
            "total_requirements": 0,
            "total_net_requirements": 0.0,
            "total_planned_orders": 0,
            "total_exceptions": 0,
            "exceptions_by_severity": {},
            "orders_by_type": {},
            "total_cost_estimate": 0.0,
        }
        return response

    # If FAILED, return error information
    if mrp_run.status == "FAILED":
        response["error_message"] = mrp_run.error_message
        response["message"] = "MRP execution failed. See error_message for details."
        response["summary"] = {
            "total_components": 0,
            "total_requirements": 0,
            "total_net_requirements": 0.0,
            "total_planned_orders": 0,
            "total_exceptions": 0,
            "exceptions_by_severity": {},
            "orders_by_type": {},
            "total_cost_estimate": 0.0,
        }
        return response

    # COMPLETED - return full results
    # Query requirements
    requirements = db.execute(
        select(MRPRequirementModel).where(MRPRequirementModel.mrp_run_id == mrp_run.id)
    ).scalars().all()

    requirements_list = []
    for req in requirements:
        component = db.get(Product, req.component_id)
        requirements_list.append({
            "component_id": req.component_id,
            "component_name": component.name if component else f"Item {req.component_id}",
            "parent_id": None,
            "parent_name": None,
            "bom_level": req.bom_level,
            "period_number": req.period_number,
            "period_start_date": req.period_start_date.isoformat() if req.period_start_date else None,
            "period_end_date": req.period_end_date.isoformat() if req.period_end_date else None,
            "gross_requirement": req.gross_requirement,
            "scheduled_receipts": req.scheduled_receipts or 0.0,
            "projected_available": req.projected_available or 0.0,
            "net_requirement": req.net_requirement,
            "planned_order_receipt": req.planned_order_receipt or 0.0,
            "planned_order_release": req.planned_order_release or 0.0,
            "source_type": req.source_type,
            "source_site_id": req.source_site_id,
            "lead_time_days": req.lead_time_days,
        })

    # Query exceptions
    exceptions = db.execute(
        select(MRPExceptionModel).where(MRPExceptionModel.mrp_run_id == mrp_run.id)
    ).scalars().all()

    exceptions_list = []
    for exc in exceptions:
        component = db.get(Product, exc.component_id)
        site = db.get(Node, exc.site_id)
        exceptions_list.append({
            "exception_type": exc.exception_type,
            "severity": exc.severity,
            "component_id": exc.component_id,
            "component_name": component.name if component else f"Item {exc.component_id}",
            "site_id": exc.site_id,
            "site_name": site.name if site else f"Site {exc.site_id}",
            "period_number": exc.period_number or 0,
            "period_start_date": exc.period_start_date.isoformat() if exc.period_start_date else None,
            "message": exc.message,
            "recommended_action": exc.recommended_action,
            "quantity_shortfall": exc.quantity_shortfall,
        })

    # Build summary
    summary = {
        "total_components": mrp_run.total_components or 0,
        "total_requirements": mrp_run.total_requirements or len(requirements),
        "total_net_requirements": mrp_run.total_net_requirements or 0.0,
        "total_planned_orders": mrp_run.total_planned_orders or 0,
        "total_exceptions": mrp_run.total_exceptions or len(exceptions),
        "exceptions_by_severity": mrp_run.exceptions_by_severity or {},
        "orders_by_type": mrp_run.orders_by_type or {},
        "total_cost_estimate": mrp_run.total_cost_estimate or 0.0,
    }

    response["summary"] = summary
    response["requirements"] = requirements_list
    response["exceptions"] = exceptions_list
    # Query generated orders from supply_plan table linked to this MRP run
    from app.models.sc_entities import SupplyPlan
    from sqlalchemy import and_
    generated_orders_query = db.query(SupplyPlan).filter(
        and_(
            SupplyPlan.source == "MRP",
            SupplyPlan.source_event_id == mrp_run.run_id,
        )
    ).all()

    orders_list = []
    for sp in generated_orders_query:
        product = db.get(Product, sp.product_id)
        site = db.get(Node, sp.site_id)
        from_site = db.get(Node, sp.from_site_id) if sp.from_site_id else None
        orders_list.append({
            "id": sp.id,
            "plan_type": sp.plan_type,
            "product_id": sp.product_id,
            "product_name": product.name if product else f"Item {sp.product_id}",
            "site_id": sp.site_id,
            "site_name": site.name if site else f"Site {sp.site_id}",
            "from_site_id": sp.from_site_id,
            "from_site_name": from_site.name if from_site else None,
            "planned_order_quantity": sp.planned_order_quantity,
            "planned_order_date": sp.planned_order_date.isoformat() if sp.planned_order_date else None,
            "planned_receipt_date": sp.planned_receipt_date.isoformat() if sp.planned_receipt_date else None,
            "order_cost": sp.order_cost,
            "supplier_id": sp.supplier_id,
        })
    response["generated_orders"] = orders_list

    return response


@router.get("/runs/{run_id}/exceptions", response_model=MRPExceptionListResponse)
async def get_mrp_exceptions(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    severity: Optional[str] = None,
) -> Dict:
    """
    Get MRP exceptions for a run.

    Optional filters:
    - severity: Filter by severity (high, medium, low)
    """
    check_mrp_permission(current_user, "view")

    # Query MRP run
    mrp_run = db.execute(
        select(MRPRunModel).where(MRPRunModel.run_id == run_id)
    ).scalar_one_or_none()

    if not mrp_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MRP run with id {run_id} not found"
        )

    # Query exceptions with optional severity filter
    query = select(MRPExceptionModel).where(MRPExceptionModel.mrp_run_id == mrp_run.id)

    if severity:
        query = query.where(MRPExceptionModel.severity == severity)

    exceptions = db.execute(query).scalars().all()

    exceptions_list = []
    for exc in exceptions:
        component = db.get(Product, exc.component_id)
        site = db.get(Node, exc.site_id)
        exceptions_list.append(MRPException(
            exception_type=exc.exception_type,
            severity=exc.severity,
            component_id=exc.component_id,
            component_name=component.name if component else f"Item {exc.component_id}",
            site_id=exc.site_id,
            site_name=site.name if site else f"Site {exc.site_id}",
            period_number=exc.period_index or 0,
            period_start_date=exc.period_start_date or date.today(),
            message=exc.message,
            recommended_action=None,
            quantity_shortfall=exc.quantity,
        ))

    return MRPExceptionListResponse(
        run_id=run_id,
        mps_plan_id=mrp_run.mps_plan_id,
        exceptions=exceptions_list,
        total_exceptions=len(exceptions_list),
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mrp_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an MRP run"""
    check_mrp_permission(current_user, "manage")

    # Query MRP run
    mrp_run = db.execute(
        select(MRPRunModel).where(MRPRunModel.run_id == run_id)
    ).scalar_one_or_none()

    if not mrp_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MRP run with id {run_id} not found"
        )

    # Delete MRP run (CASCADE will delete requirements and exceptions)
    db.delete(mrp_run)

    # Also delete from supply_plan table (planning_run_id = run_id)
    supply_plans = db.execute(
        select(SupplyPlan).where(SupplyPlan.planning_run_id == run_id)
    ).scalars().all()

    for supply_plan in supply_plans:
        db.delete(supply_plan)

    db.commit()

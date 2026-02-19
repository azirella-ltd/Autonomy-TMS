"""
Powell Framework API Endpoints

Exposes the Powell SDAM framework services through REST API:
- Allocations: Priority × Product × Location allocation management
- ATP: Allocated Available-to-Promise checks and commits
- Rebalancing: Cross-location inventory transfer recommendations
- PO Creation: Purchase order timing and quantity recommendations
- Order Tracking: Exception detection and recommended actions
- Training: TRM training status and triggers

Access Control:
- VIEW_POWELL: View allocations, recommendations, decisions
- MANAGE_POWELL: Create/update allocations, execute recommendations
- ADMIN_POWELL: Configure TRM training, manage policies
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, select
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from enum import Enum

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.powell_allocation import PowellAllocation
from app.models.planning_cascade import PolicyEnvelope

# Powell service imports
from app.services.powell import (
    # Allocation Service
    AllocationService,
    AllocationConfig,
    AllocationCadence,
    UnfulfillableOrderAction,
    PriorityAllocation,
    ConsumptionResult,
    # ATP Executor
    ATPExecutorTRM,
    ATPRequest,
    ATPResponse,
    # Rebalancing TRM
    InventoryRebalancingTRM,
    RebalancingState,
    SiteInventoryState,
    TransferLane,
    RebalanceRecommendation,
    # PO Creation TRM
    POCreationTRM,
    POCreationState,
    InventoryPosition,
    SupplierInfo,
    PORecommendation,
    # Order Tracking TRM
    OrderTrackingTRM,
    OrderState,
    OrderType,
    OrderStatus,
    ExceptionDetection,
    # Training
    TRMTrainer,
    TrainingConfig,
    TrainingMethod,
    TrainingResult,
)

router = APIRouter()


# ============================================================================
# Pydantic Models for API
# ============================================================================

class AllocationCreate(BaseModel):
    """Request to create/update allocations"""
    product_id: str
    location_id: str
    priority: int = Field(ge=1, le=5, description="1=highest, 5=lowest")
    allocated_qty: float = Field(ge=0)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class AllocationResponse(BaseModel):
    """Allocation details response"""
    id: Optional[int] = None
    product_id: str
    location_id: str
    priority: int
    allocated_qty: float
    consumed_qty: float
    available_qty: float
    valid_from: datetime
    valid_to: datetime


class AllocationTimelineBucket(BaseModel):
    """Single daily bucket for timeline chart"""
    date: str  # ISO date string, e.g. "2026-02-09"
    P1: float = 0.0
    P2: float = 0.0
    P3: float = 0.0
    P4: float = 0.0
    P5: float = 0.0
    is_today: bool = False


class PolicyContext(BaseModel):
    """S&OP policy envelope context relevant to allocation decisions"""
    envelope_id: Optional[int] = None
    effective_date: Optional[str] = None
    generated_by: Optional[str] = None
    allocation_reserves: Optional[Dict[str, float]] = None  # segment → fraction
    otif_floors: Optional[Dict[str, float]] = None  # segment → fraction
    safety_stock_targets: Optional[Dict[str, float]] = None  # category → weeks
    total_inventory_cap: Optional[float] = None
    gmroi_target: Optional[float] = None


class AllocationTimelineResponse(BaseModel):
    """Response for the allocation timeline endpoint"""
    product_id: str
    location_id: str
    today: str
    buckets: List[AllocationTimelineBucket]
    policy_context: Optional[PolicyContext] = None


class AllocationOverrideCell(BaseModel):
    """Single cell override"""
    priority: int = Field(ge=1, le=5)
    date: str  # ISO date string
    allocated_qty: float = Field(ge=0)


class AllocationBulkOverrideRequest(BaseModel):
    """Bulk override request for timeline cells"""
    product_id: str
    location_id: str
    overrides: List[AllocationOverrideCell]
    reason: Optional[str] = None


class AllocationBulkOverrideResponse(BaseModel):
    """Response from bulk override"""
    updated_count: int
    created_count: int
    product_id: str
    location_id: str


class ATPCheckRequest(BaseModel):
    """Request for ATP check"""
    order_id: str
    product_id: str
    location_id: str
    requested_qty: float = Field(gt=0)
    priority: int = Field(ge=1, le=5)
    requested_date: Optional[str] = None
    customer_id: Optional[str] = None


class ATPCheckResponse(BaseModel):
    """Response from ATP check"""
    order_id: str
    can_fulfill: bool
    available_qty: float
    promised_qty: float
    consumption_breakdown: Dict[int, float]
    confidence: float
    reasoning: str


class ATPCommitRequest(BaseModel):
    """Request to commit ATP decision"""
    order_id: str
    product_id: str
    location_id: str
    promised_qty: float
    priority: int


class RebalanceRequest(BaseModel):
    """Request for rebalancing evaluation"""
    product_id: str
    site_ids: List[str]


class RebalanceResponse(BaseModel):
    """Rebalancing recommendation response"""
    from_site: str
    to_site: str
    product_id: str
    quantity: float
    reason: str
    urgency: float
    confidence: float
    expected_cost: float
    source_dos_before: float
    source_dos_after: float
    dest_dos_before: float
    dest_dos_after: float


class PORecommendationRequest(BaseModel):
    """Request for PO recommendations"""
    product_id: str
    location_id: str


class PORecommendationResponse(BaseModel):
    """PO recommendation response"""
    product_id: str
    location_id: str
    supplier_id: str
    recommended_qty: float
    urgency: str
    trigger_reason: str
    expected_receipt_date: str
    expected_cost: float
    confidence: float
    reasoning: str


class OrderExceptionRequest(BaseModel):
    """Request for order exception check"""
    order_id: str
    order_type: str  # purchase_order, transfer_order, customer_order
    status: str
    created_date: str
    expected_date: str
    ordered_qty: float
    received_qty: float = 0


class OrderExceptionResponse(BaseModel):
    """Order exception detection response"""
    order_id: str
    exception_type: str
    severity: str
    recommended_action: str
    description: str
    impact_assessment: str
    confidence: float


class TrainingStatusResponse(BaseModel):
    """TRM training status response"""
    buffer_size: int
    records_with_expert: int
    records_with_next_state: int
    trm_type_distribution: Dict[str, int]
    average_reward: float
    last_training_result: Optional[Dict[str, Any]] = None


class TrainingTriggerRequest(BaseModel):
    """Request to trigger TRM training"""
    method: str = "hybrid"  # behavioral_cloning, td_learning, offline_rl, hybrid
    epochs: int = 100


# ============================================================================
# Service Instances (would be injected via DI in production)
# ============================================================================

# These are created per-request with config_id from the request
def get_allocation_service(config_id: int) -> AllocationService:
    """Get allocation service for config"""
    config = AllocationConfig(
        num_priorities=5,
        cadence=AllocationCadence.WEEKLY,
        unfulfillable_action=UnfulfillableOrderAction.BACKLOG
    )
    return AllocationService(config)


def get_atp_executor(config_id: int) -> ATPExecutorTRM:
    """Get ATP executor for config"""
    allocation_service = get_allocation_service(config_id)
    return ATPExecutorTRM(allocation_service, use_heuristic_fallback=True)


def get_rebalancing_trm() -> InventoryRebalancingTRM:
    """Get rebalancing TRM"""
    return InventoryRebalancingTRM(use_heuristic_fallback=True)


def get_po_creation_trm() -> POCreationTRM:
    """Get PO creation TRM"""
    return POCreationTRM(use_heuristic_fallback=True)


def get_order_tracking_trm() -> OrderTrackingTRM:
    """Get order tracking TRM"""
    return OrderTrackingTRM(use_heuristic_fallback=True)


# ============================================================================
# Allocation Endpoints
# ============================================================================

@router.get("/allocations/{config_id}", response_model=List[AllocationResponse])
async def get_allocations(
    config_id: int,
    product_id: Optional[str] = None,
    location_id: Optional[str] = None,
    priority: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current allocations for a config.

    Filter by product_id, location_id, and/or priority.
    """
    service = get_allocation_service(config_id)

    # Get allocation status
    if product_id and location_id:
        status = service.get_allocation_status(product_id, location_id)
        allocations = []
        for p, alloc_status in status.items():
            if priority is None or p == priority:
                allocations.append(AllocationResponse(
                    product_id=product_id,
                    location_id=location_id,
                    priority=p,
                    allocated_qty=alloc_status.get("allocated", 0),
                    consumed_qty=alloc_status.get("consumed", 0),
                    available_qty=alloc_status.get("available", 0),
                    valid_from=datetime.now(),
                    valid_to=datetime.now() + timedelta(days=7)
                ))
        return allocations

    # TODO: Query from database for broader filters
    return []


@router.post("/allocations/{config_id}", response_model=AllocationResponse)
async def create_allocation(
    config_id: int,
    allocation: AllocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create or update an allocation.

    Allocations are typically generated by tGNN but can be manually adjusted.
    """
    service = get_allocation_service(config_id)

    # Set allocation
    valid_from = allocation.valid_from or datetime.now()
    valid_to = allocation.valid_to or (datetime.now() + timedelta(days=7))

    service.set_allocation(
        product_id=allocation.product_id,
        location_id=allocation.location_id,
        priority=allocation.priority,
        quantity=allocation.allocated_qty,
        valid_from=valid_from,
        valid_to=valid_to
    )

    return AllocationResponse(
        product_id=allocation.product_id,
        location_id=allocation.location_id,
        priority=allocation.priority,
        allocated_qty=allocation.allocated_qty,
        consumed_qty=0,
        available_qty=allocation.allocated_qty,
        valid_from=valid_from,
        valid_to=valid_to
    )


@router.post("/allocations/{config_id}/generate")
async def generate_allocations(
    config_id: int,
    product_ids: List[str],
    location_ids: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger tGNN to generate allocations for products/locations.

    This would call the Execution tGNN to compute priority allocations.
    """
    # TODO: Integrate with tGNN service
    return {
        "status": "triggered",
        "message": f"Allocation generation triggered for {len(product_ids)} products at {len(location_ids)} locations",
        "config_id": config_id
    }


@router.get("/allocations/{config_id}/timeline", response_model=AllocationTimelineResponse)
async def get_allocation_timeline(
    config_id: int,
    product_id: str = Query(..., description="Product ID"),
    location_id: str = Query(..., description="Location/site ID"),
    days_past: int = Query(5, ge=0, le=30),
    days_future: int = Query(9, ge=0, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get allocation timeline for a product/location.

    Returns daily buckets aggregated by priority class (P1-P5)
    for the specified date window (default: 5 past + today + 9 future = 15 days).
    """
    today = date.today()
    window_start = today - timedelta(days=days_past)
    window_end = today + timedelta(days=days_future)

    # Convert to datetime for comparison with valid_from/valid_to
    dt_start = datetime.combine(window_start, datetime.min.time())
    dt_end = datetime.combine(window_end, datetime.max.time())

    result = await db.execute(
        select(PowellAllocation).where(
            PowellAllocation.config_id == config_id,
            PowellAllocation.product_id == product_id,
            PowellAllocation.location_id == location_id,
            PowellAllocation.is_active == True,
            PowellAllocation.valid_from <= dt_end,
            PowellAllocation.valid_to >= dt_start,
        )
    )
    rows = result.scalars().all()

    total_days = days_past + 1 + days_future
    buckets = []
    for day_offset in range(total_days):
        bucket_date = window_start + timedelta(days=day_offset)
        bucket = {
            "date": bucket_date.isoformat(),
            "P1": 0.0, "P2": 0.0, "P3": 0.0, "P4": 0.0, "P5": 0.0,
            "is_today": bucket_date == today,
        }

        for row in rows:
            row_start = row.valid_from.date() if isinstance(row.valid_from, datetime) else row.valid_from
            row_end = row.valid_to.date() if isinstance(row.valid_to, datetime) else row.valid_to
            if row_start <= bucket_date <= row_end:
                period_days = max(1, (row_end - row_start).days + 1)
                if row.allocation_cadence == "daily" or period_days == 1:
                    daily_qty = row.allocated_qty
                else:
                    daily_qty = row.allocated_qty / period_days
                p_key = f"P{row.priority}"
                if p_key in bucket:
                    bucket[p_key] = round(bucket[p_key] + daily_qty, 1)

        buckets.append(AllocationTimelineBucket(**bucket))

    # Fetch active S&OP Policy Envelope for context
    policy_ctx = None
    try:
        pe_result = await db.execute(
            select(PolicyEnvelope)
            .where(PolicyEnvelope.config_id == config_id)
            .order_by(PolicyEnvelope.effective_date.desc())
            .limit(1)
        )
        envelope = pe_result.scalars().first()
        if envelope:
            policy_ctx = PolicyContext(
                envelope_id=envelope.id,
                effective_date=envelope.effective_date.isoformat() if envelope.effective_date else None,
                generated_by=envelope.generated_by if isinstance(envelope.generated_by, str) else (envelope.generated_by.value if envelope.generated_by else None),
                allocation_reserves=envelope.allocation_reserves,
                otif_floors=envelope.otif_floors,
                safety_stock_targets=envelope.safety_stock_targets,
                total_inventory_cap=envelope.total_inventory_cap,
                gmroi_target=envelope.gmroi_target,
            )
    except Exception:
        pass  # Policy context is supplementary; don't fail the timeline

    return AllocationTimelineResponse(
        product_id=product_id,
        location_id=location_id,
        today=today.isoformat(),
        buckets=buckets,
        policy_context=policy_ctx,
    )


@router.post("/allocations/{config_id}/bulk-override", response_model=AllocationBulkOverrideResponse)
async def bulk_override_allocations(
    config_id: int,
    request: AllocationBulkOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Override allocation quantities for specific priority/date cells.

    Creates or updates daily allocation rows with allocation_source='manual'.
    Used by the allocmgr to fine-tune tGNN-generated allocations.
    """
    updated = 0
    created = 0

    for cell in request.overrides:
        cell_date = datetime.strptime(cell.date, "%Y-%m-%d").date()
        cell_start = datetime.combine(cell_date, datetime.min.time())
        cell_end = datetime.combine(cell_date, datetime.max.time())

        # Look for an existing daily row for this exact date
        result = await db.execute(
            select(PowellAllocation).where(
                PowellAllocation.config_id == config_id,
                PowellAllocation.product_id == request.product_id,
                PowellAllocation.location_id == request.location_id,
                PowellAllocation.priority == cell.priority,
                PowellAllocation.allocation_cadence == "daily",
                PowellAllocation.valid_from >= cell_start,
                PowellAllocation.valid_from <= cell_end,
                PowellAllocation.is_active == True,
            )
        )
        existing = result.scalars().first()

        if existing:
            existing.allocated_qty = cell.allocated_qty
            existing.allocation_source = "manual"
            existing.updated_at = datetime.now()
            updated += 1
        else:
            new_alloc = PowellAllocation(
                config_id=config_id,
                product_id=request.product_id,
                location_id=request.location_id,
                priority=cell.priority,
                allocated_qty=cell.allocated_qty,
                consumed_qty=0,
                reserved_qty=0,
                allocation_source="manual",
                allocation_cadence="daily",
                valid_from=cell_start,
                valid_to=cell_end,
                is_active=True,
            )
            db.add(new_alloc)
            created += 1

    await db.commit()

    return AllocationBulkOverrideResponse(
        updated_count=updated,
        created_count=created,
        product_id=request.product_id,
        location_id=request.location_id,
    )


# ============================================================================
# ATP Endpoints
# ============================================================================

@router.post("/atp/{config_id}/check", response_model=ATPCheckResponse)
async def check_atp(
    config_id: int,
    request: ATPCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check Available-to-Promise for an order.

    Uses TRM-based AATP with priority consumption logic:
    1. Own tier first
    2. Bottom-up from lowest priority
    3. Cannot consume above own tier
    """
    executor = get_atp_executor(config_id)

    atp_request = ATPRequest(
        order_id=request.order_id,
        product_id=request.product_id,
        location_id=request.location_id,
        requested_qty=request.requested_qty,
        priority=request.priority,
        requested_date=request.requested_date,
        customer_id=request.customer_id
    )

    response = executor.check_atp(atp_request)

    return ATPCheckResponse(
        order_id=response.order_id,
        can_fulfill=response.can_fulfill,
        available_qty=response.available_qty,
        promised_qty=response.promised_qty,
        consumption_breakdown=response.consumption_breakdown,
        confidence=response.confidence,
        reasoning=response.reasoning
    )


@router.post("/atp/{config_id}/commit")
async def commit_atp(
    config_id: int,
    request: ATPCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Commit an ATP decision, consuming from allocations.

    Called when order is confirmed after ATP check.
    """
    executor = get_atp_executor(config_id)

    atp_request = ATPRequest(
        order_id=request.order_id,
        product_id=request.product_id,
        location_id=request.location_id,
        requested_qty=request.promised_qty,
        priority=request.priority
    )

    atp_response = ATPResponse(
        order_id=request.order_id,
        line_id=None,
        can_fulfill=True,
        available_qty=request.promised_qty,
        promised_qty=request.promised_qty
    )

    result = executor.commit_atp(atp_request, atp_response)

    return {
        "order_id": result.order_id,
        "fulfilled_qty": result.fulfilled_qty,
        "fully_fulfilled": result.fully_fulfilled,
        "consumption_by_priority": result.consumption_by_priority
    }


@router.get("/atp/{config_id}/metrics")
async def get_atp_metrics(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get ATP executor performance metrics.
    """
    executor = get_atp_executor(config_id)
    return executor.get_metrics()


# ============================================================================
# Rebalancing Endpoints
# ============================================================================

@router.post("/rebalancing/{config_id}/evaluate", response_model=List[RebalanceResponse])
async def evaluate_rebalancing(
    config_id: int,
    request: RebalanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Evaluate rebalancing opportunities for a product across sites.

    Returns ranked recommendations for inventory transfers.
    """
    trm = get_rebalancing_trm()

    # Build state from request (would normally come from inventory service)
    # This is a simplified example
    site_states = {}
    for site_id in request.site_ids:
        site_states[site_id] = SiteInventoryState(
            site_id=site_id,
            product_id=request.product_id,
            on_hand=100,  # Would come from inventory
            in_transit=0,
            committed=0,
            backlog=0,
            demand_forecast=50,
            demand_uncertainty=10,
            safety_stock=20,
            target_dos=14
        )

    # Build transfer lanes (would come from network config)
    transfer_lanes = []
    for i, from_site in enumerate(request.site_ids):
        for to_site in request.site_ids[i+1:]:
            transfer_lanes.append(TransferLane(
                from_site=from_site,
                to_site=to_site,
                transfer_time=2,
                cost_per_unit=1.0
            ))
            transfer_lanes.append(TransferLane(
                from_site=to_site,
                to_site=from_site,
                transfer_time=2,
                cost_per_unit=1.0
            ))

    state = RebalancingState(
        product_id=request.product_id,
        site_states=site_states,
        transfer_lanes=transfer_lanes
    )

    recommendations = trm.evaluate_rebalancing(state)

    return [
        RebalanceResponse(
            from_site=r.from_site,
            to_site=r.to_site,
            product_id=r.product_id,
            quantity=r.quantity,
            reason=r.reason.value,
            urgency=r.urgency,
            confidence=r.confidence,
            expected_cost=r.expected_cost,
            source_dos_before=r.source_dos_before,
            source_dos_after=r.source_dos_after,
            dest_dos_before=r.dest_dos_before,
            dest_dos_after=r.dest_dos_after
        )
        for r in recommendations
    ]


@router.post("/rebalancing/{config_id}/execute")
async def execute_rebalancing(
    config_id: int,
    recommendation: RebalanceResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a rebalancing recommendation by creating a transfer order.
    """
    # TODO: Create transfer order via supply planning service
    return {
        "status": "executed",
        "transfer_order_id": f"TO-{recommendation.from_site}-{recommendation.to_site}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "quantity": recommendation.quantity,
        "from_site": recommendation.from_site,
        "to_site": recommendation.to_site
    }


# ============================================================================
# PO Creation Endpoints
# ============================================================================

@router.post("/po-recommendations/{config_id}", response_model=List[PORecommendationResponse])
async def get_po_recommendations(
    config_id: int,
    request: PORecommendationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get PO creation recommendations for a product-location.

    Returns recommendations with timing, quantity, and supplier selection.
    """
    trm = get_po_creation_trm()

    # Build state (would come from inventory and supplier services)
    inv_position = InventoryPosition(
        product_id=request.product_id,
        location_id=request.location_id,
        on_hand=50,
        in_transit=0,
        on_order=0,
        committed=10,
        backlog=0,
        safety_stock=20,
        reorder_point=40,
        target_inventory=100,
        average_daily_demand=5,
        demand_variability=2
    )

    suppliers = [
        SupplierInfo(
            supplier_id="SUP-001",
            product_id=request.product_id,
            lead_time_days=7,
            lead_time_variability=1,
            unit_cost=10.0,
            order_cost=50.0,
            min_order_qty=10,
            on_time_rate=0.95
        ),
        SupplierInfo(
            supplier_id="SUP-002",
            product_id=request.product_id,
            lead_time_days=5,
            lead_time_variability=2,
            unit_cost=12.0,
            order_cost=30.0,
            min_order_qty=5,
            on_time_rate=0.90
        )
    ]

    state = POCreationState(
        product_id=request.product_id,
        location_id=request.location_id,
        inventory_position=inv_position,
        suppliers=suppliers,
        forecast_next_30_days=150,
        forecast_uncertainty=30
    )

    recommendations = trm.evaluate_po_need(state)

    return [
        PORecommendationResponse(
            product_id=r.product_id,
            location_id=r.location_id,
            supplier_id=r.supplier_id,
            recommended_qty=r.recommended_qty,
            urgency=r.urgency.value,
            trigger_reason=r.trigger_reason.value,
            expected_receipt_date=r.expected_receipt_date,
            expected_cost=r.expected_cost,
            confidence=r.confidence,
            reasoning=r.reasoning
        )
        for r in recommendations
    ]


@router.post("/po-recommendations/{config_id}/execute")
async def execute_po_recommendation(
    config_id: int,
    recommendation: PORecommendationResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a PO recommendation by creating a purchase order.
    """
    # TODO: Create PO via procurement service
    return {
        "status": "executed",
        "purchase_order_id": f"PO-{recommendation.supplier_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "quantity": recommendation.recommended_qty,
        "supplier_id": recommendation.supplier_id,
        "expected_receipt_date": recommendation.expected_receipt_date
    }


# ============================================================================
# Order Tracking / Exception Endpoints
# ============================================================================

@router.post("/exceptions/{config_id}/check", response_model=OrderExceptionResponse)
async def check_order_exception(
    config_id: int,
    request: OrderExceptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check an order for exceptions.

    Detects late deliveries, quantity shortages, stuck orders, etc.
    """
    trm = get_order_tracking_trm()

    order_state = OrderState(
        order_id=request.order_id,
        order_type=OrderType(request.order_type),
        status=OrderStatus(request.status),
        created_date=request.created_date,
        expected_date=request.expected_date,
        ordered_qty=request.ordered_qty,
        received_qty=request.received_qty,
        remaining_qty=request.ordered_qty - request.received_qty
    )

    detection = trm.evaluate_order(order_state)

    return OrderExceptionResponse(
        order_id=detection.order_id,
        exception_type=detection.exception_type.value,
        severity=detection.severity.value,
        recommended_action=detection.recommended_action.value,
        description=detection.description,
        impact_assessment=detection.impact_assessment,
        confidence=detection.confidence
    )


@router.post("/exceptions/{config_id}/batch", response_model=List[OrderExceptionResponse])
async def check_order_exceptions_batch(
    config_id: int,
    requests: List[OrderExceptionRequest],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check multiple orders for exceptions in batch.
    """
    trm = get_order_tracking_trm()

    order_states = [
        OrderState(
            order_id=req.order_id,
            order_type=OrderType(req.order_type),
            status=OrderStatus(req.status),
            created_date=req.created_date,
            expected_date=req.expected_date,
            ordered_qty=req.ordered_qty,
            received_qty=req.received_qty,
            remaining_qty=req.ordered_qty - req.received_qty
        )
        for req in requests
    ]

    detections = trm.evaluate_orders_batch(order_states)

    return [
        OrderExceptionResponse(
            order_id=d.order_id,
            exception_type=d.exception_type.value,
            severity=d.severity.value,
            recommended_action=d.recommended_action.value,
            description=d.description,
            impact_assessment=d.impact_assessment,
            confidence=d.confidence
        )
        for d in detections
    ]


@router.get("/exceptions/{config_id}/critical", response_model=List[OrderExceptionResponse])
async def get_critical_exceptions(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all critical and high-severity exceptions.

    Used for exception dashboard and alerts.
    """
    # TODO: Query from powell_order_exceptions table
    return []


# ============================================================================
# Training Endpoints
# ============================================================================

@router.get("/training/{config_id}/status", response_model=TrainingStatusResponse)
async def get_training_status(
    config_id: int,
    trm_type: str = Query("all", description="atp, rebalancing, po_creation, order_tracking, or all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get TRM training status and statistics.
    """
    # TODO: Load trainer state from database/cache
    return TrainingStatusResponse(
        buffer_size=0,
        records_with_expert=0,
        records_with_next_state=0,
        trm_type_distribution={},
        average_reward=0.0,
        last_training_result=None
    )


@router.post("/training/{config_id}/trigger")
async def trigger_training(
    config_id: int,
    request: TrainingTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger TRM training.

    Methods:
    - behavioral_cloning: Learn from expert demonstrations
    - td_learning: Q-learning with actual outcomes
    - offline_rl: Conservative Q-learning from logs
    - hybrid: BC warm-start + RL fine-tune (recommended)
    """
    method_map = {
        "behavioral_cloning": TrainingMethod.BEHAVIORAL_CLONING,
        "td_learning": TrainingMethod.TD_LEARNING,
        "offline_rl": TrainingMethod.OFFLINE_RL,
        "hybrid": TrainingMethod.HYBRID
    }

    method = method_map.get(request.method, TrainingMethod.HYBRID)

    # TODO: Actually trigger training (async job)
    return {
        "status": "triggered",
        "method": request.method,
        "epochs": request.epochs,
        "job_id": f"train-{config_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    }


@router.get("/training/{config_id}/history")
async def get_training_history(
    config_id: int,
    limit: int = Query(10, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get TRM training history.
    """
    # TODO: Query from database
    return []


# ============================================================================
# Monitoring Endpoints
# ============================================================================

class MonitoringRunRequest(BaseModel):
    """Request for running monitoring checks"""
    check_types: Optional[List[str]] = None  # exceptions, po_recommendations, rebalancing
    game_id: Optional[int] = None


class MonitoringResultResponse(BaseModel):
    """Monitoring result response"""
    check_type: str
    timestamp: str
    config_id: int
    findings_count: int
    critical_count: int
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]


@router.post("/monitoring/{config_id}/run", response_model=Dict[str, MonitoringResultResponse])
async def run_monitoring_checks(
    config_id: int,
    request: Optional[MonitoringRunRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run Powell monitoring checks.

    Executes background monitoring for:
    - Order exceptions (late, shortage, stuck orders)
    - PO recommendations (low inventory positions)
    - Rebalancing opportunities (inventory imbalances)

    If check_types is not specified, runs all checks.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from app.services.powell.monitoring_service import PowellMonitoringService

    # For sync endpoint, we use the monitoring service with async-to-sync wrapper
    # In production, this would be properly async
    game_id = request.game_id if request else None
    check_types = request.check_types if request else None

    # Create monitoring service (simplified - would use DI in production)
    # Note: This endpoint demonstrates the interface; actual impl needs async session
    results = {
        "status": "monitoring_endpoint_ready",
        "message": "Use /monitoring/{config_id}/exceptions, /monitoring/{config_id}/po, or /monitoring/{config_id}/rebalancing for individual checks",
        "config_id": config_id,
    }

    return results


@router.get("/monitoring/{config_id}/exceptions", response_model=MonitoringResultResponse)
async def check_exceptions(
    config_id: int,
    game_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run exception detection monitoring.

    Scans active orders for:
    - Late delivery risk
    - Quantity shortages
    - Stuck in transit
    - Missing confirmations
    """
    # This would call the monitoring service
    # Simplified response for now
    return MonitoringResultResponse(
        check_type="order_exceptions",
        timestamp=datetime.utcnow().isoformat(),
        config_id=config_id,
        findings_count=0,
        critical_count=0,
        findings=[],
        recommendations=[]
    )


@router.get("/monitoring/{config_id}/po", response_model=MonitoringResultResponse)
async def check_po_needs(
    config_id: int,
    game_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run PO recommendation monitoring.

    Identifies inventory positions requiring replenishment:
    - Below reorder point
    - Low days of supply
    - Upcoming demand exceeds ATP
    """
    return MonitoringResultResponse(
        check_type="po_recommendations",
        timestamp=datetime.utcnow().isoformat(),
        config_id=config_id,
        findings_count=0,
        critical_count=0,
        findings=[],
        recommendations=[]
    )


@router.get("/monitoring/{config_id}/rebalancing", response_model=MonitoringResultResponse)
async def check_rebalancing_needs(
    config_id: int,
    game_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run rebalancing monitoring.

    Identifies inventory imbalances across sites:
    - Sites with excess inventory
    - Sites at stockout risk
    - Transfer opportunities
    """
    return MonitoringResultResponse(
        check_type="rebalancing",
        timestamp=datetime.utcnow().isoformat(),
        config_id=config_id,
        findings_count=0,
        critical_count=0,
        findings=[],
        recommendations=[]
    )


@router.get("/monitoring/{config_id}/status")
async def get_monitoring_status(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get monitoring service status and last check times.
    """
    return {
        "config_id": config_id,
        "last_exception_check": None,
        "last_po_check": None,
        "last_rebalance_check": None,
        "monitoring_enabled": True,
        "config": {
            "exception_interval_minutes": 60,
            "po_interval_minutes": 240,
            "rebalance_interval_minutes": 1440,
        }
    }


# ============================================================================
# Decision History Endpoints
# ============================================================================

@router.get("/decisions/{config_id}/atp")
async def get_atp_decision_history(
    config_id: int,
    limit: int = Query(100, le=1000),
    product_id: Optional[str] = None,
    location_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get ATP decision history for analysis and training.
    """
    # TODO: Query from powell_atp_decisions table
    return []


@router.get("/decisions/{config_id}/rebalancing")
async def get_rebalancing_decision_history(
    config_id: int,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get rebalancing decision history.
    """
    # TODO: Query from powell_rebalance_decisions table
    return []


@router.get("/decisions/{config_id}/po")
async def get_po_decision_history(
    config_id: int,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get PO creation decision history.
    """
    # TODO: Query from powell_po_decisions table
    return []

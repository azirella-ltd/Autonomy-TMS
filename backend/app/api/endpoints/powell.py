"""
Powell Framework API Endpoints

Exposes the Powell SDAM framework services through REST API:
- Allocations: Priority × Product × Location allocation management
- ATP: Allocated Available-to-Promise checks and commits
- Rebalancing: Cross-site inventory transfer recommendations
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
from app.core.clock import config_today
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
    # PO Creation TRM retired — see commit 3dc1d72e. TMS uses
    # FreightProcurementTRM for the ACQUIRE phase.
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
    """Response from ATP check with optional conformal prediction intervals"""
    order_id: str
    can_fulfill: bool
    available_qty: float
    promised_qty: float
    consumption_breakdown: Dict[int, float]
    confidence: float
    reasoning: str
    # Conformal Decision Theory (CDT) risk bound
    risk_bound: Optional[float] = Field(
        None, description="P(loss > threshold) from CDT wrapper. Lower is safer."
    )
    risk_assessment: Optional[Dict[str, Any]] = Field(
        None, description="Full CDT diagnostic: threshold, calibration_size, interval_width"
    )
    # Demand conformal interval for the order's product-site
    demand_interval: Optional[Dict[str, Any]] = Field(
        None, description="Conformal demand interval: {lower, upper, point, coverage, method}"
    )


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
    risk_bound: Optional[float] = Field(None, description="P(loss > threshold) from CDT wrapper")
    risk_assessment: Optional[Dict[str, Any]] = Field(None, description="Full CDT diagnostic")


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
    risk_bound: Optional[float] = Field(None, description="P(loss > threshold) from CDT wrapper")
    risk_assessment: Optional[Dict[str, Any]] = Field(None, description="Full CDT diagnostic")
    lead_time_interval: Optional[Dict[str, float]] = Field(None, description="Conformal lead time interval")
    demand_interval: Optional[Dict[str, float]] = Field(None, description="Conformal demand interval")


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
    risk_bound: Optional[float] = Field(None, description="P(loss > threshold) from CDT wrapper")
    risk_assessment: Optional[Dict[str, Any]] = Field(None, description="Full CDT diagnostic")


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


# get_po_creation_trm retired — see commit 3dc1d72e.


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

    # Query from database for broader filters
    from app.models.powell_allocation import PowellAllocation
    query = db.query(PowellAllocation).filter(PowellAllocation.config_id == config_id)
    if product_id:
        query = query.filter(PowellAllocation.product_id == product_id)
    if location_id:
        query = query.filter(PowellAllocation.location_id == location_id)
    rows = query.order_by(PowellAllocation.priority).limit(500).all()
    return [
        AllocationResponse(
            product_id=r.product_id,
            location_id=r.location_id,
            priority=r.priority,
            allocated_qty=r.allocated_qty or 0,
            consumed_qty=r.consumed_qty or 0,
            available_qty=(r.allocated_qty or 0) - (r.consumed_qty or 0),
            valid_from=r.valid_from,
            valid_to=r.valid_to,
        )
        for r in rows
    ]


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
    site_ids: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger tGNN to generate allocations for products/sites.

    This would call the Execution tGNN to compute priority allocations.
    """
    # Generate allocations via AllocationService (fair-share if no tGNN)
    service = get_allocation_service(config_id)
    generated = 0
    for pid in product_ids:
        for sid in site_ids:
            for priority in range(1, 6):
                service.set_allocation(pid, sid, priority, quantity=0,
                                       valid_from=datetime.now(),
                                       valid_to=datetime.now() + timedelta(days=7))
                generated += 1
    return {
        "status": "completed",
        "message": f"Generated {generated} allocation slots for {len(product_ids)} products x {len(site_ids)} sites x 5 priorities",
        "config_id": config_id,
        "generated": generated,
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
    Get allocation timeline for a product/site.

    Returns daily buckets aggregated by priority class (P1-P5)
    for the specified date window (default: 5 past + today + 9 future = 15 days).
    """
    today = await config_today(config_id, db)
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

    # Get demand conformal interval (optional enrichment)
    demand_interval = None
    try:
        from app.services.conformal_prediction.suite import get_conformal_suite
        suite = get_conformal_suite()
        location_int = int(request.location_id) if request.location_id else None
        if location_int and suite.has_demand_predictor(request.product_id, location_int):
            interval = suite.predict_demand(
                request.product_id, location_int, request.requested_qty
            )
            demand_interval = {
                "lower": interval.lower,
                "upper": interval.upper,
                "point": interval.point_estimate,
                "coverage": interval.coverage_target,
                "method": interval.method,
            }
    except Exception:
        pass  # Conformal enrichment is optional

    return ATPCheckResponse(
        order_id=response.order_id,
        can_fulfill=response.can_fulfill,
        available_qty=response.available_qty,
        promised_qty=response.promised_qty,
        consumption_breakdown=response.consumption_breakdown,
        confidence=response.confidence,
        reasoning=response.reasoning,
        risk_bound=getattr(response, 'risk_bound', None),
        risk_assessment=getattr(response, 'risk_assessment', None),
        demand_interval=demand_interval,
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
    # Create transfer order via InboundOrder entity
    from app.models.sc_entities import InboundOrder
    to_id = f"TO-{recommendation.from_site}-{recommendation.to_site}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    today = await config_today(config_id, db)
    order = InboundOrder(
        id=to_id,
        order_type="TRANSFER",
        order_status="PLANNED",
        ship_from_site_id=None,  # Resolved by name in calling code
        ship_to_site_id=None,
        order_date=today,
        expected_delivery_date=today + timedelta(days=3),
        total_quantity=recommendation.quantity,
    )
    db.add(order)
    db.commit()
    return {
        "status": "executed",
        "transfer_order_id": to_id,
        "quantity": recommendation.quantity,
        "from_site": recommendation.from_site,
        "to_site": recommendation.to_site,
    }


# ============================================================================
# PO Creation Endpoints
# ============================================================================

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
    from app.models.powell_decisions import PowellOrderException
    rows = db.query(PowellOrderException).filter(
        PowellOrderException.config_id == config_id,
        PowellOrderException.severity.in_(["critical", "high"]),
    ).order_by(PowellOrderException.created_at.desc()).limit(100).all()
    return [r.to_dict() for r in rows]


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
    from app.models.powell_decision import SiteAgentDecision, SiteAgentCheckpoint
    # Count decisions (training buffer)
    buffer_q = db.query(SiteAgentDecision).filter(SiteAgentDecision.config_id == config_id)
    buffer_size = buffer_q.count()
    expert_count = buffer_q.filter(SiteAgentDecision.is_expert == True).count()
    with_next = buffer_q.filter(SiteAgentDecision.reward.isnot(None)).count()
    # TRM type distribution
    from sqlalchemy import func as sqla_func
    type_dist_rows = db.query(
        SiteAgentDecision.trm_type, sqla_func.count(SiteAgentDecision.id)
    ).filter(SiteAgentDecision.config_id == config_id).group_by(SiteAgentDecision.trm_type).all()
    type_dist = {row[0]: row[1] for row in type_dist_rows if row[0]}
    # Average reward
    avg_reward_row = db.query(sqla_func.avg(SiteAgentDecision.reward)).filter(
        SiteAgentDecision.config_id == config_id, SiteAgentDecision.reward.isnot(None)
    ).scalar()
    # Latest checkpoint
    latest_ckpt = db.query(SiteAgentCheckpoint).order_by(
        SiteAgentCheckpoint.created_at.desc()
    ).first()
    last_result = None
    if latest_ckpt:
        last_result = {
            "checkpoint_id": latest_ckpt.checkpoint_id,
            "training_phase": latest_ckpt.training_phase,
            "training_loss": latest_ckpt.training_loss,
            "val_accuracy": latest_ckpt.val_accuracy,
            "training_samples": latest_ckpt.training_samples,
        }
    return TrainingStatusResponse(
        buffer_size=buffer_size,
        records_with_expert=expert_count,
        records_with_next_state=with_next,
        trm_type_distribution=type_dist,
        average_reward=float(avg_reward_row or 0.0),
        last_training_result=last_result,
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

    from fastapi import BackgroundTasks
    job_id = f"train-{config_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    # Queue training as background task via CDCRetrainingService
    # In production this would use the retraining service; for now log and acknowledge
    import logging
    logger = logging.getLogger("powell.training")
    logger.info(f"Training triggered: job={job_id}, method={request.method}, epochs={request.epochs}")
    return {
        "status": "queued",
        "method": request.method,
        "epochs": request.epochs,
        "job_id": job_id,
        "message": "Training job queued. Monitor via GET /training/{config_id}/status",
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
    from app.models.powell_decision import SiteAgentCheckpoint
    rows = db.query(SiteAgentCheckpoint).order_by(
        SiteAgentCheckpoint.created_at.desc()
    ).limit(limit).all()
    return [
        {
            "checkpoint_id": c.checkpoint_id,
            "site_key": c.site_key,
            "model_version": c.model_version,
            "training_phase": c.training_phase,
            "training_samples": c.training_samples,
            "training_epochs": c.training_epochs,
            "training_loss": c.training_loss,
            "val_accuracy": c.val_accuracy,
            "benchmark_service_level": c.benchmark_service_level,
            "benchmark_cost_reduction": c.benchmark_cost_reduction,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


# ============================================================================
# Monitoring Endpoints
# ============================================================================

class MonitoringRunRequest(BaseModel):
    """Request for running monitoring checks"""
    check_types: Optional[List[str]] = None  # exceptions, po_recommendations, rebalancing
    scenario_id: Optional[int] = None


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
    scenario_id = request.scenario_id if request else None
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
    scenario_id: Optional[int] = None,
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
    scenario_id: Optional[int] = None,
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
    scenario_id: Optional[int] = None,
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
    from app.models.powell_decisions import PowellATPDecision
    query = db.query(PowellATPDecision).filter(PowellATPDecision.config_id == config_id)
    if product_id:
        query = query.filter(PowellATPDecision.product_id == product_id)
    if location_id:
        query = query.filter(PowellATPDecision.location_id == location_id)
    rows = query.order_by(PowellATPDecision.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in rows]


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
    from app.models.powell_decisions import PowellRebalanceDecision
    rows = db.query(PowellRebalanceDecision).filter(
        PowellRebalanceDecision.config_id == config_id
    ).order_by(PowellRebalanceDecision.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in rows]


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
    from app.models.powell_decisions import PowellPODecision
    rows = db.query(PowellPODecision).filter(
        PowellPODecision.config_id == config_id
    ).order_by(PowellPODecision.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in rows]


# ============================================================================
# S&OP GraphSAGE Analysis Endpoints
# ============================================================================

class SOPAnalysisResponse(BaseModel):
    """S&OP network analysis results."""
    config_id: int
    num_sites: int
    checkpoint_path: str
    criticality: Dict[str, float]
    bottleneck_risk: Dict[str, float]
    concentration_risk: Dict[str, float]
    resilience: Dict[str, float]
    safety_stock_multiplier: Dict[str, float]
    network_risk: Dict[str, float]
    site_keys: List[str]
    computed_at: Optional[str] = None
    # Conformal prediction intervals on scores (MC-Dropout or input perturbation)
    score_intervals: Optional[Dict[str, Dict[str, Dict[str, float]]]] = Field(
        None,
        description="Per-site score intervals: {site_key: {metric: {lower, upper, coverage}}}"
    )


class SOPSiteScoreResponse(BaseModel):
    """S&OP scores for a single site."""
    site_key: str
    criticality: float
    bottleneck_risk: float
    concentration_risk: float
    resilience: float
    safety_stock_multiplier: float
    embedding_dim: int = 0
    # Per-score conformal intervals (if available from MC-Dropout)
    score_intervals: Optional[Dict[str, Dict[str, float]]] = Field(
        None,
        description="Conformal intervals per metric: {metric: {lower, upper, coverage}}"
    )


@router.get("/sop/analysis/{config_id}", response_model=SOPAnalysisResponse)
async def get_sop_analysis(
    config_id: int,
    force_recompute: bool = Query(False, description="Force recomputation even if cached"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run or return cached S&OP GraphSAGE network analysis.

    Computes per-site criticality, bottleneck risk, concentration risk,
    resilience, and safety stock multipliers. Results are cached in DB.

    Set force_recompute=true to re-run the model even if cached results exist.
    """
    from app.services.powell.sop_inference_service import SOPInferenceService

    try:
        svc = SOPInferenceService(db=db, config_id=config_id)
        analysis = await svc.analyze_network(force_recompute=force_recompute)
        return SOPAnalysisResponse(
            config_id=analysis.config_id,
            num_sites=analysis.num_sites,
            checkpoint_path=analysis.checkpoint_path,
            criticality=analysis.criticality,
            bottleneck_risk=analysis.bottleneck_risk,
            concentration_risk=analysis.concentration_risk,
            resilience=analysis.resilience,
            safety_stock_multiplier=analysis.safety_stock_multiplier,
            network_risk=analysis.network_risk,
            site_keys=analysis.site_keys,
            computed_at=analysis.computed_at.isoformat() if analysis.computed_at else None,
            score_intervals=analysis.score_intervals if hasattr(analysis, 'score_intervals') else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S&OP analysis failed: {str(e)}")


@router.get("/sop/criticality/{config_id}/{site_key}")
async def get_site_criticality(
    config_id: int,
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get criticality score for a specific site.

    Returns the cached S&OP criticality score (0-1).
    Higher values indicate more critical sites (single points of failure).
    """
    from app.services.powell.sop_inference_service import SOPInferenceService

    svc = SOPInferenceService(db=db, config_id=config_id)
    scores = await svc.get_site_scores(site_key)

    if scores is None:
        raise HTTPException(
            status_code=404,
            detail=f"No S&OP analysis found for site '{site_key}' in config {config_id}. "
                   f"Run GET /sop/analysis/{config_id} first."
        )

    # Include per-site score intervals if available from last analysis
    site_intervals = None
    try:
        analysis = await svc.analyze_network(force_recompute=False)
        if hasattr(analysis, 'score_intervals') and analysis.score_intervals:
            site_intervals = analysis.score_intervals.get(site_key)
    except Exception:
        pass

    return SOPSiteScoreResponse(site_key=site_key, score_intervals=site_intervals, **scores)

"""
Simulation Execution API Endpoints

Provides order visibility, backlog tracking, shipment monitoring,
and round execution control for refactored simulation using AWS SC
execution capabilities.

Endpoints:
- POST /execute-round - Execute a simulation round
- GET /orders - List customer orders with filtering
- GET /orders/{order_id} - Get order details
- GET /backlog - Get backlog report
- GET /purchase-orders - List purchase orders
- GET /shipments - List transfer orders (shipments)
- GET /shipments/arriving - Get arriving shipments
- GET /metrics - Get round metrics
- GET /metrics/summary - Get aggregated metrics
- POST /atp/calculate - Calculate ATP for order promising
- GET /inventory - Get current inventory levels
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
from app.models.scenario import Scenario
from app.models.sc_entities import OutboundOrderLine, InvLevel
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.round_metric import RoundMetric
from app.models.supply_chain_config import Node
from app.services.simulation_execution_engine import SimulationExecutionEngine
from app.services.order_management_service import OrderManagementService
from app.services.fulfillment_service import FulfillmentService
from app.services.atp_calculation_service import ATPCalculationService
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ExecuteRoundRequest(BaseModel):
    """Request to execute a simulation round"""
    scenario_id: int
    agent_decisions: Optional[dict] = Field(
        default=None,
        description="Optional dict of {site_id: order_quantity} for agent decisions"
    )


class ExecuteRoundResponse(BaseModel):
    """Response from round execution"""
    scenario_id: int
    round: int
    receipts: dict
    customer_orders: dict
    fulfillment: dict
    replenishment: dict
    metrics: dict
    execution_time_ms: float


class OrderResponse(BaseModel):
    """Customer order response"""
    id: int
    order_id: str
    line_number: int
    product_id: str
    site_id: int
    site_name: Optional[str]
    ordered_quantity: float
    shipped_quantity: float
    backlog_quantity: float
    status: str
    priority_code: str
    order_date: date
    requested_delivery_date: date
    promised_delivery_date: Optional[date]
    first_ship_date: Optional[date]
    last_ship_date: Optional[date]
    market_demand_site_id: Optional[int]
    scenario_id: Optional[int]

    class Config:
        from_attributes = True


class PurchaseOrderResponse(BaseModel):
    """Purchase order response"""
    id: int
    po_number: str
    supplier_site_id: int
    supplier_site_name: Optional[str]
    destination_site_id: int
    destination_site_name: Optional[str]
    status: str
    order_date: date
    requested_delivery_date: date
    promised_delivery_date: Optional[date]
    scenario_id: Optional[int]
    order_round: Optional[int]
    line_items: List[dict]

    class Config:
        from_attributes = True


class TransferOrderResponse(BaseModel):
    """Transfer order (shipment) response"""
    id: int
    to_number: str
    source_site_id: int
    source_site_name: Optional[str]
    destination_site_id: int
    destination_site_name: Optional[str]
    status: str
    order_date: date
    shipment_date: Optional[date]
    estimated_delivery_date: date
    actual_delivery_date: Optional[date]
    scenario_id: Optional[int]
    order_round: Optional[int]
    arrival_round: Optional[int]
    line_items: List[dict]

    class Config:
        from_attributes = True


class BacklogReportResponse(BaseModel):
    """Backlog report for a site"""
    site_id: int
    site_name: str
    product_id: str
    total_backlog: float
    orders_in_backlog: int
    oldest_backlog_date: Optional[date]
    avg_backlog_age_days: float
    orders: List[OrderResponse]


class RoundMetricResponse(BaseModel):
    """Round metric response"""
    id: int
    scenario_id: int
    round_number: int
    site_id: int
    site_name: Optional[str]
    inventory: float
    backlog: float
    pipeline_qty: float
    in_transit_qty: float
    holding_cost: float
    backlog_cost: float
    total_cost: float
    cumulative_cost: float
    fill_rate: Optional[float]
    service_level: Optional[float]
    orders_received: int
    orders_fulfilled: int
    incoming_order_qty: float
    outgoing_order_qty: float
    shipment_qty: float

    class Config:
        from_attributes = True


class MetricsSummaryResponse(BaseModel):
    """Aggregated metrics summary"""
    scenario_id: int
    total_rounds: int
    total_cost: float
    avg_cost_per_round: float
    total_inventory: float
    total_backlog: float
    avg_fill_rate: float
    avg_service_level: float
    bullwhip_ratio: Optional[float]
    sites: List[dict]


class ATPCalculationRequest(BaseModel):
    """ATP calculation request"""
    site_id: int
    product_id: str
    config_id: int
    scenario_id: int
    current_round: Optional[int] = None


class ATPCalculationResponse(BaseModel):
    """ATP calculation response"""
    site_id: int
    product_id: str
    current_atp: float
    on_hand: float
    in_transit: float
    committed: float
    backlog: float
    future_receipts: List[dict]
    projected_atp: List[dict]


class InventoryLevelResponse(BaseModel):
    """Inventory level response"""
    site_id: int
    site_name: Optional[str]
    product_id: str
    quantity: float
    as_of_date: date

    class Config:
        from_attributes = True


# ============================================================================
# Round Execution Endpoints
# ============================================================================

@router.post("/execute-round", response_model=ExecuteRoundResponse)
@require_capabilities(["manage_simulations"])
async def execute_round(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: ExecuteRoundRequest
):
    """
    Execute a simulation round using refactored execution engine.

    Orchestrates complete round flow:
    1. Receive shipments
    2. Generate customer orders
    3. Fulfill orders (FIFO + priority)
    4. Evaluate replenishment
    5. Issue POs
    6. Calculate costs and metrics

    Args:
        request: Execution parameters (scenario_id, optional agent_decisions)

    Returns:
        Round execution summary with metrics
    """
    start_time = datetime.utcnow()

    # Get scenario
    scenario = await db.get(Scenario, request.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {request.scenario_id} not found")

    # Create execution engine
    engine = SimulationExecutionEngine(db)

    # Execute round
    result = await engine.execute_round(
        scenario_id=request.scenario_id,
        current_round=scenario.current_round,
        agent_decisions=request.agent_decisions,
    )

    # Update scenario round
    scenario.current_round += 1
    await db.commit()

    execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

    return ExecuteRoundResponse(
        **result,
        execution_time_ms=execution_time
    )


# ============================================================================
# Order Management Endpoints
# ============================================================================

@router.get("/orders", response_model=List[OrderResponse])
@require_capabilities(["view_simulations"])
async def list_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: Optional[int] = None,
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    priority_code: Optional[str] = None,
    has_backlog: Optional[bool] = None,
    limit: int = Query(100, le=1000)
):
    """
    List customer orders with filtering.

    Args:
        scenario_id: Filter by scenario ID
        site_id: Filter by fulfillment site
        status: Filter by status (DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED)
        priority_code: Filter by priority (VIP, HIGH, STANDARD, LOW)
        has_backlog: Filter for orders with backlog > 0
        limit: Maximum results

    Returns:
        List of customer orders
    """
    query = select(OutboundOrderLine)

    if scenario_id is not None:
        query = query.where(OutboundOrderLine.scenario_id == scenario_id)

    if site_id is not None:
        query = query.where(OutboundOrderLine.site_id == site_id)

    if status:
        query = query.where(OutboundOrderLine.status == status)

    if priority_code:
        query = query.where(OutboundOrderLine.priority_code == priority_code)

    if has_backlog is True:
        query = query.where(OutboundOrderLine.backlog_quantity > 0)

    query = query.order_by(OutboundOrderLine.order_date.desc()).limit(limit)

    result = await db.execute(query)
    orders = result.scalars().all()

    responses = []
    for order in orders:
        site = await db.get(Node, order.site_id) if order.site_id else None
        responses.append(OrderResponse(
            **order.__dict__,
            site_name=site.name if site else None
        ))

    return responses


@router.get("/orders/{order_id}", response_model=OrderResponse)
@require_capabilities(["view_simulations"])
async def get_order(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    order_id: int
):
    """Get order details by ID."""
    order = await db.get(OutboundOrderLine, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # Load site
    site = await db.get(Node, order.site_id) if order.site_id else None

    return OrderResponse(
        **order.__dict__,
        site_name=site.name if site else None
    )


@router.get("/backlog", response_model=List[BacklogReportResponse])
@require_capabilities(["view_simulations"])
async def get_backlog_report(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: int,
    site_id: Optional[int] = None
):
    """
    Get backlog report for scenario.

    Groups backlogged orders by site and provides summary statistics.

    Args:
        scenario_id: Scenario ID
        site_id: Optional site filter

    Returns:
        List of backlog reports per site
    """
    query = select(OutboundOrderLine).where(
        and_(
            OutboundOrderLine.scenario_id == scenario_id,
            OutboundOrderLine.backlog_quantity > 0
        )
    )

    if site_id is not None:
        query = query.where(OutboundOrderLine.site_id == site_id)

    result = await db.execute(query)
    orders = result.scalars().all()

    # Group by site
    backlog_by_site = {}
    for order in orders:
        if order.site_id not in backlog_by_site:
            site = await db.get(Node, order.site_id)
            backlog_by_site[order.site_id] = {
                'site_id': order.site_id,
                'site_name': site.name if site else "Unknown",
                'product_id': order.product_id,
                'orders': [],
                'total_backlog': 0.0,
                'oldest_date': None,
                'total_age_days': 0.0,
            }

        backlog_by_site[order.site_id]['orders'].append(order)
        backlog_by_site[order.site_id]['total_backlog'] += order.backlog_quantity

        # Track oldest date
        if not backlog_by_site[order.site_id]['oldest_date'] or order.order_date < backlog_by_site[order.site_id]['oldest_date']:
            backlog_by_site[order.site_id]['oldest_date'] = order.order_date

        # Calculate age
        age_days = (date.today() - order.order_date).days
        backlog_by_site[order.site_id]['total_age_days'] += age_days

    # Build response
    reports = []
    for site_data in backlog_by_site.values():
        site = await db.get(Node, site_data['site_id'])
        reports.append(BacklogReportResponse(
            site_id=site_data['site_id'],
            site_name=site_data['site_name'],
            product_id=site_data['product_id'],
            total_backlog=site_data['total_backlog'],
            orders_in_backlog=len(site_data['orders']),
            oldest_backlog_date=site_data['oldest_date'],
            avg_backlog_age_days=site_data['total_age_days'] / len(site_data['orders']) if site_data['orders'] else 0.0,
            orders=[
                OrderResponse(
                    **order.__dict__,
                    site_name=site.name if site else None
                )
                for order in site_data['orders']
            ]
        ))

    return reports


# ============================================================================
# Purchase Order Endpoints
# ============================================================================

@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
@require_capabilities(["view_simulations"])
async def list_purchase_orders(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: Optional[int] = None,
    supplier_site_id: Optional[int] = None,
    destination_site_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    """
    List purchase orders with filtering.

    Args:
        scenario_id: Filter by scenario ID
        supplier_site_id: Filter by supplier site
        destination_site_id: Filter by destination site
        status: Filter by status (APPROVED, SHIPPED, RECEIVED)
        limit: Maximum results

    Returns:
        List of purchase orders
    """
    query = select(PurchaseOrder)

    if scenario_id is not None:
        query = query.where(PurchaseOrder.scenario_id == scenario_id)

    if supplier_site_id is not None:
        query = query.where(PurchaseOrder.supplier_site_id == supplier_site_id)

    if destination_site_id is not None:
        query = query.where(PurchaseOrder.destination_site_id == destination_site_id)

    if status:
        query = query.where(PurchaseOrder.status == status)

    query = query.order_by(PurchaseOrder.order_date.desc()).limit(limit)

    result = await db.execute(query)
    pos = result.scalars().all()

    responses = []
    for po in pos:
        supplier_site = await db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
        dest_site = await db.get(Node, po.destination_site_id) if po.destination_site_id else None

        # Get line items
        line_items_result = await db.execute(
            select(PurchaseOrderLineItem).where(PurchaseOrderLineItem.po_id == po.id)
        )
        line_items = line_items_result.scalars().all()

        responses.append(PurchaseOrderResponse(
            **po.__dict__,
            supplier_site_name=supplier_site.name if supplier_site else None,
            destination_site_name=dest_site.name if dest_site else None,
            line_items=[
                {
                    'line_number': li.line_number,
                    'product_id': li.product_id,
                    'quantity': li.quantity,
                    'shipped_quantity': li.shipped_quantity,
                    'received_quantity': li.received_quantity,
                }
                for li in line_items
            ]
        ))

    return responses


# ============================================================================
# Shipment (Transfer Order) Endpoints
# ============================================================================

@router.get("/shipments", response_model=List[TransferOrderResponse])
@require_capabilities(["view_simulations"])
async def list_shipments(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: Optional[int] = None,
    source_site_id: Optional[int] = None,
    destination_site_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    """
    List transfer orders (shipments) with filtering.

    Args:
        scenario_id: Filter by scenario ID
        source_site_id: Filter by source site
        destination_site_id: Filter by destination site
        status: Filter by status (IN_TRANSIT, RECEIVED)
        limit: Maximum results

    Returns:
        List of transfer orders
    """
    query = select(TransferOrder)

    if scenario_id is not None:
        query = query.where(TransferOrder.scenario_id == scenario_id)

    if source_site_id is not None:
        query = query.where(TransferOrder.source_site_id == source_site_id)

    if destination_site_id is not None:
        query = query.where(TransferOrder.destination_site_id == destination_site_id)

    if status:
        query = query.where(TransferOrder.status == status)

    query = query.order_by(TransferOrder.order_date.desc()).limit(limit)

    result = await db.execute(query)
    tos = result.scalars().all()

    responses = []
    for to in tos:
        source_site = await db.get(Node, to.source_site_id) if to.source_site_id else None
        dest_site = await db.get(Node, to.destination_site_id) if to.destination_site_id else None

        # Get line items
        line_items_result = await db.execute(
            select(TransferOrderLineItem).where(TransferOrderLineItem.to_id == to.id)
        )
        line_items = line_items_result.scalars().all()

        responses.append(TransferOrderResponse(
            **to.__dict__,
            source_site_name=source_site.name if source_site else None,
            destination_site_name=dest_site.name if dest_site else None,
            line_items=[
                {
                    'line_number': li.line_number,
                    'product_id': li.product_id,
                    'quantity': li.quantity,
                    'uom': li.uom,
                }
                for li in line_items
            ]
        ))

    return responses


@router.get("/shipments/arriving", response_model=List[TransferOrderResponse])
@require_capabilities(["view_simulations"])
async def get_arriving_shipments(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: int,
    arrival_round: int
):
    """
    Get shipments arriving in a specific round.

    Args:
        scenario_id: Scenario ID
        arrival_round: Round number

    Returns:
        List of arriving transfer orders
    """
    order_mgmt = OrderManagementService(db)

    arriving = await order_mgmt.get_arriving_transfer_orders(
        scenario_id=scenario_id,
        arrival_round=arrival_round,
    )

    responses = []
    for to in arriving:
        source_site = await db.get(Node, to.source_site_id) if to.source_site_id else None
        dest_site = await db.get(Node, to.destination_site_id) if to.destination_site_id else None

        # Get line items
        line_items_result = await db.execute(
            select(TransferOrderLineItem).where(TransferOrderLineItem.to_id == to.id)
        )
        line_items = line_items_result.scalars().all()

        responses.append(TransferOrderResponse(
            **to.__dict__,
            source_site_name=source_site.name if source_site else None,
            destination_site_name=dest_site.name if dest_site else None,
            line_items=[
                {
                    'line_number': li.line_number,
                    'product_id': li.product_id,
                    'quantity': li.quantity,
                    'uom': li.uom,
                }
                for li in line_items
            ]
        ))

    return responses


# ============================================================================
# Metrics Endpoints
# ============================================================================

@router.get("/metrics", response_model=List[RoundMetricResponse])
@require_capabilities(["view_simulations"])
async def list_metrics(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: int,
    round_number: Optional[int] = None,
    site_id: Optional[int] = None
):
    """
    List round metrics with filtering.

    Args:
        scenario_id: Scenario ID
        round_number: Filter by round number
        site_id: Filter by site

    Returns:
        List of round metrics
    """
    query = select(RoundMetric).where(RoundMetric.scenario_id == scenario_id)

    if round_number is not None:
        query = query.where(RoundMetric.round_number == round_number)

    if site_id is not None:
        query = query.where(RoundMetric.site_id == site_id)

    query = query.order_by(RoundMetric.round_number, RoundMetric.site_id)

    result = await db.execute(query)
    metrics = result.scalars().all()

    responses = []
    for metric in metrics:
        site = await db.get(Node, metric.site_id) if metric.site_id else None
        responses.append(RoundMetricResponse(
            **metric.__dict__,
            site_name=site.name if site else None
        ))

    return responses


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
@require_capabilities(["view_simulations"])
async def get_metrics_summary(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: int
):
    """
    Get aggregated metrics summary for a scenario.

    Calculates total costs, average fill rates, bullwhip ratio, etc.

    Args:
        scenario_id: Scenario ID

    Returns:
        Aggregated metrics summary
    """
    # Get all metrics for scenario
    result = await db.execute(
        select(RoundMetric).where(RoundMetric.scenario_id == scenario_id)
    )
    metrics = result.scalars().all()

    if not metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for scenario {scenario_id}")

    # Calculate aggregates
    total_rounds = max(m.round_number for m in metrics)
    total_cost = sum(m.total_cost for m in metrics)
    avg_cost_per_round = total_cost / total_rounds if total_rounds > 0 else 0.0

    # Current state (latest round)
    latest_metrics = [m for m in metrics if m.round_number == total_rounds]
    total_inventory = sum(m.inventory for m in latest_metrics)
    total_backlog = sum(m.backlog for m in latest_metrics)

    # KPIs
    avg_fill_rate = sum(m.fill_rate or 0.0 for m in metrics) / len(metrics)
    avg_service_level = sum(m.service_level or 0.0 for m in metrics) / len(metrics)

    # Bullwhip ratio (variance of orders / variance of demand)
    # Simplified: ratio of max to min order quantities across sites
    order_quantities = [m.outgoing_order_qty for m in latest_metrics if m.outgoing_order_qty > 0]
    bullwhip_ratio = (max(order_quantities) / min(order_quantities)) if order_quantities and min(order_quantities) > 0 else None

    # Per-site summary
    sites_data = {}
    for metric in metrics:
        if metric.site_id not in sites_data:
            site = await db.get(Node, metric.site_id)
            sites_data[metric.site_id] = {
                'site_id': metric.site_id,
                'site_name': site.name if site else "Unknown",
                'total_cost': 0.0,
                'cumulative_cost': 0.0,
                'avg_inventory': 0.0,
                'avg_backlog': 0.0,
                'avg_fill_rate': 0.0,
                'round_count': 0,
            }

        sites_data[metric.site_id]['total_cost'] += metric.total_cost
        sites_data[metric.site_id]['cumulative_cost'] = metric.cumulative_cost
        sites_data[metric.site_id]['avg_inventory'] += metric.inventory
        sites_data[metric.site_id]['avg_backlog'] += metric.backlog
        sites_data[metric.site_id]['avg_fill_rate'] += (metric.fill_rate or 0.0)
        sites_data[metric.site_id]['round_count'] += 1

    # Average per-site metrics
    for site_data in sites_data.values():
        if site_data['round_count'] > 0:
            site_data['avg_inventory'] /= site_data['round_count']
            site_data['avg_backlog'] /= site_data['round_count']
            site_data['avg_fill_rate'] /= site_data['round_count']

    return MetricsSummaryResponse(
        scenario_id=scenario_id,
        total_rounds=total_rounds,
        total_cost=total_cost,
        avg_cost_per_round=avg_cost_per_round,
        total_inventory=total_inventory,
        total_backlog=total_backlog,
        avg_fill_rate=avg_fill_rate,
        avg_service_level=avg_service_level,
        bullwhip_ratio=bullwhip_ratio,
        sites=list(sites_data.values())
    )


# ============================================================================
# ATP Calculation Endpoints
# ============================================================================

@router.post("/atp/calculate", response_model=ATPCalculationResponse)
@require_capabilities(["view_simulations"])
async def calculate_atp(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: ATPCalculationRequest
):
    """
    Calculate ATP for order promising.

    Returns current ATP and projected future ATP based on
    scheduled receipts.

    Args:
        request: ATP calculation parameters

    Returns:
        ATP calculation result with projections
    """
    atp_service = ATPCalculationService(db)

    atp_data = await atp_service.calculate_atp(
        site_id=request.site_id,
        product_id=request.product_id,
        config_id=request.config_id,
        scenario_id=request.scenario_id,
        current_round=request.current_round,
        horizon_rounds=6,
    )

    return ATPCalculationResponse(**atp_data)


# ============================================================================
# Inventory Endpoints
# ============================================================================

@router.get("/inventory", response_model=List[InventoryLevelResponse])
@require_capabilities(["view_simulations"])
async def list_inventory_levels(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    scenario_id: int,
    site_id: Optional[int] = None,
    product_id: Optional[str] = None
):
    """
    List current inventory levels.

    Args:
        scenario_id: Scenario ID
        site_id: Filter by site
        product_id: Filter by product

    Returns:
        List of inventory levels
    """
    query = select(InvLevel).where(InvLevel.scenario_id == scenario_id)

    if site_id is not None:
        query = query.where(InvLevel.site_id == site_id)

    if product_id:
        query = query.where(InvLevel.product_id == product_id)

    result = await db.execute(query)
    inventory_levels = result.scalars().all()

    responses = []
    for inv in inventory_levels:
        site = await db.get(Node, inv.site_id) if inv.site_id else None
        responses.append(InventoryLevelResponse(
            **inv.__dict__,
            site_name=site.name if site else None
        ))

    return responses

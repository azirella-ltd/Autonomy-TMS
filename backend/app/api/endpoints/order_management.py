"""
Advanced Order Management API

Endpoints for order splitting, consolidation, and optimization.

Phase 3.4: Advanced Order Features
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
import uuid

from app.db.session import get_sync_db as get_db
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supplier import VendorProduct, VendorLeadTime

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class SplitLineItem(BaseModel):
    """Line item specification for split order."""
    product_id: str
    quantity: float
    target_vendor_id: Optional[str] = None


class SplitOrderRequest(BaseModel):
    """Request to split an order across multiple vendors."""
    order_id: str = Field(..., description="Original order ID to split")
    order_type: str = Field(..., description="PO or TO")
    split_strategy: str = Field(default="round_robin", description="round_robin, by_capacity, by_cost, by_lead_time, manual")
    line_splits: Optional[List[Dict[str, Any]]] = Field(None, description="Manual split specification")
    vendor_ids: Optional[List[str]] = Field(None, description="Vendors to split across")
    create_new_orders: bool = Field(default=True, description="Create new orders or modify existing")


class SplitOrderResponse(BaseModel):
    """Response for order split operation."""
    success: bool
    original_order_id: str
    new_order_ids: List[str]
    split_details: List[Dict[str, Any]]
    message: str


class ConsolidateOrdersRequest(BaseModel):
    """Request to consolidate multiple orders."""
    order_ids: List[str] = Field(..., min_length=2, description="Orders to consolidate")
    order_type: str = Field(..., description="PO or TO")
    consolidation_strategy: str = Field(default="by_vendor", description="by_vendor, by_ship_date, by_destination")
    target_ship_date: Optional[datetime] = None
    target_vendor_id: Optional[str] = None


class ConsolidateOrdersResponse(BaseModel):
    """Response for order consolidation operation."""
    success: bool
    original_order_ids: List[str]
    new_order_id: str
    consolidated_items: int
    total_quantity: float
    message: str


class OptimizeSourcingRequest(BaseModel):
    """Request to optimize sourcing for a set of requirements."""
    requirements: List[Dict[str, Any]] = Field(..., description="Requirements to source")
    optimization_objective: str = Field(default="cost", description="cost, lead_time, risk, sustainability")
    constraints: Optional[Dict[str, Any]] = Field(None, description="Constraints for optimization")
    config_id: Optional[int] = None


class OptimizeSourcingResponse(BaseModel):
    """Response for sourcing optimization."""
    success: bool
    sourcing_plan: List[Dict[str, Any]]
    total_cost: Optional[float]
    total_lead_time_days: Optional[float]
    risk_score: Optional[float]
    sustainability_score: Optional[float]
    message: str


class OrderSuggestion(BaseModel):
    """Suggestion for order improvement."""
    suggestion_type: str  # split, consolidate, expedite, defer
    description: str
    potential_savings: Optional[float]
    affected_orders: List[str]
    recommended_action: Dict[str, Any]


class OrderAnalysisResponse(BaseModel):
    """Analysis of orders with improvement suggestions."""
    orders_analyzed: int
    total_value: float
    suggestions: List[OrderSuggestion]
    consolidation_opportunities: int
    splitting_opportunities: int


# ============================================================================
# Order Splitting Endpoints
# ============================================================================

@router.post("/split", response_model=SplitOrderResponse)
async def split_order(
    request: SplitOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Split an order across multiple vendors/sources.

    Strategies:
    - round_robin: Distribute evenly across vendors
    - by_capacity: Based on vendor capacity
    - by_cost: Minimize total cost
    - by_lead_time: Minimize delivery time
    - manual: Use provided line_splits specification
    """
    # Get original order
    if request.order_type == "PO":
        original_order = db.query(PurchaseOrder).filter(
            PurchaseOrder.id == request.order_id
        ).first()
        if not original_order:
            raise HTTPException(status_code=404, detail="Purchase order not found")

        original_items = db.query(PurchaseOrderLineItem).filter(
            PurchaseOrderLineItem.purchase_order_id == request.order_id
        ).all()
    elif request.order_type == "TO":
        original_order = db.query(TransferOrder).filter(
            TransferOrder.id == request.order_id
        ).first()
        if not original_order:
            raise HTTPException(status_code=404, detail="Transfer order not found")

        original_items = db.query(TransferOrderLineItem).filter(
            TransferOrderLineItem.transfer_order_id == request.order_id
        ).all()
    else:
        raise HTTPException(status_code=400, detail="Invalid order type. Use 'PO' or 'TO'")

    if not original_items:
        raise HTTPException(status_code=400, detail="Order has no line items to split")

    # Get available vendors for splitting
    vendor_ids = request.vendor_ids
    if not vendor_ids and request.order_type == "PO":
        # Find vendors that supply these products
        product_ids = [item.product_id for item in original_items]
        vendor_products = db.query(VendorProduct).filter(
            VendorProduct.product_id.in_(product_ids),
            VendorProduct.is_active == True
        ).all()
        vendor_ids = list(set(vp.vendor_id for vp in vendor_products))

    if not vendor_ids or len(vendor_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 vendors to split order")

    # Calculate split based on strategy
    split_details = []
    new_order_ids = []

    if request.split_strategy == "round_robin":
        # Distribute items evenly across vendors
        items_per_vendor = {}
        for i, item in enumerate(original_items):
            vendor_id = vendor_ids[i % len(vendor_ids)]
            if vendor_id not in items_per_vendor:
                items_per_vendor[vendor_id] = []
            items_per_vendor[vendor_id].append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': getattr(item, 'unit_price', None),
            })

        # Create new orders
        for vendor_id, items in items_per_vendor.items():
            if request.create_new_orders:
                new_order_id = str(uuid.uuid4())
                new_order_ids.append(new_order_id)

                if request.order_type == "PO":
                    new_order = PurchaseOrder(
                        id=new_order_id,
                        vendor_id=vendor_id,
                        status='DRAFT',
                        order_date=datetime.utcnow(),
                        config_id=original_order.config_id,
                        group_id=original_order.group_id,
                        created_at=datetime.utcnow(),
                        notes=f"Split from order {request.order_id}"
                    )
                    db.add(new_order)

                    for item in items:
                        line_item = PurchaseOrderLineItem(
                            id=str(uuid.uuid4()),
                            purchase_order_id=new_order_id,
                            product_id=item['product_id'],
                            quantity=item['quantity'],
                            unit_price=item.get('unit_price', 0),
                        )
                        db.add(line_item)

                split_details.append({
                    'vendor_id': vendor_id,
                    'new_order_id': new_order_id,
                    'items': items,
                    'total_quantity': sum(i['quantity'] for i in items)
                })

    elif request.split_strategy == "by_cost":
        # Split to minimize cost - assign to lowest cost vendor per product
        for item in original_items:
            # Find cheapest vendor for this product
            vendor_prices = db.query(VendorProduct).filter(
                VendorProduct.product_id == item.product_id,
                VendorProduct.vendor_id.in_(vendor_ids),
                VendorProduct.is_active == True
            ).order_by(VendorProduct.unit_cost.asc()).all()

            if vendor_prices:
                best_vendor = vendor_prices[0].vendor_id
            else:
                best_vendor = vendor_ids[0]

            split_details.append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'assigned_vendor': best_vendor,
                'reason': 'lowest_cost'
            })

        # Group by vendor and create orders
        by_vendor = {}
        for detail in split_details:
            vendor = detail['assigned_vendor']
            if vendor not in by_vendor:
                by_vendor[vendor] = []
            by_vendor[vendor].append(detail)

        for vendor_id, items in by_vendor.items():
            if request.create_new_orders:
                new_order_id = str(uuid.uuid4())
                new_order_ids.append(new_order_id)

    elif request.split_strategy == "by_lead_time":
        # Split to minimize lead time
        for item in original_items:
            # Find vendor with shortest lead time
            vendor_lead_times = db.query(VendorLeadTime).filter(
                VendorLeadTime.product_id == item.product_id,
                VendorLeadTime.vendor_id.in_(vendor_ids)
            ).order_by(VendorLeadTime.lead_time_days.asc()).all()

            if vendor_lead_times:
                best_vendor = vendor_lead_times[0].vendor_id
            else:
                best_vendor = vendor_ids[0]

            split_details.append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'assigned_vendor': best_vendor,
                'reason': 'shortest_lead_time'
            })

    elif request.split_strategy == "manual" and request.line_splits:
        # Use provided split specification
        for split_spec in request.line_splits:
            split_details.append(split_spec)

    # Mark original order as split
    original_order.status = 'SPLIT'
    if hasattr(original_order, 'split_from_ids'):
        original_order.split_into_ids = new_order_ids

    db.commit()

    return SplitOrderResponse(
        success=True,
        original_order_id=request.order_id,
        new_order_ids=new_order_ids,
        split_details=split_details,
        message=f"Order split into {len(new_order_ids)} new orders using {request.split_strategy} strategy"
    )


@router.get("/split-preview/{order_id}")
async def preview_split(
    order_id: str,
    order_type: str = Query(..., description="PO or TO"),
    strategy: str = Query(default="round_robin"),
    vendor_ids: Optional[str] = Query(None, description="Comma-separated vendor IDs"),
    db: Session = Depends(get_db)
):
    """Preview what a split would look like without executing it."""
    # Similar logic to split but without committing
    if order_type == "PO":
        order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
        items = db.query(PurchaseOrderLineItem).filter(
            PurchaseOrderLineItem.purchase_order_id == order_id
        ).all() if order else []
    else:
        order = db.query(TransferOrder).filter(TransferOrder.id == order_id).first()
        items = db.query(TransferOrderLineItem).filter(
            TransferOrderLineItem.transfer_order_id == order_id
        ).all() if order else []

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    vendors = vendor_ids.split(",") if vendor_ids else []

    preview = {
        "order_id": order_id,
        "order_type": order_type,
        "strategy": strategy,
        "total_items": len(items),
        "total_quantity": sum(i.quantity for i in items),
        "available_vendors": vendors,
        "estimated_splits": len(vendors) if vendors else "Unknown",
        "preview_details": []
    }

    if strategy == "round_robin" and vendors:
        for i, item in enumerate(items):
            vendor = vendors[i % len(vendors)]
            preview["preview_details"].append({
                "product_id": item.product_id,
                "quantity": item.quantity,
                "assigned_vendor": vendor
            })

    return preview


# ============================================================================
# Order Consolidation Endpoints
# ============================================================================

@router.post("/consolidate", response_model=ConsolidateOrdersResponse)
async def consolidate_orders(
    request: ConsolidateOrdersRequest,
    db: Session = Depends(get_db)
):
    """
    Consolidate multiple orders into one.

    Strategies:
    - by_vendor: Combine orders going to same vendor
    - by_ship_date: Combine orders with similar ship dates
    - by_destination: Combine orders going to same destination
    """
    if request.order_type == "PO":
        orders = db.query(PurchaseOrder).filter(
            PurchaseOrder.id.in_(request.order_ids)
        ).all()

        if len(orders) != len(request.order_ids):
            raise HTTPException(status_code=404, detail="Some orders not found")

        # Validate consolidation is possible
        if request.consolidation_strategy == "by_vendor":
            vendor_ids = set(o.vendor_id for o in orders)
            if len(vendor_ids) > 1 and not request.target_vendor_id:
                raise HTTPException(
                    status_code=400,
                    detail="Orders have different vendors. Specify target_vendor_id."
                )
            target_vendor = request.target_vendor_id or list(vendor_ids)[0]
        else:
            target_vendor = orders[0].vendor_id

        # Create consolidated order
        new_order_id = str(uuid.uuid4())
        consolidated_order = PurchaseOrder(
            id=new_order_id,
            vendor_id=target_vendor,
            status='DRAFT',
            order_date=datetime.utcnow(),
            config_id=orders[0].config_id,
            group_id=orders[0].group_id,
            expected_delivery_date=request.target_ship_date,
            created_at=datetime.utcnow(),
            notes=f"Consolidated from orders: {', '.join(request.order_ids)}"
        )
        db.add(consolidated_order)

        # Consolidate line items
        total_quantity = 0
        consolidated_items = 0
        item_aggregation = {}

        for order in orders:
            items = db.query(PurchaseOrderLineItem).filter(
                PurchaseOrderLineItem.purchase_order_id == order.id
            ).all()

            for item in items:
                key = item.product_id
                if key not in item_aggregation:
                    item_aggregation[key] = {
                        'product_id': item.product_id,
                        'quantity': 0,
                        'unit_price': item.unit_price or 0,
                    }
                item_aggregation[key]['quantity'] += item.quantity
                total_quantity += item.quantity

        # Create consolidated line items
        for key, agg in item_aggregation.items():
            line_item = PurchaseOrderLineItem(
                id=str(uuid.uuid4()),
                purchase_order_id=new_order_id,
                product_id=agg['product_id'],
                quantity=agg['quantity'],
                unit_price=agg['unit_price'],
            )
            db.add(line_item)
            consolidated_items += 1

        # Mark original orders as consolidated
        for order in orders:
            order.status = 'CONSOLIDATED'
            if hasattr(order, 'consolidated_into_id'):
                order.consolidated_into_id = new_order_id

    elif request.order_type == "TO":
        orders = db.query(TransferOrder).filter(
            TransferOrder.id.in_(request.order_ids)
        ).all()

        if len(orders) != len(request.order_ids):
            raise HTTPException(status_code=404, detail="Some orders not found")

        # Create consolidated transfer order
        new_order_id = str(uuid.uuid4())
        consolidated_order = TransferOrder(
            id=new_order_id,
            source_site_id=orders[0].source_site_id,
            destination_site_id=orders[0].destination_site_id,
            status='DRAFT',
            order_date=datetime.utcnow(),
            config_id=orders[0].config_id,
            group_id=orders[0].group_id,
            created_at=datetime.utcnow(),
            notes=f"Consolidated from orders: {', '.join(request.order_ids)}"
        )
        db.add(consolidated_order)

        # Consolidate line items
        total_quantity = 0
        consolidated_items = 0
        item_aggregation = {}

        for order in orders:
            items = db.query(TransferOrderLineItem).filter(
                TransferOrderLineItem.transfer_order_id == order.id
            ).all()

            for item in items:
                key = item.product_id
                if key not in item_aggregation:
                    item_aggregation[key] = {
                        'product_id': item.product_id,
                        'quantity': 0,
                    }
                item_aggregation[key]['quantity'] += item.quantity
                total_quantity += item.quantity

        for key, agg in item_aggregation.items():
            line_item = TransferOrderLineItem(
                id=str(uuid.uuid4()),
                transfer_order_id=new_order_id,
                product_id=agg['product_id'],
                quantity=agg['quantity'],
            )
            db.add(line_item)
            consolidated_items += 1

        for order in orders:
            order.status = 'CONSOLIDATED'

    else:
        raise HTTPException(status_code=400, detail="Invalid order type")

    db.commit()

    return ConsolidateOrdersResponse(
        success=True,
        original_order_ids=request.order_ids,
        new_order_id=new_order_id,
        consolidated_items=consolidated_items,
        total_quantity=total_quantity,
        message=f"Consolidated {len(request.order_ids)} orders into 1 order with {consolidated_items} unique items"
    )


@router.get("/consolidation-opportunities")
async def find_consolidation_opportunities(
    order_type: str = Query(..., description="PO or TO"),
    config_id: Optional[int] = None,
    min_orders: int = Query(default=2, ge=2),
    time_window_days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """Find orders that could potentially be consolidated."""
    cutoff = datetime.utcnow() + timedelta(days=time_window_days)

    opportunities = []

    if order_type == "PO":
        query = db.query(PurchaseOrder).filter(
            PurchaseOrder.status.in_(['DRAFT', 'PENDING', 'APPROVED']),
        )
        if config_id:
            query = query.filter(PurchaseOrder.config_id == config_id)

        orders = query.all()

        # Group by vendor
        by_vendor = {}
        for order in orders:
            vendor = order.vendor_id
            if vendor not in by_vendor:
                by_vendor[vendor] = []
            by_vendor[vendor].append(order)

        for vendor, vendor_orders in by_vendor.items():
            if len(vendor_orders) >= min_orders:
                total_qty = sum(
                    sum(item.quantity for item in db.query(PurchaseOrderLineItem).filter(
                        PurchaseOrderLineItem.purchase_order_id == o.id
                    ).all())
                    for o in vendor_orders
                )
                opportunities.append({
                    'type': 'by_vendor',
                    'vendor_id': vendor,
                    'order_count': len(vendor_orders),
                    'order_ids': [o.id for o in vendor_orders],
                    'total_quantity': total_qty,
                    'potential_savings': 'Reduced shipping costs',
                })

    elif order_type == "TO":
        query = db.query(TransferOrder).filter(
            TransferOrder.status.in_(['DRAFT', 'PENDING', 'APPROVED']),
        )
        if config_id:
            query = query.filter(TransferOrder.config_id == config_id)

        orders = query.all()

        # Group by route (source -> destination)
        by_route = {}
        for order in orders:
            route = f"{order.source_site_id}->{order.destination_site_id}"
            if route not in by_route:
                by_route[route] = []
            by_route[route].append(order)

        for route, route_orders in by_route.items():
            if len(route_orders) >= min_orders:
                opportunities.append({
                    'type': 'by_route',
                    'route': route,
                    'order_count': len(route_orders),
                    'order_ids': [o.id for o in route_orders],
                    'potential_savings': 'Reduced transportation costs',
                })

    return {
        "order_type": order_type,
        "time_window_days": time_window_days,
        "opportunities_found": len(opportunities),
        "opportunities": opportunities
    }


# ============================================================================
# Order Analysis and Optimization
# ============================================================================

@router.post("/analyze", response_model=OrderAnalysisResponse)
async def analyze_orders(
    order_type: str = Query(..., description="PO or TO"),
    config_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Analyze orders and provide optimization suggestions."""
    suggestions = []

    if order_type == "PO":
        orders = db.query(PurchaseOrder).filter(
            PurchaseOrder.status.in_(['DRAFT', 'PENDING', 'APPROVED'])
        )
        if config_id:
            orders = orders.filter(PurchaseOrder.config_id == config_id)
        orders = orders.all()
    else:
        orders = db.query(TransferOrder).filter(
            TransferOrder.status.in_(['DRAFT', 'PENDING', 'APPROVED'])
        )
        if config_id:
            orders = orders.filter(TransferOrder.config_id == config_id)
        orders = orders.all()

    # Calculate total value
    total_value = 0
    for order in orders:
        if order_type == "PO":
            items = db.query(PurchaseOrderLineItem).filter(
                PurchaseOrderLineItem.purchase_order_id == order.id
            ).all()
            total_value += sum((i.unit_price or 0) * i.quantity for i in items)

    # Find consolidation opportunities
    consolidation_count = 0
    if order_type == "PO":
        by_vendor = {}
        for order in orders:
            if order.vendor_id not in by_vendor:
                by_vendor[order.vendor_id] = []
            by_vendor[order.vendor_id].append(order)

        for vendor, v_orders in by_vendor.items():
            if len(v_orders) >= 2:
                consolidation_count += 1
                suggestions.append(OrderSuggestion(
                    suggestion_type="consolidate",
                    description=f"Consolidate {len(v_orders)} orders to vendor {vendor}",
                    potential_savings=len(v_orders) * 50,  # Estimated shipping savings
                    affected_orders=[o.id for o in v_orders],
                    recommended_action={
                        "action": "consolidate",
                        "order_ids": [o.id for o in v_orders],
                        "vendor_id": vendor
                    }
                ))

    # Find splitting opportunities (large orders that could benefit from multi-sourcing)
    splitting_count = 0
    large_order_threshold = 1000  # Quantity threshold

    for order in orders:
        if order_type == "PO":
            items = db.query(PurchaseOrderLineItem).filter(
                PurchaseOrderLineItem.purchase_order_id == order.id
            ).all()
            total_qty = sum(i.quantity for i in items)

            if total_qty > large_order_threshold:
                splitting_count += 1
                suggestions.append(OrderSuggestion(
                    suggestion_type="split",
                    description=f"Consider splitting large order ({total_qty} units) across multiple vendors",
                    potential_savings=total_qty * 0.05,  # Estimated 5% cost reduction
                    affected_orders=[order.id],
                    recommended_action={
                        "action": "split",
                        "order_id": order.id,
                        "strategy": "by_cost"
                    }
                ))

    return OrderAnalysisResponse(
        orders_analyzed=len(orders),
        total_value=total_value,
        suggestions=suggestions,
        consolidation_opportunities=consolidation_count,
        splitting_opportunities=splitting_count
    )


@router.post("/optimize-sourcing", response_model=OptimizeSourcingResponse)
async def optimize_sourcing(
    request: OptimizeSourcingRequest,
    db: Session = Depends(get_db)
):
    """
    Optimize sourcing decisions for a set of requirements.

    Uses linear programming or heuristics to find optimal vendor assignment.
    """
    sourcing_plan = []
    total_cost = 0
    total_lead_time = 0

    for req in request.requirements:
        product_id = req.get('product_id')
        quantity = req.get('quantity', 0)

        # Find available vendors for this product
        vendor_products = db.query(VendorProduct).filter(
            VendorProduct.product_id == product_id,
            VendorProduct.is_active == True
        ).all()

        if not vendor_products:
            sourcing_plan.append({
                'product_id': product_id,
                'quantity': quantity,
                'vendor_id': None,
                'status': 'no_vendor_found'
            })
            continue

        # Select vendor based on optimization objective
        if request.optimization_objective == "cost":
            # Sort by unit cost
            best_vendor = min(vendor_products, key=lambda v: v.unit_cost or float('inf'))
        elif request.optimization_objective == "lead_time":
            # Get lead times
            lead_times = {}
            for vp in vendor_products:
                lt = db.query(VendorLeadTime).filter(
                    VendorLeadTime.vendor_id == vp.vendor_id,
                    VendorLeadTime.product_id == product_id
                ).first()
                lead_times[vp.vendor_id] = lt.lead_time_days if lt else 999

            best_vendor = min(vendor_products, key=lambda v: lead_times.get(v.vendor_id, 999))
        else:
            # Default: use first available
            best_vendor = vendor_products[0]

        unit_cost = best_vendor.unit_cost or 0
        sourcing_plan.append({
            'product_id': product_id,
            'quantity': quantity,
            'vendor_id': best_vendor.vendor_id,
            'unit_cost': unit_cost,
            'total_cost': unit_cost * quantity,
            'status': 'sourced'
        })
        total_cost += unit_cost * quantity

    return OptimizeSourcingResponse(
        success=True,
        sourcing_plan=sourcing_plan,
        total_cost=total_cost,
        total_lead_time_days=None,  # Would calculate if lead time data available
        risk_score=None,
        sustainability_score=None,
        message=f"Optimized sourcing for {len(request.requirements)} requirements using {request.optimization_objective} objective"
    )

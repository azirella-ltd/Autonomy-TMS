"""
Purchase Order (PO) API Endpoints

Provides functionality for:
- Creating purchase orders from MRP planned orders
- Managing PO lifecycle (draft, submitted, approved, received)
- PO acknowledgment and tracking
- Vendor management integration
"""

from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.sc_entities import SupplyPlan
from app.models.supply_chain_config import Node
from app.models.sc_entities import Product
from app.models.purchase_order import (
    PurchaseOrder as PurchaseOrderModel,
    PurchaseOrderLineItem as PurchaseOrderLineItemModel,
)
from app.models.goods_receipt import (
    GoodsReceipt as GoodsReceiptModel,
    GoodsReceiptLineItem as GoodsReceiptLineItemModel,
)
from sqlalchemy import func
import uuid


# ============================================================================
# Request/Response Schemas
# ============================================================================

class PurchaseOrderLineItem(BaseModel):
    """Individual line item in a purchase order"""
    line_number: int
    product_id: int
    product_name: str
    quantity: float
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    requested_delivery_date: date
    promised_delivery_date: Optional[date] = None


class CreatePurchaseOrderRequest(BaseModel):
    """Request to create a purchase order"""
    vendor_id: Optional[str] = Field(None, description="Vendor identifier")
    supplier_site_id: int = Field(..., description="Supplier node ID")
    destination_site_id: int = Field(..., description="Receiving site ID")
    order_date: date = Field(..., description="Order placement date")
    line_items: List[PurchaseOrderLineItem] = Field(
        ...,
        min_length=1,
        description="Line items to order"
    )
    notes: Optional[str] = None


class CreatePOFromMRPRequest(BaseModel):
    """Request to create POs from MRP run"""
    mrp_run_id: str = Field(..., description="MRP run ID")
    planning_run_id: Optional[str] = Field(
        None,
        description="Filter by planning run ID (optional)"
    )
    auto_approve: bool = Field(
        False,
        description="Auto-approve generated POs"
    )
    group_by_vendor: bool = Field(
        True,
        description="Group line items by vendor into single PO"
    )


class PurchaseOrderResponse(BaseModel):
    """Purchase order response"""
    id: int
    po_number: str
    vendor_id: Optional[str]
    supplier_site_id: int
    supplier_site_name: str
    destination_site_id: int
    destination_site_name: str
    status: str
    order_date: date
    total_amount: float
    line_items_count: int
    created_at: datetime
    approved_at: Optional[datetime] = None
    received_at: Optional[datetime] = None


class PurchaseOrderDetailResponse(BaseModel):
    """Detailed purchase order response"""
    id: int
    po_number: str
    vendor_id: Optional[str]
    supplier_site_id: int
    supplier_site_name: str
    destination_site_id: int
    destination_site_name: str
    status: str
    order_date: date
    total_amount: float
    line_items: List[PurchaseOrderLineItem]
    notes: Optional[str]
    created_by_id: int
    created_by_name: Optional[str]
    approved_by_id: Optional[int]
    approved_by_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None
    received_at: Optional[datetime] = None


class POGenerationSummary(BaseModel):
    """Summary of PO generation from MRP"""
    total_pos_created: int
    total_line_items: int
    total_cost_estimate: float
    pos_by_vendor: dict
    purchase_orders: List[PurchaseOrderResponse]


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])


# ============================================================================
# Database Storage
# ============================================================================

# PO data is now persisted to purchase_order and purchase_order_line_item tables


# ============================================================================
# Helper Functions
# ============================================================================

def check_po_permission(user: User, action: str) -> None:
    """Check if user has permission for PO action"""
    required_permissions = {
        "view": "view_mps",  # Reuse MPS view permission
        "manage": "manage_mps",  # Reuse MPS manage permission
    }

    permission = required_permissions.get(action)
    if not permission:
        return

    has_permission = False
    for role in user.roles:
        for capability in role.capabilities:
            if capability.key == permission:
                has_permission = True
                break
        if has_permission:
            break

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have permission to {action} purchase orders"
        )


def generate_po_number(db: Session, vendor_id: Optional[str], order_date: date) -> str:
    """Generate unique PO number using database count"""
    vendor_prefix = vendor_id[:3].upper() if vendor_id else "VEN"
    date_str = order_date.strftime("%Y%m%d")

    # Get count of POs for this vendor+date combination
    count = db.execute(
        select(func.count(PurchaseOrderModel.id)).where(
            and_(
                PurchaseOrderModel.vendor_id == vendor_id,
                PurchaseOrderModel.order_date == order_date
            )
        )
    ).scalar() or 0

    po_number = f"PO-{vendor_prefix}-{date_str}-{(count + 1):04d}"

    return po_number


def get_po_requests_from_supply_plan(
    db: Session,
    planning_run_id: Optional[str] = None
) -> List[SupplyPlan]:
    """Get PO requests from supply_plan table"""
    query = select(SupplyPlan).where(SupplyPlan.plan_type == "po_request")

    if planning_run_id:
        query = query.where(SupplyPlan.planning_run_id == planning_run_id)

    return db.execute(query).scalars().all()


def group_po_requests_by_vendor(
    po_requests: List[SupplyPlan]
) -> dict:
    """
    Group PO requests by vendor and destination site.

    Returns: {(vendor_id, destination_site_id): [po_requests]}
    """
    grouped = {}

    for req in po_requests:
        key = (req.vendor_id, req.destination_site_id)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(req)

    return grouped


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/create", response_model=PurchaseOrderResponse)
async def create_purchase_order(
    request: CreatePurchaseOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Create a new purchase order.

    Creates a PO with line items for ordering components from suppliers.
    """
    check_po_permission(current_user, "manage")

    # Get supplier and destination site details
    supplier_site = db.get(Node, request.supplier_site_id)
    destination_site = db.get(Node, request.destination_site_id)

    if not supplier_site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier site {request.supplier_site_id} not found"
        )

    if not destination_site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination site {request.destination_site_id} not found"
        )

    # Generate PO number
    po_number = generate_po_number(db, request.vendor_id, request.order_date)

    # Calculate total
    total_amount = sum(
        (item.unit_price or 0) * item.quantity
        for item in request.line_items
    )

    # Create PO in database
    purchase_order = PurchaseOrderModel(
        po_number=po_number,
        vendor_id=request.vendor_id,
        supplier_site_id=request.supplier_site_id,
        destination_site_id=request.destination_site_id,
        status="DRAFT",
        order_date=request.order_date,
        requested_delivery_date=request.line_items[0].requested_delivery_date,
        total_amount=total_amount,
        currency="USD",
        notes=request.notes,
        created_by_id=current_user.id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(purchase_order)
    db.flush()  # Get purchase_order.id

    # Create line items
    for item in request.line_items:
        line_item = PurchaseOrderLineItemModel(
            po_id=purchase_order.id,
            line_number=item.line_number,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price or 0.0,
            line_amount=(item.unit_price or 0.0) * item.quantity,
            requested_delivery_date=item.requested_delivery_date,
            promised_delivery_date=item.promised_delivery_date,
            created_at=datetime.now(),
        )
        db.add(line_item)

    db.commit()
    db.refresh(purchase_order)

    return PurchaseOrderResponse(
        id=purchase_order.id,
        po_number=purchase_order.po_number,
        vendor_id=purchase_order.vendor_id,
        supplier_site_id=purchase_order.supplier_site_id,
        supplier_site_name=supplier_site.name,
        destination_site_id=purchase_order.destination_site_id,
        destination_site_name=destination_site.name,
        status=purchase_order.status,
        order_date=purchase_order.order_date,
        total_amount=purchase_order.total_amount or 0.0,
        line_items_count=len(request.line_items),
        created_at=purchase_order.created_at,
        approved_at=purchase_order.approved_at,
        received_at=purchase_order.received_at,
    )


@router.post("/generate-from-mrp", response_model=POGenerationSummary)
async def generate_pos_from_mrp(
    request: CreatePOFromMRPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Generate purchase orders from MRP planned orders.

    Converts PO requests in supply_plan table to actual purchase orders.
    Can group by vendor to consolidate line items.
    """
    check_po_permission(current_user, "manage")

    # Get PO requests from supply_plan
    po_requests = get_po_requests_from_supply_plan(
        db,
        request.planning_run_id or request.mrp_run_id
    )

    if not po_requests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No PO requests found for MRP run {request.mrp_run_id}"
        )

    created_pos = []
    total_cost = 0.0
    total_line_items = 0
    pos_by_vendor = {}

    if request.group_by_vendor:
        # Group by vendor and destination
        grouped = group_po_requests_by_vendor(po_requests)

        for (vendor_id, dest_site_id), reqs in grouped.items():
            # Get site details
            dest_site = db.get(Node, dest_site_id)

            # Assume supplier site from first request
            supplier_site_id = reqs[0].source_site_id
            supplier_site = db.get(Node, supplier_site_id) if supplier_site_id else None

            # Create line items
            line_items = []
            for idx, req in enumerate(reqs):
                product = db.get(Product, req.product_id)

                line_item = PurchaseOrderLineItem(
                    line_number=idx + 1,
                    product_id=req.product_id,
                    product_name=product.name if product else f"Product {req.product_id}",
                    quantity=req.planned_order_quantity,
                    unit_price=req.unit_cost,
                    line_total=req.planned_order_quantity * (req.unit_cost or 0),
                    requested_delivery_date=req.planned_receipt_date,
                    promised_delivery_date=None,
                )
                line_items.append(line_item)
                total_line_items += 1

            # Calculate PO total
            po_total = sum(item.line_total or 0 for item in line_items)
            total_cost += po_total

            # Generate PO number
            po_number = generate_po_number(db, vendor_id, reqs[0].planned_order_date)

            # Create PO in database
            purchase_order = PurchaseOrderModel(
                po_number=po_number,
                vendor_id=vendor_id,
                supplier_site_id=supplier_site_id,
                destination_site_id=dest_site_id,
                status="APPROVED" if request.auto_approve else "DRAFT",
                order_date=reqs[0].planned_order_date,
                requested_delivery_date=line_items[0].requested_delivery_date,
                total_amount=po_total,
                currency="USD",
                notes=f"Generated from MRP run {request.mrp_run_id}",
                mrp_run_id=request.mrp_run_id,
                planning_run_id=request.planning_run_id,
                created_by_id=current_user.id,
                approved_by_id=current_user.id if request.auto_approve else None,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                approved_at=datetime.now() if request.auto_approve else None,
            )
            db.add(purchase_order)
            db.flush()  # Get purchase_order.id

            # Create line items in database
            for line_item in line_items:
                po_line = PurchaseOrderLineItemModel(
                    po_id=purchase_order.id,
                    line_number=line_item.line_number,
                    product_id=line_item.product_id,
                    quantity=line_item.quantity,
                    unit_price=line_item.unit_price or 0.0,
                    line_amount=line_item.line_total or 0.0,
                    requested_delivery_date=line_item.requested_delivery_date,
                    promised_delivery_date=line_item.promised_delivery_date,
                    created_at=datetime.now(),
                )
                db.add(po_line)

            db.commit()
            db.refresh(purchase_order)

            # Get site names for response
            supplier_site_name = supplier_site.name if supplier_site else "Unknown Supplier"
            dest_site_name = dest_site.name if dest_site else f"Site {dest_site_id}"

            created_pos.append(PurchaseOrderResponse(
                id=purchase_order.id,
                po_number=purchase_order.po_number,
                vendor_id=purchase_order.vendor_id,
                supplier_site_id=purchase_order.supplier_site_id,
                supplier_site_name=supplier_site_name,
                destination_site_id=purchase_order.destination_site_id,
                destination_site_name=dest_site_name,
                status=purchase_order.status,
                order_date=purchase_order.order_date,
                total_amount=purchase_order.total_amount,
                line_items_count=len(line_items),
                created_at=purchase_order.created_at,
                approved_at=purchase_order.approved_at,
                received_at=purchase_order.received_at,
            ))

            # Track by vendor
            vendor_key = vendor_id or "Unknown"
            pos_by_vendor[vendor_key] = pos_by_vendor.get(vendor_key, 0) + 1

    else:
        # Create one PO per request (no grouping)
        for req in po_requests:
            product = db.get(Product, req.product_id)
            dest_site = db.get(Node, req.destination_site_id)
            supplier_site = db.get(Node, req.source_site_id) if req.source_site_id else None

            line_item = PurchaseOrderLineItem(
                line_number=1,
                product_id=req.product_id,
                product_name=product.name if product else f"Product {req.product_id}",
                quantity=req.planned_order_quantity,
                unit_price=req.unit_cost,
                line_total=req.planned_order_quantity * (req.unit_cost or 0),
                requested_delivery_date=req.planned_receipt_date,
                promised_delivery_date=None,
            )

            total_line_items += 1
            po_total = line_item.line_total or 0
            total_cost += po_total

            po_number = generate_po_number(db, req.vendor_id, req.planned_order_date)

            # Create PO in database
            purchase_order = PurchaseOrderModel(
                po_number=po_number,
                vendor_id=req.vendor_id,
                supplier_site_id=req.source_site_id,
                destination_site_id=req.destination_site_id,
                status="APPROVED" if request.auto_approve else "DRAFT",
                order_date=req.planned_order_date,
                requested_delivery_date=line_item.requested_delivery_date,
                total_amount=po_total,
                currency="USD",
                notes=f"Generated from MRP run {request.mrp_run_id}",
                mrp_run_id=request.mrp_run_id,
                planning_run_id=request.planning_run_id,
                created_by_id=current_user.id,
                approved_by_id=current_user.id if request.auto_approve else None,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                approved_at=datetime.now() if request.auto_approve else None,
            )
            db.add(purchase_order)
            db.flush()  # Get purchase_order.id

            # Create line item in database
            po_line = PurchaseOrderLineItemModel(
                po_id=purchase_order.id,
                line_number=line_item.line_number,
                product_id=line_item.product_id,
                quantity=line_item.quantity,
                unit_price=line_item.unit_price or 0.0,
                line_amount=line_item.line_total or 0.0,
                requested_delivery_date=line_item.requested_delivery_date,
                promised_delivery_date=line_item.promised_delivery_date,
                created_at=datetime.now(),
            )
            db.add(po_line)

            db.commit()
            db.refresh(purchase_order)

            # Get site names for response
            supplier_site_name = supplier_site.name if supplier_site else "Unknown Supplier"
            dest_site_name = dest_site.name if dest_site else f"Site {req.destination_site_id}"

            created_pos.append(PurchaseOrderResponse(
                id=purchase_order.id,
                po_number=purchase_order.po_number,
                vendor_id=purchase_order.vendor_id,
                supplier_site_id=purchase_order.supplier_site_id,
                supplier_site_name=supplier_site_name,
                destination_site_id=purchase_order.destination_site_id,
                destination_site_name=dest_site_name,
                status=purchase_order.status,
                order_date=purchase_order.order_date,
                total_amount=purchase_order.total_amount,
                line_items_count=1,
                created_at=purchase_order.created_at,
                approved_at=purchase_order.approved_at,
                received_at=purchase_order.received_at,
            ))

            vendor_key = req.vendor_id or "Unknown"
            pos_by_vendor[vendor_key] = pos_by_vendor.get(vendor_key, 0) + 1

    return POGenerationSummary(
        total_pos_created=len(created_pos),
        total_line_items=total_line_items,
        total_cost_estimate=total_cost,
        pos_by_vendor=pos_by_vendor,
        purchase_orders=created_pos,
    )


@router.get("/", response_model=List[PurchaseOrderResponse])
async def list_purchase_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[str] = None,
) -> List[dict]:
    """List all purchase orders with optional status filter"""
    check_po_permission(current_user, "view")

    # Query from database
    query = select(PurchaseOrderModel).order_by(PurchaseOrderModel.created_at.desc())

    if status_filter:
        query = query.where(PurchaseOrderModel.status == status_filter)

    pos = db.execute(query).scalars().all()

    results = []
    for po in pos:
        # Get site names
        supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
        dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

        # Count line items
        line_items_count = db.execute(
            select(func.count(PurchaseOrderLineItemModel.id)).where(
                PurchaseOrderLineItemModel.po_id == po.id
            )
        ).scalar() or 0

        results.append(PurchaseOrderResponse(
            id=po.id,
            po_number=po.po_number,
            vendor_id=po.vendor_id,
            supplier_site_id=po.supplier_site_id,
            supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
            destination_site_id=po.destination_site_id,
            destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
            status=po.status,
            order_date=po.order_date,
            total_amount=po.total_amount,
            line_items_count=line_items_count,
            created_at=po.created_at,
            approved_at=po.approved_at,
            received_at=po.received_at,
        ))

    return results


@router.get("/{po_id}", response_model=PurchaseOrderDetailResponse)
async def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get detailed purchase order by ID"""
    check_po_permission(current_user, "view")

    # Query from database
    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    # Get line items
    line_items = db.execute(
        select(PurchaseOrderLineItemModel).where(
            PurchaseOrderLineItemModel.po_id == po_id
        ).order_by(PurchaseOrderLineItemModel.line_number)
    ).scalars().all()

    # Get site names
    supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
    dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

    # Get user names
    created_by = db.get(User, po.created_by_id) if po.created_by_id else None
    approved_by = db.get(User, po.approved_by_id) if po.approved_by_id else None

    # Build line items response
    line_items_response = []
    for line in line_items:
        product = db.get(Product, line.product_id)
        line_items_response.append(PurchaseOrderLineItem(
            line_number=line.line_number,
            product_id=line.product_id,
            product_name=product.name if product else f"Product {line.product_id}",
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.line_amount,
            requested_delivery_date=line.requested_delivery_date,
            promised_delivery_date=line.promised_delivery_date,
        ))

    return PurchaseOrderDetailResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        supplier_site_id=po.supplier_site_id,
        supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
        destination_site_id=po.destination_site_id,
        destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
        status=po.status,
        order_date=po.order_date,
        total_amount=po.total_amount,
        line_items=line_items_response,
        notes=po.notes,
        created_by_id=po.created_by_id,
        created_by_name=f"{created_by.first_name} {created_by.last_name}".strip() if created_by else None,
        approved_by_id=po.approved_by_id,
        approved_by_name=f"{approved_by.first_name} {approved_by.last_name}".strip() if approved_by else None,
        created_at=po.created_at,
        updated_at=po.updated_at,
        approved_at=po.approved_at,
        received_at=po.received_at,
    )


@router.post("/{po_id}/approve", response_model=PurchaseOrderResponse)
async def approve_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Approve a purchase order"""
    check_po_permission(current_user, "manage")

    # Query from database
    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve DRAFT purchase orders. Current status: {po.status}"
        )

    # Update status
    po.status = "APPROVED"
    po.approved_by_id = current_user.id
    po.approved_at = datetime.now()
    po.updated_at = datetime.now()

    db.commit()
    db.refresh(po)

    # Get site names and line items count
    supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
    dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

    line_items_count = db.execute(
        select(func.count(PurchaseOrderLineItemModel.id)).where(
            PurchaseOrderLineItemModel.po_id == po.id
        )
    ).scalar() or 0

    return PurchaseOrderResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        supplier_site_id=po.supplier_site_id,
        supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
        destination_site_id=po.destination_site_id,
        destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
        status=po.status,
        order_date=po.order_date,
        total_amount=po.total_amount,
        line_items_count=line_items_count,
        created_at=po.created_at,
        approved_at=po.approved_at,
        received_at=po.received_at,
    )


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a purchase order (DRAFT only)"""
    check_po_permission(current_user, "manage")

    # Query from database
    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only delete DRAFT purchase orders. Current status: {po.status}"
        )

    # Delete from database (CASCADE will delete line items)
    db.delete(po)
    db.commit()


@router.post("/{po_id}/send", response_model=PurchaseOrderResponse)
async def send_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send an approved purchase order to the supplier"""
    check_po_permission(current_user, "manage")

    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only send APPROVED purchase orders. Current status: {po.status}"
        )

    # Update status
    po.status = "SENT"
    po.sent_at = datetime.now()
    po.sent_by_id = current_user.id
    po.updated_at = datetime.now()

    db.commit()
    db.refresh(po)

    # Get site names and line items count
    supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
    dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

    line_items_count = db.execute(
        select(func.count(PurchaseOrderLineItemModel.id)).where(
            PurchaseOrderLineItemModel.po_id == po.id
        )
    ).scalar() or 0

    return PurchaseOrderResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        supplier_site_id=po.supplier_site_id,
        supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
        destination_site_id=po.destination_site_id,
        destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
        status=po.status,
        order_date=po.order_date,
        total_amount=po.total_amount,
        line_items_count=line_items_count,
        created_at=po.created_at,
        approved_at=po.approved_at,
        received_at=po.received_at,
    )


class AcknowledgementRequest(BaseModel):
    """Request to acknowledge or confirm a purchase order"""
    notes: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


@router.post("/{po_id}/acknowledge", response_model=PurchaseOrderResponse)
async def acknowledge_purchase_order(
    po_id: int,
    request: AcknowledgementRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Record supplier acknowledgment of a purchase order"""
    check_po_permission(current_user, "manage")

    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status != "SENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only acknowledge SENT purchase orders. Current status: {po.status}"
        )

    # Update status and acknowledgment fields
    po.status = "ACKNOWLEDGED"
    po.acknowledged_at = request.acknowledged_at or datetime.now()
    po.acknowledged_by = request.acknowledged_by or "Supplier"
    po.acknowledgment_notes = request.notes
    po.updated_at = datetime.now()

    db.commit()
    db.refresh(po)

    # Get site names and line items count
    supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
    dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

    line_items_count = db.execute(
        select(func.count(PurchaseOrderLineItemModel.id)).where(
            PurchaseOrderLineItemModel.po_id == po.id
        )
    ).scalar() or 0

    return PurchaseOrderResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        supplier_site_id=po.supplier_site_id,
        supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
        destination_site_id=po.destination_site_id,
        destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
        status=po.status,
        order_date=po.order_date,
        total_amount=po.total_amount,
        line_items_count=line_items_count,
        created_at=po.created_at,
        approved_at=po.approved_at,
        received_at=po.received_at,
    )


@router.post("/{po_id}/confirm", response_model=PurchaseOrderResponse)
async def confirm_purchase_order(
    po_id: int,
    request: AcknowledgementRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Record supplier confirmation of a purchase order (ready for shipment)"""
    check_po_permission(current_user, "manage")

    po = db.get(PurchaseOrderModel, po_id)

    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status != "ACKNOWLEDGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only confirm ACKNOWLEDGED purchase orders. Current status: {po.status}"
        )

    # Update status and confirmation fields
    po.status = "CONFIRMED"
    po.confirmed_at = request.acknowledged_at or datetime.now()
    po.confirmed_by = request.acknowledged_by or "Supplier"
    po.confirmation_notes = request.notes
    po.updated_at = datetime.now()

    db.commit()
    db.refresh(po)

    # Get site names and line items count
    supplier_site = db.get(Node, po.supplier_site_id) if po.supplier_site_id else None
    dest_site = db.get(Node, po.destination_site_id) if po.destination_site_id else None

    line_items_count = db.execute(
        select(func.count(PurchaseOrderLineItemModel.id)).where(
            PurchaseOrderLineItemModel.po_id == po.id
        )
    ).scalar() or 0

    return PurchaseOrderResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        supplier_site_id=po.supplier_site_id,
        supplier_site_name=supplier_site.name if supplier_site else "Unknown Supplier",
        destination_site_id=po.destination_site_id,
        destination_site_name=dest_site.name if dest_site else f"Site {po.destination_site_id}",
        status=po.status,
        order_date=po.order_date,
        total_amount=po.total_amount,
        line_items_count=line_items_count,
        created_at=po.created_at,
        approved_at=po.approved_at,
        received_at=po.received_at,
    )


# ============================================================================
# Goods Receipt Schemas
# ============================================================================

class GoodsReceiptLineItemRequest(BaseModel):
    """Line item for goods receipt"""
    po_line_id: int = Field(..., description="PO line item ID")
    received_qty: float = Field(..., ge=0, description="Quantity received")
    accepted_qty: Optional[float] = Field(None, ge=0, description="Quantity accepted after inspection")
    rejected_qty: Optional[float] = Field(0, ge=0, description="Quantity rejected")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection: DAMAGED, WRONG_ITEM, QUALITY, QUANTITY, OTHER")
    rejection_notes: Optional[str] = None
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    put_away_location: Optional[str] = None


class CreateGoodsReceiptRequest(BaseModel):
    """Request to create a goods receipt"""
    po_id: int = Field(..., description="Purchase order ID")
    receipt_date: datetime = Field(default_factory=datetime.now, description="Date/time of receipt")
    delivery_note_number: Optional[str] = Field(None, description="Supplier's delivery note number")
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    receiving_location: Optional[str] = None
    notes: Optional[str] = None
    line_items: List[GoodsReceiptLineItemRequest] = Field(..., min_length=1)


class GoodsReceiptLineItemResponse(BaseModel):
    """Response for goods receipt line item"""
    id: int
    po_line_id: int
    line_number: int
    product_id: str
    expected_qty: float
    received_qty: float
    accepted_qty: float
    rejected_qty: float
    variance_qty: float
    variance_type: Optional[str]
    inspection_status: Optional[str]
    rejection_reason: Optional[str]
    batch_number: Optional[str]
    put_away_location: Optional[str]

    class Config:
        from_attributes = True


class GoodsReceiptResponse(BaseModel):
    """Response for goods receipt"""
    id: int
    gr_number: str
    po_id: int
    receipt_date: datetime
    delivery_note_number: Optional[str]
    carrier: Optional[str]
    tracking_number: Optional[str]
    status: str
    receiving_location: Optional[str]
    total_received_qty: float
    total_accepted_qty: float
    total_rejected_qty: float
    has_variance: bool
    variance_notes: Optional[str]
    notes: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    line_items: List[GoodsReceiptLineItemResponse] = []

    class Config:
        from_attributes = True


class GoodsReceiptSummary(BaseModel):
    """Summary of goods receipt for list views"""
    id: int
    gr_number: str
    po_id: int
    po_number: str
    receipt_date: datetime
    status: str
    total_received_qty: float
    total_accepted_qty: float
    total_rejected_qty: float
    has_variance: bool

    class Config:
        from_attributes = True


# ============================================================================
# Goods Receipt Endpoints
# ============================================================================

@router.post("/{po_id}/receive", response_model=GoodsReceiptResponse)
async def create_goods_receipt(
    po_id: int,
    request: CreateGoodsReceiptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Create a goods receipt for a purchase order.

    Supports:
    - Partial receipts (receive less than ordered)
    - Over-delivery (receive more than ordered)
    - Quality inspection with accept/reject
    - Multiple receipts per PO (partial deliveries)
    """
    check_po_permission(current_user, "manage")

    # Validate PO exists and is in receivable state
    po = db.get(PurchaseOrderModel, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    if po.status not in ["SENT", "ACKNOWLEDGED", "CONFIRMED", "SHIPPED", "PARTIAL_RECEIVED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot receive goods for PO in status: {po.status}. Must be SENT, ACKNOWLEDGED, CONFIRMED, SHIPPED, or PARTIAL_RECEIVED."
        )

    # Generate GR number
    gr_number = f"GR-{po.po_number}-{uuid.uuid4().hex[:6].upper()}"

    # Create goods receipt header
    gr = GoodsReceiptModel(
        gr_number=gr_number,
        po_id=po_id,
        receipt_date=request.receipt_date,
        delivery_note_number=request.delivery_note_number,
        carrier=request.carrier,
        tracking_number=request.tracking_number,
        status="PENDING",
        receiving_site_id=po.destination_site_id,
        receiving_location=request.receiving_location,
        notes=request.notes,
        received_by_id=current_user.id,
    )
    db.add(gr)
    db.flush()  # Get the ID

    # Get PO line items for validation
    po_lines = {
        line.id: line for line in db.query(PurchaseOrderLineItemModel).filter(
            PurchaseOrderLineItemModel.po_id == po_id
        ).all()
    }

    total_received = 0.0
    total_accepted = 0.0
    total_rejected = 0.0
    has_variance = False
    line_items_response = []

    for item in request.line_items:
        po_line = po_lines.get(item.po_line_id)
        if not po_line:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PO line item {item.po_line_id} not found"
            )

        # Calculate remaining quantity to receive
        remaining_qty = po_line.quantity - po_line.received_quantity

        # Create GR line item
        accepted_qty = item.accepted_qty if item.accepted_qty is not None else item.received_qty
        rejected_qty = item.rejected_qty or 0

        # Validate accepted + rejected = received
        if accepted_qty + rejected_qty > item.received_qty:
            accepted_qty = item.received_qty - rejected_qty

        gr_line = GoodsReceiptLineItemModel(
            gr_id=gr.id,
            po_line_id=item.po_line_id,
            line_number=po_line.line_number,
            product_id=po_line.product_id,
            expected_qty=remaining_qty,
            received_qty=item.received_qty,
            accepted_qty=accepted_qty,
            rejected_qty=rejected_qty,
            inspection_required=rejected_qty > 0,
            inspection_status="PASSED" if rejected_qty == 0 else ("FAILED" if accepted_qty == 0 else "PARTIAL"),
            rejection_reason=item.rejection_reason,
            rejection_notes=item.rejection_notes,
            batch_number=item.batch_number,
            lot_number=item.lot_number,
            put_away_location=item.put_away_location,
        )

        # Calculate variance
        gr_line.calculate_variance()
        if gr_line.variance_type != "EXACT":
            has_variance = True

        db.add(gr_line)

        # Update PO line item quantities
        po_line.received_quantity += item.received_qty
        po_line.rejected_quantity += rejected_qty

        total_received += item.received_qty
        total_accepted += accepted_qty
        total_rejected += rejected_qty

        line_items_response.append(GoodsReceiptLineItemResponse(
            id=gr_line.id,
            po_line_id=gr_line.po_line_id,
            line_number=gr_line.line_number,
            product_id=gr_line.product_id,
            expected_qty=gr_line.expected_qty,
            received_qty=gr_line.received_qty,
            accepted_qty=gr_line.accepted_qty,
            rejected_qty=gr_line.rejected_qty,
            variance_qty=gr_line.variance_qty,
            variance_type=gr_line.variance_type,
            inspection_status=gr_line.inspection_status,
            rejection_reason=gr_line.rejection_reason,
            batch_number=gr_line.batch_number,
            put_away_location=gr_line.put_away_location,
        ))

    # Update GR totals
    gr.total_received_qty = total_received
    gr.total_accepted_qty = total_accepted
    gr.total_rejected_qty = total_rejected
    gr.has_variance = has_variance
    gr.status = "COMPLETED"
    gr.completed_at = datetime.now()

    # Update PO status based on receipt completeness
    total_ordered = sum(line.quantity for line in po_lines.values())
    total_po_received = sum(line.received_quantity for line in po_lines.values())

    if total_po_received >= total_ordered:
        po.status = "RECEIVED"
        po.actual_delivery_date = request.receipt_date.date() if hasattr(request.receipt_date, 'date') else request.receipt_date
        po.received_at = datetime.now()
        po.received_by_id = current_user.id
    else:
        po.status = "PARTIAL_RECEIVED"

    db.commit()
    db.refresh(gr)

    return GoodsReceiptResponse(
        id=gr.id,
        gr_number=gr.gr_number,
        po_id=gr.po_id,
        receipt_date=gr.receipt_date,
        delivery_note_number=gr.delivery_note_number,
        carrier=gr.carrier,
        tracking_number=gr.tracking_number,
        status=gr.status,
        receiving_location=gr.receiving_location,
        total_received_qty=gr.total_received_qty,
        total_accepted_qty=gr.total_accepted_qty,
        total_rejected_qty=gr.total_rejected_qty,
        has_variance=gr.has_variance,
        variance_notes=gr.variance_notes,
        notes=gr.notes,
        created_at=gr.created_at,
        completed_at=gr.completed_at,
        line_items=line_items_response,
    )


@router.get("/{po_id}/receipts", response_model=List[GoodsReceiptSummary])
async def get_po_goods_receipts(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """Get all goods receipts for a purchase order"""
    check_po_permission(current_user, "view")

    po = db.get(PurchaseOrderModel, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    receipts = db.query(GoodsReceiptModel).filter(
        GoodsReceiptModel.po_id == po_id
    ).order_by(GoodsReceiptModel.receipt_date.desc()).all()

    return [
        GoodsReceiptSummary(
            id=gr.id,
            gr_number=gr.gr_number,
            po_id=gr.po_id,
            po_number=po.po_number,
            receipt_date=gr.receipt_date,
            status=gr.status,
            total_received_qty=gr.total_received_qty,
            total_accepted_qty=gr.total_accepted_qty,
            total_rejected_qty=gr.total_rejected_qty,
            has_variance=gr.has_variance,
        )
        for gr in receipts
    ]


@router.get("/{po_id}/receipts/{gr_id}", response_model=GoodsReceiptResponse)
async def get_goods_receipt_detail(
    po_id: int,
    gr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get detailed goods receipt information"""
    check_po_permission(current_user, "view")

    gr = db.query(GoodsReceiptModel).filter(
        GoodsReceiptModel.id == gr_id,
        GoodsReceiptModel.po_id == po_id
    ).first()

    if not gr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goods receipt {gr_id} not found for PO {po_id}"
        )

    line_items = db.query(GoodsReceiptLineItemModel).filter(
        GoodsReceiptLineItemModel.gr_id == gr_id
    ).all()

    return GoodsReceiptResponse(
        id=gr.id,
        gr_number=gr.gr_number,
        po_id=gr.po_id,
        receipt_date=gr.receipt_date,
        delivery_note_number=gr.delivery_note_number,
        carrier=gr.carrier,
        tracking_number=gr.tracking_number,
        status=gr.status,
        receiving_location=gr.receiving_location,
        total_received_qty=gr.total_received_qty,
        total_accepted_qty=gr.total_accepted_qty,
        total_rejected_qty=gr.total_rejected_qty,
        has_variance=gr.has_variance,
        variance_notes=gr.variance_notes,
        notes=gr.notes,
        created_at=gr.created_at,
        completed_at=gr.completed_at,
        line_items=[
            GoodsReceiptLineItemResponse(
                id=item.id,
                po_line_id=item.po_line_id,
                line_number=item.line_number,
                product_id=item.product_id,
                expected_qty=item.expected_qty,
                received_qty=item.received_qty,
                accepted_qty=item.accepted_qty,
                rejected_qty=item.rejected_qty,
                variance_qty=item.variance_qty,
                variance_type=item.variance_type,
                inspection_status=item.inspection_status,
                rejection_reason=item.rejection_reason,
                batch_number=item.batch_number,
                put_away_location=item.put_away_location,
            )
            for item in line_items
        ],
    )


@router.get("/{po_id}/receive-status")
async def get_po_receive_status(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Get receipt status summary for a PO.

    Returns quantities ordered, received, accepted, rejected, and remaining.
    """
    check_po_permission(current_user, "view")

    po = db.get(PurchaseOrderModel, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    # Get all PO line items with receipt status
    line_items = db.query(PurchaseOrderLineItemModel).filter(
        PurchaseOrderLineItemModel.po_id == po_id
    ).all()

    lines_status = []
    total_ordered = 0.0
    total_received = 0.0
    total_rejected = 0.0
    total_remaining = 0.0

    for line in line_items:
        remaining = line.quantity - line.received_quantity
        lines_status.append({
            "line_id": line.id,
            "line_number": line.line_number,
            "product_id": line.product_id,
            "ordered_qty": line.quantity,
            "received_qty": line.received_quantity,
            "rejected_qty": line.rejected_quantity,
            "remaining_qty": max(0, remaining),
            "is_complete": remaining <= 0,
        })
        total_ordered += line.quantity
        total_received += line.received_quantity
        total_rejected += line.rejected_quantity
        total_remaining += max(0, remaining)

    # Count receipts
    receipt_count = db.query(func.count(GoodsReceiptModel.id)).filter(
        GoodsReceiptModel.po_id == po_id
    ).scalar() or 0

    return {
        "po_id": po_id,
        "po_number": po.po_number,
        "status": po.status,
        "total_ordered": total_ordered,
        "total_received": total_received,
        "total_rejected": total_rejected,
        "total_remaining": total_remaining,
        "receipt_count": receipt_count,
        "is_fully_received": total_remaining <= 0,
        "receive_percentage": round((total_received / total_ordered * 100), 1) if total_ordered > 0 else 0,
        "line_items": lines_status,
    }

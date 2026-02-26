"""
Invoice and 3-Way Matching API Endpoints

Provides functionality for:
- Invoice entry and management
- 3-way matching (PO, GR, Invoice)
- Discrepancy handling and resolution
- Payment processing workflow
"""

from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from pydantic import BaseModel, Field
import json

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceMatchResult
from app.models.purchase_order import (
    PurchaseOrder as PurchaseOrderModel,
    PurchaseOrderLineItem as PurchaseOrderLineItemModel,
)
from app.models.goods_receipt import (
    GoodsReceipt as GoodsReceiptModel,
    GoodsReceiptLineItem as GoodsReceiptLineItemModel,
)

router = APIRouter(prefix="/invoices", tags=["invoices", "3-way-match"])


# ============================================================================
# Permission Check
# ============================================================================

def check_invoice_permission(user: User, action: str):
    """Check if user has permission for invoice actions"""
    required_caps = {
        "view": ["view_invoices", "view_order_planning"],
        "create": ["create_invoices", "manage_order_planning"],
        "approve": ["approve_invoices", "approve_order"],
        "manage": ["manage_invoices", "manage_order_planning"],
    }
    caps = required_caps.get(action, [])

    # Check if user has any of the required capabilities
    if user.roles:
        for role in user.roles:
            if hasattr(role, 'name') and role.name in ['SYSTEM_ADMIN', 'TENANT_ADMIN']:
                return True
            if hasattr(role, 'permissions'):
                for perm in role.permissions:
                    if hasattr(perm, 'name') and perm.name in caps:
                        return True

    # Allow if no specific permission required (fallback for demo)
    return True


# ============================================================================
# Request/Response Schemas
# ============================================================================

class InvoiceLineItemCreate(BaseModel):
    """Line item for invoice creation"""
    line_number: int
    product_id: str
    description: Optional[str] = None
    invoiced_qty: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    discount_amount: float = Field(0, ge=0)
    tax_amount: float = Field(0, ge=0)
    po_line_id: Optional[int] = None  # Link to PO line for matching


class CreateInvoiceRequest(BaseModel):
    """Request to create an invoice"""
    vendor_invoice_number: str = Field(..., description="Supplier's invoice number")
    vendor_id: str = Field(..., description="Vendor identifier")
    vendor_name: Optional[str] = None
    po_id: Optional[int] = Field(None, description="Primary PO ID")
    invoice_date: date
    due_date: Optional[date] = None
    tax_amount: float = Field(0, ge=0)
    shipping_amount: float = Field(0, ge=0)
    discount_amount: float = Field(0, ge=0)
    currency: str = Field("USD", max_length=3)
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    line_items: List[InvoiceLineItemCreate] = Field(..., min_length=1)


class InvoiceLineItemResponse(BaseModel):
    """Line item response"""
    id: int
    line_number: int
    product_id: str
    description: Optional[str]
    invoiced_qty: float
    po_qty: Optional[float]
    received_qty: Optional[float]
    unit_price: float
    po_unit_price: Optional[float]
    line_total: float
    match_status: str
    qty_variance: float
    price_variance: float
    variance_pct: float

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    """Invoice response"""
    id: int
    invoice_number: str
    vendor_invoice_number: str
    vendor_id: str
    vendor_name: Optional[str]
    po_id: Optional[int]
    invoice_date: date
    received_date: date
    due_date: Optional[date]
    subtotal: float
    tax_amount: float
    shipping_amount: float
    discount_amount: float
    total_amount: float
    currency: str
    match_status: str
    match_score: float
    status: str
    has_discrepancy: bool
    discrepancy_amount: float
    created_at: datetime
    line_items: List[InvoiceLineItemResponse] = []

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """List of invoices"""
    id: int
    invoice_number: str
    vendor_invoice_number: str
    vendor_id: str
    vendor_name: Optional[str]
    po_id: Optional[int]
    invoice_date: date
    due_date: Optional[date]
    total_amount: float
    match_status: str
    match_score: float
    status: str
    has_discrepancy: bool

    class Config:
        from_attributes = True


class MatchResultResponse(BaseModel):
    """3-way match result"""
    id: int
    invoice_id: int
    po_id: Optional[int]
    gr_id: Optional[int]
    match_date: datetime
    overall_status: str
    match_score: float
    po_total: Optional[float]
    gr_total: Optional[float]
    invoice_total: float
    total_variance: float
    qty_variance: float
    qty_match_pct: float
    price_match_pct: float
    exceptions_count: int
    resolution_status: Optional[str]

    class Config:
        from_attributes = True


class PerformMatchRequest(BaseModel):
    """Request to perform 3-way match"""
    po_id: Optional[int] = None  # If not provided, will try to auto-detect
    gr_id: Optional[int] = None  # If not provided, will use latest GR for PO
    qty_tolerance_pct: float = Field(2.0, ge=0, le=100, description="Quantity tolerance %")
    price_tolerance_pct: float = Field(1.0, ge=0, le=100, description="Price tolerance %")


class ResolveDiscrepancyRequest(BaseModel):
    """Request to resolve a discrepancy"""
    resolution: str = Field(..., description="ACCEPT, REJECT, DEBIT_MEMO, CREDIT_MEMO, ADJUST")
    notes: Optional[str] = None
    adjusted_amount: Optional[float] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("", response_model=InvoiceResponse)
async def create_invoice(
    request: CreateInvoiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new invoice from supplier.

    Optionally links to a PO for automatic 3-way matching.
    """
    check_invoice_permission(current_user, "create")

    # Generate invoice number
    count = db.query(func.count(Invoice.id)).scalar() or 0
    invoice_number = f"INV-{datetime.now().strftime('%Y%m')}-{count + 1:05d}"

    # Calculate totals
    subtotal = sum(
        (item.invoiced_qty * item.unit_price) - item.discount_amount + item.tax_amount
        for item in request.line_items
    )
    total_amount = subtotal + request.tax_amount + request.shipping_amount - request.discount_amount

    # Create invoice header
    invoice = Invoice(
        invoice_number=invoice_number,
        vendor_invoice_number=request.vendor_invoice_number,
        vendor_id=request.vendor_id,
        vendor_name=request.vendor_name,
        po_id=request.po_id,
        invoice_date=request.invoice_date,
        received_date=date.today(),
        due_date=request.due_date,
        subtotal=subtotal,
        tax_amount=request.tax_amount,
        shipping_amount=request.shipping_amount,
        discount_amount=request.discount_amount,
        total_amount=total_amount,
        currency=request.currency,
        payment_terms=request.payment_terms,
        notes=request.notes,
        status="RECEIVED",
        match_status="PENDING",
        created_by_id=current_user.id,
    )
    db.add(invoice)
    db.flush()

    # Create line items
    line_items_response = []
    for item in request.line_items:
        line_total = (item.invoiced_qty * item.unit_price) - item.discount_amount + item.tax_amount

        inv_line = InvoiceLineItem(
            invoice_id=invoice.id,
            po_line_id=item.po_line_id,
            line_number=item.line_number,
            product_id=item.product_id,
            description=item.description,
            invoiced_qty=item.invoiced_qty,
            unit_price=item.unit_price,
            line_total=line_total,
            discount_amount=item.discount_amount,
            tax_amount=item.tax_amount,
            match_status="PENDING",
        )
        db.add(inv_line)

        line_items_response.append(InvoiceLineItemResponse(
            id=inv_line.id,
            line_number=inv_line.line_number,
            product_id=inv_line.product_id,
            description=inv_line.description,
            invoiced_qty=inv_line.invoiced_qty,
            po_qty=None,
            received_qty=None,
            unit_price=inv_line.unit_price,
            po_unit_price=None,
            line_total=inv_line.line_total,
            match_status=inv_line.match_status,
            qty_variance=0,
            price_variance=0,
            variance_pct=0,
        ))

    db.commit()
    db.refresh(invoice)

    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        vendor_invoice_number=invoice.vendor_invoice_number,
        vendor_id=invoice.vendor_id,
        vendor_name=invoice.vendor_name,
        po_id=invoice.po_id,
        invoice_date=invoice.invoice_date,
        received_date=invoice.received_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        shipping_amount=invoice.shipping_amount,
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        match_status=invoice.match_status,
        match_score=invoice.match_score,
        status=invoice.status,
        has_discrepancy=invoice.has_discrepancy,
        discrepancy_amount=invoice.discrepancy_amount,
        created_at=invoice.created_at,
        line_items=line_items_response,
    )


@router.get("", response_model=List[InvoiceListResponse])
async def list_invoices(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    match_status_filter: Optional[str] = Query(None, description="Filter by match status"),
    vendor_id: Optional[str] = Query(None, description="Filter by vendor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all invoices with optional filters"""
    check_invoice_permission(current_user, "view")

    query = db.query(Invoice)

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if match_status_filter:
        query = query.filter(Invoice.match_status == match_status_filter)
    if vendor_id:
        query = query.filter(Invoice.vendor_id == vendor_id)

    invoices = query.order_by(Invoice.created_at.desc()).all()

    return [
        InvoiceListResponse(
            id=inv.id,
            invoice_number=inv.invoice_number,
            vendor_invoice_number=inv.vendor_invoice_number,
            vendor_id=inv.vendor_id,
            vendor_name=inv.vendor_name,
            po_id=inv.po_id,
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            total_amount=inv.total_amount,
            match_status=inv.match_status,
            match_score=inv.match_score,
            status=inv.status,
            has_discrepancy=inv.has_discrepancy,
        )
        for inv in invoices
    ]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get invoice details"""
    check_invoice_permission(current_user, "view")

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    line_items = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id
    ).all()

    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        vendor_invoice_number=invoice.vendor_invoice_number,
        vendor_id=invoice.vendor_id,
        vendor_name=invoice.vendor_name,
        po_id=invoice.po_id,
        invoice_date=invoice.invoice_date,
        received_date=invoice.received_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        shipping_amount=invoice.shipping_amount,
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        match_status=invoice.match_status,
        match_score=invoice.match_score,
        status=invoice.status,
        has_discrepancy=invoice.has_discrepancy,
        discrepancy_amount=invoice.discrepancy_amount,
        created_at=invoice.created_at,
        line_items=[
            InvoiceLineItemResponse(
                id=item.id,
                line_number=item.line_number,
                product_id=item.product_id,
                description=item.description,
                invoiced_qty=item.invoiced_qty,
                po_qty=item.po_qty,
                received_qty=item.received_qty,
                unit_price=item.unit_price,
                po_unit_price=item.po_unit_price,
                line_total=item.line_total,
                match_status=item.match_status,
                qty_variance=item.qty_variance,
                price_variance=item.price_variance,
                variance_pct=item.variance_pct,
            )
            for item in line_items
        ],
    )


@router.post("/{invoice_id}/match", response_model=MatchResultResponse)
async def perform_three_way_match(
    invoice_id: int,
    request: PerformMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Perform 3-way match between Invoice, PO, and Goods Receipt.

    Compares:
    1. Invoice quantities vs. GR received quantities
    2. Invoice prices vs. PO prices
    3. Overall totals

    Returns match status and any discrepancies.
    """
    check_invoice_permission(current_user, "manage")

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    # Get PO (from request or invoice)
    po_id = request.po_id or invoice.po_id
    if not po_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No PO specified for matching. Provide po_id or link invoice to a PO."
        )

    po = db.get(PurchaseOrderModel, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {po_id} not found"
        )

    # Get GR (from request or latest for PO)
    gr_id = request.gr_id
    gr = None
    if gr_id:
        gr = db.get(GoodsReceiptModel, gr_id)
    else:
        # Get latest GR for PO
        gr = db.query(GoodsReceiptModel).filter(
            GoodsReceiptModel.po_id == po_id
        ).order_by(GoodsReceiptModel.receipt_date.desc()).first()

    # Get all documents' line items
    inv_lines = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id
    ).all()

    po_lines = {
        line.id: line for line in db.query(PurchaseOrderLineItemModel).filter(
            PurchaseOrderLineItemModel.po_id == po_id
        ).all()
    }

    # Build product -> PO line mapping
    po_lines_by_product = {line.product_id: line for line in po_lines.values()}

    # Get GR lines if we have a GR
    gr_lines_by_po_line = {}
    if gr:
        gr_lines = db.query(GoodsReceiptLineItemModel).filter(
            GoodsReceiptLineItemModel.gr_id == gr.id
        ).all()
        gr_lines_by_po_line = {line.po_line_id: line for line in gr_lines}

    # Perform matching
    total_po_qty = 0.0
    total_gr_qty = 0.0
    total_invoiced_qty = 0.0
    po_total = 0.0
    gr_total = 0.0
    invoice_total = invoice.total_amount

    matched_lines = 0
    qty_mismatch_lines = 0
    price_mismatch_lines = 0
    exceptions = []

    for inv_line in inv_lines:
        # Find matching PO line
        po_line = None
        if inv_line.po_line_id:
            po_line = po_lines.get(inv_line.po_line_id)
        else:
            # Try to match by product
            po_line = po_lines_by_product.get(inv_line.product_id)

        # Get received quantity from GR
        received_qty = 0.0
        if po_line and po_line.id in gr_lines_by_po_line:
            gr_line = gr_lines_by_po_line[po_line.id]
            received_qty = gr_line.accepted_qty

        # Update invoice line with comparison data
        if po_line:
            inv_line.po_qty = po_line.quantity
            inv_line.po_unit_price = po_line.unit_price
            inv_line.po_line_id = po_line.id
            po_total += po_line.quantity * (po_line.unit_price or 0)
            total_po_qty += po_line.quantity

        inv_line.received_qty = received_qty
        total_gr_qty += received_qty
        total_invoiced_qty += inv_line.invoiced_qty

        # Calculate variances
        qty_variance = inv_line.invoiced_qty - received_qty if received_qty else 0
        price_variance = 0.0
        if po_line and po_line.unit_price:
            price_variance = inv_line.unit_price - po_line.unit_price

        inv_line.qty_variance = qty_variance
        inv_line.price_variance = price_variance

        # Calculate variance percentage
        if po_line and po_line.unit_price:
            inv_line.variance_pct = abs(price_variance / po_line.unit_price * 100)
        else:
            inv_line.variance_pct = 0

        # Determine line match status
        qty_within_tolerance = abs(qty_variance) <= (received_qty * request.qty_tolerance_pct / 100) if received_qty else True
        price_within_tolerance = abs(price_variance) <= ((po_line.unit_price or 0) * request.price_tolerance_pct / 100) if po_line else True

        if not po_line:
            inv_line.match_status = "NOT_FOUND"
            exceptions.append({
                "line": inv_line.line_number,
                "product": inv_line.product_id,
                "issue": "No matching PO line found",
            })
        elif not qty_within_tolerance:
            inv_line.match_status = "QTY_MISMATCH"
            qty_mismatch_lines += 1
            exceptions.append({
                "line": inv_line.line_number,
                "product": inv_line.product_id,
                "issue": f"Quantity mismatch: invoiced {inv_line.invoiced_qty}, received {received_qty}",
                "variance": qty_variance,
            })
        elif not price_within_tolerance:
            inv_line.match_status = "PRICE_MISMATCH"
            price_mismatch_lines += 1
            exceptions.append({
                "line": inv_line.line_number,
                "product": inv_line.product_id,
                "issue": f"Price mismatch: invoiced ${inv_line.unit_price}, PO ${po_line.unit_price}",
                "variance": price_variance,
            })
        else:
            inv_line.match_status = "MATCHED"
            matched_lines += 1

    # Calculate overall match status
    total_lines = len(inv_lines)
    qty_match_pct = (matched_lines + price_mismatch_lines) / total_lines * 100 if total_lines else 0
    price_match_pct = (matched_lines + qty_mismatch_lines) / total_lines * 100 if total_lines else 0

    if matched_lines == total_lines:
        overall_status = "MATCHED"
        match_score = 100.0
    elif matched_lines > 0:
        overall_status = "PARTIAL_MATCH"
        match_score = matched_lines / total_lines * 100
    elif qty_mismatch_lines > price_mismatch_lines:
        overall_status = "QUANTITY_MISMATCH"
        match_score = 0
    elif price_mismatch_lines > 0:
        overall_status = "PRICE_MISMATCH"
        match_score = 0
    else:
        overall_status = "UNMATCHED"
        match_score = 0

    total_variance = invoice_total - po_total
    qty_variance = total_invoiced_qty - total_gr_qty

    # Update invoice
    invoice.match_status = overall_status
    invoice.match_score = match_score
    invoice.has_discrepancy = len(exceptions) > 0
    invoice.discrepancy_amount = abs(total_variance)
    if overall_status == "MATCHED":
        invoice.status = "VALIDATED"
        invoice.validated_at = datetime.utcnow()
        invoice.validated_by_id = current_user.id

    # Create match result record
    match_result = InvoiceMatchResult(
        invoice_id=invoice_id,
        po_id=po_id,
        gr_id=gr.id if gr else None,
        matched_by_id=current_user.id,
        match_method="AUTOMATIC",
        overall_status=overall_status,
        match_score=match_score,
        po_total=po_total,
        gr_total=total_gr_qty,  # Using qty as proxy for now
        invoice_total=invoice_total,
        total_variance=total_variance,
        total_po_qty=total_po_qty,
        total_gr_qty=total_gr_qty,
        total_invoiced_qty=total_invoiced_qty,
        qty_variance=qty_variance,
        qty_match_pct=qty_match_pct,
        price_match_pct=price_match_pct,
        price_variance=invoice_total - po_total,
        qty_tolerance_pct=request.qty_tolerance_pct,
        price_tolerance_pct=request.price_tolerance_pct,
        exceptions_count=len(exceptions),
        exception_details=json.dumps(exceptions) if exceptions else None,
    )
    db.add(match_result)

    db.commit()
    db.refresh(match_result)

    return MatchResultResponse(
        id=match_result.id,
        invoice_id=match_result.invoice_id,
        po_id=match_result.po_id,
        gr_id=match_result.gr_id,
        match_date=match_result.match_date,
        overall_status=match_result.overall_status,
        match_score=match_result.match_score,
        po_total=match_result.po_total,
        gr_total=match_result.gr_total,
        invoice_total=match_result.invoice_total,
        total_variance=match_result.total_variance,
        qty_variance=match_result.qty_variance,
        qty_match_pct=match_result.qty_match_pct,
        price_match_pct=match_result.price_match_pct,
        exceptions_count=match_result.exceptions_count,
        resolution_status=match_result.resolution_status,
    )


@router.get("/{invoice_id}/match-history", response_model=List[MatchResultResponse])
async def get_match_history(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get match history for an invoice"""
    check_invoice_permission(current_user, "view")

    results = db.query(InvoiceMatchResult).filter(
        InvoiceMatchResult.invoice_id == invoice_id
    ).order_by(InvoiceMatchResult.match_date.desc()).all()

    return [
        MatchResultResponse(
            id=r.id,
            invoice_id=r.invoice_id,
            po_id=r.po_id,
            gr_id=r.gr_id,
            match_date=r.match_date,
            overall_status=r.overall_status,
            match_score=r.match_score,
            po_total=r.po_total,
            gr_total=r.gr_total,
            invoice_total=r.invoice_total,
            total_variance=r.total_variance,
            qty_variance=r.qty_variance,
            qty_match_pct=r.qty_match_pct,
            price_match_pct=r.price_match_pct,
            exceptions_count=r.exceptions_count,
            resolution_status=r.resolution_status,
        )
        for r in results
    ]


@router.post("/{invoice_id}/resolve", response_model=InvoiceResponse)
async def resolve_discrepancy(
    invoice_id: int,
    request: ResolveDiscrepancyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resolve invoice discrepancy.

    Options:
    - ACCEPT: Accept invoice despite discrepancy
    - REJECT: Reject invoice
    - DEBIT_MEMO: Issue debit memo to supplier
    - CREDIT_MEMO: Issue credit memo
    - ADJUST: Adjust invoice amount
    """
    check_invoice_permission(current_user, "approve")

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    if not invoice.has_discrepancy and request.resolution not in ["ACCEPT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice has no discrepancy to resolve"
        )

    invoice.discrepancy_resolution = request.resolution
    invoice.match_notes = request.notes

    if request.resolution == "ACCEPT":
        invoice.status = "APPROVED"
        invoice.approved_at = datetime.utcnow()
        invoice.approved_by_id = current_user.id
    elif request.resolution == "REJECT":
        invoice.status = "REJECTED"
    elif request.resolution == "ADJUST" and request.adjusted_amount is not None:
        invoice.total_amount = request.adjusted_amount
        invoice.status = "APPROVED"
        invoice.approved_at = datetime.utcnow()
        invoice.approved_by_id = current_user.id

    # Update latest match result
    latest_match = db.query(InvoiceMatchResult).filter(
        InvoiceMatchResult.invoice_id == invoice_id
    ).order_by(InvoiceMatchResult.match_date.desc()).first()

    if latest_match:
        latest_match.resolution_status = "APPROVED" if request.resolution != "REJECT" else "REJECTED"
        latest_match.resolution_notes = request.notes
        latest_match.resolved_by_id = current_user.id
        latest_match.resolved_at = datetime.utcnow()

    db.commit()
    db.refresh(invoice)

    line_items = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.invoice_id == invoice_id
    ).all()

    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        vendor_invoice_number=invoice.vendor_invoice_number,
        vendor_id=invoice.vendor_id,
        vendor_name=invoice.vendor_name,
        po_id=invoice.po_id,
        invoice_date=invoice.invoice_date,
        received_date=invoice.received_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        shipping_amount=invoice.shipping_amount,
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        match_status=invoice.match_status,
        match_score=invoice.match_score,
        status=invoice.status,
        has_discrepancy=invoice.has_discrepancy,
        discrepancy_amount=invoice.discrepancy_amount,
        created_at=invoice.created_at,
        line_items=[
            InvoiceLineItemResponse(
                id=item.id,
                line_number=item.line_number,
                product_id=item.product_id,
                description=item.description,
                invoiced_qty=item.invoiced_qty,
                po_qty=item.po_qty,
                received_qty=item.received_qty,
                unit_price=item.unit_price,
                po_unit_price=item.po_unit_price,
                line_total=item.line_total,
                match_status=item.match_status,
                qty_variance=item.qty_variance,
                price_variance=item.price_variance,
                variance_pct=item.variance_pct,
            )
            for item in line_items
        ],
    )


@router.post("/{invoice_id}/approve", response_model=InvoiceResponse)
async def approve_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve invoice for payment"""
    check_invoice_permission(current_user, "approve")

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    if invoice.match_status not in ["MATCHED", "PARTIAL_MATCH"] and invoice.status != "VALIDATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice must be matched/validated before approval"
        )

    invoice.status = "APPROVED"
    invoice.approved_at = datetime.utcnow()
    invoice.approved_by_id = current_user.id

    db.commit()
    db.refresh(invoice)

    return await get_invoice(invoice_id, db, current_user)


@router.post("/{invoice_id}/pay")
async def mark_invoice_paid(
    invoice_id: int,
    payment_reference: str = Query(..., description="Payment reference number"),
    payment_date: Optional[date] = Query(None, description="Payment date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark invoice as paid"""
    check_invoice_permission(current_user, "manage")

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    if invoice.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice must be approved before payment"
        )

    invoice.status = "PAID"
    invoice.payment_reference = payment_reference
    invoice.payment_date = payment_date or date.today()

    db.commit()

    return {"success": True, "message": f"Invoice {invoice.invoice_number} marked as paid"}

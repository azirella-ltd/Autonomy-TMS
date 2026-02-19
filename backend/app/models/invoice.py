"""
Invoice and Invoice Matching Database Models

Supports 3-way matching between:
1. Purchase Order (what was ordered)
2. Goods Receipt (what was received)
3. Invoice (what supplier bills)

Match statuses:
- MATCHED: All three documents agree within tolerance
- QUANTITY_MISMATCH: Invoiced qty differs from received qty
- PRICE_MISMATCH: Invoiced price differs from PO price
- UNMATCHED: No matching GR or PO found
- PARTIAL_MATCH: Some lines match, others don't
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Double,
    ForeignKey,
    DateTime,
    Date,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional, List
from .base import Base


class Invoice(Base):
    """
    Supplier Invoice Header

    Represents an invoice received from a supplier for goods/services.
    Links to one or more POs for 3-way matching.
    """
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Invoice identification
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    vendor_invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)  # Supplier's invoice number

    # Vendor info
    vendor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Reference to PO (primary PO for this invoice)
    po_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("purchase_order.id"))

    # Dates
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    payment_date: Mapped[Optional[date]] = mapped_column(Date)

    # Amounts
    subtotal: Mapped[float] = mapped_column(Double, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Double, default=0.0)
    shipping_amount: Mapped[float] = mapped_column(Double, default=0.0)
    discount_amount: Mapped[float] = mapped_column(Double, default=0.0)
    total_amount: Mapped[float] = mapped_column(Double, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # 3-Way Match Status
    match_status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
        comment="PENDING, MATCHED, QUANTITY_MISMATCH, PRICE_MISMATCH, UNMATCHED, PARTIAL_MATCH, APPROVED, REJECTED"
    )
    match_score: Mapped[float] = mapped_column(Double, default=0.0)  # 0-100 match confidence
    match_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Invoice Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="RECEIVED",
        nullable=False,
        comment="RECEIVED, VALIDATED, APPROVED, REJECTED, PAID, CANCELLED"
    )

    # Payment info
    payment_terms: Mapped[Optional[str]] = mapped_column(String(50))  # NET30, NET60, etc.
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100))

    # Discrepancy handling
    has_discrepancy: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancy_amount: Mapped[float] = mapped_column(Double, default=0.0)
    discrepancy_reason: Mapped[Optional[str]] = mapped_column(String(500))
    discrepancy_resolution: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="ACCEPT, REJECT, DEBIT_MEMO, CREDIT_MEMO, ADJUST"
    )

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Audit
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    validated_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    approved_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")
    match_results = relationship("InvoiceMatchResult", back_populates="invoice", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_invoice_vendor', 'vendor_id'),
        Index('idx_invoice_po', 'po_id'),
        Index('idx_invoice_status', 'status'),
        Index('idx_invoice_match_status', 'match_status'),
        Index('idx_invoice_date', 'invoice_date'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invoice_number": self.invoice_number,
            "vendor_invoice_number": self.vendor_invoice_number,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "po_id": self.po_id,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "subtotal": self.subtotal,
            "tax_amount": self.tax_amount,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "match_status": self.match_status,
            "match_score": self.match_score,
            "status": self.status,
            "has_discrepancy": self.has_discrepancy,
            "discrepancy_amount": self.discrepancy_amount,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class InvoiceLineItem(Base):
    """
    Invoice Line Item

    Individual line on an invoice, linked to PO line for matching.
    """
    __tablename__ = "invoice_line_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # References
    invoice_id: Mapped[int] = mapped_column(Integer, ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False)
    po_line_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("purchase_order_line_item.id"))

    # Line details
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    # Quantities
    invoiced_qty: Mapped[float] = mapped_column(Double, nullable=False)
    po_qty: Mapped[Optional[float]] = mapped_column(Double)  # From PO for comparison
    received_qty: Mapped[Optional[float]] = mapped_column(Double)  # From GR for comparison

    # Pricing
    unit_price: Mapped[float] = mapped_column(Double, nullable=False)
    po_unit_price: Mapped[Optional[float]] = mapped_column(Double)  # From PO for comparison
    line_total: Mapped[float] = mapped_column(Double, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Double, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Double, default=0.0)

    # Match status
    match_status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        comment="PENDING, MATCHED, QTY_MISMATCH, PRICE_MISMATCH, NOT_FOUND"
    )
    qty_variance: Mapped[float] = mapped_column(Double, default=0.0)  # invoiced - received
    price_variance: Mapped[float] = mapped_column(Double, default=0.0)  # invoiced - PO price
    variance_pct: Mapped[float] = mapped_column(Double, default=0.0)  # Variance as percentage

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")

    __table_args__ = (
        Index('idx_inv_line_invoice', 'invoice_id'),
        Index('idx_inv_line_po_line', 'po_line_id'),
        Index('idx_inv_line_product', 'product_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "po_line_id": self.po_line_id,
            "line_number": self.line_number,
            "product_id": self.product_id,
            "description": self.description,
            "invoiced_qty": self.invoiced_qty,
            "po_qty": self.po_qty,
            "received_qty": self.received_qty,
            "unit_price": self.unit_price,
            "po_unit_price": self.po_unit_price,
            "line_total": self.line_total,
            "match_status": self.match_status,
            "qty_variance": self.qty_variance,
            "price_variance": self.price_variance,
            "variance_pct": self.variance_pct,
        }


class InvoiceMatchResult(Base):
    """
    3-Way Match Result Record

    Stores the detailed results of matching an invoice against PO and GR.
    Used for audit trail and dispute resolution.
    """
    __tablename__ = "invoice_match_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # References
    invoice_id: Mapped[int] = mapped_column(Integer, ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False)
    po_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("purchase_order.id"))
    gr_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("goods_receipt.id"))

    # Match execution info
    match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    matched_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    match_method: Mapped[str] = mapped_column(String(50), default="AUTOMATIC")  # AUTOMATIC, MANUAL

    # Overall results
    overall_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="MATCHED, QUANTITY_MISMATCH, PRICE_MISMATCH, PARTIAL_MATCH, UNMATCHED"
    )
    match_score: Mapped[float] = mapped_column(Double, default=0.0)  # 0-100

    # Document totals comparison
    po_total: Mapped[Optional[float]] = mapped_column(Double)
    gr_total: Mapped[Optional[float]] = mapped_column(Double)
    invoice_total: Mapped[float] = mapped_column(Double, nullable=False)
    total_variance: Mapped[float] = mapped_column(Double, default=0.0)

    # Quantity match
    total_po_qty: Mapped[Optional[float]] = mapped_column(Double)
    total_gr_qty: Mapped[Optional[float]] = mapped_column(Double)
    total_invoiced_qty: Mapped[float] = mapped_column(Double, nullable=False)
    qty_variance: Mapped[float] = mapped_column(Double, default=0.0)
    qty_match_pct: Mapped[float] = mapped_column(Double, default=0.0)  # % of lines matching on qty

    # Price match
    price_match_pct: Mapped[float] = mapped_column(Double, default=0.0)  # % of lines matching on price
    price_variance: Mapped[float] = mapped_column(Double, default=0.0)

    # Tolerance used
    qty_tolerance_pct: Mapped[float] = mapped_column(Double, default=2.0)  # Default 2% tolerance
    price_tolerance_pct: Mapped[float] = mapped_column(Double, default=1.0)  # Default 1% tolerance

    # Exception details
    exceptions_count: Mapped[int] = mapped_column(Integer, default=0)
    exception_details: Mapped[Optional[str]] = mapped_column(Text)  # JSON list of issues

    # Resolution
    resolution_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="PENDING, APPROVED, REJECTED, ESCALATED"
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    invoice = relationship("Invoice", back_populates="match_results")

    __table_args__ = (
        Index('idx_match_invoice', 'invoice_id'),
        Index('idx_match_po', 'po_id'),
        Index('idx_match_gr', 'gr_id'),
        Index('idx_match_status', 'overall_status'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "po_id": self.po_id,
            "gr_id": self.gr_id,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "match_method": self.match_method,
            "overall_status": self.overall_status,
            "match_score": self.match_score,
            "po_total": self.po_total,
            "gr_total": self.gr_total,
            "invoice_total": self.invoice_total,
            "total_variance": self.total_variance,
            "qty_variance": self.qty_variance,
            "qty_match_pct": self.qty_match_pct,
            "price_match_pct": self.price_match_pct,
            "price_variance": self.price_variance,
            "exceptions_count": self.exceptions_count,
            "resolution_status": self.resolution_status,
        }

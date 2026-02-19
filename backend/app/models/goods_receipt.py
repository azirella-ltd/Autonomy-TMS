"""
Goods Receipt Database Models

Tracks goods receipt transactions against purchase orders.
Supports:
- Partial receipts (receive in multiple deliveries)
- Quality inspection with accept/reject
- Variance tracking (over/under delivery)
- Receipt history and audit trail
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
from datetime import datetime
from typing import Optional
from .base import Base


class GoodsReceipt(Base):
    """
    Goods Receipt Header - Represents a single receipt transaction

    One PO can have multiple goods receipts (partial deliveries).
    Each receipt has line items corresponding to PO line items.
    """
    __tablename__ = "goods_receipt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Receipt identification
    gr_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Reference to PO
    po_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_order.id", ondelete="CASCADE"), nullable=False)

    # Receipt info
    receipt_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivery_note_number: Mapped[Optional[str]] = mapped_column(String(100))  # Supplier's delivery note/packing slip
    carrier: Mapped[Optional[str]] = mapped_column(String(100))
    tracking_number: Mapped[Optional[str]] = mapped_column(String(200))

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
        comment="PENDING, INSPECTING, COMPLETED, REJECTED"
    )

    # Location
    receiving_site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    receiving_location: Mapped[Optional[str]] = mapped_column(String(100))  # Dock, warehouse location

    # Totals (computed from line items)
    total_received_qty: Mapped[float] = mapped_column(Double, default=0.0)
    total_accepted_qty: Mapped[float] = mapped_column(Double, default=0.0)
    total_rejected_qty: Mapped[float] = mapped_column(Double, default=0.0)

    # Variance tracking
    has_variance: Mapped[bool] = mapped_column(Boolean, default=False)
    variance_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Audit
    received_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    inspected_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    line_items = relationship("GoodsReceiptLineItem", back_populates="goods_receipt", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_gr_po', 'po_id'),
        Index('idx_gr_status', 'status'),
        Index('idx_gr_receipt_date', 'receipt_date'),
        Index('idx_gr_receiving_site', 'receiving_site_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "gr_number": self.gr_number,
            "po_id": self.po_id,
            "receipt_date": self.receipt_date.isoformat() if self.receipt_date else None,
            "delivery_note_number": self.delivery_note_number,
            "carrier": self.carrier,
            "tracking_number": self.tracking_number,
            "status": self.status,
            "receiving_site_id": self.receiving_site_id,
            "receiving_location": self.receiving_location,
            "total_received_qty": self.total_received_qty,
            "total_accepted_qty": self.total_accepted_qty,
            "total_rejected_qty": self.total_rejected_qty,
            "has_variance": self.has_variance,
            "variance_notes": self.variance_notes,
            "notes": self.notes,
            "received_by_id": self.received_by_id,
            "inspected_by_id": self.inspected_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "line_items": [item.to_dict() for item in self.line_items] if self.line_items else [],
        }


class GoodsReceiptLineItem(Base):
    """
    Goods Receipt Line Item - Receipt details for each PO line

    Tracks quantities received, accepted, and rejected per PO line item.
    Supports quality inspection results.
    """
    __tablename__ = "goods_receipt_line_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # References
    gr_id: Mapped[int] = mapped_column(Integer, ForeignKey("goods_receipt.id", ondelete="CASCADE"), nullable=False)
    po_line_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_order_line_item.id"), nullable=False)

    # Line details
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), ForeignKey("product.id"), nullable=False)

    # Quantities
    expected_qty: Mapped[float] = mapped_column(Double, nullable=False)  # From PO
    received_qty: Mapped[float] = mapped_column(Double, nullable=False)  # What was delivered
    accepted_qty: Mapped[float] = mapped_column(Double, default=0.0)  # Passed inspection
    rejected_qty: Mapped[float] = mapped_column(Double, default=0.0)  # Failed inspection

    # Variance
    variance_qty: Mapped[float] = mapped_column(Double, default=0.0)  # received - expected
    variance_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="OVER, UNDER, EXACT"
    )
    variance_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # Quality inspection
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="PENDING, PASSED, FAILED, PARTIAL"
    )
    inspection_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Rejection details
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="DAMAGED, WRONG_ITEM, QUALITY, QUANTITY, OTHER"
    )
    rejection_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Storage location
    put_away_location: Mapped[Optional[str]] = mapped_column(String(100))

    # Batch/lot tracking
    batch_number: Mapped[Optional[str]] = mapped_column(String(100))
    lot_number: Mapped[Optional[str]] = mapped_column(String(100))
    expiry_date: Mapped[Optional[datetime]] = mapped_column(Date)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    goods_receipt = relationship("GoodsReceipt", back_populates="line_items")

    __table_args__ = (
        Index('idx_gr_line_gr', 'gr_id'),
        Index('idx_gr_line_po_line', 'po_line_id'),
        Index('idx_gr_line_product', 'product_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "gr_id": self.gr_id,
            "po_line_id": self.po_line_id,
            "line_number": self.line_number,
            "product_id": self.product_id,
            "expected_qty": self.expected_qty,
            "received_qty": self.received_qty,
            "accepted_qty": self.accepted_qty,
            "rejected_qty": self.rejected_qty,
            "variance_qty": self.variance_qty,
            "variance_type": self.variance_type,
            "variance_reason": self.variance_reason,
            "inspection_required": self.inspection_required,
            "inspection_status": self.inspection_status,
            "inspection_notes": self.inspection_notes,
            "rejection_reason": self.rejection_reason,
            "rejection_notes": self.rejection_notes,
            "put_away_location": self.put_away_location,
            "batch_number": self.batch_number,
            "lot_number": self.lot_number,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
        }

    def calculate_variance(self):
        """Calculate variance from expected quantity"""
        self.variance_qty = self.received_qty - self.expected_qty
        if self.variance_qty > 0:
            self.variance_type = "OVER"
        elif self.variance_qty < 0:
            self.variance_type = "UNDER"
        else:
            self.variance_type = "EXACT"

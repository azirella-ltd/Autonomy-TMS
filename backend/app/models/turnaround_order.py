"""
Turnaround Order Database Models
Sprint 6: Additional Order Types

Turnaround orders are used for return and refurbishment workflows.
Supports reverse logistics, product returns, repairs, and refurbishment processes.
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
    Index,
    JSON,
)
from datetime import datetime
from .base import Base


class TurnaroundOrder(Base):
    """
    Turnaround order header for return and refurbishment workflows

    Turnaround orders represent reverse logistics flows including product returns,
    repairs, refurbishment, and redistribution back into the supply chain.
    """
    __tablename__ = "turnaround_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turnaround_order_number = Column(String(100), unique=True, nullable=False, index=True)

    # Original order reference
    return_order_id = Column(String(40), index=True)  # Original sales/delivery order
    return_order_type = Column(String(50))  # SO, DO, TO (which order type is being returned)
    rma_number = Column(String(100), index=True)  # Return Merchandise Authorization number

    # Customer information
    customer_id = Column(String(40), index=True)
    customer_name = Column(String(200))
    end_customer_id = Column(String(40))  # For B2B2C scenarios

    # Sites - Reverse logistics flow
    from_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Return origin (customer location)
    to_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Return destination (refurb center, warehouse)
    refurbishment_site_id = Column(Integer, ForeignKey("site.id"))  # If different from to_site

    # Configuration
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))

    # AWS SC Compliance fields
    company_id = Column(String(100))  # SC: company identifier
    order_type = Column(String(50), default="turnaround")  # SC: order type
    source = Column(String(100))  # SC: system of record
    source_event_id = Column(String(100))  # SC: event lineage
    source_update_dttm = Column(DateTime)  # SC: last update timestamp

    # Return reason
    return_reason_code = Column(String(50), nullable=False, index=True)
    # Reason codes: DEFECTIVE, WRONG_ITEM, DAMAGED_IN_TRANSIT, CUSTOMER_REMORSE, WARRANTY_CLAIM, END_OF_LEASE, RECALL

    return_reason_description = Column(Text)

    # Return type
    turnaround_type = Column(String(50), nullable=False, index=True)
    # Type values: RETURN, REPAIR, REFURBISH, RECYCLE, SCRAP

    # Status and lifecycle
    status = Column(String(20), nullable=False, default="INITIATED")
    # Status values: INITIATED, APPROVED, IN_TRANSIT, RECEIVED, INSPECTED, REFURBISHING, COMPLETED, REJECTED, SCRAPPED

    # Dates
    order_date = Column(Date, nullable=False)
    return_requested_date = Column(Date)
    return_approved_date = Column(Date)
    pickup_scheduled_date = Column(Date)
    pickup_actual_date = Column(Date)
    received_date = Column(Date)
    inspection_date = Column(Date)
    refurbishment_start_date = Column(Date)
    refurbishment_completion_date = Column(Date)
    disposition_date = Column(Date)  # Final disposition decision date

    # Inspection and disposition
    inspection_status = Column(String(50))  # PASSED, FAILED, PARTIAL, PENDING
    disposition = Column(String(50))  # RETURN_TO_STOCK, REPAIR, REFURBISH, SCRAP, DONATE, SELL_AS_IS
    inspection_notes = Column(Text)

    # Refurbishment details
    refurbishment_required = Column(String(1), default="N")  # Y/N
    refurbishment_type = Column(String(100))  # COSMETIC, FUNCTIONAL, COMPONENT_REPLACEMENT, FULL_REBUILD
    refurbishment_notes = Column(Text)
    refurbishment_cost = Column(Double, default=0.0)

    # Financial tracking
    original_sale_value = Column(Double)  # Original sale price
    refund_amount = Column(Double)  # Amount refunded to customer
    restocking_fee = Column(Double, default=0.0)
    return_shipping_cost = Column(Double, default=0.0)
    total_turnaround_cost = Column(Double, default=0.0)  # Total cost of return + refurb
    recovery_value = Column(Double)  # Expected value after refurbishment
    currency = Column(String(3), default="USD")

    # Quality assessment
    product_condition = Column(String(50))  # NEW, LIKE_NEW, GOOD, FAIR, POOR, DEFECTIVE
    quality_grade = Column(String(10))  # A, B, C, D (grading for resale)
    cosmetic_damage = Column(String(1))  # Y/N
    functional_issues = Column(String(1))  # Y/N
    missing_components = Column(String(1))  # Y/N

    # Warranty and compliance
    warranty_status = Column(String(50))  # IN_WARRANTY, OUT_OF_WARRANTY, EXTENDED_WARRANTY
    warranty_claim_number = Column(String(100))
    regulatory_compliance = Column(String(1), default="Y")  # Y/N - Environmental, safety compliance
    disposal_certification = Column(String(100))  # For scrapped items

    # Transportation
    carrier_id = Column(String(40))
    tracking_number = Column(String(100))
    return_label_number = Column(String(100))

    # Priority
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, URGENT

    # Additional metadata
    notes = Column(Text)
    context_data = Column(JSON)  # Flexible JSON for turnaround-specific data

    # Planning linkage
    planning_run_id = Column(String(100))

    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    received_by_id = Column(Integer, ForeignKey("users.id"))
    inspected_by_id = Column(Integer, ForeignKey("users.id"))
    disposed_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    received_at = Column(DateTime)
    inspected_at = Column(DateTime)
    disposed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_turn_return_order', 'return_order_id'),
        Index('idx_turn_rma', 'rma_number'),
        Index('idx_turn_customer', 'customer_id'),
        Index('idx_turn_from_site', 'from_site_id'),
        Index('idx_turn_to_site', 'to_site_id'),
        Index('idx_turn_status', 'status'),
        Index('idx_turn_type', 'turnaround_type'),
        Index('idx_turn_reason', 'return_reason_code'),
        Index('idx_turn_disposition', 'disposition'),
        Index('idx_turn_config', 'config_id'),
        Index('idx_turn_customer', 'customer_id'),
        Index('idx_turn_company', 'company_id'),
        Index('idx_turn_order_date', 'order_date'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "turnaround_order_number": self.turnaround_order_number,
            "return_order_id": self.return_order_id,
            "rma_number": self.rma_number,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "from_site_id": self.from_site_id,
            "to_site_id": self.to_site_id,
            "return_reason_code": self.return_reason_code,
            "return_reason_description": self.return_reason_description,
            "turnaround_type": self.turnaround_type,
            "status": self.status,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "inspection_status": self.inspection_status,
            "disposition": self.disposition,
            "refurbishment_required": self.refurbishment_required,
            "product_condition": self.product_condition,
            "quality_grade": self.quality_grade,
            "refund_amount": self.refund_amount,
            "total_turnaround_cost": self.total_turnaround_cost,
            "recovery_value": self.recovery_value,
            "currency": self.currency,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TurnaroundOrderLineItem(Base):
    """
    Turnaround order line item - products/items being returned

    Tracks individual items within a turnaround order with detailed
    inspection and disposition information per line.
    """
    __tablename__ = "turnaround_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turnaround_order_id = Column(Integer, ForeignKey("turnaround_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    product_description = Column(String(500))

    # Identification
    serial_number = Column(String(100), index=True)  # For serialized items
    lot_number = Column(String(100))
    batch_number = Column(String(100))

    # Quantities
    quantity_returned = Column(Double, nullable=False)
    quantity_accepted = Column(Double, default=0.0)
    quantity_rejected = Column(Double, default=0.0)
    quantity_scrapped = Column(Double, default=0.0)
    quantity_refurbished = Column(Double, default=0.0)
    quantity_returned_to_stock = Column(Double, default=0.0)

    # Unit of measure
    uom = Column(String(20), default="EA")

    # Line-specific inspection
    line_inspection_status = Column(String(50))  # PASSED, FAILED, PARTIAL
    line_condition = Column(String(50))  # Condition of this specific item
    line_disposition = Column(String(50))  # Disposition for this line
    inspection_notes = Column(Text)

    # Defect tracking
    defect_codes = Column(JSON)  # List of defect codes found
    defect_description = Column(Text)

    # Financial (line-level)
    original_unit_price = Column(Double)
    refund_unit_price = Column(Double)
    line_refund_total = Column(Double)
    line_refurbishment_cost = Column(Double, default=0.0)

    # Status
    status = Column(String(20), default="PENDING")  # PENDING, INSPECTED, PROCESSING, COMPLETED

    # Dates
    received_date = Column(Date)
    inspected_date = Column(Date)
    disposition_date = Column(Date)

    # Notes
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_turn_line_order', 'turnaround_order_id'),
        Index('idx_turn_line_product', 'product_id'),
        Index('idx_turn_line_number', 'turnaround_order_id', 'line_number'),
        Index('idx_turn_line_serial', 'serial_number'),
        Index('idx_turn_line_status', 'status'),
        Index('idx_turn_line_disposition', 'line_disposition'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "line_number": self.line_number,
            "product_id": self.product_id,
            "product_description": self.product_description,
            "serial_number": self.serial_number,
            "quantity_returned": self.quantity_returned,
            "quantity_accepted": self.quantity_accepted,
            "quantity_rejected": self.quantity_rejected,
            "line_inspection_status": self.line_inspection_status,
            "line_condition": self.line_condition,
            "line_disposition": self.line_disposition,
            "defect_codes": self.defect_codes or [],
            "refund_unit_price": self.refund_unit_price,
            "line_refund_total": self.line_refund_total,
            "status": self.status,
            "uom": self.uom,
        }

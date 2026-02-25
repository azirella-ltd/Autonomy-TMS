"""
Purchase Order Database Models

Stores purchase orders and line items for vendor procurement.
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
)
from datetime import datetime
from .base import Base


class PurchaseOrder(Base):
    """Purchase order header"""
    __tablename__ = "purchase_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_number = Column(String(100), unique=True, nullable=False, index=True)

    # Vendor and sites
    vendor_id = Column(String(100))  # External vendor identifier
    supplier_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    destination_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Configuration
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))

    # SC Compliance fields
    company_id = Column(String(100))  # SC: company identifier
    order_type = Column(String(50), default="po")  # SC: po, blanket_po, requisition
    supplier_reference_id = Column(String(100))  # SC: vendor's order reference
    source = Column(String(100))  # SC: system of record
    source_event_id = Column(String(100))  # SC: event lineage
    source_update_dttm = Column(DateTime)  # SC: last update timestamp

    # Status and dates
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT, APPROVED, SENT, ACKNOWLEDGED, RECEIVED, CANCELLED
    order_date = Column(Date, nullable=False)
    requested_delivery_date = Column(Date)
    promised_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Financial
    total_amount = Column(Double, default=0.0)
    currency = Column(String(3), default="USD")

    # Tracking
    notes = Column(Text)
    acknowledgment_number = Column(String(100))  # Vendor's PO confirmation number

    # Source tracking (if generated from MRP)
    mrp_run_id = Column(String(100))  # Link to MRP run that generated this PO
    planning_run_id = Column(String(100))

    # Simulation extensions
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"))  # Link to simulation session
    order_round = Column(Integer)  # Round when PO was created

    # Audit
    created_by_id = Column(Integer, ForeignKey("users.id"))
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    received_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    sent_at = Column(DateTime)
    acknowledged_at = Column(DateTime)
    received_at = Column(DateTime)

    __table_args__ = (
        Index('idx_po_vendor', 'vendor_id'),
        Index('idx_po_supplier_site', 'supplier_site_id'),
        Index('idx_po_dest_site', 'destination_site_id'),
        Index('idx_po_status', 'status'),
        Index('idx_po_order_date', 'order_date'),
        Index('idx_po_config', 'config_id'),
        Index('idx_po_customer', 'customer_id'),
        Index('idx_po_mrp_run', 'mrp_run_id'),
        Index('idx_po_company', 'company_id'),
        Index('idx_po_order_type', 'order_type'),
        Index('idx_po_scenario_round', 'scenario_id', 'order_round'),
    )


class PurchaseOrderLineItem(Base):
    """Purchase order line item"""
    __tablename__ = "purchase_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(Integer, ForeignKey("purchase_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # Quantities
    quantity = Column(Double, nullable=False)
    shipped_quantity = Column(Double, default=0.0)  # Simulation: fulfilled amount (vs. received_quantity which is after receipt)
    received_quantity = Column(Double, default=0.0)
    rejected_quantity = Column(Double, default=0.0)

    # Pricing
    unit_price = Column(Double)
    line_total = Column(Double)
    discount_percent = Column(Double, default=0.0)

    # Dates
    requested_delivery_date = Column(Date, nullable=False)
    promised_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Notes
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_po_line_po', 'po_id'),
        Index('idx_po_line_product', 'product_id'),
        Index('idx_po_line_number', 'po_id', 'line_number'),
    )

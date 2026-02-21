"""
Quality Order Database Models
Sprint 7: Additional Order Types for Powell TRM Framework

Quality orders manage quality inspection, disposition, and control processes.
Supports incoming inspection, in-process inspection, and final inspection workflows.

AWS SC Entity: quality_order (Extension)

Quality Order Lifecycle:
1. CREATED - Quality order created (triggered by goods receipt, production milestone, or complaint)
2. INSPECTION_PENDING - Awaiting inspector assignment
3. IN_INSPECTION - Inspector performing quality checks
4. DISPOSITION_PENDING - Inspection complete, awaiting disposition decision
5. DISPOSITION_DECIDED - Disposition decided (accept, reject, rework, scrap, use-as-is)
6. CLOSED - All disposition actions completed
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Double,
    Float,
    ForeignKey,
    DateTime,
    Date,
    Text,
    Index,
    JSON,
    Boolean,
)
from datetime import datetime
from .base import Base


class QualityOrder(Base):
    """
    Quality Order header for quality inspection and disposition.

    AWS SC Entity: quality_order (Extension)
    Manages quality inspection workflows triggered by:
    - Goods receipt (incoming material inspection)
    - Production milestones (in-process quality checks)
    - Customer complaints (returns inspection)
    - Preventive sampling (statistical quality control)
    """
    __tablename__ = "quality_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quality_order_number = Column(String(100), unique=True, nullable=False, index=True)

    # AWS SC Core Fields
    company_id = Column(String(100))
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    # SC source tracking
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Inspection type
    inspection_type = Column(String(50), nullable=False, index=True)
    # Values: INCOMING, IN_PROCESS, FINAL, RETURNS, SAMPLING, COMPLAINT

    # Status lifecycle
    status = Column(String(30), nullable=False, default="CREATED", index=True)
    # Values: CREATED, INSPECTION_PENDING, IN_INSPECTION, DISPOSITION_PENDING, DISPOSITION_DECIDED, CLOSED, CANCELLED

    # Origin - what triggered this quality order
    origin_type = Column(String(50), nullable=False)
    # Values: GOODS_RECEIPT, PRODUCTION_ORDER, CUSTOMER_COMPLAINT, PREVENTIVE_SAMPLE, TRANSFER_RECEIPT
    origin_order_id = Column(String(100))  # PO number, MO number, complaint ID, etc.
    origin_order_type = Column(String(50))  # purchase_order, production_order, service_order, transfer_order

    # Product being inspected
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)
    lot_number = Column(String(100), index=True)
    batch_number = Column(String(100))
    serial_number = Column(String(100))

    # Quantities
    inspection_quantity = Column(Double, nullable=False)
    sample_size = Column(Double)  # For sampling inspection
    accepted_quantity = Column(Double, default=0.0)
    rejected_quantity = Column(Double, default=0.0)
    rework_quantity = Column(Double, default=0.0)
    scrap_quantity = Column(Double, default=0.0)
    use_as_is_quantity = Column(Double, default=0.0)

    # Disposition decision
    disposition = Column(String(30))
    # Values: ACCEPT, REJECT, REWORK, SCRAP, USE_AS_IS, RETURN_TO_VENDOR, CONDITIONAL_ACCEPT
    disposition_reason = Column(Text)
    disposition_decided_by_id = Column(Integer, ForeignKey("users.id"))
    disposition_decided_at = Column(DateTime)

    # Quality metrics
    defect_rate = Column(Float)  # Defects per unit or %
    defect_category = Column(String(100))  # Visual, dimensional, functional, chemical, etc.
    severity_level = Column(String(20), default="MINOR")  # MINOR, MAJOR, CRITICAL
    nonconformance_id = Column(String(100))  # Link to NCR (Non-Conformance Report)

    # Inspection plan
    inspection_plan_id = Column(String(100))  # Reference to quality inspection plan
    aql_level = Column(String(20))  # Acceptable Quality Level
    sampling_standard = Column(String(50))  # e.g., MIL-STD-1916, ISO 2859

    # Vendor context (for incoming inspection)
    vendor_id = Column(String(100))
    vendor_lot = Column(String(100))

    # Dates
    order_date = Column(Date, nullable=False)
    inspection_start_date = Column(DateTime)
    inspection_end_date = Column(DateTime)
    disposition_due_date = Column(Date)  # SLA for disposition decision

    # Cost tracking
    inspection_cost = Column(Double, default=0.0)
    rework_cost = Column(Double, default=0.0)
    scrap_cost = Column(Double, default=0.0)
    total_quality_cost = Column(Double, default=0.0)
    currency = Column(String(3), default="USD")

    # Inspector assignment
    inspector_id = Column(Integer, ForeignKey("users.id"))
    supervisor_id = Column(Integer, ForeignKey("users.id"))

    # Results
    inspection_results = Column(JSON)  # Structured inspection results
    test_results = Column(JSON)  # Lab test results
    measurement_data = Column(JSON)  # Dimensional/measurement data
    photos = Column(JSON)  # Photo evidence references

    # Notes and context
    notes = Column(Text)
    corrective_action_required = Column(Boolean, default=False)
    corrective_action_id = Column(String(100))  # Link to CAPA

    # Planning linkage
    mrp_impact = Column(Boolean, default=False)  # Does disposition affect MRP?
    hold_inventory = Column(Boolean, default=True)  # Is inventory on hold during inspection?

    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    closed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_qo_site', 'site_id'),
        Index('idx_qo_config', 'config_id'),
        Index('idx_qo_group', 'group_id'),
        Index('idx_qo_company', 'company_id'),
        Index('idx_qo_product', 'product_id'),
        Index('idx_qo_status', 'status'),
        Index('idx_qo_inspection_type', 'inspection_type'),
        Index('idx_qo_disposition', 'disposition'),
        Index('idx_qo_origin', 'origin_type', 'origin_order_id'),
        Index('idx_qo_lot', 'lot_number'),
        Index('idx_qo_vendor', 'vendor_id'),
        Index('idx_qo_order_date', 'order_date'),
        Index('idx_qo_severity', 'severity_level'),
    )


class QualityOrderLineItem(Base):
    """
    Quality Order Line Item - individual inspection checks/characteristics.

    Each line item represents a specific quality characteristic being inspected.
    """
    __tablename__ = "quality_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quality_order_id = Column(Integer, ForeignKey("quality_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    characteristic_name = Column(String(200), nullable=False)
    characteristic_type = Column(String(50))  # QUANTITATIVE, QUALITATIVE, ATTRIBUTE

    # Specification
    specification = Column(String(200))
    target_value = Column(Double)
    lower_limit = Column(Double)
    upper_limit = Column(Double)
    unit_of_measure = Column(String(20))

    # Results
    measured_value = Column(Double)
    measured_text = Column(String(500))  # For qualitative results
    result = Column(String(20))  # PASS, FAIL, CONDITIONAL
    defect_count = Column(Integer, default=0)

    # Inspector details
    inspected_by_id = Column(Integer, ForeignKey("users.id"))
    inspected_at = Column(DateTime)

    # Notes
    notes = Column(Text)
    measurement_instrument = Column(String(100))  # Calibrated instrument used

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_qo_line_order', 'quality_order_id'),
        Index('idx_qo_line_number', 'quality_order_id', 'line_number'),
        Index('idx_qo_line_result', 'result'),
    )

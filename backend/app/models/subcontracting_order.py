"""
Subcontracting Order Database Models
Sprint 7: Additional Order Types for Powell TRM Framework

Subcontracting orders manage external manufacturing where materials are
provided to a subcontractor who performs manufacturing operations and
returns the finished/semi-finished product.

AWS SC Entity: subcontracting_order (Extension)

Subcontracting Order Lifecycle:
1. PLANNED - Created from MPS/MRP, not yet released
2. RELEASED - Released to procurement for vendor selection
3. MATERIAL_SENT - Raw materials shipped to subcontractor
4. IN_PRODUCTION - Subcontractor performing manufacturing
5. GOODS_RECEIVED - Finished goods received back
6. QUALITY_CHECK - Under incoming quality inspection
7. CLOSED - All activities complete
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


class SubcontractingOrder(Base):
    """
    Subcontracting Order header for external manufacturing.

    AWS SC Entity: subcontracting_order (Extension)
    Manages toll manufacturing / subcontracting workflows where:
    - Company provides raw materials to subcontractor
    - Subcontractor performs manufacturing operations
    - Subcontractor returns finished/semi-finished goods
    """
    __tablename__ = "subcontracting_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subcontract_order_number = Column(String(100), unique=True, nullable=False, index=True)

    # AWS SC Core Fields
    company_id = Column(String(100))
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)  # Originating site
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    # SC source tracking
    source = Column(String(100))
    source_event_id = Column(String(100))
    source_update_dttm = Column(DateTime)

    # Subcontractor details
    subcontractor_id = Column(String(100), nullable=False, index=True)  # Vendor/subcontractor
    subcontractor_site_id = Column(Integer, ForeignKey("site.id"))  # Subcontractor's facility
    subcontractor_name = Column(String(200))
    subcontractor_contact = Column(String(200))

    # Status lifecycle
    status = Column(String(30), nullable=False, default="PLANNED", index=True)
    # Values: PLANNED, RELEASED, MATERIAL_SENT, IN_PRODUCTION, GOODS_RECEIVED, QUALITY_CHECK, CLOSED, CANCELLED

    # Order type
    order_type = Column(String(50), default="subcontract")
    # Values: subcontract (standard), toll_manufacturing, co_manufacturing, outsource

    # Product details - what's being manufactured
    finished_product_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)
    bom_id = Column(String(100))  # Bill of Materials reference

    # Quantities
    planned_quantity = Column(Double, nullable=False)
    actual_quantity = Column(Double)
    rejected_quantity = Column(Double, default=0.0)
    scrap_quantity = Column(Double, default=0.0)
    yield_percentage = Column(Float)

    # Dates
    order_date = Column(Date, nullable=False)
    planned_material_ship_date = Column(Date)
    actual_material_ship_date = Column(Date)
    planned_completion_date = Column(Date, nullable=False)
    actual_completion_date = Column(Date)
    planned_receipt_date = Column(Date, nullable=False)
    actual_receipt_date = Column(Date)

    # Lead times
    manufacturing_lead_time_days = Column(Integer)  # Time at subcontractor
    transit_lead_time_days = Column(Integer)  # Shipping time each way
    total_lead_time_days = Column(Integer)  # Total from order to receipt

    # Priority
    priority = Column(Integer, default=5)  # 1 (highest) to 10 (lowest)

    # Cost tracking
    per_unit_processing_cost = Column(Double)  # Subcontractor's processing fee
    material_cost = Column(Double, default=0.0)  # Cost of materials sent
    transportation_cost = Column(Double, default=0.0)
    total_cost = Column(Double, default=0.0)
    currency = Column(String(3), default="USD")

    # Quality requirements
    quality_spec_id = Column(String(100))  # Quality specification reference
    quality_order_id = Column(Integer, ForeignKey("quality_order.id"))  # Linked quality inspection
    quality_status = Column(String(30))  # PENDING, PASSED, FAILED, WAIVED

    # Contract details
    contract_number = Column(String(100))
    contract_rate = Column(Double)  # Agreed processing rate
    penalty_clause = Column(Boolean, default=False)
    penalty_description = Column(Text)

    # Logistics
    outbound_shipment_id = Column(String(100))  # Materials sent tracking
    inbound_shipment_id = Column(String(100))  # Finished goods tracking
    transportation_mode = Column(String(50))

    # Planning linkage
    mrp_run_id = Column(String(100))
    planning_run_id = Column(String(100))
    production_order_id = Column(Integer, ForeignKey("production_orders.id"))  # If replacing internal MO

    # Notes
    notes = Column(Text)
    manufacturing_instructions = Column(Text)
    context_data = Column(JSON)

    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    received_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    material_sent_at = Column(DateTime)
    received_at = Column(DateTime)
    closed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_sco_site', 'site_id'),
        Index('idx_sco_config', 'config_id'),
        Index('idx_sco_group', 'group_id'),
        Index('idx_sco_company', 'company_id'),
        Index('idx_sco_subcontractor', 'subcontractor_id'),
        Index('idx_sco_product', 'finished_product_id'),
        Index('idx_sco_status', 'status'),
        Index('idx_sco_order_date', 'order_date'),
        Index('idx_sco_planned_receipt', 'planned_receipt_date'),
        Index('idx_sco_quality', 'quality_status'),
        Index('idx_sco_mrp_run', 'mrp_run_id'),
        Index('idx_sco_production_order', 'production_order_id'),
    )


class SubcontractingOrderLineItem(Base):
    """
    Subcontracting Order Line Item - materials provided to subcontractor.

    Tracks raw materials/components sent to the subcontractor for manufacturing.
    """
    __tablename__ = "subcontracting_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subcontract_order_id = Column(Integer, ForeignKey("subcontracting_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    component_product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    component_description = Column(String(500))

    # Quantities
    planned_quantity = Column(Double, nullable=False)  # Quantity to send
    sent_quantity = Column(Double, default=0.0)  # Actually shipped
    consumed_quantity = Column(Double, default=0.0)  # Used by subcontractor
    returned_quantity = Column(Double, default=0.0)  # Unused returned
    scrap_quantity = Column(Double, default=0.0)

    # Unit of measure
    uom = Column(String(20), default="EA")

    # BOM reference
    bom_quantity_per = Column(Double)  # Qty per finished unit from BOM
    scrap_rate = Column(Float, default=0.0)  # Expected scrap %

    # Cost
    unit_cost = Column(Double)
    total_cost = Column(Double)

    # Tracking
    shipment_date = Column(Date)
    shipment_tracking = Column(String(100))

    # Status
    status = Column(String(20), default="PENDING")  # PENDING, SHIPPED, CONSUMED, RETURNED

    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_sco_line_order', 'subcontract_order_id'),
        Index('idx_sco_line_product', 'component_product_id'),
        Index('idx_sco_line_number', 'subcontract_order_id', 'line_number'),
        Index('idx_sco_line_status', 'status'),
    )

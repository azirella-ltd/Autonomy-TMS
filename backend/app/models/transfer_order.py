"""
Transfer Order Database Models

Stores transfer orders and line items for inter-site inventory movements.
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


class TransferOrder(Base):
    """Transfer order header"""
    __tablename__ = "transfer_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    to_number = Column(String(100), unique=True, nullable=False, index=True)

    # Sites (SC standard: Integer ForeignKey to nodes table)
    source_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    destination_site_id = Column(Integer, ForeignKey("site.id"), nullable=False)

    # Configuration
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))

    # SC Compliance fields
    company_id = Column(String(100))  # SC: company identifier
    order_type = Column(String(50), default="transfer")  # SC: transfer, transfer_return
    from_tpartner_id = Column(String(100))  # SC: source trading partner (for 3PL)
    to_tpartner_id = Column(String(100))  # SC: destination trading partner (for 3PL)
    source = Column(String(100))  # SC: system of record
    source_event_id = Column(String(100))  # SC: event lineage
    source_update_dttm = Column(DateTime)  # SC: last update timestamp

    # Status and dates
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT, RELEASED, PICKED, SHIPPED, IN_TRANSIT, RECEIVED, CANCELLED
    order_date = Column(Date)  # Extension: Simulation - date order was placed
    shipment_date = Column(Date, nullable=False)
    estimated_delivery_date = Column(Date, nullable=False)
    actual_ship_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Extension: Simulation fields
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))  # Link to simulation session
    order_period = Column(Integer)  # Round when TO was created
    arrival_period = Column(Integer)  # Round when TO arrives (order_period + lead_time)

    # Transportation
    transportation_mode = Column(String(50))  # truck, rail, air, ocean, courier
    carrier = Column(String(100))
    tracking_number = Column(String(100))
    transportation_lane_id = Column(String(100))  # Link to transportation lane

    # Cost tracking
    transportation_cost = Column(Double, default=0.0)
    currency = Column(String(3), default="USD")

    # Tracking
    notes = Column(Text)

    # Source tracking (if generated from MRP)
    mrp_run_id = Column(String(100))  # Link to MRP run that generated this TO
    planning_run_id = Column(String(100))
    source_po_id = Column(Integer, ForeignKey("purchase_order.id", ondelete="SET NULL"))  # Link TO to originating PO

    # DAG Sequential Execution - Bidirectional link to ScenarioUserPeriod
    source_participant_period_id = Column(Integer, ForeignKey("scenario_user_periods.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_by_id = Column(Integer, ForeignKey("users.id"))
    released_by_id = Column(Integer, ForeignKey("users.id"))
    picked_by_id = Column(Integer, ForeignKey("users.id"))
    shipped_by_id = Column(Integer, ForeignKey("users.id"))
    received_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    released_at = Column(DateTime)
    picked_at = Column(DateTime)
    shipped_at = Column(DateTime)
    received_at = Column(DateTime)

    __table_args__ = (
        Index('idx_to_source_site', 'source_site_id'),
        Index('idx_to_dest_site', 'destination_site_id'),
        Index('idx_to_status', 'status'),
        Index('idx_to_shipment_date', 'shipment_date'),
        Index('idx_to_config', 'config_id'),
        Index('idx_to_tenant', 'tenant_id'),
        Index('idx_to_mrp_run', 'mrp_run_id'),
        Index('idx_to_lane', 'source_site_id', 'destination_site_id'),
        Index('idx_to_company', 'company_id'),
        Index('idx_to_order_type', 'order_type'),
        Index('idx_to_scenario_arrival', 'scenario_id', 'arrival_period', 'status'),  # Simulation: efficient TO arrival queries
        Index('idx_to_scenario_order', 'scenario_id', 'order_period'),  # Simulation: TOs created per round
        Index('idx_to_source_po', 'source_po_id'),  # Link TO to PO
        Index('idx_to_participant_round', 'source_participant_period_id'),  # DAG: bidirectional link to ParticipantRound
    )


class TransferOrderLineItem(Base):
    """Transfer order line item"""
    __tablename__ = "transfer_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    to_id = Column(Integer, ForeignKey("transfer_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)

    # Quantities
    quantity = Column(Double, nullable=False)
    picked_quantity = Column(Double, default=0.0)
    shipped_quantity = Column(Double, default=0.0)
    received_quantity = Column(Double, default=0.0)
    damaged_quantity = Column(Double, default=0.0)

    # Dates
    requested_ship_date = Column(Date, nullable=False)
    requested_delivery_date = Column(Date, nullable=False)
    actual_ship_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Notes
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_to_line_to', 'to_id'),
        Index('idx_to_line_product', 'product_id'),
        Index('idx_to_line_number', 'to_id', 'line_number'),
    )

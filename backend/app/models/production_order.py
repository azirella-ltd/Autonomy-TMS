"""
Production Order Model

Represents production orders in the supply chain system.
Part of Supply Chain compliance (Phase 2).

Production Order Lifecycle:
1. PLANNED - Created from MPS, not yet released
2. RELEASED - Released to shop floor for execution
3. IN_PROGRESS - Currently being produced
4. COMPLETED - Production finished
5. CLOSED - Order archived after all downstream activities complete
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class ProductionOrder(Base):
    """
    Production Order entity following Supply Chain data model.

    Represents a manufacturing work order that transforms raw materials
    into finished goods according to a Bill of Materials (BOM).
    """
    __tablename__ = "production_orders"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    mps_plan_id = Column(Integer, ForeignKey("mps_plans.id"), nullable=True, index=True)
    item_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False, index=True)

    # Order Identification
    order_number = Column(String(100), unique=True, nullable=False, index=True)

    # Quantities
    planned_quantity = Column(Integer, nullable=False)
    actual_quantity = Column(Integer, nullable=True)
    scrap_quantity = Column(Integer, default=0)
    yield_percentage = Column(Float, nullable=True)  # actual / planned * 100

    # Status Management
    status = Column(String(50), default="PLANNED", nullable=False, index=True)
    # Status values: PLANNED, RELEASED, IN_PROGRESS, COMPLETED, CLOSED, CANCELLED

    # Dates
    planned_start_date = Column(DateTime, nullable=False)
    planned_completion_date = Column(DateTime, nullable=False)
    actual_start_date = Column(DateTime, nullable=True)
    actual_completion_date = Column(DateTime, nullable=True)
    released_date = Column(DateTime, nullable=True)
    closed_date = Column(DateTime, nullable=True)

    # Lead Times (in periods/days)
    lead_time_planned = Column(Integer, nullable=False, default=1)
    lead_time_actual = Column(Integer, nullable=True)

    # Priority
    priority = Column(Integer, default=5)  # 1 (highest) to 10 (lowest)

    # Resource Requirements
    resource_hours_planned = Column(Float, nullable=True)
    resource_hours_actual = Column(Float, nullable=True)

    # Cost Tracking
    setup_cost = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)

    # Extension: SAP AFKO/AUFK fields
    order_type = Column(String(50), nullable=True)  # SAP AUFK.AUART (e.g., PP01, PP02)
    logical_type = Column(String(50), nullable=True)  # SAP AUFK.AUTYP (10=production, 30=maintenance)
    currency = Column(String(3), nullable=True)  # SAP AUFK.WAERS
    sap_objnr = Column(String(50), nullable=True)  # SAP object number for status management

    # Additional Metadata
    notes = Column(String(500), nullable=True)
    extra_data = Column(JSON, nullable=True)  # Flexible field for additional data (renamed from 'metadata' to avoid SQLAlchemy reserved word)

    # Tracking Fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Soft Delete
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    mps_plan = relationship("MPSPlan", foreign_keys=[mps_plan_id])  # back_populates removed due to circular import
    item = relationship("Product", foreign_keys=[item_id])
    site = relationship("Site", foreign_keys=[site_id])
    config = relationship("SupplyChainConfig", foreign_keys=[config_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    def __repr__(self):
        return (
            f"<ProductionOrder(id={self.id}, order_number='{self.order_number}', "
            f"item_id={self.item_id}, site_id={self.site_id}, "
            f"status='{self.status}', planned_qty={self.planned_quantity})>"
        )

    @property
    def is_overdue(self) -> bool:
        """Check if production order is overdue."""
        if self.status in ["COMPLETED", "CLOSED", "CANCELLED"]:
            return False
        if self.planned_completion_date:
            return datetime.utcnow() > self.planned_completion_date
        return False

    @property
    def days_until_due(self) -> int:
        """Calculate days until planned completion date."""
        if self.planned_completion_date:
            delta = self.planned_completion_date - datetime.utcnow()
            return delta.days
        return 0

    @property
    def is_on_time(self) -> bool:
        """Check if order was completed on time."""
        if self.status == "COMPLETED" and self.actual_completion_date and self.planned_completion_date:
            return self.actual_completion_date <= self.planned_completion_date
        return True  # Can't determine if not completed

    def calculate_yield(self):
        """Calculate yield percentage from actual vs planned quantity."""
        if self.planned_quantity and self.actual_quantity is not None:
            self.yield_percentage = (self.actual_quantity / self.planned_quantity) * 100

    def calculate_lead_time_actual(self):
        """Calculate actual lead time from start to completion."""
        if self.actual_start_date and self.actual_completion_date:
            delta = self.actual_completion_date - self.actual_start_date
            self.lead_time_actual = delta.days

    def transition_to_released(self, user_id: int = None):
        """Transition order from PLANNED to RELEASED."""
        if self.status != "PLANNED":
            raise ValueError(f"Cannot release order in status: {self.status}")
        self.status = "RELEASED"
        self.released_date = datetime.utcnow()
        if user_id:
            self.updated_by_id = user_id

    def transition_to_in_progress(self, user_id: int = None):
        """Transition order from RELEASED to IN_PROGRESS."""
        if self.status != "RELEASED":
            raise ValueError(f"Cannot start order in status: {self.status}")
        self.status = "IN_PROGRESS"
        self.actual_start_date = datetime.utcnow()
        if user_id:
            self.updated_by_id = user_id

    def transition_to_completed(self, actual_quantity: int, scrap_quantity: int = 0, user_id: int = None):
        """Transition order from IN_PROGRESS to COMPLETED."""
        if self.status != "IN_PROGRESS":
            raise ValueError(f"Cannot complete order in status: {self.status}")
        self.status = "COMPLETED"
        self.actual_completion_date = datetime.utcnow()
        self.actual_quantity = actual_quantity
        self.scrap_quantity = scrap_quantity
        self.calculate_yield()
        self.calculate_lead_time_actual()
        if user_id:
            self.updated_by_id = user_id

    def transition_to_closed(self, user_id: int = None):
        """Transition order from COMPLETED to CLOSED."""
        if self.status != "COMPLETED":
            raise ValueError(f"Cannot close order in status: {self.status}")
        self.status = "CLOSED"
        self.closed_date = datetime.utcnow()
        if user_id:
            self.updated_by_id = user_id

    def cancel(self, user_id: int = None):
        """Cancel the production order."""
        if self.status in ["COMPLETED", "CLOSED"]:
            raise ValueError(f"Cannot cancel order in status: {self.status}")
        self.status = "CANCELLED"
        if user_id:
            self.updated_by_id = user_id


class ProductionOrderComponent(Base):
    """
    Production Order Component - tracks material consumption for a production order.

    Links production orders to their BOM components and tracks
    planned vs actual material consumption.
    """
    __tablename__ = "production_order_components"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    component_item_id = Column(String(100), ForeignKey("product.id"), nullable=False, index=True)

    # Quantities
    planned_quantity = Column(Float, nullable=False)  # From BOM
    actual_quantity = Column(Float, nullable=True)
    scrap_quantity = Column(Float, default=0.0)

    # Unit of Measure
    unit_of_measure = Column(String(20), default="EA")

    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    production_order = relationship("ProductionOrder", backref="components")
    component_item = relationship("Product", foreign_keys=[component_item_id])

    def __repr__(self):
        return (
            f"<ProductionOrderComponent(id={self.id}, "
            f"order_id={self.production_order_id}, "
            f"component_id={self.component_item_id}, "
            f"planned_qty={self.planned_quantity})>"
        )

"""
Maintenance Order Database Models
Sprint 6: Additional Order Types

Maintenance orders are used for asset maintenance with spare parts planning.
Supports preventive, corrective, and predictive maintenance workflows.
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


class MaintenanceOrder(Base):
    """
    Maintenance order header for asset maintenance planning

    Maintenance orders represent scheduled or unscheduled maintenance activities
    on assets, with associated spare parts requirements and work planning.
    """
    __tablename__ = "maintenance_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    maintenance_order_number = Column(String(100), unique=True, nullable=False, index=True)

    # Asset identification
    asset_id = Column(String(40), nullable=False, index=True)
    asset_name = Column(String(200))
    asset_type = Column(String(100))  # Equipment type (pump, conveyor, machine, etc.)
    equipment_id = Column(String(100))  # Equipment identifier

    # Sites and configuration
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"))

    # AWS SC Compliance fields
    company_id = Column(String(100))  # SC: company identifier
    order_type = Column(String(50), default="maintenance")  # SC: order type
    source = Column(String(100))  # SC: system of record
    source_event_id = Column(String(100))  # SC: event lineage
    source_update_dttm = Column(DateTime)  # SC: last update timestamp

    # Maintenance type
    maintenance_type = Column(String(50), nullable=False, index=True)
    # Type values: PREVENTIVE, CORRECTIVE, PREDICTIVE, EMERGENCY, ROUTINE

    # Status and lifecycle
    status = Column(String(20), nullable=False, default="PLANNED")
    # Status values: PLANNED, APPROVED, SCHEDULED, IN_PROGRESS, ON_HOLD, COMPLETED, CANCELLED

    # Dates
    order_date = Column(Date, nullable=False)
    scheduled_start_date = Column(DateTime)
    scheduled_completion_date = Column(DateTime)
    actual_start_date = Column(DateTime)
    actual_completion_date = Column(DateTime)

    # For preventive maintenance
    pm_schedule_id = Column(String(100))  # Link to preventive maintenance schedule
    last_maintenance_date = Column(Date)
    next_maintenance_due = Column(Date)
    maintenance_frequency_days = Column(Integer)  # Frequency in days

    # Priority and urgency
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, CRITICAL, EMERGENCY
    downtime_required = Column(String(1), default="Y")  # Y/N - Does maintenance require asset downtime?
    estimated_downtime_hours = Column(Double)
    actual_downtime_hours = Column(Double)

    # Work details
    work_description = Column(Text, nullable=False)
    failure_description = Column(Text)  # For corrective maintenance
    root_cause_analysis = Column(Text)
    corrective_actions = Column(Text)

    # Resource requirements
    estimated_labor_hours = Column(Double)
    actual_labor_hours = Column(Double, default=0.0)
    estimated_cost = Column(Double)
    actual_cost = Column(Double, default=0.0)
    currency = Column(String(3), default="USD")

    # Technician assignment
    assigned_technician_id = Column(Integer, ForeignKey("users.id"))
    supervisor_id = Column(Integer, ForeignKey("users.id"))

    # Completion tracking
    completion_notes = Column(Text)
    parts_used_summary = Column(JSON)  # Summary of spare parts used
    work_performed = Column(Text)
    test_results = Column(Text)

    # Quality and safety
    quality_check_passed = Column(String(1))  # Y/N
    safety_incidents = Column(Integer, default=0)
    safety_notes = Column(Text)

    # Additional metadata
    notes = Column(Text)
    context_data = Column(JSON)  # Flexible JSON for maintenance-specific data

    # Planning linkage
    mrp_run_id = Column(String(100))  # Link to MRP run for spare parts planning
    planning_run_id = Column(String(100))

    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    completed_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    scheduled_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    __table_args__ = (
        Index('idx_maint_asset', 'asset_id'),
        Index('idx_maint_site', 'site_id'),
        Index('idx_maint_type', 'maintenance_type'),
        Index('idx_maint_status', 'status'),
        Index('idx_maint_priority', 'priority'),
        Index('idx_maint_scheduled_date', 'scheduled_start_date'),
        Index('idx_maint_config', 'config_id'),
        Index('idx_maint_tenant', 'tenant_id'),
        Index('idx_maint_company', 'company_id'),
        Index('idx_maint_technician', 'assigned_technician_id'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "maintenance_order_number": self.maintenance_order_number,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "site_id": self.site_id,
            "maintenance_type": self.maintenance_type,
            "status": self.status,
            "priority": self.priority,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "scheduled_start_date": self.scheduled_start_date.isoformat() if self.scheduled_start_date else None,
            "scheduled_completion_date": self.scheduled_completion_date.isoformat() if self.scheduled_completion_date else None,
            "actual_completion_date": self.actual_completion_date.isoformat() if self.actual_completion_date else None,
            "work_description": self.work_description,
            "downtime_required": self.downtime_required,
            "estimated_downtime_hours": self.estimated_downtime_hours,
            "actual_downtime_hours": self.actual_downtime_hours,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "currency": self.currency,
            "assigned_technician_id": self.assigned_technician_id,
            "completion_notes": self.completion_notes,
            "quality_check_passed": self.quality_check_passed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaintenanceOrderSpare(Base):
    """
    Maintenance order spare parts line item

    Links maintenance orders to required spare parts and consumables.
    """
    __tablename__ = "maintenance_order_spare"

    id = Column(Integer, primary_key=True, autoincrement=True)
    maintenance_order_id = Column(Integer, ForeignKey("maintenance_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    product_description = Column(String(500))

    # Part classification
    part_type = Column(String(50))  # SPARE_PART, CONSUMABLE, TOOL, MATERIAL

    # Quantities
    quantity_required = Column(Double, nullable=False)
    quantity_reserved = Column(Double, default=0.0)
    quantity_issued = Column(Double, default=0.0)
    quantity_used = Column(Double, default=0.0)
    quantity_returned = Column(Double, default=0.0)

    # Unit of measure
    uom = Column(String(20), default="EA")

    # Availability
    availability_status = Column(String(20), default="CHECKING")  # CHECKING, AVAILABLE, BACKORDERED, NOT_AVAILABLE
    expected_availability_date = Column(Date)

    # Cost tracking
    unit_cost = Column(Double)
    total_cost = Column(Double)

    # Issue tracking
    issued_date = Column(DateTime)
    issued_by_id = Column(Integer, ForeignKey("users.id"))

    # Status
    status = Column(String(20), default="PENDING")  # PENDING, RESERVED, ISSUED, USED, RETURNED

    # Notes
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_maint_spare_order', 'maintenance_order_id'),
        Index('idx_maint_spare_product', 'product_id'),
        Index('idx_maint_spare_line', 'maintenance_order_id', 'line_number'),
        Index('idx_maint_spare_status', 'status'),
        Index('idx_maint_spare_availability', 'availability_status'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "line_number": self.line_number,
            "product_id": self.product_id,
            "product_description": self.product_description,
            "part_type": self.part_type,
            "quantity_required": self.quantity_required,
            "quantity_reserved": self.quantity_reserved,
            "quantity_issued": self.quantity_issued,
            "quantity_used": self.quantity_used,
            "uom": self.uom,
            "availability_status": self.availability_status,
            "status": self.status,
            "unit_cost": self.unit_cost,
            "total_cost": self.total_cost,
        }

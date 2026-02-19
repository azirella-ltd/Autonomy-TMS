"""
Project Order Database Models
Sprint 6: Additional Order Types

Project orders are used for project-based demand with completion tracking.
Typical use cases: Custom manufacturing projects, construction projects, engineering-to-order (ETO).
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


class ProjectOrder(Base):
    """
    Project order header for project-based demand

    Project orders represent demand from specific customer projects with
    milestone tracking, completion tracking, and project-specific requirements.
    """
    __tablename__ = "project_order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_order_number = Column(String(100), unique=True, nullable=False, index=True)

    # Project identification
    project_id = Column(String(40), nullable=False, index=True)
    project_name = Column(String(200), nullable=False)
    customer_id = Column(String(40), index=True)
    customer_name = Column(String(200))

    # Sites and configuration
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    # AWS SC Compliance fields
    company_id = Column(String(100))  # SC: company identifier
    order_type = Column(String(50), default="project")  # SC: order type
    source = Column(String(100))  # SC: system of record
    source_event_id = Column(String(100))  # SC: event lineage
    source_update_dttm = Column(DateTime)  # SC: last update timestamp

    # Status and lifecycle
    status = Column(String(20), nullable=False, default="PLANNED")
    # Status values: PLANNED, APPROVED, IN_PROGRESS, ON_HOLD, COMPLETED, CANCELLED

    # Dates
    order_date = Column(Date, nullable=False)
    required_start_date = Column(Date)
    required_completion_date = Column(Date, nullable=False)
    planned_start_date = Column(Date)
    planned_completion_date = Column(Date)
    actual_start_date = Column(Date)
    actual_completion_date = Column(Date)

    # Project details
    project_type = Column(String(50))  # ETO (engineer-to-order), MTO (make-to-order), custom
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, CRITICAL
    contract_number = Column(String(100))
    contract_value = Column(Double)
    currency = Column(String(3), default="USD")

    # Completion tracking
    completion_percentage = Column(Double, default=0.0)  # 0-100
    milestones = Column(JSON)  # [{name, target_date, completion_date, status}, ...]

    # Resource requirements
    estimated_hours = Column(Double)
    actual_hours = Column(Double, default=0.0)
    estimated_cost = Column(Double)
    actual_cost = Column(Double, default=0.0)

    # Additional metadata
    description = Column(Text)
    notes = Column(Text)
    special_requirements = Column(Text)
    context_data = Column(JSON)  # Flexible JSON for project-specific data

    # Planning linkage
    mrp_run_id = Column(String(100))  # Link to MRP run that generated requirements
    planning_run_id = Column(String(100))

    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    completed_by_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    approved_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    __table_args__ = (
        Index('idx_proj_project_id', 'project_id'),
        Index('idx_proj_customer', 'customer_id'),
        Index('idx_proj_site', 'site_id'),
        Index('idx_proj_status', 'status'),
        Index('idx_proj_order_date', 'order_date'),
        Index('idx_proj_completion_date', 'required_completion_date'),
        Index('idx_proj_config', 'config_id'),
        Index('idx_proj_group', 'group_id'),
        Index('idx_proj_company', 'company_id'),
        Index('idx_proj_priority', 'priority'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "project_order_number": self.project_order_number,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "site_id": self.site_id,
            "status": self.status,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "required_completion_date": self.required_completion_date.isoformat() if self.required_completion_date else None,
            "actual_completion_date": self.actual_completion_date.isoformat() if self.actual_completion_date else None,
            "completion_percentage": self.completion_percentage,
            "priority": self.priority,
            "contract_value": self.contract_value,
            "currency": self.currency,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "milestones": self.milestones or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProjectOrderLineItem(Base):
    """
    Project order line item - products/materials required for the project
    """
    __tablename__ = "project_order_line_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_order_id = Column(Integer, ForeignKey("project_order.id", ondelete="CASCADE"), nullable=False)

    # Line details
    line_number = Column(Integer, nullable=False)
    product_id = Column(String(100), ForeignKey("product.id"), nullable=False)
    product_description = Column(String(500))

    # Quantities
    quantity_required = Column(Double, nullable=False)
    quantity_allocated = Column(Double, default=0.0)
    quantity_issued = Column(Double, default=0.0)
    quantity_returned = Column(Double, default=0.0)

    # Unit of measure
    uom = Column(String(20), default="EA")

    # Dates
    required_date = Column(Date, nullable=False)
    planned_issue_date = Column(Date)
    actual_issue_date = Column(Date)

    # Cost tracking
    unit_cost = Column(Double)
    total_cost = Column(Double)

    # Status
    status = Column(String(20), default="PENDING")  # PENDING, ALLOCATED, ISSUED, COMPLETED

    # Notes
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_proj_line_order', 'project_order_id'),
        Index('idx_proj_line_product', 'product_id'),
        Index('idx_proj_line_number', 'project_order_id', 'line_number'),
        Index('idx_proj_line_status', 'status'),
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "line_number": self.line_number,
            "product_id": self.product_id,
            "product_description": self.product_description,
            "quantity_required": self.quantity_required,
            "quantity_allocated": self.quantity_allocated,
            "quantity_issued": self.quantity_issued,
            "uom": self.uom,
            "required_date": self.required_date.isoformat() if self.required_date else None,
            "status": self.status,
            "unit_cost": self.unit_cost,
            "total_cost": self.total_cost,
        }

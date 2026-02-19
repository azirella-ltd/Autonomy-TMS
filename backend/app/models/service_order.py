"""
Service Order Entity Model - AWS SC Compliant
AWS Supply Chain Entity: service_order

Manages service and repair orders (corrective maintenance, warranty work, field service).
Different from maintenance_orders (preventive) - service orders are reactive/corrective.

IMPORTANT: This implementation follows the AWS Supply Chain Data Model as the foundation.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, text, Double, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional

from app.models.base import Base


class ServiceOrder(Base):
    """
    Service Order - Corrective maintenance and repair orders

    AWS SC Entity: service_order

    Manages reactive maintenance work:
    - Equipment breakdowns
    - Warranty repairs
    - Field service calls
    - Corrective maintenance

    AWS SC Core Fields (REQUIRED):
    - company_id, site_id, resource_id
    - service_order_id, service_order_type
    - service_date, completion_date
    - status (open, in_progress, completed, cancelled)
    - source, source_event_id, source_update_dttm

    Extensions:
    - Priority level (critical, high, medium, low)
    - Service provider (internal, external vendor)
    - Cost tracking (labor, parts, total)
    - Downtime impact on capacity
    """
    __tablename__ = "service_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields - Identifiers
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("site.id"))
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)  # Equipment/machine being serviced
    service_order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # AWS SC Core Fields - Service Type
    service_order_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="breakdown, repair, warranty, calibration, inspection"
    )

    # AWS SC Core Fields - Dates
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # When service is scheduled
    completion_date: Mapped[Optional[date]] = mapped_column(Date)  # Actual completion
    requested_date: Mapped[Optional[date]] = mapped_column(Date)  # Original request date

    # AWS SC Core Fields - Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="open",
        nullable=False,
        comment="open, assigned, in_progress, completed, cancelled"
    )

    # Extension: Priority and Urgency
    priority: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        comment="critical, high, medium, low"
    )
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)  # Emergency service call

    # Extension: Service Provider
    service_provider_type: Mapped[str] = mapped_column(
        String(50),
        default="internal",
        comment="internal, external_vendor, oem"
    )
    service_provider_id: Mapped[Optional[str]] = mapped_column(String(100))  # Vendor or technician ID

    # Extension: Problem Description
    problem_description: Mapped[Optional[str]] = mapped_column(String(1000))
    root_cause: Mapped[Optional[str]] = mapped_column(String(1000))
    resolution_description: Mapped[Optional[str]] = mapped_column(String(1000))

    # Extension: Cost Tracking
    estimated_labor_hours: Mapped[Optional[float]] = mapped_column(Double)
    actual_labor_hours: Mapped[Optional[float]] = mapped_column(Double)
    labor_cost: Mapped[Optional[float]] = mapped_column(Double)
    parts_cost: Mapped[Optional[float]] = mapped_column(Double)
    total_cost: Mapped[Optional[float]] = mapped_column(Double)

    # Extension: Downtime Impact
    planned_downtime_hours: Mapped[Optional[float]] = mapped_column(Double)  # Scheduled downtime
    actual_downtime_hours: Mapped[Optional[float]] = mapped_column(Double)  # Actual downtime
    production_impact_units: Mapped[Optional[float]] = mapped_column(Double)  # Lost production

    # Extension: Parts and Materials
    parts_required: Mapped[Optional[str]] = mapped_column(String(500))  # Comma-separated part IDs
    parts_availability: Mapped[Optional[str]] = mapped_column(String(50))  # available, ordered, backorder

    # Extension: Work Order Details
    work_order_number: Mapped[Optional[str]] = mapped_column(String(100))
    assigned_technician: Mapped[Optional[str]] = mapped_column(String(100))
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # AWS SC Core Fields - Source Tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Extension: Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Relationships
    site = relationship("Site")

    def __repr__(self):
        return (
            f"<ServiceOrder(id={self.id}, service_order_id='{self.service_order_id}', "
            f"resource_id='{self.resource_id}', status='{self.status}', priority='{self.priority}')>"
        )

    def calculate_response_time_hours(self) -> Optional[float]:
        """Calculate response time from request to assignment"""
        if self.requested_date and self.assigned_at:
            delta = self.assigned_at.date() - self.requested_date
            return delta.total_seconds() / 3600
        return None

    def calculate_resolution_time_hours(self) -> Optional[float]:
        """Calculate time from assignment to completion"""
        if self.assigned_at and self.completed_at:
            delta = self.completed_at - self.assigned_at
            return delta.total_seconds() / 3600
        return None

    def is_overdue(self) -> bool:
        """Check if service order is overdue"""
        if self.status in ['completed', 'cancelled']:
            return False

        if self.service_date and date.today() > self.service_date:
            return True

        return False

    def calculate_cost_variance(self) -> Optional[float]:
        """Calculate cost variance from estimate"""
        if self.total_cost and self.estimated_labor_hours:
            estimated_total = (self.estimated_labor_hours * 50) + (self.parts_cost or 0)  # Assume $50/hr
            variance = ((self.total_cost - estimated_total) / estimated_total) * 100
            return round(variance, 2)
        return None

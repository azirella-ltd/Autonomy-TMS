"""
Resource Capacity Entity Model - AWS SC Compliant
AWS Supply Chain Entity: resource_capacity

Manages production capacity at resource level (work centers, machines, labor).
Used for capacity planning, bottleneck analysis, and finite capacity scheduling.

IMPORTANT: This implementation follows the AWS Supply Chain Data Model as the foundation.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, text, Double
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional

from app.models.base import Base


class ResourceCapacity(Base):
    """
    Resource Capacity - Production capacity tracking

    AWS SC Entity: resource_capacity

    Tracks available capacity for production resources (work centers, machines, labor pools)
    at site level. Supports finite capacity planning and bottleneck analysis.

    AWS SC Core Fields (REQUIRED):
    - company_id, site_id, resource_id
    - capacity_date, available_capacity_hours
    - utilized_capacity_hours, remaining_capacity_hours
    - capacity_uom (unit of measure)
    - source, source_event_id, source_update_dttm

    Extensions:
    - capacity_efficiency: Efficiency factor (0-1)
    - planned_downtime_hours: Scheduled maintenance
    - unplanned_downtime_hours: Breakdowns
    - overtime_hours: Available overtime capacity
    """
    __tablename__ = "resource_capacity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields - Identifiers
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("site.id"))
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)  # Work center, machine, labor pool
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))  # machine, labor, equipment, facility

    # AWS SC Core Fields - Date and Capacity
    capacity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    available_capacity_hours: Mapped[float] = mapped_column(Double, nullable=False)  # Total available capacity
    utilized_capacity_hours: Mapped[float] = mapped_column(Double, default=0.0)  # Currently utilized
    remaining_capacity_hours: Mapped[float] = mapped_column(Double, default=0.0)  # Available - Utilized

    # AWS SC Core Fields - Unit of Measure
    capacity_uom: Mapped[str] = mapped_column(String(20), default="hours", nullable=False)  # hours, units, pieces

    # Extension: Efficiency and Downtime
    capacity_efficiency: Mapped[float] = mapped_column(Double, default=1.0)  # 0.0 - 1.0 (100%)
    planned_downtime_hours: Mapped[Optional[float]] = mapped_column(Double, default=0.0)  # Scheduled maintenance
    unplanned_downtime_hours: Mapped[Optional[float]] = mapped_column(Double, default=0.0)  # Breakdowns
    overtime_hours: Mapped[Optional[float]] = mapped_column(Double, default=0.0)  # Available overtime

    # Extension: Resource Details
    resource_name: Mapped[Optional[str]] = mapped_column(String(255))  # Human-friendly name
    resource_group: Mapped[Optional[str]] = mapped_column(String(100))  # Grouping (e.g., "Assembly Line 1")
    shift_count: Mapped[Optional[int]] = mapped_column(Integer, default=1)  # Number of shifts
    hours_per_shift: Mapped[Optional[float]] = mapped_column(Double, default=8.0)  # Hours per shift

    # Extension: Capacity Constraints
    max_capacity_hours: Mapped[Optional[float]] = mapped_column(Double)  # Maximum capacity (including overtime)
    min_capacity_hours: Mapped[Optional[float]] = mapped_column(Double)  # Minimum required capacity

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
            f"<ResourceCapacity(id={self.id}, resource_id='{self.resource_id}', "
            f"date={self.capacity_date}, available={self.available_capacity_hours}, "
            f"utilized={self.utilized_capacity_hours})>"
        )

    def calculate_utilization_pct(self) -> float:
        """Calculate capacity utilization percentage"""
        if self.available_capacity_hours <= 0:
            return 0.0
        return (self.utilized_capacity_hours / self.available_capacity_hours) * 100.0

    def is_at_capacity(self, buffer_pct: float = 0.95) -> bool:
        """Check if resource is at or near full capacity"""
        return self.calculate_utilization_pct() >= (buffer_pct * 100)

    def get_available_hours(self) -> float:
        """Get truly available hours (accounting for efficiency and downtime)"""
        effective_hours = self.available_capacity_hours * self.capacity_efficiency
        effective_hours -= (self.planned_downtime_hours or 0.0)
        effective_hours -= (self.unplanned_downtime_hours or 0.0)
        effective_hours -= self.utilized_capacity_hours
        return max(0.0, effective_hours)


class ResourceCapacityConstraint(Base):
    """
    Resource Capacity Constraints

    Defines constraints on resource capacity usage:
    - Time-based constraints (weekends, holidays)
    - Product-specific constraints (not all resources can produce all products)
    - Sequence-dependent setup times

    Extension to AWS SC resource_capacity entity
    """
    __tablename__ = "resource_capacity_constraint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identifiers
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(50), nullable=False)  # time_window, product_compatibility, setup

    # Time window constraints
    constraint_start_date: Mapped[Optional[date]] = mapped_column(Date)
    constraint_end_date: Mapped[Optional[date]] = mapped_column(Date)
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)  # 0=Monday, 6=Sunday
    start_time: Mapped[Optional[str]] = mapped_column(String(10))  # HH:MM format
    end_time: Mapped[Optional[str]] = mapped_column(String(10))  # HH:MM format

    # Product compatibility
    product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))
    is_compatible: Mapped[Optional[bool]] = mapped_column(Integer, default=True)  # Can this resource produce this product?

    # Setup time constraints
    from_product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))
    to_product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))
    setup_time_hours: Mapped[Optional[float]] = mapped_column(Double)  # Sequence-dependent setup time

    # Constraint value
    capacity_reduction_pct: Mapped[Optional[float]] = mapped_column(Double, default=0.0)  # % reduction in capacity
    description: Mapped[Optional[str]] = mapped_column(String(500))

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<ResourceCapacityConstraint(id={self.id}, resource_id='{self.resource_id}', "
            f"type='{self.constraint_type}')>"
        )

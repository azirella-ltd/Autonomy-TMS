"""
Capacity Planning Models (RCCP - Rough-Cut Capacity Planning)

Capacity planning validates production feasibility by comparing resource requirements
against available capacity. Identifies bottlenecks and overload conditions.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from enum import Enum

from .base import Base


class CapacityPlanStatus(str, Enum):
    """Capacity Plan Status"""
    DRAFT = "DRAFT"  # Being created/edited
    ACTIVE = "ACTIVE"  # Currently in use
    SCENARIO = "SCENARIO"  # What-if analysis scenario
    ARCHIVED = "ARCHIVED"  # Historical record


class ResourceType(str, Enum):
    """Resource Type Classification"""
    LABOR = "LABOR"  # Human resources (workers, operators)
    MACHINE = "MACHINE"  # Equipment (CNC, assembly lines, packaging)
    FACILITY = "FACILITY"  # Building space (warehouse, production floor)
    UTILITY = "UTILITY"  # Utilities (power, water, gas)
    TOOL = "TOOL"  # Tools and fixtures


class CapacityPlan(Base):
    """
    Capacity Plan — TMS variant of the universal capacity-plan concept.

    **Conforms to** ``azirella_data_model.capacity_plan.CapacityPlanMixin``
    contract. Today this class is a near-copy of SCP's production-RCCP
    model; as TMS's capacity planning diverges toward transport-specific
    resources (lanes, carriers, dock slots), migrate to a TMS-native
    schema that directly subclasses ``CapacityPlanMixin``.

    Contract mapping (same field names as SCP's equivalent):

    | Mixin field     | TMS column                 |
    |-----------------|----------------------------|
    | name            | name                       |
    | description     | description                |
    | tenant_id       | (derived via supply_chain_config_id) |
    | start_date      | start_date                 |
    | end_date        | end_date                   |
    | horizon_length  | planning_horizon_weeks     |
    | bucket_size     | bucket_size_days           |
    | bucket_unit     | (implicit DAY)             |
    | status          | status                     |

    See Autonomy-Core docs/CAPABILITY_MANIFEST.md for the rationale.
    """
    __tablename__ = "capacity_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Basic Information
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Configuration Reference
    supply_chain_config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Planning Parameters
    planning_horizon_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=13)
    bucket_size_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)  # Weekly = 7
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Status Management
    status: Mapped[CapacityPlanStatus] = mapped_column(
        SQLEnum(CapacityPlanStatus),
        nullable=False,
        default=CapacityPlanStatus.DRAFT,
        index=True
    )

    # What-If Scenario
    is_scenario: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scenario_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("capacity_plans.id", ondelete="SET NULL"),
        nullable=True
    )

    # Summary Metrics
    total_resources: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overloaded_resources: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_utilization_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_utilization_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bottleneck_identified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Workflow Tracking
    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    supply_chain_config = relationship("SupplyChainConfig", back_populates="capacity_plans")
    resources = relationship("CapacityResource", back_populates="plan", cascade="all, delete-orphan")
    requirements = relationship("CapacityRequirement", back_populates="plan", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    base_plan = relationship("CapacityPlan", remote_side=[id], foreign_keys=[base_plan_id])

    def calculate_summary_metrics(self) -> None:
        """Calculate summary metrics from requirements."""
        if not self.requirements:
            return

        self.total_resources = len(set(req.resource_id for req in self.requirements))

        # Count overloaded periods
        overloaded = set()
        total_utilization = 0
        max_util = 0
        count = 0

        for req in self.requirements:
            if req.is_overloaded:
                overloaded.add(req.resource_id)
            if req.utilization_percent:
                total_utilization += req.utilization_percent
                max_util = max(max_util, req.utilization_percent)
                count += 1

        self.overloaded_resources = len(overloaded)
        self.avg_utilization_percent = total_utilization / count if count > 0 else 0
        self.max_utilization_percent = max_util
        self.bottleneck_identified = self.max_utilization_percent >= 95.0

    @property
    def is_feasible(self) -> bool:
        """Check if capacity plan is feasible (no overloaded resources)."""
        return self.overloaded_resources == 0 if self.overloaded_resources is not None else True

    @property
    def has_bottlenecks(self) -> bool:
        """Check if plan has bottleneck resources (>95% utilization)."""
        return self.bottleneck_identified


class CapacityResource(Base):
    """
    Capacity Resource

    Defines available resources at sites with capacity constraints.
    Resources can be labor, machines, facilities, utilities, or tools.
    """
    __tablename__ = "capacity_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Plan Reference
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("capacity_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Resource Identification
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        SQLEnum(ResourceType),
        nullable=False,
        default=ResourceType.MACHINE
    )

    # Site Reference
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Capacity Parameters
    available_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Hours/units per period
    capacity_unit: Mapped[str] = mapped_column(String(50), default="hours", nullable=False)
    efficiency_percent: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    utilization_target_percent: Mapped[float] = mapped_column(Float, default=85.0, nullable=False)

    # Cost Information
    cost_per_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    setup_time_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Schedule
    shifts_per_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hours_per_shift: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    working_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    plan = relationship("CapacityPlan", back_populates="resources")
    site = relationship("Site", foreign_keys=[site_id])
    requirements = relationship("CapacityRequirement", back_populates="resource")

    @property
    def effective_capacity(self) -> float:
        """Calculate effective capacity considering efficiency."""
        return self.available_capacity * (self.efficiency_percent / 100.0)

    @property
    def target_capacity(self) -> float:
        """Calculate target capacity based on utilization target."""
        return self.effective_capacity * (self.utilization_target_percent / 100.0)


class CapacityRequirement(Base):
    """
    Capacity Requirement

    Time-phased capacity requirements for each resource and period.
    Calculated from production orders, MPS, or demand forecasts.
    """
    __tablename__ = "capacity_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Plan Reference
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("capacity_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Resource Reference
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("capacity_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Time Period
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3, ..., N

    # Capacity Analysis
    required_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Hours/units required
    available_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Hours/units available
    utilization_percent: Mapped[float] = mapped_column(Float, nullable=False)  # (required/available)*100

    # Status
    is_overloaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overload_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_bottleneck: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Source Information
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # MPS, Production Order, Forecast
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Breakdown (optional detailed analysis)
    requirement_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Example: {"product_A": 40, "product_B": 30, "setup": 5}

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    plan = relationship("CapacityPlan", back_populates="requirements")
    resource = relationship("CapacityResource", back_populates="requirements")

    def calculate_utilization(self) -> None:
        """Calculate utilization and overload status."""
        if self.available_capacity > 0:
            self.utilization_percent = (self.required_capacity / self.available_capacity) * 100.0
        else:
            self.utilization_percent = 0.0

        self.is_overloaded = self.utilization_percent > 100.0
        if self.is_overloaded:
            self.overload_amount = self.required_capacity - self.available_capacity
        else:
            self.overload_amount = 0.0

        # Bottleneck if utilization > 95%
        self.is_bottleneck = self.utilization_percent >= 95.0

    @property
    def spare_capacity(self) -> float:
        """Calculate spare capacity (negative if overloaded)."""
        return self.available_capacity - self.required_capacity

    @property
    def load_factor(self) -> float:
        """Calculate load factor (0.0 to 1.0+)."""
        return self.required_capacity / self.available_capacity if self.available_capacity > 0 else 0.0

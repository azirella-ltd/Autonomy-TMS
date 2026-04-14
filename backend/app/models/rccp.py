"""
RCCP (Rough-Cut Capacity Planning) Models

Bill of Resources links products to resource consumption rates per site.
RCCP Runs capture the result of validating an MPS plan against available capacity.

Three RCCP methods supported:
  - CPOF (Capacity Planning using Overall Factors): single hours_per_unit per product
  - Bill of Capacity: per-resource hours_per_unit
  - Resource Profile: phased per-resource consumption with lead-time offsets
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SQLEnum,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from enum import Enum

from .base import Base


class RCCPMethod(str, Enum):
    """RCCP calculation method."""
    CPOF = "cpof"
    BILL_OF_CAPACITY = "bill_of_capacity"
    RESOURCE_PROFILE = "resource_profile"


class ProductionPhase(str, Enum):
    """Production phase within a resource profile."""
    SETUP = "setup"
    RUN = "run"
    TEARDOWN = "teardown"
    QUEUE = "queue"
    MOVE = "move"


class RCCPRunStatus(str, Enum):
    """Result status of an RCCP validation run."""
    FEASIBLE = "feasible"
    OVERLOADED = "overloaded"
    LEVELLING_RECOMMENDED = "levelling_recommended"
    ESCALATE_TO_SOP = "escalate_to_sop"


class BillOfResources(Base):
    """
    Bill of Resources

    Links products to resource consumption rates per site. Supports three
    RCCP methods:
      - CPOF: overall_hours_per_unit (resource_id is NULL)
      - Bill of Capacity: hours_per_unit per resource
      - Resource Profile: phase_hours_per_unit with lead_time_offset_days per phase
    """
    __tablename__ = "bill_of_resources"
    __table_args__ = (
        UniqueConstraint(
            "config_id", "product_id", "site_id", "resource_id", "phase",
            name="uq_bor_config_product_site_resource_phase",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Configuration Reference
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Product Reference — canonical Product.id is String(100) in
    # azirella_data_model.master.entities; keep the FK column type aligned.
    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Site Reference
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Resource Reference (NULL for CPOF method)
    resource_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("capacity_resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # CPOF method: overall hours per unit (no resource breakdown)
    overall_hours_per_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Bill of Capacity method: hours per unit on a specific resource
    hours_per_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Setup and batch parameters
    setup_hours_per_batch: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    typical_batch_size: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Resource Profile method: phased consumption
    phase: Mapped[Optional[ProductionPhase]] = mapped_column(
        SQLEnum(ProductionPhase),
        nullable=True,
    )
    lead_time_offset_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phase_hours_per_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Flags
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional link to production process definition
    production_process_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        ForeignKey("production_process.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    product = relationship("Product", foreign_keys=[product_id])
    site = relationship("Site", foreign_keys=[site_id])
    resource = relationship("CapacityResource", foreign_keys=[resource_id])
    config = relationship("SupplyChainConfig", foreign_keys=[config_id])

    @property
    def effective_hours_per_unit(self) -> float:
        """
        Effective hours per unit including amortised setup time.

        effective = hours_per_unit + setup_hours_per_batch / typical_batch_size
        """
        base = self.hours_per_unit or 0.0
        batch = self.typical_batch_size if self.typical_batch_size and self.typical_batch_size > 0 else 1.0
        return base + self.setup_hours_per_batch / batch


class RCCPRun(Base):
    """
    RCCP Run

    Captures the result of a rough-cut capacity planning validation run
    against an MPS plan for a specific site. Includes utilisation metrics,
    overload analysis, changeover details (Glenday Sieve), and any
    recommended MPS adjustments.
    """
    __tablename__ = "rccp_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Configuration Reference
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # MPS Plan Reference
    mps_plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mps_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Site Reference
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Method and Status
    method: Mapped[RCCPMethod] = mapped_column(
        SQLEnum(RCCPMethod),
        nullable=False,
        default=RCCPMethod.BILL_OF_CAPACITY,
    )
    status: Mapped[RCCPRunStatus] = mapped_column(
        SQLEnum(RCCPRunStatus),
        nullable=False,
    )
    is_feasible: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Planning Horizon
    planning_horizon_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Utilisation Summary
    max_utilization_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_utilization_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Overload Analysis
    overloaded_resource_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overloaded_week_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chronic_overload_resources: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=False)

    # Overtime
    overtime_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MPS Adjustments (recommended changes to resolve overloads)
    mps_adjustments: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=False)

    # Per-resource per-week load details
    resource_loads: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=False)

    # Rules / heuristics applied during the run
    rules_applied: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=False)

    # Demand Variability
    demand_variability_cv: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    variability_buffer_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Changeover Analysis (Glenday Sieve + nearest-neighbour)
    changeover_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_changeover_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    changeover_details: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=False)
    glenday_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Workflow Tracking
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    mps_plan = relationship("MPSPlan", foreign_keys=[mps_plan_id])
    site = relationship("Site", foreign_keys=[site_id])
    config = relationship("SupplyChainConfig", foreign_keys=[config_id])

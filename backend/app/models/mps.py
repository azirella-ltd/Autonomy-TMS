"""
Master Production Scheduling (MPS) Models

MPS is the time-phased plan for manufacturing end items (finished goods).
It specifies what to produce, how much, and when.
"""

from datetime import datetime
from typing import Optional
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


class MPSStatus(str, Enum):
    """MPS Plan Status"""
    DRAFT = "DRAFT"  # Editable, not released
    PENDING_APPROVAL = "PENDING_APPROVAL"  # Awaiting approval
    APPROVED = "APPROVED"  # Approved and released for execution
    IN_EXECUTION = "IN_EXECUTION"  # Currently being executed
    COMPLETED = "COMPLETED"  # Execution finished
    CANCELLED = "CANCELLED"  # Cancelled before completion


class MPSPlan(Base):
    """
    Master Production Schedule Plan

    Represents a time-phased production plan for a specific supply chain configuration.
    Contains weekly/periodic quantities to produce for finished goods.
    """
    __tablename__ = "mps_plans"

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
    status: Mapped[MPSStatus] = mapped_column(
        SQLEnum(MPSStatus),
        nullable=False,
        default=MPSStatus.DRAFT,
        index=True
    )

    # Workflow Tracking
    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Execution Tracking
    execution_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    execution_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    supply_chain_config = relationship("SupplyChainConfig", back_populates="mps_plans")
    items = relationship("MPSPlanItem", back_populates="plan", cascade="all, delete-orphan")
    capacity_checks = relationship("MPSCapacityCheck", back_populates="plan", cascade="all, delete-orphan")
    key_material_requirements = relationship("MPSKeyMaterialRequirement", back_populates="plan", cascade="all, delete-orphan")

    # One-way relationships (no back_populates to avoid circular imports)
    # NOTE: Commented out to avoid SQLAlchemy mapper initialization errors
    # MonteCarloRun and ProductionOrder already have mps_plan relationship
    # These relationships can be accessed via queries: db.query(MonteCarloRun).filter(MonteCarloRun.mps_plan_id == plan.id)
    # monte_carlo_runs = relationship("MonteCarloRun", foreign_keys="MonteCarloRun.mps_plan_id", cascade="all, delete-orphan")
    # production_orders = relationship("ProductionOrder", foreign_keys="ProductionOrder.mps_plan_id")

    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])


class MPSPlanItem(Base):
    """
    MPS Plan Item - Time-phased quantities for a specific product/site

    Stores the weekly production quantities for each finished good.
    Each row represents ONE product at ONE site for the entire planning horizon.
    """
    __tablename__ = "mps_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Plan Reference
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mps_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Product/Site Reference
    # Updated to use SC Product table with String PK
    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Time-Phased Quantities
    # Format: [week1_qty, week2_qty, week3_qty, ..., weekN_qty]
    # Array length should match plan.planning_horizon_weeks
    weekly_quantities: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    # Lot Sizing Parameters
    lot_size_rule: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # EOQ, LFL, POQ, Fixed
    lot_size_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    plan = relationship("MPSPlan", back_populates="items")
    product = relationship("Product", foreign_keys=[product_id])  # Changed from "Item" to "Product"
    site = relationship("Site", foreign_keys=[site_id])


class MPSCapacityCheck(Base):
    """
    MPS Capacity Check - Rough-Cut Capacity Planning (RCCP)

    Validates that the MPS is feasible given available resources.
    Stores capacity requirements and utilization for each resource and time period.
    """
    __tablename__ = "mps_capacity_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Plan Reference
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mps_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Resource Reference
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Time Period
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Capacity Analysis
    required_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Hours/units required
    available_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Hours/units available
    utilization_percent: Mapped[float] = mapped_column(Float, nullable=False)  # (required/available)*100

    # Status
    is_overloaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overload_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    plan = relationship("MPSPlan", back_populates="capacity_checks")
    site = relationship("Site", foreign_keys=[site_id])


class MPSKeyMaterialRequirement(Base):
    """
    MPS Key Material Requirements - Rough-cut BOM explosion for critical materials

    Stores requirements for key materials (long lead time, bottleneck, strategic items)
    that need to be planned at the MPS level before detailed MRP explosion.

    Key materials are flagged in product_bom.is_key_material = 'true'.
    This enables MPS to perform rough-cut capacity and material availability checks
    for critical components without full MRP detail.

    Industry Standard: SAP calls this "Key Figure Planning", Kinaxis uses "Constrained Materials"
    """
    __tablename__ = "mps_key_material_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Plan Reference
    plan_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mps_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Parent MPS Item (Finished Good)
    mps_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mps_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    # Updated to use SC Product table with String PK
    parent_product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("product.id"),
        nullable=False,
        index=True
    )

    # Key Material (Component)
    # Updated to use SC Product table with String PK
    key_material_product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("product.id"),
        nullable=False,
        index=True
    )
    key_material_site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id"),
        nullable=False,
        index=True
    )

    # BOM Relationship
    bom_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=direct child, 2=grandchild, etc.
    component_quantity: Mapped[float] = mapped_column(Float, nullable=False)  # Units per parent
    scrap_percentage: Mapped[float] = mapped_column(Float, default=0.0)  # Scrap/yield loss

    # Time-Phased Gross Requirements
    # Format: [week1_qty, week2_qty, week3_qty, ..., weekN_qty]
    # Derived from MPS quantities × component_quantity × (1 + scrap_percentage/100)
    weekly_gross_requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    # Total Requirements
    total_gross_requirement: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Key Material Flags
    is_bottleneck: Mapped[bool] = mapped_column(Boolean, default=False)  # Resource constraint
    is_long_lead_time: Mapped[bool] = mapped_column(Boolean, default=False)  # >4 weeks
    is_strategic: Mapped[bool] = mapped_column(Boolean, default=False)  # Limited suppliers

    # Lead Time Information
    procurement_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    plan = relationship("MPSPlan", back_populates="key_material_requirements")
    mps_item = relationship("MPSPlanItem")
    # Changed from "Item" to "Product" (SC compliant)
    parent_product = relationship("Product", foreign_keys=[parent_product_id])
    key_material_product = relationship("Product", foreign_keys=[key_material_product_id])
    key_material_site = relationship("Site", foreign_keys=[key_material_site_id])

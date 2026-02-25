from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum

from .base import Base
from .explainability import ExplainabilityLevel


class CustomerMode(str, Enum):
    """Customer operating mode - determines navigation and behavior."""
    LEARNING = "learning"      # Simplified nav, game-like clock, turn-based (user education)
    PRODUCTION = "production"  # Full nav, real data, real planning


class ClockMode(str, Enum):
    """Clock progression mode for Learning customers."""
    TURN_BASED = "turn_based"  # Advance when all players submit
    TIMED = "timed"            # Fixed time per round
    REALTIME = "realtime"      # Continuous (for demos)

if TYPE_CHECKING:
    from .user import User
    from .supply_chain_config import SupplyChainConfig
    from .scenario import Scenario
    from .sync_job import SyncJobConfig
    from .workflow import WorkflowTemplate
    from .planning_cycle import PlanningCycle

class Customer(Base):
    """Organization representing an Autonomy customer (tenant boundary)."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Agent Explainability Configuration
    explainability_level: Mapped[ExplainabilityLevel] = mapped_column(
        SAEnum(ExplainabilityLevel, values_callable=lambda x: [e.value for e in x], name="explainability_level_enum"),
        nullable=False,
        server_default=ExplainabilityLevel.NORMAL.value,
        default=ExplainabilityLevel.NORMAL,
    )

    # Customer Operating Mode (Learning vs Production)
    mode: Mapped[CustomerMode] = mapped_column(
        SAEnum(CustomerMode, values_callable=lambda x: [e.value for e in x], name="customer_mode_enum"),
        nullable=False,
        server_default=CustomerMode.PRODUCTION.value,
        default=CustomerMode.PRODUCTION,
    )

    # Learning Mode Settings
    clock_mode: Mapped[Optional[ClockMode]] = mapped_column(
        SAEnum(ClockMode, values_callable=lambda x: [e.value for e in x], name="clock_mode_enum"),
        nullable=True,
        default=None,
    )
    round_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None,
        comment="Round duration in seconds for timed clock mode"
    )

    # Production Mode Settings
    data_refresh_schedule: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default=None,
        comment="Cron expression for data refresh schedule"
    )
    last_data_import: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=None,
        comment="Timestamp of last data import"
    )

    @property
    def is_learning(self) -> bool:
        """Check if customer is in learning mode (user education)."""
        return self.mode == CustomerMode.LEARNING

    @property
    def is_production(self) -> bool:
        """Check if customer is in production mode."""
        return self.mode == CustomerMode.PRODUCTION

    admin: Mapped["User"] = relationship("User", back_populates="admin_of_customer", foreign_keys=[admin_id])
    users: Mapped[List["User"]] = relationship("User", back_populates="customer", foreign_keys="User.customer_id", cascade="all, delete-orphan")

    # Make supply_chain_configs relationship optional
    if TYPE_CHECKING:
        supply_chain_configs: Mapped[List["SupplyChainConfig"]]
    else:
        supply_chain_configs = relationship(
            "SupplyChainConfig",
            back_populates="customer",
            cascade="all, delete-orphan",
            lazy='dynamic'
        )

    # Scenarios belonging to this customer
    scenarios: Mapped[List["Scenario"]] = relationship("Scenario", back_populates="customer", cascade="all, delete-orphan")
    watchlists: Mapped[List["Watchlist"]] = relationship("Watchlist", back_populates="customer", cascade="all, delete-orphan")

    # SAP Data Import Cadence System
    sync_job_configs: Mapped[List["SyncJobConfig"]] = relationship(
        "SyncJobConfig", back_populates="customer", cascade="all, delete-orphan"
    )

    # Workflow System
    workflow_templates: Mapped[List["WorkflowTemplate"]] = relationship(
        "WorkflowTemplate", back_populates="customer", cascade="all, delete-orphan"
    )

    # Planning Cycle Management
    planning_cycles: Mapped[List["PlanningCycle"]] = relationship(
        "PlanningCycle", back_populates="customer", cascade="all, delete-orphan"
    )


# Backward compatibility aliases
Group = Customer
GroupMode = CustomerMode

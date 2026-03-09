from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum
from sqlalchemy.sql import func

from .base import Base
from .explainability import ExplainabilityLevel


class TenantMode(str, Enum):
    """Tenant operating mode - determines navigation and behavior."""
    LEARNING = "learning"      # Simplified nav, game-like clock, turn-based (user education)
    PRODUCTION = "production"  # Full nav, real data, real planning


class ClockMode(str, Enum):
    """Clock progression mode for Learning tenants."""
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

class Tenant(Base):
    """Organization representing an Autonomy tenant (isolation boundary)."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    subdomain: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Multi-tenant provisioning defaults
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    billing_plan: Mapped[str] = mapped_column(String(20), nullable=False, default="FREE")
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_games: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_supply_chain_configs: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    current_user_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_game_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_config_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # Agent Explainability Configuration
    explainability_level: Mapped[ExplainabilityLevel] = mapped_column(
        SAEnum(ExplainabilityLevel, values_callable=lambda x: [e.value for e in x], name="explainability_level_enum"),
        nullable=False,
        server_default=ExplainabilityLevel.NORMAL.value,
        default=ExplainabilityLevel.NORMAL,
    )

    # Tenant Operating Mode (Learning vs Production)
    mode: Mapped[TenantMode] = mapped_column(
        SAEnum(TenantMode, values_callable=lambda x: [e.value for e in x], name="tenant_mode_enum"),
        nullable=False,
        server_default=TenantMode.PRODUCTION.value,
        default=TenantMode.PRODUCTION,
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
        """Check if tenant is in learning mode (user education)."""
        return self.mode == TenantMode.LEARNING

    @property
    def is_production(self) -> bool:
        """Check if tenant is in production mode."""
        return self.mode == TenantMode.PRODUCTION

    admin: Mapped["User"] = relationship("User", back_populates="admin_of_tenant", foreign_keys=[admin_id])
    users: Mapped[List["User"]] = relationship("User", back_populates="tenant", foreign_keys="User.tenant_id", cascade="all, delete-orphan")

    # Make supply_chain_configs relationship optional
    if TYPE_CHECKING:
        supply_chain_configs: Mapped[List["SupplyChainConfig"]]
    else:
        supply_chain_configs = relationship(
            "SupplyChainConfig",
            back_populates="tenant",
            cascade="all, delete-orphan",
            lazy='dynamic'
        )

    # Scenarios belonging to this tenant
    scenarios: Mapped[List["Scenario"]] = relationship("Scenario", back_populates="tenant", cascade="all, delete-orphan")
    watchlists: Mapped[List["Watchlist"]] = relationship("Watchlist", back_populates="tenant", cascade="all, delete-orphan")

    # SAP Data Import Cadence System
    sync_job_configs: Mapped[List["SyncJobConfig"]] = relationship(
        "SyncJobConfig", back_populates="tenant", cascade="all, delete-orphan"
    )

    # Workflow System
    workflow_templates: Mapped[List["WorkflowTemplate"]] = relationship(
        "WorkflowTemplate", back_populates="tenant", cascade="all, delete-orphan"
    )

    # Planning Cycle Management
    planning_cycles: Mapped[List["PlanningCycle"]] = relationship(
        "PlanningCycle", back_populates="tenant", cascade="all, delete-orphan"
    )

    # SSO Providers (explicit FK needed — SSOProvider has both tenant_id and default_tenant_id)
    sso_providers: Mapped[List["SSOProvider"]] = relationship(
        "SSOProvider", back_populates="tenant",
        foreign_keys="SSOProvider.tenant_id",
    )

    # Audit Logs
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="tenant"
    )

"""ScenarioUser model - represents a user participating in a simulation/scenario.

Terminology (Feb 2026):
- Player -> ScenarioUser (in DB/code)
- Player -> User (in UI)
- Game -> Scenario
- Gamification -> Simulation

The 'scenario_users' table stores simulation participants, distinct from 'users'
which stores platform authentication accounts. A user can have multiple
scenario_users across different scenarios.
"""
from enum import Enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, Enum as SQLEnum, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .scenario import Scenario, ScenarioUserAction
    from .function_assignment import FunctionAssignment
from .user import User
from .supply_chain import ScenarioUserInventory, ScenarioUserPeriod, Order
from .supply_chain_config import NodeType


class FunctionCategory(str, Enum):
    """Category of supply chain function."""
    PLANNING = "planning"    # Weekly/monthly horizon decisions
    EXECUTION = "execution"  # Daily/real-time horizon decisions


class ScenarioUserFunction(str, Enum):
    """Specific function a scenario user performs at a site.

    Planning functions operate on weekly/monthly horizons and set targets.
    Execution functions operate on daily/real-time horizons and fulfill orders.
    """

    # Planning Functions (weekly/monthly)
    FORECASTING = "forecasting"           # Generate demand forecasts
    DEMAND_PLANNING = "demand_planning"   # Reconcile forecasts, consensus
    INVENTORY_PLANNING = "inventory_planning"  # Safety stock, targets
    SUPPLY_PLANNING = "supply_planning"   # Net requirements, sourcing
    ALLOCATION_PLANNING = "allocation_planning"  # Supply-to-demand allocation

    # Execution Functions (daily/real-time)
    ATP_PROMISING = "atp_promising"       # Order fulfillment decisions
    SHIPPING = "shipping"                 # Outbound shipment release
    PO_CREATION = "po_creation"           # Purchase order creation
    RECEIVING = "receiving"               # Inbound goods receipt

    # Legacy: Full node responsibility (backward compatibility)
    NODE_OPERATOR = "node_operator"       # All functions at a node

    @property
    def category(self) -> FunctionCategory:
        """Get the category for this function."""
        planning_functions = {
            ScenarioUserFunction.FORECASTING,
            ScenarioUserFunction.DEMAND_PLANNING,
            ScenarioUserFunction.INVENTORY_PLANNING,
            ScenarioUserFunction.SUPPLY_PLANNING,
            ScenarioUserFunction.ALLOCATION_PLANNING,
        }
        if self in planning_functions:
            return FunctionCategory.PLANNING
        return FunctionCategory.EXECUTION

    @property
    def default_horizon_weeks(self) -> int:
        """Default planning horizon for this function."""
        horizons = {
            ScenarioUserFunction.FORECASTING: 26,
            ScenarioUserFunction.DEMAND_PLANNING: 13,
            ScenarioUserFunction.INVENTORY_PLANNING: 13,
            ScenarioUserFunction.SUPPLY_PLANNING: 8,
            ScenarioUserFunction.ALLOCATION_PLANNING: 4,
            ScenarioUserFunction.ATP_PROMISING: 1,
            ScenarioUserFunction.SHIPPING: 1,
            ScenarioUserFunction.PO_CREATION: 2,
            ScenarioUserFunction.RECEIVING: 1,
            ScenarioUserFunction.NODE_OPERATOR: 1,
        }
        return horizons.get(self, 1)

    @property
    def description(self) -> str:
        """Human-readable description of the function."""
        descriptions = {
            ScenarioUserFunction.FORECASTING: "Generate statistical/ML demand forecasts",
            ScenarioUserFunction.DEMAND_PLANNING: "Reconcile forecasts into consensus demand",
            ScenarioUserFunction.INVENTORY_PLANNING: "Set safety stock targets and policies",
            ScenarioUserFunction.SUPPLY_PLANNING: "Calculate net requirements and sourcing",
            ScenarioUserFunction.ALLOCATION_PLANNING: "Allocate supply to demand priorities",
            ScenarioUserFunction.ATP_PROMISING: "Promise orders against available inventory",
            ScenarioUserFunction.SHIPPING: "Release outbound shipments",
            ScenarioUserFunction.PO_CREATION: "Create purchase orders for replenishment",
            ScenarioUserFunction.RECEIVING: "Accept and verify inbound deliveries",
            ScenarioUserFunction.NODE_OPERATOR: "Full responsibility for all functions at node",
        }
        return descriptions.get(self, "Unknown function")


class ScenarioUserRole(str, Enum):
    """Role of a scenario user in the supply chain simulation."""
    RETAILER = NodeType.RETAILER.value
    WHOLESALER = NodeType.WHOLESALER.value
    DISTRIBUTOR = NodeType.DISTRIBUTOR.value
    MANUFACTURER = NodeType.MANUFACTURER.value
    SUPPLIER = NodeType.SUPPLIER.value
    MARKET_DEMAND = NodeType.MARKET_DEMAND.value
    MARKET_SUPPLY = NodeType.MARKET_SUPPLY.value


class ScenarioUserType(str, Enum):
    """Whether the scenario user is human or AI."""
    HUMAN = "HUMAN"
    AI = "AI"


class AgentMode(str, Enum):
    """Agent decision mode for supply chain simulation execution."""
    MANUAL = "manual"      # Human makes all decisions
    COPILOT = "copilot"    # AI suggests, human approves
    AUTONOMOUS = "autonomous"  # AI makes all decisions


class ScenarioUserStrategy(str, Enum):
    """Strategy used by the scenario user (human or AI)."""
    # Basic strategies
    MANUAL = "MANUAL"
    RANDOM = "RANDOM"
    FIXED = "FIXED"

    # Advanced strategies
    DEMAND_AVERAGE = "DEMAND_AVERAGE"
    TREND_FOLLOWER = "TREND_FOLLOWER"

    # LLM-based strategies
    LLM_BASIC = "LLM_BASIC"
    LLM_ADVANCED = "LLM_ADVANCED"
    LLM_REINFORCEMENT = "LLM_REINFORCEMENT"


class ScenarioUser(Base):
    """A user participating in a supply chain simulation/scenario.

    This represents a specific role assignment within a scenario (simulation).
    A user (platform account) can have multiple scenario_users across different
    scenarios.
    """
    __tablename__ = "scenario_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenarios.id", ondelete="CASCADE")
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[ScenarioUserRole] = mapped_column(SQLEnum(ScenarioUserRole), nullable=False)
    type: Mapped[ScenarioUserType] = mapped_column(
        SQLEnum(ScenarioUserType), default=ScenarioUserType.HUMAN
    )
    strategy: Mapped[ScenarioUserStrategy] = mapped_column(
        SQLEnum(ScenarioUserStrategy), default=ScenarioUserStrategy.MANUAL
    )
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    can_see_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="qwen3-8b"
    )
    site_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Agent mode for execution
    agent_mode: Mapped[Optional[str]] = mapped_column(
        SQLEnum(AgentMode),
        default=AgentMode.MANUAL,
        nullable=True,
        comment="Decision mode: MANUAL (human), COPILOT (AI suggests), AUTONOMOUS (AI decides)"
    )

    # Functional role within the supply chain node
    function: Mapped[Optional[ScenarioUserFunction]] = mapped_column(
        SQLEnum(ScenarioUserFunction),
        nullable=True,  # NULL = NODE_OPERATOR (backward compat)
        default=ScenarioUserFunction.NODE_OPERATOR,
        comment="Functional responsibility (forecasting, atp_promising, etc.)"
    )

    # Planning horizon override (weeks) for planning functions
    planning_horizon_weeks: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="For planners: lookahead horizon (default from function)"
    )

    # Acceptable decision latency (ms) for execution functions
    max_decision_latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="For executors: max acceptable latency (e.g., ATP=10ms)"
    )

    # Linked TRM agent type (for AI scenario users)
    trm_agent_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="TRM agent type: atp_executor, po_creation_trm, etc."
    )

    # Simulation state
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    last_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(
        "Scenario", back_populates="scenario_users", lazy="selectin"
    )
    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="scenario_users", lazy="selectin"
    )
    actions: Mapped[List["ScenarioUserAction"]] = relationship(
        "ScenarioUserAction", back_populates="scenario_user", lazy="selectin"
    )
    inventory: Mapped["ScenarioUserInventory"] = relationship(
        "ScenarioUserInventory", back_populates="scenario_user", lazy="selectin", uselist=False
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="scenario_user", lazy="selectin"
    )
    scenario_user_periods: Mapped[List["ScenarioUserPeriod"]] = relationship(
        "ScenarioUserPeriod", back_populates="scenario_user", lazy="selectin"
    )

    # Collaboration features
    agent_suggestions = relationship(
        "AgentSuggestion", back_populates="scenario_user", lazy="selectin"
    )
    what_if_analyses = relationship(
        "WhatIfAnalysis", back_populates="scenario_user", lazy="selectin"
    )

    # Function assignments (multiple functions per scenario user)
    function_assignments: Mapped[List["FunctionAssignment"]] = relationship(
        "FunctionAssignment", back_populates="scenario_user", lazy="selectin"
    )

    def __repr__(self) -> str:
        if self.site_key:
            return f"<ScenarioUser {self.name} ({self.role}, site={self.site_key})>"
        return f"<ScenarioUser {self.name} ({self.role})>"


# Backward-compatibility aliases (temporary - remove after full migration)
Participant = ScenarioUser
ParticipantRole = ScenarioUserRole
ParticipantType = ScenarioUserType
ParticipantStrategy = ScenarioUserStrategy
ParticipantFunction = ScenarioUserFunction
ParticipantAction = None  # Will be set after scenario.py imports

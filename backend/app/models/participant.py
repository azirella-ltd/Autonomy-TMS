"""Participant model - represents a user participating in a simulation/scenario.

Terminology (Feb 2026):
- Player -> Participant (in DB/code)
- Player -> User (in UI)
- Game -> Scenario
- Gamification -> Simulation

The 'participants' table stores simulation participants, distinct from 'users'
which stores platform authentication accounts. A user can have multiple
participants across different scenarios.
"""
from enum import Enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, Enum as SQLEnum, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .scenario import Scenario, ParticipantAction
    from .function_assignment import FunctionAssignment
from .user import User
from .supply_chain import ParticipantInventory, ParticipantRound, Order
from .supply_chain_config import NodeType


class FunctionCategory(str, Enum):
    """Category of supply chain function."""
    PLANNING = "planning"    # Weekly/monthly horizon decisions
    EXECUTION = "execution"  # Daily/real-time horizon decisions


class ParticipantFunction(str, Enum):
    """Specific function a participant performs at a site.

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
            ParticipantFunction.FORECASTING,
            ParticipantFunction.DEMAND_PLANNING,
            ParticipantFunction.INVENTORY_PLANNING,
            ParticipantFunction.SUPPLY_PLANNING,
            ParticipantFunction.ALLOCATION_PLANNING,
        }
        if self in planning_functions:
            return FunctionCategory.PLANNING
        return FunctionCategory.EXECUTION

    @property
    def default_horizon_weeks(self) -> int:
        """Default planning horizon for this function."""
        horizons = {
            ParticipantFunction.FORECASTING: 26,
            ParticipantFunction.DEMAND_PLANNING: 13,
            ParticipantFunction.INVENTORY_PLANNING: 13,
            ParticipantFunction.SUPPLY_PLANNING: 8,
            ParticipantFunction.ALLOCATION_PLANNING: 4,
            ParticipantFunction.ATP_PROMISING: 1,
            ParticipantFunction.SHIPPING: 1,
            ParticipantFunction.PO_CREATION: 2,
            ParticipantFunction.RECEIVING: 1,
            ParticipantFunction.NODE_OPERATOR: 1,
        }
        return horizons.get(self, 1)

    @property
    def description(self) -> str:
        """Human-readable description of the function."""
        descriptions = {
            ParticipantFunction.FORECASTING: "Generate statistical/ML demand forecasts",
            ParticipantFunction.DEMAND_PLANNING: "Reconcile forecasts into consensus demand",
            ParticipantFunction.INVENTORY_PLANNING: "Set safety stock targets and policies",
            ParticipantFunction.SUPPLY_PLANNING: "Calculate net requirements and sourcing",
            ParticipantFunction.ALLOCATION_PLANNING: "Allocate supply to demand priorities",
            ParticipantFunction.ATP_PROMISING: "Promise orders against available inventory",
            ParticipantFunction.SHIPPING: "Release outbound shipments",
            ParticipantFunction.PO_CREATION: "Create purchase orders for replenishment",
            ParticipantFunction.RECEIVING: "Accept and verify inbound deliveries",
            ParticipantFunction.NODE_OPERATOR: "Full responsibility for all functions at node",
        }
        return descriptions.get(self, "Unknown function")


class ParticipantRole(str, Enum):
    """Role of a participant in the supply chain simulation."""
    RETAILER = NodeType.RETAILER.value
    WHOLESALER = NodeType.WHOLESALER.value
    DISTRIBUTOR = NodeType.DISTRIBUTOR.value
    MANUFACTURER = NodeType.MANUFACTURER.value
    SUPPLIER = NodeType.SUPPLIER.value
    MARKET_DEMAND = NodeType.MARKET_DEMAND.value
    MARKET_SUPPLY = NodeType.MARKET_SUPPLY.value


class ParticipantType(str, Enum):
    """Whether the participant is human or AI."""
    HUMAN = "HUMAN"
    AI = "AI"


class AgentMode(str, Enum):
    """Agent decision mode for supply chain simulation execution."""
    MANUAL = "manual"      # Human makes all decisions
    COPILOT = "copilot"    # AI suggests, human approves
    AUTONOMOUS = "autonomous"  # AI makes all decisions


class ParticipantStrategy(str, Enum):
    """Strategy used by the participant (human or AI)."""
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


class Participant(Base):
    """A user participating in a supply chain simulation/scenario.

    This represents a specific role assignment within a scenario (simulation).
    A user (platform account) can have multiple participants across different
    scenarios.
    """
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenarios.id", ondelete="CASCADE")
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[ParticipantRole] = mapped_column(SQLEnum(ParticipantRole), nullable=False)
    type: Mapped[ParticipantType] = mapped_column(
        SQLEnum(ParticipantType), default=ParticipantType.HUMAN
    )
    strategy: Mapped[ParticipantStrategy] = mapped_column(
        SQLEnum(ParticipantStrategy), default=ParticipantStrategy.MANUAL
    )
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    can_see_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default="gpt-5-mini"
    )
    site_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Agent mode for execution
    agent_mode: Mapped[Optional[str]] = mapped_column(
        SQLEnum(AgentMode),
        default=AgentMode.MANUAL,
        nullable=True,
        comment="Decision mode: MANUAL (human), COPILOT (AI suggests), AUTONOMOUS (AI decides)"
    )

    # Functional role within the supply chain node (Feb 2026 expansion)
    function: Mapped[Optional[ParticipantFunction]] = mapped_column(
        SQLEnum(ParticipantFunction),
        nullable=True,  # NULL = NODE_OPERATOR (backward compat)
        default=ParticipantFunction.NODE_OPERATOR,
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

    # Linked TRM agent type (for AI participants)
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
        "Scenario", back_populates="participants", lazy="selectin"
    )
    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="participants", lazy="selectin"
    )
    actions: Mapped[List["ParticipantAction"]] = relationship(
        "ParticipantAction", back_populates="participant", lazy="selectin"
    )
    inventory: Mapped["ParticipantInventory"] = relationship(
        "ParticipantInventory", back_populates="participant", lazy="selectin", uselist=False
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="participant", lazy="selectin"
    )
    participant_rounds: Mapped[List["ParticipantRound"]] = relationship(
        "ParticipantRound", back_populates="participant", lazy="selectin"
    )

    # Collaboration features
    agent_suggestions = relationship(
        "AgentSuggestion", back_populates="participant", lazy="selectin"
    )
    what_if_analyses = relationship(
        "WhatIfAnalysis", back_populates="participant", lazy="selectin"
    )

    # Function assignments (multiple functions per participant)
    function_assignments: Mapped[List["FunctionAssignment"]] = relationship(
        "FunctionAssignment", back_populates="participant", lazy="selectin"
    )

    def __repr__(self) -> str:
        if self.site_key:
            return f"<Participant {self.name} ({self.role}, site={self.site_key})>"
        return f"<Participant {self.name} ({self.role})>"

"""Function Assignment model for mapping participants to supply chain functions.

This enables multiple participants per site with different planning and execution
functions. Each function can be assigned with a different agent mode (MANUAL,
COPILOT, AUTONOMOUS).

Terminology (Feb 2026):
- game_id -> scenario_id
- Game -> Scenario
- player -> participant
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, Enum as SQLEnum, ForeignKey, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .participant import ParticipantFunction, AgentMode

if TYPE_CHECKING:
    from .scenario import Scenario
    from .participant import Participant


class FunctionAssignment(Base):
    """Assignment of a participant to a specific function at a site.

    Enables multiple participants per site with different functions.
    For example, one participant handles ATP/Order Promising while another
    handles Inventory Planning at the same distribution center.

    Key concepts:
    - function: The specific planning or execution responsibility
    - agent_mode: MANUAL (human), COPILOT (AI suggests), or AUTONOMOUS (AI decides)
    - auto_execute_threshold: Confidence level for automatic execution in COPILOT/AUTONOMOUS
    """
    __tablename__ = "function_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    site_key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="The supply chain site (node) this function operates on"
    )

    # Function assignment
    function: Mapped[ParticipantFunction] = mapped_column(
        SQLEnum(ParticipantFunction), nullable=False,
        comment="The planning or execution function assigned"
    )

    # Agent mode for this function
    agent_mode: Mapped[AgentMode] = mapped_column(
        SQLEnum(AgentMode), default=AgentMode.MANUAL,
        comment="Decision mode for this function"
    )

    # Auto-execution confidence threshold (for COPILOT/AUTONOMOUS modes)
    auto_execute_threshold: Mapped[float] = mapped_column(
        Float, default=0.8,
        comment="Confidence threshold (0-1) for automatic execution"
    )

    # Is this function active for this scenario?
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="Whether this function assignment is currently active"
    )

    # Override planning horizon (weeks) for this specific assignment
    planning_horizon_weeks: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Override for default function horizon"
    )

    # Linked TRM agent type for AI execution
    trm_agent_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="TRM agent type: atp_executor, po_creation_trm, etc."
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(
        "Scenario", back_populates="function_assignments", lazy="selectin"
    )
    participant: Mapped["Participant"] = relationship(
        "Participant", back_populates="function_assignments", lazy="selectin"
    )

    # Unique constraint: one participant per function per site per scenario
    __table_args__ = (
        UniqueConstraint(
            'scenario_id', 'site_key', 'function',
            name='uq_scenario_site_function'
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FunctionAssignment(id={self.id}, site={self.site_key}, "
            f"function={self.function.value}, mode={self.agent_mode.value})>"
        )

    @property
    def effective_horizon_weeks(self) -> int:
        """Get the effective planning horizon, using override if set."""
        if self.planning_horizon_weeks is not None:
            return self.planning_horizon_weeks
        return self.function.default_horizon_weeks

    @property
    def is_planning_function(self) -> bool:
        """Check if this is a planning (vs execution) function."""
        from .participant import FunctionCategory
        return self.function.category == FunctionCategory.PLANNING

    @property
    def is_execution_function(self) -> bool:
        """Check if this is an execution (vs planning) function."""
        from .participant import FunctionCategory
        return self.function.category == FunctionCategory.EXECUTION

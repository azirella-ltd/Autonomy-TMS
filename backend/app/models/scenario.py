"""Scenario model - represents a simulation/planning scenario in supply chain planning.

This module contains the core Scenario model (formerly Alternative/Game).

Terminology (Feb 2026):
- Game -> Scenario (clean break, no backward compat)
- Simulation -> Simulation
- Player -> ScenarioUser (in DB/code)
- Player -> User (in UI)

The 'scenarios' table stores simulation scenarios. Each scenario has
scenario_users (human or AI) who take on roles in the supply chain.
"""
from enum import Enum
from datetime import datetime, date
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, Enum as SQLEnum, JSON, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship, Mapped, mapped_column, Session

from .base import Base
from app.core.time_buckets import TimeBucket, DEFAULT_START_DATE

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .tenant import Tenant
    from .participant import ScenarioUser
    from .user import User
    from .agent_config import AgentConfig
    from .supply_chain import ScenarioRound as SCScenarioRound
    from .supply_chain_config import SupplyChainConfig
    from .function_assignment import FunctionAssignment


class ScenarioStatus(str, Enum):
    """Status of a scenario/simulation."""
    CREATED = "CREATED"
    STARTED = "STARTED"
    PERIOD_IN_PROGRESS = "PERIOD_IN_PROGRESS"
    PERIOD_COMPLETED = "PERIOD_COMPLETED"
    FINISHED = "FINISHED"


class Scenario(Base):
    """A supply chain simulation/scenario.

    Scenarios represent individual simulation runs where scenario users
    (human or AI) take on supply chain roles and make decisions.
    """
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[ScenarioStatus] = mapped_column(
        SQLEnum(ScenarioStatus, name="scenariostatus", create_type=False),
        default=ScenarioStatus.CREATED,
    )
    current_period: Mapped[int] = mapped_column(Integer, default=0)
    max_periods: Mapped[int] = mapped_column(Integer, default=52)

    # Optional metadata/ownership
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    demand_pattern: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    time_bucket: Mapped[str] = mapped_column(String(16), default=TimeBucket.WEEK.value)
    start_date: Mapped[date] = mapped_column(Date, default=DEFAULT_START_DATE)
    current_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    supply_chain_config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # SC Planning Integration
    use_sc_planning: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # DAG Sequential Execution
    use_dag_sequential: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Role assignments: {role: {'is_ai': bool, 'agent_config_id': Optional[int], 'user_id': Optional[int]}}
    role_assignments: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    scenario_users: Mapped[List["ScenarioUser"]] = relationship("ScenarioUser", back_populates="scenario", lazy="selectin")
    rounds: Mapped[List["Round"]] = relationship("Round", back_populates="scenario", lazy="selectin")
    supply_chain_rounds: Mapped[List["SCScenarioRound"]] = relationship(
        "ScenarioRound", back_populates="scenario", lazy="selectin"
    )
    users = relationship("User", secondary="user_scenarios", back_populates="scenarios", lazy="selectin")
    supervisor_actions = relationship("SupervisorAction", back_populates="scenario", lazy="selectin")
    agent_configs = relationship("AgentConfig", back_populates="scenario", lazy="selectin")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="scenarios")
    supply_chain_config: Mapped["SupplyChainConfig"] = relationship(
        "SupplyChainConfig",
        back_populates="scenarios",
    )

    # A2A Collaboration
    chat_messages = relationship("ChatMessage", back_populates="scenario", lazy="selectin")
    agent_suggestions = relationship("AgentSuggestion", back_populates="scenario", lazy="selectin")
    what_if_analyses = relationship("WhatIfAnalysis", back_populates="scenario", lazy="selectin")

    # Function assignments
    function_assignments: Mapped[List["FunctionAssignment"]] = relationship(
        "FunctionAssignment", back_populates="scenario", lazy="selectin"
    )

    def get_role_assignment(self, role: str) -> Dict[str, Any]:
        """Get the assignment for a specific role."""
        return self.role_assignments.get(role, {'is_ai': False, 'agent_config_id': None, 'user_id': None})

    def set_role_assignment(self, role: str, is_ai: bool, agent_config_id: Optional[int] = None, user_id: Optional[int] = None):
        """Set the assignment for a specific role."""
        if not hasattr(self, 'role_assignments') or not self.role_assignments:
            self.role_assignments = {}
        self.role_assignments[role] = {
            'is_ai': is_ai,
            'agent_config_id': agent_config_id,
            'user_id': user_id if not is_ai else None
        }

    def get_agent_config(self, role: str, db: Session) -> Optional['AgentConfig']:
        """Get the agent configuration for a role."""
        from .agent_config import AgentConfig
        assignment = self.get_role_assignment(role)
        if not assignment or not assignment['is_ai'] or not assignment['agent_config_id']:
            return None
        return db.query(AgentConfig).filter(
            AgentConfig.id == assignment['agent_config_id'],
            AgentConfig.scenario_id == self.id
        ).first()


class Round(Base):
    """A round within a scenario/simulation."""
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="rounds", lazy="selectin")
    scenario_user_actions: Mapped[List["ScenarioUserAction"]] = relationship("ScenarioUserAction", back_populates="round", lazy="selectin")


class ScenarioUserAction(Base):
    """An action taken by a scenario user during a round.

    Records decisions made by scenario users (human or AI) during simulation.
    """
    __tablename__ = "scenario_user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"))
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id", ondelete="CASCADE"))
    scenario_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenario_users.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    round: Mapped["Round"] = relationship("Round", back_populates="scenario_user_actions", lazy="selectin")
    scenario_user: Mapped["ScenarioUser"] = relationship("ScenarioUser", back_populates="actions", lazy="selectin")
    scenario: Mapped["Scenario"] = relationship("Scenario", lazy="selectin")


# Backward-compatibility aliases (temporary - remove after full migration)
ParticipantAction = ScenarioUserAction

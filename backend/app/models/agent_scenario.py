"""
Scenario Engine — Database Models

ORM models for machine-speed what-if planning:
  - AgentScenario: scenario branches (fork of digital twin state)
  - AgentScenarioAction: individual actions within a scenario
  - ScenarioTemplate: template library with Beta priors for candidate ranking

See docs/internal/SCENARIO_ENGINE.md for full architecture.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON,
    ForeignKey, Index, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class AgentScenario(Base):
    """
    A scenario branch — a lightweight fork of the digital twin.

    Lifecycle: CREATED → EVALUATING → SCORED → PROMOTED | REJECTED | EXPIRED

    Analogous to a Git feature branch: the Plan of Record is 'main',
    agents create branches to test alternatives, the best branch is
    merged (promoted), and rejected branches are retained for training.
    """
    __tablename__ = "agent_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    parent_scenario_id = Column(Integer, ForeignKey("agent_scenarios.id"), nullable=True)

    # Trigger context — what decision prompted this scenario
    trigger_decision_id = Column(Integer, nullable=True)
    trigger_trm_type = Column(String(50), nullable=False)
    trigger_context = Column(JSON, nullable=True)  # order details, shortfall, urgency

    # Decision level in Powell hierarchy
    decision_level = Column(String(20), nullable=False, default="execution")

    # Lifecycle status
    status = Column(String(20), nullable=False, default="CREATED")

    # BSC scoring results
    raw_bsc_score = Column(Float, nullable=True)
    compound_likelihood = Column(Float, nullable=True)
    urgency_discount = Column(Float, nullable=True)
    final_score = Column(Float, nullable=True)
    bsc_breakdown = Column(JSON, nullable=True)  # per-dimension scores
    context_weights = Column(JSON, nullable=True)  # dynamic BSC weights used

    # Simulation parameters
    simulation_days = Column(Integer, nullable=True)
    simulation_seed = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    scored_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    actions = relationship(
        "AgentScenarioAction",
        back_populates="scenario",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_scenarios_config", "config_id", "status"),
        Index("ix_agent_scenarios_trigger", "trigger_trm_type", "created_at"),
        Index("ix_agent_scenarios_tenant", "tenant_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "parent_scenario_id": self.parent_scenario_id,
            "trigger_decision_id": self.trigger_decision_id,
            "trigger_trm_type": self.trigger_trm_type,
            "trigger_context": self.trigger_context,
            "decision_level": self.decision_level,
            "status": self.status,
            "raw_bsc_score": self.raw_bsc_score,
            "compound_likelihood": self.compound_likelihood,
            "urgency_discount": self.urgency_discount,
            "final_score": self.final_score,
            "bsc_breakdown": self.bsc_breakdown,
            "context_weights": self.context_weights,
            "simulation_days": self.simulation_days,
            "simulation_seed": self.simulation_seed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "actions": [a.to_dict() for a in (self.actions or [])],
        }


class AgentScenarioAction(Base):
    """
    An individual action within a scenario branch.

    Each action is a proposed decision (CREATE_PO, EXPEDITE_TO, etc.)
    that a responsible TRM agent must approve/execute if the scenario
    is promoted.
    """
    __tablename__ = "agent_scenario_actions"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(
        Integer,
        ForeignKey("agent_scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    trm_type = Column(String(50), nullable=False)
    action_type = Column(String(50), nullable=False)  # CREATE_PO, EXPEDITE_TO, etc.
    action_params = Column(JSON, nullable=True)  # product_id, quantity, supplier, etc.
    responsible_agent = Column(String(50), nullable=True)  # which TRM type must execute

    # CDT risk bound for this individual action
    decision_likelihood = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    estimated_benefit = Column(Float, nullable=True)

    # Action status within the scenario
    status = Column(String(20), nullable=False, default="PROPOSED")
    actioned_decision_id = Column(Integer, nullable=True)  # FK to powell_*_decisions when promoted

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    scenario = relationship("AgentScenario", back_populates="actions")

    __table_args__ = (
        Index("ix_scenario_actions_scenario", "scenario_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "trm_type": self.trm_type,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "responsible_agent": self.responsible_agent,
            "decision_likelihood": self.decision_likelihood,
            "estimated_cost": self.estimated_cost,
            "estimated_benefit": self.estimated_benefit,
            "status": self.status,
            "actioned_decision_id": self.actioned_decision_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScenarioTemplate(Base):
    """
    Template library for candidate scenario generation.

    Each template represents a known response pattern for a TRM type
    (e.g., "split fulfillment" for ATP shortfall). Templates carry a
    Beta(alpha, beta) posterior tracking historical success rate:

        prior_likelihood = alpha / (alpha + beta)

    Templates are sorted by prior_likelihood DESC and tried in order.
    The posterior is updated on each promoted/rejected scenario outcome.
    """
    __tablename__ = "scenario_templates"

    id = Column(Integer, primary_key=True, index=True)
    trm_type = Column(String(50), nullable=False)
    template_key = Column(String(100), nullable=False)  # e.g., 'split_fulfillment'
    template_name = Column(String(255), nullable=False)
    template_params = Column(JSON, nullable=True)  # configurable parameters

    # Beta posterior parameters
    alpha = Column(Float, default=1.0, nullable=False)  # Success pseudo-count
    beta_param = Column(Float, default=1.0, nullable=False)  # Failure pseudo-count

    # Usage tracking
    uses_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_scenario_templates_trm", "trm_type", "tenant_id"),
    )

    @property
    def prior_likelihood(self) -> float:
        """Expected success probability from Beta posterior."""
        return self.alpha / (self.alpha + self.beta_param)

    def to_dict(self):
        return {
            "id": self.id,
            "trm_type": self.trm_type,
            "template_key": self.template_key,
            "template_name": self.template_name,
            "template_params": self.template_params,
            "alpha": self.alpha,
            "beta_param": self.beta_param,
            "prior_likelihood": self.prior_likelihood,
            "uses_count": self.uses_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

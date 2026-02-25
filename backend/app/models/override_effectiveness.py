"""
Override Effectiveness — Bayesian Posterior and Causal Match Models

Maintains Beta distribution posteriors for override quality by (user, trm_type)
and stores propensity-score-matched pairs for causal inference.

See docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md for the full methodology.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.base_class import Base


class OverrideEffectivenessPosterior(Base):
    """
    Bayesian Beta posterior for override effectiveness by (user, trm_type).

    Starts with uninformative prior Beta(1,1) → E[p]=0.50.
    Each observed outcome updates alpha (success) or beta (failure)
    with signal strength based on the observability tier.

    Training weight is derived from the posterior:
        weight = 0.3 + 1.7 * E[p], capped by certainty.
    """
    __tablename__ = "override_effectiveness_posteriors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trm_type = Column(String(50), nullable=False)
    site_key = Column(String(100), nullable=True)  # Optional site-level refinement

    # Beta distribution parameters
    alpha = Column(Float, default=1.0, nullable=False)    # Success pseudo-count
    beta_param = Column(Float, default=1.0, nullable=False)  # Failure pseudo-count

    # Derived (updated on each observation)
    expected_effectiveness = Column(Float, default=0.5)
    observation_count = Column(Integer, default=0)
    training_weight = Column(Float, default=0.85)

    # Metadata
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id", "trm_type", "site_key",
            name="uq_posterior_user_trm_site",
        ),
        Index("idx_posterior_user_trm", "user_id", "trm_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trm_type": self.trm_type,
            "site_key": self.site_key,
            "alpha": self.alpha,
            "beta_param": self.beta_param,
            "expected_effectiveness": self.expected_effectiveness,
            "observation_count": self.observation_count,
            "training_weight": self.training_weight,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class CausalMatchPair(Base):
    """
    Propensity-score-matched pairs for Tier 2 causal inference.

    Each row links an overridden decision to a similar non-overridden
    decision (matched on state vector) and records the treatment effect.
    """
    __tablename__ = "override_causal_match_pairs"

    id = Column(Integer, primary_key=True, index=True)
    overridden_decision_id = Column(
        Integer, ForeignKey("powell_site_agent_decisions.id"), index=True,
    )
    control_decision_id = Column(
        Integer, ForeignKey("powell_site_agent_decisions.id"), index=True,
    )

    trm_type = Column(String(50), nullable=False, index=True)
    state_distance = Column(Float)     # L2 norm of normalised state diff
    propensity_score = Column(Float)   # P(override | state)

    # Outcomes
    override_reward = Column(Float)
    control_reward = Column(Float)
    treatment_effect = Column(Float)   # override_reward - control_reward

    match_quality = Column(String(20))  # HIGH, MEDIUM, LOW
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_causal_match_trm", "trm_type", "match_quality"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "overridden_decision_id": self.overridden_decision_id,
            "control_decision_id": self.control_decision_id,
            "trm_type": self.trm_type,
            "state_distance": self.state_distance,
            "treatment_effect": self.treatment_effect,
            "match_quality": self.match_quality,
        }

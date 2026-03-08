"""
Powell Framework Models - Sequential Decision Analytics & Modeling

This module implements the Powell SDAM framework models for:
- Belief State: Uncertainty quantification via conformal prediction
- Policy Parameters: Optimized policy parameters (θ) from CFA
- Value Function: VFA state values for TRM/RL agents

Reference: Warren B. Powell - Sequential Decision Analytics and Modeling (SDAM)
"""

from datetime import datetime, date
from typing import Optional, Dict, List, Any
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, JSON, DateTime, Date, Text,
    ForeignKey, Index, Enum as SAEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from enum import Enum

from .base import Base


class ConformalMethod(str, Enum):
    """Conformal prediction methods for uncertainty quantification."""
    SPLIT = "split"          # Split conformal
    JACKKNIFE = "jackknife"  # Jackknife+
    CV_PLUS = "cv_plus"      # Cross-validation+
    ADAPTIVE = "adaptive"    # Adaptive conformal inference (ACI)
    WEIGHTED = "weighted"    # Weighted conformal


class EntityType(str, Enum):
    """Types of entities that can have belief states."""
    DEMAND = "demand"
    LEAD_TIME = "lead_time"
    YIELD = "yield"
    CAPACITY = "capacity"
    PRICE = "price"
    SERVICE_LEVEL = "service_level"
    INVENTORY = "inventory"
    COST = "cost"


class PolicyType(str, Enum):
    """Types of policies that can be optimized."""
    INVENTORY = "inventory"       # Safety stock, reorder point
    LOT_SIZING = "lot_sizing"     # EOQ, POQ parameters
    EXCEPTION = "exception"       # Exception thresholds
    ALLOCATION = "allocation"     # Priority allocation rules
    SOURCING = "sourcing"         # Vendor selection rules


class PowellBeliefState(Base):
    """
    Belief State for Powell Framework - Uncertainty Quantification

    Stores point estimates with conformal prediction intervals that provide
    coverage guarantees. Used by agents to quantify uncertainty and by the
    feedback loop to recalibrate predictions.

    Conformal prediction provides calibrated intervals:
    - Given target coverage α (e.g., 0.80), intervals contain true value ~α of the time
    - Residuals track prediction errors for adaptive recalibration
    - Coverage history tracks actual coverage for drift detection
    """
    __tablename__ = "powell_belief_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="powell_entity_type_enum"),
        nullable=False,
        comment="Type of entity: demand, lead_time, yield, etc."
    )
    entity_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Entity identifier (product_id, site_id, or product_site key)"
    )

    # Point estimate
    point_estimate: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Best single-value estimate"
    )

    # Conformal prediction intervals
    conformal_lower: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Lower bound of conformal interval"
    )
    conformal_upper: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Upper bound of conformal interval"
    )
    conformal_coverage: Mapped[Optional[float]] = mapped_column(
        Float,
        default=0.80,
        comment="Target coverage probability (e.g., 0.80 for 80% intervals)"
    )
    conformal_method: Mapped[Optional[ConformalMethod]] = mapped_column(
        SAEnum(ConformalMethod, name="conformal_method_enum"),
        default=ConformalMethod.ADAPTIVE,
        comment="Conformal prediction method used"
    )

    # Nonconformity tracking - how unusual is current context?
    nonconformity_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Current nonconformity score (lower = more typical)"
    )
    nonconformity_threshold: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Threshold for flagging unusual situations"
    )

    # Adaptive conformal tracking (for recalibration)
    recent_residuals: Mapped[Optional[List]] = mapped_column(
        JSON,
        comment="Last N residuals (predicted - actual) for adaptive conformal"
    )
    coverage_history: Mapped[Optional[List]] = mapped_column(
        JSON,
        comment="Last N coverage indicators (1 if in interval, 0 if not)"
    )

    # Calibration metrics
    empirical_coverage: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Actual observed coverage rate over history"
    )
    interval_width_mean: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Mean interval width (measure of precision)"
    )
    last_recalibration: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="When intervals were last recalibrated"
    )

    # Drift detection
    drift_detected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether significant drift has been detected"
    )
    drift_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Drift detection score (e.g., CUSUM statistic)"
    )

    # Distribution fit metadata (Kravanja 2026)
    # Stores fitted distribution type/params alongside conformal intervals
    # for diagnostic enrichment and hybrid policies (sl_conformal_fitted)
    distribution_fit: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Fitted distribution metadata: {dist_type, params, ks_pvalue, is_normal_like}"
    )

    # Metadata
    observation_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of observations used for this belief state"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        Index('idx_belief_entity', 'entity_type', 'entity_id'),
        Index('idx_belief_tenant', 'tenant_id', 'entity_type'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "entity_type": self.entity_type.value if self.entity_type else None,
            "entity_id": self.entity_id,
            "point_estimate": self.point_estimate,
            "conformal_lower": self.conformal_lower,
            "conformal_upper": self.conformal_upper,
            "conformal_coverage": self.conformal_coverage,
            "conformal_method": self.conformal_method.value if self.conformal_method else None,
            "nonconformity_score": self.nonconformity_score,
            "empirical_coverage": self.empirical_coverage,
            "interval_width_mean": self.interval_width_mean,
            "drift_detected": self.drift_detected,
            "drift_score": self.drift_score,
            "distribution_fit": self.distribution_fit,
            "observation_count": self.observation_count,
            "last_recalibration": self.last_recalibration.isoformat() if self.last_recalibration else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PowellPolicyParameters(Base):
    """
    Optimized Policy Parameters from Powell CFA (Cost Function Approximation)

    Stores optimized policy parameters (θ) derived from Monte Carlo optimization.
    These parameters define the behavior of inventory policies, lot sizing rules,
    exception thresholds, etc.

    Example: Safety stock multiplier optimized across 1000 demand scenarios
    to minimize expected cost while maintaining target service level.
    """
    __tablename__ = "powell_policy_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False
    )
    policy_type: Mapped[PolicyType] = mapped_column(
        SAEnum(PolicyType, name="powell_policy_type_enum"),
        nullable=False,
        comment="Type of policy: inventory, lot_sizing, exception, etc."
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Scope: product, site, product_site"
    )
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(200),
        comment="Entity identifier for scoped parameters"
    )

    # Optimized parameters (flexible JSON structure)
    parameters: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Optimized parameter values: {safety_stock_multiplier: 1.65, ...}"
    )

    # Optimization metadata
    optimization_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Method: monte_carlo, gradient_descent, bayesian"
    )
    optimization_objective: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Objective: min_cost, max_service_level, min_inventory"
    )
    optimization_value: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Best objective value achieved"
    )
    confidence_interval_lower: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Lower CI bound on optimal value"
    )
    confidence_interval_upper: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Upper CI bound on optimal value"
    )
    num_scenarios: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Number of Monte Carlo scenarios used"
    )
    num_iterations: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Number of optimization iterations"
    )

    # Validity period
    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # GraphSAGE reasoning — English explanation of why these parameters were chosen
    decision_reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="English explanation of why GraphSAGE/CFA chose these policy parameters"
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_policy_config', 'config_id', 'policy_type'),
        Index('idx_policy_entity', 'entity_type', 'entity_id'),
    )


class PowellValueFunction(Base):
    """
    Value Function Approximation State for TRM/RL Agents

    Stores V(s) and Q(s,a) estimates learned via TD learning.
    Provides tabular fallback when neural VFA (TRM) uncertainty is high.

    Used by:
    - TRM agents for decision validation
    - RL fine-tuning for value targets
    - Explainability (show Q-value comparison)
    """
    __tablename__ = "powell_value_function"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False
    )
    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Agent type: trm, rl, gnn"
    )

    # State discretization (for tabular VFA)
    state_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Discretized state key for tabular lookup"
    )

    # Value estimates
    v_value: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="V(s) estimate - expected value from this state"
    )
    q_values: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Q(s,a) estimates by action: {action_key: q_value}"
    )

    # TD learning metadata
    td_error_history: Mapped[Optional[List]] = mapped_column(
        JSON,
        comment="Recent TD errors for learning diagnostics"
    )
    update_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of updates to this state"
    )
    last_visit: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        comment="When this state was last visited"
    )

    # Uncertainty
    v_variance: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Variance estimate for V(s)"
    )
    confidence_radius: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Confidence radius for UCB exploration"
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        Index('idx_vf_config_agent', 'config_id', 'agent_type'),
        Index('idx_vf_state', 'state_key'),
    )


class PowellCalibrationLog(Base):
    """
    Calibration Log for Feedback Loop

    Tracks calibration events and recalibration history for audit trail.
    Enables analysis of prediction quality over time.
    """
    __tablename__ = "powell_calibration_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    belief_state_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("powell_belief_state.id", ondelete="CASCADE"),
        nullable=False
    )

    # Observation
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_lower: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_upper: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    in_interval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    residual: Mapped[float] = mapped_column(Float, nullable=False)

    # Metrics at time of prediction
    nonconformity_score: Mapped[Optional[float]] = mapped_column(Float)

    # Link to action if applicable
    action_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("agent_action.id", ondelete="SET NULL")
    )

    # Timestamp
    observed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    belief_state = relationship("PowellBeliefState")
    action = relationship("AgentAction")

    __table_args__ = (
        Index('idx_calibration_belief', 'belief_state_id', 'observed_at'),
    )


class PowellSOPEmbedding(Base):
    """
    Cached S&OP GraphSAGE embeddings and analysis scores per site.

    Computed by SOPInferenceService when running network analysis.
    These are consumed by:
    - Execution tGNN (structural_embeddings as input features)
    - AllocationService (criticality-weighted priority)
    - RebalancingTRM (bottleneck_risk for transfer targeting)
    - SiteAgent (embedded in state encoding)

    Refresh: Weekly/Monthly (matches S&OP cadence)
    """
    __tablename__ = "powell_sop_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Context
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False
    )
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False
    )
    site_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Structural embedding vector (64-dim by default)
    embedding: Mapped[Dict] = mapped_column(JSON, nullable=False)  # List[float]

    # S&OP analysis scores (all 0-1)
    criticality: Mapped[float] = mapped_column(Float, nullable=False)
    bottleneck_risk: Mapped[float] = mapped_column(Float, nullable=False)
    concentration_risk: Mapped[float] = mapped_column(Float, nullable=False)
    resilience: Mapped[float] = mapped_column(Float, nullable=False)
    safety_stock_multiplier: Mapped[float] = mapped_column(Float, nullable=False)

    # Network-level risk scores (from global aggregation)
    network_risk: Mapped[Optional[Dict]] = mapped_column(JSON)  # {overall, supply, demand, operational}

    # Checkpoint used
    checkpoint_path: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamps
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_sop_embedding_config_site', 'config_id', 'site_id'),
        Index('idx_sop_embedding_computed', 'config_id', 'computed_at'),
    )

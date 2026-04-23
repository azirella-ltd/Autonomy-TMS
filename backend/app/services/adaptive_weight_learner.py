"""
Adaptive Weight Learner

Learns optimal agent weights over time based on performance feedback.

Learning Methods:
- Exponential Moving Average (EMA): Smooth weight updates
- Multi-Armed Bandits (MAB): Exploration vs exploitation
- Performance-Based: Direct performance-to-weight mapping
- Gradient Descent: Optimize weights to minimize cost

Persistence:
- Stores learned weights per scenario/scenario_user/config
- Allows rollback to previous weight configurations
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, ForeignKey, Boolean
from enum import Enum
import statistics
import logging
import math

from app.models.base import Base

logger = logging.getLogger(__name__)


class LearningMethod(str, Enum):
    """Weight learning algorithms."""
    EMA = "ema"  # Exponential Moving Average
    UCB = "ucb"  # Upper Confidence Bound (MAB)
    THOMPSON = "thompson"  # Thompson Sampling (MAB)
    PERFORMANCE = "performance"  # Direct performance mapping
    GRADIENT = "gradient"  # Gradient descent on cost


@dataclass
class WeightUpdate:
    """Record of weight update event."""
    agent_type: str
    old_weight: float
    new_weight: float
    performance_score: float
    reason: str
    timestamp: str


@dataclass
class AdaptiveWeights:
    """Learned agent weights with metadata."""
    weights: Dict[str, float]  # Agent type -> weight
    confidence: float  # Confidence in these weights (0-1)
    num_samples: int  # Number of decisions used to learn
    performance_metrics: Dict[str, float]  # Performance per agent
    learning_method: str
    last_updated: str


class AdaptiveWeightLearner:
    """
    Learns optimal agent weights through online learning.

    Uses various algorithms to adapt weights based on observed performance:
    - EMA: Smooth updates with exponential decay
    - UCB: Optimistic exploration with confidence bounds
    - Thompson Sampling: Bayesian bandit algorithm
    - Performance: Direct mapping from performance to weights
    - Gradient Descent: Optimize cost function
    """

    def __init__(
        self,
        db: Session,
        learning_method: LearningMethod = LearningMethod.EMA,
        learning_rate: float = 0.1,
        exploration_factor: float = 1.0,
        min_samples_for_confidence: int = 30
    ):
        """
        Initialize adaptive learner.

        Args:
            db: Database session
            learning_method: Algorithm to use
            learning_rate: How quickly to adapt (0-1, higher = faster adaptation)
            exploration_factor: Exploration vs exploitation tradeoff (UCB/Thompson)
            min_samples_for_confidence: Minimum samples for full confidence
        """
        self.db = db
        self.learning_method = learning_method
        self.learning_rate = learning_rate
        self.exploration_factor = exploration_factor
        self.min_samples_for_confidence = min_samples_for_confidence

    def learn_weights(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float],
        context_id: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Update weights based on observed performance.

        Args:
            agent_type: Agent that was evaluated
            performance_score: Performance metric (0-1, higher = better)
            current_weights: Current weight distribution
            context_id: Scenario/scenario_user/config ID for persistence

        Returns:
            Updated weights (normalized to sum to 1.0)
        """
        if self.learning_method == LearningMethod.EMA:
            new_weights = self._learn_ema(agent_type, performance_score, current_weights)
        elif self.learning_method == LearningMethod.UCB:
            new_weights = self._learn_ucb(agent_type, performance_score, current_weights, context_id)
        elif self.learning_method == LearningMethod.THOMPSON:
            new_weights = self._learn_thompson(agent_type, performance_score, current_weights, context_id)
        elif self.learning_method == LearningMethod.PERFORMANCE:
            new_weights = self._learn_performance_based(agent_type, performance_score, current_weights)
        elif self.learning_method == LearningMethod.GRADIENT:
            new_weights = self._learn_gradient(agent_type, performance_score, current_weights)
        else:
            raise ValueError(f"Unknown learning method: {self.learning_method}")

        # Persist if context_id provided
        if context_id:
            self._persist_weights(
                context_id=context_id,
                weights=new_weights,
                learning_method=self.learning_method.value
            )

        logger.info(
            f"Learned weights via {self.learning_method.value}: "
            f"{agent_type} performance={performance_score:.3f}, "
            f"new_weights={new_weights}"
        )

        return new_weights

    def _learn_ema(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Exponential Moving Average: Smooth weight updates.

        Formula: new_weight = old_weight + learning_rate * (performance - old_weight)
        """
        new_weights = current_weights.copy()

        # Update target agent's weight based on performance
        old_weight = current_weights.get(agent_type, 1.0 / len(current_weights))
        new_weight = old_weight + self.learning_rate * (performance_score - old_weight)

        new_weights[agent_type] = new_weight

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        return new_weights

    def _learn_ucb(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float],
        context_id: Optional[int]
    ) -> Dict[str, float]:
        """
        Upper Confidence Bound: Optimistic exploration.

        Formula: UCB = avg_reward + exploration_factor * sqrt(ln(total_trials) / agent_trials)
        """
        # Get historical performance stats
        stats = self._get_agent_stats(context_id) if context_id else {}

        # Update stats for this agent
        if agent_type not in stats:
            stats[agent_type] = {"total_reward": 0.0, "count": 0}

        stats[agent_type]["total_reward"] += performance_score
        stats[agent_type]["count"] += 1

        total_trials = sum(s["count"] for s in stats.values())

        # Calculate UCB for each agent
        ucb_scores = {}
        for agent, stat in stats.items():
            avg_reward = stat["total_reward"] / stat["count"] if stat["count"] > 0 else 0.0
            exploration_bonus = self.exploration_factor * math.sqrt(
                math.log(total_trials) / stat["count"] if stat["count"] > 0 else float('inf')
            )
            ucb_scores[agent] = avg_reward + exploration_bonus

        # Convert UCB scores to weights (softmax)
        new_weights = self._softmax(ucb_scores)

        # Persist stats
        if context_id:
            self._persist_agent_stats(context_id, stats)

        return new_weights

    def _learn_thompson(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float],
        context_id: Optional[int]
    ) -> Dict[str, float]:
        """
        Thompson Sampling: Bayesian bandit algorithm.

        Maintains Beta distribution for each agent:
        - Alpha: Number of successes
        - Beta: Number of failures
        """
        # Get beta distribution parameters
        beta_params = self._get_beta_params(context_id) if context_id else {}

        # Update for this agent (success if performance > 0.7)
        if agent_type not in beta_params:
            beta_params[agent_type] = {"alpha": 1.0, "beta": 1.0}

        if performance_score > 0.7:
            beta_params[agent_type]["alpha"] += 1
        else:
            beta_params[agent_type]["beta"] += 1

        # Sample from each agent's beta distribution
        import random
        samples = {}
        for agent, params in beta_params.items():
            samples[agent] = random.betavariate(params["alpha"], params["beta"])

        # Convert samples to weights (softmax)
        new_weights = self._softmax(samples)

        # Persist beta params
        if context_id:
            self._persist_beta_params(context_id, beta_params)

        return new_weights

    def _learn_performance_based(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Direct performance-to-weight mapping.

        Weights are directly proportional to recent performance.
        """
        # Update performance score for this agent
        # (Simplified: assumes all agents have been evaluated equally)
        new_weights = current_weights.copy()
        new_weights[agent_type] = performance_score

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        return new_weights

    def _learn_gradient(
        self,
        agent_type: str,
        performance_score: float,
        current_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Gradient descent on cost function.

        Gradient: d(cost)/d(weight) ≈ -(performance - avg_performance)
        Update: weight -= learning_rate * gradient
        """
        new_weights = current_weights.copy()

        # Approximate gradient (negative of performance deviation)
        avg_performance = statistics.mean(current_weights.values()) if current_weights else 0.5
        gradient = -(performance_score - avg_performance)

        # Update weight
        old_weight = current_weights.get(agent_type, 1.0 / len(current_weights))
        new_weight = old_weight - self.learning_rate * gradient

        # Clamp to positive
        new_weight = max(0.01, new_weight)

        new_weights[agent_type] = new_weight

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        return new_weights

    def _softmax(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Convert scores to probabilities via softmax."""
        import math

        # Calculate exp(score) for each agent
        exp_scores = {agent: math.exp(score) for agent, score in scores.items()}

        # Normalize
        total = sum(exp_scores.values())
        if total > 0:
            return {agent: exp_score / total for agent, exp_score in exp_scores.items()}
        else:
            # Equal weights if all scores are -inf
            num_agents = len(scores)
            return {agent: 1.0 / num_agents for agent in scores.keys()}

    def get_learned_weights(
        self,
        context_id: int
    ) -> Optional[AdaptiveWeights]:
        """
        Retrieve learned weights for a context.

        Args:
            context_id: Scenario/scenario_user/config ID

        Returns:
            AdaptiveWeights or None if not found
        """
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).order_by(LearnedWeightConfig.updated_at.desc()).first()

        if not weight_config:
            return None

        # Calculate confidence based on num_samples
        confidence = min(1.0, weight_config.num_samples / self.min_samples_for_confidence)

        return AdaptiveWeights(
            weights=weight_config.weights,
            confidence=confidence,
            num_samples=weight_config.num_samples,
            performance_metrics=weight_config.performance_metrics or {},
            learning_method=weight_config.learning_method,
            last_updated=weight_config.updated_at.isoformat()
        )

    def _persist_weights(
        self,
        context_id: int,
        weights: Dict[str, float],
        learning_method: str
    ):
        """Persist learned weights to database."""
        # Check if config exists
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).first()

        if weight_config:
            # Update existing
            weight_config.weights = weights
            weight_config.num_samples += 1
            weight_config.updated_at = datetime.utcnow()
        else:
            # Create new
            weight_config = LearnedWeightConfig(
                context_id=context_id,
                weights=weights,
                learning_method=learning_method,
                num_samples=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(weight_config)

        self.db.commit()

    def _get_agent_stats(self, context_id: int) -> Dict[str, Dict[str, float]]:
        """Get agent statistics for UCB."""
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).first()

        return weight_config.config_metadata.get("agent_stats", {}) if weight_config and weight_config.config_metadata else {}

    def _persist_agent_stats(self, context_id: int, stats: Dict[str, Dict[str, float]]):
        """Persist agent statistics for UCB."""
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).first()

        if weight_config:
            if not weight_config.config_metadata:
                weight_config.config_metadata = {}
            weight_config.config_metadata["agent_stats"] = stats
            self.db.commit()

    def _get_beta_params(self, context_id: int) -> Dict[str, Dict[str, float]]:
        """Get beta distribution parameters for Thompson sampling."""
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).first()

        return weight_config.config_metadata.get("beta_params", {}) if weight_config and weight_config.config_metadata else {}

    def _persist_beta_params(self, context_id: int, beta_params: Dict[str, Dict[str, float]]):
        """Persist beta parameters for Thompson sampling."""
        weight_config = self.db.query(LearnedWeightConfig).filter_by(
            context_id=context_id,
            is_active=True
        ).first()

        if weight_config:
            if not weight_config.config_metadata:
                weight_config.config_metadata = {}
            weight_config.config_metadata["beta_params"] = beta_params
            self.db.commit()


# Database model for learned weights
class LearnedWeightConfig(Base):
    """
    Stores learned agent weights per context (scenario/scenario_user/config).

    Supports:
    - Weight persistence across sessions
    - Rollback to previous configurations
    - A/B testing of weight strategies
    """
    __tablename__ = "learned_weight_configs"

    id = Column(Integer, primary_key=True, index=True)
    context_id = Column(Integer, nullable=False, index=True)  # Scenario ID, scenario_user ID, or config ID
    context_type = Column(String(20), nullable=False, default="scenario")  # scenario, scenario_user, config

    weights = Column(JSON, nullable=False)  # {"llm": 0.5, "gnn": 0.3, "trm": 0.2}
    learning_method = Column(String(20), nullable=False, index=True)  # ema, ucb, thompson, etc.
    num_samples = Column(Integer, nullable=False, default=0)  # Number of decisions used

    performance_metrics = Column(JSON, nullable=True)  # Per-agent performance
    config_metadata = Column(JSON, nullable=True)  # Algorithm-specific data (UCB stats, beta params, etc.)

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, index=True)


# Dependency injection
from fastapi import Depends
from app.db.session import get_db

def get_adaptive_weight_learner(
    db: Session = Depends(get_db),
    learning_method: LearningMethod = LearningMethod.EMA
) -> AdaptiveWeightLearner:
    """FastAPI dependency for AdaptiveWeightLearner."""
    return AdaptiveWeightLearner(db, learning_method=learning_method)

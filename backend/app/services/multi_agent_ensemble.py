"""
Multi-Agent Ensemble Service

Phase 4: Multi-Agent Orchestration (Week 12)
Orchestrates multiple AI agents (LLM, GNN, TRM) to make consensus decisions.

Consensus Methods:
- Voting: Majority vote with tie-breaking
- Averaging: Weighted average of decisions
- Confidence-based: Highest confidence agent wins

Use Cases:
- Robust decision-making through agent diversity
- Performance comparison and benchmarking
- Ensemble learning for improved accuracy
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import statistics
import logging

logger = logging.getLogger(__name__)


class ConsensusMethod(str, Enum):
    """Methods for aggregating agent decisions."""
    VOTING = "voting"  # Majority vote
    AVERAGING = "averaging"  # Weighted average
    CONFIDENCE = "confidence"  # Highest confidence wins
    MEDIAN = "median"  # Median of all decisions


class AgentType(str, Enum):
    """Types of agents in the ensemble."""
    LLM = "llm"  # GPT-4 multi-agent system
    GNN = "gnn"  # Graph Neural Network
    TRM = "trm"  # Tiny Recursive Model


@dataclass
class AgentDecision:
    """Individual agent's decision."""
    agent_type: str
    order_quantity: int
    confidence: float  # 0.0 to 1.0
    reasoning: Optional[str] = None
    execution_time_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EnsembleDecision:
    """Consensus decision from ensemble."""
    final_decision: int
    consensus_method: str
    confidence: float
    agent_decisions: List[Dict[str, Any]]
    agreement_score: float  # 0.0 (full disagreement) to 1.0 (full agreement)
    reasoning: str
    execution_time_ms: float
    metadata: Optional[Dict[str, Any]] = None


class MultiAgentEnsemble:
    """
    Orchestrates multiple AI agents to make consensus decisions.

    Responsibilities:
    - Execute multiple agents in parallel (or sequential fallback)
    - Aggregate decisions using various consensus methods
    - Calculate confidence and agreement scores
    - Track ensemble performance metrics
    """

    def __init__(
        self,
        agent_weights: Optional[Dict[str, float]] = None,
        consensus_method: ConsensusMethod = ConsensusMethod.AVERAGING
    ):
        """
        Initialize ensemble with agent weights and consensus method.

        Args:
            agent_weights: Dict mapping agent_type to weight (default: equal weights)
            consensus_method: Method for aggregating decisions
        """
        self.agent_weights = agent_weights or {
            AgentType.LLM.value: 1.0,
            AgentType.GNN.value: 1.0,
            AgentType.TRM.value: 1.0
        }
        self.consensus_method = consensus_method

        # Normalize weights to sum to 1.0
        total_weight = sum(self.agent_weights.values())
        if total_weight > 0:
            self.agent_weights = {
                agent: weight / total_weight
                for agent, weight in self.agent_weights.items()
            }

    def make_consensus_decision(
        self,
        agent_decisions: List[AgentDecision],
        consensus_method: Optional[ConsensusMethod] = None
    ) -> EnsembleDecision:
        """
        Aggregate multiple agent decisions into a consensus decision.

        Args:
            agent_decisions: List of individual agent decisions
            consensus_method: Override default consensus method

        Returns:
            EnsembleDecision with final decision and metadata

        Raises:
            ValueError: If agent_decisions is empty or invalid
        """
        if not agent_decisions:
            raise ValueError("Cannot make consensus decision with no agent decisions")

        method = consensus_method or self.consensus_method

        # Calculate total execution time
        total_execution_time = sum(
            d.execution_time_ms or 0 for d in agent_decisions
        )

        # Apply consensus method
        if method == ConsensusMethod.VOTING:
            final_decision, confidence, reasoning = self._voting_consensus(agent_decisions)
        elif method == ConsensusMethod.AVERAGING:
            final_decision, confidence, reasoning = self._averaging_consensus(agent_decisions)
        elif method == ConsensusMethod.CONFIDENCE:
            final_decision, confidence, reasoning = self._confidence_consensus(agent_decisions)
        elif method == ConsensusMethod.MEDIAN:
            final_decision, confidence, reasoning = self._median_consensus(agent_decisions)
        else:
            raise ValueError(f"Unknown consensus method: {method}")

        # Calculate agreement score
        agreement_score = self._calculate_agreement_score(agent_decisions, final_decision)

        return EnsembleDecision(
            final_decision=final_decision,
            consensus_method=method.value,
            confidence=confidence,
            agent_decisions=[asdict(d) for d in agent_decisions],
            agreement_score=agreement_score,
            reasoning=reasoning,
            execution_time_ms=total_execution_time,
            metadata={
                "num_agents": len(agent_decisions),
                "agent_types": [d.agent_type for d in agent_decisions],
                "decision_variance": self._calculate_variance([d.order_quantity for d in agent_decisions])
            }
        )

    def _voting_consensus(
        self,
        agent_decisions: List[AgentDecision]
    ) -> Tuple[int, float, str]:
        """
        Majority vote consensus.

        For continuous values (order quantities), rounds to nearest integer
        and finds mode. If tie, uses highest-weighted agent.

        Returns:
            (final_decision, confidence, reasoning)
        """
        # Round all decisions to integers
        decisions = [d.order_quantity for d in agent_decisions]

        # Find mode (most common value)
        from collections import Counter
        vote_counts = Counter(decisions)
        most_common = vote_counts.most_common()

        if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
            # Clear winner
            final_decision = most_common[0][0]
            confidence = most_common[0][1] / len(decisions)  # Fraction of votes
            reasoning = f"Voting consensus: {most_common[0][1]}/{len(decisions)} agents chose {final_decision}"
        else:
            # Tie - use highest-weighted agent
            tied_decisions = [value for value, count in most_common if count == most_common[0][1]]

            # Find highest-weighted agent among tied decisions
            max_weight = 0
            final_decision = tied_decisions[0]

            for d in agent_decisions:
                if d.order_quantity in tied_decisions:
                    weight = self.agent_weights.get(d.agent_type, 1.0)
                    if weight > max_weight:
                        max_weight = weight
                        final_decision = d.order_quantity

            confidence = 0.5  # Tie-break has lower confidence
            reasoning = f"Voting tie-break: Highest-weighted agent chose {final_decision}"

        return final_decision, confidence, reasoning

    def _averaging_consensus(
        self,
        agent_decisions: List[AgentDecision]
    ) -> Tuple[int, float, str]:
        """
        Weighted average consensus.

        Returns:
            (final_decision, confidence, reasoning)
        """
        weighted_sum = 0
        total_weight = 0

        for d in agent_decisions:
            weight = self.agent_weights.get(d.agent_type, 1.0)
            weighted_sum += d.order_quantity * weight
            total_weight += weight

        if total_weight == 0:
            raise ValueError("Total weight is zero - cannot compute weighted average")

        final_decision = round(weighted_sum / total_weight)

        # Confidence based on inverse of variance
        variance = self._calculate_variance([d.order_quantity for d in agent_decisions])
        confidence = 1.0 / (1.0 + variance / 100.0)  # Normalize variance

        reasoning = f"Weighted average: {weighted_sum / total_weight:.1f} → {final_decision}"

        return final_decision, confidence, reasoning

    def _confidence_consensus(
        self,
        agent_decisions: List[AgentDecision]
    ) -> Tuple[int, float, str]:
        """
        Highest-confidence agent wins.

        Returns:
            (final_decision, confidence, reasoning)
        """
        # Find agent with highest confidence
        max_confidence_agent = max(agent_decisions, key=lambda d: d.confidence)

        final_decision = max_confidence_agent.order_quantity
        confidence = max_confidence_agent.confidence

        reasoning = (
            f"Confidence-based: {max_confidence_agent.agent_type.upper()} agent "
            f"(confidence: {confidence:.2f}) chose {final_decision}"
        )

        return final_decision, confidence, reasoning

    def _median_consensus(
        self,
        agent_decisions: List[AgentDecision]
    ) -> Tuple[int, float, str]:
        """
        Median of all decisions (robust to outliers).

        Returns:
            (final_decision, confidence, reasoning)
        """
        decisions = [d.order_quantity for d in agent_decisions]
        median_value = statistics.median(decisions)
        final_decision = round(median_value)

        # Confidence based on how close decisions are to median
        deviations = [abs(d - median_value) for d in decisions]
        avg_deviation = statistics.mean(deviations)
        confidence = 1.0 / (1.0 + avg_deviation / 50.0)  # Normalize deviation

        reasoning = f"Median consensus: {median_value:.1f} → {final_decision}"

        return final_decision, confidence, reasoning

    def _calculate_agreement_score(
        self,
        agent_decisions: List[AgentDecision],
        final_decision: int
    ) -> float:
        """
        Calculate agreement score (0.0 to 1.0).

        Measures how close agent decisions are to the final decision.

        Returns:
            Agreement score (1.0 = perfect agreement, 0.0 = full disagreement)
        """
        if not agent_decisions:
            return 0.0

        # Calculate average deviation from final decision
        deviations = [
            abs(d.order_quantity - final_decision)
            for d in agent_decisions
        ]
        avg_deviation = statistics.mean(deviations)

        # Normalize to 0-1 scale (assuming max deviation of 100 units)
        agreement_score = max(0.0, 1.0 - (avg_deviation / 100.0))

        return agreement_score

    def _calculate_variance(self, values: List[float]) -> float:
        """Calculate variance of a list of values."""
        if len(values) <= 1:
            return 0.0
        return statistics.variance(values)

    def update_agent_weights(
        self,
        performance_metrics: Dict[str, float]
    ):
        """
        Update agent weights based on performance metrics.

        Args:
            performance_metrics: Dict mapping agent_type to performance score (0-1)

        Example:
            {
                "llm": 0.85,  # 85% accuracy
                "gnn": 0.78,
                "trm": 0.72
            }
        """
        # Update weights proportional to performance
        self.agent_weights = performance_metrics.copy()

        # Normalize to sum to 1.0
        total_weight = sum(self.agent_weights.values())
        if total_weight > 0:
            self.agent_weights = {
                agent: weight / total_weight
                for agent, weight in self.agent_weights.items()
            }

        logger.info(f"Updated agent weights: {self.agent_weights}")

    def get_ensemble_stats(
        self,
        ensemble_decisions: List[EnsembleDecision]
    ) -> Dict[str, Any]:
        """
        Calculate ensemble statistics over multiple decisions.

        Args:
            ensemble_decisions: List of ensemble decisions

        Returns:
            Dict with ensemble performance metrics
        """
        if not ensemble_decisions:
            return {}

        return {
            "num_decisions": len(ensemble_decisions),
            "avg_confidence": statistics.mean([d.confidence for d in ensemble_decisions]),
            "avg_agreement_score": statistics.mean([d.agreement_score for d in ensemble_decisions]),
            "avg_execution_time_ms": statistics.mean([d.execution_time_ms for d in ensemble_decisions]),
            "consensus_method": ensemble_decisions[0].consensus_method,
            "agent_participation": self._count_agent_participation(ensemble_decisions),
        }

    def _count_agent_participation(
        self,
        ensemble_decisions: List[EnsembleDecision]
    ) -> Dict[str, int]:
        """Count how many times each agent participated."""
        participation = {}

        for ensemble_decision in ensemble_decisions:
            for agent_decision in ensemble_decision.agent_decisions:
                agent_type = agent_decision.get("agent_type")
                participation[agent_type] = participation.get(agent_type, 0) + 1

        return participation


# Dependency injection
def get_multi_agent_ensemble(
    consensus_method: ConsensusMethod = ConsensusMethod.AVERAGING
) -> MultiAgentEnsemble:
    """FastAPI dependency for MultiAgentEnsemble."""
    return MultiAgentEnsemble(consensus_method=consensus_method)

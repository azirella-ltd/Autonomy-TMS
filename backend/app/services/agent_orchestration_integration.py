"""
Agent Orchestration Integration Service

Phase 4: Multi-Agent Orchestration - Integration Layer
Ties together all Phase 4 services into game round processing:
- Multi-agent consensus decision-making
- Performance tracking per round
- Adaptive weight learning
- RLHF data collection

This service is called during game round processing to:
1. Gather agent decisions using current weights
2. Make ensemble consensus decision
3. Track performance metrics
4. Update weights based on performance
5. Record RLHF feedback if in copilot mode
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from dataclasses import asdict
import logging
import time

from app.services.multi_agent_ensemble import (
    MultiAgentEnsemble,
    AgentDecision,
    ConsensusMethod
)
from app.services.adaptive_weight_learner import (
    AdaptiveWeightLearner,
    LearningMethod
)
from app.services.agent_performance_tracker import (
    AgentPerformanceTracker,
    PerformanceMetrics
)
from app.services.rlhf_data_collector import (
    RLHFDataCollector,
    FeedbackAction
)
from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
Game = Scenario

logger = logging.getLogger(__name__)


class AgentOrchestrationIntegration:
    """
    Integration layer for Phase 4 multi-agent orchestration.

    Coordinates:
    - Ensemble decision-making with learned weights
    - Performance tracking after each decision
    - Weight adaptation based on outcomes
    - RLHF data collection from human overrides
    """

    def __init__(self, db: Session):
        self.db = db
        self.ensemble = None
        self.learner = None
        self.tracker = None
        self.rlhf_collector = None

    def initialize_for_game(
        self,
        scenario_id: int,
        consensus_method: ConsensusMethod = ConsensusMethod.AVERAGING,
        learning_method: LearningMethod = LearningMethod.EMA,
        learning_rate: float = 0.1
    ):
        """
        Initialize orchestration services for a game.

        Args:
            scenario_id: Game ID to initialize for
            consensus_method: Ensemble consensus method
            learning_method: Weight learning algorithm
            learning_rate: Learning rate for adaptive learning
        """
        # Initialize learner
        self.learner = AdaptiveWeightLearner(
            db=self.db,
            learning_method=learning_method,
            learning_rate=learning_rate
        )

        # Get learned weights or use defaults
        adaptive_weights = self.learner.get_learned_weights(context_id=scenario_id)
        if adaptive_weights:
            agent_weights = adaptive_weights.weights
            logger.info(f"Loaded learned weights for game {scenario_id}: {agent_weights}")
        else:
            agent_weights = {"llm": 1.0/3, "gnn": 1.0/3, "trm": 1.0/3}
            logger.info(f"Using default equal weights for game {scenario_id}")

        # Initialize ensemble with learned weights
        self.ensemble = MultiAgentEnsemble(
            agent_weights=agent_weights,
            consensus_method=consensus_method
        )

        # Initialize tracker and RLHF collector
        self.tracker = AgentPerformanceTracker(self.db)
        self.rlhf_collector = RLHFDataCollector(self.db)

    def make_ensemble_decision(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        agent_decisions: List[Dict[str, Any]],
        game_state: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Make ensemble consensus decision and record metadata.

        Args:
            scenario_user: ScenarioUser making decision
            game: Game context
            agent_decisions: List of agent decision dicts
            game_state: Current game state context

        Returns:
            (final_decision, ensemble_metadata)
        """
        # Convert dict decisions to AgentDecision objects
        agent_decision_objs = []
        for decision_dict in agent_decisions:
            agent_decision_objs.append(
                AgentDecision(
                    agent_type=decision_dict.get("agent_type", "unknown"),
                    order_quantity=decision_dict.get("order_quantity", 0),
                    confidence=decision_dict.get("confidence", 0.5),
                    reasoning=decision_dict.get("reasoning"),
                    execution_time_ms=decision_dict.get("execution_time_ms")
                )
            )

        # Make consensus decision
        start_time = time.time()
        ensemble_result = self.ensemble.make_consensus_decision(agent_decision_objs)
        execution_time = (time.time() - start_time) * 1000  # ms

        # Prepare metadata
        metadata = {
            "final_decision": ensemble_result.final_decision,
            "consensus_method": ensemble_result.consensus_method,
            "confidence": ensemble_result.confidence,
            "agreement_score": ensemble_result.agreement_score,
            "agent_decisions": ensemble_result.agent_decisions,
            "reasoning": ensemble_result.reasoning,
            "execution_time_ms": execution_time,
            "current_weights": self.ensemble.agent_weights
        }

        logger.info(
            f"Ensemble decision for scenario_user {scenario_user.id} in game {game.id}: "
            f"decision={ensemble_result.final_decision}, "
            f"confidence={ensemble_result.confidence:.2f}, "
            f"agreement={ensemble_result.agreement_score:.2f}"
        )

        return ensemble_result.final_decision, metadata

    def record_performance_and_learn(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        round_number: int,
        agent_type: str,
        decision: int,
        outcome_metrics: Dict[str, float]
    ):
        """
        Record agent performance and update weights via learning.

        Args:
            scenario_user: ScenarioUser who made decision
            game: Game context
            round_number: Round number
            agent_type: Agent type that made decision (llm, gnn, trm, ensemble)
            decision: Order quantity decided
            outcome_metrics: Performance metrics (cost, service_level, inventory, etc.)
        """
        # Extract metrics
        total_cost = outcome_metrics.get("total_cost", 0.0)
        holding_cost = outcome_metrics.get("holding_cost", 0.0)
        shortage_cost = outcome_metrics.get("shortage_cost", 0.0)
        service_level = outcome_metrics.get("service_level", 1.0)
        stockout_count = outcome_metrics.get("stockout_count", 0)
        backlog = outcome_metrics.get("backlog", 0)
        avg_inventory = outcome_metrics.get("avg_inventory", 0.0)
        inventory_variance = outcome_metrics.get("inventory_variance", 0.0)

        # Record performance
        performance_metrics = PerformanceMetrics(
            scenario_user_id=scenario_user.id,
            scenario_id=game.id,
            round_number=round_number,
            agent_type=agent_type,
            agent_mode=scenario_user.agent_mode or "manual",
            total_cost=total_cost,
            holding_cost=holding_cost,
            shortage_cost=shortage_cost,
            service_level=service_level,
            stockout_count=stockout_count,
            backlog=backlog,
            avg_inventory=avg_inventory,
            inventory_variance=inventory_variance,
            order_quantity=decision
        )

        self.tracker.record_performance(performance_metrics)

        # Calculate performance score (0-1, higher = better)
        # Simple heuristic: inverse of normalized cost + service level
        max_cost = 10000  # Normalize cost to this max
        normalized_cost = min(total_cost / max_cost, 1.0)
        performance_score = (1.0 - normalized_cost) * 0.5 + service_level * 0.5

        # Learn weights if adaptive learning enabled
        if self.learner and agent_type in ["llm", "gnn", "trm"]:
            current_weights = self.ensemble.agent_weights
            new_weights = self.learner.learn_weights(
                agent_type=agent_type,
                performance_score=performance_score,
                current_weights=current_weights,
                context_id=game.id
            )

            # Update ensemble weights
            self.ensemble.agent_weights = new_weights

            logger.info(
                f"Updated weights after round {round_number}: {new_weights}, "
                f"performance_score={performance_score:.3f}"
            )

    def record_copilot_feedback(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        round_number: int,
        agent_type: str,
        game_state: Dict[str, Any],
        ai_suggestion: int,
        human_decision: int,
        ai_reasoning: Optional[str] = None,
        ai_confidence: Optional[float] = None
    ) -> int:
        """
        Record RLHF feedback when human overrides AI suggestion in copilot mode.

        Args:
            scenario_user: ScenarioUser who made decision
            game: Game context
            round_number: Round number
            agent_type: AI agent type (llm, gnn, trm)
            game_state: Current game state
            ai_suggestion: What AI recommended
            human_decision: What human actually chose
            ai_reasoning: AI's explanation
            ai_confidence: AI's confidence score

        Returns:
            Feedback record ID
        """
        feedback_id = self.rlhf_collector.record_feedback(
            scenario_user_id=scenario_user.id,
            scenario_id=game.id,
            round_number=round_number,
            agent_type=agent_type,
            game_state=game_state,
            ai_suggestion=ai_suggestion,
            human_decision=human_decision,
            ai_reasoning=ai_reasoning,
            ai_confidence=ai_confidence
        )

        logger.info(
            f"Recorded RLHF feedback for scenario_user {scenario_user.id} round {round_number}: "
            f"ai_suggested={ai_suggestion}, human_chose={human_decision}, "
            f"feedback_id={feedback_id}"
        )

        return feedback_id

    def update_feedback_outcomes(
        self,
        feedback_id: int,
        ai_outcome: Dict[str, float],
        human_outcome: Dict[str, float]
    ):
        """
        Update RLHF feedback with actual outcomes after round completes.

        Args:
            feedback_id: Feedback record ID
            ai_outcome: Metrics if AI suggestion was used
            human_outcome: Metrics from human decision
        """
        self.rlhf_collector.update_preference_label(
            feedback_id=feedback_id,
            ai_outcome=ai_outcome,
            human_outcome=human_outcome
        )

        logger.info(
            f"Updated preference label for feedback {feedback_id}: "
            f"ai_cost={ai_outcome.get('total_cost')}, "
            f"human_cost={human_outcome.get('total_cost')}"
        )

    def get_ensemble_summary(self, scenario_id: int) -> Dict[str, Any]:
        """
        Get summary of ensemble performance for a game.

        Args:
            scenario_id: Game ID

        Returns:
            Dict with ensemble statistics
        """
        # Get current weights
        adaptive_weights = self.learner.get_learned_weights(context_id=scenario_id) if self.learner else None

        # Get performance summary
        summary = {
            "scenario_id": scenario_id,
            "current_weights": adaptive_weights.weights if adaptive_weights else {},
            "confidence": adaptive_weights.confidence if adaptive_weights else 0.0,
            "num_samples": adaptive_weights.num_samples if adaptive_weights else 0,
            "performance_metrics": adaptive_weights.performance_metrics if adaptive_weights else {},
            "learning_method": adaptive_weights.learning_method if adaptive_weights else "default",
        }

        # Get performance comparison if tracker initialized
        if self.tracker:
            try:
                # Get agent-level performance summaries
                for agent_type in ["llm", "gnn", "trm"]:
                    perf_summary = self.tracker.get_agent_performance_summary(
                        scenario_id=scenario_id,
                        agent_type=agent_type,
                        min_rounds=5
                    )
                    if not perf_summary.get("insufficient_data"):
                        summary[f"{agent_type}_performance"] = perf_summary
            except Exception as e:
                logger.warning(f"Could not get performance comparison: {e}")

        return summary

    def get_weight_history(self, scenario_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history of weight changes over time.

        Args:
            scenario_id: Game ID
            limit: Max records to return

        Returns:
            List of weight snapshots with timestamps
        """
        # Query learned_weight_configs ordered by updated_at
        from app.services.adaptive_weight_learner import LearnedWeightConfig

        configs = self.db.query(LearnedWeightConfig).filter_by(
            context_id=scenario_id,
            is_active=True
        ).order_by(LearnedWeightConfig.updated_at.desc()).limit(limit).all()

        history = []
        for config in reversed(configs):  # Oldest first
            history.append({
                "weights": config.weights,
                "num_samples": config.num_samples,
                "learning_method": config.learning_method,
                "timestamp": config.updated_at.isoformat(),
                "performance_metrics": config.performance_metrics
            })

        return history


# Dependency injection
from fastapi import Depends
from app.db.session import get_db

def get_agent_orchestration_integration(db: Session = Depends(get_db)) -> AgentOrchestrationIntegration:
    """FastAPI dependency for AgentOrchestrationIntegration."""
    return AgentOrchestrationIntegration(db)

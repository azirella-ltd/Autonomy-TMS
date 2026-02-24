"""
RLHF (Reinforcement Learning from Human Feedback) Data Collector

Phase 4: Multi-Agent Orchestration (Week 14)
Collects training data from human overrides of AI decisions for continuous learning.

Data Collection:
- AI recommendations (context + suggestion)
- Human decisions (accept, modify, reject)
- Game outcomes (reward signal)
- Preference labels (human decision better/worse than AI)

Use Cases:
- Fine-tuning TRM/GNN agents with human preferences
- Identifying failure modes and edge cases
- Improving copilot mode suggestions
- Personalizing agent behavior per user
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, Boolean, ForeignKey, Text
from enum import Enum
import logging

from app.models.base import Base

logger = logging.getLogger(__name__)


class FeedbackAction(str, Enum):
    """Human action on AI recommendation."""
    ACCEPTED = "accepted"  # Used AI suggestion as-is
    MODIFIED = "modified"  # Changed AI suggestion
    REJECTED = "rejected"  # Ignored AI suggestion entirely
    OVERRIDDEN = "overridden"  # Switched from autonomous to manual


class PreferenceLabel(str, Enum):
    """Preference label for training."""
    HUMAN_BETTER = "human_better"  # Human decision outperformed AI
    AI_BETTER = "ai_better"  # AI suggestion was better
    EQUIVALENT = "equivalent"  # Both performed similarly
    UNKNOWN = "unknown"  # Outcome not yet determined


@dataclass
class RLHFTrainingExample:
    """Single training example for RLHF fine-tuning."""
    # Required fields (no defaults) - must come first
    # Context (input features)
    game_state: Dict[str, Any]  # Inventory, backlog, pipeline, demand history
    player_role: str  # Retailer, wholesaler, distributor, manufacturer
    round_number: int

    # AI recommendation
    ai_suggestion: int

    # Human decision
    human_decision: int
    feedback_action: str  # accepted, modified, rejected, overridden

    # Metadata (required)
    player_id: int
    scenario_id: int
    agent_type: str  # llm, gnn, trm
    timestamp: str

    # Optional fields (have defaults) - must come last
    ai_reasoning: Optional[str] = None
    ai_confidence: Optional[float] = None

    # Outcome (reward signal)
    ai_outcome: Optional[Dict[str, float]] = None  # Cost, service level if AI was used
    human_outcome: Optional[Dict[str, float]] = None  # Cost, service level from human decision
    preference_label: Optional[str] = None  # human_better, ai_better, equivalent


@dataclass
class FeedbackSession:
    """Aggregate feedback from a gameplay session."""
    player_id: int
    scenario_id: int
    num_decisions: int
    num_accepted: int
    num_modified: int
    num_rejected: int
    acceptance_rate: float
    avg_modification_delta: Optional[float] = None
    performance_improvement: Optional[float] = None


class RLHFDataCollector:
    """
    Collects training data from human feedback for RLHF fine-tuning.

    Responsibilities:
    - Record AI suggestions and human responses
    - Calculate reward signals (outcome comparison)
    - Generate preference labels
    - Export training datasets
    - Track feedback patterns
    """

    def __init__(self, db: Session):
        self.db = db

    def record_feedback(
        self,
        player_id: int,
        scenario_id: int,
        round_number: int,
        agent_type: str,
        game_state: Dict[str, Any],
        ai_suggestion: int,
        human_decision: int,
        ai_reasoning: Optional[str] = None,
        ai_confidence: Optional[float] = None
    ) -> int:
        """
        Record human feedback on AI recommendation.

        Args:
            player_id: Player who made decision
            scenario_id: Game context
            round_number: Round number
            agent_type: Type of AI agent (llm, gnn, trm)
            game_state: Current game state (inventory, backlog, etc.)
            ai_suggestion: AI's recommended order quantity
            human_decision: Human's actual order quantity
            ai_reasoning: AI's explanation (optional)
            ai_confidence: AI's confidence score (optional)

        Returns:
            ID of created feedback record
        """
        # Determine feedback action
        feedback_action = self._classify_feedback_action(ai_suggestion, human_decision)

        # Create feedback record
        feedback = RLHFFeedback(
            player_id=player_id,
            scenario_id=scenario_id,
            round_number=round_number,
            agent_type=agent_type,
            game_state=game_state,
            ai_suggestion=ai_suggestion,
            ai_reasoning=ai_reasoning,
            ai_confidence=ai_confidence,
            human_decision=human_decision,
            feedback_action=feedback_action.value,
            modification_delta=abs(human_decision - ai_suggestion) if feedback_action == FeedbackAction.MODIFIED else None,
            timestamp=datetime.utcnow(),
            preference_label=PreferenceLabel.UNKNOWN.value  # Will be updated after round completes
        )

        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)

        logger.info(
            f"Recorded RLHF feedback: player={player_id}, round={round_number}, "
            f"ai_suggestion={ai_suggestion}, human_decision={human_decision}, "
            f"action={feedback_action.value}"
        )

        return feedback.id

    def update_preference_label(
        self,
        feedback_id: int,
        ai_outcome: Dict[str, float],
        human_outcome: Dict[str, float]
    ):
        """
        Update preference label after round completes and outcomes are known.

        Args:
            feedback_id: Feedback record ID
            ai_outcome: Metrics if AI suggestion was used (cost, service level)
            human_outcome: Metrics from human decision (cost, service level)
        """
        feedback = self.db.query(RLHFFeedback).filter_by(id=feedback_id).first()
        if not feedback:
            logger.warning(f"Feedback record {feedback_id} not found")
            return

        # Determine preference based on outcomes
        preference_label = self._calculate_preference_label(ai_outcome, human_outcome)

        # Update record
        feedback.ai_outcome = ai_outcome
        feedback.human_outcome = human_outcome
        feedback.preference_label = preference_label.value

        self.db.commit()

        logger.info(
            f"Updated preference label for feedback {feedback_id}: {preference_label.value}"
        )

    def get_training_examples(
        self,
        agent_type: Optional[str] = None,
        preference_label: Optional[PreferenceLabel] = None,
        min_confidence: float = 0.0,
        limit: int = 1000
    ) -> List[RLHFTrainingExample]:
        """
        Get training examples for RLHF fine-tuning.

        Args:
            agent_type: Filter by agent type (llm, gnn, trm)
            preference_label: Filter by preference (human_better, ai_better)
            min_confidence: Minimum AI confidence threshold
            limit: Maximum examples to return

        Returns:
            List of training examples
        """
        query = self.db.query(RLHFFeedback).filter(
            RLHFFeedback.preference_label != PreferenceLabel.UNKNOWN.value
        )

        if agent_type:
            query = query.filter_by(agent_type=agent_type)

        if preference_label:
            query = query.filter_by(preference_label=preference_label.value)

        if min_confidence > 0:
            query = query.filter(RLHFFeedback.ai_confidence >= min_confidence)

        query = query.order_by(RLHFFeedback.timestamp.desc()).limit(limit)

        feedbacks = query.all()

        return [
            RLHFTrainingExample(
                game_state=feedback.game_state,
                player_role=feedback.game_state.get("role", "unknown"),
                round_number=feedback.round_number,
                ai_suggestion=feedback.ai_suggestion,
                ai_reasoning=feedback.ai_reasoning,
                ai_confidence=feedback.ai_confidence,
                human_decision=feedback.human_decision,
                feedback_action=feedback.feedback_action,
                ai_outcome=feedback.ai_outcome,
                human_outcome=feedback.human_outcome,
                preference_label=feedback.preference_label,
                player_id=feedback.player_id,
                scenario_id=feedback.scenario_id,
                agent_type=feedback.agent_type,
                timestamp=feedback.timestamp.isoformat()
            )
            for feedback in feedbacks
        ]

    def get_feedback_session_summary(
        self,
        player_id: int,
        scenario_id: int
    ) -> FeedbackSession:
        """
        Get aggregate feedback summary for a player's game session.

        Args:
            player_id: Player ID
            scenario_id: Game ID

        Returns:
            FeedbackSession with aggregate metrics
        """
        feedbacks = self.db.query(RLHFFeedback).filter_by(
            player_id=player_id,
            scenario_id=scenario_id
        ).all()

        if not feedbacks:
            return FeedbackSession(
                player_id=player_id,
                scenario_id=scenario_id,
                num_decisions=0,
                num_accepted=0,
                num_modified=0,
                num_rejected=0,
                acceptance_rate=0.0
            )

        num_decisions = len(feedbacks)
        num_accepted = sum(1 for f in feedbacks if f.feedback_action == FeedbackAction.ACCEPTED.value)
        num_modified = sum(1 for f in feedbacks if f.feedback_action == FeedbackAction.MODIFIED.value)
        num_rejected = sum(1 for f in feedbacks if f.feedback_action == FeedbackAction.REJECTED.value)

        acceptance_rate = num_accepted / num_decisions if num_decisions > 0 else 0.0

        # Calculate average modification delta
        modifications = [f.modification_delta for f in feedbacks if f.modification_delta is not None]
        avg_modification_delta = sum(modifications) / len(modifications) if modifications else None

        # Calculate performance improvement (human vs AI)
        improvements = []
        for f in feedbacks:
            if f.ai_outcome and f.human_outcome:
                ai_cost = f.ai_outcome.get("total_cost", 0)
                human_cost = f.human_outcome.get("total_cost", 0)
                if ai_cost > 0:
                    improvement = (ai_cost - human_cost) / ai_cost * 100
                    improvements.append(improvement)

        performance_improvement = sum(improvements) / len(improvements) if improvements else None

        return FeedbackSession(
            player_id=player_id,
            scenario_id=scenario_id,
            num_decisions=num_decisions,
            num_accepted=num_accepted,
            num_modified=num_modified,
            num_rejected=num_rejected,
            acceptance_rate=acceptance_rate,
            avg_modification_delta=avg_modification_delta,
            performance_improvement=performance_improvement
        )

    def export_training_dataset(
        self,
        agent_type: str,
        output_format: str = "json"
    ) -> List[Dict[str, Any]]:
        """
        Export training dataset for offline fine-tuning.

        Args:
            agent_type: Agent type to export data for (gnn, trm)
            output_format: Format (json, csv, tfrecord)

        Returns:
            List of training examples as dicts
        """
        examples = self.get_training_examples(
            agent_type=agent_type,
            preference_label=PreferenceLabel.HUMAN_BETTER,  # Focus on human improvements
            limit=10000
        )

        if output_format == "json":
            return [asdict(example) for example in examples]
        else:
            raise NotImplementedError(f"Format {output_format} not yet implemented")

    def get_failure_modes(
        self,
        agent_type: str,
        min_occurrences: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Identify common failure modes (patterns where AI consistently fails).

        Args:
            agent_type: Agent type to analyze
            min_occurrences: Minimum occurrences to consider pattern

        Returns:
            List of failure mode patterns
        """
        # Get all human_better examples
        feedbacks = self.db.query(RLHFFeedback).filter_by(
            agent_type=agent_type,
            preference_label=PreferenceLabel.HUMAN_BETTER.value
        ).all()

        # Group by game state patterns (simplified - real implementation would cluster)
        failure_patterns = {}

        for feedback in feedbacks:
            # Create pattern key based on game state
            inventory = feedback.game_state.get("inventory", 0)
            backlog = feedback.game_state.get("backlog", 0)

            # Discretize into buckets
            inv_bucket = "low" if inventory < 50 else "medium" if inventory < 150 else "high"
            backlog_bucket = "low" if backlog < 10 else "medium" if backlog < 50 else "high"

            pattern_key = f"{inv_bucket}_inventory_{backlog_bucket}_backlog"

            if pattern_key not in failure_patterns:
                failure_patterns[pattern_key] = {
                    "pattern": pattern_key,
                    "occurrences": 0,
                    "avg_ai_suggestion": 0,
                    "avg_human_decision": 0,
                    "avg_improvement": 0
                }

            pattern = failure_patterns[pattern_key]
            pattern["occurrences"] += 1
            pattern["avg_ai_suggestion"] += feedback.ai_suggestion
            pattern["avg_human_decision"] += feedback.human_decision

            if feedback.ai_outcome and feedback.human_outcome:
                ai_cost = feedback.ai_outcome.get("total_cost", 0)
                human_cost = feedback.human_outcome.get("total_cost", 0)
                if ai_cost > 0:
                    improvement = (ai_cost - human_cost) / ai_cost * 100
                    pattern["avg_improvement"] += improvement

        # Filter by min_occurrences and calculate averages
        failure_modes = []
        for pattern_key, pattern in failure_patterns.items():
            if pattern["occurrences"] >= min_occurrences:
                count = pattern["occurrences"]
                pattern["avg_ai_suggestion"] /= count
                pattern["avg_human_decision"] /= count
                pattern["avg_improvement"] /= count
                failure_modes.append(pattern)

        # Sort by frequency
        failure_modes.sort(key=lambda x: x["occurrences"], reverse=True)

        return failure_modes

    def _classify_feedback_action(
        self,
        ai_suggestion: int,
        human_decision: int
    ) -> FeedbackAction:
        """Classify human action on AI suggestion."""
        if ai_suggestion == human_decision:
            return FeedbackAction.ACCEPTED
        elif abs(ai_suggestion - human_decision) <= 5:  # Small modification
            return FeedbackAction.MODIFIED
        else:
            return FeedbackAction.REJECTED

    def _calculate_preference_label(
        self,
        ai_outcome: Dict[str, float],
        human_outcome: Dict[str, float]
    ) -> PreferenceLabel:
        """
        Calculate preference label based on outcomes.

        Compares total cost and service level to determine which was better.
        """
        ai_cost = ai_outcome.get("total_cost", float('inf'))
        human_cost = human_outcome.get("total_cost", float('inf'))

        ai_service = ai_outcome.get("service_level", 0.0)
        human_service = human_outcome.get("service_level", 0.0)

        # Calculate relative differences
        cost_diff_pct = abs(ai_cost - human_cost) / max(ai_cost, human_cost) * 100 if max(ai_cost, human_cost) > 0 else 0
        service_diff_pct = abs(ai_service - human_service) * 100

        # Significant difference threshold
        SIGNIFICANT_THRESHOLD = 5  # 5% difference

        if cost_diff_pct < SIGNIFICANT_THRESHOLD and service_diff_pct < SIGNIFICANT_THRESHOLD:
            return PreferenceLabel.EQUIVALENT

        # Calculate composite score (lower cost + higher service = better)
        ai_score = -ai_cost + (ai_service * 1000)
        human_score = -human_cost + (human_service * 1000)

        if human_score > ai_score:
            return PreferenceLabel.HUMAN_BETTER
        else:
            return PreferenceLabel.AI_BETTER


# Database model for RLHF feedback
class RLHFFeedback(Base):
    """
    Stores human feedback on AI recommendations for RLHF training.

    Each record captures:
    - Context: Game state when decision was made
    - AI recommendation: What AI suggested
    - Human decision: What human actually chose
    - Outcomes: Performance comparison
    - Preference: Which was better (human or AI)
    """
    __tablename__ = "rlhf_feedback"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    scenario_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)

    agent_type = Column(String(20), nullable=False, index=True)  # llm, gnn, trm

    # Context (game state)
    game_state = Column(JSON, nullable=False)  # Inventory, backlog, pipeline, demand history

    # AI recommendation
    ai_suggestion = Column(Integer, nullable=False)
    ai_reasoning = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)

    # Human decision
    human_decision = Column(Integer, nullable=False)
    feedback_action = Column(String(20), nullable=False, index=True)  # accepted, modified, rejected
    modification_delta = Column(Integer, nullable=True)  # Abs difference if modified

    # Outcomes (filled after round completes)
    ai_outcome = Column(JSON, nullable=True)  # {total_cost, service_level}
    human_outcome = Column(JSON, nullable=True)
    preference_label = Column(String(20), nullable=False, default="unknown", index=True)  # human_better, ai_better, equivalent

    timestamp = Column(DateTime, nullable=False, index=True)


# Dependency injection
def get_rlhf_data_collector(db: Session) -> RLHFDataCollector:
    """FastAPI dependency for RLHFDataCollector."""
    return RLHFDataCollector(db)

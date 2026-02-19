"""
Pattern Analysis Service
Phase 7 Sprint 4 - Feature 2

Tracks suggestion outcomes, detects player patterns, and measures AI effectiveness.
Provides insights into player behavior and AI recommendation quality.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
import statistics

from app.models.scenario import Scenario
from app.models.participant import Participant

# Aliases for backwards compatibility
Game = Scenario
Player = Participant

logger = logging.getLogger(__name__)


class PatternAnalysisService:
    """Service for analyzing player patterns and AI suggestion outcomes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_suggestion_outcome(
        self,
        suggestion_id: int,
        accepted: bool,
        actual_order_placed: int,
        modified_quantity: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Track the outcome of an AI suggestion.

        Args:
            suggestion_id: ID of the suggestion
            accepted: Whether player accepted the suggestion
            actual_order_placed: The actual order quantity placed
            modified_quantity: If player modified, what they changed it to

        Returns:
            Outcome record with performance metrics
        """
        # In production, this would insert into suggestion_outcomes table
        # The database trigger will automatically update player_patterns

        outcome = {
            "id": 1,  # Would be auto-generated
            "suggestion_id": suggestion_id,
            "accepted": accepted,
            "modified_quantity": modified_quantity,
            "actual_order_placed": actual_order_placed,
            "round_result": None,  # Will be filled after round completes
            "performance_score": None,  # Calculated later
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Tracked suggestion {suggestion_id}: "
            f"accepted={accepted}, order={actual_order_placed}"
        )

        return outcome

    async def calculate_performance_score(
        self,
        outcome_id: int,
        inventory_cost: float,
        backlog_cost: float,
        service_level: float,
    ) -> float:
        """
        Calculate performance score for a suggestion outcome.

        Score combines cost efficiency and service level:
        - Lower costs = better score
        - Higher service level = better score
        - Range: 0-100

        Args:
            outcome_id: Outcome record ID
            inventory_cost: Holding cost incurred
            backlog_cost: Stockout cost incurred
            service_level: Percentage of demand fulfilled (0-1)

        Returns:
            Performance score (0-100)
        """
        # Normalize costs (assuming typical ranges)
        max_expected_cost = 100.0
        total_cost = inventory_cost + backlog_cost
        cost_score = max(0, 100 - (total_cost / max_expected_cost * 100))

        # Service level score (0-1 -> 0-100)
        service_score = service_level * 100

        # Weighted combination: 40% cost, 60% service
        performance_score = (cost_score * 0.4) + (service_score * 0.6)

        logger.info(
            f"Calculated performance score for outcome {outcome_id}: "
            f"{performance_score:.2f} "
            f"(cost={cost_score:.1f}, service={service_score:.1f})"
        )

        return round(performance_score, 2)

    async def get_player_patterns(
        self, player_id: int, game_id: int
    ) -> Dict[str, Any]:
        """
        Get detected patterns for a player in a game.

        Analyzes:
        - Acceptance rate
        - Modification behavior
        - Priority preferences
        - Risk tolerance

        Args:
            player_id: Player ID
            game_id: Game ID

        Returns:
            Pattern analysis dictionary
        """
        # In production, query player_patterns table and suggestions
        # For now, return mock data structure

        patterns = {
            "player_id": player_id,
            "game_id": game_id,
            "pattern_type": "balanced",  # conservative, aggressive, balanced, reactive
            "acceptance_rate": 0.75,  # 75% of suggestions accepted
            "avg_modification": 0.15,  # Average 15% deviation when modified
            "preferred_priorities": ["minimize_cost", "balance_costs"],
            "total_suggestions": 20,
            "total_accepted": 15,
            "insights": [
                "Player tends to accept suggestions with >70% confidence",
                "Prefers conservative recommendations during high volatility",
                "Frequently modifies orders downward by 10-20%",
            ],
            "risk_tolerance": "moderate",  # low, moderate, high
            "last_analyzed": datetime.utcnow().isoformat(),
        }

        return patterns

    async def get_ai_effectiveness(self, game_id: int) -> Dict[str, Any]:
        """
        Measure AI suggestion effectiveness for a game.

        Compares AI-suggested orders vs player-chosen orders
        to determine which performs better.

        Args:
            game_id: Game ID

        Returns:
            Effectiveness metrics
        """
        # In production, query suggestion_outcomes and calculate metrics
        # For now, return mock analysis

        effectiveness = {
            "game_id": game_id,
            "total_suggestions": 50,
            "acceptance_rate": 0.72,  # 72% accepted
            "avg_confidence_accepted": 0.81,
            "avg_confidence_rejected": 0.62,
            "performance_comparison": {
                "ai_suggested": {
                    "avg_cost": 42.5,
                    "avg_service_level": 0.88,
                    "avg_performance_score": 78.3,
                },
                "player_modified": {
                    "avg_cost": 48.2,
                    "avg_service_level": 0.85,
                    "avg_performance_score": 72.1,
                },
                "improvement": {
                    "cost_savings": 5.7,  # Following AI saves $5.70 on average
                    "service_improvement": 0.03,  # 3% better service level
                    "score_improvement": 6.2,  # 6.2 points better performance
                },
            },
            "confidence_calibration": {
                "high_confidence": {  # >80%
                    "count": 25,
                    "accuracy": 0.88,  # 88% of high-confidence suggestions performed well
                },
                "medium_confidence": {  # 60-80%
                    "count": 20,
                    "accuracy": 0.70,
                },
                "low_confidence": {  # <60%
                    "count": 5,
                    "accuracy": 0.40,
                },
            },
            "insights": [
                "AI suggestions with >80% confidence perform 12% better on average",
                "Players who consistently follow AI recommendations save $5.70 per round",
                "Conservative suggestions (during high volatility) have 92% acceptance rate",
                "AI is well-calibrated: high confidence correlates with good outcomes",
            ],
        }

        return effectiveness

    async def get_suggestion_history(
        self,
        game_id: int,
        player_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get suggestion history with outcomes.

        Args:
            game_id: Game ID
            player_id: Optional player filter
            limit: Maximum number of records

        Returns:
            List of suggestions with outcomes
        """
        # In production, join agent_suggestions with suggestion_outcomes
        # For now, return mock history

        history = [
            {
                "id": 1,
                "round": 5,
                "agent_name": "wholesaler",
                "suggested_quantity": 50,
                "confidence": 0.78,
                "accepted": True,
                "actual_quantity": 50,
                "modified": False,
                "performance_score": 82.5,
                "outcome": {
                    "inventory_after": 25,
                    "backlog_after": 0,
                    "cost": 38.5,
                    "service_level": 1.0,
                },
                "created_at": "2026-01-14T10:00:00Z",
            },
            {
                "id": 2,
                "round": 6,
                "agent_name": "wholesaler",
                "suggested_quantity": 55,
                "confidence": 0.72,
                "accepted": False,
                "actual_quantity": 45,
                "modified": True,
                "performance_score": 75.3,
                "outcome": {
                    "inventory_after": 15,
                    "backlog_after": 5,
                    "cost": 45.2,
                    "service_level": 0.88,
                },
                "created_at": "2026-01-14T10:15:00Z",
            },
        ]

        return history[:limit]

    async def detect_pattern_type(
        self, acceptance_rate: float, avg_modification: float, recent_suggestions: List[Dict]
    ) -> str:
        """
        Detect player pattern type based on behavior.

        Args:
            acceptance_rate: Percentage of suggestions accepted (0-1)
            avg_modification: Average modification percentage
            recent_suggestions: Recent suggestion outcomes

        Returns:
            Pattern type: conservative, aggressive, balanced, reactive
        """
        # Conservative: High acceptance (>80%), small modifications (<10%)
        if acceptance_rate > 0.8 and avg_modification < 0.1:
            return "conservative"

        # Aggressive: Low acceptance (<50%), large modifications (>30%)
        if acceptance_rate < 0.5 and avg_modification > 0.3:
            return "aggressive"

        # Reactive: Varies based on conditions, high volatility in choices
        if len(recent_suggestions) >= 5:
            modifications = [s.get("modification", 0) for s in recent_suggestions[-5:]]
            if len(modifications) > 2:
                std_dev = statistics.stdev(modifications) if len(modifications) > 1 else 0
                if std_dev > 0.5:
                    return "reactive"

        # Balanced: Moderate acceptance (50-80%), moderate modifications
        return "balanced"

    async def get_acceptance_trends(
        self, game_id: int, player_id: int, window: int = 10
    ) -> Dict[str, Any]:
        """
        Get acceptance rate trends over time.

        Args:
            game_id: Game ID
            player_id: Player ID
            window: Rolling window size for trend calculation

        Returns:
            Trend analysis with rolling averages
        """
        # In production, calculate rolling averages from outcomes
        # For now, return mock trend data

        trends = {
            "player_id": player_id,
            "game_id": game_id,
            "window_size": window,
            "current_acceptance_rate": 0.75,
            "trend": "stable",  # increasing, decreasing, stable, volatile
            "rolling_averages": [
                {"round_range": "1-10", "acceptance_rate": 0.70},
                {"round_range": "11-20", "acceptance_rate": 0.75},
                {"round_range": "21-30", "acceptance_rate": 0.78},
            ],
            "confidence_correlation": {
                "high_confidence_acceptance": 0.92,  # Accept 92% of high-confidence
                "low_confidence_acceptance": 0.45,  # Accept 45% of low-confidence
            },
            "insights": [
                "Acceptance rate improving over time (+8% from start)",
                "Strong correlation between confidence and acceptance",
                "Player learning to trust AI recommendations",
            ],
        }

        return trends

    async def generate_insights(
        self, game_id: int, player_id: Optional[int] = None
    ) -> List[str]:
        """
        Generate actionable insights from pattern analysis.

        Args:
            game_id: Game ID
            player_id: Optional player filter

        Returns:
            List of insight strings
        """
        patterns = await self.get_player_patterns(
            player_id, game_id
        ) if player_id else None
        effectiveness = await self.get_ai_effectiveness(game_id)

        insights = []

        # Player-specific insights
        if patterns:
            if patterns["acceptance_rate"] > 0.8:
                insights.append(
                    f"You trust AI recommendations highly ({patterns['acceptance_rate']:.0%} acceptance rate)"
                )

            if patterns["avg_modification"] > 0.2:
                insights.append(
                    f"You frequently modify suggestions by {patterns['avg_modification']:.0%}. "
                    "Consider why you're adjusting - AI might need better context."
                )

            if patterns["pattern_type"] == "conservative":
                insights.append(
                    "Your conservative approach minimizes risk but may miss opportunities for optimization"
                )
            elif patterns["pattern_type"] == "aggressive":
                insights.append(
                    "Your aggressive modifications show independent thinking but increase cost volatility"
                )

        # Game-wide insights
        if effectiveness["performance_comparison"]["improvement"]["cost_savings"] > 5:
            insights.append(
                f"Following AI recommendations saves "
                f"${effectiveness['performance_comparison']['improvement']['cost_savings']:.2f} per round on average"
            )

        if effectiveness["avg_confidence_accepted"] > effectiveness["avg_confidence_rejected"] + 0.15:
            insights.append(
                "You're good at identifying high-quality suggestions - accepted suggestions have "
                f"{effectiveness['avg_confidence_accepted']:.0%} avg confidence vs "
                f"{effectiveness['avg_confidence_rejected']:.0%} for rejected"
            )

        insights.append(
            f"AI suggestion acceptance rate: {effectiveness['acceptance_rate']:.0%} "
            f"({effectiveness['total_suggestions']} suggestions)"
        )

        return insights


def get_pattern_analysis_service(db: AsyncSession) -> PatternAnalysisService:
    """Get pattern analysis service instance."""
    return PatternAnalysisService(db)

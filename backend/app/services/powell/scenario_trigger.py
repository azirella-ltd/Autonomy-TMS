"""
Scenario Trigger — When to Create Scenarios

Determines whether a TRM decision warrants scenario testing using a
logistic regression on four features already computed by the TRM + CDT
pipeline: risk_bound, urgency, economic_impact, and confidence.

The Analysis Paralysis Problem (SCENARIO_ENGINE.md Section 3.1):
Unbounded scenario generation is worse than no scenarios. The opportunity
cost of late action often exceeds the benefit of finding the optimal action.

Hard caps per decision level prevent runaway scenario creation:
  - Execution (TRM): max 20 scenarios/hour, max 3 candidates each
  - Tactical (Site tGNN): max 10 scenarios/hour, max 5 candidates
  - Strategic (S&OP): max 5 scenarios/hour, max 10 candidates
  - Human-requested (Azirella): unlimited

Weights and threshold are calibrated from historical decision-outcome pairs
using the same infrastructure as CDT (outcome collector, hourly updates).
"""

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default trigger weights (calibrated from historical decision-outcome pairs)
# ---------------------------------------------------------------------------

@dataclass
class TriggerWeights:
    """Logistic regression weights for scenario creation decision.

    score = w_uncertainty * risk_bound
          + w_urgency * urgency
          + w_impact * log(economic_impact)
          - w_confidence * confidence

    create_scenario = score > threshold
    """
    w_uncertainty: float = 0.40
    w_urgency: float = 0.30
    w_impact: float = 0.20
    w_confidence: float = 0.30  # negative contribution (subtracted)
    threshold: float = 0.50

    # Minimum economic impact to consider scenario testing ($)
    min_economic_impact: float = 1000.0


# ---------------------------------------------------------------------------
# Hard caps per decision level
# ---------------------------------------------------------------------------

@dataclass
class LevelCaps:
    """Per-decision-level caps to prevent analysis paralysis."""
    max_candidates: int
    max_simulation_seconds: float
    max_scenarios_per_hour: int


LEVEL_CAPS: Dict[str, LevelCaps] = {
    "execution": LevelCaps(max_candidates=3, max_simulation_seconds=1.0, max_scenarios_per_hour=20),
    "tactical": LevelCaps(max_candidates=5, max_simulation_seconds=5.0, max_scenarios_per_hour=10),
    "strategic": LevelCaps(max_candidates=10, max_simulation_seconds=30.0, max_scenarios_per_hour=5),
    "human_requested": LevelCaps(max_candidates=10, max_simulation_seconds=60.0, max_scenarios_per_hour=999999),
}


# ---------------------------------------------------------------------------
# Rate tracker (in-memory, per-process)
# ---------------------------------------------------------------------------

class _RateTracker:
    """Tracks scenario creation rates per (decision_level, tenant_id).

    Uses a sliding window of timestamps to enforce hourly rate limits.
    """

    def __init__(self):
        self._timestamps: Dict[str, list] = defaultdict(list)

    def _key(self, decision_level: str, tenant_id: int) -> str:
        return f"{decision_level}:{tenant_id}"

    def count_in_window(self, decision_level: str, tenant_id: int, window_seconds: float = 3600.0) -> int:
        key = self._key(decision_level, tenant_id)
        now = time.monotonic()
        cutoff = now - window_seconds
        # Prune old entries
        self._timestamps[key] = [t for t in self._timestamps[key] if t > cutoff]
        return len(self._timestamps[key])

    def record(self, decision_level: str, tenant_id: int) -> None:
        key = self._key(decision_level, tenant_id)
        self._timestamps[key].append(time.monotonic())


# Module-level singleton
_rate_tracker = _RateTracker()


# ---------------------------------------------------------------------------
# ScenarioTrigger
# ---------------------------------------------------------------------------

class ScenarioTrigger:
    """Determines whether a TRM decision warrants scenario testing.

    Uses a logistic regression on (risk_bound, urgency, log_economic_impact,
    confidence) with configurable weights and threshold per tenant.

    Respects hard caps per decision level to prevent analysis paralysis.
    """

    def __init__(
        self,
        tenant_id: int,
        weights: Optional[TriggerWeights] = None,
    ):
        self.tenant_id = tenant_id
        self.weights = weights or TriggerWeights()

    def should_create_scenario(
        self,
        trm_decision: Dict[str, Any],
        context: Dict[str, Any],
    ) -> bool:
        """Evaluate whether a scenario should be created for this decision.

        Args:
            trm_decision: Decision dict with keys:
                - risk_bound: float (CDT P(loss > threshold))
                - confidence: float (TRM self-confidence)
                - trm_type: str
            context: Context dict with keys:
                - urgency: float (UrgencyVector time pressure)
                - economic_impact: float (order value * shortfall)
                - decision_level: str (execution/tactical/strategic/human_requested)

        Returns:
            True if scenario testing is warranted, False otherwise.
        """
        decision_level = context.get("decision_level", "execution")

        # Human-requested scenarios always pass trigger check
        if decision_level == "human_requested":
            return self._check_rate_limit(decision_level)

        # Extract features
        risk_bound = float(trm_decision.get("risk_bound", 0.0))
        confidence = float(trm_decision.get("confidence", 0.5))
        urgency = float(context.get("urgency", 0.0))
        economic_impact = float(context.get("economic_impact", 0.0))

        # Below minimum impact threshold — not worth scenario testing
        if economic_impact < self.weights.min_economic_impact:
            return False

        # Compute logistic score
        score = self._compute_score(risk_bound, urgency, economic_impact, confidence)

        if score <= self.weights.threshold:
            return False

        # Check rate limit
        if not self._check_rate_limit(decision_level):
            logger.info(
                "Scenario trigger suppressed by rate limit: level=%s tenant=%d score=%.3f",
                decision_level, self.tenant_id, score,
            )
            return False

        logger.info(
            "Scenario trigger fired: trm_type=%s level=%s score=%.3f "
            "(risk=%.2f urgency=%.2f impact=$%.0f conf=%.2f)",
            trm_decision.get("trm_type", "unknown"),
            decision_level, score, risk_bound, urgency, economic_impact, confidence,
        )
        return True

    def _compute_score(
        self,
        risk_bound: float,
        urgency: float,
        economic_impact: float,
        confidence: float,
    ) -> float:
        """Compute logistic regression score from four features.

        score = w_uncertainty * risk_bound
              + w_urgency * urgency
              + w_impact * log(economic_impact)
              - w_confidence * confidence
        """
        w = self.weights
        # Log-scale economic impact to prevent large values dominating
        log_impact = math.log(max(economic_impact, 1.0)) / math.log(1e6)
        log_impact = max(0.0, min(1.0, log_impact))

        score = (
            w.w_uncertainty * risk_bound
            + w.w_urgency * urgency
            + w.w_impact * log_impact
            - w.w_confidence * confidence
        )
        return score

    def _check_rate_limit(self, decision_level: str) -> bool:
        """Check if we are within the hourly rate limit for this level."""
        caps = LEVEL_CAPS.get(decision_level, LEVEL_CAPS["execution"])
        current_count = _rate_tracker.count_in_window(decision_level, self.tenant_id)
        if current_count >= caps.max_scenarios_per_hour:
            return False
        _rate_tracker.record(decision_level, self.tenant_id)
        return True

    def get_level_caps(self, decision_level: str) -> LevelCaps:
        """Return the hard caps for a decision level."""
        return LEVEL_CAPS.get(decision_level, LEVEL_CAPS["execution"])

    @staticmethod
    def get_trigger_weights(tenant_id: int) -> Dict[str, float]:
        """Return current trigger weights for a tenant.

        Future: load per-tenant calibrated weights from DB.
        Currently returns defaults.
        """
        w = TriggerWeights()
        return {
            "w_uncertainty": w.w_uncertainty,
            "w_urgency": w.w_urgency,
            "w_impact": w.w_impact,
            "w_confidence": w.w_confidence,
            "threshold": w.threshold,
            "min_economic_impact": w.min_economic_impact,
        }

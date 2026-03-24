"""
Contextual BSC — Context-Weighted Balanced Scorecard Scoring

Implements dynamic BSC scoring where metric weights come from the business
context, not static configuration. A high-value customer order increases the
customer dimension weight; high capacity utilization increases operational
weight.

Core formula (SCENARIO_ENGINE.md Section 5):
    scenario_score = raw_bsc_value * compound_likelihood * urgency_discount

Where:
    raw_bsc_value = context-weighted BSC across 4 dimensions
    compound_likelihood = product of individual decision CDT bounds
    urgency_discount = time decay (longer execution = less value)

Includes satisficing check: if score > aspiration_threshold, stop search early
(Herbert Simon, 1956 — bounded rationality).
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BSC dimension scores
# ---------------------------------------------------------------------------

@dataclass
class BSCScore:
    """Balanced Scorecard score across four dimensions.

    Each dimension is a normalized [0, 1] score where higher = better.
    The final_score incorporates context weights, compound likelihood,
    and urgency discount.
    """
    financial_score: float = 0.0   # Cost delta from baseline
    customer_score: float = 0.0    # OTIF / fill rate delta
    operational_score: float = 0.0  # Inventory efficiency delta
    strategic_score: float = 0.0   # Flexibility / resilience delta

    # Context weights used (for audit)
    financial_weight: float = 0.25
    customer_weight: float = 0.25
    operational_weight: float = 0.25
    strategic_weight: float = 0.25

    # Raw weighted BSC
    raw_bsc_value: float = 0.0

    # Risk adjustments
    compound_likelihood: float = 1.0
    urgency_discount: float = 1.0

    # Final risk-adjusted score
    final_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "financial_score": self.financial_score,
            "customer_score": self.customer_score,
            "operational_score": self.operational_score,
            "strategic_score": self.strategic_score,
            "financial_weight": self.financial_weight,
            "customer_weight": self.customer_weight,
            "operational_weight": self.operational_weight,
            "strategic_weight": self.strategic_weight,
            "raw_bsc_value": self.raw_bsc_value,
            "compound_likelihood": self.compound_likelihood,
            "urgency_discount": self.urgency_discount,
            "final_score": self.final_score,
        }


# ---------------------------------------------------------------------------
# ContextualBSC
# ---------------------------------------------------------------------------

class ContextualBSC:
    """Context-weighted BSC scoring for scenario evaluation.

    BSC dimension weights are dynamic — they come from the business context,
    not static configuration. This implements Prospect Theory: the certain
    option is preferred unless the risky upside is large enough.
    """

    # Base weights (before context adjustment)
    BASE_FINANCIAL_WEIGHT = 0.25
    BASE_CUSTOMER_WEIGHT = 0.25
    BASE_OPERATIONAL_WEIGHT = 0.25
    BASE_STRATEGIC_WEIGHT = 0.25

    # Satisficing: scenario must be at least 5% better than baseline
    DEFAULT_MIN_IMPROVEMENT_PCT = 0.05

    def __init__(
        self,
        aspiration_threshold: Optional[float] = None,
        min_improvement_pct: float = 0.05,
    ):
        """
        Args:
            aspiration_threshold: If set, scenarios above this score are
                accepted immediately without further search. If None,
                computed as baseline_bsc * (1 + min_improvement_pct).
            min_improvement_pct: Minimum improvement over baseline to
                justify scenario execution (default 5%).
        """
        self.aspiration_threshold = aspiration_threshold
        self.min_improvement_pct = min_improvement_pct

    def compute_bsc(
        self,
        sim_result: Dict[str, Any],
        baseline_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> BSCScore:
        """Compute BSC score from simulation result vs baseline.

        Args:
            sim_result: Simulation output from _DagChain after injecting
                scenario actions. Keys: total_cost, total_holding,
                total_backlog, avg_fill_rate, network_avg_days_cover.
            baseline_result: Simulation output from _DagChain with no
                actions injected (the "do nothing" case).
            context: Business context for weight adjustment. Keys:
                revenue_pressure_factor, customer_importance_factor,
                capacity_utilization_factor, product_importance_factor.

        Returns:
            BSCScore with all dimension scores, weights, and final score.
        """
        # Compute context-adjusted weights
        weights = self.compute_context_weights(context)

        # Compute per-dimension scores (normalized improvement over baseline)
        financial = self._financial_score(sim_result, baseline_result)
        customer = self._customer_score(sim_result, baseline_result)
        operational = self._operational_score(sim_result, baseline_result)
        strategic = self._strategic_score(sim_result, baseline_result, context)

        # Weighted sum
        raw_bsc = (
            financial * weights["financial"]
            + customer * weights["customer"]
            + operational * weights["operational"]
            + strategic * weights["strategic"]
        )

        score = BSCScore(
            financial_score=financial,
            customer_score=customer,
            operational_score=operational,
            strategic_score=strategic,
            financial_weight=weights["financial"],
            customer_weight=weights["customer"],
            operational_weight=weights["operational"],
            strategic_weight=weights["strategic"],
            raw_bsc_value=raw_bsc,
        )
        return score

    def compute_context_weights(self, context: Dict[str, Any]) -> Dict[str, float]:
        """Compute dynamic BSC dimension weights from business context.

        Each dimension's weight is adjusted by a context factor:
            adjusted = base_weight * (1 + factor)

        All weights are then normalized to sum to 1.0.

        Context factors (all in [0, 1], 0 = no adjustment):
            revenue_pressure_factor: Revenue pressure at location
            customer_importance_factor: Top customer? Contractual penalties?
            capacity_utilization_factor: Current utilization level
            product_importance_factor: Core vs tail product
        """
        rev_factor = float(context.get("revenue_pressure_factor", 0.0))
        cust_factor = float(context.get("customer_importance_factor", 0.0))
        cap_factor = float(context.get("capacity_utilization_factor", 0.0))
        prod_factor = float(context.get("product_importance_factor", 0.0))

        raw = {
            "financial": self.BASE_FINANCIAL_WEIGHT * (1.0 + rev_factor),
            "customer": self.BASE_CUSTOMER_WEIGHT * (1.0 + cust_factor),
            "operational": self.BASE_OPERATIONAL_WEIGHT * (1.0 + cap_factor),
            "strategic": self.BASE_STRATEGIC_WEIGHT * (1.0 + prod_factor),
        }

        # Normalize to sum to 1.0
        total = sum(raw.values())
        if total <= 0:
            return {
                "financial": 0.25,
                "customer": 0.25,
                "operational": 0.25,
                "strategic": 0.25,
            }

        return {k: v / total for k, v in raw.items()}

    def risk_adjust(
        self,
        raw_score: float,
        compound_likelihood: float,
        urgency_discount: float,
    ) -> float:
        """Apply risk adjustment to raw BSC score.

        final = raw_score * compound_likelihood * urgency_discount

        This implements Prospect Theory: the certain option (high likelihood)
        is preferred unless the risky upside (high raw score) is large enough.
        """
        return raw_score * compound_likelihood * urgency_discount

    def satisfices(
        self,
        score: float,
        baseline_score: float = 0.0,
    ) -> bool:
        """Check if a scenario score exceeds the aspiration threshold.

        Following Herbert Simon's satisficing principle, search stops
        early if any candidate exceeds the aspiration threshold.

        Args:
            score: Final risk-adjusted score of the candidate
            baseline_score: Score of the "do nothing" baseline

        Returns:
            True if the scenario is good enough to accept immediately.
        """
        if self.aspiration_threshold is not None:
            return score > self.aspiration_threshold

        # Default: must be min_improvement_pct better than baseline
        threshold = baseline_score * (1.0 + self.min_improvement_pct)
        return score > threshold

    # -----------------------------------------------------------------------
    # Per-dimension scoring
    # -----------------------------------------------------------------------

    def _financial_score(
        self,
        sim_result: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> float:
        """Financial: cost reduction compared to baseline.

        Score = (baseline_cost - scenario_cost) / max(baseline_cost, 1)
        Positive = cost reduction = good. Negative = cost increase.
        Clamped to [-1, 1].
        """
        scenario_cost = sim_result.get("total_cost", 0.0)
        baseline_cost = baseline.get("total_cost", 0.0)
        if baseline_cost <= 0:
            return 0.0
        delta = (baseline_cost - scenario_cost) / baseline_cost
        return max(-1.0, min(1.0, delta))

    def _customer_score(
        self,
        sim_result: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> float:
        """Customer: OTIF/fill rate improvement.

        Score = (scenario_fill_rate - baseline_fill_rate) / max(1 - baseline, 0.01)
        Positive = fill rate improvement = good.
        Clamped to [-1, 1].
        """
        scenario_fill = sim_result.get("avg_fill_rate", 0.0)
        baseline_fill = baseline.get("avg_fill_rate", 0.0)
        headroom = max(1.0 - baseline_fill, 0.01)
        delta = (scenario_fill - baseline_fill) / headroom
        return max(-1.0, min(1.0, delta))

    def _operational_score(
        self,
        sim_result: Dict[str, Any],
        baseline: Dict[str, Any],
    ) -> float:
        """Operational: inventory efficiency (days of cover stability).

        Measures how close days-of-cover is to the optimal target range
        (15-30 days). Being within range is positive; deviation is negative.
        """
        scenario_doc = sim_result.get("network_avg_days_cover", 15.0)
        baseline_doc = baseline.get("network_avg_days_cover", 15.0)

        # Optimal range: 15-30 days of cover
        optimal_center = 22.5
        optimal_range = 7.5

        scenario_dev = abs(scenario_doc - optimal_center) / optimal_range
        baseline_dev = abs(baseline_doc - optimal_center) / optimal_range

        # Improvement = reduction in deviation
        if baseline_dev <= 0:
            return 0.0
        delta = (baseline_dev - scenario_dev) / max(baseline_dev, 0.01)
        return max(-1.0, min(1.0, delta))

    def _strategic_score(
        self,
        sim_result: Dict[str, Any],
        baseline: Dict[str, Any],
        context: Dict[str, Any],
    ) -> float:
        """Strategic: flexibility and resilience.

        Measures supply diversity (fewer stockouts = more resilient) and
        cost stability (lower cost variance = more predictable).
        """
        # Stockout reduction
        scenario_stockout = 1.0 if sim_result.get("any_stockout", False) else 0.0
        baseline_stockout = 1.0 if baseline.get("any_stockout", False) else 0.0
        stockout_improvement = baseline_stockout - scenario_stockout

        # Cost variance reduction (via holding/backlog split stability)
        scenario_holding = sim_result.get("total_holding", 0.0)
        scenario_backlog = sim_result.get("total_backlog", 0.0)
        scenario_total = scenario_holding + scenario_backlog
        baseline_holding = baseline.get("total_holding", 0.0)
        baseline_backlog = baseline.get("total_backlog", 0.0)
        baseline_total = baseline_holding + baseline_backlog

        # Balance ratio: how evenly distributed are costs?
        if scenario_total > 0:
            scenario_balance = 1.0 - abs(scenario_holding - scenario_backlog) / scenario_total
        else:
            scenario_balance = 1.0
        if baseline_total > 0:
            baseline_balance = 1.0 - abs(baseline_holding - baseline_backlog) / baseline_total
        else:
            baseline_balance = 1.0

        balance_improvement = scenario_balance - baseline_balance

        return max(-1.0, min(1.0, 0.5 * stockout_improvement + 0.5 * balance_improvement))


def compute_compound_likelihood(action_likelihoods: List[float]) -> float:
    """Compute compound likelihood as the product of individual likelihoods.

    Each decision in a scenario has its own CDT-derived likelihood.
    The scenario's compound likelihood is:
        compound = prod(likelihood_i)

    Missing likelihoods default to 0.80 (moderate confidence).
    """
    if not action_likelihoods:
        return 1.0

    compound = 1.0
    for likelihood in action_likelihoods:
        # Default missing likelihoods to 0.80
        val = likelihood if likelihood is not None else 0.80
        compound *= max(0.01, min(1.0, val))

    return compound


def compute_urgency_discount(
    urgency: float,
    execution_days: int,
    max_discount: float = 0.5,
) -> float:
    """Compute urgency discount for scenario score.

    Scenarios that take longer to execute are worth less because the
    situation may change before all actions complete.

    discount = 1.0 - time_penalty
    time_penalty = min(max_discount, execution_days / (urgency_scale * 30))

    Higher urgency = steeper discount (less tolerance for delay).
    """
    if execution_days <= 0:
        return 1.0

    # Urgency scales the penalty: high urgency = less tolerance for delay
    urgency_scale = max(0.1, 1.0 - urgency * 0.5)
    time_penalty = min(max_discount, execution_days / (urgency_scale * 30.0))

    return max(1.0 - max_discount, 1.0 - time_penalty)

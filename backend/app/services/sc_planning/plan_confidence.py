"""
Plan-Level Confidence Score

Computes a composite confidence metric for a supply plan by aggregating
conformal prediction coverage across all planning inputs:

1. Demand interval coverage — fraction of demand entries with calibrated intervals
2. Lead time interval coverage — fraction of supply plans with LT intervals
3. Safety stock adequacy — fraction of SS targets covering worst-case demand-during-LT
4. Calibration freshness — fraction of predictors that are fresh (not stale)

The composite score is in [0, 1] where:
  >= 0.80: High confidence (well-calibrated intervals, adequate buffers)
  0.60-0.80: Moderate confidence (some gaps in calibration)
  < 0.60: Low confidence (mostly uncalibrated, recommend running calibration)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class PlanConfidenceScore:
    """Composite plan-level confidence with diagnostic breakdown."""

    overall: float                           # Weighted composite [0, 1]

    # Sub-scores (each [0, 1])
    demand_coverage_score: float             # Fraction of demand entries with intervals
    lead_time_coverage_score: float          # Fraction of supply plans with LT intervals
    safety_stock_adequacy: float             # Fraction of SS targets covering worst-case
    calibration_freshness: float             # Fraction of predictors not stale

    # Joint coverage from conformal suite
    joint_conformal_coverage: Optional[float] = None

    # Diagnostics
    demand_entries_total: int = 0
    demand_entries_with_intervals: int = 0
    supply_plans_total: int = 0
    supply_plans_with_lt_intervals: int = 0
    ss_targets_total: int = 0
    ss_targets_adequate: int = 0
    stale_predictors: int = 0
    total_predictors: int = 0

    # Confidence band
    confidence_level: str = "unknown"        # "high", "moderate", "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "demand_coverage_score": round(self.demand_coverage_score, 4),
            "lead_time_coverage_score": round(self.lead_time_coverage_score, 4),
            "safety_stock_adequacy": round(self.safety_stock_adequacy, 4),
            "calibration_freshness": round(self.calibration_freshness, 4),
            "joint_conformal_coverage": (
                round(self.joint_conformal_coverage, 4)
                if self.joint_conformal_coverage is not None else None
            ),
            "confidence_level": self.confidence_level,
            "diagnostics": {
                "demand_entries": f"{self.demand_entries_with_intervals}/{self.demand_entries_total}",
                "supply_plans_lt": f"{self.supply_plans_with_lt_intervals}/{self.supply_plans_total}",
                "ss_adequate": f"{self.ss_targets_adequate}/{self.ss_targets_total}",
                "stale_predictors": f"{self.stale_predictors}/{self.total_predictors}",
            },
        }


class PlanConfidenceCalculator:
    """
    Computes plan-level confidence from demand estimates, supply plans,
    and inventory targets.

    Weights reflect relative importance:
    - Demand intervals (0.35): Most impactful — demand is the primary driver
    - Lead time intervals (0.25): Second most impactful — drives timing risk
    - Safety stock adequacy (0.25): Buffer coverage against worst case
    - Calibration freshness (0.15): Data recency
    """

    DEMAND_WEIGHT = 0.35
    LEAD_TIME_WEIGHT = 0.25
    SAFETY_STOCK_WEIGHT = 0.25
    FRESHNESS_WEIGHT = 0.15

    def compute(
        self,
        demand_estimates: Dict[Tuple[str, str, date], Any],
        supply_plans: List,
        target_inventory: Dict[Tuple[str, str], float],
        suite=None,
    ) -> PlanConfidenceScore:
        """
        Compute composite plan confidence score.

        Args:
            demand_estimates: DemandEstimateDict from Step 1
            supply_plans: List[SupplyPlan] from Step 3
            target_inventory: Target inventory dict from Step 2
            suite: Optional SupplyChainConformalSuite for freshness/joint coverage
        """
        # Sub-score 1: Demand coverage
        demand_total = len(demand_estimates)
        demand_with_intervals = sum(
            1 for est in demand_estimates.values()
            if hasattr(est, 'has_interval') and est.has_interval
        )
        demand_score = demand_with_intervals / demand_total if demand_total > 0 else 0.0

        # Sub-score 2: Lead time coverage
        plans_total = len(supply_plans)
        plans_with_lt = sum(
            1 for p in supply_plans
            if getattr(p, 'lead_time_lower', None) is not None
        )
        lt_score = plans_with_lt / plans_total if plans_total > 0 else 0.0

        # Sub-score 3: Safety stock adequacy
        ss_total = 0
        ss_adequate = 0
        for (product_id, site_id), target in target_inventory.items():
            if target <= 0:
                continue
            ss_total += 1

            # Check if any demand estimate for this product-site has an interval
            # where the safety stock covers the worst-case gap
            worst_case_gap = 0
            for (p, s, d), est in demand_estimates.items():
                if p == product_id and s == site_id and hasattr(est, 'has_interval') and est.has_interval:
                    gap = est.upper - est.point
                    worst_case_gap = max(worst_case_gap, gap)

            if worst_case_gap == 0 or target >= worst_case_gap:
                ss_adequate += 1

        ss_score = ss_adequate / ss_total if ss_total > 0 else 0.0

        # Sub-score 4: Calibration freshness
        freshness_score = 1.0
        stale_count = 0
        total_predictors = 0

        if suite is not None:
            try:
                stale_keys = suite.check_recalibration_needed(max_age_hours=168)
                stale_count = len(stale_keys)

                summary = suite.get_calibration_summary()
                total_predictors = sum(
                    summary.get(f'{t}_predictors', 0)
                    for t in ['demand', 'lead_time', 'yield', 'price']
                )

                if total_predictors > 0:
                    freshness_score = (total_predictors - stale_count) / total_predictors
            except Exception as e:
                logger.debug(f"Freshness check failed: {e}")

        # Joint conformal coverage
        joint_coverage = None
        if suite is not None:
            try:
                joint_coverage = suite.compute_joint_coverage(
                    include_yields=False, include_prices=False
                )
            except Exception as e:
                logger.debug(f"Joint coverage computation failed: {e}")

        # Composite score
        overall = (
            self.DEMAND_WEIGHT * demand_score
            + self.LEAD_TIME_WEIGHT * lt_score
            + self.SAFETY_STOCK_WEIGHT * ss_score
            + self.FRESHNESS_WEIGHT * freshness_score
        )

        # Confidence level
        if overall >= 0.80:
            level = "high"
        elif overall >= 0.60:
            level = "moderate"
        else:
            level = "low"

        return PlanConfidenceScore(
            overall=overall,
            demand_coverage_score=demand_score,
            lead_time_coverage_score=lt_score,
            safety_stock_adequacy=ss_score,
            calibration_freshness=freshness_score,
            joint_conformal_coverage=joint_coverage,
            demand_entries_total=demand_total,
            demand_entries_with_intervals=demand_with_intervals,
            supply_plans_total=plans_total,
            supply_plans_with_lt_intervals=plans_with_lt,
            ss_targets_total=ss_total,
            ss_targets_adequate=ss_adequate,
            stale_predictors=stale_count,
            total_predictors=total_predictors,
            confidence_level=level,
        )

"""
Perturbation Generator — Creates N scenarios around the ERP baseline.

Perturbs the operating parameters (demand, lead times, costs, capacity)
while preserving the topology. This gives the agents training diversity
without drifting away from the tenant's actual network.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np

from .erp_baseline_extractor import ERPBaselineSnapshot

logger = logging.getLogger(__name__)


@dataclass
class PerturbationParams:
    """Multipliers and shifts applied to the baseline for one scenario."""
    scenario_index: int

    # Demand
    demand_scale_by_product: Dict[str, float] = field(default_factory=dict)
    demand_cv_scale: float = 1.0

    # Lead time
    lead_time_scale_by_lane: Dict[str, float] = field(default_factory=dict)
    lead_time_cv_scale: float = 1.0

    # Costs
    unit_cost_scale_by_product: Dict[str, float] = field(default_factory=dict)
    stockout_cost_scale: float = 1.0
    ordering_cost_scale: float = 1.0

    # Capacity
    capacity_scale_by_lane: Dict[str, float] = field(default_factory=dict)
    supplier_reliability_delta: float = 0.0

    # Seasonality
    seasonal_intensity_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_index": self.scenario_index,
            "demand_cv_scale": self.demand_cv_scale,
            "lead_time_cv_scale": self.lead_time_cv_scale,
            "stockout_cost_scale": self.stockout_cost_scale,
            "ordering_cost_scale": self.ordering_cost_scale,
            "supplier_reliability_delta": self.supplier_reliability_delta,
            "seasonal_intensity_scale": self.seasonal_intensity_scale,
            "demand_scale_by_product_sample": dict(list(self.demand_scale_by_product.items())[:5]),
            "lead_time_scale_by_lane_sample": dict(list(self.lead_time_scale_by_lane.items())[:5]),
        }


class PerturbationGenerator:
    """Generates perturbation scenarios around the ERP baseline.

    Each perturbation is a parameterized modification of the baseline.
    The generator is deterministic given the seed, so the same config
    produces the same perturbations across runs.

    Default ranges (configurable):
        Demand:            [-15%, +15%]
        Demand CV:         [0.5x, 2.0x]
        Lead time:         [-20%, +25%] (right-skewed: delays more likely)
        Lead time CV:      [0.7x, 1.8x]
        Unit cost:         [-10%, +10%]
        Stockout cost:     [-15%, +20%]
        Ordering cost:     [-10%, +15%]
        Capacity:          [-20%, +10%]
        Reliability delta: [-0.10, +0.05]
        Seasonality:       [0.7x, 1.5x]
    """

    def __init__(self, seed: int = 0):
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    def generate(
        self,
        baseline: ERPBaselineSnapshot,
        n: int = 500,
    ) -> List[PerturbationParams]:
        """Generate n perturbation scenarios."""
        perturbations = []

        product_ids = baseline.get_product_ids()
        lane_keys = [f"{l.from_site}->{l.to_site}" for l in baseline.lanes]

        # Scenario 0 is the identity (unperturbed baseline)
        perturbations.append(PerturbationParams(
            scenario_index=0,
            demand_scale_by_product={pid: 1.0 for pid in product_ids},
            demand_cv_scale=1.0,
            lead_time_scale_by_lane={lk: 1.0 for lk in lane_keys},
            lead_time_cv_scale=1.0,
            unit_cost_scale_by_product={pid: 1.0 for pid in product_ids},
        ))

        # Scenarios 1..n-1 are perturbations
        for i in range(1, n):
            scenario_rng = np.random.default_rng(self.seed * 10000 + i)

            demand_scale = {
                pid: self._triangular(scenario_rng, 0.85, 1.0, 1.15)
                for pid in product_ids
            }
            lane_lt_scale = {
                lk: self._triangular(scenario_rng, 0.80, 1.0, 1.25)  # right-skewed
                for lk in lane_keys
            }
            cost_scale = {
                pid: self._uniform(scenario_rng, 0.90, 1.10)
                for pid in product_ids
            }
            lane_cap_scale = {
                lk: self._triangular(scenario_rng, 0.80, 1.0, 1.10)
                for lk in lane_keys
            }

            perturbations.append(PerturbationParams(
                scenario_index=i,
                demand_scale_by_product=demand_scale,
                demand_cv_scale=self._log_uniform(scenario_rng, 0.5, 2.0),
                lead_time_scale_by_lane=lane_lt_scale,
                lead_time_cv_scale=self._log_uniform(scenario_rng, 0.7, 1.8),
                unit_cost_scale_by_product=cost_scale,
                stockout_cost_scale=self._uniform(scenario_rng, 0.85, 1.20),
                ordering_cost_scale=self._uniform(scenario_rng, 0.90, 1.15),
                capacity_scale_by_lane=lane_cap_scale,
                supplier_reliability_delta=self._uniform(scenario_rng, -0.10, 0.05),
                seasonal_intensity_scale=self._uniform(scenario_rng, 0.7, 1.5),
            ))

        logger.info(
            "PerturbationGenerator: %d scenarios generated (seed=%d, products=%d, lanes=%d)",
            n, self.seed, len(product_ids), len(lane_keys),
        )
        return perturbations

    @staticmethod
    def _triangular(rng: np.random.Generator, low: float, mode: float, high: float) -> float:
        return float(rng.triangular(low, mode, high))

    @staticmethod
    def _uniform(rng: np.random.Generator, low: float, high: float) -> float:
        return float(rng.uniform(low, high))

    @staticmethod
    def _log_uniform(rng: np.random.Generator, low: float, high: float) -> float:
        """Log-uniform sampling: equal probability per order of magnitude."""
        return float(np.exp(rng.uniform(np.log(low), np.log(high))))

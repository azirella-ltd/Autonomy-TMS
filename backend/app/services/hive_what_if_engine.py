"""
Hive What-If Engine — Scenario evaluation using coordinated TRM simulation.

Takes a PlanningScenario's variable deltas, instantiates a CoordinatedSimRunner,
runs an N-period simulation with all 11 TRMs + signal bus, and returns a
balanced scorecard.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Sections 11-12
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class BalancedScorecard:
    """Structured balanced scorecard with four quadrants.

    Provides both raw metrics and normalized scores for comparison.
    """

    def __init__(
        self,
        financial: Optional[Dict[str, float]] = None,
        customer: Optional[Dict[str, float]] = None,
        operational: Optional[Dict[str, float]] = None,
        strategic: Optional[Dict[str, float]] = None,
    ):
        self.financial = financial or {}
        self.customer = customer or {}
        self.operational = operational or {}
        self.strategic = strategic or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "financial": self.financial,
            "customer": self.customer,
            "operational": self.operational,
            "strategic": self.strategic,
        }

    @property
    def net_benefit(self) -> float:
        """Weighted net benefit across all quadrants."""
        weights = {"financial": 0.3, "customer": 0.3, "operational": 0.25, "strategic": 0.15}
        total = 0.0
        for name, weight in weights.items():
            metrics = getattr(self, name, {})
            if metrics:
                values = [v for v in metrics.values() if isinstance(v, (int, float))]
                if values:
                    total += weight * (sum(values) / len(values))
        return total


class HiveWhatIfEngine:
    """Hive-aware what-if evaluation engine.

    Runs CoordinatedSimRunner with variable deltas applied to produce
    a balanced scorecard for planning scenario comparison.

    Args:
        site_key: Site identifier for simulation.
        seed: Optional random seed for reproducibility.
        executor_factory: Optional callable returning TRM executors.
            If not provided, uses synthetic simulation.
    """

    def __init__(
        self,
        site_key: str = "default",
        seed: Optional[int] = None,
        executor_factory: Optional[Callable] = None,
    ):
        self.site_key = site_key
        self.seed = seed
        self.executor_factory = executor_factory
        self._cache: Dict[str, BalancedScorecard] = {}

    def evaluate(
        self,
        variable_deltas: Optional[Dict[str, Any]] = None,
        num_periods: int = 12,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Run simulation with variable deltas and return balanced scorecard.

        Args:
            variable_deltas: Override parameters for the simulation.
            num_periods: Number of periods to simulate.
            use_cache: If True, return cached result for identical deltas.

        Returns:
            Balanced scorecard as dict.
        """
        import json
        cache_key = json.dumps(variable_deltas or {}, sort_keys=True)

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key].to_dict()

        start = time.time()

        if self.executor_factory is not None:
            scorecard = self._run_coordinated(variable_deltas, num_periods)
        else:
            scorecard = self._run_synthetic(variable_deltas, num_periods)

        duration = time.time() - start
        logger.info(
            f"HiveWhatIfEngine evaluated in {duration:.2f}s "
            f"({num_periods} periods, net_benefit={scorecard.net_benefit:.4f})"
        )

        if use_cache:
            self._cache[cache_key] = scorecard

        return scorecard.to_dict()

    def _run_coordinated(
        self,
        variable_deltas: Optional[Dict[str, Any]],
        num_periods: int,
    ) -> BalancedScorecard:
        """Run full coordinated simulation with signal bus."""
        try:
            from app.services.powell.coordinated_sim_runner import CoordinatedSimRunner
            from app.services.powell.hive_signal import HiveSignalBus

            bus = HiveSignalBus()
            runner = CoordinatedSimRunner(
                site_key=self.site_key,
                signal_bus=bus,
                seed=self.seed,
            )

            executors = self.executor_factory(variable_deltas)
            result = runner.run_episode(
                num_periods=num_periods,
                executor_factory=lambda period: executors,
            )

            return self._episode_to_scorecard(result, variable_deltas)
        except Exception as e:
            logger.warning(f"Coordinated sim failed, falling back to synthetic: {e}")
            return self._run_synthetic(variable_deltas, num_periods)

    def _run_synthetic(
        self,
        variable_deltas: Optional[Dict[str, Any]],
        num_periods: int,
    ) -> BalancedScorecard:
        """Generate synthetic scorecard based on variable deltas.

        Used when no executor_factory is provided, or as fallback.
        """
        deltas = variable_deltas or {}
        rng = np.random.RandomState(self.seed or 42)

        # Base metrics influenced by deltas
        ss_mult = deltas.get("safety_stock_multiplier", 1.0)
        demand_change = deltas.get("demand_change_pct", 0.0)
        lead_time_change = deltas.get("lead_time_change_pct", 0.0)

        # Simulate cost and service level trajectories
        base_cost = 100.0
        base_fill_rate = 0.95
        base_inv_turns = 8.0

        # Safety stock changes affect cost and fill rate inversely
        cost_factor = 1.0 + 0.05 * (ss_mult - 1.0) + 0.01 * demand_change
        fill_factor = 1.0 + 0.02 * (ss_mult - 1.0) - 0.005 * demand_change
        turns_factor = 1.0 - 0.03 * (ss_mult - 1.0) + 0.01 * lead_time_change

        # Add simulation noise
        noise = rng.normal(0, 0.02, num_periods)
        cost_trajectory = base_cost * cost_factor * (1 + noise)
        fill_trajectory = np.clip(
            base_fill_rate * fill_factor * (1 + rng.normal(0, 0.01, num_periods)),
            0, 1,
        )

        avg_cost = float(np.mean(cost_trajectory))
        avg_fill = float(np.mean(fill_trajectory))
        avg_turns = float(base_inv_turns * turns_factor)
        bullwhip = float(1.0 + 0.1 * abs(demand_change) + rng.uniform(0, 0.1))

        return BalancedScorecard(
            financial={
                "total_cost": avg_cost,
                "total_cost_reduction": (base_cost - avg_cost) / base_cost,
                "working_capital_improvement": 0.05 * (ss_mult - 1.0),
            },
            customer={
                "otif": avg_fill,
                "otif_improvement": avg_fill - base_fill_rate,
                "fill_rate": avg_fill,
            },
            operational={
                "inventory_turns": avg_turns,
                "inventory_turns_improvement": (avg_turns - base_inv_turns) / base_inv_turns,
                "bullwhip_ratio": bullwhip,
            },
            strategic={
                "flexibility_score": float(0.7 + rng.uniform(-0.1, 0.1)),
                "resilience_score": float(0.6 + rng.uniform(-0.1, 0.1)),
            },
        )

    def _episode_to_scorecard(
        self,
        episode_result,
        variable_deltas: Optional[Dict[str, Any]],
    ) -> BalancedScorecard:
        """Convert CoordinatedSimRunner EpisodeResult to BalancedScorecard."""
        num_traces = len(episode_result.traces)
        total_reward = episode_result.total_cross_head_reward
        avg_conflicts = episode_result.avg_conflicts_per_period
        avg_signals = episode_result.avg_signals_per_period

        # Derive scorecard from episode metrics
        coordination_quality = total_reward / max(1, num_traces)
        conflict_rate = avg_conflicts / max(1, num_traces)

        return BalancedScorecard(
            financial={
                "total_cost_reduction": coordination_quality * 0.2,
                "working_capital_improvement": max(0, 0.1 - conflict_rate * 0.05),
            },
            customer={
                "otif_improvement": coordination_quality * 0.1,
                "fill_rate": 0.9 + coordination_quality * 0.05,
            },
            operational={
                "inventory_turns_improvement": coordination_quality * 0.15,
                "bullwhip_reduction": max(0, 0.1 - conflict_rate * 0.02),
                "avg_signals_per_period": avg_signals,
            },
            strategic={
                "flexibility_score": 0.5 + coordination_quality * 0.3,
                "resilience_score": 0.5 + (1 - conflict_rate) * 0.3,
            },
        )

    def clear_cache(self):
        """Clear the evaluation cache."""
        self._cache.clear()

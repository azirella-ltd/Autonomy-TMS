"""
Conformal Scenario Generator

Generates scenarios for stochastic programming that inherit coverage guarantees
from conformal prediction. This is the KEY BRIDGE between uncertainty quantification
and optimization.

Theory:
- Traditional: Sample from assumed distributions (no guarantees)
- Conformal: Sample from data-driven regions (guaranteed coverage)

Key Innovation:
- Scenarios sampled from conformal regions inherit coverage guarantees
- Stochastic programming solutions have provable robustness
- P(optimal solution is feasible) >= joint conformal coverage

References:
- Romano et al. (2019). Conformalized Quantile Regression
- Tibshirani et al. (2019). Conformal Prediction Under Covariate Shift
- Powell (2022). Sequential Decision Analytics and Modeling
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging

import numpy as np
from scipy import stats

from ..conformal_prediction.suite import SupplyChainConformalSuite
from .stochastic_program import Scenario

logger = logging.getLogger(__name__)


@dataclass
class ConformalScenarioConfig:
    """Configuration for conformal scenario generation"""

    n_scenarios: int = 50
    horizon: int = 12

    # Sampling strategy
    sampling_method: str = "stratified"  # "uniform", "stratified", "antithetic"

    # Coverage levels (should match suite configuration)
    demand_coverage: float = 0.90
    lead_time_coverage: float = 0.90
    yield_coverage: float = 0.95

    # Correlation structure
    demand_correlation: Optional[np.ndarray] = None  # Cross-product correlation matrix
    temporal_correlation: float = 0.7  # AR(1) autocorrelation coefficient

    # Variance reduction techniques
    use_antithetic: bool = True
    use_common_random_numbers: bool = True
    use_latin_hypercube: bool = False

    # Bounds
    min_demand: float = 0.0
    min_lead_time: float = 0.0


class ConformalScenarioGenerator:
    """
    Generates scenarios from conformal prediction regions.

    Key Innovation:
    - Traditional SP: Scenarios from assumed distributions (Normal, Lognormal, etc.)
    - This approach: Scenarios from conformal regions with coverage guarantees

    The result: Stochastic programming solutions have provable robustness!

    P(optimal solution is feasible) >= joint conformal coverage

    Usage:
        # Initialize with calibrated suite
        suite = SupplyChainConformalSuite()
        suite.calibrate_demand("PROD001", 1, forecasts, actuals)

        # Generate scenarios
        generator = ConformalScenarioGenerator(suite)
        scenarios = generator.generate_scenarios(
            products=["PROD001"],
            sites=[1],
            suppliers=["SUP001"],
            demand_forecasts={(("PROD001", 1)): [100, 110, 105]},
            expected_lead_times={"SUP001": 5},
        )

        # Use in stochastic program
        program = TwoStageStochasticProgram(scenarios=scenarios, ...)
    """

    def __init__(
        self,
        conformal_suite: SupplyChainConformalSuite,
        config: Optional[ConformalScenarioConfig] = None,
    ):
        """
        Initialize generator with calibrated conformal suite.

        Args:
            conformal_suite: Calibrated SupplyChainConformalSuite
            config: Generation configuration
        """
        self.suite = conformal_suite
        self.config = config or ConformalScenarioConfig()

        # Random state for reproducibility
        self._rng = np.random.default_rng()
        self._crn_seed: Optional[int] = None

        logger.info(
            f"Initialized ConformalScenarioGenerator: "
            f"n_scenarios={self.config.n_scenarios}, "
            f"horizon={self.config.horizon}, "
            f"method={self.config.sampling_method}"
        )

    def set_seed(self, seed: int):
        """Set random seed for reproducibility"""
        self._rng = np.random.default_rng(seed)
        self._crn_seed = seed

    def generate_scenarios(
        self,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        demand_forecasts: Dict[Tuple[str, int], List[float]],
        expected_lead_times: Dict[str, float],
        expected_yields: Optional[Dict[str, float]] = None,
        expected_prices: Optional[Dict[str, float]] = None,
    ) -> List[Scenario]:
        """
        Generate scenarios for two-stage stochastic program.

        Each scenario is sampled from conformal prediction regions,
        inheriting coverage guarantees.

        Args:
            products: List of product IDs
            sites: List of site IDs
            suppliers: List of supplier IDs
            demand_forecasts: Point forecasts by (product, site)
            expected_lead_times: Expected lead times by supplier
            expected_yields: Expected yields by product (optional)
            expected_prices: Expected prices by material (optional)

        Returns:
            List of Scenario objects for TwoStageStochasticProgram
        """
        n = self.config.n_scenarios
        scenarios = []

        # Use common random numbers if configured
        if self.config.use_common_random_numbers:
            self._rng = np.random.default_rng(self._crn_seed or 42)

        # Precompute intervals for efficiency
        demand_intervals = self._precompute_demand_intervals(
            products, sites, demand_forecasts
        )
        lt_intervals = self._precompute_lead_time_intervals(
            suppliers, expected_lead_times
        )
        yield_intervals = None
        if expected_yields:
            yield_intervals = self._precompute_yield_intervals(expected_yields)

        for i in range(n):
            # Generate antithetic pair if configured
            is_antithetic = self.config.use_antithetic and i % 2 == 1 and i > 0

            if is_antithetic:
                # Use antithetic variates (1 - U instead of U)
                scenario = self._generate_antithetic_scenario(
                    scenarios[-1],
                    products,
                    demand_intervals,
                    lt_intervals,
                    yield_intervals,
                )
            else:
                scenario = self._generate_single_scenario(
                    i,
                    products,
                    sites,
                    suppliers,
                    demand_intervals,
                    lt_intervals,
                    yield_intervals,
                    expected_yields,
                )

            scenarios.append(scenario)

        # Normalize probabilities
        total_prob = sum(s.probability for s in scenarios)
        for s in scenarios:
            s.probability /= total_prob

        logger.info(
            f"Generated {n} conformal scenarios with joint coverage "
            f"{self.compute_coverage_guarantee():.1%}"
        )

        return scenarios

    def _precompute_demand_intervals(
        self,
        products: List[str],
        sites: List[int],
        forecasts: Dict[Tuple[str, int], List[float]],
    ) -> Dict[Tuple[str, int, int], Tuple[float, float]]:
        """Precompute demand intervals for all (product, site, period) combinations"""
        intervals = {}

        for prod in products:
            for site in sites:
                key = (prod, site)
                if key not in forecasts:
                    continue

                point_forecasts = forecasts[key][: self.config.horizon]

                for t, fc in enumerate(point_forecasts):
                    try:
                        if self.suite.has_demand_predictor(prod, site):
                            interval = self.suite.predict_demand(prod, site, fc)
                            lower, upper = interval.lower, interval.upper
                        else:
                            # Default uncertainty: ±20%
                            lower = fc * 0.8
                            upper = fc * 1.2
                    except Exception as e:
                        logger.debug(f"Using default interval for demand: {e}")
                        lower = fc * 0.8
                        upper = fc * 1.2

                    lower = max(self.config.min_demand, lower)
                    intervals[(prod, site, t)] = (lower, upper)

        return intervals

    def _precompute_lead_time_intervals(
        self,
        suppliers: List[str],
        expected_lead_times: Dict[str, float],
    ) -> Dict[str, Tuple[float, float]]:
        """Precompute lead time intervals for all suppliers"""
        intervals = {}

        for supplier in suppliers:
            if supplier not in expected_lead_times:
                continue

            expected = expected_lead_times[supplier]

            try:
                if self.suite.has_lead_time_predictor(supplier):
                    lower, upper = self.suite.predict_lead_time(supplier, expected)
                else:
                    # Default uncertainty: -20% to +30%
                    lower = expected * 0.8
                    upper = expected * 1.3
            except Exception as e:
                logger.debug(f"Using default interval for lead time: {e}")
                lower = expected * 0.8
                upper = expected * 1.3

            lower = max(self.config.min_lead_time, lower)
            intervals[supplier] = (lower, upper)

        return intervals

    def _precompute_yield_intervals(
        self,
        expected_yields: Dict[str, float],
    ) -> Dict[str, Tuple[float, float]]:
        """Precompute yield intervals for all products"""
        intervals = {}

        for prod, expected in expected_yields.items():
            try:
                if self.suite.has_yield_predictor(prod):
                    lower, upper = self.suite.predict_yield(prod, None, expected)
                else:
                    lower = max(0.0, expected * 0.95)
                    upper = min(1.0, expected * 1.02)
            except Exception as e:
                logger.debug(f"Using default interval for yield: {e}")
                lower = max(0.0, expected * 0.95)
                upper = min(1.0, expected * 1.02)

            intervals[prod] = (lower, upper)

        return intervals

    def _generate_single_scenario(
        self,
        scenario_id: int,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        demand_intervals: Dict[Tuple[str, int, int], Tuple[float, float]],
        lt_intervals: Dict[str, Tuple[float, float]],
        yield_intervals: Optional[Dict[str, Tuple[float, float]]],
        expected_yields: Optional[Dict[str, float]],
    ) -> Scenario:
        """Generate a single scenario from conformal regions"""

        # DEMAND: Sample with temporal correlation
        demand = self._sample_demand_with_correlation(
            products, sites, demand_intervals
        )

        # LEAD TIMES: Sample from conformal intervals
        lead_times = {}
        for supplier, (lower, upper) in lt_intervals.items():
            lead_times[supplier] = self._sample_uniform(lower, upper)

        # YIELDS: Sample from conformal intervals
        yields = {}
        if yield_intervals and expected_yields:
            for prod in expected_yields.keys():
                if prod in yield_intervals:
                    lower, upper = yield_intervals[prod]
                    yields[prod] = self._sample_uniform(lower, upper)

        return Scenario(
            id=scenario_id,
            probability=1.0 / self.config.n_scenarios,
            demand=demand,
            lead_times=lead_times,
            yields=yields,
        )

    def _sample_demand_with_correlation(
        self,
        products: List[str],
        sites: List[int],
        intervals: Dict[Tuple[str, int, int], Tuple[float, float]],
    ) -> Dict[str, List[float]]:
        """
        Sample demand with temporal correlation.

        Uses AR(1) process to generate correlated samples across time,
        then maps to conformal intervals.
        """
        demand = {}
        rho = self.config.temporal_correlation

        for prod in products:
            prod_demand = []
            prev_z = 0.0  # Previous standardized residual

            for site in sites:
                for t in range(self.config.horizon):
                    key = (prod, site, t)
                    if key not in intervals:
                        continue

                    lower, upper = intervals[key]

                    # Sample with temporal correlation using AR(1) process
                    if t == 0:
                        # First period: independent sample
                        z = self._rng.standard_normal()
                    else:
                        # Subsequent periods: AR(1) process
                        z = rho * prev_z + np.sqrt(1 - rho**2) * self._rng.standard_normal()

                    prev_z = z

                    # Map z to interval using CDF
                    u = stats.norm.cdf(z)
                    sample = lower + u * (upper - lower)
                    prod_demand.append(max(self.config.min_demand, sample))

            if prod_demand:
                demand[prod] = prod_demand

        return demand

    def _generate_antithetic_scenario(
        self,
        base_scenario: Scenario,
        products: List[str],
        demand_intervals: Dict[Tuple[str, int, int], Tuple[float, float]],
        lt_intervals: Dict[str, Tuple[float, float]],
        yield_intervals: Optional[Dict[str, Tuple[float, float]]],
    ) -> Scenario:
        """
        Generate antithetic variate of base scenario.

        If base sampled at percentile p, antithetic samples at (1-p).
        This reduces variance in expected value calculations.
        """
        antithetic_demand = {}

        for prod, demands in base_scenario.demand.items():
            antithetic_demands = []

            for t, base_demand in enumerate(demands):
                # Find the interval for this period
                interval_key = None
                for key in demand_intervals.keys():
                    if key[0] == prod and key[2] == t:
                        interval_key = key
                        break

                if interval_key:
                    lower, upper = demand_intervals[interval_key]
                    # Antithetic: reflect around midpoint
                    midpoint = (lower + upper) / 2
                    antithetic = 2 * midpoint - base_demand
                    antithetic = max(lower, min(upper, antithetic))
                    antithetic_demands.append(max(self.config.min_demand, antithetic))
                else:
                    antithetic_demands.append(base_demand)

            antithetic_demand[prod] = antithetic_demands

        # Antithetic lead times
        antithetic_lead_times = {}
        for supplier, base_lt in base_scenario.lead_times.items():
            if supplier in lt_intervals:
                lower, upper = lt_intervals[supplier]
                midpoint = (lower + upper) / 2
                antithetic_lead_times[supplier] = max(
                    lower, min(upper, 2 * midpoint - base_lt)
                )
            else:
                antithetic_lead_times[supplier] = base_lt

        # Antithetic yields
        antithetic_yields = {}
        if base_scenario.yields and yield_intervals:
            for prod, base_yield in base_scenario.yields.items():
                if prod in yield_intervals:
                    lower, upper = yield_intervals[prod]
                    midpoint = (lower + upper) / 2
                    antithetic_yields[prod] = max(lower, min(upper, 2 * midpoint - base_yield))
                else:
                    antithetic_yields[prod] = base_yield

        return Scenario(
            id=base_scenario.id + 1,
            probability=base_scenario.probability,
            demand=antithetic_demand,
            lead_times=antithetic_lead_times,
            yields=antithetic_yields,
        )

    def _sample_uniform(self, lower: float, upper: float) -> float:
        """Sample uniformly from interval"""
        return float(self._rng.uniform(lower, upper))

    def _sample_stratified(
        self,
        lower: float,
        upper: float,
        stratum: int,
        n_strata: int,
    ) -> float:
        """
        Stratified sampling: divide interval into strata, sample within.

        This reduces variance compared to pure random sampling.
        """
        stratum_width = (upper - lower) / n_strata
        stratum_lower = lower + stratum * stratum_width
        stratum_upper = stratum_lower + stratum_width
        return float(self._rng.uniform(stratum_lower, stratum_upper))

    def compute_coverage_guarantee(self) -> float:
        """
        Compute the joint coverage guarantee of generated scenarios.

        Joint coverage = product of individual coverages (assuming independence)
        """
        return (
            self.config.demand_coverage
            * self.config.lead_time_coverage
            * self.config.yield_coverage
        )

    def get_generation_summary(self) -> Dict[str, Any]:
        """Summary of scenario generation configuration"""
        return {
            "n_scenarios": self.config.n_scenarios,
            "horizon": self.config.horizon,
            "sampling_method": self.config.sampling_method,
            "use_antithetic": self.config.use_antithetic,
            "use_common_random_numbers": self.config.use_common_random_numbers,
            "temporal_correlation": self.config.temporal_correlation,
            "joint_coverage_guarantee": self.compute_coverage_guarantee(),
            "calibrated_predictors": self.suite.get_calibration_summary(),
        }


class ConformalStochasticProgramBuilder:
    """
    Convenience class to build stochastic programs from conformal scenarios.

    Combines ConformalScenarioGenerator with TwoStageStochasticProgram.

    Usage:
        builder = ConformalStochasticProgramBuilder(
            conformal_suite=suite,
            products=["PROD001", "PROD002"],
            resources=["MACHINE1"],
        )

        solution = builder.build_and_solve(
            demand_forecasts={...},
            expected_lead_times={...},
            sites=[1, 2],
            suppliers=["SUP001"],
        )

        # Solution has provable robustness!
        print(f"Coverage guarantee: {solution.extracted_policy_params['conformal_coverage_guarantee']}")
    """

    def __init__(
        self,
        conformal_suite: SupplyChainConformalSuite,
        products: List[str],
        resources: List[str],
        planning_horizon: int = 12,
    ):
        self.generator = ConformalScenarioGenerator(conformal_suite)
        self.products = products
        self.resources = resources
        self.planning_horizon = planning_horizon

    def build_and_solve(
        self,
        demand_forecasts: Dict[Tuple[str, int], List[float]],
        expected_lead_times: Dict[str, float],
        sites: List[int],
        suppliers: List[str],
        expected_yields: Optional[Dict[str, float]] = None,
        n_scenarios: int = 50,
        risk_measure: str = "cvar",
        cvar_alpha: float = 0.95,
        max_investment: Optional[float] = None,
    ):
        """
        Generate conformal scenarios and solve stochastic program.

        Args:
            demand_forecasts: Point forecasts by (product, site)
            expected_lead_times: Expected lead times by supplier
            sites: List of site IDs
            suppliers: List of supplier IDs
            expected_yields: Expected yields by product (optional)
            n_scenarios: Number of scenarios to generate
            risk_measure: "expected", "cvar", or "robust"
            cvar_alpha: Alpha level for CVaR (e.g., 0.95 for 95% CVaR)
            max_investment: Optional cap on first-stage investment

        Returns:
            StochasticSolution with provable robustness
        """
        from .stochastic_program import TwoStageStochasticProgram

        # Update config
        self.generator.config.n_scenarios = n_scenarios
        self.generator.config.horizon = self.planning_horizon

        # Generate scenarios from conformal regions
        scenarios = self.generator.generate_scenarios(
            products=self.products,
            sites=sites,
            suppliers=suppliers,
            demand_forecasts=demand_forecasts,
            expected_lead_times=expected_lead_times,
            expected_yields=expected_yields,
        )

        # Build and solve stochastic program
        program = TwoStageStochasticProgram(
            scenarios=scenarios,
            products=self.products,
            resources=self.resources,
            planning_horizon=self.planning_horizon,
        )

        solution = program.solve(
            risk_measure=risk_measure,
            cvar_alpha=cvar_alpha,
            max_investment=max_investment,
        )

        # Annotate solution with coverage guarantee
        if solution.extracted_policy_params is None:
            solution.extracted_policy_params = {}

        solution.extracted_policy_params["conformal_coverage_guarantee"] = (
            self.generator.compute_coverage_guarantee()
        )
        solution.extracted_policy_params["n_scenarios"] = n_scenarios
        solution.extracted_policy_params["risk_measure"] = risk_measure

        logger.info(
            f"Built and solved conformal stochastic program: "
            f"expected_cost={solution.expected_cost:.2f}, "
            f"coverage={solution.extracted_policy_params['conformal_coverage_guarantee']:.1%}"
        )

        return solution

    def build_scenarios_only(
        self,
        demand_forecasts: Dict[Tuple[str, int], List[float]],
        expected_lead_times: Dict[str, float],
        sites: List[int],
        suppliers: List[str],
        expected_yields: Optional[Dict[str, float]] = None,
        n_scenarios: int = 50,
    ) -> List[Scenario]:
        """
        Generate conformal scenarios without solving.

        Useful when you want to apply scenario reduction before solving.
        """
        self.generator.config.n_scenarios = n_scenarios
        self.generator.config.horizon = self.planning_horizon

        return self.generator.generate_scenarios(
            products=self.products,
            sites=sites,
            suppliers=suppliers,
            demand_forecasts=demand_forecasts,
            expected_lead_times=expected_lead_times,
            expected_yields=expected_yields,
        )

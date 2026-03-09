# Implementation Prompt: Conformal Prediction & Stochastic Programming Integration

## Executive Summary

**Objective**: Complete the integration between Conformal Prediction (CP) and Stochastic Programming (SP) to achieve Powell's vision of "a supply chain planning system where uncertainty is rigorously quantified (conformal), decisions explicitly account for uncertainty (stochastic programming), and the whole system improves as it observes outcomes (adaptive conformal + policy learning)."

**Current Status**: ~80% complete
- Part 1 (Conformal Prediction): 6 complete, 2 partial
- Part 2 (Stochastic Programming): 5 complete, 1 partial, 3 not implemented
- Orchestration Layer (Gap 6): Complete — automatic feedback loop wiring all components

**Estimated Effort**: 10-15 weeks (parallelizable to ~8 weeks with 2 developers)

---

## Context: What's Already Implemented

### Conformal Prediction (Complete)

**Location**: `backend/app/services/conformal_prediction/`

| File | Description | Key Classes |
|------|-------------|-------------|
| `engine.py` | Core CP engine with coverage guarantees | `ConformalPredictionEngine`, `PredictionInterval`, `CoverageStats`, `MultiTargetConformalEngine` |
| `predictors.py` | Specialized predictors | `SplitConformalPredictor`, `QuantileConformalPredictor`, `AdaptiveConformalPredictor`, `ATPConformalPredictor`, `DemandConformalPredictor`, `LeadTimeConformalPredictor` |
| `calibration.py` | Calibration storage | `CalibrationStore` |

**Also**: `backend/app/services/conformal_prediction.py` contains `ConformalDecisionMaker` with `calculate_safety_stock()` method.

### Stochastic Programming (Complete)

**Location**: `backend/app/services/powell/`

| File | Description | Key Classes |
|------|-------------|-------------|
| `stochastic_program.py` | Two-stage SP using CVXPY | `TwoStageStochasticProgram`, `Scenario`, `StochasticSolution`, `compute_expected_value_of_perfect_information()`, `compute_value_of_stochastic_solution()` |
| `mpc_planner.py` | Model Predictive Control (Powell's DLA) | `MPCSupplyPlanner`, `MPCState`, `MPCForecast`, `MPCDecision` |
| `belief_state.py` | Powell belief state | `PowellBeliefState` |
| `policy_optimizer.py` | Policy optimization | Various policy classes |

### Planning Services (Integration Points)

**Location**: `backend/app/services/sc_planning/`

| File | Description |
|------|-------------|
| `planner.py` | Main 3-step orchestrator |
| `inventory_target_calculator.py` | Current safety stock calculation (4 policy types: abs_level, doc_dem, doc_fcst, sl) |
| `demand_processor.py` | Demand aggregation |
| `net_requirements_calculator.py` | Supply plan generation |

---

## Gap 1: SupplyChainConformalSuite (1-2 weeks)

### Objective
Create a unified suite managing demand, lead_time, yield, and price conformal predictors with joint uncertainty scenarios.

### Specification

**New File**: `backend/app/services/conformal_prediction/suite.py`

```python
"""
Supply Chain Conformal Suite

Unified management of multiple conformal predictors for joint uncertainty quantification.
Enables generation of scenarios from conformal regions with guaranteed coverage.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import numpy as np

from .engine import ConformalPredictionEngine, PredictionInterval
from .predictors import (
    DemandConformalPredictor,
    LeadTimeConformalPredictor,
    AdaptiveConformalPredictor,
    SplitConformalPredictor,
)


@dataclass
class JointUncertaintyScenario:
    """
    A scenario sampled from joint conformal prediction regions.

    Attributes:
        scenario_id: Unique identifier
        probability: Scenario probability (for stochastic programming)
        demand: Dict[product_id, List[float]] - demand by product by period
        lead_times: Dict[supplier_id, float] - lead time by supplier
        yields: Dict[product_id, float] - yield percentage by product
        prices: Dict[product_id, float] - price by product
        coverage_guarantee: Joint coverage guarantee (product of individual coverages)
    """
    scenario_id: int
    probability: float
    demand: Dict[str, List[float]]
    lead_times: Dict[str, float]
    yields: Dict[str, float]
    prices: Dict[str, float]
    coverage_guarantee: float

    def to_stochastic_scenario(self) -> "Scenario":
        """Convert to stochastic programming Scenario format"""
        from ..powell.stochastic_program import Scenario
        return Scenario(
            id=self.scenario_id,
            probability=self.probability,
            demand=self.demand,
            lead_times=self.lead_times,
            yields=self.yields,
        )


class YieldConformalPredictor:
    """
    Conformal predictor for production yields.

    Yields are typically high (90-99%) with occasional failures.
    Uses bounded intervals [0, 1].
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(
            target="yield",
            coverage=coverage,
        )
        self._calibrated = False

    def calibrate(
        self,
        expected_yields: List[float],
        actual_yields: List[float],
        product_id: Optional[str] = None,
    ):
        """Calibrate from historical expected vs actual yields"""
        self.predictor.calibrate_from_history(expected_yields, actual_yields)
        self._calibrated = True

    def predict(self, expected_yield: float) -> Tuple[float, float]:
        """
        Predict yield interval.

        Returns:
            (lower_bound, upper_bound) bounded to [0, 1]
        """
        interval = self.predictor.predict(expected_yield)
        return (
            max(0.0, interval.lower),
            min(1.0, interval.upper)
        )


class PriceConformalPredictor:
    """
    Conformal predictor for prices (raw materials, commodities).

    Prices are non-negative with potentially high volatility.
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = AdaptiveConformalPredictor(
            target="price",
            coverage=coverage,
            gamma=0.01,  # Higher gamma for volatile prices
        )
        self._calibrated = False

    def calibrate(
        self,
        predicted_prices: List[float],
        actual_prices: List[float],
    ):
        """Calibrate from historical price predictions"""
        for pred, actual in zip(predicted_prices, actual_prices):
            self.predictor.update_and_predict(pred, actual)
        self._calibrated = True

    def predict(self, expected_price: float) -> PredictionInterval:
        """Predict price interval (non-negative)"""
        interval = self.predictor.update_and_predict(expected_price)
        interval.lower = max(0.0, interval.lower)
        return interval


class SupplyChainConformalSuite:
    """
    Unified suite for supply chain conformal prediction.

    Manages calibration and prediction for:
    - Demand forecasts (per product, per site)
    - Lead times (per supplier, per transportation lane)
    - Yields (per product, per production process)
    - Prices (per raw material)

    Enables:
    - Individual prediction intervals with coverage guarantees
    - Joint uncertainty scenarios for stochastic programming
    - Automatic recalibration triggers
    """

    def __init__(
        self,
        demand_coverage: float = 0.90,
        lead_time_coverage: float = 0.90,
        yield_coverage: float = 0.95,  # Higher coverage for yields (critical)
        price_coverage: float = 0.90,
    ):
        self.demand_coverage = demand_coverage
        self.lead_time_coverage = lead_time_coverage
        self.yield_coverage = yield_coverage
        self.price_coverage = price_coverage

        # Predictor registries keyed by (product_id, site_id) or similar
        self._demand_predictors: Dict[str, DemandConformalPredictor] = {}
        self._lead_time_predictors: Dict[str, LeadTimeConformalPredictor] = {}
        self._yield_predictors: Dict[str, YieldConformalPredictor] = {}
        self._price_predictors: Dict[str, PriceConformalPredictor] = {}

        # Calibration timestamps for staleness detection
        self._calibration_timestamps: Dict[str, datetime] = {}

    def _get_key(self, *args) -> str:
        """Generate registry key from identifiers"""
        return ":".join(str(a) for a in args if a is not None)

    # =========================================================================
    # Demand Prediction
    # =========================================================================

    def calibrate_demand(
        self,
        product_id: str,
        site_id: int,
        historical_forecasts: List[float],
        historical_actuals: List[float],
    ):
        """Calibrate demand predictor for product-site combination"""
        key = self._get_key("demand", product_id, site_id)
        predictor = DemandConformalPredictor(
            coverage=self.demand_coverage,
            use_adaptive=True,
        )
        # Initialize calibration
        for pred, actual in zip(historical_forecasts, historical_actuals):
            predictor.predict(pred, actual)

        self._demand_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_demand(
        self,
        product_id: str,
        site_id: int,
        point_forecast: float,
    ) -> PredictionInterval:
        """Get demand prediction interval"""
        key = self._get_key("demand", product_id, site_id)
        if key not in self._demand_predictors:
            raise ValueError(f"No calibrated demand predictor for {key}")
        return self._demand_predictors[key].predict(point_forecast)

    # =========================================================================
    # Lead Time Prediction
    # =========================================================================

    def calibrate_lead_time(
        self,
        supplier_id: str,
        predicted_lead_times: List[float],
        actual_lead_times: List[float],
    ):
        """Calibrate lead time predictor for supplier"""
        key = self._get_key("lead_time", supplier_id)
        predictor = LeadTimeConformalPredictor(coverage=self.lead_time_coverage)
        predictor.calibrate(predicted_lead_times, actual_lead_times)

        self._lead_time_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_lead_time(
        self,
        supplier_id: str,
        expected_lead_time: float,
    ) -> Tuple[float, float]:
        """Get lead time prediction interval"""
        key = self._get_key("lead_time", supplier_id)
        if key not in self._lead_time_predictors:
            raise ValueError(f"No calibrated lead time predictor for {key}")
        return self._lead_time_predictors[key].predict_arrival_window(expected_lead_time)

    # =========================================================================
    # Yield Prediction
    # =========================================================================

    def calibrate_yield(
        self,
        product_id: str,
        process_id: Optional[str],
        expected_yields: List[float],
        actual_yields: List[float],
    ):
        """Calibrate yield predictor for product-process combination"""
        key = self._get_key("yield", product_id, process_id)
        predictor = YieldConformalPredictor(coverage=self.yield_coverage)
        predictor.calibrate(expected_yields, actual_yields, product_id)

        self._yield_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_yield(
        self,
        product_id: str,
        process_id: Optional[str],
        expected_yield: float,
    ) -> Tuple[float, float]:
        """Get yield prediction interval"""
        key = self._get_key("yield", product_id, process_id)
        if key not in self._yield_predictors:
            # Fallback: conservative estimate
            return (expected_yield * 0.9, min(1.0, expected_yield * 1.05))
        return self._yield_predictors[key].predict(expected_yield)

    # =========================================================================
    # Price Prediction
    # =========================================================================

    def calibrate_price(
        self,
        material_id: str,
        predicted_prices: List[float],
        actual_prices: List[float],
    ):
        """Calibrate price predictor for raw material"""
        key = self._get_key("price", material_id)
        predictor = PriceConformalPredictor(coverage=self.price_coverage)
        predictor.calibrate(predicted_prices, actual_prices)

        self._price_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_price(
        self,
        material_id: str,
        expected_price: float,
    ) -> PredictionInterval:
        """Get price prediction interval"""
        key = self._get_key("price", material_id)
        if key not in self._price_predictors:
            raise ValueError(f"No calibrated price predictor for {key}")
        return self._price_predictors[key].predict(expected_price)

    # =========================================================================
    # Joint Uncertainty Scenarios
    # =========================================================================

    def generate_joint_scenarios(
        self,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        demand_forecasts: Dict[Tuple[str, int], List[float]],  # (product, site) -> [demand by period]
        expected_lead_times: Dict[str, float],  # supplier -> lead time
        expected_yields: Optional[Dict[str, float]] = None,  # product -> yield
        n_scenarios: int = 20,
        horizon: int = 12,
    ) -> List[JointUncertaintyScenario]:
        """
        Generate scenarios sampled from conformal prediction regions.

        This is the KEY INTEGRATION POINT with stochastic programming.
        Scenarios inherit coverage guarantees from conformal predictors.

        Args:
            products: List of product IDs
            sites: List of site IDs
            suppliers: List of supplier IDs
            demand_forecasts: Point forecasts by (product, site)
            expected_lead_times: Expected lead times by supplier
            expected_yields: Expected yields by product (optional)
            n_scenarios: Number of scenarios to generate
            horizon: Planning horizon (periods)

        Returns:
            List of JointUncertaintyScenario with coverage guarantees
        """
        scenarios = []

        # Calculate joint coverage (product of individual coverages)
        joint_coverage = (
            self.demand_coverage *
            self.lead_time_coverage *
            (self.yield_coverage if expected_yields else 1.0)
        )

        for i in range(n_scenarios):
            # Sample demand scenarios
            demand = {}
            for (prod, site), forecasts in demand_forecasts.items():
                key = self._get_key("demand", prod, site)

                if key in self._demand_predictors:
                    # Sample from conformal region
                    sampled_demand = []
                    for fc in forecasts[:horizon]:
                        interval = self._demand_predictors[key].predict(fc)
                        # Sample uniformly from interval (conservative)
                        sample = np.random.uniform(interval.lower, interval.upper)
                        sampled_demand.append(max(0, sample))
                    demand[prod] = sampled_demand
                else:
                    # Fallback: add noise to point forecast
                    demand[prod] = [
                        max(0, fc * np.random.lognormal(0, 0.2))
                        for fc in forecasts[:horizon]
                    ]

            # Sample lead times
            lead_times = {}
            for supplier, lt in expected_lead_times.items():
                key = self._get_key("lead_time", supplier)

                if key in self._lead_time_predictors:
                    lower, upper = self._lead_time_predictors[key].predict_arrival_window(lt)
                    lead_times[supplier] = np.random.uniform(lower, upper)
                else:
                    lead_times[supplier] = lt * np.random.uniform(0.8, 1.3)

            # Sample yields
            yields = {}
            if expected_yields:
                for prod, expected_yield in expected_yields.items():
                    key = self._get_key("yield", prod, None)

                    if key in self._yield_predictors:
                        lower, upper = self._yield_predictors[key].predict(expected_yield)
                        yields[prod] = np.random.uniform(lower, upper)
                    else:
                        yields[prod] = expected_yield * np.random.uniform(0.95, 1.0)

            scenarios.append(JointUncertaintyScenario(
                scenario_id=i,
                probability=1.0 / n_scenarios,
                demand=demand,
                lead_times=lead_times,
                yields=yields,
                prices={},  # Extend if price predictors calibrated
                coverage_guarantee=joint_coverage,
            ))

        return scenarios

    # =========================================================================
    # Diagnostics & Monitoring
    # =========================================================================

    def get_calibration_summary(self) -> Dict[str, Any]:
        """Get summary of all calibrated predictors"""
        return {
            "demand_predictors": len(self._demand_predictors),
            "lead_time_predictors": len(self._lead_time_predictors),
            "yield_predictors": len(self._yield_predictors),
            "price_predictors": len(self._price_predictors),
            "coverage_targets": {
                "demand": self.demand_coverage,
                "lead_time": self.lead_time_coverage,
                "yield": self.yield_coverage,
                "price": self.price_coverage,
            },
            "calibration_timestamps": {
                k: v.isoformat() for k, v in self._calibration_timestamps.items()
            },
        }

    def check_recalibration_needed(
        self,
        max_age_hours: int = 168,  # 1 week
    ) -> List[str]:
        """Identify predictors that need recalibration"""
        stale = []
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        for key, timestamp in self._calibration_timestamps.items():
            if timestamp < cutoff:
                stale.append(key)

        return stale
```

### Integration Points

1. **Update `__init__.py`** in `conformal_prediction/`:
```python
from .suite import SupplyChainConformalSuite, JointUncertaintyScenario
```

2. **Add API endpoint** in `backend/app/api/endpoints/conformal_prediction.py`:
```python
@router.post("/suite/calibrate")
async def calibrate_suite(...)

@router.get("/suite/scenarios")
async def generate_scenarios(...)
```

### Acceptance Criteria

- [ ] All 4 predictor types (demand, lead_time, yield, price) can be calibrated independently
- [ ] `generate_joint_scenarios()` produces scenarios compatible with `TwoStageStochasticProgram`
- [ ] Joint coverage guarantee is correctly computed
- [ ] Stale calibration detection works
- [ ] Unit tests cover individual predictors and joint scenario generation

---

## Gap 2: ConformalScenarioGenerator (3-4 weeks)

### Objective
Replace Monte Carlo scenario generation with conformal-region-based sampling that inherits coverage guarantees.

### Specification

**New File**: `backend/app/services/powell/conformal_scenario_generator.py`

```python
"""
Conformal Scenario Generator

Generates scenarios for stochastic programming that inherit coverage guarantees
from conformal prediction. This is the KEY BRIDGE between uncertainty quantification
and optimization.

Theory:
- Traditional: Sample from assumed distributions (no guarantees)
- Conformal: Sample from data-driven regions (guaranteed coverage)

References:
- Romano et al. (2019). Conformalized Quantile Regression
- Tibshirani et al. (2019). Conformal Prediction Under Covariate Shift
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import datetime
import numpy as np
from scipy import stats

from ..conformal_prediction.suite import SupplyChainConformalSuite, JointUncertaintyScenario
from .stochastic_program import Scenario


@dataclass
class ConformalScenarioConfig:
    """Configuration for conformal scenario generation"""
    n_scenarios: int = 50
    horizon: int = 12

    # Sampling strategy
    sampling_method: str = "stratified"  # "uniform", "stratified", "antithetic"

    # Coverage levels
    demand_coverage: float = 0.90
    lead_time_coverage: float = 0.90
    yield_coverage: float = 0.95

    # Correlation structure (if known)
    demand_correlation: Optional[np.ndarray] = None  # Cross-product correlation
    temporal_correlation: float = 0.7  # Autocorrelation coefficient

    # Variance reduction
    use_antithetic: bool = True
    use_common_random_numbers: bool = True


class ConformalScenarioGenerator:
    """
    Generates scenarios from conformal prediction regions.

    Key Innovation:
    - Traditional SP: Scenarios from assumed distributions (Normal, Lognormal, etc.)
    - This approach: Scenarios from conformal regions with coverage guarantees

    The result: Stochastic programming solutions have provable robustness!

    P(optimal solution is feasible) >= joint conformal coverage
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
        self._crn_seed = None  # Common random numbers seed

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
            expected_yields: Expected yields by product
            expected_prices: Expected prices by material

        Returns:
            List of Scenario objects for TwoStageStochasticProgram
        """
        n = self.config.n_scenarios
        scenarios = []

        # Use common random numbers if configured
        if self.config.use_common_random_numbers:
            self._rng = np.random.default_rng(self._crn_seed or 42)

        for i in range(n):
            # Generate antithetic pair if configured
            is_antithetic = self.config.use_antithetic and i % 2 == 1 and i > 0

            if is_antithetic:
                # Use antithetic variates (1 - U instead of U)
                scenario = self._generate_antithetic_scenario(
                    scenarios[-1], products, sites, demand_forecasts
                )
            else:
                scenario = self._generate_single_scenario(
                    i, products, sites, suppliers,
                    demand_forecasts, expected_lead_times,
                    expected_yields, expected_prices
                )

            scenarios.append(scenario)

        # Normalize probabilities
        total_prob = sum(s.probability for s in scenarios)
        for s in scenarios:
            s.probability /= total_prob

        return scenarios

    def _generate_single_scenario(
        self,
        scenario_id: int,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        demand_forecasts: Dict[Tuple[str, int], List[float]],
        expected_lead_times: Dict[str, float],
        expected_yields: Optional[Dict[str, float]],
        expected_prices: Optional[Dict[str, float]],
    ) -> Scenario:
        """Generate a single scenario from conformal regions"""

        # DEMAND: Sample from conformal intervals with temporal correlation
        demand = self._sample_demand_scenarios(
            products, sites, demand_forecasts
        )

        # LEAD TIMES: Sample from conformal intervals
        lead_times = self._sample_lead_time_scenarios(
            suppliers, expected_lead_times
        )

        # YIELDS: Sample from conformal intervals
        yields = {}
        if expected_yields:
            for prod, expected in expected_yields.items():
                lower, upper = self.suite.predict_yield(prod, None, expected)
                yields[prod] = self._sample_uniform(lower, upper)

        # PRICES: Sample from conformal intervals
        prices = {}
        # (Extend when price predictors are available)

        return Scenario(
            id=scenario_id,
            probability=1.0 / self.config.n_scenarios,
            demand=demand,
            lead_times=lead_times,
            yields=yields,
        )

    def _sample_demand_scenarios(
        self,
        products: List[str],
        sites: List[int],
        forecasts: Dict[Tuple[str, int], List[float]],
    ) -> Dict[str, List[float]]:
        """
        Sample demand with temporal correlation.

        Uses the conformal interval at each period, but correlates
        samples across time using the temporal_correlation parameter.
        """
        demand = {}
        rho = self.config.temporal_correlation

        for prod in products:
            prod_demand = []
            prev_z = 0  # Previous standardized residual

            for site in sites:
                key = (prod, site)
                if key not in forecasts:
                    continue

                point_forecasts = forecasts[key][:self.config.horizon]

                for t, fc in enumerate(point_forecasts):
                    try:
                        interval = self.suite.predict_demand(prod, site, fc)
                        lower, upper = interval.lower, interval.upper
                    except ValueError:
                        # No calibrated predictor, use default uncertainty
                        lower = fc * 0.8
                        upper = fc * 1.2

                    # Sample with temporal correlation
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
                    prod_demand.append(max(0, sample))

            if prod_demand:
                demand[prod] = prod_demand

        return demand

    def _sample_lead_time_scenarios(
        self,
        suppliers: List[str],
        expected_lead_times: Dict[str, float],
    ) -> Dict[str, float]:
        """Sample lead times from conformal intervals"""
        lead_times = {}

        for supplier in suppliers:
            if supplier not in expected_lead_times:
                continue

            expected = expected_lead_times[supplier]

            try:
                lower, upper = self.suite.predict_lead_time(supplier, expected)
            except ValueError:
                # No calibrated predictor
                lower = expected * 0.8
                upper = expected * 1.3

            lead_times[supplier] = self._sample_uniform(lower, upper)

        return lead_times

    def _generate_antithetic_scenario(
        self,
        base_scenario: Scenario,
        products: List[str],
        sites: List[int],
        forecasts: Dict[Tuple[str, int], List[float]],
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
                # Find which product-site this came from
                for site in sites:
                    key = (prod, site)
                    if key in forecasts:
                        fc = forecasts[key][t] if t < len(forecasts[key]) else forecasts[key][-1]

                        try:
                            interval = self.suite.predict_demand(prod, site, fc)
                            lower, upper = interval.lower, interval.upper
                        except ValueError:
                            lower = fc * 0.8
                            upper = fc * 1.2

                        # Antithetic: reflect around midpoint
                        midpoint = (lower + upper) / 2
                        antithetic = 2 * midpoint - base_demand
                        antithetic = max(lower, min(upper, antithetic))
                        antithetic_demands.append(max(0, antithetic))
                        break

            antithetic_demand[prod] = antithetic_demands

        # Antithetic lead times
        antithetic_lead_times = {}
        for supplier, base_lt in base_scenario.lead_times.items():
            try:
                lower, upper = self.suite.predict_lead_time(supplier, base_lt)
            except:
                lower = base_lt * 0.8
                upper = base_lt * 1.3

            midpoint = (lower + upper) / 2
            antithetic_lead_times[supplier] = max(lower, min(upper, 2 * midpoint - base_lt))

        return Scenario(
            id=base_scenario.id + 1,
            probability=base_scenario.probability,
            demand=antithetic_demand,
            lead_times=antithetic_lead_times,
            yields={k: 1.0 - (v - 0.95) for k, v in base_scenario.yields.items()}
            if base_scenario.yields else {},
        )

    def _sample_uniform(self, lower: float, upper: float) -> float:
        """Sample uniformly from interval"""
        return self._rng.uniform(lower, upper)

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
        return self._rng.uniform(stratum_lower, stratum_upper)

    def compute_coverage_guarantee(self) -> float:
        """
        Compute the joint coverage guarantee of generated scenarios.

        Joint coverage = product of individual coverages (assuming independence)
        """
        return (
            self.config.demand_coverage *
            self.config.lead_time_coverage *
            self.config.yield_coverage
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
        n_scenarios: int = 50,
        risk_measure: str = "cvar",
        cvar_alpha: float = 0.95,
    ):
        """
        Generate conformal scenarios and solve stochastic program.

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
        )

        # Annotate solution with coverage guarantee
        solution.extracted_policy_params = solution.extracted_policy_params or {}
        solution.extracted_policy_params["conformal_coverage_guarantee"] = \
            self.generator.compute_coverage_guarantee()

        return solution
```

### Integration with Existing Stochastic Program

Update `stochastic_program.py` to support conformal scenarios:

```python
# In TwoStageStochasticProgram.__init__
def __init__(
    self,
    scenarios: List[Scenario],
    products: List[str],
    resources: List[str],
    planning_horizon: int = 12,
    conformal_coverage: Optional[float] = None,  # NEW
):
    ...
    self.conformal_coverage = conformal_coverage
```

### Acceptance Criteria

- [ ] Scenarios sampled from conformal regions (not parametric distributions)
- [ ] Temporal correlation in demand scenarios
- [ ] Antithetic variates for variance reduction
- [ ] Common random numbers support
- [ ] Coverage guarantee correctly propagates to solution
- [ ] Compatible with existing `TwoStageStochasticProgram`
- [ ] Unit tests for sampling methods

---

## Gap 3: Scenario Reduction (2-3 weeks)

### Objective
Implement Wasserstein-based forward selection to reduce 1000+ scenarios to 20-50 while preserving solution quality.

### Specification

**New File**: `backend/app/services/powell/scenario_reduction.py`

```python
"""
Scenario Reduction for Stochastic Programming

Reduces large scenario sets to tractable sizes while preserving
solution quality. Uses Wasserstein distance for scenario selection.

Theory:
- Too many scenarios → computationally intractable
- Too few scenarios → lose coverage guarantees
- Scenario reduction → optimal trade-off

References:
- Heitsch & Römisch (2003). Scenario Reduction Algorithms
- Dupačová, Gröwe-Kuska, Römisch (2003). Scenario Reduction
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment

from .stochastic_program import Scenario


@dataclass
class ScenarioReductionResult:
    """Result of scenario reduction"""
    reduced_scenarios: List[Scenario]
    original_count: int
    reduced_count: int
    wasserstein_error: float
    computation_time: float

    # Mapping: reduced scenario index -> list of original indices it represents
    scenario_mapping: Dict[int, List[int]]


class WassersteinScenarioReducer:
    """
    Reduces scenarios using Wasserstein distance-based forward selection.

    Algorithm (Forward Selection):
    1. Start with empty reduced set
    2. Iteratively add scenario that minimizes Wasserstein distance
    3. Stop when target size reached or error threshold met

    Preserves conformal coverage guarantees better than random sampling.
    """

    def __init__(
        self,
        distance_metric: str = "euclidean",
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize reducer.

        Args:
            distance_metric: Distance metric ("euclidean", "manhattan", "chebyshev")
            weights: Feature weights for distance calculation
        """
        self.distance_metric = distance_metric
        self.weights = weights or {}

    def reduce(
        self,
        scenarios: List[Scenario],
        target_count: int,
        method: str = "forward_selection",
    ) -> ScenarioReductionResult:
        """
        Reduce scenario set to target size.

        Args:
            scenarios: Original scenario list
            target_count: Target number of scenarios
            method: "forward_selection", "backward_reduction", "fast_forward"

        Returns:
            ScenarioReductionResult with reduced scenarios
        """
        import time
        start_time = time.time()

        if len(scenarios) <= target_count:
            return ScenarioReductionResult(
                reduced_scenarios=scenarios,
                original_count=len(scenarios),
                reduced_count=len(scenarios),
                wasserstein_error=0.0,
                computation_time=0.0,
                scenario_mapping={i: [i] for i in range(len(scenarios))},
            )

        # Convert scenarios to feature matrix
        features = self._scenarios_to_features(scenarios)
        probabilities = np.array([s.probability for s in scenarios])

        if method == "forward_selection":
            selected, mapping = self._forward_selection(
                features, probabilities, target_count
            )
        elif method == "backward_reduction":
            selected, mapping = self._backward_reduction(
                features, probabilities, target_count
            )
        elif method == "fast_forward":
            selected, mapping = self._fast_forward_selection(
                features, probabilities, target_count
            )
        else:
            raise ValueError(f"Unknown method: {method}")

        # Create reduced scenario list with updated probabilities
        reduced_scenarios = []
        for i, idx in enumerate(selected):
            scenario = scenarios[idx]
            # Aggregate probability from all scenarios mapped to this one
            aggregated_prob = sum(probabilities[j] for j in mapping[i])
            reduced_scenarios.append(Scenario(
                id=i,
                probability=aggregated_prob,
                demand=scenario.demand,
                lead_times=scenario.lead_times,
                yields=scenario.yields,
                capacities=scenario.capacities,
            ))

        # Compute Wasserstein error
        error = self._compute_wasserstein_error(
            features, probabilities, features[selected],
            np.array([s.probability for s in reduced_scenarios])
        )

        return ScenarioReductionResult(
            reduced_scenarios=reduced_scenarios,
            original_count=len(scenarios),
            reduced_count=len(reduced_scenarios),
            wasserstein_error=error,
            computation_time=time.time() - start_time,
            scenario_mapping={i: mapping[i] for i in range(len(selected))},
        )

    def _scenarios_to_features(self, scenarios: List[Scenario]) -> np.ndarray:
        """
        Convert scenarios to feature matrix for distance calculations.

        Features include:
        - Total demand by product
        - Mean demand by product
        - Lead times
        - Yields
        """
        features = []

        for scenario in scenarios:
            f = []

            # Demand features
            for prod, demands in sorted(scenario.demand.items()):
                f.append(sum(demands))  # Total demand
                f.append(np.mean(demands))  # Mean demand
                f.append(np.std(demands) if len(demands) > 1 else 0)  # Demand variability

            # Lead time features
            for supplier, lt in sorted(scenario.lead_times.items()):
                f.append(lt)

            # Yield features
            for prod, y in sorted(scenario.yields.items()):
                f.append(y)

            features.append(f)

        features = np.array(features)

        # Normalize features
        mean = features.mean(axis=0)
        std = features.std(axis=0)
        std[std == 0] = 1  # Avoid division by zero
        features = (features - mean) / std

        return features

    def _forward_selection(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Forward selection: iteratively add best scenario.

        At each step, add the scenario that most reduces Wasserstein distance
        to the original distribution.
        """
        n = len(features)
        remaining = set(range(n))
        selected = []
        mapping = {}

        # Distance matrix
        distances = cdist(features, features, metric=self.distance_metric)

        while len(selected) < target_count and remaining:
            best_idx = None
            best_error = float('inf')

            for candidate in remaining:
                # Tentatively add candidate
                trial_selected = selected + [candidate]

                # Compute error with this selection
                error = self._compute_selection_error(
                    distances, probabilities, trial_selected, remaining - {candidate}
                )

                if error < best_error:
                    best_error = error
                    best_idx = candidate

            if best_idx is not None:
                selected.append(best_idx)
                remaining.remove(best_idx)

        # Assign remaining scenarios to nearest selected
        mapping = {i: [selected[i]] for i in range(len(selected))}

        for j in range(n):
            if j in selected:
                continue

            # Find nearest selected scenario
            nearest = min(range(len(selected)),
                         key=lambda i: distances[j, selected[i]])
            mapping[nearest].append(j)

        return selected, mapping

    def _fast_forward_selection(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Fast forward selection using k-medoids initialization.

        Much faster than full forward selection for large scenario sets.
        """
        from sklearn.cluster import KMeans

        # Use k-means to find initial clusters
        kmeans = KMeans(n_clusters=target_count, random_state=42, n_init=10)
        labels = kmeans.fit_predict(features)

        # For each cluster, select scenario closest to centroid
        # weighted by probability
        selected = []
        mapping = {i: [] for i in range(target_count)}

        for k in range(target_count):
            cluster_indices = np.where(labels == k)[0]

            if len(cluster_indices) == 0:
                continue

            # Select highest-probability scenario in cluster
            cluster_probs = probabilities[cluster_indices]
            best_in_cluster = cluster_indices[np.argmax(cluster_probs)]

            selected.append(best_in_cluster)
            mapping[len(selected) - 1] = list(cluster_indices)

        return selected, mapping

    def _backward_reduction(
        self,
        features: np.ndarray,
        probabilities: np.ndarray,
        target_count: int,
    ) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Backward reduction: iteratively remove worst scenario.

        More accurate than forward selection but slower.
        """
        n = len(features)
        remaining = list(range(n))
        distances = cdist(features, features, metric=self.distance_metric)

        while len(remaining) > target_count:
            worst_idx = None
            best_remaining_error = float('inf')

            for candidate in remaining:
                # Tentatively remove candidate
                trial_remaining = [i for i in remaining if i != candidate]

                # Compute error without this scenario
                error = self._compute_removal_error(
                    distances, probabilities, trial_remaining, candidate
                )

                if error < best_remaining_error:
                    best_remaining_error = error
                    worst_idx = candidate

            remaining.remove(worst_idx)

        # Create mapping
        selected = remaining
        mapping = {i: [selected[i]] for i in range(len(selected))}

        for j in range(n):
            if j in selected:
                continue
            nearest = min(range(len(selected)),
                         key=lambda i: distances[j, selected[i]])
            mapping[nearest].append(j)

        return selected, mapping

    def _compute_selection_error(
        self,
        distances: np.ndarray,
        probabilities: np.ndarray,
        selected: List[int],
        remaining: set,
    ) -> float:
        """Compute approximation error for current selection"""
        error = 0.0

        for j in remaining:
            # Distance to nearest selected scenario
            min_dist = min(distances[j, i] for i in selected)
            error += probabilities[j] * min_dist

        return error

    def _compute_removal_error(
        self,
        distances: np.ndarray,
        probabilities: np.ndarray,
        remaining: List[int],
        removed: int,
    ) -> float:
        """Compute error after removing a scenario"""
        if not remaining:
            return float('inf')

        # Find nearest remaining scenario to removed
        min_dist = min(distances[removed, i] for i in remaining)
        return probabilities[removed] * min_dist

    def _compute_wasserstein_error(
        self,
        original_features: np.ndarray,
        original_probs: np.ndarray,
        reduced_features: np.ndarray,
        reduced_probs: np.ndarray,
    ) -> float:
        """
        Compute Wasserstein distance between original and reduced distributions.

        This is the approximation error of the scenario reduction.
        """
        # Cost matrix: distance between each original and reduced scenario
        cost_matrix = cdist(original_features, reduced_features, metric=self.distance_metric)

        # Solve transportation problem (approximate)
        # For exact Wasserstein, would need linear programming
        error = 0.0
        for i, p in enumerate(original_probs):
            min_cost = cost_matrix[i].min()
            error += p * min_cost

        return error


def reduce_conformal_scenarios(
    scenarios: List[Scenario],
    target_count: int = 50,
    method: str = "fast_forward",
) -> List[Scenario]:
    """
    Convenience function to reduce scenarios.

    Args:
        scenarios: Original scenario list from ConformalScenarioGenerator
        target_count: Target number of scenarios
        method: Reduction method

    Returns:
        Reduced scenario list with aggregated probabilities
    """
    reducer = WassersteinScenarioReducer()
    result = reducer.reduce(scenarios, target_count, method)
    return result.reduced_scenarios
```

### Acceptance Criteria

- [ ] Forward selection correctly minimizes Wasserstein distance
- [ ] Fast forward selection scales to 1000+ scenarios
- [ ] Probabilities correctly aggregated after reduction
- [ ] Wasserstein error metric computed
- [ ] Unit tests comparing full vs reduced solutions

---

## Gap 4: Conformal Safety Stock Integration (2-3 weeks)

### Objective
Add a 5th inventory policy type (`conformal`) that uses conformal prediction intervals directly instead of the traditional zσ√LT formula.

### Specification

**Modify**: `backend/app/services/sc_planning/inventory_target_calculator.py`

Add new policy type:

```python
class InventoryPolicyType(str, Enum):
    ABS_LEVEL = "abs_level"      # Fixed quantity
    DOC_DEM = "doc_dem"          # Days of coverage (demand-based)
    DOC_FCST = "doc_fcst"        # Days of coverage (forecast-based)
    SL = "sl"                    # Service level with z-score
    CONFORMAL = "conformal"      # NEW: Conformal prediction-based


class ConformalSafetyStockCalculator:
    """
    Calculate safety stock using conformal prediction intervals.

    Traditional:
        SS = z * σ_demand * sqrt(lead_time)
        - Assumes Normal demand distribution
        - No guarantee on actual service level

    Conformal:
        SS = max_demand_during_LT - expected_demand_during_LT
        where max_demand_during_LT is upper bound of conformal interval
        - No distribution assumptions
        - Formal service level guarantee
    """

    def __init__(
        self,
        conformal_suite: "SupplyChainConformalSuite",
    ):
        self.suite = conformal_suite

    def calculate_safety_stock(
        self,
        product_id: str,
        site_id: int,
        expected_demand_per_period: float,
        expected_lead_time: float,
        supplier_id: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Calculate safety stock with conformal guarantees.

        Args:
            product_id: Product identifier
            site_id: Site identifier
            expected_demand_per_period: Average demand per period
            expected_lead_time: Expected replenishment lead time
            supplier_id: Supplier identifier (for lead time calibration)

        Returns:
            Dict with safety_stock, reorder_point, service_level_guarantee
        """
        # Get demand interval for lead time periods
        try:
            # Predict demand for lead time duration
            demand_during_lt = expected_demand_per_period * expected_lead_time
            demand_interval = self.suite.predict_demand(
                product_id, site_id, demand_during_lt
            )
            demand_upper = demand_interval.upper
            demand_coverage = self.suite.demand_coverage
        except ValueError:
            # No calibrated predictor - use fallback
            demand_upper = expected_demand_per_period * expected_lead_time * 1.3
            demand_coverage = 0.80

        # Get lead time interval
        try:
            if supplier_id:
                lt_lower, lt_upper = self.suite.predict_lead_time(
                    supplier_id, expected_lead_time
                )
            else:
                lt_upper = expected_lead_time * 1.3
            lt_coverage = self.suite.lead_time_coverage
        except ValueError:
            lt_upper = expected_lead_time * 1.3
            lt_coverage = 0.80

        # Worst-case: high demand × long lead time
        # This covers joint uncertainty
        worst_case_demand_during_lt = (
            (demand_upper / (expected_demand_per_period * expected_lead_time)) *
            expected_demand_per_period * lt_upper
        )

        expected_demand_during_lt = expected_demand_per_period * expected_lead_time

        # Safety stock covers gap between worst-case and expected
        safety_stock = max(0, worst_case_demand_during_lt - expected_demand_during_lt)

        # Reorder point
        reorder_point = expected_demand_during_lt + safety_stock

        # Joint coverage (assuming independence)
        joint_coverage = demand_coverage * lt_coverage

        return {
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "expected_demand_during_lt": expected_demand_during_lt,
            "worst_case_demand_during_lt": worst_case_demand_during_lt,
            "service_level_guarantee": joint_coverage,
            "demand_coverage": demand_coverage,
            "lead_time_coverage": lt_coverage,
            "policy_type": "conformal",
        }
```

**Add to existing `InventoryTargetCalculator`**:

```python
async def _calculate_conformal_safety_stock(
    self,
    product_id: str,
    site_id: int,
    policy: "InvPolicy",
    demand_data: Dict,
) -> float:
    """Calculate safety stock using conformal prediction"""
    from ..conformal_prediction.suite import SupplyChainConformalSuite

    # Get or create conformal suite (singleton)
    suite = self._get_conformal_suite()

    calculator = ConformalSafetyStockCalculator(suite)

    result = calculator.calculate_safety_stock(
        product_id=product_id,
        site_id=site_id,
        expected_demand_per_period=demand_data.get("avg_demand", 0),
        expected_lead_time=policy.lead_time_periods or 2,
        supplier_id=demand_data.get("supplier_id"),
    )

    return result["safety_stock"]
```

### Database Changes

Add to `inv_policy` table:

```sql
-- Add conformal-specific columns
ALTER TABLE inv_policy ADD COLUMN conformal_demand_coverage FLOAT DEFAULT 0.90;
ALTER TABLE inv_policy ADD COLUMN conformal_lead_time_coverage FLOAT DEFAULT 0.90;
```

### API Changes

Update inventory policy endpoints to support conformal type:

```python
class InvPolicyCreate(BaseModel):
    policy_type: InventoryPolicyType
    # ... existing fields ...

    # New conformal-specific fields
    conformal_demand_coverage: Optional[float] = 0.90
    conformal_lead_time_coverage: Optional[float] = 0.90
```

### Acceptance Criteria

- [ ] New `conformal` policy type in enum
- [ ] `ConformalSafetyStockCalculator` correctly uses suite
- [ ] Service level guarantee computed and stored
- [ ] Works alongside existing 4 policy types
- [ ] Database migration for new columns
- [ ] API support for conformal policies
- [ ] Compare conformal vs traditional safety stock in tests

---

## Gap 5: Rolling Horizon S&OP with Conformal Updates (2-3 weeks)

### Objective
Create a rolling horizon S&OP planner that updates conformal predictors each planning cycle, enabling continuous learning.

### Specification

**New File**: `backend/app/services/powell/rolling_horizon_sop.py`

```python
"""
Rolling Horizon S&OP with Conformal Updates

Implements Powell's adaptive policy framework at the S&OP (strategic) level:
1. Solve stochastic program with current conformal scenarios
2. Execute first-period decisions
3. Observe actuals and update conformal predictors
4. Re-solve with updated conformal regions
5. Repeat

This creates a continuous learning loop where the planning system
improves as it observes outcomes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import date, timedelta
import logging

from ..conformal_prediction.suite import SupplyChainConformalSuite
from .conformal_scenario_generator import (
    ConformalScenarioGenerator,
    ConformalScenarioConfig,
    ConformalStochasticProgramBuilder,
)
from .scenario_reduction import reduce_conformal_scenarios
from .stochastic_program import StochasticSolution
from .mpc_planner import MPCSupplyPlanner

logger = logging.getLogger(__name__)


@dataclass
class SOPPlanningCycle:
    """Result of a single S&OP planning cycle"""
    cycle_id: int
    planning_date: date
    solution: StochasticSolution
    conformal_coverage: float
    n_scenarios_generated: int
    n_scenarios_after_reduction: int
    calibration_updates: Dict[str, int]  # predictor_key -> n_new_points

    # Decisions made
    first_stage_decisions: Dict[str, Any]

    # Performance metrics (if actuals available)
    realized_cost: Optional[float] = None
    service_level_achieved: Optional[float] = None


@dataclass
class RollingHorizonSOPConfig:
    """Configuration for rolling horizon S&OP"""
    planning_frequency_days: int = 30  # Monthly S&OP
    stochastic_horizon_periods: int = 12  # 12-month horizon
    tactical_horizon_periods: int = 4  # 4-week tactical

    # Scenario generation
    n_scenarios: int = 100
    n_scenarios_after_reduction: int = 30

    # Risk settings
    risk_measure: str = "cvar"  # "expected", "cvar", "robust"
    cvar_alpha: float = 0.95

    # Recalibration settings
    min_calibration_points: int = 20
    recalibration_trigger_coverage_gap: float = 0.05  # Recalibrate if gap > 5%


class RollingHorizonSOP:
    """
    Rolling Horizon S&OP Planner with Conformal Learning.

    Key Innovation: The conformal predictors update each cycle based on
    observed outcomes, so the uncertainty quantification improves over time.

    This implements Powell's "Approximate Dynamic Programming" at the S&OP level:
    - State: Current inventory, backlog, calibration data
    - Decision: Capacity, contracts, safety stock targets (Stage 1)
    - Exogenous info: Demand, lead time, yield realizations
    - Transition: State update + conformal recalibration
    """

    def __init__(
        self,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        resources: List[str],
        config: Optional[RollingHorizonSOPConfig] = None,
    ):
        self.products = products
        self.sites = sites
        self.suppliers = suppliers
        self.resources = resources
        self.config = config or RollingHorizonSOPConfig()

        # Initialize conformal suite
        self.conformal_suite = SupplyChainConformalSuite(
            demand_coverage=0.90,
            lead_time_coverage=0.90,
            yield_coverage=0.95,
        )

        # History of planning cycles
        self.cycle_history: List[SOPPlanningCycle] = []

        # Observation buffers for conformal updates
        self._demand_observations: Dict[str, List[tuple]] = {}  # key -> [(pred, actual), ...]
        self._lead_time_observations: Dict[str, List[tuple]] = {}
        self._yield_observations: Dict[str, List[tuple]] = {}

    def run_planning_cycle(
        self,
        current_date: date,
        demand_forecasts: Dict[tuple, List[float]],
        expected_lead_times: Dict[str, float],
        expected_yields: Optional[Dict[str, float]] = None,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> SOPPlanningCycle:
        """
        Run a single S&OP planning cycle.

        Args:
            current_date: Planning cycle date
            demand_forecasts: Point forecasts by (product, site)
            expected_lead_times: Expected lead times by supplier
            expected_yields: Expected yields by product
            current_state: Current inventory/backlog state

        Returns:
            SOPPlanningCycle with decisions and metadata
        """
        cycle_id = len(self.cycle_history)
        logger.info(f"Starting S&OP cycle {cycle_id} for {current_date}")

        # Step 1: Generate scenarios from current conformal regions
        generator = ConformalScenarioGenerator(
            self.conformal_suite,
            ConformalScenarioConfig(
                n_scenarios=self.config.n_scenarios,
                horizon=self.config.stochastic_horizon_periods,
            )
        )

        scenarios = generator.generate_scenarios(
            products=self.products,
            sites=self.sites,
            suppliers=self.suppliers,
            demand_forecasts=demand_forecasts,
            expected_lead_times=expected_lead_times,
            expected_yields=expected_yields,
        )

        n_generated = len(scenarios)

        # Step 2: Reduce scenarios if needed
        if len(scenarios) > self.config.n_scenarios_after_reduction:
            scenarios = reduce_conformal_scenarios(
                scenarios,
                target_count=self.config.n_scenarios_after_reduction,
                method="fast_forward",
            )

        n_reduced = len(scenarios)

        # Step 3: Solve stochastic program
        from .stochastic_program import TwoStageStochasticProgram

        program = TwoStageStochasticProgram(
            scenarios=scenarios,
            products=self.products,
            resources=self.resources,
            planning_horizon=self.config.stochastic_horizon_periods,
        )

        solution = program.solve(
            risk_measure=self.config.risk_measure,
            cvar_alpha=self.config.cvar_alpha,
        )

        # Step 4: Create cycle record
        cycle = SOPPlanningCycle(
            cycle_id=cycle_id,
            planning_date=current_date,
            solution=solution,
            conformal_coverage=generator.compute_coverage_guarantee(),
            n_scenarios_generated=n_generated,
            n_scenarios_after_reduction=n_reduced,
            calibration_updates={},
            first_stage_decisions=solution.first_stage_decisions,
        )

        self.cycle_history.append(cycle)

        logger.info(
            f"S&OP cycle {cycle_id} complete: "
            f"expected_cost={solution.expected_cost:.2f}, "
            f"coverage={cycle.conformal_coverage:.1%}"
        )

        return cycle

    def observe_actuals(
        self,
        observation_date: date,
        actual_demands: Dict[tuple, float],  # (product, site) -> actual
        actual_lead_times: Optional[Dict[str, float]] = None,  # supplier -> actual
        actual_yields: Optional[Dict[str, float]] = None,  # product -> actual
        forecasts_used: Optional[Dict[tuple, float]] = None,  # For calibration update
    ):
        """
        Observe actual outcomes and update conformal predictors.

        This is the KEY LEARNING STEP:
        - Compare predictions to actuals
        - Update conformal calibration
        - Improved uncertainty quantification for next cycle

        Args:
            observation_date: Date of observation
            actual_demands: Realized demands
            actual_lead_times: Realized lead times
            actual_yields: Realized yields
            forecasts_used: Original forecasts (for calibration)
        """
        updates = {}

        # Update demand predictors
        if forecasts_used:
            for (prod, site), actual in actual_demands.items():
                key = f"demand:{prod}:{site}"
                forecast = forecasts_used.get((prod, site))

                if forecast is not None:
                    if key not in self._demand_observations:
                        self._demand_observations[key] = []
                    self._demand_observations[key].append((forecast, actual))

                    # Trigger recalibration if enough new observations
                    if len(self._demand_observations[key]) >= 10:
                        self._recalibrate_demand(prod, site)
                        updates[key] = len(self._demand_observations[key])

        # Update lead time predictors
        if actual_lead_times:
            for supplier, actual_lt in actual_lead_times.items():
                key = f"lead_time:{supplier}"
                # Assume we have expected lead time from most recent cycle
                if self.cycle_history:
                    # Simplified: would need to track promised lead times
                    pass

        # Update yield predictors similarly

        # Update most recent cycle with calibration updates
        if self.cycle_history:
            self.cycle_history[-1].calibration_updates = updates

        logger.info(f"Updated {len(updates)} conformal predictors with new observations")

    def _recalibrate_demand(self, product_id: str, site_id: int):
        """Recalibrate demand predictor with accumulated observations"""
        key = f"demand:{product_id}:{site_id}"
        observations = self._demand_observations.get(key, [])

        if len(observations) < self.config.min_calibration_points:
            return

        forecasts = [o[0] for o in observations]
        actuals = [o[1] for o in observations]

        self.conformal_suite.calibrate_demand(
            product_id=product_id,
            site_id=site_id,
            historical_forecasts=forecasts,
            historical_actuals=actuals,
        )

        logger.info(f"Recalibrated demand predictor for {key} with {len(observations)} observations")

    def evaluate_performance(
        self,
        cycle_id: int,
        realized_cost: float,
        service_level_achieved: float,
    ):
        """
        Evaluate performance of a planning cycle against actuals.

        This enables tracking of:
        - Did conformal coverage hold? (service level >= guarantee)
        - How accurate were cost estimates?
        - Is the system improving over time?
        """
        if cycle_id >= len(self.cycle_history):
            raise ValueError(f"No cycle {cycle_id}")

        cycle = self.cycle_history[cycle_id]
        cycle.realized_cost = realized_cost
        cycle.service_level_achieved = service_level_achieved

        # Log performance
        expected_cost = cycle.solution.expected_cost
        cost_error = abs(realized_cost - expected_cost) / expected_cost if expected_cost else 0

        coverage_met = service_level_achieved >= cycle.conformal_coverage

        logger.info(
            f"Cycle {cycle_id} performance: "
            f"cost_error={cost_error:.1%}, "
            f"service_level={service_level_achieved:.1%} "
            f"(guarantee={cycle.conformal_coverage:.1%}, met={coverage_met})"
        )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of performance across all cycles"""
        if not self.cycle_history:
            return {"n_cycles": 0}

        evaluated = [c for c in self.cycle_history if c.realized_cost is not None]

        if not evaluated:
            return {
                "n_cycles": len(self.cycle_history),
                "n_evaluated": 0,
            }

        # Coverage analysis
        coverage_met = sum(
            1 for c in evaluated
            if c.service_level_achieved >= c.conformal_coverage
        )

        return {
            "n_cycles": len(self.cycle_history),
            "n_evaluated": len(evaluated),
            "coverage_hit_rate": coverage_met / len(evaluated),
            "avg_cost_error": np.mean([
                abs(c.realized_cost - c.solution.expected_cost) / c.solution.expected_cost
                for c in evaluated if c.solution.expected_cost > 0
            ]),
            "avg_service_level": np.mean([c.service_level_achieved for c in evaluated]),
            "avg_conformal_coverage": np.mean([c.conformal_coverage for c in evaluated]),
        }
```

### Integration with Existing MPC Planner

Update `mpc_planner.py` to consume conformal scenarios:

```python
class MPCSupplyPlanner:
    def __init__(
        self,
        ...
        conformal_suite: Optional[SupplyChainConformalSuite] = None,
    ):
        ...
        self.conformal_suite = conformal_suite

    def _generate_scenarios(self, ...):
        if self.conformal_suite:
            # Use conformal scenarios
            generator = ConformalScenarioGenerator(self.conformal_suite)
            return generator.generate_scenarios(...)
        else:
            # Existing parametric scenario generation
            ...
```

### Acceptance Criteria

- [ ] Planning cycles execute correctly
- [ ] Observations update conformal predictors
- [ ] Coverage guarantee tracked across cycles
- [ ] Performance improves over time (learning)
- [ ] Integration with existing MPC planner
- [ ] Unit tests for multi-cycle scenarios

---

## Implementation Order & Dependencies

```
Week 1-2: Gap 1 (SupplyChainConformalSuite)
    ↓
Week 2-5: Gap 2 (ConformalScenarioGenerator) [depends on Gap 1]
    ↓
Week 5-7: Gap 3 (Scenario Reduction) [can parallel with Gap 2]
    ↓
Week 5-7: Gap 4 (Conformal Safety Stock) [can parallel with Gap 2]
    ↓
Week 7-10: Gap 5 (Rolling Horizon S&OP) [depends on Gaps 1-4]
```

**Parallelizable**: Gaps 3 and 4 can be developed in parallel after Gap 1.

---

## Testing Strategy

### Unit Tests

1. **SupplyChainConformalSuite**
   - Individual predictor calibration
   - Joint scenario generation
   - Coverage guarantee calculation

2. **ConformalScenarioGenerator**
   - Sampling from conformal regions
   - Temporal correlation
   - Antithetic variates

3. **ScenarioReducer**
   - Forward selection correctness
   - Probability aggregation
   - Wasserstein error computation

4. **ConformalSafetyStock**
   - Calculation correctness
   - Comparison with traditional methods

5. **RollingHorizonSOP**
   - Multi-cycle execution
   - Calibration updates
   - Performance tracking

### Integration Tests

1. **End-to-End Pipeline**
   - Calibrate suite → Generate scenarios → Reduce → Solve SP → Extract policy
   - Verify coverage guarantees hold

2. **Learning Loop**
   - Run multiple cycles
   - Verify performance improves
   - Verify coverage met empirically

### Benchmarks

1. **Conformal vs Monte Carlo**
   - Compare solution quality
   - Compare coverage guarantees

2. **Reduced vs Full Scenarios**
   - Compare solve times
   - Compare solution quality

---

## API Endpoints (New)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/conformal/suite/calibrate` | Calibrate full suite |
| GET | `/api/v1/conformal/suite/status` | Get calibration status |
| POST | `/api/v1/conformal/scenarios/generate` | Generate conformal scenarios |
| POST | `/api/v1/conformal/scenarios/reduce` | Reduce scenario set |
| POST | `/api/v1/stochastic/solve-conformal` | Solve SP with conformal scenarios |
| POST | `/api/v1/sop/run-cycle` | Run S&OP planning cycle |
| POST | `/api/v1/sop/observe-actuals` | Update with observed actuals |
| GET | `/api/v1/sop/performance` | Get performance summary |

---

## Gap 6: Conformal Prediction Orchestrator (Implemented Feb 2026)

### Objective

Wire all conformal prediction components into an automatic feedback loop. Previously, calibration required manual API calls, forecasts loaded without interacting with conformal prediction, and actual demand was never compared back to forecasts.

### Implementation

**New File**: `backend/app/services/conformal_orchestrator.py`

The `ConformalOrchestrator` is a singleton service that fills 6 integration gaps:

| Gap | Method | Trigger | Description |
|-----|--------|---------|-------------|
| 1 - Forecast load hook | `on_forecasts_loaded()` | BackgroundTask after `/demand-plan/integrate` and `/demand-plan/override` | Checks if calibrated predictor exists; if not, bootstraps from historical `forecast_error` data (≥10 samples) |
| 2 - Actuals observation | `on_actual_demand_observed()` | Inline after `OrderManagementService.create_customer_order()` | Matches actual to forecast (exact date, then ±7 day window), computes error, updates `Forecast.forecast_error`, feeds calibration log |
| 3 - Drift monitoring | `_record_and_check_calibration()` | On each observation (inline) | Generic across all entity types. Checks empirical coverage; if deviation >5% from target, triggers `_emergency_recalibrate()` |
| 4 - Scheduled recalibration | `_run_daily_conformal_recalibration()` | APScheduler CronTrigger at 1:30 AM UTC | Calls `CalibrationFeedbackService.recalibrate_all_stale()` for each group, then re-hydrates suite |
| 5 - Planning staleness | `check_staleness()` / `check_staleness_by_entity()` | Before `_calculate_conformal_safety_stock()` in inventory target calculator | Advisory warning: stale >7 days, expired >14 days. Generic version supports any entity type. |
| 6 - Suite ↔ DB persistence | `hydrate_from_db()` / `persist_calibration()` | Startup / after every calibration | Persists to `powell_belief_state` table; hydrates from DB on app startup |

### Multi-Entity Observation Hooks (Feb 2026)

Beyond demand, the orchestrator automatically observes non-demand time series:

| Entity Type | Method | Trigger | Predicted vs Actual |
|-------------|--------|---------|---------------------|
| **Lead Time** | `on_lead_time_observed()` | `receive_transfer_order()` (TO receipt and linked PO receipt) | `estimated_delivery_date - order_date` vs `actual_delivery_date - order_date` |
| **Price** | `on_price_observed()` | `receive_transfer_order()` (PO line items at receipt) | `VendorProduct.vendor_unit_cost` vs `PurchaseOrderLineItem.unit_price` |
| **Service Level** | `on_service_level_observed()` | `update_order_fulfillment()` (order fully fulfilled) | Target fill rate (1.0) vs actual `shipped_quantity / ordered_quantity` |
| **Yield** | `on_yield_observed()` | Not wired yet (no manufacturing execution) | Expected yield vs actual yield ratio |

All hooks use the generic `_record_and_check_calibration()` and `_emergency_recalibrate()` which dispatch to the correct suite predictor type based on `EntityType`.

### Data Flow

```
FORECAST LOADED (4 paths)                    ACTUAL DEMAND OBSERVED
  demand_plan /integrate                      OrderManagementService.create_customer_order
  demand_plan /override                              │
  synthetic_data_generator                           ▼
  seed scripts                               on_actual_demand_observed()
         │                                     ├─ _match_forecast() → find matching Forecast
         ▼                                     ├─ compute error = actual - forecast
  on_forecasts_loaded()                        ├─ update Forecast.forecast_error
    ├─ suite.has_demand_predictor()?           ├─ _record_and_check_calibration(DEMAND)
    │   yes → already calibrated              └─ check drift → _emergency_recalibrate() if >5%
    │   no  → check forecast_error history
    │         ├─ ≥10 records → calibrate     TO/PO RECEIVED
    │         └─ <10 records → needs data      receive_transfer_order()
    └─ persist_calibration()                     ├─ on_lead_time_observed(LEAD_TIME)
                                                 │   └─ expected vs actual delivery days
         DAILY 1:30 AM UTC                       ├─ on_price_observed(PRICE)
         _run_daily_conformal_recalibration()    │   └─ catalog price vs PO line price
           ├─ recalibrate_all_stale(group)       └─ _record_and_check_calibration(*)
           └─ hydrate_from_db()
                                               ORDER FULFILLED
         STARTUP                                 update_order_fulfillment(customer_id)
         hydrate_from_db()                         ├─ on_service_level_observed(SERVICE_LEVEL)
           └─ PowellBeliefState                    │   └─ target fill rate vs actual fill rate
              → suite.calibrate_*(DEMAND,          └─ _record_and_check_calibration(*)
                LEAD_TIME, YIELD, PRICE)
```

### Modified Files

| File | Change |
|------|--------|
| `backend/main.py` | Registers APScheduler job; hydrates suite from DB on startup |
| `backend/app/api/endpoints/demand_plan.py` | `BackgroundTasks` hook on `/integrate` and `/override` |
| `backend/app/services/order_management_service.py` | Demand actuals hook on `create_customer_order(customer_id)`; lead time + price hooks on `receive_transfer_order()`; service level hook on `update_order_fulfillment(customer_id)` |
| `backend/app/services/sc_planning/inventory_target_calculator.py` | Advisory staleness check in `_calculate_conformal_safety_stock` |
| `backend/app/services/powell/belief_state.py` | `integrate_with_conformal_service()` stub replaced with real wiring |

### Configuration Constants

```python
STALENESS_WARNING_HOURS = 168       # 7 days → warning
STALENESS_ERROR_HOURS = 336         # 14 days → expired
DRIFT_COVERAGE_THRESHOLD = 0.05    # 5% deviation triggers emergency recalibration
MIN_OBSERVATIONS_FOR_CALIBRATION = 10
DAILY_RECALIBRATION_HOUR = 1       # 1:30 AM UTC
DAILY_RECALIBRATION_MINUTE = 30
```

### Key Design Decisions

1. **Non-critical hooks**: All hooks are wrapped in try/except. Forecast saves and order creation never fail due to conformal processing.
2. **BackgroundTasks for forecast hooks**: Conformal processing runs after the HTTP response is sent.
3. **Suite key vs DB key translation**: Suite uses `"demand:product_id:site_id"` internally; DB stores `entity_type=DEMAND` + `entity_id="product_id:site_id"` separately.
4. **Sync/async bridge**: The daily APScheduler job creates `asyncio.new_event_loop()` for async `CalibrationFeedbackService` calls (APScheduler runs in a background thread).

---

## Success Metrics

1. **Coverage Guarantee Met**: Empirical service level ≥ conformal coverage in 90%+ of cycles
2. **Cost Accuracy**: Realized cost within 10% of expected cost
3. **Learning Improvement**: Coverage hit rate improves over first 6 cycles
4. **Computational Efficiency**: Scenario reduction achieves 10x speedup with <5% solution degradation
5. **Orchestrator Metrics** (new):
   - **Auto-calibration rate**: % of product-site pairs with calibrated predictors after 30 days
   - **Forecast error coverage**: % of `Forecast.forecast_error` fields populated automatically
   - **Drift detection latency**: Number of observations between drift onset and emergency recalibration
   - **Belief state freshness**: % of belief states recalibrated within 24 hours

---

## References

- Romano, Sesia, Candès (2019). "Conformalized Quantile Regression"
- Tibshirani et al. (2019). "Conformal Prediction Under Covariate Shift"
- Heitsch & Römisch (2003). "Scenario Reduction Algorithms in Stochastic Programming"
- Powell (2022). "Sequential Decision Analytics and Modeling"
- Birge & Louveaux (2011). "Introduction to Stochastic Programming"

"""
Supply Chain Conformal Suite

Unified management of multiple conformal predictors for joint uncertainty quantification.
Enables generation of scenarios from conformal regions with guaranteed coverage.

This is the KEY INTEGRATION POINT between:
- Conformal Prediction (uncertainty quantification)
- Stochastic Programming (optimization under uncertainty)

References:
- Romano et al. (2019). Conformalized Quantile Regression
- Tibshirani et al. (2019). Conformal Prediction Under Covariate Shift
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import numpy as np

from .engine import ConformalPredictionEngine, PredictionInterval
from .predictors import (
    AdaptiveConformalPredictor,
    DemandConformalPredictor,
    LeadTimeConformalPredictor,
    SplitConformalPredictor,
)

logger = logging.getLogger(__name__)


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
        prices: Dict[material_id, float] - price by material
        coverage_guarantee: Joint coverage guarantee (product of individual coverages)
    """

    scenario_id: int
    probability: float
    demand: Dict[str, List[float]]
    lead_times: Dict[str, float]
    yields: Dict[str, float]
    prices: Dict[str, float]
    coverage_guarantee: float

    def to_stochastic_scenario(self):
        """Convert to stochastic programming Scenario format"""
        # Import here to avoid circular dependency
        from ..powell.stochastic_program import Scenario

        return Scenario(
            id=self.scenario_id,
            probability=self.probability,
            demand=self.demand,
            lead_times=self.lead_times,
            yields=self.yields,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "scenario_id": self.scenario_id,
            "probability": self.probability,
            "demand": self.demand,
            "lead_times": self.lead_times,
            "yields": self.yields,
            "prices": self.prices,
            "coverage_guarantee": self.coverage_guarantee,
        }


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
        self._product_id: Optional[str] = None

    def calibrate(
        self,
        expected_yields: List[float],
        actual_yields: List[float],
        product_id: Optional[str] = None,
    ):
        """Calibrate from historical expected vs actual yields"""
        self.predictor.calibrate_from_history(expected_yields, actual_yields)
        self._calibrated = True
        self._product_id = product_id
        logger.info(f"Calibrated yield predictor for {product_id} with {len(expected_yields)} points")

    def predict(self, expected_yield: float) -> Tuple[float, float]:
        """
        Predict yield interval.

        Returns:
            (lower_bound, upper_bound) bounded to [0, 1]
        """
        if not self._calibrated:
            # Conservative fallback
            return (max(0.0, expected_yield * 0.9), min(1.0, expected_yield * 1.02))

        interval = self.predictor.predict(expected_yield)
        return (max(0.0, interval.lower), min(1.0, interval.upper))

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


class PriceConformalPredictor:
    """
    Conformal predictor for prices (raw materials, commodities).

    Prices are non-negative with potentially high volatility.
    Uses adaptive conformal prediction to handle price drift.
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = AdaptiveConformalPredictor(
            target="price",
            coverage=coverage,
            gamma=0.01,  # Higher gamma for volatile prices
        )
        self._calibrated = False
        self._material_id: Optional[str] = None

    def calibrate(
        self,
        predicted_prices: List[float],
        actual_prices: List[float],
        material_id: Optional[str] = None,
    ):
        """Calibrate from historical price predictions"""
        # For adaptive predictor, add points sequentially
        for i, (pred, actual) in enumerate(zip(predicted_prices, actual_prices)):
            prev_actual = actual_prices[i - 1] if i > 0 else None
            self.predictor.update_and_predict(pred, prev_actual)

        self._calibrated = True
        self._material_id = material_id
        logger.info(f"Calibrated price predictor for {material_id} with {len(predicted_prices)} points")

    def predict(self, expected_price: float, previous_actual: Optional[float] = None) -> PredictionInterval:
        """Predict price interval (non-negative)"""
        interval = self.predictor.update_and_predict(expected_price, previous_actual)
        interval.lower = max(0.0, interval.lower)
        return interval

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


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

    Usage:
        suite = SupplyChainConformalSuite()

        # Calibrate predictors
        suite.calibrate_demand("PROD001", 1, forecasts, actuals)
        suite.calibrate_lead_time("SUPPLIER001", predicted_lt, actual_lt)

        # Get prediction intervals
        interval = suite.predict_demand("PROD001", 1, point_forecast)

        # Generate joint scenarios for stochastic programming
        scenarios = suite.generate_joint_scenarios(...)
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

        logger.info(
            f"Initialized SupplyChainConformalSuite: "
            f"demand={demand_coverage}, lead_time={lead_time_coverage}, "
            f"yield={yield_coverage}, price={price_coverage}"
        )

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
        """
        Calibrate demand predictor for product-site combination.

        Args:
            product_id: Product identifier
            site_id: Site identifier
            historical_forecasts: Past demand forecasts
            historical_actuals: Corresponding actual demands
        """
        key = self._get_key("demand", product_id, site_id)

        predictor = DemandConformalPredictor(
            coverage=self.demand_coverage,
            use_adaptive=True,
        )

        # Initialize calibration by simulating online updates
        for i, (pred, actual) in enumerate(zip(historical_forecasts, historical_actuals)):
            prev_actual = historical_actuals[i - 1] if i > 0 else None
            predictor.predict(pred, prev_actual)

        self._demand_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

        logger.info(
            f"Calibrated demand predictor for {key} with {len(historical_forecasts)} points"
        )

    def predict_demand(
        self,
        product_id: str,
        site_id: int,
        point_forecast: float,
        previous_actual: Optional[float] = None,
    ) -> PredictionInterval:
        """
        Get demand prediction interval.

        Args:
            product_id: Product identifier
            site_id: Site identifier
            point_forecast: Point forecast of demand
            previous_actual: Previous actual demand (for adaptive update)

        Returns:
            PredictionInterval with guaranteed coverage
        """
        key = self._get_key("demand", product_id, site_id)

        if key not in self._demand_predictors:
            raise ValueError(f"No calibrated demand predictor for {key}. Call calibrate_demand() first.")

        return self._demand_predictors[key].predict(point_forecast, previous_actual)

    def has_demand_predictor(self, product_id: str, site_id: int) -> bool:
        """Check if demand predictor exists for product-site"""
        key = self._get_key("demand", product_id, site_id)
        return key in self._demand_predictors

    # =========================================================================
    # Lead Time Prediction
    # =========================================================================

    def calibrate_lead_time(
        self,
        supplier_id: str,
        predicted_lead_times: List[float],
        actual_lead_times: List[float],
    ):
        """
        Calibrate lead time predictor for supplier.

        Args:
            supplier_id: Supplier identifier
            predicted_lead_times: Promised/expected lead times
            actual_lead_times: Actual observed lead times
        """
        key = self._get_key("lead_time", supplier_id)

        predictor = LeadTimeConformalPredictor(coverage=self.lead_time_coverage)
        predictor.calibrate(predicted_lead_times, actual_lead_times)

        self._lead_time_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

        logger.info(
            f"Calibrated lead time predictor for {key} with {len(predicted_lead_times)} points"
        )

    def predict_lead_time(
        self,
        supplier_id: str,
        expected_lead_time: float,
    ) -> Tuple[float, float]:
        """
        Get lead time prediction interval.

        Args:
            supplier_id: Supplier identifier
            expected_lead_time: Expected/promised lead time

        Returns:
            (earliest_arrival, latest_arrival) tuple
        """
        key = self._get_key("lead_time", supplier_id)

        if key not in self._lead_time_predictors:
            raise ValueError(f"No calibrated lead time predictor for {key}. Call calibrate_lead_time() first.")

        return self._lead_time_predictors[key].predict_arrival_window(expected_lead_time)

    def has_lead_time_predictor(self, supplier_id: str) -> bool:
        """Check if lead time predictor exists for supplier"""
        key = self._get_key("lead_time", supplier_id)
        return key in self._lead_time_predictors

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
        """
        Calibrate yield predictor for product-process combination.

        Args:
            product_id: Product identifier
            process_id: Production process identifier (optional)
            expected_yields: Expected yield percentages
            actual_yields: Actual observed yields
        """
        key = self._get_key("yield", product_id, process_id)

        predictor = YieldConformalPredictor(coverage=self.yield_coverage)
        predictor.calibrate(expected_yields, actual_yields, product_id)

        self._yield_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

        logger.info(
            f"Calibrated yield predictor for {key} with {len(expected_yields)} points"
        )

    def predict_yield(
        self,
        product_id: str,
        process_id: Optional[str],
        expected_yield: float,
    ) -> Tuple[float, float]:
        """
        Get yield prediction interval.

        Args:
            product_id: Product identifier
            process_id: Production process identifier (optional)
            expected_yield: Expected yield percentage

        Returns:
            (lower_bound, upper_bound) bounded to [0, 1]
        """
        key = self._get_key("yield", product_id, process_id)

        if key not in self._yield_predictors:
            # Fallback: conservative estimate
            return (max(0.0, expected_yield * 0.9), min(1.0, expected_yield * 1.02))

        return self._yield_predictors[key].predict(expected_yield)

    def has_yield_predictor(self, product_id: str, process_id: Optional[str] = None) -> bool:
        """Check if yield predictor exists"""
        key = self._get_key("yield", product_id, process_id)
        return key in self._yield_predictors

    # =========================================================================
    # Price Prediction
    # =========================================================================

    def calibrate_price(
        self,
        material_id: str,
        predicted_prices: List[float],
        actual_prices: List[float],
    ):
        """
        Calibrate price predictor for raw material.

        Args:
            material_id: Material identifier
            predicted_prices: Predicted/expected prices
            actual_prices: Actual observed prices
        """
        key = self._get_key("price", material_id)

        predictor = PriceConformalPredictor(coverage=self.price_coverage)
        predictor.calibrate(predicted_prices, actual_prices, material_id)

        self._price_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

        logger.info(
            f"Calibrated price predictor for {key} with {len(predicted_prices)} points"
        )

    def predict_price(
        self,
        material_id: str,
        expected_price: float,
        previous_actual: Optional[float] = None,
    ) -> PredictionInterval:
        """
        Get price prediction interval.

        Args:
            material_id: Material identifier
            expected_price: Expected price
            previous_actual: Previous actual price (for adaptive update)

        Returns:
            PredictionInterval with guaranteed coverage
        """
        key = self._get_key("price", material_id)

        if key not in self._price_predictors:
            raise ValueError(f"No calibrated price predictor for {key}. Call calibrate_price() first.")

        return self._price_predictors[key].predict(expected_price, previous_actual)

    def has_price_predictor(self, material_id: str) -> bool:
        """Check if price predictor exists for material"""
        key = self._get_key("price", material_id)
        return key in self._price_predictors

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
        expected_prices: Optional[Dict[str, float]] = None,  # material -> price
        n_scenarios: int = 20,
        horizon: int = 12,
        seed: Optional[int] = None,
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
            expected_prices: Expected prices by material (optional)
            n_scenarios: Number of scenarios to generate
            horizon: Planning horizon (periods)
            seed: Random seed for reproducibility

        Returns:
            List of JointUncertaintyScenario with coverage guarantees
        """
        if seed is not None:
            np.random.seed(seed)

        scenarios = []

        # Calculate joint coverage (product of individual coverages)
        joint_coverage = self.demand_coverage * self.lead_time_coverage
        if expected_yields:
            joint_coverage *= self.yield_coverage
        if expected_prices:
            joint_coverage *= self.price_coverage

        for i in range(n_scenarios):
            # Sample demand scenarios
            demand = self._sample_demand(products, sites, demand_forecasts, horizon)

            # Sample lead times
            lead_times = self._sample_lead_times(suppliers, expected_lead_times)

            # Sample yields
            yields = {}
            if expected_yields:
                yields = self._sample_yields(expected_yields)

            # Sample prices
            prices = {}
            if expected_prices:
                prices = self._sample_prices(expected_prices)

            scenarios.append(
                JointUncertaintyScenario(
                    scenario_id=i,
                    probability=1.0 / n_scenarios,
                    demand=demand,
                    lead_times=lead_times,
                    yields=yields,
                    prices=prices,
                    coverage_guarantee=joint_coverage,
                )
            )

        logger.info(
            f"Generated {n_scenarios} joint scenarios with coverage guarantee {joint_coverage:.1%}"
        )

        return scenarios

    def _sample_demand(
        self,
        products: List[str],
        sites: List[int],
        forecasts: Dict[Tuple[str, int], List[float]],
        horizon: int,
    ) -> Dict[str, List[float]]:
        """Sample demand from conformal intervals"""
        demand = {}

        for prod in products:
            prod_demand = []

            for site in sites:
                key = (prod, site)
                if key not in forecasts:
                    continue

                point_forecasts = forecasts[key][:horizon]
                predictor_key = self._get_key("demand", prod, site)

                for fc in point_forecasts:
                    if predictor_key in self._demand_predictors:
                        try:
                            interval = self._demand_predictors[predictor_key].predict(fc)
                            lower, upper = interval.lower, interval.upper
                        except Exception:
                            lower, upper = fc * 0.8, fc * 1.2
                    else:
                        # No calibrated predictor, use default uncertainty
                        lower, upper = fc * 0.8, fc * 1.2

                    # Sample uniformly from interval
                    sample = np.random.uniform(max(0, lower), upper)
                    prod_demand.append(sample)

            if prod_demand:
                demand[prod] = prod_demand

        return demand

    def _sample_lead_times(
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
            predictor_key = self._get_key("lead_time", supplier)

            if predictor_key in self._lead_time_predictors:
                try:
                    lower, upper = self._lead_time_predictors[predictor_key].predict_arrival_window(
                        expected
                    )
                except Exception:
                    lower, upper = expected * 0.8, expected * 1.3
            else:
                lower, upper = expected * 0.8, expected * 1.3

            lead_times[supplier] = np.random.uniform(max(0, lower), upper)

        return lead_times

    def _sample_yields(
        self,
        expected_yields: Dict[str, float],
    ) -> Dict[str, float]:
        """Sample yields from conformal intervals"""
        yields = {}

        for prod, expected in expected_yields.items():
            predictor_key = self._get_key("yield", prod, None)

            if predictor_key in self._yield_predictors:
                lower, upper = self._yield_predictors[predictor_key].predict(expected)
            else:
                lower, upper = max(0, expected * 0.95), min(1.0, expected * 1.02)

            yields[prod] = np.random.uniform(lower, upper)

        return yields

    def _sample_prices(
        self,
        expected_prices: Dict[str, float],
    ) -> Dict[str, float]:
        """Sample prices from conformal intervals"""
        prices = {}

        for material, expected in expected_prices.items():
            predictor_key = self._get_key("price", material)

            if predictor_key in self._price_predictors:
                try:
                    interval = self._price_predictors[predictor_key].predict(expected)
                    lower, upper = interval.lower, interval.upper
                except Exception:
                    lower, upper = expected * 0.8, expected * 1.2
            else:
                lower, upper = expected * 0.8, expected * 1.2

            prices[material] = np.random.uniform(max(0, lower), upper)

        return prices

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
            "total_predictors": (
                len(self._demand_predictors)
                + len(self._lead_time_predictors)
                + len(self._yield_predictors)
                + len(self._price_predictors)
            ),
            "coverage_targets": {
                "demand": self.demand_coverage,
                "lead_time": self.lead_time_coverage,
                "yield": self.yield_coverage,
                "price": self.price_coverage,
            },
            "predictor_keys": {
                "demand": list(self._demand_predictors.keys()),
                "lead_time": list(self._lead_time_predictors.keys()),
                "yield": list(self._yield_predictors.keys()),
                "price": list(self._price_predictors.keys()),
            },
            "calibration_timestamps": {
                k: v.isoformat() for k, v in self._calibration_timestamps.items()
            },
        }

    def check_recalibration_needed(
        self,
        max_age_hours: int = 168,  # 1 week
    ) -> List[str]:
        """
        Identify predictors that need recalibration.

        Args:
            max_age_hours: Maximum age in hours before recalibration needed

        Returns:
            List of predictor keys that are stale
        """
        stale = []
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        for key, timestamp in self._calibration_timestamps.items():
            if timestamp < cutoff:
                stale.append(key)

        if stale:
            logger.warning(f"Found {len(stale)} stale predictors needing recalibration")

        return stale

    def compute_joint_coverage(
        self,
        include_yields: bool = True,
        include_prices: bool = False,
    ) -> float:
        """
        Compute the joint coverage guarantee.

        Joint coverage = product of individual coverages (assuming independence)
        """
        coverage = self.demand_coverage * self.lead_time_coverage

        if include_yields:
            coverage *= self.yield_coverage

        if include_prices:
            coverage *= self.price_coverage

        return coverage

    def reset(self):
        """Clear all calibrated predictors"""
        self._demand_predictors.clear()
        self._lead_time_predictors.clear()
        self._yield_predictors.clear()
        self._price_predictors.clear()
        self._calibration_timestamps.clear()
        logger.info("Reset SupplyChainConformalSuite - all predictors cleared")


# Singleton instance
_suite_instance: Optional[SupplyChainConformalSuite] = None


def get_conformal_suite() -> SupplyChainConformalSuite:
    """Get the global conformal suite instance"""
    global _suite_instance
    if _suite_instance is None:
        _suite_instance = SupplyChainConformalSuite()
    return _suite_instance


def reset_conformal_suite():
    """Reset the global conformal suite instance"""
    global _suite_instance
    if _suite_instance is not None:
        _suite_instance.reset()
    _suite_instance = None

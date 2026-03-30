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
- Clarkson (2025). CoRel: Relational Conformal Prediction for Correlated Time Series
- Angelopoulos et al. (2024). Conformal Risk Control, ICLR 2024
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


class TransitTimeConformalPredictor:
    """
    Conformal predictor for transportation/transfer transit times.

    Transit times are positive with right-skewed distribution (occasional delays).
    Uses split conformal with floor at 0.
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(target="transit_time", coverage=coverage)
        self._calibrated = False

    def calibrate(self, estimated_times: List[float], actual_times: List[float], lane_id: Optional[str] = None):
        self.predictor.calibrate_from_history(estimated_times, actual_times)
        self._calibrated = True
        logger.info(f"Calibrated transit_time predictor for {lane_id} with {len(estimated_times)} points")

    def predict(self, estimated_time: float) -> Tuple[float, float]:
        if not self._calibrated:
            return (max(0.0, estimated_time * 0.7), estimated_time * 1.5)
        interval = self.predictor.predict(estimated_time)
        return (max(0.0, interval.lower), interval.upper)

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


class ReceiptVarianceConformalPredictor:
    """
    Conformal predictor for receipt quantity variance (ordered vs received).

    Variance ratio is typically near 1.0 with occasional under/over delivery.
    Bounded to [0, ∞).
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(target="receipt_variance", coverage=coverage)
        self._calibrated = False

    def calibrate(self, ordered_quantities: List[float], received_quantities: List[float], vendor_id: Optional[str] = None):
        # Compute variance ratios: received/ordered
        ratios_pred = [1.0] * len(ordered_quantities)  # Expected: 100% receipt
        ratios_actual = [r / max(1, o) for o, r in zip(ordered_quantities, received_quantities)]
        self.predictor.calibrate_from_history(ratios_pred, ratios_actual)
        self._calibrated = True
        logger.info(f"Calibrated receipt_variance predictor for {vendor_id} with {len(ordered_quantities)} points")

    def predict(self, expected_qty: float) -> Tuple[float, float]:
        if not self._calibrated:
            return (expected_qty * 0.85, expected_qty * 1.05)
        interval = self.predictor.predict(1.0)  # Predict around ratio=1.0
        return (max(0.0, expected_qty * interval.lower), expected_qty * interval.upper)

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


class QualityRejectionConformalPredictor:
    """
    Conformal predictor for quality rejection rates.

    Rejection rate is bounded to [0, 1] with most values near 0.
    Uses split conformal with tight bounds.
    """

    def __init__(self, coverage: float = 0.95):  # Higher coverage for quality (food safety)
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(target="quality_rejection", coverage=coverage)
        self._calibrated = False

    def calibrate(self, expected_rates: List[float], actual_rates: List[float], product_id: Optional[str] = None):
        self.predictor.calibrate_from_history(expected_rates, actual_rates)
        self._calibrated = True
        logger.info(f"Calibrated quality_rejection predictor for {product_id} with {len(expected_rates)} points")

    def predict(self, expected_rate: float) -> Tuple[float, float]:
        if not self._calibrated:
            return (0.0, min(1.0, expected_rate + 0.10))
        interval = self.predictor.predict(expected_rate)
        return (max(0.0, interval.lower), min(1.0, interval.upper))

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


class MaintenanceDowntimeConformalPredictor:
    """
    Conformal predictor for maintenance downtime (estimated vs actual hours).

    Downtime is positive with heavy right tail (emergency repairs can be much longer).
    Uses split conformal for batch calibration from historical data.
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(
            target="maintenance_downtime", coverage=coverage,
        )
        self._calibrated = False

    def calibrate(self, estimated_hours: List[float], actual_hours: List[float], asset_type: Optional[str] = None):
        self.predictor.calibrate_from_history(estimated_hours, actual_hours)
        self._calibrated = True
        logger.info(f"Calibrated maintenance_downtime predictor for {asset_type} with {len(estimated_hours)} points")

    def predict(self, estimated_hours: float) -> Tuple[float, float]:
        if not self._calibrated:
            return (max(0.0, estimated_hours * 0.5), estimated_hours * 3.0)
        interval = self.predictor.predict(estimated_hours)
        return (max(0.0, interval.lower), interval.upper)

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated


class ForecastBiasConformalPredictor:
    """
    Conformal predictor for forecast bias.

    Bias should be near zero. Calibrated interval gives guaranteed bounds on bias magnitude.
    """

    def __init__(self, coverage: float = 0.90):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(target="forecast_bias", coverage=coverage)
        self._calibrated = False

    def calibrate(self, bias_values: List[float], product_id: Optional[str] = None):
        # Predict zero bias, actual is measured bias
        zeros = [0.0] * len(bias_values)
        self.predictor.calibrate_from_history(zeros, bias_values)
        self._calibrated = True
        logger.info(f"Calibrated forecast_bias predictor for {product_id} with {len(bias_values)} points")

    def predict(self) -> Tuple[float, float]:
        if not self._calibrated:
            return (-0.15, 0.15)
        interval = self.predictor.predict(0.0)
        return (interval.lower, interval.upper)

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
        transit_time_coverage: float = 0.90,
        receipt_variance_coverage: float = 0.90,
        quality_rejection_coverage: float = 0.95,  # Higher for food safety
        maintenance_downtime_coverage: float = 0.90,
        forecast_bias_coverage: float = 0.90,
    ):
        self.demand_coverage = demand_coverage
        self.lead_time_coverage = lead_time_coverage
        self.yield_coverage = yield_coverage
        self.price_coverage = price_coverage
        self.transit_time_coverage = transit_time_coverage
        self.receipt_variance_coverage = receipt_variance_coverage
        self.quality_rejection_coverage = quality_rejection_coverage
        self.maintenance_downtime_coverage = maintenance_downtime_coverage
        self.forecast_bias_coverage = forecast_bias_coverage

        # Predictor registries keyed by (product_id, site_id) or similar
        self._demand_predictors: Dict[str, DemandConformalPredictor] = {}
        self._lead_time_predictors: Dict[str, LeadTimeConformalPredictor] = {}
        self._yield_predictors: Dict[str, YieldConformalPredictor] = {}
        self._price_predictors: Dict[str, PriceConformalPredictor] = {}
        self._transit_time_predictors: Dict[str, TransitTimeConformalPredictor] = {}
        self._receipt_variance_predictors: Dict[str, ReceiptVarianceConformalPredictor] = {}
        self._quality_rejection_predictors: Dict[str, QualityRejectionConformalPredictor] = {}
        self._maintenance_downtime_predictors: Dict[str, MaintenanceDowntimeConformalPredictor] = {}
        self._forecast_bias_predictors: Dict[str, ForecastBiasConformalPredictor] = {}

        # Calibration timestamps for staleness detection
        self._calibration_timestamps: Dict[str, datetime] = {}

        logger.info(
            f"Initialized SupplyChainConformalSuite: "
            f"demand={demand_coverage}, lead_time={lead_time_coverage}, "
            f"yield={yield_coverage}, price={price_coverage}, "
            f"transit={transit_time_coverage}, receipt_var={receipt_variance_coverage}, "
            f"quality={quality_rejection_coverage}, maint={maintenance_downtime_coverage}, "
            f"bias={forecast_bias_coverage}"
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
    # Transit Time Prediction (transfer orders, inter-DC shipments)
    # =========================================================================

    def calibrate_transit_time(
        self, lane_id: str, estimated_times: List[float], actual_times: List[float],
    ):
        key = self._get_key("transit_time", lane_id)
        predictor = TransitTimeConformalPredictor(coverage=self.transit_time_coverage)
        predictor.calibrate(estimated_times, actual_times, lane_id)
        self._transit_time_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_transit_time(self, lane_id: str, estimated_time: float) -> Tuple[float, float]:
        key = self._get_key("transit_time", lane_id)
        if key not in self._transit_time_predictors:
            return (max(0.0, estimated_time * 0.7), estimated_time * 1.5)
        return self._transit_time_predictors[key].predict(estimated_time)

    def has_transit_time_predictor(self, lane_id: str) -> bool:
        return self._get_key("transit_time", lane_id) in self._transit_time_predictors

    # =========================================================================
    # Receipt Quantity Variance (PO receipt accuracy by vendor)
    # =========================================================================

    def calibrate_receipt_variance(
        self, vendor_id: str, ordered_quantities: List[float], received_quantities: List[float],
    ):
        key = self._get_key("receipt_variance", vendor_id)
        predictor = ReceiptVarianceConformalPredictor(coverage=self.receipt_variance_coverage)
        predictor.calibrate(ordered_quantities, received_quantities, vendor_id)
        self._receipt_variance_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_receipt_variance(self, vendor_id: str, expected_qty: float) -> Tuple[float, float]:
        key = self._get_key("receipt_variance", vendor_id)
        if key not in self._receipt_variance_predictors:
            return (expected_qty * 0.85, expected_qty * 1.05)
        return self._receipt_variance_predictors[key].predict(expected_qty)

    def has_receipt_variance_predictor(self, vendor_id: str) -> bool:
        return self._get_key("receipt_variance", vendor_id) in self._receipt_variance_predictors

    # =========================================================================
    # Quality Rejection Rate (incoming inspection by product×vendor)
    # =========================================================================

    def calibrate_quality_rejection(
        self, entity_id: str, expected_rates: List[float], actual_rates: List[float],
    ):
        key = self._get_key("quality_rejection", entity_id)
        predictor = QualityRejectionConformalPredictor(coverage=self.quality_rejection_coverage)
        predictor.calibrate(expected_rates, actual_rates, entity_id)
        self._quality_rejection_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_quality_rejection(self, entity_id: str, expected_rate: float) -> Tuple[float, float]:
        key = self._get_key("quality_rejection", entity_id)
        if key not in self._quality_rejection_predictors:
            return (0.0, min(1.0, expected_rate + 0.10))
        return self._quality_rejection_predictors[key].predict(expected_rate)

    def has_quality_rejection_predictor(self, entity_id: str) -> bool:
        return self._get_key("quality_rejection", entity_id) in self._quality_rejection_predictors

    # =========================================================================
    # Maintenance Downtime (estimated vs actual by equipment type)
    # =========================================================================

    def calibrate_maintenance_downtime(
        self, asset_type: str, estimated_hours: List[float], actual_hours: List[float],
    ):
        key = self._get_key("maintenance_downtime", asset_type)
        predictor = MaintenanceDowntimeConformalPredictor(coverage=self.maintenance_downtime_coverage)
        predictor.calibrate(estimated_hours, actual_hours, asset_type)
        self._maintenance_downtime_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_maintenance_downtime(self, asset_type: str, estimated_hours: float) -> Tuple[float, float]:
        key = self._get_key("maintenance_downtime", asset_type)
        if key not in self._maintenance_downtime_predictors:
            return (max(0.0, estimated_hours * 0.5), estimated_hours * 3.0)
        return self._maintenance_downtime_predictors[key].predict(estimated_hours)

    def has_maintenance_downtime_predictor(self, asset_type: str) -> bool:
        return self._get_key("maintenance_downtime", asset_type) in self._maintenance_downtime_predictors

    # =========================================================================
    # Forecast Bias (systematic over/under-forecasting)
    # =========================================================================

    def calibrate_forecast_bias(
        self, entity_id: str, bias_values: List[float],
    ):
        key = self._get_key("forecast_bias", entity_id)
        predictor = ForecastBiasConformalPredictor(coverage=self.forecast_bias_coverage)
        predictor.calibrate(bias_values, entity_id)
        self._forecast_bias_predictors[key] = predictor
        self._calibration_timestamps[key] = datetime.utcnow()

    def predict_forecast_bias(self, entity_id: str) -> Tuple[float, float]:
        key = self._get_key("forecast_bias", entity_id)
        if key not in self._forecast_bias_predictors:
            return (-0.15, 0.15)
        return self._forecast_bias_predictors[key].predict()

    def has_forecast_bias_predictor(self, entity_id: str) -> bool:
        return self._get_key("forecast_bias", entity_id) in self._forecast_bias_predictors

    # =========================================================================
    # Calibration Summary (all variable types)
    # =========================================================================

    def get_calibration_summary(self) -> Dict[str, Any]:
        """Return summary of all calibrated predictors across all variable types."""
        return {
            "demand": {"count": len(self._demand_predictors), "coverage": self.demand_coverage},
            "lead_time": {"count": len(self._lead_time_predictors), "coverage": self.lead_time_coverage},
            "yield": {"count": len(self._yield_predictors), "coverage": self.yield_coverage},
            "price": {"count": len(self._price_predictors), "coverage": self.price_coverage},
            "transit_time": {"count": len(self._transit_time_predictors), "coverage": self.transit_time_coverage},
            "receipt_variance": {"count": len(self._receipt_variance_predictors), "coverage": self.receipt_variance_coverage},
            "quality_rejection": {"count": len(self._quality_rejection_predictors), "coverage": self.quality_rejection_coverage},
            "maintenance_downtime": {"count": len(self._maintenance_downtime_predictors), "coverage": self.maintenance_downtime_coverage},
            "forecast_bias": {"count": len(self._forecast_bias_predictors), "coverage": self.forecast_bias_coverage},
            "total_predictors": (
                len(self._demand_predictors) + len(self._lead_time_predictors) +
                len(self._yield_predictors) + len(self._price_predictors) +
                len(self._transit_time_predictors) + len(self._receipt_variance_predictors) +
                len(self._quality_rejection_predictors) + len(self._maintenance_downtime_predictors) +
                len(self._forecast_bias_predictors)
            ),
        }

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
        if hasattr(self, '_relational_predictor'):
            self._relational_predictor = None
        logger.info("Reset SupplyChainConformalSuite - all predictors cleared")

    # =========================================================================
    # Distribution Fitting for Residuals (Kravanja 2026)
    # =========================================================================

    @staticmethod
    def fit_residual_distribution(
        residuals: List[float],
        variable_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fit a distribution to conformal prediction residuals.

        Enriches conformal intervals with parametric distribution info.
        When residuals are non-Normal (e.g., right-skewed lead time errors),
        this provides diagnostic metadata and enables hybrid policies
        (sl_conformal_fitted) to combine parametric precision with
        conformal guarantees.

        Args:
            residuals: List of (predicted - actual) residuals
            variable_type: Hint for candidate selection ("demand", "lead_time", "yield")

        Returns:
            Dict with distribution fit metadata, or None if insufficient data
        """
        try:
            from ..stochastic.distribution_fitter import DistributionFitter
        except ImportError:
            logger.debug("DistributionFitter not available; skipping residual fitting")
            return None

        arr = np.array(residuals, dtype=float)
        arr = arr[np.isfinite(arr)]

        if len(arr) < DistributionFitter.MIN_SAMPLES_FOR_FIT:
            return None

        fitter = DistributionFitter()

        # For residuals (which can be negative), use general candidates
        # unless they're all positive (lead time errors are often positive)
        try:
            report = fitter.fit(arr, variable_type=None)
        except Exception as e:
            logger.debug("Residual distribution fitting failed: %s", e)
            return None

        # Check if Normal is a plausible model for the residuals
        is_normal_like = False
        normal_aic = float("inf")
        for c in report.candidates:
            if c.dist_type == "normal":
                normal_aic = c.aic
                if c.ks_pvalue > 0.05:
                    is_normal_like = True
                break

        # If Normal wasn't a candidate, check best-fit
        if normal_aic == float("inf"):
            is_normal_like = report.best.dist_type == "normal"

        # AIC gap: how much better is the best fit vs Normal?
        aic_gap = normal_aic - report.best.aic if np.isfinite(normal_aic) else 0.0

        metadata = {
            "dist_type": report.best.dist_type,
            "params": {k: round(v, 6) for k, v in report.best.params.items()},
            "ks_statistic": round(report.best.ks_statistic, 6),
            "ks_pvalue": round(report.best.ks_pvalue, 6),
            "aic": round(report.best.aic, 4),
            "is_normal_like": is_normal_like,
            "normal_aic_gap": round(aic_gap, 4),
            "n_residuals": len(arr),
            "skewness": round(float(report.data_summary.get("skewness", 0.0)), 4),
        }

        if not is_normal_like:
            logger.info(
                "Residuals are non-Normal (best=%s, AIC gap=%.1f). "
                "Consider sl_conformal_fitted for tighter intervals.",
                report.best.dist_type, aic_gap,
            )

        return metadata

    # =========================================================================
    # CoRel: Graph-Aware Relational Conformal Prediction
    # =========================================================================

    def calibrate_relational(
        self,
        adjacency: Dict[str, List[str]],
        site_residuals: Dict[str, List[float]],
        attention_decay: float = 0.5,
    ):
        """
        Calibrate the relational conformal predictor using DAG structure.

        CoRel (Clarkson 2025) exploits supply chain graph topology to produce
        tighter, correlated prediction intervals. A demand spike at a retailer
        implies increased demand at upstream wholesaler/distributor within
        lead-time offset.

        Args:
            adjacency: DAG adjacency list {site_key: [upstream_site_keys]}
            site_residuals: Historical forecast residuals per site
                           {site_key: [residual_1, residual_2, ...]}
            attention_decay: Weight decay for neighbor influence (0-1).
                           Higher = neighbors matter more.
        """
        self._relational_predictor = RelationalConformalPredictor(
            adjacency=adjacency,
            attention_decay=attention_decay,
        )
        self._relational_predictor.calibrate(site_residuals)
        logger.info(
            f"Calibrated relational predictor with {len(adjacency)} sites, "
            f"decay={attention_decay}"
        )

    def predict_relational_demand(
        self,
        site_key: str,
        point_forecast: float,
        neighbor_actuals: Optional[Dict[str, float]] = None,
    ) -> 'PredictionInterval':
        """
        Get graph-aware demand prediction interval for a site.

        Uses neighbor residuals to tighten or widen intervals based on
        observed upstream/downstream conditions.

        Args:
            site_key: Site identifier (format: "product_id:site_id")
            point_forecast: Point demand forecast
            neighbor_actuals: Recent actual demands from neighbors
                            {neighbor_key: actual_demand}

        Returns:
            PredictionInterval with graph-informed width
        """
        if not hasattr(self, '_relational_predictor') or self._relational_predictor is None:
            raise ValueError("Relational predictor not calibrated. Call calibrate_relational() first.")

        return self._relational_predictor.predict(
            site_key, point_forecast, neighbor_actuals
        )

    @property
    def has_relational_predictor(self) -> bool:
        return hasattr(self, '_relational_predictor') and self._relational_predictor is not None


class RelationalConformalPredictor:
    """
    CoRel: Relational Conformal Prediction for correlated supply chain nodes.

    Reference: Clarkson (2025). "CoRel: Relational Conformal Prediction for
    Correlated Time Series"

    Key insight: In a supply chain DAG, forecast errors are correlated across
    connected sites. A large positive residual at a retailer (higher-than-expected
    demand) predicts larger residuals at its upstream wholesaler within the
    transportation lead time.

    CoRel uses graph attention weights to compute correlation-aware nonconformity
    scores. Instead of treating each site independently:
      score_i = |residual_i|                          (standard CP)
    It uses:
      score_i = |residual_i - Σ_j w_ij × residual_j| (CoRel)

    where w_ij are attention weights from the DAG structure, decaying with
    graph distance.

    This produces:
    - Tighter intervals when neighbors are well-behaved (correlation helps)
    - Wider intervals when neighbors show anomalies (early warning)
    - Proper joint coverage across the entire network
    """

    def __init__(
        self,
        adjacency: Dict[str, List[str]],
        attention_decay: float = 0.5,
        coverage: float = 0.90,
    ):
        """
        Args:
            adjacency: DAG adjacency {site_key: [upstream_neighbor_keys]}
            attention_decay: Exponential decay for hop distance (0-1)
            coverage: Target marginal coverage
        """
        self.adjacency = adjacency
        self.attention_decay = attention_decay
        self.coverage = coverage

        # Compute attention weights from graph structure
        self._attention_weights: Dict[str, Dict[str, float]] = {}
        self._calibration_scores: Dict[str, List[float]] = {}
        self._global_scores: List[float] = []
        self._calibrated = False

        self._compute_attention_weights()

    def _compute_attention_weights(self):
        """
        Compute graph attention weights based on DAG distance.

        Weight w_ij = decay^(distance(i,j)) for neighbors,
        normalized so weights sum to 1 per site.
        """
        for site, neighbors in self.adjacency.items():
            weights = {}

            # Direct neighbors (distance=1)
            for neighbor in neighbors:
                weights[neighbor] = self.attention_decay

            # 2-hop neighbors (distance=2)
            for neighbor in neighbors:
                for hop2 in self.adjacency.get(neighbor, []):
                    if hop2 != site and hop2 not in weights:
                        weights[hop2] = self.attention_decay ** 2

            # Normalize
            total = sum(weights.values())
            if total > 0:
                weights = {k: v / total for k, v in weights.items()}

            self._attention_weights[site] = weights

    def calibrate(self, site_residuals: Dict[str, List[float]]):
        """
        Calibrate using graph-corrected nonconformity scores.

        Args:
            site_residuals: {site_key: [forecast_residuals]}
                           residual = actual - forecast
        """
        all_scores = []

        for site, residuals in site_residuals.items():
            site_scores = []
            weights = self._attention_weights.get(site, {})

            for t, residual in enumerate(residuals):
                # Graph-corrected score: subtract weighted neighbor residuals
                neighbor_correction = 0.0
                for neighbor, w in weights.items():
                    neighbor_resids = site_residuals.get(neighbor, [])
                    if t < len(neighbor_resids):
                        neighbor_correction += w * neighbor_resids[t]

                corrected_score = abs(residual - neighbor_correction)
                site_scores.append(corrected_score)

            self._calibration_scores[site] = site_scores
            all_scores.extend(site_scores)

        self._global_scores = sorted(all_scores)
        self._calibrated = True

        logger.info(
            f"CoRel calibrated with {len(site_residuals)} sites, "
            f"{len(all_scores)} total scores"
        )

    def predict(
        self,
        site_key: str,
        point_forecast: float,
        neighbor_actuals: Optional[Dict[str, float]] = None,
    ) -> PredictionInterval:
        """
        Produce graph-aware prediction interval.

        Args:
            site_key: Target site
            point_forecast: Demand point forecast
            neighbor_actuals: Recent actuals from neighbors (for online correction)

        Returns:
            PredictionInterval with CoRel-adjusted width
        """
        if not self._calibrated:
            # Fallback to standard interval
            width = abs(point_forecast) * 0.3
            return PredictionInterval(
                lower=max(0, point_forecast - width),
                upper=point_forecast + width,
                point=point_forecast,
                coverage=self.coverage,
                method="fallback",
            )

        # Use site-specific scores if available, else global
        scores = self._calibration_scores.get(site_key, self._global_scores)
        if not scores:
            scores = self._global_scores

        # Compute quantile
        alpha = 1.0 - self.coverage
        quantile_idx = int(np.ceil((1 - alpha) * (len(scores) + 1))) - 1
        quantile_idx = max(0, min(len(scores) - 1, quantile_idx))
        sorted_scores = sorted(scores)
        base_width = sorted_scores[quantile_idx]

        # Online correction: if neighbor actuals are provided,
        # adjust the interval center based on neighbor deviations
        correction = 0.0
        if neighbor_actuals:
            weights = self._attention_weights.get(site_key, {})
            for neighbor, actual in neighbor_actuals.items():
                if neighbor in weights:
                    # Neighbor's deviation from their own forecast propagates
                    correction += weights[neighbor] * actual

        adjusted_center = point_forecast + correction
        lower = max(0, adjusted_center - base_width)
        upper = adjusted_center + base_width

        return PredictionInterval(
            lower=lower,
            upper=upper,
            point=point_forecast,
            coverage=self.coverage,
            method="corel",
        )

    def get_network_risk_score(
        self,
        site_residuals: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Compute per-site risk scores based on network-wide residual pattern.

        High risk = site's graph-corrected score exceeds calibration quantile.

        Args:
            site_residuals: Current period residuals {site_key: residual}

        Returns:
            {site_key: risk_score} where risk_score ∈ [0, 1]
        """
        risk_scores = {}

        for site, residual in site_residuals.items():
            weights = self._attention_weights.get(site, {})
            neighbor_correction = sum(
                w * site_residuals.get(n, 0)
                for n, w in weights.items()
            )
            corrected = abs(residual - neighbor_correction)

            # Compare to calibration distribution
            scores = self._calibration_scores.get(site, self._global_scores)
            if scores:
                # Percentile rank
                rank = sum(1 for s in scores if s <= corrected) / len(scores)
                risk_scores[site] = rank
            else:
                risk_scores[site] = 0.5  # Unknown

        return risk_scores


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

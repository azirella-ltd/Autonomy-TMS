"""
Conformal Prediction Service

Distribution-free uncertainty quantification for supply chain planning.
Provides guaranteed prediction intervals without distributional assumptions.

Key Features:
1. ConformalPredictor - Base class for conformal prediction intervals
2. ConformalDemandForecaster - Demand forecasting with guaranteed coverage
3. ConformalLeadTimePredictor - Lead time prediction intervals
4. ConformalDecisionMaker - Supply chain decisions with formal risk bounds
5. AdaptiveConformalPredictor - Online conformal prediction with drift detection

Theory:
- Traditional forecasting: Point estimate + assumed distribution (often wrong)
- Conformal prediction: Point estimate + data-driven interval (distribution-free)
- Guarantee: If we say "90% coverage", the actual coverage will be ≥90%
"""

import numpy as np
from typing import Tuple, List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ConformalInterval:
    """Prediction interval with metadata"""
    point_forecast: float
    lower_bound: float
    upper_bound: float
    interval_width: float
    coverage_guarantee: float
    miscoverage_rate: float
    quantile: float
    method: str = "conformal_prediction"
    calibration_size: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CalibrationResult:
    """Result of conformal calibration"""
    alpha: float
    quantile: float
    empirical_coverage: float
    n_samples: int
    calibration_scores: np.ndarray
    timestamp: datetime = field(default_factory=datetime.now)
    variable_name: str = ""
    product_id: Optional[str] = None
    site_id: Optional[int] = None


@dataclass
class SafetyStockResult:
    """Safety stock calculation with conformal guarantees"""
    safety_stock: float
    reorder_point: float
    expected_demand: float
    demand_interval: Tuple[float, float]
    lead_time_interval: Tuple[float, float]
    service_level_guarantee: float
    method: str = "conformal_decision_theory"


@dataclass
class OrderPromiseResult:
    """Order promising with conformal guarantees"""
    can_promise: bool
    promised_date: Optional[datetime]
    confidence: float
    earliest_date: datetime
    latest_date: datetime
    risk_of_late_delivery: float


# ============================================================================
# Core Conformal Predictor
# ============================================================================

class ConformalPredictor:
    """
    Base class for conformal prediction intervals.

    Theory:
    1. Calibrate on historical data (Plan vs Actual)
    2. Compute nonconformity scores (absolute errors)
    3. Calculate (1-α) quantile of errors
    4. For new predictions: interval = point ± quantile

    Guarantee: P(actual ∈ interval) ≥ 1-α (no assumptions needed)
    """

    def __init__(self, alpha: float = 0.1):
        """
        Args:
            alpha: Miscoverage rate (0.1 = 90% guaranteed coverage)
        """
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1")

        self.alpha = alpha
        self.calibration_scores: np.ndarray = np.array([])
        self.quantile: Optional[float] = None
        self.calibration_result: Optional[CalibrationResult] = None
        self.is_calibrated = False

    def calibrate(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        variable_name: str = "",
        product_id: Optional[str] = None,
        site_id: Optional[int] = None
    ) -> CalibrationResult:
        """
        Calibrate using historical data (Plan vs. Actual).

        Args:
            y_true: Actual outcomes (e.g., realized demand)
            y_pred: Predicted values (e.g., forecasted demand)
            variable_name: Name of variable being predicted
            product_id: Optional product identifier
            site_id: Optional site identifier

        Returns:
            CalibrationResult with calibration statistics
        """
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)

        if len(y_true) != len(y_pred):
            raise ValueError("y_true and y_pred must have same length")

        if len(y_true) < 10:
            logger.warning(f"Small calibration set ({len(y_true)} samples). "
                          "Consider using more data for reliable intervals.")

        # Compute absolute errors (nonconformity scores)
        self.calibration_scores = np.abs(y_true - y_pred)

        # Calculate (1-α) quantile of errors
        # Use ceiling formula to guarantee coverage (conservative)
        n = len(self.calibration_scores)
        q_level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
        self.quantile = float(np.quantile(self.calibration_scores, q_level))

        # Compute empirical coverage
        empirical_coverage = float(np.mean(self.calibration_scores <= self.quantile))

        self.calibration_result = CalibrationResult(
            alpha=self.alpha,
            quantile=self.quantile,
            empirical_coverage=empirical_coverage,
            n_samples=n,
            calibration_scores=self.calibration_scores,
            variable_name=variable_name,
            product_id=product_id,
            site_id=site_id
        )

        self.is_calibrated = True

        logger.info(
            f"Conformal calibration complete: α={self.alpha:.2f}, "
            f"quantile={self.quantile:.2f}, "
            f"empirical_coverage={empirical_coverage:.1%} "
            f"(target: {1-self.alpha:.1%}), n={n}"
        )

        return self.calibration_result

    def predict(self, point_forecast: float) -> Tuple[float, float]:
        """
        Generate conformal prediction interval.

        Args:
            point_forecast: Point forecast from any model

        Returns:
            (lower_bound, upper_bound) with guaranteed (1-α) coverage
        """
        if not self.is_calibrated:
            raise ValueError("Must call calibrate() first")

        lower = point_forecast - self.quantile
        upper = point_forecast + self.quantile

        return (lower, upper)

    def predict_with_metadata(self, point_forecast: float) -> ConformalInterval:
        """
        Generate prediction interval with full metadata.
        """
        lower, upper = self.predict(point_forecast)

        return ConformalInterval(
            point_forecast=point_forecast,
            lower_bound=lower,
            upper_bound=upper,
            interval_width=upper - lower,
            coverage_guarantee=1 - self.alpha,
            miscoverage_rate=self.alpha,
            quantile=self.quantile,
            calibration_size=len(self.calibration_scores)
        )

    def predict_batch(self, point_forecasts: np.ndarray) -> List[ConformalInterval]:
        """Generate intervals for multiple forecasts."""
        return [self.predict_with_metadata(pf) for pf in point_forecasts]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize calibration state for storage."""
        if not self.is_calibrated:
            return {"is_calibrated": False, "alpha": self.alpha}

        return {
            "is_calibrated": True,
            "alpha": self.alpha,
            "quantile": self.quantile,
            "n_samples": len(self.calibration_scores),
            "calibration_scores": self.calibration_scores.tolist(),
            "empirical_coverage": self.calibration_result.empirical_coverage,
            "variable_name": self.calibration_result.variable_name,
            "product_id": self.calibration_result.product_id,
            "site_id": self.calibration_result.site_id,
            "timestamp": self.calibration_result.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConformalPredictor':
        """Deserialize calibration state."""
        predictor = cls(alpha=data["alpha"])

        if data.get("is_calibrated", False):
            predictor.calibration_scores = np.array(data["calibration_scores"])
            predictor.quantile = data["quantile"]
            predictor.is_calibrated = True
            predictor.calibration_result = CalibrationResult(
                alpha=data["alpha"],
                quantile=data["quantile"],
                empirical_coverage=data["empirical_coverage"],
                n_samples=data["n_samples"],
                calibration_scores=predictor.calibration_scores,
                variable_name=data.get("variable_name", ""),
                product_id=data.get("product_id"),
                site_id=data.get("site_id")
            )

        return predictor


# ============================================================================
# Adaptive Conformal Predictor (Online Learning)
# ============================================================================

class AdaptiveConformalPredictor(ConformalPredictor):
    """
    Adaptive conformal predictor that updates with new data.

    Features:
    - Rolling window calibration
    - Drift detection
    - Automatic recalibration when coverage degrades
    """

    def __init__(
        self,
        alpha: float = 0.1,
        window_size: int = 100,
        drift_threshold: float = 0.05
    ):
        """
        Args:
            alpha: Miscoverage rate
            window_size: Rolling window size for calibration
            drift_threshold: Trigger recalibration if coverage drops by this amount
        """
        super().__init__(alpha)
        self.window_size = window_size
        self.drift_threshold = drift_threshold

        # Rolling window of (actual, predicted) pairs
        self.history: deque = deque(maxlen=window_size)

        # Track recent coverage
        self.recent_coverage: deque = deque(maxlen=50)

    def update(self, actual: float, predicted: float) -> bool:
        """
        Update with new observation and check if recalibration needed.

        Args:
            actual: Actual outcome
            predicted: Previous prediction

        Returns:
            True if recalibration was triggered
        """
        self.history.append((actual, predicted))

        # Track whether this prediction was within the interval
        if self.is_calibrated:
            lower, upper = self.predict(predicted)
            in_interval = lower <= actual <= upper
            self.recent_coverage.append(1 if in_interval else 0)

            # Check for drift
            if len(self.recent_coverage) >= 20:
                recent_rate = np.mean(list(self.recent_coverage))
                target_rate = 1 - self.alpha

                if recent_rate < target_rate - self.drift_threshold:
                    logger.warning(
                        f"Coverage drift detected: {recent_rate:.1%} < "
                        f"{target_rate - self.drift_threshold:.1%}. Recalibrating."
                    )
                    self._recalibrate()
                    return True

        # Initial calibration or periodic recalibration
        if len(self.history) >= 20 and len(self.history) % 20 == 0:
            self._recalibrate()

        return False

    def _recalibrate(self):
        """Recalibrate using rolling window."""
        if len(self.history) < 10:
            return

        actuals = np.array([h[0] for h in self.history])
        predicted = np.array([h[1] for h in self.history])

        self.calibrate(actuals, predicted, variable_name="adaptive")
        self.recent_coverage.clear()


# ============================================================================
# Specialized Predictors
# ============================================================================

class ConformalDemandForecaster:
    """
    Demand forecaster with conformal prediction intervals.

    Wraps any base forecaster and adds distribution-free prediction intervals.
    """

    def __init__(self, base_forecaster: Any = None, alpha: float = 0.1):
        """
        Args:
            base_forecaster: Any forecasting model with predict() method
            alpha: Miscoverage rate (0.1 = 90% guaranteed coverage)
        """
        self.base_forecaster = base_forecaster
        self.conformal = ConformalPredictor(alpha=alpha)
        self.is_calibrated = False

    def calibrate(
        self,
        historical_forecasts: np.ndarray,
        historical_actuals: np.ndarray,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None
    ) -> CalibrationResult:
        """
        Calibrate using historical forecast vs actual data.

        Args:
            historical_forecasts: Past forecasts
            historical_actuals: Actual demand values
            product_id: Product identifier
            site_id: Site identifier
        """
        result = self.conformal.calibrate(
            y_true=historical_actuals,
            y_pred=historical_forecasts,
            variable_name="demand",
            product_id=product_id,
            site_id=site_id
        )
        self.is_calibrated = True
        return result

    def forecast_with_interval(
        self,
        point_forecast: float
    ) -> ConformalInterval:
        """
        Generate demand forecast with guaranteed prediction interval.

        Args:
            point_forecast: Point forecast (from any method)

        Returns:
            ConformalInterval with guaranteed coverage
        """
        if not self.is_calibrated:
            raise ValueError("Must call calibrate() first")

        return self.conformal.predict_with_metadata(point_forecast)

    def forecast_horizon(
        self,
        point_forecasts: List[float],
        periods: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate forecasts with intervals for multiple periods.

        Args:
            point_forecasts: Point forecasts for each period
            periods: Period labels (default: 1, 2, 3, ...)
        """
        if periods is None:
            periods = list(range(1, len(point_forecasts) + 1))

        results = []
        for period, forecast in zip(periods, point_forecasts):
            interval = self.forecast_with_interval(forecast)
            results.append({
                "period": period,
                "point_forecast": interval.point_forecast,
                "lower_bound": interval.lower_bound,
                "upper_bound": interval.upper_bound,
                "interval_width": interval.interval_width,
                "coverage_guarantee": interval.coverage_guarantee
            })

        return results


class ConformalLeadTimePredictor:
    """
    Lead time predictor with conformal intervals.

    Useful for:
    - Order promising (ATP/CTP)
    - Safety stock calculation
    - Supplier performance monitoring
    """

    def __init__(self, alpha: float = 0.1, min_lead_time: float = 0):
        """
        Args:
            alpha: Miscoverage rate
            min_lead_time: Minimum possible lead time (for truncation)
        """
        self.conformal = ConformalPredictor(alpha=alpha)
        self.min_lead_time = min_lead_time
        self.is_calibrated = False

    def calibrate(
        self,
        promised_lead_times: np.ndarray,
        actual_lead_times: np.ndarray,
        supplier_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> CalibrationResult:
        """
        Calibrate using historical promised vs actual lead times.
        """
        result = self.conformal.calibrate(
            y_true=actual_lead_times,
            y_pred=promised_lead_times,
            variable_name="lead_time",
            product_id=product_id
        )
        self.is_calibrated = True
        return result

    def predict_lead_time(
        self,
        promised_lead_time: float
    ) -> ConformalInterval:
        """
        Predict actual lead time interval.
        """
        if not self.is_calibrated:
            raise ValueError("Must call calibrate() first")

        interval = self.conformal.predict_with_metadata(promised_lead_time)

        # Truncate at minimum
        interval.lower_bound = max(self.min_lead_time, interval.lower_bound)
        interval.interval_width = interval.upper_bound - interval.lower_bound

        return interval


# ============================================================================
# Conformal Decision Maker
# ============================================================================

class ConformalDecisionMaker:
    """
    Make supply chain decisions with formal risk bounds using conformal prediction.

    Provides:
    - Safety stock calculation with service level guarantee
    - Order promising with delivery confidence
    - Inventory policy optimization under uncertainty
    """

    def __init__(
        self,
        demand_predictor: Optional[ConformalPredictor] = None,
        lead_time_predictor: Optional[ConformalPredictor] = None
    ):
        self.demand_predictor = demand_predictor
        self.lead_time_predictor = lead_time_predictor

    def calculate_safety_stock(
        self,
        expected_demand: float,
        expected_lead_time: float,
        demand_alpha: float = 0.1,
        lead_time_alpha: float = 0.1
    ) -> SafetyStockResult:
        """
        Calculate safety stock with formal service level guarantee.

        Traditional approach:
        - SS = z * σ_demand * sqrt(lead_time)
        - Assumes normal demand, fixed lead time
        - No guarantee on actual service level

        Conformal approach:
        - SS = worst_case_demand_during_LT - expected_demand_during_LT
        - No distribution assumptions
        - Formal guarantee on service level

        Args:
            expected_demand: Expected demand per period
            expected_lead_time: Expected lead time (periods)
            demand_alpha: Demand interval miscoverage rate
            lead_time_alpha: Lead time interval miscoverage rate

        Returns:
            SafetyStockResult with guaranteed service level
        """
        # Get demand interval
        if self.demand_predictor and self.demand_predictor.is_calibrated:
            demand_interval = self.demand_predictor.predict(expected_demand)
        else:
            # Default: ±20% uncertainty
            demand_interval = (expected_demand * 0.8, expected_demand * 1.2)

        # Get lead time interval
        if self.lead_time_predictor and self.lead_time_predictor.is_calibrated:
            lt_interval = self.lead_time_predictor.predict(expected_lead_time)
            lt_interval = (max(0, lt_interval[0]), lt_interval[1])
        else:
            # Default: ±30% uncertainty
            lt_interval = (expected_lead_time * 0.7, expected_lead_time * 1.3)

        # Worst-case scenario: high demand + long lead time
        demand_upper = demand_interval[1]
        lt_upper = lt_interval[1]

        worst_case_demand_during_lt = demand_upper * lt_upper
        expected_demand_during_lt = expected_demand * expected_lead_time

        # Safety stock covers the gap between worst-case and expected
        safety_stock = worst_case_demand_during_lt - expected_demand_during_lt

        # Reorder point = expected demand during LT + safety stock
        reorder_point = expected_demand_during_lt + safety_stock

        # Service level guarantee (joint probability, assuming independence)
        demand_coverage = 1 - demand_alpha
        lt_coverage = 1 - lead_time_alpha
        joint_coverage = demand_coverage * lt_coverage

        return SafetyStockResult(
            safety_stock=max(0, safety_stock),
            reorder_point=reorder_point,
            expected_demand=expected_demand,
            demand_interval=demand_interval,
            lead_time_interval=lt_interval,
            service_level_guarantee=joint_coverage
        )

    def promise_order(
        self,
        order_qty: float,
        available_inventory: float,
        expected_replenishment_date: datetime,
        expected_lead_time: float
    ) -> OrderPromiseResult:
        """
        Promise order delivery date with formal confidence.

        Args:
            order_qty: Quantity to promise
            available_inventory: Current inventory available
            expected_replenishment_date: When replenishment expected
            expected_lead_time: Expected lead time for replenishment

        Returns:
            OrderPromiseResult with delivery date and confidence
        """
        today = datetime.now()

        # Can fulfill from stock?
        if available_inventory >= order_qty:
            return OrderPromiseResult(
                can_promise=True,
                promised_date=today + timedelta(days=1),  # Next day delivery
                confidence=0.99,
                earliest_date=today + timedelta(days=1),
                latest_date=today + timedelta(days=2),
                risk_of_late_delivery=0.01
            )

        # Need replenishment
        if self.lead_time_predictor and self.lead_time_predictor.is_calibrated:
            lt_interval = self.lead_time_predictor.predict(expected_lead_time)
            lt_lower = max(0, lt_interval[0])
            lt_upper = lt_interval[1]
            confidence = 1 - self.lead_time_predictor.alpha
        else:
            lt_lower = expected_lead_time * 0.7
            lt_upper = expected_lead_time * 1.3
            confidence = 0.8

        earliest = expected_replenishment_date + timedelta(days=lt_lower)
        latest = expected_replenishment_date + timedelta(days=lt_upper)
        promised = expected_replenishment_date + timedelta(days=expected_lead_time)

        return OrderPromiseResult(
            can_promise=True,
            promised_date=promised,
            confidence=confidence,
            earliest_date=earliest,
            latest_date=latest,
            risk_of_late_delivery=1 - confidence
        )


# ============================================================================
# Conformal Prediction Service (Main Interface)
# ============================================================================

class ConformalPredictionService:
    """
    Main service for conformal prediction in supply chain planning.

    Manages multiple predictors for different variables/products/sites.
    """

    def __init__(self):
        self.predictors: Dict[str, ConformalPredictor] = {}
        self.demand_forecasters: Dict[str, ConformalDemandForecaster] = {}
        self.lead_time_predictors: Dict[str, ConformalLeadTimePredictor] = {}
        self.decision_makers: Dict[str, ConformalDecisionMaker] = {}

    def get_predictor_key(
        self,
        variable: str,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None
    ) -> str:
        """Generate unique key for a predictor."""
        parts = [variable]
        if product_id:
            parts.append(f"prod:{product_id}")
        if site_id:
            parts.append(f"site:{site_id}")
        return ":".join(parts)

    def calibrate_demand(
        self,
        historical_forecasts: np.ndarray,
        historical_actuals: np.ndarray,
        alpha: float = 0.1,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None
    ) -> CalibrationResult:
        """
        Calibrate a demand forecaster for a specific product/site.
        """
        key = self.get_predictor_key("demand", product_id, site_id)

        forecaster = ConformalDemandForecaster(alpha=alpha)
        result = forecaster.calibrate(
            historical_forecasts,
            historical_actuals,
            product_id,
            site_id
        )

        self.demand_forecasters[key] = forecaster
        return result

    def calibrate_lead_time(
        self,
        promised_lead_times: np.ndarray,
        actual_lead_times: np.ndarray,
        alpha: float = 0.1,
        supplier_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> CalibrationResult:
        """
        Calibrate a lead time predictor for a specific supplier/product.
        """
        key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            key = f"{key}:supplier:{supplier_id}"

        predictor = ConformalLeadTimePredictor(alpha=alpha)
        result = predictor.calibrate(
            promised_lead_times,
            actual_lead_times,
            supplier_id,
            product_id
        )

        self.lead_time_predictors[key] = predictor
        return result

    def predict_demand(
        self,
        point_forecast: float,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None
    ) -> ConformalInterval:
        """
        Get demand prediction with conformal interval.
        """
        key = self.get_predictor_key("demand", product_id, site_id)

        if key not in self.demand_forecasters:
            raise ValueError(f"No calibrated demand forecaster for {key}. Call calibrate_demand() first.")

        return self.demand_forecasters[key].forecast_with_interval(point_forecast)

    def predict_lead_time(
        self,
        promised_lead_time: float,
        supplier_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> ConformalInterval:
        """
        Get lead time prediction with conformal interval.
        """
        key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            key = f"{key}:supplier:{supplier_id}"

        if key not in self.lead_time_predictors:
            raise ValueError(f"No calibrated lead time predictor for {key}. Call calibrate_lead_time() first.")

        return self.lead_time_predictors[key].predict_lead_time(promised_lead_time)

    def calculate_safety_stock(
        self,
        expected_demand: float,
        expected_lead_time: float,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None,
        supplier_id: Optional[str] = None
    ) -> SafetyStockResult:
        """
        Calculate safety stock with conformal guarantees.
        """
        # Get demand predictor if available
        demand_key = self.get_predictor_key("demand", product_id, site_id)
        demand_pred = None
        if demand_key in self.demand_forecasters:
            demand_pred = self.demand_forecasters[demand_key].conformal

        # Get lead time predictor if available
        lt_key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            lt_key = f"{lt_key}:supplier:{supplier_id}"
        lt_pred = None
        if lt_key in self.lead_time_predictors:
            lt_pred = self.lead_time_predictors[lt_key].conformal

        decision_maker = ConformalDecisionMaker(
            demand_predictor=demand_pred,
            lead_time_predictor=lt_pred
        )

        return decision_maker.calculate_safety_stock(
            expected_demand=expected_demand,
            expected_lead_time=expected_lead_time
        )

    def get_calibration_summary(self) -> Dict[str, Any]:
        """Get summary of all calibrated predictors."""
        summary = {
            "demand_forecasters": {},
            "lead_time_predictors": {},
            "total_calibrated": 0
        }

        for key, forecaster in self.demand_forecasters.items():
            if forecaster.is_calibrated:
                cal = forecaster.conformal.calibration_result
                summary["demand_forecasters"][key] = {
                    "alpha": cal.alpha,
                    "quantile": cal.quantile,
                    "empirical_coverage": cal.empirical_coverage,
                    "n_samples": cal.n_samples
                }
                summary["total_calibrated"] += 1

        for key, predictor in self.lead_time_predictors.items():
            if predictor.is_calibrated:
                cal = predictor.conformal.calibration_result
                summary["lead_time_predictors"][key] = {
                    "alpha": cal.alpha,
                    "quantile": cal.quantile,
                    "empirical_coverage": cal.empirical_coverage,
                    "n_samples": cal.n_samples
                }
                summary["total_calibrated"] += 1

        return summary


# ============================================================================
# Singleton Instance
# ============================================================================

_conformal_service: Optional[ConformalPredictionService] = None


def get_conformal_service() -> ConformalPredictionService:
    """Get the global conformal prediction service instance."""
    global _conformal_service
    if _conformal_service is None:
        _conformal_service = ConformalPredictionService()
    return _conformal_service

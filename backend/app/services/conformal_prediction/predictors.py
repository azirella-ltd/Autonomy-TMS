"""
Specialized Conformal Predictors

Concrete implementations for supply chain prediction targets:
- ATP (Available to Promise)
- Demand Forecasting
- Lead Time Prediction
- Yield Prediction
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .engine import ConformalPredictionEngine, PredictionInterval
from .calibration import CalibrationStore, get_calibration_store

logger = logging.getLogger(__name__)


class SplitConformalPredictor:
    """
    Split Conformal Predictor - the simplest and most commonly used method.

    Uses absolute residuals |y - ŷ| as nonconformity scores.
    Prediction interval: [ŷ - q, ŷ + q] where q is the calibrated quantile.

    Guarantees: P(Y ∈ [ŷ - q, ŷ + q]) ≥ 1 - α
    """

    def __init__(
        self,
        target: str,
        coverage: float = 0.90,
        calibration_store: Optional[CalibrationStore] = None,
    ):
        self.target = target
        self.coverage = coverage
        self.engine = ConformalPredictionEngine(coverage=coverage, method="split")
        self.calibration_store = calibration_store or get_calibration_store()

    def calibrate_from_history(
        self,
        predictions: List[float],
        actuals: List[float],
    ):
        """
        Calibrate from historical prediction-actual pairs.

        Args:
            predictions: Historical point predictions
            actuals: Corresponding actual values
        """
        self.engine.reset_calibration()
        self.engine.add_calibration_batch(predictions, actuals)

        # Also store in calibration store for persistence
        self.calibration_store.add_batch(self.target, predictions, actuals)

        logger.info(
            f"Calibrated {self.target} predictor with {len(predictions)} points"
        )

    def predict(self, point_prediction: float) -> PredictionInterval:
        """
        Generate prediction interval for a point prediction.

        Args:
            point_prediction: The base point prediction

        Returns:
            PredictionInterval with guaranteed coverage
        """
        return self.engine.predict_interval(point_prediction)

    def update(self, prediction: float, actual: float) -> bool:
        """
        Update calibration with new observation.

        Args:
            prediction: Predicted value
            actual: Actual observed value

        Returns:
            Whether the prediction interval contained the actual
        """
        self.engine.add_calibration_point(prediction, actual)
        self.calibration_store.add(self.target, prediction, actual)

        # Get coverage for this point
        interval = self.predict(prediction)
        return interval.contains(actual)


class QuantileConformalPredictor:
    """
    Conformalized Quantile Regression (CQR) Predictor.

    Uses quantile regression models for lower/upper bounds, then
    conformally calibrates them for guaranteed coverage.

    Better for heteroscedastic data where uncertainty varies with features.
    """

    def __init__(
        self,
        target: str,
        coverage: float = 0.90,
        lower_quantile: float = 0.05,
        upper_quantile: float = 0.95,
    ):
        self.target = target
        self.coverage = coverage
        self.lower_quantile = lower_quantile
        self.upper_quantile = upper_quantile
        self.engine = ConformalPredictionEngine(coverage=coverage, method="quantile")

        # Quantile regression models (to be set externally)
        self._lower_model = None
        self._upper_model = None

    def set_quantile_models(
        self,
        lower_model,  # Callable[[features], float]
        upper_model,  # Callable[[features], float]
    ):
        """Set the quantile regression models."""
        self._lower_model = lower_model
        self._upper_model = upper_model
        self.engine.set_quantile_models(lower_model, upper_model)

    def calibrate(
        self,
        features_list: List[Dict],
        actuals: List[float],
    ):
        """
        Calibrate CQR from historical data.

        Args:
            features_list: List of feature dictionaries
            actuals: Corresponding actual values
        """
        if not self._lower_model or not self._upper_model:
            raise ValueError("Quantile models must be set before calibration")

        self.engine.reset_calibration()

        for features, actual in zip(features_list, actuals):
            q_lower = self._lower_model(features)
            q_upper = self._upper_model(features)
            # For CQR, we use the midpoint as the "prediction"
            prediction = (q_lower + q_upper) / 2
            self.engine.add_calibration_point(prediction, actual, features)

        logger.info(f"Calibrated CQR for {self.target} with {len(actuals)} points")

    def predict(
        self,
        features: Dict,
        point_prediction: Optional[float] = None,
    ) -> PredictionInterval:
        """
        Generate conformalized quantile prediction interval.

        Args:
            features: Feature dictionary for quantile models
            point_prediction: Optional point prediction (default: midpoint)

        Returns:
            PredictionInterval with guaranteed coverage
        """
        if point_prediction is None:
            q_lower = self._lower_model(features)
            q_upper = self._upper_model(features)
            point_prediction = (q_lower + q_upper) / 2

        return self.engine.predict_interval(point_prediction, features)


class AdaptiveConformalPredictor:
    """
    Adaptive Conformal Inference (ACI) Predictor.

    Automatically adjusts the significance level α over time to
    maintain target coverage under distribution shift.

    Ideal for non-stationary environments like supply chains where
    patterns change over time.
    """

    def __init__(
        self,
        target: str,
        coverage: float = 0.90,
        gamma: float = 0.005,
        window_size: int = 100,
    ):
        """
        Initialize adaptive conformal predictor.

        Args:
            target: Prediction target name
            coverage: Target coverage level
            gamma: Learning rate for alpha adjustment
            window_size: Window for rolling calibration
        """
        self.target = target
        self.coverage = coverage
        self.gamma = gamma
        self.window_size = window_size

        self.engine = ConformalPredictionEngine(
            coverage=coverage,
            method="adaptive",
            adaptive_gamma=gamma,
        )

        # Rolling window of recent observations
        self._recent_predictions: List[float] = []
        self._recent_actuals: List[float] = []

    def update_and_predict(
        self,
        current_prediction: float,
        previous_actual: Optional[float] = None,
    ) -> PredictionInterval:
        """
        Update calibration with previous actual and predict for current.

        This is the typical online prediction flow:
        1. Get prediction interval for current time
        2. Later, when actual is observed, update calibration

        Args:
            current_prediction: Point prediction for current time
            previous_actual: Actual value for previous prediction (if available)

        Returns:
            PredictionInterval for current prediction
        """
        # Update with previous observation if available
        if previous_actual is not None and self._recent_predictions:
            prev_pred = self._recent_predictions[-1]
            self.engine.add_calibration_point(prev_pred, previous_actual)

            # Update rolling window
            self._recent_actuals.append(previous_actual)
            if len(self._recent_actuals) > self.window_size:
                self._recent_actuals.pop(0)
                self._recent_predictions.pop(0)

            # Update coverage tracking
            interval = self.engine.predict_interval(prev_pred)
            self.engine.update_coverage(previous_actual, interval)

        # Store current prediction
        self._recent_predictions.append(current_prediction)
        if len(self._recent_predictions) > self.window_size + 1:
            self._recent_predictions.pop(0)

        # Return interval for current prediction
        return self.engine.predict_interval(current_prediction)

    def get_adaptive_alpha(self) -> float:
        """Get current adaptive alpha value."""
        return self.engine._adaptive_alpha

    def get_coverage_stats(self, window: Optional[int] = None):
        """Get coverage statistics."""
        return self.engine.get_coverage_stats(window)


@dataclass
class ATPConformalResult:
    """Result from conformal ATP prediction."""
    atp_point: float
    atp_lower: float
    atp_upper: float
    coverage: float
    method: str
    calibration_size: int
    interval_width: float
    is_calibrated: bool
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atp_point": self.atp_point,
            "atp_lower": self.atp_lower,
            "atp_upper": self.atp_upper,
            "coverage": self.coverage,
            "method": self.method,
            "calibration_size": self.calibration_size,
            "interval_width": self.interval_width,
            "is_calibrated": self.is_calibrated,
            "timestamp": self.timestamp.isoformat(),
        }


class ATPConformalPredictor:
    """
    Specialized conformal predictor for ATP (Available to Promise).

    ATP = On-Hand + Scheduled Receipts - Allocated Orders - Safety Stock

    The uncertainty comes from:
    - Lead time variability (scheduled receipts may arrive early/late)
    - Demand variability (allocated orders may change)
    - Yield variability (production may have scrap)

    This predictor provides prediction intervals with guaranteed coverage.
    """

    def __init__(
        self,
        coverage: float = 0.90,
        method: str = "adaptive",  # "split", "quantile", or "adaptive"
        gamma: float = 0.005,
    ):
        self.coverage = coverage
        self.method = method

        if method == "adaptive":
            self.predictor = AdaptiveConformalPredictor(
                target="atp",
                coverage=coverage,
                gamma=gamma,
            )
        elif method == "quantile":
            self.predictor = QuantileConformalPredictor(
                target="atp",
                coverage=coverage,
            )
        else:
            self.predictor = SplitConformalPredictor(
                target="atp",
                coverage=coverage,
            )

    def calibrate(
        self,
        historical_predictions: List[float],
        historical_actuals: List[float],
    ):
        """
        Calibrate from historical ATP predictions and actuals.

        Args:
            historical_predictions: Past ATP point predictions
            historical_actuals: Corresponding actual ATP values observed
        """
        if isinstance(self.predictor, SplitConformalPredictor):
            self.predictor.calibrate_from_history(
                historical_predictions, historical_actuals
            )
        elif isinstance(self.predictor, AdaptiveConformalPredictor):
            # For adaptive, add points one by one to simulate online learning
            for pred, actual in zip(historical_predictions, historical_actuals):
                self.predictor.update_and_predict(pred, actual if pred != historical_predictions[0] else None)

        logger.info(
            f"ATP conformal predictor calibrated with "
            f"{len(historical_predictions)} historical points"
        )

    def predict(
        self,
        atp_point_estimate: float,
        previous_actual: Optional[float] = None,
    ) -> ATPConformalResult:
        """
        Generate conformal prediction interval for ATP.

        Args:
            atp_point_estimate: Point estimate of ATP
            previous_actual: Previous actual ATP (for adaptive method)

        Returns:
            ATPConformalResult with guaranteed coverage interval
        """
        if isinstance(self.predictor, AdaptiveConformalPredictor):
            interval = self.predictor.update_and_predict(
                atp_point_estimate, previous_actual
            )
        else:
            interval = self.predictor.predict(atp_point_estimate)

        return ATPConformalResult(
            atp_point=interval.point_estimate,
            atp_lower=max(0, interval.lower),  # ATP can't be negative
            atp_upper=interval.upper,
            coverage=interval.coverage_target,
            method=interval.method,
            calibration_size=interval.calibration_size,
            interval_width=interval.width,
            is_calibrated=interval.calibration_size >= 30,
            timestamp=interval.timestamp,
        )

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get predictor diagnostics."""
        if isinstance(self.predictor, SplitConformalPredictor):
            return self.predictor.engine.get_diagnostics()
        elif isinstance(self.predictor, AdaptiveConformalPredictor):
            diag = self.predictor.engine.get_diagnostics()
            diag["adaptive_alpha"] = self.predictor.get_adaptive_alpha()
            return diag
        return {}


class DemandConformalPredictor:
    """
    Specialized conformal predictor for demand forecasting.

    Provides prediction intervals for demand forecasts with
    guaranteed coverage, adapting to forecast model performance.
    """

    def __init__(
        self,
        coverage: float = 0.90,
        use_adaptive: bool = True,
    ):
        self.coverage = coverage

        if use_adaptive:
            self.predictor = AdaptiveConformalPredictor(
                target="demand",
                coverage=coverage,
                gamma=0.01,  # Higher gamma for faster adaptation
            )
        else:
            self.predictor = SplitConformalPredictor(
                target="demand",
                coverage=coverage,
            )

    def predict(
        self,
        demand_forecast: float,
        previous_actual: Optional[float] = None,
    ) -> PredictionInterval:
        """
        Generate prediction interval for demand forecast.

        Args:
            demand_forecast: Point forecast of demand
            previous_actual: Previous actual demand (for updates)

        Returns:
            PredictionInterval with guaranteed coverage
        """
        if isinstance(self.predictor, AdaptiveConformalPredictor):
            interval = self.predictor.update_and_predict(
                demand_forecast, previous_actual
            )
        else:
            interval = self.predictor.predict(demand_forecast)

        # Demand can't be negative
        interval.lower = max(0, interval.lower)
        return interval


class LeadTimeConformalPredictor:
    """
    Specialized conformal predictor for lead time prediction.

    Provides prediction intervals for when shipments will arrive,
    accounting for transportation variability.
    """

    def __init__(
        self,
        coverage: float = 0.90,
    ):
        self.coverage = coverage
        self.predictor = SplitConformalPredictor(
            target="lead_time",
            coverage=coverage,
        )

    def calibrate(
        self,
        predicted_lead_times: List[float],
        actual_lead_times: List[float],
    ):
        """
        Calibrate from historical lead time predictions.

        Args:
            predicted_lead_times: Predicted lead times (days/rounds)
            actual_lead_times: Actual lead times observed
        """
        self.predictor.calibrate_from_history(
            predicted_lead_times, actual_lead_times
        )

    def predict_arrival_window(
        self,
        expected_lead_time: float,
        ship_date: Optional[datetime] = None,
    ) -> Tuple[float, float]:
        """
        Predict arrival time window with guaranteed coverage.

        Args:
            expected_lead_time: Expected lead time in days/rounds
            ship_date: Ship date for absolute arrival calculation

        Returns:
            Tuple of (earliest_arrival, latest_arrival) in same units
        """
        interval = self.predictor.predict(expected_lead_time)

        # Lead time must be positive
        earliest = max(0, interval.lower)
        latest = interval.upper

        return earliest, latest

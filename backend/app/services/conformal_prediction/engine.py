"""
Conformal Prediction Engine

Core engine for distribution-free prediction intervals with guaranteed coverage.
Supports multiple conformal prediction methods and automatic recalibration.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PredictionInterval:
    """Prediction interval with coverage guarantee."""
    lower: float
    upper: float
    point_estimate: float
    coverage_target: float
    method: str
    calibration_size: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def width(self) -> float:
        """Interval width."""
        return self.upper - self.lower

    @property
    def relative_width(self) -> float:
        """Width relative to point estimate."""
        if self.point_estimate == 0:
            return float('inf') if self.width > 0 else 0
        return self.width / abs(self.point_estimate)

    def contains(self, actual: float) -> bool:
        """Check if actual value falls within interval."""
        return self.lower <= actual <= self.upper

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "lower": self.lower,
            "upper": self.upper,
            "point_estimate": self.point_estimate,
            "coverage_target": self.coverage_target,
            "method": self.method,
            "calibration_size": self.calibration_size,
            "width": self.width,
            "relative_width": self.relative_width,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CoverageStats:
    """Coverage statistics for monitoring calibration."""
    target_coverage: float
    empirical_coverage: float
    n_predictions: int
    n_covered: int
    coverage_gap: float = field(init=False)
    is_calibrated: bool = field(init=False)

    def __post_init__(self):
        self.coverage_gap = self.empirical_coverage - self.target_coverage
        # Consider calibrated if within 2% of target
        self.is_calibrated = abs(self.coverage_gap) <= 0.02

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_coverage": self.target_coverage,
            "empirical_coverage": self.empirical_coverage,
            "n_predictions": self.n_predictions,
            "n_covered": self.n_covered,
            "coverage_gap": self.coverage_gap,
            "is_calibrated": self.is_calibrated,
        }


class ConformalPredictionEngine:
    """
    Main engine for conformal prediction.

    Supports:
    - Split Conformal Prediction (SCP)
    - Conformalized Quantile Regression (CQR)
    - Adaptive Conformal Inference (ACI) for distribution shift

    Usage:
        engine = ConformalPredictionEngine(coverage=0.90)

        # Add calibration data
        for pred, actual in historical_data:
            engine.add_calibration_point(pred, actual)

        # Get prediction interval
        interval = engine.predict_interval(new_prediction)
        # interval.lower, interval.upper have 90% coverage guarantee
    """

    def __init__(
        self,
        coverage: float = 0.90,
        method: str = "split",
        min_calibration_size: int = 30,
        adaptive_gamma: float = 0.005,
    ):
        """
        Initialize conformal prediction engine.

        Args:
            coverage: Target coverage level (e.g., 0.90 for 90%)
            method: "split" (SCP), "quantile" (CQR), or "adaptive" (ACI)
            min_calibration_size: Minimum calibration points required
            adaptive_gamma: Learning rate for adaptive conformal (ACI)
        """
        if not 0 < coverage < 1:
            raise ValueError("Coverage must be between 0 and 1")

        self.coverage = coverage
        self.alpha = 1 - coverage  # Miscoverage rate
        self.method = method
        self.min_calibration_size = min_calibration_size
        self.adaptive_gamma = adaptive_gamma

        # Calibration data
        self._predictions: List[float] = []
        self._actuals: List[float] = []
        self._nonconformity_scores: List[float] = []

        # Adaptive state (for ACI)
        self._adaptive_alpha = self.alpha
        self._coverage_history: List[bool] = []

        # Quantile regression models (for CQR)
        self._lower_quantile_model: Optional[Callable] = None
        self._upper_quantile_model: Optional[Callable] = None

        logger.info(
            f"ConformalPredictionEngine initialized: "
            f"coverage={coverage}, method={method}"
        )

    @property
    def calibration_size(self) -> int:
        """Number of calibration points."""
        return len(self._nonconformity_scores)

    @property
    def is_calibrated(self) -> bool:
        """Check if engine has sufficient calibration data."""
        return self.calibration_size >= self.min_calibration_size

    def add_calibration_point(
        self,
        prediction: float,
        actual: float,
        features: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Add a calibration point (prediction, actual) pair.

        Args:
            prediction: Point prediction
            actual: Actual observed value
            features: Optional feature dict for CQR method

        Returns:
            Nonconformity score for this point
        """
        self._predictions.append(prediction)
        self._actuals.append(actual)

        # Compute nonconformity score based on method
        if self.method == "split":
            # Standard absolute residual
            score = abs(actual - prediction)
        elif self.method == "quantile":
            # For CQR, score is max of violations from quantile bounds
            if self._lower_quantile_model and self._upper_quantile_model:
                q_lower = self._lower_quantile_model(features)
                q_upper = self._upper_quantile_model(features)
                score = max(q_lower - actual, actual - q_upper)
            else:
                # Fallback to absolute residual if models not set
                score = abs(actual - prediction)
        else:  # adaptive
            score = abs(actual - prediction)

        self._nonconformity_scores.append(score)

        logger.debug(
            f"Added calibration point: pred={prediction:.2f}, "
            f"actual={actual:.2f}, score={score:.2f}"
        )

        return score

    def add_calibration_batch(
        self,
        predictions: List[float],
        actuals: List[float],
    ) -> List[float]:
        """
        Add multiple calibration points at once.

        Args:
            predictions: List of predictions
            actuals: List of actual values

        Returns:
            List of nonconformity scores
        """
        if len(predictions) != len(actuals):
            raise ValueError("Predictions and actuals must have same length")

        scores = []
        for pred, actual in zip(predictions, actuals):
            score = self.add_calibration_point(pred, actual)
            scores.append(score)

        return scores

    def compute_quantile(self, alpha: Optional[float] = None) -> float:
        """
        Compute the (1-alpha) quantile of nonconformity scores.

        This is the critical value for constructing prediction intervals.

        Args:
            alpha: Miscoverage rate (default: self.alpha)

        Returns:
            Quantile value q such that P(score <= q) >= 1-alpha
        """
        if not self.is_calibrated:
            logger.warning(
                f"Insufficient calibration data: {self.calibration_size} < "
                f"{self.min_calibration_size}. Using fallback."
            )
            # Fallback: use empirical standard deviation
            if len(self._nonconformity_scores) > 0:
                return np.percentile(self._nonconformity_scores, 95)
            return 0.0

        if alpha is None:
            alpha = self._adaptive_alpha if self.method == "adaptive" else self.alpha

        n = len(self._nonconformity_scores)
        scores = np.array(self._nonconformity_scores)

        # Compute (1 - alpha)(1 + 1/n) quantile for finite-sample validity
        # This ensures coverage >= 1 - alpha for any sample size
        adjusted_quantile = (1 - alpha) * (1 + 1 / n)
        adjusted_quantile = min(adjusted_quantile, 1.0)  # Cap at 1

        q = np.quantile(scores, adjusted_quantile)

        logger.debug(
            f"Computed quantile: alpha={alpha:.3f}, n={n}, "
            f"adjusted_q={adjusted_quantile:.3f}, q={q:.2f}"
        )

        return float(q)

    def predict_interval(
        self,
        prediction: float,
        features: Optional[Dict[str, Any]] = None,
    ) -> PredictionInterval:
        """
        Construct prediction interval around a point prediction.

        For Split Conformal: [pred - q, pred + q]
        For CQR: [q_lower - q, q_upper + q]

        Args:
            prediction: Point prediction
            features: Optional features for CQR method

        Returns:
            PredictionInterval with guaranteed coverage
        """
        q = self.compute_quantile()

        if self.method == "quantile" and self._lower_quantile_model:
            # CQR: Use quantile regression predictions as base
            q_lower = self._lower_quantile_model(features)
            q_upper = self._upper_quantile_model(features)
            lower = q_lower - q
            upper = q_upper + q
        else:
            # SCP/Adaptive: Symmetric interval around point prediction
            lower = prediction - q
            upper = prediction + q

        return PredictionInterval(
            lower=lower,
            upper=upper,
            point_estimate=prediction,
            coverage_target=self.coverage,
            method=self.method,
            calibration_size=self.calibration_size,
        )

    def update_coverage(self, actual: float, interval: PredictionInterval) -> bool:
        """
        Update coverage tracking after observing actual value.

        For adaptive method, this adjusts alpha based on coverage.

        Args:
            actual: Observed actual value
            interval: Previously predicted interval

        Returns:
            Whether actual was covered by interval
        """
        covered = interval.contains(actual)
        self._coverage_history.append(covered)

        if self.method == "adaptive":
            # Adaptive Conformal Inference (ACI) update
            # If covered, decrease alpha (wider intervals)
            # If not covered, increase alpha (narrower intervals)
            if covered:
                self._adaptive_alpha = self._adaptive_alpha - self.adaptive_gamma * self.alpha
            else:
                self._adaptive_alpha = self._adaptive_alpha + self.adaptive_gamma * (1 - self.alpha)

            # Clip to valid range
            self._adaptive_alpha = max(0.001, min(0.999, self._adaptive_alpha))

            logger.debug(
                f"Adaptive update: covered={covered}, "
                f"new_alpha={self._adaptive_alpha:.4f}"
            )

        return covered

    def get_coverage_stats(self, window: Optional[int] = None) -> CoverageStats:
        """
        Compute empirical coverage statistics.

        Args:
            window: Only consider last N predictions (None = all)

        Returns:
            CoverageStats with target vs empirical coverage
        """
        if not self._coverage_history:
            return CoverageStats(
                target_coverage=self.coverage,
                empirical_coverage=0.0,
                n_predictions=0,
                n_covered=0,
            )

        history = self._coverage_history
        if window:
            history = history[-window:]

        n_covered = sum(history)
        n_total = len(history)
        empirical = n_covered / n_total if n_total > 0 else 0.0

        return CoverageStats(
            target_coverage=self.coverage,
            empirical_coverage=empirical,
            n_predictions=n_total,
            n_covered=n_covered,
        )

    def set_quantile_models(
        self,
        lower_model: Callable[[Dict], float],
        upper_model: Callable[[Dict], float],
    ):
        """
        Set quantile regression models for CQR method.

        Args:
            lower_model: Function that returns lower quantile prediction
            upper_model: Function that returns upper quantile prediction
        """
        self._lower_quantile_model = lower_model
        self._upper_quantile_model = upper_model
        logger.info("Quantile models set for CQR method")

    def reset_calibration(self):
        """Clear all calibration data."""
        self._predictions.clear()
        self._actuals.clear()
        self._nonconformity_scores.clear()
        self._coverage_history.clear()
        self._adaptive_alpha = self.alpha
        logger.info("Calibration data reset")

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get diagnostic information about the engine state."""
        scores = np.array(self._nonconformity_scores) if self._nonconformity_scores else np.array([])

        return {
            "method": self.method,
            "target_coverage": self.coverage,
            "calibration_size": self.calibration_size,
            "min_calibration_size": self.min_calibration_size,
            "is_calibrated": self.is_calibrated,
            "current_alpha": self._adaptive_alpha if self.method == "adaptive" else self.alpha,
            "nonconformity_scores": {
                "mean": float(scores.mean()) if len(scores) > 0 else None,
                "std": float(scores.std()) if len(scores) > 0 else None,
                "min": float(scores.min()) if len(scores) > 0 else None,
                "max": float(scores.max()) if len(scores) > 0 else None,
                "p50": float(np.percentile(scores, 50)) if len(scores) > 0 else None,
                "p90": float(np.percentile(scores, 90)) if len(scores) > 0 else None,
                "p95": float(np.percentile(scores, 95)) if len(scores) > 0 else None,
            },
            "coverage_stats": self.get_coverage_stats().to_dict() if self._coverage_history else None,
        }


class MultiTargetConformalEngine:
    """
    Manages multiple conformal prediction engines for different targets.

    Useful for supply chain where we need separate calibration for:
    - ATP predictions
    - Demand forecasts
    - Lead time predictions
    - Yield predictions
    """

    def __init__(self, default_coverage: float = 0.90):
        self.default_coverage = default_coverage
        self._engines: Dict[str, ConformalPredictionEngine] = {}

    def get_or_create_engine(
        self,
        target: str,
        coverage: Optional[float] = None,
        method: str = "split",
    ) -> ConformalPredictionEngine:
        """
        Get existing engine or create new one for target.

        Args:
            target: Target name (e.g., "atp", "demand", "lead_time")
            coverage: Coverage level (default: default_coverage)
            method: Conformal method

        Returns:
            ConformalPredictionEngine for the target
        """
        if target not in self._engines:
            self._engines[target] = ConformalPredictionEngine(
                coverage=coverage or self.default_coverage,
                method=method,
            )
            logger.info(f"Created conformal engine for target: {target}")

        return self._engines[target]

    def get_all_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        """Get diagnostics for all engines."""
        return {
            target: engine.get_diagnostics()
            for target, engine in self._engines.items()
        }

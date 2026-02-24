"""
Calibration Data Store

Persists historical prediction-actual pairs for conformal calibration.
Supports multiple prediction targets and automatic data expiry.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class NonconformityScore:
    """A single nonconformity score with metadata."""
    prediction: float
    actual: float
    score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    features: Optional[Dict[str, Any]] = None
    target: str = "default"
    source: str = "unknown"  # scenario_id, config_id, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction": self.prediction,
            "actual": self.actual,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
            "features": self.features,
            "target": self.target,
            "source": self.source,
        }


class CalibrationStore:
    """
    In-memory store for calibration data with optional persistence.

    Features:
    - Rolling window of recent calibration points
    - Stratified storage by target and source
    - Automatic expiry of old data
    - Statistics computation

    For production, extend with database persistence.
    """

    def __init__(
        self,
        max_points_per_target: int = 1000,
        expiry_days: Optional[int] = 30,
    ):
        """
        Initialize calibration store.

        Args:
            max_points_per_target: Maximum calibration points per target
            expiry_days: Auto-expire points older than this (None = no expiry)
        """
        self.max_points = max_points_per_target
        self.expiry_days = expiry_days

        # Storage: target -> deque of NonconformityScore
        self._data: Dict[str, deque] = {}

        logger.info(
            f"CalibrationStore initialized: max_points={max_points_per_target}, "
            f"expiry_days={expiry_days}"
        )

    def add(
        self,
        target: str,
        prediction: float,
        actual: float,
        features: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        timestamp: Optional[datetime] = None,
    ) -> NonconformityScore:
        """
        Add a calibration point.

        Args:
            target: Prediction target (e.g., "atp", "demand", "lead_time")
            prediction: Point prediction value
            actual: Actual observed value
            features: Optional feature dictionary
            source: Source identifier (e.g., scenario_id)
            timestamp: Timestamp (default: now)

        Returns:
            NonconformityScore object
        """
        if target not in self._data:
            self._data[target] = deque(maxlen=self.max_points)

        score = abs(actual - prediction)
        entry = NonconformityScore(
            prediction=prediction,
            actual=actual,
            score=score,
            timestamp=timestamp or datetime.utcnow(),
            features=features,
            target=target,
            source=source,
        )

        self._data[target].append(entry)

        logger.debug(
            f"Added calibration point: target={target}, pred={prediction:.2f}, "
            f"actual={actual:.2f}, score={score:.2f}"
        )

        return entry

    def add_batch(
        self,
        target: str,
        predictions: List[float],
        actuals: List[float],
        source: str = "unknown",
    ) -> List[NonconformityScore]:
        """Add multiple calibration points at once."""
        if len(predictions) != len(actuals):
            raise ValueError("Predictions and actuals must have same length")

        return [
            self.add(target, pred, actual, source=source)
            for pred, actual in zip(predictions, actuals)
        ]

    def get_scores(
        self,
        target: str,
        max_age_days: Optional[int] = None,
        source: Optional[str] = None,
    ) -> List[float]:
        """
        Get nonconformity scores for a target.

        Args:
            target: Prediction target
            max_age_days: Only include points from last N days
            source: Filter by source

        Returns:
            List of nonconformity scores
        """
        if target not in self._data:
            return []

        entries = list(self._data[target])

        # Apply filters
        if max_age_days:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            entries = [e for e in entries if e.timestamp >= cutoff]

        if source:
            entries = [e for e in entries if e.source == source]

        return [e.score for e in entries]

    def get_pairs(
        self,
        target: str,
        max_age_days: Optional[int] = None,
    ) -> Tuple[List[float], List[float]]:
        """
        Get (predictions, actuals) pairs for a target.

        Returns:
            Tuple of (predictions list, actuals list)
        """
        if target not in self._data:
            return [], []

        entries = list(self._data[target])

        if max_age_days:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            entries = [e for e in entries if e.timestamp >= cutoff]

        predictions = [e.prediction for e in entries]
        actuals = [e.actual for e in entries]

        return predictions, actuals

    def get_statistics(self, target: str) -> Dict[str, Any]:
        """
        Compute statistics for a target's calibration data.

        Returns:
            Dictionary with statistics
        """
        scores = self.get_scores(target)

        if not scores:
            return {
                "target": target,
                "count": 0,
                "mean_score": None,
                "std_score": None,
                "quantiles": None,
            }

        scores_arr = np.array(scores)

        return {
            "target": target,
            "count": len(scores),
            "mean_score": float(scores_arr.mean()),
            "std_score": float(scores_arr.std()),
            "min_score": float(scores_arr.min()),
            "max_score": float(scores_arr.max()),
            "quantiles": {
                "p10": float(np.percentile(scores_arr, 10)),
                "p25": float(np.percentile(scores_arr, 25)),
                "p50": float(np.percentile(scores_arr, 50)),
                "p75": float(np.percentile(scores_arr, 75)),
                "p90": float(np.percentile(scores_arr, 90)),
                "p95": float(np.percentile(scores_arr, 95)),
            },
        }

    def get_all_targets(self) -> List[str]:
        """Get list of all targets with calibration data."""
        return list(self._data.keys())

    def get_count(self, target: str) -> int:
        """Get number of calibration points for a target."""
        return len(self._data.get(target, []))

    def cleanup_expired(self):
        """Remove expired calibration points."""
        if not self.expiry_days:
            return

        cutoff = datetime.utcnow() - timedelta(days=self.expiry_days)
        removed_count = 0

        for target in self._data:
            original_len = len(self._data[target])
            self._data[target] = deque(
                (e for e in self._data[target] if e.timestamp >= cutoff),
                maxlen=self.max_points,
            )
            removed_count += original_len - len(self._data[target])

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} expired calibration points")

    def clear(self, target: Optional[str] = None):
        """
        Clear calibration data.

        Args:
            target: Clear specific target, or all if None
        """
        if target:
            if target in self._data:
                self._data[target].clear()
                logger.info(f"Cleared calibration data for target: {target}")
        else:
            self._data.clear()
            logger.info("Cleared all calibration data")

    def export_to_dict(self, target: str) -> List[Dict[str, Any]]:
        """Export calibration data for a target."""
        if target not in self._data:
            return []
        return [e.to_dict() for e in self._data[target]]


# Global calibration store instance
_global_calibration_store: Optional[CalibrationStore] = None


def get_calibration_store() -> CalibrationStore:
    """Get or create the global calibration store."""
    global _global_calibration_store
    if _global_calibration_store is None:
        _global_calibration_store = CalibrationStore()
    return _global_calibration_store

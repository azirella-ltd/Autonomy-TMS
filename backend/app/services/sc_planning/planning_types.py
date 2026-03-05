"""
Shared data structures for the 3-step planning pipeline.

These types propagate conformal prediction intervals through:
  DemandProcessor -> InventoryTargetCalculator -> NetRequirementsCalculator

Each estimate wraps a scalar point value with an optional conformal interval.
When intervals are present, they carry a distribution-free coverage guarantee
(e.g., 0.90 means "the true value falls within [lower, upper] with ≥90% probability").

Backward compatibility: callers that only need the scalar call .to_float() or .point.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Tuple


@dataclass
class DemandEstimate:
    """
    A demand value with optional conformal interval.

    The point estimate is always present (backward compatible).
    The interval is populated when a calibrated conformal predictor
    exists for this product-site combination, or when the Forecast
    model has stored P10/P90 percentiles.
    """
    point: float
    lower: Optional[float] = None
    upper: Optional[float] = None
    coverage: Optional[float] = None  # e.g., 0.90 for 90% guarantee
    method: Optional[str] = None      # "adaptive", "split", "stored_percentiles"
    source: str = "forecast"          # "forecast", "actual", "net"

    @property
    def has_interval(self) -> bool:
        return self.lower is not None and self.upper is not None

    @property
    def width(self) -> float:
        if not self.has_interval:
            return 0.0
        return self.upper - self.lower

    def to_float(self) -> float:
        """Backward-compatible: extract the scalar value."""
        return self.point


@dataclass
class LeadTimeEstimate:
    """
    A lead time value (in days) with optional conformal interval.
    """
    point: float
    lower: Optional[float] = None
    upper: Optional[float] = None
    coverage: Optional[float] = None
    supplier_id: Optional[str] = None

    @property
    def has_interval(self) -> bool:
        return self.lower is not None and self.upper is not None

    def to_float(self) -> float:
        return self.point


@dataclass
class InventoryTargetEstimate:
    """
    An inventory target with optional interval and policy metadata.
    """
    target: float
    safety_stock: float = 0.0
    reorder_point: float = 0.0
    target_upper: Optional[float] = None   # Target when lead_time is at upper bound
    policy_type: Optional[str] = None      # "sl", "conformal", "sl_conformal_fitted", etc.
    joint_coverage: Optional[float] = None

    def to_float(self) -> float:
        return self.target


# Type aliases for the two pipeline shapes
DemandDict = Dict[Tuple[str, str, date], float]
DemandEstimateDict = Dict[Tuple[str, str, date], DemandEstimate]
TargetDict = Dict[Tuple[str, str], float]
TargetEstimateDict = Dict[Tuple[str, str], InventoryTargetEstimate]

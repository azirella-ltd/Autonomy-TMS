"""
Belief State Management for Powell Framework

Belief state contains:
- Point estimates (forecasts)
- Uncertainty quantification (conformal intervals)
- Parameter distributions (Bayesian posteriors)

Powell's framework separates physical state (inventory, orders) from
belief state (what we believe about uncertain quantities).

Key Features:
- Conformal prediction integration for distribution-free intervals
- Adaptive Conformal Inference (ACI) for non-stationary demand
- Coverage monitoring and automatic recalibration

References:
- Angelopoulos & Bates (2021). A Gentle Introduction to Conformal Prediction
- Gibbs & Candès (2021). Adaptive Conformal Inference Under Distribution Shift
- Powell (2022) Sequential Decision Analytics, Chapter 5 on Belief States
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConformalInterval:
    """
    Conformal prediction interval with coverage guarantee.

    Unlike traditional confidence intervals (which require distributional assumptions),
    conformal intervals provide distribution-free coverage guarantees:
    P(Y ∈ [lower, upper]) ≥ 1 - α

    This is achieved through the conformal prediction framework.
    """
    lower: float
    upper: float
    coverage: float  # e.g., 0.90 for 90% coverage
    method: str  # 'split_conformal', 'aci', 'enbpi', 'cqr'
    point_estimate: Optional[float] = None

    @property
    def width(self) -> float:
        """Width of the interval"""
        return self.upper - self.lower

    @property
    def midpoint(self) -> float:
        """Midpoint of the interval"""
        return (self.lower + self.upper) / 2

    @property
    def half_width(self) -> float:
        """Half-width (margin of error)"""
        return self.width / 2

    def contains(self, value: float) -> bool:
        """Check if value is within interval"""
        return self.lower <= value <= self.upper

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "lower": self.lower,
            "upper": self.upper,
            "coverage": self.coverage,
            "method": self.method,
            "point_estimate": self.point_estimate,
            "width": self.width,
        }


@dataclass
class BeliefState:
    """
    Powell's belief state: What we believe about uncertain quantities.

    Separate from physical state (inventory, orders) which is known with certainty.
    Belief state captures our uncertainty about:
    - Future demand
    - Supplier lead times
    - Manufacturing yields
    - Forecast errors/bias
    """
    # Demand beliefs
    demand_forecast: float
    demand_interval: Optional[ConformalInterval] = None
    demand_distribution_type: str = "unknown"  # For parametric fallback

    # Lead time beliefs
    lead_time_estimate: float = 0.0
    lead_time_interval: Optional[ConformalInterval] = None

    # Yield beliefs (manufacturing)
    yield_estimate: float = 100.0  # Percentage
    yield_interval: Optional[ConformalInterval] = None

    # Forecast error beliefs (for bias correction)
    forecast_bias_estimate: float = 0.0
    forecast_bias_interval: Optional[ConformalInterval] = None

    # Tracking for adaptive conformal prediction
    recent_residuals: List[float] = field(default_factory=list)
    coverage_history: List[bool] = field(default_factory=list)

    # Entity identification
    entity_type: str = "demand"  # 'demand', 'lead_time', 'yield'
    entity_id: Optional[str] = None

    def get_robust_demand(self, risk_level: str = 'moderate') -> float:
        """
        Get demand estimate based on risk preference.

        Powell's framework supports different risk attitudes through
        the objective function. This method provides a simple interface
        for risk-adjusted demand estimates.

        Args:
            risk_level:
                - 'aggressive': Use P50 (midpoint) - accept stockout risk
                - 'moderate': Use P75 (upper quartile) - balanced
                - 'conservative': Use P90 (upper bound) - minimize stockouts

        Returns:
            Risk-adjusted demand estimate
        """
        if self.demand_interval is None:
            return self.demand_forecast

        if risk_level == 'aggressive':
            return self.demand_interval.midpoint
        elif risk_level == 'moderate':
            # Interpolate to ~75th percentile
            return self.demand_interval.lower + 0.75 * self.demand_interval.width
        else:  # conservative
            return self.demand_interval.upper

    def get_robust_lead_time(self, risk_level: str = 'moderate') -> float:
        """Get risk-adjusted lead time estimate"""
        if self.lead_time_interval is None:
            return self.lead_time_estimate

        if risk_level == 'aggressive':
            return self.lead_time_interval.lower
        elif risk_level == 'moderate':
            return self.lead_time_interval.midpoint
        else:  # conservative
            return self.lead_time_interval.upper

    def update_with_observation(self, actual_value: float, forecast: Optional[float] = None):
        """
        Update belief state with new observation (for adaptive conformal).

        This is crucial for handling non-stationarity. When actual values
        consistently fall outside predicted intervals, we need to adapt.

        Args:
            actual_value: Observed actual value
            forecast: Point forecast (uses stored forecast if None)
        """
        if forecast is None:
            forecast = self.demand_forecast

        # Track residual
        residual = actual_value - forecast
        self.recent_residuals.append(residual)

        # Keep last 100 residuals (sliding window)
        if len(self.recent_residuals) > 100:
            self.recent_residuals = self.recent_residuals[-100:]

        # Track coverage if interval exists
        if self.demand_interval is not None:
            covered = self.demand_interval.contains(actual_value)
            self.coverage_history.append(covered)

            if len(self.coverage_history) > 100:
                self.coverage_history = self.coverage_history[-100:]

    @property
    def empirical_coverage(self) -> Optional[float]:
        """Actual coverage rate from observations"""
        if len(self.coverage_history) < 10:
            return None
        return sum(self.coverage_history) / len(self.coverage_history)

    @property
    def needs_recalibration(self) -> bool:
        """Check if intervals need recalibration"""
        if self.demand_interval is None:
            return True

        emp_cov = self.empirical_coverage
        if emp_cov is None:
            return False

        # Recalibrate if empirical coverage deviates significantly from target
        target = self.demand_interval.coverage
        deviation = abs(emp_cov - target)
        return deviation > 0.05  # 5% deviation threshold

    def to_dict(self) -> Dict[str, Any]:
        """Serialize belief state"""
        return {
            "demand_forecast": self.demand_forecast,
            "demand_interval": self.demand_interval.to_dict() if self.demand_interval else None,
            "lead_time_estimate": self.lead_time_estimate,
            "yield_estimate": self.yield_estimate,
            "forecast_bias_estimate": self.forecast_bias_estimate,
            "empirical_coverage": self.empirical_coverage,
            "needs_recalibration": self.needs_recalibration,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
        }


class AdaptiveConformalPredictor:
    """
    Adaptive Conformal Inference (ACI) for non-stationary demand.

    Standard conformal prediction assumes exchangeability (roughly, stationarity).
    ACI relaxes this by adapting interval width based on observed coverage.

    If we're over-covering (intervals too wide), we narrow them.
    If we're under-covering (intervals too narrow), we widen them.

    This is Powell's recommendation for belief state construction
    under distribution shift.

    Reference: Gibbs & Candès (2021). Adaptive Conformal Inference
    """

    def __init__(
        self,
        target_coverage: float = 0.90,
        gamma: float = 0.01,
        min_alpha: float = 0.01,
        max_alpha: float = 0.50
    ):
        """
        Initialize ACI predictor.

        Args:
            target_coverage: Desired coverage probability (e.g., 0.90)
            gamma: Learning rate for coverage adjustment
            min_alpha: Minimum miscoverage rate (widest intervals)
            max_alpha: Maximum miscoverage rate (narrowest intervals)
        """
        self.target_coverage = target_coverage
        self.gamma = gamma
        self.min_alpha = min_alpha
        self.max_alpha = max_alpha
        self.alpha = 1 - target_coverage  # Current miscoverage rate

    def update_alpha(self, covered: bool):
        """
        Online update of miscoverage rate.

        ACI update rule:
        α_{t+1} = α_t + γ * (α_t - err_t)

        where err_t = 1 if not covered, 0 if covered.
        """
        err_t = 0 if covered else 1
        self.alpha = self.alpha + self.gamma * (self.alpha - err_t)
        self.alpha = max(self.min_alpha, min(self.max_alpha, self.alpha))

    @property
    def current_coverage(self) -> float:
        """Current target coverage based on adapted alpha"""
        return 1 - self.alpha

    def get_interval(
        self,
        point_forecast: float,
        residuals: List[float],
        base_model_interval: Optional[Tuple[float, float]] = None
    ) -> ConformalInterval:
        """
        Compute conformal interval with adaptive width.

        Uses quantile of absolute residuals as the interval half-width,
        with the quantile level adapting based on observed coverage.

        Args:
            point_forecast: Point prediction
            residuals: Historical forecast residuals
            base_model_interval: Optional interval from underlying model

        Returns:
            ConformalInterval with coverage guarantee
        """
        if len(residuals) < 10:
            # Not enough data, use wide interval
            width = abs(point_forecast) * 0.5  # 50% of forecast
            return ConformalInterval(
                lower=max(0, point_forecast - width),
                upper=point_forecast + width,
                coverage=self.target_coverage,
                method='fallback',
                point_estimate=point_forecast,
            )

        # Compute quantile of absolute residuals
        abs_residuals = [abs(r) for r in residuals]
        quantile_level = 1 - self.alpha

        # Conformal quantile calculation
        n = len(abs_residuals)
        quantile_index = int(np.ceil(quantile_level * (n + 1))) - 1
        quantile_index = max(0, min(n - 1, quantile_index))
        sorted_residuals = sorted(abs_residuals)
        width = sorted_residuals[quantile_index]

        return ConformalInterval(
            lower=max(0, point_forecast - width),
            upper=point_forecast + width,
            coverage=1 - self.alpha,
            method='aci',
            point_estimate=point_forecast,
        )


class BeliefStateManager:
    """
    Manages belief states across supply chain entities.

    Powell's framework requires tracking uncertainty for all relevant
    quantities. This manager coordinates belief states across:
    - Multiple products (SKUs)
    - Multiple locations (sites)
    - Multiple time horizons
    """

    def __init__(
        self,
        default_coverage: float = 0.90,
        use_adaptive: bool = True
    ):
        """
        Initialize belief state manager.

        Args:
            default_coverage: Default coverage for conformal intervals
            use_adaptive: Whether to use adaptive conformal inference
        """
        self.default_coverage = default_coverage
        self.use_adaptive = use_adaptive

        # Storage for belief states by entity
        self.belief_states: Dict[str, BeliefState] = {}

        # Adaptive predictors by entity
        self.adaptive_predictors: Dict[str, AdaptiveConformalPredictor] = {}

    def get_or_create_belief(
        self,
        entity_type: str,
        entity_id: str,
        initial_forecast: Optional[float] = None
    ) -> BeliefState:
        """
        Get or create belief state for entity.

        Args:
            entity_type: Type of entity ('demand', 'lead_time', 'yield')
            entity_id: Unique identifier (e.g., product_id, supplier_id)
            initial_forecast: Initial point forecast

        Returns:
            BeliefState for the entity
        """
        key = f"{entity_type}_{entity_id}"

        if key not in self.belief_states:
            self.belief_states[key] = BeliefState(
                demand_forecast=initial_forecast or 0.0,
                entity_type=entity_type,
                entity_id=entity_id,
            )

            if self.use_adaptive:
                self.adaptive_predictors[key] = AdaptiveConformalPredictor(
                    target_coverage=self.default_coverage
                )

        return self.belief_states[key]

    def update_belief(
        self,
        entity_type: str,
        entity_id: str,
        new_forecast: float,
        actual_value: Optional[float] = None,
        residuals: Optional[List[float]] = None
    ) -> BeliefState:
        """
        Update belief state with new information.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            new_forecast: New point forecast
            actual_value: Actual observed value (for updating residuals)
            residuals: Historical residuals for interval calculation

        Returns:
            Updated BeliefState
        """
        key = f"{entity_type}_{entity_id}"
        belief = self.get_or_create_belief(entity_type, entity_id, new_forecast)

        # Update point forecast
        belief.demand_forecast = new_forecast

        # Update with observation if provided
        if actual_value is not None:
            belief.update_with_observation(actual_value, new_forecast)

            # Update adaptive predictor
            if key in self.adaptive_predictors and belief.demand_interval is not None:
                covered = belief.demand_interval.contains(actual_value)
                self.adaptive_predictors[key].update_alpha(covered)

        # Compute new interval
        if residuals is not None or belief.recent_residuals:
            use_residuals = residuals or belief.recent_residuals
            if key in self.adaptive_predictors:
                belief.demand_interval = self.adaptive_predictors[key].get_interval(
                    new_forecast, use_residuals
                )
            else:
                # Non-adaptive interval
                belief.demand_interval = self._compute_standard_interval(
                    new_forecast, use_residuals
                )

        return belief

    def _compute_standard_interval(
        self,
        forecast: float,
        residuals: List[float]
    ) -> ConformalInterval:
        """Compute standard (non-adaptive) conformal interval"""
        if len(residuals) < 10:
            width = abs(forecast) * 0.3
            return ConformalInterval(
                lower=max(0, forecast - width),
                upper=forecast + width,
                coverage=self.default_coverage,
                method='fallback',
                point_estimate=forecast,
            )

        abs_residuals = [abs(r) for r in residuals]
        quantile_level = self.default_coverage
        quantile_index = int(np.ceil(quantile_level * (len(abs_residuals) + 1))) - 1
        quantile_index = max(0, min(len(abs_residuals) - 1, quantile_index))
        sorted_residuals = sorted(abs_residuals)
        width = sorted_residuals[quantile_index]

        return ConformalInterval(
            lower=max(0, forecast - width),
            upper=forecast + width,
            coverage=self.default_coverage,
            method='split_conformal',
            point_estimate=forecast,
        )

    def get_all_beliefs(self) -> Dict[str, Dict[str, Any]]:
        """Get all belief states as dictionaries"""
        return {key: belief.to_dict() for key, belief in self.belief_states.items()}

    def check_recalibration_needed(self) -> List[str]:
        """Get list of entities needing interval recalibration"""
        return [
            key for key, belief in self.belief_states.items()
            if belief.needs_recalibration
        ]

    def integrate_with_conformal_service(self, conformal_service: Any):
        """
        Integrate with the SupplyChainConformalSuite.

        When the suite has calibrated predictors, use those intervals
        for the corresponding belief states instead of basic estimates.
        """
        from app.services.conformal_prediction.suite import SupplyChainConformalSuite

        if not isinstance(conformal_service, SupplyChainConformalSuite):
            logger.warning(
                f"Expected SupplyChainConformalSuite, got {type(conformal_service)}"
            )
            return

        self._conformal_suite = conformal_service
        updated = 0

        for key, belief in self.belief_states.items():
            parts = key.split("_", 1)
            if len(parts) < 2:
                continue
            entity_type, entity_id = parts[0], parts[1]

            if entity_type == "demand":
                id_parts = entity_id.split(":")
                if len(id_parts) >= 2:
                    prod_id, site_id = id_parts[0], int(id_parts[1])
                    if conformal_service.has_demand_predictor(prod_id, site_id):
                        try:
                            interval = conformal_service.predict_demand(
                                prod_id, site_id, belief.demand_forecast
                            )
                            belief.demand_interval = ConformalInterval(
                                lower=interval.lower,
                                upper=interval.upper,
                                coverage=conformal_service.demand_coverage,
                                method="suite_adaptive",
                                point_estimate=belief.demand_forecast,
                            )
                            updated += 1
                        except Exception as e:
                            logger.debug(
                                f"Suite prediction failed for {key}: {e}"
                            )

        logger.info(
            f"Integrated BeliefStateManager with SupplyChainConformalSuite "
            f"({updated}/{len(self.belief_states)} beliefs updated)"
        )

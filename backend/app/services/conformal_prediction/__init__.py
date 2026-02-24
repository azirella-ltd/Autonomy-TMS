"""
Conformal Prediction Module

Provides distribution-free prediction intervals with guaranteed coverage
for supply chain applications including ATP, CTP, demand forecasting,
and lead time prediction.

References:
- Vovk, V., Gammerman, A., & Shafer, G. (2005). Algorithmic Learning in a Random World
- Romano, Y., Patterson, E., & Candès, E. (2019). Conformalized Quantile Regression
- Gibbs, I., & Candès, E. (2021). Adaptive Conformal Inference Under Distribution Shift
- Angelopoulos et al. (2024). Conformal Risk Control, ICLR 2024
- Clarkson (2025). CoRel: Relational Conformal Prediction for Correlated Time Series
- Lekeufack et al. (2024). Conformal Decision Theory, ICRA 2024
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .engine import ConformalPredictionEngine, PredictionInterval, CoverageStats
from .calibration import CalibrationStore, NonconformityScore
from .predictors import (
    SplitConformalPredictor,
    QuantileConformalPredictor,
    AdaptiveConformalPredictor,
    ATPConformalPredictor,
    DemandConformalPredictor,
    LeadTimeConformalPredictor,
)
from .suite import (
    SupplyChainConformalSuite,
    JointUncertaintyScenario,
    YieldConformalPredictor,
    PriceConformalPredictor,
    RelationalConformalPredictor,
    get_conformal_suite,
    reset_conformal_suite,
)
from .conformal_decision import (
    ConformalDecisionWrapper,
    ConformalDecisionRegistry,
    DecisionOutcomePair,
    RiskAssessment,
    get_cdt_registry,
    reset_cdt_registry,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes (API-compatible with endpoint expectations)
# ============================================================================

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
class SafetyStockResult:
    """Safety stock calculation with conformal guarantees"""
    safety_stock: float
    reorder_point: float
    expected_demand: float
    demand_interval: Tuple[float, float]
    lead_time_interval: Tuple[float, float]
    service_level_guarantee: float
    method: str = "conformal_decision_theory"


# ============================================================================
# Demand Forecaster Wrapper
# ============================================================================

class _DemandForecaster:
    """Wraps a ConformalPredictionEngine for demand forecasting."""

    def __init__(self, engine: ConformalPredictionEngine, calibration_result: CalibrationResult, alpha: float):
        self.conformal = self  # self-reference for .conformal.calibration_result access
        self.calibration_result = calibration_result
        self._engine = engine
        self._alpha = alpha

    @property
    def is_calibrated(self) -> bool:
        return self._engine.calibration_size > 0

    def predict(self, point_forecast: float) -> ConformalInterval:
        quantile = self.calibration_result.quantile
        return ConformalInterval(
            point_forecast=point_forecast,
            lower_bound=point_forecast - quantile,
            upper_bound=point_forecast + quantile,
            interval_width=2 * quantile,
            coverage_guarantee=1 - self._alpha,
            miscoverage_rate=self._alpha,
            quantile=quantile,
        )

    def forecast_horizon(
        self,
        point_forecasts: List[float],
        periods: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        if periods is None:
            periods = list(range(1, len(point_forecasts) + 1))

        results = []
        for i, pf in enumerate(point_forecasts):
            interval = self.predict(pf)
            results.append({
                "period": periods[i] if i < len(periods) else i + 1,
                "point_forecast": interval.point_forecast,
                "lower_bound": interval.lower_bound,
                "upper_bound": interval.upper_bound,
                "interval_width": interval.interval_width,
                "coverage_guarantee": interval.coverage_guarantee,
            })
        return results


# ============================================================================
# Lead Time Predictor Wrapper
# ============================================================================

class _LeadTimePredictor:
    """Wraps a ConformalPredictionEngine for lead time prediction."""

    def __init__(self, engine: ConformalPredictionEngine, calibration_result: CalibrationResult, alpha: float):
        self.conformal = self
        self.calibration_result = calibration_result
        self._engine = engine
        self._alpha = alpha

    @property
    def is_calibrated(self) -> bool:
        return self._engine.calibration_size > 0

    def predict(self, promised_lead_time: float) -> ConformalInterval:
        quantile = self.calibration_result.quantile
        return ConformalInterval(
            point_forecast=promised_lead_time,
            lower_bound=max(0.0, promised_lead_time - quantile),
            upper_bound=promised_lead_time + quantile,
            interval_width=2 * quantile,
            coverage_guarantee=1 - self._alpha,
            miscoverage_rate=self._alpha,
            quantile=quantile,
        )


# ============================================================================
# Conformal Prediction Service (API expected by endpoints)
# ============================================================================

class ConformalPredictionService:
    """
    Main service for conformal prediction in supply chain planning.

    Manages multiple predictors for different variables/products/sites.
    Uses ConformalPredictionEngine under the hood.
    """

    def __init__(self):
        self.demand_forecasters: Dict[str, _DemandForecaster] = {}
        self.lead_time_predictors: Dict[str, _LeadTimePredictor] = {}

    def get_predictor_key(
        self,
        variable: str,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None,
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
        site_id: Optional[int] = None,
    ) -> CalibrationResult:
        """Calibrate a demand forecaster from historical forecast vs actual data."""
        key = self.get_predictor_key("demand", product_id, site_id)
        engine = ConformalPredictionEngine(coverage=1 - alpha, min_calibration_size=10)
        engine.add_calibration_batch(historical_forecasts.tolist(), historical_actuals.tolist())

        quantile = engine.compute_quantile()
        scores = np.array(engine._nonconformity_scores)
        empirical_coverage = float(np.mean(scores <= quantile))

        result = CalibrationResult(
            alpha=alpha,
            quantile=quantile,
            empirical_coverage=empirical_coverage,
            n_samples=len(historical_forecasts),
            calibration_scores=scores,
            variable_name="demand",
            product_id=product_id,
            site_id=site_id,
        )

        self.demand_forecasters[key] = _DemandForecaster(engine, result, alpha)
        logger.info(f"Calibrated demand forecaster [{key}]: quantile={quantile:.2f}, coverage={empirical_coverage:.1%}")
        return result

    def calibrate_lead_time(
        self,
        promised_lead_times: np.ndarray,
        actual_lead_times: np.ndarray,
        alpha: float = 0.1,
        supplier_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> CalibrationResult:
        """Calibrate a lead time predictor from promised vs actual lead times."""
        key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            key = f"{key}:supplier:{supplier_id}"

        engine = ConformalPredictionEngine(coverage=1 - alpha, min_calibration_size=10)
        engine.add_calibration_batch(promised_lead_times.tolist(), actual_lead_times.tolist())

        quantile = engine.compute_quantile()
        scores = np.array(engine._nonconformity_scores)
        empirical_coverage = float(np.mean(scores <= quantile))

        result = CalibrationResult(
            alpha=alpha,
            quantile=quantile,
            empirical_coverage=empirical_coverage,
            n_samples=len(promised_lead_times),
            calibration_scores=scores,
            variable_name="lead_time",
            product_id=product_id,
        )

        self.lead_time_predictors[key] = _LeadTimePredictor(engine, result, alpha)
        logger.info(f"Calibrated lead time predictor [{key}]: quantile={quantile:.2f}, coverage={empirical_coverage:.1%}")
        return result

    def predict_demand(
        self,
        point_forecast: float,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None,
    ) -> ConformalInterval:
        """Generate prediction interval for a demand point forecast."""
        key = self.get_predictor_key("demand", product_id, site_id)
        if key not in self.demand_forecasters:
            raise ValueError(
                f"No calibrated demand forecaster for product={product_id}, site={site_id}. "
                "Calibrate first."
            )
        return self.demand_forecasters[key].predict(point_forecast)

    def predict_lead_time(
        self,
        promised_lead_time: float,
        supplier_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> ConformalInterval:
        """Generate prediction interval for a lead time estimate."""
        key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            key = f"{key}:supplier:{supplier_id}"

        if key not in self.lead_time_predictors:
            # Fallback: ±30% default interval
            quantile = promised_lead_time * 0.3
            return ConformalInterval(
                point_forecast=promised_lead_time,
                lower_bound=max(0.0, promised_lead_time - quantile),
                upper_bound=promised_lead_time + quantile,
                interval_width=2 * quantile,
                coverage_guarantee=0.9,
                miscoverage_rate=0.1,
                quantile=quantile,
                method="default_fallback",
            )
        return self.lead_time_predictors[key].predict(promised_lead_time)

    def calculate_safety_stock(
        self,
        expected_demand: float,
        expected_lead_time: float,
        product_id: Optional[str] = None,
        site_id: Optional[int] = None,
        supplier_id: Optional[str] = None,
    ) -> SafetyStockResult:
        """Calculate safety stock with conformal guarantees."""
        # Get demand interval
        demand_key = self.get_predictor_key("demand", product_id, site_id)
        if demand_key in self.demand_forecasters:
            demand_interval = self.demand_forecasters[demand_key].predict(expected_demand)
            demand_lower = demand_interval.lower_bound
            demand_upper = demand_interval.upper_bound
            method = "conformal_decision_theory"
        else:
            # Fallback: ±20%
            demand_lower = expected_demand * 0.8
            demand_upper = expected_demand * 1.2
            method = "default_fallback"

        # Get lead time interval
        lt_key = self.get_predictor_key("lead_time", product_id)
        if supplier_id:
            lt_key = f"{lt_key}:supplier:{supplier_id}"

        if lt_key in self.lead_time_predictors:
            lt_interval = self.lead_time_predictors[lt_key].predict(expected_lead_time)
            lt_lower = lt_interval.lower_bound
            lt_upper = lt_interval.upper_bound
        else:
            lt_lower = expected_lead_time * 0.8
            lt_upper = expected_lead_time * 1.3

        # Worst-case demand during worst-case lead time
        worst_case_demand = demand_upper * lt_upper
        expected_demand_during_lt = expected_demand * expected_lead_time
        safety_stock = max(0.0, worst_case_demand - expected_demand_during_lt)
        reorder_point = expected_demand_during_lt + safety_stock

        # Service level from joint coverage
        demand_coverage = 0.9 if demand_key in self.demand_forecasters else 0.8
        lt_coverage = 0.9 if lt_key in self.lead_time_predictors else 0.8
        service_level = demand_coverage * lt_coverage

        return SafetyStockResult(
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            expected_demand=expected_demand,
            demand_interval=(demand_lower, demand_upper),
            lead_time_interval=(lt_lower, lt_upper),
            service_level_guarantee=service_level,
            method=method,
        )

    def get_calibration_summary(self) -> Dict[str, Any]:
        """Get summary of all calibrated predictors."""
        summary: Dict[str, Any] = {
            "demand_forecasters": {},
            "lead_time_predictors": {},
            "total_calibrated": 0,
        }

        for key, forecaster in self.demand_forecasters.items():
            if forecaster.is_calibrated:
                cal = forecaster.calibration_result
                summary["demand_forecasters"][key] = {
                    "alpha": cal.alpha,
                    "quantile": cal.quantile,
                    "empirical_coverage": cal.empirical_coverage,
                    "n_samples": cal.n_samples,
                }
                summary["total_calibrated"] += 1

        for key, predictor in self.lead_time_predictors.items():
            if predictor.is_calibrated:
                cal = predictor.calibration_result
                summary["lead_time_predictors"][key] = {
                    "alpha": cal.alpha,
                    "quantile": cal.quantile,
                    "empirical_coverage": cal.empirical_coverage,
                    "n_samples": cal.n_samples,
                }
                summary["total_calibrated"] += 1

        return summary


# ============================================================================
# Singleton
# ============================================================================

# Alias for backward compatibility
ConformalPredictor = SplitConformalPredictor

_conformal_service: Optional[ConformalPredictionService] = None


def get_conformal_service() -> ConformalPredictionService:
    """Get or create the singleton conformal prediction service"""
    global _conformal_service
    if _conformal_service is None:
        _conformal_service = ConformalPredictionService()
    return _conformal_service


__all__ = [
    # Core classes
    "ConformalPredictionEngine",
    "CalibrationStore",
    "NonconformityScore",
    "PredictionInterval",
    "CoverageStats",
    # Predictors
    "SplitConformalPredictor",
    "QuantileConformalPredictor",
    "AdaptiveConformalPredictor",
    "ATPConformalPredictor",
    "DemandConformalPredictor",
    "LeadTimeConformalPredictor",
    # Suite (unified management)
    "SupplyChainConformalSuite",
    "JointUncertaintyScenario",
    "YieldConformalPredictor",
    "PriceConformalPredictor",
    "RelationalConformalPredictor",
    "get_conformal_suite",
    "reset_conformal_suite",
    # Conformal Decision Theory
    "ConformalDecisionWrapper",
    "ConformalDecisionRegistry",
    "DecisionOutcomePair",
    "RiskAssessment",
    "get_cdt_registry",
    "reset_cdt_registry",
    # API service
    "ConformalPredictionService",
    "ConformalPredictor",
    "ConformalInterval",
    # Results
    "CalibrationResult",
    "SafetyStockResult",
    # Factory function
    "get_conformal_service",
]

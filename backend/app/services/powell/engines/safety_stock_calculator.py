"""
Safety Stock Calculator - 100% Deterministic

Implements the 4 AWS SC policy types:
- abs_level: Fixed quantity
- doc_dem: Days of coverage (demand-based)
- doc_fcst: Days of coverage (forecast-based)
- sl: Service level with z-score (SS = z × σ × √L)

This engine handles the mathematically defined formulas.
TRM heads handle service level target adjustments and seasonal overrides.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
from enum import Enum
import math
import logging

logger = logging.getLogger(__name__)


class PolicyType(Enum):
    """Safety stock policy types (AWS SC standard)"""
    ABS_LEVEL = "abs_level"    # Fixed quantity
    DOC_DEM = "doc_dem"        # Days of coverage (demand)
    DOC_FCST = "doc_fcst"      # Days of coverage (forecast)
    SL = "sl"                  # Service level


@dataclass
class SSPolicy:
    """Safety stock policy definition"""
    policy_type: PolicyType

    # For abs_level
    fixed_quantity: Optional[float] = None

    # For doc_dem / doc_fcst
    days_of_coverage: Optional[float] = None

    # For sl
    target_service_level: Optional[float] = None  # e.g., 0.95

    # Common constraints
    min_ss: float = 0
    max_ss: Optional[float] = None

    # Optional overrides
    seasonal_factor: float = 1.0  # Multiply SS by this during peak seasons


@dataclass
class DemandStats:
    """Demand statistics for SS calculation"""
    avg_daily_demand: float
    std_daily_demand: float
    avg_daily_forecast: float
    std_daily_forecast: float = 0  # Forecast error std
    lead_time_days: float = 7
    lead_time_std: float = 0  # For lead time variability
    review_period_days: float = 1  # For periodic review systems


@dataclass
class SSResult:
    """Safety stock calculation result"""
    product_id: str
    location_id: str
    safety_stock: float
    reorder_point: float
    policy_type: PolicyType
    calculation_detail: Dict[str, Any]
    target_inventory: float = 0  # SS + average demand during lead time


# Z-scores for common service levels
Z_SCORES = {
    0.50: 0.000,
    0.75: 0.674,
    0.80: 0.842,
    0.85: 1.036,
    0.90: 1.282,
    0.95: 1.645,
    0.97: 1.881,
    0.98: 2.054,
    0.99: 2.326,
    0.995: 2.576,
    0.999: 3.090,
}


@dataclass
class SafetyStockConfig:
    """Configuration for safety stock calculator"""
    default_policy_type: PolicyType = PolicyType.SL
    default_service_level: float = 0.95
    default_days_of_coverage: float = 14
    min_safety_stock: float = 0
    use_forecast_error: bool = True  # Use forecast error instead of demand std


class SafetyStockCalculator:
    """
    Safety stock calculator implementing 4 policy types.

    100% deterministic - formula-based calculations only.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[SafetyStockConfig] = None
    ):
        self.site_key = site_key
        self.config = config or SafetyStockConfig()

    def compute_safety_stock(
        self,
        product_id: str,
        location_id: str,
        policy: SSPolicy,
        stats: DemandStats
    ) -> SSResult:
        """
        Compute safety stock based on policy type.
        """
        if policy.policy_type == PolicyType.ABS_LEVEL:
            ss, detail = self._calc_abs_level(policy)
        elif policy.policy_type == PolicyType.DOC_DEM:
            ss, detail = self._calc_doc_dem(policy, stats)
        elif policy.policy_type == PolicyType.DOC_FCST:
            ss, detail = self._calc_doc_fcst(policy, stats)
        elif policy.policy_type == PolicyType.SL:
            ss, detail = self._calc_service_level(policy, stats)
        else:
            ss, detail = 0, {'error': 'Unknown policy type'}

        # Apply seasonal factor
        ss *= policy.seasonal_factor

        # Apply bounds
        ss = max(policy.min_ss, ss)
        if policy.max_ss is not None:
            ss = min(policy.max_ss, ss)

        # Reorder point = SS + (demand during lead time)
        ddlt = stats.avg_daily_demand * stats.lead_time_days
        rop = ss + ddlt

        # Target inventory = SS + avg demand during (lead time + review period)
        target_inv = ss + stats.avg_daily_demand * (stats.lead_time_days + stats.review_period_days)

        detail.update({
            'demand_during_lead_time': ddlt,
            'avg_daily_demand': stats.avg_daily_demand,
            'lead_time_days': stats.lead_time_days,
            'seasonal_factor': policy.seasonal_factor,
            'bounds_applied': {
                'min': policy.min_ss,
                'max': policy.max_ss
            }
        })

        return SSResult(
            product_id=product_id,
            location_id=location_id,
            safety_stock=ss,
            reorder_point=rop,
            policy_type=policy.policy_type,
            calculation_detail=detail,
            target_inventory=target_inv
        )

    def _calc_abs_level(self, policy: SSPolicy) -> tuple:
        """Fixed quantity - simplest policy"""
        ss = policy.fixed_quantity or 0
        detail = {
            'method': 'absolute_level',
            'fixed_quantity': policy.fixed_quantity
        }
        return ss, detail

    def _calc_doc_dem(self, policy: SSPolicy, stats: DemandStats) -> tuple:
        """Days of coverage based on historical demand"""
        if not policy.days_of_coverage:
            return 0, {'error': 'days_of_coverage not specified'}

        ss = stats.avg_daily_demand * policy.days_of_coverage

        detail = {
            'method': 'days_of_coverage_demand',
            'days_of_coverage': policy.days_of_coverage,
            'avg_daily_demand': stats.avg_daily_demand,
            'formula': 'SS = avg_daily_demand × days_of_coverage'
        }

        return ss, detail

    def _calc_doc_fcst(self, policy: SSPolicy, stats: DemandStats) -> tuple:
        """Days of coverage based on forecast"""
        if not policy.days_of_coverage:
            return 0, {'error': 'days_of_coverage not specified'}

        ss = stats.avg_daily_forecast * policy.days_of_coverage

        detail = {
            'method': 'days_of_coverage_forecast',
            'days_of_coverage': policy.days_of_coverage,
            'avg_daily_forecast': stats.avg_daily_forecast,
            'formula': 'SS = avg_daily_forecast × days_of_coverage'
        }

        return ss, detail

    def _calc_service_level(self, policy: SSPolicy, stats: DemandStats) -> tuple:
        """
        Service level based safety stock.

        Formula depends on configuration:

        1. Basic (fixed lead time):
           SS = z × σ_D × √L

        2. Variable lead time:
           SS = z × √(L × σ_D² + D² × σ_L²)

        3. Using forecast error (recommended):
           SS = z × σ_FE × √L
           Where σ_FE = forecast error standard deviation

        Where:
        - z = z-score for target service level
        - σ_D = standard deviation of daily demand
        - L = lead time in days
        - D = average daily demand
        - σ_L = standard deviation of lead time
        """
        if not policy.target_service_level:
            return 0, {'error': 'target_service_level not specified'}

        z = self._get_z_score(policy.target_service_level)
        L = stats.lead_time_days

        # Determine which standard deviation to use
        if self.config.use_forecast_error and stats.std_daily_forecast > 0:
            # Use forecast error std
            sigma = stats.std_daily_forecast
            method = 'service_level_forecast_error'
        else:
            # Use demand std
            sigma = stats.std_daily_demand
            method = 'service_level_demand'

        if stats.lead_time_std > 0:
            # Variable lead time formula
            variance = (
                L * (sigma ** 2) +
                (stats.avg_daily_demand ** 2) * (stats.lead_time_std ** 2)
            )
            ss = z * math.sqrt(variance)
            formula = 'SS = z × √(L × σ² + D² × σ_L²)'
        else:
            # Fixed lead time formula: z × σ × √L
            ss = z * sigma * math.sqrt(L)
            formula = 'SS = z × σ × √L'

        detail = {
            'method': method,
            'target_service_level': policy.target_service_level,
            'z_score': z,
            'sigma': sigma,
            'lead_time_days': L,
            'lead_time_std': stats.lead_time_std,
            'formula': formula
        }

        return ss, detail

    def _get_z_score(self, service_level: float) -> float:
        """Get z-score for service level, with interpolation"""
        # Direct lookup
        if service_level in Z_SCORES:
            return Z_SCORES[service_level]

        # Linear interpolation
        levels = sorted(Z_SCORES.keys())
        for i in range(len(levels) - 1):
            if levels[i] <= service_level <= levels[i + 1]:
                # Interpolate
                ratio = (service_level - levels[i]) / (levels[i + 1] - levels[i])
                return Z_SCORES[levels[i]] + ratio * (Z_SCORES[levels[i + 1]] - Z_SCORES[levels[i]])

        # Extrapolate for very high service levels
        if service_level > 0.999:
            # Use approximation: z ≈ 3.09 + 1.0 * (SL - 0.999) / 0.001
            return 3.09 + (service_level - 0.999) * 100

        # Very low service levels
        if service_level < 0.50:
            return -self._get_z_score(1 - service_level)

        return 0

    def compute_batch(
        self,
        items: List[Dict],
        default_policy: Optional[SSPolicy] = None
    ) -> List[SSResult]:
        """
        Compute safety stock for multiple items.

        Each item dict should have:
        - product_id: str
        - location_id: str
        - policy: SSPolicy (optional, uses default if not provided)
        - stats: DemandStats
        """
        results = []

        for item in items:
            policy = item.get('policy', default_policy)
            if policy is None:
                policy = SSPolicy(
                    policy_type=self.config.default_policy_type,
                    target_service_level=self.config.default_service_level,
                    days_of_coverage=self.config.default_days_of_coverage
                )

            result = self.compute_safety_stock(
                product_id=item['product_id'],
                location_id=item['location_id'],
                policy=policy,
                stats=item['stats']
            )
            results.append(result)

        return results

    def get_tunable_params(self) -> List[Dict]:
        """Return parameters that can be tuned by PolicyOptimizer"""
        return [
            {
                'name': 'ss_multiplier',
                'initial_value': 1.0,
                'lower_bound': 0.5,
                'upper_bound': 2.0,
                'parameter_type': 'continuous',
                'description': 'Multiplier applied to calculated safety stock'
            },
            {
                'name': 'service_level_target',
                'initial_value': 0.95,
                'lower_bound': 0.85,
                'upper_bound': 0.99,
                'parameter_type': 'continuous',
                'description': 'Target service level for SL policy type'
            },
            {
                'name': 'days_of_coverage',
                'initial_value': 14,
                'lower_bound': 1,
                'upper_bound': 60,
                'parameter_type': 'continuous',
                'description': 'Days of coverage for DOC policy types'
            }
        ]

    @staticmethod
    def service_level_from_z(z: float) -> float:
        """Convert z-score to service level (inverse lookup)"""
        from scipy.stats import norm
        return norm.cdf(z)

    @staticmethod
    def z_from_service_level(sl: float) -> float:
        """Convert service level to z-score"""
        from scipy.stats import norm
        return norm.ppf(sl)

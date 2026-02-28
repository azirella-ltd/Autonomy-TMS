"""
Distribution-Aware Feature Extractor for ML Pipelines

Extracts distribution-native parameters as features for TRM and GNN models.
Instead of using mean/std (which implicitly assume Normal), this module fits
the actual distribution (Weibull, Lognormal, Gamma) and extracts native
parameters (shape k, scale lambda, etc.) that better capture the underlying
data-generating process.

Insight: Kravanja (2026) — "Stop Using Average and Standard Deviation for
Your Features." Distribution parameters are more meaningful features than
mean/std for non-Normal supply chain data.

Usage:
    extractor = DistributionFeatureExtractor()
    features = extractor.extract_lead_time_features(lt_data)
    # {'lt_mean': 7.2, 'lt_weibull_k': 2.1, 'lt_weibull_lambda': 8.1, ...}

Note: These features are stored as metadata alongside TRM decisions for
future model retraining. They do NOT change current TRM input dimensions.
"""

import logging
from typing import Dict, Optional

import numpy as np
from scipy import stats as sp_stats

from .distribution_fitter import DistributionFitter

logger = logging.getLogger(__name__)


class DistributionFeatureExtractor:
    """Extract distribution-aware features from historical data.

    Produces a flat dictionary of named features suitable for ML pipelines.
    Each feature name is prefixed with the variable type (lt_, demand_, yield_)
    for namespacing when combined into a larger feature vector.
    """

    def __init__(self, fitter: Optional[DistributionFitter] = None):
        self._fitter = fitter or DistributionFitter()

    def extract_lead_time_features(self, data: np.ndarray) -> Dict[str, float]:
        """Extract features from lead time data.

        Lead times are always positive and typically right-skewed, making
        Weibull the natural parametric model. The shape parameter k is
        especially informative:
        - k < 1: Highly variable (exponential-like)
        - k ~ 1: Memoryless (exponential)
        - k > 1: Regular, predictable (low-variance)
        - k > 3: Very regular (approaching Normal)

        Args:
            data: 1-D array of historical lead time values

        Returns:
            Dictionary of named features with 'lt_' prefix
        """
        data = np.asarray(data, dtype=float).ravel()
        data = data[np.isfinite(data) & (data > 0)]

        features: Dict[str, float] = {
            "lt_n": float(len(data)),
        }

        if len(data) == 0:
            return features

        # Traditional stats (for backward compatibility)
        features["lt_mean"] = float(np.mean(data))
        features["lt_median"] = float(np.median(data))
        features["lt_std"] = float(np.std(data, ddof=1)) if len(data) > 1 else 0.0
        features["lt_cv"] = features["lt_std"] / features["lt_mean"] if features["lt_mean"] > 0 else 0.0

        # Robust stats
        mad = float(np.median(np.abs(data - np.median(data))))
        features["lt_mad"] = mad
        features["lt_robust_cv"] = (mad * 1.4826) / features["lt_median"] if features["lt_median"] > 0 else 0.0

        # Shape statistics
        if len(data) >= 3:
            features["lt_skewness"] = float(sp_stats.skew(data))
        if len(data) >= 4:
            features["lt_kurtosis"] = float(sp_stats.kurtosis(data))

        # Distribution fitting
        if len(data) >= self._fitter.MIN_SAMPLES_FOR_FIT:
            try:
                report = self._fitter.fit(data, variable_type="lead_time")
                features["lt_best_dist"] = _encode_dist_type(report.best.dist_type)
                features["lt_ks_pvalue"] = report.best.ks_pvalue

                # Extract Weibull params specifically (always useful for LT)
                for c in report.candidates:
                    if c.dist_type == "weibull":
                        features["lt_weibull_k"] = c.params.get("shape", 0.0)
                        features["lt_weibull_lambda"] = c.params.get("scale", 0.0)
                        break

                # Best-fit params
                features["lt_fitted_param1"] = list(report.best.params.values())[0] if report.best.params else 0.0
                features["lt_fitted_param2"] = list(report.best.params.values())[1] if len(report.best.params) > 1 else 0.0
            except Exception as e:
                logger.debug("Lead time feature extraction failed: %s", e)

        return features

    def extract_demand_features(self, data: np.ndarray) -> Dict[str, float]:
        """Extract features from demand data.

        Demand data is non-negative, often intermittent (many zeros), and
        right-skewed. Lognormal is typically the best fit for the non-zero
        portion. The Syntetos-Boylan ADI (Average Demand Interval) captures
        the intermittency pattern.

        Args:
            data: 1-D array of historical demand values

        Returns:
            Dictionary of named features with 'demand_' prefix
        """
        data = np.asarray(data, dtype=float).ravel()
        data = data[np.isfinite(data)]

        features: Dict[str, float] = {
            "demand_n": float(len(data)),
        }

        if len(data) == 0:
            return features

        # Traditional stats
        features["demand_mean"] = float(np.mean(data))
        features["demand_median"] = float(np.median(data))
        features["demand_std"] = float(np.std(data, ddof=1)) if len(data) > 1 else 0.0
        features["demand_cv"] = features["demand_std"] / features["demand_mean"] if features["demand_mean"] > 0 else 0.0

        # Robust stats
        mad = float(np.median(np.abs(data - np.median(data))))
        features["demand_mad"] = mad
        features["demand_robust_cv"] = (mad * 1.4826) / features["demand_median"] if features["demand_median"] > 0 else 0.0

        # Intermittency
        non_zero = np.count_nonzero(data)
        features["demand_pct_zeros"] = float(np.sum(data == 0) / len(data))
        features["demand_adi"] = float(len(data) / non_zero) if non_zero > 0 else float("inf")

        # Shape statistics
        if len(data) >= 3:
            features["demand_skewness"] = float(sp_stats.skew(data))
        if len(data) >= 4:
            features["demand_kurtosis"] = float(sp_stats.kurtosis(data))

        # Distribution fitting (on non-zero values)
        pos_data = data[data > 0]
        if len(pos_data) >= self._fitter.MIN_SAMPLES_FOR_FIT:
            try:
                report = self._fitter.fit(pos_data, variable_type="demand")
                features["demand_best_dist"] = _encode_dist_type(report.best.dist_type)
                features["demand_ks_pvalue"] = report.best.ks_pvalue

                # Extract Lognormal params specifically (common for demand)
                for c in report.candidates:
                    if c.dist_type == "lognormal":
                        features["demand_lognormal_mu"] = c.params.get("mean_log", 0.0)
                        features["demand_lognormal_sigma"] = c.params.get("stddev_log", 0.0)
                        break

                features["demand_fitted_param1"] = list(report.best.params.values())[0] if report.best.params else 0.0
                features["demand_fitted_param2"] = list(report.best.params.values())[1] if len(report.best.params) > 1 else 0.0
            except Exception as e:
                logger.debug("Demand feature extraction failed: %s", e)

        return features

    def extract_yield_features(self, data: np.ndarray) -> Dict[str, float]:
        """Extract features from yield/scrap data.

        Yields are bounded in [0, 1] (or sometimes [0.5, 1.0] for
        manufacturing). Beta distribution is the natural parametric model.

        Args:
            data: 1-D array of historical yield values (0-1 range)

        Returns:
            Dictionary of named features with 'yield_' prefix
        """
        data = np.asarray(data, dtype=float).ravel()
        data = data[np.isfinite(data)]

        features: Dict[str, float] = {
            "yield_n": float(len(data)),
        }

        if len(data) == 0:
            return features

        features["yield_mean"] = float(np.mean(data))
        features["yield_std"] = float(np.std(data, ddof=1)) if len(data) > 1 else 0.0

        # Distribution fitting
        bounded = data[(data > 0) & (data < 1)]
        if len(bounded) >= self._fitter.MIN_SAMPLES_FOR_FIT:
            try:
                report = self._fitter.fit(bounded, variable_type="yield")
                features["yield_best_dist"] = _encode_dist_type(report.best.dist_type)
                features["yield_ks_pvalue"] = report.best.ks_pvalue
                if report.best.dist_type == "beta":
                    features["yield_beta_alpha"] = report.best.params.get("alpha", 1.0)
                    features["yield_beta_beta"] = report.best.params.get("beta", 1.0)
            except Exception as e:
                logger.debug("Yield feature extraction failed: %s", e)

        return features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIST_TYPE_ENCODING = {
    "normal": 0,
    "lognormal": 1,
    "gamma": 2,
    "weibull": 3,
    "exponential": 4,
    "beta": 5,
    "empirical": 6,
}


def _encode_dist_type(dist_type: str) -> float:
    """Encode distribution type as a numeric feature."""
    return float(_DIST_TYPE_ENCODING.get(dist_type, -1))

"""
Distribution Fitter for Stochastic Supply Chain Modeling

Fits candidate probability distributions to observed data using MLE (Maximum
Likelihood Estimation), ranks them by goodness-of-fit (AIC/BIC, Kolmogorov-Smirnov),
and returns platform-native Distribution objects.

Motivation (Kravanja 2026): Using mean+stddev implicitly assumes Normal distribution.
Supply chain data — lead times (positive, right-skewed), demand (non-negative, lumpy),
yields (bounded 0-1) — is rarely Normal. Fitting the actual distribution and using its
native parameters (Weibull shape k, Lognormal sigma, etc.) produces better features
and more accurate tail-risk estimates for safety stock and forecasting.

Usage:
    from app.services.stochastic.distribution_fitter import DistributionFitter

    fitter = DistributionFitter()
    report = fitter.fit(lead_time_data, variable_type="lead_time")
    print(report.best.dist_type)        # e.g., "weibull"
    print(report.best.params)           # e.g., {"shape": 2.1, "scale": 7.3}
    print(report.best.distribution)     # WeibullDistribution object
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from scipy import stats as sp_stats

from .distributions import (
    Distribution,
    NormalDistribution,
    LognormalDistribution,
    GammaDistribution,
    WeibullDistribution,
    ExponentialDistribution,
    BetaDistribution,
    EmpiricalContinuousDistribution,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FitResult:
    """Result of fitting a single distribution to data."""
    distribution: Distribution
    dist_type: str
    params: Dict[str, float]
    ks_statistic: float
    ks_pvalue: float
    aic: float
    bic: float
    log_likelihood: float
    n_samples: int


@dataclass
class FitReport:
    """Complete report from distribution fitting."""
    best: FitResult
    candidates: List[FitResult]
    data_summary: Dict[str, float]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses."""
        return {
            "best": {
                "dist_type": self.best.dist_type,
                "params": self.best.params,
                "ks_statistic": round(self.best.ks_statistic, 6),
                "ks_pvalue": round(self.best.ks_pvalue, 6),
                "aic": round(self.best.aic, 4),
                "bic": round(self.best.bic, 4),
                "n_samples": self.best.n_samples,
            },
            "candidates": [
                {
                    "dist_type": c.dist_type,
                    "params": c.params,
                    "ks_statistic": round(c.ks_statistic, 6),
                    "ks_pvalue": round(c.ks_pvalue, 6),
                    "aic": round(c.aic, 4),
                    "bic": round(c.bic, 4),
                }
                for c in self.candidates
            ],
            "data_summary": {k: round(v, 6) for k, v in self.data_summary.items()},
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Parameterization mapping: scipy -> platform Distribution constructors
# ---------------------------------------------------------------------------

def _scipy_to_platform(dist_type: str, scipy_params: tuple,
                       data: np.ndarray) -> Tuple[Distribution, Dict[str, float]]:
    """Convert scipy MLE parameters to a platform Distribution object.

    scipy.stats uses (shape, loc, scale) convention. We fix loc=0 for most
    distributions (lead times, demand are zero-based) and map the remaining
    params to platform constructors.
    """
    if dist_type == "weibull":
        # scipy weibull_min.fit() returns (c, loc, scale)
        c, _loc, scale = scipy_params
        params = {"shape": float(c), "scale": float(scale)}
        dist = WeibullDistribution(shape=c, scale=scale)

    elif dist_type == "lognormal":
        # scipy lognorm.fit() returns (s, loc, scale) where s=sigma, scale=exp(mu)
        s, _loc, scale = scipy_params
        mean_log = float(np.log(scale))
        stddev_log = float(s)
        params = {"mean_log": mean_log, "stddev_log": stddev_log}
        dist = LognormalDistribution(mean_log=mean_log, stddev_log=stddev_log)

    elif dist_type == "gamma":
        # scipy gamma.fit() returns (a, loc, scale)
        a, _loc, scale = scipy_params
        params = {"shape": float(a), "scale": float(scale)}
        dist = GammaDistribution(shape=a, scale=scale)

    elif dist_type == "exponential":
        # scipy expon.fit() returns (loc, scale)
        _loc, scale = scipy_params
        rate = 1.0 / scale if scale > 0 else 1.0
        params = {"rate": float(rate)}
        dist = ExponentialDistribution(rate=rate)

    elif dist_type == "normal":
        # scipy norm.fit() returns (loc, scale)
        loc, scale = scipy_params
        params = {"mean": float(loc), "stddev": float(scale)}
        dist = NormalDistribution(mean=loc, stddev=scale)

    elif dist_type == "beta":
        # scipy beta.fit() returns (a, b, loc, scale)
        a, b, _loc, _scale = scipy_params
        params = {"alpha": float(a), "beta": float(b)}
        dist = BetaDistribution(alpha=a, beta=b)

    elif dist_type == "loglogistic":
        # scipy fisk.fit() returns (c, loc, scale) where c=shape(beta), scale=alpha(median)
        c, _loc, scale = scipy_params
        params = {"alpha": float(scale), "beta": float(c)}
        from .distributions import LogLogisticDistribution
        dist = LogLogisticDistribution(alpha=scale, beta=c)

    else:
        raise ValueError(f"Unsupported distribution type: {dist_type}")

    return dist, params


def _get_scipy_dist(dist_type: str):
    """Get the scipy.stats distribution object for a type name."""
    mapping = {
        "weibull": sp_stats.weibull_min,
        "lognormal": sp_stats.lognorm,
        "gamma": sp_stats.gamma,
        "exponential": sp_stats.expon,
        "normal": sp_stats.norm,
        "beta": sp_stats.beta,
        "loglogistic": sp_stats.fisk,
    }
    return mapping.get(dist_type)


def _count_params(dist_type: str) -> int:
    """Number of free parameters for AIC/BIC calculation."""
    counts = {
        "weibull": 2,       # shape, scale
        "lognormal": 2,     # mean_log, stddev_log
        "gamma": 2,         # shape, scale
        "exponential": 1,   # rate
        "normal": 2,        # mean, stddev
        "beta": 2,          # alpha, beta
        "loglogistic": 2,   # alpha (scale/median), beta (shape)
    }
    return counts.get(dist_type, 2)


# ---------------------------------------------------------------------------
# Core fitter
# ---------------------------------------------------------------------------

class DistributionFitter:
    """Fits distributions to data using MLE and goodness-of-fit tests.

    Candidate sets by variable type match the nature of supply chain data:
    - Lead times: always positive, right-skewed -> Weibull, Lognormal, Gamma
    - Demand: non-negative, often lumpy -> Lognormal, Gamma, Normal
    - Yields: bounded [0,1] -> Beta, Truncated Normal
    """

    LEAD_TIME_CANDIDATES = ["weibull", "lognormal", "gamma", "loglogistic", "exponential"]
    DEMAND_CANDIDATES = ["lognormal", "gamma", "normal"]
    YIELD_CANDIDATES = ["beta"]
    GENERAL_CANDIDATES = ["normal", "lognormal", "gamma", "weibull", "exponential"]

    MIN_SAMPLES_FOR_FIT = 5
    MIN_SAMPLES_RELIABLE = 20

    def fit(
        self,
        data: np.ndarray,
        variable_type: Optional[str] = None,
        candidates: Optional[List[str]] = None,
        censored_mask: Optional[np.ndarray] = None,
    ) -> FitReport:
        """Fit candidate distributions to data and return ranked results.

        Args:
            data: 1-D array of observed values
            variable_type: Hint for candidate selection ("lead_time", "demand", "yield")
            candidates: Explicit list of distribution types to try
            censored_mask: Optional boolean array where True = censored observation
                (e.g., stockout period where observed demand is a lower bound of
                true demand). Censored observations are excluded from MLE fitting.
                Inspired by Lokad's censored demand handling methodology.

        Returns:
            FitReport with best-fit distribution and all candidates ranked by AIC
        """
        data = np.asarray(data, dtype=float).ravel()
        data = data[np.isfinite(data)]

        # Apply censoring mask — exclude censored observations from fitting
        if censored_mask is not None:
            censored_mask = np.asarray(censored_mask, dtype=bool).ravel()
            if len(censored_mask) == len(data):
                n_censored = int(censored_mask.sum())
                uncensored_data = data[~censored_mask]
                if len(uncensored_data) >= self.MIN_SAMPLES_FOR_FIT:
                    data = uncensored_data
                    # Warning added below after warnings list is created
                else:
                    n_censored = 0  # Not enough uncensored data, use all
            else:
                censored_mask = None
                n_censored = 0
        else:
            n_censored = 0

        warnings: List[str] = []
        n = len(data)

        if n_censored > 0:
            warnings.append(
                f"Excluded {n_censored} censored observations (stockout periods). "
                f"Fitting on {n} uncensored observations."
            )

        # Data summary (always computed)
        summary = self._data_summary(data)

        # Too few samples — return empirical
        if n < self.MIN_SAMPLES_FOR_FIT:
            warnings.append(
                f"Only {n} samples (min {self.MIN_SAMPLES_FOR_FIT}). "
                "Returning empirical distribution."
            )
            empirical = EmpiricalContinuousDistribution(samples=data.tolist())
            result = FitResult(
                distribution=empirical,
                dist_type="empirical",
                params={"n_samples": n},
                ks_statistic=0.0,
                ks_pvalue=1.0,
                aic=float("inf"),
                bic=float("inf"),
                log_likelihood=float("-inf"),
                n_samples=n,
            )
            return FitReport(
                best=result, candidates=[result],
                data_summary=summary, warnings=warnings,
            )

        if n < self.MIN_SAMPLES_RELIABLE:
            warnings.append(
                f"Only {n} samples (< {self.MIN_SAMPLES_RELIABLE}). "
                "KS p-values may be unreliable."
            )

        # Select candidates
        if candidates is not None:
            candidate_list = candidates
        elif variable_type == "lead_time":
            candidate_list = self.LEAD_TIME_CANDIDATES
        elif variable_type == "demand":
            candidate_list = self.DEMAND_CANDIDATES
        elif variable_type == "yield":
            candidate_list = self.YIELD_CANDIDATES
        else:
            candidate_list = self._auto_select_candidates(data)

        # Fit each candidate
        results: List[FitResult] = []
        for dtype in candidate_list:
            try:
                result = self.fit_single(data, dtype)
                results.append(result)
            except Exception as e:
                logger.debug("Failed to fit %s: %s", dtype, e)
                warnings.append(f"Could not fit {dtype}: {str(e)}")

        if not results:
            warnings.append("All candidate fits failed. Returning empirical distribution.")
            empirical = EmpiricalContinuousDistribution(samples=data.tolist())
            fallback = FitResult(
                distribution=empirical,
                dist_type="empirical",
                params={"n_samples": n},
                ks_statistic=0.0,
                ks_pvalue=1.0,
                aic=float("inf"),
                bic=float("inf"),
                log_likelihood=float("-inf"),
                n_samples=n,
            )
            return FitReport(
                best=fallback, candidates=[fallback],
                data_summary=summary, warnings=warnings,
            )

        # Rank by AIC (lower is better)
        results.sort(key=lambda r: r.aic)

        return FitReport(
            best=results[0],
            candidates=results,
            data_summary=summary,
            warnings=warnings,
        )

    def fit_single(self, data: np.ndarray, dist_type: str) -> FitResult:
        """Fit a single distribution type to data via MLE.

        Args:
            data: 1-D array of observed values
            dist_type: Distribution type name

        Returns:
            FitResult with fitted distribution and goodness-of-fit metrics

        Raises:
            ValueError: If the distribution type is unsupported or fit fails
        """
        data = np.asarray(data, dtype=float).ravel()
        data = data[np.isfinite(data)]
        n = len(data)

        scipy_dist = _get_scipy_dist(dist_type)
        if scipy_dist is None:
            raise ValueError(f"Unsupported distribution type: {dist_type}")

        # MLE fitting with loc fixed at 0 for positive distributions
        if dist_type in ("weibull", "lognormal", "gamma"):
            # Positive data only; filter zeros for fitting stability
            pos_data = data[data > 0]
            if len(pos_data) < 3:
                raise ValueError(f"Need >= 3 positive values for {dist_type}, got {len(pos_data)}")
            mle_params = scipy_dist.fit(pos_data, floc=0)
        elif dist_type == "exponential":
            pos_data = data[data > 0]
            if len(pos_data) < 2:
                raise ValueError(f"Need >= 2 positive values for exponential, got {len(pos_data)}")
            mle_params = scipy_dist.fit(pos_data, floc=0)
        elif dist_type == "beta":
            # Beta needs data in (0, 1)
            bounded = data[(data > 0) & (data < 1)]
            if len(bounded) < 3:
                raise ValueError(f"Need >= 3 values in (0,1) for beta, got {len(bounded)}")
            mle_params = scipy_dist.fit(bounded, floc=0, fscale=1)
        elif dist_type == "normal":
            mle_params = scipy_dist.fit(data)
        else:
            mle_params = scipy_dist.fit(data)

        # Convert to platform Distribution
        platform_dist, params = _scipy_to_platform(dist_type, mle_params, data)

        # Log-likelihood
        if dist_type in ("weibull", "lognormal", "gamma", "exponential"):
            eval_data = data[data > 0]
        elif dist_type == "beta":
            eval_data = data[(data > 0) & (data < 1)]
        else:
            eval_data = data

        log_lik = float(np.sum(scipy_dist.logpdf(eval_data, *mle_params)))
        if not np.isfinite(log_lik):
            log_lik = float("-inf")

        # AIC / BIC
        k = _count_params(dist_type)
        n_eval = len(eval_data)
        aic = 2 * k - 2 * log_lik if np.isfinite(log_lik) else float("inf")
        bic = k * math.log(n_eval) - 2 * log_lik if (np.isfinite(log_lik) and n_eval > 0) else float("inf")

        # KS test
        ks_stat, ks_pvalue = sp_stats.kstest(eval_data, scipy_dist.cdf, args=mle_params)

        return FitResult(
            distribution=platform_dist,
            dist_type=dist_type,
            params=params,
            ks_statistic=float(ks_stat),
            ks_pvalue=float(ks_pvalue),
            aic=float(aic),
            bic=float(bic),
            log_likelihood=float(log_lik),
            n_samples=n,
        )

    def to_distribution_config(self, result: FitResult) -> Dict[str, Any]:
        """Convert a FitResult to a JSON config for DistributionFactory.create()."""
        return result.distribution.to_dict()

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _data_summary(data: np.ndarray) -> Dict[str, float]:
        """Compute descriptive statistics for the data."""
        n = len(data)
        if n == 0:
            return {"n": 0}
        return {
            "n": float(n),
            "mean": float(np.mean(data)),
            "median": float(np.median(data)),
            "std": float(np.std(data, ddof=1)) if n > 1 else 0.0,
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "skewness": float(sp_stats.skew(data)) if n >= 3 else 0.0,
            "kurtosis": float(sp_stats.kurtosis(data)) if n >= 4 else 0.0,
            "pct_zeros": float(np.sum(data == 0) / n),
            "p10": float(np.percentile(data, 10)),
            "p25": float(np.percentile(data, 25)),
            "p50": float(np.percentile(data, 50)),
            "p75": float(np.percentile(data, 75)),
            "p90": float(np.percentile(data, 90)),
        }

    @staticmethod
    def _auto_select_candidates(data: np.ndarray) -> List[str]:
        """Heuristic candidate selection based on data characteristics."""
        has_negative = bool(np.any(data < 0))
        all_positive = bool(np.all(data > 0))
        in_unit_interval = bool(np.all((data >= 0) & (data <= 1)))
        skew = float(sp_stats.skew(data)) if len(data) >= 3 else 0.0

        if in_unit_interval and not has_negative:
            return ["beta", "normal"]
        if has_negative:
            return ["normal"]
        if all_positive and skew > 0.5:
            # Right-skewed, positive: classic lead-time/demand profile
            return ["weibull", "lognormal", "gamma", "exponential"]
        if all_positive:
            return ["normal", "lognormal", "gamma", "weibull"]
        return ["normal", "lognormal", "gamma"]

"""
Stochastic Analytics Service

Provides analytics and statistical analysis for stochastic supply chain simulations.

Key Features:
- Variability metrics (standard deviation, coefficient of variation)
- Confidence intervals for key metrics
- Distribution fit analysis (goodness-of-fit tests)
- Risk metrics (VaR, CVaR)
- Scenario comparison

Usage:
    from app.services.stochastic_analytics_service import StochasticAnalyticsService

    service = StochasticAnalyticsService()

    # Analyze variability
    variability = service.analyze_variability(samples)

    # Calculate confidence intervals
    ci = service.confidence_interval(samples, confidence=0.95)

    # Risk metrics
    var = service.value_at_risk(samples, alpha=0.05)
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from scipy import stats
from dataclasses import dataclass


@dataclass
class VariabilityMetrics:
    """Metrics describing variability in data"""
    mean: float
    std: float
    cv: float  # Coefficient of variation (std/mean)
    min: float
    max: float
    range: float
    iqr: float  # Interquartile range
    mad: float  # Median absolute deviation


@dataclass
class ConfidenceInterval:
    """Confidence interval for a statistic"""
    lower: float
    upper: float
    mean: float
    confidence: float
    margin_of_error: float


@dataclass
class RiskMetrics:
    """Risk metrics for supply chain analysis"""
    var_95: float  # Value at Risk (95th percentile)
    var_99: float  # Value at Risk (99th percentile)
    cvar_95: float  # Conditional VaR (average beyond 95th percentile)
    cvar_99: float  # Conditional VaR (average beyond 99th percentile)
    max_drawdown: float  # Maximum observed value (worst case)


@dataclass
class DistributionFit:
    """Goodness-of-fit test results"""
    distribution_type: str
    statistic: float
    p_value: float
    significant: bool  # True if p < 0.05 (reject null hypothesis)


class StochasticAnalyticsService:
    """
    Service for analyzing stochastic supply chain simulations

    Provides statistical analysis, risk metrics, and comparison tools
    for evaluating supply chain performance under uncertainty.
    """

    def __init__(self):
        """Initialize analytics service"""
        pass

    # ============================================================================
    # VARIABILITY ANALYSIS
    # ============================================================================

    def analyze_variability(self, samples: np.ndarray) -> VariabilityMetrics:
        """
        Analyze variability in sample data

        Args:
            samples: Array of sample values

        Returns:
            VariabilityMetrics with detailed variability statistics
        """
        samples = np.asarray(samples)

        mean = float(np.mean(samples))
        std = float(np.std(samples, ddof=1))  # Sample std (n-1)
        cv = (std / abs(mean) * 100) if mean != 0 else np.inf

        min_val = float(np.min(samples))
        max_val = float(np.max(samples))
        range_val = max_val - min_val

        # IQR
        q25, q75 = np.percentile(samples, [25, 75])
        iqr = float(q75 - q25)

        # MAD (Median Absolute Deviation)
        median = np.median(samples)
        mad = float(np.median(np.abs(samples - median)))

        return VariabilityMetrics(
            mean=mean,
            std=std,
            cv=cv,
            min=min_val,
            max=max_val,
            range=range_val,
            iqr=iqr,
            mad=mad
        )

    def compare_variability(self,
                           samples_a: np.ndarray,
                           samples_b: np.ndarray,
                           label_a: str = "A",
                           label_b: str = "B") -> Dict[str, Any]:
        """
        Compare variability between two datasets

        Args:
            samples_a: First dataset
            samples_b: Second dataset
            label_a: Label for first dataset
            label_b: Label for second dataset

        Returns:
            Dictionary with comparison metrics
        """
        metrics_a = self.analyze_variability(samples_a)
        metrics_b = self.analyze_variability(samples_b)

        # F-test for variance equality
        f_stat = metrics_a.std**2 / metrics_b.std**2 if metrics_b.std > 0 else np.inf
        df1 = len(samples_a) - 1
        df2 = len(samples_b) - 1
        p_value = 1 - stats.f.cdf(f_stat, df1, df2)

        return {
            label_a: {
                'mean': metrics_a.mean,
                'std': metrics_a.std,
                'cv': metrics_a.cv,
                'range': metrics_a.range
            },
            label_b: {
                'mean': metrics_b.mean,
                'std': metrics_b.std,
                'cv': metrics_b.cv,
                'range': metrics_b.range
            },
            'comparison': {
                'mean_diff': metrics_a.mean - metrics_b.mean,
                'mean_diff_pct': ((metrics_a.mean - metrics_b.mean) / metrics_b.mean * 100) if metrics_b.mean != 0 else np.inf,
                'std_ratio': metrics_a.std / metrics_b.std if metrics_b.std > 0 else np.inf,
                'cv_diff': metrics_a.cv - metrics_b.cv,
                'variance_equal': p_value > 0.05,
                'f_statistic': f_stat,
                'p_value': p_value
            }
        }

    # ============================================================================
    # CONFIDENCE INTERVALS
    # ============================================================================

    def confidence_interval(self,
                          samples: np.ndarray,
                          confidence: float = 0.95) -> ConfidenceInterval:
        """
        Calculate confidence interval for the mean

        Args:
            samples: Array of sample values
            confidence: Confidence level (default 0.95 for 95%)

        Returns:
            ConfidenceInterval with bounds and statistics
        """
        samples = np.asarray(samples)
        n = len(samples)
        mean = float(np.mean(samples))
        std_err = float(stats.sem(samples))  # Standard error of mean

        # t-distribution for small samples
        df = n - 1
        t_critical = stats.t.ppf((1 + confidence) / 2, df)

        margin = t_critical * std_err
        lower = mean - margin
        upper = mean + margin

        return ConfidenceInterval(
            lower=lower,
            upper=upper,
            mean=mean,
            confidence=confidence,
            margin_of_error=margin
        )

    def bootstrap_confidence_interval(self,
                                     samples: np.ndarray,
                                     statistic_func: callable = np.mean,
                                     confidence: float = 0.95,
                                     n_bootstrap: int = 1000,
                                     seed: Optional[int] = None) -> ConfidenceInterval:
        """
        Calculate bootstrap confidence interval for any statistic

        Args:
            samples: Array of sample values
            statistic_func: Function to compute statistic (default: mean)
            confidence: Confidence level (default 0.95)
            n_bootstrap: Number of bootstrap samples
            seed: Random seed for reproducibility

        Returns:
            ConfidenceInterval with bootstrap bounds
        """
        rng = np.random.default_rng(seed)
        samples = np.asarray(samples)
        n = len(samples)

        # Bootstrap samples
        bootstrap_stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            bootstrap_sample = rng.choice(samples, size=n, replace=True)
            bootstrap_stats[i] = statistic_func(bootstrap_sample)

        # Percentile method
        alpha = 1 - confidence
        lower = float(np.percentile(bootstrap_stats, alpha/2 * 100))
        upper = float(np.percentile(bootstrap_stats, (1 - alpha/2) * 100))
        mean = float(statistic_func(samples))
        margin = (upper - lower) / 2

        return ConfidenceInterval(
            lower=lower,
            upper=upper,
            mean=mean,
            confidence=confidence,
            margin_of_error=margin
        )

    # ============================================================================
    # RISK METRICS
    # ============================================================================

    def value_at_risk(self, samples: np.ndarray, alpha: float = 0.05) -> float:
        """
        Calculate Value at Risk (VaR)

        VaR is the threshold value such that the probability of a loss
        exceeding this value is alpha.

        Args:
            samples: Array of cost/loss values (higher = worse)
            alpha: Risk level (default 0.05 for 95% VaR)

        Returns:
            VaR threshold value
        """
        samples = np.asarray(samples)
        return float(np.percentile(samples, (1 - alpha) * 100))

    def conditional_value_at_risk(self, samples: np.ndarray, alpha: float = 0.05) -> float:
        """
        Calculate Conditional Value at Risk (CVaR), also known as Expected Shortfall

        CVaR is the expected value of losses that exceed the VaR threshold.

        Args:
            samples: Array of cost/loss values (higher = worse)
            alpha: Risk level (default 0.05 for 95% CVaR)

        Returns:
            CVaR (average of values beyond VaR)
        """
        samples = np.asarray(samples)
        var_threshold = self.value_at_risk(samples, alpha)

        # Average of values exceeding VaR
        tail_values = samples[samples >= var_threshold]
        return float(np.mean(tail_values)) if len(tail_values) > 0 else var_threshold

    def calculate_risk_metrics(self, samples: np.ndarray) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics

        Args:
            samples: Array of cost/loss values

        Returns:
            RiskMetrics with VaR, CVaR, and max drawdown
        """
        samples = np.asarray(samples)

        return RiskMetrics(
            var_95=self.value_at_risk(samples, alpha=0.05),
            var_99=self.value_at_risk(samples, alpha=0.01),
            cvar_95=self.conditional_value_at_risk(samples, alpha=0.05),
            cvar_99=self.conditional_value_at_risk(samples, alpha=0.01),
            max_drawdown=float(np.max(samples))
        )

    # ============================================================================
    # DISTRIBUTION FIT ANALYSIS
    # ============================================================================

    def kolmogorov_smirnov_test(self,
                                samples: np.ndarray,
                                distribution: str = 'norm',
                                params: Optional[Tuple] = None) -> DistributionFit:
        """
        Perform Kolmogorov-Smirnov goodness-of-fit test

        Tests whether the samples come from a specified distribution.

        Args:
            samples: Array of sample values
            distribution: Distribution name ('norm', 'lognorm', 'gamma', etc.)
            params: Distribution parameters (estimated if None)

        Returns:
            DistributionFit with test results
        """
        samples = np.asarray(samples)

        # Get distribution from scipy.stats
        dist = getattr(stats, distribution)

        # Estimate parameters if not provided
        if params is None:
            params = dist.fit(samples)

        # Perform K-S test
        statistic, p_value = stats.kstest(samples, dist.cdf, args=params)

        return DistributionFit(
            distribution_type=distribution,
            statistic=float(statistic),
            p_value=float(p_value),
            significant=p_value < 0.05  # Reject null hypothesis if True
        )

    def anderson_darling_test(self, samples: np.ndarray) -> Dict[str, Any]:
        """
        Perform Anderson-Darling test for normality

        Args:
            samples: Array of sample values

        Returns:
            Dictionary with test results
        """
        samples = np.asarray(samples)

        result = stats.anderson(samples)

        # Check against 5% significance level
        critical_value_5pct = result.critical_values[2]  # Index 2 is 5%
        significant = result.statistic > critical_value_5pct

        return {
            'statistic': float(result.statistic),
            'critical_values': result.critical_values.tolist(),
            'significance_levels': result.significance_level.tolist(),
            'reject_normality': significant
        }

    # ============================================================================
    # SCENARIO COMPARISON
    # ============================================================================

    def compare_scenarios(self,
                         scenarios: Dict[str, np.ndarray],
                         metric: str = 'total_cost') -> Dict[str, Any]:
        """
        Compare multiple scenarios across a metric

        Args:
            scenarios: Dictionary mapping scenario names to sample arrays
            metric: Name of the metric being compared

        Returns:
            Dictionary with comprehensive comparison
        """
        results = {}

        # Analyze each scenario
        for name, samples in scenarios.items():
            samples = np.asarray(samples)
            variability = self.analyze_variability(samples)
            ci = self.confidence_interval(samples, confidence=0.95)
            risk = self.calculate_risk_metrics(samples)

            results[name] = {
                'mean': variability.mean,
                'std': variability.std,
                'cv': variability.cv,
                'min': variability.min,
                'max': variability.max,
                'ci_lower': ci.lower,
                'ci_upper': ci.upper,
                'var_95': risk.var_95,
                'cvar_95': risk.cvar_95
            }

        # Rankings
        scenario_names = list(scenarios.keys())
        means = [results[name]['mean'] for name in scenario_names]
        stds = [results[name]['std'] for name in scenario_names]
        cvs = [results[name]['cv'] for name in scenario_names]

        results['rankings'] = {
            'best_mean': scenario_names[np.argmin(means)],
            'worst_mean': scenario_names[np.argmax(means)],
            'least_variable': scenario_names[np.argmin(stds)],
            'most_variable': scenario_names[np.argmax(stds)],
            'lowest_cv': scenario_names[np.argmin(cvs)],
            'highest_cv': scenario_names[np.argmax(cvs)]
        }

        return results

    # ============================================================================
    # MONTE CARLO ANALYSIS
    # ============================================================================

    def monte_carlo_summary(self,
                           simulation_results: List[Dict[str, Any]],
                           metric_keys: List[str]) -> Dict[str, Any]:
        """
        Summarize Monte Carlo simulation results

        Args:
            simulation_results: List of simulation result dictionaries
            metric_keys: Keys of metrics to analyze

        Returns:
            Dictionary with summary statistics for each metric
        """
        summary = {}

        for key in metric_keys:
            # Extract metric values from all simulations
            values = np.array([result.get(key, np.nan) for result in simulation_results])

            # Remove NaN values
            values = values[~np.isnan(values)]

            if len(values) > 0:
                variability = self.analyze_variability(values)
                ci = self.confidence_interval(values, confidence=0.95)

                summary[key] = {
                    'mean': variability.mean,
                    'std': variability.std,
                    'cv': variability.cv,
                    'min': variability.min,
                    'max': variability.max,
                    'median': float(np.median(values)),
                    'p5': float(np.percentile(values, 5)),
                    'p95': float(np.percentile(values, 95)),
                    'ci_lower': ci.lower,
                    'ci_upper': ci.upper,
                    'n_samples': len(values)
                }

        return summary

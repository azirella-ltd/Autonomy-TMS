"""
Advanced Analytics Service
Phase 6 Sprint 2: Advanced Analytics

Provides advanced statistical analysis capabilities:
1. Sensitivity Analysis (OAT, Sobol indices)
2. Correlation Analysis (Pearson, Spearman)
3. Time Series Analysis (ACF, PACF, trend decomposition)
4. Optimization Integration
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import spearmanr, kendalltau
from typing import Dict, List, Tuple, Callable, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SensitivityResult:
    """One-at-a-time sensitivity analysis result"""
    parameter: str
    values: List[float]
    outputs: List[float]
    sensitivity: float  # Change in output / change in input
    min_output: float
    max_output: float
    output_range: float


@dataclass
class SobolIndices:
    """Sobol sensitivity indices"""
    parameter: str
    first_order: float  # Main effect
    total_order: float  # Total effect (including interactions)
    confidence_interval: Tuple[float, float]


@dataclass
class CorrelationMatrix:
    """Correlation analysis result"""
    variables: List[str]
    correlation_matrix: np.ndarray  # NxN correlation matrix
    p_values: np.ndarray  # NxN p-value matrix
    method: str  # 'pearson', 'spearman', 'kendall'


@dataclass
class TimeSeriesDecomposition:
    """Time series decomposition result"""
    trend: np.ndarray
    seasonal: np.ndarray
    residual: np.ndarray
    original: np.ndarray


@dataclass
class AutocorrelationResult:
    """Autocorrelation analysis result"""
    lags: np.ndarray
    acf_values: np.ndarray
    pacf_values: np.ndarray
    confidence_interval: Tuple[float, float]


@dataclass
class ForecastAccuracy:
    """Forecast accuracy metrics"""
    mape: float  # Mean Absolute Percentage Error
    rmse: float  # Root Mean Squared Error
    mae: float   # Mean Absolute Error
    mse: float   # Mean Squared Error
    r_squared: float  # R-squared


# ============================================================================
# Advanced Analytics Service
# ============================================================================

class AdvancedAnalyticsService:
    """
    Advanced analytics service providing sensitivity analysis,
    correlation analysis, and time series analysis.
    """

    def __init__(self):
        self.logger = logger

    # ========================================================================
    # Sensitivity Analysis
    # ========================================================================

    def one_at_a_time_sensitivity(
        self,
        base_params: Dict[str, float],
        param_ranges: Dict[str, Tuple[float, float]],
        simulation_func: Callable[[Dict], float],
        num_samples: int = 10
    ) -> List[SensitivityResult]:
        """
        One-at-a-time (OAT) sensitivity analysis

        Varies each parameter independently while holding others constant
        to measure the impact on the output.

        Args:
            base_params: Baseline parameter values
            param_ranges: Dict of (min, max) ranges for each parameter
            simulation_func: Function that takes params dict and returns output
            num_samples: Number of samples per parameter

        Returns:
            List of SensitivityResult objects
        """
        results = []

        for param_name, (min_val, max_val) in param_ranges.items():
            if param_name not in base_params:
                logger.warning(f"Parameter {param_name} not in base_params, skipping")
                continue

            values = np.linspace(min_val, max_val, num_samples)
            outputs = []

            for value in values:
                # Create params with this parameter varied
                params = base_params.copy()
                params[param_name] = value

                # Run simulation
                output = simulation_func(params)
                outputs.append(output)

            # Calculate sensitivity (slope of output vs input)
            if len(outputs) > 1:
                sensitivity = (max(outputs) - min(outputs)) / (max_val - min_val)
            else:
                sensitivity = 0.0

            results.append(SensitivityResult(
                parameter=param_name,
                values=values.tolist(),
                outputs=outputs,
                sensitivity=sensitivity,
                min_output=min(outputs),
                max_output=max(outputs),
                output_range=max(outputs) - min(outputs)
            ))

        # Sort by sensitivity (most sensitive first)
        results.sort(key=lambda r: abs(r.sensitivity), reverse=True)

        return results

    def sobol_sensitivity_indices(
        self,
        param_ranges: Dict[str, Tuple[float, float]],
        simulation_func: Callable[[Dict], float],
        num_samples: int = 1000,
        confidence: float = 0.95
    ) -> List[SobolIndices]:
        """
        Variance-based sensitivity analysis using Sobol indices

        Calculates first-order (main effect) and total-order (including interactions)
        sensitivity indices using Monte Carlo sampling.

        Args:
            param_ranges: Dict of (min, max) ranges for each parameter
            simulation_func: Function that takes params dict and returns output
            num_samples: Number of Monte Carlo samples
            confidence: Confidence level for intervals

        Returns:
            List of SobolIndices objects
        """
        param_names = list(param_ranges.keys())
        num_params = len(param_names)

        # Generate two independent sample matrices (Saltelli's scheme)
        # Matrix A: base sample matrix
        A = np.random.random((num_samples, num_params))
        # Matrix B: resample matrix
        B = np.random.random((num_samples, num_params))

        # Scale to parameter ranges
        for i, param_name in enumerate(param_names):
            min_val, max_val = param_ranges[param_name]
            A[:, i] = A[:, i] * (max_val - min_val) + min_val
            B[:, i] = B[:, i] * (max_val - min_val) + min_val

        # Evaluate model for matrix A and B
        f_A = np.array([simulation_func(dict(zip(param_names, row))) for row in A])
        f_B = np.array([simulation_func(dict(zip(param_names, row))) for row in B])

        # Calculate variance
        var_y = np.var(np.concatenate([f_A, f_B]))

        results = []

        for i, param_name in enumerate(param_names):
            # Create matrix A_B^(i) - all from A except column i from B
            A_Bi = A.copy()
            A_Bi[:, i] = B[:, i]
            f_A_Bi = np.array([simulation_func(dict(zip(param_names, row))) for row in A_Bi])

            # First-order index (main effect)
            S_i = np.mean(f_B * (f_A_Bi - f_A)) / var_y

            # Total-order index (total effect)
            S_Ti = np.mean((f_A - f_A_Bi) ** 2) / (2 * var_y)

            # Bootstrap confidence interval
            bootstrap_S_i = []
            for _ in range(100):
                indices = np.random.choice(num_samples, num_samples, replace=True)
                boot_var = np.var(np.concatenate([f_A[indices], f_B[indices]]))
                boot_S_i = np.mean(f_B[indices] * (f_A_Bi[indices] - f_A[indices])) / boot_var
                bootstrap_S_i.append(boot_S_i)

            ci_lower = np.percentile(bootstrap_S_i, (1 - confidence) / 2 * 100)
            ci_upper = np.percentile(bootstrap_S_i, (1 + confidence) / 2 * 100)

            results.append(SobolIndices(
                parameter=param_name,
                first_order=float(S_i),
                total_order=float(S_Ti),
                confidence_interval=(float(ci_lower), float(ci_upper))
            ))

        # Sort by total-order index (most important first)
        results.sort(key=lambda r: abs(r.total_order), reverse=True)

        return results

    def tornado_diagram_data(
        self,
        sensitivity_results: List[SensitivityResult]
    ) -> Dict[str, List]:
        """
        Prepare data for tornado diagram visualization

        Args:
            sensitivity_results: List of sensitivity results from OAT analysis

        Returns:
            Dictionary with parameter names and output ranges
        """
        data = {
            'parameters': [],
            'min_outputs': [],
            'max_outputs': [],
            'ranges': [],
            'sensitivities': []
        }

        # Sort by output range (for tornado effect)
        sorted_results = sorted(sensitivity_results, key=lambda r: r.output_range, reverse=True)

        for result in sorted_results:
            data['parameters'].append(result.parameter)
            data['min_outputs'].append(result.min_output)
            data['max_outputs'].append(result.max_output)
            data['ranges'].append(result.output_range)
            data['sensitivities'].append(result.sensitivity)

        return data

    # ========================================================================
    # Correlation Analysis
    # ========================================================================

    def correlation_matrix(
        self,
        data_dict: Dict[str, np.ndarray],
        method: str = 'pearson'
    ) -> CorrelationMatrix:
        """
        Calculate correlation matrix for multiple variables

        Args:
            data_dict: Dictionary of variable names to arrays
            method: 'pearson', 'spearman', or 'kendall'

        Returns:
            CorrelationMatrix object
        """
        # Convert to DataFrame for easier correlation calculation
        df = pd.DataFrame(data_dict)
        variables = list(data_dict.keys())

        if method == 'pearson':
            corr_matrix = df.corr(method='pearson').values
            # Calculate p-values
            n = len(df)
            p_values = np.zeros_like(corr_matrix)
            for i in range(len(variables)):
                for j in range(len(variables)):
                    if i != j:
                        _, p_val = stats.pearsonr(df[variables[i]], df[variables[j]])
                        p_values[i, j] = p_val

        elif method == 'spearman':
            corr_matrix = df.corr(method='spearman').values
            # Calculate p-values
            p_values = np.zeros_like(corr_matrix)
            for i in range(len(variables)):
                for j in range(len(variables)):
                    if i != j:
                        _, p_val = spearmanr(df[variables[i]], df[variables[j]])
                        p_values[i, j] = p_val

        elif method == 'kendall':
            corr_matrix = df.corr(method='kendall').values
            # Calculate p-values
            p_values = np.zeros_like(corr_matrix)
            for i in range(len(variables)):
                for j in range(len(variables)):
                    if i != j:
                        _, p_val = kendalltau(df[variables[i]], df[variables[j]])
                        p_values[i, j] = p_val
        else:
            raise ValueError(f"Unknown method: {method}")

        return CorrelationMatrix(
            variables=variables,
            correlation_matrix=corr_matrix,
            p_values=p_values,
            method=method
        )

    def find_strong_correlations(
        self,
        corr_matrix: CorrelationMatrix,
        threshold: float = 0.7,
        p_value_threshold: float = 0.05
    ) -> List[Dict[str, Any]]:
        """
        Find pairs of variables with strong correlation

        Args:
            corr_matrix: CorrelationMatrix object
            threshold: Minimum absolute correlation to report
            p_value_threshold: Maximum p-value for significance

        Returns:
            List of dictionaries with correlation info
        """
        strong_correlations = []
        n = len(corr_matrix.variables)

        for i in range(n):
            for j in range(i + 1, n):  # Upper triangle only
                corr = corr_matrix.correlation_matrix[i, j]
                p_val = corr_matrix.p_values[i, j]

                if abs(corr) >= threshold and p_val < p_value_threshold:
                    strong_correlations.append({
                        'var1': corr_matrix.variables[i],
                        'var2': corr_matrix.variables[j],
                        'correlation': float(corr),
                        'p_value': float(p_val),
                        'strength': 'strong' if abs(corr) >= 0.9 else 'moderate'
                    })

        # Sort by absolute correlation
        strong_correlations.sort(key=lambda x: abs(x['correlation']), reverse=True)

        return strong_correlations

    # ========================================================================
    # Time Series Analysis
    # ========================================================================

    def autocorrelation_function(
        self,
        time_series: np.ndarray,
        max_lag: Optional[int] = None,
        confidence: float = 0.95
    ) -> AutocorrelationResult:
        """
        Calculate autocorrelation function (ACF)

        Args:
            time_series: Time series data
            max_lag: Maximum lag to calculate (default: len/4)
            confidence: Confidence level for significance bounds

        Returns:
            AutocorrelationResult object
        """
        n = len(time_series)
        if max_lag is None:
            max_lag = min(n // 4, 40)

        # Calculate ACF using numpy
        mean = np.mean(time_series)
        c0 = np.sum((time_series - mean) ** 2) / n

        acf_values = np.zeros(max_lag + 1)
        acf_values[0] = 1.0

        for lag in range(1, max_lag + 1):
            c_lag = np.sum((time_series[:-lag] - mean) * (time_series[lag:] - mean)) / n
            acf_values[lag] = c_lag / c0

        # Confidence interval (approximate)
        z_critical = stats.norm.ppf((1 + confidence) / 2)
        conf_int = z_critical / np.sqrt(n)

        return AutocorrelationResult(
            lags=np.arange(max_lag + 1),
            acf_values=acf_values,
            pacf_values=self._calculate_pacf(time_series, max_lag),
            confidence_interval=(-conf_int, conf_int)
        )

    def _calculate_pacf(self, time_series: np.ndarray, max_lag: int) -> np.ndarray:
        """Calculate partial autocorrelation function (PACF)"""
        n = len(time_series)
        pacf_values = np.zeros(max_lag + 1)
        pacf_values[0] = 1.0

        # Use Yule-Walker equations for PACF
        for lag in range(1, max_lag + 1):
            # Build autocorrelation matrix
            acf = np.array([self._acf_single_lag(time_series, k) for k in range(lag + 1)])

            # Solve Yule-Walker equations
            if lag == 1:
                pacf_values[lag] = acf[1]
            else:
                R = np.zeros((lag, lag))
                for i in range(lag):
                    for j in range(lag):
                        R[i, j] = acf[abs(i - j)]

                r = acf[1:lag + 1]
                try:
                    phi = np.linalg.solve(R, r)
                    pacf_values[lag] = phi[-1]
                except np.linalg.LinAlgError:
                    pacf_values[lag] = 0.0

        return pacf_values

    def _acf_single_lag(self, time_series: np.ndarray, lag: int) -> float:
        """Calculate ACF for a single lag"""
        n = len(time_series)
        mean = np.mean(time_series)
        c0 = np.sum((time_series - mean) ** 2) / n

        if lag == 0:
            return 1.0

        c_lag = np.sum((time_series[:-lag] - mean) * (time_series[lag:] - mean)) / n
        return c_lag / c0

    def decompose_time_series(
        self,
        time_series: np.ndarray,
        period: int,
        model: str = 'additive'
    ) -> TimeSeriesDecomposition:
        """
        Decompose time series into trend, seasonal, and residual components

        Args:
            time_series: Time series data
            period: Seasonal period
            model: 'additive' or 'multiplicative'

        Returns:
            TimeSeriesDecomposition object
        """
        n = len(time_series)

        # Calculate trend using moving average
        window = period if period % 2 == 1 else period + 1
        trend = self._moving_average(time_series, window)

        # Calculate seasonal component
        if model == 'additive':
            detrended = time_series - trend
        else:  # multiplicative
            detrended = time_series / (trend + 1e-10)  # Avoid division by zero

        # Calculate seasonal indices
        seasonal = np.zeros(n)
        for i in range(period):
            indices = np.arange(i, n, period)
            seasonal[indices] = np.mean(detrended[indices])

        # Center seasonal component
        if model == 'additive':
            seasonal = seasonal - np.mean(seasonal)
        else:
            seasonal = seasonal / np.mean(seasonal)

        # Calculate residual
        if model == 'additive':
            residual = time_series - trend - seasonal
        else:
            residual = time_series / ((trend + 1e-10) * (seasonal + 1e-10))

        return TimeSeriesDecomposition(
            trend=trend,
            seasonal=seasonal,
            residual=residual,
            original=time_series
        )

    def _moving_average(self, data: np.ndarray, window: int) -> np.ndarray:
        """Calculate moving average with centered window"""
        n = len(data)
        result = np.zeros(n)

        half_window = window // 2

        for i in range(n):
            start = max(0, i - half_window)
            end = min(n, i + half_window + 1)
            result[i] = np.mean(data[start:end])

        return result

    def forecast_accuracy_metrics(
        self,
        actual: np.ndarray,
        predicted: np.ndarray
    ) -> ForecastAccuracy:
        """
        Calculate forecast accuracy metrics

        Args:
            actual: Actual values
            predicted: Predicted values

        Returns:
            ForecastAccuracy object
        """
        # Remove NaN values
        mask = ~(np.isnan(actual) | np.isnan(predicted))
        actual = actual[mask]
        predicted = predicted[mask]

        # Mean Absolute Percentage Error
        mape = np.mean(np.abs((actual - predicted) / (actual + 1e-10))) * 100

        # Root Mean Squared Error
        mse = np.mean((actual - predicted) ** 2)
        rmse = np.sqrt(mse)

        # Mean Absolute Error
        mae = np.mean(np.abs(actual - predicted))

        # R-squared
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        r_squared = 1 - (ss_res / (ss_tot + 1e-10))

        return ForecastAccuracy(
            mape=float(mape),
            rmse=float(rmse),
            mae=float(mae),
            mse=float(mse),
            r_squared=float(r_squared)
        )


if __name__ == "__main__":
    # Example usage and testing
    print("="*80)
    print("ADVANCED ANALYTICS SERVICE - DEMO")
    print("="*80)

    service = AdvancedAnalyticsService()

    # Example 1: One-at-a-time sensitivity analysis
    print("\n1. Sensitivity Analysis (OAT)")
    print("-" * 80)

    def simple_sim(params):
        # Simple quadratic function
        return params['x']**2 + 2*params['y'] + params['z']

    base = {'x': 1.0, 'y': 2.0, 'z': 3.0}
    ranges = {'x': (0, 2), 'y': (1, 3), 'z': (2, 4)}

    sensitivity = service.one_at_a_time_sensitivity(base, ranges, simple_sim, num_samples=5)

    for result in sensitivity:
        print(f"  {result.parameter}: sensitivity={result.sensitivity:.3f}, range={result.output_range:.3f}")

    # Example 2: Correlation analysis
    print("\n2. Correlation Analysis")
    print("-" * 80)

    data = {
        'cost': np.random.normal(1000, 100, 100),
        'inventory': np.random.normal(50, 10, 100),
        'service_level': np.random.beta(9, 1, 100)
    }
    # Add some correlation
    data['backlog'] = 1200 - data['cost'] + np.random.normal(0, 50, 100)

    corr = service.correlation_matrix(data, method='pearson')
    print(f"  Variables: {corr.variables}")
    print(f"  Correlation matrix shape: {corr.correlation_matrix.shape}")

    strong = service.find_strong_correlations(corr, threshold=0.5)
    for c in strong:
        print(f"  {c['var1']} <-> {c['var2']}: r={c['correlation']:.3f}, p={c['p_value']:.4f}")

    # Example 3: Time series analysis
    print("\n3. Time Series Analysis (ACF)")
    print("-" * 80)

    # Generate time series with autocorrelation
    ts = np.cumsum(np.random.normal(0, 1, 100))

    acf_result = service.autocorrelation_function(ts, max_lag=20)
    print(f"  ACF values (first 5 lags): {acf_result.acf_values[:5]}")
    print(f"  Confidence interval: {acf_result.confidence_interval}")

    print("\n✅ Advanced Analytics Service demo complete!")

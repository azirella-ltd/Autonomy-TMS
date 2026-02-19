"""
Sampling Strategies for Stochastic Distributions

This module provides different strategies for sampling from distributions:
1. IndependentSampling: Sample each distribution independently
2. CorrelatedSampling: Sample with correlation matrix (multivariate)
3. TimeSeriesSampling: Sample with autocorrelation (AR process)

These strategies enable realistic modeling of dependencies and temporal patterns
in supply chain variables (e.g., lead times that covary, demand with seasonality).
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import numpy as np
from .distributions import Distribution, DistributionFactory


class SamplingStrategy(ABC):
    """Base class for sampling strategies"""

    @abstractmethod
    def sample(self, distributions: Dict[str, Distribution],
               seed: Optional[int] = None) -> Dict[str, float]:
        """Sample values from all distributions

        Args:
            distributions: Dictionary mapping variable names to Distribution objects
            seed: Random seed for reproducibility

        Returns:
            Dictionary mapping variable names to sampled values
        """
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize strategy to JSON"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'SamplingStrategy':
        """Deserialize strategy from JSON"""
        pass


class IndependentSampling(SamplingStrategy):
    """Sample each distribution independently

    This is the simplest and most common strategy. Each variable is sampled
    independently without considering correlations between variables.

    Use when:
    - Variables are truly independent
    - No historical correlation data available
    - Simplicity is preferred over accuracy
    """

    def __init__(self):
        pass

    def sample(self, distributions: Dict[str, Distribution],
               seed: Optional[int] = None) -> Dict[str, float]:
        """Sample each distribution independently

        Args:
            distributions: Dictionary of distributions
            seed: Random seed (incremented for each variable)

        Returns:
            Dictionary of sampled values
        """
        result = {}
        for i, (var_name, dist) in enumerate(distributions.items()):
            var_seed = None if seed is None else seed + i
            sample = dist.sample(size=1, seed=var_seed)
            result[var_name] = float(sample[0])

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'independent'}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'IndependentSampling':
        return cls()


class CorrelatedSampling(SamplingStrategy):
    """Sample with correlation matrix using Cholesky decomposition

    This strategy allows modeling dependencies between variables. For example,
    manufacturing lead time and yield might be negatively correlated (longer
    lead times → lower yields due to quality issues).

    The correlation matrix must be:
    - Symmetric
    - Positive semi-definite
    - Diagonal elements = 1

    Use when:
    - Known correlations exist between variables
    - Historical data shows covariance
    - More realistic modeling is needed

    Example:
        # Lead time and yield negatively correlated (-0.3)
        variables = ['lead_time', 'yield']
        correlation_matrix = [
            [1.0, -0.3],
            [-0.3, 1.0]
        ]
    """

    def __init__(self, variables: list, correlation_matrix: np.ndarray):
        """Initialize correlated sampling

        Args:
            variables: List of variable names (ordered)
            correlation_matrix: NxN correlation matrix (symmetric, PSD)

        Raises:
            ValueError: If correlation matrix is invalid
        """
        if len(variables) != correlation_matrix.shape[0]:
            raise ValueError(f"variables length ({len(variables)}) must match "
                           f"correlation matrix size ({correlation_matrix.shape[0]})")

        if correlation_matrix.shape[0] != correlation_matrix.shape[1]:
            raise ValueError("correlation_matrix must be square")

        # Validate symmetry
        if not np.allclose(correlation_matrix, correlation_matrix.T):
            raise ValueError("correlation_matrix must be symmetric")

        # Validate diagonal is 1
        if not np.allclose(np.diag(correlation_matrix), 1.0):
            raise ValueError("correlation_matrix diagonal must be 1.0")

        # Validate range [-1, 1]
        if np.any(np.abs(correlation_matrix) > 1.0):
            raise ValueError("correlation_matrix elements must be in [-1, 1]")

        self.variables = list(variables)
        self.correlation_matrix = np.array(correlation_matrix, dtype=float)

        # Precompute Cholesky decomposition
        try:
            self.cholesky = np.linalg.cholesky(self.correlation_matrix)
        except np.linalg.LinAlgError as e:
            raise ValueError(f"correlation_matrix must be positive semi-definite: {e}")

    def sample(self, distributions: Dict[str, Distribution],
               seed: Optional[int] = None) -> Dict[str, float]:
        """Sample with correlations using Gaussian copula

        Algorithm:
        1. Sample independent standard normal variables Z ~ N(0, 1)
        2. Apply correlation: X = L @ Z (where L is Cholesky decomposition)
        3. Transform to uniform: U = Φ(X)
        4. Apply inverse CDF of target distributions: F^{-1}(U)

        Args:
            distributions: Dictionary of distributions
            seed: Random seed

        Returns:
            Dictionary of correlated samples
        """
        rng = np.random.default_rng(seed)

        # Filter distributions to only those in self.variables
        ordered_dists = []
        for var in self.variables:
            if var not in distributions:
                raise ValueError(f"Variable '{var}' not found in distributions")
            ordered_dists.append(distributions[var])

        # Step 1: Sample independent standard normals
        z = rng.standard_normal(len(self.variables))

        # Step 2: Apply correlation via Cholesky
        x = self.cholesky @ z

        # Step 3: Transform to uniform via CDF of standard normal
        from scipy.stats import norm
        u = norm.cdf(x)

        # Step 4: Transform to target distributions via inverse CDF
        # For simplicity, we use quantile approximation:
        # Sample many values, compute empirical CDF, interpolate
        result = {}
        for i, (var, dist) in enumerate(zip(self.variables, ordered_dists)):
            # Generate samples for inverse CDF approximation
            samples = dist.sample(size=10000, seed=seed)
            samples_sorted = np.sort(samples)

            # Interpolate quantile
            quantile = u[i]
            idx = int(quantile * len(samples_sorted))
            idx = np.clip(idx, 0, len(samples_sorted) - 1)
            value = samples_sorted[idx]

            result[var] = float(value)

        # Add any remaining distributions (not in correlation matrix)
        for var, dist in distributions.items():
            if var not in self.variables:
                sample = dist.sample(size=1, seed=seed)
                result[var] = float(sample[0])

        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'correlated',
            'variables': self.variables,
            'correlation_matrix': self.correlation_matrix.tolist()
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'CorrelatedSampling':
        return cls(
            variables=config['variables'],
            correlation_matrix=np.array(config['correlation_matrix'])
        )


class TimeSeriesSampling(SamplingStrategy):
    """Sample with temporal autocorrelation using AR(1) process

    This strategy models temporal dependencies where current values depend on
    previous values. Useful for variables that have inertia or momentum.

    The AR(1) model is:
        X_t = μ + φ(X_{t-1} - μ) + ε_t

    where:
    - μ = long-term mean (distribution mean)
    - φ = autocorrelation coefficient in [-1, 1]
    - ε_t = white noise from distribution

    Use when:
    - Variables show temporal persistence (today → tomorrow)
    - Demand has seasonality or trends
    - Lead times exhibit serial correlation

    Example:
        # Demand with moderate persistence (φ=0.5)
        strategy = TimeSeriesSampling(ar_coeff=0.5)

        # High persistence (φ=0.9) - slow-changing
        # Low persistence (φ=0.1) - fast-changing
        # Negative (φ=-0.3) - oscillating
    """

    def __init__(self, ar_coeff: float = 0.5, warmup_periods: int = 10):
        """Initialize time series sampling

        Args:
            ar_coeff: Autocorrelation coefficient φ in [-1, 1]
            warmup_periods: Number of warmup samples to reach steady state

        Raises:
            ValueError: If ar_coeff not in [-1, 1]
        """
        if not -1 <= ar_coeff <= 1:
            raise ValueError(f"ar_coeff ({ar_coeff}) must be in [-1, 1]")

        self.ar_coeff = float(ar_coeff)
        self.warmup_periods = int(warmup_periods)
        self.prev_values: Dict[str, float] = {}
        self.initialized: bool = False

    def _initialize(self, distributions: Dict[str, Distribution],
                   seed: Optional[int] = None):
        """Initialize with warmup samples to reach steady state"""
        rng = np.random.default_rng(seed)

        for var_name, dist in distributions.items():
            # Start at distribution mean
            mean = dist.mean()
            value = mean

            # Run warmup to reach AR(1) steady state
            for _ in range(self.warmup_periods):
                epsilon = dist.sample(size=1, seed=None if seed is None else rng.integers(0, 1000000))[0]
                epsilon_centered = epsilon - mean

                # AR(1): X_t = μ + φ(X_{t-1} - μ) + ε_t
                # Simplified: X_t = φ*X_{t-1} + (1-φ)*μ + ε_t
                value = mean + self.ar_coeff * (value - mean) + epsilon_centered * (1 - abs(self.ar_coeff))

            self.prev_values[var_name] = value

        self.initialized = True

    def sample(self, distributions: Dict[str, Distribution],
               seed: Optional[int] = None) -> Dict[str, float]:
        """Sample using AR(1) process

        Args:
            distributions: Dictionary of distributions
            seed: Random seed

        Returns:
            Dictionary of sampled values with temporal correlation
        """
        if not self.initialized:
            self._initialize(distributions, seed)

        rng = np.random.default_rng(seed)
        result = {}

        for var_name, dist in distributions.items():
            mean = dist.mean()

            # Sample innovation (white noise)
            epsilon = dist.sample(size=1, seed=None if seed is None else rng.integers(0, 1000000))[0]
            epsilon_centered = epsilon - mean

            # Get previous value (or initialize if new variable)
            if var_name not in self.prev_values:
                self.prev_values[var_name] = mean

            prev = self.prev_values[var_name]

            # AR(1) update
            # Scale noise by (1 - |φ|) to maintain variance
            value = mean + self.ar_coeff * (prev - mean) + epsilon_centered * (1 - abs(self.ar_coeff))

            # Store for next time
            self.prev_values[var_name] = value
            result[var_name] = float(value)

        return result

    def reset(self):
        """Reset time series state (start fresh)"""
        self.prev_values = {}
        self.initialized = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'time_series',
            'ar_coeff': self.ar_coeff,
            'warmup_periods': self.warmup_periods,
            'prev_values': self.prev_values,
            'initialized': self.initialized
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'TimeSeriesSampling':
        strategy = cls(
            ar_coeff=config['ar_coeff'],
            warmup_periods=config.get('warmup_periods', 10)
        )
        strategy.prev_values = config.get('prev_values', {})
        strategy.initialized = config.get('initialized', False)
        return strategy


# ==============================================================================
# SAMPLING STRATEGY FACTORY
# ==============================================================================

class SamplingStrategyFactory:
    """Factory for creating sampling strategies from JSON config"""

    _registry = {
        'independent': IndependentSampling,
        'correlated': CorrelatedSampling,
        'time_series': TimeSeriesSampling,
    }

    @classmethod
    def create(cls, config: Optional[Dict[str, Any]] = None) -> SamplingStrategy:
        """Create sampling strategy from JSON config

        Args:
            config: Dictionary with 'type' key and strategy parameters
                   If None, returns IndependentSampling (default)

        Returns:
            SamplingStrategy instance

        Raises:
            ValueError: If strategy type unknown or config invalid
        """
        if config is None:
            return IndependentSampling()

        strategy_type = config.get('type', 'independent')

        if strategy_type not in cls._registry:
            raise ValueError(f"Unknown sampling strategy: {strategy_type}. "
                           f"Available types: {list(cls._registry.keys())}")

        try:
            return cls._registry[strategy_type].from_dict(config)
        except Exception as e:
            raise ValueError(f"Failed to create {strategy_type} strategy: {e}") from e

    @classmethod
    def get_available_types(cls) -> list:
        """Get list of available sampling strategy types"""
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str, strategy_class: type):
        """Register a new sampling strategy type (for extensions)"""
        if not issubclass(strategy_class, SamplingStrategy):
            raise ValueError(f"{strategy_class} must be subclass of SamplingStrategy")
        cls._registry[name] = strategy_class

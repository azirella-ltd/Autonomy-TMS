"""
Distribution Engine for Stochastic Supply Chain Modeling

This module provides the main interface for working with distributions and sampling.
It handles:
- Creating distributions from JSON config
- Sampling with different strategies
- Managing distribution state and seeds
- Backward compatibility with deterministic values

Usage Example:
    # Create engine
    engine = DistributionEngine(seed=42)

    # Define stochastic variables
    variables = {
        'lead_time': {
            'type': 'normal',
            'mean': 7.0,
            'stddev': 1.5,
            'min': 3.0,
            'max': 12.0
        },
        'capacity': {
            'type': 'truncated_normal',
            'mean': 100.0,
            'stddev': 15.0,
            'min': 60.0,
            'max': 120.0
        }
    }

    # Sample values
    samples = engine.sample(variables)
    # {'lead_time': 7.23, 'capacity': 98.45}

    # Use with sampling strategy
    strategy = TimeSeriesSampling(ar_coeff=0.5)
    samples = engine.sample_with_strategy(variables, strategy)
"""

from typing import Dict, Optional, Any, List
import numpy as np
from .distributions import Distribution, DistributionFactory
from .sampling_strategies import (
    SamplingStrategy,
    SamplingStrategyFactory,
    IndependentSampling
)


class DistributionEngine:
    """Main engine for distribution management and sampling

    This class provides a high-level interface for:
    - Creating distributions from JSON configs
    - Sampling values (with/without strategies)
    - Managing random seeds for reproducibility
    - Caching distributions for performance
    """

    def __init__(self, seed: Optional[int] = None,
                 default_strategy: Optional[SamplingStrategy] = None):
        """Initialize distribution engine

        Args:
            seed: Global random seed for reproducibility
            default_strategy: Default sampling strategy (IndependentSampling if None)
        """
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.default_strategy = default_strategy or IndependentSampling()

        # Cache for parsed distributions (performance)
        self._distribution_cache: Dict[str, Distribution] = {}

    def create_distribution(self, config: Dict[str, Any],
                          cache_key: Optional[str] = None) -> Distribution:
        """Create a distribution from JSON config

        Args:
            config: Distribution configuration dict
            cache_key: Optional key to cache the distribution

        Returns:
            Distribution instance

        Raises:
            ValueError: If config is invalid
        """
        # Check cache
        if cache_key and cache_key in self._distribution_cache:
            return self._distribution_cache[cache_key]

        # Create distribution
        dist = DistributionFactory.create(config)

        # Cache if requested
        if cache_key:
            self._distribution_cache[cache_key] = dist

        return dist

    def sample(self, variable_configs: Dict[str, Dict[str, Any]],
              size: int = 1,
              seed: Optional[int] = None) -> Dict[str, Any]:
        """Sample from multiple distributions independently

        Args:
            variable_configs: Dict mapping variable names to distribution configs
            size: Number of samples per variable
            seed: Random seed (uses engine seed if None)

        Returns:
            If size=1: Dict[str, float] mapping variable names to single values
            If size>1: Dict[str, np.ndarray] mapping variable names to arrays

        Example:
            configs = {
                'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5},
                'capacity': {'type': 'uniform', 'min': 80.0, 'max': 120.0}
            }
            samples = engine.sample(configs, size=10)
            # {'lead_time': array([...]), 'capacity': array([...])}
        """
        if seed is None:
            seed = self.rng.integers(0, 2**31 - 1)

        result = {}

        for var_name, config in variable_configs.items():
            # Handle None config (backward compatible - no distribution)
            if config is None:
                if size == 1:
                    result[var_name] = None
                else:
                    result[var_name] = np.full(size, None)
                continue

            # Create distribution
            dist = self.create_distribution(config, cache_key=f"{var_name}_{hash(str(config))}")

            # Sample
            samples = dist.sample(size=size, seed=seed)

            # Return single value if size=1
            if size == 1:
                result[var_name] = float(samples[0])
            else:
                result[var_name] = samples

        return result

    def sample_with_strategy(self,
                            variable_configs: Dict[str, Dict[str, Any]],
                            strategy: Optional[SamplingStrategy] = None,
                            seed: Optional[int] = None) -> Dict[str, float]:
        """Sample from distributions using a sampling strategy

        This enables correlated or time-series sampling.

        Args:
            variable_configs: Dict mapping variable names to distribution configs
            strategy: Sampling strategy (uses default if None)
            seed: Random seed (uses engine seed if None)

        Returns:
            Dict mapping variable names to sampled values

        Example:
            # Time series sampling
            strategy = TimeSeriesSampling(ar_coeff=0.7)
            samples1 = engine.sample_with_strategy(configs, strategy)
            samples2 = engine.sample_with_strategy(configs, strategy)
            # samples2 will be correlated with samples1

            # Correlated sampling
            strategy = CorrelatedSampling(
                variables=['lead_time', 'yield'],
                correlation_matrix=[[1.0, -0.3], [-0.3, 1.0]]
            )
            samples = engine.sample_with_strategy(configs, strategy)
        """
        if strategy is None:
            strategy = self.default_strategy

        if seed is None:
            seed = self.rng.integers(0, 2**31 - 1)

        # Create distributions
        distributions = {}
        for var_name, config in variable_configs.items():
            if config is None:
                continue
            dist = self.create_distribution(config, cache_key=f"{var_name}_{hash(str(config))}")
            distributions[var_name] = dist

        # Sample using strategy
        samples = strategy.sample(distributions, seed=seed)

        return samples

    def sample_or_default(self,
                         config: Optional[Dict[str, Any]],
                         default_value: float,
                         seed: Optional[int] = None) -> float:
        """Sample from distribution or return default if config is None

        This is the key function for backward compatibility. If a distribution
        config is provided, sample from it. Otherwise, use the deterministic
        default value.

        Args:
            config: Distribution config (can be None for deterministic)
            default_value: Value to use if config is None
            seed: Random seed

        Returns:
            Sampled value (or default if no distribution)

        Example:
            # With distribution
            lead_time = engine.sample_or_default(
                config={'type': 'normal', 'mean': 7.0, 'stddev': 1.5},
                default_value=7.0
            )  # Returns sampled value ~7.0

            # Without distribution (backward compatible)
            lead_time = engine.sample_or_default(
                config=None,
                default_value=7.0
            )  # Returns 7.0 (deterministic)
        """
        if config is None:
            return default_value

        if seed is None:
            seed = self.rng.integers(0, 2**31 - 1)

        dist = self.create_distribution(config)
        sample = dist.sample(size=1, seed=seed)
        return float(sample[0])

    def get_distribution_stats(self,
                              variable_configs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """Get statistical summary of distributions

        Args:
            variable_configs: Dict mapping variable names to distribution configs

        Returns:
            Dict mapping variable names to stats dicts with keys:
            - mean: Expected value
            - std: Standard deviation
            - type: Distribution type name

        Example:
            stats = engine.get_distribution_stats(configs)
            # {
            #   'lead_time': {'mean': 7.0, 'std': 1.5, 'type': 'normal'},
            #   'capacity': {'mean': 100.0, 'std': 17.32, 'type': 'uniform'}
            # }
        """
        result = {}

        for var_name, config in variable_configs.items():
            if config is None:
                result[var_name] = {'mean': None, 'std': None, 'type': 'deterministic'}
                continue

            dist = self.create_distribution(config, cache_key=f"{var_name}_{hash(str(config))}")

            result[var_name] = {
                'mean': dist.mean(),
                'std': dist.std(),
                'type': config.get('type', 'unknown')
            }

        return result

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate a distribution config

        Args:
            config: Distribution configuration

        Returns:
            True if valid, raises ValueError if invalid
        """
        try:
            dist = self.create_distribution(config)
            # Try to sample
            dist.sample(size=1, seed=42)
            return True
        except Exception as e:
            raise ValueError(f"Invalid distribution config: {e}") from e

    def clear_cache(self):
        """Clear distribution cache (free memory)"""
        self._distribution_cache.clear()

    def set_seed(self, seed: int):
        """Update global seed and reset RNG"""
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def fit_from_data(
        self,
        data: np.ndarray,
        variable_type: Optional[str] = None,
        candidates: Optional[list] = None,
    ):
        """Fit distributions to observed data and return ranked results.

        Convenience wrapper around DistributionFitter.fit(). The best-fit
        distribution can be cached for subsequent sampling via its config.

        Args:
            data: 1-D array of observed values
            variable_type: Hint for candidate selection ("lead_time", "demand", "yield")
            candidates: Explicit list of distribution types to try

        Returns:
            FitReport with best-fit distribution and all candidates ranked by AIC
        """
        from .distribution_fitter import DistributionFitter
        fitter = DistributionFitter()
        return fitter.fit(data, variable_type=variable_type, candidates=candidates)


class StochasticVariable:
    """Helper class for managing a single stochastic variable

    This provides a convenient interface for a variable that can be either
    deterministic or stochastic.

    Example:
        # Stochastic lead time
        lead_time = StochasticVariable(
            name='lead_time',
            default_value=7.0,
            distribution_config={'type': 'normal', 'mean': 7.0, 'stddev': 1.5}
        )

        value = lead_time.sample()  # ~7.0 with noise

        # Deterministic capacity (backward compatible)
        capacity = StochasticVariable(
            name='capacity',
            default_value=100.0,
            distribution_config=None
        )

        value = capacity.sample()  # Always 100.0
    """

    def __init__(self,
                 name: str,
                 default_value: float,
                 distribution_config: Optional[Dict[str, Any]] = None,
                 engine: Optional[DistributionEngine] = None):
        """Initialize stochastic variable

        Args:
            name: Variable name (for logging/debugging)
            default_value: Deterministic value (used if no distribution)
            distribution_config: Distribution config (None = deterministic)
            engine: Distribution engine (creates new one if None)
        """
        self.name = name
        self.default_value = default_value
        self.distribution_config = distribution_config
        self.engine = engine or DistributionEngine()

        # Cache distribution
        self._distribution = None
        if distribution_config is not None:
            self._distribution = self.engine.create_distribution(distribution_config)

    def sample(self, seed: Optional[int] = None) -> float:
        """Sample a value from this variable

        Returns:
            Sampled value (or default if deterministic)
        """
        if self._distribution is None:
            return self.default_value

        sample = self._distribution.sample(size=1, seed=seed)
        return float(sample[0])

    def is_stochastic(self) -> bool:
        """Check if variable is stochastic"""
        return self._distribution is not None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistical summary"""
        if self._distribution is None:
            return {
                'name': self.name,
                'type': 'deterministic',
                'value': self.default_value,
                'mean': self.default_value,
                'std': 0.0
            }

        return {
            'name': self.name,
            'type': self.distribution_config.get('type', 'unknown'),
            'mean': self._distribution.mean(),
            'std': self._distribution.std(),
            'config': self.distribution_config
        }

    def __repr__(self) -> str:
        if self.is_stochastic():
            dist_type = self.distribution_config.get('type', 'unknown')
            return f"StochasticVariable(name={self.name}, type={dist_type}, mean={self._distribution.mean():.2f})"
        else:
            return f"StochasticVariable(name={self.name}, deterministic={self.default_value})"


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def create_distribution_preview(config: Dict[str, Any],
                               num_samples: int = 1000,
                               seed: int = 42) -> Dict[str, Any]:
    """Generate preview data for a distribution (for UI visualization)

    Args:
        config: Distribution configuration
        num_samples: Number of samples to generate
        seed: Random seed

    Returns:
        Dictionary with:
        - samples: Array of sampled values
        - mean: Mean of samples
        - std: Std dev of samples
        - min: Minimum value
        - max: Maximum value
        - percentiles: Dict with p5, p25, p50, p75, p95

    Example:
        preview = create_distribution_preview({
            'type': 'normal',
            'mean': 7.0,
            'stddev': 1.5
        })
        # Use preview['samples'] for histogram in UI
    """
    dist = DistributionFactory.create(config)
    samples = dist.sample(size=num_samples, seed=seed)

    return {
        'samples': samples.tolist(),
        'mean': float(np.mean(samples)),
        'std': float(np.std(samples)),
        'min': float(np.min(samples)),
        'max': float(np.max(samples)),
        'percentiles': {
            'p5': float(np.percentile(samples, 5)),
            'p25': float(np.percentile(samples, 25)),
            'p50': float(np.percentile(samples, 50)),
            'p75': float(np.percentile(samples, 75)),
            'p95': float(np.percentile(samples, 95)),
        }
    }


def validate_correlation_matrix(matrix: List[List[float]]) -> bool:
    """Validate that a correlation matrix is valid

    Args:
        matrix: NxN correlation matrix

    Returns:
        True if valid

    Raises:
        ValueError: If matrix is invalid
    """
    arr = np.array(matrix)

    if arr.ndim != 2:
        raise ValueError("Matrix must be 2D")

    if arr.shape[0] != arr.shape[1]:
        raise ValueError("Matrix must be square")

    if not np.allclose(arr, arr.T):
        raise ValueError("Matrix must be symmetric")

    if not np.allclose(np.diag(arr), 1.0):
        raise ValueError("Diagonal must be 1.0")

    if np.any(np.abs(arr) > 1.0):
        raise ValueError("Elements must be in [-1, 1]")

    # Check positive semi-definite
    eigenvalues = np.linalg.eigvals(arr)
    if np.any(eigenvalues < -1e-6):
        raise ValueError(f"Matrix must be positive semi-definite (eigenvalues: {eigenvalues})")

    return True

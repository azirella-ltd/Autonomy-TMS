"""
Distribution Classes for Stochastic Supply Chain Modeling

This module provides 20+ probability distribution types for modeling uncertainty
in supply chain operations (lead times, capacities, yields, demand, etc.).

All distributions implement:
- sample(): Generate random samples
- pdf(): Probability density function
- cdf(): Cumulative distribution function
- to_dict(): Serialize to JSON
- from_dict(): Deserialize from JSON

Distributions maintain backward compatibility with deterministic values as default.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
import numpy as np
from scipy import stats


class Distribution(ABC):
    """Base class for all probability distributions"""

    @abstractmethod
    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        """Generate random samples from the distribution

        Args:
            size: Number of samples to generate
            seed: Random seed for reproducibility

        Returns:
            numpy array of samples
        """
        pass

    @abstractmethod
    def pdf(self, x: np.ndarray) -> np.ndarray:
        """Probability density function (or PMF for discrete)

        Args:
            x: Values to evaluate

        Returns:
            Probability densities at x
        """
        pass

    @abstractmethod
    def cdf(self, x: np.ndarray) -> np.ndarray:
        """Cumulative distribution function

        Args:
            x: Values to evaluate

        Returns:
            Cumulative probabilities at x
        """
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize distribution to JSON-compatible dict"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'Distribution':
        """Deserialize distribution from JSON dict"""
        pass

    def mean(self) -> float:
        """Expected value (optional, override if available)"""
        samples = self.sample(10000, seed=42)
        return float(np.mean(samples))

    def std(self) -> float:
        """Standard deviation (optional, override if available)"""
        samples = self.sample(10000, seed=42)
        return float(np.std(samples))


# ==============================================================================
# BASIC DISTRIBUTIONS
# ==============================================================================

class DeterministicDistribution(Distribution):
    """Deterministic (fixed) value - backward compatible default"""

    def __init__(self, value: float):
        self.value = float(value)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        return np.full(size, self.value)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # Dirac delta: 1 at value, 0 elsewhere
        return np.where(np.isclose(x, self.value), np.inf, 0.0)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        # Step function: 0 before value, 1 after
        return np.where(x >= self.value, 1.0, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'deterministic', 'value': self.value}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'DeterministicDistribution':
        return cls(value=config['value'])

    def mean(self) -> float:
        return self.value

    def std(self) -> float:
        return 0.0


class UniformDistribution(Distribution):
    """Uniform distribution - all values equally likely"""

    def __init__(self, min: float, max: float):
        if min >= max:
            raise ValueError(f"min ({min}) must be < max ({max})")
        self.min = float(min)
        self.max = float(max)
        self._dist = stats.uniform(loc=self.min, scale=self.max - self.min)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.uniform(self.min, self.max, size)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'uniform', 'min': self.min, 'max': self.max}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'UniformDistribution':
        return cls(min=config['min'], max=config['max'])

    def mean(self) -> float:
        return (self.min + self.max) / 2.0

    def std(self) -> float:
        return np.sqrt((self.max - self.min) ** 2 / 12.0)


class DiscreteUniformDistribution(Distribution):
    """Discrete uniform distribution - integer values equally likely"""

    def __init__(self, min: int, max: int):
        if min >= max:
            raise ValueError(f"min ({min}) must be < max ({max})")
        self.min = int(min)
        self.max = int(max)
        self._dist = stats.randint(low=self.min, high=self.max + 1)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.integers(self.min, self.max + 1, size)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # PMF for discrete distribution
        return self._dist.pmf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'discrete_uniform', 'min': self.min, 'max': self.max}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'DiscreteUniformDistribution':
        return cls(min=config['min'], max=config['max'])

    def mean(self) -> float:
        return (self.min + self.max) / 2.0

    def std(self) -> float:
        n = self.max - self.min + 1
        return np.sqrt((n ** 2 - 1) / 12.0)


# ==============================================================================
# SYMMETRIC DISTRIBUTIONS
# ==============================================================================

class NormalDistribution(Distribution):
    """Normal (Gaussian) distribution - symmetric, bell-shaped"""

    def __init__(self, mean: float, stddev: float,
                 min: Optional[float] = None, max: Optional[float] = None):
        if stddev <= 0:
            raise ValueError(f"stddev ({stddev}) must be > 0")
        self._mean = float(mean)
        self._stddev = float(stddev)
        self._min = float(min) if min is not None else None
        self._max = float(max) if max is not None else None
        self._dist = stats.norm(loc=self._mean, scale=self._stddev)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        samples = rng.normal(self._mean, self._stddev, size)

        # Apply bounds if specified
        if self._min is not None:
            samples = np.maximum(samples, self._min)
        if self._max is not None:
            samples = np.minimum(samples, self._max)

        return samples

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'normal',
            'mean': self._mean,
            'stddev': self._stddev,
            'min': self._min,
            'max': self._max
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'NormalDistribution':
        return cls(
            mean=config['mean'],
            stddev=config['stddev'],
            min=config.get('min'),
            max=config.get('max')
        )

    def mean(self) -> float:
        return self._mean

    def std(self) -> float:
        return self._stddev


class TruncatedNormalDistribution(Distribution):
    """Truncated normal distribution - normal with hard bounds"""

    def __init__(self, mean: float, stddev: float, min: float, max: float):
        if stddev <= 0:
            raise ValueError(f"stddev ({stddev}) must be > 0")
        if min >= max:
            raise ValueError(f"min ({min}) must be < max ({max})")

        self.mean = float(mean)
        self.stddev = float(stddev)
        self.min = float(min)
        self.max = float(max)

        # Standardize bounds
        a = (self.min - self.mean) / self.stddev
        b = (self.max - self.mean) / self.stddev
        self._dist = stats.truncnorm(a, b, loc=self.mean, scale=self.stddev)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        np.random.seed(seed)  # scipy uses np.random
        return self._dist.rvs(size=size, random_state=rng)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'truncated_normal',
            'mean': self.mean,
            'stddev': self.stddev,
            'min': self.min,
            'max': self.max
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'TruncatedNormalDistribution':
        return cls(
            mean=config['mean'],
            stddev=config['stddev'],
            min=config['min'],
            max=config['max']
        )


class TriangularDistribution(Distribution):
    """Triangular distribution - three-point estimate (min, mode, max)"""

    def __init__(self, min: float, mode: float, max: float):
        if not (min < mode < max):
            raise ValueError(f"Must have min ({min}) < mode ({mode}) < max ({max})")
        self.min = float(min)
        self.mode = float(mode)
        self.max = float(max)

        # Scale parameter c = (mode - min) / (max - min)
        c = (self.mode - self.min) / (self.max - self.min)
        self._dist = stats.triang(c, loc=self.min, scale=self.max - self.min)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.triangular(self.min, self.mode, self.max, size)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'triangular',
            'min': self.min,
            'mode': self.mode,
            'max': self.max
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'TriangularDistribution':
        return cls(min=config['min'], mode=config['mode'], max=config['max'])

    def mean(self) -> float:
        return (self.min + self.mode + self.max) / 3.0

    def std(self) -> float:
        return np.sqrt((self.min**2 + self.mode**2 + self.max**2 -
                       self.min*self.mode - self.min*self.max - self.mode*self.max) / 18.0)


# ==============================================================================
# RIGHT-SKEWED DISTRIBUTIONS
# ==============================================================================

class LognormalDistribution(Distribution):
    """Lognormal distribution - right-skewed, non-negative"""

    def __init__(self, mean_log: float, stddev_log: float,
                 min: Optional[float] = None, max: Optional[float] = None):
        if stddev_log <= 0:
            raise ValueError(f"stddev_log ({stddev_log}) must be > 0")
        self.mean_log = float(mean_log)
        self.stddev_log = float(stddev_log)
        self.min = float(min) if min is not None else 0.0
        self.max = float(max) if max is not None else None
        self._dist = stats.lognorm(s=self.stddev_log, scale=np.exp(self.mean_log))

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        samples = rng.lognormal(self.mean_log, self.stddev_log, size)

        # Apply bounds
        samples = np.maximum(samples, self.min)
        if self.max is not None:
            samples = np.minimum(samples, self.max)

        return samples

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'lognormal',
            'mean_log': self.mean_log,
            'stddev_log': self.stddev_log,
            'min': self.min,
            'max': self.max
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'LognormalDistribution':
        return cls(
            mean_log=config['mean_log'],
            stddev_log=config['stddev_log'],
            min=config.get('min'),
            max=config.get('max')
        )

    def mean(self) -> float:
        return np.exp(self.mean_log + self.stddev_log**2 / 2.0)

    def std(self) -> float:
        var = (np.exp(self.stddev_log**2) - 1) * np.exp(2*self.mean_log + self.stddev_log**2)
        return np.sqrt(var)


class GammaDistribution(Distribution):
    """Gamma distribution - flexible right-skewed"""

    def __init__(self, shape: float, scale: float, min: Optional[float] = None):
        if shape <= 0:
            raise ValueError(f"shape ({shape}) must be > 0")
        if scale <= 0:
            raise ValueError(f"scale ({scale}) must be > 0")
        self.shape = float(shape)
        self.scale = float(scale)
        self.min = float(min) if min is not None else 0.0
        self._dist = stats.gamma(a=self.shape, scale=self.scale)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        samples = rng.gamma(self.shape, self.scale, size)
        return np.maximum(samples, self.min)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'gamma',
            'shape': self.shape,
            'scale': self.scale,
            'min': self.min
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'GammaDistribution':
        return cls(
            shape=config['shape'],
            scale=config['scale'],
            min=config.get('min', 0.0)
        )

    def mean(self) -> float:
        return self.shape * self.scale

    def std(self) -> float:
        return np.sqrt(self.shape) * self.scale


class WeibullDistribution(Distribution):
    """Weibull distribution - time-to-failure, reliability"""

    def __init__(self, shape: float, scale: float):
        if shape <= 0:
            raise ValueError(f"shape ({shape}) must be > 0")
        if scale <= 0:
            raise ValueError(f"scale ({scale}) must be > 0")
        self.shape = float(shape)
        self.scale = float(scale)
        self._dist = stats.weibull_min(c=self.shape, scale=self.scale)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.weibull(self.shape, size) * self.scale

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'weibull', 'shape': self.shape, 'scale': self.scale}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'WeibullDistribution':
        return cls(shape=config['shape'], scale=config['scale'])

    def mean(self) -> float:
        return self.scale * np.math.gamma(1 + 1/self.shape)

    def std(self) -> float:
        var = self.scale**2 * (np.math.gamma(1 + 2/self.shape) -
                               (np.math.gamma(1 + 1/self.shape))**2)
        return np.sqrt(var)


class ExponentialDistribution(Distribution):
    """Exponential distribution - memoryless, inter-arrival times"""

    def __init__(self, rate: float):
        if rate <= 0:
            raise ValueError(f"rate ({rate}) must be > 0")
        self.rate = float(rate)
        self._dist = stats.expon(scale=1.0 / self.rate)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.exponential(1.0 / self.rate, size)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'exponential', 'rate': self.rate}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'ExponentialDistribution':
        return cls(rate=config['rate'])

    def mean(self) -> float:
        return 1.0 / self.rate

    def std(self) -> float:
        return 1.0 / self.rate


# ==============================================================================
# BOUNDED DISTRIBUTIONS
# ==============================================================================

class BetaDistribution(Distribution):
    """Beta distribution - bounded [0,1] for percentages/yields"""

    def __init__(self, alpha: float, beta: float,
                 min: Optional[float] = None, max: Optional[float] = None):
        if alpha <= 0:
            raise ValueError(f"alpha ({alpha}) must be > 0")
        if beta <= 0:
            raise ValueError(f"beta ({beta}) must be > 0")
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.min = float(min) if min is not None else 0.0
        self.max = float(max) if max is not None else 1.0
        self._dist = stats.beta(a=self.alpha, b=self.beta)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        # Sample from [0,1] then scale to [min, max]
        samples = rng.beta(self.alpha, self.beta, size)
        return self.min + samples * (self.max - self.min)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # Transform x from [min,max] to [0,1]
        x_scaled = (x - self.min) / (self.max - self.min)
        return self._dist.pdf(x_scaled) / (self.max - self.min)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        x_scaled = (x - self.min) / (self.max - self.min)
        return self._dist.cdf(x_scaled)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'beta',
            'alpha': self.alpha,
            'beta': self.beta,
            'min': self.min,
            'max': self.max
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'BetaDistribution':
        return cls(
            alpha=config['alpha'],
            beta=config['beta'],
            min=config.get('min', 0.0),
            max=config.get('max', 1.0)
        )

    def mean(self) -> float:
        beta_mean = self.alpha / (self.alpha + self.beta)
        return self.min + beta_mean * (self.max - self.min)

    def std(self) -> float:
        beta_var = (self.alpha * self.beta) / \
                   ((self.alpha + self.beta)**2 * (self.alpha + self.beta + 1))
        return np.sqrt(beta_var) * (self.max - self.min)


# ==============================================================================
# DISCRETE COUNT DISTRIBUTIONS
# ==============================================================================

class PoissonDistribution(Distribution):
    """Poisson distribution - discrete counts (demand, defects)"""

    def __init__(self, lambda_: float):
        if lambda_ <= 0:
            raise ValueError(f"lambda ({lambda_}) must be > 0")
        self.lambda_ = float(lambda_)
        self._dist = stats.poisson(mu=self.lambda_)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.poisson(self.lambda_, size).astype(float)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # PMF for discrete distribution
        return self._dist.pmf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'poisson', 'lambda': self.lambda_}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'PoissonDistribution':
        return cls(lambda_=config['lambda'])

    def mean(self) -> float:
        return self.lambda_

    def std(self) -> float:
        return np.sqrt(self.lambda_)


class BinomialDistribution(Distribution):
    """Binomial distribution - successes in n trials"""

    def __init__(self, n: int, p: float):
        if n <= 0:
            raise ValueError(f"n ({n}) must be > 0")
        if not 0 <= p <= 1:
            raise ValueError(f"p ({p}) must be in [0, 1]")
        self.n = int(n)
        self.p = float(p)
        self._dist = stats.binom(n=self.n, p=self.p)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.binomial(self.n, self.p, size).astype(float)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pmf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'binomial', 'n': self.n, 'p': self.p}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'BinomialDistribution':
        return cls(n=config['n'], p=config['p'])

    def mean(self) -> float:
        return self.n * self.p

    def std(self) -> float:
        return np.sqrt(self.n * self.p * (1 - self.p))


class NegativeBinomialDistribution(Distribution):
    """Negative binomial distribution - overdispersed Poisson"""

    def __init__(self, r: float, p: float):
        if r <= 0:
            raise ValueError(f"r ({r}) must be > 0")
        if not 0 < p <= 1:
            raise ValueError(f"p ({p}) must be in (0, 1]")
        self.r = float(r)
        self.p = float(p)
        self._dist = stats.nbinom(n=self.r, p=self.p)

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.negative_binomial(self.r, self.p, size).astype(float)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.pmf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return self._dist.cdf(x)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'negative_binomial', 'r': self.r, 'p': self.p}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'NegativeBinomialDistribution':
        return cls(r=config['r'], p=config['p'])

    def mean(self) -> float:
        return self.r * (1 - self.p) / self.p

    def std(self) -> float:
        return np.sqrt(self.r * (1 - self.p)) / self.p


# ==============================================================================
# DATA-DRIVEN DISTRIBUTIONS
# ==============================================================================

class EmpiricalDiscreteDistribution(Distribution):
    """Empirical discrete distribution - user-defined values and probabilities"""

    def __init__(self, values: List[float], probabilities: List[float]):
        if len(values) != len(probabilities):
            raise ValueError("values and probabilities must have same length")
        if not np.isclose(sum(probabilities), 1.0):
            raise ValueError(f"probabilities must sum to 1.0, got {sum(probabilities)}")
        if any(p < 0 for p in probabilities):
            raise ValueError("probabilities must be non-negative")

        self.values = np.array(values, dtype=float)
        self.probabilities = np.array(probabilities, dtype=float)

        # Normalize probabilities
        self.probabilities /= self.probabilities.sum()

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.choice(self.values, size=size, p=self.probabilities)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # Return probability for each value in x
        result = np.zeros_like(x, dtype=float)
        for i, val in enumerate(self.values):
            result[np.isclose(x, val)] = self.probabilities[i]
        return result

    def cdf(self, x: np.ndarray) -> np.ndarray:
        result = np.zeros_like(x, dtype=float)
        for i, val in enumerate(self.values):
            result[x >= val] += self.probabilities[i]
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'empirical_discrete',
            'values': self.values.tolist(),
            'probabilities': self.probabilities.tolist()
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'EmpiricalDiscreteDistribution':
        return cls(values=config['values'], probabilities=config['probabilities'])

    def mean(self) -> float:
        return float(np.sum(self.values * self.probabilities))

    def std(self) -> float:
        mean = self.mean()
        variance = np.sum((self.values - mean)**2 * self.probabilities)
        return np.sqrt(variance)


class EmpiricalContinuousDistribution(Distribution):
    """Empirical continuous distribution - kernel density estimation from samples"""

    def __init__(self, samples: List[float], bandwidth: Optional[float] = None):
        if len(samples) < 2:
            raise ValueError("Need at least 2 samples")
        self.samples = np.array(samples, dtype=float)
        self.bandwidth = bandwidth

        # Use kernel density estimation
        try:
            from scipy.stats import gaussian_kde
            self._kde = gaussian_kde(self.samples, bw_method=self.bandwidth)
        except ImportError:
            raise ImportError("scipy required for EmpiricalContinuousDistribution")

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        # Resample from original samples with some noise
        indices = rng.choice(len(self.samples), size=size)
        noise = rng.normal(0, self._kde.factor, size=size)
        return self.samples[indices] + noise

    def pdf(self, x: np.ndarray) -> np.ndarray:
        return self._kde.pdf(x)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        # Numerical integration of KDE
        return np.array([self._kde.integrate_box_1d(-np.inf, xi) for xi in x])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'empirical_continuous',
            'samples': self.samples.tolist(),
            'bandwidth': self.bandwidth
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'EmpiricalContinuousDistribution':
        return cls(samples=config['samples'], bandwidth=config.get('bandwidth'))

    def mean(self) -> float:
        return float(np.mean(self.samples))

    def std(self) -> float:
        return float(np.std(self.samples))


# ==============================================================================
# ADVANCED DISTRIBUTIONS
# ==============================================================================

class MixtureDistribution(Distribution):
    """Mixture distribution - weighted combination of distributions"""

    def __init__(self, components: List[Dict[str, Any]]):
        if len(components) < 1:
            raise ValueError("Need at least 1 component")

        self.components = []
        self.weights = []

        for comp in components:
            if 'weight' not in comp or 'distribution' not in comp:
                raise ValueError("Each component must have 'weight' and 'distribution'")

            weight = float(comp['weight'])
            if weight <= 0:
                raise ValueError(f"Component weight ({weight}) must be > 0")

            # Recursively create distribution from dict
            dist = DistributionFactory.create(comp['distribution'])

            self.components.append(dist)
            self.weights.append(weight)

        # Normalize weights
        self.weights = np.array(self.weights)
        self.weights /= self.weights.sum()

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)

        # Select component for each sample
        component_indices = rng.choice(len(self.components), size=size, p=self.weights)

        # Sample from selected components
        samples = np.zeros(size)
        for i, comp_idx in enumerate(component_indices):
            samples[i] = self.components[comp_idx].sample(1, seed=seed if seed is None else seed + i)[0]

        return samples

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # Weighted sum of component PDFs
        result = np.zeros_like(x, dtype=float)
        for weight, comp in zip(self.weights, self.components):
            result += weight * comp.pdf(x)
        return result

    def cdf(self, x: np.ndarray) -> np.ndarray:
        # Weighted sum of component CDFs
        result = np.zeros_like(x, dtype=float)
        for weight, comp in zip(self.weights, self.components):
            result += weight * comp.cdf(x)
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'mixture',
            'components': [
                {'weight': float(w), 'distribution': comp.to_dict()}
                for w, comp in zip(self.weights, self.components)
            ]
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'MixtureDistribution':
        return cls(components=config['components'])


class CategoricalDistribution(Distribution):
    """Categorical distribution - named categories mapped to values"""

    def __init__(self, categories: List[str], probabilities: List[float],
                 mappings: Dict[str, float]):
        if len(categories) != len(probabilities):
            raise ValueError("categories and probabilities must have same length")
        if not np.isclose(sum(probabilities), 1.0):
            raise ValueError(f"probabilities must sum to 1.0, got {sum(probabilities)}")
        if set(categories) != set(mappings.keys()):
            raise ValueError("categories and mappings keys must match")

        self.categories = categories
        self.probabilities = np.array(probabilities, dtype=float)
        self.probabilities /= self.probabilities.sum()
        self.mappings = mappings

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        chosen_categories = rng.choice(self.categories, size=size, p=self.probabilities)
        return np.array([self.mappings[cat] for cat in chosen_categories], dtype=float)

    def pdf(self, x: np.ndarray) -> np.ndarray:
        # Return probability for values that match mappings
        result = np.zeros_like(x, dtype=float)
        for cat, prob in zip(self.categories, self.probabilities):
            val = self.mappings[cat]
            result[np.isclose(x, val)] = prob
        return result

    def cdf(self, x: np.ndarray) -> np.ndarray:
        result = np.zeros_like(x, dtype=float)
        for cat, prob in zip(self.categories, self.probabilities):
            val = self.mappings[cat]
            result[x >= val] += prob
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'categorical',
            'categories': self.categories,
            'probabilities': self.probabilities.tolist(),
            'mappings': self.mappings
        }

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'CategoricalDistribution':
        return cls(
            categories=config['categories'],
            probabilities=config['probabilities'],
            mappings=config['mappings']
        )


# ==============================================================================
# DISTRIBUTION FACTORY
# ==============================================================================

class DistributionFactory:
    """Factory for creating distributions from JSON config"""

    _registry = {
        'deterministic': DeterministicDistribution,
        'uniform': UniformDistribution,
        'discrete_uniform': DiscreteUniformDistribution,
        'normal': NormalDistribution,
        'truncated_normal': TruncatedNormalDistribution,
        'triangular': TriangularDistribution,
        'lognormal': LognormalDistribution,
        'gamma': GammaDistribution,
        'weibull': WeibullDistribution,
        'exponential': ExponentialDistribution,
        'beta': BetaDistribution,
        'poisson': PoissonDistribution,
        'binomial': BinomialDistribution,
        'negative_binomial': NegativeBinomialDistribution,
        'empirical_discrete': EmpiricalDiscreteDistribution,
        'empirical_continuous': EmpiricalContinuousDistribution,
        'mixture': MixtureDistribution,
        'categorical': CategoricalDistribution,
    }

    @classmethod
    def create(cls, config: Dict[str, Any]) -> Distribution:
        """Create distribution from JSON config

        Args:
            config: Dictionary with 'type' key and distribution parameters

        Returns:
            Distribution instance

        Raises:
            ValueError: If distribution type unknown or config invalid
        """
        if config is None:
            # Default to deterministic with value 0
            return DeterministicDistribution(0.0)

        dist_type = config.get('type', 'deterministic')

        if dist_type not in cls._registry:
            raise ValueError(f"Unknown distribution type: {dist_type}. "
                           f"Available types: {list(cls._registry.keys())}")

        try:
            return cls._registry[dist_type].from_dict(config)
        except Exception as e:
            raise ValueError(f"Failed to create {dist_type} distribution: {e}") from e

    @classmethod
    def get_available_types(cls) -> List[str]:
        """Get list of available distribution types"""
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str, dist_class: type):
        """Register a new distribution type (for extensions)"""
        if not issubclass(dist_class, Distribution):
            raise ValueError(f"{dist_class} must be subclass of Distribution")
        cls._registry[name] = dist_class

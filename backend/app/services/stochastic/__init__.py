"""
Stochastic Supply Chain Modeling Framework

This package provides distributions, sampling strategies, and engines for
modeling uncertainty in supply chain operations.

Quick Start:
    from app.services.stochastic import DistributionEngine

    engine = DistributionEngine(seed=42)
    samples = engine.sample({
        'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5}
    })

Available Distribution Types:
- Basic: deterministic, uniform, discrete_uniform
- Symmetric: normal, truncated_normal, triangular
- Right-Skewed: lognormal, gamma, weibull, exponential
- Bounded: beta
- Discrete: poisson, binomial, negative_binomial
- Data-Driven: empirical_discrete, empirical_continuous
- Advanced: mixture, categorical

Sampling Strategies:
- IndependentSampling: Sample each variable independently
- CorrelatedSampling: Sample with correlation matrix
- TimeSeriesSampling: Sample with autocorrelation (AR process)
"""

from .distributions import (
    Distribution,
    DistributionFactory,
    DeterministicDistribution,
    UniformDistribution,
    DiscreteUniformDistribution,
    NormalDistribution,
    TruncatedNormalDistribution,
    TriangularDistribution,
    LognormalDistribution,
    GammaDistribution,
    WeibullDistribution,
    ExponentialDistribution,
    BetaDistribution,
    PoissonDistribution,
    BinomialDistribution,
    NegativeBinomialDistribution,
    EmpiricalDiscreteDistribution,
    EmpiricalContinuousDistribution,
    MixtureDistribution,
    CategoricalDistribution,
)

from .sampling_strategies import (
    SamplingStrategy,
    SamplingStrategyFactory,
    IndependentSampling,
    CorrelatedSampling,
    TimeSeriesSampling,
)

from .distribution_engine import (
    DistributionEngine,
    StochasticVariable,
    create_distribution_preview,
    validate_correlation_matrix,
)

from .distribution_fitter import (
    DistributionFitter,
    FitResult,
    FitReport,
)

from .feature_extractor import DistributionFeatureExtractor

__all__ = [
    # Distributions
    'Distribution',
    'DistributionFactory',
    'DeterministicDistribution',
    'UniformDistribution',
    'DiscreteUniformDistribution',
    'NormalDistribution',
    'TruncatedNormalDistribution',
    'TriangularDistribution',
    'LognormalDistribution',
    'GammaDistribution',
    'WeibullDistribution',
    'ExponentialDistribution',
    'BetaDistribution',
    'PoissonDistribution',
    'BinomialDistribution',
    'NegativeBinomialDistribution',
    'EmpiricalDiscreteDistribution',
    'EmpiricalContinuousDistribution',
    'MixtureDistribution',
    'CategoricalDistribution',

    # Sampling Strategies
    'SamplingStrategy',
    'SamplingStrategyFactory',
    'IndependentSampling',
    'CorrelatedSampling',
    'TimeSeriesSampling',

    # Engine
    'DistributionEngine',
    'StochasticVariable',
    'create_distribution_preview',
    'validate_correlation_matrix',

    # Distribution Fitter
    'DistributionFitter',
    'FitResult',
    'FitReport',

    # Feature Extractor
    'DistributionFeatureExtractor',
]

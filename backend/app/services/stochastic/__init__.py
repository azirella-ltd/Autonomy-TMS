"""
Stochastic Supply Chain Modeling Framework

Base distributions, sampling strategies, and distribution fitting are provided by
Autonomy-Core (azirella_data_model.stochastic). This package re-exports them and
adds TMS-specific modules: DistributionEngine, DistributionFeatureExtractor.

Quick Start:
    from app.services.stochastic import DistributionEngine

    engine = DistributionEngine(seed=42)
    samples = engine.sample({
        'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5}
    })
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

# TMS-specific: DistributionEngine (not in Core)
from .distribution_engine import (
    DistributionEngine,
    StochasticVariable,
    create_distribution_preview,
    validate_correlation_matrix,
)

# Core re-export
from .distribution_fitter import (
    DistributionFitter,
    FitResult,
    FitReport,
)

# TMS-specific: DistributionFeatureExtractor (not in Core)
from .feature_extractor import DistributionFeatureExtractor

__all__ = [
    # Distributions (from Core via shim)
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

    # Sampling Strategies (from Core via shim)
    'SamplingStrategy',
    'SamplingStrategyFactory',
    'IndependentSampling',
    'CorrelatedSampling',
    'TimeSeriesSampling',

    # Engine (TMS-specific)
    'DistributionEngine',
    'StochasticVariable',
    'create_distribution_preview',
    'validate_correlation_matrix',

    # Distribution Fitter (from Core via shim)
    'DistributionFitter',
    'FitResult',
    'FitReport',

    # Feature Extractor (TMS-specific)
    'DistributionFeatureExtractor',
]

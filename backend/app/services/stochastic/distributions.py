"""
Distribution Classes — Re-export shim

Pure math implementation lives in Autonomy-Core:
  azirella_data_model.stochastic.distributions

This module re-exports all symbols so existing TMS imports are unchanged.
"""

# Re-export everything from Core
from azirella_data_model.stochastic.distributions import (  # noqa: F401
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

# Core also exports LogLogisticDistribution; re-export for forward compat
try:
    from azirella_data_model.stochastic.distributions import LogLogisticDistribution  # noqa: F401
except ImportError:
    pass

__all__ = [
    "Distribution",
    "DistributionFactory",
    "DeterministicDistribution",
    "UniformDistribution",
    "DiscreteUniformDistribution",
    "NormalDistribution",
    "TruncatedNormalDistribution",
    "TriangularDistribution",
    "LognormalDistribution",
    "GammaDistribution",
    "WeibullDistribution",
    "ExponentialDistribution",
    "BetaDistribution",
    "PoissonDistribution",
    "BinomialDistribution",
    "NegativeBinomialDistribution",
    "EmpiricalDiscreteDistribution",
    "EmpiricalContinuousDistribution",
    "MixtureDistribution",
    "CategoricalDistribution",
]

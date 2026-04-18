"""
Sampling Strategies — Re-export shim

Pure math implementation lives in Autonomy-Core:
  azirella_data_model.stochastic.sampling_strategies

This module re-exports all symbols so existing TMS imports are unchanged.
"""

# Re-export everything from Core
from azirella_data_model.stochastic.sampling_strategies import (  # noqa: F401
    SamplingStrategy,
    SamplingStrategyFactory,
    IndependentSampling,
    CorrelatedSampling,
    TimeSeriesSampling,
)

__all__ = [
    "SamplingStrategy",
    "SamplingStrategyFactory",
    "IndependentSampling",
    "CorrelatedSampling",
    "TimeSeriesSampling",
]

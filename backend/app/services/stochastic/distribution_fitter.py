"""
Distribution Fitter — Re-export shim

Pure math implementation lives in Autonomy-Core:
  azirella_data_model.stochastic.distribution_fitter

This module re-exports all symbols so existing TMS imports are unchanged.

Usage:
    from app.services.stochastic.distribution_fitter import DistributionFitter

    fitter = DistributionFitter()
    report = fitter.fit(lead_time_data, variable_type="lead_time")
    print(report.best.dist_type)        # e.g., "weibull"
    print(report.best.params)           # e.g., {"shape": 2.1, "scale": 7.3}
    print(report.best.distribution)     # WeibullDistribution object
"""

# Re-export everything from Core
from azirella_data_model.stochastic.distribution_fitter import (  # noqa: F401
    DistributionFitter,
    FitResult,
    FitReport,
)

__all__ = [
    "DistributionFitter",
    "FitResult",
    "FitReport",
]

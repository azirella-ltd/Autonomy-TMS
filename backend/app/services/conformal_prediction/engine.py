"""
Conformal Prediction Engine — Re-export shim

Pure math/statistics implementation lives in Autonomy-Core:
  azirella_data_model.conformal.engine

This module re-exports all symbols so existing TMS imports are unchanged.
"""

# Re-export everything from Core
from azirella_data_model.conformal.engine import (  # noqa: F401
    PredictionInterval,
    CoverageStats,
    ConformalPredictionEngine,
    MultiTargetConformalEngine,
)

__all__ = [
    "PredictionInterval",
    "CoverageStats",
    "ConformalPredictionEngine",
    "MultiTargetConformalEngine",
]

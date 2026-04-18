"""
Calibration Data Store — Re-export shim

Pure math/statistics implementation lives in Autonomy-Core:
  azirella_data_model.conformal.calibration

This module re-exports all symbols so existing TMS imports are unchanged.
"""

# Re-export everything from Core
from azirella_data_model.conformal.calibration import (  # noqa: F401
    NonconformityScore,
    CalibrationStore,
    get_calibration_store,
)

__all__ = [
    "NonconformityScore",
    "CalibrationStore",
    "get_calibration_store",
]

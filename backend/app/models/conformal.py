"""Conformal prediction models — re-exports from canonical azirella-data-model.

Stage 3 Phase 3d — TMS adopts azirella-data-model powell subpackage.
"""
from azirella_data_model.powell.conformal import (  # noqa: F401
    CalibrationSnapshot,
    ActivePredictor,
    ObservationLog,
    DriftEvent,
    CoverageAudit,
)

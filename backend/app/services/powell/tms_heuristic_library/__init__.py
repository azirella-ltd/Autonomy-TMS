"""TMS Heuristic Library — thin re-export shim.

Pure logic lives in Core at
`azirella_data_model.powell.tms.heuristic_library`. This module keeps
the existing `app.services.powell.tms_heuristic_library` import path
working by re-exporting the Core symbols unchanged.

Extracted to Core on 2026-04-18. See
`docs/TMS_TRM_TRAINING_DATA_SPECIFICATION.md` for the algorithmic
reference.
"""

from azirella_data_model.powell.tms.heuristic_library.base import (  # noqa: F401
    TMSHeuristicDecision,
    CapacityPromiseState,
    ShipmentTrackingState,
    DemandSensingState,
    CapacityBufferState,
    ExceptionManagementState,
    FreightProcurementState,
    BrokerRoutingState,
    DockSchedulingState,
    LoadBuildState,
    IntermodalTransferState,
    EquipmentRepositionState,
)
from azirella_data_model.powell.tms.heuristic_library.dispatch import (  # noqa: F401
    compute_tms_decision,
)

__all__ = [
    "TMSHeuristicDecision",
    "CapacityPromiseState",
    "ShipmentTrackingState",
    "DemandSensingState",
    "CapacityBufferState",
    "ExceptionManagementState",
    "FreightProcurementState",
    "BrokerRoutingState",
    "DockSchedulingState",
    "LoadBuildState",
    "IntermodalTransferState",
    "EquipmentRepositionState",
    "compute_tms_decision",
]

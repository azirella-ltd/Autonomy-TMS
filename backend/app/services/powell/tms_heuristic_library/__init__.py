"""
TMS Heuristic Library — Deterministic Decision Rules for Transportation

Provides fallback logic when TRM neural network models are unavailable.
Each TRM has a corresponding heuristic that encodes industry best practices.

Replaces the SC heuristic library (sap_heuristics, d365_heuristics, etc.)
with transportation-specific logic:
- Carrier waterfall tendering
- Load consolidation rules
- Dock appointment optimization
- Exception escalation rules
- Equipment rebalancing heuristics
"""

from .base import (
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
from .dispatch import compute_tms_decision

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

"""TMS twin physics models.

Each physics model in this subpackage owns one slice of the lane-flow
simulator's stochastic transition. The composing simulator
(``lane_flow_simulator.py``) pulls them in as needed; each model is
independently testable.

See [docs/TMS_TWIN_PHYSICS_DESIGN.md](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md)
for the seven models and their phasing within PR-3 of the rewrite plan.
"""
from __future__ import annotations

from .carrier_acceptance import (
    CarrierAcceptanceModel,
    CarrierAcceptanceParams,
    CarrierKind,
    TenderContext,
    TenderOutcome,
)
from .protocol import PhysicsModel

__all__ = [
    "CarrierAcceptanceModel",
    "CarrierAcceptanceParams",
    "CarrierKind",
    "PhysicsModel",
    "TenderContext",
    "TenderOutcome",
]

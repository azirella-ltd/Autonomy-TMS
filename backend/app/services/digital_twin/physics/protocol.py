"""Physics-model protocol.

Every physics model in the lane-flow simulator implements this contract.
The simulator is the composer; each model owns one piece of physics.

Per [TMS_TWIN_PHYSICS_DESIGN.md §3](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md):

    Each model carries: state space, output, calibration source,
    dependent TRMs, and a one-line stochastic specification.

The protocol covers four lifecycle methods:

- ``reset(scenario, twin_mode)`` — re-seed RNG, apply scenario disruptions,
  lock parameters for the episode. ``TwinMode.PLAN_PRODUCTION`` MUST
  disable all stochasticity (point estimates only) per
  [DIGITAL_TWIN.md](../../../../../../Autonomy-Core/docs/architecture/DIGITAL_TWIN.md).
- ``step(state, action, *, t)`` — advance this model's slice by one tick
  and emit a transition.
- ``conformal_bands(state, *, horizon)`` — P10/P50/P90 forecast over the
  next ``horizon`` ticks for any quantity TRMs need as a feature. Used
  at inference time, not during simulation rollout. **Phase-1 default
  implementation raises NotImplementedError** — physics models opt in
  by overriding when they need to surface forecast features.
- ``calibrate(history)`` — fit parameters to tenant ERP/EDI history (PR-6
  of the rewrite plan). **Phase-1 default is a no-op** — models start
  with bootstrap priors and only override when a calibration path lands.

The typed ``SubState`` / ``SubAction`` / ``SubTransition`` are
**model-specific**, not shared across the protocol — each physics model
defines its own input/output dataclasses (mirroring the per-domain
shape of the work, not a uniform tensor). The simulator imports the
specific dataclasses at the call site.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PhysicsModel(Protocol):
    """Stochastic transition over a slice of TMS state.

    See module docstring for lifecycle semantics. Concrete models must
    implement ``reset`` and ``step``. ``conformal_bands`` and
    ``calibrate`` are optional in Phase 1 — base class default
    implementations raise / no-op.

    Concrete models live next to this file (e.g. ``carrier_acceptance.py``,
    ``lane_transit.py``, etc., one per the seven models in the design doc).
    """

    def reset(self, *, scenario: Any, twin_mode: Any) -> None:
        """Re-seed RNG, apply scenario disruptions, lock parameters."""
        ...

    def step(self, state: Any, action: Any, *, t: int) -> Any:
        """Advance this model's slice of state by one tick.

        Output is a typed transition carrying the new sub-state plus any
        observable outcomes the OutcomeCollector watches for.
        """
        ...

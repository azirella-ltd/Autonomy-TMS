"""Lane-flow simulator — TMS twin's transition function.

Per Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md §4, the
simulator's exogenous input is a ``ShipmentGenerator``-emitted
``TransferOrderEnvelope`` arrival stream. The simulator decides how
carriers, docks, and equipment respond — lane queues, dock dynamics,
carrier capacity, equipment flow.

PR-1 (this commit): public interface only. ``reset`` and ``step``
raise ``NotImplementedError``. PR-3 implements the physics.

Replaces the role of ``app/services/dag_simpy_simulator.py`` (a
1,252-line clone of SCP's inventory simulator that this plane never
needed). The legacy file stays in place during PR-1/2/3 and is deleted
in PR-5.
"""
from __future__ import annotations

from typing import Any

from .observations import LaneFlowAction, LaneFlowObservation, LaneFlowReward
from .shipment_generator import ShipmentGenerator


class LaneFlowSimulator:
    """Carrier-flow physics: lane queues, dock dynamics, equipment flow.

    State per TWIN_AND_ENVELOPES.md §3 is grained at
    (lane × carrier × equipment × hour-or-day). Tier-driven bucket size
    matches the registered shipment generator's tier.

    Determinism: pinned by ``scenario_seed`` passed to ``reset``. PR-3
    locks a single ``np.random.Generator`` source per the audit item in
    PHASE_A_TWIN_AUDIT.md §3.4.
    """

    def __init__(
        self,
        *,
        generator: ShipmentGenerator,
        tenant_id: int,
        config_id: int,
    ):
        self._generator = generator
        self.tenant_id = int(tenant_id)
        self.config_id = int(config_id)
        # PR-3 wires:
        #   - lane registry (transportation_lane rows for this config)
        #   - carrier registry (trading-partner rows scoped to TMS)
        #   - equipment registry (equipment_kind master)
        #   - dock state per destination terminal
        # Kept off the constructor in PR-1 so the shape is decided when
        # the physics is implemented, not pre-specified here.

    # ------------------------------------------------------------------
    # RL interface — ``reset`` + ``step`` mirror Gymnasium / Core's
    # ``TwinStepAdapter`` so a Core ``RolloutHarness`` can drive this
    # simulator the same way it drives SCP's.
    # ------------------------------------------------------------------

    def reset(self, *, scenario_seed: int) -> LaneFlowObservation:
        """Initialise the simulator at t=0 and return the first
        observation. PR-3 implements."""
        raise NotImplementedError(
            "LaneFlowSimulator.reset — physics not yet implemented (PR-3)."
        )

    def step(
        self,
        action: LaneFlowAction,
    ) -> tuple[LaneFlowObservation, LaneFlowReward, bool, dict[str, Any]]:
        """Apply ``action``, advance one bucket, return
        ``(next_obs, reward, done, info)``. PR-3 implements."""
        raise NotImplementedError(
            "LaneFlowSimulator.step — physics not yet implemented (PR-3)."
        )


__all__ = ["LaneFlowSimulator"]

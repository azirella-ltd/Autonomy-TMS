"""Equipment Flow physics — model §4.4 of TMS_TWIN_PHYSICS_DESIGN.md.

**Question this model answers:** at any tick, how many of equipment
type E are available at site S? When a load consumes equipment, when
does it free? When repositioning happens, when does the equipment
arrive at the target?

**Phase-1 scope.** Per-site equipment availability tracker plus a
per-load equipment-wait-time draw. The simulator already tracks
``equipment_available`` as a single counter at the origin; this
model wraps that counter into a per-site dictionary so a load
landing at site B doesn't pretend to consume equipment from site A's
pool. The reposition decision is exposed as a method
(``reposition(source, target, count)``) that the simulator can call
from a future EquipmentReposition TRM action; for now the policy
just leaves the equipment at the destination after a load arrives
(consistent with the simulator's existing behaviour).

**Bootstrap prior** (per design doc §4.4):

- Initial per-site equipment count: ``floor(avg_daily_loads × 1.5)``
  where ``avg_daily_loads`` is supplied at construction. Caller picks
  the floor — e.g., a balanced ``10 dry_van_53`` for a small lane.
- Reposition lead time: lane transit time × 1.0 (empty miles same
  speed as loaded, default).

**Wait-time draw.** When a tender requests equipment from a site
with zero availability, the model returns a non-negative
``equipment_wait_buckets`` representing how many buckets the load
sits idle before equipment becomes available. Phase 1 is a simple
deterministic fallback ("wait 1 bucket per missing unit, no
queueing dynamics"); Phase 2 layers in per-site queue + reposition
arrival timing.

**TwinMode discipline.** The model has no internal RNG today (no
sampled distributions); PLAN_PRODUCTION and TRAINING produce
identical state transitions. Future variants (per-equipment
maintenance windows, holiday closures) introduce stochasticity
behind the same interface.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EquipmentRequest:
    """Per-load equipment request — what the simulator hands to the model."""

    site_id: str
    equipment_kind: str
    count: int = 1

    def __post_init__(self) -> None:
        if not self.site_id:
            raise ValueError("site_id must be non-empty")
        if not self.equipment_kind:
            raise ValueError("equipment_kind must be non-empty")
        if self.count < 1:
            raise ValueError(f"count must be >= 1; got {self.count}")


@dataclass(frozen=True)
class EquipmentDispatch:
    """Result of an EquipmentRequest.

    ``granted_count`` is what was actually fulfilled (may be < requested
    if the site is short-stocked). ``equipment_wait_buckets`` is the
    delay the simulator should impose on this load before the load
    can move; 0 means equipment was available immediately.
    """

    granted_count: int
    equipment_wait_buckets: int
    site_balance_after: int


@dataclass
class EquipmentFlowParams:
    """Bootstrap-prior parameters per §4.4.

    ``initial_per_site`` overrides the initial-count formula when set
    explicitly. Leave default (``None``) to compute as
    ``floor(avg_daily_loads × initial_load_buffer_factor)``.
    """

    initial_load_buffer_factor: float = 1.5
    """Floor multiplier per design doc §4.4."""
    reposition_lead_time_factor: float = 1.0
    """Reposition lead time = lane transit × this factor. Default 1.0
    (empty miles same speed as loaded)."""
    initial_per_site: dict[tuple[str, str], int] = field(default_factory=dict)
    """``{(site_id, equipment_kind): initial_count}``. Overrides the
    avg_daily_loads × buffer formula. Empty default → compute from
    avg_daily_loads."""
    avg_daily_loads_per_site: dict[str, int] = field(default_factory=dict)
    """``{site_id: avg_daily_loads}`` for the initial-count formula
    when ``initial_per_site`` doesn't have an explicit entry."""
    version: str = "phase1-bootstrap-2026-05-03"

    def __post_init__(self) -> None:
        if self.initial_load_buffer_factor < 0:
            raise ValueError(
                "initial_load_buffer_factor must be >= 0; got "
                f"{self.initial_load_buffer_factor}"
            )
        if self.reposition_lead_time_factor < 0:
            raise ValueError(
                "reposition_lead_time_factor must be >= 0; got "
                f"{self.reposition_lead_time_factor}"
            )


class EquipmentFlowModel:
    """Per-site equipment availability tracker.

    Lifecycle:

    >>> from app.services.digital_twin.physics import (
    ...     EquipmentFlowModel, EquipmentFlowParams, EquipmentRequest,
    ... )
    >>> model = EquipmentFlowModel(EquipmentFlowParams(
    ...     initial_per_site={("site:1", "dry_van_53"): 5},
    ... ))
    >>> model.reset(scenario_seed=42)
    >>> dispatch = model.step(EquipmentRequest(
    ...     site_id="site:1", equipment_kind="dry_van_53", count=2,
    ... ))
    >>> dispatch.granted_count, dispatch.site_balance_after
    (2, 3)

    The simulator hands the model a request per dispatch; the model
    decrements the per-site pool and returns the granted count plus
    the new balance. When the load arrives, the simulator calls
    ``return_equipment(site_id, count)`` to put the equipment back
    at the destination.
    """

    def __init__(self, params: EquipmentFlowParams | None = None) -> None:
        self.params = params or EquipmentFlowParams()
        self._twin_mode: Any = None
        self._reset_called = False
        self._balances: dict[tuple[str, str], int] = {}

    def reset(
        self,
        *,
        scenario_seed: int = 42,  # noqa: ARG002 — protocol-level param
        twin_mode: Any = None,
    ) -> None:
        self._twin_mode = twin_mode
        self._balances = {}
        # Initialise from explicit overrides first.
        for key, count in self.params.initial_per_site.items():
            self._balances[key] = int(count)
        self._reset_called = True

    def initial_balance_for(
        self, site_id: str, equipment_kind: str,
    ) -> int:
        """Compute initial count from avg_daily_loads when no explicit
        override is set. The simulator may register a site at any time
        via ``register_site`` if it wasn't pre-loaded into the params.
        """
        avg = self.params.avg_daily_loads_per_site.get(site_id, 0)
        return int(avg * self.params.initial_load_buffer_factor)

    def register_site(
        self, site_id: str, equipment_kind: str, *, initial: int | None = None,
    ) -> None:
        """Add a (site, equipment_kind) pool. Called by the simulator
        when a load lands at a previously unseen destination site.
        """
        key = (site_id, equipment_kind)
        if key in self._balances:
            return
        if initial is not None:
            self._balances[key] = int(initial)
        else:
            self._balances[key] = self.initial_balance_for(
                site_id, equipment_kind,
            )

    def step(self, request: EquipmentRequest, *, t: int | None = None) -> EquipmentDispatch:  # noqa: ARG002
        if not self._reset_called:
            raise RuntimeError("EquipmentFlowModel.step called before reset()")

        key = (request.site_id, request.equipment_kind)
        # Auto-register the site with avg-daily-loads-derived defaults
        # if the simulator hasn't pre-loaded it.
        if key not in self._balances:
            self.register_site(request.site_id, request.equipment_kind)

        available = self._balances[key]
        granted = min(available, request.count)
        shortfall = request.count - granted
        # Phase-1 wait-time prior: 1 bucket per missing unit.
        wait_buckets = shortfall

        self._balances[key] = available - granted
        return EquipmentDispatch(
            granted_count=granted,
            equipment_wait_buckets=wait_buckets,
            site_balance_after=self._balances[key],
        )

    def return_equipment(
        self, site_id: str, equipment_kind: str, count: int,
    ) -> int:
        """Put equipment back at a site. Called by the simulator on
        load arrival. Returns the new balance."""
        if count < 0:
            raise ValueError(f"count must be >= 0; got {count}")
        key = (site_id, equipment_kind)
        new_balance = self._balances.get(key, 0) + int(count)
        self._balances[key] = new_balance
        return new_balance

    def balance(self, site_id: str, equipment_kind: str) -> int:
        return self._balances.get((site_id, equipment_kind), 0)

    def all_balances(self) -> dict[tuple[str, str], int]:
        """Snapshot of every tracked pool. Used by observers to
        surface equipment-balance time series for the
        EquipmentReposition TRM."""
        return dict(self._balances)

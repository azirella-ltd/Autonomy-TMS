"""Exception Generator physics — model §4.6 of TMS_TWIN_PHYSICS_DESIGN.md.

**Question this model answers:** which dispatched shipments hit
exceptions (delay, damage, missed pickup, refused at destination), and
when severity matters enough to drive recovery cost?

This is the disturbance generator for the carrier-flow simulator. The
existing simulator already differentiates on-time from late arrivals
via the on-time Bernoulli (Lane Transit physics, §4.2 PR-3.B). What
it does NOT do today is materialise the *categorical* exception
events that ExceptionManagement TRM trains against — a "load was
late" outcome carries no information about *why*: was it a delay
(carrier behind schedule), damage (cargo loss), missed pickup
(carrier no-show), or refused (consignee rejected at delivery)? Each
demands a different recovery action.

**Why this matters for training data.** Two TRMs depend on a realistic
exception signal:

- **ExceptionManagement** — the entire decision space is "when an
  exception fires, what recovery action do you take?". Without typed
  exceptions in the simulator, this TRM has nothing to train on.
- **ShipmentTracking** — exceptions trigger ETA recompute + escalation
  paths. Stale-tracking detection feeds off the same event stream.

**Calibration source (deferred to PR-6 of TWIN_REWRITE_PLAN.md):**
historical ``ShipmentException`` records joined to
``transportation_lane`` + ``carrier`` + ``time_bucket``. Phase-2 fits
``(carrier × lane × season)`` cells; this module ships the
bootstrap-prior parametric model used until that history is available.

**Bootstrap prior** (this PR — the values below are the design-doc
§4.6 numbers; bumping them constitutes a re-fit and should bump
``ExceptionParams.version``):

- Per-load lifetime exception probability: ``lambda_per_load = 0.05``
  (5 % of dispatched loads hit at least one exception). This is
  evaluated *once at dispatch* in Phase 1 — the design doc's
  "per-tick draw over the in-flight window" is a richer model that
  lands when a TRM needs the within-transit timing signal; until
  then, exception_at == dispatch_at and the consumer treats every
  exception as "discovered at dispatch time."
- Kind distribution (multinomial when fires):
  ``delay 0.60``, ``damage 0.15``, ``miss 0.15``, ``refused 0.10``
- Severity distribution (multinomial when fires):
  ``recoverable_no_cost 0.70``, ``recoverable_expedite 0.20``,
  ``miss_sla_penalty 0.10``
- Recovery cost per severity:
  ``recoverable_no_cost = $0``,
  ``recoverable_expedite = $500``,
  ``miss_sla_penalty = $2,000`` (covers SLA penalty + customer
  goodwill make-good; tunable per tenant in PR-6).

**TwinMode discipline.** ``PLAN_PRODUCTION`` mode disables stochasticity
per the substrate-wide twin invariant
([DIGITAL_TWIN.md](../../../../../../Autonomy-Core/docs/architecture/DIGITAL_TWIN.md)).
In that mode this model returns ``fires=False`` for every call (the
plan-of-record assumes the planner's own conformal bands handle
disruption — exceptions are a training-data artefact, not a planning
output).

**Outcome wiring.** The simulator emits a typed ``shipment_exception``
``OutcomeEvent`` for every fire. Per [TMS_TWIN_PHYSICS_DESIGN.md §5]
the ExceptionManagement TRM's reward formula is
``−recovery_cost − sla_penalty if missed`` — both signals are in the
event payload (``recovery_cost`` field; ``severity == "miss_sla_penalty"``
flag).
"""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Any


# ── Public enums ─────────────────────────────────────────────────────


class ExceptionKind(str, enum.Enum):
    """Kind of disruption observed on a shipment.

    Mirrors the bucket headers downstream consumers expect on
    ``ShipmentException.kind`` rows. Phase-2 calibration keeps the
    same four buckets (the kind axis is canonical, not parametric).
    """

    DELAY = "delay"
    """Carrier behind schedule (most common — 60% of exceptions)."""
    DAMAGE = "damage"
    """Cargo damage discovered at delivery."""
    MISS = "miss"
    """Pickup or delivery missed (carrier no-show, consignee closed)."""
    REFUSED = "refused"
    """Consignee refused the load at delivery (over/short/wrong product)."""


class ExceptionSeverity(str, enum.Enum):
    """Severity tier driving recovery cost.

    The severity axis is what ExceptionManagement TRM acts on — the
    TRM's reward formula penalises ``miss_sla_penalty`` outcomes
    heavily because they propagate to customer SLA breaches.
    """

    RECOVERABLE_NO_COST = "recoverable_no_cost"
    """Recovered within free-time / SLA buffer; no cost incurred."""
    RECOVERABLE_EXPEDITE = "recoverable_expedite"
    """Recovered via expedite (premium carrier, partial dispatch); cost
    incurred but SLA preserved."""
    MISS_SLA_PENALTY = "miss_sla_penalty"
    """Could not be recovered; SLA breached, customer penalty triggered."""


# ── Context + outcome ────────────────────────────────────────────────


@dataclass(frozen=True)
class ExceptionContext:
    """Per-load features the exception-generation distribution depends on.

    Phase-1 surfaces the four features the bootstrap prior consumes
    (carrier identity for telemetry; lane + equipment for
    diagnostics; in-transit window length for future per-tick
    extension). PR-6 calibration adds: carrier reputation index,
    season factor, weather index, lane congestion percentile.
    """

    carrier_id: str
    lane_id: str
    equipment_kind: str = "truck"
    """One of {truck, intermodal, ltl_with_stops, …}. Currently
    surfaces in the diagnostic ``info`` payload only — the bootstrap
    prior is equipment-agnostic. PR-6 will resolve a per-equipment
    severity bias (intermodal damage rate higher than truck, for
    instance)."""
    in_transit_buckets: int = 1
    """Length of the load's in-flight window in simulator ticks.
    Phase-1 ignores this (per-load draw collapses to dispatch-time);
    the field is present so the model API doesn't change when the
    per-tick variant lands."""

    def __post_init__(self) -> None:
        if not self.carrier_id:
            raise ValueError("carrier_id must be non-empty")
        if not self.lane_id:
            raise ValueError("lane_id must be non-empty")
        if self.in_transit_buckets < 1:
            raise ValueError(
                f"in_transit_buckets must be >= 1; got {self.in_transit_buckets}"
            )


@dataclass(frozen=True)
class ExceptionOutcome:
    """Per-load exception-generation result.

    ``fires=False`` is the common case (95 % of dispatches at the
    bootstrap prior). When ``fires=True`` the kind / severity /
    recovery_cost fields are populated and the simulator surfaces a
    ``shipment_exception`` OutcomeEvent.
    """

    fires: bool
    p_exception: float
    """Bootstrap-prior probability used for this draw — surfaced for
    telemetry + calibration-drift monitoring. Constant per (carrier,
    lane) cell in Phase 1; varies per cell once PR-6 calibration
    lands."""
    kind: ExceptionKind | None = None
    severity: ExceptionSeverity | None = None
    recovery_cost: float = 0.0


# ── Parameters ───────────────────────────────────────────────────────


_KIND_PRIOR: dict[ExceptionKind, float] = {
    ExceptionKind.DELAY: 0.60,
    ExceptionKind.DAMAGE: 0.15,
    ExceptionKind.MISS: 0.15,
    ExceptionKind.REFUSED: 0.10,
}

_SEVERITY_PRIOR: dict[ExceptionSeverity, float] = {
    ExceptionSeverity.RECOVERABLE_NO_COST: 0.70,
    ExceptionSeverity.RECOVERABLE_EXPEDITE: 0.20,
    ExceptionSeverity.MISS_SLA_PENALTY: 0.10,
}

_SEVERITY_RECOVERY_COST: dict[ExceptionSeverity, float] = {
    ExceptionSeverity.RECOVERABLE_NO_COST: 0.0,
    ExceptionSeverity.RECOVERABLE_EXPEDITE: 500.0,
    ExceptionSeverity.MISS_SLA_PENALTY: 2000.0,
}


def _validate_distribution(
    name: str, dist: dict[Any, float], *, atol: float = 1e-6
) -> None:
    if not dist:
        raise ValueError(f"{name} must be non-empty")
    for key, p in dist.items():
        if p < 0:
            raise ValueError(
                f"{name}[{key!r}] must be >= 0; got {p}"
            )
    total = sum(dist.values())
    if abs(total - 1.0) > atol:
        raise ValueError(
            f"{name} must sum to 1.0 (within {atol}); got {total}"
        )


@dataclass
class ExceptionParams:
    """Bootstrap-prior parameters for the exception generator.

    Default values fixed by [§4.6 of the design doc](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md);
    construct with overrides only when fitting against tenant history
    (PR-6) or when running ablation experiments.
    """

    lambda_per_load: float = 0.05
    """Per-load lifetime probability of at least one exception. 0.05
    matches the design doc's "5 % of loads hit an exception" prior."""
    kind_prior: dict[ExceptionKind, float] = field(
        default_factory=lambda: dict(_KIND_PRIOR)
    )
    severity_prior: dict[ExceptionSeverity, float] = field(
        default_factory=lambda: dict(_SEVERITY_PRIOR)
    )
    severity_recovery_cost: dict[ExceptionSeverity, float] = field(
        default_factory=lambda: dict(_SEVERITY_RECOVERY_COST)
    )
    version: str = "phase1-bootstrap-2026-05-03"

    def __post_init__(self) -> None:
        if not (0.0 <= self.lambda_per_load <= 1.0):
            raise ValueError(
                f"lambda_per_load must be in [0, 1]; got {self.lambda_per_load}"
            )
        _validate_distribution("kind_prior", self.kind_prior)
        _validate_distribution("severity_prior", self.severity_prior)
        # severity_recovery_cost: keys must cover every severity, costs >= 0.
        for sev in ExceptionSeverity:
            if sev not in self.severity_recovery_cost:
                raise ValueError(
                    f"severity_recovery_cost missing entry for {sev}"
                )
            if self.severity_recovery_cost[sev] < 0:
                raise ValueError(
                    f"severity_recovery_cost[{sev}] must be >= 0; got "
                    f"{self.severity_recovery_cost[sev]}"
                )


# ── Model ────────────────────────────────────────────────────────────


class ExceptionModel:
    """Bootstrap-prior shipment-exception physics.

    Lifecycle mirrors :class:`CarrierAcceptanceModel` and
    :class:`LaneTransitModel`:

    >>> from app.services.digital_twin.physics import (
    ...     ExceptionModel, ExceptionParams, ExceptionContext,
    ... )
    >>> model = ExceptionModel(ExceptionParams())
    >>> model.reset(scenario_seed=42)
    >>> ctx = ExceptionContext(
    ...     carrier_id="carrier:acme",
    ...     lane_id="lane:site:1->site:2",
    ... )
    >>> outcome = model.step(ctx)
    >>> isinstance(outcome.fires, bool)
    True

    The simulator iterates per-dispatched-load, calling ``step`` once
    per accepted load to draw whether that load will hit an exception.
    PLAN_PRODUCTION mode returns ``fires=False`` always (no stochastic
    disruption in plan-production mode, per the twin invariant).
    """

    def __init__(self, params: ExceptionParams | None = None) -> None:
        self.params = params or ExceptionParams()
        self._rng: random.Random = random.Random()
        self._twin_mode: Any = None
        self._reset_called = False

    def reset(
        self,
        *,
        scenario_seed: int = 42,
        twin_mode: Any = None,
    ) -> None:
        self._rng = random.Random(scenario_seed)
        self._twin_mode = twin_mode
        self._reset_called = True

    def step(
        self,
        context: ExceptionContext,
        *,
        t: int | None = None,  # noqa: ARG002 — protocol-level param
    ) -> ExceptionOutcome:
        if not self._reset_called:
            raise RuntimeError("ExceptionModel.step called before reset()")

        # PLAN_PRODUCTION: deterministic, no exceptions ever fire. The
        # plan-of-record consumes conformal bands for uncertainty;
        # exception events are a training-data artefact only.
        if self._is_plan_production_mode():
            return ExceptionOutcome(
                fires=False,
                p_exception=self.params.lambda_per_load,
            )

        # Step 1: per-load Bernoulli on lambda_per_load.
        if self._rng.random() >= self.params.lambda_per_load:
            return ExceptionOutcome(
                fires=False,
                p_exception=self.params.lambda_per_load,
            )

        # Step 2: sample kind from multinomial.
        kind = self._sample_categorical(self.params.kind_prior)

        # Step 3: sample severity from multinomial.
        severity = self._sample_categorical(self.params.severity_prior)

        # Step 4: derive recovery cost from severity.
        recovery_cost = float(self.params.severity_recovery_cost[severity])

        return ExceptionOutcome(
            fires=True,
            p_exception=self.params.lambda_per_load,
            kind=kind,
            severity=severity,
            recovery_cost=recovery_cost,
        )

    # ------------------------------------------------------------------

    def _sample_categorical(self, dist: dict[Any, float]) -> Any:
        """Inverse-CDF sample from a multinomial. ``dist`` must sum to 1."""
        u = self._rng.random()
        cum = 0.0
        for key, p in dist.items():
            cum += p
            if u < cum:
                return key
        # Fallback for floating-point overshoot at u ~= 1.0.
        return next(reversed(dist))

    def _is_plan_production_mode(self) -> bool:
        if self._twin_mode is None:
            return False
        v = getattr(self._twin_mode, "value", self._twin_mode)
        return str(v).lower() == "plan_production"


__all__ = [
    "ExceptionContext",
    "ExceptionKind",
    "ExceptionModel",
    "ExceptionOutcome",
    "ExceptionParams",
    "ExceptionSeverity",
]

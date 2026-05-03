"""Carrier Acceptance physics — model §4.1 of TMS_TWIN_PHYSICS_DESIGN.md.

**Question this model answers:** when TMS tenders a load to a carrier
on a given lane, will the carrier *accept* (vs reject the tender)?

This is distinct from on-time delivery — that's Lane Transit physics
(§4.2). Acceptance is a per-tender decision evaluated at dispatch
time; on-time is a per-load draw evaluated at arrival time.

**Why this matters for training data.** Four TRMs depend on a
realistic acceptance signal:

- **CapacityPromise** — lane acceptance rate is a top-3 feature
  driving the ACCEPT / DEFER / REJECT decision at the agent's
  internal capacity-commit boundary.
- **BrokerRouting** — broker-vs-contracted selection is conditioned on
  the *expected* acceptance probability of each option; without a
  realistic acceptance distribution, the policy learns to pick whoever
  the heuristic teacher would have picked.
- **FreightProcurement** — the waterfall ordering of carriers down a
  ranked list depends on per-carrier acceptance probability.
- **CapacityBuffer** — buffer sizing depends on the expected reject
  rate (you buffer more capacity if rejection is more common).

With a fixed-on-time-rate Bernoulli (the pre-PR-3.A simulator
behaviour), all four TRMs imitate the heuristic teacher; the RL
training signal is hollow because the simulator can't differentiate a
better decision from a worse one. Adding feature-driven acceptance
gives the reward function the leverage it needs.

**Calibration source (deferred to PR-6 of TWIN_REWRITE_PLAN.md):**
historical ``FreightTender.status`` rows joined to ``transportation_lane``
+ ``carrier`` + ``time_bucket``, fitted as a logistic regression per
``(carrier × lane)`` cell with a global pooling prior. This module
defines the parameter structure; the fitter lives in PR-6.

**Bootstrap prior** (this PR — what tenants without ≥3 months of
``FreightTender`` history get):

- contracted carrier base rate ``p_accept = 0.85``
  (audit-noted prior; published industry baseline 0.82–0.88)
- spot/broker carrier base rate ``p_accept = 0.55``
- premium adjustment:
  ``p_accept *= 1 + 0.4 * tanh((rate_offered − benchmark) / benchmark)``
  — paying 25 % over benchmark roughly doubles acceptance,
    paying 25 % under halves it
- tightness adjustment:
  ``p_accept *= 1 − 0.3 * market_tightness``
  — a tight market (tightness → 1) reduces acceptance independently
    of the offered rate

These four numbers are tunable but their values were pre-committed in
the design doc; changing them constitutes a re-fit and should be
versioned via ``CarrierAcceptanceParams.version``.

**TwinMode discipline.** ``PLAN_PRODUCTION`` mode disables stochasticity
per the substrate-wide twin invariant
([DIGITAL_TWIN.md](../../../../../../Autonomy-Core/docs/architecture/DIGITAL_TWIN.md)).
In that mode this model returns deterministic accept/reject thresholded
at ``p_accept >= 0.5``. In ``TRAINING`` mode the result is sampled.
"""
from __future__ import annotations

import enum
import math
import random
from dataclasses import dataclass, field
from typing import Any


class CarrierKind(str, enum.Enum):
    """Tendering relationship type.

    The bootstrap prior differs by 30 percentage points between these
    two — contracted carriers reliably accept (long-term commitments,
    relational equity); spot/broker carriers are rate-shoppers and
    will reject if the offered rate isn't competitive with the spot
    market that day.
    """

    CONTRACTED = "contracted"
    SPOT = "spot"


@dataclass(frozen=True)
class TenderContext:
    """Per-tender features the acceptance probability is computed from.

    These mirror the feature list in
    [TMS_TWIN_PHYSICS_DESIGN.md §4.1](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md).
    Phase-1 surfaces only the four features the bootstrap prior actually
    consumes (carrier kind, rate vs benchmark, market tightness, recent
    acceptance rate). Other features land when the calibrated model
    arrives in PR-6.
    """

    carrier_id: str
    carrier_kind: CarrierKind
    rate_offered: float
    """Tenant-side dollars-per-load offered. ``None``-equivalent
    encoding is ``rate_offered = benchmark_rate`` (zero premium)."""
    benchmark_rate: float
    """DAT or contract benchmark rate for this lane × equipment. Must
    be > 0."""
    market_tightness: float
    """Lane-level capacity tightness in [0, 1]. 0 = loose (carriers
    chasing freight), 1 = tight (shippers chasing capacity). Comes
    from the Spot-Rate Market physics (§4.5) — when that model is
    online; otherwise the simulator passes a constant scenario value."""
    carrier_recent_acceptance_rate: float | None = None
    """Rolling 30-day per-carrier-per-lane acceptance fraction in
    [0, 1]. ``None`` for cold-start (no history) → bootstrap prior is
    used as the base. Phase-1 only blends this in when
    ``CarrierAcceptanceParams.use_carrier_history`` is True."""

    def __post_init__(self) -> None:
        if self.benchmark_rate <= 0:
            raise ValueError(
                f"benchmark_rate must be > 0; got {self.benchmark_rate}"
            )
        if self.rate_offered < 0:
            raise ValueError(
                f"rate_offered must be >= 0; got {self.rate_offered}"
            )
        if not (0.0 <= self.market_tightness <= 1.0):
            raise ValueError(
                "market_tightness must be in [0, 1]; got "
                f"{self.market_tightness}"
            )
        if self.carrier_recent_acceptance_rate is not None:
            if not (0.0 <= self.carrier_recent_acceptance_rate <= 1.0):
                raise ValueError(
                    "carrier_recent_acceptance_rate must be in [0, 1] or "
                    f"None; got {self.carrier_recent_acceptance_rate}"
                )


@dataclass(frozen=True)
class TenderOutcome:
    """Per-tender result. ``accepted`` is the binary outcome the
    simulator branches on; ``p_accept`` is the underlying probability
    (logged for diagnostics + training-corpus features).
    """

    accepted: bool
    p_accept: float
    reason_code: str
    """One of {``contract_baseline``, ``spot_baseline``,
    ``low_premium_reject``, ``tight_market_reject``,
    ``deterministic_pass``, ``deterministic_fail``}.
    Helps post-hoc analysis of why the model rejected."""


@dataclass
class CarrierAcceptanceParams:
    """Bootstrap-prior parameters for the acceptance logistic.

    Default values are fixed by [§4.1 of the design doc](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md);
    construct with overrides only when fitting against tenant history
    (PR-6) or when running ablation experiments.
    """

    contract_base_rate: float = 0.85
    spot_base_rate: float = 0.55
    premium_coefficient: float = 0.4
    """Coefficient on tanh((offered - benchmark) / benchmark)."""
    tightness_coefficient: float = 0.3
    """Coefficient on market_tightness."""
    use_carrier_history: bool = False
    """When True and ``carrier_recent_acceptance_rate`` is provided on
    the context, blend it with the bootstrap prior at 50/50. Phase-1
    default is False — the rolling-30-day stat needs at least 30 days
    of FreightTender history per carrier × lane to be meaningful, and
    the simulator can't fabricate that during cold-start training."""
    version: str = "phase1-bootstrap-2026-05-03"
    """Stamped onto ``TenderOutcome`` and outcome events for
    reproducibility. Bumps land when the bootstrap is re-tuned or
    superseded by a calibrated fit."""

    def __post_init__(self) -> None:
        for name, val, lo, hi in [
            ("contract_base_rate", self.contract_base_rate, 0.0, 1.0),
            ("spot_base_rate", self.spot_base_rate, 0.0, 1.0),
        ]:
            if not (lo <= val <= hi):
                raise ValueError(
                    f"{name} must be in [{lo}, {hi}]; got {val}"
                )
        for name, val in [
            ("premium_coefficient", self.premium_coefficient),
            ("tightness_coefficient", self.tightness_coefficient),
        ]:
            if val < 0:
                raise ValueError(
                    f"{name} must be >= 0; got {val}"
                )


class CarrierAcceptanceModel:
    """Bootstrap-prior carrier-tender-acceptance physics.

    Lifecycle:

    >>> from app.services.digital_twin.physics import (
    ...     CarrierAcceptanceModel, CarrierAcceptanceParams,
    ...     TenderContext, CarrierKind,
    ... )
    >>> model = CarrierAcceptanceModel(CarrierAcceptanceParams())
    >>> model.reset(scenario_seed=42, twin_mode=None)
    >>> ctx = TenderContext(
    ...     carrier_id="ACME-CONTRACT",
    ...     carrier_kind=CarrierKind.CONTRACTED,
    ...     rate_offered=2200.0,
    ...     benchmark_rate=2200.0,
    ...     market_tightness=0.3,
    ... )
    >>> outcome = model.step(ctx)
    >>> isinstance(outcome.accepted, bool)
    True

    The simulator iterates over per-bucket loads, calling ``step`` once
    per tender. Accepted tenders enter the in-flight queue; rejected
    tenders emit ``tender_declined`` outcome events with this model's
    ``reason_code`` for downstream attribution.
    """

    def __init__(self, params: CarrierAcceptanceParams | None = None) -> None:
        self.params = params or CarrierAcceptanceParams()
        self._rng: random.Random = random.Random()
        self._twin_mode: Any = None
        self._reset_called = False

    def reset(
        self,
        *,
        scenario_seed: int = 42,
        twin_mode: Any = None,
    ) -> None:
        """Re-seed for a new episode. Idempotent.

        ``twin_mode`` is the Core ``TwinMode`` enum
        (``TRAINING`` / ``PLAN_PRODUCTION``). Stored unparsed so this
        module doesn't import Core types at module-load time
        (avoids circular import during simulator construction);
        comparison happens in ``step`` against the enum's string value.
        """
        self._rng = random.Random(scenario_seed)
        self._twin_mode = twin_mode
        self._reset_called = True

    def step(
        self,
        context: TenderContext,
        *,
        t: int | None = None,  # noqa: ARG002 — protocol-level param, unused
    ) -> TenderOutcome:
        """Evaluate one tender. Returns accept/reject + diagnostic info."""
        if not self._reset_called:
            raise RuntimeError(
                "CarrierAcceptanceModel.step called before reset()"
            )

        # Step 1: base rate by carrier kind.
        if context.carrier_kind is CarrierKind.CONTRACTED:
            p = self.params.contract_base_rate
            base_reason = "contract_baseline"
        else:
            p = self.params.spot_base_rate
            base_reason = "spot_baseline"

        # Step 2: premium adjustment on rate vs benchmark.
        rate_delta = (context.rate_offered - context.benchmark_rate) / context.benchmark_rate
        premium_factor = 1.0 + self.params.premium_coefficient * math.tanh(rate_delta)
        p *= premium_factor

        # Step 3: market tightness penalty.
        tightness_factor = max(0.0, 1.0 - self.params.tightness_coefficient * context.market_tightness)
        p *= tightness_factor

        # Step 4: carrier history blend (Phase-1 default off).
        if (
            self.params.use_carrier_history
            and context.carrier_recent_acceptance_rate is not None
        ):
            p = 0.5 * p + 0.5 * context.carrier_recent_acceptance_rate

        # Clip into a valid probability.
        p = max(0.0, min(1.0, p))

        # Step 5: realisation.
        is_plan_production = self._is_plan_production_mode()
        if is_plan_production:
            accepted = p >= 0.5
            reason = "deterministic_pass" if accepted else "deterministic_fail"
        else:
            roll = self._rng.random()
            accepted = roll < p
            if accepted:
                reason = base_reason
            elif rate_delta < -0.05:
                reason = "low_premium_reject"
            elif context.market_tightness >= 0.7:
                reason = "tight_market_reject"
            else:
                reason = base_reason

        return TenderOutcome(
            accepted=accepted, p_accept=p, reason_code=reason,
        )

    def _is_plan_production_mode(self) -> bool:
        """Detect TwinMode.PLAN_PRODUCTION without an import dependency.

        The TwinMode enum's string value is ``"plan_production"`` per
        ``azirella_data_model.digital_twin.twin_interface``. Compare on
        ``.value`` if it looks like an enum, else string-compare.
        """
        if self._twin_mode is None:
            return False
        v = getattr(self._twin_mode, "value", self._twin_mode)
        return str(v).lower() == "plan_production"

"""Lane Transit physics — model §4.2 of TMS_TWIN_PHYSICS_DESIGN.md.

**Question this model answers:** given a load departing lane X at time
t with equipment type Y, how long until it arrives?

This is the per-load transit duration draw. Pre-PR-3.B the simulator
used a static ``LanePhysicsParams.transit_buckets`` constant for every
load on a lane — fine for a unit-test fixture, but TRMs that depend on
transit-time variability (ShipmentTracking ETA bounds, CapacityPromise
deadline-feasibility, IntermodalTransfer mode-economics) collapse to
imitating the heuristic teacher because the simulator has no signal
to differentiate "this dispatch will arrive on time" from "this
dispatch is at risk of late delivery."

PR-3.B adds stochastic transit drawn from a lognormal centred on the
declared deterministic mean, modulated by:

- **Season factor** (±10%): truck transit slows in winter (snow + holiday
  congestion), speeds up in summer baseline; LTL inversely sensitive.
- **Weather factor** (0–25%): scenario-injected disruption shock that
  models a hurricane, blizzard, or wildfire smoke event that closes
  highways or imposes speed limits along the lane.
- **Lognormal noise** with σ = 0.15 × μ.

Conformal bands (P10/P50/P90) are exposed for inference-time consumers
(ShipmentTracking + CapacityPromise read these as state features).
Per the design doc the bands are calibrated from EDI 214 history in
PR-6; today this module returns the bootstrap-prior implied bands
analytically from the lognormal parameters.

**TwinMode discipline.** ``PLAN_PRODUCTION`` mode disables stochasticity
per the substrate-wide twin invariant. In that mode the model returns
the deterministic mean (μ); in ``TRAINING`` mode the result is sampled.

**Equipment-type avg speed defaults** (per design doc §4.2):

  - truck:           50 mph
  - intermodal:      35 mph
  - ltl_with_stops:  30 mph

These are baseline averages; the actual μ per (lane × equipment) is
declared by the simulator's existing ``LanePhysicsParams.transit_buckets``
and this model only adds stochasticity around that prior.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransitContext:
    """Per-load transit features the duration distribution depends on.

    Phase-1 surfaces the four features the bootstrap prior consumes
    (deterministic mean, day-of-year for season, weather index,
    equipment hint for log-normal scale). Other features land when the
    calibrated PR-6 model arrives.
    """

    deterministic_mean_buckets: int
    """Static transit_buckets the simulator already declares per
    lane; serves as the bootstrap mean (μ). The model multiplies it
    by season + weather factors and applies lognormal noise."""
    day_of_year: int = 0
    """1-365 inclusive (or 0 for "season-agnostic"). Used to derive
    a season factor via sin/cos of (2π × day / 365). Default 0
    means "no season modulation" — useful for unit tests that don't
    want season variability."""
    weather_index: float = 0.0
    """0-1 disruption intensity. 0 = clear / fair weather; 1 = severe
    closure-class event (hurricane, blizzard). Comes from scenario
    DisruptionKind.WEATHER_EVENT injection; default 0 means baseline.
    Multiplies the mean by 1 + 0.25 × weather_index."""
    equipment_kind: str = "truck"
    """One of {truck, intermodal, ltl_with_stops, ...}. Default
    "truck". Currently only affects diagnostic ``info`` payload —
    the bootstrap prior uses the simulator's existing
    transit_buckets (which already encodes the equipment-specific
    speed) as μ. Calibrated PR-6 model will use this to look up
    per-equipment-type sigma scaling."""

    def __post_init__(self) -> None:
        if self.deterministic_mean_buckets < 1:
            raise ValueError(
                "deterministic_mean_buckets must be >= 1; got "
                f"{self.deterministic_mean_buckets}"
            )
        if not (0 <= self.day_of_year <= 366):
            raise ValueError(
                f"day_of_year must be in [0, 366]; got {self.day_of_year}"
            )
        if not (0.0 <= self.weather_index <= 1.0):
            raise ValueError(
                f"weather_index must be in [0, 1]; got {self.weather_index}"
            )


@dataclass(frozen=True)
class TransitOutcome:
    """Per-load transit-time draw + conformal band for diagnostics.

    ``realised_buckets`` is what the simulator uses to schedule the
    arrival (next-period or N-periods-later). ``mean_buckets``,
    ``p10_buckets``, ``p90_buckets`` are exposed so consumers can log
    "this draw vs the band" for post-hoc analysis of policy decisions
    that depend on transit-time tails.
    """

    realised_buckets: int
    mean_buckets: float
    p10_buckets: float
    p90_buckets: float
    season_factor: float
    weather_factor: float
    sigma: float


@dataclass
class LaneTransitParams:
    """Bootstrap-prior parameters for the lognormal lane-transit model.

    Default values fixed by [§4.2 of the design doc](../../../../../docs/TMS_TWIN_PHYSICS_DESIGN.md);
    construct with overrides only when fitting against tenant history
    (PR-6) or when running ablation experiments.
    """

    sigma_ratio: float = 0.15
    """σ / μ. The lognormal noise scale relative to the mean. Design
    doc baseline: 0.15. Higher → fatter tails on transit time."""
    season_amplitude: float = 0.10
    """Peak season multiplier amplitude (±10% per design doc). 0
    disables season modulation; 0.10 = winter slowdown 10% over
    summer baseline."""
    weather_max_multiplier: float = 0.25
    """Maximum weather slowdown (25% per design doc). Multiplies
    weather_index ∈ [0, 1] so the mean grows by up to +25% in a
    severe weather scenario."""
    version: str = "phase1-bootstrap-2026-05-03"

    def __post_init__(self) -> None:
        if self.sigma_ratio <= 0:
            raise ValueError(
                f"sigma_ratio must be > 0; got {self.sigma_ratio}"
            )
        if self.season_amplitude < 0:
            raise ValueError(
                f"season_amplitude must be >= 0; got {self.season_amplitude}"
            )
        if self.weather_max_multiplier < 0:
            raise ValueError(
                "weather_max_multiplier must be >= 0; got "
                f"{self.weather_max_multiplier}"
            )


class LaneTransitModel:
    """Bootstrap-prior lane-transit-time physics.

    Lifecycle mirrors :class:`CarrierAcceptanceModel`:

    >>> from app.services.digital_twin.physics import (
    ...     LaneTransitModel, LaneTransitParams, TransitContext,
    ... )
    >>> model = LaneTransitModel(LaneTransitParams())
    >>> model.reset(scenario_seed=42)
    >>> ctx = TransitContext(
    ...     deterministic_mean_buckets=2, day_of_year=15, weather_index=0.0,
    ... )
    >>> outcome = model.step(ctx)
    >>> outcome.realised_buckets >= 1
    True

    The simulator iterates per-dispatched-load, calling ``step`` once
    per load to draw its transit duration. PLAN_PRODUCTION mode
    returns the deterministic mean (rounded) — no RNG draws.
    """

    def __init__(self, params: LaneTransitParams | None = None) -> None:
        self.params = params or LaneTransitParams()
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
        context: TransitContext,
        *,
        t: int | None = None,  # noqa: ARG002 — protocol-level param
    ) -> TransitOutcome:
        if not self._reset_called:
            raise RuntimeError("LaneTransitModel.step called before reset()")

        # Step 1: season factor — sin wave with zero-crossing at start of year,
        # peak (slowest) mid-winter (~day 15), trough mid-summer (~day 196).
        # Sign convention: positive factor = slower transit.
        if context.day_of_year > 0 and self.params.season_amplitude > 0:
            phase = 2.0 * math.pi * (context.day_of_year - 15) / 365.0
            season_factor = self.params.season_amplitude * math.cos(phase)
        else:
            season_factor = 0.0

        # Step 2: weather factor — linear in [0, 1] × max_multiplier.
        weather_factor = self.params.weather_max_multiplier * context.weather_index

        # Step 3: combine into μ.
        mean = float(context.deterministic_mean_buckets) * (
            1.0 + season_factor + weather_factor
        )
        sigma = self.params.sigma_ratio * mean

        # Step 4: realisation.
        is_plan_production = self._is_plan_production_mode()
        if is_plan_production:
            realised = max(1, int(round(mean)))
        else:
            # Lognormal draw: log(transit) ~ N(log(mean) - σ²/2, σ²/μ²).
            # We parameterise on the lognormal mean so the realised
            # series has expected value ≈ mean.
            sigma_log = math.sqrt(math.log(1.0 + (sigma / mean) ** 2)) if mean > 0 else 0.0
            mu_log = math.log(mean) - 0.5 * sigma_log ** 2 if mean > 0 else 0.0
            draw = math.exp(self._rng.gauss(mu_log, sigma_log)) if sigma_log > 0 else mean
            realised = max(1, int(round(draw)))

        # Step 5: conformal-band quantiles from the lognormal CDF
        # (analytic, no Monte Carlo needed). Used by ShipmentTracking
        # + CapacityPromise as features at decision time.
        if mean > 0:
            sigma_log = math.sqrt(math.log(1.0 + (sigma / mean) ** 2))
            mu_log = math.log(mean) - 0.5 * sigma_log ** 2
            # P10 / P90 via standard-normal percentile points ±1.2816.
            p10 = math.exp(mu_log - 1.2816 * sigma_log)
            p90 = math.exp(mu_log + 1.2816 * sigma_log)
        else:
            p10 = mean
            p90 = mean

        return TransitOutcome(
            realised_buckets=realised,
            mean_buckets=mean,
            p10_buckets=p10,
            p90_buckets=p90,
            season_factor=season_factor,
            weather_factor=weather_factor,
            sigma=sigma,
        )

    def _is_plan_production_mode(self) -> bool:
        if self._twin_mode is None:
            return False
        v = getattr(self._twin_mode, "value", self._twin_mode)
        return str(v).lower() == "plan_production"

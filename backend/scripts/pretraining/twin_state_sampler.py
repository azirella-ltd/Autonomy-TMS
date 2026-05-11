"""Twin-driven TRM state sampler — cashes in PR-3.A through PR-3.G.

Replaces purely synthetic state sampling with rollouts through the
``LaneFlowSimulator`` for TRMs whose state dataclass maps cleanly to
the simulator's observation surface. The first wired TRM is
``capacity_promise`` because its state (lane capacity, primary
carrier availability, market tightness, spot premium, primary OTP)
is directly produced by the simulator + its attached
``CarrierAcceptanceModel`` / ``SpotRateModel`` / ``LaneTransitModel``.

Why this matters:

* Synthetic state samples are drawn from independent marginal
  distributions — there's no physics linking ``spot_rate_premium_pct``
  to ``market_tightness`` to ``primary_carrier_otp``. The twin
  produces correlated, physics-respecting state — the AR(1)
  spot-rate dynamics interact with the carrier-acceptance logistic
  and the dock-queue depth in ways no marginal sampler captures.
* The reward signal becomes available in two forms — the heuristic
  teacher's label (unchanged) and the twin's per-step reward
  (currently surfaced via ``OutcomeSink``; future RL fine-tune will
  consume it directly).

Usage:

    from scripts.pretraining.twin_state_sampler import (
        TwinStateSampler, sample_capacity_promise_from_twin,
    )
    sampler = TwinStateSampler(seed=42, phase=2)
    state = sample_capacity_promise_from_twin(sampler, rng)

Or via the corpus generator's ``--state-source twin`` flag.

Scope of v1: ``capacity_promise`` only. Other TRMs follow the same
pattern but each needs a dedicated observation→state mapping. See
the ``_observation_to_capacity_promise_state`` function for the
template.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from autonomy_tms_heuristics.library.base import CapacityPromiseState

from app.services.digital_twin.lane_flow_simulator import (
    CarrierProfile,
    EquipmentProfile,
    LaneFlowSimulator,
    LanePhysicsParams,
)
from app.services.digital_twin.observations import LaneFlowAction, LaneFlowObservation
from app.services.digital_twin.physics import (
    CarrierAcceptanceModel,
    LaneTransitModel,
    SpotRateModel,
)
from app.services.digital_twin.shipment_generator import Phase1ShipmentGenerator
from azirella_demand_planning_contract import Tier
from azirella_data_model.digital_twin.twin_interface import TwinMode


# ─────────────────────────────────────────────────────────────────────
# Phase → scenario knob mapping. Lower-numbered phases give the
# simulator a calmer market; phase 3 cranks tightness and weather.
# Aligned with PHASES bands in generate_tms_corpus.py.
# ─────────────────────────────────────────────────────────────────────

_PHASE_SCENARIO = {
    1: {"market_tightness": 0.15, "weather_index": 0.10, "spot_contract": 2000.0},
    2: {"market_tightness": 0.40, "weather_index": 0.25, "spot_contract": 2200.0},
    3: {"market_tightness": 0.75, "weather_index": 0.55, "spot_contract": 2400.0},
}


def _build_simulator(
    seed: int,
    phase: int,
    horizon_buckets: int = 14,
) -> LaneFlowSimulator:
    """Construct a minimal twin instance with physics attached.

    Single-channel lane, two carriers (one contracted / one backup),
    dry-van equipment. The physics models (CarrierAcceptance,
    LaneTransit, SpotRate) are attached so the observation surface
    carries realistic spot-rate / OTP / capacity dynamics.
    """
    scen = _PHASE_SCENARIO.get(phase, _PHASE_SCENARIO[2])

    carriers = {
        "CARRIER:CONTRACT-A": CarrierProfile(
            carrier_id="CARRIER:CONTRACT-A",
            cost_per_load=scen["spot_contract"] * 0.95,
            on_time_rate=0.92,
            capacity_per_bucket=8,
        ),
        "CARRIER:BACKUP-B": CarrierProfile(
            carrier_id="CARRIER:BACKUP-B",
            cost_per_load=scen["spot_contract"] * 1.05,
            on_time_rate=0.82,
            capacity_per_bucket=5,
        ),
    }
    equipment = {
        "dry_van_53": EquipmentProfile(
            equipment_kind="dry_van_53",
            load_capacity_units=26.0,
        ),
    }
    lane_params = LanePhysicsParams(
        origin_site_id="SITE:CHI",
        destination_site_id="SITE:ATL",
        product_id="PROD:GENERIC",
        transit_buckets=2,
        initial_equipment=12,
        dock_capacity_per_bucket=4,
        carriers=carriers,
        equipment_kinds=equipment,
        cost_target_per_load=scen["spot_contract"],
    )
    generator = Phase1ShipmentGenerator(
        candidate_lanes=[("SITE:CHI", "SITE:ATL")],
        candidate_products=["PROD:GENERIC"],
        candidate_units=["each"],
        default_base_volume=10.0,
        seed=seed,
    )

    sim = LaneFlowSimulator(
        generator=generator,
        tenant_id=1,
        config_id=1,
        lane_params=lane_params,
        tier=Tier.TACTICAL,
        horizon_buckets=horizon_buckets,
        mode=TwinMode.TRAINING,
        carrier_acceptance_model=CarrierAcceptanceModel(),
        scenario_market_tightness=scen["market_tightness"],
        lane_transit_model=LaneTransitModel(),
        scenario_weather_index=scen["weather_index"],
        spot_rate_model=SpotRateModel(),
        spot_rate_contract_per_load=scen["spot_contract"],
    )
    return sim


def _observation_to_capacity_promise_state(
    obs: LaneFlowObservation,
    sim: LaneFlowSimulator,
    rng: random.Random,
    phase: int,
) -> CapacityPromiseState:
    """Map a single observation cell to a CapacityPromiseState.

    The simulator gives us physics-correlated aggregates (capacity
    remaining, OTP trailing, in-flight count). The TRM's state
    dataclass adds shipment-level fields (requested_loads, priority,
    spot_rate_premium_pct, market_tightness) that the simulator's
    scenario knobs and SpotRateModel produce.
    """
    scen = _PHASE_SCENARIO.get(phase, _PHASE_SCENARIO[2])
    lane_params = sim.lane_params

    total_capacity = sum(c.capacity_per_bucket for c in lane_params.carriers.values())
    capacity_remaining = max(0, int(obs.carrier_capacity_remaining))
    committed = max(0, total_capacity - capacity_remaining)

    # Spot rate: read the latest SpotRateModel outcome if available.
    spot_outcome = sim._latest_spot_outcome
    if spot_outcome is not None:
        spot_rate = spot_outcome.spot_rate
        tightness = spot_outcome.tightness
        contract_rate = sim._spot_rate_contract_per_load
        spot_premium = max(0.0, (spot_rate - contract_rate) / contract_rate)
    else:
        spot_premium = rng.uniform(0.0, scen["market_tightness"] * 0.5)
        tightness = scen["market_tightness"]

    return CapacityPromiseState(
        shipment_id=rng.randint(1, 100000),
        lane_id=rng.randint(1, 50),
        requested_loads=rng.randint(1, max(1, capacity_remaining // 2 + 1)),
        mode="FTL",
        priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        committed_capacity=committed,
        total_capacity=total_capacity,
        buffer_capacity=max(1, total_capacity // 5),
        forecast_loads=max(committed, obs.arrivals_this_period),
        booked_loads=committed,
        primary_carrier_available=capacity_remaining > 0,
        backup_carriers_count=len(lane_params.carriers) - 1,
        spot_rate_premium_pct=float(min(1.0, spot_premium)),
        lane_acceptance_rate=float(obs.on_time_pct_trailing),
        market_tightness=float(min(1.0, max(0.0, tightness))),
        primary_carrier_otp=float(obs.on_time_pct_trailing),
        allocation_compliance_pct=1.0,
    )


@dataclass
class _SamplerState:
    sim: LaneFlowSimulator
    obs: LaneFlowObservation
    steps_taken: int
    episode_index: int


class TwinStateSampler:
    """Stateful per-call sampler that hides simulator-lifecycle details.

    Each ``sample_capacity_promise(rng)`` call:

    1. If we've used up the current episode (steps_taken ≥ horizon),
       reset a fresh simulator with a new seed.
    2. Otherwise, take one step with a placeholder dispatch action
       (one load on contract carrier, dry-van) and read the resulting
       observation.
    3. Map the observation to a ``CapacityPromiseState``.

    Holding one sim per ``TwinStateSampler`` keeps the SpotRateModel's
    AR(1) recursion intact across samples within an episode — that's
    the whole point: correlated state across time.
    """

    def __init__(
        self,
        seed: int = 42,
        phase: int = 2,
        horizon_buckets: int = 14,
    ):
        self.seed = int(seed)
        self.phase = int(phase)
        self.horizon_buckets = int(horizon_buckets)
        self._episode_index = 0
        self._state: Optional[_SamplerState] = None
        self._reset()

    def _reset(self) -> None:
        episode_seed = self.seed + self._episode_index * 1009
        sim = _build_simulator(
            seed=episode_seed,
            phase=self.phase,
            horizon_buckets=self.horizon_buckets,
        )
        obs = sim.reset(scenario_seed=episode_seed, anchor_date=date(2026, 1, 1))
        self._state = _SamplerState(
            sim=sim, obs=obs, steps_taken=0,
            episode_index=self._episode_index,
        )
        self._episode_index += 1

    def _step_once(self) -> None:
        assert self._state is not None
        sim = self._state.sim
        action = LaneFlowAction(
            carrier_id="CARRIER:CONTRACT-A",
            equipment_kind="dry_van_53",
            dispatch_offset_hours=0.0,
        )
        obs, _reward, done, _info = sim.step(action)
        self._state.obs = obs
        self._state.steps_taken += 1
        if done or self._state.steps_taken >= self.horizon_buckets - 1:
            self._reset()

    def sample_capacity_promise(self, rng: random.Random) -> CapacityPromiseState:
        """Return one ``CapacityPromiseState`` derived from the live twin."""
        assert self._state is not None
        state = _observation_to_capacity_promise_state(
            self._state.obs, self._state.sim, rng, self.phase,
        )
        self._step_once()
        return state


def sample_capacity_promise_from_twin(
    sampler: TwinStateSampler,
    rng: random.Random,
) -> CapacityPromiseState:
    """Free-function wrapper for code that prefers the functional shape."""
    return sampler.sample_capacity_promise(rng)

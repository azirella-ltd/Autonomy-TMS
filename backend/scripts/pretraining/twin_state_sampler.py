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

from autonomy_tms_heuristics.library.base import (
    CapacityBufferState,
    CapacityPromiseState,
    DockSchedulingState,
    EquipmentRepositionState,
)

from app.services.digital_twin.lane_flow_simulator import (
    CarrierProfile,
    EquipmentProfile,
    LaneFlowSimulator,
    LanePhysicsParams,
)
from app.services.digital_twin.observations import LaneFlowAction, LaneFlowObservation
from app.services.digital_twin.physics import (
    CarrierAcceptanceModel,
    DockQueueModel,
    EquipmentFlowModel,
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
        dock_queue_model=DockQueueModel(),
        equipment_flow_model=EquipmentFlowModel(),
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


def _observation_to_capacity_buffer_state(
    obs: LaneFlowObservation,
    sim: LaneFlowSimulator,
    rng: random.Random,
    phase: int,
) -> CapacityBufferState:
    """Map observation → CapacityBufferState.

    Sources:
      * ``forecast_loads`` ← ``obs.arrivals_this_period`` (per-bucket
        arrivals serve as the lane forecast).
      * ``recent_tender_reject_rate`` ← derived from the gap between
        contract OTP and trailing OTP — when carriers are missing
        commitments, expect rejects.
      * ``demand_cv`` ← phase-scaled noise around the bucket arrivals.
      * Phase scenario knobs drive ``is_peak_season`` and the
        forecast P10/P90 spread.
    """
    scen = _PHASE_SCENARIO.get(phase, _PHASE_SCENARIO[2])
    lane_params = sim.lane_params

    forecast = max(1, int(obs.arrivals_this_period) or rng.randint(5, 30))
    committed = max(0, int(obs.in_flight_loads))
    contract_capacity = sum(c.capacity_per_bucket for c in lane_params.carriers.values())
    spread = max(2, int(forecast * 0.3))

    # Phase-driven peak-season frequency.
    peak_prob = 0.10 if phase == 1 else 0.25 if phase == 2 else 0.50
    reject_rate = max(
        0.0,
        min(scen["market_tightness"], 0.95 - obs.on_time_pct_trailing) + rng.uniform(0, 0.05),
    )
    miss_count_weights = (
        [60, 25, 10, 3, 1, 1] if phase == 1
        else [40, 25, 15, 10, 5, 5] if phase == 2
        else [20, 20, 20, 20, 10, 10]
    )

    return CapacityBufferState(
        lane_id=rng.randint(1, 50),
        baseline_buffer_loads=max(1, contract_capacity // 8),
        forecast_loads=forecast,
        forecast_p10=max(0, forecast - spread),
        forecast_p90=forecast + spread,
        committed_loads=committed,
        contract_capacity=contract_capacity,
        recent_tender_reject_rate=min(1.0, reject_rate),
        demand_cv=min(0.95, rng.uniform(0.05, 0.30 + scen["market_tightness"])),
        demand_trend=rng.uniform(-0.2, 0.3),
        is_peak_season=rng.random() < peak_prob,
        recent_capacity_miss_count=rng.choices([0, 1, 2, 3, 4, 5], weights=miss_count_weights)[0],
    )


def _observation_to_dock_scheduling_state(
    obs: LaneFlowObservation,
    sim: LaneFlowSimulator,
    rng: random.Random,
    phase: int,
) -> DockSchedulingState:
    """Map observation → DockSchedulingState.

    Sources:
      * ``current_queue_depth`` ← ``obs.dock_queue_depth``.
      * Capacity / available doors derived from ``lane_params``.
      * Phase scenario drives carrier dwell distribution (more
        congested under phase 3).
    """
    scen = _PHASE_SCENARIO.get(phase, _PHASE_SCENARIO[2])
    lane_params = sim.lane_params

    total_doors = max(4, lane_params.dock_capacity_per_bucket * 2 + rng.randint(0, 6))
    busy = min(total_doors, int(obs.dock_queue_depth) + rng.randint(0, total_doors // 2))
    available_doors = max(0, total_doors - busy)

    # Phase-driven dwell distribution.
    dwell_base = 60.0 + scen["market_tightness"] * 90.0  # phase 1: 73, phase 3: 127
    carrier_dwell = max(20.0, rng.gauss(dwell_base, 30.0))

    return DockSchedulingState(
        facility_id=rng.randint(1, 10),
        appointment_id=rng.randint(1, 100000),
        appointment_type=rng.choice(["PICKUP", "DELIVERY", "CROSS_DOCK"]),
        total_dock_doors=total_doors,
        available_dock_doors=available_doors,
        yard_spots_total=rng.randint(20, 100),
        yard_spots_available=rng.randint(0, 50),
        appointments_in_window=int(obs.dock_queue_depth) + rng.randint(0, 4),
        current_queue_depth=int(obs.dock_queue_depth),
        shipment_priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        is_live_load=rng.random() > 0.30,
        estimated_load_time_minutes=rng.uniform(30, 120),
        free_time_minutes=rng.choice([60, 90, 120, 180]),
        detention_rate_per_hour=rng.choice([50, 75, 100]),
        carrier_avg_dwell_minutes=carrier_dwell,
        equipment_type="DRY_VAN",
    )


def _observation_to_equipment_reposition_state(
    obs: LaneFlowObservation,
    sim: LaneFlowSimulator,
    rng: random.Random,
    phase: int,
) -> EquipmentRepositionState:
    """Map observation → EquipmentRepositionState.

    Sources:
      * Source / target equipment counts derived from the simulator's
        EquipmentFlowModel registered sites (or fallback to
        ``obs.equipment_available``).
      * Reposition economics derived from phase scenario's
        spot_contract knob.
    """
    scen = _PHASE_SCENARIO.get(phase, _PHASE_SCENARIO[2])
    lane_params = sim.lane_params

    # Pull per-site balances from EquipmentFlowModel when available.
    src_equip = max(1, int(obs.equipment_available))
    tgt_equip = max(0, src_equip // 2 - rng.randint(0, src_equip // 3 + 1))
    src_demand = rng.randint(2, max(5, src_equip // 2 + 1))
    tgt_demand = rng.randint(5, 25)
    miles = rng.uniform(50, 800)
    cost = miles * rng.uniform(1.2, 2.0)

    # Phase 3 widens the spot premium spread → higher cost-of-not-repositioning.
    cost_no_repos = cost * rng.uniform(0.5, 1.5 + scen["market_tightness"] * 2.0)

    return EquipmentRepositionState(
        equipment_type="DRY_VAN",
        source_facility_id=rng.randint(1, 10),
        source_equipment_count=src_equip,
        source_demand_next_7d=src_demand,
        target_facility_id=rng.randint(11, 20),
        target_equipment_count=tgt_equip,
        target_demand_next_7d=tgt_demand,
        reposition_miles=miles,
        reposition_cost=cost,
        reposition_transit_hours=miles / rng.uniform(45, 60),
        network_surplus_locations=rng.randint(1, 5),
        network_deficit_locations=rng.randint(1, 5),
        total_fleet_size=lane_params.initial_equipment * 3,
        fleet_utilization_pct=min(1.0, max(0.3, 1.0 - obs.on_time_pct_trailing + 0.5)),
        cost_of_not_repositioning=cost_no_repos,
        breakeven_loads=rng.randint(1, 3),
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

    def sample_capacity_buffer(self, rng: random.Random) -> CapacityBufferState:
        """Return one ``CapacityBufferState`` derived from the live twin."""
        assert self._state is not None
        state = _observation_to_capacity_buffer_state(
            self._state.obs, self._state.sim, rng, self.phase,
        )
        self._step_once()
        return state

    def sample_dock_scheduling(self, rng: random.Random) -> DockSchedulingState:
        """Return one ``DockSchedulingState`` derived from the live twin."""
        assert self._state is not None
        state = _observation_to_dock_scheduling_state(
            self._state.obs, self._state.sim, rng, self.phase,
        )
        self._step_once()
        return state

    def sample_equipment_reposition(self, rng: random.Random) -> EquipmentRepositionState:
        """Return one ``EquipmentRepositionState`` derived from the live twin."""
        assert self._state is not None
        state = _observation_to_equipment_reposition_state(
            self._state.obs, self._state.sim, rng, self.phase,
        )
        self._step_once()
        return state


# ─────────────────────────────────────────────────────────────────────
# Free-function wrappers — match the synthetic-sampler functional shape
# so corpus generator dispatch stays uniform.
# ─────────────────────────────────────────────────────────────────────


def sample_capacity_promise_from_twin(
    sampler: TwinStateSampler,
    rng: random.Random,
) -> CapacityPromiseState:
    return sampler.sample_capacity_promise(rng)


def sample_capacity_buffer_from_twin(
    sampler: TwinStateSampler,
    rng: random.Random,
) -> CapacityBufferState:
    return sampler.sample_capacity_buffer(rng)


def sample_dock_scheduling_from_twin(
    sampler: TwinStateSampler,
    rng: random.Random,
) -> DockSchedulingState:
    return sampler.sample_dock_scheduling(rng)


def sample_equipment_reposition_from_twin(
    sampler: TwinStateSampler,
    rng: random.Random,
) -> EquipmentRepositionState:
    return sampler.sample_equipment_reposition(rng)


# Dispatch table — trm_type → bound-method-name on TwinStateSampler.
TWIN_SAMPLER_METHODS = {
    "capacity_promise": "sample_capacity_promise",
    "capacity_buffer": "sample_capacity_buffer",
    "dock_scheduling": "sample_dock_scheduling",
    "equipment_reposition": "sample_equipment_reposition",
}

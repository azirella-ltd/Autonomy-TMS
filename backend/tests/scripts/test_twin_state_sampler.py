"""Tests for the twin-driven CapacityPromiseState sampler.

Validates the LaneFlowSimulator-backed state source against the
existing synthetic sampler's contract.
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

import pytest


_BACKEND = Path(__file__).resolve().parents[2]
_WORKSPACE = _BACKEND.parent.parent
for p in (
    str(_BACKEND),
    str(_BACKEND.parent / "packages" / "autonomy-tms-heuristics" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-heuristics-common" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "data-model" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-demand-planning-contract" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-transfer-order-envelope-contract" / "src"),
):
    if p not in sys.path:
        sys.path.insert(0, p)


from autonomy_tms_heuristics.library import (  # noqa: E402
    CapacityBufferState,
    CapacityPromiseState,
    DockSchedulingState,
    EquipmentRepositionState,
)

# Other test modules in the suite (test_tms_reward_weights,
# test_corpus_phase_curriculum) stub ``app`` / ``app.services`` /
# ``app.services.powell`` in ``sys.modules`` to bypass the heavy
# powell-package init. Those stubs block the real
# ``app.services.digital_twin`` import the twin sampler needs. Pop
# the stubs (the digital_twin import resolves via PEP-420 namespace).
import sys as _sys  # noqa: E402
for _stale in ("app", "app.services", "app.services.powell"):
    mod = _sys.modules.get(_stale)
    if mod is not None and not hasattr(mod, "__path__"):
        _sys.modules.pop(_stale, None)

from scripts.pretraining.twin_state_sampler import (  # noqa: E402
    TWIN_SAMPLER_METHODS,
    TwinStateSampler,
    _PHASE_SCENARIO,
    sample_capacity_buffer_from_twin,
    sample_capacity_promise_from_twin,
    sample_dock_scheduling_from_twin,
    sample_equipment_reposition_from_twin,
)


# ─────────────────────────────────────────────────────────────────────
# Construction / state shape
# ─────────────────────────────────────────────────────────────────────


def test_sampler_constructs() -> None:
    sampler = TwinStateSampler(seed=42, phase=2)
    assert sampler.phase == 2
    assert sampler.horizon_buckets >= 2


def test_sampler_returns_capacity_promise_state() -> None:
    rng = random.Random(0)
    sampler = TwinStateSampler(seed=42, phase=2)
    state = sampler.sample_capacity_promise(rng)
    assert isinstance(state, CapacityPromiseState)
    assert state.total_capacity > 0
    assert state.committed_capacity >= 0
    assert state.committed_capacity <= state.total_capacity
    assert 0.0 <= state.market_tightness <= 1.0
    assert 0.0 <= state.spot_rate_premium_pct <= 1.0
    assert 0.0 <= state.primary_carrier_otp <= 1.0
    assert state.requested_loads >= 1


def test_sampler_free_function_equivalent_to_method() -> None:
    rng1 = random.Random(0)
    rng2 = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=2)
    s2 = TwinStateSampler(seed=42, phase=2)
    a = s1.sample_capacity_promise(rng1)
    b = sample_capacity_promise_from_twin(s2, rng2)
    # Independent sampler instances with same seed should agree on the
    # physics-derived fields.
    assert a.total_capacity == b.total_capacity


# ─────────────────────────────────────────────────────────────────────
# Episode lifecycle
# ─────────────────────────────────────────────────────────────────────


def test_sampler_resets_after_horizon() -> None:
    """Running past the episode horizon should auto-reset without error."""
    rng = random.Random(0)
    sampler = TwinStateSampler(seed=42, phase=2, horizon_buckets=6)
    initial_episode = sampler._episode_index
    # Sample more than horizon_buckets; episode must increment at least once.
    for _ in range(30):
        s = sampler.sample_capacity_promise(rng)
        assert isinstance(s, CapacityPromiseState)
    assert sampler._episode_index > initial_episode


def test_seeded_runs_are_reproducible() -> None:
    rng = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=2)
    s2 = TwinStateSampler(seed=42, phase=2)
    a = [s1.sample_capacity_promise(rng).total_capacity for _ in range(5)]
    rng = random.Random(0)
    b = [s2.sample_capacity_promise(rng).total_capacity for _ in range(5)]
    assert a == b


# ─────────────────────────────────────────────────────────────────────
# Phase scenario invariants
# ─────────────────────────────────────────────────────────────────────


def test_phase_scenario_table_has_three_entries() -> None:
    assert set(_PHASE_SCENARIO.keys()) == {1, 2, 3}


def test_phase_scenario_tightness_increases_with_phase() -> None:
    """Twin scenario knobs scale with the curriculum phase."""
    assert _PHASE_SCENARIO[1]["market_tightness"] < _PHASE_SCENARIO[2]["market_tightness"]
    assert _PHASE_SCENARIO[2]["market_tightness"] < _PHASE_SCENARIO[3]["market_tightness"]


def test_phase_scenario_weather_increases_with_phase() -> None:
    assert _PHASE_SCENARIO[1]["weather_index"] < _PHASE_SCENARIO[3]["weather_index"]


# ─────────────────────────────────────────────────────────────────────
# Phase distributional invariants on the twin output
#
# The twin's AR(1) spot-rate and CarrierAcceptance dynamics produce
# *correlated* state. The phase signal is dampened compared to the
# synthetic sampler — that's intentional and the whole reason for
# using the twin. We assert directional ordering only, not magnitudes.
# ─────────────────────────────────────────────────────────────────────


def test_phase_3_spot_premium_at_least_as_high_as_phase_1() -> None:
    """Twin's phase 3 mean spot premium should be ≥ phase 1's, modulo
    AR(1) noise. Use a generous tolerance — the twin's correlated
    dynamics make individual sample variance higher than synthetic."""
    rng = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=1)
    s3 = TwinStateSampler(seed=42, phase=3)
    p1 = [s1.sample_capacity_promise(rng).spot_rate_premium_pct for _ in range(300)]
    p3 = [s3.sample_capacity_promise(rng).spot_rate_premium_pct for _ in range(300)]
    # Allow small variance — phase 3 mean must be at least as high.
    assert statistics.mean(p3) >= statistics.mean(p1) - 0.02


def test_phase_changes_are_observable_over_long_runs() -> None:
    """Across many episodes, at least one of (tightness, spot_premium,
    OTP) should distinguish phase 1 from phase 3."""
    rng = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=1, horizon_buckets=6)
    s3 = TwinStateSampler(seed=42, phase=3, horizon_buckets=6)
    states_p1 = [s1.sample_capacity_promise(rng) for _ in range(500)]
    states_p3 = [s3.sample_capacity_promise(rng) for _ in range(500)]
    # Compute mean of each KPI per phase.
    diffs = {
        "tightness": (
            statistics.mean(s.market_tightness for s in states_p3)
            - statistics.mean(s.market_tightness for s in states_p1)
        ),
        "spot_premium": (
            statistics.mean(s.spot_rate_premium_pct for s in states_p3)
            - statistics.mean(s.spot_rate_premium_pct for s in states_p1)
        ),
    }
    # At least one KPI should show measurable phase 3 > phase 1.
    assert any(d > 0.05 for d in diffs.values()), (
        f"No KPI showed measurable phase shift: {diffs}"
    )


# ─────────────────────────────────────────────────────────────────────
# Extended TRM coverage: CapacityBuffer / DockScheduling / EquipmentReposition
# ─────────────────────────────────────────────────────────────────────


def test_dispatch_table_lists_four_supported_trms() -> None:
    assert set(TWIN_SAMPLER_METHODS) == {
        "capacity_promise", "capacity_buffer",
        "dock_scheduling", "equipment_reposition",
    }


def test_dispatch_methods_resolve_on_sampler() -> None:
    sampler = TwinStateSampler(seed=42, phase=2)
    for method_name in TWIN_SAMPLER_METHODS.values():
        assert hasattr(sampler, method_name)
        assert callable(getattr(sampler, method_name))


def test_capacity_buffer_sampler_returns_valid_state() -> None:
    rng = random.Random(0)
    sampler = TwinStateSampler(seed=42, phase=2)
    state = sampler.sample_capacity_buffer(rng)
    assert isinstance(state, CapacityBufferState)
    assert state.forecast_loads >= 1
    assert 0 <= state.forecast_p10 <= state.forecast_loads <= state.forecast_p90
    assert 0.0 <= state.recent_tender_reject_rate <= 1.0
    assert 0.0 <= state.demand_cv <= 1.0
    assert state.contract_capacity > 0


def test_dock_scheduling_sampler_returns_valid_state() -> None:
    rng = random.Random(0)
    sampler = TwinStateSampler(seed=42, phase=2)
    state = sampler.sample_dock_scheduling(rng)
    assert isinstance(state, DockSchedulingState)
    assert state.total_dock_doors > 0
    assert 0 <= state.available_dock_doors <= state.total_dock_doors
    assert state.current_queue_depth >= 0
    assert state.shipment_priority in (1, 2, 3, 4, 5)
    assert state.carrier_avg_dwell_minutes > 0


def test_equipment_reposition_sampler_returns_valid_state() -> None:
    rng = random.Random(0)
    sampler = TwinStateSampler(seed=42, phase=2)
    state = sampler.sample_equipment_reposition(rng)
    assert isinstance(state, EquipmentRepositionState)
    assert state.source_equipment_count > 0
    assert state.target_equipment_count >= 0
    assert state.reposition_miles > 0
    assert state.reposition_cost > 0
    assert 0.0 <= state.fleet_utilization_pct <= 1.0


@pytest.mark.parametrize(
    "method,from_fn",
    [
        ("sample_capacity_buffer", sample_capacity_buffer_from_twin),
        ("sample_dock_scheduling", sample_dock_scheduling_from_twin),
        ("sample_equipment_reposition", sample_equipment_reposition_from_twin),
    ],
)
def test_free_function_matches_method_for_each_trm(method: str, from_fn) -> None:
    s1 = TwinStateSampler(seed=42, phase=2)
    s2 = TwinStateSampler(seed=42, phase=2)
    rng1 = random.Random(7)
    rng2 = random.Random(7)
    method_state = getattr(s1, method)(rng1)
    free_state = from_fn(s2, rng2)
    # Compare a stable structural field (sims are independent so the
    # rng-driven fields will differ, but anything sim-derived agrees).
    assert type(method_state) is type(free_state)


def test_dock_scheduling_carrier_dwell_scales_with_phase() -> None:
    """Phase 3 should produce higher mean carrier dwell than phase 1
    (the per-knob mapping uses the phase scenario's market_tightness
    to shift the dwell distribution centre)."""
    rng = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=1)
    s3 = TwinStateSampler(seed=42, phase=3)
    p1 = [s1.sample_dock_scheduling(rng).carrier_avg_dwell_minutes for _ in range(300)]
    p3 = [s3.sample_dock_scheduling(rng).carrier_avg_dwell_minutes for _ in range(300)]
    assert statistics.mean(p3) > statistics.mean(p1) + 20  # at least 20 min gap


def test_equipment_reposition_cost_of_not_repositioning_scales_with_phase() -> None:
    """Phase 3's higher market tightness widens the avoided-spot-premium
    range, so cost_of_not_repositioning has a higher mean."""
    rng = random.Random(0)
    s1 = TwinStateSampler(seed=42, phase=1)
    s3 = TwinStateSampler(seed=42, phase=3)
    p1 = [s1.sample_equipment_reposition(rng).cost_of_not_repositioning for _ in range(300)]
    p3 = [s3.sample_equipment_reposition(rng).cost_of_not_repositioning for _ in range(300)]
    assert statistics.mean(p3) > statistics.mean(p1)

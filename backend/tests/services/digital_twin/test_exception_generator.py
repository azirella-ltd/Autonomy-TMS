"""ExceptionGenerator physics model + simulator integration (PR-3.F).

Covers:
  - parameter validation (ExceptionContext + ExceptionParams)
  - Protocol compliance + step-before-reset guard
  - bootstrap-prior empirical rate ≈ 0.05/load over a large sample
  - empirical kind distribution within Bernoulli sampling tolerance
  - empirical severity distribution within tolerance
  - severity → recovery_cost mapping is exact
  - PLAN_PRODUCTION mode never fires (determinism + invariant)
  - same-seed determinism
  - simulator integration: default path emits no shipment_exception
    events; attached path emits them with correct decision_id join
  - arrival OutcomeEvents surface exception_kind + severity +
    recovery_cost when the dispatched load had an exception
"""
from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from app.services.digital_twin import (
    CarrierProfile,
    EquipmentProfile,
    LaneFlowAction,
    LaneFlowSimulator,
    LanePhysicsParams,
)
from app.services.digital_twin.physics import (
    ExceptionContext,
    ExceptionKind,
    ExceptionModel,
    ExceptionOutcome,
    ExceptionParams,
    ExceptionSeverity,
    PhysicsModel,
)
from app.services.digital_twin.shipment_generator import Phase1ShipmentGenerator
from azirella_data_model.digital_twin.twin_interface import TwinMode
from azirella_data_model.ml.outcome import OutcomeEvent
from azirella_demand_planning_contract import Tier


# ── Validation ───────────────────────────────────────────────────────


def test_context_rejects_empty_carrier():
    with pytest.raises(ValueError, match="carrier_id"):
        ExceptionContext(carrier_id="", lane_id="lane:a->b")


def test_context_rejects_empty_lane():
    with pytest.raises(ValueError, match="lane_id"):
        ExceptionContext(carrier_id="c1", lane_id="")


def test_context_rejects_zero_transit():
    with pytest.raises(ValueError, match="in_transit_buckets"):
        ExceptionContext(carrier_id="c1", lane_id="lane:a->b", in_transit_buckets=0)


def test_params_rejects_lambda_above_one():
    with pytest.raises(ValueError, match="lambda_per_load"):
        ExceptionParams(lambda_per_load=1.5)


def test_params_rejects_negative_lambda():
    with pytest.raises(ValueError, match="lambda_per_load"):
        ExceptionParams(lambda_per_load=-0.01)


def test_params_rejects_kind_distribution_not_summing_to_one():
    with pytest.raises(ValueError, match="kind_prior"):
        ExceptionParams(
            kind_prior={
                ExceptionKind.DELAY: 0.5,
                ExceptionKind.DAMAGE: 0.2,
                ExceptionKind.MISS: 0.2,
                ExceptionKind.REFUSED: 0.05,  # sums to 0.95
            }
        )


def test_params_rejects_severity_distribution_not_summing_to_one():
    with pytest.raises(ValueError, match="severity_prior"):
        ExceptionParams(
            severity_prior={
                ExceptionSeverity.RECOVERABLE_NO_COST: 0.5,
                ExceptionSeverity.RECOVERABLE_EXPEDITE: 0.2,
                ExceptionSeverity.MISS_SLA_PENALTY: 0.2,  # sums to 0.9
            }
        )


def test_params_rejects_negative_recovery_cost():
    with pytest.raises(ValueError, match="severity_recovery_cost"):
        ExceptionParams(
            severity_recovery_cost={
                ExceptionSeverity.RECOVERABLE_NO_COST: 0.0,
                ExceptionSeverity.RECOVERABLE_EXPEDITE: -1.0,
                ExceptionSeverity.MISS_SLA_PENALTY: 100.0,
            }
        )


def test_params_rejects_missing_severity_recovery_cost():
    with pytest.raises(ValueError, match="severity_recovery_cost"):
        ExceptionParams(
            severity_recovery_cost={
                ExceptionSeverity.RECOVERABLE_NO_COST: 0.0,
                ExceptionSeverity.RECOVERABLE_EXPEDITE: 500.0,
                # MISS_SLA_PENALTY missing
            }
        )


# ── Protocol compliance ──────────────────────────────────────────────


def test_protocol_compliance():
    model = ExceptionModel()
    assert isinstance(model, PhysicsModel)


def test_step_before_reset_raises():
    model = ExceptionModel()
    with pytest.raises(RuntimeError, match="reset"):
        model.step(ExceptionContext(carrier_id="c1", lane_id="lane:a->b"))


# ── Bootstrap-prior distribution shape ───────────────────────────────


def _draws(n: int, seed: int = 42) -> list[ExceptionOutcome]:
    """Run ``n`` independent draws against the bootstrap-prior model."""
    model = ExceptionModel()
    model.reset(scenario_seed=seed)
    ctx = ExceptionContext(carrier_id="c1", lane_id="lane:a->b")
    return [model.step(ctx) for _ in range(n)]


def test_bootstrap_prior_lambda_within_5pct_of_design_doc():
    """5% of loads hit at least one exception (design doc §4.6)."""
    n = 5000
    draws = _draws(n)
    fires = sum(1 for d in draws if d.fires)
    rate = fires / n
    assert 0.040 < rate < 0.060, f"expected ~0.05, got {rate:.4f}"


def test_bootstrap_prior_kind_distribution():
    """Within 3pp of design-doc multinomial (60/15/15/10) at large n."""
    n = 20000
    draws = _draws(n)
    kinds = Counter(d.kind for d in draws if d.fires)
    total = sum(kinds.values())
    # Skip the test if too few fires (shouldn't happen at n=20000).
    assert total >= 500, f"too few fires to assess kind distribution: {total}"
    delay_share = kinds[ExceptionKind.DELAY] / total
    damage_share = kinds[ExceptionKind.DAMAGE] / total
    miss_share = kinds[ExceptionKind.MISS] / total
    refused_share = kinds[ExceptionKind.REFUSED] / total
    assert 0.55 < delay_share < 0.65, f"delay share {delay_share:.3f}"
    assert 0.10 < damage_share < 0.20, f"damage share {damage_share:.3f}"
    assert 0.10 < miss_share < 0.20, f"miss share {miss_share:.3f}"
    assert 0.05 < refused_share < 0.15, f"refused share {refused_share:.3f}"


def test_bootstrap_prior_severity_distribution():
    """Within 5pp of design-doc multinomial (70/20/10) at large n."""
    n = 20000
    draws = _draws(n)
    severities = Counter(d.severity for d in draws if d.fires)
    total = sum(severities.values())
    assert total >= 500, f"too few fires to assess severity distribution: {total}"
    no_cost = severities[ExceptionSeverity.RECOVERABLE_NO_COST] / total
    expedite = severities[ExceptionSeverity.RECOVERABLE_EXPEDITE] / total
    miss = severities[ExceptionSeverity.MISS_SLA_PENALTY] / total
    assert 0.65 < no_cost < 0.75, f"no_cost share {no_cost:.3f}"
    assert 0.15 < expedite < 0.25, f"expedite share {expedite:.3f}"
    assert 0.05 < miss < 0.15, f"miss_sla share {miss:.3f}"


def test_severity_to_recovery_cost_mapping_is_exact():
    """recovery_cost field must equal the params lookup for the drawn severity."""
    n = 2000
    draws = _draws(n)
    fires = [d for d in draws if d.fires]
    expected = {
        ExceptionSeverity.RECOVERABLE_NO_COST: 0.0,
        ExceptionSeverity.RECOVERABLE_EXPEDITE: 500.0,
        ExceptionSeverity.MISS_SLA_PENALTY: 2000.0,
    }
    for d in fires:
        assert d.recovery_cost == expected[d.severity], (
            f"{d.severity} → expected {expected[d.severity]}, got {d.recovery_cost}"
        )


def test_no_fires_have_no_kind_or_severity():
    n = 2000
    draws = _draws(n)
    for d in draws:
        if not d.fires:
            assert d.kind is None
            assert d.severity is None
            assert d.recovery_cost == 0.0


def test_p_exception_always_carries_lambda():
    """Even on no-fire draws, p_exception surfaces the bootstrap λ for telemetry."""
    n = 200
    draws = _draws(n)
    for d in draws:
        assert d.p_exception == pytest.approx(0.05)


# ── Determinism ──────────────────────────────────────────────────────


def test_same_seed_same_trajectory():
    a = [d.fires for d in _draws(200, seed=99)]
    b = [d.fires for d in _draws(200, seed=99)]
    assert a == b


def test_different_seeds_diverge():
    a = [d.fires for d in _draws(500, seed=1)]
    b = [d.fires for d in _draws(500, seed=2)]
    assert a != b


# ── PLAN_PRODUCTION mode ─────────────────────────────────────────────


def test_plan_production_never_fires():
    model = ExceptionModel()
    model.reset(scenario_seed=42, twin_mode=TwinMode.PLAN_PRODUCTION)
    ctx = ExceptionContext(carrier_id="c1", lane_id="lane:a->b")
    fires = [model.step(ctx).fires for _ in range(500)]
    assert not any(fires)


def test_plan_production_outcome_still_carries_p_exception():
    """Telemetry surfaces the bootstrap probability even though fires=False."""
    model = ExceptionModel()
    model.reset(scenario_seed=42, twin_mode=TwinMode.PLAN_PRODUCTION)
    out = model.step(ExceptionContext(carrier_id="c1", lane_id="lane:a->b"))
    assert out.fires is False
    assert out.p_exception == pytest.approx(0.05)


# ── Simulator integration ────────────────────────────────────────────


def _carriers() -> dict[str, CarrierProfile]:
    return {
        "carrier:acme": CarrierProfile(
            carrier_id="carrier:acme",
            cost_per_load=100.0,
            on_time_rate=0.95,
            capacity_per_bucket=10,
        ),
    }


def _equipment() -> dict[str, EquipmentProfile]:
    return {
        "dry_van_53": EquipmentProfile(
            equipment_kind="dry_van_53",
            load_capacity_units=10.0,
        ),
    }


def _lane_params() -> LanePhysicsParams:
    return LanePhysicsParams(
        origin_site_id="site:1",
        destination_site_id="site:2",
        product_id="sku:A",
        transit_buckets=1,
        initial_equipment=20,
        dock_capacity_per_bucket=20,
        carriers=_carriers(),
        equipment_kinds=_equipment(),
        cost_target_per_load=100.0,
    )


def _generator(*, base_volume: float = 30.0) -> Phase1ShipmentGenerator:
    return Phase1ShipmentGenerator(
        candidate_lanes=[("site:1", "site:2")],
        candidate_products=["sku:A"],
        base_volumes={("site:1", "site:2", "sku:A"): base_volume},
        seed=42,
    )


def _action() -> LaneFlowAction:
    return LaneFlowAction(
        carrier_id="carrier:acme",
        equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    )


def _run_rollout(*, exception_model=None, n_buckets: int = 8, lambda_override: float | None = None) -> list[OutcomeEvent]:
    """Run a multi-bucket rollout; return all OutcomeEvents the simulator emitted."""
    events: list[OutcomeEvent] = []
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=n_buckets,
        outcome_sink=events.append,
        exception_model=exception_model,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 1, 5))
    done = False
    while not done:
        _, _, done, _ = sim.step(_action())
    return events


def test_simulator_default_path_emits_no_shipment_exception_events():
    events = _run_rollout(exception_model=None)
    kinds = {e.outcome_kind for e in events}
    assert "shipment_exception" not in kinds


def test_simulator_attached_path_emits_shipment_exception_events():
    """With λ=1.0, every dispatched load fires an exception."""
    model = ExceptionModel(ExceptionParams(lambda_per_load=1.0))
    events = _run_rollout(exception_model=model, n_buckets=4)
    exception_events = [e for e in events if e.outcome_kind == "shipment_exception"]
    tender_events = [e for e in events if e.outcome_kind == "tender_accepted"]
    # One exception per dispatched load when λ=1.
    assert len(exception_events) == len(tender_events)
    assert len(exception_events) > 0
    for ev in exception_events:
        assert ev.payload["kind"] is not None
        assert ev.payload["severity"] is not None
        assert ev.payload["recovery_cost"] >= 0.0
        assert ev.payload["p_exception"] == pytest.approx(1.0)


def test_simulator_exception_decision_id_joins_to_tender_accepted():
    """shipment_exception decision_id matches the tender_accepted that produced it."""
    model = ExceptionModel(ExceptionParams(lambda_per_load=1.0))
    events = _run_rollout(exception_model=model, n_buckets=4)
    tender_ids = {
        e.decision_id for e in events if e.outcome_kind == "tender_accepted"
    }
    exception_ids = {
        e.decision_id for e in events if e.outcome_kind == "shipment_exception"
    }
    # λ=1 → every tender → an exception, so id sets are identical.
    assert exception_ids == tender_ids


def test_simulator_arrival_event_carries_exception_metadata():
    """When a dispatched load had an exception, the arrival event surfaces it."""
    model = ExceptionModel(ExceptionParams(lambda_per_load=1.0))
    events = _run_rollout(exception_model=model, n_buckets=4)
    arrival_events = [
        e for e in events
        if e.outcome_kind in ("shipment_delivered", "shipment_late")
    ]
    assert arrival_events, "expected at least one arrival event"
    for ev in arrival_events:
        assert "exception_kind" in ev.payload
        assert "exception_severity" in ev.payload
        assert "exception_recovery_cost" in ev.payload
        # With λ=1, recovery cost is whatever the severity draw mapped.
        assert ev.payload["exception_recovery_cost"] in (0.0, 500.0, 2000.0)


def test_simulator_arrival_event_omits_exception_metadata_when_none():
    """λ=0 → no fires → arrival events lack exception fields."""
    model = ExceptionModel(ExceptionParams(lambda_per_load=0.0))
    events = _run_rollout(exception_model=model, n_buckets=4)
    arrival_events = [
        e for e in events
        if e.outcome_kind in ("shipment_delivered", "shipment_late")
    ]
    assert arrival_events
    for ev in arrival_events:
        assert "exception_kind" not in ev.payload
        assert "exception_severity" not in ev.payload


def test_simulator_plan_production_never_emits_shipment_exception():
    """PLAN_PRODUCTION mode: simulator runs, model attached, no fires."""
    model = ExceptionModel()
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=6,
        mode=TwinMode.PLAN_PRODUCTION,
        demand_stochastic=False,
        on_time_stochastic=False,
        exception_model=model,
    )
    events: list[OutcomeEvent] = []
    sim_events = sim
    # Re-construct to wire outcome_sink (constructor arg).
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=6,
        mode=TwinMode.PLAN_PRODUCTION,
        demand_stochastic=False,
        on_time_stochastic=False,
        exception_model=model,
        outcome_sink=events.append,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 1, 5))
    done = False
    while not done:
        _, _, done, _ = sim.step(_action())
    kinds = {e.outcome_kind for e in events}
    assert "shipment_exception" not in kinds


def test_simulator_attaching_exception_model_does_not_change_other_outcomes():
    """Sanity: attaching ExceptionModel doesn't break tender_accepted /
    shipment_delivered counts compared to default.
    """
    plain_events = _run_rollout(exception_model=None, n_buckets=4)
    plain_tenders = sum(1 for e in plain_events if e.outcome_kind == "tender_accepted")
    plain_arrivals = sum(
        1 for e in plain_events
        if e.outcome_kind in ("shipment_delivered", "shipment_late")
    )

    # λ=0 means every draw returns fires=False → identical behaviour to no model.
    model = ExceptionModel(ExceptionParams(lambda_per_load=0.0))
    attached_events = _run_rollout(exception_model=model, n_buckets=4)
    attached_tenders = sum(
        1 for e in attached_events if e.outcome_kind == "tender_accepted"
    )
    attached_arrivals = sum(
        1 for e in attached_events
        if e.outcome_kind in ("shipment_delivered", "shipment_late")
    )

    assert plain_tenders == attached_tenders
    assert plain_arrivals == attached_arrivals

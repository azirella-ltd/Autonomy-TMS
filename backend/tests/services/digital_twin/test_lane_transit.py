"""LaneTransit physics model + simulator integration (PR-3.B).

Covers:
  - parameter validation (TransitContext + LaneTransitParams)
  - lognormal draw is unbiased: empirical mean ≈ μ at no season/weather
  - season modulation: winter > summer
  - weather modulation: storm > clear
  - conformal P10/P90 bracket the mean
  - PLAN_PRODUCTION deterministic
  - simulator integration: opt-in via constructor; default path
    preserves legacy behaviour; transit metadata reaches outcome events
"""
from __future__ import annotations

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
    LaneTransitModel,
    LaneTransitParams,
    PhysicsModel,
    TransitContext,
)
from app.services.digital_twin.shipment_generator import Phase1ShipmentGenerator
from azirella_data_model.digital_twin.twin_interface import TwinMode
from azirella_data_model.ml.outcome import OutcomeEvent
from azirella_demand_planning_contract import Tier


# ── Validation ───────────────────────────────────────────────────────


def test_context_rejects_zero_mean():
    with pytest.raises(ValueError, match="deterministic_mean_buckets"):
        TransitContext(deterministic_mean_buckets=0)


def test_context_rejects_out_of_range_day():
    with pytest.raises(ValueError, match="day_of_year"):
        TransitContext(deterministic_mean_buckets=2, day_of_year=400)


def test_context_rejects_out_of_range_weather():
    with pytest.raises(ValueError, match="weather_index"):
        TransitContext(deterministic_mean_buckets=2, weather_index=1.5)


def test_params_rejects_negative_sigma_ratio():
    with pytest.raises(ValueError, match="sigma_ratio"):
        LaneTransitParams(sigma_ratio=-0.1)


def test_params_rejects_negative_amplitude():
    with pytest.raises(ValueError, match="season_amplitude"):
        LaneTransitParams(season_amplitude=-0.1)


# ── Protocol compliance ──────────────────────────────────────────────


def test_protocol_compliance():
    model = LaneTransitModel()
    assert isinstance(model, PhysicsModel)


def test_step_before_reset_raises():
    model = LaneTransitModel()
    with pytest.raises(RuntimeError, match="reset"):
        model.step(TransitContext(deterministic_mean_buckets=2))


# ── Distribution shape ───────────────────────────────────────────────


def test_unbiased_at_no_modulation():
    """Mean draw ≈ μ when day_of_year=0 and weather_index=0."""
    model = LaneTransitModel()
    model.reset(scenario_seed=42)
    ctx = TransitContext(deterministic_mean_buckets=10)
    draws = [model.step(ctx).realised_buckets for _ in range(2000)]
    mean = sum(draws) / len(draws)
    assert 9.5 < mean < 10.5, f"expected ~10, got {mean}"


def test_season_winter_slower_than_summer():
    """Winter (day 15) transit > Summer (day 196) by season amplitude."""
    model = LaneTransitModel()
    model.reset(scenario_seed=42)
    ctx_winter = TransitContext(deterministic_mean_buckets=10, day_of_year=15)
    winter = sum(
        model.step(ctx_winter).realised_buckets for _ in range(1500)
    ) / 1500
    model.reset(scenario_seed=42)
    ctx_summer = TransitContext(deterministic_mean_buckets=10, day_of_year=196)
    summer = sum(
        model.step(ctx_summer).realised_buckets for _ in range(1500)
    ) / 1500
    assert winter > summer + 0.5, (
        f"winter {winter:.2f} should exceed summer {summer:.2f} by 0.5+"
    )


def test_weather_storm_slower_than_clear():
    """Severe weather (1.0) raises mean transit by ~25%."""
    model = LaneTransitModel()
    model.reset(scenario_seed=42)
    ctx_clear = TransitContext(deterministic_mean_buckets=10, weather_index=0.0)
    clear = sum(
        model.step(ctx_clear).realised_buckets for _ in range(1500)
    ) / 1500
    model.reset(scenario_seed=42)
    ctx_storm = TransitContext(deterministic_mean_buckets=10, weather_index=1.0)
    storm = sum(
        model.step(ctx_storm).realised_buckets for _ in range(1500)
    ) / 1500
    assert storm > clear + 1.5, (
        f"storm {storm:.2f} should exceed clear {clear:.2f} by 1.5+"
    )


def test_conformal_bands_bracket_mean():
    model = LaneTransitModel()
    model.reset(scenario_seed=42)
    out = model.step(TransitContext(deterministic_mean_buckets=10))
    assert out.p10_buckets < out.mean_buckets < out.p90_buckets
    # Bands should be roughly symmetric around the mean in log space —
    # geometric mean ≈ arithmetic mean for σ_ratio=0.15.
    geo_mean = (out.p10_buckets * out.p90_buckets) ** 0.5
    assert abs(geo_mean - out.mean_buckets) / out.mean_buckets < 0.05


def test_plan_production_is_deterministic():
    class _FakeMode:
        value = "plan_production"

    model = LaneTransitModel()
    model.reset(scenario_seed=999, twin_mode=_FakeMode())
    ctx = TransitContext(deterministic_mean_buckets=10)
    out1 = model.step(ctx)
    out2 = model.step(ctx)
    assert out1.realised_buckets == out2.realised_buckets
    assert out1.realised_buckets == int(round(out1.mean_buckets))


def test_determinism_same_seed_same_draws():
    def _draws() -> list[int]:
        m = LaneTransitModel()
        m.reset(scenario_seed=12345)
        ctx = TransitContext(deterministic_mean_buckets=5, day_of_year=180)
        return [m.step(ctx).realised_buckets for _ in range(50)]

    assert _draws() == _draws()


# ── Simulator integration ────────────────────────────────────────────


def _carriers() -> dict[str, CarrierProfile]:
    return {
        "carrier:acme": CarrierProfile(
            carrier_id="carrier:acme",
            cost_per_load=120.0,
            on_time_rate=0.95,
            capacity_per_bucket=8,
        ),
    }


def _equipment() -> dict[str, EquipmentProfile]:
    return {
        "dry_van_53": EquipmentProfile(
            equipment_kind="dry_van_53", load_capacity_units=10.0,
        ),
    }


def _lane_params() -> LanePhysicsParams:
    return LanePhysicsParams(
        origin_site_id="site:1",
        destination_site_id="site:2",
        product_id="sku:A",
        transit_buckets=2,
        initial_equipment=20,
        dock_capacity_per_bucket=20,
        carriers=_carriers(),
        equipment_kinds=_equipment(),
        cost_target_per_load=100.0,
    )


def _generator() -> Phase1ShipmentGenerator:
    return Phase1ShipmentGenerator(
        candidate_lanes=[("site:1", "site:2")],
        candidate_products=["sku:A"],
        base_volumes={("site:1", "site:2", "sku:A"): 60.0},
        seed=42,
    )


def test_simulator_default_no_transit_model_uses_static_buckets():
    """No model attached → every load uses LanePhysicsParams.transit_buckets."""
    events: list[OutcomeEvent] = []
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1, config_id=1,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        mode=TwinMode.TRAINING,
        outcome_sink=events.append,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
    sim.step(LaneFlowAction(
        carrier_id="carrier:acme", equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    ))

    accepted = [e for e in events if e.outcome_kind == "tender_accepted"]
    assert accepted, "expected at least one tender_accepted"
    for e in accepted:
        # Legacy events DON'T carry transit-band metadata.
        assert "transit_realised_buckets" not in e.payload
        assert "transit_p10_buckets" not in e.payload


def test_simulator_attached_transit_model_emits_band_metadata():
    """With LaneTransitModel attached, every accepted event carries
    transit_realised_buckets + p10/p90 + season + weather factors."""
    events: list[OutcomeEvent] = []
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1, config_id=1,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        mode=TwinMode.TRAINING,
        lane_transit_model=LaneTransitModel(),
        scenario_weather_index=0.3,
        outcome_sink=events.append,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
    sim.step(LaneFlowAction(
        carrier_id="carrier:acme", equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    ))

    accepted = [e for e in events if e.outcome_kind == "tender_accepted"]
    assert accepted
    for e in accepted:
        assert "transit_realised_buckets" in e.payload
        assert "transit_mean_buckets" in e.payload
        assert "transit_p10_buckets" in e.payload
        assert "transit_p90_buckets" in e.payload
        assert "transit_season_factor" in e.payload
        assert "transit_weather_factor" in e.payload
        # P10 < mean < P90 always.
        assert e.payload["transit_p10_buckets"] <= e.payload["transit_mean_buckets"]
        assert e.payload["transit_mean_buckets"] <= e.payload["transit_p90_buckets"]


def test_simulator_determinism_with_attached_transit_model():
    def _run_realised_buckets() -> list[int]:
        events: list[OutcomeEvent] = []
        sim = LaneFlowSimulator(
            generator=_generator(),
            tenant_id=1, config_id=1,
            lane_params=_lane_params(),
            tier=Tier.TACTICAL,
            horizon_buckets=4,
            mode=TwinMode.TRAINING,
            lane_transit_model=LaneTransitModel(),
            outcome_sink=events.append,
        )
        sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
        sim.step(LaneFlowAction(
            carrier_id="carrier:acme", equipment_kind="dry_van_53",
            dispatch_offset_hours=0.0,
        ))
        return [
            e.payload["transit_realised_buckets"]
            for e in events
            if e.outcome_kind == "tender_accepted"
        ]

    a = _run_realised_buckets()
    b = _run_realised_buckets()
    assert a == b, f"same-seed runs should produce identical transit draws: a={a} b={b}"

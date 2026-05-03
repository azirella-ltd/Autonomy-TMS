"""SeasonalEnvelope Phase-C adoption (PR-4) — observation-side tests.

Covers:
  - LaneFlowObservation defaults: season_sin/cos = 0.0, regime = None
  - simulator computes sin/cos from bucket_start day_of_year
  - sin/cos sit on the unit circle (sin² + cos² ≈ 1)
  - phase advances across buckets (Jan 1 vs April Fool's vs midsummer)
  - default-no-envelope path leaves regime = None
  - registered SeasonalEnvelope populates regime per Core classify_regime
  - regime values cycle through the four states across a year
  - end-to-end ScenarioSampler stratification: rollout dates land in
    each regime
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.services.digital_twin import (
    CarrierProfile,
    EquipmentProfile,
    LaneFlowAction,
    LaneFlowObservation,
    LaneFlowSimulator,
    LanePhysicsParams,
    Phase1ShipmentGenerator,
)
from azirella_data_model.stochastic import (
    FitMetadata,
    SeasonalEnvelope,
    SeasonalRegime,
    TriangularDistribution,
    classify_regime,
    stratified_start_dates,
)
from azirella_demand_planning_contract import Tier


# ── Fixtures ─────────────────────────────────────────────────────────


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
        initial_equipment=10,
        dock_capacity_per_bucket=20,
        carriers=_carriers(),
        equipment_kinds=_equipment(),
        cost_target_per_load=100.0,
    )


def _generator() -> Phase1ShipmentGenerator:
    return Phase1ShipmentGenerator(
        candidate_lanes=[("site:1", "site:2")],
        candidate_products=["sku:A"],
        base_volumes={("site:1", "site:2", "sku:A"): 30.0},
        seed=42,
    )


def _action() -> LaneFlowAction:
    return LaneFlowAction(
        carrier_id="carrier:acme",
        equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    )


def _make_envelope() -> SeasonalEnvelope:
    """Cosine-shaped envelope with peak in early winter (week 0–4)
    and trough in early summer (week 25–28). Useful for regime tests
    because each calendar quarter sits in a different regime.
    """
    period = 52
    p_mid: list[float] = []
    for i in range(period):
        # Phase 0 at week 0 (peak winter), so cos = 1 → high p_mid.
        # Half-cycle (phase π) at week 26 → cos = -1 → low p_mid.
        phase = 2.0 * math.pi * i / period
        p_mid.append(20.0 + 10.0 * math.cos(phase))
    p_low = [v * 0.85 for v in p_mid]
    p_high = [v * 1.15 for v in p_mid]
    return SeasonalEnvelope(
        series_kind="other",
        series_key="lane:site:1->site:2",
        period=period,
        period_indices=list(range(period)),
        p_low=p_low,
        p_mid=p_mid,
        p_high=p_high,
        residual_distribution=TriangularDistribution(min=-1.0, mode=0.0, max=1.0),
        fit_metadata=FitMetadata(
            n_observations=period * 2,
            n_full_periods=2.0,
            fit_method="centered_mean",
            residual_std=1.0,
        ),
    )


# ── LaneFlowObservation defaults ─────────────────────────────────────


def test_observation_defaults_have_zero_season_sin_cos_and_no_regime():
    obs = LaneFlowObservation(
        transportation_lane_id="lane:1->2",
        period=0,
        in_flight_loads=0,
        arrivals_this_period=0,
        carrier_capacity_remaining=10.0,
        equipment_available=4,
        dock_queue_depth=0,
        on_time_pct_trailing=1.0,
        cost_per_load_trailing=0.0,
    )
    assert obs.season_sin == 0.0
    assert obs.season_cos == 0.0
    assert obs.seasonal_regime is None


# ── Simulator — sin/cos from bucket_start ─────────────────────────────


def test_initial_observation_january_first_anchored_at_phase_zero():
    """Day 1 → phase 0 → (sin, cos) = (0, 1)."""
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
    )
    obs = sim.reset(scenario_seed=42, anchor_date=date(2026, 1, 1))
    assert obs.season_sin == pytest.approx(0.0, abs=1e-9)
    assert obs.season_cos == pytest.approx(1.0, abs=1e-9)


def test_seasonal_features_sit_on_unit_circle():
    """For any anchor date, sin² + cos² ≈ 1."""
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=8,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 4, 15))
    done = False
    while not done:
        obs, _, done, _ = sim.step(_action())
        magnitude = obs.season_sin ** 2 + obs.season_cos ** 2
        assert magnitude == pytest.approx(1.0, rel=1e-6)


def test_seasonal_features_advance_per_bucket():
    """Successive observations from a TACTICAL (7-day) rollout produce
    different sin/cos pairs (no degenerate constant)."""
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 1, 1))
    pairs: list[tuple[float, float]] = []
    done = False
    while not done:
        obs, _, done, _ = sim.step(_action())
        pairs.append((obs.season_sin, obs.season_cos))
    assert len(set(pairs)) == len(pairs), (
        f"expected {len(pairs)} distinct phases, got {len(set(pairs))}"
    )


def test_no_anchor_date_yields_zero_phase():
    """When ``reset(anchor_date=None)`` is called and ``date.today()``
    happens to land on phase 0 we'd be fragile, so test the underlying
    helper with ``None`` directly.
    """
    # Construct an observation directly with ``plan_date=None`` to assert
    # the sentinel path returns (0, 0).
    from app.services.digital_twin.lane_flow_simulator import LaneFlowSimulator

    sin_, cos_ = LaneFlowSimulator._season_phase(None)
    assert (sin_, cos_) == (0.0, 0.0)


def test_season_phase_helper_known_anchors():
    """Day 1 → (0, 1); ~quarter-year later → (~1, ~0); half-year → (~0, -1)."""
    from app.services.digital_twin.lane_flow_simulator import LaneFlowSimulator

    s_jan1, c_jan1 = LaneFlowSimulator._season_phase(date(2026, 1, 1))
    assert s_jan1 == pytest.approx(0.0, abs=1e-9)
    assert c_jan1 == pytest.approx(1.0, abs=1e-9)

    # Approximately quarter year (day 92 = April 2 in 2026): phase ≈ π/2.
    s_q, c_q = LaneFlowSimulator._season_phase(date(2026, 4, 2))
    assert s_q == pytest.approx(1.0, abs=0.05)
    assert c_q == pytest.approx(0.0, abs=0.05)

    # Approximately mid-year (day 183 = July 2): phase ≈ π.
    s_h, c_h = LaneFlowSimulator._season_phase(date(2026, 7, 2))
    assert s_h == pytest.approx(0.0, abs=0.05)
    assert c_h == pytest.approx(-1.0, abs=0.05)


# ── Regime: default no envelope ──────────────────────────────────────


def test_no_envelope_yields_none_regime():
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
    )
    obs = sim.reset(scenario_seed=42, anchor_date=date(2026, 6, 15))
    assert obs.seasonal_regime is None
    done = False
    while not done:
        next_obs, _, done, _ = sim.step(_action())
        assert next_obs.seasonal_regime is None


# ── Regime: with envelope registered ─────────────────────────────────


def test_envelope_registered_yields_regime_string():
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        seasonal_envelope=_make_envelope(),
    )
    obs = sim.reset(scenario_seed=42, anchor_date=date(2026, 1, 1))
    assert obs.seasonal_regime is not None
    # Anchor on week 0, peak winter envelope → PEAK regime.
    assert obs.seasonal_regime == SeasonalRegime.PEAK.value


def test_envelope_regime_matches_core_classify_regime():
    """Simulator's regime exactly matches Core's classify_regime helper."""
    envelope = _make_envelope()
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1,
        config_id=10,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        seasonal_envelope=envelope,
    )
    anchor = date(2026, 6, 1)
    obs = sim.reset(scenario_seed=42, anchor_date=anchor)
    expected = classify_regime(envelope, anchor).value
    assert obs.seasonal_regime == expected


def test_regime_visits_all_four_buckets_across_a_year():
    """Anchored at successive 13-week offsets, observations land in each
    of the four regimes (with the cosine-shaped envelope above).
    """
    envelope = _make_envelope()
    seen_regimes: set[str] = set()
    for week_offset in range(0, 52, 4):  # every 4 weeks across the year
        anchor = date(2026, 1, 1) + timedelta(weeks=week_offset)
        sim = LaneFlowSimulator(
            generator=_generator(),
            tenant_id=1,
            config_id=10,
            lane_params=_lane_params(),
            tier=Tier.TACTICAL,
            horizon_buckets=2,
            seasonal_envelope=envelope,
        )
        obs = sim.reset(scenario_seed=42, anchor_date=anchor)
        seen_regimes.add(obs.seasonal_regime)
    expected = {r.value for r in SeasonalRegime}
    assert seen_regimes == expected, (
        f"expected all 4 regimes, got {seen_regimes}"
    )


# ── End-to-end stratification: Core helper feeds simulator anchor ────


def test_stratified_start_dates_drive_distinct_simulator_anchors():
    """``stratified_start_dates`` returns dates per regime; passing each
    into the simulator's reset yields an observation whose
    ``seasonal_regime`` matches.
    """
    envelope = _make_envelope()
    pools = stratified_start_dates(
        envelope,
        window_start=date(2026, 1, 1),
        window_end=date(2026, 12, 31),
        n_per_regime=1,
    )
    # All four regimes should have at least one date in a full year.
    for regime in SeasonalRegime:
        assert pools.get(regime), f"no dates for {regime}"
        anchor = pools[regime][0]
        sim = LaneFlowSimulator(
            generator=_generator(),
            tenant_id=1,
            config_id=10,
            lane_params=_lane_params(),
            tier=Tier.TACTICAL,
            horizon_buckets=2,
            seasonal_envelope=envelope,
        )
        obs = sim.reset(scenario_seed=42, anchor_date=anchor)
        assert obs.seasonal_regime == regime.value, (
            f"regime mismatch: anchor {anchor} expected {regime.value} got {obs.seasonal_regime}"
        )


# ── Backward-compat: existing observation-equality patterns still hold ──


def test_existing_observation_construction_unchanged():
    """Observations built without the new fields still equal each other —
    PR-4 added fields with sensible defaults (0.0 / None), not required
    fields that break existing fixtures.
    """
    a = LaneFlowObservation(
        transportation_lane_id="lane:x",
        period=0,
        in_flight_loads=0,
        arrivals_this_period=0,
        carrier_capacity_remaining=1.0,
        equipment_available=1,
        dock_queue_depth=0,
        on_time_pct_trailing=1.0,
        cost_per_load_trailing=0.0,
    )
    b = LaneFlowObservation(
        transportation_lane_id="lane:x",
        period=0,
        in_flight_loads=0,
        arrivals_this_period=0,
        carrier_capacity_remaining=1.0,
        equipment_available=1,
        dock_queue_depth=0,
        on_time_pct_trailing=1.0,
        cost_per_load_trailing=0.0,
    )
    assert a == b

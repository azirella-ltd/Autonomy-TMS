"""EquipmentFlow physics + simulator integration (PR-3.D).

Covers:
  - validation (EquipmentRequest + EquipmentFlowParams)
  - register_site initial-count formula
  - step() decrements pool, computes wait when short
  - return_equipment increments
  - all_balances snapshot
  - simulator integration: opt-in via constructor; default path
    preserves legacy behaviour; per-site balances stay synced via
    dispatch + arrival paths
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
    EquipmentDispatch,
    EquipmentFlowModel,
    EquipmentFlowParams,
    EquipmentRequest,
)
from app.services.digital_twin.shipment_generator import Phase1ShipmentGenerator
from azirella_data_model.digital_twin.twin_interface import TwinMode
from azirella_demand_planning_contract import Tier


# ── Validation ───────────────────────────────────────────────────────


def test_request_rejects_empty_site():
    with pytest.raises(ValueError, match="site_id"):
        EquipmentRequest(site_id="", equipment_kind="dry_van", count=1)


def test_request_rejects_empty_kind():
    with pytest.raises(ValueError, match="equipment_kind"):
        EquipmentRequest(site_id="s1", equipment_kind="", count=1)


def test_request_rejects_zero_count():
    with pytest.raises(ValueError, match="count"):
        EquipmentRequest(site_id="s1", equipment_kind="dry_van", count=0)


def test_params_rejects_negative_buffer():
    with pytest.raises(ValueError, match="initial_load_buffer_factor"):
        EquipmentFlowParams(initial_load_buffer_factor=-0.1)


def test_params_rejects_negative_lead_time():
    with pytest.raises(ValueError, match="reposition_lead_time_factor"):
        EquipmentFlowParams(reposition_lead_time_factor=-0.1)


# ── register_site / initial balances ─────────────────────────────────


def test_initial_per_site_overrides_loaded():
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={
            ("site:1", "dry_van"): 12,
            ("site:2", "reefer"): 4,
        },
    ))
    model.reset()
    assert model.balance("site:1", "dry_van") == 12
    assert model.balance("site:2", "reefer") == 4


def test_register_site_uses_avg_daily_loads_formula():
    """floor(avg_daily_loads × initial_load_buffer_factor)."""
    model = EquipmentFlowModel(EquipmentFlowParams(
        avg_daily_loads_per_site={"site:1": 10},
        initial_load_buffer_factor=1.5,
    ))
    model.reset()
    model.register_site("site:1", "dry_van")
    assert model.balance("site:1", "dry_van") == 15


def test_register_site_explicit_initial_overrides_formula():
    model = EquipmentFlowModel(EquipmentFlowParams(
        avg_daily_loads_per_site={"site:1": 10},
    ))
    model.reset()
    model.register_site("site:1", "dry_van", initial=99)
    assert model.balance("site:1", "dry_van") == 99


def test_register_site_idempotent():
    """Re-registering a site shouldn't reset its balance."""
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={("site:1", "dry_van"): 5},
    ))
    model.reset()
    model.register_site("site:1", "dry_van", initial=999)
    assert model.balance("site:1", "dry_van") == 5  # unchanged


# ── step / dispatch ──────────────────────────────────────────────────


def test_step_before_reset_raises():
    model = EquipmentFlowModel()
    with pytest.raises(RuntimeError, match="reset"):
        model.step(EquipmentRequest(site_id="s1", equipment_kind="dv", count=1))


def test_step_decrements_pool_when_available():
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={("site:1", "dry_van"): 5},
    ))
    model.reset()
    out = model.step(EquipmentRequest(
        site_id="site:1", equipment_kind="dry_van", count=2,
    ))
    assert out.granted_count == 2
    assert out.equipment_wait_buckets == 0
    assert out.site_balance_after == 3
    assert model.balance("site:1", "dry_van") == 3


def test_step_short_returns_wait_buckets_for_shortfall():
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={("site:1", "dry_van"): 1},
    ))
    model.reset()
    out = model.step(EquipmentRequest(
        site_id="site:1", equipment_kind="dry_van", count=4,
    ))
    assert out.granted_count == 1
    # 3 missing units → 3 bucket wait per the Phase-1 prior.
    assert out.equipment_wait_buckets == 3
    assert out.site_balance_after == 0


def test_step_auto_registers_unknown_site():
    """Stepping at an unknown site auto-registers via avg_daily_loads."""
    model = EquipmentFlowModel(EquipmentFlowParams(
        avg_daily_loads_per_site={"site:42": 8},
    ))
    model.reset()
    out = model.step(EquipmentRequest(
        site_id="site:42", equipment_kind="dry_van", count=2,
    ))
    # Auto-registered with floor(8 × 1.5) = 12; consumed 2 → 10.
    assert out.granted_count == 2
    assert out.site_balance_after == 10


def test_return_equipment_increments_pool():
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={("site:1", "dry_van"): 3},
    ))
    model.reset()
    new = model.return_equipment("site:1", "dry_van", 2)
    assert new == 5
    assert model.balance("site:1", "dry_van") == 5


def test_return_equipment_rejects_negative():
    model = EquipmentFlowModel()
    model.reset()
    with pytest.raises(ValueError, match="count"):
        model.return_equipment("site:1", "dry_van", -1)


def test_all_balances_snapshot():
    model = EquipmentFlowModel(EquipmentFlowParams(
        initial_per_site={
            ("site:1", "dry_van"): 5,
            ("site:2", "reefer"): 3,
        },
    ))
    model.reset()
    snapshot = model.all_balances()
    assert snapshot == {
        ("site:1", "dry_van"): 5,
        ("site:2", "reefer"): 3,
    }
    # Mutating the snapshot doesn't affect the model.
    snapshot[("site:1", "dry_van")] = 999
    assert model.balance("site:1", "dry_van") == 5


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
        transit_buckets=1,
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


def test_simulator_default_no_equipment_model_works():
    """Default behaviour preserved when no model attached."""
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1, config_id=1,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        mode=TwinMode.TRAINING,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
    obs, _, _, _ = sim.step(LaneFlowAction(
        carrier_id="carrier:acme", equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    ))
    # The simulator's legacy equipment_available counter is the only
    # source of truth — observation should still report it.
    assert obs.equipment_available <= 20


def test_simulator_attached_equipment_model_initialises_origin_only():
    """At reset, origin pre-loaded with initial_equipment, destination 0."""
    model = EquipmentFlowModel(EquipmentFlowParams())
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1, config_id=1,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        mode=TwinMode.TRAINING,
        equipment_flow_model=model,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
    assert model.balance("site:1", "dry_van_53") == 20
    assert model.balance("site:2", "dry_van_53") == 0


def test_simulator_attached_equipment_model_decrements_on_dispatch():
    """Per-site origin balance drops by accepted_count after dispatch."""
    model = EquipmentFlowModel(EquipmentFlowParams())
    sim = LaneFlowSimulator(
        generator=_generator(),
        tenant_id=1, config_id=1,
        lane_params=_lane_params(),
        tier=Tier.TACTICAL,
        horizon_buckets=4,
        mode=TwinMode.TRAINING,
        equipment_flow_model=model,
    )
    sim.reset(scenario_seed=42, anchor_date=date(2026, 5, 3))
    obs_before = model.balance("site:1", "dry_van_53")
    obs, _, _, _ = sim.step(LaneFlowAction(
        carrier_id="carrier:acme", equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    ))
    obs_after = model.balance("site:1", "dry_van_53")
    # Should have dropped by the simulator's accepted_count.
    delta = obs_before - obs_after
    assert delta >= 0
    # The simulator's legacy counter and the model's per-site origin
    # balance should agree for this single-channel scenario.
    assert obs.equipment_available == obs_after

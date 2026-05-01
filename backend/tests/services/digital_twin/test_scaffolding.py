"""PR-1 scaffolding smoke tests.

Verifies the new ``app.services.digital_twin`` subpackage imports, the
TMS-shaped dataclasses construct, the Phase-1 shipment generator emits
a contract-valid empty envelope, and the simulator + adapter shells
honour their interfaces.

PR-2/3 expand these as the parametric generator and lane-flow physics
land.
"""
from __future__ import annotations

import pytest

from app.services.digital_twin import (
    LaneFlowAction,
    LaneFlowObservation,
    LaneFlowReward,
    LaneFlowSimulator,
    LaneFlowStepAdapter,
    LaneFlowTransition,
    PARAMETRIC_STUB_PRODUCER_SIGNATURE,
    Phase1ShipmentGenerator,
    ShipmentGenerator,
)
from azirella_demand_planning_contract import Tier
from azirella_transfer_order_envelope_contract import (
    PhaseIndicator,
    TransferOrderEnvelope,
)


def _make_observation(period: int = 0) -> LaneFlowObservation:
    return LaneFlowObservation(
        transportation_lane_id="lane:1->2",
        period=period,
        in_flight_loads=0,
        arrivals_this_period=0,
        carrier_capacity_remaining=10.0,
        equipment_available=4,
        dock_queue_depth=0,
        on_time_pct_trailing=1.0,
        cost_per_load_trailing=0.0,
    )


def _make_action() -> LaneFlowAction:
    return LaneFlowAction(
        carrier_id="carrier:acme",
        equipment_kind="dry_van_53",
        dispatch_offset_hours=0.0,
    )


def _make_reward() -> LaneFlowReward:
    return LaneFlowReward(total=0.0)


# ── Dataclass construction ─────────────────────────────────────────────


def test_observation_constructs_with_required_fields_only():
    obs = _make_observation()
    assert obs.transportation_lane_id == "lane:1->2"
    assert obs.plan_date is None and obs.as_of is None


def test_action_constructs_with_optional_reposition():
    action = LaneFlowAction(
        carrier_id="carrier:acme",
        equipment_kind="reefer_48",
        dispatch_offset_hours=2.0,
        reposition_to_site_id="site:42",
    )
    assert action.reposition_to_site_id == "site:42"
    assert action.confidence == 1.0  # default


def test_transition_carries_done_flag_and_metadata():
    transition = LaneFlowTransition(
        observation=_make_observation(0),
        action=_make_action(),
        reward=_make_reward(),
        next_observation=_make_observation(1),
        done=False,
        metadata={"bucket": "TACTICAL"},
    )
    assert transition.metadata["bucket"] == "TACTICAL"
    assert transition.done is False


# ── Phase-1 shipment generator ────────────────────────────────────────


def test_phase1_generator_satisfies_protocol():
    generator = Phase1ShipmentGenerator()
    assert isinstance(generator, ShipmentGenerator)


def test_phase1_generator_emits_empty_envelope_with_correct_metadata():
    generator = Phase1ShipmentGenerator(
        candidate_lanes=[("site:1", "site:2")],
        candidate_products=["sku:A"],
    )
    envelope = generator.generate_envelope(
        tenant_id=1,
        config_id=10,
        tier=Tier.TACTICAL,
    )
    assert isinstance(envelope, TransferOrderEnvelope)
    assert envelope.rows == []  # PR-1: empty by design
    assert envelope.phase_indicator is PhaseIndicator.PARAMETRIC_STUB
    assert envelope.produced_by == PARAMETRIC_STUB_PRODUCER_SIGNATURE
    assert envelope.upstream_supply_plan_signature is None


def test_phase1_producer_signature_format():
    # Format is "<plane>:<artefact>:<version>" per TWIN_AND_ENVELOPES.md §6.
    parts = PARAMETRIC_STUB_PRODUCER_SIGNATURE.split(":")
    assert len(parts) == 3
    assert parts[0] == "tms"
    assert parts[2].startswith("v")


# ── Simulator + adapter shells ────────────────────────────────────────


def test_simulator_reset_raises_not_implemented_in_pr1():
    simulator = LaneFlowSimulator(
        generator=Phase1ShipmentGenerator(),
        tenant_id=1,
        config_id=10,
    )
    with pytest.raises(NotImplementedError, match="PR-3"):
        simulator.reset(scenario_seed=42)


def test_simulator_step_raises_not_implemented_in_pr1():
    simulator = LaneFlowSimulator(
        generator=Phase1ShipmentGenerator(),
        tenant_id=1,
        config_id=10,
    )
    with pytest.raises(NotImplementedError, match="PR-3"):
        simulator.step(_make_action())


def test_step_adapter_rejects_step_before_reset():
    adapter = LaneFlowStepAdapter(
        simulator=LaneFlowSimulator(
            generator=Phase1ShipmentGenerator(),
            tenant_id=1,
            config_id=10,
        ),
    )
    with pytest.raises(RuntimeError, match="reset"):
        adapter.step(_make_action())


def test_step_adapter_starts_with_empty_trajectory():
    adapter = LaneFlowStepAdapter(
        simulator=LaneFlowSimulator(
            generator=Phase1ShipmentGenerator(),
            tenant_id=1,
            config_id=10,
        ),
    )
    assert adapter.trajectory == []

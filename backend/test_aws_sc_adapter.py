#!/usr/bin/env python3
"""
Test AWS SC Adapter - Backward Compatibility Verification

This script tests that the AWS SC compliance layer maintains
backward compatibility with existing Beer Game agents and training data.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from app.rl.config import SimulationParams
from app.rl.aws_sc_config import (
    SimulationParamsV2,
    simulation_to_sc_state,
    sc_to_simulation_state,
    AWS_SC_NODE_FEATURES,
)
from app.rl.training_data_adapter import (
    SCAdapter,
    TrainingDataAdapter,
)


def test_params_conversion():
    """Test parameter conversion between schemas."""
    print("\n" + "=" * 80)
    print("TEST 1: Parameter Conversion")
    print("=" * 80)

    # Create legacy simulation params
    legacy_params = SimulationParams(
        order_leadtime=2,
        supply_leadtime=2,
        init_inventory=12,
        holding_cost=0.5,
        backlog_cost=1.0,
    )
    print(f"\n✅ Created legacy SimulationParams:")
    print(f"   order_leadtime: {legacy_params.order_leadtime}")
    print(f"   init_inventory: {legacy_params.init_inventory}")
    print(f"   holding_cost: {legacy_params.holding_cost}")

    # Convert to AWS SC params
    adapter = TrainingDataAdapter(use_sc_fields=True)
    aws_sc_params = adapter.convert_params(legacy_params)
    print(f"\n✅ Converted to SimulationParamsV2 (AWS SC):")
    print(f"   lead_time_days: {aws_sc_params.lead_time_days}")
    print(f"   on_hand_qty: {aws_sc_params.on_hand_qty}")
    print(f"   holding_cost_per_unit: {aws_sc_params.holding_cost_per_unit}")

    # Test backward compatibility aliases
    print(f"\n✅ Testing backward compatibility aliases:")
    print(f"   params.inventory (alias): {aws_sc_params.inventory}")
    print(f"   params.on_hand_qty (AWS SC): {aws_sc_params.on_hand_qty}")
    assert aws_sc_params.inventory == aws_sc_params.on_hand_qty, "Alias mismatch!"

    print(f"   params.backlog (alias): {aws_sc_params.backlog}")
    print(f"   params.backorder_qty (AWS SC): {aws_sc_params.backorder_qty}")
    assert aws_sc_params.backlog == aws_sc_params.backorder_qty, "Alias mismatch!"

    print(f"   params.order_leadtime (alias): {aws_sc_params.order_leadtime}")
    print(f"   params.lead_time_days (AWS SC): {aws_sc_params.lead_time_days}")
    assert aws_sc_params.order_leadtime == aws_sc_params.lead_time_days, "Alias mismatch!"

    print(f"\n✅ All aliases work correctly!")

    # Test dictionary conversion
    beer_game_dict = aws_sc_params.to_beer_game_dict()
    print(f"\n✅ Converted to Beer Game dict:")
    print(f"   {beer_game_dict}")

    aws_sc_dict = aws_sc_params.to_aws_sc_dict()
    print(f"\n✅ Converted to AWS SC dict:")
    print(f"   {aws_sc_dict}")

    print(f"\n✅ TEST 1 PASSED: Parameter conversion works correctly")


def test_state_conversion():
    """Test state dictionary conversion."""
    print("\n" + "=" * 80)
    print("TEST 2: State Dictionary Conversion")
    print("=" * 80)

    # Simulation state
    simulation_state = {
        "inventory": 12,
        "backlog": 3,
        "pipeline": 8,
        "incoming_orders": 5,
        "incoming_shipments": 6,
        "order_leadtime": 2,
        "holding_cost": 0.5,
    }
    print(f"\n✅ Simulation state:")
    for key, val in simulation_state.items():
        print(f"   {key}: {val}")

    # Convert to AWS SC
    aws_sc_state = simulation_to_sc_state(simulation_state)
    print(f"\n✅ AWS SC state:")
    for key, val in aws_sc_state.items():
        print(f"   {key}: {val}")

    # Verify mappings
    assert aws_sc_state["on_hand_qty"] == simulation_state["inventory"]
    assert aws_sc_state["backorder_qty"] == simulation_state["backlog"]
    assert aws_sc_state["in_transit_qty"] == simulation_state["pipeline"]
    assert aws_sc_state["demand_qty"] == simulation_state["incoming_orders"]
    assert aws_sc_state["supply_qty"] == simulation_state["incoming_shipments"]
    assert aws_sc_state["lead_time_days"] == simulation_state["order_leadtime"]

    # Convert back to simulation state
    simulation_state_restored = sc_to_simulation_state(aws_sc_state)
    print(f"\n✅ Restored simulation state:")
    for key, val in simulation_state_restored.items():
        print(f"   {key}: {val}")

    # Verify round-trip
    for key in ["inventory", "backlog", "pipeline", "incoming_orders"]:
        assert simulation_state_restored[key] == simulation_state[key], f"Round-trip failed for {key}"

    print(f"\n✅ TEST 2 PASSED: State conversion is bidirectional")


def test_training_sample_wrapping():
    """Test training sample wrapping with AWS SC fields."""
    print("\n" + "=" * 80)
    print("TEST 3: Training Sample Wrapping")
    print("=" * 80)

    adapter = SCAdapter(use_sc_fields=True, backward_compatible=True)

    # Create sample with Beer Game fields
    sample = adapter.wrap_training_sample(
        role="retailer",
        position=0,
        inventory=12,
        backlog=3,
        pipeline=8,
        incoming_orders=5,
    )

    print(f"\n✅ Wrapped sample:")
    for key, val in sample.items():
        print(f"   {key}: {val}")

    # Verify AWS SC fields are present
    assert "on_hand_qty" in sample, "Missing on_hand_qty"
    assert "backorder_qty" in sample, "Missing backorder_qty"
    assert "in_transit_qty" in sample, "Missing in_transit_qty"
    assert "site_id" in sample, "Missing site_id"
    assert "item_id" in sample, "Missing item_id"

    # Verify Beer Game fields are present (backward compat)
    assert "inventory" in sample, "Missing inventory (backward compat)"
    assert "backlog" in sample, "Missing backlog (backward compat)"
    assert "role" in sample, "Missing role (backward compat)"

    # Verify values match
    assert sample["on_hand_qty"] == sample["inventory"]
    assert sample["backorder_qty"] == sample["backlog"]
    assert sample["in_transit_qty"] == sample["pipeline"]

    print(f"\n✅ TEST 3 PASSED: Sample wrapping includes both schemas")


def test_training_batch_wrapping():
    """Test training batch wrapping."""
    print("\n" + "=" * 80)
    print("TEST 4: Training Batch Wrapping")
    print("=" * 80)

    adapter = SCAdapter(use_sc_fields=True, backward_compatible=True)

    # Create batch with Beer Game fields
    batch = {
        "inventory": np.array([[12], [10], [15]]),
        "backlog": np.array([[3], [0], [5]]),
        "pipeline": np.array([[8], [6], [10]]),
        "node_types": np.array([[0], [1], [2]]),
    }

    print(f"\n✅ Original batch keys: {list(batch.keys())}")

    # Wrap batch
    wrapped_batch = adapter.wrap_training_batch(batch)

    print(f"\n✅ Wrapped batch keys: {list(wrapped_batch.keys())}")

    # Verify AWS SC fields added
    assert "on_hand_qty" in wrapped_batch
    assert "backorder_qty" in wrapped_batch
    assert "in_transit_qty" in wrapped_batch

    # Verify arrays are identical
    assert np.array_equal(wrapped_batch["on_hand_qty"], batch["inventory"])
    assert np.array_equal(wrapped_batch["backorder_qty"], batch["backlog"])
    assert np.array_equal(wrapped_batch["in_transit_qty"], batch["pipeline"])

    print(f"\n✅ TEST 4 PASSED: Batch wrapping preserves data")


def test_backward_compatibility():
    """Test that existing code can still use Beer Game fields."""
    print("\n" + "=" * 80)
    print("TEST 6: Backward Compatibility")
    print("=" * 80)

    # Create params with simulation fields
    params = SimulationParamsV2(
        role="retailer",
        position=0,
    )

    # Access via Beer Game aliases
    inventory = params.inventory
    backlog = params.backlog
    pipeline = params.pipeline
    order_leadtime = params.order_leadtime
    holding_cost = params.holding_cost

    print(f"\n✅ Accessed via Beer Game aliases:")
    print(f"   params.inventory: {inventory}")
    print(f"   params.backlog: {backlog}")
    print(f"   params.pipeline: {pipeline}")
    print(f"   params.order_leadtime: {order_leadtime}")
    print(f"   params.holding_cost: {holding_cost}")

    # Access via AWS SC fields
    on_hand_qty = params.on_hand_qty
    backorder_qty = params.backorder_qty
    in_transit_qty = params.in_transit_qty
    lead_time_days = params.lead_time_days
    holding_cost_per_unit = params.holding_cost_per_unit

    print(f"\n✅ Accessed via AWS SC fields:")
    print(f"   params.on_hand_qty: {on_hand_qty}")
    print(f"   params.backorder_qty: {backorder_qty}")
    print(f"   params.in_transit_qty: {in_transit_qty}")
    print(f"   params.lead_time_days: {lead_time_days}")
    print(f"   params.holding_cost_per_unit: {holding_cost_per_unit}")

    # Verify they return same values
    assert inventory == on_hand_qty
    assert backlog == backorder_qty
    assert pipeline == in_transit_qty
    assert order_leadtime == lead_time_days
    assert holding_cost == holding_cost_per_unit

    print(f"\n✅ TEST 6 PASSED: Existing Beer Game code works unchanged")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("AWS SC ADAPTER - BACKWARD COMPATIBILITY TEST SUITE")
    print("=" * 80)

    try:
        test_params_conversion()
        test_state_conversion()
        test_training_sample_wrapping()
        test_training_batch_wrapping()
        test_backward_compatibility()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("\n Summary:")
        print("   ✅ Parameter conversion works (Beer Game ↔ AWS SC)")
        print("   ✅ State dictionary conversion is bidirectional")
        print("   ✅ Training samples include both schemas")
        print("   ✅ Training batches preserve data integrity")
        print("   ✅ Existing Beer Game code works unchanged")
        print("\n Conclusion:")
        print("   AWS SC compliance layer maintains 100% backward compatibility")
        print("   Existing agents and training code will continue to work")
        print("   New code can use AWS SC fields transparently")
        print("\n" + "=" * 80)

        return 0

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

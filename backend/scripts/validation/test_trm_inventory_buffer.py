#!/usr/bin/env python3
"""C11: Inventory Buffer TRM Validation

Tests InventoryBufferTRM:
- Heuristic rules (stockout, volatility, seasonal, trend, excess, bias)
- Buffer multiplier clamping within effective bounds
- tGNN context modulation of bounds
- Hive signal emission (BUFFER_INCREASED / BUFFER_DECREASED)
- Output structure validation
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test_trm")

from datetime import date, datetime, timedelta

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} — {detail}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"C11: Inventory Buffer TRM Validation")
    print(f"{'='*60}")

    from app.services.powell.inventory_buffer_trm import (
        InventoryBufferTRM, BufferState, BufferAdjustment,
        BufferAdjustmentReason,
    )
    from app.services.powell.engines.buffer_calculator import (
        BufferCalculator, BufferPolicy, DemandStats, PolicyType,
    )
    from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType

    # ----------------------------------------------------------------
    # Test 1: Engine computes service-level buffer
    # ----------------------------------------------------------------
    print("\n--- Test 1: Engine computes SL-based buffer ---")
    calc = BufferCalculator(site_key="SITE_A")
    policy = BufferPolicy(
        policy_type=PolicyType.SL,
        target_service_level=0.95,
    )
    stats = DemandStats(
        avg_daily_demand=100,
        std_daily_demand=20,
        avg_daily_forecast=105,
        lead_time_days=7,
    )
    engine_result = calc.compute_safety_stock("PROD-A", "LOC-1", policy, stats)
    test(
        "Engine computes positive safety stock for SL policy",
        engine_result.safety_stock > 0,
        f"got {engine_result.safety_stock:.1f}",
    )
    test(
        "Reorder point > safety stock",
        engine_result.reorder_point > engine_result.safety_stock,
        f"rop={engine_result.reorder_point:.1f}, ss={engine_result.safety_stock:.1f}",
    )

    # ----------------------------------------------------------------
    # Test 2: TRM heuristic increases buffer on recent stockouts
    # ----------------------------------------------------------------
    print("\n--- Test 2: TRM increases buffer on stockouts ---")
    trm = InventoryBufferTRM(use_heuristic_fallback=True)
    state_stockout = BufferState(
        product_id="PROD-A",
        location_id="LOC-1",
        baseline_ss=100.0,
        baseline_reorder_point=800.0,
        baseline_target_inventory=1000.0,
        policy_type="sl",
        current_on_hand=50.0,
        current_dos=3.0,
        demand_cv=0.20,
        avg_daily_demand=100.0,
        demand_trend=0.0,
        seasonal_index=1.0,
        month_of_year=6,
        recent_stockout_count=3,
        recent_excess_days=0,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj = trm.evaluate(state_stockout)
    test(
        "TRM returns BufferAdjustment",
        isinstance(adj, BufferAdjustment),
        f"got {type(adj).__name__}",
    )
    test(
        "Multiplier > 1.0 for multiple stockouts",
        adj.multiplier > 1.0,
        f"got {adj.multiplier:.2f}",
    )
    test(
        "Reason is RECENT_STOCKOUT",
        adj.reason == BufferAdjustmentReason.RECENT_STOCKOUT,
        f"got {adj.reason}",
    )
    test(
        "Adjusted SS > baseline",
        adj.adjusted_ss > adj.baseline_ss,
        f"adjusted={adj.adjusted_ss:.1f}, baseline={adj.baseline_ss:.1f}",
    )

    # ----------------------------------------------------------------
    # Test 3: TRM heuristic increases buffer on high volatility
    # ----------------------------------------------------------------
    print("\n--- Test 3: TRM increases buffer on high volatility ---")
    state_volatile = BufferState(
        product_id="PROD-B",
        location_id="LOC-1",
        baseline_ss=80.0,
        baseline_reorder_point=600.0,
        baseline_target_inventory=800.0,
        policy_type="sl",
        current_on_hand=200.0,
        current_dos=10.0,
        demand_cv=0.55,
        avg_daily_demand=80.0,
        demand_trend=0.0,
        seasonal_index=1.0,
        month_of_year=3,
        recent_stockout_count=0,
        recent_excess_days=0,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_vol = trm.evaluate(state_volatile)
    test(
        "Multiplier > 1.0 for high volatility",
        adj_vol.multiplier > 1.0,
        f"got {adj_vol.multiplier:.2f}",
    )
    test(
        "Reason is HIGH_VOLATILITY",
        adj_vol.reason == BufferAdjustmentReason.HIGH_VOLATILITY,
        f"got {adj_vol.reason}",
    )

    # ----------------------------------------------------------------
    # Test 4: TRM heuristic decreases buffer on seasonal trough
    # ----------------------------------------------------------------
    print("\n--- Test 4: TRM decreases buffer on seasonal trough ---")
    state_trough = BufferState(
        product_id="PROD-C",
        location_id="LOC-1",
        baseline_ss=120.0,
        baseline_reorder_point=900.0,
        baseline_target_inventory=1100.0,
        policy_type="sl",
        current_on_hand=500.0,
        current_dos=20.0,
        demand_cv=0.15,
        avg_daily_demand=60.0,
        demand_trend=0.0,
        seasonal_index=0.60,
        month_of_year=1,
        recent_stockout_count=0,
        recent_excess_days=0,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_trough = trm.evaluate(state_trough)
    test(
        "Multiplier < 1.0 for seasonal trough",
        adj_trough.multiplier < 1.0,
        f"got {adj_trough.multiplier:.2f}",
    )
    test(
        "Reason is SEASONAL_TROUGH",
        adj_trough.reason == BufferAdjustmentReason.SEASONAL_TROUGH,
        f"got {adj_trough.reason}",
    )

    # ----------------------------------------------------------------
    # Test 5: TRM decreases buffer on excess inventory
    # ----------------------------------------------------------------
    print("\n--- Test 5: TRM decreases buffer on excess inventory ---")
    state_excess = BufferState(
        product_id="PROD-D",
        location_id="LOC-1",
        baseline_ss=100.0,
        baseline_reorder_point=800.0,
        baseline_target_inventory=1000.0,
        policy_type="sl",
        current_on_hand=2000.0,
        current_dos=50.0,
        demand_cv=0.10,
        avg_daily_demand=40.0,
        demand_trend=0.0,
        seasonal_index=1.0,
        month_of_year=9,
        recent_stockout_count=0,
        recent_excess_days=75,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_excess = trm.evaluate(state_excess)
    test(
        "Multiplier < 1.0 for excess inventory",
        adj_excess.multiplier < 1.0,
        f"got {adj_excess.multiplier:.2f}",
    )
    test(
        "Reason is EXCESS_INVENTORY",
        adj_excess.reason == BufferAdjustmentReason.EXCESS_INVENTORY,
        f"got {adj_excess.reason}",
    )

    # ----------------------------------------------------------------
    # Test 6: tGNN context modulates effective bounds
    # ----------------------------------------------------------------
    print("\n--- Test 6: tGNN context modulates effective bounds ---")
    trm_tgnn = InventoryBufferTRM(use_heuristic_fallback=True)
    default_lo, default_hi = trm_tgnn.effective_bounds
    test(
        "Default bounds are [0.5, 2.0]",
        abs(default_lo - 0.5) < 0.01 and abs(default_hi - 2.0) < 0.01,
        f"got [{default_lo}, {default_hi}]",
    )
    trm_tgnn.apply_network_context({"safety_stock_multiplier": 1.5})
    new_lo, new_hi = trm_tgnn.effective_bounds
    test(
        "Bounds shift with tGNN multiplier 1.5",
        abs(new_lo - 0.75) < 0.01 and abs(new_hi - 3.0) < 0.01,
        f"got [{new_lo}, {new_hi}]",
    )

    # ----------------------------------------------------------------
    # Test 7: Hive signal BUFFER_INCREASED on multiplier > 1.05
    # ----------------------------------------------------------------
    print("\n--- Test 7: Hive signal BUFFER_INCREASED ---")
    bus = HiveSignalBus()
    trm_sig = InventoryBufferTRM(use_heuristic_fallback=True)
    trm_sig.signal_bus = bus

    state_increase = BufferState(
        product_id="PROD-E",
        location_id="LOC-1",
        baseline_ss=100.0,
        baseline_reorder_point=800.0,
        baseline_target_inventory=1000.0,
        policy_type="sl",
        current_on_hand=50.0,
        current_dos=2.0,
        demand_cv=0.20,
        avg_daily_demand=100.0,
        demand_trend=0.0,
        seasonal_index=1.0,
        month_of_year=6,
        recent_stockout_count=2,
        recent_excess_days=0,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_sig = trm_sig.evaluate(state_increase)
    test(
        "Multiplier > 1.05 triggers BUFFER_INCREASED",
        adj_sig.multiplier > 1.05,
        f"got {adj_sig.multiplier:.2f}",
    )
    signals = bus.read(consumer_trm="test", types={HiveSignalType.BUFFER_INCREASED})
    test(
        "BUFFER_INCREASED signal emitted",
        len(signals) >= 1,
        f"found {len(signals)} signals",
    )
    if signals:
        test(
            "Signal source is inventory_buffer",
            signals[0].source_trm == "inventory_buffer",
            f"got {signals[0].source_trm}",
        )

    # ----------------------------------------------------------------
    # Test 8: Hive signal BUFFER_DECREASED on multiplier < 0.95
    # ----------------------------------------------------------------
    print("\n--- Test 8: Hive signal BUFFER_DECREASED ---")
    bus2 = HiveSignalBus()
    trm_dec = InventoryBufferTRM(use_heuristic_fallback=True)
    trm_dec.signal_bus = bus2

    state_decrease = BufferState(
        product_id="PROD-F",
        location_id="LOC-1",
        baseline_ss=120.0,
        baseline_reorder_point=900.0,
        baseline_target_inventory=1100.0,
        policy_type="sl",
        current_on_hand=500.0,
        current_dos=20.0,
        demand_cv=0.15,
        avg_daily_demand=60.0,
        demand_trend=0.0,
        seasonal_index=0.60,
        month_of_year=1,
        recent_stockout_count=0,
        recent_excess_days=0,
        forecast_bias=0.0,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_dec = trm_dec.evaluate(state_decrease)
    test(
        "Multiplier < 0.95 triggers BUFFER_DECREASED",
        adj_dec.multiplier < 0.95,
        f"got {adj_dec.multiplier:.2f}",
    )
    signals_dec = bus2.read(consumer_trm="test", types={HiveSignalType.BUFFER_DECREASED})
    test(
        "BUFFER_DECREASED signal emitted",
        len(signals_dec) >= 1,
        f"found {len(signals_dec)} signals",
    )

    # ----------------------------------------------------------------
    # Test 9: Output structure and to_dict
    # ----------------------------------------------------------------
    print("\n--- Test 9: Output structure and to_dict ---")
    test("product_id populated", adj.product_id == "PROD-A", f"got {adj.product_id}")
    test("location_id populated", adj.location_id == "LOC-1", f"got {adj.location_id}")
    test("confidence in [0,1]", 0.0 <= adj.confidence <= 1.0, f"got {adj.confidence}")
    test("description is non-empty", len(adj.description) > 0, "empty description")

    d = adj.to_dict()
    test("to_dict has product_id", "product_id" in d, f"keys: {list(d.keys())}")
    test("to_dict has multiplier", "multiplier" in d, f"keys: {list(d.keys())}")
    test("to_dict has reason as string", isinstance(d.get("reason"), str), f"got {type(d.get('reason'))}")

    # ----------------------------------------------------------------
    # Test 10: No adjustment when all metrics are normal
    # ----------------------------------------------------------------
    print("\n--- Test 10: No adjustment for normal state ---")
    state_normal = BufferState(
        product_id="PROD-G",
        location_id="LOC-1",
        baseline_ss=100.0,
        baseline_reorder_point=800.0,
        baseline_target_inventory=1000.0,
        policy_type="sl",
        current_on_hand=400.0,
        current_dos=15.0,
        demand_cv=0.15,
        avg_daily_demand=100.0,
        demand_trend=0.0,
        seasonal_index=1.0,
        month_of_year=6,
        recent_stockout_count=0,
        recent_excess_days=0,
        forecast_bias=0.05,
        lead_time_days=7.0,
        lead_time_cv=0.1,
    )
    adj_normal = InventoryBufferTRM(use_heuristic_fallback=True).evaluate(state_normal)
    test(
        "Multiplier is 1.0 for normal state",
        abs(adj_normal.multiplier - 1.0) < 0.01,
        f"got {adj_normal.multiplier:.2f}",
    )
    test(
        "Reason is NO_ADJUSTMENT",
        adj_normal.reason == BufferAdjustmentReason.NO_ADJUSTMENT,
        f"got {adj_normal.reason}",
    )

    # ----------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

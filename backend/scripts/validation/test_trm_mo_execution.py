#!/usr/bin/env python3
"""C5: MOExecutionTRM Validation

Tests the MOExecutionTRM: engine evaluation, heuristic fallback with
Glenday/changeover integration, recommendation structure, hive signal
emission (MO_RELEASED / MO_DELAYED), and state encoding.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Minimal env vars to allow import chain (no actual DB connection used)
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
os.environ.setdefault('SECRET_KEY', 'test-key-for-validation')

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
        print(f"  FAIL: {name} -- {detail}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"C5: MOExecutionTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.mo_execution_trm import (
            MOExecutionTRM,
            MOExecutionTRMConfig,
            MOExecutionState,
            MORecommendation,
        )
        from app.services.powell.engines.mo_execution_engine import (
            MOExecutionEngine, MOExecutionConfig, MODecisionType,
        )
        from app.services.powell.hive_signal import (
            HiveSignalBus, HiveSignalType,
        )
        test("Imports successful", True)
    except Exception as e:
        test("Imports successful", False, str(e))
        print(f"\n{'='*60}")
        print(f"Results: {passed} passed, {failed} failed")
        print(f"{'='*60}")
        sys.exit(1)

    # --- Section 1: Ready-to-release MO (high material, ample capacity) ---
    print("\n  -- Ready-to-Release MO --")
    bus = HiveSignalBus()
    trm = MOExecutionTRM(
        site_key="PLANT-001",
        config=MOExecutionTRMConfig(),
        model=None,       # heuristic fallback
        db_session=None,
    )
    trm.signal_bus = bus

    state_ready = MOExecutionState(
        order_id="MO-1001",
        product_id="FG-WIDGET",
        site_id="PLANT-001",
        planned_quantity=500,
        days_until_due=10,
        priority=2,
        material_availability_pct=0.98,
        missing_component_count=0,
        capacity_utilization_pct=0.10,   # low utilization -> high availability (0.90 > 0.80 threshold)
        resource_utilization_pct=0.20,
        setup_time_hours=1.5,
        run_time_hours=8.0,
        queue_depth=3,
        queue_total_hours=20.0,
        avg_yield_pct=0.96,
        avg_setup_overrun_pct=0.05,
        late_completion_rate=0.08,
        customer_order_linked=True,
        runner_category="green",
        changeover_hours_from_current=0.5,
    )

    rec = trm.evaluate_order(state_ready)

    test("Result is MORecommendation",
         isinstance(rec, MORecommendation),
         f"type={type(rec).__name__}")
    test("order_id preserved",
         rec.order_id == "MO-1001",
         f"order_id={rec.order_id}")
    test("decision_type is a string",
         isinstance(rec.decision_type, str) and len(rec.decision_type) > 0,
         f"decision_type={rec.decision_type}")
    test("confidence in [0, 1]",
         0 <= rec.confidence <= 1,
         f"confidence={rec.confidence}")
    test("release_now is True (ready MO)",
         rec.release_now is True,
         f"release_now={rec.release_now}")
    test("recommended_sequence_position >= 0",
         rec.recommended_sequence_position >= 0,
         f"seq={rec.recommended_sequence_position}")
    test("reason non-empty",
         len(rec.reason) > 0,
         f"reason='{rec.reason[:50]}...'")

    # --- Section 2: MO_RELEASED signal ---
    print("\n  -- MO_RELEASED Signal --")
    released_signals = bus.read(
        consumer_trm="atp_executor",
        types={HiveSignalType.MO_RELEASED},
    )
    test("MO_RELEASED signal emitted",
         len(released_signals) >= 1,
         f"count={len(released_signals)}")
    if released_signals:
        sig = released_signals[0]
        test("Signal source is mo_execution",
             sig.source_trm == "mo_execution",
             f"source={sig.source_trm}")
        test("Signal payload has order_id",
             sig.payload.get("order_id") == "MO-1001",
             f"payload={sig.payload}")

    # --- Section 3: Deferred MO (material shortage) ---
    print("\n  -- Deferred MO (Material Shortage) --")
    bus2 = HiveSignalBus()
    trm2 = MOExecutionTRM(
        site_key="PLANT-002",
        config=MOExecutionTRMConfig(),
        model=None,
        db_session=None,
    )
    trm2.signal_bus = bus2

    state_defer = MOExecutionState(
        order_id="MO-1002",
        product_id="FG-GADGET",
        site_id="PLANT-002",
        planned_quantity=200,
        days_until_due=20,
        priority=4,
        material_availability_pct=0.40,  # low material
        missing_component_count=3,
        capacity_utilization_pct=0.90,   # high utilization
        resource_utilization_pct=0.85,
        setup_time_hours=3.0,
        run_time_hours=12.0,
        queue_depth=10,
        queue_total_hours=80.0,
        avg_yield_pct=0.88,
        avg_setup_overrun_pct=0.15,
        late_completion_rate=0.20,
        customer_order_linked=False,
        runner_category="blue",
    )

    rec_defer = trm2.evaluate_order(state_defer)

    test("Deferred MO: release_now is False",
         rec_defer.release_now is False,
         f"release_now={rec_defer.release_now}")
    test("Deferred MO: decision_type is not empty",
         len(rec_defer.decision_type) > 0,
         f"decision_type={rec_defer.decision_type}")

    # --- Section 4: Customer-linked priority boost ---
    print("\n  -- Customer-Linked Priority Boost --")
    state_customer = MOExecutionState(
        order_id="MO-1003",
        product_id="FG-CUSTOM",
        site_id="PLANT-001",
        planned_quantity=100,
        days_until_due=3,     # close to due
        priority=4,           # low priority
        material_availability_pct=0.95,
        missing_component_count=0,
        capacity_utilization_pct=0.50,
        resource_utilization_pct=0.50,
        setup_time_hours=1.0,
        run_time_hours=4.0,
        queue_depth=2,
        queue_total_hours=10.0,
        avg_yield_pct=0.95,
        customer_order_linked=True,  # linked to customer
        runner_category="yellow",
    )
    rec_customer = trm.evaluate_order(state_customer)

    test("Customer-linked: priority_override set to 2",
         rec_customer.priority_override == 2,
         f"priority_override={rec_customer.priority_override}")
    test("Customer-linked: expedite is True",
         rec_customer.expedite is True,
         f"expedite={rec_customer.expedite}")

    # --- Section 5: State encoding ---
    print("\n  -- State Encoding --")
    features = trm._encode_state(state_ready)
    test("State encoding returns 20 floats",
         len(features) == 20,
         f"len={len(features)}")
    test("All features are float",
         all(isinstance(f, float) for f in features),
         "")
    test("Features are normalized (all in [0, 2])",
         all(-0.01 <= f <= 2.01 for f in features),
         f"min={min(features):.3f}, max={max(features):.3f}")

    # Changeover-aware setup time: slot [18]
    test("Setup time slot uses changeover hours (0.5/8.0)",
         abs(features[18] - 0.5 / 8.0) < 0.01,
         f"features[18]={features[18]:.4f}, expected={0.5/8.0:.4f}")

    # Runner category in slot [13]: green=1.0
    test("Runner category slot is 1.0 (green)",
         abs(features[13] - 1.0) < 0.01,
         f"features[13]={features[13]}")

    # --- Section 6: Batch evaluation ---
    print("\n  -- Batch Evaluation --")
    batch_recs = trm.evaluate_batch([state_ready, state_customer])
    test("Batch returns 2 recommendations",
         len(batch_recs) == 2,
         f"got {len(batch_recs)}")
    test("All batch results are MORecommendation",
         all(isinstance(r, MORecommendation) for r in batch_recs),
         "")

    # --- Section 7: Yield-based split suggestion ---
    print("\n  -- Yield-Based Split --")
    state_low_yield = MOExecutionState(
        order_id="MO-1004",
        product_id="FG-FRAGILE",
        site_id="PLANT-001",
        planned_quantity=200,
        days_until_due=15,
        priority=3,
        material_availability_pct=0.95,
        missing_component_count=0,
        capacity_utilization_pct=0.50,
        resource_utilization_pct=0.50,
        setup_time_hours=2.0,
        run_time_hours=6.0,
        queue_depth=2,
        queue_total_hours=12.0,
        avg_yield_pct=0.85,  # low yield triggers overage
        customer_order_linked=False,
        runner_category="red",
    )
    rec_yield = trm.evaluate_order(state_low_yield)
    test("Low yield: split_quantities populated",
         len(rec_yield.split_quantities) > 0,
         f"split_quantities={rec_yield.split_quantities}")
    if rec_yield.split_quantities:
        test("Split qty > planned qty (overage for scrap)",
             rec_yield.split_quantities[0] > state_low_yield.planned_quantity,
             f"split={rec_yield.split_quantities[0]}, planned={state_low_yield.planned_quantity}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

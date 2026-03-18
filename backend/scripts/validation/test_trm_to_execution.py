#!/usr/bin/env python3
"""C6: TOExecutionTRM Validation

Tests the TOExecutionTRM: engine evaluation, heuristic release/expedite
decisions, recommendation structure, hive signal emission
(TO_RELEASED / TO_DELAYED), and state encoding.
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
    print(f"C6: TOExecutionTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.to_execution_trm import (
            TOExecutionTRM,
            TOExecutionTRMConfig,
            TOExecutionState,
            TORecommendation,
        )
        from app.services.powell.engines.to_execution_engine import (
            TOExecutionEngine, TOExecutionConfig, TODecisionType,
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

    # --- Section 1: Release-ready TO (source has stock, dest needs it) ---
    print("\n  -- Release-Ready TO --")
    bus = HiveSignalBus()
    trm = TOExecutionTRM(
        site_key="DC-CENTRAL",
        config=TOExecutionTRMConfig(),
        model=None,       # heuristic fallback
        db_session=None,
    )
    trm.signal_bus = bus

    ship_date = date.today()
    delivery_date = date.today() + timedelta(days=3)

    state_ready = TOExecutionState(
        order_id="TO-2001",
        product_id="SKU-300",
        source_site_id="DC-EAST",
        dest_site_id="DC-WEST",
        planned_qty=150,
        status="DRAFT",
        transportation_mode="truck",
        estimated_transit_days=3,
        source_on_hand=800,
        source_dos=25.0,
        source_committed=100,
        source_safety_stock=50,
        dest_on_hand=40,
        dest_dos=3.0,
        dest_backlog=20,
        dest_safety_stock=60,
        dest_demand_forecast=200,
        days_until_needed=5,
        planned_ship_date=ship_date,
        planned_delivery_date=delivery_date,
        priority=2,
        trigger_reason="mrp_planned",
        transportation_cost=250.0,
        avg_transit_time_days=3.0,
        transit_time_variability=0.2,
        carrier_on_time_pct=0.95,
        lane_criticality=0.7,
        network_congestion_score=0.3,
    )

    rec = trm.evaluate_order(state_ready)

    test("Result is TORecommendation",
         isinstance(rec, TORecommendation),
         f"type={type(rec).__name__}")
    test("order_id preserved",
         rec.order_id == "TO-2001",
         f"order_id={rec.order_id}")
    test("decision_type is a string",
         isinstance(rec.decision_type, str) and len(rec.decision_type) > 0,
         f"decision_type={rec.decision_type}")
    test("confidence in [0, 1]",
         0 <= rec.confidence <= 1,
         f"confidence={rec.confidence}")
    test("release_now is True (dest needs stock, source has plenty)",
         rec.release_now is True,
         f"release_now={rec.release_now}")
    test("reason non-empty",
         len(rec.reason) > 0,
         f"reason='{rec.reason[:50]}...'")
    test("dest_stockout_risk in [0, 1]",
         0 <= rec.dest_stockout_risk <= 1,
         f"dest_stockout_risk={rec.dest_stockout_risk}")
    test("source_depletion_risk in [0, 1]",
         0 <= rec.source_depletion_risk <= 1,
         f"source_depletion_risk={rec.source_depletion_risk}")

    # --- Section 2: TO_RELEASED signal ---
    print("\n  -- TO_RELEASED Signal --")
    released_signals = bus.read(
        consumer_trm="order_tracking",
        types={HiveSignalType.TO_RELEASED},
    )
    test("TO_RELEASED signal emitted",
         len(released_signals) >= 1,
         f"count={len(released_signals)}")
    if released_signals:
        sig = released_signals[0]
        test("Signal source is to_execution",
             sig.source_trm == "to_execution",
             f"source={sig.source_trm}")
        test("Signal payload has source and dest",
             "source" in sig.payload and "dest" in sig.payload,
             f"payload_keys={list(sig.payload.keys())}")
        test("Signal direction is relief",
             sig.direction == "relief",
             f"direction={sig.direction}")

    # Urgency vector
    urg_val, urg_dir, _ = bus.urgency.read("to_execution")
    test("Urgency vector updated for to_execution",
         urg_val > 0,
         f"urgency={urg_val}, direction={urg_dir}")

    # --- Section 3: Deferred TO (source depleted) ---
    print("\n  -- Deferred TO (Source Low) --")
    bus2 = HiveSignalBus()
    trm2 = TOExecutionTRM(
        site_key="DC-SOUTH",
        config=TOExecutionTRMConfig(),
        model=None,
        db_session=None,
    )
    trm2.signal_bus = bus2

    state_defer = TOExecutionState(
        order_id="TO-2002",
        product_id="SKU-301",
        source_site_id="DC-SOUTH",
        dest_site_id="DC-NORTH",
        planned_qty=300,
        status="DRAFT",
        transportation_mode="truck",
        estimated_transit_days=4,
        source_on_hand=100,       # barely enough
        source_dos=3.0,
        source_committed=80,
        source_safety_stock=90,
        dest_on_hand=200,
        dest_dos=15.0,            # dest is OK
        dest_backlog=0,
        dest_safety_stock=40,
        dest_demand_forecast=100,
        days_until_needed=20,     # plenty of time
        priority=4,
        trigger_reason="mrp_planned",
        transportation_cost=400.0,
        avg_transit_time_days=4.0,
        transit_time_variability=0.5,
        carrier_on_time_pct=0.90,
    )

    rec_defer = trm2.evaluate_order(state_defer)
    test("Deferred TO: has valid decision_type",
         len(rec_defer.decision_type) > 0,
         f"decision_type={rec_defer.decision_type}")
    test("Deferred TO: confidence in [0, 1]",
         0 <= rec_defer.confidence <= 1,
         f"confidence={rec_defer.confidence}")

    # --- Section 4: Expedite heuristic (high transit variability, tight timing) ---
    print("\n  -- Expedite Heuristic --")
    state_expedite = TOExecutionState(
        order_id="TO-2003",
        product_id="SKU-302",
        source_site_id="DC-EAST",
        dest_site_id="DC-WEST",
        planned_qty=100,
        status="DRAFT",
        transportation_mode="truck",
        estimated_transit_days=3,
        source_on_hand=500,
        source_dos=20.0,
        source_committed=50,
        dest_on_hand=20,
        dest_dos=2.0,
        dest_backlog=10,       # has backlog
        dest_safety_stock=30,
        dest_demand_forecast=150,
        days_until_needed=4,   # tight: transit_days + 2 = 5, needed in 4
        priority=1,
        trigger_reason="mrp_planned",
        transportation_cost=200.0,
        transit_time_variability=0.5,  # high variability triggers expedite
        carrier_on_time_pct=0.85,
    )
    bus3 = HiveSignalBus()
    trm3 = TOExecutionTRM(
        site_key="DC-EAST",
        config=TOExecutionTRMConfig(),
        model=None,
        db_session=None,
    )
    trm3.signal_bus = bus3
    rec_expedite = trm3.evaluate_order(state_expedite)

    test("Expedite: expedite is True (high variability + tight timing)",
         rec_expedite.expedite is True,
         f"expedite={rec_expedite.expedite}")
    test("Expedite: release_now is True (dest has backlog, source has stock)",
         rec_expedite.release_now is True,
         f"release_now={rec_expedite.release_now}")

    # --- Section 5: State encoding ---
    print("\n  -- State Encoding --")
    features = trm._encode_state(state_ready)
    test("State encoding returns 18 floats",
         len(features) == 18,
         f"len={len(features)}")
    test("All features are float",
         all(isinstance(f, float) for f in features),
         "")
    # Check specific encoded values
    test("Encoded planned_qty = 150/1000 = 0.15",
         abs(features[0] - 0.15) < 0.01,
         f"features[0]={features[0]}")
    test("Encoded priority = 2/5 = 0.4",
         abs(features[2] - 0.4) < 0.01,
         f"features[2]={features[2]}")

    # --- Section 6: Batch evaluation ---
    print("\n  -- Batch Evaluation --")
    batch_recs = trm.evaluate_batch([state_ready, state_expedite])
    test("Batch returns 2 recommendations",
         len(batch_recs) == 2,
         f"got {len(batch_recs)}")
    test("All batch results are TORecommendation",
         all(isinstance(r, TORecommendation) for r in batch_recs),
         "")

    # --- Section 7: Consolidation list type ---
    print("\n  -- Consolidation Structure --")
    test("consolidate_with is a list",
         isinstance(rec.consolidate_with, list),
         f"type={type(rec.consolidate_with)}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

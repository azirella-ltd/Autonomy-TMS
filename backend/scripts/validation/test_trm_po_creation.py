#!/usr/bin/env python3
"""C3: POCreationTRM Validation

Tests the POCreationTRM: order need assessment, heuristic supplier
evaluation, recommendation structure, urgency/trigger classification,
and hive signal emission (PO_EXPEDITE / PO_DEFERRED).
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
    print(f"C3: POCreationTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.po_creation_trm import (
            POCreationTRM,
            POCreationState,
            InventoryPosition,
            SupplierInfo,
            PORecommendation,
            POTriggerReason,
            POUrgency,
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

    # --- Section 1: Critical inventory (below zero available) ---
    print("\n  -- Critical Inventory Scenario --")
    inv_pos_critical = InventoryPosition(
        product_id="MAT-001",
        location_id="PLANT-A",
        on_hand=5,
        in_transit=0,
        on_order=0,
        committed=10,
        backlog=3,
        safety_stock=50,
        reorder_point=100,
        target_inventory=200,
        average_daily_demand=10,
        demand_variability=3,
    )
    test("Critical: available <= 0",
         inv_pos_critical.available <= 0,
         f"available={inv_pos_critical.available}")

    supplier = SupplierInfo(
        supplier_id="SUPPLIER-X",
        product_id="MAT-001",
        lead_time_days=7,
        lead_time_variability=1.5,
        unit_cost=25.0,
        order_cost=100.0,
        min_order_qty=50,
        max_order_qty=5000,
        order_multiple=10,
        on_time_rate=0.92,
        fill_rate=0.97,
        quality_rate=0.99,
        is_available=True,
    )

    state_critical = POCreationState(
        product_id="MAT-001",
        location_id="PLANT-A",
        inventory_position=inv_pos_critical,
        suppliers=[supplier],
        forecast_next_30_days=300,
        forecast_uncertainty=40,
        supply_risk_score=0.3,
        demand_volatility_score=0.2,
    )

    bus = HiveSignalBus()
    trm = POCreationTRM(
        trm_model=None,
        use_heuristic_fallback=True,
    )
    trm.signal_bus = bus

    recs = trm.evaluate_po_need(state_critical)

    test("At least 1 recommendation returned",
         len(recs) >= 1,
         f"got {len(recs)}")

    if recs:
        rec = recs[0]
        test("Recommendation is PORecommendation",
             isinstance(rec, PORecommendation),
             f"type={type(rec).__name__}")
        test("product_id preserved",
             rec.product_id == "MAT-001",
             f"product_id={rec.product_id}")
        test("supplier_id matches",
             rec.supplier_id == "SUPPLIER-X",
             f"supplier_id={rec.supplier_id}")
        test("recommended_qty > 0",
             rec.recommended_qty > 0,
             f"qty={rec.recommended_qty}")
        test("recommended_qty >= min_order_qty (50)",
             rec.recommended_qty >= 50,
             f"qty={rec.recommended_qty}")
        test("recommended_qty is multiple of 10",
             rec.recommended_qty % 10 == 0,
             f"qty={rec.recommended_qty}")
        test("create_now is True (critical/high urgency)",
             rec.create_now is True,
             f"create_now={rec.create_now}")
        test("urgency is CRITICAL or HIGH",
             rec.urgency in (POUrgency.CRITICAL, POUrgency.HIGH),
             f"urgency={rec.urgency}")
        test("trigger_reason is EXPEDITE (available <= 0)",
             rec.trigger_reason == POTriggerReason.EXPEDITE,
             f"trigger={rec.trigger_reason}")
        test("confidence in [0, 1]",
             0 <= rec.confidence <= 1,
             f"confidence={rec.confidence}")
        test("expected_cost > 0",
             rec.expected_cost > 0,
             f"cost={rec.expected_cost}")
        test("expected_receipt_date is valid date string",
             len(rec.expected_receipt_date) == 10,
             f"date={rec.expected_receipt_date}")
        test("reasoning non-empty",
             len(rec.reasoning) > 0,
             f"reasoning='{rec.reasoning[:40]}...'")

    # --- Section 2: Signal emission on critical PO ---
    print("\n  -- Signal Emission (Critical) --")
    expedite_signals = bus.read(
        consumer_trm="atp_executor",
        types={HiveSignalType.PO_EXPEDITE},
    )
    test("PO_EXPEDITE signal emitted",
         len(expedite_signals) >= 1,
         f"count={len(expedite_signals)}")
    if expedite_signals:
        sig = expedite_signals[0]
        test("Signal source is po_creation",
             sig.source_trm == "po_creation",
             f"source={sig.source_trm}")
        test("Signal urgency >= 0.6 (high/critical)",
             sig.urgency >= 0.6,
             f"urgency={sig.urgency}")

    # --- Section 3: Normal reorder point scenario ---
    print("\n  -- Reorder Point Scenario --")
    # inventory_position=70 is > safety_stock=50 but <= reorder_point=100
    # so triggers REORDER_POINT (NORMAL), not INVENTORY_BUFFER (HIGH)
    inv_pos_normal = InventoryPosition(
        product_id="MAT-002",
        location_id="PLANT-B",
        on_hand=70,
        in_transit=0,
        on_order=0,
        committed=0,
        backlog=0,
        safety_stock=50,
        reorder_point=100,
        target_inventory=200,
        average_daily_demand=8,
        demand_variability=2,
    )
    test("Normal: at reorder point",
         inv_pos_normal.inventory_position <= inv_pos_normal.reorder_point,
         f"pos={inv_pos_normal.inventory_position}, ROP={inv_pos_normal.reorder_point}")

    supplier_b = SupplierInfo(
        supplier_id="SUPPLIER-Y",
        product_id="MAT-002",
        lead_time_days=5,
        lead_time_variability=1.0,
        unit_cost=15.0,
        order_cost=50.0,
        min_order_qty=20,
        max_order_qty=2000,
        order_multiple=5,
    )
    state_normal = POCreationState(
        product_id="MAT-002",
        location_id="PLANT-B",
        inventory_position=inv_pos_normal,
        suppliers=[supplier_b],
        forecast_next_30_days=240,
        forecast_uncertainty=30,
    )
    bus2 = HiveSignalBus()
    trm2 = POCreationTRM(trm_model=None, use_heuristic_fallback=True)
    trm2.signal_bus = bus2
    recs_normal = trm2.evaluate_po_need(state_normal)
    test("Normal scenario: recommendation returned",
         len(recs_normal) >= 1,
         f"got {len(recs_normal)}")
    if recs_normal:
        rec_n = recs_normal[0]
        test("Normal: trigger is REORDER_POINT",
             rec_n.trigger_reason == POTriggerReason.REORDER_POINT,
             f"trigger={rec_n.trigger_reason}")
        test("Normal: urgency is NORMAL",
             rec_n.urgency == POUrgency.NORMAL,
             f"urgency={rec_n.urgency}")
        test("Normal: create_now is False",
             rec_n.create_now is False,
             f"create_now={rec_n.create_now}")

    # PO_DEFERRED signal for normal urgency
    deferred_signals = bus2.read(
        consumer_trm="atp_executor",
        types={HiveSignalType.PO_DEFERRED},
    )
    test("PO_DEFERRED signal emitted for normal urgency",
         len(deferred_signals) >= 1,
         f"count={len(deferred_signals)}")

    # --- Section 4: No PO needed when well-stocked ---
    print("\n  -- No PO Needed --")
    inv_pos_full = InventoryPosition(
        product_id="MAT-003",
        location_id="PLANT-C",
        on_hand=500,
        in_transit=100,
        on_order=200,
        committed=50,
        backlog=0,
        safety_stock=30,
        reorder_point=100,
        target_inventory=200,
        average_daily_demand=5,
        demand_variability=1,
    )
    state_full = POCreationState(
        product_id="MAT-003",
        location_id="PLANT-C",
        inventory_position=inv_pos_full,
        suppliers=[supplier_b],
        forecast_next_30_days=150,
        forecast_uncertainty=15,
    )
    recs_none = trm.evaluate_po_need(state_full)
    test("No PO recommendation when well-stocked",
         len(recs_none) == 0,
         f"got {len(recs_none)}")

    # --- Section 5: to_dict serialization ---
    print("\n  -- Serialization --")
    if recs:
        d = recs[0].to_dict()
        test("to_dict has product_id", "product_id" in d, "")
        test("to_dict has supplier_id", "supplier_id" in d, "")
        test("to_dict has urgency string", isinstance(d.get("urgency"), str), "")
        test("to_dict has trigger_reason string",
             isinstance(d.get("trigger_reason"), str), "")
        test("to_dict has confidence", "confidence" in d, "")

    # --- Section 6: Supplier feature vector ---
    print("\n  -- Supplier Feature Vector --")
    features = state_critical.get_supplier_features("SUPPLIER-X")
    test("Feature vector length = 17 (8+5+4)",
         len(features) == 17,
         f"len={len(features)}")
    test("Feature vector dtype is float32",
         str(features.dtype) == "float32",
         f"dtype={features.dtype}")

    # Non-existent supplier returns zeros
    features_none = state_critical.get_supplier_features("NONEXISTENT")
    test("Unknown supplier returns zero vector",
         all(f == 0.0 for f in features_none),
         "")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

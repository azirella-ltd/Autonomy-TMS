#!/usr/bin/env python3
"""C4: OrderTrackingTRM Validation

Tests the OrderTrackingTRM: late delivery detection, severity
classification, recommended actions, hive signal emission
(ORDER_EXCEPTION), and batch evaluation.
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
    print(f"C4: OrderTrackingTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.order_tracking_trm import (
            OrderTrackingTRM,
            OrderState,
            OrderType,
            OrderStatus,
            ExceptionDetection,
            ExceptionType,
            ExceptionSeverity,
            RecommendedAction,
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

    # --- Section 1: Late delivery detection ---
    print("\n  -- Late Delivery Detection --")
    # Order expected 5 days ago (late)
    past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    created_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")

    late_order = OrderState(
        order_id="PO-500",
        order_type=OrderType.PURCHASE_ORDER,
        status=OrderStatus.IN_TRANSIT,
        created_date=created_date,
        expected_date=past_date,
        ordered_qty=100,
        received_qty=0,
        remaining_qty=100,
        product_id="MAT-010",
        from_location="SUPPLIER-HQ",
        to_location="PLANT-A",
        partner_id="SUPP-001",
        partner_on_time_rate=0.80,
        partner_fill_rate=0.95,
        typical_transit_days=5,
    )

    test("Late order: days_until_expected < 0",
         late_order.days_until_expected < 0,
         f"days_until_expected={late_order.days_until_expected}")

    bus = HiveSignalBus()
    trm = OrderTrackingTRM(
        trm_model=None,
        use_heuristic_fallback=True,
        late_threshold_days=2.0,
    )
    trm.signal_bus = bus

    result = trm.evaluate_order(late_order)

    test("Result is ExceptionDetection",
         isinstance(result, ExceptionDetection),
         f"type={type(result).__name__}")
    test("Exception type is not NO_EXCEPTION (late/stuck)",
         result.exception_type != ExceptionType.NO_EXCEPTION,
         f"exception_type={result.exception_type}")
    test("Severity is HIGH or CRITICAL",
         result.severity in (ExceptionSeverity.HIGH, ExceptionSeverity.CRITICAL),
         f"severity={result.severity}")
    test("Recommended action is not NO_ACTION",
         result.recommended_action != RecommendedAction.NO_ACTION,
         f"action={result.recommended_action}")
    test("order_id preserved",
         result.order_id == "PO-500",
         f"order_id={result.order_id}")
    test("description non-empty",
         len(result.description) > 0,
         f"description='{result.description[:50]}...'")
    test("confidence in [0, 1]",
         0 <= result.confidence <= 1,
         f"confidence={result.confidence}")

    # --- Section 2: Signal emission for exception ---
    print("\n  -- Signal Emission --")
    exc_signals = bus.read(
        consumer_trm="po_creation",
        types={HiveSignalType.ORDER_EXCEPTION},
    )
    test("ORDER_EXCEPTION signal emitted",
         len(exc_signals) >= 1,
         f"count={len(exc_signals)}")
    if exc_signals:
        sig = exc_signals[0]
        test("Signal source is order_tracking",
             sig.source_trm == "order_tracking",
             f"source={sig.source_trm}")
        test("Signal urgency > 0.5 (HIGH/CRITICAL)",
             sig.urgency > 0.5,
             f"urgency={sig.urgency}")
        test("Signal payload has exception_type",
             "exception_type" in sig.payload,
             f"payload={sig.payload}")

    # --- Section 3: Urgency vector ---
    print("\n  -- Urgency Vector --")
    urg_val, urg_dir, _ = bus.urgency.read("order_tracking")
    test("Urgency vector updated",
         urg_val > 0,
         f"urgency={urg_val}, direction={urg_dir}")
    test("Direction is 'risk'",
         urg_dir == "risk",
         f"direction={urg_dir}")

    # --- Section 4: Normal order (no exception) ---
    print("\n  -- Normal Order (No Exception) --")
    # Use 2 days in future (within early_threshold=3) so engine sees it as normal
    future_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    # Created recently so days_since_created doesn't trigger stuck_in_transit
    recent_created = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    normal_order = OrderState(
        order_id="PO-501",
        order_type=OrderType.PURCHASE_ORDER,
        status=OrderStatus.CONFIRMED,
        created_date=recent_created,
        expected_date=future_date,
        ordered_qty=50,
        received_qty=0,
        remaining_qty=50,
        product_id="MAT-011",
        from_location="SUPPLIER-HQ",
        to_location="PLANT-A",
        partner_id="SUPP-002",
        partner_on_time_rate=0.98,
        partner_fill_rate=0.99,
        typical_transit_days=5,
    )
    bus2 = HiveSignalBus()
    trm2 = OrderTrackingTRM(trm_model=None, use_heuristic_fallback=True)
    trm2.signal_bus = bus2
    result_normal = trm2.evaluate_order(normal_order)

    test("Normal order: exception_type is NO_EXCEPTION",
         result_normal.exception_type == ExceptionType.NO_EXCEPTION,
         f"exception_type={result_normal.exception_type}")
    test("Normal order: recommended_action is NO_ACTION",
         result_normal.recommended_action == RecommendedAction.NO_ACTION,
         f"action={result_normal.recommended_action}")

    # No signal emitted for normal orders
    exc_signals_normal = bus2.read(
        consumer_trm="po_creation",
        types={HiveSignalType.ORDER_EXCEPTION},
    )
    test("No ORDER_EXCEPTION signal for normal order",
         len(exc_signals_normal) == 0,
         f"count={len(exc_signals_normal)}")

    # --- Section 5: Quantity shortage detection ---
    print("\n  -- Quantity Shortage --")
    qty_short_order = OrderState(
        order_id="PO-502",
        order_type=OrderType.PURCHASE_ORDER,
        status=OrderStatus.PARTIALLY_RECEIVED,
        created_date=created_date,
        expected_date=past_date,
        ordered_qty=100,
        received_qty=80,
        remaining_qty=20,
        expected_unit_price=10.0,
        actual_unit_price=10.0,
        product_id="MAT-012",
        from_location="SUPPLIER-HQ",
        to_location="PLANT-A",
        partner_on_time_rate=0.90,
        partner_fill_rate=0.85,
        typical_transit_days=5,
    )
    test("Shortage order: fill_rate < 1.0",
         qty_short_order.fill_rate < 1.0,
         f"fill_rate={qty_short_order.fill_rate}")

    result_short = trm.evaluate_order(qty_short_order)
    test("Shortage detected (not NO_EXCEPTION)",
         result_short.exception_type != ExceptionType.NO_EXCEPTION,
         f"exception_type={result_short.exception_type}")

    # --- Section 6: Batch evaluation ---
    print("\n  -- Batch Evaluation --")
    orders = [late_order, normal_order, qty_short_order]
    batch_results = trm.evaluate_orders_batch(orders)
    test("Batch returns same count as input",
         len(batch_results) == 3,
         f"got {len(batch_results)}")
    test("All results are ExceptionDetection",
         all(isinstance(r, ExceptionDetection) for r in batch_results),
         "")

    # --- Section 7: Feature vector ---
    print("\n  -- Feature Vector --")
    features = late_order.to_features()
    test("Feature vector length = 15",
         len(features) == 15,
         f"len={len(features)}")
    test("Feature vector dtype is float32",
         str(features.dtype) == "float32",
         f"dtype={features.dtype}")

    # --- Section 8: to_dict serialization ---
    print("\n  -- Serialization --")
    d = result.to_dict()
    test("to_dict has order_id", "order_id" in d, "")
    test("to_dict has exception_type string",
         isinstance(d.get("exception_type"), str), "")
    test("to_dict has severity string",
         isinstance(d.get("severity"), str), "")
    test("to_dict has recommended_action string",
         isinstance(d.get("recommended_action"), str), "")
    test("to_dict has confidence", "confidence" in d, "")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

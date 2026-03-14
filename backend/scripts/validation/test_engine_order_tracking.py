#!/usr/bin/env python3
"""A4: Order Tracking Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Direct module load to avoid heavy app init chain via powell/__init__.py
_engine_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines', 'order_tracking_engine.py')
_spec = importlib.util.spec_from_file_location("order_tracking_engine", os.path.abspath(_engine_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
OrderTrackingEngine = _mod.OrderTrackingEngine
OrderTrackingConfig = _mod.OrderTrackingConfig
OrderSnapshot = _mod.OrderSnapshot
ExceptionResult = _mod.ExceptionResult

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


# ---------------------------------------------------------------------------
# Test 1: Late delivery detection
# ---------------------------------------------------------------------------
def test_late_delivery():
    print("\n[Test 1] Late delivery detection")
    config = OrderTrackingConfig(late_threshold_days=2.0)
    engine = OrderTrackingEngine(config=config)

    order = OrderSnapshot(
        order_id="PO-1",
        order_type="purchase_order",
        status="in_transit",
        days_until_expected=-3,  # 3 days past due
        days_since_created=10,
        typical_transit_days=5,
        ordered_qty=100,
        received_qty=0,
        expected_unit_price=10.0,
        actual_unit_price=10.0,
        partner_on_time_rate=0.85,
        partner_fill_rate=0.90,
    )

    result = engine.evaluate_order(order)
    test("Exception type is late_delivery",
         result.exception_type == "late_delivery",
         f"type={result.exception_type}")
    test("Severity is warning or higher",
         result.severity in ("warning", "high", "critical"),
         f"severity={result.severity}")
    test("Recommended action is expedite",
         result.recommended_action == "expedite",
         f"action={result.recommended_action}")
    test("Confidence is 1.0 (deterministic)",
         result.confidence == 1.0,
         f"confidence={result.confidence}")

    # Very late (>7 days) should be critical
    very_late = OrderSnapshot(
        order_id="PO-2", order_type="purchase_order", status="in_transit",
        days_until_expected=-10, days_since_created=15,
        typical_transit_days=5, ordered_qty=100,
    )
    result_vl = engine.evaluate_order(very_late)
    test("Very late (10 days) is critical severity",
         result_vl.severity == "critical",
         f"severity={result_vl.severity}")
    test("Very late recommends find_alternate",
         result_vl.recommended_action == "find_alternate",
         f"action={result_vl.recommended_action}")


# ---------------------------------------------------------------------------
# Test 2: Quantity variance
# ---------------------------------------------------------------------------
def test_quantity_variance():
    print("\n[Test 2] Quantity variance detection")
    config = OrderTrackingConfig(quantity_variance_threshold=0.05)
    engine = OrderTrackingEngine(config=config)

    order = OrderSnapshot(
        order_id="PO-3",
        order_type="purchase_order",
        status="partially_received",
        days_until_expected=0,
        days_since_created=7,
        typical_transit_days=5,
        ordered_qty=100,
        received_qty=85,  # 15% shortage
        expected_unit_price=10.0,
        actual_unit_price=10.0,
    )

    result = engine.evaluate_order(order)
    test("Exception type is quantity_shortage",
         result.exception_type == "quantity_shortage",
         f"type={result.exception_type}")
    test("Fill rate computed correctly",
         abs(order.fill_rate - 0.85) < 0.001,
         f"fill_rate={order.fill_rate}")
    test("Severity is high (15% shortage > 10%)",
         result.severity == "high",
         f"severity={result.severity}")

    # Small shortage (6%) should be warning
    small_shortage = OrderSnapshot(
        order_id="PO-4", order_type="purchase_order",
        status="partially_received",
        days_until_expected=0, days_since_created=7,
        typical_transit_days=5, ordered_qty=100, received_qty=94,
    )
    result_ss = engine.evaluate_order(small_shortage)
    test("Small shortage (6%) detected",
         result_ss.exception_type == "quantity_shortage",
         f"type={result_ss.exception_type}")
    test("Small shortage severity is warning",
         result_ss.severity == "warning",
         f"severity={result_ss.severity}")


# ---------------------------------------------------------------------------
# Test 3: Price variance
# ---------------------------------------------------------------------------
def test_price_variance():
    print("\n[Test 3] Price variance detection")
    config = OrderTrackingConfig(price_variance_threshold=0.10)
    engine = OrderTrackingEngine(config=config)

    order = OrderSnapshot(
        order_id="PO-5",
        order_type="purchase_order",
        status="received",
        days_until_expected=0,
        days_since_created=7,
        typical_transit_days=5,
        ordered_qty=100,
        received_qty=100,  # Full receipt, so no qty exception
        expected_unit_price=10.0,
        actual_unit_price=11.5,  # 15% over
    )

    result = engine.evaluate_order(order)
    test("Exception type is price_variance",
         result.exception_type == "price_variance",
         f"type={result.exception_type}")
    test("Price variance computed correctly",
         abs(order.price_variance_pct - 0.15) < 0.001,
         f"variance={order.price_variance_pct}")
    test("Severity is warning",
         result.severity == "warning",
         f"severity={result.severity}")
    test("Recommended action is price_negotiation",
         result.recommended_action == "price_negotiation",
         f"action={result.recommended_action}")

    # Price within threshold should not trigger
    ok_price = OrderSnapshot(
        order_id="PO-6", order_type="purchase_order", status="received",
        days_until_expected=0, days_since_created=7,
        typical_transit_days=5, ordered_qty=100, received_qty=100,
        expected_unit_price=10.0, actual_unit_price=10.5,  # 5% -- within 10%
    )
    result_ok = engine.evaluate_order(ok_price)
    test("5% price variance (within 10% threshold) is no_exception",
         result_ok.exception_type == "no_exception",
         f"type={result_ok.exception_type}")


# ---------------------------------------------------------------------------
# Test 4: No exception on healthy order
# ---------------------------------------------------------------------------
def test_healthy_order():
    print("\n[Test 4] No exception on healthy order")
    engine = OrderTrackingEngine(config=OrderTrackingConfig())

    order = OrderSnapshot(
        order_id="PO-7",
        order_type="purchase_order",
        status="in_transit",
        days_until_expected=2,  # Arriving in 2 days (on time)
        days_since_created=3,
        typical_transit_days=5,
        ordered_qty=100,
        received_qty=0,
        expected_unit_price=10.0,
        actual_unit_price=10.0,
        partner_on_time_rate=0.95,
        partner_fill_rate=0.98,
    )

    result = engine.evaluate_order(order)
    test("Exception type is no_exception",
         result.exception_type == "no_exception",
         f"type={result.exception_type}")
    test("Severity is info",
         result.severity == "info",
         f"severity={result.severity}")
    test("Recommended action is no_action",
         result.recommended_action == "no_action",
         f"action={result.recommended_action}")

    # evaluate_batch should filter out healthy orders
    results = engine.evaluate_batch([order])
    test("Batch evaluation excludes healthy orders",
         len(results) == 0,
         f"got {len(results)} exceptions")


# ---------------------------------------------------------------------------
# Test 5: Stuck in transit
# ---------------------------------------------------------------------------
def test_stuck_in_transit():
    print("\n[Test 5] Stuck in transit detection")
    config = OrderTrackingConfig(stuck_transit_multiplier=2.0)
    engine = OrderTrackingEngine(config=config)

    order = OrderSnapshot(
        order_id="PO-8",
        order_type="purchase_order",
        status="in_transit",
        days_until_expected=-5,
        days_since_created=15,    # 15 days in transit
        typical_transit_days=5,   # Typical is 5 days -> 2x = 10 threshold
        ordered_qty=100,
        received_qty=0,
        expected_unit_price=10.0,
        actual_unit_price=10.0,
    )

    result = engine.evaluate_order(order)
    test("Exception type is stuck_in_transit",
         result.exception_type == "stuck_in_transit",
         f"type={result.exception_type}")
    test("Severity is critical",
         result.severity == "critical",
         f"severity={result.severity}")
    test("Recommended action is find_alternate",
         result.recommended_action == "find_alternate",
         f"action={result.recommended_action}")

    # Just under threshold should not be stuck (days_since_created = 9 < 10)
    not_stuck = OrderSnapshot(
        order_id="PO-9", order_type="purchase_order", status="in_transit",
        days_until_expected=1, days_since_created=9,
        typical_transit_days=5, ordered_qty=100,
    )
    result_ns = engine.evaluate_order(not_stuck)
    test("Order at 9 days (below 2x threshold of 10) is not stuck",
         result_ns.exception_type != "stuck_in_transit",
         f"type={result_ns.exception_type}")

    # Stuck takes priority over late (highest priority check)
    # Order is both stuck AND late
    test("Stuck in transit takes priority over late delivery",
         result.exception_type == "stuck_in_transit",
         f"type={result.exception_type} (should not be late_delivery)")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A4: Order Tracking Engine Validation")
    print(f"{'='*60}")

    test_late_delivery()
    test_quantity_variance()
    test_price_variance()
    test_healthy_order()
    test_stuck_in_transit()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

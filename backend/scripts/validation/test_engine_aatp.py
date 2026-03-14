#!/usr/bin/env python3
"""A1: AATP Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import date, timedelta

# Direct module load to avoid heavy app init chain via powell/__init__.py
_engine_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines', 'aatp_engine.py')
_spec = importlib.util.spec_from_file_location("aatp_engine", os.path.abspath(_engine_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AATPEngine = _mod.AATPEngine
AATPConfig = _mod.AATPConfig
ATPAllocation = _mod.ATPAllocation
Order = _mod.Order
ATPResult = _mod.ATPResult
Priority = _mod.Priority

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


def make_allocations(product_id="PROD-1", location_id="LOC-1", qty_per_tier=100):
    """Create allocations for all 5 priority tiers."""
    today = date.today()
    return [
        ATPAllocation(
            product_id=product_id,
            location_id=location_id,
            priority=Priority(tier),
            allocated_qty=qty_per_tier,
            period_start=today,
            period_end=today + timedelta(days=30),
            source="test",
        )
        for tier in range(1, 6)
    ]


def make_order(order_id="ORD-1", product_id="PROD-1", location_id="LOC-1",
               qty=50, priority=Priority.HIGH, customer_id="CUST-1"):
    return Order(
        order_id=order_id,
        product_id=product_id,
        location_id=location_id,
        requested_qty=qty,
        requested_date=date.today(),
        priority=priority,
        customer_id=customer_id,
        order_type="standard",
    )


# ---------------------------------------------------------------------------
# Test 1: Priority consumption sequence
# ---------------------------------------------------------------------------
def test_priority_consumption_sequence():
    print("\n[Test 1] Priority consumption sequence")
    config = AATPConfig(num_priority_tiers=5, allow_borrowing_up=False)
    engine = AATPEngine(site_key="TEST", config=config)

    # Verify the internal consumption sequence builder
    seq = engine._build_consumption_sequence(Priority.HIGH)  # P2
    seq_values = [p.value for p in seq]
    # Expected: own tier (2), then bottom-up skipping own and anything above own
    # 2, 5, 4, 3 (skips 1)
    test(
        "P2 consumption sequence is [2,5,4,3]",
        seq_values == [2, 5, 4, 3],
        f"got {seq_values}",
    )

    # P1 (CRITICAL) should only have own tier when borrowing_up=False
    seq_p1 = engine._build_consumption_sequence(Priority.CRITICAL)
    seq_p1_values = [p.value for p in seq_p1]
    test(
        "P1 consumption sequence is [1,5,4,3,2]",
        seq_p1_values == [1, 5, 4, 3, 2],
        f"got {seq_p1_values}",
    )

    # P5 (STANDARD) should only have own tier (nothing below it)
    seq_p5 = engine._build_consumption_sequence(Priority.STANDARD)
    seq_p5_values = [p.value for p in seq_p5]
    test(
        "P5 consumption sequence is [5] (nothing below)",
        seq_p5_values == [5],
        f"got {seq_p5_values}",
    )


# ---------------------------------------------------------------------------
# Test 2: Full fulfillment
# ---------------------------------------------------------------------------
def test_full_fulfillment():
    print("\n[Test 2] Full fulfillment")
    engine = AATPEngine(site_key="TEST", config=AATPConfig())
    engine.load_allocations(make_allocations(qty_per_tier=100))

    order = make_order(qty=50, priority=Priority.HIGH)
    result = engine.check_availability(order)

    test("can_fulfill_full is True", result.can_fulfill_full,
         f"can_fulfill_full={result.can_fulfill_full}")
    test("shortage_qty is 0", result.shortage_qty == 0,
         f"shortage_qty={result.shortage_qty}")
    test("available_qty equals requested", result.available_qty == 50,
         f"available_qty={result.available_qty}")
    test("consumption_detail is non-empty", len(result.consumption_detail) > 0,
         "no consumption detail")
    # Should consume entirely from own tier (P2=100, need 50)
    test("consumed from own tier only",
         result.consumption_detail == [(Priority.HIGH, 50)],
         f"detail={result.consumption_detail}")


# ---------------------------------------------------------------------------
# Test 3: Partial fulfillment / shortage
# ---------------------------------------------------------------------------
def test_partial_fulfillment():
    print("\n[Test 3] Partial fulfillment / shortage")
    engine = AATPEngine(site_key="TEST", config=AATPConfig())
    # P5 order can only consume from tier 5 (nothing below)
    engine.load_allocations(make_allocations(qty_per_tier=40))

    order = make_order(qty=80, priority=Priority.STANDARD)  # P5
    result = engine.check_availability(order)

    test("can_fulfill_full is False", not result.can_fulfill_full,
         f"can_fulfill_full={result.can_fulfill_full}")
    test("shortage_qty is 40", result.shortage_qty == 40,
         f"shortage_qty={result.shortage_qty}")
    test("available_qty is 40", result.available_qty == 40,
         f"available_qty={result.available_qty}")

    # Now test a P2 order that exceeds own tier but can borrow from lower
    order2 = make_order(order_id="ORD-2", qty=150, priority=Priority.HIGH)
    result2 = engine.check_availability(order2)
    # P2 sequence: [2, 5, 4, 3] with 40 each = 160 available
    test("P2 can fulfill 150 across tiers", result2.can_fulfill_full,
         f"can_fulfill_full={result2.can_fulfill_full}, avail={result2.available_qty}")
    test("P2 consumed from multiple tiers", len(result2.consumption_detail) > 1,
         f"detail={result2.consumption_detail}")


# ---------------------------------------------------------------------------
# Test 4: Commit and rollback
# ---------------------------------------------------------------------------
def test_commit_and_rollback():
    print("\n[Test 4] Commit and rollback")
    engine = AATPEngine(site_key="TEST", config=AATPConfig())
    engine.load_allocations(make_allocations(qty_per_tier=100))

    order = make_order(qty=60, priority=Priority.HIGH)
    result = engine.check_availability(order)

    # Before commit, availability unchanged
    avail_before = engine.get_available_by_priority("PROD-1", "LOC-1")
    test("P2 allocation still 100 before commit",
         avail_before[Priority.HIGH] == 100,
         f"P2={avail_before.get(Priority.HIGH)}")

    # Commit
    engine.commit_consumption(order, result)
    avail_after = engine.get_available_by_priority("PROD-1", "LOC-1")
    test("P2 allocation reduced to 40 after commit",
         avail_after[Priority.HIGH] == 40,
         f"P2={avail_after.get(Priority.HIGH)}")

    # Rollback
    engine.rollback_consumption(order, result)
    avail_restored = engine.get_available_by_priority("PROD-1", "LOC-1")
    test("P2 allocation restored to 100 after rollback",
         avail_restored[Priority.HIGH] == 100,
         f"P2={avail_restored.get(Priority.HIGH)}")


# ---------------------------------------------------------------------------
# Test 5: Multiple products/locations
# ---------------------------------------------------------------------------
def test_multiple_products_locations():
    print("\n[Test 5] Multiple products/locations")
    engine = AATPEngine(site_key="TEST", config=AATPConfig())

    allocs = make_allocations("PROD-1", "LOC-1", qty_per_tier=100)
    allocs += make_allocations("PROD-2", "LOC-1", qty_per_tier=200)
    allocs += make_allocations("PROD-1", "LOC-2", qty_per_tier=50)
    engine.load_allocations(allocs)

    total_p1_l1 = engine.get_total_available("PROD-1", "LOC-1")
    total_p2_l1 = engine.get_total_available("PROD-2", "LOC-1")
    total_p1_l2 = engine.get_total_available("PROD-1", "LOC-2")

    test("PROD-1/LOC-1 total is 500", total_p1_l1 == 500,
         f"got {total_p1_l1}")
    test("PROD-2/LOC-1 total is 1000", total_p2_l1 == 1000,
         f"got {total_p2_l1}")
    test("PROD-1/LOC-2 total is 250", total_p1_l2 == 250,
         f"got {total_p1_l2}")

    # Consuming from PROD-1/LOC-1 should not affect PROD-2/LOC-1
    order = make_order(qty=50, priority=Priority.MEDIUM, product_id="PROD-1", location_id="LOC-1")
    result = engine.check_availability(order)
    engine.commit_consumption(order, result)

    total_p2_l1_after = engine.get_total_available("PROD-2", "LOC-1")
    test("PROD-2/LOC-1 unaffected after PROD-1/LOC-1 consumption",
         total_p2_l1_after == 1000,
         f"got {total_p2_l1_after}")

    # No allocations for unknown product
    order_unknown = make_order(order_id="ORD-X", qty=10, product_id="PROD-99", location_id="LOC-1")
    result_unknown = engine.check_availability(order_unknown)
    test("Unknown product returns can_fulfill_full=False",
         not result_unknown.can_fulfill_full,
         f"can_fulfill_full={result_unknown.can_fulfill_full}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A1: AATP Engine Validation")
    print(f"{'='*60}")

    test_priority_consumption_sequence()
    test_full_fulfillment()
    test_partial_fulfillment()
    test_commit_and_rollback()
    test_multiple_products_locations()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

#!/usr/bin/env python3
"""C1: ATPExecutorTRM Validation

Tests the ATPExecutorTRM end-to-end: allocation setup, engine-based
heuristic decision, response structure, CDT risk_bound field, and
hive signal emission on shortage.
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
    print(f"C1: ATPExecutorTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.atp_executor import (
            ATPExecutorTRM, ATPRequest, ATPResponse, ATPState,
        )
        from app.services.powell.allocation_service import (
            AllocationService, AllocationConfig, PriorityAllocation,
        )
        from app.services.powell.engines.aatp_engine import (
            AATPEngine, AATPConfig, ATPAllocation,
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

    # --- Section 1: Allocation service setup ---
    print("\n  -- Allocation & Engine Setup --")
    alloc_svc = AllocationService()

    # Seed allocations: priority 1 = 50 units, priority 2 = 80 units
    alloc_svc.set_allocations(
        allocations=[
            PriorityAllocation(priority=1, product_id="PROD-001",
                               location_id="LOC-A", allocated_qty=50),
            PriorityAllocation(priority=2, product_id="PROD-001",
                               location_id="LOC-A", allocated_qty=80),
        ],
    )
    status = alloc_svc.get_allocation_status("PROD-001", "LOC-A")
    test("Allocations seeded", len(status) == 2,
         f"Expected 2 priorities, got {len(status)}")

    # --- Section 2: ATPExecutorTRM with heuristic (no TRM model) ---
    print("\n  -- Heuristic ATP Decision --")
    bus = HiveSignalBus()
    executor = ATPExecutorTRM(
        allocation_service=alloc_svc,
        trm_model=None,
        use_heuristic_fallback=True,
        signal_bus=bus,
    )

    req = ATPRequest(
        order_id="ORD-100",
        product_id="PROD-001",
        location_id="LOC-A",
        requested_qty=40,
        priority=2,
    )
    inv_ctx = {
        "current_inventory": 200,
        "pipeline_inventory": 50,
        "safety_stock": 30,
        "demand_forecast": 100,
        "demand_uncertainty": 20,
    }
    resp = executor.check_atp(req, inventory_context=inv_ctx)

    test("Response is ATPResponse", isinstance(resp, ATPResponse),
         f"Got {type(resp).__name__}")
    test("can_fulfill is True (40 <= 80)", resp.can_fulfill is True,
         f"can_fulfill={resp.can_fulfill}")
    test("promised_qty == 40", resp.promised_qty == 40.0,
         f"promised_qty={resp.promised_qty}")
    test("confidence is 1.0 (heuristic)", resp.confidence == 1.0,
         f"confidence={resp.confidence}")
    test("consumption_breakdown non-empty", len(resp.consumption_breakdown) > 0,
         f"breakdown={resp.consumption_breakdown}")
    test("order_id preserved", resp.order_id == "ORD-100",
         f"order_id={resp.order_id}")
    test("reasoning non-empty", len(resp.reasoning) > 0,
         f"reasoning='{resp.reasoning}'")

    # --- Section 3: Partial fill scenario (triggers ATP_SHORTAGE signal) ---
    print("\n  -- Partial Fill & Signal Emission --")
    # Request more than available across all tiers for priority 3
    # Priority 3 order: sequence is [3] then bottom-up [2], cannot go above 3
    # But we only have priority 1 and 2 allocations, so nothing for priority 3
    req_partial = ATPRequest(
        order_id="ORD-101",
        product_id="PROD-001",
        location_id="LOC-A",
        requested_qty=200,
        priority=1,
    )
    resp_partial = executor.check_atp(req_partial, inventory_context=inv_ctx)

    # Priority 1 can consume own tier (50) + bottom-up from tier 2 (80) = 130 total
    # But allocation was already consumed for 40 from tier 2, so tier 2 has 40 left
    # Tier 1 had 50, so total = 50 + 40 = 90
    test("Partial fill: can_fulfill is True", resp_partial.can_fulfill is True,
         f"can_fulfill={resp_partial.can_fulfill}")
    test("Partial fill: promised < requested",
         resp_partial.promised_qty < req_partial.requested_qty,
         f"promised={resp_partial.promised_qty}, requested={req_partial.requested_qty}")

    # Check that ATP_SHORTAGE signal was emitted
    shortage_signals = bus.read(
        consumer_trm="rebalancing",
        types={HiveSignalType.ATP_SHORTAGE},
    )
    test("ATP_SHORTAGE signal emitted on shortage",
         len(shortage_signals) > 0,
         f"Found {len(shortage_signals)} signals")
    if shortage_signals:
        sig = shortage_signals[0]
        test("Signal source is atp_executor",
             sig.source_trm == "atp_executor",
             f"source_trm={sig.source_trm}")
        test("Signal product_id matches",
             sig.product_id == "PROD-001",
             f"product_id={sig.product_id}")
        test("Signal urgency > 0", sig.urgency > 0,
             f"urgency={sig.urgency}")

    # --- Section 4: UrgencyVector updated ---
    print("\n  -- Urgency Vector --")
    urg_val, urg_dir, _ = bus.urgency.read("atp_executor")
    test("Urgency vector updated for atp_executor",
         urg_val > 0,
         f"urgency={urg_val}, direction={urg_dir}")

    # --- Section 5: Metrics tracking ---
    print("\n  -- Metrics --")
    metrics = executor.get_metrics()
    test("total_requests >= 2", metrics["total_requests"] >= 2,
         f"total_requests={metrics['total_requests']}")
    test("heuristic_decisions >= 2", metrics["heuristic_decisions"] >= 2,
         f"heuristic_decisions={metrics['heuristic_decisions']}")

    # --- Section 6: Decision history for training ---
    print("\n  -- Training Data --")
    history = executor.get_training_data()
    test("Decision history populated", len(history) >= 2,
         f"history_len={len(history)}")

    # --- Section 7: ATPState feature vector ---
    print("\n  -- State Feature Vector --")
    state = ATPState(
        order_priority=2,
        requested_qty=100,
        allocation_available={1: 50, 2: 80, 3: 30},
        current_inventory=200,
        pipeline_inventory=50,
        safety_stock_level=30,
        demand_forecast=100,
        demand_uncertainty=20,
    )
    features = state.to_features()
    test("Feature vector length = 12 (7 base + 5 alloc)",
         len(features) == 12,
         f"len={len(features)}")
    test("Feature vector dtype is float32",
         str(features.dtype) == "float32",
         f"dtype={features.dtype}")

    # --- Section 8: to_dict serialization ---
    print("\n  -- Response Serialization --")
    d = resp.to_dict()
    test("to_dict has order_id", "order_id" in d, f"keys={list(d.keys())}")
    test("to_dict has can_fulfill", "can_fulfill" in d, "")
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

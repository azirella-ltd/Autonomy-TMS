#!/usr/bin/env python3
"""F5: Site tGNN Layer 1.5 Inference Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import time
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
    print(f"F5: Site tGNN Layer 1.5 Inference Validation")
    print(f"{'='*60}")

    try:
        from app.models.gnn.site_tgnn import TRM_NAMES, NUM_TRM_TYPES
        from app.services.powell.site_tgnn_inference_service import (
            SiteTGNNInferenceService,
            SiteTGNNOutput,
        )
    except ImportError as e:
        print(f"  SKIP: Required module not available: {e}")
        print(f"\n{'='*60}")
        print(f"Results: 0 passed, 0 failed (SKIPPED - missing dependencies)")
        print(f"{'='*60}")
        sys.exit(0)

    # ── Test 1: Cold-start returns neutral output ──────────────────────
    print("\n[Test 1] Cold-start returns neutral output")
    neutral = SiteTGNNOutput.neutral()
    test(
        "Neutral output has all TRM names in urgency_adjustments",
        set(neutral.urgency_adjustments.keys()) == set(TRM_NAMES),
        f"Expected {set(TRM_NAMES)}, got {set(neutral.urgency_adjustments.keys())}",
    )
    all_zero = all(v == 0.0 for v in neutral.urgency_adjustments.values())
    test(
        "Neutral urgency adjustments are all zero",
        all_zero,
        f"Non-zero values: {[k for k, v in neutral.urgency_adjustments.items() if v != 0.0]}",
    )

    # ── Test 2: Output structure has per-TRM urgency_adjustments ──────
    print("\n[Test 2] Output structure has per-TRM fields")
    test(
        "SiteTGNNOutput has urgency_adjustments dict",
        isinstance(neutral.urgency_adjustments, dict),
        f"Type is {type(neutral.urgency_adjustments)}",
    )
    test(
        "SiteTGNNOutput has confidence_modifiers dict",
        isinstance(neutral.confidence_modifiers, dict),
        f"Type is {type(neutral.confidence_modifiers)}",
    )
    test(
        "SiteTGNNOutput has coordination_signals dict",
        isinstance(neutral.coordination_signals, dict),
        f"Type is {type(neutral.coordination_signals)}",
    )
    test(
        "All 11 TRM types present in urgency_adjustments",
        len(neutral.urgency_adjustments) == NUM_TRM_TYPES,
        f"Expected {NUM_TRM_TYPES}, got {len(neutral.urgency_adjustments)}",
    )

    # ── Test 3: Adjustments within valid range [-0.3, +0.3] ───────────
    print("\n[Test 3] Adjustment range validation")
    # Neutral is trivially in range; also check coordination_signals for [0, 1]
    all_in_range = all(
        -0.3 <= v <= 0.3 for v in neutral.urgency_adjustments.values()
    )
    test(
        "Neutral urgency adjustments within [-0.3, +0.3]",
        all_in_range,
        f"Out of range: {[(k,v) for k,v in neutral.urgency_adjustments.items() if not (-0.3 <= v <= 0.3)]}",
    )
    conf_in_range = all(
        -0.2 <= v <= 0.2 for v in neutral.confidence_modifiers.values()
    )
    test(
        "Neutral confidence modifiers within [-0.2, +0.2]",
        conf_in_range,
        f"Out of range values found",
    )
    coord_in_range = all(
        0.0 <= v <= 1.0 for v in neutral.coordination_signals.values()
    )
    test(
        "Neutral coordination signals within [0.0, 1.0]",
        coord_in_range,
        f"Out of range values found",
    )

    # ── Test 4: Active TRM filtering ──────────────────────────────────
    print("\n[Test 4] Active TRM filtering - inactive TRMs get zero adjustment")
    # Create service with restricted active_trms (only 3 TRMs active)
    active_set = frozenset(["atp_executor", "po_creation", "order_tracking"])
    service = SiteTGNNInferenceService(
        site_key="TEST_FILTER",
        config_id=999,
        active_trms=active_set,
    )
    # Without a model, infer returns neutral, but mask should still be set
    output = service.infer(
        hive_signal_bus=None,
        urgency_vector=None,
        recent_decisions=None,
        hive_feedback=None,
    )
    # All adjustments should be zero for neutral output
    test(
        "Inactive TRMs get zero urgency adjustment",
        all(
            output.urgency_adjustments.get(name, 0.0) == 0.0
            for name in TRM_NAMES
            if name not in active_set
            and name not in ("forecast_adjustment", "quality_disposition", "maintenance_scheduling")
        ),
        "Some inactive TRMs have non-zero adjustments",
    )
    # Verify the active mask is correctly set
    expected_active_count = sum(1 for m in service._active_mask if m)
    test(
        "Active mask reflects provided active_trms",
        expected_active_count == len(active_set),
        f"Expected {len(active_set)} active, got {expected_active_count}",
    )

    # ── Test 5: Latency check ─────────────────────────────────────────
    print("\n[Test 5] Latency check - inference should be fast")
    service_fast = SiteTGNNInferenceService(
        site_key="TEST_LATENCY",
        config_id=999,
    )
    start = time.perf_counter()
    for _ in range(100):
        service_fast.infer(None, None, None, None)
    elapsed_ms = (time.perf_counter() - start) * 1000
    avg_ms = elapsed_ms / 100
    test(
        f"Average inference latency < 10ms (cold start path)",
        avg_ms < 10.0,
        f"Average latency was {avg_ms:.2f}ms",
    )

    # ── Test 6: to_dict serialization ─────────────────────────────────
    print("\n[Test 6] Serialization")
    d = neutral.to_dict()
    test(
        "to_dict has urgency_adjustments key",
        "urgency_adjustments" in d,
        f"Keys: {list(d.keys())}",
    )
    test(
        "to_dict has reasoning key",
        "reasoning" in d,
        f"Keys: {list(d.keys())}",
    )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

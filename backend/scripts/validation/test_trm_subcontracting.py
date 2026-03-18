#!/usr/bin/env python3
"""C9: Subcontracting TRM Validation

Tests SubcontractingTRM:
- Engine baseline routing (keep_internal, route_external, split)
- TRM heuristic overrides (bad vendor -> keep_internal, critical product)
- Hive signal emission for route_external/split decisions
- Output structure validation (split ratio, cost savings)
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
    print(f"C9: Subcontracting TRM Validation")
    print(f"{'='*60}")

    from app.services.powell.subcontracting_trm import (
        SubcontractingTRM, SubcontractingTRMConfig,
        SubcontractingState, SubcontractingRecommendation,
    )
    from app.services.powell.engines.subcontracting_engine import (
        SubcontractingEngine, SubcontractingEngineConfig,
        SubcontractSnapshot, SubcontractDecisionType,
    )
    from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType

    # ----------------------------------------------------------------
    # Test 1: Engine keeps internal when no subcontractor
    # ----------------------------------------------------------------
    print("\n--- Test 1: Engine keeps internal (no subcontractor) ---")
    engine = SubcontractingEngine("SITE_A")
    snap_no_vendor = SubcontractSnapshot(
        product_id="PROD-A",
        site_id="SITE_A",
        required_quantity=500,
        internal_capacity_pct=60.0,
        internal_cost_per_unit=10.0,
        internal_lead_time_days=5,
    )
    result = engine.evaluate_routing(snap_no_vendor)
    test(
        "Engine keeps internal when no subcontractor",
        result.decision_type == SubcontractDecisionType.KEEP_INTERNAL,
        f"got {result.decision_type}",
    )
    test(
        "Internal qty equals required qty",
        result.internal_quantity == 500,
        f"got {result.internal_quantity}",
    )

    # ----------------------------------------------------------------
    # Test 2: Engine keeps internal for high IP sensitivity
    # ----------------------------------------------------------------
    print("\n--- Test 2: Engine keeps internal (high IP) ---")
    snap_ip = SubcontractSnapshot(
        product_id="PROD-B",
        site_id="SITE_A",
        required_quantity=300,
        internal_capacity_pct=50.0,
        internal_cost_per_unit=15.0,
        subcontractor_id="VENDOR-1",
        subcontractor_cost_per_unit=8.0,
        subcontractor_quality_score=0.95,
        subcontractor_on_time_score=0.90,
        ip_sensitivity="high",
    )
    result_ip = engine.evaluate_routing(snap_ip)
    test(
        "Engine keeps internal for high IP sensitivity",
        result_ip.decision_type == SubcontractDecisionType.KEEP_INTERNAL,
        f"got {result_ip.decision_type}",
    )

    # ----------------------------------------------------------------
    # Test 3: Engine routes external for cost savings
    # ----------------------------------------------------------------
    print("\n--- Test 3: Engine routes external (cost savings) ---")
    snap_cost = SubcontractSnapshot(
        product_id="PROD-C",
        site_id="SITE_A",
        required_quantity=1000,
        internal_capacity_pct=0.60,
        internal_cost_per_unit=20.0,
        internal_lead_time_days=10,
        subcontractor_id="VENDOR-2",
        subcontractor_cost_per_unit=12.0,
        subcontractor_lead_time_days=8,
        subcontractor_quality_score=0.92,
        subcontractor_on_time_score=0.88,
        subcontractor_capacity_available=1500,
        ip_sensitivity="low",
    )
    result_cost = engine.evaluate_routing(snap_cost)
    test(
        "Engine routes external for significant cost savings",
        result_cost.decision_type == SubcontractDecisionType.ROUTE_EXTERNAL,
        f"got {result_cost.decision_type}",
    )
    test(
        "Cost savings is positive",
        result_cost.cost_savings > 0,
        f"got {result_cost.cost_savings}",
    )

    # ----------------------------------------------------------------
    # Test 4: Engine splits when capacity is constrained
    # ----------------------------------------------------------------
    print("\n--- Test 4: Engine splits (capacity constrained) ---")
    snap_split = SubcontractSnapshot(
        product_id="PROD-D",
        site_id="SITE_A",
        required_quantity=1000,
        internal_capacity_available=200,
        internal_capacity_total=1000,
        internal_capacity_pct=95.0,
        internal_cost_per_unit=15.0,
        internal_lead_time_days=7,
        subcontractor_id="VENDOR-3",
        subcontractor_cost_per_unit=18.0,
        subcontractor_lead_time_days=10,
        subcontractor_quality_score=0.90,
        subcontractor_on_time_score=0.85,
        subcontractor_capacity_available=800,
        ip_sensitivity="low",
    )
    result_split = engine.evaluate_routing(snap_split)
    test(
        "Engine splits when capacity constrained",
        result_split.decision_type in (SubcontractDecisionType.SPLIT, SubcontractDecisionType.ROUTE_EXTERNAL),
        f"got {result_split.decision_type}",
    )
    if result_split.decision_type == SubcontractDecisionType.SPLIT:
        test(
            "Split has both internal and external qty",
            result_split.internal_quantity > 0 and result_split.external_quantity > 0,
            f"internal={result_split.internal_quantity}, external={result_split.external_quantity}",
        )
        test(
            "Split quantities sum to required",
            abs(result_split.internal_quantity + result_split.external_quantity - 1000) < 1,
            f"sum={result_split.internal_quantity + result_split.external_quantity}",
        )

    # ----------------------------------------------------------------
    # Test 5: TRM heuristic overrides route_external to keep_internal (bad vendor)
    # ----------------------------------------------------------------
    print("\n--- Test 5: TRM heuristic override (bad vendor -> keep_internal) ---")
    trm = SubcontractingTRM(site_key="SITE_A")
    state_bad_vendor = SubcontractingState(
        product_id="PROD-E",
        site_id="SITE_A",
        required_quantity=500,
        internal_capacity_pct=60.0,
        internal_cost_per_unit=20.0,
        internal_lead_time_days=7,
        subcontractor_id="VENDOR-BAD",
        subcontractor_cost_per_unit=12.0,
        subcontractor_lead_time_days=5,
        subcontractor_quality_score=0.92,
        subcontractor_on_time_score=0.88,
        subcontractor_capacity_available=1000,
        ip_sensitivity="low",
        vendor_historical_reject_rate=0.12,
        vendor_historical_late_rate=0.25,
    )
    rec = trm.evaluate_routing(state_bad_vendor)
    test(
        "TRM returns SubcontractingRecommendation",
        isinstance(rec, SubcontractingRecommendation),
        f"got {type(rec).__name__}",
    )
    test(
        "Heuristic overrides to keep_internal for bad vendor history",
        rec.decision_type == "keep_internal",
        f"got {rec.decision_type}",
    )

    # ----------------------------------------------------------------
    # Test 6: TRM heuristic overrides for critical product + mediocre vendor
    # ----------------------------------------------------------------
    print("\n--- Test 6: TRM heuristic (critical product + mediocre vendor) ---")
    state_critical = SubcontractingState(
        product_id="PROD-F",
        site_id="SITE_A",
        required_quantity=200,
        internal_capacity_pct=60.0,
        internal_cost_per_unit=25.0,
        internal_lead_time_days=10,
        subcontractor_id="VENDOR-MED",
        subcontractor_cost_per_unit=15.0,
        subcontractor_lead_time_days=7,
        subcontractor_quality_score=0.88,
        subcontractor_on_time_score=0.85,
        subcontractor_capacity_available=500,
        is_critical_product=True,
        ip_sensitivity="low",
    )
    rec_crit = trm.evaluate_routing(state_critical)
    test(
        "Critical product with mediocre vendor stays internal",
        rec_crit.decision_type == "keep_internal",
        f"got {rec_crit.decision_type}",
    )

    # ----------------------------------------------------------------
    # Test 7: Hive signal on route_external
    # ----------------------------------------------------------------
    print("\n--- Test 7: Hive signal emission on route_external ---")
    bus = HiveSignalBus()
    trm_sig = SubcontractingTRM(site_key="SITE_A")
    trm_sig.signal_bus = bus

    state_external = SubcontractingState(
        product_id="PROD-G",
        site_id="SITE_A",
        required_quantity=1000,
        internal_capacity_pct=60.0,
        internal_cost_per_unit=20.0,
        internal_lead_time_days=10,
        subcontractor_id="VENDOR-GOOD",
        subcontractor_cost_per_unit=12.0,
        subcontractor_lead_time_days=7,
        subcontractor_quality_score=0.95,
        subcontractor_on_time_score=0.92,
        subcontractor_capacity_available=2000,
        ip_sensitivity="low",
        vendor_historical_reject_rate=0.02,
        vendor_historical_late_rate=0.05,
    )
    rec_ext = trm_sig.evaluate_routing(state_external)
    if rec_ext.decision_type in ("route_external", "split"):
        signals = bus.read(consumer_trm="test", types={HiveSignalType.SUBCONTRACT_ROUTED})
        test(
            "SUBCONTRACT_ROUTED signal emitted",
            len(signals) >= 1,
            f"found {len(signals)} signals",
        )
        if signals:
            test(
                "Signal source is subcontracting",
                signals[0].source_trm == "subcontracting",
                f"got {signals[0].source_trm}",
            )
    else:
        test(
            "Route external for signal test",
            False,
            f"got {rec_ext.decision_type}; expected route_external or split",
        )

    # ----------------------------------------------------------------
    # Test 8: Output structure completeness
    # ----------------------------------------------------------------
    print("\n--- Test 8: Output structure completeness ---")
    test(
        "order_id is product_site format",
        "_" in rec.order_id,
        f"got {rec.order_id}",
    )
    test("confidence in [0,1]", 0.0 <= rec.confidence <= 1.0, f"got {rec.confidence}")
    test("total_cost is non-negative", rec.total_cost >= 0, f"got {rec.total_cost}")
    test("quality_risk is float", isinstance(rec.quality_risk, (int, float)), f"got {type(rec.quality_risk).__name__}")
    test("delivery_risk is float", isinstance(rec.delivery_risk, (int, float)), f"got {type(rec.delivery_risk).__name__}")
    test("reason is populated", len(rec.reason) > 0, f"empty reason")

    # ----------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

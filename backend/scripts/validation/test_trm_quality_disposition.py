#!/usr/bin/env python3
"""C7: Quality Disposition TRM Validation

Tests QualityDispositionTRM:
- Engine baseline disposition for various defect scenarios
- TRM heuristic overrides (accept->rework, rework->scrap)
- Hive signal emission after disposition decisions
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
    print(f"C7: Quality Disposition TRM Validation")
    print(f"{'='*60}")

    from app.services.powell.quality_disposition_trm import (
        QualityDispositionTRM, QualityDispositionTRMConfig,
        QualityDispositionState, QualityRecommendation,
    )
    from app.services.powell.engines.quality_engine import (
        QualityEngine, QualityEngineConfig, QualitySnapshot,
        DispositionType,
    )
    from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType

    # ----------------------------------------------------------------
    # Test 1: Engine auto-accept for low defect rate
    # ----------------------------------------------------------------
    print("\n--- Test 1: Engine auto-accept (low defect rate) ---")
    engine = QualityEngine("SITE_A")
    snap_good = QualitySnapshot(
        quality_order_id="QO-001",
        product_id="PROD-A",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=1000,
        defect_count=5,
        defect_rate=0.005,
        defect_category="visual",
        severity_level="minor",
        characteristics_tested=10,
        characteristics_passed=10,
        product_unit_value=50.0,
        estimated_rework_cost=500.0,
        estimated_scrap_cost=2500.0,
        inventory_on_hand=500,
        safety_stock=100,
        days_of_supply=15,
    )
    result = engine.evaluate_disposition(snap_good)
    test(
        "Engine auto-accepts low defect rate",
        result.recommended_disposition == DispositionType.ACCEPT,
        f"got {result.recommended_disposition}",
    )
    test(
        "Accept qty equals inspection qty",
        result.accept_qty == 1000,
        f"got {result.accept_qty}",
    )

    # ----------------------------------------------------------------
    # Test 2: Engine rejects critical defects
    # ----------------------------------------------------------------
    print("\n--- Test 2: Engine rejects critical defects ---")
    snap_critical = QualitySnapshot(
        quality_order_id="QO-002",
        product_id="PROD-B",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=500,
        defect_count=2,
        defect_rate=0.004,
        severity_level="critical",
        characteristics_tested=10,
        characteristics_passed=8,
        product_unit_value=100.0,
        estimated_rework_cost=1000.0,
        estimated_scrap_cost=5000.0,
    )
    result_crit = engine.evaluate_disposition(snap_critical)
    test(
        "Engine rejects critical defects",
        result_crit.recommended_disposition == DispositionType.REJECT,
        f"got {result_crit.recommended_disposition}",
    )
    test(
        "Reject qty equals inspection qty",
        result_crit.reject_qty == 500,
        f"got {result_crit.reject_qty}",
    )

    # ----------------------------------------------------------------
    # Test 3: TRM heuristic override — vendor with poor quality
    # ----------------------------------------------------------------
    print("\n--- Test 3: TRM heuristic override (poor vendor -> return_to_vendor) ---")
    trm = QualityDispositionTRM(site_key="SITE_A")
    state_bad_vendor = QualityDispositionState(
        quality_order_id="QO-003",
        product_id="PROD-C",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=200,
        defect_count=4,
        defect_rate=0.02,
        defect_category="dimensional",
        severity_level="major",
        characteristics_tested=10,
        characteristics_passed=8,
        product_unit_value=75.0,
        estimated_rework_cost=300.0,
        estimated_scrap_cost=1500.0,
        vendor_id="VENDOR-X",
        vendor_quality_score=60.0,
        vendor_recent_reject_rate=0.20,
        days_since_receipt=5,
        inventory_on_hand=300,
        safety_stock=50,
        days_of_supply=10,
    )
    rec = trm.evaluate_disposition(state_bad_vendor)
    test(
        "TRM returns QualityRecommendation",
        isinstance(rec, QualityRecommendation),
        f"got {type(rec).__name__}",
    )
    test(
        "Heuristic overrides to return_to_vendor for bad vendor",
        rec.disposition == "return_to_vendor",
        f"got {rec.disposition}",
    )
    test(
        "Confidence is set",
        0.0 < rec.confidence <= 1.0,
        f"got {rec.confidence}",
    )
    test(
        "Reason mentions heuristic",
        "Heuristic" in rec.reason or "heuristic" in rec.reason.lower(),
        f"reason: {rec.reason[:80]}",
    )

    # ----------------------------------------------------------------
    # Test 4: TRM heuristic override — use_as_is blocked by complaints
    # ----------------------------------------------------------------
    print("\n--- Test 4: TRM heuristic (use_as_is with complaints -> rework) ---")
    # Engine would suggest use_as_is for minor defect + low inventory
    state_use_as_is = QualityDispositionState(
        quality_order_id="QO-004",
        product_id="PROD-D",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=100,
        defect_count=2,
        defect_rate=0.02,
        defect_category="visual",
        severity_level="minor",
        characteristics_tested=5,
        characteristics_passed=5,
        product_unit_value=30.0,
        estimated_rework_cost=200.0,
        estimated_scrap_cost=600.0,
        inventory_on_hand=10,
        safety_stock=50,
        days_of_supply=1,
        pending_customer_orders=80,
        similar_use_as_is_complaint_rate=0.15,
        product_rework_success_rate=0.90,
    )
    rec2 = trm.evaluate_disposition(state_use_as_is)
    test(
        "High complaint rate blocks use_as_is",
        rec2.disposition != "use_as_is",
        f"got {rec2.disposition}",
    )

    # ----------------------------------------------------------------
    # Test 5: TRM heuristic — low rework success forces scrap
    # ----------------------------------------------------------------
    print("\n--- Test 5: TRM heuristic (low rework success -> scrap or reject) ---")
    state_low_rework = QualityDispositionState(
        quality_order_id="QO-005",
        product_id="PROD-E",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=500,
        defect_count=50,
        defect_rate=0.10,
        defect_category="functional",
        severity_level="major",
        characteristics_tested=10,
        characteristics_passed=5,
        product_unit_value=100.0,
        estimated_rework_cost=5000.0,
        estimated_scrap_cost=5000.0,
        vendor_id="VENDOR-Y",
        vendor_quality_score=80.0,
        vendor_recent_reject_rate=0.05,
        days_since_receipt=10,
        product_rework_success_rate=0.50,
    )
    rec3 = trm.evaluate_disposition(state_low_rework)
    test(
        "Low rework success avoids rework disposition",
        rec3.disposition != "rework",
        f"got {rec3.disposition} (expected scrap or reject)",
    )

    # ----------------------------------------------------------------
    # Test 6: Hive signal emission on reject
    # ----------------------------------------------------------------
    print("\n--- Test 6: Hive signal emission on reject ---")
    bus = HiveSignalBus()
    trm_sig = QualityDispositionTRM(site_key="SITE_A")
    trm_sig.signal_bus = bus

    state_reject = QualityDispositionState(
        quality_order_id="QO-006",
        product_id="PROD-F",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=100,
        defect_count=10,
        defect_rate=0.10,
        defect_category="functional",
        severity_level="critical",
        characteristics_tested=5,
        characteristics_passed=3,
        product_unit_value=200.0,
        estimated_rework_cost=5000.0,
        estimated_scrap_cost=2000.0,
    )
    rec_reject = trm_sig.evaluate_disposition(state_reject)
    test(
        "Reject disposition emitted",
        rec_reject.disposition in ("reject", "return_to_vendor", "scrap"),
        f"got {rec_reject.disposition}",
    )
    signals = bus.read(consumer_trm="test", types={HiveSignalType.QUALITY_REJECT})
    test(
        "QUALITY_REJECT signal emitted to bus",
        len(signals) >= 1,
        f"found {len(signals)} signals",
    )
    if signals:
        test(
            "Signal source is quality",
            signals[0].source_trm == "quality",
            f"got source_trm={signals[0].source_trm}",
        )
        test(
            "Signal urgency > 0",
            signals[0].urgency > 0,
            f"got urgency={signals[0].urgency}",
        )

    # ----------------------------------------------------------------
    # Test 7: Hive signal emission on rework (QUALITY_HOLD)
    # ----------------------------------------------------------------
    print("\n--- Test 7: Hive signal emission on rework (QUALITY_HOLD) ---")
    bus2 = HiveSignalBus()
    trm_rework = QualityDispositionTRM(site_key="SITE_A")
    trm_rework.signal_bus = bus2

    state_rework = QualityDispositionState(
        quality_order_id="QO-007",
        product_id="PROD-G",
        site_id="SITE_A",
        inspection_type="incoming",
        inspection_quantity=200,
        defect_count=15,
        defect_rate=0.075,
        defect_category="visual",
        severity_level="major",
        characteristics_tested=8,
        characteristics_passed=6,
        product_unit_value=50.0,
        estimated_rework_cost=500.0,
        estimated_scrap_cost=2000.0,
        vendor_id=None,
        vendor_recent_reject_rate=0.0,
        product_rework_success_rate=0.95,
    )
    rec_rework = trm_rework.evaluate_disposition(state_rework)
    if rec_rework.disposition == "rework":
        hold_signals = bus2.read(consumer_trm="test", types={HiveSignalType.QUALITY_HOLD})
        test(
            "QUALITY_HOLD signal emitted on rework",
            len(hold_signals) >= 1,
            f"found {len(hold_signals)} signals",
        )
    else:
        test(
            "Rework disposition for signal test",
            False,
            f"got {rec_rework.disposition} instead of rework; signal test skipped",
        )

    # ----------------------------------------------------------------
    # Test 8: Output structure completeness
    # ----------------------------------------------------------------
    print("\n--- Test 8: Output structure completeness ---")
    test(
        "quality_order_id populated",
        rec.quality_order_id == "QO-003",
        f"got {rec.quality_order_id}",
    )
    test(
        "disposition is a string",
        isinstance(rec.disposition, str),
        f"got {type(rec.disposition).__name__}",
    )
    test(
        "rework_cost is float",
        isinstance(rec.rework_cost, (int, float)),
        f"got {type(rec.rework_cost).__name__}",
    )
    test(
        "scrap_cost is float",
        isinstance(rec.scrap_cost, (int, float)),
        f"got {type(rec.scrap_cost).__name__}",
    )
    test(
        "service_risk is float",
        isinstance(rec.service_risk, (int, float)),
        f"got {type(rec.service_risk).__name__}",
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

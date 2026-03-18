#!/usr/bin/env python3
"""A7: Quality Engine Validation"""
import os, sys, importlib.util

# Direct module loading to avoid pulling in the full app dependency chain
_ENGINES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines')

def _load_engine(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(_ENGINES_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_qe = _load_engine("quality_engine", "quality_engine.py")
QualityEngine = _qe.QualityEngine
QualityEngineConfig = _qe.QualityEngineConfig
QualitySnapshot = _qe.QualitySnapshot
QualityDispositionResult = _qe.QualityDispositionResult
DispositionType = _qe.DispositionType
SeverityLevel = _qe.SeverityLevel
InspectionType = _qe.InspectionType

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


def test_auto_accept_low_defect():
    """defect_rate=0.005 (< 0.01) + minor severity => ACCEPT"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    qo = QualitySnapshot(
        quality_order_id="QO-1", product_id="PROD-1", site_id="SITE-1",
        inspection_type="incoming",
        inspection_quantity=1000, defect_count=5, defect_rate=0.005,
        defect_category="cosmetic", severity_level="minor",
        characteristics_tested=10, characteristics_passed=10,
        characteristics_failed=0,
        product_unit_value=50.0, estimated_rework_cost=2000.0,
        estimated_scrap_cost=25000.0,
        vendor_id="VEND-1", vendor_quality_score=0.92,
        days_since_receipt=5,
        inventory_on_hand=500, safety_stock=200, days_of_supply=15.0,
        pending_customer_orders=3,
        lot_number="LOT-001", lot_size=1000,
    )
    result = engine.evaluate_disposition(qo)
    test("Auto-accept - disposition is ACCEPT",
         result.recommended_disposition == DispositionType.ACCEPT,
         f"got {result.recommended_disposition}")
    test("Auto-accept - accept_qty equals inspection_quantity",
         result.accept_qty == 1000,
         f"got accept_qty={result.accept_qty}")
    test("Auto-accept - high confidence",
         result.confidence >= 0.90,
         f"got confidence={result.confidence}")


def test_auto_reject_critical():
    """severity=critical, critical_defect_auto_reject=True => REJECT"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    qo = QualitySnapshot(
        quality_order_id="QO-2", product_id="PROD-1", site_id="SITE-1",
        inspection_type="incoming",
        inspection_quantity=1000, defect_count=10, defect_rate=0.01,
        defect_category="functional", severity_level="critical",
        product_unit_value=50.0, estimated_rework_cost=30000.0,
        estimated_scrap_cost=25000.0,
        vendor_id="VEND-1", vendor_quality_score=0.70,
        days_since_receipt=5,
        inventory_on_hand=500, safety_stock=200, days_of_supply=15.0,
        pending_customer_orders=3,
        lot_number="LOT-002", lot_size=1000,
    )
    result = engine.evaluate_disposition(qo)
    test("Critical reject - disposition is REJECT",
         result.recommended_disposition == DispositionType.REJECT,
         f"got {result.recommended_disposition}")
    test("Critical reject - reject_qty equals full lot",
         result.reject_qty == 1000,
         f"got reject_qty={result.reject_qty}")


def test_rework_viable():
    """defect_rate=0.06 (> max_accept 0.05), rework_cost < 30% of value => REWORK"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    product_value = 500 * 50.0  # 500 qty * $50 = $25,000
    rework_cost = 5000.0  # 20% of value => below 30% threshold
    qo = QualitySnapshot(
        quality_order_id="QO-3", product_id="PROD-1", site_id="SITE-1",
        inspection_type="in_process",
        inspection_quantity=500, defect_count=30, defect_rate=0.06,
        defect_category="dimensional", severity_level="major",
        product_unit_value=50.0,
        estimated_rework_cost=rework_cost,
        estimated_scrap_cost=12500.0,
        vendor_id="VEND-1", days_since_receipt=10,
        inventory_on_hand=500, safety_stock=200, days_of_supply=10.0,
        pending_customer_orders=2,
        lot_number="LOT-003", lot_size=500,
    )
    result = engine.evaluate_disposition(qo)
    test("Rework viable - disposition is REWORK",
         result.recommended_disposition == DispositionType.REWORK,
         f"got {result.recommended_disposition}")
    test("Rework viable - rework_cost populated",
         result.rework_cost == rework_cost,
         f"got rework_cost={result.rework_cost}")


def test_scrap_rework_too_expensive():
    """rework_cost > 50% of value => SCRAP"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    # product_value = 200 * 100 = $20,000; rework = $12,000 = 60% > 50% threshold
    qo = QualitySnapshot(
        quality_order_id="QO-4", product_id="PROD-2", site_id="SITE-1",
        inspection_type="final",
        inspection_quantity=200, defect_count=20, defect_rate=0.10,
        defect_category="functional", severity_level="major",
        product_unit_value=100.0,
        estimated_rework_cost=12000.0,
        estimated_scrap_cost=10000.0,
        vendor_id=None, days_since_receipt=40,
        inventory_on_hand=500, safety_stock=200, days_of_supply=10.0,
        pending_customer_orders=1,
        lot_number="LOT-004", lot_size=200,
    )
    result = engine.evaluate_disposition(qo)
    test("Scrap - disposition is SCRAP",
         result.recommended_disposition == DispositionType.SCRAP,
         f"got {result.recommended_disposition}")
    test("Scrap - scrap_qty equals inspection_quantity",
         result.scrap_qty == 200,
         f"got scrap_qty={result.scrap_qty}")


def test_use_as_is_minor():
    """severity=minor, defect_rate < 0.03, inventory critically needed => USE_AS_IS"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    qo = QualitySnapshot(
        quality_order_id="QO-5", product_id="PROD-1", site_id="SITE-1",
        inspection_type="incoming",
        inspection_quantity=1000, defect_count=20, defect_rate=0.02,
        defect_category="cosmetic", severity_level="minor",
        product_unit_value=50.0,
        estimated_rework_cost=5000.0, estimated_scrap_cost=25000.0,
        vendor_id="VEND-1", days_since_receipt=5,
        inventory_on_hand=100, safety_stock=200, days_of_supply=2.0,
        pending_customer_orders=150,
        lot_number="LOT-005", lot_size=1000,
    )
    result = engine.evaluate_disposition(qo)
    test("Use-as-is - disposition is USE_AS_IS",
         result.recommended_disposition == DispositionType.USE_AS_IS,
         f"got {result.recommended_disposition}")
    test("Use-as-is - use_as_is_qty equals inspection_quantity",
         result.use_as_is_qty == 1000,
         f"got use_as_is_qty={result.use_as_is_qty}")


def test_vendor_return_window():
    """Within return window (days_since_receipt < 30) => return_to_vendor flag on reject"""
    engine = QualityEngine(site_key="SITE-1", config=QualityEngineConfig())
    # High defect, rework between 30-50% of value, vendor present, within 30 days
    # product_value = 300 * 80 = $24,000; rework = $9,600 = 40% (between 30% and 50%)
    qo = QualitySnapshot(
        quality_order_id="QO-6", product_id="PROD-3", site_id="SITE-1",
        inspection_type="incoming",
        inspection_quantity=300, defect_count=30, defect_rate=0.10,
        defect_category="dimensional", severity_level="major",
        product_unit_value=80.0,
        estimated_rework_cost=9600.0,
        estimated_scrap_cost=12000.0,
        vendor_id="VEND-2", vendor_quality_score=0.60,
        days_since_receipt=15,
        inventory_on_hand=800, safety_stock=200, days_of_supply=20.0,
        pending_customer_orders=1,
        lot_number="LOT-006", lot_size=300,
    )
    result = engine.evaluate_disposition(qo)
    test("Vendor return - disposition is RETURN_TO_VENDOR",
         result.recommended_disposition == DispositionType.RETURN_TO_VENDOR,
         f"got {result.recommended_disposition}")
    test("Vendor return - return_to_vendor flag set",
         result.return_to_vendor,
         f"got return_to_vendor={result.return_to_vendor}")
    test("Vendor return - within_return_window is True",
         result.within_return_window,
         f"got within_return_window={result.within_return_window}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A7: Quality Engine Validation")
    print(f"{'='*60}")

    print("\n[1] Auto-accept low defect rate")
    test_auto_accept_low_defect()

    print("\n[2] Auto-reject critical defect")
    test_auto_reject_critical()

    print("\n[3] Rework viable")
    test_rework_viable()

    print("\n[4] Scrap when rework too expensive")
    test_scrap_rework_too_expensive()

    print("\n[5] Use-as-is for minor defects")
    test_use_as_is_minor()

    print("\n[6] Vendor return within window")
    test_vendor_return_window()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

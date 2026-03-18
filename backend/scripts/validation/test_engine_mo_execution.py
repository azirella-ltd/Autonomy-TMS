#!/usr/bin/env python3
"""A5: MO Execution Engine Validation"""
import os, sys, importlib.util

# Direct module loading to avoid pulling in the full app dependency chain
_ENGINES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines')

def _load_engine(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(_ENGINES_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_mo = _load_engine("mo_execution_engine", "mo_execution_engine.py")
MOExecutionEngine = _mo.MOExecutionEngine
MOExecutionConfig = _mo.MOExecutionConfig
MOSnapshot = _mo.MOSnapshot
MOExecutionResult = _mo.MOExecutionResult
MODecisionType = _mo.MODecisionType
MOPriority = _mo.MOPriority

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


def test_release_ready():
    """Material >= 0.95 AND capacity >= 0.80 => ready_to_release=True"""
    engine = MOExecutionEngine(site_key="SITE-1", config=MOExecutionConfig())
    mo = MOSnapshot(
        order_id="MO-1", product_id="PROD-1", site_id="SITE-1", status="PLANNED",
        planned_quantity=100, completed_quantity=0, scrap_quantity=0,
        planned_start_date=date.today(),
        planned_completion_date=date.today() + timedelta(days=7),
        resource_id="RES-1", setup_time_hours=2.0, run_time_hours=8.0,
        material_availability_pct=0.98, missing_components=[],
        capacity_availability_pct=0.85, resource_utilization_pct=0.70,
        priority=3, customer_order_linked=True, days_until_due=5,
        predecessor_complete=True, current_sequence_position=1,
        product_group_id="GRP-1", runner_category="green",
    )
    result = engine.evaluate_release_readiness(mo)
    test("Release ready - ready_to_release is True",
         result.ready_to_release,
         f"got ready_to_release={result.ready_to_release}")
    test("Release ready - no blockers",
         len(result.release_blockers) == 0,
         f"blockers={result.release_blockers}")
    test("Release ready - decision type is RELEASE",
         result.decision_type == MODecisionType.RELEASE,
         f"got {result.decision_type}")


def test_release_blocked_material():
    """Material < 0.95 => ready_to_release=False, blockers non-empty"""
    engine = MOExecutionEngine(site_key="SITE-1", config=MOExecutionConfig())
    mo = MOSnapshot(
        order_id="MO-2", product_id="PROD-1", site_id="SITE-1", status="PLANNED",
        planned_quantity=100,
        material_availability_pct=0.80,
        missing_components=["COMP-A", "COMP-B"],
        capacity_availability_pct=0.90,
        priority=3, days_until_due=5, predecessor_complete=True,
    )
    result = engine.evaluate_release_readiness(mo)
    test("Release blocked - ready_to_release is False",
         not result.ready_to_release,
         f"got ready_to_release={result.ready_to_release}")
    test("Release blocked - blockers mention material",
         any("aterial" in b for b in result.release_blockers),
         f"blockers={result.release_blockers}")


def test_expedite_overdue_customer():
    """Overdue (days_until_due < 0), customer_order_linked => expedite_recommended"""
    engine = MOExecutionEngine(site_key="SITE-1", config=MOExecutionConfig())
    mo = MOSnapshot(
        order_id="MO-3", product_id="PROD-1", site_id="SITE-1", status="RELEASED",
        planned_quantity=100,
        material_availability_pct=1.0, capacity_availability_pct=1.0,
        priority=3, customer_order_linked=True, days_until_due=-2,
        predecessor_complete=True,
    )
    result = engine.evaluate_expedite_need(mo)
    test("Expedite overdue - expedite_recommended is True",
         result.expedite_recommended,
         f"got expedite_recommended={result.expedite_recommended}")
    test("Expedite overdue - reason mentions overdue",
         "overdue" in result.expedite_reason.lower(),
         f"reason={result.expedite_reason}")
    test("Expedite overdue - service_risk is 1.0 (overdue)",
         result.service_risk == 1.0,
         f"got service_risk={result.service_risk}")


def test_defer_recommendation():
    """days_until_due >> release_horizon, not ready => defer via evaluate_order"""
    engine = MOExecutionEngine(site_key="SITE-1", config=MOExecutionConfig())
    mo = MOSnapshot(
        order_id="MO-4", product_id="PROD-1", site_id="SITE-1", status="PLANNED",
        planned_quantity=100,
        material_availability_pct=0.70,  # blocked
        capacity_availability_pct=0.90,
        priority=4, customer_order_linked=False, days_until_due=30,
        predecessor_complete=True,
    )
    result = engine.evaluate_order(mo)
    test("Defer - decision_type is DEFER",
         result.decision_type == MODecisionType.DEFER,
         f"got {result.decision_type}")
    test("Defer - defer_recommended is True",
         result.defer_recommended,
         f"got defer_recommended={result.defer_recommended}")


def test_sequence_scoring():
    """Higher priority + closer due date => higher priority_score"""
    engine = MOExecutionEngine(site_key="SITE-1", config=MOExecutionConfig())

    urgent_mo = MOSnapshot(
        order_id="MO-U", product_id="PROD-A", site_id="SITE-1", status="PLANNED",
        planned_quantity=100,
        priority=1, customer_order_linked=True, days_until_due=1,
        predecessor_complete=True,
    )
    relaxed_mo = MOSnapshot(
        order_id="MO-R", product_id="PROD-B", site_id="SITE-1", status="PLANNED",
        planned_quantity=100,
        priority=4, customer_order_linked=False, days_until_due=25,
        predecessor_complete=True,
    )

    results = engine.evaluate_sequencing([urgent_mo, relaxed_mo])
    urgent_result = next(r for r in results if r.order_id == "MO-U")
    relaxed_result = next(r for r in results if r.order_id == "MO-R")

    test("Sequence - urgent has higher priority_score",
         urgent_result.priority_score > relaxed_result.priority_score,
         f"urgent={urgent_result.priority_score:.3f}, relaxed={relaxed_result.priority_score:.3f}")
    test("Sequence - urgent sequenced first",
         urgent_result.recommended_sequence < relaxed_result.recommended_sequence,
         f"urgent seq={urgent_result.recommended_sequence}, relaxed seq={relaxed_result.recommended_sequence}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A5: MO Execution Engine Validation")
    print(f"{'='*60}")

    print("\n[1] Release readiness - ready")
    test_release_ready()

    print("\n[2] Release readiness - blocked (material)")
    test_release_blocked_material()

    print("\n[3] Expedite recommendation (overdue + customer)")
    test_expedite_overdue_customer()

    print("\n[4] Defer recommendation")
    test_defer_recommendation()

    print("\n[5] Sequence scoring (priority + due date)")
    test_sequence_scoring()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

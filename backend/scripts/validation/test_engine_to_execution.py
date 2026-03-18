#!/usr/bin/env python3
"""A6: TO Execution Engine Validation"""
import os, sys, importlib.util

# Direct module loading to avoid pulling in the full app dependency chain
_ENGINES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines')

def _load_engine(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(_ENGINES_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_to = _load_engine("to_execution_engine", "to_execution_engine.py")
TOExecutionEngine = _to.TOExecutionEngine
TOExecutionConfig = _to.TOExecutionConfig
TOSnapshot = _to.TOSnapshot
TOExecutionResult = _to.TOExecutionResult
TODecisionType = _to.TODecisionType

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
    """source_on_hand > planned_qty AND source_dos > min => ready"""
    engine = TOExecutionEngine(site_key="DC-EAST", config=TOExecutionConfig())
    to = TOSnapshot(
        order_id="TO-1", product_id="PROD-1",
        source_site_id="DC-EAST", dest_site_id="DC-WEST",
        status="DRAFT",
        planned_qty=200, picked_qty=0, shipped_qty=0,
        planned_ship_date=date.today() + timedelta(days=2),
        planned_delivery_date=date.today() + timedelta(days=5),
        transportation_mode="truck", estimated_transit_days=3,
        carrier="CARRIER-1", trigger_reason="mrp_planned",
        priority=2, days_until_needed=5,
        source_on_hand=1000, source_dos=15.0, source_committed=200,
        dest_on_hand=300, dest_dos=8.0, dest_backlog=0,
        dest_safety_stock=200, transportation_cost=500.0,
    )
    result = engine.evaluate_release_readiness(to)
    test("Release ready - ready_to_release is True",
         result.ready_to_release,
         f"got {result.ready_to_release}, blockers={result.release_blockers}")
    test("Release ready - decision type is RELEASE",
         result.decision_type == TODecisionType.RELEASE,
         f"got {result.decision_type}")


def test_source_depletion_risk():
    """source_dos < min_source_inventory_days => blocked, depletion risk flagged"""
    engine = TOExecutionEngine(site_key="DC-EAST", config=TOExecutionConfig())
    to = TOSnapshot(
        order_id="TO-2", product_id="PROD-1",
        source_site_id="DC-EAST", dest_site_id="DC-WEST",
        status="DRAFT",
        planned_qty=200,
        planned_ship_date=date.today() + timedelta(days=2),
        planned_delivery_date=date.today() + timedelta(days=5),
        estimated_transit_days=3,
        priority=3, days_until_needed=5,
        source_on_hand=500, source_dos=2.0, source_committed=100,
        dest_on_hand=300, dest_dos=8.0, dest_backlog=0,
        dest_safety_stock=200, transportation_cost=500.0,
    )
    result = engine.evaluate_release_readiness(to)
    test("Source depletion - not ready to release",
         not result.ready_to_release,
         f"got ready_to_release={result.ready_to_release}")
    test("Source depletion - blockers mention DOS",
         any("DOS" in b or "dos" in b.lower() for b in result.release_blockers),
         f"blockers={result.release_blockers}")
    test("Source depletion - source_depletion_risk > 0.5",
         result.source_depletion_risk > 0.5,
         f"got source_depletion_risk={result.source_depletion_risk}")


def test_expedite_dest_needs_stock():
    """dest_dos < 2, dest_backlog > 0 => expedite_recommended"""
    engine = TOExecutionEngine(site_key="DC-EAST", config=TOExecutionConfig())
    to = TOSnapshot(
        order_id="TO-3", product_id="PROD-1",
        source_site_id="DC-EAST", dest_site_id="DC-WEST",
        status="RELEASED",
        planned_qty=200,
        planned_ship_date=date.today() + timedelta(days=1),
        planned_delivery_date=date.today() + timedelta(days=4),
        estimated_transit_days=3,
        priority=2, days_until_needed=3,
        source_on_hand=1000, source_dos=15.0, source_committed=100,
        dest_on_hand=50, dest_dos=1.5, dest_backlog=100,
        dest_safety_stock=200, transportation_cost=500.0,
    )
    result = engine.evaluate_expedite_need(to)
    test("Expedite dest needs stock - expedite_recommended",
         result.expedite_recommended,
         f"got expedite_recommended={result.expedite_recommended}")
    test("Expedite - reason mentions destination",
         "destination" in result.expedite_reason.lower(),
         f"reason={result.expedite_reason}")


def test_defer_not_needed():
    """dest_dos high, days_until_needed >> max_defer_days => defer via evaluate_order"""
    engine = TOExecutionEngine(site_key="DC-EAST", config=TOExecutionConfig())
    to = TOSnapshot(
        order_id="TO-4", product_id="PROD-1",
        source_site_id="DC-EAST", dest_site_id="DC-WEST",
        status="DRAFT",
        planned_qty=200,
        planned_ship_date=date.today() + timedelta(days=20),
        planned_delivery_date=date.today() + timedelta(days=23),
        estimated_transit_days=3,
        priority=4, days_until_needed=20,
        source_on_hand=300, source_dos=2.0, source_committed=200,
        dest_on_hand=800, dest_dos=25.0, dest_backlog=0,
        dest_safety_stock=200, transportation_cost=500.0,
    )
    result = engine.evaluate_order(to)
    test("Defer - decision_type is DEFER",
         result.decision_type == TODecisionType.DEFER,
         f"got {result.decision_type}")
    test("Defer - defer_recommended is True",
         result.defer_recommended,
         f"got defer_recommended={result.defer_recommended}")


def test_dest_stockout_risk():
    """dest_on_hand < dest_safety_stock => high stockout risk"""
    engine = TOExecutionEngine(site_key="DC-EAST", config=TOExecutionConfig())
    to = TOSnapshot(
        order_id="TO-5", product_id="PROD-1",
        source_site_id="DC-EAST", dest_site_id="DC-WEST",
        status="RELEASED",
        planned_qty=200,
        planned_ship_date=date.today(),
        planned_delivery_date=date.today() + timedelta(days=3),
        estimated_transit_days=3,
        priority=1, days_until_needed=2,
        source_on_hand=1000, source_dos=20.0, source_committed=0,
        dest_on_hand=50, dest_dos=1.0, dest_backlog=50,
        dest_safety_stock=200, transportation_cost=800.0,
    )
    result = engine.evaluate_expedite_need(to)
    test("Stockout risk - dest_stockout_risk >= 0.8",
         result.dest_stockout_risk >= 0.8,
         f"got dest_stockout_risk={result.dest_stockout_risk}")
    test("Stockout risk - expedite recommended (below safety stock)",
         result.expedite_recommended,
         f"got expedite_recommended={result.expedite_recommended}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A6: TO Execution Engine Validation")
    print(f"{'='*60}")

    print("\n[1] Release readiness - ready")
    test_release_ready()

    print("\n[2] Source depletion risk")
    test_source_depletion_risk()

    print("\n[3] Expedite when destination needs stock")
    test_expedite_dest_needs_stock()

    print("\n[4] Defer when not needed")
    test_defer_not_needed()

    print("\n[5] Destination stockout risk")
    test_dest_stockout_risk()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

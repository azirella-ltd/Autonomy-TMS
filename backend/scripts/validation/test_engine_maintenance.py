#!/usr/bin/env python3
"""A8: Maintenance Engine Validation"""
import os, sys, importlib.util

# Direct module loading to avoid pulling in the full app dependency chain
_ENGINES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines')

def _load_engine(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(_ENGINES_DIR, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_me = _load_engine("maintenance_engine", "maintenance_engine.py")
MaintenanceEngine = _me.MaintenanceEngine
MaintenanceEngineConfig = _me.MaintenanceEngineConfig
MaintenanceSnapshot = _me.MaintenanceSnapshot
MaintenanceSchedulingResult = _me.MaintenanceSchedulingResult
MaintenanceDecisionType = _me.MaintenanceDecisionType
MaintenanceType = _me.MaintenanceType

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


def test_schedule_on_time():
    """Not overdue, spare parts available, production gap available => SCHEDULE"""
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())
    mo = MaintenanceSnapshot(
        order_id="WO-1", asset_id="ASSET-1", site_id="SITE-1",
        maintenance_type="preventive", status="PLANNED",
        scheduled_date=date.today() + timedelta(days=3),
        last_maintenance_date=date.today() - timedelta(days=60),
        days_since_last_maintenance=60,
        maintenance_frequency_days=90,
        days_overdue=0, defer_count=0,
        estimated_downtime_hours=4.0, estimated_labor_hours=6.0,
        estimated_cost=2000.0, spare_parts_available=True,
        asset_criticality="normal", asset_age_years=5,
        mean_time_between_failures_days=120,
        recent_failure_count=0,
        production_schedule_load_pct=0.75,
        production_impact_units=500,
        next_production_gap_days=2,
        priority="NORMAL",
        external_cost_estimate=3000.0,
        external_lead_time_days=5,
    )
    result = engine.evaluate_scheduling(mo)
    test("Schedule on time - decision is SCHEDULE",
         result.decision_type == MaintenanceDecisionType.SCHEDULE,
         f"got {result.decision_type}")
    test("Schedule on time - recommended_date set",
         result.recommended_date is not None,
         f"got recommended_date={result.recommended_date}")
    test("Schedule on time - breakdown_probability low",
         result.breakdown_probability < 0.3,
         f"got breakdown_probability={result.breakdown_probability}")


def test_defer_production_critical():
    """production_schedule_load_pct > 0.95, not overdue, defer_count < max => DEFER"""
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())
    mo = MaintenanceSnapshot(
        order_id="WO-2", asset_id="ASSET-2", site_id="SITE-1",
        maintenance_type="preventive", status="PLANNED",
        scheduled_date=date.today() + timedelta(days=5),
        last_maintenance_date=date.today() - timedelta(days=50),
        days_since_last_maintenance=50,
        maintenance_frequency_days=90,
        days_overdue=0, defer_count=0,
        estimated_downtime_hours=6.0, estimated_labor_hours=8.0,
        estimated_cost=3000.0, spare_parts_available=True,
        asset_criticality="normal", asset_age_years=3,
        mean_time_between_failures_days=180,
        recent_failure_count=0,
        production_schedule_load_pct=0.97,  # very busy
        production_impact_units=1000,
        next_production_gap_days=10,
        priority="NORMAL",
        external_cost_estimate=4000.0,
        external_lead_time_days=7,
    )
    result = engine.evaluate_scheduling(mo)
    test("Defer production critical - decision is DEFER",
         result.decision_type == MaintenanceDecisionType.DEFER,
         f"got {result.decision_type}")
    test("Defer - defer_recommended is True",
         result.defer_recommended,
         f"got defer_recommended={result.defer_recommended}")
    test("Defer - defer_to_date set",
         result.defer_to_date is not None,
         f"got defer_to_date={result.defer_to_date}")


def test_expedite_high_risk():
    """recent failures high, days_overdue > 0, critical asset => EXPEDITE"""
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())
    mo = MaintenanceSnapshot(
        order_id="WO-3", asset_id="ASSET-3", site_id="SITE-1",
        maintenance_type="preventive", status="PLANNED",
        scheduled_date=date.today() - timedelta(days=10),
        last_maintenance_date=date.today() - timedelta(days=120),
        days_since_last_maintenance=120,
        maintenance_frequency_days=90,
        days_overdue=10, defer_count=1,
        estimated_downtime_hours=8.0, estimated_labor_hours=12.0,
        estimated_cost=5000.0, spare_parts_available=True,
        asset_criticality="critical",
        asset_age_years=12,
        mean_time_between_failures_days=90,
        recent_failure_count=3,
        production_schedule_load_pct=0.60,
        production_impact_units=2000,
        next_production_gap_days=1,
        priority="HIGH",
        external_cost_estimate=7000.0,
        external_lead_time_days=3,
    )
    result = engine.evaluate_scheduling(mo)
    test("Expedite high risk - decision is EXPEDITE",
         result.decision_type == MaintenanceDecisionType.EXPEDITE,
         f"got {result.decision_type}")
    test("Expedite - expedite_recommended is True",
         result.expedite_recommended,
         f"got expedite_recommended={result.expedite_recommended}")
    test("Expedite - breakdown_probability >= 0.7",
         result.breakdown_probability >= 0.7,
         f"got breakdown_probability={result.breakdown_probability}")


def test_cannot_defer_exceeded_limit():
    """defer_count >= max_defer_count => cannot defer, must SCHEDULE or EXPEDITE"""
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())
    mo = MaintenanceSnapshot(
        order_id="WO-4", asset_id="ASSET-4", site_id="SITE-1",
        maintenance_type="preventive", status="PLANNED",
        scheduled_date=date.today() + timedelta(days=5),
        last_maintenance_date=date.today() - timedelta(days=80),
        days_since_last_maintenance=80,
        maintenance_frequency_days=90,
        days_overdue=0, defer_count=2,  # at max (max_defer_count=2)
        estimated_downtime_hours=4.0, estimated_labor_hours=6.0,
        estimated_cost=2000.0, spare_parts_available=True,
        asset_criticality="normal", asset_age_years=5,
        mean_time_between_failures_days=120,
        recent_failure_count=0,
        production_schedule_load_pct=0.97,  # busy but can't defer anymore
        production_impact_units=500,
        next_production_gap_days=10,
        priority="NORMAL",
        external_cost_estimate=3000.0,
        external_lead_time_days=5,
    )
    result = engine.evaluate_scheduling(mo)
    test("Cannot defer exceeded - decision is NOT DEFER",
         result.decision_type != MaintenanceDecisionType.DEFER,
         f"got {result.decision_type}")
    test("Cannot defer exceeded - decision is SCHEDULE or EXPEDITE",
         result.decision_type in (MaintenanceDecisionType.SCHEDULE, MaintenanceDecisionType.EXPEDITE),
         f"got {result.decision_type}")


def test_outsource_internal_expensive():
    """internal cost * outsource_cost_threshold < estimated_cost => OUTSOURCE"""
    # outsource_cost_threshold=1.5: outsource when internal > 1.5x external
    # internal=9000, external=5000 => ratio=1.8 > 1.5 => outsource
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())
    mo = MaintenanceSnapshot(
        order_id="WO-5", asset_id="ASSET-5", site_id="SITE-1",
        maintenance_type="preventive", status="PLANNED",
        scheduled_date=date.today() + timedelta(days=7),
        last_maintenance_date=date.today() - timedelta(days=60),
        days_since_last_maintenance=60,
        maintenance_frequency_days=90,
        days_overdue=0, defer_count=0,
        estimated_downtime_hours=4.0, estimated_labor_hours=6.0,
        estimated_cost=9000.0,  # expensive internally
        spare_parts_available=True,
        asset_criticality="normal", asset_age_years=4,
        mean_time_between_failures_days=180,
        recent_failure_count=0,
        production_schedule_load_pct=0.50,  # low load, no defer trigger
        production_impact_units=200,
        next_production_gap_days=2,
        priority="NORMAL",
        external_cost_estimate=5000.0,  # much cheaper
        external_lead_time_days=10,
    )
    result = engine.evaluate_scheduling(mo)
    test("Outsource - decision is OUTSOURCE",
         result.decision_type == MaintenanceDecisionType.OUTSOURCE,
         f"got {result.decision_type}")
    test("Outsource - outsource_recommended is True",
         result.outsource_recommended,
         f"got outsource_recommended={result.outsource_recommended}")
    test("Outsource - outsource_savings > 0",
         result.outsource_savings > 0,
         f"got outsource_savings={result.outsource_savings}")


def test_breakdown_probability_scales_with_overdue():
    """Breakdown probability increases as days_overdue increases relative to MTBF"""
    engine = MaintenanceEngine(site_key="SITE-1", config=MaintenanceEngineConfig())

    def make_snapshot(days_overdue):
        return MaintenanceSnapshot(
            order_id=f"WO-BP-{days_overdue}", asset_id="ASSET-6", site_id="SITE-1",
            maintenance_type="preventive", status="PLANNED",
            days_since_last_maintenance=90 + days_overdue,
            maintenance_frequency_days=90,
            days_overdue=days_overdue, defer_count=0,
            estimated_cost=2000.0, spare_parts_available=True,
            asset_criticality="normal", asset_age_years=5,
            mean_time_between_failures_days=120,
            recent_failure_count=0,
            production_schedule_load_pct=0.50,
            priority="NORMAL",
        )

    prob_0 = engine._estimate_breakdown_probability(make_snapshot(0))
    prob_10 = engine._estimate_breakdown_probability(make_snapshot(10))
    prob_30 = engine._estimate_breakdown_probability(make_snapshot(30))

    test("Breakdown prob scales - 0 overdue < 10 overdue",
         prob_0 < prob_10,
         f"prob_0={prob_0:.3f}, prob_10={prob_10:.3f}")
    test("Breakdown prob scales - 10 overdue < 30 overdue",
         prob_10 < prob_30,
         f"prob_10={prob_10:.3f}, prob_30={prob_30:.3f}")
    test("Breakdown prob scales - 30 overdue is significant (> 0.2)",
         prob_30 > 0.2,
         f"prob_30={prob_30:.3f}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A8: Maintenance Engine Validation")
    print(f"{'='*60}")

    print("\n[1] Schedule on time")
    test_schedule_on_time()

    print("\n[2] Defer when production critical")
    test_defer_production_critical()

    print("\n[3] Expedite high-risk")
    test_expedite_high_risk()

    print("\n[4] Cannot defer - exceeded limit")
    test_cannot_defer_exceeded_limit()

    print("\n[5] Outsource when internal resources expensive")
    test_outsource_internal_expensive()

    print("\n[6] Breakdown probability scales with overdue")
    test_breakdown_probability_scales_with_overdue()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

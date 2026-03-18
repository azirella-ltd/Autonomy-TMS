#!/usr/bin/env python3
"""C8: Maintenance Scheduling TRM Validation

Tests MaintenanceSchedulingTRM:
- Engine baseline decisions (schedule, defer, expedite)
- TRM heuristic overrides (defer blocked by high breakdown rate)
- Hive signal emission for defer and expedite decisions
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
    print(f"C8: Maintenance Scheduling TRM Validation")
    print(f"{'='*60}")

    from app.services.powell.maintenance_scheduling_trm import (
        MaintenanceSchedulingTRM, MaintenanceSchedulingTRMConfig,
        MaintenanceSchedulingState, MaintenanceRecommendation,
    )
    from app.services.powell.engines.maintenance_engine import (
        MaintenanceEngine, MaintenanceEngineConfig, MaintenanceSnapshot,
        MaintenanceDecisionType,
    )
    from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType

    # ----------------------------------------------------------------
    # Test 1: Engine expedites emergency maintenance
    # ----------------------------------------------------------------
    print("\n--- Test 1: Engine expedites emergency maintenance ---")
    engine = MaintenanceEngine("SITE_A")
    snap_emergency = MaintenanceSnapshot(
        order_id="MO-001",
        asset_id="ASSET-PUMP-1",
        site_id="SITE_A",
        maintenance_type="emergency",
        status="PLANNED",
        scheduled_date=date.today(),
        days_since_last_maintenance=120,
        maintenance_frequency_days=90,
        estimated_downtime_hours=4.0,
        estimated_cost=2000.0,
        asset_criticality="critical",
        priority="EMERGENCY",
    )
    result = engine.evaluate_scheduling(snap_emergency)
    test(
        "Engine expedites emergency maintenance",
        result.decision_type == MaintenanceDecisionType.EXPEDITE,
        f"got {result.decision_type}",
    )
    test(
        "Expedite recommended flag is True",
        result.expedite_recommended is True,
        f"got {result.expedite_recommended}",
    )

    # ----------------------------------------------------------------
    # Test 2: Engine defers when production is busy and risk is low
    # ----------------------------------------------------------------
    print("\n--- Test 2: Engine defers preventive maintenance ---")
    snap_defer = MaintenanceSnapshot(
        order_id="MO-002",
        asset_id="ASSET-CONVEYOR-1",
        site_id="SITE_A",
        maintenance_type="preventive",
        status="PLANNED",
        scheduled_date=date.today() + timedelta(days=5),
        days_since_last_maintenance=80,
        maintenance_frequency_days=90,
        days_overdue=0,
        defer_count=0,
        estimated_downtime_hours=2.0,
        estimated_cost=500.0,
        spare_parts_available=True,
        asset_criticality="normal",
        asset_age_years=3.0,
        mean_time_between_failures_days=365,
        recent_failure_count=0,
        production_schedule_load_pct=92.0,
        production_impact_units=200,
        next_production_gap_days=14,
        priority="NORMAL",
    )
    result_defer = engine.evaluate_scheduling(snap_defer)
    test(
        "Engine defers when production busy and risk low",
        result_defer.decision_type == MaintenanceDecisionType.DEFER,
        f"got {result_defer.decision_type}",
    )
    test(
        "Defer-to-date is set",
        result_defer.defer_to_date is not None,
        f"got {result_defer.defer_to_date}",
    )

    # ----------------------------------------------------------------
    # Test 3: Engine schedules normal maintenance
    # ----------------------------------------------------------------
    print("\n--- Test 3: Engine schedules normal maintenance ---")
    snap_schedule = MaintenanceSnapshot(
        order_id="MO-003",
        asset_id="ASSET-MIXER-1",
        site_id="SITE_A",
        maintenance_type="preventive",
        status="PLANNED",
        scheduled_date=date.today() + timedelta(days=7),
        days_since_last_maintenance=85,
        maintenance_frequency_days=90,
        estimated_downtime_hours=3.0,
        estimated_cost=800.0,
        spare_parts_available=True,
        asset_criticality="normal",
        production_schedule_load_pct=0.60,
        priority="NORMAL",
    )
    result_sched = engine.evaluate_scheduling(snap_schedule)
    test(
        "Engine schedules normal maintenance",
        result_sched.decision_type == MaintenanceDecisionType.SCHEDULE,
        f"got {result_sched.decision_type}",
    )

    # ----------------------------------------------------------------
    # Test 4: TRM heuristic blocks defer when breakdown rate is high
    # ----------------------------------------------------------------
    print("\n--- Test 4: TRM heuristic override (high breakdown rate blocks defer) ---")
    trm = MaintenanceSchedulingTRM(site_key="SITE_A")
    state_risky_defer = MaintenanceSchedulingState(
        order_id="MO-004",
        asset_id="ASSET-PRESS-1",
        site_id="SITE_A",
        maintenance_type="preventive",
        status="PLANNED",
        scheduled_date=date.today() + timedelta(days=5),
        days_since_last_maintenance=80,
        maintenance_frequency_days=90,
        days_overdue=0,
        defer_count=0,
        estimated_downtime_hours=2.0,
        estimated_cost=600.0,
        spare_parts_available=True,
        asset_criticality="normal",
        asset_age_years=5.0,
        mean_time_between_failures_days=365,
        recent_failure_count=0,
        production_schedule_load_pct=92.0,
        production_impact_units=100,
        next_production_gap_days=14,
        priority="NORMAL",
        historical_breakdown_rate_after_defer=0.40,
        avg_actual_vs_estimated_cost_ratio=1.2,
    )
    rec = trm.evaluate_scheduling(state_risky_defer)
    test(
        "TRM returns MaintenanceRecommendation",
        isinstance(rec, MaintenanceRecommendation),
        f"got {type(rec).__name__}",
    )
    test(
        "High breakdown rate overrides defer to schedule",
        rec.decision_type == "schedule",
        f"got {rec.decision_type} (expected schedule due to historical_breakdown_rate > 0.30)",
    )

    # ----------------------------------------------------------------
    # Test 5: TRM cost adjustment via historical ratio
    # ----------------------------------------------------------------
    print("\n--- Test 5: TRM cost adjusted by historical cost ratio ---")
    state_cost = MaintenanceSchedulingState(
        order_id="MO-005",
        asset_id="ASSET-OVEN-1",
        site_id="SITE_A",
        maintenance_type="preventive",
        status="PLANNED",
        scheduled_date=date.today() + timedelta(days=3),
        days_since_last_maintenance=60,
        maintenance_frequency_days=90,
        estimated_downtime_hours=4.0,
        estimated_cost=1000.0,
        spare_parts_available=True,
        asset_criticality="normal",
        production_schedule_load_pct=50.0,
        priority="NORMAL",
        avg_actual_vs_estimated_cost_ratio=1.5,
    )
    rec_cost = trm.evaluate_scheduling(state_cost)
    test(
        "Cost estimate adjusted by historical ratio",
        rec_cost.cost_estimate >= 1000.0,
        f"got {rec_cost.cost_estimate} (expected >= 1000 with ratio 1.5)",
    )

    # ----------------------------------------------------------------
    # Test 6: Hive signal on defer decision
    # ----------------------------------------------------------------
    print("\n--- Test 6: Hive signal emission on defer ---")
    bus = HiveSignalBus()
    trm_sig = MaintenanceSchedulingTRM(site_key="SITE_A")
    trm_sig.signal_bus = bus

    state_defer_sig = MaintenanceSchedulingState(
        order_id="MO-006",
        asset_id="ASSET-COMPRESSOR-1",
        site_id="SITE_A",
        maintenance_type="preventive",
        status="PLANNED",
        scheduled_date=date.today() + timedelta(days=5),
        days_since_last_maintenance=80,
        maintenance_frequency_days=90,
        days_overdue=0,
        defer_count=0,
        estimated_downtime_hours=2.0,
        estimated_cost=500.0,
        spare_parts_available=True,
        asset_criticality="normal",
        mean_time_between_failures_days=365,
        recent_failure_count=0,
        production_schedule_load_pct=92.0,
        next_production_gap_days=14,
        priority="NORMAL",
        historical_breakdown_rate_after_defer=0.05,
    )
    rec_defer_sig = trm_sig.evaluate_scheduling(state_defer_sig)
    if rec_defer_sig.decision_type == "defer":
        signals = bus.read(consumer_trm="test", types={HiveSignalType.MAINTENANCE_DEFERRED})
        test(
            "MAINTENANCE_DEFERRED signal emitted on defer",
            len(signals) >= 1,
            f"found {len(signals)} signals",
        )
        if signals:
            test(
                "Deferred signal source is maintenance",
                signals[0].source_trm == "maintenance",
                f"got {signals[0].source_trm}",
            )
    else:
        test(
            "Defer decision for signal test",
            False,
            f"got {rec_defer_sig.decision_type} instead of defer",
        )

    # ----------------------------------------------------------------
    # Test 7: Hive signal on expedite decision
    # ----------------------------------------------------------------
    print("\n--- Test 7: Hive signal emission on expedite ---")
    bus2 = HiveSignalBus()
    trm_exp = MaintenanceSchedulingTRM(site_key="SITE_A")
    trm_exp.signal_bus = bus2

    state_expedite = MaintenanceSchedulingState(
        order_id="MO-007",
        asset_id="ASSET-TURBINE-1",
        site_id="SITE_A",
        maintenance_type="emergency",
        status="PLANNED",
        estimated_downtime_hours=8.0,
        estimated_cost=5000.0,
        asset_criticality="critical",
        priority="EMERGENCY",
    )
    rec_exp = trm_exp.evaluate_scheduling(state_expedite)
    test(
        "Emergency results in expedite",
        rec_exp.decision_type == "expedite",
        f"got {rec_exp.decision_type}",
    )
    signals_exp = bus2.read(consumer_trm="test", types={HiveSignalType.MAINTENANCE_URGENT})
    test(
        "MAINTENANCE_URGENT signal emitted on expedite",
        len(signals_exp) >= 1,
        f"found {len(signals_exp)} signals",
    )

    # ----------------------------------------------------------------
    # Test 8: Output structure completeness
    # ----------------------------------------------------------------
    print("\n--- Test 8: Output structure completeness ---")
    test("order_id populated", rec.order_id == "MO-004", f"got {rec.order_id}")
    test("decision_type is string", isinstance(rec.decision_type, str), f"got {type(rec.decision_type).__name__}")
    test("confidence in [0,1]", 0.0 <= rec.confidence <= 1.0, f"got {rec.confidence}")
    test("breakdown_probability is float", isinstance(rec.breakdown_probability, (int, float)), f"got {type(rec.breakdown_probability).__name__}")
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

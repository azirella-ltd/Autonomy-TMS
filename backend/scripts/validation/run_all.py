#!/usr/bin/env python3
"""
Autonomy Platform — Comprehensive Validation Runner

Runs all validation test scripts and reports results.

Usage:
  python scripts/validation/run_all.py              # Run all categories
  python scripts/validation/run_all.py --category A  # Engines only
  python scripts/validation/run_all.py --category B  # Planning only
  python scripts/validation/run_all.py --category C  # TRM agents only
  python scripts/validation/run_all.py --category F  # Hive/AAP/coordination
  python scripts/validation/run_all.py --quick       # A + F only (no DB mutations)
  python scripts/validation/run_all.py --list        # List all tests without running
"""

import os
import sys
import subprocess
import time
import argparse
from datetime import datetime
from typing import Dict, List, Tuple

# All test scripts organized by category
CATEGORIES: Dict[str, List[Tuple[str, str]]] = {
    "A": [
        ("test_engine_aatp.py", "A1: AATP Engine"),
        ("test_engine_mrp.py", "A2: MRP Engine"),
        ("test_engine_rebalancing.py", "A3: Rebalancing Engine"),
        ("test_engine_order_tracking.py", "A4: Order Tracking Engine"),
        ("test_engine_mo_execution.py", "A5: MO Execution Engine"),
        ("test_engine_to_execution.py", "A6: TO Execution Engine"),
        ("test_engine_quality.py", "A7: Quality Engine"),
        ("test_engine_maintenance.py", "A8: Maintenance Engine"),
        ("test_engine_subcontracting.py", "A9: Subcontracting Engine"),
        ("test_engine_forecast_adj.py", "A10: Forecast Adjustment Engine"),
        ("test_engine_buffer.py", "A11: Buffer Calculator Engine"),
    ],
    "B": [
        ("test_demand_planning.py", "B1: Demand Planning"),
        ("test_supply_planning.py", "B2: Supply Planning"),
        ("test_inventory_planning.py", "B3: Inventory Planning"),
        ("test_mps_generation.py", "B4: MPS Generation"),
        ("test_rccp_validation.py", "B5: RCCP Validation"),
    ],
    "C": [
        ("test_trm_atp_executor.py", "C1: ATP Executor TRM"),
        ("test_trm_inventory_rebalancing.py", "C2: Inventory Rebalancing TRM"),
        ("test_trm_po_creation.py", "C3: PO Creation TRM"),
        ("test_trm_order_tracking.py", "C4: Order Tracking TRM"),
        ("test_trm_mo_execution.py", "C5: MO Execution TRM"),
        ("test_trm_to_execution.py", "C6: TO Execution TRM"),
        ("test_trm_quality_disposition.py", "C7: Quality Disposition TRM"),
        ("test_trm_maintenance_scheduling.py", "C8: Maintenance Scheduling TRM"),
        ("test_trm_subcontracting.py", "C9: Subcontracting TRM"),
        ("test_trm_forecast_adjustment.py", "C10: Forecast Adjustment TRM"),
        ("test_trm_inventory_buffer.py", "C11: Inventory Buffer TRM"),
        ("test_trm_full_stack.py", "C12: TRM Full Stack (all 11)"),
        ("test_site_agent_cycle.py", "C13: SiteAgent 6-Phase Cycle"),
    ],
    "D": [
        ("test_cdc_full_loop.py", "D1: CDC Full Loop"),
        ("test_override_effectiveness.py", "D2: Override Effectiveness"),
        ("test_conformal_calibration.py", "D3: Conformal Calibration"),
    ],
    "E": [
        ("test_full_planning_workflow.py", "E1: Full Planning Workflow"),
        ("test_warmstart_pipeline.py", "E2: Warmstart Pipeline"),
    ],
    "F": [
        ("test_hive_signal_bus.py", "F1: Hive Signal Bus"),
        ("test_decision_cycle.py", "F2: Decision Cycle"),
        ("test_aap_authorization.py", "F3: AAP Authorization"),
        ("test_escalation_arbiter.py", "F4: Escalation Arbiter"),
        ("test_site_tgnn_inference.py", "F5: Site tGNN Inference"),
        ("test_glenday_sieve.py", "F6: Glenday Sieve"),
        ("test_checkpoint_save_load.py", "F7: Checkpoint Save/Load"),
    ],
    "G": [
        ("test_email_signal_pipeline.py", "G1: Email Signal Pipeline"),
        ("test_decision_stream.py", "G2: Decision Stream"),
        ("test_conformal_coverage.py", "G3: Conformal Coverage"),
        ("test_decision_reasoning.py", "G4: Decision Reasoning"),
    ],
}

CATEGORY_DESCRIPTIONS = {
    "A": "Deterministic Engines (no DB required)",
    "B": "Planning Engines (requires seeded DB)",
    "C": "TRM Agents (all 11 + SiteAgent)",
    "D": "Feedback Loops (CDC, overrides, conformal)",
    "E": "Integration Workflows (planning cascade, warmstart)",
    "F": "Hive, AAP & Coordination (signals, authorization, escalation)",
    "G": "Signal Pipelines & Services (email, decision stream, reasoning)",
}

QUICK_CATEGORIES = ["A", "F"]


def run_test(script_path: str, label: str, timeout: int = 120) -> Tuple[bool, float, str]:
    """Run a single test script. Returns (passed, duration_seconds, output)."""
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(script_path),
        )
        duration = time.time() - start
        output = result.stdout + result.stderr
        return result.returncode == 0, duration, output
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return False, duration, f"TIMEOUT after {timeout}s"
    except Exception as e:
        duration = time.time() - start
        return False, duration, f"ERROR: {e}"


def list_tests(categories: List[str]):
    """List all tests without running them."""
    total = 0
    for cat in categories:
        tests = CATEGORIES.get(cat, [])
        desc = CATEGORY_DESCRIPTIONS.get(cat, "")
        print(f"\nCategory {cat}: {desc} ({len(tests)} tests)")
        for script, label in tests:
            script_path = os.path.join(os.path.dirname(__file__), script)
            exists = os.path.exists(script_path)
            status = "ready" if exists else "NOT FOUND"
            print(f"  [{status:>9}] {label} — {script}")
            total += 1
    print(f"\nTotal: {total} tests")


def main():
    parser = argparse.ArgumentParser(description="Autonomy Platform Validation Runner")
    parser.add_argument("--category", "-c", type=str, help="Run specific category (A-G)")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: A + F only")
    parser.add_argument("--list", "-l", action="store_true", help="List all tests without running")
    parser.add_argument("--timeout", "-t", type=int, default=120, help="Per-test timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full test output")
    args = parser.parse_args()

    # Determine which categories to run
    if args.category:
        cats = [c.strip().upper() for c in args.category.split(",")]
        for c in cats:
            if c not in CATEGORIES:
                print(f"Unknown category: {c}. Valid: {', '.join(CATEGORIES.keys())}")
                sys.exit(1)
    elif args.quick:
        cats = QUICK_CATEGORIES
    else:
        cats = list(CATEGORIES.keys())

    if args.list:
        list_tests(cats)
        sys.exit(0)

    # Run tests
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results = {}
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_time = 0.0

    print(f"\n{'='*70}")
    print(f" Autonomy Platform — Comprehensive Validation Suite")
    print(f" Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Categories: {', '.join(cats)}")
    print(f"{'='*70}")

    for cat in cats:
        tests = CATEGORIES[cat]
        desc = CATEGORY_DESCRIPTIONS.get(cat, "")
        print(f"\n{'─'*70}")
        print(f" Category {cat}: {desc}")
        print(f"{'─'*70}")

        for script, label in tests:
            script_path = os.path.join(script_dir, script)

            if not os.path.exists(script_path):
                print(f"  SKIP: {label} — script not found")
                results[label] = ("SKIP", 0.0)
                total_skipped += 1
                continue

            passed, duration, output = run_test(script_path, label, args.timeout)
            total_time += duration

            if passed:
                status = "PASS"
                total_passed += 1
                print(f"  PASS: {label} ({duration:.1f}s)")
            else:
                status = "FAIL"
                total_failed += 1
                print(f"  FAIL: {label} ({duration:.1f}s)")

            results[label] = (status, duration)

            if args.verbose or (not passed):
                # Show output for failures always, or all output in verbose mode
                for line in output.strip().split("\n")[-10:]:
                    print(f"        {line}")

    # Summary
    total_tests = total_passed + total_failed + total_skipped
    print(f"\n{'='*70}")
    print(f" VALIDATION SUMMARY")
    print(f"{'='*70}")
    print(f" Total:   {total_tests} tests")
    print(f" Passed:  {total_passed}")
    print(f" Failed:  {total_failed}")
    print(f" Skipped: {total_skipped}")
    print(f" Time:    {total_time:.1f}s")
    print(f"{'='*70}")

    if total_failed > 0:
        print(f"\n FAILURES:")
        for label, (status, dur) in results.items():
            if status == "FAIL":
                print(f"   - {label}")

    if total_skipped > 0:
        print(f"\n SKIPPED (script not found):")
        for label, (status, dur) in results.items():
            if status == "SKIP":
                print(f"   - {label}")

    print()

    if total_failed == 0 and total_skipped == 0:
        print(" ALL TESTS PASSED")
    elif total_failed == 0:
        print(f" ALL EXECUTED TESTS PASSED ({total_skipped} skipped)")
    else:
        print(f" {total_failed} TEST(S) FAILED")

    print(f"{'='*70}\n")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()

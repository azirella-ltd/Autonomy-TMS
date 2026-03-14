#!/usr/bin/env python3
"""F2: Decision Cycle Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import importlib.util
from datetime import datetime, timezone

# Direct module load to avoid powell/__init__.py (which triggers DB config)
_POWELL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell')

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# decision_cycle.py has a lazy import of hive_signal inside detect_conflicts(),
# so we pre-register hive_signal in sys.modules for it.
_hive = _load_module("hive_signal", os.path.join(_POWELL_DIR, "hive_signal.py"))
# Also register under the relative import name used by decision_cycle
sys.modules["app.services.powell.hive_signal"] = _hive

_dc = _load_module("decision_cycle", os.path.join(_POWELL_DIR, "decision_cycle.py"))

DecisionCyclePhase = _dc.DecisionCyclePhase
PhaseResult = _dc.PhaseResult
CycleResult = _dc.CycleResult
TRM_PHASE_MAP = _dc.TRM_PHASE_MAP
PHASE_TRM_MAP = _dc.PHASE_TRM_MAP
_CANONICAL_PHASE_MAP = _dc._CANONICAL_PHASE_MAP
get_phase_for_trm = _dc.get_phase_for_trm
get_trms_for_phase = _dc.get_trms_for_phase

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
    print(f"F2: Decision Cycle Validation")
    print(f"{'='*60}")

    # ------------------------------------------------------------------
    # 1. Phase ordering
    # ------------------------------------------------------------------
    print("\n--- 1. Phase ordering ---")
    expected_order = [
        DecisionCyclePhase.SENSE,
        DecisionCyclePhase.ASSESS,
        DecisionCyclePhase.ACQUIRE,
        DecisionCyclePhase.PROTECT,
        DecisionCyclePhase.BUILD,
        DecisionCyclePhase.REFLECT,
    ]
    test("6 phases defined", len(DecisionCyclePhase) == 6, f"got {len(DecisionCyclePhase)}")

    for i in range(len(expected_order) - 1):
        a = expected_order[i]
        b = expected_order[i + 1]
        test(
            f"{a.name} < {b.name}",
            a < b,
            f"{a.name}={int(a)}, {b.name}={int(b)}",
        )

    test("SENSE=1", int(DecisionCyclePhase.SENSE) == 1, f"got {int(DecisionCyclePhase.SENSE)}")
    test("REFLECT=6", int(DecisionCyclePhase.REFLECT) == 6, f"got {int(DecisionCyclePhase.REFLECT)}")

    # ------------------------------------------------------------------
    # 2. TRM-to-phase mapping
    # ------------------------------------------------------------------
    print("\n--- 2. TRM-to-phase mapping ---")
    canonical_trms = {
        "atp_executor": DecisionCyclePhase.SENSE,
        "order_tracking": DecisionCyclePhase.SENSE,
        "inventory_buffer": DecisionCyclePhase.ASSESS,
        "forecast_adjustment": DecisionCyclePhase.ASSESS,
        "quality_disposition": DecisionCyclePhase.ASSESS,
        "po_creation": DecisionCyclePhase.ACQUIRE,
        "subcontracting": DecisionCyclePhase.ACQUIRE,
        "maintenance_scheduling": DecisionCyclePhase.PROTECT,
        "mo_execution": DecisionCyclePhase.BUILD,
        "to_execution": DecisionCyclePhase.BUILD,
        "rebalancing": DecisionCyclePhase.REFLECT,
    }

    test(
        "11 canonical TRMs in _CANONICAL_PHASE_MAP",
        len(_CANONICAL_PHASE_MAP) == 11,
        f"got {len(_CANONICAL_PHASE_MAP)}: {list(_CANONICAL_PHASE_MAP.keys())}",
    )

    for trm_name, expected_phase in canonical_trms.items():
        actual = get_phase_for_trm(trm_name)
        test(
            f"{trm_name} -> {expected_phase.name}",
            actual == expected_phase,
            f"expected {expected_phase.name}, got {actual.name}",
        )

    # Aliases
    test(
        "forecast_adj alias -> ASSESS",
        get_phase_for_trm("forecast_adj") == DecisionCyclePhase.ASSESS,
        f"got {get_phase_for_trm('forecast_adj').name}",
    )

    # Unknown TRM raises ValueError
    try:
        get_phase_for_trm("nonexistent_trm")
        test("Unknown TRM raises ValueError", False, "no exception raised")
    except ValueError:
        test("Unknown TRM raises ValueError", True)

    # ------------------------------------------------------------------
    # 3. CycleResult structure
    # ------------------------------------------------------------------
    print("\n--- 3. CycleResult structure ---")
    cr = CycleResult()
    test("CycleResult has cycle_id (UUID)", len(cr.cycle_id) == 36, f"got {cr.cycle_id!r}")
    test("CycleResult has started_at", isinstance(cr.started_at, datetime), f"type={type(cr.started_at)}")
    test("CycleResult has phases (list)", isinstance(cr.phases, list), f"type={type(cr.phases)}")
    test("CycleResult has total_duration_ms", isinstance(cr.total_duration_ms, float), f"type={type(cr.total_duration_ms)}")
    test("CycleResult has total_signals_emitted", isinstance(cr.total_signals_emitted, int), f"type={type(cr.total_signals_emitted)}")
    test("Empty cycle success=True", cr.success is True, f"got {cr.success}")

    d = cr.to_dict()
    test("to_dict has cycle_id", "cycle_id" in d, f"keys: {list(d.keys())}")
    test("to_dict has phases", "phases" in d, f"keys: {list(d.keys())}")
    test("to_dict has success", "success" in d, f"keys: {list(d.keys())}")

    # ------------------------------------------------------------------
    # 4. PhaseResult structure
    # ------------------------------------------------------------------
    print("\n--- 4. PhaseResult structure ---")
    pr = PhaseResult(phase=DecisionCyclePhase.SENSE)
    test("PhaseResult.phase is SENSE", pr.phase == DecisionCyclePhase.SENSE, f"got {pr.phase}")
    test("PhaseResult.trms_executed is list", isinstance(pr.trms_executed, list), f"type={type(pr.trms_executed)}")
    test("PhaseResult.signals_emitted default 0", pr.signals_emitted == 0, f"got {pr.signals_emitted}")
    test("PhaseResult.success default True", pr.success is True, f"got {pr.success}")

    pr_err = PhaseResult(phase=DecisionCyclePhase.BUILD, errors=["MO release failed"])
    test("PhaseResult with error -> success=False", pr_err.success is False, f"got {pr_err.success}")

    d2 = pr.to_dict()
    test("PhaseResult to_dict has phase", "phase" in d2, f"keys: {list(d2.keys())}")
    test("PhaseResult to_dict phase_number=1", d2.get("phase_number") == 1, f"got {d2.get('phase_number')}")

    cr2 = CycleResult()
    cr2.phases.append(PhaseResult(phase=DecisionCyclePhase.SENSE))
    cr2.phases.append(pr_err)
    test("CycleResult with failed phase -> success=False", cr2.success is False, f"got {cr2.success}")

    # ------------------------------------------------------------------
    # 5. Empty cycle and PHASE_TRM_MAP coverage
    # ------------------------------------------------------------------
    print("\n--- 5. Empty cycle and reverse map ---")
    cr_empty = CycleResult()
    test("Empty cycle phases_completed=0", cr_empty.phases_completed == 0, f"got {cr_empty.phases_completed}")
    test("Empty cycle success=True", cr_empty.success is True, f"got {cr_empty.success}")

    all_phases_covered = all(phase in PHASE_TRM_MAP for phase in DecisionCyclePhase)
    test("PHASE_TRM_MAP covers all 6 phases", all_phases_covered, f"keys: {list(PHASE_TRM_MAP.keys())}")

    all_trms_from_reverse = set()
    for trms in PHASE_TRM_MAP.values():
        all_trms_from_reverse.update(trms)
    test(
        "PHASE_TRM_MAP contains all 11 canonical TRMs",
        len(all_trms_from_reverse) == 11,
        f"got {len(all_trms_from_reverse)}: {all_trms_from_reverse}",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

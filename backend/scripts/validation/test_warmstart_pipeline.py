#!/usr/bin/env python3
"""E2: Warm-Start Provisioning Pipeline Validation — 14-step Powell Cascade"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
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
    print(f"E2: Warm-Start Provisioning Pipeline Validation")
    print(f"{'='*60}")

    # ── 1. ConfigProvisioningStatus model ──────────────────────────────
    print("\n--- ConfigProvisioningStatus Model ---")
    try:
        from app.models.user_directive import ConfigProvisioningStatus
        test("ConfigProvisioningStatus importable", True)
    except ImportError as e:
        test("ConfigProvisioningStatus importable", False, str(e))

    # ── 2. All 14 steps defined ────────────────────────────────────────
    print("\n--- Step Definitions ---")
    try:
        steps = ConfigProvisioningStatus.STEPS
        expected_steps = [
            "warm_start", "sop_graphsage", "cfa_optimization",
            "lgbm_forecast", "demand_tgnn", "supply_tgnn", "inventory_tgnn",
            "trm_training", "supply_plan", "rccp_validation", "decision_seed",
            "site_tgnn", "conformal", "briefing",
        ]
        test(f"STEPS has 14 entries (found {len(steps)})",
             len(steps) == 14,
             f"Steps: {steps}")
        test("STEPS matches expected 14-step list",
             steps == expected_steps,
             f"Got: {steps}")
        test("rccp_validation is in STEPS",
             "rccp_validation" in steps,
             f"Steps: {steps}")
    except Exception as e:
        test("STEPS definition", False, str(e))

    # ── 3. All 14 step labels ──────────────────────────────────────────
    print("\n--- Step Labels ---")
    try:
        labels = ConfigProvisioningStatus.STEP_LABELS
        test(f"STEP_LABELS has {len(labels)} entries (expected 14)",
             len(labels) == 14,
             f"Labels: {list(labels.keys())}")

        # Every step in STEPS must have a label
        missing_labels = [s for s in steps if s not in labels]
        test("Every step has a label",
             len(missing_labels) == 0,
             f"Missing labels for: {missing_labels}")

        # Specific label checks
        test("warm_start label is 'Historical Demand Simulation'",
             labels.get("warm_start") == "Historical Demand Simulation",
             f"Got: {labels.get('warm_start')}")
        test("rccp_validation label is 'Rough-Cut Capacity Validation'",
             labels.get("rccp_validation") == "Rough-Cut Capacity Validation",
             f"Got: {labels.get('rccp_validation')}")
        test("briefing label is 'Executive Briefing'",
             labels.get("briefing") == "Executive Briefing",
             f"Got: {labels.get('briefing')}")
    except Exception as e:
        test("STEP_LABELS", False, str(e))

    # ── 4. Dependency graph ────────────────────────────────────────────
    print("\n--- Dependency Graph ---")
    try:
        deps = ConfigProvisioningStatus.STEP_DEPENDS
        test("STEP_DEPENDS exists and is dict",
             isinstance(deps, dict),
             f"Type: {type(deps)}")

        # Every step in STEPS should have a dependency entry
        missing_deps = [s for s in steps if s not in deps]
        test("Every step has a dependency entry",
             len(missing_deps) == 0,
             f"Missing dependency entries for: {missing_deps}")

        # warm_start has no dependencies (root)
        test("warm_start has no dependencies (root node)",
             deps.get("warm_start") == [],
             f"Got: {deps.get('warm_start')}")

        # Specific dependency checks
        test("rccp_validation depends on supply_plan",
             "supply_plan" in deps.get("rccp_validation", []),
             f"rccp_validation deps: {deps.get('rccp_validation')}")

        test("briefing depends on supply_plan",
             "supply_plan" in deps.get("briefing", []),
             f"briefing deps: {deps.get('briefing')}")

        test("briefing depends on decision_seed",
             "decision_seed" in deps.get("briefing", []),
             f"briefing deps: {deps.get('briefing')}")

        test("sop_graphsage depends on warm_start",
             "warm_start" in deps.get("sop_graphsage", []),
             f"sop_graphsage deps: {deps.get('sop_graphsage')}")

        test("trm_training depends on demand_tgnn",
             "demand_tgnn" in deps.get("trm_training", []),
             f"trm_training deps: {deps.get('trm_training')}")

        test("supply_plan depends on cfa_optimization",
             "cfa_optimization" in deps.get("supply_plan", []),
             f"supply_plan deps: {deps.get('supply_plan')}")

        test("conformal depends on warm_start",
             "warm_start" in deps.get("conformal", []),
             f"conformal deps: {deps.get('conformal')}")
    except Exception as e:
        test("Dependency graph", False, str(e))

    # ── 5. No circular dependencies ────────────────────────────────────
    print("\n--- Circular Dependency Check ---")
    try:
        def detect_cycle(graph, steps_list):
            """DFS-based cycle detection."""
            WHITE, GRAY, BLACK = 0, 1, 2
            color = {s: WHITE for s in steps_list}

            def dfs(node):
                color[node] = GRAY
                for dep in graph.get(node, []):
                    if dep not in color:
                        continue
                    if color[dep] == GRAY:
                        return True  # Back edge = cycle
                    if color[dep] == WHITE and dfs(dep):
                        return True
                color[node] = BLACK
                return False

            for step in steps_list:
                if color[step] == WHITE:
                    if dfs(step):
                        return True
            return False

        has_cycle = detect_cycle(deps, steps)
        test("No circular dependencies in STEP_DEPENDS",
             not has_cycle,
             "Circular dependency detected!")
    except Exception as e:
        test("Circular dependency check", False, str(e))

    # ── 6. All dependencies reference valid steps ──────────────────────
    print("\n--- Dependency Validity ---")
    try:
        step_set = set(steps)
        invalid_deps = []
        for step, step_deps in deps.items():
            for d in step_deps:
                if d not in step_set:
                    invalid_deps.append(f"{step} -> {d}")
        test("All dependencies reference valid steps",
             len(invalid_deps) == 0,
             f"Invalid deps: {invalid_deps}")
    except Exception as e:
        test("Dependency validity", False, str(e))

    # ── 7. Model columns for each step ─────────────────────────────────
    print("\n--- Model Columns ---")
    try:
        cols = {c.name for c in ConfigProvisioningStatus.__table__.columns}

        missing_status = []
        missing_at = []
        missing_error = []
        for step in steps:
            if f"{step}_status" not in cols:
                missing_status.append(step)
            if f"{step}_at" not in cols:
                missing_at.append(step)
            if f"{step}_error" not in cols:
                missing_error.append(step)

        test("All 14 steps have _status columns",
             len(missing_status) == 0,
             f"Missing _status for: {missing_status}")
        test("All 14 steps have _at columns",
             len(missing_at) == 0,
             f"Missing _at for: {missing_at}")
        test("All 14 steps have _error columns",
             len(missing_error) == 0,
             f"Missing _error for: {missing_error}")

        test("overall_status column exists",
             "overall_status" in cols,
             f"Missing overall_status")
        test("config_id column exists",
             "config_id" in cols,
             f"Missing config_id")
    except Exception as e:
        test("Model columns", False, str(e))

    # ── 8. ProvisioningService ─────────────────────────────────────────
    print("\n--- ProvisioningService ---")
    try:
        from app.services.provisioning_service import ProvisioningService
        test("ProvisioningService importable", True)
    except ImportError as e:
        test("ProvisioningService importable", False, str(e))

    try:
        test("run_step method exists",
             hasattr(ProvisioningService, 'run_step'),
             "Missing run_step")
        test("run_all method exists",
             hasattr(ProvisioningService, 'run_all'),
             "Missing run_all")
        test("get_or_create_status method exists",
             hasattr(ProvisioningService, 'get_or_create_status'),
             "Missing get_or_create_status")
        test("_execute_step method exists",
             hasattr(ProvisioningService, '_execute_step'),
             "Missing _execute_step")
    except NameError:
        test("ProvisioningService methods", False, "Class not imported")

    # ── 9. Step handler methods ────────────────────────────────────────
    print("\n--- Step Handler Methods ---")
    try:
        # Check for step handler methods (pattern: _step_{step_key})
        handler_steps = []
        missing_handlers = []
        for step in steps:
            handler_name = f"_step_{step}"
            if hasattr(ProvisioningService, handler_name):
                handler_steps.append(step)
            else:
                missing_handlers.append(step)

        test(f"Handler methods found for {len(handler_steps)}/{len(steps)} steps",
             len(handler_steps) > 0,
             f"No handlers found. Checked: _step_warm_start, _step_sop_graphsage, etc.")

        if handler_steps:
            print(f"    Steps with handlers: {handler_steps}")
        if missing_handlers:
            print(f"    Steps using _execute_step fallback: {missing_handlers}")
    except NameError:
        test("Handler methods", False, "ProvisioningService not imported")

    # ── 10. to_dict serialization ──────────────────────────────────────
    print("\n--- Serialization ---")
    try:
        test("ConfigProvisioningStatus has to_dict()",
             hasattr(ConfigProvisioningStatus, 'to_dict'),
             "Missing to_dict method")
    except NameError:
        test("to_dict method", False, "Model not imported")

    # ── 11. DB-dependent tests ─────────────────────────────────────────
    print("\n--- DB Verification (optional) ---")
    try:
        from app.db.session import sync_session_factory
        db = sync_session_factory()
        status_count = db.query(ConfigProvisioningStatus).count()
        test(f"ConfigProvisioningStatus table accessible ({status_count} rows)",
             True)
        db.close()
    except Exception as e:
        print(f"  SKIP: DB tests (no connection): {e}")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

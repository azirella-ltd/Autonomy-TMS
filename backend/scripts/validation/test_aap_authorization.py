#!/usr/bin/env python3
"""F3: Agentic Authorization Protocol (AAP) Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import importlib.util

# Direct module load to avoid package __init__.py chains that trigger DB config
_SERVICES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services')
_POWELL_DIR = os.path.join(_SERVICES_DIR, 'powell')

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Load authorization_protocol first (defines ActionCategory, AgentRole)
_aap = _load_module(
    "app.services.authorization_protocol",
    os.path.join(_SERVICES_DIR, "authorization_protocol.py"),
)
ActionCategory = _aap.ActionCategory
AgentRole = _aap.AgentRole

# Load authority_boundaries (imports from authorization_protocol)
_ab = _load_module(
    "app.services.powell.authority_boundaries",
    os.path.join(_POWELL_DIR, "authority_boundaries.py"),
)
AUTHORITY_BOUNDARIES = _ab.AUTHORITY_BOUNDARIES
AuthorityBoundary = _ab.AuthorityBoundary
AuthorizationTarget = _ab.AuthorizationTarget
get_authority_boundary = _ab.get_authority_boundary
check_action_category = _ab.check_action_category
get_required_target = _ab.get_required_target
get_all_actions = _ab.get_all_actions

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
    print(f"F3: Agentic Authorization Protocol Validation")
    print(f"{'='*60}")

    # ------------------------------------------------------------------
    # 1. Agent roles defined
    # ------------------------------------------------------------------
    print("\n--- 1. Agent roles defined ---")
    all_roles = list(AgentRole)
    test(
        f"AgentRole has 16 roles",
        len(all_roles) == 16,
        f"got {len(all_roles)}: {[r.value for r in all_roles]}",
    )

    expected_roles = [
        "so_atp", "supply", "allocation", "logistics", "inventory",
        "sop", "plant", "quality", "maintenance", "procurement",
        "supplier", "channel", "demand", "finance", "service", "risk",
    ]
    for role_val in expected_roles:
        found = any(r.value == role_val for r in all_roles)
        test(f"AgentRole.{role_val} exists", found, f"not found in {[r.value for r in all_roles]}")

    roles_with_boundaries = list(AUTHORITY_BOUNDARIES.keys())
    test(
        f"Authority boundaries defined for >= 13 roles",
        len(roles_with_boundaries) >= 13,
        f"got {len(roles_with_boundaries)}: {[r.value for r in roles_with_boundaries]}",
    )

    # ------------------------------------------------------------------
    # 2. UNILATERAL actions don't need auth
    # ------------------------------------------------------------------
    print("\n--- 2. UNILATERAL actions ---")

    cat = check_action_category(AgentRole.SO_ATP, "reallocate_within_tier")
    test("SO_ATP reallocate_within_tier is UNILATERAL", cat == ActionCategory.UNILATERAL, f"got {cat}")

    cat2 = check_action_category(AgentRole.QUALITY, "hold_lot")
    test("QUALITY hold_lot is UNILATERAL", cat2 == ActionCategory.UNILATERAL, f"got {cat2}")

    cat3 = check_action_category(AgentRole.PLANT, "sequence_within_shift")
    test("PLANT sequence_within_shift is UNILATERAL", cat3 == ActionCategory.UNILATERAL, f"got {cat3}")

    cat4 = check_action_category(AgentRole.MAINTENANCE, "schedule_pm")
    test("MAINTENANCE schedule_pm is UNILATERAL", cat4 == ActionCategory.UNILATERAL, f"got {cat4}")

    target = get_required_target(AgentRole.SO_ATP, "reallocate_within_tier")
    test("UNILATERAL action target is None", target is None, f"got {target}")

    # ------------------------------------------------------------------
    # 3. REQUIRES_AUTHORIZATION routes to correct target
    # ------------------------------------------------------------------
    print("\n--- 3. REQUIRES_AUTHORIZATION routing ---")

    cat5 = check_action_category(AgentRole.SO_ATP, "request_expedite")
    test("SO_ATP request_expedite requires auth", cat5 == ActionCategory.REQUIRES_AUTHORIZATION, f"got {cat5}")
    target5 = get_required_target(AgentRole.SO_ATP, "request_expedite")
    test(
        "request_expedite routes to LOGISTICS",
        target5 is not None and target5.target_agent == AgentRole.LOGISTICS,
        f"target={target5}",
    )

    cat6 = check_action_category(AgentRole.PLANT, "insert_rush_order")
    test("PLANT insert_rush_order requires auth", cat6 == ActionCategory.REQUIRES_AUTHORIZATION, f"got {cat6}")
    target6 = get_required_target(AgentRole.PLANT, "insert_rush_order")
    test(
        "insert_rush_order routes to SO_ATP",
        target6 is not None and target6.target_agent == AgentRole.SO_ATP,
        f"target={target6}",
    )

    target7 = get_required_target(AgentRole.INVENTORY, "cross_dc_transfer")
    test(
        "cross_dc_transfer routes to LOGISTICS",
        target7 is not None and target7.target_agent == AgentRole.LOGISTICS,
        f"target={target7}",
    )

    target8 = get_required_target(AgentRole.PROCUREMENT, "new_supplier_qualification")
    test(
        "new_supplier_qualification routes to QUALITY",
        target8 is not None and target8.target_agent == AgentRole.QUALITY,
        f"target={target8}",
    )

    test(
        "request_expedite SLA=60 min",
        target5 is not None and target5.sla_minutes == 60,
        f"sla={target5.sla_minutes if target5 else 'N/A'}",
    )

    # ------------------------------------------------------------------
    # 4. FORBIDDEN actions are blocked
    # ------------------------------------------------------------------
    print("\n--- 4. FORBIDDEN actions ---")

    cat_f1 = check_action_category(AgentRole.SO_ATP, "override_priority")
    test("SO_ATP override_priority is FORBIDDEN", cat_f1 == ActionCategory.FORBIDDEN, f"got {cat_f1}")

    cat_f2 = check_action_category(AgentRole.PLANT, "shutdown_line")
    test("PLANT shutdown_line is FORBIDDEN", cat_f2 == ActionCategory.FORBIDDEN, f"got {cat_f2}")

    cat_f3 = check_action_category(AgentRole.FINANCE, "capex_approval")
    test("FINANCE capex_approval is FORBIDDEN", cat_f3 == ActionCategory.FORBIDDEN, f"got {cat_f3}")

    cat_f4 = check_action_category(AgentRole.PROCUREMENT, "change_contract_terms")
    test("PROCUREMENT change_contract_terms is FORBIDDEN", cat_f4 == ActionCategory.FORBIDDEN, f"got {cat_f4}")

    target_f = get_required_target(AgentRole.SO_ATP, "override_priority")
    test("FORBIDDEN action target is None", target_f is None, f"got {target_f}")

    # ------------------------------------------------------------------
    # 5. Authority boundary lookup for all roles
    # ------------------------------------------------------------------
    print("\n--- 5. Authority boundary lookup ---")

    for role in AgentRole:
        boundary = get_authority_boundary(role)
        test(
            f"get_authority_boundary({role.value})",
            isinstance(boundary, AuthorityBoundary),
            f"type={type(boundary)}",
        )
        test(
            f"  boundary.agent_role matches",
            boundary.agent_role == role,
            f"expected {role}, got {boundary.agent_role}",
        )

    cat_unknown = check_action_category(AgentRole.SO_ATP, "totally_unknown_action")
    test(
        "Unknown action defaults to REQUIRES_AUTHORIZATION",
        cat_unknown == ActionCategory.REQUIRES_AUTHORIZATION,
        f"got {cat_unknown}",
    )

    all_actions = get_all_actions(AgentRole.SO_ATP)
    test(
        "get_all_actions returns non-empty dict",
        isinstance(all_actions, dict) and len(all_actions) > 0,
        f"got {type(all_actions)} len={len(all_actions)}",
    )
    for action, cat in all_actions.items():
        test(
            f"  SO_ATP action '{action}' has valid category",
            cat in (ActionCategory.UNILATERAL, ActionCategory.REQUIRES_AUTHORIZATION, ActionCategory.FORBIDDEN),
            f"got {cat}",
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

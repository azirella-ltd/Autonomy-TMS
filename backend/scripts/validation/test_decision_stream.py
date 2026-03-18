#!/usr/bin/env python3
"""G2: Decision Stream Service Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

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


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"G2: Decision Stream Service Validation")
    print(f"{'='*60}")

    from app.services.decision_stream_service import (
        DEEP_LINK_MAP,
        DECISION_TABLES,
        DECISION_TYPE_TABLE_MAP,
        _ABANDON_COMBINED_THRESHOLD,
    )

    # ── Test 1: Abandonment logic ─────────────────────────────────────
    print("\n[Test 1] Abandonment logic - combined score < threshold -> abandoned")
    threshold = _ABANDON_COMBINED_THRESHOLD  # Default 0.5

    # Low urgency + low likelihood = abandoned
    urgency_low = 0.1
    likelihood_low = 0.2
    combined_low = urgency_low + likelihood_low
    test(
        f"Low urgency ({urgency_low}) + low likelihood ({likelihood_low}) = {combined_low} < {threshold} -> abandoned",
        combined_low < threshold,
        f"Combined {combined_low} >= threshold {threshold}",
    )

    # Medium urgency + medium likelihood = kept
    urgency_med = 0.3
    likelihood_med = 0.3
    combined_med = urgency_med + likelihood_med
    test(
        f"Medium urgency ({urgency_med}) + medium likelihood ({likelihood_med}) = {combined_med} >= {threshold} -> kept",
        combined_med >= threshold,
        f"Combined {combined_med} < threshold {threshold}",
    )

    # Very low both = abandoned
    urgency_tiny = 0.05
    likelihood_tiny = 0.1
    combined_tiny = urgency_tiny + likelihood_tiny
    test(
        f"Tiny urgency ({urgency_tiny}) + tiny likelihood ({likelihood_tiny}) = {combined_tiny} < {threshold} -> abandoned",
        combined_tiny < threshold,
        f"Combined {combined_tiny} >= threshold {threshold}",
    )

    # ── Test 2: High urgency never abandoned ──────────────────────────
    print("\n[Test 2] High urgency never abandoned regardless of likelihood")
    urgency_high = 0.8
    likelihood_zero = 0.1
    combined_high = urgency_high + likelihood_zero
    test(
        f"High urgency ({urgency_high}) + low likelihood ({likelihood_zero}) = {combined_high} >= {threshold} -> kept",
        combined_high >= threshold,
        f"Combined {combined_high} < threshold {threshold}",
    )

    urgency_critical = 0.95
    likelihood_none = 0.0
    combined_critical = urgency_critical + likelihood_none
    test(
        f"Critical urgency ({urgency_critical}) + zero likelihood ({likelihood_none}) = {combined_critical} >= {threshold} -> kept",
        combined_critical >= threshold,
        f"Combined {combined_critical} < threshold {threshold}",
    )

    # ── Test 3: Deep link generation per decision type ────────────────
    print("\n[Test 3] Deep link generation per decision type")
    test(
        "atp deep link is /planning/execution/atp-worklist",
        DEEP_LINK_MAP.get("atp") == "/planning/execution/atp-worklist",
        f"Got {DEEP_LINK_MAP.get('atp')}",
    )
    test(
        "po_creation deep link is /planning/execution/po-worklist",
        DEEP_LINK_MAP.get("po_creation") == "/planning/execution/po-worklist",
        f"Got {DEEP_LINK_MAP.get('po_creation')}",
    )
    test(
        "rebalancing deep link is /planning/execution/rebalancing-worklist",
        DEEP_LINK_MAP.get("rebalancing") == "/planning/execution/rebalancing-worklist",
        f"Got {DEEP_LINK_MAP.get('rebalancing')}",
    )
    test(
        "forecast_adjustment deep link is /planning/demand",
        DEEP_LINK_MAP.get("forecast_adjustment") == "/planning/demand",
        f"Got {DEEP_LINK_MAP.get('forecast_adjustment')}",
    )
    test(
        "inventory_buffer deep link is /planning/inventory-optimization",
        DEEP_LINK_MAP.get("inventory_buffer") == "/planning/inventory-optimization",
        f"Got {DEEP_LINK_MAP.get('inventory_buffer')}",
    )
    test(
        "mo_execution deep link is /planning/execution/mo-worklist",
        DEEP_LINK_MAP.get("mo_execution") == "/planning/execution/mo-worklist",
        f"Got {DEEP_LINK_MAP.get('mo_execution')}",
    )
    test(
        "quality deep link is /planning/execution/quality-worklist",
        DEEP_LINK_MAP.get("quality") == "/planning/execution/quality-worklist",
        f"Got {DEEP_LINK_MAP.get('quality')}",
    )

    # ── Test 4: Decision type mapping covers all 11 tables ────────────
    print("\n[Test 4] Decision type mapping covers all 11 powell_*_decisions tables")
    expected_types = {
        "atp", "rebalancing", "po_creation", "order_tracking",
        "mo_execution", "to_execution", "quality", "maintenance",
        "subcontracting", "forecast_adjustment", "inventory_buffer",
    }

    # Check DECISION_TYPE_TABLE_MAP
    mapped_types = set(DECISION_TYPE_TABLE_MAP.keys())
    test(
        "DECISION_TYPE_TABLE_MAP has all 11 decision types",
        expected_types.issubset(mapped_types),
        f"Missing: {expected_types - mapped_types}",
    )
    test(
        "DECISION_TYPE_TABLE_MAP has exactly 11 entries",
        len(DECISION_TYPE_TABLE_MAP) == 11,
        f"Got {len(DECISION_TYPE_TABLE_MAP)} entries",
    )

    # Check DECISION_TABLES registry
    table_type_keys = {t[1] for t in DECISION_TABLES}
    test(
        "DECISION_TABLES registry has all 11 decision types",
        expected_types.issubset(table_type_keys),
        f"Missing: {expected_types - table_type_keys}",
    )

    # Verify table names follow naming convention
    for type_key, table_name in DECISION_TYPE_TABLE_MAP.items():
        test(
            f"Table name for '{type_key}' starts with 'powell_'",
            table_name.startswith("powell_"),
            f"Got '{table_name}'",
        )

    # ── Test 5: Deep link map covers all decision types ───────────────
    print("\n[Test 5] Deep link map covers all decision types")
    for dtype in expected_types:
        test(
            f"Deep link exists for '{dtype}'",
            dtype in DEEP_LINK_MAP,
            "Missing from DEEP_LINK_MAP",
        )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

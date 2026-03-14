#!/usr/bin/env python3
"""A9: Subcontracting Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import date, datetime, timedelta

# Direct import to avoid __init__.py chains that require DB config
_engine_path = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'app', 'services', 'powell', 'engines', 'subcontracting_engine.py',
)
_spec = importlib.util.spec_from_file_location('subcontracting_engine', _engine_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SubcontractingEngine = _mod.SubcontractingEngine
SubcontractingEngineConfig = _mod.SubcontractingEngineConfig
SubcontractSnapshot = _mod.SubcontractSnapshot
SubcontractingResult = _mod.SubcontractingResult
SubcontractDecisionType = _mod.SubcontractDecisionType
SubcontractReason = _mod.SubcontractReason

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


def base_snapshot(**overrides) -> SubcontractSnapshot:
    """Build a baseline snapshot with sensible defaults, applying overrides."""
    # NOTE: internal_capacity_pct is compared against config threshold (default 0.90)
    # as a raw number, so use fractional values (0.0-1.0) to match the engine logic.
    defaults = dict(
        product_id="PROD-1",
        site_id="SITE-1",
        required_quantity=1000,
        required_by_date=date.today() + timedelta(days=14),
        internal_capacity_available=200,
        internal_capacity_total=1000,
        internal_capacity_pct=0.80,
        internal_cost_per_unit=10.0,
        internal_lead_time_days=7,
        internal_quality_yield_pct=0.98,
        subcontractor_id="SUB-1",
        subcontractor_cost_per_unit=12.0,
        subcontractor_lead_time_days=10,
        subcontractor_quality_score=0.92,
        subcontractor_on_time_score=0.88,
        subcontractor_capacity_available=800,
        is_critical_product=False,
        has_special_tooling=False,
        ip_sensitivity="low",
        current_external_pct=0.20,
        demand_forecast_next_30_days=3000,
        backlog_quantity=500,
    )
    defaults.update(overrides)
    return SubcontractSnapshot(**defaults)


# ── Test 1: Keep internal when capacity available ────────────────────────
def test_keep_internal_capacity_available():
    """internal_capacity_pct well below trigger (0.90) → KEEP_INTERNAL"""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(internal_capacity_pct=0.70)
    result = engine.evaluate_routing(snap)

    test(
        "keep_internal_capacity_available — decision is KEEP_INTERNAL",
        result.decision_type == SubcontractDecisionType.KEEP_INTERNAL,
        f"got {result.decision_type}",
    )
    test(
        "keep_internal_capacity_available — full qty internal",
        result.internal_quantity == 1000,
        f"got {result.internal_quantity}",
    )
    test(
        "keep_internal_capacity_available — no external qty",
        result.external_quantity == 0,
        f"got {result.external_quantity}",
    )


# ── Test 2: Route external on capacity constraint ────────────────────────
def test_route_external_capacity_constraint():
    """internal_capacity_pct > trigger, good vendor scores → routes externally"""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(
        internal_capacity_pct=0.96,
        subcontractor_quality_score=0.95,
        subcontractor_on_time_score=0.92,
    )
    result = engine.evaluate_routing(snap)

    test(
        "route_external_capacity — decision is SPLIT or ROUTE_EXTERNAL",
        result.decision_type in (
            SubcontractDecisionType.ROUTE_EXTERNAL,
            SubcontractDecisionType.SPLIT,
        ),
        f"got {result.decision_type}",
    )
    test(
        "route_external_capacity — external_quantity > 0",
        result.external_quantity > 0,
        f"got {result.external_quantity}",
    )
    test(
        "route_external_capacity — recommended vendor set",
        result.recommended_vendor == "SUB-1",
        f"got {result.recommended_vendor}",
    )


# ── Test 3: Split when partial capacity ──────────────────────────────────
def test_split_partial_capacity():
    """Internal can only satisfy part; remainder goes external (split)."""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(
        required_quantity=1000,
        internal_capacity_pct=0.95,
        internal_capacity_total=1000,
    )
    result = engine.evaluate_routing(snap)

    test(
        "split_partial — decision is SPLIT or ROUTE_EXTERNAL",
        result.decision_type in (
            SubcontractDecisionType.SPLIT,
            SubcontractDecisionType.ROUTE_EXTERNAL,
        ),
        f"got {result.decision_type}",
    )
    total = result.internal_quantity + result.external_quantity
    test(
        "split_partial — internal + external = required_quantity",
        abs(total - 1000) < 1e-6,
        f"got {total}",
    )
    test(
        "split_partial — external ≤ max_external_pct (70%)",
        result.external_quantity <= 1000 * 0.70 + 1e-6,
        f"got {result.external_quantity}",
    )
    test(
        "split_partial — cost totals consistent",
        abs(result.total_cost - (result.internal_cost + result.external_cost)) < 1e-6,
        f"internal_cost={result.internal_cost}, external_cost={result.external_cost}, total={result.total_cost}",
    )


# ── Test 4: Reject vendor with low quality ───────────────────────────────
def test_reject_low_quality_vendor():
    """Vendor quality_score < min_vendor_quality_score (0.85) → KEEP_INTERNAL"""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(
        internal_capacity_pct=0.96,
        subcontractor_quality_score=0.70,
    )
    result = engine.evaluate_routing(snap)

    test(
        "reject_low_quality — decision is KEEP_INTERNAL",
        result.decision_type == SubcontractDecisionType.KEEP_INTERNAL,
        f"got {result.decision_type}",
    )
    test(
        "reject_low_quality — reason mentions quality",
        "quality" in result.primary_reason.lower(),
        f"got reason='{result.primary_reason}'",
    )
    test(
        "reject_low_quality — quality_risk set",
        result.quality_risk > 0,
        f"got {result.quality_risk}",
    )


# ── Test 5: IP sensitivity blocks external ───────────────────────────────
def test_ip_sensitivity_blocks_external():
    """ip_sensitivity='high' → KEEP_INTERNAL even if capacity constrained"""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(
        internal_capacity_pct=0.99,
        ip_sensitivity="high",
    )
    result = engine.evaluate_routing(snap)

    test(
        "ip_sensitivity — decision is KEEP_INTERNAL",
        result.decision_type == SubcontractDecisionType.KEEP_INTERNAL,
        f"got {result.decision_type}",
    )
    test(
        "ip_sensitivity — ip_risk = 1.0",
        result.ip_risk == 1.0,
        f"got {result.ip_risk}",
    )
    test(
        "ip_sensitivity — reason is ip_protection",
        "ip" in result.primary_reason.lower(),
        f"got reason='{result.primary_reason}'",
    )


# ── Test 6: Cost optimisation routes external ────────────────────────────
def test_cost_optimization():
    """External cheaper by > min_cost_savings_pct (10%) → ROUTE_EXTERNAL"""
    engine = SubcontractingEngine("SITE-1")
    snap = base_snapshot(
        internal_capacity_pct=0.50,           # plenty of internal capacity
        internal_cost_per_unit=10.0,
        subcontractor_cost_per_unit=8.0,       # 20% cheaper
        subcontractor_quality_score=0.95,
        subcontractor_on_time_score=0.90,
    )
    result = engine.evaluate_routing(snap)

    test(
        "cost_optimization — decision is ROUTE_EXTERNAL",
        result.decision_type == SubcontractDecisionType.ROUTE_EXTERNAL,
        f"got {result.decision_type}",
    )
    test(
        "cost_optimization — cost_savings > 0",
        result.cost_savings > 0,
        f"got {result.cost_savings}",
    )
    expected_savings = 1000 * (10.0 - 8.0)
    test(
        "cost_optimization — cost_savings = $2000",
        abs(result.cost_savings - expected_savings) < 1e-6,
        f"got {result.cost_savings}, expected {expected_savings}",
    )
    test(
        "cost_optimization — reason is cost_optimization",
        "cost" in result.primary_reason.lower(),
        f"got reason='{result.primary_reason}'",
    )


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A9: Subcontracting Engine Validation")
    print(f"{'='*60}")

    test_keep_internal_capacity_available()
    test_route_external_capacity_constraint()
    test_split_partial_capacity()
    test_reject_low_quality_vendor()
    test_ip_sensitivity_blocks_external()
    test_cost_optimization()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

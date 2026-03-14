#!/usr/bin/env python3
"""A11: Buffer Calculator Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import math
from datetime import date, datetime, timedelta

# Direct import to avoid __init__.py chains that require DB config
_engine_path = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'app', 'services', 'powell', 'engines', 'buffer_calculator.py',
)
_spec = importlib.util.spec_from_file_location('buffer_calculator', _engine_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

BufferCalculator = _mod.BufferCalculator
BufferConfig = _mod.BufferConfig
BufferPolicy = _mod.BufferPolicy
BufferResult = _mod.BufferResult
DemandStats = _mod.DemandStats
PolicyType = _mod.PolicyType
Z_SCORES = _mod.Z_SCORES

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


def default_stats(**overrides) -> DemandStats:
    defaults = dict(
        avg_daily_demand=100,
        std_daily_demand=20,
        avg_daily_forecast=95,
        std_daily_forecast=15,
        lead_time_days=7,
        lead_time_std=1.5,
        review_period_days=1,
    )
    defaults.update(overrides)
    return DemandStats(**defaults)


# ── Test 1: ABS_LEVEL policy ────────────────────────────────────────────
def test_abs_level():
    """Fixed quantity = 500 → safety_stock = 500"""
    calc = BufferCalculator("SITE-1")
    policy = BufferPolicy(policy_type=PolicyType.ABS_LEVEL, fixed_quantity=500)
    stats = default_stats()
    result = calc.compute_safety_stock("PROD-1", "LOC-1", policy, stats)

    test(
        "abs_level — safety_stock = 500",
        abs(result.safety_stock - 500.0) < 1e-6,
        f"got {result.safety_stock}",
    )
    test(
        "abs_level — policy_type is ABS_LEVEL",
        result.policy_type == PolicyType.ABS_LEVEL,
        f"got {result.policy_type}",
    )


# ── Test 2: DOC_DEM policy ──────────────────────────────────────────────
def test_doc_dem():
    """days_of_coverage=14, avg_daily_demand=100 → safety_stock = 1400"""
    calc = BufferCalculator("SITE-1")
    policy = BufferPolicy(policy_type=PolicyType.DOC_DEM, days_of_coverage=14)
    stats = default_stats(avg_daily_demand=100)
    result = calc.compute_safety_stock("PROD-1", "LOC-1", policy, stats)

    expected = 100 * 14  # 1400
    test(
        "doc_dem — safety_stock = 1400",
        abs(result.safety_stock - expected) < 1e-6,
        f"got {result.safety_stock}, expected {expected}",
    )


# ── Test 3: DOC_FCST policy ─────────────────────────────────────────────
def test_doc_fcst():
    """days_of_coverage=14, avg_daily_forecast=80 → safety_stock = 1120"""
    calc = BufferCalculator("SITE-1")
    policy = BufferPolicy(policy_type=PolicyType.DOC_FCST, days_of_coverage=14)
    stats = default_stats(avg_daily_forecast=80)
    result = calc.compute_safety_stock("PROD-1", "LOC-1", policy, stats)

    expected = 80 * 14  # 1120
    test(
        "doc_fcst — safety_stock = 1120",
        abs(result.safety_stock - expected) < 1e-6,
        f"got {result.safety_stock}, expected {expected}",
    )


# ── Test 4: SL policy (95%, fixed lead time) ────────────────────────────
def test_sl_policy():
    """z=1.645, std_daily_demand=10, lead_time=7 → ~1.645*10*sqrt(7) ≈ 43.52

    NOTE: Engine uses forecast error std (std_daily_forecast) by default when
    use_forecast_error=True and std_daily_forecast > 0.  We set use_forecast_error=False
    and lead_time_std=0 to use the basic formula: z * sigma_D * sqrt(L).
    """
    config = BufferConfig(use_forecast_error=False)
    calc = BufferCalculator("SITE-1", config=config)
    policy = BufferPolicy(policy_type=PolicyType.SL, target_service_level=0.95)
    stats = default_stats(std_daily_demand=10, lead_time_std=0)
    result = calc.compute_safety_stock("PROD-1", "LOC-1", policy, stats)

    z = 1.645
    expected = z * 10 * math.sqrt(7)  # ≈ 43.52
    test(
        f"sl_95 — safety_stock ≈ {expected:.2f}",
        abs(result.safety_stock - expected) < 0.1,
        f"got {result.safety_stock:.4f}, expected {expected:.4f}",
    )
    test(
        "sl_95 — z_score in calculation_detail = 1.645",
        abs(result.calculation_detail.get("z_score", 0) - 1.645) < 1e-6,
        f"got {result.calculation_detail.get('z_score')}",
    )


# ── Test 5: Reorder point ───────────────────────────────────────────────
def test_reorder_point():
    """reorder_point = safety_stock + avg_demand * lead_time"""
    config = BufferConfig(use_forecast_error=False)
    calc = BufferCalculator("SITE-1", config=config)
    policy = BufferPolicy(policy_type=PolicyType.ABS_LEVEL, fixed_quantity=200)
    stats = default_stats(avg_daily_demand=50, lead_time_days=10)
    result = calc.compute_safety_stock("PROD-1", "LOC-1", policy, stats)

    expected_rop = 200 + 50 * 10  # 200 + 500 = 700
    test(
        "reorder_point — reorder_point = 700",
        abs(result.reorder_point - expected_rop) < 1e-6,
        f"got {result.reorder_point}, expected {expected_rop}",
    )


# ── Test 6: Min/max safety stock bounds ──────────────────────────────────
def test_min_max_bounds():
    """min_ss=100, max_ss=2000 → clamp result"""
    calc = BufferCalculator("SITE-1")

    # Tiny fixed qty should be clamped up to min_ss
    policy_low = BufferPolicy(
        policy_type=PolicyType.ABS_LEVEL,
        fixed_quantity=10,
        min_ss=100,
        max_ss=2000,
    )
    stats = default_stats()
    result_low = calc.compute_safety_stock("PROD-1", "LOC-1", policy_low, stats)

    test(
        "bounds — clamped up to min_ss=100",
        abs(result_low.safety_stock - 100) < 1e-6,
        f"got {result_low.safety_stock}",
    )

    # Huge fixed qty should be clamped down to max_ss
    policy_high = BufferPolicy(
        policy_type=PolicyType.ABS_LEVEL,
        fixed_quantity=5000,
        min_ss=100,
        max_ss=2000,
    )
    result_high = calc.compute_safety_stock("PROD-1", "LOC-1", policy_high, stats)

    test(
        "bounds — clamped down to max_ss=2000",
        abs(result_high.safety_stock - 2000) < 1e-6,
        f"got {result_high.safety_stock}",
    )


# ── Test 7: Batch compute ───────────────────────────────────────────────
def test_batch_compute():
    """Multiple items → returns list of BufferResult"""
    calc = BufferCalculator("SITE-1")
    items = [
        {
            "product_id": "P1",
            "location_id": "L1",
            "policy": BufferPolicy(policy_type=PolicyType.ABS_LEVEL, fixed_quantity=300),
            "stats": default_stats(),
        },
        {
            "product_id": "P2",
            "location_id": "L2",
            "policy": BufferPolicy(policy_type=PolicyType.DOC_DEM, days_of_coverage=7),
            "stats": default_stats(avg_daily_demand=50),
        },
        {
            "product_id": "P3",
            "location_id": "L3",
            "policy": BufferPolicy(policy_type=PolicyType.ABS_LEVEL, fixed_quantity=100),
            "stats": default_stats(),
        },
    ]
    results = calc.compute_batch(items)

    test(
        "batch — returns 3 results",
        len(results) == 3,
        f"got {len(results)}",
    )
    test(
        "batch — first item safety_stock = 300",
        abs(results[0].safety_stock - 300) < 1e-6,
        f"got {results[0].safety_stock}",
    )
    test(
        "batch — second item safety_stock = 350 (50*7)",
        abs(results[1].safety_stock - 350) < 1e-6,
        f"got {results[1].safety_stock}",
    )
    test(
        "batch — product_ids preserved",
        results[0].product_id == "P1" and results[2].product_id == "P3",
        f"got [{results[0].product_id}, {results[2].product_id}]",
    )


# ── Test 8: z_from_service_level ─────────────────────────────────────────
def test_z_from_service_level():
    """Verify z_from_service_level(0.95) ≈ 1.645"""
    z = BufferCalculator.z_from_service_level(0.95)

    test(
        "z_from_service_level(0.95) ≈ 1.645",
        abs(z - 1.645) < 0.001,
        f"got {z}",
    )
    z_99 = BufferCalculator.z_from_service_level(0.99)
    test(
        "z_from_service_level(0.99) ≈ 2.326",
        abs(z_99 - 2.326) < 0.001,
        f"got {z_99}",
    )


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A11: Buffer Calculator Engine Validation")
    print(f"{'='*60}")

    test_abs_level()
    test_doc_dem()
    test_doc_fcst()
    test_sl_policy()
    test_reorder_point()
    test_min_max_bounds()
    test_batch_compute()
    test_z_from_service_level()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

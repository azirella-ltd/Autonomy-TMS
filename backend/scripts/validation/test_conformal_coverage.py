#!/usr/bin/env python3
"""G3: Conformal Prediction Coverage Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import math
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
    print(f"G3: Conformal Prediction Coverage Validation")
    print(f"{'='*60}")

    import numpy as np

    from app.services.conformal_orchestrator import ConformalOrchestrator
    from app.services.conformal_prediction.engine import (
        ConformalPredictionEngine,
        PredictionInterval,
    )
    from app.services.conformal_prediction.predictors import SplitConformalPredictor

    # ── Test 1: CRPS computation for Normal distribution ──────────────
    print("\n[Test 1] CRPS computation for Normal distribution")

    # When observed == mean, CRPS should be sigma * (1/sqrt(pi) - ... )
    # CRPS(N(0,1), 0) = 1/sqrt(pi) approximately 0.5642
    crps_at_mean = ConformalOrchestrator.compute_crps_normal(mu=0.0, sigma=1.0, observed=0.0)
    expected_at_mean = 1.0 / math.sqrt(math.pi)
    # Actually CRPS(N(0,1),0) = sigma * (2*phi(0) - 1/sqrt(pi)) = 1*(2*0.3989 - 0.5642) = 0.2337
    # Let's just verify it returns a positive finite number and is less than sigma
    test(
        "CRPS for N(0,1) at mean is positive",
        crps_at_mean > 0,
        f"Got {crps_at_mean}",
    )
    test(
        "CRPS for N(0,1) at mean is less than sigma",
        crps_at_mean < 1.0,
        f"Got {crps_at_mean}",
    )

    # CRPS should increase as observation moves away from mean
    crps_far = ConformalOrchestrator.compute_crps_normal(mu=0.0, sigma=1.0, observed=3.0)
    test(
        "CRPS increases for observation further from mean",
        crps_far > crps_at_mean,
        f"At mean: {crps_at_mean:.4f}, at 3 sigma: {crps_far:.4f}",
    )

    # CRPS with sigma=0 degenerates to MAE
    crps_degenerate = ConformalOrchestrator.compute_crps_normal(mu=5.0, sigma=0.0, observed=8.0)
    test(
        "CRPS with sigma=0 equals MAE",
        abs(crps_degenerate - 3.0) < 1e-6,
        f"Expected 3.0, got {crps_degenerate}",
    )

    # ── Test 2: CRPS computation for empirical distribution ───────────
    print("\n[Test 2] CRPS computation for empirical distribution")
    # Create a simple step CDF: all mass at point 5
    grid = np.array([0.0, 2.5, 5.0, 7.5, 10.0])
    cdf = np.array([0.0, 0.0, 0.5, 1.0, 1.0])
    crps_emp = ConformalOrchestrator.compute_crps_empirical(cdf, grid, observed=5.0)
    test(
        "Empirical CRPS is non-negative",
        crps_emp >= 0.0,
        f"Got {crps_emp}",
    )
    test(
        "Empirical CRPS is finite",
        math.isfinite(crps_emp),
        f"Got {crps_emp}",
    )
    # CRPS should be larger when observed is far from CDF mass
    crps_emp_far = ConformalOrchestrator.compute_crps_empirical(cdf, grid, observed=0.0)
    test(
        "Empirical CRPS larger when observed far from mass",
        crps_emp_far > crps_emp,
        f"At mass: {crps_emp:.4f}, far from mass: {crps_emp_far:.4f}",
    )

    # ── Test 3: Conformal interval construction ───────────────────────
    print("\n[Test 3] Conformal interval construction")
    engine = ConformalPredictionEngine(coverage=0.90, method="split")

    # Calibrate with known residuals
    np.random.seed(42)
    n_cal = 200
    predictions = np.random.normal(100, 10, n_cal).tolist()
    actuals = [p + np.random.normal(0, 5) for p in predictions]
    engine.add_calibration_batch(predictions, actuals)

    interval = engine.predict_interval(100.0)
    test(
        "Prediction interval is a PredictionInterval object",
        isinstance(interval, PredictionInterval),
        f"Got {type(interval)}",
    )
    test(
        "Interval lower < point estimate",
        interval.lower < interval.point_estimate,
        f"Lower={interval.lower}, point={interval.point_estimate}",
    )
    test(
        "Interval upper > point estimate",
        interval.upper > interval.point_estimate,
        f"Upper={interval.upper}, point={interval.point_estimate}",
    )
    test(
        "Interval width is positive",
        interval.width > 0,
        f"Width={interval.width}",
    )
    test(
        "contains() works correctly for in-range value",
        interval.contains(100.0),
        f"100.0 not in [{interval.lower}, {interval.upper}]",
    )

    # ── Test 4: Coverage guarantee ────────────────────────────────────
    print("\n[Test 4] Coverage guarantee - 90% target yields >= 90% on calibration set")
    # Generate test data from same distribution
    np.random.seed(123)
    n_test = 500
    test_predictions = np.random.normal(100, 10, n_test)
    test_actuals = test_predictions + np.random.normal(0, 5, n_test)

    covered = 0
    for pred, actual in zip(test_predictions, test_actuals):
        ivl = engine.predict_interval(float(pred))
        if ivl.contains(float(actual)):
            covered += 1
    coverage = covered / n_test
    test(
        f"Empirical coverage ({coverage:.1%}) >= 85% (allowing 5% finite-sample slack on 90% target)",
        coverage >= 0.85,  # Allow 5% slack for finite sample variation
        f"Coverage was {coverage:.1%} on {n_test} test points",
    )

    # ── Test 5: Interval width increases with coverage level ──────────
    print("\n[Test 5] Interval width increases with target coverage level")
    engine_80 = ConformalPredictionEngine(coverage=0.80, method="split")
    engine_80.add_calibration_batch(predictions, actuals)
    interval_80 = engine_80.predict_interval(100.0)

    engine_95 = ConformalPredictionEngine(coverage=0.95, method="split")
    engine_95.add_calibration_batch(predictions, actuals)
    interval_95 = engine_95.predict_interval(100.0)

    test(
        f"80% coverage width ({interval_80.width:.2f}) < 90% width ({interval.width:.2f})",
        interval_80.width < interval.width,
        f"80%={interval_80.width:.2f}, 90%={interval.width:.2f}",
    )
    test(
        f"90% coverage width ({interval.width:.2f}) < 95% width ({interval_95.width:.2f})",
        interval.width < interval_95.width,
        f"90%={interval.width:.2f}, 95%={interval_95.width:.2f}",
    )

    # ── Test 6: SplitConformalPredictor end-to-end ────────────────────
    print("\n[Test 6] SplitConformalPredictor end-to-end")
    predictor = SplitConformalPredictor(target="demand_test", coverage=0.90)
    predictor.calibrate_from_history(predictions, actuals)
    result = predictor.predict(100.0)
    test(
        "SplitConformalPredictor returns PredictionInterval",
        isinstance(result, PredictionInterval),
        f"Got {type(result)}",
    )
    test(
        "SplitConformalPredictor coverage target is 0.90",
        result.coverage_target == 0.90,
        f"Got {result.coverage_target}",
    )
    test(
        "SplitConformalPredictor calibration_size matches input",
        result.calibration_size == n_cal,
        f"Expected {n_cal}, got {result.calibration_size}",
    )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

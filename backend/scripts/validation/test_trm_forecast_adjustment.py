#!/usr/bin/env python3
"""C10: Forecast Adjustment TRM Validation

Tests ForecastAdjustmentTRM:
- Engine baseline signal evaluation (direction/magnitude/confidence)
- TRM heuristic overrides (dampened by poor source accuracy, volatility)
- Hive signal emission for significant adjustments
- Output structure validation (adjusted values, auto_applicable flag)
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
    print(f"C10: Forecast Adjustment TRM Validation")
    print(f"{'='*60}")

    from app.services.powell.forecast_adjustment_trm import (
        ForecastAdjustmentTRM, ForecastAdjustmentTRMConfig,
        ForecastAdjustmentState, ForecastAdjustmentRecommendation,
    )
    from app.services.powell.engines.forecast_adjustment_engine import (
        ForecastAdjustmentEngine, ForecastAdjustmentConfig,
        ForecastSignal, AdjustmentDirection,
    )
    from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType

    # ----------------------------------------------------------------
    # Test 1: Engine processes a high-confidence upward signal
    # ----------------------------------------------------------------
    print("\n--- Test 1: Engine processes high-confidence upward signal ---")
    engine = ForecastAdjustmentEngine("SITE_A")
    signal_up = ForecastSignal(
        signal_id="SIG-001",
        product_id="PROD-A",
        site_id="SITE_A",
        source="market_intelligence",
        signal_type="demand_increase",
        signal_text="Major customer expanding operations, expect 20% volume increase",
        signal_confidence=0.85,
        direction="up",
        magnitude_hint=0.20,
        time_horizon_periods=4,
        current_forecast_value=10000.0,
        current_forecast_confidence=0.7,
    )
    result = engine.evaluate_signal(signal_up)
    test(
        "Engine recommends adjustment for high-confidence signal",
        result.should_adjust is True,
        f"should_adjust={result.should_adjust}",
    )
    test(
        "Direction is UP",
        result.direction == AdjustmentDirection.UP,
        f"got {result.direction}",
    )
    test(
        "Adjustment pct is positive and capped",
        0.0 < result.adjustment_pct <= 0.50,
        f"got {result.adjustment_pct}",
    )
    test(
        "Adjusted forecast > original",
        result.adjusted_forecast_value > 10000.0,
        f"got {result.adjusted_forecast_value}",
    )

    # ----------------------------------------------------------------
    # Test 2: Engine rejects weak signal
    # ----------------------------------------------------------------
    print("\n--- Test 2: Engine rejects weak signal ---")
    signal_weak = ForecastSignal(
        signal_id="SIG-002",
        product_id="PROD-B",
        site_id="SITE_A",
        source="social_media",
        signal_type="demand_increase",
        signal_text="Viral post about product",
        signal_confidence=0.20,
        direction="up",
        current_forecast_value=5000.0,
    )
    result_weak = engine.evaluate_signal(signal_weak)
    test(
        "Engine rejects weak signal (low combined confidence)",
        result_weak.should_adjust is False,
        f"should_adjust={result_weak.should_adjust}",
    )

    # ----------------------------------------------------------------
    # Test 3: TRM heuristic — direction/magnitude override (upward)
    # ----------------------------------------------------------------
    print("\n--- Test 3: TRM heuristic evaluates upward signal ---")
    trm = ForecastAdjustmentTRM(site_key="SITE_A")
    state_up = ForecastAdjustmentState(
        signal_id="SIG-003",
        product_id="PROD-C",
        site_id="SITE_A",
        source="customer_feedback",
        signal_type="demand_increase",
        signal_text="Customer requests 15% more volume next quarter",
        signal_confidence=0.80,
        direction="up",
        magnitude_hint=0.15,
        time_horizon_periods=4,
        current_forecast_value=8000.0,
        current_forecast_confidence=0.75,
        historical_forecast_accuracy=0.85,
        source_historical_accuracy=0.70,
        product_volatility=0.20,
        product_trend=0.05,
        seasonality_factor=1.0,
    )
    rec = trm.evaluate_signal(state_up)
    test(
        "TRM returns ForecastAdjustmentRecommendation",
        isinstance(rec, ForecastAdjustmentRecommendation),
        f"got {type(rec).__name__}",
    )
    test(
        "Should adjust for strong customer signal",
        rec.should_adjust is True,
        f"should_adjust={rec.should_adjust}",
    )
    test(
        "Direction is up",
        rec.direction == "up",
        f"got {rec.direction}",
    )
    test(
        "Adjusted forecast is higher than original",
        rec.adjusted_forecast_value > 8000.0,
        f"got {rec.adjusted_forecast_value}",
    )

    # ----------------------------------------------------------------
    # Test 4: TRM heuristic — dampened by poor source accuracy
    # ----------------------------------------------------------------
    print("\n--- Test 4: TRM heuristic dampens low-accuracy source ---")
    state_poor_source = ForecastAdjustmentState(
        signal_id="SIG-004",
        product_id="PROD-D",
        site_id="SITE_A",
        source="sales_input",
        signal_type="demand_increase",
        signal_text="Sales rep says demand will double",
        signal_confidence=0.70,
        direction="up",
        magnitude_hint=None,
        time_horizon_periods=4,
        current_forecast_value=5000.0,
        current_forecast_confidence=0.80,
        historical_forecast_accuracy=0.90,
        source_historical_accuracy=0.30,
        product_volatility=0.15,
        product_trend=0.0,
    )
    rec_poor = trm.evaluate_signal(state_poor_source)
    test(
        "Poor source accuracy dampens adjustment magnitude",
        rec_poor.adjustment_pct < 0.15,
        f"got {rec_poor.adjustment_pct:.3f} (expected dampened < 0.15)",
    )

    # ----------------------------------------------------------------
    # Test 5: TRM heuristic — high volatility product ignores small signal
    # ----------------------------------------------------------------
    print("\n--- Test 5: TRM heuristic blocks small signal for volatile product ---")
    state_volatile = ForecastAdjustmentState(
        signal_id="SIG-005",
        product_id="PROD-E",
        site_id="SITE_A",
        source="email",
        signal_type="demand_increase",
        signal_text="Slight uptick expected",
        signal_confidence=0.50,
        direction="up",
        time_horizon_periods=2,
        current_forecast_value=3000.0,
        current_forecast_confidence=0.60,
        source_historical_accuracy=0.50,
        product_volatility=0.60,
        product_trend=0.0,
    )
    rec_vol = trm.evaluate_signal(state_volatile)
    test(
        "High volatility product ignores small signal",
        rec_vol.should_adjust is False or rec_vol.adjustment_pct < 0.10,
        f"should_adjust={rec_vol.should_adjust}, adj_pct={rec_vol.adjustment_pct:.3f}",
    )

    # ----------------------------------------------------------------
    # Test 6: TRM heuristic — counter-trend signal dampened
    # ----------------------------------------------------------------
    print("\n--- Test 6: TRM heuristic dampens counter-trend signal ---")
    state_counter = ForecastAdjustmentState(
        signal_id="SIG-006",
        product_id="PROD-F",
        site_id="SITE_A",
        source="market_intelligence",
        signal_type="demand_increase",
        signal_text="One-time event may increase demand",
        signal_confidence=0.70,
        direction="up",
        magnitude_hint=0.10,
        time_horizon_periods=4,
        current_forecast_value=6000.0,
        current_forecast_confidence=0.75,
        source_historical_accuracy=0.80,
        product_volatility=0.20,
        product_trend=-0.15,
    )
    rec_counter = trm.evaluate_signal(state_counter)

    state_aligned = ForecastAdjustmentState(
        signal_id="SIG-006b",
        product_id="PROD-F",
        site_id="SITE_A",
        source="market_intelligence",
        signal_type="demand_increase",
        signal_text="One-time event may increase demand",
        signal_confidence=0.70,
        direction="up",
        magnitude_hint=0.10,
        time_horizon_periods=4,
        current_forecast_value=6000.0,
        current_forecast_confidence=0.75,
        source_historical_accuracy=0.80,
        product_volatility=0.20,
        product_trend=0.15,
    )
    rec_aligned = trm.evaluate_signal(state_aligned)
    test(
        "Counter-trend adjustment is smaller than aligned-trend",
        rec_counter.adjustment_pct <= rec_aligned.adjustment_pct,
        f"counter={rec_counter.adjustment_pct:.3f}, aligned={rec_aligned.adjustment_pct:.3f}",
    )

    # ----------------------------------------------------------------
    # Test 7: Hive signal emission for significant forecast adjustment
    # ----------------------------------------------------------------
    print("\n--- Test 7: Hive signal emission on significant adjustment ---")
    bus = HiveSignalBus()
    trm_sig = ForecastAdjustmentTRM(site_key="SITE_A")
    trm_sig.signal_bus = bus

    state_big = ForecastAdjustmentState(
        signal_id="SIG-007",
        product_id="PROD-G",
        site_id="SITE_A",
        source="market_intelligence",
        signal_type="demand_increase",
        signal_text="Major market shift confirmed by multiple sources",
        signal_confidence=0.90,
        direction="up",
        magnitude_hint=0.25,
        time_horizon_periods=6,
        current_forecast_value=20000.0,
        current_forecast_confidence=0.80,
        source_historical_accuracy=0.85,
        product_volatility=0.15,
        product_trend=0.10,
    )
    rec_big = trm_sig.evaluate_signal(state_big)
    test(
        "Significant adjustment is applied",
        rec_big.should_adjust is True and rec_big.adjustment_pct > 0.01,
        f"should_adjust={rec_big.should_adjust}, adj_pct={rec_big.adjustment_pct:.3f}",
    )
    signals = bus.read(consumer_trm="test", types={HiveSignalType.FORECAST_ADJUSTED})
    test(
        "FORECAST_ADJUSTED signal emitted",
        len(signals) >= 1,
        f"found {len(signals)} signals",
    )
    if signals:
        test(
            "Signal source is forecast_adj",
            signals[0].source_trm == "forecast_adj",
            f"got {signals[0].source_trm}",
        )

    # ----------------------------------------------------------------
    # Test 8: Output structure completeness
    # ----------------------------------------------------------------
    print("\n--- Test 8: Output structure completeness ---")
    test("signal_id populated", rec.signal_id == "SIG-003", f"got {rec.signal_id}")
    test("product_id populated", rec.product_id == "PROD-C", f"got {rec.product_id}")
    test("site_id populated", rec.site_id == "SITE_A", f"got {rec.site_id}")
    test("confidence in [0,1]", 0.0 <= rec.confidence <= 1.0, f"got {rec.confidence}")
    test("requires_human_review is bool", isinstance(rec.requires_human_review, bool), f"got {type(rec.requires_human_review).__name__}")
    test("auto_applicable is bool", isinstance(rec.auto_applicable, bool), f"got {type(rec.auto_applicable).__name__}")
    test("adjustment_magnitude is non-negative", rec.adjustment_magnitude >= 0, f"got {rec.adjustment_magnitude}")
    test("reason is populated", len(rec.reason) > 0, "empty reason")

    # ----------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

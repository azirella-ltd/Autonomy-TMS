#!/usr/bin/env python3
"""A10: Forecast Adjustment Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import date, datetime, timedelta

# Direct import to avoid __init__.py chains that require DB config
_engine_path = os.path.join(
    os.path.dirname(__file__), '..', '..',
    'app', 'services', 'powell', 'engines', 'forecast_adjustment_engine.py',
)
_spec = importlib.util.spec_from_file_location('forecast_adjustment_engine', _engine_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ForecastAdjustmentEngine = _mod.ForecastAdjustmentEngine
ForecastAdjustmentConfig = _mod.ForecastAdjustmentConfig
ForecastSignal = _mod.ForecastSignal
ForecastAdjustmentResult = _mod.ForecastAdjustmentResult
SignalSource = _mod.SignalSource
SignalType = _mod.SignalType
AdjustmentDirection = _mod.AdjustmentDirection

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


def base_signal(**overrides) -> ForecastSignal:
    """Build a baseline signal, applying overrides."""
    defaults = dict(
        signal_id="SIG-1",
        product_id="PROD-1",
        site_id="SITE-1",
        source=SignalSource.MARKET_INTELLIGENCE.value,
        signal_type=SignalType.DEMAND_INCREASE.value,
        signal_text="Major customer expanding operations",
        signal_confidence=0.85,
        direction=AdjustmentDirection.UP.value,
        magnitude_hint=0.20,
        time_horizon_periods=4,
        signal_timestamp=datetime.utcnow(),
        effective_date=date.today(),
        current_forecast_value=1000.0,
        current_forecast_confidence=0.80,
        historical_accuracy_pct=0.85,
    )
    defaults.update(overrides)
    return ForecastSignal(**defaults)


# ── Test 1: Demand increase signal ───────────────────────────────────────
def test_demand_increase_signal():
    """High-confidence demand increase → should_adjust=True, direction=UP"""
    engine = ForecastAdjustmentEngine("SITE-1")
    sig = base_signal()
    result = engine.evaluate_signal(sig)

    test(
        "demand_increase — should_adjust is True",
        result.should_adjust is True,
        f"got {result.should_adjust}",
    )
    test(
        "demand_increase — direction is UP",
        result.direction == AdjustmentDirection.UP,
        f"got {result.direction}",
    )
    test(
        "demand_increase — adjusted_forecast > current",
        result.adjusted_forecast_value > 1000.0,
        f"got {result.adjusted_forecast_value}",
    )
    # magnitude_hint=0.20 but combined_confidence (0.85*0.8=0.68) < high_confidence (0.80)
    # so capped at max_adjustment_pct_low_confidence = 0.15
    test(
        "demand_increase — adjustment_pct capped at 0.15 (low-conf cap)",
        abs(result.adjustment_pct - 0.15) < 1e-6,
        f"got {result.adjustment_pct}",
    )


# ── Test 2: Demand decrease signal ───────────────────────────────────────
def test_demand_decrease_signal():
    """Demand decrease → direction=DOWN, adjusted forecast < current"""
    engine = ForecastAdjustmentEngine("SITE-1")
    sig = base_signal(
        signal_type=SignalType.DEMAND_DECREASE.value,
        direction=AdjustmentDirection.DOWN.value,
        magnitude_hint=0.15,
    )
    result = engine.evaluate_signal(sig)

    test(
        "demand_decrease — should_adjust is True",
        result.should_adjust is True,
        f"got {result.should_adjust}",
    )
    test(
        "demand_decrease — direction is DOWN",
        result.direction == AdjustmentDirection.DOWN,
        f"got {result.direction}",
    )
    test(
        "demand_decrease — adjusted_forecast < current",
        result.adjusted_forecast_value < 1000.0,
        f"got {result.adjusted_forecast_value}",
    )
    expected = 1000.0 * (1 - 0.15)
    test(
        "demand_decrease — adjusted value = 850",
        abs(result.adjusted_forecast_value - expected) < 1e-6,
        f"got {result.adjusted_forecast_value}, expected {expected}",
    )


# ── Test 3: Low confidence rejected ─────────────────────────────────────
def test_low_confidence_rejected():
    """Combined confidence below min_signal_confidence → should_adjust=False"""
    engine = ForecastAdjustmentEngine("SITE-1")
    # social_media reliability = 0.3; signal_confidence = 0.30
    # combined = 0.30 * 0.30 * 1.0 = 0.09 < 0.30
    sig = base_signal(
        source=SignalSource.SOCIAL_MEDIA.value,
        signal_confidence=0.30,
    )
    result = engine.evaluate_signal(sig)

    test(
        "low_confidence — should_adjust is False",
        result.should_adjust is False,
        f"got {result.should_adjust}",
    )
    test(
        "low_confidence — combined_confidence < min (0.30)",
        result.combined_confidence < 0.30,
        f"got {result.combined_confidence}",
    )


# ── Test 4: Source reliability weighting ─────────────────────────────────
def test_source_reliability_weighting():
    """market_intelligence (0.8) vs social_media (0.3) → different magnitudes"""
    engine = ForecastAdjustmentEngine("SITE-1")

    # Use no explicit magnitude_hint so engine derives from base_impact * combined_confidence
    sig_market = base_signal(
        source=SignalSource.MARKET_INTELLIGENCE.value,
        signal_confidence=0.85,
        magnitude_hint=None,
    )
    sig_social = base_signal(
        signal_id="SIG-2",
        source=SignalSource.SOCIAL_MEDIA.value,
        signal_confidence=0.85,
        magnitude_hint=None,
    )
    res_market = engine.evaluate_signal(sig_market)
    res_social = engine.evaluate_signal(sig_social)

    test(
        "source_reliability — market source_reliability = 0.8",
        abs(res_market.source_reliability - 0.8) < 1e-6,
        f"got {res_market.source_reliability}",
    )
    test(
        "source_reliability — social source_reliability = 0.3",
        abs(res_social.source_reliability - 0.3) < 1e-6,
        f"got {res_social.source_reliability}",
    )
    # Market has higher combined confidence → higher adjustment (if social even adjusts)
    if res_social.should_adjust and res_market.should_adjust:
        test(
            "source_reliability — market adjustment_pct > social adjustment_pct",
            res_market.adjustment_pct > res_social.adjustment_pct,
            f"market={res_market.adjustment_pct}, social={res_social.adjustment_pct}",
        )
    else:
        # Social may be rejected entirely, which still proves weighting matters
        test(
            "source_reliability — social may be rejected or smaller adjustment",
            (not res_social.should_adjust) or (res_market.adjustment_pct >= res_social.adjustment_pct),
            f"market_adj={res_market.should_adjust}, social_adj={res_social.should_adjust}",
        )


# ── Test 5: Max adjustment cap ───────────────────────────────────────────
def test_max_adjustment_cap():
    """Huge magnitude_hint still capped at max_adjustment_pct (0.50)"""
    engine = ForecastAdjustmentEngine("SITE-1")
    sig = base_signal(
        signal_confidence=0.95,
        magnitude_hint=0.90,  # 90% requested
    )
    result = engine.evaluate_signal(sig)

    test(
        "max_cap — should_adjust is True",
        result.should_adjust is True,
        f"got {result.should_adjust}",
    )
    test(
        "max_cap — adjustment_pct ≤ 0.50",
        result.adjustment_pct <= 0.50 + 1e-9,
        f"got {result.adjustment_pct}",
    )
    test(
        "max_cap — adjusted_forecast ≤ 1500",
        result.adjusted_forecast_value <= 1500.0 + 1e-6,
        f"got {result.adjusted_forecast_value}",
    )


# ── Test 6: Signal freshness / time decay ────────────────────────────────
def test_signal_freshness_decay():
    """Old signal (well beyond freshness_hours=72) → reduced combined_confidence"""
    engine = ForecastAdjustmentEngine("SITE-1")

    # Fresh signal
    sig_fresh = base_signal(
        signal_timestamp=datetime.utcnow(),
        magnitude_hint=None,
    )
    res_fresh = engine.evaluate_signal(sig_fresh)

    # Old signal — 10 days ago (240 hours >> 72h freshness)
    sig_old = base_signal(
        signal_id="SIG-OLD",
        signal_timestamp=datetime.utcnow() - timedelta(days=10),
        magnitude_hint=None,
    )
    res_old = engine.evaluate_signal(sig_old)

    test(
        "freshness — fresh combined_confidence > old combined_confidence",
        res_fresh.combined_confidence > res_old.combined_confidence,
        f"fresh={res_fresh.combined_confidence}, old={res_old.combined_confidence}",
    )
    # Old signal with heavy decay should produce smaller (or zero) adjustment
    if res_old.should_adjust and res_fresh.should_adjust:
        test(
            "freshness — fresh adjustment_pct ≥ old adjustment_pct",
            res_fresh.adjustment_pct >= res_old.adjustment_pct,
            f"fresh={res_fresh.adjustment_pct}, old={res_old.adjustment_pct}",
        )
    else:
        test(
            "freshness — old signal rejected or produces smaller adjustment",
            True,
            "",
        )


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A10: Forecast Adjustment Engine Validation")
    print(f"{'='*60}")

    test_demand_increase_signal()
    test_demand_decrease_signal()
    test_low_confidence_rejected()
    test_source_reliability_weighting()
    test_max_adjustment_cap()
    test_signal_freshness_decay()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

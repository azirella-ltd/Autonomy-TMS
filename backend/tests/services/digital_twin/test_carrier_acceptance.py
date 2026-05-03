"""CarrierAcceptance physics model + simulator integration (PR-3.A).

Covers:
  - parameter validation (TenderContext + CarrierAcceptanceParams)
  - bootstrap-prior baseline for contracted vs spot carriers
  - premium-rate sensitivity (paying over benchmark raises p_accept)
  - market-tightness sensitivity (tight market lowers p_accept)
  - TwinMode discipline (PLAN_PRODUCTION → deterministic threshold)
  - determinism (same seed → identical sequence of accept/reject)
  - simulator integration: opt-in via constructor; default path
    preserves legacy behaviour
"""
from __future__ import annotations

import pytest

from app.services.digital_twin.physics import (
    CarrierAcceptanceModel,
    CarrierAcceptanceParams,
    CarrierKind,
    PhysicsModel,
    TenderContext,
    TenderOutcome,
)


# ── TenderContext validation ─────────────────────────────────────────


def test_tender_context_rejects_zero_benchmark():
    with pytest.raises(ValueError, match="benchmark_rate"):
        TenderContext(
            carrier_id="acme", carrier_kind=CarrierKind.CONTRACTED,
            rate_offered=100.0, benchmark_rate=0.0, market_tightness=0.5,
        )


def test_tender_context_rejects_negative_rate_offered():
    with pytest.raises(ValueError, match="rate_offered"):
        TenderContext(
            carrier_id="acme", carrier_kind=CarrierKind.CONTRACTED,
            rate_offered=-1.0, benchmark_rate=100.0, market_tightness=0.5,
        )


def test_tender_context_rejects_out_of_range_tightness():
    with pytest.raises(ValueError, match="market_tightness"):
        TenderContext(
            carrier_id="acme", carrier_kind=CarrierKind.CONTRACTED,
            rate_offered=100.0, benchmark_rate=100.0, market_tightness=1.5,
        )


def test_tender_context_rejects_out_of_range_history():
    with pytest.raises(ValueError, match="carrier_recent_acceptance_rate"):
        TenderContext(
            carrier_id="acme", carrier_kind=CarrierKind.CONTRACTED,
            rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.5,
            carrier_recent_acceptance_rate=1.5,
        )


# ── CarrierAcceptanceParams validation ───────────────────────────────


def test_params_rejects_out_of_range_base_rates():
    with pytest.raises(ValueError, match="contract_base_rate"):
        CarrierAcceptanceParams(contract_base_rate=1.5)


def test_params_rejects_negative_coefficients():
    with pytest.raises(ValueError, match="premium_coefficient"):
        CarrierAcceptanceParams(premium_coefficient=-0.1)


# ── Bootstrap prior — contracted vs spot ─────────────────────────────


def test_protocol_compliance():
    """CarrierAcceptanceModel duck-types to PhysicsModel."""
    model = CarrierAcceptanceModel()
    assert isinstance(model, PhysicsModel)


def test_step_before_reset_raises():
    model = CarrierAcceptanceModel()
    ctx = TenderContext(
        carrier_id="x", carrier_kind=CarrierKind.CONTRACTED,
        rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.0,
    )
    with pytest.raises(RuntimeError, match="reset"):
        model.step(ctx)


def _eval_acceptance_rate(
    model: CarrierAcceptanceModel,
    *, carrier_kind: CarrierKind, n: int = 1000,
    rate_offered: float = 100.0, benchmark_rate: float = 100.0,
    market_tightness: float = 0.0,
) -> float:
    """Empirical acceptance rate over n trials."""
    accepted = 0
    for i in range(n):
        ctx = TenderContext(
            carrier_id="x", carrier_kind=carrier_kind,
            rate_offered=rate_offered, benchmark_rate=benchmark_rate,
            market_tightness=market_tightness,
        )
        outcome = model.step(ctx)
        if outcome.accepted:
            accepted += 1
    return accepted / n


def test_bootstrap_contracted_baseline():
    """Contracted carrier at zero premium, loose market → ~0.85 accept rate."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=42)
    rate = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.CONTRACTED, n=2000,
    )
    # Bootstrap target 0.85 ± 0.04 sampling tolerance at n=2000.
    assert 0.81 < rate < 0.89, (
        f"contracted baseline expected ~0.85, got {rate:.3f}"
    )


def test_bootstrap_spot_baseline():
    """Spot carrier at zero premium, loose market → ~0.55 accept rate."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=42)
    rate = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.SPOT, n=2000,
    )
    assert 0.51 < rate < 0.59, (
        f"spot baseline expected ~0.55, got {rate:.3f}"
    )


def test_premium_raises_acceptance():
    """Paying 25% over benchmark raises spot acceptance well above 0.55."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=42)
    base = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.SPOT,
        rate_offered=100.0, benchmark_rate=100.0, n=1500,
    )
    model.reset(scenario_seed=42)
    high = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.SPOT,
        rate_offered=125.0, benchmark_rate=100.0, n=1500,
    )
    assert high > base + 0.05, (
        f"25%-over-benchmark expected > base+0.05; "
        f"base={base:.3f} high={high:.3f}"
    )


def test_below_benchmark_lowers_acceptance():
    """Paying 25% under benchmark lowers contracted acceptance."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=42)
    base = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.CONTRACTED,
        rate_offered=100.0, benchmark_rate=100.0, n=1500,
    )
    model.reset(scenario_seed=42)
    low = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.CONTRACTED,
        rate_offered=75.0, benchmark_rate=100.0, n=1500,
    )
    assert low < base - 0.05, (
        f"25%-under-benchmark expected < base-0.05; "
        f"base={base:.3f} low={low:.3f}"
    )


def test_tight_market_lowers_acceptance():
    """Tight market (tightness=1.0) drops acceptance vs loose market (0.0)."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=42)
    loose = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.CONTRACTED, market_tightness=0.0, n=1500,
    )
    model.reset(scenario_seed=42)
    tight = _eval_acceptance_rate(
        model, carrier_kind=CarrierKind.CONTRACTED, market_tightness=1.0, n=1500,
    )
    assert tight < loose - 0.10, (
        f"tight market expected < loose-0.10; "
        f"loose={loose:.3f} tight={tight:.3f}"
    )


# ── Determinism ──────────────────────────────────────────────────────


def test_determinism_same_seed_same_outcomes():
    """Same seed → identical sequence of accept/reject + p_accept."""
    def _run() -> list[TenderOutcome]:
        m = CarrierAcceptanceModel()
        m.reset(scenario_seed=12345)
        outcomes = []
        for _ in range(50):
            ctx = TenderContext(
                carrier_id="x", carrier_kind=CarrierKind.SPOT,
                rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.5,
            )
            outcomes.append(m.step(ctx))
        return outcomes

    a = _run()
    b = _run()
    for o_a, o_b in zip(a, b):
        assert o_a.accepted == o_b.accepted
        assert o_a.p_accept == pytest.approx(o_b.p_accept)
        assert o_a.reason_code == o_b.reason_code


# ── TwinMode discipline ──────────────────────────────────────────────


class _FakeMode:
    """Minimal stand-in for TwinMode to avoid Core import in unit tests."""

    def __init__(self, value: str) -> None:
        self.value = value


def test_plan_production_mode_is_deterministic():
    """PLAN_PRODUCTION mode: accept = (p_accept >= 0.5), no RNG draws."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=999, twin_mode=_FakeMode("plan_production"))
    ctx = TenderContext(
        carrier_id="x", carrier_kind=CarrierKind.CONTRACTED,
        rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.0,
    )
    # Contracted base rate 0.85 >= 0.5 → deterministic accept.
    out1 = model.step(ctx)
    out2 = model.step(ctx)
    assert out1.accepted is True
    assert out2.accepted is True
    assert out1.reason_code == "deterministic_pass"

    ctx_low = TenderContext(
        carrier_id="x", carrier_kind=CarrierKind.SPOT,
        rate_offered=50.0, benchmark_rate=100.0, market_tightness=1.0,
    )
    # Spot 0.55 × premium-down × tightness-down → < 0.5 → deterministic reject.
    out3 = model.step(ctx_low)
    assert out3.accepted is False
    assert out3.reason_code == "deterministic_fail"


# ── Reason codes diagnostic ──────────────────────────────────────────


def test_reason_code_low_premium_dominates_when_under_benchmark():
    """When the carrier is offered well below benchmark and rejects,
    the reason_code should surface low_premium_reject."""
    model = CarrierAcceptanceModel()
    model.reset(scenario_seed=1)
    found_low_premium = False
    for _ in range(200):
        ctx = TenderContext(
            carrier_id="x", carrier_kind=CarrierKind.SPOT,
            rate_offered=50.0, benchmark_rate=100.0, market_tightness=0.0,
        )
        out = model.step(ctx)
        if not out.accepted and out.reason_code == "low_premium_reject":
            found_low_premium = True
            break
    assert found_low_premium, (
        "expected at least one low_premium_reject reason in 200 trials "
        "of below-benchmark spot tendering"
    )


# ── Carrier-history blend (opt-in) ───────────────────────────────────


def test_history_blend_off_by_default():
    """Phase-1 default: carrier_recent_acceptance_rate is ignored."""
    params = CarrierAcceptanceParams()
    assert params.use_carrier_history is False

    model = CarrierAcceptanceModel(params)
    model.reset(scenario_seed=42)
    ctx_with_history = TenderContext(
        carrier_id="x", carrier_kind=CarrierKind.SPOT,
        rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.0,
        carrier_recent_acceptance_rate=0.99,  # very high history
    )
    # Should evaluate at the 0.55 spot baseline, not blend toward 0.99.
    rates = []
    for _ in range(800):
        rates.append(1 if model.step(ctx_with_history).accepted else 0)
    actual = sum(rates) / len(rates)
    assert 0.50 < actual < 0.62, (
        f"history-off should track 0.55 baseline; got {actual:.3f}"
    )


def test_history_blend_on_pulls_toward_history():
    """When use_carrier_history=True, p_accept = 0.5 * bootstrap +
    0.5 * carrier_recent_acceptance_rate."""
    params = CarrierAcceptanceParams(use_carrier_history=True)
    model = CarrierAcceptanceModel(params)
    model.reset(scenario_seed=42)
    ctx = TenderContext(
        carrier_id="x", carrier_kind=CarrierKind.SPOT,
        rate_offered=100.0, benchmark_rate=100.0, market_tightness=0.0,
        carrier_recent_acceptance_rate=0.95,
    )
    # Expected: 0.5 * 0.55 + 0.5 * 0.95 = 0.75. Empirical ≈ 0.75 ± 0.04.
    rates = []
    for _ in range(800):
        rates.append(1 if model.step(ctx).accepted else 0)
    actual = sum(rates) / len(rates)
    assert 0.70 < actual < 0.80, (
        f"history-on should pull toward 0.75; got {actual:.3f}"
    )

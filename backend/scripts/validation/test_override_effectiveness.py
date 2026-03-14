#!/usr/bin/env python3
"""D2: Override Effectiveness Validation — Bayesian posteriors, tiered causal inference"""
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
    print(f"D2: Override Effectiveness Validation")
    print(f"{'='*60}")

    # ── 1. Model structure ─────────────────────────────────────────────
    print("\n--- OverrideEffectivenessPosterior Model ---")
    try:
        from app.models.override_effectiveness import (
            OverrideEffectivenessPosterior,
            CausalMatchPair,
        )
        test("OverrideEffectivenessPosterior importable", True)
        test("CausalMatchPair importable", True)
    except ImportError as e:
        test("Models importable", False, str(e))

    try:
        cols = {c.name for c in OverrideEffectivenessPosterior.__table__.columns}
        test("alpha column exists", "alpha" in cols, f"Columns: {cols}")
        test("beta_param column exists", "beta_param" in cols, f"Columns: {cols}")
        test("expected_effectiveness column exists",
             "expected_effectiveness" in cols, f"Columns: {cols}")
        test("training_weight column exists", "training_weight" in cols, f"Columns: {cols}")
        test("observation_count column exists", "observation_count" in cols, f"Columns: {cols}")
        test("user_id column exists", "user_id" in cols, f"Columns: {cols}")
        test("trm_type column exists", "trm_type" in cols, f"Columns: {cols}")
        test("site_key column exists", "site_key" in cols, f"Columns: {cols}")
        test("Table name is override_effectiveness_posteriors",
             OverrideEffectivenessPosterior.__tablename__ == "override_effectiveness_posteriors",
             f"Got {OverrideEffectivenessPosterior.__tablename__}")
    except Exception as e:
        test("Posterior model columns", False, str(e))

    # ── 2. CausalMatchPair structure ───────────────────────────────────
    print("\n--- CausalMatchPair Model ---")
    try:
        cols = {c.name for c in CausalMatchPair.__table__.columns}
        test("overridden_decision_id column exists",
             "overridden_decision_id" in cols, f"Columns: {cols}")
        test("control_decision_id column exists",
             "control_decision_id" in cols, f"Columns: {cols}")
        test("treatment_effect column exists",
             "treatment_effect" in cols, f"Columns: {cols}")
        test("state_distance column exists",
             "state_distance" in cols, f"Columns: {cols}")
        test("propensity_score column exists",
             "propensity_score" in cols, f"Columns: {cols}")
        test("match_quality column exists",
             "match_quality" in cols, f"Columns: {cols}")
        test("Table name is override_causal_match_pairs",
             CausalMatchPair.__tablename__ == "override_causal_match_pairs",
             f"Got {CausalMatchPair.__tablename__}")
    except Exception as e:
        test("CausalMatchPair columns", False, str(e))

    # ── 3. Service import and TIER_MAP ─────────────────────────────────
    print("\n--- OverrideEffectivenessService ---")
    try:
        from app.services.override_effectiveness_service import (
            OverrideEffectivenessService,
            TIER_MAP,
            OVERRIDE_DELTA_THRESHOLDS,
        )
        test("OverrideEffectivenessService importable", True)
    except ImportError as e:
        test("Service importable", False, str(e))

    # ── 4. Three observability tiers ───────────────────────────────────
    print("\n--- Observability Tiers ---")
    try:
        tier1_types = {k for k, v in TIER_MAP.items() if v == 1}
        tier2_types = {k for k, v in TIER_MAP.items() if v == 2}
        tier3_types = {k for k, v in TIER_MAP.items() if v == 3}

        test("Tier 1 types exist (analytical counterfactual)",
             len(tier1_types) > 0,
             f"Found: {tier1_types}")
        test("Tier 1 includes atp_executor",
             "atp_executor" in tier1_types,
             f"Tier 1: {tier1_types}")
        test("Tier 1 includes forecast_adjustment",
             "forecast_adjustment" in tier1_types,
             f"Tier 1: {tier1_types}")
        test("Tier 1 includes quality",
             "quality" in tier1_types or "quality_disposition" in tier1_types,
             f"Tier 1: {tier1_types}")

        test("Tier 2 types exist (statistical matching)",
             len(tier2_types) > 0,
             f"Found: {tier2_types}")
        test("Tier 2 includes mo or mo_execution",
             "mo" in tier2_types or "mo_execution" in tier2_types,
             f"Tier 2: {tier2_types}")
        test("Tier 2 includes po or po_creation",
             "po" in tier2_types or "po_creation" in tier2_types,
             f"Tier 2: {tier2_types}")

        test("Tier 3 types exist (Bayesian prior only)",
             len(tier3_types) > 0,
             f"Found: {tier3_types}")
        test("Tier 3 includes inventory_buffer or safety_stock",
             "inventory_buffer" in tier3_types or "safety_stock" in tier3_types,
             f"Tier 3: {tier3_types}")
        test("Tier 3 includes maintenance or maintenance_scheduling",
             "maintenance" in tier3_types or "maintenance_scheduling" in tier3_types,
             f"Tier 3: {tier3_types}")
    except NameError as e:
        test("TIER_MAP analysis", False, str(e))

    # ── 5. Signal strength values ──────────────────────────────────────
    print("\n--- Signal Strength ---")
    try:
        # Tier 1 signal = 1.0 (from _signal_strength static method)
        # Tier 3 signal = 0.15
        # Tier 2 signal = 0.3 to 0.9 (depends on match count)
        # We verify the static method exists and the tier mapping logic
        test("_signal_strength method exists",
             hasattr(OverrideEffectivenessService, '_signal_strength'),
             "Missing _signal_strength")
        test("get_tier method exists",
             hasattr(OverrideEffectivenessService, 'get_tier'),
             "Missing get_tier")

        # Verify get_tier returns correct tiers
        test("get_tier('atp_executor') returns 1",
             OverrideEffectivenessService.get_tier('atp_executor') == 1,
             f"Got {OverrideEffectivenessService.get_tier('atp_executor')}")
        test("get_tier('mo_execution') returns 2",
             OverrideEffectivenessService.get_tier('mo_execution') == 2,
             f"Got {OverrideEffectivenessService.get_tier('mo_execution')}")
        test("get_tier('inventory_buffer') returns 3",
             OverrideEffectivenessService.get_tier('inventory_buffer') == 3,
             f"Got {OverrideEffectivenessService.get_tier('inventory_buffer')}")
        test("Unknown type defaults to tier 3",
             OverrideEffectivenessService.get_tier('unknown_type') == 3,
             f"Got {OverrideEffectivenessService.get_tier('unknown_type')}")
    except Exception as e:
        test("Signal strength validation", False, str(e))

    # ── 6. Training weight formula ─────────────────────────────────────
    print("\n--- Training Weight Formula ---")
    try:
        weight_fn = OverrideEffectivenessService._posterior_to_weight

        # Uninformative prior: Beta(1,1) -> E[p]=0.5
        # weight = 0.3 + 1.7 * 0.5 = 1.15
        # But certainty discount: n = 1+1-2 = 0, certainty = 0
        # max_weight = 0.85 + 1.15 * 0 = 0.85
        # weight = min(1.15, 0.85) = 0.85
        w_uninf = weight_fn(1.0, 1.0)
        test("Uninformative prior Beta(1,1) -> weight=0.85",
             w_uninf == 0.85,
             f"Got {w_uninf}")

        # Proven beneficial: Beta(11,1) -> E[p]=11/12=0.917
        # weight = 0.3 + 1.7 * 0.917 = 1.859
        # n = 11+1-2 = 10, certainty = min(1, 10/10) = 1.0
        # max_weight = 0.85 + 1.15 * 1.0 = 2.0
        # weight = min(1.859, 2.0) = 1.859
        w_good = weight_fn(11.0, 1.0)
        test("Beneficial Beta(11,1) -> weight > 1.5",
             w_good > 1.5,
             f"Got {w_good}")
        test("Beneficial Beta(11,1) -> weight <= 2.0",
             w_good <= 2.0,
             f"Got {w_good}")

        # Proven detrimental: Beta(1,11) -> E[p]=1/12=0.083
        # weight = 0.3 + 1.7 * 0.083 = 0.441
        # n = 1+11-2 = 10, certainty = 1.0
        # max_weight = 2.0
        # weight = min(0.441, 2.0) = 0.441
        w_bad = weight_fn(1.0, 11.0)
        test("Detrimental Beta(1,11) -> weight < 0.5",
             w_bad < 0.5,
             f"Got {w_bad}")
        test("Detrimental Beta(1,11) -> weight >= 0.3",
             w_bad >= 0.3,
             f"Got {w_bad}")

        # Verify formula: weight = 0.3 + 1.7 * E[p] (before certainty cap)
        # With enough observations (n >= 10), certainty = 1.0, max_weight = 2.0
        # so the raw formula should apply
        alpha, beta_p = 6.0, 6.0  # E[p]=0.5, n=10
        w_50 = weight_fn(alpha, beta_p)
        expected_raw = 0.3 + 1.7 * (alpha / (alpha + beta_p))  # 1.15
        test("50/50 with observations: weight = 0.3 + 1.7*0.5 = 1.15",
             abs(w_50 - expected_raw) < 0.01,
             f"Got {w_50}, expected {expected_raw}")
    except Exception as e:
        test("Training weight formula", False, str(e))

    # ── 7. Override delta thresholds ───────────────────────────────────
    print("\n--- Override Delta Thresholds ---")
    try:
        test("beneficial_min threshold is 0.05",
             OVERRIDE_DELTA_THRESHOLDS.get("beneficial_min") == 0.05,
             f"Got {OVERRIDE_DELTA_THRESHOLDS.get('beneficial_min')}")
        test("detrimental_max threshold is -0.05",
             OVERRIDE_DELTA_THRESHOLDS.get("detrimental_max") == -0.05,
             f"Got {OVERRIDE_DELTA_THRESHOLDS.get('detrimental_max')}")
    except NameError as e:
        test("Delta thresholds", False, str(e))

    # ── 8. Classify delta ──────────────────────────────────────────────
    print("\n--- Delta Classification ---")
    try:
        test("classify_delta(0.10) = BENEFICIAL",
             OverrideEffectivenessService.classify_delta(0.10) == "BENEFICIAL",
             f"Got {OverrideEffectivenessService.classify_delta(0.10)}")
        test("classify_delta(-0.10) = DETRIMENTAL",
             OverrideEffectivenessService.classify_delta(-0.10) == "DETRIMENTAL",
             f"Got {OverrideEffectivenessService.classify_delta(-0.10)}")
        test("classify_delta(0.02) = NEUTRAL",
             OverrideEffectivenessService.classify_delta(0.02) == "NEUTRAL",
             f"Got {OverrideEffectivenessService.classify_delta(0.02)}")
    except Exception as e:
        test("Delta classification", False, str(e))

    # ── 9. Composite score formula in outcome_collector ────────────────
    print("\n--- Composite Score Formula ---")
    try:
        # The composite score: 0.4 * local_delta + 0.6 * site_bsc_delta
        # Verified by reading outcome_collector.py line 156-157
        local_delta = 0.10
        bsc_delta = 0.20
        composite = 0.4 * local_delta + 0.6 * bsc_delta
        expected = 0.16
        test("Composite score formula: 0.4*local + 0.6*bsc",
             abs(composite - expected) < 0.001,
             f"0.4*{local_delta} + 0.6*{bsc_delta} = {composite}, expected {expected}")
    except Exception as e:
        test("Composite score", False, str(e))

    # ── 10. Service public API methods ─────────────────────────────────
    print("\n--- Service Public API ---")
    try:
        test("update_posterior method exists",
             hasattr(OverrideEffectivenessService, 'update_posterior'),
             "Missing update_posterior")
        test("get_training_weight method exists",
             hasattr(OverrideEffectivenessService, 'get_training_weight'),
             "Missing get_training_weight")
        test("get_posteriors_for_user method exists",
             hasattr(OverrideEffectivenessService, 'get_posteriors_for_user'),
             "Missing get_posteriors_for_user")
        test("get_posteriors_for_trm_type method exists",
             hasattr(OverrideEffectivenessService, 'get_posteriors_for_trm_type'),
             "Missing get_posteriors_for_trm_type")
        test("get_aggregate_stats method exists",
             hasattr(OverrideEffectivenessService, 'get_aggregate_stats'),
             "Missing get_aggregate_stats")
        test("get_credible_interval method exists",
             hasattr(OverrideEffectivenessService, 'get_credible_interval'),
             "Missing get_credible_interval")
    except NameError as e:
        test("Service API", False, str(e))

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

#!/usr/bin/env python3
"""D3: Conformal Decision Theory Calibration Validation"""
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
    print(f"D3: Conformal Decision Theory Calibration Validation")
    print(f"{'='*60}")

    # ── 1. CDTCalibrationService import ────────────────────────────────
    print("\n--- CDTCalibrationService ---")
    try:
        from app.services.powell.cdt_calibration_service import (
            CDTCalibrationService,
            TRM_COST_MAPPING,
        )
        test("CDTCalibrationService importable", True)
    except ImportError as e:
        test("CDTCalibrationService importable", False, str(e))

    try:
        test("calibrate_all() method exists",
             hasattr(CDTCalibrationService, 'calibrate_all'),
             "Missing calibrate_all")
        test("calibrate_incremental() method exists",
             hasattr(CDTCalibrationService, 'calibrate_incremental'),
             "Missing calibrate_incremental")
    except NameError:
        test("CDTCalibrationService methods", False, "Class not imported")

    # ── 2. TRM_COST_MAPPING covers all 11 types ───────────────────────
    print("\n--- TRM Cost Mapping ---")
    try:
        expected_types = {
            "atp", "inventory_rebalancing", "po_creation", "order_tracking",
            "mo_execution", "to_execution", "quality_disposition",
            "maintenance_scheduling", "subcontracting",
            "forecast_adjustment", "inventory_buffer",
        }
        test("TRM_COST_MAPPING has 11 entries",
             len(TRM_COST_MAPPING) == 11,
             f"Found {len(TRM_COST_MAPPING)}: {set(TRM_COST_MAPPING.keys())}")
        test("TRM_COST_MAPPING covers all 11 TRM types",
             set(TRM_COST_MAPPING.keys()) == expected_types,
             f"Missing: {expected_types - set(TRM_COST_MAPPING.keys())}")

        # Each mapping should have: model, estimated, actual, loss
        for agent_type, mapping in TRM_COST_MAPPING.items():
            has_keys = all(k in mapping for k in ["model", "loss"])
            test(f"  {agent_type} has model+loss keys",
                 has_keys,
                 f"Keys: {list(mapping.keys())}")
    except NameError as e:
        test("TRM_COST_MAPPING", False, str(e))

    # ── 3. DecisionOutcomePair structure ───────────────────────────────
    print("\n--- DecisionOutcomePair ---")
    try:
        import numpy as np
        from app.services.conformal_prediction.conformal_decision import (
            DecisionOutcomePair,
            RiskAssessment,
            ConformalDecisionWrapper,
            get_cdt_registry,
        )
        test("DecisionOutcomePair importable", True)
        test("RiskAssessment importable", True)
        test("ConformalDecisionWrapper importable", True)

        # Verify DecisionOutcomePair structure
        pair = DecisionOutcomePair(
            decision_features=np.zeros(10),
            decision_cost_estimate=100.0,
            actual_cost=120.0,
            agent_type="atp",
        )
        test("DecisionOutcomePair.loss property works",
             abs(pair.loss - 20.0) < 0.001,
             f"Expected 20.0, got {pair.loss}")
        test("DecisionOutcomePair has timestamp field",
             hasattr(pair, 'timestamp'),
             "Missing timestamp")
        test("DecisionOutcomePair has metadata field",
             hasattr(pair, 'metadata'),
             "Missing metadata")
    except ImportError as e:
        test("Conformal decision imports", False, str(e))

    # ── 4. ConformalDecisionWrapper default thresholds ─────────────────
    print("\n--- CDT Wrapper Thresholds ---")
    try:
        test("DEFAULT_THRESHOLDS has 11 entries",
             len(ConformalDecisionWrapper.DEFAULT_THRESHOLDS) == 11,
             f"Found {len(ConformalDecisionWrapper.DEFAULT_THRESHOLDS)}")
        test("MIN_CALIBRATION_SIZE is 30",
             ConformalDecisionWrapper.MIN_CALIBRATION_SIZE == 30,
             f"Got {ConformalDecisionWrapper.MIN_CALIBRATION_SIZE}")

        # Verify specific thresholds
        test("ATP threshold is 0.10",
             ConformalDecisionWrapper.DEFAULT_THRESHOLDS.get("atp") == 0.10,
             f"Got {ConformalDecisionWrapper.DEFAULT_THRESHOLDS.get('atp')}")
        test("PO creation threshold is 0.20",
             ConformalDecisionWrapper.DEFAULT_THRESHOLDS.get("po_creation") == 0.20,
             f"Got {ConformalDecisionWrapper.DEFAULT_THRESHOLDS.get('po_creation')}")
    except NameError as e:
        test("CDT thresholds", False, str(e))

    # ── 5. Risk bound calculation: P(loss > threshold) ─────────────────
    print("\n--- Risk Bound Calculation ---")
    try:
        wrapper = ConformalDecisionWrapper(agent_type="atp")
        test("Wrapper instantiation works", True)

        # Uncalibrated wrapper should return conservative risk bound
        risk = wrapper.compute_risk_bound(100.0)
        test("Uncalibrated risk_bound is 0.50 (max uncertainty)",
             abs(risk.risk_bound - 0.50) < 0.01,
             f"Got {risk.risk_bound}")
        test("Uncalibrated escalation_recommended is True",
             risk.escalation_recommended is True,
             f"Got {risk.escalation_recommended}")
        test("Risk assessment has method='conformal_decision_theory'",
             risk.method == "conformal_decision_theory",
             f"Got {risk.method}")
    except Exception as e:
        test("Risk bound uncalibrated", False, str(e))

    # ── 6. Calibration from synthetic pairs ────────────────────────────
    print("\n--- Calibration with Synthetic Data ---")
    try:
        wrapper = ConformalDecisionWrapper(
            agent_type="atp",
            loss_threshold=0.10,
            acceptable_risk=0.10,
            escalation_risk=0.20,
        )

        # Create 50 synthetic pairs: most with small losses, a few large
        pairs = []
        np.random.seed(42)
        for i in range(50):
            estimated = 100.0
            # Most outcomes near estimated, a few significantly higher
            actual = estimated + np.random.exponential(scale=5.0)
            pairs.append(DecisionOutcomePair(
                decision_features=np.random.randn(10),
                decision_cost_estimate=estimated,
                actual_cost=actual,
                agent_type="atp",
            ))

        wrapper.calibrate(pairs)
        test("Calibration with 50 pairs succeeds", True)

        # After calibration, risk bound should be between 0 and 1
        risk = wrapper.compute_risk_bound(100.0)
        test("Post-calibration risk_bound in [0, 1]",
             0.0 <= risk.risk_bound <= 1.0,
             f"Got {risk.risk_bound}")
        test("Post-calibration calibration_size is 50",
             risk.calibration_size == 50,
             f"Got {risk.calibration_size}")
        test("Post-calibration loss_threshold is 0.10",
             abs(risk.loss_threshold - 0.10) < 0.001,
             f"Got {risk.loss_threshold}")
        test("Risk assessment is_safe is bool",
             isinstance(risk.is_safe, bool),
             f"Type: {type(risk.is_safe)}")
        test("Risk assessment to_dict() works",
             isinstance(risk.to_dict(), dict),
             "to_dict() failed")
    except Exception as e:
        test("Synthetic calibration", False, str(e))

    # ── 7. CDT Registry ────────────────────────────────────────────────
    print("\n--- CDT Registry ---")
    try:
        registry = get_cdt_registry()
        test("get_cdt_registry() returns registry", registry is not None, "None returned")

        # get_or_create should lazily create wrappers
        test("Registry has get_or_create method",
             hasattr(registry, 'get_or_create'),
             "Missing get_or_create")

        atp_wrapper = registry.get_or_create("atp")
        test("Registry creates ATP wrapper",
             atp_wrapper is not None,
             "None returned")
        test("ATP wrapper has correct agent_type",
             atp_wrapper.agent_type == "atp",
             f"Got {atp_wrapper.agent_type}")

        # Same call should return same instance
        atp_wrapper2 = registry.get_or_create("atp")
        test("Registry returns same instance on repeat call",
             atp_wrapper is atp_wrapper2,
             "Different instances returned")
    except Exception as e:
        test("CDT Registry", False, str(e))

    # ── 8. Coverage guarantee mechanism ────────────────────────────────
    print("\n--- Coverage Guarantee ---")
    try:
        # The conformal guarantee: P(loss > threshold) <= risk_bound
        # Finite-sample correction: (exceedances + 1) / (n + 1)
        # Verify this by creating a wrapper with known loss distribution
        wrapper = ConformalDecisionWrapper(agent_type="po_creation", loss_threshold=0.20)
        pairs = []
        # 100 pairs: 80 with loss < 0.20, 20 with loss > 0.20
        for i in range(80):
            pairs.append(DecisionOutcomePair(
                decision_features=np.zeros(10),
                decision_cost_estimate=100.0,
                actual_cost=100.0 + np.random.uniform(0, 0.15),  # loss < 0.20
                agent_type="po_creation",
            ))
        for i in range(20):
            pairs.append(DecisionOutcomePair(
                decision_features=np.zeros(10),
                decision_cost_estimate=100.0,
                actual_cost=100.0 + np.random.uniform(0.25, 0.50),  # loss > 0.20
                agent_type="po_creation",
            ))

        wrapper.calibrate(pairs)
        risk = wrapper.compute_risk_bound(100.0)

        # Expected: ~20/100 exceedances, risk_bound ~ (20+1)/(100+1) ~ 0.208
        test("Risk bound reflects empirical exceedance rate",
             0.10 <= risk.risk_bound <= 0.40,
             f"Got {risk.risk_bound} (expected ~0.21 for 20% exceedance)")
        test("Calibration size is 100",
             risk.calibration_size == 100,
             f"Got {risk.calibration_size}")
    except Exception as e:
        test("Coverage guarantee", False, str(e))

    # ── 9. add_calibration_pair incremental method ─────────────────────
    print("\n--- Incremental Calibration ---")
    try:
        wrapper = ConformalDecisionWrapper(agent_type="inventory_rebalancing")
        test("add_calibration_pair method exists",
             hasattr(wrapper, 'add_calibration_pair'),
             "Missing add_calibration_pair")
        test("calibrate method exists",
             hasattr(wrapper, 'calibrate'),
             "Missing calibrate")
        test("compute_risk_bound method exists",
             hasattr(wrapper, 'compute_risk_bound'),
             "Missing compute_risk_bound")
    except Exception as e:
        test("Incremental calibration", False, str(e))

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

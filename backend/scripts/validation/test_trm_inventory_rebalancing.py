#!/usr/bin/env python3
"""C2: InventoryRebalancingTRM Validation

Tests the InventoryRebalancingTRM: candidate pair identification,
heuristic evaluation via the deterministic engine, recommendation
structure, and hive signal emission (REBALANCE_INBOUND / OUTBOUND).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Minimal env vars to allow import chain (no actual DB connection used)
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
os.environ.setdefault('SECRET_KEY', 'test-key-for-validation')

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
    print(f"C2: InventoryRebalancingTRM Validation")
    print(f"{'='*60}")

    # --- imports ---
    try:
        from app.services.powell.inventory_rebalancing_trm import (
            InventoryRebalancingTRM,
            RebalancingState,
            SiteInventoryState,
            TransferLane,
            RebalanceRecommendation,
            RebalanceReason,
        )
        from app.services.powell.hive_signal import (
            HiveSignalBus, HiveSignalType,
        )
        test("Imports successful", True)
    except Exception as e:
        test("Imports successful", False, str(e))
        print(f"\n{'='*60}")
        print(f"Results: {passed} passed, {failed} failed")
        print(f"{'='*60}")
        sys.exit(1)

    # --- Section 1: Build state with imbalanced sites ---
    print("\n  -- State Construction --")
    excess_site = SiteInventoryState(
        site_id="DC-EAST",
        product_id="SKU-100",
        on_hand=500,
        in_transit=0,
        committed=20,
        backlog=0,
        demand_forecast=100,   # monthly
        demand_uncertainty=15,
        safety_stock=50,
        target_dos=14,
    )
    deficit_site = SiteInventoryState(
        site_id="DC-WEST",
        product_id="SKU-100",
        on_hand=30,
        in_transit=0,
        committed=10,
        backlog=5,
        demand_forecast=120,
        demand_uncertainty=20,
        safety_stock=60,
        target_dos=14,
    )

    test("Excess site DOS > target * 1.5",
         excess_site.days_of_supply > excess_site.target_dos * 1.5,
         f"DOS={excess_site.days_of_supply:.1f}, threshold={excess_site.target_dos * 1.5:.1f}")
    test("Deficit site DOS < target * 0.75",
         deficit_site.days_of_supply < deficit_site.target_dos * 0.75,
         f"DOS={deficit_site.days_of_supply:.1f}, threshold={deficit_site.target_dos * 0.75:.1f}")

    lane = TransferLane(
        from_site="DC-EAST",
        to_site="DC-WEST",
        transfer_time=2.0,
        cost_per_unit=0.50,
        min_qty=10,
        max_qty=200,
        is_available=True,
    )

    state = RebalancingState(
        product_id="SKU-100",
        site_states={"DC-EAST": excess_site, "DC-WEST": deficit_site},
        transfer_lanes=[lane],
        network_imbalance_score=0.7,
        total_network_inventory=530,
        total_network_demand=220,
    )
    test("State created with 2 sites", len(state.site_states) == 2, "")

    # --- Section 2: Run heuristic evaluation ---
    print("\n  -- Heuristic Evaluation --")
    bus = HiveSignalBus()
    trm = InventoryRebalancingTRM(
        trm_model=None,
        use_heuristic_fallback=True,
    )
    trm.signal_bus = bus

    recs = trm.evaluate_rebalancing(state)

    test("At least 1 recommendation returned",
         len(recs) >= 1,
         f"got {len(recs)} recommendations")

    if recs:
        rec = recs[0]
        test("Recommendation is RebalanceRecommendation",
             isinstance(rec, RebalanceRecommendation),
             f"type={type(rec).__name__}")
        test("from_site is DC-EAST (excess)",
             rec.from_site == "DC-EAST",
             f"from_site={rec.from_site}")
        test("to_site is DC-WEST (deficit)",
             rec.to_site == "DC-WEST",
             f"to_site={rec.to_site}")
        test("quantity > 0", rec.quantity > 0,
             f"quantity={rec.quantity}")
        test("product_id preserved",
             rec.product_id == "SKU-100",
             f"product_id={rec.product_id}")
        test("reason is a RebalanceReason",
             isinstance(rec.reason, RebalanceReason),
             f"reason={rec.reason}")
        test("urgency in [0, 1]",
             0 <= rec.urgency <= 1,
             f"urgency={rec.urgency}")
        test("confidence in [0, 1]",
             0 <= rec.confidence <= 1,
             f"confidence={rec.confidence}")
        test("expected_cost > 0",
             rec.expected_cost > 0,
             f"expected_cost={rec.expected_cost}")
        test("expected_arrival == lane transfer_time",
             rec.expected_arrival == 2.0,
             f"expected_arrival={rec.expected_arrival}")
        test("source_dos_after < source_dos_before",
             rec.source_dos_after < rec.source_dos_before,
             f"before={rec.source_dos_before:.1f}, after={rec.source_dos_after:.1f}")
        test("dest_dos_after > dest_dos_before",
             rec.dest_dos_after > rec.dest_dos_before,
             f"before={rec.dest_dos_before:.1f}, after={rec.dest_dos_after:.1f}")

    # --- Section 3: Hive signal emission ---
    print("\n  -- Signal Emission --")
    inbound_signals = bus.read(
        consumer_trm="atp_executor",
        types={HiveSignalType.REBALANCE_INBOUND},
    )
    test("REBALANCE_INBOUND signal emitted",
         len(inbound_signals) >= 1,
         f"count={len(inbound_signals)}")

    outbound_signals = bus.read(
        consumer_trm="atp_executor",
        types={HiveSignalType.REBALANCE_OUTBOUND},
    )
    test("REBALANCE_OUTBOUND signal emitted",
         len(outbound_signals) >= 1,
         f"count={len(outbound_signals)}")

    if inbound_signals:
        sig = inbound_signals[0]
        test("Inbound signal source_trm is rebalancing",
             sig.source_trm == "rebalancing",
             f"source_trm={sig.source_trm}")
        test("Inbound signal has payload with to_site",
             "to_site" in sig.payload,
             f"payload_keys={list(sig.payload.keys())}")

    # --- Section 4: Urgency vector ---
    print("\n  -- Urgency Vector --")
    urg_val, urg_dir, _ = bus.urgency.read("rebalancing")
    test("Urgency vector updated for rebalancing",
         urg_val > 0,
         f"urgency={urg_val}, direction={urg_dir}")

    # --- Section 5: Pair features ---
    print("\n  -- Pair Feature Vector --")
    features = state.get_pair_features("DC-EAST", "DC-WEST")
    test("Feature vector length = 30 (12+12+3+3)",
         len(features) == 30,
         f"len={len(features)}")
    test("Feature vector dtype is float32",
         str(features.dtype) == "float32",
         f"dtype={features.dtype}")

    # --- Section 6: to_dict serialization ---
    print("\n  -- Serialization --")
    if recs:
        d = recs[0].to_dict()
        test("to_dict has from_site", "from_site" in d, "")
        test("to_dict has to_site", "to_site" in d, "")
        test("to_dict has quantity", "quantity" in d, "")
        test("to_dict has confidence", "confidence" in d, "")
        test("to_dict has reason string", "reason" in d and isinstance(d["reason"], str), "")

    # --- Section 7: No recommendation when balanced ---
    print("\n  -- No Recommendation When Balanced --")
    balanced_site_a = SiteInventoryState(
        site_id="SITE-A", product_id="SKU-200",
        on_hand=200, in_transit=0, committed=0, backlog=0,
        demand_forecast=100, demand_uncertainty=10,
        safety_stock=30, target_dos=14,
    )
    balanced_site_b = SiteInventoryState(
        site_id="SITE-B", product_id="SKU-200",
        on_hand=200, in_transit=0, committed=0, backlog=0,
        demand_forecast=100, demand_uncertainty=10,
        safety_stock=30, target_dos=14,
    )
    balanced_state = RebalancingState(
        product_id="SKU-200",
        site_states={"SITE-A": balanced_site_a, "SITE-B": balanced_site_b},
        transfer_lanes=[TransferLane("SITE-A", "SITE-B", 2.0, 0.5)],
    )
    balanced_recs = trm.evaluate_rebalancing(balanced_state)
    test("No recommendation when sites are balanced",
         len(balanced_recs) == 0,
         f"got {len(balanced_recs)} recommendations")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

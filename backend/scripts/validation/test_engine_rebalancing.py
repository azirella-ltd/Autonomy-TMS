#!/usr/bin/env python3
"""A3: Rebalancing Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Direct module load to avoid heavy app init chain via powell/__init__.py
_engine_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines', 'rebalancing_engine.py')
_spec = importlib.util.spec_from_file_location("rebalancing_engine", os.path.abspath(_engine_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RebalancingEngine = _mod.RebalancingEngine
RebalancingConfig = _mod.RebalancingConfig
SiteState = _mod.SiteState
LaneConstraints = _mod.LaneConstraints
TransferRecommendation = _mod.TransferRecommendation

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


# ---------------------------------------------------------------------------
# Test 1: Surplus to deficit transfer
# ---------------------------------------------------------------------------
def test_surplus_to_deficit():
    print("\n[Test 1] Surplus to deficit transfer")
    config = RebalancingConfig(
        excess_threshold=1.5, deficit_threshold=0.75
    )
    engine = RebalancingEngine(site_key="TEST", config=config)

    site_a = SiteState(
        site_id="SITE-A", available=1000, safety_stock=200,
        days_of_supply=30, target_dos=14, stockout_risk=0.05, demand_forecast=33
    )
    site_b = SiteState(
        site_id="SITE-B", available=100, safety_stock=200,
        days_of_supply=3, target_dos=14, stockout_risk=0.8, demand_forecast=33
    )
    lane = LaneConstraints(
        from_site="SITE-A", to_site="SITE-B",
        min_qty=10, max_qty=500, transfer_time=2, cost_per_unit=1.5, is_available=True
    )

    states = {"SITE-A": site_a, "SITE-B": site_b}
    recs = engine.evaluate_network(states, [lane])

    test("At least one recommendation generated", len(recs) >= 1,
         f"got {len(recs)} recommendations")

    if recs:
        rec = recs[0]
        test("Transfer from SITE-A", rec.from_site == "SITE-A",
             f"from_site={rec.from_site}")
        test("Transfer to SITE-B", rec.to_site == "SITE-B",
             f"to_site={rec.to_site}")
        test("Transfer qty > 0", rec.quantity > 0,
             f"qty={rec.quantity}")
        test("Reason is stockout_risk (high stockout at dest)",
             rec.reason == "stockout_risk",
             f"reason={rec.reason}")
        test("Dest DOS after > dest DOS before",
             rec.dest_dos_after > rec.dest_dos_before,
             f"before={rec.dest_dos_before}, after={rec.dest_dos_after}")


# ---------------------------------------------------------------------------
# Test 2: Respects lane max_qty
# ---------------------------------------------------------------------------
def test_lane_max_qty():
    print("\n[Test 2] Respects lane max_qty")
    engine = RebalancingEngine(site_key="TEST", config=RebalancingConfig())

    site_a = SiteState(
        site_id="SITE-A", available=5000, safety_stock=200,
        days_of_supply=60, target_dos=14, stockout_risk=0.01, demand_forecast=33
    )
    site_b = SiteState(
        site_id="SITE-B", available=50, safety_stock=200,
        days_of_supply=1.5, target_dos=14, stockout_risk=0.9, demand_forecast=33
    )
    # Very small max_qty
    lane = LaneConstraints(
        from_site="SITE-A", to_site="SITE-B",
        min_qty=5, max_qty=25, transfer_time=1, cost_per_unit=2.0, is_available=True
    )

    rec = engine.evaluate_pair(site_a, site_b, lane)
    test("Recommendation generated", rec is not None, "got None")
    if rec:
        test(f"Transfer qty <= max_qty (25)", rec.quantity <= 25,
             f"qty={rec.quantity}")
        test(f"Transfer qty >= min_qty (5)", rec.quantity >= 5,
             f"qty={rec.quantity}")


# ---------------------------------------------------------------------------
# Test 3: No transfer when balanced
# ---------------------------------------------------------------------------
def test_no_transfer_when_balanced():
    print("\n[Test 3] No transfer when balanced")
    engine = RebalancingEngine(site_key="TEST", config=RebalancingConfig(
        excess_threshold=1.5, deficit_threshold=0.75
    ))

    # Both sites near target DOS (14)
    site_a = SiteState(
        site_id="SITE-A", available=500, safety_stock=400,
        days_of_supply=15, target_dos=14, stockout_risk=0.1, demand_forecast=33
    )
    site_b = SiteState(
        site_id="SITE-B", available=450, safety_stock=400,
        days_of_supply=13, target_dos=14, stockout_risk=0.15, demand_forecast=33
    )
    lane = LaneConstraints(
        from_site="SITE-A", to_site="SITE-B",
        min_qty=10, max_qty=500, transfer_time=2, cost_per_unit=1.0, is_available=True
    )

    states = {"SITE-A": site_a, "SITE-B": site_b}
    pairs = engine.identify_candidate_pairs(states, [lane])

    test("No candidate pairs when both near target DOS", len(pairs) == 0,
         f"got {len(pairs)} pairs: {pairs}")


# ---------------------------------------------------------------------------
# Test 4: Lane unavailable
# ---------------------------------------------------------------------------
def test_lane_unavailable():
    print("\n[Test 4] Lane unavailable blocks transfer")
    engine = RebalancingEngine(site_key="TEST", config=RebalancingConfig())

    site_a = SiteState(
        site_id="SITE-A", available=1000, safety_stock=200,
        days_of_supply=30, target_dos=14, stockout_risk=0.05, demand_forecast=33
    )
    site_b = SiteState(
        site_id="SITE-B", available=50, safety_stock=200,
        days_of_supply=1.5, target_dos=14, stockout_risk=0.9, demand_forecast=33
    )
    lane = LaneConstraints(
        from_site="SITE-A", to_site="SITE-B",
        min_qty=10, max_qty=500, transfer_time=2, cost_per_unit=1.5,
        is_available=False,  # Lane disabled
    )

    states = {"SITE-A": site_a, "SITE-B": site_b}
    pairs = engine.identify_candidate_pairs(states, [lane])
    test("No candidate pairs when lane unavailable", len(pairs) == 0,
         f"got {len(pairs)} pairs")

    # Also test evaluate_pair directly
    rec = engine.evaluate_pair(site_a, site_b, lane)
    test("evaluate_pair returns None for unavailable lane", rec is None,
         f"got {rec}")


# ---------------------------------------------------------------------------
# Test 5: Multiple candidate pairs
# ---------------------------------------------------------------------------
def test_multiple_candidate_pairs():
    print("\n[Test 5] Multiple candidate pairs identification")
    engine = RebalancingEngine(site_key="TEST", config=RebalancingConfig(
        excess_threshold=1.5, deficit_threshold=0.75
    ))

    # 1 surplus site, 2 deficit sites
    site_a = SiteState(
        site_id="SITE-A", available=2000, safety_stock=200,
        days_of_supply=45, target_dos=14, stockout_risk=0.02, demand_forecast=33
    )
    site_b = SiteState(
        site_id="SITE-B", available=50, safety_stock=200,
        days_of_supply=1.5, target_dos=14, stockout_risk=0.9, demand_forecast=33
    )
    site_c = SiteState(
        site_id="SITE-C", available=80, safety_stock=200,
        days_of_supply=2.5, target_dos=14, stockout_risk=0.7, demand_forecast=33
    )

    lanes = [
        LaneConstraints(from_site="SITE-A", to_site="SITE-B",
                         min_qty=10, max_qty=500, is_available=True),
        LaneConstraints(from_site="SITE-A", to_site="SITE-C",
                         min_qty=10, max_qty=500, is_available=True),
    ]

    states = {"SITE-A": site_a, "SITE-B": site_b, "SITE-C": site_c}
    pairs = engine.identify_candidate_pairs(states, lanes)

    test("Two candidate pairs found", len(pairs) == 2,
         f"got {len(pairs)} pairs: {pairs}")

    recs = engine.evaluate_network(states, lanes)
    test("Two recommendations generated", len(recs) == 2,
         f"got {len(recs)}")

    if len(recs) >= 2:
        # Higher urgency should be first (SITE-B has higher stockout risk)
        test("Higher urgency recommendation first",
             recs[0].urgency >= recs[1].urgency,
             f"urgencies: {recs[0].urgency}, {recs[1].urgency}")

    # Verify surplus identification
    surplus_sites = [s for s_id, s in states.items()
                     if s.days_of_supply > s.target_dos * engine.config.excess_threshold]
    deficit_sites = [s for s_id, s in states.items()
                     if s.days_of_supply < s.target_dos * engine.config.deficit_threshold]
    test("1 surplus site identified", len(surplus_sites) == 1,
         f"got {len(surplus_sites)}")
    test("2 deficit sites identified", len(deficit_sites) == 2,
         f"got {len(deficit_sites)}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A3: Rebalancing Engine Validation")
    print(f"{'='*60}")

    test_surplus_to_deficit()
    test_lane_max_qty()
    test_no_transfer_when_balanced()
    test_lane_unavailable()
    test_multiple_candidate_pairs()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

#!/usr/bin/env python3
"""A2: MRP Engine Validation"""
import os, sys, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import date, timedelta

# Direct module load to avoid heavy app init chain via powell/__init__.py
_engine_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'services', 'powell', 'engines', 'mrp_engine.py')
_spec = importlib.util.spec_from_file_location("mrp_engine", os.path.abspath(_engine_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
MRPEngine = _mod.MRPEngine
MRPConfig = _mod.MRPConfig
GrossRequirement = _mod.GrossRequirement
NetRequirement = _mod.NetRequirement
PlannedOrder = _mod.PlannedOrder

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
# Test 1: Simple netting
# ---------------------------------------------------------------------------
def test_simple_netting():
    print("\n[Test 1] Simple netting")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=30, lot_sizing_rule="lot_for_lot"
    ))

    req_date = date.today() + timedelta(days=10)
    gross = [GrossRequirement(
        item_id="FG-1", required_date=req_date, quantity=100,
        source="demand", priority=1
    )]
    on_hand = {"FG-1": 30}
    receipts = {"FG-1": [(req_date, 20)]}
    bom = {}
    lead_times = {"FG-1": 3}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, receipts, bom, lead_times
    )

    # Net = 100 + 0(SS) - (30 on_hand + 20 receipt) = 50
    fg_nets = [n for n in nets if n.item_id == "FG-1"]
    test("One net requirement generated", len(fg_nets) == 1,
         f"got {len(fg_nets)}")

    if fg_nets:
        net = fg_nets[0]
        test("net_qty is 50", net.net_qty == 50,
             f"net_qty={net.net_qty}")
        test("gross_qty is 100", net.gross_qty == 100,
             f"gross_qty={net.gross_qty}")

    fg_planned = [p for p in planned if p.item_id == "FG-1"]
    test("One planned order generated", len(fg_planned) == 1,
         f"got {len(fg_planned)}")
    if fg_planned:
        test("Planned order qty is 50", fg_planned[0].quantity == 50,
             f"qty={fg_planned[0].quantity}")


# ---------------------------------------------------------------------------
# Test 2: BOM explosion
# ---------------------------------------------------------------------------
def test_bom_explosion():
    print("\n[Test 2] BOM explosion")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=30, lot_sizing_rule="lot_for_lot"
    ))

    req_date = date.today() + timedelta(days=10)
    gross = [GrossRequirement(
        item_id="FG-1", required_date=req_date, quantity=10,
        source="demand", priority=1
    )]
    on_hand = {"FG-1": 0, "COMP-A": 0}
    receipts = {}
    # 1 FG-1 = 3 COMP-A
    bom = {"FG-1": [("COMP-A", 3.0)]}
    lead_times = {"FG-1": 2, "COMP-A": 5}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, receipts, bom, lead_times
    )

    fg_planned = [p for p in planned if p.item_id == "FG-1"]
    comp_planned = [p for p in planned if p.item_id == "COMP-A"]

    test("FG-1 planned order exists", len(fg_planned) >= 1,
         f"got {len(fg_planned)}")

    if fg_planned:
        test("FG-1 planned qty is 10", fg_planned[0].quantity == 10,
             f"qty={fg_planned[0].quantity}")
        test("FG-1 order type is manufacture", fg_planned[0].order_type == "manufacture",
             f"type={fg_planned[0].order_type}")

    test("COMP-A planned order exists", len(comp_planned) >= 1,
         f"got {len(comp_planned)}")
    if comp_planned:
        test("COMP-A planned qty is 30 (10 * 3.0)", comp_planned[0].quantity == 30,
             f"qty={comp_planned[0].quantity}")
        test("COMP-A order type is purchase", comp_planned[0].order_type == "purchase",
             f"type={comp_planned[0].order_type}")


# ---------------------------------------------------------------------------
# Test 3: Multi-level BOM
# ---------------------------------------------------------------------------
def test_multi_level_bom():
    print("\n[Test 3] Multi-level BOM explosion")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=60, lot_sizing_rule="lot_for_lot"
    ))

    req_date = date.today() + timedelta(days=20)
    gross = [GrossRequirement(
        item_id="GP-1", required_date=req_date, quantity=5,
        source="demand", priority=1
    )]
    on_hand = {"GP-1": 0, "PARENT-1": 0, "CHILD-1": 0}
    receipts = {}
    # GP-1 -> 2 PARENT-1 -> 3 CHILD-1
    bom = {
        "GP-1": [("PARENT-1", 2.0)],
        "PARENT-1": [("CHILD-1", 3.0)],
    }
    lead_times = {"GP-1": 2, "PARENT-1": 3, "CHILD-1": 5}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, receipts, bom, lead_times
    )

    gp_planned = [p for p in planned if p.item_id == "GP-1"]
    parent_planned = [p for p in planned if p.item_id == "PARENT-1"]
    child_planned = [p for p in planned if p.item_id == "CHILD-1"]

    test("GP-1 planned qty is 5", len(gp_planned) >= 1 and gp_planned[0].quantity == 5,
         f"planned={[p.quantity for p in gp_planned]}")

    # 5 GP-1 * 2 = 10 PARENT-1
    test("PARENT-1 planned qty is 10",
         len(parent_planned) >= 1 and parent_planned[0].quantity == 10,
         f"planned={[p.quantity for p in parent_planned]}")

    # 10 PARENT-1 * 3 = 30 CHILD-1
    test("CHILD-1 planned qty is 30 (5*2*3 amplification)",
         len(child_planned) >= 1 and child_planned[0].quantity == 30,
         f"planned={[p.quantity for p in child_planned]}")


# ---------------------------------------------------------------------------
# Test 4: Lead time offset
# ---------------------------------------------------------------------------
def test_lead_time_offset():
    print("\n[Test 4] Lead time offset")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=30, lot_sizing_rule="lot_for_lot",
        safety_lead_time_days=0
    ))

    req_date = date.today() + timedelta(days=15)
    gross = [GrossRequirement(
        item_id="FG-1", required_date=req_date, quantity=50,
        source="demand", priority=1
    )]
    on_hand = {"FG-1": 0}
    lead_time = 5
    lead_times = {"FG-1": lead_time}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, {}, {}, lead_times
    )

    fg_planned = [p for p in planned if p.item_id == "FG-1"]
    test("Planned order exists", len(fg_planned) >= 1, f"got {len(fg_planned)}")

    if fg_planned:
        expected_order_date = req_date - timedelta(days=lead_time)
        test(f"Order date is {lead_time} days before requirement",
             fg_planned[0].order_date == expected_order_date,
             f"order_date={fg_planned[0].order_date}, expected={expected_order_date}")
        test("Receipt date matches requirement date",
             fg_planned[0].receipt_date == req_date,
             f"receipt_date={fg_planned[0].receipt_date}")


# ---------------------------------------------------------------------------
# Test 5: Lot-for-lot sizing
# ---------------------------------------------------------------------------
def test_lot_for_lot():
    print("\n[Test 5] Lot-for-lot sizing")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=30, lot_sizing_rule="lot_for_lot"
    ))

    req_date = date.today() + timedelta(days=10)
    gross = [GrossRequirement(
        item_id="FG-1", required_date=req_date, quantity=73,
        source="demand", priority=1
    )]
    on_hand = {"FG-1": 0}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, {}, {}, {"FG-1": 1}
    )

    fg_planned = [p for p in planned if p.item_id == "FG-1"]
    test("Planned order qty matches net exactly (lot-for-lot)",
         len(fg_planned) >= 1 and fg_planned[0].quantity == 73,
         f"planned={[p.quantity for p in fg_planned]}")


# ---------------------------------------------------------------------------
# Test 6: No requirements when covered
# ---------------------------------------------------------------------------
def test_no_requirements_when_covered():
    print("\n[Test 6] No requirements when fully covered")
    engine = MRPEngine(site_key="TEST", config=MRPConfig(
        planning_horizon_days=30, lot_sizing_rule="lot_for_lot"
    ))

    req_date = date.today() + timedelta(days=10)
    gross = [GrossRequirement(
        item_id="FG-1", required_date=req_date, quantity=100,
        source="demand", priority=1
    )]
    # on_hand (80) + receipt (30) = 110 >= 100 gross
    on_hand = {"FG-1": 80}
    receipts = {"FG-1": [(req_date, 30)]}

    nets, planned = engine.compute_net_requirements(
        gross, on_hand, receipts, {}, {"FG-1": 1}
    )

    fg_planned = [p for p in planned if p.item_id == "FG-1"]
    test("No planned orders when inventory covers demand",
         len(fg_planned) == 0,
         f"got {len(fg_planned)} planned orders: {[p.quantity for p in fg_planned]}")

    fg_nets = [n for n in nets if n.item_id == "FG-1"]
    if fg_nets:
        test("net_qty is 0 when fully covered", fg_nets[0].net_qty == 0,
             f"net_qty={fg_nets[0].net_qty}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("A2: MRP Engine Validation")
    print(f"{'='*60}")

    test_simple_netting()
    test_bom_explosion()
    test_multi_level_bom()
    test_lead_time_offset()
    test_lot_for_lot()
    test_no_requirements_when_covered()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

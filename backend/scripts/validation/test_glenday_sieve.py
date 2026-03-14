#!/usr/bin/env python3
"""F6: GlendaySieve and SetupMatrix Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import random
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
    print(f"F6: GlendaySieve and SetupMatrix Validation")
    print(f"{'='*60}")

    from app.services.powell.engines.setup_matrix import (
        GlendaySieve,
        GlendaySieveConfig,
        SetupMatrix,
        ChangeoverEntry,
        RunnerCategory,
        SequencedMO,
        sequence_with_glenday,
    )

    # ── Prepare volume data for Glenday Sieve ─────────────────────────
    # Pareto-like: a few products dominate volume
    volume_data = {
        "PROD_A": 5000,   # 50% of total -> green
        "PROD_B": 2000,   # 20% -> yellow (cumulative 70%)
        "PROD_C": 1500,   # 15% -> yellow (cumulative 85%)
        "PROD_D": 1000,   # 10% -> yellow (cumulative 95%)
        "PROD_E": 300,    #  3% -> red (cumulative 98%)
        "PROD_F": 100,    #  1% -> red (cumulative 99%)
        "PROD_G": 50,     # 0.5% -> blue (cumulative 99.5%)
        "PROD_H": 30,     # 0.3% -> blue
        "PROD_I": 15,     # 0.15% -> blue
        "PROD_J": 5,      # 0.05% -> blue
    }

    sieve = GlendaySieve(site_id="PLANT_TEST")
    count = sieve.classify(volume_data=volume_data)

    # ── Test 1: Green runner classification ────────────────────────────
    print("\n[Test 1] Green runner classification (top 50% volume)")
    green_cat = sieve.get_category("PROD_A")
    test(
        "PROD_A (50% volume) classified as GREEN",
        green_cat == RunnerCategory.GREEN,
        f"Got {green_cat}",
    )
    green_runners = sieve.green_runners()
    test(
        "Green runners list contains PROD_A",
        "PROD_A" in green_runners,
        f"Green runners: {green_runners}",
    )

    # ── Test 2: Yellow runner classification ───────────────────────────
    print("\n[Test 2] Yellow runner classification (cumulative 50-95%)")
    yellow_cat_b = sieve.get_category("PROD_B")
    yellow_cat_d = sieve.get_category("PROD_D")
    test(
        "PROD_B classified as YELLOW",
        yellow_cat_b == RunnerCategory.YELLOW,
        f"Got {yellow_cat_b}",
    )
    test(
        "PROD_D (cumulative ~95%) classified as YELLOW",
        yellow_cat_d == RunnerCategory.YELLOW,
        f"Got {yellow_cat_d}",
    )

    # ── Test 3: Red runner classification ──────────────────────────────
    print("\n[Test 3] Red runner classification (cumulative 95-99%)")
    red_cat = sieve.get_category("PROD_E")
    test(
        "PROD_E (cumulative ~98%) classified as RED",
        red_cat == RunnerCategory.RED,
        f"Got {red_cat}",
    )
    red_cat_f = sieve.get_category("PROD_F")
    test(
        "PROD_F (cumulative ~99%) classified as RED",
        red_cat_f == RunnerCategory.RED,
        f"Got {red_cat_f}",
    )

    # ── Test 4: Blue runner classification ─────────────────────────────
    print("\n[Test 4] Blue runner classification (bottom <1% volume)")
    blue_cat = sieve.get_category("PROD_G")
    test(
        "PROD_G (cumulative >99%) classified as BLUE",
        blue_cat == RunnerCategory.BLUE,
        f"Got {blue_cat}",
    )
    # Unknown product defaults to BLUE
    unknown_cat = sieve.get_category("PROD_UNKNOWN")
    test(
        "Unknown product defaults to BLUE",
        unknown_cat == RunnerCategory.BLUE,
        f"Got {unknown_cat}",
    )

    # ── Test 5: SetupMatrix changeover lookup ─────────────────────────
    print("\n[Test 5] SetupMatrix changeover time lookup")
    matrix = SetupMatrix(site_id="PLANT_TEST", db=None, default_setup_time_hours=2.0)
    entries = [
        ChangeoverEntry("PROD_A", "PROD_B", "LINE_1", 0.5),
        ChangeoverEntry("PROD_B", "PROD_A", "LINE_1", 0.75),
        ChangeoverEntry("PROD_A", "PROD_C", "*", 1.0),
    ]
    matrix.load_from_entries(entries)

    time_ab = matrix.get_changeover_time("PROD_A", "PROD_B", resource_id="LINE_1")
    test(
        "Known pair (A->B, LINE_1) returns 0.5 hours",
        time_ab == 0.5,
        f"Got {time_ab}",
    )
    time_ba = matrix.get_changeover_time("PROD_B", "PROD_A", resource_id="LINE_1")
    test(
        "Reverse pair (B->A, LINE_1) returns 0.75 hours (asymmetric)",
        time_ba == 0.75,
        f"Got {time_ba}",
    )

    # ── Test 6: Default changeover for unknown pair ───────────────────
    print("\n[Test 6] Default changeover for unknown pair")
    time_unknown = matrix.get_changeover_time("PROD_D", "PROD_E")
    test(
        "Unknown pair defaults to 2.0 hours (global default)",
        time_unknown == 2.0,
        f"Got {time_unknown}",
    )
    # Same product = 0.0
    time_same = matrix.get_changeover_time("PROD_A", "PROD_A")
    test(
        "Same product changeover is 0.0",
        time_same == 0.0,
        f"Got {time_same}",
    )
    # Wildcard resource match
    time_wildcard = matrix.get_changeover_time("PROD_A", "PROD_C", resource_id="LINE_2")
    test(
        "Wildcard resource match (A->C, *) returns 1.0 hours",
        time_wildcard == 1.0,
        f"Got {time_wildcard}",
    )

    # ── Test 7: sequence_with_glenday returns valid sequence ──────────
    print("\n[Test 7] sequence_with_glenday returns valid sequence")
    orders = [
        {"order_id": "MO_1", "product_id": "PROD_A", "priority": 1, "days_until_due": 2, "run_time_hours": 4.0, "setup_time_hours": 0.0},
        {"order_id": "MO_2", "product_id": "PROD_B", "priority": 2, "days_until_due": 5, "run_time_hours": 3.0, "setup_time_hours": 0.0},
        {"order_id": "MO_3", "product_id": "PROD_C", "priority": 3, "days_until_due": 3, "run_time_hours": 2.0, "setup_time_hours": 0.0},
        {"order_id": "MO_4", "product_id": "PROD_G", "priority": 4, "days_until_due": 10, "run_time_hours": 1.0, "setup_time_hours": 0.0},
    ]
    seq = sequence_with_glenday(
        orders=orders,
        setup_matrix=matrix,
        sieve=sieve,
        available_capacity_hours=100.0,
        current_product=None,
    )
    test(
        "sequence_with_glenday returns non-empty list",
        len(seq) > 0,
        f"Got {len(seq)} items",
    )
    test(
        "All items are SequencedMO instances",
        all(isinstance(s, SequencedMO) for s in seq),
        "Non-SequencedMO items found",
    )
    # Green runner (PROD_A) should be first in sequence
    test(
        "Green runner (PROD_A) scheduled first",
        seq[0].product_id == "PROD_A",
        f"First product is {seq[0].product_id}",
    )

    # ── Test 8: Nearest-neighbor minimizes changeover vs random ───────
    print("\n[Test 8] Nearest-neighbor minimizes total changeover time")
    # Create a matrix where products have varying changeover costs
    big_matrix = SetupMatrix(site_id="PLANT_TEST", db=None, default_setup_time_hours=5.0)
    # Create a cluster of products with low changeover between them
    cluster_entries = []
    products = ["P1", "P2", "P3", "P4", "P5", "P6"]
    for i, p1 in enumerate(products):
        for j, p2 in enumerate(products):
            if p1 != p2:
                # Adjacent products have low changeover, distant ones have high
                dist = min(abs(i - j), len(products) - abs(i - j))
                changeover = dist * 1.5
                cluster_entries.append(ChangeoverEntry(p1, p2, "*", changeover))
    big_matrix.load_from_entries(cluster_entries)

    # All products are blue runners (not classified)
    blue_sieve = GlendaySieve(site_id="PLANT_TEST")
    blue_sieve.classify(volume_data={p: 10 for p in products})  # Equal volume -> all blue-ish

    nn_orders = [
        {"order_id": f"MO_{p}", "product_id": p, "priority": 3, "days_until_due": 10, "run_time_hours": 1.0, "setup_time_hours": 0.0}
        for p in products
    ]
    nn_seq = sequence_with_glenday(
        orders=nn_orders,
        setup_matrix=big_matrix,
        sieve=blue_sieve,
        available_capacity_hours=200.0,
        current_product=None,
    )
    nn_changeover = sum(s.changeover_hours for s in nn_seq)

    # Compare with random ordering (average of 10 random shuffles)
    random_changeovers = []
    for _ in range(20):
        shuffled = list(products)
        random.shuffle(shuffled)
        total = 0.0
        for k in range(1, len(shuffled)):
            total += big_matrix.get_changeover_time(shuffled[k-1], shuffled[k])
        random_changeovers.append(total)
    avg_random = sum(random_changeovers) / len(random_changeovers)

    test(
        f"NN changeover ({nn_changeover:.1f}h) <= avg random ({avg_random:.1f}h)",
        nn_changeover <= avg_random,
        f"NN={nn_changeover:.1f}h, avg random={avg_random:.1f}h",
    )

    # ── Test 9: to_dict serialization ─────────────────────────────────
    print("\n[Test 9] Sieve serialization")
    d = sieve.to_dict()
    test(
        "to_dict has categories field",
        "categories" in d,
        f"Keys: {list(d.keys())}",
    )
    test(
        "to_dict total_products matches input",
        d["total_products"] == len(volume_data),
        f"Expected {len(volume_data)}, got {d['total_products']}",
    )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

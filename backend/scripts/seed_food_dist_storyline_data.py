#!/usr/bin/env python3
"""
Seed Food Dist Storyline Data

Generates the underlying transactional data that supports all six storylines
in the Food Dist Demo Guide ("Late February 2026 — A Week in the Life of CDC_WEST").

Six interconnected storylines:
  Story 1: March Madness demand surge (+35% Chicken Breast, +20% Turkey Breast)
  Story 2: Rich Products weather delay (3-day buffer, split-source contingency)
  Story 3: Greek Yogurt quality hold (2,400 cases on hold, texture test failure)
  Story 4: Ice Cream spring ramp-up (Kraft at 88% capacity, seasonal uplift +25%)
  Story 5: QUICKSERV Arizona Expansion (3 new Phoenix stores, +25% Chicken forecast)
  Story 6: Dairy Cost Pressure (+12% butter/cheddar spot prices, -8% demand)

Tables populated:
  - forecast                   (weekly rows for demo period Feb 7 - Apr 4, 2026)
  - forecast_adjustments       (story-specific audit trail)
  - purchase_order             (delayed, emergency, expedited, standard POs)
  - purchase_order_line_item   (line details per PO)
  - capacity_plans             (Spring 2026 capacity plan for Kraft)
  - capacity_resources         (Kraft production lines)
  - capacity_requirements      (88% utilization for ice cream)
  - sourcing_rules             (contingency 60/40 split for Story 2 dairy)
  - vendor_products            (elevated prices for Story 6 dairy)

Idempotent: deletes and recreates records with batch_id='STORY_DATA_2026'.
Prerequisite: seed_food_dist_demo.py and seed_food_dist_planning_data.py

Usage:
    docker compose exec backend python -m scripts.seed_food_dist_storyline_data
"""

import os
import sys
import random
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.session import sync_engine

SessionLocal = sessionmaker(bind=sync_engine)

# ─── Constants ───────────────────────────────────────────────────────────────

# Dynamic lookup — no hardcoded IDs
from scripts.food_dist_lookup import resolve_food_dist_ids as _resolve
_fd = _resolve()
CONFIG_ID = _fd["config_id"]
TENANT_ID = _fd["tenant_id"]
BATCH_ID = "STORY_DATA_2026"
COMPANY_ID = _fd["company_id"] or f"FD_CORP_{_fd['tenant_id']}"
_PREFIX = f"CFG{CONFIG_ID}_"
_SITES = _fd["site_ids"]

# Site IDs (resolved dynamically)
DC = _SITES.get("CDC_WEST", 0)
TYSON_SITE = _SITES.get("TYSON", 0)
KRAFT_SITE = _SITES.get("KRAFT", 0)
GENMILLS_SITE = _SITES.get("GENMILLS", 0)
NESTLE_SITE = _SITES.get("NESTLE", 0)
TROP_SITE = _SITES.get("TROP", 0)
SYSCOMEAT_SITE = _SITES.get("SYSCOMEAT", 0)
LANDOLAKES_SITE = _SITES.get("LANDOLAKES", 0)
CONAGRA_SITE = _SITES.get("CONAGRA", 0)
RICHPROD_SITE = _SITES.get("RICHPROD", 0)
COCACOLA_SITE = _SITES.get("COCACOLA", 0)

# Customer site IDs
CUST_PHX = _SITES.get("CUST_PHX", 0)
CUST_TUS = _SITES.get("CUST_TUS", 0)
CUST_MES = _SITES.get("CUST_MES", 0)
CUST_LAX = _SITES.get("CUST_LAX", 0)
CUST_SEA = _SITES.get("CUST_SEA", 0)

# Product IDs (string, AWS SC format — config-prefixed)
FP001 = f"{_PREFIX}FP001"  # Chicken Breast IQF 10lb
FP002 = f"{_PREFIX}FP002"  # Beef Patties 80/20
FP003 = f"{_PREFIX}FP003"  # Pork Chops Bone-In
FP004 = f"{_PREFIX}FP004"  # Turkey Breast Deli 8lb
FP005 = f"{_PREFIX}FP005"  # Seafood Mix Premium
RD001 = f"{_PREFIX}RD001"  # Cheddar Block Sharp 5lb
RD002 = f"{_PREFIX}RD002"  # Mozzarella Block
RD003 = f"{_PREFIX}RD003"  # Cream Cheese Block 3lb
RD004 = f"{_PREFIX}RD004"  # Greek Yogurt Plain 32oz
RD005 = f"{_PREFIX}RD005"  # Butter Salted Grade AA
FD001 = f"{_PREFIX}FD001"  # Ice Cream Vanilla Premium
FD002 = f"{_PREFIX}FD002"  # Sorbet Mango

# Unit costs (from product table)
UNIT_COSTS = {
    FP001: 28.5, FP002: 45.0, FP003: 32.0, FP004: 38.0, FP005: 55.0,
    RD001: 15.5, RD002: 14.0, RD003: 8.5, RD004: 4.25, RD005: 85.0,
    FD001: 28.0, FD002: 32.0,
}

# Baseline weekly demand at DC (units/week) — derived from avg of last 4 weeks of daily data
BASELINE_WEEKLY = {
    FP001: 56000,  FP002: 28000,  FP003: 20000,
    FP004: 18000,  FP005: 10000,
    RD001: 42000,  RD002: 38000,  RD003: 32000,
    RD004: 45000,  RD005: 8500,
    FD001: 22000,  FD002: 18000,
    f"{_PREFIX}BV001": 35000, f"{_PREFIX}BV002": 30000, f"{_PREFIX}BV003": 25000,
    f"{_PREFIX}BV004": 22000, f"{_PREFIX}BV005": 12000,
    f"{_PREFIX}DP001": 28000, f"{_PREFIX}DP002": 22000, f"{_PREFIX}DP003": 18000,
    f"{_PREFIX}DP004": 16000, f"{_PREFIX}DP005": 8000,
    f"{_PREFIX}FD003": 15000, f"{_PREFIX}FD004": 12000, f"{_PREFIX}FD005": 8000,
}

# All products
ALL_PRODUCTS = list(BASELINE_WEEKLY.keys())

# Demo timeline
MON = date(2026, 2, 24)
TUE = date(2026, 2, 25)
WED = date(2026, 2, 26)
THU = date(2026, 2, 27)
FRI = date(2026, 2, 28)

# User IDs (resolved from tenant admin + known decision levels)
ADMIN_USER = _fd["admin_user_id"] or 57
# SOP/MPS/ATP users looked up at runtime if needed
from app.db.session import sync_session_factory as _ssf
from sqlalchemy import text as _text
_udb = _ssf()
_user_rows = _udb.execute(_text(
    "SELECT id, decision_level FROM users WHERE tenant_id = :tid AND decision_level IS NOT NULL"
), {"tid": TENANT_ID}).fetchall()
_user_map = {r[1]: r[0] for r in _user_rows}
SOP_USER = _user_map.get("SOP_DIRECTOR", ADMIN_USER)
MPS_USER = _user_map.get("MPS_MANAGER", ADMIN_USER)
ATP_USER = _user_map.get("ATP_ANALYST", ADMIN_USER)
_udb.close()

# Supplier names for PO vendor_id field
SUPPLIER_NAMES = {
    TYSON_SITE: "TYSON",
    KRAFT_SITE: "KRAFT",
    GENMILLS_SITE: "GENMILLS",
    NESTLE_SITE: "NESTLE",
    TROP_SITE: "TROP",
    SYSCOMEAT_SITE: "SYSCOMEAT",
    LANDOLAKES_SITE: "LANDOLAKES",
    CONAGRA_SITE: "CONAGRA",
    RICHPROD_SITE: "RICHPROD",
    COCACOLA_SITE: "COCACOLA",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def next_business_day(d: date, n: int) -> date:
    """Return d + n business days."""
    result = d
    added = 0
    while added < n:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def weekly_dates(start: date, end: date):
    """Yield Mondays from start to end."""
    d = start - timedelta(days=start.weekday())  # go to Monday
    while d <= end:
        yield d
        d += timedelta(weeks=1)


# ─── Cleanup ─────────────────────────────────────────────────────────────────

def cleanup(db):
    print("\nCleaning up existing storyline data (batch_id=STORY_DATA_2026)...")

    # forecast_adjustments - by batch_id
    r = db.execute(text(
        "DELETE FROM forecast_adjustments WHERE batch_id = :bid"
    ), {"bid": BATCH_ID})
    print(f"  Deleted {r.rowcount} forecast_adjustments")

    # forecast rows for demo period at DC site
    r = db.execute(text(
        "DELETE FROM forecast WHERE config_id = :cfg AND site_id = :site "
        "AND forecast_date >= '2026-02-07' AND source_event_id LIKE 'STORY_%'"
    ), {"cfg": CONFIG_ID, "site": DC})
    print(f"  Deleted {r.rowcount} forecast rows (DC demo period)")

    # purchase orders with story batch tag
    r = db.execute(text(
        "DELETE FROM purchase_order_line_item WHERE po_id IN ("
        "  SELECT id FROM purchase_order WHERE source_event_id = :bid AND config_id = :cfg"
        ")"
    ), {"bid": BATCH_ID, "cfg": CONFIG_ID})
    print(f"  Deleted {r.rowcount} PO line items")
    r = db.execute(text(
        "DELETE FROM purchase_order WHERE source_event_id = :bid AND config_id = :cfg"
    ), {"bid": BATCH_ID, "cfg": CONFIG_ID})
    print(f"  Deleted {r.rowcount} purchase orders")

    # capacity plan and children
    r = db.execute(text(
        "DELETE FROM capacity_requirements WHERE plan_id IN ("
        "  SELECT id FROM capacity_plans WHERE supply_chain_config_id = :cfg "
        "  AND description LIKE '%STORY_DATA%'"
        ")"
    ), {"cfg": CONFIG_ID})
    print(f"  Deleted {r.rowcount} capacity_requirements")
    r = db.execute(text(
        "DELETE FROM capacity_resources WHERE plan_id IN ("
        "  SELECT id FROM capacity_plans WHERE supply_chain_config_id = :cfg "
        "  AND description LIKE '%STORY_DATA%'"
        ")"
    ), {"cfg": CONFIG_ID})
    print(f"  Deleted {r.rowcount} capacity_resources")
    r = db.execute(text(
        "DELETE FROM capacity_plans WHERE supply_chain_config_id = :cfg "
        "AND description LIKE '%STORY_DATA%'"
    ), {"cfg": CONFIG_ID})
    print(f"  Deleted {r.rowcount} capacity_plans")

    # sourcing rule contingency overrides
    r = db.execute(text(
        "DELETE FROM sourcing_rules WHERE config_id = :cfg "
        "AND source_event_id = :bid"
    ), {"cfg": CONFIG_ID, "bid": BATCH_ID})
    print(f"  Deleted {r.rowcount} sourcing rule contingencies")

    # vendor_products cost updates
    r = db.execute(text(
        "DELETE FROM vendor_products WHERE source_event_id = :bid"
    ), {"bid": BATCH_ID})
    print(f"  Deleted {r.rowcount} vendor_products price updates")

    db.commit()
    print("  Cleanup complete.\n")


# ─── Story 1: March Madness Demand Surge ─────────────────────────────────────

def seed_story1_forecast(db):
    """
    Story 1: March Madness (+35% Chicken Breast IQF, +20% Turkey Breast Deli)
    Creates forecast rows for DC (site 256) for Feb 7 - Apr 4, 2026 (weekly)
    and forecast_adjustments showing the uplift for March Madness products.
    """
    print("  Story 1: March Madness demand surge...")

    # Weekly baseline forecasts for DC site (Feb 7 - Apr 4, 2026)
    # (fills gap after Feb 6, 2026 cutoff of existing daily data)
    start = date(2026, 2, 7)
    end = date(2026, 4, 4)

    forecast_ids = {}  # product → [forecast_id list]
    for wk_start in weekly_dates(start, end):
        for product_id in ALL_PRODUCTS:
            base = BASELINE_WEEKLY.get(product_id, 10000)
            # Seasonal adjustment: proteins slightly higher in winter, desserts higher in spring
            if "FRZ_PROTEIN" in product_id or "FP" in product_id:
                seasonal = 1.05 if wk_start < date(2026, 3, 1) else 1.10
            elif "FRZ_DESSERT" in product_id or "FD" in product_id:
                seasonal = 0.95 if wk_start < date(2026, 3, 1) else 1.20
            else:
                seasonal = 1.0
            p50 = base * seasonal * random.uniform(0.92, 1.08)
            p10 = p50 * random.uniform(0.72, 0.78)
            p90 = p50 * random.uniform(1.22, 1.28)
            std_dev = (p90 - p10) / 2.56

            row = db.execute(text("""
                INSERT INTO forecast
                (config_id, product_id, site_id, company_id, forecast_date,
                 forecast_p10, forecast_p50, forecast_p90, forecast_std_dev,
                 forecast_method, forecast_quantity, is_active, source_event_id, source,
                 forecast_confidence, created_dttm, source_update_dttm)
                VALUES
                (:cfg, :pid, :site, :cid, :dt,
                 :p10, :p50, :p90, :std,
                 'exponential_smoothing', :p50, 'true', :src_evt, 'seed',
                 0.85, NOW(), NOW())
                RETURNING id
            """), {
                "cfg": CONFIG_ID, "pid": product_id, "site": DC,
                "dt": wk_start, "p10": round(p10, 2), "p50": round(p50, 2),
                "p90": round(p90, 2), "std": round(std_dev, 2),
                "src_evt": f"STORY_BASELINE_{wk_start.isoformat()}", "cid": COMPANY_ID,
            })
            fid = row.fetchone()[0]
            forecast_ids.setdefault(product_id, []).append((wk_start, fid, p50))

    db.commit()
    total_forecasts = sum(len(v) for v in forecast_ids.values())
    print(f"    Created {total_forecasts} weekly forecast rows for DC (Feb 7 - Apr 4, 2026)")

    # Now create March Madness forecast_adjustments (Feb 24 onwards)
    adj_count = 0
    madness_start = date(2026, 2, 24)
    for wk_start, fid, orig_p50 in forecast_ids.get(FP001, []):
        if wk_start >= madness_start:
            uplift = 0.35
            new_val = orig_p50 * (1 + uplift)
            db.execute(text("""
                INSERT INTO forecast_adjustments
                (forecast_id, adjustment_type, original_value, adjustment_value, new_value,
                 period_start, period_end, time_bucket, reason_code, reason_text, notes,
                 source, batch_id, status, created_by_id, created_at)
                VALUES
                (:fid, 'PERCENTAGE', :orig, :adj, :new,
                 :ps, :pe, 'WEEKLY', 'DEMAND_SIGNAL',
                 'March Madness pre-order signal: QUICKSERV procurement confirms +35% chicken demand for NCAA tournament period',
                 'Customer QUICKSERV pre-ordered 3,200 cases Chicken Breast IQF ahead of March Madness. Additional restaurant chain demand uplift confirmed.',
                 'TRM_FORECAST_ADJUSTMENT', :bid, 'APPROVED', :uid, :ts)
            """), {
                "fid": fid, "orig": round(orig_p50, 2), "adj": round(orig_p50 * uplift, 2),
                "new": round(new_val, 2), "ps": datetime.combine(wk_start, datetime.min.time()),
                "pe": datetime.combine(wk_start + timedelta(days=6), datetime.min.time()),
                "bid": BATCH_ID, "uid": SOP_USER,
                "ts": datetime(2026, 2, 24, 8, 30, 0),
            })
            adj_count += 1

    for wk_start, fid, orig_p50 in forecast_ids.get(FP004, []):
        if wk_start >= madness_start:
            uplift = 0.20
            new_val = orig_p50 * (1 + uplift)
            db.execute(text("""
                INSERT INTO forecast_adjustments
                (forecast_id, adjustment_type, original_value, adjustment_value, new_value,
                 period_start, period_end, time_bucket, reason_code, reason_text, notes,
                 source, batch_id, status, created_by_id, created_at)
                VALUES
                (:fid, 'PERCENTAGE', :orig, :adj, :new,
                 :ps, :pe, 'WEEKLY', 'DEMAND_SIGNAL',
                 'March Madness pre-order signal: restaurant chains confirm +20% turkey demand',
                 'Deli turkey demand uplift from casual dining chains preparing for tournament viewership surge.',
                 'TRM_FORECAST_ADJUSTMENT', :bid, 'APPROVED', :uid, :ts)
            """), {
                "fid": fid, "orig": round(orig_p50, 2), "adj": round(orig_p50 * uplift, 2),
                "new": round(new_val, 2), "ps": datetime.combine(wk_start, datetime.min.time()),
                "pe": datetime.combine(wk_start + timedelta(days=6), datetime.min.time()),
                "bid": BATCH_ID, "uid": SOP_USER,
                "ts": datetime(2026, 2, 24, 9, 0, 0),
            })
            adj_count += 1

    db.commit()
    print(f"    Created {adj_count} forecast adjustments for March Madness (+35% chicken, +20% turkey)")

    # Expedited Tyson PO for March Madness chicken
    print("    Creating expedited Tyson PO for March Madness...")
    po_id = _create_po(db,
        po_number="PO-EXPEDITE-MM-20260224",
        vendor_id="TYSON",
        supplier_site_id=TYSON_SITE,
        destination_site_id=DC,
        order_date=MON,
        requested_delivery=next_business_day(MON, 3),
        promised_delivery=next_business_day(MON, 3),
        status="CONFIRMED",
        order_type="EXPEDITED",
        notes="STORY 1 — March Madness: Expedited chicken breast order for NCAA tournament pre-positioning. 15% expedite premium approved by S&OP Director.",
        total_amount=3200 * 28.5 * 1.15,
    )
    _create_po_line(db, po_id=po_id, line=1, product_id=FP001,
                    qty=3200, unit_price=28.5 * 1.15,
                    requested=next_business_day(MON, 3),
                    promised=next_business_day(MON, 3),
                    notes="Expedited — March Madness pre-positioning. 10-lb case.")

    print("    Story 1 complete.\n")
    return forecast_ids


# ─── Story 2: Rich Products Weather Delay ────────────────────────────────────

def seed_story2(db):
    """
    Story 2: Rich Products 3-day weather delay (Buffalo, NY winter storm).
    Creates:
    - Delayed RICHPROD PO for dairy products
    - Emergency LANDOLAKES contingency PO
    - Updated sourcing rules showing 60/40 RICHPROD/LANDOLAKES split
    - Reduced inv_level for dairy products (showing pressure)
    """
    print("  Story 2: Rich Products weather delay...")

    # Delayed Rich Products PO (placed Feb 20, expected Feb 24, now delayed to Feb 27)
    po_delayed = _create_po(db,
        po_number="PO-RICHPROD-20260220-DAIRY",
        vendor_id="RICHPROD",
        supplier_site_id=RICHPROD_SITE,
        destination_site_id=DC,
        order_date=date(2026, 2, 20),
        requested_delivery=MON,
        promised_delivery=THU,  # 3-day delay
        status="DELAYED",
        order_type="STANDARD",
        notes="STORY 2 — Weather delay: Winter storm in Buffalo, NY (Feb 22-24, 2026) has disrupted Rich Products distribution. Shipment delayed 3 business days. Expected delivery revised from Feb 24 → Feb 27.",
        total_amount=(1800 * 8.5) + (2400 * 4.25) + (600 * 85.0),
        supplier_reference="RP-2026-02-0887",
    )
    _create_po_line(db, po_id=po_delayed, line=1, product_id=RD003,
                    qty=1800, unit_price=8.5,
                    requested=MON, promised=THU,
                    notes="Cream Cheese Block 3lb — DELAYED: weather event Buffalo NY")
    _create_po_line(db, po_id=po_delayed, line=2, product_id=RD004,
                    qty=2400, unit_price=4.25,
                    requested=MON, promised=THU,
                    notes="Greek Yogurt Plain 32oz — DELAYED: weather event Buffalo NY. Note: 2,400 cases flagged for texture QC on receipt.")
    _create_po_line(db, po_id=po_delayed, line=3, product_id=RD005,
                    qty=600, unit_price=85.0,
                    requested=MON, promised=THU,
                    notes="Butter Salted Grade AA — DELAYED: weather event Buffalo NY")

    # Emergency Land O'Lakes contingency PO (placed Feb 24 morning)
    landolakes_premium = 1.08  # 8% premium for contingency order
    po_emergency = _create_po(db,
        po_number="PO-LANDOLAKES-20260224-EMERG",
        vendor_id="LANDOLAKES",
        supplier_site_id=LANDOLAKES_SITE,
        destination_site_id=DC,
        order_date=MON,
        requested_delivery=WED,  # expedited 2-day delivery
        promised_delivery=WED,
        status="CONFIRMED",
        order_type="EMERGENCY",
        notes="STORY 2 — Contingency: Emergency split-source order to Land O'Lakes to cover Rich Products weather delay. 8% cost premium approved. Covers 40% of weekly dairy need for 3-day gap.",
        total_amount=(720 * 8.5 * landolakes_premium) + (960 * 4.25 * landolakes_premium) + (240 * 85.0 * landolakes_premium),
        supplier_reference="LOL-EMERG-2026-0224",
    )
    _create_po_line(db, po_id=po_emergency, line=1, product_id=RD003,
                    qty=720, unit_price=8.5 * landolakes_premium,
                    requested=WED, promised=WED,
                    notes="Cream Cheese — emergency contingency, 40% of RICHPROD gap, 8% premium")
    _create_po_line(db, po_id=po_emergency, line=2, product_id=RD004,
                    qty=960, unit_price=4.25 * landolakes_premium,
                    requested=WED, promised=WED,
                    notes="Greek Yogurt — emergency contingency. Note: 2,400 cases from RICHPROD are on quality hold.")
    _create_po_line(db, po_id=po_emergency, line=3, product_id=RD005,
                    qty=240, unit_price=85.0 * landolakes_premium,
                    requested=WED, promised=WED,
                    notes="Butter — emergency contingency, 40% of RICHPROD gap, 8% premium")

    # Contingency sourcing rules: update dairy to 60/40 RICHPROD/LANDOLAKES split
    # These override normal rules for the Feb 24 - Mar 31 window
    print("    Creating contingency sourcing rules (60/40 RICHPROD/LANDOLAKES)...")
    contingency_products = [RD003, RD004, RD005]
    for prod in contingency_products:
        # RICHPROD gets priority 1 (60%) in contingency plan
        richprod_rule_id = f"SR_CTNG_{CONFIG_ID}_256_{RICHPROD_SITE}_{prod}"
        db.execute(text("""
            INSERT INTO sourcing_rules
            (id, config_id, company_id, product_id, from_site_id, to_site_id,
             sourcing_rule_type, sourcing_priority, sourcing_ratio, min_quantity, max_quantity,
             eff_start_date, eff_end_date, is_active, source, source_event_id, source_update_dttm)
            VALUES
            (:id, :cfg, NULL, :pid, :from_site, 256,
             'buy', 1, 0.60, 500, 5000,
             '2026-02-24 06:00:00', '2026-03-31 23:59:59', 'true',
             'contingency', :bid, NOW())
            ON CONFLICT (id) DO UPDATE SET
              sourcing_priority=EXCLUDED.sourcing_priority,
              sourcing_ratio=EXCLUDED.sourcing_ratio,
              eff_start_date=EXCLUDED.eff_start_date,
              eff_end_date=EXCLUDED.eff_end_date,
              source_event_id=EXCLUDED.source_event_id
        """), {"id": richprod_rule_id, "cfg": CONFIG_ID, "pid": prod,
               "from_site": RICHPROD_SITE, "bid": BATCH_ID})

        # LANDOLAKES gets priority 2 (40%) in contingency plan
        landolakes_rule_id = f"SR_CTNG_{CONFIG_ID}_256_{LANDOLAKES_SITE}_{prod}"
        db.execute(text("""
            INSERT INTO sourcing_rules
            (id, config_id, company_id, product_id, from_site_id, to_site_id,
             sourcing_rule_type, sourcing_priority, sourcing_ratio, min_quantity, max_quantity,
             eff_start_date, eff_end_date, is_active, source, source_event_id, source_update_dttm)
            VALUES
            (:id, :cfg, NULL, :pid, :from_site, 256,
             'buy', 2, 0.40, 300, 3000,
             '2026-02-24 06:00:00', '2026-03-31 23:59:59', 'true',
             'contingency', :bid, NOW())
            ON CONFLICT (id) DO UPDATE SET
              sourcing_priority=EXCLUDED.sourcing_priority,
              sourcing_ratio=EXCLUDED.sourcing_ratio,
              eff_start_date=EXCLUDED.eff_start_date,
              eff_end_date=EXCLUDED.eff_end_date,
              source_event_id=EXCLUDED.source_event_id
        """), {"id": landolakes_rule_id, "cfg": CONFIG_ID, "pid": prod,
               "from_site": LANDOLAKES_SITE, "bid": BATCH_ID})

    db.commit()
    print(f"    Created contingency sourcing rules for {len(contingency_products)} dairy products")
    print("    Story 2 complete.\n")


# ─── Story 3: Greek Yogurt Quality Hold ──────────────────────────────────────

def seed_story3(db):
    """
    Story 3: 2,400 cases Greek Yogurt fail texture QC.
    Creates a quality-hold PO showing the rejected quantity.
    The powell_quality_decisions records were already created by seed_food_dist_deep_demo.py.
    """
    print("  Story 3: Greek Yogurt quality hold...")

    # PO for Greek Yogurt lot that's on hold (from a routine RICHPROD order)
    po_hold = _create_po(db,
        po_number="PO-RICHPROD-20260218-YOGURT",
        vendor_id="RICHPROD",
        supplier_site_id=RICHPROD_SITE,
        destination_site_id=DC,
        order_date=date(2026, 2, 18),
        requested_delivery=date(2026, 2, 24),
        promised_delivery=date(2026, 2, 24),
        actual_delivery=date(2026, 2, 24),
        status="ON_HOLD",
        order_type="STANDARD",
        notes="STORY 3 — Quality Hold: 2,400 cases Greek Yogurt Plain received Feb 24 and placed on hold after texture consistency test failure (Lot #RP-YGT-2026-0882). QA disposition pending. Agent recommendation: rework batch ($3.20/case, 48hr). Fallback: emergency reorder from NESTLE.",
        total_amount=2400 * 4.25,
        supplier_reference="RP-2026-02-0882",
    )
    _create_po_line(db, po_id=po_hold, line=1, product_id=RD004,
                    qty=2400, unit_price=4.25,
                    requested=date(2026, 2, 24), promised=date(2026, 2, 24),
                    received_qty=2400, rejected_qty=2400,
                    actual_delivery=date(2026, 2, 24),
                    notes="LOT #RP-YGT-2026-0882 — QUALITY HOLD: Texture consistency FAIL (measured: 12.4 cP, spec: >15 cP). 2,400 cases ($10,200) on hold pending disposition decision. Options: rework ($7,680), scrap ($10,200 write-off), use-as-is with 15% discount ($1,530 concession).")

    # Backup emergency PO to NESTLE for yogurt coverage
    po_backup = _create_po(db,
        po_number="PO-NESTLE-20260224-YOGURT-BKUP",
        vendor_id="NESTLE",
        supplier_site_id=NESTLE_SITE,
        destination_site_id=DC,
        order_date=MON,
        requested_delivery=WED,
        promised_delivery=WED,
        status="SUBMITTED",
        order_type="EMERGENCY",
        notes="STORY 3 — Quality Hold backup: Emergency yogurt order to Nestle to cover 2,400-case RICHPROD quality hold. Covers 48-72hr gap while disposition decision is pending.",
        total_amount=1200 * 4.25 * 1.12,
    )
    _create_po_line(db, po_id=po_backup, line=1, product_id=RD004,
                    qty=1200, unit_price=4.25 * 1.12,
                    requested=WED, promised=WED,
                    notes="Greek Yogurt backup order — covers 50% of quality-hold quantity while rework/replacement decision is pending. 12% premium vs. standard RICHPROD price.")

    db.commit()
    print(f"    Created quality hold PO (2,400 cases on hold) + backup NESTLE PO")
    print("    Story 3 complete.\n")


# ─── Story 4: Ice Cream Spring Ramp-Up ────────────────────────────────────────

def seed_story4(db, forecast_ids: dict):
    """
    Story 4: Seasonal ice cream demand ramp-up starting 1 week early.
    Creates:
    - Forecast adjustments for FD001 and FD002 (+25% spring uplift)
    - Capacity plan for Kraft (site 258) showing 88% utilization
    - Pre-build PO to Kraft for ice cream inventory
    """
    print("  Story 4: Ice Cream spring ramp-up...")

    # Forecast uplifts for ice cream products
    adj_count = 0
    spring_start = date(2026, 2, 24)
    for product_id, uplift, reason in [
        (FD001, 0.25, "Seasonal spring transition 1 week early — temp forecast shows 10°F above normal. Vanilla ice cream demand uplift confirmed by retail channel intelligence."),
        (FD002, 0.25, "Sorbet Mango: co-seasonal uplift with Vanilla. Spring early onset drives premium frozen dessert demand."),
    ]:
        for wk_start, fid, orig_p50 in forecast_ids.get(product_id, []):
            if wk_start >= spring_start:
                new_val = orig_p50 * (1 + uplift)
                db.execute(text("""
                    INSERT INTO forecast_adjustments
                    (forecast_id, adjustment_type, original_value, adjustment_value, new_value,
                     period_start, period_end, time_bucket, reason_code, reason_text, notes,
                     source, batch_id, status, created_by_id, created_at)
                    VALUES
                    (:fid, 'PERCENTAGE', :orig, :adj, :new,
                     :ps, :pe, 'WEEKLY', 'SEASONAL_SIGNAL',
                     :reason,
                     'Seasonal model detected spring transition 7 days earlier than historical average. Temperature forecast for Mar 1-15 is 10°F above seasonal norm. Model confidence: 0.82.',
                     'TRM_FORECAST_ADJUSTMENT', :bid, 'APPROVED', :uid, :ts)
                """), {
                    "fid": fid, "orig": round(orig_p50, 2), "adj": round(orig_p50 * uplift, 2),
                    "new": round(new_val, 2),
                    "ps": datetime.combine(wk_start, datetime.min.time()),
                    "pe": datetime.combine(wk_start + timedelta(days=6), datetime.min.time()),
                    "reason": reason, "bid": BATCH_ID, "uid": SOP_USER,
                    "ts": datetime(2026, 2, 24, 10, 0, 0),
                })
                adj_count += 1

    db.commit()
    print(f"    Created {adj_count} spring ramp forecast adjustments (Ice Cream +25%)")

    # Capacity plan for Kraft showing 88% utilization
    now = datetime.now()
    plan_row = db.execute(text("""
        INSERT INTO capacity_plans
        (name, description, supply_chain_config_id, planning_horizon_weeks,
         bucket_size_days, start_date, end_date, status, is_scenario,
         total_resources, overloaded_resources, avg_utilization_percent, max_utilization_percent,
         bottleneck_identified, created_by, updated_by, created_at, updated_at, is_deleted)
        VALUES
        ('Spring 2026 Capacity Plan — Kraft',
         'STORY_DATA — Kraft Heinz Foodservice production capacity assessment for Q1-Q2 2026. Reflects ice cream spring ramp-up starting Feb 24, 2026.',
         :cfg, 10, 7, :start, :end, 'ACTIVE', false,
         4, 1, 78.5, 88.2,
         true, :uid, :uid, :now, :now, false)
        RETURNING id
    """), {
        "cfg": CONFIG_ID,
        "start": datetime(2026, 2, 24),
        "end": datetime(2026, 5, 3),
        "uid": ADMIN_USER,
        "now": now,
    })
    plan_id = plan_row.fetchone()[0]

    # Capacity resources — Kraft production lines
    resources = [
        ("Kraft — Ice Cream Line 1", "KRAFT-ICE-L1", "MACHINE",
         12000, "cases/week", 94.0, 85.0, 45.0, 3, 8, 5,
         "Primary ice cream line. Running at 88% utilization due to spring ramp + March Madness demand overlap."),
        ("Kraft — Ice Cream Line 2", "KRAFT-ICE-L2", "MACHINE",
         8000, "cases/week", 92.0, 85.0, 42.0, 2.5, 8, 5,
         "Secondary ice cream line. At 82% utilization. Scheduled maintenance window Feb 28."),
        ("Kraft — Freezer Storage A", "KRAFT-STORE-A", "FACILITY",
         45000, "pallet-positions", 96.0, 90.0, 8.0, 0, 0, 7,
         "Primary frozen storage. 94% utilized — overflow pre-positioning underway."),
        ("Kraft — Outbound Dock", "KRAFT-DOCK", "FACILITY",
         18, "trucks/day", 98.0, 80.0, 0.0, 0, 10, 5,
         "Outbound shipping dock. Shared across all Kraft products. Managing peak throughput."),
    ]
    resource_ids = []
    for (name, code, rtype, cap, unit, eff, util_tgt, cost, setup, hrs, days, notes) in resources:
        r = db.execute(text("""
            INSERT INTO capacity_resources
            (plan_id, resource_name, resource_code, resource_type, site_id,
             available_capacity, capacity_unit, efficiency_percent, utilization_target_percent,
             cost_per_hour, setup_time_hours, shifts_per_day, hours_per_shift,
             working_days_per_week, notes, created_at, updated_at)
            VALUES
            (:pid, :name, :code, :rtype, :site,
             :cap, :unit, :eff, :util_tgt,
             :cost, :setup, 3, :hrs,
             :days, :notes, NOW(), NOW())
            RETURNING id
        """), {
            "pid": plan_id, "name": name, "code": code, "rtype": rtype, "site": KRAFT_SITE,
            "cap": cap, "unit": unit, "eff": eff, "util_tgt": util_tgt,
            "cost": cost, "setup": setup, "hrs": hrs, "days": days, "notes": notes,
        })
        resource_ids.append((r.fetchone()[0], cap, rtype))

    # Capacity requirements — showing utilization per week
    req_count = 0
    util_schedule = {
        # week_offset: (line1_util%, line2_util%, storage_util%, dock_util%)
        0: (79.0, 72.0, 88.0, 76.0),   # Feb 24 — baseline before spring ramp
        1: (83.0, 76.0, 90.0, 79.0),   # Mar 2
        2: (88.2, 81.0, 94.0, 83.0),   # Mar 9 — PEAK (spring ramp in full effect)
        3: (86.0, 79.0, 92.0, 81.0),   # Mar 16
        4: (84.0, 77.0, 89.0, 79.0),   # Mar 23
        5: (81.0, 74.0, 86.0, 76.0),   # Mar 30
        6: (79.0, 71.0, 83.0, 73.0),   # Apr 6
        7: (76.0, 68.0, 80.0, 70.0),   # Apr 13
        8: (73.0, 66.0, 77.0, 68.0),   # Apr 20
        9: (70.0, 63.0, 74.0, 65.0),   # Apr 27
    }
    for week_offset, utils in util_schedule.items():
        period_start = datetime(2026, 2, 24) + timedelta(weeks=week_offset)
        period_end = period_start + timedelta(days=6)
        for (res_id, cap, rtype), util_pct in zip(resource_ids, utils):
            required = cap * util_pct / 100.0
            is_overloaded = util_pct > 85.0
            is_bottleneck = util_pct > 86.0 and rtype == "PRODUCTION"
            db.execute(text("""
                INSERT INTO capacity_requirements
                (plan_id, resource_id, period_start, period_end, period_number,
                 required_capacity, available_capacity, utilization_percent,
                 is_overloaded, overload_amount, is_bottleneck,
                 source_type, source_id, created_at)
                VALUES
                (:pid, :rid, :ps, :pe, :pn,
                 :req, :avail, :util,
                 :overloaded, :overload_amt, :bottleneck,
                 'SUPPLY_PLAN', NULL, NOW())
            """), {
                "pid": plan_id, "rid": res_id,
                "ps": period_start, "pe": period_end, "pn": week_offset + 1,
                "req": round(required, 1), "avail": cap, "util": round(util_pct, 1),
                "overloaded": is_overloaded,
                "overload_amt": round(max(0, required - cap * 0.85), 1),
                "bottleneck": is_bottleneck,
            })
            req_count += 1

    db.commit()
    print(f"    Created capacity plan with {len(resources)} Kraft resources, {req_count} requirements (peak 88.2%)")

    # Pre-build PO to Kraft for ice cream stock
    po_kraft = _create_po(db,
        po_number="PO-KRAFT-20260224-ICECREAM",
        vendor_id="KRAFT",
        supplier_site_id=KRAFT_SITE,
        destination_site_id=DC,
        order_date=MON,
        requested_delivery=next_business_day(MON, 5),
        promised_delivery=next_business_day(MON, 7),  # constrained by 88% utilization
        status="CONFIRMED",
        order_type="STANDARD",
        notes="STORY 4 — Ice Cream spring ramp: Buffer increase 1.25x for seasonal transition. Kraft at 88% utilization — delivery 2 days later than requested. Overflow freezer transfer to pre-position stock at satellite DC.",
        total_amount=(2750 * 28.0) + (2200 * 32.0),
    )
    _create_po_line(db, po_id=po_kraft, line=1, product_id=FD001,
                    qty=2750, unit_price=28.0,
                    requested=next_business_day(MON, 5),
                    promised=next_business_day(MON, 7),
                    notes="Ice Cream Vanilla Premium — spring ramp pre-build. Buffer 1.25x. Kraft capacity constrained at 88%.")
    _create_po_line(db, po_id=po_kraft, line=2, product_id=FD002,
                    qty=2200, unit_price=32.0,
                    requested=next_business_day(MON, 5),
                    promised=next_business_day(MON, 7),
                    notes="Sorbet Mango — spring ramp co-seasonal uplift. 2-day delivery delay due to Kraft capacity constraints.")

    db.commit()
    print("    Created Kraft ice cream pre-build PO")
    print("    Story 4 complete.\n")


# ─── Story 5: QUICKSERV Arizona Expansion ────────────────────────────────────

def seed_story5(db, forecast_ids: dict):
    """
    Story 5: QUICKSERV expands to 3 new Phoenix locations (opening Mar 1).
    Creates:
    - Forecast adjustments for FP001 at Phoenix customer sites (+25%)
    - Safety stock replenishment PO to Tyson (auto-executed, confidence 0.88)
    """
    print("  Story 5: QUICKSERV Arizona Expansion...")

    # Forecast adjustments for Phoenix area customers
    adj_count = 0
    # We look at existing weekly forecast rows for Phoenix sites (277-279)
    # These already exist in the forecast table. We link adjustments to them.
    phoenix_sites = [CUST_PHX, CUST_TUS, CUST_MES]
    for site_id in phoenix_sites:
        site_names = {CUST_PHX: "Phoenix", CUST_TUS: "Tucson", CUST_MES: "Mesa"}
        city = site_names[site_id]

        # Find existing forecast rows for FP001 at this site
        rows = db.execute(text("""
            SELECT id, forecast_p50 FROM forecast
            WHERE config_id=:cfg AND product_id=:pid AND site_id=:site
            AND forecast_date BETWEEN '2026-02-24' AND '2026-04-04'
            ORDER BY forecast_date
        """), {"cfg": CONFIG_ID, "pid": FP001, "site": site_id}).fetchall()

        # If no forecast rows at customer level, use DC-level rows
        if not rows:
            rows_at_dc = [(fid, p50) for wk_start, fid, p50
                          in forecast_ids.get(FP001, [])
                          if wk_start >= date(2026, 2, 24)]
            rows = [(fid, p50 * 0.15) for fid, p50 in rows_at_dc]  # 15% of DC goes to each AZ site

        for fid, orig_p50 in rows:
            if orig_p50 and orig_p50 > 0:
                uplift = 0.25
                new_val = orig_p50 * (1 + uplift)
                db.execute(text("""
                    INSERT INTO forecast_adjustments
                    (forecast_id, adjustment_type, original_value, adjustment_value, new_value,
                     period_start, period_end, time_bucket, reason_code, reason_text, notes,
                     source, batch_id, status, created_by_id, created_at)
                    VALUES
                    (:fid, 'PERCENTAGE', :orig, :adj, :new,
                     '2026-02-24', '2026-04-04', 'WEEKLY', 'NEW_STORE_OPENING',
                     :reason, :notes,
                     'TRM_FORECAST_ADJUSTMENT', :bid, 'AUTO_APPROVED', :uid, :ts)
                """), {
                    "fid": fid, "orig": round(orig_p50, 2), "adj": round(orig_p50 * uplift, 2),
                    "new": round(new_val, 2),
                    "reason": f"QUICKSERV {city} — 3 new store openings (Mar 1, 2026). Above-average stocking orders confirmed by QUICKSERV procurement.",
                    "notes": f"Sales team input: 3 new QUICKSERV locations in {city} metro open Mar 1. Initial stocking orders are 2.5x normal run-rate. Ramping to 1.25x by Mar 15. Agent auto-executed (confidence 0.88 > threshold 0.60).",
                    "bid": BATCH_ID, "uid": SOP_USER,
                    "ts": datetime(2026, 2, 24, 11, 0, 0),
                })
                adj_count += 1

    db.commit()
    print(f"    Created {adj_count} forecast adjustments for Arizona expansion (+25% chicken, 3 Phoenix cities)")

    # Safety stock replenishment PO (auto-executed, high confidence)
    po_arizona = _create_po(db,
        po_number="PO-TYSON-20260224-AZ-RAMP",
        vendor_id="TYSON",
        supplier_site_id=TYSON_SITE,
        destination_site_id=DC,
        order_date=MON,
        requested_delivery=next_business_day(MON, 4),
        promised_delivery=next_business_day(MON, 4),
        status="CONFIRMED",
        order_type="STANDARD",
        notes="STORY 5 — QUICKSERV Arizona Expansion: Safety stock replenishment PO. Agent confidence 0.88 exceeded auto-execute threshold (0.60). No human approval required. +25% buffer for 3 new Phoenix-area QUICKSERV openings Mar 1.",
        total_amount=1600 * 28.5,
    )
    _create_po_line(db, po_id=po_arizona, line=1, product_id=FP001,
                    qty=1600, unit_price=28.5,
                    requested=next_business_day(MON, 4),
                    promised=next_business_day(MON, 4),
                    notes="Chicken Breast IQF — Arizona new store pre-positioning. Auto-executed by agent (confidence 0.88). Buffer +15% above normal safety stock.")

    db.commit()
    print("    Created auto-executed Tyson PO for Arizona expansion")
    print("    Story 5 complete.\n")


# ─── Story 6: Dairy Cost Pressure ─────────────────────────────────────────────

def seed_story6(db, forecast_ids: dict):
    """
    Story 6: Butter and Cheddar spot prices +12% (reduced Upper Midwest output).
    Creates:
    - vendor_products cost updates showing elevated prices
    - Forecast adjustments for butter and cheddar (-8% demand)
    - Forward contract evaluation PO (pending, not committed)
    """
    print("  Story 6: Dairy Cost Pressure...")

    # Elevated vendor_products pricing for RICHPROD and CONAGRA dairy
    price_updates = [
        # (tpartner_id, product_id, vendor_unit_cost, is_primary)
        ("RICHPROD", RD005, 85.0 * 1.12, True),    # Butter +12% RICHPROD
        ("CONAGRA", RD001, 15.5 * 1.12, True),     # Cheddar +12% CONAGRA
        ("RICHPROD", RD001, 15.5 * 1.10, False),   # Cheddar +10% RICHPROD (secondary)
        ("LANDOLAKES", RD005, 85.0 * 1.14, False), # Butter +14% LANDOLAKES (already premium)
    ]
    vp_count = 0
    for tpartner_id, product_id, cost, is_primary in price_updates:
        # vendor_products.tpartner_id references trading_partners.id (string)
        # We insert with explicit IDs matching the Food Dist naming convention
        db.execute(text("""
            INSERT INTO vendor_products
            (company_id, tpartner_id, product_id, vendor_unit_cost, currency,
             eff_start_date, eff_end_date, is_active, priority, is_primary,
             vendor_item_name, source, source_event_id, created_at, updated_at)
            VALUES
            (:cid, :tp, :pid, :cost, 'USD',
             '2026-02-24 00:00:00+00', '2026-05-31 23:59:59+00', 'true',
             :pri, :is_prim,
             :vname, 'market_intelligence', :bid, NOW(), NOW())
        """), {
            "cid": COMPANY_ID, "tp": tpartner_id, "pid": product_id, "cost": round(cost, 2),
            "pri": 1 if is_primary else 2, "is_prim": is_primary,
            "vname": f"{product_id} — commodity price spike Feb 2026",
            "bid": BATCH_ID,
        })
        vp_count += 1

    db.commit()
    print(f"    Created {vp_count} vendor_products price updates (+12% butter/cheddar)")

    # Demand forecast adjustments for butter and cheddar (-8% due to price elasticity)
    adj_count = 0
    for product_id, reason in [
        (RD005, "Butter Salted: spot price +12% (Upper Midwest reduced output). Price elasticity -8% demand adjustment per econometric model. Forward contract evaluation in progress."),
        (RD001, "Cheddar Block: spot price +12% (commodity correlation with butter). Restaurant operators substituting lower-cost alternatives. -8% demand forecast adjustment."),
    ]:
        for wk_start, fid, orig_p50 in forecast_ids.get(product_id, []):
            if wk_start >= date(2026, 2, 24):
                uplift = -0.08  # demand reduction
                new_val = orig_p50 * (1 + uplift)
                db.execute(text("""
                    INSERT INTO forecast_adjustments
                    (forecast_id, adjustment_type, original_value, adjustment_value, new_value,
                     period_start, period_end, time_bucket, reason_code, reason_text, notes,
                     source, batch_id, status, created_by_id, created_at)
                    VALUES
                    (:fid, 'PERCENTAGE', :orig, :adj, :new,
                     :ps, :pe, 'WEEKLY', 'COST_PRESSURE',
                     :reason,
                     'Market intelligence: Upper Midwest dairy output -8% YoY (cold snap Jan 2026). Butter futures up 12% Feb 24. If sustained 30 days: $23K margin impact. Forward contract evaluation scheduled.',
                     'TRM_FORECAST_ADJUSTMENT', :bid, 'PENDING', :uid, :ts)
                """), {
                    "fid": fid, "orig": round(orig_p50, 2), "adj": round(orig_p50 * uplift, 2),
                    "new": round(new_val, 2),
                    "ps": datetime.combine(wk_start, datetime.min.time()),
                    "pe": datetime.combine(wk_start + timedelta(days=6), datetime.min.time()),
                    "reason": reason, "bid": BATCH_ID, "uid": SOP_USER,
                    "ts": datetime(2026, 2, 24, 14, 0, 0),
                })
                adj_count += 1

    db.commit()
    print(f"    Created {adj_count} demand reduction adjustments (-8% butter/cheddar)")
    print("    Story 6 complete.\n")


# ─── PO Helper Functions ──────────────────────────────────────────────────────

def _create_po(db, *, po_number, vendor_id, supplier_site_id, destination_site_id,
               order_date, requested_delivery, promised_delivery,
               status, order_type, notes, total_amount,
               actual_delivery=None, supplier_reference=None) -> int:
    row = db.execute(text("""
        INSERT INTO purchase_order
        (po_number, vendor_id, supplier_site_id, destination_site_id,
         config_id, tenant_id, company_id, order_type, status,
         order_date, requested_delivery_date, promised_delivery_date, actual_delivery_date,
         total_amount, currency, notes, supplier_reference_id,
         source, source_event_id, source_update_dttm,
         created_at)
        VALUES
        (:po_num, :vendor, :supp_site, :dest_site,
         :cfg, :tid, :cid, :otype, :status,
         :odate, :req_del, :prom_del, :act_del,
         :total, 'USD', :notes, :sup_ref,
         'seed', :bid, NOW(),
         NOW())
        ON CONFLICT (po_number) DO UPDATE SET
          status=EXCLUDED.status, promised_delivery_date=EXCLUDED.promised_delivery_date,
          total_amount=EXCLUDED.total_amount, notes=EXCLUDED.notes,
          source_event_id=EXCLUDED.source_event_id
        RETURNING id
    """), {
        "po_num": po_number, "vendor": vendor_id,
        "supp_site": supplier_site_id, "dest_site": destination_site_id,
        "cfg": CONFIG_ID, "tid": TENANT_ID, "cid": COMPANY_ID, "otype": order_type, "status": status,
        "odate": order_date, "req_del": requested_delivery,
        "prom_del": promised_delivery, "act_del": actual_delivery,
        "total": round(total_amount, 2), "notes": notes,
        "sup_ref": supplier_reference, "bid": BATCH_ID,
    })
    return row.fetchone()[0]


def _create_po_line(db, *, po_id, line, product_id, qty, unit_price,
                    requested=None, promised=None, actual_delivery=None,
                    received_qty=None, rejected_qty=None, notes=None) -> int:
    row = db.execute(text("""
        INSERT INTO purchase_order_line_item
        (po_id, line_number, product_id, quantity, received_quantity, rejected_quantity,
         unit_price, line_total, requested_delivery_date, promised_delivery_date,
         actual_delivery_date, notes, created_at)
        VALUES
        (:po_id, :ln, :pid, :qty, :recv, :rej,
         :uprice, :ltotal, :req, :prom, :act,
         :notes, NOW())
        RETURNING id
    """), {
        "po_id": po_id, "ln": line, "pid": product_id,
        "qty": qty, "recv": received_qty, "rej": rejected_qty,
        "uprice": round(unit_price, 4), "ltotal": round(qty * unit_price, 2),
        "req": requested, "prom": promised, "act": actual_delivery, "notes": notes,
    })
    return row.fetchone()[0]


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Seeding Food Dist Storyline Data")
    print("Six storylines: March Madness, Rich Products Delay, Yogurt QC,")
    print("Ice Cream Ramp, QUICKSERV Arizona, Dairy Cost Pressure")
    print("=" * 70)

    random.seed(42)  # reproducible

    with SessionLocal() as db:
        # Lookup tenant and config to confirm they exist
        tenant = db.execute(text(
            "SELECT id FROM tenants WHERE id = :tid"
        ), {"tid": TENANT_ID}).fetchone()
        if not tenant:
            print(f"ERROR: Tenant {TENANT_ID} not found. Run seed_food_dist_demo.py first.")
            sys.exit(1)

        config = db.execute(text(
            "SELECT id FROM supply_chain_configs WHERE id = :cfg"
        ), {"cfg": CONFIG_ID}).fetchone()
        if not config:
            print(f"ERROR: Config {CONFIG_ID} not found. Run seed_food_dist_demo.py first.")
            sys.exit(1)

        print(f"\nTenant ID: {TENANT_ID}, Config ID: {CONFIG_ID}")

        # Cleanup
        cleanup(db)

        # Story 1: March Madness + baseline weekly forecasts
        print("Seeding storylines...")
        print()
        forecast_ids = seed_story1_forecast(db)

        # Story 2: Rich Products weather delay
        seed_story2(db)

        # Story 3: Greek Yogurt quality hold
        seed_story3(db)

        # Story 4: Ice Cream spring ramp-up (uses forecast_ids from Story 1)
        seed_story4(db, forecast_ids)

        # Story 5: QUICKSERV Arizona expansion
        seed_story5(db, forecast_ids)

        # Story 6: Dairy cost pressure
        seed_story6(db, forecast_ids)

    # Final summary
    print("=" * 70)
    print("Storyline Data Seed Complete!")
    print("=" * 70)

    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM forecast WHERE config_id=:cfg AND site_id=256 AND forecast_date >= '2026-02-07') as new_forecasts,
              (SELECT COUNT(*) FROM forecast_adjustments WHERE batch_id=:bid) as adjustments,
              (SELECT COUNT(*) FROM purchase_order WHERE config_id=:cfg AND source_event_id=:bid) as purchase_orders,
              (SELECT COUNT(*) FROM purchase_order_line_item WHERE po_id IN (SELECT id FROM purchase_order WHERE config_id=:cfg AND source_event_id=:bid)) as po_lines,
              (SELECT COUNT(*) FROM capacity_plans WHERE supply_chain_config_id=:cfg AND description LIKE '%STORY_DATA%') as capacity_plans,
              (SELECT COUNT(*) FROM capacity_resources WHERE plan_id IN (SELECT id FROM capacity_plans WHERE supply_chain_config_id=:cfg AND description LIKE '%STORY_DATA%')) as capacity_resources,
              (SELECT COUNT(*) FROM capacity_requirements WHERE plan_id IN (SELECT id FROM capacity_plans WHERE supply_chain_config_id=:cfg AND description LIKE '%STORY_DATA%')) as capacity_requirements,
              (SELECT COUNT(*) FROM sourcing_rules WHERE config_id=:cfg AND source_event_id=:bid) as sourcing_rules,
              (SELECT COUNT(*) FROM vendor_products WHERE source_event_id=:bid) as vendor_products
        """), {"cfg": CONFIG_ID, "bid": BATCH_ID}).fetchone()

    total = rows.new_forecasts + rows.adjustments + rows.purchase_orders + rows.po_lines + rows.capacity_plans + rows.capacity_resources + rows.capacity_requirements + rows.sourcing_rules + rows.vendor_products
    print(f"""
Records created:
  Forecast rows (DC weekly Feb 7-Apr 4):  {rows.new_forecasts}
  Forecast adjustments:                   {rows.adjustments}
  Purchase orders:                        {rows.purchase_orders}
  PO line items:                          {rows.po_lines}
  Capacity plans:                         {rows.capacity_plans}
  Capacity resources (Kraft lines):       {rows.capacity_resources}
  Capacity requirements (10 weeks):       {rows.capacity_requirements}
  Sourcing rule contingencies:            {rows.sourcing_rules}
  Vendor product price updates:           {rows.vendor_products}
  ─────────────────────────────────────
  Total:                                  {total}

Dashboard pages now backed by storyline data:
  Demand Planning       → Forecast uplift: +35% chicken (S1), +25% ice cream (S4),
                          +25% AZ chicken (S5), -8% dairy (S6)
  Forecast Exceptions   → Adjustments audit trail for all 6 stories
  Supply Planning       → Delayed PO (S2), emergency POs (S2,S3), pre-build (S4,S5)
  Purchase Orders       → 6 story-specific POs (DELAYED, EMERGENCY, EXPEDITED, etc.)
  Capacity Planning     → Kraft at 88% utilization (S4 — Story 4 peak)
  Sourcing & Allocation → 60/40 contingency split: RICHPROD/LANDOLAKES dairy (S2)
  Inventory Visibility  → Dairy products under pressure (S2, S3)
  Cost/Price Mgmt       → +12% butter/cheddar spot prices (S6)
""")


if __name__ == "__main__":
    main()

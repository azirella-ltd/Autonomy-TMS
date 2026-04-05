#!/usr/bin/env python3
"""Seed external signal snapshot for a frozen demo tenant.

Generates a realistic set of external market signals (economic, weather,
energy, geopolitical, commodity, trade) anchored to the tenant's virtual_today.
These signals feed the Azirella RAG context and make the frozen demo feel
as if it was captured at the reference date.

Usage:
    python scripts/seed_frozen_demo_signals.py --tenant-id 20

By default, seeds the tenant's virtual_today ± 30 days (rolling window so
get_relevant_signals(max_age_days=14) returns meaningful content).

See docs/internal/VIRTUAL_CLOCK_ARCHITECTURE.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import sync_session_factory
from sqlalchemy import text


# Realistic signal templates anchored around Nov 2025 market conditions.
# Each template produces ONE signal on a specific day offset from virtual_today.
# Offsets are NEGATIVE (days before virtual_today) so get_relevant_signals(14-day window)
# returns them.
SIGNAL_TEMPLATES: List[Dict[str, Any]] = [
    # ─── Economic Indicators (FRED-style) ───────────────────────────
    {
        "day_offset": -3,
        "source_key": "fred",
        "category": "economic",
        "signal_type": "indicator",
        "signal_key": "fred:CPIAUCSL:2025-10",
        "title": "US Consumer Price Index: 2.9% YoY (Oct 2025)",
        "summary": "Headline CPI rose 0.2% MoM in October to 2.9% YoY, up from 2.7% in September. Core services remain sticky at 3.8%. Food inflation steady at 2.4%.",
        "raw_value": 2.9,
        "raw_unit": "pct_yoy",
        "change_pct": 0.2,
        "change_direction": "up",
        "relevance_score": 0.75,
        "urgency_score": 0.4,
        "affected_trm_types": ["po_creation", "forecast_adjustment"],
        "planning_layer": "strategic",
        "expiry_days": 45,
    },
    {
        "day_offset": -5,
        "source_key": "fred",
        "category": "economic",
        "signal_type": "indicator",
        "signal_key": "fred:FEDFUNDS:2025-11",
        "title": "Fed Funds Rate held at 4.25–4.50% (Nov 2025 FOMC)",
        "summary": "FOMC held rates unchanged at Nov meeting. Dot plot signals 50 bps of cuts through 2026 contingent on inflation trajectory. Commercial credit conditions ease slightly.",
        "raw_value": 4.375,
        "raw_unit": "pct",
        "change_pct": 0.0,
        "change_direction": "stable",
        "relevance_score": 0.6,
        "urgency_score": 0.3,
        "affected_trm_types": ["po_creation", "inventory_buffer"],
        "planning_layer": "strategic",
        "expiry_days": 60,
    },
    {
        "day_offset": -7,
        "source_key": "fred",
        "category": "economic",
        "signal_type": "indicator",
        "signal_key": "fred:RETAILSL:2025-10",
        "title": "US Retail Sales: +0.4% MoM (October 2025)",
        "summary": "Retail sales grew 0.4% MoM in October, slightly above 0.3% consensus. Ex-auto +0.3%. Apparel and general merchandise led; restaurants flat. Holiday pre-buy signals emerging.",
        "raw_value": 0.4,
        "raw_unit": "pct_mom",
        "change_pct": 0.4,
        "change_direction": "up",
        "relevance_score": 0.8,
        "urgency_score": 0.5,
        "affected_trm_types": ["forecast_adjustment", "atp_executor"],
        "planning_layer": "tactical",
        "expiry_days": 30,
    },
    # ─── Weather & Climate (Open-Meteo style) ───────────────────────
    {
        "day_offset": -2,
        "source_key": "open_meteo",
        "category": "weather",
        "signal_type": "alert",
        "signal_key": "weather:NW-EU-storm:2025-11-18",
        "title": "Storm system hitting Northwest Europe — shipping delays expected",
        "summary": "Low-pressure system crossing North Sea Nov 18–20. Port of Rotterdam reports 24–48h vessel delays. Hamburg at reduced capacity. Rail freight via Belgium rerouted.",
        "raw_value": None,
        "raw_unit": None,
        "change_direction": "unknown",
        "relevance_score": 0.85,
        "urgency_score": 0.8,
        "affected_trm_types": ["to_execution", "order_tracking", "po_creation"],
        "affected_region_tags": ["NL", "DE", "BE", "GB"],
        "planning_layer": "execution",
        "expiry_days": 7,
    },
    {
        "day_offset": -4,
        "source_key": "open_meteo",
        "category": "weather",
        "signal_type": "forecast",
        "signal_key": "weather:US-NE-cold:2025-11-25",
        "title": "Early cold snap forecast for US Northeast — demand shift expected",
        "summary": "Arctic air mass forecast to reach New England Nov 25–28 with lows 15°F below seasonal norm. Expect demand pull-forward in heating products, apparel winter categories, and comfort food.",
        "raw_value": -15.0,
        "raw_unit": "deg_F_anomaly",
        "change_direction": "down",
        "relevance_score": 0.7,
        "urgency_score": 0.6,
        "affected_trm_types": ["forecast_adjustment", "inventory_buffer"],
        "affected_region_tags": ["US-NE"],
        "planning_layer": "tactical",
        "expiry_days": 14,
    },
    # ─── Energy Markets (EIA style) ─────────────────────────────────
    {
        "day_offset": -6,
        "source_key": "eia",
        "category": "energy",
        "signal_type": "indicator",
        "signal_key": "eia:brent:2025-11-14",
        "title": "Brent crude at $78.40/bbl — up 3% WoW",
        "summary": "Brent crude futures settled at $78.40/bbl Friday Nov 14, up 3% on the week on Middle East supply concerns. Diesel crack spreads widening. Trucking and ocean freight fuel surcharges likely to rise Q1.",
        "raw_value": 78.40,
        "raw_unit": "usd_per_bbl",
        "change_pct": 3.0,
        "change_direction": "up",
        "relevance_score": 0.75,
        "urgency_score": 0.5,
        "affected_trm_types": ["to_execution", "po_creation"],
        "planning_layer": "tactical",
        "expiry_days": 14,
    },
    # ─── Geopolitical (GDELT style) ─────────────────────────────────
    {
        "day_offset": -8,
        "source_key": "gdelt",
        "category": "geopolitical",
        "signal_type": "event",
        "signal_key": "gdelt:red-sea-disruption:2025-11-12",
        "title": "Red Sea shipping disruptions persist — 18% of container traffic rerouted",
        "summary": "Ongoing Red Sea security concerns continue to affect Asia-Europe container shipping. 18% of traffic rerouting via Cape of Good Hope (+12 days transit). Forwarders signal rate increases for Q1 contracts.",
        "raw_value": 18.0,
        "raw_unit": "pct_traffic",
        "change_direction": "up",
        "relevance_score": 0.9,
        "urgency_score": 0.85,
        "affected_trm_types": ["to_execution", "po_creation", "order_tracking"],
        "affected_region_tags": ["ASIA", "EU"],
        "planning_layer": "strategic",
        "expiry_days": 60,
    },
    {
        "day_offset": -10,
        "source_key": "gdelt",
        "category": "geopolitical",
        "signal_type": "event",
        "signal_key": "gdelt:panama-canal:2025-11-10",
        "title": "Panama Canal transit slots normalized after drought-era restrictions",
        "summary": "Panama Canal Authority confirms transit slot availability restored to 36/day from earlier drought-era 24/day cap. Wait times dropped to <2 days. Positive for US East Coast import flows from Asia.",
        "raw_value": 36,
        "raw_unit": "transits_per_day",
        "change_direction": "up",
        "relevance_score": 0.65,
        "urgency_score": 0.3,
        "affected_trm_types": ["to_execution", "po_creation"],
        "affected_region_tags": ["US-E", "ASIA"],
        "planning_layer": "strategic",
        "expiry_days": 90,
    },
    # ─── Commodity Markets ──────────────────────────────────────────
    {
        "day_offset": -9,
        "source_key": "commodities",
        "category": "commodity",
        "signal_type": "indicator",
        "signal_key": "cotton:futures:2025-11-11",
        "title": "Cotton futures at 71.5 c/lb — down 4% on demand concerns",
        "summary": "ICE cotton futures down 4% WoW to 71.5 cents/lb. Chinese apparel manufacturing PMI contracted in October. USDA forecast increased US cotton production for 2025/26. Softness expected to persist through Q1.",
        "raw_value": 71.5,
        "raw_unit": "usd_cents_per_lb",
        "change_pct": -4.0,
        "change_direction": "down",
        "relevance_score": 0.7,
        "urgency_score": 0.4,
        "affected_trm_types": ["po_creation", "forecast_adjustment"],
        "planning_layer": "strategic",
        "expiry_days": 30,
    },
    # ─── Consumer Sentiment ─────────────────────────────────────────
    {
        "day_offset": -11,
        "source_key": "sentiment",
        "category": "sentiment",
        "signal_type": "indicator",
        "signal_key": "umich:consumer-sentiment:2025-11",
        "title": "UMich Consumer Sentiment: 71.2 (preliminary Nov)",
        "summary": "University of Michigan consumer sentiment preliminary Nov reading 71.2, up from 68.9 in Oct. Inflation expectations 1-yr at 2.8%, 5-10yr at 3.0%. Higher-income cohort more optimistic; bottom quartile unchanged.",
        "raw_value": 71.2,
        "raw_unit": "index",
        "change_pct": 3.3,
        "change_direction": "up",
        "relevance_score": 0.55,
        "urgency_score": 0.25,
        "affected_trm_types": ["forecast_adjustment"],
        "planning_layer": "tactical",
        "expiry_days": 30,
    },
    # ─── Trade & Logistics ──────────────────────────────────────────
    {
        "day_offset": -1,
        "source_key": "drewry",
        "category": "trade",
        "signal_type": "indicator",
        "signal_key": "drewry:wci:2025-11-19",
        "title": "Drewry WCI: +2.1% WoW — Asia-Europe lanes leading",
        "summary": "Drewry World Container Index rose 2.1% week-over-week to $3,180/40ft. Shanghai–Rotterdam up 3.8%, Shanghai–Genoa up 4.2% on Red Sea diversion cost pass-through. Transpacific stable.",
        "raw_value": 3180,
        "raw_unit": "usd_per_40ft",
        "change_pct": 2.1,
        "change_direction": "up",
        "relevance_score": 0.75,
        "urgency_score": 0.55,
        "affected_trm_types": ["to_execution", "po_creation"],
        "affected_region_tags": ["ASIA", "EU"],
        "planning_layer": "tactical",
        "expiry_days": 14,
    },
    {
        "day_offset": -12,
        "source_key": "trade",
        "category": "trade",
        "signal_type": "indicator",
        "signal_key": "usla:port-dwell:2025-11-08",
        "title": "US West Coast port dwell time: 3.8 days (stable)",
        "summary": "LA/Long Beach combined container dwell time 3.8 days, unchanged WoW. Terminal gate fluidity normal. Rail pull-rate on target. No systemic bottlenecks heading into Black Friday import peak.",
        "raw_value": 3.8,
        "raw_unit": "days",
        "change_pct": 0.0,
        "change_direction": "stable",
        "relevance_score": 0.6,
        "urgency_score": 0.2,
        "affected_trm_types": ["to_execution", "order_tracking"],
        "affected_region_tags": ["US-W"],
        "planning_layer": "tactical",
        "expiry_days": 14,
    },
]


def _ensure_source(db, tenant_id: int, source_key: str) -> int:
    """Ensure an external_signal_sources row exists for the tenant+source_key. Returns id."""
    import json as _json
    row = db.execute(
        text(
            "SELECT id FROM external_signal_sources "
            "WHERE tenant_id = :tid AND source_key = :sk"
        ),
        {"tid": tenant_id, "sk": source_key},
    ).fetchone()
    if row:
        return row[0]

    # Create a snapshot-mode source stub
    result = db.execute(
        text("""
            INSERT INTO external_signal_sources (
                tenant_id, source_key, source_name, is_active,
                source_params, industry_tags, region_tags, product_tags,
                refresh_cadence, signals_collected, created_at
            ) VALUES (
                :tid, :sk, :name, false,
                CAST(:params AS jsonb), CAST('[]' AS jsonb),
                CAST('[]' AS jsonb), CAST('[]' AS jsonb),
                'snapshot', 0, NOW()
            )
            RETURNING id
        """),
        {
            "tid": tenant_id,
            "sk": source_key,
            "name": f"{source_key} (demo snapshot)",
            "params": _json.dumps({"mode": "snapshot"}),
        },
    )
    return result.scalar_one()


def seed_signals(tenant_id: int, virtual_today: date, dry_run: bool = False) -> dict:
    """Insert snapshot signals for a frozen demo tenant."""
    db = sync_session_factory()
    try:
        # Verify tenant exists and is frozen
        tenant_row = db.execute(
            text("SELECT id, name, time_mode, virtual_today FROM tenants WHERE id = :tid"),
            {"tid": tenant_id},
        ).fetchone()
        if not tenant_row:
            raise ValueError(f"Tenant {tenant_id} not found")

        tid, name, time_mode, vt = tenant_row
        print(f"Tenant: {name} (id={tid})")
        print(f"  time_mode:     {time_mode}")
        print(f"  virtual_today: {vt}")
        if time_mode != "frozen":
            print(f"  WARNING: tenant is not frozen — seeding anyway for preview")
        if vt and vt != virtual_today:
            print(f"  NOTE: using override virtual_today={virtual_today} (tenant has {vt})")

        # Clear any existing signals for this tenant (clean slate)
        if not dry_run:
            deleted = db.execute(
                text("DELETE FROM external_signals WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).rowcount
            print(f"  Deleted {deleted} existing signals")

            # Ensure a source row exists for each unique source_key used in templates
            unique_sources = {tmpl["source_key"] for tmpl in SIGNAL_TEMPLATES}
            source_id_by_key = {}
            for sk in unique_sources:
                source_id_by_key[sk] = _ensure_source(db, tenant_id, sk)
            db.commit()
            print(f"  Ensured {len(source_id_by_key)} source rows")
        else:
            source_id_by_key = {tmpl["source_key"]: 0 for tmpl in SIGNAL_TEMPLATES}

        inserted = 0
        for tmpl in SIGNAL_TEMPLATES:
            signal_date = virtual_today + timedelta(days=tmpl["day_offset"])
            expiry_days = tmpl.get("expiry_days", 30)
            # Expiry: real wall-clock offset from signal_date, so that
            # get_relevant_signals sees it as "not yet expired" from the
            # virtual_today perspective (expires_at > real_utcnow).
            # Since virtual_today is in the past, we set expires_at far into
            # the future to keep the signal active indefinitely for the demo.
            expires_at = datetime.utcnow() + timedelta(days=365 * 10)  # 10 years out

            affected_trm = tmpl.get("affected_trm_types", [])
            affected_region = tmpl.get("affected_region_tags", [])
            affected_product = tmpl.get("affected_product_tags", [])

            embedding_text = (
                f"[{tmpl['category'].upper()}] {tmpl['title']}. "
                f"{tmpl['summary']} "
                f"Date: {signal_date.isoformat()}. "
                f"SC Impact: {', '.join(affected_trm) if affected_trm else 'general'}. "
                f"Planning layer: {tmpl.get('planning_layer', 'tactical')}."
            )

            if dry_run:
                print(f"  [dry-run] {signal_date} {tmpl['category']:12} {tmpl['title'][:70]}")
                inserted += 1
                continue

            import json as _json
            db.execute(
                text("""
                INSERT INTO external_signals (
                    tenant_id, source_id, source_key, category, signal_type, signal_key,
                    title, summary, signal_date,
                    raw_value, raw_unit, change_pct, change_direction,
                    relevance_score, urgency_score, magnitude_score,
                    affected_trm_types, planning_layer,
                    affected_product_tags, affected_region_tags,
                    embedding_text, is_embedded, expires_at, is_active,
                    created_at
                ) VALUES (
                    :tenant_id, :source_id, :source_key, :category, :signal_type, :signal_key,
                    :title, :summary, :signal_date,
                    :raw_value, :raw_unit, :change_pct, :change_direction,
                    :relevance_score, :urgency_score, :magnitude_score,
                    CAST(:affected_trm_types AS jsonb), :planning_layer,
                    CAST(:affected_product_tags AS jsonb), CAST(:affected_region_tags AS jsonb),
                    :embedding_text, false, :expires_at, true,
                    NOW()
                )
                ON CONFLICT (tenant_id, signal_key) DO NOTHING
                """),
                {
                    "tenant_id": tenant_id,
                    "source_id": source_id_by_key[tmpl["source_key"]],
                    "source_key": tmpl["source_key"],
                    "category": tmpl["category"],
                    "signal_type": tmpl["signal_type"],
                    "signal_key": tmpl["signal_key"],
                    "title": tmpl["title"][:500],
                    "summary": tmpl["summary"],
                    "signal_date": signal_date,
                    "raw_value": tmpl.get("raw_value"),
                    "raw_unit": tmpl.get("raw_unit"),
                    "change_pct": tmpl.get("change_pct"),
                    "change_direction": tmpl.get("change_direction"),
                    "relevance_score": tmpl["relevance_score"],
                    "urgency_score": tmpl["urgency_score"],
                    "magnitude_score": tmpl.get("magnitude_score", tmpl["urgency_score"]),
                    "affected_trm_types": _json.dumps(affected_trm),
                    "planning_layer": tmpl.get("planning_layer", "tactical"),
                    "affected_product_tags": _json.dumps(affected_product),
                    "affected_region_tags": _json.dumps(affected_region),
                    "embedding_text": embedding_text,
                    "expires_at": expires_at,
                },
            )
            inserted += 1

        if not dry_run:
            db.commit()
            print(f"  Inserted {inserted} signals")

        return {"tenant_id": tenant_id, "inserted": inserted, "dry_run": dry_run}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Seed frozen demo tenant external signal snapshot")
    parser.add_argument("--tenant-id", type=int, required=True, help="Tenant ID (e.g., 20 for SAP Demo)")
    parser.add_argument("--virtual-today", type=str, default=None,
                        help="Override virtual_today (ISO date). Default: read from tenant.virtual_today")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing")
    args = parser.parse_args()

    # Resolve virtual_today
    if args.virtual_today:
        vtoday = date.fromisoformat(args.virtual_today)
    else:
        db = sync_session_factory()
        try:
            row = db.execute(
                text("SELECT virtual_today FROM tenants WHERE id = :tid"),
                {"tid": args.tenant_id},
            ).fetchone()
            if not row or not row[0]:
                print(f"ERROR: Tenant {args.tenant_id} has no virtual_today set. Pass --virtual-today or set tenant.")
                sys.exit(1)
            vtoday = row[0]
        finally:
            db.close()

    result = seed_signals(args.tenant_id, vtoday, dry_run=args.dry_run)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()

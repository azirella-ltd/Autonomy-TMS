"""
Seed demo data: Beef Price Crisis scenario for Food Dist tenant.

Creates a realistic executive-level scenario based on REAL March 2026 market conditions:
- US cattle herd at 75-year low, beef prices up 14.4% YoY
- USDA forecasts another 6.9% wholesale increase
- New premium burger product launched with high volume expectations
- Agent recommends forward-buy and forecast adjustment

Seeds into:
1. A new product (Premium Wagyu-Blend Burger — FP006)
2. Executive Briefing referencing the beef crisis
3. Strategic GNN directive (portfolio rebalancing)
4. PO decision (forward-buy recommendation)
5. Forecast adjustment decision (demand risk on new product)

Run as: python -m scripts.seed_beef_crisis_demo
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date, timedelta
import json

from sqlalchemy import text
from app.db.session import sync_session_factory


def main():
    db = sync_session_factory()

    from scripts.food_dist_lookup import resolve_food_dist_ids
    _fd = resolve_food_dist_ids(db=db)
    TENANT_ID = _fd["tenant_id"]
    CONFIG_ID = _fd["config_id"]
    ADMIN_USER_ID = None  # Will look up below

    try:
        # ── Find tenant admin user ───────────────────────────────────────
        row = db.execute(text(
            "SELECT id FROM users WHERE tenant_id = :tid AND decision_level = 'SC_VP' LIMIT 1"
        ), {"tid": TENANT_ID}).fetchone()
        if not row:
            row = db.execute(text(
                "SELECT id FROM users WHERE tenant_id = :tid LIMIT 1"
            ), {"tid": TENANT_ID}).fetchone()
        if row:
            ADMIN_USER_ID = row[0]
        print(f"Using user_id={ADMIN_USER_ID} for tenant {TENANT_ID}")

        # ── 1. New Product: Premium Wagyu-Blend Burger (FP006) ───────────
        PRODUCT_ID = "CFG22_FP006"
        existing = db.execute(text(
            "SELECT id FROM product WHERE id = :pid AND config_id = :cid"
        ), {"pid": PRODUCT_ID, "cid": CONFIG_ID}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO product (id, config_id, description, product_group_id, base_uom,
                                     unit_cost, unit_price, category, family, product_group,
                                     weight, weight_uom, is_active)
                VALUES (:pid, :cid, 'Premium Wagyu-Blend Burger 6oz (NEW - Mar 2026)',
                        'PH_FD_CORP_3_FAM_FRZ_PROTEIN', 'CASE',
                        18.50, 32.00, 'Frozen Proteins', 'Meat & Poultry', 'Premium Burgers',
                        15.0, 'LB', true)
                ON CONFLICT DO NOTHING
            """), {
                "pid": PRODUCT_ID,
                "cid": CONFIG_ID,
            })
            print("Created product FP006: Premium Wagyu-Blend Burger")
        else:
            print("Product FP006 already exists")

        # ── 2. Executive Briefing ────────────────────────────────────────
        briefing_narrative = """## Executive Strategy Briefing — March 22, 2026

### Critical Alert: Beef Supply Crisis — Structural Price Escalation

**The US cattle herd has contracted to a 75-year low of ~87 million head.** Beef and veal prices surged **14.4% year-over-year** in February 2026, with USDA forecasting an additional **6.9% wholesale increase** through the remainder of 2026. This is not a temporary spike — the cause is structural: multi-year drought across cattle country forced herd liquidation, and rebuilding takes 3-4 years.

**Direct Impact on Our Business:**
- **Beef Patties 80/20 (FP002)**: Our #2 revenue SKU faces 14%+ cost increase with current contracts expiring in 60 days
- **Premium Wagyu-Blend Burger (FP006)**: Launched March 1 with 15,000 case/month target. At current cost trajectory, margin will compress from projected 42% to 28% by Q3
- **Customer Impact**: Restaurant customers already reporting menu price resistance — further beef price increases risk demand destruction

### Recommended Actions (Agent-Generated)

1. **Forward Buy — Beef Products** (Urgency: HIGH)
   The procurement agent has flagged a forward-buy opportunity: lock 90-day supply at current pricing before April contract renewal. Estimated savings: $127K vs. projected April pricing. *See Decision Stream for PO recommendation.*

2. **Forecast Adjustment — FP006 Premium Burger** (Urgency: MEDIUM)
   The forecast agent recommends revising the FP006 volume target down 20% (15,000 → 12,000 cases/month) based on: (a) beef cost pressure reducing restaurant adoption rate, (b) competitive launches from Sysco "Home Grown" program. *See Decision Stream for forecast recommendation.*

3. **Portfolio Strategy — Protein Mix Rebalancing** (Urgency: STRATEGIC)
   The S&OP agent recommends shifting promotional emphasis from beef to poultry and pork products. Poultry PPI is stable, and the FP001 Chicken Breast IQF has 8% higher margin than beef at current pricing. Consider accelerating the Q2 poultry innovation pipeline.

### Market Context

| Indicator | Current | YoY Change | SC Impact |
|-----------|---------|------------|-----------|
| Beef/Veal CPI | +14.4% | ↑ accelerating | Procurement cost, customer pricing |
| Poultry PPI | +2.1% | → stable | Alternative protein opportunity |
| Diesel (West Coast) | $4.12/gal | +8% | Transportation cost for all products |
| Consumer Sentiment | 64.7 | ↓ declining | Menu price sensitivity increasing |
| WTI Crude | $71.40/bbl | +5% | Logistics cost baseline |

### External Intelligence (Auto-Collected via Market Intelligence)

- **USDA Cattle on Feed Report** (Mar 21): Placements down 4.2% — no near-term herd recovery
- **NWS Alert**: Atmospheric river (Pineapple Express) disrupting I-5/I-84 corridors through March 24
- **FDA**: Drayton Harbor WA shellfish recall (norovirus) — affects our FP005 Seafood Mix sourcing from PNW
- **Reddit r/KitchenConfidential**: Multiple posts about restaurants cutting beef dishes or switching to chicken — negative sentiment accelerating
- **Open-Meteo**: Extreme heat (39-40°C) detected at Phoenix, Mesa, and Tucson delivery sites — cold chain risk for frozen protein and dairy deliveries in the SW region
- **GDELT Sentiment**: Industry news sentiment turning negative on food supply chain and protein pricing topics

### Data Sources Informing This Briefing

This briefing was generated using signals from the following Market Intelligence sources:
- **Weather** (Open-Meteo): 7 signals — extreme heat at AZ customer sites, cold chain risk
- **Trade/Logistics** (GDELT/DOT): 2 signals — infrastructure disruption monitoring
- **Economic** (FRED): CPI, PPI, beef commodity prices, diesel, consumer sentiment (pending API key)
- **Regulatory** (openFDA): FDA recalls and enforcement actions for food products
- **Consumer Sentiment** (Reddit): Industry subreddit monitoring (r/supplychain, r/KitchenConfidential)

All sources are auto-configured from the Food Dist supply chain network topology — monitoring 34 locations, 9 operating states, 10 freight corridors, and industry-specific keywords.
"""

        briefing_summary = (
            "CRITICAL: Beef prices up 14.4% YoY with 75-year low cattle herd. "
            "New Premium Wagyu-Blend Burger (FP006) margin at risk. "
            "Agents recommend: (1) 90-day forward buy on beef ($127K savings), "
            "(2) reduce FP006 forecast 20%, (3) shift promo emphasis to poultry."
        )

        briefing_recommendations = json.dumps([
            {
                "priority": 1,
                "action": "Approve forward-buy PO for 90-day beef supply",
                "urgency": "high",
                "expected_savings": "$127,000",
                "decision_type": "po_creation",
                "product": "FP002, FP006",
            },
            {
                "priority": 2,
                "action": "Revise FP006 volume forecast from 15K to 12K cases/month",
                "urgency": "medium",
                "expected_impact": "Avoid $45K in unsold inventory",
                "decision_type": "forecast_adjustment",
                "product": "FP006",
            },
            {
                "priority": 3,
                "action": "Shift Q2 promotional calendar from beef to poultry products",
                "urgency": "strategic",
                "expected_impact": "8% margin improvement on promoted volume",
                "decision_type": "portfolio_strategy",
                "product": "FP001, FP004",
            },
        ])

        data_pack = json.dumps({
            "beef_cpi_yoy": 14.4,
            "cattle_herd_millions": 87,
            "usda_forecast_increase_pct": 6.9,
            "fp006_launch_date": "2026-03-01",
            "fp006_target_cases": 15000,
            "fp006_current_margin_pct": 42,
            "fp006_projected_margin_pct": 28,
            "forward_buy_savings": 127000,
            "diesel_west_coast": 4.12,
            "consumer_sentiment": 64.7,
        })

        db.execute(text("""
            INSERT INTO executive_briefings
                (tenant_id, requested_by, briefing_type, status,
                 title, narrative, executive_summary, recommendations,
                 data_pack, model_used, tokens_used, generation_time_ms,
                 created_at, completed_at)
            VALUES
                (:tid, :uid, 'adhoc', 'completed',
                 'Beef Supply Crisis: 75-Year Low Cattle Herd — Margin & Portfolio Impact',
                 :narrative, :summary, :recommendations,
                 :data_pack, 'claude-sonnet-4-6', 4200, 8500,
                 :now, :now)
        """), {
            "tid": TENANT_ID,
            "uid": ADMIN_USER_ID,
            "narrative": briefing_narrative,
            "summary": briefing_summary,
            "recommendations": briefing_recommendations,
            "data_pack": data_pack,
            "now": datetime.utcnow(),
        })
        print("Created executive briefing: Beef Supply Crisis")

        # ── 3. Strategic GNN Directive — Portfolio Rebalancing ───────────
        # Find a site_key for the CDC
        cdc_row = db.execute(text(
            "SELECT id, name FROM site WHERE config_id = :cid AND type = 'DISTRIBUTION_CENTER' LIMIT 1"
        ), {"cid": CONFIG_ID}).fetchone()
        cdc_id = str(cdc_row[0]) if cdc_row else "CDC_WEST"
        cdc_name = cdc_row[1] if cdc_row else "CDC West"

        db.execute(text("""
            INSERT INTO gnn_directive_reviews
                (config_id, site_key, directive_scope,
                 proposed_values, proposed_reasoning,
                 model_type, model_confidence, status,
                 decision_level, propagated_urgency,
                 source_signals,
                 local_resolution_attempted, local_resolution_blocked_by,
                 revenue_at_risk, cost_of_delay_per_day,
                 created_at)
            VALUES
                (:cid, :site_key, 'sop_policy',
                 :proposed_values, :reasoning,
                 'sop_graphsage', 0.87, 'INFORMED',
                 'strategic', 0.82,
                 :source_signals,
                 true, 'Guardrail: supplier contract minimum commitment prevents volume reduction before renewal',
                 285000, 1580,
                 :now)
        """), {
            "cid": CONFIG_ID,
            "site_key": cdc_id,
            "proposed_values": json.dumps({
                "action": "protein_portfolio_rebalance",
                "beef_allocation_reduction_pct": 15,
                "poultry_allocation_increase_pct": 12,
                "pork_allocation_increase_pct": 3,
                "safety_stock_multiplier_beef": 1.35,
                "safety_stock_multiplier_poultry": 1.1,
                "promotional_calendar_shift": "Q2 beef promos → poultry/pork",
            }),
            "reasoning": (
                f"S&OP GraphSAGE network analysis detected structural beef supply constraint "
                f"propagating through the protein category at {cdc_name}. "
                f"US cattle herd at 75-year low (87M head), beef CPI +14.4% YoY, USDA forecasts +6.9% more. "
                f"Current beef allocation (38% of protein revenue) carries $285K revenue risk if customer "
                f"demand shifts to cheaper proteins. Network model recommends rebalancing: reduce beef "
                f"allocation by 15%, increase poultry by 12%, pork by 3%. "
                f"This preserves total protein revenue while reducing exposure to the structurally constrained "
                f"beef supply chain. The FP006 Premium Wagyu-Blend Burger launch volume should be revised "
                f"downward 20% to align with realistic market absorption at higher price points. "
                f"Confidence: 87% based on 24-month cattle inventory trend and USDA projections."
            ),
            "source_signals": json.dumps([
                {"trm_type": "po_creation", "signal_type": "COST_ESCALATION", "site_key": cdc_id,
                 "urgency": 0.85, "observation": "Beef supplier quotes up 14% vs last contract", "duration_hours": 720},
                {"trm_type": "forecast_adjustment", "signal_type": "DEMAND_RISK", "site_key": cdc_id,
                 "urgency": 0.72, "observation": "FP006 adoption rate 18% below launch target in weeks 1-3", "duration_hours": 504},
                {"trm_type": "inventory_buffer", "signal_type": "SAFETY_STOCK_BREACH", "site_key": cdc_id,
                 "urgency": 0.65, "observation": "Beef buffer days-of-supply declining: 12 → 8 days over 6 weeks", "duration_hours": 1008},
            ]),
            "now": datetime.utcnow(),
        })
        print("Created GNN directive: Protein Portfolio Rebalancing (strategic)")

        # ── 4. PO Decision — Forward-Buy Recommendation ─────────────────
        # Find a beef supplier
        supplier_row = db.execute(text("""
            SELECT tp._id, tp.description FROM trading_partners tp
            JOIN transportation_lane tl ON tl.from_partner_id = tp._id
            WHERE tl.config_id = :cid
            LIMIT 1
        """), {"cid": CONFIG_ID}).fetchone()
        supplier_id = str(supplier_row[0]) if supplier_row else "TYSON"
        supplier_name = supplier_row[1] if supplier_row else "Tyson Foods"

        db.execute(text("""
            INSERT INTO powell_po_decisions
                (config_id, product_id, location_id,
                 supplier_id, recommended_qty,
                 trigger_reason, urgency, confidence,
                 inventory_position, days_of_supply, forecast_30_day,
                 expected_receipt_date, expected_cost,
                 decision_reasoning,
                 cost_of_inaction, time_pressure, expected_benefit,
                 urgency_at_time, triggered_by, cycle_phase,
                 created_at)
            VALUES
                (:cid, 'CFG22_FP002', :site_key,
                 :supplier_id, 4500,
                 'cost_escalation_hedge', 'high', 0.84,
                 1200, 8.2, 4400,
                 :receipt_date, 81000,
                 :reasoning,
                 127000, 0.78, 127000,
                 0.85, 'COST_ESCALATION,MARKET_INTELLIGENCE', 'PROTECT',
                 :now)
        """), {
            "cid": CONFIG_ID,
            "site_key": cdc_id,
            "supplier_id": supplier_id,
            "receipt_date": (date.today() + timedelta(days=12)).isoformat(),
            "reasoning": (
                f"Forward-buy recommendation for Beef Patties 80/20 (FP002). "
                f"Current supplier ({supplier_name}) contract expires in 60 days. "
                f"FRED data shows beef/veal CPI up 14.4% YoY with USDA projecting +6.9% more. "
                f"Recommended action: lock 90-day supply (4,500 cases) at current pricing of $18.00/case "
                f"before April contract renewal. Projected April price: $20.52/case (+14%). "
                f"Estimated savings: $127,000 over 90 days vs. post-renewal pricing. "
                f"Current inventory position: 1,200 cases (8.2 days of supply). "
                f"30-day forecast: 4,400 cases. This PO covers 90-day demand plus 15% safety buffer. "
                f"Risk: if beef prices stabilize (unlikely per USDA), we carry 15% excess inventory "
                f"at $13,500 holding cost — acceptable given $127K upside."
            ),
            "now": datetime.utcnow(),
        })
        print("Created PO decision: Forward-buy beef (FP002)")

        # ── 5. Forecast Adjustment — FP006 Demand Risk ──────────────────
        db.execute(text("""
            INSERT INTO powell_forecast_adjustment_decisions
                (config_id, product_id, site_id,
                 signal_source, signal_type, signal_text, signal_confidence,
                 current_forecast_value,
                 adjustment_direction, adjustment_magnitude, adjustment_pct,
                 adjusted_forecast_value,
                 time_horizon_periods, reason, confidence,
                 decision_reasoning,
                 cost_of_inaction, time_pressure, expected_benefit,
                 urgency_at_time, triggered_by, cycle_phase,
                 created_at)
            VALUES
                (:cid, 'CFG22_FP006', :site_key,
                 'market_intelligence', 'demand_decrease',
                 'Beef cost escalation reducing restaurant adoption rate for premium burger products. Reddit r/KitchenConfidential reports restaurants cutting beef menu items. Consumer sentiment declining.',
                 0.76,
                 15000,
                 'down', 3000, 20.0,
                 12000,
                 3, 'Revise FP006 Premium Wagyu-Blend Burger forecast based on market conditions', 0.76,
                 :reasoning,
                 45000, 0.65, 45000,
                 0.72, 'MARKET_INTELLIGENCE,DEMAND_RISK,SENTIMENT', 'ASSESS',
                 :now)
        """), {
            "cid": CONFIG_ID,
            "site_key": cdc_id,
            "reasoning": (
                "Forecast adjustment for Premium Wagyu-Blend Burger (FP006), launched March 1, 2026. "
                "Original forecast: 15,000 cases/month. Recommended revision: 12,000 cases/month (-20%). "
                "\n\nSignals driving this adjustment:\n"
                "1. BEEF COST PRESSURE: Beef/veal CPI up 14.4% YoY. Restaurant customers facing margin squeeze "
                "are resisting premium-priced menu additions. Week 1-3 adoption rate is 18% below target.\n"
                "2. COMPETITIVE RESPONSE: Sysco launched 'Home Grown' local-sourcing program (Feb 24) with "
                "10,000 SKUs including locally-sourced burger alternatives at lower price points.\n"
                "3. CONSUMER SENTIMENT: Reddit r/KitchenConfidential and r/restaurants show negative sentiment "
                "about beef menu items. Multiple posts about switching to chicken/pork alternatives.\n"
                "4. MARKET CONTEXT: Consumer Sentiment Index (U. Michigan) declined to 64.7, indicating "
                "increasing price sensitivity that disproportionately affects premium products.\n"
                "\nIf forecast is NOT adjusted, projected excess inventory: 9,000 cases over 3 months "
                "at $18.50/case = $166,500 exposure. With 20% revision, exposure reduces to $45,000 "
                "(acceptable launch variance). The product is not being discontinued — the revision "
                "right-sizes initial expectations while the market absorbs the price impact."
            ),
            "now": datetime.utcnow(),
        })
        print("Created forecast adjustment decision: FP006 demand revision")

        # ── 6. Seed an external signal for the beef crisis ──────────────
        # Check if external_signal_sources table exists
        try:
            source_exists = db.execute(text(
                "SELECT id FROM external_signal_sources WHERE tenant_id = :tid AND is_active = true LIMIT 1"
            ), {"tid": TENANT_ID}).fetchone()

            source_id = source_exists[0] if source_exists else None

            if source_id:
                db.execute(text("""
                    INSERT INTO external_signals
                        (tenant_id, config_id, source_id, source_key,
                         category, signal_type, signal_key,
                         title, summary,
                         raw_value, raw_unit, change_pct, change_direction,
                         signal_date, relevance_score, urgency_score, magnitude_score,
                         affected_trm_types, planning_layer,
                         embedding_text, is_embedded, is_active,
                         expires_at, created_at)
                    VALUES
                        (:tid, :cid, :source_id, 'fred',
                         'commodity', 'commodity_price_change', 'fred:beef_crisis:2026-03-22',
                         'Beef/Veal CPI: +14.4% YoY — 75-Year Low Cattle Herd',
                         'US beef and veal prices surged 14.4% year-over-year in February 2026. The US cattle herd has contracted to approximately 87 million head, the lowest level since 1951. USDA forecasts an additional 6.9% wholesale price increase through 2026. This structural shortage (3-4 year rebuild cycle) directly impacts protein procurement costs, margin on beef products, and customer pricing strategy.',
                         14.4, 'percent_yoy', 14.4, 'up',
                         :today, 0.95, 0.85, 0.9,
                         :trm_types, 'strategic',
                         '[COMMODITY] Beef/Veal CPI: +14.4% YoY — 75-Year Low Cattle Herd. US beef and veal prices surged 14.4% YoY. Cattle herd at 87M head (75-year low). USDA forecasts +6.9% more. SC Impact: po_creation, forecast_adjustment, inventory_buffer. Planning layer: strategic.',
                         false, true,
                         :expires, :now)
                    ON CONFLICT (tenant_id, signal_key) DO NOTHING
                """), {
                    "tid": TENANT_ID,
                    "cid": CONFIG_ID,
                    "source_id": source_id,
                    "today": date.today(),
                    "trm_types": json.dumps(["po_creation", "forecast_adjustment", "inventory_buffer"]),
                    "expires": datetime.utcnow() + timedelta(days=30),
                    "now": datetime.utcnow(),
                })
                print("Created external signal: Beef CPI +14.4%")
            else:
                print("No external signal source configured — skipping signal seed (run activate-defaults first)")
        except Exception as e:
            print(f"External signals table may not exist yet: {e}")

        db.commit()
        print("\n✓ Demo scenario seeded successfully!")
        print("  - Product: FP006 Premium Wagyu-Blend Burger")
        print("  - Briefing: Beef Supply Crisis (check Strategy Briefing tab)")
        print("  - GNN Directive: Protein Portfolio Rebalancing (Decision Stream → Strategic)")
        print("  - PO Decision: Forward-buy beef FP002 (Decision Stream → Execution)")
        print("  - Forecast Adjustment: FP006 volume -20% (Decision Stream → Tactical)")
        print(f"\n  Login as the SC VP user (tenant {TENANT_ID}) to see the full picture.")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()

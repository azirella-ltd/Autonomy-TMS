#!/usr/bin/env python3
"""
Seed Collaboration Scenarios for Food Dist

Creates 5 collaboration scenario records demonstrating the Agentic
Authorization Protocol (AAP) for cross-functional decision-making.

Scenarios:
  1. S&OP:      Summer Beverage Surge (Policy Envelope adjustment)
  2. Execution:  Metro Grocery Rush Order (multi-party order promising) ★
  3. Execution:  Tyson Supplier Delay (PO rerouting)
  4. Execution:  School Lunch Demand Spike (safety stock exception)
  5. Execution:  Frozen Zone Capacity (inventory rebalancing)

Usage:
    docker compose exec backend python scripts/seed_collaboration_scenarios.py

Idempotent: deletes existing collaboration_scenarios for the Food Dist
config, then inserts fresh records.
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_engine():
    sync_url = str(settings.DATABASE_URL).replace('+asyncpg', '').replace('asyncpg', 'psycopg2')
    if '+psycopg2' not in sync_url and 'psycopg2' not in sync_url:
        sync_url = sync_url.replace('postgresql://', 'postgresql+psycopg2://')
    return create_engine(sync_url)


def lookup_food_dist(conn):
    """Find Food Dist tenant, config, and user IDs."""
    row = conn.execute(text(
        "SELECT id FROM customers WHERE name ILIKE '%food dist%' OR name ILIKE '%dot foods%' LIMIT 1"
    )).fetchone()
    if not row:
        log.error("Food Dist tenant not found. Run seed_food_dist_demo.py first.")
        sys.exit(1)
    customer_id = row[0]

    row = conn.execute(text(
        "SELECT id FROM supply_chain_configs WHERE customer_id = :gid ORDER BY id LIMIT 1"
    ), {"gid": customer_id}).fetchone()
    if not row:
        log.error("No supply chain config found for Food Dist tenant.")
        sys.exit(1)
    config_id = row[0]

    # Lookup demo user IDs by email
    users = {}
    for email, key in [
        ("sc_vp@distdemo.com", "sc_vp"),
        ("sopdir@distdemo.com", "sop_director"),
        ("mpsmanager@distdemo.com", "mps_manager"),
        ("atp@distdemo.com", "atp_analyst"),
        ("po@distdemo.com", "po_analyst"),
        ("rebalancing@distdemo.com", "rebalancing_analyst"),
    ]:
        row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).fetchone()
        users[key] = row[0] if row else None

    log.info(f"  Tenant ID: {customer_id}, Config ID: {config_id}")
    log.info(f"  Users found: {sum(1 for v in users.values() if v)}/{len(users)}")
    return customer_id, config_id, users


def ensure_table(conn):
    """Create collaboration_scenarios table if it doesn't exist."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS collaboration_scenarios (
            id SERIAL PRIMARY KEY,
            config_id INTEGER NOT NULL REFERENCES supply_chain_configs(id) ON DELETE CASCADE,
            customer_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            scenario_code VARCHAR(50) NOT NULL UNIQUE,
            title VARCHAR(200) NOT NULL,
            description TEXT NOT NULL,
            level VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'open',
            priority VARCHAR(20) DEFAULT 'high',
            originating_agent VARCHAR(100) NOT NULL,
            target_agents JSONB NOT NULL,
            trigger_event JSONB NOT NULL,
            authorization_requests JSONB NOT NULL,
            balanced_scorecard JSONB NOT NULL,
            net_benefit FLOAT,
            resolution JSONB,
            timeline JSONB,
            assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
            escalated_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_collab_scenario_group
            ON collaboration_scenarios(customer_id, level);
    """))
    conn.commit()
    log.info("  Table collaboration_scenarios ensured.")


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------

# Baseline date for all scenarios
BASE_DATE = datetime(2026, 3, 2)


def scenario_1_sop_beverage_surge(customer_id, config_id, users):
    """S&OP: Summer Beverage Surge — Policy Envelope Adjustment"""
    return {
        "config_id": config_id,
        "customer_id": customer_id,
        "scenario_code": "COLLAB-SOP-001",
        "title": "Summer Beverage Surge: Policy Envelope Adjustment for Q2 2026",
        "description": (
            "The Demand Agent detects a 35% demand increase signal for Beverages (BV001-BV005) "
            "heading into Q2 2026, driven by summer seasonal patterns and a new Quick Serve Foods "
            "contract. Current safety stock parameters (2.5 WOS) will be insufficient. Requires "
            "cross-functional S&OP alignment between Demand, Supply, Finance, and Inventory agents "
            "to adjust the Policy Envelope before the surge hits."
        ),
        "level": "sop",
        "status": "resolved",
        "priority": "high",
        "originating_agent": "demand_agent",
        "target_agents": json.dumps(["sop_agent", "supply_agent", "finance_agent", "inventory_agent"]),
        "trigger_event": json.dumps({
            "type": "demand_signal_anomaly",
            "detected_at": (BASE_DATE - timedelta(days=1)).isoformat() + "Z",
            "products": ["BV001", "BV002", "BV003", "BV004", "BV005"],
            "current_weekly_demand": {"BV001": 220, "BV002": 150, "BV003": 180, "BV004": 200, "BV005": 60},
            "projected_weekly_demand": {"BV001": 297, "BV002": 202, "BV003": 243, "BV004": 270, "BV005": 81},
            "demand_increase_pct": 35,
            "period": "2026-Q2 (Apr-Jun)",
            "driver": "Seasonal pattern + new contract with Quick Serve Foods LLC (QUICKSERV)"
        }),
        "authorization_requests": json.dumps([
            {
                "id": "AR-SOP-001-A",
                "requesting_agent": "demand_agent",
                "target_agent": "sop_agent",
                "proposed_action": {
                    "type": "adjust_policy_envelope",
                    "parameter": "safety_stock_wos",
                    "category": "BEV",
                    "current_value": 2.5,
                    "proposed_value": 3.5,
                    "effective_date": "2026-04-01",
                    "duration": "Q2 2026 (Apr-Jun)"
                },
                "justification": "Current 2.5 WOS insufficient for 35% demand surge. 3.5 WOS maintains 98% service level during ramp.",
                "decision": "AUTHORIZE",
                "decision_reason": "Demand signal validated against 3-year seasonal pattern. Confidence: 92%."
            },
            {
                "id": "AR-SOP-001-B",
                "requesting_agent": "sop_agent",
                "target_agent": "finance_agent",
                "proposed_action": {
                    "type": "working_capital_increase",
                    "amount": 127000,
                    "category": "BEV",
                    "duration_weeks": 13,
                    "weekly_holding_cost": 1230
                },
                "justification": "Incremental inventory investment to support 35% beverage volume growth. GMROI remains above 3.0x.",
                "decision": "AUTHORIZE",
                "decision_reason": "ROI positive: $285K incremental revenue vs $127K working capital. GMROI 3.0x (above 2.5x floor)."
            },
            {
                "id": "AR-SOP-001-C",
                "requesting_agent": "sop_agent",
                "target_agent": "supply_agent",
                "proposed_action": {
                    "type": "secure_forward_commitments",
                    "suppliers": [
                        {"code": "TROP", "name": "Tropicana Brands Group", "products": ["BV001", "BV003"], "volume_increase_pct": 35},
                        {"code": "COCACOLA", "name": "Coca-Cola Foodservice", "products": ["BV002", "BV004", "BV005"], "volume_increase_pct": 35}
                    ],
                    "commitment_period": "2026-Q2"
                },
                "justification": "Lock in supplier capacity before seasonal competition from other distributors.",
                "decision": "AUTHORIZE",
                "decision_reason": "Both suppliers confirmed capacity. TROP offers 2% volume discount at commitment level. COCACOLA standard pricing."
            },
            {
                "id": "AR-SOP-001-D",
                "requesting_agent": "sop_agent",
                "target_agent": "inventory_agent",
                "proposed_action": {
                    "type": "expand_capacity_allocation",
                    "zone": "refrigerated",
                    "current_allocation_pct": 15,
                    "proposed_allocation_pct": 22,
                    "products_affected": ["BV001", "BV002", "BV003", "BV004", "BV005"],
                    "duration": "2026-Q2"
                },
                "justification": "Refrigerated zone currently at 68% utilization. Expanding beverage allocation from 15% to 22% keeps zone at 85% (within operating range).",
                "decision": "AUTHORIZE",
                "decision_reason": "Capacity available. Refrigerated zone projected 85% utilization (below 90% threshold). No displacement of dairy products required."
            }
        ]),
        "balanced_scorecard": json.dumps({
            "customer": {
                "otif_beverages": {"current": 0.95, "projected": 0.97, "status": "GREEN"},
                "fill_rate_strategic": {"current": 0.98, "projected": 0.99, "status": "GREEN"},
                "new_contract_risk": {"current": "HIGH", "projected": "NONE", "status": "GREEN"}
            },
            "financial": {
                "incremental_working_capital": {"current": 0, "projected": 127000, "status": "AMBER"},
                "incremental_revenue": {"current": 0, "projected": 285000, "status": "GREEN"},
                "gmroi_beverages": {"current": 3.2, "projected": 3.0, "status": "GREEN"}
            },
            "operational": {
                "refrigerated_utilization": {"current": 0.68, "projected": 0.85, "status": "AMBER"},
                "safety_stock_wos": {"current": 2.5, "projected": 3.5, "status": "GREEN"},
                "supplier_concentration": {"current": "low", "projected": "low", "status": "GREEN"}
            },
            "strategic": {
                "revenue_at_risk": {"current": 285000, "projected": 0, "status": "GREEN"},
                "customer_retention": {"current": "MEDIUM", "projected": "HIGH", "status": "GREEN"},
                "market_share_growth": {"current": "flat", "projected": "+2.1%", "status": "GREEN"}
            }
        }),
        "net_benefit": 158000.0,
        "resolution": json.dumps({
            "decision": "authorize_all",
            "actions_taken": [
                "Policy Envelope safety stock WOS updated 2.5 → 3.5 for BEV category effective Apr 1",
                "Working capital increase of $127K approved by Finance",
                "Forward commitments secured: TROP +35%, COCACOLA +35% for Q2",
                "Refrigerated zone allocation expanded 15% → 22% for beverages"
            ],
            "resolved_by": "sop_agent",
            "resolved_at": BASE_DATE.isoformat() + "Z",
            "human_review": "S&OP Director approved. SC VP signed off on working capital."
        }),
        "timeline": json.dumps([
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=16)).isoformat() + "Z", "agent": "demand_agent", "action": "detect", "detail": "35% demand increase signal detected for BEV category (Q2 seasonal + QUICKSERV contract)."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=15, minutes=50)).isoformat() + "Z", "agent": "demand_agent", "action": "evaluate", "detail": "Evaluated 3 options: (1) accept stockout risk, (2) partial adjustment, (3) full Policy Envelope change. Option 3 selected: net benefit +$158K."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=15, minutes=45)).isoformat() + "Z", "agent": "demand_agent", "action": "request_auth", "detail": "Sent AR-SOP-001-A to sop_agent: adjust safety stock WOS 2.5 → 3.5 for BEV category."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=15)).isoformat() + "Z", "agent": "sop_agent", "action": "authorize", "detail": "AR-SOP-001-A AUTHORIZED. Forwarding downstream requests to finance, supply, inventory agents."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=14, minutes=30)).isoformat() + "Z", "agent": "sop_agent", "action": "request_auth", "detail": "Sent AR-SOP-001-B (working capital), AR-SOP-001-C (supplier commitments), AR-SOP-001-D (capacity allocation)."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=12)).isoformat() + "Z", "agent": "supply_agent", "action": "authorize", "detail": "AR-SOP-001-C AUTHORIZED. TROP and COCACOLA confirmed capacity for Q2 +35%."},
            {"timestamp": (BASE_DATE - timedelta(days=1, hours=10)).isoformat() + "Z", "agent": "inventory_agent", "action": "authorize", "detail": "AR-SOP-001-D AUTHORIZED. Refrigerated zone allocation expanded. Projected 85% utilization."},
            {"timestamp": (BASE_DATE - timedelta(hours=8)).isoformat() + "Z", "agent": "finance_agent", "action": "authorize", "detail": "AR-SOP-001-B AUTHORIZED. $127K working capital approved. GMROI 3.0x above floor."},
            {"timestamp": BASE_DATE.isoformat() + "Z", "agent": "sop_agent", "action": "resolve", "detail": "All 4 authorizations received. Policy Envelope updated for Q2 2026 beverage surge."}
        ]),
        "assigned_to": users.get("sop_director"),
        "escalated_to": users.get("sc_vp"),
    }


def scenario_2_exec_metro_grocery_rush(customer_id, config_id, users):
    """Execution: Metro Grocery Rush Order — Multi-Party Authorization (KEY SCENARIO)"""
    return {
        "config_id": config_id,
        "customer_id": customer_id,
        "scenario_code": "COLLAB-EXEC-001",
        "title": "Metro Grocery Rush Order: Multi-Party Authorization for Strategic Customer",
        "description": (
            "Metro Grocery Chain (METROGRO, Los Angeles, Tier 1 strategic customer, $624K annual value) "
            "places an urgent order for 500 cases Chicken Breast IQF (FP001) and 300 cases Mozzarella "
            "Block (RD002), delivery required by March 5 (3 days). Current on-hand can fulfill only 350 "
            "FP001 and 200 RD002. The SO/ATP Agent orchestrates three concurrent authorization requests: "
            "(1) outbound LTL expedite to LA, (2) inbound supply expedite from Tyson and Land O'Lakes, "
            "(3) reallocation from lower-priority QUICKSERV and FAMREST orders."
        ),
        "level": "execution",
        "status": "resolved",
        "priority": "critical",
        "originating_agent": "so_atp_agent",
        "target_agents": json.dumps(["logistics_agent", "supply_agent", "allocation_agent"]),
        "trigger_event": json.dumps({
            "type": "strategic_customer_order",
            "order_id": "ORD-2026-8834",
            "customer_code": "METROGRO",
            "customer_name": "Metro Grocery Chain",
            "customer_segment": "Retail Grocery",
            "customer_priority": 1,
            "site": "FOODDIST_DC",
            "order_date": (BASE_DATE + timedelta(hours=9, minutes=15)).isoformat() + "Z",
            "required_delivery_date": "2026-03-05",
            "line_items": [
                {"product_id": "FP001", "product_name": "Chicken Breast IQF", "requested_qty": 500, "unit_price": 34.99, "line_value": 17495.00},
                {"product_id": "RD002", "product_name": "Mozzarella Block LMPS", "requested_qty": 300, "unit_price": 18.49, "line_value": 5547.00}
            ],
            "total_order_value": 23042.00,
            "revenue_at_risk": 23042.00,
            "annual_customer_value": 624000,
            "current_available": {"FP001": 350, "RD002": 200},
            "shortfall": {"FP001": 150, "RD002": 100}
        }),
        "authorization_requests": json.dumps([
            {
                "id": "AR-2026-0302-001",
                "requesting_agent": "so_atp_agent",
                "target_agent": "logistics_agent",
                "priority": "CRITICAL",
                "proposed_action": {
                    "type": "expedite_outbound_shipment",
                    "order_id": "ORD-2026-8834",
                    "route": "West Valley City, UT → Los Angeles, CA",
                    "distance_miles": 660,
                    "normal_lead_time_days": 4,
                    "requested_lead_time_days": 3,
                    "mode": "LTL_expedite",
                    "temperature_requirement": "Multi-temperature (frozen + refrigerated)",
                    "estimated_expedite_cost": 1850.00,
                    "standard_shipping_cost": 980.00,
                    "expedite_premium": 870.00
                },
                "justification": "Strategic Tier 1 customer (METROGRO), $624K annual value. 3-day delivery required for 800 multi-temp cases. Standard 4-day lane insufficient.",
                "scorecard_impact": {
                    "financial": {"expedite_spend": {"current": 2100, "projected": 3950, "delta": 1850, "status": "AMBER", "note": "49% of $8,000 weekly logistics budget"}},
                    "customer": {"otif_strategic": {"current": 0.94, "projected": 0.99, "status": "GREEN"}},
                    "operational": {"carrier_utilization": {"current": 0.72, "projected": 0.78, "status": "GREEN"}}
                },
                "decision": "AUTHORIZE",
                "decision_reason": "Budget available ($4,050 remaining after this). Refrigerated LTL slot confirmed for Mar 3 pickup, Mar 5 AM delivery. Carrier: Werner Enterprises.",
                "decided_at": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=8)).isoformat() + "Z"
            },
            {
                "id": "AR-2026-0302-002",
                "requesting_agent": "so_atp_agent",
                "target_agent": "supply_agent",
                "priority": "HIGH",
                "proposed_action": {
                    "type": "expedite_inbound_supply",
                    "purpose": "Replenish stock depleted by reallocation from deferred orders",
                    "purchase_orders": [
                        {
                            "po_id": "PO-2026-EXP-441",
                            "supplier_code": "TYSON",
                            "supplier_name": "Tyson Foods Inc",
                            "supplier_location": "Springdale, AR",
                            "product_id": "FP001",
                            "product_name": "Chicken Breast IQF",
                            "qty": 150,
                            "unit_cost": 28.50,
                            "base_cost": 4275.00,
                            "normal_lead_time_days": 7,
                            "requested_lead_time_days": 4,
                            "expedite_premium_pct": 15,
                            "expedite_cost": 641.25,
                            "total_cost": 4916.25,
                            "ship_date": "2026-03-02",
                            "expected_arrival": "2026-03-06"
                        },
                        {
                            "po_id": "PO-2026-EXP-442",
                            "supplier_code": "LANDOLAKES",
                            "supplier_name": "Land O'Lakes Foodservice",
                            "supplier_location": "Arden Hills, MN",
                            "product_id": "RD002",
                            "product_name": "Mozzarella Block LMPS",
                            "qty": 100,
                            "unit_cost": 14.00,
                            "base_cost": 1400.00,
                            "normal_lead_time_days": 6,
                            "requested_lead_time_days": 3,
                            "expedite_premium_pct": 12,
                            "expedite_cost": 168.00,
                            "total_cost": 1568.00,
                            "ship_date": "2026-03-02",
                            "expected_arrival": "2026-03-05"
                        }
                    ],
                    "total_expedite_cost": 809.25
                },
                "justification": "Replenish stock depleted by reallocation from QUICKSERV/FAMREST orders. Prevents cascading shortfalls next week. Both suppliers have confirmed expedite capacity.",
                "scorecard_impact": {
                    "financial": {"procurement_expedite": {"current": 0, "projected": 809.25, "status": "AMBER"}},
                    "operational": {"pipeline_inventory": {"current": "adequate", "projected": "adequate", "status": "GREEN"}, "dos_fp001": {"current": 6.2, "projected": 8.5, "status": "GREEN"}}
                },
                "decision": "AUTHORIZE",
                "decision_reason": "Both suppliers confirmed expedite capacity. TYSON ships Mar 2 PM (arrive Mar 6). LANDOLAKES ships Mar 2 AM (arrive Mar 5). Combined premium $809 within procurement expedite budget ($5K/week).",
                "decided_at": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=12)).isoformat() + "Z"
            },
            {
                "id": "AR-2026-0302-003",
                "requesting_agent": "so_atp_agent",
                "target_agent": "allocation_agent",
                "priority": "HIGH",
                "proposed_action": {
                    "type": "reallocate_supply",
                    "aatp_consumption_rule": "Priority 1 (METROGRO) consumes from Priority 2 and 3 allocations per AATP policy",
                    "reallocations": [
                        {
                            "from_order_id": "ORD-2026-8790",
                            "from_customer_code": "QUICKSERV",
                            "from_customer_name": "Quick Serve Foods LLC",
                            "from_customer_segment": "Quick Service",
                            "from_priority": 2,
                            "product_id": "FP001",
                            "product_name": "Chicken Breast IQF",
                            "reallocate_qty": 150,
                            "original_delivery_date": "2026-03-04",
                            "deferred_delivery_date": "2026-03-08",
                            "deferral_days": 4,
                            "within_sla": True,
                            "contractual_sla_days": 5,
                            "customer_impact": "Standard order, 4-day delay within contractual SLA (5-day window). Customer notified proactively."
                        },
                        {
                            "from_order_id": "ORD-2026-8812",
                            "from_customer_code": "FAMREST",
                            "from_customer_name": "Family Restaurant Inc",
                            "from_customer_segment": "Casual Dining",
                            "from_priority": 3,
                            "product_id": "RD002",
                            "product_name": "Mozzarella Block LMPS",
                            "reallocate_qty": 100,
                            "original_delivery_date": "2026-03-05",
                            "deferred_delivery_date": "2026-03-09",
                            "deferral_days": 4,
                            "within_sla": True,
                            "contractual_sla_days": 5,
                            "customer_impact": "Standard order, 4-day delay within contractual SLA. Customer notified proactively."
                        }
                    ]
                },
                "justification": "AATP consumption sequence for Priority 1 order: [1, 5, 4, 3, 2]. Consuming from priorities 2 and 3. Both deferred orders remain within contractual SLA windows. Expedited replenishment POs (AR-002) will cover the deferred quantities before their new delivery dates.",
                "scorecard_impact": {
                    "customer": {
                        "otif_strategic": {"current": 0.94, "projected": 0.99, "status": "GREEN"},
                        "otif_standard": {"current": 0.97, "projected": 0.95, "status": "AMBER", "note": "2 standard orders deferred 4 days (within SLA)"}
                    },
                    "operational": {"backlog": {"current": 0, "projected": 0, "status": "GREEN"}}
                },
                "decision": "AUTHORIZE",
                "decision_reason": "Reallocation within AATP priority consumption policy. Both deferred customers within SLA. Proactive notification templates generated. Expedited replenishment POs cover deferred quantities.",
                "decided_at": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=5)).isoformat() + "Z"
            }
        ]),
        "balanced_scorecard": json.dumps({
            "customer": {
                "otif_strategic": {"current": 0.94, "projected": 0.99, "status": "GREEN", "note": "Metro Grocery order fulfilled on-time"},
                "otif_standard": {"current": 0.97, "projected": 0.95, "status": "AMBER", "note": "2 standard orders deferred 4 days (within SLA)"},
                "fill_rate_overall": {"current": 0.92, "projected": 0.96, "status": "GREEN"}
            },
            "financial": {
                "total_expedite_cost": {"current": 0, "projected": 2659.25, "status": "AMBER", "breakdown": {"outbound_ltl": 1850.00, "tyson_premium": 641.25, "landolakes_premium": 168.00}},
                "revenue_protected": {"current": 0, "projected": 23042.00, "status": "GREEN"},
                "annual_relationship_value": {"current": 0, "projected": 624000, "status": "GREEN"}
            },
            "operational": {
                "inventory_turns_impact": {"current": 12.1, "projected": 12.3, "status": "GREEN"},
                "pipeline_replenishment": {"current": "standard", "projected": "2 expedited POs in transit", "status": "GREEN"},
                "backlog_created": {"current": 0, "projected": 0, "status": "GREEN"}
            },
            "strategic": {
                "customer_retention_risk": {"current": "HIGH", "projected": "NONE", "status": "GREEN"},
                "revenue_at_risk": {"current": 23042, "projected": 0, "status": "GREEN"},
                "supplier_reliability_signal": {"current": "neutral", "projected": "positive", "status": "GREEN", "note": "Both suppliers responded to expedite within 30 min"}
            }
        }),
        "net_benefit": 20382.75,
        "resolution": json.dumps({
            "decision": "authorize_all",
            "actions_taken": [
                "Order ORD-2026-8834 committed to METROGRO. Promised delivery: Mar 5.",
                "Outbound LTL expedite booked: Werner Enterprises, pickup Mar 3, deliver Mar 5 AM.",
                "150 cases FP001 reallocated from QUICKSERV order ORD-2026-8790 (deferred to Mar 8).",
                "100 cases RD002 reallocated from FAMREST order ORD-2026-8812 (deferred to Mar 9).",
                "Expedited PO-2026-EXP-441 to TYSON: 150 cases FP001, ship Mar 2, arrive Mar 6.",
                "Expedited PO-2026-EXP-442 to LANDOLAKES: 100 cases RD002, ship Mar 2, arrive Mar 5.",
                "Proactive delay notifications sent to QUICKSERV and FAMREST."
            ],
            "resolved_by": "so_atp_agent",
            "resolved_at": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=13)).isoformat() + "Z",
            "total_elapsed_seconds": 13,
            "human_intervention": "none"
        }),
        "timeline": json.dumps([
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=0)).isoformat() + "Z", "agent": "so_atp_agent", "action": "order_received", "detail": "Metro Grocery order ORD-2026-8834 received. 500 FP001 + 300 RD002, deliver by Mar 5. CTP check: shortfall FP001 -150, RD002 -100."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=1)).isoformat() + "Z", "agent": "so_atp_agent", "action": "evaluate", "detail": "Evaluated 4 options: (1) partial fill 69% ($15,899), (2) full fill with expedite only ($23,042 - $2,659 = $20,383), (3) full fill with reallocation only ($23,042 - $0 = $23,042 but SLA risk), (4) multi-party expedite + reallocate + replenish ($20,383 net, zero SLA breach). Option 4 selected."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=3)).isoformat() + "Z", "agent": "so_atp_agent", "action": "request_auth", "detail": "Sent 3 concurrent authorization requests: AR-001 (logistics: outbound expedite $1,850), AR-002 (supply: inbound expedite $809), AR-003 (allocation: reallocate from P2/P3 orders)."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=5)).isoformat() + "Z", "agent": "allocation_agent", "action": "authorize", "detail": "AR-003 AUTHORIZED. Priority consumption policy permits reallocation. QUICKSERV (P2) deferred 4d, FAMREST (P3) deferred 4d. Both within SLA."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=8)).isoformat() + "Z", "agent": "logistics_agent", "action": "authorize", "detail": "AR-001 AUTHORIZED. Refrigerated LTL slot confirmed: Werner Enterprises, pickup Wed Mar 3, arrive Fri Mar 5 AM. Multi-temp trailer allocated."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=12)).isoformat() + "Z", "agent": "supply_agent", "action": "authorize", "detail": "AR-002 AUTHORIZED. TYSON confirms 150 FP001 ship today PM (arrive Mar 6). LANDOLAKES confirms 100 RD002 ship today AM (arrive Mar 5). Expedite premiums: $641 + $168 = $809."},
            {"timestamp": (BASE_DATE + timedelta(hours=9, minutes=15, seconds=13)).isoformat() + "Z", "agent": "so_atp_agent", "action": "resolve", "detail": "All 3 authorizations received in 13 seconds. Order ORD-2026-8834 committed. Promised delivery: Mar 5. Net benefit: +$20,383."}
        ]),
        "assigned_to": users.get("atp_analyst"),
        "escalated_to": None,
    }


def scenario_3_exec_tyson_delay(customer_id, config_id, users):
    """Execution: Tyson Shipment Delay — Emergency PO Rerouting"""
    return {
        "config_id": config_id,
        "customer_id": customer_id,
        "scenario_code": "COLLAB-EXEC-002",
        "title": "Tyson Shipment Delay: Emergency PO Rerouting for Frozen Proteins",
        "description": (
            "Tyson Foods (TYSON) notifies of a 5-day delay on a scheduled shipment of 800 cases "
            "Chicken Breast IQF (FP001) and 400 cases Turkey Breast Deli (FP004) due to a winter storm "
            "affecting trucking from Springdale, AR. Current DC inventory covers only 6 days of demand. "
            "The PO Creation TRM recommends splitting: redirect 60% to Sysco Protein Solutions (SYSCOMEAT, "
            "Houston, TX) and keep 40% with Tyson for delayed delivery."
        ),
        "level": "execution",
        "status": "resolved",
        "priority": "high",
        "originating_agent": "po_creation_agent",
        "target_agents": json.dumps(["procurement_agent", "finance_agent"]),
        "trigger_event": json.dumps({
            "type": "supplier_delay_notification",
            "detected_at": (BASE_DATE + timedelta(hours=7)).isoformat() + "Z",
            "supplier_code": "TYSON",
            "supplier_name": "Tyson Foods Inc",
            "original_po": "PO-2026-4410",
            "affected_products": [
                {"product_id": "FP001", "product_name": "Chicken Breast IQF", "qty": 800, "unit_cost": 28.50},
                {"product_id": "FP004", "product_name": "Turkey Breast Deli", "qty": 400, "unit_cost": 38.00}
            ],
            "delay_days": 5,
            "reason": "Winter storm affecting I-40 corridor, Springdale AR trucking hub closed",
            "original_delivery_date": "2026-03-04",
            "revised_delivery_date": "2026-03-09",
            "current_dos": {"FP001": 6.2, "FP004": 5.8},
            "risk_level": "stockout_imminent"
        }),
        "authorization_requests": json.dumps([
            {
                "id": "AR-2026-0302-004",
                "requesting_agent": "po_creation_agent",
                "target_agent": "procurement_agent",
                "proposed_action": {
                    "type": "emergency_alternate_sourcing",
                    "alternate_supplier": {
                        "code": "SYSCOMEAT",
                        "name": "Sysco Protein Solutions",
                        "location": "Houston, TX",
                        "normal_lead_time_days": 9,
                        "expedited_lead_time_days": 5,
                        "reliability": 0.94
                    },
                    "split_strategy": {
                        "syscomeat_portion": 0.60,
                        "tyson_delayed_portion": 0.40,
                        "reason": "Minimize risk while maintaining TYSON relationship"
                    },
                    "emergency_pos": [
                        {"po_id": "PO-2026-EXP-450", "product_id": "FP001", "qty": 480, "unit_cost": 30.78, "spot_premium_pct": 8},
                        {"po_id": "PO-2026-EXP-451", "product_id": "FP004", "qty": 240, "unit_cost": 41.04, "spot_premium_pct": 8}
                    ],
                    "total_emergency_cost": 24619.20,
                    "standard_cost": 22795.20,
                    "spot_premium_cost": 1824.00
                },
                "justification": "Split sourcing: 60% SYSCOMEAT (arrive Mar 7) + 40% TYSON delayed (arrive Mar 9). Maintains 3+ DOS throughout. Avoids stockout affecting 4 key customers.",
                "decision": "AUTHORIZE",
                "decision_reason": "SYSCOMEAT confirmed capacity. Spot premium 8% ($1,824) acceptable vs stockout cost ($20,780). Approved under emergency procurement authority."
            },
            {
                "id": "AR-2026-0302-005",
                "requesting_agent": "po_creation_agent",
                "target_agent": "finance_agent",
                "proposed_action": {
                    "type": "unplanned_procurement_spend",
                    "amount": 1824.00,
                    "category": "spot_premium",
                    "budget_impact": "Within weekly emergency procurement reserve ($5,000)"
                },
                "justification": "Spot premium of $1,824 to avoid $20,780 in stockout costs (customer penalties, lost sales, expedite fees). ROI: 11.4x.",
                "decision": "AUTHORIZE",
                "decision_reason": "ROI 11.4x. Within emergency procurement reserve. Auto-approved per policy (<$2,500 threshold)."
            }
        ]),
        "balanced_scorecard": json.dumps({
            "customer": {
                "otif_frozen_protein": {"current": 0.96, "projected": 0.93, "status": "AMBER", "note": "Slight dip due to 1-2 day delay on some orders"},
                "fill_rate_fp001": {"current": 1.0, "projected": 0.98, "status": "GREEN"},
                "customers_affected": {"current": 0, "projected": 0, "status": "GREEN", "note": "All orders fulfilled, some shifted 1-2 days"}
            },
            "financial": {
                "spot_premium": {"current": 0, "projected": 1824.00, "status": "AMBER"},
                "stockout_cost_avoided": {"current": 0, "projected": 20780.00, "status": "GREEN"},
                "net_savings": {"current": 0, "projected": 18956.00, "status": "GREEN"}
            },
            "operational": {
                "dos_fp001": {"current": 6.2, "projected": 4.1, "status": "AMBER", "note": "Drops to 4.1 before SYSCOMEAT arrives Mar 7"},
                "dos_fp004": {"current": 5.8, "projected": 3.5, "status": "AMBER"},
                "supplier_diversification": {"current": "single_source", "projected": "dual_source", "status": "GREEN"}
            },
            "strategic": {
                "supplier_risk_score": {"current": 0.15, "projected": 0.25, "status": "AMBER", "note": "TYSON reliability downgraded temporarily"},
                "contingency_plan_activated": {"current": False, "projected": True, "status": "GREEN"}
            }
        }),
        "net_benefit": 18956.00,
        "resolution": json.dumps({
            "decision": "authorize_all",
            "actions_taken": [
                "Emergency PO-2026-EXP-450: 480 cases FP001 to SYSCOMEAT (arrive Mar 7)",
                "Emergency PO-2026-EXP-451: 240 cases FP004 to SYSCOMEAT (arrive Mar 7)",
                "TYSON delayed shipment maintained for remaining 320 FP001 + 160 FP004 (arrive Mar 9)",
                "Customer delivery schedules adjusted: 1-2 day shifts communicated proactively",
                "Supplier reliability dashboard updated: TYSON flagged for weather event tracking"
            ],
            "resolved_by": "po_creation_agent",
            "resolved_at": (BASE_DATE + timedelta(hours=7, minutes=45)).isoformat() + "Z",
            "total_elapsed_seconds": 2700,
            "human_intervention": "PO Analyst reviewed and confirmed emergency POs"
        }),
        "timeline": json.dumps([
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=0)).isoformat() + "Z", "agent": "order_tracking_agent", "action": "detect", "detail": "Supplier delay notification received from TYSON: 5-day delay on PO-2026-4410 (winter storm, I-40 corridor)."},
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=2)).isoformat() + "Z", "agent": "po_creation_agent", "action": "evaluate", "detail": "Evaluated options: (1) wait for TYSON (stockout risk 87%), (2) full switch to SYSCOMEAT (cost +$2,280), (3) split 60/40 (cost +$1,824, no stockout). Option 3 selected."},
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=5)).isoformat() + "Z", "agent": "po_creation_agent", "action": "request_auth", "detail": "Sent AR-004 to procurement_agent (emergency sourcing) and AR-005 to finance_agent (spot premium approval)."},
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=8)).isoformat() + "Z", "agent": "finance_agent", "action": "authorize", "detail": "AR-005 auto-approved. $1,824 within emergency procurement threshold ($2,500)."},
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=25)).isoformat() + "Z", "agent": "procurement_agent", "action": "authorize", "detail": "AR-004 AUTHORIZED. SYSCOMEAT confirmed 480 FP001 + 240 FP004. Ship Mar 3, arrive Mar 7. Spot premium 8%."},
            {"timestamp": (BASE_DATE + timedelta(hours=7, minutes=45)).isoformat() + "Z", "agent": "po_creation_agent", "action": "resolve", "detail": "Split sourcing executed. Emergency POs confirmed. Customer schedules adjusted. Net benefit: +$18,956."}
        ]),
        "assigned_to": users.get("po_analyst"),
        "escalated_to": None,
    }


def scenario_4_exec_school_lunch_surge(customer_id, config_id, users):
    """Execution: School Lunch Program Surge — Safety Stock Exception"""
    return {
        "config_id": config_id,
        "customer_id": customer_id,
        "scenario_code": "COLLAB-EXEC-003",
        "title": "School Lunch Program Surge: Refrigerated Dairy Safety Stock Exception",
        "description": (
            "School District Foods (SCHLDFOOD, San Diego, K-12 segment) submits an unforecasted bulk "
            "order for 600 cases Greek Yogurt Plain (RD004) and 400 cases Cheddar Block Sharp (RD001) "
            "for a district-wide school lunch program expansion. Fulfilling this order would deplete "
            "safety stock for Refrigerated Dairy below the policy floor (14 DOS down to 8 DOS). The "
            "Inventory Agent requests a temporary safety stock exception while coordinating expedited "
            "replenishment from Land O'Lakes."
        ),
        "level": "execution",
        "status": "resolved",
        "priority": "high",
        "originating_agent": "inventory_agent",
        "target_agents": json.dumps(["sop_agent", "supply_agent", "so_atp_agent"]),
        "trigger_event": json.dumps({
            "type": "safety_stock_breach_imminent",
            "detected_at": (BASE_DATE + timedelta(hours=10, minutes=30)).isoformat() + "Z",
            "customer_code": "SCHLDFOOD",
            "customer_name": "School District Foods",
            "customer_segment": "K-12 Education",
            "order_id": "ORD-2026-8851",
            "line_items": [
                {"product_id": "RD004", "product_name": "Greek Yogurt Plain", "qty": 600, "unit_cost": 4.25, "unit_price": 5.99, "line_value": 3594.00, "shelf_life_days": 45},
                {"product_id": "RD001", "product_name": "Cheddar Block Sharp", "qty": 400, "unit_cost": 15.50, "unit_price": 19.99, "line_value": 7996.00, "shelf_life_days": 180}
            ],
            "total_order_value": 11590.00,
            "safety_stock_impact": {
                "RD004": {"current_dos": 14.0, "post_order_dos": 8.0, "policy_floor_dos": 14.0, "breach_severity": "moderate"},
                "RD001": {"current_dos": 14.0, "post_order_dos": 9.0, "policy_floor_dos": 14.0, "breach_severity": "moderate"}
            },
            "reason": "District-wide school lunch program expansion — 47 schools, starts Mar 10"
        }),
        "authorization_requests": json.dumps([
            {
                "id": "AR-2026-0302-006",
                "requesting_agent": "inventory_agent",
                "target_agent": "sop_agent",
                "proposed_action": {
                    "type": "temporary_safety_stock_exception",
                    "products": ["RD004", "RD001"],
                    "current_policy_dos": 14,
                    "temporary_floor_dos": 7,
                    "duration_days": 7,
                    "effective_date": "2026-03-02",
                    "expiry_date": "2026-03-09"
                },
                "justification": "7-day exception allows order fulfillment while expedited replenishment arrives. DOS never drops below 7 (50% of policy). Replenishment PO arrives Mar 5, restoring full safety stock by Mar 8.",
                "decision": "AUTHORIZE",
                "decision_reason": "Exception approved. 7-day DOS is acceptable short-term risk given known replenishment in pipeline. Historical stockout probability at 7 DOS: 3.2% (vs 0.5% at 14 DOS)."
            },
            {
                "id": "AR-2026-0302-007",
                "requesting_agent": "inventory_agent",
                "target_agent": "supply_agent",
                "proposed_action": {
                    "type": "expedite_replenishment",
                    "purchase_orders": [
                        {
                            "po_id": "PO-2026-REP-460",
                            "supplier_code": "LANDOLAKES",
                            "supplier_name": "Land O'Lakes Foodservice",
                            "products": [
                                {"product_id": "RD004", "qty": 600, "unit_cost": 4.25},
                                {"product_id": "RD001", "qty": 400, "unit_cost": 15.50}
                            ],
                            "normal_lead_time_days": 6,
                            "requested_lead_time_days": 3,
                            "expedite_premium": 0,
                            "total_cost": 8750.00,
                            "note": "LANDOLAKES has capacity — no premium required"
                        }
                    ]
                },
                "justification": "LANDOLAKES has available capacity and can expedite without premium. Replenishment restores full safety stock within 3 days.",
                "decision": "AUTHORIZE",
                "decision_reason": "LANDOLAKES confirmed. Ship Mar 2, arrive Mar 5. Standard pricing (no expedite premium — supplier has capacity and values the volume)."
            },
            {
                "id": "AR-2026-0302-008",
                "requesting_agent": "inventory_agent",
                "target_agent": "so_atp_agent",
                "proposed_action": {
                    "type": "reserve_incoming_stock",
                    "po_id": "PO-2026-REP-460",
                    "products": [
                        {"product_id": "RD004", "qty": 600, "reserve_until": "2026-03-10"},
                        {"product_id": "RD001", "qty": 400, "reserve_until": "2026-03-10"}
                    ],
                    "reason": "Prevent incoming replenishment from being allocated to other orders before safety stock is restored"
                },
                "justification": "Incoming stock must be reserved for safety stock restoration, not consumed by new orders during the exception window.",
                "decision": "AUTHORIZE",
                "decision_reason": "Stock reservation confirmed. PO-2026-REP-460 quantities will be reserved for safety stock restoration upon receipt."
            }
        ]),
        "balanced_scorecard": json.dumps({
            "customer": {
                "otif_schldfood": {"current": 0.96, "projected": 1.0, "status": "GREEN", "note": "Order fulfilled in full, on time"},
                "fill_rate_dairy": {"current": 0.98, "projected": 0.95, "status": "AMBER", "note": "Slight risk during exception window"},
                "customer_satisfaction": {"current": "good", "projected": "excellent", "status": "GREEN", "note": "K-12 contract secured"}
            },
            "financial": {
                "order_revenue": {"current": 0, "projected": 11590.00, "status": "GREEN"},
                "expedite_cost": {"current": 0, "projected": 0, "status": "GREEN", "note": "No premium from LANDOLAKES"},
                "customer_lifetime_value": {"current": 90000, "projected": 135000, "status": "GREEN", "note": "School program is recurring"}
            },
            "operational": {
                "dos_rd004": {"current": 14.0, "projected": 8.0, "status": "AMBER", "note": "Restores to 14 DOS by Mar 8"},
                "dos_rd001": {"current": 14.0, "projected": 9.0, "status": "AMBER", "note": "Restores to 14 DOS by Mar 8"},
                "stockout_probability": {"current": 0.005, "projected": 0.032, "status": "AMBER", "note": "Temporary elevation during exception"}
            },
            "strategic": {
                "k12_segment_growth": {"current": "stable", "projected": "+15%", "status": "GREEN"},
                "customer_retention_risk": {"current": "MEDIUM", "projected": "NONE", "status": "GREEN"},
                "recurring_revenue": {"current": 0, "projected": 46360, "status": "GREEN", "note": "$11,590/month recurring"}
            }
        }),
        "net_benefit": 12800.00,
        "resolution": json.dumps({
            "decision": "authorize_all",
            "actions_taken": [
                "Temporary safety stock exception approved: 14 DOS → 7 DOS floor for RD004/RD001 (7 days)",
                "Order ORD-2026-8851 committed to SCHLDFOOD. Full quantity, delivery Mar 4.",
                "Expedited replenishment PO-2026-REP-460 to LANDOLAKES: 600 RD004 + 400 RD001 (arrive Mar 5)",
                "Stock reservation placed on incoming PO for safety stock restoration",
                "Exception dashboard alert set: auto-close when DOS restored above 14"
            ],
            "resolved_by": "inventory_agent",
            "resolved_at": (BASE_DATE + timedelta(hours=11, minutes=15)).isoformat() + "Z",
            "human_intervention": "MPS Manager reviewed exception. S&OP Director approved safety stock override."
        }),
        "timeline": json.dumps([
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=30)).isoformat() + "Z", "agent": "so_atp_agent", "action": "order_received", "detail": "SCHLDFOOD order ORD-2026-8851 received: 600 RD004 + 400 RD001. CTP check passed but safety stock breach detected."},
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=31)).isoformat() + "Z", "agent": "inventory_agent", "action": "detect", "detail": "Safety stock breach imminent: RD004 drops to 8 DOS (floor: 14), RD001 drops to 9 DOS (floor: 14)."},
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=33)).isoformat() + "Z", "agent": "inventory_agent", "action": "evaluate", "detail": "Evaluated options: (1) reject order (lose $11,590 + customer), (2) partial fill (risk relationship), (3) exception + expedited replenishment (net benefit +$12,800). Option 3 selected."},
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=35)).isoformat() + "Z", "agent": "inventory_agent", "action": "request_auth", "detail": "Sent AR-006 (SS exception to sop_agent), AR-007 (expedite replenishment to supply_agent), AR-008 (reserve stock to so_atp_agent)."},
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=40)).isoformat() + "Z", "agent": "so_atp_agent", "action": "authorize", "detail": "AR-008 AUTHORIZED. Stock reservation placed on incoming PO quantities."},
            {"timestamp": (BASE_DATE + timedelta(hours=10, minutes=50)).isoformat() + "Z", "agent": "supply_agent", "action": "authorize", "detail": "AR-007 AUTHORIZED. LANDOLAKES confirmed: 600 RD004 + 400 RD001, ship today, arrive Mar 5. No premium."},
            {"timestamp": (BASE_DATE + timedelta(hours=11, minutes=0)).isoformat() + "Z", "agent": "sop_agent", "action": "escalate", "detail": "AR-006 requires human approval (safety stock exception). Escalated to MPS Manager and S&OP Director."},
            {"timestamp": (BASE_DATE + timedelta(hours=11, minutes=10)).isoformat() + "Z", "agent": "sop_agent", "action": "authorize", "detail": "AR-006 AUTHORIZED. S&OP Director approved 7-day exception. DOS floor lowered 14 → 7 for RD004/RD001."},
            {"timestamp": (BASE_DATE + timedelta(hours=11, minutes=15)).isoformat() + "Z", "agent": "inventory_agent", "action": "resolve", "detail": "All authorizations received. Order committed. Replenishment in transit. Exception auto-closes when DOS restored."}
        ]),
        "assigned_to": users.get("mps_manager"),
        "escalated_to": users.get("sop_director"),
    }


def scenario_5_exec_frozen_zone_rebalancing(customer_id, config_id, users):
    """Execution: Frozen Zone Capacity — Cross-Temperature Rebalancing"""
    return {
        "config_id": config_id,
        "customer_id": customer_id,
        "scenario_code": "COLLAB-EXEC-004",
        "title": "Frozen Zone Capacity Crunch: Cross-Temperature Rebalancing",
        "description": (
            "The DC's frozen storage zone is at 93% capacity (139,500 / 150,000 cases) due to seasonal "
            "build-up of Frozen Desserts (FD001-FD005) for spring catering season. Meanwhile the dry goods "
            "zone is at only 52% utilization. Inbound shipments from Nestle (FD001, FD002) and Rich Products "
            "(FD003-FD005) arriving Mar 3-4 will push frozen to 101% — exceeding capacity. The Rebalancing "
            "TRM recommends transferring 15,000 dry goods cases to overflow staging, freeing dock capacity "
            "for frozen receiving."
        ),
        "level": "execution",
        "status": "resolved",
        "priority": "medium",
        "originating_agent": "inventory_rebalancing_agent",
        "target_agents": json.dumps(["logistics_agent", "sop_agent", "order_tracking_agent"]),
        "trigger_event": json.dumps({
            "type": "capacity_threshold_breach",
            "detected_at": (BASE_DATE + timedelta(hours=6)).isoformat() + "Z",
            "zone": "frozen",
            "site": "FOODDIST_DC",
            "current_utilization": 0.93,
            "current_cases": 139500,
            "max_capacity_cases": 150000,
            "incoming_shipments": [
                {"supplier": "NESTLE", "products": ["FD001", "FD002"], "cases": 6000, "arrival": "2026-03-03"},
                {"supplier": "RICHPROD", "products": ["FD003", "FD004", "FD005"], "cases": 8500, "arrival": "2026-03-04"}
            ],
            "projected_utilization_post_receipt": 1.027,
            "projected_overflow_cases": 4000,
            "dry_zone_utilization": 0.52,
            "dry_zone_available_cases": 48000,
            "reason": "Seasonal frozen dessert build for spring catering season"
        }),
        "authorization_requests": json.dumps([
            {
                "id": "AR-2026-0302-009",
                "requesting_agent": "inventory_rebalancing_agent",
                "target_agent": "logistics_agent",
                "proposed_action": {
                    "type": "dock_schedule_rearrangement",
                    "current_dock_schedule": "Frozen receiving: Dock 1-3 (06:00-14:00), Dry receiving: Dock 4-5 (06:00-12:00)",
                    "proposed_schedule": "Frozen receiving: Dock 1-4 (06:00-16:00 Mar 3-4), Dry transfer: Dock 5 (14:00-16:00 Mar 2)",
                    "dry_transfer_volume": 15000,
                    "transfer_destination": "Overflow staging area (adjacent building, dry temp)",
                    "labor_requirement": "2 forklift operators × 2 hours",
                    "estimated_cost": 450
                },
                "justification": "Rearranging dock schedule opens Dock 4 for frozen receiving. 2-hour dry transfer window minimal disruption to outbound picks.",
                "decision": "AUTHORIZE",
                "decision_reason": "Dock 4 available for reassignment. Forklift operators available 14:00-16:00 shift. Overflow staging confirmed dry and secure."
            },
            {
                "id": "AR-2026-0302-010",
                "requesting_agent": "inventory_rebalancing_agent",
                "target_agent": "sop_agent",
                "proposed_action": {
                    "type": "capacity_threshold_override",
                    "zone": "frozen",
                    "current_threshold": 0.90,
                    "temporary_threshold": 0.97,
                    "duration_days": 5,
                    "reason": "Allow seasonal frozen build while transfer occurs"
                },
                "justification": "Temporary 97% threshold during the 5-day build period. Normal operations resume once spring catering orders begin depleting frozen inventory (~Mar 7).",
                "decision": "AUTHORIZE",
                "decision_reason": "Temporary threshold acceptable. Fire safety clearance maintained at 97%. Sprinkler access not impacted. Reviewed by facility manager."
            },
            {
                "id": "AR-2026-0302-011",
                "requesting_agent": "inventory_rebalancing_agent",
                "target_agent": "order_tracking_agent",
                "proposed_action": {
                    "type": "adjust_pick_sequencing",
                    "affected_products": ["DP001", "DP002", "DP003", "DP004", "DP005"],
                    "current_pick_zone": "Dry Zone A (primary)",
                    "temporary_pick_zone": "Overflow Staging (secondary)",
                    "duration_days": 5,
                    "impact_on_pick_time": "+3 minutes per dry order (additional walk distance)"
                },
                "justification": "15,000 dry cases moved to overflow. Outbound pick time increases by ~3 minutes per dry order. No impact on delivery windows (all dry orders picked by 10 AM).",
                "decision": "AUTHORIZE",
                "decision_reason": "Pick sequencing updated. WMS rerouting configured. +3 min per order acceptable — still within pick-to-ship SLA."
            }
        ]),
        "balanced_scorecard": json.dumps({
            "customer": {
                "otif_frozen": {"current": 0.97, "projected": 0.97, "status": "GREEN", "note": "No impact on customer deliveries"},
                "otif_dry": {"current": 0.98, "projected": 0.97, "status": "GREEN", "note": "Minimal pick time increase"}
            },
            "financial": {
                "demurrage_avoided": {"current": 0, "projected": 4500, "status": "GREEN", "note": "2 trucks × $2,250 demurrage fee avoided"},
                "receiving_delay_cost_avoided": {"current": 0, "projected": 3700, "status": "GREEN", "note": "14,500 cases would be delayed 2 days"},
                "transfer_labor_cost": {"current": 0, "projected": 450, "status": "GREEN"},
                "net_savings": {"current": 0, "projected": 7750, "status": "GREEN"}
            },
            "operational": {
                "frozen_utilization": {"current": 0.93, "projected": 0.95, "status": "AMBER", "note": "Post-receiving, pre-catering depletion"},
                "dry_utilization": {"current": 0.52, "projected": 0.62, "status": "GREEN"},
                "dock_throughput": {"current": "constrained", "projected": "normal", "status": "GREEN"}
            },
            "strategic": {
                "seasonal_readiness": {"current": "at_risk", "projected": "ready", "status": "GREEN"},
                "supplier_relationship": {"current": "strained", "projected": "positive", "status": "GREEN", "note": "No demurrage disputes with NESTLE/RICHPROD"}
            }
        }),
        "net_benefit": 7750.00,
        "resolution": json.dumps({
            "decision": "authorize_all",
            "actions_taken": [
                "15,000 dry goods cases transferred to overflow staging (Mar 2, 14:00-16:00)",
                "Dock 4 reassigned to frozen receiving for Mar 3-4",
                "Frozen capacity threshold temporarily raised to 97% for 5 days",
                "WMS pick sequencing updated: dry products route through overflow staging",
                "Inbound NESTLE (6,000 cases Mar 3) and RICHPROD (8,500 cases Mar 4) confirmed received"
            ],
            "resolved_by": "inventory_rebalancing_agent",
            "resolved_at": (BASE_DATE + timedelta(hours=6, minutes=45)).isoformat() + "Z",
            "human_intervention": "Rebalancing Analyst confirmed dock schedule change with warehouse supervisor"
        }),
        "timeline": json.dumps([
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=0)).isoformat() + "Z", "agent": "inventory_rebalancing_agent", "action": "detect", "detail": "Frozen zone at 93% capacity. Incoming NESTLE + RICHPROD shipments (14,500 cases) will push to 101%. Breach in 24 hours."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=3)).isoformat() + "Z", "agent": "inventory_rebalancing_agent", "action": "evaluate", "detail": "Evaluated options: (1) defer inbound (demurrage $4,500), (2) emergency off-site storage ($8,200), (3) internal rebalancing: dry → overflow ($450). Option 3 selected."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=5)).isoformat() + "Z", "agent": "inventory_rebalancing_agent", "action": "request_auth", "detail": "Sent AR-009 (dock rearrangement), AR-010 (capacity threshold override), AR-011 (pick sequencing adjustment)."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=10)).isoformat() + "Z", "agent": "logistics_agent", "action": "authorize", "detail": "AR-009 AUTHORIZED. Dock 4 reassigned. Forklift operators scheduled 14:00-16:00."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=20)).isoformat() + "Z", "agent": "order_tracking_agent", "action": "authorize", "detail": "AR-011 AUTHORIZED. WMS pick sequencing updated for overflow routing. +3 min/order within SLA."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=35)).isoformat() + "Z", "agent": "sop_agent", "action": "authorize", "detail": "AR-010 AUTHORIZED. Temporary frozen threshold 90% → 97% for 5 days. Facility safety clearance confirmed."},
            {"timestamp": (BASE_DATE + timedelta(hours=6, minutes=45)).isoformat() + "Z", "agent": "inventory_rebalancing_agent", "action": "resolve", "detail": "All 3 authorizations received. Dry transfer scheduled for 14:00 today. Frozen zone ready for inbound. Net savings: +$7,750."}
        ]),
        "assigned_to": users.get("rebalancing_analyst"),
        "escalated_to": None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("Seeding Collaboration Scenarios for Food Dist")
    log.info("=" * 60)

    engine = get_engine()

    with engine.connect() as conn:
        # Step 1: Ensure table exists
        log.info("\n[1/3] Ensuring collaboration_scenarios table...")
        ensure_table(conn)

        # Step 2: Lookup Food Dist context
        log.info("\n[2/3] Looking up Food Dist tenant, config, and users...")
        customer_id, config_id, users = lookup_food_dist(conn)

        # Step 3: Clean and insert
        log.info("\n[3/3] Seeding 5 collaboration scenarios...")
        conn.execute(text(
            "DELETE FROM collaboration_scenarios WHERE config_id = :cid"
        ), {"cid": config_id})
        conn.commit()
        log.info("  Cleaned existing scenarios.")

        scenarios = [
            scenario_1_sop_beverage_surge(customer_id, config_id, users),
            scenario_2_exec_metro_grocery_rush(customer_id, config_id, users),
            scenario_3_exec_tyson_delay(customer_id, config_id, users),
            scenario_4_exec_school_lunch_surge(customer_id, config_id, users),
            scenario_5_exec_frozen_zone_rebalancing(customer_id, config_id, users),
        ]

        for s in scenarios:
            conn.execute(text("""
                INSERT INTO collaboration_scenarios (
                    config_id, customer_id, scenario_code, title, description,
                    level, status, priority,
                    originating_agent, target_agents, trigger_event,
                    authorization_requests, balanced_scorecard, net_benefit,
                    resolution, timeline, assigned_to, escalated_to
                ) VALUES (
                    :config_id, :customer_id, :scenario_code, :title, :description,
                    :level, :status, :priority,
                    :originating_agent, :target_agents, :trigger_event,
                    :authorization_requests, :balanced_scorecard, :net_benefit,
                    :resolution, :timeline, :assigned_to, :escalated_to
                )
            """), s)
            log.info(f"  ✓ {s['scenario_code']}: {s['title'][:60]}...")

        conn.commit()

    log.info("\n" + "=" * 60)
    log.info("Done! 5 collaboration scenarios seeded.")
    log.info("=" * 60)
    log.info("\nScenarios:")
    log.info("  1. COLLAB-SOP-001  (S&OP)      Summer Beverage Surge")
    log.info("  2. COLLAB-EXEC-001 (Execution)  Metro Grocery Rush Order ★")
    log.info("  3. COLLAB-EXEC-002 (Execution)  Tyson Supplier Delay")
    log.info("  4. COLLAB-EXEC-003 (Execution)  School Lunch Demand Spike")
    log.info("  5. COLLAB-EXEC-004 (Execution)  Frozen Zone Capacity")
    log.info("\nTest: curl -b /tmp/cookies3.txt http://localhost:8000/api/v1/collaboration/scenarios")


if __name__ == "__main__":
    main()

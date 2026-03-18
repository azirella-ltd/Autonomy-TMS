#!/usr/bin/env python3
"""Seed realistic Decision Stream, S&OP Worklist, MPS Plan, and Executive Briefing
for config 74 (Company Code 1710 SC Network), tenant 20.

Uses ONLY real site names, product IDs, supplier names, and realistic volumes/prices
extracted from the SAP-imported data set.

Usage:
    docker compose exec backend python scripts/seed_sap_decisions.py
"""

import sys, os, uuid, random
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_TYPE", "postgresql")

from app.db.session import sync_session_factory
from sqlalchemy import text

CONFIG_ID = 74
TENANT_ID = 20
NOW = datetime.utcnow()
TODAY = date.today()

# ─── Real master data from config 74 ─────────────────────────────────────────

PLANTS = {
    "1710": {"id": 429, "desc": "Plant 1 US", "city": "Palo Alto"},
    "1720": {"id": 430, "desc": "Plant 2 US", "city": "Dallas"},
}

SUPPLIERS = {
    "0017300001": "Domestic US Supplier 1",
    "0017300002": "Domestic US Supplier 2",
    "0017300003": "Domestic US Supplier 3",
    "0017300007": "Domestic US Subcontractor A",
    "EWM17-SU01": "EWM Supplier 01",
}

CUSTOMERS = {
    "DEMAND_US": {"id": 439, "label": "US Customers"},
    "DEMAND_AMERICAS": {"id": 440, "label": "Americas Customers"},
    "DEMAND_EUROPE": {"id": 441, "label": "Europe Customers"},
    "DEMAND_ASIA": {"id": 442, "label": "Asia Customers"},
}

# Key products with realistic prices and volumes
FINISHED_GOODS = {
    "FG111":  {"desc": "Finished Good 111",         "price": 45.00,  "wk_demand": 200},
    "FG126":  {"desc": "Finished Good 126",         "price": 78.50,  "wk_demand": 120},
    "FG129":  {"desc": "Finished Good 129",         "price": 1950.0, "wk_demand": 15},
    "FG200":  {"desc": "Finished Good 200",         "price": 62.00,  "wk_demand": 85},
    "FG226":  {"desc": "Finished Good 226",         "price": 320.00, "wk_demand": 42},
    "MZ-FG-R100": {"desc": "Racing Bike R100",      "price": 2800.0, "wk_demand": 8},
    "MZ-FG-M500": {"desc": "Mountain Bike M500",    "price": 1450.0, "wk_demand": 12},
    "MZ-FG-C900": {"desc": "Cruise Bike C900",      "price": 980.0,  "wk_demand": 18},
    "FG-FL-MV-V00": {"desc": "Forklift Model V00",  "price": 24500.0,"wk_demand": 3},
    "AVC_RBT_ROBOT": {"desc": "Robotics Assembly",  "price": 8750.0, "wk_demand": 5},
}

RAW_MATERIALS = {
    "RM09":   {"desc": "Raw Material 09",     "price": 0.08,   "wk_usage": 5000},
    "RM20":   {"desc": "Raw Material 20",     "price": 1.23,   "wk_usage": 3200},
    "RM120":  {"desc": "Raw Material 120",    "price": 1.37,   "wk_usage": 1800},
    "RM128":  {"desc": "Raw Material 128",    "price": 38.00,  "wk_usage": 420},
    "RM129":  {"desc": "Raw Material 129",    "price": 1800.0, "wk_usage": 8},
    "PUMP_MOTOR_KE": {"desc": "Pump Motor KE","price": 520.95, "wk_usage": 25},
    "MZ-RM-FRAME-R": {"desc": "Racing Frame", "price": 285.0,  "wk_usage": 8},
    "MZ-RM-WHEEL-R": {"desc": "Racing Wheel", "price": 120.0,  "wk_usage": 16},
}

SEMI_FINISHED = {
    "SG21":   {"desc": "Semi-Finished 21",    "price": 15.50,  "wk_usage": 600},
    "SG22":   {"desc": "Semi-Finished 22",    "price": 22.80,  "wk_usage": 450},
    "SG23":   {"desc": "Semi-Finished 23",    "price": 0.59,   "wk_usage": 2200},
    "SF-FL-FORK-SEAT": {"desc": "Forklift Fork-Seat Assembly", "price": 890.0, "wk_usage": 3},
}

TRADING_GOODS = {
    "TG10":  {"desc": "Trading Good 10",  "price": 12.46, "wk_demand": 350},
    "TG14":  {"desc": "Trading Good 14",  "price": 35.00, "wk_demand": 180},
    "TG25":  {"desc": "Trading Good 25",  "price": 48.00, "wk_demand": 95},
    "QM001": {"desc": "Quality Mat 001",  "price": 35.00, "wk_demand": 65},
}


def uid():
    return str(uuid.uuid4())[:8]


def seed_atp_decisions(db):
    """ATP decisions with a range of urgencies and likelihoods."""
    print("  Seeding ATP decisions...")
    decisions = [
        # HIGH urgency, HIGH confidence — large US customer order, tight timeline
        {
            "order_id": f"SO-1710-{uid()}",
            "product_id": "FG129",
            "location_id": "1710",
            "requested_qty": 12,
            "order_priority": 1,
            "can_fulfill": False,
            "promised_qty": 8,
            "confidence": 0.92,
            "reason": "inventory_shortfall",
            "decision_method": "trm",
            "decision_reasoning": (
                "Customer order for 12 units of Finished Good 129 (unit price $1,950) at Plant 1710. "
                "Current on-hand inventory is 0 EA with 8 units in production pipeline (MO-1710-A). "
                "Can promise 8 units by requested date; remaining 4 units require expedited production. "
                "Recommending partial fulfillment to protect $15,600 revenue while avoiding $7,800 backorder cost. "
                "US Customers (DEMAND_US) account for 62% of FG129 demand."
            ),
            "urgency_at_time": 0.88,
            "cycle_phase": "PROTECT",
        },
        # HIGH urgency, MEDIUM confidence — bike order hitting capacity
        {
            "order_id": f"SO-1710-{uid()}",
            "product_id": "MZ-FG-R100",
            "location_id": "1710",
            "requested_qty": 6,
            "order_priority": 2,
            "can_fulfill": True,
            "promised_qty": 6,
            "confidence": 0.71,
            "reason": "tight_capacity",
            "decision_method": "trm",
            "decision_reasoning": (
                "Order for 6 Racing Bike R100 units ($2,800 each, $16,800 total) from Europe Customers. "
                "Assembly line at Plant 1710 currently at 87% utilization. BOM requires Racing Frame "
                "(MZ-RM-FRAME-R, $285), 2x Racing Wheels (MZ-RM-WHEEL-R, $120 each), and 4 other components. "
                "All components currently available. Confidence reduced to 0.71 because the frame supplier "
                "(EV Parts Inc.) has shown 3-day lead time variability in recent shipments. "
                "Recommending full promise with 2-day buffer on delivery date."
            ),
            "urgency_at_time": 0.82,
            "cycle_phase": "PROTECT",
        },
        # MEDIUM urgency, HIGH confidence — standard trading goods
        {
            "order_id": f"SO-1710-{uid()}",
            "product_id": "TG10",
            "location_id": "1710",
            "requested_qty": 500,
            "order_priority": 3,
            "can_fulfill": True,
            "promised_qty": 500,
            "confidence": 0.95,
            "reason": "fully_available",
            "decision_method": "trm",
            "decision_reasoning": (
                "Standard replenishment order for 500 units of Trading Good 10 ($12.46/unit, $6,230 total) "
                "for US Customers. Sourced from Domestic US Supplier 1 with reliable 7-day lead time. "
                "Current pipeline has 1,200 units in transit. Full promise with standard priority."
            ),
            "urgency_at_time": 0.35,
            "cycle_phase": "PROTECT",
        },
        # LOW urgency, HIGH confidence — routine small order
        {
            "order_id": f"SO-1720-{uid()}",
            "product_id": "FG200",
            "location_id": "1720",
            "requested_qty": 30,
            "order_priority": 4,
            "can_fulfill": True,
            "promised_qty": 30,
            "confidence": 0.97,
            "reason": "fully_available",
            "decision_method": "heuristic",
            "decision_reasoning": (
                "Routine order for 30 units of Finished Good 200 ($62/unit) at Plant 1720 (Dallas). "
                "Well within available capacity and inventory. Americas Customers order, standard terms. "
                "No supply constraints detected."
            ),
            "urgency_at_time": 0.12,
            "cycle_phase": "PROTECT",
        },
        # HIGH urgency, LOW confidence — robotics order with component uncertainty
        {
            "order_id": f"SO-1710-{uid()}",
            "product_id": "AVC_RBT_ROBOT",
            "location_id": "1710",
            "requested_qty": 4,
            "order_priority": 1,
            "can_fulfill": False,
            "promised_qty": 2,
            "confidence": 0.45,
            "reason": "component_shortage",
            "decision_method": "trm",
            "decision_reasoning": (
                "Priority order for 4 Robotics Assembly units ($8,750 each, $35,000 total) from Asia Customers. "
                "BOM explosion shows shortage of AVC_RBT_LINK_ARM component — only 2 in stock, 0 in pipeline. "
                "Supplier lead time for link arms is 14 days. Can promise 2 units now, remaining 2 units "
                "earliest in 3 weeks. Confidence low (0.45) due to supplier variability on specialty components. "
                "Escalation recommended — $17,500 revenue at risk."
            ),
            "urgency_at_time": 0.94,
            "cycle_phase": "PROTECT",
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_atp_decisions
            (config_id, order_id, product_id, location_id, requested_qty, order_priority,
             can_fulfill, promised_qty, confidence, reason, decision_method,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :order_id, :product_id, :location_id, :requested_qty, :order_priority,
                    :can_fulfill, :promised_qty, :confidence, :reason, :decision_method,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(0.5, 12)),
        })
    print(f"    {len(decisions)} ATP decisions created")


def seed_po_decisions(db):
    """Purchase order decisions across urgency/confidence spectrum."""
    print("  Seeding PO decisions...")
    decisions = [
        # URGENT — critical raw material running out
        {
            "product_id": "RM129",
            "location_id": "1710",
            "supplier_id": "0017300002",
            "recommended_qty": 10,
            "trigger_reason": "stockout_prevention",
            "urgency": "critical",
            "confidence": 0.88,
            "inventory_position": 2.0,
            "days_of_supply": 1.8,
            "forecast_30_day": 35.0,
            "expected_receipt_date": TODAY + timedelta(days=9),
            "expected_cost": 18000.0,
            "decision_reasoning": (
                "CRITICAL: Raw Material 129 ($1,800/unit) at Plant 1710 has only 2 units on hand — "
                "1.8 days of supply against 30-day forecast of 35 units. Domestic US Supplier 2 "
                "is the sole source with 9-day lead time. Recommending immediate PO for 10 units "
                "($18,000) to cover 2-week demand plus safety buffer. RM129 is a critical component "
                "for FG129 production — stockout would halt the $1,950/unit finished goods line. "
                "Lead time from SUPPLY_US via truck is 7 days plus 2-day receiving."
            ),
            "urgency_at_time": 0.95,
        },
        # STANDARD — pump motor replenishment
        {
            "product_id": "PUMP_MOTOR_KE",
            "location_id": "1710",
            "supplier_id": "0017300001",
            "recommended_qty": 50,
            "trigger_reason": "reorder_point",
            "urgency": "standard",
            "confidence": 0.91,
            "inventory_position": 28.0,
            "days_of_supply": 7.8,
            "forecast_30_day": 108.0,
            "expected_receipt_date": TODAY + timedelta(days=7),
            "expected_cost": 26047.50,
            "decision_reasoning": (
                "Pump Motor KE inventory at Plant 1710 hit reorder point: 28 units on hand, "
                "7.8 days of supply. Weekly usage rate is 25 units for forklift assembly (FG-FL-MV-V00). "
                "Domestic US Supplier 1 offers $520.95/unit with 7-day lead time from SUPPLY_US. "
                "Recommending standard PO for 50 units ($26,048) — covers 2 weeks of production "
                "plus safety stock buffer. Supplier reliability score: 94%."
            ),
            "urgency_at_time": 0.52,
        },
        # LOW — opportunistic volume purchase
        {
            "product_id": "RM09",
            "location_id": "1720",
            "supplier_id": "0017300001",
            "recommended_qty": 15000,
            "trigger_reason": "economic_order_qty",
            "urgency": "low",
            "confidence": 0.85,
            "inventory_position": 8500.0,
            "days_of_supply": 11.9,
            "forecast_30_day": 21400.0,
            "expected_receipt_date": TODAY + timedelta(days=7),
            "expected_cost": 1200.0,
            "decision_reasoning": (
                "Raw Material 09 ($0.08/unit) at Plant 1720 (Dallas) — 8,500 units on hand, "
                "11.9 days of supply. Weekly usage across multiple BOMs is ~5,000 units. "
                "EOQ calculation suggests 15,000 unit order ($1,200) from Domestic US Supplier 1 "
                "to minimize total cost (ordering + holding). Non-urgent — current stock covers "
                "next 12 days. Order can be combined with next scheduled delivery for freight savings."
            ),
            "urgency_at_time": 0.15,
        },
        # MEDIUM — racing bike frame from specialty supplier
        {
            "product_id": "MZ-RM-FRAME-R",
            "location_id": "1710",
            "supplier_id": "0017300001",
            "recommended_qty": 20,
            "trigger_reason": "demand_increase",
            "urgency": "standard",
            "confidence": 0.68,
            "inventory_position": 5.0,
            "days_of_supply": 4.4,
            "forecast_30_day": 34.0,
            "expected_receipt_date": TODAY + timedelta(days=12),
            "expected_cost": 5700.0,
            "decision_reasoning": (
                "Racing Frame (MZ-RM-FRAME-R, $285/unit) at Plant 1710: 5 units on hand, 4.4 days supply. "
                "Demand forecast increased 25% due to Europe Customers order surge for Racing Bike R100. "
                "Supplier lead time is 12 days for specialty aluminum frames. Confidence at 0.68 — "
                "supplier has shown variability (9-15 days actual vs. 12 quoted). Recommending 20 units "
                "($5,700) to cover forecasted demand plus a 3-unit safety buffer. "
                "Racing Bike R100 at $2,800/unit — frame availability directly gates finished goods revenue."
            ),
            "urgency_at_time": 0.65,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_po_decisions
            (config_id, product_id, location_id, supplier_id, recommended_qty,
             trigger_reason, urgency, confidence, inventory_position, days_of_supply,
             forecast_30_day, expected_receipt_date, expected_cost,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :product_id, :location_id, :supplier_id, :recommended_qty,
                    :trigger_reason, :urgency, :confidence, :inventory_position, :days_of_supply,
                    :forecast_30_day, :expected_receipt_date, :expected_cost,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "ACQUIRE",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(0.5, 18)),
        })
    print(f"    {len(decisions)} PO decisions created")


def seed_mo_decisions(db):
    """Manufacturing order decisions at both plants."""
    print("  Seeding MO decisions...")
    decisions = [
        # Urgent forklift production at 1710
        {
            "production_order_id": f"MO-1710-{uid()}",
            "product_id": "FG-FL-MV-V00",
            "site_id": "1710",
            "planned_qty": 5,
            "decision_type": "expedite",
            "sequence_position": 1,
            "priority_override": 1,
            "resource_id": "ASSEMBLY-LINE-1",
            "setup_time_hours": 4.0,
            "run_time_hours": 16.0,
            "confidence": 0.83,
            "reason": "customer_commit",
            "decision_reasoning": (
                "Expedite manufacturing order for 5 Forklift Model V00 ($24,500/unit, $122,500 total) at Plant 1710. "
                "Priority customer commitment to US Customers with delivery in 10 days. BOM requires "
                "Fork-Seat Assembly (SF-FL-FORK-SEAT, $890), combustion engine, electric drive, tires, "
                "and counterweight components. All components verified available. Setup time 4h on Assembly Line 1 "
                "followed by 16h run time (3.2h per unit). Moving to position 1 in sequence — "
                "displaces FG226 batch which has 5 more days of slack."
            ),
            "urgency_at_time": 0.85,
        },
        # Standard bike batch at 1710
        {
            "production_order_id": f"MO-1710-{uid()}",
            "product_id": "MZ-FG-C900",
            "site_id": "1710",
            "planned_qty": 20,
            "decision_type": "release",
            "sequence_position": 3,
            "priority_override": None,
            "resource_id": "BIKE-ASSEMBLY",
            "setup_time_hours": 1.5,
            "run_time_hours": 10.0,
            "confidence": 0.90,
            "reason": "mrp_planned",
            "decision_reasoning": (
                "Release MO for 20 Cruise Bike C900 ($980/unit, $19,600 batch) at Plant 1710. "
                "MRP-planned order based on 18 units/week demand from US and Americas Customers. "
                "BOM: frame, handlebar, seat, 2x wheels, fork, brakes, drivetrain (7 RM components). "
                "All materials available. Sequenced at position 3 on Bike Assembly — after Racing Bike "
                "R100 batch (position 1) and Mountain Bike M500 (position 2) to minimize changeover. "
                "Standard priority, on-time delivery projected."
            ),
            "urgency_at_time": 0.42,
        },
        # Deferred robotics order at 1710
        {
            "production_order_id": f"MO-1710-{uid()}",
            "product_id": "AVC_RBT_ROBOT",
            "site_id": "1710",
            "planned_qty": 8,
            "decision_type": "defer",
            "sequence_position": None,
            "priority_override": None,
            "resource_id": "ROBOTICS-CELL",
            "setup_time_hours": 6.0,
            "run_time_hours": 32.0,
            "confidence": 0.55,
            "reason": "component_shortage",
            "decision_reasoning": (
                "DEFER manufacturing of 8 Robotics Assembly units ($8,750/unit, $70,000 batch) at Plant 1710. "
                "Component shortage: AVC_RBT_LINK_ARM has 2 units on hand vs. 8 required. "
                "Supplier PO placed but lead time is 14 days. Deferring MO start by 10 days to align with "
                "component arrival. Confidence 0.55 due to specialty supplier variability. "
                "Setup on Robotics Cell requires 6h for fixtures and calibration. "
                "Asia Customers order (SO for 4 units) will be partially fulfilled from existing stock."
            ),
            "urgency_at_time": 0.70,
        },
        # Standard production at Plant 1720
        {
            "production_order_id": f"MO-1720-{uid()}",
            "product_id": "FG111",
            "site_id": "1720",
            "planned_qty": 400,
            "decision_type": "release",
            "sequence_position": 1,
            "priority_override": None,
            "resource_id": "PROD-LINE-A",
            "setup_time_hours": 2.0,
            "run_time_hours": 20.0,
            "confidence": 0.94,
            "reason": "mrp_planned",
            "decision_reasoning": (
                "Release MO for 400 units of Finished Good 111 ($45/unit, $18,000 batch) at Plant 1720 (Dallas). "
                "Covers 2-week demand (200/week) for US Customers. All raw materials available. "
                "Production Line A — 2h setup, 20h run at 20 units/hour. Standard MRP-planned order, "
                "no constraints. Plant 1720 currently at 65% utilization."
            ),
            "urgency_at_time": 0.22,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_mo_decisions
            (config_id, production_order_id, product_id, site_id, planned_qty,
             decision_type, sequence_position, priority_override, resource_id,
             setup_time_hours, run_time_hours, confidence, reason,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :production_order_id, :product_id, :site_id, :planned_qty,
                    :decision_type, :sequence_position, :priority_override, :resource_id,
                    :setup_time_hours, :run_time_hours, :confidence, :reason,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "BUILD",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(0.5, 24)),
        })
    print(f"    {len(decisions)} MO decisions created")


def seed_to_decisions(db):
    """Transfer order decisions between plants and from suppliers."""
    print("  Seeding TO decisions...")
    decisions = [
        {
            "transfer_order_id": f"TO-{uid()}",
            "product_id": "FG226",
            "source_site_id": "1720",
            "dest_site_id": "1710",
            "planned_qty": 60,
            "decision_type": "release",
            "transportation_mode": "truck",
            "estimated_transit_days": 3.0,
            "priority": 2,
            "trigger_reason": "rebalancing",
            "confidence": 0.87,
            "decision_reasoning": (
                "Transfer 60 units of Finished Good 226 ($320/unit, $19,200 value) from Plant 1720 (Dallas) "
                "to Plant 1710 (Palo Alto). Plant 1720 has 14 days of supply vs Plant 1710's 3 days. "
                "US Customers demand is concentrated at Plant 1710. Truck transit 3 days via SUPPLY_US lane. "
                "Rebalancing will equalize days-of-supply across both plants to ~8.5 days each."
            ),
            "urgency_at_time": 0.58,
        },
        {
            "transfer_order_id": f"TO-{uid()}",
            "product_id": "SG23",
            "source_site_id": "1720",
            "dest_site_id": "1710",
            "planned_qty": 3000,
            "decision_type": "consolidate",
            "transportation_mode": "truck",
            "estimated_transit_days": 2.0,
            "priority": 4,
            "trigger_reason": "mrp_planned",
            "confidence": 0.93,
            "decision_reasoning": (
                "Consolidate transfer of 3,000 Semi-Finished 23 ($0.59/unit, $1,770 value) with pending "
                "FG226 shipment from Plant 1720 → Plant 1710 to save $450 in freight. "
                "MRP-planned transfer, non-urgent. Both items fit within truck capacity of 10,000 units. "
                "Produced by Domestic US Subcontractor A at Plant 1720."
            ),
            "urgency_at_time": 0.18,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_to_decisions
            (config_id, transfer_order_id, product_id, source_site_id, dest_site_id,
             planned_qty, decision_type, transportation_mode, estimated_transit_days,
             priority, trigger_reason, confidence,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :transfer_order_id, :product_id, :source_site_id, :dest_site_id,
                    :planned_qty, :decision_type, :transportation_mode, :estimated_transit_days,
                    :priority, :trigger_reason, :confidence,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "BUILD",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(1, 20)),
        })
    print(f"    {len(decisions)} TO decisions created")


def seed_rebalance_decisions(db):
    print("  Seeding rebalance decisions...")
    decisions = [
        {
            "product_id": "TG14",
            "from_site": "1720",
            "to_site": "1710",
            "recommended_qty": 200,
            "reason": "demand_shift",
            "urgency": 0.72,
            "confidence": 0.80,
            "source_dos_before": 18.5,
            "source_dos_after": 11.2,
            "dest_dos_before": 3.1,
            "dest_dos_after": 9.8,
            "expected_cost": 850.0,
            "decision_reasoning": (
                "Rebalance 200 units of Trading Good 14 ($35/unit) from Plant 1720 → Plant 1710. "
                "Plant 1710 down to 3.1 days of supply while Plant 1720 has 18.5 days. "
                "Demand shift: US Customers orders for TG14 surged 40% this week at Plant 1710 (180→252/week). "
                "Transfer cost $850 (freight). Post-transfer: 1710 at 9.8 DOS, 1720 at 11.2 DOS. "
                "Net benefit: avoids $2,100 in potential stockout cost at Plant 1710."
            ),
            "urgency_at_time": 0.72,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_rebalance_decisions
            (config_id, product_id, from_site, to_site, recommended_qty, reason,
             urgency, confidence, source_dos_before, source_dos_after,
             dest_dos_before, dest_dos_after, expected_cost,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :product_id, :from_site, :to_site, :recommended_qty, :reason,
                    :urgency, :confidence, :source_dos_before, :source_dos_after,
                    :dest_dos_before, :dest_dos_after, :expected_cost,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "ASSESS",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(2, 16)),
        })
    print(f"    {len(decisions)} rebalance decisions created")


def seed_order_exceptions(db):
    print("  Seeding order exceptions...")
    decisions = [
        {
            "order_id": f"PO-EXT-{uid()}",
            "order_type": "purchase_order",
            "order_status": "overdue",
            "exception_type": "late_delivery",
            "severity": "high",
            "recommended_action": "expedite",
            "description": (
                "PO for 50 Pump Motor KE ($520.95/unit) from Domestic US Supplier 1 is 3 days overdue. "
                "Original delivery date was " + (TODAY - timedelta(days=3)).isoformat() + ". "
                "These motors are critical for Forklift Model V00 assembly at Plant 1710."
            ),
            "impact_assessment": (
                "Without these motors, 5 forklift units ($122,500 revenue) cannot complete assembly. "
                "Plant 1710 Assembly Line 1 will idle for 2 shifts if not received within 48 hours."
            ),
            "estimated_impact_cost": 8500.0,
            "confidence": 0.90,
            "reason": "supplier_delay",
            "decision_reasoning": (
                "OVERDUE: PO from Domestic US Supplier 1 for 50 Pump Motor KE units is 3 days late. "
                "Supplier contacted — shipment delayed due to freight consolidation at carrier. "
                "Recommending expedite action: switch to express carrier ($1,200 premium) to receive "
                "within 24 hours. Alternative: partial shipment of 25 units available for pickup today. "
                "Impact: 5 Forklift V00 units ($122,500) at risk. Assembly Line 1 has 48h of buffer work."
            ),
            "urgency_at_time": 0.91,
        },
        {
            "order_id": f"SO-1710-{uid()}",
            "order_type": "sales_order",
            "order_status": "at_risk",
            "exception_type": "quantity_mismatch",
            "severity": "medium",
            "recommended_action": "partial_ship",
            "description": (
                "Sales order for 25 Quality Mat 001 (QM001) from Americas Customers. "
                "Only 18 units available at Plant 1710, 7 unit shortfall."
            ),
            "impact_assessment": (
                "Partial shipment of 18/25 units covers 72% of order. "
                "Remaining 7 units available from Plant 1720 in 3 days."
            ),
            "estimated_impact_cost": 245.0,
            "confidence": 0.86,
            "reason": "inventory_gap",
            "decision_reasoning": (
                "Sales order for 25 QM001 ($35/unit, $875 total) from Americas Customers. "
                "Plant 1710 has 18 units; shortfall of 7. Recommending partial shipment of 18 units now "
                "plus cross-plant transfer of 7 from Plant 1720 (Dallas) — 3-day transit. "
                "Customer relationship: Americas Customers, mid-priority account. "
                "Impact of full delay ($245 in backorder costs) exceeds express transfer cost ($120)."
            ),
            "urgency_at_time": 0.60,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_order_exceptions
            (config_id, order_id, order_type, order_status, exception_type,
             severity, recommended_action, description, impact_assessment,
             estimated_impact_cost, confidence, reason,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :order_id, :order_type, :order_status, :exception_type,
                    :severity, :recommended_action, :description, :impact_assessment,
                    :estimated_impact_cost, :confidence, :reason,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "SENSE",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(1, 8)),
        })
    print(f"    {len(decisions)} order exceptions created")


def seed_forecast_adjustment_decisions(db):
    print("  Seeding forecast adjustment decisions...")
    decisions = [
        {
            "product_id": "MZ-FG-R100",
            "site_id": "1710",
            "signal_source": "email",
            "signal_type": "demand_increase",
            "signal_text": "Key European distributor indicates 30% volume increase for Q2 racing bike orders",
            "signal_confidence": 0.75,
            "current_forecast_value": 8.0,
            "adjustment_direction": "up",
            "adjustment_magnitude": 2.4,
            "adjustment_pct": 30.0,
            "adjusted_forecast_value": 10.4,
            "time_horizon_periods": 8,
            "reason": "Europe Customers distributor signaled 30% demand uplift for Racing Bike R100 in Q2",
            "confidence": 0.72,
            "decision_reasoning": (
                "Email signal from Europe Customers distributor reports 30% volume increase for Racing Bike R100 "
                "in Q2 2026. Current weekly forecast is 8 units at Plant 1710. Adjusting to 10.4 units/week "
                "for the next 8 periods. Signal confidence 0.75 (verified distributor, specific SKU reference). "
                "Impact: +$6,720/week additional revenue potential ($2,800/unit × 2.4 extra units). "
                "Triggers cascade: PO for Racing Frames (MZ-RM-FRAME-R) and Racing Wheels (MZ-RM-WHEEL-R) "
                "need proportional increase. BOM requires 1 frame + 2 wheels per bike."
            ),
            "urgency_at_time": 0.68,
        },
        {
            "product_id": "FG111",
            "site_id": "1720",
            "signal_source": "market_intelligence",
            "signal_type": "demand_decrease",
            "signal_text": "Industry report: sector slowdown expected in Southwest US region for basic goods",
            "signal_confidence": 0.55,
            "current_forecast_value": 200.0,
            "adjustment_direction": "down",
            "adjustment_magnitude": 20.0,
            "adjustment_pct": 10.0,
            "adjusted_forecast_value": 180.0,
            "time_horizon_periods": 4,
            "reason": "Industry report signals 10% demand softening for basic finished goods in US Southwest",
            "confidence": 0.52,
            "decision_reasoning": (
                "Market intelligence report indicates 10% sector slowdown in US Southwest for basic manufactured goods. "
                "FG111 weekly forecast at Plant 1720 (Dallas): 200 → 180 units for next 4 weeks. "
                "Signal confidence is moderate (0.55) — industry-level report, not customer-specific. "
                "Conservative 10% reduction recommended rather than full 15% industry estimate. "
                "Impact: $900/week reduction in planned revenue ($45/unit × 20 units). "
                "Downstream: reduces RM demand proportionally, no PO cancellation needed — "
                "existing pipeline absorbs with slightly higher inventory for 2 weeks."
            ),
            "urgency_at_time": 0.35,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_forecast_adjustment_decisions
            (config_id, product_id, site_id, signal_source, signal_type, signal_text,
             signal_confidence, current_forecast_value, adjustment_direction,
             adjustment_magnitude, adjustment_pct, adjusted_forecast_value,
             time_horizon_periods, reason, confidence,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :product_id, :site_id, :signal_source, :signal_type, :signal_text,
                    :signal_confidence, :current_forecast_value, :adjustment_direction,
                    :adjustment_magnitude, :adjustment_pct, :adjusted_forecast_value,
                    :time_horizon_periods, :reason, :confidence,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "SENSE",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(2, 24)),
        })
    print(f"    {len(decisions)} forecast adjustment decisions created")


def seed_quality_decisions(db):
    print("  Seeding quality decisions...")
    decisions = [
        {
            "quality_order_id": f"QO-{uid()}",
            "product_id": "MZ-RM-FRAME-R",
            "site_id": "1710",
            "lot_number": f"LOT-FRAME-{uid()}",
            "inspection_type": "incoming",
            "inspection_qty": 20.0,
            "defect_rate": 0.10,
            "defect_category": "dimensional_tolerance",
            "severity_level": "medium",
            "disposition": "rework",
            "disposition_reason": (
                "2 of 20 Racing Frames (MZ-RM-FRAME-R) from EV Parts Inc. failed dimensional tolerance check "
                "on headtube angle (±0.3° spec, measured ±0.8°). Defective frames can be reworked by re-machining "
                "the headtube — estimated $45/unit vs. $285 replacement cost. Non-safety-critical dimension "
                "for cruise use but required for racing specification. Rework recommended over scrap."
            ),
            "rework_cost_estimate": 90.0,
            "scrap_cost_estimate": 570.0,
            "service_risk_if_accepted": 0.15,
            "confidence": 0.84,
            "decision_reasoning": (
                "Incoming inspection of 20 Racing Frames from supplier: 2 units (10% defect rate) failed "
                "headtube angle tolerance. Dimensional defect — reworkable by re-machining at Plant 1710 "
                "machine shop. Rework cost $90 (2×$45) vs. scrap cost $570 (2×$285). "
                "18 good frames released to production immediately. 2 frames sent to rework queue, "
                "estimated 4-hour turnaround. Racing Bike R100 production schedule not impacted — "
                "18 frames cover this week's demand of 8 bikes with 10 surplus."
            ),
            "urgency_at_time": 0.55,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_quality_decisions
            (config_id, quality_order_id, product_id, site_id, lot_number,
             inspection_type, inspection_qty, defect_rate, defect_category, severity_level,
             disposition, disposition_reason, rework_cost_estimate, scrap_cost_estimate,
             service_risk_if_accepted, confidence,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :quality_order_id, :product_id, :site_id, :lot_number,
                    :inspection_type, :inspection_qty, :defect_rate, :defect_category, :severity_level,
                    :disposition, :disposition_reason, :rework_cost_estimate, :scrap_cost_estimate,
                    :service_risk_if_accepted, :confidence,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "ASSESS",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(4, 36)),
        })
    print(f"    {len(decisions)} quality decisions created")


def seed_maintenance_decisions(db):
    print("  Seeding maintenance decisions...")
    decisions = [
        {
            "maintenance_order_id": f"PM-{uid()}",
            "asset_id": "ASSEMBLY-LINE-1",
            "site_id": "1710",
            "maintenance_type": "preventive",
            "decision_type": "defer",
            "scheduled_date": TODAY + timedelta(days=2),
            "deferred_to_date": TODAY + timedelta(days=9),
            "estimated_downtime_hours": 8.0,
            "production_impact_units": 40.0,
            "spare_parts_available": True,
            "priority": 3,
            "risk_score_if_deferred": 0.12,
            "confidence": 0.88,
            "reason": "production_priority",
            "decision_reasoning": (
                "Defer preventive maintenance on Assembly Line 1 at Plant 1710 from "
                f"{(TODAY + timedelta(days=2)).isoformat()} to {(TODAY + timedelta(days=9)).isoformat()}. "
                "Current production priority: 5 Forklift V00 ($122,500) expedited for US Customers. "
                "PM requires 8-hour shutdown — would idle 40 units of FG production. "
                "Risk score if deferred: 0.12 (low) — last PM was 6 weeks ago, equipment health index at 92%. "
                "Spare parts for PM are available in stores. Recommended window: next Saturday (non-production day)."
            ),
            "urgency_at_time": 0.30,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_maintenance_decisions
            (config_id, maintenance_order_id, asset_id, site_id, maintenance_type,
             decision_type, scheduled_date, deferred_to_date, estimated_downtime_hours,
             production_impact_units, spare_parts_available, priority, risk_score_if_deferred,
             confidence, reason,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :maintenance_order_id, :asset_id, :site_id, :maintenance_type,
                    :decision_type, :scheduled_date, :deferred_to_date, :estimated_downtime_hours,
                    :production_impact_units, :spare_parts_available, :priority, :risk_score_if_deferred,
                    :confidence, :reason,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "cycle_phase": "BUILD",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(6, 48)),
        })
    print(f"    {len(decisions)} maintenance decisions created")


def seed_subcontracting_decisions(db):
    print("  Seeding subcontracting decisions...")
    decisions = [
        {
            "product_id": "SG23",
            "site_id": "1710",
            "subcontractor_id": "0017300007",
            "planned_qty": 5000,
            "decision_type": "route_external",
            "reason": "capacity_constraint",
            "internal_capacity_pct": 95.0,
            "subcontractor_lead_time_days": 5.0,
            "subcontractor_cost_per_unit": 0.72,
            "internal_cost_per_unit": 0.59,
            "quality_score": 0.96,
            "on_time_score": 0.91,
            "confidence": 0.78,
            "decision_reasoning": (
                "Route 5,000 units of Semi-Finished 23 ($0.59 internal / $0.72 subcontracted) to "
                "Domestic US Subcontractor A. Plant 1710 at 95% capacity — insufficient capacity for "
                "this batch alongside priority FG production. Cost premium: $0.13/unit × 5,000 = $650 total. "
                "Subcontractor A quality score 96%, on-time 91%. 5-day turnaround. "
                "Alternative: defer internal production 2 weeks (unacceptable — downstream SG23 feeds "
                "multiple FG BOMs). External routing is $650 cheaper than the $2,400 opportunity cost of deferral."
            ),
            "urgency_at_time": 0.62,
        },
    ]

    for d in decisions:
        db.execute(text("""
            INSERT INTO powell_subcontracting_decisions
            (config_id, product_id, site_id, subcontractor_id, planned_qty,
             required_qty, routing_decision, decision_type, reason, internal_capacity_pct,
             subcontractor_lead_time_days, subcontractor_cost_per_unit,
             internal_cost_per_unit, quality_score, on_time_score, confidence,
             decision_reasoning, urgency_at_time, cycle_phase, cycle_id, created_at)
            VALUES (:config_id, :product_id, :site_id, :subcontractor_id, :planned_qty,
                    :required_qty, :routing_decision, :decision_type, :reason, :internal_capacity_pct,
                    :subcontractor_lead_time_days, :subcontractor_cost_per_unit,
                    :internal_cost_per_unit, :quality_score, :on_time_score, :confidence,
                    :decision_reasoning, :urgency_at_time, :cycle_phase, :cycle_id, :created_at)
        """), {
            **d,
            "config_id": CONFIG_ID,
            "required_qty": d["planned_qty"],
            "routing_decision": d["decision_type"],
            "cycle_phase": "BUILD",
            "cycle_id": uid(),
            "created_at": NOW - timedelta(hours=random.uniform(3, 24)),
        })
    print(f"    {len(decisions)} subcontracting decisions created")


def seed_sop_worklist(db):
    """S&OP worklist items with real product/site references."""
    print("  Seeding S&OP worklist items...")
    items = [
        {
            "item_code": "SOP-CAP-001",
            "item_name": "Plant 1710 Assembly Line 1 Capacity Breach",
            "category": "Capacity Planning",
            "issue_type": "CAPACITY",
            "issue_summary": (
                "Assembly Line 1 at Plant 1710 (Palo Alto) projected at 112% utilization in weeks 3-5. "
                "Concurrent orders: 5 Forklift V00 (expedited), 20 Cruise Bike C900, 8 Robotics Assembly. "
                "Total setup time 11.5h + 58h run time exceeds 50h available weekly capacity."
            ),
            "impact_value": -122500.0,
            "impact_description": "Revenue at risk: $122,500 forklift order plus $19,600 bike batch if capacity not resolved",
            "impact_type": "negative",
            "due_description": "48 hours",
            "urgency": "URGENT",
            "agent_recommendation": (
                "Option A: Defer Cruise Bike C900 batch by 1 week (5 days slack available). "
                "Option B: Route 3 Forklift V00 to Plant 1720 (Dallas has 35% spare capacity). "
                "Option C: Approve overtime (8h Saturday shift, $2,400 cost). "
                "Recommended: Option A — lowest cost, no customer impact (C900 has 5-day buffer)."
            ),
            "agent_reasoning": (
                "Glenday Sieve analysis: Forklift V00 is a Green category item (top 6% of revenue, "
                "highest priority). Racing Bike R100 is also Green. Cruise Bike C900 is Yellow — "
                "deferral has lowest customer impact. Plant 1720 transfer incurs $3,200 logistics cost."
            ),
            "status": "INFORMED",
        },
        {
            "item_code": "SOP-PORT-001",
            "item_name": "Racing Bike R100 Demand Uplift — BOM Component Review",
            "category": "Portfolio Review",
            "issue_type": "PORTFOLIO",
            "issue_summary": (
                "Europe Customers distributor signals 30% demand increase for Racing Bike R100 in Q2. "
                "Current weekly forecast: 8 units. Proposed: 10.4 units/week for 8 weeks. "
                "BOM cascade: need +19 Racing Frames, +38 Racing Wheels, +19 each of 5 other components."
            ),
            "impact_value": 53760.0,
            "impact_description": "Potential revenue gain: $53,760 over 8 weeks (+2.4 units × $2,800 × 8 weeks)",
            "impact_type": "positive",
            "due_description": "Friday",
            "urgency": "STANDARD",
            "agent_recommendation": (
                "Accept forecast uplift and trigger component POs immediately. "
                "Racing Frame (MZ-RM-FRAME-R) has 12-day lead time — PO must be placed by EOD Thursday "
                "to avoid assembly gap in week 3. Racing Wheels (MZ-RM-WHEEL-R) have 7-day lead time, less critical."
            ),
            "agent_reasoning": (
                "Racing Bike R100 is the highest-margin product in the bike family ($2,800 vs $1,450 Mountain, "
                "$980 Cruise). Europe Customers account for 35% of R100 volume. Signal confidence 0.75 "
                "(specific SKU, verified distributor). Downside risk of overstock: $5,700 in frame inventory "
                "if demand doesn't materialize — acceptable vs. $53,760 upside."
            ),
            "status": "INFORMED",
        },
        {
            "item_code": "SOP-RISK-001",
            "item_name": "Robotics Component Sole-Source Risk",
            "category": "Supply Risk",
            "issue_type": "CAPACITY",
            "issue_summary": (
                "AVC_RBT_LINK_ARM component for Robotics Assembly is sole-sourced with 14-day lead time. "
                "Current stock: 2 units. Open PO: 0. Asia Customers order for 4 units cannot be fully fulfilled. "
                "No qualified alternate supplier."
            ),
            "impact_value": -35000.0,
            "impact_description": "Revenue at risk: $35,000 (4 Robotics Assembly × $8,750). Supplier concentration = 100%",
            "impact_type": "negative",
            "due_description": "EOD",
            "urgency": "URGENT",
            "agent_recommendation": (
                "Immediate: Place emergency PO for 10 link arms (covers order + safety buffer). "
                "Medium-term: Qualify second supplier within 60 days. "
                "Strategic: Evaluate BOM redesign to use more common arm linkage across AVC_RBT product family."
            ),
            "agent_reasoning": (
                "Supplier concentration risk is 100% for a $8,750/unit finished good. "
                "Conformal prediction interval for supplier lead time is wide: [10, 21] days at 90% coverage. "
                "Each day of delay costs $1,250 in opportunity cost (forfeited margin on 1 unit/week demand)."
            ),
            "status": "INFORMED",
        },
        {
            "item_code": "SOP-INV-001",
            "item_name": "Trading Goods Inventory Imbalance Across Plants",
            "category": "Inventory Optimization",
            "issue_type": "PORTFOLIO",
            "issue_summary": (
                "Trading Good 14 (TG14, $35/unit): Plant 1720 has 18.5 DOS vs Plant 1710 at 3.1 DOS. "
                "Similar pattern for TG10 and TG25. Demand is shifting to Plant 1710 (US Customers) "
                "but replenishment still routed to Plant 1720."
            ),
            "impact_value": -2100.0,
            "impact_description": "Projected stockout cost at Plant 1710: $2,100/week if imbalance persists",
            "impact_type": "trade-off",
            "due_description": "This week",
            "urgency": "STANDARD",
            "agent_recommendation": (
                "Execute rebalancing transfer: 200 TG14 units from Plant 1720 → Plant 1710 (3-day transit, $850 freight). "
                "Update sourcing rules: redirect 60% of TG14 supplier deliveries to Plant 1710. "
                "Review all trading goods sourcing split across plants."
            ),
            "agent_reasoning": (
                "Rebalancing cost $850 vs. stockout cost $2,100/week. ROI positive within 3 days. "
                "Root cause: sourcing rules still reflect pre-demand-shift configuration where Plant 1720 "
                "served the majority of US West Coast customers. Since Q1, US Customers demand at Plant 1710 "
                "has increased 40% for trading goods."
            ),
            "status": "INFORMED",
        },
    ]

    for item in items:
        db.execute(text("""
            INSERT INTO sop_worklist_items
            (tenant_id, item_code, item_name, category, issue_type, issue_summary,
             impact_value, impact_description, impact_type, due_description,
             urgency, agent_recommendation, agent_reasoning, status, created_at)
            VALUES (:tenant_id, :item_code, :item_name, :category, :issue_type, :issue_summary,
                    :impact_value, :impact_description, :impact_type, :due_description,
                    :urgency, :agent_recommendation, :agent_reasoning, :status, :created_at)
        """), {
            **item,
            "tenant_id": TENANT_ID,
            "created_at": NOW - timedelta(hours=random.uniform(1, 12)),
        })
    print(f"    {len(items)} S&OP worklist items created")


def seed_mps_plan(db):
    """MPS plan with realistic weekly quantities for key finished goods."""
    print("  Seeding MPS plan...")

    # Create the plan
    db.execute(text("""
        INSERT INTO mps_plans
        (name, description, supply_chain_config_id, planning_horizon_weeks,
         bucket_size_days, start_date, end_date, status, created_at, updated_at)
        VALUES (:name, :desc, :config_id, :horizon, :bucket, :start, :end, :status, :now, :now)
    """), {
        "name": "MPS Week 11-23 2026 — Company Code 1710",
        "desc": (
            "Master Production Schedule for Plant 1710 and Plant 1720, weeks 11-23 (March-June 2026). "
            "Covers 10 key finished goods and trading goods across US, Americas, Europe, and Asia demand regions. "
            "Incorporates Racing Bike R100 demand uplift (+30%) and FG111 demand softening (-10%)."
        ),
        "config_id": CONFIG_ID,
        "horizon": 13,
        "bucket": 7,
        "start": TODAY,
        "end": TODAY + timedelta(weeks=13),
        "status": "DRAFT",
        "now": NOW,
    })

    # Get the plan ID
    plan_id = db.execute(text(
        "SELECT id FROM mps_plans WHERE supply_chain_config_id = :cid ORDER BY id DESC LIMIT 1"
    ), {"cid": CONFIG_ID}).scalar()

    # Weekly quantities per product — 13 weeks
    # product.id uses CFG74_ prefix for config 74; site IDs: 429=Plant 1710, 430=Plant 1720
    plan_items = [
        ("CFG74_FG111",         429, [200]*2 + [180]*4 + [200]*7),   # softening then recovery
        ("CFG74_FG126",         429, [120]*13),
        ("CFG74_FG129",         429, [15, 15, 18, 18, 20, 20, 15, 15, 15, 18, 18, 15, 15]),
        ("CFG74_FG226",         429, [42]*13),
        ("CFG74_MZ-FG-R100",    429, [8, 8, 10, 10, 10, 12, 12, 10, 10, 10, 8, 8, 8]),  # demand uplift
        ("CFG74_MZ-FG-M500",    429, [12]*13),
        ("CFG74_MZ-FG-C900",    429, [18, 18, 20, 20, 18, 18, 20, 20, 18, 18, 18, 20, 20]),
        ("CFG74_FG-FL-MV-V00",  429, [3, 3, 5, 5, 3, 3, 5, 3, 3, 5, 3, 3, 3]),  # lumpy forklift demand
        ("CFG74_AVC_RBT_ROBOT", 429, [5, 5, 5, 8, 8, 5, 5, 5, 8, 5, 5, 5, 5]),  # robotics batches
        ("CFG74_TG10",          429, [350]*13),
        ("CFG74_FG111",         430, [200]*2 + [180]*4 + [200]*7),   # Plant 1720 mirror
        ("CFG74_FG202",         430, [85]*13),
    ]

    import json
    for product_id, site_id, quantities in plan_items:
        db.execute(text("""
            INSERT INTO mps_plan_items
            (plan_id, product_id, site_id, weekly_quantities, created_at, updated_at)
            VALUES (:plan_id, :product_id, :site_id, :weekly_quantities, :now, :now)
        """), {
            "plan_id": plan_id,
            "product_id": product_id,
            "site_id": site_id,
            "weekly_quantities": json.dumps(quantities),
            "now": NOW,
        })
    print(f"    MPS plan created with {len(plan_items)} line items")


def seed_executive_briefing(db):
    """Executive briefing with realistic narrative drawn from all seeded data."""
    print("  Seeding executive briefing...")

    narrative = f"""# Executive Strategy Briefing — Company Code 1710 SC Network
## {TODAY.strftime('%B %d, %Y')}

### Network Overview
The Company Code 1710 supply chain operates across 2 manufacturing plants (Plant 1710 in Palo Alto, Plant 1720 in Dallas), 8 supplier regions, and 7 customer demand regions spanning US, Americas, Europe, Asia, NZ, AU, and ZA. The network manages 609 products across finished goods (132), semi-finished (113), raw materials (181), and trading goods (53).

---

### Critical Issues Requiring Attention

**1. Plant 1710 Capacity Breach (URGENT)**
Assembly Line 1 at Plant 1710 is projected at 112% utilization over the next 3 weeks due to concurrent orders: 5 Forklift Model V00 (expedited, $122,500), 20 Cruise Bike C900, and 8 Robotics Assembly units. Recommended action: defer Cruise Bike C900 batch by 1 week — this product has 5 days of delivery slack and is lower priority than the forklift and robotics orders.

**2. Robotics Component Sole-Source Risk (URGENT)**
The AVC_RBT_LINK_ARM component for the $8,750 Robotics Assembly is sole-sourced with only 2 units in stock and a 14-day supplier lead time. Asia Customers order for 4 units ($35,000 revenue) is at risk. Emergency PO recommended immediately, with medium-term action to qualify a second supplier.

**3. Pump Motor KE Delivery Overdue (HIGH)**
Purchase order for 50 Pump Motor KE units ($520.95/unit) from Domestic US Supplier 1 is 3 days overdue. These motors are critical for the expedited Forklift V00 production. Recommended: switch to express carrier at $1,200 premium to receive within 24 hours.

---

### Demand Signals & Forecast Adjustments

| Product | Signal | Direction | Magnitude | Confidence |
|---------|--------|-----------|-----------|------------|
| Racing Bike R100 | Europe distributor email | +30% | 8→10.4 units/week | 0.72 |
| Finished Good 111 | Industry slowdown report | -10% | 200→180 units/week | 0.52 |

The Racing Bike R100 uplift represents $53,760 in potential Q2 revenue. BOM cascade requires immediate POs for Racing Frames (MZ-RM-FRAME-R, 12-day lead time) and Racing Wheels (MZ-RM-WHEEL-R, 7-day lead time). The FG111 softening at Plant 1720 is conservative at -10% with moderate confidence — monitoring recommended before further adjustment.

---

### Decision Stream Summary (Last 24 Hours)

| Decision Type | Count | Avg Confidence | Avg Urgency | Key Actions |
|--------------|-------|---------------|-------------|-------------|
| ATP Fulfillment | 5 | 0.80 | 0.62 | 2 partial fulfillments, 3 full promises |
| Purchase Orders | 4 | 0.83 | 0.57 | 1 critical (RM129), 1 standard, 1 opportunistic, 1 specialty |
| Manufacturing | 4 | 0.81 | 0.55 | 1 expedite (forklift), 2 releases, 1 deferral (robotics) |
| Transfer Orders | 2 | 0.90 | 0.38 | 1 rebalancing, 1 consolidation |
| Order Exceptions | 2 | 0.88 | 0.76 | 1 overdue PO (Pump Motor), 1 quantity mismatch (QM001) |
| Forecast Adj. | 2 | 0.62 | 0.52 | 1 uplift (R100), 1 reduction (FG111) |
| Quality | 1 | 0.84 | 0.55 | Racing Frame rework (2 of 20 units, $90 rework vs $570 scrap) |
| Maintenance | 1 | 0.88 | 0.30 | PM deferral on Assembly Line 1 (production priority) |
| Subcontracting | 1 | 0.78 | 0.62 | Route SG23 to Subcontractor A (capacity constraint) |

**High-urgency decisions (>0.80):** Robotics Assembly ATP shortfall, RM129 stockout prevention, Pump Motor overdue exception.
**Low-confidence decisions (<0.60):** Robotics Assembly ATP (0.45 — component uncertainty), FG111 forecast reduction (0.52 — industry-level signal).

---

### Plant Utilization

| Plant | Location | Current Utilization | Trend |
|-------|----------|-------------------|-------|
| 1710 | Palo Alto | 87% (projected 112% wk 3-5) | Increasing — forklift + bike demand |
| 1720 | Dallas | 65% | Stable — FG111 softening offset by TG growth |

**Recommendation:** Evaluate shifting 2-3 Forklift V00 units to Plant 1720 to relieve Plant 1710 pressure. Plant 1720 has 35% spare capacity and the necessary tooling for forklift assembly.

---

### Inventory Health

| Metric | Plant 1710 | Plant 1720 |
|--------|-----------|-----------|
| Products below safety stock | 8 | 3 |
| Average days of supply | 6.2 | 12.4 |
| Trading goods DOS imbalance | TG14: 3.1 DOS | TG14: 18.5 DOS |

Rebalancing recommended for Trading Goods (TG14, TG10, TG25) — demand has shifted to Plant 1710 but sourcing rules still favor Plant 1720. Cost of rebalancing transfer: $850 vs. projected weekly stockout cost of $2,100.

---

### Key Metrics (Period Ending {TODAY.strftime('%B %d, %Y')})

| KPI | Value | Target | Status |
|-----|-------|--------|--------|
| OTIF (On Time In Full) | 88.2% | 95% | Below target |
| Revenue at risk | $192,500 | <$50K | Elevated |
| Active decisions pending | 22 | — | Normal |
| Agent confidence (avg) | 0.79 | >0.75 | On target |
| Supplier on-time rate | 91% | 95% | Slightly below |

---

### Recommendations for S&OP Review

1. **Approve** Cruise Bike C900 deferral (1 week) to resolve Plant 1710 capacity breach
2. **Approve** Racing Bike R100 forecast uplift and trigger component POs immediately
3. **Escalate** Robotics sole-source risk to strategic sourcing for supplier qualification
4. **Monitor** FG111 demand softening — reassess in 2 weeks before adjusting Plant 1720 production
5. **Execute** Trading goods rebalancing transfer (Plant 1720 → Plant 1710)
"""

    executive_summary = (
        "Two urgent issues require immediate attention: Plant 1710 Assembly Line 1 faces a capacity breach "
        "at 112% utilization in weeks 3-5, and the Robotics Assembly component (AVC_RBT_LINK_ARM) is "
        "sole-sourced with only 2 units in stock against a 4-unit customer order. An overdue PO for "
        "Pump Motor KE from Domestic US Supplier 1 threatens $122,500 in forklift production. "
        "On the positive side, Europe Customers signal a 30% Racing Bike R100 demand uplift worth $53,760 in Q2 revenue. "
        "22 active decisions are pending across the decision stream with average agent confidence of 0.79."
    )

    import json
    recommendations = json.dumps([
        {"title": "Defer Cruise Bike C900 batch", "priority": 1, "impact": "Resolves 112% capacity breach at Plant 1710", "score": 0.92},
        {"title": "Accept Racing Bike R100 forecast uplift", "priority": 2, "impact": "+$53,760 Q2 revenue, trigger component POs", "score": 0.88},
        {"title": "Emergency PO for Robotics link arms", "priority": 1, "impact": "Protects $35,000 Asia Customers order", "score": 0.91},
        {"title": "Expedite Pump Motor KE delivery", "priority": 1, "impact": "Unblocks $122,500 forklift production", "score": 0.90},
        {"title": "Execute trading goods rebalancing", "priority": 3, "impact": "Saves $2,100/week in stockout costs for $850 freight", "score": 0.85},
        {"title": "Qualify second Robotics component supplier", "priority": 2, "impact": "Eliminates 100% concentration risk on $8,750 FG", "score": 0.82},
    ])

    data_pack = json.dumps({
        "network": {"plants": 2, "supplier_regions": 8, "customer_regions": 7, "products": 609},
        "utilization": {"1710": 0.87, "1720": 0.65},
        "decisions_24h": {"total": 22, "urgent": 5, "standard": 12, "low": 5},
        "revenue_at_risk": 192500,
        "otif": 0.882,
        "avg_confidence": 0.79,
        "supplier_otd": 0.91,
    })

    db.execute(text("""
        INSERT INTO executive_briefings
        (tenant_id, briefing_type, status, title, data_pack, narrative,
         recommendations, executive_summary, model_used, tokens_used,
         generation_time_ms, created_at, completed_at)
        VALUES (:tenant_id, :type, :status, :title, :data_pack, :narrative,
                :recs, :exec_summary, :model, :tokens, :gen_time, :now, :now)
    """), {
        "tenant_id": TENANT_ID,
        "type": "weekly",
        "status": "completed",
        "title": f"Weekly Strategy Briefing — Company Code 1710 — {TODAY.strftime('%B %d, %Y')}",
        "data_pack": data_pack,
        "narrative": narrative,
        "recs": recommendations,
        "exec_summary": executive_summary,
        "model": "claude-sonnet-4-6",
        "tokens": 4250,
        "gen_time": 8500,
        "now": NOW,
    })
    print("    Executive briefing created")


def main():
    print(f"\n{'='*70}")
    print(f"  Seeding Decision Stream & Executive Briefing for Config 74")
    print(f"  Tenant 20 — Company Code 1710 SC Network")
    print(f"{'='*70}\n")

    db = sync_session_factory()
    try:
        # Clear existing seeded decisions (keep the 57 buffer decisions from warm start)
        for tbl in [
            "powell_atp_decisions", "powell_po_decisions", "powell_mo_decisions",
            "powell_to_decisions", "powell_rebalance_decisions", "powell_order_exceptions",
            "powell_forecast_adjustment_decisions", "powell_quality_decisions",
            "powell_maintenance_decisions", "powell_subcontracting_decisions",
        ]:
            db.execute(text(f"DELETE FROM {tbl} WHERE config_id = :cid"), {"cid": CONFIG_ID})

        # Clear S&OP and MPS for this tenant/config
        db.execute(text("DELETE FROM sop_worklist_items WHERE tenant_id = :tid"), {"tid": TENANT_ID})
        db.execute(text("""
            DELETE FROM mps_plan_items WHERE plan_id IN
            (SELECT id FROM mps_plans WHERE supply_chain_config_id = :cid)
        """), {"cid": CONFIG_ID})
        db.execute(text("DELETE FROM mps_plans WHERE supply_chain_config_id = :cid"), {"cid": CONFIG_ID})
        db.execute(text("DELETE FROM executive_briefings WHERE tenant_id = :tid"), {"tid": TENANT_ID})

        db.commit()
        print("  Cleared existing data\n")

        seed_atp_decisions(db)
        seed_po_decisions(db)
        seed_mo_decisions(db)
        seed_to_decisions(db)
        seed_rebalance_decisions(db)
        seed_order_exceptions(db)
        seed_forecast_adjustment_decisions(db)
        seed_quality_decisions(db)
        seed_maintenance_decisions(db)
        seed_subcontracting_decisions(db)
        seed_sop_worklist(db)
        seed_mps_plan(db)
        seed_executive_briefing(db)

        db.commit()

        # Summary counts
        print(f"\n{'='*70}")
        print("  SUMMARY")
        print(f"{'='*70}")
        total = 0
        for tbl in [
            "powell_atp_decisions", "powell_po_decisions", "powell_mo_decisions",
            "powell_to_decisions", "powell_rebalance_decisions", "powell_order_exceptions",
            "powell_forecast_adjustment_decisions", "powell_quality_decisions",
            "powell_maintenance_decisions", "powell_subcontracting_decisions",
            "powell_buffer_decisions",
        ]:
            cnt = db.execute(text(f"SELECT count(*) FROM {tbl} WHERE config_id = :cid"), {"cid": CONFIG_ID}).scalar()
            total += cnt
            print(f"    {tbl:45s} {cnt:4d}")
        print(f"    {'TOTAL DECISIONS':45s} {total:4d}")

        sop_cnt = db.execute(text("SELECT count(*) FROM sop_worklist_items WHERE tenant_id = :tid"), {"tid": TENANT_ID}).scalar()
        mps_cnt = db.execute(text("SELECT count(*) FROM mps_plan_items WHERE plan_id IN (SELECT id FROM mps_plans WHERE supply_chain_config_id = :cid)"), {"cid": CONFIG_ID}).scalar()
        brief_cnt = db.execute(text("SELECT count(*) FROM executive_briefings WHERE tenant_id = :tid"), {"tid": TENANT_ID}).scalar()
        print(f"    {'sop_worklist_items':45s} {sop_cnt:4d}")
        print(f"    {'mps_plan_items':45s} {mps_cnt:4d}")
        print(f"    {'executive_briefings':45s} {brief_cnt:4d}")
        print(f"\n  Done!\n")

    except Exception as e:
        db.rollback()
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

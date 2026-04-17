#!/usr/bin/env python3
"""Seed TMS demo data for Food Dist tenant.

Populates: carriers, carrier-lanes, freight rates, TMS shipments, loads,
transportation plan + items, appointments, shipment exceptions, and
TMS-domain agent decisions. Idempotent — skips if carriers already exist.

Run:  docker exec autonomy-tms-backend-gpu python scripts/seed_tms_demo.py
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://autonomy_user:autonomy_password@autonomy-tms-db:5432/autonomy",
)
engine = create_engine(DATABASE_URL)

TENANT_ID = 1
CONFIG_ID = 2
NOW = datetime.utcnow()
TODAY = date.today()
random.seed(42)

CARRIERS = [
    {"code": "SNDR", "name": "Schneider National", "carrier_type": "ASSET", "scac": "SNDR", "mc_number": "MC-133655", "dot_number": "231027", "modes": ["FTL", "LTL", "INTERMODAL"], "equipment_types": ["DRY_VAN", "REEFER", "FLATBED"], "service_regions": ["US-WEST", "US-NATIONAL"]},
    {"code": "JBHT", "name": "J.B. Hunt Transport", "carrier_type": "ASSET", "scac": "JBHT", "mc_number": "MC-92485", "dot_number": "62205", "modes": ["FTL", "INTERMODAL", "DRAYAGE"], "equipment_types": ["DRY_VAN", "REEFER", "CONTAINER_40"], "service_regions": ["US-NATIONAL"]},
    {"code": "WERN", "name": "Werner Enterprises", "carrier_type": "ASSET", "scac": "WERN", "mc_number": "MC-153625", "dot_number": "91227", "modes": ["FTL", "LTL"], "equipment_types": ["DRY_VAN", "REEFER", "FLATBED"], "service_regions": ["US-WEST", "US-SW"]},
    {"code": "XPOL", "name": "XPO Logistics", "carrier_type": "THREE_PL", "scac": "CNWY", "mc_number": "MC-136561", "dot_number": "282914", "modes": ["LTL", "FTL"], "equipment_types": ["DRY_VAN", "REEFER"], "service_regions": ["US-NATIONAL"]},
    {"code": "ODFL", "name": "Old Dominion Freight Line", "carrier_type": "ASSET", "scac": "ODFL", "mc_number": "MC-76573", "dot_number": "66420", "modes": ["LTL"], "equipment_types": ["DRY_VAN"], "service_regions": ["US-NATIONAL"]},
    {"code": "FDXF", "name": "FedEx Freight", "carrier_type": "ASSET", "scac": "FXFE", "mc_number": "MC-349309", "dot_number": "1067081", "modes": ["LTL", "FTL"], "equipment_types": ["DRY_VAN", "REEFER"], "service_regions": ["US-NATIONAL"]},
    {"code": "USFC", "name": "US Foods Carrier Fleet", "carrier_type": "ASSET", "scac": "USFC", "mc_number": None, "dot_number": None, "modes": ["FTL"], "equipment_types": ["REEFER"], "service_regions": ["US-WEST"]},
    {"code": "KNGT", "name": "Knight-Swift Transportation", "carrier_type": "ASSET", "scac": "KNIG", "mc_number": "MC-116574", "dot_number": "52814", "modes": ["FTL", "INTERMODAL"], "equipment_types": ["DRY_VAN", "REEFER", "FLATBED"], "service_regions": ["US-WEST", "US-SW", "US-NATIONAL"]},
]

LANE_DISTANCES = {
    "TYSON→CDC_WEST": 1200, "KRAFT→CDC_WEST": 1800, "GENMILLS→CDC_WEST": 1500,
    "NESTLE→CDC_WEST": 1100, "TROP→CDC_WEST": 2400, "SYSCOMEAT→CDC_WEST": 350,
    "LANDOLAKES→CDC_WEST": 1600, "CONAGRA→CDC_WEST": 1400, "RICHPROD→CDC_WEST": 2200,
    "COCACOLA→CDC_WEST": 2100,
    "CDC_WEST→CUST_PDX": 175, "CDC_WEST→CUST_EUG": 280, "CDC_WEST→CUST_SAL": 250,
    "CDC_WEST→CUST_SEA": 175, "CDC_WEST→CUST_TAC": 155, "CDC_WEST→CUST_SPO": 350,
    "CDC_WEST→CUST_LAX": 960, "CDC_WEST→CUST_SFO": 640, "CDC_WEST→CUST_SDG": 1090,
    "CDC_WEST→CUST_SAC": 585, "CDC_WEST→CUST_PHX": 1420, "CDC_WEST→CUST_TUS": 1510,
    "CDC_WEST→CUST_MES": 1430, "CDC_WEST→CUST_SLC": 770,
}

SHIPMENT_STATUSES = ["DRAFT", "DISPATCHED", "IN_TRANSIT", "DELIVERED"]
SHIPMENT_STATUS_WEIGHTS = [0.10, 0.15, 0.25, 0.50]


def seed_carriers(db: Session):
    existing = db.execute(text("SELECT count(*) FROM carrier WHERE tenant_id = :t"), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Carriers already exist ({existing}), skipping")
        return
    for c in CARRIERS:
        db.execute(text("""
            INSERT INTO carrier (code, name, carrier_type, scac, mc_number, dot_number,
                modes, equipment_types, service_regions, is_active, onboarding_status,
                onboarding_date, tenant_id, config_id, created_at)
            VALUES (:code, :name, :ct, :scac, :mc, :dot,
                :modes, :eq, :regions, true, 'ACTIVE',
                :od, :tid, :cid, :now)
        """), {
            "code": c["code"], "name": c["name"], "ct": c["carrier_type"],
            "scac": c["scac"], "mc": c.get("mc_number"), "dot": c.get("dot_number"),
            "modes": json.dumps(c["modes"]), "eq": json.dumps(c["equipment_types"]),
            "regions": json.dumps(c["service_regions"]),
            "od": TODAY - timedelta(days=random.randint(30, 365)),
            "tid": TENANT_ID, "cid": CONFIG_ID, "now": NOW,
        })
    db.commit()
    print(f"  Inserted {len(CARRIERS)} carriers")


def seed_carrier_lanes(db: Session):
    existing = db.execute(text("SELECT count(*) FROM carrier_lane WHERE tenant_id = :t"), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Carrier-lanes already exist ({existing}), skipping")
        return
    carriers = db.execute(text("SELECT id, code FROM carrier WHERE tenant_id = :t"), {"t": TENANT_ID}).mappings().all()
    lanes = db.execute(text("""
        SELECT tl.id FROM transportation_lane tl WHERE tl.config_id = :cid
    """), {"cid": CONFIG_ID}).mappings().all()
    count = 0
    for lane in lanes:
        assigned = random.sample(list(carriers), k=min(random.randint(2, 4), len(carriers)))
        for i, c in enumerate(assigned):
            db.execute(text("""
                INSERT INTO carrier_lane (carrier_id, lane_id, mode, equipment_type,
                    weekly_capacity, avg_transit_days, priority, is_primary, is_active,
                    eff_start_date, eff_end_date, tenant_id, created_at)
                VALUES (:cid, :lid, 'FTL', 'DRY_VAN', :wc, :atd, :pri, :prim, true,
                    :es, :ee, :tid, :now)
            """), {
                "cid": c["id"], "lid": lane["id"], "wc": random.randint(8, 30),
                "atd": round(random.uniform(1.0, 4.0), 1),
                "pri": i + 1, "prim": i == 0,
                "es": TODAY - timedelta(days=90), "ee": TODAY + timedelta(days=275),
                "tid": TENANT_ID, "now": NOW,
            })
            count += 1
    db.commit()
    print(f"  Inserted {count} carrier-lane assignments")


def seed_freight_rates(db: Session):
    existing = db.execute(text("SELECT count(*) FROM freight_rate WHERE tenant_id = :t"), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Freight rates already exist ({existing}), skipping")
        return
    carrier_lanes = db.execute(text(
        "SELECT carrier_id, lane_id, mode, equipment_type FROM carrier_lane WHERE tenant_id = :t"
    ), {"t": TENANT_ID}).mappings().all()
    count = 0
    for cl in carrier_lanes:
        db.execute(text("""
            INSERT INTO freight_rate (carrier_id, lane_id, mode, equipment_type,
                rate_type, rate_per_mile, min_charge, fuel_surcharge_pct,
                eff_start_date, eff_end_date, is_active, tenant_id, config_id, created_at)
            VALUES (:cid, :lid, :mode, :eq, 'CONTRACT', :rpm, :mc, :fsp,
                :es, :ee, true, :tid, :cfgid, :now)
        """), {
            "cid": cl["carrier_id"], "lid": cl["lane_id"],
            "mode": cl["mode"], "eq": cl["equipment_type"],
            "rpm": round(random.uniform(2.10, 3.80), 2),
            "mc": round(random.uniform(250, 500), 2),
            "fsp": round(random.uniform(0.15, 0.28), 2),
            "es": TODAY - timedelta(days=90), "ee": TODAY + timedelta(days=275),
            "tid": TENANT_ID, "cfgid": CONFIG_ID, "now": NOW,
        })
        count += 1
    db.commit()
    print(f"  Inserted {count} freight rates")


def seed_tms_shipments(db: Session, n=300):
    existing = db.execute(text(
        "SELECT count(*) FROM tms_shipment WHERE tenant_id = :t AND source = 'demo_seed'"
    ), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  TMS shipments already exist ({existing}), skipping")
        return
    lanes = db.execute(text("""
        SELECT tl.id, s1.name AS origin, s2.name AS dest, tl.from_site_id, tl.to_site_id
        FROM transportation_lane tl
        JOIN site s1 ON tl.from_site_id = s1.id JOIN site s2 ON tl.to_site_id = s2.id
        WHERE tl.config_id = :cid
    """), {"cid": CONFIG_ID}).mappings().all()
    outbound = [l for l in lanes if l["origin"] == "CDC_WEST"]
    inbound = [l for l in lanes if l["dest"] == "CDC_WEST"]
    count = 0
    for i in range(n):
        lane = random.choice(outbound if random.random() < 0.7 else inbound)
        key = f"{lane['origin']}→{lane['dest']}"
        dist = LANE_DISTANCES.get(key, 500)
        days_ago = random.randint(0, 28)
        pickup = NOW - timedelta(days=days_ago, hours=random.randint(6, 18))
        delivery = pickup + timedelta(days=max(1, round(dist / 500)))
        status = random.choices(SHIPMENT_STATUSES, weights=SHIPMENT_STATUS_WEIGHTS)[0]
        weight = round(random.uniform(8000, 44000), 0)
        pallets = random.randint(4, 26)
        db.execute(text("""
            INSERT INTO tms_shipment (shipment_number, status, origin_site_id, destination_site_id,
                lane_id, quantity, weight, volume, pallet_count, mode, required_equipment,
                requested_pickup_date, requested_delivery_date, priority, service_level,
                source, tenant_id, config_id, created_at)
            VALUES (:sn, :st, :oid, :did, :lid, :qty, :wt, :vol, :pal, 'FTL', 'DRY_VAN',
                :rpd, :rdd, :pri, :sl, 'demo_seed', :tid, :cid, :ca)
        """), {
            "sn": f"FD-{i+1:06d}", "st": status,
            "oid": lane["from_site_id"], "did": lane["to_site_id"], "lid": lane["id"],
            "qty": pallets, "wt": weight, "vol": round(random.uniform(800, 3200), 0),
            "pal": pallets, "rpd": pickup, "rdd": delivery,
            "pri": random.choice([1, 2, 3, 4, 5]),
            "sl": random.choice(["STANDARD", "STANDARD", "STANDARD", "EXPEDITED", "PREMIUM"]),
            "ca": pickup - timedelta(days=random.randint(1, 3)),
            "tid": TENANT_ID, "cid": CONFIG_ID,
        })
        count += 1
    db.commit()
    print(f"  Inserted {count} TMS shipments")


def seed_loads(db: Session, n=120):
    existing = db.execute(text(
        "SELECT count(*) FROM load WHERE tenant_id = :t AND source = 'demo_seed'"
    ), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Loads already exist ({existing}), skipping")
        return
    carriers = db.execute(text("SELECT id FROM carrier WHERE tenant_id = :t"), {"t": TENANT_ID}).mappings().all()
    lanes = db.execute(text("""
        SELECT tl.id, tl.from_site_id, tl.to_site_id, s1.name AS origin, s2.name AS dest
        FROM transportation_lane tl
        JOIN site s1 ON tl.from_site_id = s1.id JOIN site s2 ON tl.to_site_id = s2.id
        WHERE tl.config_id = :cid
    """), {"cid": CONFIG_ID}).mappings().all()
    statuses = ["PLANNING", "READY", "TENDERED", "ASSIGNED", "IN_TRANSIT", "DELIVERED", "DELIVERED", "DELIVERED"]
    count = 0
    for i in range(n):
        lane = random.choice(lanes)
        key = f"{lane['origin']}→{lane['dest']}"
        dist = LANE_DISTANCES.get(key, 500)
        carrier = random.choice(carriers)
        days_ago = random.randint(0, 21)
        depart = NOW - timedelta(days=days_ago, hours=random.randint(4, 20))
        arrive = depart + timedelta(hours=max(8, round(dist / 45)))
        wt = round(random.uniform(20000, 44000), 0)
        vol = round(random.uniform(1800, 3600), 0)
        pals = random.randint(12, 26)
        cost = round(dist * random.uniform(2.20, 3.50), 2)
        db.execute(text("""
            INSERT INTO load (load_number, status, origin_site_id, destination_site_id,
                mode, equipment_type, carrier_id, total_weight, total_volume, total_pallets,
                weight_utilization_pct, volume_utilization_pct, planned_departure, planned_arrival,
                total_cost, cost_per_mile, total_miles, source, tenant_id, config_id, created_at)
            VALUES (:ln, :st, :oid, :did, 'FTL', 'DRY_VAN', :cid, :wt, :vol, :pal,
                :wu, :vu, :pd, :pa, :tc, :cpm, :mi, 'demo_seed', :tid, :cfgid, :ca)
        """), {
            "ln": f"LD-{i+1:05d}", "st": random.choice(statuses),
            "oid": lane["from_site_id"], "did": lane["to_site_id"],
            "cid": carrier["id"], "wt": wt, "vol": vol, "pal": pals,
            "wu": round(wt / 44000 * 100, 1), "vu": round(vol / 3800 * 100, 1),
            "pd": depart, "pa": arrive,
            "tc": cost, "cpm": round(cost / max(dist, 1), 2), "mi": dist,
            "tid": TENANT_ID, "cfgid": CONFIG_ID,
            "ca": depart - timedelta(hours=random.randint(1, 12)),
        })
        count += 1
    db.commit()
    print(f"  Inserted {count} loads")


def seed_transportation_plan(db: Session):
    existing = db.execute(text(
        "SELECT count(*) FROM transportation_plan WHERE tenant_id = :t AND generated_by = 'demo_seed'"
    ), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Transportation plans already exist ({existing}), skipping")
        return
    loads = db.execute(text("""
        SELECT id, origin_site_id, destination_site_id, carrier_id,
            total_weight, total_volume, total_pallets, weight_utilization_pct,
            total_cost, cost_per_mile, total_miles, planned_departure, planned_arrival
        FROM load WHERE tenant_id = :t AND source = 'demo_seed' ORDER BY planned_departure
    """), {"t": TENANT_ID}).mappings().all()
    lanes_map = {}
    for r in db.execute(text(
        "SELECT id, from_site_id, to_site_id FROM transportation_lane WHERE config_id = :c"
    ), {"c": CONFIG_ID}).mappings().all():
        lanes_map[(r["from_site_id"], r["to_site_id"])] = r["id"]

    for version in ["constrained_live", "unconstrained_reference"]:
        total_cost = sum(float(l["total_cost"] or 0) for l in loads if l["total_cost"])
        total_miles = sum(float(l["total_miles"] or 0) for l in loads if l["total_miles"])
        is_unc = version == "unconstrained_reference"
        db.execute(text("""
            INSERT INTO transportation_plan (config_id, plan_version, plan_name, status,
                plan_start_date, plan_end_date, planning_horizon_days,
                total_planned_loads, total_planned_shipments, total_estimated_cost,
                total_estimated_miles, avg_cost_per_mile, avg_utilization_pct,
                carrier_count, optimization_method, generated_by, tenant_id, created_at)
            VALUES (:cid, :pv, :pn, 'READY', :sd, :ed, 28, :tpl, :tps, :tec,
                :tem, :acpm, :aup, 8, :om, 'demo_seed', :tid, :now)
        """), {
            "cid": CONFIG_ID, "pv": version,
            "pn": f"Food Dist — {version.replace('_', ' ').title()}",
            "sd": TODAY - timedelta(days=28), "ed": TODAY,
            "tpl": len(loads), "tps": len(loads) * 2,
            "tec": round(total_cost * (0.92 if is_unc else 1.0), 2),
            "tem": round(total_miles, 1),
            "acpm": round(total_cost / max(total_miles, 1), 2),
            "aup": round(random.uniform(85, 95) if is_unc else random.uniform(72, 88), 1),
            "om": "UNCONSTRAINED_HEURISTIC" if is_unc else "AGENT",
            "tid": TENANT_ID, "now": NOW,
        })
        plan_id = db.execute(text(
            "SELECT id FROM transportation_plan WHERE tenant_id = :t AND plan_version = :pv AND generated_by = 'demo_seed' ORDER BY id DESC LIMIT 1"
        ), {"t": TENANT_ID, "pv": version}).scalar()
        for ld in loads:
            lane_id = lanes_map.get((ld["origin_site_id"], ld["destination_site_id"]))
            cost_mult = 0.92 if is_unc else 1.0
            db.execute(text("""
                INSERT INTO transportation_plan_item (plan_id, origin_site_id, destination_site_id,
                    lane_id, mode, equipment_type, carrier_id, status,
                    planned_pickup_date, planned_delivery_date,
                    shipment_count, total_weight, total_volume, total_pallets,
                    utilization_pct, estimated_cost, estimated_cost_per_mile, distance_miles,
                    load_id, tenant_id, created_at)
                VALUES (:pid, :oid, :did, :lid, 'FTL', 'DRY_VAN', :cid, 'PLANNED',
                    :ppd, :pdd, 2, :tw, :tv, :tp, :up, :ec, :ecpm, :dm, :ldid, :tid, :now)
            """), {
                "pid": plan_id, "oid": ld["origin_site_id"], "did": ld["destination_site_id"],
                "lid": lane_id, "cid": ld["carrier_id"],
                "ppd": ld["planned_departure"], "pdd": ld["planned_arrival"],
                "tw": ld["total_weight"], "tv": ld["total_volume"], "tp": ld["total_pallets"],
                "up": ld["weight_utilization_pct"],
                "ec": round(float(ld["total_cost"] or 0) * cost_mult, 2),
                "ecpm": ld["cost_per_mile"], "dm": ld["total_miles"], "ldid": ld["id"],
                "tid": TENANT_ID, "now": NOW,
            })
    db.commit()
    print(f"  Inserted 2 transportation plans with {len(loads)} items each")


def seed_appointments(db: Session):
    existing = db.execute(text("SELECT count(*) FROM appointment WHERE tenant_id = :t"), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Appointments already exist ({existing}), skipping")
        return
    loads_data = db.execute(text("""
        SELECT id, destination_site_id, carrier_id, planned_arrival, status
        FROM load WHERE tenant_id = :t AND source = 'demo_seed' LIMIT 80
    """), {"t": TENANT_ID}).mappings().all()
    dock_doors = {}
    for dd in db.execute(text("SELECT id, site_id FROM dock_door WHERE tenant_id = :t"), {"t": TENANT_ID}).mappings().all():
        dock_doors.setdefault(dd["site_id"], []).append(dd["id"])
    count = 0
    for ld in loads_data:
        doors = dock_doors.get(ld["destination_site_id"], [])
        if not doors:
            continue
        sched = ld["planned_arrival"] or (NOW - timedelta(days=random.randint(0, 14)))
        status = "COMPLETED" if ld["status"] == "DELIVERED" else random.choice(["CONFIRMED", "CHECKED_IN", "AT_DOCK"])
        db.execute(text("""
            INSERT INTO appointment (site_id, dock_door_id, load_id, appointment_type,
                status, scheduled_start, scheduled_end, carrier_id, tenant_id, created_at)
            VALUES (:sid, :ddid, :lid, 'DELIVERY', :st, :ss, :se, :cid, :tid, :now)
        """), {
            "sid": ld["destination_site_id"], "ddid": random.choice(doors), "lid": ld["id"],
            "st": status, "ss": sched, "se": sched + timedelta(hours=2),
            "cid": ld["carrier_id"], "tid": TENANT_ID, "now": NOW,
        })
        count += 1
    db.commit()
    print(f"  Inserted {count} appointments")


def seed_exceptions(db: Session):
    existing = db.execute(text("SELECT count(*) FROM shipment_exception WHERE tenant_id = :t"), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  Exceptions already exist ({existing}), skipping")
        return
    shipments = db.execute(text("""
        SELECT id FROM tms_shipment WHERE tenant_id = :t AND source = 'demo_seed'
        AND status IN ('IN_TRANSIT', 'DELIVERED') ORDER BY random() LIMIT 20
    """), {"t": TENANT_ID}).mappings().all()
    exc_types = ["LATE_PICKUP", "LATE_DELIVERY", "WEATHER_DELAY", "CARRIER_BREAKDOWN",
                 "TEMPERATURE_EXCURSION", "DETENTION", "ROUTE_DEVIATION", "SHORTAGE"]
    count = 0
    for s in shipments:
        etype = random.choice(exc_types)
        db.execute(text("""
            INSERT INTO shipment_exception (shipment_id, exception_type, severity,
                resolution_status, description, detected_at, estimated_delay_hrs,
                estimated_cost_impact, detection_source, tenant_id, created_at)
            VALUES (:sid, :et, :sev, :rs, :desc, :da, :edh, :eci, :ds, :tid, :now)
        """), {
            "sid": s["id"], "et": etype,
            "sev": random.choice(["LOW", "MEDIUM", "MEDIUM", "HIGH", "CRITICAL"]),
            "rs": random.choice(["DETECTED", "DETECTED", "INVESTIGATING", "RESOLVED", "RESOLVED"]),
            "desc": f"{etype.replace('_', ' ').title()} detected on shipment",
            "da": NOW - timedelta(hours=random.randint(1, 72)),
            "edh": round(random.uniform(2, 24), 1),
            "eci": round(random.uniform(150, 5000), 2),
            "ds": random.choice(["P44_WEBHOOK", "CARRIER_EDI", "MANUAL", "AGENT_DETECTION"]),
            "tid": TENANT_ID, "now": NOW,
        })
        count += 1
    db.commit()
    print(f"  Inserted {count} shipment exceptions")


def add_tms_decision_types(db: Session):
    tms_types = [
        "LOAD_BUILD", "FREIGHT_PROCUREMENT", "SHIPMENT_TRACKING",
        "DOCK_SCHEDULING", "CAPACITY_PROMISE", "EQUIPMENT_REPOSITION",
        "BROKER_ROUTING", "INTERMODAL_TRANSFER", "DEMAND_SENSING",
        "CAPACITY_BUFFER", "EXCEPTION_MANAGEMENT",
    ]
    existing = db.execute(text(
        "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
        "WHERE typname = 'decision_type_enum'"
    )).scalars().all()
    added = 0
    for dt in tms_types:
        if dt not in existing:
            db.execute(text(f"ALTER TYPE decision_type_enum ADD VALUE IF NOT EXISTS '{dt}'"))
            added += 1
    if added:
        db.commit()
        print(f"  Added {added} TMS decision types to enum")
    else:
        print("  TMS decision types already in enum")


def seed_agent_decisions(db: Session, target=120):
    existing = db.execute(text(
        "SELECT count(*) FROM agent_decisions WHERE tenant_id = :t AND agent_type = 'TMS_TRM'"
    ), {"t": TENANT_ID}).scalar()
    if existing > 0:
        print(f"  TMS agent decisions already exist ({existing}), skipping")
        return
    sites = db.execute(text("SELECT id, name FROM site WHERE config_id = :c"), {"c": CONFIG_ID}).mappings().all()
    carriers = db.execute(text("SELECT id, name FROM carrier WHERE tenant_id = :t"), {"t": TENANT_ID}).mappings().all()

    decisions_spec = [
        ("LOAD_BUILD", [
            ("Load consolidation — PDX + EUG", "Consolidate 3 LTL shipments to Portland and Eugene into single FTL", "Reduces cost per shipment by 35%, fills trailer to 87% utilisation"),
            ("Multi-stop load — CA customers", "Build multi-stop FTL: CDC_WEST → LAX → SFO → SAC", "Same-day delivery for 3 customers, 92% utilisation vs 3 separate LTL at 45%"),
            ("Split overweight load", "Split 52,000 lb shipment into two loads for 44,000 lb FTL limit", "Compliance required — single overweight load would face $4,200 fine"),
        ]),
        ("FREIGHT_PROCUREMENT", [
            ("Tender to Schneider — Lane 11", "Award CDC_WEST→PDX to Schneider at $2.45/mi (contract rate)", "Best rate among 3 bids; 98.2% OTD history on this lane"),
            ("Spot rate escalation — Phoenix", "Market rate for CDC_WEST→PHX spiked 22% — spot tender at $3.85/mi to Knight-Swift", "Contract rate unavailable this week. Spot avoids service failure."),
            ("Carrier waterfall — rejected tender", "JB Hunt rejected Lane 17 tender. Cascading to Werner at +$0.15/mi", "Auto-cascade per waterfall priority. Werner confirmed in 12 minutes."),
        ]),
        ("SHIPMENT_TRACKING", [
            ("ETA slip — FD-000042", "Carrier reports 4-hour delay due to I-5 construction near Sacramento", "Revised ETA still within delivery window."),
            ("GPS dark — FD-000108", "No tracking update for 6 hours on FD-000108 (CDC_WEST→SEA)", "Dispatched carrier check-call. Dead zone on US-97."),
            ("Early arrival — FD-000201", "Shipment arriving 8 hours early at CUST_SFO", "Dock appointment rescheduled. Customer notified."),
        ]),
        ("DOCK_SCHEDULING", [
            ("Dock conflict — Door D-03", "Two deliveries at D-03 14:00. Moved FD-000055 to D-05.", "D-05 reefer-capable. Zero wait time impact."),
            ("Peak day rebalance", "Thursday 18 inbound vs 8-door capacity. Shifted 4 to Wednesday PM.", "Peak dock utilisation reduced from 225% to 175%."),
        ]),
        ("CAPACITY_PROMISE", [
            ("Lane 17 capacity commit", "Committed 12 loads/week CDC_WEST→LAX for 4 weeks with Schneider", "Locked rate $2.85/mi vs spot $3.40/mi."),
            ("Reefer capacity alert", "Reefer availability dropping to 60% for Weeks 18-20", "PEAK_PRODUCE_SEASON approaching. Recommend 8 additional reefer loads/week."),
        ]),
        ("EQUIPMENT_REPOSITION", [
            ("Empty reposition PHX→CDC_WEST", "6 empty dry vans at CUST_PHX. Repositioning 4 to CDC_WEST.", "$380 deadhead vs $1,200 spot trailer rental."),
            ("Reefer pre-position for produce season", "Pre-positioning 3 reefers at CDC_WEST from CUST_SLC", "Produce season demand starts Week 18."),
        ]),
        ("BROKER_ROUTING", [
            ("Overflow to XPO — surge week", "Route 5 overflow loads through XPO for Week 16 surge", "Asset carriers at capacity. XPO rate 18% above contract but service guaranteed."),
        ]),
        ("EXCEPTION_MANAGEMENT", [
            ("Weather delay — I-10 closure", "Flash flooding closed I-10 near Tucson. 3 shipments affected.", "Rerouted via I-8. +2 hours transit. Customers notified."),
            ("Carrier breakdown — Werner", "Werner tractor breakdown Lane 24 (CDC_WEST→SLC). Load stranded.", "Knight-Swift rescue unit dispatched. ETA 3 hours."),
            ("Refused delivery — CUST_MES", "CUST_MES refused partial delivery (18 of 22 pallets)", "Investigating origin. Return-to-shipper in progress."),
        ]),
        ("DEMAND_SENSING", [
            ("Volume spike — Portland metro", "PDX+EUG+SAL volumes up 15% vs 4-week average", "Back-to-school season. Recommend capacity pre-commit Weeks 17-19."),
        ]),
        ("CAPACITY_BUFFER", [
            ("Surge buffer — CA lanes", "Reserving 8 FTL slots/week across CA lanes for produce season", "Historical 25% increase May-August. Buffer $2,400/week."),
        ]),
    ]

    statuses = ["ACTIONED", "ACTIONED", "ACTIONED", "INFORMED", "INFORMED", "INSPECTED", "OVERRIDDEN"]
    urgencies = ["STANDARD", "STANDARD", "STANDARD", "URGENT", "LOW"]
    count = 0

    for dtype, items in decisions_spec:
        for item_name, recommendation, reasoning in items:
            site = random.choice(sites)
            carrier = random.choice(carriers) if carriers else None
            days_ago = random.randint(0, 14)
            db.execute(text("""
                INSERT INTO agent_decisions (tenant_id, decision_type, item_code, item_name,
                    category, issue_summary, impact_value, impact_description,
                    agent_recommendation, agent_reasoning, agent_confidence,
                    status, urgency, agent_type, agent_version,
                    created_at, updated_at, outcome_measured, planning_cycle, context_data)
                VALUES (:tid, :dt, :ic, :iname, 'TRANSPORTATION', :iss, :iv, :idesc,
                    :arec, :areas, :aconf, :st, :urg, 'TMS_TRM', 'v1.0',
                    :ca, :ua, false, 'DAILY', :ctx)
            """), {
                "tid": TENANT_ID, "dt": dtype,
                "ic": f"{dtype}-{count+1:03d}", "iname": item_name,
                "iss": recommendation, "iv": round(random.uniform(500, 15000), 2),
                "idesc": f"Estimated impact: ${random.randint(500, 15000):,}",
                "arec": recommendation, "areas": reasoning,
                "aconf": round(random.uniform(0.72, 0.98), 2),
                "st": random.choice(statuses), "urg": random.choice(urgencies),
                "ca": NOW - timedelta(days=days_ago, hours=random.randint(0, 12)),
                "ua": NOW - timedelta(days=days_ago),
                "ctx": json.dumps({"site_id": site["id"], "site_name": site["name"],
                    "carrier_id": carrier["id"] if carrier else None,
                    "carrier_name": carrier["name"] if carrier else None}),
            })
            count += 1

    while count < target:
        dtype, items = random.choice(decisions_spec)
        base = random.choice(items)
        site = random.choice(sites)
        days_ago = random.randint(0, 21)
        db.execute(text("""
            INSERT INTO agent_decisions (tenant_id, decision_type, item_code, item_name,
                category, issue_summary, impact_value, impact_description,
                agent_recommendation, agent_reasoning, agent_confidence,
                status, urgency, agent_type, agent_version,
                created_at, updated_at, outcome_measured, planning_cycle)
            VALUES (:tid, :dt, :ic, :iname, 'TRANSPORTATION', :iss, :iv, :idesc,
                :arec, :areas, :aconf, :st, :urg, 'TMS_TRM', 'v1.0',
                :ca, :ua, false, 'DAILY')
        """), {
            "tid": TENANT_ID, "dt": dtype,
            "ic": f"{dtype}-{count+1:03d}", "iname": f"{base[0]} (v{count})",
            "iss": base[1], "iv": round(random.uniform(200, 12000), 2),
            "idesc": f"Estimated impact: ${random.randint(200, 12000):,}",
            "arec": base[1], "areas": base[2],
            "aconf": round(random.uniform(0.65, 0.98), 2),
            "st": random.choice(statuses), "urg": random.choice(urgencies),
            "ca": NOW - timedelta(days=days_ago, hours=random.randint(0, 23)),
            "ua": NOW - timedelta(days=days_ago),
        })
        count += 1

    db.commit()
    print(f"  Inserted {count} TMS agent decisions")


def main():
    print("=== TMS Demo Seed — Food Dist Tenant ===")
    print(f"  Tenant: {TENANT_ID}, Config: {CONFIG_ID}, Date: {TODAY}")
    with Session(engine) as db:
        print("\n1. Carriers")
        seed_carriers(db)
        print("2. Carrier-lane assignments")
        seed_carrier_lanes(db)
        print("3. Freight rates")
        seed_freight_rates(db)
        print("4. TMS shipments")
        seed_tms_shipments(db)
        print("5. Loads")
        seed_loads(db)
        print("6. Transportation plan + items")
        seed_transportation_plan(db)
        print("7. Appointments")
        seed_appointments(db)
        print("8. Shipment exceptions")
        seed_exceptions(db)
        print("9. TMS decision types + agent decisions")
        add_tms_decision_types(db)
        seed_agent_decisions(db)
    print("\n=== Done. Demo data seeded. ===")


if __name__ == "__main__":
    main()

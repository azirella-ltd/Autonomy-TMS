"""
Seed Food Dist Execution Data

Populates all Execution-section dashboards with demo data:
- Purchase Order Line Items (for existing POs)
- Transfer Orders + Line Items
- Supplier Performance metrics
- Project Orders + Line Items
- Maintenance Orders + Spare Parts
- Turnaround Orders + Line Items
- Invoices + Line Items + 3-Way Match Results
- Goods Receipts + Line Items

Uses: config_id=22, tenant_id=13, dc_site_id=256, user_id=60
"""

import sys
import os
import random
import json
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.db.session import db_url

engine = create_engine(db_url)

# ─── Constants ───────────────────────────────────────────────────────────────
CONFIG_ID = 22
DC_SITE_ID = 256

# Look up tenant, company, and user IDs dynamically from config
with engine.connect() as _conn:
    _row = _conn.execute(text(
        "SELECT sc.tenant_id, t.admin_id "
        "FROM supply_chain_configs sc JOIN tenants t ON t.id = sc.tenant_id "
        "WHERE sc.id = :cid"
    ), {"cid": CONFIG_ID}).fetchone()
    if not _row:
        print(f"ERROR: Config {CONFIG_ID} or its tenant not found.")
        sys.exit(1)
    TENANT_ID = _row[0]
    USER_ID = _row[1] or 60
    # Find the company record for this tenant
    _comp = _conn.execute(text(
        "SELECT id FROM company WHERE id LIKE :pat LIMIT 1"
    ), {"pat": f"%CORP_{TENANT_ID}"}).fetchone()
    COMPANY_ID = _comp[0] if _comp else f"DF_CORP_{TENANT_ID}"

SUPPLIER_SITES = [
    (257, "TYSON"), (258, "KRAFT"), (259, "GENMILLS"), (260, "NESTLE"),
    (261, "TROP"), (262, "SYSCOMEAT"), (263, "LANDOLAKES"), (264, "CONAGRA"),
    (265, "RICHPROD"), (266, "COCACOLA"),
]

CUSTOMER_SITES = [
    (267, "CUST_PDX"), (268, "CUST_EUG"), (269, "CUST_SAL"),
    (270, "CUST_SEA"), (271, "CUST_TAC"), (272, "CUST_SPO"),
    (273, "CUST_LAX"), (274, "CUST_SFO"), (275, "CUST_SDG"),
    (276, "CUST_SAC"), (277, "CUST_PHX"), (278, "CUST_TUS"),
    (279, "CUST_MES"),
]

PRODUCTS = [f"CFG22_{cat}{str(i).zfill(3)}" for cat in ["FP", "DP", "BV", "FD", "RD"] for i in range(1, 6)]

SUPPLIER_PRODUCTS = {
    257: ["CFG22_FP001", "CFG22_FP002"],
    258: ["CFG22_FD001", "CFG22_FD002", "CFG22_FD003"],
    259: ["CFG22_DP001", "CFG22_DP002"],
    260: ["CFG22_FD004", "CFG22_FD005"],
    261: ["CFG22_BV001", "CFG22_BV002"],
    262: ["CFG22_FP003", "CFG22_FP004", "CFG22_FP005"],
    263: ["CFG22_DP003", "CFG22_DP004"],
    264: ["CFG22_RD001", "CFG22_RD002"],
    265: ["CFG22_RD003", "CFG22_RD004", "CFG22_RD005"],
    266: ["CFG22_BV003", "CFG22_BV004", "CFG22_BV005"],
}

EQUIPMENT = [
    ("EQ-CONV-01", "Conveyor System A", "CONVEYOR"),
    ("EQ-CONV-02", "Conveyor System B", "CONVEYOR"),
    ("EQ-FORK-01", "Forklift Fleet #1", "FORKLIFT"),
    ("EQ-FORK-02", "Forklift Fleet #2", "FORKLIFT"),
    ("EQ-COOL-01", "Refrigeration Unit - Zone A", "REFRIGERATION"),
    ("EQ-COOL-02", "Refrigeration Unit - Zone B", "REFRIGERATION"),
    ("EQ-COOL-03", "Freezer Unit - Zone C", "REFRIGERATION"),
    ("EQ-DOCK-01", "Loading Dock Hydraulic #1", "DOCK"),
    ("EQ-DOCK-02", "Loading Dock Hydraulic #2", "DOCK"),
    ("EQ-SORT-01", "Automated Sorting Line", "SORTING"),
    ("EQ-WRAP-01", "Pallet Wrapper", "PACKAGING"),
    ("EQ-SCAN-01", "Barcode Scanner Array", "TECHNOLOGY"),
]

now = datetime.now()
today = date.today()
counters = {}


def rand_date(days_back_start, days_back_end=0):
    delta = random.randint(days_back_end, days_back_start)
    return today - timedelta(days=delta)


def rand_datetime(days_back_start, days_back_end=0):
    d = rand_date(days_back_start, days_back_end)
    return datetime(d.year, d.month, d.day, random.randint(6, 18), random.randint(0, 59))


def seed_all():
    with engine.begin() as conn:
        print("=" * 60)
        print("Seeding Food Dist Execution Data")
        print("=" * 60)

        # Clean up any partial runs (but keep PO line items since they were committed)
        for tbl in ['invoice_match_result', 'invoice_line_item', 'invoice',
                     'goods_receipt_line_item', 'goods_receipt',
                     'turnaround_order_line_item', 'turnaround_order',
                     'maintenance_order_spare', 'maintenance_order',
                     'project_order_line_item', 'project_order',
                     'supplier_performance']:
            ct = conn.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
            if ct > 0:
                conn.execute(text(f"DELETE FROM {tbl}"))
                print(f"  Cleaned {ct} rows from {tbl}")

        # Transfer orders - clean if any exist for our config
        for tbl_pair in [('transfer_order_line_item', 'to_id', 'transfer_order'),
                         ('transfer_order', None, None)]:
            if tbl_pair[1]:
                conn.execute(text(f"DELETE FROM {tbl_pair[0]} WHERE {tbl_pair[1]} IN (SELECT id FROM {tbl_pair[2]} WHERE config_id = :cid)"), {"cid": CONFIG_ID})
            else:
                ct = conn.execute(text(f"DELETE FROM transfer_order WHERE config_id = :cid"), {"cid": CONFIG_ID}).rowcount
                if ct: print(f"  Cleaned {ct} transfer orders")

        seed_po_line_items(conn)
        seed_transfer_orders(conn)
        seed_supplier_performance(conn)
        seed_project_orders(conn)
        seed_maintenance_orders(conn)
        seed_turnaround_orders(conn)
        seed_goods_receipts(conn)
        seed_invoices(conn)

        print("\n" + "=" * 60)
        print("EXECUTION DATA SEEDING COMPLETE")
        print("=" * 60)
        total = sum(counters.values())
        for k, v in counters.items():
            print(f"  {k}: {v}")
        print(f"  TOTAL: {total}")


# ─── 1. PO Line Items ────────────────────────────────────────────────────────
# Actual columns: id, po_id, line_number, product_id, quantity,
#   received_quantity, rejected_quantity, unit_price, line_total,
#   discount_percent, requested_delivery_date, promised_delivery_date,
#   actual_delivery_date, notes, created_at, updated_at

def seed_po_line_items(conn):
    print("\n--- Seeding PO Line Items ---")
    rows = conn.execute(text(
        "SELECT po.id, po.supplier_site_id FROM purchase_order po "
        "WHERE po.config_id = :cid AND NOT EXISTS "
        "(SELECT 1 FROM purchase_order_line_item pli WHERE pli.po_id = po.id) "
        "ORDER BY po.id"
    ), {"cid": CONFIG_ID}).fetchall()

    count = 0
    for po_id, supplier_site_id in rows:
        products = SUPPLIER_PRODUCTS.get(supplier_site_id, random.sample(PRODUCTS, 2))
        num_lines = random.randint(1, min(3, len(products)))
        selected = random.sample(products, num_lines)

        for line_num, product_id in enumerate(selected, 1):
            qty = random.choice([50, 100, 150, 200, 250, 300, 400, 500])
            unit_price = round(random.uniform(5.0, 45.0), 2)
            received = random.choice([0, qty, int(qty * 0.95)])
            req_date = rand_date(90, 14)

            conn.execute(text("""
                INSERT INTO purchase_order_line_item
                (po_id, line_number, product_id, quantity, received_quantity,
                 rejected_quantity, unit_price, line_total, discount_percent,
                 requested_delivery_date, promised_delivery_date, created_at)
                VALUES (:po_id, :ln, :pid, :qty, :received,
                 :rejected, :up, :lt, :disc,
                 :req, :prom, :cat)
            """), {
                "po_id": po_id, "ln": line_num, "pid": product_id,
                "qty": qty, "received": received,
                "rejected": random.choice([0, 0, 0, 0, int(qty * 0.02)]),
                "up": unit_price, "lt": round(qty * unit_price, 2),
                "disc": random.choice([0.0, 0.0, 0.0, 2.0, 5.0]),
                "req": req_date,
                "prom": req_date + timedelta(days=random.randint(0, 3)),
                "cat": now,
            })
            count += 1

    # Update PO total_amount
    conn.execute(text("""
        UPDATE purchase_order SET total_amount = sub.total
        FROM (SELECT po_id, SUM(line_total) as total FROM purchase_order_line_item GROUP BY po_id) sub
        WHERE purchase_order.id = sub.po_id AND purchase_order.config_id = :cid
    """), {"cid": CONFIG_ID})

    counters["PO Line Items"] = count
    print(f"  Created {count} PO line items for {len(rows)} POs")


# ─── 2. Transfer Orders ──────────────────────────────────────────────────────
# Actual columns: id, to_number, source_site_id, destination_site_id, config_id,
#   tenant_id, company_id, order_type, from_tpartner_id, to_tpartner_id, source,
#   source_event_id, source_update_dttm, status, order_date, shipment_date,
#   estimated_delivery_date, actual_ship_date, actual_delivery_date, scenario_id,
#   order_round, arrival_round, transportation_mode, carrier, tracking_number,
#   transportation_lane_id, transportation_cost, currency, notes, mrp_run_id,
#   planning_run_id, created_by_id, released_by_id, picked_by_id, shipped_by_id,
#   received_by_id, created_at, updated_at, released_at, picked_at, shipped_at,
#   received_at, source_participant_round_id
#
# Line: id, to_id, line_number, product_id, quantity, picked_quantity,
#   shipped_quantity, received_quantity, damaged_quantity, requested_ship_date,
#   requested_delivery_date, actual_ship_date, actual_delivery_date, notes,
#   created_at, updated_at

def seed_transfer_orders(conn):
    print("\n--- Seeding Transfer Orders ---")
    count_to = 0
    count_lines = 0
    statuses = ["DRAFT", "RELEASED", "PICKED", "SHIPPED", "IN_TRANSIT", "DELIVERED", "RECEIVED"]
    status_weights = [5, 8, 6, 10, 12, 25, 34]

    for i in range(80):
        cust_id, cust_name = random.choice(CUSTOMER_SITES)
        status = random.choices(statuses, weights=status_weights, k=1)[0]
        order_date = rand_date(120, 5)
        ship_date = order_date + timedelta(days=random.randint(1, 3))
        est_delivery = ship_date + timedelta(days=random.randint(1, 4))
        to_number = f"TO-{order_date.strftime('%Y%m%d')}-{str(i).zfill(4)}"

        actual_ship = ship_date if status in ("SHIPPED", "IN_TRANSIT", "DELIVERED", "RECEIVED") else None
        actual_delivery = est_delivery + timedelta(days=random.randint(-1, 2)) if status in ("DELIVERED", "RECEIVED") else None
        carrier = random.choice(["XPO Logistics", "FedEx Freight", "Old Dominion", "Food Dist Transport", "SAIA Inc"])

        conn.execute(text("""
            INSERT INTO transfer_order
            (to_number, source_site_id, destination_site_id, config_id, tenant_id, company_id,
             order_type, status, order_date, shipment_date, estimated_delivery_date,
             actual_ship_date, actual_delivery_date, transportation_mode, carrier,
             tracking_number, transportation_cost, currency, created_by_id, created_at)
            VALUES (:ton, :src, :dst, :cid, :gid, :comp,
             'transfer', :status, :od, :sd, :edd,
             :asd, :add, :mode, :carrier,
             :track, :cost, 'USD', :uid, :cat)
            RETURNING id
        """), {
            "ton": to_number, "src": DC_SITE_ID, "dst": cust_id,
            "cid": CONFIG_ID, "gid": TENANT_ID, "comp": COMPANY_ID,
            "status": status, "od": order_date, "sd": ship_date, "edd": est_delivery,
            "asd": actual_ship, "add": actual_delivery,
            "mode": random.choice(["LTL", "FTL", "PARCEL", "REEFER"]),
            "carrier": carrier,
            "track": f"TRK{random.randint(100000, 999999)}" if status != "DRAFT" else None,
            "cost": round(random.uniform(200, 2500), 2),
            "uid": USER_ID, "cat": now,
        })
        to_id = conn.execute(text("SELECT lastval()")).scalar()
        count_to += 1

        num_lines = random.randint(1, 5)
        selected_products = random.sample(PRODUCTS, num_lines)
        for ln, pid in enumerate(selected_products, 1):
            qty = random.choice([20, 40, 50, 80, 100, 120, 150, 200])
            picked = qty if status in ("PICKED", "SHIPPED", "IN_TRANSIT", "DELIVERED", "RECEIVED") else 0
            shipped_qty = qty if status in ("SHIPPED", "IN_TRANSIT", "DELIVERED", "RECEIVED") else 0
            received_qty = qty if status == "RECEIVED" else (int(qty * 0.95) if status == "DELIVERED" else 0)

            conn.execute(text("""
                INSERT INTO transfer_order_line_item
                (to_id, line_number, product_id, quantity, picked_quantity,
                 shipped_quantity, received_quantity, damaged_quantity,
                 requested_ship_date, requested_delivery_date, created_at)
                VALUES (:tid, :ln, :pid, :qty, :picked,
                 :shipped, :received, :damaged,
                 :rsd, :rdd, :cat)
            """), {
                "tid": to_id, "ln": ln, "pid": pid, "qty": qty,
                "picked": picked, "shipped": shipped_qty,
                "received": received_qty,
                "damaged": random.choice([0, 0, 0, 0, 0, 1, 2]),
                "rsd": ship_date, "rdd": est_delivery, "cat": now,
            })
            count_lines += 1

    counters["Transfer Orders"] = count_to
    counters["Transfer Order Lines"] = count_lines
    print(f"  Created {count_to} transfer orders with {count_lines} line items")


# ─── 3. Supplier Performance ─────────────────────────────────────────────────
# Actual columns: id, tpartner_id, period_start, period_end, period_type,
#   orders_placed, orders_delivered_on_time, orders_delivered_late,
#   average_days_late, units_received, units_accepted, units_rejected,
#   reject_rate_percent, average_lead_time_days, std_dev_lead_time_days,
#   total_spend, currency, on_time_delivery_rate, quality_rating,
#   overall_performance_score, created_at

def seed_supplier_performance(conn):
    print("\n--- Seeding Supplier Performance ---")

    # Ensure trading_partners exist for FK
    for supplier_site_id, supplier_name in SUPPLIER_SITES:
        tpartner_id = f"TP_{supplier_name}"
        exists = conn.execute(text(
            "SELECT 1 FROM trading_partners WHERE id = :tid"
        ), {"tid": tpartner_id}).fetchone()
        if not exists:
            conn.execute(text("""
                INSERT INTO trading_partners (id, tpartner_type, description, company_id, is_active, source)
                VALUES (:tid, 'SUPPLIER', :desc, :comp, 'true', 'AUTONOMY')
            """), {
                "tid": tpartner_id, "desc": f"Supplier - {supplier_name}",
                "comp": COMPANY_ID,
            })
            print(f"  Created trading partner: {tpartner_id}")

    count = 0
    for supplier_site_id, supplier_name in SUPPLIER_SITES:
        tpartner_id = f"TP_{supplier_name}"
        for months_back in range(6):
            period_start = (today.replace(day=1) - timedelta(days=30 * months_back)).replace(day=1)
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)

            orders_placed = random.randint(15, 45)
            on_time_rate = round(random.uniform(0.82, 0.98), 4)
            on_time = int(orders_placed * on_time_rate)
            late = orders_placed - on_time
            units_received = orders_placed * random.randint(80, 300)
            reject_rate = round(random.uniform(0.005, 0.04), 4)
            units_rejected = int(units_received * reject_rate)

            conn.execute(text("""
                INSERT INTO supplier_performance
                (tpartner_id, period_start, period_end, period_type,
                 orders_placed, orders_delivered_on_time, orders_delivered_late,
                 average_days_late, units_received, units_accepted, units_rejected,
                 reject_rate_percent, average_lead_time_days, std_dev_lead_time_days,
                 total_spend, currency, on_time_delivery_rate, quality_rating,
                 overall_performance_score)
                VALUES (:tp, :ps, :pe, 'MONTHLY',
                 :op, :ot, :late, :adl, :ur, :ua, :uj,
                 :rrp, :alt, :slt, :spend, 'USD', :otdr, :qr, :ops)
            """), {
                "tp": tpartner_id,
                "ps": datetime(period_start.year, period_start.month, period_start.day),
                "pe": datetime(period_end.year, period_end.month, period_end.day),
                "op": orders_placed, "ot": on_time, "late": late,
                "adl": round(random.uniform(0.5, 3.0), 1) if late > 0 else 0,
                "ur": units_received, "ua": units_received - units_rejected,
                "uj": units_rejected, "rrp": round(reject_rate * 100, 2),
                "alt": round(random.uniform(3, 14), 1),
                "slt": round(random.uniform(0.5, 2.5), 1),
                "spend": round(random.uniform(50000, 350000), 2),
                "otdr": round(on_time_rate * 100, 2),
                "qr": round(random.uniform(85, 99), 1),
                "ops": round(random.uniform(78, 97), 1),
            })
            count += 1

    counters["Supplier Performance"] = count
    print(f"  Created {count} supplier performance records")


# ─── 4. Project Orders ───────────────────────────────────────────────────────
# Actual columns: id, project_order_number, project_id, project_name,
#   tenant_id, customer_name, site_id (String), config_id, tenant_id,
#   company_id, order_type, source, source_event_id, source_update_dttm,
#   status, order_date, required_start_date, required_completion_date,
#   planned_start_date, planned_completion_date, actual_start_date,
#   actual_completion_date, project_type, priority, contract_number,
#   contract_value, currency, completion_percentage, milestones (JSON),
#   estimated_hours, actual_hours, estimated_cost, actual_cost, description,
#   notes, special_requirements, context_data (JSON), mrp_run_id,
#   planning_run_id, created_by_id, approved_by_id, completed_by_id,
#   created_at, updated_at, approved_at, started_at, completed_at, cancelled_at
#
# Line: id, project_order_id, line_number, product_id, description,
#   quantity_required, quantity_produced, unit_of_measure, unit_price,
#   line_total, required_date, status, notes, created_at, updated_at

def seed_project_orders(conn):
    print("\n--- Seeding Project Orders ---")

    projects = [
        ("Warehouse Zone A Expansion", "CAPITAL", "HIGH", 45000, 320),
        ("Cold Storage Upgrade Phase 2", "CAPITAL", "HIGH", 78000, 480),
        ("Loading Dock Modernization", "CAPITAL", "NORMAL", 32000, 240),
        ("Inventory Barcode System Upgrade", "TECHNOLOGY", "HIGH", 18000, 160),
        ("Forklift Fleet Replacement", "CAPITAL", "NORMAL", 55000, 120),
        ("Safety System Overhaul", "REGULATORY", "URGENT", 24000, 200),
        ("Automated Sorting Line Install", "TECHNOLOGY", "HIGH", 95000, 600),
        ("Solar Panel Installation", "SUSTAINABILITY", "LOW", 42000, 280),
        ("Office Renovation", "FACILITY", "LOW", 15000, 100),
        ("Sprinkler System Upgrade", "REGULATORY", "NORMAL", 28000, 180),
        ("Parking Lot Repaving", "FACILITY", "LOW", 35000, 90),
        ("EV Charging Station Install", "SUSTAINABILITY", "NORMAL", 22000, 120),
    ]

    count_proj = 0
    count_lines = 0

    for i, (name, ptype, priority, est_cost, est_hours) in enumerate(projects):
        order_date = rand_date(180, 30)
        req_start = order_date + timedelta(days=random.randint(7, 30))
        req_complete = req_start + timedelta(days=random.randint(30, 120))

        if i < 5:
            status = "COMPLETED"
            completion = 100.0
            actual_cost = round(est_cost * random.uniform(0.9, 1.15), 2)
            actual_hours = round(est_hours * random.uniform(0.85, 1.2), 1)
            actual_start = req_start + timedelta(days=random.randint(-2, 5))
            actual_complete = req_complete + timedelta(days=random.randint(-10, 15))
        elif i < 9:
            status = random.choice(["IN_PROGRESS", "APPROVED"])
            completion = round(random.uniform(15, 85), 1)
            actual_cost = round(est_cost * completion / 100 * random.uniform(0.9, 1.1), 2)
            actual_hours = round(est_hours * completion / 100, 1)
            actual_start = req_start if status == "IN_PROGRESS" else None
            actual_complete = None
        else:
            status = "PLANNED"
            completion = 0.0
            actual_cost = 0.0
            actual_hours = 0.0
            actual_start = None
            actual_complete = None

        milestones = json.dumps([
            {"name": "Planning Complete", "target_date": str(req_start), "status": "COMPLETED" if completion > 10 else "PENDING"},
            {"name": "Materials Procured", "target_date": str(req_start + timedelta(days=14)), "status": "COMPLETED" if completion > 30 else "PENDING"},
            {"name": "Installation", "target_date": str(req_start + timedelta(days=45)), "status": "COMPLETED" if completion > 60 else "PENDING"},
            {"name": "Testing", "target_date": str(req_complete - timedelta(days=14)), "status": "COMPLETED" if completion > 90 else "PENDING"},
            {"name": "Sign-off", "target_date": str(req_complete), "status": "COMPLETED" if completion == 100 else "PENDING"},
        ])

        conn.execute(text("""
            INSERT INTO project_order
            (project_order_number, project_id, project_name, site_id,
             config_id, tenant_id, company_id, order_type, status, order_date,
             required_start_date, required_completion_date,
             planned_start_date, planned_completion_date,
             actual_start_date, actual_completion_date,
             project_type, priority, estimated_hours, actual_hours,
             estimated_cost, actual_cost, completion_percentage,
             milestones, currency, description, created_by_id, created_at)
            VALUES (:pon, :pid, :pname, :sid,
             :cid, :gid, :comp, 'project', :status, :od,
             :rsd, :rcd, :psd, :pcd, :asd, :acd,
             :ptype, :priority, :eh, :ah,
             :ec, :ac, :cp,
             CAST(:milestones AS json), 'USD', :desc, :uid, :cat)
            RETURNING id
        """), {
            "pon": f"PROJ-{str(i+1).zfill(4)}", "pid": f"PRJ-FD-{str(i+1).zfill(3)}",
            "pname": name, "sid": str(DC_SITE_ID),
            "cid": CONFIG_ID, "gid": TENANT_ID, "comp": COMPANY_ID,
            "status": status, "od": order_date,
            "rsd": req_start, "rcd": req_complete,
            "psd": req_start, "pcd": req_complete,
            "asd": actual_start, "acd": actual_complete,
            "ptype": ptype, "priority": priority,
            "eh": est_hours, "ah": actual_hours,
            "ec": est_cost, "ac": actual_cost, "cp": completion,
            "milestones": milestones,
            "desc": f"{name} - Food Dist DC facility project",
            "uid": USER_ID, "cat": now,
        })
        proj_id = conn.execute(text("SELECT lastval()")).scalar()
        count_proj += 1

        # Line items (actual cols: product_id, description, quantity_required,
        #   quantity_produced, unit_of_measure, unit_price, line_total, required_date, status)
        num_lines = random.randint(2, 5)
        for ln in range(1, num_lines + 1):
            pid = random.choice(PRODUCTS)
            qty_req = random.choice([10, 20, 25, 50, 100])
            qty_prod = qty_req if completion == 100 else int(qty_req * min(completion / 100, 1.0))
            unit_price = round(random.uniform(10, 200), 2)
            line_status = "COMPLETED" if qty_prod >= qty_req else ("IN_PROGRESS" if qty_prod > 0 else "PENDING")

            conn.execute(text("""
                INSERT INTO project_order_line_item
                (project_order_id, line_number, product_id, description,
                 quantity_required, quantity_produced, unit_of_measure,
                 unit_price, line_total, required_date, status, created_at)
                VALUES (:poid, :ln, :pid, :desc,
                 :qr, :qp, 'EA', :uc, :tc, :rd, :status, :cat)
            """), {
                "poid": proj_id, "ln": ln, "pid": pid,
                "desc": f"Project material - {pid}",
                "qr": qty_req, "qp": qty_prod,
                "uc": unit_price, "tc": round(qty_req * unit_price, 2),
                "rd": req_start + timedelta(days=random.randint(0, 30)),
                "status": line_status, "cat": now,
            })
            count_lines += 1

    counters["Project Orders"] = count_proj
    counters["Project Order Lines"] = count_lines
    print(f"  Created {count_proj} project orders with {count_lines} line items")


# ─── 5. Maintenance Orders ───────────────────────────────────────────────────
# Actual columns: id, maintenance_order_number, asset_id, asset_name,
#   asset_category, site_id (String), config_id, tenant_id, company_id,
#   order_type, source, maintenance_type, status, priority, order_date,
#   scheduled_start_date, scheduled_end_date, actual_start_date,
#   actual_end_date, work_description, root_cause, resolution_notes,
#   failure_code, downtime_required, estimated_downtime_hours,
#   actual_downtime_hours, estimated_labor_hours, actual_labor_hours,
#   estimated_cost, actual_cost, assigned_technician_id, supervisor_id,
#   created_by_id, approved_by_id, completed_by_id, created_at, updated_at,
#   approved_at, started_at, completed_at
#
# Spare: id, maintenance_order_id, line_number, product_id, description,
#   quantity_required, quantity_issued, unit_of_measure, unit_cost, line_total,
#   issued_by_id, created_at, updated_at

def seed_maintenance_orders(conn):
    print("\n--- Seeding Maintenance Orders ---")
    maint_types = ["PREVENTIVE", "CORRECTIVE", "PREDICTIVE", "EMERGENCY"]
    maint_weights = [40, 25, 20, 15]
    count_mo = 0
    count_spares = 0

    for i in range(35):
        eq_id, eq_name, eq_type = random.choice(EQUIPMENT)
        mtype = random.choices(maint_types, weights=maint_weights, k=1)[0]
        order_date = rand_date(120, 3)
        sched_start = rand_datetime(100, 2)
        sched_end = sched_start + timedelta(hours=random.randint(2, 48))

        if i < 20:
            status = "COMPLETED"
            actual_start = sched_start + timedelta(hours=random.randint(-2, 4))
            actual_end = sched_end + timedelta(hours=random.randint(-4, 8))
        elif i < 28:
            status = random.choice(["IN_PROGRESS", "SCHEDULED", "APPROVED"])
            actual_start = sched_start if status == "IN_PROGRESS" else None
            actual_end = None
        else:
            status = "PLANNED"
            actual_start = None
            actual_end = None

        est_downtime = round(random.uniform(1, 24), 1)
        est_labor = round(random.uniform(2, 40), 1)
        est_cost = round(random.uniform(500, 15000), 2)

        work_desc = {
            "PREVENTIVE": f"Scheduled PM for {eq_name}. Inspect, lubricate, replace wear items.",
            "CORRECTIVE": f"Corrective maintenance - {eq_name} degraded performance. Diagnose and repair.",
            "PREDICTIVE": f"Predictive maintenance triggered by sensor data on {eq_name}.",
            "EMERGENCY": f"Emergency breakdown of {eq_name}. Immediate response required.",
        }

        conn.execute(text("""
            INSERT INTO maintenance_order
            (maintenance_order_number, asset_id, asset_name, asset_category,
             site_id, config_id, tenant_id, company_id, order_type, source,
             maintenance_type, status, priority, order_date,
             scheduled_start_date, scheduled_end_date,
             actual_start_date, actual_end_date,
             work_description, root_cause, resolution_notes, failure_code,
             downtime_required, estimated_downtime_hours, actual_downtime_hours,
             estimated_labor_hours, actual_labor_hours,
             estimated_cost, actual_cost,
             created_by_id, created_at)
            VALUES (:mon, :aid, :aname, :acat,
             :sid, :cid, :gid, :comp, 'maintenance', 'AUTONOMY',
             :mtype, :status, :priority, :od,
             :ssd, :sed, :asd, :aed,
             :wd, :rc, :rn, :fc,
             :dr, :edh, :adh, :elh, :alh, :ec, :ac,
             :uid, :cat)
            RETURNING id
        """), {
            "mon": f"MO-{order_date.strftime('%Y%m%d')}-{str(i+1).zfill(4)}",
            "aid": eq_id, "aname": eq_name, "acat": eq_type,
            "sid": str(DC_SITE_ID),
            "cid": CONFIG_ID, "gid": TENANT_ID, "comp": COMPANY_ID,
            "mtype": mtype, "status": status,
            "priority": "URGENT" if mtype == "EMERGENCY" else random.choice(["NORMAL", "NORMAL", "HIGH"]),
            "od": order_date, "ssd": sched_start, "sed": sched_end,
            "asd": actual_start, "aed": actual_end,
            "wd": work_desc[mtype],
            "rc": f"Wear and tear - {eq_type}" if status == "COMPLETED" and mtype == "CORRECTIVE" else None,
            "rn": "Replaced worn components, tested and verified" if status == "COMPLETED" else None,
            "fc": f"FC-{eq_type[:4]}-{random.randint(100,999)}" if mtype in ("CORRECTIVE", "EMERGENCY") else None,
            "dr": "Y" if mtype != "PREDICTIVE" else random.choice(["Y", "N"]),
            "edh": est_downtime,
            "adh": round(est_downtime * random.uniform(0.8, 1.3), 1) if status == "COMPLETED" else None,
            "elh": est_labor,
            "alh": round(est_labor * random.uniform(0.9, 1.2), 1) if status == "COMPLETED" else 0,
            "ec": est_cost,
            "ac": round(est_cost * random.uniform(0.85, 1.25), 2) if status == "COMPLETED" else 0,
            "uid": USER_ID, "cat": now,
        })
        mo_id = conn.execute(text("SELECT lastval()")).scalar()
        count_mo += 1

        # Spare parts (actual cols: product_id, description, quantity_required,
        #   quantity_issued, unit_of_measure, unit_cost, line_total)
        num_spares = random.randint(1, 4)
        for ln in range(1, num_spares + 1):
            pid = random.choice(PRODUCTS)
            qty_req = random.choice([1, 2, 3, 5, 10])
            qty_issued = qty_req if status == "COMPLETED" else 0
            part_types = ["Consumable", "Replacement", "Filter", "Lubricant", "Belt", "Bearing"]
            unit_cost = round(random.uniform(15, 500), 2)

            conn.execute(text("""
                INSERT INTO maintenance_order_spare
                (maintenance_order_id, line_number, product_id, description,
                 quantity_required, quantity_issued, unit_of_measure,
                 unit_cost, line_total, created_at)
                VALUES (:moid, :ln, :pid, :desc,
                 :qr, :qi, 'EA', :uc, :lt, :cat)
            """), {
                "moid": mo_id, "ln": ln, "pid": pid,
                "desc": f"{random.choice(part_types)} - {pid}",
                "qr": qty_req, "qi": qty_issued,
                "uc": unit_cost, "lt": round(qty_req * unit_cost, 2),
                "cat": now,
            })
            count_spares += 1

    counters["Maintenance Orders"] = count_mo
    counters["Maintenance Spares"] = count_spares
    print(f"  Created {count_mo} maintenance orders with {count_spares} spare parts")


# ─── 6. Turnaround Orders ────────────────────────────────────────────────────
# Actual columns: id, turnaround_order_number, from_site_id (String),
#   to_site_id (String), refurbishment_site_id (String), config_id, tenant_id,
#   company_id, order_type, source, return_reason_code,
#   return_reason_description, turnaround_type, status, order_date,
#   expected_receipt_date, actual_receipt_date, inspection_date,
#   disposition_date, completion_date, disposition, quality_grade,
#   product_condition, estimated_refurbishment_cost, actual_refurbishment_cost,
#   recovery_value, notes, created_by_id, approved_by_id, received_by_id,
#   inspected_by_id, disposed_by_id, created_at, updated_at, approved_at
#
# Line: id, turnaround_order_id, line_number, product_id, description,
#   quantity_returned, quantity_accepted, quantity_rejected, serial_number,
#   lot_number, product_condition, quality_grade, notes, created_at, updated_at

def seed_turnaround_orders(conn):
    print("\n--- Seeding Turnaround Orders ---")
    return_reasons = [
        ("DAMAGED", "Product damaged during shipping"),
        ("QUALITY", "Product quality below standards"),
        ("WRONG_ITEM", "Incorrect product shipped"),
        ("OVERSTOCK", "Customer returning excess"),
        ("EXPIRED", "Product near or past expiry"),
        ("RECALL", "Manufacturer-initiated recall"),
    ]
    turnaround_types = ["RETURN_TO_STOCK", "RETURN_TO_VENDOR", "REFURBISH", "SCRAP"]
    dispositions = ["RETURN_TO_STOCK", "RETURN_TO_VENDOR", "REFURBISH", "SCRAP", "DONATE"]
    count_ta = 0
    count_lines = 0

    for i in range(25):
        cust_id, cust_name = random.choice(CUSTOMER_SITES)
        reason_code, reason_desc = random.choice(return_reasons)
        order_date = rand_date(90, 5)
        ta_type = random.choice(turnaround_types)

        if i < 15:
            status = random.choice(["COMPLETED", "DISPOSED"])
            actual_receipt = order_date + timedelta(days=random.randint(3, 10))
            inspection_date = actual_receipt + timedelta(days=random.randint(1, 3))
            disposition_date = inspection_date + timedelta(days=random.randint(1, 3))
            completion_date = disposition_date + timedelta(days=random.randint(1, 5))
            disposition = random.choice(dispositions)
        elif i < 22:
            status = random.choice(["RECEIVED", "INSPECTING"])
            actual_receipt = order_date + timedelta(days=random.randint(3, 10))
            inspection_date = actual_receipt + timedelta(days=1) if status == "INSPECTING" else None
            disposition_date = None
            completion_date = None
            disposition = None
        else:
            status = random.choice(["INITIATED", "APPROVED"])
            actual_receipt = None
            inspection_date = None
            disposition_date = None
            completion_date = None
            disposition = None

        est_refurb_cost = round(random.uniform(50, 500), 2) if ta_type == "REFURBISH" else 0

        conn.execute(text("""
            INSERT INTO turnaround_order
            (turnaround_order_number, from_site_id, to_site_id, refurbishment_site_id,
             config_id, tenant_id, company_id, order_type, source,
             return_reason_code, return_reason_description, turnaround_type,
             status, order_date, expected_receipt_date, actual_receipt_date,
             inspection_date, disposition_date, completion_date, disposition,
             quality_grade, product_condition,
             estimated_refurbishment_cost, actual_refurbishment_cost, recovery_value,
             notes, created_by_id, created_at)
            VALUES (:tan, :from_sid, :to_sid, :refurb_sid,
             :cid, :gid, :comp, 'turnaround', 'AUTONOMY',
             :rrc, :rrd, :tat,
             :status, :od, :erd, :ard,
             :insp, :disp_date, :comp_date, :disp,
             :qg, :pc,
             :erc, :arc, :rv,
             :notes, :uid, :cat)
            RETURNING id
        """), {
            "tan": f"TA-{order_date.strftime('%Y%m%d')}-{str(i+1).zfill(4)}",
            "from_sid": str(cust_id), "to_sid": str(DC_SITE_ID),
            "refurb_sid": str(DC_SITE_ID) if ta_type == "REFURBISH" else None,
            "cid": CONFIG_ID, "gid": TENANT_ID, "comp": COMPANY_ID,
            "rrc": reason_code, "rrd": reason_desc, "tat": ta_type,
            "status": status, "od": order_date,
            "erd": order_date + timedelta(days=random.randint(5, 14)),
            "ard": actual_receipt, "insp": inspection_date,
            "disp_date": disposition_date, "comp_date": completion_date,
            "disp": disposition,
            "qg": random.choice(["A", "B", "C", "D"]) if actual_receipt else None,
            "pc": random.choice(["GOOD", "FAIR", "POOR", "DAMAGED"]) if actual_receipt else None,
            "erc": est_refurb_cost,
            "arc": round(est_refurb_cost * random.uniform(0.8, 1.2), 2) if status in ("COMPLETED", "DISPOSED") and ta_type == "REFURBISH" else 0,
            "rv": round(random.uniform(100, 2000), 2) if status in ("COMPLETED", "DISPOSED") else None,
            "notes": f"Return from {cust_name}: {reason_desc}",
            "uid": USER_ID, "cat": now,
        })
        ta_id = conn.execute(text("SELECT lastval()")).scalar()
        count_ta += 1

        num_lines = random.randint(1, 3)
        selected_products = random.sample(PRODUCTS, num_lines)
        for ln, pid in enumerate(selected_products, 1):
            qty_returned = random.choice([1, 2, 5, 10, 20])
            qty_accepted = qty_returned if status in ("COMPLETED", "DISPOSED") else 0
            qty_rejected = 0
            if status in ("COMPLETED", "DISPOSED") and random.random() < 0.1:
                qty_rejected = random.randint(1, max(1, qty_returned // 4))
                qty_accepted = qty_returned - qty_rejected

            conn.execute(text("""
                INSERT INTO turnaround_order_line_item
                (turnaround_order_id, line_number, product_id, description,
                 quantity_returned, quantity_accepted, quantity_rejected,
                 serial_number, lot_number, product_condition, quality_grade,
                 notes, created_at)
                VALUES (:taid, :ln, :pid, :desc,
                 :qret, :qacc, :qrej,
                 :sn, :lot, :pc, :qg,
                 :notes, :cat)
            """), {
                "taid": ta_id, "ln": ln, "pid": pid,
                "desc": f"Return item - {pid}",
                "qret": qty_returned, "qacc": qty_accepted, "qrej": qty_rejected,
                "sn": f"SN-{random.randint(100000, 999999)}" if random.random() > 0.5 else None,
                "lot": f"LOT-{random.randint(1000, 9999)}" if random.random() > 0.5 else None,
                "pc": random.choice(["GOOD", "FAIR", "POOR"]) if actual_receipt else None,
                "qg": random.choice(["A", "B", "C"]) if actual_receipt else None,
                "notes": None, "cat": now,
            })
            count_lines += 1

    counters["Turnaround Orders"] = count_ta
    counters["Turnaround Order Lines"] = count_lines
    print(f"  Created {count_ta} turnaround orders with {count_lines} line items")


# ─── 7. Goods Receipts ───────────────────────────────────────────────────────
# Actual columns: id, gr_number, po_id, receiving_site_id, receipt_date,
#   status, notes, received_by_id, inspected_by_id, created_at, updated_at,
#   inspection_date, completed_at
#
# Line: id, goods_receipt_id (NOT gr_id!), po_line_id, line_number, product_id,
#   description, expected_qty, received_qty, accepted_qty, rejected_qty,
#   variance_type, inspection_status, rejection_reason, notes, created_at,
#   updated_at

def seed_goods_receipts(conn):
    print("\n--- Seeding Goods Receipts ---")

    po_rows = conn.execute(text("""
        SELECT po.id, po.po_number, po.order_date
        FROM purchase_order po
        WHERE po.config_id = :cid
        AND EXISTS (SELECT 1 FROM purchase_order_line_item pli WHERE pli.po_id = po.id)
        ORDER BY po.id LIMIT 200
    """), {"cid": CONFIG_ID}).fetchall()

    count_gr = 0
    count_lines = 0
    gr_id_map = {}

    selected_pos = random.sample(po_rows, min(len(po_rows), 140))

    for po_id, po_number, order_date in selected_pos:
        gr_num = f"GR-{po_number.replace('PO-', '')}"
        receipt_date = datetime.combine(order_date, datetime.min.time()) + timedelta(days=random.randint(5, 21))

        po_lines = conn.execute(text(
            "SELECT id, line_number, product_id, quantity, unit_price "
            "FROM purchase_order_line_item WHERE po_id = :pid ORDER BY line_number"
        ), {"pid": po_id}).fetchall()

        conn.execute(text("""
            INSERT INTO goods_receipt
            (gr_number, po_id, receiving_site_id, receipt_date,
             status, notes, received_by_id, created_at, completed_at)
            VALUES (:grn, :poid, :rsid, :rd,
             'COMPLETED', :notes, :uid, :cat, :ca)
            RETURNING id
        """), {
            "grn": gr_num, "poid": po_id, "rsid": DC_SITE_ID,
            "rd": receipt_date,
            "notes": f"Receipt for {po_number}",
            "uid": USER_ID, "cat": now,
            "ca": receipt_date + timedelta(hours=random.randint(2, 8)),
        })
        gr_id = conn.execute(text("SELECT lastval()")).scalar()
        gr_id_map[po_id] = gr_id
        count_gr += 1

        for po_line_id, line_num, product_id, qty, unit_price in po_lines:
            variance_roll = random.random()
            if variance_roll < 0.8:
                received_qty = qty
                rejected_qty = 0
            elif variance_roll < 0.92:
                received_qty = qty - random.randint(1, max(1, int(qty * 0.05)))
                rejected_qty = 0
            else:
                received_qty = qty
                rejected_qty = random.randint(1, max(1, int(qty * 0.03)))

            accepted_qty = received_qty - rejected_qty
            variance_qty = received_qty - qty

            conn.execute(text("""
                INSERT INTO goods_receipt_line_item
                (goods_receipt_id, po_line_id, line_number, product_id, description,
                 expected_qty, received_qty, accepted_qty, rejected_qty,
                 variance_type, inspection_status, rejection_reason, created_at)
                VALUES (:grid, :plid, :ln, :pid, :desc,
                 :eq, :rq, :aq, :rejq,
                 :vt, :is, :rr, :cat)
            """), {
                "grid": gr_id, "plid": po_line_id, "ln": line_num,
                "pid": product_id, "desc": f"Receipt of {product_id}",
                "eq": qty, "rq": received_qty, "aq": accepted_qty, "rejq": rejected_qty,
                "vt": "SHORTAGE" if variance_qty < 0 else ("OVERAGE" if variance_qty > 0 else None),
                "is": "FAILED" if rejected_qty > 0 else "PASSED",
                "rr": "Quality defect" if rejected_qty > 0 else None,
                "cat": now,
            })
            count_lines += 1

    counters["Goods Receipts"] = count_gr
    counters["Goods Receipt Lines"] = count_lines
    print(f"  Created {count_gr} goods receipts with {count_lines} line items")
    seed_goods_receipts.gr_id_map = gr_id_map


# ─── 8. Invoices & 3-Way Match ───────────────────────────────────────────────
# Actual invoice cols: id, invoice_number, vendor_invoice_number, vendor_id,
#   vendor_name, po_id, invoice_date, received_date, due_date, payment_date,
#   subtotal, tax_amount, total_amount, currency, match_status, status,
#   payment_terms, notes, created_by_id, validated_by_id, approved_by_id,
#   created_at, updated_at, validated_at, approved_at
#
# Actual inv_line cols: id, invoice_id, po_line_id, line_number, product_id,
#   description, quantity, unit_price, line_total, created_at, updated_at
#
# Actual inv_match cols: id, invoice_id, po_id, gr_id, match_type,
#   match_status, po_total, gr_total, invoice_total, quantity_variance,
#   price_variance, total_variance, tolerance_percent, is_within_tolerance,
#   discrepancy_details, resolution, resolution_notes, resolved_by_id,
#   created_at, resolved_at

def seed_invoices(conn):
    print("\n--- Seeding Invoices & 3-Way Match ---")
    gr_id_map = getattr(seed_goods_receipts, 'gr_id_map', {})
    if not gr_id_map:
        print("  No goods receipts found - skipping invoices")
        return

    po_with_gr = list(gr_id_map.keys())
    selected_pos = random.sample(po_with_gr, min(len(po_with_gr), 110))

    count_inv = 0
    count_lines = 0
    count_match = 0

    match_statuses = ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "PARTIAL_MATCH", "DISCREPANCY", "PENDING"]

    for po_id in selected_pos:
        gr_id = gr_id_map[po_id]

        po_info = conn.execute(text(
            "SELECT po_number, order_date, total_amount, supplier_site_id "
            "FROM purchase_order WHERE id = :pid"
        ), {"pid": po_id}).fetchone()
        po_number, order_date, po_total, supplier_site_id = po_info
        supplier_name = next((n for sid, n in SUPPLIER_SITES if sid == supplier_site_id), "Unknown")

        inv_date = order_date + timedelta(days=random.randint(10, 30))
        match_status = random.choice(match_statuses)

        price_factor = random.uniform(0.95, 1.08) if match_status == "DISCREPANCY" else 1.0
        subtotal = round((po_total or 0) * price_factor, 2)
        tax = round(subtotal * random.uniform(0.05, 0.09), 2)
        total = round(subtotal + tax, 2)

        inv_status = "APPROVED" if match_status == "MATCHED" else (
            "UNDER_REVIEW" if match_status in ("PARTIAL_MATCH", "DISCREPANCY") else "RECEIVED"
        )

        conn.execute(text("""
            INSERT INTO invoice
            (invoice_number, vendor_invoice_number, vendor_id, vendor_name,
             po_id, invoice_date, received_date, due_date,
             subtotal, tax_amount, total_amount,
             currency, match_status, status, payment_terms,
             notes, created_by_id, created_at)
            VALUES (:inv_num, :vin, :vid, :vname,
             :poid, :idate, :rdate, :ddate,
             :sub, :tax, :total,
             'USD', :ms, :status, :pt,
             :notes, :uid, :cat)
            RETURNING id
        """), {
            "inv_num": f"INV-{po_number.replace('PO-', '')}",
            "vin": f"V-{supplier_name}-{random.randint(10000, 99999)}",
            "vid": f"TP_{supplier_name}", "vname": f"Supplier - {supplier_name}",
            "poid": po_id, "idate": inv_date,
            "rdate": inv_date + timedelta(days=random.randint(0, 3)),
            "ddate": inv_date + timedelta(days=30),
            "sub": subtotal, "tax": tax, "total": total,
            "ms": match_status, "status": inv_status,
            "pt": random.choice(["NET30", "NET45", "NET60", "2/10_NET30"]),
            "notes": None, "uid": USER_ID, "cat": now,
        })
        inv_id = conn.execute(text("SELECT lastval()")).scalar()
        count_inv += 1

        # Invoice line items (cols: invoice_id, po_line_id, line_number,
        #   product_id, description, quantity, unit_price, line_total)
        po_lines = conn.execute(text(
            "SELECT id, line_number, product_id, quantity, unit_price, line_total "
            "FROM purchase_order_line_item WHERE po_id = :pid ORDER BY line_number"
        ), {"pid": po_id}).fetchall()

        gr_lines = conn.execute(text(
            "SELECT po_line_id, received_qty FROM goods_receipt_line_item WHERE goods_receipt_id = :grid"
        ), {"grid": gr_id}).fetchall()
        gr_qty_map = {r[0]: r[1] for r in gr_lines}

        for po_line_id, line_num, product_id, po_qty, po_unit_price, po_line_total in po_lines:
            inv_unit_price = round((po_unit_price or 0) * price_factor, 2)
            inv_qty = po_qty
            line_total = round(inv_qty * inv_unit_price, 2)

            conn.execute(text("""
                INSERT INTO invoice_line_item
                (invoice_id, po_line_id, line_number, product_id, description,
                 quantity, unit_price, line_total, created_at)
                VALUES (:iid, :plid, :ln, :pid, :desc,
                 :qty, :up, :lt, :cat)
            """), {
                "iid": inv_id, "plid": po_line_id, "ln": line_num,
                "pid": product_id, "desc": f"Invoice for {product_id}",
                "qty": inv_qty, "up": inv_unit_price, "lt": line_total,
                "cat": now,
            })
            count_lines += 1

        # 3-Way Match Result (cols: invoice_id, po_id, gr_id, match_type,
        #   match_status, po_total, gr_total, invoice_total, quantity_variance,
        #   price_variance, total_variance, tolerance_percent, is_within_tolerance,
        #   discrepancy_details, resolution, resolution_notes, resolved_by_id)
        po_total_val = po_total or 0
        gr_total = sum(gr_qty_map.get(pl[0], pl[3]) * (pl[4] or 0) for pl in po_lines)
        total_variance = round(total - po_total_val, 2)
        is_within = match_status == "MATCHED"

        conn.execute(text("""
            INSERT INTO invoice_match_result
            (invoice_id, po_id, gr_id, match_type, match_status,
             po_total, gr_total, invoice_total,
             quantity_variance, price_variance, total_variance,
             tolerance_percent, is_within_tolerance,
             discrepancy_details, resolution, resolution_notes,
             resolved_by_id, created_at, resolved_at)
            VALUES (:iid, :poid, :grid, '3_WAY', :ms,
             :pot, :grt, :invt,
             :qv, :pv, :tv,
             :tp, :iwt,
             :dd, :res, :rn,
             :rbi, :cat, :ra)
        """), {
            "iid": inv_id, "poid": po_id, "grid": gr_id,
            "ms": match_status,
            "pot": po_total_val, "grt": round(gr_total, 2), "invt": total,
            "qv": 0.0, "pv": round(total - po_total_val - tax, 2),
            "tv": total_variance,
            "tp": 2.0, "iwt": is_within,
            "dd": json.dumps({"type": "price_variance", "amount": total_variance}) if not is_within else None,
            "res": "AUTO_APPROVED" if is_within else ("PENDING_REVIEW" if match_status == "PENDING" else None),
            "rn": "Automatically matched within tolerance" if is_within else None,
            "rbi": USER_ID if is_within else None,
            "cat": now,
            "ra": now if is_within else None,
        })
        count_match += 1

    counters["Invoices"] = count_inv
    counters["Invoice Lines"] = count_lines
    counters["3-Way Match Results"] = count_match
    print(f"  Created {count_inv} invoices, {count_lines} line items, {count_match} match results")


if __name__ == "__main__":
    seed_all()

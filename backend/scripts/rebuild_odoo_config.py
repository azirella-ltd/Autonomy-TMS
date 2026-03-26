#!/usr/bin/env python3
"""
Rebuild a SupplyChainConfig from Odoo CSV exports (translated from SAP IDES).

Usage:
    python scripts/rebuild_odoo_config.py --config-id 114 --csv-dir /path/to/Odoo_Demo

CSV files expected:
    product_template.csv        — Products
    res_partner_vendors.csv     — Vendors
    res_partner_customers.csv   — Customers
    mrp_bom.csv                 — BOM headers
    mrp_bom_line.csv            — BOM components
    product_supplierinfo.csv    — Supplier/product links (for vendor→site lanes)
    stock_warehouse_orderpoint.csv — Reorder rules (inventory policy)
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import sync_session_factory
from sqlalchemy import text


def read_csv(csv_dir: Path, *filenames: str) -> List[Dict[str, str]]:
    for filename in filenames:
        path = csv_dir / filename
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            print(f"  READ {filename}: {len(rows)} rows")
            return rows
    print(f"  SKIP {filenames[0]} (not found)")
    return []


def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    try:
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


def main():
    parser = argparse.ArgumentParser(description="Rebuild SC config from Odoo CSV exports")
    parser.add_argument("--config-id", type=int, required=True)
    parser.add_argument("--csv-dir", type=str, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_id = args.config_id
    csv_dir = Path(args.csv_dir)
    dry_run = args.dry_run

    print(f"\n{'='*70}")
    print(f"  Odoo Config Rebuild")
    print(f"  Config ID: {config_id}")
    print(f"  CSV dir:   {csv_dir}")
    print(f"  Dry run:   {dry_run}")
    print(f"{'='*70}\n")

    # Phase 1: Load CSVs
    print("Phase 1: Loading CSV files...")
    products = read_csv(csv_dir, "product_template.csv")
    vendors = read_csv(csv_dir, "res_partner_vendors.csv")
    customers = read_csv(csv_dir, "res_partner_customers.csv")
    bom_headers = read_csv(csv_dir, "mrp_bom.csv")
    bom_lines = read_csv(csv_dir, "mrp_bom_line.csv")
    supplier_info = read_csv(csv_dir, "product_supplierinfo.csv")
    orderpoints = read_csv(csv_dir, "stock_warehouse_orderpoint.csv")

    # Filter to storable products only
    storable = [p for p in products if p.get("type") == "product"]
    print(f"\n  Storable products: {len(storable)}")

    # Identify manufacturing products (those with BOMs)
    bom_parent_codes = {b["product_code"] for b in bom_headers}
    mfg_products = {p["default_code"] for p in storable if p["default_code"] in bom_parent_codes}
    print(f"  Products with BOMs: {len(mfg_products)}")

    # Vendor→product mapping from supplier_info
    vendor_products = defaultdict(set)
    for si in supplier_info:
        vendor_products[si.get("partner_name", "")].add(si.get("product_code", ""))

    print(f"\n{'='*70}")
    print(f"  Build plan:")
    print(f"    Products:   {len(storable)}")
    print(f"    Vendors:    {len(vendors)} ({len(supplier_info)} supplier-product links)")
    print(f"    Customers:  {len(customers)}")
    print(f"    BOMs:       {len(bom_headers)} headers, {len(bom_lines)} lines")
    print(f"{'='*70}\n")

    if dry_run:
        print("DRY RUN — no database changes")
        return

    # Phase 2: Write to DB
    session = sync_session_factory()

    try:
        # Verify config exists
        row = session.execute(
            text("SELECT name, tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        ).fetchone()
        if not row:
            print(f"ERROR: Config {config_id} not found")
            return
        print(f"Phase 2: Rebuilding config in database...")
        print(f"  Config: {row[0]} (tenant_id={row[1]})")

        # Clean existing data
        print("\n  Deleting existing config data...")
        old_sites = session.execute(
            text("SELECT id FROM site WHERE config_id = :cid"), {"cid": config_id}
        ).fetchall()
        old_products = session.execute(
            text("SELECT id FROM product WHERE config_id = :cid"), {"cid": config_id}
        ).fetchall()

        if old_sites or old_products:
            old_site_ids = [r[0] for r in old_sites]
            old_pid_ids = [r[0] for r in old_products]

            # Delete config-scoped tables
            tables_result = session.execute(text("""
                SELECT table_name FROM information_schema.columns
                WHERE column_name = 'config_id' AND table_schema = 'public'
            """)).fetchall()
            for (table,) in tables_result:
                if table not in ("supply_chain_configs", "site", "product"):
                    session.execute(
                        text(f"DELETE FROM {table} WHERE config_id = :cid"),
                        {"cid": config_id}
                    )
            session.execute(text("DELETE FROM product WHERE config_id = :cid"), {"cid": config_id})
            session.execute(text("DELETE FROM site WHERE config_id = :cid"), {"cid": config_id})
            print(f"    Deleted: {len(old_site_ids)} sites, {len(old_pid_ids)} products")

        # Update config name
        new_name = f"Odoo Bike Demo"
        session.execute(
            text("UPDATE supply_chain_configs SET name = :n, description = :d WHERE id = :cid"),
            {"n": new_name, "d": f"Imported from Odoo on {date.today()}", "cid": config_id}
        )

        # Create sites: 1 warehouse + 1 manufacturing plant
        print("\n  Creating sites...")
        sites_data = [
            ("WH", "Main Warehouse", "WAREHOUSE", "inventory", 1),
            ("MFG-1710", "Manufacturing Plant 1710", "MANUFACTURING_PLANT", "manufacturer", 2),
        ]
        site_ids = {}
        for code, name, stype, mtype, prio in sites_data:
            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority,
                                      is_external, order_aging, attributes)
                    VALUES (:cid, :name, :type, :dag, :mt, :prio, false, 0, '{}')
                """),
                {"cid": config_id, "name": name, "type": stype, "dag": code,
                 "mt": mtype, "prio": prio}
            )
            sid = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": name}
            ).fetchone()[0]
            site_ids[code] = sid
        print(f"    Created {len(sites_data)} internal sites")

        # Trading partners
        print("\n  Creating trading partners...")
        vendor_pks = {}
        for v in vendors:
            ref = v.get("ref", "").strip()
            name = v.get("name", ref)[:200]
            tid = f"ODOOV_{ref}"
            session.execute(
                text("""
                    INSERT INTO trading_partners (id, tpartner_type, description,
                        company_id, source)
                    VALUES (:tid, 'vendor', :desc, 'ODOO_BIKE', 'ODOO')
                    ON CONFLICT (id) DO UPDATE SET description = :desc
                """),
                {"tid": tid, "desc": name}
            )
            pk = session.execute(
                text("SELECT _id FROM trading_partners WHERE id = :tid"),
                {"tid": tid}
            ).fetchone()[0]
            vendor_pks[name] = pk

        customer_pks = {}
        for c in customers:
            ref = c.get("ref", "").strip()
            name = c.get("name", ref)[:200]
            tid = f"ODOOC_{ref}"
            session.execute(
                text("""
                    INSERT INTO trading_partners (id, tpartner_type, description,
                        company_id, source)
                    VALUES (:tid, 'customer', :desc, 'ODOO_BIKE', 'ODOO')
                    ON CONFLICT (id) DO UPDATE SET description = :desc
                """),
                {"tid": tid, "desc": name}
            )
            pk = session.execute(
                text("SELECT _id FROM trading_partners WHERE id = :tid"),
                {"tid": tid}
            ).fetchone()[0]
            customer_pks[name] = pk

        print(f"    Created {len(vendor_pks)} vendors + {len(customer_pks)} customers")

        # Products
        print("\n  Creating products...")
        product_id_map = {}
        for p in storable:
            code = p["default_code"]
            pid = f"CFG{config_id}_{code}"
            name = p.get("name", code)[:200]
            is_mfg = code in mfg_products
            ptype = "FINISHED_GOOD" if is_mfg else "RAW_MATERIAL"
            price = safe_float(p.get("standard_price", "0"))

            session.execute(
                text("""
                    INSERT INTO product (id, config_id, description, product_type, item_type,
                                         unit_cost, base_uom)
                    VALUES (:pid, :cid, :desc, :ptype, :itype, :cost, 'EA')
                """),
                {"pid": pid, "cid": config_id, "desc": name, "ptype": ptype,
                 "itype": "PHYSICAL", "cost": price}
            )
            product_id_map[code] = pid
        print(f"    Created {len(product_id_map)} products")

        # Transportation lanes
        print("\n  Creating transportation lanes...")
        lane_count = 0
        wh_id = site_ids["WH"]
        mfg_id = site_ids["MFG-1710"]

        # Vendor → MFG lanes (from supplier_info)
        seen_vendor_lanes = set()
        for si in supplier_info:
            vname = si.get("partner_name", "")
            vpk = vendor_pks.get(vname)
            if not vpk:
                continue
            lt = safe_int(si.get("delay", "7"), 7)
            lt_json = json.dumps({"type": "deterministic", "value": max(lt, 1)})
            lane_key = (vpk, mfg_id)
            if lane_key in seen_vendor_lanes:
                continue
            seen_vendor_lanes.add(lane_key)

            session.execute(
                text("""
                    INSERT INTO transportation_lane (config_id, from_partner_id, to_site_id,
                                                    supply_lead_time, capacity)
                    VALUES (:cid, :pid, :sid, CAST(:lt AS jsonb), 10000)
                """),
                {"cid": config_id, "pid": vpk, "sid": mfg_id, "lt": lt_json}
            )
            lane_count += 1

        # MFG → WH lane
        session.execute(
            text("""
                INSERT INTO transportation_lane (config_id, from_site_id, to_site_id,
                                                supply_lead_time, capacity)
                VALUES (:cid, :from_id, :to_id,
                        '{"type": "deterministic", "value": 1}'::jsonb, 10000)
            """),
            {"cid": config_id, "from_id": mfg_id, "to_id": wh_id}
        )
        lane_count += 1

        # WH → Customer lanes
        for cname, cpk in customer_pks.items():
            session.execute(
                text("""
                    INSERT INTO transportation_lane (config_id, from_site_id, to_partner_id,
                                                    supply_lead_time, capacity)
                    VALUES (:cid, :sid, :pid,
                            '{"type": "deterministic", "value": 2}'::jsonb, 10000)
                """),
                {"cid": config_id, "sid": wh_id, "pid": cpk}
            )
            lane_count += 1

        print(f"    Created {lane_count} lanes")

        # BOMs
        print("\n  Creating BOMs...")
        bom_count = 0
        for bl in bom_lines:
            parent_code = bl.get("bom_product_code", "")
            child_code = bl.get("product_code", "")
            parent_pid = product_id_map.get(parent_code)
            child_pid = product_id_map.get(child_code)
            if not parent_pid or not child_pid:
                continue

            qty = safe_float(bl.get("product_qty", "1"), 1.0)
            scrap = safe_float(bl.get("scrap_pct", "0"), 0.0)

            session.execute(
                text("""
                    INSERT INTO product_bom (config_id, product_id, component_product_id,
                                            component_quantity, scrap_percentage)
                    VALUES (:cid, :pid, :cpid, :qty, :scrap)
                """),
                {"cid": config_id, "pid": parent_pid, "cpid": child_pid,
                 "qty": qty, "scrap": scrap / 100.0 if scrap > 1 else scrap}
            )
            bom_count += 1
        print(f"    Created {bom_count} BOM lines")

        # Inventory policies from orderpoints
        print("\n  Creating inventory policies...")
        policy_count = 0
        for op in orderpoints:
            code = op.get("product_code", "")
            pid = product_id_map.get(code)
            if not pid:
                continue

            min_qty = safe_float(op.get("product_min_qty", "0"))
            max_qty = safe_float(op.get("product_max_qty", "0"))

            # Determine policy type from Odoo trigger
            trigger = op.get("trigger", "auto")
            if max_qty > 0 and min_qty > 0:
                policy = "abs_level"
            else:
                policy = "doc_dem"

            session.execute(
                text("""
                    INSERT INTO inv_policy (config_id, site_id, product_id,
                                           ss_policy, ss_quantity, order_up_to_level,
                                           reorder_point)
                    VALUES (:cid, :sid, :pid, :policy, :ss, :oul, :rop)
                """),
                {"cid": config_id, "sid": wh_id, "pid": pid,
                 "policy": policy, "ss": min_qty,
                 "oul": max_qty if max_qty > 0 else min_qty * 2,
                 "rop": min_qty}
            )
            policy_count += 1
        print(f"    Created {policy_count} inventory policies")

        session.commit()

        print(f"\n{'='*70}")
        print(f"  SUCCESS — Config {config_id} rebuilt from Odoo CSVs")
        print(f"    Internal Sites:     {len(sites_data)}")
        print(f"    Trading Partners:   {len(vendor_pks) + len(customer_pks)}")
        print(f"    Products:           {len(product_id_map)}")
        print(f"    Lanes:              {lane_count}")
        print(f"    BOMs:               {bom_count}")
        print(f"    Inv Policies:       {policy_count}")
        print(f"{'='*70}")

    except Exception as e:
        print(f"\nERROR: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()

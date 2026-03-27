#!/usr/bin/env python3
"""
Rebuild a SupplyChainConfig from SAP Business One Service Layer or CSV exports.

Connects to a B1 Service Layer instance (or reads CSV exports), extracts
master data, and populates the Autonomy SupplyChainConfig with sites,
products, BOMs, trading partners, inventory, and policies.

Usage:
    # From live B1 instance (Service Layer)
    python scripts/rebuild_b1_config.py --config-id 115 \
        --b1-url https://my-b1:50000/b1s/v2 \
        --company-db SBODemoUS \
        --username manager --password manager

    # From CSV exports
    python scripts/rebuild_b1_config.py --config-id 115 \
        --csv-dir /path/to/b1_csvs

    # Dry run
    python scripts/rebuild_b1_config.py --config-id 115 \
        --csv-dir /path/to/b1_csvs --dry-run

B1 OEC Computers demo data:
    ~4,000 items, ~500 business partners, ~30 BOMs, 3 warehouses
    Company DB: SBODemoUS (US), SBODemoGB (UK), SBODemoDE (DE)

Service Layer entity → DB table mapping:
    Items           → OITM   (products)
    BusinessPartners→ OCRD   (vendors + customers)
    Warehouses      → OWHS   (sites)
    ProductTrees    → OITT   (BOMs)
    Orders          → ORDR   (sales orders)
    PurchaseOrders  → OPOR   (purchase orders)
    ProductionOrders→ OWOR   (manufacturing orders)
"""

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import sync_session_factory
from sqlalchemy import text


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


async def extract_from_service_layer(args) -> Dict[str, List[Dict]]:
    """Extract data from a live B1 instance via Service Layer."""
    from app.integrations.b1.connector import B1Connector, B1ConnectionConfig

    config = B1ConnectionConfig(
        base_url=args.b1_url,
        company_db=args.company_db,
        username=args.username,
        password=args.password,
    )
    connector = B1Connector(config)

    ok = await connector.login()
    if not ok:
        print("ERROR: Failed to login to B1 Service Layer")
        return {}

    info = await connector.test_connection()
    print(f"  Connected: {info.get('company_name', '?')} (v{info.get('version', '?')})")

    data = {}
    entities = [
        "Warehouses",
        "BusinessPartners",
        "Items",
        "ItemGroups",
        "ProductTrees",
        "Orders",
        "PurchaseOrders",
        "ProductionOrders",
    ]
    for entity in entities:
        try:
            records = await connector.query(entity)
            data[entity] = records
            print(f"  {entity}: {len(records)} records")
        except Exception as e:
            print(f"  {entity}: ERROR - {e}")
            data[entity] = []

    # Item-warehouse info needs special handling (sub-entity of Items)
    # Extracted via Items?$expand=ItemWarehouseInfoCollection
    try:
        items_with_wh = await connector.query("Items", expand="ItemWarehouseInfoCollection")
        wh_info = []
        for item in items_with_wh:
            for wh in item.get("ItemWarehouseInfoCollection", []):
                wh["ItemCode"] = item.get("ItemCode")
                wh_info.append(wh)
        data["ItemWarehouseInfoCollection"] = wh_info
        print(f"  ItemWarehouseInfo: {len(wh_info)} records")
    except Exception as e:
        print(f"  ItemWarehouseInfo: ERROR - {e}")
        data["ItemWarehouseInfoCollection"] = []

    await connector.close()
    return data


def extract_from_csv(csv_dir: str) -> Dict[str, List[Dict]]:
    """Extract data from CSV files."""
    data = {}
    csv_path = Path(csv_dir)
    entity_map = {
        "Warehouses": ["Warehouses.csv", "OWHS.csv"],
        "BusinessPartners": ["BusinessPartners.csv", "OCRD.csv"],
        "Items": ["Items.csv", "OITM.csv"],
        "ItemGroups": ["ItemGroups.csv", "OITB.csv"],
        "ProductTrees": ["ProductTrees.csv", "OITT.csv"],
        "ProductTreeLines": ["ProductTreeLines.csv", "ITT1.csv"],
        "Orders": ["Orders.csv", "ORDR.csv"],
        "PurchaseOrders": ["PurchaseOrders.csv", "OPOR.csv"],
        "ProductionOrders": ["ProductionOrders.csv", "OWOR.csv"],
        "ItemWarehouseInfoCollection": ["ItemWarehouseInfoCollection.csv", "OITW.csv"],
    }

    for entity, filenames in entity_map.items():
        for fn in filenames:
            path = csv_path / fn
            if path.exists():
                with open(path, encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
                print(f"  READ {fn}: {len(rows)} rows")
                data[entity] = rows
                break
        if entity not in data:
            print(f"  SKIP {filenames[0]} (not found)")
            data[entity] = []

    return data


def build_config(config_id: int, data: Dict[str, List[Dict]], dry_run: bool = False):
    """Build the SupplyChainConfig from extracted B1 data."""
    from app.integrations.b1.field_mapping import map_card_type

    warehouses = data.get("Warehouses", [])
    partners = data.get("BusinessPartners", [])
    items = data.get("Items", [])
    product_trees = data.get("ProductTrees", [])
    product_tree_lines = data.get("ProductTreeLines", [])
    item_wh_info = data.get("ItemWarehouseInfoCollection", [])

    # Determine manufactured items (have BOMs)
    bom_items: Set[str] = set()
    for pt in product_trees:
        code = pt.get("TreeCode") or pt.get("ItemCode", "")
        if code:
            bom_items.add(code)

    # Separate vendors and customers
    vendors = [p for p in partners if map_card_type(p.get("CardType", "")) == "vendor"]
    customers = [p for p in partners if map_card_type(p.get("CardType", "")) == "customer"]

    print(f"\n  Build plan:")
    print(f"    Warehouses:  {len(warehouses)}")
    print(f"    Items:       {len(items)} ({len(bom_items)} with BOMs)")
    print(f"    Vendors:     {len(vendors)}")
    print(f"    Customers:   {len(customers)}")
    print(f"    BOMs:        {len(product_trees)} headers")

    if dry_run:
        print("\n  DRY RUN — no database changes")
        return

    session = sync_session_factory()

    try:
        # Verify config exists
        row = session.execute(
            text("SELECT name, tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        ).fetchone()
        if not row:
            print(f"  ERROR: Config {config_id} not found")
            return

        tenant_id = row[1]
        print(f"\n  Config: {row[0]} (tenant_id={tenant_id})")

        # Ensure company record exists
        session.execute(
            text("""
                INSERT INTO company (id, description)
                VALUES (:cid, :desc)
                ON CONFLICT (id) DO NOTHING
            """),
            {"cid": f"B1_{config_id}", "desc": f"SAP Business One (config {config_id})"},
        )

        # Clean existing data
        tables_result = session.execute(text("""
            SELECT table_name FROM information_schema.columns
            WHERE column_name = 'config_id' AND table_schema = 'public'
        """)).fetchall()
        for (table,) in tables_result:
            if table not in ("supply_chain_configs", "site", "product"):
                session.execute(
                    text(f"DELETE FROM {table} WHERE config_id = :cid"),
                    {"cid": config_id},
                )
        session.execute(text("DELETE FROM product WHERE config_id = :cid"), {"cid": config_id})
        session.execute(text("DELETE FROM site WHERE config_id = :cid"), {"cid": config_id})
        print("  Cleaned existing data")

        # Create sites from warehouses
        site_ids = {}
        for wh in warehouses:
            code = wh.get("WarehouseCode", "")
            name = wh.get("WarehouseName", code)
            master_type = "manufacturer" if any(
                i.get("ItemCode", "") in bom_items
                for i in item_wh_info
                if i.get("WarehouseCode") == code and safe_float(i.get("InStock", "0")) > 0
            ) else "inventory"

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type,
                                      priority, is_external, order_aging, attributes)
                    VALUES (:cid, :name, :type, :dag, :mt, 1, false, 0, '{}')
                """),
                {"cid": config_id, "name": name[:100], "type": master_type.upper(),
                 "dag": code, "mt": master_type},
            )
            sid = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": name[:100]},
            ).fetchone()[0]
            site_ids[code] = sid
        print(f"  Created {len(site_ids)} sites")

        # Create trading partners
        vendor_pks = {}
        for v in vendors:
            code = v.get("CardCode", "")
            name = (v.get("CardName") or code)[:200]
            tid = f"B1V_{code}"
            session.execute(
                text("""
                    INSERT INTO trading_partners (id, tpartner_type, description,
                        company_id, source)
                    VALUES (:tid, 'vendor', :desc, :co, 'SAP_B1')
                    ON CONFLICT (id) DO UPDATE SET description = :desc
                """),
                {"tid": tid, "desc": name, "co": f"B1_{config_id}"},
            )
            pk = session.execute(
                text("SELECT _id FROM trading_partners WHERE id = :tid"),
                {"tid": tid},
            ).fetchone()[0]
            vendor_pks[code] = pk

        customer_pks = {}
        for c in customers:
            code = c.get("CardCode", "")
            name = (c.get("CardName") or code)[:200]
            tid = f"B1C_{code}"
            session.execute(
                text("""
                    INSERT INTO trading_partners (id, tpartner_type, description,
                        company_id, source)
                    VALUES (:tid, 'customer', :desc, :co, 'SAP_B1')
                    ON CONFLICT (id) DO UPDATE SET description = :desc
                """),
                {"tid": tid, "desc": name, "co": f"B1_{config_id}"},
            )
            pk = session.execute(
                text("SELECT _id FROM trading_partners WHERE id = :tid"),
                {"tid": tid},
            ).fetchone()[0]
            customer_pks[code] = pk
        print(f"  Created {len(vendor_pks)} vendors + {len(customer_pks)} customers")

        # Create products
        product_id_map = {}
        for item in items:
            code = item.get("ItemCode", "")
            name = (item.get("ItemName") or code)[:200]
            pid = f"CFG{config_id}_{code}"
            cost = safe_float(item.get("AvgStdPrice", item.get("AvgPrice", "0")))
            ptype = "FINISHED_GOOD" if code in bom_items else "RAW_MATERIAL"

            session.execute(
                text("""
                    INSERT INTO product (id, config_id, description, product_type,
                                         item_type, unit_cost, base_uom)
                    VALUES (:pid, :cid, :desc, :ptype, 'PHYSICAL', :cost, 'EA')
                """),
                {"pid": pid, "cid": config_id, "desc": name,
                 "ptype": ptype, "cost": cost},
            )
            product_id_map[code] = pid
        print(f"  Created {len(product_id_map)} products")

        # Create lanes (vendor→site, site→site, site→customer)
        lane_count = 0
        first_site_id = next(iter(site_ids.values())) if site_ids else None

        # Vendor → first warehouse
        if first_site_id:
            for vcode, vpk in vendor_pks.items():
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_partner_id, to_site_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :pid, :sid,
                                '{"type": "deterministic", "value": 7}'::jsonb, 10000)
                    """),
                    {"cid": config_id, "pid": vpk, "sid": first_site_id},
                )
                lane_count += 1

            for ccode, cpk in customer_pks.items():
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_partner_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :sid, :pid,
                                '{"type": "deterministic", "value": 2}'::jsonb, 10000)
                    """),
                    {"cid": config_id, "sid": first_site_id, "pid": cpk},
                )
                lane_count += 1

        # Inter-warehouse lanes
        wh_codes = list(site_ids.keys())
        for i, src in enumerate(wh_codes):
            for dst in wh_codes[i + 1:]:
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :src, :dst,
                                '{"type": "deterministic", "value": 1}'::jsonb, 10000)
                    """),
                    {"cid": config_id, "src": site_ids[src], "dst": site_ids[dst]},
                )
                lane_count += 1
        print(f"  Created {lane_count} lanes")

        # BOMs
        bom_count = 0
        for pt in product_trees:
            parent_code = pt.get("TreeCode") or pt.get("ItemCode", "")
            parent_pid = product_id_map.get(parent_code)
            if not parent_pid:
                continue

            # Get BOM lines — either from expanded ProductTrees or separate ProductTreeLines
            lines = pt.get("ProductTreeLines", [])
            if not lines:
                lines = [
                    l for l in product_tree_lines
                    if l.get("TreeCode") == parent_code or l.get("Father") == parent_code
                ]

            for line in lines:
                child_code = line.get("ItemCode", "")
                child_pid = product_id_map.get(child_code)
                if not child_pid:
                    continue
                qty = safe_float(line.get("Quantity", "1"), 1.0)
                if qty <= 0:
                    qty = 1.0

                session.execute(
                    text("""
                        INSERT INTO product_bom (config_id, product_id, component_product_id,
                                                component_quantity, scrap_percentage)
                        VALUES (:cid, :pid, :cpid, :qty, 0)
                    """),
                    {"cid": config_id, "pid": parent_pid, "cpid": child_pid, "qty": qty},
                )
                bom_count += 1
        print(f"  Created {bom_count} BOM lines")

        # Inventory levels + policies from ItemWarehouseInfo
        inv_count = 0
        policy_count = 0
        for whi in item_wh_info:
            item_code = whi.get("ItemCode", "")
            wh_code = whi.get("WarehouseCode", "")
            pid = product_id_map.get(item_code)
            sid = site_ids.get(wh_code)
            if not pid or not sid:
                continue

            on_hand = safe_float(whi.get("InStock", "0"))
            if on_hand > 0:
                session.execute(
                    text("""
                        INSERT INTO inv_level (config_id, site_id, product_id, on_hand_qty)
                        VALUES (:cid, :sid, :pid, :qty)
                    """),
                    {"cid": config_id, "sid": sid, "pid": pid, "qty": on_hand},
                )
                inv_count += 1

            min_stock = safe_float(whi.get("MinimalStock", whi.get("MinStock", "0")))
            max_stock = safe_float(whi.get("MaximalStock", whi.get("MaxStock", "0")))
            if min_stock > 0:
                session.execute(
                    text("""
                        INSERT INTO inv_policy (config_id, site_id, product_id,
                                               ss_policy, ss_quantity, reorder_point,
                                               order_up_to_level)
                        VALUES (:cid, :sid, :pid, 'abs_level', :ss, :rop, :oul)
                    """),
                    {"cid": config_id, "sid": sid, "pid": pid,
                     "ss": min_stock, "rop": min_stock,
                     "oul": max_stock if max_stock > 0 else min_stock * 3},
                )
                policy_count += 1

        print(f"  Created {inv_count} inventory levels, {policy_count} policies")

        session.commit()
        print(f"\n  SUCCESS — Config {config_id} built from SAP Business One")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Rebuild SC config from SAP Business One")
    parser.add_argument("--config-id", type=int, required=True)

    # Service Layer connection
    parser.add_argument("--b1-url", type=str, default="", help="B1 Service Layer URL")
    parser.add_argument("--company-db", type=str, default="SBODemoUS")
    parser.add_argument("--username", type=str, default="manager")
    parser.add_argument("--password", type=str, default="manager")

    # CSV-based
    parser.add_argument("--csv-dir", type=str, default="", help="Directory with B1 CSV exports")

    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  SAP Business One Config Rebuild")
    print(f"  Config ID: {args.config_id}")
    if args.b1_url:
        print(f"  B1 URL:    {args.b1_url}")
        print(f"  Company:   {args.company_db}")
    elif args.csv_dir:
        print(f"  CSV dir:   {args.csv_dir}")
    else:
        print("  ERROR: Specify --b1-url or --csv-dir")
        return
    print(f"  Dry run:   {args.dry_run}")
    print(f"{'='*70}\n")

    if args.b1_url:
        data = asyncio.run(extract_from_service_layer(args))
    elif args.csv_dir:
        data = extract_from_csv(args.csv_dir)
    else:
        return

    if not data:
        print("  No data extracted")
        return

    build_config(args.config_id, data, args.dry_run)


if __name__ == "__main__":
    main()

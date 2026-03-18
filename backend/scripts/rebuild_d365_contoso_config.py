#!/usr/bin/env python3
"""
Rebuild a SupplyChainConfig from Dynamics 365 F&O Contoso (USMF) CSV exports.

Expects CSV files exported via D365 DMF (Data Management Framework) or OData.
Each file named after its D365 entity (e.g. ReleasedProductsV2.csv).

Usage:
    # From backend/ directory
    python scripts/rebuild_d365_contoso_config.py --config-id 82 --csv-dir /path/to/d365_csvs

    # Dry-run (show what would be created, no DB changes)
    python scripts/rebuild_d365_contoso_config.py --config-id 82 --csv-dir /path/to/d365_csvs --dry-run

CSV files expected (from D365 DMF export):
    Required:
        ReleasedProductsV2.csv          — Products (ItemNumber, ProductName, ...)
        Sites.csv  OR OperationalSites.csv  — Operational sites
        Warehouses.csv                  — Warehouses per site
        Vendors.csv  OR VendorsV2.csv   — Vendor master
        CustomersV3.csv                 — Customer master

    Optional (enrich topology):
        BillOfMaterialsHeaders.csv      — BOM headers
        BillOfMaterialsLines.csv        — BOM components
        PurchaseOrderHeadersV2.csv      — PO headers
        PurchaseOrderLinesV2.csv        — PO line items
        SalesOrderHeadersV2.csv         — SO headers
        SalesOrderLinesV2.csv           — SO line items
        InventWarehouseOnHandEntity.csv — On-hand inventory
        ItemCoverageSettings.csv        — Safety stock / coverage
        VendorLeadTimes.csv             — Vendor lead time by product
        DemandForecastEntries.csv       — Demand forecast
        ProductionOrderHeaders.csv      — Production orders
        TransportationRoutes.csv        — Transportation routes

Data area: Defaults to USMF (Contoso Entertainment System USA).
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

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import sync_session_factory
from sqlalchemy import text


# ── Utilities ────────────────────────────────────────────────────────────────

def read_csv(csv_dir: Path, *filenames: str) -> List[Dict[str, str]]:
    """Read a CSV file, return list of dicts. Tries multiple filenames."""
    for filename in filenames:
        path = csv_dir / filename
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            print(f"  READ {filename}: {len(rows)} rows")
            return rows
    print(f"  SKIP {filenames[0]} (not found)")
    return []


def safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default: int = 0) -> int:
    try:
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Rebuild SC config from D365 Contoso CSV exports")
    parser.add_argument("--config-id", type=int, required=True, help="SupplyChainConfig ID to rebuild")
    parser.add_argument("--csv-dir", type=str, required=True, help="Directory containing D365 CSV exports")
    parser.add_argument("--data-area", type=str, default="usmf", help="D365 legal entity (default: usmf)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without DB changes")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    if not csv_dir.is_dir():
        print(f"ERROR: CSV directory not found: {csv_dir}")
        return

    config_id = args.config_id
    data_area = args.data_area.lower()

    print(f"\n{'='*70}")
    print(f"  D365 Contoso Config Rebuild")
    print(f"  Config ID: {config_id}")
    print(f"  CSV dir:   {csv_dir}")
    print(f"  Data area: {data_area}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"{'='*70}")

    # ── Phase 1: Load CSV files ──────────────────────────────────────────
    print("\nPhase 1: Loading CSV files...")

    sites_raw = read_csv(csv_dir, "Sites.csv", "OperationalSites.csv")
    warehouses = read_csv(csv_dir, "Warehouses.csv")
    products_raw = read_csv(csv_dir, "ReleasedProductsV2.csv")
    vendors_raw = read_csv(csv_dir, "Vendors.csv", "VendorsV2.csv")
    customers_raw = read_csv(csv_dir, "CustomersV3.csv")
    bom_headers = read_csv(csv_dir, "BillOfMaterialsHeaders.csv")
    bom_lines = read_csv(csv_dir, "BillOfMaterialsLines.csv")
    po_headers = read_csv(csv_dir, "PurchaseOrderHeadersV2.csv")
    po_lines = read_csv(csv_dir, "PurchaseOrderLinesV2.csv")
    so_headers = read_csv(csv_dir, "SalesOrderHeadersV2.csv")
    so_lines = read_csv(csv_dir, "SalesOrderLinesV2.csv")
    inv_on_hand = read_csv(csv_dir, "InventWarehouseOnHandEntity.csv", "InventoryOnHandEntities.csv")
    coverage = read_csv(csv_dir, "ItemCoverageSettings.csv")
    vendor_lt = read_csv(csv_dir, "VendorLeadTimes.csv")
    forecasts = read_csv(csv_dir, "DemandForecastEntries.csv", "DemandForecastLines.csv")
    prod_orders = read_csv(csv_dir, "ProductionOrderHeaders.csv")
    routes = read_csv(csv_dir, "TransportationRoutes.csv")

    # ── Phase 2: Filter to data area and build lookup maps ───────────────
    print(f"\nPhase 2: Filtering to data area '{data_area}'...")

    def filter_da(rows):
        """Filter rows to the target data area (legal entity)."""
        return [r for r in rows if r.get("dataAreaId", r.get("DataArea", "")).lower() == data_area]

    sites = filter_da(sites_raw) or sites_raw  # Sites may not have dataAreaId
    products = filter_da(products_raw) or products_raw
    vendors = filter_da(vendors_raw) or vendors_raw
    customers = filter_da(customers_raw) or customers_raw
    po_headers = filter_da(po_headers) or po_headers
    po_lines_f = filter_da(po_lines) or po_lines
    so_headers = filter_da(so_headers) or so_headers
    so_lines_f = filter_da(so_lines) or so_lines
    prod_orders = filter_da(prod_orders) or prod_orders

    print(f"  Sites: {len(sites)}")
    print(f"  Products: {len(products)}")
    print(f"  Vendors: {len(vendors)}")
    print(f"  Customers: {len(customers)}")
    print(f"  BOM Headers: {len(bom_headers)}")
    print(f"  BOM Lines: {len(bom_lines)}")
    print(f"  PO Headers: {len(po_headers)}")
    print(f"  SO Headers: {len(so_headers)}")
    print(f"  Inventory: {len(inv_on_hand)}")
    print(f"  Coverage: {len(coverage)}")
    print(f"  Forecasts: {len(forecasts)}")
    print(f"  Production Orders: {len(prod_orders)}")

    # Build lookup maps
    product_map = {}  # ItemNumber → row
    for p in products:
        item = p.get("ItemNumber", "")
        if item:
            product_map[item] = p

    # Determine manufacturing sites (have production orders)
    mfg_sites: Set[str] = set()
    for po in prod_orders:
        s = po.get("SiteId", "")
        if s:
            mfg_sites.add(s)

    # PO vendor counts
    po_num_to_vendor = {h.get("PurchaseOrderNumber", ""): h.get("VendorAccountNumber", "") for h in po_headers}
    vendor_po_counts: Counter = Counter()
    vendor_materials: Dict[str, Set[str]] = defaultdict(set)
    for line in po_lines_f:
        vendor = po_num_to_vendor.get(line.get("PurchaseOrderNumber", ""), "")
        item = line.get("ItemNumber", "")
        if vendor:
            vendor_po_counts[vendor] += 1
            if item:
                vendor_materials[vendor].add(item)

    # SO customer counts
    so_num_to_customer = {h.get("SalesOrderNumber", ""): h.get("CustomerAccountNumber", "") for h in so_headers}
    customer_so_counts: Counter = Counter()
    customer_materials: Dict[str, Set[str]] = defaultdict(set)
    for line in so_lines_f:
        cust = so_num_to_customer.get(line.get("SalesOrderNumber", ""), "")
        item = line.get("ItemNumber", "")
        if cust:
            customer_so_counts[cust] += 1
            if item:
                customer_materials[cust].add(item)

    # Vendor lead time map
    vlt_map: Dict[str, int] = {}  # "vendor|item" → days
    for vl in vendor_lt:
        key = f"{vl.get('VendorAccountNumber', '')}|{vl.get('ItemNumber', '')}"
        vlt_map[key] = safe_int(vl.get("LeadTimeDays", "7"), 7)

    # Inventory on-hand map
    inv_map: Dict[str, float] = {}  # "item|warehouse" → qty
    for inv in inv_on_hand:
        key = f"{inv.get('ItemNumber', '')}|{inv.get('WarehouseId', inv.get('SiteId', ''))}"
        inv_map[key] = safe_float(inv.get("PhysicalOnHandQuantity", inv.get("AvailableQuantity", "0")))

    # Coverage / safety stock map
    cov_map: Dict[str, Dict] = {}  # "item|site" → {ss, min, max}
    for c in coverage:
        key = f"{c.get('ItemNumber', '')}|{c.get('SiteId', '')}"
        cov_map[key] = {
            "ss": safe_float(c.get("SafetyStockQuantity", "0")),
            "min": safe_float(c.get("MinimumInventoryLevel", "0")),
            "max": safe_float(c.get("MaximumInventoryLevel", "0")),
        }

    # Filter products: only include storable/physical items
    EXCLUDE_TYPES = {"Service", "NonInventory"}
    physical_products = {
        item: row for item, row in product_map.items()
        if row.get("ProductType", "") not in EXCLUDE_TYPES
    }
    print(f"\n  Physical products (after filtering): {len(physical_products)}")

    # ── Phase 3: Summary ─────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  Build plan:")
    print(f"    Sites:      {len(sites)} operational + {len(warehouses)} warehouses")
    print(f"    Products:   {len(physical_products)}")
    print(f"    Vendors:    {len(vendors)} ({sum(vendor_po_counts.values())} PO lines)")
    print(f"    Customers:  {len(customers)} ({sum(customer_so_counts.values())} SO lines)")
    print(f"    BOMs:       {len(bom_headers)} headers, {len(bom_lines)} lines")
    print(f"    Mfg sites:  {mfg_sites or 'none detected'}")
    print(f"{'='*70}")

    if args.dry_run:
        print("\n  DRY RUN — no database changes made.")
        return

    # ── Phase 4: Database operations ─────────────────────────────────────
    print("\nPhase 4: Rebuilding config in database...")

    session = sync_session_factory()
    try:
        # Verify config exists
        row = session.execute(
            text("SELECT id, name, tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        ).fetchone()
        if not row:
            print(f"ERROR: Config {config_id} not found")
            return
        tenant_id = row[2]
        print(f"  Config: {row[1]} (tenant_id={tenant_id})")

        # ── Delete existing data ─────────────────────────────────────────
        print("\n  Deleting existing config data...")
        engine = session.get_bind()
        raw_conn = engine.raw_connection()
        cur = raw_conn.cursor()
        try:
            # Get old IDs
            cur.execute("SELECT id FROM site WHERE config_id = %s", (config_id,))
            old_site_ids = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT id FROM product WHERE config_id = %s", (config_id,))
            old_product_ids = [r[0] for r in cur.fetchall()]

            # Delete product_bom
            if old_product_ids:
                pid_list = ",".join(["%s"] * len(old_product_ids))
                cur.execute(
                    f"DELETE FROM product_bom WHERE parent_product_id IN ({pid_list}) OR child_product_id IN ({pid_list})",
                    old_product_ids + old_product_ids,
                )

            # Delete all config-scoped tables
            cur.execute("""
                SELECT table_name FROM information_schema.columns
                WHERE column_name = 'config_id' AND table_schema = 'public'
                  AND table_name != 'supply_chain_configs'
                ORDER BY table_name
            """)
            config_tables = [r[0] for r in cur.fetchall()]
            for table in config_tables:
                if table not in ("site", "product"):
                    cur.execute(f"DELETE FROM {table} WHERE config_id = %s", (config_id,))

            cur.execute("DELETE FROM product WHERE config_id = %s", (config_id,))
            cur.execute("DELETE FROM site WHERE config_id = %s", (config_id,))

            # Update config metadata
            new_name = f"D365 Contoso {data_area.upper()}"
            cur.execute(
                "UPDATE supply_chain_configs SET name = %s, description = %s WHERE id = %s",
                (new_name, f"Imported from D365 F&O Contoso on {date.today()}", config_id),
            )
            raw_conn.commit()
            print(f"    Deleted: {len(old_site_ids)} sites, {len(old_product_ids)} products")
        finally:
            cur.close()
            raw_conn.close()

        # Reopen session
        session = sync_session_factory()
        site_ids: Dict[str, int] = {}  # key → site.id

        # ── Create Sites ─────────────────────────────────────────────────
        print("\n  Creating sites...")

        for s in sites:
            site_id_str = s.get("SiteId", "")
            if not site_id_str:
                continue
            master_type = "MANUFACTURER" if site_id_str in mfg_sites else "INVENTORY"
            site_name = s.get("SiteName", f"Site {site_id_str}")

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority,
                                     order_aging, is_external, company_id, attributes)
                    VALUES (:cid, :name, :type, :dag, :master, 1, 0, false, :company, :attrs)
                """),
                {
                    "cid": config_id,
                    "name": site_id_str[:50],
                    "type": site_name[:100],
                    "dag": master_type,
                    "master": master_type,
                    "company": f"D365_{data_area.upper()}",
                    "attrs": json.dumps({"d365_site": site_id_str, "data_area": data_area}),
                },
            )
            session.flush()
            site_ids[site_id_str] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": site_id_str[:50]},
            ).scalar()

        # Vendor sites (top 50)
        for v_id, count in Counter({v.get("VendorAccountNumber", ""): vendor_po_counts.get(v.get("VendorAccountNumber", ""), 0) for v in vendors}).most_common(50):
            if not v_id:
                continue
            v_info = next((v for v in vendors if v.get("VendorAccountNumber") == v_id), {})
            v_name = v_info.get("VendorName", v_id)
            site_key = f"VEND-{v_id}"

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority,
                                     order_aging, is_external, tpartner_type, attributes)
                    VALUES (:cid, :name, :type, 'SUPPLIER', 'VENDOR', 10, 0, true, 'vendor', :attrs)
                """),
                {
                    "cid": config_id,
                    "name": site_key[:50],
                    "type": f"Supplier - {v_name}"[:100],
                    "attrs": json.dumps({
                        "d365_vendor": v_id,
                        "country": v_info.get("AddressCountryRegionId", ""),
                        "city": v_info.get("AddressCity", ""),
                        "po_lines": count,
                    }),
                },
            )
            session.flush()
            site_ids[site_key] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": site_key[:50]},
            ).scalar()

        # Customer sites (top 50)
        for c_id, count in Counter({c.get("CustomerAccount", ""): customer_so_counts.get(c.get("CustomerAccount", ""), 0) for c in customers}).most_common(50):
            if not c_id:
                continue
            c_info = next((c for c in customers if c.get("CustomerAccount") == c_id), {})
            c_name = c_info.get("CustomerName", c_id)
            site_key = f"CUST-{c_id}"

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority,
                                     order_aging, is_external, tpartner_type, attributes)
                    VALUES (:cid, :name, :type, 'CUSTOMER', 'CUSTOMER', 10, 0, true, 'customer', :attrs)
                """),
                {
                    "cid": config_id,
                    "name": site_key[:50],
                    "type": f"Customer - {c_name}"[:100],
                    "attrs": json.dumps({
                        "d365_customer": c_id,
                        "country": c_info.get("AddressCountryRegionId", ""),
                        "city": c_info.get("AddressCity", ""),
                        "so_lines": count,
                    }),
                },
            )
            session.flush()
            site_ids[site_key] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": site_key[:50]},
            ).scalar()

        print(f"    Created {len(site_ids)} sites")

        # ── Create Products ──────────────────────────────────────────────
        print("\n  Creating products...")
        prod_ids: Dict[str, str] = {}  # ItemNumber → product.id (string)

        for item_num, p in physical_products.items():
            prod_id = f"CFG{config_id}_{item_num}"
            prod_name = p.get("ProductName", item_num)
            prod_type_raw = p.get("ProductType", "Item")

            unit_cost = safe_float(p.get("ProductionStandardCost", "0"))
            if unit_cost == 0:
                unit_cost = safe_float(p.get("SalesPrice", "0"))
            if unit_cost == 0:
                unit_cost = 10.0  # default

            base_uom = p.get("InventoryUnitSymbol", "EA")

            session.execute(
                text("""
                    INSERT INTO product (id, config_id, description, product_type, item_type,
                                        base_uom, unit_cost, is_active, source)
                    VALUES (:pid, :cid, :desc, :ptype, 'material', :uom, :cost, 'Y', 'D365_CONTOSO')
                """),
                {
                    "pid": prod_id,
                    "cid": config_id,
                    "desc": prod_name[:500],
                    "ptype": prod_type_raw[:50],
                    "uom": (base_uom or "EA")[:20],
                    "cost": unit_cost,
                },
            )
            prod_ids[item_num] = prod_id

        session.flush()
        print(f"    Created {len(prod_ids)} products")

        # ── Create Transportation Lanes ──────────────────────────────────
        print("\n  Creating transportation lanes...")
        lane_count = 0

        # Pick the first operational site as primary hub
        primary_site = next(iter(site_ids.keys() - {k for k in site_ids if k.startswith(("VEND-", "CUST-"))}), None)

        # Vendor → primary site
        for v in vendors[:50]:
            v_id = v.get("VendorAccountNumber", "")
            site_key = f"VEND-{v_id}"
            from_id = site_ids.get(site_key)
            to_id = site_ids.get(primary_site) if primary_site else None
            if from_id and to_id:
                # Use vendor-specific lead time if available
                lt_days = 7
                for item in vendor_materials.get(v_id, set()):
                    lt = vlt_map.get(f"{v_id}|{item}")
                    if lt:
                        lt_days = lt
                        break

                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, source_id, destination_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id,
                                :lt::jsonb, 10000)
                    """),
                    {
                        "cid": config_id,
                        "from_id": from_id,
                        "to_id": to_id,
                        "lt": json.dumps({"mean": lt_days, "std": max(1, lt_days // 3), "distribution": "lognormal"}),
                    },
                )
                lane_count += 1

        # Inter-site lanes (between operational sites)
        op_sites = [k for k in site_ids if not k.startswith(("VEND-", "CUST-"))]
        for i, src in enumerate(op_sites):
            for dst in op_sites[i+1:]:
                from_id = site_ids.get(src)
                to_id = site_ids.get(dst)
                if from_id and to_id:
                    session.execute(
                        text("""
                            INSERT INTO transportation_lane (config_id, source_id, destination_id,
                                                            supply_lead_time, capacity)
                            VALUES (:cid, :from_id, :to_id,
                                    '{"mean": 2, "std": 0.5, "distribution": "normal"}'::jsonb, 10000)
                        """),
                        {"cid": config_id, "from_id": from_id, "to_id": to_id},
                    )
                    lane_count += 1

        # Primary site → customer
        for c in customers[:50]:
            c_id = c.get("CustomerAccount", "")
            site_key = f"CUST-{c_id}"
            from_id = site_ids.get(primary_site) if primary_site else None
            to_id = site_ids.get(site_key)
            if from_id and to_id:
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, source_id, destination_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id,
                                '{"mean": 3, "std": 1, "distribution": "lognormal"}'::jsonb, 10000)
                    """),
                    {"cid": config_id, "from_id": from_id, "to_id": to_id},
                )
                lane_count += 1

        # From explicit routes
        for r in routes:
            src = r.get("OriginSiteId", "")
            dst = r.get("DestinationSiteId", "")
            from_id = site_ids.get(src)
            to_id = site_ids.get(dst)
            if from_id and to_id:
                lt = safe_int(r.get("TransitTimeDays", "3"), 3)
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, source_id, destination_id,
                                                        supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id, :lt::jsonb, 10000)
                    """),
                    {
                        "cid": config_id,
                        "from_id": from_id,
                        "to_id": to_id,
                        "lt": json.dumps({"mean": lt, "std": max(1, lt // 3), "distribution": "lognormal"}),
                    },
                )
                lane_count += 1

        session.flush()
        print(f"    Created {lane_count} lanes")

        # ── Create BOMs ──────────────────────────────────────────────────
        print("\n  Creating BOMs...")
        bom_count = 0

        bom_id_to_product = {}
        for bh in bom_headers:
            bom_id_to_product[bh.get("BOMId", "")] = bh.get("ProductNumber", bh.get("ItemNumber", ""))

        for bl in bom_lines:
            bom_id = bl.get("BOMId", "")
            parent_item = bom_id_to_product.get(bom_id)
            component_item = bl.get("ItemNumber", "")
            if not parent_item or not component_item:
                continue
            parent_pid = prod_ids.get(parent_item)
            component_pid = prod_ids.get(component_item)
            if not parent_pid or not component_pid:
                continue

            qty = safe_float(bl.get("BOMLineQuantity", "1"), 1.0)
            scrap = safe_float(bl.get("ScrapPercentage", "0"), 0.0)

            session.execute(
                text("""
                    INSERT INTO product_bom (config_id, parent_product_id, child_product_id,
                                            quantity_per, scrap_rate)
                    VALUES (:cid, :pid, :cpid, :qty, :scrap)
                """),
                {
                    "cid": config_id,
                    "pid": parent_pid,
                    "cpid": component_pid,
                    "qty": qty,
                    "scrap": scrap / 100.0 if scrap > 1 else scrap,
                },
            )
            bom_count += 1

        session.flush()
        print(f"    Created {bom_count} BOM lines")

        # ── Create Inventory Levels ──────────────────────────────────────
        print("\n  Creating inventory levels...")
        inv_count = 0
        today = date.today()

        # For each product at the primary site
        if primary_site and site_ids.get(primary_site):
            primary_site_db_id = site_ids[primary_site]
            for item_num, prod_id in prod_ids.items():
                # Sum inventory across all warehouses for this item
                total_qty = 0.0
                for key, qty in inv_map.items():
                    if key.startswith(f"{item_num}|"):
                        total_qty += qty

                session.execute(
                    text("""
                        INSERT INTO inv_level (config_id, site_id, product_id, on_hand_qty,
                                              in_transit_qty, allocated_qty, inventory_date, source)
                        VALUES (:cid, :sid, :pid, :qty, 0, 0, :dt, 'D365_CONTOSO')
                    """),
                    {
                        "cid": config_id,
                        "sid": primary_site_db_id,
                        "pid": prod_id,
                        "qty": total_qty,
                        "dt": today,
                    },
                )
                inv_count += 1

        session.flush()
        print(f"    Created {inv_count} inventory levels")

        # ── Create Inventory Policies ────────────────────────────────────
        print("\n  Creating inventory policies...")
        pol_count = 0

        if primary_site and site_ids.get(primary_site):
            primary_site_db_id = site_ids[primary_site]
            for item_num, prod_id in prod_ids.items():
                cov = cov_map.get(f"{item_num}|{primary_site}", {})
                ss = cov.get("ss", 0)
                rop = cov.get("min", 0)

                if ss == 0 and rop == 0:
                    # Default based on product cost
                    cost = safe_float(physical_products.get(item_num, {}).get("ProductionStandardCost", "0"))
                    ss = 25.0 if cost > 100 else 50.0
                    rop = ss * 2
                    source = "DEFAULT"
                else:
                    source = "D365_COVERAGE"

                session.execute(
                    text("""
                        INSERT INTO inv_policy (config_id, site_id, product_id, ss_policy,
                                              ss_quantity, reorder_point, service_level,
                                              review_period, is_active, source)
                        VALUES (:cid, :sid, :pid, 'abs_level', :ss, :rop, 0.95, 7, 'Y', :src)
                    """),
                    {
                        "cid": config_id,
                        "sid": primary_site_db_id,
                        "pid": prod_id,
                        "ss": ss,
                        "rop": rop,
                        "src": source,
                    },
                )
                pol_count += 1

        session.flush()
        print(f"    Created {pol_count} inventory policies")

        # ── Commit ───────────────────────────────────────────────────────
        session.commit()
        print(f"\n{'='*70}")
        print(f"  SUCCESS — Config {config_id} rebuilt from D365 Contoso ({data_area.upper()})")
        print(f"    Sites:     {len(site_ids)}")
        print(f"    Products:  {len(prod_ids)}")
        print(f"    Lanes:     {lane_count}")
        print(f"    BOMs:      {bom_count}")
        print(f"    Inv Lvls:  {inv_count}")
        print(f"    Policies:  {pol_count}")
        print(f"{'='*70}")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()

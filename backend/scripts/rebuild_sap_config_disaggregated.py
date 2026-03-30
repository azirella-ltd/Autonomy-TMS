#!/usr/bin/env python3
"""
Rebuild SAP FAA config with disaggregated (individual) customer/supplier sites.

Fixes three problems with the current config 82 ("Country Template IT SC Network"):
1. Customers were aggregated into regional buckets (DEMAND_AMERICAS, DEMAND_EUROPE, etc.)
   → Creates individual customer sites (one per active customer from sales orders)
2. Suppliers were aggregated into regional buckets (SUPPLY_US, SUPPLY_EUROPE, etc.)
   → Creates individual vendor sites (one per active vendor from purchase orders)
3. Only 185 of 2790 products had inventory policies
   → Creates abs_level inventory policies for ALL products at the manufacturing site

Data source: SAP S/4HANA FAA (IDES) extract at imports/sap_faa_extract/
Primary plant: 1710 (Plant 1 US, Palo Alto) — the only plant with transactional data

Usage:
    # Run inside Docker container:
    docker compose exec backend python scripts/rebuild_sap_config_disaggregated.py

    # Or locally:
    python scripts/rebuild_sap_config_disaggregated.py [--config-id 82] [--dry-run]
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

os.environ.setdefault("DATABASE_TYPE", "postgresql")

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def read_csv(csv_dir: Path, filename: str) -> List[Dict[str, str]]:
    """Read a CSV file, return list of dicts. Returns [] if missing."""
    path = csv_dir / filename
    if not path.exists():
        print(f"  SKIP {filename} (not found)")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  READ {filename}: {len(rows)} rows")
    return rows


def safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def strip_zeros(val: str) -> str:
    if val and val.isdigit():
        return val.lstrip("0") or "0"
    return val.strip() if val else val


# ---------------------------------------------------------------------------
# Main rebuild
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Rebuild SAP config with individual sites")
    parser.add_argument("--config-id", type=int, default=None, help="Config ID to rebuild (auto-detects SAP demo if not specified)")
    parser.add_argument("--csv-dir", type=str, default="imports/sap_faa_extract",
                        help="Directory with SAP CSV extracts")
    parser.add_argument("--plant", type=str, default="1710",
                        help="Primary SAP plant code (default: 1710)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without modifying DB")
    args = parser.parse_args()

    # Auto-detect SAP demo config if not specified
    if args.config_id is None:
        from app.db.session import sync_session_factory
        from sqlalchemy import text
        _db = sync_session_factory()
        row = _db.execute(text(
            "SELECT sc.id FROM supply_chain_configs sc "
            "JOIN tenants t ON t.id = sc.tenant_id "
            "WHERE t.slug = 'sap-demo' ORDER BY sc.id DESC LIMIT 1"
        )).fetchone()
        if row:
            args.config_id = row[0]
            print(f"Auto-detected SAP demo config: {args.config_id}")
        else:
            print("ERROR: No SAP demo config found. Use --config-id explicitly.")
            sys.exit(1)
        _db.close()

    csv_dir = Path(args.csv_dir)
    if not csv_dir.exists():
        # Try relative to project root
        csv_dir = Path(__file__).resolve().parent.parent / args.csv_dir
    if not csv_dir.exists():
        print(f"ERROR: CSV directory not found: {csv_dir}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"Rebuild SAP Config (Disaggregated)")
    print(f"  Config ID: {args.config_id}")
    print(f"  CSV dir:   {csv_dir}")
    print(f"  Plant:     {args.plant}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"{'='*70}\n")

    # -----------------------------------------------------------------------
    # 1. Load SAP CSV data
    # -----------------------------------------------------------------------
    print("Phase 1: Loading SAP CSV data...")
    t001w = read_csv(csv_dir, "T001W.csv")
    kna1 = read_csv(csv_dir, "KNA1.csv")
    lfa1 = read_csv(csv_dir, "LFA1.csv")
    marc = read_csv(csv_dir, "MARC.csv")
    makt = read_csv(csv_dir, "MAKT.csv")
    mara = read_csv(csv_dir, "MARA.csv")
    mard = read_csv(csv_dir, "MARD.csv")
    vbak = read_csv(csv_dir, "VBAK.csv")
    vbap = read_csv(csv_dir, "VBAP.csv")
    ekko = read_csv(csv_dir, "EKKO.csv")
    ekpo = read_csv(csv_dir, "EKPO.csv")
    afko = read_csv(csv_dir, "AFKO.csv")

    PRIMARY = args.plant

    # -----------------------------------------------------------------------
    # 2. Identify active entities for this plant
    # -----------------------------------------------------------------------
    print(f"\nPhase 2: Identifying active entities for plant {PRIMARY}...")

    # Build lookup maps first (needed for filtering)
    makt_map = {}
    for r in makt:
        mat = r.get("MATNR", "")
        if mat and mat not in makt_map:
            makt_map[mat] = r.get("MAKTX", mat)

    mara_map = {}
    for r in mara:
        mat = r.get("MATNR", "")
        if mat:
            mara_map[mat] = r

    # Materials at this plant — filter to physical products with transactional data
    marc_plant = [r for r in marc if r.get("WERKS") == PRIMARY]
    all_materials_at_plant = {r["MATNR"] for r in marc_plant}
    print(f"  All materials at plant {PRIMARY}: {len(all_materials_at_plant)}")

    # Exclude non-physical material types (services, packaging, vehicles, etc.)
    EXCLUDE_MTART = {"SERV", "DIEN", "NLAG", "VERP", "LEIH", "PIPE", "VEHI", "SWNV", "UNSF", "UNFR"}
    physical_materials = set()
    for mat in all_materials_at_plant:
        mara_row = mara_map.get(mat, {})
        mtart = mara_row.get("MTART", "") if isinstance(mara_row, dict) else ""
        if mtart not in EXCLUDE_MTART:
            physical_materials.add(mat)

    # Further filter to materials with actual orders (sales or purchase)
    vbap_mats = {r.get("MATNR") for r in vbap if r.get("WERKS") == PRIMARY}
    ekpo_mats = {r.get("MATNR") for r in ekpo if r.get("WERKS") == PRIMARY}
    ordered_materials = vbap_mats | ekpo_mats
    materials = physical_materials & ordered_materials
    print(f"  Physical materials: {len(physical_materials)}")
    print(f"  Materials with orders: {len(ordered_materials & all_materials_at_plant)}")
    print(f"  Final product set (physical + ordered): {len(materials)}")

    # Active customers (from sales orders targeting this plant)
    vbap_plant = [r for r in vbap if r.get("WERKS") == PRIMARY]
    vbeln_to_kunnr = {r["VBELN"]: r.get("KUNNR", "") for r in vbak}
    customer_order_counts: Counter = Counter()
    customer_materials: Dict[str, Set[str]] = defaultdict(set)
    for r in vbap_plant:
        kunnr = vbeln_to_kunnr.get(r.get("VBELN", ""), "")
        if kunnr:
            customer_order_counts[kunnr] += 1
            customer_materials[kunnr].add(r.get("MATNR", ""))
    print(f"  Active customers: {len(customer_order_counts)}")

    # Customer master lookup
    kna1_map = {}
    for r in kna1:
        k = r.get("KUNNR", "")
        if k and k not in kna1_map:
            kna1_map[k] = r

    # Active vendors (from POs targeting this plant)
    ekpo_plant = [r for r in ekpo if r.get("WERKS") == PRIMARY]
    ebeln_to_lifnr = {r["EBELN"]: r.get("LIFNR", "") for r in ekko}
    vendor_po_counts: Counter = Counter()
    vendor_materials: Dict[str, Set[str]] = defaultdict(set)
    for r in ekpo_plant:
        lifnr = ebeln_to_lifnr.get(r.get("EBELN", ""), "")
        if lifnr:
            vendor_po_counts[lifnr] += 1
            vendor_materials[lifnr].add(r.get("MATNR", ""))
    print(f"  Active vendors: {len(vendor_po_counts)}")

    # Production indicator (BESKZ): E = in-house, F = external procurement
    mat_beskz = {}
    for r in marc_plant:
        mat_beskz[r["MATNR"]] = r.get("BESKZ", "")

    # Safety stock and planning parameters from MARC
    mat_eisbe = {}
    mat_minbe = {}
    mat_marc_params = {}  # Full MARC planning fields per material
    for r in marc_plant:
        mat = r["MATNR"]
        mat_eisbe[mat] = safe_float(r.get("EISBE", "0"))
        mat_minbe[mat] = safe_float(r.get("MINBE", "0"))
        mat_marc_params[mat] = {
            "DISMM": (r.get("DISMM", "") or "").strip(),
            "DISLS": (r.get("DISLS", "") or "").strip(),
            "LOSGR": safe_float(r.get("LOSGR", "0")),
            "BSTMI": safe_float(r.get("BSTMI", "0")),
            "BSTMA": safe_float(r.get("BSTMA", "0")),
            "BSTRF": safe_float(r.get("BSTRF", "0")),
            "MABST": safe_float(r.get("MABST", "0")),
            "VRMOD": (r.get("VRMOD", "") or "").strip(),
            "VINT1": int(safe_float(r.get("VINT1", "0"))),
            "VINT2": int(safe_float(r.get("VINT2", "0"))),
            "FXHOR": int(safe_float(r.get("FXHOR", "0"))),
            "STRGR": (r.get("STRGR", "") or "").strip(),
            "DISPO": (r.get("DISPO", "") or "").strip(),
            "BESKZ": (r.get("BESKZ", "") or "").strip(),
            "SHZET": int(safe_float(r.get("SHZET", "0"))),
            "PLIFZ": int(safe_float(r.get("PLIFZ", "0"))),
            "DZEIT": int(safe_float(r.get("DZEIT", "0"))),
            "AUSSS": safe_float(r.get("AUSSS", "0")),
            "RDPRF": (r.get("RDPRF", "") or "").strip(),
        }

    # Stock levels from MARD
    mat_stock = defaultdict(float)
    for r in mard:
        if r.get("WERKS") == PRIMARY:
            mat_stock[r["MATNR"]] += safe_float(r.get("LABST", "0"))

    # Check for secondary plant (1720 in the US case)
    secondary_plants = set()
    for r in t001w:
        werks = r.get("WERKS", "")
        if werks != PRIMARY and werks.startswith(PRIMARY[:2]):
            secondary_plants.add(werks)
    print(f"  Secondary plants (same country prefix): {secondary_plants or 'none'}")

    # -----------------------------------------------------------------------
    # 3. Print summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"REBUILD PLAN")
    print(f"{'='*70}")

    # Plant info
    plant_info = next((r for r in t001w if r.get("WERKS") == PRIMARY), {})
    plant_name = plant_info.get("NAME1", f"Plant {PRIMARY}")
    plant_country = plant_info.get("LAND1", "??")
    plant_city = plant_info.get("ORT01", "")
    print(f"\n  Internal Sites:")
    print(f"    {PRIMARY}: {plant_name} ({plant_city}, {plant_country}) — MANUFACTURER")
    for sp in sorted(secondary_plants):
        sp_info = next((r for r in t001w if r.get("WERKS") == sp), {})
        print(f"    {sp}: {sp_info.get('NAME1', sp)} ({sp_info.get('ORT01', '')}, {sp_info.get('LAND1', '')}) — INVENTORY")

    print(f"\n  Customer Sites ({len(customer_order_counts)} individual, NO aggregation):")
    for cust_id, count in customer_order_counts.most_common():
        info = kna1_map.get(cust_id, {})
        name = info.get("NAME1", cust_id)
        country = info.get("LAND1", "?")
        city = info.get("ORT01", "")
        n_mats = len(customer_materials.get(cust_id, set()))
        print(f"    CUST-{cust_id}: {name} ({city}, {country}) — {count} order lines, {n_mats} products")

    # Vendor master lookup
    lfa1_map = {}
    for r in lfa1:
        v = r.get("LIFNR", "")
        if v and v not in lfa1_map:
            lfa1_map[v] = r

    print(f"\n  Vendor Sites ({len(vendor_po_counts)} individual, NO aggregation):")
    for v_id, count in vendor_po_counts.most_common():
        info = lfa1_map.get(v_id, {})
        name = info.get("NAME1", v_id)
        country = info.get("LAND1", "?")
        city = info.get("ORT01", "")
        n_mats = len(vendor_materials.get(v_id, set()))
        print(f"    VEND-{v_id}: {name} ({city}, {country}) — {count} PO lines, {n_mats} products")

    print(f"\n  Products: {len(materials)} total")
    n_manufactured = sum(1 for m in materials if mat_beskz.get(m) == "E")
    n_procured = sum(1 for m in materials if mat_beskz.get(m) == "F")
    print(f"    Manufactured (BESKZ=E): {n_manufactured}")
    print(f"    Procured (BESKZ=F): {n_procured}")
    print(f"    Other: {len(materials) - n_manufactured - n_procured}")

    n_with_ss = sum(1 for m in materials if mat_eisbe.get(m, 0) > 0 or mat_minbe.get(m, 0) > 0)
    print(f"\n  Inventory Policies:")
    print(f"    Products with SAP safety stock/reorder point: {n_with_ss}")
    print(f"    Products needing default policy: {len(materials) - n_with_ss}")
    print(f"    TOTAL policies to create: {len(materials)} (one per product at plant)")

    if args.dry_run:
        print(f"\n  DRY RUN — no database changes made.")
        return

    # -----------------------------------------------------------------------
    # 4. Connect to database and rebuild
    # -----------------------------------------------------------------------
    print(f"\nPhase 3: Rebuilding config {args.config_id} in database...")

    from app.db.session import sync_session_factory
    from sqlalchemy import text

    session = sync_session_factory()

    try:
        config_id = args.config_id

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

        new_name = f"SAP IDES {PRIMARY} — {plant_name}"
        print(f"  Will rename to: {new_name}")

        # ---------------------------------------------------------------
        # 4a. Delete existing sites, products, lanes, policies, etc.
        # ---------------------------------------------------------------
        print("  Deleting existing entities...")

        # Use raw connection with a simple, reliable deletion approach.
        # Temporarily disable FK checks, delete everything, re-enable.
        from sqlalchemy import create_engine
        engine = session.get_bind()
        raw_conn = engine.raw_connection()
        cur = raw_conn.cursor()
        try:
            # Collect site IDs and product IDs before deletion
            cur.execute("SELECT id FROM site WHERE config_id = %s", (config_id,))
            old_site_ids = [r[0] for r in cur.fetchall()]

            cur.execute("SELECT id FROM product WHERE config_id = %s", (config_id,))
            old_product_ids = [r[0] for r in cur.fetchall()]

            # Disable FK triggers temporarily (requires superuser or table owner)
            # Alternative: delete in correct order using explicit queries
            tables_to_clean = []

            # 1. Delete all rows from tables with config_id
            cur.execute("""
                SELECT table_name FROM information_schema.columns
                WHERE column_name = 'config_id' AND table_schema = 'public'
                  AND table_name != 'supply_chain_configs'
                ORDER BY table_name
            """)
            config_tables = [r[0] for r in cur.fetchall()]

            # 2. Delete product_bom via product FK
            if old_product_ids:
                pid_list = ",".join(["%s"] * len(old_product_ids))
                cur.execute(f"DELETE FROM product_bom WHERE product_id IN ({pid_list}) OR component_product_id IN ({pid_list})",
                           old_product_ids + old_product_ids)
                if cur.rowcount > 0:
                    print(f"    Deleted {cur.rowcount} rows from product_bom")

            # 3. Delete site-referencing tables (that don't have config_id)
            if old_site_ids:
                sid_list = ",".join(["%s"] * len(old_site_ids))
                # Find all tables that have site_id, from_site_id, or to_site_id columns
                for col_name in ["site_id", "from_site_id", "to_site_id", "ship_from_site_id"]:
                    cur.execute("""
                        SELECT DISTINCT table_name FROM information_schema.columns
                        WHERE column_name = %s AND table_schema = 'public'
                    """, (col_name,))
                    ref_tables = [r[0] for r in cur.fetchall()]
                    for table in ref_tables:
                        if table == "site":
                            continue
                        try:
                            cur.execute(f"DELETE FROM {table} WHERE {col_name} IN ({sid_list})", old_site_ids)
                            if cur.rowcount > 0:
                                print(f"    Deleted {cur.rowcount} rows from {table} (via {col_name})")
                        except Exception as e:
                            raw_conn.rollback()
                            cur = raw_conn.cursor()

            # 4. Delete all dependent tables, then core tables
            # Order: product-dependent → config-scoped → product → site
            all_tables_ordered = [
                # Product-dependent tables (must be deleted before product)
                "inv_level", "inv_policy", "inv_projection", "inventory_projection",
                "forecast", "sourcing_rules", "supply_demand_pegging",
                "aatp_consumption_record", "site_planning_config",
                "atp_projection", "ctp_projection", "backorder",
                "consensus_demand", "forecast_exception",
                "monte_carlo_time_series", "monte_carlo_risk_alerts",
                "mps_plan_items", "product_bom",
            ]
            # Add remaining config_id tables (skip site/product — they go last)
            for table in config_tables:
                if table not in ("site", "product") and table not in all_tables_ordered:
                    all_tables_ordered.append(table)
            # Core tables last
            all_tables_ordered.extend(["product", "site"])

            for table in all_tables_ordered:
                try:
                    cur.execute(f"SAVEPOINT sp_{table}")
                    cur.execute(f"DELETE FROM {table} WHERE config_id = %s", (config_id,))
                    if cur.rowcount > 0:
                        print(f"    Deleted {cur.rowcount} rows from {table}")
                    cur.execute(f"RELEASE SAVEPOINT sp_{table}")
                except Exception:
                    cur.execute(f"ROLLBACK TO SAVEPOINT sp_{table}")
                    cur.execute(f"RELEASE SAVEPOINT sp_{table}")

            # Update config name
            cur.execute("UPDATE supply_chain_configs SET name = %s WHERE id = %s", (new_name, config_id))

            raw_conn.commit()
            print("  Deletion complete.")
        except Exception as e:
            raw_conn.rollback()
            raise RuntimeError(f"Deletion failed: {e}") from e
        finally:
            cur.close()
            raw_conn.close()

        # Reopen session for inserts
        session = sync_session_factory()

        # ---------------------------------------------------------------
        # 4b. Create internal sites (plants)
        # ---------------------------------------------------------------
        print("  Creating internal sites...")

        site_ids = {}  # key -> DB id

        # Primary manufacturing plant
        session.execute(
            text("""
                INSERT INTO site (config_id, name, type, dag_type, master_type, priority, order_aging, is_external, company_id, attributes)
                VALUES (:cid, :name, :type, 'MANUFACTURER', 'MANUFACTURER', 1, 0, false, :company, :attrs)
            """),
            {
                "cid": config_id,
                "name": PRIMARY,
                "type": plant_name,
                "company": f"CC_{PRIMARY}",
                "attrs": f'{{"sap_plant": "{PRIMARY}", "city": "{plant_city}", "country": "{plant_country}"}}',
            },
        )
        session.flush()
        site_ids[PRIMARY] = session.execute(
            text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
            {"cid": config_id, "name": PRIMARY},
        ).scalar()
        print(f"    Created {PRIMARY}: {plant_name} (id={site_ids[PRIMARY]})")

        # Secondary plants
        for sp in sorted(secondary_plants):
            sp_info = next((r for r in t001w if r.get("WERKS") == sp), {})
            sp_name = sp_info.get("NAME1", f"Plant {sp}")
            sp_city = sp_info.get("ORT01", "")
            sp_country = sp_info.get("LAND1", "")
            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority, order_aging, is_external, company_id, attributes)
                    VALUES (:cid, :name, :type, 'DISTRIBUTION_CENTER', 'INVENTORY', 2, 0, false, :company, :attrs)
                """),
                {
                    "cid": config_id,
                    "name": sp,
                    "type": sp_name,
                    "company": f"CC_{PRIMARY}",
                    "attrs": f'{{"sap_plant": "{sp}", "city": "{sp_city}", "country": "{sp_country}"}}',
                },
            )
            session.flush()
            site_ids[sp] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": sp},
            ).scalar()
            print(f"    Created {sp}: {sp_name} (id={site_ids[sp]})")

        # ---------------------------------------------------------------
        # 4c. Create individual customer sites
        # ---------------------------------------------------------------
        print("  Creating individual customer sites...")

        for cust_id, count in customer_order_counts.most_common():
            info = kna1_map.get(cust_id, {})
            name = info.get("NAME1", cust_id)
            country = info.get("LAND1", "US")
            city = info.get("ORT01", "")
            site_key = f"CUST-{cust_id}"

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority, order_aging, is_external, tpartner_type, attributes)
                    VALUES (:cid, :name, :type, 'CUSTOMER', 'CUSTOMER', 10, 0, true, 'customer', :attrs)
                """),
                {
                    "cid": config_id,
                    "name": site_key,
                    "type": name,
                    "attrs": f'{{"sap_customer": "{cust_id}", "city": "{city}", "country": "{country}", "order_lines": {count}}}',
                },
            )
            session.flush()
            site_ids[site_key] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": site_key},
            ).scalar()

        print(f"    Created {len(customer_order_counts)} customer sites")

        # ---------------------------------------------------------------
        # 4d. Create individual vendor sites
        # ---------------------------------------------------------------
        print("  Creating individual vendor sites...")

        for v_id, count in vendor_po_counts.most_common():
            info = lfa1_map.get(v_id, {})
            name = info.get("NAME1", v_id)
            country = info.get("LAND1", "US")
            city = info.get("ORT01", "")
            site_key = f"VEND-{v_id}"

            session.execute(
                text("""
                    INSERT INTO site (config_id, name, type, dag_type, master_type, priority, order_aging, is_external, tpartner_type, attributes)
                    VALUES (:cid, :name, :type, 'SUPPLIER', 'VENDOR', 10, 0, true, 'vendor', :attrs)
                """),
                {
                    "cid": config_id,
                    "name": site_key,
                    "type": name,
                    "attrs": f'{{"sap_vendor": "{v_id}", "city": "{city}", "country": "{country}", "po_lines": {count}}}',
                },
            )
            session.flush()
            site_ids[site_key] = session.execute(
                text("SELECT id FROM site WHERE config_id = :cid AND name = :name"),
                {"cid": config_id, "name": site_key},
            ).scalar()

        print(f"    Created {len(vendor_po_counts)} vendor sites")

        # ---------------------------------------------------------------
        # 4e. Create products
        # ---------------------------------------------------------------
        print(f"  Creating {len(materials)} products...")

        product_count = 0
        for mat_id in sorted(materials):
            desc = makt_map.get(mat_id, mat_id)
            mara_row = mara_map.get(mat_id, {})
            prod_id = f"CFG{config_id}_{mat_id}"
            beskz = mat_beskz.get(mat_id, "")
            prod_type = "FERT" if beskz == "E" else ("ROH" if beskz == "F" else "HAWA")

            unit_cost = safe_float(mara_row.get("STPRS", "0"))
            if unit_cost == 0:
                unit_cost = safe_float(mara_row.get("VERPR", "0"))
            base_uom = mara_row.get("MEINS", "EA")

            session.execute(
                text("""
                    INSERT INTO product (id, config_id, description, product_type, item_type, base_uom, unit_cost, is_active, source)
                    VALUES (:pid, :cid, :desc, :ptype, :itype, :uom, :cost, 'Y', 'SAP_IDES')
                """),
                {
                    "pid": prod_id,
                    "cid": config_id,
                    "desc": desc[:500],
                    "ptype": prod_type,
                    "itype": "material",
                    "uom": base_uom[:20] if base_uom else "EA",
                    "cost": unit_cost if unit_cost > 0 else 10.0,
                },
            )
            product_count += 1

        session.flush()
        print(f"    Created {product_count} products")

        # ---------------------------------------------------------------
        # 4f. Create transportation lanes
        # ---------------------------------------------------------------
        print("  Creating transportation lanes...")

        lane_count = 0

        # Vendor → Plant lanes (procurement)
        for v_id in vendor_po_counts:
            site_key = f"VEND-{v_id}"
            from_id = site_ids.get(site_key)
            to_id = site_ids.get(PRIMARY)
            if from_id and to_id:
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id, supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id, '{"mean": 7, "std": 2, "distribution": "lognormal"}', 10000)
                    """),
                    {"cid": config_id, "from_id": from_id, "to_id": to_id},
                )
                lane_count += 1

        # Plant → Plant lanes (if secondary plants exist)
        for sp in secondary_plants:
            from_id = site_ids.get(PRIMARY)
            to_id = site_ids.get(sp)
            if from_id and to_id:
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id, supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id, '{"mean": 2, "std": 0.5, "distribution": "normal"}', 10000)
                    """),
                    {"cid": config_id, "from_id": from_id, "to_id": to_id},
                )
                lane_count += 1

        # Plant → Customer lanes (distribution)
        for cust_id in customer_order_counts:
            site_key = f"CUST-{cust_id}"
            from_id = site_ids.get(PRIMARY)
            to_id = site_ids.get(site_key)
            if from_id and to_id:
                session.execute(
                    text("""
                        INSERT INTO transportation_lane (config_id, from_site_id, to_site_id, supply_lead_time, capacity)
                        VALUES (:cid, :from_id, :to_id, '{"mean": 3, "std": 1, "distribution": "lognormal"}', 10000)
                    """),
                    {"cid": config_id, "from_id": from_id, "to_id": to_id},
                )
                lane_count += 1

        session.flush()
        print(f"    Created {lane_count} transportation lanes")

        # ---------------------------------------------------------------
        # 4g. Create inventory policies for ALL products at plant
        # ---------------------------------------------------------------
        print(f"  Creating inventory policies for ALL {len(materials)} products at plant {PRIMARY}...")

        plant_site_id = site_ids[PRIMARY]
        policy_count = 0

        for mat_id in sorted(materials):
            prod_id = f"CFG{config_id}_{mat_id}"
            eisbe = mat_eisbe.get(mat_id, 0)
            minbe = mat_minbe.get(mat_id, 0)

            # Use SAP safety stock if available, otherwise set a reasonable default
            if eisbe > 0:
                ss_qty = eisbe
                rop = minbe if minbe > 0 else eisbe * 1.5
                policy_source = "SAP_EISBE"
            elif minbe > 0:
                ss_qty = minbe * 0.5  # Reorder point as basis, safety stock = 50% of ROP
                rop = minbe
                policy_source = "SAP_MINBE"
            else:
                # Default: set safety stock based on product type
                beskz = mat_beskz.get(mat_id, "")
                if beskz == "E":  # Manufactured — higher buffer
                    ss_qty = 50.0
                    rop = 100.0
                else:  # Procured or other
                    ss_qty = 25.0
                    rop = 50.0
                policy_source = "DEFAULT"

            # Get MARC planning params for erp_planning_params JSONB
            marc_p = mat_marc_params.get(mat_id, {})
            erp_params_json = {k: v for k, v in marc_p.items() if v} if marc_p else None

            session.execute(
                text("""
                    INSERT INTO inv_policy (config_id, site_id, product_id, ss_policy, ss_quantity,
                                           reorder_point, order_up_to_level, min_order_quantity,
                                           max_order_quantity, fixed_order_quantity,
                                           service_level, review_period, is_active, source,
                                           erp_planning_params)
                    VALUES (:cid, :sid, :pid, 'abs_level', :ss, :rop, :oul, :moq, :maxq, :foq,
                            0.95, 7, 'Y', :src, CAST(:erp_params AS jsonb))
                """),
                {
                    "cid": config_id,
                    "sid": plant_site_id,
                    "pid": prod_id,
                    "ss": ss_qty,
                    "rop": rop,
                    "oul": marc_p.get("MABST", 0) if marc_p.get("MABST", 0) > 0 else rop * 2,
                    "moq": marc_p.get("BSTMI", 0) or None,
                    "maxq": marc_p.get("BSTMA", 0) or None,
                    "foq": marc_p.get("LOSGR", 0) or marc_p.get("BSTRF", 0) or None,
                    "src": policy_source,
                    "erp_params": json.dumps(erp_params_json) if erp_params_json else None,
                },
            )
            policy_count += 1

        session.flush()
        print(f"    Created {policy_count} inventory policies (with erp_planning_params)")

        # ---------------------------------------------------------------
        # 4g-ext. Create site_planning_config rows (ERP heuristic dispatch)
        # ---------------------------------------------------------------
        print(f"  Creating site_planning_config rows...")

        # DISMM → PlanningMethod mapping
        DISMM_MAP = {
            "VB": "REORDER_POINT", "VM": "REORDER_POINT",
            "V1": "MRP_AUTO", "V2": "MRP_AUTO",
            "VV": "FORECAST_BASED",
            "PD": "MRP_DETERMINISTIC",
            "ND": "NO_PLANNING",
        }
        # DISLS → LotSizingRule mapping
        DISLS_MAP = {
            "EX": "LOT_FOR_LOT", "FX": "FIXED", "HB": "REPLENISH_TO_MAX",
            "WB": "WEEKLY_BATCH", "MB": "MONTHLY_BATCH", "TB": "DAILY_BATCH",
        }

        spc_count = 0
        for mat_id in sorted(materials):
            prod_id = f"CFG{config_id}_{mat_id}"
            marc_p = mat_marc_params.get(mat_id, {})
            dismm = marc_p.get("DISMM", "")
            disls = marc_p.get("DISLS", "")

            erp_params_json = {k: v for k, v in marc_p.items() if v} if marc_p else None

            session.execute(
                text("""
                    INSERT INTO site_planning_config
                        (config_id, tenant_id, site_id, product_id,
                         planning_method, lot_sizing_rule,
                         fixed_lot_size, min_order_quantity, max_order_quantity, order_multiple,
                         frozen_horizon_days, planning_time_fence_days,
                         forecast_consumption_mode, forecast_consumption_fwd_days, forecast_consumption_bwd_days,
                         procurement_type, strategy_group, mrp_controller,
                         erp_source, erp_params)
                    VALUES (:cid, :tid, :sid, :pid,
                            :pm, :ls,
                            :fls, :moq, :maxq, :mult,
                            :fhz, :ptf,
                            :fcm, :fcf, :fcb,
                            :pt, :sg, :mc,
                            'SAP', CAST(:erp_params AS jsonb))
                    ON CONFLICT (config_id, site_id, product_id) DO UPDATE SET
                        planning_method = EXCLUDED.planning_method,
                        lot_sizing_rule = EXCLUDED.lot_sizing_rule,
                        erp_params = EXCLUDED.erp_params,
                        updated_at = NOW()
                """),
                {
                    "cid": config_id,
                    "tid": tenant_id,
                    "sid": plant_site_id,
                    "pid": prod_id,
                    "pm": DISMM_MAP.get(dismm, "REORDER_POINT"),
                    "ls": DISLS_MAP.get(disls, "LOT_FOR_LOT"),
                    "fls": marc_p.get("LOSGR") or None,
                    "moq": marc_p.get("BSTMI") or None,
                    "maxq": marc_p.get("BSTMA") or None,
                    "mult": marc_p.get("BSTRF") or None,
                    "fhz": marc_p.get("FXHOR") or None,
                    "ptf": marc_p.get("PLIFZ") or None,
                    "fcm": marc_p.get("VRMOD") or None,
                    "fcf": marc_p.get("VINT2") or None,
                    "fcb": marc_p.get("VINT1") or None,
                    "pt": marc_p.get("BESKZ") or None,
                    "sg": marc_p.get("STRGR") or None,
                    "mc": marc_p.get("DISPO") or None,
                    "erp_params": json.dumps(erp_params_json) if erp_params_json else None,
                },
            )
            spc_count += 1

        session.flush()
        print(f"    Created {spc_count} site_planning_config rows")

        # ---------------------------------------------------------------
        # 4h. Create inventory levels (from MARD stock)
        # ---------------------------------------------------------------
        print(f"  Creating inventory levels...")

        inv_count = 0
        today = date.today()
        for mat_id in sorted(materials):
            prod_id = f"CFG{config_id}_{mat_id}"
            stock = mat_stock.get(mat_id, 0.0)
            # Even if stock is 0, create the record so the system knows about it
            session.execute(
                text("""
                    INSERT INTO inv_level (config_id, site_id, product_id, on_hand_qty, in_transit_qty,
                                          allocated_qty, inventory_date, source)
                    VALUES (:cid, :sid, :pid, :qty, 0, 0, :dt, 'SAP_MARD')
                """),
                {
                    "cid": config_id,
                    "sid": plant_site_id,
                    "pid": prod_id,
                    "qty": stock,
                    "dt": today,
                },
            )
            inv_count += 1

        session.flush()
        print(f"    Created {inv_count} inventory level records")

        # ---------------------------------------------------------------
        # 4i. Load SAP forecasts (PBIM/PBED → forecast table)
        # ---------------------------------------------------------------
        print(f"\n  Loading SAP forecasts (PBIM/PBED)...")
        pbim = read_csv(csv_dir, "PBIM.csv")
        pbed = read_csv(csv_dir, "PBED.csv")

        # Build BDZEI → (material, plant) lookup from PBIM
        bdzei_to_mat = {}
        for r in pbim:
            bdzei = (r.get("BDZEI") or "").strip()
            mat = (r.get("MATNR") or "").strip()
            werks = (r.get("WERKS") or "").strip()
            if bdzei and mat and (werks == PRIMARY or not werks):
                bdzei_to_mat[bdzei] = mat

        fcst_count = 0
        today = date.today()
        for r in pbed:
            bdzei = (r.get("BDZEI") or "").strip()
            mat = bdzei_to_mat.get(bdzei)
            if not mat or mat not in materials:
                continue
            qty = float(r.get("PLNMG") or 0)
            if qty <= 0:
                continue
            raw_date = (r.get("PDATU") or "").strip()
            if not raw_date or len(raw_date) < 8:
                continue
            try:
                fcst_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            except (ValueError, IndexError):
                continue
            # Date-shift: move historical dates to current year range
            year_offset = today.year - fcst_date.year
            try:
                fcst_date = fcst_date.replace(year=fcst_date.year + year_offset)
            except ValueError:
                fcst_date = fcst_date.replace(year=fcst_date.year + year_offset, day=28)

            prod_id = f"CFG{config_id}_{mat}"
            session.execute(
                text("""
                    INSERT INTO forecast (config_id, customer_id, product_id, site_id,
                                          forecast_date, forecast_quantity, forecast_p50,
                                          forecast_type, source, is_active)
                    VALUES (:cid, :tid, :pid, :sid, :dt, :qty, :qty, 'statistical', 'SAP_PBED', 'Y')
                    ON CONFLICT DO NOTHING
                """),
                {
                    "cid": config_id,
                    "tid": str(tenant_id),
                    "pid": prod_id,
                    "sid": plant_site_id,
                    "dt": fcst_date,
                    "qty": qty,
                },
            )
            fcst_count += 1

        session.flush()
        print(f"    Created {fcst_count} forecast records from SAP PBED")

        # ---------------------------------------------------------------
        # 4j. Load SAP sales orders (VBAK/VBAP → outbound_order/line)
        # ---------------------------------------------------------------
        print(f"  Loading SAP sales orders (VBAK/VBAP)...")
        vbak = read_csv(csv_dir, "VBAK.csv")
        vbap = read_csv(csv_dir, "VBAP.csv")

        # Build order header lookup
        vbak_map = {}
        for r in vbak:
            vbeln = (r.get("VBELN") or "").strip()
            if vbeln:
                vbak_map[vbeln] = r

        so_count = 0
        sol_count = 0
        for r in vbap:
            vbeln = (r.get("VBELN") or "").strip()
            mat = (r.get("MATNR") or "").strip()
            werks = (r.get("WERKS") or "").strip()
            if werks != PRIMARY or mat not in materials:
                continue
            qty = float(r.get("KWMENG") or r.get("ZMENG") or 0)
            if qty <= 0:
                continue

            header = vbak_map.get(vbeln, {})
            raw_date = (r.get("EDATU") or header.get("ERDAT") or "").strip()
            if not raw_date or len(raw_date) < 8:
                continue
            try:
                order_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            except (ValueError, IndexError):
                continue
            # Date-shift
            year_offset = today.year - order_date.year
            try:
                order_date = order_date.replace(year=order_date.year + year_offset)
            except ValueError:
                order_date = order_date.replace(year=order_date.year + year_offset, day=28)

            prod_id = f"CFG{config_id}_{mat}"
            customer_id = (r.get("KUNNR") or header.get("KUNNR") or "").strip()

            posnr = (r.get("POSNR") or str(sol_count + 1)).strip()
            session.execute(
                text("""
                    INSERT INTO outbound_order_line (config_id, product_id, site_id,
                                                     ordered_quantity, requested_delivery_date,
                                                     order_id, order_date, line_number)
                    VALUES (:cid, :pid, :sid, :qty, :dt, :oid, :dt, :ln)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "cid": config_id,
                    "pid": prod_id,
                    "sid": plant_site_id,
                    "qty": qty,
                    "dt": order_date,
                    "oid": vbeln,
                    "ln": posnr,
                },
            )
            sol_count += 1

        session.flush()
        print(f"    Created {sol_count} sales order lines from SAP VBAP")

        # ---------------------------------------------------------------
        # 4k. Commit
        # ---------------------------------------------------------------
        session.commit()
        print(f"\n{'='*70}")
        print(f"REBUILD COMPLETE")
        print(f"  Config: {new_name} (id={config_id})")
        print(f"  Internal sites: {1 + len(secondary_plants)}")
        print(f"  Customer sites: {len(customer_order_counts)}")
        print(f"  Vendor sites: {len(vendor_po_counts)}")
        print(f"  Products: {product_count}")
        print(f"  Transportation lanes: {lane_count}")
        print(f"  Inventory policies: {policy_count}")
        print(f"  Inventory levels: {inv_count}")
        print(f"  Total sites: {len(site_ids)}")
        print(f"{'='*70}")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()

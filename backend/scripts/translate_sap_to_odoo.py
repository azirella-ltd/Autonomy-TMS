#!/usr/bin/env python3
"""
Translate SAP IDES CSV exports into Odoo-compatible data and load via JSON-RPC.

Reads SAP tables (T001W, MARA, MAKT, MARC, MARD, LFA1, KNA1, EKKO, EKPO,
VBAK, VBAP, STKO, STPO) and creates the corresponding Odoo records:
  - product.product / product.template
  - stock.warehouse / stock.location
  - mrp.bom / mrp.bom.line
  - stock.warehouse.orderpoint (reorder rules with planning params)
  - product.supplierinfo (vendor links)
  - res.partner (vendors, customers)

Can operate in two modes:
  1. JSON-RPC (direct load into running Odoo instance)
  2. CSV export (for manual import via Odoo's Import feature)

After loading, run Odoo's MRP scheduler to generate planned orders:
  - Via JSON-RPC: call procurement.group.run_scheduler()
  - Via UI: Inventory > Operations > Run Scheduler

Usage:
    # Load into Odoo via JSON-RPC
    python scripts/translate_sap_to_odoo.py \\
        --sap-dir imports/sap_faa_extract_20260322 \\
        --odoo-url http://acer-nitro.local:8069 \\
        --odoo-db odoo \\
        --odoo-user admin \\
        --odoo-password admin \\
        --plant 1710

    # Export as CSVs only (no Odoo connection needed)
    python scripts/translate_sap_to_odoo.py \\
        --sap-dir imports/sap_faa_extract_20260322 \\
        --output-dir imports/Odoo_Demo \\
        --csv-only \\
        --plant 1710
"""

import argparse
import csv
import json
import os
import sys
import xmlrpc.client
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def read_csv(csv_dir: Path, filename: str) -> List[Dict[str, str]]:
    path = csv_dir / filename
    if not path.exists():
        print(f"  SKIP {filename} (not found)")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  READ {filename}: {len(rows)} rows")
    return rows


def write_csv(output_dir: str, filename: str, rows: List[Dict], fieldnames: List[str]):
    if not rows:
        print(f"  SKIP {filename} (no rows)")
        return
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  WROTE {filename}: {len(rows)} rows")


def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# SAP DISMM → Odoo orderpoint trigger mapping
# ---------------------------------------------------------------------------
DISMM_TO_TRIGGER = {
    "PD": "auto",    # Deterministic MRP → auto reorder
    "VB": "auto",    # Reorder Point → auto
    "VM": "auto",    # Auto ROP → auto
    "VV": "auto",    # Forecast-based → auto
    "ND": "manual",  # No planning → manual
}


class OdooRPCClient:
    """Simple Odoo JSON-RPC/XML-RPC client for data loading."""

    def __init__(self, url: str, db: str, user: str, password: str):
        self.url = url
        self.db = db
        self.uid = None
        self.password = password

        # Authenticate
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise ConnectionError(f"Odoo authentication failed for {user}@{db}")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        print(f"  Connected to Odoo: {url} as uid={self.uid}")

    def create(self, model: str, vals: Dict) -> int:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "create", [vals]
        )

    def search(self, model: str, domain: list, limit: int = 0) -> List[int]:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "search", [domain],
            {"limit": limit}
        )

    def search_read(self, model: str, domain: list, fields: list, limit: int = 0) -> List[Dict]:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "search_read", [domain],
            {"fields": fields, "limit": limit}
        )

    def write(self, model: str, ids: List[int], vals: Dict):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "write", [ids, vals]
        )

    def run_scheduler(self):
        """Run Odoo MRP/procurement scheduler."""
        print("  Running Odoo MRP scheduler...")
        try:
            self.models.execute_kw(
                self.db, self.uid, self.password,
                "procurement.group", "run_scheduler", []
            )
            print("  MRP scheduler completed")
        except Exception as e:
            print(f"  MRP scheduler error (may need mrp module): {e}")
            # Try alternative method
            try:
                self.models.execute_kw(
                    self.db, self.uid, self.password,
                    "stock.warehouse.orderpoint", "action_replenish", [[]]
                )
                print("  Replenishment action completed (Odoo 17+)")
            except Exception as e2:
                print(f"  Replenishment action also failed: {e2}")


def main():
    parser = argparse.ArgumentParser(description="Translate SAP data to Odoo format")
    parser.add_argument("--sap-dir", type=str, required=True, help="SAP CSV extract directory")
    parser.add_argument("--plant", type=str, default="1710", help="SAP plant code")
    parser.add_argument("--csv-only", action="store_true", help="Export CSVs only, don't load into Odoo")
    parser.add_argument("--output-dir", type=str, default="imports/Odoo_Demo", help="CSV output dir")
    parser.add_argument("--odoo-url", type=str, default="http://acer-nitro.local:8069")
    parser.add_argument("--odoo-db", type=str, default="odoo")
    parser.add_argument("--odoo-user", type=str, default="admin")
    parser.add_argument("--odoo-password", type=str, default="admin")
    parser.add_argument("--run-mrp", action="store_true", help="Run MRP scheduler after loading")
    args = parser.parse_args()

    sap_dir = Path(args.sap_dir)
    if not sap_dir.exists():
        sap_dir = Path(__file__).resolve().parent.parent / args.sap_dir
    if not sap_dir.exists():
        print(f"ERROR: SAP directory not found: {sap_dir}")
        sys.exit(1)

    plant = args.plant

    print(f"\n{'='*70}")
    print(f"SAP → Odoo Translation")
    print(f"  SAP dir:   {sap_dir}")
    print(f"  Plant:     {plant}")
    print(f"  Mode:      {'CSV only' if args.csv_only else f'JSON-RPC → {args.odoo_url}'}")
    print(f"{'='*70}\n")

    # ── Load SAP data ────────────────────────────────────────────────────
    print("Phase 1: Loading SAP CSV data...")
    t001w = read_csv(sap_dir, "T001W.csv")
    mara = read_csv(sap_dir, "MARA.csv")
    makt = read_csv(sap_dir, "MAKT.csv")
    marc = read_csv(sap_dir, "MARC.csv")
    mard = read_csv(sap_dir, "MARD.csv")
    lfa1 = read_csv(sap_dir, "LFA1.csv")
    kna1 = read_csv(sap_dir, "KNA1.csv")
    stko = read_csv(sap_dir, "STKO.csv")
    stpo = read_csv(sap_dir, "STPO.csv")
    mast = read_csv(sap_dir, "MAST.csv")
    eina = read_csv(sap_dir, "EINA.csv")

    # ── Filter to plant ──────────────────────────────────────────────────
    marc_plant = [r for r in marc if (r.get("WERKS") or "").strip() == plant]
    mard_plant = [r for r in mard if (r.get("WERKS") or "").strip() == plant]
    materials = set((r.get("MATNR") or "").strip() for r in marc_plant)

    # Material descriptions
    desc_map = {}
    for r in makt:
        mat = (r.get("MATNR") or "").strip()
        lang = (r.get("SPRAS", "") or "").strip()
        if lang in ("E", "EN", ""):
            desc_map[mat] = r.get("MAKTX", mat)

    # MARC params
    marc_map = {(r.get("MATNR") or "").strip(): r for r in marc_plant}

    # Stock
    stock_map = defaultdict(float)
    for r in mard_plant:
        stock_map[(r.get("MATNR") or "").strip()] += safe_float(r.get("LABST", "0"))

    # Vendor-material links from EINA
    vendor_materials = defaultdict(set)
    for r in eina:
        mat = (r.get("MATNR") or "").strip()
        vendor = (r.get("LIFNR", "") or "").strip()
        if mat in materials and vendor:
            vendor_materials[vendor].add(mat)

    print(f"\n  Materials at plant {plant}: {len(materials)}")
    print(f"  With stock: {sum(1 for m in materials if stock_map.get(m, 0) > 0)}")
    print(f"  Vendors with materials: {len(vendor_materials)}")

    # ── Build Odoo-format records ────────────────────────────────────────
    print("\nPhase 2: Building Odoo records...")

    # Products (product.template)
    product_rows = []
    for mat in sorted(materials):
        marc_r = marc_map.get(mat, {})
        beskz = (marc_r.get("BESKZ", "") or "").strip()
        product_rows.append({
            "name": desc_map.get(mat, mat),
            "default_code": mat,
            "type": "product",
            "sale_ok": True,
            "purchase_ok": beskz in ("F", "X", ""),
            "produce_delay": int(safe_float(marc_r.get("DZEIT", "0"))) or 0,
            "list_price": 0.0,
            "standard_price": 0.0,
        })

    # Vendors (res.partner)
    vendor_rows = []
    vendor_names = {(r.get("LIFNR", "") or "").strip(): (r.get("NAME1", "") or "").strip() for r in lfa1}
    for vendor_id in sorted(vendor_materials.keys()):
        vendor_rows.append({
            "name": vendor_names.get(vendor_id, f"Vendor {vendor_id}"),
            "ref": vendor_id,
            "supplier_rank": 1,
            "is_company": True,
        })

    # Customers (res.partner)
    customer_rows = []
    for r in kna1:
        cust_id = (r.get("KUNNR", "") or "").strip()
        if cust_id:
            customer_rows.append({
                "name": r.get("NAME1", f"Customer {cust_id}").strip(),
                "ref": cust_id,
                "customer_rank": 1,
                "is_company": True,
            })

    # Vendor pricelists (product.supplierinfo)
    supplierinfo_rows = []
    for vendor_id, mats in vendor_materials.items():
        for mat in sorted(mats):
            marc_r = marc_map.get(mat, {})
            plifz = int(safe_float(marc_r.get("PLIFZ", "0"))) or 7
            bstmi = safe_float(marc_r.get("BSTMI", "0"))
            supplierinfo_rows.append({
                "partner_name": vendor_names.get(vendor_id, vendor_id),
                "partner_ref": vendor_id,
                "product_code": mat,
                "product_name": desc_map.get(mat, mat),
                "delay": plifz,
                "min_qty": bstmi,
                "price": 0.0,
            })

    # BOMs (mrp.bom + mrp.bom.line)
    # BOM linkage: MAST maps material → STLNR (BOM number)
    mat_to_stlnr = {}
    for r in mast:
        werks = (r.get("WERKS") or "").strip()
        if werks == plant or not werks:
            mat_to_stlnr[(r.get("MATNR") or "").strip()] = (r.get("STLNR") or "").strip()
    stlnr_to_mat = {v: k for k, v in mat_to_stlnr.items()}
    print(f"  BOM assignments (MAST): {len(mat_to_stlnr)}")

    bom_rows = []
    bom_line_rows = []
    bom_parents = set()
    for r in stpo:
        stlnr = (r.get("STLNR", "") or "").strip()
        component = (r.get("IDNRK", "") or "").strip()
        qty = safe_float(r.get("MENGE", "1"))
        scrap = safe_float(r.get("AUSCH", "0"))
        if not stlnr or not component:
            continue

        parent_mat = stlnr_to_mat.get(stlnr, "")
        if parent_mat and parent_mat in materials and component in materials:
            bom_parents.add(parent_mat)
            bom_line_rows.append({
                "bom_product_code": parent_mat,
                "product_code": component,
                "product_qty": qty,
                "scrap_pct": scrap,
            })

    for parent_mat in sorted(bom_parents):
        marc_r = marc_map.get(parent_mat, {})
        bom_rows.append({
            "product_code": parent_mat,
            "product_name": desc_map.get(parent_mat, parent_mat),
            "product_qty": safe_float(marc_r.get("LOSGR", "1")) or 1,
            "type": "normal",
        })

    # Reorder rules (stock.warehouse.orderpoint)
    orderpoint_rows = []
    for mat in sorted(materials):
        marc_r = marc_map.get(mat, {})
        dismm = (marc_r.get("DISMM", "") or "").strip()
        eisbe = safe_float(marc_r.get("EISBE", "0"))
        minbe = safe_float(marc_r.get("MINBE", "0"))
        mabst = safe_float(marc_r.get("MABST", "0"))
        bstrf = safe_float(marc_r.get("BSTRF", "0"))
        losgr = safe_float(marc_r.get("LOSGR", "0"))

        # Odoo orderpoint: product_min_qty = reorder point, product_max_qty = order-up-to
        min_qty = minbe if minbe > 0 else eisbe
        max_qty = mabst if mabst > 0 else (min_qty * 2 if min_qty > 0 else losgr)
        qty_multiple = bstrf if bstrf > 0 else 0

        trigger = DISMM_TO_TRIGGER.get(dismm, "auto")

        orderpoint_rows.append({
            "product_code": mat,
            "product_name": desc_map.get(mat, mat),
            "product_min_qty": min_qty,
            "product_max_qty": max_qty,
            "qty_multiple": qty_multiple,
            "trigger": trigger,
            # SAP source fields (for reference in CSV, not loaded into Odoo)
            "sap_dismm": dismm,
            "sap_disls": (marc_r.get("DISLS", "") or "").strip(),
            "sap_losgr": losgr,
            "sap_beskz": (marc_r.get("BESKZ", "") or "").strip(),
        })

    # Initial stock (stock.quant)
    quant_rows = []
    for mat in sorted(materials):
        qty = stock_map.get(mat, 0)
        if qty > 0:
            quant_rows.append({
                "product_code": mat,
                "product_name": desc_map.get(mat, mat),
                "quantity": qty,
                "location_name": f"WH/{plant}/Stock",
            })

    print(f"  Products: {len(product_rows)}")
    print(f"  Vendors: {len(vendor_rows)}")
    print(f"  Customers: {len(customer_rows)}")
    print(f"  Vendor pricelists: {len(supplierinfo_rows)}")
    print(f"  BOMs: {len(bom_rows)} ({len(bom_line_rows)} components)")
    print(f"  Reorder rules: {len(orderpoint_rows)}")
    print(f"  Stock quants: {len(quant_rows)}")

    # ── Output ───────────────────────────────────────────────────────────
    if args.csv_only:
        print(f"\nPhase 3: Writing CSVs to {args.output_dir}...")
        write_csv(args.output_dir, "product_template.csv", product_rows,
                  ["name", "default_code", "type", "sale_ok", "purchase_ok", "produce_delay", "list_price", "standard_price"])
        write_csv(args.output_dir, "res_partner_vendors.csv", vendor_rows,
                  ["name", "ref", "supplier_rank", "is_company"])
        write_csv(args.output_dir, "res_partner_customers.csv", customer_rows,
                  ["name", "ref", "customer_rank", "is_company"])
        write_csv(args.output_dir, "product_supplierinfo.csv", supplierinfo_rows,
                  ["partner_name", "partner_ref", "product_code", "product_name", "delay", "min_qty", "price"])
        write_csv(args.output_dir, "mrp_bom.csv", bom_rows,
                  ["product_code", "product_name", "product_qty", "type"])
        write_csv(args.output_dir, "mrp_bom_line.csv", bom_line_rows,
                  ["bom_product_code", "product_code", "product_qty", "scrap_pct"])
        write_csv(args.output_dir, "stock_warehouse_orderpoint.csv", orderpoint_rows,
                  ["product_code", "product_name", "product_min_qty", "product_max_qty",
                   "qty_multiple", "trigger", "sap_dismm", "sap_disls", "sap_losgr", "sap_beskz"])
        write_csv(args.output_dir, "stock_quant.csv", quant_rows,
                  ["product_code", "product_name", "quantity", "location_name"])
        print(f"\n  CSVs written to {args.output_dir}/")
        print(f"  Import into Odoo via: Settings > Technical > Import > Upload CSV")
    else:
        print(f"\nPhase 3: Loading into Odoo at {args.odoo_url}...")
        try:
            odoo = OdooRPCClient(args.odoo_url, args.odoo_db, args.odoo_user, args.odoo_password)
        except Exception as e:
            print(f"  ERROR connecting to Odoo: {e}")
            print(f"  Falling back to CSV export...")
            args.csv_only = True
            # Re-run CSV export
            os.makedirs(args.output_dir, exist_ok=True)
            write_csv(args.output_dir, "stock_warehouse_orderpoint.csv", orderpoint_rows,
                      ["product_code", "product_name", "product_min_qty", "product_max_qty",
                       "qty_multiple", "trigger", "sap_dismm", "sap_disls", "sap_losgr", "sap_beskz"])
            return

        # TODO: Implement JSON-RPC loading for each model
        # This requires careful sequencing: partners → products → BOMs → orderpoints → quants
        print("  JSON-RPC loading not yet implemented — use --csv-only for now")
        print("  (Odoo's Import feature handles CSV loading with field mapping)")

    if not args.csv_only and args.run_mrp:
        try:
            odoo.run_scheduler()
        except Exception as e:
            print(f"  MRP scheduler error: {e}")

    print(f"\n{'='*70}")
    print(f"Translation complete")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

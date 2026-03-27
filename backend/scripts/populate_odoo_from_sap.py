#!/usr/bin/env python3
"""
Translate SAP IDES data and populate a live Odoo instance via JSON-RPC.

Creates a new company in Odoo ("SAP IDES 1710") and populates it with:
- Product categories (from SAP MATKL groups)
- Products with costs/prices (from MARA+MAKT+MBEW)
- Vendors and customers (from LFA1+KNA1, as res.partner)
- Vendor pricelists with lead times (from EINA+EINE)
- Warehouses (from T001W plants)
- Bills of Materials with components (from STKO+STPO+MAST)
- Inventory on-hand (from MARD as stock.quant adjustments)
- Reordering rules / safety stock (from MARC EISBE/MINBE)
- Purchase orders with lines (from EKKO+EKPO)
- Sale orders with lines (from VBAK+VBAP)
- Manufacturing orders (from AFKO)

Usage:
    python scripts/populate_odoo_from_sap.py \
        --sap-dir imports/SAP_Demo/S4HANA/2026-03-18 \
        --odoo-url http://acer-nitro.local:8069 \
        --odoo-db odoo_demo \
        --odoo-user admin \
        --odoo-password admin \
        --plant 1710 \
        --company-name "SAP IDES 1710"

    # Dry run (translate only, no Odoo writes)
    python scripts/populate_odoo_from_sap.py \
        --sap-dir imports/SAP_Demo/S4HANA/2026-03-18 --dry-run
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests


# ── Utilities ────────────────────────────────────────────────────────────────

def read_csv(csv_dir: Path, filename: str) -> List[Dict[str, str]]:
    path = csv_dir / filename
    if not path.exists():
        print(f"  SKIP {filename}")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  READ {filename}: {len(rows)} rows")
    return rows


def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


# ── Odoo JSON-RPC Client ────────────────────────────────────────────────────

class OdooClient:
    def __init__(self, url: str, db: str, user: str, password: str):
        self.url = f"{url}/jsonrpc"
        self.db = db
        self.user = user
        self.password = password
        self.uid = None
        self._id = 0

    def authenticate(self):
        self.uid = self._call("common", "authenticate",
                              self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError(f"Odoo auth failed for {self.user}@{self.db}")
        print(f"  Authenticated as uid={self.uid}")
        return self.uid

    def create(self, model: str, vals: dict) -> int:
        return self._call("object", "execute_kw",
                          self.db, self.uid, self.password,
                          model, "create", [vals])

    def create_batch(self, model: str, vals_list: List[dict]) -> List[int]:
        """Create multiple records at once."""
        return self._call("object", "execute_kw",
                          self.db, self.uid, self.password,
                          model, "create", [vals_list])

    def search(self, model: str, domain: list, limit: int = 0) -> List[int]:
        kwargs = {"limit": limit} if limit else {}
        return self._call("object", "execute_kw",
                          self.db, self.uid, self.password,
                          model, "search", [domain], kwargs)

    def search_read(self, model: str, domain: list, fields: list, limit: int = 0) -> list:
        kwargs = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        return self._call("object", "execute_kw",
                          self.db, self.uid, self.password,
                          model, "search_read", [domain], kwargs)

    def write(self, model: str, ids: List[int], vals: dict):
        return self._call("object", "execute_kw",
                          self.db, self.uid, self.password,
                          model, "write", [ids, vals])

    def _call(self, service, method, *args):
        self._id += 1
        r = requests.post(self.url, json={
            "jsonrpc": "2.0", "method": "call", "id": self._id,
            "params": {"service": service, "method": method, "args": list(args)}
        }, timeout=300)
        result = r.json()
        if "error" in result:
            err = result["error"]
            msg = err.get("data", {}).get("message", str(err))
            raise RuntimeError(f"Odoo error: {msg}")
        return result.get("result")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Populate Odoo from SAP IDES data")
    parser.add_argument("--sap-dir", required=True)
    parser.add_argument("--odoo-url", default="http://acer-nitro.local:8069")
    parser.add_argument("--odoo-db", default="odoo_demo")
    parser.add_argument("--odoo-user", default="admin")
    parser.add_argument("--odoo-password", default="admin")
    parser.add_argument("--plant", default="1710")
    parser.add_argument("--company-name", default="SAP Bike Demo")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-products", type=int, default=0,
                        help="Max products (0=all, default: all)")
    parser.add_argument("--max-vendors", type=int, default=0)
    parser.add_argument("--max-customers", type=int, default=0)
    args = parser.parse_args()

    sap_dir = Path(args.sap_dir)
    plant = args.plant

    print(f"\n{'='*70}")
    print(f"  SAP IDES → Odoo Population")
    print(f"  SAP dir:      {sap_dir}")
    print(f"  Odoo:         {args.odoo_url} / {args.odoo_db}")
    print(f"  Company:      {args.company_name}")
    print(f"  Plant:        {plant}")
    print(f"  Max products: {args.max_products}")
    print(f"  Dry run:      {args.dry_run}")
    print(f"{'='*70}")

    # ── Phase 1: Load SAP data ───────────────────────────────────────────
    print("\nPhase 1: Loading SAP CSVs...")
    t001w = read_csv(sap_dir, "T001W.csv")
    mara = read_csv(sap_dir, "MARA.csv")
    makt = read_csv(sap_dir, "MAKT.csv")
    marc = read_csv(sap_dir, "MARC.csv")
    mard = read_csv(sap_dir, "MARD.csv")
    mbew = read_csv(sap_dir, "MBEW.csv")
    lfa1 = read_csv(sap_dir, "LFA1.csv")
    kna1 = read_csv(sap_dir, "KNA1.csv")
    eina = read_csv(sap_dir, "EINA.csv")
    eine = read_csv(sap_dir, "EINE.csv")
    ekko = read_csv(sap_dir, "EKKO.csv")
    ekpo = read_csv(sap_dir, "EKPO.csv")
    vbak = read_csv(sap_dir, "VBAK.csv")
    vbap = read_csv(sap_dir, "VBAP.csv")
    stko = read_csv(sap_dir, "STKO.csv")
    stpo = read_csv(sap_dir, "STPO.csv")
    mast = read_csv(sap_dir, "MAST.csv")
    afko = read_csv(sap_dir, "AFKO.csv")
    # Transaction history
    likp = read_csv(sap_dir, "LIKP.csv")
    lips = read_csv(sap_dir, "LIPS.csv")
    afvc = read_csv(sap_dir, "AFVC.csv")
    resb = read_csv(sap_dir, "RESB.csv")
    crhd = read_csv(sap_dir, "CRHD.csv")
    plko = read_csv(sap_dir, "PLKO.csv")
    plpo = read_csv(sap_dir, "PLPO.csv")
    mch1 = read_csv(sap_dir, "MCH1.csv")
    mcha = read_csv(sap_dir, "MCHA.csv")
    equi = read_csv(sap_dir, "EQUI.csv")

    # ── Phase 2: Build lookup maps ───────────────────────────────────────
    print("\nPhase 2: Building maps...")

    makt_map = {}
    for r in makt:
        mat = r.get("MATNR", "")
        if mat and (r.get("SPRAS", "E") == "E" or mat not in makt_map):
            makt_map[mat] = r.get("MAKTX", mat)

    mara_map = {r["MATNR"]: r for r in mara if r.get("MATNR")}
    mbew_map = {}
    for r in mbew:
        if r.get("BWKEY") == plant:
            mbew_map[r["MATNR"]] = r

    marc_plant = [r for r in marc if r.get("WERKS") == plant]
    marc_map = {r["MATNR"]: r for r in marc_plant}
    materials_at_plant = {r["MATNR"] for r in marc_plant}

    EXCLUDE_MTART = {"SERV", "DIEN", "NLAG", "VERP", "LEIH", "PIPE", "VEHI"}
    materials = set()
    for mat in materials_at_plant:
        mtart = mara_map.get(mat, {}).get("MTART", "")
        if mtart not in EXCLUDE_MTART:
            materials.add(mat)

    # Stock by material
    stock_map = defaultdict(float)
    for r in mard:
        if r.get("WERKS") == plant:
            stock_map[r["MATNR"]] += safe_float(r.get("LABST", "0"))

    # BOM linkage
    mat_to_stlnr = {}
    for r in mast:
        if r.get("WERKS", "") == plant or not r.get("WERKS"):
            mat_to_stlnr[r.get("MATNR", "")] = r.get("STLNR", "")
    stlnr_to_mat = {v: k for k, v in mat_to_stlnr.items()}

    # Active vendors/customers from POs/SOs
    ebeln_to_lifnr = {r["EBELN"]: r.get("LIFNR", "") for r in ekko}
    ekpo_plant = [r for r in ekpo if r.get("WERKS") == plant]
    active_vendors = set()
    for r in ekpo_plant:
        v = ebeln_to_lifnr.get(r.get("EBELN", ""), "")
        if v:
            active_vendors.add(v)

    vbeln_to_kunnr = {r["VBELN"]: r.get("KUNNR", "") for r in vbak}
    vbap_plant = [r for r in vbap if r.get("WERKS") == plant]
    active_customers = set()
    for r in vbap_plant:
        c = vbeln_to_kunnr.get(r.get("VBELN", ""), "")
        if c:
            active_customers.add(c)

    # EINA+EINE for vendor pricing
    eina_map = {r["INFNR"]: r for r in eina if r.get("LOEKZ") != "X"}
    eine_by_mat = defaultdict(list)
    for r in eine:
        infnr = r.get("INFNR", "")
        eina_r = eina_map.get(infnr, {})
        mat = eina_r.get("MATNR", "")
        vendor = eina_r.get("LIFNR", "")
        if mat and vendor:
            eine_by_mat[mat].append({
                "vendor": vendor,
                "price": safe_float(r.get("NETPR", "0")),
                "lead_days": safe_float(r.get("APLFZ", "0")),
                "min_qty": safe_float(r.get("NORBM", "0")),
                "currency": r.get("WAERS", "USD"),
            })

    # Use all materials (or limit if requested)
    top_materials = sorted(materials)
    if args.max_products > 0:
        # If limiting, prioritize by transaction activity + BOM completeness
        mat_activity = Counter()
        for r in ekpo_plant:
            mat_activity[r.get("MATNR", "")] += 1
        for r in vbap_plant:
            mat_activity[r.get("MATNR", "")] += 1
        ranked = [m for m, _ in mat_activity.most_common() if m in materials]
        bom_mats = set()
        for mat in ranked[:args.max_products]:
            stlnr = mat_to_stlnr.get(mat)
            if stlnr:
                bom_mats.add(mat)
                for sp in stpo:
                    if sp.get("STLNR") == stlnr and sp.get("IDNRK", "") in materials:
                        bom_mats.add(sp["IDNRK"])
        top_materials = sorted((set(ranked[:args.max_products]) | bom_mats))

    top_materials_set = set(top_materials)
    print(f"  Materials: {len(top_materials)} (of {len(materials)} total)")
    print(f"  Vendors: {len(active_vendors)}")
    print(f"  Customers: {len(active_customers)}")

    if args.dry_run:
        print("\n  DRY RUN — no Odoo writes.")
        return

    # ── Phase 3: Connect to Odoo ─────────────────────────────────────────
    print("\nPhase 3: Connecting to Odoo...")
    odoo = OdooClient(args.odoo_url, args.odoo_db, args.odoo_user, args.odoo_password)
    odoo.authenticate()

    # ── Create company ───────────────────────────────────────────────────
    print(f"\n  Creating company '{args.company_name}'...")
    existing = odoo.search("res.company", [["name", "=", args.company_name]], limit=1)
    if existing:
        company_id = existing[0]
        print(f"    Company already exists: id={company_id}")
    else:
        company_id = odoo.create("res.company", {
            "name": args.company_name,
            "currency_id": 2,  # USD (typically id=2 in Odoo)
        })
        print(f"    Created company id={company_id}")

    # Give admin access to the new company
    admin_user = odoo.search_read("res.users", [["id", "=", odoo.uid]], ["company_ids"])
    if admin_user:
        current_companies = admin_user[0].get("company_ids", [])
        if company_id not in current_companies:
            odoo.write("res.users", [odoo.uid], {
                "company_ids": [(4, company_id)],
            })
            print(f"    Added company to admin user")

    # ── Create warehouse ─────────────────────────────────────────────────
    print(f"\n  Creating warehouse for plant {plant}...")
    plant_info = next((w for w in t001w if w.get("WERKS") == plant), {})
    plant_name = plant_info.get("NAME1", f"Plant {plant}")

    existing_wh = odoo.search("stock.warehouse", [
        ["company_id", "=", company_id], ["code", "=", plant[:5]]
    ], limit=1)
    if existing_wh:
        wh_id = existing_wh[0]
        print(f"    Warehouse exists: id={wh_id}")
    else:
        wh_id = odoo.create("stock.warehouse", {
            "name": plant_name,
            "code": plant[:5],
            "company_id": company_id,
        })
        print(f"    Created warehouse id={wh_id}")

    # Get the warehouse's stock location
    wh_data = odoo.search_read("stock.warehouse", [["id", "=", wh_id]], ["lot_stock_id"])
    stock_location_id = wh_data[0]["lot_stock_id"][0] if wh_data else False

    # ── Create product categories ────────────────────────────────────────
    print("\n  Creating product categories...")
    cat_names = set()
    for mat in top_materials:
        matkl = mara_map.get(mat, {}).get("MATKL", "")
        if matkl:
            cat_names.add(matkl)

    cat_id_map: Dict[str, int] = {}
    for cat_name in sorted(cat_names):
        existing = odoo.search("product.category", [["name", "=", cat_name]], limit=1)
        if existing:
            cat_id_map[cat_name] = existing[0]
        else:
            cat_id_map[cat_name] = odoo.create("product.category", {"name": cat_name})
    print(f"    {len(cat_id_map)} categories")

    # ── Create vendors ───────────────────────────────────────────────────
    print("\n  Creating vendors...")
    vendor_id_map: Dict[str, int] = {}
    lfa1_map = {r["LIFNR"]: r for r in lfa1}
    count = 0
    vendor_limit = sorted(active_vendors)[:args.max_vendors] if args.max_vendors > 0 else sorted(active_vendors)
    for v_id in vendor_limit:
        v = lfa1_map.get(v_id, {})
        name = v.get("NAME1", v_id)
        existing = odoo.search("res.partner", [
            ["name", "=", name], ["company_id", "in", [company_id, False]]
        ], limit=1)
        if existing:
            vendor_id_map[v_id] = existing[0]
        else:
            vendor_id_map[v_id] = odoo.create("res.partner", {
                "name": name,
                "is_company": True,
                "supplier_rank": 1,
                "city": v.get("ORT01", ""),
                "country_id": False,  # would need country mapping
                "phone": v.get("TELF1", ""),
                "company_id": company_id,
            })
            count += 1
    print(f"    {count} new vendors (of {len(vendor_id_map)} total)")

    # ── Create customers ─────────────────────────────────────────────────
    print("\n  Creating customers...")
    customer_id_map: Dict[str, int] = {}
    kna1_map = {r["KUNNR"]: r for r in kna1}
    count = 0
    cust_limit = sorted(active_customers)[:args.max_customers] if args.max_customers > 0 else sorted(active_customers)
    for c_id in cust_limit:
        c = kna1_map.get(c_id, {})
        name = c.get("NAME1", c_id)
        existing = odoo.search("res.partner", [
            ["name", "=", name], ["company_id", "in", [company_id, False]]
        ], limit=1)
        if existing:
            customer_id_map[c_id] = existing[0]
        else:
            customer_id_map[c_id] = odoo.create("res.partner", {
                "name": name,
                "is_company": True,
                "customer_rank": 1,
                "city": c.get("ORT01", ""),
                "phone": c.get("TELF1", ""),
                "company_id": company_id,
            })
            count += 1
    print(f"    {count} new customers (of {len(customer_id_map)} total)")

    # ── Create products (batch) ───────────────────────────────────────────
    print("\n  Creating products...")
    product_id_map: Dict[str, int] = {}
    tmpl_id_map: Dict[str, int] = {}

    # Check which products already exist
    existing_prods = odoo.search_read(
        "product.product",
        [["company_id", "in", [company_id, False]], ["default_code", "!=", False]],
        ["id", "default_code", "product_tmpl_id"],
    )
    for ep in existing_prods:
        code = ep.get("default_code")
        if code and code in top_materials_set:
            product_id_map[code] = ep["id"]
            tmpl_id_map[code] = ep["product_tmpl_id"][0] if ep.get("product_tmpl_id") else None

    # Batch create missing products
    to_create = []
    to_create_mats = []
    for mat in top_materials:
        if mat in product_id_map:
            continue
        desc = makt_map.get(mat, mat)
        mara_r = mara_map.get(mat, {})
        mbew_r = mbew_map.get(mat, {})

        std_cost = safe_float(mbew_r.get("STPRS", "0"))
        mvg_price = safe_float(mbew_r.get("VERPR", "0"))
        cost = std_cost if std_cost > 0 else (mvg_price if mvg_price > 0 else 10.0)
        sale_price = cost * 1.4

        categ_id = cat_id_map.get(mara_r.get("MATKL", ""), 1)
        weight = safe_float(mara_r.get("NTGEW", "0"))

        to_create.append({
            "name": desc[:128],
            "default_code": mat,
            "type": "consu",
            "categ_id": categ_id,
            "standard_price": cost,
            "list_price": sale_price,
            "weight": weight,
            "sale_ok": True,
            "purchase_ok": True,
            "company_id": company_id,
        })
        to_create_mats.append(mat)

    if to_create:
        # Batch create in chunks of 100 (Odoo can handle ~200 but be conservative)
        CHUNK = 100
        for i in range(0, len(to_create), CHUNK):
            chunk_vals = to_create[i:i + CHUNK]
            chunk_mats = to_create_mats[i:i + CHUNK]
            new_ids = odoo.create_batch("product.product", chunk_vals)
            for mat, pid in zip(chunk_mats, new_ids):
                product_id_map[mat] = pid
            print(f"    ... {min(i + CHUNK, len(to_create))}/{len(to_create)} products created")

        # Batch fetch template IDs for new products
        new_prod_ids = [product_id_map[m] for m in to_create_mats if m in product_id_map]
        if new_prod_ids:
            tmpl_data = odoo.search_read(
                "product.product",
                [["id", "in", new_prod_ids]],
                ["id", "default_code", "product_tmpl_id"],
            )
            for td in tmpl_data:
                code = td.get("default_code")
                if code and td.get("product_tmpl_id"):
                    tmpl_id_map[code] = td["product_tmpl_id"][0]

    print(f"    {len(to_create)} new products (of {len(product_id_map)} total)")

    # ── Create vendor pricelists (batch) ──────────────────────────────────
    print("\n  Creating vendor pricelists...")
    # Check existing
    existing_si = odoo.search_read(
        "product.supplierinfo",
        [["company_id", "=", company_id]],
        ["product_tmpl_id", "partner_id"],
    )
    existing_si_keys = {(r["product_tmpl_id"][0] if r.get("product_tmpl_id") else 0,
                         r["partner_id"][0] if r.get("partner_id") else 0) for r in existing_si}

    si_batch = []
    for mat in top_materials:
        tmpl_id = tmpl_id_map.get(mat)
        if not tmpl_id:
            continue
        for info in eine_by_mat.get(mat, []):
            vendor_odoo_id = vendor_id_map.get(info["vendor"])
            if not vendor_odoo_id:
                continue
            if (tmpl_id, vendor_odoo_id) in existing_si_keys:
                continue
            si_batch.append({
                "partner_id": vendor_odoo_id,
                "product_tmpl_id": tmpl_id,
                "min_qty": info["min_qty"],
                "price": info["price"],
                "delay": int(info["lead_days"]) if info["lead_days"] else 7,
                "company_id": company_id,
            })
    if si_batch:
        for i in range(0, len(si_batch), 100):
            odoo.create_batch("product.supplierinfo", si_batch[i:i + 100])
    print(f"    {len(si_batch)} vendor pricelists")

    # ── Create BOMs ──────────────────────────────────────────────────────
    print("\n  Creating BOMs...")
    bom_count = 0
    seen_boms = set()
    for r in stko:
        stlnr = r.get("STLNR", "")
        if stlnr in seen_boms or r.get("LOEKZ") == "X":
            continue

        parent_mat = stlnr_to_mat.get(stlnr, "")
        if parent_mat not in product_id_map:
            continue

        parent_tmpl = tmpl_id_map.get(parent_mat)
        if not parent_tmpl:
            continue

        # Collect BOM lines
        lines = []
        for sp in stpo:
            if sp.get("STLNR") != stlnr:
                continue
            comp_mat = sp.get("IDNRK", "")
            comp_id = product_id_map.get(comp_mat)
            if not comp_id:
                continue
            qty = safe_float(sp.get("MENGE", "1"))
            if qty <= 0:
                qty = 1.0  # Odoo requires qty > 0 for BOM lines
            lines.append((0, 0, {
                "product_id": comp_id,
                "product_qty": qty,
            }))

        if not lines:
            continue

        seen_boms.add(stlnr)

        # Check if BOM already exists
        existing = odoo.search("mrp.bom", [
            ["product_tmpl_id", "=", parent_tmpl],
            ["company_id", "=", company_id],
        ], limit=1)

        if not existing:
            bom_qty = safe_float(r.get("BMENG", "1"))
            if bom_qty <= 0:
                bom_qty = 1.0
            try:
                odoo.create("mrp.bom", {
                    "product_tmpl_id": parent_tmpl,
                    "product_qty": bom_qty,
                    "type": "normal",
                    "company_id": company_id,
                    "bom_line_ids": lines,
                })
                bom_count += 1
            except Exception as e:
                if bom_count == 0:
                    print(f"    WARNING: BOM error: {str(e)[:100]}")

    print(f"    {bom_count} BOMs created")

    # ── Create reordering rules (batch) ──────────────────────────────────
    print("\n  Creating reordering rules...")
    existing_ops = odoo.search_read(
        "stock.warehouse.orderpoint",
        [["warehouse_id", "=", wh_id]],
        ["product_id"],
    )
    existing_op_products = {r["product_id"][0] for r in existing_ops if r.get("product_id")}

    op_batch = []
    for mat in top_materials:
        marc_r = marc_map.get(mat, {})
        eisbe = safe_float(marc_r.get("EISBE", "0"))
        minbe = safe_float(marc_r.get("MINBE", "0"))
        mabst = safe_float(marc_r.get("MABST", "0"))

        prod_id = product_id_map.get(mat)
        if not prod_id or prod_id in existing_op_products:
            continue

        min_qty = minbe if minbe > 0 else eisbe
        max_qty = mabst if mabst > 0 else min_qty * 3

        if min_qty <= 0:
            continue

        op_batch.append({
            "product_id": prod_id,
            "warehouse_id": wh_id,
            "product_min_qty": min_qty,
            "product_max_qty": max_qty,
            "qty_multiple": 1.0,
            "company_id": company_id,
        })

    if op_batch:
        for i in range(0, len(op_batch), 100):
            odoo.create_batch("stock.warehouse.orderpoint", op_batch[i:i + 100])
    print(f"    {len(op_batch)} reordering rules")

    # ── Create work centers (CRHD) ──────────────────────────────────────
    print("\n  Creating work centers...")
    wc_count = 0
    wc_errors = 0
    wc_id_map: Dict[str, int] = {}
    for r in crhd:
        if r.get("WERKS", "") != plant and r.get("WERKS", ""):
            continue
        objid = r.get("OBJID", "")
        name = r.get("ARBPL", objid)
        if not name or objid in wc_id_map:
            continue
        existing = odoo.search("mrp.workcenter", [
            ["name", "=", name], ["company_id", "in", [company_id, False]]
        ], limit=1)
        if existing:
            wc_id_map[objid] = existing[0]
        else:
            try:
                wc_id_map[objid] = odoo.create("mrp.workcenter", {
                    "name": f"{name} ({args.company_name[:10]})",
                    "company_id": company_id,
                })
                wc_count += 1
            except Exception:
                wc_errors += 1
    print(f"    {wc_count} work centers ({wc_errors} skipped due to company conflicts)")

    # ── Create purchase orders (EKKO+EKPO) ───────────────────────────────
    print("\n  Creating purchase orders...")
    po_count = 0
    po_line_count = 0
    # Group PO lines by PO number
    po_lines_by_ebeln = defaultdict(list)
    for r in ekpo_plant:
        mat = r.get("MATNR", "")
        if mat not in product_id_map:
            continue
        po_lines_by_ebeln[r.get("EBELN", "")].append(r)

    for ebeln, lines in po_lines_by_ebeln.items():
        ekko_r = next((e for e in ekko if e.get("EBELN") == ebeln), None)
        if not ekko_r:
            continue
        vendor = ekko_r.get("LIFNR", "")
        vendor_odoo = vendor_id_map.get(vendor)
        if not vendor_odoo:
            continue

        # Check if PO exists
        existing = odoo.search("purchase.order", [
            ["partner_ref", "=", ebeln], ["company_id", "=", company_id]
        ], limit=1)
        if existing:
            continue

        order_lines = []
        for line in lines:
            prod_id = product_id_map.get(line.get("MATNR", ""))
            if not prod_id:
                continue
            order_lines.append((0, 0, {
                "product_id": prod_id,
                "product_qty": safe_float(line.get("MENGE", "0")),
                "price_unit": safe_float(line.get("NETPR", "0")),
            }))
            po_line_count += 1

        if not order_lines:
            continue

        try:
            odoo.create("purchase.order", {
                "partner_id": vendor_odoo,
                "partner_ref": ebeln,
                "company_id": company_id,
                "order_line": order_lines,
            })
            po_count += 1
        except Exception as e:
            if po_count == 0:
                print(f"    WARNING: PO creation error: {str(e)[:100]}")

        if po_count % 100 == 0 and po_count > 0:
            print(f"    ... {po_count} POs created")

    print(f"    {po_count} POs, {po_line_count} lines")

    # ── Create sale orders (VBAK+VBAP) ───────────────────────────────────
    print("\n  Creating sale orders...")
    so_count = 0
    so_line_count = 0
    so_lines_by_vbeln = defaultdict(list)
    for r in vbap_plant:
        mat = r.get("MATNR", "")
        if mat not in product_id_map:
            continue
        so_lines_by_vbeln[r.get("VBELN", "")].append(r)

    for vbeln, lines in so_lines_by_vbeln.items():
        vbak_r = next((v for v in vbak if v.get("VBELN") == vbeln), None)
        if not vbak_r:
            continue
        cust = vbak_r.get("KUNNR", "")
        cust_odoo = customer_id_map.get(cust)
        if not cust_odoo:
            continue

        existing = odoo.search("sale.order", [
            ["client_order_ref", "=", vbeln], ["company_id", "=", company_id]
        ], limit=1)
        if existing:
            continue

        order_lines = []
        for line in lines:
            prod_id = product_id_map.get(line.get("MATNR", ""))
            if not prod_id:
                continue
            order_lines.append((0, 0, {
                "product_id": prod_id,
                "product_uom_qty": safe_float(line.get("KWMENG", "0")),
                "price_unit": safe_float(line.get("NETPR", "0")),
            }))
            so_line_count += 1

        if not order_lines:
            continue

        try:
            odoo.create("sale.order", {
                "partner_id": cust_odoo,
                "client_order_ref": vbeln,
                "company_id": company_id,
                "warehouse_id": wh_id,
                "order_line": order_lines,
            })
            so_count += 1
        except Exception as e:
            if so_count == 0:
                print(f"    WARNING: SO creation error: {str(e)[:100]}")

        if so_count % 100 == 0 and so_count > 0:
            print(f"    ... {so_count} SOs created")

    print(f"    {so_count} SOs, {so_line_count} lines")

    # ── Create manufacturing orders (AFKO) ───────────────────────────────
    print("\n  Creating manufacturing orders...")
    mo_count = 0
    for r in afko:
        mat = r.get("PLNBEZ", "")
        prod_id = product_id_map.get(mat)
        if not prod_id:
            continue
        tmpl_id = tmpl_id_map.get(mat)
        if not tmpl_id:
            continue

        # Find BOM for this product
        bom_ids = odoo.search("mrp.bom", [
            ["product_tmpl_id", "=", tmpl_id], ["company_id", "=", company_id]
        ], limit=1)

        aufnr = r.get("AUFNR", "")
        existing = odoo.search("mrp.production", [
            ["origin", "=", aufnr], ["company_id", "=", company_id]
        ], limit=1)
        if existing:
            continue

        try:
            vals = {
                "product_id": prod_id,
                "product_qty": safe_float(r.get("GAMNG", "1")),
                "origin": aufnr,
                "company_id": company_id,
            }
            if bom_ids:
                vals["bom_id"] = bom_ids[0]
            odoo.create("mrp.production", vals)
            mo_count += 1
        except Exception as e:
            if mo_count == 0:
                print(f"    WARNING: MO creation error: {str(e)[:100]}")

    print(f"    {mo_count} manufacturing orders")

    # ── Create lot/serial numbers (MCH1+MCHA) ───────────────────────────
    print("\n  Creating lot/serial numbers...")
    lot_count = 0
    for r in mcha:
        mat = r.get("MATNR", "")
        prod_id = product_id_map.get(mat)
        if not prod_id or r.get("LVORM") == "X":
            continue
        charg = r.get("CHARG", "")
        if not charg:
            continue
        existing = odoo.search("stock.lot", [
            ["name", "=", charg], ["product_id", "=", prod_id], ["company_id", "=", company_id]
        ], limit=1)
        if not existing:
            try:
                odoo.create("stock.lot", {
                    "name": charg,
                    "product_id": prod_id,
                    "company_id": company_id,
                })
                lot_count += 1
            except Exception:
                pass
    print(f"    {lot_count} lots/batches")

    # ── Create inventory (MARD → stock.quant via inventory adjustment) ───
    print("\n  Creating inventory levels...")
    inv_count = 0
    if stock_location_id:
        for mat in top_materials:
            qty = stock_map.get(mat, 0.0)
            if qty <= 0:
                continue
            prod_id = product_id_map.get(mat)
            if not prod_id:
                continue
            # Check if quant already exists
            existing = odoo.search("stock.quant", [
                ["product_id", "=", prod_id],
                ["location_id", "=", stock_location_id],
                ["company_id", "=", company_id],
            ], limit=1)
            if existing:
                continue
            try:
                odoo.create("stock.quant", {
                    "product_id": prod_id,
                    "location_id": stock_location_id,
                    "inventory_quantity": qty,
                    "company_id": company_id,
                })
                inv_count += 1
            except Exception as e:
                if inv_count == 0:
                    print(f"    WARNING: Inventory error: {str(e)[:100]}")
    print(f"    {inv_count} inventory records")

    # ── Create maintenance equipment (EQUI) ──────────────────────────────
    print("\n  Creating maintenance equipment...")
    equip_count = 0
    for r in equi[:500]:  # cap at 500 to avoid slowness
        equnr = r.get("EQUNR", "")
        if not equnr:
            continue
        existing = odoo.search("maintenance.equipment", [
            ["name", "=", equnr], ["company_id", "=", company_id]
        ], limit=1)
        if not existing:
            try:
                odoo.create("maintenance.equipment", {
                    "name": equnr,
                    "equipment_assign_to": "other",
                    "company_id": company_id,
                })
                equip_count += 1
            except Exception as e:
                if equip_count == 0:
                    print(f"    WARNING: Equipment error: {str(e)[:100]}")
                break  # If model doesn't exist, stop
    print(f"    {equip_count} equipment records")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  Odoo population complete!")
    print(f"  Company:      {args.company_name} (id={company_id})")
    print(f"  Warehouse:    {plant_name} (id={wh_id})")
    print(f"")
    print(f"  Master Data:")
    print(f"    Products:     {len(product_id_map)}")
    print(f"    Categories:   {len(cat_id_map)}")
    print(f"    Vendors:      {len(vendor_id_map)}")
    print(f"    Customers:    {len(customer_id_map)}")
    print(f"    Pricelists:   {count}")
    print(f"    BOMs:         {bom_count}")
    print(f"    Work centers: {wc_count}")
    print(f"    Reorder rules:{len(op_batch) if 'op_batch' in dir() else 0}")
    print(f"")
    print(f"  Transaction Data:")
    print(f"    Purchase orders: {po_count} ({po_line_count} lines)")
    print(f"    Sale orders:     {so_count} ({so_line_count} lines)")
    print(f"    Mfg orders:      {mo_count}")
    print(f"    Lots/batches:    {lot_count}")
    print(f"    Inventory:       {inv_count}")
    print(f"    Equipment:       {equip_count}")
    print(f"")
    print(f"  Odoo URL: {args.odoo_url}")
    print(f"  Switch to company '{args.company_name}' in the top-right menu")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

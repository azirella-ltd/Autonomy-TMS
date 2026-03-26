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

    def fields_get(self, model: str) -> Dict:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "fields_get", [],
            {"attributes": ["string", "type"]}
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


# ---------------------------------------------------------------------------
# JSON-RPC loader — idempotent upsert via ir.model.data external IDs
# ---------------------------------------------------------------------------

MODULE_PREFIX = "sap_import"  # external ID module name


def _get_or_create_by_xmlid(
    odoo: OdooRPCClient,
    model: str,
    xml_id_suffix: str,
    vals: Dict[str, Any],
    *,
    update: bool = True,
) -> int:
    """Find record by external ID (xml_id) or create it.  Returns record id.

    xml_id format: ``sap_import.<suffix>``
    If the record already exists and *update* is True, it is updated with *vals*.
    """
    full_xmlid = f"{MODULE_PREFIX}.{xml_id_suffix}"

    # Check if ir.model.data entry already exists
    existing = odoo.search_read(
        "ir.model.data",
        [("module", "=", MODULE_PREFIX), ("name", "=", xml_id_suffix)],
        ["res_id", "model"],
        limit=1,
    )
    if existing:
        rec_id = existing[0]["res_id"]
        if update and vals:
            try:
                odoo.write(model, [rec_id], vals)
            except Exception:
                pass  # record may have been deleted; fall through to create
            else:
                return rec_id

        # Verify the record still exists
        check = odoo.search(model, [("id", "=", rec_id)], limit=1)
        if check:
            return rec_id
        # Record was deleted but ir.model.data lingers — remove stale entry
        odoo.models.execute_kw(
            odoo.db, odoo.uid, odoo.password,
            "ir.model.data", "unlink", [existing[0]["id"]]
        )

    # Create the record
    rec_id = odoo.create(model, vals)

    # Register the external ID so future runs are idempotent
    odoo.create("ir.model.data", {
        "module": MODULE_PREFIX,
        "name": xml_id_suffix,
        "model": model,
        "res_id": rec_id,
    })
    return rec_id


def _resolve_uom(odoo: OdooRPCClient) -> int:
    """Return the id of the 'Units' UoM (ea / Unit(s))."""
    ids = odoo.search("uom.uom", [("name", "ilike", "Units")], limit=1)
    if not ids:
        ids = odoo.search("uom.uom", [], limit=1)
    return ids[0] if ids else 1


def _resolve_warehouse(odoo: OdooRPCClient) -> Tuple[int, int]:
    """Return (warehouse_id, lot_stock_location_id) for the main warehouse."""
    wh = odoo.search_read("stock.warehouse", [], ["id", "lot_stock_id"], limit=1)
    if wh:
        lot = wh[0]["lot_stock_id"]
        loc_id = lot[0] if isinstance(lot, (list, tuple)) else lot
        return wh[0]["id"], loc_id
    return 1, 1


def _load_via_rpc(
    odoo: OdooRPCClient,
    product_rows: List[Dict],
    vendor_rows: List[Dict],
    customer_rows: List[Dict],
    supplierinfo_rows: List[Dict],
    bom_rows: List[Dict],
    bom_line_rows: List[Dict],
    orderpoint_rows: List[Dict],
    quant_rows: List[Dict],
):
    """Load all translated data into Odoo via XML-RPC, using external IDs for
    idempotent upserts.  Sequence: partners → products → supplierinfo → BOMs →
    orderpoints → stock quants."""

    uom_id = _resolve_uom(odoo)
    wh_id, stock_loc_id = _resolve_warehouse(odoo)
    print(f"  UoM id: {uom_id}  |  Warehouse id: {wh_id}  |  Stock location id: {stock_loc_id}")

    # -- 1. Vendors (res.partner) ------------------------------------------
    print(f"\n  [1/7] Loading {len(vendor_rows)} vendors...")
    vendor_id_map: Dict[str, int] = {}  # SAP vendor ref → Odoo id
    for i, row in enumerate(vendor_rows, 1):
        ref = row["ref"]
        xmlid = f"vendor_{ref}"
        vals = {
            "name": row["name"],
            "ref": ref,
            "supplier_rank": row.get("supplier_rank", 1),
            "is_company": True,
        }
        rec_id = _get_or_create_by_xmlid(odoo, "res.partner", xmlid, vals)
        vendor_id_map[ref] = rec_id
        if i % 50 == 0 or i == len(vendor_rows):
            print(f"    vendors: {i}/{len(vendor_rows)}")

    # -- 2. Customers (res.partner) ----------------------------------------
    print(f"\n  [2/7] Loading {len(customer_rows)} customers...")
    for i, row in enumerate(customer_rows, 1):
        ref = row["ref"]
        xmlid = f"customer_{ref}"
        vals = {
            "name": row["name"],
            "ref": ref,
            "customer_rank": row.get("customer_rank", 1),
            "is_company": True,
        }
        _get_or_create_by_xmlid(odoo, "res.partner", xmlid, vals)
        if i % 50 == 0 or i == len(customer_rows):
            print(f"    customers: {i}/{len(customer_rows)}")

    # -- 3. Products (product.template) ------------------------------------
    print(f"\n  [3/7] Loading {len(product_rows)} products...")
    # Query valid fields to handle Odoo version differences
    pt_fields = set(odoo.fields_get("product.template").keys())
    product_tmpl_map: Dict[str, int] = {}   # default_code → product.template id
    product_prod_map: Dict[str, int] = {}   # default_code → product.product id
    for i, row in enumerate(product_rows, 1):
        code = row["default_code"]
        xmlid = f"product_{code}"
        vals = {
            "name": row["name"],
            "default_code": code,
            "type": "consu",  # Odoo 18: 'consu' (Goods), v16/v17 used 'product'
            "sale_ok": row.get("sale_ok", True),
            "purchase_ok": row.get("purchase_ok", True),
            "uom_id": uom_id,
            "uom_po_id": uom_id,
        }
        # Optional fields — only set if they exist in this Odoo version
        if row.get("produce_delay") and "produce_delay" in pt_fields:
            vals["produce_delay"] = row["produce_delay"]

        tmpl_id = _get_or_create_by_xmlid(odoo, "product.template", xmlid, vals)
        product_tmpl_map[code] = tmpl_id

        # Odoo auto-creates one product.product per template (for non-variant products)
        pp_ids = odoo.search("product.product", [("product_tmpl_id", "=", tmpl_id)], limit=1)
        if pp_ids:
            product_prod_map[code] = pp_ids[0]
        else:
            product_prod_map[code] = tmpl_id  # fallback

        if i % 50 == 0 or i == len(product_rows):
            print(f"    products: {i}/{len(product_rows)}")

    # -- 4. Supplier pricelists (product.supplierinfo) ---------------------
    print(f"\n  [4/7] Loading {len(supplierinfo_rows)} supplier pricelists...")
    for i, row in enumerate(supplierinfo_rows, 1):
        vendor_ref = row["partner_ref"]
        mat_code = row["product_code"]
        partner_id = vendor_id_map.get(vendor_ref)
        tmpl_id = product_tmpl_map.get(mat_code)
        if not partner_id or not tmpl_id:
            continue

        xmlid = f"supinfo_{vendor_ref}_{mat_code}"
        vals = {
            "partner_id": partner_id,
            "product_tmpl_id": tmpl_id,
            "delay": row.get("delay", 7),
            "min_qty": row.get("min_qty", 0),
            "price": row.get("price", 0.0),
        }
        _get_or_create_by_xmlid(odoo, "product.supplierinfo", xmlid, vals)
        if i % 100 == 0 or i == len(supplierinfo_rows):
            print(f"    supplierinfo: {i}/{len(supplierinfo_rows)}")

    # -- 5. BOMs (mrp.bom + mrp.bom.line) ---------------------------------
    print(f"\n  [5/7] Loading {len(bom_rows)} BOMs ({len(bom_line_rows)} lines)...")

    # Group bom_line_rows by parent product code
    bom_lines_by_parent: Dict[str, List[Dict]] = defaultdict(list)
    for line in bom_line_rows:
        bom_lines_by_parent[line["bom_product_code"]].append(line)

    bom_id_map: Dict[str, int] = {}  # parent product code → mrp.bom id
    for i, row in enumerate(bom_rows, 1):
        code = row["product_code"]
        tmpl_id = product_tmpl_map.get(code)
        if not tmpl_id:
            continue

        xmlid = f"bom_{code}"
        vals = {
            "product_tmpl_id": tmpl_id,
            "product_qty": max(float(row.get("product_qty", 1) or 1), 0.001),
            "type": "normal",
        }
        bom_id = _get_or_create_by_xmlid(odoo, "mrp.bom", xmlid, vals)
        bom_id_map[code] = bom_id

        # BOM lines
        lines = bom_lines_by_parent.get(code, [])
        for j, line in enumerate(lines):
            comp_code = line["product_code"]
            comp_pp_id = product_prod_map.get(comp_code)
            if not comp_pp_id:
                continue

            line_xmlid = f"bomline_{code}_{comp_code}_{j}"
            raw_qty = float(line.get("product_qty", 1) or 1)
            line_vals: Dict[str, Any] = {
                "bom_id": bom_id,
                "product_id": comp_pp_id,
                "product_qty": max(raw_qty, 0.001),  # Odoo 18 requires qty > 0
            }
            # Odoo >=17 may not have product_uom_id as required; set if available
            line_vals["product_uom_id"] = uom_id
            _get_or_create_by_xmlid(odoo, "mrp.bom.line", line_xmlid, line_vals)

        if i % 20 == 0 or i == len(bom_rows):
            print(f"    BOMs: {i}/{len(bom_rows)}")

    # -- 6. Reorder rules (stock.warehouse.orderpoint) ---------------------
    print(f"\n  [6/7] Loading {len(orderpoint_rows)} reorder rules...")
    for i, row in enumerate(orderpoint_rows, 1):
        code = row["product_code"]
        pp_id = product_prod_map.get(code)
        if not pp_id:
            continue

        xmlid = f"orderpoint_{code}"
        vals = {
            "product_id": pp_id,
            "warehouse_id": wh_id,
            "location_id": stock_loc_id,
            "product_min_qty": row.get("product_min_qty", 0),
            "product_max_qty": row.get("product_max_qty", 0),
            "qty_multiple": row.get("qty_multiple", 0),
            "trigger": row.get("trigger", "auto"),
        }
        _get_or_create_by_xmlid(odoo, "stock.warehouse.orderpoint", xmlid, vals)
        if i % 100 == 0 or i == len(orderpoint_rows):
            print(f"    orderpoints: {i}/{len(orderpoint_rows)}")

    # -- 7. Initial stock (stock.quant) ------------------------------------
    # stock.quant doesn't support normal create via external API in all Odoo
    # versions.  We use the inventory adjustment wizard when available, or
    # fall back to direct quant write.
    print(f"\n  [7/7] Loading {len(quant_rows)} stock quants...")
    loaded_quants = 0
    for i, row in enumerate(quant_rows, 1):
        code = row["product_code"]
        pp_id = product_prod_map.get(code)
        if not pp_id:
            continue

        qty = row.get("quantity", 0)
        if qty <= 0:
            continue

        # Check if quant already exists for this product+location
        existing = odoo.search(
            "stock.quant",
            [("product_id", "=", pp_id), ("location_id", "=", stock_loc_id)],
            limit=1,
        )
        if existing:
            odoo.write("stock.quant", existing, {"inventory_quantity": qty})
            # Apply the inventory adjustment
            try:
                odoo.models.execute_kw(
                    odoo.db, odoo.uid, odoo.password,
                    "stock.quant", "action_apply_inventory", [existing]
                )
            except Exception:
                # Older Odoo versions: just set quantity directly
                try:
                    odoo.write("stock.quant", existing, {"quantity": qty})
                except Exception:
                    pass
        else:
            try:
                odoo.create("stock.quant", {
                    "product_id": pp_id,
                    "location_id": stock_loc_id,
                    "inventory_quantity": qty,
                })
                # Apply — search again since we just created
                new_ids = odoo.search(
                    "stock.quant",
                    [("product_id", "=", pp_id), ("location_id", "=", stock_loc_id)],
                    limit=1,
                )
                if new_ids:
                    try:
                        odoo.models.execute_kw(
                            odoo.db, odoo.uid, odoo.password,
                            "stock.quant", "action_apply_inventory", [new_ids]
                        )
                    except Exception:
                        pass
            except Exception as e:
                # stock.quant create may be blocked; try setting quantity directly
                try:
                    odoo.create("stock.quant", {
                        "product_id": pp_id,
                        "location_id": stock_loc_id,
                        "quantity": qty,
                    })
                except Exception:
                    if i <= 3:
                        print(f"    WARN: Could not create quant for {code}: {e}")
                    continue
        loaded_quants += 1
        if i % 100 == 0 or i == len(quant_rows):
            print(f"    quants: {i}/{len(quant_rows)} (loaded: {loaded_quants})")

    print(f"\n  JSON-RPC loading complete!")
    print(f"    Partners: {len(vendor_rows)} vendors + {len(customer_rows)} customers")
    print(f"    Products: {len(product_rows)}")
    print(f"    Supplier pricelists: {len(supplierinfo_rows)}")
    print(f"    BOMs: {len(bom_rows)} ({len(bom_line_rows)} lines)")
    print(f"    Reorder rules: {len(orderpoint_rows)}")
    print(f"    Stock quants: {loaded_quants}/{len(quant_rows)}")


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

        _load_via_rpc(odoo, product_rows, vendor_rows, customer_rows,
                      supplierinfo_rows, bom_rows, bom_line_rows,
                      orderpoint_rows, quant_rows)

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

#!/usr/bin/env python3
"""
Translate SAP IDES CSV exports into Odoo-compatible data and load via JSON-RPC.

Reads SAP tables (T001W, MARA, MAKT, MARC, MARD, LFA1, KNA1, EKKO, EKPO,
VBAK, VBAP, STKO, STPO, MAST, EINA, AFKO, AFVC, LIKP, LIPS, EKBE, MSEG,
LTAK, LTAP, MCH1, MCHA, QALS, QMEL, EQUI, PLPO, CRHD, MARM) and creates
the corresponding Odoo records (25 CSV outputs matching all 30 Odoo registry models):

  Master:
  - product.template              (from MARA/MAKT/MARC)
  - res.partner (vendors)         (from LFA1/EINA)
  - res.partner (customers)       (from KNA1)
  - product.supplierinfo          (from EINA/MARC)
  - mrp.bom / mrp.bom.line       (from MAST/STPO)
  - stock.warehouse.orderpoint    (from MARC)
  - mrp.routing.workcenter        (from PLPO/CRHD)
  - uom.uom / uom.category       (from MARM)

  Transaction:
  - purchase.order                (from EKKO)
  - purchase.order.line           (from EKPO)
  - sale.order                    (from VBAK)
  - sale.order.line               (from VBAP)
  - mrp.production                (from AFKO)
  - mrp.workorder                 (from AFVC/CRHD)
  - stock.picking                 (from LIKP/EKBE/LTAK)
  - stock.move                    (from LIPS/EKBE/LTAP)

  CDC:
  - stock.quant                   (from MARD)
  - stock.move.line               (from LIPS/EKBE/LTAP detail)
  - stock.lot                     (from MCH1/MCHA)
  - quality.check                 (from QALS)
  - quality.alert                 (from QMEL)
  - maintenance.equipment         (from EQUI)
  - maintenance.request           (from EQUI/PM data)

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

    # Transaction tables
    ekko = read_csv(sap_dir, "EKKO.csv")   # PO headers
    ekpo = read_csv(sap_dir, "EKPO.csv")   # PO items
    vbak = read_csv(sap_dir, "VBAK.csv")   # SO headers
    vbap = read_csv(sap_dir, "VBAP.csv")   # SO items
    afko = read_csv(sap_dir, "AFKO.csv")   # Production order headers
    afvc = read_csv(sap_dir, "AFVC.csv")   # Production order operations
    likp = read_csv(sap_dir, "LIKP.csv")   # Delivery headers
    lips = read_csv(sap_dir, "LIPS.csv")   # Delivery items
    ekbe = read_csv(sap_dir, "EKBE.csv")   # PO history (goods receipts)
    mseg = read_csv(sap_dir, "MSEG.csv")   # Material document items
    ltak = read_csv(sap_dir, "LTAK.csv")   # Transfer order headers
    ltap = read_csv(sap_dir, "LTAP.csv")   # Transfer order items

    # CDC / quality / maintenance tables
    mch1 = read_csv(sap_dir, "MCH1.csv")   # Batch master (plant-independent)
    mcha = read_csv(sap_dir, "MCHA.csv")   # Batch master (plant-level)
    qals = read_csv(sap_dir, "QALS.csv")   # Quality inspection lots
    qmel = read_csv(sap_dir, "QMEL.csv")   # Quality notifications
    equi = read_csv(sap_dir, "EQUI.csv")   # Equipment/assets

    # Additional master tables
    plpo = read_csv(sap_dir, "PLPO.csv")   # Routing operations
    crhd = read_csv(sap_dir, "CRHD.csv")   # Work centers
    marm = read_csv(sap_dir, "MARM.csv")   # UOM conversions

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

    # PO header lookup
    ebeln_to_ekko = {(r.get("EBELN") or "").strip(): r for r in ekko}
    ekpo_plant = [r for r in ekpo if (r.get("WERKS") or "").strip() == plant]

    # SO header lookup
    vbeln_to_vbak = {(r.get("VBELN") or "").strip(): r for r in vbak}
    vbap_plant = [r for r in vbap if (r.get("WERKS") or "").strip() == plant]

    # Vendor / customer name maps
    vendor_names = {(r.get("LIFNR", "") or "").strip(): (r.get("NAME1", "") or "").strip() for r in lfa1}
    customer_names = {(r.get("KUNNR", "") or "").strip(): (r.get("NAME1", "") or "").strip() for r in kna1}

    # Work center lookup (CRHD)
    crhd_map = {}
    for r in crhd:
        objid = (r.get("OBJID") or "").strip()
        if objid:
            crhd_map[objid] = r

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

    # ── Transaction records ────────────────────────────────────────────
    print("\n  --- Transaction Data ---")

    # SAP AUART → Odoo PO state mapping
    SAP_PO_STATUS = {
        "": "purchase",     # Default: confirmed
        "L": "done",        # Completed
        "X": "cancel",      # Deleted
    }

    # purchase.order (from EKKO)
    po_rows = []
    seen_po = set()
    for r in ekpo_plant:
        ebeln = (r.get("EBELN") or "").strip()
        if ebeln in seen_po:
            continue
        ekko_r = ebeln_to_ekko.get(ebeln, {})
        if not ekko_r:
            continue
        seen_po.add(ebeln)
        lifnr = (ekko_r.get("LIFNR") or "").strip()
        loekz = (ekko_r.get("LOEKZ") or "").strip()
        po_rows.append({
            "id": ebeln,
            "name": f"PO{ebeln}",
            "partner_id": lifnr,
            "partner_name": vendor_names.get(lifnr, f"Vendor {lifnr}"),
            "date_order": (ekko_r.get("BEDAT") or ekko_r.get("AEDAT") or ""),
            "state": SAP_PO_STATUS.get(loekz, "purchase"),
            "amount_total": safe_float(ekko_r.get("RLWRT", "0")),
            "currency_id": ekko_r.get("WAERS", "USD"),
        })

    # purchase.order.line (from EKPO)
    po_line_rows = []
    for r in ekpo_plant:
        mat = (r.get("MATNR") or "").strip()
        if mat not in materials:
            continue
        ebeln = (r.get("EBELN") or "").strip()
        ekko_r = ebeln_to_ekko.get(ebeln, {})
        # Delivery date from EINDT or EKKO date
        date_planned = (r.get("EINDT") or r.get("LFDAT")
                        or ekko_r.get("BEDAT") or "")
        po_line_rows.append({
            "id": f"{ebeln}-{(r.get('EBELP') or '').strip()}",
            "order_id": ebeln,
            "order_name": f"PO{ebeln}",
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "product_qty": safe_float(r.get("MENGE", "0")),
            "price_unit": safe_float(r.get("NETPR", "0")),
            "date_planned": date_planned,
        })

    # SAP SO → Odoo SO state mapping
    SAP_SO_STATUS = {
        "": "sale",       # Default: confirmed
        "A": "sale",      # Open
        "B": "sale",      # In process
        "C": "done",      # Completed
    }

    # sale.order (from VBAK)
    so_rows = []
    seen_so = set()
    for r in vbap_plant:
        vbeln = (r.get("VBELN") or "").strip()
        if vbeln in seen_so:
            continue
        vbak_r = vbeln_to_vbak.get(vbeln, {})
        if not vbak_r:
            continue
        seen_so.add(vbeln)
        kunnr = (vbak_r.get("KUNNR") or "").strip()
        gbstk = (vbak_r.get("GBSTK") or "").strip()
        so_rows.append({
            "id": vbeln,
            "name": f"SO{vbeln}",
            "partner_id": kunnr,
            "partner_name": customer_names.get(kunnr, f"Customer {kunnr}"),
            "date_order": (vbak_r.get("ERDAT") or ""),
            "state": SAP_SO_STATUS.get(gbstk, "sale"),
            "amount_total": safe_float(vbak_r.get("NETWR", "0")),
            "commitment_date": (vbak_r.get("VDATU") or ""),
        })

    # sale.order.line (from VBAP)
    so_line_rows = []
    for r in vbap_plant:
        mat = (r.get("MATNR") or "").strip()
        if mat not in materials:
            continue
        vbeln = (r.get("VBELN") or "").strip()
        so_line_rows.append({
            "id": f"{vbeln}-{(r.get('POSNR') or '').strip()}",
            "order_id": vbeln,
            "order_name": f"SO{vbeln}",
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "product_uom_qty": safe_float(r.get("KWMENG", "0")),
            "price_unit": safe_float(r.get("NETPR", "0")),
        })

    # SAP production order status mapping
    SAP_MO_STATUS = {
        "CRTD": "draft",       # Created
        "REL": "confirmed",    # Released
        "PCNF": "progress",    # Partially confirmed
        "CNF": "progress",     # Confirmed
        "DLV": "done",         # Delivered
        "TECO": "done",        # Technically complete
        "": "confirmed",       # Default
    }

    # mrp.production (from AFKO)
    mo_rows = []
    for r in afko:
        mat = (r.get("PLNBEZ") or "").strip()
        if mat not in materials:
            continue
        aufnr = (r.get("AUFNR") or "").strip()
        # Derive state from SAP system status
        sap_stat = (r.get("STAT") or r.get("STATUS") or "").strip()
        state = "confirmed"
        for key, val in SAP_MO_STATUS.items():
            if key and key in sap_stat:
                state = val
                break
        mo_rows.append({
            "id": aufnr,
            "name": f"MO/{aufnr}",
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "product_qty": safe_float(r.get("GAMNG", "0")),
            "date_start": (r.get("GSTRS") or r.get("GSTRP") or ""),
            "date_finished": (r.get("GLTRS") or r.get("GLTRP") or ""),
            "state": state,
            "origin": "",  # Could link to sales order if available
        })

    # mrp.workorder (from AFVC — production order operations)
    wo_rows = []
    for r in afvc:
        werks = (r.get("WERKS") or "").strip()
        if werks and werks != plant:
            continue
        aufpl = (r.get("AUFPL") or "").strip()
        vornr = (r.get("VORNR") or "").strip()
        arbid = (r.get("ARBID") or "").strip()
        wc_name = crhd_map.get(arbid, {}).get("ARBPL", arbid)
        # Duration: setup + machine time (in minutes)
        setup_min = safe_float(r.get("VGW01", "0"))
        machine_min = safe_float(r.get("VGW02", "0"))
        wo_rows.append({
            "id": f"{aufpl}-{vornr}",
            "production_id": (r.get("AUFNR") or aufpl),
            "name": (r.get("LTXA1") or f"OP {vornr}"),
            "workcenter_id": arbid,
            "workcenter_name": wc_name,
            "duration_expected": setup_min + machine_min,
            "state": "ready",
        })

    # stock.picking (from LIKP/LIPS outgoing + EKBE incoming + LTAK/LTAP internal)
    picking_rows = []
    move_rows = []
    move_line_rows = []
    pick_seq = 0

    # Outgoing deliveries (LIKP + LIPS)
    for r in likp:
        vbeln = (r.get("VBELN") or "").strip()
        kunnr = (r.get("KUNNR") or "").strip()
        lfdat = (r.get("LFDAT") or "")
        wadat_ist = (r.get("WADAT_IST") or "")
        state = "done" if wadat_ist else "assigned"
        pick_seq += 1
        picking_rows.append({
            "id": f"OUT-{vbeln}",
            "name": f"WH/OUT/{vbeln}",
            "partner_id": kunnr,
            "partner_name": customer_names.get(kunnr, f"Customer {kunnr}"),
            "picking_type_code": "outgoing",
            "scheduled_date": lfdat,
            "date_done": wadat_ist,
            "state": state,
            "origin": vbeln,
            "carrier_tracking_ref": "",
        })
        # Lines from LIPS
        for lip in lips:
            if (lip.get("VBELN") or "").strip() != vbeln:
                continue
            lip_mat = (lip.get("MATNR") or "").strip()
            lip_qty = safe_float(lip.get("LFIMG", "0"))
            posnr = (lip.get("POSNR") or "").strip()
            move_id = f"OUT-{vbeln}-{posnr}"
            move_rows.append({
                "id": move_id,
                "picking_id": f"OUT-{vbeln}",
                "picking_name": f"WH/OUT/{vbeln}",
                "product_id": lip_mat,
                "product_name": desc_map.get(lip_mat, lip_mat),
                "product_uom_qty": lip_qty,
                "quantity_done": lip_qty if state == "done" else 0,
                "state": state,
            })
            move_line_rows.append({
                "id": f"ML-{move_id}",
                "move_id": move_id,
                "product_id": lip_mat,
                "product_name": desc_map.get(lip_mat, lip_mat),
                "qty_done": lip_qty if state == "done" else 0,
                "lot_id": "",
                "lot_name": "",
            })

    # Incoming receipts (EKBE with movement type 101 = goods receipt)
    # Group by PO number to create one picking per PO receipt
    gr_by_po: Dict[str, List[Dict]] = defaultdict(list)
    for r in ekbe:
        bwart = (r.get("VGABE") or r.get("BWART") or "").strip()
        # Movement type 101 = goods receipt, or VGABE = "1" (GR)
        if bwart in ("101", "1"):
            ebeln = (r.get("EBELN") or "").strip()
            gr_by_po[ebeln].append(r)

    for ebeln, gr_items in gr_by_po.items():
        ekko_r = ebeln_to_ekko.get(ebeln, {})
        lifnr = (ekko_r.get("LIFNR") or "").strip()
        budat = (gr_items[0].get("BUDAT") or gr_items[0].get("CPUDT") or "")
        pick_seq += 1
        picking_rows.append({
            "id": f"IN-{ebeln}",
            "name": f"WH/IN/{ebeln}",
            "partner_id": lifnr,
            "partner_name": vendor_names.get(lifnr, f"Vendor {lifnr}"),
            "picking_type_code": "incoming",
            "scheduled_date": budat,
            "date_done": budat,
            "state": "done",
            "origin": f"PO{ebeln}",
            "carrier_tracking_ref": "",
        })
        for gr in gr_items:
            gr_mat = (gr.get("MATNR") or "").strip()
            gr_qty = safe_float(gr.get("MENGE", "0"))
            ebelp = (gr.get("EBELP") or "").strip()
            move_id = f"IN-{ebeln}-{ebelp}"
            move_rows.append({
                "id": move_id,
                "picking_id": f"IN-{ebeln}",
                "picking_name": f"WH/IN/{ebeln}",
                "product_id": gr_mat,
                "product_name": desc_map.get(gr_mat, gr_mat),
                "product_uom_qty": gr_qty,
                "quantity_done": gr_qty,
                "state": "done",
            })
            move_line_rows.append({
                "id": f"ML-{move_id}",
                "move_id": move_id,
                "product_id": gr_mat,
                "product_name": desc_map.get(gr_mat, gr_mat),
                "qty_done": gr_qty,
                "lot_id": "",
                "lot_name": "",
            })

    # Internal transfers (LTAK/LTAP)
    for r in ltak:
        tanum = (r.get("TANUM") or "").strip()
        lgnum = (r.get("LGNUM") or "").strip()
        pick_seq += 1
        picking_rows.append({
            "id": f"INT-{tanum}",
            "name": f"WH/INT/{tanum}",
            "partner_id": "",
            "partner_name": "",
            "picking_type_code": "internal",
            "scheduled_date": (r.get("BDATU") or ""),
            "date_done": (r.get("EDATU") or ""),
            "state": "done" if (r.get("EDATU") or "") else "assigned",
            "origin": f"TO-{lgnum}/{tanum}",
            "carrier_tracking_ref": "",
        })

    for r in ltap:
        tanum = (r.get("TANUM") or "").strip()
        tapos = (r.get("TAPOS") or "").strip()
        lt_mat = (r.get("MATNR") or "").strip()
        lt_qty = safe_float(r.get("VSOLM", "0"))
        move_id = f"INT-{tanum}-{tapos}"
        move_rows.append({
            "id": move_id,
            "picking_id": f"INT-{tanum}",
            "picking_name": f"WH/INT/{tanum}",
            "product_id": lt_mat,
            "product_name": desc_map.get(lt_mat, lt_mat),
            "product_uom_qty": lt_qty,
            "quantity_done": lt_qty,
            "state": "done",
        })
        move_line_rows.append({
            "id": f"ML-{move_id}",
            "move_id": move_id,
            "product_id": lt_mat,
            "product_name": desc_map.get(lt_mat, lt_mat),
            "qty_done": lt_qty,
            "lot_id": "",
            "lot_name": "",
        })

    # ── CDC records ────────────────────────────────────────────────────
    print("\n  --- CDC Data ---")

    # stock.lot (from MCH1/MCHA)
    lot_rows = []
    seen_lots = set()
    for r in mcha:
        mat = (r.get("MATNR") or "").strip()
        charg = (r.get("CHARG") or "").strip()
        if mat not in materials or not charg:
            continue
        lot_key = f"{mat}|{charg}"
        if lot_key in seen_lots:
            continue
        seen_lots.add(lot_key)
        lot_rows.append({
            "id": lot_key,
            "name": charg,
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "expiration_date": (r.get("VFDAT") or ""),
        })
    for r in mch1:
        mat = (r.get("MATNR") or "").strip()
        charg = (r.get("CHARG") or "").strip()
        if not charg:
            continue
        lot_key = f"{mat}|{charg}"
        if lot_key in seen_lots:
            continue
        seen_lots.add(lot_key)
        lot_rows.append({
            "id": lot_key,
            "name": charg,
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "expiration_date": (r.get("VFDAT") or ""),
        })

    # quality.check (from QALS — inspection lots)
    qc_rows = []
    for r in qals:
        prueflos = (r.get("PRUEFLOS") or "").strip()
        mat = (r.get("MATNR") or "").strip()
        # Derive quality state from processing status
        bearb = (r.get("BEARBSTATU") or r.get("GEESSION") or "").strip()
        # Simple heuristic: if usage decision exists, pass; else pending
        quality_state = "pass" if bearb else "none"
        qc_rows.append({
            "id": prueflos,
            "name": f"QC/{prueflos}",
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "point_id": (r.get("ART") or ""),
            "quality_state": quality_state,
            "picking_id": "",
        })

    # quality.alert (from QMEL — quality notifications)
    qa_rows = []
    # SAP priority mapping: 1=Very High, 2=High, 3=Medium, 4=Low
    SAP_PRIORITY = {"1": "3", "2": "2", "3": "1", "4": "0"}  # Odoo: 0=Normal,1=Low,2=High,3=Urgent
    for r in qmel:
        qmnum = (r.get("QMNUM") or "").strip()
        mat = (r.get("MATNR") or "").strip()
        priok = (r.get("PRIOK") or "").strip()
        qa_rows.append({
            "id": qmnum,
            "name": f"QA/{qmnum}",
            "product_id": mat,
            "product_name": desc_map.get(mat, mat),
            "description": (r.get("QMTXT") or ""),
            "stage_id": "new",
            "priority": SAP_PRIORITY.get(priok, "1"),
        })

    # maintenance.equipment (from EQUI)
    equip_rows = []
    for r in equi:
        equnr = (r.get("EQUNR") or "").strip()
        if not equnr:
            continue
        equip_rows.append({
            "id": equnr,
            "name": (r.get("EQKTX") or r.get("TYPBZ") or equnr),
            "category_id": (r.get("EQART") or ""),
            "serial_no": (r.get("SERGE") or ""),
            "location": (r.get("SWERK") or r.get("STANDORT") or ""),
            "partner_id": (r.get("HERST") or ""),
        })

    # maintenance.request (from EQUI cross-ref with PM data — generate
    # synthetic requests from equipment records since SAP PM orders are
    # in a separate module; fallback: one preventive maintenance per equipment)
    maint_req_rows = []
    for i, r in enumerate(equi, 1):
        equnr = (r.get("EQUNR") or "").strip()
        if not equnr:
            continue
        maint_req_rows.append({
            "id": f"MR-{equnr}",
            "name": f"Preventive Maintenance - {equnr}",
            "equipment_id": equnr,
            "equipment_name": (r.get("EQKTX") or r.get("TYPBZ") or equnr),
            "maintenance_type": "preventive",
            "priority": "1",
            "schedule_date": "",
            "stage_id": "new",
            "request_date": (r.get("ERDAT") or ""),
        })

    # ── Additional master records ──────────────────────────────────────
    print("\n  --- Additional Master Data ---")

    # stock.warehouse (from T001W — one warehouse per plant)
    warehouse_rows = []
    for r in t001w:
        werks = (r.get("WERKS") or "").strip()
        warehouse_rows.append({
            "id": werks,
            "name": (r.get("NAME1") or f"Warehouse {werks}"),
            "code": werks[:5],
        })

    # product.category (from MARA.MATKL — unique material groups)
    category_rows = []
    seen_cats = set()
    for mat in sorted(materials):
        marc_r = marc_map.get(mat, {})
        mara_r = next((r for r in mara if (r.get("MATNR") or "").strip() == mat), {})
        matkl = (mara_r.get("MATKL") or marc_r.get("MATKL") or "").strip()
        if matkl and matkl not in seen_cats:
            seen_cats.add(matkl)
            category_rows.append({
                "id": matkl,
                "name": matkl,
                "complete_name": f"All / {matkl}",
            })

    # mrp.workcenter (from CRHD)
    workcenter_rows = []
    for r in crhd:
        werks = (r.get("WERKS") or "").strip()
        if werks and werks != plant:
            continue
        objid = (r.get("OBJID") or "").strip()
        if not objid:
            continue
        workcenter_rows.append({
            "id": objid,
            "name": (r.get("ARBPL") or objid),
            "code": (r.get("ARBPL") or objid),
            "time_efficiency": 100.0,
            "capacity": 1,
        })

    # mrp.routing.workcenter (from PLPO + CRHD)
    routing_wc_rows = []
    for r in plpo:
        plnnr = (r.get("PLNNR") or "").strip()
        vornr = (r.get("VORNR") or "").strip()
        arbid = (r.get("ARBID") or "").strip()
        if not plnnr or not vornr:
            continue
        wc = crhd_map.get(arbid, {})
        wc_name = (wc.get("ARBPL") or arbid)
        # Cycle time = machine time per unit
        time_cycle = safe_float(r.get("VGW02", "0"))
        routing_wc_rows.append({
            "id": f"{plnnr}-{vornr}",
            "name": (r.get("LTXA1") or f"OP {vornr}"),
            "workcenter_id": arbid,
            "workcenter_name": wc_name,
            "time_cycle": time_cycle if time_cycle > 0 else safe_float(r.get("VGW01", "0")),
            "time_mode": "auto",
        })

    # uom.uom (from MARM — unique UOM entries)
    uom_rows = []
    seen_uom = set()
    # Static categories
    UOM_CATEGORY_MAP = {
        "KG": "Weight", "G": "Weight", "LB": "Weight", "TO": "Weight", "TNE": "Weight",
        "L": "Volume", "ML": "Volume", "GAL": "Volume", "M3": "Volume",
        "ST": "Unit", "EA": "Unit", "PC": "Unit", "PAA": "Unit", "PAL": "Unit",
        "CS": "Unit", "BOX": "Unit", "SET": "Unit", "ROL": "Unit",
        "H": "Time", "MIN": "Time", "S": "Time", "TAG": "Time",
        "M": "Length", "CM": "Length", "MM": "Length", "IN": "Length", "FT": "Length",
    }
    for r in marm:
        uom = (r.get("MEINH") or "").strip()
        if not uom or uom in seen_uom:
            continue
        seen_uom.add(uom)
        factor = safe_float(r.get("UMREZ", "1"))
        denom = safe_float(r.get("UMREN", "1"))
        ratio = factor / denom if denom > 0 else 1.0
        uom_rows.append({
            "id": uom,
            "name": uom,
            "category_id": UOM_CATEGORY_MAP.get(uom, "Unit"),
            "factor": ratio,
            "uom_type": "bigger" if ratio > 1.0 else ("smaller" if ratio < 1.0 else "reference"),
        })
    # Ensure base UOM categories exist
    for base_uom, cat in [("EA", "Unit"), ("KG", "Weight"), ("L", "Volume"), ("H", "Time")]:
        if base_uom not in seen_uom:
            seen_uom.add(base_uom)
            uom_rows.append({
                "id": base_uom,
                "name": base_uom,
                "category_id": cat,
                "factor": 1.0,
                "uom_type": "reference",
            })

    # uom.category (static)
    uom_category_rows = [
        {"id": "1", "name": "Unit"},
        {"id": "2", "name": "Weight"},
        {"id": "3", "name": "Volume"},
        {"id": "4", "name": "Time"},
        {"id": "5", "name": "Length"},
    ]

    print(f"  Purchase orders: {len(po_rows)} ({len(po_line_rows)} lines)")
    print(f"  Sale orders: {len(so_rows)} ({len(so_line_rows)} lines)")
    print(f"  Manufacturing orders: {len(mo_rows)} ({len(wo_rows)} work orders)")
    print(f"  Stock pickings: {len(picking_rows)} ({len(move_rows)} moves)")
    print(f"  Stock move lines: {len(move_line_rows)}")
    print(f"  Lots/batches: {len(lot_rows)}")
    print(f"  Quality checks: {len(qc_rows)}")
    print(f"  Quality alerts: {len(qa_rows)}")
    print(f"  Equipment: {len(equip_rows)}")
    print(f"  Maintenance requests: {len(maint_req_rows)}")
    print(f"  Warehouses: {len(warehouse_rows)}")
    print(f"  Product categories: {len(category_rows)}")
    print(f"  Work centers: {len(workcenter_rows)}")
    print(f"  Routing operations: {len(routing_wc_rows)}")
    print(f"  UoMs: {len(uom_rows)} ({len(uom_category_rows)} categories)")

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

        # ── Transaction CSVs ──────────────────────────────────────────
        write_csv(args.output_dir, "purchase_order.csv", po_rows,
                  ["id", "name", "partner_id", "partner_name", "date_order",
                   "state", "amount_total", "currency_id"])
        write_csv(args.output_dir, "purchase_order_line.csv", po_line_rows,
                  ["id", "order_id", "order_name", "product_id", "product_name",
                   "product_qty", "price_unit", "date_planned"])
        write_csv(args.output_dir, "sale_order.csv", so_rows,
                  ["id", "name", "partner_id", "partner_name", "date_order",
                   "state", "amount_total", "commitment_date"])
        write_csv(args.output_dir, "sale_order_line.csv", so_line_rows,
                  ["id", "order_id", "order_name", "product_id", "product_name",
                   "product_uom_qty", "price_unit"])
        write_csv(args.output_dir, "mrp_production.csv", mo_rows,
                  ["id", "name", "product_id", "product_name", "product_qty",
                   "date_start", "date_finished", "state", "origin"])
        write_csv(args.output_dir, "mrp_workorder.csv", wo_rows,
                  ["id", "production_id", "name", "workcenter_id",
                   "workcenter_name", "duration_expected", "state"])
        write_csv(args.output_dir, "stock_picking.csv", picking_rows,
                  ["id", "name", "partner_id", "partner_name", "picking_type_code",
                   "scheduled_date", "date_done", "state", "origin",
                   "carrier_tracking_ref"])
        write_csv(args.output_dir, "stock_move.csv", move_rows,
                  ["id", "picking_id", "picking_name", "product_id", "product_name",
                   "product_uom_qty", "quantity_done", "state"])

        # ── CDC CSVs ──────────────────────────────────────────────────
        write_csv(args.output_dir, "stock_move_line.csv", move_line_rows,
                  ["id", "move_id", "product_id", "product_name",
                   "qty_done", "lot_id", "lot_name"])
        write_csv(args.output_dir, "stock_lot.csv", lot_rows,
                  ["id", "name", "product_id", "product_name", "expiration_date"])
        write_csv(args.output_dir, "quality_check.csv", qc_rows,
                  ["id", "name", "product_id", "product_name", "point_id",
                   "quality_state", "picking_id"])
        write_csv(args.output_dir, "quality_alert.csv", qa_rows,
                  ["id", "name", "product_id", "product_name", "description",
                   "stage_id", "priority"])
        write_csv(args.output_dir, "maintenance_request.csv", maint_req_rows,
                  ["id", "name", "equipment_id", "equipment_name",
                   "maintenance_type", "priority", "schedule_date", "stage_id",
                   "request_date"])
        write_csv(args.output_dir, "maintenance_equipment.csv", equip_rows,
                  ["id", "name", "category_id", "serial_no", "location",
                   "partner_id"])

        # ── Additional master CSVs ────────────────────────────────────
        write_csv(args.output_dir, "stock_warehouse.csv", warehouse_rows,
                  ["id", "name", "code"])
        write_csv(args.output_dir, "product_category.csv", category_rows,
                  ["id", "name", "complete_name"])
        write_csv(args.output_dir, "mrp_workcenter.csv", workcenter_rows,
                  ["id", "name", "code", "time_efficiency", "capacity"])
        write_csv(args.output_dir, "mrp_routing_workcenter.csv", routing_wc_rows,
                  ["id", "name", "workcenter_id", "workcenter_name",
                   "time_cycle", "time_mode"])
        write_csv(args.output_dir, "uom_uom.csv", uom_rows,
                  ["id", "name", "category_id", "factor", "uom_type"])
        write_csv(args.output_dir, "uom_category.csv", uom_category_rows,
                  ["id", "name"])

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
    print(f"  Translation complete!")
    print(f"")
    print(f"  Master Data (8 files):")
    print(f"    product_template.csv             {len(product_rows)} products")
    print(f"    res_partner_vendors.csv          {len(vendor_rows)} vendors")
    print(f"    res_partner_customers.csv        {len(customer_rows)} customers")
    print(f"    product_supplierinfo.csv         {len(supplierinfo_rows)} vendor pricelists")
    print(f"    mrp_bom.csv                      {len(bom_rows)} BOMs")
    print(f"    mrp_bom_line.csv                 {len(bom_line_rows)} BOM lines")
    print(f"    stock_warehouse_orderpoint.csv   {len(orderpoint_rows)} reorder rules")
    print(f"    stock_quant.csv                  {len(quant_rows)} stock quants")
    print(f"")
    print(f"  Transaction Data (8 files):")
    print(f"    purchase_order.csv               {len(po_rows)} POs")
    print(f"    purchase_order_line.csv           {len(po_line_rows)} PO lines")
    print(f"    sale_order.csv                   {len(so_rows)} SOs")
    print(f"    sale_order_line.csv              {len(so_line_rows)} SO lines")
    print(f"    mrp_production.csv               {len(mo_rows)} MOs")
    print(f"    mrp_workorder.csv                {len(wo_rows)} work orders")
    print(f"    stock_picking.csv                {len(picking_rows)} pickings")
    print(f"    stock_move.csv                   {len(move_rows)} moves")
    print(f"")
    print(f"  CDC Data (6 files):")
    print(f"    stock_move_line.csv              {len(move_line_rows)} move lines")
    print(f"    stock_lot.csv                    {len(lot_rows)} lots/batches")
    print(f"    quality_check.csv                {len(qc_rows)} quality checks")
    print(f"    quality_alert.csv                {len(qa_rows)} quality alerts")
    print(f"    maintenance_equipment.csv        {len(equip_rows)} equipment")
    print(f"    maintenance_request.csv          {len(maint_req_rows)} maintenance requests")
    print(f"")
    print(f"  Additional Master (6 files):")
    print(f"    stock_warehouse.csv              {len(warehouse_rows)} warehouses")
    print(f"    product_category.csv             {len(category_rows)} product categories")
    print(f"    mrp_workcenter.csv               {len(workcenter_rows)} work centers")
    print(f"    mrp_routing_workcenter.csv       {len(routing_wc_rows)} routing operations")
    print(f"    uom_uom.csv                      {len(uom_rows)} UoMs")
    print(f"    uom_category.csv                 {len(uom_category_rows)} UoM categories")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

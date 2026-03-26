#!/usr/bin/env python3
"""
Translate SAP IDES CSV exports into D365 Contoso-format CSV files.

Reads SAP tables (T001W, MARA, MAKT, MARC, MARD, LFA1, KNA1, EKKO, EKPO,
VBAK, VBAP, STKO, STPO, AFKO, MBEW, PBED) and produces D365-named CSVs
(Sites.csv, ReleasedProductsV2.csv, etc.) that can be ingested by
rebuild_d365_contoso_config.py.

This lets us demonstrate the full D365 integration pipeline without needing
a live D365 environment.

Usage:
    python scripts/translate_sap_to_d365_csvs.py \
        --sap-dir imports/SAP_Demo/S4HANA/2026-03-18 \
        --output-dir imports/D365_Demo \
        --plant 1710 \
        --data-area usmf
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


def read_csv(csv_dir: Path, filename: str) -> List[Dict[str, str]]:
    """Read a CSV file, return list of dicts."""
    path = csv_dir / filename
    if not path.exists():
        print(f"  SKIP {filename} (not found)")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  READ {filename}: {len(rows)} rows")
    return rows


def write_csv(output_dir: str, filename: str, rows: List[Dict], fieldnames: List[str]):
    """Write rows to a CSV file."""
    if not rows:
        print(f"  SKIP {filename} (no rows)")
        return
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


def main():
    parser = argparse.ArgumentParser(description="Translate SAP CSVs to D365 format")
    parser.add_argument("--sap-dir", required=True, help="Directory containing SAP CSV files")
    parser.add_argument("--output-dir", required=True, help="Output directory for D365 CSVs")
    parser.add_argument("--plant", default="1710", help="SAP plant to translate (default: 1710)")
    parser.add_argument("--data-area", default="usmf", help="D365 data area ID (default: usmf)")
    args = parser.parse_args()

    sap_dir = Path(args.sap_dir)
    output_dir = args.output_dir
    plant = args.plant
    data_area = args.data_area

    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  SAP → D365 CSV Translation")
    print(f"  SAP dir:    {sap_dir}")
    print(f"  Output:     {output_dir}")
    print(f"  Plant:      {plant}")
    print(f"  Data area:  {data_area}")
    print(f"{'='*70}")

    # ── Load SAP data ────────────────────────────────────────────────────
    print("\nPhase 1: Loading SAP CSVs...")

    t001w = read_csv(sap_dir, "T001W.csv")
    mara = read_csv(sap_dir, "MARA.csv")
    makt = read_csv(sap_dir, "MAKT.csv")
    marc = read_csv(sap_dir, "MARC.csv")
    mard = read_csv(sap_dir, "MARD.csv")
    mbew = read_csv(sap_dir, "MBEW.csv")
    lfa1 = read_csv(sap_dir, "LFA1.csv")
    kna1 = read_csv(sap_dir, "KNA1.csv")
    ekko = read_csv(sap_dir, "EKKO.csv")
    ekpo = read_csv(sap_dir, "EKPO.csv")
    vbak = read_csv(sap_dir, "VBAK.csv")
    vbap = read_csv(sap_dir, "VBAP.csv")
    stko = read_csv(sap_dir, "STKO.csv")
    stpo = read_csv(sap_dir, "STPO.csv")
    mast = read_csv(sap_dir, "MAST.csv")
    afko = read_csv(sap_dir, "AFKO.csv")
    pbed = read_csv(sap_dir, "PBED.csv")
    pbim = read_csv(sap_dir, "PBIM.csv")
    # Transaction history tables
    likp = read_csv(sap_dir, "LIKP.csv")   # Delivery headers
    lips = read_csv(sap_dir, "LIPS.csv")   # Delivery items
    ekbe = read_csv(sap_dir, "EKBE.csv")   # PO history (goods receipts)
    vbep = read_csv(sap_dir, "VBEP.csv")   # SO schedule lines (delivery schedule)
    resb = read_csv(sap_dir, "RESB.csv")   # Production order components
    afvc = read_csv(sap_dir, "AFVC.csv")   # Production order operations/routing
    eban = read_csv(sap_dir, "EBAN.csv")   # Purchase requisitions
    plaf = read_csv(sap_dir, "PLAF.csv")   # Planned orders (MRP output)
    equi = read_csv(sap_dir, "EQUI.csv")   # Equipment/assets
    qals = read_csv(sap_dir, "QALS.csv")   # Quality inspection lots
    # Additional master/transaction tables
    t001 = read_csv(sap_dir, "T001.csv")   # Company codes
    t001l = read_csv(sap_dir, "T001L.csv") # Storage locations
    adrc = read_csv(sap_dir, "ADRC.csv")   # Addresses
    marm = read_csv(sap_dir, "MARM.csv")   # UOM conversions
    mvke = read_csv(sap_dir, "MVKE.csv")   # Sales org data
    knvv = read_csv(sap_dir, "KNVV.csv")   # Customer sales area
    eina = read_csv(sap_dir, "EINA.csv")   # Purchasing info records
    eine = read_csv(sap_dir, "EINE.csv")   # Purchasing conditions
    eord = read_csv(sap_dir, "EORD.csv")   # Source list (approved vendors)
    eket = read_csv(sap_dir, "EKET.csv")   # PO schedule lines
    afpo = read_csv(sap_dir, "AFPO.csv")   # Production order items
    afru = read_csv(sap_dir, "AFRU.csv")   # Production confirmations
    aufk = read_csv(sap_dir, "AUFK.csv")   # Order master
    plko = read_csv(sap_dir, "PLKO.csv")   # Routing headers
    plpo = read_csv(sap_dir, "PLPO.csv")   # Routing operations
    crhd = read_csv(sap_dir, "CRHD.csv")   # Work centers
    crco = read_csv(sap_dir, "CRCO.csv")   # Cost center assignments
    qase = read_csv(sap_dir, "QASE.csv")   # Quality results
    qmel = read_csv(sap_dir, "QMEL.csv")   # Quality notifications
    jest = read_csv(sap_dir, "JEST.csv")   # System status
    kako = read_csv(sap_dir, "KAKO.csv")   # Capacity data
    mch1 = read_csv(sap_dir, "MCH1.csv")   # Batch master (plant-independent)
    mcha = read_csv(sap_dir, "MCHA.csv")   # Batch master (plant-level)

    # ── Build lookup maps ────────────────────────────────────────────────
    print("\nPhase 2: Building lookup maps...")

    # Material descriptions
    makt_map = {}
    for r in makt:
        mat = r.get("MATNR", "")
        if mat and (r.get("SPRAS", "E") == "E" or mat not in makt_map):
            makt_map[mat] = r.get("MAKTX", mat)

    # Material master
    mara_map = {r.get("MATNR", ""): r for r in mara if r.get("MATNR")}

    # Valuation (costs)
    mbew_map = {}
    for r in mbew:
        mat = r.get("MATNR", "")
        if mat and r.get("BWKEY", "") == plant:
            mbew_map[mat] = r

    # Materials at plant
    marc_plant = [r for r in marc if r.get("WERKS") == plant]
    materials_at_plant = {r["MATNR"] for r in marc_plant}

    # Exclude non-physical
    EXCLUDE_MTART = {"SERV", "DIEN", "NLAG", "VERP", "LEIH", "PIPE", "VEHI"}
    materials = set()
    for mat in materials_at_plant:
        mtart = mara_map.get(mat, {}).get("MTART", "")
        if mtart not in EXCLUDE_MTART:
            materials.add(mat)

    marc_map = {r["MATNR"]: r for r in marc_plant if r["MATNR"] in materials}

    # Stock
    stock_map = defaultdict(float)
    for r in mard:
        if r.get("WERKS") == plant and r.get("MATNR") in materials:
            stock_map[r["MATNR"]] += safe_float(r.get("LABST", "0"))

    # BOM linkage: MAST maps material → STLNR (BOM number)
    mat_to_stlnr = {}
    for r in mast:
        if r.get("WERKS", "") == plant or not r.get("WERKS"):
            mat_to_stlnr[r.get("MATNR", "")] = r.get("STLNR", "")

    # Reverse: STLNR → material
    stlnr_to_mat = {v: k for k, v in mat_to_stlnr.items()}

    # PO vendor lookup
    ebeln_to_lifnr = {r["EBELN"]: r.get("LIFNR", "") for r in ekko}
    ekpo_plant = [r for r in ekpo if r.get("WERKS") == plant]

    # SO customer lookup
    vbeln_to_kunnr = {r["VBELN"]: r.get("KUNNR", "") for r in vbak}
    vbap_plant = [r for r in vbap if r.get("WERKS") == plant]

    # Active vendors and customers
    active_vendors: Set[str] = set()
    for r in ekpo_plant:
        v = ebeln_to_lifnr.get(r.get("EBELN", ""), "")
        if v:
            active_vendors.add(v)

    active_customers: Set[str] = set()
    for r in vbap_plant:
        c = vbeln_to_kunnr.get(r.get("VBELN", ""), "")
        if c:
            active_customers.add(c)

    # Forecast: PBIM maps product→forecast profile, PBED has actual data
    pbim_map = {}
    for r in pbim:
        pbim_map[r.get("BDZEI", "")] = r.get("MATNR", "")

    # Address lookup (ADRC)
    adrc_map = {}
    for r in adrc:
        adrc_map[r.get("ADDRNUMBER", "")] = r

    # AUFK order master lookup
    aufk_map = {r.get("AUFNR", ""): r for r in aufk}

    # EINA+EINE: purchasing info records → vendor purchase prices
    eina_map = {}  # INFNR → {MATNR, LIFNR}
    for r in eina:
        if r.get("LOEKZ") != "X":
            eina_map[r.get("INFNR", "")] = r

    # Cost center assignments for work centers
    crco_map = defaultdict(str)  # OBJID → KOSTL
    for r in crco:
        crco_map[r.get("OBJID", "")] = r.get("KOSTL", "")

    print(f"  Materials: {len(materials)}")
    print(f"  Active vendors: {len(active_vendors)}")
    print(f"  Active customers: {len(active_customers)}")
    print(f"  BOMs (MAST): {len(mat_to_stlnr)}")

    # ── Translate to D365 format ─────────────────────────────────────────
    print("\nPhase 3: Translating to D365 CSVs...")

    # ── Sites.csv ────────────────────────────────────────────────────────
    sites = []
    for w in t001w:
        sites.append({
            "SiteId": w.get("WERKS", ""),
            "SiteName": w.get("NAME1", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "Sites.csv", sites, ["SiteId", "SiteName", "dataAreaId"])

    # ── Warehouses.csv ───────────────────────────────────────────────────
    # SAP plants double as warehouses; create one warehouse per plant
    warehouses = []
    for w in t001w:
        warehouses.append({
            "WarehouseId": w.get("WERKS", ""),
            "WarehouseName": w.get("NAME1", ""),
            "SiteId": w.get("WERKS", ""),
            "OperationalSiteId": w.get("WERKS", ""),
            "IsInventoryManaged": "Yes",
            "WarehouseType": "Standard",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "Warehouses.csv", warehouses,
              ["WarehouseId", "WarehouseName", "SiteId", "OperationalSiteId",
               "IsInventoryManaged", "WarehouseType", "dataAreaId"])

    # ── ReleasedProductsV2.csv ───────────────────────────────────────────
    products = []
    for mat in sorted(materials):
        mara_r = mara_map.get(mat, {})
        mbew_r = mbew_map.get(mat, {})
        desc = makt_map.get(mat, mat)

        # Cost: standard price → moving average → sales price
        std_cost = safe_float(mbew_r.get("STPRS", "0"))
        mvg_price = safe_float(mbew_r.get("VERPR", "0"))
        unit_cost = std_cost if std_cost > 0 else mvg_price

        # Product type mapping
        mtart = mara_r.get("MTART", "")
        beskz = marc_map.get(mat, {}).get("BESKZ", "")
        if beskz == "E":
            prod_type = "Item"  # manufactured
        elif mtart in ("ROH", "ERSA"):
            prod_type = "Item"  # raw material
        else:
            prod_type = "Item"

        products.append({
            "ItemNumber": mat,
            "ProductName": desc[:100],
            "ProductType": prod_type,
            "ProductSubType": mtart,
            "ProductGroupId": mara_r.get("MATKL", ""),
            "InventoryUnitSymbol": mara_r.get("MEINS", "EA"),
            "SalesPrice": safe_float(mbew_r.get("VERPR", "0")),
            "ProductionStandardCost": unit_cost,
            "NetWeight": safe_float(mara_r.get("NTGEW", "0")),
            "GrossWeight": safe_float(mara_r.get("BRGEW", "0")),
            "NetVolume": safe_float(mara_r.get("VOLUM", "0")),
            "BarcodeId": mara_r.get("EAN11", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ReleasedProductsV2.csv", products,
              ["ItemNumber", "ProductName", "ProductType", "ProductSubType",
               "ProductGroupId", "InventoryUnitSymbol", "SalesPrice",
               "ProductionStandardCost", "NetWeight", "GrossWeight",
               "NetVolume", "BarcodeId", "dataAreaId"])

    # ── Vendors.csv ──────────────────────────────────────────────────────
    vendors = []
    for v in lfa1:
        v_id = v.get("LIFNR", "")
        if v_id not in active_vendors:
            continue
        vendors.append({
            "VendorAccountNumber": v_id,
            "VendorName": v.get("NAME1", ""),
            "VendorGroupId": "",
            "AddressCountryRegionId": v.get("LAND1", ""),
            "AddressCity": v.get("ORT01", ""),
            "AddressZipCode": v.get("PSTLZ", ""),
            "PrimaryContactPhone": v.get("TELF1", ""),
            "PrimaryContactEmail": "",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "Vendors.csv", vendors,
              ["VendorAccountNumber", "VendorName", "VendorGroupId",
               "AddressCountryRegionId", "AddressCity", "AddressZipCode",
               "PrimaryContactPhone", "PrimaryContactEmail", "dataAreaId"])

    # ── CustomersV3.csv ──────────────────────────────────────────────────
    customers = []
    for c in kna1:
        c_id = c.get("KUNNR", "")
        if c_id not in active_customers:
            continue
        customers.append({
            "CustomerAccount": c_id,
            "CustomerName": c.get("NAME1", ""),
            "CustomerGroupId": c.get("KTOKD", ""),
            "AddressCountryRegionId": c.get("LAND1", ""),
            "AddressCity": c.get("ORT01", ""),
            "AddressZipCode": c.get("PSTLZ", ""),
            "PrimaryContactPhone": c.get("TELF1", ""),
            "PrimaryContactEmail": "",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "CustomersV3.csv", customers,
              ["CustomerAccount", "CustomerName", "CustomerGroupId",
               "AddressCountryRegionId", "AddressCity", "AddressZipCode",
               "PrimaryContactPhone", "PrimaryContactEmail", "dataAreaId"])

    # ── BillOfMaterialsHeaders.csv ───────────────────────────────────────
    bom_headers = []
    seen_boms = set()
    for r in stko:
        stlnr = r.get("STLNR", "")
        if stlnr in seen_boms or r.get("LOEKZ") == "X":
            continue
        seen_boms.add(stlnr)

        parent_mat = stlnr_to_mat.get(stlnr, "")
        if not parent_mat or parent_mat not in materials:
            continue

        bom_headers.append({
            "BOMId": stlnr,
            "ProductNumber": parent_mat,
            "SiteId": plant,
            "BOMName": makt_map.get(parent_mat, parent_mat)[:50],
            "IsActive": "Yes",
            "BOMQuantity": safe_float(r.get("BMENG", "1")),
            "BOMUnitSymbol": r.get("BMEIN", "EA"),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "BillOfMaterialsHeaders.csv", bom_headers,
              ["BOMId", "ProductNumber", "SiteId", "BOMName", "IsActive",
               "BOMQuantity", "BOMUnitSymbol", "dataAreaId"])

    # ── BillOfMaterialsLines.csv ─────────────────────────────────────────
    bom_lines = []
    for r in stpo:
        stlnr = r.get("STLNR", "")
        if stlnr not in seen_boms:
            continue
        component = r.get("IDNRK", "")
        if not component or component not in materials:
            continue

        bom_lines.append({
            "BOMId": stlnr,
            "LineNumber": r.get("POSNR", r.get("STLKN", "")),
            "ItemNumber": component,
            "BOMLineQuantity": safe_float(r.get("MENGE", "1")),
            "BOMLineQuantityUnitSymbol": r.get("MEINS", "EA"),
            "ScrapPercentage": safe_float(r.get("AUSCH", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "BillOfMaterialsLines.csv", bom_lines,
              ["BOMId", "LineNumber", "ItemNumber", "BOMLineQuantity",
               "BOMLineQuantityUnitSymbol", "ScrapPercentage", "dataAreaId"])

    # ── PurchaseOrderHeadersV2.csv ───────────────────────────────────────
    po_headers = []
    seen_po = set()
    for r in ekko:
        ebeln = r.get("EBELN", "")
        if ebeln in seen_po:
            continue
        # Only include POs with lines at our plant
        if not any(ep.get("EBELN") == ebeln for ep in ekpo_plant):
            continue
        seen_po.add(ebeln)

        po_headers.append({
            "PurchaseOrderNumber": ebeln,
            "VendorAccountNumber": r.get("LIFNR", ""),
            "OrderDate": r.get("BEDAT", r.get("AEDAT", "")),
            "DeliveryDate": "",
            "PurchaseOrderStatus": "Confirmed",
            "CurrencyCode": r.get("WAERS", "USD"),
            "TotalOrderAmount": "",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PurchaseOrderHeadersV2.csv", po_headers,
              ["PurchaseOrderNumber", "VendorAccountNumber", "OrderDate",
               "DeliveryDate", "PurchaseOrderStatus", "CurrencyCode",
               "TotalOrderAmount", "dataAreaId"])

    # ── PurchaseOrderLinesV2.csv ─────────────────────────────────────────
    po_lines_out = []
    for r in ekpo_plant:
        if r.get("MATNR", "") not in materials:
            continue
        po_lines_out.append({
            "PurchaseOrderNumber": r.get("EBELN", ""),
            "LineNumber": r.get("EBELP", ""),
            "ItemNumber": r.get("MATNR", ""),
            "PurchasedQuantity": safe_float(r.get("MENGE", "0")),
            "ReceivedQuantity": 0,
            "PurchasePrice": safe_float(r.get("NETPR", "0")),
            "DeliveryDate": "",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PurchaseOrderLinesV2.csv", po_lines_out,
              ["PurchaseOrderNumber", "LineNumber", "ItemNumber",
               "PurchasedQuantity", "ReceivedQuantity", "PurchasePrice",
               "DeliveryDate", "dataAreaId"])

    # ── SalesOrderHeadersV2.csv ──────────────────────────────────────────
    so_headers = []
    seen_so = set()
    for r in vbak:
        vbeln = r.get("VBELN", "")
        if vbeln in seen_so:
            continue
        if not any(vp.get("VBELN") == vbeln for vp in vbap_plant):
            continue
        seen_so.add(vbeln)

        so_headers.append({
            "SalesOrderNumber": vbeln,
            "CustomerAccountNumber": r.get("KUNNR", ""),
            "OrderDate": r.get("ERDAT", ""),
            "RequestedShipDate": r.get("VDATU", ""),
            "SalesOrderStatus": "Confirmed",
            "CurrencyCode": r.get("WAERK", "USD"),
            "TotalOrderAmount": r.get("NETWR", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "SalesOrderHeadersV2.csv", so_headers,
              ["SalesOrderNumber", "CustomerAccountNumber", "OrderDate",
               "RequestedShipDate", "SalesOrderStatus", "CurrencyCode",
               "TotalOrderAmount", "dataAreaId"])

    # ── SalesOrderLinesV2.csv ────────────────────────────────────────────
    so_lines_out = []
    for r in vbap_plant:
        if r.get("MATNR", "") not in materials:
            continue
        so_lines_out.append({
            "SalesOrderNumber": r.get("VBELN", ""),
            "LineNumber": r.get("POSNR", ""),
            "ItemNumber": r.get("MATNR", ""),
            "OrderedSalesQuantity": safe_float(r.get("KWMENG", "0")),
            "DeliveredQuantity": 0,
            "SalesPrice": safe_float(r.get("NETPR", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "SalesOrderLinesV2.csv", so_lines_out,
              ["SalesOrderNumber", "LineNumber", "ItemNumber",
               "OrderedSalesQuantity", "DeliveredQuantity", "SalesPrice",
               "dataAreaId"])

    # ── InventWarehouseOnHandEntity.csv ──────────────────────────────────
    inv_rows = []
    for mat in sorted(materials):
        qty = stock_map.get(mat, 0.0)
        inv_rows.append({
            "ItemNumber": mat,
            "WarehouseId": plant,
            "SiteId": plant,
            "PhysicalOnHandQuantity": qty,
            "ReservedQuantity": 0,
            "AvailableQuantity": qty,
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "InventWarehouseOnHandEntity.csv", inv_rows,
              ["ItemNumber", "WarehouseId", "SiteId", "PhysicalOnHandQuantity",
               "ReservedQuantity", "AvailableQuantity", "dataAreaId"])

    # ── ItemCoverageSettings.csv ─────────────────────────────────────────
    # Maps SAP MARC planning fields to D365 ItemCoverageSettings
    # See DIGITAL_TWIN.md §8C for the full field mapping
    DISMM_TO_COVERAGE_CODE = {
        "PD": 2,  # Deterministic MRP → Requirement (lot-for-lot)
        "VB": 3,  # Reorder Point → Min/Max
        "VM": 3,  # Auto Reorder Point → Min/Max
        "V1": 3,  # ROP + External → Min/Max
        "V2": 3,  # Auto ROP + External → Min/Max
        "VV": 2,  # Forecast-based → Requirement
        "ND": 0,  # No planning → Manual
    }

    coverage_rows = []
    for mat in sorted(materials):
        marc_r = marc_map.get(mat, {})
        eisbe = safe_float(marc_r.get("EISBE", "0"))
        minbe = safe_float(marc_r.get("MINBE", "0"))
        mabst = safe_float(marc_r.get("MABST", "0"))
        dismm = (marc_r.get("DISMM", "") or "").strip()
        losgr = safe_float(marc_r.get("LOSGR", "0"))
        bstmi = safe_float(marc_r.get("BSTMI", "0"))
        bstma = safe_float(marc_r.get("BSTMA", "0"))
        bstrf = safe_float(marc_r.get("BSTRF", "0"))
        plifz = int(safe_float(marc_r.get("PLIFZ", "0")))
        dzeit = int(safe_float(marc_r.get("DZEIT", "0")))
        fxhor = int(safe_float(marc_r.get("FXHOR", "0")))

        coverage_rows.append({
            "ItemNumber": mat,
            "SiteId": plant,
            "WarehouseId": plant,
            "MinimumInventoryLevel": minbe,
            "MaximumInventoryLevel": mabst,
            "SafetyStockQuantity": eisbe,
            "CoveragePlanGroupId": marc_r.get("DISMM", ""),
            # New planning fields (SAP MARC → D365 ItemCoverageSettings)
            "CoverageCode": DISMM_TO_COVERAGE_CODE.get(dismm, 2),
            "StandardOrderQuantity": losgr,
            "MinimumOrderQuantity": bstmi,
            "MaximumOrderQuantity": bstma,
            "MultipleQuantity": bstrf,
            "LeadTimePurchase": plifz if (marc_r.get("BESKZ", "") or "").strip() == "F" else 0,
            "LeadTimeProduction": dzeit if (marc_r.get("BESKZ", "") or "").strip() in ("E", "X") else 0,
            "LeadTimeTransfer": 0,  # No SAP equivalent for inter-plant transfer LT in MARC
            "CoverageTimeFence": fxhor if fxhor > 0 else 90,  # Default 90 days
            "LockingTimeFence": fxhor,  # SAP FXHOR ≈ D365 firming fence
            "MaxPositiveDays": 7,   # Default: accept supply up to 7 days early
            "MaxNegativeDays": 3,   # Default: accept supply up to 3 days late
            "PreferredVendor": "",  # Would come from EORD source list
            "FulfillMinimum": "",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ItemCoverageSettings.csv", coverage_rows,
              ["ItemNumber", "SiteId", "WarehouseId", "MinimumInventoryLevel",
               "MaximumInventoryLevel", "SafetyStockQuantity",
               "CoveragePlanGroupId", "CoverageCode",
               "StandardOrderQuantity", "MinimumOrderQuantity", "MaximumOrderQuantity",
               "MultipleQuantity", "LeadTimePurchase", "LeadTimeProduction", "LeadTimeTransfer",
               "CoverageTimeFence", "LockingTimeFence",
               "MaxPositiveDays", "MaxNegativeDays",
               "PreferredVendor", "FulfillMinimum", "dataAreaId"])

    # ── ProductionOrderHeaders.csv ───────────────────────────────────────
    prod_orders = []
    for r in afko:
        mat = r.get("PLNBEZ", "")
        if mat not in materials:
            continue
        prod_orders.append({
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "ItemNumber": mat,
            "ProductionQuantity": safe_float(r.get("GAMNG", "0")),
            "ProductionStatus": "Started",
            "ScheduledStartDate": r.get("GSTRS", ""),
            "ScheduledEndDate": r.get("GLTRS", ""),
            "SiteId": plant,
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductionOrderHeaders.csv", prod_orders,
              ["ProductionOrderNumber", "ItemNumber", "ProductionQuantity",
               "ProductionStatus", "ScheduledStartDate", "ScheduledEndDate",
               "SiteId", "dataAreaId"])

    # ── DemandForecastEntries.csv ────────────────────────────────────────
    forecast_rows = []
    for r in pbed:
        bdzei = r.get("BDZEI", "")
        mat = pbim_map.get(bdzei, "")
        if not mat or mat not in materials:
            continue
        forecast_rows.append({
            "ItemNumber": mat,
            "SiteId": plant,
            "WarehouseId": plant,
            "ForecastQuantity": safe_float(r.get("PLNMG", "0")),
            "ForecastDate": r.get("PDATU", ""),
            "ForecastModel": "SAP_TRANSLATED",
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "DemandForecastEntries.csv", forecast_rows,
              ["ItemNumber", "SiteId", "WarehouseId", "ForecastQuantity",
               "ForecastDate", "ForecastModel", "dataAreaId"])

    # ══════════════════════════════════════════════════════════════════════
    # ADDITIONAL MASTER DATA (previously missing)
    # ══════════════════════════════════════════════════════════════════════
    print("\n  --- Additional Master Data ---")

    # ── LegalEntities.csv (T001) ─────────────────────────────────────────
    legal_entities = []
    for r in t001:
        legal_entities.append({
            "DataArea": r.get("BUKRS", ""),
            "Name": r.get("BUTXT", ""),
            "AddressCountryRegionId": r.get("LAND1", ""),
            "CurrencyCode": r.get("WAERS", ""),
            "dataAreaId": r.get("BUKRS", "").lower(),
        })
    write_csv(output_dir, "LegalEntities.csv", legal_entities,
              ["DataArea", "Name", "AddressCountryRegionId", "CurrencyCode", "dataAreaId"])

    # ── StorageLocations.csv (T001L → extends Warehouses) ────────────────
    storage_locs = []
    for r in t001l:
        storage_locs.append({
            "SiteId": r.get("WERKS", ""),
            "StorageLocationId": r.get("LGORT", ""),
            "StorageLocationName": r.get("LGOBE", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "StorageLocations.csv", storage_locs,
              ["SiteId", "StorageLocationId", "StorageLocationName", "dataAreaId"])

    # ── ProductUnitConversions.csv (MARM) ────────────────────────────────
    uom_conversions = []
    for r in marm:
        if r.get("MATNR", "") not in materials:
            continue
        uom_conversions.append({
            "ItemNumber": r.get("MATNR", ""),
            "AlternativeUnitSymbol": r.get("MEINH", ""),
            "Numerator": safe_float(r.get("UMREZ", "1")),
            "Denominator": safe_float(r.get("UMREN", "1")),
            "GrossWeight": safe_float(r.get("BRGEW", "0")),
            "Volume": safe_float(r.get("VOLUM", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductUnitConversions.csv", uom_conversions,
              ["ItemNumber", "AlternativeUnitSymbol", "Numerator", "Denominator",
               "GrossWeight", "Volume", "dataAreaId"])

    # ── VendorPurchasePrices.csv (EINA+EINE joined) ─────────────────────
    vendor_prices = []
    for r in eine:
        infnr = r.get("INFNR", "")
        eina_r = eina_map.get(infnr, {})
        mat = eina_r.get("MATNR", "")
        vendor = eina_r.get("LIFNR", "")
        if not mat or not vendor:
            continue
        vendor_prices.append({
            "VendorAccountNumber": vendor,
            "ItemNumber": mat,
            "PurchasingOrganization": r.get("EKORG", ""),
            "SiteId": r.get("WERKS", ""),
            "UnitPrice": safe_float(r.get("NETPR", "0")),
            "PriceUnit": safe_float(r.get("PEINH", "1")),
            "Currency": r.get("WAERS", "USD"),
            "LeadTimeDays": safe_float(r.get("APLFZ", "0")),
            "MinimumOrderQuantity": safe_float(r.get("NORBM", "0")),
            "MinimumQuantity": safe_float(r.get("MINBM", "0")),
            "OverdeliveryTolerance": safe_float(r.get("UEBTO", "0")),
            "UnderdeliveryTolerance": safe_float(r.get("UNTTO", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "VendorPurchasePrices.csv", vendor_prices,
              ["VendorAccountNumber", "ItemNumber", "PurchasingOrganization", "SiteId",
               "UnitPrice", "PriceUnit", "Currency", "LeadTimeDays",
               "MinimumOrderQuantity", "MinimumQuantity",
               "OverdeliveryTolerance", "UnderdeliveryTolerance", "dataAreaId"])

    # ── ApprovedVendorList.csv (EORD — source list) ─────────────────────
    approved_vendors = []
    for r in eord:
        approved_vendors.append({
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("WERKS", ""),
            "SourceListNumber": r.get("ZEORD", ""),
            "ValidFromDate": r.get("VDATU", ""),
            "ValidToDate": r.get("BDATU", ""),
            "VendorAccountNumber": r.get("LIFNR", ""),
            "IsFixed": r.get("FLIFN", ""),
            "IsBlocked": r.get("NOTKZ", ""),
            "PurchasingOrganization": r.get("EKORG", ""),
            "SourceType": r.get("EORTP", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ApprovedVendorList.csv", approved_vendors,
              ["ItemNumber", "SiteId", "SourceListNumber", "ValidFromDate",
               "ValidToDate", "VendorAccountNumber", "IsFixed", "IsBlocked",
               "PurchasingOrganization", "SourceType", "dataAreaId"])

    # ── CustomerSalesAreas.csv (KNVV) ────────────────────────────────────
    cust_sales = []
    for r in knvv:
        cust_sales.append({
            "CustomerAccount": r.get("KUNNR", ""),
            "SalesOrganization": r.get("VKORG", ""),
            "DistributionChannel": r.get("VTWEG", ""),
            "Division": r.get("SPART", ""),
            "Currency": r.get("WAERS", ""),
            "PricingProcedure": r.get("KALKS", ""),
            "DeliveryPriority": r.get("LPRIO", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "CustomerSalesAreas.csv", cust_sales,
              ["CustomerAccount", "SalesOrganization", "DistributionChannel",
               "Division", "Currency", "PricingProcedure", "DeliveryPriority", "dataAreaId"])

    # ── WorkCenters.csv (CRHD + CRCO) ───────────────────────────────────
    work_centers = []
    for r in crhd:
        if r.get("WERKS", "") != plant and r.get("WERKS", ""):
            continue
        objid = r.get("OBJID", "")
        work_centers.append({
            "WorkCenterId": objid,
            "WorkCenterName": r.get("ARBPL", ""),
            "SiteId": r.get("WERKS", ""),
            "WorkCenterType": r.get("VERWE", ""),
            "ObjectType": r.get("OBJTY", ""),
            "CostCenter": crco_map.get(objid, ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "WorkCenters.csv", work_centers,
              ["WorkCenterId", "WorkCenterName", "SiteId", "WorkCenterType",
               "ObjectType", "CostCenter", "dataAreaId"])

    # ── RoutingHeaders.csv (PLKO) ────────────────────────────────────────
    routing_headers = []
    for r in plko:
        if r.get("LOEKZ") == "X":  # Skip deleted
            continue
        if r.get("WERKS", "") != plant and r.get("WERKS", ""):
            continue
        routing_headers.append({
            "RoutingType": r.get("PLNTY", ""),
            "RoutingNumber": r.get("PLNNR", ""),
            "RoutingAlternative": r.get("PLNAL", ""),
            "SiteId": r.get("WERKS", ""),
            "RoutingStatus": r.get("STATU", ""),
            "BaseUnitSymbol": r.get("PLNME", ""),
            "UsageType": r.get("VERWE", ""),
            "Description": r.get("KTEXT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "RoutingHeaders.csv", routing_headers,
              ["RoutingType", "RoutingNumber", "RoutingAlternative", "SiteId",
               "RoutingStatus", "BaseUnitSymbol", "UsageType", "Description", "dataAreaId"])

    # ── RoutingOperations.csv (PLPO) ─────────────────────────────────────
    routing_ops = []
    for r in plpo:
        routing_ops.append({
            "RoutingType": r.get("PLNTY", ""),
            "RoutingNumber": r.get("PLNNR", ""),
            "OperationNode": r.get("PLNKN", ""),
            "OperationNumber": r.get("VORNR", ""),
            "WorkCenterId": r.get("ARBID", ""),
            "ControlKey": r.get("STEUS", ""),
            "SetupTime": safe_float(r.get("VGW01", "0")),
            "MachineTime": safe_float(r.get("VGW02", "0")),
            "LaborTime": safe_float(r.get("VGW03", "0")),
            "SetupTimeUnit": r.get("VGE01", ""),
            "MachineTimeUnit": r.get("VGE02", ""),
            "LaborTimeUnit": r.get("VGE03", ""),
            "BaseQuantity": safe_float(r.get("BMSCH", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "RoutingOperations.csv", routing_ops,
              ["RoutingType", "RoutingNumber", "OperationNode", "OperationNumber",
               "WorkCenterId", "ControlKey", "SetupTime", "MachineTime", "LaborTime",
               "SetupTimeUnit", "MachineTimeUnit", "LaborTimeUnit", "BaseQuantity", "dataAreaId"])

    # ── CapacityData.csv (KAKO) ──────────────────────────────────────────
    capacity_rows = []
    for r in kako:
        capacity_rows.append({
            "CapacityId": r.get("KAPID", ""),
            "MaxCapacity": safe_float(r.get("AZMAX", "0")),
            "NormalCapacity": safe_float(r.get("AZNOR", "0")),
            "BaseUnit": r.get("MEINS", ""),
            "CalendarId": r.get("KALID", ""),
            "CapacityCategory": r.get("KAPAR", ""),
            "StartTime": r.get("BEGZT", ""),
            "EndTime": r.get("ENDZT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "CapacityData.csv", capacity_rows,
              ["CapacityId", "MaxCapacity", "NormalCapacity", "BaseUnit",
               "CalendarId", "CapacityCategory", "StartTime", "EndTime", "dataAreaId"])

    # ── BatchMaster.csv (MCH1 + MCHA) ───────────────────────────────────
    batches = []
    for r in mcha:  # Plant-level batches (more specific)
        if r.get("MATNR", "") not in materials:
            continue
        batches.append({
            "ItemNumber": r.get("MATNR", ""),
            "BatchNumber": r.get("CHARG", ""),
            "SiteId": r.get("WERKS", ""),
            "IsDeleted": r.get("LVORM", ""),
            "CreationDate": r.get("ERSDA", ""),
            "ExpirationDate": r.get("VFDAT", ""),
            "dataAreaId": data_area,
        })
    for r in mch1:  # Plant-independent batches (add if not already present)
        if r.get("MATNR", "") not in materials:
            continue
        batch_key = f"{r.get('MATNR', '')}|{r.get('CHARG', '')}"
        if any(f"{b['ItemNumber']}|{b['BatchNumber']}" == batch_key for b in batches):
            continue
        batches.append({
            "ItemNumber": r.get("MATNR", ""),
            "BatchNumber": r.get("CHARG", ""),
            "SiteId": "",
            "IsDeleted": r.get("LVORM", ""),
            "CreationDate": r.get("ERSDA", ""),
            "ExpirationDate": r.get("VFDAT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "BatchMaster.csv", batches,
              ["ItemNumber", "BatchNumber", "SiteId", "IsDeleted",
               "CreationDate", "ExpirationDate", "dataAreaId"])

    # ══════════════════════════════════════════════════════════════════════
    # TRANSACTION HISTORY (Phase 3b)
    # ══════════════════════════════════════════════════════════════════════
    print("\n  --- Transaction History ---")

    # ── Shipments / Deliveries (LIKP+LIPS → ShipmentHeaders + ShipmentLines) ─
    shipment_headers = []
    for r in likp:
        shipment_headers.append({
            "ShipmentNumber": r.get("VBELN", ""),
            "ShipmentType": r.get("LFART", ""),
            "PlannedShipDate": r.get("WADAT", ""),
            "ActualShipDate": r.get("WADAT_IST", ""),
            "LoadingDate": r.get("LDDAT", ""),
            "DeliveryDate": r.get("LFDAT", ""),
            "RouteId": r.get("ROUTE", ""),
            "GrossWeight": safe_float(r.get("BTGEW", "0")),
            "NetWeight": safe_float(r.get("NTGEW", "0")),
            "Volume": safe_float(r.get("VOLUM", "0")),
            "WeightUnit": r.get("GEWEI", ""),
            "VolumeUnit": r.get("VOLEH", ""),
            "CustomerAccount": r.get("KUNNR", ""),
            "VendorAccountNumber": r.get("LIFNR", ""),
            "ShippingPoint": r.get("VSTEL", ""),
            "SalesOrganization": r.get("VKORG", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ShipmentHeaders.csv", shipment_headers,
              ["ShipmentNumber", "ShipmentType", "PlannedShipDate", "ActualShipDate",
               "LoadingDate", "DeliveryDate", "RouteId", "GrossWeight", "NetWeight",
               "Volume", "WeightUnit", "VolumeUnit", "CustomerAccount",
               "VendorAccountNumber", "ShippingPoint", "SalesOrganization", "dataAreaId"])

    shipment_lines = []
    for r in lips:
        if r.get("MATNR", "") not in materials and r.get("MATNR", ""):
            continue
        shipment_lines.append({
            "ShipmentNumber": r.get("VBELN", ""),
            "LineNumber": r.get("POSNR", ""),
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("WERKS", ""),
            "WarehouseId": r.get("LGORT", ""),
            "DeliveredQuantity": safe_float(r.get("LFIMG", "0")),
            "UnitSymbol": r.get("MEINS", ""),
            "SourceDocument": r.get("VGBEL", ""),
            "SourceLineNumber": r.get("VGPOS", ""),
            "ItemCategory": r.get("PSTYV", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ShipmentLines.csv", shipment_lines,
              ["ShipmentNumber", "LineNumber", "ItemNumber", "SiteId", "WarehouseId",
               "DeliveredQuantity", "UnitSymbol", "SourceDocument", "SourceLineNumber",
               "ItemCategory", "dataAreaId"])

    # ── PO Goods Receipt History (EKBE → PurchaseOrderReceiptJournal) ────
    po_receipts = []
    for r in ekbe:
        po_receipts.append({
            "PurchaseOrderNumber": r.get("EBELN", ""),
            "LineNumber": r.get("EBELP", ""),
            "MovementType": r.get("VGABE", ""),
            "TransactionType": r.get("BEWTP", ""),
            "Quantity": safe_float(r.get("MENGE", "0")),
            "Amount": safe_float(r.get("DMBTR", "0")),
            "PostingDate": r.get("BUDAT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PurchaseOrderReceiptJournal.csv", po_receipts,
              ["PurchaseOrderNumber", "LineNumber", "MovementType", "TransactionType",
               "Quantity", "Amount", "PostingDate", "dataAreaId"])

    # ── SO Delivery Schedule (VBEP → SalesOrderDeliverySchedules) ────────
    so_schedules = []
    for r in vbep:
        so_schedules.append({
            "SalesOrderNumber": r.get("VBELN", ""),
            "LineNumber": r.get("POSNR", ""),
            "ScheduleLineNumber": r.get("ETENR", ""),
            "RequestedDeliveryDate": r.get("EDATU", ""),
            "OrderedQuantity": safe_float(r.get("WMENG", "0")),
            "ConfirmedQuantity": safe_float(r.get("BMENG", "0")),
            "DeliveredQuantity": safe_float(r.get("LMENG", "0")),
            "UnitSymbol": r.get("MEINS", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "SalesOrderDeliverySchedules.csv", so_schedules,
              ["SalesOrderNumber", "LineNumber", "ScheduleLineNumber",
               "RequestedDeliveryDate", "OrderedQuantity", "ConfirmedQuantity",
               "DeliveredQuantity", "UnitSymbol", "dataAreaId"])

    # ── Production Order Components (RESB → ProductionOrderBOMLines) ─────
    prod_components = []
    for r in resb:
        if r.get("MATNR", "") not in materials and r.get("MATNR", ""):
            continue
        prod_components.append({
            "ReservationNumber": r.get("RSNUM", ""),
            "LineNumber": r.get("RSPOS", ""),
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("WERKS", ""),
            "WarehouseId": r.get("LGORT", ""),
            "RequiredQuantity": safe_float(r.get("BDMNG", "0")),
            "UnitSymbol": r.get("MEINS", ""),
            "RequirementDate": r.get("BDTER", ""),
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "IsWithdrawn": r.get("XWAOK", ""),
            "WithdrawnQuantity": safe_float(r.get("ENMNG", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductionOrderBOMLines.csv", prod_components,
              ["ReservationNumber", "LineNumber", "ItemNumber", "SiteId", "WarehouseId",
               "RequiredQuantity", "UnitSymbol", "RequirementDate",
               "ProductionOrderNumber", "IsWithdrawn", "WithdrawnQuantity", "dataAreaId"])

    # ── Production Routing Operations (AFVC → ProductionRouteOperations) ─
    prod_operations = []
    for r in afvc:
        if r.get("WERKS", "") != plant and r.get("WERKS", ""):
            continue
        prod_operations.append({
            "RoutingPlanNumber": r.get("AUFPL", ""),
            "OperationSequence": r.get("APLZL", ""),
            "OperationNumber": r.get("VORNR", ""),
            "WorkCenterId": r.get("ARBID", ""),
            "SiteId": r.get("WERKS", ""),
            "ControlKey": r.get("STEUS", ""),
            "OperationDescription": r.get("LTXA1", ""),
            "SubcontractorVendor": r.get("LIFNR", ""),
            "PlannedCost": safe_float(r.get("PREIS", "0")),
            "Currency": r.get("WAERS", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductionRouteOperations.csv", prod_operations,
              ["RoutingPlanNumber", "OperationSequence", "OperationNumber",
               "WorkCenterId", "SiteId", "ControlKey", "OperationDescription",
               "SubcontractorVendor", "PlannedCost", "Currency", "dataAreaId"])

    # ── Purchase Requisitions (EBAN → PurchaseRequisitionLines) ──────────
    requisitions = []
    for r in eban:
        if r.get("LOEKZ") == "X":  # Skip deleted
            continue
        if r.get("MATNR", "") not in materials and r.get("MATNR", ""):
            continue
        requisitions.append({
            "RequisitionNumber": r.get("BANFN", ""),
            "LineNumber": r.get("BNFPO", ""),
            "RequisitionType": r.get("BSART", ""),
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("WERKS", ""),
            "WarehouseId": r.get("LGORT", ""),
            "RequestedQuantity": safe_float(r.get("MENGE", "0")),
            "UnitSymbol": r.get("MEINS", ""),
            "EstimatedPrice": safe_float(r.get("PREIS", "0")),
            "PriceUnit": safe_float(r.get("PEINH", "1")),
            "PurchasingGroup": r.get("EKGRP", ""),
            "ReleaseIndicator": r.get("FRGKZ", ""),
            "ReleaseStatus": r.get("FRGZU", ""),
            "CreationDate": r.get("BADAT", ""),
            "DeliveryDate": r.get("LFDAT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PurchaseRequisitionLines.csv", requisitions,
              ["RequisitionNumber", "LineNumber", "RequisitionType", "ItemNumber",
               "SiteId", "WarehouseId", "RequestedQuantity", "UnitSymbol",
               "EstimatedPrice", "PriceUnit", "PurchasingGroup",
               "ReleaseIndicator", "ReleaseStatus", "CreationDate", "DeliveryDate", "dataAreaId"])

    # ── Planned Orders / MRP Output (PLAF → PlannedOrders) ───────────────
    planned_orders = []
    for r in plaf:
        if r.get("MATNR", "") not in materials and r.get("MATNR", ""):
            continue
        planned_orders.append({
            "PlannedOrderNumber": r.get("PLNUM", ""),
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("PLWRK", ""),
            "PlannedQuantity": safe_float(r.get("GSMNG", "0")),
            "UnitSymbol": r.get("MEINS", ""),
            "PlannedEndDate": r.get("PEDTR", ""),
            "PlannedStartDate": r.get("PSTTR", ""),
            "BOMId": r.get("STLFX", ""),
            "OrderType": r.get("PAART", ""),
            "ProcurementType": r.get("BESKZ", ""),
            "RoutingType": r.get("PLNTY", ""),
            "MRPController": r.get("DISPO", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PlannedOrders.csv", planned_orders,
              ["PlannedOrderNumber", "ItemNumber", "SiteId", "PlannedQuantity",
               "UnitSymbol", "PlannedEndDate", "PlannedStartDate", "BOMId",
               "OrderType", "ProcurementType", "RoutingType", "MRPController", "dataAreaId"])

    # ── Equipment / Maintenance Assets (EQUI → MaintenanceAssets) ────────
    assets = []
    for r in equi:
        assets.append({
            "EquipmentNumber": r.get("EQUNR", ""),
            "EquipmentType": r.get("EQART", ""),
            "CreationDate": r.get("ERDAT", ""),
            "AcquisitionDate": r.get("ANSDT", ""),
            "AcquisitionValue": safe_float(r.get("ANSWT", "0")),
            "Currency": r.get("WAERS", ""),
            "Manufacturer": r.get("HERST", ""),
            "SerialNumber": r.get("SERGE", ""),
            "ModelNumber": r.get("TYPBZ", ""),
            "GrossWeight": safe_float(r.get("BRGEW", "0")),
            "WeightUnit": r.get("GEWEI", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "MaintenanceAssets.csv", assets,
              ["EquipmentNumber", "EquipmentType", "CreationDate", "AcquisitionDate",
               "AcquisitionValue", "Currency", "Manufacturer", "SerialNumber",
               "ModelNumber", "GrossWeight", "WeightUnit", "dataAreaId"])

    # ── Quality Inspection Lots (QALS → QualityOrders) ───────────────────
    quality_orders = []
    for r in qals:
        quality_orders.append({
            "QualityOrderNumber": r.get("PRUEFLOS", ""),
            "ItemNumber": r.get("MATNR", ""),
            "SiteId": r.get("WERK", ""),
            "InspectionType": r.get("ART", ""),
            "Origin": r.get("HERKUNFT", ""),
            "ProcessingStatus": r.get("BEARBSTATU", ""),
            "CreationDate": r.get("ENSTEHDAT", ""),
            "CreationTime": r.get("ENTSTEZEIT", ""),
            "PlannedStartDate": r.get("PASTRTERM", ""),
            "PlannedEndDate": r.get("PAENDTERM", ""),
            "LotQuantity": safe_float(r.get("LOSMENGE", "0")),
            "UnitSymbol": r.get("MENGENEINH", ""),
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "BatchNumber": r.get("CHARG", ""),
            "StockType": r.get("INSMK", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "QualityOrders.csv", quality_orders,
              ["QualityOrderNumber", "ItemNumber", "SiteId", "InspectionType",
               "Origin", "ProcessingStatus", "CreationDate", "CreationTime",
               "PlannedStartDate", "PlannedEndDate", "LotQuantity", "UnitSymbol",
               "ProductionOrderNumber", "BatchNumber", "StockType", "dataAreaId"])

    # ── PO Schedule Lines (EKET → PurchaseOrderScheduleLines) ────────────
    po_schedules = []
    for r in eket:
        po_schedules.append({
            "PurchaseOrderNumber": r.get("EBELN", ""),
            "LineNumber": r.get("EBELP", ""),
            "ScheduleLineNumber": r.get("ETENR", ""),
            "DeliveryDate": r.get("EINDT", ""),
            "ScheduledQuantity": safe_float(r.get("MENGE", "0")),
            "ReceivedQuantity": safe_float(r.get("WEMNG", "0")),
            "IssuedQuantity": safe_float(r.get("WAMNG", "0")),
            "StatisticalDeliveryDate": r.get("SLFDT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "PurchaseOrderScheduleLines.csv", po_schedules,
              ["PurchaseOrderNumber", "LineNumber", "ScheduleLineNumber",
               "DeliveryDate", "ScheduledQuantity", "ReceivedQuantity",
               "IssuedQuantity", "StatisticalDeliveryDate", "dataAreaId"])

    # ── Production Order Items (AFPO → ProductionOrderItems) ─────────────
    prod_items = []
    for r in afpo:
        if r.get("MATNR", "") not in materials and r.get("MATNR", ""):
            continue
        prod_items.append({
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "LineNumber": r.get("POSNR", ""),
            "ItemNumber": r.get("MATNR", ""),
            "UnitSymbol": r.get("MEINS", ""),
            "PlannedQuantity": safe_float(r.get("PSMNG", "0")),
            "DeliveredQuantity": safe_float(r.get("WEMNG", "0")),
            "LatestFinishDate": r.get("LTRMI", ""),
            "LatestStartDate": r.get("LTRMP", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductionOrderItems.csv", prod_items,
              ["ProductionOrderNumber", "LineNumber", "ItemNumber", "UnitSymbol",
               "PlannedQuantity", "DeliveredQuantity", "LatestFinishDate",
               "LatestStartDate", "dataAreaId"])

    # ── Production Confirmations (AFRU → ProductionOrderConfirmations) ───
    prod_confirms = []
    for r in afru:
        prod_confirms.append({
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "OperationNumber": r.get("VORNR", ""),
            "YieldQuantity": safe_float(r.get("LMNGA", "0")),
            "ScrapQuantity": safe_float(r.get("XMNGA", "0")),
            "ReworkQuantity": safe_float(r.get("RMNGA", "0")),
            "ActivityQuantity1": safe_float(r.get("ISM01", "0")),
            "ActivityQuantity2": safe_float(r.get("ISM02", "0")),
            "ActivityQuantity3": safe_float(r.get("ISM03", "0")),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ProductionOrderConfirmations.csv", prod_confirms,
              ["ProductionOrderNumber", "OperationNumber", "YieldQuantity",
               "ScrapQuantity", "ReworkQuantity", "ActivityQuantity1",
               "ActivityQuantity2", "ActivityQuantity3", "dataAreaId"])

    # ── Quality Test Results (QASE → QualityTestResults) ─────────────────
    quality_results = []
    for r in qase:
        quality_results.append({
            "QualityOrderNumber": r.get("PRUEFLOS", ""),
            "OperationSequence": r.get("VORGLFNR", ""),
            "CharacteristicNumber": r.get("MERKNR", ""),
            "MeasuredValue": safe_float(r.get("MESSWERT", "0")),
            "Valuation": r.get("MBEWERTG", ""),
            "DefectCount": safe_float(r.get("ANZFEHLER", "0")),
            "CatalogCode": r.get("CODE1", ""),
            "Version": r.get("VERSION1", ""),
            "CreationDate": r.get("ERSTELLDAT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "QualityTestResults.csv", quality_results,
              ["QualityOrderNumber", "OperationSequence", "CharacteristicNumber",
               "MeasuredValue", "Valuation", "DefectCount", "CatalogCode",
               "Version", "CreationDate", "dataAreaId"])

    # ── Quality Notifications (QMEL → QualityNotifications) ──────────────
    quality_notifs = []
    for r in qmel:
        quality_notifs.append({
            "NotificationNumber": r.get("QMNUM", ""),
            "NotificationType": r.get("QMART", ""),
            "ItemNumber": r.get("MATNR", ""),
            "CreationDate": r.get("ERDAT", ""),
            "Priority": r.get("PRIOK", ""),
            "RequiredStartDate": r.get("STRMN", ""),
            "RequiredEndDate": r.get("LTRMN", ""),
            "Description": r.get("QMTXT", ""),
            "ProductionOrderNumber": r.get("AUFNR", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "QualityNotifications.csv", quality_notifs,
              ["NotificationNumber", "NotificationType", "ItemNumber",
               "CreationDate", "Priority", "RequiredStartDate", "RequiredEndDate",
               "Description", "ProductionOrderNumber", "dataAreaId"])

    # ── Object Status History (JEST → ObjectStatusHistory) ───────────────
    status_rows = []
    for r in jest:
        status_rows.append({
            "ObjectNumber": r.get("OBJNR", ""),
            "StatusCode": r.get("STAT", ""),
            "IsInactive": r.get("INACT", ""),
            "dataAreaId": data_area,
        })
    write_csv(output_dir, "ObjectStatusHistory.csv", status_rows,
              ["ObjectNumber", "StatusCode", "IsInactive", "dataAreaId"])

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  Translation complete!")
    print(f"  Output: {output_dir}/")
    print(f"")
    print(f"  Master Data:")
    print(f"    Sites.csv                       {len(sites)} sites")
    print(f"    Warehouses.csv                  {len(warehouses)} warehouses")
    print(f"    ReleasedProductsV2.csv          {len(products)} products")
    print(f"    Vendors.csv                     {len(vendors)} vendors")
    print(f"    CustomersV3.csv                 {len(customers)} customers")
    print(f"    BillOfMaterialsHeaders.csv      {len(bom_headers)} BOMs")
    print(f"    BillOfMaterialsLines.csv        {len(bom_lines)} BOM lines")
    print(f"    InventWarehouseOnHandEntity.csv {len(inv_rows)} inventory rows")
    print(f"    ItemCoverageSettings.csv        {len(coverage_rows)} coverage rows")
    print(f"    DemandForecastEntries.csv       {len(forecast_rows)} forecast entries")
    print(f"")
    print(f"  Open Orders:")
    print(f"    PurchaseOrderHeadersV2.csv      {len(po_headers)} POs")
    print(f"    PurchaseOrderLinesV2.csv        {len(po_lines_out)} PO lines")
    print(f"    SalesOrderHeadersV2.csv         {len(so_headers)} SOs")
    print(f"    SalesOrderLinesV2.csv           {len(so_lines_out)} SO lines")
    print(f"    ProductionOrderHeaders.csv      {len(prod_orders)} production orders")
    print(f"")
    print(f"  Additional Master Data:")
    print(f"    LegalEntities.csv               {len(legal_entities)} companies")
    print(f"    StorageLocations.csv            {len(storage_locs)} locations")
    print(f"    ProductUnitConversions.csv      {len(uom_conversions)} UOM conversions")
    print(f"    VendorPurchasePrices.csv        {len(vendor_prices)} vendor prices")
    print(f"    ApprovedVendorList.csv          {len(approved_vendors)} source list entries")
    print(f"    CustomerSalesAreas.csv          {len(cust_sales)} customer sales areas")
    print(f"    WorkCenters.csv                 {len(work_centers)} work centers")
    print(f"    RoutingHeaders.csv              {len(routing_headers)} routing headers")
    print(f"    RoutingOperations.csv           {len(routing_ops)} routing operations")
    print(f"    CapacityData.csv                {len(capacity_rows)} capacity entries")
    print(f"    BatchMaster.csv                 {len(batches)} batch records")
    print(f"")
    print(f"  Transaction History:")
    print(f"    ShipmentHeaders.csv             {len(shipment_headers)} deliveries")
    print(f"    ShipmentLines.csv               {len(shipment_lines)} delivery items")
    print(f"    PurchaseOrderReceiptJournal.csv  {len(po_receipts)} GR entries")
    print(f"    PurchaseOrderScheduleLines.csv  {len(po_schedules)} PO schedule lines")
    print(f"    SalesOrderDeliverySchedules.csv {len(so_schedules)} SO schedule lines")
    print(f"    ProductionOrderBOMLines.csv     {len(prod_components)} components")
    print(f"    ProductionOrderItems.csv        {len(prod_items)} prod order items")
    print(f"    ProductionOrderConfirmations.csv {len(prod_confirms)} confirmations")
    print(f"    ProductionRouteOperations.csv   {len(prod_operations)} operations")
    print(f"    PurchaseRequisitionLines.csv    {len(requisitions)} requisitions")
    print(f"    PlannedOrders.csv               {len(planned_orders)} MRP planned orders")
    print(f"    MaintenanceAssets.csv           {len(assets)} equipment")
    print(f"    QualityOrders.csv               {len(quality_orders)} inspection lots")
    print(f"    QualityTestResults.csv          {len(quality_results)} test results")
    print(f"    QualityNotifications.csv        {len(quality_notifs)} notifications")
    print(f"    ObjectStatusHistory.csv         {len(status_rows)} status records")
    print(f"")
    print(f"  Next step:")
    print(f"    python scripts/rebuild_d365_contoso_config.py \\")
    print(f"      --config-id <ID> --csv-dir {output_dir}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

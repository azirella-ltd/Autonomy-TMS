#!/usr/bin/env python3
"""
Ingest extracted SAP IDES CSV files into Autonomy as an operational tenant.

Creates:
  1. Operational tenant (TenantMode.PRODUCTION)
  2. Supply chain config with sites, products, transportation lanes, BOMs
  3. AWS SC entities: forecasts, inventory levels, inv policies, sourcing rules
  4. Transactional data: outbound orders, inbound orders (POs), production orders

Usage:
    python scripts/ingest_sap_csvs.py [--csv-dir imports/SAP/IDES_1710] [--dry-run]
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

os.environ.setdefault("DATABASE_TYPE", "postgresql")


# ---------------------------------------------------------------------------
# CSV reading helpers
# ---------------------------------------------------------------------------

def read_csv(csv_dir: Path, filename: str) -> List[Dict[str, str]]:
    """Read a CSV file and return list of dicts. Returns [] if file missing."""
    path = csv_dir / filename
    if not path.exists():
        print(f"  SKIP {filename} (not found)")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"  READ {filename}: {len(rows)} rows")
    return rows


def strip_leading_zeros(val: str) -> str:
    """Strip SAP leading zeros from numeric IDs like '000000000000002211' -> '2211'."""
    if val and val.isdigit():
        return val.lstrip("0") or "0"
    return val


def safe_float(val: str, default: float = 0.0) -> float:
    """Parse float safely."""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def parse_sap_date(val: str) -> Optional[date]:
    """Parse SAP date formats: YYYYMMDD or YYYY-MM-DD."""
    if not val or val == "00000000" or len(val) < 8:
        return None
    try:
        if "-" in val:
            return datetime.strptime(val[:10], "%Y-%m-%d").date()
        return datetime.strptime(val[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest(csv_dir: Path, tenant_id: int, dry_run: bool = False):
    """Ingest SAP CSVs into an existing Autonomy tenant.

    Prerequisites (done by systemadmin via UI):
      1. Create tenant (e.g. "Autonomy SAP Demo") with mode=PRODUCTION
      2. Create tenant admin (e.g. admin@sap_demo.com)
      3. SAP tenant admin logs in, downloads SAP CSVs, then runs this script
    """
    print(f"\n{'='*60}")
    print(f"SAP IDES CSV Ingestion → Tenant {tenant_id}")
    print(f"Source: {csv_dir}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*60}\n")

    # -----------------------------------------------------------------------
    # Phase 1: Read all CSVs into memory
    # -----------------------------------------------------------------------
    print("Phase 1: Reading CSV files...")

    plants = read_csv(csv_dir, "T001W_plants.csv")
    materials = read_csv(csv_dir, "MARA_materials.csv")
    mat_plant = read_csv(csv_dir, "MARC_material_plant.csv")
    mat_desc = read_csv(csv_dir, "MAKT_descriptions.csv")
    vendors = read_csv(csv_dir, "LFA1_vendors.csv")
    customers = read_csv(csv_dir, "KNA1_customers.csv")
    bom_headers = read_csv(csv_dir, "STKO_bom_headers.csv")
    bom_items = read_csv(csv_dir, "STPO_bom_items.csv")
    source_list = read_csv(csv_dir, "EORD_source_list.csv")
    stock = read_csv(csv_dir, "MARD_stock.csv")
    valuation = read_csv(csv_dir, "MBEW_valuation.csv")
    sales_orders = read_csv(csv_dir, "VBAK_sales_orders.csv")
    sales_items = read_csv(csv_dir, "VBAP_sales_order_items.csv")
    schedule_lines = read_csv(csv_dir, "VBEP_schedule_lines.csv")
    po_headers = read_csv(csv_dir, "EKKO_purchase_orders.csv")
    po_items = read_csv(csv_dir, "EKPO_purchase_order_items.csv")
    deliveries = read_csv(csv_dir, "LIKP_deliveries.csv")
    delivery_items = read_csv(csv_dir, "LIPS_delivery_items.csv")
    prod_orders = read_csv(csv_dir, "AFKO_production_orders.csv")
    prod_order_items = read_csv(csv_dir, "AFPO_production_order_items.csv")
    work_centers = read_csv(csv_dir, "CRHD_work_centers.csv")
    equipment = read_csv(csv_dir, "EQUI_equipment.csv")
    quality_notif = read_csv(csv_dir, "QMEL_notifications.csv")

    # New tables (Phase 2 — status, forecasts, quality, operations)
    jest_statuses = read_csv(csv_dir, "JEST_system_status.csv")
    status_texts = read_csv(csv_dir, "TJ02T_status_texts.csv")
    pir_headers = read_csv(csv_dir, "PBIM_pir_header.csv")
    pir_schedule = read_csv(csv_dir, "PBED_pir_schedule.csv")
    inspection_lots = read_csv(csv_dir, "QALS_inspection_lots.csv")
    order_operations = read_csv(csv_dir, "AFVC_order_operations.csv")

    # Build lookup maps
    desc_map: Dict[str, str] = {}
    for d in mat_desc:
        if d.get("SPRAS") == "E":
            desc_map[d["MATNR"]] = d.get("MAKTX", "")

    # -----------------------------------------------------------------------
    # JEST status mapping: OBJNR → set of active system statuses
    # OBJNR prefix "OR" = production order (AUFNR = digits after OR)
    # -----------------------------------------------------------------------
    objnr_statuses: Dict[str, Set[str]] = defaultdict(set)
    for j in jest_statuses:
        objnr = j.get("OBJNR", "")
        stat = j.get("STAT", "")
        inact = j.get("INACT", "")
        if objnr and stat and not inact:  # Only active statuses
            objnr_statuses[objnr].add(stat)

    def aufnr_to_objnr(aufnr: str) -> str:
        """Convert SAP order number to JEST object number (OR prefix)."""
        return f"OR{aufnr.zfill(12)}"

    def jest_to_production_status(statuses: Set[str]) -> str:
        """Map JEST system statuses to Autonomy ProductionOrder status.
        Priority order (highest lifecycle state wins):
          I0046 CLSD → CLOSED
          I0045 TECO → COMPLETED
          I0009 CNF  → IN_PROGRESS (confirmed = work has begun)
          I0002 REL  → RELEASED
          I0001 CRTD → PLANNED
        """
        if "I0046" in statuses:
            return "CLOSED"
        if "I0045" in statuses:
            return "COMPLETED"
        if "I0009" in statuses:
            return "IN_PROGRESS"
        if "I0002" in statuses:
            return "RELEASED"
        if "I0001" in statuses:
            return "PLANNED"
        return "PLANNED"

    def gbstk_to_outbound_status(gbstk: str) -> str:
        """Map VBAK.GBSTK (overall status) to Autonomy OutboundOrderLine status.
        A = Not yet processed → CONFIRMED
        B = Partially processed → PARTIALLY_FULFILLED
        C = Completely processed → FULFILLED
        """
        return {
            "A": "CONFIRMED",
            "B": "PARTIALLY_FULFILLED",
            "C": "FULFILLED",
        }.get(gbstk, "CONFIRMED")

    def elikz_to_inbound_status(elikz: str) -> str:
        """Map EKPO.ELIKZ (delivery completed indicator) to Autonomy InboundOrder status.
        X = Delivery completed → RECEIVED
        blank = Open → CONFIRMED
        """
        return "RECEIVED" if elikz == "X" else "CONFIRMED"

    # Build PIR header → material/plant map for forecast ingestion
    pir_header_map: Dict[str, Dict] = {}
    for ph in pir_headers:
        bdzei = ph.get("BDZEI", "")
        if bdzei:
            pir_header_map[bdzei] = ph

    val_map: Dict[str, Dict] = {}
    for v in valuation:
        val_map[v["MATNR"]] = v

    # -----------------------------------------------------------------------
    # Phase 2: Determine topology
    # -----------------------------------------------------------------------
    print("\nPhase 2: Analyzing supply chain topology...")

    # Plants → sites (INVENTORY or MANUFACTURER)
    plant_map: Dict[str, Dict] = {}
    for p in plants:
        plant_map[p["WERKS"]] = p

    # Determine which plants are manufacturers (have production orders)
    mfg_plants: Set[str] = set()
    for po in prod_orders:
        werks = mat_plant_lookup(mat_plant, po.get("PLNBEZ", ""))
        if werks:
            mfg_plants.add(werks)
    # Also check MARC SOBSL (special procurement) or BESKZ (procurement type)
    for mp in mat_plant:
        if mp.get("BESKZ") == "E":  # In-house production
            mfg_plants.add(mp["WERKS"])

    # Unique vendor IDs from POs
    vendor_ids: Set[str] = set()
    for po in po_headers:
        if po.get("LIFNR"):
            vendor_ids.add(po["LIFNR"])
    for sl in source_list:
        if sl.get("LIFNR"):
            vendor_ids.add(sl["LIFNR"])

    vendor_name_map: Dict[str, str] = {}
    for v in vendors:
        vendor_name_map[v["LIFNR"]] = v.get("NAME1", f"Vendor {v['LIFNR']}")

    # Unique customer IDs from sales orders
    customer_ids: Set[str] = set()
    for so in sales_orders:
        if so.get("KUNNR"):
            customer_ids.add(so["KUNNR"])

    customer_name_map: Dict[str, str] = {}
    for c in customers:
        customer_name_map[c["KUNNR"]] = c.get("NAME1", f"Customer {c['KUNNR']}")

    # Filter to materials that exist in our plant(s)
    active_materials: Set[str] = set()
    for mp in mat_plant:
        if mp["WERKS"] in plant_map:
            active_materials.add(mp["MATNR"])

    print(f"  Plants: {len(plant_map)}")
    print(f"  Manufacturing plants: {len(mfg_plants)}")
    print(f"  Vendors (suppliers): {len(vendor_ids)}")
    print(f"  Customers: {len(customer_ids)}")
    print(f"  Active materials: {len(active_materials)}")
    print(f"  BOM headers: {len(bom_headers)}, BOM items: {len(bom_items)}")

    if dry_run:
        print(f"\n[DRY RUN] Would create the following in tenant {tenant_id}:")
        print(f"  - 1 supply chain config")
        print(f"  - {len(plant_map)} plant sites (INVENTORY/MANUFACTURER)")
        print(f"  - {min(len(vendor_ids), 50)} supplier sites (MARKET_SUPPLY)")
        print(f"  - {min(len(customer_ids), 50)} customer sites (MARKET_DEMAND)")
        print(f"  - {len(active_materials)} products")
        print(f"  - Transportation lanes between sites")
        print(f"  - Inventory levels, forecasts, sourcing rules, BOMs")
        print(f"  - Outbound orders from sales data")
        print(f"  - Inbound orders from PO data")
        return

    # -----------------------------------------------------------------------
    # Phase 3: Create DB objects
    # -----------------------------------------------------------------------
    print("\nPhase 3: Creating Autonomy entities...")

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.db.session import get_database_url
    from app.models.tenant import Tenant, TenantMode
    from app.models.supply_chain_config import (
        SupplyChainConfig, Site, TransportationLane, Product as SCProduct, Market,
    )
    from app.models.sc_entities import (
        Product, ProductBOM, InvLevel, InvPolicy, Forecast,
        OutboundOrderLine, InboundOrder, InboundOrderLine,
        SourcingRule, VendorProduct, TradingPartner,
    )
    from app.models.production_order import ProductionOrder, ProductionOrderComponent
    from app.models.quality_order import QualityOrder

    db_url = get_database_url()
    engine = create_engine(db_url.replace("+asyncpg", "").replace("postgresql+aiopg", "postgresql"))
    session = Session(engine)

    try:
        # --- Look up existing tenant ---
        tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            print(f"ERROR: Tenant {tenant_id} not found. Create it first via Administration > Tenant Management.")
            return
        print(f"  Using tenant: {tenant.name} (id={tenant_id}, mode={tenant.mode})")

        # --- Supply Chain Config ---
        config = SupplyChainConfig(
            name="SAP IDES 1710 - US Operations",
            description="Extracted from SAP S/4HANA 2025 FAA, company code 1710, plant 1710",
            tenant_id=tenant_id,
            is_active=True,
        )
        session.add(config)
        session.flush()
        config_id = config.id
        print(f"  Created config: {config.name} (id={config_id})")

        # --- Sites ---
        site_id_map: Dict[str, int] = {}  # sap_key → site.id

        # Plant sites
        for werks, p in plant_map.items():
            master_type = "MANUFACTURER" if werks in mfg_plants else "INVENTORY"
            sc_site_type = "Factory" if master_type == "MANUFACTURER" else "Distribution Center"
            site = Site(
                config_id=config_id,
                name=p.get("NAME1", f"Plant {werks}"),
                site_id=f"PLANT-{werks}",
                master_type=master_type,
                sc_site_type=sc_site_type,
                dag_type=master_type,
                description=f"SAP Plant {werks}: {p.get('STRAS', '')} {p.get('ORT01', '')} {p.get('REGIO', '')}",
                country=p.get("LAND1", "US"),
                region=p.get("REGIO", ""),
                city=p.get("ORT01", ""),
                address=p.get("STRAS", ""),
                postal_code=p.get("PSTLZ", ""),
            )
            session.add(site)
            session.flush()
            site_id_map[f"PLANT-{werks}"] = site.id
            print(f"    Site: {site.name} ({master_type}, id={site.id})")

        # Vendor sites (MARKET_SUPPLY) — top 50 by PO count
        vendor_po_count = defaultdict(int)
        for po in po_headers:
            if po.get("LIFNR"):
                vendor_po_count[po["LIFNR"]] += 1
        top_vendors = sorted(vendor_ids, key=lambda v: vendor_po_count.get(v, 0), reverse=True)[:50]

        for lifnr in top_vendors:
            vname = vendor_name_map.get(lifnr, f"Vendor {strip_leading_zeros(lifnr)}")
            site = Site(
                config_id=config_id,
                name=vname,
                site_id=f"VENDOR-{strip_leading_zeros(lifnr)}",
                master_type="MARKET_SUPPLY",
                sc_site_type="Supplier",
                dag_type="MARKET_SUPPLY",
                description=f"SAP Vendor {lifnr}",
            )
            session.add(site)
            session.flush()
            site_id_map[f"VENDOR-{lifnr}"] = site.id

        print(f"    Created {len(top_vendors)} supplier sites")

        # Customer sites (MARKET_DEMAND) — top 50 by order count
        cust_order_count = defaultdict(int)
        for so in sales_orders:
            if so.get("KUNNR"):
                cust_order_count[so["KUNNR"]] += 1
        top_customers = sorted(customer_ids, key=lambda c: cust_order_count.get(c, 0), reverse=True)[:50]

        for kunnr in top_customers:
            cname = customer_name_map.get(kunnr, f"Customer {strip_leading_zeros(kunnr)}")
            site = Site(
                config_id=config_id,
                name=cname,
                site_id=f"CUST-{strip_leading_zeros(kunnr)}",
                master_type="MARKET_DEMAND",
                sc_site_type="Customer",
                dag_type="MARKET_DEMAND",
                description=f"SAP Customer {kunnr}",
            )
            session.add(site)
            session.flush()
            site_id_map[f"CUST-{kunnr}"] = site.id

        print(f"    Created {len(top_customers)} customer sites")

        # --- Products ---
        product_id_map: Dict[str, str] = {}  # MATNR → product.id (String PK)

        for matnr in active_materials:
            desc = desc_map.get(matnr, "")
            val = val_map.get(matnr, {})
            mara = next((m for m in materials if m["MATNR"] == matnr), {})

            product_name = desc or strip_leading_zeros(matnr)
            unit_cost = safe_float(val.get("VERPR") or val.get("STPRS"), 0.0)
            peinh = safe_float(val.get("PEINH"), 1.0) or 1.0
            if unit_cost > 0 and peinh > 0:
                unit_cost = unit_cost / peinh

            product = Product(
                id=strip_leading_zeros(matnr),
                description=product_name,
                base_uom=mara.get("MEINS", "EA"),
                product_group_name=mara.get("MATKL", ""),
                unit_cost=round(unit_cost, 4) if unit_cost > 0 else None,
                config_id=config_id,
            )
            session.add(product)
            session.flush()
            product_id_map[matnr] = product.id

        print(f"    Created {len(product_id_map)} products")

        # --- Transportation Lanes ---
        lane_count = 0

        # Vendor → Plant lanes (from POs)
        vendor_plant_pairs: Set[Tuple[str, str]] = set()
        for po in po_headers:
            lifnr = po.get("LIFNR", "")
            if f"VENDOR-{lifnr}" in site_id_map:
                # Find plant from PO items
                for pi in po_items:
                    if pi["EBELN"] == po["EBELN"] and pi.get("WERKS"):
                        pkey = f"PLANT-{pi['WERKS']}"
                        if pkey in site_id_map:
                            vendor_plant_pairs.add((f"VENDOR-{lifnr}", pkey))

        for vkey, pkey in vendor_plant_pairs:
            lane = TransportationLane(
                config_id=config_id,
                from_site_id=site_id_map[vkey],
                to_site_id=site_id_map[pkey],
                lane_type="PROCUREMENT",
                supply_lead_time={"mean": 7, "std": 2, "distribution": "lognormal"},
                capacity=10000,
            )
            session.add(lane)
            lane_count += 1

        # Plant → Customer lanes (from deliveries)
        plant_cust_pairs: Set[Tuple[str, str]] = set()
        for d in deliveries:
            kunnr = d.get("KUNNR", "")
            vstel = d.get("VSTEL", "")
            ckey = f"CUST-{kunnr}"
            # Shipping point often maps to plant
            pkey = f"PLANT-{vstel}" if f"PLANT-{vstel}" in site_id_map else None
            if not pkey:
                # Use first plant
                pkey = next((k for k in site_id_map if k.startswith("PLANT-")), None)
            if pkey and ckey in site_id_map:
                plant_cust_pairs.add((pkey, ckey))

        for pkey, ckey in plant_cust_pairs:
            lane = TransportationLane(
                config_id=config_id,
                from_site_id=site_id_map[pkey],
                to_site_id=site_id_map[ckey],
                lane_type="DISTRIBUTION",
                supply_lead_time={"mean": 3, "std": 1, "distribution": "lognormal"},
                capacity=10000,
            )
            session.add(lane)
            lane_count += 1

        session.flush()
        print(f"    Created {lane_count} transportation lanes")

        # --- Product BOMs ---
        bom_count = 0
        # Build BOM header → material map
        bom_header_material: Dict[str, str] = {}
        for mp in mat_plant:
            # MARC may have STLNR via join; we'll match via STKO
            pass
        # STKO has STLNR, STPO has STLNR+IDNRK (component)
        # We need parent material: typically from MAST (not extracted) or MARC
        # Use STPO.IDNRK as component, match STKO.STLNR to parent via material
        # Simplified: create BOMs from STPO where both parent and component are in our product set
        bom_by_header: Dict[str, List[Dict]] = defaultdict(list)
        for item in bom_items:
            bom_by_header[item["STLNR"]].append(item)

        # Try to map BOM header numbers to parent materials via prod orders
        for po in prod_orders:
            plnbez = po.get("PLNBEZ", "")
            if plnbez in product_id_map:
                # Find components from reservations
                pass

        # Direct approach: use AFPO (prod order items) + RESB (reservations) for BOM-like data
        reservations = read_csv(csv_dir, "RESB_reservations.csv")
        parent_component_qty: Dict[Tuple[str, str], float] = {}
        for res in reservations:
            aufnr = res.get("AUFNR", "")
            matnr_comp = res.get("MATNR", "")
            bdmng = safe_float(res.get("BDMNG", "0"))
            # Find parent from prod order
            parent = next((po.get("PLNBEZ") for po in prod_orders if po.get("AUFNR") == aufnr), None)
            if parent and parent in product_id_map and matnr_comp in product_id_map and parent != matnr_comp:
                key = (parent, matnr_comp)
                if key not in parent_component_qty:
                    parent_component_qty[key] = bdmng
                else:
                    parent_component_qty[key] = max(parent_component_qty[key], bdmng)

        for (parent_matnr, comp_matnr), qty in parent_component_qty.items():
            if qty <= 0:
                qty = 1.0
            bom = ProductBOM(
                parent_product_id=product_id_map[parent_matnr],
                component_product_id=product_id_map[comp_matnr],
                quantity_per=round(qty, 4),
                config_id=config_id,
            )
            session.add(bom)
            bom_count += 1

        session.flush()
        print(f"    Created {bom_count} BOM entries")

        # --- Inventory Levels ---
        inv_count = 0
        today = date.today()
        for s in stock:
            matnr = s["MATNR"]
            werks = s["WERKS"]
            pkey = f"PLANT-{werks}"
            if matnr in product_id_map and pkey in site_id_map:
                on_hand = safe_float(s.get("LABST", "0"))
                in_transit = safe_float(s.get("UMLME", "0"))
                quality_insp = safe_float(s.get("INSME", "0"))

                inv = InvLevel(
                    product_id=product_id_map[matnr],
                    site_id=site_id_map[pkey],
                    config_id=config_id,
                    inventory_date=today,
                    on_hand_qty=on_hand,
                    in_transit_qty=in_transit,
                    on_order_qty=0.0,
                    allocated_qty=0.0,
                    available_qty=on_hand,
                    backorder_qty=0.0,
                    safety_stock_qty=0.0,
                    source="SAP_IDES_IMPORT",
                    source_event_id="INITIAL_LOAD",
                    source_update_dttm=datetime.utcnow(),
                )
                session.add(inv)
                inv_count += 1

        session.flush()
        print(f"    Created {inv_count} inventory level records")

        # --- Inventory Policies (DOC-based safety stock) ---
        policy_count = 0
        for mp in mat_plant:
            matnr = mp["MATNR"]
            werks = mp["WERKS"]
            pkey = f"PLANT-{werks}"
            if matnr in product_id_map and pkey in site_id_map:
                eisbe = safe_float(mp.get("EISBE", "0"))  # Safety stock
                minbe = safe_float(mp.get("MINBE", "0"))  # Reorder point
                if eisbe > 0 or minbe > 0:
                    policy = InvPolicy(
                        product_id=product_id_map[matnr],
                        site_id=site_id_map[pkey],
                        config_id=config_id,
                        policy_type="abs_level",
                        ss_quantity=eisbe if eisbe > 0 else minbe,
                        target_dos=0,
                        service_level=0.95,
                        review_period_days=7,
                        source="SAP_IDES_IMPORT",
                    )
                    session.add(policy)
                    policy_count += 1

        session.flush()
        print(f"    Created {policy_count} inventory policies")

        # --- Sourcing Rules ---
        sr_count = 0
        for sl in source_list:
            matnr = sl["MATNR"]
            werks = sl["WERKS"]
            lifnr = sl.get("LIFNR", "")
            pkey = f"PLANT-{werks}"
            vkey = f"VENDOR-{lifnr}"
            if matnr in product_id_map and pkey in site_id_map and vkey in site_id_map:
                rule = SourcingRule(
                    product_id=product_id_map[matnr],
                    site_id=site_id_map[pkey],
                    config_id=config_id,
                    source_type="buy",
                    source_site_id=site_id_map[vkey],
                    priority=safe_int(sl.get("ZEORD", "1")),
                    split_percentage=100.0,
                    effective_start=parse_sap_date(sl.get("VDATU", "")) or today,
                    effective_end=parse_sap_date(sl.get("BDATU", "")),
                    source_field="SAP_IDES_IMPORT",
                )
                session.add(rule)
                sr_count += 1

        session.flush()
        print(f"    Created {sr_count} sourcing rules")

        # --- Outbound Orders (from SAP Sales Orders) ---
        ob_count = 0
        so_map = {so["VBELN"]: so for so in sales_orders}
        first_plant_id = next((site_id_map[k] for k in site_id_map if k.startswith("PLANT-")), None)

        for item in sales_items:
            vbeln = item["VBELN"]
            matnr = item.get("MATNR", "")
            werks = item.get("WERKS", "")
            so = so_map.get(vbeln, {})
            kunnr = so.get("KUNNR", "")
            ckey = f"CUST-{kunnr}"
            pkey = f"PLANT-{werks}"

            if matnr not in product_id_map:
                continue
            site_id = site_id_map.get(pkey, first_plant_id)
            if not site_id:
                continue

            order_date = parse_sap_date(so.get("ERDAT", ""))
            delivery_date = parse_sap_date(so.get("VDATU", "")) or order_date

            # Map SAP overall status (GBSTK) to Autonomy status
            ob_status = gbstk_to_outbound_status(so.get("GBSTK", "A"))

            ob = OutboundOrderLine(
                order_id=f"SAP-SO-{vbeln}",
                line_number=safe_int(item.get("POSNR", "1")),
                product_id=product_id_map[matnr],
                site_id=site_id,
                ordered_quantity=safe_float(item.get("KWMENG", "0")),
                requested_delivery_date=delivery_date,
                order_date=order_date or today,
                config_id=config_id,
                status=ob_status,
                priority_code="STANDARD",
                market_demand_site_id=site_id_map.get(ckey),
            )
            session.add(ob)
            ob_count += 1
            if ob_count >= 5000:
                break  # Cap to avoid overwhelming the DB on first load

        session.flush()
        print(f"    Created {ob_count} outbound order lines")

        # --- Inbound Orders (from SAP Purchase Orders) ---
        ib_count = 0
        for po in po_headers:
            ebeln = po["EBELN"]
            lifnr = po.get("LIFNR", "")
            vkey = f"VENDOR-{lifnr}"
            if vkey not in site_id_map:
                continue

            order_date = parse_sap_date(po.get("BEDAT", ""))
            # Get items
            items_for_po = [pi for pi in po_items if pi["EBELN"] == ebeln]
            if not items_for_po:
                continue

            first_item = items_for_po[0]
            werks = first_item.get("WERKS", "")
            pkey = f"PLANT-{werks}"
            dest_site_id = site_id_map.get(pkey, first_plant_id)
            if not dest_site_id:
                continue

            total_qty = sum(safe_float(pi.get("MENGE", "0")) for pi in items_for_po)

            # Determine PO-level status from line items' ELIKZ
            all_received = all(pi.get("ELIKZ") == "X" for pi in items_for_po)
            any_received = any(pi.get("ELIKZ") == "X" for pi in items_for_po)
            if all_received:
                ib_status = "RECEIVED"
            elif any_received:
                ib_status = "PARTIALLY_RECEIVED"
            else:
                ib_status = "CONFIRMED"

            ib_order = InboundOrder(
                id=f"SAP-PO-{ebeln}",
                order_type="PURCHASE",
                supplier_name=vendor_name_map.get(lifnr, f"Vendor {lifnr}"),
                ship_from_site_id=site_id_map[vkey],
                ship_to_site_id=dest_site_id,
                status=ib_status,
                order_date=order_date or today,
                total_ordered_qty=total_qty,
                source="SAP_IDES_IMPORT",
                source_event_id=f"PO-{ebeln}",
                source_update_dttm=datetime.utcnow(),
            )
            session.add(ib_order)

            for pi in items_for_po:
                matnr = pi.get("MATNR", "")
                if matnr not in product_id_map:
                    continue

                line_status = elikz_to_inbound_status(pi.get("ELIKZ", ""))

                ib_line = InboundOrderLine(
                    order_id=f"SAP-PO-{ebeln}",
                    line_number=safe_int(pi.get("EBELP", "1")),
                    product_id=product_id_map[matnr],
                    site_id=dest_site_id,
                    ordered_quantity=safe_float(pi.get("MENGE", "0")),
                    status=line_status,
                    source="SAP_IDES_IMPORT",
                )
                session.add(ib_line)

            ib_count += 1
            if ib_count >= 2000:
                break

        session.flush()
        print(f"    Created {ib_count} inbound orders (POs)")

        # --- Forecasts (from SAP Planned Independent Requirements if available) ---
        fc_count = 0
        pir_used = False

        if pir_schedule and pir_header_map:
            # Use real SAP PIR data (PBIM/PBED) for forecasts
            for sched in pir_schedule:
                bdzei = sched.get("BDZEI", "")
                header = pir_header_map.get(bdzei)
                if not header:
                    continue

                matnr = header.get("MATNR", "")
                werks = header.get("WERKS", "")
                pkey = f"PLANT-{werks}"

                if matnr not in product_id_map or pkey not in site_id_map:
                    continue

                fc_date = parse_sap_date(sched.get("PDATU", ""))
                qty = safe_float(sched.get("PLNMG", "0"))
                if not fc_date or qty <= 0:
                    continue

                # PIR provides planned quantity; estimate P10/P90 at ±20% CV
                std = max(qty * 0.2, 1.0)
                fc = Forecast(
                    product_id=product_id_map[matnr],
                    site_id=site_id_map[pkey],
                    config_id=config_id,
                    forecast_date=fc_date,
                    forecast_quantity=round(qty, 2),
                    p10_quantity=round(max(0, qty - 1.28 * std), 2),
                    p50_quantity=round(qty, 2),
                    p90_quantity=round(qty + 1.28 * std, 2),
                    source="SAP_IDES_PIR",
                )
                session.add(fc)
                fc_count += 1

            if fc_count > 0:
                pir_used = True

        if not pir_used:
            # Fallback: synthetic forecasts from sales history
            product_monthly_demand: Dict[str, List[float]] = defaultdict(list)
            for item in sales_items:
                matnr = item.get("MATNR", "")
                qty = safe_float(item.get("KWMENG", "0"))
                if matnr in product_id_map and qty > 0:
                    product_monthly_demand[matnr].append(qty)

            for matnr, qtys in product_monthly_demand.items():
                if not qtys:
                    continue
                avg_weekly = sum(qtys) / max(len(qtys), 1)
                std_weekly = max(avg_weekly * 0.2, 1.0)

                for week in range(12):
                    fc_date = today + timedelta(weeks=week)
                    fc = Forecast(
                        product_id=product_id_map[matnr],
                        site_id=first_plant_id,
                        config_id=config_id,
                        forecast_date=fc_date,
                        forecast_quantity=round(avg_weekly, 2),
                        p10_quantity=round(max(0, avg_weekly - 1.28 * std_weekly), 2),
                        p50_quantity=round(avg_weekly, 2),
                        p90_quantity=round(avg_weekly + 1.28 * std_weekly, 2),
                        source="SAP_IDES_IMPORT",
                    )
                    session.add(fc)
                    fc_count += 1

        session.flush()
        fc_source = "SAP PIR (PBIM/PBED)" if pir_used else "synthetic (sales history)"
        print(f"    Created {fc_count} forecast records ({fc_source})")

        # --- Production Orders (from AFKO/AFPO with JEST status mapping) ---
        mo_count = 0
        comp_count = 0

        for po in prod_orders:
            aufnr = po.get("AUFNR", "")
            plnbez = po.get("PLNBEZ", "")  # Planned material

            if plnbez not in product_id_map:
                continue

            # Find plant from AFPO or mat_plant
            afpo_item = next(
                (pi for pi in prod_order_items if pi.get("AUFNR") == aufnr),
                None,
            )
            werks = mat_plant_lookup(mat_plant, plnbez)
            if not werks:
                werks = next(iter(plant_map), None)
            pkey = f"PLANT-{werks}" if werks else None
            if not pkey or pkey not in site_id_map:
                continue

            # Map JEST status
            objnr = aufnr_to_objnr(aufnr)
            statuses = objnr_statuses.get(objnr, set())
            mo_status = jest_to_production_status(statuses)

            # Quantities from AFPO
            planned_qty = safe_float(po.get("GAMNG", "1")) or 1.0
            actual_qty = None
            if afpo_item:
                wemng = safe_float(afpo_item.get("WEMNG", "0"))
                if wemng > 0:
                    actual_qty = int(wemng)
                pq = safe_float(afpo_item.get("PSMNG", "0"))
                if pq > 0:
                    planned_qty = pq

            # Dates
            start_date = parse_sap_date(po.get("GSTRS", "")) or parse_sap_date(po.get("GSTRP", ""))
            end_date = parse_sap_date(po.get("GLTRP", "")) or parse_sap_date(po.get("GLTRS", ""))
            if not start_date:
                start_date = today
            if not end_date:
                end_date = start_date + timedelta(days=7)

            mo = ProductionOrder(
                order_number=f"SAP-MO-{strip_leading_zeros(aufnr)}",
                item_id=product_id_map[plnbez],
                site_id=site_id_map[pkey],
                config_id=config_id,
                planned_quantity=int(planned_qty),
                actual_quantity=actual_qty,
                status=mo_status,
                planned_start_date=datetime.combine(start_date, datetime.min.time()),
                planned_completion_date=datetime.combine(end_date, datetime.min.time()),
                lead_time_planned=max(1, (end_date - start_date).days),
                priority=5,
                notes=f"JEST statuses: {','.join(sorted(statuses))}" if statuses else None,
                extra_data={"sap_aufnr": aufnr, "sap_objnr": objnr},
            )
            session.add(mo)
            session.flush()
            mo_count += 1

            # Add components from RESB reservations
            for res in reservations:
                if res.get("AUFNR") != aufnr:
                    continue
                comp_matnr = res.get("MATNR", "")
                if comp_matnr not in product_id_map or comp_matnr == plnbez:
                    continue
                comp = ProductionOrderComponent(
                    production_order_id=mo.id,
                    component_item_id=product_id_map[comp_matnr],
                    planned_quantity=safe_float(res.get("BDMNG", "1")),
                    unit_of_measure=res.get("MEINS", "EA"),
                )
                session.add(comp)
                comp_count += 1

        session.flush()
        print(f"    Created {mo_count} production orders ({comp_count} components)")

        # --- Quality Orders (from QALS inspection lots) ---
        qo_count = 0
        for ql in inspection_lots:
            matnr = ql.get("MATNR", "")
            werks = ql.get("WERK", "")
            pkey = f"PLANT-{werks}"

            if matnr not in product_id_map or pkey not in site_id_map:
                continue

            prueflos = ql.get("PRUEFLOS", "")
            art = ql.get("ART", "01")
            herkunft = ql.get("HERKUNFT", "")

            # Map inspection origin
            origin_map = {
                "01": ("INCOMING", "GOODS_RECEIPT"),
                "02": ("IN_PROCESS", "PRODUCTION_ORDER"),
                "03": ("FINAL", "PRODUCTION_ORDER"),
                "04": ("RETURNS", "CUSTOMER_COMPLAINT"),
                "05": ("SAMPLING", "PREVENTIVE_SAMPLE"),
            }
            insp_type, origin_type = origin_map.get(art, ("INCOMING", "GOODS_RECEIPT"))

            # Status from BEARBSTATU (processing status)
            bearbstatu = ql.get("BEARBSTATU", "")
            if bearbstatu:
                qo_status = "IN_INSPECTION"
            else:
                qo_status = "CREATED"
            # Check for INSMK (stock posting indicator — if set, disposition was made)
            if ql.get("INSMK"):
                qo_status = "DISPOSITION_DECIDED"

            create_date = parse_sap_date(ql.get("ENSTEHDAT", ""))

            qo = QualityOrder(
                quality_order_number=f"SAP-QI-{strip_leading_zeros(prueflos)}",
                site_id=site_id_map[pkey],
                config_id=config_id,
                tenant_id=tenant_id,
                inspection_type=insp_type,
                status=qo_status,
                origin_type=origin_type,
                origin_order_id=ql.get("AUFNR", ""),
                product_id=product_id_map[matnr],
                lot_number=ql.get("CHARG", ""),
                inspection_quantity=safe_float(ql.get("LOSMENGE", "0")),
                source="SAP_IDES_IMPORT",
                source_event_id=f"QALS-{prueflos}",
                source_update_dttm=datetime.utcnow(),
            )
            if create_date:
                qo.created_at = datetime.combine(create_date, datetime.min.time())
            session.add(qo)
            qo_count += 1

        session.flush()
        print(f"    Created {qo_count} quality orders")

        # -----------------------------------------------------------------------
        # Phase 4: Commit
        # -----------------------------------------------------------------------
        session.commit()
        print(f"\n{'='*60}")
        print(f"SUCCESS: Ingestion complete!")
        print(f"  Tenant ID: {tenant_id}")
        print(f"  Config ID: {config_id}")
        print(f"  Sites: {len(site_id_map)}")
        print(f"  Products: {len(product_id_map)}")
        print(f"  Lanes: {lane_count}")
        print(f"  BOMs: {bom_count}")
        print(f"  Inventory: {inv_count}")
        print(f"  Policies: {policy_count}")
        print(f"  Sourcing rules: {sr_count}")
        print(f"  Outbound orders: {ob_count} (status from VBAK.GBSTK)")
        print(f"  Inbound orders: {ib_count} (status from EKPO.ELIKZ)")
        print(f"  Forecasts: {fc_count} ({fc_source})")
        print(f"  Production orders: {mo_count} (status from JEST)")
        print(f"  Quality orders: {qo_count}")
        print(f"{'='*60}")
        print(f"\nTo run the SAP Change Simulator:")
        print(f"  curl -X POST http://localhost:8000/api/v1/sap-simulator/create \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"config_id\": {config_id}, \"tenant_id\": {tenant_id}, \"clock_speed\": \"100x\", \"scenario\": \"steady_state\"}}'")
        print(f"\n  curl -X POST http://localhost:8000/api/v1/sap-simulator/tick \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"num_ticks\": 7}}'")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()
        engine.dispose()


def mat_plant_lookup(mat_plant: List[Dict], matnr: str) -> Optional[str]:
    """Find which plant a material belongs to."""
    for mp in mat_plant:
        if mp["MATNR"] == matnr:
            return mp["WERKS"]
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest SAP IDES CSVs into an existing Autonomy tenant",
        epilog=(
            "Prerequisites:\n"
            "  1. Systemadmin creates the tenant and tenant admin via the UI\n"
            "  2. Tenant admin logs in and runs this script with --tenant-id\n"
            "\n"
            "Example:\n"
            "  python scripts/ingest_sap_csvs.py --tenant-id 4\n"
            "  python scripts/ingest_sap_csvs.py --tenant-id 4 --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        required=True,
        help="ID of the existing tenant to load SAP data into",
    )
    parser.add_argument(
        "--csv-dir",
        default="imports/SAP/IDES_1710",
        help="Path to CSV directory (default: imports/SAP/IDES_1710)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't write to DB")
    args = parser.parse_args()

    csv_path = Path(args.csv_dir)
    if not csv_path.is_absolute():
        csv_path = Path(__file__).resolve().parent.parent / csv_path

    if not csv_path.exists():
        print(f"ERROR: CSV directory not found: {csv_path}")
        sys.exit(1)

    ingest(csv_path, tenant_id=args.tenant_id, dry_run=args.dry_run)

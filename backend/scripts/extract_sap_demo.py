#!/usr/bin/env python3
"""
Extract SAP S/4HANA Demo Data via TMS ERP Integration Framework

Uses the proper TMSExtractionAdapter → SAPTMAdapter → CSV path to extract
the SAP demo data and persist it into TMS staging tables under a dedicated
SAP LEARNING tenant.

The SAP demo CSVs are real SAP table exports from an S/4HANA 2025 system:
- Core (shared): T001W (plants→Sites), KNA1 (customers→Sites),
  LFA1 (vendors→Carriers), MARA/MAKT (materials→Commodities)
- TMS (freight): LIKP/LIPS (deliveries→Shipments), EKKO/EKPO
  (contracts→CarrierContracts)

This exercises the same TMSExtractionAdapter contract a production SAP TM
deployment would use (with RFC or OData instead of CSV).

Prerequisites:
    - SAP demo CSV directory mounted at /app/data/sap_demo
    - TMS database running

Usage:
    docker compose exec backend python scripts/extract_sap_demo.py
"""
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.tenant import Tenant, TenantMode, ClockMode
from app.models.user import User
from app.integrations.sap.tms_extractor import SAPTMAdapter, SAPTMConnectionConfig
from app.integrations.core.tms_adapter import ExtractionMode
from app.services.tms.scp_etl import (
    tms_src_scp_config, tms_src_scp_site, tms_src_scp_shipment,
    tms_src_scp_product, tms_src_scp_trading_partner, tms_src_scp_lane,
    create_staging_tables,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("extract_sap_demo")

SAP_TENANT_NAME = "SAP S/4HANA Demo (LEARNING)"
SAP_TENANT_SLUG = "sap-s4hana-demo"
CSV_DIR = "/app/data/sap_demo"


def get_or_create_sap_tenant(session) -> Tenant:
    tenant = session.execute(
        select(Tenant).where(Tenant.slug == SAP_TENANT_SLUG)
    ).scalar_one_or_none()
    if tenant:
        logger.info("Existing SAP tenant: id=%d", tenant.id)
        return tenant

    admin = session.execute(
        select(User).where(User.email == "systemadmin@sap-demo.local")
    ).scalar_one_or_none()
    if admin is None:
        admin = User(
            email="systemadmin@sap-demo.local",
            username="systemadmin_sap",
            full_name="SAP Demo System Admin",
            hashed_password="!",
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        session.flush()

    tenant = Tenant(
        name=SAP_TENANT_NAME,
        slug=SAP_TENANT_SLUG,
        subdomain=SAP_TENANT_SLUG,
        admin_id=admin.id,
        mode=TenantMode.LEARNING,
        time_mode=ClockMode.TURN_BASED,
        industry="manufacturing",
    )
    session.add(tenant)
    session.flush()
    session.execute(
        text("UPDATE users SET tenant_id = :tid WHERE id = :uid"),
        {"tid": tenant.id, "uid": admin.id},
    )
    session.commit()
    logger.info("Created SAP tenant: id=%d", tenant.id)
    return tenant


def persist_to_staging(session, adapter: SAPTMAdapter):
    """
    Persist SAP-extracted records into TMS staging tables.

    Uses the same tms_src_scp_* staging tables as the Food Dist ETL —
    the tables are source-agnostic despite the 'scp' prefix. A future
    cleanup should rename to tms_erp_staging_*.
    """
    from datetime import datetime

    SAP_CONFIG_ID = 188  # Matches SCP-side SAP config; scopes SAP staging data

    # Sites (plants + customers)
    sites = adapter._extract_sites_from_csv()
    site_rows = []
    for i, s in enumerate(sites):
        site_rows.append({
            "scp_site_id": i + 10000,
            "scp_config_id": SAP_CONFIG_ID,
            "name": s["name"],
            "type": s["type"],
            "master_type": s["type"],
            "is_external": 1 if s["type"] == "MARKET_DEMAND" else 0,
            "latitude": None,
            "longitude": None,
            "attributes": {"country": s.get("country"), "city": s.get("city"),
                           "sap_code": s.get("site_code"), "_source": "sap_csv"},
        })
    if site_rows:
        session.execute(tms_src_scp_site.insert(), site_rows)
    logger.info(f"Staged {len(site_rows)} sites")

    # Trading partners (carriers from LFA1)
    carriers = adapter._extract_carriers_from_csv()
    tp_rows = []
    for i, c in enumerate(carriers):
        tp_rows.append({
            "scp_partner_id": i + 20000,
            "scp_config_id": SAP_CONFIG_ID,
            "name": c["name"],
            "partner_type": "carrier",
            "postal_code": None,
            "country": c.get("country"),
        })
    if tp_rows:
        session.execute(tms_src_scp_trading_partner.insert(), tp_rows)
    logger.info(f"Staged {len(tp_rows)} carriers/trading partners")

    # Products (materials from MARA/MAKT — deduplicate by material number)
    materials = adapter._extract_materials_from_csv()
    seen_materials = set()
    prod_rows = []
    for m in materials:
        mid = m["material_number"]
        if mid in seen_materials:
            continue
        seen_materials.add(mid)
        temp_cat = "dry"  # Industrial parts are always ambient
        prod_rows.append({
            "scp_product_id": f"SAP_{mid}",
            "scp_config_id": SAP_CONFIG_ID,
            "name": m["description"],
            "product_group": m.get("material_group"),
            "temperature_category": temp_cat,
            "unit_size": m.get("base_uom"),
            "cases_per_pallet": None,
            "attributes": {"material_type": m.get("material_type"),
                           "gross_weight": m.get("gross_weight"),
                           "weight_uom": m.get("weight_uom")},
        })
    if prod_rows:
        session.execute(tms_src_scp_product.insert(), prod_rows)
    logger.info(f"Staged {len(prod_rows)} products/materials")

    # Build plant-code → site-id lookup for shipment mapping
    # Also map by shipping point (VSTEL) — SAP LIKP uses VSTEL, not WERKS.
    # VSTEL typically shares digits with the plant code.
    plant_to_site = {}
    for s in site_rows:
        code = (s["attributes"] or {}).get("sap_code", "")
        if code:
            plant_to_site[code] = s["scp_site_id"]
            # Also register the 4-digit prefix as a VSTEL lookup
            # (SAP shipping points map to plants by first 4 digits)
            if len(code) >= 4:
                plant_to_site[code[:4]] = s["scp_site_id"]

    # Shipments (deliveries from LIKP/LIPS)
    shipments = adapter._extract_shipments_from_csv(since=None, mode=ExtractionMode.HISTORICAL)
    ship_rows = []
    for s in shipments:
        # LIKP uses VSTEL (shipping point), not WERKS (plant)
        origin_key = s.get("origin_plant") or s.get("carrier_vendor", "")
        from_site = plant_to_site.get(origin_key)
        # Also try shipping_type as VSTEL proxy
        if from_site is None:
            from_site = plant_to_site.get(s.get("shipping_type", ""))
        to_site = plant_to_site.get(f"CUST_{s.get('destination_customer')}")
        ship_rows.append({
            "scp_shipment_id": f"SAP_{s['shipment_number']}",
            "scp_config_id": SAP_CONFIG_ID,
            "scp_order_id": s["shipment_number"],
            "scp_product_id": f"SAP_{s['items'][0]['material']}" if s.get("items") else None,
            "quantity": s["items"][0]["quantity"] if s.get("items") else 0,
            "uom": s["items"][0]["uom"] if s.get("items") else "EA",
            "from_site_id": from_site,
            "to_site_id": to_site,
            "scp_lane_id": None,
            "status": s["status"],
            "ship_date": s.get("ship_date"),
            "expected_delivery_date": s.get("planned_delivery_date"),
            "actual_delivery_date": s.get("actual_delivery_date"),
            "scp_carrier_id": s.get("carrier_vendor"),
            "scp_carrier_name": None,
        })
    if ship_rows:
        BATCH = 1000
        for i in range(0, len(ship_rows), BATCH):
            session.execute(tms_src_scp_shipment.insert(), ship_rows[i:i + BATCH])
    logger.info(f"Staged {len(ship_rows)} shipments")

    session.commit()
    return {
        "sites": len(site_rows),
        "carriers": len(tp_rows),
        "products": len(prod_rows),
        "shipments": len(ship_rows),
    }


async def run_extraction():
    csv_dir = Path(CSV_DIR)

    config = SAPTMConnectionConfig(
        tenant_id=0,
        connection_name="SAP S/4HANA 2025 Demo (CSV)",
        preferred_method="csv",
        csv_directory=str(csv_dir),
    )

    adapter = SAPTMAdapter(config)
    logger.info("Connecting to SAP CSV data at %s...", csv_dir)
    connected = await adapter.connect()
    if not connected:
        raise SystemExit("Failed to connect to SAP CSV data")

    Session = sessionmaker(bind=sync_engine, expire_on_commit=False)
    with Session() as session:
        logger.info("Creating SAP LEARNING tenant...")
        tenant = get_or_create_sap_tenant(session)

        logger.info("Ensuring staging tables exist...")
        create_staging_tables(sync_engine)

        logger.info("Persisting SAP data to TMS staging...")
        stats = persist_to_staging(session, adapter)

    await adapter.disconnect()
    logger.info("Done. SAP demo extraction complete: %s", stats)


if __name__ == "__main__":
    asyncio.run(run_extraction())

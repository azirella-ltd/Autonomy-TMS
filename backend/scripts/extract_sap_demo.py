#!/usr/bin/env python3
"""
Extract SAP S/4HANA Demo Data via TMS ERP Integration Framework

Uses the proper TMSExtractionAdapter → SAPTMAdapter → CSV path to extract
the SAP demo data from CSV files into TMS staging tables. This exercises
the same integration framework that a real SAP S/4HANA customer deployment
would use (with RFC or OData instead of CSV).

The SAP demo CSVs are real SAP table exports (LIKP, LIPS, LFA1, T001W,
KNA1, MARA, MAKT, etc.) from an S/4HANA 2025 system.

Prerequisites:
    - SAP demo CSV directory accessible (via mount or local path)
    - TMS database running

Usage (inside backend container):
    docker compose exec backend python scripts/extract_sap_demo.py \\
        --csv-dir /data/sap_demo

    # Or with a mounted path from the host:
    docker compose exec backend python scripts/extract_sap_demo.py \\
        --csv-dir /app/data/sap_faa_backup/Autonomy_SAP_Demo
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.integrations.sap.tms_extractor import SAPTMAdapter, SAPTMConnectionConfig
from app.integrations.core.tms_adapter import ExtractionMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("extract_sap_demo")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", type=str, required=True,
                    help="Path to directory containing SAP table CSV files")
    ap.add_argument("--tenant-id", type=int, default=0,
                    help="TMS tenant ID for this extraction")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)
    if not csv_dir.exists():
        raise SystemExit(f"CSV directory does not exist: {csv_dir}")

    config = SAPTMConnectionConfig(
        tenant_id=args.tenant_id,
        connection_name="SAP S/4HANA 2025 Demo (CSV)",
        preferred_method="csv",
        csv_directory=str(csv_dir),
    )

    adapter = SAPTMAdapter(config)

    logger.info("Connecting via CSV loader...")
    connected = await adapter.connect()
    if not connected:
        raise SystemExit("Failed to connect to SAP CSV data")

    logger.info("Extracting shipments (LIKP/LIPS)...")
    ship_result = await adapter.extract_shipments(mode=ExtractionMode.HISTORICAL)
    logger.info(f"  Shipments: {ship_result.records_extracted} extracted, {ship_result.records_mapped} mapped")

    logger.info("Extracting sites (T001W + KNA1)...")
    sites = adapter._extract_sites_from_csv()
    logger.info(f"  Sites: {len(sites)} extracted")

    logger.info("Extracting carriers (LFA1)...")
    carriers = adapter._extract_carriers_from_csv()
    logger.info(f"  Carriers: {len(carriers)} extracted")

    logger.info("Extracting materials (MARA/MAKT)...")
    materials = adapter._extract_materials_from_csv()
    logger.info(f"  Materials: {len(materials)} extracted")

    await adapter.disconnect()

    logger.info("Done. SAP demo data extracted through TMS ERP integration framework.")
    logger.info(f"  Total: {ship_result.records_extracted} shipments, {len(sites)} sites, "
                f"{len(carriers)} carriers, {len(materials)} materials")


if __name__ == "__main__":
    asyncio.run(main())

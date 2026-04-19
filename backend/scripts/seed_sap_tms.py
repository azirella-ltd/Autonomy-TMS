#!/usr/bin/env python3
"""
Seed SAP S/4HANA TMS LEARNING Tenant

Creates the carrier network, equipment fleet, rates, and generates
TMS operational history (loads, tenders, tracking, exceptions) for
the SAP S/4HANA demo data extracted via extract_sap_demo.py.

Uses the global carrier seed (ocean/air/European road/Asian/intermodal)
instead of the US foodservice carriers.

Run AFTER: scripts/extract_sap_demo.py

Usage:
    docker compose exec backend python scripts/seed_sap_tms.py --seed-only
    docker compose exec backend python scripts/seed_sap_tms.py \\
        --start 2020-01-01 --end 2025-11-26
"""
import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.tenant import Tenant, TenantMode
from app.services.tms.food_dist_tms_overlay import FoodDistTMSOverlay, OverlayConfig
from app.services.tms.global_carriers_seed import GLOBAL_CARRIERS
from app.services.tms.carriers_seed import TOP_FOODSERVICE_CARRIERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("seed_sap_tms")

SAP_TENANT_SLUG = "sap-s4hana-demo"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=str, default="2020-01-01")
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--seed", type=int, default=20260419)
    return ap.parse_args()


def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = (datetime.strptime(args.end, "%Y-%m-%d").date()
           if args.end else date(2025, 11, 26))

    Session = sessionmaker(bind=sync_engine, expire_on_commit=False)
    with Session() as session:
        tenant = session.execute(
            select(Tenant).where(Tenant.slug == SAP_TENANT_SLUG)
        ).scalar_one_or_none()
        if not tenant:
            raise SystemExit(
                f"SAP tenant not found (slug='{SAP_TENANT_SLUG}'). "
                "Run scripts/extract_sap_demo.py first."
            )
        logger.info("SAP tenant: id=%d", tenant.id)

        # Verify staging has SAP data
        n_sites = session.execute(text(
            "SELECT COUNT(*) FROM tms_src_scp_site WHERE scp_site_id >= 10000"
        )).scalar()
        n_ships = session.execute(text(
            "SELECT COUNT(*) FROM tms_src_scp_shipment WHERE scp_shipment_id LIKE '%'"
            " AND scp_config_id = 0 AND from_site_id >= 10000"
        )).scalar() or 0
        # Broader check — SAP shipments have from_site_id >= 10000 or NULL
        n_ships_total = session.execute(text(
            "SELECT COUNT(*) FROM tms_src_scp_shipment WHERE scp_product_id LIKE 'SAP_%'"
        )).scalar()
        logger.info("SAP staging: %d sites, %d shipments (SAP-prefixed products: %d)",
                     n_sites, n_ships, n_ships_total)

        if n_sites == 0:
            raise SystemExit("No SAP sites in staging. Run extract_sap_demo.py first.")

        # Monkey-patch the carrier list for global network
        import app.services.tms.carriers_seed as cs_mod
        original_carriers = cs_mod.TOP_FOODSERVICE_CARRIERS
        cs_mod.TOP_FOODSERVICE_CARRIERS = GLOBAL_CARRIERS

        overlay = FoodDistTMSOverlay(
            session=session,
            tms_tenant_id=tenant.id,
            sc_config_id=0,
            config=OverlayConfig(random_seed=args.seed, staging_config_id=188),
        )

        logger.info("Phase 1 — seeding global carrier network...")
        overlay.seed_carrier_network()

        if args.seed_only:
            logger.info("--seed-only set; skipping history generation.")
            cs_mod.TOP_FOODSERVICE_CARRIERS = original_carriers
            return

        logger.info("Phase 2 — generating TMS history %s → %s ...", start, end)
        totals = overlay.generate_range(start, end)
        logger.info("Done. Totals: %s", totals)

        cs_mod.TOP_FOODSERVICE_CARRIERS = original_carriers


if __name__ == "__main__":
    main()

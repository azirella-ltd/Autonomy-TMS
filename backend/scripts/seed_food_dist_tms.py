#!/usr/bin/env python3
"""
Seed Food Dist TMS LEARNING Tenant

Creates a new `food_dist_tms` LEARNING tenant based on the existing
Food Dist SCP config, seeds the carrier network + equipment fleet +
rate cards, then synthesizes TMS operational history over the full
Food Dist date range.

Run AFTER:
    scripts/extract_scp_food_dist.py    # populates tms_src_scp_* staging from SCP DB

The SCP-side seed scripts (seed_food_dist_demo.py / _hierarchies.py /
_planning_data.py / _transactions.py) live in the SCP repo and run against
SCP's database, NOT here. After running them on SCP, re-run the extractor
above before this script.

Usage (inside backend container):
    docker compose exec backend python scripts/seed_food_dist_tms.py
    docker compose exec backend python scripts/seed_food_dist_tms.py \\
        --start 2023-01-01 --end 2023-06-30

    # Seed carriers only (no history generation):
    docker compose exec backend python scripts/seed_food_dist_tms.py --seed-only
"""
import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models.tenant import Tenant, TenantMode, ClockMode
from app.models.supply_chain_config import SupplyChainConfig
from sqlalchemy import text
from app.services.tms.food_dist_tms_overlay import FoodDistTMSOverlay, OverlayConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_food_dist_tms")


FOOD_DIST_SLUG = "food-dist"
TMS_TENANT_NAME = "Food Dist TMS (LEARNING)"
TMS_TENANT_SLUG = "food-dist-tms"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=str, default="2023-01-01",
                    help="History start date (YYYY-MM-DD)")
    ap.add_argument("--end", type=str, default=None,
                    help="History end date (YYYY-MM-DD); default = yesterday")
    ap.add_argument("--seed-only", action="store_true",
                    help="Only seed carriers/lanes/rates, skip daily history")
    ap.add_argument("--seed", type=int, default=20260414,
                    help="Random seed for reproducibility")
    return ap.parse_args()


def get_or_create_tms_tenant(session) -> Tenant:
    tenant = session.execute(
        select(Tenant).where(Tenant.slug == TMS_TENANT_SLUG)
    ).scalar_one_or_none()
    if tenant:
        logger.info("Existing TMS tenant: id=%d slug=%s", tenant.id, tenant.slug)
        return tenant

    tenant = Tenant(
        name=TMS_TENANT_NAME,
        slug=TMS_TENANT_SLUG,
        subdomain=TMS_TENANT_SLUG,
        mode=TenantMode.LEARNING,
        time_mode=ClockMode.TURN_BASED,
        industry="foodservice",
    )
    session.add(tenant)
    session.flush()
    logger.info("Created TMS tenant: id=%d slug=%s", tenant.id, tenant.slug)
    return tenant


def assert_staging_populated(session) -> None:
    """Sanity check: staging tables must exist and be non-empty."""
    try:
        n_sites = session.execute(text("SELECT COUNT(*) FROM tms_src_scp_site")).scalar()
        n_ships = session.execute(text("SELECT COUNT(*) FROM tms_src_scp_shipment")).scalar()
    except Exception as e:
        raise SystemExit(
            "tms_src_scp_* staging tables missing or unreadable. "
            "Run scripts/extract_scp_food_dist.py first."
        ) from e
    if not n_sites:
        raise SystemExit("tms_src_scp_site is empty — re-run extract_scp_food_dist.py.")
    logger.info("Staging populated: %d sites, %d shipments", n_sites, n_ships)


def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = (datetime.strptime(args.end, "%Y-%m-%d").date()
           if args.end else (date.today() - timedelta(days=1)))

    Session = sessionmaker(bind=sync_engine, expire_on_commit=False)
    with Session() as session:
        tms_tenant = get_or_create_tms_tenant(session)
        session.commit()

        assert_staging_populated(session)

        # Overlay materializes its own TMS-side SC config from staging on first
        # call to seed_carrier_network() — pass 0 here as a placeholder; it gets
        # overridden internally to point at the materialized "Food Dist (from SCP)"
        # config under the LEARNING tenant.
        overlay = FoodDistTMSOverlay(
            session=session,
            tms_tenant_id=tms_tenant.id,
            sc_config_id=0,
            config=OverlayConfig(random_seed=args.seed),
        )

        logger.info("Phase 1 — seeding carrier network, equipment fleet, rates...")
        overlay.seed_carrier_network()

        if args.seed_only:
            logger.info("--seed-only set; skipping history generation.")
            return

        logger.info("Phase 2 — generating daily TMS history %s → %s ...", start, end)
        totals = overlay.generate_range(start, end)
        logger.info("Done. Totals: %s", totals)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Extract Food Dist Demo from SCP into TMS staging tables.

Pulls SCP supply_chain_config + sites + lanes + trading partners + products +
shipments + order lines into `tms_src_scp_*` tables on the TMS database.

Reseed dependency: if SCP Food Dist is reseeded, this extractor must be re-run
before `seed_food_dist_tms.py` or the TMS overlay will reference stale SCP IDs.

Requires SCP_DB_URL env var (set in docker-compose.override.yml).

Usage (inside backend container):
    docker compose exec backend python scripts/extract_scp_food_dist.py
    docker compose exec backend python scripts/extract_scp_food_dist.py \\
        --config-name "Food Dist Demo"
"""
import argparse
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import sync_engine
from app.services.tms.scp_etl import (
    FoodDistExtractor, build_scp_engine, create_staging_tables,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("extract_scp_food_dist")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-name", default="Food Dist Distribution Network",
                    help="SCP supply chain config name to extract")
    args = ap.parse_args()

    if not settings.SCP_DB_URL:
        raise SystemExit(
            "SCP_DB_URL is not set. See docker-compose.override.yml — "
            "TMS backend needs to be on SCP's external Docker network "
            "(or pointed at SCP's host-exposed Postgres port)."
        )

    logger.info("Creating staging tables (idempotent)...")
    create_staging_tables(sync_engine)

    logger.info("Connecting to SCP read engine: %s",
                settings.SCP_DB_URL.split("@")[-1])
    scp_engine = build_scp_engine(settings.SCP_DB_URL)

    Session = sessionmaker(bind=sync_engine, expire_on_commit=False)
    with Session() as session:
        extractor = FoodDistExtractor(scp_engine, session,
                                       scp_config_name=args.config_name)
        stats = extractor.run()

    logger.info("Done: %s", stats)


if __name__ == "__main__":
    main()

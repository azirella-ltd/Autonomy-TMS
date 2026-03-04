#!/usr/bin/env python3
"""Seed TBG SC configs with Product, InvPolicy, and SourcingRules records.

Idempotent — skips records that already exist.

For each SupplyChainConfig whose name contains "TBG" (case-insensitive):
  1. Creates one Product  (id = TBG-CASES-{config_id})
  2. Creates one InvPolicy per INVENTORY/MANUFACTURER site
  3. Creates one SourcingRules per TransportationLane (transfer rule)

After seeding, Beer Game scenarios with use_sc_execution=True can be executed
entirely through the standard AWS SC execution layer.

Usage:
    # Inside the Docker container:
    docker compose exec backend python scripts/seed_tbg_sc_data.py

    # Targeting a specific config by ID:
    docker compose exec backend python scripts/seed_tbg_sc_data.py --config-id 22

    # With verbose output:
    docker compose exec backend python scripts/seed_tbg_sc_data.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import sync_engine
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import Product, InvPolicy, SourcingRules

logger = logging.getLogger(__name__)

# ── Beer Game constants ────────────────────────────────────────────────────────
# Classic TBG parameters from MIT Sloan / Sterman (1989)
TBG_INITIAL_INVENTORY = 12.0     # Starting inventory at each site (units)
TBG_SAFETY_STOCK = 4.0           # Abs-level safety stock target per site
TBG_ORDER_UP_TO = 12.0           # Base-stock order-up-to level
TBG_LEAD_TIME_WEEKS = 2          # 2-period lead time (supply_lead_time value)
TBG_UNIT_COST = 1.0              # Cost per unit (used for InvLevel valuation)
TBG_UNIT_PRICE = 1.5             # Selling price per unit
TBG_HOLDING_COST_RANGE = {"min": 0.5, "max": 0.5}
TBG_BACKLOG_COST_RANGE = {"min": 1.0, "max": 1.0}

# Master types that should receive inventory policies and sourcing rules
INVENTORY_MASTER_TYPES = {"inventory", "manufacturer"}


def _make_product_id(config_id: int) -> str:
    return f"TBG-CASES-{config_id}"


def seed_config(db: Session, config: SupplyChainConfig, verbose: bool = False) -> dict:
    """Seed one SupplyChainConfig with TBG SC data.

    Args:
        db: Synchronous SQLAlchemy session.
        config: The SupplyChainConfig to seed.
        verbose: Print per-record details.

    Returns:
        Summary dict with counts of created/skipped records.
    """
    summary = {
        "config_id": config.id,
        "config_name": config.name,
        "product": {"created": 0, "skipped": 0},
        "inv_policy": {"created": 0, "skipped": 0},
        "sourcing_rules": {"created": 0, "skipped": 0},
    }

    product_id = _make_product_id(config.id)

    # ── 1. Product ─────────────────────────────────────────────────────────────
    existing_product = db.query(Product).filter(Product.id == product_id).first()
    if existing_product:
        if verbose:
            logger.info(f"  ↳ Product {product_id}: SKIP (already exists)")
        summary["product"]["skipped"] += 1
    else:
        product = Product(
            id=product_id,
            description=f"Beer Game cases — config {config.id}",
            config_id=config.id,
            base_uom="CASES",
            unit_cost=TBG_UNIT_COST,
            unit_price=TBG_UNIT_PRICE,
            is_active="true",
        )
        db.add(product)
        if verbose:
            logger.info(f"  ↳ Product {product_id}: CREATED")
        summary["product"]["created"] += 1

    # Flush so the product FK is available for dependent records
    db.flush()

    # ── 2. InvPolicy per INVENTORY/MANUFACTURER site ───────────────────────────
    sites = (
        db.query(Site)
        .filter(Site.config_id == config.id)
        .all()
    )

    inventory_sites: List[Site] = [
        s for s in sites
        if (s.master_type or "").lower() in INVENTORY_MASTER_TYPES
    ]

    for site in inventory_sites:
        existing_policy = (
            db.query(InvPolicy)
            .filter(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site.id,
            )
            .first()
        )
        if existing_policy:
            if verbose:
                logger.info(
                    f"  ↳ InvPolicy site={site.name} product={product_id}: SKIP"
                )
            summary["inv_policy"]["skipped"] += 1
        else:
            policy = InvPolicy(
                site_id=site.id,
                product_id=product_id,
                config_id=config.id,
                ss_policy="abs_level",
                ss_quantity=TBG_SAFETY_STOCK,
                order_up_to_level=TBG_ORDER_UP_TO,
                min_order_quantity=0.0,
                is_active="true",
                # Simulation extensions
                holding_cost_range=TBG_HOLDING_COST_RANGE,
                backlog_cost_range=TBG_BACKLOG_COST_RANGE,
                initial_inventory_range={"min": TBG_INITIAL_INVENTORY, "max": TBG_INITIAL_INVENTORY},
            )
            db.add(policy)
            if verbose:
                logger.info(
                    f"  ↳ InvPolicy site={site.name} product={product_id}: CREATED"
                )
            summary["inv_policy"]["created"] += 1

    # ── 3. SourcingRules per TransportationLane ────────────────────────────────
    lanes = (
        db.query(TransportationLane)
        .filter(TransportationLane.config_id == config.id)
        .all()
    )

    for lane in lanes:
        existing_rule = (
            db.query(SourcingRules)
            .filter(
                SourcingRules.product_id == product_id,
                SourcingRules.to_site_id == lane.to_site_id,
                SourcingRules.from_site_id == lane.from_site_id,
            )
            .first()
        )
        if existing_rule:
            if verbose:
                logger.info(
                    f"  ↳ SourcingRule lane={lane.id}"
                    f" ({lane.from_site_id}→{lane.to_site_id}): SKIP"
                )
            summary["sourcing_rules"]["skipped"] += 1
        else:
            # String PK: use a deterministic ID based on config + product + lane
            rule_id = f"TBG-SR-{config.id}-{product_id}-{lane.id}"

            # Extract lead time from the lane's supply_lead_time JSON
            supply_lt = lane.supply_lead_time or {}
            lead_time_weeks = supply_lt.get("value", TBG_LEAD_TIME_WEEKS)

            rule = SourcingRules(
                id=rule_id,
                product_id=product_id,
                from_site_id=lane.from_site_id,   # upstream (supplier)
                to_site_id=lane.to_site_id,        # downstream (receiving)
                sourcing_rule_type="transfer",
                sourcing_priority=1,
                sourcing_ratio=1.0,
                transportation_lane_id=lane.id,
                is_active="true",
                # config_id is a simulation extension on SourcingRules
                config_id=config.id,
            )
            db.add(rule)
            if verbose:
                logger.info(
                    f"  ↳ SourcingRule lane={lane.id}"
                    f" ({lane.from_site_id}→{lane.to_site_id}): CREATED"
                )
            summary["sourcing_rules"]["created"] += 1

    db.commit()
    return summary


def run(
    config_id: Optional[int] = None,
    verbose: bool = False,
) -> None:
    """Seed TBG SC data for all matching configs (or a specific one).

    Args:
        config_id: If provided, seed only this config ID.
        verbose: Print per-record details.
    """
    if sync_engine is None:
        raise RuntimeError(
            "Synchronous database engine not configured. "
            "Check DATABASE_TYPE and POSTGRESQL_* environment variables."
        )

    Session = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

    with Session() as db:
        if config_id is not None:
            configs = (
                db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.id == config_id)
                .all()
            )
            if not configs:
                logger.error(f"Config ID {config_id} not found.")
                sys.exit(1)
        else:
            # Seed all configs whose name contains "TBG" (case-insensitive)
            configs = (
                db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.name.ilike("%TBG%"))
                .all()
            )
            if not configs:
                logger.warning("No TBG configs found (name ILIKE '%TBG%'). Nothing to seed.")
                return

        logger.info(f"Seeding {len(configs)} TBG config(s)...")

        totals = {
            "product": {"created": 0, "skipped": 0},
            "inv_policy": {"created": 0, "skipped": 0},
            "sourcing_rules": {"created": 0, "skipped": 0},
        }

        for config in configs:
            logger.info(f"Config {config.id} — {config.name}")
            summary = seed_config(db, config, verbose=verbose)
            for key in totals:
                totals[key]["created"] += summary[key]["created"]
                totals[key]["skipped"] += summary[key]["skipped"]

        logger.info("─" * 60)
        logger.info("Seed complete:")
        for key, counts in totals.items():
            logger.info(
                f"  {key:20s}: {counts['created']} created, {counts['skipped']} skipped"
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Seed TBG SC configs with Product, InvPolicy, SourcingRules"
    )
    parser.add_argument(
        "--config-id",
        type=int,
        default=None,
        help="Seed only this SupplyChainConfig ID (default: all TBG configs)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print per-record details",
    )
    args = parser.parse_args()

    run(config_id=args.config_id, verbose=args.verbose)

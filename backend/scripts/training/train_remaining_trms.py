#!/usr/bin/env python3
"""
Train TRM types via Phase 1 Behavioral Cloning for a given SC config and site.

Phase 1 BC requires no DB data — it generates synthetic curriculum data and
trains against deterministic engine labels. Use this script to fill gaps in
checkpoint coverage for any supply chain configuration.

Usage:
    # Train all 11 TRM types for all sites in config 22
    python train_remaining_trms.py --config-id 22

    # Train specific TRM types for a specific site
    python train_remaining_trms.py --config-id 22 --site-id 256 --trm-types rebalancing,inventory_buffer

    # Train on GPU
    python train_remaining_trms.py --config-id 22 --device cuda
"""

import argparse
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ALL_TRM_TYPES = [
    "atp_executor",
    "rebalancing",
    "po_creation",
    "order_tracking",
    "inventory_buffer",
    "mo_execution",
    "to_execution",
    "quality_disposition",
    "maintenance_scheduling",
    "subcontracting",
    "forecast_adjustment",
]


def get_sites_from_config(config_id: int):
    """Load site metadata from the DB for a given config."""
    try:
        from app.db.session import SessionLocal
        from app.models.supply_chain_config import SupplyChainConfig
        from sqlalchemy.orm import joinedload

        db = SessionLocal()
        try:
            config = (
                db.query(SupplyChainConfig)
                .options(joinedload(SupplyChainConfig.sites))
                .filter(SupplyChainConfig.id == config_id)
                .first()
            )
            if config and config.sites:
                return [
                    {
                        "site_id": s.id,
                        "site_name": s.name,
                        "master_type": s.master_type or "INVENTORY",
                    }
                    for s in config.sites
                ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load sites from DB: {e}")
    return []


def get_tenant_id_from_config(config_id: int) -> int:
    """Load tenant_id from supply chain config record. Falls back to 1."""
    try:
        from app.db.session import SessionLocal
        from app.models.supply_chain_config import SupplyChainConfig

        db = SessionLocal()
        try:
            cfg = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
            if cfg and cfg.tenant_id:
                return int(cfg.tenant_id)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load tenant_id for config {config_id}: {e}")
    return 1


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-id", type=int, required=True,
                        help="Supply chain config ID to load sites from")
    parser.add_argument("--site-id", type=int, default=None,
                        help="Specific site ID; if omitted, trains all sites in config")
    parser.add_argument("--trm-types", type=str, default=None,
                        help="Comma-separated TRM types (default: all 11)")
    parser.add_argument("--tenant-id", type=int, default=None,
                        help="Tenant ID (auto-loaded from DB if not provided)")
    parser.add_argument("--epochs", type=int, default=30,
                        help="Epochs per sub-phase (10 each: simple/moderate/stress)")
    parser.add_argument("--device", type=str, default="cpu")
    return parser.parse_args()


async def main():
    from app.services.powell.trm_site_trainer import TRMSiteTrainer
    from pathlib import Path
    import torch

    args = parse_args()

    # Resolve sites
    all_sites = get_sites_from_config(args.config_id)
    if not all_sites:
        logger.error(f"No sites found for config {args.config_id}. Check DB connection and config ID.")
        return

    if args.site_id is not None:
        sites = [s for s in all_sites if s["site_id"] == args.site_id]
        if not sites:
            logger.error(f"Site {args.site_id} not found in config {args.config_id}.")
            return
    else:
        sites = all_sites

    # Resolve TRM types
    trm_types = ALL_TRM_TYPES
    if args.trm_types:
        trm_types = [t.strip() for t in args.trm_types.split(",")]

    # Resolve tenant_id
    tenant_id = args.tenant_id if args.tenant_id else get_tenant_id_from_config(args.config_id)

    # Checkpoint directory: per-config, not food dist specific
    checkpoint_dir = Path(__file__).parent.parent.parent / "checkpoints" / f"trm_config{args.config_id}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Config ID: {args.config_id} | Tenant ID: {tenant_id}")
    logger.info(f"Sites to train: {[s['site_name'] for s in sites]}")
    logger.info(f"TRM types: {trm_types}")
    logger.info(f"Checkpoint dir: {checkpoint_dir}")

    for site in sites:
        for trm_type in trm_types:
            logger.info("=" * 60)
            logger.info(f"Training {trm_type} for {site['site_name']} (id={site['site_id']})")
            logger.info("=" * 60)

            trainer = TRMSiteTrainer(
                trm_type=trm_type,
                site_id=site["site_id"],
                site_name=site["site_name"],
                master_type=site["master_type"],
                tenant_id=tenant_id,
                config_id=args.config_id,
                device=args.device,
                checkpoint_dir=checkpoint_dir,
            )

            result = await trainer.train_phase1(
                epochs=args.epochs,
                num_samples=5000,
                learning_rate=1e-4,
                batch_size=64,
            )

            if result.get("skipped"):
                logger.warning(f"  SKIPPED: {result.get('reason')}")
                continue

            logger.info(f"  Final loss: {result.get('final_loss', 'N/A'):.4f}")
            logger.info(f"  Training time: {result.get('training_time', 0):.1f}s")

            # Save checkpoint
            standard_path = checkpoint_dir / f"trm_{trm_type}_site{site['site_id']}.pt"
            checkpoint_data = {
                "model_state_dict": trainer.model.state_dict(),
                "trm_type": trm_type,
                "site_id": site["site_id"],
                "site_name": site["site_name"],
                "master_type": site["master_type"],
                "state_dim": trainer.state_dim,
                "model_class": trainer.model_cls.__name__,
                "config_id": args.config_id,
                "tenant_id": tenant_id,
                "phase": "phase1_bc",
                "training_result": result,
            }
            torch.save(checkpoint_data, standard_path)
            logger.info(f"  Saved: {standard_path}")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info(f"All checkpoints for config {args.config_id}:")
    logger.info("=" * 60)
    for f in sorted(checkpoint_dir.glob("trm_*.pt")):
        logger.info(f"  {f.name}")


if __name__ == "__main__":
    asyncio.run(main())

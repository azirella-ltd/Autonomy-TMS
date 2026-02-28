#!/usr/bin/env python3
"""
Train remaining TRM types for Food Dist DC (site 256) via Phase 1 BC.

Existing checkpoints: atp_executor, po_creation, order_tracking
Missing for INVENTORY site: rebalancing, inventory_buffer

This script trains Phase 1 (Behavioral Cloning) which requires no DB data -
it generates synthetic curriculum data and trains against deterministic engine labels.
"""

import asyncio
import sys
import os
import logging

# Ensure app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from app.services.powell.trm_site_trainer import TRMSiteTrainer
    from pathlib import Path

    # Food Dist DC site parameters
    SITE_ID = 256
    SITE_NAME = "FOODDIST_DC"
    MASTER_TYPE = "INVENTORY"
    TENANT_ID = 3
    CONFIG_ID = 22
    DEVICE = "cpu"

    # Checkpoint directory for food dist (at project root, not scripts/)
    checkpoint_dir = Path(__file__).parent.parent.parent / "checkpoints" / "trm_food_dist"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # TRM types to train (missing from existing checkpoints)
    trm_types_to_train = ["rebalancing", "inventory_buffer"]

    for trm_type in trm_types_to_train:
        logger.info("=" * 60)
        logger.info(f"Training TRM: {trm_type} for site {SITE_NAME} (id={SITE_ID})")
        logger.info("=" * 60)

        trainer = TRMSiteTrainer(
            trm_type=trm_type,
            site_id=SITE_ID,
            site_name=SITE_NAME,
            master_type=MASTER_TYPE,
            tenant_id=TENANT_ID,
            config_id=CONFIG_ID,
            device=DEVICE,
            checkpoint_dir=checkpoint_dir,
        )

        result = await trainer.train_phase1(
            epochs=30,         # 10 per sub-phase (simple/moderate/full)
            num_samples=5000,
            learning_rate=1e-4,
            batch_size=64,
        )

        if result.get("skipped"):
            logger.warning(f"  SKIPPED: {result.get('reason')}")
            continue

        logger.info(f"  Final loss: {result.get('final_loss', 'N/A'):.4f}")
        logger.info(f"  Training time: {result.get('training_time', 0):.1f}s")

        # Save checkpoint with standard naming (trm_{type}.pt)
        import torch
        standard_path = checkpoint_dir / f"trm_{trm_type}.pt"
        checkpoint_data = {
            "model_state_dict": trainer.model.state_dict(),
            "trm_type": trm_type,
            "site_id": SITE_ID,
            "site_name": SITE_NAME,
            "master_type": MASTER_TYPE,
            "state_dim": trainer.state_dim,
            "model_class": trainer.model_cls.__name__,
            "config_id": CONFIG_ID,
            "phase": "phase1_bc",
            "training_result": result,
        }
        torch.save(checkpoint_data, standard_path)
        logger.info(f"  Saved checkpoint: {standard_path}")

    # Verify all checkpoints
    logger.info("\n" + "=" * 60)
    logger.info("All TRM checkpoints for Food Dist:")
    logger.info("=" * 60)
    for f in sorted(checkpoint_dir.glob("trm_*.pt")):
        logger.info(f"  {f.name}")


if __name__ == "__main__":
    asyncio.run(main())

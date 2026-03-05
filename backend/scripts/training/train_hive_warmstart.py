#!/usr/bin/env python3
"""
Hive Warm-Start Training — Signal Phases 1 + 2

Runs the stigmergic curriculum through NO_SIGNALS and URGENCY_ONLY phases
for all 11 TRM types across specified sites. This is the warm-start that
prepares models for full signal-aware RL fine-tuning.

Phases executed:
  Signal Phase 1 (NO_SIGNALS):  Learning Phase 1 (BC)
  Signal Phase 2 (URGENCY_ONLY): Learning Phase 1 (BC) + Phase 2 (Expert)

Usage:
    python scripts/training/train_hive_warmstart.py --config-id 1 --epochs 30
    python scripts/training/train_hive_warmstart.py --site-ids 1,2,3 --trm-types atp_executor,po_creation
    python scripts/training/train_hive_warmstart.py --all-sites --device cuda

Environment Variables:
    CUDA_VISIBLE_DEVICES: GPU selection
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch

from app.services.powell.trm_site_trainer import TRMSiteTrainer, StigmergicPhase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# All 11 TRM types
ALL_TRM_TYPES = [
    "atp_executor",
    "rebalancing",
    "po_creation",
    "order_tracking",
    "mo_execution",
    "to_execution",
    "quality_disposition",
    "maintenance_scheduling",
    "subcontracting",
    "forecast_adjustment",
    "inventory_buffer",
]


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
    parser = argparse.ArgumentParser(description='Hive Warm-Start Training (Phases 1+2)')

    # Site selection
    parser.add_argument('--config-id', type=int, default=1,
                        help='Supply chain config ID to load sites from')
    parser.add_argument('--site-ids', type=str, default=None,
                        help='Comma-separated site IDs (overrides --config-id)')
    parser.add_argument('--all-sites', action='store_true',
                        help='Train all sites from config')

    # TRM selection
    parser.add_argument('--trm-types', type=str, default=None,
                        help='Comma-separated TRM types (default: all 11)')

    # Training
    parser.add_argument('--epochs', type=int, default=30,
                        help='Epochs per learning phase')
    parser.add_argument('--num-samples', type=int, default=5000,
                        help='Synthetic samples per BC sub-phase')
    parser.add_argument('--device', type=str, default='cpu',
                        help='Training device (cpu/cuda)')

    # Tenant
    parser.add_argument('--tenant-id', type=int, default=None,
                        help='Tenant ID (auto-loaded from DB via config-id if not provided)')

    # Output
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Checkpoint output directory (default: checkpoints/trm_config{id}/)')
    parser.add_argument('--results-json', type=str, default=None,
                        help='Path to save results JSON')

    return parser.parse_args()


def get_sites_from_config(config_id: int) -> List[dict]:
    """Load sites from a supply chain config (lightweight, no DB session needed for training)."""
    # For warm-start, we generate synthetic data, so we just need site metadata.
    # If a DB is available, load real sites; otherwise use default placeholders.
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

    # Fallback: default 4-site supply chain topology
    return [
        {"site_id": 1, "site_name": "Retailer", "master_type": "INVENTORY"},
        {"site_id": 2, "site_name": "Wholesaler", "master_type": "INVENTORY"},
        {"site_id": 3, "site_name": "Distributor", "master_type": "INVENTORY"},
        {"site_id": 4, "site_name": "Factory", "master_type": "MANUFACTURER"},
    ]


async def train_site_trm(
    trm_type: str,
    site: dict,
    config_id: int,
    tenant_id: int,
    epochs: int,
    num_samples: int,
    device: str,
    output_dir: Optional[Path],
) -> dict:
    """Train one TRM for one site through warm-start phases."""
    trainer = TRMSiteTrainer(
        trm_type=trm_type,
        site_id=site["site_id"],
        site_name=site["site_name"],
        master_type=site["master_type"],
        tenant_id=tenant_id,
        config_id=config_id,
        device=device,
        checkpoint_dir=output_dir,
    )

    results = []

    # Signal Phase 1: NO_SIGNALS → BC
    trainer.stigmergic_phase = StigmergicPhase.NO_SIGNALS
    r = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)
    results.append(r)

    version = 1
    trainer.save_checkpoint(version, extra_meta={
        "stigmergic_phase": "NO_SIGNALS",
        "learning_phase": 1,
    })

    # Signal Phase 2: URGENCY_ONLY → BC
    trainer.stigmergic_phase = StigmergicPhase.URGENCY_ONLY
    r = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)
    results.append(r)

    version = 2
    trainer.save_checkpoint(version, extra_meta={
        "stigmergic_phase": "URGENCY_ONLY",
        "learning_phase": 1,
    })

    return {
        "trm_type": trm_type,
        "site_id": site["site_id"],
        "site_name": site["site_name"],
        "phases_completed": len(results),
        "results": results,
    }


async def main():
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Hive Warm-Start Training")
    logger.info("=" * 60)

    # Resolve sites
    if args.site_ids:
        site_ids = [int(x.strip()) for x in args.site_ids.split(",")]
        sites = [{"site_id": sid, "site_name": f"Site_{sid}", "master_type": "INVENTORY"} for sid in site_ids]
    else:
        sites = get_sites_from_config(args.config_id)

    # Resolve TRM types
    trm_types = ALL_TRM_TYPES
    if args.trm_types:
        trm_types = [t.strip() for t in args.trm_types.split(",")]

    # Resolve tenant_id from DB if not provided
    tenant_id = args.tenant_id if args.tenant_id else get_tenant_id_from_config(args.config_id)

    # Output directory — defaults to checkpoints/trm_config{id}/
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(__file__).parent.parent.parent / "checkpoints" / f"trm_config{args.config_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Config ID: {args.config_id} | Tenant ID: {tenant_id}")
    logger.info(f"Sites: {[s['site_name'] for s in sites]}")
    logger.info(f"TRM types: {trm_types}")
    logger.info(f"Epochs per phase: {args.epochs}")
    logger.info(f"Samples per sub-phase: {args.num_samples}")
    logger.info(f"Device: {args.device}")
    logger.info(f"Checkpoint dir: {output_dir}")

    start = time.time()
    all_results = []

    for site in sites:
        for trm_type in trm_types:
            logger.info(f"\n--- Training {trm_type} @ {site['site_name']} ---")
            try:
                result = await train_site_trm(
                    trm_type=trm_type,
                    site=site,
                    config_id=args.config_id,
                    tenant_id=tenant_id,
                    epochs=args.epochs,
                    num_samples=args.num_samples,
                    device=args.device,
                    output_dir=output_dir,
                )
                all_results.append(result)
                logger.info(
                    f"  Done: {result['phases_completed']} phases, "
                    f"loss={result['results'][-1].get('final_loss', 'N/A')}"
                )
            except Exception as e:
                logger.error(f"  Failed: {e}")
                all_results.append({
                    "trm_type": trm_type,
                    "site_id": site["site_id"],
                    "error": str(e),
                })

    total_duration = time.time() - start
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Warm-start complete: {len(all_results)} site-TRM pairs, {total_duration:.1f}s")

    # Save results
    if args.results_json:
        results_path = Path(args.results_json)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "total_duration_seconds": total_duration,
                "config_id": args.config_id,
                "device": args.device,
                "results": all_results,
            }, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")


if __name__ == "__main__":
    asyncio.run(main())

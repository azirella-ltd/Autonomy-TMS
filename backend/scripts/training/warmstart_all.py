#!/usr/bin/env python3
"""
Unified warm start for all AI models for a given supply chain config.

Runs in sequence:
  1. TRM Hive Warm Start  — Phase 1 BC (NO_SIGNALS) + Phase 1 BC (URGENCY_ONLY)
                            for all 11 TRM types × all sites in the config
  2. GNN Hybrid Training  — S&OP GraphSAGE + Execution tGNN trained together
                            from topology data loaded from the DB config

All checkpoints are named from the config ID, not from a demo-specific slug.

Usage:
    # Warm-start everything for config 22
    python warmstart_all.py --config-id 22

    # TRM only (skip GNN), GPU, 50 epochs
    python warmstart_all.py --config-id 22 --device cuda --epochs 50 --skip-gnn

    # GNN only for config 5
    python warmstart_all.py --config-id 5 --skip-trm

    # Specific site + TRM types
    python warmstart_all.py --config-id 22 --site-id 256 --trm-types atp_executor,po_creation
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

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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


# ---------------------------------------------------------------------------
# DB helpers (shared with train_hive_warmstart.py logic)
# ---------------------------------------------------------------------------

def get_sites_from_config(config_id: int) -> List[dict]:
    """Load site metadata from DB for a given config."""
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


# ---------------------------------------------------------------------------
# TRM warm start
# ---------------------------------------------------------------------------

async def run_trm_warmstart(
    config_id: int,
    tenant_id: int,
    sites: List[dict],
    trm_types: List[str],
    epochs: int,
    num_samples: int,
    device: str,
    checkpoint_dir: Path,
) -> dict:
    from app.services.powell.trm_site_trainer import TRMSiteTrainer, StigmergicPhase

    results = []
    errors = []

    for site in sites:
        for trm_type in trm_types:
            logger.info(f"  TRM {trm_type} @ {site['site_name']}")
            try:
                trainer = TRMSiteTrainer(
                    trm_type=trm_type,
                    site_id=site["site_id"],
                    site_name=site["site_name"],
                    master_type=site["master_type"],
                    tenant_id=tenant_id,
                    config_id=config_id,
                    device=device,
                    checkpoint_dir=checkpoint_dir,
                )

                # Signal Phase 1: NO_SIGNALS → BC
                trainer.stigmergic_phase = StigmergicPhase.NO_SIGNALS
                r1 = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)
                trainer.save_checkpoint(1, extra_meta={
                    "stigmergic_phase": "NO_SIGNALS",
                    "learning_phase": 1,
                })

                # Signal Phase 2: URGENCY_ONLY → BC
                trainer.stigmergic_phase = StigmergicPhase.URGENCY_ONLY
                r2 = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)
                trainer.save_checkpoint(2, extra_meta={
                    "stigmergic_phase": "URGENCY_ONLY",
                    "learning_phase": 1,
                })

                results.append({
                    "trm_type": trm_type,
                    "site_id": site["site_id"],
                    "site_name": site["site_name"],
                    "phases": 2,
                    "final_loss": r2.get("final_loss"),
                })
            except Exception as e:
                logger.error(f"    Failed: {e}")
                errors.append({"trm_type": trm_type, "site_id": site["site_id"], "error": str(e)})

    return {"results": results, "errors": errors}


# ---------------------------------------------------------------------------
# GNN warm start
# ---------------------------------------------------------------------------

def run_gnn_warmstart(
    config_id: int,
    epochs: int,
    device: str,
    checkpoint_dir: Path,
) -> dict:
    """Train hybrid GNN (SOP GraphSAGE + Execution tGNN) for the given config."""
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        logger.error("PyTorch not available — skipping GNN warm start.")
        return {"skipped": True, "reason": "PyTorch not available"}

    try:
        from app.models.gnn.planning_execution_gnn import (
            create_sop_model,
            create_execution_model,
        )
        from app.models.gnn.large_sc_data_generator import (
            load_config_from_db,
            generate_synthetic_config,
            LargeSupplyChainSimulator,
        )
    except ImportError as e:
        logger.error(f"GNN modules not available: {e} — skipping GNN warm start.")
        return {"skipped": True, "reason": str(e)}

    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, using CPU for GNN")
        device = "cpu"

    checkpoint_name = f"planning_execution_config{config_id}"

    try:
        config = load_config_from_db(config_id)
    except Exception as e:
        logger.warning(f"Could not load config {config_id} from DB: {e}. Using synthetic.")
        config = generate_synthetic_config(20)

    logger.info(f"  GNN config: {config.name}, nodes: {config.num_nodes()}, edges: {config.num_edges()}")

    # ---- S&OP GraphSAGE ----
    from scripts.training.train_planning_execution import (
        generate_sop_features,
        generate_execution_features,
        train_sop_model,
        train_execution_model,
    )

    logger.info("  Generating S&OP features...")
    sop_data = generate_sop_features(config, num_samples=50)

    sop_model = create_sop_model(hidden_dim=128, embedding_dim=64)
    logger.info("  Training S&OP GraphSAGE...")
    sop_model = train_sop_model(
        sop_model, sop_data, device,
        epochs=epochs,
        checkpoint_name=f"{checkpoint_name}_sop",
    )

    # Extract structural embeddings
    sop_model.eval()
    with torch.no_grad():
        outputs = sop_model(
            sop_data["node_features"][0].to(device),
            sop_data["edge_index"].to(device),
            sop_data["edge_features"][0].to(device) if sop_data["edge_features"].dim() == 3 else sop_data["edge_features"].to(device),
        )
        structural_emb = outputs["structural_embeddings"].cpu()

    # ---- Execution tGNN ----
    logger.info("  Generating Execution features...")
    exec_data = generate_execution_features(config, structural_emb, num_samples=200, window_size=10)

    exec_model = create_execution_model(structural_embedding_dim=64, hidden_dim=128, window_size=10)
    logger.info("  Training Execution tGNN...")
    train_execution_model(
        exec_model, exec_data, device,
        epochs=epochs,
        checkpoint_name=f"{checkpoint_name}_execution",
    )

    return {
        "checkpoint_prefix": checkpoint_name,
        "sop_checkpoint": str(BACKEND_ROOT / "checkpoints" / f"{checkpoint_name}_sop_best.pt"),
        "exec_checkpoint": str(BACKEND_ROOT / "checkpoints" / f"{checkpoint_name}_execution_best.pt"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-id", type=int, required=True,
                        help="Supply chain config ID (loads sites and topology from DB)")
    parser.add_argument("--device", type=str, default="cpu",
                        help="Training device: cpu or cuda")
    parser.add_argument("--epochs", type=int, default=30,
                        help="Epochs per training phase")
    parser.add_argument("--num-samples", type=int, default=5000,
                        help="Synthetic samples per TRM BC sub-phase")
    parser.add_argument("--tenant-id", type=int, default=None,
                        help="Tenant ID (auto-loaded from DB if not provided)")
    parser.add_argument("--site-id", type=int, default=None,
                        help="Train a single site ID only (default: all sites)")
    parser.add_argument("--trm-types", type=str, default=None,
                        help="Comma-separated TRM types (default: all 11)")
    parser.add_argument("--skip-trm", action="store_true",
                        help="Skip TRM warm start")
    parser.add_argument("--skip-gnn", action="store_true",
                        help="Skip GNN training")
    parser.add_argument("--results-json", type=str, default=None,
                        help="Path to save results summary as JSON")
    return parser.parse_args()


async def main():
    args = parse_args()

    logger.info("=" * 70)
    logger.info(f"Warm Start — Config {args.config_id}")
    logger.info("=" * 70)

    start_total = time.time()

    # Resolve DB metadata
    tenant_id = args.tenant_id if args.tenant_id else get_tenant_id_from_config(args.config_id)
    all_sites = get_sites_from_config(args.config_id)

    if not all_sites:
        logger.warning(f"No sites found for config {args.config_id} — DB may be unavailable.")

    if args.site_id is not None:
        sites = [s for s in all_sites if s["site_id"] == args.site_id]
        if not sites:
            logger.error(f"Site {args.site_id} not in config {args.config_id}. Available: {[s['site_id'] for s in all_sites]}")
            return
    else:
        sites = all_sites

    trm_types = ALL_TRM_TYPES
    if args.trm_types:
        trm_types = [t.strip() for t in args.trm_types.split(",")]

    checkpoint_dir = BACKEND_ROOT / "checkpoints" / f"trm_config{args.config_id}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Tenant ID: {tenant_id}")
    logger.info(f"Sites: {[s['site_name'] for s in sites]}")
    logger.info(f"TRM types: {trm_types}")
    logger.info(f"TRM checkpoint dir: {checkpoint_dir}")
    logger.info(f"Device: {args.device} | Epochs: {args.epochs}")
    logger.info(f"Skip TRM: {args.skip_trm} | Skip GNN: {args.skip_gnn}")

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "config_id": args.config_id,
        "tenant_id": tenant_id,
        "device": args.device,
        "epochs": args.epochs,
        "trm": None,
        "gnn": None,
    }

    # ---- Step 1: TRM warm start ----
    if not args.skip_trm:
        logger.info("\n" + "=" * 70)
        logger.info("STEP 1: TRM Hive Warm Start")
        logger.info("=" * 70)
        t0 = time.time()
        trm_result = await run_trm_warmstart(
            config_id=args.config_id,
            tenant_id=tenant_id,
            sites=sites,
            trm_types=trm_types,
            epochs=args.epochs,
            num_samples=args.num_samples,
            device=args.device,
            checkpoint_dir=checkpoint_dir,
        )
        trm_duration = time.time() - t0
        logger.info(f"TRM complete: {len(trm_result['results'])} trained, {len(trm_result['errors'])} errors, {trm_duration:.1f}s")
        summary["trm"] = {**trm_result, "duration_seconds": trm_duration}
    else:
        logger.info("STEP 1: TRM — SKIPPED")

    # ---- Step 2: GNN warm start ----
    if not args.skip_gnn:
        logger.info("\n" + "=" * 70)
        logger.info("STEP 2: GNN Warm Start (S&OP GraphSAGE + Execution tGNN)")
        logger.info("=" * 70)
        t0 = time.time()
        gnn_result = run_gnn_warmstart(
            config_id=args.config_id,
            epochs=args.epochs,
            device=args.device,
            checkpoint_dir=BACKEND_ROOT / "checkpoints",
        )
        gnn_duration = time.time() - t0
        logger.info(f"GNN complete: {gnn_duration:.1f}s")
        if not gnn_result.get("skipped"):
            logger.info(f"  SOP checkpoint:  {gnn_result.get('sop_checkpoint')}")
            logger.info(f"  Exec checkpoint: {gnn_result.get('exec_checkpoint')}")
        summary["gnn"] = {**gnn_result, "duration_seconds": gnn_duration}
    else:
        logger.info("STEP 2: GNN — SKIPPED")

    total_duration = time.time() - start_total
    summary["total_duration_seconds"] = total_duration

    logger.info("\n" + "=" * 70)
    logger.info(f"Warm start complete — {total_duration:.1f}s total")
    logger.info("=" * 70)

    if args.results_json:
        results_path = Path(args.results_json)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")


if __name__ == "__main__":
    asyncio.run(main())

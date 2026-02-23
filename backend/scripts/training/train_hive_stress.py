#!/usr/bin/env python3
"""
Hive Stress Training — Signal Phase 3 (FULL_SIGNALS) + RL/CQL

Runs the final stigmergic curriculum phase with full signal features
and RL fine-tuning using cross-head reward from coordinated traces.

Prerequisite: Run train_hive_warmstart.py first to create Phase 1+2 checkpoints.

Phases executed:
  Signal Phase 3 (FULL_SIGNALS):
    → Learning Phase 1 (BC): Full signal-augmented behavioral cloning
    → Learning Phase 2 (Expert): Expert overrides with full signal context
    → Learning Phase 3 (RL/CQL): TD learning with cross-head coordination reward

Usage:
    python scripts/training/train_hive_stress.py --config-id 1 --epochs 40
    python scripts/training/train_hive_stress.py --site-ids 1,2,3 --device cuda
    python scripts/training/train_hive_stress.py --trace-dir traces/ --cross-head-weight 0.1

Environment Variables:
    CUDA_VISIBLE_DEVICES: GPU selection
    DATABASE_URL: PostgreSQL connection for expert/replay data
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

import numpy as np
import torch

from app.services.powell.trm_site_trainer import (
    TRMSiteTrainer,
    StigmergicPhase,
    find_best_checkpoint,
)

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
    "safety_stock",
]


def parse_args():
    parser = argparse.ArgumentParser(description='Hive Stress Training (Phase 3 RL/CQL)')

    # Site selection
    parser.add_argument('--config-id', type=int, default=1,
                        help='Supply chain config ID')
    parser.add_argument('--site-ids', type=str, default=None,
                        help='Comma-separated site IDs')

    # TRM selection
    parser.add_argument('--trm-types', type=str, default=None,
                        help='Comma-separated TRM types (default: all 11)')

    # Training
    parser.add_argument('--epochs', type=int, default=40,
                        help='Epochs per learning phase')
    parser.add_argument('--num-samples', type=int, default=5000,
                        help='Synthetic samples for BC sub-phase')
    parser.add_argument('--cross-head-weight', type=float, default=0.05,
                        help='Weight for cross-head reward in RL loss')
    parser.add_argument('--device', type=str, default='cpu',
                        help='Training device (cpu/cuda)')

    # Data
    parser.add_argument('--trace-dir', type=str, default=None,
                        help='Directory with hive trace files from generate_hive_traces.py')
    parser.add_argument('--use-db', action='store_true',
                        help='Load expert/replay data from database')

    # Output
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Checkpoint output directory')
    parser.add_argument('--results-json', type=str, default=None,
                        help='Path to save results JSON')

    return parser.parse_args()


def load_traces_as_replay(trace_dir: Path, trm_type: str, site_id: int) -> dict:
    """Load hive traces from disk and convert to replay buffer format.

    Hive traces (from generate_hive_traces.py) contain per-TRM decision
    snapshots with state features, actions, rewards, and signal context.
    """
    states, next_states, rewards, dones = [], [], [], []
    signal_contexts, next_signal_contexts, cross_head_rewards = [], [], []

    trace_files = sorted(trace_dir.glob("*.json"))
    if not trace_files:
        logger.warning(f"No trace files found in {trace_dir}")
        return {
            "states": np.empty((0,)), "next_states": np.empty((0,)),
            "rewards": np.empty((0,)), "dones": np.empty((0,)),
            "signal_contexts": [], "next_signal_contexts": [],
            "cross_head_rewards": np.empty((0,)),
        }

    for tf in trace_files:
        try:
            with open(tf) as f:
                episode = json.load(f)
        except Exception:
            continue

        traces = episode.get("traces", [])
        for i, trace in enumerate(traces):
            if trace.get("site_key", "") and str(site_id) not in trace.get("site_key", ""):
                continue

            for decision in trace.get("decisions", []):
                if decision.get("trm_name") != trm_type:
                    continue

                features = decision.get("state_features")
                if features is None:
                    continue

                states.append(features)
                rewards.append(decision.get("reward", 0.0))
                cross_head_rewards.append(trace.get("cross_head_reward", 0.0))

                # Signal context from urgency snapshot
                signal_contexts.append({
                    "urgency_vector": trace.get("urgency_snapshot", {}),
                    "summary": {},
                })

                # Next state: use next trace's features if available
                next_trace = traces[i + 1] if i + 1 < len(traces) else None
                if next_trace:
                    next_decisions = next_trace.get("decisions", [])
                    next_feat = None
                    for nd in next_decisions:
                        if nd.get("trm_name") == trm_type:
                            next_feat = nd.get("state_features")
                            break
                    next_states.append(next_feat if next_feat else features)
                    next_signal_contexts.append({
                        "urgency_vector": next_trace.get("urgency_snapshot", {}),
                        "summary": {},
                    })
                    dones.append(0.0)
                else:
                    next_states.append(features)
                    next_signal_contexts.append(signal_contexts[-1])
                    dones.append(1.0)

    return {
        "states": np.array(states, dtype=np.float32) if states else np.empty((0,)),
        "next_states": np.array(next_states, dtype=np.float32) if next_states else np.empty((0,)),
        "rewards": np.array(rewards, dtype=np.float32) if rewards else np.empty((0,)),
        "dones": np.array(dones, dtype=np.float32) if dones else np.empty((0,)),
        "signal_contexts": signal_contexts,
        "next_signal_contexts": next_signal_contexts,
        "cross_head_rewards": np.array(cross_head_rewards, dtype=np.float32) if cross_head_rewards else np.empty((0,)),
    }


def get_sites(args) -> List[dict]:
    """Resolve site list from args."""
    if args.site_ids:
        return [
            {"site_id": int(x.strip()), "site_name": f"Site_{x.strip()}", "master_type": "INVENTORY"}
            for x in args.site_ids.split(",")
        ]

    try:
        from app.db.session import SessionLocal
        from app.models.supply_chain_config import SupplyChainConfig
        from sqlalchemy.orm import joinedload

        db = SessionLocal()
        try:
            config = (
                db.query(SupplyChainConfig)
                .options(joinedload(SupplyChainConfig.sites))
                .filter(SupplyChainConfig.id == args.config_id)
                .first()
            )
            if config and config.sites:
                return [
                    {"site_id": s.id, "site_name": s.name, "master_type": s.master_type or "INVENTORY"}
                    for s in config.sites
                ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load sites from DB: {e}")

    return [
        {"site_id": 1, "site_name": "Retailer", "master_type": "INVENTORY"},
        {"site_id": 2, "site_name": "Wholesaler", "master_type": "INVENTORY"},
        {"site_id": 3, "site_name": "Distributor", "master_type": "INVENTORY"},
        {"site_id": 4, "site_name": "Factory", "master_type": "MANUFACTURER"},
    ]


async def train_stress(
    trm_type: str,
    site: dict,
    config_id: int,
    epochs: int,
    num_samples: int,
    cross_head_weight: float,
    device: str,
    trace_dir: Optional[Path],
    output_dir: Optional[Path],
) -> dict:
    """Train one TRM through full-signal stress phase."""
    trainer = TRMSiteTrainer(
        trm_type=trm_type,
        site_id=site["site_id"],
        site_name=site["site_name"],
        master_type=site["master_type"],
        group_id=1,
        config_id=config_id,
        device=device,
        checkpoint_dir=output_dir,
        stigmergic_phase=StigmergicPhase.FULL_SIGNALS,
        cross_head_reward_weight=cross_head_weight,
    )

    # Try to load warm-start checkpoint
    ckpt_path = find_best_checkpoint(
        trm_type=trm_type,
        site_id=site["site_id"],
        master_type=site["master_type"],
        config_id=config_id,
        checkpoint_dir=output_dir,
    )
    if ckpt_path:
        try:
            trainer.from_checkpoint(ckpt_path)
            logger.info(f"Loaded warm-start checkpoint: {ckpt_path}")
        except Exception as e:
            logger.warning(f"Could not load checkpoint {ckpt_path}: {e}")

    results = []

    # Signal Phase 3, Learning Phase 1: BC with full signals
    logger.info(f"  FULL_SIGNALS × Phase 1 (BC)")
    r = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)
    results.append(r)

    # If trace data available, create synthetic replay for Phase 3 RL
    if trace_dir and trace_dir.exists():
        replay_data = load_traces_as_replay(trace_dir, trm_type, site["site_id"])
        n_replay = len(replay_data.get("states", []))

        if n_replay >= 100:
            logger.info(f"  FULL_SIGNALS × Phase 3 (RL/CQL) — {n_replay} trace samples")

            # Augment states with signal context
            augmented_s = trainer._augment_states_from_context(
                replay_data["states"], replay_data["signal_contexts"]
            )
            augmented_ns = trainer._augment_states_from_context(
                replay_data["next_states"], replay_data["next_signal_contexts"]
            )

            # Build reward tensor with cross-head bonus
            rewards = replay_data["rewards"]
            if cross_head_weight > 0:
                rewards = rewards + cross_head_weight * replay_data["cross_head_rewards"]

            states_t = torch.tensor(augmented_s, dtype=torch.float32).to(device)
            next_states_t = torch.tensor(augmented_ns, dtype=torch.float32).to(device)
            rewards_t = torch.tensor(rewards, dtype=torch.float32).to(device)
            dones_t = torch.tensor(replay_data["dones"], dtype=torch.float32).to(device)

            # Manual RL training loop (same as Phase 3 but with trace data)
            import copy
            trainer._ensure_model()
            target_model = copy.deepcopy(trainer.model)
            target_model.eval()

            optimizer = torch.optim.AdamW(trainer.model.parameters(), lr=1e-5, weight_decay=0.01)
            gamma, tau = 0.99, 0.005
            best_loss = float("inf")
            loss_history = []

            for epoch in range(epochs):
                trainer.model.train()
                total_loss = 0.0
                n_batches = 0
                indices = np.random.permutation(len(states_t))

                for bi in range(0, len(states_t), 64):
                    batch_idx = indices[bi:bi + 64]
                    optimizer.zero_grad()

                    outputs = trainer.model(states_t[batch_idx])
                    q_values = outputs["value"].squeeze(-1)

                    with torch.no_grad():
                        next_outputs = target_model(next_states_t[batch_idx])
                        next_q = next_outputs["value"].squeeze(-1)
                        target_q = rewards_t[batch_idx] + gamma * next_q * (1 - dones_t[batch_idx])

                    td_loss = torch.nn.functional.mse_loss(q_values, target_q)
                    cql_penalty = 0.1 * (q_values ** 2).mean()
                    loss = td_loss + cql_penalty

                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(trainer.model.parameters(), 1.0)
                    optimizer.step()

                    for p, tp in zip(trainer.model.parameters(), target_model.parameters()):
                        tp.data.copy_(tau * p.data + (1 - tau) * tp.data)

                    total_loss += loss.item()
                    n_batches += 1

                avg_loss = total_loss / max(1, n_batches)
                loss_history.append(avg_loss)
                if avg_loss < best_loss:
                    best_loss = avg_loss

            results.append({
                "phase": "outcome_optimization",
                "stigmergic_phase": "FULL_SIGNALS",
                "final_loss": best_loss,
                "trace_samples": n_replay,
                "cross_head_weight": cross_head_weight,
                "loss_history": loss_history,
            })
        else:
            logger.info(f"  Skipping RL: only {n_replay} trace samples (need ≥100)")

    # Save final checkpoint
    trainer.save_checkpoint(3, extra_meta={
        "stigmergic_phase": "FULL_SIGNALS",
        "learning_phase": 3,
        "cross_head_weight": cross_head_weight,
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
    logger.info("Hive Stress Training (Phase 3 — Full Signals + RL)")
    logger.info("=" * 60)

    sites = get_sites(args)
    trm_types = ALL_TRM_TYPES
    if args.trm_types:
        trm_types = [t.strip() for t in args.trm_types.split(",")]

    output_dir = Path(args.output_dir) if args.output_dir else None
    trace_dir = Path(args.trace_dir) if args.trace_dir else None

    logger.info(f"Sites: {[s['site_name'] for s in sites]}")
    logger.info(f"TRM types: {trm_types}")
    logger.info(f"Epochs per phase: {args.epochs}")
    logger.info(f"Cross-head reward weight: {args.cross_head_weight}")
    logger.info(f"Trace dir: {trace_dir}")
    logger.info(f"Device: {args.device}")

    start = time.time()
    all_results = []

    for site in sites:
        for trm_type in trm_types:
            logger.info(f"\n--- Stress training {trm_type} @ {site['site_name']} ---")
            try:
                result = await train_stress(
                    trm_type=trm_type,
                    site=site,
                    config_id=args.config_id,
                    epochs=args.epochs,
                    num_samples=args.num_samples,
                    cross_head_weight=args.cross_head_weight,
                    device=args.device,
                    trace_dir=trace_dir,
                    output_dir=output_dir,
                )
                all_results.append(result)
                final_loss = result["results"][-1].get("final_loss", "N/A") if result["results"] else "N/A"
                logger.info(f"  Done: {result['phases_completed']} phases, loss={final_loss}")
            except Exception as e:
                logger.error(f"  Failed: {e}")
                all_results.append({
                    "trm_type": trm_type,
                    "site_id": site["site_id"],
                    "error": str(e),
                })

    total_duration = time.time() - start
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Stress training complete: {len(all_results)} site-TRM pairs, {total_duration:.1f}s")

    if args.results_json:
        results_path = Path(args.results_json)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "total_duration_seconds": total_duration,
                "config_id": args.config_id,
                "device": args.device,
                "cross_head_weight": args.cross_head_weight,
                "results": all_results,
            }, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Training Orchestrator for Food Distribution (or any SupplyChainConfig)

Runs the full 3-tier warm-start pipeline:
  1. DAG Deterministic Simulation  → SimulationResult
  2. DAG SimPy Monte Carlo         → MonteCarloResult (128 × 52)
  3. Convert to training data      → NPZ + TRM records
  4. Train S&OP GraphSAGE          → sop_graphsage_{config_id}.pt
  5. Train Execution tGNN           → execution_tgnn_{config_id}.pt
  6. Train TRMs via Behavioral Cloning → trm_{type}_{site_key}.pt

Usage:
    python -m scripts.training.train_food_dist_models \
        --config-name "Food Distribution" \
        --periods 52 \
        --monte-carlo-runs 128 \
        --epochs 50 \
        --device cuda
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-7s %(message)s",
)


TRAINING_ROOT = BACKEND_ROOT / "training_jobs"
CHECKPOINT_ROOT = BACKEND_ROOT / "checkpoints" / "supply_chain_configs"


def _slugify(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "-", name.strip().lower()).strip("-") or "config"


async def run_pipeline(
    config_name: str,
    num_periods: int = 52,
    mc_runs: int = 128,
    epochs: int = 50,
    device: str = "cpu",
    seed: int = 42,
    demand_noise_cv: float = 0.15,
    window: int = 52,
    horizon: int = 1,
):
    """Run the full warm-start training pipeline."""

    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import async_session_factory
    from app.models.supply_chain_config import SupplyChainConfig
    from sqlalchemy import select

    start_time = time.time()

    # ── Step 0: Load config from DB ──
    logger.info(f"Loading config '{config_name}' from database...")
    async with async_session_factory() as db:
        result = await db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.name == config_name)
        )
        config = result.scalar_one_or_none()
        if not config:
            logger.error(f"Config '{config_name}' not found in database")
            sys.exit(1)

        config_id = config.id
        slug = _slugify(config_name)
        logger.info(f"Found config: id={config_id}, name={config_name}, slug={slug}")

    output_dir = TRAINING_ROOT / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Deterministic Simulation ──
    logger.info("=" * 60)
    logger.info("STEP 1: Deterministic DAG Simulation")
    logger.info("=" * 60)

    from app.services.dag_simulator import DAGSimulator, load_topology, OrderingStrategy

    async with async_session_factory() as db:
        topology = await load_topology(config_id, db)

    strategies = [
        OrderingStrategy.BASE_STOCK,
        OrderingStrategy.CONSERVATIVE,
        OrderingStrategy.PID,
    ]
    det_results = []
    for strategy in strategies:
        logger.info(f"  Running {strategy.value} for {num_periods} periods (seed={seed})...")
        sim = DAGSimulator(topology, strategy=strategy)
        result = sim.simulate(
            num_periods=num_periods,
            seed=seed,
            demand_noise_cv=demand_noise_cv,
        )
        det_results.append(result)
        logger.info(
            f"  {strategy.value}: fill_rate={result.kpis.fill_rate:.2%}, "
            f"decisions={len(result.decisions)}"
        )

    # ── Step 2: Stochastic Monte Carlo Simulation ──
    logger.info("=" * 60)
    logger.info(f"STEP 2: Stochastic SimPy Monte Carlo ({mc_runs} runs × {num_periods} periods)")
    logger.info("=" * 60)

    from app.services.dag_simpy_simulator import DAGSimPySimulator, StochasticConfig

    stochastic_config = StochasticConfig(
        demand_cv=demand_noise_cv,
        lead_time_cv=0.15,
        supplier_reliability=0.95,
    )
    simpy_sim = DAGSimPySimulator(
        topology,
        strategy=OrderingStrategy.BASE_STOCK,
        stochastic_config=stochastic_config,
    )
    mc_result = simpy_sim.run_monte_carlo(
        num_runs=mc_runs,
        num_periods=num_periods,
        seed=seed,
    )
    logger.info(
        f"  Monte Carlo done: {mc_runs} runs, "
        f"avg_fill_rate={mc_result.kpi_stats['fill_rate']['mean']:.2%}, "
        f"total decisions across runs: {sum(len(r.decisions) for r in mc_result.all_results)}"
    )

    # ── Step 3: Convert to Training Data ──
    logger.info("=" * 60)
    logger.info("STEP 3: Convert Simulation Data to Training Formats")
    logger.info("=" * 60)

    from app.services.simulation_data_converter import SimulationDataConverter

    converter = SimulationDataConverter(window=window, horizon=horizon)

    # Combine deterministic + stochastic results
    all_sim_results = det_results + mc_result.all_results
    logger.info(f"  Converting {len(all_sim_results)} simulation runs...")

    conversion = converter.convert_multiple(all_sim_results)

    # Save GNN data
    gnn_path = converter.save_npz(conversion, output_dir / f"{slug}_gnn_dataset.npz")

    # Save TRM data
    trm_paths = converter.save_trm_records(conversion, output_dir / "trm_data")

    logger.info(f"  GNN data: X={conversion.X.shape}, A={conversion.A.shape}, Y={conversion.Y.shape}")
    logger.info(f"  TRM types: {list(conversion.trm_records.keys())}")
    for trm_type, records in conversion.trm_records.items():
        logger.info(f"    {trm_type}: {len(records)} records")

    # Insert decisions into DB for CDC loop
    logger.info("  Inserting decisions into powell_site_agent_decisions...")
    async with async_session_factory() as db:
        await converter.insert_decisions_to_db(conversion, db, config_id)
        await db.commit()
    logger.info("  DB insert complete")

    # ── Step 4: Train S&OP GraphSAGE ──
    logger.info("=" * 60)
    logger.info("STEP 4: Train S&OP GraphSAGE")
    logger.info("=" * 60)

    sop_checkpoint = CHECKPOINT_ROOT / slug / f"sop_graphsage_{config_id}.pt"
    sop_checkpoint.parent.mkdir(parents=True, exist_ok=True)

    try:
        from app.services.powell.powell_training_service import PowellTrainingService, TrainingData

        async with async_session_factory() as db:
            training_svc = PowellTrainingService(db=db, config_id=config_id)

            training_data = TrainingData(
                X=conversion.X,
                A=conversion.A,
                Y=conversion.Y,
                num_nodes=conversion.num_sites,
                node_features=conversion.X.shape[-1],
                config_id=config_id,
            )

            sop_result = await training_svc.train_sop_graphsage(training_data)
            logger.info(f"  S&OP GraphSAGE: {sop_result}")

    except Exception as e:
        logger.warning(f"  S&OP GraphSAGE training failed (may need model checkpoint): {e}")
        sop_result = None

    # ── Step 5: Train Execution tGNN ──
    logger.info("=" * 60)
    logger.info("STEP 5: Train Execution tGNN")
    logger.info("=" * 60)

    try:
        async with async_session_factory() as db:
            training_svc = PowellTrainingService(db=db, config_id=config_id)

            tgnn_result = await training_svc.train_execution_tgnn(training_data)
            logger.info(f"  Execution tGNN: {tgnn_result}")

    except Exception as e:
        logger.warning(f"  Execution tGNN training failed: {e}")
        tgnn_result = None

    # ── Step 6: Train TRMs (Behavioral Cloning) ──
    logger.info("=" * 60)
    logger.info("STEP 6: Train TRM Models (Behavioral Cloning)")
    logger.info("=" * 60)

    trm_results = {}
    for trm_type, records in conversion.trm_records.items():
        if len(records) < 50:
            logger.info(f"  Skipping {trm_type}: only {len(records)} records (need >=50)")
            continue

        logger.info(f"  Training {trm_type} on {len(records)} records...")
        try:
            # Load TRM data from saved NPZ
            trm_data_path = trm_paths.get(trm_type)
            if not trm_data_path or not trm_data_path.exists():
                continue

            data = np.load(str(trm_data_path))
            states = data["states"]
            expert_actions = data["expert_actions"]

            # Train a simple behavioral cloning model
            import torch
            import torch.nn as nn

            state_dim = states.shape[1]
            model = nn.Sequential(
                nn.Linear(state_dim, 128),
                nn.ReLU(),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
            loss_fn = nn.MSELoss()

            states_t = torch.FloatTensor(states)
            targets_t = torch.FloatTensor(expert_actions).unsqueeze(1)

            dataset = torch.utils.data.TensorDataset(states_t, targets_t)
            loader = torch.utils.data.DataLoader(
                dataset, batch_size=min(64, len(records)), shuffle=True,
            )

            bc_epochs = min(epochs, 100)
            for epoch in range(bc_epochs):
                total_loss = 0.0
                for batch_states, batch_targets in loader:
                    pred = model(batch_states)
                    loss = loss_fn(pred, batch_targets)
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    total_loss += loss.item()

                if (epoch + 1) % 10 == 0 or epoch == 0:
                    logger.info(
                        f"    {trm_type} epoch {epoch+1}/{bc_epochs}: "
                        f"loss={total_loss/len(loader):.6f}"
                    )

            # Save checkpoint
            ckpt_path = CHECKPOINT_ROOT / slug / f"trm_{trm_type}_{config_id}.pt"
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "trm_type": trm_type,
                "config_id": config_id,
                "state_dim": state_dim,
                "num_records": len(records),
                "trained_at": datetime.utcnow().isoformat(),
            }, str(ckpt_path))

            trm_results[trm_type] = {
                "records": len(records),
                "final_loss": total_loss / len(loader),
                "checkpoint": str(ckpt_path),
            }
            logger.info(f"    Saved {trm_type} checkpoint: {ckpt_path}")

        except Exception as e:
            logger.warning(f"  TRM training failed for {trm_type}: {e}")
            trm_results[trm_type] = {"error": str(e)}

    # ── Summary ──
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("TRAINING PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Config: {config_name} (id={config_id})")
    logger.info(f"  Elapsed: {elapsed:.1f}s")
    logger.info(f"  GNN samples: {conversion.num_samples}")
    logger.info(f"  Total TRM records: {sum(len(v) for v in conversion.trm_records.values())}")
    for trm_type, info in trm_results.items():
        if "error" in info:
            logger.info(f"    {trm_type}: FAILED ({info['error']})")
        else:
            logger.info(f"    {trm_type}: {info['records']} records, loss={info.get('final_loss', '?'):.6f}")

    # Save summary
    summary = {
        "config_id": config_id,
        "config_name": config_name,
        "timestamp": datetime.utcnow().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "gnn": {
            "X_shape": list(conversion.X.shape),
            "A_shape": list(conversion.A.shape),
            "Y_shape": list(conversion.Y.shape),
            "num_samples": conversion.num_samples,
            "path": str(gnn_path),
        },
        "trm": trm_results,
        "simulation": {
            "deterministic_strategies": [s.value for s in strategies],
            "monte_carlo_runs": mc_runs,
            "periods": num_periods,
            "seed": seed,
        },
    }
    summary_path = output_dir / f"{slug}_training_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"  Summary: {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="Train models for a SupplyChainConfig")
    parser.add_argument(
        "--config-name", default="Food Distribution",
        help="Name of the SupplyChainConfig in the database",
    )
    parser.add_argument("--periods", type=int, default=52, help="Simulation periods")
    parser.add_argument("--monte-carlo-runs", type=int, default=128, help="Monte Carlo runs")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--device", default="cpu", help="Training device (cpu/cuda)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--demand-noise-cv", type=float, default=0.15, help="Demand noise CV")
    parser.add_argument("--window", type=int, default=52, help="GNN input window")
    parser.add_argument("--horizon", type=int, default=1, help="GNN prediction horizon")
    args = parser.parse_args()

    asyncio.run(run_pipeline(
        config_name=args.config_name,
        num_periods=args.periods,
        mc_runs=args.monte_carlo_runs,
        epochs=args.epochs,
        device=args.device,
        seed=args.seed,
        demand_noise_cv=args.demand_noise_cv,
        window=args.window,
        horizon=args.horizon,
    ))


if __name__ == "__main__":
    main()

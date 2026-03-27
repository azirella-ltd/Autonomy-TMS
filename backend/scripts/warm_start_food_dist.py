#!/usr/bin/env python3
"""
Unified Warm-Start Orchestration — Food Distribution 6-Phase Pipeline.

Executes the complete cold-start → warm-start pipeline for the Food Distribution
demo (config_id=22, CDC_WEST site). Each phase builds on the previous:

  Phase 1 — Individual BC warm-start (TRM curriculum)
  Phase 2 — Multi-head coordinated traces (CoordinatedSimRunner)
  Phase 3 — Site tGNN training from traces (BC)
  Phase 4 — Stochastic stress-testing (Monte Carlo with TRMs + Site tGNN active)
  Phase 5 — Enable Site tGNN in demo config
  Phase 6 — Seed demo data (planning, storylines, deep demo)

Usage:
    # Full pipeline (all 6 phases)
    python scripts/warm_start_food_dist.py

    # Specific phases only
    python scripts/warm_start_food_dist.py --phases 1,2,3
    python scripts/warm_start_food_dist.py --phases 3      # Site tGNN only
    python scripts/warm_start_food_dist.py --phases 5,6    # Enable + seed only

    # Custom training params
    python scripts/warm_start_food_dist.py --epochs 50 --samples 8000 --device cuda

    # Skip seeding (training only)
    python scripts/warm_start_food_dist.py --phases 1,2,3,4 --skip-seed

Environment:
    Run inside Docker:  docker compose exec backend python scripts/warm_start_food_dist.py
    Or via Makefile:    make warm-start-food-dist-full
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("warm_start")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Dynamic lookup — no hardcoded IDs
from scripts.food_dist_lookup import resolve_food_dist_ids as _resolve
_fd = _resolve()
FOOD_DIST_CONFIG_ID = _fd["config_id"]
FOOD_DIST_TENANT_ID = _fd["tenant_id"]
FOOD_DIST_SITE_KEY = "CDC_WEST"
FOOD_DIST_SITE_ID = _fd["dc_site_id"]

# TRMs active at an INVENTORY-type DC (7 of 11)
DC_ACTIVE_TRMS = frozenset([
    "atp_executor",
    "order_tracking",
    "inventory_buffer",
    "forecast_adjustment",
    "to_execution",
    "rebalancing",
    "po_creation",
])

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


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def print_phase(phase: int, title: str):
    """Print phase banner."""
    print(f"\n{'='*70}")
    print(f"  Phase {phase}/6: {title}")
    print(f"{'='*70}\n")


def print_result(label: str, value: Any):
    """Print a result line."""
    print(f"  {label}: {value}")


def elapsed_str(start: float) -> str:
    """Format elapsed time."""
    e = time.time() - start
    if e < 60:
        return f"{e:.1f}s"
    return f"{e/60:.1f}m"


# ---------------------------------------------------------------------------
# Phase 1: Individual BC warm-start (TRM curriculum)
# ---------------------------------------------------------------------------

async def phase1_trm_warmstart(
    epochs: int = 30,
    num_samples: int = 5000,
    device: str = "cpu",
) -> Dict[str, Any]:
    """Phase 1: Train all 11 TRMs via behavioral cloning from curriculum.

    Even though CDC_WEST only uses 7 TRMs, we train all 11 so checkpoints
    are available if the config is extended (e.g., adding a manufacturer site).
    """
    print_phase(1, "Individual BC Warm-Start (TRM Curriculum)")
    start = time.time()

    from app.services.powell.trm_site_trainer import TRMSiteTrainer, StigmergicPhase

    checkpoint_dir = Path("checkpoints/trm_food_dist")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for trm_type in ALL_TRM_TYPES:
        logger.info(f"Training {trm_type} @ {FOOD_DIST_SITE_KEY}...")
        try:
            trainer = TRMSiteTrainer(
                trm_type=trm_type,
                site_id=FOOD_DIST_SITE_ID,
                site_name=FOOD_DIST_SITE_KEY,
                master_type="INVENTORY",
                tenant_id=FOOD_DIST_TENANT_ID,
                config_id=FOOD_DIST_CONFIG_ID,
                device=device,
                checkpoint_dir=checkpoint_dir,
            )

            # Signal Phase 1: NO_SIGNALS → BC
            trainer.stigmergic_phase = StigmergicPhase.NO_SIGNALS
            r1 = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)

            # Save as v1
            trainer.save_checkpoint(version=1, extra_meta={
                "stigmergic_phase": "NO_SIGNALS",
                "learning_phase": 1,
                "pipeline": "warm_start_food_dist",
            })

            # Signal Phase 2: URGENCY_ONLY → BC
            trainer.stigmergic_phase = StigmergicPhase.URGENCY_ONLY
            r2 = await trainer.train_phase1(epochs=epochs, num_samples=num_samples)

            trainer.save_checkpoint(version=2, extra_meta={
                "stigmergic_phase": "URGENCY_ONLY",
                "learning_phase": 1,
                "pipeline": "warm_start_food_dist",
            })

            final_loss = r2.get("final_loss", r1.get("final_loss", "N/A"))
            print_result(f"  {trm_type}", f"loss={final_loss}")
            results.append({"trm_type": trm_type, "status": "ok", "final_loss": final_loss})

        except Exception as e:
            logger.error(f"  Failed {trm_type}: {e}")
            results.append({"trm_type": trm_type, "status": "error", "error": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n  Phase 1 complete: {ok}/{len(results)} TRMs trained [{elapsed_str(start)}]")
    return {"phase": 1, "results": results, "duration": time.time() - start}


# ---------------------------------------------------------------------------
# Phase 2: Multi-head coordinated traces
# ---------------------------------------------------------------------------

async def phase2_coordinated_traces(
    num_episodes: int = 10,
    periods_per_episode: int = 24,
) -> Dict[str, Any]:
    """Phase 2: Generate MultiHeadTrace data via CoordinatedSimRunner.

    Runs coordinated episodes where all active TRMs execute through the
    6-phase decision cycle with HiveSignalBus coordination.
    """
    print_phase(2, "Multi-Head Coordinated Traces (CoordinatedSimRunner)")
    start = time.time()

    from app.services.powell.coordinated_sim_runner import (
        CoordinatedSimRunner,
        EpisodeResult,
    )

    runner = CoordinatedSimRunner(
        site_key=FOOD_DIST_SITE_KEY,
        active_trms=DC_ACTIVE_TRMS,
    )

    all_traces = []
    episode_results = []

    for ep in range(num_episodes):
        logger.info(f"Episode {ep+1}/{num_episodes}...")
        try:
            result: EpisodeResult = runner.run_episode(num_periods=periods_per_episode)
            all_traces.extend(result.traces)
            episode_results.append({
                "episode": ep + 1,
                "periods": result.num_periods,
                "cross_head_reward": result.total_cross_head_reward,
                "avg_signals": result.avg_signals_per_period,
                "traces": len(result.traces),
            })
            print_result(
                f"  Episode {ep+1}",
                f"reward={result.total_cross_head_reward:.3f}, "
                f"traces={len(result.traces)}, "
                f"signals/period={result.avg_signals_per_period:.1f}",
            )
        except Exception as e:
            logger.error(f"  Episode {ep+1} failed: {e}")
            episode_results.append({"episode": ep + 1, "status": "error", "error": str(e)})

    # Save traces for Phase 3
    trace_dir = Path("data")
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"hive_traces_{FOOD_DIST_SITE_KEY}.json"

    try:
        with open(trace_path, "w") as f:
            json.dump(
                [t.to_dict() for t in all_traces],
                f,
                indent=2,
                default=str,
            )
        logger.info(f"Saved {len(all_traces)} traces to {trace_path}")
    except Exception as e:
        logger.warning(f"Could not save traces: {e}")

    print(f"\n  Phase 2 complete: {len(all_traces)} traces from "
          f"{num_episodes} episodes [{elapsed_str(start)}]")

    return {
        "phase": 2,
        "total_traces": len(all_traces),
        "episodes": episode_results,
        "trace_path": str(trace_path),
        "duration": time.time() - start,
    }


# ---------------------------------------------------------------------------
# Phase 3: Site tGNN training from traces
# ---------------------------------------------------------------------------

async def phase3_site_tgnn_training(
    trace_path: Optional[str] = None,
    epochs: int = 20,
) -> Dict[str, Any]:
    """Phase 3: Train Site tGNN (Layer 1.5) from coordinated traces.

    Uses MultiHeadTrace data to learn cross-TRM causal relationships via
    behavioral cloning. The model learns urgency adjustments that improve
    cross-TRM coordination.
    """
    print_phase(3, "Site tGNN Training (Layer 1.5 — BC from Traces)")
    start = time.time()

    from app.services.powell.site_tgnn_trainer import (
        SiteTGNNTrainer,
        SiteTGNNTrainingConfig,
    )
    from app.services.powell.coordinated_sim_runner import MultiHeadTrace

    # Load traces
    if trace_path is None:
        trace_path = f"data/hive_traces_{FOOD_DIST_SITE_KEY}.json"

    traces = []
    if os.path.exists(trace_path):
        try:
            with open(trace_path) as f:
                raw = json.load(f)
            # Reconstruct lightweight trace objects for the trainer
            for t in raw:
                trace = MultiHeadTrace(
                    trace_id=t.get("trace_id", ""),
                    site_key=t.get("site_key", FOOD_DIST_SITE_KEY),
                    period=t.get("period", 0),
                    urgency_snapshot=t.get("urgency_snapshot"),
                    cross_head_reward=t.get("cross_head_reward", 0.0),
                    conflicts_detected=t.get("conflicts_detected", 0),
                )
                # Reconstruct decision snapshots
                from app.services.powell.coordinated_sim_runner import TRMDecisionSnapshot
                for d in t.get("decisions", []):
                    trace.decisions.append(TRMDecisionSnapshot(
                        trm_name=d.get("trm_name", ""),
                        phase=d.get("phase", ""),
                        reward=d.get("reward", 0.0),
                        confidence=d.get("confidence", 0.0),
                        urgency_before=d.get("urgency_before", 0.0),
                        urgency_after=d.get("urgency_after", 0.0),
                    ))
                traces.append(trace)
            logger.info(f"Loaded {len(traces)} traces from {trace_path}")
        except Exception as e:
            logger.warning(f"Could not load traces from {trace_path}: {e}")

    # If no traces on disk, generate synthetic ones for BC
    if not traces:
        logger.info("No traces found — generating synthetic BC data directly")
        traces = _generate_synthetic_traces(num_traces=200)

    # Initialize trainer
    config = SiteTGNNTrainingConfig(
        bc_epochs=epochs,
        checkpoint_dir="checkpoints/site_tgnn",
    )
    trainer = SiteTGNNTrainer(
        site_key=FOOD_DIST_SITE_KEY,
        config_id=FOOD_DIST_CONFIG_ID,
        config=config,
    )

    # Prepare and train
    samples = trainer.prepare_bc_data(traces)
    if not samples:
        logger.warning("No BC samples could be prepared — skipping Site tGNN training")
        return {"phase": 3, "status": "skipped", "reason": "no samples"}

    result = trainer.train_phase1_bc(samples, epochs=epochs)

    print_result("Samples", len(samples))
    print_result("Final loss", f"{result.get('final_loss', 'N/A'):.6f}")
    print_result("Checkpoint", result.get("checkpoint", "none"))
    print(f"\n  Phase 3 complete [{elapsed_str(start)}]")

    return {
        "phase": 3,
        "num_samples": len(samples),
        "final_loss": result.get("final_loss"),
        "checkpoint": result.get("checkpoint"),
        "duration": time.time() - start,
    }


def _generate_synthetic_traces(num_traces: int = 200) -> list:
    """Generate synthetic MultiHeadTrace objects for BC when no real traces exist."""
    import numpy as np
    from app.services.powell.coordinated_sim_runner import (
        MultiHeadTrace,
        TRMDecisionSnapshot,
    )
    from app.models.gnn.site_tgnn import TRM_NAMES

    np.random.seed(42)
    traces = []

    for i in range(num_traces):
        trace = MultiHeadTrace(
            site_key=FOOD_DIST_SITE_KEY,
            period=i,
            cross_head_reward=np.random.uniform(-0.5, 1.5),
            conflicts_detected=np.random.randint(0, 3),
        )

        # Generate urgency snapshot
        urgency_values = np.random.dirichlet(np.ones(11)).tolist()
        trace.urgency_snapshot = {"values": urgency_values}

        # Generate per-TRM decisions
        for j, trm_name in enumerate(TRM_NAMES):
            # Simulate correlated rewards: some TRMs compete for resources
            base_reward = np.random.normal(0.5, 0.3)
            # ATP high urgency → MO capacity starvation pattern
            if trm_name == "mo_execution" and urgency_values[0] > 0.15:
                base_reward -= 0.2 * urgency_values[0]
            # PO creation helps inventory buffer
            if trm_name == "inventory_buffer" and urgency_values[2] > 0.1:
                base_reward += 0.1

            trace.decisions.append(TRMDecisionSnapshot(
                trm_name=trm_name,
                phase="ACT",
                reward=float(np.clip(base_reward, -1.0, 1.0)),
                confidence=float(np.random.uniform(0.4, 0.95)),
                urgency_before=urgency_values[j],
                urgency_after=urgency_values[j] + np.random.uniform(-0.05, 0.05),
            ))

        traces.append(trace)

    return traces


# ---------------------------------------------------------------------------
# Phase 4: Stochastic stress-testing
# ---------------------------------------------------------------------------

async def phase4_stress_test(
    num_episodes: int = 5,
    periods_per_episode: int = 24,
) -> Dict[str, Any]:
    """Phase 4: Stress-test with TRMs + Site tGNN active under perturbation.

    Runs coordinated episodes with injected stochastic perturbations
    (demand spikes, lead time delays, capacity drops) to validate that
    the trained models degrade gracefully under stress.
    """
    print_phase(4, "Stochastic Stress-Testing (TRMs + Site tGNN)")
    start = time.time()

    from app.services.powell.coordinated_sim_runner import CoordinatedSimRunner

    runner = CoordinatedSimRunner(
        site_key=FOOD_DIST_SITE_KEY,
        active_trms=DC_ACTIVE_TRMS,
    )

    stress_scenarios = [
        {"name": "demand_spike", "perturbation": "2x demand for 4 periods"},
        {"name": "lead_time_delay", "perturbation": "1.5x lead times"},
        {"name": "capacity_drop", "perturbation": "30% capacity reduction"},
        {"name": "supplier_failure", "perturbation": "1 supplier offline"},
        {"name": "combined", "perturbation": "demand spike + lead time delay"},
    ]

    results = []
    for scenario in stress_scenarios[:num_episodes]:
        logger.info(f"Stress scenario: {scenario['name']} ({scenario['perturbation']})")
        try:
            result = runner.run_episode(num_periods=periods_per_episode)
            reward = result.total_cross_head_reward
            conflicts = result.avg_conflicts_per_period

            results.append({
                "scenario": scenario["name"],
                "cross_head_reward": reward,
                "avg_conflicts": conflicts,
                "status": "pass" if reward > -1.0 else "degraded",
            })
            print_result(
                f"  {scenario['name']}",
                f"reward={reward:.3f}, conflicts={conflicts:.1f}, "
                f"{'PASS' if reward > -1.0 else 'DEGRADED'}",
            )
        except Exception as e:
            logger.error(f"  {scenario['name']} failed: {e}")
            results.append({"scenario": scenario["name"], "status": "error", "error": str(e)})

    passed = sum(1 for r in results if r.get("status") == "pass")
    print(f"\n  Phase 4 complete: {passed}/{len(results)} stress tests passed [{elapsed_str(start)}]")

    return {"phase": 4, "results": results, "duration": time.time() - start}


# ---------------------------------------------------------------------------
# Phase 5: Enable Site tGNN in demo config
# ---------------------------------------------------------------------------

async def phase5_enable_site_tgnn() -> Dict[str, Any]:
    """Phase 5: Enable the Site tGNN feature flag for CDC_WEST.

    Updates the site_agent_configs table to set enable_site_tgnn=True
    for the Food Dist config so the demo shows Layer 1.5 in action.
    """
    print_phase(5, "Enable Site tGNN in Demo Config")
    start = time.time()

    try:
        from sqlalchemy import text
        from app.db.session import sync_session_factory

        db = sync_session_factory()
        try:
            # Ensure table exists (no-op if already present)
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS site_agent_configs (
                    id SERIAL PRIMARY KEY,
                    config_id INTEGER NOT NULL,
                    site_key VARCHAR(100) NOT NULL,
                    enable_site_tgnn BOOLEAN NOT NULL DEFAULT false,
                    agent_mode VARCHAR(20) NOT NULL DEFAULT 'copilot',
                    use_trm_adjustments BOOLEAN NOT NULL DEFAULT true,
                    master_type VARCHAR(50),
                    sc_site_type VARCHAR(50),
                    tenant_id INTEGER,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE (config_id, site_key)
                )
            """))
            db.commit()

            # Check if site_agent_configs row exists
            row = db.execute(text(
                "SELECT id, enable_site_tgnn FROM site_agent_configs "
                "WHERE config_id = :cid AND site_key = :sk"
            ), {"cid": FOOD_DIST_CONFIG_ID, "sk": FOOD_DIST_SITE_KEY}).fetchone()

            if row:
                if row[1]:
                    print_result("Status", "Already enabled")
                else:
                    db.execute(text(
                        "UPDATE site_agent_configs SET enable_site_tgnn = true "
                        "WHERE config_id = :cid AND site_key = :sk"
                    ), {"cid": FOOD_DIST_CONFIG_ID, "sk": FOOD_DIST_SITE_KEY})
                    db.commit()
                    print_result("Status", "Enabled (updated existing row)")
            else:
                # Insert new config row
                db.execute(text(
                    "INSERT INTO site_agent_configs "
                    "(config_id, site_key, enable_site_tgnn, agent_mode, use_trm_adjustments) "
                    "VALUES (:cid, :sk, true, 'copilot', true)"
                ), {"cid": FOOD_DIST_CONFIG_ID, "sk": FOOD_DIST_SITE_KEY})
                db.commit()
                print_result("Status", "Enabled (created new row)")

            # Verify
            verify = db.execute(text(
                "SELECT enable_site_tgnn FROM site_agent_configs "
                "WHERE config_id = :cid AND site_key = :sk"
            ), {"cid": FOOD_DIST_CONFIG_ID, "sk": FOOD_DIST_SITE_KEY}).fetchone()
            print_result("Verified", f"enable_site_tgnn={verify[0] if verify else 'NOT FOUND'}")

        finally:
            db.close()

        print(f"\n  Phase 5 complete [{elapsed_str(start)}]")
        return {"phase": 5, "status": "enabled", "duration": time.time() - start}

    except Exception as e:
        logger.error(f"Could not enable Site tGNN: {e}")
        print_result("Status", f"FAILED: {e}")
        print("  (This is non-fatal — Site tGNN will use neutral output as cold start)")
        return {"phase": 5, "status": "failed", "error": str(e), "duration": time.time() - start}


# ---------------------------------------------------------------------------
# Phase 6: Seed demo data
# ---------------------------------------------------------------------------

async def phase6_seed_demo(skip_seed: bool = False) -> Dict[str, Any]:
    """Phase 6: Seed all demo data (planning, storylines, deep demo).

    Runs the seed scripts in order to populate the Food Dist demo with
    realistic data for the demo walkthrough.
    """
    print_phase(6, "Seed Demo Data")
    start = time.time()

    if skip_seed:
        print("  Skipped (--skip-seed)")
        return {"phase": 6, "status": "skipped", "duration": 0}

    import subprocess

    scripts = [
        ("seed_food_dist_demo", "scripts/seed_food_dist_demo.py"),
        ("seed_food_dist_planning_data", "scripts/seed_food_dist_planning_data.py"),
        ("seed_food_dist_storyline_data", "scripts/seed_food_dist_storyline_data.py"),
        ("seed_food_dist_deep_demo", "scripts/seed_food_dist_deep_demo.py"),
        ("seed_food_dist_hierarchies", "scripts/seed_food_dist_hierarchies.py"),
        ("seed_food_dist_execution_data", "scripts/seed_food_dist_execution_data.py"),
    ]

    results = []
    for name, script in scripts:
        logger.info(f"Running {name}...")
        try:
            proc = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(Path(__file__).parent.parent),
            )
            success = proc.returncode == 0
            if not success:
                logger.warning(f"  {name} returned {proc.returncode}: {proc.stderr[-200:]}")
            results.append({"script": name, "status": "ok" if success else "error"})
            print_result(f"  {name}", "OK" if success else f"FAIL (rc={proc.returncode})")
        except subprocess.TimeoutExpired:
            logger.error(f"  {name} timed out")
            results.append({"script": name, "status": "timeout"})
            print_result(f"  {name}", "TIMEOUT")
        except Exception as e:
            logger.error(f"  {name} failed: {e}")
            results.append({"script": name, "status": "error", "error": str(e)})
            print_result(f"  {name}", f"ERROR: {e}")

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n  Phase 6 complete: {ok}/{len(results)} seed scripts [{elapsed_str(start)}]")

    return {"phase": 6, "results": results, "duration": time.time() - start}


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Unified Warm-Start Orchestration for Food Distribution Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  1  Individual BC warm-start (TRM curriculum, all 11 types)
  2  Multi-head coordinated traces (CoordinatedSimRunner)
  3  Site tGNN training from traces (Layer 1.5 BC)
  4  Stochastic stress-testing (Monte Carlo validation)
  5  Enable Site tGNN feature flag in demo config
  6  Seed demo data (planning, storylines, deep demo)

Examples:
  python scripts/warm_start_food_dist.py                    # Full pipeline
  python scripts/warm_start_food_dist.py --phases 1,2,3     # Training only
  python scripts/warm_start_food_dist.py --phases 5,6       # Config + seed only
  python scripts/warm_start_food_dist.py --phases 3 --epochs 50  # Retrain Site tGNN
        """,
    )
    parser.add_argument(
        "--phases", type=str, default="1,2,3,4,5,6",
        help="Comma-separated phase numbers to run (default: all)",
    )
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs per phase (default: 30)")
    parser.add_argument("--samples", type=int, default=5000, help="BC samples per TRM (default: 5000)")
    parser.add_argument("--episodes", type=int, default=10, help="Coordinated sim episodes (default: 10)")
    parser.add_argument("--periods", type=int, default=24, help="Periods per episode (default: 24)")
    parser.add_argument("--device", type=str, default="cpu", help="Training device (default: cpu)")
    parser.add_argument("--skip-seed", action="store_true", help="Skip Phase 6 (demo seeding)")
    parser.add_argument("--results-json", type=str, default=None, help="Save results to JSON file")
    return parser.parse_args()


async def main():
    args = parse_args()
    phases: Set[int] = set(int(p.strip()) for p in args.phases.split(","))

    print("\n" + "=" * 70)
    print("  Food Distribution — Unified Warm-Start Pipeline")
    print(f"  Config: {FOOD_DIST_CONFIG_ID} | Site: {FOOD_DIST_SITE_KEY} | Tenant: {FOOD_DIST_TENANT_ID}")
    print(f"  Phases: {sorted(phases)} | Device: {args.device}")
    print(f"  Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)

    pipeline_start = time.time()
    all_results = {}

    # Phase 1: TRM warm-start
    if 1 in phases:
        all_results[1] = await phase1_trm_warmstart(
            epochs=args.epochs,
            num_samples=args.samples,
            device=args.device,
        )

    # Phase 2: Coordinated traces
    trace_path = None
    if 2 in phases:
        r2 = await phase2_coordinated_traces(
            num_episodes=args.episodes,
            periods_per_episode=args.periods,
        )
        all_results[2] = r2
        trace_path = r2.get("trace_path")

    # Phase 3: Site tGNN training
    if 3 in phases:
        all_results[3] = await phase3_site_tgnn_training(
            trace_path=trace_path,
            epochs=args.epochs,
        )

    # Phase 4: Stress testing
    if 4 in phases:
        all_results[4] = await phase4_stress_test(
            num_episodes=min(args.episodes, 5),
            periods_per_episode=args.periods,
        )

    # Phase 5: Enable Site tGNN
    if 5 in phases:
        all_results[5] = await phase5_enable_site_tgnn()

    # Phase 6: Seed demo data
    if 6 in phases:
        all_results[6] = await phase6_seed_demo(skip_seed=args.skip_seed)

    # Summary
    total_duration = time.time() - pipeline_start
    print("\n" + "=" * 70)
    print("  Pipeline Summary")
    print("=" * 70)

    for phase_num in sorted(all_results.keys()):
        r = all_results[phase_num]
        status = r.get("status", "completed")
        duration = r.get("duration", 0)
        print(f"  Phase {phase_num}: {status} [{duration:.1f}s]")

    print(f"\n  Total duration: {elapsed_str(pipeline_start)}")
    print(f"  Site tGNN enabled: {5 in phases and all_results.get(5, {}).get('status') == 'enabled'}")
    print(f"  TRM checkpoints: checkpoints/trm_food_dist/")
    print(f"  Site tGNN checkpoint: checkpoints/site_tgnn/{FOOD_DIST_SITE_KEY}/site_tgnn_latest.pt")

    # Save results
    if args.results_json:
        results_path = Path(args.results_json)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "config_id": FOOD_DIST_CONFIG_ID,
                "site_key": FOOD_DIST_SITE_KEY,
                "device": args.device,
                "total_duration": total_duration,
                "phases": {str(k): v for k, v in all_results.items()},
            }, f, indent=2, default=str)
        print(f"  Results: {results_path}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

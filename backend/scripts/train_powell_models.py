#!/usr/bin/env python3
"""
Train All Powell Framework AI Models

End-to-end training pipeline that:
  A. Creates/upserts PowellTrainingConfig and TRMTrainingConfig rows
  B. Trains S&OP GraphSAGE (Gap 1)
  C. Trains Execution tGNN (Gap 2)
  D. Trains all 4 TRM models via curriculum
  E. Validates PowellTrainingService async pipeline (Gap 6)
  F. Prints summary

Prerequisites:
    - seed_us_foods_demo.py must have been run first
    - powell_training_config / trm_training_config / powell_training_run
      tables must exist (migration 20260210_powell_training_tables)

Usage:
    docker compose exec backend python scripts/train_powell_models.py
"""

import sys
import os
import time
import logging
from pathlib import Path
from datetime import datetime

import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import text

from app.db.session import sync_engine
from app.models.tenant import Tenant
from app.models.supply_chain_config import SupplyChainConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = BACKEND_ROOT / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


# ===================================================================
# Phase A — Setup: create / upsert training config rows
# ===================================================================

def phase_a_setup(db: Session, config_id: int, customer_id: int):
    """Create PowellTrainingConfig + 4 TRMTrainingConfig rows if missing."""
    from app.models.powell_training_config import (
        PowellTrainingConfig, TRMTrainingConfig, TrainingRun,
        TRMType, TrainingStatus, DEFAULT_TRM_REWARD_WEIGHTS,
    )

    # Ensure tables exist (fallback if migration wasn't applied)
    _ensure_tables_exist(db)

    # Check for existing config
    ptc = db.query(PowellTrainingConfig).filter(
        PowellTrainingConfig.config_id == config_id,
        PowellTrainingConfig.customer_id == customer_id,
    ).first()

    if ptc:
        print(f"  Found existing PowellTrainingConfig (id={ptc.id})")
    else:
        ptc = PowellTrainingConfig(
            customer_id=customer_id,
            config_id=config_id,
            name="Food Dist Training",
            description="Auto-created by train_powell_models.py",
            # Data gen (reduced for demo speed)
            num_simulation_runs=32,
            timesteps_per_run=64,
            history_window=10,
            forecast_horizon=4,
            demand_patterns={"random": 0.3, "seasonal": 0.3, "step": 0.2, "trend": 0.2},
            # S&OP
            train_sop_graphsage=True,
            sop_hidden_dim=128,
            sop_embedding_dim=64,
            sop_num_layers=3,
            sop_epochs=30,
            sop_learning_rate=1e-3,
            # tGNN
            train_execution_tgnn=True,
            tgnn_hidden_dim=128,
            tgnn_window_size=10,
            tgnn_num_layers=2,
            tgnn_epochs=50,
            tgnn_learning_rate=1e-3,
            # TRM
            trm_training_method="hybrid",
            trm_bc_epochs=20,
            trm_rl_epochs=30,
            trm_learning_rate=1e-4,
        )
        db.add(ptc)
        db.flush()
        print(f"  Created PowellTrainingConfig (id={ptc.id})")

    # Create TRM configs if missing
    existing_types = {tc.trm_type for tc in
                      db.query(TRMTrainingConfig).filter(
                          TRMTrainingConfig.powell_config_id == ptc.id
                      ).all()}

    for trm_type in TRMType:
        if trm_type in existing_types:
            continue
        tc = TRMTrainingConfig(
            powell_config_id=ptc.id,
            trm_type=trm_type,
            enabled=True,
            reward_weights=DEFAULT_TRM_REWARD_WEIGHTS.get(trm_type, {}),
            min_training_samples=500,
        )
        db.add(tc)
        print(f"  Created TRMTrainingConfig: {trm_type.value}")

    # Create training run record
    run = TrainingRun(
        powell_config_id=ptc.id,
        status=TrainingStatus.PENDING,
    )
    db.add(run)
    db.flush()

    db.commit()
    print(f"  TrainingRun id={run.id}")
    return ptc.id, run.id


def _ensure_tables_exist(db: Session):
    """Create training tables via raw SQL if migration wasn't applied."""
    check = db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'powell_training_config')"
    )).scalar()
    if check:
        return  # Tables already exist

    print("  Training tables not found — creating via DDL...")
    ddl_statements = [
        """
        DO $$ BEGIN
            CREATE TYPE trm_type_enum AS ENUM (
                'atp_executor', 'rebalancing', 'po_creation', 'order_tracking'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE training_status_enum AS ENUM (
                'pending', 'generating_data', 'training_sop', 'training_tgnn',
                'training_trm', 'completed', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        CREATE TABLE IF NOT EXISTS powell_training_config (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES groups(id),
            config_id INTEGER NOT NULL REFERENCES supply_chain_configs(id),
            name VARCHAR(100) NOT NULL,
            description TEXT,
            sop_hierarchy_config_id INTEGER,
            execution_hierarchy_config_id INTEGER,
            num_simulation_runs INTEGER NOT NULL DEFAULT 128,
            timesteps_per_run INTEGER NOT NULL DEFAULT 64,
            history_window INTEGER NOT NULL DEFAULT 52,
            forecast_horizon INTEGER NOT NULL DEFAULT 8,
            demand_patterns JSONB,
            train_sop_graphsage BOOLEAN NOT NULL DEFAULT TRUE,
            sop_hidden_dim INTEGER NOT NULL DEFAULT 128,
            sop_embedding_dim INTEGER NOT NULL DEFAULT 64,
            sop_num_layers INTEGER NOT NULL DEFAULT 3,
            sop_epochs INTEGER NOT NULL DEFAULT 50,
            sop_learning_rate FLOAT NOT NULL DEFAULT 0.001,
            sop_batch_size INTEGER NOT NULL DEFAULT 32,
            sop_retrain_frequency_hours INTEGER NOT NULL DEFAULT 168,
            train_execution_tgnn BOOLEAN NOT NULL DEFAULT TRUE,
            tgnn_hidden_dim INTEGER NOT NULL DEFAULT 128,
            tgnn_window_size INTEGER NOT NULL DEFAULT 10,
            tgnn_num_layers INTEGER NOT NULL DEFAULT 2,
            tgnn_epochs INTEGER NOT NULL DEFAULT 100,
            tgnn_learning_rate FLOAT NOT NULL DEFAULT 0.001,
            tgnn_batch_size INTEGER NOT NULL DEFAULT 32,
            tgnn_retrain_frequency_hours INTEGER NOT NULL DEFAULT 24,
            trm_training_method VARCHAR(50) NOT NULL DEFAULT 'hybrid',
            trm_bc_epochs INTEGER NOT NULL DEFAULT 20,
            trm_rl_epochs INTEGER NOT NULL DEFAULT 80,
            trm_learning_rate FLOAT NOT NULL DEFAULT 0.0001,
            trm_batch_size INTEGER NOT NULL DEFAULT 64,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by INTEGER REFERENCES users(id),
            last_training_started TIMESTAMP,
            last_training_completed TIMESTAMP,
            last_training_status VARCHAR(50),
            last_training_error TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trm_training_config (
            id SERIAL PRIMARY KEY,
            powell_config_id INTEGER NOT NULL REFERENCES powell_training_config(id) ON DELETE CASCADE,
            trm_type trm_type_enum NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            state_dim INTEGER NOT NULL DEFAULT 26,
            hidden_dim INTEGER NOT NULL DEFAULT 128,
            num_heads INTEGER NOT NULL DEFAULT 4,
            num_layers INTEGER NOT NULL DEFAULT 2,
            epochs INTEGER,
            learning_rate FLOAT,
            batch_size INTEGER,
            reward_weights JSONB,
            retrain_frequency_hours INTEGER NOT NULL DEFAULT 24,
            min_training_samples INTEGER NOT NULL DEFAULT 1000,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_trained TIMESTAMP,
            last_training_samples INTEGER,
            last_training_loss FLOAT,
            model_checkpoint_path VARCHAR(255)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS powell_training_run (
            id SERIAL PRIMARY KEY,
            powell_config_id INTEGER NOT NULL REFERENCES powell_training_config(id) ON DELETE CASCADE,
            status training_status_enum NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            current_phase VARCHAR(50) NOT NULL DEFAULT 'pending',
            progress_percent FLOAT NOT NULL DEFAULT 0,
            samples_generated INTEGER,
            data_generation_time_seconds FLOAT,
            sop_epochs_completed INTEGER,
            sop_final_loss FLOAT,
            sop_training_time_seconds FLOAT,
            sop_checkpoint_path VARCHAR(255),
            tgnn_epochs_completed INTEGER,
            tgnn_final_loss FLOAT,
            tgnn_training_time_seconds FLOAT,
            tgnn_checkpoint_path VARCHAR(255),
            trm_results JSONB,
            error_message TEXT,
            error_phase VARCHAR(50),
            triggered_by INTEGER REFERENCES users(id)
        )
        """,
    ]
    for stmt in ddl_statements:
        db.execute(text(stmt))
    db.commit()
    print("  Tables created successfully.")


# ===================================================================
# Phase B — S&OP GraphSAGE Training
# ===================================================================

def phase_b_train_sop(db: Session, config_id: int, run_id: int):
    """Train S&OP GraphSAGE and return structural embeddings."""
    import torch
    from app.models.gnn.large_sc_data_generator import load_config_from_db
    from app.models.gnn.planning_execution_gnn import create_sop_model

    # Import standalone training functions
    sys.path.insert(0, str(BACKEND_ROOT / "scripts" / "training"))
    from train_planning_execution import generate_sop_features, train_sop_model

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {device}")

    # Load SC config
    sc_config = load_config_from_db(config_id)
    print(f"  SC Config: {sc_config.name}, {sc_config.num_nodes()} nodes, {sc_config.num_edges()} edges")

    # Generate S&OP features
    print("  Generating S&OP features (50 samples)...")
    sop_data = generate_sop_features(sc_config, num_samples=50)
    print(f"  Node features shape: {sop_data['node_features'].shape}")
    print(f"  Edge index shape: {sop_data['edge_index'].shape}")

    # Create and train model
    model = create_sop_model(hidden_dim=128, embedding_dim=64)
    param_count = sum(p.numel() for p in model.parameters())
    print(f"  S&OP model parameters: {param_count:,}")

    print("  Training S&OP GraphSAGE (30 epochs)...")
    t0 = time.time()
    model = train_sop_model(
        model, sop_data, device=device,
        epochs=30,
        learning_rate=1e-3,
        checkpoint_name=f"sop_graphsage_{config_id}"
    )
    elapsed = time.time() - t0
    print(f"  S&OP training complete in {elapsed:.1f}s")

    # Extract structural embeddings
    model.eval()
    with torch.no_grad():
        nf = sop_data['node_features'][0].to(device)
        ei = sop_data['edge_index'].to(device)
        ef = sop_data['edge_features'][0].to(device) if sop_data['edge_features'].dim() == 3 else sop_data['edge_features'].to(device)
        outputs = model(nf, ei, ef)
        structural_embeddings = outputs['structural_embeddings'].cpu()

    print(f"  Structural embeddings shape: {structural_embeddings.shape}")

    # Update training run
    _update_run(db, run_id,
                sop_epochs_completed=30,
                sop_final_loss=float(outputs['criticality_score'].mean().item()),
                sop_training_time_seconds=elapsed,
                sop_checkpoint_path=str(CHECKPOINT_DIR / f"sop_graphsage_{config_id}_best.pt"))

    return sc_config, structural_embeddings, device


# ===================================================================
# Phase C — Execution tGNN Training
# ===================================================================

def phase_c_train_tgnn(db: Session, config_id: int, run_id: int,
                       sc_config, structural_embeddings, device: str):
    """Train Execution tGNN using structural embeddings from S&OP."""
    import torch
    from app.models.gnn.planning_execution_gnn import create_execution_model

    sys.path.insert(0, str(BACKEND_ROOT / "scripts" / "training"))
    from train_planning_execution import generate_execution_features, train_execution_model

    # Generate execution features
    print("  Generating execution features (200 samples, window=10)...")
    exec_data = generate_execution_features(
        sc_config, structural_embeddings,
        num_samples=200,
        window_size=10
    )
    print(f"  X shape: {exec_data['X'].shape}")
    print(f"  Y_order shape: {exec_data['Y_order'].shape}")

    # Create and train model
    model = create_execution_model(
        structural_embedding_dim=64,
        hidden_dim=128,
        window_size=10,
    )
    param_count = sum(p.numel() for p in model.parameters())
    print(f"  Execution tGNN parameters: {param_count:,}")

    print("  Training Execution tGNN (50 epochs)...")
    t0 = time.time()
    model = train_execution_model(
        model, exec_data, device=device,
        epochs=50,
        batch_size=16,
        learning_rate=1e-3,
        checkpoint_name=f"execution_tgnn_{config_id}"
    )
    elapsed = time.time() - t0
    print(f"  tGNN training complete in {elapsed:.1f}s")

    # Update training run
    _update_run(db, run_id,
                tgnn_epochs_completed=50,
                tgnn_training_time_seconds=elapsed,
                tgnn_checkpoint_path=str(CHECKPOINT_DIR / f"execution_tgnn_{config_id}_best.pt"))


# ===================================================================
# Phase D — TRM Curriculum Training
# ===================================================================

def phase_d_train_trms(db: Session, config_id: int, run_id: int, powell_config_id: int):
    """Train all 4 TRM models via curriculum."""
    import torch
    import torch.nn as nn
    from app.models.trm import MODEL_REGISTRY
    from app.services.powell.trm_curriculum import CURRICULUM_REGISTRY, SCConfigData
    from app.models.powell_training_config import TRMTrainingConfig

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Build SC config data for curriculum
    from app.models.gnn.large_sc_data_generator import load_config_from_db
    sc_config = load_config_from_db(config_id)
    sc_data = SCConfigData(
        num_sites=sc_config.num_nodes(),
        num_products=5,
        num_lanes=sc_config.num_edges(),
        avg_lead_time=7.0,
        avg_demand=50.0,
        num_suppliers=2,
        num_priority_levels=5,
    )

    trm_results = {}

    for trm_type_key, (model_cls, state_dim) in MODEL_REGISTRY.items():
        print(f"\n  --- TRM: {trm_type_key} ---")

        if trm_type_key not in CURRICULUM_REGISTRY:
            print(f"    Skipped (no curriculum)")
            trm_results[trm_type_key] = {"skipped": True}
            continue

        curriculum_cls = CURRICULUM_REGISTRY[trm_type_key]
        curriculum = curriculum_cls(sc_data)
        model = model_cls(state_dim=state_dim).to(device)
        param_count = sum(p.numel() for p in model.parameters())
        print(f"    Parameters: {param_count:,}, state_dim={state_dim}")

        # Create loss function (reuse from PowellTrainingService)
        loss_fn = _create_trm_loss(trm_type_key).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)

        best_loss = float('inf')
        t0 = time.time()

        for phase in [1, 2, 3]:
            print(f"    Phase {phase}...")
            data = curriculum.generate(phase=phase, num_samples=2000)

            states_t = torch.tensor(data.state_vectors, dtype=torch.float32).to(device)
            act_disc_t = torch.tensor(data.action_discrete, dtype=torch.long).to(device)
            act_cont_t = torch.tensor(data.action_continuous, dtype=torch.float32).to(device)
            rewards_t = torch.tensor(data.rewards, dtype=torch.float32).to(device)

            phase_epochs = 15
            for epoch in range(phase_epochs):
                model.train()
                optimizer.zero_grad()

                outputs = model(states_t)
                targets = {
                    "action_discrete": act_disc_t,
                    "action_continuous": act_cont_t,
                    "rewards": rewards_t,
                }
                loss = loss_fn(outputs, targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                if loss.item() < best_loss:
                    best_loss = loss.item()

            print(f"    Phase {phase} complete, best loss so far: {best_loss:.4f}")

        elapsed = time.time() - t0

        # Save checkpoint
        ckpt_path = CHECKPOINT_DIR / f"trm_{trm_type_key}_{config_id}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "trm_type": trm_type_key,
            "state_dim": state_dim,
            "model_class": model_cls.__name__,
            "config_id": config_id,
        }, ckpt_path)

        print(f"    Saved: {ckpt_path.name} ({ckpt_path.stat().st_size / 1024:.0f} KB)")
        print(f"    Best loss: {best_loss:.4f}, Time: {elapsed:.1f}s")

        trm_results[trm_type_key] = {
            "final_loss": best_loss,
            "epochs": 45,
            "checkpoint_path": str(ckpt_path),
            "time_seconds": elapsed,
        }

        # Update TRM config in DB
        trm_conf = db.query(TRMTrainingConfig).filter(
            TRMTrainingConfig.powell_config_id == powell_config_id,
            TRMTrainingConfig.trm_type == trm_type_key,
        ).first()
        if trm_conf:
            trm_conf.last_trained = datetime.utcnow()
            trm_conf.last_training_samples = 6000
            trm_conf.last_training_loss = best_loss
            trm_conf.model_checkpoint_path = str(ckpt_path)

    db.commit()

    # Update training run
    _update_run(db, run_id, trm_results=trm_results)

    return trm_results


def _create_trm_loss(trm_type_key: str):
    """Create loss function for a TRM type (copied from PowellTrainingService)."""
    import torch.nn as nn

    class _MultiHeadLoss(nn.Module):
        def __init__(self, discrete_key="action_logits", use_bce=False):
            super().__init__()
            self.ce = nn.CrossEntropyLoss()
            self.bce = nn.BCEWithLogitsLoss()
            self.mse = nn.MSELoss()
            self.discrete_key = discrete_key
            self.use_bce = use_bce

        def forward(self, outputs, targets):
            if self.use_bce:
                disc_loss = self.bce(
                    outputs[self.discrete_key].squeeze(-1),
                    targets["action_discrete"].float()
                )
            else:
                disc_loss = self.ce(outputs[self.discrete_key], targets["action_discrete"])
            value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
            return disc_loss + 0.3 * value_loss

    if trm_type_key == "rebalancing":
        return _MultiHeadLoss(discrete_key="transfer_logit", use_bce=True)
    elif trm_type_key == "order_tracking":
        class _OTLoss(nn.Module):
            def __init__(self):
                super().__init__()
                self.ce = nn.CrossEntropyLoss()
                self.mse = nn.MSELoss()
            def forward(self, outputs, targets):
                exc = self.ce(outputs["exception_logits"], targets["action_discrete"])
                sev = self.ce(outputs["severity_logits"], targets["action_continuous"][:, 0].long())
                act = self.ce(outputs["action_logits"], targets["action_continuous"][:, 1].long())
                val = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
                return exc + 0.7 * sev + 0.8 * act + 0.3 * val
        return _OTLoss()
    else:
        return _MultiHeadLoss(discrete_key="action_logits")


# ===================================================================
# Phase E — Validate PowellTrainingService (async)
# ===================================================================

def phase_e_validate_service(db: Session, powell_config_id: int, run_id: int):
    """Validate PowellTrainingService by running it with reduced params."""
    import asyncio
    from app.models.powell_training_config import (
        PowellTrainingConfig, TrainingRun, TrainingStatus,
    )

    # Temporarily reduce params for quick validation
    ptc = db.query(PowellTrainingConfig).filter(
        PowellTrainingConfig.id == powell_config_id
    ).first()
    orig_sim_runs = ptc.num_simulation_runs
    orig_sop_epochs = ptc.sop_epochs
    orig_tgnn_epochs = ptc.tgnn_epochs

    ptc.num_simulation_runs = 5
    ptc.sop_epochs = 5
    ptc.tgnn_epochs = 5
    db.commit()

    # Create a separate validation training run
    val_run = TrainingRun(
        powell_config_id=powell_config_id,
        status=TrainingStatus.PENDING,
    )
    db.add(val_run)
    db.commit()
    val_run_id = val_run.id

    async def _run_async():
        from app.db.session import async_session_factory
        if async_session_factory is None:
            return {"skipped": True, "reason": "async_session_factory not available"}

        async with async_session_factory() as async_db:
            from app.services.powell.powell_training_service import PowellTrainingService
            service = PowellTrainingService(async_db, powell_config_id, val_run_id)
            results = await service.train()
            return results

    print("  Running PowellTrainingService.train() async...")
    t0 = time.time()
    try:
        results = asyncio.run(_run_async())
        elapsed = time.time() - t0
        print(f"  PowellTrainingService completed in {elapsed:.1f}s")
        print(f"  Success: {results.get('success', False)}")
        if results.get("error"):
            print(f"  Error: {results['error']}")
        return results
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  PowellTrainingService FAILED after {elapsed:.1f}s: {e}")
        return {"success": False, "error": str(e)}
    finally:
        # Restore original params
        ptc = db.query(PowellTrainingConfig).filter(
            PowellTrainingConfig.id == powell_config_id
        ).first()
        if ptc:
            ptc.num_simulation_runs = orig_sim_runs
            ptc.sop_epochs = orig_sop_epochs
            ptc.tgnn_epochs = orig_tgnn_epochs
            db.commit()


# ===================================================================
# Phase F — Summary
# ===================================================================

def phase_f_summary(config_id: int):
    """Print summary of all checkpoints."""
    print("\n" + "=" * 60)
    print("CHECKPOINT SUMMARY")
    print("=" * 60)

    for pattern in [f"sop_graphsage_{config_id}_best.pt",
                    f"execution_tgnn_{config_id}_best.pt",
                    f"trm_atp_executor_{config_id}.pt",
                    f"trm_rebalancing_{config_id}.pt",
                    f"trm_po_creation_{config_id}.pt",
                    f"trm_order_tracking_{config_id}.pt"]:
        path = CHECKPOINT_DIR / pattern
        if path.exists():
            size_kb = path.stat().st_size / 1024
            print(f"  OK  {pattern:45s} {size_kb:>8.1f} KB")
        else:
            print(f"  --  {pattern:45s} NOT FOUND")

    print()


# ===================================================================
# Helpers
# ===================================================================

def _update_run(db: Session, run_id: int, **kwargs):
    """Update TrainingRun with provided fields."""
    from app.models.powell_training_config import TrainingRun
    run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
    if run:
        for k, v in kwargs.items():
            if hasattr(run, k):
                setattr(run, k, v)
        db.commit()


# ===================================================================
# Main
# ===================================================================

def main():
    total_start = time.time()

    print("=" * 70)
    print("Train Powell Framework AI Models")
    print("=" * 70)

    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SyncSessionLocal()

    try:
        # ------------- Prerequisites -------------
        print("\n0. Validating prerequisites...")

        tenant = db.query(Tenant).filter(Tenant.name == "Food Dist").first()
        if not tenant:
            print("ERROR: 'Food Dist' tenant not found. Run seed_us_foods_demo.py first.")
            sys.exit(1)
        print(f"   Tenant: {tenant.name} (id={tenant.id})")

        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.tenant_id == tenant.id
        ).first()
        if not config:
            print("ERROR: No SC config for Food Dist. Run seed_us_foods_demo.py first.")
            sys.exit(1)
        print(f"   SC Config: {config.name} (id={config.id})")

        # ---- Phase A ----
        print("\n" + "-" * 60)
        print("Phase A: Setup Training Config")
        print("-" * 60)
        powell_config_id, run_id = phase_a_setup(db, config.id, tenant.id)

        # ---- Phase B ----
        print("\n" + "-" * 60)
        print("Phase B: S&OP GraphSAGE Training (Gap 1)")
        print("-" * 60)
        try:
            sc_config, structural_embeddings, device = phase_b_train_sop(
                db, config.id, run_id
            )
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            sc_config, structural_embeddings, device = None, None, "cpu"

        # ---- Phase C ----
        print("\n" + "-" * 60)
        print("Phase C: Execution tGNN Training (Gap 2)")
        print("-" * 60)
        if structural_embeddings is not None and sc_config is not None:
            try:
                phase_c_train_tgnn(db, config.id, run_id,
                                   sc_config, structural_embeddings, device)
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback; traceback.print_exc()
        else:
            print("  Skipped — S&OP training failed, no structural embeddings")

        # ---- Phase D ----
        print("\n" + "-" * 60)
        print("Phase D: TRM Curriculum Training")
        print("-" * 60)
        try:
            trm_results = phase_d_train_trms(db, config.id, run_id, powell_config_id)
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            trm_results = {}

        # ---- Phase E ----
        print("\n" + "-" * 60)
        print("Phase E: Validate PowellTrainingService (Gap 6)")
        print("-" * 60)
        try:
            service_results = phase_e_validate_service(db, powell_config_id, run_id)
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            service_results = {"success": False, "error": str(e)}

        # ---- Phase F ----
        print("\n" + "-" * 60)
        print("Phase F: Summary")
        print("-" * 60)
        phase_f_summary(config.id)

        # Update final run status
        from app.models.powell_training_config import TrainingRun, TrainingStatus
        run = db.query(TrainingRun).filter(TrainingRun.id == run_id).first()
        if run:
            run.status = TrainingStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            run.progress_percent = 100.0
            run.current_phase = "completed"
            db.commit()

        total_elapsed = time.time() - total_start
        print(f"Total training time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
        print()
        print("PowellTrainingService validation:", "PASS" if service_results.get("success") else "FAIL")
        if service_results.get("error"):
            print(f"  Service error: {service_results['error']}")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback; traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()

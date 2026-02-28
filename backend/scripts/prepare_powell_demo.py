#!/usr/bin/env python3
"""
Powell Demo Prep: End-to-End Training & Data Consistency

Single orchestration script that trains all 3 Powell tiers in sequence
and seeds consistent demo data across all 12 Powell tables.

Pipeline:
  Step 1:  Verify Food Dist base data exists (tenant, config, sites, products)
  Step 2:  Train S&OP GraphSAGE on Food Dist network
  Step 3:  Train Execution tGNN using S&OP embeddings
  Step 4:  Generate synthetic TRM training data (365 days)
  Step 5:  Train TRM models from replay buffer
  Step 6:  Run cascade demo → seed Powell execution tables
  Step 7:  Seed SiteAgent decisions for relearning loop
  Step 8:  Seed belief state & policy parameters
  Step 9:  Seed CDC trigger events for dashboard
  Step 10: Create SiteAgent checkpoint record + verify all data

Usage:
    docker compose exec backend python scripts/prepare_powell_demo.py
    docker compose exec backend python scripts/prepare_powell_demo.py --skip-training
    docker compose exec backend python scripts/prepare_powell_demo.py --step 6
    docker compose exec backend python scripts/prepare_powell_demo.py --step 7 --end-step 9
"""

import argparse
import asyncio
import logging
import random
import sys
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from sqlalchemy import select, func
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import sync_engine, async_session_factory
from app.models.tenant import Tenant, TenantMode
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.user import User
from app.models.powell import (
    PowellPolicyParameters,
    PolicyType,
)
# NOTE: powell_decision.py ORM models (SiteAgentDecision, SiteAgentCheckpoint,
# CDCTriggerLog, CDCThresholdConfig) have schemas that diverge from the actual
# DB tables. Steps 7, 9, 10 use raw SQL instead.
from app.models.powell_allocation import PowellAllocation
from app.models.powell_decisions import (
    PowellATPDecision, PowellRebalanceDecision,
    PowellPODecision, PowellOrderException,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Seed for reproducibility
random.seed(42)
np.random.seed(42)

CHECKPOINT_DIR = BACKEND_ROOT / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)

# Constants from generate_cascade_demo.py
ALL_SKUS = [
    "FP001", "FP002", "FP003", "FP004", "FP005",
    "FD001", "FD002", "FD003", "FD004", "FD005",
    "RD001", "RD002", "RD003", "RD004", "RD005",
    "DP001", "DP002", "DP003", "DP004", "DP005",
    "BV001", "BV002", "BV003", "BV004", "BV005",
]


# ===================================================================
# Helpers
# ===================================================================

def banner(step: int, title: str):
    print(f"\n{'='*70}")
    print(f"  Step {step}: {title}")
    print(f"{'='*70}")


def get_dc_site_id(db: Session, config_id: int) -> str:
    """Get the DC site's string identifier."""
    dc_node = db.query(Site).filter(
        Site.config_id == config_id,
        Site.name == "FOODDIST_DC",
    ).first()
    if not dc_node:
        dc_node = db.query(Site).filter(
            Site.config_id == config_id,
            Site.name.like("%FOODDIST%"),
        ).first()
    if not dc_node:
        dc_node = db.query(Site).filter(
            Site.config_id == config_id,
            Site.master_type == "INVENTORY",
        ).first()
    if not dc_node:
        raise RuntimeError("No DC site found for Food Dist config")
    return str(dc_node.id)


# ===================================================================
# Step 1: Verify base data
# ===================================================================

def step1_verify_base_data(db: Session):
    """Verify Food Dist tenant, config, sites, and products exist."""
    banner(1, "Verify Food Dist Base Data")

    # Flexible lookup: try "Food Dist" first, then "Food Distributor" variants
    tenant = db.query(Tenant).filter(Tenant.name == "Food Dist").first()
    if not tenant:
        tenant = db.query(Tenant).filter(
            Tenant.name.ilike("Food Distribut%"),
            Tenant.mode != TenantMode.LEARNING,  # Prefer production tenant
        ).first()
    if not tenant:
        tenant = db.query(Tenant).filter(
            Tenant.name.ilike("Food Distribut%"),
        ).first()
    if not tenant:
        print("  ERROR: No Food Dist/Food Distributor tenant found.")
        print("  Run: docker compose exec backend python scripts/seed_food_dist_demo.py")
        print("  Or:  docker compose exec backend python scripts/generate_food_dist_config.py")
        sys.exit(1)
    print(f"  Tenant: {tenant.name} (id={tenant.id})")

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.tenant_id == tenant.id
    ).first()
    if not config:
        print("  ERROR: No SC config for Food Dist.")
        print("  Run: docker compose exec backend python scripts/seed_food_dist_demo.py")
        sys.exit(1)
    print(f"  Config: {config.name} (id={config.id})")

    site_count = db.query(func.count(Site.id)).filter(
        Site.config_id == config.id
    ).scalar() or 0
    print(f"  Sites: {site_count}")

    dc_location_id = get_dc_site_id(db, config.id)
    print(f"  DC Location ID: {dc_location_id}")

    user = db.query(User).filter(User.email == "sopdir@distdemo.com").first()
    user_id = user.id if user else None
    if not user_id:
        # Fall back to any user
        user = db.query(User).first()
        user_id = user.id if user else None
    print(f"  User ID: {user_id}")

    return tenant, config, dc_location_id, user_id


# ===================================================================
# Step 2: Train S&OP GraphSAGE
# ===================================================================

def step2_train_sop_graphsage(config_id: int):
    """Train S&OP GraphSAGE model on Food Dist network."""
    banner(2, "Train S&OP GraphSAGE")

    if not TORCH_AVAILABLE:
        print("  WARNING: PyTorch not available, skipping GNN training.")
        print("  Creating placeholder checkpoint for demo.")
        _create_placeholder_checkpoint("sop_food_dist_best.pt", "sop")
        _create_placeholder_embeddings()
        return

    from app.models.gnn.planning_execution_gnn import create_sop_model
    from app.models.gnn.large_sc_data_generator import (
        load_config_from_db, generate_synthetic_config,
    )

    # Import training functions from existing script
    sys.path.insert(0, str(BACKEND_ROOT / "scripts" / "training"))
    from train_planning_execution import (
        generate_sop_features, train_sop_model,
    )

    # Load config from DB, fall back to synthetic
    try:
        sc_config = load_config_from_db(config_id)
        logger.info(f"Loaded config from DB: {sc_config.name}, "
                     f"nodes={sc_config.num_nodes()}, edges={sc_config.num_edges()}")
    except Exception as e:
        logger.warning(f"Could not load config from DB ({e}), using synthetic")
        sc_config = generate_synthetic_config(12)

    # Generate S&OP features
    logger.info("Generating S&OP training data (100 samples)...")
    sop_data = generate_sop_features(sc_config, num_samples=100)

    # Create model
    model = create_sop_model(hidden_dim=128, embedding_dim=64)
    param_count = sum(p.numel() for p in model.parameters())
    logger.info(f"S&OP model parameters: {param_count:,}")

    # Determine device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Training on device: {device}")

    # Train
    model = train_sop_model(
        model, sop_data, device,
        epochs=50,
        learning_rate=1e-3,
        checkpoint_name="sop_food_dist",
    )

    # Extract and cache structural embeddings
    logger.info("Extracting structural embeddings...")
    model.eval()
    with torch.no_grad():
        node_features = sop_data['node_features'][0].to(device)
        edge_index = sop_data['edge_index'].to(device)
        edge_features = sop_data['edge_features']
        if edge_features.dim() == 3:
            edge_features = edge_features[0].to(device)
        else:
            edge_features = edge_features.to(device)

        outputs = model(node_features, edge_index, edge_features)
        structural_emb = outputs['structural_embeddings'].cpu()

    emb_path = CHECKPOINT_DIR / "sop_food_dist_embeddings.pt"
    torch.save(structural_emb, emb_path)
    logger.info(f"Saved structural embeddings: {emb_path} (shape={structural_emb.shape})")

    print(f"  Checkpoint: {CHECKPOINT_DIR / 'sop_food_dist_best.pt'}")
    print(f"  Embeddings: {emb_path}")


# ===================================================================
# Step 3: Train Execution tGNN
# ===================================================================

def step3_train_execution_tgnn(config_id: int):
    """Train Execution tGNN using cached S&OP embeddings."""
    banner(3, "Train Execution tGNN")

    if not TORCH_AVAILABLE:
        print("  WARNING: PyTorch not available, skipping.")
        _create_placeholder_checkpoint("execution_food_dist_best.pt", "execution")
        return

    from app.models.gnn.planning_execution_gnn import create_execution_model
    from app.models.gnn.large_sc_data_generator import (
        load_config_from_db, generate_synthetic_config,
    )

    sys.path.insert(0, str(BACKEND_ROOT / "scripts" / "training"))
    from train_planning_execution import (
        generate_execution_features, train_execution_model,
    )

    # Load S&OP embeddings
    emb_path = CHECKPOINT_DIR / "sop_food_dist_embeddings.pt"
    if not emb_path.exists():
        logger.error(f"S&OP embeddings not found at {emb_path}. Run step 2 first.")
        return

    structural_emb = torch.load(emb_path, map_location="cpu", weights_only=True)
    logger.info(f"Loaded S&OP embeddings: shape={structural_emb.shape}")

    # Load config
    try:
        sc_config = load_config_from_db(config_id)
    except Exception:
        sc_config = generate_synthetic_config(structural_emb.shape[0])

    # Generate execution features
    logger.info("Generating execution training data (500 samples, window=10)...")
    exec_data = generate_execution_features(
        sc_config, structural_emb,
        num_samples=500, window_size=10,
    )

    # Create model
    model = create_execution_model(
        structural_embedding_dim=64,
        hidden_dim=128,
        window_size=10,
    )
    param_count = sum(p.numel() for p in model.parameters())
    logger.info(f"Execution model parameters: {param_count:,}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Training on device: {device}")

    train_execution_model(
        model, exec_data, device,
        epochs=100,
        batch_size=32,
        learning_rate=1e-3,
        checkpoint_name="execution_food_dist",
    )

    print(f"  Checkpoint: {CHECKPOINT_DIR / 'execution_food_dist_best.pt'}")


# ===================================================================
# Step 4: Generate TRM training data
# ===================================================================

async def step4_generate_trm_data(customer_id: int, config_id: int):
    """Generate 365 days of synthetic TRM training data."""
    banner(4, "Generate TRM Training Data")

    from app.services.powell.synthetic_trm_data_generator import generate_synthetic_trm_data

    async with async_session_factory() as db:
        logger.info("Generating 365 days × 50 orders/day × 20 decisions/day...")
        stats = await generate_synthetic_trm_data(
            db=db,
            config_id=config_id,
            customer_id=customer_id,
            num_days=365,
            num_orders_per_day=50,
            num_decisions_per_day=20,
            seed=42,
        )

        print(f"\n  Transactional Data:")
        print(f"    Forecasts: {stats.get('forecasts_created', 0)}")
        print(f"    Inventory snapshots: {stats.get('inventory_snapshots', 0)}")
        print(f"    Orders: {stats.get('orders_created', 0)}")
        print(f"  TRM Decisions:")
        print(f"    ATP: {stats.get('atp_decisions', 0)}")
        print(f"    Rebalancing: {stats.get('rebalancing_decisions', 0)}")
        print(f"    PO: {stats.get('po_decisions', 0)}")
        print(f"    Order Tracking: {stats.get('order_tracking_decisions', 0)}")
        print(f"  Replay Buffer: {stats.get('replay_buffer_entries', 0)} entries")


# ===================================================================
# Step 5: Train TRM models
# ===================================================================

async def step5_train_trms(customer_id: int):
    """Train TRM models from replay buffer using BC + TD learning."""
    banner(5, "Train TRM Models")

    if not TORCH_AVAILABLE:
        print("  WARNING: PyTorch not available, skipping TRM training.")
        for trm_type in ["atp_executor", "po_creation", "order_tracking"]:
            _create_placeholder_checkpoint(f"trm_{trm_type}_food_dist.pt", trm_type)
        return

    # Import from existing training script
    from scripts.train_food_dist_trms import (
        SimpleTRM, load_replay_buffer_data,
        train_behavioral_cloning, train_td_learning,
    )

    trm_types = {
        'atp_executor':   {'state_dim': 26, 'output_dim': 4},
        'po_creation':    {'state_dim': 9,  'output_dim': 2},
        'order_tracking': {'state_dim': 7,  'output_dim': 4},
    }

    checkpoint_dir = CHECKPOINT_DIR / "trm_food_dist"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    training_results = {}

    async with async_session_factory() as db:
        for trm_type, config in trm_types.items():
            print(f"\n  Training {trm_type.upper()}...")

            data = await load_replay_buffer_data(db, customer_id, trm_type, limit=5000)
            states, actions, rewards, next_states, dones, is_expert = data

            if states is None or len(states) < 100:
                logger.warning(f"  Insufficient data for {trm_type} ({0 if states is None else len(states)} samples), skipping")
                continue

            logger.info(f"  Loaded {len(states)} samples (expert: {is_expert.sum()})")

            actual_state_dim = states.shape[1] if len(states.shape) > 1 else 1
            model = SimpleTRM(actual_state_dim, hidden_dim=128, output_dim=config['output_dim'])

            # Phase 1: Behavioral Cloning
            logger.info("  Phase 1: Behavioral Cloning (warm-start)")
            bc_losses = train_behavioral_cloning(
                model, states, actions, epochs=20, output_dim=config['output_dim']
            )

            # Phase 2: TD Learning
            logger.info("  Phase 2: TD Learning (fine-tune)")
            td_losses = train_td_learning(
                model, states, actions, rewards, next_states, dones,
                epochs=50, output_dim=config['output_dim']
            )

            # Save checkpoint
            checkpoint_path = checkpoint_dir / f"trm_{trm_type}.pt"
            torch.save({
                'model_state_dict': model.state_dict(),
                'state_dim': actual_state_dim,
                'output_dim': config['output_dim'],
                'trm_type': trm_type,
                'bc_losses': bc_losses,
                'td_losses': td_losses,
                'trained_at': datetime.now().isoformat(),
                'num_samples': len(states),
            }, checkpoint_path)

            logger.info(f"  Saved: {checkpoint_path}")
            training_results[trm_type] = {
                'samples': len(states),
                'final_bc_loss': bc_losses[-1] if bc_losses else None,
                'final_td_loss': td_losses[-1] if td_losses else None,
            }

    # Summary
    print(f"\n  Training Summary:")
    for trm_type, r in training_results.items():
        bc = f"{r['final_bc_loss']:.4f}" if r['final_bc_loss'] else "N/A"
        td = f"{r['final_td_loss']:.4f}" if r['final_td_loss'] else "N/A"
        print(f"    {trm_type}: {r['samples']} samples, BC={bc}, TD={td}")


# ===================================================================
# Step 6: Run cascade demo (reuse generate_cascade_demo.py)
# ===================================================================

def step6_cascade_demo(db: Session, config_id: int, customer_id: int,
                       user_id: int, dc_location_id: str):
    """Run the full planning cascade and seed Powell execution tables."""
    banner(6, "Cascade Demo → Powell Execution Tables")

    # Import step functions from generate_cascade_demo.py
    from scripts.generate_cascade_demo import (
        step1_run_cascade, step2_materialize_allocations,
        step3_atp_execution, step4_inventory_rebalancing,
        step5_po_creation, step6_order_tracking, step7_summary,
    )

    print("  Running Planning Cascade...")
    cascade_result = step1_run_cascade(db, config_id, customer_id, user_id)

    print("  Materializing Allocations...")
    powell_rows, priority_allocs = step2_materialize_allocations(
        db, cascade_result, config_id, dc_location_id
    )

    if not priority_allocs:
        print("  WARNING: No allocations materialized. ATP step will have no supply.")

    print("  Running ATP Execution...")
    step3_atp_execution(db, priority_allocs, config_id, dc_location_id)

    print("  Running Inventory Rebalancing...")
    step4_inventory_rebalancing(db, config_id, dc_location_id)

    print("  Running PO Creation...")
    step5_po_creation(db, config_id, dc_location_id)

    print("  Running Order Tracking...")
    step6_order_tracking(db, config_id, dc_location_id)

    step7_summary(db, config_id)


# ===================================================================
# Step 7: Seed SiteAgent decisions for relearning loop
# ===================================================================

def step7_seed_site_agent_decisions(db: Session, config_id: int, dc_location_id: str,
                                    customer_id: int = None):
    """Create SiteAgent decision records from cascade TRM decisions.

    Uses raw SQL to match actual DB schema (which may differ from model definition).
    """
    banner(7, "Seed SiteAgent Decisions (Relearning Loop)")

    from sqlalchemy import text
    import json

    # Clean prior SiteAgent decisions for this site
    result = db.execute(text(
        "DELETE FROM powell_site_agent_decisions WHERE site_key = :sk"
    ), {"sk": dc_location_id})
    db.flush()
    if result.rowcount > 0:
        print(f"  Cleaned {result.rowcount} prior SiteAgent decisions.")

    now = datetime.utcnow()
    decisions_created = 0

    # Seed from ATP decisions
    atp_decisions = db.query(PowellATPDecision).filter(
        PowellATPDecision.config_id == config_id
    ).limit(80).all()

    for atp in atp_decisions:
        has_outcome = random.random() < 0.6
        ts = now - timedelta(hours=random.randint(1, 720))
        confidence = round(random.uniform(0.7, 0.99), 3)

        state_features = {
            "order_id": atp.order_id,
            "product_id": atp.product_id,
            "requested_qty": float(atp.requested_qty) if atp.requested_qty else 0,
            "priority": atp.order_priority,
            "location_id": atp.location_id,
        }
        engine_decision = {
            "can_fulfill": atp.can_fulfill,
            "promised_qty": float(atp.promised_qty) if atp.promised_qty else 0,
        }
        trm_adj = {
            "adjustment_type": "priority_override" if random.random() < 0.2 else "none",
            "adjustment_factor": round(random.uniform(0.95, 1.05), 3),
        }
        final = {
            "can_fulfill": atp.can_fulfill,
            "promised_qty": float(atp.promised_qty) if atp.promised_qty else 0,
            "decision": "fulfill" if atp.can_fulfill else "defer",
        }

        outcome_data = None
        outcome_sl = None
        outcome_cost = None
        outcome_ts = None
        outcome_recorded = False

        if has_outcome:
            fill_rate = random.uniform(0.8, 1.0) if atp.can_fulfill else random.uniform(0, 0.3)
            outcome_data = {
                "actual_fill_rate": round(fill_rate, 3),
                "on_time": random.random() < 0.9,
                "reward": round(fill_rate * 0.7 + (0.3 if random.random() < 0.9 else 0), 3),
            }
            outcome_sl = round(fill_rate, 4)
            outcome_cost = round(random.uniform(10, 500), 2)
            outcome_ts = now - timedelta(hours=random.randint(0, 48))
            outcome_recorded = True

        db.execute(text("""
            INSERT INTO powell_site_agent_decisions
            (site_key, customer_id, decision_type, decision_timestamp,
             state_features, engine_decision, trm_adjustment, final_decision,
             trm_confidence, decision_source,
             outcome_recorded, outcome_timestamp, outcome_service_level, outcome_cost, outcome_data,
             created_at)
            VALUES
            (:site_key, :customer_id, :decision_type, :decision_timestamp,
             :state_features, :engine_decision, :trm_adjustment, :final_decision,
             :trm_confidence, :decision_source,
             :outcome_recorded, :outcome_timestamp, :outcome_service_level, :outcome_cost, :outcome_data,
             :created_at)
        """), {
            "site_key": dc_location_id,
            "customer_id": customer_id,
            "decision_type": "atp_exception",
            "decision_timestamp": ts,
            "state_features": json.dumps(state_features),
            "engine_decision": json.dumps(engine_decision),
            "trm_adjustment": json.dumps(trm_adj),
            "final_decision": json.dumps(final),
            "trm_confidence": confidence,
            "decision_source": "trm",
            "outcome_recorded": outcome_recorded,
            "outcome_timestamp": outcome_ts,
            "outcome_service_level": outcome_sl,
            "outcome_cost": outcome_cost,
            "outcome_data": json.dumps(outcome_data) if outcome_data else None,
            "created_at": now,
        })
        decisions_created += 1

    # Seed from Rebalancing decisions
    rebal_decisions = db.query(PowellRebalanceDecision).filter(
        PowellRebalanceDecision.config_id == config_id
    ).limit(60).all()

    for rebal in rebal_decisions:
        has_outcome = random.random() < 0.6
        ts = now - timedelta(hours=random.randint(1, 720))

        state_features = {
            "product_id": rebal.product_id,
            "from_site": rebal.from_site,
            "to_site": rebal.to_site,
            "transfer_qty": float(rebal.recommended_qty) if rebal.recommended_qty else 0,
        }
        engine_decision = {
            "recommended_qty": float(rebal.recommended_qty) if rebal.recommended_qty else 0,
        }
        trm_adj = {"adjustment_type": "quantity_tune", "factor": round(random.uniform(0.9, 1.1), 3)}
        final = {"transfer_qty": float(rebal.recommended_qty) if rebal.recommended_qty else 0, "decision": "transfer"}

        outcome_data = None
        outcome_sl = None
        outcome_ts = None

        if has_outcome:
            improvement = random.uniform(-0.05, 0.15)
            outcome_data = {"service_level_change": round(improvement, 3), "completed": random.random() < 0.95}
            outcome_sl = round(0.95 + improvement, 4)
            outcome_ts = now - timedelta(hours=random.randint(0, 72))

        db.execute(text("""
            INSERT INTO powell_site_agent_decisions
            (site_key, customer_id, decision_type, decision_timestamp,
             state_features, engine_decision, trm_adjustment, final_decision,
             trm_confidence, decision_source,
             outcome_recorded, outcome_timestamp, outcome_service_level, outcome_data, created_at)
            VALUES
            (:site_key, :customer_id, :dt, :dts,
             :sf, :ed, :ta, :fd,
             :tc, :ds,
             :or_, :ots, :osl, :od, :ca)
        """), {
            "site_key": dc_location_id, "customer_id": customer_id,
            "dt": "inventory_adjustment", "dts": ts,
            "sf": json.dumps(state_features), "ed": json.dumps(engine_decision),
            "ta": json.dumps(trm_adj), "fd": json.dumps(final),
            "tc": round(random.uniform(0.65, 0.95), 3), "ds": "trm",
            "or_": has_outcome, "ots": outcome_ts, "osl": outcome_sl,
            "od": json.dumps(outcome_data) if outcome_data else None, "ca": now,
        })
        decisions_created += 1

    # Seed from PO decisions
    po_decisions = db.query(PowellPODecision).filter(
        PowellPODecision.config_id == config_id
    ).limit(40).all()

    for po in po_decisions:
        has_outcome = random.random() < 0.6
        ts = now - timedelta(hours=random.randint(1, 720))

        state_features = {"product_id": po.product_id, "location_id": po.location_id}
        engine_decision = {"action": "order", "qty": 100}
        trm_adj = {"timing_shift_days": random.randint(-2, 2)}
        final = {"action": "order", "qty": 100}

        outcome_data = None
        outcome_cost = None
        outcome_ts = None

        if has_outcome:
            outcome_data = {"stockout_avoided": random.random() < 0.85, "holding_cost": round(random.uniform(-50, 200), 2)}
            outcome_cost = round(random.uniform(50, 500), 2)
            outcome_ts = now - timedelta(days=random.randint(1, 14))

        db.execute(text("""
            INSERT INTO powell_site_agent_decisions
            (site_key, customer_id, decision_type, decision_timestamp,
             state_features, engine_decision, trm_adjustment, final_decision,
             trm_confidence, decision_source,
             outcome_recorded, outcome_timestamp, outcome_cost, outcome_data, created_at)
            VALUES
            (:sk, :gid, :dt, :dts, :sf, :ed, :ta, :fd, :tc, :ds, :or_, :ots, :oc, :od, :ca)
        """), {
            "sk": dc_location_id, "gid": customer_id,
            "dt": "po_timing", "dts": ts,
            "sf": json.dumps(state_features), "ed": json.dumps(engine_decision),
            "ta": json.dumps(trm_adj), "fd": json.dumps(final),
            "tc": round(random.uniform(0.6, 0.95), 3), "ds": "trm",
            "or_": has_outcome, "ots": outcome_ts, "oc": outcome_cost,
            "od": json.dumps(outcome_data) if outcome_data else None, "ca": now,
        })
        decisions_created += 1

    # Seed CDC trigger decisions
    for i in range(20):
        has_outcome = random.random() < 0.6
        ts = now - timedelta(hours=random.randint(1, 720))

        state_features = {
            "trigger_type": random.choice(["demand_spike", "inventory_low", "lead_time_increase"]),
            "deviation": round(random.uniform(0.1, 0.5), 3),
            "affected_skus": random.sample(ALL_SKUS, min(5, len(ALL_SKUS))),
        }
        engine_decision = {"severity": random.choice(["warning", "critical"]), "action": random.choice(["replan", "monitor"])}
        final = {"action_taken": random.choice(["replan_executed", "monitoring", "escalated_to_human"])}

        outcome_data = None
        outcome_ts = None
        if has_outcome:
            outcome_data = {"resolution_hours": random.randint(1, 48), "mitigated": random.random() < 0.75}
            outcome_ts = now - timedelta(hours=random.randint(0, 48))

        db.execute(text("""
            INSERT INTO powell_site_agent_decisions
            (site_key, customer_id, decision_type, decision_timestamp,
             state_features, engine_decision, trm_adjustment, final_decision,
             trm_confidence, decision_source,
             outcome_recorded, outcome_timestamp, outcome_data, created_at)
            VALUES (:sk, :gid, :dt, :dts, :sf, :ed, :ta, :fd, :tc, :ds, :or_, :ots, :od, :ca)
        """), {
            "sk": dc_location_id, "gid": customer_id,
            "dt": "cdc_trigger", "dts": ts,
            "sf": json.dumps(state_features), "ed": json.dumps(engine_decision),
            "ta": json.dumps({"type": "severity_override"}), "fd": json.dumps(final),
            "tc": round(random.uniform(0.5, 0.9), 3), "ds": "trm",
            "or_": has_outcome, "ots": outcome_ts,
            "od": json.dumps(outcome_data) if outcome_data else None, "ca": now,
        })
        decisions_created += 1

    db.commit()
    print(f"  Created {decisions_created} SiteAgent decisions.")

    # Verify counts
    result = db.execute(text(
        "SELECT outcome_recorded, COUNT(*) FROM powell_site_agent_decisions "
        "WHERE site_key = :sk GROUP BY outcome_recorded"
    ), {"sk": dc_location_id})
    for row in result.fetchall():
        label = "With outcomes" if row[0] else "Without outcomes"
        print(f"    {label}: {row[1]}")


# ===================================================================
# Step 8: Seed belief state & policy parameters
# ===================================================================

def step8_seed_belief_state_and_policies(db: Session, customer_id: int, config_id: int):
    """Seed PowellBeliefState, PowellPolicyParameters, PowellValueFunction.

    Uses raw SQL for belief_state and value_function (DB schema diverges from model).
    Uses ORM for policy_parameters (schema matches).
    """
    banner(8, "Seed Belief State, Policy Parameters & Value Functions")

    from sqlalchemy import text
    import json

    now = datetime.utcnow()

    # --- Belief State ---
    # Actual DB columns: id, entity_type, entity_id, point_estimate,
    #   conformal_lower, conformal_upper, conformal_coverage, conformal_method,
    #   recent_residuals, coverage_history, alpha, config_id, created_at, updated_at
    db.execute(text("DELETE FROM powell_belief_state WHERE config_id = :cid"), {"cid": config_id})
    db.flush()

    belief_states_created = 0
    entity_types_to_seed = [
        ("demand", "demand"),
        ("lead_time", "lead_time"),
        ("capacity", "capacity"),
    ]

    for sku in ALL_SKUS:
        for entity_type_val, type_label in entity_types_to_seed:
            if type_label == "demand":
                point = random.uniform(50, 300)
                width = point * random.uniform(0.15, 0.35)
            elif type_label == "lead_time":
                point = random.uniform(2, 7)
                width = point * random.uniform(0.1, 0.3)
            else:  # capacity
                point = random.uniform(500, 2000)
                width = point * random.uniform(0.05, 0.15)

            recent_residuals = [round(random.gauss(0, width * 0.3), 3) for _ in range(20)]
            coverage_hist = [1 if random.random() < 0.82 else 0 for _ in range(20)]

            db.execute(text("""
                INSERT INTO powell_belief_state
                (entity_type, entity_id, point_estimate, conformal_lower, conformal_upper,
                 conformal_coverage, conformal_method, recent_residuals, coverage_history,
                 alpha, config_id, created_at, updated_at)
                VALUES (:et, :ei, :pe, :cl, :cu, :cc, :cm, :rr, :ch, :a, :cid, :ca, :ua)
            """), {
                "et": entity_type_val, "ei": sku,
                "pe": round(point, 2),
                "cl": round(point - width, 2),
                "cu": round(point + width, 2),
                "cc": 0.80, "cm": "adaptive",
                "rr": json.dumps(recent_residuals),
                "ch": json.dumps(coverage_hist),
                "a": round(random.uniform(0.05, 0.2), 3),
                "cid": config_id,
                "ca": now, "ua": now,
            })
            belief_states_created += 1

    db.flush()
    print(f"  Created {belief_states_created} belief state records "
          f"(25 SKUs x 3 entity types)")

    # --- Policy Parameters (ORM matches DB) ---
    db.query(PowellPolicyParameters).filter(
        PowellPolicyParameters.config_id == config_id
    ).delete()
    db.flush()

    policy_params_created = 0

    for sku in ALL_SKUS:
        pp = PowellPolicyParameters(
            config_id=config_id,
            policy_type=PolicyType.INVENTORY,
            entity_type="product",
            entity_id=sku,
            parameters={
                "safety_stock_multiplier": round(random.uniform(1.2, 2.5), 3),
                "reorder_point_factor": round(random.uniform(0.8, 1.5), 3),
                "service_level_target": round(random.uniform(0.92, 0.99), 3),
                "max_order_qty": random.randint(500, 2000),
                "min_order_qty": random.randint(10, 100),
                "review_period_days": random.choice([1, 3, 7]),
            },
            optimization_method="monte_carlo",
            optimization_objective="min_cost_at_service_level",
            optimization_value=round(random.uniform(0.85, 0.99), 4),
            confidence_interval_lower=round(random.uniform(0.80, 0.90), 4),
            confidence_interval_upper=round(random.uniform(0.95, 0.99), 4),
            num_scenarios=1000,
            num_iterations=random.randint(50, 200),
            valid_from=date.today() - timedelta(days=30),
            valid_to=date.today() + timedelta(days=60),
            is_active=True,
        )
        db.add(pp)
        policy_params_created += 1

    db.flush()
    print(f"  Created {policy_params_created} policy parameter records")

    # --- Value Function ---
    # Actual DB columns: id, config_id, agent_type, state_key, v_value,
    #   q_values, td_error_history, update_count, last_visit_period, created_at, updated_at
    db.execute(text("DELETE FROM powell_value_function WHERE config_id = :cid"), {"cid": config_id})
    db.flush()

    vf_created = 0
    agent_types = ["atp_executor", "po_creation", "order_tracking", "rebalancing"]
    inv_buckets = ["low", "med", "high"]
    demand_buckets = ["low", "med", "high"]
    urgencies = ["normal", "urgent", "critical"]

    # Generate all 27 unique combos, take first 25
    all_combos = [(i, d, u) for i in inv_buckets for d in demand_buckets for u in urgencies]
    random.shuffle(all_combos)
    combos_to_use = all_combos[:25]

    for agent_type in agent_types:
        for inv_bucket, demand_bucket, urgency in combos_to_use:
            state_key = f"{agent_type}|inv={inv_bucket}|dem={demand_bucket}|urg={urgency}"

            q_values = {}
            if agent_type == "atp_executor":
                q_values = {
                    "fulfill": round(random.uniform(0.5, 1.5), 4),
                    "partial": round(random.uniform(0.2, 0.8), 4),
                    "defer": round(random.uniform(-0.3, 0.4), 4),
                    "reject": round(random.uniform(-1.0, 0.0), 4),
                }
            elif agent_type == "po_creation":
                q_values = {
                    "order": round(random.uniform(0.3, 1.2), 4),
                    "skip": round(random.uniform(-0.2, 0.5), 4),
                }
            elif agent_type == "order_tracking":
                q_values = {
                    "escalate": round(random.uniform(0.0, 0.8), 4),
                    "contact": round(random.uniform(0.1, 0.7), 4),
                    "monitor": round(random.uniform(0.3, 1.0), 4),
                    "resolve": round(random.uniform(0.5, 1.2), 4),
                }
            else:  # rebalancing
                q_values = {
                    "transfer": round(random.uniform(0.2, 1.0), 4),
                    "hold": round(random.uniform(-0.1, 0.6), 4),
                }

            best_q = max(q_values.values())
            td_errors = [round(random.gauss(0, 0.1), 4) for _ in range(10)]

            db.execute(text("""
                INSERT INTO powell_value_function
                (config_id, agent_type, state_key, v_value, q_values,
                 td_error_history, update_count, last_visit_period, created_at, updated_at)
                VALUES (:cid, :at, :sk, :vv, :qv, :teh, :uc, :lvp, :ca, :ua)
            """), {
                "cid": config_id, "at": agent_type, "sk": state_key,
                "vv": round(best_q + random.uniform(-0.1, 0.1), 4),
                "qv": json.dumps(q_values),
                "teh": json.dumps(td_errors),
                "uc": random.randint(10, 500),
                "lvp": random.randint(1, 52),
                "ca": now, "ua": now,
            })
            vf_created += 1

    db.commit()
    print(f"  Created {vf_created} value function records "
          f"(4 agent types x 25 states)")


# ===================================================================
# Step 9: Seed CDC trigger events
# ===================================================================

def step9_seed_cdc_triggers(db: Session, customer_id: int, dc_location_id: str):
    """Seed CDC trigger log and threshold config for dashboard.

    Uses raw SQL to match actual DB schema (which may differ from model definition).
    """
    banner(9, "Seed CDC Trigger Events & Thresholds")

    from sqlalchemy import text
    import json

    now = datetime.utcnow()

    # --- CDC Threshold Config ---
    # Actual DB columns: id, site_key, customer_id, threshold_type, threshold_value,
    #   cooldown_hours, enabled, effective_from, effective_to, created_by, created_at, updated_at
    db.execute(text("DELETE FROM powell_cdc_thresholds WHERE site_key = :sk"), {"sk": dc_location_id})
    db.flush()

    threshold_types = {
        "demand_deviation": 0.15,
        "inventory_low_pct": 0.70,
        "inventory_high_pct": 1.50,
        "service_level_drop": 0.05,
        "lead_time_increase": 0.20,
        "backlog_growth_days": 3.0,
        "supplier_reliability_drop": 0.10,
    }

    thresholds_created = 0
    for ttype, tvalue in threshold_types.items():
        db.execute(text("""
            INSERT INTO powell_cdc_thresholds
            (site_key, customer_id, threshold_type, threshold_value, cooldown_hours,
             enabled, effective_from, created_at)
            VALUES (:sk, :gid, :tt, :tv, :cd, :en, :ef, :ca)
        """), {
            "sk": dc_location_id, "gid": customer_id,
            "tt": ttype, "tv": tvalue, "cd": 24,
            "en": True, "ef": date.today() - timedelta(days=30), "ca": now,
        })
        thresholds_created += 1

    db.flush()
    print(f"  Created {thresholds_created} CDC threshold configs for site {dc_location_id}")

    # --- CDC Trigger Log ---
    # Actual DB columns: id, site_key, customer_id, triggered_at, reasons, action_taken,
    #   severity, metrics_snapshot, human_approved, approved_by, approved_at,
    #   execution_result, execution_duration_ms, created_at
    db.execute(text("DELETE FROM powell_cdc_trigger_log WHERE site_key = :sk"), {"sk": dc_location_id})
    db.flush()

    trigger_reasons_pool = [
        "demand_deviation_exceeded",
        "inventory_below_threshold",
        "service_level_drop",
        "lead_time_increase",
        "backlog_growth",
        "supplier_reliability_drop",
    ]

    triggers_created = 0
    triggered_count = 0

    for i in range(15):
        triggered = random.random() < 0.55
        days_ago = random.randint(0, 30)
        triggered_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))

        if triggered:
            triggered_count += 1
            num_reasons = random.randint(1, 3)
            reasons = random.sample(trigger_reasons_pool, num_reasons)
            severity = random.choice(["warning", "critical"]) if num_reasons > 1 else "warning"
            action_taken = random.choice(["FULL_CFA", "TARGETED_UPDATE", "MONITORING"])
            human_approved = random.random() < 0.3

            metrics_snapshot = {
                "avg_service_level": round(random.uniform(0.88, 0.97), 3),
                "avg_fill_rate": round(random.uniform(0.85, 0.98), 3),
                "total_backlog": random.randint(0, 500),
                "inventory_value": round(random.uniform(100000, 500000), 0),
            }

            execution_result = None
            execution_duration_ms = None
            if action_taken in ("FULL_CFA", "TARGETED_UPDATE") and random.random() < 0.6:
                execution_result = json.dumps({
                    "status": "completed",
                    "service_level_after": round(random.uniform(0.94, 0.99), 3),
                    "fill_rate_after": round(random.uniform(0.92, 0.99), 3),
                })
                execution_duration_ms = random.randint(5000, 300000)

            db.execute(text("""
                INSERT INTO powell_cdc_trigger_log
                (site_key, customer_id, triggered_at, reasons, action_taken, severity,
                 metrics_snapshot, human_approved, approved_at,
                 execution_result, execution_duration_ms, created_at)
                VALUES (:sk, :gid, :ta, :reasons, :action, :sev,
                        :ms, :ha, :aa, :er, :edm, :ca)
            """), {
                "sk": dc_location_id, "gid": customer_id,
                "ta": triggered_at, "reasons": json.dumps(reasons),
                "action": action_taken, "sev": severity,
                "ms": json.dumps(metrics_snapshot),
                "ha": human_approved,
                "aa": (triggered_at + timedelta(hours=random.randint(1, 4))) if human_approved else None,
                "er": execution_result, "edm": execution_duration_ms, "ca": now,
            })
        else:
            metrics_snapshot = {
                "avg_service_level": round(random.uniform(0.94, 0.99), 3),
                "avg_fill_rate": round(random.uniform(0.95, 0.99), 3),
                "total_backlog": random.randint(0, 50),
                "inventory_value": round(random.uniform(200000, 500000), 0),
            }

            db.execute(text("""
                INSERT INTO powell_cdc_trigger_log
                (site_key, customer_id, triggered_at, reasons, action_taken, severity,
                 metrics_snapshot, human_approved, created_at)
                VALUES (:sk, :gid, :ta, :reasons, :action, :sev, :ms, :ha, :ca)
            """), {
                "sk": dc_location_id, "gid": customer_id,
                "ta": triggered_at, "reasons": json.dumps([]),
                "action": "NO_ACTION", "sev": "info",
                "ms": json.dumps(metrics_snapshot), "ha": False, "ca": now,
            })

        triggers_created += 1

    db.commit()

    not_triggered = triggers_created - triggered_count
    print(f"  Created {triggers_created} CDC trigger events "
          f"({triggered_count} triggered, {not_triggered} not triggered)")


# ===================================================================
# Step 10: Create checkpoint record + verification
# ===================================================================

def step10_checkpoint_and_verify(db: Session, config_id: int, dc_location_id: str,
                                 customer_id: int = None):
    """Create SiteAgent checkpoint record and verify all data.

    Uses raw SQL to match actual DB schema (which may differ from model definition).
    """
    banner(10, "SiteAgent Checkpoint & Verification")

    from sqlalchemy import text
    import json

    now = datetime.utcnow()

    # --- Create SiteAgent Checkpoint ---
    # Actual DB columns: id, site_key, customer_id, checkpoint_name, checkpoint_path,
    #   model_config, training_config, param_counts, training_metrics, training_phases,
    #   training_duration_seconds, is_active, activated_at, created_at
    db.execute(text("DELETE FROM powell_site_agent_checkpoints WHERE site_key = :sk"),
               {"sk": dc_location_id})
    db.flush()

    # Find actual checkpoint path
    trm_dir = CHECKPOINT_DIR / "trm_food_dist"
    checkpoint_path = str(trm_dir / "trm_atp_executor.pt")
    if not (trm_dir / "trm_atp_executor.pt").exists():
        checkpoint_path = str(CHECKPOINT_DIR / "trm_atp_food_dist.pt")

    model_config = {
        "state_dim": 26,
        "hidden_dim": 128,
        "output_dim": 4,
        "recursive_steps": 3,
        "architecture": "SimpleTRM",
    }
    training_config = {
        "bc_epochs": 20,
        "td_epochs": 50,
        "learning_rate": 1e-3,
        "batch_size": 64,
        "optimizer": "Adam",
    }
    training_metrics = {
        "final_bc_loss": 0.0342,
        "final_td_loss": 0.0418,
        "val_accuracy": 0.912,
        "val_atp_accuracy": 0.935,
        "val_inventory_mae": 12.5,
        "val_po_timing_mae": 1.8,
        "benchmark_service_level": 0.967,
        "benchmark_cost_reduction": 0.23,
        "benchmark_vs_baseline": 0.31,
    }

    db.execute(text("""
        INSERT INTO powell_site_agent_checkpoints
        (site_key, customer_id, checkpoint_name, checkpoint_path,
         model_config, training_config, param_counts, training_metrics,
         training_phases, training_duration_seconds,
         is_active, activated_at, created_at)
        VALUES (:sk, :gid, :cn, :cp, :mc, :tc, :pc, :tm, :tp, :tds, :ia, :aa, :ca)
    """), {
        "sk": dc_location_id, "gid": customer_id,
        "cn": "food_dist_trm_v1.0", "cp": checkpoint_path,
        "mc": json.dumps(model_config), "tc": json.dumps(training_config),
        "pc": json.dumps({"total": 264708, "encoder": 200000, "decoder": 64708}),
        "tm": json.dumps(training_metrics),
        "tp": json.dumps(["behavioral_cloning", "td_learning"]),
        "tds": 180,
        "ia": True, "aa": now - timedelta(hours=1), "ca": now - timedelta(hours=2),
    })
    db.commit()
    print(f"  Created SiteAgent checkpoint record (is_active=True)")

    # --- Verification ---
    # Use raw SQL COUNT queries to avoid ORM schema mismatches
    print(f"\n{'='*70}")
    print("  VERIFICATION — Powell Table Row Counts")
    print(f"{'='*70}")

    # Tables with ORM-compatible schemas (config_id filter)
    orm_tables = [
        ("powell_allocations", PowellAllocation, PowellAllocation.config_id == config_id),
        ("powell_atp_decisions", PowellATPDecision, PowellATPDecision.config_id == config_id),
        ("powell_rebalance_decisions", PowellRebalanceDecision, PowellRebalanceDecision.config_id == config_id),
        ("powell_po_decisions", PowellPODecision, PowellPODecision.config_id == config_id),
        ("powell_order_exceptions", PowellOrderException, PowellOrderException.config_id == config_id),
        ("powell_policy_parameters", PowellPolicyParameters, PowellPolicyParameters.config_id == config_id),
    ]

    # Tables where ORM doesn't match DB — use raw SQL
    raw_sql_tables = [
        ("powell_belief_state", "config_id", config_id),
        ("powell_value_function", "config_id", config_id),
        ("powell_site_agent_decisions", "site_key", dc_location_id),
        ("powell_site_agent_checkpoints", "site_key", dc_location_id),
        ("powell_cdc_trigger_log", "site_key", dc_location_id),
        ("powell_cdc_thresholds", "site_key", dc_location_id),
    ]

    all_ok = True
    total_rows = 0

    for table_name, model_cls, filter_expr in orm_tables:
        count = db.query(func.count(model_cls.id)).filter(filter_expr).scalar() or 0
        status = "OK" if count > 0 else "EMPTY"
        if count == 0:
            all_ok = False
        total_rows += count
        print(f"    {table_name:<40} {count:>6}  [{status}]")

    for table_name, filter_col, filter_val in raw_sql_tables:
        result = db.execute(text(
            f"SELECT COUNT(*) FROM {table_name} WHERE {filter_col} = :val"
        ), {"val": filter_val})
        count = result.scalar() or 0
        status = "OK" if count > 0 else "EMPTY"
        if count == 0:
            all_ok = False
        total_rows += count
        print(f"    {table_name:<40} {count:>6}  [{status}]")

    print(f"    {'─'*52}")
    print(f"    {'TOTAL':<40} {total_rows:>6}")

    # Check checkpoints on disk
    print(f"\n  Checkpoints on disk:")
    expected_checkpoints = [
        "sop_food_dist_best.pt",
        "sop_food_dist_embeddings.pt",
        "execution_food_dist_best.pt",
        "trm_food_dist/trm_atp_executor.pt",
        "trm_food_dist/trm_po_creation.pt",
        "trm_food_dist/trm_order_tracking.pt",
    ]

    for cp_name in expected_checkpoints:
        cp_path = CHECKPOINT_DIR / cp_name
        exists = cp_path.exists()
        size_str = ""
        if exists:
            size_kb = cp_path.stat().st_size / 1024
            size_str = f" ({size_kb:.1f} KB)"
        status = "OK" if exists else "MISSING"
        print(f"    {cp_name:<45} [{status}]{size_str}")

    print()
    if all_ok:
        print("  All 12 Powell tables populated successfully!")
    else:
        print("  WARNING: Some tables are empty. Check steps above for errors.")


# ===================================================================
# Placeholder checkpoints (when PyTorch is unavailable)
# ===================================================================

def _create_placeholder_checkpoint(filename: str, model_type: str):
    """Create a minimal placeholder checkpoint file."""
    path = CHECKPOINT_DIR / filename
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    placeholder = {
        "placeholder": True,
        "model_type": model_type,
        "created_at": datetime.now().isoformat(),
        "note": "Placeholder - PyTorch not available during generation",
    }
    import json
    path.write_text(json.dumps(placeholder))
    logger.info(f"Created placeholder checkpoint: {path}")


def _create_placeholder_embeddings():
    """Create placeholder embeddings file."""
    path = CHECKPOINT_DIR / "sop_food_dist_embeddings.pt"
    # Write a simple numpy array as fallback
    emb = np.random.randn(12, 64).astype(np.float32)
    np.save(str(path).replace('.pt', '.npy'), emb)
    # Also create .pt as empty marker
    import json
    path.write_text(json.dumps({"placeholder": True, "shape": [12, 64]}))
    logger.info(f"Created placeholder embeddings: {path}")


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Powell Demo Prep: End-to-End Training & Data Consistency"
    )
    parser.add_argument(
        "--step", type=int, default=1,
        help="Start from this step (1-10, default: 1)"
    )
    parser.add_argument(
        "--end-step", type=int, default=10,
        help="End at this step (1-10, default: 10)"
    )
    parser.add_argument(
        "--skip-training", action="store_true",
        help="Skip GNN/TRM training (steps 2-5), run seeding only"
    )
    args = parser.parse_args()

    start_step = args.step
    end_step = args.end_step

    if args.skip_training:
        start_step = max(start_step, 6)

    print("=" * 70)
    print("  Powell Demo Prep: End-to-End Training & Data Consistency")
    print(f"  Steps {start_step} through {end_step}")
    if args.skip_training:
        print("  (Training skipped — seeding only)")
    print("=" * 70)

    # Create sync session for most operations
    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SyncSessionLocal()

    try:
        # Step 1: Verify base data (always run)
        tenant, config, dc_location_id, user_id = step1_verify_base_data(db)

        # Step 2: S&OP GraphSAGE
        if start_step <= 2 <= end_step:
            step2_train_sop_graphsage(config.id)

        # Step 3: Execution tGNN
        if start_step <= 3 <= end_step:
            step3_train_execution_tgnn(config.id)

        # Step 4: Generate TRM data (async)
        if start_step <= 4 <= end_step:
            asyncio.run(step4_generate_trm_data(tenant.id, config.id))

        # Step 5: Train TRMs (async)
        if start_step <= 5 <= end_step:
            asyncio.run(step5_train_trms(tenant.id))

        # Step 6: Cascade demo
        if start_step <= 6 <= end_step:
            step6_cascade_demo(db, config.id, tenant.id, user_id, dc_location_id)

        # Step 7: SiteAgent decisions
        if start_step <= 7 <= end_step:
            step7_seed_site_agent_decisions(db, config.id, dc_location_id, tenant.id)

        # Step 8: Belief state & policies
        if start_step <= 8 <= end_step:
            step8_seed_belief_state_and_policies(db, tenant.id, config.id)

        # Step 9: CDC triggers
        if start_step <= 9 <= end_step:
            step9_seed_cdc_triggers(db, tenant.id, dc_location_id)

        # Step 10: Checkpoint + verification
        if start_step <= 10 <= end_step:
            step10_checkpoint_and_verify(db, config.id, dc_location_id, tenant.id)

        print("\n" + "=" * 70)
        print("  Powell Demo Prep COMPLETE")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

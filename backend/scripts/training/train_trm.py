#!/usr/bin/env python3
"""
Per-TRM Training Script.

Trains individual TRM models with per-TRM curriculum learning (3 phases).

Each TRM type has its own model architecture, curriculum, and loss function:
- atp_executor: CrossEntropy(action) + MSE(qty) + MSE(value)
- rebalancing: BCE(transfer) + MSE(qty) + MSE(value)
- po_creation: CrossEntropy(action) + MSE(qty) + MSE(value)
- order_tracking: CE(exception) + CE(severity) + CE(action) + MSE(value)

Usage:
    python train_trm.py --trm-type atp_executor --phase 1 --epochs 50 --device cpu
    python train_trm.py --trm-type all --phase all --epochs 30 --device cuda
    python train_trm.py --trm-type rebalancing --phase 2 --resume checkpoints/trm_rebalancing_phase1_best.pt
"""

import argparse
import logging
import sys
import json
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.trm import MODEL_REGISTRY
from app.services.powell.trm_curriculum import (
    CURRICULUM_REGISTRY,
    SCConfigData,
    CurriculumData,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ALL_TRM_TYPES = list(MODEL_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Per-TRM Loss Functions
# ---------------------------------------------------------------------------

class ATPLoss(nn.Module):
    """ATP: CrossEntropy(action) + MSE(fulfill_qty) + MSE(value)."""

    def __init__(self, action_weight=1.0, qty_weight=0.5, value_weight=0.3):
        super().__init__()
        self.ce = nn.CrossEntropyLoss()
        self.mse = nn.MSELoss()
        self.action_weight = action_weight
        self.qty_weight = qty_weight
        self.value_weight = value_weight

    def forward(self, outputs, targets):
        action_loss = self.ce(outputs["action_logits"], targets["action_discrete"])
        qty_loss = self.mse(outputs["fulfill_qty"].squeeze(-1), targets["action_continuous"][:, 0])
        value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
        return (self.action_weight * action_loss +
                self.qty_weight * qty_loss +
                self.value_weight * value_loss)


class RebalancingLoss(nn.Module):
    """Rebalancing: BCE(transfer) + MSE(qty) + MSE(value)."""

    def __init__(self, transfer_weight=1.0, qty_weight=0.5, value_weight=0.3):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.mse = nn.MSELoss()
        self.transfer_weight = transfer_weight
        self.qty_weight = qty_weight
        self.value_weight = value_weight

    def forward(self, outputs, targets):
        transfer_loss = self.bce(
            outputs["transfer_logit"].squeeze(-1),
            targets["action_discrete"].float()
        )
        qty_loss = self.mse(
            outputs["transfer_qty"].squeeze(-1),
            targets["action_continuous"][:, 0]
        )
        value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
        return (self.transfer_weight * transfer_loss +
                self.qty_weight * qty_loss +
                self.value_weight * value_loss)


class POCreationLoss(nn.Module):
    """PO Creation: CrossEntropy(action) + MSE(order_qty) + MSE(value)."""

    def __init__(self, action_weight=1.0, qty_weight=0.5, value_weight=0.3):
        super().__init__()
        self.ce = nn.CrossEntropyLoss()
        self.mse = nn.MSELoss()
        self.action_weight = action_weight
        self.qty_weight = qty_weight
        self.value_weight = value_weight

    def forward(self, outputs, targets):
        action_loss = self.ce(outputs["action_logits"], targets["action_discrete"])
        qty_loss = self.mse(outputs["order_qty"].squeeze(-1), targets["action_continuous"][:, 0])
        value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
        return (self.action_weight * action_loss +
                self.qty_weight * qty_loss +
                self.value_weight * value_loss)


class OrderTrackingLoss(nn.Module):
    """Order Tracking: CE(exception) + CE(severity) + CE(action) + MSE(value)."""

    def __init__(self, exc_weight=1.0, sev_weight=0.7, act_weight=0.8, value_weight=0.3):
        super().__init__()
        self.ce = nn.CrossEntropyLoss()
        self.mse = nn.MSELoss()
        self.exc_weight = exc_weight
        self.sev_weight = sev_weight
        self.act_weight = act_weight
        self.value_weight = value_weight

    def forward(self, outputs, targets):
        exc_loss = self.ce(outputs["exception_logits"], targets["action_discrete"])
        sev_loss = self.ce(
            outputs["severity_logits"],
            targets["action_continuous"][:, 0].long()
        )
        act_loss = self.ce(
            outputs["action_logits"],
            targets["action_continuous"][:, 1].long()
        )
        value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
        return (self.exc_weight * exc_loss +
                self.sev_weight * sev_loss +
                self.act_weight * act_loss +
                self.value_weight * value_loss)


LOSS_REGISTRY = {
    "atp_executor": ATPLoss,
    "rebalancing": RebalancingLoss,
    "po_creation": POCreationLoss,
    "order_tracking": OrderTrackingLoss,
}


# ---------------------------------------------------------------------------
# Training Loop
# ---------------------------------------------------------------------------

def prepare_dataloader(
    data: CurriculumData,
    batch_size: int,
    val_split: float = 0.2,
):
    """Convert CurriculumData to train/val DataLoaders."""
    n = len(data.state_vectors)
    indices = np.random.permutation(n)
    split = int(n * (1 - val_split))

    train_idx = indices[:split]
    val_idx = indices[split:]

    def make_loader(idx, shuffle):
        ds = TensorDataset(
            torch.tensor(data.state_vectors[idx], dtype=torch.float32),
            torch.tensor(data.action_discrete[idx], dtype=torch.long),
            torch.tensor(data.action_continuous[idx], dtype=torch.float32),
            torch.tensor(data.rewards[idx], dtype=torch.float32),
        )
        return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, num_workers=0)

    return make_loader(train_idx, True), make_loader(val_idx, False)


def train_one_trm(
    trm_type: str,
    phases: list,
    epochs_per_phase: int,
    device: str,
    batch_size: int,
    learning_rate: float,
    num_samples: int,
    checkpoint_dir: Path,
    config_id: str,
    resume_path: str = None,
) -> dict:
    """Train a single TRM type across specified phases."""

    model_cls, state_dim = MODEL_REGISTRY[trm_type]
    curriculum_cls = CURRICULUM_REGISTRY[trm_type]
    loss_cls = LOSS_REGISTRY[trm_type]

    # Create model
    model = model_cls(state_dim=state_dim).to(device)
    loss_fn = loss_cls().to(device)

    param_count = sum(p.numel() for p in model.parameters())
    logger.info(f"[{trm_type}] Model: {model_cls.__name__}, params: {param_count:,}, state_dim: {state_dim}")

    optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=5)

    # Resume
    start_phase = phases[0]
    if resume_path and Path(resume_path).exists():
        ckpt = torch.load(resume_path, map_location=device)
        model.load_state_dict(ckpt["model_state_dict"])
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_phase = ckpt.get("phase", phases[0])
        logger.info(f"[{trm_type}] Resumed from {resume_path}, phase={start_phase}")

    # SC config for curriculum
    sc_config = SCConfigData()
    curriculum = curriculum_cls(sc_config)

    history = {"train_loss": [], "val_loss": [], "phase": []}
    overall_best_loss = float("inf")

    for phase in phases:
        if phase < start_phase:
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"[{trm_type}] Phase {phase} — generating {num_samples} samples")
        logger.info(f"{'='*60}")

        data = curriculum.generate(phase=phase, num_samples=num_samples)
        train_loader, val_loader = prepare_dataloader(data, batch_size)

        best_val_loss = float("inf")

        for epoch in range(1, epochs_per_phase + 1):
            # Train
            model.train()
            train_loss_sum = 0.0
            train_batches = 0

            for states, act_disc, act_cont, rews in train_loader:
                states = states.to(device)
                targets = {
                    "action_discrete": act_disc.to(device),
                    "action_continuous": act_cont.to(device),
                    "rewards": rews.to(device),
                }

                optimizer.zero_grad()
                outputs = model(states)
                loss = loss_fn(outputs, targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                train_loss_sum += loss.item()
                train_batches += 1

            avg_train = train_loss_sum / max(1, train_batches)

            # Validate
            model.eval()
            val_loss_sum = 0.0
            val_batches = 0

            with torch.no_grad():
                for states, act_disc, act_cont, rews in val_loader:
                    states = states.to(device)
                    targets = {
                        "action_discrete": act_disc.to(device),
                        "action_continuous": act_cont.to(device),
                        "rewards": rews.to(device),
                    }
                    outputs = model(states)
                    loss = loss_fn(outputs, targets)
                    val_loss_sum += loss.item()
                    val_batches += 1

            avg_val = val_loss_sum / max(1, val_batches)
            scheduler.step(avg_val)

            history["train_loss"].append(avg_train)
            history["val_loss"].append(avg_val)
            history["phase"].append(phase)

            is_best = avg_val < best_val_loss
            if is_best:
                best_val_loss = avg_val

            if epoch % 10 == 0 or epoch == 1 or is_best:
                lr_now = optimizer.param_groups[0]["lr"]
                marker = " *" if is_best else ""
                logger.info(
                    f"  [{trm_type}] Phase {phase} Epoch {epoch}/{epochs_per_phase} "
                    f"train={avg_train:.4f} val={avg_val:.4f} lr={lr_now:.2e}{marker}"
                )

            if is_best:
                best_path = checkpoint_dir / f"trm_{trm_type}_{config_id}_phase{phase}_best.pt"
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "trm_type": trm_type,
                    "config_id": config_id,
                    "phase": phase,
                    "epoch": epoch,
                    "val_loss": best_val_loss,
                    "state_dim": state_dim,
                    "model_class": model_cls.__name__,
                }, best_path)

        logger.info(f"[{trm_type}] Phase {phase} done. Best val loss: {best_val_loss:.4f}")

        if best_val_loss < overall_best_loss:
            overall_best_loss = best_val_loss

        # Load best for next phase
        best_path = checkpoint_dir / f"trm_{trm_type}_{config_id}_phase{phase}_best.pt"
        if best_path.exists() and phase < max(phases):
            ckpt = torch.load(best_path, map_location=device)
            model.load_state_dict(ckpt["model_state_dict"])

    # Save final
    final_path = checkpoint_dir / f"trm_{trm_type}_{config_id}_final.pt"
    torch.save({
        "model_state_dict": model.state_dict(),
        "trm_type": trm_type,
        "config_id": config_id,
        "state_dim": state_dim,
        "model_class": model_cls.__name__,
        "history": history,
        "timestamp": datetime.utcnow().isoformat(),
    }, final_path)

    logger.info(f"[{trm_type}] Training complete. Final model: {final_path}")

    return {
        "trm_type": trm_type,
        "final_loss": overall_best_loss,
        "final_path": str(final_path),
        "phases_completed": len(phases),
        "total_epochs": len(history["train_loss"]),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Per-TRM Curriculum Training")

    parser.add_argument("--trm-type", type=str, default="all",
                        choices=ALL_TRM_TYPES + ["all"],
                        help="TRM type to train (or 'all')")
    parser.add_argument("--phase", type=str, default="all",
                        help="Curriculum phase: 1, 2, 3, or 'all'")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Epochs per phase")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Training device: cuda or cpu")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=1e-4,
                        help="Learning rate")
    parser.add_argument("--num-samples", type=int, default=10000,
                        help="Samples per phase")
    parser.add_argument("--config-id", type=str, default="default_beer_game",
                        help="Supply chain config ID for checkpoint naming")
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints",
                        help="Checkpoint directory")
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from checkpoint file")

    args = parser.parse_args()

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU")
        device = "cpu"
    logger.info(f"Device: {device}")

    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Determine phases
    if args.phase == "all":
        phases = [1, 2, 3]
    else:
        phases = [int(args.phase)]

    # Determine TRM types
    if args.trm_type == "all":
        trm_types = ALL_TRM_TYPES
    else:
        trm_types = [args.trm_type]

    config_id = args.config_id.lower().replace("-", "_").replace(" ", "_")

    all_results = {}
    for trm_type in trm_types:
        logger.info(f"\n{'#'*60}")
        logger.info(f"# Training TRM: {trm_type}")
        logger.info(f"{'#'*60}")

        result = train_one_trm(
            trm_type=trm_type,
            phases=phases,
            epochs_per_phase=args.epochs,
            device=device,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            num_samples=args.num_samples,
            checkpoint_dir=checkpoint_dir,
            config_id=config_id,
            resume_path=args.resume,
        )
        all_results[trm_type] = result

    # Save summary
    summary_path = checkpoint_dir / f"training_summary_{config_id}.json"
    with open(summary_path, "w") as f:
        json.dump(all_results, f, indent=2)

    logger.info(f"\nAll training complete. Summary: {summary_path}")
    for trm_type, result in all_results.items():
        logger.info(f"  {trm_type}: loss={result['final_loss']:.4f}, epochs={result['total_epochs']}")


if __name__ == "__main__":
    main()

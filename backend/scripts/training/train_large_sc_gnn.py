#!/usr/bin/env python3
"""
Training script for Scalable GraphSAGE on Large Supply Chains.

Supports:
- Database-loaded supply chain configurations
- Synthetic large-scale supply chains (50+ nodes)
- Mini-batch training with neighbor sampling
- Mixed precision training (AMP)
- Multi-task learning (order, demand, cost, bullwhip)

Usage:
    # Train on database config
    python train_large_sc_gnn.py --config-id 1 --epochs 50 --device cuda

    # Train on synthetic 50-node SC
    python train_large_sc_gnn.py --synthetic --num-nodes 50 --epochs 100

    # Temporal model with sequence window
    python train_large_sc_gnn.py --config-id 1 --temporal --window 10 --epochs 50

    # Resume from checkpoint
    python train_large_sc_gnn.py --config-id 1 --resume checkpoints/large_sc_epoch20.pt
"""

import argparse
import logging
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List

import numpy as np

# Add parent paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# PyTorch imports
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.cuda.amp import GradScaler, autocast
    from torch_geometric.loader import DataLoader as PyGDataLoader
    TORCH_AVAILABLE = True
except ImportError as e:
    print(f"PyTorch not available: {e}")
    TORCH_AVAILABLE = False
    sys.exit(1)

from app.models.gnn.scalable_graphsage import (
    ScalableGraphSAGE,
    TemporalScalableGNN,
    create_scalable_gnn
)
from app.models.gnn.large_sc_data_generator import (
    generate_synthetic_config,
    generate_training_dataset,
    generate_temporal_training_data,
    load_config_from_db,
    LargeSupplyChainConfig
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = BACKEND_ROOT / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


class LargeSCTrainer:
    """Trainer for Scalable GraphSAGE on large supply chains."""

    def __init__(
        self,
        model: nn.Module,
        device: str = "cuda",
        learning_rate: float = 1e-3,
        weight_decay: float = 0.01,
        use_amp: bool = True,
        checkpoint_dir: Path = CHECKPOINT_DIR,
        config_name: str = "large_sc"
    ):
        self.model = model.to(device)
        self.device = device
        self.use_amp = use_amp and device == "cuda"
        self.checkpoint_dir = checkpoint_dir
        self.config_name = config_name

        # Optimizer
        self.optimizer = optim.AdamW(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )

        # Learning rate scheduler
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode="min",
            factor=0.5,
            patience=5,
            verbose=True
        )

        # AMP scaler
        self.scaler = GradScaler() if self.use_amp else None

        # Loss functions
        self.order_loss_fn = nn.HuberLoss(delta=1.0)
        self.cost_loss_fn = nn.MSELoss()
        self.bullwhip_loss_fn = nn.MSELoss()

        # Multi-task loss weights (learnable)
        self.log_vars = nn.Parameter(torch.zeros(3, device=device))

        # History
        self.history = {
            "train_loss": [],
            "val_loss": [],
            "order_loss": [],
            "cost_loss": [],
            "learning_rate": []
        }

    def compute_loss(
        self,
        outputs: Dict[str, torch.Tensor],
        targets: Dict[str, torch.Tensor]
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """Compute multi-task loss with uncertainty weighting."""
        losses = {}

        # Order prediction loss
        if 'y_order' in targets:
            order_pred = outputs['order'].squeeze(-1)
            order_target = targets['y_order'].squeeze(-1)
            losses['order'] = self.order_loss_fn(order_pred, order_target)

        # Cost prediction loss
        if 'y_cost' in targets:
            cost_pred = outputs['cost'].squeeze(-1)
            cost_target = targets['y_cost'].squeeze(-1)
            losses['cost'] = self.cost_loss_fn(cost_pred, cost_target)

        # Combine with uncertainty weighting
        total_loss = 0
        loss_info = {}

        for i, (name, loss) in enumerate(losses.items()):
            precision = torch.exp(-self.log_vars[i])
            weighted_loss = precision * loss + self.log_vars[i]
            total_loss += weighted_loss
            loss_info[f"{name}_loss"] = loss.item()
            loss_info[f"{name}_weight"] = precision.item()

        loss_info["total_loss"] = total_loss.item()
        return total_loss, loss_info

    def train_epoch_pyg(
        self,
        train_loader: PyGDataLoader
    ) -> Tuple[float, Dict[str, float]]:
        """Train for one epoch on PyG DataLoader."""
        self.model.train()
        total_loss = 0
        num_batches = 0
        epoch_losses = {}

        for batch in train_loader:
            batch = batch.to(self.device)

            self.optimizer.zero_grad()

            # Forward pass
            if self.use_amp:
                with autocast():
                    outputs = self.model(
                        x=batch.x,
                        edge_index=batch.edge_index,
                        edge_attr=batch.edge_attr if hasattr(batch, 'edge_attr') else None,
                        master_types=batch.master_types if hasattr(batch, 'master_types') else None,
                        node_types=batch.node_types if hasattr(batch, 'node_types') else None,
                        batch=batch.batch if hasattr(batch, 'batch') else None
                    )
                    loss, loss_info = self.compute_loss(outputs, {
                        'y_order': batch.y_order,
                        'y_cost': batch.y_cost if hasattr(batch, 'y_cost') else None
                    })

                self.scaler.scale(loss).backward()
                self.scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.scaler.step(self.optimizer)
                self.scaler.update()
            else:
                outputs = self.model(
                    x=batch.x,
                    edge_index=batch.edge_index,
                    edge_attr=batch.edge_attr if hasattr(batch, 'edge_attr') else None,
                    master_types=batch.master_types if hasattr(batch, 'master_types') else None,
                    node_types=batch.node_types if hasattr(batch, 'node_types') else None,
                    batch=batch.batch if hasattr(batch, 'batch') else None
                )
                loss, loss_info = self.compute_loss(outputs, {
                    'y_order': batch.y_order,
                    'y_cost': batch.y_cost if hasattr(batch, 'y_cost') else None
                })

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

            # Accumulate losses
            for k, v in loss_info.items():
                epoch_losses[k] = epoch_losses.get(k, 0) + v

        avg_loss = total_loss / max(num_batches, 1)
        avg_losses = {k: v / max(num_batches, 1) for k, v in epoch_losses.items()}

        return avg_loss, avg_losses

    def train_epoch_temporal(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        edge_index: np.ndarray,
        edge_attr: np.ndarray,
        batch_size: int = 32
    ) -> Tuple[float, Dict[str, float]]:
        """Train for one epoch on temporal data."""
        self.model.train()
        num_samples = len(X)
        indices = np.random.permutation(num_samples)
        total_loss = 0
        num_batches = 0

        # Convert to tensors
        edge_index_t = torch.tensor(edge_index, dtype=torch.long, device=self.device)
        edge_attr_t = torch.tensor(edge_attr, dtype=torch.float, device=self.device)

        for i in range(0, num_samples, batch_size):
            batch_indices = indices[i:i + batch_size]
            x_batch = torch.tensor(X[batch_indices], dtype=torch.float, device=self.device)
            y_batch = torch.tensor(Y[batch_indices], dtype=torch.float, device=self.device)

            self.optimizer.zero_grad()

            if self.use_amp:
                with autocast():
                    outputs = self.model(x_batch, edge_index_t, edge_attr_t)
                    loss, _ = self.compute_loss(outputs, {'y_order': y_batch})

                self.scaler.scale(loss).backward()
                self.scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.scaler.step(self.optimizer)
                self.scaler.update()
            else:
                outputs = self.model(x_batch, edge_index_t, edge_attr_t)
                loss, _ = self.compute_loss(outputs, {'y_order': y_batch})
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        return total_loss / max(num_batches, 1), {}

    def validate(
        self,
        val_loader: PyGDataLoader
    ) -> float:
        """Validate on validation set."""
        self.model.eval()
        total_loss = 0
        num_batches = 0

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(self.device)

                outputs = self.model(
                    x=batch.x,
                    edge_index=batch.edge_index,
                    edge_attr=batch.edge_attr if hasattr(batch, 'edge_attr') else None,
                    master_types=batch.master_types if hasattr(batch, 'master_types') else None,
                    node_types=batch.node_types if hasattr(batch, 'node_types') else None
                )

                loss, _ = self.compute_loss(outputs, {
                    'y_order': batch.y_order,
                    'y_cost': batch.y_cost if hasattr(batch, 'y_cost') else None
                })

                total_loss += loss.item()
                num_batches += 1

        return total_loss / max(num_batches, 1)

    def save_checkpoint(
        self,
        epoch: int,
        val_loss: float,
        is_best: bool = False
    ):
        """Save model checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "config_name": self.config_name,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "log_vars": self.log_vars.data.cpu(),
            "val_loss": val_loss,
            "history": self.history
        }

        # Save regular checkpoint
        checkpoint_path = self.checkpoint_dir / f"{self.config_name}_epoch{epoch}.pt"
        torch.save(checkpoint, checkpoint_path)
        logger.info(f"Saved checkpoint: {checkpoint_path}")

        # Save best model
        if is_best:
            best_path = self.checkpoint_dir / f"{self.config_name}_best.pt"
            torch.save(checkpoint, best_path)
            logger.info(f"Saved best model: {best_path}")

    def load_checkpoint(self, checkpoint_path: str) -> int:
        """Load checkpoint and return starting epoch."""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        self.log_vars.data = checkpoint["log_vars"].to(self.device)
        self.history = checkpoint.get("history", self.history)
        logger.info(f"Loaded checkpoint from {checkpoint_path}")
        return checkpoint["epoch"]


def train_pyg_model(
    model: nn.Module,
    train_dataset: List,
    val_dataset: List,
    config_name: str,
    epochs: int = 50,
    batch_size: int = 32,
    device: str = "cuda",
    use_amp: bool = True,
    resume: Optional[str] = None
):
    """Train model on PyG dataset."""
    trainer = LargeSCTrainer(
        model=model,
        device=device,
        use_amp=use_amp,
        config_name=config_name
    )

    # Create data loaders
    train_loader = PyGDataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = PyGDataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    start_epoch = 0
    if resume:
        start_epoch = trainer.load_checkpoint(resume)

    best_val_loss = float("inf")

    for epoch in range(start_epoch + 1, epochs + 1):
        logger.info(f"\nEpoch {epoch}/{epochs}")

        # Train
        train_loss, loss_info = trainer.train_epoch_pyg(train_loader)
        logger.info(f"Train Loss: {train_loss:.4f}")
        for k, v in loss_info.items():
            logger.info(f"  {k}: {v:.4f}")

        # Validate
        val_loss = trainer.validate(val_loader)
        logger.info(f"Val Loss: {val_loss:.4f}")

        # Update scheduler
        trainer.scheduler.step(val_loss)

        # Record history
        trainer.history["train_loss"].append(train_loss)
        trainer.history["val_loss"].append(val_loss)
        trainer.history["learning_rate"].append(trainer.optimizer.param_groups[0]["lr"])

        # Save checkpoint
        is_best = val_loss < best_val_loss
        if is_best:
            best_val_loss = val_loss

        if epoch % 10 == 0 or is_best:
            trainer.save_checkpoint(epoch, val_loss, is_best)

    # Save final model
    final_path = CHECKPOINT_DIR / f"{config_name}_final.pt"
    torch.save({
        "model_state_dict": model.state_dict(),
        "config_name": config_name,
        "history": trainer.history
    }, final_path)
    logger.info(f"Training complete! Final model saved to: {final_path}")


def train_temporal_model(
    model: nn.Module,
    data: Dict[str, np.ndarray],
    config_name: str,
    epochs: int = 50,
    batch_size: int = 32,
    device: str = "cuda",
    use_amp: bool = True,
    resume: Optional[str] = None
):
    """Train temporal model on sequential data."""
    trainer = LargeSCTrainer(
        model=model,
        device=device,
        use_amp=use_amp,
        config_name=config_name
    )

    # Split data
    num_samples = len(data['X'])
    split_idx = int(0.8 * num_samples)
    indices = np.random.permutation(num_samples)

    X_train = data['X'][indices[:split_idx]]
    Y_train = data['Y'][indices[:split_idx]]
    X_val = data['X'][indices[split_idx:]]
    Y_val = data['Y'][indices[split_idx:]]

    start_epoch = 0
    if resume:
        start_epoch = trainer.load_checkpoint(resume)

    best_val_loss = float("inf")

    for epoch in range(start_epoch + 1, epochs + 1):
        logger.info(f"\nEpoch {epoch}/{epochs}")

        # Train
        train_loss, _ = trainer.train_epoch_temporal(
            X_train, Y_train,
            data['edge_index'], data['edge_attr'],
            batch_size
        )
        logger.info(f"Train Loss: {train_loss:.4f}")

        # Validate (simplified)
        model.eval()
        with torch.no_grad():
            edge_index_t = torch.tensor(data['edge_index'], dtype=torch.long, device=device)
            edge_attr_t = torch.tensor(data['edge_attr'], dtype=torch.float, device=device)
            x_val_t = torch.tensor(X_val, dtype=torch.float, device=device)
            y_val_t = torch.tensor(Y_val, dtype=torch.float, device=device)

            outputs = model(x_val_t, edge_index_t, edge_attr_t)
            val_loss = trainer.order_loss_fn(
                outputs['order'].squeeze(-1),
                y_val_t.squeeze(-1)
            ).item()

        logger.info(f"Val Loss: {val_loss:.4f}")

        trainer.scheduler.step(val_loss)
        trainer.history["train_loss"].append(train_loss)
        trainer.history["val_loss"].append(val_loss)

        is_best = val_loss < best_val_loss
        if is_best:
            best_val_loss = val_loss

        if epoch % 10 == 0 or is_best:
            trainer.save_checkpoint(epoch, val_loss, is_best)

    logger.info("Training complete!")


def main():
    parser = argparse.ArgumentParser(description="Train Scalable GraphSAGE on Large Supply Chains")

    # Data source
    parser.add_argument("--config-id", type=int, help="Database config ID to load")
    parser.add_argument("--config-name", type=str, help="Database config name to load")
    parser.add_argument("--synthetic", action="store_true", help="Generate synthetic config")
    parser.add_argument("--num-nodes", type=int, default=50, help="Nodes for synthetic config")
    parser.add_argument("--num-tiers", type=int, default=5, help="Tiers for synthetic config")

    # Model architecture
    parser.add_argument("--temporal", action="store_true", help="Use temporal model")
    parser.add_argument("--hidden-dim", type=int, default=128, help="Hidden dimension")
    parser.add_argument("--num-layers", type=int, default=3, help="Number of GNN layers")
    parser.add_argument("--num-heads", type=int, default=4, help="Attention heads")
    parser.add_argument("--dropout", type=float, default=0.1, help="Dropout rate")

    # Training
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--device", type=str, default="cuda", help="Device (cuda/cpu)")
    parser.add_argument("--no-amp", action="store_true", help="Disable mixed precision")

    # Data generation
    parser.add_argument("--num-sims", type=int, default=100, help="Number of simulations")
    parser.add_argument("--timesteps", type=int, default=100, help="Timesteps per simulation")
    parser.add_argument("--samples-per-sim", type=int, default=5, help="Samples per simulation")
    parser.add_argument("--window", type=int, default=10, help="Temporal window size")

    # Checkpointing
    parser.add_argument("--resume", type=str, help="Resume from checkpoint")
    parser.add_argument("--checkpoint-dir", type=str, default=str(CHECKPOINT_DIR))

    args = parser.parse_args()

    # Device setup
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU")
        device = "cpu"

    use_amp = not args.no_amp and device == "cuda"
    logger.info(f"Using device: {device}, AMP: {use_amp}")

    # Load or generate config
    if args.config_id:
        config = load_config_from_db(args.config_id)
        config_name = f"config_{args.config_id}"
    elif args.config_name:
        # Try to find by name
        try:
            from app.db.session import sync_engine
            from app.models.supply_chain_config import SupplyChainConfig
            from sqlalchemy.orm import Session

            with Session(sync_engine) as session:
                db_config = session.query(SupplyChainConfig).filter_by(name=args.config_name).first()
                if db_config:
                    config = load_config_from_db(db_config.id)
                    config_name = args.config_name.lower().replace(" ", "_")
                else:
                    raise ValueError(f"Config '{args.config_name}' not found")
        except Exception as e:
            logger.warning(f"Could not load from DB: {e}, using synthetic")
            config = generate_synthetic_config(args.num_nodes, args.num_tiers, name=args.config_name)
            config_name = args.config_name.lower().replace(" ", "_")
    elif args.synthetic:
        config = generate_synthetic_config(args.num_nodes, args.num_tiers)
        config_name = f"synthetic_{args.num_nodes}nodes"
    else:
        logger.info("No config specified, using default 50-node synthetic")
        config = generate_synthetic_config(50, 5)
        config_name = "synthetic_50nodes"

    logger.info(f"Config: {config.name}, Nodes: {config.num_nodes()}, Edges: {config.num_edges()}")

    # Model configuration
    model_config = {
        'node_feature_dim': 8,
        'edge_feature_dim': 4,
        'hidden_dim': args.hidden_dim,
        'num_layers': args.num_layers,
        'num_heads': args.num_heads,
        'dropout': args.dropout,
        'use_edge_features': True,
        'use_node_types': True,
    }

    if args.temporal:
        model_config['window_size'] = args.window
        model_config['num_gnn_layers'] = args.num_layers
        model_config['num_temporal_layers'] = 2

        # Generate temporal data
        logger.info("Generating temporal training data...")
        data = generate_temporal_training_data(
            config=config,
            num_simulations=args.num_sims,
            timesteps_per_sim=args.timesteps,
            window_size=args.window,
            samples_per_sim=args.samples_per_sim
        )
        logger.info(f"Generated {len(data['X'])} temporal samples")

        # Create temporal model
        model = create_scalable_gnn(model_config, temporal=True)
        logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

        # Train
        train_temporal_model(
            model=model,
            data=data,
            config_name=config_name,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device=device,
            use_amp=use_amp,
            resume=args.resume
        )
    else:
        # Generate PyG dataset
        logger.info("Generating training dataset...")
        dataset = generate_training_dataset(
            config=config,
            num_simulations=args.num_sims,
            timesteps_per_sim=args.timesteps,
            samples_per_sim=args.samples_per_sim,
            window_size=args.window
        )
        logger.info(f"Generated {len(dataset)} samples")

        # Split dataset
        split_idx = int(0.8 * len(dataset))
        train_dataset = dataset[:split_idx]
        val_dataset = dataset[split_idx:]

        # Create model
        model = create_scalable_gnn(model_config, temporal=False)
        logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

        # Train
        train_pyg_model(
            model=model,
            train_dataset=train_dataset,
            val_dataset=val_dataset,
            config_name=config_name,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device=device,
            use_amp=use_amp,
            resume=args.resume
        )


if __name__ == "__main__":
    main()

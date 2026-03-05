#!/usr/bin/env python3
"""Lightweight temporal GNN training script with GPU and AMP integration."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from contextlib import nullcontext
from typing import Optional, Tuple

import numpy as np

TORCH_IMPORT_ERROR = None
F = None
try:  # pragma: no cover - optional dependency
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.cuda.amp import GradScaler, autocast
    import torch.nn.functional as F  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - depends on torch availability
    TORCH_IMPORT_ERROR = exc
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    optim = None  # type: ignore[assignment]
    GradScaler = None  # type: ignore[assignment]
    autocast = None  # type: ignore[assignment]

from app.rl.config import SimulationParams
from app.rl.data_generator import (
    DbLookupConfig,
    load_sequences_from_db,
)
from app.core.db_urls import resolve_sync_database_url
from app.rl.policy import SimpleTemporalHead
from app.utils.device import device_scope, empty_cache, get_available_device

# Import enhanced GNN architectures
try:
    from app.models.gnn.enhanced_gnn import (
        GraphSAGESupplyChain,
        EnhancedTemporalGNN,
        create_enhanced_gnn
    )
    ENHANCED_GNN_AVAILABLE = True
except ImportError:
    ENHANCED_GNN_AVAILABLE = False

# Import MLflow experiment tracking
try:
    from app.ml.experiment_tracking import ExperimentTracker
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

TRAINING_ROOT = Path(__file__).resolve().parents[2] / "training_jobs"


if torch is not None:

    class TinyBackbone(nn.Module):
        """
        Stand-in for your temporal GNN:
        - Input: X [B, T, N, F]
        - Output: H [B, T, N, H]
        """

        def __init__(self, in_dim: int, hidden_dim: int = 64):
            super().__init__()
            self.net = nn.Sequential(
                nn.LayerNorm(in_dim),
                nn.Linear(in_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            B, T, N, F = x.shape
            x = x.reshape(B * T * N, F)
            h = self.net(x)
            return h.reshape(B, T, N, -1)

else:

    class TinyBackbone:  # type: ignore[empty-body]
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("TinyBackbone requires torch; training should have exited earlier")


def get_data(
    source: str,
    window: int,
    horizon: int,
    db_url: Optional[str],
    steps_table: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Load or generate training data.

    Args:
        source: 'db' to load from database, 'sim' to generate synthetic data
        window: number of time steps in each input sequence
        horizon: number of future steps to predict
        db_url: database connection string
        steps_table: name of the table containing simulation steps

    Returns:
        X: [num_windows, window, num_nodes, num_features] input sequences
        A: [2, num_nodes, num_nodes] adjacency matrices for graph structure
        P: [num_windows, 0] global context (unused)
        Y: [num_windows, horizon, num_nodes] target action indices
    """
    params = SimulationParams()
    if source == "db":
        if not db_url:
            db_url = resolve_sync_database_url()
        cfg = DbLookupConfig(database_url=db_url, steps_table=steps_table)
        return load_sequences_from_db(cfg, params=params, game_ids=None, window=window, horizon=horizon)
    if source == "sim":
        raise ValueError(
            "Simulation-based data generation has been removed. "
            "Use source='db' with a valid steps_table and db_url."
        )
    raise ValueError(f"Unknown source: {source}")


def train_epoch(
    model: nn.Module,
    head: nn.Module,
    X: np.ndarray,
    Y: np.ndarray,
    optimizer: optim.Optimizer,
    device: torch.device,
    scaler: Optional[GradScaler],
    amp_enabled: bool,
) -> float:
    """Train for one epoch on the full dataset arrays."""
    model.train()
    head.train()
    B, T, N, feature_dim = X.shape
    if Y.ndim == 3 and Y.shape[1] == N:
        Y = np.swapaxes(Y, 1, 2)
    H = Y.shape[1]  # horizon

    x = torch.as_tensor(X, dtype=torch.float32, device=device)
    y = torch.as_tensor(Y, dtype=torch.long, device=device)

    optimizer.zero_grad(set_to_none=True)

    use_amp = bool(amp_enabled and autocast is not None)
    autocast_ctx = autocast() if use_amp else nullcontext()
    with autocast_ctx:
        h = model(x)               # [B, T, N, hidden]
        # repeat final hidden state for multi-step decoding if needed
        h_tail = h[:, -1:].repeat(1, H, 1, 1)
        logits = head(h_tail)      # [B, H, N, A]
        logits_flat = logits.reshape(-1, logits.shape[-1])
        targets_flat = y.reshape(-1)
        # compute per-step loss with temporal discounting toward later horizons
        losses = F.cross_entropy(logits_flat, targets_flat, reduction="none")
        losses = losses.view(B, H, N)
        # earlier steps receive higher weight (gamma close to 1 favours long-horizon)
        gamma = 0.95
        discounts = torch.pow(torch.full((H,), gamma, device=device), torch.arange(H, device=device))
        weighted = losses * discounts.view(1, H, 1)
        loss = weighted.mean()

    if use_amp and scaler is not None:
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
    else:
        loss.backward()
        optimizer.step()

    loss_value = float(loss.detach().cpu().item())
    empty_cache()
    return loss_value


def _normalize_features(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Standardize per-feature statistics across all nodes and windows."""
    # Compute mean/std across batch, time, and node axes
    feature_mean = X.mean(axis=(0, 1, 2), keepdims=True)
    feature_std = X.std(axis=(0, 1, 2), keepdims=True)
    feature_std = np.where(feature_std < 1e-6, 1.0, feature_std)
    X_norm = (X - feature_mean) / feature_std
    return X_norm, feature_mean.reshape(-1), feature_std.reshape(-1)


def create_model(architecture: str, in_dim: int, hidden_dim: int, edge_feature_dim: int = 4) -> Tuple[nn.Module, Optional[nn.Module]]:
    """
    Create GNN model based on architecture type.

    Args:
        architecture: Model architecture ("tiny", "graphsage", "temporal", "enhanced")
        in_dim: Input feature dimension
        hidden_dim: Hidden dimension
        edge_feature_dim: Edge feature dimension for graph models

    Returns:
        model: The backbone model
        head: Optional prediction head (None for architectures with built-in heads)
    """
    if architecture == "tiny":
        # Original lightweight backbone
        model = TinyBackbone(in_dim=in_dim, hidden_dim=hidden_dim)
        head = SimpleTemporalHead(hidden_dim=hidden_dim)
        return model, head

    if not ENHANCED_GNN_AVAILABLE:
        raise RuntimeError(
            f"Architecture '{architecture}' requires enhanced GNN models, but they are not available. "
            "Falling back to 'tiny' architecture or check imports."
        )

    if architecture == "graphsage":
        # GraphSAGE with multi-task heads built-in
        model = GraphSAGESupplyChain(
            node_feature_dim=in_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            num_layers=3,
            dropout=0.1,
            output_dim=1
        )
        return model, None  # Built-in heads

    elif architecture == "temporal":
        # Enhanced temporal GNN with attention - requires edge index
        model = EnhancedTemporalGNN(
            node_feature_dim=in_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            num_spatial_layers=2,
            num_temporal_layers=2,
            num_heads=4,
            dropout=0.1,
            window_size=10
        )
        return model, None  # Built-in heads

    elif architecture == "enhanced":
        # GraphSAGE + Temporal Attention (most powerful)
        model = create_enhanced_gnn(
            architecture="temporal",
            node_feature_dim=in_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            num_spatial_layers=3,
            num_temporal_layers=2,
            num_heads=8,
            dropout=0.1
        )
        return model, None  # Built-in heads

    else:
        raise ValueError(f"Unknown architecture: {architecture}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a GNN for supply chain simulation")
    parser.add_argument(
        "--source",
        choices=["db", "sim"],
        default="db",
        help="Data source: 'db' for database, 'sim' for simulator",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database connection URL (default: use DATABASE_URL env var)",
    )
    parser.add_argument(
        "--steps-table",
        default="simulation_steps",
        help="Name of the table containing simulation steps",
    )
    parser.add_argument("--window", type=int, default=52, help="Number of time steps in each input sequence")
    parser.add_argument("--horizon", type=int, default=1, help="Number of future steps to predict")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")

    default_device = "cpu"
    if torch is not None:
        try:
            if torch.cuda.is_available():
                default_device = "cuda"
        except Exception:
            default_device = "cpu"

    parser.add_argument(
        "--device",
        default=default_device,
        help="Device to train on (cuda/cpu)",
    )
    parser.add_argument(
        "--save-path",
        default="artifacts/temporal_gnn.pt",
        help="Path to save the trained model",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Optional path to an .npz dataset with arrays X,A,P,Y. If provided, overrides --source/--db-url.",
    )
    parser.add_argument(
        "--architecture",
        choices=["tiny", "graphsage", "temporal", "enhanced"],
        default="tiny",
        help="GNN architecture: 'tiny' (lightweight), 'graphsage', 'temporal' (attention), 'enhanced' (GraphSAGE+temporal)",
    )
    parser.add_argument(
        "--no-amp",
        dest="amp",
        action="store_false",
        help="Disable mixed precision even when training on CUDA.",
    )
    parser.add_argument(
        "--amp",
        dest="amp",
        action="store_true",
        help="Enable mixed precision (default when CUDA is available).",
    )
    parser.add_argument(
        "--mlflow-tracking-uri",
        default="file:./mlruns",
        help="MLflow tracking server URI (default: file:./mlruns)",
    )
    parser.add_argument(
        "--experiment-name",
        default="Supply Chain GNN",
        help="MLflow experiment name (default: Supply Chain GNN)",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="MLflow run name (default: auto-generated)",
    )
    parser.add_argument(
        "--no-mlflow",
        dest="use_mlflow",
        action="store_false",
        help="Disable MLflow experiment tracking",
    )
    parser.add_argument(
        "--config-name",
        default=None,
        help="Supply chain config name (included in checkpoint metadata)",
    )
    parser.set_defaults(amp=True, use_mlflow=True)
    args = parser.parse_args()

    if torch is None:  # pragma: no cover - environment without torch
        payload = {
            "status": "unavailable",
            "reason": str(TORCH_IMPORT_ERROR) if TORCH_IMPORT_ERROR else "torch not installed",
        }
        print(json.dumps(payload))
        return

    # --- Load/Generate data
    dataset_path = args.dataset
    if not dataset_path:
        metadata_path = TRAINING_ROOT / "latest_dataset.json"
        if metadata_path.exists():
            try:
                with metadata_path.open("r", encoding="utf-8") as fp:
                    metadata = json.load(fp)
                candidate = metadata.get("best_dataset")
                if candidate and os.path.exists(candidate):
                    dataset_path = candidate
                    print(f"Using dataset from metadata: {dataset_path}")
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Warning: unable to read dataset metadata: {exc}")

    if dataset_path:
        print(f"Loading dataset from {dataset_path}...")
        data = np.load(dataset_path)
        required = {"X", "A", "P", "Y"}
        if not required.issubset(set(data.files)):
            raise RuntimeError(
                f"Dataset {dataset_path} missing required arrays {required}. Found: {set(data.files)}"
            )
        X, A, P, Y = data["X"], data["A"], data["P"], data["Y"]
    else:
        print(f"Loading data from {args.source}...")
        X, A, P, Y = get_data(
            source=args.source,
            window=args.window,
            horizon=args.horizon,
            db_url=args.db_url,
            steps_table=args.steps_table,
        )
    print(f"Loaded {len(X)} training samples")
    print(f"Input shape: {X.shape}, Target shape: {Y.shape}")

    X, feature_mean, feature_std = _normalize_features(X)
    print("Applied feature normalization (z-score) across the training corpus.")

    # Initialize MLflow tracking if enabled
    tracker = None
    if args.use_mlflow and MLFLOW_AVAILABLE:
        try:
            tracker = ExperimentTracker(
                tracking_uri=args.mlflow_tracking_uri,
                experiment_name=args.experiment_name
            )
            print(f"MLflow tracking enabled: experiment='{args.experiment_name}'")
        except Exception as e:
            print(f"Warning: Failed to initialize MLflow: {e}")
            tracker = None
    elif args.use_mlflow and not MLFLOW_AVAILABLE:
        print("Warning: MLflow requested but not available. Install with: pip install mlflow")

    target_device = get_available_device(args.device)
    if target_device.type == "cuda":
        gpu_name = torch.cuda.get_device_name(target_device)
        print(f"Using device: {target_device} ({gpu_name})")
    else:
        print(f"Using device: {target_device}")

    amp_enabled = bool(args.amp and target_device.type == "cuda" and autocast is not None and GradScaler is not None)
    if amp_enabled:
        print("Mixed precision training enabled (CUDA autocast + GradScaler).")
    elif target_device.type == "cuda" and args.amp and autocast is None:
        print("Warning: torch.cuda.amp is unavailable; proceeding without mixed precision.")

    in_dim = X.shape[-1]
    hidden_dim = 128 if args.architecture != "tiny" else 64  # Larger hidden dim for advanced architectures

    print(f"Creating {args.architecture} architecture...")
    model, head = create_model(
        architecture=args.architecture,
        in_dim=in_dim,
        hidden_dim=hidden_dim,
        edge_feature_dim=4
    )
    model = model.to(target_device)
    if head is not None:
        head = head.to(target_device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")
    if head is not None:
        head_params = sum(p.numel() for p in head.parameters())
        print(f"Head parameters: {head_params:,}")
        total_params += head_params
    print(f"Total parameters: {total_params:,}")

    # Create optimizer for model and head (if present)
    params = list(model.parameters())
    if head is not None:
        params += list(head.parameters())
    optimizer = optim.Adam(params, lr=1e-3)
    scaler = GradScaler(enabled=amp_enabled) if GradScaler is not None else None

    loss_history = []
    print("Starting training...")

    # Start MLflow run if tracker is available
    mlflow_run = None
    if tracker:
        run_name = args.run_name or f"{args.architecture}_{args.source}"
        mlflow_run = tracker.start_run(
            run_name=run_name,
            tags={
                "architecture": args.architecture,
                "source": args.source,
                "device": str(target_device),
            }
        )

        # Log hyperparameters
        tracker.log_params({
            "architecture": args.architecture,
            "data_source": args.source,
            "window": args.window,
            "horizon": args.horizon,
            "epochs": args.epochs,
            "hidden_dim": hidden_dim,
            "in_dim": in_dim,
            "learning_rate": 1e-3,
            "device": str(target_device),
            "amp_enabled": amp_enabled,
            "num_samples": len(X),
            "total_parameters": sum(p.numel() for p in model.parameters()) + (sum(p.numel() for p in head.parameters()) if head else 0),
        })

    with device_scope(target_device):
        for epoch in range(1, args.epochs + 1):
            loss = train_epoch(
                model,
                head,
                X,
                Y,
                optimizer,
                target_device,
                scaler,
                amp_enabled,
            )
            print(f"[epoch {epoch:02d}/{args.epochs}] loss={loss:.4f}")
            loss_history.append(loss)

            # Log metrics to MLflow
            if tracker:
                tracker.log_metrics({
                    "train_loss": loss,
                    "epoch": epoch
                }, step=epoch)

        empty_cache()

    # Log final metrics
    if tracker and loss_history:
        tracker.log_metrics({
            "final_loss": loss_history[-1],
            "min_loss": min(loss_history),
            "mean_loss": sum(loss_history) / len(loss_history)
        })

    os.makedirs(os.path.dirname(args.save_path) or ".", exist_ok=True)
    checkpoint = {
        "architecture": args.architecture,
        "backbone_state_dict": model.state_dict(),
        "in_dim": in_dim,
        "hidden_dim": hidden_dim,
        "loss_history": loss_history,
        "A": A,
        "P": P,
        "feature_mean": feature_mean,
        "feature_std": feature_std,
        "config": {
            "name": args.config_name,
            "window": args.window,
            "horizon": args.horizon,
        } if args.config_name else None,
    }
    if head is not None:
        checkpoint["head_state_dict"] = head.state_dict()

    torch.save(checkpoint, args.save_path)
    print(f"Saved model to {args.save_path}")

    # Log model and artifacts to MLflow
    if tracker:
        try:
            # Log the model checkpoint
            tracker.log_artifact(args.save_path, artifact_path="model")

            # Log training configuration as JSON
            config_dict = {
                "architecture": args.architecture,
                "data_source": args.source,
                "window": args.window,
                "horizon": args.horizon,
                "epochs": args.epochs,
                "hidden_dim": hidden_dim,
                "in_dim": in_dim,
                "device": str(target_device),
                "amp_enabled": amp_enabled,
            }
            tracker.log_dict(config_dict, "training_config.json")

            # Log loss history plot if matplotlib is available
            try:
                import matplotlib.pyplot as plt
                plt.figure(figsize=(10, 6))
                plt.plot(loss_history)
                plt.xlabel('Epoch')
                plt.ylabel('Loss')
                plt.title(f'{args.architecture} Training Loss')
                plt.grid(True)
                tracker.log_figure(plt, "loss_history.png")
                plt.close()
            except ImportError:
                pass

            print(f"Logged artifacts to MLflow run: {mlflow_run.info.run_id}")

        except Exception as e:
            print(f"Warning: Failed to log artifacts to MLflow: {e}")

        # End MLflow run
        tracker.end_run(status="FINISHED")

    payload = {
        "status": "trained",
        "architecture": args.architecture,
        "epochs": args.epochs,
        "final_loss": loss_history[-1] if loss_history else None,
        "total_parameters": total_params,
        "device": str(target_device),
        "amp_enabled": amp_enabled,
        "save_path": args.save_path,
        "feature_mean": feature_mean.tolist(),
        "feature_std": feature_std.tolist(),
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()

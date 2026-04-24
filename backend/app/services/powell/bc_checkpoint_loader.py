"""
Shared BC checkpoint loader for TMS TRMs.

Every TRM follows the same load lifecycle:
  1. Abort early if PyTorch is unavailable (heuristic-only deploy).
  2. Abort early if the checkpoint path doesn't exist.
  3. Load the checkpoint and verify the full contract
     (model_state_dict + input_dim + normalization stats).
  4. Reconstruct the TRMClassifier, load weights, `eval()`.
  5. Return a structured `BcCheckpoint` the TRM can stash.

Before this helper existed, each TRM carried a 10-line stub that only
handled steps (1) and (2). FreightProcurementTRM had a fuller loader
with a broken `from scripts.pretraining.train_tms_trms import ...`
path that silently threw at call time. Consolidating into one helper
kills the duplication, fixes the import path, and surfaces missing
contract fields clearly rather than silently falling through to heuristic.

Checkpoint contract (produced by backend/scripts/pretraining/train_tms_trms.py):
    model_state_dict : Dict[str, Tensor]
    input_dim        : int
    hidden_dims      : Tuple[int, int]           (default (128, 64))
    num_actions      : int                        (11, from ACTION_NAMES)
    feature_keys     : List[str]                  state_/derived_ columns
    feature_means    : List[float]                per-column train-set mean
    feature_stds     : List[float]                per-column train-set std
    trm_type         : str                        canonical TRM name
    best_val_acc     : float
    active_actions   : List[int]

The last three are metadata; only the first seven are required for
inference. `load_bc_checkpoint` returns None (non-fatal) when any
required key is missing and logs a structured WARNING naming the gap.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


_REQUIRED_KEYS = (
    "model_state_dict",
    "input_dim",
    "feature_keys",
    "feature_means",
    "feature_stds",
)


@dataclass
class BcCheckpoint:
    """Parsed + validated BC checkpoint, ready for inference."""
    model: Any  # TRMClassifier — typed loosely to avoid torch at import time
    input_dim: int
    feature_keys: List[str]
    feature_means: List[float]
    feature_stds: List[float]
    num_actions: int
    best_val_acc: float
    active_actions: List[int]
    trm_type: str
    raw: Dict[str, Any]  # full checkpoint dict for caller debugging


def load_bc_checkpoint(
    checkpoint_path: str,
    trm_type: str,
) -> Optional[BcCheckpoint]:
    """Load a BC checkpoint produced by train_tms_trms.py.

    Args:
        checkpoint_path: filesystem path to the `.pt` file.
        trm_type: canonical TRM name (for logging only; the checkpoint
            carries its own `trm_type` key but we don't enforce a match).

    Returns:
        BcCheckpoint on success, None on any failure. Failures are
        logged at WARNING (missing PyTorch / missing file / missing
        contract keys) or ERROR (torch load or state_dict load raised).
        Callers should fall through to heuristic when None comes back.
    """
    if not TORCH_AVAILABLE:
        logger.warning(
            "%s: PyTorch unavailable — falling back to heuristic teacher",
            trm_type,
        )
        return None

    if not os.path.exists(checkpoint_path):
        logger.info(
            "%s: no checkpoint at %s — heuristic teacher",
            trm_type, checkpoint_path,
        )
        return None

    try:
        ckpt = torch.load(checkpoint_path, map_location="cpu")
    except Exception as e:
        logger.error(
            "%s: torch.load failed for %s: %s — heuristic teacher",
            trm_type, checkpoint_path, e,
        )
        return None

    missing = [k for k in _REQUIRED_KEYS if k not in ckpt]
    if missing:
        logger.warning(
            "%s: checkpoint %s missing required keys %s — heuristic teacher. "
            "Re-train with the current trainer (train_tms_trms.py) so "
            "feature_keys/means/stds are persisted.",
            trm_type, checkpoint_path, missing,
        )
        return None

    try:
        # Import lazily — TRMClassifier lives in scripts/pretraining/, which
        # is importable from /app in the container but not from a non-Docker
        # shell unless PYTHONPATH is set.
        from scripts.pretraining.train_tms_trms import TRMClassifier
    except Exception as e:
        logger.error(
            "%s: cannot import TRMClassifier (scripts.pretraining.train_tms_trms): %s — "
            "heuristic teacher",
            trm_type, e,
        )
        return None

    input_dim = int(ckpt["input_dim"])
    hidden_dims: Tuple[int, ...] = tuple(ckpt.get("hidden_dims", (128, 64)))

    try:
        model = TRMClassifier(input_dim=input_dim, hidden_dims=hidden_dims)
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
    except Exception as e:
        logger.error(
            "%s: state_dict load failed: %s — heuristic teacher",
            trm_type, e,
        )
        return None

    logger.info(
        "%s: checkpoint loaded (input_dim=%d, val_acc=%.3f, active_actions=%s)",
        trm_type,
        input_dim,
        float(ckpt.get("best_val_acc", 0.0)),
        ckpt.get("active_actions", []),
    )

    return BcCheckpoint(
        model=model,
        input_dim=input_dim,
        feature_keys=list(ckpt["feature_keys"]),
        feature_means=list(ckpt["feature_means"]),
        feature_stds=list(ckpt["feature_stds"]),
        num_actions=int(ckpt.get("num_actions", 11)),
        best_val_acc=float(ckpt.get("best_val_acc", 0.0)),
        active_actions=list(ckpt.get("active_actions", [])),
        trm_type=str(ckpt.get("trm_type", trm_type)),
        raw=ckpt,
    )

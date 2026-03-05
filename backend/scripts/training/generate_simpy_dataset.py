#!/usr/bin/env python3
"""Generate Autonomy GNN training data from DB scenario records for a given SC config."""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = BACKEND_ROOT / "training_jobs"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

try:  # pragma: no cover - torch might be unavailable in minimal installs
    import torch
except Exception:  # noqa: ANN001
    torch = None  # type: ignore[assignment]

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session as SyncSession

from app.core.config import settings
from app.rl.config import SimulationParams
from app.rl.data_generator import load_sequences_from_db, DbLookupConfig
from app.db.session import sync_engine
from app.models.supply_chain_config import SupplyChainConfig
from app.utils.device import device_scope, empty_cache, get_available_device

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_CONFIG_NAME = "Case Beer Game"


@dataclass
class TrainingParams:
    window: int
    horizon: int
    steps_table: str = "simulation_steps"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower()).strip("-")
    return slug or "config"


def _generate_training_dataset(
    config_id: int,
    slug: str,
    params: TrainingParams,
    *,
    device: Optional["torch.device"] = None,
    amp_enabled: bool = False,
) -> Dict[str, Any]:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)

    db_url = settings.SQLALCHEMY_DATABASE_URI or None
    if not db_url:
        raise RuntimeError("Database URL not configured; cannot load training data.")

    cfg = DbLookupConfig(database_url=db_url, steps_table=params.steps_table)
    X, A, P, Y = load_sequences_from_db(
        cfg,
        SimulationParams(),
        window=params.window,
        horizon=params.horizon,
        config_id=config_id,
    )

    if torch is not None and device is not None:
        non_blocking = device.type == "cuda"
        tensor_X = torch.from_numpy(X).to(device, non_blocking=non_blocking)
        tensor_A = torch.from_numpy(A).to(device, non_blocking=non_blocking)
        tensor_P = torch.from_numpy(P).to(device, non_blocking=non_blocking)
        tensor_Y = torch.from_numpy(Y).to(device, non_blocking=non_blocking)

        if amp_enabled and device.type == "cuda":
            tensor_X = tensor_X.half()
            tensor_A = tensor_A.half()
            tensor_P = tensor_P.half()

        X = tensor_X.float().cpu().numpy()
        A = tensor_A.float().cpu().numpy()
        P = tensor_P.float().cpu().numpy()
        Y = tensor_Y.cpu().numpy().astype(np.int64, copy=False)

        empty_cache()

    dataset_path = TRAINING_ROOT / f"{slug}_dataset.npz"
    np.savez(dataset_path, X=X, A=A, P=P, Y=Y)

    return {
        "path": str(dataset_path),
        "samples": int(X.shape[0]),
        "window": params.window,
        "horizon": params.horizon,
    }


def _resolve_config_id(config_id: Optional[int], config_name: str) -> int:
    if sync_engine is None:
        raise RuntimeError("Synchronous database engine is not configured; cannot access the database.")

    with SyncSession(sync_engine) as session:
        stmt = (
            select(SupplyChainConfig.id).where(SupplyChainConfig.id == config_id)
            if config_id is not None
            else select(SupplyChainConfig.id).where(SupplyChainConfig.name == config_name)
        )
        result = session.execute(stmt).scalar()
        if result is None:
            identifier = f"id={config_id}" if config_id is not None else f"name='{config_name}'"
            raise RuntimeError(f"Supply chain configuration not found ({identifier}).")
        return int(result)


def _latest_dataset_path(config_id: int, slug: str) -> Optional[Path]:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = TRAINING_ROOT / f"{slug}_dataset.npz"
    if candidate.exists():
        return candidate
    matches = sorted(TRAINING_ROOT.glob(f"dataset_cfg{config_id}_*.npz"))
    return matches[-1] if matches else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-id", type=int, default=None, help="Target supply chain configuration ID.")
    parser.add_argument(
        "--config-name",
        default=DEFAULT_CONFIG_NAME,
        help="Supply chain configuration name to use when an explicit ID is not provided.",
    )
    parser.add_argument("--window", type=int, default=52, help="Input window length.")
    parser.add_argument("--horizon", type=int, default=1, help="Prediction horizon for training labels.")
    parser.add_argument(
        "--steps-table",
        default="simulation_steps",
        help="DB table name that holds scenario step records.",
    )
    parser.add_argument("--force", action="store_true", help="Regenerate even if a dataset already exists.")
    parser.add_argument(
        "--device",
        default=None,
        help="Preferred torch device to stage dataset tensors on (e.g. 'cuda', 'cpu').",
    )
    parser.add_argument(
        "--no-amp",
        dest="amp",
        action="store_false",
        help="Disable mixed precision processing when staging tensors on GPU.",
    )
    parser.add_argument(
        "--amp",
        dest="amp",
        action="store_true",
        help="Enable mixed precision processing when tensors are staged on GPU.",
    )
    parser.set_defaults(amp=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_id = _resolve_config_id(args.config_id, args.config_name)

    with SyncSession(sync_engine) as session:
        config_obj = session.get(SupplyChainConfig, config_id)
        if not config_obj:
            raise RuntimeError(f"Supply chain configuration not found (id={config_id}).")
        slug = _slugify(config_obj.name)

    preferred_device = None
    if torch is not None:
        preferred_device = get_available_device(args.device)
        logger.info("Staging dataset tensors on device: %s", preferred_device)
        if preferred_device.type == "cuda":
            logger.info(
                "CUDA device: %s (capabilities %s)",
                torch.cuda.get_device_name(preferred_device),
                torch.cuda.get_device_capability(preferred_device),
            )
    elif args.device and str(args.device).lower() not in ("", "cpu"):
        logger.warning(
            "PyTorch is not available; device hint '%s' ignored.",
            args.device,
        )

    latest_dataset = _latest_dataset_path(config_id, slug)
    if latest_dataset and not args.force:
        logger.info(
            "Existing dataset found for config %s at %s; skipping generation.",
            config_id,
            latest_dataset,
        )
        output = {"status": "skipped", "path": str(latest_dataset), "config_id": config_id}
        print(json.dumps(output))
        return

    amp_enabled = bool(
        args.amp
        and torch is not None
        and preferred_device is not None
        and preferred_device.type == "cuda"
    )

    params = TrainingParams(
        window=int(args.window),
        horizon=int(args.horizon),
        steps_table=args.steps_table,
    )

    with device_scope(preferred_device or "cpu"):
        dataset_info = _generate_training_dataset(
            config_id,
            slug,
            params,
            device=preferred_device if torch is not None else None,
            amp_enabled=amp_enabled,
        )

    dataset_info.update({"status": "created", "config_id": config_id})

    logger.info(
        "Generated dataset for config %s with %s samples at %s",
        config_id,
        dataset_info.get("samples"),
        dataset_info.get("path"),
    )

    metadata_path = TRAINING_ROOT / f"{slug}_latest_dataset.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(dataset_info, fp, indent=2)

    output = {
        "status": dataset_info["status"],
        "config_id": config_id,
        "path": dataset_info.get("path"),
        "samples": dataset_info.get("samples"),
        "window": dataset_info.get("window"),
        "horizon": dataset_info.get("horizon"),
        "metadata_path": str(metadata_path),
    }
    print(json.dumps(output))

    if preferred_device is not None and preferred_device.type == "cuda":
        empty_cache()


if __name__ == "__main__":
    main()

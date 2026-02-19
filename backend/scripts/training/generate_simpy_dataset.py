#!/usr/bin/env python3
"""Generate Autonomy training data using the SimPy backend for the default configuration."""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from app.rl.data_generator import (
    SimulationParams,
    SimDemand,
    generate_sim_training_windows,
    simulate_supply_chain,
)
from app.services.agents import AgentStrategy
from app.db.session import sync_engine
from app.models.supply_chain_config import SupplyChainConfig
from app.utils.device import device_scope, empty_cache, get_available_device

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_CONFIG_NAME = "Case Beer Game"


@dataclass
class TrainingParams:
    num_runs: int
    timesteps: int
    window: int
    horizon: int
    sim_alpha: float
    sim_wip_k: float
    use_simpy: bool = True
    agent_strategy: str = AgentStrategy.NAIVE.value


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower()).strip("-")
    return slug or "config"


PID_IMPROVEMENT_THRESHOLD = 0.10
PID_TUNING_SAMPLE_LIMIT = 256
PID_RANDOM_SEARCH_SAMPLES = 16
PID_MODE_PRECISION = 2


def _compute_trace_cost(trace: Dict[str, Dict[str, List[int]]], params: SimulationParams) -> float:
    holding_cost = float(getattr(params, "holding_cost", 1.0))
    backlog_cost = float(getattr(params, "backlog_cost", 1.0))
    total = 0.0
    for role_data in trace.values():
        inventory = np.asarray(role_data.get("inventory", []), dtype=np.float32)
        backlog = np.asarray(role_data.get("backlog", []), dtype=np.float32)
        total += float(np.sum(inventory * holding_cost + backlog * backlog_cost))
    return total


def _evaluate_strategy_cost(
    run_params: Sequence[SimulationParams],
    training_params: TrainingParams,
    strategy: AgentStrategy,
    *,
    pid_params: Optional[Dict[str, Any]] = None,
    sample_size: int = PID_TUNING_SAMPLE_LIMIT,
) -> float:
    if not run_params:
        return float("inf")

    limit = max(1, min(len(run_params), sample_size))
    subset = list(run_params)[:limit]
    total_cost = 0.0
    for cfg in subset:
        trace = simulate_supply_chain(
            T=training_params.timesteps,
            params=cfg,
            demand_fn=SimDemand(),
            agent_strategy=strategy,
            pid_params=pid_params if strategy == AgentStrategy.PID else None,
        )
        total_cost += _compute_trace_cost(trace, cfg)
    return total_cost / limit


def _tune_pid_hyperparameters(
    run_params: Sequence[SimulationParams],
    training_params: TrainingParams,
) -> Dict[str, Any]:
    sample_size = min(len(run_params), PID_TUNING_SAMPLE_LIMIT)
    if sample_size == 0:
        return {"status": "skipped", "reason": "no_runs"}

    logger.info("Starting PID hyperparameter tuning on %s simulation runs", sample_size)
    rng = np.random.default_rng(1234)
    per_run_best: List[Dict[str, float]] = []

    for idx, params in enumerate(list(run_params)[:sample_size], start=1):
        candidate_best: Optional[Dict[str, float]] = None
        candidate_cost = float("inf")
        for _ in range(PID_RANDOM_SEARCH_SAMPLES):
            candidate = {
                "alpha": float(rng.uniform(0.2, 2.0)),
                "beta": float(rng.uniform(0.1, 1.2)),
                "gamma": float(rng.uniform(0.0, 0.2)),
                "delta": float(rng.uniform(0.0, 0.2)),
                "target_multiplier": float(rng.uniform(1.0, 3.5)),
            }
            cost = _evaluate_strategy_cost(
                [params],
                training_params,
                AgentStrategy.PID,
                pid_params=candidate,
                sample_size=1,
            )
            if cost < candidate_cost:
                candidate_cost = cost
                candidate_best = candidate
        if candidate_best:
            per_run_best.append(candidate_best)
        logger.debug(
            "PID tuning sample %s/%s best cost %.2f with params %s",
            idx,
            sample_size,
            candidate_cost,
            candidate_best,
        )

    if not per_run_best:
        return {"status": "skipped", "reason": "no_candidates"}

    def _consensus(key: str) -> float:
        values = [best[key] for best in per_run_best]
        rounded = [round(val, PID_MODE_PRECISION) for val in values]
        frequency: Dict[float, int] = {}
        for val in rounded:
            frequency[val] = frequency.get(val, 0) + 1
        top = max(frequency.values())
        top_vals = [val for val, count in frequency.items() if count == top]
        return float(sum(top_vals) / len(top_vals))

    best_params = {
        "alpha": _consensus("alpha"),
        "beta": _consensus("beta"),
        "gamma": _consensus("gamma"),
        "delta": _consensus("delta"),
        "target_multiplier": _consensus("target_multiplier"),
    }

    baseline_cost = _evaluate_strategy_cost(
        run_params,
        training_params,
        AgentStrategy.NAIVE,
        sample_size=sample_size,
    )
    best_cost = _evaluate_strategy_cost(
        run_params,
        training_params,
        AgentStrategy.PID,
        pid_params=best_params,
        sample_size=sample_size,
    )

    improvement = 0.0
    if baseline_cost > 0 and np.isfinite(baseline_cost) and np.isfinite(best_cost):
        improvement = 1.0 - (best_cost / baseline_cost)

    logger.info(
        "Consensus PID cost: %.2f (improvement %.2f%%) using params %s",
        best_cost,
        improvement * 100.0,
        best_params,
    )

    return {
        "status": "ok",
        "sample_size": sample_size,
        "baseline_cost": baseline_cost,
        "best_cost": best_cost,
        "improvement": improvement,
        "best_params": best_params,
    }


def _generate_training_dataset(
    config_id: int,
    slug: str,
    params: TrainingParams,
    *,
    device: Optional["torch.device"] = None,
    amp_enabled: bool = False,
    collect_run_params: bool = False,
    dataset_suffix: Optional[str] = None,
    pid_params: Optional[Dict[str, Any]] = None,
    reuse_run_params: Optional[Sequence[SimulationParams]] = None,
) -> Tuple[Dict[str, Any], Optional[List[SimulationParams]]]:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)

    suffix_token = f"_{dataset_suffix}" if dataset_suffix else ""

    result = generate_sim_training_windows(
        num_runs=params.num_runs,
        T=params.timesteps,
        window=params.window,
        horizon=params.horizon,
        supply_chain_config_id=config_id,
        db_url=settings.SQLALCHEMY_DATABASE_URI or None,
        use_simpy=params.use_simpy,
        sim_alpha=params.sim_alpha,
        sim_wip_k=params.sim_wip_k,
        agent_strategy=params.agent_strategy,
        pid_params=pid_params,
        return_run_params=collect_run_params,
        run_params=reuse_run_params,
    )

    if collect_run_params:
        X, A, P, Y, run_params = result
    else:
        X, A, P, Y = result
        run_params = None

    if torch is not None and device is not None:
        non_blocking = device.type == "cuda"
        tensor_X = torch.from_numpy(X).to(device, non_blocking=non_blocking)
        tensor_A = torch.from_numpy(A).to(device, non_blocking=non_blocking)
        tensor_P = torch.from_numpy(P).to(device, non_blocking=non_blocking)
        tensor_Y = torch.from_numpy(Y).to(device, non_blocking=non_blocking)

        if amp_enabled and device.type == "cuda":
            # Keep intermediate buffers lightweight when GPU is available
            tensor_X = tensor_X.half()
            tensor_A = tensor_A.half()
            tensor_P = tensor_P.half()

        # Persist back to CPU for npz storage
        X = tensor_X.float().cpu().numpy()
        A = tensor_A.float().cpu().numpy()
        P = tensor_P.float().cpu().numpy()
        Y = tensor_Y.cpu().numpy().astype(np.int64, copy=False)

        empty_cache()

    dataset_path = TRAINING_ROOT / f"{slug}{suffix_token}_dataset.npz"
    np.savez(dataset_path, X=X, A=A, P=P, Y=Y)

    info = {
        "path": str(dataset_path),
        "samples": int(X.shape[0]),
        "window": params.window,
        "horizon": params.horizon,
        "agent_strategy": params.agent_strategy,
    }

    return info, run_params


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
    parser.add_argument("--num-runs", type=int, default=2500, help="Number of simulated runs.")
    parser.add_argument("--timesteps", type=int, default=64, help="Number of periods per simulation run.")
    parser.add_argument("--window", type=int, default=52, help="Input window length.")
    parser.add_argument("--horizon", type=int, default=1, help="Prediction horizon for training labels.")
    parser.add_argument("--sim-alpha", type=float, default=0.3, help="SimPy smoothing factor.")
    parser.add_argument("--sim-wip-k", type=float, default=1.0, help="SimPy WIP gain parameter.")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a dataset already exists.")
    parser.add_argument(
        "--agent-strategy",
        default=AgentStrategy.NAIVE.value,
        help="Agent strategy token to use for synthetic gameplay (e.g. pid_heuristic, naive, llm).",
    )
    parser.add_argument(
        "--disable-simpy",
        action="store_true",
        help="Force the discrete agent-driven simulator instead of the SimPy backend.",
    )
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
        device_name = str(preferred_device)
        logger.info("Staging dataset tensors on device: %s", device_name)
        if preferred_device.type == "cuda":
            logger.info(
                "CUDA device detected: %s (capabilities %s)",
                torch.cuda.get_device_name(preferred_device),
                torch.cuda.get_device_capability(preferred_device),
            )
    elif args.device and str(args.device).lower() not in ("", "cpu"):
        logger.warning(
            "PyTorch is not available in this environment; device hint '%s' will be ignored.",
            args.device,
        )

    latest_dataset = _latest_dataset_path(config_id, slug)
    if latest_dataset and not args.force:
        logger.info(
            "Existing dataset found for config %s at %s; skipping generation.",
            config_id,
            latest_dataset,
        )
        output = {
            "status": "skipped",
            "path": str(latest_dataset),
            "config_id": config_id,
        }
        print(json.dumps(output))
        return

    amp_enabled = bool(args.amp and torch is not None and preferred_device is not None and preferred_device.type == "cuda")
    if amp_enabled:
        logger.info("Mixed precision enabled for dataset staging.")

    agent_token = str(args.agent_strategy or AgentStrategy.NAIVE.value).strip().lower()
    try:
        strategy_enum = AgentStrategy(agent_token)
    except ValueError as exc:
        raise ValueError(f"Unsupported agent strategy: {args.agent_strategy}") from exc

    params = TrainingParams(
        num_runs=int(args.num_runs),
        timesteps=int(args.timesteps),
        window=int(args.window),
        horizon=int(args.horizon),
        sim_alpha=float(args.sim_alpha),
        sim_wip_k=float(args.sim_wip_k),
        use_simpy=not bool(args.disable_simpy),
        agent_strategy=strategy_enum.value,
    )

    base_dataset_info: Dict[str, Any]
    pid_dataset_info: Optional[Dict[str, Any]] = None
    run_params: Optional[List[SimulationParams]] = None
    tuning_summary: Optional[Dict[str, Any]] = None

    with device_scope(preferred_device or "cpu"):
        base_dataset_info, run_params = _generate_training_dataset(
            config_id,
            slug,
            params,
            device=preferred_device if torch is not None else None,
            amp_enabled=amp_enabled,
            collect_run_params=strategy_enum == AgentStrategy.NAIVE,
        )

        if strategy_enum == AgentStrategy.NAIVE and run_params:
            tuning_summary = _tune_pid_hyperparameters(run_params, params)
            best_params = tuning_summary.get("best_params") if isinstance(tuning_summary, dict) else None
            improvement = float(tuning_summary.get("improvement", 0.0)) if isinstance(tuning_summary, dict) else 0.0
            pid_dataset_details: Optional[Dict[str, Any]] = None
            if best_params:
                pid_params = dict(best_params)
                pid_training_params = TrainingParams(
                    num_runs=params.num_runs,
                    timesteps=params.timesteps,
                    window=params.window,
                    horizon=params.horizon,
                    sim_alpha=params.sim_alpha,
                    sim_wip_k=params.sim_wip_k,
                    use_simpy=params.use_simpy,
                    agent_strategy=AgentStrategy.PID.value,
                )
                pid_dataset_details, _ = _generate_training_dataset(
                    config_id,
                    slug,
                    pid_training_params,
                    device=preferred_device if torch is not None else None,
                    amp_enabled=amp_enabled,
                    dataset_suffix="pid",
                    pid_params=pid_params,
                    reuse_run_params=run_params,
                )
                if pid_dataset_details is not None:
                    pid_dataset_details["pid_params"] = pid_params
                pid_dataset_info = pid_dataset_details
                if improvement >= PID_IMPROVEMENT_THRESHOLD:
                    logger.info(
                        "PID dataset generated with improvement %.2f%%",
                        improvement * 100.0,
                    )
                else:
                    logger.info(
                        "PID improvement %.2f%% below threshold %.2f%%; dataset generated with tuned parameters regardless.",
                        improvement * 100.0,
                        PID_IMPROVEMENT_THRESHOLD * 100.0,
                    )
            else:
                tuning_summary = None

    base_dataset_info.update({
        "status": "created",
        "config_id": config_id,
    })

    best_dataset_path = base_dataset_info.get("path")
    if pid_dataset_info:
        pid_dataset_info.update({
            "status": "created",
            "config_id": config_id,
        })
        best_dataset_path = pid_dataset_info.get("path", best_dataset_path)

    logger.info(
        "Generated base dataset for config %s with %s samples at %s",
        config_id,
        base_dataset_info.get("samples"),
        base_dataset_info.get("path"),
    )

    metadata = {
        "config_id": config_id,
        "slug": slug,
        "naive_dataset": base_dataset_info.get("path"),
        "pid_dataset": pid_dataset_info.get("path") if pid_dataset_info else None,
        "best_dataset": best_dataset_path,
        "pid_tuning": tuning_summary,
        "threshold": PID_IMPROVEMENT_THRESHOLD,
    }
    metadata_path = TRAINING_ROOT / f"{slug}_latest_dataset.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2)

    output = {
        "status": base_dataset_info["status"],
        "config_id": config_id,
        "path": base_dataset_info.get("path"),
        "samples": base_dataset_info.get("samples"),
        "window": base_dataset_info.get("window"),
        "horizon": base_dataset_info.get("horizon"),
        "agent_strategy": base_dataset_info.get("agent_strategy"),
        "best_dataset": best_dataset_path,
        "metadata_path": str(metadata_path),
        "pid_tuning": tuning_summary,
    }
    if pid_dataset_info:
        output["pid_dataset"] = pid_dataset_info

    logger.info("Dataset metadata written to %s", metadata_path)
    print(json.dumps(output))

    if preferred_device is not None and preferred_device.type == "cuda":
        empty_cache()


if __name__ == "__main__":
    main()

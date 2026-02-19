"""Factory helpers for creating Beer Game order policies."""

from __future__ import annotations

from typing import Any, Dict

from .policies import NaiveEchoPolicy, OrderPolicy, PIDPolicy


def make_policy(kind: str, params: Dict[str, Any] | None = None) -> OrderPolicy:
    """Instantiate an :class:`OrderPolicy` from a configuration mapping."""

    params = params or {}
    key = (kind or "").strip().lower()

    if key in {"naive", "echo", "naive_echo"}:
        return NaiveEchoPolicy()

    if key in {"pi", "pi_controller", "pid", "pid_controller", "pid_heuristic"}:
        return PIDPolicy(
            base_stock=int(params.get("base_stock", 20)),
            kp=float(params.get("kp", 0.6)),
            ki=float(params.get("ki", 0.1)),
            kd=float(params.get("kd", 0.05)),
            clamp_min=int(params.get("clamp_min", 0)),
            clamp_max=(
                None
                if params.get("clamp_max") is None
                else int(params.get("clamp_max"))
            ),
        )

    raise ValueError(f"Unknown policy kind: {kind}")

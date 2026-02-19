"""Lightweight helper for interacting with the Autonomy Simulation Strategist."""

from __future__ import annotations

from threading import Lock
from typing import Any, Dict, Optional

from .autonomy_client import AutonomyStrategistSession, get_session, resolve_model


_SESSION: Optional[AutonomyStrategistSession] = None
_SESSION_LOCK = Lock()


def _resolve_model(preferred: Optional[str] = None) -> str:
    return resolve_model(preferred)


def _bool_from_env(name: str, default: bool) -> bool:
    from os import getenv

    token = getenv(name)
    if token is None:
        return default
    return token.strip().lower() in {"1", "true", "yes", "on"}


def _get_session(
    model: Optional[str] = None,
    *,
    custom_gpt: Optional[str] = None,
    supervisor: Optional[bool] = None,
    global_agent: Optional[bool] = None,
    strategy: str = "balanced",
) -> AutonomyStrategistSession:
    """Return a singleton session for the supplied model."""

    global _SESSION
    resolved = _resolve_model(model)

    supervisor_enabled = supervisor if supervisor is not None else _bool_from_env("AUTONOMY_ENABLE_SUPERVISOR", True)
    global_enabled = global_agent if global_agent is not None else _bool_from_env("AUTONOMY_ENABLE_GLOBAL_AGENT", False)
    custom = custom_gpt
    if custom is None:
        from os import getenv

        custom = getenv("AUTONOMY_CUSTOM_GPT") or getenv("AUTONOMY_CUSTOM_GPT")

    with _SESSION_LOCK:
        if (
            _SESSION is None
            or _SESSION.model != resolved
            or _SESSION.custom_gpt != custom
            or _SESSION.supervisor_enabled != supervisor_enabled
            or _SESSION.global_enabled != global_enabled
            or _SESSION.strategy != strategy
        ):
            _SESSION = get_session(
                model=resolved,
                strategy=strategy,
                supervisor=supervisor_enabled,
                global_agent=global_enabled,
                custom_gpt=custom,
            )
        return _SESSION


def call_simulation_gpt(
    state: Dict[str, Any],
    *,
    model: Optional[str] = None,
    reset_thread: bool = False,
    custom_gpt: Optional[str] = None,
    supervisor: Optional[bool] = None,
    global_agent: Optional[bool] = None,
    strategy: str = "balanced",
) -> Dict[str, Any]:
    """Submit a single simulation state snapshot and return the assistant decision."""

    if not isinstance(state, dict):
        raise TypeError(
            "call_simulation_gpt expects a state dictionary matching the strategist schema"
        )

    session = _get_session(
        model,
        custom_gpt=custom_gpt,
        supervisor=supervisor,
        global_agent=global_agent,
        strategy=strategy,
    )
    if reset_thread:
        session.reset()
    return session.decide(state)


def get_last_decision() -> Optional[Dict[str, Any]]:
    """Expose the most recent assistant response for debugging or telemetry."""

    if _SESSION is None:
        return None
    return _SESSION.last_decision


__all__ = ["call_simulation_gpt", "get_last_decision", "AutonomyStrategistSession", "get_session", "resolve_model"]

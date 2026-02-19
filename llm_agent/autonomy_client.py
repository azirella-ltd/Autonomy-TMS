"""Session management for the simulation OpenAI agent hierarchy."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from openai import OpenAI

from .simulation_openai_agents import SimulationAgentsOrchestrator, resolve_model


_CLIENT: Optional[OpenAI] = None
_CLIENT_LOCK = Lock()

_SESSION_CACHE: Dict[str, "AutonomyStrategistSession"] = {}
_SESSION_CACHE_LOCK = Lock()


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set")

            client_kwargs: Dict[str, Any] = {"api_key": api_key}

            project = os.getenv("OPENAI_PROJECT")
            if project:
                client_kwargs["project"] = project

            organization = os.getenv("OPENAI_ORGANIZATION") or os.getenv("OPENAI_ORG")
            if organization:
                client_kwargs["organization"] = organization

            timeout_token = os.getenv("AUTONOMY_LLM_TIMEOUT")
            if timeout_token:
                try:
                    timeout_value = float(timeout_token)
                except ValueError:
                    timeout_value = None
            else:
                timeout_value = None
            if not timeout_value or timeout_value <= 0:
                timeout_value = 15.0
            client_kwargs["timeout"] = timeout_value

            retries_token = os.getenv("AUTONOMY_LLM_MAX_RETRIES")
            if retries_token:
                try:
                    retries_value = int(retries_token)
                except ValueError:
                    retries_value = None
            else:
                retries_value = None
            if retries_value is None or retries_value < 0:
                retries_value = 1
            client_kwargs["max_retries"] = retries_value

            _CLIENT = OpenAI(**client_kwargs)
        return _CLIENT


def _session_cache_key(
    model: Optional[str],
    *,
    strategy: str,
    supervisor: bool,
    global_agent: bool,
    custom_gpt: Optional[str],
) -> str:
    resolved = resolve_model(model, custom_gpt=custom_gpt)
    return json.dumps(
        {
            "model": resolved,
            "strategy": strategy,
            "supervisor": supervisor,
            "global": global_agent,
            "custom": custom_gpt,
        },
        sort_keys=True,
    )


@dataclass
class AutonomyStrategistSession:
    """Stateful orchestrator facade used by the backend."""

    model: str
    strategy: str = "balanced"
    supervisor_enabled: bool = True
    global_enabled: bool = False
    custom_gpt: Optional[str] = None
    _client: Optional[OpenAI] = None
    _orchestrator: Optional[SimulationAgentsOrchestrator] = None
    _last_decision: Optional[Dict[str, Any]] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = _get_client()
        return self._client

    @property
    def orchestrator(self) -> SimulationAgentsOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = SimulationAgentsOrchestrator(
                client=self.client,
                model=self.model,
                node_style=self.strategy,
                enable_supervisor=self.supervisor_enabled,
                enable_global=self.global_enabled,
                custom_gpt=self.custom_gpt,
            )
        return self._orchestrator

    def reset(self) -> None:
        self._last_decision = None
        if self._orchestrator is not None:
            self._orchestrator.reset()

    def decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            raise TypeError("State must be a dictionary containing the strategist payload")

        node_id = str(state.get("node_key") or state.get("role") or "retailer").lower()
        period = int(state.get("week") or state.get("period") or 0)

        decision_bundle = self.orchestrator.decide(
            node_id=node_id,
            period=period,
            observation=state,
        )

        action = decision_bundle.get("action", {})
        order_qty = int(action.get("order_qty", 0))
        ship_qty = int(action.get("ship_qty", order_qty))
        rationale = str(action.get("rationale", "")).strip() or "No rationale provided"

        enriched = {
            **decision_bundle,
            "order_upstream": order_qty,
            "ship_to_downstream": ship_qty,
            "rationale": rationale,
        }

        self._last_decision = enriched
        return enriched

    @property
    def last_decision(self) -> Optional[Dict[str, Any]]:
        return self._last_decision


def get_session(
    model: Optional[str] = None,
    *,
    strategy: str = "balanced",
    supervisor: bool = True,
    global_agent: bool = False,
    custom_gpt: Optional[str] = None,
) -> AutonomyStrategistSession:
    key = _session_cache_key(
        model,
        strategy=strategy,
        supervisor=supervisor,
        global_agent=global_agent,
        custom_gpt=custom_gpt,
    )
    with _SESSION_CACHE_LOCK:
        session = _SESSION_CACHE.get(key)
        if session is None:
            resolved_model = resolve_model(model, custom_gpt=custom_gpt)
            session = AutonomyStrategistSession(
                model=resolved_model,
                strategy=strategy,
                supervisor_enabled=supervisor,
                global_enabled=global_agent,
                custom_gpt=custom_gpt,
            )
            _SESSION_CACHE[key] = session
        return session


__all__ = ["AutonomyStrategistSession", "get_session", "resolve_model"]


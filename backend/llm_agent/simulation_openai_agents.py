"""OpenAI Agent scaffolding for the simulation multi-agent hierarchy.

This module exposes light-weight wrappers around the OpenAI Responses API that
mirror the hierarchy described in the product brief: node level agents submit
actions, a supervisor agent can amend them, and an optional global agent emits
network-wide targets.  The helpers focus on two goals:

* Enforce the structured JSON contracts expected by the backend.
* Provide a deterministic place to plug Python tool functions that the agents
  can call through OpenAI's tool-calling interface.

The implementation intentionally avoids any simulation-specific business logic so
that the same infrastructure can power unit tests with simple stubs or production
runs backed by the real simulator/optimisation helpers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Optional

from openai import OpenAI


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON schemas used for structured outputs
# ---------------------------------------------------------------------------

NODE_ACTION_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["node_id", "period", "action"],
    "properties": {
        "node_id": {"type": "string", "minLength": 1},
        "period": {"type": "integer", "minimum": 0},
        "action": {
            "type": "object",
            "additionalProperties": False,
            "required": ["order_qty", "ship_qty", "rationale", "notes"],
            "properties": {
                "order_qty": {"type": "integer", "minimum": 0},
                "ship_qty": {"type": "integer", "minimum": 0},
                "rationale": {"type": "string", "minLength": 1},
                "notes": {"type": "string"},
            },
        },
    },
}

SUPERVISOR_PATCH_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["node_id", "period", "patch"],
    "properties": {
        "node_id": {"type": "string", "minLength": 1},
        "period": {"type": "integer", "minimum": 0},
        "patch": {
            "type": "object",
            "additionalProperties": False,
            "required": ["order_qty", "reason", "enforced"],
            "properties": {
                "order_qty": {"type": "integer", "minimum": 0},
                "reason": {"type": "string"},
                "enforced": {"type": "boolean"},
            },
        },
    },
}

GLOBAL_TARGET_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["effective_period", "targets"],
    "properties": {
        "effective_period": {"type": "integer", "minimum": 0},
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["node_id"],
                "properties": {
                    "node_id": {"type": "string", "minLength": 1},
                    "base_stock": {"type": "number"},
                    "order_smoothing": {"type": "number", "minimum": 0, "maximum": 1},
                    "sl_target": {"type": "number", "minimum": 0, "maximum": 1},
                    "variance_cap": {"type": "number", "minimum": 0},
                },
            },
        },
        "notes": {"type": "string"},
    },
}


# ---------------------------------------------------------------------------
# Tool registration helpers
# ---------------------------------------------------------------------------


def _default_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return json.dumps(str(value))


@dataclass
class ToolDefinition:
    """Describes a Python callable exposed to the agent runtime as a tool."""

    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable[..., Any]


@dataclass
class ToolRegistry:
    """Maintains the mapping between tool names and callables."""

    tools: MutableMapping[str, ToolDefinition] = field(default_factory=dict)

    def register(self, definition: ToolDefinition) -> None:
        if not isinstance(definition, ToolDefinition):
            raise TypeError("Tool definition must be an instance of ToolDefinition")
        if definition.name in self.tools:
            raise ValueError(f"Tool '{definition.name}' already registered")
        self.tools[definition.name] = definition

    def as_openai_tools(self) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for definition in self.tools.values():
            payload.append(
                {
                    "type": "function",
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                }
            )
        return payload

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self.tools:
            raise KeyError(f"Unknown tool '{name}'")
        function = self.tools[name].function
        return function(**arguments)


# ---------------------------------------------------------------------------
# Base class wrapping the Responses API
# ---------------------------------------------------------------------------


class OpenAIResponsesAgent:
    """Tiny wrapper around ``client.responses.create`` supporting tool loops."""

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        instructions: str,
        response_schema: Dict[str, Any],
        response_name: str,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self._client = client
        self._model = model
        self._instructions = instructions
        self._schema = response_schema
        self._schema_name = response_name
        self._tools = tool_registry or ToolRegistry()

    # -- public API -----------------------------------------------------
    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent with ``payload`` as the user message."""

        message = self._format_payload(payload)
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": message,
                }
            ],
        }

        conversation: List[Dict[str, Any]] = [user_message]

        json_schema_payload = {
            "name": self._schema_name,
            "schema": self._schema,
            "strict": True,
        }
        schema_format = {
            "type": "json_schema",
            "json_schema": json_schema_payload,
        }
        text_format = {
            "type": "json_schema",
            "name": self._schema_name,
            "schema": self._schema,
            "strict": True,
        }

        while True:
            request_kwargs = {
                "model": self._model,
                "instructions": self._instructions,
                "input": conversation,
                "tools": self._tools.as_openai_tools() or None,
            }
            try:
                response = self._client.responses.create(
                    **request_kwargs,
                    response_format=schema_format,
                )
            except TypeError as exc:
                if "response_format" not in str(exc):
                    raise
                response = self._client.responses.create(
                    **request_kwargs,
                    text={"format": text_format},
                )

            tool_calls = _collect_tool_calls(response)
            if tool_calls:
                for call in tool_calls:
                    arguments = _safe_parse_json(call.arguments or "{}")
                    result = self._tools.invoke(call.name, arguments)
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": _default_json_dumps(result),
                                }
                            ],
                        }
                    )
                continue

            text_output = _extract_response_text(response)
            return _safe_parse_json(text_output)

    # -- helpers --------------------------------------------------------
    def _format_payload(self, payload: Dict[str, Any]) -> str:
        packed = json.dumps(payload, indent=2, sort_keys=True, default=str)
        return (
            "You are receiving structured state for the simulation. "
            "Use the schema-locked response format.\n\n"
            f"State JSON:\n```json\n{packed}\n```"
        )


# ---------------------------------------------------------------------------
# Concrete agent wrappers
# ---------------------------------------------------------------------------


NODE_AGENT_INSTRUCTIONS = """\
You operate a single simulation node (Retailer, Wholesaler, Distributor, or Factory).
Decide how many units to order from your upstream partner this period. Always emit
valid JSON matching the provided schema. Incorporate backlog, on-hand, pipeline,
incoming orders, lead times, and any global targets. If the Supervisor has sent
temporary policies or variance caps, respect them. Describe your reasoning in the
"rationale" field so humans can audit the decision.
"""


SUPERVISOR_INSTRUCTIONS = """\
You are the Simulation Supervisor. Review node proposals for compliance with
network policies. Clamp extreme swings, respect capacity/budget/service caps,
and enforce any targets from the Global Planner. If no adjustment is needed you
may return an empty patch object. When you override, explain the reasoning in
plain language.
"""


GLOBAL_INSTRUCTIONS = """\
You orchestrate the simulation network. Analyse the shared state/history to set
rolling targets such as base-stock levels, order variance caps, and service-level
goals. Output only the JSON schema. Provide targets for nodes that need guidance
and leave others absent. Use notes to document major trade-offs.
"""


class SimulationNodeAgent(OpenAIResponsesAgent):
    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        instructions: str = NODE_AGENT_INSTRUCTIONS,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        super().__init__(
            client=client,
            model=model,
            instructions=instructions,
            response_schema=NODE_ACTION_SCHEMA,
            response_name="simulation_node_action",
            tool_registry=tool_registry,
        )


class SimulationSupervisorAgent(OpenAIResponsesAgent):
    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        instructions: str = SUPERVISOR_INSTRUCTIONS,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        super().__init__(
            client=client,
            model=model,
            instructions=instructions,
            response_schema=SUPERVISOR_PATCH_SCHEMA,
            response_name="simulation_supervisor_patch",
            tool_registry=tool_registry,
        )


class SimulationGlobalAgent(OpenAIResponsesAgent):
    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        instructions: str = GLOBAL_INSTRUCTIONS,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        super().__init__(
            client=client,
            model=model,
            instructions=instructions,
            response_schema=GLOBAL_TARGET_SCHEMA,
            response_name="simulation_global_targets",
            tool_registry=tool_registry,
        )


# ---------------------------------------------------------------------------
# Orchestrator tying the tiers together
# ---------------------------------------------------------------------------


def resolve_model(preferred: Optional[str] = None, *, custom_gpt: Optional[str] = None) -> str:
    """Resolve a model identifier, preferring an explicit Custom GPT when present."""

    from os import getenv

    if custom_gpt:
        return custom_gpt

    env_custom = getenv("AUTONOMY_CUSTOM_GPT") or getenv("SIMULATION_CUSTOM_GPT")
    if env_custom:
        return env_custom

    if preferred:
        return preferred

    return (
        getenv("LLM_MODEL_NAME")  # Local vLLM/Ollama served model name
        or getenv("AUTONOMY_LLM_MODEL")
        or getenv("OPENAI_MODEL")
        or "gpt-4.1-mini"
    )


class SimulationAgentsOrchestrator:
    """Coordinates node, supervisor, and global agents for a simulation node."""

    def __init__(
        self,
        *,
        client: OpenAI,
        model: Optional[str] = None,
        node_style: str = "balanced",
        enable_supervisor: bool = True,
        enable_global: bool = False,
        tool_registry: Optional[ToolRegistry] = None,
        custom_gpt: Optional[str] = None,
    ) -> None:
        resolved_model = resolve_model(model, custom_gpt=custom_gpt)
        self._client = client
        self._model = resolved_model
        self._node_style = node_style
        self._tool_registry = tool_registry or ToolRegistry()
        self._enable_supervisor = enable_supervisor
        self._enable_global = enable_global

        self._node_agents: Dict[str, SimulationNodeAgent] = {}
        self._supervisor_agent: Optional[SimulationSupervisorAgent] = (
            SimulationSupervisorAgent(client=client, model=resolved_model, tool_registry=self._tool_registry)
            if enable_supervisor
            else None
        )
        self._global_agent: Optional[SimulationGlobalAgent] = (
            SimulationGlobalAgent(client=client, model=resolved_model, tool_registry=self._tool_registry)
            if enable_global
            else None
        )

        self._active_targets: List[Dict[str, Any]] = []
        self._history: List[Dict[str, Any]] = []

    # -- lifecycle ------------------------------------------------------
    def reset(self) -> None:
        self._active_targets.clear()
        self._history.clear()

    # -- decisions ------------------------------------------------------
    def decide(
        self,
        *,
        node_id: str,
        period: int,
        observation: Dict[str, Any],
        history: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Return a structured decision bundle for the supplied node."""

        if not node_id:
            raise ValueError("node_id must be provided")

        self._history.append({"node_id": node_id, "period": period, "observation": observation})
        if history:
            self._history.extend(history)

        if self._global_agent is not None:
            global_payload = {
                "effective_period": max(period + 1, 0),
                "latest_observation": observation,
                "history": self._history[-24:],
                "active_targets": self._active_targets,
                "style": self._node_style,
            }
            try:
                global_output = self._global_agent.invoke(global_payload)
                if isinstance(global_output, dict) and global_output.get("targets"):
                    self._active_targets = list(global_output.get("targets", []))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Global agent failed: %s", exc)

        node_agent = self._ensure_node_agent(node_id)
        node_payload = {
            "node_id": node_id,
            "period": period,
            "observation": observation,
            "active_targets": self._active_targets,
            "style": self._node_style,
        }
        node_output = node_agent.invoke(node_payload)

        final_qty = _coerce_int(node_output.get("action", {}).get("order_qty"))
        ship_qty = node_output.get("action", {}).get("ship_qty")
        rationale = str(node_output.get("action", {}).get("rationale") or "").strip()
        notes = node_output.get("action", {}).get("notes")

        supervisor_output: Optional[Dict[str, Any]] = None
        if self._supervisor_agent is not None:
            supervisor_payload = {
                "node_id": node_id,
                "period": period,
                "proposal": node_output,
                "active_targets": self._active_targets,
                "observation": observation,
            }
            try:
                supervisor_output = self._supervisor_agent.invoke(supervisor_payload)
                patch = (supervisor_output or {}).get("patch", {})
                if patch and patch.get("order_qty") is not None:
                    final_qty = _coerce_int(patch.get("order_qty"))
                    reason = str(patch.get("reason") or "").strip()
                    if reason:
                        rationale = f"{rationale} | Supervisor: {reason}" if rationale else f"Supervisor: {reason}"
                if patch and patch.get("reason") and notes:
                    rationale = f"{rationale} | Notes: {notes}" if rationale else f"Notes: {notes}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supervisor agent failed: %s", exc)

        decision_bundle = {
            "node_id": node_id,
            "period": period,
            "action": {
                "order_qty": max(0, final_qty),
                "ship_qty": _coerce_int(ship_qty) if ship_qty is not None else max(0, final_qty),
                "rationale": rationale or "No rationale provided",
                "notes": notes,
            },
            "proposal": node_output,
            "supervisor_patch": supervisor_output,
            "global_targets": self._active_targets,
        }

        return decision_bundle

    # -- helpers --------------------------------------------------------
    def _ensure_node_agent(self, node_id: str) -> SimulationNodeAgent:
        if node_id not in self._node_agents:
            instructions = NODE_AGENT_INSTRUCTIONS
            if self._node_style and self._node_style != "balanced":
                instructions = (
                    f"Strategy: {self._node_style}. Follow the style when balancing risk/costs.\n\n"
                    f"{NODE_AGENT_INSTRUCTIONS}"
                )
            self._node_agents[node_id] = SimulationNodeAgent(
                client=self._client,
                model=self._model,
                instructions=instructions,
                tool_registry=self._tool_registry,
            )
        return self._node_agents[node_id]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent response is not valid JSON: {text}") from exc


def _collect_tool_calls(response: Any) -> List[Any]:
    calls: List[Any] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "tool_call":
            calls.append(item)
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "tool_call":
                calls.append(content)
    return calls


def _extract_response_text(response: Any) -> str:
    if getattr(response, "output_text", None):
        return response.output_text

    chunks: List[str] = []
    for item in getattr(response, "output", []) or []:
        contents = getattr(item, "content", []) or []
        for content in contents:
            if getattr(content, "type", None) in {"text", "output_text"}:
                value = getattr(getattr(content, "text", None), "value", None)
                if value is None and hasattr(content, "text") and isinstance(content.text, str):
                    value = content.text
                if value:
                    chunks.append(value)
    if not chunks:
        raise RuntimeError("Agent response did not contain text output")
    return "\n".join(chunks)


__all__ = [
    "SimulationAgentsOrchestrator",
    "SimulationNodeAgent",
    "SimulationSupervisorAgent",
    "SimulationGlobalAgent",
    "ToolRegistry",
    "ToolDefinition",
    "NODE_ACTION_SCHEMA",
    "SUPERVISOR_PATCH_SCHEMA",
    "GLOBAL_TARGET_SCHEMA",
    "resolve_model",
]

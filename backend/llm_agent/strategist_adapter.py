"""OpenAI Strategist adapter for the simulation engine."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI
from pydantic import BaseModel, Field

DEFAULT_BASE_URL = os.getenv("SIMULATION_API_BASE_URL", "http://localhost:8000")
LOG = logging.getLogger(__name__)


class SimulationClient:
    """Simple REST client for the simulation backend."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.openapi: Optional[Dict[str, Any]] = self._load_openapi()

    def _load_openapi(self) -> Optional[Dict[str, Any]]:
        try:
            resp = requests.get(f"{self.base_url}/openapi.json", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def run_simulation(self, **kwargs) -> Dict[str, Any]:
        path = "/api/sim/run"
        return self._post(path, kwargs)

    def get_kpis(self, **kwargs) -> Dict[str, Any]:
        path = "/api/kpis"
        return self._get(path, kwargs)


class RunSimulationRequest(BaseModel):
    demand: List[int] = Field(..., description="Demand series")
    lead_time: int = Field(..., description="Lead time in weeks")
    initial_inventory: int = Field(..., description="Starting inventory")


class GetKpisRequest(BaseModel):
    window: int = Field(4, description="Rolling window in weeks")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_simulation",
            "description": "Run a simulation and return the state history.",
            "parameters": RunSimulationRequest.schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpis",
            "description": "Compute KPIs over the last N rounds.",
            "parameters": GetKpisRequest.schema(),
        },
    },
]

INSTRUCTIONS = (
    "You are the Simulation Strategist. Use the provided tools to simulate supply chain "
    "scenarios and report key metrics."
)


def make_openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _handle_tool_calls(
    client: OpenAI,
    response_id: str,
    tool_calls: List[Dict[str, Any]],
    sim_api: SimulationClient,
) -> str:
    outputs = []
    for call in tool_calls:
        name = call.get("name")
        args = json.loads(call.get("arguments", "{}"))
        if name == "run_simulation":
            result = sim_api.run_simulation(**args)
        elif name == "get_kpis":
            result = sim_api.get_kpis(**args)
        else:
            result = {"error": f"unknown tool {name}"}
        outputs.append({"tool_call_id": call.get("id"), "output": json.dumps(result)})

    followup = client.responses.submit_tool_outputs(
        response_id=response_id, tool_outputs=outputs
    )
    return getattr(followup, "output_text", str(followup))


def strategist_query(
    user_input: str,
    *,
    model: str = "gpt-5-mini",
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    sim_api = SimulationClient(base_url=base_url)
    ai = make_openai_client()

    resp = ai.responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=user_input,
        tools=TOOLS,
    )

    tool_calls: List[Dict[str, Any]] = []
    for block in getattr(resp, "output", []) or []:
        if getattr(block, "type", None) == "tool_call":
            tool_calls.append(
                {
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "arguments": getattr(block, "arguments", None),
                }
            )

    if tool_calls:
        return _handle_tool_calls(ai, resp.id, tool_calls, sim_api)

    return getattr(resp, "output_text", str(resp))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    base = os.getenv("SIMULATION_API_BASE_URL", DEFAULT_BASE_URL)
    LOG.info("Using backend: %s", base)
    client = SimulationClient(base_url=base)
    if client.openapi:
        LOG.info("OpenAPI titles: %s", client.openapi.get("info", {}).get("title"))
    else:
        LOG.warning("OpenAPI missing; using default paths")

    try:
        answer = strategist_query(
            "Demand ~40±15 weekly, lead 2w, initial inv 100. Propose low‑WIP policy and A/B sim plan.",
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            base_url=base,
        )
        print("\n=== Strategist Answer ===\n", answer)
    except Exception as exc:
        LOG.error("Strategist run failed: %s", exc)

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _OpenAIStub:
    def __init__(self, *args, **kwargs):  # pragma: no cover - safety guard
        raise AssertionError("OpenAI client should be patched in tests")


sys.modules.setdefault("openai", SimpleNamespace(OpenAI=_OpenAIStub))

from llm_agent import autonomy_client


class DummyOrchestrator:
    def __init__(self, *args, **kwargs):
        self.decide_calls = []
        self.reset_calls = 0

    def decide(self, **kwargs):
        self.decide_calls.append(kwargs)
        site_id = kwargs.get("site_id", "retailer")
        period = kwargs.get("period", 0)
        return {
            "site_id": site_id,
            "period": period,
            "action": {
                "order_qty": 6,
                "ship_qty": 4,
                "rationale": "Stub orchestrator decision",
            },
            "proposal": {"action": {"order_qty": 6}},
            "supervisor_patch": None,
            "global_targets": [],
        }

    def reset(self):
        self.reset_calls += 1


def _minimal_state() -> dict:
    return {
        "role": "retailer",
        "week": 1,
        "toggles": {
            "customer_demand_history_sharing": False,
            "volatility_signal_sharing": False,
            "downstream_inventory_visibility": False,
        },
        "parameters": {
            "holding_cost": 0.5,
            "backlog_cost": 0.5,
            "L_order": 2,
            "L_ship": 2,
            "L_prod": 4,
        },
        "local_state": {
            "on_hand": 12,
            "backlog": 0,
            "incoming_orders_this_week": 4,
            "received_shipment_this_week": 0,
            "pipeline_orders_upstream": [0, 0],
            "pipeline_shipments_inbound": [0, 0],
            "optional": {},
        },
    }


def test_autonomy_session_decide_delegates_to_orchestrator(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(autonomy_client, "_CLIENT", SimpleNamespace())
    monkeypatch.setattr(autonomy_client, "_SESSION_CACHE", {})
    dummy_orchestrator = DummyOrchestrator()
    monkeypatch.setattr(
        autonomy_client,
        "SimulationAgentsOrchestrator",
        lambda **kwargs: dummy_orchestrator,
    )

    session = autonomy_client.AutonomyStrategistSession(model="gpt-test")
    state = _minimal_state()

    result_one = session.decide(state)
    assert result_one["order_upstream"] == 6
    assert result_one["ship_to_downstream"] == 4
    assert "rationale" in result_one
    assert dummy_orchestrator.decide_calls

    result_two = session.decide(state)
    assert len(dummy_orchestrator.decide_calls) == 2
    assert result_two["order_upstream"] == 6


def test_autonomy_session_reset_clears_orchestrator(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(autonomy_client, "_CLIENT", SimpleNamespace())
    monkeypatch.setattr(autonomy_client, "_SESSION_CACHE", {})
    dummy_orchestrator = DummyOrchestrator()
    monkeypatch.setattr(
        autonomy_client,
        "SimulationAgentsOrchestrator",
        lambda **kwargs: dummy_orchestrator,
    )

    session = autonomy_client.AutonomyStrategistSession(model="gpt-reset")
    state = _minimal_state()

    session.decide(state)
    session.reset()
    assert dummy_orchestrator.reset_calls == 1

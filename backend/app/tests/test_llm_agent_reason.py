import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def test_llm_agent_records_rationale(monkeypatch):
    """LLM agent should surface the strategist rationale in its explanation."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=SimpleNamespace))

    from app.services import llm_agent as llm_module

    class DummySession:
        def __init__(self, model: str):
            self.model = model
            self.decide_calls = []

        def decide(self, state):
            self.decide_calls.append(state)
            return {
                "site_id": state.get("role", "retailer"),
                "period": state.get("week", 0),
                "action": {
                    "order_qty": 9,
                    "ship_qty": 4,
                    "rationale": "Maintain a two-week buffer while clearing backlog.",
                },
                "order_upstream": 9,
                "ship_to_downstream": 4,
                "rationale": "Maintain a two-week buffer while clearing backlog.",
            }

        def reset(self):
            self.decide_calls.clear()

    monkeypatch.setattr(
        llm_module,
        "get_session",
        lambda *args, **kwargs: DummySession(kwargs.get("model") or args[0]),
    )

    agent = llm_module.LLMAgent(role="retailer", model="stub-model")

    order = agent.make_decision(
        current_period=1,
        current_inventory=10,
        backorders=2,
        incoming_shipments=[2, 2],
        demand_history=[8, 9],
        order_history=[8, 8],
        current_demand=8,
        upstream_data={"llm_payload": {"stub": True}},
    )

    assert order == 9
    assert agent.last_explanation is not None
    assert "Maintain a two-week buffer" in agent.last_explanation
    assert agent.last_decision and agent.last_decision.get("order_upstream") == 9
    assert agent.last_supervisor_patch is None or isinstance(agent.last_supervisor_patch, dict)


def test_llm_agent_truncates_lengthy_rationale(monkeypatch):
    """Extremely long rationales should be truncated to the configured limit."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=SimpleNamespace))

    from app.services import llm_agent as llm_module

    class DummySession:
        def __init__(self, model: str):
            self.model = model

        def decide(self, state):
            return {
                "site_id": state.get("role", "retailer"),
                "period": state.get("week", 0),
                "action": {
                    "order_qty": 5,
                    "ship_qty": 3,
                    "rationale": "R" * (llm_module.MAX_RATIONALE_CHARS * 2),
                },
                "order_upstream": 5,
                "ship_to_downstream": 3,
                "rationale": "R" * (llm_module.MAX_RATIONALE_CHARS * 2),
            }

        def reset(self):
            pass

    monkeypatch.setattr(
        llm_module,
        "get_session",
        lambda *args, **kwargs: DummySession(kwargs.get("model") or args[0]),
    )

    agent = llm_module.LLMAgent(role="retailer", model="stub-model")

    agent.make_decision(
        current_period=1,
        current_inventory=10,
        backorders=2,
        incoming_shipments=[2, 2],
        demand_history=[8, 9],
        order_history=[8, 8],
        current_demand=8,
        upstream_data={"llm_payload": {"stub": True}},
    )

    assert agent.last_explanation is not None
    assert len(agent.last_explanation) <= llm_module.MAX_RATIONALE_CHARS
    assert agent.last_explanation.endswith("…")
    assert agent.last_decision["rationale"].startswith("R")


def test_llm_agent_handles_empty_payload(monkeypatch):
    """A structurally empty dict should still be treated as a provided payload."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=SimpleNamespace))

    from app.services import llm_agent as llm_module

    class DummySession:
        def __init__(self, model: str):
            self.model = model
            self.decide_calls = []

        def decide(self, state):
            self.decide_calls.append(state)
            return {
                "site_id": state.get("role", "retailer"),
                "period": state.get("week", 0),
                "action": {
                    "order_qty": 7,
                    "ship_qty": 5,
                    "rationale": "Maintain flow despite sparse telemetry.",
                },
                "order_upstream": 7,
                "ship_to_downstream": 5,
                "rationale": "Maintain flow despite sparse telemetry.",
            }

        def reset(self):
            self.decide_calls.clear()

    monkeypatch.setattr(
        llm_module,
        "get_session",
        lambda *args, **kwargs: DummySession(kwargs.get("model") or args[0]),
    )

    agent = llm_module.LLMAgent(role="retailer", model="stub-model")

    order = agent.make_decision(
        current_period=1,
        current_inventory=10,
        backorders=2,
        incoming_shipments=[2, 2],
        demand_history=[8, 9],
        order_history=[8, 8],
        current_demand=8,
        upstream_data={"llm_payload": {}},
    )

    assert order == 7
    assert agent.last_decision and agent.last_decision.get("order_upstream") == 7
    assert agent.last_explanation and "Maintain flow" in agent.last_explanation


def test_llm_agent_errors_when_payload_missing(monkeypatch):
    """Missing payload should raise a descriptive AutonomyLLMError."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=SimpleNamespace))

    from app.services import llm_agent as llm_module

    class DummySession:
        def __init__(self, model: str):
            self.model = model

        def decide(self, state):  # pragma: no cover - shouldn't be hit
            raise AssertionError("Decide should not be called without payload")

        def reset(self):
            pass

    monkeypatch.setattr(
        llm_module,
        "get_session",
        lambda *args, **kwargs: DummySession(kwargs.get("model") or args[0]),
    )

    agent = llm_module.LLMAgent(role="retailer", model="stub-model")

    with pytest.raises(llm_module.AutonomyLLMError) as excinfo:
        agent.make_decision(
            current_period=1,
            current_inventory=10,
            backorders=2,
            incoming_shipments=[2, 2],
            demand_history=[8, 9],
            order_history=[8, 8],
            current_demand=8,
            upstream_data={"other": "context"},
        )

    message = str(excinfo.value)
    assert "payload missing" in message
    assert "llm_agent.LLMAgent.make_decision" in message
    assert agent.last_decision is None
    assert agent.last_explanation == message


def test_llm_agent_surfaces_strategist_errors(monkeypatch):
    """Errors surfaced by the strategist should raise AutonomyLLMError."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=SimpleNamespace))

    from app.services import llm_agent as llm_module

    class FailingSession:
        def __init__(self, model: str):
            self.model = model

        def decide(self, state):
            raise RuntimeError("boom")

        def reset(self):
            pass

    monkeypatch.setattr(
        llm_module,
        "get_session",
        lambda *args, **kwargs: FailingSession(kwargs.get("model") or args[0]),
    )

    agent = llm_module.LLMAgent(role="retailer", model="stub-model")

    with pytest.raises(llm_module.AutonomyLLMError) as excinfo:
        agent.make_decision(
            current_period=1,
            current_inventory=10,
            backorders=2,
            incoming_shipments=[2, 2],
            demand_history=[8, 9],
            order_history=[8, 8],
            current_demand=8,
            upstream_data={"llm_payload": {"stub": True}},
        )

    message = str(excinfo.value)
    assert "call failed" in message
    assert "boom" in message
    assert agent.last_decision is None
    assert agent.last_explanation == message

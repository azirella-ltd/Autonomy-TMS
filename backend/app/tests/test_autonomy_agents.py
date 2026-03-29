import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.agents import (
    AgentStrategy,
    AgentType,
    SimulationAgent,
    AutonomyCoordinator,
    AutonomyGlobalController,
)


@pytest.fixture
def base_local_state():
    return {
        "inventory": 18,
        "backlog": 3,
        "incoming_shipments": [4, 4],
        "node_label": "Retailer",
        "node_key": "retailer",
    }


@pytest.fixture
def base_upstream_data():
    return {
        "previous_orders": [6, 7, 8],
        "previous_orders_by_role": {"retailer": 7, "wholesaler": 8},
    }


def _assert_reason(decision):
    assert isinstance(decision.reason, str)
    assert decision.reason.strip(), "expected a non-empty explanation"
    assert decision.reason.startswith("["), "expected label prefix in explanation"


def test_autonomy_dtce_agent_returns_reason(base_local_state, base_upstream_data):
    agent = SimulationAgent(
        agent_id=1,
        agent_type=AgentType.RETAILER,
        strategy=AgentStrategy.AUTONOMY_DTCE,
        central_coordinator=AutonomyCoordinator(),
        global_controller=AutonomyGlobalController(),
    )

    decision = agent.make_decision(
        current_period=3,
        current_demand=9,
        upstream_data=base_upstream_data,
        local_state=base_local_state,
    )

    assert decision.quantity >= 0
    _assert_reason(decision)


def test_autonomy_dtce_central_agent_returns_reason(base_local_state, base_upstream_data):
    coordinator = AutonomyCoordinator(default_override=0.1)
    agent = SimulationAgent(
        agent_id=2,
        agent_type=AgentType.WHOLESALER,
        strategy=AgentStrategy.AUTONOMY_DTCE_CENTRAL,
        central_coordinator=coordinator,
        global_controller=AutonomyGlobalController(),
    )

    decision = agent.make_decision(
        current_period=5,
        current_demand=None,
        upstream_data=base_upstream_data,
        local_state={**base_local_state, "node_label": "Wholesaler", "node_key": "wholesaler"},
    )

    assert decision.quantity >= 0
    _assert_reason(decision)


def test_autonomy_dtce_global_agent_returns_reason(base_local_state, base_upstream_data):
    coordinator = AutonomyCoordinator(default_override=0.1)
    controller = AutonomyGlobalController()
    agent = SimulationAgent(
        agent_id=3,
        agent_type=AgentType.DISTRIBUTOR,
        strategy=AgentStrategy.AUTONOMY_DTCE_GLOBAL,
        central_coordinator=coordinator,
        global_controller=controller,
    )

    decision = agent.make_decision(
        current_period=7,
        current_demand=None,
        upstream_data=base_upstream_data,
        local_state={**base_local_state, "node_label": "Distributor", "node_key": "distributor"},
    )

    assert decision.quantity >= 0
    _assert_reason(decision)


class _StubLLMAgent:
    def __init__(self, order: int = 6, message: str = "Stub rationale"):
        self._order = order
        self._message = message
        self.last_explanation = message

    def make_decision(self, **kwargs):  # type: ignore[no-untyped-def]
        self.last_explanation = self._message
        return self._order


def test_llm_supervised_agent_generates_adjusted_order(base_local_state, base_upstream_data):
    coordinator = AutonomyCoordinator(default_override=0.1)
    controller = AutonomyGlobalController()
    agent = SimulationAgent(
        agent_id=4,
        agent_type=AgentType.WHOLESALER,
        strategy=AgentStrategy.LLM_SUPERVISED,
        central_coordinator=coordinator,
        global_controller=controller,
    )
    agent._llm_agent = _StubLLMAgent(order=8, message="LLM stub explanation")

    decision = agent.make_decision(
        current_period=4,
        current_demand=10,
        upstream_data=base_upstream_data,
        local_state={**base_local_state, "node_label": "Wholesaler", "node_key": "wholesaler"},
    )

    assert decision.quantity >= 0
    assert isinstance(decision.reason, str)
    assert decision.reason.strip()


def test_llm_global_agent_coordinated_plan(base_local_state, base_upstream_data):
    coordinator = AutonomyCoordinator(default_override=0.1)
    controller = AutonomyGlobalController()
    agent = SimulationAgent(
        agent_id=5,
        agent_type=AgentType.MANUFACTURER,
        strategy=AgentStrategy.LLM_GLOBAL,
        central_coordinator=coordinator,
        global_controller=controller,
    )
    agent._llm_agent = _StubLLMAgent(order=9, message="LLM orchestrator explanation")

    decision = agent.make_decision(
        current_period=6,
        current_demand=12,
        upstream_data=base_upstream_data,
        local_state={**base_local_state, "node_label": "Manufacturer", "node_key": "manufacturer"},
    )

    assert decision.quantity >= 0
    assert isinstance(decision.reason, str)
    assert decision.reason.strip()

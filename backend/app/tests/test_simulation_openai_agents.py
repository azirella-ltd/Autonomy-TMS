import sys
from types import SimpleNamespace

if "openai" not in sys.modules:
    sys.modules["openai"] = SimpleNamespace(OpenAI=SimpleNamespace)

from llm_agent.simulation_openai_agents import SimulationNodeAgent


class _DummyResponse:
    def __init__(self):
        payload = '{"site_id":"retailer","period":0,"action":{"order_qty":1,"rationale":"ok"}}'
        self.output = [
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text=SimpleNamespace(value=payload),
                    )
                ]
            )
        ]


def test_openai_agent_prefers_response_format():
    class StubClient:
        def __init__(self):
            self.responses = SimpleNamespace()

    agent = SimulationNodeAgent(client=StubClient(), model="stub-model")
    create_calls = []

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        if "response_format" in kwargs:
            raise TypeError("response_format unsupported")
        return _DummyResponse()

    agent._client.responses.create = fake_create  # type: ignore[attr-defined]
    result = agent.invoke({"site_id": "retailer", "period": 0, "state": {}})
    assert result["site_id"] == "retailer"
    assert create_calls
    assert "response_format" in create_calls[0]

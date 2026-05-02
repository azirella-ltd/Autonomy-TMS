"""Tests for TMS's A2A Agent Card (§3.32 Phase 4)."""
from __future__ import annotations

import pytest


class TestAgentCard:
    def test_card_construction(self):
        from app.a2a import build_agent_card
        card = build_agent_card()
        assert card.name == "autonomy-tms"
        assert card.version == "0.1.0"

    def test_card_lists_three_skills(self):
        from app.a2a import build_agent_card
        card = build_agent_card()
        skill_ids = {s.id for s in card.skills}
        assert "transport.load.evaluate_consolidation" in skill_ids
        assert "transport.carrier.recommend" in skill_ids
        assert "transport.lane.estimate_eta" in skill_ids
        assert len(card.skills) == 3

    def test_skill_id_convention(self):
        from app.a2a import build_agent_card
        card = build_agent_card()
        for s in card.skills:
            assert "." in s.id
            assert len(s.id.split(".")) >= 3


class TestSkillHandlers:
    def test_handler_keys_match_card_skills(self):
        from app.a2a import build_agent_card, get_skill_handlers
        card = build_agent_card()
        handlers = get_skill_handlers()
        assert set(handlers.keys()) == {s.id for s in card.skills}

    def test_all_handlers_async(self):
        import inspect
        from app.a2a import get_skill_handlers
        for skill_id, handler in get_skill_handlers().items():
            assert (
                inspect.iscoroutinefunction(handler)
                or inspect.isasyncgenfunction(handler)
            ), f"skill {skill_id!r} handler must be async"


@pytest.mark.asyncio
class TestInputValidation:
    async def test_consolidation_requires_inputs(self):
        from app.a2a.skills import evaluate_consolidation_skill
        from azirella_a2a_client import Task, TaskState, SkillContext

        ctx = SkillContext(
            skill_id="transport.load.evaluate_consolidation",
            input={"shipment_ids": ["s1", "s2"]},  # missing config_id
            tenant_id=None,
            task=Task(task_id="t1", skill_id="transport.load.evaluate_consolidation", state=TaskState.WORKING),
        )
        with pytest.raises(ValueError, match="config_id"):
            await evaluate_consolidation_skill(ctx)

    async def test_consolidation_requires_non_empty_shipments(self):
        from app.a2a.skills import evaluate_consolidation_skill
        from azirella_a2a_client import Task, TaskState, SkillContext

        ctx = SkillContext(
            skill_id="transport.load.evaluate_consolidation",
            input={"config_id": 1, "shipment_ids": []},
            tenant_id=None,
            task=Task(task_id="t1", skill_id="transport.load.evaluate_consolidation", state=TaskState.WORKING),
        )
        with pytest.raises(ValueError, match="shipment_ids"):
            await evaluate_consolidation_skill(ctx)

    async def test_recommend_carrier_requires_inputs(self):
        from app.a2a.skills import recommend_carrier_skill
        from azirella_a2a_client import Task, TaskState, SkillContext

        ctx = SkillContext(
            skill_id="transport.carrier.recommend",
            input={"config_id": 1},  # missing load_id
            tenant_id=None,
            task=Task(task_id="t1", skill_id="transport.carrier.recommend", state=TaskState.WORKING),
        )
        with pytest.raises(ValueError, match="load_id"):
            await recommend_carrier_skill(ctx)

    async def test_estimate_lane_eta_requires_inputs(self):
        from app.a2a.skills import estimate_lane_eta_skill
        from azirella_a2a_client import Task, TaskState, SkillContext

        ctx = SkillContext(
            skill_id="transport.lane.estimate_eta",
            input={"from_site_id": "A"},  # missing to_site_id, departure_at
            tenant_id=None,
            task=Task(task_id="t1", skill_id="transport.lane.estimate_eta", state=TaskState.WORKING),
        )
        with pytest.raises(ValueError, match="to_site_id|departure_at"):
            await estimate_lane_eta_skill(ctx)


class TestMountIntegration:
    def test_well_known_endpoint_returns_card(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.a2a import mount

        app = FastAPI()
        mount(app)

        with TestClient(app) as client:
            resp = client.get("/.well-known/agent.json")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "autonomy-tms"
            assert any(
                s["id"] == "transport.load.evaluate_consolidation"
                for s in data["skills"]
            )

from collections import defaultdict
from types import SimpleNamespace

import pytest

pytest.importorskip("pydantic")

from app.services import mixed_game_service
from app.services.mixed_game_service import MixedGameService
from app.schemas.simulation import RoundContext, NodeState, TopologyConfig, LaneConfig


def _make_service() -> MixedGameService:
    service = MixedGameService.__new__(MixedGameService)
    service.db = None
    service.agent_manager = None
    service._game_columns_cache = None
    return service


def test_calculate_demand_lognormal_uses_generator(monkeypatch):
    service = _make_service()
    game = SimpleNamespace(demand_pattern={"type": "lognormal", "params": {"mean": 8.0, "cov": 0.25}})

    captured = {}

    def fake_generate(num_rounds: int, **kwargs):
        captured["num_rounds"] = num_rounds
        captured["kwargs"] = kwargs
        return [5]

    monkeypatch.setattr(
        mixed_game_service.DemandGenerator,
        "generate_lognormal",
        staticmethod(fake_generate),
    )

    value = MixedGameService.calculate_demand(service, game, 1)

    assert value == 5
    assert captured["num_rounds"] == 1
    assert captured["kwargs"]["mean"] == pytest.approx(8.0)


def test_calculate_demand_backfills_from_config(monkeypatch):
    service = _make_service()
    pattern = {"type": "lognormal", "params": {"mean": 6.0, "cov": 0.4}}
    game = SimpleNamespace(demand_pattern=None, config={"demand_pattern": pattern})

    def fake_generate(num_rounds: int, **kwargs):
        assert num_rounds == 1
        assert kwargs["mean"] == pytest.approx(6.0)
        return [13]

    monkeypatch.setattr(
        mixed_game_service.DemandGenerator,
        "generate_lognormal",
        staticmethod(fake_generate),
    )

    value = MixedGameService.calculate_demand(service, game, 1)

    assert value == 13
    assert getattr(game, "demand_pattern")["type"] == "lognormal"


def test_calculate_demand_uses_market_demand_fallback(monkeypatch):
    service = _make_service()
    pattern = {"type": "lognormal", "params": {"mean": 10.0, "cov": 0.3}}
    game = SimpleNamespace(demand_pattern=None, config={"market_demands": [{"demand_pattern": pattern}]})

    def fake_generate(num_rounds: int, **kwargs):
        assert kwargs["mean"] == pytest.approx(10.0)
        return [7]

    monkeypatch.setattr(
        mixed_game_service.DemandGenerator,
        "generate_lognormal",
        staticmethod(fake_generate),
    )

    assert MixedGameService.calculate_demand(service, game, 1) == 7


def test_compute_initial_conditions_reflects_lead_times():
    result = MixedGameService._compute_initial_conditions(
        mean_demand=8.0,
        variance=4.0,
        order_leadtime=2,
        supply_leadtime=3,
    )

    assert result["steady_quantity"] == 8
    # Cycle stock should cover supply lead time (3 periods) plus safety stock
    assert result["initial_inventory"] >= 24
    assert result["on_order"] == 16
    assert result["base_stock"] >= result["initial_inventory"]


def test_apply_market_demand_respects_lane_lead_time():
    service = _make_service()
    lane = LaneConfig(**{"from": "retailer", "to": "customer", "demand_lead_time": 1})
    topology = TopologyConfig(
        lanes=[lane],
        shipments_map={"retailer": ["customer"]},
        orders_map={"customer": ["retailer"]},
        market_nodes=["customer"],
        all_nodes=["retailer", "customer"],
        node_sequence=["customer", "retailer"],
        lanes_by_upstream={"retailer": [lane]},
        node_types={"retailer": "retailer", "customer": "customer"},
        lane_lookup={("retailer", "customer"): lane},
    )
    context = RoundContext(
        round_number=1,
        scenario_id=42,
        topology=topology,
        node_states={
            "retailer": NodeState(),
            "customer": NodeState(),
        },
        node_policies={"retailer": {"order_leadtime": 1}},
        market_demand_map={"customer": {"Case": 4}},
    )
    demand_inputs = defaultdict(int)
    demand_item_inputs = defaultdict(lambda: defaultdict(int))

    service._apply_market_demand(context, demand_inputs, demand_item_inputs)

    supplier_orders = context.node_states["retailer"].inbound_demand
    assert len(supplier_orders) == 1
    assert supplier_orders[0].due_round == 2  # current_period (1) + lane lead (1)
    assert supplier_orders[0].quantity == 4

    market_orders = context.node_states["customer"].backlog_orders
    assert len(market_orders) == 1
    assert market_orders[0].due_round == 2
    assert market_orders[0].quantity == 4

    assert demand_inputs["customer"] == 4

from types import SimpleNamespace

import pytest

from app.services.mixed_scenario_service import MixedScenarioService as MixedGameService


def test_build_market_item_profiles_produces_item_baselines():
    cfg = {
        "market_demands": [
            {
                "market_name": "North Region",
                "item_id": "widget",
                "demand_pattern": {
                    "type": "constant",
                    "params": {"value": 12},
                },
            },
            {
                "market_name": "North Region",
                "item_id": "widget",
                "demand_pattern": {
                    "type": "constant",
                    "params": {"value": 4},
                },
            },
            {
                "market_name": "South Region",
                "item_id": "gadget",
                "demand_pattern": {
                    "type": "constant",
                    "params": {"value": 6},
                },
            },
        ]
    }

    profiles = MixedGameService._build_market_item_profiles(cfg)

    assert profiles == {
        "north_region": {"widget": 16},
        "south_region": {"gadget": 6},
    }


def test_propagate_item_profiles_follows_order_hierarchy_without_loops():
    orders_map = {
        "market_demand": ["retailer"],
        "retailer": ["wholesaler"],
        "wholesaler": ["manufacturer"],
    }
    profiles = {
        "market_demand": {
            "widget": 10,
            "gadget": 4,
        }
    }

    propagated = MixedGameService._propagate_item_profiles(orders_map, profiles)

    for node in ("market_demand", "retailer", "wholesaler", "manufacturer"):
        assert propagated[node]["widget"] == 10
        assert propagated[node]["gadget"] == 4


def test_propagate_item_profiles_handles_cycles_gracefully():
    orders_map = {
        "a": ["b"],
        "b": ["a"],
    }
    profiles = {
        "a": {"item": 5},
    }

    propagated = MixedGameService._propagate_item_profiles(orders_map, profiles)

    assert propagated["a"]["item"] == 5
    assert propagated["b"]["item"] == 5


def test_build_lane_views_normalises_leadtime_payloads():
    node_policies = {
        "retailer": {"order_leadtime": 0, "supply_leadtime": 1},
        "wholesaler": {"order_leadtime": 1, "supply_leadtime": 2},
    }
    cfg = {
        "node_types": {"retailer": "retailer", "wholesaler": "wholesaler", "factory": "market_supply"},
        "market_demand_nodes": ["Customer"],
        "nodes": [
            {"name": "Customer", "type": "market_demand", "master_type": "market_demand"},
        ],
        "lanes": [
            {
                "from": "factory",
                "to": "wholesaler",
                "demand_lead_time": 1,
                "supply_lead_time": 1,
            },
            {
                "from": "wholesaler",
                "to": "retailer",
                "demand_lead_time": {"type": "deterministic", "value": 4},
                "supply_lead_time": {"type": "deterministic", "value": 6},
            },
        ],
    }

    views = MixedGameService._build_lane_views(node_policies, cfg)
    lane_lookup = views["lane_lookup"]
    record = lane_lookup[("wholesaler", "retailer")]

    # Normalised lead times are kept under demand_lead_time/supply_lead_time
    assert record["demand_lead_time"] == 4
    assert record["supply_lead_time"] == 6

    resolved_order = MixedGameService._resolve_lane_order_delay(
        lane_lookup, "wholesaler", "retailer", default_delay=2
    )
    resolved_ship = MixedGameService._resolve_lane_ship_delay(
        lane_lookup, "wholesaler", "retailer", default_delay=3
    )

    assert resolved_order == 4
    assert resolved_ship == 6


def test_seed_order_queue_includes_detail_breakdown():
    state = {}

    MixedGameService._seed_order_queue(
        state,
        current_step=2,
        order_leadtime=3,
        quantity=10,
        detail_breakdown={"alpha": 6, "beta": 3, "gamma": 1},
        default_downstream="__self__",
        product_id="widget",
    )

    queue = state["inbound_demand"]
    assert len(queue) == 1
    entry = queue[0]
    assert entry["step_number"] == 3
    assert entry["quantity"] == 10
    assert entry["order_priority"] == 1
    assert entry["downstream"] == "__self__"
    assert entry["product_id"] == "widget"
    assert "breakdown" not in entry


def test_initialise_order_pipeline_scales_detail_breakdown():
    state = {}

    MixedGameService._initialise_order_pipeline(
        state,
        order_leadtime=3,
        default_quantity=9,
        detail_breakdown={"north": 5, "south": 2},
    )

    # Legacy info queues are removed; only incoming_orders is tracked.
    assert "info_queue" not in state
    assert "info_detail_queue" not in state
    assert "inbound_demand" not in state
    assert state["incoming_orders"] == 0


@pytest.mark.parametrize(
    "market_entry,expected_total",
    [
        (
            {
                "market_name": "Region A",
                "item_id": 1,
                "demand_pattern": {"type": "constant", "params": {"value": 7}},
            },
            7,
        ),
        (
            {
                "market_name": "Region B",
                "item_id": "sku-42",
                "demand_pattern": {"type": "classic", "params": {"initial_demand": 5}},
            },
            5,
        ),
    ],
)
def test_compute_market_round_demand_updates_market_entries(market_entry, expected_total):
    cfg = {"market_demands": [market_entry]}
    game = SimpleNamespace(demand_pattern=None)

    demand_map, total = MixedGameService._compute_market_round_demand(game, cfg, round_number=3)

    market_key = MixedGameService._normalise_key(market_entry["market_name"])
    assert demand_map == {market_key: {str(market_entry["item_id"]): expected_total}}
    assert total == expected_total

    updated_entry = cfg["market_demands"][0]
    assert updated_entry["demand_pattern"]["type"] == market_entry["demand_pattern"]["type"]
    assert isinstance(updated_entry["demand_pattern"]["params"], dict)


def test_compute_market_round_demand_falls_back_to_global_pattern():
    cfg = {
        "market_demands": [
            {
                "market_name": "market_demand",
                "item_id": "default",
                "demand_pattern": {"type": "constant", "params": {"value": 11}},
            }
        ]
    }
    game = SimpleNamespace(
        demand_pattern={"type": "constant", "params": {"value": 11}},
    )

    demand_map, total = MixedGameService._compute_market_round_demand(game, cfg, round_number=2)

    assert demand_map == {"market_demand": {"default": 11}}
    assert total == 11
    assert cfg["market_demands"][0]["demand_pattern"]["type"] == "constant"
    assert cfg["market_demands"][0]["demand_pattern"]["params"]["value"] == 11


def test_fallback_game_config_uses_supply_chain_id_without_snapshot():
    captured = {}

    class FakeSupplyChainService:
        def __init__(self, db):
            captured["db"] = db

        def create_game_from_config(self, config_id, payload):
            captured["config_id"] = config_id
            captured["payload"] = payload
            return {
                "node_policies": {"assembly": {"order_leadtime": 2}},
                "lanes": [{"source": "assembly", "target": "market"}],
            }

    cfg = {"supply_chain_config_id": "77"}
    game = SimpleNamespace(name="Custom", description="", max_rounds=12, is_public=False)
    mgs = MixedGameService(SimpleNamespace())

    fallback = mgs._fallback_game_config_from_supply_chain(
        cfg,
        game,
        snapshot=None,
        sc_service_factory=lambda db: FakeSupplyChainService(db),
    )

    assert captured.get("config_id") == 77
    assert captured.get("payload", {}).get("max_rounds") == 12
    assert fallback and fallback.get("lanes") == [{"source": "assembly", "target": "market"}]


def test_record_startup_notice_adds_message_and_logs(monkeypatch):
    captured = {}

    def fake_append(cfg, game, message, details=None, exc=None):  # noqa: ARG001
        captured["message"] = message
        captured["details"] = details

    def fake_ensure(cfg, game):  # noqa: ARG001
        captured["ensure_called"] = True
        return "dummy_path"

    monkeypatch.setattr("app.services.mixed_scenario_service.append_debug_error", fake_append)
    monkeypatch.setattr("app.services.mixed_scenario_service.ensure_debug_log_file", fake_ensure)

    cfg = {"debug_logging": {"enabled": True}}
    game = SimpleNamespace(id=11, name="Startup Notices")

    MixedGameService._record_startup_notice(
        cfg,
        game,
        "Regenerated node policies from supply chain config",
        details={"supply_chain_config_id": 123},
    )

    assert cfg.get("startup_notices") == [
        "Regenerated node policies from supply chain config"
    ]
    assert captured.get("message") == "Regenerated node policies from supply chain config"
    assert captured.get("details") == {"supply_chain_config_id": 123}
    assert captured.get("ensure_called") is True

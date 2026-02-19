import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

pytest.importorskip("pydantic")

backend_root = Path(__file__).resolve().parents[2]
if str(backend_root) not in sys.path:
    sys.path.append(str(backend_root))

from app.services.engine import DEFAULT_STEADY_STATE_DEMAND
from app.services.mixed_game_service import MixedGameService
from app.simulation.debug_logging import append_debug_round_log
from app.simulation.helpers import compute_shipping_outcome, process_ship_queue


class DummyGame:
    def __init__(self, game_id: int = 1, name: str = "Test Game") -> None:
        self.id = game_id
        self.name = name


def test_process_ship_queue_preserves_pipeline_state():
    state = {
        "current_step": 0,
        # Modern pipeline: inbound_supply_future carries shipments with item ids.
        "inbound_supply_future": [
            {"step_number": 1, "quantity": 4, "product_id": "widget", "source": "__upstream__"},
            {"step_number": 2, "quantity": 4, "product_id": "widget", "source": "__upstream__"},
        ],
    }
    policy = {"supply_leadtime": 2}

    arriving, snapshot = process_ship_queue(state, policy, current_step=1)

    # First leg arrives, second stays in pipeline
    assert arriving == 4
    assert snapshot == [4, 0]
    assert state["ship_queue"] == [4, 0]
    assert state["incoming_shipments"] == [4, 0]


def test_market_supply_ships_full_demand():
    shipped, inventory_after, backlog_after, demand, available = compute_shipping_outcome(
        node_type="market_supply",
        inventory_before=0,
        backlog_before=0,
        arrivals_now=0,
        incoming_now=25,
    )

    assert demand == 25
    assert available == 0
    assert shipped == 25
    assert backlog_after == 0
    assert inventory_after == 0


def test_debug_rounds_append_in_chronological_order(tmp_path):
    config = {"debug_logging": {"enabled": True, "file_path": str(tmp_path / "log.txt")}}
    game = DummyGame()
    timestamp = datetime(2025, 1, 1, 12, 0, 0)

    append_debug_round_log(
        config,
        game,
        round_number=1,
        timestamp=timestamp,
        entries=[{"node": "retailer", "info_sent": {}, "reply": {}, "ending_state": {}}],
    )
    append_debug_round_log(
        config,
        game,
        round_number=2,
        timestamp=timestamp,
        entries=[{"node": "wholesaler", "info_sent": {}, "reply": {}, "ending_state": {}}],
    )

    path = Path(config["debug_logging"]["file_path"])
    content = path.read_text(encoding="utf-8")

    round1_index = content.index("Round 1 @")
    round2_index = content.index("Round 2 @")
    assert round1_index < round2_index


def test_initialise_shipment_pipeline_uses_default_when_zero():
    state: Dict[str, Any] = {
        "current_step": 0,
        "ship_queue": [1, 2],
        "incoming_shipments": [1, 2],
        "inbound_supply_future": [{"step_number": 1, "quantity": 1}],
    }

    MixedGameService._initialise_shipment_pipeline(
        state,
        supply_leadtime=2,
        default_quantity=0,
        product_id="widget",
    )

    assert "ship_queue" not in state
    assert "incoming_shipments" not in state
    assert "inbound_supply_future" not in state


def test_initialise_shipment_pipeline_backfills_missing_entries():
    state: Dict[str, Any] = {"current_step": 0, "ship_queue": [0, 6], "incoming_shipments": [0, 6]}

    MixedGameService._initialise_shipment_pipeline(
        state,
        supply_leadtime=2,
        default_quantity=4,
        product_id="widget",
    )

    assert "ship_queue" not in state
    assert "incoming_shipments" not in state
    assert "inbound_supply_future" not in state


def test_initialise_order_pipeline_uses_default_when_zero():
    state: Dict[str, Any] = {"info_queue": [1], "info_detail_queue": [{"x": 1}]}

    MixedGameService._initialise_order_pipeline(
        state,
        order_leadtime=3,
        default_quantity=0,
    )

    assert "info_queue" not in state
    assert "info_detail_queue" not in state
    assert "inbound_demand" not in state
    assert state["incoming_orders"] == 0


def test_initialise_order_pipeline_replaces_non_positive_entries():
    state: Dict[str, Any] = {
        "info_queue": [0, -5],
        "info_detail_queue": [{}, {}],
    }

    MixedGameService._initialise_order_pipeline(
        state,
        order_leadtime=2,
        default_quantity=7,
    )

    assert "info_queue" not in state
    assert "info_detail_queue" not in state
    assert "inbound_demand" not in state
    assert state["incoming_orders"] == 0


def test_seed_order_queue_ensures_positive_baseline():
    state: Dict[str, Any] = {}

    MixedGameService._seed_order_queue(
        state,
        current_step=0,
        order_leadtime=2,
        quantity=0,
        default_downstream="__self__",
        product_id="widget",
    )

    assert state["inbound_demand"] == [
        {
            "step_number": 1,
            "quantity": DEFAULT_STEADY_STATE_DEMAND,
            "order_priority": 1,
            "downstream": "__self__",
            "product_id": "widget",
        }
    ]

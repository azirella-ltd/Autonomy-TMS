from app.services.mixed_scenario_service import MixedScenarioService


def test_seed_order_queue_populates_future_steps():
    state = {}

    MixedScenarioService._seed_order_queue(
        state,
        current_step=0,
        order_leadtime=3,
        quantity=4,
        default_downstream="__self__",
        product_id="widget",
    )

    orders = state.get("inbound_demand")
    assert orders is not None
    assert len(orders) == 1
    assert orders[0]["quantity"] == 4
    # step number should be 1 since we start from current_step=0
    assert orders[0]["step_number"] == 1


def test_initialise_shipment_pipeline_creates_inbound_supply():
    state = {}

    MixedScenarioService._initialise_shipment_pipeline(
        state,
        supply_leadtime=2,
        default_quantity=5,
        product_id="widget",
    )

    assert state.get("ship_queue") is None
    assert state.get("incoming_shipments") is None
    assert state.get("inbound_supply_future") is None

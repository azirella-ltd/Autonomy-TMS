from app.services.engine import SupplyChainLine

def test_inventory_position_matches_onhand_minus_backlog():
    line = SupplyChainLine()

    # Seed different on-hand/backlog values to ensure non-trivial inventory positions.
    for node in line.nodes:
        node.inventory = 5
        node.backlog = 1

    retailer = line.nodes[0]
    retailer.inventory = 3
    retailer.backlog = 4

    stats = line.tick(customer_demand=5)

    for node in line.nodes:
        role_stats = stats[node.name]
        assert role_stats["inventory_position"] == role_stats["inventory_after"] - role_stats["backlog_after"]
        assert role_stats["inventory_position"] == node.inventory - node.backlog
        assert role_stats["inventory_position_with_pipeline"] == node.inventory_position


def test_zero_order_lead_propagates_orders_immediately():
    line = SupplyChainLine(demand_lead_time=0)

    for node in line.nodes:
        node.inventory = 20
        node.backlog = 0

    stats = line.tick(customer_demand=4)

    # All upstream partners should see the retailer's order in the same tick.
    assert stats["Retailer"]["incoming_order"] == 4
    assert stats["Wholesaler"]["incoming_order"] == 4
    assert stats["Distributor"]["incoming_order"] == 4
    assert stats["Manufacturer"]["incoming_order"] == 4

    # Orders are still queued through the pipeline bookkeeping, even with zero delay.
    assert stats["Retailer"]["order_pipe"] == [4]
    assert stats["Wholesaler"]["order_pipe"] == [4]
    assert stats["Distributor"]["order_pipe"] == [4]
    assert stats["Manufacturer"]["order_pipe"] == [0]

    # Shipments respond immediately to the observed demand, preventing upstream starvation.
    assert stats["Wholesaler"]["demand"] == 4
    assert stats["Distributor"]["demand"] == 4
    assert stats["Manufacturer"]["demand"] == 4


def test_pipelines_prefilled_for_positive_lead_times():
    line = SupplyChainLine(demand_lead_time=2, shipment_lead_time=2, initial_demand=5)

    for node in line.nodes:
        assert list(node.pipeline_shipments) == [5, 5]
        assert list(node.order_pipe) == [5, 5]

from app.simulation.sankey_logging import build_sankey_snapshot


def test_build_sankey_snapshot_legacy_order_fields():
    history = [
        {
            "demand": 12,
            "orders": {
                "distributor": {"order_received": 11},
                "wholesaler": {"order_received": 10},
                "retailer": {
                    "order_received": 9,
                    "backlog_before": 2,
                    "backlog_after": 1,
                },
            },
            "inventory_positions": {},
            "shipments": {},
        }
    ]

    snapshot = build_sankey_snapshot(history)

    assert snapshot["lane_totals"]["manufacturer_to_distributor"] == 11
    assert snapshot["lane_totals"]["distributor_to_wholesaler"] == 10
    # Demand (12) + backlog_before (2) - backlog_after (1) = 13 shipped to customers.
    assert snapshot["lane_totals"]["retailer_to_market"] == 13


def test_build_sankey_snapshot_backorder_aliases():
    history = [
        {
            "demand": 5,
            "orders": {
                "retailer": {
                    "received": 4,
                    "backorders_before": 3,
                    "backorder_after": 1,
                }
            },
            "inventory_positions": {},
            "shipments": {},
        }
    ]

    snapshot = build_sankey_snapshot(history)

    # When no shipment telemetry exists we fall back to backlog deltas.
    # Demand (5) + backlog_before (3) - backlog_after (1) = 7.
    assert snapshot["lane_totals"]["retailer_to_market"] == 7

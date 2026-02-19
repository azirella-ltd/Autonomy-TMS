from pathlib import Path
import sys

backend_root = Path(__file__).resolve().parents[2]
if str(backend_root) not in sys.path:
    sys.path.append(str(backend_root))

import pytest

try:
    from app.services.engine import Node
    from app.services.inventory_projection import project_start_of_next_round_inventory
    from app.services.policies import FixedOrderPolicy
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
    pytest.skip(f"Required dependency missing for tests: {exc}", allow_module_level=True)


def test_projected_inventory_includes_next_shipment():
    node = Node(
        "Retailer",
        FixedOrderPolicy(0),
        inventory=0,
        pipeline_shipments=[4, 1],
        shipment_lead_time=2,
        demand_lead_time=1,
    )

    projected = project_start_of_next_round_inventory(node)

    assert projected == 4


def test_projected_inventory_handles_zero_lead_time():
    node = Node(
        "Retailer",
        FixedOrderPolicy(0),
        inventory=7,
        pipeline_shipments=[],
        shipment_lead_time=0,
        demand_lead_time=0,
    )

    projected = project_start_of_next_round_inventory(node)

    assert projected == 7

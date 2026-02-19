from flask import Flask, request, jsonify
from typing import Any, Dict, List

from llm_agent.autonomy_simulation_agent import call_simulation_gpt

app = Flask(__name__)

@app.post("/order")
def get_order():
    data = request.get_json(force=True)
    role = str(data.get("role", "retailer")).lower()
    turn = int(data.get("turn", 0) or 0)
    on_hand = int(data.get("on_hand", 0) or 0)
    backlog = int(data.get("backlog", 0) or 0)
    demand = int(data.get("demand", 0) or 0)
    received = int(data.get("received_shipment", 0) or 0)

    expected_deliveries = data.get("expected_deliveries", [])
    if isinstance(expected_deliveries, list):
        pipeline_shipments: List[int] = [int(x) for x in expected_deliveries]
    else:
        pipeline_shipments = [int(expected_deliveries or 0)]

    try:
        order_lead = int(data.get("demand_lead_time", 2))
    except (TypeError, ValueError):
        order_lead = 2
    try:
        ship_lead = int(data.get("shipping_lead_time", 2))
    except (TypeError, ValueError):
        ship_lead = 2

    order_lead = max(order_lead, 0)
    ship_lead = max(ship_lead, 0)

    while len(pipeline_shipments) < max(ship_lead, 0):
        pipeline_shipments.append(0)

    state: Dict[str, Any] = {
        "role": role,
        "week": turn,
        "toggles": {
            "customer_demand_history_sharing": bool(data.get("customer_demand_history_sharing", False)),
            "volatility_signal_sharing": bool(data.get("volatility_signal_sharing", False)),
            "downstream_inventory_visibility": bool(data.get("downstream_inventory_visibility", False)),
        },
        "parameters": {
            "holding_cost": float(data.get("holding_cost", 0.5)),
            "backlog_cost": float(data.get("backlog_cost", 0.5)),
            "L_order": order_lead,
            "L_ship": ship_lead,
            "L_prod": int(data.get("production_lead_time", 4)),
        },
        "local_state": {
            "on_hand": on_hand,
            "backlog": backlog,
            "incoming_orders_this_week": demand,
            "received_shipment_this_week": received,
            "pipeline_orders_upstream": [0] * max(order_lead, 0),
            "pipeline_shipments_inbound": pipeline_shipments[:ship_lead] or [0] * max(ship_lead, 0),
            "optional": {},
        },
    }

    decision = call_simulation_gpt(state)
    return jsonify(
        {
            "order": decision.get("order_upstream"),
            "ship_to_downstream": decision.get("ship_to_downstream"),
            "rationale": decision.get("rationale"),
            "decision": decision,
        }
    )

if __name__ == "__main__":
    app.run(debug=True)

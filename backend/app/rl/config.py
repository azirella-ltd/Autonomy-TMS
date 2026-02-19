from dataclasses import dataclass
from typing import Dict, List, Tuple

# --- Discrete action indices (from the transentis-style game UI) -------------
# Interpret action index 'i' as "order ACTION_LEVELS[i] units" this week.
# We use 0..100 in steps of 5 (21 actions). This maps nicely to UI sliders
# and keeps the agent's search space compact and stable.
ACTION_LEVELS: List[int] = list(range(0, 105, 5))  # [0, 5, 10, ..., 100]

# --- Supply chain topology (classic simulation) --------------------------------
# Node order is fixed: 0=Retailer, 1=Wholesaler, 2=Distributor, 3=Manufacturer
NODES: List[str] = ["retailer", "wholesaler", "distributor", "manufacturer"]
NODE_INDEX: Dict[str, int] = {name: i for i, name in enumerate(NODES)}

# Upstream shipments move Manufacturer -> Distributor -> Wholesaler -> Retailer
# Downstream orders move Retailer -> Wholesaler -> Distributor -> Manufacturer
# Adjacency for shipments (directed): edge u->v means shipments flow u -> v
SHIPMENT_EDGES: List[Tuple[int, int]] = [
    (NODE_INDEX["manufacturer"], NODE_INDEX["distributor"]),
    (NODE_INDEX["distributor"], NODE_INDEX["wholesaler"]),
    (NODE_INDEX["wholesaler"], NODE_INDEX["retailer"]),
]

# Orders flow opposite direction (v->u)
ORDER_EDGES: List[Tuple[int, int]] = [(v, u) for (u, v) in SHIPMENT_EDGES]

# Default delays (in weeks)
DEFAULT_ORDER_LEADTIME = 2      # order information delay
DEFAULT_SUPPLY_LEADTIME = 2      # shipping lead time

# Features we expect per node per week when training / deciding
NODE_FEATURES: List[str] = [
    # Observations (state)
    "inventory",
    "backlog",
    "incoming_orders",
    "incoming_shipments",
    "on_order",         # pipeline (orders placed but not arrived yet)
    # Optional conditioning (context)
    "role_onehot_0", "role_onehot_1", "role_onehot_2", "role_onehot_3",
    "lead_time_order", "lead_time_supply",
]

@dataclass
class SimulationParams:
    order_leadtime: int = DEFAULT_ORDER_LEADTIME
    supply_leadtime: int = DEFAULT_SUPPLY_LEADTIME
    init_inventory: int = 12
    holding_cost: float = 0.5
    backlog_cost: float = 1.0
    max_inbound_per_link: int = 100  # shipment capacity (cap simulation explosions)
    max_order: int = 100             # to clip raw orders in simulators

from dataclasses import dataclass
from typing import List

# --- Discrete action indices -------------------------------------------------
# Interpret action index 'i' as "order ACTION_LEVELS[i] units" this week.
# We use 0..100 in steps of 5 (21 actions). Maps to UI sliders.
ACTION_LEVELS: List[int] = list(range(0, 105, 5))  # [0, 5, 10, ..., 100]

# --- Node features (per site per week) ---------------------------------------
# Site-type one-hots use AWS SC master_type categories (4 values) — independent
# of topology size. Feature count (11) is stable across topologies.
NODE_FEATURES: List[str] = [
    # Observations (state)
    "inventory",
    "backlog",
    "incoming_orders",
    "incoming_shipments",
    "on_order",           # pipeline (orders placed but not arrived yet)
    # Site-type conditioning — AWS SC master_type one-hot
    "site_type_market_supply",   # MARKET_SUPPLY (upstream source)
    "site_type_market_demand",   # MARKET_DEMAND (terminal demand sink)
    "site_type_inventory",       # INVENTORY (storage/fulfillment)
    "site_type_manufacturer",    # MANUFACTURER (transform with BOM)
    "lead_time_order", "lead_time_supply",
]


@dataclass
class SimulationParams:
    """Simulation parameters loaded from SC entities.

    All fields must be populated from DB records before use:
    - order_leadtime / supply_leadtime: from TransportationLane.supply_lead_time
    - init_inventory: from InvLevel.on_hand_qty
    - holding_cost: from InvPolicy.holding_cost_range or (product.unit_cost * 0.25 / 52)
    - backlog_cost: from InvPolicy.backlog_cost_range or (holding_cost * 4)

    Raises ValueError at runtime if any field is not set before simulation.
    """
    order_leadtime: int = 2
    supply_leadtime: int = 2
    init_inventory: float = 0.0
    holding_cost: float = 0.0
    backlog_cost: float = 0.0
    max_inbound_per_link: int = 100  # shipment capacity (cap simulation explosions)
    max_order: int = 100             # to clip raw orders in simulators

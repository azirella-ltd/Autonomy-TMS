from dataclasses import dataclass
from typing import Dict, List, Tuple

# --- Discrete action indices -------------------------------------------------
# Interpret action index 'i' as "order ACTION_LEVELS[i] units" this week.
# We use 0..100 in steps of 5 (21 actions). Maps to UI sliders.
ACTION_LEVELS: List[int] = list(range(0, 105, 5))  # [0, 5, 10, ..., 100]

# --- DEPRECATED: Beer Game 4-node topology constants -------------------------
# These constants hardcode the classic Beer Game (Retailer→Wholesaler→Distributor→Manufacturer).
# New training runs must load topology dynamically from Site/TransportationLane tables.
# Pass config_id to load_sequences_from_db() to get topology from the actual SC config.
# Retained for backward compatibility with legacy training scripts only.
NODES: List[str] = ["retailer", "wholesaler", "distributor", "manufacturer"]  # DEPRECATED
NODE_INDEX: Dict[str, int] = {name: i for i, name in enumerate(NODES)}        # DEPRECATED

# DEPRECATED: edges assume the 4-node Beer Game linear chain.
# Use TransportationLane records for real topology.
SHIPMENT_EDGES: List[Tuple[int, int]] = [  # DEPRECATED
    (NODE_INDEX["manufacturer"], NODE_INDEX["distributor"]),
    (NODE_INDEX["distributor"], NODE_INDEX["wholesaler"]),
    (NODE_INDEX["wholesaler"], NODE_INDEX["retailer"]),
]
ORDER_EDGES: List[Tuple[int, int]] = [(v, u) for (u, v) in SHIPMENT_EDGES]   # DEPRECATED

# DEPRECATED: Default delays hardcoded to Beer Game standard.
# Use TransportationLane.supply_lead_time for real lead times.
DEFAULT_ORDER_LEADTIME = 2   # DEPRECATED — use TransportationLane.supply_lead_time
DEFAULT_SUPPLY_LEADTIME = 2  # DEPRECATED — use TransportationLane.supply_lead_time

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
    # Site-type conditioning — AWS SC master_type one-hot (replaces Beer Game role one-hots)
    "site_type_market_supply",   # MARKET_SUPPLY (upstream source)
    "site_type_market_demand",   # MARKET_DEMAND (terminal demand sink)
    "site_type_inventory",       # INVENTORY (storage/fulfillment)
    "site_type_manufacturer",    # MANUFACTURER (transform with BOM)
    "lead_time_order", "lead_time_supply",
]


@dataclass
class SimulationParams:
    # DEPRECATED: defaults below are Beer Game values retained for legacy training only.
    # New simulations must populate these from SC entities (InvLevel, TransportationLane, InvPolicy).
    order_leadtime: int = DEFAULT_ORDER_LEADTIME   # DEPRECATED default
    supply_leadtime: int = DEFAULT_SUPPLY_LEADTIME  # DEPRECATED default
    init_inventory: int = 12   # DEPRECATED — use InvLevel.on_hand_qty
    holding_cost: float = 0.5  # DEPRECATED — use InvPolicy.holding_cost_range
    backlog_cost: float = 1.0  # DEPRECATED — use InvPolicy.backlog_cost_range
    max_inbound_per_link: int = 100  # shipment capacity (cap simulation explosions)
    max_order: int = 100             # to clip raw orders in simulators

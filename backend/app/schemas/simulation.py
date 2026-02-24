from typing import List, Dict, Optional, Any, Set, Union
from pydantic import BaseModel, Field

class OrderRequest(BaseModel):
    """Represents an order placed by a node."""
    product_id: str
    quantity: int
    downstream: Optional[str] = None
    due_round: int
    order_priority: int = 1
    source: Optional[str] = None
    sequence: Optional[int] = None
    breakdown: Optional[Dict[str, int]] = None
    step_number: Optional[int] = None # Alias for due_round in some contexts

class Shipment(BaseModel):
    """Represents a shipment of goods between nodes."""
    product_id: str
    quantity: int
    source: str
    destination: str
    arrival_round: int
    shipment_id: Optional[str] = None

class NodeState(BaseModel):
    """Represents the mutable state of a single node in the supply chain."""
    inventory_by_item: Dict[str, int] = Field(default_factory=dict)
    backlog_by_item: Dict[str, int] = Field(default_factory=dict)
    base_stock_by_item: Dict[str, int] = Field(default_factory=dict)
    on_order_by_item: Dict[str, int] = Field(default_factory=dict)
    inventory: int = 0
    backlog: int = 0
    backlog_orders: List[OrderRequest] = Field(default_factory=list)
    
    inbound_demand: List[OrderRequest] = Field(default_factory=list)
    inbound_supply: List[Shipment] = Field(default_factory=list)
    inbound_supply_future: List[Shipment] = Field(default_factory=list)  # future inbound supply
    
    # Tracking metrics for the current round
    current_round_demand: Dict[str, int] = Field(default_factory=dict)
    current_round_fulfillment: Dict[str, int] = Field(default_factory=dict)
    orders_received_by_item: Dict[str, int] = Field(default_factory=dict)
    supply_received_by_item: Dict[str, int] = Field(default_factory=dict)
    lost_sales_by_item: Dict[str, int] = Field(default_factory=dict)
    otif_total_orders: int = 0
    otif_total_units: int = 0
    otif_on_time_in_full_units: int = 0
    otif_late_units: int = 0
    otif_late_orders: int = 0
    otif_lost_sale_cost: float = 0.0
    
    # Transient fields for round processing
    matured_orders: List[OrderRequest] = Field(default_factory=list)

    class Config:
        extra = "allow"  # allow transient debug fields (e.g., debug_start_inventory)

class LaneConfig(BaseModel):
    """Configuration for a connection between two sites."""
    from_site_id: str = Field(alias="from")
    to_site_id: str = Field(alias="to")
    capacity: Optional[int] = None
    lead_time_days: Optional[int] = None
    demand_lead_time: int = 0
    supply_lead_time: int = 0

class TopologyConfig(BaseModel):
    """Represents the static structure of the supply chain network."""
    lanes: List[LaneConfig]
    shipments_map: Dict[str, List[str]] # upstream -> [downstream]
    orders_map: Dict[str, List[str]] # downstream -> [upstream]
    market_nodes: List[str]
    all_nodes: List[str]
    node_sequence: List[str] # Topological order (upstream to downstream)
    lanes_by_upstream: Dict[str, List[LaneConfig]]
    node_types: Dict[str, str]
    lane_lookup: Dict[Any, LaneConfig] # Keyed by (upstream, downstream) tuple, but Pydantic dict keys must be strings

class RoundContext(BaseModel):
    """Holds the context for the current simulation round."""
    round_number: int
    scenario_id: int
    topology: TopologyConfig
    config: Dict[str, Any] = Field(default_factory=dict)
    node_states: Dict[str, NodeState] = Field(default_factory=dict)
    
    # Global queues
    inbound_supply: List[Shipment] = Field(default_factory=list)

    node_policies: Dict[str, Any] = Field(default_factory=dict)
    market_demand_map: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    round_record: Optional[Any] = None # GameRound object (Any to avoid circular import issues if not careful, but we imported GameRound)
    item_priorities: Dict[str, Optional[int]] = Field(default_factory=dict)
    node_priorities: Dict[str, Optional[int]] = Field(default_factory=dict)
    agent_comments: Dict[str, str] = Field(default_factory=dict)
    agent_fallbacks: Dict[str, Dict[str, Any]] = Field(default_factory=dict)  # Tracks AI fallback warnings

    # In the current implementation, orders are often passed directly or stored in queues.
    # We'll need to adapt this to the specific logic.

class SimulationConfig(BaseModel):
    """Unified configuration for the simulation."""
    scenario_id: int
    topology: TopologyConfig
    # Add other config fields as needed

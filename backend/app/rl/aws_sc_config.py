"""
Supply Chain Data Model compliant configuration for training data.

This module extends SimulationParams to use SC field names and entities,
while maintaining backward compatibility with simulation schema.

Reference: https://docs.[removed]
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


# ============================================================================
# SC Field Mappings
# ============================================================================

# Mapping from simulation fields to SC fields
SIMULATION_TO_AWS_SC_MAP = {
    # Inventory fields
    "inventory": "on_hand_qty",
    "backlog": "backorder_qty",
    "pipeline": "in_transit_qty",
    "on_order": "in_transit_qty",  # Alias

    # Lead time fields
    "order_leadtime": "lead_time_days",
    "supply_leadtime": "lead_time_days",

    # Order fields
    "incoming_orders": "demand_qty",
    "incoming_shipments": "supply_qty",
    "placed_order": "order_qty",

    # Cost fields (extensions)
    "holding_cost": "holding_cost_per_unit",
    "backlog_cost": "backlog_cost_per_unit",
}

# Mapping from SC fields to simulation fields (reverse)
AWS_SC_TO_SIMULATION_MAP = {
    "on_hand_qty": "inventory",
    "backorder_qty": "backlog",
    "in_transit_qty": "pipeline",
    "lead_time_days": "order_leadtime",
    "demand_qty": "incoming_orders",
    "supply_qty": "incoming_shipments",
    "order_qty": "placed_order",
    "holding_cost_per_unit": "holding_cost",
    "backlog_cost_per_unit": "backlog_cost",
}


# ============================================================================
# SC Node Features (for GNN training)
# ============================================================================

# Node features following SC inv_level schema
AWS_SC_NODE_FEATURES: List[str] = [
    # Core SC inv_level fields
    "on_hand_qty",              # Inventory on hand
    "backorder_qty",            # Backorder quantity
    "in_transit_qty",           # In-transit inventory (pipeline)
    "allocated_qty",            # Allocated to orders
    "available_qty",            # Available to promise (ATP)

    # Demand/supply fields
    "demand_qty",               # Incoming demand
    "supply_qty",               # Incoming supply
    "order_qty",                # Order placed upstream

    # Policy fields (from inv_policy)
    "safety_stock_qty",         # Safety stock target
    "reorder_point_qty",        # Reorder point
    "min_qty",                  # Min inventory
    "max_qty",                  # Max inventory

    # Sourcing fields (from sourcing_rules)
    "lead_time_days",           # Lead time in days
    "source_type",              # "buy", "transfer", "manufacture"
    "priority",                 # Sourcing priority

    # Site context (one-hot encoded) — AWS SC master_type (4 categories)
    "site_type_0", "site_type_1", "site_type_2", "site_type_3",

    # Position in DAG (0-1)
    "position_normalized",
]

# Minimal subset for simulation compatibility
SIMULATION_COMPATIBLE_FEATURES: List[str] = [
    "on_hand_qty",              # Maps to inventory
    "backorder_qty",            # Maps to backlog
    "in_transit_qty",           # Maps to pipeline
    "demand_qty",               # Maps to incoming_orders
    "supply_qty",               # Maps to incoming_shipments
    "order_qty",                # Maps to placed_order
    "lead_time_days",           # Maps to order_leadtime
]


# ============================================================================
# SC Site Types (master node types)
# ============================================================================

class SiteType(str, Enum):
    """SC master node types for DAG routing."""
    CUSTOMER = "CUSTOMER"                # Terminal demand sink (TradingPartner tpartner_type='customer')
    VENDOR = "VENDOR"                    # Upstream source (TradingPartner tpartner_type='vendor')
    INVENTORY = "INVENTORY"              # Storage/fulfillment
    MANUFACTURER = "MANUFACTURER"        # Transform node with BOM
    # Legacy aliases kept for backward compatibility with existing DB rows
    MARKET_DEMAND = "CUSTOMER"
    MARKET_SUPPLY = "VENDOR"


# Simulation role to SC site type mapping
SIMULATION_ROLE_TO_SITE_TYPE = {
    "retailer": SiteType.INVENTORY,
    "wholesaler": SiteType.INVENTORY,
    "distributor": SiteType.INVENTORY,
    "manufacturer": SiteType.MANUFACTURER,
}


# ============================================================================
# SC Inventory Policy Types
# ============================================================================

class InvPolicyType(str, Enum):
    """SC inventory policy types."""
    ABS_LEVEL = "abs_level"      # Absolute quantity
    DOC_DEM = "doc_dem"          # Days of coverage (demand-based)
    DOC_FCST = "doc_fcst"        # Days of coverage (forecast-based)
    SERVICE_LEVEL = "sl"         # Service level with z-score


# ============================================================================
# SC Sourcing Types
# ============================================================================

class SourceType(str, Enum):
    """SC sourcing rule types."""
    BUY = "buy"                  # Purchase from vendor
    TRANSFER = "transfer"        # Transfer from another site
    MANUFACTURE = "manufacture"  # Produce at this site


# ============================================================================
# SC-Compliant Parameters
# ============================================================================

@dataclass
class SupplyChainParams:
    """
    Supply Chain Data Model compliant parameters for training.

    This class uses SC field names as the primary schema,
    with optional simulation fields for backward compatibility.

    **SC Compliance**: Uses fields from:
    - inv_level: on_hand_qty, backorder_qty, in_transit_qty, safety_stock_qty
    - sourcing_rules: lead_time_days, source_type, priority
    - inv_policy: policy_type, cost fields
    - site: site_id, site_type
    - product: item_id
    """

    # ===== SC Core Fields (REQUIRED) =====

    # Entity identifiers
    site_id: str = "site_001"            # SC: site.site_id
    item_id: str = "item_001"            # SC: product.item_id
    company_id: str = "company_001"      # SC: company.company_id

    # Inventory level fields (from inv_level entity)
    on_hand_qty: float = 12.0            # SC: inv_level.on_hand_qty
    backorder_qty: float = 0.0           # SC: inv_level.backorder_qty
    in_transit_qty: float = 0.0          # SC: inv_level.in_transit_qty
    allocated_qty: float = 0.0           # SC: inv_level.allocated_qty
    available_qty: float = 12.0          # SC: inv_level.available_qty (ATP)
    safety_stock_qty: float = 0.0        # SC: inv_level.safety_stock_qty
    reorder_point_qty: float = 0.0       # SC: inv_level.reorder_point_qty
    min_qty: float = 0.0                 # SC: inv_level.min_qty
    max_qty: float = 100.0               # SC: inv_level.max_qty

    # Sourcing rule fields (from sourcing_rules entity)
    lead_time_days: int = 2              # SC: sourcing_rules.lead_time_days
    source_type: str = SourceType.TRANSFER.value  # SC: sourcing_rules.source_type
    priority: int = 1                    # SC: sourcing_rules.priority

    # Site fields (from site entity)
    site_type: str = SiteType.INVENTORY.value  # SC: Derived from master node type

    # ===== SC Policy Fields (from inv_policy) =====

    policy_type: str = InvPolicyType.ABS_LEVEL.value  # SC: inv_policy.policy_type
    holding_cost_per_unit: float = 0.5   # Extension: cost per unit per period
    backlog_cost_per_unit: float = 1.0   # Extension: cost per unit backorder

    # ===== Operational Constraints =====

    max_inbound_per_link: int = 100      # Extension: shipment capacity
    max_order_qty: int = 100             # Extension: max order size

    # ===== Simulation Compatibility (OPTIONAL - Extensions) =====

    # These fields are extensions to maintain backward compatibility
    # with simulation training data and agents
    role: Optional[str] = None           # Extension: Simulation role (retailer, etc.)
    position: Optional[int] = None       # Extension: Position in DAG (0-3)

    # Legacy field aliases (for backward compat)
    @property
    def inventory(self) -> float:
        """Alias for on_hand_qty (simulation compatibility)."""
        return self.on_hand_qty

    @property
    def backlog(self) -> float:
        """Alias for backorder_qty (simulation compatibility)."""
        return self.backorder_qty

    @property
    def pipeline(self) -> float:
        """Alias for in_transit_qty (simulation compatibility)."""
        return self.in_transit_qty

    @property
    def order_leadtime(self) -> int:
        """Alias for lead_time_days (simulation compatibility)."""
        return self.lead_time_days

    @property
    def supply_leadtime(self) -> int:
        """Alias for lead_time_days (simulation compatibility)."""
        return self.lead_time_days

    @property
    def holding_cost(self) -> float:
        """Alias for holding_cost_per_unit (simulation compatibility)."""
        return self.holding_cost_per_unit

    @property
    def backlog_cost(self) -> float:
        """Alias for backlog_cost_per_unit (simulation compatibility)."""
        return self.backlog_cost_per_unit

    @property
    def init_inventory(self) -> float:
        """Alias for on_hand_qty initial value (simulation compatibility)."""
        return self.on_hand_qty

    @property
    def max_order(self) -> int:
        """Alias for max_order_qty (simulation compatibility)."""
        return self.max_order_qty


@dataclass
class SimulationParamsV2(SupplyChainParams):
    """
    Extended SimulationParams with SC compliance.

    This class extends SupplyChainParams with simulation-specific
    defaults and convenience methods.

    **Usage**:
    ```python
    # SC compliant usage
    params = SimulationParamsV2(
        site_id="retailer_001",
        item_id="cases",
        on_hand_qty=12.0,
        backorder_qty=0.0,
        lead_time_days=2
    )

    # Simulation backward compatibility
    params = SimulationParamsV2(
        role="retailer",
        position=0
    )
    # Accesses params.inventory, params.backlog work via aliases
    ```
    """

    def __post_init__(self):
        """Initialize simulation-specific defaults."""
        # If role is provided, map to site_id and site_type
        if self.role is not None:
            self.site_id = f"{self.role}_001"
            self.site_type = SIMULATION_ROLE_TO_SITE_TYPE.get(
                self.role,
                SiteType.INVENTORY.value
            )

        # If position is provided, use it for normalization
        if self.position is not None:
            # Position 0-3 for simulation
            pass

    def to_simulation_dict(self) -> Dict:
        """
        Convert to simulation schema dictionary (legacy format).

        Returns:
            Dictionary with simulation field names
        """
        return {
            "inventory": self.on_hand_qty,
            "backlog": self.backorder_qty,
            "pipeline": self.in_transit_qty,
            "order_leadtime": self.lead_time_days,
            "supply_leadtime": self.lead_time_days,
            "holding_cost": self.holding_cost_per_unit,
            "backlog_cost": self.backlog_cost_per_unit,
            "init_inventory": self.on_hand_qty,
            "max_order": self.max_order_qty,
            "role": self.role,
            "position": self.position,
        }

    def to_sc_dict(self) -> Dict:
        """
        Convert to SC schema dictionary.

        Returns:
            Dictionary with SC field names
        """
        return {
            "site_id": self.site_id,
            "item_id": self.item_id,
            "company_id": self.company_id,
            "on_hand_qty": self.on_hand_qty,
            "backorder_qty": self.backorder_qty,
            "in_transit_qty": self.in_transit_qty,
            "allocated_qty": self.allocated_qty,
            "available_qty": self.available_qty,
            "safety_stock_qty": self.safety_stock_qty,
            "reorder_point_qty": self.reorder_point_qty,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "lead_time_days": self.lead_time_days,
            "source_type": self.source_type,
            "priority": self.priority,
            "site_type": self.site_type,
            "policy_type": self.policy_type,
            "holding_cost_per_unit": self.holding_cost_per_unit,
            "backlog_cost_per_unit": self.backlog_cost_per_unit,
        }

    @classmethod
    def from_simulation_dict(cls, data: Dict) -> "SimulationParamsV2":
        """
        Create from simulation schema dictionary (legacy format).

        Args:
            data: Dictionary with simulation field names

        Returns:
            SimulationParamsV2 instance
        """
        return cls(
            on_hand_qty=data.get("inventory", 12.0),
            backorder_qty=data.get("backlog", 0.0),
            in_transit_qty=data.get("pipeline", 0.0),
            lead_time_days=data.get("order_leadtime", 2),
            holding_cost_per_unit=data.get("holding_cost", 0.5),
            backlog_cost_per_unit=data.get("backlog_cost", 1.0),
            max_order_qty=data.get("max_order", 100),
            role=data.get("role"),
            position=data.get("position"),
        )

    @classmethod
    def from_sc_entities(
        cls,
        site_id: str,
        item_id: str,
        inv_level: Dict,
        sourcing_rule: Dict,
        inv_policy: Optional[Dict] = None,
    ) -> "SimulationParamsV2":
        """
        Create from SC entity dictionaries.

        Args:
            site_id: Site identifier
            item_id: Item identifier
            inv_level: inv_level entity fields
            sourcing_rule: sourcing_rules entity fields
            inv_policy: inv_policy entity fields (optional)

        Returns:
            SimulationParamsV2 instance
        """
        params = cls(
            site_id=site_id,
            item_id=item_id,
            on_hand_qty=inv_level.get("on_hand_qty", 0.0),
            backorder_qty=inv_level.get("backorder_qty", 0.0),
            in_transit_qty=inv_level.get("in_transit_qty", 0.0),
            allocated_qty=inv_level.get("allocated_qty", 0.0),
            available_qty=inv_level.get("available_qty", 0.0),
            safety_stock_qty=inv_level.get("safety_stock_qty", 0.0),
            reorder_point_qty=inv_level.get("reorder_point_qty", 0.0),
            min_qty=inv_level.get("min_qty", 0.0),
            max_qty=inv_level.get("max_qty", 100.0),
            lead_time_days=sourcing_rule.get("lead_time_days", 2),
            source_type=sourcing_rule.get("source_type", SourceType.TRANSFER.value),
            priority=sourcing_rule.get("priority", 1),
        )

        if inv_policy:
            params.policy_type = inv_policy.get("policy_type", InvPolicyType.ABS_LEVEL.value)
            params.holding_cost_per_unit = inv_policy.get("holding_cost_per_unit", 0.5)
            params.backlog_cost_per_unit = inv_policy.get("backlog_cost_per_unit", 1.0)

        return params


# ============================================================================
# Utility Functions
# ============================================================================

def simulation_to_sc_state(simulation_state: Dict) -> Dict:
    """
    Convert simulation state dictionary to SC format.

    Args:
        simulation_state: Dictionary with simulation field names

    Returns:
        Dictionary with SC field names
    """
    sc_state = {}
    for sim_field, aws_field in SIMULATION_TO_AWS_SC_MAP.items():
        if sim_field in simulation_state:
            sc_state[aws_field] = simulation_state[sim_field]

    # Add default fields if missing
    sc_state.setdefault("site_id", "site_001")
    sc_state.setdefault("item_id", "item_001")

    return sc_state


def sc_to_simulation_state(sc_state: Dict) -> Dict:
    """
    Convert SC state dictionary to simulation format.

    Args:
        sc_state: Dictionary with SC field names

    Returns:
        Dictionary with simulation field names
    """
    simulation_state = {}
    for aws_field, sim_field in AWS_SC_TO_SIMULATION_MAP.items():
        if aws_field in sc_state:
            simulation_state[sim_field] = sc_state[aws_field]

    return simulation_state


def get_sc_node_features(
    params: SupplyChainParams,
    demand_qty: float = 0.0,
    supply_qty: float = 0.0,
    order_qty: float = 0.0,
) -> List[float]:
    """
    Assemble SC-compliant node features for GNN training.

    Args:
        params: SC parameters
        demand_qty: Current demand
        supply_qty: Current supply
        order_qty: Order placed

    Returns:
        List of feature values matching AWS_SC_NODE_FEATURES
    """
    # Site type one-hot (4 types — CUSTOMER/VENDOR are the canonical names;
    # MARKET_DEMAND/MARKET_SUPPLY are legacy aliases that map to the same slots)
    site_type_onehot = [0.0] * 4
    site_types = [
        SiteType.CUSTOMER.value,
        SiteType.VENDOR.value,
        SiteType.INVENTORY.value,
        SiteType.MANUFACTURER.value
    ]
    # Normalise legacy names before lookup
    site_type_val = params.site_type
    if site_type_val == SiteType.CUSTOMER.value:
        site_type_val = SiteType.CUSTOMER.value
    elif site_type_val == SiteType.VENDOR.value:
        site_type_val = SiteType.VENDOR.value
    if site_type_val in site_types:
        idx = site_types.index(site_type_val)
        site_type_onehot[idx] = 1.0

    # Role one-hot (simulation compatibility)
    role_onehot = [0.0] * 4
    if params.role:
        roles = ["retailer", "wholesaler", "distributor", "manufacturer"]
        if params.role in roles:
            idx = roles.index(params.role)
            role_onehot[idx] = 1.0

    return [
        # Core SC fields
        params.on_hand_qty,
        params.backorder_qty,
        params.in_transit_qty,
        params.allocated_qty,
        params.available_qty,

        # Demand/supply
        demand_qty,
        supply_qty,
        order_qty,

        # Policy fields
        params.safety_stock_qty,
        params.reorder_point_qty,
        params.min_qty,
        params.max_qty,

        # Sourcing fields
        float(params.lead_time_days),
        float(params.source_type == SourceType.BUY.value),  # Binary encoding
        float(params.priority),

        # Site type one-hot
        *site_type_onehot,

        # Role one-hot (simulation compat)
        *role_onehot,

        # Position
        float(params.position or 0) / 3.0,  # Normalized 0-1
    ]

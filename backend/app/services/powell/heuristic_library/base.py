"""
ERP-Aware Heuristic Library -- Abstract Base & Shared Dataclasses.

Defines the universal interface for ERP-specific heuristic implementations.
Each ERP vendor (SAP, D365, Odoo) implements ``BaseHeuristics`` with all 11
TRM decision types.  Pure functions: f(state, params) -> HeuristicDecision.
No database access, no API calls, no side effects.

See DIGITAL_TWIN.md section 8A for the full algorithmic specification.
"""

from __future__ import annotations

import abc
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Decision result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeuristicDecision:
    """Result from any heuristic computation.

    Every TRM heuristic returns one of these.  The ``erp_params_used`` dict
    provides an audit trail of which ERP parameters drove the decision.
    """

    trm_type: str
    action: int                 # discrete action index (0=no-action, 1..N per TRM)
    quantity: float             # continuous parameter (order qty, buffer level, etc.)
    reasoning: str              # human-readable explanation
    confidence: float = 1.0    # always 1.0 for deterministic heuristics
    erp_params_used: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-TRM state dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplenishmentState:
    """What the simulation site knows at replenishment decision time."""

    inventory_position: float     # on_hand + pipeline - backlog
    on_hand: float
    backlog: float
    pipeline_qty: float           # total in-transit
    avg_daily_demand: float
    demand_cv: float
    lead_time_days: float
    forecast_daily: float         # current-period forecast
    day_of_week: int              # 0=Mon ... 6=Sun
    day_of_month: int             # 1-31

    # Extension: from material_valuation — price change % (current vs previous)
    cost_trend: float = 0.0
    # Extension: from supply_plan — already-planned qty for this product-site
    existing_planned_qty: float = 0.0
    # Extension: from material_valuation — current standard/moving-avg cost
    unit_cost: float = 0.0


@dataclass(frozen=True)
class ATPState:
    """State for ATP/order promising decisions."""

    order_qty: float
    order_priority: int           # 1=highest ... 5=lowest
    product_id: str
    site_id: str
    available_inventory: float
    allocated_inventory: float    # already consumed by higher-priority orders
    pipeline_qty: float
    forecast_remaining: float     # unconsumed forecast in horizon
    confirmed_orders: float       # already confirmed customer orders
    delivery_date_requested: Optional[str] = None

    # Extension: from outbound_order_line_schedule — qty already promised for this date
    schedule_committed_qty: float = 0.0
    # Extension: from outbound_order_status — delivery status code
    order_delivery_status: str = ""
    # Extension: derived from outbound_order_status — urgency factor (0-1)
    customer_urgency: float = 0.5


@dataclass(frozen=True)
class RebalancingState:
    """State for inventory rebalancing (cross-location transfer) decisions."""

    source_on_hand: float
    source_backlog: float
    source_avg_demand: float
    source_safety_stock: float
    target_on_hand: float
    target_backlog: float
    target_avg_demand: float
    target_safety_stock: float
    transfer_lead_time_days: float
    transfer_cost_per_unit: float = 0.0


@dataclass(frozen=True)
class OrderTrackingState:
    """State for order exception detection."""

    order_id: str
    order_type: str               # PO, MO, TO
    expected_date: str
    current_status: str
    quantity_ordered: float
    quantity_received: float
    days_overdue: float
    supplier_on_time_rate: float  # 0.0-1.0 historical
    is_critical: bool = False

    # Extension: from outbound_order_status — granular status fields
    delivery_status: str = ""
    billing_status: str = ""
    goods_issue_status: str = ""


@dataclass(frozen=True)
class MOExecutionState:
    """State for manufacturing order execution decisions."""

    mo_id: str
    product_id: str
    site_id: str
    quantity: float
    priority: int
    due_date: str
    setup_time_hours: float
    run_time_hours: float
    available_capacity_hours: float
    current_wip: float
    product_family: str = ""
    glenday_category: str = ""    # green/yellow/blue/red
    last_product_run: str = ""    # for changeover minimization
    oee: float = 0.85

    # Extension: from capacity_resource_detail / work_center_master
    work_center_capacity_hours: float = 8.0
    work_center_queue_depth: int = 0     # production orders waiting at this WC
    work_center_parallel_ops: int = 1    # from capacity_resource_detail.standard_parallel_ops


@dataclass(frozen=True)
class TOExecutionState:
    """State for transfer order execution decisions."""

    to_id: str
    product_id: str
    from_site_id: str
    to_site_id: str
    quantity: float
    priority: int
    due_date: str
    transport_mode: str           # truck, rail, sea, air
    consolidation_window_days: int = 1
    current_load_pct: float = 0.0
    is_expeditable: bool = True


@dataclass(frozen=True)
class QualityState:
    """State for quality disposition decisions."""

    lot_id: str
    product_id: str
    defect_type: str              # visual, dimensional, functional, contamination
    defect_severity: str          # minor, major, critical
    quantity: float
    unit_cost: float
    rework_cost_per_unit: float
    scrap_value_per_unit: float
    customer_impact: bool = False

    # Extension: from outbound_order_status — urgency from downstream order status
    customer_urgency: float = 0.5


@dataclass(frozen=True)
class MaintenanceState:
    """State for maintenance scheduling decisions."""

    asset_id: str
    site_id: str
    last_maintenance_date: str
    mtbf_days: float              # mean time between failures
    mttr_hours: float             # mean time to repair
    current_operating_hours: float
    hours_since_last_pm: float
    criticality: str              # A, B, C (A=highest)
    upcoming_production_load: float  # 0.0-1.0 capacity utilization
    maintenance_cost: float = 0.0

    # Extension: from capacity_resource_detail — queue hours at this work center
    work_center_queue_hours: float = 0.0
    # Extension: gap in production schedule (hours available for maintenance)
    production_gap_hours: float = 0.0


@dataclass(frozen=True)
class SubcontractingState:
    """State for make-vs-buy / subcontracting decisions."""

    product_id: str
    site_id: str
    quantity_needed: float
    internal_capacity_available: float
    internal_cost_per_unit: float
    external_cost_per_unit: float
    external_lead_time_days: float
    internal_lead_time_days: float
    quality_risk_external: float  # 0.0-1.0 probability of quality issue
    due_date: str = ""

    # Extension: from material_valuation — internal cost for make-vs-buy comparison
    internal_unit_cost: float = 0.0
    # Extension: from vendor_product — external vendor pricing
    external_unit_cost: float = 0.0


@dataclass(frozen=True)
class ForecastAdjustmentState:
    """State for signal-driven forecast adjustment decisions."""

    product_id: str
    site_id: str
    current_forecast: float
    signal_type: str              # email, voice, market_intel, demand_sensing
    signal_direction: str         # increase, decrease, unchanged
    signal_magnitude_pct: float   # suggested adjustment percentage
    signal_confidence: float      # 0.0-1.0
    forecast_error_recent: float  # recent MAPE or bias
    demand_cv: float = 0.0

    # Extension: from outbound_order_line_schedule — order velocity trend
    order_velocity_trend: float = 0.0


@dataclass(frozen=True)
class InventoryBufferState:
    """State for inventory buffer (safety stock) adjustment decisions."""

    product_id: str
    site_id: str
    current_safety_stock: float
    avg_daily_demand: float
    demand_cv: float
    lead_time_days: float
    lead_time_cv: float
    service_level_target: float   # 0.0-1.0
    recent_stockout_count: int
    recent_excess_days: int
    holding_cost_per_unit: float = 0.0
    stockout_cost_per_unit: float = 0.0

    # Extension: from material_valuation — price change % for buffer sizing
    cost_trend: float = 0.0


# ---------------------------------------------------------------------------
# Universal ERP Planning Parameters
# ---------------------------------------------------------------------------


@dataclass
class ERPPlanningParams:
    """Universal planning parameters loaded from site_planning_config.

    These are the ERP-agnostic typed columns from ``SitePlanningConfig``
    plus the raw ``erp_params`` JSONB for ERP-specific overrides.
    """

    planning_method: str = "REORDER_POINT"
    lot_sizing_rule: str = "LOT_FOR_LOT"
    reorder_point: float = 0.0
    order_up_to: float = 0.0
    safety_stock: float = 0.0
    fixed_lot_size: float = 0.0
    min_order_quantity: float = 0.0
    max_order_quantity: float = 0.0   # 0 = unlimited
    order_multiple: float = 0.0
    lead_time_days: int = 7
    review_period_days: int = 7
    frozen_horizon_days: int = 0
    max_inventory: float = 0.0
    procurement_type: str = "buy"     # buy, transfer, manufacture
    forecast_consumption_mode: str = ""
    forecast_consumption_fwd_days: int = 0
    forecast_consumption_bwd_days: int = 0
    strategy_group: str = ""
    erp_source: str = "sap"           # sap, d365, odoo
    erp_params: Dict[str, Any] = field(default_factory=dict)

    # --- Convenience properties for backward compat ---

    def to_replenishment_config(self) -> "ReplenishmentConfig":
        """Convert to the legacy ReplenishmentConfig for backward compat."""
        return ReplenishmentConfig(
            planning_method=self.planning_method,
            lot_sizing_rule=self.lot_sizing_rule,
            reorder_point=self.reorder_point,
            order_up_to=self.order_up_to,
            safety_stock=self.safety_stock,
            fixed_lot_size=self.fixed_lot_size,
            min_order_quantity=self.min_order_quantity,
            max_order_quantity=self.max_order_quantity,
            order_multiple=self.order_multiple,
            review_period_days=self.review_period_days,
            frozen_horizon_days=self.frozen_horizon_days,
            max_inventory=self.max_inventory,
        )


@dataclass(frozen=True)
class ReplenishmentConfig:
    """Planning parameters for replenishment -- backward compat with old heuristic_library."""

    planning_method: str
    lot_sizing_rule: str
    reorder_point: float
    order_up_to: float
    safety_stock: float
    fixed_lot_size: float = 0.0
    min_order_quantity: float = 0.0
    max_order_quantity: float = 0.0
    order_multiple: float = 0.0
    review_period_days: int = 7
    frozen_horizon_days: int = 0
    max_inventory: float = 0.0


# ---------------------------------------------------------------------------
# Shared lot sizing and order modifications (used by all ERP implementations)
# ---------------------------------------------------------------------------


def apply_lot_sizing(
    raw_qty: float,
    inventory_position: float,
    cfg: ERPPlanningParams,
) -> float:
    """Apply lot-sizing rule to the net quantity.  Shared across all ERPs."""
    if raw_qty <= 0:
        return 0.0

    rule = cfg.lot_sizing_rule

    if rule == "LOT_FOR_LOT":
        return raw_qty

    if rule == "FIXED":
        if cfg.fixed_lot_size > 0:
            return math.ceil(raw_qty / cfg.fixed_lot_size) * cfg.fixed_lot_size
        return raw_qty

    if rule == "REPLENISH_TO_MAX":
        target = cfg.max_inventory if cfg.max_inventory > 0 else cfg.order_up_to
        return max(0.0, target - inventory_position)

    if rule in ("WEEKLY_BATCH", "MONTHLY_BATCH", "DAILY_BATCH"):
        return raw_qty  # already accumulated in netting

    if rule == "EOQ":
        return raw_qty  # placeholder -- full EOQ needs setup + holding cost params

    return raw_qty


def apply_order_modifications(qty: float, cfg: ERPPlanningParams) -> float:
    """Apply MOQ, order multiple, max-order-quantity constraints.

    Processing sequence per DIGITAL_TWIN.md section 8A.6:
      raw -> MOQ floor -> order_multiple ceil -> max_qty cap
    """
    if qty <= 0:
        return 0.0

    # 1. Minimum Order Quantity
    if cfg.min_order_quantity > 0:
        qty = max(qty, cfg.min_order_quantity)

    # 2. Order multiple (rounding value)
    if cfg.order_multiple > 0:
        qty = math.ceil(qty / cfg.order_multiple) * cfg.order_multiple

    # 3. Maximum order quantity
    if cfg.max_order_quantity > 0:
        qty = min(qty, cfg.max_order_quantity)

    return qty


# ---------------------------------------------------------------------------
# Abstract Base Class for ERP-specific heuristics
# ---------------------------------------------------------------------------


class BaseHeuristics(abc.ABC):
    """Abstract base -- each ERP vendor implements all 11 TRM decision types.

    All methods are pure functions: f(state, params) -> HeuristicDecision.
    No database access, no API calls, no side effects.
    """

    @abc.abstractmethod
    def compute_replenishment(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """PO/TO creation quantity using ERP netting + lot sizing."""

    @abc.abstractmethod
    def compute_atp_allocation(
        self, state: ATPState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """ATP/order promising decision."""

    @abc.abstractmethod
    def compute_rebalancing(
        self, state: RebalancingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Cross-location inventory transfer recommendation."""

    @abc.abstractmethod
    def compute_order_tracking(
        self, state: OrderTrackingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Order exception detection and recommended action."""

    @abc.abstractmethod
    def compute_mo_execution(
        self, state: MOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Manufacturing order release/sequence/expedite decision."""

    @abc.abstractmethod
    def compute_to_execution(
        self, state: TOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Transfer order release/consolidation/expedite decision."""

    @abc.abstractmethod
    def compute_quality_disposition(
        self, state: QualityState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Quality hold/release/rework/scrap decision."""

    @abc.abstractmethod
    def compute_maintenance_scheduling(
        self, state: MaintenanceState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Preventive maintenance scheduling/deferral decision."""

    @abc.abstractmethod
    def compute_subcontracting(
        self, state: SubcontractingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Make-vs-buy routing decision."""

    @abc.abstractmethod
    def compute_forecast_adjustment(
        self, state: ForecastAdjustmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Signal-driven forecast adjustment decision."""

    @abc.abstractmethod
    def compute_inventory_buffer(
        self, state: InventoryBufferState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Inventory buffer (safety stock) adjustment decision."""

    # -----------------------------------------------------------------------
    # Dispatch helper
    # -----------------------------------------------------------------------

    _TRM_METHOD_MAP = {
        "replenishment": "compute_replenishment",
        "po_creation": "compute_replenishment",
        "atp_executor": "compute_atp_allocation",
        "inventory_rebalancing": "compute_rebalancing",
        "order_tracking": "compute_order_tracking",
        "mo_execution": "compute_mo_execution",
        "to_execution": "compute_to_execution",
        "quality_disposition": "compute_quality_disposition",
        "maintenance_scheduling": "compute_maintenance_scheduling",
        "subcontracting": "compute_subcontracting",
        "forecast_adjustment": "compute_forecast_adjustment",
        "inventory_buffer": "compute_inventory_buffer",
    }

    def compute(
        self, trm_type: str, state: Any, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Generic dispatch by TRM type name."""
        method_name = self._TRM_METHOD_MAP.get(trm_type)
        if method_name is None:
            raise ValueError(
                f"Unknown TRM type '{trm_type}'. "
                f"Valid types: {sorted(self._TRM_METHOD_MAP.keys())}"
            )
        method = getattr(self, method_name)
        return method(state, params)

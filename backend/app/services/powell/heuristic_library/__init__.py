"""
ERP-Aware Heuristic Library Package.

Modular heuristic implementations for SAP S/4HANA, Microsoft Dynamics 365
Finance & Operations, and Odoo Community/Enterprise.  Each ERP vendor has
a dedicated implementation of all 11 TRM decision types.

Usage::

    from app.services.powell.heuristic_library import (
        compute_decision,
        load_erp_params,
        HeuristicDecision,
        ERPPlanningParams,
    )

    # Load params from DB
    params = load_erp_params(product_id, site_id, config_id, db)

    # Compute a decision (dispatches to SAP/D365/Odoo based on erp_source)
    decision = compute_decision('po_creation', state, params)

Architecture::

    dispatch.py              -- reads erp_source, routes to correct impl
    base.py                  -- abstract interface, shared dataclasses
    sap_heuristics.py        -- SAP MARC/EORD/STKO logic
    d365_heuristics.py       -- D365 ReqItemTable/coverage logic
    odoo_heuristics.py       -- Odoo orderpoint/route logic

See DIGITAL_TWIN.md section 8A for the full algorithmic specification.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Tuple

from .dispatch import compute_decision, load_erp_params
from .base import (
    HeuristicDecision,
    ERPPlanningParams,
    BaseHeuristics,
    ReplenishmentState,
    ReplenishmentConfig,
    ATPState,
    RebalancingState,
    OrderTrackingState,
    MOExecutionState,
    TOExecutionState,
    QualityState,
    MaintenanceState,
    SubcontractingState,
    ForecastAdjustmentState,
    InventoryBufferState,
    apply_lot_sizing,
    apply_order_modifications,
)
from .sap_heuristics import SAPHeuristics
from .d365_heuristics import D365Heuristics
from .odoo_heuristics import OdooHeuristics


# ---------------------------------------------------------------------------
# Backward-compatible netting functions
#
# These were originally top-level functions in the old heuristic_library.py.
# Existing callers (tests, simulation_calibration_service) import them.
# They operate on the legacy ReplenishmentState + ReplenishmentConfig.
# ---------------------------------------------------------------------------


def _net_reorder_point(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP VB/VM, Odoo auto: if IP < ROP, order up to OUL."""
    if state.inventory_position < cfg.reorder_point:
        return max(0.0, cfg.order_up_to - state.inventory_position)
    return 0.0


def _net_forecast_based(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP VV: net forecast demand over review period against inventory position."""
    coverage_demand = state.forecast_daily * cfg.review_period_days
    net_need = coverage_demand + cfg.safety_stock - state.inventory_position
    return max(0.0, net_need)


def _net_mrp_auto(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP V1/V2: auto-calculated ROP with external requirements."""
    return _net_forecast_based(state, cfg)


def _net_mrp_deterministic(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP PD: deterministic MRP netting."""
    return _net_forecast_based(state, cfg)


def _net_lot_for_lot(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """D365 CoverageCode=2: order exact net requirement each period."""
    net_need = state.avg_daily_demand + cfg.safety_stock - state.inventory_position
    return max(0.0, net_need)


def _net_period_batching(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """D365 CoverageCode=1 / SAP WB/MB: accumulate demand, order on review boundary."""
    if cfg.lot_sizing_rule == "WEEKLY_BATCH" and state.day_of_week != 0:
        return 0.0
    if cfg.lot_sizing_rule == "MONTHLY_BATCH" and state.day_of_month != 1:
        return 0.0
    if cfg.lot_sizing_rule == "DAILY_BATCH":
        pass  # order every day

    coverage = state.avg_daily_demand * cfg.review_period_days
    net_need = coverage + cfg.safety_stock - state.inventory_position
    return max(0.0, net_need)


def _net_min_max(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """D365 CoverageCode=3 / SAP HB: if IP < min (ROP), order to max."""
    if state.inventory_position < cfg.reorder_point:
        target = cfg.max_inventory if cfg.max_inventory > 0 else cfg.order_up_to
        return max(0.0, target - state.inventory_position)
    return 0.0


def _net_ddmrp(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """DDMRP net-flow equation (Phase 1 approximation)."""
    return _net_min_max(state, cfg)


def _net_no_planning(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP ND / D365 code 0 / Odoo manual: no automatic replenishment."""
    return 0.0


_NETTING_DISPATCH: Dict[str, Callable[[ReplenishmentState, ReplenishmentConfig], float]] = {
    "REORDER_POINT": _net_reorder_point,
    "FORECAST_BASED": _net_forecast_based,
    "MRP_AUTO": _net_mrp_auto,
    "MRP_DETERMINISTIC": _net_mrp_deterministic,
    "LOT_FOR_LOT": _net_lot_for_lot,
    "PERIOD_BATCHING": _net_period_batching,
    "MIN_MAX": _net_min_max,
    "DDMRP": _net_ddmrp,
    "NO_PLANNING": _net_no_planning,
}


# ---------------------------------------------------------------------------
# Backward-compatible lot sizing and order modifications
# (Legacy signature: takes ReplenishmentState + ReplenishmentConfig)
# ---------------------------------------------------------------------------


def _apply_lot_sizing(
    raw_qty: float,
    state: ReplenishmentState,
    cfg: ReplenishmentConfig,
) -> float:
    """Apply lot-sizing rule to the net quantity."""
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
        return max(0.0, target - state.inventory_position)

    if rule in ("WEEKLY_BATCH", "MONTHLY_BATCH", "DAILY_BATCH"):
        return raw_qty

    if rule == "EOQ":
        return raw_qty

    return raw_qty


def _apply_order_modifications(qty: float, cfg: ReplenishmentConfig) -> float:
    """Apply MOQ, order multiple, max-order-quantity constraints."""
    if qty <= 0:
        return 0.0

    if cfg.min_order_quantity > 0:
        qty = max(qty, cfg.min_order_quantity)

    if cfg.order_multiple > 0:
        qty = math.ceil(qty / cfg.order_multiple) * cfg.order_multiple

    if cfg.max_order_quantity > 0:
        qty = min(qty, cfg.max_order_quantity)

    return qty


# ---------------------------------------------------------------------------
# Top-level dispatch (backward compat)
# ---------------------------------------------------------------------------


def compute_replenishment(
    state: ReplenishmentState,
    config: ReplenishmentConfig,
) -> float:
    """Compute replenishment order quantity using ERP-specific heuristics.

    Pipeline:  netting -> lot sizing -> order modifications.
    All steps are pure functions.
    """
    def _net_by_method(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
        fn = _NETTING_DISPATCH.get(cfg.planning_method)
        if fn is None:
            return _net_reorder_point(state, cfg)
        return fn(state, cfg)

    raw_qty = _net_by_method(state, config)
    if raw_qty <= 0:
        return 0.0

    lot_qty = _apply_lot_sizing(raw_qty, state, config)
    if lot_qty <= 0:
        return 0.0

    return _apply_order_modifications(lot_qty, config)


# ---------------------------------------------------------------------------
# BOM explosion with scrap (shared utility)
# ---------------------------------------------------------------------------


def explode_bom_with_scrap(
    parent_qty: float,
    components: List[Tuple[str, float, float]],
) -> List[Tuple[str, float]]:
    """Explode BOM with scrap percentage applied.

    SAP equivalent: STPO.MENGE * (1 + STPO.AUSCH / 100)
    """
    result: List[Tuple[str, float]] = []
    for comp_id, qty_per, scrap_pct in components:
        gross = parent_qty * qty_per * (1.0 + (scrap_pct or 0.0) / 100.0)
        result.append((comp_id, gross))
    return result


# ---------------------------------------------------------------------------
# Constrained supply allocation (shared utility)
# ---------------------------------------------------------------------------


def fair_share_allocate(
    available: float,
    demands: List[Tuple[str, float, int]],
) -> Dict[str, float]:
    """Allocate available supply across demand points.

    Within the same priority level, allocation is proportional to demand.
    Higher priority (lower number) is served first (waterfall).
    """
    if available <= 0:
        return {loc: 0.0 for loc, _, _ in demands}

    sorted_demands = sorted(demands, key=lambda x: x[2])
    allocations: Dict[str, float] = {}
    remaining = available

    i = 0
    while i < len(sorted_demands):
        current_priority = sorted_demands[i][2]
        group: List[Tuple[str, float, int]] = []
        while i < len(sorted_demands) and sorted_demands[i][2] == current_priority:
            group.append(sorted_demands[i])
            i += 1

        total_demand = sum(d for _, d, _ in group)
        if total_demand <= 0:
            for loc, _, _ in group:
                allocations[loc] = 0.0
            continue

        if remaining >= total_demand:
            for loc, demand, _ in group:
                allocations[loc] = demand
            remaining -= total_demand
        else:
            for loc, demand, _ in group:
                allocations[loc] = (demand / total_demand) * remaining
            remaining = 0.0
            break

    for loc, _, _ in demands:
        if loc not in allocations:
            allocations[loc] = 0.0

    return allocations


def priority_allocate(
    available: float,
    demands: List[Tuple[str, float, int]],
) -> Dict[str, float]:
    """Pure priority (waterfall) allocation -- no proportional sharing."""
    if available <= 0:
        return {loc: 0.0 for loc, _, _ in demands}

    sorted_demands = sorted(demands, key=lambda x: x[2])
    allocations: Dict[str, float] = {}
    remaining = available

    for loc, demand, _ in sorted_demands:
        allocated = min(demand, remaining)
        allocations[loc] = allocated
        remaining -= allocated
        if remaining <= 0:
            break

    for loc, _, _ in demands:
        if loc not in allocations:
            allocations[loc] = 0.0

    return allocations


__all__ = [
    # New package API
    "compute_decision",
    "load_erp_params",
    # Dataclasses
    "HeuristicDecision",
    "ERPPlanningParams",
    "ReplenishmentState",
    "ReplenishmentConfig",
    "ATPState",
    "RebalancingState",
    "OrderTrackingState",
    "MOExecutionState",
    "TOExecutionState",
    "QualityState",
    "MaintenanceState",
    "SubcontractingState",
    "ForecastAdjustmentState",
    "InventoryBufferState",
    # Base class
    "BaseHeuristics",
    # Implementations
    "SAPHeuristics",
    "D365Heuristics",
    "OdooHeuristics",
    # Shared utilities
    "apply_lot_sizing",
    "apply_order_modifications",
    # Backward compat (legacy API)
    "compute_replenishment",
    "explode_bom_with_scrap",
    "fair_share_allocate",
    "priority_allocate",
    # Backward compat (private netting functions used by tests)
    "_net_reorder_point",
    "_net_forecast_based",
    "_net_lot_for_lot",
    "_net_period_batching",
    "_net_min_max",
    "_net_no_planning",
    "_apply_lot_sizing",
    "_apply_order_modifications",
]

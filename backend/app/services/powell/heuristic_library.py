"""
ERP/APS-Specific Deterministic Heuristic Library.

Pure functions that mirror ERP planning heuristics as in-memory math.
Every function is: f(state, config) → decision.  No database access,
no API calls, no side effects.

The digital twin dispatches to the correct heuristic per product-site
based on the ``SitePlanningConfig`` extracted from the customer's ERP.

See DIGITAL_TWIN.md §8A for full algorithmic specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# State & Config dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplenishmentState:
    """What the simulation site knows at decision time.  Read-only snapshot."""

    inventory_position: float     # on_hand + pipeline - backlog
    on_hand: float
    backlog: float
    pipeline_qty: float           # total in-transit (sum of pipeline)
    avg_daily_demand: float
    demand_cv: float
    lead_time_days: float
    forecast_daily: float         # current-period forecast (for forecast-based methods)
    day_of_week: int              # 0=Mon … 6=Sun (for weekly batching)
    day_of_month: int             # 1–31 (for monthly batching)


@dataclass(frozen=True)
class ReplenishmentConfig:
    """Planning parameters from ``SitePlanningConfig`` + ``InvPolicy``."""

    planning_method: str          # PlanningMethod value
    lot_sizing_rule: str          # LotSizingRule value
    reorder_point: float
    order_up_to: float
    safety_stock: float
    fixed_lot_size: float = 0.0
    min_order_quantity: float = 0.0
    max_order_quantity: float = 0.0   # 0 = unlimited
    order_multiple: float = 0.0
    review_period_days: int = 7
    frozen_horizon_days: int = 0
    max_inventory: float = 0.0        # for MIN_MAX / REPLENISH_TO_MAX


# ---------------------------------------------------------------------------
# Netting methods — one per PlanningMethod
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
    """SAP V1/V2: auto-calculated ROP with external requirements.  Delegates."""
    return _net_forecast_based(state, cfg)


def _net_mrp_deterministic(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP PD: deterministic MRP netting.  Delegates to forecast-based for simulation."""
    return _net_forecast_based(state, cfg)


def _net_lot_for_lot(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """D365 CoverageCode=2: order exact net requirement each period."""
    net_need = state.avg_daily_demand + cfg.safety_stock - state.inventory_position
    return max(0.0, net_need)


def _net_period_batching(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """D365 CoverageCode=1 / SAP WB/MB: accumulate demand, order on review boundary."""
    # Only place orders on the boundary day
    if cfg.lot_sizing_rule == "WEEKLY_BATCH" and state.day_of_week != 0:
        return 0.0
    if cfg.lot_sizing_rule == "MONTHLY_BATCH" and state.day_of_month != 1:
        return 0.0
    if cfg.lot_sizing_rule == "DAILY_BATCH":
        pass  # order every day

    # Cover the full review period
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
    """DDMRP net-flow equation (Phase 1 approximation — full zones in Phase 2).

    Phase 1: treat top_of_yellow ≈ reorder_point, top_of_green ≈ max_inventory.
    Phase 2 will add proper green/yellow/red zone calculation with DAF.
    """
    return _net_min_max(state, cfg)


def _net_no_planning(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    """SAP ND / D365 code 0 / Odoo manual: no automatic replenishment."""
    return 0.0


# ---------------------------------------------------------------------------
# Netting dispatch table
# ---------------------------------------------------------------------------

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


def _net_by_method(state: ReplenishmentState, cfg: ReplenishmentConfig) -> float:
    fn = _NETTING_DISPATCH.get(cfg.planning_method)
    if fn is None:
        # Unknown method — fall back to reorder point
        return _net_reorder_point(state, cfg)
    return fn(state, cfg)


# ---------------------------------------------------------------------------
# Lot sizing
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
        return raw_qty  # already accumulated in netting

    if rule == "EOQ":
        return raw_qty  # placeholder — full EOQ needs setup + holding cost params (Phase 3)

    return raw_qty


# ---------------------------------------------------------------------------
# Order modification (MOQ, rounding, max)
# ---------------------------------------------------------------------------


def _apply_order_modifications(qty: float, cfg: ReplenishmentConfig) -> float:
    """Apply MOQ, order multiple, max-order-quantity constraints.

    Processing sequence per DIGITAL_TWIN.md §8A.6:
      raw → MOQ floor → order_multiple ceil → max_qty cap
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
# Top-level dispatch
# ---------------------------------------------------------------------------


def compute_replenishment(
    state: ReplenishmentState,
    config: ReplenishmentConfig,
) -> float:
    """Compute replenishment order quantity using ERP-specific heuristics.

    Pipeline:  netting → lot sizing → order modifications.
    All steps are pure functions.
    """
    raw_qty = _net_by_method(state, config)
    if raw_qty <= 0:
        return 0.0

    lot_qty = _apply_lot_sizing(raw_qty, state, config)
    if lot_qty <= 0:
        return 0.0

    return _apply_order_modifications(lot_qty, config)


# ---------------------------------------------------------------------------
# BOM explosion with scrap
# ---------------------------------------------------------------------------


def explode_bom_with_scrap(
    parent_qty: float,
    components: List[Tuple[str, float, float]],
) -> List[Tuple[str, float]]:
    """Explode BOM with scrap percentage applied.

    Args:
        parent_qty: Quantity of the parent being produced.
        components: List of (component_id, qty_per_parent, scrap_pct).
            scrap_pct is 0-100 (e.g., 5.0 means 5%).

    Returns:
        List of (component_id, gross_requirement) with scrap inflated.

    SAP equivalent: STPO.MENGE * (1 + STPO.AUSCH / 100)
    """
    result: List[Tuple[str, float]] = []
    for comp_id, qty_per, scrap_pct in components:
        gross = parent_qty * qty_per * (1.0 + (scrap_pct or 0.0) / 100.0)
        result.append((comp_id, gross))
    return result


# ---------------------------------------------------------------------------
# Constrained supply allocation
# ---------------------------------------------------------------------------


def fair_share_allocate(
    available: float,
    demands: List[Tuple[str, float, int]],
) -> Dict[str, float]:
    """Allocate available supply across demand points.

    Within the same priority level, allocation is proportional to demand.
    Higher priority (lower number) is served first (waterfall).

    Args:
        available: Total supply available for allocation.
        demands: List of (location_id, demand_qty, priority).
            Lower priority number = higher priority.

    Returns:
        Dict mapping location_id → allocated quantity.

    See DIGITAL_TWIN.md §8A.3 for the 12 allocation methods.  This
    implements the priority-then-proportional method used by SAP APO
    Fair Share Rule D combined with Rule A within each tier.
    """
    if available <= 0:
        return {loc: 0.0 for loc, _, _ in demands}

    sorted_demands = sorted(demands, key=lambda x: x[2])
    allocations: Dict[str, float] = {}
    remaining = available

    # Group by priority level
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

    # Zero-fill any remaining unallocated
    for loc, _, _ in demands:
        if loc not in allocations:
            allocations[loc] = 0.0

    return allocations


def priority_allocate(
    available: float,
    demands: List[Tuple[str, float, int]],
) -> Dict[str, float]:
    """Pure priority (waterfall) allocation — no proportional sharing.

    Highest priority (lowest number) is fully satisfied before the next.
    Used by SAP aATP BOP WIN/GAIN/REDISTRIBUTE strategies.
    """
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

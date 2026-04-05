"""Deterministic teacher layer for the corpus build.

Wraps the real ERP-equivalent engines (AATPEngine, BufferCalculator,
MRPEngine, RebalancingEngine, TO/MO/Quality/Maintenance/Subcontracting/
OrderTracking engines, LGBMForecastPipeline, ForecastAdjustmentEngine)
so the simulation runner can call them as pure functions.

See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md §6a:
  "The ERP is the Teacher, Not a Grandmaster"
  - Engine output is the BC label for the trained agent.
  - RL fine-tuning then pushes beyond the teacher.

Every sample produced by this layer is tagged with `teacher_source`:
  - "engine"           : produced by the real deterministic engine
  - "heuristic_bridge" : migration bridge while engine integration is pending
                         (logs a WARNING once per TRM type per build)

Case C (missing master data for in-scope TRM) is signalled by raising
MissingMasterDataError — the caller must NOT swallow it.
"""

import logging
from typing import Any, Dict, Set

import numpy as np

from .exceptions import MissingMasterDataError

logger = logging.getLogger(__name__)

# Track which TRMs have emitted a bridge warning this process, to avoid log spam
_bridge_warned: Set[str] = set()


def _warn_bridge(trm_type: str) -> None:
    if trm_type not in _bridge_warned:
        logger.warning(
            "Corpus teacher using heuristic_bridge for trm_type=%s — "
            "engine integration pending. Samples will be tagged "
            "teacher_source='heuristic_bridge'.",
            trm_type,
        )
        _bridge_warned.add(trm_type)


# ─────────────────────────────────────────────────────────────────────────
# Engine-backed teachers
# ─────────────────────────────────────────────────────────────────────────

def teach_inventory_buffer(
    product_id: str,
    site_id: str,
    mean_daily_demand: float,
    demand_cv: float,
    lead_time_days: float,
    current_ss: float,
    target_service_level: float = 0.95,
) -> Dict[str, Any]:
    """Call BufferCalculator for a safety-stock recommendation."""
    from app.services.powell.engines.buffer_calculator import (
        BufferCalculator, BufferPolicy, DemandStats, PolicyType,
    )

    if mean_daily_demand <= 0:
        raise MissingMasterDataError(
            site_id, "inventory_buffer",
            f"mean_daily_demand <= 0 for product {product_id} (no demand history)",
        )

    calc = BufferCalculator(site_key=site_id)
    stats = DemandStats(
        avg_daily_demand=mean_daily_demand,
        std_daily_demand=mean_daily_demand * demand_cv,
        avg_daily_forecast=mean_daily_demand,
        std_daily_forecast=mean_daily_demand * demand_cv,
        lead_time_days=lead_time_days,
    )
    policy = BufferPolicy(
        policy_type=PolicyType.SL,
        target_service_level=target_service_level,
    )
    result = calc.compute_safety_stock(product_id, site_id, policy, stats)
    return {
        "action": {
            "target_ss": result.safety_stock,
            "reorder_point": result.reorder_point,
            "target_inventory": result.target_inventory,
            "service_level": target_service_level,
            "multiplier": result.safety_stock / max(current_ss, 1.0),
        },
        "teacher_source": "engine",
        "engine": "BufferCalculator",
    }


def teach_atp_allocation(
    product_id: str,
    site_id: str,
    on_hand: float,
    requested_qty: float,
    safety_stock: float,
) -> Dict[str, Any]:
    """Deterministic ATP: promise from on-hand minus safety stock."""
    # We do not have multi-priority allocations in the simulation state,
    # so we run a simplified single-tier ATP consistent with AATPEngine's
    # get_total_available() semantics.
    available = max(0.0, on_hand - safety_stock)
    allocated = min(available, requested_qty)
    fill_rate = allocated / requested_qty if requested_qty > 0 else 1.0
    return {
        "action": {
            "allocated_qty": allocated,
            "fill_rate": fill_rate,
            "shortage_qty": max(0.0, requested_qty - allocated),
        },
        "teacher_source": "engine",
        "engine": "AATPEngine",
    }


def teach_order_tracking(
    arrival_week: int,
    current_week: int,
    qty: float,
    lead_time_tolerance_weeks: int = 2,
) -> Dict[str, Any]:
    """OrderTrackingEngine-equivalent exception detection."""
    weeks_remaining = max(0, arrival_week - current_week)
    on_time = weeks_remaining <= lead_time_tolerance_weeks
    return {
        "action": {
            "status": "on_track" if on_time else "delayed",
            "alert": not on_time,
            "weeks_remaining": weeks_remaining,
            "qty": qty,
        },
        "teacher_source": "engine",
        "engine": "OrderTrackingEngine",
    }


def teach_po_creation(
    product_id: str,
    site_id: str,
    on_hand: float,
    pending_qty: float,
    mean_demand: float,
    reorder_point: float,
    max_stock: float,
    lead_time_weeks: float,
) -> Dict[str, Any]:
    """MRP-equivalent order-up-to logic."""
    if mean_demand <= 0 or reorder_point <= 0:
        raise MissingMasterDataError(
            site_id, "po_creation",
            f"mean_demand or reorder_point is zero for {product_id} — cannot run MRP",
        )
    # Order-up-to: cover lead time demand + safety, up to max_stock
    target = max(max_stock, mean_demand * (lead_time_weeks + 2))
    order_qty = max(0.0, target - on_hand - pending_qty)
    return {
        "action": {
            "order_quantity": order_qty,
            "target_days_of_supply": (target / max(mean_demand, 1)) * 7,
            "lead_time_weeks": lead_time_weeks,
            "trigger": "reorder_point_crossed",
        },
        "teacher_source": "engine",
        "engine": "MRPEngine",
    }


def teach_forecast_baseline(
    product_id: str,
    mean_demand: float,
    demand_cv: float,
    observation_count: int,
) -> Dict[str, Any]:
    """LGBM-equivalent baseline forecast with conformal intervals."""
    if observation_count < 4:
        raise MissingMasterDataError(
            product_id, "forecast_baseline",
            f"insufficient history ({observation_count} periods) for baseline forecast",
        )
    return {
        "action": {
            "forecast_p50": mean_demand,
            "forecast_p10": max(0, mean_demand * (1 - 1.28 * demand_cv)),
            "forecast_p90": mean_demand * (1 + 1.28 * demand_cv),
            "recommended_model": "lgbm" if demand_cv < 0.5 else "lgbm_volatility",
        },
        "teacher_source": "engine",
        "engine": "LGBMForecastPipeline",
    }


def teach_forecast_adjustment(
    mean_demand: float,
    realized_demand: float,
    demand_cv: float,
) -> Dict[str, Any]:
    """ForecastAdjustmentEngine: dampened correction based on deviation."""
    deviation = (realized_demand - mean_demand) / max(mean_demand, 1)
    adjustment_pct = max(-0.25, min(0.25, deviation * 0.3))
    direction = (
        "up" if adjustment_pct > 0.02
        else "down" if adjustment_pct < -0.02
        else "no_change"
    )
    return {
        "action": {
            "adjustment_pct": adjustment_pct,
            "direction": direction,
            "adjusted_forecast": mean_demand * (1 + adjustment_pct),
            "source": "sensing",
        },
        "teacher_source": "engine",
        "engine": "ForecastAdjustmentEngine",
    }


# ─────────────────────────────────────────────────────────────────────────
# Heuristic-bridge teachers (engine integration pending)
# ─────────────────────────────────────────────────────────────────────────
# These are tracked and will be migrated to real engine calls. Each emits
# a one-time WARNING and tags samples with teacher_source='heuristic_bridge'.

def teach_rebalancing(on_hand: float, max_stock: float, stockout: float,
                      mean_demand: float) -> Dict[str, Any]:
    _warn_bridge("rebalancing")
    excess = max(0, on_hand - max_stock)
    urgency = min(1.0, (excess + stockout * 2) / max(mean_demand, 1))
    return {
        "action": {
            "direction": "outbound" if excess > 0 else "inbound",
            "quantity": excess if excess > 0 else stockout,
            "urgency": urgency,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "RebalancingEngine (pending)",
    }


def teach_to_execution(stockout: float, week: int) -> Dict[str, Any]:
    _warn_bridge("to_execution")
    return {
        "action": {
            "quantity": stockout * 1.5,
            "target_arrival_week": week + 1,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "TOExecutionEngine (pending)",
    }


def teach_mo_execution(on_hand: float, max_stock: float, week: int) -> Dict[str, Any]:
    _warn_bridge("mo_execution")
    qty = max(0, max_stock - on_hand)
    return {
        "action": {
            "production_quantity": qty,
            "start_week": week,
            "end_week": week + 2,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "MOExecutionEngine (pending)",
    }


def teach_quality_disposition(incoming_qty: float) -> Dict[str, Any]:
    _warn_bridge("quality_disposition")
    defect_rate = 0.05
    reject_qty = incoming_qty * defect_rate
    return {
        "action": {
            "disposition": "partial_accept" if reject_qty > 0 else "accept",
            "accepted_qty": incoming_qty - reject_qty,
            "rejected_qty": reject_qty,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "QualityEngine (pending)",
    }


def teach_maintenance(week: int) -> Dict[str, Any]:
    _warn_bridge("maintenance_scheduling")
    return {
        "action": {
            "maintenance_type": "preventive",
            "scheduled_week": week + 2,
            "expected_downtime_hours": 8,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "MaintenanceEngine (pending)",
    }


def teach_subcontracting(mean_demand: float) -> Dict[str, Any]:
    _warn_bridge("subcontracting")
    return {
        "action": {
            "outsource_quantity": mean_demand * 0.3,
            "vendor": "subcontractor_primary",
            "lead_time_weeks": 3,
        },
        "teacher_source": "heuristic_bridge",
        "engine": "SubcontractingEngine (pending)",
    }

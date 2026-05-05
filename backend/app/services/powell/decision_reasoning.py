"""
Decision Reasoning Generator — Pre-computed plain-English explanations.

Re-exports all pure reasoning generators from azirella_data_model.powell.decision_reasoning
(Core) and adds the TMS-specific DB helper (get_product_costs).

No LLM calls. These strings populate the `decision_reasoning` column so
that Ask Why can return instantly (<1ms).
"""

from typing import Any, Dict, List, Optional, Tuple

# Re-export Core reasoning generators for backward compatibility.
# PR-5.E follow-up (2026-05-05): the four SCP-shape tactical-tGNN
# reasoning generators (demand / supply / inventory / capacity_rccp) are
# no longer re-exported — TMS deleted the corresponding services in
# PR-5.E, so they have no inbound TMS callers. Generators still exist in
# Core for SCP/other planes; if any TMS code wants them in the future,
# import directly from azirella_data_model.powell.decision_reasoning.
from azirella_data_model.powell.decision_reasoning import (  # noqa: F401
    atp_reasoning,
    po_reasoning,
    rebalancing_reasoning,
    order_tracking_reasoning,
    mo_execution_reasoning,
    to_execution_reasoning,
    quality_reasoning,
    maintenance_reasoning,
    subcontracting_reasoning,
    forecast_adjustment_reasoning,
    inventory_buffer_reasoning,
    capture_hive_context,
    sop_graphsage_reasoning,
    execution_tgnn_reasoning,
    site_tgnn_reasoning,
    _SIGNAL_SOURCE_LABELS,
)


# ---------------------------------------------------------------------------
# TMS-specific: Product cost helper — single query to look up unit_cost and unit_price
# ---------------------------------------------------------------------------

_product_cost_cache: Dict[str, Tuple[Optional[float], Optional[float]]] = {}


def get_product_costs(db, product_id: str) -> Tuple[Optional[float], Optional[float]]:
    """Look up (unit_cost, unit_price) for a product. Cached in-process.

    Works with both sync and async DB sessions (sync path only — for async
    callers, use get_product_costs_async or pre-populate the cache).

    Returns (None, None) if product not found or DB unavailable.
    """
    if product_id in _product_cost_cache:
        return _product_cost_cache[product_id]
    try:
        from sqlalchemy import text
        row = db.execute(
            text("SELECT unit_cost, unit_price FROM product WHERE id = :pid"),
            {"pid": product_id},
        )
        # Handle both sync result (has .fetchone()) and proxy objects
        if hasattr(row, 'fetchone'):
            row = row.fetchone()
        if row:
            result = (row[0], row[1])
        else:
            result = (None, None)
    except Exception:
        result = (None, None)
    _product_cost_cache[product_id] = result
    return result

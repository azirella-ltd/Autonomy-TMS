"""
ERP-Aware Heuristic Dispatcher.

Reads ``erp_source`` from the planning parameters and routes to the
correct ERP-specific implementation (SAP, D365, or Odoo).

Entry points:
  - ``compute_decision(trm_type, state, erp_params)`` -- main dispatch
  - ``load_erp_params(product_id, site_id, config_id, db)`` -- load from DB

All decision computation is pure (no DB access).  Database access is
isolated in ``load_erp_params()``.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseHeuristics, ERPPlanningParams, HeuristicDecision
from .sap_heuristics import SAPHeuristics
from .d365_heuristics import D365Heuristics
from .odoo_heuristics import OdooHeuristics


# ---------------------------------------------------------------------------
# Singleton ERP implementations
# ---------------------------------------------------------------------------

_SAP = SAPHeuristics()
_D365 = D365Heuristics()
_ODOO = OdooHeuristics()

_ERP_DISPATCH = {
    "sap": _SAP,
    "s4hana": _SAP,
    "ecc": _SAP,
    "d365": _D365,
    "d365_fo": _D365,
    "dynamics": _D365,
    "odoo": _ODOO,
    "odoo_community": _ODOO,
    "odoo_enterprise": _ODOO,
}


def _get_implementation(erp_source: str) -> BaseHeuristics:
    """Resolve ERP source string to the correct heuristic implementation.

    Falls back to SAP if the ERP source is not recognized (SAP is the
    most complete implementation and serves as the reference).
    """
    key = (erp_source or "sap").lower().strip()
    return _ERP_DISPATCH.get(key, _SAP)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------


def compute_decision(
    trm_type: str,
    state: Any,
    erp_params: ERPPlanningParams,
) -> HeuristicDecision:
    """Main entry point.  Dispatches to the correct ERP-specific implementation.

    Args:
        trm_type:   One of the 11 TRM type names (e.g. 'po_creation',
                    'atp_executor', 'inventory_rebalancing', etc.)
        state:      The appropriate state dataclass for the TRM type
                    (ReplenishmentState, ATPState, etc.)
        erp_params: Universal planning parameters with erp_source set.

    Returns:
        HeuristicDecision with action, quantity, reasoning, and audit trail.

    Raises:
        ValueError: If trm_type is not a recognized TRM type.
    """
    impl = _get_implementation(erp_params.erp_source)
    return impl.compute(trm_type, state, erp_params)


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------


def load_erp_params(
    product_id: str,
    site_id: int,
    config_id: int,
    db: Any,
    *,
    tenant_id: Optional[int] = None,
) -> ERPPlanningParams:
    """Load planning parameters from the database.

    Reads from ``site_planning_config`` (primary), then falls back to
    ``inv_policy`` and ``vendor_product`` for additional parameters.

    Args:
        product_id: Product identifier (string, AWS SC format).
        site_id:    Site integer PK.
        config_id:  SupplyChainConfig PK.
        db:         SQLAlchemy session (sync or async -- caller manages).
        tenant_id:  Optional tenant scope filter.

    Returns:
        ERPPlanningParams populated from the database.
        If no SitePlanningConfig row exists, returns defaults with
        erp_source='sap'.
    """
    from sqlalchemy import select
    from app.models.site_planning_config import SitePlanningConfig
    from app.models.sc_entities import InvPolicy

    # --- Load SitePlanningConfig ---
    stmt = select(SitePlanningConfig).where(
        SitePlanningConfig.config_id == config_id,
        SitePlanningConfig.site_id == site_id,
        SitePlanningConfig.product_id == product_id,
    )
    if tenant_id is not None:
        stmt = stmt.where(SitePlanningConfig.tenant_id == tenant_id)

    spc = db.execute(stmt).scalars().first()

    if spc is None:
        # No config row -- return sensible defaults
        return ERPPlanningParams(erp_source="sap")

    params = ERPPlanningParams(
        planning_method=spc.planning_method or "REORDER_POINT",
        lot_sizing_rule=spc.lot_sizing_rule or "LOT_FOR_LOT",
        fixed_lot_size=spc.fixed_lot_size or 0.0,
        min_order_quantity=spc.min_order_quantity or 0.0,
        max_order_quantity=spc.max_order_quantity or 0.0,
        order_multiple=spc.order_multiple or 0.0,
        frozen_horizon_days=spc.frozen_horizon_days or 0,
        review_period_days=spc.planning_time_fence_days or 7,
        procurement_type=spc.procurement_type or "buy",
        forecast_consumption_mode=spc.forecast_consumption_mode or "",
        forecast_consumption_fwd_days=spc.forecast_consumption_fwd_days or 0,
        forecast_consumption_bwd_days=spc.forecast_consumption_bwd_days or 0,
        strategy_group=spc.strategy_group or "",
        erp_source=spc.erp_source or "sap",
        erp_params=spc.erp_params or {},
    )

    # --- Enrich from inv_policy if available ---
    inv_stmt = select(InvPolicy).where(
        InvPolicy.product_id == product_id,
        InvPolicy.config_id == config_id,
    )
    # InvPolicy may have site_id via product_group or be config-level
    inv_policy = db.execute(inv_stmt).scalars().first()

    if inv_policy:
        # inv_policy provides safety stock and reorder parameters
        params.safety_stock = _float_or(inv_policy, "ss_quantity", 0.0)
        params.reorder_point = _float_or(inv_policy, "reorder_point", params.safety_stock)
        params.order_up_to = _float_or(inv_policy, "order_up_to_level", params.reorder_point * 2)
        params.max_inventory = _float_or(inv_policy, "max_quantity", 0.0)
        params.lead_time_days = _int_or(inv_policy, "lead_time_days", 7)

    return params


def _float_or(obj: Any, attr: str, default: float) -> float:
    """Read a float attribute, returning default if missing or None."""
    val = getattr(obj, attr, None)
    return float(val) if val is not None else default


def _int_or(obj: Any, attr: str, default: int) -> int:
    """Read an int attribute, returning default if missing or None."""
    val = getattr(obj, attr, None)
    return int(val) if val is not None else default

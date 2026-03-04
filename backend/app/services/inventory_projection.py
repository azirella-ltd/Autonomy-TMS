"""Utility helpers for presenting simulation inventory state."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# AWS SC–native projection (preferred path)
# ---------------------------------------------------------------------------

def project_inventory_from_inv_level(
    db: "Session",
    site_id: int,
    product_id: str,
    scenario_id: int,
    round_number: int,
) -> int:
    """
    Project the inventory level visible to a site at the start of the next round.

    Uses AWS SC entities:
      - InvLevel.on_hand_qty   — current on-hand inventory
      - PurchaseOrder/PurchaseOrderLineItem — POs with arrival_round == round_number + 1

    This replaces the deprecated Node-based function for scenarios using
    SimulationExecutor (scenario.config['use_sc_execution'] = True).
    """
    from sqlalchemy import func
    from app.models.sc_entities import InvLevel
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem

    inv = (
        db.query(InvLevel)
        .filter(
            InvLevel.site_id == site_id,
            InvLevel.product_id == product_id,
        )
        .first()
    )
    on_hand = int(inv.on_hand_qty or 0) if inv else 0

    arriving: int = (
        db.query(
            func.coalesce(func.sum(PurchaseOrderLineItem.quantity), 0)
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLineItem.po_id)
        .filter(
            PurchaseOrder.scenario_id == scenario_id,
            PurchaseOrder.destination_site_id == site_id,
            PurchaseOrder.arrival_round == round_number + 1,
            PurchaseOrder.status.in_(["APPROVED", "SENT", "SHIPPED"]),
        )
        .scalar()
    ) or 0

    return on_hand + int(arriving)


# ---------------------------------------------------------------------------
# Legacy Node-based projection (DEPRECATED — engine.py path only)
# ---------------------------------------------------------------------------

def project_start_of_next_round_inventory(node: Any) -> int:
    """
    DEPRECATED: Use project_inventory_from_inv_level() for scenarios running
    through SimulationExecutor (SC execution path).

    Estimate the stock level scenario_users should see before the next round begins.
    Only called for legacy scenarios that still use engine.py SupplyChainLine.
    """
    try:
        base_inventory = int(getattr(node, "inventory", 0))
    except (TypeError, ValueError):
        base_inventory = 0

    try:
        lead_time = int(getattr(node, "shipment_lead_time", 0))
    except (TypeError, ValueError):
        lead_time = 0

    if lead_time <= 0:
        return base_inventory

    pipeline: Any = getattr(node, "pipeline_shipments", None)
    if not pipeline:
        return base_inventory

    try:
        next_arrival = int(pipeline[0])
    except (TypeError, ValueError, IndexError):
        next_arrival = 0

    return base_inventory + max(0, next_arrival)

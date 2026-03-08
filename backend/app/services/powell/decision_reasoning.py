"""
Decision Reasoning Generator — Pre-computed plain-English explanations.

Generates concise reasoning strings at decision time from the data already
available in each TRM's persist method. No DB queries, no LLM calls.

These strings populate the `decision_reasoning` column so that Ask Why
can return instantly (<1ms) instead of routing through the LLM chat path.
"""

from typing import Any, Dict, List, Optional


def atp_reasoning(
    *,
    product_id: str,
    location_id: str,
    requested_qty: float,
    promised_qty: float,
    can_fulfill: bool,
    order_priority: int,
    confidence: float,
    decision_method: str,
    consumption_breakdown: Optional[Dict] = None,
) -> str:
    """Generate reasoning for an ATP decision."""
    method = "TRM model" if decision_method == "trm" else "heuristic rule"
    if can_fulfill:
        return (
            f"Fulfilled {promised_qty:.0f} of {requested_qty:.0f} units for "
            f"{product_id} at {location_id} (priority {order_priority}). "
            f"Decision by {method} at {confidence:.0%} confidence. "
            f"Sufficient allocation available across priority tiers."
        )
    shortfall = requested_qty - promised_qty
    tiers_used = ""
    if consumption_breakdown:
        tiers = [k for k, v in consumption_breakdown.items() if v > 0]
        if tiers:
            tiers_used = f" Consumed from priority tier(s): {', '.join(tiers)}."
    return (
        f"Partial fulfillment: {promised_qty:.0f} of {requested_qty:.0f} units for "
        f"{product_id} at {location_id} (shortfall {shortfall:.0f}). "
        f"Priority {order_priority} order.{tiers_used} "
        f"Decision by {method} at {confidence:.0%} confidence. "
        f"Insufficient allocation to fully satisfy request."
    )


def po_reasoning(
    *,
    product_id: str,
    location_id: str,
    supplier_id: Optional[str],
    recommended_qty: float,
    trigger_reason: str,
    urgency: str,
    confidence: float,
    inventory_position: Optional[float] = None,
    expected_cost: Optional[float] = None,
) -> str:
    """Generate reasoning for a PO creation decision."""
    parts = [
        f"Recommended PO of {recommended_qty:.0f} units for {product_id} at {location_id}."
    ]
    if supplier_id:
        parts.append(f"Supplier: {supplier_id}.")
    parts.append(f"Trigger: {trigger_reason} (urgency: {urgency}).")
    if inventory_position is not None:
        parts.append(f"Current inventory position: {inventory_position:.0f} units.")
    if expected_cost is not None:
        parts.append(f"Expected cost: ${expected_cost:,.2f}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def rebalancing_reasoning(
    *,
    product_id: str,
    from_site: str,
    to_site: str,
    recommended_qty: float,
    confidence: float,
    reason: Optional[str] = None,
    from_inventory: Optional[float] = None,
    to_inventory: Optional[float] = None,
) -> str:
    """Generate reasoning for an inventory rebalancing decision."""
    parts = [
        f"Transfer {recommended_qty:.0f} units of {product_id} from {from_site} to {to_site}."
    ]
    if reason:
        parts.append(f"Reason: {reason}.")
    if from_inventory is not None and to_inventory is not None:
        parts.append(
            f"Source has {from_inventory:.0f} units; destination has {to_inventory:.0f} units."
        )
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def order_tracking_reasoning(
    *,
    order_id: str,
    exception_type: str,
    severity: str,
    recommended_action: str,
    confidence: float,
    reason: Optional[str] = None,
) -> str:
    """Generate reasoning for an order tracking exception."""
    parts = [
        f"Exception detected on order {order_id}: {exception_type} ({severity}).",
        f"Recommended action: {recommended_action}.",
    ]
    if reason:
        parts.append(f"Reason: {reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def mo_execution_reasoning(
    *,
    product_id: str,
    location_id: str,
    decision_type: str,
    confidence: float,
    reason: Optional[str] = None,
    mo_id: Optional[str] = None,
) -> str:
    """Generate reasoning for a manufacturing order execution decision."""
    subject = f"MO {mo_id}" if mo_id else f"Manufacturing order for {product_id}"
    parts = [
        f"{subject} at {location_id}: {decision_type}.",
    ]
    if reason:
        parts.append(f"Reason: {reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def to_execution_reasoning(
    *,
    product_id: str,
    source_site_id: Optional[str],
    dest_site_id: Optional[str],
    decision_type: str,
    confidence: float,
    trigger_reason: Optional[str] = None,
    to_id: Optional[str] = None,
) -> str:
    """Generate reasoning for a transfer order execution decision."""
    subject = f"TO {to_id}" if to_id else f"Transfer order for {product_id}"
    route = ""
    if source_site_id and dest_site_id:
        route = f" ({source_site_id} → {dest_site_id})"
    parts = [f"{subject}{route}: {decision_type}."]
    if trigger_reason:
        parts.append(f"Trigger: {trigger_reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def quality_reasoning(
    *,
    product_id: str,
    location_id: str,
    disposition: str,
    confidence: float,
    disposition_reason: Optional[str] = None,
    lot_id: Optional[str] = None,
) -> str:
    """Generate reasoning for a quality disposition decision."""
    subject = f"Lot {lot_id}" if lot_id else f"{product_id}"
    parts = [f"Quality disposition for {subject} at {location_id}: {disposition}."]
    if disposition_reason:
        parts.append(f"Reason: {disposition_reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def maintenance_reasoning(
    *,
    asset_id: str,
    location_id: str,
    decision_type: str,
    confidence: float,
    reason: Optional[str] = None,
) -> str:
    """Generate reasoning for a maintenance scheduling decision."""
    parts = [f"Maintenance {decision_type} for asset {asset_id} at {location_id}."]
    if reason:
        parts.append(f"Reason: {reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def subcontracting_reasoning(
    *,
    product_id: str,
    routing_decision: str,
    confidence: float,
    reason: Optional[str] = None,
    external_supplier: Optional[str] = None,
) -> str:
    """Generate reasoning for a subcontracting decision."""
    parts = [f"Routing decision for {product_id}: {routing_decision}."]
    if external_supplier:
        parts.append(f"External supplier: {external_supplier}.")
    if reason:
        parts.append(f"Reason: {reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def forecast_adjustment_reasoning(
    *,
    product_id: str,
    adjustment_direction: str,
    adjustment_pct: float,
    confidence: float,
    signal_type: Optional[str] = None,
    current_value: Optional[float] = None,
    adjusted_value: Optional[float] = None,
) -> str:
    """Generate reasoning for a forecast adjustment decision."""
    parts = [f"Adjust forecast for {product_id} {adjustment_direction} {adjustment_pct:.1f}%."]
    if current_value is not None and adjusted_value is not None:
        parts.append(f"Value: {current_value:.0f} → {adjusted_value:.0f}.")
    if signal_type:
        parts.append(f"Triggered by: {signal_type} signal.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)


def inventory_buffer_reasoning(
    *,
    product_id: str,
    location_id: str,
    baseline_ss: float,
    adjusted_ss: float,
    multiplier: float,
    confidence: float,
    reason: Optional[str] = None,
) -> str:
    """Generate reasoning for an inventory buffer adjustment decision."""
    direction = "increased" if adjusted_ss > baseline_ss else "decreased"
    parts = [
        f"Inventory buffer {direction} for {product_id} at {location_id}: "
        f"{baseline_ss:.0f} → {adjusted_ss:.0f} ({multiplier:.2f}x)."
    ]
    if reason:
        parts.append(f"Reason: {reason}.")
    parts.append(f"Confidence: {confidence:.0%}.")
    return " ".join(parts)

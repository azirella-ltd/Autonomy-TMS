"""
Decision Reasoning Generator — Pre-computed plain-English explanations.

Generates concise reasoning strings at decision time from the data already
available in each TRM's persist method and GNN inference outputs.
No DB queries, no LLM calls.

These strings populate the `decision_reasoning` column so that Ask Why
can return instantly (<1ms) instead of routing through the LLM chat path.

Coverage:
- 11 TRM reasoning generators (one per TRM type)
- 3 GNN reasoning generators (S&OP GraphSAGE, Network tGNN, Site tGNN)
- capture_hive_context() helper for populating HiveSignalMixin fields
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


# ============================================================================
# Hive context capture helper — populates HiveSignalMixin fields at persist time
# ============================================================================

def capture_hive_context(
    signal_bus: Any,
    trm_name: str,
    cycle_id: Optional[str] = None,
    cycle_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """Capture current hive signal state for HiveSignalMixin fields.

    Call this in each TRM's persist method to populate the 6 signal columns
    (signal_context, urgency_at_time, triggered_by, signals_emitted,
    cycle_phase, cycle_id).

    Args:
        signal_bus: HiveSignalBus instance (or None).
        trm_name: Short TRM name (e.g. "atp_executor").
        cycle_id: UUID of the current decision cycle (from CycleResult).
        cycle_phase: Phase name (e.g. "SENSE", "BUILD").

    Returns:
        Dict with keys matching HiveSignalMixin column names. All values
        are safe for direct unpacking into the SQLAlchemy model constructor.
    """
    ctx: Dict[str, Any] = {
        "signal_context": None,
        "urgency_at_time": None,
        "triggered_by": None,
        "signals_emitted": None,
        "cycle_phase": cycle_phase,
        "cycle_id": cycle_id,
    }

    if signal_bus is None:
        return ctx

    try:
        # Signal context snapshot (JSON-serializable dict)
        ctx["signal_context"] = signal_bus.to_context_dict()
    except Exception:
        pass

    try:
        # Urgency value for this TRM at decision time
        if hasattr(signal_bus, "urgency"):
            val, _direction, _ts = signal_bus.urgency.read(trm_name)
            ctx["urgency_at_time"] = float(val)
    except Exception:
        pass

    try:
        # Triggered-by: signal types recently consumed by this TRM.
        # HiveSignalBus.read() is called in _read_signals_before_decision();
        # we capture which signal types were active at that time.
        active = signal_bus.read(consumer_trm=trm_name) if hasattr(signal_bus, "read") else []
        if active:
            type_names = sorted({str(getattr(s, "signal_type", s)) for s in active})
            ctx["triggered_by"] = ",".join(type_names[:20])
    except Exception:
        pass

    return ctx


# ============================================================================
# GNN reasoning generators — plain-English explanations for GNN outputs
# ============================================================================

def sop_graphsage_reasoning(
    *,
    site_key: str,
    criticality: float,
    bottleneck_risk: float,
    concentration_risk: float,
    resilience: float,
    safety_stock_multiplier: float,
    network_risk: Optional[Dict[str, float]] = None,
    score_intervals: Optional[Dict[str, Dict[str, float]]] = None,
) -> str:
    """Generate reasoning for an S&OP GraphSAGE network analysis output.

    Produces one string per site describing the strategic risk assessment
    and policy parameter recommendations from the weekly GraphSAGE run.
    """
    parts = [f"S&OP GraphSAGE analysis for site {site_key}:"]

    # Criticality
    if criticality >= 0.8:
        parts.append(f"Critically important node (criticality {criticality:.2f}).")
    elif criticality >= 0.5:
        parts.append(f"Moderately important node (criticality {criticality:.2f}).")
    else:
        parts.append(f"Low-criticality node ({criticality:.2f}).")

    # Bottleneck risk
    if bottleneck_risk >= 0.7:
        parts.append(f"High bottleneck risk ({bottleneck_risk:.0%}) — capacity constraint likely.")
    elif bottleneck_risk >= 0.3:
        parts.append(f"Moderate bottleneck risk ({bottleneck_risk:.0%}).")

    # Concentration risk
    if concentration_risk >= 0.7:
        parts.append(f"High supply concentration risk ({concentration_risk:.0%}) — single-source vulnerability.")
    elif concentration_risk >= 0.3:
        parts.append(f"Moderate concentration risk ({concentration_risk:.0%}).")

    # Resilience
    parts.append(f"Network resilience score: {resilience:.2f}.")

    # Safety stock multiplier recommendation
    if abs(safety_stock_multiplier - 1.0) > 0.05:
        direction = "increase" if safety_stock_multiplier > 1.0 else "decrease"
        parts.append(
            f"Recommending safety stock {direction} to {safety_stock_multiplier:.2f}x baseline "
            f"based on network risk profile."
        )

    # Conformal intervals if available
    if score_intervals:
        crit_iv = score_intervals.get("criticality")
        if crit_iv and "lower" in crit_iv and "upper" in crit_iv:
            parts.append(
                f"Criticality confidence interval: [{crit_iv['lower']:.2f}, {crit_iv['upper']:.2f}]."
            )

    return " ".join(parts)


def execution_tgnn_reasoning(
    *,
    site_key: str,
    demand_forecast_next: Optional[float] = None,
    exception_probability: float,
    order_recommendation: float,
    confidence: float,
    demand_interval: Optional[Dict[str, float]] = None,
    allocation_interval: Optional[Dict[str, float]] = None,
    propagation_sites: Optional[List[str]] = None,
) -> str:
    """Generate reasoning for a Network tGNN (Execution) inference output.

    Produces one string per site describing the daily allocation directive,
    demand forecast, and exception probability.
    """
    parts = [f"Network tGNN daily directive for site {site_key}:"]

    # Demand forecast
    if demand_forecast_next is not None:
        parts.append(f"Next-period demand forecast: {demand_forecast_next:.0f} units.")
        if demand_interval and "lower" in demand_interval and "upper" in demand_interval:
            parts.append(
                f"Conformal demand interval: [{demand_interval['lower']:.0f}, "
                f"{demand_interval['upper']:.0f}]."
            )

    # Exception probability
    if exception_probability >= 0.7:
        parts.append(f"High exception risk ({exception_probability:.0%}) — stockout or overstock likely.")
    elif exception_probability >= 0.3:
        parts.append(f"Moderate exception risk ({exception_probability:.0%}).")
    else:
        parts.append(f"Low exception risk ({exception_probability:.0%}).")

    # Order recommendation
    parts.append(f"Recommended allocation: {order_recommendation:.0f} units.")
    if allocation_interval and "lower" in allocation_interval and "upper" in allocation_interval:
        parts.append(
            f"Allocation interval: [{allocation_interval['lower']:.0f}, "
            f"{allocation_interval['upper']:.0f}]."
        )

    # Propagation impact
    if propagation_sites:
        parts.append(f"Demand propagation affects: {', '.join(propagation_sites[:5])}.")

    parts.append(f"Model confidence: {confidence:.0%}.")
    return " ".join(parts)


def site_tgnn_reasoning(
    *,
    site_key: str,
    urgency_adjustments: Dict[str, float],
    confidence_modifiers: Dict[str, float],
    coordination_signals: Dict[str, float],
) -> str:
    """Generate reasoning for a Site tGNN (Layer 1.5) inference output.

    Produces a single string per site summarizing the cross-TRM urgency
    adjustments and the causal coordination patterns detected.
    """
    parts = [f"Site tGNN hourly coordination for {site_key}:"]

    # Identify significant urgency adjustments (|adj| > 0.01)
    boosted = []
    dampened = []
    for trm, adj in urgency_adjustments.items():
        if adj > 0.01:
            boosted.append(f"{trm} (+{adj:.3f})")
        elif adj < -0.01:
            dampened.append(f"{trm} ({adj:.3f})")

    if boosted:
        parts.append(f"Urgency boosted for: {', '.join(boosted)}.")
    if dampened:
        parts.append(f"Urgency dampened for: {', '.join(dampened)}.")
    if not boosted and not dampened:
        parts.append("No significant urgency adjustments this cycle (neutral output).")

    # Identify TRMs with high coordination attention (> 0.7)
    high_coord = [
        trm for trm, sig in coordination_signals.items() if sig > 0.7
    ]
    if high_coord:
        parts.append(f"High cross-TRM attention on: {', '.join(high_coord)}.")

    # Identify confidence adjustments
    conf_changes = [
        f"{trm} ({mod:+.3f})" for trm, mod in confidence_modifiers.items()
        if abs(mod) > 0.01
    ]
    if conf_changes:
        parts.append(f"Confidence threshold adjustments: {', '.join(conf_changes)}.")

    return " ".join(parts)

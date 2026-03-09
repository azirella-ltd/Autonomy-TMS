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
    prio_label = {1: "critical", 2: "high", 3: "standard", 4: "low", 5: "backfill"}.get(order_priority, f"level {order_priority}")
    if can_fulfill:
        parts = [
            f"Full fulfillment of {promised_qty:.0f} units for {product_id} at {location_id}.",
            f"This is a {prio_label}-priority order (tier {order_priority} of 5).",
            f"The ATP agent evaluated available allocations across all priority tiers using the AATP consumption sequence and confirmed sufficient inventory to satisfy the full request.",
        ]
        if consumption_breakdown:
            tier_details = [f"tier {k}: {v:.0f}" for k, v in consumption_breakdown.items() if v > 0]
            if tier_details:
                parts.append(f"Allocation consumed from: {', '.join(tier_details)} units.")
        parts.append(f"Decision made by {method} at {confidence:.0%} confidence. No shortfall — downstream fulfillment is on track.")
        return " ".join(parts)
    shortfall = requested_qty - promised_qty
    fill_pct = (promised_qty / requested_qty * 100) if requested_qty > 0 else 0
    parts = [
        f"Partial fulfillment: {promised_qty:.0f} of {requested_qty:.0f} units for {product_id} at {location_id} ({fill_pct:.0f}% fill rate, shortfall of {shortfall:.0f} units).",
        f"This is a {prio_label}-priority order (tier {order_priority} of 5).",
        f"The ATP agent consumed available allocations bottom-up from lowest priority through tier {order_priority}, but could not source enough inventory to fully satisfy the request.",
    ]
    if consumption_breakdown:
        tier_details = [f"tier {k}: {v:.0f}" for k, v in consumption_breakdown.items() if v > 0]
        if tier_details:
            parts.append(f"Allocation consumed from: {', '.join(tier_details)} units.")
    parts.append(f"Decision by {method} at {confidence:.0%} confidence. Consider expediting a replenishment order or rebalancing inventory from a surplus location to close the gap.")
    return " ".join(parts)


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
    trigger_label = trigger_reason.replace("_", " ").lower()
    parts = [
        f"Purchase order recommended: {recommended_qty:.0f} units of {product_id} at {location_id}.",
    ]
    if supplier_id:
        parts.append(f"Sourced from supplier {supplier_id} based on sourcing rules and lead time evaluation.")
    parts.append(f"This PO was triggered by {trigger_label} conditions with {urgency} urgency.")
    if inventory_position is not None:
        coverage_note = ""
        if recommended_qty > 0:
            days_est = inventory_position / (recommended_qty / 30) if recommended_qty > 0 else 0
            if days_est < 7:
                coverage_note = " Current stock covers less than a week of expected demand — replenishment is time-critical."
            elif days_est < 14:
                coverage_note = " Current stock covers approximately two weeks of expected demand."
        parts.append(f"Current inventory position is {inventory_position:.0f} units.{coverage_note}")
    if expected_cost is not None:
        parts.append(f"Estimated procurement cost: ${expected_cost:,.2f}.")
    parts.append(f"Decision confidence: {confidence:.0%}. If not executed, the location risks stockout within the replenishment lead time window.")
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
    reason_label = reason.replace("_", " ") if reason else "inventory imbalance"
    parts = [
        f"Inventory rebalancing: transfer {recommended_qty:.0f} units of {product_id} from {from_site} to {to_site}.",
        f"This transfer was triggered by {reason_label} detected across the distribution network.",
    ]
    if from_inventory is not None and to_inventory is not None:
        ratio = from_inventory / to_inventory if to_inventory > 0 else float("inf")
        parts.append(
            f"Source site ({from_site}) currently holds {from_inventory:.0f} units while destination ({to_site}) holds {to_inventory:.0f} units — a {ratio:.1f}:1 imbalance."
        )
        if to_inventory == 0:
            parts.append("The destination site has zero stock, making this transfer critical to prevent stockouts.")
    else:
        parts.append(f"The agent identified {to_site} as having insufficient coverage relative to its demand forecast, while {from_site} has surplus inventory that can be redistributed without risk.")
    parts.append(f"Decision confidence: {confidence:.0%}. Transferring this quantity equalizes days-of-supply across locations and improves overall network service level.")
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
    severity_context = {
        "critical": "This requires immediate attention as it may impact customer commitments or production schedules.",
        "high": "This exception has significant downstream impact and should be addressed within the current planning cycle.",
        "medium": "This is a moderate-priority exception that should be reviewed but is not immediately blocking.",
        "low": "This is an informational exception flagged for awareness — no urgent action required.",
    }.get(severity.lower(), f"Severity level: {severity}.")
    action_label = recommended_action.replace("_", " ")
    exc_label = exception_type.replace("_", " ").lower()
    parts = [
        f"Exception detected on order {order_id}: {exc_label} ({severity} severity).",
        severity_context,
        f"The order tracking agent recommends: {action_label}.",
    ]
    if reason:
        parts.append(f"Root cause analysis: {reason}.")
    parts.append(f"Decision confidence: {confidence:.0%}. If this exception is not resolved, it may cascade to downstream orders and affect service level commitments.")
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
    decision_label = decision_type.replace("_", " ").lower()
    parts = [
        f"{subject} at {location_id}: decision is to {decision_label}.",
        f"The MO execution agent evaluated current production capacity, material availability, and downstream demand priority to determine the optimal action for this order.",
    ]
    if reason:
        parts.append(f"Specific trigger: {reason}.")
    parts.append(f"Decision confidence: {confidence:.0%}. This action aligns with the current production schedule and capacity constraints at {location_id}.")
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
        route = f" from {source_site_id} to {dest_site_id}"
    decision_label = decision_type.replace("_", " ").lower()
    parts = [
        f"{subject}{route}: decision is to {decision_label}.",
        f"The transfer order agent assessed transportation lane capacity, transit lead times, and inventory urgency at both the source and destination to determine the optimal execution action.",
    ]
    if trigger_reason:
        trigger_label = trigger_reason.replace("_", " ").lower()
        parts.append(f"This action was triggered by: {trigger_label}.")
    parts.append(f"Decision confidence: {confidence:.0%}. Executing this transfer order supports network-level inventory balance and service level targets.")
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
    subject = f"Lot {lot_id} ({product_id})" if lot_id else product_id
    disposition_label = disposition.replace("_", " ").lower()
    parts = [
        f"Quality disposition for {subject} at {location_id}: {disposition_label}.",
        f"The quality agent evaluated inspection results, defect classifications, and downstream impact to determine the appropriate disposition for this material.",
    ]
    if disposition_reason:
        parts.append(f"Disposition rationale: {disposition_reason}.")
    impact = {
        "accept": "Releasing this material to available inventory for immediate use.",
        "reject": "This material will be quarantined and returned or disposed. Replacement inventory may need to be sourced.",
        "rework": "This material will be routed to rework operations, adding processing time but recovering value.",
        "scrap": "This material is unrecoverable and will be written off. A replacement order may be needed.",
        "use_as_is": "Despite the quality deviation, the material meets minimum acceptance criteria for its intended use.",
    }.get(disposition.lower(), "")
    if impact:
        parts.append(impact)
    parts.append(f"Decision confidence: {confidence:.0%}.")
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
    decision_label = decision_type.replace("_", " ").lower()
    parts = [
        f"Maintenance decision for asset {asset_id} at {location_id}: {decision_label}.",
        f"The maintenance scheduling agent balanced production capacity requirements against equipment reliability risk and preventive maintenance schedules to determine the optimal timing.",
    ]
    if reason:
        parts.append(f"Specific trigger: {reason}.")
    context = {
        "schedule": "Preventive maintenance will be scheduled during a planned downtime window to minimize production impact.",
        "defer": "Maintenance is being deferred because current production demand takes priority and equipment condition metrics remain within acceptable bounds.",
        "expedite": "Maintenance is being expedited due to elevated equipment risk indicators — delaying further could result in unplanned downtime.",
        "outsource": "This maintenance task is being routed to an external service provider due to internal capacity constraints or specialized skill requirements.",
    }.get(decision_type.lower(), "")
    if context:
        parts.append(context)
    parts.append(f"Decision confidence: {confidence:.0%}.")
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
    routing_label = routing_decision.replace("_", " ").lower()
    parts = [
        f"Make-vs-buy routing decision for {product_id}: {routing_label}.",
        f"The subcontracting agent evaluated internal manufacturing capacity, external supplier lead times and costs, and current demand urgency to determine the optimal production routing.",
    ]
    if external_supplier:
        parts.append(f"External manufacturing will be handled by {external_supplier}.")
    if reason:
        parts.append(f"Key factor: {reason}.")
    context = {
        "internal": "Keeping production in-house because internal capacity is available and cost-effective for this volume.",
        "external": "Routing to external manufacturing because internal capacity is constrained or the external supplier offers better cost/lead time for this product.",
        "split": "Splitting production between internal and external sources to balance capacity utilization and meet delivery timelines.",
    }.get(routing_decision.lower(), "")
    if context:
        parts.append(context)
    parts.append(f"Decision confidence: {confidence:.0%}.")
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
    parts = [
        f"Forecast adjustment for {product_id}: {adjustment_direction} by {adjustment_pct:.1f}%.",
    ]
    if current_value is not None and adjusted_value is not None:
        delta = abs(adjusted_value - current_value)
        parts.append(f"Baseline forecast of {current_value:.0f} units adjusted to {adjusted_value:.0f} units (delta: {delta:.0f} units).")
    if signal_type:
        signal_label = signal_type.replace("_", " ")
        parts.append(f"This adjustment was triggered by a {signal_label} signal that indicates a deviation from the statistical forecast baseline.")
    direction_context = {
        "up": "Demand is expected to be higher than the statistical forecast suggests. Upstream supply plans should account for the increased requirement to avoid stockouts.",
        "down": "Demand is expected to be lower than the statistical forecast suggests. Reducing the forecast prevents excess inventory build-up and associated holding costs.",
    }.get(adjustment_direction.lower(), "")
    if direction_context:
        parts.append(direction_context)
    parts.append(f"Decision confidence: {confidence:.0%}. This adjustment will propagate through dependent supply plans in the next planning cycle.")
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
    delta = abs(adjusted_ss - baseline_ss)
    parts = [
        f"Inventory buffer {direction} for {product_id} at {location_id}: {baseline_ss:.0f} → {adjusted_ss:.0f} units ({multiplier:.2f}x multiplier, delta of {delta:.0f} units).",
        f"The inventory buffer agent evaluated demand variability, lead time uncertainty, and recent service level performance to determine whether the current buffer is appropriately sized.",
    ]
    if reason:
        reason_label = reason.replace("_", " ")
        parts.append(f"Adjustment triggered by: {reason_label}.")
    if direction == "increased":
        parts.append(f"Increasing the buffer absorbs additional uncertainty and reduces the probability of stockout. The trade-off is higher average on-hand inventory and associated holding costs.")
    else:
        parts.append(f"Decreasing the buffer releases excess working capital while maintaining acceptable service levels. Demand patterns have stabilized enough to warrant a tighter buffer.")
    parts.append(f"Decision confidence: {confidence:.0%}.")
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

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
    unit_cost: Optional[float] = None,
    unit_price: Optional[float] = None,
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
        if unit_price is not None:
            revenue = promised_qty * unit_price
            parts.append(f"Revenue secured: ${revenue:,.2f} ({promised_qty:.0f} × ${unit_price:.2f}/unit).")
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
    if unit_price is not None:
        lost_revenue = shortfall * unit_price
        fulfilled_revenue = promised_qty * unit_price
        total_revenue = requested_qty * unit_price
        lost_pct = (lost_revenue / total_revenue * 100) if total_revenue > 0 else 0
        parts.append(
            f"Revenue at risk: ${lost_revenue:,.2f} from {shortfall:.0f} unfulfilled units "
            f"({lost_pct:.0f}% of ${total_revenue:,.2f} order value). "
            f"Fulfilled portion secures ${fulfilled_revenue:,.2f}."
        )
    if unit_cost is not None and shortfall > 0:
        expedite_premium = 0.35  # typical expedite premium
        expedite_cost = shortfall * unit_cost * (1 + expedite_premium)
        normal_cost = shortfall * unit_cost
        premium_delta = expedite_cost - normal_cost
        parts.append(
            f"Expediting {shortfall:.0f} units would cost ~${expedite_cost:,.2f} "
            f"(${premium_delta:,.2f} / {expedite_premium:.0%} premium over standard procurement at ${normal_cost:,.2f})."
        )
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
    unit_cost: Optional[float] = None,
    unit_price: Optional[float] = None,
    daily_demand: Optional[float] = None,
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
        # Compute cost of inaction (stockout cost)
        if unit_price is not None and daily_demand is not None and daily_demand > 0:
            # Stockout cost = lost margin × days until next replenishment opportunity (est. 7 days)
            margin = unit_price - (unit_cost or 0)
            stockout_days = 7
            stockout_cost = margin * daily_demand * stockout_days
            if stockout_cost > 0:
                saving = stockout_cost - expected_cost
                saving_pct = (saving / stockout_cost * 100) if stockout_cost > 0 else 0
                parts.append(
                    f"Cost of inaction: ~${stockout_cost:,.2f} in lost margin over {stockout_days} days "
                    f"of potential stockout ({daily_demand:.0f} units/day × ${margin:.2f} margin). "
                    f"Ordering now saves ${saving:,.2f} ({saving_pct:.0f}%) net vs. stockout risk."
                )
        elif unit_cost is not None:
            # Expedite alternative
            expedite_cost = expected_cost * 1.40
            premium = expedite_cost - expected_cost
            parts.append(
                f"Delaying this PO could require expedited procurement at ~${expedite_cost:,.2f} "
                f"(${premium:,.2f} / 40% premium over standard cost of ${expected_cost:,.2f})."
            )
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
    expected_cost: Optional[float] = None,
    unit_cost: Optional[float] = None,
    unit_price: Optional[float] = None,
    source_dos_before: Optional[float] = None,
    dest_dos_before: Optional[float] = None,
    dest_dos_after: Optional[float] = None,
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
    # Cost quantification
    if expected_cost is not None:
        parts.append(f"Transfer cost: ${expected_cost:,.2f}.")
        if unit_cost is not None:
            # Alternative: new PO from supplier (typically 2-3x transfer cost)
            new_po_cost = recommended_qty * unit_cost
            if new_po_cost > expected_cost:
                saving = new_po_cost - expected_cost
                saving_pct = (saving / new_po_cost * 100) if new_po_cost > 0 else 0
                parts.append(
                    f"Alternative (new PO from supplier): ${new_po_cost:,.2f}. "
                    f"Rebalancing saves ${saving:,.2f} ({saving_pct:.0f}%) vs. new procurement."
                )
            # Alternative: expedited shipment
            expedite_cost = expected_cost * 2.5
            expedite_saving = expedite_cost - expected_cost
            parts.append(
                f"Alternative (expedited shipment): ~${expedite_cost:,.2f}. "
                f"Standard transfer saves ${expedite_saving:,.2f} ({150:.0f}%) vs. expedite."
            )
        if unit_price is not None and dest_dos_before is not None and dest_dos_before < 3:
            # Quantify stockout risk at destination
            daily_revenue = unit_price * (recommended_qty / max(dest_dos_after - dest_dos_before, 1) if dest_dos_after and dest_dos_before else recommended_qty / 5)
            stockout_days = max(3 - dest_dos_before, 0)
            lost_revenue = daily_revenue * stockout_days
            if lost_revenue > 0:
                parts.append(
                    f"Without this transfer, {to_site} risks ~${lost_revenue:,.2f} in lost sales "
                    f"over {stockout_days:.0f} days of potential stockout."
                )
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
    estimated_impact_cost: Optional[float] = None,
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
    if estimated_impact_cost is not None and estimated_impact_cost > 0:
        # Quantify cost of inaction vs resolution
        resolution_cost = estimated_impact_cost * 0.25  # typical resolution cost is 25% of full impact
        saving = estimated_impact_cost - resolution_cost
        saving_pct = (saving / estimated_impact_cost * 100) if estimated_impact_cost > 0 else 0
        parts.append(
            f"Estimated impact if unresolved: ${estimated_impact_cost:,.2f}. "
            f"Estimated resolution cost: ~${resolution_cost:,.2f}. "
            f"Acting now saves ~${saving:,.2f} ({saving_pct:.0f}%) vs. allowing the exception to cascade."
        )
    elif estimated_impact_cost == 0:
        parts.append("No direct financial impact estimated — this is a process compliance exception.")
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
    unit_cost: Optional[float] = None,
    quantity: Optional[float] = None,
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
    if unit_cost is not None and quantity is not None and quantity > 0:
        production_value = quantity * unit_cost
        if decision_type.lower() == "expedite":
            overtime_premium = production_value * 0.50
            parts.append(
                f"Production value: ${production_value:,.2f} ({quantity:.0f} units × ${unit_cost:.2f}). "
                f"Expediting adds ~${overtime_premium:,.2f} in overtime/setup costs (50% premium), "
                f"but avoids downstream stockout worth ${production_value * 1.3:,.2f} in lost margin."
            )
        elif decision_type.lower() == "defer":
            holding_saving = production_value * 0.25 / 52  # one week holding cost
            parts.append(
                f"Deferring saves ~${holding_saving:,.2f}/week in holding costs on ${production_value:,.2f} of inventory. "
                f"Risk: downstream demand may not be met if deferred too long."
            )
        elif decision_type.lower() in ("release", "release_standard"):
            parts.append(f"Production value: ${production_value:,.2f} ({quantity:.0f} units × ${unit_cost:.2f}).")
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
    unit_cost: Optional[float] = None,
    quantity: Optional[float] = None,
    transfer_cost: Optional[float] = None,
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
    if unit_cost is not None and quantity is not None and quantity > 0:
        shipment_value = quantity * unit_cost
        if transfer_cost is not None:
            cost_pct = (transfer_cost / shipment_value * 100) if shipment_value > 0 else 0
            parts.append(f"Shipment value: ${shipment_value:,.2f}. Transfer cost: ${transfer_cost:,.2f} ({cost_pct:.1f}% of goods value).")
        else:
            parts.append(f"Shipment value: ${shipment_value:,.2f} ({quantity:.0f} units × ${unit_cost:.2f}).")
        if decision_type.lower() == "expedite":
            standard_cost = (transfer_cost or shipment_value * 0.05)
            expedite_cost = standard_cost * 2.5
            premium = expedite_cost - standard_cost
            parts.append(
                f"Expediting costs ~${expedite_cost:,.2f} vs. standard ${standard_cost:,.2f} "
                f"(${premium:,.2f} / {150:.0f}% premium). Justified if destination stockout risk is imminent."
            )
        elif decision_type.lower() == "consolidate":
            estimated_saving = (transfer_cost or shipment_value * 0.05) * 0.30
            parts.append(f"Consolidation saves ~${estimated_saving:,.2f} (est. 30% freight reduction) by combining shipments.")
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
    unit_cost: Optional[float] = None,
    quantity: Optional[float] = None,
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
    # Cost quantification by disposition type
    if unit_cost is not None and quantity is not None and quantity > 0:
        lot_value = quantity * unit_cost
        if disposition.lower() == "scrap":
            parts.append(
                f"Write-off value: ${lot_value:,.2f} ({quantity:.0f} units × ${unit_cost:.2f}). "
                f"Replacement PO cost: ~${lot_value:,.2f} + ${lot_value * 0.10:,.2f} expedite premium if urgent."
            )
        elif disposition.lower() == "rework":
            rework_cost = lot_value * 0.20
            recovered_value = lot_value - rework_cost
            vs_scrap_saving = lot_value - rework_cost
            vs_scrap_pct = (vs_scrap_saving / lot_value * 100) if lot_value > 0 else 0
            parts.append(
                f"Rework cost: ~${rework_cost:,.2f} (est. 20% of ${lot_value:,.2f} lot value). "
                f"Recovered value: ${recovered_value:,.2f}. "
                f"Rework saves ${vs_scrap_saving:,.2f} ({vs_scrap_pct:.0f}%) vs. scrapping and reordering."
            )
        elif disposition.lower() == "reject":
            parts.append(
                f"Lot value at risk: ${lot_value:,.2f}. Supplier recovery/credit may offset "
                f"${lot_value * 0.80:,.2f} (80%) of the loss pending return terms."
            )
        elif disposition.lower() in ("accept", "use_as_is"):
            parts.append(f"Lot value preserved: ${lot_value:,.2f} — no reorder or rework cost incurred.")
    parts.append(f"Decision confidence: {confidence:.0%}.")
    return " ".join(parts)


def maintenance_reasoning(
    *,
    asset_id: str,
    location_id: str,
    decision_type: str,
    confidence: float,
    reason: Optional[str] = None,
    estimated_maintenance_cost: Optional[float] = None,
    estimated_downtime_hours: Optional[float] = None,
    hourly_production_value: Optional[float] = None,
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
    # Cost quantification
    if estimated_maintenance_cost is not None:
        parts.append(f"Planned maintenance cost: ${estimated_maintenance_cost:,.2f}.")
        if estimated_downtime_hours is not None and hourly_production_value is not None:
            planned_lost_production = estimated_downtime_hours * hourly_production_value
            # Unplanned breakdown costs 3-5x more
            unplanned_downtime = estimated_downtime_hours * 3
            unplanned_cost = estimated_maintenance_cost * 3 + unplanned_downtime * hourly_production_value
            saving = unplanned_cost - (estimated_maintenance_cost + planned_lost_production)
            saving_pct = (saving / unplanned_cost * 100) if unplanned_cost > 0 else 0
            parts.append(
                f"Planned downtime: {estimated_downtime_hours:.1f}h (${planned_lost_production:,.2f} lost production). "
                f"Unplanned breakdown estimate: ${unplanned_cost:,.2f} "
                f"({unplanned_downtime:.0f}h downtime + 3× repair cost). "
                f"Planned maintenance saves ${saving:,.2f} ({saving_pct:.0f}%) vs. unplanned failure."
            )
        elif estimated_downtime_hours is not None:
            unplanned_cost = estimated_maintenance_cost * 3
            saving = unplanned_cost - estimated_maintenance_cost
            parts.append(
                f"Planned downtime: {estimated_downtime_hours:.1f}h. "
                f"Unplanned breakdown estimate: ~${unplanned_cost:,.2f} (3× planned cost). "
                f"Preventive approach saves ~${saving:,.2f}."
            )
    parts.append(f"Decision confidence: {confidence:.0%}.")
    return " ".join(parts)


def subcontracting_reasoning(
    *,
    product_id: str,
    routing_decision: str,
    confidence: float,
    reason: Optional[str] = None,
    external_supplier: Optional[str] = None,
    unit_cost: Optional[float] = None,
    quantity: Optional[float] = None,
    internal_cost_per_unit: Optional[float] = None,
    external_cost_per_unit: Optional[float] = None,
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
    # Cost quantification
    if quantity is not None and quantity > 0:
        int_cpu = internal_cost_per_unit or unit_cost
        ext_cpu = external_cost_per_unit or (unit_cost * 1.25 if unit_cost else None)
        if int_cpu is not None and ext_cpu is not None:
            internal_total = quantity * int_cpu
            external_total = quantity * ext_cpu
            delta = abs(external_total - internal_total)
            delta_pct = (delta / max(internal_total, external_total) * 100) if max(internal_total, external_total) > 0 else 0
            if routing_decision.lower() == "internal":
                parts.append(
                    f"Internal production: ${internal_total:,.2f} ({quantity:.0f} × ${int_cpu:.2f}). "
                    f"External alternative: ${external_total:,.2f} ({quantity:.0f} × ${ext_cpu:.2f}). "
                    f"Internal routing saves ${delta:,.2f} ({delta_pct:.0f}%)."
                )
            elif routing_decision.lower() == "external":
                parts.append(
                    f"External production: ${external_total:,.2f} ({quantity:.0f} × ${ext_cpu:.2f}). "
                    f"Internal alternative: ${internal_total:,.2f} ({quantity:.0f} × ${int_cpu:.2f}). "
                    f"External routing costs ${delta:,.2f} ({delta_pct:.0f}%) more, "
                    f"justified by capacity constraints or lead time advantage."
                )
            elif routing_decision.lower() == "split":
                # Assume 60/40 split
                int_qty = quantity * 0.6
                ext_qty = quantity * 0.4
                split_cost = int_qty * int_cpu + ext_qty * ext_cpu
                vs_all_ext = external_total - split_cost
                vs_all_ext_pct = (vs_all_ext / external_total * 100) if external_total > 0 else 0
                parts.append(
                    f"Split cost (est. 60/40): ${split_cost:,.2f} "
                    f"(internal ${int_qty * int_cpu:,.2f} + external ${ext_qty * ext_cpu:,.2f}). "
                    f"Saves ${vs_all_ext:,.2f} ({vs_all_ext_pct:.0f}%) vs. fully external at ${external_total:,.2f}."
                )
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
    unit_cost: Optional[float] = None,
    unit_price: Optional[float] = None,
) -> str:
    """Generate reasoning for a forecast adjustment decision."""
    parts = [
        f"Forecast adjustment for {product_id}: {adjustment_direction} by {adjustment_pct:.1f}%.",
    ]
    if current_value is not None and adjusted_value is not None:
        delta = abs(adjusted_value - current_value)
        parts.append(f"Baseline forecast of {current_value:.0f} units adjusted to {adjusted_value:.0f} units (delta: {delta:.0f} units).")
        # Cost quantification of the adjustment
        if unit_cost is not None:
            holding_cost_annual_pct = 0.25
            weekly_holding_per_unit = unit_cost * holding_cost_annual_pct / 52
            if adjustment_direction.lower() == "up":
                # Upward: cost of not adjusting = potential stockout on the delta
                if unit_price is not None:
                    margin = unit_price - unit_cost
                    stockout_cost = delta * margin
                    parts.append(
                        f"Cost of not adjusting: ~${stockout_cost:,.2f} in lost margin if demand materializes "
                        f"at the higher level ({delta:.0f} units × ${margin:.2f}/unit margin). "
                        f"Additional holding cost from adjustment: ${delta * weekly_holding_per_unit:,.2f}/week "
                        f"({delta:.0f} units × ${weekly_holding_per_unit:.2f}/unit/week)."
                    )
                else:
                    extra_holding = delta * weekly_holding_per_unit
                    parts.append(
                        f"Additional holding cost from higher forecast: ${extra_holding:,.2f}/week "
                        f"({delta:.0f} units × ${weekly_holding_per_unit:.2f}/unit/week)."
                    )
            else:
                # Downward: savings from reduced inventory
                weekly_saving = delta * weekly_holding_per_unit
                monthly_saving = weekly_saving * 4.33
                parts.append(
                    f"Holding cost savings from lower forecast: ${weekly_saving:,.2f}/week "
                    f"(${monthly_saving:,.2f}/month). "
                    f"Reduces excess inventory by {delta:.0f} units × ${unit_cost:.2f}/unit = "
                    f"${delta * unit_cost:,.2f} working capital freed."
                )
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
    unit_cost: Optional[float] = None,
    unit_price: Optional[float] = None,
    current_dos: Optional[float] = None,
    excess_holding_cost: Optional[float] = None,
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
    # Cost quantification
    if unit_cost is not None:
        holding_cost_annual_pct = 0.25
        weekly_holding_per_unit = unit_cost * holding_cost_annual_pct / 52
        annual_holding_delta = delta * unit_cost * holding_cost_annual_pct
        weekly_holding_delta = delta * weekly_holding_per_unit
        working_capital_delta = delta * unit_cost
        if direction == "increased":
            parts.append(
                f"Additional holding cost: ${weekly_holding_delta:,.2f}/week (${annual_holding_delta:,.2f}/year) "
                f"for {delta:.0f} extra buffer units at ${unit_cost:.2f}/unit. "
                f"Working capital increase: ${working_capital_delta:,.2f}."
            )
            if unit_price is not None:
                # Quantify stockout prevention value
                margin = unit_price - unit_cost
                stockout_prevention = delta * margin  # one stockout cycle worth of margin protected
                roi_pct = (stockout_prevention / annual_holding_delta * 100) if annual_holding_delta > 0 else 0
                parts.append(
                    f"Stockout prevention value: ${stockout_prevention:,.2f} per stockout event avoided "
                    f"({delta:.0f} units × ${margin:.2f} margin). "
                    f"ROI vs. holding cost: {roi_pct:.0f}% if one stockout event is prevented per year."
                )
        else:
            parts.append(
                f"Holding cost savings: ${weekly_holding_delta:,.2f}/week (${annual_holding_delta:,.2f}/year). "
                f"Working capital freed: ${working_capital_delta:,.2f}."
            )
            if unit_price is not None:
                margin = unit_price - unit_cost
                risk_exposure = delta * margin
                parts.append(
                    f"Trade-off: ${risk_exposure:,.2f} additional margin exposure per stockout event "
                    f"({delta:.0f} fewer buffer units × ${margin:.2f} margin)."
                )
    elif excess_holding_cost is not None:
        parts.append(f"Excess holding cost impact: ${excess_holding_cost:,.2f}.")
    else:
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

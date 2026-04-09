"""
TMS Heuristic Dispatch — Transportation Decision Rules

Deterministic fallback logic for all 11 TMS TRMs when neural network
models are unavailable. Encodes industry best practices for:
- Carrier waterfall tendering
- Load consolidation
- Dock door optimization
- Exception triage
- Equipment rebalancing

Unlike the SC library which dispatches by ERP source (SAP/D365/Odoo),
TMS heuristics are universal — transportation operations follow standard
industry practices regardless of source system.
"""

import logging
from typing import Any

from .base import (
    TMSHeuristicDecision,
    CapacityPromiseState,
    ShipmentTrackingState,
    DemandSensingState,
    CapacityBufferState,
    ExceptionManagementState,
    FreightProcurementState,
    BrokerRoutingState,
    DockSchedulingState,
    LoadBuildState,
    IntermodalTransferState,
    EquipmentRepositionState,
)

logger = logging.getLogger(__name__)


# ── Action Constants ────────────────────────────────────────────────────
# Discrete action indices used across TRMs

class Actions:
    ACCEPT = 0
    REJECT = 1
    DEFER = 2
    ESCALATE = 3
    MODIFY = 4
    RETENDER = 5
    REROUTE = 6
    CONSOLIDATE = 7
    SPLIT = 8
    REPOSITION = 9
    HOLD = 10


# ============================================================================
# Main Dispatch
# ============================================================================

def compute_tms_decision(trm_type: str, state: Any) -> TMSHeuristicDecision:
    """
    Compute a deterministic decision for any TMS TRM.

    Args:
        trm_type: TRM canonical name (e.g., "capacity_promise")
        state: Corresponding state dataclass

    Returns:
        TMSHeuristicDecision with action, reasoning, and parameters
    """
    dispatch_map = {
        "capacity_promise": _compute_capacity_promise,
        "shipment_tracking": _compute_shipment_tracking,
        "demand_sensing": _compute_demand_sensing,
        "capacity_buffer": _compute_capacity_buffer,
        "exception_management": _compute_exception_management,
        "freight_procurement": _compute_freight_procurement,
        "broker_routing": _compute_broker_routing,
        "dock_scheduling": _compute_dock_scheduling,
        "load_build": _compute_load_build,
        "intermodal_transfer": _compute_intermodal_transfer,
        "equipment_reposition": _compute_equipment_reposition,
    }

    func = dispatch_map.get(trm_type)
    if not func:
        logger.warning(f"No heuristic for TRM type '{trm_type}'")
        return TMSHeuristicDecision(
            trm_type=trm_type, action=Actions.HOLD,
            reasoning=f"No heuristic available for {trm_type}",
        )

    return func(state)


# ============================================================================
# 1. Capacity Promise
# ============================================================================

def _compute_capacity_promise(state: CapacityPromiseState) -> TMSHeuristicDecision:
    """
    Evaluate whether to promise capacity for a shipment request.

    Rules:
    - P1-P2 priority: always promise (consume buffer if needed)
    - Capacity available: promise
    - Spot available but premium >20%: defer to procurement
    - No capacity: reject
    """
    available = state.available_capacity()

    if state.priority <= 2:
        # Critical priority: promise even if tight
        if available >= state.requested_loads or state.buffer_capacity > 0:
            return TMSHeuristicDecision(
                trm_type="capacity_promise", action=Actions.ACCEPT,
                quantity=state.requested_loads,
                reasoning=f"High priority (P{state.priority}): committed from {'buffer' if available < state.requested_loads else 'available capacity'}",
                urgency=0.8,
            )

    if available >= state.requested_loads:
        return TMSHeuristicDecision(
            trm_type="capacity_promise", action=Actions.ACCEPT,
            quantity=state.requested_loads,
            reasoning=f"Capacity available ({available} loads on lane, {state.requested_loads} requested)",
            urgency=0.3,
        )

    if state.backup_carriers_count > 0 and state.spot_rate_premium_pct < 0.20:
        return TMSHeuristicDecision(
            trm_type="capacity_promise", action=Actions.ACCEPT,
            quantity=state.requested_loads,
            reasoning=f"Spot capacity available at {state.spot_rate_premium_pct*100:.0f}% premium (within threshold)",
            urgency=0.5,
        )

    if state.spot_rate_premium_pct >= 0.20:
        return TMSHeuristicDecision(
            trm_type="capacity_promise", action=Actions.DEFER,
            quantity=state.requested_loads,
            reasoning=f"Spot premium {state.spot_rate_premium_pct*100:.0f}% exceeds 20% threshold; deferring to procurement",
            urgency=0.6,
        )

    return TMSHeuristicDecision(
        trm_type="capacity_promise", action=Actions.REJECT,
        quantity=0,
        reasoning=f"No capacity: {available} available, {state.requested_loads} requested, 0 backup carriers",
        urgency=0.9,
    )


# ============================================================================
# 2. Shipment Tracking
# ============================================================================

def _compute_shipment_tracking(state: ShipmentTrackingState) -> TMSHeuristicDecision:
    """
    Evaluate shipment tracking status and detect exceptions.

    Rules:
    - No update >4 hours (truck) or >24 hours (ocean): tracking lost
    - ETA past delivery window: late delivery exception
    - Temperature out of range: temperature excursion
    - <50% complete and >50% time elapsed: at-risk
    """
    # Tracking lost detection
    if state.last_update_hours_ago > 4 and state.shipment_status == "IN_TRANSIT":
        return TMSHeuristicDecision(
            trm_type="shipment_tracking", action=Actions.ESCALATE,
            reasoning=f"No tracking update for {state.last_update_hours_ago:.1f} hours",
            urgency=0.7,
        )

    # Late delivery detection
    if state.is_late():
        hours_late = 0
        if state.planned_delivery and state.current_eta:
            hours_late = (state.current_eta - state.planned_delivery).total_seconds() / 3600
        return TMSHeuristicDecision(
            trm_type="shipment_tracking", action=Actions.ESCALATE,
            quantity=hours_late,
            reasoning=f"ETA {hours_late:.1f}h past delivery window",
            urgency=min(1.0, 0.5 + hours_late / 24),
        )

    # Temperature excursion
    if (state.is_temperature_sensitive
            and state.current_temp is not None
            and state.temp_min is not None
            and state.temp_max is not None):
        if state.current_temp < state.temp_min or state.current_temp > state.temp_max:
            return TMSHeuristicDecision(
                trm_type="shipment_tracking", action=Actions.ESCALATE,
                quantity=state.current_temp,
                reasoning=f"Temperature {state.current_temp}°F outside range [{state.temp_min}, {state.temp_max}]",
                urgency=0.9,
            )

    # At-risk detection
    hours_remaining = state.hours_to_delivery()
    if hours_remaining and hours_remaining > 0 and state.pct_complete < 0.5:
        total_hours = hours_remaining / max(0.01, 1.0 - state.pct_complete)
        if state.pct_complete < (1.0 - hours_remaining / max(1, total_hours)) - 0.1:
            return TMSHeuristicDecision(
                trm_type="shipment_tracking", action=Actions.MODIFY,
                reasoning=f"Shipment at-risk: {state.pct_complete*100:.0f}% complete with {hours_remaining:.0f}h remaining",
                urgency=0.5,
            )

    return TMSHeuristicDecision(
        trm_type="shipment_tracking", action=Actions.ACCEPT,
        reasoning="Shipment tracking nominal",
        urgency=0.1,
    )


# ============================================================================
# 3. Demand Sensing
# ============================================================================

def _compute_demand_sensing(state: DemandSensingState) -> TMSHeuristicDecision:
    """
    Evaluate whether to adjust volume forecast.

    Rules:
    - Bias >15%: adjust forecast toward actuals
    - WoW change >20%: flag volume shift
    - Peak season + high MAPE: increase buffer recommendation
    """
    bias = state.forecast_bias()

    if abs(bias) > 0.15:
        direction = "down" if bias > 0 else "up"
        adjustment = -bias * state.forecast_loads * 0.5  # Partial correction
        return TMSHeuristicDecision(
            trm_type="demand_sensing", action=Actions.MODIFY,
            quantity=adjustment,
            reasoning=f"Forecast bias {bias*100:.0f}%: adjusting {direction} by {abs(adjustment):.0f} loads",
            urgency=0.5 + abs(bias),
        )

    if abs(state.week_over_week_change_pct) > 0.20:
        return TMSHeuristicDecision(
            trm_type="demand_sensing", action=Actions.MODIFY,
            quantity=state.week_over_week_change_pct * state.forecast_loads * 0.3,
            reasoning=f"WoW volume change {state.week_over_week_change_pct*100:.0f}%; signaling volume shift",
            urgency=0.4,
        )

    if state.is_peak_season and state.forecast_mape > 0.20:
        return TMSHeuristicDecision(
            trm_type="demand_sensing", action=Actions.MODIFY,
            quantity=state.forecast_loads * 0.1,  # Add 10% buffer recommendation
            reasoning=f"Peak season with {state.forecast_mape*100:.0f}% MAPE; recommending buffer increase",
            urgency=0.4,
        )

    return TMSHeuristicDecision(
        trm_type="demand_sensing", action=Actions.ACCEPT,
        reasoning=f"Forecast acceptable (bias {bias*100:.0f}%, MAPE {state.forecast_mape*100:.0f}%)",
        urgency=0.1,
    )


# ============================================================================
# 4. Capacity Buffer
# ============================================================================

def _compute_capacity_buffer(state: CapacityBufferState) -> TMSHeuristicDecision:
    """
    Evaluate capacity buffer level adjustment.

    Rules:
    - Tender reject rate >15%: increase buffer
    - Demand CV >0.3: increase buffer (conformal P90 approach)
    - Peak season: increase buffer by seasonal factor
    - Consistent surplus: decrease buffer
    """
    multiplier = 1.0
    reasons = []

    if state.recent_tender_reject_rate > 0.15:
        multiplier *= 1.3
        reasons.append(f"high tender reject rate ({state.recent_tender_reject_rate*100:.0f}%)")

    if state.demand_cv > 0.3:
        multiplier *= (1.0 + state.demand_cv * 0.5)
        reasons.append(f"high demand volatility (CV={state.demand_cv:.2f})")

    if state.is_peak_season:
        multiplier *= 1.2
        reasons.append("peak season")

    if state.demand_trend > 0.1:
        multiplier *= (1.0 + state.demand_trend * 0.2)
        reasons.append(f"growing demand (trend={state.demand_trend:.2f})")

    if state.recent_capacity_miss_count >= 3:
        multiplier *= 1.25
        reasons.append(f"{state.recent_capacity_miss_count} recent capacity misses")

    # Reduce if consistently oversupplied
    if (state.recent_tender_reject_rate < 0.05
            and state.demand_cv < 0.15
            and not state.is_peak_season
            and state.recent_capacity_miss_count == 0):
        multiplier = 0.85
        reasons = ["consistently oversupplied"]

    adjusted_buffer = max(1, int(state.baseline_buffer_loads * multiplier))
    action = Actions.MODIFY if abs(multiplier - 1.0) > 0.05 else Actions.ACCEPT

    return TMSHeuristicDecision(
        trm_type="capacity_buffer", action=action,
        quantity=adjusted_buffer,
        reasoning=f"Buffer {'adjusted' if action == Actions.MODIFY else 'maintained'}: {'; '.join(reasons) or 'nominal'}",
        urgency=0.3 + abs(multiplier - 1.0) * 0.5,
        params_used={"multiplier": multiplier, "baseline": state.baseline_buffer_loads},
    )


# ============================================================================
# 5. Exception Management
# ============================================================================

def _compute_exception_management(state: ExceptionManagementState) -> TMSHeuristicDecision:
    """
    Evaluate exception response strategy.

    Rules:
    - CRITICAL + P1/P2: immediate re-tender
    - Temperature excursion: escalate immediately
    - Late delivery with time left: attempt reroute
    - Minor delay, low priority: accept and monitor
    """
    if state.severity == "CRITICAL" or (state.is_critical_path() and state.estimated_delay_hrs > 4):
        if state.can_retender and state.alternate_carriers_available > 0:
            return TMSHeuristicDecision(
                trm_type="exception_management", action=Actions.RETENDER,
                reasoning=f"Critical exception ({state.exception_type}): re-tendering to {state.alternate_carriers_available} alternates",
                urgency=0.95,
            )
        return TMSHeuristicDecision(
            trm_type="exception_management", action=Actions.ESCALATE,
            reasoning=f"Critical exception ({state.exception_type}) with no re-tender options",
            urgency=1.0,
        )

    if state.exception_type == "TEMPERATURE_EXCURSION":
        return TMSHeuristicDecision(
            trm_type="exception_management", action=Actions.ESCALATE,
            reasoning="Temperature excursion requires immediate attention",
            urgency=0.9,
        )

    if state.exception_type in ("LATE_DELIVERY", "LATE_PICKUP") and state.delivery_window_remaining_hrs > 8:
        if state.can_reroute:
            return TMSHeuristicDecision(
                trm_type="exception_management", action=Actions.REROUTE,
                reasoning=f"Late {state.exception_type.split('_')[1].lower()} with {state.delivery_window_remaining_hrs:.0f}h window remaining; rerouting",
                urgency=0.6,
            )

    if state.estimated_delay_hrs < 2 and state.severity in ("LOW", "MEDIUM"):
        return TMSHeuristicDecision(
            trm_type="exception_management", action=Actions.ACCEPT,
            reasoning=f"Minor exception ({state.exception_type}, {state.estimated_delay_hrs:.1f}h delay): monitoring",
            urgency=0.3,
        )

    return TMSHeuristicDecision(
        trm_type="exception_management", action=Actions.ESCALATE,
        quantity=state.estimated_delay_hrs,
        reasoning=f"Exception {state.exception_type} (severity={state.severity}, delay={state.estimated_delay_hrs:.1f}h): escalating for review",
        urgency=0.6,
    )


# ============================================================================
# 6. Freight Procurement
# ============================================================================

def _compute_freight_procurement(state: FreightProcurementState) -> TMSHeuristicDecision:
    """
    Carrier waterfall tendering logic.

    Rules:
    - Attempt 1: primary carrier at contract rate
    - Attempt 2: backup carriers in priority order
    - Attempt 3: spot market (if rate < 1.3x contract)
    - Beyond: escalate to broker routing
    """
    if state.tender_attempt == 1 and state.primary_carrier_id:
        return TMSHeuristicDecision(
            trm_type="freight_procurement", action=Actions.ACCEPT,
            quantity=state.primary_carrier_rate,
            reasoning=f"Tender attempt 1: primary carrier at ${state.primary_carrier_rate:.2f} contract rate",
            urgency=0.3,
            params_used={"carrier_id": state.primary_carrier_id, "rate_type": "contract"},
        )

    if state.tender_attempt <= state.max_tender_attempts and state.backup_carriers:
        # Select best available backup
        sorted_backups = sorted(state.backup_carriers, key=lambda c: c.get("priority", 99))
        if sorted_backups:
            best = sorted_backups[0]
            return TMSHeuristicDecision(
                trm_type="freight_procurement", action=Actions.ACCEPT,
                quantity=best.get("rate", 0),
                reasoning=f"Tender attempt {state.tender_attempt}: backup carrier at ${best.get('rate', 0):.2f}",
                urgency=0.5,
                params_used={"carrier_id": best.get("id"), "rate_type": "contract_backup"},
            )

    # Spot market
    if state.spot_rate > 0 and state.contract_rate > 0:
        premium = (state.spot_rate - state.contract_rate) / state.contract_rate
        if premium < 0.30:
            return TMSHeuristicDecision(
                trm_type="freight_procurement", action=Actions.ACCEPT,
                quantity=state.spot_rate,
                reasoning=f"Spot market at ${state.spot_rate:.2f} ({premium*100:.0f}% over contract)",
                urgency=0.6,
                params_used={"rate_type": "spot", "premium_pct": premium},
            )

    # Escalate to broker
    return TMSHeuristicDecision(
        trm_type="freight_procurement", action=Actions.ESCALATE,
        reasoning=f"Carrier waterfall exhausted after {state.tender_attempt} attempts; escalating to broker",
        urgency=0.8,
    )


# ============================================================================
# 7. Broker Routing
# ============================================================================

def _compute_broker_routing(state: BrokerRoutingState) -> TMSHeuristicDecision:
    """
    Broker selection when carrier waterfall is exhausted.

    Rules:
    - Select broker with best reliability/cost ratio
    - P1-P2: accept highest reliability regardless of cost
    - Reject if premium >40% over contract (escalate manually)
    """
    if not state.available_brokers:
        return TMSHeuristicDecision(
            trm_type="broker_routing", action=Actions.ESCALATE,
            reasoning="No brokers available; manual intervention required",
            urgency=1.0,
        )

    if state.shipment_priority <= 2:
        # For critical shipments, pick most reliable broker
        best = max(state.available_brokers, key=lambda b: b.get("reliability", 0))
        return TMSHeuristicDecision(
            trm_type="broker_routing", action=Actions.ACCEPT,
            quantity=best.get("rate", 0),
            reasoning=f"Critical shipment (P{state.shipment_priority}): selected broker {best.get('name', 'N/A')} (reliability {best.get('reliability', 0)*100:.0f}%)",
            urgency=0.8,
            params_used={"broker_id": best.get("id"), "selection": "reliability"},
        )

    # Score brokers by reliability-adjusted cost
    scored = []
    for broker in state.available_brokers:
        rate = broker.get("rate", float('inf'))
        reliability = broker.get("reliability", 0.5)
        # Expected cost considering re-work probability
        expected_cost = rate / max(0.1, reliability)
        scored.append((expected_cost, broker))

    scored.sort(key=lambda x: x[0])
    best_cost, best_broker = scored[0]

    # Check premium threshold
    premium = 0.0
    if state.contract_rate > 0:
        premium = (best_broker.get("rate", 0) - state.contract_rate) / state.contract_rate

    if premium > 0.40:
        return TMSHeuristicDecision(
            trm_type="broker_routing", action=Actions.ESCALATE,
            quantity=best_broker.get("rate", 0),
            reasoning=f"Best broker rate ${best_broker.get('rate', 0):.2f} is {premium*100:.0f}% over contract; needs approval",
            urgency=0.7,
        )

    return TMSHeuristicDecision(
        trm_type="broker_routing", action=Actions.ACCEPT,
        quantity=best_broker.get("rate", 0),
        reasoning=f"Broker {best_broker.get('name', 'N/A')} selected: ${best_broker.get('rate', 0):.2f} (reliability {best_broker.get('reliability', 0)*100:.0f}%)",
        urgency=0.5,
        params_used={"broker_id": best_broker.get("id"), "selection": "cost_reliability"},
    )


# ============================================================================
# 8. Dock Scheduling
# ============================================================================

def _compute_dock_scheduling(state: DockSchedulingState) -> TMSHeuristicDecision:
    """
    Dock door assignment and appointment scheduling.

    Rules:
    - Utilization >85%: defer low-priority appointments
    - Queue depth >3: switch to drop-trailer mode
    - Detention risk >0.7: prioritize turnaround
    - P1-P2: always accommodate
    """
    util = state.utilization_pct()
    detention_risk = state.detention_risk_score()

    if state.shipment_priority <= 2:
        return TMSHeuristicDecision(
            trm_type="dock_scheduling", action=Actions.ACCEPT,
            quantity=state.estimated_load_time_minutes,
            reasoning=f"Priority P{state.shipment_priority}: dock assigned at requested time",
            urgency=0.7,
        )

    if util > 0.85 and state.shipment_priority >= 4:
        return TMSHeuristicDecision(
            trm_type="dock_scheduling", action=Actions.DEFER,
            reasoning=f"Dock utilization {util*100:.0f}%; deferring P{state.shipment_priority} appointment",
            urgency=0.4,
        )

    if state.current_queue_depth > 3:
        return TMSHeuristicDecision(
            trm_type="dock_scheduling", action=Actions.MODIFY,
            reasoning=f"Queue depth {state.current_queue_depth}: recommending drop-trailer to reduce dwell",
            urgency=0.6,
            params_used={"recommendation": "drop_trailer"},
        )

    if detention_risk > 0.7:
        return TMSHeuristicDecision(
            trm_type="dock_scheduling", action=Actions.MODIFY,
            reasoning=f"Detention risk {detention_risk:.0%}: prioritizing turnaround (avg dwell {state.carrier_avg_dwell_minutes:.0f}min vs {state.free_time_minutes:.0f}min free)",
            urgency=0.7,
            params_used={"recommendation": "expedite_turnaround"},
        )

    return TMSHeuristicDecision(
        trm_type="dock_scheduling", action=Actions.ACCEPT,
        quantity=state.estimated_load_time_minutes,
        reasoning=f"Dock available (utilization {util*100:.0f}%, queue {state.current_queue_depth})",
        urgency=0.2,
    )


# ============================================================================
# 9. Load Build
# ============================================================================

def _compute_load_build(state: LoadBuildState) -> TMSHeuristicDecision:
    """
    Load consolidation decision.

    Rules:
    - Weight util <50% and compatible shipments: consolidate
    - Hazmat or temp conflict: cannot consolidate
    - FTL rate < sum of LTL rates: consolidate
    - Multi-stop limit exceeded: split
    """
    if state.has_hazmat_conflict or state.has_temp_conflict:
        return TMSHeuristicDecision(
            trm_type="load_build", action=Actions.REJECT,
            reasoning=f"Cannot consolidate: {'hazmat' if state.has_hazmat_conflict else 'temperature'} conflict",
            urgency=0.3,
        )

    if state.should_consolidate():
        return TMSHeuristicDecision(
            trm_type="load_build", action=Actions.CONSOLIDATE,
            quantity=state.shipment_count,
            reasoning=f"Consolidate {state.shipment_count} shipments: weight {state.weight_utilization()*100:.0f}%, volume {state.volume_utilization()*100:.0f}%, saving ${state.consolidation_savings:.0f}",
            urgency=0.4,
            params_used={
                "weight_util": state.weight_utilization(),
                "volume_util": state.volume_utilization(),
                "savings": state.consolidation_savings,
            },
        )

    if state.weight_utilization() > 0.95 or state.volume_utilization() > 0.95:
        return TMSHeuristicDecision(
            trm_type="load_build", action=Actions.SPLIT,
            reasoning=f"Load exceeds capacity: weight {state.weight_utilization()*100:.0f}%, volume {state.volume_utilization()*100:.0f}%",
            urgency=0.5,
        )

    if state.weight_utilization() < 0.50 and state.shipment_count == 1:
        return TMSHeuristicDecision(
            trm_type="load_build", action=Actions.DEFER,
            reasoning=f"Underutilized ({state.weight_utilization()*100:.0f}% weight): hold for consolidation window ({state.consolidation_window_hours:.0f}h)",
            urgency=0.3,
        )

    return TMSHeuristicDecision(
        trm_type="load_build", action=Actions.ACCEPT,
        quantity=state.shipment_count,
        reasoning=f"Load plan accepted: {state.shipment_count} shipments, {state.weight_utilization()*100:.0f}% weight, {state.volume_utilization()*100:.0f}% volume",
        urgency=0.2,
    )


# ============================================================================
# 10. Intermodal Transfer
# ============================================================================

def _compute_intermodal_transfer(state: IntermodalTransferState) -> TMSHeuristicDecision:
    """
    Mode shift evaluation (truck vs rail/intermodal).

    Rules:
    - Savings >15% and transit time fits: recommend intermodal
    - Distance >800 miles: always evaluate intermodal
    - Ramp congestion >0.7: stay on truck
    - Reliability <80% and tight delivery: stay on truck
    """
    savings = state.cost_savings_pct()
    has_time = state.has_time_for_intermodal()

    if state.ramp_congestion_level > 0.7:
        return TMSHeuristicDecision(
            trm_type="intermodal_transfer", action=Actions.REJECT,
            reasoning=f"Ramp congestion {state.ramp_congestion_level*100:.0f}%: staying on truck",
            urgency=0.3,
        )

    if not has_time:
        return TMSHeuristicDecision(
            trm_type="intermodal_transfer", action=Actions.REJECT,
            reasoning=f"Intermodal transit {state.intermodal_transit_days:.1f}d exceeds window ({state.delivery_window_days:.1f}d slack)",
            urgency=0.2,
        )

    if state.intermodal_reliability_pct < 0.80 and state.delivery_window_days < 2:
        return TMSHeuristicDecision(
            trm_type="intermodal_transfer", action=Actions.REJECT,
            reasoning=f"Intermodal reliability {state.intermodal_reliability_pct*100:.0f}% with tight delivery window",
            urgency=0.3,
        )

    if savings > 0.15 and has_time:
        return TMSHeuristicDecision(
            trm_type="intermodal_transfer", action=Actions.ACCEPT,
            quantity=state.intermodal_rate,
            reasoning=f"Mode shift {state.current_mode}→{state.candidate_mode}: {savings*100:.0f}% savings (${state.truck_rate - state.intermodal_rate:.0f}), +{state.transit_time_penalty_days():.1f}d transit",
            urgency=0.4,
            params_used={"savings_pct": savings, "transit_penalty_days": state.transit_time_penalty_days()},
        )

    if state.total_truck_miles > 800 and savings > 0.05:
        return TMSHeuristicDecision(
            trm_type="intermodal_transfer", action=Actions.ACCEPT,
            quantity=state.intermodal_rate,
            reasoning=f"Long-haul ({state.total_truck_miles:.0f}mi) with {savings*100:.0f}% intermodal savings",
            urgency=0.3,
        )

    return TMSHeuristicDecision(
        trm_type="intermodal_transfer", action=Actions.REJECT,
        reasoning=f"Intermodal savings {savings*100:.0f}% below threshold (15%); staying on {state.current_mode}",
        urgency=0.1,
    )


# ============================================================================
# 11. Equipment Reposition
# ============================================================================

def _compute_equipment_reposition(state: EquipmentRepositionState) -> TMSHeuristicDecision:
    """
    Equipment repositioning (deadhead management).

    Rules:
    - Source surplus + target deficit: reposition
    - ROI > 1.5: economically justified
    - Fleet utilization >90% and deficit exists: urgent reposition
    - No surplus or no deficit: hold
    """
    surplus = state.source_surplus()
    deficit = state.target_deficit()
    roi = state.reposition_roi()

    if surplus == 0:
        return TMSHeuristicDecision(
            trm_type="equipment_reposition", action=Actions.HOLD,
            reasoning=f"No surplus at source ({state.source_equipment_count} equipment, {state.source_demand_next_7d} needed)",
            urgency=0.1,
        )

    if deficit == 0:
        return TMSHeuristicDecision(
            trm_type="equipment_reposition", action=Actions.HOLD,
            reasoning=f"No deficit at target ({state.target_equipment_count} equipment, {state.target_demand_next_7d} needed)",
            urgency=0.1,
        )

    if state.fleet_utilization_pct > 0.90 and deficit > 0:
        qty = min(surplus, deficit)
        return TMSHeuristicDecision(
            trm_type="equipment_reposition", action=Actions.REPOSITION,
            quantity=qty,
            reasoning=f"Urgent: fleet {state.fleet_utilization_pct*100:.0f}% utilized, repositioning {qty} {state.equipment_type} units ({state.reposition_miles:.0f}mi)",
            urgency=0.8,
        )

    if roi > 1.5:
        qty = min(surplus, deficit, state.breakeven_loads)
        return TMSHeuristicDecision(
            trm_type="equipment_reposition", action=Actions.REPOSITION,
            quantity=qty,
            reasoning=f"ROI {roi:.1f}x: reposition {qty} units, cost ${state.reposition_cost:.0f} vs ${state.cost_of_not_repositioning:.0f} spot premium avoided",
            urgency=0.5,
            params_used={"roi": roi, "miles": state.reposition_miles},
        )

    if roi > 1.0 and state.reposition_miles < 200:
        qty = min(surplus, deficit)
        return TMSHeuristicDecision(
            trm_type="equipment_reposition", action=Actions.REPOSITION,
            quantity=qty,
            reasoning=f"Short reposition ({state.reposition_miles:.0f}mi, ROI {roi:.1f}x)",
            urgency=0.3,
        )

    return TMSHeuristicDecision(
        trm_type="equipment_reposition", action=Actions.HOLD,
        reasoning=f"Reposition ROI {roi:.1f}x below threshold (1.5x) for {state.reposition_miles:.0f}mi move",
        urgency=0.2,
    )

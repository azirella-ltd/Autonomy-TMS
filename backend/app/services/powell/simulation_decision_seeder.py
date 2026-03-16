"""
Simulation Decision Seeder
==========================

Generates diverse, realistic powell_*_decisions records from the digital twin
simulation so that the Decision Stream has meaningful content immediately after
provisioning — without waiting for production decision cycles.

Runs 5 episodes x 90 days of lightweight simulation, examines supply chain
state at each tick, and generates decision records when interesting conditions
arise.  Uses reservoir sampling to keep only the highest-urgency / highest-
impact decisions (max_per_type defaults to 6, yielding ~60-80 total decisions).

All simulation infrastructure is reused from simulation_calibration_service.py.
"""

import logging
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.powell.simulation_calibration_service import (
    _BscWeights,
    _ConfigLoader,
    _DagChain,
    _SimSite,
    _SiteSimConfig,
    _StochasticDemand,
    _StochasticLeadTime,
)
from app.models.powell_decisions import (
    PowellATPDecision,
    PowellBufferDecision,
    PowellForecastAdjustmentDecision,
    PowellMaintenanceDecision,
    PowellMODecision,
    PowellOrderException,
    PowellPODecision,
    PowellQualityDecision,
    PowellRebalanceDecision,
    PowellSubcontractingDecision,
    PowellTODecision,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_N_EPISODES = 5
_N_DAYS = 90
_WARMUP_DAYS = 10  # skip early transients

# Asset IDs for maintenance decisions
_ASSET_IDS = ["COOL-01", "CONV-02", "FORK-03", "RACK-04", "DOCK-05"]

# Thresholds for decision generation
_FORECAST_ERROR_THRESHOLD = 0.15
_DOS_IMBALANCE_THRESHOLD = 0.20
_UTILIZATION_HIGH = 0.85
_UTILIZATION_CRITICAL = 0.90
_QUALITY_THRESHOLD = 0.95
_BACKLOG_SEVERITY_MAP = {
    (0.0, 0.5): "low",
    (0.5, 1.0): "medium",
    (1.0, 2.0): "high",
    (2.0, float("inf")): "critical",
}


# ---------------------------------------------------------------------------
# Candidate decision (for reservoir sampling)
# ---------------------------------------------------------------------------

class _Candidate:
    """A candidate decision record with a priority score for reservoir sampling."""

    __slots__ = ("score", "record")

    def __init__(self, score: float, record: Any):
        self.score = score   # higher = more interesting
        self.record = record


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_product_descriptions(db: Session, config_id: int) -> Dict[str, str]:
    """product_id -> description"""
    from app.models.sc_entities import Product
    from app.models.supply_chain_config import Site

    # Get products linked to this config via sites/inv_policy/forecast
    rows = (
        db.query(Product.id, Product.description, Product.unit_cost)
        .all()
    )
    return {r.id: (r.description or r.id) for r in rows}


def _load_product_costs(db: Session) -> Dict[str, float]:
    """product_id -> unit_cost"""
    from app.models.sc_entities import Product
    rows = db.query(Product.id, Product.unit_cost).all()
    return {r.id: float(r.unit_cost) if r.unit_cost else 5.0 for r in rows}


def _load_vendor_names(db: Session, config_id: int) -> Dict[int, str]:
    """site_id -> vendor name for external vendor sites."""
    from app.models.supply_chain_config import Site
    rows = (
        db.query(Site.id, Site.name)
        .filter(
            Site.config_id == config_id,
            Site.is_external == True,
            Site.tpartner_type == "vendor",
        )
        .all()
    )
    return {r.id: r.name for r in rows}


def _spread_timestamps(n: int, days_back: int = 7) -> List[datetime]:
    """Generate n timestamps spread across the last `days_back` days."""
    now = datetime.utcnow()
    rng = random.Random(42)
    stamps = []
    for _ in range(n):
        offset_secs = rng.randint(0, days_back * 86400)
        stamps.append(now - timedelta(seconds=offset_secs))
    stamps.sort()
    return stamps


def _severity_from_ratio(ratio: float) -> str:
    for (lo, hi), sev in _BACKLOG_SEVERITY_MAP.items():
        if lo <= ratio < hi:
            return sev
    return "critical"


# ---------------------------------------------------------------------------
# Decision generators — each returns a list of _Candidate
# ---------------------------------------------------------------------------

def _gen_po_creation(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    vendor_name: str,
    day: int,
    episode: int,
) -> Optional[_Candidate]:
    """PO when inventory position < reorder point."""
    ip = node.inventory_position
    if ip >= cfg.reorder_point:
        return None

    gap = cfg.reorder_point - ip
    recommended_qty = max(0.0, cfg.order_up_to - ip)
    if recommended_qty <= 0:
        return None

    expected_cost = round(recommended_qty * unit_cost, 2)
    dos = node.inventory / max(node.avg_daily_demand, 0.01)

    # Urgency: how far below ROP
    urgency_score = min(1.0, gap / max(cfg.reorder_point, 1.0))

    # Pick trigger reason based on state
    if node.period_stockout:
        trigger = "safety_stock_breach"
    elif node.period_demand > cfg.demand_mean_daily * 1.3:
        trigger = "demand_surge"
    else:
        trigger = "replenishment"

    # Confidence from fill rate stability
    confidence = min(0.95, max(0.40, node.period_fill_rate * 0.85 + 0.10))

    reasoning = (
        f"Inventory position for {product_desc} at {cfg.site_name} has dropped to "
        f"{ip:.0f} units, below the reorder point of {cfg.reorder_point:.0f}. "
        f"Recommending a purchase order of {recommended_qty:.0f} units from {vendor_name} "
        f"at an estimated cost of ${expected_cost:,.2f} (${unit_cost:.2f}/unit). "
        f"Current days of supply: {dos:.1f}. "
        f"Daily demand average: {node.avg_daily_demand:.1f} units. "
        f"Trigger: {trigger.replace('_', ' ')}."
    )

    urgency_label = "high" if urgency_score > 0.6 else ("medium" if urgency_score > 0.3 else "low")

    record = PowellPODecision(
        config_id=config_id,
        product_id=cfg.product_id,
        location_id=cfg.site_name,
        supplier_id=vendor_name,
        recommended_qty=round(recommended_qty, 1),
        trigger_reason=trigger,
        urgency=urgency_label,
        confidence=round(confidence, 3),
        inventory_position=round(ip, 1),
        days_of_supply=round(dos, 1),
        forecast_30_day=round(node.avg_daily_demand * 30, 1),
        expected_cost=expected_cost,
        decision_method="heuristic",
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        # Outcomes (realistic for CDT calibration)
        was_executed=True,
        actual_qty=round(recommended_qty * random.uniform(0.95, 1.05), 1),
        actual_cost=round(expected_cost * random.uniform(0.97, 1.03), 2),
    )
    return _Candidate(score=urgency_score + (0.2 if trigger != "replenishment" else 0.0), record=record)


def _gen_atp_executor(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """ATP decision when demand arrives."""
    demand = node.period_demand
    if demand <= 0:
        return None

    available = node.inventory + demand  # pre-fulfillment
    can_fulfill = available >= demand
    promised = min(available, demand)
    priority = random.choice([1, 2, 2, 3, 3, 3, 4, 5])

    # More interesting when partial or cannot fulfill
    if can_fulfill and node.period_fill_rate > 0.98:
        interest = 0.1
    elif can_fulfill:
        interest = 0.3
    else:
        interest = 0.7 + min(0.3, node.backlog / max(demand, 1.0) * 0.3)

    confidence = min(0.95, max(0.35, node.period_fill_rate * 0.80 + 0.15))
    order_id = f"ORD-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"

    if can_fulfill:
        reason = "full_fulfill"
        reason_text = f"Full fulfillment of {demand:.0f} units"
    elif promised > 0:
        reason = "partial_fulfill"
        reason_text = (
            f"Partial fulfillment: {promised:.0f} of {demand:.0f} units requested. "
            f"Shortfall of {demand - promised:.0f} units added to backlog."
        )
    else:
        reason = "cannot_fulfill"
        reason_text = f"Cannot fulfill: zero inventory available. {demand:.0f} units backordered."

    reasoning = (
        f"ATP check for {product_desc} at {cfg.site_name}: "
        f"{reason_text} "
        f"Available inventory: {node.inventory:.0f} units. "
        f"Backlog: {node.backlog:.0f} units. Priority {priority}."
    )

    record = PowellATPDecision(
        config_id=config_id,
        order_id=order_id,
        product_id=cfg.product_id,
        location_id=cfg.site_name,
        requested_qty=round(demand, 1),
        order_priority=priority,
        can_fulfill=can_fulfill,
        promised_qty=round(promised, 1),
        decision_method="heuristic",
        confidence=round(confidence, 3),
        reason=reason,
        decision_reasoning=reasoning,
        urgency_at_time=round(interest, 3),
        was_committed=True,
        actual_fulfilled_qty=round(promised * random.uniform(0.97, 1.0), 1),
    )
    return _Candidate(score=interest, record=record)


def _gen_order_tracking(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """Order exception when backlog exceeds threshold."""
    threshold = node.avg_daily_demand * cfg.lead_time_days
    if node.backlog <= threshold * 0.5:
        return None

    backlog_ratio = node.backlog / max(threshold, 1.0)
    severity = _severity_from_ratio(backlog_ratio)
    urgency_score = min(1.0, backlog_ratio * 0.5)

    exception_types = ["late_delivery", "quantity_shortfall", "quality_hold"]
    weights = [0.5, 0.35, 0.15]
    exception_type = random.choices(exception_types, weights=weights, k=1)[0]

    actions = {
        "late_delivery": ["expedite", "find_alternate", "escalate_supplier"],
        "quantity_shortfall": ["split_shipment", "find_alternate", "expedite"],
        "quality_hold": ["escalate_supplier", "find_alternate", "split_shipment"],
    }
    recommended_action = random.choice(actions[exception_type])
    order_id = f"EXC-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"

    impact_cost = round(node.backlog * unit_cost * 0.15, 2)
    confidence = min(0.92, max(0.45, 1.0 - backlog_ratio * 0.3))

    reasoning = (
        f"Order exception detected at {cfg.site_name} for {product_desc}: "
        f"{exception_type.replace('_', ' ')}. "
        f"Current backlog: {node.backlog:.0f} units (${node.backlog * unit_cost:,.2f}). "
        f"Backlog ratio: {backlog_ratio:.1%} of lead-time demand. "
        f"Severity: {severity}. "
        f"Estimated impact cost: ${impact_cost:,.2f}. "
        f"Recommended action: {recommended_action.replace('_', ' ')}."
    )

    record = PowellOrderException(
        config_id=config_id,
        order_id=order_id,
        order_type="purchase_order",
        order_status="delayed",
        exception_type=exception_type,
        severity=severity,
        recommended_action=recommended_action,
        description=reasoning[:500],
        estimated_impact_cost=impact_cost,
        confidence=round(confidence, 3),
        reason=exception_type,
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        action_taken=recommended_action,
        resolution_time_hours=round(random.uniform(2.0, 48.0), 1),
        actual_impact_cost=round(impact_cost * random.uniform(0.6, 1.2), 2),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_inventory_buffer(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    day: int,
    prev_demand_cv: float,
) -> Optional[_Candidate]:
    """Buffer adjustment when demand CV changes significantly or stockout occurs."""
    cv_change = abs(node.demand_cv - prev_demand_cv) / max(prev_demand_cv, 0.01)
    triggered_by_cv = cv_change > 0.15
    triggered_by_stockout = node.period_stockout

    if not triggered_by_cv and not triggered_by_stockout:
        return None

    baseline_ss = cfg.safety_stock
    if baseline_ss <= 0:
        baseline_ss = cfg.demand_mean_daily * math.sqrt(cfg.lead_time_days) * 1.645 * cfg.demand_cv

    if triggered_by_stockout:
        multiplier = round(random.uniform(1.10, 1.35), 2)
        reason = "service_level_drop"
    elif node.demand_cv > prev_demand_cv:
        multiplier = round(random.uniform(1.05, 1.25), 2)
        reason = "demand_surge"
    else:
        multiplier = round(random.uniform(0.80, 0.95), 2)
        reason = "seasonal_transition"

    adjusted_ss = round(baseline_ss * multiplier, 1)
    dos = node.inventory / max(node.avg_daily_demand, 0.01)

    urgency_score = 0.3
    if triggered_by_stockout:
        urgency_score = 0.7
    elif cv_change > 0.30:
        urgency_score = 0.5

    confidence = min(0.90, max(0.45, 1.0 - node.demand_cv * 0.5))

    reasoning = (
        f"Inventory buffer adjustment for {product_desc} at {cfg.site_name}: "
        f"{'Stockout detected — ' if triggered_by_stockout else ''}"
        f"demand CV shifted from {prev_demand_cv:.2f} to {node.demand_cv:.2f} "
        f"({cv_change:.0%} change). "
        f"Adjusting safety stock from {baseline_ss:.0f} to {adjusted_ss:.0f} units "
        f"(multiplier {multiplier:.2f}x). "
        f"Current DOS: {dos:.1f} days. "
        f"Estimated additional holding cost: ${(adjusted_ss - baseline_ss) * cfg.holding_cost_daily * 30:,.2f}/month."
    )

    record = PowellBufferDecision(
        config_id=config_id,
        product_id=cfg.product_id,
        location_id=cfg.site_name,
        baseline_ss=round(baseline_ss, 1),
        multiplier=multiplier,
        adjusted_ss=adjusted_ss,
        reason=reason,
        confidence=round(confidence, 3),
        demand_cv=round(node.demand_cv, 3),
        current_dos=round(dos, 1),
        recent_stockout_count=1 if triggered_by_stockout else 0,
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_applied=True,
        actual_stockout_occurred=triggered_by_stockout,
        actual_dos_after=round(dos * multiplier * random.uniform(0.9, 1.1), 1),
        excess_holding_cost=round(max(0, adjusted_ss - baseline_ss) * cfg.holding_cost_daily * 14, 2),
        actual_service_level=round(random.uniform(0.90, 0.99), 3),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_rebalancing(
    nodes: Dict[int, _SimSite],
    configs: Dict[int, _SiteSimConfig],
    config_id: int,
    product_descs: Dict[str, str],
    network_avg_dos: float,
    day: int,
) -> List[_Candidate]:
    """Rebalancing when DOS imbalance exceeds threshold between sites."""
    candidates = []

    # Find sites with the same product and significant DOS imbalance
    site_dos = {}
    for sid, node in nodes.items():
        avg_demand = node.avg_daily_demand
        if avg_demand > 0.01:
            site_dos[sid] = node.inventory / avg_demand

    if len(site_dos) < 2:
        return candidates

    dos_values = list(site_dos.values())
    avg_dos = statistics.mean(dos_values)
    if avg_dos <= 0:
        return candidates

    # Find overstocked and understocked pairs
    overstocked = [(sid, dos) for sid, dos in site_dos.items() if dos > avg_dos * 1.2]
    understocked = [(sid, dos) for sid, dos in site_dos.items() if dos < avg_dos * 0.8]

    for from_sid, from_dos in overstocked:
        for to_sid, to_dos in understocked:
            from_cfg = configs[from_sid]
            to_cfg = configs[to_sid]
            from_node = nodes[from_sid]
            to_node = nodes[to_sid]

            imbalance = (from_dos - to_dos) / max(avg_dos, 1.0)
            if imbalance < _DOS_IMBALANCE_THRESHOLD:
                continue

            # Transfer qty to equalize DOS
            target_dos = avg_dos
            transfer_qty = max(0, (from_dos - target_dos) * from_node.avg_daily_demand)
            transfer_qty = min(transfer_qty, from_node.inventory * 0.3)  # cap at 30% of source inventory
            if transfer_qty < 1:
                continue

            product_id = from_cfg.product_id
            product_desc = product_descs.get(product_id, product_id)
            urgency_score = min(1.0, imbalance * 0.6)
            confidence = min(0.90, max(0.45, 1.0 - imbalance * 0.3))

            source_dos_after = from_dos - transfer_qty / max(from_node.avg_daily_demand, 0.01)
            dest_dos_after = to_dos + transfer_qty / max(to_node.avg_daily_demand, 0.01)

            reasoning = (
                f"Inventory rebalancing for {product_desc}: "
                f"{from_cfg.site_name} has {from_dos:.1f} DOS (overstocked) while "
                f"{to_cfg.site_name} has {to_dos:.1f} DOS (understocked). "
                f"Network average: {avg_dos:.1f} DOS. "
                f"Recommending transfer of {transfer_qty:.0f} units. "
                f"Expected DOS after transfer: {from_cfg.site_name} {source_dos_after:.1f}, "
                f"{to_cfg.site_name} {dest_dos_after:.1f}."
            )

            record = PowellRebalanceDecision(
                config_id=config_id,
                product_id=product_id,
                from_site=from_cfg.site_name,
                to_site=to_cfg.site_name,
                recommended_qty=round(transfer_qty, 1),
                reason="dos_imbalance",
                urgency=round(urgency_score, 3),
                confidence=round(confidence, 3),
                source_dos_before=round(from_dos, 1),
                source_dos_after=round(source_dos_after, 1),
                dest_dos_before=round(to_dos, 1),
                dest_dos_after=round(dest_dos_after, 1),
                decision_reasoning=reasoning,
                urgency_at_time=round(urgency_score, 3),
                was_executed=True,
                actual_qty=round(transfer_qty * random.uniform(0.95, 1.0), 1),
                actual_cost=round(transfer_qty * 0.50, 2),  # transport cost estimate
                service_impact=round(random.uniform(0.01, 0.05), 3),
            )
            candidates.append(_Candidate(score=urgency_score, record=record))

    return candidates


def _gen_mo_execution(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """MO decision when upstream site has capacity pressure."""
    if cfg.master_type not in ("MANUFACTURER",):
        return None

    utilization = node._capacity_used / max(node._capacity_total, 1.0)
    if utilization < 0.60:
        return None

    # Decision type based on utilization level
    if utilization > 0.95:
        decision_type = "expedite"
        urgency_score = 0.8
    elif utilization > _UTILIZATION_HIGH:
        decision_type = "release"
        urgency_score = 0.5
    elif node.backlog > node.avg_daily_demand * 2:
        decision_type = "expedite"
        urgency_score = 0.6
    else:
        decision_type = "release"
        urgency_score = 0.3

    planned_qty = round(max(node.period_demand, node.avg_daily_demand) * random.uniform(0.8, 1.5), 1)
    production_order_id = f"MO-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"
    confidence = min(0.92, max(0.40, 1.0 - utilization * 0.4))

    run_time = planned_qty / max(node._capacity_total, 1.0) * 8.0  # hours
    setup_time = random.uniform(0.5, 2.0)

    reasoning = (
        f"Manufacturing order {decision_type} at {cfg.site_name} for {product_desc}: "
        f"planned quantity {planned_qty:.0f} units (${planned_qty * unit_cost:,.2f}). "
        f"Current utilization: {utilization:.0%}. "
        f"Setup time: {setup_time:.1f}h, run time: {run_time:.1f}h. "
        f"Backlog: {node.backlog:.0f} units. "
        f"{'Capacity near limit — expediting to prevent further backlog buildup.' if decision_type == 'expedite' else 'Standard release within capacity window.'}"
    )

    record = PowellMODecision(
        config_id=config_id,
        production_order_id=production_order_id,
        product_id=cfg.product_id,
        site_id=cfg.site_name,
        planned_qty=planned_qty,
        decision_type=decision_type,
        resource_id=f"LINE-{cfg.site_id % 3 + 1:02d}",
        setup_time_hours=round(setup_time, 1),
        run_time_hours=round(run_time, 1),
        confidence=round(confidence, 3),
        reason="capacity_available" if decision_type == "release" else "demand_pull",
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_executed=True,
        actual_qty=round(planned_qty * random.uniform(0.92, 1.0), 1),
        actual_yield_pct=round(random.uniform(0.94, 0.99), 3),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_to_execution(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    upstream_name: str,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """TO decision when replenishment is triggered."""
    if node.period_order_qty <= 0:
        return None
    if not cfg.upstream_site_id:
        return None

    qty = node.period_order_qty
    transfer_order_id = f"TO-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"

    # Decision type based on urgency
    if node.period_stockout:
        decision_type = "expedite"
        urgency_score = 0.7
        trigger = "stockout_prevention"
    elif node.inventory < cfg.safety_stock:
        decision_type = "release"
        urgency_score = 0.4
        trigger = "mrp_planned"
    else:
        decision_type = "release"
        urgency_score = 0.2
        trigger = "mrp_planned"

    confidence = min(0.92, max(0.45, node.period_fill_rate * 0.80 + 0.15))
    transit_days = cfg.lead_time_days

    reasoning = (
        f"Transfer order {decision_type} for {product_desc}: "
        f"{qty:.0f} units from {upstream_name} to {cfg.site_name}. "
        f"Estimated transit: {transit_days:.0f} days. "
        f"Trigger: {trigger.replace('_', ' ')}. "
        f"Current inventory at destination: {node.inventory:.0f} units "
        f"(safety stock: {cfg.safety_stock:.0f}). "
        f"{'Expediting due to stockout risk.' if decision_type == 'expedite' else 'Standard release.'}"
    )

    mode = random.choice(["truck", "truck", "truck", "rail", "intermodal"])

    record = PowellTODecision(
        config_id=config_id,
        transfer_order_id=transfer_order_id,
        product_id=cfg.product_id,
        source_site_id=upstream_name,
        dest_site_id=cfg.site_name,
        planned_qty=round(qty, 1),
        decision_type=decision_type,
        transportation_mode=mode,
        estimated_transit_days=round(transit_days, 1),
        priority=2 if decision_type == "expedite" else 3,
        trigger_reason=trigger,
        confidence=round(confidence, 3),
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_executed=True,
        actual_qty=round(qty * random.uniform(0.95, 1.0), 1),
        actual_transit_days=round(transit_days * random.uniform(0.85, 1.20), 1),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_quality_disposition(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """Quality decision when quality outcome is below threshold."""
    quality_val, accepted = node.quality_outcome()
    if accepted and quality_val > 0.97:
        return None  # Only generate for interesting cases

    defect_rate = round(1.0 - quality_val, 4)
    inspection_qty = round(max(node.period_demand, node.avg_daily_demand) * random.uniform(0.5, 1.5), 0)
    quality_order_id = f"QC-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"

    if not accepted:
        if defect_rate > 0.10:
            disposition = "scrap"
            urgency_score = 0.8
        elif defect_rate > 0.05:
            disposition = "rework"
            urgency_score = 0.6
        else:
            disposition = "use_as_is"
            urgency_score = 0.3
    else:
        disposition = "accept"
        urgency_score = 0.15

    confidence = min(0.95, max(0.50, quality_val))

    defect_categories = ["dimensional", "surface_finish", "contamination", "packaging", "labeling"]
    defect_category = random.choice(defect_categories)

    rework_cost = round(inspection_qty * unit_cost * 0.25, 2) if disposition == "rework" else None
    scrap_cost = round(inspection_qty * unit_cost * 0.80, 2) if disposition == "scrap" else None

    reasoning = (
        f"Quality disposition for {product_desc} at {cfg.site_name}: "
        f"lot of {inspection_qty:.0f} units inspected. "
        f"Defect rate: {defect_rate:.1%} ({defect_category}). "
        f"Disposition: {disposition}. "
        f"{'Rework cost estimate: $' + f'{rework_cost:,.2f}. ' if rework_cost else ''}"
        f"{'Scrap cost estimate: $' + f'{scrap_cost:,.2f}. ' if scrap_cost else ''}"
        f"Quality score: {quality_val:.3f} (threshold: {_QUALITY_THRESHOLD})."
    )

    record = PowellQualityDecision(
        config_id=config_id,
        quality_order_id=quality_order_id,
        product_id=cfg.product_id,
        site_id=cfg.site_name,
        lot_number=f"LOT-{episode:02d}{day:03d}",
        inspection_type="incoming",
        inspection_qty=inspection_qty,
        defect_rate=defect_rate,
        defect_category=defect_category,
        severity_level="critical" if defect_rate > 0.10 else ("major" if defect_rate > 0.05 else "minor"),
        disposition=disposition,
        disposition_reason=reasoning[:500],
        rework_cost_estimate=rework_cost,
        scrap_cost_estimate=scrap_cost,
        confidence=round(confidence, 3),
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_executed=True,
        actual_disposition=disposition,
        actual_rework_cost=round(rework_cost * random.uniform(0.8, 1.2), 2) if rework_cost else None,
        actual_scrap_cost=round(scrap_cost * random.uniform(0.9, 1.1), 2) if scrap_cost else None,
        customer_complaints_after=0 if disposition != "use_as_is" else random.choice([0, 0, 0, 1]),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_maintenance_scheduling(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """Maintenance when utilization > 85% or days since PM > 90."""
    utilization = node._capacity_used / max(node._capacity_total, 1.0)
    days_since_pm = node._days_since_pm

    if utilization < 0.70 and days_since_pm < 60:
        return None

    if utilization > _UTILIZATION_HIGH or days_since_pm >= 90:
        if days_since_pm >= 90:
            decision_type = "schedule"
            urgency_score = 0.6
            maint_type = "preventive"
            reason = "preventive_due"
        elif utilization > 0.95:
            decision_type = "expedite"
            urgency_score = 0.7
            maint_type = "condition_based"
            reason = "breakdown_risk"
        else:
            decision_type = "schedule"
            urgency_score = 0.4
            maint_type = "preventive"
            reason = "condition_based"
    elif days_since_pm > 60:
        decision_type = "defer"
        urgency_score = 0.2
        maint_type = "preventive"
        reason = "production_window"
    else:
        return None

    asset_id = _ASSET_IDS[order_seq % len(_ASSET_IDS)]
    maintenance_order_id = f"PM-{config_id:03d}-{episode:02d}{day:03d}-{order_seq:04d}"
    confidence = min(0.92, max(0.45, 1.0 - utilization * 0.3))

    downtime = round(random.uniform(2.0, 8.0), 1)
    production_impact = round(downtime * node.avg_daily_demand / 8.0, 1)

    reasoning = (
        f"Maintenance {decision_type} for asset {asset_id} at {cfg.site_name}: "
        f"utilization {utilization:.0%}, days since last PM: {days_since_pm}. "
        f"Type: {maint_type}. "
        f"Estimated downtime: {downtime:.1f} hours. "
        f"Production impact: ~{production_impact:.0f} units. "
        f"{'Approaching breakdown risk threshold.' if utilization > 0.90 else ''}"
        f"{'PM interval exceeded — scheduling to prevent unplanned downtime.' if days_since_pm >= 90 else ''}"
    )

    record = PowellMaintenanceDecision(
        config_id=config_id,
        maintenance_order_id=maintenance_order_id,
        asset_id=asset_id,
        site_id=cfg.site_name,
        maintenance_type=maint_type,
        decision_type=decision_type,
        estimated_downtime_hours=downtime,
        production_impact_units=production_impact,
        spare_parts_available=random.random() > 0.15,
        priority=2 if urgency_score > 0.5 else 3,
        risk_score_if_deferred=round(min(1.0, utilization * 0.6 + days_since_pm / 180), 2),
        confidence=round(confidence, 3),
        reason=reason,
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_executed=True,
        actual_downtime_hours=round(downtime * random.uniform(0.8, 1.3), 1),
        breakdown_occurred=random.random() < (0.05 if decision_type != "defer" else 0.15),
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_subcontracting(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    unit_cost: float,
    day: int,
    episode: int,
    order_seq: int,
) -> Optional[_Candidate]:
    """Subcontracting when utilization > 90%."""
    if cfg.master_type not in ("MANUFACTURER",):
        return None

    utilization = node._capacity_used / max(node._capacity_total, 1.0)
    if utilization < 0.80:
        return None

    if utilization > _UTILIZATION_CRITICAL:
        decision_type = "route_external"
        urgency_score = 0.7
    elif utilization > _UTILIZATION_HIGH:
        decision_type = "split"
        urgency_score = 0.4
    else:
        decision_type = "keep_internal"
        urgency_score = 0.2

    planned_qty = round(node.avg_daily_demand * random.uniform(1.0, 3.0), 1)
    subcontractor_cost = round(unit_cost * random.uniform(1.15, 1.40), 2)
    confidence = min(0.90, max(0.45, 1.0 - utilization * 0.35))

    subcontractor_id = f"SUB-{(cfg.site_id * 7 + order_seq) % 5 + 1:03d}"

    reasoning = (
        f"Subcontracting decision for {product_desc} at {cfg.site_name}: "
        f"internal utilization at {utilization:.0%}. "
        f"Decision: {decision_type.replace('_', ' ')}. "
        f"Quantity: {planned_qty:.0f} units. "
        f"Internal cost: ${unit_cost:.2f}/unit vs subcontractor: ${subcontractor_cost:.2f}/unit "
        f"({(subcontractor_cost / unit_cost - 1):.0%} premium). "
        f"{'Routing externally to prevent capacity bottleneck.' if decision_type == 'route_external' else ''}"
        f"{'Splitting production to balance load.' if decision_type == 'split' else ''}"
    )

    record = PowellSubcontractingDecision(
        config_id=config_id,
        product_id=cfg.product_id,
        site_id=cfg.site_name,
        subcontractor_id=subcontractor_id,
        planned_qty=planned_qty,
        decision_type=decision_type,
        reason="capacity_constraint" if utilization > 0.90 else "cost_optimization",
        internal_capacity_pct=round(utilization * 100, 1),
        subcontractor_lead_time_days=round(cfg.lead_time_days * random.uniform(1.2, 1.8), 1),
        subcontractor_cost_per_unit=subcontractor_cost,
        internal_cost_per_unit=round(unit_cost, 2),
        quality_score=round(random.uniform(0.88, 0.98), 2),
        on_time_score=round(random.uniform(0.85, 0.97), 2),
        confidence=round(confidence, 3),
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_executed=True,
        actual_qty=round(planned_qty * random.uniform(0.90, 1.0), 1),
        actual_cost=round(planned_qty * subcontractor_cost * random.uniform(0.95, 1.05), 2),
        actual_lead_time_days=round(cfg.lead_time_days * random.uniform(1.1, 1.9), 1),
        quality_passed=random.random() > 0.08,
    )
    return _Candidate(score=urgency_score, record=record)


def _gen_forecast_adjustment(
    node: _SimSite,
    cfg: _SiteSimConfig,
    config_id: int,
    product_desc: str,
    day: int,
) -> Optional[_Candidate]:
    """Forecast adjustment when forecast error exceeds threshold."""
    forecast_error, current_forecast = node.forecast_adjustment_signal()
    if forecast_error < _FORECAST_ERROR_THRESHOLD:
        return None
    if not node._demand_history:
        return None

    actual = node._demand_history[-1]
    direction = "up" if actual > current_forecast else "down"
    adjustment_pct = round(forecast_error * 100, 1)
    adjustment_magnitude = round(abs(actual - current_forecast), 1)
    adjusted_value = round(current_forecast * (1 + forecast_error * (1 if direction == "up" else -1)), 1)

    urgency_score = min(1.0, forecast_error * 1.5)
    confidence = min(0.88, max(0.40, 1.0 - forecast_error * 0.8))

    signal_sources = ["market_intelligence", "sales_input", "customer_feedback"]
    signal_types = {
        "up": ["demand_increase", "seasonal", "promotion"],
        "down": ["demand_decrease", "seasonal", "discontinuation"],
    }

    signal_source = random.choice(signal_sources)
    signal_type = random.choice(signal_types[direction])

    reasoning = (
        f"Forecast adjustment for {product_desc} at {cfg.site_name}: "
        f"actual demand {actual:.0f} vs forecast {current_forecast:.0f} "
        f"(error: {forecast_error:.0%}). "
        f"Adjusting forecast {direction} by {adjustment_pct:.0f}% to {adjusted_value:.0f} units/day. "
        f"Signal source: {signal_source.replace('_', ' ')}. "
        f"Demand CV: {node.demand_cv:.2f}."
    )

    record = PowellForecastAdjustmentDecision(
        config_id=config_id,
        product_id=cfg.product_id,
        site_id=cfg.site_name,
        signal_source=signal_source,
        signal_type=signal_type,
        signal_confidence=round(confidence + random.uniform(-0.05, 0.05), 3),
        current_forecast_value=round(current_forecast, 1),
        adjustment_direction=direction,
        adjustment_magnitude=adjustment_magnitude,
        adjustment_pct=adjustment_pct,
        adjusted_forecast_value=adjusted_value,
        time_horizon_periods=random.choice([4, 8, 12]),
        reason=f"Forecast error of {forecast_error:.0%} exceeds {_FORECAST_ERROR_THRESHOLD:.0%} threshold",
        confidence=round(confidence, 3),
        decision_reasoning=reasoning,
        urgency_at_time=round(urgency_score, 3),
        was_applied=True,
        actual_demand=round(actual, 1),
        forecast_error_before=round(forecast_error, 3),
        forecast_error_after=round(forecast_error * random.uniform(0.3, 0.7), 3),
    )
    return _Candidate(score=urgency_score, record=record)


# ---------------------------------------------------------------------------
# Reservoir sampling: keep top-N by score per TRM type
# ---------------------------------------------------------------------------

def _reservoir_top_n(
    candidates: Dict[str, List[_Candidate]],
    max_per_type: int,
) -> Dict[str, List[Any]]:
    """Select a mix of high-urgency (needs attention) and low-urgency
    (auto-actioned) decisions per TRM type.

    Split: ~60% high-urgency for human review, ~40% low-urgency auto-actioned
    (agent acted autonomously within guardrails).  The auto-actioned decisions
    show users that agents ARE working — they just didn't need human input.
    """
    n_attention = max(2, int(max_per_type * 0.6))
    n_auto = max_per_type - n_attention

    result: Dict[str, List[Any]] = {}
    for trm_type, cands in candidates.items():
        cands.sort(key=lambda c: c.score, reverse=True)
        # Top N by urgency (needs human attention)
        attention = cands[:n_attention]
        # Bottom N by urgency (auto-actioned, within guardrails)
        auto = cands[-n_auto:] if len(cands) > n_attention else []

        # Mark auto-actioned records with low urgency and "auto-actioned" tag
        for c in auto:
            rec = c.record
            rec.urgency_at_time = min(rec.urgency_at_time or 0, 0.15)
            # Append auto-actioned note to reasoning
            if rec.decision_reasoning and "Auto-actioned" not in rec.decision_reasoning:
                rec.decision_reasoning += (
                    " Auto-actioned: confidence was high and risk bound was "
                    "within guardrails — no human review required."
                )
            # Set confidence high for auto-actioned
            if hasattr(rec, 'confidence') and rec.confidence is not None:
                rec.confidence = max(rec.confidence, 0.90)

        records = [c.record for c in attention] + [c.record for c in auto]
        if records:
            result[trm_type] = records
    return result


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

def seed_decisions_from_simulation(
    db: Session,
    config_id: int,
    tenant_id: int,
    max_per_type: int = 6,
) -> Dict[str, int]:
    """
    Run digital twin simulation and seed powell_*_decisions tables with
    diverse, realistic decision records.

    Returns {trm_type: count_seeded}.
    """
    logger.info(
        "Decision seeder: starting %d episodes x %d days for config %d",
        _N_EPISODES, _N_DAYS, config_id,
    )

    # Load config DAG
    loader = _ConfigLoader(db, config_id)
    site_configs, topo_order = loader.load()

    if not site_configs:
        logger.warning("Decision seeder: no internal sites found for config %d", config_id)
        return {}

    # Load reference data
    product_descs = _load_product_descriptions(db, config_id)
    product_costs = _load_product_costs(db)
    vendor_names = _load_vendor_names(db, config_id)

    # Build config lookup
    cfg_by_id: Dict[int, _SiteSimConfig] = {c.site_id: c for c in site_configs}

    # Find default vendor name
    default_vendor = next(iter(vendor_names.values()), "Primary Vendor")

    # Get upstream site name mapping
    upstream_names: Dict[int, str] = {}
    for c in site_configs:
        if c.upstream_site_id and c.upstream_site_id in cfg_by_id:
            upstream_names[c.site_id] = cfg_by_id[c.upstream_site_id].site_name
        else:
            upstream_names[c.site_id] = default_vendor

    # Collect candidates per TRM type
    candidates: Dict[str, List[_Candidate]] = defaultdict(list)

    order_seq = 0

    for episode in range(_N_EPISODES):
        chain = _DagChain(site_configs, topo_order, seed=episode * 1000)

        # Track previous demand CV per site for buffer detection
        prev_demand_cv: Dict[int, float] = {
            c.site_id: c.demand_cv for c in site_configs
        }

        for day in range(_N_DAYS):
            tick_result = chain.tick()
            sites: List[_SimSite] = tick_result["sites"]
            network_avg_dos = tick_result["network_avg_days_cover"]

            # Skip warmup period
            if day < _WARMUP_DAYS:
                for node in sites:
                    prev_demand_cv[node.site_id] = node.demand_cv
                continue

            for node in sites:
                cfg = cfg_by_id[node.site_id]
                pid = cfg.product_id
                pdesc = product_descs.get(pid, pid)
                ucost = product_costs.get(pid, 5.0)

                order_seq += 1

                # --- PO Creation ---
                c = _gen_po_creation(
                    node, cfg, config_id, pdesc, ucost,
                    upstream_names.get(cfg.site_id, default_vendor),
                    day, episode,
                )
                if c:
                    candidates["po_creation"].append(c)

                # --- ATP Executor ---
                if cfg.is_demand_source and node.period_demand > 0:
                    c = _gen_atp_executor(
                        node, cfg, config_id, pdesc, day, episode, order_seq,
                    )
                    if c:
                        candidates["atp_executor"].append(c)

                # --- Order Tracking ---
                c = _gen_order_tracking(
                    node, cfg, config_id, pdesc, ucost, day, episode, order_seq,
                )
                if c:
                    candidates["order_tracking"].append(c)

                # --- Inventory Buffer ---
                c = _gen_inventory_buffer(
                    node, cfg, config_id, pdesc, ucost, day,
                    prev_demand_cv.get(node.site_id, cfg.demand_cv),
                )
                if c:
                    candidates["inventory_buffer"].append(c)

                # --- MO Execution ---
                c = _gen_mo_execution(
                    node, cfg, config_id, pdesc, ucost, day, episode, order_seq,
                )
                if c:
                    candidates["mo_execution"].append(c)

                # --- TO Execution ---
                c = _gen_to_execution(
                    node, cfg, config_id, pdesc,
                    upstream_names.get(cfg.site_id, default_vendor),
                    day, episode, order_seq,
                )
                if c:
                    candidates["to_execution"].append(c)

                # --- Quality Disposition ---
                c = _gen_quality_disposition(
                    node, cfg, config_id, pdesc, ucost, day, episode, order_seq,
                )
                if c:
                    candidates["quality_disposition"].append(c)

                # --- Maintenance Scheduling ---
                c = _gen_maintenance_scheduling(
                    node, cfg, config_id, day, episode, order_seq,
                )
                if c:
                    candidates["maintenance_scheduling"].append(c)

                # --- Subcontracting ---
                c = _gen_subcontracting(
                    node, cfg, config_id, pdesc, ucost, day, episode, order_seq,
                )
                if c:
                    candidates["subcontracting"].append(c)

                # --- Forecast Adjustment ---
                if cfg.is_demand_source:
                    c = _gen_forecast_adjustment(
                        node, cfg, config_id, pdesc, day,
                    )
                    if c:
                        candidates["forecast_adjustment"].append(c)

                # Update prev CV tracker
                prev_demand_cv[node.site_id] = node.demand_cv

            # --- Rebalancing (cross-site, once per tick) ---
            rebal_cands = _gen_rebalancing(
                chain.nodes, cfg_by_id, config_id,
                product_descs, network_avg_dos, day,
            )
            candidates["rebalancing"].extend(rebal_cands)

    # Reservoir sample top-N per type
    selected = _reservoir_top_n(candidates, max_per_type)

    # Spread created_at timestamps across last 7 days
    all_records = []
    for trm_type, records in selected.items():
        all_records.extend(records)

    if not all_records:
        logger.warning("Decision seeder: no candidate decisions generated for config %d", config_id)
        return {}

    timestamps = _spread_timestamps(len(all_records), days_back=7)
    random.shuffle(all_records)
    for rec, ts in zip(all_records, timestamps):
        rec.created_at = ts

    # Persist to DB
    counts: Dict[str, int] = {}
    for trm_type, records in selected.items():
        for rec in records:
            db.add(rec)
        counts[trm_type] = len(records)

    db.flush()
    db.commit()

    total = sum(counts.values())
    logger.info(
        "Decision seeder: seeded %d decisions across %d TRM types for config %d: %s",
        total, len(counts), config_id, counts,
    )

    return counts

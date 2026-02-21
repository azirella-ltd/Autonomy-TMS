"""
Transfer Order Execution Engine

100% deterministic engine for TO execution decisions.
Handles: release timing, expediting, rerouting, consolidation.

Distinct from InventoryRebalancingTRM:
- TOs satisfy MPS/MRP planned transfers (plan-driven)
- Rebalancing is shorter-horizon financial optimization (opportunity-driven)

TRM head sits on top for exception handling and learned adjustments.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TODecisionType(Enum):
    """Types of TO execution decisions"""
    RELEASE = "release"
    EXPEDITE = "expedite"
    REROUTE = "reroute"
    CONSOLIDATE = "consolidate"
    DEFER = "defer"
    CANCEL = "cancel"


class TOTriggerReason(Enum):
    """Why this TO was created"""
    MRP_PLANNED = "mrp_planned"
    REBALANCING = "rebalancing"
    STOCKOUT_PREVENTION = "stockout_prevention"
    DEMAND_SHIFT = "demand_shift"
    MANUAL = "manual"


@dataclass
class TOExecutionConfig:
    """Configuration for TO execution engine"""
    # Release thresholds
    min_source_inventory_days: float = 3.0  # Min DOS at source to release
    max_advance_release_days: int = 5  # Max days before needed to release

    # Consolidation
    consolidation_window_hours: int = 24  # Window to consolidate TOs
    min_consolidation_savings_pct: float = 0.10  # Min cost savings to consolidate

    # Expedite
    expedite_cost_multiplier: float = 1.8  # Cost premium for expediting
    expedite_lead_time_reduction_pct: float = 0.40  # Lead time reduction via expedite

    # Reroute
    max_reroute_cost_increase_pct: float = 0.25  # Max cost increase for rerouting

    # Defer
    max_defer_days: int = 7


@dataclass
class TOSnapshot:
    """Snapshot of a transfer order"""
    order_id: str
    product_id: str
    source_site_id: str
    dest_site_id: str
    status: str  # DRAFT, RELEASED, PICKED, SHIPPED, IN_TRANSIT, RECEIVED

    # Quantities
    planned_qty: float
    picked_qty: float = 0.0
    shipped_qty: float = 0.0

    # Dates
    planned_ship_date: Optional[date] = None
    planned_delivery_date: Optional[date] = None
    actual_ship_date: Optional[date] = None

    # Transportation
    transportation_mode: str = "truck"
    estimated_transit_days: int = 2
    carrier: Optional[str] = None

    # Trigger
    trigger_reason: str = "mrp_planned"

    # Priority
    priority: int = 3
    days_until_needed: int = 0  # At destination

    # Source inventory context
    source_on_hand: float = 0.0
    source_dos: float = 0.0  # Days of supply at source
    source_committed: float = 0.0  # Already committed at source

    # Destination inventory context
    dest_on_hand: float = 0.0
    dest_dos: float = 0.0
    dest_backlog: float = 0.0
    dest_safety_stock: float = 0.0

    # Cost
    transportation_cost: float = 0.0


@dataclass
class TOExecutionResult:
    """Result of TO execution evaluation"""
    order_id: str
    decision_type: TODecisionType
    priority_score: float

    # Release
    ready_to_release: bool = False
    release_blockers: List[str] = field(default_factory=list)

    # Expedite
    expedite_recommended: bool = False
    expedite_reason: str = ""
    expedite_cost_premium: float = 0.0

    # Reroute
    reroute_recommended: bool = False
    alternative_source: Optional[str] = None
    reroute_reason: str = ""

    # Consolidation
    consolidate_with: List[str] = field(default_factory=list)
    consolidation_savings: float = 0.0

    # Defer
    defer_recommended: bool = False
    defer_days: int = 0

    # Impact
    dest_stockout_risk: float = 0.0
    source_depletion_risk: float = 0.0

    explanation: str = ""


class TOExecutionEngine:
    """
    Deterministic Transfer Order Execution Engine.

    Evaluates TOs for release readiness, expediting needs,
    consolidation opportunities, and rerouting options.
    """

    def __init__(self, site_key: str, config: Optional[TOExecutionConfig] = None):
        self.site_key = site_key
        self.config = config or TOExecutionConfig()

    def evaluate_release_readiness(self, to: TOSnapshot) -> TOExecutionResult:
        """Evaluate if a TO is ready for release."""
        blockers = []

        # Check source inventory
        available_at_source = to.source_on_hand - to.source_committed
        if available_at_source < to.planned_qty:
            blockers.append(
                f"Source available={available_at_source:.0f} < planned={to.planned_qty:.0f}"
            )

        # Check if source would be depleted below safety level
        source_after = to.source_on_hand - to.source_committed - to.planned_qty
        if to.source_dos > 0 and source_after < 0:
            blockers.append(
                f"Source would go negative: {source_after:.0f} units"
            )
        elif to.source_dos < self.config.min_source_inventory_days:
            blockers.append(
                f"Source DOS={to.source_dos:.1f} < min {self.config.min_source_inventory_days:.1f}"
            )

        # Check if too early
        if to.days_until_needed > self.config.max_advance_release_days + to.estimated_transit_days:
            blockers.append(
                f"Too early: needed in {to.days_until_needed} days, transit={to.estimated_transit_days}"
            )

        ready = len(blockers) == 0
        priority_score = self._calculate_priority_score(to)

        return TOExecutionResult(
            order_id=to.order_id,
            decision_type=TODecisionType.RELEASE,
            priority_score=priority_score,
            ready_to_release=ready,
            release_blockers=blockers,
            dest_stockout_risk=self._calculate_dest_stockout_risk(to),
            source_depletion_risk=self._calculate_source_depletion_risk(to),
            explanation=f"Release {'ready' if ready else 'blocked'}: {'; '.join(blockers) if blockers else 'OK'}"
        )

    def evaluate_expedite_need(self, to: TOSnapshot) -> TOExecutionResult:
        """Evaluate if a TO should be expedited."""
        should_expedite = False
        reasons = []

        # Destination at stockout risk
        if to.dest_dos < 2.0:
            should_expedite = True
            reasons.append(f"destination DOS={to.dest_dos:.1f} critically low")

        # Destination has backlog
        if to.dest_backlog > 0:
            should_expedite = True
            reasons.append(f"destination backlog={to.dest_backlog:.0f}")

        # Destination below safety stock
        if to.dest_on_hand < to.dest_safety_stock:
            should_expedite = True
            reasons.append("destination below safety stock")

        # Already late
        if to.days_until_needed <= 0 and to.status in ("DRAFT", "RELEASED"):
            should_expedite = True
            reasons.append(f"already {abs(to.days_until_needed)} days late")

        cost_premium = self.config.expedite_cost_multiplier * to.transportation_cost if should_expedite else 0.0

        return TOExecutionResult(
            order_id=to.order_id,
            decision_type=TODecisionType.EXPEDITE,
            priority_score=self._calculate_priority_score(to),
            expedite_recommended=should_expedite,
            expedite_reason="; ".join(reasons) if reasons else "no expedite needed",
            expedite_cost_premium=cost_premium,
            dest_stockout_risk=self._calculate_dest_stockout_risk(to),
            explanation=f"Expedite {'recommended' if should_expedite else 'not needed'}"
        )

    def evaluate_consolidation(
        self,
        orders: List[TOSnapshot]
    ) -> List[TOExecutionResult]:
        """
        Evaluate consolidation opportunities for TOs with same source->dest.
        Groups TOs by lane and checks if consolidation saves cost.
        """
        # Group by lane (source->dest)
        lanes: Dict[Tuple[str, str], List[TOSnapshot]] = {}
        for to in orders:
            key = (to.source_site_id, to.dest_site_id)
            lanes.setdefault(key, []).append(to)

        results = []
        for (src, dst), lane_orders in lanes.items():
            if len(lane_orders) < 2:
                for to in lane_orders:
                    results.append(TOExecutionResult(
                        order_id=to.order_id,
                        decision_type=TODecisionType.CONSOLIDATE,
                        priority_score=self._calculate_priority_score(to),
                        explanation="No consolidation opportunity (single TO on lane)"
                    ))
                continue

            # Sort by planned ship date
            lane_orders.sort(key=lambda x: x.planned_ship_date or date.max)

            # Check if dates are within consolidation window
            base_order = lane_orders[0]
            consolidate_group = [base_order]

            for to in lane_orders[1:]:
                if (to.planned_ship_date and base_order.planned_ship_date and
                        abs((to.planned_ship_date - base_order.planned_ship_date).days) <= 1):
                    consolidate_group.append(to)

            if len(consolidate_group) > 1:
                # Estimate savings from consolidation
                total_individual_cost = sum(t.transportation_cost for t in consolidate_group)
                # Consolidated cost = base + small incremental per additional
                consolidated_cost = base_order.transportation_cost * 1.2 if total_individual_cost > 0 else 0
                savings = max(0, total_individual_cost - consolidated_cost)
                savings_pct = savings / total_individual_cost if total_individual_cost > 0 else 0

                should_consolidate = savings_pct >= self.config.min_consolidation_savings_pct

                for to in consolidate_group:
                    others = [t.order_id for t in consolidate_group if t.order_id != to.order_id]
                    results.append(TOExecutionResult(
                        order_id=to.order_id,
                        decision_type=TODecisionType.CONSOLIDATE,
                        priority_score=self._calculate_priority_score(to),
                        consolidate_with=others if should_consolidate else [],
                        consolidation_savings=savings if should_consolidate else 0,
                        explanation=f"Consolidation {'recommended' if should_consolidate else 'marginal'}: {savings_pct:.0%} savings"
                    ))
            else:
                for to in lane_orders:
                    results.append(TOExecutionResult(
                        order_id=to.order_id,
                        decision_type=TODecisionType.CONSOLIDATE,
                        priority_score=self._calculate_priority_score(to),
                        explanation="No consolidation: dates too far apart"
                    ))

        return results

    def evaluate_order(self, to: TOSnapshot) -> TOExecutionResult:
        """Comprehensive evaluation of a TO."""
        if to.status == "DRAFT":
            result = self.evaluate_release_readiness(to)
            if not result.ready_to_release and to.days_until_needed > self.config.max_defer_days:
                return TOExecutionResult(
                    order_id=to.order_id,
                    decision_type=TODecisionType.DEFER,
                    priority_score=self._calculate_priority_score(to),
                    defer_recommended=True,
                    defer_days=min(to.days_until_needed - to.estimated_transit_days, self.config.max_defer_days),
                    explanation="Deferred: not yet needed and release blocked"
                )
            return result

        if to.status in ("RELEASED", "PICKED"):
            return self.evaluate_expedite_need(to)

        return TOExecutionResult(
            order_id=to.order_id,
            decision_type=TODecisionType.RELEASE,
            priority_score=self._calculate_priority_score(to),
            explanation=f"No action for status={to.status}"
        )

    def evaluate_batch(self, orders: List[TOSnapshot]) -> List[TOExecutionResult]:
        """Evaluate a batch of TOs."""
        return [self.evaluate_order(to) for to in orders]

    def _calculate_priority_score(self, to: TOSnapshot) -> float:
        priority_component = 1.0 - ((to.priority - 1) / 4.0)
        urgency_component = max(0, 1.0 - (to.days_until_needed / 14.0))
        dest_risk = self._calculate_dest_stockout_risk(to)
        return min(1.0, 0.3 * priority_component + 0.3 * urgency_component + 0.4 * dest_risk)

    def _calculate_dest_stockout_risk(self, to: TOSnapshot) -> float:
        if to.dest_dos <= 0:
            return 1.0
        if to.dest_dos <= 2:
            return 0.85
        if to.dest_dos <= 5:
            return 0.5
        if to.dest_dos <= 10:
            return 0.2
        return 0.05

    def _calculate_source_depletion_risk(self, to: TOSnapshot) -> float:
        remaining = to.source_on_hand - to.source_committed - to.planned_qty
        if remaining < 0:
            return 1.0
        if to.source_dos < 3:
            return 0.7
        if to.source_dos < 7:
            return 0.3
        return 0.05

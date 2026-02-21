"""
Manufacturing Order Execution Engine

100% deterministic engine for MO execution decisions.
Handles: sequencing, release timing, split decisions, expediting.

TRM head sits on top for exception handling and learned adjustments.
Engine can run standalone without TRM for graceful degradation.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MODecisionType(Enum):
    """Types of MO execution decisions"""
    RELEASE = "release"
    SEQUENCE = "sequence"
    SPLIT = "split"
    EXPEDITE = "expedite"
    DEFER = "defer"
    CANCEL = "cancel"


class MOPriority(Enum):
    """MO priority levels"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    DEFERRED = 5


@dataclass
class MOExecutionConfig:
    """Configuration for MO execution engine"""
    # Release thresholds
    min_material_availability_pct: float = 0.95  # Min % of BOM components available
    min_capacity_availability_pct: float = 0.80  # Min % of required capacity available
    release_horizon_days: int = 7  # How far ahead to consider for release

    # Sequencing parameters
    setup_time_weight: float = 0.3  # Weight for setup time minimization
    due_date_weight: float = 0.5  # Weight for due date adherence
    priority_weight: float = 0.2  # Weight for priority

    # Split thresholds
    min_split_quantity: int = 10  # Minimum quantity for split orders
    max_splits: int = 3  # Maximum number of splits

    # Expedite thresholds
    expedite_lead_time_reduction_pct: float = 0.3  # Max lead time reduction
    expedite_cost_multiplier: float = 1.5  # Cost premium for expediting

    # Defer thresholds
    max_defer_days: int = 14  # Maximum days to defer
    defer_penalty_per_day: float = 0.02  # % penalty per day of deferral


@dataclass
class MOSnapshot:
    """Snapshot of a manufacturing order's current state"""
    order_id: str
    product_id: str
    site_id: str
    status: str  # PLANNED, RELEASED, IN_PROGRESS, etc.

    # Quantities
    planned_quantity: float
    completed_quantity: float = 0.0
    scrap_quantity: float = 0.0

    # Dates
    planned_start_date: Optional[date] = None
    planned_completion_date: Optional[date] = None
    actual_start_date: Optional[date] = None

    # Resource
    resource_id: Optional[str] = None
    setup_time_hours: float = 0.0
    run_time_hours: float = 0.0

    # BOM material availability
    material_availability_pct: float = 1.0
    missing_components: List[str] = field(default_factory=list)

    # Capacity
    capacity_availability_pct: float = 1.0
    resource_utilization_pct: float = 0.0

    # Priority
    priority: int = 3  # 1=critical, 5=deferred
    customer_order_linked: bool = False  # True if linked to customer order
    days_until_due: int = 0

    # Predecessor orders
    predecessor_complete: bool = True  # Are predecessor MOs done?

    # Context
    current_sequence_position: int = 0
    changeover_from_product: Optional[str] = None  # For setup time calculation


@dataclass
class MOExecutionResult:
    """Result of MO execution evaluation"""
    order_id: str
    decision_type: MODecisionType
    priority_score: float  # 0-1, higher = more urgent

    # For RELEASE decisions
    ready_to_release: bool = False
    release_blockers: List[str] = field(default_factory=list)

    # For SEQUENCE decisions
    recommended_sequence: int = 0
    setup_time_savings_hours: float = 0.0

    # For SPLIT decisions
    split_quantities: List[float] = field(default_factory=list)
    split_reason: str = ""

    # For EXPEDITE decisions
    expedite_recommended: bool = False
    expedite_reason: str = ""
    expedite_cost_premium: float = 0.0

    # For DEFER decisions
    defer_recommended: bool = False
    defer_days: int = 0
    defer_reason: str = ""

    # Impact assessment
    estimated_completion_date: Optional[date] = None
    capacity_impact_pct: float = 0.0
    service_risk: float = 0.0  # 0-1, risk of missing customer delivery

    explanation: str = ""


class MOExecutionEngine:
    """
    Deterministic Manufacturing Order Execution Engine.

    Evaluates MOs for release readiness, optimal sequencing,
    split/expedite/defer decisions based on material availability,
    capacity, and priority rules.
    """

    def __init__(self, site_key: str, config: Optional[MOExecutionConfig] = None):
        self.site_key = site_key
        self.config = config or MOExecutionConfig()

    def evaluate_release_readiness(self, mo: MOSnapshot) -> MOExecutionResult:
        """Evaluate if an MO is ready for release to shop floor."""
        blockers = []

        if mo.material_availability_pct < self.config.min_material_availability_pct:
            blockers.append(
                f"Material availability {mo.material_availability_pct:.0%} "
                f"< {self.config.min_material_availability_pct:.0%} required"
            )
            if mo.missing_components:
                blockers.append(f"Missing: {', '.join(mo.missing_components[:5])}")

        if mo.capacity_availability_pct < self.config.min_capacity_availability_pct:
            blockers.append(
                f"Capacity availability {mo.capacity_availability_pct:.0%} "
                f"< {self.config.min_capacity_availability_pct:.0%} required"
            )

        if not mo.predecessor_complete:
            blockers.append("Predecessor orders not complete")

        ready = len(blockers) == 0

        # Calculate priority score
        priority_score = self._calculate_priority_score(mo)

        return MOExecutionResult(
            order_id=mo.order_id,
            decision_type=MODecisionType.RELEASE,
            priority_score=priority_score,
            ready_to_release=ready,
            release_blockers=blockers,
            service_risk=self._calculate_service_risk(mo),
            explanation=f"Release {'ready' if ready else 'blocked'}: {'; '.join(blockers) if blockers else 'all criteria met'}"
        )

    def evaluate_sequencing(
        self,
        orders: List[MOSnapshot],
        current_product: Optional[str] = None
    ) -> List[MOExecutionResult]:
        """
        Determine optimal sequence for a batch of MOs.

        Uses weighted scoring: due date urgency + priority + setup time minimization.
        """
        if not orders:
            return []

        scored_orders = []
        for mo in orders:
            # Due date score (higher = more urgent)
            due_score = max(0, 1.0 - (mo.days_until_due / 30.0)) if mo.days_until_due > 0 else 1.0

            # Priority score
            priority_score = 1.0 - ((mo.priority - 1) / 4.0)

            # Setup time score (prefer same product family to minimize changeover)
            setup_score = 0.5
            if current_product and mo.changeover_from_product:
                if mo.product_id == current_product:
                    setup_score = 1.0  # No changeover
                elif mo.setup_time_hours < 1.0:
                    setup_score = 0.8  # Low setup

            total_score = (
                self.config.due_date_weight * due_score +
                self.config.priority_weight * priority_score +
                self.config.setup_time_weight * setup_score
            )

            scored_orders.append((mo, total_score, due_score))

        # Sort by total score descending
        scored_orders.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, (mo, score, due_score) in enumerate(scored_orders):
            results.append(MOExecutionResult(
                order_id=mo.order_id,
                decision_type=MODecisionType.SEQUENCE,
                priority_score=score,
                recommended_sequence=idx + 1,
                service_risk=1.0 - due_score,
                explanation=f"Sequence #{idx + 1}: score={score:.2f} (due={due_score:.2f})"
            ))
            current_product = mo.product_id

        return results

    def evaluate_expedite_need(self, mo: MOSnapshot) -> MOExecutionResult:
        """Evaluate if an MO should be expedited."""
        should_expedite = False
        reasons = []

        # Critical priority
        if mo.priority <= 2:
            reasons.append("high priority order")

        # Past due or about to be
        if mo.days_until_due <= 0:
            should_expedite = True
            reasons.append(f"overdue by {abs(mo.days_until_due)} days")
        elif mo.days_until_due <= 2:
            should_expedite = True
            reasons.append(f"due in {mo.days_until_due} days")

        # Linked to customer order
        if mo.customer_order_linked and mo.days_until_due <= 5:
            should_expedite = True
            reasons.append("customer order at risk")

        cost_premium = self.config.expedite_cost_multiplier if should_expedite else 0.0

        return MOExecutionResult(
            order_id=mo.order_id,
            decision_type=MODecisionType.EXPEDITE,
            priority_score=self._calculate_priority_score(mo),
            expedite_recommended=should_expedite,
            expedite_reason="; ".join(reasons) if reasons else "no expedite needed",
            expedite_cost_premium=cost_premium,
            service_risk=self._calculate_service_risk(mo),
            explanation=f"Expedite {'recommended' if should_expedite else 'not needed'}: {'; '.join(reasons)}"
        )

    def evaluate_order(self, mo: MOSnapshot) -> MOExecutionResult:
        """
        Comprehensive evaluation of an MO - determines the best action.
        Priority-ordered evaluation: release -> expedite -> defer -> normal sequence.
        """
        # If PLANNED, check release readiness
        if mo.status == "PLANNED":
            release_result = self.evaluate_release_readiness(mo)
            if not release_result.ready_to_release:
                # Check if we should defer
                if mo.days_until_due > self.config.release_horizon_days * 2:
                    return MOExecutionResult(
                        order_id=mo.order_id,
                        decision_type=MODecisionType.DEFER,
                        priority_score=self._calculate_priority_score(mo),
                        defer_recommended=True,
                        defer_days=min(mo.days_until_due - self.config.release_horizon_days, self.config.max_defer_days),
                        defer_reason="Not yet within release horizon and blockers present",
                        explanation="Deferred: outside release window"
                    )
            return release_result

        # If RELEASED or IN_PROGRESS, check expedite need
        if mo.status in ("RELEASED", "IN_PROGRESS"):
            return self.evaluate_expedite_need(mo)

        # Default
        return MOExecutionResult(
            order_id=mo.order_id,
            decision_type=MODecisionType.SEQUENCE,
            priority_score=self._calculate_priority_score(mo),
            explanation=f"No action needed for status={mo.status}"
        )

    def evaluate_batch(self, orders: List[MOSnapshot]) -> List[MOExecutionResult]:
        """Evaluate a batch of MOs."""
        return [self.evaluate_order(mo) for mo in orders]

    def _calculate_priority_score(self, mo: MOSnapshot) -> float:
        """Calculate normalized priority score (0-1, higher = more urgent)."""
        priority_component = 1.0 - ((mo.priority - 1) / 4.0)
        urgency_component = max(0, 1.0 - (mo.days_until_due / 30.0))
        customer_component = 0.2 if mo.customer_order_linked else 0.0
        return min(1.0, 0.4 * priority_component + 0.4 * urgency_component + 0.2 + customer_component)

    def _calculate_service_risk(self, mo: MOSnapshot) -> float:
        """Calculate service risk (0-1, higher = more risk)."""
        if mo.days_until_due <= 0:
            return 1.0
        if mo.days_until_due <= 3:
            return 0.8
        if mo.days_until_due <= 7:
            return 0.5
        if mo.days_until_due <= 14:
            return 0.2
        return 0.05

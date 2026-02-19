"""
Inventory Rationing using Powell's VFA Framework

When inventory is scarce, allocate to maximize expected value:
- High-priority orders get preference
- Future high-value orders may be worth holding inventory
- Balance immediate fulfillment vs. strategic holding

This implements Powell's approach where inventory rationing
is viewed as a sequential decision problem with state-dependent
allocation rules.

Key Concepts:
- Fulfill value: Benefit of fulfilling order now
- Hold value: Expected benefit of holding for future high-priority orders
- Rationing decision: Compare fulfill vs. hold values

References:
- Powell (2022) Sequential Decision Analytics, Chapter on Resource Allocation
- de Véricourt & Karaesmen (2002). Inventory rationing in an (s, Q) system
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from enum import Enum
import numpy as np
import logging

from .value_function import ValueFunctionApproximator, PostDecisionState

logger = logging.getLogger(__name__)


class RationingPolicy(Enum):
    """Inventory rationing policy types"""
    FIFO = "fifo"  # First-in-first-out
    PRIORITY = "priority"  # Priority-based
    VALUE_BASED = "value_based"  # VFA-based (Powell)
    CRITICAL_LEVEL = "critical_level"  # Reserve for high-priority


@dataclass
class OrderRequest:
    """
    Order requesting inventory allocation.

    Represents a demand that needs to be fulfilled from available inventory.
    """
    order_id: str
    quantity: float
    priority: int = 1  # 1=highest priority
    due_date: int = 0  # periods from now (0=immediate)
    margin: float = 10.0  # profit per unit
    penalty: float = 5.0  # cost per unit short
    customer_id: Optional[str] = None
    product_id: Optional[str] = None

    # Additional context
    is_backlogged: bool = False
    original_quantity: float = field(default=0.0)

    def __post_init__(self):
        if self.original_quantity == 0.0:
            self.original_quantity = self.quantity

    @property
    def urgency_score(self) -> float:
        """Combined score of priority and due date urgency"""
        # Lower priority number = higher priority
        # Earlier due date = more urgent
        priority_weight = 5 - min(self.priority, 5)  # 1->4, 5->0
        due_date_weight = max(0, 5 - self.due_date)  # 0->5, 5+->0
        return priority_weight * 2 + due_date_weight


@dataclass
class RationingDecision:
    """
    Result of rationing decision for an order.

    Contains the allocation quantity and reasoning.
    """
    order_id: str
    requested_quantity: float
    allocated_quantity: float
    rationing_reason: str
    fulfill_value: Optional[float] = None
    hold_value: Optional[float] = None
    priority: int = 1

    @property
    def fill_rate(self) -> float:
        """Percentage of request fulfilled"""
        if self.requested_quantity == 0:
            return 1.0
        return self.allocated_quantity / self.requested_quantity

    @property
    def shortfall(self) -> float:
        """Quantity not allocated"""
        return max(0, self.requested_quantity - self.allocated_quantity)


class InventoryRationer:
    """
    Allocate scarce inventory using value function approach.

    Powell's insight: Rationing decisions should consider the value
    of holding inventory for future high-priority demand, not just
    current demand priority.

    This requires estimating:
    1. Value of fulfilling current order
    2. Expected value of holding for future orders
    """

    def __init__(
        self,
        vfa: Optional[ValueFunctionApproximator] = None,
        safety_factor: float = 1.5,
        gamma: float = 0.99,
        critical_level_pct: float = 0.2
    ):
        """
        Initialize inventory rationer.

        Args:
            vfa: Value function approximator for Powell-based rationing
            safety_factor: Multiplier on hold value (risk aversion)
            gamma: Discount factor for future values
            critical_level_pct: Fraction of base stock reserved for priority-1
        """
        self.vfa = vfa
        self.safety_factor = safety_factor
        self.gamma = gamma
        self.critical_level_pct = critical_level_pct

        # Track historical allocation decisions for learning
        self.allocation_history: List[Dict] = []

    def ration_inventory(
        self,
        available_inventory: float,
        pending_orders: List[OrderRequest],
        expected_future_orders: Optional[Dict[int, float]] = None,
        state: Optional[Dict[str, Any]] = None,
        policy: RationingPolicy = RationingPolicy.VALUE_BASED
    ) -> List[RationingDecision]:
        """
        Allocate inventory to orders using specified policy.

        Args:
            available_inventory: Total available inventory
            pending_orders: List of orders requesting inventory
            expected_future_orders: period -> expected high-priority demand
            state: Current supply chain state for VFA
            policy: Rationing policy to use

        Returns:
            List of RationingDecision for each order
        """
        if policy == RationingPolicy.FIFO:
            return self._ration_fifo(available_inventory, pending_orders)
        elif policy == RationingPolicy.PRIORITY:
            return self._ration_priority(available_inventory, pending_orders)
        elif policy == RationingPolicy.CRITICAL_LEVEL:
            return self._ration_critical_level(available_inventory, pending_orders)
        else:  # VALUE_BASED (Powell)
            return self._ration_value_based(
                available_inventory,
                pending_orders,
                expected_future_orders or {},
                state or {}
            )

    def _ration_fifo(
        self,
        available: float,
        orders: List[OrderRequest]
    ) -> List[RationingDecision]:
        """Simple first-in-first-out rationing"""
        decisions = []
        remaining = available

        for order in orders:
            allocated = min(order.quantity, remaining)
            remaining -= allocated

            decisions.append(RationingDecision(
                order_id=order.order_id,
                requested_quantity=order.quantity,
                allocated_quantity=allocated,
                rationing_reason="FIFO allocation",
                priority=order.priority,
            ))

        return decisions

    def _ration_priority(
        self,
        available: float,
        orders: List[OrderRequest]
    ) -> List[RationingDecision]:
        """Priority-based rationing (lower priority number = higher priority)"""
        decisions = []
        remaining = available

        # Sort by priority, then by due date
        sorted_orders = sorted(
            orders,
            key=lambda o: (o.priority, o.due_date)
        )

        for order in sorted_orders:
            allocated = min(order.quantity, remaining)
            remaining -= allocated

            decisions.append(RationingDecision(
                order_id=order.order_id,
                requested_quantity=order.quantity,
                allocated_quantity=allocated,
                rationing_reason=f"Priority {order.priority} allocation",
                priority=order.priority,
            ))

        return decisions

    def _ration_critical_level(
        self,
        available: float,
        orders: List[OrderRequest]
    ) -> List[RationingDecision]:
        """
        Critical level policy: Reserve inventory for high-priority orders.

        Only low-priority orders see reduced inventory.
        """
        decisions = []

        # Calculate critical level (reserved for priority-1)
        critical_level = available * self.critical_level_pct

        # Priority-1 orders see full inventory
        # Other orders see (available - critical_level)
        priority1_orders = [o for o in orders if o.priority == 1]
        other_orders = [o for o in orders if o.priority > 1]

        # Allocate to priority-1 first
        remaining_p1 = available
        for order in priority1_orders:
            allocated = min(order.quantity, remaining_p1)
            remaining_p1 -= allocated

            decisions.append(RationingDecision(
                order_id=order.order_id,
                requested_quantity=order.quantity,
                allocated_quantity=allocated,
                rationing_reason="Critical level: Priority-1 full access",
                priority=order.priority,
            ))

        # Remaining for other priorities
        remaining_other = max(0, remaining_p1 - critical_level)
        for order in sorted(other_orders, key=lambda o: (o.priority, o.due_date)):
            allocated = min(order.quantity, remaining_other)
            remaining_other -= allocated

            decisions.append(RationingDecision(
                order_id=order.order_id,
                requested_quantity=order.quantity,
                allocated_quantity=allocated,
                rationing_reason=f"Critical level: Priority-{order.priority} limited access",
                priority=order.priority,
            ))

        return decisions

    def _ration_value_based(
        self,
        available: float,
        orders: List[OrderRequest],
        expected_future_orders: Dict[int, float],
        state: Dict[str, Any]
    ) -> List[RationingDecision]:
        """
        Powell's VFA-based rationing.

        Compare value of fulfilling now vs. holding for future.
        """
        decisions = []
        remaining = available

        # Sort by urgency score (combines priority and due date)
        sorted_orders = sorted(orders, key=lambda o: -o.urgency_score)

        for order in sorted_orders:
            if remaining <= 0:
                decisions.append(RationingDecision(
                    order_id=order.order_id,
                    requested_quantity=order.quantity,
                    allocated_quantity=0,
                    rationing_reason="No inventory available",
                    priority=order.priority,
                ))
                continue

            # Value of fulfilling this order now
            fulfill_value = self._compute_fulfill_value(order, state)

            # Value of holding for potential future high-priority orders
            hold_value = self._compute_hold_value(
                order.quantity,
                expected_future_orders,
                state
            )

            if fulfill_value >= hold_value:
                allocated = min(order.quantity, remaining)
                remaining -= allocated
                decisions.append(RationingDecision(
                    order_id=order.order_id,
                    requested_quantity=order.quantity,
                    allocated_quantity=allocated,
                    rationing_reason=f"Fulfill value ({fulfill_value:.2f}) >= Hold value ({hold_value:.2f})",
                    fulfill_value=fulfill_value,
                    hold_value=hold_value,
                    priority=order.priority,
                ))
            else:
                decisions.append(RationingDecision(
                    order_id=order.order_id,
                    requested_quantity=order.quantity,
                    allocated_quantity=0,
                    rationing_reason=f"Hold value ({hold_value:.2f}) > Fulfill value ({fulfill_value:.2f})",
                    fulfill_value=fulfill_value,
                    hold_value=hold_value,
                    priority=order.priority,
                ))

        return decisions

    def _compute_fulfill_value(
        self,
        order: OrderRequest,
        state: Dict[str, Any]
    ) -> float:
        """
        Value of fulfilling order now.

        Includes:
        - Margin benefit (profit)
        - Penalty avoided (if due date is now)
        - Customer relationship value
        """
        # Margin benefit
        margin_value = order.quantity * order.margin

        # Avoid penalty if due now
        penalty_avoided = 0.0
        if order.due_date == 0:
            penalty_avoided = order.quantity * order.penalty

        # Priority bonus (higher priority = more valuable to fulfill)
        priority_bonus = (5 - order.priority) * order.quantity * 0.5

        # Backlog urgency (if already backlogged, more urgent)
        backlog_bonus = order.quantity * 2.0 if order.is_backlogged else 0.0

        return margin_value + penalty_avoided + priority_bonus + backlog_bonus

    def _compute_hold_value(
        self,
        quantity: float,
        expected_future_orders: Dict[int, float],
        state: Dict[str, Any]
    ) -> float:
        """
        Value of holding inventory for future high-priority orders.

        Uses VFA to estimate value of having inventory in future states.
        """
        if not expected_future_orders:
            return 0.0

        hold_value = 0.0

        for period, expected_qty in expected_future_orders.items():
            if period <= 0:
                continue

            # Probability that we'll need this inventory
            prob_needed = min(1.0, expected_qty / max(1, quantity))

            # Discounted value
            if self.vfa is not None:
                # Use VFA to estimate future value
                future_state = {**state, 'period': state.get('period', 0) + period}
                post_state = self.vfa._compute_post_decision_state(future_state, 0)
                value = self.vfa.compute_value(post_state)
            else:
                # Heuristic: future high-priority demand has premium value
                value = expected_qty * 15.0  # Premium for high-priority

            discounted = (self.gamma ** period) * prob_needed * value * self.safety_factor
            hold_value += discounted

        return hold_value

    def suggest_critical_level(
        self,
        historical_orders: List[OrderRequest],
        base_stock: float
    ) -> float:
        """
        Suggest optimal critical level based on historical demand patterns.

        Analyzes historical priority distribution to determine what
        fraction of inventory to reserve for high-priority orders.
        """
        if not historical_orders:
            return base_stock * self.critical_level_pct

        # Analyze priority distribution
        total_qty = sum(o.quantity for o in historical_orders)
        priority1_qty = sum(o.quantity for o in historical_orders if o.priority == 1)

        if total_qty == 0:
            return base_stock * self.critical_level_pct

        # Reserve enough for typical priority-1 demand + safety buffer
        priority1_fraction = priority1_qty / total_qty
        suggested = base_stock * priority1_fraction * (1 + self.safety_factor)

        return min(suggested, base_stock * 0.5)  # Cap at 50%

    def record_allocation(
        self,
        decisions: List[RationingDecision],
        actual_outcomes: Optional[Dict[str, Dict]] = None
    ):
        """
        Record allocation decisions for learning.

        If actual outcomes provided, can compute regret for policy improvement.
        """
        record = {
            "decisions": [
                {
                    "order_id": d.order_id,
                    "requested": d.requested_quantity,
                    "allocated": d.allocated_quantity,
                    "fill_rate": d.fill_rate,
                    "priority": d.priority,
                }
                for d in decisions
            ],
            "total_allocated": sum(d.allocated_quantity for d in decisions),
            "total_requested": sum(d.requested_quantity for d in decisions),
        }

        if actual_outcomes:
            # Compute regret (difference from optimal hindsight allocation)
            record["outcomes"] = actual_outcomes

        self.allocation_history.append(record)

        # Keep bounded history
        if len(self.allocation_history) > 1000:
            self.allocation_history = self.allocation_history[-1000:]

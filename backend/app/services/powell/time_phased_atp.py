"""
Time-Phased ATP Service for Allocated Available-to-Promise

Implements time-phased ATP consumption where allocations are consumed at the
expected delivery date minus the delivery lead time.

Key Concept:
    ATP consumption occurs at the "ship date", which is calculated as:
        ship_date = expected_delivery_date - delivery_lead_time

    This ensures inventory is available when the order needs to ship, not when
    it's placed or when it's delivered.

Business Days:
    Lead times are calculated in business days (default: Mon-Fri).
    The system supports configurable work weeks and holidays.

Fallback Logic:
    If insufficient ATP is available at the calculated ship date, the system
    cascades backward to today, checking each day for available supply.

Example:
    Order placed: today
    Expected delivery: 2 weeks from today (14 calendar days)
    Delivery lead time: 3 business days
    Work week: Mon-Fri (5 days)

    Ship date calculation:
        14 calendar days = ~10 business days
        Ship date = 10 business days - 3 business days = 7 business days from today

    ATP consumed at day 7 (business days from today)

    If day 7 has insufficient supply:
        Try day 6, then day 5, ... down to day 0 (today)

References:
    - User specification: "The allocation should be consumed at the expected
      delivery lead time"
    - Powell (2022) - Sequential Decision Analytics
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WorkWeekType(Enum):
    """Work week configuration"""
    FIVE_DAY = "five_day"      # Mon-Fri (default)
    SIX_DAY = "six_day"        # Mon-Sat
    SEVEN_DAY = "seven_day"    # Every day


@dataclass
class TimePhasedAllocation:
    """
    Allocation for a specific date × priority × product × location.

    Time-phased allocations allow ATP to be consumed at specific future dates,
    supporting forward planning of shipments.
    """
    date: date
    priority: int
    product_id: str
    location_id: str

    allocated_qty: float
    consumed_qty: float = 0.0

    # Source of supply
    supply_source: str = "inventory"  # inventory, production, inbound_po
    supply_source_id: Optional[str] = None  # PO number, production order, etc.

    @property
    def available_qty(self) -> float:
        return max(0, self.allocated_qty - self.consumed_qty)

    def consume(self, qty: float) -> float:
        """Consume from allocation, returns actually consumed qty"""
        available = self.available_qty
        consumed = min(qty, available)
        self.consumed_qty += consumed
        return consumed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "priority": self.priority,
            "product_id": self.product_id,
            "location_id": self.location_id,
            "allocated_qty": self.allocated_qty,
            "consumed_qty": self.consumed_qty,
            "available_qty": self.available_qty,
            "supply_source": self.supply_source,
            "supply_source_id": self.supply_source_id,
        }


@dataclass
class TimePhasedATPRequest:
    """Request for time-phased ATP check"""
    order_id: str
    line_id: Optional[str]
    product_id: str
    location_id: str
    requested_qty: float
    priority: int

    # Delivery timing
    expected_delivery_date: date
    delivery_lead_time_days: int  # Business days

    # Optional context
    customer_id: Optional[str] = None
    demand_source: Optional[str] = None
    order_date: Optional[date] = None


@dataclass
class TimePhasedATPResponse:
    """Response from time-phased ATP check"""
    order_id: str
    line_id: Optional[str]

    # Fulfillment decision
    can_fulfill: bool
    promised_qty: float
    shortfall_qty: float

    # Timing
    calculated_ship_date: date  # Where we intended to consume
    actual_consumption_date: Optional[date]  # Where we actually consumed (after cascade)

    # Consumption breakdown by date and priority
    consumption_breakdown: Dict[str, Dict[int, float]] = field(default_factory=dict)
    # Format: {"2026-02-07": {1: 50, 2: 30}, "2026-02-06": {3: 20}}

    # Cascade info
    cascade_required: bool = False
    cascade_depth: int = 0  # How many days we had to go back

    # Reasoning
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "line_id": self.line_id,
            "can_fulfill": self.can_fulfill,
            "promised_qty": self.promised_qty,
            "shortfall_qty": self.shortfall_qty,
            "calculated_ship_date": self.calculated_ship_date.isoformat(),
            "actual_consumption_date": self.actual_consumption_date.isoformat() if self.actual_consumption_date else None,
            "consumption_breakdown": self.consumption_breakdown,
            "cascade_required": self.cascade_required,
            "cascade_depth": self.cascade_depth,
            "reasoning": self.reasoning,
        }


@dataclass
class TimePhasedATPConfig:
    """Configuration for time-phased ATP service"""
    work_week: WorkWeekType = WorkWeekType.FIVE_DAY
    holidays: List[date] = field(default_factory=list)
    num_priorities: int = 5
    planning_horizon_days: int = 90  # How far forward to plan

    # Cascade behavior
    enable_cascade: bool = True
    max_cascade_days: int = 30  # Don't cascade more than N days back

    # Unfulfillable orders
    partial_fill_allowed: bool = True


class TimePhasedATPService:
    """
    Time-Phased ATP Service for date-aware ATP consumption.

    This service manages ATP allocations across a daily time horizon,
    supporting the consumption of ATP at the calculated ship date
    (delivery date minus delivery lead time).

    Key Features:
    1. Business day calculations (configurable work week)
    2. Ship date calculation: delivery_date - lead_time
    3. Backward cascade when insufficient supply at ship date
    4. Priority-based consumption within each date bucket

    Architecture:
        - Allocations stored by: (product_id, location_id, date, priority)
        - Consumption happens at ship date, cascades backward if needed
        - Integrates with inventory position and inbound supply
    """

    def __init__(self, config: Optional[TimePhasedATPConfig] = None):
        self.config = config or TimePhasedATPConfig()

        # Allocations: (product_id, location_id) -> date -> priority -> allocation
        self._allocations: Dict[
            Tuple[str, str],
            Dict[date, Dict[int, TimePhasedAllocation]]
        ] = {}

        # Consumption history for analytics
        self._consumption_history: List[TimePhasedATPResponse] = []

    def is_business_day(self, check_date: date) -> bool:
        """Check if a date is a business day"""
        if check_date in self.config.holidays:
            return False

        weekday = check_date.weekday()  # 0=Mon, 6=Sun

        if self.config.work_week == WorkWeekType.FIVE_DAY:
            return weekday < 5  # Mon-Fri
        elif self.config.work_week == WorkWeekType.SIX_DAY:
            return weekday < 6  # Mon-Sat
        else:  # SEVEN_DAY
            return True

    def add_business_days(self, from_date: date, business_days: int) -> date:
        """Add N business days to a date"""
        current = from_date
        days_added = 0
        direction = 1 if business_days >= 0 else -1
        target = abs(business_days)

        while days_added < target:
            current += timedelta(days=direction)
            if self.is_business_day(current):
                days_added += 1

        return current

    def subtract_business_days(self, from_date: date, business_days: int) -> date:
        """Subtract N business days from a date"""
        return self.add_business_days(from_date, -business_days)

    def business_days_between(self, start_date: date, end_date: date) -> int:
        """Count business days between two dates (exclusive of start, inclusive of end)"""
        if start_date >= end_date:
            return 0

        count = 0
        current = start_date
        while current < end_date:
            current += timedelta(days=1)
            if self.is_business_day(current):
                count += 1

        return count

    def calculate_ship_date(
        self,
        expected_delivery_date: date,
        delivery_lead_time_days: int,
        from_date: Optional[date] = None
    ) -> date:
        """
        Calculate the ship date given delivery date and lead time.

        Ship date = delivery date - delivery lead time (in business days)

        Args:
            expected_delivery_date: When the order should arrive
            delivery_lead_time_days: Business days for delivery
            from_date: Reference date (defaults to today)

        Returns:
            The date when ATP should be consumed (ship date)
        """
        today = from_date or date.today()
        ship_date = self.subtract_business_days(expected_delivery_date, delivery_lead_time_days)

        # Ship date cannot be in the past
        if ship_date < today:
            ship_date = today

        return ship_date

    def set_allocation(
        self,
        allocation: TimePhasedAllocation
    ):
        """Set or update an allocation for a specific date/priority/product/location"""
        key = (allocation.product_id, allocation.location_id)

        if key not in self._allocations:
            self._allocations[key] = {}

        if allocation.date not in self._allocations[key]:
            self._allocations[key][allocation.date] = {}

        self._allocations[key][allocation.date][allocation.priority] = allocation

    def set_allocations_bulk(self, allocations: List[TimePhasedAllocation]):
        """Bulk set allocations"""
        for alloc in allocations:
            self.set_allocation(alloc)

        logger.info(f"Set {len(allocations)} time-phased allocations")

    def generate_allocations_from_inventory(
        self,
        product_id: str,
        location_id: str,
        current_inventory: float,
        inbound_supply: Optional[Dict[date, float]] = None,
        priority_split: Optional[Dict[int, float]] = None
    ) -> List[TimePhasedAllocation]:
        """
        Generate time-phased allocations from inventory position.

        Args:
            product_id: Product ID
            location_id: Location/site ID
            current_inventory: Current on-hand inventory
            inbound_supply: Expected inbound by date {date: qty}
            priority_split: Allocation % by priority {priority: pct}

        Returns:
            List of allocations set for the planning horizon
        """
        today = date.today()
        horizon_end = today + timedelta(days=self.config.planning_horizon_days)

        # Default priority split
        if not priority_split:
            priority_split = {
                1: 0.30,
                2: 0.25,
                3: 0.20,
                4: 0.15,
                5: 0.10,
            }

        allocations = []
        inbound = inbound_supply or {}

        # Calculate cumulative available by date
        cumulative_available = current_inventory

        current_date = today
        while current_date <= horizon_end:
            if self.is_business_day(current_date):
                # Add any inbound supply for this date
                cumulative_available += inbound.get(current_date, 0)

                # Create allocations by priority for this date
                for priority, pct in priority_split.items():
                    allocated_qty = cumulative_available * pct

                    alloc = TimePhasedAllocation(
                        date=current_date,
                        priority=priority,
                        product_id=product_id,
                        location_id=location_id,
                        allocated_qty=allocated_qty,
                        supply_source="inventory" if current_date == today else "projection",
                    )
                    allocations.append(alloc)
                    self.set_allocation(alloc)

            current_date += timedelta(days=1)

        return allocations

    def check_atp(self, request: TimePhasedATPRequest) -> TimePhasedATPResponse:
        """
        Check time-phased ATP for an order.

        This is the main entry point. It:
        1. Calculates ship date (delivery date - lead time)
        2. Checks ATP at ship date
        3. If insufficient, cascades backward to today

        Args:
            request: ATP request with delivery date and lead time

        Returns:
            TimePhasedATPResponse with fulfillment details
        """
        today = request.order_date or date.today()

        # Calculate target ship date
        ship_date = self.calculate_ship_date(
            request.expected_delivery_date,
            request.delivery_lead_time_days,
            from_date=today
        )

        logger.info(
            f"ATP check for order {request.order_id}: "
            f"delivery={request.expected_delivery_date}, "
            f"lead_time={request.delivery_lead_time_days} days, "
            f"ship_date={ship_date}"
        )

        # Try to fulfill at ship date
        result = self._attempt_fulfillment_at_date(
            request=request,
            target_date=ship_date,
            remaining_qty=request.requested_qty
        )

        if result["fulfilled_qty"] >= request.requested_qty:
            # Full fulfillment at calculated ship date
            response = TimePhasedATPResponse(
                order_id=request.order_id,
                line_id=request.line_id,
                can_fulfill=True,
                promised_qty=result["fulfilled_qty"],
                shortfall_qty=0,
                calculated_ship_date=ship_date,
                actual_consumption_date=ship_date,
                consumption_breakdown=result["breakdown"],
                cascade_required=False,
                cascade_depth=0,
                reasoning=f"Full fulfillment at ship date {ship_date}",
            )
        elif self.config.enable_cascade:
            # Need to cascade backward
            response = self._cascade_backward(
                request=request,
                ship_date=ship_date,
                today=today,
                initial_result=result
            )
        else:
            # No cascade, partial fill or reject
            promised = result["fulfilled_qty"] if self.config.partial_fill_allowed else 0
            response = TimePhasedATPResponse(
                order_id=request.order_id,
                line_id=request.line_id,
                can_fulfill=promised > 0,
                promised_qty=promised,
                shortfall_qty=request.requested_qty - promised,
                calculated_ship_date=ship_date,
                actual_consumption_date=ship_date if promised > 0 else None,
                consumption_breakdown=result["breakdown"] if promised > 0 else {},
                cascade_required=False,
                cascade_depth=0,
                reasoning=f"Partial fulfillment at ship date, cascade disabled",
            )

        # Record for analytics
        self._consumption_history.append(response)

        return response

    def _attempt_fulfillment_at_date(
        self,
        request: TimePhasedATPRequest,
        target_date: date,
        remaining_qty: float
    ) -> Dict[str, Any]:
        """
        Attempt to fulfill order from allocations at a specific date.

        Uses priority-based consumption:
        1. Own tier first
        2. Bottom-up from lowest priority
        3. Stop at own tier (cannot consume above)
        """
        key = (request.product_id, request.location_id)

        if key not in self._allocations or target_date not in self._allocations[key]:
            return {
                "fulfilled_qty": 0,
                "breakdown": {},
            }

        date_allocations = self._allocations[key][target_date]
        consumption_sequence = self._build_consumption_sequence(
            request.priority, self.config.num_priorities
        )

        fulfilled_qty = 0
        breakdown: Dict[int, float] = {}

        for priority in consumption_sequence:
            if remaining_qty <= 0:
                break

            if priority not in date_allocations:
                continue

            alloc = date_allocations[priority]
            consumed = alloc.consume(remaining_qty)

            if consumed > 0:
                breakdown[priority] = consumed
                fulfilled_qty += consumed
                remaining_qty -= consumed

        return {
            "fulfilled_qty": fulfilled_qty,
            "breakdown": {target_date.isoformat(): breakdown} if breakdown else {},
        }

    def _cascade_backward(
        self,
        request: TimePhasedATPRequest,
        ship_date: date,
        today: date,
        initial_result: Dict[str, Any]
    ) -> TimePhasedATPResponse:
        """
        Cascade backward from ship date to today seeking additional supply.

        If the calculated ship date doesn't have enough ATP, we check earlier
        dates going back to today.
        """
        fulfilled_qty = initial_result["fulfilled_qty"]
        remaining_qty = request.requested_qty - fulfilled_qty
        all_breakdown = dict(initial_result["breakdown"])

        actual_consumption_date = ship_date if fulfilled_qty > 0 else None
        cascade_depth = 0

        # Cascade backward from ship_date - 1 to today
        check_date = ship_date - timedelta(days=1)
        max_cascade_date = today - timedelta(days=self.config.max_cascade_days)

        while remaining_qty > 0 and check_date >= today and check_date >= max_cascade_date:
            if self.is_business_day(check_date):
                result = self._attempt_fulfillment_at_date(
                    request=request,
                    target_date=check_date,
                    remaining_qty=remaining_qty
                )

                if result["fulfilled_qty"] > 0:
                    fulfilled_qty += result["fulfilled_qty"]
                    remaining_qty -= result["fulfilled_qty"]
                    all_breakdown.update(result["breakdown"])

                    if actual_consumption_date is None:
                        actual_consumption_date = check_date

                cascade_depth += 1

            check_date -= timedelta(days=1)

        can_fulfill = fulfilled_qty > 0
        if not self.config.partial_fill_allowed and fulfilled_qty < request.requested_qty:
            # Rollback all consumption
            self._rollback_consumption(all_breakdown, request.product_id, request.location_id)
            can_fulfill = False
            fulfilled_qty = 0
            all_breakdown = {}

        # Build reasoning
        if fulfilled_qty >= request.requested_qty:
            reasoning = f"Full fulfillment via cascade from {ship_date} to {actual_consumption_date}"
        elif fulfilled_qty > 0:
            reasoning = (
                f"Partial fulfillment ({fulfilled_qty}/{request.requested_qty}) "
                f"via cascade, checked {cascade_depth} days back"
            )
        else:
            reasoning = f"No supply available, cascaded {cascade_depth} days back to {today}"

        return TimePhasedATPResponse(
            order_id=request.order_id,
            line_id=request.line_id,
            can_fulfill=can_fulfill,
            promised_qty=fulfilled_qty,
            shortfall_qty=request.requested_qty - fulfilled_qty,
            calculated_ship_date=ship_date,
            actual_consumption_date=actual_consumption_date,
            consumption_breakdown=all_breakdown,
            cascade_required=True,
            cascade_depth=cascade_depth,
            reasoning=reasoning,
        )

    def _rollback_consumption(
        self,
        breakdown: Dict[str, Dict[int, float]],
        product_id: str,
        location_id: str
    ):
        """Rollback consumption when partial fill not allowed"""
        key = (product_id, location_id)

        if key not in self._allocations:
            return

        for date_str, priorities in breakdown.items():
            alloc_date = date.fromisoformat(date_str)

            if alloc_date not in self._allocations[key]:
                continue

            date_allocations = self._allocations[key][alloc_date]

            for priority, qty in priorities.items():
                if priority in date_allocations:
                    date_allocations[priority].consumed_qty -= qty

    def _build_consumption_sequence(self, order_priority: int, num_priorities: int) -> List[int]:
        """
        Build consumption sequence per AATP rules.

        1. Own tier first
        2. Lowest tier (highest number)
        3. Work upward toward own tier
        4. Cannot go above own tier
        """
        sequence = [order_priority]

        for p in range(num_priorities, order_priority, -1):
            if p != order_priority:
                sequence.append(p)

        return sequence

    def commit_atp(self, response: TimePhasedATPResponse) -> bool:
        """
        Commit an ATP decision (consumption already happened during check).

        In this implementation, consumption happens during check_atp.
        This method is for explicit confirmation and logging.

        Returns:
            True if committed successfully
        """
        if response.can_fulfill:
            logger.info(
                f"ATP committed for order {response.order_id}: "
                f"{response.promised_qty} units at {response.actual_consumption_date}"
            )
            return True
        return False

    def get_available_atp(
        self,
        product_id: str,
        location_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        priority: Optional[int] = None
    ) -> Dict[str, Dict[int, float]]:
        """
        Get available ATP by date and priority for a product/location.

        Returns:
            Dict of date -> priority -> available_qty
        """
        key = (product_id, location_id)

        if key not in self._allocations:
            return {}

        start = from_date or date.today()
        end = to_date or (start + timedelta(days=self.config.planning_horizon_days))

        result: Dict[str, Dict[int, float]] = {}

        for alloc_date, priorities in self._allocations[key].items():
            if start <= alloc_date <= end:
                date_str = alloc_date.isoformat()
                result[date_str] = {}

                for p, alloc in priorities.items():
                    if priority is None or p == priority:
                        result[date_str][p] = alloc.available_qty

        return result

    def get_consumption_summary(self) -> Dict[str, Any]:
        """Get summary of consumption history"""
        if not self._consumption_history:
            return {"total_orders": 0}

        total = len(self._consumption_history)
        fulfilled = sum(1 for r in self._consumption_history if r.can_fulfill)
        full_fill = sum(
            1 for r in self._consumption_history
            if r.can_fulfill and r.shortfall_qty == 0
        )
        cascaded = sum(1 for r in self._consumption_history if r.cascade_required)
        avg_cascade_depth = (
            sum(r.cascade_depth for r in self._consumption_history if r.cascade_required) /
            cascaded if cascaded > 0 else 0
        )

        return {
            "total_orders": total,
            "fulfilled_orders": fulfilled,
            "fulfillment_rate": fulfilled / total if total > 0 else 0,
            "full_fulfillment_rate": full_fill / total if total > 0 else 0,
            "cascade_rate": cascaded / total if total > 0 else 0,
            "avg_cascade_depth": avg_cascade_depth,
        }

    def clear_history(self):
        """Clear consumption history"""
        self._consumption_history.clear()

    def reset(self):
        """Reset all allocations and history"""
        self._allocations.clear()
        self._consumption_history.clear()

"""
Allocated Available-to-Promise (AATP) Engine - 100% Deterministic

Implements priority-based ATP consumption:
1. Allocations set by tGNN (Priority × Product × Location)
2. Orders consume from own priority tier first
3. Then bottom-up from lowest priority
4. Cannot consume above own tier

This engine handles the deterministic consumption rules.
TRM heads handle exceptions like partial fills and substitutions.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from enum import IntEnum
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Order priorities (1=highest, 5=lowest)"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    STANDARD = 5

    @classmethod
    def from_value(cls, value: int) -> 'Priority':
        """Get Priority from int value with bounds checking"""
        value = max(1, min(5, value))
        return cls(value)


@dataclass
class ATPAllocation:
    """Allocation bucket from tGNN"""
    product_id: str
    location_id: str
    priority: Priority
    allocated_qty: float
    period_start: date
    period_end: date
    source: str = "tgnn"  # "tgnn", "manual", "default"


@dataclass
class Order:
    """Incoming order to promise"""
    order_id: str
    product_id: str
    location_id: str
    requested_qty: float
    requested_date: date
    priority: Priority
    customer_id: str
    order_type: str = "standard"  # "standard", "rush", "backorder"


@dataclass
class ATPResult:
    """Result of ATP check"""
    order_id: str
    can_fulfill_full: bool
    available_qty: float
    shortage_qty: float
    available_date: date
    consumption_detail: List[Tuple[Priority, float]]  # Which tiers consumed
    recommendation: str = ""  # For partial/exception handling


@dataclass
class AATPConfig:
    """AATP engine configuration"""
    num_priority_tiers: int = 5
    allow_borrowing_up: bool = False  # If True, can consume from higher priority
    default_allocation_percent: Dict[int, float] = field(default_factory=lambda: {
        1: 0.10,  # 10% for critical
        2: 0.15,  # 15% for high
        3: 0.25,  # 25% for medium
        4: 0.25,  # 25% for low
        5: 0.25,  # 25% for standard
    })


class AATPEngine:
    """
    Allocated Available-to-Promise engine.

    100% deterministic consumption logic.
    Allocations come from tGNN; this engine just executes the rules.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[AATPConfig] = None,
        pegging_service=None,
        config_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ):
        self.site_key = site_key
        self.config = config or AATPConfig()
        self._pegging_service = pegging_service  # Optional PeggingService for DB persistence
        self._config_id = config_id
        self._tenant_id = tenant_id

        # Allocations by product:location -> priority -> qty
        self.allocations: Dict[str, Dict[Priority, float]] = defaultdict(
            lambda: {p: 0.0 for p in Priority}
        )

        # Consumption history for audit
        self.consumption_history: List[Dict] = []

    def load_allocations(self, allocations: List[ATPAllocation]):
        """Load allocations from tGNN"""
        self.allocations.clear()

        for alloc in allocations:
            key = self._make_key(alloc.product_id, alloc.location_id)
            self.allocations[key][alloc.priority] = alloc.allocated_qty

        logger.info(f"Loaded {len(allocations)} allocations for {self.site_key}")

    def set_default_allocations(
        self,
        product_id: str,
        location_id: str,
        total_inventory: float
    ):
        """
        Set default allocations when tGNN allocations not available.
        Uses configured default percentages.
        """
        key = self._make_key(product_id, location_id)

        for priority in Priority:
            pct = self.config.default_allocation_percent.get(priority.value, 0.2)
            self.allocations[key][priority] = total_inventory * pct

    def check_availability(self, order: Order) -> ATPResult:
        """
        Check availability for an order using AATP logic.

        Consumption sequence:
        1. Own priority tier first
        2. Bottom-up from lowest (5→4→3→...)
        3. Stop at own tier (cannot consume above) unless allow_borrowing_up
        """
        key = self._make_key(order.product_id, order.location_id)

        if key not in self.allocations:
            return ATPResult(
                order_id=order.order_id,
                can_fulfill_full=False,
                available_qty=0,
                shortage_qty=order.requested_qty,
                available_date=order.requested_date,
                consumption_detail=[],
                recommendation="No allocations found for product/location"
            )

        alloc = self.allocations[key]
        consumption_sequence = self._build_consumption_sequence(order.priority)

        remaining_need = order.requested_qty
        consumption_detail: List[Tuple[Priority, float]] = []

        for priority in consumption_sequence:
            available_in_tier = alloc.get(priority, 0)
            consume = min(remaining_need, available_in_tier)

            if consume > 0:
                consumption_detail.append((priority, consume))
                remaining_need -= consume

            if remaining_need <= 0:
                break

        fulfilled_qty = order.requested_qty - remaining_need

        # Generate recommendation for partial fulfillment
        recommendation = ""
        if remaining_need > 0:
            if fulfilled_qty > 0:
                recommendation = f"Partial fulfillment: {fulfilled_qty:.0f} of {order.requested_qty:.0f}"
            else:
                recommendation = "No inventory available in eligible tiers"

        return ATPResult(
            order_id=order.order_id,
            can_fulfill_full=(remaining_need <= 0),
            available_qty=fulfilled_qty,
            shortage_qty=max(0, remaining_need),
            available_date=order.requested_date,
            consumption_detail=consumption_detail,
            recommendation=recommendation
        )

    def commit_consumption(
        self,
        order: Order,
        result: ATPResult,
        record_history: bool = True
    ) -> bool:
        """
        Actually consume the allocations (after decision to fulfill).

        Call this after ATP exception handling decides to proceed.
        """
        key = self._make_key(order.product_id, order.location_id)

        if key not in self.allocations:
            return False

        alloc = self.allocations[key]

        for priority, qty in result.consumption_detail:
            alloc[priority] = max(0, alloc[priority] - qty)

        consumption_detail_dicts = [
            {'priority': p.value, 'qty': q}
            for p, q in result.consumption_detail
        ]

        if record_history:
            self.consumption_history.append({
                'order_id': order.order_id,
                'product_id': order.product_id,
                'location_id': order.location_id,
                'customer_id': order.customer_id,
                'requested_qty': order.requested_qty,
                'fulfilled_qty': result.available_qty,
                'consumption_detail': consumption_detail_dicts,
                'timestamp': date.today().isoformat()
            })

        # Persist to DB and create pegging link if pegging service is available
        if self._pegging_service and result.available_qty > 0:
            try:
                # Record AATP consumption to DB
                site_id = None
                try:
                    site_id = int(order.location_id)
                except (ValueError, TypeError):
                    pass

                pegging = self._pegging_service.peg_order_to_inventory(
                    order_id=order.order_id,
                    product_id=order.product_id,
                    site_id=site_id or 0,
                    quantity=result.available_qty,
                    priority=order.priority.value,
                    config_id=self._config_id or 0,
                    tenant_id=self._tenant_id or 0,
                )

                self._pegging_service.record_aatp_consumption(
                    order_id=order.order_id,
                    product_id=order.product_id,
                    location_id=order.location_id,
                    customer_id=order.customer_id,
                    requested_qty=order.requested_qty,
                    fulfilled_qty=result.available_qty,
                    priority=order.priority.value,
                    consumption_detail=consumption_detail_dicts,
                    config_id=self._config_id,
                    tenant_id=self._tenant_id,
                    pegging_id=pegging.id if pegging else None,
                )
            except Exception as e:
                logger.warning(f"Failed to persist AATP consumption: {e}")

        return True

    def rollback_consumption(
        self,
        order: Order,
        result: ATPResult
    ) -> bool:
        """
        Rollback a previous consumption (e.g., order cancelled).
        """
        key = self._make_key(order.product_id, order.location_id)

        if key not in self.allocations:
            return False

        alloc = self.allocations[key]

        for priority, qty in result.consumption_detail:
            alloc[priority] += qty

        return True

    def _build_consumption_sequence(self, order_priority: Priority) -> List[Priority]:
        """
        Build consumption sequence for given order priority.

        Rules:
        1. Own tier first
        2. Bottom-up from lowest priority
        3. Cannot consume above own tier (unless allow_borrowing_up)

        Example: Priority 2 order → [2, 5, 4, 3]
        (skips 1 because cannot consume above own tier)
        """
        sequence = [order_priority]  # Own tier first

        # Then from bottom up
        for p in [Priority.STANDARD, Priority.LOW, Priority.MEDIUM,
                  Priority.HIGH, Priority.CRITICAL]:
            if p == order_priority:
                continue

            if self.config.allow_borrowing_up:
                # Can consume from any tier
                sequence.append(p)
            else:
                # Can only consume from lower priority (higher number)
                if p > order_priority:
                    sequence.append(p)

        return sequence

    def get_available_by_priority(
        self,
        product_id: str,
        location_id: str
    ) -> Dict[Priority, float]:
        """Get current availability breakdown by priority"""
        key = self._make_key(product_id, location_id)
        return dict(self.allocations.get(key, {}))

    def get_total_available(
        self,
        product_id: str,
        location_id: str
    ) -> float:
        """Get total available inventory across all priorities"""
        available = self.get_available_by_priority(product_id, location_id)
        return sum(available.values())

    def get_available_for_priority(
        self,
        product_id: str,
        location_id: str,
        priority: Priority
    ) -> float:
        """
        Get inventory available for a specific priority level.
        Includes own tier plus all lower priority tiers.
        """
        key = self._make_key(product_id, location_id)

        if key not in self.allocations:
            return 0

        alloc = self.allocations[key]
        sequence = self._build_consumption_sequence(priority)

        return sum(alloc.get(p, 0) for p in sequence)

    def _make_key(self, product_id: str, location_id: str) -> str:
        """Create lookup key for allocations"""
        return f"{product_id}:{location_id}"

    def get_consumption_history(
        self,
        limit: int = 100
    ) -> List[Dict]:
        """Get recent consumption history"""
        return self.consumption_history[-limit:]

    def clear_consumption_history(self):
        """Clear consumption history"""
        self.consumption_history.clear()

    def get_allocation_summary(self) -> Dict:
        """Get summary of all allocations"""
        summary = {
            'total_products': len(self.allocations),
            'by_priority': {p.name: 0.0 for p in Priority},
            'total_allocated': 0.0
        }

        for key, alloc in self.allocations.items():
            for priority, qty in alloc.items():
                summary['by_priority'][priority.name] += qty
                summary['total_allocated'] += qty

        return summary

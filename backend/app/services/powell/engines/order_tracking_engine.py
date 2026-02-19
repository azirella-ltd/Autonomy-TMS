"""
Order Tracking Engine - 100% Deterministic

Implements threshold-based order exception detection:
- Late delivery: days_late > threshold
- Early delivery: days_early > threshold
- Quantity shortage: fill_rate < (1 - threshold)
- Price variance: |delta| > threshold
- Missing confirmation: CREATED + days > threshold
- Stuck in transit: days > 2x typical transit

This engine handles the mathematically defined threshold rules.
TRM heads handle severity refinement and action recommendations.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderTrackingConfig:
    """Order tracking engine configuration"""
    late_threshold_days: float = 2.0
    early_threshold_days: float = 3.0
    quantity_variance_threshold: float = 0.05  # 5%
    price_variance_threshold: float = 0.10    # 10%
    confirmation_threshold_days: float = 2.0
    stuck_transit_multiplier: float = 2.0     # days > typical * multiplier


@dataclass
class OrderSnapshot:
    """Order state snapshot for engine evaluation"""
    order_id: str
    order_type: str       # "purchase_order", "transfer_order", "customer_order", "production_order"
    status: str           # "created", "confirmed", "in_transit", "partially_received", "received"

    # Timing
    days_until_expected: float  # Negative = late
    days_since_created: float
    typical_transit_days: float = 5.0

    # Quantities
    ordered_qty: float = 0.0
    received_qty: float = 0.0

    # Pricing
    expected_unit_price: float = 0.0
    actual_unit_price: float = 0.0

    # Partner context
    partner_on_time_rate: float = 0.95
    partner_fill_rate: float = 0.98

    @property
    def fill_rate(self) -> float:
        if self.ordered_qty <= 0:
            return 1.0
        return self.received_qty / self.ordered_qty

    @property
    def price_variance_pct(self) -> float:
        if self.expected_unit_price <= 0:
            return 0.0
        return (self.actual_unit_price - self.expected_unit_price) / self.expected_unit_price


@dataclass
class ExceptionResult:
    """Deterministic exception detection result"""
    order_id: str
    exception_type: str   # "late_delivery", "early_delivery", "quantity_shortage", etc.
    severity: str         # "info", "warning", "high", "critical"
    recommended_action: str  # "no_action", "expedite", "find_alternate", etc.
    description: str
    impact_assessment: str
    confidence: float = 1.0  # Always 1.0 for deterministic engine


class OrderTrackingEngine:
    """
    Order exception detection engine.

    100% deterministic - threshold-based rules only.
    No neural networks, no learned components.
    """

    def __init__(self, config: Optional[OrderTrackingConfig] = None):
        self.config = config or OrderTrackingConfig()

    def evaluate_order(self, order: OrderSnapshot) -> ExceptionResult:
        """
        Evaluate a single order for exceptions.

        Checks (in priority order):
        1. Stuck in transit (CRITICAL)
        2. Missing confirmation (HIGH)
        3. Late delivery (severity varies)
        4. Early delivery (WARNING)
        5. Quantity shortage (severity varies)
        6. Price variance (WARNING)
        """
        exception_type = "no_exception"
        severity = "info"
        recommended_action = "no_action"

        # 1. Check stuck in transit (highest priority)
        if (order.status == "in_transit" and
                order.days_since_created > order.typical_transit_days * self.config.stuck_transit_multiplier):
            exception_type = "stuck_in_transit"
            severity = "critical"
            recommended_action = "find_alternate"

        # 2. Check missing confirmation
        elif (order.status == "created" and
                order.days_since_created > self.config.confirmation_threshold_days):
            exception_type = "missing_confirmation"
            severity = "high"
            recommended_action = "escalate"

        # 3. Check late delivery
        elif order.status in ["in_transit", "confirmed"]:
            if order.days_until_expected < -self.config.late_threshold_days:
                days_late = -order.days_until_expected
                exception_type = "late_delivery"

                if days_late > 7:
                    severity = "critical"
                    recommended_action = "find_alternate"
                elif days_late > 3:
                    severity = "high"
                    recommended_action = "expedite"
                else:
                    severity = "warning"
                    recommended_action = "expedite"

            # 4. Check early delivery
            elif order.days_until_expected > self.config.early_threshold_days:
                exception_type = "early_delivery"
                severity = "warning"
                recommended_action = "delay_acceptance"

        # 5. Check quantity shortage (can co-occur, but only if no higher-priority exception)
        if (exception_type == "no_exception" and
                order.status in ["partially_received", "received"] and
                order.fill_rate < (1 - self.config.quantity_variance_threshold)):
            shortage_pct = 1 - order.fill_rate
            exception_type = "quantity_shortage"

            if shortage_pct > 0.25:
                severity = "critical"
                recommended_action = "find_alternate"
            elif shortage_pct > 0.10:
                severity = "high"
                recommended_action = "partial_receipt"
            else:
                severity = "warning"
                recommended_action = "partial_receipt"

        # 6. Check price variance (lowest priority)
        if (exception_type == "no_exception" and
                abs(order.price_variance_pct) > self.config.price_variance_threshold):
            exception_type = "price_variance"
            severity = "warning"
            recommended_action = "price_negotiation"

        description = self._build_description(order, exception_type)
        impact = self._severity_impact(severity)

        return ExceptionResult(
            order_id=order.order_id,
            exception_type=exception_type,
            severity=severity,
            recommended_action=recommended_action,
            description=description,
            impact_assessment=impact,
        )

    def evaluate_batch(self, orders: List[OrderSnapshot]) -> List[ExceptionResult]:
        """Evaluate multiple orders, return only exceptions."""
        results = []
        for order in orders:
            result = self.evaluate_order(order)
            if result.exception_type != "no_exception":
                results.append(result)
        return results

    def _build_description(self, order: OrderSnapshot, exception_type: str) -> str:
        descriptions = {
            "no_exception": "Order progressing normally",
            "late_delivery": f"Order is {-order.days_until_expected:.0f} days late",
            "early_delivery": f"Order arriving {order.days_until_expected:.0f} days early",
            "quantity_shortage": f"Received {order.fill_rate*100:.0f}% of ordered quantity",
            "quantity_overage": f"Received more than ordered ({order.fill_rate*100:.0f}%)",
            "quality_issue": "Quality issues reported with order",
            "missing_confirmation": f"No confirmation after {order.days_since_created:.0f} days",
            "stuck_in_transit": f"Order in transit for {order.days_since_created:.0f} days (expected {order.typical_transit_days:.0f})",
            "price_variance": f"Price variance of {order.price_variance_pct*100:.1f}%",
        }
        return descriptions.get(exception_type, str(exception_type))

    def _severity_impact(self, severity: str) -> str:
        impacts = {
            "info": "Minimal impact expected",
            "warning": "Monitor for potential service impact",
            "high": "Service level at risk without action",
            "critical": "Immediate stockout risk or significant cost impact",
        }
        return impacts.get(severity, "Unknown impact")

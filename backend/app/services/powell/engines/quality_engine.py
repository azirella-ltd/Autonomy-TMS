"""
Quality Disposition Engine

100% deterministic engine for quality inspection disposition decisions.
Handles: accept/reject/rework/scrap based on inspection results and thresholds.

TRM head sits on top for learning nuanced disposition patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DispositionType(Enum):
    """Quality disposition options"""
    ACCEPT = "accept"
    REJECT = "reject"
    REWORK = "rework"
    SCRAP = "scrap"
    USE_AS_IS = "use_as_is"
    RETURN_TO_VENDOR = "return_to_vendor"
    CONDITIONAL_ACCEPT = "conditional_accept"


class SeverityLevel(Enum):
    """Defect severity"""
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class InspectionType(Enum):
    """Type of quality inspection"""
    INCOMING = "incoming"
    IN_PROCESS = "in_process"
    FINAL = "final"
    RETURNS = "returns"
    SAMPLING = "sampling"


@dataclass
class QualityEngineConfig:
    """Configuration for quality disposition engine"""
    # Accept thresholds
    auto_accept_defect_rate: float = 0.01  # Auto-accept below 1% defect rate
    max_accept_defect_rate: float = 0.05  # Max 5% to consider acceptance

    # Severity rules
    critical_defect_auto_reject: bool = True  # Any critical defect = reject
    major_defect_max_count: int = 3  # Max major defects before reject

    # Rework thresholds
    rework_cost_max_pct_of_value: float = 0.30  # Max rework cost as % of product value
    rework_success_min_probability: float = 0.80  # Min probability rework will succeed

    # Scrap thresholds
    scrap_if_rework_exceeds_pct: float = 0.50  # Scrap if rework > 50% of value

    # Use-as-is thresholds
    use_as_is_max_defect_rate: float = 0.03  # Max defect rate for use-as-is
    use_as_is_severity_max: str = "minor"  # Only minor defects for use-as-is

    # Vendor return
    vendor_return_window_days: int = 30  # Days after receipt to return

    # SLA
    disposition_sla_hours: int = 48  # Max hours for disposition decision


@dataclass
class QualitySnapshot:
    """Snapshot of a quality inspection"""
    quality_order_id: str
    product_id: str
    site_id: str
    inspection_type: str  # incoming, in_process, final, etc.

    # Inspection results
    inspection_quantity: float
    defect_count: int = 0
    defect_rate: float = 0.0  # defects / total inspected
    defect_category: str = ""  # visual, dimensional, functional, chemical
    severity_level: str = "minor"  # minor, major, critical

    # Line item results
    characteristics_tested: int = 0
    characteristics_passed: int = 0
    characteristics_failed: int = 0

    # Cost context
    product_unit_value: float = 0.0  # Value per unit
    estimated_rework_cost: float = 0.0
    estimated_scrap_cost: float = 0.0

    # Vendor context
    vendor_id: Optional[str] = None
    vendor_quality_score: float = 0.0  # 0-100 historical quality score
    days_since_receipt: int = 0  # For return window calculation

    # Inventory context
    inventory_on_hand: float = 0.0
    safety_stock: float = 0.0
    days_of_supply: float = 0.0
    pending_customer_orders: float = 0.0  # Demand waiting for this product

    # Lot context
    lot_number: Optional[str] = None
    lot_size: float = 0.0


@dataclass
class QualityDispositionResult:
    """Result of quality disposition evaluation"""
    quality_order_id: str
    recommended_disposition: DispositionType
    confidence: float  # 0-1

    # Quantities by disposition
    accept_qty: float = 0.0
    reject_qty: float = 0.0
    rework_qty: float = 0.0
    scrap_qty: float = 0.0
    use_as_is_qty: float = 0.0

    # Cost impact
    rework_cost: float = 0.0
    scrap_cost: float = 0.0
    service_risk_if_rejected: float = 0.0  # Risk of stockout if we reject

    # Vendor action
    return_to_vendor: bool = False
    within_return_window: bool = False
    vendor_notification_needed: bool = False

    # Urgency
    disposition_overdue: bool = False
    hours_until_sla: float = 0.0

    explanation: str = ""


class QualityEngine:
    """
    Deterministic Quality Disposition Engine.

    Evaluates quality inspection results and recommends disposition
    based on defect rates, severity, cost analysis, and inventory impact.
    """

    def __init__(self, site_key: str, config: Optional[QualityEngineConfig] = None):
        self.site_key = site_key
        self.config = config or QualityEngineConfig()

    def evaluate_disposition(self, qo: QualitySnapshot) -> QualityDispositionResult:
        """Evaluate quality inspection and recommend disposition."""
        total_qty = qo.inspection_quantity

        # Rule 1: Critical defect = auto reject
        if qo.severity_level == "critical" and self.config.critical_defect_auto_reject:
            return self._reject_result(
                qo, total_qty,
                "Critical defect detected - automatic rejection per policy"
            )

        # Rule 2: Very low defect rate = auto accept
        if qo.defect_rate <= self.config.auto_accept_defect_rate and qo.severity_level == "minor":
            return QualityDispositionResult(
                quality_order_id=qo.quality_order_id,
                recommended_disposition=DispositionType.ACCEPT,
                confidence=0.95,
                accept_qty=total_qty,
                explanation=f"Auto-accept: defect rate {qo.defect_rate:.2%} below threshold {self.config.auto_accept_defect_rate:.2%}"
            )

        # Rule 3: High defect rate = reject or rework
        if qo.defect_rate > self.config.max_accept_defect_rate:
            return self._evaluate_reject_vs_rework(qo, total_qty)

        # Rule 4: Moderate defect rate - nuanced decision
        return self._evaluate_moderate_defects(qo, total_qty)

    def _evaluate_reject_vs_rework(
        self, qo: QualitySnapshot, total_qty: float
    ) -> QualityDispositionResult:
        """Decide between reject, rework, and scrap for high-defect lots."""
        product_value = total_qty * qo.product_unit_value

        # Can we rework?
        rework_cost_pct = qo.estimated_rework_cost / product_value if product_value > 0 else 1.0

        if rework_cost_pct <= self.config.rework_cost_max_pct_of_value:
            # Rework is economical
            return QualityDispositionResult(
                quality_order_id=qo.quality_order_id,
                recommended_disposition=DispositionType.REWORK,
                confidence=0.80,
                rework_qty=total_qty,
                rework_cost=qo.estimated_rework_cost,
                service_risk_if_rejected=self._calculate_service_risk(qo),
                explanation=f"Rework recommended: cost {rework_cost_pct:.0%} of value, defect rate {qo.defect_rate:.2%}"
            )

        if rework_cost_pct > self.config.scrap_if_rework_exceeds_pct:
            # Rework too expensive, scrap
            return QualityDispositionResult(
                quality_order_id=qo.quality_order_id,
                recommended_disposition=DispositionType.SCRAP,
                confidence=0.85,
                scrap_qty=total_qty,
                scrap_cost=qo.estimated_scrap_cost,
                service_risk_if_rejected=self._calculate_service_risk(qo),
                explanation=f"Scrap: rework cost {rework_cost_pct:.0%} exceeds threshold"
            )

        # Can return to vendor?
        if qo.vendor_id and qo.days_since_receipt <= self.config.vendor_return_window_days:
            return QualityDispositionResult(
                quality_order_id=qo.quality_order_id,
                recommended_disposition=DispositionType.RETURN_TO_VENDOR,
                confidence=0.85,
                reject_qty=total_qty,
                return_to_vendor=True,
                within_return_window=True,
                vendor_notification_needed=True,
                service_risk_if_rejected=self._calculate_service_risk(qo),
                explanation=f"Return to vendor: within {self.config.vendor_return_window_days}-day window"
            )

        return self._reject_result(
            qo, total_qty,
            f"Reject: defect rate {qo.defect_rate:.2%}, rework too costly ({rework_cost_pct:.0%})"
        )

    def _evaluate_moderate_defects(
        self, qo: QualitySnapshot, total_qty: float
    ) -> QualityDispositionResult:
        """Handle moderate defect rates with nuanced analysis."""
        # Check if use-as-is is appropriate
        if (qo.defect_rate <= self.config.use_as_is_max_defect_rate and
                qo.severity_level == "minor"):

            # Check if inventory is critically needed
            if qo.days_of_supply < 3 or qo.pending_customer_orders > qo.inventory_on_hand:
                return QualityDispositionResult(
                    quality_order_id=qo.quality_order_id,
                    recommended_disposition=DispositionType.USE_AS_IS,
                    confidence=0.70,
                    use_as_is_qty=total_qty,
                    service_risk_if_rejected=self._calculate_service_risk(qo),
                    explanation=f"Use-as-is: minor defects ({qo.defect_rate:.2%}), inventory critically needed (DOS={qo.days_of_supply:.1f})"
                )

        # Conditional accept (partial)
        good_qty = total_qty * (1.0 - qo.defect_rate)
        defective_qty = total_qty - good_qty

        return QualityDispositionResult(
            quality_order_id=qo.quality_order_id,
            recommended_disposition=DispositionType.CONDITIONAL_ACCEPT,
            confidence=0.75,
            accept_qty=good_qty,
            reject_qty=defective_qty,
            service_risk_if_rejected=self._calculate_service_risk(qo),
            explanation=f"Conditional accept: {good_qty:.0f} good, {defective_qty:.0f} defective"
        )

    def _reject_result(
        self, qo: QualitySnapshot, qty: float, reason: str
    ) -> QualityDispositionResult:
        """Create a rejection result."""
        return QualityDispositionResult(
            quality_order_id=qo.quality_order_id,
            recommended_disposition=DispositionType.REJECT,
            confidence=0.90,
            reject_qty=qty,
            service_risk_if_rejected=self._calculate_service_risk(qo),
            return_to_vendor=qo.vendor_id is not None and qo.days_since_receipt <= self.config.vendor_return_window_days,
            within_return_window=qo.days_since_receipt <= self.config.vendor_return_window_days if qo.vendor_id else False,
            vendor_notification_needed=qo.vendor_id is not None,
            explanation=reason
        )

    def _calculate_service_risk(self, qo: QualitySnapshot) -> float:
        """Service risk if we reject this material."""
        if qo.days_of_supply <= 0:
            return 1.0
        if qo.pending_customer_orders > qo.inventory_on_hand:
            return 0.9
        if qo.days_of_supply < 3:
            return 0.7
        if qo.days_of_supply < 7:
            return 0.4
        if qo.inventory_on_hand < qo.safety_stock:
            return 0.5
        return 0.1

    def evaluate_batch(self, orders: List[QualitySnapshot]) -> List[QualityDispositionResult]:
        """Evaluate a batch of quality orders."""
        return [self.evaluate_disposition(qo) for qo in orders]

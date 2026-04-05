"""
Subcontracting Routing Engine

100% deterministic engine for make-vs-buy/subcontracting decisions.
Handles: route external, keep internal, split, vendor selection.

TRM head learns quality/reliability patterns from historical outcomes.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SubcontractDecisionType(Enum):
    """Subcontracting decision types"""
    ROUTE_EXTERNAL = "route_external"
    KEEP_INTERNAL = "keep_internal"
    SPLIT = "split"
    CHANGE_VENDOR = "change_vendor"


class SubcontractReason(Enum):
    """Reason for subcontracting consideration"""
    CAPACITY_CONSTRAINT = "capacity_constraint"
    COST_OPTIMIZATION = "cost_optimization"
    LEAD_TIME = "lead_time"
    QUALITY = "quality"
    SPECIALIZATION = "specialization"
    DEMAND_SURGE = "demand_surge"


@dataclass
class SubcontractingEngineConfig:
    """Configuration for subcontracting engine"""
    # Cost thresholds
    min_cost_savings_pct: float = 0.10  # Min savings to route external
    max_cost_premium_pct: float = 0.20  # Max premium for capacity relief

    # Quality requirements
    min_vendor_quality_score: float = 0.85  # Min quality score (0-1)
    min_vendor_on_time_score: float = 0.80  # Min on-time delivery score

    # Capacity thresholds
    internal_capacity_trigger_pct: float = 0.90  # Consider subcontracting above this
    min_internal_capacity_reserve_pct: float = 0.10  # Keep 10% internal capacity

    # Split rules
    min_split_quantity: float = 50
    max_external_pct: float = 0.70  # Max % of order to route externally

    # Lead time
    max_external_lead_time_days: int = 30

    # Vendor diversification
    max_single_vendor_pct: float = 0.60  # Max % with single vendor


@dataclass
class SubcontractSnapshot:
    """Snapshot for subcontracting evaluation"""
    product_id: str
    site_id: str
    required_quantity: float
    required_by_date: Optional[date] = None

    # Internal capability
    internal_capacity_available: float = 0.0
    internal_capacity_total: float = 0.0
    internal_capacity_pct: float = 0.0  # Usage %
    internal_cost_per_unit: float = 0.0
    internal_lead_time_days: int = 0
    internal_quality_yield_pct: float = 0.99

    # Subcontractor options (best candidate)
    subcontractor_id: Optional[str] = None
    subcontractor_cost_per_unit: float = 0.0
    subcontractor_lead_time_days: int = 0
    subcontractor_quality_score: float = 0.0  # 0-1
    subcontractor_on_time_score: float = 0.0  # 0-1
    subcontractor_capacity_available: float = 0.0

    # Context
    is_critical_product: bool = False
    has_special_tooling: bool = False  # Requires special tooling at subcontractor
    ip_sensitivity: str = "low"  # low, medium, high - IP protection concern
    current_external_pct: float = 0.0  # Current % already subcontracted

    # Demand context
    demand_forecast_next_30_days: float = 0.0
    backlog_quantity: float = 0.0


@dataclass
class SubcontractingResult:
    """Result of subcontracting evaluation"""
    product_id: str
    site_id: str
    decision_type: SubcontractDecisionType
    confidence: float  # 0-1

    # Routing
    internal_quantity: float = 0.0
    external_quantity: float = 0.0
    recommended_vendor: Optional[str] = None

    # Reason
    primary_reason: str = ""

    # Cost analysis
    internal_cost: float = 0.0
    external_cost: float = 0.0
    total_cost: float = 0.0
    cost_savings: float = 0.0

    # Risk
    quality_risk: float = 0.0  # 0-1
    delivery_risk: float = 0.0  # 0-1
    ip_risk: float = 0.0  # 0-1

    # Lead time
    estimated_completion_date: Optional[date] = None

    explanation: str = ""


class SubcontractingEngine:
    """
    Deterministic Subcontracting Routing Engine.

    Evaluates make-vs-buy decisions based on capacity, cost, quality,
    lead time, and risk factors.
    """

    def __init__(self, site_key: str, config: Optional[SubcontractingEngineConfig] = None):
        self.site_key = site_key
        self.config = config or SubcontractingEngineConfig()

    def evaluate_routing(self, snap: SubcontractSnapshot) -> SubcontractingResult:
        """Evaluate make-vs-buy decision for a production need."""
        # No subcontractor available
        if not snap.subcontractor_id:
            return SubcontractingResult(
                product_id=snap.product_id,
                site_id=snap.site_id,
                decision_type=SubcontractDecisionType.KEEP_INTERNAL,
                confidence=1.0,
                internal_quantity=snap.required_quantity,
                internal_cost=snap.required_quantity * snap.internal_cost_per_unit,
                total_cost=snap.required_quantity * snap.internal_cost_per_unit,
                primary_reason="no subcontractor available",
                explanation="Keep internal: no subcontractor options available"
            )

        # IP sensitivity check
        if snap.ip_sensitivity == "high":
            return SubcontractingResult(
                product_id=snap.product_id,
                site_id=snap.site_id,
                decision_type=SubcontractDecisionType.KEEP_INTERNAL,
                confidence=0.95,
                internal_quantity=snap.required_quantity,
                internal_cost=snap.required_quantity * snap.internal_cost_per_unit,
                total_cost=snap.required_quantity * snap.internal_cost_per_unit,
                primary_reason="ip_protection",
                ip_risk=1.0,
                explanation="Keep internal: high IP sensitivity"
            )

        # Quality check
        if snap.subcontractor_quality_score < self.config.min_vendor_quality_score:
            return SubcontractingResult(
                product_id=snap.product_id,
                site_id=snap.site_id,
                decision_type=SubcontractDecisionType.KEEP_INTERNAL,
                confidence=0.85,
                internal_quantity=snap.required_quantity,
                internal_cost=snap.required_quantity * snap.internal_cost_per_unit,
                total_cost=snap.required_quantity * snap.internal_cost_per_unit,
                primary_reason="vendor_quality_insufficient",
                quality_risk=1.0 - snap.subcontractor_quality_score,
                explanation=f"Keep internal: vendor quality {snap.subcontractor_quality_score:.0%} < {self.config.min_vendor_quality_score:.0%}"
            )

        # Capacity-driven: if internal capacity is stretched
        if snap.internal_capacity_pct >= self.config.internal_capacity_trigger_pct:
            return self._evaluate_capacity_driven(snap)

        # Cost-driven: if external is significantly cheaper
        cost_savings_pct = 0.0
        if snap.internal_cost_per_unit > 0:
            cost_savings_pct = (snap.internal_cost_per_unit - snap.subcontractor_cost_per_unit) / snap.internal_cost_per_unit

        if cost_savings_pct >= self.config.min_cost_savings_pct:
            return self._evaluate_cost_driven(snap, cost_savings_pct)

        # Lead time driven
        if (snap.required_by_date and
                snap.subcontractor_lead_time_days < snap.internal_lead_time_days and
                snap.subcontractor_on_time_score >= self.config.min_vendor_on_time_score):
            days_saved = snap.internal_lead_time_days - snap.subcontractor_lead_time_days
            external_cost = snap.required_quantity * snap.subcontractor_cost_per_unit
            internal_cost = snap.required_quantity * snap.internal_cost_per_unit
            cost_premium = external_cost - internal_cost

            if cost_premium <= internal_cost * self.config.max_cost_premium_pct:
                return SubcontractingResult(
                    product_id=snap.product_id,
                    site_id=snap.site_id,
                    decision_type=SubcontractDecisionType.ROUTE_EXTERNAL,
                    confidence=0.75,
                    external_quantity=snap.required_quantity,
                    recommended_vendor=snap.subcontractor_id,
                    primary_reason="lead_time",
                    internal_cost=internal_cost,
                    external_cost=external_cost,
                    total_cost=external_cost,
                    delivery_risk=1.0 - snap.subcontractor_on_time_score,
                    # TODO(virtual-clock): thread tenant_id + sync db into engine to use tenant_today_sync.
                    estimated_completion_date=date.today() + timedelta(days=snap.subcontractor_lead_time_days),
                    explanation=f"Route external: saves {days_saved} days lead time"
                )

        # Default: keep internal
        internal_cost = snap.required_quantity * snap.internal_cost_per_unit
        return SubcontractingResult(
            product_id=snap.product_id,
            site_id=snap.site_id,
            decision_type=SubcontractDecisionType.KEEP_INTERNAL,
            confidence=0.80,
            internal_quantity=snap.required_quantity,
            internal_cost=internal_cost,
            total_cost=internal_cost,
            primary_reason="no_compelling_reason_to_outsource",
            explanation="Keep internal: no cost/capacity/lead-time advantage"
        )

    def _evaluate_capacity_driven(self, snap: SubcontractSnapshot) -> SubcontractingResult:
        """Evaluate when capacity is the driver."""
        # How much can we make internally?
        internal_available = max(0, snap.internal_capacity_total * (1 - self.config.min_internal_capacity_reserve_pct) - (snap.internal_capacity_total * snap.internal_capacity_pct / 100))
        internal_qty = min(snap.required_quantity, internal_available)
        external_qty = snap.required_quantity - internal_qty

        # Cap external per vendor diversification
        max_external = snap.required_quantity * self.config.max_external_pct
        external_qty = min(external_qty, max_external)
        internal_qty = snap.required_quantity - external_qty

        if external_qty >= self.config.min_split_quantity:
            internal_cost = internal_qty * snap.internal_cost_per_unit
            external_cost = external_qty * snap.subcontractor_cost_per_unit

            return SubcontractingResult(
                product_id=snap.product_id,
                site_id=snap.site_id,
                decision_type=SubcontractDecisionType.SPLIT if internal_qty > 0 else SubcontractDecisionType.ROUTE_EXTERNAL,
                confidence=0.80,
                internal_quantity=internal_qty,
                external_quantity=external_qty,
                recommended_vendor=snap.subcontractor_id,
                primary_reason="capacity_constraint",
                internal_cost=internal_cost,
                external_cost=external_cost,
                total_cost=internal_cost + external_cost,
                quality_risk=1.0 - snap.subcontractor_quality_score,
                delivery_risk=1.0 - snap.subcontractor_on_time_score,
                explanation=f"Split: {internal_qty:.0f} internal + {external_qty:.0f} external (capacity at {snap.internal_capacity_pct:.0f}%)"
            )

        # Can't split meaningfully - keep internal and flag capacity issue
        return SubcontractingResult(
            product_id=snap.product_id,
            site_id=snap.site_id,
            decision_type=SubcontractDecisionType.KEEP_INTERNAL,
            confidence=0.60,
            internal_quantity=snap.required_quantity,
            internal_cost=snap.required_quantity * snap.internal_cost_per_unit,
            total_cost=snap.required_quantity * snap.internal_cost_per_unit,
            primary_reason="capacity_constraint_but_qty_too_small",
            explanation=f"Keep internal: external qty {external_qty:.0f} below min split {self.config.min_split_quantity}"
        )

    def _evaluate_cost_driven(self, snap: SubcontractSnapshot, savings_pct: float) -> SubcontractingResult:
        """Evaluate when cost is the driver."""
        external_cost = snap.required_quantity * snap.subcontractor_cost_per_unit
        internal_cost = snap.required_quantity * snap.internal_cost_per_unit

        return SubcontractingResult(
            product_id=snap.product_id,
            site_id=snap.site_id,
            decision_type=SubcontractDecisionType.ROUTE_EXTERNAL,
            confidence=0.80,
            external_quantity=snap.required_quantity,
            recommended_vendor=snap.subcontractor_id,
            primary_reason="cost_optimization",
            internal_cost=internal_cost,
            external_cost=external_cost,
            total_cost=external_cost,
            cost_savings=internal_cost - external_cost,
            quality_risk=1.0 - snap.subcontractor_quality_score,
            delivery_risk=1.0 - snap.subcontractor_on_time_score,
            explanation=f"Route external: {savings_pct:.0%} cost savings"
        )

    def evaluate_batch(self, snapshots: List[SubcontractSnapshot]) -> List[SubcontractingResult]:
        return [self.evaluate_routing(s) for s in snapshots]

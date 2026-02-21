"""
Maintenance Scheduling Engine

100% deterministic engine for maintenance scheduling decisions.
Handles: schedule/defer/expedite/combine/outsource decisions.

TRM head learns from historical patterns (e.g., which deferrals led to breakdowns).
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MaintenanceDecisionType(Enum):
    """Maintenance scheduling decision types"""
    SCHEDULE = "schedule"
    DEFER = "defer"
    EXPEDITE = "expedite"
    COMBINE = "combine"
    OUTSOURCE = "outsource"
    CANCEL = "cancel"


class MaintenanceType(Enum):
    """Types of maintenance"""
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"
    EMERGENCY = "emergency"
    ROUTINE = "routine"


@dataclass
class MaintenanceEngineConfig:
    """Configuration for maintenance scheduling engine"""
    # Deferral rules
    max_defer_days: int = 30
    max_defer_count: int = 2  # Max times an order can be deferred
    defer_risk_threshold: float = 0.3  # Max acceptable risk to defer

    # Scheduling windows
    preventive_schedule_window_days: int = 7  # Window for preventive maintenance
    production_freeze_zone_days: int = 2  # No maintenance during peak production

    # Combination rules
    min_combine_savings_pct: float = 0.15  # Min savings to combine maintenance windows
    max_combine_window_days: int = 3  # Max days to shift for combination

    # Outsource rules
    outsource_cost_threshold: float = 1.5  # Outsource if internal cost > 1.5x external
    outsource_lead_time_max_days: int = 14  # Max lead time for outsourced maintenance

    # Risk thresholds
    high_risk_expedite_threshold: float = 0.7  # Expedite if breakdown risk > 70%
    critical_asset_multiplier: float = 1.5  # Risk multiplier for critical assets


@dataclass
class MaintenanceSnapshot:
    """Snapshot of a maintenance order"""
    order_id: str
    asset_id: str
    site_id: str
    maintenance_type: str  # preventive, corrective, etc.
    status: str  # PLANNED, APPROVED, SCHEDULED, IN_PROGRESS, ON_HOLD

    # Scheduling
    scheduled_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    days_since_last_maintenance: int = 0
    maintenance_frequency_days: int = 90

    # Overdue tracking
    days_overdue: int = 0
    defer_count: int = 0  # How many times already deferred

    # Resource requirements
    estimated_downtime_hours: float = 0.0
    estimated_labor_hours: float = 0.0
    estimated_cost: float = 0.0
    spare_parts_available: bool = True

    # Asset context
    asset_criticality: str = "normal"  # critical, high, normal, low
    asset_age_years: float = 0.0
    mean_time_between_failures_days: float = 365.0
    recent_failure_count: int = 0  # Failures in last 90 days

    # Production context
    production_schedule_load_pct: float = 0.0  # Current production load
    production_impact_units: float = 0.0  # Lost production if maintenance done now
    next_production_gap_days: int = 0  # Days until next production gap

    # Priority
    priority: str = "NORMAL"  # LOW, NORMAL, HIGH, CRITICAL, EMERGENCY

    # External maintenance options
    external_cost_estimate: float = 0.0
    external_lead_time_days: int = 0


@dataclass
class MaintenanceSchedulingResult:
    """Result of maintenance scheduling evaluation"""
    order_id: str
    decision_type: MaintenanceDecisionType
    priority_score: float  # 0-1

    # Schedule
    recommended_date: Optional[date] = None

    # Defer
    defer_recommended: bool = False
    defer_to_date: Optional[date] = None
    defer_risk_score: float = 0.0  # Risk of breakdown if deferred

    # Expedite
    expedite_recommended: bool = False
    expedite_reason: str = ""

    # Combine
    combine_with: List[str] = field(default_factory=list)
    combined_savings: float = 0.0

    # Outsource
    outsource_recommended: bool = False
    outsource_savings: float = 0.0

    # Impact
    production_impact_hours: float = 0.0
    breakdown_probability: float = 0.0
    cost_estimate: float = 0.0

    explanation: str = ""


class MaintenanceEngine:
    """
    Deterministic Maintenance Scheduling Engine.

    Evaluates maintenance orders for optimal scheduling considering
    production impact, asset risk, resource availability, and cost.
    """

    def __init__(self, site_key: str, config: Optional[MaintenanceEngineConfig] = None):
        self.site_key = site_key
        self.config = config or MaintenanceEngineConfig()

    def evaluate_scheduling(self, mo: MaintenanceSnapshot) -> MaintenanceSchedulingResult:
        """Evaluate optimal scheduling for a maintenance order."""
        # Calculate breakdown probability
        breakdown_prob = self._estimate_breakdown_probability(mo)

        # Emergency/corrective - always expedite
        if mo.maintenance_type in ("emergency", "corrective") or mo.priority == "EMERGENCY":
            return MaintenanceSchedulingResult(
                order_id=mo.order_id,
                decision_type=MaintenanceDecisionType.EXPEDITE,
                priority_score=1.0,
                expedite_recommended=True,
                expedite_reason=f"{mo.maintenance_type} maintenance - immediate action required",
                recommended_date=date.today(),
                breakdown_probability=breakdown_prob,
                production_impact_hours=mo.estimated_downtime_hours,
                cost_estimate=mo.estimated_cost,
                explanation=f"Expedite: {mo.maintenance_type} maintenance"
            )

        # High breakdown risk - expedite
        if breakdown_prob >= self.config.high_risk_expedite_threshold:
            return MaintenanceSchedulingResult(
                order_id=mo.order_id,
                decision_type=MaintenanceDecisionType.EXPEDITE,
                priority_score=0.9,
                expedite_recommended=True,
                expedite_reason=f"breakdown probability {breakdown_prob:.0%} exceeds threshold",
                recommended_date=date.today() + timedelta(days=1),
                breakdown_probability=breakdown_prob,
                production_impact_hours=mo.estimated_downtime_hours,
                cost_estimate=mo.estimated_cost,
                explanation=f"Expedite: breakdown risk {breakdown_prob:.0%}"
            )

        # Check if deferral is appropriate
        can_defer = (
            mo.defer_count < self.config.max_defer_count and
            breakdown_prob < self.config.defer_risk_threshold and
            mo.production_schedule_load_pct > 0.85 and  # Production is busy
            mo.spare_parts_available  # Don't defer if parts are here and may expire
        )

        if can_defer and mo.next_production_gap_days <= self.config.max_defer_days:
            defer_to = date.today() + timedelta(days=mo.next_production_gap_days)
            return MaintenanceSchedulingResult(
                order_id=mo.order_id,
                decision_type=MaintenanceDecisionType.DEFER,
                priority_score=0.3,
                defer_recommended=True,
                defer_to_date=defer_to,
                defer_risk_score=breakdown_prob,
                recommended_date=defer_to,
                breakdown_probability=breakdown_prob,
                production_impact_hours=0,  # Deferred to gap
                cost_estimate=mo.estimated_cost,
                explanation=f"Defer to production gap in {mo.next_production_gap_days} days (risk={breakdown_prob:.0%})"
            )

        # Check outsource option
        if mo.external_cost_estimate > 0:
            cost_ratio = mo.estimated_cost / mo.external_cost_estimate if mo.external_cost_estimate > 0 else 0
            if (cost_ratio > self.config.outsource_cost_threshold and
                    mo.external_lead_time_days <= self.config.outsource_lead_time_max_days):
                return MaintenanceSchedulingResult(
                    order_id=mo.order_id,
                    decision_type=MaintenanceDecisionType.OUTSOURCE,
                    priority_score=0.5,
                    outsource_recommended=True,
                    outsource_savings=mo.estimated_cost - mo.external_cost_estimate,
                    recommended_date=mo.scheduled_date or date.today() + timedelta(days=mo.external_lead_time_days),
                    breakdown_probability=breakdown_prob,
                    cost_estimate=mo.external_cost_estimate,
                    explanation=f"Outsource: saves {cost_ratio - 1:.0%} vs internal"
                )

        # Default: schedule as planned
        priority_score = self._calculate_priority_score(mo, breakdown_prob)
        return MaintenanceSchedulingResult(
            order_id=mo.order_id,
            decision_type=MaintenanceDecisionType.SCHEDULE,
            priority_score=priority_score,
            recommended_date=mo.scheduled_date or date.today() + timedelta(days=self.config.preventive_schedule_window_days),
            breakdown_probability=breakdown_prob,
            production_impact_hours=mo.estimated_downtime_hours,
            cost_estimate=mo.estimated_cost,
            explanation=f"Schedule as planned (risk={breakdown_prob:.0%}, priority={mo.priority})"
        )

    def _estimate_breakdown_probability(self, mo: MaintenanceSnapshot) -> float:
        """Estimate probability of breakdown if maintenance is deferred."""
        base_prob = 0.05  # 5% baseline

        # Overdue increases risk
        if mo.days_overdue > 0:
            overdue_factor = min(0.5, mo.days_overdue / mo.maintenance_frequency_days)
            base_prob += overdue_factor

        # Days since last maintenance
        if mo.maintenance_frequency_days > 0:
            usage_ratio = mo.days_since_last_maintenance / mo.maintenance_frequency_days
            if usage_ratio > 1.0:
                base_prob += min(0.3, (usage_ratio - 1.0) * 0.3)

        # Recent failures increase risk
        if mo.recent_failure_count > 0:
            base_prob += min(0.3, mo.recent_failure_count * 0.1)

        # Asset age factor
        if mo.asset_age_years > 10:
            base_prob += min(0.15, (mo.asset_age_years - 10) * 0.015)

        # Prior deferrals increase risk
        base_prob += mo.defer_count * 0.1

        # Critical asset multiplier
        if mo.asset_criticality == "critical":
            base_prob *= self.config.critical_asset_multiplier

        return min(1.0, base_prob)

    def _calculate_priority_score(self, mo: MaintenanceSnapshot, breakdown_prob: float) -> float:
        """Calculate composite priority score for scheduling."""
        priority_map = {"EMERGENCY": 1.0, "CRITICAL": 0.9, "HIGH": 0.7, "NORMAL": 0.5, "LOW": 0.3}
        priority_score = priority_map.get(mo.priority, 0.5)
        return min(1.0, 0.4 * priority_score + 0.4 * breakdown_prob + 0.2 * (mo.defer_count / max(1, self.config.max_defer_count)))

    def evaluate_batch(self, orders: List[MaintenanceSnapshot]) -> List[MaintenanceSchedulingResult]:
        """Evaluate a batch of maintenance orders."""
        return [self.evaluate_scheduling(mo) for mo in orders]

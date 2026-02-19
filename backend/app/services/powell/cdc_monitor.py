"""
CDC (Change Detection and Control) Monitor for Event-Driven Planning

Monitors key metrics against thresholds and triggers out-of-cadence
planning runs when significant deviations are detected.

This implements "condition-based maintenance" for policy parameters:
- Don't wait for scheduled replanning when metrics indicate policy staleness
- Trigger early to prevent error compounding
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TriggerReason(Enum):
    """Reasons for CDC trigger"""
    DEMAND_DEVIATION = "demand_deviation"
    INVENTORY_LOW = "inventory_low"
    INVENTORY_HIGH = "inventory_high"
    SERVICE_LEVEL_DROP = "service_level_drop"
    LEAD_TIME_INCREASE = "lead_time_increase"
    BACKLOG_GROWTH = "backlog_growth"
    SUPPLIER_RELIABILITY = "supplier_reliability"


class ReplanAction(Enum):
    """Actions to take on CDC trigger"""
    FULL_CFA = "full_cfa"           # Full policy parameter re-optimization
    ALLOCATION_ONLY = "allocation"   # Rerun tGNN allocations only
    PARAM_ADJUSTMENT = "param_adj"   # Light parameter tweak (±10%)
    NONE = "none"                    # No action (within tolerance)


@dataclass
class SiteMetrics:
    """Current metrics for a site or site group"""
    site_key: str
    timestamp: datetime

    # Demand metrics
    demand_cumulative: float        # Actual cumulative demand this period
    forecast_cumulative: float      # Forecasted cumulative demand

    # Inventory metrics
    inventory_on_hand: float
    inventory_target: float

    # Service metrics
    service_level: float            # Actual (0.0-1.0)
    target_service_level: float     # Target (0.0-1.0)

    # Supply metrics
    avg_lead_time_actual: float     # Days
    avg_lead_time_expected: float   # Days
    supplier_on_time_rate: float    # 0.0-1.0

    # Execution metrics
    backlog_units: float
    backlog_yesterday: float        # For growth calculation


@dataclass
class TriggerEvent:
    """Result of a CDC trigger check"""
    triggered: bool
    reasons: List[TriggerReason]
    metrics_snapshot: SiteMetrics
    recommended_action: ReplanAction
    severity: str                   # "none", "low", "medium", "high", "critical"
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CDCConfig:
    """Configuration for CDC monitor"""
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        'demand_deviation': 0.15,       # ±15%
        'inventory_ratio_low': 0.70,    # <70% of target
        'inventory_ratio_high': 1.50,   # >150% of target
        'service_level_drop': 0.05,     # 5% below target
        'lead_time_increase': 0.30,     # +30%
        'backlog_growth_days': 2,       # 2 consecutive days
        'supplier_reliability_drop': 0.15,  # 15% below target
    })
    cooldown_hours: int = 24
    max_cfa_per_period_days: int = 3  # Max 1 full CFA per 3 days
    enabled: bool = True


class CDCMonitor:
    """
    Monitors key metrics and triggers out-of-cadence planning runs.

    Implements event-driven planning layered on top of periodic cadence.
    Analogous to condition-based maintenance for policy parameters.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[CDCConfig] = None
    ):
        self.site_key = site_key
        self.config = config or CDCConfig()
        self.last_trigger_time: Dict[TriggerReason, datetime] = {}
        self.last_cfa_time: Optional[datetime] = None
        self.backlog_growth_days = 0  # Consecutive days of growth

    async def check_and_trigger(
        self,
        metrics: SiteMetrics,
        db: Optional[Session] = None,
    ) -> TriggerEvent:
        """
        Check current metrics against thresholds.
        Returns TriggerEvent with recommended action if thresholds exceeded.

        Args:
            metrics: Current site metrics to check
            db: Optional DB session — if provided, trigger events are persisted
                to the powell_cdc_trigger_log table.
        """
        if not self.config.enabled:
            return TriggerEvent(
                triggered=False,
                reasons=[],
                metrics_snapshot=metrics,
                recommended_action=ReplanAction.NONE,
                severity="none",
                message="CDC monitoring disabled"
            )

        triggers: List[TriggerReason] = []

        # 1. Demand deviation check
        triggers.extend(self._check_demand_deviation(metrics))

        # 2. Inventory imbalance check
        triggers.extend(self._check_inventory_imbalance(metrics))

        # 3. Service level degradation check
        triggers.extend(self._check_service_level(metrics))

        # 4. Lead time increase check
        triggers.extend(self._check_lead_time(metrics))

        # 5. Backlog growth check
        triggers.extend(self._check_backlog_growth(metrics))

        # 6. Supplier reliability check
        triggers.extend(self._check_supplier_reliability(metrics))

        # Determine action and severity
        if not triggers:
            return TriggerEvent(
                triggered=False,
                reasons=[],
                metrics_snapshot=metrics,
                recommended_action=ReplanAction.NONE,
                severity="none",
                message="All metrics within tolerance"
            )

        action, severity = self._determine_action_and_severity(triggers)

        # Check if action is allowed (rate limiting)
        if action == ReplanAction.FULL_CFA and not self._cfa_allowed():
            action = ReplanAction.ALLOCATION_ONLY
            severity = "medium"  # Downgrade severity

        # Record trigger times
        now = datetime.utcnow()
        for reason in triggers:
            self.last_trigger_time[reason] = now

        if action == ReplanAction.FULL_CFA:
            self.last_cfa_time = now

        event = TriggerEvent(
            triggered=True,
            reasons=triggers,
            metrics_snapshot=metrics,
            recommended_action=action,
            severity=severity,
            message=f"CDC triggered: {[r.value for r in triggers]}"
        )

        # Persist to database if session provided
        if db is not None:
            self._persist_trigger(db, event)

        return event

    def _persist_trigger(self, db: Session, event: TriggerEvent) -> None:
        """Persist a TriggerEvent to the powell_cdc_trigger_log table."""
        try:
            from app.models.powell_decision import CDCTriggerLog

            metrics_dict = {
                'site_key': event.metrics_snapshot.site_key,
                'demand_cumulative': event.metrics_snapshot.demand_cumulative,
                'forecast_cumulative': event.metrics_snapshot.forecast_cumulative,
                'inventory_on_hand': event.metrics_snapshot.inventory_on_hand,
                'inventory_target': event.metrics_snapshot.inventory_target,
                'service_level': event.metrics_snapshot.service_level,
                'target_service_level': event.metrics_snapshot.target_service_level,
                'avg_lead_time_actual': event.metrics_snapshot.avg_lead_time_actual,
                'avg_lead_time_expected': event.metrics_snapshot.avg_lead_time_expected,
                'supplier_on_time_rate': event.metrics_snapshot.supplier_on_time_rate,
                'backlog_units': event.metrics_snapshot.backlog_units,
                'backlog_yesterday': event.metrics_snapshot.backlog_yesterday,
            }

            log_entry = CDCTriggerLog(
                site_key=self.site_key,
                timestamp=event.timestamp,
                triggered=event.triggered,
                reasons=[r.value for r in event.reasons],
                severity=event.severity,
                recommended_action=event.recommended_action.value,
                metrics_snapshot=metrics_dict,
                threshold_breaches=self._compute_threshold_breaches(event.metrics_snapshot, event.reasons),
            )
            db.add(log_entry)
            db.commit()
            logger.info(f"Persisted CDC trigger for {self.site_key}: {event.severity}")
        except Exception as e:
            logger.warning(f"Failed to persist CDC trigger for {self.site_key}: {e}")
            try:
                db.rollback()
            except Exception:
                pass

    def _compute_threshold_breaches(
        self, metrics: SiteMetrics, reasons: List[TriggerReason]
    ) -> Dict[str, Any]:
        """Compute threshold breach details for each triggered reason."""
        breaches = {}
        thresholds = self.config.thresholds

        for reason in reasons:
            if reason == TriggerReason.DEMAND_DEVIATION and metrics.forecast_cumulative > 0:
                deviation = abs(metrics.demand_cumulative - metrics.forecast_cumulative) / metrics.forecast_cumulative
                breaches['demand_deviation'] = {
                    'actual': round(deviation, 4),
                    'threshold': thresholds['demand_deviation'],
                    'deviation_pct': round((deviation - thresholds['demand_deviation']) / thresholds['demand_deviation'] * 100, 1),
                }
            elif reason == TriggerReason.INVENTORY_LOW and metrics.inventory_target > 0:
                ratio = metrics.inventory_on_hand / metrics.inventory_target
                breaches['inventory_low'] = {
                    'actual': round(ratio, 4),
                    'threshold': thresholds['inventory_ratio_low'],
                    'deviation_pct': round((thresholds['inventory_ratio_low'] - ratio) / thresholds['inventory_ratio_low'] * 100, 1),
                }
            elif reason == TriggerReason.INVENTORY_HIGH and metrics.inventory_target > 0:
                ratio = metrics.inventory_on_hand / metrics.inventory_target
                breaches['inventory_high'] = {
                    'actual': round(ratio, 4),
                    'threshold': thresholds['inventory_ratio_high'],
                    'deviation_pct': round((ratio - thresholds['inventory_ratio_high']) / thresholds['inventory_ratio_high'] * 100, 1),
                }
            elif reason == TriggerReason.SERVICE_LEVEL_DROP:
                drop = metrics.target_service_level - metrics.service_level
                breaches['service_level_drop'] = {
                    'actual': round(drop, 4),
                    'threshold': thresholds['service_level_drop'],
                    'deviation_pct': round((drop - thresholds['service_level_drop']) / max(thresholds['service_level_drop'], 0.001) * 100, 1),
                }
            elif reason == TriggerReason.LEAD_TIME_INCREASE and metrics.avg_lead_time_expected > 0:
                increase = (metrics.avg_lead_time_actual - metrics.avg_lead_time_expected) / metrics.avg_lead_time_expected
                breaches['lead_time_increase'] = {
                    'actual': round(increase, 4),
                    'threshold': thresholds['lead_time_increase'],
                    'deviation_pct': round((increase - thresholds['lead_time_increase']) / thresholds['lead_time_increase'] * 100, 1),
                }
            elif reason == TriggerReason.BACKLOG_GROWTH:
                breaches['backlog_growth'] = {
                    'actual': self.backlog_growth_days,
                    'threshold': thresholds['backlog_growth_days'],
                    'deviation_pct': round((self.backlog_growth_days - thresholds['backlog_growth_days']) / max(thresholds['backlog_growth_days'], 1) * 100, 1),
                }
            elif reason == TriggerReason.SUPPLIER_RELIABILITY:
                target = 0.95
                drop = target - metrics.supplier_on_time_rate
                breaches['supplier_reliability'] = {
                    'actual': round(metrics.supplier_on_time_rate, 4),
                    'threshold': round(target - thresholds['supplier_reliability_drop'], 4),
                    'deviation_pct': round((drop - thresholds['supplier_reliability_drop']) / max(thresholds['supplier_reliability_drop'], 0.001) * 100, 1),
                }

        return breaches

    def _check_demand_deviation(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for significant demand vs forecast deviation"""
        triggers = []

        if metrics.forecast_cumulative > 0:
            demand_dev = abs(metrics.demand_cumulative - metrics.forecast_cumulative) / metrics.forecast_cumulative
            if demand_dev > self.config.thresholds['demand_deviation']:
                if self._cooldown_ok(TriggerReason.DEMAND_DEVIATION):
                    triggers.append(TriggerReason.DEMAND_DEVIATION)
                    logger.info(f"CDC: Demand deviation {demand_dev:.1%} at {self.site_key}")

        return triggers

    def _check_inventory_imbalance(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for inventory too low or too high vs target"""
        triggers = []

        if metrics.inventory_target > 0:
            inv_ratio = metrics.inventory_on_hand / metrics.inventory_target

            if inv_ratio < self.config.thresholds['inventory_ratio_low']:
                if self._cooldown_ok(TriggerReason.INVENTORY_LOW):
                    triggers.append(TriggerReason.INVENTORY_LOW)
                    logger.info(f"CDC: Inventory low {inv_ratio:.1%} at {self.site_key}")

            elif inv_ratio > self.config.thresholds['inventory_ratio_high']:
                if self._cooldown_ok(TriggerReason.INVENTORY_HIGH):
                    triggers.append(TriggerReason.INVENTORY_HIGH)
                    logger.info(f"CDC: Inventory high {inv_ratio:.1%} at {self.site_key}")

        return triggers

    def _check_service_level(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for service level drop below target"""
        triggers = []

        sl_threshold = metrics.target_service_level - self.config.thresholds['service_level_drop']
        if metrics.service_level < sl_threshold:
            if self._cooldown_ok(TriggerReason.SERVICE_LEVEL_DROP):
                triggers.append(TriggerReason.SERVICE_LEVEL_DROP)
                logger.warning(f"CDC: Service level {metrics.service_level:.1%} below target at {self.site_key}")

        return triggers

    def _check_lead_time(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for lead time increase"""
        triggers = []

        if metrics.avg_lead_time_expected > 0:
            lt_increase = (metrics.avg_lead_time_actual - metrics.avg_lead_time_expected) / metrics.avg_lead_time_expected
            if lt_increase > self.config.thresholds['lead_time_increase']:
                if self._cooldown_ok(TriggerReason.LEAD_TIME_INCREASE):
                    triggers.append(TriggerReason.LEAD_TIME_INCREASE)
                    logger.info(f"CDC: Lead time increase {lt_increase:.1%} at {self.site_key}")

        return triggers

    def _check_backlog_growth(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for consecutive days of backlog growth"""
        triggers = []

        if metrics.backlog_units > metrics.backlog_yesterday:
            self.backlog_growth_days += 1
            if self.backlog_growth_days >= self.config.thresholds['backlog_growth_days']:
                if self._cooldown_ok(TriggerReason.BACKLOG_GROWTH):
                    triggers.append(TriggerReason.BACKLOG_GROWTH)
                    logger.info(f"CDC: Backlog growing for {self.backlog_growth_days} days at {self.site_key}")
        else:
            self.backlog_growth_days = 0  # Reset counter

        return triggers

    def _check_supplier_reliability(self, metrics: SiteMetrics) -> List[TriggerReason]:
        """Check for supplier on-time rate drop"""
        triggers = []

        target_reliability = 0.95  # Could be parameterized
        threshold = target_reliability - self.config.thresholds['supplier_reliability_drop']

        if metrics.supplier_on_time_rate < threshold:
            if self._cooldown_ok(TriggerReason.SUPPLIER_RELIABILITY):
                triggers.append(TriggerReason.SUPPLIER_RELIABILITY)
                logger.info(f"CDC: Supplier OT rate {metrics.supplier_on_time_rate:.1%} at {self.site_key}")

        return triggers

    def _cooldown_ok(self, reason: TriggerReason) -> bool:
        """Check if cooldown period has passed for this trigger type"""
        if reason not in self.last_trigger_time:
            return True

        elapsed = datetime.utcnow() - self.last_trigger_time[reason]
        return elapsed > timedelta(hours=self.config.cooldown_hours)

    def _cfa_allowed(self) -> bool:
        """Check if full CFA is allowed (rate limiting)"""
        if self.last_cfa_time is None:
            return True

        elapsed = datetime.utcnow() - self.last_cfa_time
        return elapsed > timedelta(days=self.config.max_cfa_per_period_days)

    def _determine_action_and_severity(
        self,
        triggers: List[TriggerReason]
    ) -> tuple:
        """
        Map trigger combination to action and severity.

        Priority:
        - SERVICE_LEVEL_DROP → FULL_CFA (critical - customer impact)
        - DEMAND_DEVIATION → FULL_CFA (high - forecast invalidated)
        - SUPPLIER_RELIABILITY → FULL_CFA (high - supply disruption)
        - INVENTORY_LOW → ALLOCATION_ONLY (medium - rebalance)
        - LEAD_TIME_INCREASE → PARAM_ADJUSTMENT (medium - buffer adjustment)
        - INVENTORY_HIGH / BACKLOG → ALLOCATION_ONLY (low - optimize)
        """

        # Critical: Customer-facing impact
        if TriggerReason.SERVICE_LEVEL_DROP in triggers:
            return ReplanAction.FULL_CFA, "critical"

        # High: Fundamental assumption change
        if TriggerReason.DEMAND_DEVIATION in triggers:
            return ReplanAction.FULL_CFA, "high"

        if TriggerReason.SUPPLIER_RELIABILITY in triggers:
            return ReplanAction.FULL_CFA, "high"

        # Medium: Operational adjustment needed
        if TriggerReason.INVENTORY_LOW in triggers:
            return ReplanAction.ALLOCATION_ONLY, "medium"

        if TriggerReason.LEAD_TIME_INCREASE in triggers:
            return ReplanAction.PARAM_ADJUSTMENT, "medium"

        # Low: Optimization opportunity
        return ReplanAction.ALLOCATION_ONLY, "low"

    def reset_counters(self):
        """Reset all counters and trigger times"""
        self.last_trigger_time.clear()
        self.last_cfa_time = None
        self.backlog_growth_days = 0

    def get_status(self) -> Dict[str, Any]:
        """Get current monitor status"""
        return {
            'site_key': self.site_key,
            'enabled': self.config.enabled,
            'backlog_growth_days': self.backlog_growth_days,
            'last_cfa_time': self.last_cfa_time.isoformat() if self.last_cfa_time else None,
            'last_triggers': {
                reason.value: time.isoformat()
                for reason, time in self.last_trigger_time.items()
            },
            'thresholds': self.config.thresholds
        }

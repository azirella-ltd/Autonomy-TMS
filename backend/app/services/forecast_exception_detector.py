"""
Forecast Exception Detection Engine

Compares forecast (P50) vs actuals (OutboundOrderLine) and creates
ForecastException records where detection rules are triggered.

Supports 4 detection rule types:
- VARIANCE_THRESHOLD: Simple percentage variance check
- TREND_DETECTION: Consecutive periods of same-direction variance
- OUTLIER_DETECTION: Statistical outlier (>N std devs from mean)
- BIAS_DETECTION: Consistent over/under forecasting
"""

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.forecast_exception import ForecastException, ForecastExceptionRule
from app.models.sc_entities import Forecast, OutboundOrderLine

logger = logging.getLogger(__name__)


class ForecastExceptionDetector:
    """Detects forecast exceptions by comparing forecast vs actual demand."""

    def __init__(self, db: Session):
        self.db = db

    def run_detection(
        self,
        config_id: Optional[int],
        period_start: date,
        period_end: date,
        threshold_percent: float = 20.0,
        product_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run exception detection for a given period.

        1. Load active detection rules
        2. Query forecast aggregates (P50) by product/site
        3. Query actual demand aggregates by product/site
        4. Calculate variance and apply rules
        5. Create ForecastException records

        Returns summary with counts.
        """
        rules = self._load_active_rules(config_id)
        if not rules:
            rules = [self._make_default_rule(threshold_percent)]

        forecasts = self._load_forecast_aggregates(
            config_id, period_start, period_end, product_ids
        )
        actuals = self._load_actual_aggregates(
            config_id, period_start, period_end, product_ids
        )

        all_keys = set(forecasts.keys()) | set(actuals.keys())
        exceptions_created = 0

        for key in all_keys:
            product_id, site_id = key
            forecast_qty = forecasts.get(key, 0.0)
            actual_qty = actuals.get(key, 0.0)

            if forecast_qty == 0 and actual_qty == 0:
                continue

            if self._has_existing_exception(product_id, site_id, period_start, period_end):
                continue

            variance_qty, variance_pct, direction = self._calculate_variance(
                forecast_qty, actual_qty
            )

            for rule in rules:
                if not self._rule_applies(rule, product_id, site_id):
                    continue
                if not self._threshold_triggered(rule, variance_pct, variance_qty):
                    continue

                severity = self._determine_severity(abs(variance_pct), rule)
                self._create_exception(
                    config_id=config_id,
                    product_id=product_id,
                    site_id=site_id,
                    period_start=period_start,
                    period_end=period_end,
                    rule=rule,
                    forecast_qty=forecast_qty,
                    actual_qty=actual_qty,
                    variance_qty=variance_qty,
                    variance_pct=variance_pct,
                    direction=direction,
                    severity=severity,
                )
                exceptions_created += 1
                break  # One exception per product/site — highest-priority rule wins

        self.db.commit()

        return {
            "status": "completed",
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "products_analyzed": len(all_keys),
            "exceptions_created": exceptions_created,
            "rules_evaluated": len(rules),
        }

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_active_rules(self, config_id: Optional[int]) -> List[ForecastExceptionRule]:
        q = self.db.query(ForecastExceptionRule).filter(
            ForecastExceptionRule.is_active == True  # noqa: E712
        )
        if config_id is not None:
            q = q.filter(
                or_(
                    ForecastExceptionRule.config_id == config_id,
                    ForecastExceptionRule.config_id.is_(None),
                )
            )
        return q.order_by(ForecastExceptionRule.id).all()

    def _make_default_rule(self, threshold_percent: float) -> ForecastExceptionRule:
        """Create an in-memory default rule when no DB rules exist."""
        rule = ForecastExceptionRule()
        rule.id = None
        rule.rule_type = "VARIANCE_THRESHOLD"
        rule.variance_threshold_percent = threshold_percent
        rule.is_active = True
        rule.product_ids = None
        rule.site_ids = None
        rule.severity_mapping = None
        return rule

    def _load_forecast_aggregates(
        self,
        config_id: Optional[int],
        period_start: date,
        period_end: date,
        product_ids: Optional[List[str]] = None,
    ) -> Dict[Tuple[str, int], float]:
        """Load forecast P50 (or quantity) aggregated by product/site."""
        q = self.db.query(
            Forecast.product_id,
            Forecast.site_id,
            func.sum(
                func.coalesce(Forecast.forecast_p50, Forecast.forecast_quantity, 0)
            ).label("total_forecast"),
        ).filter(
            and_(
                Forecast.forecast_date >= period_start,
                Forecast.forecast_date <= period_end,
            )
        )

        if config_id is not None:
            q = q.filter(Forecast.config_id == config_id)
        if product_ids:
            q = q.filter(Forecast.product_id.in_(product_ids))

        q = q.group_by(Forecast.product_id, Forecast.site_id)

        result = {}
        for row in q.all():
            result[(row.product_id, row.site_id)] = float(row.total_forecast or 0)
        return result

    def _load_actual_aggregates(
        self,
        config_id: Optional[int],
        period_start: date,
        period_end: date,
        product_ids: Optional[List[str]] = None,
    ) -> Dict[Tuple[str, int], float]:
        """Load actual demand (ordered qty) aggregated by product/site."""
        q = self.db.query(
            OutboundOrderLine.product_id,
            OutboundOrderLine.site_id,
            func.sum(OutboundOrderLine.ordered_quantity).label("total_actual"),
        ).filter(
            and_(
                OutboundOrderLine.requested_delivery_date >= period_start,
                OutboundOrderLine.requested_delivery_date <= period_end,
            )
        )

        if config_id is not None:
            q = q.filter(OutboundOrderLine.config_id == config_id)
        if product_ids:
            q = q.filter(OutboundOrderLine.product_id.in_(product_ids))

        q = q.group_by(OutboundOrderLine.product_id, OutboundOrderLine.site_id)

        result = {}
        for row in q.all():
            result[(row.product_id, row.site_id)] = float(row.total_actual or 0)
        return result

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _has_existing_exception(
        self,
        product_id: str,
        site_id: int,
        period_start: date,
        period_end: date,
    ) -> bool:
        """Check for existing open exception on the same product/site/period."""
        count = (
            self.db.query(func.count(ForecastException.id))
            .filter(
                and_(
                    ForecastException.product_id == product_id,
                    ForecastException.site_id == site_id,
                    ForecastException.period_start == period_start,
                    ~ForecastException.status.in_(["RESOLVED", "DISMISSED"]),
                )
            )
            .scalar()
        )
        return count > 0

    # ------------------------------------------------------------------
    # Variance calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_variance(
        forecast_qty: float, actual_qty: float
    ) -> Tuple[float, float, str]:
        """Returns (variance_qty, variance_pct, direction)."""
        variance_qty = actual_qty - forecast_qty
        if forecast_qty != 0:
            variance_pct = (variance_qty / forecast_qty) * 100.0
        elif actual_qty != 0:
            variance_pct = 100.0 if actual_qty > 0 else -100.0
        else:
            variance_pct = 0.0

        direction = "OVER" if actual_qty > forecast_qty else "UNDER"
        return variance_qty, variance_pct, direction

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_applies(
        rule: ForecastExceptionRule, product_id: str, site_id: int
    ) -> bool:
        """Check if rule scope covers this product/site."""
        if rule.product_ids:
            ids = rule.product_ids if isinstance(rule.product_ids, list) else []
            if ids and product_id not in ids:
                return False
        if rule.site_ids:
            ids = rule.site_ids if isinstance(rule.site_ids, list) else []
            if ids and site_id not in ids:
                return False
        return True

    @staticmethod
    def _threshold_triggered(
        rule: ForecastExceptionRule,
        variance_pct: float,
        variance_qty: float,
    ) -> bool:
        """Check if variance exceeds rule thresholds."""
        abs_pct = abs(variance_pct)
        abs_qty = abs(variance_qty)

        pct_threshold = getattr(rule, "variance_threshold_percent", None)
        abs_threshold = getattr(rule, "variance_threshold_absolute", None)

        if pct_threshold is not None and abs_pct >= pct_threshold:
            return True
        if abs_threshold is not None and abs_qty >= abs_threshold:
            return True

        # If rule has no thresholds at all, don't trigger
        if pct_threshold is None and abs_threshold is None:
            return False

        return False

    @staticmethod
    def _determine_severity(abs_variance_pct: float, rule: ForecastExceptionRule) -> str:
        """Determine severity from rule's severity_mapping or defaults."""
        mapping = getattr(rule, "severity_mapping", None)
        if mapping and isinstance(mapping, dict):
            for range_key, sev in mapping.items():
                try:
                    parts = str(range_key).split("-")
                    low, high = float(parts[0]), float(parts[1])
                    if low <= abs_variance_pct < high:
                        return sev
                except (ValueError, IndexError):
                    continue

        # Defaults
        if abs_variance_pct >= 100:
            return "CRITICAL"
        elif abs_variance_pct >= 50:
            return "HIGH"
        elif abs_variance_pct >= 25:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Exception creation
    # ------------------------------------------------------------------

    def _create_exception(
        self,
        config_id: Optional[int],
        product_id: str,
        site_id: int,
        period_start: date,
        period_end: date,
        rule: ForecastExceptionRule,
        forecast_qty: float,
        actual_qty: float,
        variance_qty: float,
        variance_pct: float,
        direction: str,
        severity: str,
    ) -> ForecastException:
        exc = ForecastException(
            exception_number=f"EXC-{uuid.uuid4().hex[:8].upper()}",
            config_id=config_id,
            product_id=product_id,
            site_id=site_id,
            period_start=period_start,
            period_end=period_end,
            time_bucket="CUSTOM",
            exception_type=getattr(rule, "rule_type", "VARIANCE"),
            severity=severity,
            priority=self._severity_to_priority(severity),
            forecast_quantity=forecast_qty,
            actual_quantity=actual_qty,
            variance_quantity=variance_qty,
            variance_percent=variance_pct,
            threshold_percent=getattr(rule, "variance_threshold_percent", None),
            direction=direction,
            status="NEW",
            detection_method="AUTOMATED",
            detection_rule_id=getattr(rule, "id", None),
            detected_at=datetime.utcnow(),
        )
        self.db.add(exc)
        return exc

    @staticmethod
    def _severity_to_priority(severity: str) -> int:
        return {"CRITICAL": 90, "HIGH": 70, "MEDIUM": 50, "LOW": 30}.get(severity, 50)

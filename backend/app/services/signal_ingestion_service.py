"""
Signal Ingestion Service — Bridge from OpenClaw channels to ForecastAdjustmentTRM.

Processes external signals (from Slack, Teams, WhatsApp, email, voice, news, etc.)
through a confidence-gated pipeline:

  Channel → Normalize → Classify → Score confidence → Gate → Route

Confidence gating:
  - >= 0.8: Auto-apply via ForecastAdjustmentTRM
  - 0.3 - 0.8: Queue for human review
  - < 0.3: Reject (log for audit)

Multi-signal correlation:
  Signals from different channels agreeing on same product/direction within 2h
  get combined confidence = 1 - product(1 - conf_i).

Architecture: TRM_HIVE_ARCHITECTURE.md Section 2, PICOCLAW_OPENCLAW_IMPLEMENTATION.md Phase 5
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Edge agent models removed — PicoClaw/OpenClaw replaced by Claude Skills ecosystem.
# Signal ingestion logic preserved for future Claude-based signal pipeline.
# TODO: Refactor to use inline models or new signal tables.
EdgeIngestedSignal = None
EdgeSignalCorrelation = None
EdgeSourceReliability = None
EdgeOpenClawSession = None
EdgeActivityLog = None

import logging

logger = logging.getLogger(__name__)


# Confidence thresholds
AUTO_APPLY_THRESHOLD = 0.8
REVIEW_THRESHOLD = 0.3

# Rate limiting
MAX_SIGNALS_PER_SOURCE_PER_HOUR = 100
MAX_SIGNALS_GLOBAL_PER_HOUR = 500
DEDUP_WINDOW_HOURS = 1

# Magnitude caps
MAX_ADJUSTMENT_PCT = 50.0  # ±50%

# Correlation window
CORRELATION_WINDOW_HOURS = 2

# Prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above)\s+(instructions?|prompts?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\s*/?script", re.I),
    re.compile(r"```\s*(python|bash|sh|cmd)", re.I),
    re.compile(r"(exec|eval|import\s+os|subprocess)", re.I),
]

# Valid signal types
VALID_SIGNAL_TYPES = {
    "DEMAND_INCREASE", "DEMAND_DECREASE", "DISRUPTION", "PRICE_CHANGE",
    "LEAD_TIME_CHANGE", "QUALITY_ALERT", "NEW_OPPORTUNITY", "COMPETITOR_ACTION",
}

# Channel-to-source mapping defaults
CHANNEL_SOURCE_MAP = {
    "slack_demand": "sales_input",
    "slack_customer": "customer_feedback",
    "slack": "sales_input",
    "teams": "sales_input",
    "whatsapp": "sales_input",
    "telegram": "customer_feedback",
    "email_customer": "customer_feedback",
    "email_market": "market_intelligence",
    "email": "customer_feedback",
    "voice": "voice",
    "weather_api": "weather",
    "economic_api": "economic_indicator",
    "news_rss": "news",
}


class SignalIngestionService:
    """Processes external signals through the confidence-gated ingestion pipeline."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_signal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main ingestion entry point.

        Args:
            data: {
                channel: str,
                raw_text: str,
                signal_type: str,
                direction: str (up/down/no_change),
                product_id: Optional[str],
                site_id: Optional[str],
                magnitude_hint: Optional[float],
                base_confidence: Optional[float],
            }

        Returns:
            Ingestion result with signal_id, status, confidence breakdown.
        """
        channel = data.get("channel", "unknown")
        raw_text = data.get("raw_text", "")

        # 1. Input sanitization
        sanitized_text = self._sanitize_input(raw_text)
        injection_detected = self._check_injection(sanitized_text)
        if injection_detected:
            await self._log_activity(
                "signal", "Blocked prompt injection attempt",
                details={"channel": channel, "pattern": injection_detected},
                severity="warning",
            )
            return {
                "signal_id": None,
                "status": "rejected",
                "reason": "Prompt injection pattern detected",
                "injection_blocked": True,
            }

        # 2. Rate limiting check
        is_limited, limit_info = await self._check_rate_limit(channel)
        if is_limited:
            return {
                "signal_id": None,
                "status": "rate_limited",
                "reason": f"Rate limit exceeded: {limit_info}",
            }

        # 3. Deduplication check
        is_dup, dup_signal_id = await self._check_duplicate(data)
        if is_dup:
            return {
                "signal_id": dup_signal_id,
                "status": "duplicate",
                "reason": "Duplicate signal within deduplication window",
            }

        # 4. Resolve source from channel
        source = CHANNEL_SOURCE_MAP.get(channel, data.get("source", "unknown"))

        # 5. Compute confidence
        base_confidence = data.get("base_confidence", 0.5)
        source_reliability = await self._get_source_weight(source)
        time_decay = 1.0  # Fresh signal, no decay yet
        final_confidence = base_confidence * source_reliability * time_decay

        # 6. Determine status based on confidence gating
        signal_type = data.get("signal_type", "DEMAND_INCREASE")
        if signal_type not in VALID_SIGNAL_TYPES:
            signal_type = "DEMAND_INCREASE"

        if final_confidence >= AUTO_APPLY_THRESHOLD:
            status = "auto_applied"
        elif final_confidence >= REVIEW_THRESHOLD:
            status = "pending"
        else:
            status = "rejected"

        # 7. Cap magnitude
        magnitude_hint = data.get("magnitude_hint")
        if magnitude_hint is not None:
            magnitude_hint = max(-MAX_ADJUSTMENT_PCT, min(MAX_ADJUSTMENT_PCT, magnitude_hint))

        # 8. Create signal record
        signal_id = str(uuid.uuid4())
        signal = EdgeIngestedSignal(
            signal_id=signal_id,
            channel=channel,
            source=source,
            raw_text=sanitized_text[:2000],  # Truncate long text
            signal_type=signal_type,
            direction=data.get("direction", "up"),
            product_id=data.get("product_id"),
            site_id=data.get("site_id"),
            base_confidence=base_confidence,
            source_reliability=source_reliability,
            time_decay=time_decay,
            final_confidence=final_confidence,
            status=status,
            magnitude_hint=magnitude_hint,
        )
        self.db.add(signal)

        # 9. Update source signal count
        await self._increment_source_count(source)

        # 10. Check for multi-signal correlation
        correlation = await self._check_correlation(signal)

        await self.db.flush()

        result = {
            "signal_id": signal_id,
            "status": status,
            "confidence": {
                "base": base_confidence,
                "source_reliability": source_reliability,
                "time_decay": time_decay,
                "final": final_confidence,
            },
            "magnitude_hint": magnitude_hint,
            "correlation_group_id": correlation.get("correlation_id") if correlation else None,
        }

        # 11. If auto-apply, route to ForecastAdjustmentTRM
        if status == "auto_applied":
            trm_result = await self._route_to_forecast_trm(signal, data)
            result["auto_applied"] = True
            result["message"] = "Signal auto-applied (confidence >= 0.8)"
            if trm_result:
                result["trm_recommendation"] = trm_result
                signal.magnitude_applied = trm_result.get("adjustment_pct")
                signal.adjustment_id = trm_result.get("decision_id")
        elif status == "approved":
            # Approved signals also route to TRM
            trm_result = await self._route_to_forecast_trm(signal, data)
            result["message"] = "Signal approved and applied"
            if trm_result:
                result["trm_recommendation"] = trm_result
                signal.magnitude_applied = trm_result.get("adjustment_pct")
        elif status == "pending":
            result["message"] = "Signal queued for human review (confidence 0.3-0.8)"
        else:
            result["message"] = "Signal rejected (confidence < 0.3)"

        await self._log_activity(
            "signal", f"Ingested signal: {signal_type} from {channel}",
            details={"signal_id": signal_id, "status": status, "confidence": final_confidence},
        )

        return result

    async def get_dashboard(self, period: str = "today") -> Dict[str, Any]:
        """Get signal ingestion dashboard summary."""
        now = datetime.now(timezone.utc)
        if period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Status counts
        status_q = (
            select(EdgeIngestedSignal.status, func.count(EdgeIngestedSignal.id))
            .where(EdgeIngestedSignal.created_at >= since)
            .group_by(EdgeIngestedSignal.status)
        )
        status_result = await self.db.execute(status_q)
        status_counts = {row[0]: row[1] for row in status_result.all()}

        total = sum(status_counts.values())

        # Type breakdown
        type_q = (
            select(EdgeIngestedSignal.signal_type, func.count(EdgeIngestedSignal.id))
            .where(EdgeIngestedSignal.created_at >= since)
            .group_by(EdgeIngestedSignal.signal_type)
        )
        type_result = await self.db.execute(type_q)
        type_breakdown = [{"type": row[0], "count": row[1]} for row in type_result.all()]

        # Source breakdown
        source_q = (
            select(EdgeIngestedSignal.source, func.count(EdgeIngestedSignal.id))
            .where(EdgeIngestedSignal.created_at >= since)
            .group_by(EdgeIngestedSignal.source)
        )
        source_result = await self.db.execute(source_q)
        source_breakdown = []
        for row in source_result.all():
            weight = await self._get_source_weight(row[0])
            source_breakdown.append({"source": row[0], "count": row[1], "reliability": weight})

        # Correlation groups count
        corr_q = (
            select(func.count(EdgeSignalCorrelation.id))
            .where(EdgeSignalCorrelation.created_at >= since)
            .where(EdgeSignalCorrelation.status == "active")
        )
        corr_result = await self.db.execute(corr_q)
        corr_count = corr_result.scalar() or 0

        # Signals this hour
        hour_ago = now - timedelta(hours=1)
        hour_q = (
            select(func.count(EdgeIngestedSignal.id))
            .where(EdgeIngestedSignal.created_at >= hour_ago)
        )
        hour_result = await self.db.execute(hour_q)
        signals_this_hour = hour_result.scalar() or 0

        return {
            "signals_today": total,
            "auto_applied": status_counts.get("auto_applied", 0),
            "pending_review": status_counts.get("pending", 0),
            "rejected": status_counts.get("rejected", 0),
            "correlated_groups": corr_count,
            "signals_this_hour": signals_this_hour,
            "duplicates_filtered": status_counts.get("duplicate", 0),
            "injection_attempts": 0,  # Would need separate counter
            "rate_limited": status_counts.get("rate_limited", 0),
            "type_breakdown": type_breakdown,
            "source_breakdown": source_breakdown,
        }

    async def get_signals(
        self,
        source: Optional[str] = None,
        signal_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get signals with optional filters."""
        q = select(EdgeIngestedSignal).order_by(desc(EdgeIngestedSignal.created_at)).limit(limit)
        if source:
            q = q.where(EdgeIngestedSignal.source == source)
        if signal_type:
            q = q.where(EdgeIngestedSignal.signal_type == signal_type)
        if status:
            q = q.where(EdgeIngestedSignal.status == status)
        result = await self.db.execute(q)
        return [s.to_dict() for s in result.scalars().all()]

    async def get_pending_signals(
        self, source: Optional[str] = None, limit: int = 50
    ) -> List[Dict]:
        """Get signals pending human review."""
        q = (
            select(EdgeIngestedSignal)
            .where(EdgeIngestedSignal.status == "pending")
            .order_by(desc(EdgeIngestedSignal.final_confidence))
            .limit(limit)
        )
        if source:
            q = q.where(EdgeIngestedSignal.source == source)
        result = await self.db.execute(q)
        return [s.to_dict() for s in result.scalars().all()]

    async def get_signal_details(self, signal_id: str) -> Optional[Dict]:
        """Get full signal details with confidence breakdown."""
        result = await self.db.execute(
            select(EdgeIngestedSignal).where(EdgeIngestedSignal.signal_id == signal_id)
        )
        signal = result.scalar_one_or_none()
        if not signal:
            return None
        d = signal.to_dict()
        d["confidence_breakdown"] = {
            "base_confidence": signal.base_confidence,
            "source_reliability": signal.source_reliability,
            "time_decay": signal.time_decay,
            "formula": "base_confidence × source_reliability × time_decay",
            "final": signal.final_confidence,
        }
        return d

    async def approve_signal(
        self, signal_id: str, magnitude_override: Optional[float] = None, reason: Optional[str] = None
    ) -> Optional[Dict]:
        """Approve a pending signal and mark for forecast adjustment."""
        result = await self.db.execute(
            select(EdgeIngestedSignal).where(EdgeIngestedSignal.signal_id == signal_id)
        )
        signal = result.scalar_one_or_none()
        if not signal or signal.status != "pending":
            return None

        signal.status = "approved"
        signal.reviewed_at = datetime.now(timezone.utc)
        signal.review_reason = reason
        if magnitude_override is not None:
            magnitude_override = max(-MAX_ADJUSTMENT_PCT, min(MAX_ADJUSTMENT_PCT, magnitude_override))
            signal.magnitude_applied = magnitude_override
        else:
            signal.magnitude_applied = signal.magnitude_hint

        await self.db.flush()
        await self._log_activity(
            "signal", f"Approved signal {signal_id}",
            details={"magnitude": signal.magnitude_applied},
        )
        return signal.to_dict()

    async def reject_signal(self, signal_id: str, reason: str) -> Optional[Dict]:
        """Reject a pending signal."""
        result = await self.db.execute(
            select(EdgeIngestedSignal).where(EdgeIngestedSignal.signal_id == signal_id)
        )
        signal = result.scalar_one_or_none()
        if not signal or signal.status != "pending":
            return None

        signal.status = "rejected"
        signal.reviewed_at = datetime.now(timezone.utc)
        signal.review_reason = reason
        await self.db.flush()
        await self._log_activity("signal", f"Rejected signal {signal_id}", details={"reason": reason})
        return signal.to_dict()

    async def get_correlations(self, limit: int = 20) -> List[Dict]:
        """Get active multi-signal correlation groups."""
        result = await self.db.execute(
            select(EdgeSignalCorrelation)
            .where(EdgeSignalCorrelation.status == "active")
            .order_by(desc(EdgeSignalCorrelation.combined_confidence))
            .limit(limit)
        )
        return [c.to_dict() for c in result.scalars().all()]

    async def get_adjustment_history(self, limit: int = 50) -> List[Dict]:
        """Get forecast adjustments applied from signals."""
        result = await self.db.execute(
            select(EdgeIngestedSignal)
            .where(EdgeIngestedSignal.status.in_(["auto_applied", "approved"]))
            .order_by(desc(EdgeIngestedSignal.created_at))
            .limit(limit)
        )
        return [s.to_dict() for s in result.scalars().all()]

    async def revert_adjustment(self, signal_id: str) -> Optional[Dict]:
        """Revert a previously applied forecast adjustment."""
        result = await self.db.execute(
            select(EdgeIngestedSignal).where(EdgeIngestedSignal.signal_id == signal_id)
        )
        signal = result.scalar_one_or_none()
        if not signal or signal.status not in ("auto_applied", "approved"):
            return None

        signal.status = "reverted"
        signal.reviewed_at = datetime.now(timezone.utc)
        signal.review_reason = "Reverted by user"
        await self.db.flush()
        await self._log_activity("signal", f"Reverted adjustment for signal {signal_id}")
        return signal.to_dict()

    # -------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------

    async def get_rate_limits(self) -> Dict[str, Any]:
        """Get rate limiting status."""
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        # Global count
        global_q = select(func.count(EdgeIngestedSignal.id)).where(
            EdgeIngestedSignal.created_at >= hour_ago
        )
        global_result = await self.db.execute(global_q)
        global_count = global_result.scalar() or 0

        # Per-source counts
        source_q = (
            select(EdgeIngestedSignal.source, func.count(EdgeIngestedSignal.id))
            .where(EdgeIngestedSignal.created_at >= hour_ago)
            .group_by(EdgeIngestedSignal.source)
        )
        source_result = await self.db.execute(source_q)
        per_source = {row[0]: row[1] for row in source_result.all()}

        return {
            "per_source_limit": MAX_SIGNALS_PER_SOURCE_PER_HOUR,
            "global_limit": MAX_SIGNALS_GLOBAL_PER_HOUR,
            "current_hour_total": global_count,
            "per_source_current": per_source,
            "deduplication_window_hours": DEDUP_WINDOW_HOURS,
        }

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _sanitize_input(self, text: str) -> str:
        """Strip control characters and normalize whitespace."""
        if not text:
            return ""
        # Remove control chars except newline/tab
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _check_injection(self, text: str) -> Optional[str]:
        """Check for prompt injection patterns. Returns pattern name or None."""
        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                return pattern.pattern
        return None

    async def _check_rate_limit(self, channel: str) -> Tuple[bool, str]:
        """Check if rate limit is exceeded."""
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        source = CHANNEL_SOURCE_MAP.get(channel, "unknown")

        # Per-source check
        source_q = select(func.count(EdgeIngestedSignal.id)).where(
            and_(
                EdgeIngestedSignal.source == source,
                EdgeIngestedSignal.created_at >= hour_ago,
            )
        )
        source_result = await self.db.execute(source_q)
        source_count = source_result.scalar() or 0
        if source_count >= MAX_SIGNALS_PER_SOURCE_PER_HOUR:
            return True, f"{source}: {source_count}/{MAX_SIGNALS_PER_SOURCE_PER_HOUR}"

        # Global check
        global_q = select(func.count(EdgeIngestedSignal.id)).where(
            EdgeIngestedSignal.created_at >= hour_ago
        )
        global_result = await self.db.execute(global_q)
        global_count = global_result.scalar() or 0
        if global_count >= MAX_SIGNALS_GLOBAL_PER_HOUR:
            return True, f"global: {global_count}/{MAX_SIGNALS_GLOBAL_PER_HOUR}"

        return False, ""

    async def _check_duplicate(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Check for duplicate signal within dedup window."""
        window_start = datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
        q = (
            select(EdgeIngestedSignal.signal_id)
            .where(
                and_(
                    EdgeIngestedSignal.channel == data.get("channel", ""),
                    EdgeIngestedSignal.signal_type == data.get("signal_type", ""),
                    EdgeIngestedSignal.direction == data.get("direction", ""),
                    EdgeIngestedSignal.product_id == data.get("product_id"),
                    EdgeIngestedSignal.site_id == data.get("site_id"),
                    EdgeIngestedSignal.created_at >= window_start,
                    EdgeIngestedSignal.status != "rejected",
                )
            )
            .limit(1)
        )
        result = await self.db.execute(q)
        existing = result.scalar_one_or_none()
        if existing:
            return True, existing
        return False, None

    async def _get_source_weight(self, source: str) -> float:
        """Get effective reliability weight for a source."""
        result = await self.db.execute(
            select(EdgeSourceReliability).where(EdgeSourceReliability.source == source)
        )
        src = result.scalar_one_or_none()
        if not src:
            return 0.5
        return src.effective_weight

    async def _increment_source_count(self, source: str) -> None:
        """Increment the signal count for a source."""
        result = await self.db.execute(
            select(EdgeSourceReliability).where(EdgeSourceReliability.source == source)
        )
        src = result.scalar_one_or_none()
        if src:
            src.signals_count = (src.signals_count or 0) + 1

    async def _check_correlation(self, signal: EdgeIngestedSignal) -> Optional[Dict]:
        """Check if this signal correlates with existing signals from different channels."""
        if not signal.product_id:
            return None

        window_start = datetime.now(timezone.utc) - timedelta(hours=CORRELATION_WINDOW_HOURS)

        # Find signals with same product/direction from different channels
        q = (
            select(EdgeIngestedSignal)
            .where(
                and_(
                    EdgeIngestedSignal.product_id == signal.product_id,
                    EdgeIngestedSignal.direction == signal.direction,
                    EdgeIngestedSignal.channel != signal.channel,
                    EdgeIngestedSignal.created_at >= window_start,
                    EdgeIngestedSignal.status.in_(["pending", "auto_applied", "approved"]),
                )
            )
        )
        result = await self.db.execute(q)
        correlated_signals = result.scalars().all()

        if not correlated_signals:
            return None

        # Find or create correlation group
        all_signal_ids = [s.signal_id for s in correlated_signals] + [signal.signal_id]

        # Check if any existing correlation group contains these signals
        existing_corr = None
        for cs in correlated_signals:
            if cs.correlation_group_id:
                corr_result = await self.db.execute(
                    select(EdgeSignalCorrelation).where(
                        EdgeSignalCorrelation.correlation_id == cs.correlation_group_id
                    )
                )
                existing_corr = corr_result.scalar_one_or_none()
                if existing_corr:
                    break

        if existing_corr:
            # Add to existing group
            current_ids = existing_corr.signal_ids or []
            if signal.signal_id not in current_ids:
                current_ids.append(signal.signal_id)
                existing_corr.signal_ids = current_ids
                existing_corr.signal_count = len(current_ids)
            # Recompute combined confidence: 1 - product(1 - conf_i)
            all_confs = [signal.final_confidence or 0.5]
            for cs in correlated_signals:
                all_confs.append(cs.final_confidence or 0.5)
            product = 1.0
            for c in all_confs:
                product *= (1.0 - c)
            existing_corr.combined_confidence = 1.0 - product
            signal.correlation_group_id = existing_corr.correlation_id
            return existing_corr.to_dict()
        else:
            # Create new correlation group
            corr_id = str(uuid.uuid4())
            all_confs = [signal.final_confidence or 0.5]
            for cs in correlated_signals:
                all_confs.append(cs.final_confidence or 0.5)
            product = 1.0
            for c in all_confs:
                product *= (1.0 - c)
            combined = 1.0 - product

            corr = EdgeSignalCorrelation(
                correlation_id=corr_id,
                product_id=signal.product_id,
                site_id=signal.site_id,
                direction=signal.direction,
                signal_ids=all_signal_ids,
                signal_count=len(all_signal_ids),
                combined_confidence=combined,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=CORRELATION_WINDOW_HOURS),
            )
            self.db.add(corr)

            # Update all correlated signals with group id
            signal.correlation_group_id = corr_id
            for cs in correlated_signals:
                cs.correlation_group_id = corr_id

            return corr.to_dict()

    async def _route_to_forecast_trm(
        self, signal: EdgeIngestedSignal, data: Dict[str, Any],
    ) -> Optional[Dict]:
        """Route an auto-applied or approved signal to ForecastAdjustmentTRM.

        Creates a ForecastAdjustmentState and calls evaluate_signal().
        Returns the TRM recommendation summary or None on error.
        """
        try:
            from app.services.powell.forecast_adjustment_trm import (
                ForecastAdjustmentTRM,
                ForecastAdjustmentState,
            )

            # Map signal types to forecast directions
            direction_map = {
                "DEMAND_INCREASE": "up",
                "DEMAND_DECREASE": "down",
                "NEW_OPPORTUNITY": "up",
                "DISRUPTION": "down",
                "PRICE_CHANGE": "no_change",
                "LEAD_TIME_CHANGE": "no_change",
                "QUALITY_ALERT": "down",
                "COMPETITOR_ACTION": "no_change",
            }
            direction = data.get("direction", direction_map.get(signal.signal_type, "no_change"))

            # Map signal types to engine signal types
            signal_type_map = {
                "DEMAND_INCREASE": "demand_increase",
                "DEMAND_DECREASE": "demand_decrease",
                "DISRUPTION": "disruption",
                "PRICE_CHANGE": "price_change",
                "LEAD_TIME_CHANGE": "lead_time_change",
                "QUALITY_ALERT": "quality_alert",
                "NEW_OPPORTUNITY": "new_product",
                "COMPETITOR_ACTION": "market_intelligence",
            }

            state = ForecastAdjustmentState(
                signal_id=signal.signal_id,
                product_id=signal.product_id or "UNKNOWN",
                site_id=signal.site_id or "UNKNOWN",
                source=signal.source,
                signal_type=signal_type_map.get(signal.signal_type, "demand_increase"),
                signal_text=signal.raw_text or "",
                signal_confidence=signal.final_confidence or 0.5,
                direction=direction,
                magnitude_hint=signal.magnitude_hint,
                signal_timestamp=signal.created_at,
                source_historical_accuracy=signal.source_reliability or 0.5,
            )

            # Initialize TRM for the target site (no trained model = heuristic fallback)
            trm = ForecastAdjustmentTRM(
                site_key=signal.site_id or "default",
                config=None,  # Uses defaults
                model=None,   # Heuristic fallback
                db_session=None,  # Don't double-persist; signal table tracks this
            )

            recommendation = trm.evaluate_signal(state)

            return {
                "should_adjust": recommendation.should_adjust,
                "direction": recommendation.direction,
                "adjustment_pct": recommendation.adjustment_pct,
                "adjustment_magnitude": recommendation.adjustment_magnitude,
                "adjusted_forecast_value": recommendation.adjusted_forecast_value,
                "confidence": recommendation.confidence,
                "auto_applicable": recommendation.auto_applicable,
                "reason": recommendation.reason,
                "decision_id": None,  # Not persisted via TRM (signal table tracks)
            }

        except Exception as e:
            logger.warning(f"ForecastAdjustmentTRM routing failed for signal {signal.signal_id}: {e}")
            return None

    async def _log_activity(
        self, component: str, action: str,
        details: Optional[Dict] = None, severity: str = "info",
    ) -> None:
        entry = EdgeActivityLog(
            component=component, action=action, details=details, severity=severity,
        )
        self.db.add(entry)

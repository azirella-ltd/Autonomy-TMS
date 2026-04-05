"""
Forecast Adjustment Engine

100% deterministic engine for processing external signals into forecast adjustments.
Handles: signal classification, magnitude estimation, confidence scoring.

TRM head learns to improve signal interpretation from historical accuracy.

Signals can come from:
- Email (parsed by NLP)
- Voice input (transcribed)
- Market intelligence feeds
- Customer feedback
- Sales team input
- News/events
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SignalSource(Enum):
    """Source of the forecast signal"""
    EMAIL = "email"
    VOICE = "voice"
    MARKET_INTELLIGENCE = "market_intelligence"
    NEWS = "news"
    CUSTOMER_FEEDBACK = "customer_feedback"
    SALES_INPUT = "sales_input"
    WEATHER = "weather"
    ECONOMIC_INDICATOR = "economic_indicator"
    SOCIAL_MEDIA = "social_media"
    COMPETITOR_ACTION = "competitor_action"


class SignalType(Enum):
    """Type of demand signal"""
    DEMAND_INCREASE = "demand_increase"
    DEMAND_DECREASE = "demand_decrease"
    NEW_PRODUCT = "new_product"
    DISCONTINUATION = "discontinuation"
    SEASONAL = "seasonal"
    PROMOTION = "promotion"
    DISRUPTION = "disruption"
    PRICE_CHANGE = "price_change"
    COMPETITOR = "competitor"
    REGULATORY = "regulatory"


class AdjustmentDirection(Enum):
    """Direction of forecast adjustment"""
    UP = "up"
    DOWN = "down"
    NO_CHANGE = "no_change"


@dataclass
class ForecastAdjustmentConfig:
    """Configuration for forecast adjustment engine"""
    # Signal confidence thresholds
    min_signal_confidence: float = 0.3  # Below this, ignore signal
    high_confidence_threshold: float = 0.8  # Above this, auto-apply

    # Adjustment magnitude limits
    max_adjustment_pct: float = 0.50  # Max 50% adjustment in either direction
    max_adjustment_pct_low_confidence: float = 0.15  # Max adjustment for low confidence

    # Source reliability weights (0-1)
    source_reliability: Dict[str, float] = field(default_factory=lambda: {
        "email": 0.5,
        "voice": 0.4,
        "market_intelligence": 0.8,
        "news": 0.6,
        "customer_feedback": 0.7,
        "sales_input": 0.7,
        "weather": 0.7,
        "economic_indicator": 0.8,
        "social_media": 0.3,
        "competitor_action": 0.6,
    })

    # Signal type impact multipliers
    signal_type_base_impact: Dict[str, float] = field(default_factory=lambda: {
        "demand_increase": 0.15,
        "demand_decrease": 0.15,
        "new_product": 0.30,
        "discontinuation": 0.50,
        "seasonal": 0.20,
        "promotion": 0.25,
        "disruption": 0.35,
        "price_change": 0.10,
        "competitor": 0.10,
        "regulatory": 0.20,
    })

    # Time decay
    signal_freshness_hours: int = 72  # Signals older than this get discounted
    signal_decay_rate: float = 0.1  # Per-day confidence decay


@dataclass
class ForecastSignal:
    """An incoming forecast adjustment signal"""
    signal_id: str
    product_id: str
    site_id: str

    # Signal details
    source: str  # From SignalSource enum values
    signal_type: str  # From SignalType enum values
    signal_text: str  # Raw text of the signal
    signal_confidence: float  # 0-1, how confident are we in the signal

    # Parsed intent (from NLP/LLM preprocessing)
    direction: str = "up"  # up, down, no_change
    magnitude_hint: Optional[float] = None  # If explicitly stated (e.g., "20% increase")

    # Time context
    time_horizon_periods: int = 4  # How many periods the adjustment applies
    signal_timestamp: Optional[datetime] = None
    effective_date: Optional[date] = None

    # Current forecast context
    current_forecast_value: float = 0.0
    current_forecast_confidence: float = 0.0  # Existing forecast confidence
    historical_accuracy_pct: float = 0.0  # Historical forecast accuracy for this product


@dataclass
class ForecastAdjustmentResult:
    """Result of forecast adjustment evaluation"""
    signal_id: str
    product_id: str
    site_id: str

    # Decision
    should_adjust: bool = False
    direction: AdjustmentDirection = AdjustmentDirection.NO_CHANGE
    adjustment_magnitude: float = 0.0  # Absolute adjustment
    adjustment_pct: float = 0.0  # Percentage adjustment
    adjusted_forecast_value: float = 0.0

    # Confidence
    signal_confidence: float = 0.0
    source_reliability: float = 0.0
    combined_confidence: float = 0.0

    # Time horizon
    time_horizon_periods: int = 0
    effective_date: Optional[date] = None

    # Impact
    current_forecast: float = 0.0
    forecast_change: float = 0.0

    # Flags
    requires_human_review: bool = False
    auto_applicable: bool = False

    explanation: str = ""


class ForecastAdjustmentEngine:
    """
    Deterministic Forecast Adjustment Engine.

    Processes external signals and converts them into quantified
    forecast adjustments with confidence scoring.
    """

    def __init__(self, site_key: str, config: Optional[ForecastAdjustmentConfig] = None):
        self.site_key = site_key
        self.config = config or ForecastAdjustmentConfig()

    def evaluate_signal(self, signal: ForecastSignal) -> ForecastAdjustmentResult:
        """Evaluate a forecast signal and determine adjustment."""
        # Step 1: Calculate source reliability
        source_reliability = self.config.source_reliability.get(signal.source, 0.5)

        # Step 2: Apply time decay
        time_factor = 1.0
        if signal.signal_timestamp:
            age_hours = (datetime.utcnow() - signal.signal_timestamp).total_seconds() / 3600
            if age_hours > self.config.signal_freshness_hours:
                excess_days = (age_hours - self.config.signal_freshness_hours) / 24
                time_factor = max(0.1, 1.0 - excess_days * self.config.signal_decay_rate)

        # Step 3: Combined confidence
        combined_confidence = (
            signal.signal_confidence *
            source_reliability *
            time_factor
        )

        # Step 4: Below minimum threshold?
        if combined_confidence < self.config.min_signal_confidence:
            return ForecastAdjustmentResult(
                signal_id=signal.signal_id,
                product_id=signal.product_id,
                site_id=signal.site_id,
                should_adjust=False,
                signal_confidence=signal.signal_confidence,
                source_reliability=source_reliability,
                combined_confidence=combined_confidence,
                current_forecast=signal.current_forecast_value,
                explanation=f"Signal too weak: combined confidence {combined_confidence:.2f} < {self.config.min_signal_confidence}"
            )

        # Step 5: Calculate magnitude
        direction = AdjustmentDirection(signal.direction) if signal.direction in ("up", "down", "no_change") else AdjustmentDirection.NO_CHANGE

        if direction == AdjustmentDirection.NO_CHANGE:
            return ForecastAdjustmentResult(
                signal_id=signal.signal_id,
                product_id=signal.product_id,
                site_id=signal.site_id,
                should_adjust=False,
                direction=direction,
                signal_confidence=signal.signal_confidence,
                source_reliability=source_reliability,
                combined_confidence=combined_confidence,
                current_forecast=signal.current_forecast_value,
                explanation="No change indicated"
            )

        # Use explicit magnitude if provided, otherwise estimate from signal type
        if signal.magnitude_hint is not None:
            adjustment_pct = min(abs(signal.magnitude_hint), self.config.max_adjustment_pct)
        else:
            base_impact = self.config.signal_type_base_impact.get(signal.signal_type, 0.10)
            adjustment_pct = base_impact * combined_confidence

        # Cap based on confidence level
        max_pct = (self.config.max_adjustment_pct
                   if combined_confidence >= self.config.high_confidence_threshold
                   else self.config.max_adjustment_pct_low_confidence)
        adjustment_pct = min(adjustment_pct, max_pct)

        # Step 6: Calculate adjusted value
        sign = 1.0 if direction == AdjustmentDirection.UP else -1.0
        adjustment_magnitude = signal.current_forecast_value * adjustment_pct * sign
        adjusted_value = max(0, signal.current_forecast_value + adjustment_magnitude)

        # Step 7: Determine if auto-applicable or needs review
        auto_applicable = combined_confidence >= self.config.high_confidence_threshold
        requires_review = not auto_applicable

        return ForecastAdjustmentResult(
            signal_id=signal.signal_id,
            product_id=signal.product_id,
            site_id=signal.site_id,
            should_adjust=True,
            direction=direction,
            adjustment_magnitude=abs(adjustment_magnitude),
            adjustment_pct=adjustment_pct,
            adjusted_forecast_value=adjusted_value,
            signal_confidence=signal.signal_confidence,
            source_reliability=source_reliability,
            combined_confidence=combined_confidence,
            time_horizon_periods=signal.time_horizon_periods,
            # TODO(virtual-clock): thread tenant_id + sync db into engine to use
            # tenant_today_sync instead of date.today() for demo reproducibility.
            effective_date=signal.effective_date or date.today(),
            current_forecast=signal.current_forecast_value,
            forecast_change=adjustment_magnitude,
            requires_human_review=requires_review,
            auto_applicable=auto_applicable,
            explanation=(
                f"{'Auto-apply' if auto_applicable else 'Review needed'}: "
                f"{direction.value} {adjustment_pct:.0%} "
                f"(source={signal.source}, confidence={combined_confidence:.2f})"
            )
        )

    def evaluate_batch(self, signals: List[ForecastSignal]) -> List[ForecastAdjustmentResult]:
        """Evaluate a batch of forecast signals."""
        return [self.evaluate_signal(s) for s in signals]

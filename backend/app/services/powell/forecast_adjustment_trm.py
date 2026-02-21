"""
Forecast Adjustment TRM

Narrow TRM for processing external signals into forecast adjustments.

TRM Scope (narrow):
- Given: External signal (email, voice, market intel), current forecast, historical accuracy
- Decide: Adjust forecast? By how much? What confidence?

Learns from historical signal accuracy: which sources and signal types
actually improved forecast accuracy vs which were noise.

Signal sources include:
- Email (parsed by NLP)
- Voice input (transcribed)
- Market intelligence feeds
- Customer feedback
- Sales team input
- News/events
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date
import numpy as np
import logging

from .engines.forecast_adjustment_engine import (
    ForecastAdjustmentEngine, ForecastAdjustmentConfig,
    ForecastSignal, ForecastAdjustmentResult, AdjustmentDirection,
)

logger = logging.getLogger(__name__)


@dataclass
class ForecastAdjustmentState:
    """State representation for forecast adjustment TRM"""
    signal_id: str
    product_id: str
    site_id: str

    # Signal details
    source: str
    signal_type: str
    signal_text: str
    signal_confidence: float
    direction: str  # up, down, no_change
    magnitude_hint: Optional[float] = None

    # Time context
    time_horizon_periods: int = 4
    signal_timestamp: Optional[datetime] = None
    effective_date: Optional[date] = None

    # Current forecast
    current_forecast_value: float = 0.0
    current_forecast_confidence: float = 0.0

    # Historical accuracy
    historical_forecast_accuracy: float = 0.0
    source_historical_accuracy: float = 0.0  # How accurate this source has been
    signal_type_historical_accuracy: float = 0.0  # How accurate this signal type has been

    # Product context
    product_volatility: float = 0.0  # CV of demand
    product_trend: float = 0.0  # Positive = growing, negative = declining
    seasonality_factor: float = 1.0  # Current seasonal index

    # Inventory context
    current_inventory_dos: float = 0.0
    pending_orders: float = 0.0


@dataclass
class ForecastAdjustmentRecommendation:
    """TRM recommendation for forecast adjustment"""
    signal_id: str
    product_id: str
    site_id: str

    should_adjust: bool = False
    direction: str = "no_change"
    adjustment_pct: float = 0.0
    adjustment_magnitude: float = 0.0
    adjusted_forecast_value: float = 0.0

    confidence: float = 0.0
    auto_applicable: bool = False
    requires_human_review: bool = True

    time_horizon_periods: int = 0
    effective_date: Optional[date] = None

    reason: str = ""


@dataclass
class ForecastAdjustmentTRMConfig:
    engine_config: ForecastAdjustmentConfig = field(default_factory=ForecastAdjustmentConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7
    # Learned source reliability overrides
    learned_source_reliability: Dict[str, float] = field(default_factory=dict)


class ForecastAdjustmentTRM:
    """
    Forecast Adjustment TRM.

    Wraps the deterministic ForecastAdjustmentEngine with learned
    signal reliability assessment.
    """

    def __init__(self, site_key, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config or ForecastAdjustmentTRMConfig()
        self.engine = ForecastAdjustmentEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session

    def evaluate_signal(self, state: ForecastAdjustmentState) -> ForecastAdjustmentRecommendation:
        """Evaluate a forecast signal and recommend adjustment."""
        signal = ForecastSignal(
            signal_id=state.signal_id,
            product_id=state.product_id,
            site_id=state.site_id,
            source=state.source,
            signal_type=state.signal_type,
            signal_text=state.signal_text,
            signal_confidence=state.signal_confidence,
            direction=state.direction,
            magnitude_hint=state.magnitude_hint,
            time_horizon_periods=state.time_horizon_periods,
            signal_timestamp=state.signal_timestamp,
            effective_date=state.effective_date,
            current_forecast_value=state.current_forecast_value,
            current_forecast_confidence=state.current_forecast_confidence,
            historical_accuracy_pct=state.historical_forecast_accuracy,
        )

        engine_result = self.engine.evaluate_signal(signal)

        if self.model is not None and self.config.use_trm_model:
            try:
                rec = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM failed for signal {state.signal_id}: {e}")
                rec = self._heuristic_evaluate(state, engine_result)
        else:
            rec = self._heuristic_evaluate(state, engine_result)

        self._persist_decision(state, rec)
        return rec

    def _trm_evaluate(self, state, engine_result):
        features = self._encode_state(state)
        import torch
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))

        confidence = float(output.get('confidence', 0.5))
        if confidence < self.config.confidence_threshold:
            return self._heuristic_evaluate(state, engine_result)

        # TRM may adjust the magnitude based on learned patterns
        adj_pct = engine_result.adjustment_pct
        if 'adjustment_scale' in output:
            scale = float(output['adjustment_scale'].item())
            adj_pct = adj_pct * max(0.5, min(2.0, scale))

        sign = 1.0 if engine_result.direction == AdjustmentDirection.UP else -1.0
        magnitude = state.current_forecast_value * adj_pct * sign
        adjusted = max(0, state.current_forecast_value + magnitude)

        return ForecastAdjustmentRecommendation(
            signal_id=state.signal_id,
            product_id=state.product_id,
            site_id=state.site_id,
            should_adjust=engine_result.should_adjust,
            direction=engine_result.direction.value if engine_result.direction != AdjustmentDirection.NO_CHANGE else "no_change",
            adjustment_pct=adj_pct,
            adjustment_magnitude=abs(magnitude),
            adjusted_forecast_value=adjusted,
            confidence=confidence,
            auto_applicable=confidence >= 0.8,
            requires_human_review=confidence < 0.8,
            time_horizon_periods=state.time_horizon_periods,
            effective_date=state.effective_date or date.today(),
            reason=f"TRM: {engine_result.explanation}",
        )

    def _heuristic_evaluate(self, state, engine_result):
        """Heuristic with learned source reliability."""
        should_adjust = engine_result.should_adjust
        adj_pct = engine_result.adjustment_pct

        # Override 1: Use learned source reliability if available
        learned_reliability = self.config.learned_source_reliability.get(state.source)
        if learned_reliability is not None:
            # Scale adjustment by learned reliability
            adj_pct *= learned_reliability

        # Override 2: If source historical accuracy is poor, dampen
        if state.source_historical_accuracy < 0.5 and state.source_historical_accuracy > 0:
            adj_pct *= state.source_historical_accuracy

        # Override 3: High volatility products need larger signals to act on
        if state.product_volatility > 0.5 and adj_pct < 0.10:
            should_adjust = False

        # Override 4: Consider current trend alignment
        if state.direction == "up" and state.product_trend < -0.1:
            # Signal says up but trend is down - reduce confidence
            adj_pct *= 0.7
        elif state.direction == "down" and state.product_trend > 0.1:
            adj_pct *= 0.7

        sign = 1.0 if state.direction == "up" else (-1.0 if state.direction == "down" else 0.0)
        magnitude = state.current_forecast_value * adj_pct * sign
        adjusted = max(0, state.current_forecast_value + magnitude)

        return ForecastAdjustmentRecommendation(
            signal_id=state.signal_id,
            product_id=state.product_id,
            site_id=state.site_id,
            should_adjust=should_adjust,
            direction=state.direction,
            adjustment_pct=adj_pct,
            adjustment_magnitude=abs(magnitude),
            adjusted_forecast_value=adjusted,
            confidence=0.5,
            auto_applicable=False,
            requires_human_review=True,
            time_horizon_periods=state.time_horizon_periods,
            effective_date=state.effective_date or date.today(),
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state):
        source_map = {
            "email": 0.1, "voice": 0.2, "market_intelligence": 0.3,
            "news": 0.4, "customer_feedback": 0.5, "sales_input": 0.6,
            "weather": 0.7, "economic_indicator": 0.8, "social_media": 0.9,
            "competitor_action": 1.0,
        }
        direction_map = {"up": 1.0, "down": -1.0, "no_change": 0.0}
        return [
            source_map.get(state.source, 0.5),
            direction_map.get(state.direction, 0.0),
            state.signal_confidence,
            state.magnitude_hint or 0.0,
            state.current_forecast_value / 10000.0,
            state.current_forecast_confidence,
            state.historical_forecast_accuracy,
            state.source_historical_accuracy,
            state.signal_type_historical_accuracy,
            state.product_volatility,
            state.product_trend,
            state.seasonality_factor,
            state.current_inventory_dos / 30.0,
            state.pending_orders / 1000.0,
            state.time_horizon_periods / 12.0,
        ]

    def _persist_decision(self, state, rec):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellForecastAdjustmentDecision
            d = PowellForecastAdjustmentDecision(
                config_id=0,
                product_id=state.product_id,
                site_id=state.site_id,
                signal_source=state.source,
                signal_type=state.signal_type,
                signal_text=state.signal_text[:500] if state.signal_text else None,
                signal_confidence=state.signal_confidence,
                current_forecast_value=state.current_forecast_value,
                adjustment_direction=rec.direction,
                adjustment_magnitude=rec.adjustment_magnitude,
                adjustment_pct=rec.adjustment_pct,
                adjusted_forecast_value=rec.adjusted_forecast_value,
                time_horizon_periods=rec.time_horizon_periods,
                reason=rec.reason[:200] if rec.reason else None,
                confidence=rec.confidence,
                state_features={
                    'source_accuracy': state.source_historical_accuracy,
                    'product_volatility': state.product_volatility,
                    'trend': state.product_trend,
                },
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist forecast adjustment decision: {e}")

    def record_outcome(self, signal_id, actual_demand=None,
                       forecast_error_before=None, forecast_error_after=None,
                       was_applied=True):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellForecastAdjustmentDecision
            d = (self.db.query(PowellForecastAdjustmentDecision)
                 .filter(PowellForecastAdjustmentDecision.signal_source == signal_id)  # Use signal_id to find
                 .order_by(PowellForecastAdjustmentDecision.created_at.desc()).first())
            if d:
                d.was_applied = was_applied
                d.actual_demand = actual_demand
                d.forecast_error_before = forecast_error_before
                d.forecast_error_after = forecast_error_after
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record forecast adjustment outcome: {e}")

    def get_training_data(self, config_id, limit=1000):
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellForecastAdjustmentDecision
            return [d.to_dict() for d in self.db.query(PowellForecastAdjustmentDecision)
                    .filter(PowellForecastAdjustmentDecision.config_id == config_id,
                            PowellForecastAdjustmentDecision.was_applied.isnot(None))
                    .order_by(PowellForecastAdjustmentDecision.created_at.desc()).limit(limit).all()]
        except Exception as e:
            logger.warning(f"Failed to get forecast adjustment training data: {e}")
            return []

    def evaluate_batch(self, states):
        return [self.evaluate_signal(s) for s in states]

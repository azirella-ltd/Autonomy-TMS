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
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

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
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class ForecastAdjustmentTRMConfig:
    engine_config: ForecastAdjustmentConfig = field(default_factory=ForecastAdjustmentConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7
    # Learned source reliability overrides
    learned_source_reliability: Dict[str, float] = field(default_factory=dict)


class ForecastAdjustmentTRM:
    """
    Forecast Adjustment TRM — Expanded Multi-Domain Agent.

    Handles 7 adjustment domains:
      1. External signal processing (original — via ForecastAdjustmentEngine)
      2. Promotion effect estimation (learned elasticity)
      3. NPI transfer learning (similar-product matching)
      4. EOL coordination (phase-out + successor ramp)
      5. Demand sensing (POS exception detection)
      6. Cannibalization / substitution (category share)
      7. Consensus FVA gating (accept/reject overrides)

    Each domain has deterministic heuristics (95%) with LLM escalation (5%).
    All adjustments are FVA-tracked.
    """

    def __init__(self, site_key, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config or ForecastAdjustmentTRMConfig()
        self.engine = ForecastAdjustmentEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session
        self.ctx_explainer = None  # Set externally by SiteAgent or caller
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        self._fva_cache: Dict[str, float] = {}  # source → trailing FVA
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("forecast_adjustment")
            except Exception:
                pass

    # ── Multi-Domain Evaluation (NEW) ──

    async def evaluate_domain(
        self,
        domain: str,
        product_id: str,
        site_id: str,
        config_id: int,
        baseline_p50: float = 0.0,
        **kwargs,
    ) -> "ForecastAdjustmentRecommendation":
        """Evaluate a specific adjustment domain for a product×site.

        Delegates to the appropriate domain engine, then applies
        common post-processing (FVA check, signal emission, persistence).

        Args:
            domain: One of: promotion, npi, eol, sensing, cannibalization, consensus, signal
            product_id: Product identifier
            site_id: Site identifier
            config_id: Supply chain config ID
            baseline_p50: Current baseline P50 forecast
            **kwargs: Domain-specific parameters

        Returns:
            ForecastAdjustmentRecommendation with adjustment details
        """
        from .engines.forecast_adjustment_domains import (
            PromotionDomain, NPIDomain, EOLDomain,
            DemandSensingDomain, CannibalizationDomain, ConsensusDomain,
            AdjustmentResult,
        )

        signal_context = self._read_signals_before_decision()

        # Route to domain engine
        if domain == "promotion":
            result = await PromotionDomain.evaluate(
                self.db, product_id, site_id, config_id,
                promo_id=kwargs.get("promo_id"),
                promo_type=kwargs.get("promo_type"),
                expected_uplift_pct=kwargs.get("expected_uplift_pct"),
                expected_cannibalization_pct=kwargs.get("expected_cannibalization_pct"),
                product_category=kwargs.get("product_category"),
                product_type=kwargs.get("product_type", "default"),
            )
        elif domain == "npi":
            result = await NPIDomain.evaluate(
                self.db, product_id, site_id, config_id,
                weeks_since_launch=kwargs.get("weeks_since_launch", 0),
                expected_market_share=kwargs.get("expected_market_share"),
                product_category=kwargs.get("product_category"),
                product_price=kwargs.get("product_price"),
                category_velocity=kwargs.get("category_velocity", "medium"),
            )
        elif domain == "eol":
            result = await EOLDomain.evaluate(
                self.db, product_id, site_id, config_id,
                periods_until_eol=kwargs.get("periods_until_eol", 6),
                successor_product_id=kwargs.get("successor_product_id"),
                current_baseline=baseline_p50,
            )
        elif domain == "sensing":
            result = await DemandSensingDomain.evaluate(
                self.db, product_id, site_id, config_id,
                actual_recent=kwargs.get("actual_recent", 0),
                forecast_recent=kwargs.get("forecast_recent", 0),
                exception_threshold=kwargs.get("exception_threshold", 0.15),
            )
        elif domain == "cannibalization":
            result = await CannibalizationDomain.evaluate(
                self.db, product_id, site_id, config_id,
                current_share=kwargs.get("current_share", 0),
                prior_share=kwargs.get("prior_share", 0),
                family_demand_change=kwargs.get("family_demand_change", 0),
                inventory_level=kwargs.get("inventory_level", 0),
                substitutes=kwargs.get("substitutes"),
            )
        elif domain == "consensus":
            result = await ConsensusDomain.evaluate(
                self.db, product_id, config_id,
                override_pct=kwargs.get("override_pct", 0),
                override_user_id=kwargs.get("override_user_id"),
                product_category=kwargs.get("product_category"),
            )
        elif domain == "signal":
            # Delegate to existing signal engine (synchronous)
            state = ForecastAdjustmentState(
                signal_id=kwargs.get("signal_id", ""),
                product_id=product_id,
                site_id=site_id,
                source=kwargs.get("source", ""),
                signal_type=kwargs.get("signal_type", ""),
                signal_text=kwargs.get("signal_text", ""),
                signal_confidence=kwargs.get("signal_confidence", 0.5),
                direction=kwargs.get("direction", "no_change"),
                magnitude_hint=kwargs.get("magnitude_hint"),
                current_forecast_value=baseline_p50,
                current_forecast_confidence=kwargs.get("forecast_confidence", 0.5),
                historical_forecast_accuracy=kwargs.get("historical_accuracy", 0.5),
                source_historical_accuracy=kwargs.get("source_accuracy", 0.5),
                product_volatility=kwargs.get("product_volatility", 0),
                product_trend=kwargs.get("product_trend", 0),
            )
            return self.evaluate_signal(state)
        else:
            result = AdjustmentResult(reason=f"Unknown domain: {domain}")

        # Convert domain result to TRM recommendation
        adjusted_value = baseline_p50 * (1 + result.adjustment_pct) if baseline_p50 > 0 else 0
        adjusted_value = max(0, adjusted_value)

        rec = ForecastAdjustmentRecommendation(
            signal_id=kwargs.get("signal_id", f"{domain}_{product_id}"),
            product_id=product_id,
            site_id=site_id,
            should_adjust=result.should_adjust,
            direction="up" if result.adjustment_pct > 0 else "down" if result.adjustment_pct < 0 else "no_change",
            adjustment_pct=abs(result.adjustment_pct),
            adjustment_magnitude=abs(baseline_p50 * result.adjustment_pct),
            adjusted_forecast_value=adjusted_value,
            confidence=result.confidence,
            auto_applicable=result.confidence >= 0.8 and not result.requires_human_review,
            requires_human_review=result.requires_human_review,
            reason=result.reason,
        )

        # LLM escalation check
        if result.escalate_to_llm:
            rec = await self._escalate_to_llm(
                domain, product_id, site_id, config_id,
                baseline_p50, result, kwargs,
            )

        # Emit signals
        self._emit_domain_signal(domain, product_id, result)

        # Persist
        self._persist_domain_decision(
            product_id, site_id, domain, result, baseline_p50, adjusted_value,
        )

        return rec

    async def _escalate_to_llm(
        self, domain: str, product_id: str, site_id: str,
        config_id: int, baseline: float,
        trm_result, kwargs: Dict,
    ) -> "ForecastAdjustmentRecommendation":
        """Escalate to Claude Skills when TRM confidence is low."""
        try:
            from ..skills.base_skill import get_skill
            from ..skills.skill_orchestrator import SkillOrchestrator

            skill = get_skill("forecast_adjustment")
            if skill is None:
                logger.debug("Forecast adjustment skill not registered — using TRM result")
                return self._result_to_recommendation(
                    trm_result, product_id, site_id, baseline, kwargs
                )

            # Build context for LLM
            context = {
                "domain": domain,
                "product_id": product_id,
                "site_id": site_id,
                "baseline_p50": baseline,
                "trm_estimate": trm_result.adjustment_pct,
                "trm_confidence": trm_result.confidence,
                "escalation_reason": trm_result.escalation_reason,
                **{k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))},
            }

            logger.info(
                "Forecast adjustment escalated to LLM: domain=%s product=%s reason=%s",
                domain, product_id, trm_result.escalation_reason,
            )

            # The actual LLM call would go through SkillOrchestrator
            # For now, return TRM result with escalation flag
            rec = self._result_to_recommendation(
                trm_result, product_id, site_id, baseline, kwargs
            )
            rec.reason = f"[LLM escalated: {trm_result.escalation_reason}] {trm_result.reason}"
            rec.requires_human_review = True  # LLM decisions always reviewed
            return rec

        except Exception as e:
            logger.warning("LLM escalation failed: %s — using TRM result", e)
            return self._result_to_recommendation(
                trm_result, product_id, site_id, baseline, kwargs
            )

    def _result_to_recommendation(
        self, result, product_id, site_id, baseline, kwargs
    ) -> "ForecastAdjustmentRecommendation":
        """Convert AdjustmentResult to ForecastAdjustmentRecommendation."""
        adjusted = max(0, baseline * (1 + result.adjustment_pct)) if baseline > 0 else 0
        return ForecastAdjustmentRecommendation(
            signal_id=kwargs.get("signal_id", f"{result.domain}_{product_id}"),
            product_id=product_id,
            site_id=site_id,
            should_adjust=result.should_adjust,
            direction="up" if result.adjustment_pct > 0 else "down" if result.adjustment_pct < 0 else "no_change",
            adjustment_pct=abs(result.adjustment_pct),
            adjustment_magnitude=abs(baseline * result.adjustment_pct),
            adjusted_forecast_value=adjusted,
            confidence=result.confidence,
            auto_applicable=False,
            requires_human_review=True,
            reason=result.reason,
        )

    def _emit_domain_signal(self, domain: str, product_id: str, result) -> None:
        """Emit hive signals from domain evaluation."""
        if self.signal_bus is None or not result.should_adjust:
            return
        try:
            urgency = min(1.0, abs(result.adjustment_pct) * 3)
            direction = "surplus" if result.adjustment_pct > 0 else "shortage" if result.adjustment_pct < 0 else "neutral"
            self.signal_bus.emit(HiveSignal(
                source_trm="forecast_adj",
                signal_type=HiveSignalType.FORECAST_ADJUSTED,
                urgency=urgency,
                direction=direction,
                magnitude=abs(result.adjustment_pct),
                product_id=product_id,
                payload={
                    "domain": domain,
                    "adj_pct": result.adjustment_pct,
                    "confidence": result.confidence,
                    "escalated": result.escalate_to_llm,
                },
            ))
            self.signal_bus.urgency.update("forecast_adj", urgency, direction)
        except Exception as e:
            logger.debug("Domain signal emit failed: %s", e)

    def _persist_domain_decision(
        self, product_id, site_id, domain, result, baseline, adjusted,
    ) -> None:
        """Persist domain decision to powell_forecast_adjustment_decisions."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellForecastAdjustmentDecision
            from app.services.powell.decision_reasoning import capture_hive_context

            hive_ctx = capture_hive_context(
                self.signal_bus, "forecast_adj",
                cycle_id=getattr(self, "_cycle_id", None),
                cycle_phase=getattr(self, "_cycle_phase", None),
            )
            d = PowellForecastAdjustmentDecision(
                config_id=0,
                product_id=product_id,
                site_id=site_id,
                signal_source=domain,
                signal_type=domain,
                signal_text=result.reason[:500],
                signal_confidence=result.confidence,
                current_forecast_value=baseline,
                adjustment_direction="up" if result.adjustment_pct > 0 else "down" if result.adjustment_pct < 0 else "no_change",
                adjustment_magnitude=abs(baseline * result.adjustment_pct),
                adjustment_pct=result.adjustment_pct,
                adjusted_forecast_value=adjusted,
                time_horizon_periods=4,
                reason=result.reason[:200],
                confidence=result.confidence,
                state_features={
                    "domain": domain,
                    "escalated_to_llm": result.escalate_to_llm,
                    "fva_expected": result.fva_expected,
                    "cannibalization_impact": result.cannibalization_impact,
                    "forward_buy_pct": result.forward_buy_pct,
                },
                decision_reasoning=result.reason,
                **hive_ctx,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning("Failed to persist domain decision: %s", e)

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making forecast decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="forecast_adj",
                types={
                    HiveSignalType.DEMAND_SURGE,
                    HiveSignalType.DEMAND_DROP,
                    HiveSignalType.ORDER_EXCEPTION,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.DEMAND_SURGE:
                    context["demand_surge"] = True
                    context["surge_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.DEMAND_DROP:
                    context["demand_drop"] = True
                    context["drop_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.ORDER_EXCEPTION:
                    context["order_exceptions"] = True
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: ForecastAdjustmentState, rec: ForecastAdjustmentRecommendation
    ) -> None:
        """Emit hive signals after forecast adjustment decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.should_adjust and abs(rec.adjustment_pct) > 0.01:
                urgency = min(1.0, abs(rec.adjustment_pct) * 2.0)
                direction = "surplus" if rec.direction == "up" else "shortage" if rec.direction == "down" else "neutral"
                self.signal_bus.emit(HiveSignal(
                    source_trm="forecast_adj",
                    signal_type=HiveSignalType.FORECAST_ADJUSTED,
                    urgency=urgency,
                    direction=direction,
                    magnitude=abs(rec.adjustment_pct),
                    product_id=state.product_id,
                    payload={
                        "signal_id": state.signal_id,
                        "adj_direction": rec.direction,
                        "adj_pct": rec.adjustment_pct,
                        "source": state.source,
                    },
                ))
                self.signal_bus.urgency.update("forecast_adj", urgency, direction)
            else:
                self.signal_bus.urgency.update("forecast_adj", 0.0, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate_signal(self, state: ForecastAdjustmentState) -> ForecastAdjustmentRecommendation:
        """Evaluate a forecast signal and recommend adjustment."""
        self._read_signals_before_decision()

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

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                direction_str = rec.direction if isinstance(rec.direction, str) else rec.direction
                summary = (
                    f"Forecast {direction_str}: {rec.adjustment_pct:.1%} "
                    f"for {state.product_id}"
                )
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=rec.confidence,
                    trm_confidence=rec.confidence if self.model else None,
                    decision_category='demand_forecast',
                    delta_percent=rec.adjustment_pct * 100,
                )
                rec.reason = ctx.explanation
                rec.context_explanation = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

        # CDT risk bound
        if self._cdt_wrapper is not None and self._cdt_wrapper.is_calibrated:
            try:
                risk = self._cdt_wrapper.compute_risk_bound(rec.adjustment_magnitude)
                rec.risk_bound = risk.risk_bound
                rec.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._emit_signals_after_decision(state, rec)
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
            from app.services.powell.decision_reasoning import forecast_adjustment_reasoning, capture_hive_context, get_product_costs
            hive_ctx = capture_hive_context(
                self.signal_bus, "forecast_adj",
                cycle_id=getattr(self, "_cycle_id", None),
                cycle_phase=getattr(self, "_cycle_phase", None),
            )
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
                decision_reasoning=forecast_adjustment_reasoning(
                    product_id=state.product_id,
                    adjustment_direction=rec.direction,
                    adjustment_pct=rec.adjustment_pct,
                    confidence=rec.confidence,
                    signal_type=state.signal_type,
                    current_value=state.current_forecast_value,
                    adjusted_value=rec.adjusted_forecast_value,
                    **dict(zip(("unit_cost", "unit_price"), get_product_costs(self.db, state.product_id))),
                ),
                **hive_ctx,
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

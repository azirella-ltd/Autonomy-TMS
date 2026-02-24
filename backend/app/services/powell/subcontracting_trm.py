"""
Subcontracting TRM

Narrow TRM for make-vs-buy/subcontracting routing decisions.

TRM Scope (narrow):
- Given: Capacity, cost, quality scores, lead times, IP sensitivity
- Decide: Route external, keep internal, split, or change vendor?

Learns vendor reliability patterns from historical outcomes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
import numpy as np
import logging

from .engines.subcontracting_engine import (
    SubcontractingEngine, SubcontractingEngineConfig,
    SubcontractSnapshot, SubcontractingResult, SubcontractDecisionType,
)
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SubcontractingState:
    """State representation for subcontracting TRM"""
    product_id: str
    site_id: str
    required_quantity: float
    required_by_date: Optional[date] = None

    # Internal capability
    internal_capacity_pct: float = 0.0
    internal_cost_per_unit: float = 0.0
    internal_lead_time_days: int = 0
    internal_quality_yield_pct: float = 0.99

    # Subcontractor
    subcontractor_id: Optional[str] = None
    subcontractor_cost_per_unit: float = 0.0
    subcontractor_lead_time_days: int = 0
    subcontractor_quality_score: float = 0.0
    subcontractor_on_time_score: float = 0.0
    subcontractor_capacity_available: float = 0.0

    # Context
    is_critical_product: bool = False
    has_special_tooling: bool = False
    ip_sensitivity: str = "low"
    current_external_pct: float = 0.0

    # Historical
    vendor_historical_reject_rate: float = 0.0
    vendor_historical_late_rate: float = 0.0
    internal_capacity_trend: float = 0.0  # positive = improving

    # Demand
    demand_forecast: float = 0.0
    backlog_quantity: float = 0.0


@dataclass
class SubcontractingRecommendation:
    order_id: str  # Product-site key
    decision_type: str
    confidence: float

    internal_quantity: float = 0.0
    external_quantity: float = 0.0
    recommended_vendor: Optional[str] = None

    internal_cost: float = 0.0
    external_cost: float = 0.0
    total_cost: float = 0.0
    cost_savings: float = 0.0

    quality_risk: float = 0.0
    delivery_risk: float = 0.0
    estimated_completion_date: Optional[date] = None

    reason: str = ""
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class SubcontractingTRMConfig:
    engine_config: SubcontractingEngineConfig = field(default_factory=SubcontractingEngineConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7


class SubcontractingTRM:
    """Subcontracting TRM with learned vendor reliability assessment."""

    def __init__(self, site_key, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config or SubcontractingTRMConfig()
        self.engine = SubcontractingEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session
        self.ctx_explainer = None  # Set externally by SiteAgent or caller
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("subcontracting")
            except Exception:
                pass

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making subcontracting decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="subcontracting",
                types={
                    HiveSignalType.MO_DELAYED,
                    HiveSignalType.QUALITY_REJECT,
                    HiveSignalType.ATP_SHORTAGE,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.MO_DELAYED:
                    context["mo_delayed"] = True
                    context["mo_delay_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.QUALITY_REJECT:
                    context["quality_reject"] = True
                elif s.signal_type == HiveSignalType.ATP_SHORTAGE:
                    context["atp_shortage"] = True
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: SubcontractingState, rec: SubcontractingRecommendation
    ) -> None:
        """Emit hive signals after subcontracting decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.decision_type in ("route_external", "split"):
                urgency = min(1.0, 0.3 + rec.delivery_risk * 0.5)
                self.signal_bus.emit(HiveSignal(
                    source_trm="subcontracting",
                    signal_type=HiveSignalType.SUBCONTRACT_ROUTED,
                    urgency=urgency,
                    direction="relief" if rec.delivery_risk < 0.3 else "risk",
                    magnitude=rec.external_quantity / max(1, state.required_quantity),
                    product_id=state.product_id,
                    payload={
                        "vendor": rec.recommended_vendor,
                        "external_qty": rec.external_quantity,
                        "internal_qty": rec.internal_quantity,
                    },
                ))
                self.signal_bus.urgency.update("subcontracting", urgency, "relief" if rec.delivery_risk < 0.3 else "risk")
            else:
                self.signal_bus.urgency.update("subcontracting", 0.1, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate_routing(self, state: SubcontractingState) -> SubcontractingRecommendation:
        self._read_signals_before_decision()

        snapshot = SubcontractSnapshot(
            product_id=state.product_id,
            site_id=state.site_id,
            required_quantity=state.required_quantity,
            required_by_date=state.required_by_date,
            internal_capacity_pct=state.internal_capacity_pct,
            internal_cost_per_unit=state.internal_cost_per_unit,
            internal_lead_time_days=state.internal_lead_time_days,
            internal_quality_yield_pct=state.internal_quality_yield_pct,
            subcontractor_id=state.subcontractor_id,
            subcontractor_cost_per_unit=state.subcontractor_cost_per_unit,
            subcontractor_lead_time_days=state.subcontractor_lead_time_days,
            subcontractor_quality_score=state.subcontractor_quality_score,
            subcontractor_on_time_score=state.subcontractor_on_time_score,
            subcontractor_capacity_available=state.subcontractor_capacity_available,
            is_critical_product=state.is_critical_product,
            has_special_tooling=state.has_special_tooling,
            ip_sensitivity=state.ip_sensitivity,
            current_external_pct=state.current_external_pct,
            demand_forecast_next_30_days=state.demand_forecast,
            backlog_quantity=state.backlog_quantity,
        )

        engine_result = self.engine.evaluate_routing(snapshot)

        if self.model is not None and self.config.use_trm_model:
            try:
                rec = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM failed for subcontracting {state.product_id}: {e}")
                rec = self._heuristic_evaluate(state, engine_result)
        else:
            rec = self._heuristic_evaluate(state, engine_result)

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = f"{rec.decision_type}: {state.product_id} at {state.site_id}"
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=rec.confidence,
                    trm_confidence=rec.confidence if self.model else None,
                    decision_value=rec.total_cost,
                )
                rec.reason = ctx.explanation
                rec.context_explanation = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

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

        return SubcontractingRecommendation(
            order_id=f"{state.product_id}_{state.site_id}",
            decision_type=engine_result.decision_type.value,
            confidence=confidence,
            internal_quantity=engine_result.internal_quantity,
            external_quantity=engine_result.external_quantity,
            recommended_vendor=engine_result.recommended_vendor,
            internal_cost=engine_result.internal_cost,
            external_cost=engine_result.external_cost,
            total_cost=engine_result.total_cost,
            cost_savings=engine_result.cost_savings,
            quality_risk=engine_result.quality_risk,
            delivery_risk=engine_result.delivery_risk,
            reason=f"TRM: {engine_result.explanation}",
        )

    def _heuristic_evaluate(self, state, engine_result):
        decision_type = engine_result.decision_type.value

        # Heuristic: If vendor has high reject/late rate, avoid
        if (state.vendor_historical_reject_rate > 0.10 or
                state.vendor_historical_late_rate > 0.20):
            if decision_type in ("route_external", "split"):
                decision_type = "keep_internal"

        # Heuristic: If critical product and vendor quality mediocre, keep internal
        if state.is_critical_product and state.subcontractor_quality_score < 0.92:
            decision_type = "keep_internal"

        return SubcontractingRecommendation(
            order_id=f"{state.product_id}_{state.site_id}",
            decision_type=decision_type,
            confidence=0.6,
            internal_quantity=engine_result.internal_quantity if decision_type != "route_external" else state.required_quantity,
            external_quantity=engine_result.external_quantity if decision_type != "keep_internal" else 0,
            recommended_vendor=engine_result.recommended_vendor,
            internal_cost=engine_result.internal_cost,
            external_cost=engine_result.external_cost,
            total_cost=engine_result.total_cost,
            cost_savings=engine_result.cost_savings,
            quality_risk=engine_result.quality_risk,
            delivery_risk=engine_result.delivery_risk,
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state):
        return [
            state.required_quantity / 1000.0,
            state.internal_capacity_pct / 100.0,
            state.internal_cost_per_unit / 100.0,
            state.internal_lead_time_days / 30.0,
            state.internal_quality_yield_pct,
            state.subcontractor_cost_per_unit / 100.0 if state.subcontractor_id else 0,
            state.subcontractor_lead_time_days / 30.0 if state.subcontractor_id else 0,
            state.subcontractor_quality_score,
            state.subcontractor_on_time_score,
            1.0 if state.is_critical_product else 0.0,
            1.0 if state.has_special_tooling else 0.0,
            {"low": 0.2, "medium": 0.5, "high": 1.0}.get(state.ip_sensitivity, 0.2),
            state.current_external_pct,
            state.vendor_historical_reject_rate,
            state.vendor_historical_late_rate,
            state.demand_forecast / 1000.0,
            state.backlog_quantity / 500.0,
        ]

    def _persist_decision(self, state, rec):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellSubcontractingDecision
            d = PowellSubcontractingDecision(
                config_id=0,
                product_id=state.product_id,
                site_id=state.site_id,
                subcontractor_id=state.subcontractor_id or "",
                planned_qty=state.required_quantity,
                decision_type=rec.decision_type,
                reason=rec.reason[:50] if rec.reason else "",
                internal_capacity_pct=state.internal_capacity_pct,
                subcontractor_lead_time_days=state.subcontractor_lead_time_days,
                subcontractor_cost_per_unit=state.subcontractor_cost_per_unit,
                internal_cost_per_unit=state.internal_cost_per_unit,
                quality_score=state.subcontractor_quality_score,
                on_time_score=state.subcontractor_on_time_score,
                confidence=rec.confidence,
                state_features={'ip': state.ip_sensitivity, 'critical': state.is_critical_product},
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist subcontracting decision: {e}")

    def record_outcome(self, product_id, site_id, actual_qty=None, actual_cost=None,
                       actual_lead_time_days=None, quality_passed=None, was_executed=True):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellSubcontractingDecision
            d = (self.db.query(PowellSubcontractingDecision)
                 .filter(PowellSubcontractingDecision.product_id == product_id,
                         PowellSubcontractingDecision.site_id == site_id)
                 .order_by(PowellSubcontractingDecision.created_at.desc()).first())
            if d:
                d.was_executed = was_executed
                d.actual_qty = actual_qty
                d.actual_cost = actual_cost
                d.actual_lead_time_days = actual_lead_time_days
                d.quality_passed = quality_passed
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record subcontracting outcome: {e}")

    def get_training_data(self, config_id, limit=1000):
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellSubcontractingDecision
            return [d.to_dict() for d in self.db.query(PowellSubcontractingDecision)
                    .filter(PowellSubcontractingDecision.config_id == config_id,
                            PowellSubcontractingDecision.was_executed.isnot(None))
                    .order_by(PowellSubcontractingDecision.created_at.desc()).limit(limit).all()]
        except Exception as e:
            logger.warning(f"Failed to get subcontracting training data: {e}")
            return []

    def evaluate_batch(self, states):
        return [self.evaluate_routing(s) for s in states]

"""
Quality Disposition TRM

Narrow TRM for quality inspection disposition decisions.

TRM Scope (narrow):
- Given: Inspection results, defect data, inventory context, vendor history
- Decide: Accept, reject, rework, scrap, use-as-is, or return to vendor?

Learns from historical disposition outcomes (e.g., which use-as-is
decisions led to customer complaints vs which were fine).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date
import numpy as np
import logging

from .engines.quality_engine import (
    QualityEngine, QualityEngineConfig, QualitySnapshot, QualityDispositionResult,
    DispositionType,
)
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class QualityDispositionState:
    """State representation for quality disposition TRM"""
    quality_order_id: str
    product_id: str
    site_id: str
    inspection_type: str

    # Inspection results
    inspection_quantity: float
    defect_count: int
    defect_rate: float
    defect_category: str
    severity_level: str  # minor, major, critical
    characteristics_tested: int
    characteristics_passed: int

    # Cost context
    product_unit_value: float
    estimated_rework_cost: float
    estimated_scrap_cost: float

    # Vendor context
    vendor_id: Optional[str] = None
    vendor_quality_score: float = 0.0
    vendor_recent_reject_rate: float = 0.0
    days_since_receipt: int = 0

    # Inventory context
    inventory_on_hand: float = 0.0
    safety_stock: float = 0.0
    days_of_supply: float = 0.0
    pending_customer_orders: float = 0.0

    # Historical context
    product_historical_defect_rate: float = 0.0
    product_rework_success_rate: float = 0.90
    similar_use_as_is_complaint_rate: float = 0.0

    # Lot
    lot_number: Optional[str] = None
    lot_size: float = 0.0


@dataclass
class QualityRecommendation:
    """TRM recommendation for quality disposition"""
    quality_order_id: str
    disposition: str  # accept, reject, rework, scrap, use_as_is, return_to_vendor
    confidence: float

    # Quantities
    accept_qty: float = 0.0
    reject_qty: float = 0.0
    rework_qty: float = 0.0
    scrap_qty: float = 0.0
    use_as_is_qty: float = 0.0

    # Cost impact
    rework_cost: float = 0.0
    scrap_cost: float = 0.0
    service_risk: float = 0.0

    # Vendor action
    return_to_vendor: bool = False
    vendor_notification: bool = False

    reason: str = ""
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class QualityDispositionTRMConfig:
    """Configuration for QualityDispositionTRM"""
    engine_config: QualityEngineConfig = field(default_factory=QualityEngineConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7


class QualityDispositionTRM:
    """
    Quality Disposition TRM.

    Wraps the deterministic QualityEngine with learned adjustments.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[QualityDispositionTRMConfig] = None,
        model: Optional[Any] = None,
        db_session: Optional[Any] = None,
    ):
        self.site_key = site_key
        self.config = config or QualityDispositionTRMConfig()
        self.engine = QualityEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session
        self.ctx_explainer = None  # Set externally by SiteAgent or caller
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("quality_disposition")
            except Exception:
                pass

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making quality decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="quality",
                types={
                    HiveSignalType.MO_RELEASED,
                    HiveSignalType.MO_DELAYED,
                    HiveSignalType.ATP_SHORTAGE,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.MO_RELEASED:
                    context["mo_released_active"] = True
                elif s.signal_type == HiveSignalType.ATP_SHORTAGE:
                    context["atp_shortage"] = True
                    context["atp_shortage_urgency"] = s.current_strength
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: QualityDispositionState, rec: QualityRecommendation
    ) -> None:
        """Emit hive signals after quality decision."""
        if self.signal_bus is None:
            return
        try:
            severity_urgency = {"minor": 0.3, "major": 0.6, "critical": 0.9}
            urgency = severity_urgency.get(state.severity_level, 0.5)

            if rec.disposition in ("reject", "scrap", "return_to_vendor"):
                self.signal_bus.emit(HiveSignal(
                    source_trm="quality",
                    signal_type=HiveSignalType.QUALITY_REJECT,
                    urgency=urgency,
                    direction="risk",
                    magnitude=rec.reject_qty / max(1, state.inspection_quantity),
                    product_id=state.product_id,
                    payload={
                        "quality_order_id": state.quality_order_id,
                        "disposition": rec.disposition,
                        "qty": rec.reject_qty + rec.scrap_qty,
                    },
                ))
                self.signal_bus.urgency.update("quality", urgency, "risk")
            elif rec.disposition == "rework":
                self.signal_bus.emit(HiveSignal(
                    source_trm="quality",
                    signal_type=HiveSignalType.QUALITY_HOLD,
                    urgency=urgency * 0.7,
                    direction="risk",
                    magnitude=rec.rework_qty / max(1, state.inspection_quantity),
                    product_id=state.product_id,
                    payload={
                        "quality_order_id": state.quality_order_id,
                        "rework_qty": rec.rework_qty,
                    },
                ))
                self.signal_bus.urgency.update("quality", urgency * 0.7, "risk")
            else:
                self.signal_bus.urgency.update("quality", 0.1, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate_disposition(self, state: QualityDispositionState) -> QualityRecommendation:
        """Evaluate quality inspection and recommend disposition."""
        self._read_signals_before_decision()

        snapshot = QualitySnapshot(
            quality_order_id=state.quality_order_id,
            product_id=state.product_id,
            site_id=state.site_id,
            inspection_type=state.inspection_type,
            inspection_quantity=state.inspection_quantity,
            defect_count=state.defect_count,
            defect_rate=state.defect_rate,
            defect_category=state.defect_category,
            severity_level=state.severity_level,
            characteristics_tested=state.characteristics_tested,
            characteristics_passed=state.characteristics_passed,
            product_unit_value=state.product_unit_value,
            estimated_rework_cost=state.estimated_rework_cost,
            estimated_scrap_cost=state.estimated_scrap_cost,
            vendor_id=state.vendor_id,
            vendor_quality_score=state.vendor_quality_score,
            days_since_receipt=state.days_since_receipt,
            inventory_on_hand=state.inventory_on_hand,
            safety_stock=state.safety_stock,
            days_of_supply=state.days_of_supply,
            pending_customer_orders=state.pending_customer_orders,
            lot_number=state.lot_number,
            lot_size=state.lot_size,
        )

        engine_result = self.engine.evaluate_disposition(snapshot)

        # Note: Glenday Sieve skip-lot logic for Green runners is enforced
        # by the governance gate, not inline. The TRM generates the best
        # disposition; governance may override to "accept" for green runners
        # with minor defects.

        if self.model is not None and self.config.use_trm_model:
            try:
                recommendation = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM evaluation failed for QO {state.quality_order_id}: {e}")
                recommendation = self._heuristic_evaluate(state, engine_result)
        else:
            recommendation = self._heuristic_evaluate(state, engine_result)

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = f"{recommendation.disposition}: QO {state.quality_order_id}"
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=recommendation.confidence,
                    trm_confidence=recommendation.confidence if self.model else None,
                )
                recommendation.reason = ctx.explanation
                recommendation.context_explanation = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

        # CDT risk bound
        if self._cdt_wrapper is not None and self._cdt_wrapper.is_calibrated:
            try:
                cost = recommendation.rework_cost + recommendation.scrap_cost
                risk = self._cdt_wrapper.compute_risk_bound(cost)
                recommendation.risk_bound = risk.risk_bound
                recommendation.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._emit_signals_after_decision(state, recommendation)
        self._persist_decision(state, recommendation)
        return recommendation

    def _trm_evaluate(
        self, state: QualityDispositionState, engine_result: QualityDispositionResult
    ) -> QualityRecommendation:
        """Apply TRM model adjustments."""
        features = self._encode_state(state)
        import torch
        with torch.no_grad():
            state_tensor = torch.tensor([features], dtype=torch.float32)
            output = self.model(state_tensor)

        confidence = float(output.get('confidence', 0.5))
        if confidence < self.config.confidence_threshold:
            return self._heuristic_evaluate(state, engine_result)

        return QualityRecommendation(
            quality_order_id=state.quality_order_id,
            disposition=engine_result.recommended_disposition.value,
            confidence=confidence,
            accept_qty=engine_result.accept_qty,
            reject_qty=engine_result.reject_qty,
            rework_qty=engine_result.rework_qty,
            scrap_qty=engine_result.scrap_qty,
            use_as_is_qty=engine_result.use_as_is_qty,
            rework_cost=engine_result.rework_cost,
            scrap_cost=engine_result.scrap_cost,
            service_risk=engine_result.service_risk_if_rejected,
            return_to_vendor=engine_result.return_to_vendor,
            vendor_notification=engine_result.vendor_notification_needed,
            reason=f"TRM adjusted: {engine_result.explanation}",
        )

    def _heuristic_evaluate(
        self, state: QualityDispositionState, engine_result: QualityDispositionResult
    ) -> QualityRecommendation:
        """Heuristic fallback."""
        disposition = engine_result.recommended_disposition.value

        # Heuristic: If vendor has poor recent quality, reject + return
        if (state.vendor_id and state.vendor_recent_reject_rate > 0.15 and
                state.severity_level != "minor"):
            disposition = "return_to_vendor"

        # Heuristic: If use-as-is has led to complaints historically, avoid it
        if (disposition == "use_as_is" and
                state.similar_use_as_is_complaint_rate > 0.10):
            disposition = "rework" if state.estimated_rework_cost < state.product_unit_value * state.inspection_quantity * 0.3 else "reject"

        # Heuristic: If rework success rate is low, skip rework
        if disposition == "rework" and state.product_rework_success_rate < 0.70:
            disposition = "scrap" if state.defect_rate > 0.10 else "reject"

        return QualityRecommendation(
            quality_order_id=state.quality_order_id,
            disposition=disposition,
            confidence=0.6,
            accept_qty=engine_result.accept_qty,
            reject_qty=engine_result.reject_qty,
            rework_qty=engine_result.rework_qty,
            scrap_qty=engine_result.scrap_qty,
            use_as_is_qty=engine_result.use_as_is_qty,
            rework_cost=engine_result.rework_cost,
            scrap_cost=engine_result.scrap_cost,
            service_risk=engine_result.service_risk_if_rejected,
            return_to_vendor=engine_result.return_to_vendor,
            vendor_notification=engine_result.vendor_notification_needed,
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state: QualityDispositionState) -> List[float]:
        """Encode state for TRM model."""
        severity_map = {"minor": 0.2, "major": 0.6, "critical": 1.0}
        return [
            state.inspection_quantity / 1000.0,
            state.defect_count / 100.0,
            state.defect_rate,
            severity_map.get(state.severity_level, 0.5),
            state.characteristics_passed / max(1, state.characteristics_tested),
            state.product_unit_value / 100.0,
            state.estimated_rework_cost / 10000.0,
            state.estimated_scrap_cost / 10000.0,
            state.vendor_quality_score / 100.0,
            state.vendor_recent_reject_rate,
            state.days_since_receipt / 30.0,
            state.inventory_on_hand / 1000.0,
            state.safety_stock / 500.0,
            state.days_of_supply / 30.0,
            state.pending_customer_orders / 500.0,
            state.product_historical_defect_rate,
            state.product_rework_success_rate,
            state.similar_use_as_is_complaint_rate,
        ]

    def _persist_decision(self, state: QualityDispositionState, rec: QualityRecommendation):
        """Persist decision to powell_quality_decisions table."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellQualityDecision
            from app.services.powell.decision_reasoning import quality_reasoning, capture_hive_context
            hive_ctx = capture_hive_context(
                self.signal_bus, "quality",
                cycle_id=getattr(self, "_cycle_id", None),
                cycle_phase=getattr(self, "_cycle_phase", None),
            )
            decision = PowellQualityDecision(
                config_id=0,
                quality_order_id=state.quality_order_id,
                product_id=state.product_id,
                site_id=state.site_id,
                lot_number=state.lot_number,
                inspection_type=state.inspection_type,
                inspection_qty=state.inspection_quantity,
                defect_rate=state.defect_rate,
                defect_category=state.defect_category,
                severity_level=state.severity_level,
                disposition=rec.disposition,
                disposition_reason=rec.reason,
                rework_cost_estimate=rec.rework_cost,
                scrap_cost_estimate=rec.scrap_cost,
                service_risk_if_accepted=rec.service_risk,
                confidence=rec.confidence,
                state_features={
                    'vendor_quality': state.vendor_quality_score,
                    'inventory_dos': state.days_of_supply,
                    'pending_orders': state.pending_customer_orders,
                },
                decision_reasoning=quality_reasoning(
                    product_id=state.product_id,
                    location_id=state.site_id,
                    disposition=rec.disposition,
                    confidence=rec.confidence,
                    disposition_reason=rec.reason,
                    lot_id=state.lot_number,
                ),
                **hive_ctx,
            )
            self.db.add(decision)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist quality decision: {e}")

    def record_outcome(
        self,
        quality_order_id: str,
        actual_disposition: Optional[str] = None,
        actual_rework_cost: Optional[float] = None,
        actual_scrap_cost: Optional[float] = None,
        customer_complaints_after: int = 0,
        was_executed: bool = True,
    ):
        """Record actual outcome."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellQualityDecision
            decision = (
                self.db.query(PowellQualityDecision)
                .filter(PowellQualityDecision.quality_order_id == quality_order_id)
                .order_by(PowellQualityDecision.created_at.desc())
                .first()
            )
            if decision:
                decision.was_executed = was_executed
                decision.actual_disposition = actual_disposition
                decision.actual_rework_cost = actual_rework_cost
                decision.actual_scrap_cost = actual_scrap_cost
                decision.customer_complaints_after = customer_complaints_after
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record quality outcome: {e}")

    def get_training_data(self, config_id: int, limit: int = 1000) -> List[Dict]:
        """Extract training data."""
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellQualityDecision
            decisions = (
                self.db.query(PowellQualityDecision)
                .filter(
                    PowellQualityDecision.config_id == config_id,
                    PowellQualityDecision.was_executed.isnot(None),
                )
                .order_by(PowellQualityDecision.created_at.desc())
                .limit(limit)
                .all()
            )
            return [d.to_dict() for d in decisions]
        except Exception as e:
            logger.warning(f"Failed to get quality training data: {e}")
            return []

    def evaluate_batch(self, states: List[QualityDispositionState]) -> List[QualityRecommendation]:
        return [self.evaluate_disposition(s) for s in states]

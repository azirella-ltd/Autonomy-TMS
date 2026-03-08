"""
Transfer Order Execution TRM

Narrow TRM for plan-driven TO execution decisions.

IMPORTANT DISTINCTION:
- TOExecutionTRM: Satisfies MPS/MRP planned transfers (plan-driven)
- InventoryRebalancingTRM: Shorter-horizon financial optimization (opportunity-driven)

TRM Scope (narrow):
- Given: TO details, source/dest inventory, transit time, priority
- Decide: Release now? Expedite? Consolidate? Defer?
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date
import numpy as np
import logging

from .engines.to_execution_engine import (
    TOExecutionEngine, TOExecutionConfig, TOSnapshot, TOExecutionResult,
    TODecisionType,
)
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TOExecutionState:
    """State representation for TO execution TRM"""
    order_id: str
    product_id: str
    source_site_id: str
    dest_site_id: str
    planned_qty: float
    status: str

    # Transportation
    transportation_mode: str = "truck"
    estimated_transit_days: int = 2

    # Source context
    source_on_hand: float = 0.0
    source_dos: float = 0.0
    source_committed: float = 0.0
    source_safety_stock: float = 0.0

    # Destination context
    dest_on_hand: float = 0.0
    dest_dos: float = 0.0
    dest_backlog: float = 0.0
    dest_safety_stock: float = 0.0
    dest_demand_forecast: float = 0.0

    # Timing
    days_until_needed: int = 0
    planned_ship_date: Optional[date] = None
    planned_delivery_date: Optional[date] = None

    # Priority & trigger
    priority: int = 3
    trigger_reason: str = "mrp_planned"

    # Cost
    transportation_cost: float = 0.0

    # Historical
    avg_transit_time_days: float = 0.0
    transit_time_variability: float = 0.0
    carrier_on_time_pct: float = 0.95

    # tGNN context
    lane_criticality: float = 0.5
    network_congestion_score: float = 0.0


@dataclass
class TORecommendation:
    """TRM recommendation for TO execution"""
    order_id: str
    decision_type: str
    confidence: float

    # Actions
    release_now: bool = False
    expedite: bool = False
    consolidate_with: List[str] = field(default_factory=list)
    defer_days: int = 0
    reroute_via: Optional[str] = None

    # Impact
    dest_stockout_risk: float = 0.0
    source_depletion_risk: float = 0.0
    estimated_delivery_date: Optional[date] = None
    cost_impact: float = 0.0

    reason: str = ""
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class TOExecutionTRMConfig:
    """Configuration for TOExecutionTRM"""
    engine_config: TOExecutionConfig = field(default_factory=TOExecutionConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7
    max_defer_days: int = 7


class TOExecutionTRM:
    """
    Transfer Order Execution TRM.

    Wraps the deterministic TOExecutionEngine with learned adjustments
    for release timing, expediting, and consolidation decisions.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[TOExecutionTRMConfig] = None,
        model: Optional[Any] = None,
        db_session: Optional[Any] = None,
    ):
        self.site_key = site_key
        self.config = config or TOExecutionTRMConfig()
        self.engine = TOExecutionEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session
        self.ctx_explainer = None  # Set externally by SiteAgent or caller
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("to_execution")
            except Exception:
                pass

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making TO decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="to_execution",
                types={
                    HiveSignalType.REBALANCE_INBOUND,
                    HiveSignalType.REBALANCE_OUTBOUND,
                    HiveSignalType.NETWORK_SHORTAGE,
                    HiveSignalType.NETWORK_SURPLUS,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.REBALANCE_INBOUND:
                    context["rebalance_inbound"] = True
                    context["rebalance_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.REBALANCE_OUTBOUND:
                    context["rebalance_outbound"] = True
                elif s.signal_type in (HiveSignalType.NETWORK_SHORTAGE, HiveSignalType.NETWORK_SURPLUS):
                    context["network_signal"] = s.signal_type.value
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: TOExecutionState, rec: TORecommendation
    ) -> None:
        """Emit hive signals after TO decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.release_now:
                self.signal_bus.emit(HiveSignal(
                    source_trm="to_execution",
                    signal_type=HiveSignalType.TO_RELEASED,
                    urgency=min(1.0, (5 - state.priority) / 4.0),
                    direction="relief",
                    magnitude=state.planned_qty / 1000.0,
                    product_id=state.product_id,
                    payload={
                        "order_id": state.order_id,
                        "source": state.source_site_id,
                        "dest": state.dest_site_id,
                    },
                ))
                self.signal_bus.urgency.update("to_execution", 0.2, "relief")
            elif rec.defer_days > 0 or rec.decision_type == "defer":
                urgency = min(1.0, 0.3 + rec.dest_stockout_risk * 0.7)
                self.signal_bus.emit(HiveSignal(
                    source_trm="to_execution",
                    signal_type=HiveSignalType.TO_DELAYED,
                    urgency=urgency,
                    direction="risk",
                    magnitude=rec.defer_days / 7.0,
                    product_id=state.product_id,
                    payload={"order_id": state.order_id, "defer_days": rec.defer_days},
                ))
                self.signal_bus.urgency.update("to_execution", urgency, "risk")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate_order(self, state: TOExecutionState) -> TORecommendation:
        """Evaluate a TO and recommend execution action."""
        self._read_signals_before_decision()

        snapshot = TOSnapshot(
            order_id=state.order_id,
            product_id=state.product_id,
            source_site_id=state.source_site_id,
            dest_site_id=state.dest_site_id,
            status=state.status,
            planned_qty=state.planned_qty,
            transportation_mode=state.transportation_mode,
            estimated_transit_days=state.estimated_transit_days,
            planned_ship_date=state.planned_ship_date,
            planned_delivery_date=state.planned_delivery_date,
            trigger_reason=state.trigger_reason,
            priority=state.priority,
            days_until_needed=state.days_until_needed,
            source_on_hand=state.source_on_hand,
            source_dos=state.source_dos,
            source_committed=state.source_committed,
            dest_on_hand=state.dest_on_hand,
            dest_dos=state.dest_dos,
            dest_backlog=state.dest_backlog,
            dest_safety_stock=state.dest_safety_stock,
            transportation_cost=state.transportation_cost,
        )

        engine_result = self.engine.evaluate_order(snapshot)

        if self.model is not None and self.config.use_trm_model:
            try:
                recommendation = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM evaluation failed for TO {state.order_id}: {e}")
                recommendation = self._heuristic_evaluate(state, engine_result)
        else:
            recommendation = self._heuristic_evaluate(state, engine_result)

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = f"{recommendation.decision_type}: TO {state.order_id}"
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
                risk = self._cdt_wrapper.compute_risk_bound(recommendation.cost_impact)
                recommendation.risk_bound = risk.risk_bound
                recommendation.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._emit_signals_after_decision(state, recommendation)
        self._persist_decision(state, recommendation)
        return recommendation

    def _trm_evaluate(
        self, state: TOExecutionState, engine_result: TOExecutionResult
    ) -> TORecommendation:
        """Apply TRM model adjustments."""
        features = self._encode_state(state)
        import torch
        with torch.no_grad():
            state_tensor = torch.tensor([features], dtype=torch.float32)
            output = self.model(state_tensor)

        confidence = float(output.get('confidence', 0.5))
        if confidence < self.config.confidence_threshold:
            return self._heuristic_evaluate(state, engine_result)

        return TORecommendation(
            order_id=state.order_id,
            decision_type=engine_result.decision_type.value,
            confidence=confidence,
            release_now=engine_result.ready_to_release,
            expedite=engine_result.expedite_recommended,
            consolidate_with=engine_result.consolidate_with,
            defer_days=engine_result.defer_days if engine_result.defer_recommended else 0,
            dest_stockout_risk=engine_result.dest_stockout_risk,
            source_depletion_risk=engine_result.source_depletion_risk,
            reason=f"TRM adjusted: {engine_result.explanation}",
        )

    def _heuristic_evaluate(
        self, state: TOExecutionState, engine_result: TOExecutionResult
    ) -> TORecommendation:
        """Heuristic fallback."""
        expedite = engine_result.expedite_recommended

        # Heuristic: Transit time variability buffer
        if state.transit_time_variability > 0.3 and state.days_until_needed <= state.estimated_transit_days + 2:
            expedite = True

        # Heuristic: If destination has backlog AND source has plenty, release immediately
        release_now = engine_result.ready_to_release
        if state.dest_backlog > 0 and state.source_dos > 7 and state.status == "DRAFT":
            release_now = True

        defer_days = 0
        if engine_result.defer_recommended:
            defer_days = min(engine_result.defer_days, self.config.max_defer_days)

        return TORecommendation(
            order_id=state.order_id,
            decision_type=engine_result.decision_type.value,
            confidence=0.6,
            release_now=release_now,
            expedite=expedite,
            consolidate_with=engine_result.consolidate_with,
            defer_days=defer_days,
            dest_stockout_risk=engine_result.dest_stockout_risk,
            source_depletion_risk=engine_result.source_depletion_risk,
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state: TOExecutionState) -> List[float]:
        """Encode state for TRM model."""
        return [
            state.planned_qty / 1000.0,
            state.days_until_needed / 14.0,
            state.priority / 5.0,
            state.estimated_transit_days / 10.0,
            state.source_on_hand / 1000.0,
            state.source_dos / 30.0,
            state.source_committed / 1000.0,
            state.dest_on_hand / 1000.0,
            state.dest_dos / 30.0,
            state.dest_backlog / 500.0,
            state.dest_safety_stock / 500.0,
            state.dest_demand_forecast / 500.0,
            state.transportation_cost / 1000.0,
            state.avg_transit_time_days / 10.0,
            state.transit_time_variability,
            state.carrier_on_time_pct,
            state.lane_criticality,
            state.network_congestion_score,
        ]

    def _persist_decision(self, state: TOExecutionState, rec: TORecommendation):
        """Persist decision to powell_to_decisions table."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellTODecision
            from app.services.powell.decision_reasoning import to_execution_reasoning
            decision = PowellTODecision(
                config_id=0,
                transfer_order_id=state.order_id,
                product_id=state.product_id,
                source_site_id=state.source_site_id,
                dest_site_id=state.dest_site_id,
                planned_qty=state.planned_qty,
                decision_type=rec.decision_type,
                transportation_mode=state.transportation_mode,
                estimated_transit_days=state.estimated_transit_days,
                priority=state.priority,
                trigger_reason=state.trigger_reason,
                confidence=rec.confidence,
                state_features={
                    'source_dos': state.source_dos,
                    'dest_dos': state.dest_dos,
                    'dest_backlog': state.dest_backlog,
                    'days_until_needed': state.days_until_needed,
                },
                decision_reasoning=to_execution_reasoning(
                    product_id=state.product_id,
                    source_site_id=state.source_site_id,
                    dest_site_id=state.dest_site_id,
                    decision_type=rec.decision_type,
                    confidence=rec.confidence,
                    trigger_reason=state.trigger_reason,
                    to_id=state.order_id,
                ),
            )
            self.db.add(decision)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist TO decision: {e}")

    def record_outcome(
        self,
        order_id: str,
        actual_ship_date: Optional[date] = None,
        actual_receipt_date: Optional[date] = None,
        actual_qty: Optional[float] = None,
        actual_transit_days: Optional[int] = None,
        was_executed: bool = True,
    ):
        """Record actual outcome for training data."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellTODecision
            decision = (
                self.db.query(PowellTODecision)
                .filter(PowellTODecision.transfer_order_id == order_id)
                .order_by(PowellTODecision.created_at.desc())
                .first()
            )
            if decision:
                decision.was_executed = was_executed
                decision.actual_ship_date = actual_ship_date
                decision.actual_receipt_date = actual_receipt_date
                decision.actual_qty = actual_qty
                decision.actual_transit_days = actual_transit_days
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record TO outcome: {e}")

    def get_training_data(self, config_id: int, limit: int = 1000) -> List[Dict]:
        """Extract training data for offline RL."""
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellTODecision
            decisions = (
                self.db.query(PowellTODecision)
                .filter(
                    PowellTODecision.config_id == config_id,
                    PowellTODecision.was_executed.isnot(None),
                )
                .order_by(PowellTODecision.created_at.desc())
                .limit(limit)
                .all()
            )
            return [d.to_dict() for d in decisions]
        except Exception as e:
            logger.warning(f"Failed to get TO training data: {e}")
            return []

    def evaluate_batch(self, states: List[TOExecutionState]) -> List[TORecommendation]:
        """Evaluate a batch of TOs."""
        return [self.evaluate_order(s) for s in states]

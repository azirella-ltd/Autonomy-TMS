"""
Manufacturing Order Execution TRM

Narrow TRM for MO execution decisions: release timing, sequencing,
expediting, and split/defer decisions.

TRM Scope (narrow):
- Given: MO details, material availability, capacity, priority
- Decide: Release now? Expedite? Defer? Sequence position?

Integrates with MOExecutionEngine (deterministic base) and learns
to improve sequencing and timing from historical outcomes.

References:
- Powell VFA for narrow execution decisions
- Production scheduling literature (setup time optimization)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, date
import numpy as np
import logging

from .engines.mo_execution_engine import (
    MOExecutionEngine, MOExecutionConfig, MOSnapshot, MOExecutionResult,
    MODecisionType,
)
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class MOExecutionState:
    """State representation for MO execution TRM"""
    # Order features
    order_id: str
    product_id: str
    site_id: str
    planned_quantity: float
    days_until_due: int
    priority: int  # 1-5

    # Material readiness
    material_availability_pct: float
    missing_component_count: int

    # Capacity context
    capacity_utilization_pct: float
    resource_utilization_pct: float
    setup_time_hours: float
    run_time_hours: float

    # Queue context
    queue_depth: int  # How many MOs ahead in queue
    queue_total_hours: float  # Total hours of work in queue

    # Historical context
    avg_yield_pct: float = 0.95  # Historical yield for this product
    avg_setup_overrun_pct: float = 0.0  # How much setups typically overrun
    late_completion_rate: float = 0.0  # Historical late rate for this product

    # Customer link
    customer_order_linked: bool = False
    customer_promise_date: Optional[date] = None

    # Changeover context
    changeover_hours_from_current: float = 0.0  # Setup time from current product on line
    product_group_id: Optional[str] = None       # Product family (for changeover grouping)
    runner_category: str = "blue"                 # Glenday sieve: green/yellow/red/blue

    # From tGNN embeddings
    site_criticality: float = 0.5
    supply_risk_score: float = 0.0


@dataclass
class MORecommendation:
    """TRM recommendation for MO execution"""
    order_id: str
    decision_type: str  # release, sequence, expedite, defer, split
    confidence: float

    # Specific recommendations
    release_now: bool = False
    recommended_sequence_position: int = 0
    expedite: bool = False
    defer_days: int = 0
    split_quantities: List[float] = field(default_factory=list)

    # Priority override
    priority_override: Optional[int] = None

    # Impact
    estimated_completion_date: Optional[date] = None
    service_risk: float = 0.0
    capacity_impact_pct: float = 0.0

    reason: str = ""
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class MOExecutionTRMConfig:
    """Configuration for MOExecutionTRM"""
    engine_config: MOExecutionConfig = field(default_factory=MOExecutionConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7
    max_sequence_adjustment: int = 3  # Max positions to shift in sequence
    max_defer_days: int = 14


class MOExecutionTRM:
    """
    Manufacturing Order Execution TRM.

    Wraps the deterministic MOExecutionEngine with learned adjustments
    for sequencing, timing, and priority decisions.
    """

    def __init__(
        self,
        site_key: str,
        config: Optional[MOExecutionTRMConfig] = None,
        model: Optional[Any] = None,
        db_session: Optional[Any] = None,
        setup_matrix: Optional[Any] = None,
        glenday_sieve: Optional[Any] = None,
    ):
        self.site_key = site_key
        self.config = config or MOExecutionTRMConfig()
        self.engine = MOExecutionEngine(
            site_key, self.config.engine_config, setup_matrix=setup_matrix,
        )
        self.model = model
        self.db = db_session
        self.setup_matrix = setup_matrix
        self.glenday_sieve = glenday_sieve
        self.ctx_explainer = None  # Set externally by SiteAgent or caller
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("mo_execution")
            except Exception:
                pass

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making MO decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="mo_execution",
                types={
                    HiveSignalType.QUALITY_HOLD,
                    HiveSignalType.QUALITY_REJECT,
                    HiveSignalType.MAINTENANCE_URGENT,
                    HiveSignalType.MAINTENANCE_DEFERRED,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.QUALITY_HOLD:
                    context["quality_hold_active"] = True
                    context["quality_hold_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.QUALITY_REJECT:
                    context["quality_reject_active"] = True
                elif s.signal_type == HiveSignalType.MAINTENANCE_URGENT:
                    context["maintenance_urgent"] = True
                    context["maintenance_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.MAINTENANCE_DEFERRED:
                    context["maintenance_deferred"] = True
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: MOExecutionState, rec: MORecommendation
    ) -> None:
        """Emit hive signals after MO decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.release_now:
                self.signal_bus.emit(HiveSignal(
                    source_trm="mo_execution",
                    signal_type=HiveSignalType.MO_RELEASED,
                    urgency=min(1.0, (5 - state.priority) / 4.0),
                    direction="relief",
                    magnitude=state.planned_quantity / 1000.0,
                    product_id=state.product_id,
                    payload={"order_id": state.order_id, "qty": state.planned_quantity},
                ))
                self.signal_bus.urgency.update(
                    "mo_execution", 0.2, "relief",
                )
            elif rec.defer_days > 0 or rec.decision_type == "defer":
                urgency = min(1.0, 0.4 + (rec.service_risk * 0.6))
                self.signal_bus.emit(HiveSignal(
                    source_trm="mo_execution",
                    signal_type=HiveSignalType.MO_DELAYED,
                    urgency=urgency,
                    direction="risk",
                    magnitude=rec.defer_days / 14.0,
                    product_id=state.product_id,
                    payload={"order_id": state.order_id, "defer_days": rec.defer_days},
                ))
                self.signal_bus.urgency.update("mo_execution", urgency, "risk")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate_order(self, state: MOExecutionState) -> MORecommendation:
        """
        Evaluate an MO and recommend execution action.

        Flow:
        1. Read hive signals for context
        2. Build MOSnapshot from state
        3. Run deterministic engine
        4. If TRM model available, apply learned adjustments
        5. Emit signals and persist decision
        """
        # Read hive signals
        self._read_signals_before_decision()

        # Build engine snapshot
        snapshot = MOSnapshot(
            order_id=state.order_id,
            product_id=state.product_id,
            site_id=state.site_id,
            status="PLANNED",
            planned_quantity=state.planned_quantity,
            material_availability_pct=state.material_availability_pct,
            missing_components=[f"comp_{i}" for i in range(state.missing_component_count)],
            capacity_availability_pct=1.0 - state.capacity_utilization_pct,
            resource_utilization_pct=state.resource_utilization_pct,
            setup_time_hours=state.setup_time_hours,
            run_time_hours=state.run_time_hours,
            priority=state.priority,
            customer_order_linked=state.customer_order_linked,
            days_until_due=state.days_until_due,
        )

        # Step 1: Deterministic engine evaluation
        engine_result = self.engine.evaluate_order(snapshot)

        # Step 2: TRM adjustment (if model available)
        if self.model is not None and self.config.use_trm_model:
            try:
                recommendation = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM evaluation failed for MO {state.order_id}: {e}")
                recommendation = self._heuristic_evaluate(state, engine_result)
        else:
            recommendation = self._heuristic_evaluate(state, engine_result)

        # Step 3: Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = f"{recommendation.decision_type}: MO {state.order_id}"
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
                risk = self._cdt_wrapper.compute_risk_bound(recommendation.service_risk)
                recommendation.risk_bound = risk.risk_bound
                recommendation.risk_assessment = risk.to_dict()
            except Exception:
                pass

        # Step 4: Emit signals
        self._emit_signals_after_decision(state, recommendation)

        # Step 5: Persist decision
        self._persist_decision(state, recommendation)

        return recommendation

    def _trm_evaluate(
        self, state: MOExecutionState, engine_result: MOExecutionResult
    ) -> MORecommendation:
        """Apply TRM model adjustments to engine result."""
        # Encode state features
        features = self._encode_state(state)

        # Forward pass through TRM model
        import torch
        with torch.no_grad():
            state_tensor = torch.tensor([features], dtype=torch.float32)
            output = self.model(state_tensor)

        # Parse model output
        confidence = float(output.get('confidence', 0.5))

        if confidence < self.config.confidence_threshold:
            return self._heuristic_evaluate(state, engine_result)

        # Apply TRM adjustments
        recommendation = MORecommendation(
            order_id=state.order_id,
            decision_type=engine_result.decision_type.value,
            confidence=confidence,
            release_now=engine_result.ready_to_release,
            recommended_sequence_position=engine_result.recommended_sequence,
            expedite=engine_result.expedite_recommended,
            defer_days=engine_result.defer_days if engine_result.defer_recommended else 0,
            service_risk=engine_result.service_risk,
            reason=f"TRM adjusted: {engine_result.explanation}",
        )

        # Apply sequence adjustment if model suggests it
        if 'sequence_adj' in output:
            adj = int(output['sequence_adj'].item())
            adj = max(-self.config.max_sequence_adjustment,
                      min(self.config.max_sequence_adjustment, adj))
            recommendation.recommended_sequence_position = max(
                1, engine_result.recommended_sequence + adj
            )

        # Apply priority override if model suggests it
        if 'priority_override' in output:
            override = int(output['priority_override'].item())
            if 1 <= override <= 5:
                recommendation.priority_override = override

        return recommendation

    def _heuristic_evaluate(
        self, state: MOExecutionState, engine_result: MOExecutionResult
    ) -> MORecommendation:
        """Heuristic fallback when no trained TRM model."""
        # Enhance engine result with heuristic rules
        decision_type = engine_result.decision_type.value
        expedite = engine_result.expedite_recommended

        # Heuristic: If customer-linked and close to due, boost priority
        priority_override = None
        if state.customer_order_linked and state.days_until_due <= 5 and state.priority > 2:
            priority_override = 2
            expedite = True

        # Heuristic: If yield is historically poor, increase quantity
        split_quantities = []
        if state.avg_yield_pct < 0.90 and state.planned_quantity > 100:
            # Suggest producing more to account for scrap
            overage = state.planned_quantity * (1.0 - state.avg_yield_pct) * 1.2
            split_quantities = [state.planned_quantity + overage]

        # Heuristic: If setup overruns are common, add buffer
        defer_days = 0
        if engine_result.defer_recommended:
            defer_days = min(engine_result.defer_days, self.config.max_defer_days)

        return MORecommendation(
            order_id=state.order_id,
            decision_type=decision_type,
            confidence=0.6,
            release_now=engine_result.ready_to_release,
            recommended_sequence_position=engine_result.recommended_sequence,
            expedite=expedite,
            defer_days=defer_days,
            split_quantities=split_quantities,
            priority_override=priority_override,
            estimated_completion_date=engine_result.estimated_completion_date,
            service_risk=engine_result.service_risk,
            capacity_impact_pct=engine_result.capacity_impact_pct,
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state: MOExecutionState) -> List[float]:
        """Encode state for TRM model input (20 floats, matches MO_STATE_DIM).

        Feature mapping (matches mo_execution_trm_model.py):
          [0] work_in_progress (queue_total_hours normalised)
          [1] capacity_available (1 - utilization)
          [2] order_qty (normalised)
          [3] due_date_urgency (0-1)
          [4] backlog (queue_depth normalised)
          [5] material_available (0-1)
          [6] operator_available (1 - resource_utilization)
          [7] quality_rate (yield_pct)
          [8] tool_wear (setup_overrun as proxy)
          [9] maintenance_due (0-1, from signals)
          [10] parallel_orders (queue_depth normalised)
          [11] priority (normalised)
          [12] yield_rate (0-1)
          [13] energy_cost (normalised, placeholder)
          [14] overtime_available (0-1)
          [15] sequence_position (normalised)
          [16] bom_coverage (material_availability)
          [17] defect_rate (1 - yield)
          [18] setup_time (normalised, includes changeover)
          [19] cycle_time (run_time normalised)
        """
        # Changeover-aware setup time: use actual changeover if available
        effective_setup = state.setup_time_hours
        if state.changeover_hours_from_current > 0:
            effective_setup = state.changeover_hours_from_current

        # Runner category encoding: green=1.0, yellow=0.66, red=0.33, blue=0.0
        _runner_map = {"green": 1.0, "yellow": 0.66, "red": 0.33, "blue": 0.0}

        return [
            min(state.queue_total_hours / 100.0, 1.0),           # [0] work_in_progress
            max(0.0, 1.0 - state.capacity_utilization_pct),      # [1] capacity_available
            state.planned_quantity / 1000.0,                      # [2] order_qty
            max(0.0, 1.0 - state.days_until_due / 30.0),         # [3] due_date_urgency
            min(state.queue_depth / 20.0, 1.0),                   # [4] backlog
            state.material_availability_pct,                       # [5] material_available
            max(0.0, 1.0 - state.resource_utilization_pct),       # [6] operator_available
            state.avg_yield_pct,                                   # [7] quality_rate
            min(state.avg_setup_overrun_pct, 1.0),                # [8] tool_wear
            0.0,  # [9] maintenance_due — populated from hive signals
            min(state.queue_depth / 20.0, 1.0),                   # [10] parallel_orders
            state.priority / 5.0,                                  # [11] priority
            state.avg_yield_pct,                                   # [12] yield_rate
            _runner_map.get(state.runner_category, 0.0),          # [13] runner_category (repurposed from energy_cost)
            1.0 if state.customer_order_linked else 0.5,          # [14] overtime_available
            state.queue_depth / max(state.queue_depth + 1, 1),    # [15] sequence_position
            state.material_availability_pct,                       # [16] bom_coverage
            max(0.0, 1.0 - state.avg_yield_pct),                 # [17] defect_rate
            min(effective_setup / 8.0, 1.0),                      # [18] setup_time (changeover-aware)
            min(state.run_time_hours / 24.0, 1.0),               # [19] cycle_time
        ]

    def _persist_decision(self, state: MOExecutionState, rec: MORecommendation):
        """Persist decision to powell_mo_decisions table."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellMODecision
            from app.services.powell.decision_reasoning import mo_execution_reasoning
            decision = PowellMODecision(
                config_id=0,  # Set by caller
                production_order_id=state.order_id,
                product_id=state.product_id,
                site_id=state.site_id,
                planned_qty=state.planned_quantity,
                decision_type=rec.decision_type,
                sequence_position=rec.recommended_sequence_position,
                priority_override=rec.priority_override,
                resource_id=None,
                setup_time_hours=state.setup_time_hours,
                run_time_hours=state.run_time_hours,
                confidence=rec.confidence,
                state_features={
                    'material_pct': state.material_availability_pct,
                    'capacity_pct': state.capacity_utilization_pct,
                    'days_until_due': state.days_until_due,
                    'queue_depth': state.queue_depth,
                    'yield_pct': state.avg_yield_pct,
                },
                decision_reasoning=mo_execution_reasoning(
                    product_id=state.product_id,
                    location_id=state.site_id,
                    decision_type=rec.decision_type,
                    confidence=rec.confidence,
                    mo_id=state.order_id,
                ),
            )
            self.db.add(decision)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist MO decision: {e}")

    def record_outcome(
        self,
        order_id: str,
        actual_completion_date: Optional[datetime] = None,
        actual_qty: Optional[float] = None,
        actual_yield_pct: Optional[float] = None,
        was_executed: bool = True,
    ):
        """Record actual outcome for training data."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellMODecision
            decision = (
                self.db.query(PowellMODecision)
                .filter(PowellMODecision.production_order_id == order_id)
                .order_by(PowellMODecision.created_at.desc())
                .first()
            )
            if decision:
                decision.was_executed = was_executed
                decision.actual_completion_date = actual_completion_date
                decision.actual_qty = actual_qty
                decision.actual_yield_pct = actual_yield_pct
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record MO outcome: {e}")

    def get_training_data(self, config_id: int, limit: int = 1000) -> List[Dict]:
        """Extract training data for offline RL."""
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellMODecision
            decisions = (
                self.db.query(PowellMODecision)
                .filter(
                    PowellMODecision.config_id == config_id,
                    PowellMODecision.was_executed.isnot(None),
                )
                .order_by(PowellMODecision.created_at.desc())
                .limit(limit)
                .all()
            )
            return [d.to_dict() for d in decisions]
        except Exception as e:
            logger.warning(f"Failed to get MO training data: {e}")
            return []

    def evaluate_batch(self, states: List[MOExecutionState]) -> List[MORecommendation]:
        """Evaluate a batch of MOs."""
        return [self.evaluate_order(s) for s in states]

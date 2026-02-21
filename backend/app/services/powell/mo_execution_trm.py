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
    ):
        self.site_key = site_key
        self.config = config or MOExecutionTRMConfig()
        self.engine = MOExecutionEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session
        self.ctx_explainer = None  # Set externally by SiteAgent or caller

    def evaluate_order(self, state: MOExecutionState) -> MORecommendation:
        """
        Evaluate an MO and recommend execution action.

        Flow:
        1. Build MOSnapshot from state
        2. Run deterministic engine
        3. If TRM model available, apply learned adjustments
        4. Persist decision for training
        """
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

        # Step 4: Persist decision
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
        """Encode state for TRM model input."""
        return [
            state.planned_quantity / 1000.0,
            state.days_until_due / 30.0,
            state.priority / 5.0,
            state.material_availability_pct,
            state.missing_component_count / 10.0,
            state.capacity_utilization_pct,
            state.resource_utilization_pct,
            state.setup_time_hours / 8.0,
            state.run_time_hours / 24.0,
            state.queue_depth / 20.0,
            state.queue_total_hours / 100.0,
            state.avg_yield_pct,
            state.avg_setup_overrun_pct,
            state.late_completion_rate,
            1.0 if state.customer_order_linked else 0.0,
            state.site_criticality,
            state.supply_risk_score,
        ]

    def _persist_decision(self, state: MOExecutionState, rec: MORecommendation):
        """Persist decision to powell_mo_decisions table."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellMODecision
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

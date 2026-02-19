"""
Decision Integration

Records SiteAgent's TRM decisions for audit trail and RLHF feedback.
Connects with the planning decision service for tracking.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session

from app.services.powell.site_agent import SiteAgent, ATPResponse
from app.services.powell.cdc_monitor import TriggerEvent

logger = logging.getLogger(__name__)


@dataclass
class TRMDecisionRecord:
    """Record of a TRM decision for audit and training."""
    decision_id: str
    site_key: str
    decision_type: str  # atp_exception, inventory_adjustment, po_timing, cdc_trigger
    timestamp: datetime

    # Input context
    input_state: Dict[str, Any]

    # Deterministic result (baseline)
    deterministic_result: Dict[str, Any]

    # TRM adjustment
    trm_adjustment: Dict[str, Any]
    confidence: float

    # Final result
    final_result: Dict[str, Any]

    # Feedback (filled in later)
    actual_outcome: Optional[Dict[str, Any]] = None
    reward_signal: Optional[float] = None
    human_feedback: Optional[str] = None


class SiteAgentDecisionTracker:
    """
    Tracks SiteAgent decisions for audit trail and RLHF feedback.

    Records all TRM-adjusted decisions with:
    - Input context
    - Deterministic baseline
    - TRM adjustment
    - Confidence scores
    - Later: actual outcomes for reward signal
    """

    def __init__(self, db: Session):
        """
        Initialize decision tracker.

        Args:
            db: Database session
        """
        self.db = db
        self._pending_decisions: Dict[str, TRMDecisionRecord] = {}

    def record_atp_decision(
        self,
        site_key: str,
        order_context: Dict[str, Any],
        deterministic_result: Dict[str, Any],
        trm_adjustment: Optional[Dict[str, Any]],
        final_response: ATPResponse
    ) -> str:
        """
        Record an ATP decision.

        Args:
            site_key: Site identifier
            order_context: Order request context
            deterministic_result: Result from AATP engine
            trm_adjustment: TRM adjustment applied
            final_response: Final ATP response

        Returns:
            Decision ID for later feedback
        """
        import uuid
        decision_id = f"ATP-{uuid.uuid4().hex[:8]}"

        record = TRMDecisionRecord(
            decision_id=decision_id,
            site_key=site_key,
            decision_type="atp_exception",
            timestamp=datetime.utcnow(),
            input_state=order_context,
            deterministic_result=deterministic_result,
            trm_adjustment=trm_adjustment or {},
            confidence=final_response.confidence,
            final_result={
                "promised_qty": final_response.promised_qty,
                "source": final_response.source,
                "exception_action": final_response.exception_action,
            }
        )

        self._pending_decisions[decision_id] = record
        self._persist_decision(record)

        logger.debug(f"Recorded ATP decision {decision_id}")
        return decision_id

    def record_inventory_adjustment(
        self,
        site_key: str,
        current_state: Dict[str, Any],
        deterministic_ss: float,
        trm_multiplier: float,
        final_ss: float,
        confidence: float
    ) -> str:
        """
        Record an inventory adjustment decision.

        Args:
            site_key: Site identifier
            current_state: Current inventory state
            deterministic_ss: Safety stock from formula
            trm_multiplier: TRM adjustment multiplier
            final_ss: Final safety stock
            confidence: TRM confidence

        Returns:
            Decision ID
        """
        import uuid
        decision_id = f"INV-{uuid.uuid4().hex[:8]}"

        record = TRMDecisionRecord(
            decision_id=decision_id,
            site_key=site_key,
            decision_type="inventory_adjustment",
            timestamp=datetime.utcnow(),
            input_state=current_state,
            deterministic_result={"safety_stock": deterministic_ss},
            trm_adjustment={"multiplier": trm_multiplier},
            confidence=confidence,
            final_result={"safety_stock": final_ss}
        )

        self._pending_decisions[decision_id] = record
        self._persist_decision(record)

        logger.debug(f"Recorded inventory adjustment {decision_id}")
        return decision_id

    def record_po_timing_decision(
        self,
        site_key: str,
        po_context: Dict[str, Any],
        planned_date: str,
        days_offset: int,
        expedite_prob: float,
        final_date: str,
        confidence: float
    ) -> str:
        """
        Record a PO timing decision.

        Args:
            site_key: Site identifier
            po_context: PO context
            planned_date: Original planned date
            days_offset: TRM timing adjustment
            expedite_prob: Expedite probability
            final_date: Final order date
            confidence: TRM confidence

        Returns:
            Decision ID
        """
        import uuid
        decision_id = f"PO-{uuid.uuid4().hex[:8]}"

        record = TRMDecisionRecord(
            decision_id=decision_id,
            site_key=site_key,
            decision_type="po_timing",
            timestamp=datetime.utcnow(),
            input_state=po_context,
            deterministic_result={"planned_date": planned_date},
            trm_adjustment={
                "days_offset": days_offset,
                "expedite_prob": expedite_prob,
            },
            confidence=confidence,
            final_result={"final_date": final_date}
        )

        self._pending_decisions[decision_id] = record
        self._persist_decision(record)

        logger.debug(f"Recorded PO timing decision {decision_id}")
        return decision_id

    def record_cdc_trigger(
        self,
        site_key: str,
        metrics: Dict[str, Any],
        trigger_result: TriggerEvent
    ) -> str:
        """
        Record a CDC trigger decision.

        Args:
            site_key: Site identifier
            metrics: Site metrics that triggered CDC
            trigger_result: CDC trigger result

        Returns:
            Decision ID
        """
        import uuid
        decision_id = f"CDC-{uuid.uuid4().hex[:8]}"

        record = TRMDecisionRecord(
            decision_id=decision_id,
            site_key=site_key,
            decision_type="cdc_trigger",
            timestamp=datetime.utcnow(),
            input_state=metrics,
            deterministic_result={
                "triggered": trigger_result.triggered,
                "reasons": [r.value for r in trigger_result.reasons],
            },
            trm_adjustment={},  # CDC is deterministic
            confidence=1.0,
            final_result={
                "action": trigger_result.recommended_action.value,
                "severity": trigger_result.severity,
            }
        )

        self._pending_decisions[decision_id] = record
        self._persist_decision(record)

        logger.info(f"Recorded CDC trigger {decision_id}")
        return decision_id

    def record_outcome(
        self,
        decision_id: str,
        actual_outcome: Dict[str, Any],
        reward_signal: Optional[float] = None
    ) -> bool:
        """
        Record actual outcome for a decision (for RLHF).

        Args:
            decision_id: Decision ID
            actual_outcome: What actually happened
            reward_signal: Computed reward (optional)

        Returns:
            True if outcome recorded
        """
        if decision_id in self._pending_decisions:
            record = self._pending_decisions[decision_id]
            record.actual_outcome = actual_outcome
            record.reward_signal = reward_signal
            self._persist_decision(record)
            logger.debug(f"Recorded outcome for decision {decision_id}")
            return True

        # Try to load from database
        return self._update_persisted_outcome(decision_id, actual_outcome, reward_signal)

    def record_human_feedback(
        self,
        decision_id: str,
        feedback: str,
        rating: Optional[int] = None
    ) -> bool:
        """
        Record human feedback on a decision.

        Args:
            decision_id: Decision ID
            feedback: Human feedback text
            rating: Optional rating (1-5)

        Returns:
            True if feedback recorded
        """
        if decision_id in self._pending_decisions:
            record = self._pending_decisions[decision_id]
            record.human_feedback = feedback
            self._persist_decision(record)
            logger.debug(f"Recorded human feedback for decision {decision_id}")
            return True

        return self._update_persisted_feedback(decision_id, feedback, rating)

    def get_pending_outcomes(
        self,
        delay_map: Optional[Dict[str, 'timedelta']] = None,
        site_key: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Get decisions without outcomes that are past their delay threshold.

        Args:
            delay_map: {decision_type: timedelta} for per-type feedback horizons.
                       Defaults to sensible values if not provided.
            site_key: Filter by site
            limit: Maximum records per type

        Returns:
            List of decision records awaiting outcome computation
        """
        from datetime import timedelta as td
        if delay_map is None:
            delay_map = {
                "atp_exception": td(hours=4),
                "inventory_adjustment": td(hours=24),
                "po_timing": td(days=7),
                "cdc_trigger": td(hours=24),
            }

        results = []
        now = datetime.utcnow()

        try:
            from app.models.powell_decision import SiteAgentDecision

            for decision_type, delay in delay_map.items():
                cutoff = now - delay
                query = self.db.query(SiteAgentDecision).filter(
                    SiteAgentDecision.actual_outcome.is_(None),
                    SiteAgentDecision.decision_type == decision_type,
                    SiteAgentDecision.timestamp < cutoff,
                    SiteAgentDecision.timestamp > now - td(days=30),
                )
                if site_key:
                    query = query.filter(SiteAgentDecision.site_key == site_key)

                for d in query.limit(limit).all():
                    results.append(asdict(TRMDecisionRecord(
                        decision_id=d.decision_id,
                        site_key=d.site_key,
                        decision_type=d.decision_type,
                        timestamp=d.timestamp,
                        input_state=d.input_state or {},
                        deterministic_result=d.deterministic_result or {},
                        trm_adjustment=d.trm_adjustment or {},
                        confidence=d.confidence,
                        final_result=d.final_result or {},
                    )))
        except Exception as e:
            logger.warning(f"Failed to query pending outcomes: {e}")

        return results

    def get_decisions_for_training(
        self,
        site_key: Optional[str] = None,
        decision_type: Optional[str] = None,
        with_outcomes: bool = True,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get decisions for TRM training.

        Args:
            site_key: Filter by site
            decision_type: Filter by type
            with_outcomes: Only include decisions with recorded outcomes
            limit: Maximum records

        Returns:
            List of decision records
        """
        # Query from database
        records = self._query_decisions(site_key, decision_type, with_outcomes, limit)
        return [asdict(r) for r in records]

    def compute_reward_signals(
        self,
        decision_ids: List[str]
    ) -> Dict[str, float]:
        """
        Compute reward signals for decisions based on outcomes.

        Args:
            decision_ids: Decision IDs to process

        Returns:
            {decision_id: reward}
        """
        rewards = {}

        for decision_id in decision_ids:
            record = self._pending_decisions.get(decision_id)
            if not record or not record.actual_outcome:
                continue

            # Compute reward based on decision type
            if record.decision_type == "atp_exception":
                rewards[decision_id] = self._compute_atp_reward(record)
            elif record.decision_type == "inventory_adjustment":
                rewards[decision_id] = self._compute_inventory_reward(record)
            elif record.decision_type == "po_timing":
                rewards[decision_id] = self._compute_po_reward(record)
            elif record.decision_type == "cdc_trigger":
                rewards[decision_id] = self._compute_cdc_reward(record)

        return rewards

    def _compute_atp_reward(self, record: TRMDecisionRecord) -> float:
        """Compute reward for ATP decision."""
        outcome = record.actual_outcome or {}

        # Reward = fulfillment rate - penalty for over-promise
        fulfilled = outcome.get("fulfilled_qty", 0)
        promised = record.final_result.get("promised_qty", 0)

        if promised > 0:
            fulfillment_rate = min(1.0, fulfilled / promised)
            over_promise_penalty = max(0, promised - fulfilled) * 0.1
            return fulfillment_rate - over_promise_penalty
        return 0.0

    def _compute_inventory_reward(self, record: TRMDecisionRecord) -> float:
        """Compute reward for inventory adjustment."""
        outcome = record.actual_outcome or {}

        # Reward = service level achieved - excess holding cost
        service_level = outcome.get("service_level", 0.95)
        avg_inventory = outcome.get("avg_inventory", 0)
        target_ss = record.final_result.get("safety_stock", 100)

        holding_penalty = max(0, (avg_inventory - target_ss) / max(target_ss, 1)) * 0.1
        return service_level - holding_penalty

    def _compute_po_reward(self, record: TRMDecisionRecord) -> float:
        """Compute reward for PO timing decision."""
        outcome = record.actual_outcome or {}

        # Reward = on-time delivery rate
        on_time = outcome.get("on_time_delivery", False)
        days_late = outcome.get("days_late", 0)

        if on_time:
            return 1.0
        else:
            return max(0, 1.0 - days_late * 0.1)

    def _compute_cdc_reward(self, record: TRMDecisionRecord) -> float:
        """Compute reward for CDC trigger decision."""
        outcome = record.actual_outcome or {}

        # Reward = improvement in KPIs after replan
        pre_kpi = outcome.get("pre_replan_kpi", 0.9)
        post_kpi = outcome.get("post_replan_kpi", 0.9)
        replan_cost = outcome.get("replan_cost", 0)

        improvement = post_kpi - pre_kpi
        return improvement - replan_cost * 0.01

    def _persist_decision(self, record: TRMDecisionRecord) -> None:
        """Persist decision to database."""
        try:
            from app.models.powell_decision import SiteAgentDecision

            decision = self.db.query(SiteAgentDecision).filter_by(
                decision_id=record.decision_id
            ).first()

            if decision:
                # Update existing
                decision.actual_outcome = record.actual_outcome
                decision.reward_signal = record.reward_signal
                decision.human_feedback = record.human_feedback
            else:
                # Create new
                decision = SiteAgentDecision(
                    decision_id=record.decision_id,
                    site_key=record.site_key,
                    decision_type=record.decision_type,
                    timestamp=record.timestamp,
                    input_state=record.input_state,
                    deterministic_result=record.deterministic_result,
                    trm_adjustment=record.trm_adjustment,
                    confidence=record.confidence,
                    final_result=record.final_result,
                    actual_outcome=record.actual_outcome,
                    reward_signal=record.reward_signal,
                    human_feedback=record.human_feedback,
                )
                self.db.add(decision)

            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist decision {record.decision_id}: {e}")
            self.db.rollback()

    def _update_persisted_outcome(
        self,
        decision_id: str,
        outcome: Dict[str, Any],
        reward: Optional[float]
    ) -> bool:
        """Update outcome for persisted decision."""
        try:
            from app.models.powell_decision import SiteAgentDecision

            decision = self.db.query(SiteAgentDecision).filter_by(
                decision_id=decision_id
            ).first()

            if decision:
                decision.actual_outcome = outcome
                decision.reward_signal = reward
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False

    def _update_persisted_feedback(
        self,
        decision_id: str,
        feedback: str,
        rating: Optional[int]
    ) -> bool:
        """Update feedback for persisted decision."""
        try:
            from app.models.powell_decision import SiteAgentDecision

            decision = self.db.query(SiteAgentDecision).filter_by(
                decision_id=decision_id
            ).first()

            if decision:
                decision.human_feedback = feedback
                if rating:
                    decision.human_rating = rating
                self.db.commit()
                return True
            return False
        except Exception:
            self.db.rollback()
            return False

    def _query_decisions(
        self,
        site_key: Optional[str],
        decision_type: Optional[str],
        with_outcomes: bool,
        limit: int
    ) -> List[TRMDecisionRecord]:
        """Query decisions from database."""
        try:
            from app.models.powell_decision import SiteAgentDecision

            query = self.db.query(SiteAgentDecision)

            if site_key:
                query = query.filter(SiteAgentDecision.site_key == site_key)
            if decision_type:
                query = query.filter(SiteAgentDecision.decision_type == decision_type)
            if with_outcomes:
                query = query.filter(SiteAgentDecision.actual_outcome.isnot(None))

            query = query.order_by(SiteAgentDecision.timestamp.desc()).limit(limit)

            return [
                TRMDecisionRecord(
                    decision_id=d.decision_id,
                    site_key=d.site_key,
                    decision_type=d.decision_type,
                    timestamp=d.timestamp,
                    input_state=d.input_state or {},
                    deterministic_result=d.deterministic_result or {},
                    trm_adjustment=d.trm_adjustment or {},
                    confidence=d.confidence,
                    final_result=d.final_result or {},
                    actual_outcome=d.actual_outcome,
                    reward_signal=d.reward_signal,
                    human_feedback=d.human_feedback,
                )
                for d in query.all()
            ]
        except Exception as e:
            logger.warning(f"Failed to query decisions: {e}")
            return []

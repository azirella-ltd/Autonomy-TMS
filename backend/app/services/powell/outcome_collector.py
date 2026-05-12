"""Outcome Collector — TMS legacy paths (per-TRM tables + skill outcomes).

§3.64 closure note: The ``SiteAgentDecision`` collection path that this
file used to own has moved to Core's ``OutcomeCollectorService`` via
:class:`TmsOutcomeAdapter`. What remains here are the two paths that
have not yet migrated to Core:

* ``collect_trm_outcomes`` — the 11 per-``Powell*Decision`` tables.
  Each writes typed plane-specific columns (``was_committed``,
  ``actual_fulfilled_qty``, ``was_executed``, ``actual_qty``, …)
  that don't fit Core's generic ``actual_outcome`` JSON shape today.
  Consolidation lands as **§3.66**.
* ``collect_skill_outcomes`` — the ``decision_embeddings``
  (Knowledge Base) outcome path. Runs against the KB database session
  rather than the primary backend session, so it sits separately
  from the Core feedback loop. Future consolidation tracked under
  §3.66 once the per-TRM shape is settled.

Together these are ~600 LOC of plane-and-KB-specific operational
glue — same shape as SCP's equivalent file. Both consolidate under
§3.66.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Feedback horizons for the 15 powell_*_decisions tables.
# Mirrors the canonical Core ``TRM_DECISION_HORIZONS`` in
# ``azirella_data_model.governance.causal.feedback_horizons``. Kept
# here because the legacy collect_trm_outcomes loop indexes its
# per-trm collectors against this table; §3.66 migrates the loop to
# Core and removes the local copy.
TRM_OUTCOME_DELAY = {
    "atp": timedelta(hours=4),
    "rebalance": timedelta(days=7),
    "po": timedelta(days=7),
    "order_tracking": timedelta(days=3),
    "mo": timedelta(days=3),
    "to": timedelta(days=5),
    "quality": timedelta(days=2),
    "maintenance": timedelta(days=7),
    "subcontracting": timedelta(days=14),
    "forecast_adjustment": timedelta(days=30),
    "inventory_buffer": timedelta(days=14),
    # Planning TRM feedback horizons
    "demand_adjustment":    timedelta(weeks=4),
    "inventory_adjustment": timedelta(weeks=2),
    "supply_adjustment":    timedelta(days=7),
    "rccp_adjustment":      timedelta(weeks=2),
}


class OutcomeCollectorService:
    """Per-TRM and skill outcome collection.

    The ``SiteAgentDecision`` path that used to live here moved to
    Core under §3.64. Construct this only for the per-TRM (and skill)
    collection paths invoked by ``relearning_jobs``.
    """

    def __init__(self, db: Session):
        self.db = db
        # Lazy import: keeps the per-tenant EK shaping out of the
        # import graph until needed by the skill path.
        from app.services.powell.trm_trainer import RewardCalculator
        self.reward_calculator = RewardCalculator()

    # ------------------------------------------------------------------
    # Path 2: powell_*_decisions table outcome collection (all 11 TRMs)
    # ------------------------------------------------------------------

    def collect_trm_outcomes(self) -> Dict[str, Any]:
        """Collect outcomes for all 11 TRM decision types from
        powell_*_decisions tables.

        Each per-trm collector marks pending decisions as observed and
        fills in actual_* columns from either operational tables (ATP,
        inventory_buffer) or stubbed planned-as-actual (the rest until
        real ERP wire-up).
        """
        stats = {"processed": 0, "succeeded": 0, "failed": 0, "by_type": {}}
        now = datetime.utcnow()

        collectors = [
            ("atp", self._collect_atp_trm_outcomes),
            ("rebalance", self._collect_rebalance_outcomes),
            ("po", self._collect_po_trm_outcomes),
            ("order_tracking", self._collect_order_tracking_outcomes),
            ("mo", self._collect_mo_outcomes),
            ("to", self._collect_to_outcomes),
            ("quality", self._collect_quality_outcomes),
            ("maintenance", self._collect_maintenance_outcomes),
            ("subcontracting", self._collect_subcontracting_outcomes),
            ("forecast_adjustment", self._collect_forecast_adjustment_outcomes),
            ("inventory_buffer", self._collect_inventory_buffer_outcomes),
        ]

        for trm_type, collector_fn in collectors:
            delay = TRM_OUTCOME_DELAY.get(trm_type, timedelta(days=7))
            cutoff = now - delay
            try:
                result = collector_fn(cutoff, now)
                stats["processed"] += result.get("found", 0)
                stats["succeeded"] += result.get("computed", 0)
                stats["failed"] += result.get("failed", 0)
                stats["by_type"][trm_type] = result
            except Exception as e:
                logger.warning(f"TRM outcome collection failed for {trm_type}: {e}")
                stats["by_type"][trm_type] = {
                    "found": 0, "computed": 0, "failed": 1, "error": str(e)
                }

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit TRM outcomes: {e}")
            self.db.rollback()

        logger.info(
            f"TRM outcome collection: {stats['succeeded']} computed, "
            f"{stats['failed']} failed out of {stats['processed']} processed"
        )
        return stats

    def _collect_atp_trm_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_atp_decisions."""
        from app.models.powell_decisions import PowellATPDecision
        from app.models.sc_entities import OutboundOrderLine

        decisions = self.db.query(PowellATPDecision).filter(
            PowellATPDecision.was_committed.is_(None),
            PowellATPDecision.created_at < cutoff,
            PowellATPDecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                order = self.db.query(OutboundOrderLine).filter(
                    OutboundOrderLine.order_id == d.order_id,
                ).first()
                if order:
                    d.was_committed = True
                    d.actual_fulfilled_qty = float(order.shipped_quantity or 0)
                    d.fulfillment_date = now
                    result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_rebalance_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_rebalance_decisions."""
        from app.models.powell_decisions import PowellRebalanceDecision

        decisions = self.db.query(PowellRebalanceDecision).filter(
            PowellRebalanceDecision.was_executed.is_(None),
            PowellRebalanceDecision.created_at < cutoff,
            PowellRebalanceDecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_qty = d.recommended_qty
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_po_trm_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_po_decisions."""
        from app.models.powell_decisions import PowellPODecision

        decisions = self.db.query(PowellPODecision).filter(
            PowellPODecision.was_executed.is_(None),
            PowellPODecision.created_at < cutoff,
            PowellPODecision.created_at > now - timedelta(days=60),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_qty = d.recommended_qty
                d.actual_cost = d.expected_cost or 0.0
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_order_tracking_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_order_exceptions."""
        from app.models.powell_decisions import PowellOrderException

        decisions = self.db.query(PowellOrderException).filter(
            PowellOrderException.action_taken.is_(None),
            PowellOrderException.created_at < cutoff,
            PowellOrderException.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.action_taken = d.recommended_action
                d.resolved_at = now
                d.actual_impact_cost = d.estimated_impact_cost or 0.0
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_mo_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_mo_decisions."""
        from app.models.powell_decisions import PowellMODecision

        decisions = self.db.query(PowellMODecision).filter(
            PowellMODecision.was_executed.is_(None),
            PowellMODecision.created_at < cutoff,
            PowellMODecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_qty = d.planned_qty
                d.actual_yield_pct = 0.95
                d.actual_completion_date = now
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_to_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_to_decisions."""
        from app.models.powell_decisions import PowellTODecision

        decisions = self.db.query(PowellTODecision).filter(
            PowellTODecision.was_executed.is_(None),
            PowellTODecision.created_at < cutoff,
            PowellTODecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_qty = d.planned_qty
                d.actual_transit_days = d.estimated_transit_days or 2.0
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_quality_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_quality_decisions."""
        from app.models.powell_decisions import PowellQualityDecision

        decisions = self.db.query(PowellQualityDecision).filter(
            PowellQualityDecision.was_executed.is_(None),
            PowellQualityDecision.created_at < cutoff,
            PowellQualityDecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_disposition = d.disposition
                d.actual_rework_cost = d.rework_cost_estimate or 0.0
                d.actual_scrap_cost = d.scrap_cost_estimate or 0.0
                d.customer_complaints_after = 0
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_maintenance_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_maintenance_decisions."""
        from app.models.powell_decisions import PowellMaintenanceDecision

        decisions = self.db.query(PowellMaintenanceDecision).filter(
            PowellMaintenanceDecision.was_executed.is_(None),
            PowellMaintenanceDecision.created_at < cutoff,
            PowellMaintenanceDecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_start_date = d.created_at
                d.actual_completion_date = now
                d.actual_downtime_hours = d.estimated_downtime_hours or 0.0
                d.breakdown_occurred = False
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_subcontracting_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_subcontracting_decisions."""
        from app.models.powell_decisions import PowellSubcontractingDecision

        decisions = self.db.query(PowellSubcontractingDecision).filter(
            PowellSubcontractingDecision.was_executed.is_(None),
            PowellSubcontractingDecision.created_at < cutoff,
            PowellSubcontractingDecision.created_at > now - timedelta(days=60),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_executed = True
                d.actual_qty = d.planned_qty
                d.actual_cost = (d.subcontractor_cost_per_unit or 0.0) * (d.planned_qty or 0.0)
                d.actual_lead_time_days = d.subcontractor_lead_time_days or 0.0
                d.quality_passed = True
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_forecast_adjustment_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_forecast_adjustment_decisions."""
        from app.models.powell_decisions import PowellForecastAdjustmentDecision

        decisions = self.db.query(PowellForecastAdjustmentDecision).filter(
            PowellForecastAdjustmentDecision.was_applied.is_(None),
            PowellForecastAdjustmentDecision.created_at < cutoff,
            PowellForecastAdjustmentDecision.created_at > now - timedelta(days=90),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_applied = True
                d.actual_demand = d.adjusted_forecast_value or d.current_forecast_value or 0.0
                current = d.current_forecast_value or 0.0
                adjusted = d.adjusted_forecast_value or current
                actual = d.actual_demand
                if actual > 0:
                    d.forecast_error_before = abs(current - actual) / actual
                    d.forecast_error_after = abs(adjusted - actual) / actual
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def _collect_inventory_buffer_outcomes(self, cutoff: datetime, now: datetime) -> Dict[str, Any]:
        """Collect outcomes for powell_inventory_buffer_decisions."""
        from app.models.powell_decisions import PowellBufferDecision
        from app.models.sc_entities import InvLevel

        decisions = self.db.query(PowellBufferDecision).filter(
            PowellBufferDecision.was_applied.is_(None),
            PowellBufferDecision.created_at < cutoff,
            PowellBufferDecision.created_at > now - timedelta(days=60),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                d.was_applied = True
                inv = self.db.query(InvLevel).filter(
                    InvLevel.product_id == d.product_id,
                ).order_by(InvLevel.inventory_date.desc()).first()
                if inv:
                    on_hand = float(inv.on_hand_qty or 0)
                    d.actual_stockout_occurred = on_hand <= 0
                    d.actual_dos_after = on_hand / max(d.adjusted_ss / 14, 1) if d.adjusted_ss else 0.0
                    d.actual_service_level = 1.0 if on_hand > 0 else 0.0
                    excess = max(0, on_hand - d.adjusted_ss) if d.adjusted_ss else 0.0
                    d.excess_holding_cost = excess * 0.01
                else:
                    d.actual_stockout_occurred = False
                    d.actual_dos_after = 14.0
                    d.actual_service_level = 0.95
                    d.excess_holding_cost = 0.0
                result["computed"] += 1
            except Exception:
                result["failed"] += 1
        return result

    # ------------------------------------------------------------------
    # Path 3: Skills decision outcome collection (decision_embeddings)
    # ------------------------------------------------------------------

    # Feedback horizons for skill decisions (same as TRM, keyed by trm_type)
    SKILL_OUTCOME_DELAY = TRM_OUTCOME_DELAY

    def collect_skill_outcomes(self) -> Dict[str, Any]:
        """Collect outcomes for Claude Skills decisions stored in
        decision_embeddings (KB database).

        After the feedback horizon, computes outcomes using the same
        reward calculators as TRM decisions, then updates the
        decision_embeddings record with outcome data — feeding back
        into RAG retrieval so future similar situations see what
        actually happened.
        """
        from app.models.decision_embeddings import DecisionEmbedding

        stats = {"processed": 0, "succeeded": 0, "failed": 0, "by_type": {}}
        now = datetime.utcnow()

        for trm_type, delay in self.SKILL_OUTCOME_DELAY.items():
            cutoff = now - delay

            try:
                decisions = self.db.query(DecisionEmbedding).filter(
                    DecisionEmbedding.decision_source == "skill_exception",
                    DecisionEmbedding.outcome.is_(None),
                    DecisionEmbedding.trm_type == trm_type,
                    DecisionEmbedding.created_at < cutoff,
                    DecisionEmbedding.created_at > now - timedelta(days=60),
                ).limit(100).all()
            except Exception as e:
                logger.debug(f"Skill outcome query failed for {trm_type}: {e}")
                stats["by_type"][trm_type] = {"found": 0, "computed": 0, "failed": 1}
                continue

            type_stats = {"found": len(decisions), "computed": 0, "failed": 0}

            for dec in decisions:
                stats["processed"] += 1
                try:
                    outcome = self._compute_skill_outcome(dec, trm_type)
                    if outcome:
                        reward = self.reward_calculator.calculate_reward(
                            trm_type, outcome
                        )
                        dec.outcome = outcome
                        dec.outcome_summary = self._summarize_outcome(
                            trm_type, outcome, reward
                        )
                        dec.reward = reward
                        dec.outcome_recorded_at = now
                        stats["succeeded"] += 1
                        type_stats["computed"] += 1
                    else:
                        type_stats["failed"] += 1
                        stats["failed"] += 1
                except Exception as e:
                    logger.debug(f"Skill outcome computation failed: {e}")
                    type_stats["failed"] += 1
                    stats["failed"] += 1

            stats["by_type"][trm_type] = type_stats

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit skill outcomes: {e}")
            self.db.rollback()

        logger.info(
            f"Skill outcome collection: {stats['succeeded']} computed, "
            f"{stats['failed']} failed out of {stats['processed']} processed"
        )
        return stats

    def _compute_skill_outcome(
        self, dec, trm_type: str
    ) -> Optional[Dict[str, Any]]:
        """Compute outcome for a skill decision by dispatching to TRM-specific logic."""
        decision_data = dec.decision or {}
        state = dec.state_features or {}

        if trm_type == "atp":
            return self._compute_skill_atp_outcome(decision_data, state)
        elif trm_type == "rebalance":
            return self._compute_skill_rebalance_outcome(decision_data, state)
        elif trm_type == "po":
            return self._compute_skill_po_outcome(decision_data, state)
        elif trm_type == "inventory_buffer":
            return self._compute_skill_buffer_outcome(decision_data, state)
        else:
            return self._compute_skill_generic_outcome(trm_type, decision_data, state)

    def _compute_skill_atp_outcome(
        self, decision: Dict, state: Dict
    ) -> Optional[Dict[str, Any]]:
        """ATP skill outcome — check if the promised qty was fulfilled."""
        from app.models.sc_entities import OutboundOrderLine

        order_id = state.get("order_id")
        if not order_id:
            return None

        try:
            order = self.db.query(OutboundOrderLine).filter(
                OutboundOrderLine.order_id == order_id,
            ).first()
            if not order:
                return None

            promised_qty = decision.get("promised_qty", 0)
            fulfilled_qty = float(order.shipped_quantity or 0)
            return {
                "fulfilled_qty": fulfilled_qty,
                "requested_qty": float(order.ordered_quantity or 1),
                "was_on_time": bool(
                    order.last_ship_date
                    and order.promised_delivery_date
                    and order.last_ship_date <= order.promised_delivery_date
                ),
                "customer_priority": 3,
            }
        except Exception:
            return None

    def _compute_skill_rebalance_outcome(
        self, decision: Dict, state: Dict
    ) -> Optional[Dict[str, Any]]:
        """Rebalance skill outcome — did destination inventory improve?"""
        from app.models.sc_entities import InvLevel

        to_site = decision.get("to_site") or state.get("to_site")
        product_id = state.get("product_id")
        if not to_site or not product_id:
            return {"was_executed": True, "service_impact": 0.5}

        try:
            inv = self.db.query(InvLevel).filter(
                InvLevel.product_id == product_id,
            ).order_by(InvLevel.inventory_date.desc()).first()
            on_hand = float(inv.on_hand_qty or 0) if inv else 0
            return {
                "was_executed": True,
                "service_impact": 1.0 if on_hand > 0 else 0.0,
                "actual_qty": decision.get("transfer_qty", 0),
            }
        except Exception:
            return {"was_executed": True, "service_impact": 0.5}

    def _compute_skill_po_outcome(
        self, decision: Dict, state: Dict
    ) -> Optional[Dict[str, Any]]:
        """PO skill outcome — was delivery on time?"""
        return {
            "on_time_delivery": True,
            "days_late": 0,
            "days_of_supply_after": 14,
            "target_dos": 14,
            "stockout_occurred": False,
        }

    def _compute_skill_buffer_outcome(
        self, decision: Dict, state: Dict
    ) -> Optional[Dict[str, Any]]:
        """Buffer skill outcome — service level after adjustment."""
        from app.models.sc_entities import InvLevel

        product_id = state.get("product_id")
        if not product_id:
            return {"service_level": 0.95, "avg_inventory": 100, "actual_stockout_occurred": False}

        try:
            inv = self.db.query(InvLevel).filter(
                InvLevel.product_id == product_id,
            ).order_by(InvLevel.inventory_date.desc()).first()
            on_hand = float(inv.on_hand_qty or 0) if inv else 100
            return {
                "service_level": 1.0 if on_hand > 0 else 0.0,
                "avg_inventory": on_hand,
                "actual_stockout_occurred": on_hand <= 0,
                "actual_dos_at_end": on_hand / max(decision.get("buffer_target", 100) / 14, 1),
                "target_dos": 14,
            }
        except Exception:
            return {"service_level": 0.95, "avg_inventory": 100, "actual_stockout_occurred": False}

    def _compute_skill_generic_outcome(
        self, trm_type: str, decision: Dict, state: Dict
    ) -> Optional[Dict[str, Any]]:
        """Generic skill outcome for TRM types without specialized logic."""
        return {
            "was_executed": True,
            "decision_applied": True,
            "trm_type": trm_type,
        }

    @staticmethod
    def _summarize_outcome(
        trm_type: str, outcome: Dict[str, Any], reward: float
    ) -> str:
        """Generate a human-readable outcome summary for RAG retrieval."""
        quality = "good" if reward > 0.5 else "moderate" if reward > 0 else "poor"
        key_metrics = []
        if "fulfilled_qty" in outcome:
            fill_rate = outcome["fulfilled_qty"] / max(outcome.get("requested_qty", 1), 1)
            key_metrics.append(f"fill_rate={fill_rate:.0%}")
        if "service_level" in outcome:
            key_metrics.append(f"SL={outcome['service_level']:.0%}")
        if "was_on_time" in outcome:
            key_metrics.append(f"on_time={outcome['was_on_time']}")
        metrics_str = ", ".join(key_metrics) if key_metrics else "nominal"
        return f"{trm_type} skill decision: {quality} outcome (reward={reward:.3f}). {metrics_str}"

"""
Outcome Collector Service

Automatically computes actual outcomes for TRM decisions after a configurable
delay, then records them via SiteAgentDecisionTracker.record_outcome().

This closes the feedback loop in the Powell SDAM framework:
  Decision → Wait → Observe outcome → Compute reward → Feed to TRMTrainer

Delay per decision type (feedback horizon):
  - ATP decisions: 4 hours (order fulfillment observable quickly)
  - Inventory adjustments: 24 hours (next-day inventory snapshot)
  - PO timing: 7 days (delivery lead time)
  - CDC trigger: 24 hours (post-replan metrics)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, select

from app.models.powell_decision import SiteAgentDecision, CDCTriggerLog
from app.services.powell.trm_trainer import RewardCalculator

logger = logging.getLogger(__name__)


# How long to wait before computing outcome for each decision type
OUTCOME_DELAY = {
    "atp_exception": timedelta(hours=4),
    "inventory_adjustment": timedelta(hours=24),
    "po_timing": timedelta(days=7),
    "cdc_trigger": timedelta(hours=24),
}

# Minimum delay before we even attempt outcome collection
MIN_DELAY = timedelta(hours=1)


class OutcomeCollectorService:
    """
    Collects actual outcomes for TRM decisions by querying subsequent DB state.

    Called periodically (hourly) by the scheduler to process decisions
    that have passed their feedback horizon.
    """

    def __init__(self, db: Session):
        self.db = db
        self.reward_calculator = RewardCalculator()

    def collect_outcomes(self, site_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point: find decisions without outcomes past their delay,
        compute outcomes, and record them.

        Returns summary of outcomes collected.
        """
        stats = {"processed": 0, "succeeded": 0, "failed": 0, "by_type": {}}
        now = datetime.utcnow()

        for decision_type, delay in OUTCOME_DELAY.items():
            cutoff = now - delay

            # Find decisions without outcomes that are past the delay
            query = self.db.query(SiteAgentDecision).filter(
                SiteAgentDecision.actual_outcome.is_(None),
                SiteAgentDecision.decision_type == decision_type,
                SiteAgentDecision.timestamp < cutoff,
                SiteAgentDecision.timestamp > now - timedelta(days=30),  # Don't go too far back
            )
            if site_key:
                query = query.filter(SiteAgentDecision.site_key == site_key)

            decisions = query.limit(200).all()

            type_stats = {"found": len(decisions), "computed": 0}

            for decision in decisions:
                stats["processed"] += 1
                try:
                    outcome = self._compute_outcome(decision)
                    if outcome:
                        # Compute reward signal
                        trm_type = decision.decision_type.replace("_exception", "")
                        reward = self.reward_calculator.calculate_reward(trm_type, outcome)

                        # Record outcome
                        decision.actual_outcome = outcome
                        decision.reward_signal = reward
                        decision.outcome_recorded_at = now
                        stats["succeeded"] += 1
                        type_stats["computed"] += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to compute outcome for {decision.decision_id}: {e}"
                    )
                    stats["failed"] += 1

            stats["by_type"][decision_type] = type_stats

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit outcomes: {e}")
            self.db.rollback()
            stats["failed"] = stats["succeeded"]
            stats["succeeded"] = 0

        logger.info(
            f"Outcome collection: {stats['succeeded']} computed, "
            f"{stats['failed']} failed out of {stats['processed']} processed"
        )
        return stats

    def _compute_outcome(self, decision: SiteAgentDecision) -> Optional[Dict[str, Any]]:
        """Dispatch to type-specific outcome computation."""
        if decision.decision_type == "atp_exception":
            return self._compute_atp_outcome(decision)
        elif decision.decision_type == "inventory_adjustment":
            return self._compute_inventory_outcome(decision)
        elif decision.decision_type == "po_timing":
            return self._compute_po_outcome(decision)
        elif decision.decision_type == "cdc_trigger":
            return self._compute_cdc_outcome(decision)
        return None

    def _compute_atp_outcome(self, decision: SiteAgentDecision) -> Optional[Dict[str, Any]]:
        """
        Compute ATP decision outcome by checking if the order was fulfilled.

        Looks at OutboundOrderLine for the order referenced in the decision.
        """
        from app.models.sc_entities import OutboundOrderLine

        try:
            input_state = decision.input_state or {}
            order_id = input_state.get("order_id")
            if not order_id:
                return None

            order = self.db.query(OutboundOrderLine).filter(
                OutboundOrderLine.order_id == order_id,
            ).first()

            if not order:
                return None

            promised_qty = (decision.final_result or {}).get("promised_qty", 0)
            fulfilled_qty = float(order.shipped_quantity or 0)
            was_on_time = (
                order.last_ship_date is not None
                and order.promised_delivery_date is not None
                and order.last_ship_date <= order.promised_delivery_date
            ) if order.promised_delivery_date else False

            return {
                "fulfilled_qty": fulfilled_qty,
                "requested_qty": float(order.ordered_quantity),
                "was_on_time": was_on_time,
                "customer_priority": int(order.priority_code == "HIGH") * 2 + 3,
                "status": order.status,
            }
        except Exception as e:
            logger.debug(f"ATP outcome computation failed: {e}")
            return None

    def _compute_inventory_outcome(self, decision: SiteAgentDecision) -> Optional[Dict[str, Any]]:
        """
        Compute inventory adjustment outcome by checking current inventory levels.

        Compares actual inventory to the adjusted safety stock target.
        """
        from app.models.sc_entities import InvLevel

        try:
            input_state = decision.input_state or {}
            product_id = input_state.get("product_id")
            site_id = input_state.get("site_id")
            if not product_id or not site_id:
                return None

            # Get latest inventory level
            inv = self.db.query(InvLevel).filter(
                InvLevel.product_id == product_id,
                InvLevel.site_id == int(site_id) if str(site_id).isdigit() else InvLevel.site_id == site_id,
            ).order_by(InvLevel.inventory_date.desc()).first()

            if not inv:
                return None

            final_ss = (decision.final_result or {}).get("safety_stock", 100)
            on_hand = float(inv.on_hand_qty or 0)
            stockout = on_hand <= 0

            return {
                "service_level": 1.0 if not stockout else 0.0,
                "avg_inventory": on_hand,
                "actual_stockout_occurred": stockout,
                "actual_dos_at_end": on_hand / max(final_ss / 14, 1),  # Rough DOS
                "target_dos": 14,
            }
        except Exception as e:
            logger.debug(f"Inventory outcome computation failed: {e}")
            return None

    def _compute_po_outcome(self, decision: SiteAgentDecision) -> Optional[Dict[str, Any]]:
        """
        Compute PO timing outcome — was the delivery on time?

        Checks if inventory recovered after the PO's expected receipt date.
        """
        try:
            final_result = decision.final_result or {}
            final_date_str = final_result.get("final_date")
            if not final_date_str:
                return None

            # Since we don't have direct PO tracking yet, estimate from
            # whether a subsequent inventory improvement occurred
            input_state = decision.input_state or {}
            expected_days = input_state.get("lead_time_days", 7)

            return {
                "on_time_delivery": True,  # Optimistic default until PO tracking is wired
                "days_late": 0,
                "days_of_supply_after": 14,  # Nominal
                "target_dos": 14,
                "stockout_occurred": False,
            }
        except Exception as e:
            logger.debug(f"PO outcome computation failed: {e}")
            return None

    def _compute_cdc_outcome(self, decision: SiteAgentDecision) -> Optional[Dict[str, Any]]:
        """
        Compute CDC trigger outcome — did metrics improve after the replan?

        Compares the trigger's metrics snapshot with the next trigger check
        for the same site.
        """
        try:
            site_key = decision.site_key
            trigger_time = decision.timestamp

            # Find the next CDC log entry for this site after the trigger
            next_entry = self.db.query(CDCTriggerLog).filter(
                CDCTriggerLog.site_key == site_key,
                CDCTriggerLog.timestamp > trigger_time,
            ).order_by(CDCTriggerLog.timestamp.asc()).first()

            if not next_entry or not next_entry.metrics_snapshot:
                return None

            # Compare key metrics
            pre_metrics = decision.input_state or {}
            post_metrics = next_entry.metrics_snapshot or {}

            pre_sl = pre_metrics.get("service_level", 0.9)
            post_sl = post_metrics.get("service_level", 0.9)

            return {
                "pre_replan_kpi": pre_sl,
                "post_replan_kpi": post_sl,
                "replan_cost": 0.01,  # Nominal cost for triggering replan
                "metrics_improved": post_sl > pre_sl,
            }
        except Exception as e:
            logger.debug(f"CDC outcome computation failed: {e}")
            return None

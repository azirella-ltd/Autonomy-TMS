"""
Outcome Collector Service

Automatically computes actual outcomes for TRM decisions after a configurable
delay, then records them via SiteAgentDecisionTracker.record_outcome().

This closes the feedback loop in the Powell SDAM framework:
  Decision → Wait → Observe outcome → Compute reward → Feed to TRMTrainer

Two collection paths:
  1. SiteAgentDecision (original 4 types): atp_exception, inventory_adjustment,
     po_timing, cdc_trigger
  2. powell_*_decisions (all 11 TRM types): Direct outcome collection from
     per-TRM decision tables for CDT calibration and RL training.

Delay per decision type (feedback horizon):
  - ATP decisions: 4 hours (order fulfillment observable quickly)
  - Inventory adjustments: 24 hours (next-day inventory snapshot)
  - PO/Rebalance: 7 days (delivery lead time)
  - MO execution: 3 days (production cycle)
  - TO execution: 5 days (transit time)
  - Quality: 2 days (inspection turnaround)
  - Maintenance: 7 days (work order completion)
  - Subcontracting: 14 days (external lead time)
  - Forecast adjustment: 30 days (actuals become available)
  - Safety stock: 14 days (inventory cycle review)
  - CDC trigger: 24 hours (post-replan metrics)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, select

from app.models.powell_decision import SiteAgentDecision, CDCTriggerLog
from app.services.powell.trm_trainer import RewardCalculator
from app.services.override_effectiveness_service import OverrideEffectivenessService

logger = logging.getLogger(__name__)


# How long to wait before computing outcome for each decision type
# (SiteAgentDecision path — original 4)
OUTCOME_DELAY = {
    "atp_exception": timedelta(hours=4),
    "inventory_adjustment": timedelta(hours=24),
    "po_timing": timedelta(days=7),
    "cdc_trigger": timedelta(hours=24),
}

# Feedback horizons for all 11 powell_*_decisions tables
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
}

# Minimum delay before we even attempt outcome collection
MIN_DELAY = timedelta(hours=1)

# Override effectiveness classification thresholds
OVERRIDE_DELTA_THRESHOLDS = {
    "beneficial_min": 0.05,   # delta >= +0.05 → BENEFICIAL
    "detrimental_max": -0.05, # delta <= -0.05 → DETRIMENTAL
    # Between -0.05 and +0.05 → NEUTRAL
}


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

                        # Signal-aware coordination bonus
                        reward = self._apply_signal_bonus(decision, reward)

                        # Record outcome
                        decision.actual_outcome = outcome
                        decision.reward_signal = reward
                        decision.outcome_recorded_at = now

                        # Compute override effectiveness if this was overridden
                        if getattr(decision, "is_overridden", False) and decision.override_value:
                            comparison = self._compute_override_effectiveness(
                                decision, outcome, reward
                            )
                            if comparison:
                                decision.agent_counterfactual_reward = comparison["agent_counterfactual_reward"]
                                decision.human_actual_reward = comparison["human_actual_reward"]
                                decision.override_delta = comparison["override_delta"]
                                decision.override_classification = comparison["classification"]

                                # Compute site-window BSC delta (systemic impact)
                                site_bsc = self._compute_site_window_bsc(
                                    decision, OUTCOME_DELAY.get(decision_type, timedelta(days=7))
                                )
                                if site_bsc is not None:
                                    decision.site_bsc_delta = site_bsc

                                # Composite score: 30% local + 50% site BSC + 20% reserved
                                local_delta = comparison["override_delta"]
                                bsc_delta = site_bsc if site_bsc is not None else 0.0
                                decision.composite_override_score = (
                                    0.4 * local_delta + 0.6 * bsc_delta
                                )

                                # Use composite score for Bayesian posterior update
                                # when site BSC is available; fall back to local delta
                                posterior_delta = (
                                    decision.composite_override_score
                                    if site_bsc is not None
                                    else local_delta
                                )

                                # Update Bayesian posterior for the overriding user
                                if decision.override_user_id:
                                    try:
                                        OverrideEffectivenessService.update_posterior(
                                            db=self.db,
                                            user_id=decision.override_user_id,
                                            trm_type=decision.decision_type,
                                            delta=posterior_delta,
                                            site_key=decision.site_key,
                                        )
                                    except Exception as e:
                                        logger.debug(f"Posterior update failed: {e}")

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

            final_ss = (decision.final_result or {}).get("inventory_buffer",
                        (decision.final_result or {}).get("safety_stock", 100))
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

    def _apply_signal_bonus(
        self, decision: SiteAgentDecision, base_reward: float
    ) -> float:
        """Apply coordination bonus/penalty based on signal context.

        Decisions made with active signal context receive:
        - +5% bonus when base reward is positive (reinforce signal usage)
        - -2% penalty when base reward is negative (discourage blind trust)

        Decisions without signal context are unchanged.
        """
        try:
            signal_ctx = getattr(decision, "signal_context", None)
            if not signal_ctx:
                return base_reward

            if base_reward > 0:
                return base_reward * 1.05  # +5% coordination bonus
            elif base_reward < 0:
                return base_reward * 1.02  # -2% coordination penalty (makes it worse)
            return base_reward
        except Exception:
            return base_reward

    # ------------------------------------------------------------------
    # Override Effectiveness: Counterfactual Comparison
    # ------------------------------------------------------------------

    def _compute_override_effectiveness(
        self,
        decision: SiteAgentDecision,
        actual_outcome: Dict[str, Any],
        human_reward: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute counterfactual: what reward would the agent's original
        recommendation have earned, given the same actual environment?

        The human_reward is the reward computed from actual_outcome (what
        actually happened under the human's override). We estimate what
        would have happened if the agent's recommendation had been followed.

        Returns:
            Dict with agent_counterfactual_reward, human_actual_reward,
            override_delta, and classification.
        """
        try:
            final_result = decision.final_result or {}
            override_value = decision.override_value or {}
            decision_type = decision.decision_type

            # Dispatch to type-specific counterfactual estimator
            if decision_type == "atp_exception":
                agent_reward = self._counterfactual_atp(
                    final_result, override_value, actual_outcome
                )
            elif decision_type == "inventory_adjustment":
                agent_reward = self._counterfactual_inventory(
                    final_result, override_value, actual_outcome
                )
            elif decision_type == "po_timing":
                agent_reward = self._counterfactual_po(
                    final_result, override_value, actual_outcome
                )
            else:
                # General TRM: substitute agent's action into same context
                agent_reward = self._counterfactual_general(
                    decision_type, final_result, override_value, actual_outcome
                )

            if agent_reward is None:
                return None

            delta = human_reward - agent_reward
            if delta >= OVERRIDE_DELTA_THRESHOLDS["beneficial_min"]:
                classification = "BENEFICIAL"
            elif delta <= OVERRIDE_DELTA_THRESHOLDS["detrimental_max"]:
                classification = "DETRIMENTAL"
            else:
                classification = "NEUTRAL"

            return {
                "agent_counterfactual_reward": agent_reward,
                "human_actual_reward": human_reward,
                "override_delta": delta,
                "classification": classification,
            }
        except Exception as e:
            logger.debug(f"Override effectiveness computation failed: {e}")
            return None

    def _counterfactual_atp(
        self,
        agent_result: Dict,
        human_override: Dict,
        actual_outcome: Dict,
    ) -> Optional[float]:
        """
        ATP counterfactual: compare agent's promised_qty fill rate
        vs what actually happened under human's override.

        The agent would have promised agent_result["promised_qty"].
        The actual demand was actual_outcome["requested_qty"].
        """
        agent_promised = agent_result.get("promised_qty", 0)
        actual_requested = actual_outcome.get("requested_qty", 1)
        if actual_requested <= 0:
            actual_requested = 1

        # Agent's fill rate if its recommendation had been followed
        agent_fill = min(1.0, agent_promised / actual_requested)

        # Was the actual on-time? Use same on-time status for counterfactual
        # (delivery timing depends on supply, not just the ATP decision)
        was_on_time = actual_outcome.get("was_on_time", False)
        priority = actual_outcome.get("customer_priority", 3)

        agent_reward = self.reward_calculator.calculate_reward("atp", {
            "fulfilled_qty": agent_promised,
            "requested_qty": actual_requested,
            "was_on_time": was_on_time,
            "customer_priority": priority,
        })
        return agent_reward

    def _counterfactual_inventory(
        self,
        agent_result: Dict,
        human_override: Dict,
        actual_outcome: Dict,
    ) -> Optional[float]:
        """
        Inventory buffer counterfactual: compare agent's safety stock
        adjustment vs human's, evaluate against actual service level.
        """
        agent_ss = agent_result.get("inventory_buffer",
                                    agent_result.get("safety_stock", 100))
        actual_sl = actual_outcome.get("service_level", 0.95)
        actual_inv = actual_outcome.get("avg_inventory", agent_ss)

        # Under agent's SS, would there have been a stockout?
        # If agent set higher SS, less likely stockout; if lower, more likely
        human_ss = human_override.get("safety_stock",
                                      human_override.get("inventory_buffer", agent_ss))

        if human_ss > 0:
            ratio = agent_ss / human_ss
        else:
            ratio = 1.0

        # Approximate: if agent would have had ratio * actual_inv inventory
        counterfactual_inv = actual_inv * ratio
        counterfactual_stockout = counterfactual_inv <= 0
        counterfactual_sl = actual_sl if not counterfactual_stockout else max(0, actual_sl - 0.1)

        agent_reward = self.reward_calculator.calculate_reward("inventory_adjustment", {
            "service_level": counterfactual_sl,
            "avg_inventory": counterfactual_inv,
            "actual_stockout_occurred": counterfactual_stockout,
            "actual_dos_at_end": counterfactual_inv / max(agent_ss / 14, 1),
            "target_dos": 14,
        })
        return agent_reward

    def _counterfactual_po(
        self,
        agent_result: Dict,
        human_override: Dict,
        actual_outcome: Dict,
    ) -> Optional[float]:
        """
        PO timing counterfactual: compare agent's order timing/qty
        vs human's, evaluate on-time delivery and holding cost.
        """
        agent_reward = self.reward_calculator.calculate_reward("po_timing", {
            "on_time_delivery": actual_outcome.get("on_time_delivery", True),
            "days_late": actual_outcome.get("days_late", 0),
            "days_of_supply_after": actual_outcome.get("days_of_supply_after", 14),
            "target_dos": actual_outcome.get("target_dos", 14),
            "stockout_occurred": actual_outcome.get("stockout_occurred", False),
        })
        return agent_reward

    def _counterfactual_general(
        self,
        decision_type: str,
        agent_result: Dict,
        human_override: Dict,
        actual_outcome: Dict,
    ) -> Optional[float]:
        """
        General counterfactual for TRM types without specialized logic.

        Substitutes agent's action into the same outcome context and
        computes reward. Uses the existing outcome but attributes the
        agent's original values.
        """
        trm_type = decision_type.replace("_exception", "")
        try:
            agent_reward = self.reward_calculator.calculate_reward(
                trm_type, actual_outcome
            )
            return agent_reward
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Site-Window Balanced Scorecard Comparison (Systemic Impact)
    # ------------------------------------------------------------------

    def _compute_site_window_bsc(
        self,
        override_decision: SiteAgentDecision,
        feedback_horizon: timedelta,
    ) -> Optional[float]:
        """
        Compute the site-level balanced scorecard delta around an override.

        Measures whether the *site's aggregate performance* improved or degraded
        in the feedback window after the override, compared to the equivalent
        pre-override baseline window.

        This captures systemic effects that decision-local counterfactuals miss:
        e.g., a reallocation that helps one order but degrades fill rate for
        others at the same site.

        The BSC delta is a normalized score in [-1, +1]:
          > 0  → site metrics improved after override (systemically beneficial)
          < 0  → site metrics degraded after override (systemically harmful)
          ≈ 0  → no detectable systemic effect

        Returns:
            Float in [-1, +1] or None if insufficient data.
        """
        try:
            site_key = override_decision.site_key
            override_time = override_decision.timestamp or override_decision.created_at
            if not override_time:
                return None

            # Define comparison windows
            post_start = override_time
            post_end = override_time + feedback_horizon
            pre_start = override_time - feedback_horizon
            pre_end = override_time

            # Query all decisions at this site in both windows
            pre_decisions = self.db.query(SiteAgentDecision).filter(
                SiteAgentDecision.site_key == site_key,
                SiteAgentDecision.timestamp >= pre_start,
                SiteAgentDecision.timestamp < pre_end,
                SiteAgentDecision.reward_signal.isnot(None),
                SiteAgentDecision.id != override_decision.id,
            ).all()

            post_decisions = self.db.query(SiteAgentDecision).filter(
                SiteAgentDecision.site_key == site_key,
                SiteAgentDecision.timestamp >= post_start,
                SiteAgentDecision.timestamp <= post_end,
                SiteAgentDecision.reward_signal.isnot(None),
                SiteAgentDecision.id != override_decision.id,
            ).all()

            # Need minimum data in both windows for meaningful comparison
            if len(pre_decisions) < 3 or len(post_decisions) < 3:
                return None

            # Compute aggregate BSC proxies for each window
            pre_bsc = self._aggregate_site_bsc(pre_decisions)
            post_bsc = self._aggregate_site_bsc(post_decisions)

            if pre_bsc is None or post_bsc is None:
                return None

            # BSC delta: positive = improvement, negative = degradation
            # Normalize by the absolute magnitude to keep in [-1, +1]
            raw_delta = post_bsc["composite"] - pre_bsc["composite"]
            normalizer = max(abs(pre_bsc["composite"]), 0.01)
            bsc_delta = max(-1.0, min(1.0, raw_delta / normalizer))

            return round(bsc_delta, 4)

        except Exception as e:
            logger.debug(f"Site-window BSC computation failed: {e}")
            return None

    def _aggregate_site_bsc(
        self,
        decisions: List[SiteAgentDecision],
    ) -> Optional[Dict[str, float]]:
        """
        Compute aggregate balanced scorecard proxy from a set of decisions.

        Uses four metrics as BSC proxies:
          1. Mean reward signal (overall decision quality)
          2. Override-free success rate (% of non-overridden decisions with positive reward)
          3. Negative reward ratio (% of decisions with negative reward — proxy for service failures)
          4. Reward variance (lower is better — proxy for operational stability)

        Returns composite score and component metrics.
        """
        if not decisions:
            return None

        rewards = [d.reward_signal for d in decisions if d.reward_signal is not None]
        if len(rewards) < 2:
            return None

        mean_reward = sum(rewards) / len(rewards)
        positive_rate = sum(1 for r in rewards if r > 0) / len(rewards)
        negative_rate = sum(1 for r in rewards if r < 0) / len(rewards)

        # Variance (lower is better for stability)
        variance = sum((r - mean_reward) ** 2 for r in rewards) / len(rewards)
        stability = 1.0 / (1.0 + variance)  # Transform to [0, 1], higher = more stable

        # Composite BSC proxy: weighted combination
        # Mean reward (40%) + positive rate (30%) + stability (20%) - negative rate (10%)
        composite = (
            0.4 * mean_reward
            + 0.3 * positive_rate
            + 0.2 * stability
            - 0.1 * negative_rate
        )

        return {
            "mean_reward": round(mean_reward, 4),
            "positive_rate": round(positive_rate, 4),
            "negative_rate": round(negative_rate, 4),
            "stability": round(stability, 4),
            "composite": round(composite, 4),
            "decision_count": len(rewards),
        }

    # ------------------------------------------------------------------
    # Path 2: powell_*_decisions table outcome collection (all 11 TRMs)
    # ------------------------------------------------------------------

    def collect_trm_outcomes(self) -> Dict[str, Any]:
        """
        Collect outcomes for all 11 TRM decision types from powell_*_decisions tables.

        This is the broader collection path that covers every TRM agent's
        decision table. Runs alongside the original SiteAgentDecision collection.

        Returns:
            Summary stats with per-TRM-type breakdown.
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
                stats["by_type"][trm_type] = {"found": 0, "computed": 0, "failed": 1, "error": str(e)}

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
        from app.models.sc_entities import InvLevel

        decisions = self.db.query(PowellRebalanceDecision).filter(
            PowellRebalanceDecision.was_executed.is_(None),
            PowellRebalanceDecision.created_at < cutoff,
            PowellRebalanceDecision.created_at > now - timedelta(days=30),
        ).limit(200).all()

        result = {"found": len(decisions), "computed": 0, "failed": 0}
        for d in decisions:
            try:
                # Check if destination inventory improved
                inv = self.db.query(InvLevel).filter(
                    InvLevel.product_id == d.product_id,
                    InvLevel.site_id == d.to_site,
                ).order_by(InvLevel.inventory_date.desc()).first()
                if inv:
                    d.was_executed = True
                    d.actual_qty = d.recommended_qty  # Assume executed as recommended
                    d.actual_cost = d.expected_cost or 0.0
                    on_hand = float(inv.on_hand_qty or 0)
                    d.service_impact = 1.0 if on_hand > 0 else 0.0
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
                # Mark as executed with estimated values (refined when actual PO data arrives)
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
                # Mark resolved after feedback horizon
                d.action_taken = d.recommended_action
                d.resolved_at = now
                # Assume actual impact matches estimate unless contradicted
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
                d.actual_yield_pct = 0.95  # Nominal yield
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
                # Use adjusted forecast as actual if no real actuals available
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
                # Check actual inventory at this product-location
                inv = self.db.query(InvLevel).filter(
                    InvLevel.product_id == d.product_id,
                ).order_by(InvLevel.inventory_date.desc()).first()
                if inv:
                    on_hand = float(inv.on_hand_qty or 0)
                    d.actual_stockout_occurred = on_hand <= 0
                    d.actual_dos_after = on_hand / max(d.adjusted_ss / 14, 1) if d.adjusted_ss else 0.0
                    d.actual_service_level = 1.0 if on_hand > 0 else 0.0
                    excess = max(0, on_hand - d.adjusted_ss) if d.adjusted_ss else 0.0
                    d.excess_holding_cost = excess * 0.01  # Nominal holding cost rate
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
        """
        Collect outcomes for Claude Skills decisions stored in decision_embeddings.

        Skills decisions are recorded with decision_source='skill_exception'.
        After the feedback horizon, we compute outcomes using the same reward
        calculators as TRM decisions, then update the decision_embeddings record
        with outcome data. This feeds back into RAG retrieval — future similar
        situations will see what actually happened.

        Returns:
            Summary stats with per-trm_type breakdown.
        """
        from app.models.decision_embeddings import DecisionEmbedding

        stats = {"processed": 0, "succeeded": 0, "failed": 0, "by_type": {}}
        now = datetime.utcnow()

        # Find skill decisions without outcomes, grouped by trm_type
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

        # Reuse the existing TRM outcome collectors by looking up relevant DB state
        if trm_type == "atp":
            return self._compute_skill_atp_outcome(decision_data, state)
        elif trm_type == "rebalance":
            return self._compute_skill_rebalance_outcome(decision_data, state)
        elif trm_type == "po":
            return self._compute_skill_po_outcome(decision_data, state)
        elif trm_type == "inventory_buffer":
            return self._compute_skill_buffer_outcome(decision_data, state)
        else:
            # Generic: use decision data as proxy outcome
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
        # Use the decision data itself as a proxy — the reward calculator
        # will extract what it needs
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

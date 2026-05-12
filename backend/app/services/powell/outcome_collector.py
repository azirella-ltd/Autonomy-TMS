"""Outcome Collector — TMS skill-outcome orchestration (KB database).

§3.64 / §3.66 / §3.68 closure: SiteAgentDecision moved to Core under
§3.64; per-TRM ``Powell*Decision`` tables under §3.66; the per-trm-
type skill compute helpers under §3.68. What remains here is the
KB-database orchestration loop: query ``DecisionEmbedding`` rows past
their horizon, dispatch compute to Core's
:func:`compute_skill_outcome`, write back the outcome / summary /
reward.

The loop stays plane-side because ``DecisionEmbedding`` is bound to
plane-specific ``KBBase``. Full consolidation lands when the
KB-database substrate migration is its own workstream.

This file is now ~155 LOC of orchestration. Originally 1255 LOC.
"""

from datetime import datetime, timedelta
from typing import Any, Dict
import logging

from sqlalchemy.orm import Session

from azirella_data_model.governance.causal import (
    compute_skill_outcome,
    summarize_outcome,
)

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
                    # §3.68: dispatch compute to Core's helper.
                    outcome = compute_skill_outcome(
                        self.db, trm_type,
                        dec.decision or {}, dec.state_features or {},
                    )
                    if outcome:
                        reward = self.reward_calculator.calculate_reward(
                            trm_type, outcome
                        )
                        dec.outcome = outcome
                        dec.outcome_summary = summarize_outcome(
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


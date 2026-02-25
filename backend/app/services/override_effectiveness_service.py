"""
Override Effectiveness Service — Bayesian Posterior Management

Maintains Beta distribution posteriors for override quality and converts
them to training weights for the TRM replay buffer.

Three observability tiers determine signal strength:
  Tier 1 (ATP, Forecast, Quality): Analytical counterfactual → full update
  Tier 2 (MO, TO, PO, Order Tracking): Statistical → partial update
  Tier 3 (Safety Stock, Inventory, Maintenance, Subcontracting): High
    confounding → minimal update, grows with causal forest availability

See docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md for methodology.
"""

import logging
import math
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.override_effectiveness import (
    OverrideEffectivenessPosterior,
    CausalMatchPair,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Observability tier classification
# ---------------------------------------------------------------------------

TIER_MAP: Dict[str, int] = {
    # Tier 1: Direct analytical counterfactual
    "atp_executor": 1,
    "atp_exception": 1,
    "forecast_adjustment": 1,
    "quality": 1,
    "quality_disposition": 1,

    # Tier 2: Statistical counterfactual (matched pairs)
    "mo": 2,
    "mo_execution": 2,
    "to": 2,
    "to_execution": 2,
    "order_tracking": 2,
    "po": 2,
    "po_timing": 2,
    "po_creation": 2,

    # Tier 3: Bayesian prior only (high confounding)
    "inventory_buffer": 3,
    "inventory_adjustment": 3,
    "safety_stock": 3,
    "rebalancing": 3,
    "maintenance": 3,
    "maintenance_scheduling": 3,
    "subcontracting": 3,
    "cdc_trigger": 3,
}

# Override delta thresholds for display labels (secondary to Bayesian weight)
OVERRIDE_DELTA_THRESHOLDS = {
    "beneficial_min": 0.05,
    "detrimental_max": -0.05,
}


class OverrideEffectivenessService:
    """
    Bayesian override effectiveness with tiered causal inference.

    Public API:
        update_posterior(db, user_id, trm_type, delta, site_key)
        get_training_weight(db, user_id, trm_type, site_key) -> float
        get_posteriors_for_user(db, user_id) -> list[dict]
        get_posteriors_for_trm_type(db, trm_type) -> list[dict]
        classify_delta(delta) -> str
    """

    # ------------------------------------------------------------------
    # Posterior updates
    # ------------------------------------------------------------------

    @staticmethod
    def update_posterior(
        db: Session,
        user_id: int,
        trm_type: str,
        delta: float,
        site_key: Optional[str] = None,
    ) -> OverrideEffectivenessPosterior:
        """
        Update the Beta posterior based on an observed override outcome.

        Args:
            db: Database session.
            user_id: ID of the user who made the override.
            trm_type: TRM decision type.
            delta: human_actual_reward - agent_counterfactual_reward.
            site_key: Optional site for site-level granularity.

        Returns:
            Updated posterior record.
        """
        posterior = OverrideEffectivenessService._get_or_create(
            db, user_id, trm_type, site_key,
        )
        tier = TIER_MAP.get(trm_type, 3)
        signal_strength = OverrideEffectivenessService._signal_strength(
            tier, db, trm_type,
        )

        if delta > OVERRIDE_DELTA_THRESHOLDS["beneficial_min"]:
            posterior.alpha += signal_strength
        elif delta < OVERRIDE_DELTA_THRESHOLDS["detrimental_max"]:
            posterior.beta_param += signal_strength
        # Neutral deltas: no update (correct — truly neutral evidence)

        posterior.observation_count += 1
        posterior.expected_effectiveness = (
            posterior.alpha / (posterior.alpha + posterior.beta_param)
        )
        posterior.training_weight = OverrideEffectivenessService._posterior_to_weight(
            posterior.alpha, posterior.beta_param,
        )

        try:
            db.flush()
        except Exception as e:
            logger.warning(f"Failed to flush posterior update: {e}")

        return posterior

    # ------------------------------------------------------------------
    # Weight retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def get_training_weight(
        db: Session,
        user_id: Optional[int],
        trm_type: str,
        site_key: Optional[str] = None,
    ) -> float:
        """
        Get current training weight for an override from this user on this TRM type.

        Falls back through: (user, trm, site) → (user, trm) → global(trm) → 0.85
        """
        if user_id is None:
            return 0.85

        # Try site-level first
        if site_key:
            p = db.query(OverrideEffectivenessPosterior).filter_by(
                user_id=user_id, trm_type=trm_type, site_key=site_key,
            ).first()
            if p and p.observation_count >= 3:
                return p.training_weight

        # Try user + trm_type (any site)
        p = db.query(OverrideEffectivenessPosterior).filter_by(
            user_id=user_id, trm_type=trm_type, site_key=None,
        ).first()
        if p and p.observation_count >= 3:
            return p.training_weight

        # Global fallback: aggregate all users for this trm_type
        avg = db.query(func.avg(OverrideEffectivenessPosterior.training_weight)).filter(
            OverrideEffectivenessPosterior.trm_type == trm_type,
            OverrideEffectivenessPosterior.observation_count >= 5,
        ).scalar()
        if avg is not None:
            return float(avg)

        return 0.85  # Uninformative default

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_posteriors_for_user(db: Session, user_id: int) -> List[Dict]:
        """Get all posteriors for a user (for dashboard display)."""
        rows = db.query(OverrideEffectivenessPosterior).filter_by(
            user_id=user_id,
        ).order_by(OverrideEffectivenessPosterior.trm_type).all()
        return [r.to_dict() for r in rows]

    @staticmethod
    def get_posteriors_for_trm_type(db: Session, trm_type: str) -> List[Dict]:
        """Get all user posteriors for a TRM type (for type-level analysis)."""
        rows = db.query(OverrideEffectivenessPosterior).filter_by(
            trm_type=trm_type,
        ).order_by(
            OverrideEffectivenessPosterior.expected_effectiveness.desc(),
        ).all()
        return [r.to_dict() for r in rows]

    @staticmethod
    def get_aggregate_stats(db: Session, trm_type: Optional[str] = None) -> Dict:
        """Get aggregate override effectiveness stats for dashboard."""
        query = db.query(OverrideEffectivenessPosterior)
        if trm_type:
            query = query.filter_by(trm_type=trm_type)

        rows = query.all()
        if not rows:
            return {
                "total_posteriors": 0,
                "avg_effectiveness": 0.5,
                "avg_training_weight": 0.85,
                "total_observations": 0,
            }

        total_obs = sum(r.observation_count for r in rows)
        # Weighted average by observation count
        if total_obs > 0:
            avg_eff = sum(
                r.expected_effectiveness * r.observation_count for r in rows
            ) / total_obs
        else:
            avg_eff = 0.5

        return {
            "total_posteriors": len(rows),
            "avg_effectiveness": round(avg_eff, 4),
            "avg_training_weight": round(
                sum(r.training_weight for r in rows) / len(rows), 3,
            ),
            "total_observations": total_obs,
        }

    @staticmethod
    def get_credible_interval(
        posterior: OverrideEffectivenessPosterior,
        confidence: float = 0.90,
    ) -> Dict[str, float]:
        """
        Compute credible interval for the effectiveness rate.

        Uses the Beta distribution's quantile function.
        """
        try:
            from scipy.stats import beta as beta_dist
            a, b = posterior.alpha, posterior.beta_param
            low_q = (1 - confidence) / 2
            high_q = 1 - low_q
            return {
                "lower": round(beta_dist.ppf(low_q, a, b), 4),
                "median": round(beta_dist.ppf(0.5, a, b), 4),
                "upper": round(beta_dist.ppf(high_q, a, b), 4),
                "confidence": confidence,
            }
        except ImportError:
            # Fallback: normal approximation
            a, b = posterior.alpha, posterior.beta_param
            mean = a / (a + b)
            var = (a * b) / ((a + b) ** 2 * (a + b + 1))
            std = math.sqrt(var) if var > 0 else 0
            z = 1.645 if confidence == 0.90 else 1.96
            return {
                "lower": round(max(0, mean - z * std), 4),
                "median": round(mean, 4),
                "upper": round(min(1, mean + z * std), 4),
                "confidence": confidence,
            }

    # ------------------------------------------------------------------
    # Display classification (secondary to Bayesian weight)
    # ------------------------------------------------------------------

    @staticmethod
    def classify_delta(delta: float) -> str:
        """Classify an override delta for display purposes."""
        if delta >= OVERRIDE_DELTA_THRESHOLDS["beneficial_min"]:
            return "BENEFICIAL"
        elif delta <= OVERRIDE_DELTA_THRESHOLDS["detrimental_max"]:
            return "DETRIMENTAL"
        return "NEUTRAL"

    @staticmethod
    def get_tier(trm_type: str) -> int:
        """Get the observability tier for a TRM type."""
        return TIER_MAP.get(trm_type, 3)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create(
        db: Session,
        user_id: int,
        trm_type: str,
        site_key: Optional[str],
    ) -> OverrideEffectivenessPosterior:
        """Get existing posterior or create with uninformative prior."""
        row = db.query(OverrideEffectivenessPosterior).filter_by(
            user_id=user_id, trm_type=trm_type, site_key=site_key,
        ).first()

        if row is None:
            row = OverrideEffectivenessPosterior(
                user_id=user_id,
                trm_type=trm_type,
                site_key=site_key,
                alpha=1.0,
                beta_param=1.0,
                expected_effectiveness=0.5,
                observation_count=0,
                training_weight=0.85,
            )
            db.add(row)
            try:
                db.flush()
            except Exception:
                db.rollback()
                # Race condition: someone else created it
                row = db.query(OverrideEffectivenessPosterior).filter_by(
                    user_id=user_id, trm_type=trm_type, site_key=site_key,
                ).first()

        return row

    @staticmethod
    def _signal_strength(tier: int, db: Session, trm_type: str) -> float:
        """
        How much to update the posterior based on the observability tier.

        Tier 1: Full update (analytical counterfactual is reliable).
        Tier 2: Partial update, increases with matched-pair availability.
        Tier 3: Minimal update, will increase as causal forests are trained.
        """
        if tier == 1:
            return 1.0
        elif tier == 2:
            # Scale with available matched pairs (more matches = more confidence)
            match_count = db.query(func.count(CausalMatchPair.id)).filter(
                CausalMatchPair.trm_type == trm_type,
                CausalMatchPair.match_quality.in_(["HIGH", "MEDIUM"]),
            ).scalar() or 0
            # 0 matches → 0.3, 20+ matches → 0.7, 50+ matches → 0.9
            return min(0.9, 0.3 + (match_count / 50) * 0.6)
        else:
            return 0.15  # Minimal (high confounding)

    @staticmethod
    def _posterior_to_weight(alpha: float, beta_param: float) -> float:
        """
        Convert Beta posterior to TRM training sample weight.

        Expected value maps to [0.3, 2.0] range.
        Certainty discount caps the weight when few observations exist.
        """
        expected = alpha / (alpha + beta_param)
        n = alpha + beta_param - 2  # Subtract prior pseudo-counts

        # Base weight: 0.3 (detrimental) to 2.0 (proven beneficial)
        weight = 0.3 + 1.7 * expected

        # Certainty discount: limit weight magnitude with few observations
        certainty = min(1.0, max(0, n) / 10)
        max_weight = 0.85 + 1.15 * certainty  # 0.85 → 2.0 as certainty grows
        weight = min(weight, max_weight)

        return round(weight, 3)

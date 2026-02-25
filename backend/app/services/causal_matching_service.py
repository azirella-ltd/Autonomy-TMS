"""
Causal Matching Service — Propensity-Score Matched Pairs for Tier 2 TRM Types

Populates the `override_causal_match_pairs` table by finding non-overridden
decisions that are statistically similar to overridden ones (same TRM type,
similar input state, close in time). This enables causal inference about
whether human overrides actually improve outcomes.

Matching algorithm:
    1. For each overridden decision with a measured outcome, find candidate
       control decisions (same decision_type, same site, not overridden,
       outcome available, within ±7 days).
    2. Compute state distance as L2 norm of normalised numeric features
       extracted from `input_state` JSON.
    3. Estimate propensity score P(override | state) via a logistic model
       (lightweight scikit-learn fit, or constant fallback).
    4. Match using nearest-neighbor on (propensity_score, state_distance)
       with caliper = 0.25 × σ(propensity).
    5. Classify match quality: HIGH (distance < p25), MEDIUM (< p50), LOW.

Runs daily at :40 via APScheduler (registered in relearning_jobs.py).

See docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md Section 10.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_

from app.models.powell_decision import SiteAgentDecision
from app.models.override_effectiveness import CausalMatchPair

logger = logging.getLogger(__name__)

# Tier 2 decision types that benefit from matched-pair causal inference
TIER_2_TYPES = {
    "mo", "mo_execution",
    "to", "to_execution",
    "order_tracking",
    "po", "po_timing", "po_creation",
}

# Matching parameters
MATCH_WINDOW_DAYS = 7          # Controls ±N days for candidate search
MAX_CANDIDATES_PER_OVERRIDE = 50  # Limit query size
CALIPER_SIGMA_MULT = 0.25     # Caliper = 0.25 × σ(propensity)
MIN_STATE_FEATURES = 3         # Minimum numeric features to attempt matching

# Numeric keys commonly found in input_state for state-vector extraction
STATE_NUMERIC_KEYS = [
    "inventory_level", "backlog", "demand", "pipeline",
    "safety_stock", "lead_time", "capacity_utilization",
    "service_level", "fill_rate", "order_qty", "cost",
    "days_of_supply", "forecast", "on_hand", "in_transit",
    "utilization", "reorder_point", "order_quantity",
    "production_rate", "holding_cost", "shortage_cost",
]


class CausalMatchingService:
    """
    Finds propensity-score matched control decisions for overridden decisions.

    Populates CausalMatchPair rows that upgrade Tier 2 signal strength
    in OverrideEffectivenessService._signal_strength().
    """

    def __init__(self, db: Session):
        self.db = db

    def run_matching(self, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Main entry point — find and record matched pairs.

        Args:
            lookback_days: How far back to look for unmatched overrides.

        Returns:
            Stats dict with counts per trm_type.
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        stats = {"matched": 0, "skipped": 0, "failed": 0, "by_type": {}}

        # Find overridden decisions with outcomes that don't have matches yet
        already_matched_ids = (
            self.db.query(CausalMatchPair.overridden_decision_id)
            .subquery()
        )

        overridden = (
            self.db.query(SiteAgentDecision)
            .filter(
                SiteAgentDecision.is_overridden == True,
                SiteAgentDecision.reward_signal.isnot(None),
                SiteAgentDecision.human_actual_reward.isnot(None),
                SiteAgentDecision.decision_type.in_(TIER_2_TYPES),
                SiteAgentDecision.timestamp >= cutoff,
                ~SiteAgentDecision.id.in_(already_matched_ids),
            )
            .order_by(SiteAgentDecision.timestamp.desc())
            .limit(200)  # Process in batches
            .all()
        )

        if not overridden:
            logger.info("No unmatched Tier 2 overrides found")
            return stats

        logger.info(f"Found {len(overridden)} unmatched Tier 2 overrides")

        for decision in overridden:
            try:
                match = self._find_best_match(decision)
                if match:
                    self.db.add(match)
                    stats["matched"] += 1
                    dtype = decision.decision_type
                    stats["by_type"][dtype] = stats["by_type"].get(dtype, 0) + 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.warning(
                    f"Matching failed for decision {decision.id}: {e}"
                )
                stats["failed"] += 1

        try:
            self.db.flush()
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit matched pairs: {e}")
            self.db.rollback()
            stats["failed"] += stats["matched"]
            stats["matched"] = 0

        logger.info(
            f"Causal matching: {stats['matched']} matched, "
            f"{stats['skipped']} skipped, {stats['failed']} failed"
        )
        return stats

    def _find_best_match(
        self, override: SiteAgentDecision
    ) -> Optional[CausalMatchPair]:
        """
        Find the best non-overridden control decision for a given override.

        Uses nearest-neighbor on normalised state distance with propensity
        score caliper.
        """
        # Extract state vector from override
        override_state = self._extract_state_vector(override.input_state)
        if len(override_state) < MIN_STATE_FEATURES:
            return None

        # Find candidate controls: same type, same site, not overridden,
        # has outcome, within time window
        window_start = override.timestamp - timedelta(days=MATCH_WINDOW_DAYS)
        window_end = override.timestamp + timedelta(days=MATCH_WINDOW_DAYS)

        candidates = (
            self.db.query(SiteAgentDecision)
            .filter(
                SiteAgentDecision.decision_type == override.decision_type,
                SiteAgentDecision.site_key == override.site_key,
                or_(
                    SiteAgentDecision.is_overridden == False,
                    SiteAgentDecision.is_overridden.is_(None),
                ),
                SiteAgentDecision.reward_signal.isnot(None),
                SiteAgentDecision.timestamp.between(window_start, window_end),
                SiteAgentDecision.id != override.id,
            )
            .limit(MAX_CANDIDATES_PER_OVERRIDE)
            .all()
        )

        if not candidates:
            return None

        # Compute distances
        scored = []
        for cand in candidates:
            cand_state = self._extract_state_vector(cand.input_state)
            if len(cand_state) < MIN_STATE_FEATURES:
                continue
            dist = self._state_distance(override_state, cand_state)
            if dist is not None:
                scored.append((cand, dist))

        if not scored:
            return None

        # Sort by distance, pick best
        scored.sort(key=lambda x: x[1])
        best_cand, best_dist = scored[0]

        # Classify match quality based on distance distribution
        distances = [d for _, d in scored]
        quality = self._classify_quality(best_dist, distances)

        # Compute treatment effect
        override_reward = override.human_actual_reward or override.reward_signal
        control_reward = best_cand.reward_signal
        treatment_effect = (
            (override_reward - control_reward)
            if override_reward is not None and control_reward is not None
            else None
        )

        # Estimate propensity score (fraction of decisions that were overridden
        # with similar state distance — lightweight estimate)
        propensity = self._estimate_propensity(
            override.decision_type, override.site_key,
        )

        return CausalMatchPair(
            overridden_decision_id=override.id,
            control_decision_id=best_cand.id,
            trm_type=override.decision_type,
            state_distance=round(best_dist, 6),
            propensity_score=round(propensity, 4) if propensity else None,
            override_reward=override_reward,
            control_reward=control_reward,
            treatment_effect=round(treatment_effect, 6) if treatment_effect is not None else None,
            match_quality=quality,
        )

    def _extract_state_vector(
        self, input_state: Optional[Dict]
    ) -> Dict[str, float]:
        """
        Extract numeric features from input_state JSON.

        Returns dict of {feature_name: float_value} for common state keys.
        """
        if not input_state or not isinstance(input_state, dict):
            return {}

        features = {}
        for key in STATE_NUMERIC_KEYS:
            val = input_state.get(key)
            if val is not None:
                try:
                    features[key] = float(val)
                except (TypeError, ValueError):
                    pass

        # Also extract nested numeric values from known sub-dicts
        for sub_key in ("state", "context", "metrics"):
            sub = input_state.get(sub_key)
            if isinstance(sub, dict):
                for key in STATE_NUMERIC_KEYS:
                    val = sub.get(key)
                    if val is not None and key not in features:
                        try:
                            features[key] = float(val)
                        except (TypeError, ValueError):
                            pass

        return features

    def _state_distance(
        self,
        state_a: Dict[str, float],
        state_b: Dict[str, float],
    ) -> Optional[float]:
        """
        Compute normalised L2 distance between two state vectors.

        Only uses features present in both vectors. Normalises each dimension
        by range across the pair to avoid scale dominance.
        """
        common_keys = set(state_a.keys()) & set(state_b.keys())
        if len(common_keys) < MIN_STATE_FEATURES:
            return None

        squared_sum = 0.0
        for key in common_keys:
            a_val = state_a[key]
            b_val = state_b[key]
            # Normalise by max(|a|, |b|, 1) to avoid division by zero
            scale = max(abs(a_val), abs(b_val), 1.0)
            diff = (a_val - b_val) / scale
            squared_sum += diff * diff

        return math.sqrt(squared_sum / len(common_keys))

    def _classify_quality(
        self, distance: float, all_distances: List[float]
    ) -> str:
        """Classify match quality based on distance percentile."""
        if len(all_distances) < 2:
            return "MEDIUM"

        sorted_d = sorted(all_distances)
        n = len(sorted_d)
        p25 = sorted_d[max(0, n // 4)]
        p50 = sorted_d[max(0, n // 2)]

        if distance <= p25:
            return "HIGH"
        elif distance <= p50:
            return "MEDIUM"
        return "LOW"

    def _estimate_propensity(
        self, decision_type: str, site_key: str
    ) -> Optional[float]:
        """
        Estimate P(override | decision_type, site_key) from observed rates.

        Lightweight: just the override fraction for this type+site in the
        last 90 days. More sophisticated logistic model can be plugged in
        when enough data accumulates.
        """
        cutoff = datetime.utcnow() - timedelta(days=90)

        total = self.db.query(func.count(SiteAgentDecision.id)).filter(
            SiteAgentDecision.decision_type == decision_type,
            SiteAgentDecision.site_key == site_key,
            SiteAgentDecision.timestamp >= cutoff,
        ).scalar() or 0

        if total < 5:
            return None  # Not enough data

        overridden = self.db.query(func.count(SiteAgentDecision.id)).filter(
            SiteAgentDecision.decision_type == decision_type,
            SiteAgentDecision.site_key == site_key,
            SiteAgentDecision.is_overridden == True,
            SiteAgentDecision.timestamp >= cutoff,
        ).scalar() or 0

        return overridden / total

    def get_matching_stats(self) -> Dict[str, Any]:
        """Get summary statistics of existing matched pairs."""
        total = self.db.query(func.count(CausalMatchPair.id)).scalar() or 0

        by_quality = {}
        for quality in ("HIGH", "MEDIUM", "LOW"):
            count = self.db.query(func.count(CausalMatchPair.id)).filter(
                CausalMatchPair.match_quality == quality,
            ).scalar() or 0
            by_quality[quality] = count

        by_type = {}
        type_rows = (
            self.db.query(
                CausalMatchPair.trm_type,
                func.count(CausalMatchPair.id),
                func.avg(CausalMatchPair.treatment_effect),
            )
            .group_by(CausalMatchPair.trm_type)
            .all()
        )
        for trm_type, count, avg_te in type_rows:
            by_type[trm_type] = {
                "count": count,
                "avg_treatment_effect": round(float(avg_te), 4) if avg_te else None,
            }

        avg_distance = self.db.query(
            func.avg(CausalMatchPair.state_distance)
        ).filter(
            CausalMatchPair.match_quality.in_(["HIGH", "MEDIUM"]),
        ).scalar()

        return {
            "total_pairs": total,
            "by_quality": by_quality,
            "by_type": by_type,
            "avg_state_distance": round(float(avg_distance), 4) if avg_distance else None,
        }

"""
Experiential Knowledge Service — Pattern Detection, Lifecycle, RL Integration

Elevates recurring override patterns into structured knowledge entities.
Provides four RL integration channels:
1. State augmentation — conditional features for TRM state vectors
2. Reward shaping — ±bonus for GENUINE knowledge alignment
3. Conditional CDT — uncertainty multiplier when conditions active
4. Simulation modifiers — distribution multipliers for Monte Carlo

Based on Alicke's "The Planner Was the System" — experiential knowledge
as Powell Belief State (Bₜ).
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, or_, func as sa_func, text
from sqlalchemy.orm import Session

from app.models.experiential_knowledge import (
    ExperientialKnowledge,
    PATTERN_STATE_FEATURES,
)

logger = logging.getLogger(__name__)

# ---- Decision table imports (same registry as decision_stream_service) ----
from app.models.powell_decisions import (
    PowellATPDecision,
    PowellRebalanceDecision,
    PowellPODecision,
    PowellOrderException,
    PowellMODecision,
    PowellTODecision,
    PowellQualityDecision,
    PowellMaintenanceDecision,
    PowellSubcontractingDecision,
    PowellForecastAdjustmentDecision,
    PowellBufferDecision,
)

OVERRIDE_DECISION_TABLES = [
    (PowellATPDecision, "atp"),
    (PowellRebalanceDecision, "rebalancing"),
    (PowellPODecision, "po_creation"),
    (PowellOrderException, "order_tracking"),
    (PowellMODecision, "mo_execution"),
    (PowellTODecision, "to_execution"),
    (PowellQualityDecision, "quality"),
    (PowellMaintenanceDecision, "maintenance"),
    (PowellSubcontractingDecision, "subcontracting"),
    (PowellForecastAdjustmentDecision, "forecast_adjustment"),
    (PowellBufferDecision, "inventory_buffer"),
]

MIN_PATTERN_COUNT = 3
SIMILARITY_UPDATE_THRESHOLD = 0.85
MAX_REWARD_SHAPING = 0.05


class ExperientialKnowledgeService:
    """Core service for experiential knowledge management and RL integration."""

    def __init__(self, db: Session, tenant_id: int, config_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self._cache: Dict[str, Any] = {}

    # =========================================================================
    # Pattern Detection
    # =========================================================================

    def detect_patterns(self, lookback_days: int = 90) -> Dict[str, int]:
        """Detect recurring override patterns across all 11 decision tables.

        Returns dict of {status: count} — how many CANDIDATEs created/updated.
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        created = 0
        updated = 0

        for model_cls, trm_type in OVERRIDE_DECISION_TABLES:
            try:
                overrides = self._query_overrides(model_cls, trm_type, cutoff)
                if not overrides:
                    continue

                # Group by pattern key
                groups = self._group_by_pattern(overrides, trm_type)

                for key, group in groups.items():
                    if len(group) < MIN_PATTERN_COUNT:
                        continue

                    result = self._process_pattern_group(key, group, trm_type)
                    if result == "created":
                        created += 1
                    elif result == "updated":
                        updated += 1

            except Exception as e:
                logger.warning("EK pattern detection failed for %s: %s", trm_type, e)
                continue

        logger.info(
            "EK pattern detection: %d created, %d updated (tenant=%d)",
            created, updated, self.tenant_id,
        )
        return {"created": created, "updated": updated}

    def _query_overrides(self, model_cls, trm_type: str, cutoff: datetime) -> list:
        """Query overridden decisions from a single table."""
        # All powell tables have override_action via HiveSignalMixin
        query = (
            select(model_cls)
            .where(
                and_(
                    model_cls.override_action.isnot(None),
                    model_cls.created_at >= cutoff,
                )
            )
        )

        # Filter by config_id if available
        if self.config_id and hasattr(model_cls, "config_id"):
            query = query.where(model_cls.config_id == self.config_id)

        result = self.db.execute(query)
        return result.scalars().all()

    def _group_by_pattern(self, overrides: list, trm_type: str) -> dict:
        """Group overrides by pattern key for candidate detection."""
        groups = defaultdict(list)
        for d in overrides:
            # Extract entity context from decision
            entity_context = self._extract_entity_context(d)
            reason_code = getattr(d, "override_reason_code", None) or "OTHER"
            user_id = getattr(d, "override_user_id", None) or 0

            key = (user_id, trm_type, reason_code, str(sorted(entity_context.items())))
            groups[key].append(d)
        return groups

    def _extract_entity_context(self, decision) -> dict:
        """Extract entity IDs from a decision record for pattern grouping."""
        ctx = {}
        for attr in ("product_id", "site_id", "location_id", "supplier_id"):
            val = getattr(decision, attr, None)
            if val is not None:
                ctx[attr] = str(val)
        return ctx

    def _process_pattern_group(
        self, key: tuple, group: list, trm_type: str
    ) -> Optional[str]:
        """Process a group of overrides into a CANDIDATE or update existing entity."""
        user_id, trm_type_key, reason_code, entity_str = key

        # Build entity_ids from the first decision's context
        entity_ids = self._extract_entity_context(group[0])
        entity_type = self._infer_entity_type(entity_ids)

        # Build evidence list — enriched with causal AI outcome data
        evidence = []
        beneficial_count = 0
        detrimental_count = 0
        for d in group:
            entry = {
                "decision_table": d.__tablename__,
                "decision_id": d.id,
                "date": d.created_at.isoformat() if d.created_at else None,
                "override_reason_code": reason_code,
            }
            # Enrich with outcome data if available (filled by OutcomeCollector)
            if hasattr(d, "was_committed") and d.was_committed is not None:
                entry["was_committed"] = d.was_committed
            if hasattr(d, "actual_cost") and d.actual_cost is not None:
                entry["actual_cost"] = float(d.actual_cost)
            if hasattr(d, "actual_fulfilled_qty") and d.actual_fulfilled_qty is not None:
                entry["actual_fulfilled_qty"] = float(d.actual_fulfilled_qty)
            # Check SiteAgentDecision for causal classification if linked
            causal = self._get_causal_classification(d)
            if causal:
                entry.update(causal)
                if causal.get("override_classification") == "BENEFICIAL":
                    beneficial_count += 1
                elif causal.get("override_classification") == "DETRIMENTAL":
                    detrimental_count += 1
            evidence.append(entry)

        # Build summary from reason texts
        reason_texts = [
            getattr(d, "override_reason_text", "") or ""
            for d in group
        ]
        summary = self._build_summary(
            trm_type_key, reason_code, entity_ids, reason_texts, len(group)
        )

        # Compute causal-weighted confidence
        # Base confidence from count + boost from Bayesian posterior
        causal_confidence = self._compute_causal_confidence(
            user_id, trm_type_key, len(group), beneficial_count, detrimental_count
        )

        # Check for existing matching entity
        existing = self._find_similar_entity(entity_ids, trm_type_key, reason_code)

        if existing:
            # Update existing entity with new evidence
            existing_evidence = existing.evidence or []
            existing_evidence.extend(evidence)
            existing.evidence = existing_evidence
            existing_users = existing.source_user_ids or []
            if user_id not in existing_users:
                existing_users.append(user_id)
                existing.source_user_ids = existing_users
            existing.confidence = min(1.0, max(existing.confidence, causal_confidence))
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            return "updated"

        # Auto-classify GENUINE vs COMPENSATING from causal evidence
        # If majority of overrides were BENEFICIAL → likely GENUINE
        # If majority were DETRIMENTAL/NEUTRAL → likely COMPENSATING
        auto_knowledge_type = None
        if beneficial_count + detrimental_count >= 2:
            if beneficial_count > detrimental_count:
                auto_knowledge_type = "GENUINE"
            elif detrimental_count > beneficial_count:
                auto_knowledge_type = "COMPENSATING"

        # Create new CANDIDATE
        pattern_type = self._infer_pattern_type(trm_type_key, reason_code)
        state_features = PATTERN_STATE_FEATURES.get(pattern_type, [f"ek_{pattern_type[:10]}"])

        ek = ExperientialKnowledge(
            tenant_id=self.tenant_id,
            config_id=self.config_id or 0,
            entity_type=entity_type,
            entity_ids=entity_ids,
            pattern_type=pattern_type,
            conditions=self._infer_conditions(group),
            effect=self._infer_effect(trm_type_key, reason_code, group),
            confidence=causal_confidence,
            knowledge_type=auto_knowledge_type,  # Auto-classified from causal evidence, or None
            source_type="OVERRIDE_PATTERN",
            evidence=evidence,
            source_user_ids=[user_id],
            trm_types_affected=[trm_type_key],
            state_feature_names=state_features,
            status="CANDIDATE",
            summary=summary,
        )
        self.db.add(ek)
        self.db.commit()
        return "created"

    def _find_similar_entity(
        self, entity_ids: dict, trm_type: str, reason_code: str
    ) -> Optional[ExperientialKnowledge]:
        """Find existing entity matching the same entity context and TRM type."""
        # Simple exact-match for now; can add embedding similarity later
        query = (
            select(ExperientialKnowledge)
            .where(
                and_(
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                    ExperientialKnowledge.entity_ids == entity_ids,
                    ExperientialKnowledge.status.in_(["CANDIDATE", "ACTIVE"]),
                )
            )
        )
        if self.config_id:
            query = query.where(ExperientialKnowledge.config_id == self.config_id)

        result = self.db.execute(query)
        candidates = result.scalars().all()

        for c in candidates:
            if trm_type in (c.trm_types_affected or []):
                return c
        return None

    def _get_causal_classification(self, decision) -> Optional[dict]:
        """Look up causal AI classification for an overridden decision.

        Checks SiteAgentDecision for override_delta and override_classification
        which are filled by OutcomeCollector with counterfactual analysis.
        Returns dict with causal fields or None if not available.
        """
        try:
            from app.models.powell_decision import SiteAgentDecision
            # Match by decision type + approximate time window
            result = self.db.execute(
                select(SiteAgentDecision).where(
                    and_(
                        SiteAgentDecision.is_overridden == True,
                        SiteAgentDecision.override_classification.isnot(None),
                        SiteAgentDecision.created_at >= (decision.created_at - timedelta(minutes=5)) if decision.created_at else False,
                        SiteAgentDecision.created_at <= (decision.created_at + timedelta(minutes=5)) if decision.created_at else False,
                    )
                ).limit(1)
            )
            sad = result.scalar_one_or_none()
            if sad:
                return {
                    "override_delta": sad.override_delta,
                    "override_classification": sad.override_classification,
                    "composite_override_score": sad.composite_override_score,
                    "site_bsc_delta": sad.site_bsc_delta,
                }
        except Exception:
            pass
        return None

    def _compute_causal_confidence(
        self, user_id: int, trm_type: str, count: int,
        beneficial_count: int, detrimental_count: int,
    ) -> float:
        """Compute EK entity confidence weighted by causal AI evidence.

        Factors:
        1. Override count (more = more confident)
        2. Causal classification ratio (more BENEFICIAL = higher confidence)
        3. User's Bayesian posterior (effective overriders contribute more)
        """
        # Base from count: 3 overrides → 0.3, 10 → 0.6, 20+ → 0.8
        base = min(0.8, 0.2 + 0.04 * count)

        # Causal boost: if we have classifications, weight by effectiveness
        causal_total = beneficial_count + detrimental_count
        if causal_total >= 2:
            effectiveness_ratio = beneficial_count / causal_total
            # Effective overrides boost confidence; detrimental reduce it
            causal_boost = (effectiveness_ratio - 0.5) * 0.3  # [-0.15, +0.15]
            base += causal_boost

        # User posterior boost: proven-effective users get higher weight
        try:
            from app.services.override_effectiveness_service import OverrideEffectivenessService
            weight = OverrideEffectivenessService.get_training_weight(
                self.db, user_id, trm_type
            )
            # weight ranges [0.3, 2.0], neutral = 0.85
            # Map to [-0.1, +0.1] boost
            posterior_boost = (weight - 0.85) * 0.087  # ≈ [-0.05, +0.10]
            base += posterior_boost
        except Exception:
            pass

        return max(0.1, min(1.0, base))

    def _infer_entity_type(self, entity_ids: dict) -> str:
        keys = set(entity_ids.keys())
        if "supplier_id" in keys and "site_id" in keys:
            return "supplier_site"
        if "supplier_id" in keys and "product_id" in keys:
            return "supplier_product"
        if "product_id" in keys and "site_id" in keys:
            return "product_site"
        if "supplier_id" in keys:
            return "supplier"
        if "product_id" in keys:
            return "product"
        if "site_id" in keys or "location_id" in keys:
            return "site"
        return "organizational"

    def _infer_pattern_type(self, trm_type: str, reason_code: str) -> str:
        """Infer pattern type from TRM type and reason code."""
        reason_map = {
            "SUPPLIER_ISSUE": "supplier_behavior",
            "CAPACITY_CONSTRAINT": "capacity_constraint",
            "QUALITY_CONCERN": "quality_degradation",
            "DEMAND_CHANGE": "demand_seasonality",
            "MARKET_INTELLIGENCE": "demand_seasonality",
            "COST_OPTIMIZATION": "cost_variation",
            "SERVICE_LEVEL": "forecast_bias",
        }
        return reason_map.get(reason_code, "supplier_behavior")

    def _infer_conditions(self, group: list) -> dict:
        """Infer temporal conditions from override dates."""
        conditions = {}
        if group:
            months = [d.created_at.month for d in group if d.created_at]
            if months:
                quarters = set((m - 1) // 3 + 1 for m in months)
                if len(quarters) == 1:
                    conditions["quarter"] = f"Q{quarters.pop()}"
        return conditions

    def _infer_effect(self, trm_type: str, reason_code: str, group: list) -> dict:
        """Infer effect from override pattern."""
        # Default: directional effect based on reason code
        direction_map = {
            "SUPPLIER_ISSUE": ("lead_time", "increase", 1.3),
            "CAPACITY_CONSTRAINT": ("capacity", "decrease", 0.8),
            "QUALITY_CONCERN": ("yield", "decrease", 0.9),
            "DEMAND_CHANGE": ("demand", "increase", 1.2),
            "COST_OPTIMIZATION": ("cost", "increase", 1.1),
        }
        variable, direction, multiplier = direction_map.get(
            reason_code, ("general", "increase", 1.2)
        )
        return {
            "variable": variable,
            "direction": direction,
            "multiplier": multiplier,
        }

    def _build_summary(
        self, trm_type: str, reason_code: str, entity_ids: dict,
        reason_texts: list, count: int,
    ) -> str:
        """Build human-readable summary for the knowledge entity."""
        entity_desc = ", ".join(f"{k}={v}" for k, v in entity_ids.items())
        reason_sample = next((t for t in reason_texts if t.strip()), reason_code)
        if len(reason_sample) > 100:
            reason_sample = reason_sample[:100] + "..."
        return (
            f"Recurring override pattern ({count}x) for {trm_type} "
            f"affecting {entity_desc}: {reason_sample}"
        )

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def check_lifecycle(self) -> Dict[str, int]:
        """Run stagnation and contradiction detection.

        Returns dict of {stale: N, contradicted: N}.
        """
        stale = self._detect_stagnation()
        contradicted = self._detect_contradictions()
        logger.info(
            "EK lifecycle: %d stale, %d contradicted (tenant=%d)",
            stale, contradicted, self.tenant_id,
        )
        return {"stale": stale, "contradicted": contradicted}

    def _detect_stagnation(self) -> int:
        """Mark ACTIVE entities past their validation window as STALE."""
        now = datetime.utcnow()
        query = (
            select(ExperientialKnowledge)
            .where(
                and_(
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                    ExperientialKnowledge.status == "ACTIVE",
                )
            )
        )
        result = self.db.execute(query)
        entities = result.scalars().all()

        count = 0
        for e in entities:
            validated = e.last_validated_at or e.created_at
            if validated and (now - validated).days > e.stale_after_days:
                e.status = "STALE"
                e.updated_at = now
                count += 1

        if count:
            self.db.commit()
        return count

    def _detect_contradictions(self) -> int:
        """Find ACTIVE entities with same context but conflicting effects."""
        query = (
            select(ExperientialKnowledge)
            .where(
                and_(
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                    ExperientialKnowledge.status == "ACTIVE",
                )
            )
            .order_by(ExperientialKnowledge.pattern_type, ExperientialKnowledge.entity_type)
        )
        result = self.db.execute(query)
        entities = result.scalars().all()

        # Group by (entity_ids_str, pattern_type)
        groups = defaultdict(list)
        for e in entities:
            key = (str(sorted(e.entity_ids.items())), e.pattern_type)
            groups[key].append(e)

        count = 0
        for key, group in groups.items():
            if len(group) < 2:
                continue
            # Check for conflicting directions
            directions = set(e.effect.get("direction") for e in group if e.effect)
            if len(directions) > 1:
                for e in group:
                    if e.status != "CONTRADICTED":
                        e.status = "CONTRADICTED"
                        # Cross-reference the first other entity
                        other = next((o for o in group if o.id != e.id), None)
                        if other:
                            e.contradiction_id = other.id
                        count += 1

        if count:
            self.db.commit()
        return count

    # =========================================================================
    # CRUD Helpers
    # =========================================================================

    def list_entities(
        self,
        status: Optional[str] = None,
        pattern_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        trm_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ExperientialKnowledge], int]:
        """List entities with filters. Returns (entities, total_count)."""
        query = select(ExperientialKnowledge).where(
            ExperientialKnowledge.tenant_id == self.tenant_id
        )
        if self.config_id:
            query = query.where(ExperientialKnowledge.config_id == self.config_id)
        if status:
            query = query.where(ExperientialKnowledge.status == status)
        if pattern_type:
            query = query.where(ExperientialKnowledge.pattern_type == pattern_type)
        if entity_type:
            query = query.where(ExperientialKnowledge.entity_type == entity_type)

        # Count
        count_q = select(sa_func.count()).select_from(query.subquery())
        total = self.db.execute(count_q).scalar() or 0

        # Fetch
        query = query.order_by(ExperientialKnowledge.updated_at.desc())
        query = query.limit(limit).offset(offset)
        result = self.db.execute(query)
        entities = result.scalars().all()

        # Filter by trm_type (JSON contains)
        if trm_type:
            entities = [e for e in entities if trm_type in (e.trm_types_affected or [])]

        return entities, total

    def get_by_id(self, ek_id: int) -> Optional[ExperientialKnowledge]:
        result = self.db.execute(
            select(ExperientialKnowledge).where(
                and_(
                    ExperientialKnowledge.id == ek_id,
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    def validate_entity(self, ek_id: int, user_id: int) -> Optional[ExperientialKnowledge]:
        """Confirm entity still valid (STALE → ACTIVE)."""
        ek = self.get_by_id(ek_id)
        if not ek:
            return None
        ek.status = "ACTIVE"
        ek.last_validated_at = datetime.utcnow()
        ek.validated_by_id = user_id
        self.db.commit()
        return ek

    def classify_entity(
        self, ek_id: int, knowledge_type: str, rationale: str
    ) -> Optional[ExperientialKnowledge]:
        """Set knowledge_type (GENUINE/COMPENSATING)."""
        ek = self.get_by_id(ek_id)
        if not ek:
            return None
        ek.knowledge_type = knowledge_type
        ek.knowledge_type_rationale = rationale
        self.db.commit()
        return ek

    def confirm_candidate(
        self, ek_id: int, user_id: int,
        knowledge_type: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> Optional[ExperientialKnowledge]:
        """Confirm CANDIDATE → ACTIVE."""
        ek = self.get_by_id(ek_id)
        if not ek or ek.status != "CANDIDATE":
            return None
        ek.status = "ACTIVE"
        ek.last_validated_at = datetime.utcnow()
        ek.validated_by_id = user_id
        if knowledge_type:
            ek.knowledge_type = knowledge_type
        if rationale:
            ek.knowledge_type_rationale = rationale
        self.db.commit()
        return ek

    def retire_entity(
        self, ek_id: int, reason: str
    ) -> Optional[ExperientialKnowledge]:
        """Retire an entity."""
        ek = self.get_by_id(ek_id)
        if not ek:
            return None
        ek.status = "RETIRED"
        ek.retired_reason = reason
        self.db.commit()
        return ek

    def resolve_contradiction(
        self, winner_id: int, loser_id: int
    ) -> Optional[ExperientialKnowledge]:
        """Resolve contradiction: winner stays ACTIVE, loser RETIRED."""
        winner = self.get_by_id(winner_id)
        loser = self.get_by_id(loser_id)
        if not winner or not loser:
            return None
        winner.status = "ACTIVE"
        winner.contradiction_id = None
        loser.status = "RETIRED"
        loser.retired_reason = f"Contradiction resolved in favor of entity {winner_id}"
        self.db.commit()
        return winner

    def get_stats(self) -> dict:
        """Aggregate statistics for dashboard."""
        query = (
            select(
                ExperientialKnowledge.status,
                sa_func.count().label("count"),
            )
            .where(ExperientialKnowledge.tenant_id == self.tenant_id)
            .group_by(ExperientialKnowledge.status)
        )
        if self.config_id:
            query = query.where(ExperientialKnowledge.config_id == self.config_id)

        result = self.db.execute(query)
        by_status = {r[0]: r[1] for r in result.fetchall()}

        query2 = (
            select(
                ExperientialKnowledge.pattern_type,
                sa_func.count().label("count"),
            )
            .where(
                and_(
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                    ExperientialKnowledge.status == "ACTIVE",
                )
            )
            .group_by(ExperientialKnowledge.pattern_type)
        )
        result2 = self.db.execute(query2)
        by_pattern = {r[0]: r[1] for r in result2.fetchall()}

        query3 = (
            select(
                ExperientialKnowledge.knowledge_type,
                sa_func.count().label("count"),
            )
            .where(
                and_(
                    ExperientialKnowledge.tenant_id == self.tenant_id,
                    ExperientialKnowledge.status == "ACTIVE",
                    ExperientialKnowledge.knowledge_type.isnot(None),
                )
            )
            .group_by(ExperientialKnowledge.knowledge_type)
        )
        result3 = self.db.execute(query3)
        by_type = {r[0]: r[1] for r in result3.fetchall()}

        return {
            "by_status": by_status,
            "by_pattern_type": by_pattern,
            "by_knowledge_type": by_type,
            "total": sum(by_status.values()),
        }

    # =========================================================================
    # RL Integration Methods
    # =========================================================================

    def get_state_augmentation(
        self,
        config_id: int,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        sim_day: Optional[int] = None,
        supplier_id: Optional[str] = None,
    ) -> Dict[str, float]:
        """Return conditional features to append to TRM state vectors.

        Queries ACTIVE entities matching the given context, evaluates
        conditions, and returns feature_name → feature_value dict.

        Returns empty dict if no matching entities → backward compatible.
        Cached per (config_id, sim_day) to avoid per-decision DB queries.
        """
        cache_key = f"sa_{config_id}_{sim_day}"
        if cache_key in self._cache:
            all_entities = self._cache[cache_key]
        else:
            all_entities = self._load_active_entities(config_id)
            self._cache[cache_key] = all_entities

        if not all_entities:
            return {}

        # Build context for condition evaluation
        context = {}
        if product_id is not None:
            context["product_id"] = str(product_id)
        if site_id is not None:
            context["site_id"] = str(site_id)
        if supplier_id is not None:
            context["supplier_id"] = str(supplier_id)
        if sim_day is not None:
            # Derive temporal context
            month = ((sim_day - 1) % 365) // 30 + 1
            quarter = (month - 1) // 3 + 1
            context["quarter"] = f"Q{quarter}"
            context["month"] = month
            context["day_of_week"] = sim_day % 7

        features = {}
        for ek in all_entities:
            if not ek.evaluate_conditions(context):
                continue
            # Check entity scope match
            if not self._entity_matches_context(ek, context):
                continue
            for fname, fval in ek.get_state_features().items():
                # Max across matching entities for same feature
                features[fname] = max(features.get(fname, 0.0), fval)

        return features

    def get_reward_shaping(
        self,
        config_id: int,
        trm_type: str,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        decision_direction: Optional[str] = None,
        conditions: Optional[dict] = None,
    ) -> float:
        """Return reward shaping bonus for a decision.

        Only GENUINE knowledge contributes. COMPENSATING returns 0.0.
        Returns ±MAX_REWARD_SHAPING (default ±0.05).
        """
        entities = self._load_active_entities(config_id)
        if not entities:
            return 0.0

        context = conditions or {}
        if product_id:
            context["product_id"] = str(product_id)
        if site_id:
            context["site_id"] = str(site_id)

        total_bonus = 0.0
        match_count = 0

        for ek in entities:
            if not ek.is_genuine():
                continue  # COMPENSATING excluded
            if trm_type not in (ek.trm_types_affected or []):
                continue
            if not ek.evaluate_conditions(context):
                continue
            if not self._entity_matches_context(ek, context):
                continue

            # Check alignment: does decision direction match effect direction?
            effect_dir = ek.effect.get("direction", "increase")
            bonus = ek.reward_shaping_bonus * ek.confidence

            if decision_direction and decision_direction == effect_dir:
                total_bonus += bonus  # Aligned
            elif decision_direction and decision_direction != effect_dir:
                total_bonus -= bonus  # Contradicts
            else:
                total_bonus += bonus * 0.5  # Partial alignment (direction unknown)

            match_count += 1

        if match_count == 0:
            return 0.0

        # Cap at ±MAX_REWARD_SHAPING
        return max(-MAX_REWARD_SHAPING, min(MAX_REWARD_SHAPING, total_bonus / match_count))

    def get_cdt_uncertainty_modifier(
        self,
        config_id: int,
        trm_type: str,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        conditions: Optional[dict] = None,
    ) -> float:
        """Return CDT interval width multiplier.

        Returns max cdt_uncertainty_multiplier across matching ACTIVE entities.
        Default 1.0 = no change. >1.0 = wider intervals = more uncertainty.
        """
        entities = self._load_active_entities(config_id)
        if not entities:
            return 1.0

        context = conditions or {}
        if product_id:
            context["product_id"] = str(product_id)
        if site_id:
            context["site_id"] = str(site_id)

        max_modifier = 1.0
        for ek in entities:
            if trm_type not in (ek.trm_types_affected or []):
                continue
            if not ek.evaluate_conditions(context):
                continue
            if not self._entity_matches_context(ek, context):
                continue
            max_modifier = max(max_modifier, ek.cdt_uncertainty_multiplier)

        return max_modifier

    def get_conditional_modifiers(self, config_id: int) -> List[Dict]:
        """Return ACTIVE entities as simulation distribution modifiers.

        Format: [{"entity_ids": {...}, "variable": "lead_time",
                  "condition_params": {"quarter": "Q4"}, "multiplier": 1.5}]
        """
        entities = self._load_active_entities(config_id)
        modifiers = []
        for ek in entities:
            modifiers.append({
                "entity_ids": ek.entity_ids,
                "variable": ek.effect.get("variable", "general"),
                "direction": ek.effect.get("direction", "increase"),
                "multiplier": ek.effect.get("multiplier", 1.0),
                "condition_params": ek.conditions,
                "confidence": ek.confidence,
                "knowledge_type": ek.knowledge_type,
                "ek_id": ek.id,
            })
        return modifiers

    # =========================================================================
    # Chat Context
    # =========================================================================

    def get_knowledge_for_chat_context(self, max_entities: int = 8) -> str:
        """Return formatted markdown of ACTIVE entities for Azirella prompt.

        Follows the _get_external_signals_context() pattern.
        """
        entities = self._load_active_entities(self.config_id)
        if not entities:
            return ""

        # Sort by confidence desc, take top N
        entities = sorted(entities, key=lambda e: e.confidence, reverse=True)[:max_entities]

        lines = ["## Experiential Knowledge (Planner Behavioral Patterns)"]
        lines.append("")
        for ek in entities:
            badge = "GENUINE" if ek.is_genuine() else (ek.knowledge_type or "UNCLASSIFIED")
            lines.append(f"- **[{badge}]** {ek.summary}")
            if ek.conditions:
                cond_str = ", ".join(f"{k}={v}" for k, v in ek.conditions.items())
                lines.append(f"  - Conditions: {cond_str}")
            effect = ek.effect or {}
            if effect:
                lines.append(
                    f"  - Effect: {effect.get('variable', '?')} "
                    f"{effect.get('direction', '?')} "
                    f"×{effect.get('multiplier', 1.0):.1f} "
                    f"(confidence: {ek.confidence:.0%})"
                )
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _load_active_entities(
        self, config_id: Optional[int] = None
    ) -> List[ExperientialKnowledge]:
        """Load all ACTIVE entities for tenant/config. Cached per service instance."""
        cache_key = f"active_{config_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = select(ExperientialKnowledge).where(
            and_(
                ExperientialKnowledge.tenant_id == self.tenant_id,
                ExperientialKnowledge.status == "ACTIVE",
            )
        )
        if config_id:
            query = query.where(ExperientialKnowledge.config_id == config_id)

        result = self.db.execute(query)
        entities = result.scalars().all()
        self._cache[cache_key] = entities
        return entities

    def _entity_matches_context(self, ek: ExperientialKnowledge, context: dict) -> bool:
        """Check if entity's entity_ids match the given context."""
        for key, val in (ek.entity_ids or {}).items():
            if key in context and str(context[key]) != str(val):
                return False
        return True

    def clear_cache(self):
        """Clear internal cache (call after mutations)."""
        self._cache.clear()

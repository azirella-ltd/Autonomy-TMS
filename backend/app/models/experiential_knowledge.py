"""
Experiential Knowledge — Structured Behavioral Knowledge Entities

Elevates recurring override patterns into explicit, queryable knowledge entities
that feed into the RL training pipeline via state augmentation, reward shaping,
conditional CDT, and simulation modifiers.

Based on Knut Alicke's "The Planner Was the System" — experiential knowledge
as a Powell Belief State variable (Bₜ) that enables TRMs to learn conditional
patterns they couldn't previously represent.

Key distinction (Alicke):
- GENUINE: Real behavioral pattern valid regardless of data quality
- COMPENSATING: Workaround for system deficiency; retired when root cause fixed
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.sql import func

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

from app.models.base import Base


# --- Enums (stored as VARCHAR, documented here for reference) ---

ENTITY_TYPES = [
    "supplier",
    "product",
    "site",
    "lane",
    "product_site",
    "supplier_site",
    "supplier_product",
    "season",
    "organizational",
]

PATTERN_TYPES = [
    "lead_time_variation",
    "demand_seasonality",
    "capacity_constraint",
    "quality_degradation",
    "forecast_bias",
    "supplier_behavior",
    "organizational_behavior",
    "cost_variation",
    "yield_variation",
    "transit_disruption",
]

KNOWLEDGE_TYPES = [
    "GENUINE",       # Real behavioral pattern — contributes reward shaping
    "COMPENSATING",  # Workaround for system deficiency — no reward shaping
]

SOURCE_TYPES = [
    "OVERRIDE_PATTERN",    # Auto-detected from recurring overrides
    "MANUAL_ENTRY",        # Planner entered directly
    "SYSTEM_DETECTED",     # Statistical anomaly detection
    "AZIRELLA_DIALOGUE",   # Captured via structured conversation
]

STATUS_VALUES = [
    "CANDIDATE",     # Detected, awaiting planner confirmation
    "ACTIVE",        # Confirmed, feeding into RL pipeline
    "STALE",         # Not validated within stale_after_days
    "CONTRADICTED",  # Conflicting entity exists
    "RETIRED",       # Manually retired or sole-source user left
    "SUPERSEDED",    # Statistical signals now capture this pattern
]

# Default state feature name prefixes by pattern type
PATTERN_STATE_FEATURES = {
    "lead_time_variation": ["ek_lt_risk"],
    "demand_seasonality": ["ek_demand_season"],
    "capacity_constraint": ["ek_capacity_risk"],
    "quality_degradation": ["ek_quality_risk"],
    "forecast_bias": ["ek_forecast_bias"],
    "supplier_behavior": ["ek_supplier_risk"],
    "organizational_behavior": ["ek_org_factor"],
    "cost_variation": ["ek_cost_risk"],
    "yield_variation": ["ek_yield_risk"],
    "transit_disruption": ["ek_transit_risk"],
}


class ExperientialKnowledge(Base):
    """
    Structured behavioral knowledge entity elevated from override patterns.

    Each row represents a PATTERN (not a single decision) — e.g.,
    "Supplier X lead times increase ~50% in Q4 due to harvest season."

    Feeds into the RL pipeline via four channels:
    1. State augmentation — conditional features appended to TRM state vectors
    2. Reward shaping — ±0.05 bonus for GENUINE knowledge alignment
    3. Conditional CDT — widens conformal intervals when conditions active
    4. Simulation modifiers — multipliers on stochastic distributions
    """
    __tablename__ = "experiential_knowledge"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # --- Entity scope ---
    entity_type = Column(String(50), nullable=False)
    entity_ids = Column(JSON, nullable=False)
    # e.g. {"supplier_id": 42, "site_id": 7} or {"product_id": "PROD-001"}

    # --- Pattern classification ---
    pattern_type = Column(String(80), nullable=False)

    # --- Conditions: when does this pattern apply? ---
    conditions = Column(JSON, nullable=False)
    # e.g. {"quarter": "Q4", "trigger": "harvest_season"}
    # Temporal: quarter, month, day_of_week, season
    # Categorical: supplier_region, product_category, demand_class

    # --- Effect: what happens when conditions are met? ---
    effect = Column(JSON, nullable=False)
    # e.g. {"variable": "lead_time", "direction": "increase", "multiplier": 1.5,
    #        "additive_days": 0, "confidence_interval": [1.2, 1.8]}

    # --- Confidence ---
    confidence = Column(Float, nullable=False, default=0.5)

    # --- Knowledge type (CRITICAL Alicke distinction) ---
    knowledge_type = Column(String(20), nullable=True)
    # NULL for CANDIDATE (classified during confirmation)
    # GENUINE: real behavioral pattern, contributes reward shaping
    # COMPENSATING: workaround, excluded from reward shaping
    knowledge_type_rationale = Column(Text, nullable=True)

    # --- Source ---
    source_type = Column(String(30), nullable=False)

    # --- Evidence trail ---
    evidence = Column(JSON, nullable=False, default=list)
    # [{"decision_table": "powell_po_decisions", "decision_id": 123,
    #   "date": "2026-01-15", "override_delta": 0.12}, ...]
    source_user_ids = Column(JSON, nullable=False, default=list)
    # [4, 7] — users who contributed observations

    # --- TRM routing ---
    trm_types_affected = Column(JSON, nullable=False, default=list)
    # ["po_creation", "inventory_buffer"]

    # --- RL integration ---
    state_feature_names = Column(JSON, nullable=False, default=list)
    # ["ek_lt_risk", "ek_is_q4"] — feature names appended to TRM state vectors
    reward_shaping_bonus = Column(Float, nullable=False, default=0.05)
    # Max bonus/penalty for aligned/contradicting decisions (GENUINE only)
    cdt_uncertainty_multiplier = Column(Float, nullable=False, default=1.0)
    # CDT interval width multiplier when conditions active (>1.0 = wider)

    # --- Lifecycle ---
    status = Column(String(20), nullable=False, default="CANDIDATE")
    stale_after_days = Column(Integer, nullable=False, default=180)
    last_validated_at = Column(DateTime, nullable=True)
    validated_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contradiction_id = Column(
        Integer, ForeignKey("experiential_knowledge.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_id = Column(
        Integer, ForeignKey("experiential_knowledge.id", ondelete="SET NULL"), nullable=True
    )
    retired_reason = Column(Text, nullable=True)

    # --- RAG ---
    summary = Column(Text, nullable=False)
    # "Supplier X (ID 42) lead times increase ~50% in Q4 due to harvest season"
    embedding = Column(Vector(768)) if Vector else Column(JSON, nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ek_tenant_config", "tenant_id", "config_id"),
        Index("idx_ek_tenant_config_status", "tenant_id", "config_id", "status"),
        Index("idx_ek_status", "status"),
        Index("idx_ek_pattern_type", "pattern_type"),
        Index("idx_ek_entity_type", "entity_type"),
    )

    def __repr__(self):
        return (
            f"<ExperientialKnowledge id={self.id} "
            f"pattern={self.pattern_type} status={self.status} "
            f"type={self.knowledge_type}>"
        )

    def is_active(self):
        return self.status == "ACTIVE"

    def is_genuine(self):
        return self.knowledge_type == "GENUINE"

    def evaluate_conditions(self, context: dict) -> bool:
        """Check if this entity's conditions match the given context.

        Args:
            context: Dict with keys like 'quarter', 'month', 'day_of_week',
                     'supplier_id', 'product_id', 'site_id', etc.

        Returns:
            True if all conditions in self.conditions match the context.
        """
        if not self.conditions:
            return True  # No conditions = always active

        for key, expected in self.conditions.items():
            if key not in context:
                continue  # Missing context key = don't filter on it
            actual = context[key]
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    def get_state_features(self) -> dict:
        """Return state feature dict for TRM state augmentation.

        Returns dict of feature_name → feature_value.
        Only meaningful when conditions have been evaluated as True.
        """
        features = {}
        for fname in (self.state_feature_names or []):
            # Use the effect multiplier as the feature value
            features[fname] = self.effect.get("multiplier", 1.0) * self.confidence
        return features

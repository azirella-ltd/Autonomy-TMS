"""
Tenant Configuration

Stores per-tenant settings for display preferences and agent autonomy thresholds.

Agent Autonomy Thresholds (3D routing):
  - urgency_threshold: Minimum urgency to always surface for human review
  - likelihood_threshold: Minimum agent confidence to auto-action
  - benefit_threshold: Minimum expected $ benefit to auto-action

Display Preferences:
  - display_identifiers: "name" (human-readable) or "id" (raw IDs)

Defaults are populated at tenant creation time. Only the tenant admin
can modify these settings.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

# Valid values for display_identifiers tenant preference
DISPLAY_IDENTIFIER_CHOICES = ("name", "id")

from app.db.base_class import Base


# ── Canonical TRM type keys (must match DECISION_TYPE_TABLE_MAP) ────────────
TRM_TYPE_KEYS = [
    "atp", "rebalancing", "po_creation", "order_tracking",
    "mo_execution", "to_execution", "quality", "maintenance",
    "subcontracting", "forecast_adjustment", "inventory_buffer",
]


class TenantBscConfig(Base):
    """
    Per-tenant configuration for display preferences and agent autonomy.

    Populated at tenant creation time with defaults. Only tenant admins
    can modify these settings.

    FK constraints are enforced at the DB level (tenant_id → tenants.id CASCADE,
    updated_by_id → users.id SET NULL).
    """

    __tablename__ = "tenant_bsc_config"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_bsc_config_tenant_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to tenants.id enforced at DB level
    tenant_id = Column(Integer, nullable=False, index=True)

    # ── Agent Autonomy Thresholds (3D routing) ───────────────────────────
    # urgency_threshold: Minimum urgency to surface for human review.
    #   Decisions ABOVE this are always surfaced regardless of confidence.
    #   Default 0.65 maps to "High" urgency tier.
    urgency_threshold = Column(Float, nullable=False, default=0.65)

    # likelihood_threshold: Minimum agent confidence to auto-action.
    #   For decisions BELOW urgency_threshold, if agent confidence >= this,
    #   the agent auto-actions. If confidence < this, surface for validation.
    #   Default 0.70 = agent must be 70%+ confident to act alone on routine items.
    likelihood_threshold = Column(Float, nullable=False, default=0.70)

    # ── Benefit threshold (3D routing, Mar 2026) ──────────────────────────
    # Minimum expected_benefit ($) for a decision to be auto-actioned when
    # the agent is confident.  Below this, even confident decisions are
    # surfaced because the stakes are too low to justify autonomous execution
    # without awareness.  Default $0 = benefit does not gate auto-action
    # (backward compatible with 2×2 matrix).
    benefit_threshold = Column(Float, nullable=False, default=0.0)

    # ── Display Preferences ─────────────────────────────────────────────────
    # Controls whether the UI shows human-readable names or raw IDs for
    # products, sites, and other entities.  Default "name" is best for demos
    # and new users; "id" suits experienced planners who think in SKU codes.
    display_identifiers = Column(
        String(10), nullable=False, default="name", server_default="name",
    )

    @validates("display_identifiers")
    def _validate_display_identifiers(self, _key, value):
        if value not in DISPLAY_IDENTIFIER_CHOICES:
            raise ValueError(
                f"display_identifiers must be one of {DISPLAY_IDENTIFIER_CHOICES}, got '{value}'"
            )
        return value

    # ── Audit ────────────────────────────────────────────────────────────────
    notes = Column(Text, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # FK to users.id enforced at DB level
    updated_by_id = Column(Integer, nullable=True)


class TenantDecisionThreshold(Base):
    """Per-TRM-type routing thresholds for the Decision Stream.

    Allows tenants to tune autonomy thresholds independently per decision type.
    For example, quality disposition may require lower likelihood thresholds
    (always surface) while routine rebalancing may tolerate higher autonomy.

    If no row exists for a (tenant_id, trm_type), the tenant-level defaults
    from TenantBscConfig are used as fallback.

    Three-dimensional routing (Kahneman-informed, Mar 2026):
      - urgency_threshold: min cost_of_inaction × time_pressure to always surface
      - likelihood_threshold: min agent confidence to auto-action
      - benefit_threshold: min expected $ benefit to auto-action

    Routing is grounded in Kahneman & Tversky's Prospect Theory (1979):
    losses loom ~2× larger than equivalent gains. The queue sort prioritises
    loss-prevention (high urgency) over gain-capture (high benefit) at equal
    dollar values, reflecting how human planners naturally triage.

    Reference: Kahneman, D. & Tversky, A. (1979). "Prospect Theory: An
    Analysis of Decision under Risk." Econometrica, 47(2), 263-291.
    """

    __tablename__ = "tenant_decision_thresholds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "trm_type", name="uq_tenant_trm_threshold"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    trm_type = Column(String(50), nullable=False)  # One of TRM_TYPE_KEYS

    # Thresholds (NULL = use tenant-level default from TenantBscConfig)
    urgency_threshold = Column(Float, nullable=True)
    likelihood_threshold = Column(Float, nullable=True)
    benefit_threshold = Column(Float, nullable=True)

    # Display / governance
    notes = Column(Text, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_id = Column(Integer, nullable=True)


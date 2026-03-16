"""
Tenant BSC (Balanced Scorecard) Configuration

Stores per-tenant weights for the simulation calibration balanced scorecard.
The CDT calibration loss function is a weighted combination of cost components.

Phase 1 (current): holding cost + backlog cost at equal weight.
Future phases will add customer service, operational, and strategic pillars.

Both holding_cost_weight and backlog_cost_weight represent costs to MINIMISE.
Higher values of either cost = worse outcome. Weights determine the relative
importance of each cost type in the CDT loss function.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base_class import Base


class TenantBscConfig(Base):
    """
    Per-tenant BSC weights for CDT simulation calibration.

    Weights define how much each cost component contributes to the aggregate
    loss used to calibrate Conformal Decision Theory bounds across all 11
    TRM agents.

    Constraint: all active weights must sum to 1.0 (enforced at API layer).
    FK constraints are enforced at the DB level (tenant_id → tenants.id CASCADE,
    updated_by_id → users.id SET NULL).

    Current active components (Phase 1):
      holding_cost_weight  — inventory holding cost per unit per day
      backlog_cost_weight  — backlog / stockout cost per unit per day

    Reserved for future BSC pillars (Phase 2+, kept at 0.0):
      customer_weight      — fill rate / OTIF
      operational_weight   — inventory turns, days-of-supply
      strategic_weight     — resilience, bullwhip ratio

    Default: holding=0.5, backlog=0.5 (equal cost weighting, both minimised).
    """

    __tablename__ = "tenant_bsc_config"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_bsc_config_tenant_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to tenants.id enforced at DB level
    tenant_id = Column(Integer, nullable=False, index=True)

    # ── Phase 1: cost weights ────────────────────────────────────────────────
    # Both costs are to be MINIMISED. Weights are relative importance.
    holding_cost_weight = Column(Float, nullable=False, default=0.5)
    backlog_cost_weight = Column(Float, nullable=False, default=0.5)

    # ── Phase 2+ (reserved, always 0.0 until metrics are wired up) ──────────
    customer_weight = Column(Float, nullable=False, default=0.0)
    operational_weight = Column(Float, nullable=False, default=0.0)
    strategic_weight = Column(Float, nullable=False, default=0.0)

    # ── Agent Autonomy ─────────────────────────────────────────────────────
    # Combined urgency+likelihood threshold below which agents auto-action
    # without human review. Lower = more human oversight, higher = more autonomy.
    # Range: 0.0 (surface everything) to 1.0 (agents fully autonomous).
    autonomy_threshold = Column(Float, nullable=False, default=0.5)

    # ── Audit ────────────────────────────────────────────────────────────────
    notes = Column(Text, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # FK to users.id enforced at DB level
    updated_by_id = Column(Integer, nullable=True)


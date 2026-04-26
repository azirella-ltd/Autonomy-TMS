"""
L4 Strategic Policy Parameters (θ) — current active policy per tenant × config.

Stores the policy vector that L3 Tactical / L2 Operational / L1 TRMs
consume as their decision envelope. One row per
`(tenant_id, COALESCE(config_id, 0), version)`; only one row per scope
has `effective_to IS NULL`.

See [docs/L4_POLICY_PARAMETERS_DESIGN.md](../../../docs/L4_POLICY_PARAMETERS_DESIGN.md)
for the schema rationale, validation invariants, and consumer contract.

## Versioning discipline (no in-place edits)

A change to active policy MUST create a *new* row with the patched
fields and `version = current.version + 1`, while the previous row
gets `effective_to = now()`. Never UPDATE an active row's θ in place
— that breaks the audit trail and the `source_proposal_id` linkage
back to the AgentDecision that drove the change.

Use `app.services.policy_service.apply_policy_patch()` rather than
mutating columns directly.

## Validation invariants (`validate()` enforces at write time)

  1. BSC weights sum to 1.0 ± 0.01.
  2. Mode-mix floors ≤ targets ≤ ceilings for every mode.
  3. Service-level tier priorities are unique integers.
  4. Carrier portfolio asset/contracted/spot ratios sum to 1.0 ± 0.01.

The DB-level partial unique index `uq_policy_active` enforces the
"single active policy per scope" invariant.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer,
    String, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


# ── Default JSONB blobs ─────────────────────────────────────────────
# Centralised so the migration server-defaults, Python-side defaults,
# and any test fixtures stay in sync. Keep these structures in lockstep
# with the docstring contracts in PolicyParameters.

_DEFAULT_SERVICE_LEVEL_TIERS: List[Dict[str, Any]] = [
    {"tier": "PLATINUM", "otd_target_pct": 99, "tender_accept_pct": 99, "priority": 1},
    {"tier": "GOLD",     "otd_target_pct": 95, "tender_accept_pct": 97, "priority": 2},
    {"tier": "SILVER",   "otd_target_pct": 90, "tender_accept_pct": 92, "priority": 3},
    {"tier": "BRONZE",   "otd_target_pct": 85, "tender_accept_pct": 88, "priority": 4},
    {"tier": "ECONOMY",  "otd_target_pct": 80, "tender_accept_pct": 80, "priority": 5},
]

_DEFAULT_MODE_MIX_TARGETS: Dict[str, Dict[str, float]] = {
    "FTL":          {"target_pct": 55, "floor_pct": 45, "ceiling_pct": 65},
    "LTL":          {"target_pct": 25, "floor_pct": 15, "ceiling_pct": 30},
    "INTERMODAL":   {"target_pct": 12, "floor_pct": 8,  "ceiling_pct": 20},
    "PARCEL":       {"target_pct": 5,  "floor_pct": 2,  "ceiling_pct": 10},
    "RAIL_CARLOAD": {"target_pct": 2,  "floor_pct": 0,  "ceiling_pct": 5},
    "AIR_STD":      {"target_pct": 1,  "floor_pct": 0,  "ceiling_pct": 3},
}

_DEFAULT_FLEET_COMPOSITION: Dict[str, Dict[str, float]] = {
    "DRY_VAN":         {"asset_target": 50, "3pl_target": 200, "spot_ratio": 0.15},
    "REEFER":          {"asset_target": 10, "3pl_target": 40,  "spot_ratio": 0.25},
    "FLATBED":         {"asset_target": 5,  "3pl_target": 20,  "spot_ratio": 0.30},
    "CONTAINER_40FT":  {"asset_target": 0,  "3pl_target": 100, "spot_ratio": 0.10},
    "CONTAINER_20FT":  {"asset_target": 0,  "3pl_target": 50,  "spot_ratio": 0.10},
}

_DEFAULT_CARRIER_PORTFOLIO_TARGETS: Dict[str, float] = {
    "asset_ratio":              0.25,
    "contracted_3pl_ratio":     0.60,
    "spot_market_ratio":        0.15,
    "max_single_carrier_pct":   0.30,
    "min_carrier_count_per_lane": 2,
    "brokerage_allowance_pct":  0.10,
}

_DEFAULT_NETWORK_TOPOLOGY: Dict[str, Any] = {
    "pattern":             "HUB_AND_SPOKE",   # HUB_AND_SPOKE, POINT_TO_POINT, HYBRID
    "hubs":                [],                # Site IDs designated as hubs
    "max_stops_per_route": 4,
    "cross_dock_strategy": "REGIONAL",        # REGIONAL, CENTRAL, NONE
    "intermodal_enabled":  True,
}

_DEFAULT_ESCALATION_THRESHOLDS: Dict[str, float] = {
    "tender_reject_rate_1h":         0.20,
    "exception_backlog_count":       20,
    "terminal_health_threshold":     0.5,
    "terminal_health_duration_hours": 2,
    "sla_miss_rate_4h":              0.10,
    "cascade_affected_shipments":    10,
}


# ── Source enum (string constants) ──────────────────────────────────


class PolicySource:
    """`policy_parameters.source` values."""
    STRATEGIC_AGENT = "STRATEGIC_AGENT"
    MANUAL = "MANUAL"
    BACKFILL = "BACKFILL"
    MIGRATION = "MIGRATION"


# ── Model ───────────────────────────────────────────────────────────


class PolicyParameters(Base):
    """L4 Strategic policy vector θ for one (tenant, config) scope.

    Tenant-wide default has `config_id IS NULL`; config-specific override
    sets `config_id` to a concrete value. Resolution is config-specific
    first, tenant-wide fallback second (see policy_service.get_active_policy).
    """
    __tablename__ = "policy_parameters"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    config_id = Column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=True,
    )

    # ── Effective window ────────────────────────────────────────────
    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    effective_to = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)

    # ── Authoring / audit ───────────────────────────────────────────
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    source = Column(
        String(30), nullable=False, default=PolicySource.STRATEGIC_AGENT,
        comment="STRATEGIC_AGENT | MANUAL | BACKFILL | MIGRATION",
    )
    # Soft FK to agent_decisions.id (no DB-level FK; agent_decisions
    # may live in a tenant-scoped subset and we don't want delete
    # cascades from there to rip out historical policies).
    source_proposal_id = Column(Integer, nullable=True)

    # ── Section 1: BSC weights ──────────────────────────────────────
    bsc_weight_financial = Column(Float, nullable=False, default=0.35)
    bsc_weight_customer = Column(Float, nullable=False, default=0.30)
    bsc_weight_internal = Column(Float, nullable=False, default=0.20)
    bsc_weight_learning = Column(Float, nullable=False, default=0.15)

    # ── Section 2-10: structured JSONB blobs ────────────────────────
    service_level_tiers = Column(
        JSONB, nullable=False, default=lambda: list(_DEFAULT_SERVICE_LEVEL_TIERS),
    )
    mode_mix_targets = Column(
        JSONB, nullable=False, default=lambda: dict(_DEFAULT_MODE_MIX_TARGETS),
    )
    mode_mix_period_days = Column(Integer, nullable=False, default=91)
    fleet_composition = Column(
        JSONB, nullable=False, default=lambda: dict(_DEFAULT_FLEET_COMPOSITION),
    )
    carrier_portfolio_targets = Column(
        JSONB, nullable=False, default=lambda: dict(_DEFAULT_CARRIER_PORTFOLIO_TARGETS),
    )

    # Sustainability
    co2_per_load_mile_ceiling_g = Column(Float, nullable=True)
    co2_measurement_method = Column(String(30), default="EPA_SMARTWAY")
    sustainability_penalty_weight = Column(Float, default=0.0)

    # Cost guardrails
    max_cost_delta_pct = Column(Float, nullable=False, default=0.10)
    max_expedite_premium_pct = Column(Float, nullable=False, default=0.50)
    detention_cost_cap_usd = Column(Float, nullable=True)
    accessorial_cap_usd = Column(Float, nullable=True)

    network_topology = Column(
        JSONB, nullable=False, default=lambda: dict(_DEFAULT_NETWORK_TOPOLOGY),
    )
    l3_cadence_overrides = Column(JSONB, default=dict)
    escalation_thresholds = Column(
        JSONB, nullable=False, default=lambda: dict(_DEFAULT_ESCALATION_THRESHOLDS),
    )
    extra_policy = Column(JSONB, default=dict)

    # ── Audit ───────────────────────────────────────────────────────
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index(
            "ix_policy_tenant_effective",
            "tenant_id", "effective_from", "effective_to",
        ),
        Index(
            "ix_policy_source_proposal",
            "source_proposal_id",
            postgresql_where=text("source_proposal_id IS NOT NULL"),
        ),
        # The unique-active partial index is created in the migration
        # (`uq_policy_active`) — needs `COALESCE(config_id, 0)` which
        # SQLAlchemy can't express portably here.
    )

    # ── Validation ──────────────────────────────────────────────────

    def validate(self) -> None:
        """Enforce the four invariants from the design doc.

        Raises:
            ValueError on any violation. Caller is expected to call
            this before commit (the service helper does so).
        """
        # 1. BSC weights sum to 1.0 ± 0.01
        total = (
            (self.bsc_weight_financial or 0)
            + (self.bsc_weight_customer or 0)
            + (self.bsc_weight_internal or 0)
            + (self.bsc_weight_learning or 0)
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"PolicyParameters: BSC weights must sum to 1.0 ± 0.01, got {total:.4f}"
            )

        # 2. Mode-mix floors ≤ targets ≤ ceilings
        for mode, cfg in (self.mode_mix_targets or {}).items():
            try:
                floor = float(cfg["floor_pct"])
                target = float(cfg["target_pct"])
                ceiling = float(cfg["ceiling_pct"])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(
                    f"PolicyParameters.mode_mix_targets[{mode!r}] malformed: {e}"
                )
            if not (floor <= target <= ceiling):
                raise ValueError(
                    f"PolicyParameters.mode_mix_targets[{mode!r}]: "
                    f"floor={floor} > target={target} > ceiling={ceiling}"
                )

        # 3. Service-level tier priorities unique
        priorities = [
            t.get("priority") for t in (self.service_level_tiers or [])
        ]
        if len(priorities) != len(set(priorities)):
            raise ValueError(
                f"PolicyParameters.service_level_tiers: duplicate priority "
                f"in {priorities!r}"
            )

        # 4. Carrier portfolio asset+contracted+spot sum to 1.0 ± 0.01
        portfolio = self.carrier_portfolio_targets or {}
        ratio_sum = (
            float(portfolio.get("asset_ratio") or 0)
            + float(portfolio.get("contracted_3pl_ratio") or 0)
            + float(portfolio.get("spot_market_ratio") or 0)
        )
        if not (0.99 <= ratio_sum <= 1.01):
            raise ValueError(
                f"PolicyParameters.carrier_portfolio_targets ratios must sum "
                f"to 1.0 ± 0.01, got {ratio_sum:.4f}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable snapshot. Useful for diffs against patches."""
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
        }

    def __repr__(self) -> str:
        return (
            f"<PolicyParameters tenant={self.tenant_id} "
            f"config={self.config_id} v{self.version} "
            f"source={self.source}>"
        )

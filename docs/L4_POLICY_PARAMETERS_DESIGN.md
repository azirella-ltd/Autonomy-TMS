# L4 Strategic Policy Parameters — Design Doc (v1 draft)

**Status:** Design, 2026-04-23. Scoped in `TMS_DECISION_HIERARCHY.md` §3.
**Layer:** L4 Strategic (12-18 month horizon, monthly cadence).

---

## 1. What this table does

L4 Strategic decisions (network design, carrier portfolio, fleet
composition, service tiers, mode-mix, BSC weights, sustainability
targets) produce a **policy parameter vector θ** that L3 Tactical
planners consume as their envelope. `policy_parameters` is the
canonical table that stores the current θ per tenant.

Not a decision log (those go in `agent_decisions` with
`decision_type='NETWORK_DESIGN'` etc.). This is the **active policy**
— one row per `(tenant_id, effective_from, effective_to)` describing
what L3 should plan against today.

---

## 2. Columns

```sql
CREATE TABLE policy_parameters (
    id               BIGSERIAL PRIMARY KEY,
    tenant_id        INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    config_id        INT REFERENCES supply_chain_configs(id) ON DELETE CASCADE,
                     -- NULL = applies to every config in this tenant

    -- Effective window
    effective_from   TIMESTAMP NOT NULL DEFAULT now(),
    effective_to     TIMESTAMP,  -- NULL = current policy
    version          INT NOT NULL DEFAULT 1,
                     -- monotonically increasing per (tenant, config) pair

    -- Authoring metadata
    created_by       INT REFERENCES users(id),
    approved_by      INT REFERENCES users(id),
    source           VARCHAR(30) NOT NULL DEFAULT 'STRATEGIC_AGENT',
                     -- STRATEGIC_AGENT, MANUAL, BACKFILL, MIGRATION
    source_proposal_id INT,
                     -- FK to agent_decisions.id when STRATEGIC_AGENT-authored

    -- ═══════════════════════════════════════════════════════════════
    -- Section 1: BSC weights (Balanced Scorecard)
    -- Sum to 1.0 (soft constraint; validator ensures |sum-1.0| < 0.01)
    -- ═══════════════════════════════════════════════════════════════
    bsc_weight_financial   FLOAT NOT NULL DEFAULT 0.35,  -- cost minimization
    bsc_weight_customer    FLOAT NOT NULL DEFAULT 0.30,  -- SLA achievement
    bsc_weight_internal    FLOAT NOT NULL DEFAULT 0.20,  -- operational efficiency
    bsc_weight_learning    FLOAT NOT NULL DEFAULT 0.15,  -- innovation / growth

    -- ═══════════════════════════════════════════════════════════════
    -- Section 2: Service-level tier definitions
    -- JSON array: customer tier → SLA target per metric
    -- ═══════════════════════════════════════════════════════════════
    service_level_tiers    JSONB NOT NULL DEFAULT '[
      {"tier": "PLATINUM",  "otd_target_pct": 99, "tender_accept_pct": 99, "priority": 1},
      {"tier": "GOLD",      "otd_target_pct": 95, "tender_accept_pct": 97, "priority": 2},
      {"tier": "SILVER",    "otd_target_pct": 90, "tender_accept_pct": 92, "priority": 3},
      {"tier": "BRONZE",    "otd_target_pct": 85, "tender_accept_pct": 88, "priority": 4},
      {"tier": "ECONOMY",   "otd_target_pct": 80, "tender_accept_pct": 80, "priority": 5}
    ]'::jsonb,

    -- ═══════════════════════════════════════════════════════════════
    -- Section 3: Mode-mix strategy
    -- Target percentage by transport mode, rolling 13-week window
    -- ═══════════════════════════════════════════════════════════════
    mode_mix_targets       JSONB NOT NULL DEFAULT '{
      "FTL":  {"target_pct": 55, "floor_pct": 45, "ceiling_pct": 65},
      "LTL":  {"target_pct": 25, "floor_pct": 15, "ceiling_pct": 30},
      "INTERMODAL": {"target_pct": 12, "floor_pct": 8, "ceiling_pct": 20},
      "PARCEL": {"target_pct": 5, "floor_pct": 2, "ceiling_pct": 10},
      "RAIL_CARLOAD": {"target_pct": 2, "floor_pct": 0, "ceiling_pct": 5},
      "AIR_STD": {"target_pct": 1, "floor_pct": 0, "ceiling_pct": 3}
    }'::jsonb,
    mode_mix_period_days   INT NOT NULL DEFAULT 91,  -- 13-week rolling

    -- ═══════════════════════════════════════════════════════════════
    -- Section 4: Fleet composition
    -- Target count per equipment type (asset-based); spot-market ratio
    -- ═══════════════════════════════════════════════════════════════
    fleet_composition      JSONB NOT NULL DEFAULT '{
      "DRY_VAN":   {"asset_target": 50, "3pl_target": 200, "spot_ratio": 0.15},
      "REEFER":    {"asset_target": 10, "3pl_target": 40,  "spot_ratio": 0.25},
      "FLATBED":   {"asset_target": 5,  "3pl_target": 20,  "spot_ratio": 0.30},
      "CONTAINER_40FT": {"asset_target": 0, "3pl_target": 100, "spot_ratio": 0.10},
      "CONTAINER_20FT": {"asset_target": 0, "3pl_target": 50,  "spot_ratio": 0.10}
    }'::jsonb,

    -- ═══════════════════════════════════════════════════════════════
    -- Section 5: Carrier portfolio envelope
    -- Not the full contract portfolio (that's in carrier_contract);
    -- just the strategic ratios L4 sets for L3 to plan within.
    -- ═══════════════════════════════════════════════════════════════
    carrier_portfolio_targets JSONB NOT NULL DEFAULT '{
      "asset_ratio": 0.25,            -- % of loads on own fleet
      "contracted_3pl_ratio": 0.60,    -- % on committed contract
      "spot_market_ratio": 0.15,       -- % on spot
      "max_single_carrier_pct": 0.30,  -- concentration limit per lane
      "min_carrier_count_per_lane": 2, -- diversification floor
      "brokerage_allowance_pct": 0.10  -- ceiling on broker-routed share
    }'::jsonb,

    -- ═══════════════════════════════════════════════════════════════
    -- Section 6: Sustainability targets
    -- ═══════════════════════════════════════════════════════════════
    co2_per_load_mile_ceiling_g FLOAT,  -- gCO2e per ton-mile; NULL = no target
    co2_measurement_method     VARCHAR(30) DEFAULT 'EPA_SMARTWAY',
                                        -- EPA_SMARTWAY, GLEC, CUSTOM
    sustainability_penalty_weight FLOAT DEFAULT 0.0,
                                        -- 0.0 = advisory only, >0 = penalize in BSC

    -- ═══════════════════════════════════════════════════════════════
    -- Section 7: Cost guardrails (for L2 + L3)
    -- ═══════════════════════════════════════════════════════════════
    max_cost_delta_pct         FLOAT NOT NULL DEFAULT 0.10,
                                        -- L2 can override L3 plan up to this delta
    max_expedite_premium_pct   FLOAT NOT NULL DEFAULT 0.50,
                                        -- Max premium for expedited service
    detention_cost_cap_usd     FLOAT,   -- cap on detention charges accepted without escalation
    accessorial_cap_usd        FLOAT,   -- cap on accessorial charges accepted

    -- ═══════════════════════════════════════════════════════════════
    -- Section 8: Network topology
    -- References to the strategic network envelope (not the detailed
    -- lane list — that lives in transportation_lane).
    -- ═══════════════════════════════════════════════════════════════
    network_topology           JSONB NOT NULL DEFAULT '{
      "pattern": "HUB_AND_SPOKE",        -- HUB_AND_SPOKE, POINT_TO_POINT, HYBRID
      "hubs": [],                         -- array of Site IDs designated as hubs
      "max_stops_per_route": 4,
      "cross_dock_strategy": "REGIONAL",  -- REGIONAL, CENTRAL, NONE
      "intermodal_enabled": true
    }'::jsonb,

    -- ═══════════════════════════════════════════════════════════════
    -- Section 9: Planning cadence overrides
    -- L3 runs its pipeline daily by default; L4 can override per tenant.
    -- ═══════════════════════════════════════════════════════════════
    l3_cadence_overrides       JSONB DEFAULT '{}'::jsonb,
                                        -- e.g., {"demand_potential_cron": "0 5 * * *",
                                        --        "constrained_plan_cron": "0 6 * * *"}

    -- ═══════════════════════════════════════════════════════════════
    -- Section 10: Exception escalation thresholds
    -- L1/L2 use these to decide when to escalate to L3/L4
    -- ═══════════════════════════════════════════════════════════════
    escalation_thresholds      JSONB NOT NULL DEFAULT '{
      "tender_reject_rate_1h": 0.20,
      "exception_backlog_count": 20,
      "terminal_health_threshold": 0.5,
      "terminal_health_duration_hours": 2,
      "sla_miss_rate_4h": 0.10,
      "cascade_affected_shipments": 10
    }'::jsonb,

    -- ═══════════════════════════════════════════════════════════════
    -- Section 11: Raw policy blob (future-proof extension)
    -- Anything not structured above; consumed by agents that read θ.
    -- ═══════════════════════════════════════════════════════════════
    extra_policy               JSONB DEFAULT '{}'::jsonb,

    -- Audit
    created_at                 TIMESTAMP NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMP NOT NULL DEFAULT now()
);

-- Indexes
CREATE UNIQUE INDEX uq_policy_active
    ON policy_parameters(tenant_id, COALESCE(config_id, 0))
    WHERE effective_to IS NULL;
    -- Guarantees at most one active policy per (tenant, config).
    -- config_id IS NULL is the tenant-wide default.

CREATE INDEX ix_policy_tenant_effective
    ON policy_parameters(tenant_id, effective_from DESC, effective_to DESC);

CREATE INDEX ix_policy_source_proposal
    ON policy_parameters(source_proposal_id)
    WHERE source_proposal_id IS NOT NULL;
```

---

## 3. Invariants enforced by application code

1. **Single active policy per scope.** At most one row with `effective_to IS NULL` per `(tenant_id, config_id)` pair. The `UQ_policy_active` index enforces this at the DB level, using `COALESCE(config_id, 0)` so `NULL` config_id counts as a distinct scope.

2. **BSC weights sum to 1.0 ± 0.01.** Validator on write:
   ```python
   total = bsc_weight_financial + bsc_weight_customer + bsc_weight_internal + bsc_weight_learning
   assert 0.99 <= total <= 1.01, f"BSC weights must sum to 1.0, got {total}"
   ```

3. **Mode-mix floors + ceilings bracket targets.** Validator:
   ```python
   for mode, config in mode_mix_targets.items():
       assert config['floor_pct'] <= config['target_pct'] <= config['ceiling_pct']
   ```

4. **Service-level tier priorities unique.** No two tiers share the same `priority` integer.

5. **Carrier portfolio ratios sum to 1.0 ± 0.01** (asset + contracted_3pl + spot).

6. **Versioned, not updated.** Changes create a new row (with `version += 1`), and the previous row gets `effective_to = now()` via `UPDATE`. Never `UPDATE` an active row's θ values in place.

---

## 4. How other layers consume θ

### L3 Tactical
```python
# In L3 Integrated Balancer — before solving constrained plan
θ = session.execute(
    select(PolicyParameters).where(
        PolicyParameters.tenant_id == tenant_id,
        or_(PolicyParameters.config_id == config_id,
            PolicyParameters.config_id.is_(None)),
        PolicyParameters.effective_to.is_(None),
    ).order_by(PolicyParameters.config_id.nullslast())  # config-specific beats tenant-wide
).scalars().first()

# L3 uses:
bsc_objective = (θ.bsc_weight_financial * cost_vec +
                 θ.bsc_weight_customer * sla_vec +
                 θ.bsc_weight_internal * efficiency_vec +
                 θ.bsc_weight_learning * innovation_vec)

mode_mix_constraint = θ.mode_mix_targets
fleet_envelope = θ.fleet_composition
carrier_diversification = θ.carrier_portfolio_targets
```

### L2 Operational
```python
# Terminal Coordinator reads cost-delta ceiling + escalation thresholds
if override_cost_delta_pct > θ.max_cost_delta_pct:
    escalate_to_l3()

health = terminal_health_signal.composite_health
if health < θ.escalation_thresholds['terminal_health_threshold'] and \
   duration_below_threshold >= θ.escalation_thresholds['terminal_health_duration_hours']:
    trigger_l3_replan()
```

### L1 TRMs
```python
# DockSchedulingTRM uses service-level tier priority
customer_tier = customer.service_tier
priority_from_θ = next(t for t in θ.service_level_tiers if t['tier'] == customer_tier)['priority']

# EquipmentRepositionTRM reads fleet composition target
fleet_target = θ.fleet_composition[equipment_type]['asset_target']
```

---

## 5. Provisioning flow

### Tenant creation
```python
# In tenant_service.create_tenant, after Tenant + Customer are created
default_policy = PolicyParameters(
    tenant_id=tenant.id,
    config_id=None,                    # tenant-wide default
    source='MIGRATION',
    version=1,
    # All other fields use DB defaults (see column definitions)
)
db.add(default_policy)
db.commit()
```

### Config creation
Config-specific policies are **optional** — by default a config inherits from the tenant-wide default. A tenant admin creates a config-specific policy only when they need to diverge (e.g., a test config with different BSC weights for a what-if analysis).

### Strategic agent proposal flow
```python
# When L4 Strategic agent proposes a new policy
proposal = AgentDecision(
    tenant_id=tenant_id,
    decision_type=DecisionType.BSC_WEIGHTS,  # or NETWORK_DESIGN, CARRIER_CONTRACT_PORTFOLIO, etc.
    agent_recommendation="Reduce financial weight to 0.30, increase customer to 0.35",
    agent_reasoning="...",
    status=DecisionStatus.INFORMED,       # surfaced to exec for review
    context_data={"proposed_theta_patch": {...}},
)
db.add(proposal)

# Exec approves via UI → strategic_service.apply_policy_patch()
def apply_policy_patch(proposal_id, approver_user_id):
    proposal = fetch_proposal(proposal_id)
    current_θ = fetch_active_policy(proposal.tenant_id, proposal.config_id)

    # Close current policy
    current_θ.effective_to = datetime.utcnow()

    # Create new policy with patched fields + version bump
    new_θ = PolicyParameters(
        **copy_from(current_θ),
        **proposal.context_data['proposed_theta_patch'],
        version=current_θ.version + 1,
        source='STRATEGIC_AGENT',
        source_proposal_id=proposal.id,
        approved_by=approver_user_id,
        effective_from=datetime.utcnow(),
        effective_to=None,
    )
    db.add(new_θ)

    proposal.status = DecisionStatus.ACTIONED
    proposal.action_timestamp = datetime.utcnow()
```

---

## 6. Alembic migration (first cut)

```python
"""Add policy_parameters table for L4 Strategic layer

Revision ID: 20260423_policy_parameters
Revises: <latest head>
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    if _table_exists('policy_parameters'):
        return

    op.create_table(
        'policy_parameters',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('config_id', sa.Integer, sa.ForeignKey('supply_chain_configs.id', ondelete='CASCADE')),
        sa.Column('effective_from', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('effective_to', sa.DateTime),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('approved_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('source', sa.String(30), nullable=False, server_default='STRATEGIC_AGENT'),
        sa.Column('source_proposal_id', sa.Integer),
        sa.Column('bsc_weight_financial', sa.Float, nullable=False, server_default='0.35'),
        sa.Column('bsc_weight_customer', sa.Float, nullable=False, server_default='0.30'),
        sa.Column('bsc_weight_internal', sa.Float, nullable=False, server_default='0.20'),
        sa.Column('bsc_weight_learning', sa.Float, nullable=False, server_default='0.15'),
        sa.Column('service_level_tiers', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('mode_mix_targets', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('mode_mix_period_days', sa.Integer, nullable=False, server_default='91'),
        sa.Column('fleet_composition', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('carrier_portfolio_targets', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('co2_per_load_mile_ceiling_g', sa.Float),
        sa.Column('co2_measurement_method', sa.String(30), server_default='EPA_SMARTWAY'),
        sa.Column('sustainability_penalty_weight', sa.Float, server_default='0.0'),
        sa.Column('max_cost_delta_pct', sa.Float, nullable=False, server_default='0.10'),
        sa.Column('max_expedite_premium_pct', sa.Float, nullable=False, server_default='0.50'),
        sa.Column('detention_cost_cap_usd', sa.Float),
        sa.Column('accessorial_cap_usd', sa.Float),
        sa.Column('network_topology', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('l3_cadence_overrides', postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('escalation_thresholds', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[…default JSON…]'::jsonb")),
        sa.Column('extra_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        'uq_policy_active',
        'policy_parameters',
        ['tenant_id', sa.text('COALESCE(config_id, 0)')],
        unique=True,
        postgresql_where=sa.text('effective_to IS NULL'),
    )
    op.create_index('ix_policy_tenant_effective', 'policy_parameters',
                    ['tenant_id', 'effective_from', 'effective_to'])
    op.create_index('ix_policy_source_proposal', 'policy_parameters',
                    ['source_proposal_id'],
                    postgresql_where=sa.text('source_proposal_id IS NOT NULL'))

    # Backfill: one default row per existing tenant
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO policy_parameters (tenant_id, source, version)
        SELECT id, 'MIGRATION', 1 FROM tenants
    """))


def _table_exists(name):
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :n"
    ), {'n': name}).scalar())


def downgrade():
    if _table_exists('policy_parameters'):
        op.drop_index('ix_policy_source_proposal', 'policy_parameters')
        op.drop_index('ix_policy_tenant_effective', 'policy_parameters')
        op.drop_index('uq_policy_active', 'policy_parameters')
        op.drop_table('policy_parameters')
```

---

## 7. SQLAlchemy model sketch

```python
# backend/app/models/policy_parameters.py
from datetime import datetime
from sqlalchemy import (
    BigInteger, Integer, Float, String, DateTime, ForeignKey,
    Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class PolicyParameters(Base):
    __tablename__ = "policy_parameters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    effective_from: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="STRATEGIC_AGENT")
    source_proposal_id: Mapped[int | None] = mapped_column(Integer)

    # Section 1: BSC weights
    bsc_weight_financial: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    bsc_weight_customer:  Mapped[float] = mapped_column(Float, nullable=False, default=0.30)
    bsc_weight_internal:  Mapped[float] = mapped_column(Float, nullable=False, default=0.20)
    bsc_weight_learning:  Mapped[float] = mapped_column(Float, nullable=False, default=0.15)

    # Sections 2-10: JSONB (see migration for defaults)
    service_level_tiers:       Mapped[list] = mapped_column(JSONB, nullable=False)
    mode_mix_targets:          Mapped[dict] = mapped_column(JSONB, nullable=False)
    mode_mix_period_days:      Mapped[int]  = mapped_column(Integer, nullable=False, default=91)
    fleet_composition:         Mapped[dict] = mapped_column(JSONB, nullable=False)
    carrier_portfolio_targets: Mapped[dict] = mapped_column(JSONB, nullable=False)
    co2_per_load_mile_ceiling_g:     Mapped[float | None] = mapped_column(Float)
    co2_measurement_method:          Mapped[str | None]   = mapped_column(String(30), default="EPA_SMARTWAY")
    sustainability_penalty_weight:   Mapped[float]        = mapped_column(Float, default=0.0)
    max_cost_delta_pct:              Mapped[float]        = mapped_column(Float, nullable=False, default=0.10)
    max_expedite_premium_pct:        Mapped[float]        = mapped_column(Float, nullable=False, default=0.50)
    detention_cost_cap_usd:          Mapped[float | None] = mapped_column(Float)
    accessorial_cap_usd:             Mapped[float | None] = mapped_column(Float)
    network_topology:                Mapped[dict]         = mapped_column(JSONB, nullable=False)
    l3_cadence_overrides:            Mapped[dict]         = mapped_column(JSONB, default=dict)
    escalation_thresholds:           Mapped[dict]         = mapped_column(JSONB, nullable=False)
    extra_policy:                    Mapped[dict]         = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_policy_tenant_effective', 'tenant_id', 'effective_from', 'effective_to'),
    )

    # Validation at application layer (DB guards via index):
    def validate(self):
        total = (self.bsc_weight_financial + self.bsc_weight_customer +
                 self.bsc_weight_internal + self.bsc_weight_learning)
        assert 0.99 <= total <= 1.01, f"BSC weights must sum to 1.0, got {total}"

        for mode, cfg in (self.mode_mix_targets or {}).items():
            assert cfg['floor_pct'] <= cfg['target_pct'] <= cfg['ceiling_pct'], \
                f"Mode {mode}: floor {cfg['floor_pct']} > target {cfg['target_pct']} > ceiling {cfg['ceiling_pct']}"

        priorities = [t['priority'] for t in (self.service_level_tiers or [])]
        assert len(priorities) == len(set(priorities)), \
            "Service-level tier priorities must be unique"

        portfolio = self.carrier_portfolio_targets or {}
        ratio_sum = (portfolio.get('asset_ratio', 0) +
                     portfolio.get('contracted_3pl_ratio', 0) +
                     portfolio.get('spot_market_ratio', 0))
        assert 0.99 <= ratio_sum <= 1.01, \
            f"Carrier portfolio ratios must sum to 1.0, got {ratio_sum}"
```

---

## 8. Service helper

```python
# backend/app/services/policy_service.py
from typing import Optional
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.models.policy_parameters import PolicyParameters


def get_active_policy(
    db: Session,
    *,
    tenant_id: int,
    config_id: Optional[int] = None,
) -> PolicyParameters:
    """Resolve active policy. Config-specific policy beats tenant-wide default."""
    q = (
        select(PolicyParameters)
        .where(
            PolicyParameters.tenant_id == tenant_id,
            or_(
                PolicyParameters.config_id == config_id,
                PolicyParameters.config_id.is_(None),
            ),
            PolicyParameters.effective_to.is_(None),
        )
        .order_by(PolicyParameters.config_id.nullslast())
    )
    policy = db.execute(q).scalars().first()
    if not policy:
        raise RuntimeError(
            f"No active policy for tenant={tenant_id}, config={config_id}. "
            "Provisioning may have skipped policy creation."
        )
    return policy


def apply_policy_patch(
    db: Session,
    *,
    tenant_id: int,
    config_id: Optional[int],
    patch: dict,
    approved_by: int,
    source_proposal_id: Optional[int] = None,
) -> PolicyParameters:
    """Supersede the current policy with a patched new version."""
    current = get_active_policy(db, tenant_id=tenant_id, config_id=config_id)
    current.effective_to = datetime.utcnow()

    new_fields = {c.name: getattr(current, c.name)
                  for c in PolicyParameters.__table__.columns
                  if c.name not in {'id', 'effective_from', 'effective_to', 'version',
                                    'created_at', 'updated_at', 'source', 'source_proposal_id',
                                    'approved_by'}}
    new_fields.update(patch)

    new_policy = PolicyParameters(
        **new_fields,
        version=current.version + 1,
        source='STRATEGIC_AGENT' if source_proposal_id else 'MANUAL',
        source_proposal_id=source_proposal_id,
        approved_by=approved_by,
        effective_from=datetime.utcnow(),
        effective_to=None,
    )
    new_policy.validate()
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)
    return new_policy
```

---

## 9. L4 Strategic agent — future shape (not in this doc's scope)

Once `policy_parameters` ships, the L4 agent (S&OP GraphSAGE, analog to
SCP's) reads KPI outcomes over rolling windows + the current θ, and
proposes patches via `AgentDecision` rows with
`decision_type='BSC_WEIGHTS'` etc.

Out of scope for this doc:
- L4 agent architecture (next design doc)
- Proposal approval UI (frontend work)
- Scenario-analysis on proposed θ changes

In scope for this doc:
- The schema + migration + model + service helper above. Ready to ship
  as soon as the Phase A twin + Stage B substrate extraction finish.

---

## 10. Migration sequencing

### Prerequisites
- Item 1.13 Stage B + C — SCP-fork services + models removed, so
  `Base.metadata` doesn't carry SCP-domain tables that would interact
  poorly with policy_parameters backfill.
- Item 1.13 Stage E — capability slugs cleaned, so L4 permission
  (`view_policy_parameters`, `edit_policy_parameters`) land on a clean
  slate.

### Order of operations
1. This doc reviewed + signed off.
2. Alembic migration scaffolded (this doc §6 as starter).
3. Model + service helper landed (this doc §7 + §8).
4. Tenant provisioning wired (auto-create default policy on tenant creation).
5. First consumer: L2 Terminal Coordinator reads `escalation_thresholds`
   and `max_cost_delta_pct` from policy. (Only once L2 ships.)
6. Second consumer: L3 Integrated Balancer reads BSC weights +
   mode-mix + fleet envelope. (Only once L3 ships.)

Until L2 + L3 consume it, `policy_parameters` stores θ that nothing
reads — but provisions tenants cleanly for when they do.

---

## 11. Cross-references

- [TMS_DECISION_HIERARCHY.md](TMS_DECISION_HIERARCHY.md) §3 — L4
  decision enumeration
- [L2_TERMINAL_COORDINATOR_DESIGN.md](L2_TERMINAL_COORDINATOR_DESIGN.md)
  §4.4 — L2 consumes θ
- [TACTICAL_PLANNING_REARCHITECTURE.md](TACTICAL_PLANNING_REARCHITECTURE.md)
  §4.3 — L3 Integrated Balancer consumes θ (BSC weights)
- Autonomy-Core `governance/bsc.py` — future canonical BSC types
  (currently SCP-local)

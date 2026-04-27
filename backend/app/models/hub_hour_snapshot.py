"""
L2 Phase-2 hub-hour snapshot — GATv2-ready node-feature representation.

Per ``docs/L2_TERMINAL_COORDINATOR_DESIGN.md`` §6 Phase 2: build the
data substrate the future GATv2+GRU agent (Phase 3) will train on.
One row per (tenant, config, hub, hour) — append-only time-series.

The Phase-1 ``terminal_health_signal`` table captures 5 component KPIs
sufficient for the deterministic-heuristic coordinator. This table
captures the richer per-resource graph-node features the GATv2 needs:

  * Per dock-door queue depth + status
  * Per outbound lane queue + recent reject rate
  * Per inbound lane expected-arrival count
  * Per equipment-pool inventory by status
  * Per carrier on-property count + time-at-terminal

Stored as JSONB blobs keyed by ``node_features``,
``edge_features``, ``hub_summary`` so the schema can grow without
migrations as new feature dimensions are added during graph-design
iteration.

When Phase A (TMS digital twin) ships hub-hour snapshots from twin
rollouts, the same schema is what those rollouts write to — the
production extractor (``HubHourSnapshotService``) and the twin
generator share the same columns. That keeps BC training on twin data
identical in shape to live ops, which makes the BC→PPO transition
mechanical.

## Why JSONB and not normalised columns

The graph schema is going to evolve significantly during Phase 3
agent design (which features the GATv2 ends up using is an empirical
question). JSONB lets us add / remove feature dimensions per-row
without ALTER TABLE on a hot operational table. Once the schema
stabilises (post Phase 4 rollout) we extract hot-path features into
typed columns, but for now the JSONB is the right compromise.

## Idempotency

Keyed on ``(tenant_id, config_id, hub_site_id, observed_at)`` —
re-running an hour produces no-op when a row already exists. The
extractor uses ``ON CONFLICT DO NOTHING`` against the unique
constraint.
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Index, Integer, String,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class HubHourSnapshot(Base):
    """Per-hub, per-hour graph snapshot for L2 GATv2+GRU training.

    Append-only time-series. The ``node_features`` /
    ``edge_features`` / ``hub_summary`` columns are JSONB blobs; the
    GATv2 graph constructor reads from them at training time (and the
    deterministic coordinator can use ``hub_summary`` directly today).
    """
    __tablename__ = "hub_hour_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "config_id", "hub_site_id", "observed_at",
            name="uq_hub_hour_snapshot",
        ),
        Index(
            "idx_hub_hour_snapshot_lookup",
            "tenant_id", "hub_site_id", "observed_at",
        ),
        Index(
            "idx_hub_hour_snapshot_recent",
            "tenant_id", "observed_at",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_id = Column(
        Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    hub_site_id = Column(
        Integer, ForeignKey("site.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at = Column(
        DateTime, nullable=False,
        comment="Snapshot timestamp; typically aligned to hour boundary",
    )

    # ── JSONB feature payloads ─────────────────────────────────────
    # Per-node features keyed by node_type (dock_door, outbound_lane,
    # inbound_lane, equipment_pool, carrier_presence, shipment_queue).
    # Each entry is a list of {node_id, ...feature_dict} dicts.
    node_features = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Per-edge features keyed by edge_type (dock_to_shipment,
    # lane_to_shipment, carrier_to_lane, equipment_to_lane,
    # trm_to_resource). Sparse: only present edges are listed.
    edge_features = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Hub-level scalar summary — quick-access KPIs the heuristic
    # coordinator + analytics can use without parsing node_features.
    # Subset: dock_utilization_pct, tender_reject_rate_1h,
    # exception_backlog_count, equipment_imbalance, sla_miss_rate_1h.
    # Mirrors the Phase-1 terminal_health_signal columns for quick
    # cross-table joins.
    hub_summary = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Snapshot-time policy θ snapshot — pulled from active
    # PolicyParameters at extraction time. Letting the snapshot carry
    # the policy means the trained agent learns the policy-conditioned
    # action even when policy changes mid-history.
    policy_snapshot = Column(JSONB, server_default=text("'{}'::jsonb"))

    # Provenance — was this written by live operations or by the
    # digital twin? Phase 3 BC warmup may want to filter on this.
    # Open taxonomy: "live" / "twin" / "twin_<scenario>" / "manual".
    # Default "live"; the twin extractor sets explicitly.
    source = Column(
        String(30), nullable=False, server_default=text("'live'"),
    )

    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
    )

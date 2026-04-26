"""
L2 Terminal Coordinator data plane.

Three tables that the Terminal Coordinator (always-on hub-local agent)
writes to and L1 TRMs / L3 planners read from:

  * terminal_urgency_override   — modulates an L1 TRM's baseline urgency
                                  per (hub, trm_type) for a short TTL
  * lane_waterfall_override     — caps tender-waterfall depth per
                                  (hub, lane, mode) for a short TTL
  * terminal_health_signal      — append-only KPI snapshot per hub,
                                  consumed by L3 to decide on re-plans

See docs/L2_TERMINAL_COORDINATOR_DESIGN.md §5 for the full contract.

## Why TMS-side, not Core-side

Per `.claude/rules/transport-plane-invariant.md`: terminal-coordinator
overrides + per-hub health signals are transport-plane substrate with
no plausible cross-product consumer (SCP/CRM/WMS would not query them).
Core can absorb later if a cross-product analog emerges; not now.

## TTL semantics

`expires_at` is a soft TTL — the coordinator re-fires overrides when
conditions persist rather than carrying long-lived rows. Consumer L1
TRMs filter `WHERE expires_at > NOW()` on every read. A separate
hourly cleanup job (TerminalCoordinatorService.purge_expired) removes
rows older than 7 days for table-size hygiene; un-expired rows from
the past are kept as an audit trail.
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index,
    Integer, SmallInteger, String, Text, text,
)

from .base import Base


# ── Constants for trm_type values (string literals on this side; the
# canonical mapping is in app.services.powell.agent_decision_writer
# `_TRM_TO_DECISION_TYPE`)


class L2TrendDirection:
    """`terminal_health_signal.trend_7d` values."""
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"


class TerminalUrgencyOverride(Base):
    """L2 → L1: bump or damp a TRM's urgency at this hub."""
    __tablename__ = "terminal_urgency_override"

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
    trm_type = Column(String(30), nullable=False, comment="One of 11 canonical TMS TRM types")

    # Urgency multiplier applied to the TRM's baseline urgency.
    # Range [0.5, 2.0] — the coordinator can't completely silence a TRM
    # nor push it past 2× nominal. Application code clamps on read so
    # bad inserts don't propagate.
    urgency_multiplier = Column(Float, nullable=False, default=1.0)

    expires_at = Column(DateTime, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_terminal_urgency_active",
            "tenant_id", "hub_site_id", "trm_type", "expires_at",
        ),
    )


class LaneWaterfallOverride(Base):
    """L2 → L1: limit tender-waterfall depth on a lane."""
    __tablename__ = "lane_waterfall_override"

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
    lane_id = Column(
        Integer, ForeignKey("transportation_lane.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode = Column(String(20), nullable=False)

    waterfall_depth = Column(
        SmallInteger, nullable=False,
        comment="Number of carriers to tender before falling to spot/broker",
    )

    expires_at = Column(DateTime, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_lane_waterfall_active",
            "tenant_id", "hub_site_id", "lane_id", "mode", "expires_at",
        ),
    )


class TerminalHealthSignal(Base):
    """Hub KPI snapshot. Append-only — L3 polls this to decide on re-plans.

    `composite_health < 0.5` for ≥ `terminal_health_duration_hours`
    (from policy.escalation_thresholds) triggers L3 to re-solve the
    constrained plan for this hub's lanes.
    """
    __tablename__ = "terminal_health_signal"

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
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    composite_health = Column(Float, nullable=False, comment="0..1 (0 critical, 1 nominal)")

    # Per-axis component KPIs that compose into composite_health.
    dock_utilization_pct = Column(Float)
    tender_reject_rate_1h = Column(Float)
    exception_backlog_count = Column(Integer)
    equipment_imbalance = Column(
        Float, comment="signed: + surplus, − deficit (loads-equivalent)",
    )
    sla_miss_rate_1h = Column(Float)

    trend_7d = Column(
        String(20), comment="IMPROVING | STABLE | DEGRADING",
    )
    active_overrides_count = Column(SmallInteger, default=0)

    __table_args__ = (
        Index(
            "ix_terminal_health_lookup",
            "tenant_id", "hub_site_id", "timestamp",
        ),
    )

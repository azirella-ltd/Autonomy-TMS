"""
Intermodal network + spot-rate models for TMS.

Substrate populated by Sprint-2 ratesheet ingestion (FreightWaves SONAR /
DAT / Truckstop) and external ramp-congestion feeds, consumed by
IntermodalTransferTRM at decision time.

Until the ingestion service lands, IntermodalTransferTRM keeps accepting
planner-supplied overrides as the primary input path; reading from these
tables is the *fallback* enriching the state-builder when overrides are
missing. That asymmetry preserves the v1 endpoint contract (where the
optimiser supplies the candidate intermodal route) while enabling
zero-override usage once data is wired.

## Why TMS-side, not Core-side

Per `.claude/rules/transport-plane-invariant.md`: intermodal-rail ramps
and freight spot-rate snapshots have no plausible second consumer
(SCP / CRM / WMS would not query them). They are transport-plane
substrate. Core may absorb them later if we discover a cross-product
need (e.g. inbound-cost forecasts in S&OP), at which point an entry
gets added to MIGRATION_REGISTER. Don't speculate now.

## Tables

* **intermodal_ramp** — Catalog of rail/ocean ramps. One row per
  physical ramp, optionally co-located with a `Site` for drayage
  distance lookups.
* **intermodal_rate** — Contracted or spot rates for a (origin_ramp,
  destination_ramp, mode) tuple. Validity windowed by valid_from /
  valid_to. Multiple sources (contract, spot, internal estimate) can
  coexist; consumer picks the lowest valid rate.
* **ramp_congestion_snapshot** — Time-series feed of ramp utilisation
  (0..1). The intermodal TRM's `ramp_congestion_level` defaults to
  the most recent snapshot per ramp.
* **spot_rate_snapshot** — Time-series of truck spot-market rates per
  lane × mode. Source attribution lets us calibrate when multiple
  feeds diverge.

## RLS

Tenant-scoped tables get an RLS policy in the migration that creates
them (per `.claude/rules/soc2-compliance.md`). The migration in
`backend/migrations/versions/20260424_intermodal_network.py` ships
those policies alongside the tables — never bolted on later.
"""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Date, Double, Enum as SAEnum,
    Float, ForeignKey, Index, Integer, String, UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship

from .base import Base
from .tms_entities import TransportMode


# ── Enums ────────────────────────────────────────────────────────────


class RampType:
    """String constants for `intermodal_ramp.ramp_type`."""
    RAIL = "rail"
    OCEAN_PORT = "ocean_port"
    AIR_CARGO = "air_cargo"
    INLAND_PORT = "inland_port"


class IntermodalRateSource:
    """String constants for `intermodal_rate.source`."""
    CONTRACT = "contract"
    SPOT = "spot"
    INTERNAL_ESTIMATE = "internal_estimate"


class SpotRateSource:
    """String constants for `spot_rate_snapshot.source`."""
    FREIGHTWAVES_SONAR = "FREIGHTWAVES_SONAR"
    DAT = "DAT"
    TRUCKSTOP = "TRUCKSTOP"
    INTERNAL = "INTERNAL"


# ── Tables ───────────────────────────────────────────────────────────


class IntermodalRamp(Base):
    """Rail / ocean / air-cargo ramp catalog.

    A ramp is a physical transfer point between truck and another mode.
    Co-located with a Site when drayage distance matters; otherwise
    standalone (lat/lon only). Capacity caps and congestion thresholds
    are per-ramp policy parameters.
    """
    __tablename__ = "intermodal_ramp"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))

    name = Column(String(200), nullable=False)
    code = Column(String(50), nullable=False, comment="Short identifier (e.g. 'CHI_BNSF', 'LA_LB')")
    ramp_type = Column(String(30), nullable=False, comment="rail | ocean_port | air_cargo | inland_port")
    operator = Column(String(100), comment="BNSF, UP, NSC, CSXT, port authority, ...")

    # Optional Site co-location (for drayage-distance lookups)
    site_id = Column(Integer, ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    latitude = Column(Float)
    longitude = Column(Float)
    address = Column(String(500))

    # Capacity / congestion policy
    capacity_loads_daily = Column(Integer, comment="Nominal daily throughput (loads)")
    congestion_threshold_pct = Column(
        Float, default=0.7,
        comment="Utilisation above this triggers IntermodalTransfer REJECT",
    )

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("Site")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_intermodal_ramp_tenant_code"),
        Index("idx_intermodal_ramp_tenant", "tenant_id"),
        Index("idx_intermodal_ramp_type", "ramp_type"),
    )


class IntermodalRate(Base):
    """Contracted or spot rate for an (origin_ramp, destination_ramp, mode) leg.

    Multiple rates can be valid at once (e.g. a contract rate AND a
    cheaper spot rate); the intermodal TRM picks the lowest valid rate
    for the candidate move. Drayage costs (origin_to_ramp,
    ramp_to_dest) are NOT in this table — those vary per shipment and
    come from the planner's overrides or a per-mile heuristic.
    """
    __tablename__ = "intermodal_rate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    origin_ramp_id = Column(
        Integer, ForeignKey("intermodal_ramp.id", ondelete="CASCADE"), nullable=False
    )
    destination_ramp_id = Column(
        Integer, ForeignKey("intermodal_ramp.id", ondelete="CASCADE"), nullable=False
    )
    mode = Column(SAEnum(TransportMode, name="transport_mode_enum"), nullable=False)

    rate_per_load = Column(Double, nullable=False)
    rate_per_container = Column(Double, comment="40ft container equivalent (intermodal-specific)")
    fuel_surcharge_pct = Column(Float)

    # Service quality
    transit_days_p50 = Column(Float, nullable=False)
    transit_days_p90 = Column(Float)
    reliability_pct = Column(
        Float, comment="Historical on-time %% (0..1) over the last 90 days"
    )

    # Validity window
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=False)
    source = Column(
        String(30), nullable=False,
        comment="contract | spot | internal_estimate (see IntermodalRateSource)",
    )
    contract_number = Column(String(100))

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    origin_ramp = relationship("IntermodalRamp", foreign_keys=[origin_ramp_id])
    destination_ramp = relationship("IntermodalRamp", foreign_keys=[destination_ramp_id])

    __table_args__ = (
        Index("idx_intermodal_rate_lookup", "tenant_id", "origin_ramp_id", "destination_ramp_id", "mode"),
        Index("idx_intermodal_rate_validity", "valid_from", "valid_to", "is_active"),
    )


class RampCongestionSnapshot(Base):
    """Time-series of ramp congestion. Latest snapshot per ramp drives
    the IntermodalTransferTRM congestion-gate.

    Append-only — never updated. Lookup via
    `MAX(snapshot_at) GROUP BY ramp_id`.
    """
    __tablename__ = "ramp_congestion_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    ramp_id = Column(
        Integer, ForeignKey("intermodal_ramp.id", ondelete="CASCADE"), nullable=False
    )

    congestion_level = Column(
        Float, nullable=False, comment="0..1 (utilisation as fraction of capacity)"
    )
    queued_loads = Column(Integer, comment="Snapshot of queued loads at the ramp")
    expected_clear_hours = Column(
        Float, comment="ETA to clear queue at current rate"
    )

    source = Column(String(50), comment="External feed name or 'manual'")
    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    ramp = relationship("IntermodalRamp")

    __table_args__ = (
        Index("idx_ramp_congestion_lookup", "tenant_id", "ramp_id", "snapshot_at"),
    )


class SpotRateSnapshot(Base):
    """Time-series of truck spot-market rates per lane × mode.

    Append-only. Source attribution (FreightWaves SONAR / DAT /
    Truckstop / internal) lets us cross-reference when feeds disagree.
    The IntermodalTransferTRM's `truck_rate` defaults to the most
    recent SPOT_RATE_SOURCE_PRIORITY-ranked rate per lane × mode.
    """
    __tablename__ = "spot_rate_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Lane keying — prefer lane_id when known; fall back to (origin, dest)
    lane_id = Column(
        Integer, ForeignKey("transportation_lane.id", ondelete="SET NULL"), nullable=True
    )
    origin_site_id = Column(
        Integer, ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    destination_site_id = Column(
        Integer, ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )

    mode = Column(SAEnum(TransportMode, name="transport_mode_enum"), nullable=False)
    equipment_type = Column(String(30), comment="DRY_VAN / REEFER / FLATBED / ...")

    rate_per_load = Column(Double, nullable=False)
    rate_per_mile = Column(Double)
    distance_miles = Column(Float)
    fuel_surcharge_pct = Column(Float)

    # Market context
    market_tightness = Column(
        Float, comment="0..1 (0 = abundant capacity, 1 = severely tight)"
    )
    sample_size = Column(Integer, comment="Number of observations underlying this snapshot")

    source = Column(String(50), nullable=False, comment="See SpotRateSource")
    valid_at = Column(
        DateTime, nullable=False, comment="Timestamp the rate is valid for (vs captured_at)"
    )
    captured_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    extra = Column(JSON)

    lane = relationship("TransportationLane", foreign_keys=[lane_id])

    __table_args__ = (
        Index("idx_spot_rate_lane", "tenant_id", "lane_id", "mode", "valid_at"),
        Index("idx_spot_rate_origin_dest", "tenant_id", "origin_site_id", "destination_site_id", "mode"),
        Index("idx_spot_rate_validity", "valid_at"),
    )

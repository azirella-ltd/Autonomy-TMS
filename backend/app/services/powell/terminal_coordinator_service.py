"""
L2 Terminal Coordinator — deterministic heuristic v1.

Per docs/L2_TERMINAL_COORDINATOR_DESIGN.md §6 Phase 1: ship the
scaffolding + heuristic before training the GATv2+GRU agent (Phase 3,
blocked on twin + corpora).

## What this v1 does

For each enabled hub (Site of type CROSS_DOCK / DC / TERMINAL):

  1. Compute a **terminal-health snapshot** from canonical state +
     trailing-window aggregations:
       * dock_utilization_pct  ← appointment volume vs dock_door capacity
       * tender_reject_rate_1h ← FreightTender DECLINED / total in 1h
       * exception_backlog_count ← open ShipmentException count
       * equipment_imbalance   ← Σ(available − demand_7d) at this hub
       * sla_miss_rate_1h      ← shipments delivered late / delivered
     Combined into composite_health ∈ [0, 1] where 1 = nominal.

  2. Append to `terminal_health_signal` (one row per
     (hub × hourly cycle)).

  3. Emit deterministic **urgency overrides** based on policy
     thresholds:
       * tender_reject_rate_1h > policy.escalation_thresholds.tender_reject_rate_1h
         → bump CapacityBufferTRM + FreightProcurementTRM urgency 1.5×
       * exception_backlog_count > policy.escalation_thresholds.exception_backlog_count
         → bump ExceptionManagementTRM urgency 1.8×
       * equipment_imbalance < −5 (deficit ≥ 5)
         → bump EquipmentRepositionTRM urgency 1.5×

     Each override has a 1-hour TTL. Idempotent — re-firing replaces
     the prior un-expired row for the same (hub, trm_type).

## What it does NOT do (yet)

  * `lane_waterfall_override` writes — needs lane-level reject-rate
    aggregation; deferred to Phase 1.5.
  * Batching / dock re-sequencing / yard-placement HiveSignal directives
    — needs HiveSignalBus integration that's not yet wired.
  * GATv2 inference — Phase 3.

## Cross-references

* `app.models.terminal_coordinator` — the 3 substrate tables this
  writes to.
* `app.services.powell.policy_reader.PolicyCache` — pulls
  `escalation_thresholds` for the bump triggers.
* `app.services.powell.exception_management_trm` (and other L1 TRMs)
  — read `terminal_urgency_override` from their state-builder.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.policy_parameters import PolicyParameters
from app.models import Site
from app.models.terminal_coordinator import (
    L2TrendDirection, LaneWaterfallOverride, TerminalHealthSignal,
    TerminalUrgencyOverride,
)
from app.models.tms_entities import (
    Appointment, AppointmentStatus, DockDoor, Equipment,
    ExceptionResolutionStatus, FreightTender, Load, LoadStatus,
    ShipmentException, TenderStatus, TMSShipment,
)
from app.services.policy_service import PolicyNotFound, get_active_policy

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────

# Tender-reject window for the 1h rate.
TENDER_WINDOW_HOURS = 1
SLA_WINDOW_HOURS = 1
EQUIPMENT_DEMAND_DAYS = 7

# Override TTL — short by design. Coordinator re-fires on next cycle
# if conditions persist (avoids stale overrides hanging around).
DEFAULT_OVERRIDE_TTL = timedelta(hours=1)

# Site types treated as terminals. Sites outside this set are skipped.
_TERMINAL_SITE_TYPES = {"CROSS_DOCK", "DC", "TERMINAL", "RAMP", "PORT"}

# Composite-health weighting (sums to 1.0).
# Tender-reject + SLA-miss carry more weight than utilisation drift.
_HEALTH_WEIGHTS = {
    "dock_util":     0.15,
    "tender_reject": 0.30,
    "exceptions":    0.20,
    "equipment":     0.10,
    "sla_miss":      0.25,
}


# ── Service ──────────────────────────────────────────────────────────


class TerminalCoordinatorService:
    """Deterministic heuristic L2 coordinator. One instance per
    (tenant, config) pair; iterates every terminal hub each cycle.

    Lifecycle:
        svc = TerminalCoordinatorService(db, tenant_id, config_id)
        snapshots = svc.run_cycle()   # one row per hub
        # snapshots also already wrote terminal_health_signal +
        # any triggered terminal_urgency_override rows
    """

    def __init__(self, db: Session, tenant_id: int, config_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id

    # ── Public entry points ────────────────────────────────────────

    def run_cycle(self) -> List[Dict[str, Any]]:
        """Run one coordination cycle across every hub. Returns a
        per-hub summary list (snapshot + override deltas)."""
        try:
            policy = get_active_policy(
                self.db, tenant_id=self.tenant_id, config_id=self.config_id
            )
        except PolicyNotFound:
            logger.warning(
                "TerminalCoordinator tenant=%s config=%s: no active policy "
                "— skipping cycle. Provisioning may have skipped policy seed.",
                self.tenant_id, self.config_id,
            )
            return []

        hubs = self._find_terminals()
        summaries: List[Dict[str, Any]] = []
        for hub in hubs:
            try:
                summary = self._cycle_one_hub(hub, policy)
                summaries.append(summary)
            except Exception as e:  # pragma: no cover
                logger.error(
                    "TerminalCoordinator hub=%s failed: %s",
                    hub.id, e, exc_info=True,
                )
                self.db.rollback()
        self.db.commit()
        return summaries

    def purge_expired(self, older_than_days: int = 7) -> int:
        """Drop expired override rows older than `older_than_days`.
        Un-expired rows are kept regardless. Hourly cleanup is the
        intended cadence."""
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        u_deleted = self.db.execute(
            TerminalUrgencyOverride.__table__.delete().where(
                TerminalUrgencyOverride.tenant_id == self.tenant_id,
                TerminalUrgencyOverride.expires_at < cutoff,
            )
        ).rowcount
        l_deleted = self.db.execute(
            LaneWaterfallOverride.__table__.delete().where(
                LaneWaterfallOverride.tenant_id == self.tenant_id,
                LaneWaterfallOverride.expires_at < cutoff,
            )
        ).rowcount
        self.db.commit()
        return int(u_deleted + l_deleted)

    # ── Internals ──────────────────────────────────────────────────

    def _find_terminals(self) -> List[Site]:
        """Sites at this tenant's config with a terminal-style type.

        Site is config-scoped (no direct tenant FK); we filter by
        config_id and trust that all sites under our config_id are
        within our tenant scope.
        """
        query = (
            select(Site)
            .where(
                Site.config_id == self.config_id,
                # `Site.type` is a String column; matching values
                # qualify as terminal hubs.
                Site.type.in_(_TERMINAL_SITE_TYPES),
            )
            .order_by(Site.id)
        )
        return list(self.db.execute(query).scalars().all())

    def _cycle_one_hub(
        self, hub: Site, policy: PolicyParameters,
    ) -> Dict[str, Any]:
        """Compute health snapshot + emit overrides for a single hub."""
        snapshot = self._compute_health_snapshot(hub)
        active_overrides_before = self._count_active_overrides(hub.id)
        snapshot["active_overrides_count"] = active_overrides_before

        # Persist the health signal
        signal = TerminalHealthSignal(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            hub_site_id=hub.id,
            timestamp=datetime.utcnow(),
            composite_health=snapshot["composite_health"],
            dock_utilization_pct=snapshot.get("dock_utilization_pct"),
            tender_reject_rate_1h=snapshot.get("tender_reject_rate_1h"),
            exception_backlog_count=snapshot.get("exception_backlog_count"),
            equipment_imbalance=snapshot.get("equipment_imbalance"),
            sla_miss_rate_1h=snapshot.get("sla_miss_rate_1h"),
            trend_7d=self._compute_trend(hub.id),
            active_overrides_count=active_overrides_before,
        )
        self.db.add(signal)
        self.db.flush()

        # Trigger urgency overrides per policy thresholds
        thresholds = policy.escalation_thresholds or {}
        overrides_emitted: List[str] = []
        now = datetime.utcnow()
        expires = now + DEFAULT_OVERRIDE_TTL

        if (
            snapshot["tender_reject_rate_1h"] is not None
            and snapshot["tender_reject_rate_1h"]
                > float(thresholds.get("tender_reject_rate_1h", 1.0))
        ):
            for trm_type, mult in (
                ("capacity_buffer", 1.5),
                ("freight_procurement", 1.5),
            ):
                self._upsert_urgency_override(
                    hub_id=hub.id, trm_type=trm_type,
                    multiplier=mult, expires_at=expires,
                    reason=(
                        f"tender_reject_rate_1h={snapshot['tender_reject_rate_1h']:.2f} "
                        f"> threshold={thresholds.get('tender_reject_rate_1h')}"
                    ),
                )
                overrides_emitted.append(trm_type)

        if (
            snapshot["exception_backlog_count"] is not None
            and snapshot["exception_backlog_count"]
                > int(thresholds.get("exception_backlog_count", 1_000_000))
        ):
            self._upsert_urgency_override(
                hub_id=hub.id, trm_type="exception_management",
                multiplier=1.8, expires_at=expires,
                reason=(
                    f"exception_backlog_count={snapshot['exception_backlog_count']} "
                    f"> threshold={thresholds.get('exception_backlog_count')}"
                ),
            )
            overrides_emitted.append("exception_management")

        if (
            snapshot["equipment_imbalance"] is not None
            and snapshot["equipment_imbalance"] < -5.0
        ):
            self._upsert_urgency_override(
                hub_id=hub.id, trm_type="equipment_reposition",
                multiplier=1.5, expires_at=expires,
                reason=(
                    f"equipment_imbalance={snapshot['equipment_imbalance']:.0f} "
                    "(deficit ≥ 5)"
                ),
            )
            overrides_emitted.append("equipment_reposition")

        return {
            "hub_site_id": hub.id,
            "hub_site_name": hub.name,
            "snapshot": snapshot,
            "overrides_emitted": overrides_emitted,
        }

    # ── Health snapshot computation ────────────────────────────────

    def _compute_health_snapshot(self, hub: Site) -> Dict[str, Any]:
        """Compute the per-hub KPI components + composite_health."""
        dock_util = self._dock_utilization(hub.id)
        tender_reject = self._tender_reject_rate(hub.id)
        exception_backlog = self._exception_backlog(hub.id)
        equipment_imbalance = self._equipment_imbalance(hub.id)
        sla_miss = self._sla_miss_rate(hub.id)

        # Composite: every component → 0..1 healthy → weighted average
        # Use 0.5 as the "no signal" default so missing data is neutral.
        components = {
            "dock_util":     1.0 - abs(0.7 - (dock_util if dock_util is not None else 0.7)),
            "tender_reject": 1.0 - (tender_reject if tender_reject is not None else 0.0),
            "exceptions":    1.0 - min(1.0, (exception_backlog or 0) / 50.0),
            "equipment":     1.0 - min(1.0, abs(equipment_imbalance or 0) / 20.0),
            "sla_miss":      1.0 - (sla_miss if sla_miss is not None else 0.0),
        }
        composite = sum(_HEALTH_WEIGHTS[k] * v for k, v in components.items())
        composite = max(0.0, min(1.0, composite))

        return {
            "composite_health": composite,
            "dock_utilization_pct": dock_util,
            "tender_reject_rate_1h": tender_reject,
            "exception_backlog_count": exception_backlog,
            "equipment_imbalance": equipment_imbalance,
            "sla_miss_rate_1h": sla_miss,
        }

    def _dock_utilization(self, hub_id: int) -> Optional[float]:
        """In-flight appointments / total dock doors at this hub."""
        total_doors = self.db.execute(
            select(func.count(DockDoor.id)).where(
                DockDoor.tenant_id == self.tenant_id,
                DockDoor.site_id == hub_id,
            )
        ).scalar() or 0
        if total_doors == 0:
            return None
        active = self.db.execute(
            select(func.count(Appointment.id)).where(
                Appointment.tenant_id == self.tenant_id,
                Appointment.dock_door_id.in_(
                    select(DockDoor.id).where(DockDoor.site_id == hub_id)
                ),
                Appointment.status == AppointmentStatus.CONFIRMED,
            )
        ).scalar() or 0
        return float(active) / float(total_doors)

    def _tender_reject_rate(self, hub_id: int) -> Optional[float]:
        """Tender DECLINED + EXPIRED / total over the last hour for
        loads originating from this hub."""
        cutoff = datetime.utcnow() - timedelta(hours=TENDER_WINDOW_HOURS)
        total = self.db.execute(
            select(func.count(FreightTender.id)).where(
                FreightTender.tenant_id == self.tenant_id,
                FreightTender.tendered_at >= cutoff,
                FreightTender.load_id.in_(
                    select(Load.id).where(Load.origin_site_id == hub_id)
                ),
            )
        ).scalar() or 0
        if total == 0:
            return None
        rejected = self.db.execute(
            select(func.count(FreightTender.id)).where(
                FreightTender.tenant_id == self.tenant_id,
                FreightTender.tendered_at >= cutoff,
                FreightTender.load_id.in_(
                    select(Load.id).where(Load.origin_site_id == hub_id)
                ),
                FreightTender.status.in_([
                    TenderStatus.DECLINED, TenderStatus.EXPIRED,
                ]),
            )
        ).scalar() or 0
        return float(rejected) / float(total)

    def _exception_backlog(self, hub_id: int) -> int:
        """Open exceptions on shipments touching this hub."""
        return int(
            self.db.execute(
                select(func.count(ShipmentException.id)).where(
                    ShipmentException.tenant_id == self.tenant_id,
                    ShipmentException.resolution_status.in_([
                        ExceptionResolutionStatus.DETECTED,
                        ExceptionResolutionStatus.INVESTIGATING,
                    ]),
                    ShipmentException.shipment_id.in_(
                        select(TMSShipment.id).where(
                            or_(
                                TMSShipment.origin_site_id == hub_id,
                                TMSShipment.destination_site_id == hub_id,
                            )
                        )
                    ),
                )
            ).scalar() or 0
        )

    def _equipment_imbalance(self, hub_id: int) -> Optional[float]:
        """Σ(available − demand_next_7d) across equipment types at hub.

        Positive = surplus, negative = deficit. Returns None when the
        hub has no equipment registered.
        """
        on_hand = self.db.execute(
            select(func.count(Equipment.id)).where(
                Equipment.tenant_id == self.tenant_id,
                Equipment.current_site_id == hub_id,
                Equipment.status == "AVAILABLE",
                Equipment.is_active.is_(True),
            )
        ).scalar() or 0
        # Demand: shipments originating here in next 7 days
        horizon = datetime.utcnow() + timedelta(days=EQUIPMENT_DEMAND_DAYS)
        demand = self.db.execute(
            select(func.count(TMSShipment.id)).where(
                TMSShipment.tenant_id == self.tenant_id,
                TMSShipment.origin_site_id == hub_id,
                TMSShipment.requested_pickup_date <= horizon,
                TMSShipment.requested_pickup_date >= datetime.utcnow(),
            )
        ).scalar() or 0
        if on_hand == 0 and demand == 0:
            return None
        return float(on_hand) - float(demand)

    def _sla_miss_rate(self, hub_id: int) -> Optional[float]:
        """Loads delivered late / total delivered in the last hour for
        loads originating from this hub.

        v1 uses Load.actual_arrival > Load.planned_arrival as the
        simple late-detection signal.
        """
        cutoff = datetime.utcnow() - timedelta(hours=SLA_WINDOW_HOURS)
        total = self.db.execute(
            select(func.count(Load.id)).where(
                Load.tenant_id == self.tenant_id,
                Load.origin_site_id == hub_id,
                Load.actual_arrival >= cutoff,
                Load.status == LoadStatus.DELIVERED,
            )
        ).scalar() or 0
        if total == 0:
            return None
        late = self.db.execute(
            select(func.count(Load.id)).where(
                Load.tenant_id == self.tenant_id,
                Load.origin_site_id == hub_id,
                Load.actual_arrival >= cutoff,
                Load.status == LoadStatus.DELIVERED,
                Load.actual_arrival > Load.planned_arrival,
            )
        ).scalar() or 0
        return float(late) / float(total)

    def _compute_trend(self, hub_id: int) -> str:
        """Compare last-7-day mean composite_health to prior 7d.

        Returns IMPROVING / STABLE / DEGRADING. Defaults to STABLE
        when fewer than 14d of history exist.
        """
        now = datetime.utcnow()
        last_7d = self.db.execute(
            select(func.avg(TerminalHealthSignal.composite_health)).where(
                TerminalHealthSignal.tenant_id == self.tenant_id,
                TerminalHealthSignal.hub_site_id == hub_id,
                TerminalHealthSignal.timestamp >= now - timedelta(days=7),
            )
        ).scalar()
        prior_7d = self.db.execute(
            select(func.avg(TerminalHealthSignal.composite_health)).where(
                TerminalHealthSignal.tenant_id == self.tenant_id,
                TerminalHealthSignal.hub_site_id == hub_id,
                TerminalHealthSignal.timestamp >= now - timedelta(days=14),
                TerminalHealthSignal.timestamp < now - timedelta(days=7),
            )
        ).scalar()
        if last_7d is None or prior_7d is None:
            return L2TrendDirection.STABLE
        delta = float(last_7d) - float(prior_7d)
        if delta > 0.05:
            return L2TrendDirection.IMPROVING
        if delta < -0.05:
            return L2TrendDirection.DEGRADING
        return L2TrendDirection.STABLE

    # ── Override management ────────────────────────────────────────

    def _count_active_overrides(self, hub_id: int) -> int:
        now = datetime.utcnow()
        u = self.db.execute(
            select(func.count(TerminalUrgencyOverride.id)).where(
                TerminalUrgencyOverride.tenant_id == self.tenant_id,
                TerminalUrgencyOverride.hub_site_id == hub_id,
                TerminalUrgencyOverride.expires_at > now,
            )
        ).scalar() or 0
        l = self.db.execute(
            select(func.count(LaneWaterfallOverride.id)).where(
                LaneWaterfallOverride.tenant_id == self.tenant_id,
                LaneWaterfallOverride.hub_site_id == hub_id,
                LaneWaterfallOverride.expires_at > now,
            )
        ).scalar() or 0
        return int(u + l)

    def _upsert_urgency_override(
        self,
        *,
        hub_id: int,
        trm_type: str,
        multiplier: float,
        expires_at: datetime,
        reason: str,
    ) -> None:
        """Replace any active override for (hub, trm_type) with a fresh
        row. We don't UPDATE in place so the audit trail records every
        re-fire as its own row."""
        now = datetime.utcnow()
        # Expire any active overrides for this (hub, trm_type)
        self.db.execute(
            TerminalUrgencyOverride.__table__.update().where(
                TerminalUrgencyOverride.tenant_id == self.tenant_id,
                TerminalUrgencyOverride.hub_site_id == hub_id,
                TerminalUrgencyOverride.trm_type == trm_type,
                TerminalUrgencyOverride.expires_at > now,
            ).values(expires_at=now)
        )
        clamped = max(0.5, min(2.0, float(multiplier)))
        self.db.add(
            TerminalUrgencyOverride(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                hub_site_id=hub_id,
                trm_type=trm_type,
                urgency_multiplier=clamped,
                expires_at=expires_at,
                reason=reason,
            )
        )
        self.db.flush()


# ── Read-side helper for L1 TRM consumers ────────────────────────────


def get_active_urgency_multiplier(
    db: Session,
    *,
    tenant_id: int,
    hub_site_id: int,
    trm_type: str,
) -> float:
    """Resolve the active urgency multiplier for (hub, trm_type).

    L1 TRMs call this from their state-builder when they have a hub
    context. Returns 1.0 (neutral) when no active override exists —
    consistent with the design: absent override == multiplier 1.0,
    not a fallback default.
    """
    now = datetime.utcnow()
    row = db.execute(
        select(TerminalUrgencyOverride.urgency_multiplier)
        .where(
            TerminalUrgencyOverride.tenant_id == tenant_id,
            TerminalUrgencyOverride.hub_site_id == hub_site_id,
            TerminalUrgencyOverride.trm_type == trm_type,
            TerminalUrgencyOverride.expires_at > now,
        )
        .order_by(desc(TerminalUrgencyOverride.created_at))
        .limit(1)
    ).scalar()
    if row is None:
        return 1.0
    return max(0.5, min(2.0, float(row)))

"""
HubHourSnapshotService — Phase-2 data extractor for L2 GATv2+GRU.

Extracts the GATv2-ready node + edge feature representation for one
hub at one timestamp and persists it to ``hub_hour_snapshot``. The
service is the data substrate the Phase-3 agent trains on; until the
twin ships (Phase A of TMS_TIER3_FIRST_PLAN), live ops produces the
same shape — BC training on twin data and PPO fine-tune on live data
both write to this table.

## What goes into a snapshot

Per ``docs/L2_TERMINAL_COORDINATOR_DESIGN.md`` §3 graph spec:

  Nodes (typed):
    * dock_door             — per-door status + queue depth
    * outbound_lane         — per-lane queued shipments + reject rate
    * inbound_lane          — per-lane expected arrivals
    * equipment_pool        — per-type counts by status
    * carrier_presence      — on-property carriers (placeholder until
                              the carrier-presence feed lands)
    * shipment_queue        — unassigned shipments by tier
    * TRM_agent             — current urgency + recent decision mix
                              for each of the 11 L1 TRMs

  Edges (per-pair adjacency, sparse):
    * dock_to_shipment      — which docks can serve which queued shipments
    * lane_to_shipment      — which lanes accept which shipments
    * carrier_to_lane       — which carriers ready for which lanes
    * equipment_to_lane     — which equipment feeding which lanes
    * trm_to_resource       — which TRM owns which resource node

## What this v1 extractor populates

For Phase 2 v1, we ship the **node-feature** half of the schema. The
edge-feature half lands once the graph constructor (Phase 3 scope)
finalises edge semantics. ``hub_summary`` mirrors the existing
``terminal_health_signal`` 5 KPIs so analytics keep working.

The ``policy_snapshot`` carries the active PolicyParameters at
extraction time so the trained agent learns policy-conditioned
actions.

## Idempotency

One row per (tenant, config, hub, observed_at). Re-running the same
hour is a no-op via ``ON CONFLICT DO NOTHING`` against
``uq_hub_hour_snapshot``.

## When the twin ships

Phase A's twin extractor will instantiate this service with
``source="twin"`` (or a more specific scenario tag) and call
``snapshot_hub`` against twin-rolled-out hub state. The schema +
feature pipeline is shared; only the data source differs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Site
from app.models.hub_hour_snapshot import HubHourSnapshot
from app.models.policy_parameters import PolicyParameters
from app.models.tms_entities import (
    Appointment, AppointmentStatus, Carrier, DockDoor, Equipment,
    EquipmentType, ExceptionResolutionStatus, FreightTender, Load,
    LoadStatus, ShipmentException, TenderStatus, TMSShipment,
)
from app.services.policy_service import PolicyNotFound, get_active_policy
from app.services.powell.terminal_coordinator_service import (
    _TERMINAL_SITE_TYPES, TerminalCoordinatorService,
)

logger = logging.getLogger(__name__)


# Time-window constants — match the L2 Phase-1 coordinator so
# terminal_health_signal and hub_hour_snapshot row at the same hour
# carry the same scalar KPIs.
_LANE_WINDOW_HOURS = 1
_INBOUND_HORIZON_HOURS = 4
_EQUIPMENT_WINDOW_DAYS = 7
_TRM_TYPES = (
    "capacity_promise", "shipment_tracking", "load_volume_sensing",
    "capacity_buffer", "exception_management", "freight_procurement",
    "broker_routing", "dock_scheduling", "load_build",
    "intermodal_transfer", "equipment_reposition",
)


class HubHourSnapshotService:
    """Per-hub hour-aligned graph-snapshot extractor.

    Lifecycle:
        svc = HubHourSnapshotService(db, tenant_id, config_id)
        results = svc.snapshot_all_hubs()           # walks every hub
        # or single hub:
        row = svc.snapshot_hub(hub_id, observed_at)
    """

    def __init__(
        self,
        db: Session,
        tenant_id: int,
        config_id: int,
        source: str = "live",
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self.source = source
        # Reuse Phase-1 coordinator for hub_summary KPI computation
        # so we don't re-implement the same SQL twice.
        self._coordinator = TerminalCoordinatorService(
            db, tenant_id=tenant_id, config_id=config_id,
        )

    # ── Public entry points ────────────────────────────────────────

    def snapshot_all_hubs(
        self,
        observed_at: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Walk every terminal-style Site under this (tenant, config)
        and write a snapshot for each. Aligns ``observed_at`` to the
        nearest top-of-hour so multi-hub snapshots share the same
        timestamp."""
        if observed_at is None:
            now = datetime.utcnow()
            observed_at = now.replace(minute=0, second=0, microsecond=0)

        try:
            policy = get_active_policy(
                self.db, tenant_id=self.tenant_id, config_id=self.config_id,
            )
        except PolicyNotFound:
            policy = None

        hubs = self._find_terminals()
        results: List[Dict[str, Any]] = []
        for hub in hubs:
            try:
                summary = self.snapshot_hub(
                    hub.id, observed_at=observed_at, policy=policy,
                )
                if summary:
                    results.append(summary)
            except Exception as e:  # pragma: no cover
                logger.error(
                    "HubHourSnapshot failed for hub=%s: %s",
                    hub.id, e, exc_info=True,
                )
                self.db.rollback()
        self.db.commit()
        return results

    def snapshot_hub(
        self,
        hub_id: int,
        observed_at: datetime,
        policy: Optional[PolicyParameters] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extract + persist one (hub, hour) snapshot. Returns a
        summary dict or ``None`` when the row already existed."""
        node_features = self._build_node_features(hub_id)
        edge_features: Dict[str, Any] = {
            # v1 placeholder: edge schema lands with the Phase 3 graph
            # constructor. Stored as empty so the column type stays
            # consistent across rows.
            "version": 1,
            "edges": [],
        }
        hub_summary = self._build_hub_summary(hub_id)
        policy_snapshot = self._snapshot_policy(policy)

        stmt = (
            pg_insert(HubHourSnapshot)
            .values(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                hub_site_id=hub_id,
                observed_at=observed_at,
                node_features=node_features,
                edge_features=edge_features,
                hub_summary=hub_summary,
                policy_snapshot=policy_snapshot,
                source=self.source,
            )
            .on_conflict_do_nothing(constraint="uq_hub_hour_snapshot")
        )
        res = self.db.execute(stmt)
        wrote_new = bool(res.rowcount and res.rowcount > 0)

        return {
            "hub_id": hub_id,
            "observed_at": observed_at.isoformat(),
            "node_count": sum(
                len(v) for v in node_features.values()
                if isinstance(v, list)
            ),
            "wrote_new": wrote_new,
        }

    # ── Node-feature extractors ────────────────────────────────────

    def _build_node_features(self, hub_id: int) -> Dict[str, Any]:
        """Build the typed-node feature dict for one hub.

        Returns a dict keyed by node_type, each value a list of
        ``{node_id, ...features}`` dicts. The shape stays consistent
        even when no nodes of a given type exist (empty list) so the
        graph constructor doesn't have to special-case missing keys.
        """
        return {
            "dock_door": self._dock_door_features(hub_id),
            "outbound_lane": self._outbound_lane_features(hub_id),
            "inbound_lane": self._inbound_lane_features(hub_id),
            "equipment_pool": self._equipment_pool_features(hub_id),
            "carrier_presence": self._carrier_presence_features(hub_id),
            "shipment_queue": self._shipment_queue_features(hub_id),
            "trm_agent": self._trm_agent_features(hub_id),
        }

    def _dock_door_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Per-dock node features."""
        rows = self.db.execute(
            select(DockDoor.id, DockDoor.is_active).where(
                DockDoor.tenant_id == self.tenant_id,
                DockDoor.site_id == hub_id,
            )
        ).all()
        out = []
        for door_id, is_active in rows:
            queue_depth = self.db.execute(
                select(func.count(Appointment.id)).where(
                    Appointment.tenant_id == self.tenant_id,
                    Appointment.dock_door_id == door_id,
                    Appointment.status.in_([
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.REQUESTED,
                    ]),
                )
            ).scalar() or 0
            out.append({
                "node_id": int(door_id),
                "is_active": bool(is_active),
                "queue_depth": int(queue_depth),
            })
        return out

    def _outbound_lane_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Per-outbound-lane queued shipments + recent reject rate.

        v1 keys lanes by destination_site_id (a load originating from
        this hub on lane to dest_X). When the canonical Lane FK lands
        on Load, swap for that.
        """
        cutoff = datetime.utcnow() - timedelta(hours=_LANE_WINDOW_HOURS)
        # Distinct destinations from this hub
        dests = self.db.execute(
            select(Load.destination_site_id).where(
                Load.tenant_id == self.tenant_id,
                Load.origin_site_id == hub_id,
            ).distinct()
        ).scalars().all()
        out = []
        for dest in dests:
            if dest is None:
                continue
            queued = self.db.execute(
                select(func.count(Load.id)).where(
                    Load.tenant_id == self.tenant_id,
                    Load.origin_site_id == hub_id,
                    Load.destination_site_id == dest,
                    Load.status.in_([LoadStatus.PLANNING, LoadStatus.READY]),
                )
            ).scalar() or 0
            total_tenders = self.db.execute(
                select(func.count(FreightTender.id)).where(
                    FreightTender.tenant_id == self.tenant_id,
                    FreightTender.tendered_at >= cutoff,
                    FreightTender.load_id.in_(
                        select(Load.id).where(
                            Load.origin_site_id == hub_id,
                            Load.destination_site_id == dest,
                        )
                    ),
                )
            ).scalar() or 0
            rejected = self.db.execute(
                select(func.count(FreightTender.id)).where(
                    FreightTender.tenant_id == self.tenant_id,
                    FreightTender.tendered_at >= cutoff,
                    FreightTender.load_id.in_(
                        select(Load.id).where(
                            Load.origin_site_id == hub_id,
                            Load.destination_site_id == dest,
                        )
                    ),
                    FreightTender.status.in_([
                        TenderStatus.DECLINED, TenderStatus.EXPIRED,
                    ]),
                )
            ).scalar() or 0
            reject_rate = (
                float(rejected) / float(total_tenders)
                if total_tenders > 0 else None
            )
            out.append({
                "node_id": f"out-{hub_id}-to-{dest}",
                "destination_site_id": int(dest),
                "queued_loads": int(queued),
                "tender_reject_rate_1h": reject_rate,
            })
        return out

    def _inbound_lane_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Per-inbound-lane expected arrivals in next 4h."""
        horizon = datetime.utcnow() + timedelta(hours=_INBOUND_HORIZON_HOURS)
        origins = self.db.execute(
            select(Load.origin_site_id).where(
                Load.tenant_id == self.tenant_id,
                Load.destination_site_id == hub_id,
            ).distinct()
        ).scalars().all()
        out = []
        for origin in origins:
            if origin is None:
                continue
            expected = self.db.execute(
                select(func.count(Load.id)).where(
                    Load.tenant_id == self.tenant_id,
                    Load.origin_site_id == origin,
                    Load.destination_site_id == hub_id,
                    Load.status == LoadStatus.IN_TRANSIT,
                    Load.planned_arrival <= horizon,
                )
            ).scalar() or 0
            out.append({
                "node_id": f"in-from-{origin}-to-{hub_id}",
                "origin_site_id": int(origin),
                "expected_arrivals_4h": int(expected),
            })
        return out

    def _equipment_pool_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Per-equipment-type pool counts by status at this hub."""
        rows = self.db.execute(
            select(
                Equipment.equipment_type,
                Equipment.status,
                func.count(Equipment.id),
            ).where(
                Equipment.tenant_id == self.tenant_id,
                Equipment.current_site_id == hub_id,
                Equipment.is_active.is_(True),
            ).group_by(Equipment.equipment_type, Equipment.status)
        ).all()
        # Roll up to one row per equipment_type with status counts
        by_type: Dict[str, Dict[str, int]] = {}
        for eq_type, status, count in rows:
            type_key = eq_type.value if hasattr(eq_type, "value") else str(eq_type)
            by_type.setdefault(type_key, {})[
                str(status) if status else "UNKNOWN"
            ] = int(count)
        return [
            {"node_id": f"eq-{hub_id}-{type_key}", "equipment_type": type_key, **counts}
            for type_key, counts in by_type.items()
        ]

    def _carrier_presence_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Carriers with recent activity at this hub.

        v1 placeholder — TMS doesn't have a carrier-on-property feed
        yet. Approximate via "carriers with a tendered or in-transit
        load involving this hub in the last 4 hours."
        """
        cutoff = datetime.utcnow() - timedelta(hours=4)
        rows = self.db.execute(
            select(
                Load.carrier_id, func.count(Load.id).label("active_loads")
            ).where(
                Load.tenant_id == self.tenant_id,
                or_(
                    Load.origin_site_id == hub_id,
                    Load.destination_site_id == hub_id,
                ),
                Load.carrier_id.isnot(None),
                Load.updated_at >= cutoff,
            ).group_by(Load.carrier_id)
        ).all()
        return [
            {
                "node_id": f"carrier-{cid}-at-{hub_id}",
                "carrier_id": int(cid),
                "active_loads_4h": int(count),
            }
            for cid, count in rows
        ]

    def _shipment_queue_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """Unassigned shipments at this hub by mode."""
        rows = self.db.execute(
            select(
                TMSShipment.mode,
                func.count(TMSShipment.id).label("cnt"),
            ).where(
                TMSShipment.tenant_id == self.tenant_id,
                or_(
                    TMSShipment.origin_site_id == hub_id,
                    TMSShipment.destination_site_id == hub_id,
                ),
                TMSShipment.status.in_(["DRAFT", "TENDERED"]),
            ).group_by(TMSShipment.mode)
        ).all()
        return [
            {
                "node_id": f"queue-{hub_id}-{m}",
                "mode": m.value if hasattr(m, "value") else str(m),
                "queued_count": int(cnt),
            }
            for m, cnt in rows
        ]

    def _trm_agent_features(self, hub_id: int) -> List[Dict[str, Any]]:
        """One node per L1 TRM with current active-override multiplier.

        Pulls multipliers from `terminal_urgency_override` at this hub
        — same source the L1 TRMs read from. v1 doesn't include
        recent-decision-mix because that needs an aggregation against
        agent_decisions; lands in Phase 3 graph construction.
        """
        from app.models.terminal_coordinator import TerminalUrgencyOverride

        now = datetime.utcnow()
        rows = self.db.execute(
            select(
                TerminalUrgencyOverride.trm_type,
                TerminalUrgencyOverride.urgency_multiplier,
            ).where(
                TerminalUrgencyOverride.tenant_id == self.tenant_id,
                TerminalUrgencyOverride.hub_site_id == hub_id,
                TerminalUrgencyOverride.expires_at > now,
            )
        ).all()
        active_overrides = {
            trm: float(mult) for trm, mult in rows
        }
        return [
            {
                "node_id": f"trm-{hub_id}-{trm}",
                "trm_type": trm,
                "urgency_multiplier": active_overrides.get(trm, 1.0),
            }
            for trm in _TRM_TYPES
        ]

    # ── Hub-level summary ──────────────────────────────────────────

    def _build_hub_summary(self, hub_id: int) -> Dict[str, Any]:
        """Mirror the Phase-1 terminal_health_signal 5 KPIs into the
        snapshot's ``hub_summary`` JSONB. Reuses TerminalCoordinator-
        Service's snapshot computation so the two tables agree at
        same-hour observation time."""
        return self._coordinator._compute_health_snapshot(
            self._fake_site(hub_id)
        )

    def _fake_site(self, hub_id: int):
        """Lookup helper: terminal-coordinator's _compute_health_snapshot
        only reads `.id` off the Site object, so we fetch the real Site
        rather than constructing a sham."""
        return self.db.execute(
            select(Site).where(Site.id == hub_id)
        ).scalar_one()

    # ── Policy snapshot ────────────────────────────────────────────

    def _snapshot_policy(
        self,
        policy: Optional[PolicyParameters],
    ) -> Dict[str, Any]:
        """Snapshot the policy θ values that drive L1+L2 behaviour.

        Includes BSC weights, mode-mix targets, escalation thresholds,
        and cost guardrails — the fields downstream agents
        (heuristic + GATv2) actually read.
        """
        if policy is None:
            return {}
        return {
            "bsc_weight_financial": policy.bsc_weight_financial,
            "bsc_weight_customer": policy.bsc_weight_customer,
            "bsc_weight_internal": policy.bsc_weight_internal,
            "bsc_weight_learning": policy.bsc_weight_learning,
            "mode_mix_targets": policy.mode_mix_targets,
            "escalation_thresholds": policy.escalation_thresholds,
            "max_cost_delta_pct": policy.max_cost_delta_pct,
            "max_expedite_premium_pct": policy.max_expedite_premium_pct,
            "policy_version": policy.version,
        }

    # ── Helpers ────────────────────────────────────────────────────

    def _find_terminals(self) -> List[Site]:
        """Same logic as TerminalCoordinatorService — keep the two in
        sync so snapshots cover exactly the hubs the coordinator
        manages."""
        return list(self.db.execute(
            select(Site).where(
                Site.config_id == self.config_id,
                Site.type.in_(_TERMINAL_SITE_TYPES),
            ).order_by(Site.id)
        ).scalars().all())

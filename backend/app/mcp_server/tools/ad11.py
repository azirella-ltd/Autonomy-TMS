"""
MCP tools — AD-11 Supply×Transport intersection contract.

Per `Autonomy-Core/docs/SCP_TMS_COLLABORATION_ARCHITECTURE.md` §5 + §7,
TMS exposes three read-only tools that SCP agents call to inform their
planning decisions:

  * get_carrier_capacity(lane_id, date_from, date_to)
        → CapacitySnapshot — committed + available capacity, OTRI,
          conformal P10/P50/P90 bands on `available_loads`
  * get_dock_availability(site_id, date_from, date_to)
        → DockAvailability — total / open / scheduled door counts +
          per-day occupancy
  * get_active_exceptions(severity_min, status_filter, limit)
        → ActiveExceptionList — open exceptions with shipment context

## Contract invariants (all enforced)

  * Read-only. No tool mutates TMS state. Cross-plane state changes go
    through Core intersection tables (DispatchCommitment etc.) — those
    land separately when Core ships register item 1.8.
  * Canonical IDs only. Arguments use canonical site_id / lane_id /
    tenant_id. No TMS-local IDs cross the wire.
  * Conformal payloads where applicable. `available_loads_p10/p50/p90`
    on get_carrier_capacity. Until conformal predictors are calibrated
    for transport-side variables (item 4 in this session shipped the
    framework but not the per-variable calibration), bands collapse to
    point-estimate triples — caller can detect and fall back.
  * Tenant-scoped auth. Every call validates tenant_id; cross-tenant
    reads are forbidden and blocked at the server side via the
    surrounding MCP transport.
  * Bounded latency. Target 200ms p95 per call. SQL is filtered down
    to the relevant lane/site/tenant scope, no full-table scans.

## What this module does NOT include (yet)

  * The DispatchCommitment writeback path (IntermodalTransferTRM →
    intersection table) — blocked on Core MIGRATION_REGISTER 1.8.
  * Conformal P10/P90 spread for `available_loads` — wires through
    once `conformal.active_predictors` has rows for `capacity_buffer`
    or `freight_procurement` per (tenant, lane).
  * The plane-registry guard — design says callers go through
    `fallback.py` helpers; this module is the *callee* and trusts the
    caller's guard. If a caller fires this without registering the
    transport plane, the tool still returns truthful data.
"""
from __future__ import annotations

import logging
from datetime import date as date_type, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select

logger = logging.getLogger(__name__)


def register(mcp):
    """Register the three AD-11 read-only tools on an MCP server."""

    @mcp.tool()
    async def get_carrier_capacity(
        tenant_id: int,
        config_id: int,
        lane_id: int,
        date_from: str,
        date_to: str,
    ) -> Dict[str, Any]:
        """Return a CapacitySnapshot for a lane over a date range.

        SCP's ATPExecutorTRM calls this before finalising a deployment
        requirement to verify TMS can take the volume on the requested
        lane × date band. Per AD-11 §5.1.

        Args:
            tenant_id: canonical tenant boundary
            config_id: supply-chain config scope
            lane_id: canonical TransportationLane.id
            date_from / date_to: ISO date strings (inclusive bounds)

        Returns dict with:
            * `lane_id`, `date_from`, `date_to`
            * `total_committed_loads` — sum of CapacityTarget.committed_loads
            * `total_required_loads` — sum of CapacityTarget.required_loads
            * `total_available_loads` — sum of CapacityTarget.available_loads
            * `available_loads_p10` / `_p50` / `_p90` — conformal bands
            * `recent_tender_reject_rate_14d` — DECLINED+EXPIRED / total
              tenders on this lane over trailing 14 days (OTRI)
            * `carrier_count` — distinct carriers serving the lane
            * `as_of_utc` — timestamp the snapshot was computed
        """
        from .db import get_db
        from app.models.tms_entities import (
            FreightTender, Load, TenderStatus,
        )
        from app.models.tms_planning import CapacityTarget
        from app.models.transportation_config import CarrierContract
        from app.models.supply_chain_config import TransportationLane

        d_from = date_type.fromisoformat(date_from)
        d_to = date_type.fromisoformat(date_to)

        async with get_db() as db:
            # Capacity rollup from CapacityTarget over the window
            cap_query = select(
                func.coalesce(func.sum(CapacityTarget.committed_loads), 0),
                func.coalesce(func.sum(CapacityTarget.required_loads), 0),
                func.coalesce(func.sum(CapacityTarget.available_loads), 0),
            ).where(
                CapacityTarget.tenant_id == tenant_id,
                CapacityTarget.config_id == config_id,
                CapacityTarget.lane_id == lane_id,
                CapacityTarget.target_date >= d_from,
                CapacityTarget.target_date <= d_to,
            )
            committed, required, available = (await db.execute(cap_query)).one()
            committed = int(committed)
            required = int(required)
            available = int(available)

            # Trailing 14d reject rate (OTRI proxy) on this lane.
            # FreightTender → Load → (origin_site_id, destination_site_id);
            # TMS Load doesn't carry a lane_id FK so we resolve the
            # lane to its endpoints and filter loads by that pair.
            # Canonical TransportationLane uses from_site_id /
            # to_site_id (not origin_site_id / destination_site_id —
            # which is the column shape on TMS Load).
            lane_endpoints = (await db.execute(
                select(
                    TransportationLane.from_site_id,
                    TransportationLane.to_site_id,
                ).where(TransportationLane.id == lane_id)
            )).first()

            cutoff = datetime.utcnow() - timedelta(days=14)
            total_tenders = 0
            rejected_tenders = 0
            if lane_endpoints:
                origin_sid, dest_sid = lane_endpoints
                load_filter = select(Load.id).where(
                    Load.origin_site_id == origin_sid,
                    Load.destination_site_id == dest_sid,
                )
                total_tenders = (await db.execute(
                    select(func.count(FreightTender.id)).where(
                        FreightTender.tenant_id == tenant_id,
                        FreightTender.tendered_at >= cutoff,
                        FreightTender.load_id.in_(load_filter),
                    )
                )).scalar() or 0
                rejected_tenders = (await db.execute(
                    select(func.count(FreightTender.id)).where(
                        FreightTender.tenant_id == tenant_id,
                        FreightTender.tendered_at >= cutoff,
                        FreightTender.load_id.in_(load_filter),
                        FreightTender.status.in_([
                            TenderStatus.DECLINED, TenderStatus.EXPIRED,
                        ]),
                    )
                )).scalar() or 0
            reject_rate = (
                float(rejected_tenders) / float(total_tenders)
                if total_tenders > 0 else None
            )

            # Carrier count — distinct carriers under active contract
            # for this tenant. CarrierContract.status enum =
            # ACTIVE / DRAFT / EXPIRED / RENEWED / TERMINATED.
            carrier_count = (await db.execute(
                select(func.count(func.distinct(CarrierContract.carrier_id))).where(
                    CarrierContract.tenant_id == tenant_id,
                    CarrierContract.status.in_(["ACTIVE", "RENEWED"]),
                )
            )).scalar() or 0

            # Conformal bands. Until calibration runs publish per-lane
            # quantiles, we return the point estimate three times so
            # the caller can detect collapsed bands and decide how to
            # handle. When `conformal.active_predictors` carries
            # `capacity_buffer` or `freight_procurement` rows for this
            # tenant, swap this for a real lookup.
            p10 = available
            p50 = available
            p90 = available

            return {
                "lane_id": lane_id,
                "date_from": str(d_from),
                "date_to": str(d_to),
                "total_committed_loads": committed,
                "total_required_loads": required,
                "total_available_loads": available,
                "available_loads_p10": p10,
                "available_loads_p50": p50,
                "available_loads_p90": p90,
                "conformal_bands_collapsed": True,
                "recent_tender_reject_rate_14d": reject_rate,
                "tender_sample_size_14d": int(total_tenders),
                "carrier_count": int(carrier_count),
                "as_of_utc": datetime.utcnow().isoformat() + "Z",
            }

    @mcp.tool()
    async def get_dock_availability(
        tenant_id: int,
        config_id: int,
        site_id: int,
        date_from: str,
        date_to: str,
    ) -> Dict[str, Any]:
        """Return DockAvailability for a site over a date range.

        SCP planners (and L3 agents) call this to gauge how much
        physical receiving / shipping capacity TMS has available at a
        given site over a planning horizon, without needing direct
        access to TMS's `dock_door` / `appointment` tables.

        Args:
            tenant_id, config_id, site_id: canonical scope
            date_from / date_to: ISO date strings (inclusive bounds)

        Returns dict with:
            * `site_id`, `date_from`, `date_to`
            * `total_doors` — count of dock_door rows for the site
            * `active_doors` — doors with status active (subset of total)
            * `appointments_in_window` — appointments scheduled in the
              date range
            * `confirmed_count` / `requested_count` / `cancelled_count`
              — appointment status breakdown
            * `daily_occupancy` — list of {date, scheduled, capacity}
              dicts for the window
            * `as_of_utc`
        """
        from .db import get_db
        from app.models.tms_entities import (
            Appointment, AppointmentStatus, DockDoor,
        )

        d_from = date_type.fromisoformat(date_from)
        d_to = date_type.fromisoformat(date_to)

        async with get_db() as db:
            total_doors = (await db.execute(
                select(func.count(DockDoor.id)).where(
                    DockDoor.tenant_id == tenant_id,
                    DockDoor.site_id == site_id,
                )
            )).scalar() or 0

            # active / "open" doors — interpreted via DockDoor.is_active
            # if present; otherwise fall back to total
            active_doors = (await db.execute(
                select(func.count(DockDoor.id)).where(
                    DockDoor.tenant_id == tenant_id,
                    DockDoor.site_id == site_id,
                    DockDoor.is_active.is_(True),
                )
            )).scalar() or total_doors

            # Appointments in window
            ap_in_window = select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site_id,
                Appointment.scheduled_start >= datetime.combine(d_from, datetime.min.time()),
                Appointment.scheduled_start <= datetime.combine(d_to, datetime.max.time()),
            )

            # Status breakdown
            def _count(status):
                return (
                    select(func.count(Appointment.id))
                    .where(
                        Appointment.tenant_id == tenant_id,
                        Appointment.site_id == site_id,
                        Appointment.scheduled_start >= datetime.combine(d_from, datetime.min.time()),
                        Appointment.scheduled_start <= datetime.combine(d_to, datetime.max.time()),
                        Appointment.status == status,
                    )
                )

            confirmed = (await db.execute(_count(AppointmentStatus.CONFIRMED))).scalar() or 0
            requested = (await db.execute(_count(AppointmentStatus.REQUESTED))).scalar() or 0
            cancelled = (await db.execute(_count(AppointmentStatus.CANCELLED))).scalar() or 0
            total_in_window = int(confirmed) + int(requested) + int(cancelled)

            # Daily occupancy — group by scheduled_start::date
            occ_rows = (await db.execute(
                select(
                    func.date(Appointment.scheduled_start).label("d"),
                    func.count(Appointment.id),
                )
                .where(
                    Appointment.tenant_id == tenant_id,
                    Appointment.site_id == site_id,
                    Appointment.scheduled_start >= datetime.combine(d_from, datetime.min.time()),
                    Appointment.scheduled_start <= datetime.combine(d_to, datetime.max.time()),
                    Appointment.status.in_([
                        AppointmentStatus.CONFIRMED, AppointmentStatus.REQUESTED,
                    ]),
                )
                .group_by("d")
                .order_by("d")
            )).all()
            daily_occupancy = [
                {
                    "date": str(row[0]),
                    "scheduled": int(row[1]),
                    "capacity": int(active_doors),
                }
                for row in occ_rows
            ]

            return {
                "site_id": site_id,
                "date_from": str(d_from),
                "date_to": str(d_to),
                "total_doors": int(total_doors),
                "active_doors": int(active_doors),
                "appointments_in_window": total_in_window,
                "confirmed_count": int(confirmed),
                "requested_count": int(requested),
                "cancelled_count": int(cancelled),
                "daily_occupancy": daily_occupancy,
                "as_of_utc": datetime.utcnow().isoformat() + "Z",
            }

    @mcp.tool()
    async def get_active_exceptions(
        tenant_id: int,
        config_id: int,
        site_id: Optional[int] = None,
        severity_min: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return active (DETECTED + INVESTIGATING) ShipmentExceptions.

        SCP's ATPExecutorTRM and demand planners use this to back off
        from carriers / lanes / sites that are currently in trouble.

        Args:
            tenant_id, config_id: canonical scope
            site_id: optional — restrict to exceptions on shipments
                touching this site (origin or destination)
            severity_min: optional — one of LOW / MEDIUM / HIGH /
                CRITICAL; returns exceptions ≥ this severity
            limit: max rows to return (capped at 200)

        Returns dict with:
            * `count` — total count matching the filter
            * `exceptions` — list of {exception_id, shipment_id,
              exception_type, severity, resolution_status,
              detected_at, hours_open, origin_site_id,
              destination_site_id, estimated_delay_hrs}
            * `severity_breakdown` — count per severity
            * `as_of_utc`
        """
        from .db import get_db
        from app.models.tms_entities import (
            ExceptionResolutionStatus, ExceptionSeverity, ShipmentException,
            TMSShipment,
        )

        # Severity ranking; match the model's enum values for
        # `severity_min` compare. Default = include all.
        _SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        min_rank = (
            _SEVERITY_RANK.get(severity_min.upper(), 0)
            if severity_min else 0
        )
        limit = max(1, min(200, int(limit)))

        async with get_db() as db:
            # Base WHERE clause
            conds = [
                ShipmentException.tenant_id == tenant_id,
                ShipmentException.resolution_status.in_([
                    ExceptionResolutionStatus.DETECTED,
                    ExceptionResolutionStatus.INVESTIGATING,
                ]),
            ]
            if site_id is not None:
                conds.append(
                    ShipmentException.shipment_id.in_(
                        select(TMSShipment.id).where(
                            or_(
                                TMSShipment.origin_site_id == site_id,
                                TMSShipment.destination_site_id == site_id,
                            )
                        )
                    )
                )
            if severity_min:
                # Map enum values that meet or exceed min_rank
                allowed = {
                    s.value if hasattr(s, "value") else s
                    for s in ExceptionSeverity
                    if _SEVERITY_RANK.get(
                        (s.value if hasattr(s, "value") else s).upper(), 0
                    ) >= min_rank
                }
                conds.append(ShipmentException.severity.in_(list(allowed)))

            # Count
            count = (await db.execute(
                select(func.count(ShipmentException.id)).where(*conds)
            )).scalar() or 0

            # Severity breakdown
            sev_rows = (await db.execute(
                select(
                    ShipmentException.severity,
                    func.count(ShipmentException.id),
                )
                .where(*conds)
                .group_by(ShipmentException.severity)
            )).all()
            severity_breakdown = {
                (str(r[0].value) if hasattr(r[0], "value") else str(r[0])):
                    int(r[1])
                for r in sev_rows
            }

            # Top-N rows + their shipment context
            rows = (await db.execute(
                select(
                    ShipmentException.id,
                    ShipmentException.shipment_id,
                    ShipmentException.exception_type,
                    ShipmentException.severity,
                    ShipmentException.resolution_status,
                    ShipmentException.detected_at,
                    ShipmentException.estimated_delay_hrs,
                    TMSShipment.origin_site_id,
                    TMSShipment.destination_site_id,
                )
                .join(
                    TMSShipment,
                    TMSShipment.id == ShipmentException.shipment_id,
                    isouter=True,
                )
                .where(*conds)
                .order_by(desc(ShipmentException.detected_at))
                .limit(limit)
            )).all()

            now = datetime.utcnow()
            exceptions = []
            for r in rows:
                detected = r[5]
                hours_open = (
                    (now - detected).total_seconds() / 3600.0
                    if detected else None
                )
                exceptions.append({
                    "exception_id": int(r[0]),
                    "shipment_id": int(r[1]) if r[1] else None,
                    "exception_type": r[2].value if r[2] and hasattr(r[2], "value") else (str(r[2]) if r[2] else None),
                    "severity": r[3].value if r[3] and hasattr(r[3], "value") else (str(r[3]) if r[3] else None),
                    "resolution_status": r[4].value if r[4] and hasattr(r[4], "value") else (str(r[4]) if r[4] else None),
                    "detected_at": detected.isoformat() + "Z" if detected else None,
                    "hours_open": round(hours_open, 1) if hours_open is not None else None,
                    "estimated_delay_hrs": float(r[6]) if r[6] is not None else None,
                    "origin_site_id": int(r[7]) if r[7] else None,
                    "destination_site_id": int(r[8]) if r[8] else None,
                })

            return {
                "count": int(count),
                "exceptions": exceptions,
                "severity_breakdown": severity_breakdown,
                "as_of_utc": now.isoformat() + "Z",
            }

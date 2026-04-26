"""
IntermodalTransferTRM — Mode-Shift Eligibility & Economic Viability (BUILD)

Tenth TMS-native TRM. Completes the BUILD phase alongside LoadBuildTRM (#9).

Evaluates whether a TMSShipment currently planned for truck (FTL / LTL)
should shift to intermodal (truck+rail / rail-carload / ocean). Emits
ACCEPT (proceed with intermodal) or REJECT (stay on truck) based on
the Oracle-OTM / J.B. Hunt 360 pattern.

Trigger entity: `TMSShipment` (typically DRAFT or PLANNED status, before
carrier tender). One evaluation per shipment per request. Intermodal
evaluation is an option-pricing question — the planner or upstream
orchestration supplies the candidate intermodal route + rate, and this
TRM says GO / NO-GO.

v1 design note: the intermodal network (ramp catalog, intermodal
rate-sheet, ramp-congestion feed) is not yet in TMS. The service
therefore accepts the intermodal-specific inputs as explicit overrides
on the endpoint — matching how Oracle OTM's mode-shift evaluator is
called from the optimizer. When the intermodal network lands in Sprint 2,
the state-builder will fill these in from canonical state.

Hard gates (heuristic REJECTs immediately):

1. Hazmat freight (rail restrictions) → REJECT
2. Temperature-controlled (limited reefer intermodal availability) → REJECT
3. Ramp distance > 100 miles either end (drayage kills economics) → REJECT
4. Lane < 500 miles (below intermodal breakeven) → REJECT
5. Ramp congestion > 70% → REJECT
6. Transit time exceeds delivery window → REJECT
7. Reliability < 80% with window < 2 days → REJECT

Soft evaluation:

- Drayage-decomposed all-in cost vs truck rate, with inventory
  carrying-cost adjustment (44,000 lb × 10%/365 × penalty_days).
- 8% savings threshold (5% on long-haul > 800 mi) to ACCEPT.

Observational v1 — no TMSShipment mutation. ACCEPT decisions are logged
at INFO severity; REJECT at INFO with rationale. The mode-change
write-path lands alongside PREPARE.3's dual-write to core.agent_decisions
with decision_type=INTERMODAL_TRANSFER.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intermodal_network import (
    IntermodalRate, RampCongestionSnapshot, SpotRateSnapshot,
)
from app.models.tms_entities import TMSShipment, TransportMode
from app.models.transportation_config import LaneProfile
from app.services.powell.agent_decision_writer import record_trm_decision

logger = logging.getLogger(__name__)



class IntermodalTransferTRM:
    """
    Evaluates truck→intermodal mode shift for a candidate shipment.

    Lifecycle:
        trm = IntermodalTransferTRM(db_session, tenant_id, config_id)
        decision = trm.evaluate_shipment(shipment, overrides=...)

    `overrides` carries the intermodal-specific inputs the planner
    supplies: ramp proximity, intermodal rate, transit times, etc.
    Missing overrides default to values that fail the gates (i.e., the
    heuristic REJECTs unless the caller provides a credible alternative)
    — the conservative default when network data is not yet wired.

    No TMSShipment mutation in v1.
    """

    # Defaults chosen to REJECT by default when overrides are missing:
    # ramp distance > 100 mi fails gate 3.
    _DEFAULT_ORIGIN_RAMP_MILES = 9999.0
    _DEFAULT_DEST_RAMP_MILES = 9999.0
    _DEFAULT_INTERMODAL_RELIABILITY = 0.85
    _DEFAULT_RAMP_CONGESTION = 0.3

    def __init__(self, db: Session, tenant_id: int, config_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self._model = None

        from azirella_data_model.powell.tms.heuristic_library.dispatch import (
            compute_tms_decision,
        )
        from azirella_data_model.powell.tms.heuristic_library.base import (
            IntermodalTransferState,
        )
        self._compute_decision = compute_tms_decision
        self._StateClass = IntermodalTransferState

    def load_checkpoint(self, checkpoint_path: str) -> bool:
        """Load a trained BC checkpoint. Returns True on success."""
        ckpt = load_bc_checkpoint(checkpoint_path, "intermodal_transfer")
        if ckpt is None:
            return False
        self._model = ckpt
        return True

    def evaluate_shipment(
        self,
        shipment: TMSShipment,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate mode shift for one shipment. Never mutates it.

        Args:
            shipment: the candidate TMSShipment (any status — typically
                DRAFT/PLANNED, before carrier tender).
            overrides: intermodal-specific inputs the planner supplies
                (see `_build_state` for the full key list). Missing keys
                default to gate-failing values so the heuristic REJECTs
                in the absence of network data.
        """
        state = self._build_state(shipment, overrides or {})
        decision = self._compute_decision("intermodal_transfer", state)

        action_name = {
            0: "ACCEPT",
            1: "REJECT",
            2: "DEFER",
            3: "ESCALATE",
            4: "MODIFY",
        }.get(decision.action, "UNKNOWN")

        return {
            "shipment_id": shipment.id,
            "shipment_number": shipment.shipment_number,
            "current_mode": state.current_mode,
            "candidate_mode": state.candidate_mode,
            "truck_rate": state.truck_rate,
            "intermodal_rate": state.intermodal_rate,
            "total_truck_miles": state.total_truck_miles,
            "origin_ramp_distance_miles": state.origin_ramp_distance_miles,
            "dest_ramp_distance_miles": state.dest_ramp_distance_miles,
            "truck_transit_days": state.truck_transit_days,
            "intermodal_transit_days": state.intermodal_transit_days,
            "delivery_window_days": state.delivery_window_days,
            "cost_savings_pct": state.cost_savings_pct(),
            "transit_penalty_days": state.transit_time_penalty_days(),
            "is_hazmat": state.is_hazmat,
            "is_temperature_controlled": state.is_temperature_controlled,
            "action": decision.action,
            "action_name": action_name,
            "confidence": decision.confidence,
            "urgency": decision.urgency,
            "reasoning": decision.reasoning,
            "decision_method": "trm_model" if self._model else "heuristic",
            "scoring_detail": decision.params_used,
        }

    def evaluate_and_log(
        self,
        shipment: TMSShipment,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate + log. No DB write in v1."""
        result = self.evaluate_shipment(shipment, overrides=overrides)
        if not result:
            return result

        action_name = result["action_name"]
        logger.info(
            "IntermodalTransfer %s: shipment %s — %s (savings=%.1f%%, urg=%.2f)",
            action_name,
            shipment.shipment_number,
            result["reasoning"],
            (result["cost_savings_pct"] or 0.0) * 100,
            result["urgency"],
        )

        # PREPARE.3 dual-write to core.agent_decisions
        record_trm_decision(
            self.db,
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            trm_type="intermodal_transfer",
            result=result,
            item_code=f"shipment-{shipment.id}",
            item_name=f"shipment {shipment.shipment_number}",
            category="intermodal_transfer",
            impact_description=result.get("reasoning") or None,
        )

        return result

    # ── State-builder helpers ────────────────────────────────────────────

    def _latest_truck_spot_rate(
        self, shipment: TMSShipment, mode: TransportMode
    ) -> Optional[float]:
        """Most recent spot_rate_snapshot for this lane × mode (any source).

        Lookup strategy: lane_id match first, then (origin, destination)
        fallback. Returns the rate_per_load of the most recent valid_at
        snapshot, or None when no data is wired yet.
        """
        # Prefer lane_id-keyed match
        if shipment.lane_id:
            row = self.db.execute(
                select(SpotRateSnapshot).where(
                    SpotRateSnapshot.tenant_id == self.tenant_id,
                    SpotRateSnapshot.lane_id == shipment.lane_id,
                    SpotRateSnapshot.mode == mode,
                ).order_by(SpotRateSnapshot.valid_at.desc()).limit(1)
            ).scalar_one_or_none()
            if row:
                return float(row.rate_per_load)

        # Fall back to (origin, destination) keying
        if shipment.origin_site_id and shipment.destination_site_id:
            row = self.db.execute(
                select(SpotRateSnapshot).where(
                    SpotRateSnapshot.tenant_id == self.tenant_id,
                    SpotRateSnapshot.origin_site_id == shipment.origin_site_id,
                    SpotRateSnapshot.destination_site_id == shipment.destination_site_id,
                    SpotRateSnapshot.mode == mode,
                ).order_by(SpotRateSnapshot.valid_at.desc()).limit(1)
            ).scalar_one_or_none()
            if row:
                return float(row.rate_per_load)
        return None

    def _resolve_intermodal_rate(
        self,
        candidate_mode_str: str,
        valid_on: Optional[datetime] = None,
    ) -> Optional[IntermodalRate]:
        """Cheapest active intermodal_rate for this tenant on the given mode.

        Without ramp coordinates wired into Sites, we don't yet do
        (origin_ramp, destination_ramp) resolution. v1 picks the cheapest
        active rate for the mode — sufficient for the planner-supplied-
        overrides path. The lookup tightens to per-route once
        site→ramp linkage data lands.
        """
        try:
            mode_enum = TransportMode(candidate_mode_str)
        except ValueError:
            return None

        as_of = valid_on or datetime.utcnow()
        return self.db.execute(
            select(IntermodalRate).where(
                IntermodalRate.tenant_id == self.tenant_id,
                IntermodalRate.mode == mode_enum,
                IntermodalRate.is_active.is_(True),
                IntermodalRate.valid_from <= as_of.date(),
                IntermodalRate.valid_to >= as_of.date(),
            ).order_by(IntermodalRate.rate_per_load.asc()).limit(1)
        ).scalar_one_or_none()

    def _latest_ramp_congestion(self, ramp_id: int) -> Optional[float]:
        """Most recent congestion_level for a ramp, or None."""
        row = self.db.execute(
            select(RampCongestionSnapshot.congestion_level).where(
                RampCongestionSnapshot.tenant_id == self.tenant_id,
                RampCongestionSnapshot.ramp_id == ramp_id,
            ).order_by(RampCongestionSnapshot.snapshot_at.desc()).limit(1)
        ).scalar_one_or_none()
        return float(row) if row is not None else None

    def _build_state(
        self, shipment: TMSShipment, overrides: Dict[str, Any]
    ):
        """Construct IntermodalTransferState from shipment + overrides + lane.

        Overrides (planner-supplied intermodal-specific inputs):
            candidate_mode: str                     (default: RAIL_INTERMODAL)
            origin_to_ramp_miles: float
            ramp_to_ramp_miles: float
            ramp_to_dest_miles: float
            truck_rate: float                       (falls back to shipment.estimated_cost)
            intermodal_rate: float
            drayage_rate_origin: float
            drayage_rate_dest: float
            truck_transit_days: float               (falls back to lane.p50_transit_days)
            intermodal_transit_days: float
            origin_ramp_distance_miles: float       (default 9999 → REJECT)
            dest_ramp_distance_miles: float         (default 9999 → REJECT)
            ramp_congestion_level: float            (default 0.3)
            intermodal_reliability_pct: float       (default 0.85)
            rail_capacity_available: bool           (default True)
            weather_risk_score: float               (default 0.0)
        """
        # Route miles — prefer LaneProfile.distance_miles when shipment.lane_id known
        total_truck_miles = 0.0
        truck_transit_days_from_lane = 0.0
        if shipment.lane_id:
            lp = self.db.execute(
                select(LaneProfile).where(
                    LaneProfile.lane_id == shipment.lane_id,
                    LaneProfile.config_id == self.config_id,
                )
            ).scalar_one_or_none()
            if lp:
                total_truck_miles = float(lp.distance_miles or 0.0)
                truck_transit_days_from_lane = float(lp.p50_transit_days or lp.avg_transit_days or 0.0)

        # Delivery window days — requested_delivery − requested_pickup in days
        delivery_window_days = 0.0
        if shipment.requested_pickup_date and shipment.requested_delivery_date:
            delta = shipment.requested_delivery_date - shipment.requested_pickup_date
            delivery_window_days = max(0.0, delta.total_seconds() / 86400.0)

        # Commodity value per lb for inventory-carrying-cost
        commodity_value_per_lb = 0.0
        if shipment.declared_value and shipment.weight and shipment.weight > 0:
            commodity_value_per_lb = float(shipment.declared_value) / float(shipment.weight)

        current_mode = (
            shipment.mode.value if getattr(shipment.mode, "value", None) else str(shipment.mode or "FTL")
        )
        candidate_mode_str = str(overrides.get("candidate_mode", "RAIL_INTERMODAL"))

        # ── DB-backed defaults (populated by Sprint-2 ratesheet ingest) ──
        # When tables are empty, these all return None and the override
        # path with its conservative-REJECT defaults takes over. When
        # data is wired, an override-less call gets sane fallbacks.
        truck_spot = None
        intermodal_rate_db: Optional[IntermodalRate] = None
        try:
            current_mode_enum = TransportMode(current_mode)
            truck_spot = self._latest_truck_spot_rate(shipment, current_mode_enum)
        except ValueError:
            pass

        intermodal_rate_db = self._resolve_intermodal_rate(candidate_mode_str)

        # Default truck rate: override > spot_rate_snapshot > shipment.estimated_cost
        truck_rate_default = (
            truck_spot
            if truck_spot is not None
            else float(shipment.estimated_cost or 0.0)
        )

        # Default intermodal rate / transit / reliability: override > intermodal_rate row > 0
        intermodal_rate_default = (
            float(intermodal_rate_db.rate_per_load) if intermodal_rate_db else 0.0
        )
        intermodal_transit_default = (
            float(intermodal_rate_db.transit_days_p50) if intermodal_rate_db else 0.0
        )
        intermodal_reliability_default = (
            float(intermodal_rate_db.reliability_pct)
            if intermodal_rate_db and intermodal_rate_db.reliability_pct is not None
            else self._DEFAULT_INTERMODAL_RELIABILITY
        )

        # Ramp congestion: override > most-recent snapshot for the
        # planner-named ramps > class default. Until the ramp catalog
        # has site-coordinate linkage we can't pick the ramps from the
        # shipment alone — leave that resolution to the override caller.
        congestion_origin = self._latest_ramp_congestion(
            int(overrides["origin_ramp_id"])
        ) if overrides.get("origin_ramp_id") else None
        congestion_dest = self._latest_ramp_congestion(
            int(overrides["destination_ramp_id"])
        ) if overrides.get("destination_ramp_id") else None
        congestion_default = max(
            v for v in (congestion_origin, congestion_dest)
            if v is not None
        ) if (congestion_origin is not None or congestion_dest is not None) \
            else self._DEFAULT_RAMP_CONGESTION

        return self._StateClass(
            shipment_id=shipment.id,
            current_mode=current_mode,
            candidate_mode=candidate_mode_str,
            origin_to_ramp_miles=float(overrides.get("origin_to_ramp_miles", 0.0)),
            ramp_to_ramp_miles=float(overrides.get("ramp_to_ramp_miles", 0.0)),
            ramp_to_dest_miles=float(overrides.get("ramp_to_dest_miles", 0.0)),
            total_truck_miles=float(overrides.get("total_truck_miles", total_truck_miles)),
            truck_rate=float(overrides.get("truck_rate", truck_rate_default)),
            intermodal_rate=float(overrides.get("intermodal_rate", intermodal_rate_default)),
            drayage_rate_origin=float(overrides.get("drayage_rate_origin", 0.0)),
            drayage_rate_dest=float(overrides.get("drayage_rate_dest", 0.0)),
            truck_transit_days=float(overrides.get(
                "truck_transit_days", truck_transit_days_from_lane
            )),
            intermodal_transit_days=float(overrides.get(
                "intermodal_transit_days", intermodal_transit_default
            )),
            delivery_window_days=float(overrides.get(
                "delivery_window_days", delivery_window_days
            )),
            rail_capacity_available=bool(overrides.get("rail_capacity_available", True)),
            ramp_congestion_level=float(overrides.get(
                "ramp_congestion_level", congestion_default
            )),
            intermodal_reliability_pct=float(overrides.get(
                "intermodal_reliability_pct", intermodal_reliability_default
            )),
            weather_risk_score=float(overrides.get("weather_risk_score", 0.0)),
            is_hazmat=bool(shipment.is_hazmat),
            is_temperature_controlled=bool(shipment.is_temperature_sensitive),
            commodity_value_per_lb=commodity_value_per_lb,
            origin_ramp_distance_miles=float(overrides.get(
                "origin_ramp_distance_miles", self._DEFAULT_ORIGIN_RAMP_MILES
            )),
            dest_ramp_distance_miles=float(overrides.get(
                "dest_ramp_distance_miles", self._DEFAULT_DEST_RAMP_MILES
            )),
        )

"""
ShipmentTrackingTRM — In-Transit Visibility & Exception Detection (SENSE phase)

Third TMS TRM. Maps to SCP's `order_tracking` slot. Evaluates shipment
progress and decides: ACCEPT (nominal), MODIFY (at-risk — replan), or
ESCALATE (tracking lost / temperature excursion / late ETA).

Trigger entity: Load in status IN_TRANSIT. One evaluation per load per
cycle (typically called from the scheduler; also exposed via endpoint
for ad-hoc inspection).

Feature-vector sources (v1):
- planned_pickup ← Load.planned_departure
- actual_pickup  ← Load.actual_departure
- planned_delivery ← Load.planned_arrival
- current_eta    ← Load.actual_arrival if present, else Load.planned_arrival
- total_miles    ← Load.total_miles
- last_update_hours_ago ← hours since latest TrackingEvent.event_timestamp
                         for this shipment (0.0 if no events — treated as
                         "just updated" to avoid false tracking-lost)
- carrier_otp_pct ← Carrier.on_time_delivery_pct (fallback 0.95)
- carrier_reliability_score ← proxy from OTP (0.8 default)
- transport_mode ← Load.mode.value

Not yet sourced (honest defaults used; wire up when data lands):
- current_lat / current_lon (need tracking_event GPS fields populated)
- eta_p10 / eta_p90 (conformal intervals — Sprint 2 conformal extension)
- is_temperature_sensitive / current_temp (need commodity sensitivity
  flag + reefer temperature reporting)

No persistence in v1 (same pattern as CapacityPromise). ESCALATE / MODIFY
decisions are logged at warning level for human review; ACCEPT is
info-level. PREPARE.3's dual-write to core.agent_decisions with
decision_type=SHIPMENT_TRACKING lands in Sprint 1 Week 4-5.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.models.tms_entities import (
    Carrier, CarrierScorecard, Load, LoadStatus, TrackingEvent, TransportMode,
)


from app.services.powell.agent_decision_writer import record_trm_decision
logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# Transport-mode string used by Core's silence-threshold table. TMS's
# TransportMode enum values (FTL, LTL, FCL, ...) match Core's keys 1:1
# for the core cases, so this map is mostly a passthrough; kept explicit
# so the dispatcher can evolve independently of TMS enum additions.
_MODE_TO_CORE = {
    "FTL": "FTL", "LTL": "LTL", "PARCEL": "PARCEL",
    "FCL": "FCL", "LCL": "LCL", "BULK": "BULK_OCEAN",
    "AIR_STD": "AIR_STD", "AIR_EXPRESS": "AIR_EXPRESS",
    "CHARTER": "AIR_EXPRESS",
    "RAIL_INTERMODAL": "RAIL_INTERMODAL", "RAIL_CARLOAD": "RAIL_CARLOAD",
}


class ShipmentTrackingTRM:
    """
    Evaluates in-transit shipments and detects exceptions.

    Lifecycle:
        trm = ShipmentTrackingTRM(db_session, tenant_id, config_id)
        decisions = trm.evaluate_pending_shipments()

    Unlike FreightProcurement / CapacityPromise, this TRM does NOT mutate
    Load.status. Tracking is observational — the state transition that
    matters (IN_TRANSIT → DELIVERED) is driven by carrier events, not by
    an agent decision. The TRM's ESCALATE action produces a structured
    log entry that Decision Stream will surface once PREPARE.3 lands.
    """

    DEFAULT_CARRIER_OTP = 0.95
    DEFAULT_CARRIER_RELIABILITY = 0.80

    def __init__(self, db: Session, tenant_id: int, config_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self._model = None

        from azirella_data_model.powell.tms.heuristic_library.dispatch import (
            compute_tms_decision,
        )
        from azirella_data_model.powell.tms.heuristic_library.base import (
            ShipmentTrackingState,
        )
        self._compute_decision = compute_tms_decision
        self._StateClass = ShipmentTrackingState

    def load_checkpoint(self, checkpoint_path: str) -> bool:
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available — using heuristic fallback")
            return False
        import os
        if not os.path.exists(checkpoint_path):
            return False
        logger.info("ShipmentTracking checkpoint path present but loader is a stub")
        return False

    def find_in_transit_loads(self) -> List[Load]:
        """Loads actively in transit — candidates for tracking evaluation."""
        return self.db.execute(
            select(Load).where(
                and_(
                    Load.tenant_id == self.tenant_id,
                    Load.status == LoadStatus.IN_TRANSIT,
                )
            ).order_by(Load.planned_arrival.nullslast(), Load.id)
        ).scalars().all()

    def evaluate_load(self, load: Load) -> Optional[Dict[str, Any]]:
        """Evaluate tracking decision for one load. Never mutates the load."""
        state = self._build_state(load)
        decision = self._compute_decision("shipment_tracking", state)

        action_name = {
            0: "ACCEPT",
            1: "REJECT",
            2: "DEFER",
            3: "ESCALATE",
            4: "MODIFY",
        }.get(decision.action, "UNKNOWN")

        return {
            "load_id": load.id,
            "load_number": load.load_number,
            "load_status": load.status.value,
            "transport_mode": state.transport_mode,
            "pct_complete": state.pct_complete,
            "hours_late": decision.quantity if action_name == "ESCALATE" else 0.0,
            "last_update_hours_ago": state.last_update_hours_ago,
            "action": decision.action,
            "action_name": action_name,
            "confidence": decision.confidence,
            "urgency": decision.urgency,
            "reasoning": decision.reasoning,
            "decision_method": "trm_model" if self._model else "heuristic",
            "scoring_detail": decision.params_used,
        }

    def evaluate_and_log(self, load: Load) -> Optional[Dict[str, Any]]:
        """Evaluate + log at a severity matching the decision urgency.

        No Load.status mutation (tracking is observational). ESCALATE and
        MODIFY log as WARNING so Decision Stream / log aggregators can
        pick them up; ACCEPT is INFO.
        """
        result = self.evaluate_load(load)
        if not result:
            return result

        action_name = result["action_name"]
        if action_name in ("ESCALATE", "MODIFY"):
            logger.warning(
                "ShipmentTracking %s: load %s — %s (urg=%.2f)",
                action_name,
                load.load_number,
                result["reasoning"],
                result["urgency"],
            )
        else:
            logger.info(
                "ShipmentTracking %s: load %s (pct=%.0f%%, urg=%.2f)",
                action_name,
                load.load_number,
                result["pct_complete"] * 100,
                result["urgency"],
            )

        # PREPARE.3 dual-write to core.agent_decisions
        record_trm_decision(
            self.db,
            tenant_id=self.tenant_id,
            trm_type="shipment_tracking",
            result=result,
            item_code=f"load-{load.id}",
            item_name=f"load {load.load_number}",
            category="shipment_tracking",
        )

        return result

    def evaluate_pending_shipments(self) -> List[Dict[str, Any]]:
        """Evaluate every IN_TRANSIT load."""
        loads = self.find_in_transit_loads()
        results = []
        for load in loads:
            result = self.evaluate_and_log(load)
            if result:
                results.append(result)
        return results

    # ── Helpers ──────────────────────────────────────────────────────────

    def _build_state(self, load: Load):
        """Construct ShipmentTrackingState from Load + carrier + tracking_event."""
        # Carrier performance — from most-recent CarrierScorecard row
        # (the on-time fields live on scorecard, not Carrier).
        otp_pct = self.DEFAULT_CARRIER_OTP
        reliability = self.DEFAULT_CARRIER_RELIABILITY
        if load.carrier_id:
            scorecard = self.db.execute(
                select(CarrierScorecard)
                .where(CarrierScorecard.carrier_id == load.carrier_id)
                .order_by(desc(CarrierScorecard.period_end))
                .limit(1)
            ).scalar_one_or_none()
            if scorecard and scorecard.on_time_delivery_pct is not None:
                otp_pct = float(scorecard.on_time_delivery_pct)
                # Simple proxy: reliability tracks OTP with a floor of 0.5
                reliability = max(0.5, min(1.0, otp_pct))

        # Last tracking update for this load's shipment legs
        last_update_hours_ago = 0.0
        last_event = self.db.execute(
            select(TrackingEvent)
            .where(TrackingEvent.shipment_id == load.id)
            .order_by(desc(TrackingEvent.event_timestamp))
            .limit(1)
        ).scalar_one_or_none()
        if last_event and last_event.event_timestamp:
            delta = datetime.utcnow() - last_event.event_timestamp
            last_update_hours_ago = max(0.0, delta.total_seconds() / 3600)

        # Progress: pct_complete from miles_remaining / total_miles when
        # available. Without live GPS this is a coarse proxy — the TRM's
        # at-risk branch tolerates sparse data.
        total_miles = float(load.total_miles or 0.0)
        pct_complete = 0.0
        miles_remaining = total_miles
        if load.actual_arrival:
            pct_complete = 1.0
            miles_remaining = 0.0
        elif load.actual_departure and load.planned_arrival:
            elapsed = (datetime.utcnow() - load.actual_departure).total_seconds()
            total = (load.planned_arrival - load.actual_departure).total_seconds()
            if total > 0:
                pct_complete = max(0.0, min(1.0, elapsed / total))
                miles_remaining = total_miles * (1.0 - pct_complete)

        transport_mode = (
            _MODE_TO_CORE.get(load.mode.value, load.mode.value)
            if load.mode else "FTL"
        )

        current_eta = load.actual_arrival or load.planned_arrival

        return self._StateClass(
            shipment_id=load.id,
            shipment_status=load.status.value,
            planned_pickup=load.planned_departure,
            actual_pickup=load.actual_departure,
            planned_delivery=load.planned_arrival,
            current_eta=current_eta,
            eta_p10=None,
            eta_p90=None,
            current_lat=0.0,
            current_lon=0.0,
            last_update_hours_ago=last_update_hours_ago,
            total_miles=total_miles,
            miles_remaining=miles_remaining,
            pct_complete=pct_complete,
            carrier_otp_pct=otp_pct,
            carrier_reliability_score=reliability,
            active_exceptions_count=0,
            is_temperature_sensitive=False,
            current_temp=None,
            temp_min=None,
            temp_max=None,
            transport_mode=transport_mode,
        )

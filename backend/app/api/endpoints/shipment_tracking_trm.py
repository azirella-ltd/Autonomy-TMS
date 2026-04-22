"""
Shipment Tracking TRM API — In-Transit Exception Detection (SENSE phase)

Third TMS-native TRM endpoint. Maps to SCP's order_tracking slot.
Mounted at `/shipment-tracking-trm/*` to avoid collision with the
pre-existing `/shipment-tracking/*` Sprint-2 material-visibility service
(which returns shipment-level Views, not TRM decisions).

Evaluates IN_TRANSIT loads and classifies them into ACCEPT (nominal),
MODIFY (at-risk — replan), or ESCALATE (tracking lost / temp excursion /
materially late). No Load.status mutation — tracking is observational.

Endpoints:
  POST /shipment-tracking-trm/evaluate/{load_id} — evaluate one + log
  POST /shipment-tracking-trm/evaluate-all       — evaluate all IN_TRANSIT
  GET  /shipment-tracking-trm/status/{load_id}   — stateless preview
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import Load
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipment-tracking-trm", tags=["shipment-tracking-trm"])


class ShipmentTrackingResult(BaseModel):
    load_id: int
    load_number: str
    load_status: str
    transport_mode: str
    pct_complete: float
    hours_late: float = 0.0
    last_update_hours_ago: float = 0.0
    action_name: str
    confidence: float = 1.0
    urgency: float = 0.1
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate/{load_id}", response_model=ShipmentTrackingResult)
async def evaluate_shipment_tracking(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate tracking for a specific Load and emit the log line.

    No Load.status mutation — tracking is observational.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.shipment_tracking_trm import ShipmentTrackingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = ShipmentTrackingTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_and_log(load)
        if not result:
            raise HTTPException(422, "No tracking decision produced")

        return ShipmentTrackingResult(**{
            k: v for k, v in result.items()
            if k in ShipmentTrackingResult.model_fields
        })


@router.post("/evaluate-all", response_model=List[ShipmentTrackingResult])
async def evaluate_all_in_transit(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every IN_TRANSIT load for the current tenant.

    SYSTEM_ADMIN (tenant_id=None) returns [] — tracking is tenant-scoped.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.shipment_tracking_trm import ShipmentTrackingTRM
        trm = ShipmentTrackingTRM(sync_db, user.tenant_id, 0)

        results = trm.evaluate_pending_shipments()
        return [
            ShipmentTrackingResult(**{
                k: v for k, v in r.items()
                if k in ShipmentTrackingResult.model_fields
            })
            for r in results
        ]


@router.get("/status/{load_id}", response_model=ShipmentTrackingResult)
async def get_shipment_tracking_status(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live tracking-decision preview for any Load regardless of status.

    Unlike `evaluate/`, this does not emit a log line — pure read.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.shipment_tracking_trm import ShipmentTrackingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = ShipmentTrackingTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_load(load)
        if not result:
            raise HTTPException(422, "No tracking decision produced")

        return ShipmentTrackingResult(**{
            k: v for k, v in result.items()
            if k in ShipmentTrackingResult.model_fields
        })

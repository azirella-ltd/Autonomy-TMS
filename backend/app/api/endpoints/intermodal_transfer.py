"""
Intermodal Transfer TRM API — Mode-shift eligibility & economic viability (BUILD)

Tenth TMS-native TRM endpoint. Completes the BUILD phase alongside
`/load-build/*`.

Evaluates TMSShipment rows for the truck→intermodal mode-shift
decision, using the Oracle OTM / J.B. Hunt 360 pattern: hard
eligibility gates (hazmat, reefer, ramp proximity, distance, congestion,
transit feasibility, reliability) followed by drayage-decomposed cost
comparison with inventory-carrying-cost adjustment.

Intermodal-specific inputs (rate, ramp miles, transit, congestion) are
supplied as explicit endpoint overrides since the TMS intermodal
network (ramp catalog, intermodal rate-sheet, congestion feed) is not
yet wired. This matches how Oracle OTM's mode-shift evaluator is
called from the optimizer.

Endpoints:
  POST /intermodal-transfer-trm/evaluate/{shipment_id} — evaluate + log
  GET  /intermodal-transfer-trm/status/{shipment_id}   — stateless preview
                                                        (query-string overrides)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import TMSShipment
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intermodal-transfer-trm", tags=["intermodal-transfer-trm"])


class IntermodalOverrides(BaseModel):
    """Planner-supplied intermodal-specific inputs.

    Missing fields default to values that fail the heuristic gates, so
    the TRM REJECTs by default when the caller has no credible
    intermodal alternative to evaluate.
    """
    candidate_mode: str = "RAIL_INTERMODAL"
    origin_to_ramp_miles: Optional[float] = None
    ramp_to_ramp_miles: Optional[float] = None
    ramp_to_dest_miles: Optional[float] = None
    total_truck_miles: Optional[float] = None
    truck_rate: Optional[float] = None
    intermodal_rate: Optional[float] = None
    drayage_rate_origin: Optional[float] = None
    drayage_rate_dest: Optional[float] = None
    truck_transit_days: Optional[float] = None
    intermodal_transit_days: Optional[float] = None
    delivery_window_days: Optional[float] = None
    rail_capacity_available: Optional[bool] = None
    ramp_congestion_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    intermodal_reliability_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
    weather_risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    origin_ramp_distance_miles: Optional[float] = None
    dest_ramp_distance_miles: Optional[float] = None


class IntermodalTransferResult(BaseModel):
    shipment_id: int
    shipment_number: str
    current_mode: str = "FTL"
    candidate_mode: str = "RAIL_INTERMODAL"
    truck_rate: float = 0.0
    intermodal_rate: float = 0.0
    total_truck_miles: float = 0.0
    origin_ramp_distance_miles: float = 0.0
    dest_ramp_distance_miles: float = 0.0
    truck_transit_days: float = 0.0
    intermodal_transit_days: float = 0.0
    delivery_window_days: float = 0.0
    cost_savings_pct: float = 0.0
    transit_penalty_days: float = 0.0
    is_hazmat: bool = False
    is_temperature_controlled: bool = False
    action_name: str = "REJECT"
    confidence: float = 1.0
    urgency: float = 0.1
    reasoning: str = ""
    decision_method: str = "heuristic"


def _result_to_schema(result: dict) -> IntermodalTransferResult:
    return IntermodalTransferResult(**{
        k: v for k, v in result.items()
        if k in IntermodalTransferResult.model_fields
    })


def _overrides_to_dict(overrides: Optional[IntermodalOverrides]) -> Dict[str, Any]:
    if overrides is None:
        return {}
    return {k: v for k, v in overrides.model_dump().items() if v is not None}


@router.post("/evaluate/{shipment_id}", response_model=IntermodalTransferResult)
async def evaluate_intermodal_transfer(
    shipment_id: int,
    overrides: Optional[IntermodalOverrides] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate mode-shift for one shipment and emit the log line.

    Pass intermodal-specific inputs (rate, ramp miles, transit) in the
    request body as `overrides`. Missing overrides fall back to
    gate-failing defaults → REJECT. No TMSShipment mutation.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        q = select(TMSShipment).where(TMSShipment.id == shipment_id)
        if user.tenant_id is not None:
            q = q.where(TMSShipment.tenant_id == user.tenant_id)
        shipment = sync_db.execute(q).scalar_one_or_none()
        if not shipment:
            raise HTTPException(404, f"TMSShipment {shipment_id} not found")

        from app.services.powell.intermodal_transfer_trm import IntermodalTransferTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else shipment.tenant_id
        )
        trm = IntermodalTransferTRM(
            sync_db, effective_tenant_id, shipment.config_id or 0,
        )

        result = trm.evaluate_and_log(shipment, overrides=_overrides_to_dict(overrides))
        if not result:
            raise HTTPException(422, "No intermodal-transfer decision produced")

        return _result_to_schema(result)


@router.post("/status/{shipment_id}", response_model=IntermodalTransferResult)
async def get_intermodal_transfer_status(
    shipment_id: int,
    overrides: Optional[IntermodalOverrides] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stateless mode-shift preview. Pure read — no log.

    Same override body as evaluate/. Use this when exploring what-if
    scenarios (e.g., testing a different intermodal rate).
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        q = select(TMSShipment).where(TMSShipment.id == shipment_id)
        if user.tenant_id is not None:
            q = q.where(TMSShipment.tenant_id == user.tenant_id)
        shipment = sync_db.execute(q).scalar_one_or_none()
        if not shipment:
            raise HTTPException(404, f"TMSShipment {shipment_id} not found")

        from app.services.powell.intermodal_transfer_trm import IntermodalTransferTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else shipment.tenant_id
        )
        trm = IntermodalTransferTRM(
            sync_db, effective_tenant_id, shipment.config_id or 0,
        )

        result = trm.evaluate_shipment(shipment, overrides=_overrides_to_dict(overrides))
        if not result:
            raise HTTPException(422, "No intermodal-transfer decision produced")

        return _result_to_schema(result)

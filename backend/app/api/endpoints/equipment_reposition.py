"""
Equipment Reposition TRM API — Empty-Vehicle Redistribution (REFLECT phase)

Eleventh and final TMS-native TRM endpoint. Completes the phase cycle.

Evaluates (source, target, equipment_type) repositioning candidates and
emits HOLD (no move) or REPOSITION (move N units) with ROI-gated
quantity. Follows the Powell 1996 / Crainic et al. 1993 dynamic-assignment
pattern with demand-weighted surplus/deficit + ROI threshold.

Endpoints:
  POST /equipment-reposition-trm/evaluate     — evaluate one (source, target, type)
  POST /equipment-reposition-trm/network-sweep — greedy pair all surplus/deficit
                                                 sites for a given equipment_type
  POST /equipment-reposition-trm/status        — stateless per-pair preview
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.tms_entities import EquipmentType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/equipment-reposition-trm", tags=["equipment-reposition-trm"])


class EquipmentRepositionOverrides(BaseModel):
    """Planner-supplied economics overrides.

    `reposition_miles` falls back to LaneProfile.distance_miles when not
    supplied; `reposition_cost` falls back to `$2.20/mi × miles`.
    `cost_of_not_repositioning` defaults to 0 — caller should supply a
    credible spot-premium estimate for ROI to be meaningful.
    """
    reposition_miles: Optional[float] = Field(None, ge=0)
    reposition_cost: Optional[float] = Field(None, ge=0)
    cost_of_not_repositioning: Optional[float] = Field(None, ge=0)
    reposition_transit_hours: Optional[float] = Field(None, ge=0)
    breakeven_loads: Optional[int] = Field(None, ge=1)


class EquipmentRepositionEvaluateBody(BaseModel):
    source_site_id: int
    target_site_id: int
    equipment_type: str = "DRY_VAN"
    overrides: Optional[EquipmentRepositionOverrides] = None


class EquipmentRepositionResult(BaseModel):
    source_site_id: int
    target_site_id: int
    equipment_type: str
    source_equipment_count: int = 0
    source_demand_next_7d: int = 0
    target_equipment_count: int = 0
    target_demand_next_7d: int = 0
    source_surplus: int = 0
    target_deficit: int = 0
    reposition_miles: float = 0.0
    reposition_cost: float = 0.0
    cost_of_not_repositioning: float = 0.0
    roi: float = 0.0
    fleet_utilization_pct: float = 0.0
    proposed_quantity: int = 0
    action_name: str = "HOLD"
    confidence: float = 1.0
    urgency: float = 0.1
    reasoning: str = ""
    decision_method: str = "heuristic"


def _result_to_schema(result: dict) -> EquipmentRepositionResult:
    return EquipmentRepositionResult(**{
        k: v for k, v in result.items()
        if k in EquipmentRepositionResult.model_fields
    })


def _overrides_to_dict(overrides: Optional[EquipmentRepositionOverrides]) -> Dict[str, Any]:
    if overrides is None:
        return {}
    return {k: v for k, v in overrides.model_dump().items() if v is not None}


def _resolve_config_id(sync_db, user: User, explicit_config_id: Optional[int]) -> int:
    """Pick a config_id. Tenant users get their default if not specified."""
    if explicit_config_id is not None:
        return explicit_config_id
    if user.tenant_id is None:
        raise HTTPException(400, "config_id required for system-admin calls")
    from app.models.supply_chain_config import SupplyChainConfig
    cfg = sync_db.execute(
        select(SupplyChainConfig)
        .where(SupplyChainConfig.tenant_id == user.tenant_id)
        .order_by(SupplyChainConfig.id)
    ).scalars().first()
    if not cfg:
        raise HTTPException(404, "No SupplyChainConfig for tenant")
    return cfg.id


@router.post("/evaluate", response_model=EquipmentRepositionResult)
async def evaluate_reposition_pair(
    payload: EquipmentRepositionEvaluateBody = Body(...),
    config_id: Optional[int] = Query(None, description="SupplyChainConfig id"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate one (source, target, equipment_type) repositioning candidate.

    Overrides in the body supply planner-known economics; missing ones
    fall back to LaneProfile-derived defaults.
    """
    from app.db.session import sync_session_factory
    if user.tenant_id is None and config_id is None:
        raise HTTPException(400, "config_id required for system-admin calls")

    with sync_session_factory() as sync_db:
        cfg_id = _resolve_config_id(sync_db, user, config_id)
        effective_tenant_id = user.tenant_id if user.tenant_id is not None else 0

        from app.services.powell.equipment_reposition_trm import EquipmentRepositionTRM
        trm = EquipmentRepositionTRM(sync_db, effective_tenant_id, cfg_id)

        result = trm.evaluate_and_log(
            source_site_id=payload.source_site_id,
            target_site_id=payload.target_site_id,
            equipment_type=payload.equipment_type,
            overrides=_overrides_to_dict(payload.overrides),
        )
        if not result:
            raise HTTPException(422, "No equipment-reposition decision produced")

        return _result_to_schema(result)


@router.post("/network-sweep", response_model=List[EquipmentRepositionResult])
async def network_sweep(
    equipment_type: str = Query("DRY_VAN", description="EquipmentType value"),
    config_id: Optional[int] = Query(None, description="SupplyChainConfig id"),
    overrides: Optional[EquipmentRepositionOverrides] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Greedy surplus→deficit pairing across the tenant's network for one
    equipment_type. Returns one decision per paired (source, target).

    Tenant users sweep their own tenant/config. SYSTEM_ADMIN must pass
    `config_id` explicitly.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None and config_id is None:
        raise HTTPException(400, "config_id required for system-admin calls")

    with sync_session_factory() as sync_db:
        cfg_id = _resolve_config_id(sync_db, user, config_id)
        effective_tenant_id = user.tenant_id if user.tenant_id is not None else 0

        from app.services.powell.equipment_reposition_trm import EquipmentRepositionTRM
        trm = EquipmentRepositionTRM(sync_db, effective_tenant_id, cfg_id)

        results = trm.evaluate_network(
            equipment_type=equipment_type,
            overrides=_overrides_to_dict(overrides),
        )
        return [_result_to_schema(r) for r in results]


@router.post("/status", response_model=EquipmentRepositionResult)
async def get_reposition_status(
    payload: EquipmentRepositionEvaluateBody = Body(...),
    config_id: Optional[int] = Query(None, description="SupplyChainConfig id"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stateless per-pair preview. Pure read — no log emission."""
    from app.db.session import sync_session_factory
    if user.tenant_id is None and config_id is None:
        raise HTTPException(400, "config_id required for system-admin calls")

    with sync_session_factory() as sync_db:
        cfg_id = _resolve_config_id(sync_db, user, config_id)
        effective_tenant_id = user.tenant_id if user.tenant_id is not None else 0

        from app.services.powell.equipment_reposition_trm import EquipmentRepositionTRM
        trm = EquipmentRepositionTRM(sync_db, effective_tenant_id, cfg_id)

        result = trm.evaluate_pair(
            source_site_id=payload.source_site_id,
            target_site_id=payload.target_site_id,
            equipment_type=payload.equipment_type,
            overrides=_overrides_to_dict(payload.overrides),
        )
        if not result:
            raise HTTPException(422, "No equipment-reposition decision produced")

        return _result_to_schema(result)

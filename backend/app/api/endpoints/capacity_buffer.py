"""
Capacity Buffer TRM API — Lane-level capacity buffer sizing (ASSESS phase)

Ninth TMS-native TRM endpoint. Fills out the ASSESS phase alongside
`/exception-management/*`.

Evaluates CapacityTarget rows against forecast volatility, tender
reject rate, capacity-miss history, and demand dynamics, and classifies
each into ACCEPT (buffer nominal) or MODIFY (resize buffer to the
returned `proposed_buffer_loads`). No CapacityTarget mutation —
buffer sizing is observational in v1.

Endpoints:
  POST /capacity-buffer-trm/evaluate/{target_id} — evaluate one + log
  POST /capacity-buffer-trm/evaluate-all          — evaluate every pending target
  GET  /capacity-buffer-trm/status/{target_id}    — stateless preview
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_planning import CapacityTarget
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capacity-buffer-trm", tags=["capacity-buffer-trm"])


class CapacityBufferResult(BaseModel):
    target_id: int
    lane_id: Optional[int] = None
    mode: Optional[str] = None
    target_date: Optional[str] = None
    period_type: str = "WEEK"
    baseline_buffer_loads: int = 0
    proposed_buffer_loads: int = 0
    forecast_loads: int = 0
    committed_loads: int = 0
    recent_tender_reject_rate: float = 0.0
    recent_capacity_miss_count: int = 0
    demand_cv: float = 0.0
    demand_trend: float = 0.0
    action_name: str = "ACCEPT"
    confidence: float = 1.0
    urgency: float = 0.3
    reasoning: str = ""
    decision_method: str = "heuristic"


def _result_to_schema(result: dict) -> CapacityBufferResult:
    return CapacityBufferResult(**{
        k: v for k, v in result.items()
        if k in CapacityBufferResult.model_fields
    })


@router.post("/evaluate/{target_id}", response_model=CapacityBufferResult)
async def evaluate_capacity_buffer(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate buffer sizing for one CapacityTarget and emit the log line.

    No CapacityTarget mutation — buffer sizing is observational.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        target_q = select(CapacityTarget).where(CapacityTarget.id == target_id)
        if user.tenant_id is not None:
            target_q = target_q.where(CapacityTarget.tenant_id == user.tenant_id)
        target = sync_db.execute(target_q).scalar_one_or_none()
        if not target:
            raise HTTPException(404, f"CapacityTarget {target_id} not found")

        from app.services.powell.capacity_buffer_trm import CapacityBufferTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else target.tenant_id
        )
        trm = CapacityBufferTRM(
            sync_db, effective_tenant_id, target.config_id or 0,
        )

        result = trm.evaluate_and_log(target)
        if not result:
            raise HTTPException(422, "No capacity-buffer decision produced")

        return _result_to_schema(result)


@router.post("/evaluate-all", response_model=List[CapacityBufferResult])
async def evaluate_all_targets(
    config_id: int = Query(..., description="SupplyChainConfig id"),
    as_of: Optional[date] = Query(
        None, description="Reference date (defaults to today)"
    ),
    plan_version: str = Query(
        "live", description="CapacityTarget plan_version to evaluate"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every pending CapacityTarget for the tenant's config.

    SYSTEM_ADMIN (tenant_id=None) returns []; tenant users evaluate
    only their own config (checked via CapacityTarget.tenant_id).
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.capacity_buffer_trm import CapacityBufferTRM
        trm = CapacityBufferTRM(sync_db, user.tenant_id, config_id)

        results = trm.evaluate_pending_targets(
            plan_version=plan_version, as_of=as_of
        )
        return [_result_to_schema(r) for r in results]


@router.get("/status/{target_id}", response_model=CapacityBufferResult)
async def get_capacity_buffer_status(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live buffer-sizing preview for any CapacityTarget. Pure read — no log."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        target_q = select(CapacityTarget).where(CapacityTarget.id == target_id)
        if user.tenant_id is not None:
            target_q = target_q.where(CapacityTarget.tenant_id == user.tenant_id)
        target = sync_db.execute(target_q).scalar_one_or_none()
        if not target:
            raise HTTPException(404, f"CapacityTarget {target_id} not found")

        from app.services.powell.capacity_buffer_trm import CapacityBufferTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else target.tenant_id
        )
        trm = CapacityBufferTRM(
            sync_db, effective_tenant_id, target.config_id or 0,
        )

        result = trm.evaluate_target(target)
        if not result:
            raise HTTPException(422, "No capacity-buffer decision produced")

        return _result_to_schema(result)

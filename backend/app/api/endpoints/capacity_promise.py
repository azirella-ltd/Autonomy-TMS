"""
Capacity Promise API — SENSE-phase Load Promotion

Second TMS-native TRM endpoint. Maps to SCP's atp_executor slot but
operates at the Load level rather than per-order ATP consumption.

Endpoints:
  POST /capacity-promise/evaluate/{load_id} — evaluate one PLANNING load
  POST /capacity-promise/evaluate-all       — evaluate all PLANNING loads
  GET  /capacity-promise/status/{load_id}   — current Load.status + last
                                              evaluation (stateless v1 —
                                              returns the live decision)

See docs/internal/plans/CAPACITY_PROMISE_TRM_DESIGN.md for v1 scope and
open decisions deferred to later iterations (dual-write to
core.agent_decisions per PREPARE.3, LoadStatus.REJECTED enum audit,
FreightProcurement gating to READY-only).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import Load
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capacity-promise", tags=["capacity-promise"])


class CapacityPromiseResult(BaseModel):
    load_id: int
    load_number: str
    load_status: str
    lane_id: int = 0
    priority: int = 3
    requested_loads: int = 1
    available_capacity: int = 0
    action_name: str
    composite_score: Optional[float] = None
    confidence: float = 1.0
    urgency: float = 0.5
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate/{load_id}", response_model=CapacityPromiseResult)
async def evaluate_capacity_promise(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate capacity-promise for a specific Load using CapacityPromiseTRM.

    Promotes PLANNING → READY on ACCEPT. DEFER and REJECT leave status
    unchanged (see design note; no LoadStatus.REJECTED value exists yet).
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.capacity_promise_trm import CapacityPromiseTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = CapacityPromiseTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_and_promote(load)
        if not result:
            raise HTTPException(422, "No capacity-promise decision produced")
        sync_db.commit()

        return CapacityPromiseResult(**{
            k: v for k, v in result.items()
            if k in CapacityPromiseResult.model_fields
        })


@router.post("/evaluate-all", response_model=List[CapacityPromiseResult])
async def evaluate_all_pending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every PLANNING load for the current tenant.

    SYSTEM_ADMIN (tenant_id=None) returns an empty list — the TRM is
    tenant-scoped and SYSTEM_ADMIN has no tenant of its own. Switch to
    a tenant-admin user to exercise the full flow.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.capacity_promise_trm import CapacityPromiseTRM
        trm = CapacityPromiseTRM(sync_db, user.tenant_id, 0)

        results = trm.evaluate_pending_loads()
        return [
            CapacityPromiseResult(**{
                k: v for k, v in r.items()
                if k in CapacityPromiseResult.model_fields
            })
            for r in results
        ]


@router.get("/status/{load_id}", response_model=CapacityPromiseResult)
async def get_capacity_promise_status(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the live capacity-promise decision for a load without mutating
    Load.status. Useful for UI previews and debugging.

    v1 is stateless — no per-decision persistence yet (see design note).
    Calling this twice on the same load can produce different answers if
    the underlying capacity rollup has changed between calls.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.capacity_promise_trm import CapacityPromiseTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = CapacityPromiseTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_load(load)
        if not result:
            raise HTTPException(422, "No capacity-promise decision produced")

        return CapacityPromiseResult(**{
            k: v for k, v in result.items()
            if k in CapacityPromiseResult.model_fields
        })

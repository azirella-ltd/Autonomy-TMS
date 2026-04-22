"""
Exception Management TRM API — Shipment Exception Triage (ASSESS phase)

Fourth TMS-native TRM endpoint. Evaluates open ShipmentException rows
and returns a recommended action: ACCEPT (auto-absorb within appointment
buffer), RETENDER (re-tender to alternate carrier), REROUTE (reroute on
remaining window), or ESCALATE (human intervention).

No resolution_status mutation in v1 — state transitions remain with the
existing ExceptionResolution workflow. This TRM is an advisor: decisions
are returned + logged, consumed downstream by Decision Stream (once the
PREPARE.3 dual-write to core.agent_decisions lands Sprint 1 Week 4-5).

Endpoints:
  POST /exception-management/evaluate/{exception_id} — one + log
  POST /exception-management/evaluate-all           — DETECTED+INVESTIGATING
  GET  /exception-management/status/{exception_id}  — preview (no log)
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import ShipmentException
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/exception-management",
    tags=["exception-management"],
)


class ExceptionManagementResult(BaseModel):
    exception_id: int
    shipment_id: int
    exception_type: str
    severity: str
    resolution_status: str
    estimated_delay_hrs: float = 0.0
    delivery_window_hrs: float = 0.0
    action_name: str
    priority_score: float | None = None
    confidence: float = 1.0
    urgency: float = 0.5
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate/{exception_id}", response_model=ExceptionManagementResult)
async def evaluate_exception(
    exception_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate one ShipmentException and log at severity matching the action."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        exc_q = select(ShipmentException).where(ShipmentException.id == exception_id)
        if user.tenant_id is not None:
            exc_q = exc_q.where(ShipmentException.tenant_id == user.tenant_id)
        exc = sync_db.execute(exc_q).scalar_one_or_none()
        if not exc:
            raise HTTPException(404, f"ShipmentException {exception_id} not found")

        from app.services.powell.exception_management_trm import ExceptionManagementTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else exc.tenant_id
        )
        trm = ExceptionManagementTRM(sync_db, effective_tenant_id, 0)

        result = trm.evaluate_and_log(exc)
        if not result:
            raise HTTPException(422, "No exception-management decision produced")

        return ExceptionManagementResult(**{
            k: v for k, v in result.items()
            if k in ExceptionManagementResult.model_fields
        })


@router.post("/evaluate-all", response_model=List[ExceptionManagementResult])
async def evaluate_all_open(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every DETECTED / INVESTIGATING exception for the tenant.

    SYSTEM_ADMIN (tenant_id=None) returns [] — exception triage is
    tenant-scoped by carrier + commodity context.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.exception_management_trm import ExceptionManagementTRM
        trm = ExceptionManagementTRM(sync_db, user.tenant_id, 0)
        results = trm.evaluate_pending_exceptions()
        return [
            ExceptionManagementResult(**{
                k: v for k, v in r.items()
                if k in ExceptionManagementResult.model_fields
            })
            for r in results
        ]


@router.get("/status/{exception_id}", response_model=ExceptionManagementResult)
async def get_exception_status(
    exception_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live decision preview for any ShipmentException — no log, no mutate."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        exc_q = select(ShipmentException).where(ShipmentException.id == exception_id)
        if user.tenant_id is not None:
            exc_q = exc_q.where(ShipmentException.tenant_id == user.tenant_id)
        exc = sync_db.execute(exc_q).scalar_one_or_none()
        if not exc:
            raise HTTPException(404, f"ShipmentException {exception_id} not found")

        from app.services.powell.exception_management_trm import ExceptionManagementTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else exc.tenant_id
        )
        trm = ExceptionManagementTRM(sync_db, effective_tenant_id, 0)

        result = trm.evaluate_exception(exc)
        if not result:
            raise HTTPException(422, "No exception-management decision produced")

        return ExceptionManagementResult(**{
            k: v for k, v in result.items()
            if k in ExceptionManagementResult.model_fields
        })

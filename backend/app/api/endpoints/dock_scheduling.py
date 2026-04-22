"""
Dock Scheduling TRM API — Dock-door appointment triage (PROTECT phase)

Sixth TMS-native TRM endpoint. First PROTECT-phase TRM. Evaluates open
Appointment rows (REQUESTED / CONFIRMED) and returns a recommended
action: ACCEPT / MODIFY / DEFER / ESCALATE.

Endpoints:
  POST /dock-scheduling/evaluate/{appointment_id} — evaluate + log
  POST /dock-scheduling/evaluate-all              — all open appointments
  GET  /dock-scheduling/status/{appointment_id}   — preview, no log
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.tms_entities import Appointment
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dock-scheduling", tags=["dock-scheduling"])


class DockSchedulingResult(BaseModel):
    appointment_id: int
    site_id: int
    appointment_type: str
    status: str
    scheduled_start: Optional[str] = None
    total_doors: int = 0
    available_doors: int = 0
    queue_depth: int = 0
    utilization_pct: float = 0.0
    detention_risk: float = 0.0
    projected_detention_cost: float = 0.0
    action_name: str
    recommendation: Optional[str] = None
    confidence: float = 1.0
    urgency: float = 0.5
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate/{appointment_id}", response_model=DockSchedulingResult)
async def evaluate_dock_scheduling(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate dock-scheduling for a specific appointment + emit the log line.

    No Appointment.status mutation — the existing appointment-workflow
    owns state transitions. This TRM advises the action; consumer UI /
    workflow applies it.
    """
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        q = select(Appointment).where(Appointment.id == appointment_id)
        if user.tenant_id is not None:
            q = q.where(Appointment.tenant_id == user.tenant_id)
        appt = sync_db.execute(q).scalar_one_or_none()
        if not appt:
            raise HTTPException(404, f"Appointment {appointment_id} not found")

        from app.services.powell.dock_scheduling_trm import DockSchedulingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else appt.tenant_id
        )
        trm = DockSchedulingTRM(sync_db, effective_tenant_id, 0)

        result = trm.evaluate_and_log(appt)
        if not result:
            raise HTTPException(422, "No dock-scheduling decision produced")

        return DockSchedulingResult(**{
            k: v for k, v in result.items()
            if k in DockSchedulingResult.model_fields
        })


@router.post("/evaluate-all", response_model=List[DockSchedulingResult])
async def evaluate_all_open(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every REQUESTED / CONFIRMED appointment for the tenant.

    SYSTEM_ADMIN (tenant_id=None) returns [] — dock scheduling is
    tenant-scoped (doors + yard belong to the tenant's facilities).
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.dock_scheduling_trm import DockSchedulingTRM
        trm = DockSchedulingTRM(sync_db, user.tenant_id, 0)
        results = trm.evaluate_pending_appointments()
        return [
            DockSchedulingResult(**{
                k: v for k, v in r.items()
                if k in DockSchedulingResult.model_fields
            })
            for r in results
        ]


@router.get("/status/{appointment_id}", response_model=DockSchedulingResult)
async def get_dock_scheduling_status(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live decision preview for any Appointment — no log."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        q = select(Appointment).where(Appointment.id == appointment_id)
        if user.tenant_id is not None:
            q = q.where(Appointment.tenant_id == user.tenant_id)
        appt = sync_db.execute(q).scalar_one_or_none()
        if not appt:
            raise HTTPException(404, f"Appointment {appointment_id} not found")

        from app.services.powell.dock_scheduling_trm import DockSchedulingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else appt.tenant_id
        )
        trm = DockSchedulingTRM(sync_db, effective_tenant_id, 0)

        result = trm.evaluate_appointment(appt)
        if not result:
            raise HTTPException(422, "No dock-scheduling decision produced")

        return DockSchedulingResult(**{
            k: v for k, v in result.items()
            if k in DockSchedulingResult.model_fields
        })

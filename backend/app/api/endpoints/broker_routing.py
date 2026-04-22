"""
Broker Routing TRM API — Broker vs Asset-Carrier Routing (ACQUIRE phase)

Fifth TMS-native TRM endpoint. Fires on loads where the contract-carrier
waterfall has failed to land an ACCEPTED tender. Returns either an
ACCEPT (with a chosen broker id + rate) or ESCALATE (no broker
available, or best broker's premium over benchmark exceeds the
urgency-adjusted threshold).

Endpoints:
  POST /broker-routing/evaluate/{load_id}   — evaluate + log
  POST /broker-routing/evaluate-all         — all candidate loads
  GET  /broker-routing/status/{load_id}     — stateless preview
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

router = APIRouter(prefix="/broker-routing", tags=["broker-routing"])


class BrokerRoutingResult(BaseModel):
    load_id: int
    load_number: str
    load_status: str
    tender_attempts_exhausted: int = 0
    all_contract_carriers_declined: bool = False
    hours_to_pickup: float = 0.0
    brokers_available: int = 0
    action_name: str
    selected_broker_id: Optional[int] = None
    selected_broker_name: Optional[str] = None
    selected_rate: float = 0.0
    confidence: float = 1.0
    urgency: float = 0.5
    reasoning: str = ""
    decision_method: str = "heuristic"


@router.post("/evaluate/{load_id}", response_model=BrokerRoutingResult)
async def evaluate_broker_routing(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate broker-routing for a specific Load + emit the log line."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.broker_routing_trm import BrokerRoutingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = BrokerRoutingTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_and_log(load)
        if not result:
            raise HTTPException(422, "No broker-routing decision produced")

        return BrokerRoutingResult(**{
            k: v for k, v in result.items()
            if k in BrokerRoutingResult.model_fields
        })


@router.post("/evaluate-all", response_model=List[BrokerRoutingResult])
async def evaluate_all_candidates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluate every candidate load for the current tenant.

    Candidates: loads in PLANNING/READY/TENDERED status with at least
    one tender in history but no ACCEPTED tender.

    SYSTEM_ADMIN (tenant_id=None) returns [] — broker routing is
    tenant-scoped.
    """
    from app.db.session import sync_session_factory

    if user.tenant_id is None:
        return []

    with sync_session_factory() as sync_db:
        from app.services.powell.broker_routing_trm import BrokerRoutingTRM
        trm = BrokerRoutingTRM(sync_db, user.tenant_id, 0)
        results = trm.evaluate_pending_loads()
        return [
            BrokerRoutingResult(**{
                k: v for k, v in r.items()
                if k in BrokerRoutingResult.model_fields
            })
            for r in results
        ]


@router.get("/status/{load_id}", response_model=BrokerRoutingResult)
async def get_broker_routing_status(
    load_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live broker-routing decision preview for any Load regardless of
    tender state. Useful for UI / debugging. Does not log."""
    from app.db.session import sync_session_factory

    with sync_session_factory() as sync_db:
        load_q = select(Load).where(Load.id == load_id)
        if user.tenant_id is not None:
            load_q = load_q.where(Load.tenant_id == user.tenant_id)
        load = sync_db.execute(load_q).scalar_one_or_none()
        if not load:
            raise HTTPException(404, f"Load {load_id} not found")

        from app.services.powell.broker_routing_trm import BrokerRoutingTRM
        effective_tenant_id = (
            user.tenant_id if user.tenant_id is not None else load.tenant_id
        )
        trm = BrokerRoutingTRM(
            sync_db, effective_tenant_id, load.config_id or 0,
        )

        result = trm.evaluate_load(load)
        if not result:
            raise HTTPException(422, "No broker-routing decision produced")

        return BrokerRoutingResult(**{
            k: v for k, v in result.items()
            if k in BrokerRoutingResult.model_fields
        })

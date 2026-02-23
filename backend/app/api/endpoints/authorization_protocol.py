"""
Authorization Protocol API Endpoints

Exposes the Agentic Authorization Protocol (AAP) for the frontend
Authorization Protocol Board.

Delegates to AuthorizationService for production-grade authorization
with auto-resolution, SLA tracking, and audit trail.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.authorization_protocol import (
    AUTHORITY_MAP,
    ActionCategory,
    AgentRole,
)
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/authorization-protocol", tags=["authorization-protocol"])


# Singleton service (in-memory for now; pass db_session for DB-backed)
_service: Optional[AuthorizationService] = None
_seeded: bool = False


def _get_service() -> AuthorizationService:
    """Get or create the authorization service singleton."""
    global _service
    if _service is None:
        _service = AuthorizationService()
    return _service


def _seed_demo_threads() -> None:
    """Seed demo threads for visualization when no real threads exist."""
    global _seeded
    if _seeded:
        return
    _seeded = True

    svc = _get_service()
    if svc.get_stats()["total"] > 0:
        return

    # Thread 1: Active — SO/ATP requesting expedite from Logistics
    svc.submit_request(
        requesting_agent="so_atp",
        target_agent="logistics",
        proposed_action={
            "action_type": "request_expedite",
            "description": "Expedite PO-4821 delivery from 5 days to 2 days for priority customer",
            "po_id": "PO-4821",
            "original_days": 5,
            "target_days": 2,
        },
        net_benefit=0.04,
        benefit_threshold=0.02,
        justification="Priority A customer order at risk of missing SLA. Expedite cost offset by retention value.",
        priority="HIGH",
        site_key="plant_chicago",
    )

    # Thread 2: Auto-resolved — Plant requesting overtime from Finance (high net benefit)
    svc.submit_request(
        requesting_agent="plant",
        target_agent="finance",
        proposed_action={
            "action_type": "overtime_authorization",
            "description": "Authorize 40h weekend overtime to clear production backlog",
            "hours": 40,
            "cost_per_hour": 85,
        },
        net_benefit=0.08,
        benefit_threshold=0.01,
        justification="Production backlog growing 200 units/day. Weekend overtime clears 800 units.",
        priority="MEDIUM",
        site_key="plant_detroit",
    )

    # Thread 3: Auto-denied — Low net benefit cross-DC transfer
    svc.submit_request(
        requesting_agent="inventory",
        target_agent="logistics",
        proposed_action={
            "action_type": "cross_dc_transfer",
            "description": "Transfer 500 units SKU-A from DC-West to DC-East",
            "sku": "SKU-A",
            "from_site": "dc_west",
            "to_site": "dc_east",
            "qty": 500,
        },
        net_benefit=0.01,
        benefit_threshold=0.05,
        justification="DC-East low on SKU-A but demand forecast is moderate.",
        priority="LOW",
        site_key="dc_east",
    )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SubmitRequestBody(BaseModel):
    requesting_agent: str
    target_agent: str
    proposed_action: Dict[str, Any]
    net_benefit: float = 0.0
    benefit_threshold: float = 0.0
    justification: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    priority: str = "MEDIUM"
    site_key: Optional[str] = None
    scenario_id: Optional[int] = None


class RespondBody(BaseModel):
    decision: str  # AUTHORIZE, DENY, COUNTER_OFFER, ESCALATE
    reason: Optional[str] = None
    responding_agent: Optional[str] = None
    counter_proposal: Optional[Dict[str, Any]] = None


class ResolveBody(BaseModel):
    decision: str  # AUTHORIZE or DENY
    reason: Optional[str] = None
    resolved_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/threads")
async def get_threads(
    current_user: User = Depends(get_current_user),
):
    """Get all authorization threads."""
    _seed_demo_threads()
    svc = _get_service()
    threads = svc._all_threads()
    return {
        "threads": [t.to_dict() for t in threads],
        "total": len(threads),
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single thread by ID."""
    _seed_demo_threads()
    svc = _get_service()
    thread = svc.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return thread.to_dict()


@router.post("/threads")
async def submit_request(
    body: SubmitRequestBody,
    current_user: User = Depends(get_current_user),
):
    """Submit a new authorization request."""
    svc = _get_service()
    thread = svc.submit_request(
        requesting_agent=body.requesting_agent,
        target_agent=body.target_agent,
        proposed_action=body.proposed_action,
        net_benefit=body.net_benefit,
        benefit_threshold=body.benefit_threshold,
        justification=body.justification,
        evidence=body.evidence,
        priority=body.priority,
        site_key=body.site_key,
        scenario_id=body.scenario_id,
    )
    return thread.to_dict()


@router.post("/threads/{thread_id}/respond")
async def respond_to_thread(
    thread_id: str,
    body: RespondBody,
    current_user: User = Depends(get_current_user),
):
    """Respond to an authorization thread (authorize, deny, counter-offer, escalate)."""
    svc = _get_service()
    try:
        response = svc.respond(
            thread_id=thread_id,
            decision=body.decision,
            reason=body.reason,
            responding_agent=body.responding_agent,
        )
        return {
            "response_id": response.response_id,
            "decision": response.decision.value,
            "thread_id": thread_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/threads/{thread_id}/resolve")
async def resolve_thread(
    thread_id: str,
    body: ResolveBody,
    current_user: User = Depends(get_current_user),
):
    """Manually resolve a thread (typically by human reviewer)."""
    svc = _get_service()
    try:
        thread = svc.resolve(
            thread_id=thread_id,
            decision=body.decision,
            reason=body.reason,
            resolved_by=body.resolved_by or current_user.email,
        )
        return thread.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/threads/{thread_id}/escalate")
async def escalate_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
):
    """Escalate a thread for human review."""
    svc = _get_service()
    try:
        thread = svc.escalate(thread_id=thread_id)
        return thread.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/authority-map")
async def get_authority_map(
    current_user: User = Depends(get_current_user),
):
    """Get the full authority map for all agent roles."""
    return {
        "authority_map": {
            role.value: {
                action: cat.value
                for action, cat in actions.items()
            }
            for role, actions in AUTHORITY_MAP.items()
        },
    }


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
):
    """Get aggregated authorization statistics."""
    _seed_demo_threads()
    svc = _get_service()
    return svc.get_stats()


@router.post("/sla-check")
async def check_sla_timeouts(
    current_user: User = Depends(get_current_user),
):
    """Check all open threads for SLA expiry and auto-escalate."""
    svc = _get_service()
    escalated = svc.check_sla_timeouts()
    return {
        "escalated_count": len(escalated),
        "escalated_threads": [t.thread_id for t in escalated],
    }

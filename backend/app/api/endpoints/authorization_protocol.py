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


# Singleton service (in-memory; threads submitted live via POST /threads)
_service: Optional[AuthorizationService] = None


def _get_service() -> AuthorizationService:
    """Get or create the authorization service singleton."""
    global _service
    if _service is None:
        _service = AuthorizationService()
    return _service


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

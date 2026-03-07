"""
Decision Stream API Endpoints

LLM-First UI endpoints for the Decision Stream "inbox":
  - GET  /digest  — Digest of pending decisions + alerts
  - POST /action  — Accept/override/reject a decision
  - POST /chat    — Conversational interaction with decision context
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.decision_stream import (
    DecisionDigestResponse,
    DecisionActionRequest,
    DecisionActionResponse,
    DecisionStreamChatRequest,
    DecisionStreamChatResponse,
)
from app.services.decision_stream_service import DecisionStreamService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decision-stream", tags=["Decision Stream"])


def _get_service(db: AsyncSession, user) -> DecisionStreamService:
    """Create a tenant-scoped DecisionStreamService."""
    tenant_id = getattr(user, "tenant_id", None) or 0
    tenant_name = ""
    if hasattr(user, "tenant") and user.tenant:
        tenant_name = getattr(user.tenant, "name", "")
    return DecisionStreamService(db=db, tenant_id=tenant_id, tenant_name=tenant_name)


@router.get("/digest", response_model=DecisionDigestResponse)
async def get_decision_digest(
    config_id: Optional[int] = Query(None, description="Supply chain config ID to scope"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the decision digest: pending decisions, alerts, and LLM synthesis."""
    service = _get_service(db, current_user)
    powell_role = getattr(current_user, "powell_role", None)

    result = await service.get_decision_digest(
        powell_role=powell_role,
        config_id=config_id,
    )
    return result


@router.post("/action", response_model=DecisionActionResponse)
async def act_on_decision(
    request: DecisionActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Accept, override, or reject a pending decision."""
    service = _get_service(db, current_user)

    result = await service.act_on_decision(
        decision_id=request.decision_id,
        decision_type=request.decision_type,
        action=request.action.value,
        override_reason_code=request.override_reason_code,
        override_reason_text=request.override_reason_text,
        override_values=request.override_values,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Action failed"))

    return result


@router.post("/chat", response_model=DecisionStreamChatResponse)
async def chat(
    request: DecisionStreamChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Conversational interaction with decision-context injection."""
    service = _get_service(db, current_user)
    powell_role = getattr(current_user, "powell_role", None)

    result = await service.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        config_id=request.config_id,
        powell_role=powell_role,
    )
    return result

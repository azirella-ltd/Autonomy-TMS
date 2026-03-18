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

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.decision_stream import (
    DecisionDigestResponse,
    DecisionActionRequest,
    DecisionActionResponse,
    DecisionStreamChatRequest,
    DecisionStreamChatResponse,
)
from app.services.decision_stream_service import DecisionStreamService, invalidate_digest_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decision-stream", tags=["Decision Stream"])


def _require_tenant_user(user):
    """Raise 403 if the user has no tenant (e.g. SYSTEM_ADMIN).

    The Decision Stream is a tenant-scoped feature. SYSTEM_ADMIN's scope is
    restricted to tenant and tenant admin management — it has no access to
    agent decisions, provisioning, or any other tenant-scoped feature.
    """
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Decision Stream requires a tenant-scoped user. "
                   "System administrators manage tenants and tenant admins only.",
        )
    return tenant_id


async def _get_service(db: AsyncSession, user) -> DecisionStreamService:
    """Create a tenant-scoped, user-scoped DecisionStreamService."""
    tenant_id = _require_tenant_user(user)
    tenant_name = ""
    if hasattr(user, "tenant") and user.tenant:
        tenant_name = getattr(user.tenant, "name", "")

    return DecisionStreamService(db=db, tenant_id=tenant_id, tenant_name=tenant_name, user=user)


@router.get("/digest", response_model=DecisionDigestResponse)
async def get_decision_digest(
    config_id: Optional[int] = Query(None, description="Supply chain config ID to scope"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the decision digest: pending decisions, alerts, and LLM synthesis."""
    service = await _get_service(db, current_user)
    powell_role = getattr(current_user, "powell_role", None)

    result = await service.get_decision_digest(
        powell_role=powell_role,
        config_id=config_id,
    )
    return result


@router.post("/refresh")
async def refresh_digest(
    config_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Invalidate the digest cache and return a fresh digest.

    Use the refresh button in the UI to force a fresh LLM synthesis.
    """
    service = await _get_service(db, current_user)
    invalidate_digest_cache(tenant_id=service.tenant_id, config_id=config_id)
    powell_role = getattr(current_user, "powell_role", None)
    result = await service.get_decision_digest(
        powell_role=powell_role,
        config_id=config_id,
        force_refresh=True,
    )
    return result


@router.post("/action", response_model=DecisionActionResponse)
async def act_on_decision(
    request: DecisionActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Accept, override, or reject a pending decision."""
    service = await _get_service(db, current_user)

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


@router.get("/ask-why")
async def ask_why(
    decision_id: int = Query(..., description="Decision ID"),
    decision_type: str = Query(..., description="Decision type (atp, po_creation, etc.)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return pre-computed reasoning for a decision. No LLM call — instant response."""
    from app.services.decision_stream_service import DECISION_TYPE_TABLE_MAP
    from sqlalchemy import text

    table = DECISION_TYPE_TABLE_MAP.get(decision_type)
    if not table:
        raise HTTPException(status_code=400, detail=f"Unknown decision type: {decision_type}")

    # Direct DB lookup for the pre-computed reasoning
    result = await db.execute(
        text(f"SELECT decision_reasoning FROM {table} WHERE id = :id"),
        {"id": decision_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")

    reasoning = row[0] if row[0] else "No reasoning was captured for this decision."
    return {"decision_id": decision_id, "decision_type": decision_type, "reasoning": reasoning}


@router.post("/chat", response_model=DecisionStreamChatResponse)
async def chat(
    request: DecisionStreamChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Conversational interaction with decision-context injection."""
    service = await _get_service(db, current_user, config_id=request.config_id)
    powell_role = getattr(current_user, "powell_role", None)

    result = await service.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        config_id=request.config_id,
        powell_role=powell_role,
    )
    return result

"""
AI Assistant API — Tenant-scoped conversational AI endpoint with RAG.

Provides a general-purpose supply chain assistant that uses the tenant's
knowledge base (auto-indexed SC configs + uploaded documents) to answer
questions with citations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.kb_session import get_kb_session
from app.db.session import get_db as get_async_db
from app.services.assistant_service import AssistantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's question")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for multi-turn")
    config_id: Optional[int] = Field(None, description="Scope to specific SC config")


class SourceReference(BaseModel):
    title: str
    relevance: float
    excerpt: str


class AssistantChatResponse(BaseModel):
    response: str
    conversation_id: str
    sources: List[SourceReference] = []
    suggested_followups: List[str] = []


class AssistantActionRequest(BaseModel):
    """Explicit AIIO-governed write action confirmed by the user.

    The two-step pattern: the assistant first describes the action in text
    during /chat, then the user confirms it by calling /action. This
    ensures every write is explicitly authorised by a human — the LLM
    never auto-fires writes.
    """
    action: str = Field(..., description="inspect | override | cancel | replan")
    decision_id: Optional[int] = None
    decision_type: Optional[str] = None
    reason: str = Field(..., min_length=30, description="Justification (≥30 chars, feeds EK)")
    new_values: Optional[dict] = None
    scope: Optional[str] = Field(None, description="For replan: mps|supply_plan|demand_plan|full_cascade")


class AssistantActionResponse(BaseModel):
    success: bool
    message: str
    action: str
    decision_id: Optional[int] = None
    new_status: Optional[str] = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    current_user=Depends(deps.get_current_user),
    app_db: AsyncSession = Depends(get_async_db),
):
    """Chat with the AI supply chain assistant.

    Grounded in the tenant's active SC config. Uses three DB sessions:
      - kb_db:  knowledge base DB (RAG over uploaded documents)
      - app_db: main app DB (structured SC config + live operational state)

    The assistant resolves the tenant's active config automatically from
    app_db and refuses to answer operational questions when no config is
    active.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be associated with a tenant to use the assistant",
        )

    tenant_name = ""
    try:
        tenant = getattr(current_user, "tenant", None)
        if tenant:
            tenant_name = getattr(tenant, "name", "") or ""
    except Exception:
        pass

    try:
        async with get_kb_session() as kb_db:
            service = AssistantService(
                db=kb_db,
                tenant_id=tenant_id,
                tenant_name=tenant_name or f"Tenant {tenant_id}",
                app_db=app_db,
            )
            result = await service.chat(
                message=request.message,
                conversation_id=request.conversation_id,
                config_id=request.config_id,
            )
            # Only the fields declared on AssistantChatResponse are returned;
            # active_config_id / active_config_name / tools_used are additions
            # the schema accepts via pydantic's extra='ignore' default or
            # explicit inclusion below.
            return AssistantChatResponse(**{
                k: result[k] for k in ("response", "conversation_id", "sources", "suggested_followups")
                if k in result
            })

    except Exception as e:
        logger.error(f"Assistant chat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your question. Please try again.",
        )


@router.post("/action", response_model=AssistantActionResponse)
async def assistant_action(
    request: AssistantActionRequest,
    current_user=Depends(deps.get_current_user),
    app_db: AsyncSession = Depends(get_async_db),
):
    """Execute an AIIO-governed write action confirmed by the user.

    Two-step confirmation pattern:
      1. /chat — user asks "override the PO for SKU X"; Azirella replies
         with what it plans to do (decision_id, new values, reason it will
         attribute) and asks for confirmation.
      2. /action — user confirms by hitting this endpoint. The write goes
         through the same DecisionStreamService.act_on_decision path as a
         human click in the Decision Stream UI, with full AIIO audit
         trail attribution to the user.

    Available actions: inspect, override, cancel, replan.
    """
    from app.services.assistant_write_tools import AssistantWriteToolOrchestrator
    from app.services.context_engine_dashboard import resolve_active_config_async

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be associated with a tenant to use the assistant",
        )

    # Resolve active SC config — writes MUST be scoped to it
    config_id, config_name = await resolve_active_config_async(app_db, tenant_id)
    if config_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active supply chain configuration for this tenant. Writes require an active config.",
        )

    orch = AssistantWriteToolOrchestrator(
        db=app_db, config_id=config_id, tenant_id=tenant_id, user=current_user,
    )

    action = request.action.lower()
    try:
        if action in ("inspect", "mark_inspected"):
            if request.decision_id is None or not request.decision_type:
                raise HTTPException(400, "inspect requires decision_id + decision_type")
            result = await orch.mark_decision_inspected(
                decision_id=request.decision_id,
                decision_type=request.decision_type,
                reason=request.reason,
            )
        elif action in ("override", "modify"):
            if request.decision_id is None or not request.decision_type:
                raise HTTPException(400, "override requires decision_id + decision_type")
            result = await orch.override_decision(
                decision_id=request.decision_id,
                decision_type=request.decision_type,
                reason=request.reason,
                new_values=request.new_values or {},
            )
        elif action in ("cancel", "reject"):
            if request.decision_id is None or not request.decision_type:
                raise HTTPException(400, "cancel requires decision_id + decision_type")
            result = await orch.cancel_decision(
                decision_id=request.decision_id,
                decision_type=request.decision_type,
                reason=request.reason,
            )
        elif action == "replan":
            if not request.scope:
                raise HTTPException(400, "replan requires scope")
            result = await orch.trigger_replan(scope=request.scope, reason=request.reason)
        else:
            raise HTTPException(400, f"Unknown action: {request.action}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Assistant action failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Action failed: {e!s}"[:300],
        )

    return AssistantActionResponse(
        success=result.success,
        message=result.message,
        action=action,
        decision_id=result.decision_id,
        new_status=result.new_status,
    )

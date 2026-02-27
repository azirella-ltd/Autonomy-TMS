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

from app.api import deps
from app.db.kb_session import get_kb_session
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


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    current_user=Depends(deps.get_current_user),
):
    """Chat with the AI supply chain assistant.

    Uses the tenant's knowledge base (auto-indexed SC configs + uploaded docs)
    to provide contextual answers with source citations.
    Supports multi-turn conversations via conversation_id.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be associated with a tenant to use the assistant",
        )

    tenant_name = ""
    try:
        # Try to get tenant name for personalization
        tenant = getattr(current_user, "tenant", None)
        if tenant:
            tenant_name = getattr(tenant, "name", "") or ""
    except Exception:
        pass

    try:
        async with get_kb_session() as db:
            service = AssistantService(
                db=db,
                tenant_id=tenant_id,
                tenant_name=tenant_name or f"Tenant {tenant_id}",
            )
            result = await service.chat(
                message=request.message,
                conversation_id=request.conversation_id,
                config_id=request.config_id,
            )
            return AssistantChatResponse(**result)

    except Exception as e:
        logger.error(f"Assistant chat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your question. Please try again.",
        )

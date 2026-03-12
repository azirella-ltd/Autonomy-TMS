"""
Standalone RAG context retrieval for LLM prompt augmentation.

Call `get_rag_context(query, tenant_id=...)` from any async service to
retrieve relevant knowledge base chunks formatted for LLM injection.
``tenant_id`` is REQUIRED to enforce multi-tenant data isolation.

Call `get_decision_context(trm_type, state_description)` to retrieve
similar past decisions as few-shot examples for skill prompts.

Fail-safe: returns empty string / empty list on any error so LLM calls always proceed.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
RAG_DEFAULT_TOP_K = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))
RAG_DEFAULT_MAX_TOKENS = int(os.getenv("RAG_DEFAULT_MAX_TOKENS", "3000"))


async def get_rag_context(
    query: str,
    tenant_id: int,
    top_k: Optional[int] = None,
    max_tokens: Optional[int] = None,
    category: Optional[str] = None,
) -> str:
    """Retrieve RAG context for any LLM prompt.

    Safe to call from anywhere — manages its own DB session.
    Returns empty string if KB is unavailable (never raises).

    **Tenant isolation**: ``tenant_id`` is required.  Callers MUST pass
    the current user's / service's tenant to prevent cross-tenant
    knowledge leakage.

    Args:
        query: Natural language search query.
        tenant_id: KB tenant to search (REQUIRED for tenant isolation).
        top_k: Number of chunks to retrieve (default: RAG_DEFAULT_TOP_K env or 5).
        max_tokens: Approximate word limit for context (default: RAG_DEFAULT_MAX_TOKENS env or 3000).
        category: Optional document category filter.

    Returns:
        Formatted context string, or "" if unavailable.
    """
    if not RAG_ENABLED:
        return ""

    if not query or not query.strip():
        return ""
    top_k = top_k or RAG_DEFAULT_TOP_K
    max_tokens = max_tokens or RAG_DEFAULT_MAX_TOKENS

    try:
        from app.db.kb_session import get_kb_session
        from app.services.knowledge_base_service import KnowledgeBaseService

        async with get_kb_session() as db:
            svc = KnowledgeBaseService(db=db, tenant_id=tenant_id)
            context = await svc.search_for_context(
                query, top_k=top_k, max_tokens=max_tokens
            )
            return context

    except Exception as e:
        logger.warning(f"RAG context retrieval failed (non-fatal): {e}")
        return ""


async def get_decision_context(
    trm_type: str,
    state_description: str,
    tenant_id: int,
    top_k: int = 3,
    min_reward: float = 0.5,
    site_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve similar past decisions for skill prompt injection.

    Safe to call from anywhere — manages its own DB session.
    Returns empty list if decision memory is unavailable (never raises).

    All results are scoped to the given ``tenant_id`` for multi-tenant
    data isolation.

    Args:
        trm_type: TRM type identifier (e.g., "atp_executor").
        state_description: Current state description to search for.
        tenant_id: Tenant to scope the search to.
        top_k: Number of similar decisions to retrieve.
        min_reward: Minimum reward threshold (only return good decisions).
        site_key: Optional site filter for scoping.

    Returns:
        List of similar decision dicts, or [] if unavailable.
    """
    if not RAG_ENABLED:
        return []

    try:
        from app.db.kb_session import get_kb_session
        from app.services.decision_memory_service import DecisionMemoryService

        async with get_kb_session() as db:
            svc = DecisionMemoryService(db=db, tenant_id=tenant_id)
            return await svc.find_similar_decisions(
                trm_type=trm_type,
                state_description=state_description,
                top_k=top_k,
                min_reward=min_reward,
                site_key=site_key,
            )

    except Exception as e:
        logger.warning(f"Decision context retrieval failed (non-fatal): {e}")
        return []

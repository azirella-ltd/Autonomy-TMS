"""
Standalone RAG context retrieval for LLM prompt augmentation.

Call `get_rag_context(query)` from any async service to retrieve
relevant knowledge base chunks formatted for LLM injection.

Fail-safe: returns empty string on any error so LLM calls always proceed.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
RAG_DEFAULT_TOP_K = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))
RAG_DEFAULT_MAX_TOKENS = int(os.getenv("RAG_DEFAULT_MAX_TOKENS", "3000"))
RAG_DEFAULT_CUSTOMER_ID = int(os.getenv("RAG_DEFAULT_CUSTOMER_ID", "1"))


async def get_rag_context(
    query: str,
    tenant_id: Optional[int] = None,
    top_k: Optional[int] = None,
    max_tokens: Optional[int] = None,
    category: Optional[str] = None,
) -> str:
    """Retrieve RAG context for any LLM prompt.

    Safe to call from anywhere — manages its own DB session.
    Returns empty string if KB is unavailable (never raises).

    Args:
        query: Natural language search query.
        tenant_id: KB tenant to search (default: RAG_DEFAULT_CUSTOMER_ID env or 1).
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

    tenant_id = tenant_id or RAG_DEFAULT_CUSTOMER_ID
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

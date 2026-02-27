"""
AI Assistant Service — Tenant-scoped conversational AI with RAG augmentation.

Orchestrates:
  1. Conversation history (in-memory cache with TTL)
  2. RAG retrieval from tenant's knowledge base (SC configs + general docs)
  3. LLM generation via existing LLM suggestion service
  4. Source citation extraction
"""

import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge_base_service import KnowledgeBaseService, ChunkResult

logger = logging.getLogger(__name__)

# In-memory conversation cache (conversation_id -> messages list)
# TTL: 30 minutes. Cleared on eviction.
_CONVERSATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_CACHE_TTL_SECONDS = 1800  # 30 minutes
_MAX_CACHE_SIZE = 500


def _evict_stale():
    """Remove expired conversations from cache."""
    now = time.time()
    keys_to_remove = [
        k for k, v in _CONVERSATION_CACHE.items()
        if now - v.get("last_access", 0) > _CACHE_TTL_SECONDS
    ]
    for k in keys_to_remove:
        _CONVERSATION_CACHE.pop(k, None)

    # Also cap total size
    while len(_CONVERSATION_CACHE) > _MAX_CACHE_SIZE:
        _CONVERSATION_CACHE.popitem(last=False)


class AssistantService:
    """Tenant-scoped AI assistant with RAG-augmented conversation."""

    def __init__(self, db: AsyncSession, tenant_id: int, tenant_name: str = ""):
        self.db = db
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name or f"Tenant {tenant_id}"
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a user message and generate an AI response.

        Args:
            message: User's question/message.
            conversation_id: Existing conversation ID for multi-turn (or None for new).
            config_id: Optional SC config ID to scope RAG search.

        Returns:
            Dict with response, conversation_id, sources, suggested_followups.
        """
        _evict_stale()

        # Get or create conversation
        if not conversation_id or conversation_id not in _CONVERSATION_CACHE:
            conversation_id = str(uuid.uuid4())
            _CONVERSATION_CACHE[conversation_id] = {
                "messages": [],
                "last_access": time.time(),
                "config_id": config_id,
            }

        conv = _CONVERSATION_CACHE[conversation_id]
        conv["last_access"] = time.time()
        if config_id:
            conv["config_id"] = config_id

        # Add user message to history
        conv["messages"].append({"role": "user", "content": message})

        # RAG retrieval
        sc_results, general_results = await self._retrieve_context(message, config_id)
        all_results = sc_results + general_results

        # Build prompt
        prompt = self._build_prompt(message, conv["messages"], all_results)

        # Call LLM
        response_text = await self._call_llm(prompt)

        # Add assistant response to history
        conv["messages"].append({"role": "assistant", "content": response_text})

        # Keep only last 20 messages
        if len(conv["messages"]) > 20:
            conv["messages"] = conv["messages"][-20:]

        # Extract sources
        sources = [
            {
                "title": r.document_title,
                "relevance": round(r.score, 3),
                "excerpt": r.content[:200] + "..." if len(r.content) > 200 else r.content,
            }
            for r in all_results[:5]
            if r.score > 0.3
        ]

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "sources": sources,
            "suggested_followups": self._suggest_followups(message, response_text),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _retrieve_context(
        self, query: str, config_id: Optional[int] = None
    ) -> tuple[List[ChunkResult], List[ChunkResult]]:
        """Retrieve RAG context: SC config docs + general KB docs."""
        sc_results: List[ChunkResult] = []
        general_results: List[ChunkResult] = []

        try:
            # SC config-specific context (limit to 3 to keep prompt size manageable)
            sc_results = await self.kb.search(
                query=query,
                top_k=3,
                category="supply_chain_config",
            )
        except Exception as e:
            logger.warning(f"SC config RAG search failed (non-fatal): {e}")

        try:
            # General knowledge base context
            general_results = await self.kb.search(
                query=query,
                top_k=2,
            )
            # Deduplicate — remove general results that overlap with SC results
            sc_chunk_ids = {r.chunk_id for r in sc_results}
            general_results = [r for r in general_results if r.chunk_id not in sc_chunk_ids]
        except Exception as e:
            logger.warning(f"General RAG search failed (non-fatal): {e}")

        return sc_results, general_results

    def _build_prompt(
        self,
        message: str,
        history: List[Dict[str, str]],
        rag_results: List[ChunkResult],
    ) -> str:
        """Build the LLM prompt with system context, RAG results, and conversation history."""
        parts = []

        # System prompt
        parts.append(
            f"You are an AI supply chain planning assistant for {self.tenant_name}. "
            "You help users understand their supply chain network, analyze inventory positions, "
            "evaluate demand patterns, and provide actionable planning recommendations.\n\n"
            "Guidelines:\n"
            "- Answer based on the provided supply chain context when available\n"
            "- If the context doesn't contain enough information, say so clearly\n"
            "- Be specific — reference site names, product IDs, and quantities when possible\n"
            "- For planning questions, consider lead times, safety stock, and demand variability\n"
            "- Keep answers concise but thorough"
        )

        # RAG context
        if rag_results:
            context_lines = []
            for r in rag_results[:8]:
                context_lines.append(
                    f"[Source: {r.document_title}, relevance: {r.score:.2f}]\n{r.content}"
                )
            parts.append(
                "=== SUPPLY CHAIN CONTEXT ===\n"
                + "\n\n---\n\n".join(context_lines)
                + "\n=== END CONTEXT ==="
            )

        # Conversation history (last 10 turns)
        recent_history = history[-10:]
        if len(recent_history) > 1:  # More than just the current message
            history_lines = []
            for msg in recent_history[:-1]:  # Exclude current message
                role = "User" if msg["role"] == "user" else "Assistant"
                history_lines.append(f"{role}: {msg['content']}")
            parts.append(
                "=== CONVERSATION HISTORY ===\n"
                + "\n".join(history_lines)
                + "\n=== END HISTORY ==="
            )

        # Current question
        parts.append(f"User question: {message}")

        return "\n\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM via the existing suggestion service."""
        try:
            from app.services.llm_suggestion_service import LLMSuggestionService
            llm = LLMSuggestionService(provider="openai-compatible")
            result = await llm.generate_conversation_response(
                prompt=prompt,
                context={"tenant_id": self.tenant_id},
            )
            return result.get("content", "I'm sorry, I couldn't generate a response. Please try again.")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return (
                "I'm currently unable to process your question due to a service issue. "
                "Please ensure the LLM service is running and try again."
            )

    def _suggest_followups(self, question: str, response: str) -> List[str]:
        """Generate suggested follow-up questions based on the conversation."""
        # Simple heuristic-based suggestions
        suggestions = []
        q_lower = question.lower()

        if "inventory" in q_lower or "stock" in q_lower:
            suggestions.append("What are the current safety stock levels?")
            suggestions.append("Which sites have the highest inventory carrying cost?")
        elif "lead time" in q_lower:
            suggestions.append("How does lead time variability affect service levels?")
            suggestions.append("Which lanes have the longest lead times?")
        elif "demand" in q_lower:
            suggestions.append("What is the demand forecast for next period?")
            suggestions.append("How much demand variability exists in the network?")
        elif "site" in q_lower or "network" in q_lower:
            suggestions.append("What is the capacity utilization across sites?")
            suggestions.append("Which transportation lanes are bottlenecks?")
        else:
            suggestions.append("What are the key risks in my supply chain?")
            suggestions.append("How can I reduce the bullwhip effect?")
            suggestions.append("What is the optimal inventory policy?")

        return suggestions[:3]

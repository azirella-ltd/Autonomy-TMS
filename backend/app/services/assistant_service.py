"""
AI Assistant Service — Tenant-scoped conversational AI grounded in the
active SC config.

Grounding sources (in priority order):
  1. Conversation history — what the user just asked about, what Azirella
     already said, ongoing thread context. Always placed at the top of the
     prompt so every downstream source is interpreted against it.
  2. Active SC config (sites, products, lanes, product hierarchy, entity
     counts) via SemanticContextService — injected into every prompt
  3. Live operational state via read-only tools (inventory, forecast,
     supply plan, recent agent decisions, site/product metadata) — the
     LLM decides which tools to call
  4. Knowledge base RAG (documents uploaded by the tenant) — supplements
     for policies, SOPs, reference materials

All three data sources are strictly scoped to the tenant's active SC
config. If no active config exists for the tenant, the assistant refuses
to answer operational questions and says so explicitly.
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
    """Tenant-scoped AI assistant grounded in the active SC config.

    Uses two database sessions:
      - self.kb_db: knowledge base DB (for document RAG)
      - self.app_db: main app DB (for SC config, inventory, forecasts, etc.)

    If `app_db` is not provided, operational grounding is degraded and the
    assistant will only be able to answer from documents (the legacy behaviour).
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        tenant_name: str = "",
        app_db: Optional[AsyncSession] = None,
    ):
        self.kb_db = db
        self.db = db  # legacy alias for backward compat
        self.app_db = app_db
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name or f"Tenant {tenant_id}"
        self.kb = KnowledgeBaseService(db=db, tenant_id=tenant_id)

    async def _resolve_active_config(self) -> tuple[Optional[int], Optional[str]]:
        """Resolve the tenant's active SC config using the app DB.

        Returns (config_id, config_name) or (None, None) if unavailable.
        """
        if self.app_db is None:
            return None, None
        try:
            from app.services.context_engine_dashboard import resolve_active_config_async
            return await resolve_active_config_async(self.app_db, self.tenant_id)
        except Exception as e:
            logger.warning("Assistant: failed to resolve active config: %s", e)
            return None, None

    async def _build_semantic_context(self, config_id: int) -> Dict[str, Any]:
        """Build structured context for the active SC config.

        Returns a dict with summary, entity_counts, sites, products, network,
        product_hierarchy. Returns {} if unavailable or on error.
        """
        if self.app_db is None or not config_id:
            return {}
        try:
            from app.services.semantic_context_service import SemanticContextService
            sem = SemanticContextService(self.app_db)
            return await sem.build_tenant_context(config_id=config_id, scope="planning")
        except Exception as e:
            logger.warning("Assistant: semantic context build failed for config %d: %s", config_id, e)
            return {}

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a user message and generate an AI response.

        Grounding sequence:
          1. Resolve active SC config (from user's tenant — not the passed
             config_id, which is now only a hint for conversation continuity).
          2. Build semantic context from the active config (sites, products,
             network, entity counts).
          3. Attempt tool calls for live operational queries (Phase 2).
          4. Retrieve KB RAG results for document-grounded supplements.
          5. Assemble prompt with all four sources + history.
          6. Call LLM.
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

        # Resolve the tenant's active SC config authoritatively. The
        # `config_id` parameter from the frontend is only a hint for
        # conversation pinning — the real scope comes from the DB.
        active_config_id, active_config_name = await self._resolve_active_config()
        if active_config_id is None and config_id:
            # Fallback: honour the caller's hint when we can't resolve (e.g.,
            # tenant has no is_active=true row for some reason).
            active_config_id = config_id
        conv["config_id"] = active_config_id

        # Add user message to history
        conv["messages"].append({"role": "user", "content": message})

        # Semantic context from the active config (structured supply chain
        # facts: sites, products, network, entity counts). This is the
        # primary grounding layer.
        semantic_ctx = await self._build_semantic_context(active_config_id) if active_config_id else {}

        # Phase 2: attempt tool calls against the active config to pull live
        # operational state. The tool orchestrator decides which tools to
        # invoke based on the question.
        tool_results: List[Dict[str, Any]] = []
        if active_config_id is not None and self.app_db is not None:
            try:
                from app.services.assistant_tools import (
                    AssistantToolOrchestrator,
                )
                orch = AssistantToolOrchestrator(self.app_db, active_config_id, self.tenant_id)
                tool_results = await orch.run_tools_for_question(message)
            except Exception as e:
                logger.warning("Assistant: tool orchestration failed: %s", e)
                tool_results = []

        # KB RAG — documents uploaded by the tenant (policies, SOPs, etc.)
        sc_results, general_results = await self._retrieve_context(message, active_config_id)
        all_results = sc_results + general_results

        # Build prompt with all grounding sources
        prompt = self._build_prompt(
            message=message,
            history=conv["messages"],
            rag_results=all_results,
            semantic_ctx=semantic_ctx,
            tool_results=tool_results,
            active_config_id=active_config_id,
            active_config_name=active_config_name,
        )

        response_text = await self._call_llm(prompt)

        conv["messages"].append({"role": "assistant", "content": response_text})
        if len(conv["messages"]) > 20:
            conv["messages"] = conv["messages"][-20:]

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
            "active_config_id": active_config_id,
            "active_config_name": active_config_name,
            "tools_used": [t.get("tool") for t in tool_results],
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
        semantic_ctx: Optional[Dict[str, Any]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        active_config_id: Optional[int] = None,
        active_config_name: Optional[str] = None,
    ) -> str:
        """Assemble the LLM prompt from all grounding sources.

        Ordering (top to bottom of prompt):
          1. System prompt (role, guidelines, refusal rules)
          2. Conversation history (what the user just asked, what Azirella
             already said — must be read before any other grounding so the
             current question is interpreted in thread context)
          3. Active SC config identity (which tenant + config)
          4. Semantic context (structured supply chain facts)
          5. Live tool results (operational state)
          6. RAG document context
          7. Current user question
        """
        parts: List[str] = []

        # 1. System prompt — explicit grounding instructions
        if active_config_id:
            system = (
                f"You are Azirella, the AI supply chain planning assistant for "
                f"{self.tenant_name}. You are grounded in the tenant's active supply "
                f"chain configuration '{active_config_name}' (config_id={active_config_id}). "
                "Every answer MUST be based on the conversation history, structured facts, "
                "tool results, and documents provided below — not on generic supply chain "
                "knowledge.\n\n"
                "Guidelines:\n"
                "- Read the conversation history first: it tells you what the user is working on\n"
                "- Refer to sites, products, and suppliers by the exact names/IDs from the context\n"
                "- Cite specific numbers when tool results or documents provide them\n"
                "- If the context does not contain the answer, say 'I don't have that information "
                "in the current configuration' — never guess or fabricate\n"
                "- For planning questions, consider lead times, safety stock, and demand variability "
                "from the provided data\n"
                "- Keep answers concise but thorough, and always ground them in this specific config\n"
                "\n"
                "Write actions (AIIO-governed):\n"
                "You CAN propose — but never auto-execute — the following actions on the user's\n"
                "behalf. If the user asks you to change something, describe the proposed action\n"
                "clearly (which decision_id, decision_type, reason, and new values) and ask for\n"
                "explicit confirmation. The user will then confirm via the /assistant/action\n"
                "endpoint, which runs the write through the AIIO governance pipeline.\n"
                "  - inspect a decision (mark INSPECTED after review, no value change)\n"
                "  - override a decision with new values (attribution + EK signal captured)\n"
                "  - cancel a decision (agent recommendation not executed)\n"
                "  - trigger a replan (mps / supply_plan / demand_plan / full_cascade)\n"
                "Every write requires a reason of at least 30 characters. Never write without\n"
                "explicit user confirmation — always describe and ask first."
            )
        else:
            system = (
                f"You are Azirella, the AI supply chain planning assistant for "
                f"{self.tenant_name}. You currently have NO active supply chain configuration "
                "resolved for this tenant. You must only answer general questions about the "
                "platform and MUST refuse any operational question (inventory, forecasts, "
                "supply plans, decisions) by explaining that an active SC config is required."
            )
        parts.append(system)

        # 2. Conversation history — top of grounding so the current question
        # is read in thread context. This must come BEFORE config / semantic /
        # tool / RAG blocks because those are all interpreted against the
        # thread: if the user's prior turn was "let's focus on RDC_NW", the
        # LLM needs to see that framing before reading the tenant structure.
        recent_history = history[-10:]
        if len(recent_history) > 1:  # more than just the current message
            history_lines = []
            for msg in recent_history[:-1]:  # exclude current message
                role = "User" if msg["role"] == "user" else "Assistant"
                history_lines.append(f"{role}: {msg['content']}")
            parts.append(
                "=== CONVERSATION HISTORY ===\n"
                + "\n".join(history_lines)
                + "\n=== END HISTORY ==="
            )

        # 3. Active config identity block (makes grounding explicit in the prompt body)
        if active_config_id:
            parts.append(
                f"=== ACTIVE CONFIGURATION ===\n"
                f"Tenant: {self.tenant_name}\n"
                f"Config: {active_config_name} (id={active_config_id})\n"
                f"All answers must be grounded in this configuration.\n"
                f"=== END CONFIGURATION ==="
            )

        # 4. Semantic context — structured supply chain facts
        if semantic_ctx:
            summary = semantic_ctx.get("summary", "")
            counts = semantic_ctx.get("entity_counts", {})
            sites = semantic_ctx.get("sites", [])[:15]
            products = semantic_ctx.get("products", [])[:20]

            lines = ["=== SUPPLY CHAIN STRUCTURE ==="]
            if counts:
                counts_str = ", ".join(f"{k}={v}" for k, v in counts.items())
                lines.append(f"Entity counts: {counts_str}")
            if sites:
                lines.append(f"Sites ({len(sites)} shown):")
                for s in sites:
                    name = s.get("name", s.get("id"))
                    mt = s.get("master_type") or s.get("sc_site_type") or ""
                    lines.append(f"  - {name} [{mt}]")
            if products:
                lines.append(f"Products ({len(products)} shown):")
                for p in products[:20]:
                    pid = p.get("id") or p.get("product_id")
                    desc = p.get("description") or p.get("name") or ""
                    lines.append(f"  - {pid}: {desc}"[:120])
            if summary:
                lines.append("")
                lines.append(summary)
            lines.append("=== END SUPPLY CHAIN STRUCTURE ===")
            parts.append("\n".join(lines))

        # 4. Live tool results (operational state)
        if tool_results:
            lines = ["=== LIVE OPERATIONAL DATA ==="]
            for t in tool_results:
                tool_name = t.get("tool", "unknown")
                result = t.get("result")
                rendered = t.get("rendered") or (str(result)[:500] if result is not None else "(no data)")
                lines.append(f"[{tool_name}]")
                lines.append(rendered)
                lines.append("")
            lines.append("=== END LIVE OPERATIONAL DATA ===")
            parts.append("\n".join(lines))

        # 5. RAG context from uploaded documents
        if rag_results:
            context_lines = []
            for r in rag_results[:8]:
                context_lines.append(
                    f"[Source: {r.document_title}, relevance: {r.score:.2f}]\n{r.content}"
                )
            parts.append(
                "=== DOCUMENT CONTEXT ===\n"
                + "\n\n---\n\n".join(context_lines)
                + "\n=== END DOCUMENT CONTEXT ==="
            )

        # 7. Current question (last — immediately before the model responds)
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

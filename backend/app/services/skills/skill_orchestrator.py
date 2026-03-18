"""
Skill Orchestrator — Claude Skills as Exception Handler & Meta-Learner.

In the hybrid TRM + Claude Skills architecture (LeCun JEPA mapping):
    - TRMs = Actor (fast policy execution, ~95% of decisions)
    - Claude Skills = Configurator (exception handling, ~5% of decisions)

The orchestrator is invoked ONLY when conformal prediction indicates
low TRM confidence (wide prediction intervals = novel situation).

Three roles:
    1. Exception Handler: Reason about novel situations TRMs haven't seen
    2. Orchestrator: Assess which TRM outputs to trust and when to escalate
    3. Meta-Learner: Analyze TRM failures, generate training examples

Decisions persist to existing powell_*_decisions tables (unchanged schema)
AND to decision_embeddings for RAG retrieval and TRM retraining.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from .base_skill import (
    SKILL_REGISTRY,
    SkillDefinition,
    SkillError,
    SkillResult,
    SkillTier,
    get_skill,
)
from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class SkillOrchestrator:
    """
    Claude Skills exception handler and meta-learner.

    Invoked by SiteAgent only when conformal prediction routing determines
    that TRM confidence is too low for the current situation. Handles ~5%
    of decisions — the novel/edge cases that TRMs haven't learned yet.

    Skills decisions are recorded in the decision embedding store, feeding
    back into TRM training to gradually shift the 95/5 boundary.

    Usage:
        orchestrator = SkillOrchestrator()
        result = await orchestrator.execute(
            trm_type="atp_executor",
            state_features={
                "order_qty": 100, "available": 80,
                "trm_confidence": 0.42,  # Low → escalated to Skills
                "escalation_reason": "trm_confidence=0.42 < threshold=0.60",
            },
            engine_result={"action": "partial_fulfill", "quantity": 80},
        )
    """

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        decision_memory_service=None,
        tenant_id: Optional[int] = None,
    ):
        self._client = claude_client or ClaudeClient(purpose="skills")
        self._decision_memory = decision_memory_service
        self._tenant_id = tenant_id
        # Cache loaded SKILL.md prompts (they don't change at runtime)
        self._prompt_cache: dict[str, str] = {}

    async def _find_similar_decisions(
        self,
        trm_type: str,
        state_features: dict[str, Any],
        top_k: int = 3,
        min_reward: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Retrieve tenant-scoped similar decisions from decision memory.

        If a ``decision_memory_service`` was passed at construction it is
        used directly (backwards-compatible for tests).  Otherwise, a new
        session is opened for the duration of the query.
        """
        if self._decision_memory is not None:
            return await self._decision_memory.find_similar_decisions(
                trm_type=trm_type,
                state_description=json.dumps(state_features, default=str),
                top_k=top_k,
                min_reward=min_reward,
            )
        if self._tenant_id is None:
            return []
        try:
            from app.services.decision_memory_service import DecisionMemoryService
            from app.db.kb_session import get_kb_session

            async with get_kb_session() as kb_db:
                svc = DecisionMemoryService(db=kb_db, tenant_id=self._tenant_id)
                return await svc.find_similar_decisions(
                    trm_type=trm_type,
                    state_description=json.dumps(state_features, default=str),
                    top_k=top_k,
                    min_reward=min_reward,
                )
        except Exception as e:
            logger.debug("Decision memory lookup failed: %s", e)
            return []

    def _load_skill_prompt(self, skill: SkillDefinition) -> str:
        """Load and cache the SKILL.md prompt."""
        if skill.name not in self._prompt_cache:
            self._prompt_cache[skill.name] = skill.load_prompt()
        return self._prompt_cache[skill.name]

    async def execute(
        self,
        trm_type: str,
        state_features: dict[str, Any],
        engine_result: dict[str, Any],
        site_key: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> SkillResult:
        """
        Execute a skill for the given TRM type.

        Args:
            trm_type: TRM type identifier (e.g., "atp_executor")
            state_features: Input state from the engine
            engine_result: Deterministic engine's result
            site_key: Site identifier for RAG scoping
            context: Additional context (tGNN directives, hive signals, etc.)

        Returns:
            SkillResult with the adjusted decision

        Raises:
            SkillError if skill not found (caller should use engine result)
        """
        skill = get_skill(trm_type)
        if skill is None:
            raise SkillError(trm_type, f"No skill registered for TRM type '{trm_type}'")

        # For deterministic-tier skills, return engine result directly
        if skill.tier == SkillTier.DETERMINISTIC:
            return SkillResult(
                decision=engine_result,
                confidence=1.0,
                reasoning="Deterministic engine result (no LLM adjustment needed)",
                skill_name=skill.name,
                model_used="deterministic",
            )

        try:
            return await self._execute_with_llm(
                skill, state_features, engine_result, site_key, context
            )
        except Exception as e:
            logger.warning(
                "Skill %s failed, falling back to engine result: %s",
                skill.name,
                str(e),
            )
            raise SkillError(skill.name, str(e), recoverable=True) from e

    async def _execute_with_llm(
        self,
        skill: SkillDefinition,
        state_features: dict[str, Any],
        engine_result: dict[str, Any],
        site_key: Optional[str],
        context: Optional[dict[str, Any]],
    ) -> SkillResult:
        """Execute skill via Claude/vLLM with RAG context."""
        # 1. Load SKILL.md as system prompt
        base_prompt = self._load_skill_prompt(skill)

        # 2. Retrieve similar past decisions from RAG decision memory (tenant-scoped)
        similar_decisions = await self._find_similar_decisions(
            trm_type=skill.trm_type,
            state_features=state_features,
        )

        # 3. Build system prompt with RAG context + escalation metadata
        system_prompt = self._build_system_prompt(
            base_prompt, similar_decisions, context, state_features
        )

        # 4. Build user message with state + engine result
        user_message = json.dumps(
            {
                "state_features": state_features,
                "engine_result": engine_result,
                "site_key": site_key,
            },
            default=str,
        )

        # 5. Call Claude/vLLM
        model_tier = "haiku" if skill.tier == SkillTier.HAIKU else "sonnet"
        response = await self._client.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            model_tier=model_tier,
            temperature=0.1,
        )

        # 6. Parse response
        try:
            decision_data = self._client.parse_json_response(response["content"])
        except (json.JSONDecodeError, KeyError) as e:
            raise SkillError(
                skill.name, f"Failed to parse skill response as JSON: {e}"
            ) from e

        return SkillResult(
            decision=decision_data.get("decision", engine_result),
            confidence=float(decision_data.get("confidence", 0.7)),
            reasoning=decision_data.get("reasoning", ""),
            skill_name=skill.name,
            model_used=response["model"],
            token_cost=response["tokens_used"],
            requires_human_review=decision_data.get("requires_human_review", False),
            risk_assessment=decision_data.get("risk_assessment"),
            similar_decisions=similar_decisions,
        )

    def _build_system_prompt(
        self,
        base_prompt: str,
        similar_decisions: list[dict],
        context: Optional[dict[str, Any]],
        state_features: Optional[dict[str, Any]] = None,
    ) -> str:
        """Combine SKILL.md, escalation context, RAG examples, and runtime context."""
        parts = [base_prompt]

        # Explain WHY this was escalated to Claude Skills (meta-context)
        parts.append("\n\n## Escalation Context\n")
        parts.append(
            "You are handling an EXCEPTION — the TRM (fast neural network) "
            "was not confident enough to decide autonomously. Your job is to "
            "reason about this novel situation and provide a well-justified "
            "decision. Your decision will be validated against engine constraints "
            "and recorded for TRM retraining."
        )
        if state_features:
            escalation_reason = state_features.get("escalation_reason", "")
            trm_confidence = state_features.get("trm_confidence", "N/A")
            if escalation_reason:
                parts.append(f"Escalation reason: {escalation_reason}")
            if trm_confidence != "N/A":
                parts.append(f"TRM confidence was: {trm_confidence}")

        if similar_decisions:
            parts.append("\n\n## Past Similar Decisions (for reference)\n")
            for i, dec in enumerate(similar_decisions, 1):
                parts.append(f"### Example {i} (reward: {dec.get('reward', 'N/A')})")
                parts.append(f"State: {dec.get('state_summary', 'N/A')}")
                parts.append(f"Decision: {json.dumps(dec.get('decision', {}))}")
                parts.append(f"Outcome: {dec.get('outcome_summary', 'N/A')}")
                parts.append("")

        if context:
            parts.append("\n\n## Runtime Context\n")
            if "tgnn_directive" in context:
                parts.append(
                    f"tGNN Directive: {json.dumps(context['tgnn_directive'])}"
                )
            if "hive_signals" in context:
                parts.append(
                    f"Hive Signals: {json.dumps(context['hive_signals'])}"
                )
            if "urgency_vector" in context:
                parts.append(
                    f"Urgency Vector: {json.dumps(context['urgency_vector'])}"
                )

        return "\n".join(parts)

    async def close(self):
        """Clean up resources."""
        await self._client.close()

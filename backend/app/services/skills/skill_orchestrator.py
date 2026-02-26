"""
Skill Orchestrator — routes decisions through Claude Skills with RAG context.

Follows the same pattern as site_agent.py's TRM calls:
    1. Deterministic engine runs first (unchanged)
    2. Skill adjusts the engine result using heuristic rules + past decisions
    3. Falls back to engine-only result on any failure

Decisions persist to existing powell_*_decisions tables (unchanged schema).
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
    Routes execution decisions through Claude Skills.

    Usage:
        orchestrator = SkillOrchestrator()
        result = await orchestrator.execute(
            trm_type="atp_executor",
            state_features={"order_qty": 100, "available": 80, ...},
            engine_result={"action": "partial_fulfill", "quantity": 80},
        )
    """

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        decision_memory_service=None,
    ):
        self._client = claude_client or ClaudeClient()
        self._decision_memory = decision_memory_service
        # Cache loaded SKILL.md prompts (they don't change at runtime)
        self._prompt_cache: dict[str, str] = {}

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

        # 2. Retrieve similar past decisions from RAG decision memory
        similar_decisions = []
        if self._decision_memory:
            try:
                similar_decisions = await self._decision_memory.find_similar_decisions(
                    trm_type=skill.trm_type,
                    state_description=json.dumps(state_features, default=str),
                    top_k=3,
                    min_reward=0.5,
                )
            except Exception as e:
                logger.debug("RAG decision lookup failed (non-fatal): %s", e)

        # 3. Build system prompt with RAG context
        system_prompt = self._build_system_prompt(
            base_prompt, similar_decisions, context
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
    ) -> str:
        """Combine SKILL.md, RAG examples, and runtime context into system prompt."""
        parts = [base_prompt]

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

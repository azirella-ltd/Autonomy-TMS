"""
Planning Skill Orchestrator — Claude Skills for the tactical planning layer (Layer 2).

Parallel to SkillOrchestrator (execution layer) but invoked by planning services
rather than SiteAgent. Triggered by plan deviation thresholds, new signal arrivals,
human directives, and GNN low-confidence outputs.

Key differences from the execution SkillOrchestrator:
- Routes by ``planning_domain`` ("demand" | "inventory" | "supply" | "rccp"),
  not ``trm_type``.
- Different trigger conditions (see PLANNING_AGENT_IMPLEMENTATION.md Phase 2).
- Persists to domain plan tables + ``decision_embeddings`` with
  ``decision_source='planning_skill'``.
- Returns ``PlanningSkillResult`` (not ``SkillResult``).
- Does NOT write to ``powell_*_decisions`` tables.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .base_skill import SKILL_REGISTRY, SkillDefinition, SkillError, SkillTier
from .claude_client import ClaudeClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routing table: planning domain → registered skill name
# ---------------------------------------------------------------------------

PLANNING_SKILL_ROUTES: dict[str, str] = {
    "demand":    "demand_planning",
    "inventory": "inventory_planning",
    "supply":    "supply_planning",
    "rccp":      "rccp",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlanningSkillResult:
    """Standardised result from a planning skill execution."""

    domain: str                          # "demand" | "inventory" | "supply" | "rccp"
    adjustment: dict                     # The plan modification
    confidence: float
    reasoning: str
    requires_human_review: bool
    pending_de_reconciliation: bool      # True if affects θ* indirectly
    affected_sites: list[str]
    affected_products: list[str]
    model_used: str
    token_cost: int = 0
    similar_decisions: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PlanningSkillOrchestrator:
    """
    Claude Skills exception handler for the tactical planning layer (Layer 2).

    Parallel to SkillOrchestrator (execution layer) but invoked by planning
    services rather than SiteAgent.  Triggered by:
    - Forecast MAPE > 0.15 for 3+ consecutive periods  (demand domain)
    - Plan fill rate shortfall < service_level_target × 0.90  (supply domain)
    - Inventory SS breach rate > 0.05 over 7 days  (inventory domain)
    - RCCP returns ``escalate_to_sop``  (rccp domain)
    - New email signal with planning-relevant type  (all domains)
    - Human directive submitted at Layer 2 routing  (all domains)
    - GNN conformal interval width > 0.40  (domain-specific)

    Writes adjustments to domain plan tables (forecast, supply_plan, inv_policy,
    mps) rather than powell_*_decisions.  All decisions also written to
    ``decision_embeddings`` with ``decision_source='planning_skill'`` for RAG
    retrieval and future TRM training.

    Usage::

        orchestrator = PlanningSkillOrchestrator(tenant_id=3)
        result = await orchestrator.execute(
            planning_domain="supply",
            gnn_output={"plan_qty": 500, "confidence": 0.38},
            trigger_reason="gnn_interval_width=0.45 > 0.40",
            context={"email_signals": [], "directive": None},
            tenant_id=3,
        )
    """

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        decision_memory_service: Any = None,
        tenant_id: Optional[int] = None,
    ) -> None:
        self._client = claude_client or ClaudeClient(purpose="skills")
        self._decision_memory = decision_memory_service
        self._tenant_id = tenant_id
        # Cache loaded SKILL.md prompts (they do not change at runtime)
        self._prompt_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        planning_domain: str,
        gnn_output: dict[str, Any],
        trigger_reason: str,
        context: dict[str, Any],
        tenant_id: int,
    ) -> PlanningSkillResult:
        """
        Execute the planning skill for the given domain.

        Args:
            planning_domain: "demand" | "inventory" | "supply" | "rccp"
            gnn_output: Raw GNN plan output for this domain.
            trigger_reason: Human-readable reason why the skill was invoked.
            context: Email signals, directives, state context, etc.
            tenant_id: Tenant identifier (used for RAG decision memory scoping).

        Returns:
            PlanningSkillResult with the plan adjustment.

        Raises:
            SkillError if the domain is unknown, the SKILL.md is missing, or
            the LLM call fails (caller should treat current plan as-is).
        """
        skill_name = PLANNING_SKILL_ROUTES.get(planning_domain)
        if skill_name is None:
            raise SkillError(
                planning_domain,
                f"Unknown planning domain '{planning_domain}'. "
                f"Valid domains: {sorted(PLANNING_SKILL_ROUTES.keys())}",
                recoverable=False,
            )

        # Resolve to a registered SkillDefinition for metadata (display name,
        # tier) — the skill may or may not be in SKILL_REGISTRY yet (demand /
        # inventory skills are Phase 3+ and not registered until their
        # __init__.py is created).
        skill: Optional[SkillDefinition] = SKILL_REGISTRY.get(skill_name)

        try:
            return await self._execute_with_llm(
                planning_domain=planning_domain,
                skill_name=skill_name,
                skill=skill,
                gnn_output=gnn_output,
                trigger_reason=trigger_reason,
                context=context,
                tenant_id=tenant_id,
            )
        except SkillError:
            raise
        except Exception as exc:
            logger.warning(
                "PlanningSkill %s failed: %s", skill_name, str(exc)
            )
            raise SkillError(skill_name, str(exc), recoverable=True) from exc

    # ------------------------------------------------------------------
    # SKILL.md path resolution
    # ------------------------------------------------------------------

    def _get_skill_md_path(self, planning_domain: str) -> Path:
        """Return the absolute path to the SKILL.md for ``planning_domain``."""
        skill_name = PLANNING_SKILL_ROUTES.get(planning_domain, planning_domain)
        skills_dir = Path(__file__).parent
        return skills_dir / skill_name / "SKILL.md"

    def _load_skill_prompt(self, planning_domain: str) -> str:
        """Load and cache the SKILL.md for the given planning domain.

        Raises:
            SkillError: If the SKILL.md file does not exist for this domain.
                The caller should surface this as a clear error rather than
                silently substituting a default prompt.
        """
        if planning_domain in self._prompt_cache:
            return self._prompt_cache[planning_domain]

        skill_name = PLANNING_SKILL_ROUTES.get(planning_domain, planning_domain)
        md_path = self._get_skill_md_path(planning_domain)

        if not md_path.exists():
            raise SkillError(
                skill_name,
                f"SKILL.md not found for domain: {planning_domain}. "
                f"Add SKILL.md to skills/{skill_name}/ to enable this planning skill.",
                recoverable=False,
            )

        prompt = md_path.read_text(encoding="utf-8")
        self._prompt_cache[planning_domain] = prompt
        return prompt

    # ------------------------------------------------------------------
    # RAG decision memory
    # ------------------------------------------------------------------

    async def _find_similar_decisions(
        self,
        domain: str,
        state_features: dict[str, Any],
        tenant_id: int,
        top_k: int = 3,
        min_reward: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Retrieve similar past planning decisions from tenant-scoped decision memory."""
        # If a pre-wired service was provided (e.g. in tests) use it directly.
        if self._decision_memory is not None:
            return await self._decision_memory.find_similar_decisions(
                trm_type=f"planning_{domain}",
                state_description=json.dumps(state_features, default=str),
                top_k=top_k,
                min_reward=min_reward,
            )

        effective_tenant = tenant_id or self._tenant_id
        if effective_tenant is None:
            return []

        try:
            from app.services.decision_memory_service import DecisionMemoryService
            from app.db.kb_session import get_kb_session

            async with get_kb_session() as kb_db:
                svc = DecisionMemoryService(db=kb_db, tenant_id=effective_tenant)
                return await svc.find_similar_decisions(
                    trm_type=f"planning_{domain}",
                    state_description=json.dumps(state_features, default=str),
                    top_k=top_k,
                    min_reward=min_reward,
                )
        except Exception as exc:
            logger.debug("Planning decision memory lookup failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # LLM execution
    # ------------------------------------------------------------------

    async def _execute_with_llm(
        self,
        planning_domain: str,
        skill_name: str,
        skill: Optional[SkillDefinition],
        gnn_output: dict[str, Any],
        trigger_reason: str,
        context: dict[str, Any],
        tenant_id: int,
    ) -> PlanningSkillResult:
        """Execute the planning skill via Claude/vLLM with RAG context."""
        # 1. Load SKILL.md as system prompt base — raises SkillError if missing
        base_prompt = self._load_skill_prompt(planning_domain)

        # 2. Retrieve similar past planning decisions from RAG decision memory
        similar_decisions = await self._find_similar_decisions(
            domain=planning_domain,
            state_features=gnn_output,
            tenant_id=tenant_id,
        )

        # 3. Build system prompt
        system_prompt = self._build_system_prompt(
            base_prompt=base_prompt,
            planning_domain=planning_domain,
            trigger_reason=trigger_reason,
            similar_decisions=similar_decisions,
            context=context,
        )

        # 4. Build user message
        user_message = json.dumps(
            {
                "planning_domain": planning_domain,
                "gnn_output": gnn_output,
                "trigger_reason": trigger_reason,
                "context": context,
            },
            default=str,
        )

        # 5. Call Claude — all planning skills use Sonnet (judgment required)
        response = await self._client.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            model_tier="sonnet",
            temperature=0.1,
        )

        # 6. Parse JSON response
        try:
            data = self._client.parse_json_response(response["content"])
        except (json.JSONDecodeError, KeyError) as exc:
            raise SkillError(
                skill_name,
                f"Failed to parse planning skill response as JSON: {exc}",
            ) from exc

        decision_data = data.get("decision", {})

        result = PlanningSkillResult(
            domain=planning_domain,
            adjustment=decision_data,
            confidence=float(data.get("confidence", 0.7)),
            reasoning=data.get("reasoning", ""),
            requires_human_review=bool(data.get("requires_human_review", False)),
            # Planning skill adjustments that change policy parameters
            # (service_level_target, safety_stock_multiplier, etc.) affect θ*
            # indirectly and must be reconciled by the weekly DE run.
            pending_de_reconciliation=planning_domain in ("inventory", "rccp"),
            affected_sites=data.get("affected_sites", []),
            affected_products=data.get("affected_products", []),
            model_used=response["model"],
            token_cost=response["tokens_used"],
            similar_decisions=similar_decisions,
        )

        # 7. Persist to decision_embeddings for future RAG retrieval
        await self._record_decision(
            domain=planning_domain,
            gnn_output=gnn_output,
            result=result,
            tenant_id=tenant_id,
        )

        return result

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        base_prompt: str,
        planning_domain: str,
        trigger_reason: str,
        similar_decisions: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        """Combine SKILL.md, trigger context, RAG examples, and runtime context."""
        parts = [base_prompt]

        parts.append("\n\n## Planning Skill Invocation Context\n")
        parts.append(
            "You are handling a PLANNING EXCEPTION at the tactical layer (Layer 2). "
            "The planning GNN output confidence was below threshold or a plan deviation "
            "trigger was reached. Your role is to reason about the current plan state "
            "and recommend an adjustment. Your recommendation will be persisted to the "
            "domain plan table and surfaced in the Decision Stream for human review "
            "where required."
        )
        parts.append(f"Trigger reason: {trigger_reason}")
        parts.append(f"Planning domain: {planning_domain}")

        if similar_decisions:
            parts.append("\n\n## Past Similar Planning Decisions (for reference)\n")
            for i, dec in enumerate(similar_decisions, 1):
                parts.append(
                    f"### Example {i} (reward: {dec.get('reward', 'N/A')})"
                )
                parts.append(f"State: {dec.get('state_summary', 'N/A')}")
                parts.append(f"Decision: {json.dumps(dec.get('decision', {}))}")
                parts.append(f"Outcome: {dec.get('outcome_summary', 'N/A')}")
                parts.append("")

        if context:
            parts.append("\n\n## Runtime Context\n")
            if "email_signals" in context:
                parts.append(
                    f"Email Signals: {json.dumps(context['email_signals'])}"
                )
            if "directive" in context and context["directive"]:
                parts.append(
                    f"Human Directive: {json.dumps(context['directive'])}"
                )
            if "tgnn_directive" in context:
                parts.append(
                    f"tGNN Directive: {json.dumps(context['tgnn_directive'])}"
                )
            if "gnn_interval_width" in context:
                parts.append(
                    f"GNN Conformal Interval Width: {context['gnn_interval_width']}"
                )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _record_decision(
        self,
        domain: str,
        gnn_output: dict[str, Any],
        result: PlanningSkillResult,
        tenant_id: int,
    ) -> None:
        """Persist planning skill decision to decision_embeddings for future RAG.

        Uses ``decision_source='planning_skill'`` to distinguish from execution
        skill decisions (``decision_source='skill_exception'``).
        """
        effective_tenant = tenant_id or self._tenant_id
        if effective_tenant is None:
            return

        try:
            from app.services.decision_memory_service import DecisionMemoryService
            from app.db.kb_session import get_kb_session

            state_description = json.dumps(
                {
                    "domain": domain,
                    "gnn_output": gnn_output,
                    "trigger": "planning_skill",
                },
                default=str,
            )
            decision_dict = {
                "adjustment": result.adjustment,
                "confidence": result.confidence,
                "requires_human_review": result.requires_human_review,
                "pending_de_reconciliation": result.pending_de_reconciliation,
            }

            async with get_kb_session() as kb_db:
                svc = DecisionMemoryService(db=kb_db, tenant_id=effective_tenant)
                await svc.record_decision(
                    trm_type=f"planning_{domain}",
                    state_description=state_description,
                    decision=decision_dict,
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                    decision_source="planning_skill",
                )
        except Exception as exc:
            # Non-fatal — log and continue; the plan adjustment already exists.
            logger.debug(
                "Failed to persist planning skill decision to decision_embeddings: %s",
                exc,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Clean up resources."""
        await self._client.close()

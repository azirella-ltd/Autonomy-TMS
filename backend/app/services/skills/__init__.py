"""
Claude Skills Framework

Hybrid TRM + Claude Skills architecture (LeCun JEPA pattern):
- TRMs = Actor (fast policy execution, ~95% of decisions)
- Claude Skills = Configurator (exception handling, ~5% of decisions)

Architecture:
    Deterministic Engine (always runs first)
        -> TRM adjustments (fast, <10ms, learned exceptions)
        -> Conformal Prediction Router:
            High confidence -> Accept TRM result
            Low confidence -> Escalate to Claude Skills
        -> Skill Orchestrator (routes to Claude or cache)
            -> RAG Decision Memory (find similar past decisions)
            -> Claude API (Haiku for calculation, Sonnet for judgment)
        -> Fallback: engine-only result if skill fails

Controlled by USE_CLAUDE_SKILLS env var (read by SiteAgentConfig).
"""

from .base_skill import SkillDefinition, SkillResult, SkillError, SKILL_REGISTRY
from .skill_orchestrator import SkillOrchestrator
from .claude_client import ClaudeClient

# Import all skill subpackages to trigger registration
from . import (  # noqa: F401
    atp_executor,
    forecast_adjustment,
    inventory_buffer,
    inventory_rebalancing,
    maintenance_scheduling,
    mo_execution,
    order_tracking,
    po_creation,
    quality_disposition,
    subcontracting,
    to_execution,
)

__all__ = [
    "SkillDefinition",
    "SkillResult",
    "SkillError",
    "SkillOrchestrator",
    "ClaudeClient",
    "SKILL_REGISTRY",
]

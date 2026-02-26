"""
Claude Skills Framework

Replaces TRM neural networks with Claude-powered decision skills.
Each skill encodes heuristic rules as SKILL.md prompts, with RAG decision
memory providing few-shot context from past decisions.

Architecture:
    Deterministic Engine (unchanged)
        -> Skill Orchestrator (routes to Claude or cache)
            -> RAG Decision Memory (find similar past decisions)
            -> Claude API (Haiku for calculation, Sonnet for judgment)
        -> Fallback: engine-only result if skill fails

Feature flag: USE_CLAUDE_SKILLS=false (off by default)
"""

from .base_skill import SkillDefinition, SkillResult, SkillError
from .skill_orchestrator import SkillOrchestrator
from .claude_client import ClaudeClient

__all__ = [
    "SkillDefinition",
    "SkillResult",
    "SkillError",
    "SkillOrchestrator",
    "ClaudeClient",
]

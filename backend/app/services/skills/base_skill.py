"""
Base classes for Claude Skills framework.

Each skill is a directory containing a SKILL.md file that encodes
heuristic decision rules as Claude-readable instructions, plus an
__init__.py that registers the skill with metadata.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SkillTier(str, Enum):
    """Model routing tier for cost optimization."""
    DETERMINISTIC = "deterministic"  # No LLM needed, pure engine
    HAIKU = "haiku"                  # Calculation-heavy, low judgment
    SONNET = "sonnet"                # Requires nuanced judgment


class SkillError(Exception):
    """Raised when a skill execution fails. Caller should fall back to engine-only."""

    def __init__(self, skill_name: str, message: str, recoverable: bool = True):
        self.skill_name = skill_name
        self.recoverable = recoverable
        super().__init__(f"Skill '{skill_name}' failed: {message}")


@dataclass
class SkillResult:
    """Standardized result from a skill execution."""

    decision: dict[str, Any]          # The actual decision (action, quantity, etc.)
    confidence: float                  # 0.0-1.0 confidence in this decision
    reasoning: str                     # Human-readable explanation
    skill_name: str                    # Which skill produced this
    model_used: str                    # Which Claude model was used (or "cache")
    token_cost: int = 0               # Total tokens consumed (0 if cache hit)
    requires_human_review: bool = False
    risk_assessment: Optional[dict] = None  # CDT-compatible risk bounds
    similar_decisions: list[dict] = field(default_factory=list)  # RAG matches used

    def to_powell_format(self) -> dict[str, Any]:
        """Convert to format compatible with powell_*_decisions tables."""
        return {
            "trm_adjustment": self.decision,
            "trm_confidence": self.confidence,
            "trm_reasoning": self.reasoning,
            "model_source": f"claude_skill:{self.skill_name}:{self.model_used}",
            "requires_human_review": self.requires_human_review,
            "risk_assessment": self.risk_assessment,
        }


@dataclass
class SkillDefinition:
    """Metadata for a registered skill."""

    name: str                          # e.g., "atp_executor"
    display_name: str                  # e.g., "ATP Executor"
    tier: SkillTier                    # Model routing tier
    trm_type: str                      # Matches TRM type identifier
    description: str                   # One-line description
    skill_md_path: Path = None         # Resolved path to SKILL.md

    def __post_init__(self):
        if self.skill_md_path is None:
            skills_dir = Path(__file__).parent
            self.skill_md_path = skills_dir / self.name / "SKILL.md"

    def load_prompt(self) -> str:
        """Load the SKILL.md content as the system prompt."""
        if not self.skill_md_path.exists():
            raise SkillError(
                self.name,
                f"SKILL.md not found at {self.skill_md_path}",
                recoverable=False,
            )
        return self.skill_md_path.read_text(encoding="utf-8")


# Registry of all available skills
SKILL_REGISTRY: dict[str, SkillDefinition] = {}


def register_skill(skill: SkillDefinition) -> SkillDefinition:
    """Register a skill in the global registry."""
    SKILL_REGISTRY[skill.trm_type] = skill
    return skill


def get_skill(trm_type: str) -> Optional[SkillDefinition]:
    """Look up a skill by TRM type identifier."""
    return SKILL_REGISTRY.get(trm_type)


def list_skills() -> list[SkillDefinition]:
    """List all registered skills."""
    return list(SKILL_REGISTRY.values())

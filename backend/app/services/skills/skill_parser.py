"""
SKILL.md Parser — Extracts structured rules, guardrails, and escalation
triggers from the markdown-formatted SKILL.md files.

Each SKILL.md follows a standard format with these required sections:
- Decision Rules (numbered, with Condition/Action/Urgency/Confidence)
- Guardrails (safety boundaries the TRM must respect)
- Escalation Triggers (when to escalate to Skills or human review)

The parser produces dataclasses that engines, validators, and the
SkillOrchestrator can consume programmatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SkillRule:
    """A single decision rule extracted from SKILL.md."""
    priority: int
    name: str
    condition: str
    action: str
    urgency: str = ""
    confidence: float = 0.8
    requires_human_review: bool = False


@dataclass
class SkillGuardrail:
    """A safety boundary extracted from ## Guardrails section."""
    constraint: str
    severity: str = "hard"  # hard = must never violate, soft = warn


@dataclass
class SkillEscalationTrigger:
    """A condition that triggers escalation from ## Escalation Triggers."""
    condition: str
    description: str = ""


@dataclass
class SkillRuleSet:
    """Complete parsed representation of a SKILL.md file."""
    trm_type: str
    classification: str = ""  # DETERMINISTIC, HEURISTIC, etc.
    rules: list[SkillRule] = field(default_factory=list)
    guardrails: list[SkillGuardrail] = field(default_factory=list)
    escalation_triggers: list[SkillEscalationTrigger] = field(default_factory=list)
    raw_text: str = ""


def parse_skill_md(path: Path, trm_type: str) -> SkillRuleSet:
    """Parse a SKILL.md file into a structured SkillRuleSet.

    Handles the standard section format used across all 11+ SKILL.md files.
    Sections are identified by ``## Heading`` markers.
    """
    if not path.exists():
        return SkillRuleSet(trm_type=trm_type)

    text = path.read_text(encoding="utf-8")
    result = SkillRuleSet(trm_type=trm_type, raw_text=text)

    # Extract classification
    m = re.search(r"##\s*Classification[:\s]*(\S+)", text, re.IGNORECASE)
    if m:
        result.classification = m.group(1).strip()

    # Extract sections by ## heading
    sections = _split_sections(text)

    # Parse decision rules
    rules_text = sections.get("decision rules", "") or sections.get("rules", "")
    if rules_text:
        result.rules = _parse_rules(rules_text)

    # Parse guardrails
    guardrails_text = sections.get("guardrails", "")
    if guardrails_text:
        result.guardrails = _parse_guardrails(guardrails_text)

    # Parse escalation triggers
    esc_text = sections.get("escalation triggers", "")
    if esc_text:
        result.escalation_triggers = _parse_escalation_triggers(esc_text)

    return result


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into sections keyed by lowercase heading."""
    sections: dict[str, str] = {}
    current_heading: Optional[str] = None
    current_lines: list[str] = []

    for line in text.splitlines():
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = heading_match.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines)

    return sections


def _parse_rules(text: str) -> list[SkillRule]:
    """Extract numbered rules from a Decision Rules section."""
    rules = []
    # Match patterns like "1. **CRITICAL**:" or "Rule 1:" or "### Rule 1"
    rule_blocks = re.split(r"\n(?=\d+\.\s|\*\*Rule\s|\###\s*Rule)", text)

    for i, block in enumerate(rule_blocks):
        block = block.strip()
        if not block:
            continue

        # Extract name from bold or heading
        name_match = re.search(r"\*\*(.+?)\*\*", block)
        name = name_match.group(1) if name_match else f"Rule {i + 1}"

        # Extract condition (line containing "if", "when", "condition")
        condition_lines = [
            ln.strip("- ").strip()
            for ln in block.splitlines()
            if any(kw in ln.lower() for kw in ["if ", "when ", "condition", "→", ">=", "<=", ">", "<"])
        ]
        condition = "; ".join(condition_lines) if condition_lines else block[:200]

        # Extract action
        action_lines = [
            ln.strip("- ").strip()
            for ln in block.splitlines()
            if any(kw in ln.lower() for kw in ["action", "→", "then", "set ", "emit", "create", "release", "expedite", "defer"])
        ]
        action = "; ".join(action_lines) if action_lines else ""

        # Extract confidence
        conf_match = re.search(r"confidence[:\s]*(\d+\.?\d*)", block, re.IGNORECASE)
        confidence = float(conf_match.group(1)) if conf_match else 0.8

        # Check for human review
        requires_review = "requires_human_review" in block.lower() or "human review" in block.lower()

        rules.append(SkillRule(
            priority=i + 1,
            name=name,
            condition=condition,
            action=action,
            confidence=confidence,
            requires_human_review=requires_review,
        ))

    return rules


def _parse_guardrails(text: str) -> list[SkillGuardrail]:
    """Extract guardrail constraints from bullet points."""
    guardrails = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            constraint = line.lstrip("-* ").strip()
            severity = "soft" if "warn" in constraint.lower() or "SHOULD" in constraint else "hard"
            guardrails.append(SkillGuardrail(constraint=constraint, severity=severity))
    return guardrails


def _parse_escalation_triggers(text: str) -> list[SkillEscalationTrigger]:
    """Extract escalation triggers from bullet points."""
    triggers = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            raw = line.lstrip("-* ").strip()
            # Split on parenthetical description if present
            parts = re.split(r"\s*\(", raw, maxsplit=1)
            condition = parts[0].strip()
            description = parts[1].rstrip(")").strip() if len(parts) > 1 else ""
            triggers.append(SkillEscalationTrigger(condition=condition, description=description))
    return triggers


def validate_decision(decision: dict, state: dict, rule_set: SkillRuleSet) -> list[str]:
    """Check a TRM decision against the parsed guardrails.

    Returns a list of violation messages (empty if all guardrails pass).
    This is a lightweight string-matching check — not a formal constraint solver.
    """
    violations = []
    for g in rule_set.guardrails:
        constraint_lower = g.constraint.lower()
        # Check quantity bounds
        if "quantity" in constraint_lower and "decision_quantity" in decision:
            qty = decision["decision_quantity"]
            if "min_order_qty" in constraint_lower and "min_order_qty" in state:
                if qty < state["min_order_qty"]:
                    violations.append(f"Guardrail violation: {g.constraint} (qty={qty} < min={state['min_order_qty']})")
            if "max_order_qty" in constraint_lower and "max_order_qty" in state:
                if qty > state["max_order_qty"]:
                    violations.append(f"Guardrail violation: {g.constraint} (qty={qty} > max={state['max_order_qty']})")
    return violations

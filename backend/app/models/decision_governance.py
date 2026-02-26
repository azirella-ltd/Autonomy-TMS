"""
Decision Governance — AIIO Impact-Based Gating and Executive Guardrail Directives

Two models:

1. DecisionGovernancePolicy — Configurable per-customer rules for impact
   thresholds, hold windows, and AIIO mode assignment.  Policies are
   hierarchical: (customer, action_type, category, agent_id) with
   fallback to broader scopes.

2. GuardrailDirective — Executive instructions captured from voice, email,
   chat, or manual entry that adjust governance behavior.  Each directive
   records full provenance: who said it, when, via which channel, the
   extracted objective/context/reason, and the parsed governance parameters.
   Links to IngestedSignal when the directive originates from the signal
   ingestion pipeline (OpenClaw channels).

See docs/AGENT_GUARDRAILS_AND_AIIO.md for full framework documentation.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class DecisionGovernancePolicy(Base):
    """
    Configurable AIIO governance policy per customer.

    Impact scoring produces a 0-100 composite score across five dimensions.
    The score is compared against thresholds to assign AUTOMATE / INFORM / INSPECT.

    Policies match most-specific first:
      (customer, action_type, category, agent_id)
      → (customer, action_type, category)
      → (customer, action_type)
      → (customer)  [catch-all]
      → system default
    """
    __tablename__ = "decision_governance_policies"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    # Scope — which decisions this policy applies to (NULL = all)
    action_type = Column(String(100), nullable=True,
                         comment="NULL matches all action types")
    category = Column(String(50), nullable=True,
                      comment="NULL matches all categories")
    agent_id = Column(String(100), nullable=True,
                      comment="NULL matches all agents")

    # ── Impact thresholds → mode assignment ──
    automate_below = Column(Float, default=20.0,
                            comment="Impact < this → AUTOMATE (execute, no notification)")
    inform_below = Column(Float, default=50.0,
                          comment="Impact < this (and >= automate_below) → INFORM (execute, notify)")
    # Impact >= inform_below → INSPECT (hold for review)

    # ── INSPECT hold configuration ──
    hold_minutes = Column(Integer, default=60,
                          comment="Default review window in minutes")
    max_hold_minutes = Column(Integer, default=1440,
                              comment="Max hold before forced resolution (24h)")
    auto_apply_on_expiry = Column(Boolean, default=True,
                                  comment="True = auto-execute when hold expires; False = expire/cancel")
    escalate_after_minutes = Column(Integer, default=480,
                                    comment="Escalate if no response after this many minutes (8h)")

    # ── Impact dimension weights (should sum ≈ 1.0) ──
    weight_financial = Column(Float, default=0.30,
                              comment="Weight for financial magnitude dimension")
    weight_scope = Column(Float, default=0.20,
                          comment="Weight for blast radius dimension (site/region/network)")
    weight_reversibility = Column(Float, default=0.20,
                                  comment="Weight for how hard to undo")
    weight_confidence = Column(Float, default=0.15,
                               comment="Weight for model confidence (inverted)")
    weight_override_rate = Column(Float, default=0.15,
                                  comment="Weight for historical override rate on this type")

    # ── Policy metadata ──
    name = Column(String(200), nullable=True,
                  comment="Human-readable policy name")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=100,
                      comment="Lower = higher priority; first match wins")

    # ── Audit ──
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_gov_policy_tenant", "tenant_id", "is_active"),
        Index("idx_gov_policy_scope", "tenant_id", "action_type", "category", "agent_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "action_type": self.action_type,
            "category": self.category,
            "agent_id": self.agent_id,
            "automate_below": self.automate_below,
            "inform_below": self.inform_below,
            "hold_minutes": self.hold_minutes,
            "max_hold_minutes": self.max_hold_minutes,
            "auto_apply_on_expiry": self.auto_apply_on_expiry,
            "escalate_after_minutes": self.escalate_after_minutes,
            "weight_financial": self.weight_financial,
            "weight_scope": self.weight_scope,
            "weight_reversibility": self.weight_reversibility,
            "weight_confidence": self.weight_confidence,
            "weight_override_rate": self.weight_override_rate,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "priority": self.priority,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GuardrailDirective(Base):
    """
    Executive guardrail instruction captured from any channel.

    When a senior executive communicates a governance instruction — via voice
    call, email, Slack message, or manual entry in the UI — it is captured
    here with full provenance.  The LLM (or human) extracts structured fields:
    objective, context, reason, and parameter adjustments.

    Examples:
        - VP Supply Chain on a voice call: "Tighten controls on all PO
          decisions above $50K this quarter — we have supplier bankruptcy
          concerns."
        - S&OP Director via email: "Relax the hold window on forecast
          adjustments to 15 minutes — the team is overloaded with reviews."

    Provenance fields:
        source_user_id — Who issued the directive (resolved to users.id)
        source_channel — voice, email, slack, teams, chat, manual
        source_signal_id — Link to IngestedSignal if from signal pipeline
        received_at — When the directive was received/uttered
        raw_content — Original text/transcript of the directive

    Extracted fields:
        objective — What the executive wants to achieve
        context — Why they are making this directive (business context)
        reason — Justification for the change
        extracted_parameters — Parsed governance adjustments as JSON
        affected_scope — Which decisions/categories/agents this applies to

    Lifecycle:
        PENDING → APPLIED (governance policies updated)
        PENDING → REJECTED (reviewer declined)
        PENDING → EXPIRED (past effective_until without action)
    """
    __tablename__ = "guardrail_directives"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    # ── Provenance — who, when, how ──
    source_user_id = Column(Integer, ForeignKey("users.id"), nullable=False,
                            comment="Executive who issued the directive")
    source_channel = Column(String(30), nullable=False,
                            comment="voice | email | slack | teams | chat | manual")
    source_signal_id = Column(Integer, ForeignKey("ingested_signals.id"),
                              nullable=True,
                              comment="Link to IngestedSignal if from signal pipeline")
    received_at = Column(DateTime, nullable=False,
                         comment="When the directive was received/uttered")
    raw_content = Column(Text, nullable=False,
                         comment="Original text, email body, or voice transcript")

    # ── Extracted intent (by LLM or human) ──
    objective = Column(Text, nullable=False,
                       comment="What the executive wants: 'Tighten PO controls this quarter'")
    context = Column(Text, nullable=True,
                     comment="Business context: 'Supplier bankruptcy concerns in frozen segment'")
    reason = Column(Text, nullable=True,
                    comment="Justification: 'Three suppliers in frozen category downgraded by S&P'")
    comment = Column(Text, nullable=True,
                     comment="Additional notes from the executive or reviewer")

    # ── Parsed governance parameters ──
    extracted_parameters = Column(JSON, nullable=True, comment="""\
Parsed governance changes, e.g.:
{
  "action_type": "po_creation",
  "category": "procurement",
  "automate_below": 15.0,
  "inform_below": 35.0,
  "hold_minutes": 120,
  "auto_apply_on_expiry": false
}""")
    affected_scope = Column(JSON, nullable=True, comment="""\
Which decisions are affected, e.g.:
{
  "action_types": ["po_creation", "subcontracting"],
  "categories": ["procurement"],
  "site_keys": ["SITE_DC-Frozen"],
  "product_keys": ["FAMILY_Frozen"]
}""")

    # ── Effective period ──
    effective_from = Column(DateTime, nullable=True,
                            comment="When this directive takes effect (NULL = immediately)")
    effective_until = Column(DateTime, nullable=True,
                             comment="When this directive expires (NULL = indefinite)")

    # ── Lifecycle ──
    status = Column(String(20), default="PENDING", index=True,
                    comment="PENDING | APPLIED | REJECTED | EXPIRED | SUPERSEDED")

    # Review/application tracking
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True,
                         comment="User who reviewed and applied/rejected this directive")
    reviewed_at = Column(DateTime, nullable=True)
    review_comment = Column(Text, nullable=True,
                            comment="Reviewer's comment when applying or rejecting")
    applied_policy_id = Column(Integer,
                               ForeignKey("decision_governance_policies.id"),
                               nullable=True,
                               comment="Policy created/modified as a result of this directive")

    # ── Extraction confidence ──
    extraction_confidence = Column(Float, nullable=True,
                                   comment="LLM confidence in parameter extraction (0-1)")
    extraction_model = Column(String(100), nullable=True,
                              comment="Model used for extraction: qwen3-8b, manual, etc.")

    # ── Audit ──
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    source_user = relationship("User", foreign_keys=[source_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        Index("idx_guardrail_tenant_status", "tenant_id", "status"),
        Index("idx_guardrail_source_user", "source_user_id", "received_at"),
        Index("idx_guardrail_channel", "source_channel", "received_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "source_user_id": self.source_user_id,
            "source_channel": self.source_channel,
            "source_signal_id": self.source_signal_id,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "raw_content": self.raw_content,
            "objective": self.objective,
            "context": self.context,
            "reason": self.reason,
            "comment": self.comment,
            "extracted_parameters": self.extracted_parameters,
            "affected_scope": self.affected_scope,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_until": self.effective_until.isoformat() if self.effective_until else None,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comment": self.review_comment,
            "applied_policy_id": self.applied_policy_id,
            "extraction_confidence": self.extraction_confidence,
            "extraction_model": self.extraction_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

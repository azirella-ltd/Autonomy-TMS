"""
Authorization Models — DB-backed persistence for Agentic Authorization Protocol.

Replaces the in-memory demo with SQLAlchemy models for production use.
Maintains compatibility with the existing authorization_protocol.py data
structures (AuthorizationRequest, AuthorizationThread, etc.) while adding
persistence, SLA tracking, and audit trail.

Architecture reference: AGENTIC_AUTHORIZATION_PROTOCOL.md
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class ThreadStatus(str, enum.Enum):
    """Authorization thread lifecycle status."""
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    COUNTER_OFFERED = "COUNTER_OFFERED"
    DENIED = "DENIED"
    ESCALATED = "ESCALATED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"


class AuthorizationDecision(str, enum.Enum):
    """Possible decisions on an authorization request."""
    AUTHORIZE = "AUTHORIZE"
    DENY = "DENY"
    COUNTER_OFFER = "COUNTER_OFFER"
    ESCALATE = "ESCALATE"
    TIMEOUT = "TIMEOUT"


class AuthorizationPriority(str, enum.Enum):
    """Priority levels for authorization requests."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ROUTINE = "ROUTINE"


class AuthorizationThread(Base):
    """A full authorization negotiation thread.

    Tracks the lifecycle from initial request through resolution,
    including SLA enforcement and escalation.
    """
    __tablename__ = "authorization_thread"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(64), unique=True, nullable=False, index=True)

    # Agents involved
    requesting_agent = Column(String(64), nullable=False, index=True)
    target_agent = Column(String(64), nullable=False, index=True)
    site_key = Column(String(128), nullable=True, index=True)

    # Status and priority
    status = Column(SAEnum(ThreadStatus), nullable=False, default=ThreadStatus.OPEN)
    priority = Column(SAEnum(AuthorizationPriority), nullable=False, default=AuthorizationPriority.MEDIUM)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    sla_expires_at = Column(DateTime, nullable=True)

    # Resolution
    final_decision = Column(SAEnum(AuthorizationDecision), nullable=True)
    resolution_source = Column(String(32), nullable=True)  # "agent", "human", "auto", "timeout"

    # Snapshot data (denormalized for query performance)
    net_benefit = Column(Float, nullable=True)
    benefit_threshold = Column(Float, nullable=True)

    # Audit events (JSON array)
    events = Column(JSON, nullable=True, default=list)

    # Relationships
    requests = relationship("AuthorizationRequestRecord", back_populates="thread", cascade="all, delete-orphan")
    responses = relationship("AuthorizationResponseRecord", back_populates="thread", cascade="all, delete-orphan")

    @property
    def is_resolved(self) -> bool:
        return self.status in (
            ThreadStatus.ACCEPTED, ThreadStatus.DENIED,
            ThreadStatus.EXPIRED, ThreadStatus.RESOLVED,
        )

    @property
    def is_expired(self) -> bool:
        if self.sla_expires_at and not self.is_resolved:
            return datetime.utcnow() > self.sla_expires_at
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "requesting_agent": self.requesting_agent,
            "target_agent": self.target_agent,
            "site_key": self.site_key,
            "status": self.status.value if self.status else None,
            "priority": self.priority.value if self.priority else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "sla_expires_at": self.sla_expires_at.isoformat() if self.sla_expires_at else None,
            "final_decision": self.final_decision.value if self.final_decision else None,
            "resolution_source": self.resolution_source,
            "net_benefit": self.net_benefit,
            "benefit_threshold": self.benefit_threshold,
            "events": self.events or [],
        }


class AuthorizationRequestRecord(Base):
    """An authorization request within a thread.

    Contains the proposed action, balanced scorecard, and justification.
    """
    __tablename__ = "authorization_request_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, nullable=False, index=True)
    thread_id = Column(String(64), ForeignKey("authorization_thread.thread_id"), nullable=False)

    # Action details
    proposed_action = Column(JSON, nullable=False)  # {action_type, description, parameters}
    fallback_action = Column(JSON, nullable=True)   # {description, net_benefit, parameters}
    complementary_actions = Column(JSON, nullable=True)  # [{agent_role, action_type, ...}]

    # Scorecard
    balanced_scorecard = Column(JSON, nullable=True)  # Full BSC as dict
    net_benefit = Column(Float, nullable=True)
    benefit_threshold = Column(Float, nullable=True)

    # Context
    justification = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)
    priority = Column(SAEnum(AuthorizationPriority), nullable=True)

    # Link to planning scenario (optional)
    scenario_id = Column(Integer, ForeignKey("planning_scenario.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    thread = relationship("AuthorizationThread", back_populates="requests")

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "proposed_action": self.proposed_action,
            "balanced_scorecard": self.balanced_scorecard,
            "net_benefit": self.net_benefit,
            "benefit_threshold": self.benefit_threshold,
            "justification": self.justification,
            "priority": self.priority.value if self.priority else None,
            "scenario_id": self.scenario_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuthorizationResponseRecord(Base):
    """A response to an authorization request.

    Records the decision, reasoning, and optional counter-proposal.
    """
    __tablename__ = "authorization_response_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    response_id = Column(String(64), unique=True, nullable=False, index=True)
    thread_id = Column(String(64), ForeignKey("authorization_thread.thread_id"), nullable=False)

    # Decision
    decision = Column(SAEnum(AuthorizationDecision), nullable=False)
    reason = Column(Text, nullable=True)
    responding_agent = Column(String(64), nullable=True)

    # Counter-proposal details (if COUNTER_OFFER)
    counter_proposal = Column(JSON, nullable=True)
    counter_scenario_id = Column(Integer, ForeignKey("planning_scenario.id"), nullable=True)
    revised_scorecard = Column(JSON, nullable=True)

    # Contention details (resource conflicts, capacity issues)
    contention_details = Column(JSON, nullable=True)

    # Escalation target (if ESCALATE)
    escalated_to = Column(String(64), nullable=True)

    responded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    thread = relationship("AuthorizationThread", back_populates="responses")

    def to_dict(self) -> dict:
        return {
            "response_id": self.response_id,
            "thread_id": self.thread_id,
            "decision": self.decision.value if self.decision else None,
            "reason": self.reason,
            "responding_agent": self.responding_agent,
            "counter_proposal": self.counter_proposal,
            "counter_scenario_id": self.counter_scenario_id,
            "contention_details": self.contention_details,
            "escalated_to": self.escalated_to,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }

"""
Chat and A2A Collaboration Database Models
Phase 7 Sprint 2

Terminology (Feb 2026):
- player_id -> scenario_user_id
- Game -> Scenario
- Player -> ScenarioUser (in code), User (in UI)
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.models.base import Base


class MessageType(str, enum.Enum):
    """Chat message types."""
    TEXT = "text"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    ANALYSIS = "analysis"


class SenderType(str, enum.Enum):
    """Message sender types."""
    PARTICIPANT = "participant"  # Human participant (shown as "user" in UI)
    AGENT = "agent"  # AI agent


class ChatMessage(Base):
    """
    Chat message between participants (users) and AI agents.

    Supports real-time collaboration with suggestions, questions, and analysis.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)

    # Sender info
    sender_id = Column(String(100), nullable=False)  # 'participant:1' or 'agent:wholesaler'
    sender_name = Column(String(100), nullable=False)
    sender_type = Column(Enum(SenderType, name="sendertype"), nullable=False)

    # Recipient info (optional for broadcast)
    recipient_id = Column(String(100), nullable=True)

    # Message content
    content = Column(Text, nullable=False)
    type = Column(Enum(MessageType, name="messagetype"), nullable=False, default=MessageType.TEXT)

    # Message metadata (JSON field for extensibility)
    message_metadata = Column(JSON, nullable=True)

    # Message status
    read = Column(Boolean, default=False, nullable=False)
    delivered = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)

    # Relationships
    scenario = relationship("Scenario", back_populates="chat_messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, scenario_id={self.scenario_id}, sender={self.sender_name}, type={self.type})>"


class AgentSuggestion(Base):
    """
    AI agent order suggestion with confidence and rationale.

    Tracks agent recommendations for participant (user) decisions.
    """
    __tablename__ = "agent_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    round = Column(Integer, nullable=False)

    # Agent info
    agent_name = Column(String(100), nullable=False)  # 'retailer', 'wholesaler', etc.

    # Suggestion details
    order_quantity = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    rationale = Column(Text, nullable=False)

    # Context snapshot (JSON)
    context = Column(JSON, nullable=False)

    # Decision tracking
    accepted = Column(Boolean, nullable=True)  # None = pending, True = accepted, False = declined
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)

    # Relationships
    scenario = relationship("Scenario", back_populates="agent_suggestions")
    scenario_user = relationship("ScenarioUser", back_populates="agent_suggestions")

    def __repr__(self):
        return f"<AgentSuggestion(id={self.id}, agent={self.agent_name}, quantity={self.order_quantity}, confidence={self.confidence})>"


class WhatIfAnalysis(Base):
    """
    What-if analysis request and result.

    Allows participants (users) to ask hypothetical questions about order decisions.
    """
    __tablename__ = "what_if_analyses"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    round = Column(Integer, nullable=False)

    # Request
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id"), nullable=False)
    question = Column(Text, nullable=False)
    scenario_data = Column(JSON, nullable=False)  # Hypothetical order quantities (renamed from 'scenario' to avoid conflict)

    # Result
    result = Column(JSON, nullable=True)  # Predicted outcomes
    agent_analysis = Column(Text, nullable=True)  # Agent commentary

    # Status
    completed = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    scenario = relationship("Scenario", back_populates="what_if_analyses")
    scenario_user = relationship("ScenarioUser", back_populates="what_if_analyses")

    def __repr__(self):
        return f"<WhatIfAnalysis(id={self.id}, scenario_id={self.scenario_id}, question={self.question[:50]})>"

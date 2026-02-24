"""
Chat and A2A Collaboration Schemas
Phase 7 Sprint 2
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    """Chat message types."""
    TEXT = "text"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    ANALYSIS = "analysis"


class SenderType(str, Enum):
    """Message sender types."""
    PLAYER = "scenario_user"
    AGENT = "agent"


# ===== Request Schemas =====


class ChatMessageCreate(BaseModel):
    """Create a new chat message."""
    sender_id: str = Field(..., description="Sender ID (scenario_user:1 or agent:wholesaler)")
    sender_name: str = Field(..., description="Display name of sender")
    sender_type: SenderType = Field(..., description="ScenarioUser or agent")
    recipient_id: Optional[str] = Field(None, description="Recipient ID (optional for broadcast)")
    content: str = Field(..., min_length=1, max_length=2000, description="Message content")
    type: MessageType = Field(MessageType.TEXT, description="Message type")
    message_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ChatMessageUpdate(BaseModel):
    """Update a chat message (mark as read)."""
    read: Optional[bool] = None


class AgentSuggestionRequest(BaseModel):
    """Request an agent suggestion."""
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for suggestion")


class AgentSuggestionDecision(BaseModel):
    """Accept or decline a suggestion."""
    scenario_user_id: int = Field(..., description="ScenarioUser making the decision")


class WhatIfAnalysisRequest(BaseModel):
    """Request what-if analysis."""
    scenario_user_id: int = Field(..., description="ScenarioUser requesting analysis")
    question: str = Field(..., min_length=1, max_length=500, description="Hypothetical question")
    scenario: Dict[str, Any] = Field(..., description="Hypothetical scenario (order quantities, etc.)")


# ===== Response Schemas =====


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    id: int
    scenario_id: int
    sender_id: str
    sender_name: str
    sender_type: SenderType
    recipient_id: Optional[str]
    content: str
    type: MessageType
    message_metadata: Optional[Dict[str, Any]]
    read: bool
    delivered: bool
    created_at: datetime
    read_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChatMessagesResponse(BaseModel):
    """List of chat messages."""
    messages: List[ChatMessageResponse]
    total: int
    has_more: bool


class AgentSuggestionContext(BaseModel):
    """Context snapshot for suggestion."""
    current_inventory: int = 0
    current_backlog: int = 0
    recent_demand: List[int] = []
    forecast_demand: float = 0.0


class AgentSuggestionResponse(BaseModel):
    """Agent suggestion response."""
    id: int
    scenario_id: int
    round: int
    agent_name: str
    order_quantity: int
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level (0.0 to 1.0)")
    rationale: str
    context: Dict[str, Any]  # Changed to Dict to allow extended context
    accepted: Optional[bool]
    scenario_user_id: Optional[int]
    created_at: datetime
    decided_at: Optional[datetime]

    class Config:
        from_attributes = True


class AgentSuggestionsResponse(BaseModel):
    """List of agent suggestions."""
    suggestions: List[AgentSuggestionResponse]
    total: int


class WhatIfAnalysisResponse(BaseModel):
    """What-if analysis response."""
    id: int
    scenario_id: int
    round: int
    scenario_user_id: int
    question: str
    scenario: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    agent_analysis: Optional[str]
    completed: bool
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ===== WebSocket Event Schemas =====


class TypingIndicatorEvent(BaseModel):
    """Typing indicator WebSocket event."""
    scenario_id: int
    sender_id: str
    is_typing: bool


class MessageDeliveredEvent(BaseModel):
    """Message delivered WebSocket event."""
    message_id: int
    delivered_at: datetime


class MessageReadEvent(BaseModel):
    """Message read WebSocket event."""
    message_id: int
    read_at: datetime


class SuggestionReadyEvent(BaseModel):
    """Suggestion ready WebSocket event."""
    suggestion_id: int
    scenario_id: int


class AnalysisCompleteEvent(BaseModel):
    """What-if analysis complete WebSocket event."""
    analysis_id: int
    scenario_id: int

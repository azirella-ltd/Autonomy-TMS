"""
Conversation API Endpoints
Phase 7 Sprint 4 - Multi-Turn Conversations

Handles multi-turn AI chat interactions with context retention.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.conversation_service import get_conversation_service

router = APIRouter(prefix="/conversation", tags=["conversation"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class ConversationMessageRequest(BaseModel):
    """Request to send a conversation message."""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    parent_message_id: Optional[int] = Field(None, description="Parent message ID for threading")


class ConversationMessageResponse(BaseModel):
    """Response containing message data."""
    id: int
    scenario_id: int
    player_id: int
    parent_message_id: Optional[int]
    role: str
    content: str
    context: dict
    created_at: str

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """Response containing user message and AI response."""
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
    conversation_id: int


class ConversationHistoryResponse(BaseModel):
    """Response containing conversation history."""
    messages: List[ConversationMessageResponse]
    total_count: int
    scenario_id: int
    player_id: int


class ConversationSummaryResponse(BaseModel):
    """Response containing conversation summary stats."""
    total_messages: int
    user_messages: int
    assistant_messages: int
    conversation_started: Optional[str]
    last_message: Optional[str]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/scenarios/{scenario_id}/message", response_model=ConversationResponse)
async def send_conversation_message(
    scenario_id: int,
    request: ConversationMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a message in conversation and get AI response.

    This endpoint enables multi-turn conversations with context retention.
    The AI assistant remembers previous messages and provides contextual responses.

    **Features:**
    - Context-aware responses based on conversation history
    - Follow-up question support
    - Suggested actions (e.g., order quantity recommendations)
    - Fallback to heuristic responses if LLM unavailable

    **Example Flow:**
    ```
    User: "What should I order?"
    AI: "I recommend 50 units based on current demand."

    User: "What if demand drops?"
    AI: "If demand drops, you'd have 25 units excess inventory..."
    ```
    """
    try:
        # Get conversation service
        conversation_service = get_conversation_service(db)

        # TODO: Verify user has access to this game
        # For now, we'll use a simple player lookup
        # In production, add proper authorization checks

        # Send message and get AI response
        result = await conversation_service.send_message(
            game_id=scenario_id,
            player_id=current_user.id,  # TODO: Map user to player properly
            message=request.message,
            parent_message_id=request.parent_message_id,
        )

        return ConversationResponse(
            user_message=ConversationMessageResponse(**result["user_message"]),
            assistant_message=ConversationMessageResponse(**result["assistant_message"]),
            conversation_id=result["conversation_id"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    scenario_id: int,
    limit: int = 50,
    include_context: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get conversation history for the current player in a game.

    Returns the most recent messages in reverse chronological order.
    Optionally includes full context snapshots for each message.

    **Parameters:**
    - `limit`: Maximum number of messages to return (default: 50, max: 200)
    - `include_context`: Whether to include full game state context for each message

    **Use Cases:**
    - Display chat history when player rejoins game
    - Analyze conversation patterns
    - Export conversation for review
    """
    if limit > 200:
        limit = 200

    try:
        conversation_service = get_conversation_service(db)

        # Get conversation history
        messages = await conversation_service.get_conversation_history(
            game_id=scenario_id,
            player_id=current_user.id,  # TODO: Map user to player properly
            limit=limit,
            include_context=include_context,
        )

        return ConversationHistoryResponse(
            messages=[ConversationMessageResponse(**msg) for msg in messages],
            total_count=len(messages),
            scenario_id=scenario_id,
            player_id=current_user.id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation history: {str(e)}"
        )


@router.delete("/scenarios/{scenario_id}/clear")
async def clear_conversation(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Clear conversation history for the current player.

    This removes all conversation messages but preserves system metadata.
    Useful for:
    - Starting fresh in a new round
    - Removing old/irrelevant conversation
    - Testing and development

    **Note:** This action cannot be undone.
    """
    try:
        conversation_service = get_conversation_service(db)

        success = await conversation_service.clear_conversation(
            game_id=scenario_id,
            player_id=current_user.id,  # TODO: Map user to player properly
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear conversation"
            )

        return {"status": "success", "message": "Conversation cleared"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear conversation: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/summary", response_model=ConversationSummaryResponse)
async def get_conversation_summary(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get conversation summary with key metrics.

    Returns high-level statistics about the conversation:
    - Total message count
    - User vs AI message breakdown
    - Conversation start and last activity timestamps

    **Use Cases:**
    - Dashboard widgets showing engagement
    - Activity tracking
    - Conversation analytics
    """
    try:
        conversation_service = get_conversation_service(db)

        summary = await conversation_service.get_conversation_summary(
            game_id=scenario_id,
            player_id=current_user.id,  # TODO: Map user to player properly
        )

        return ConversationSummaryResponse(**summary)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation summary: {str(e)}"
        )

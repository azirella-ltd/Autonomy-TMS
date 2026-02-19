"""
Chat and A2A Collaboration API Endpoints
Phase 7 Sprint 2
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.chat_service import ChatService
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatMessagesResponse,
    AgentSuggestionRequest,
    AgentSuggestionResponse,
    AgentSuggestionsResponse,
    AgentSuggestionDecision,
    WhatIfAnalysisRequest,
    WhatIfAnalysisResponse,
)
from app.api.endpoints.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_chat_service(db: Session = Depends(get_db)) -> ChatService:
    """Dependency for chat service."""
    return ChatService(db)


# ===== Chat Messages =====


@router.get(
    "/games/{game_id}/chat/messages",
    response_model=ChatMessagesResponse,
    summary="Get chat messages",
    description="Retrieve chat messages for a game with optional filtering",
)
async def get_chat_messages(
    game_id: int,
    since: Optional[datetime] = Query(None, description="Only return messages after this timestamp"),
    limit: int = Query(100, ge=1, le=200, description="Maximum number of messages"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Get chat messages for a game.

    **Query Parameters:**
    - `since`: ISO 8601 timestamp - only return messages after this time
    - `limit`: Maximum number of messages (1-200, default 100)
    - `offset`: Pagination offset (default 0)

    **Returns:**
    - List of chat messages in chronological order
    - Total count of messages
    - `has_more` flag for pagination
    """
    try:
        messages, total, has_more = await chat_service.get_messages(
            game_id=game_id,
            since=since,
            limit=limit,
            offset=offset,
        )

        return ChatMessagesResponse(
            messages=[ChatMessageResponse.from_orm(msg) for msg in messages],
            total=total,
            has_more=has_more,
        )

    except Exception as e:
        logger.error(f"Error getting chat messages for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve chat messages: {str(e)}",
        )


@router.post(
    "/games/{game_id}/chat/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send chat message",
    description="Send a new chat message in a game",
)
async def send_chat_message(
    game_id: int,
    message_data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Send a new chat message.

    **Request Body:**
    - `sender_id`: Sender ID (e.g., "player:1" or "agent:wholesaler")
    - `sender_name`: Display name
    - `sender_type`: "player" or "agent"
    - `recipient_id`: Optional recipient ID (omit for broadcast)
    - `content`: Message content (1-2000 characters)
    - `type`: Message type ("text", "suggestion", "question", "analysis")
    - `metadata`: Optional JSON metadata

    **Returns:**
    - Created message with ID and timestamp

    **WebSocket Broadcast:**
    - Emits `chat:new_message` event to all game participants
    """
    try:
        message = await chat_service.create_message(
            game_id=game_id,
            message_data=message_data,
        )

        # Broadcast to game via WebSocket
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:new_message",
                "data": ChatMessageResponse.from_orm(message).dict(),
            },
        )

        return ChatMessageResponse.from_orm(message)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending chat message in game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(e)}",
        )


@router.put(
    "/games/{game_id}/chat/messages/read",
    summary="Mark messages as read",
    description="Mark multiple messages as read",
)
async def mark_messages_read(
    game_id: int,
    message_ids: List[int],
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Mark messages as read.

    **Request Body:**
    - `message_ids`: List of message IDs to mark as read

    **Returns:**
    - `count`: Number of messages marked as read

    **WebSocket Broadcast:**
    - Emits `chat:messages_read` event for each message
    """
    try:
        count = await chat_service.mark_messages_read(
            game_id=game_id,
            message_ids=message_ids,
        )

        # Broadcast read receipts
        for message_id in message_ids:
            await manager.broadcast_to_game(
                game_id,
                {
                    "type": "chat:message_read",
                    "data": {
                        "message_id": message_id,
                        "read_at": datetime.utcnow().isoformat(),
                    },
                },
            )

        return {"count": count}

    except Exception as e:
        logger.error(f"Error marking messages as read in game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark messages as read: {str(e)}",
        )


# ===== Agent Suggestions =====


@router.get(
    "/games/{game_id}/chat/suggestions",
    response_model=AgentSuggestionsResponse,
    summary="Get agent suggestions",
    description="Retrieve agent suggestions for a game",
)
async def get_agent_suggestions(
    game_id: int,
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    pending_only: bool = Query(False, description="Only show pending suggestions"),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Get agent suggestions for a game.

    **Query Parameters:**
    - `agent_name`: Filter by specific agent (retailer, wholesaler, etc.)
    - `pending_only`: Only return suggestions that haven't been accepted/declined

    **Returns:**
    - List of agent suggestions with confidence, rationale, and context
    """
    try:
        suggestions = await chat_service.get_suggestions(
            game_id=game_id,
            agent_name=agent_name,
            pending_only=pending_only,
        )

        return AgentSuggestionsResponse(
            suggestions=[AgentSuggestionResponse.from_orm(s) for s in suggestions],
            total=len(suggestions),
        )

    except Exception as e:
        logger.error(f"Error getting suggestions for game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve suggestions: {str(e)}",
        )


@router.post(
    "/games/{game_id}/chat/request-suggestion",
    response_model=AgentSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request agent suggestion",
    description="Request an order recommendation from an AI agent",
)
async def request_agent_suggestion(
    game_id: int,
    agent_name: str = Query(..., description="Agent to request suggestion from"),
    request_data: Optional[AgentSuggestionRequest] = None,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Request an agent suggestion.

    **Query Parameters:**
    - `agent_name`: Agent to request from (retailer, wholesaler, distributor, factory)

    **Request Body:**
    - `context`: Optional additional context for the suggestion

    **Returns:**
    - Agent suggestion with order quantity, confidence level (0.0-1.0), rationale, and context

    **WebSocket Broadcast:**
    - Emits `chat:agent_typing` during processing
    - Emits `chat:suggestion_ready` when complete

    **Processing:**
    1. Retrieves current game state
    2. Calls LLM agent for analysis
    3. Generates order recommendation with confidence
    4. Returns suggestion with rationale
    """
    try:
        # Emit typing indicator
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:agent_typing",
                "data": {
                    "agent_id": f"agent:{agent_name}",
                    "is_typing": True,
                },
            },
        )

        suggestion = await chat_service.request_suggestion(
            game_id=game_id,
            agent_name=agent_name,
            request_data=request_data,
        )

        # Stop typing indicator
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:agent_typing",
                "data": {
                    "agent_id": f"agent:{agent_name}",
                    "is_typing": False,
                },
            },
        )

        # Emit suggestion ready
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:suggestion_ready",
                "data": AgentSuggestionResponse.from_orm(suggestion).dict(),
            },
        )

        return AgentSuggestionResponse.from_orm(suggestion)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error requesting suggestion in game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestion: {str(e)}",
        )


@router.put(
    "/games/{game_id}/chat/suggestions/{suggestion_id}/accept",
    response_model=AgentSuggestionResponse,
    summary="Accept agent suggestion",
    description="Accept an agent's order recommendation",
)
async def accept_agent_suggestion(
    game_id: int,
    suggestion_id: int,
    decision: AgentSuggestionDecision,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Accept an agent suggestion.

    **Path Parameters:**
    - `suggestion_id`: ID of the suggestion to accept

    **Request Body:**
    - `player_id`: ID of the player accepting the suggestion

    **Returns:**
    - Updated suggestion with `accepted: true` and timestamp

    **Next Steps:**
    - Frontend should pre-fill order form with suggested quantity
    """
    try:
        suggestion = await chat_service.accept_suggestion(
            game_id=game_id,
            suggestion_id=suggestion_id,
            player_id=decision.player_id,
        )

        # Broadcast decision
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:suggestion_accepted",
                "data": AgentSuggestionResponse.from_orm(suggestion).dict(),
            },
        )

        return AgentSuggestionResponse.from_orm(suggestion)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error accepting suggestion {suggestion_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept suggestion: {str(e)}",
        )


@router.put(
    "/games/{game_id}/chat/suggestions/{suggestion_id}/decline",
    response_model=AgentSuggestionResponse,
    summary="Decline agent suggestion",
    description="Decline an agent's order recommendation",
)
async def decline_agent_suggestion(
    game_id: int,
    suggestion_id: int,
    decision: AgentSuggestionDecision,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Decline an agent suggestion.

    **Path Parameters:**
    - `suggestion_id`: ID of the suggestion to decline

    **Request Body:**
    - `player_id`: ID of the player declining the suggestion

    **Returns:**
    - Updated suggestion with `accepted: false` and timestamp
    """
    try:
        suggestion = await chat_service.decline_suggestion(
            game_id=game_id,
            suggestion_id=suggestion_id,
            player_id=decision.player_id,
        )

        # Broadcast decision
        await manager.broadcast_to_game(
            game_id,
            {
                "type": "chat:suggestion_declined",
                "data": AgentSuggestionResponse.from_orm(suggestion).dict(),
            },
        )

        return AgentSuggestionResponse.from_orm(suggestion)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error declining suggestion {suggestion_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to decline suggestion: {str(e)}",
        )


# ===== What-If Analysis =====


@router.post(
    "/games/{game_id}/chat/what-if",
    response_model=WhatIfAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run what-if analysis",
    description="Run a hypothetical scenario analysis",
)
async def run_what_if_analysis(
    game_id: int,
    analysis_data: WhatIfAnalysisRequest,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Run a what-if analysis.

    **Request Body:**
    - `player_id`: Player requesting the analysis
    - `question`: Hypothetical question (e.g., "What if I order 50 units?")
    - `scenario`: Scenario parameters (order quantities, etc.)

    **Returns:**
    - Analysis request with ID
    - Result populated when analysis completes (may be async)

    **WebSocket Broadcast:**
    - Emits `chat:analysis_complete` when processing finishes

    **Example Questions:**
    - "What if I order 50 units instead of 40?"
    - "What happens if demand increases by 20%?"
    - "How would reducing my order affect inventory next week?"
    """
    try:
        analysis = await chat_service.create_what_if_analysis(
            game_id=game_id,
            analysis_data=analysis_data,
        )

        # Trigger async processing
        from app.services.what_if_service import get_what_if_service
        import asyncio

        what_if_service = get_what_if_service(chat_service.db)

        # Run in background
        asyncio.create_task(what_if_service.process_analysis(analysis.id))

        logger.info(f"Started async processing for what-if analysis {analysis.id}")

        return WhatIfAnalysisResponse.from_orm(analysis)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating what-if analysis in game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create analysis: {str(e)}",
        )


@router.get(
    "/games/{game_id}/chat/what-if/{analysis_id}",
    response_model=WhatIfAnalysisResponse,
    summary="Get what-if analysis",
    description="Retrieve a what-if analysis by ID",
)
async def get_what_if_analysis(
    game_id: int,
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Get a what-if analysis.

    **Returns:**
    - Analysis with result if completed
    - `completed: false` if still processing
    """
    try:
        analysis = await chat_service.get_what_if_analysis(
            game_id=game_id,
            analysis_id=analysis_id,
        )

        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis {analysis_id} not found in game {game_id}",
            )

        return WhatIfAnalysisResponse.from_orm(analysis)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting what-if analysis {analysis_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve analysis: {str(e)}",
        )

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from enum import Enum

class WebSocketMessageType(str, Enum):
    AUTH = "auth"
    GAME_STATE = "game_state"
    PLAYER_ACTION = "player_action"
    CHAT = "chat"
    ERROR = "error"
    NOTIFICATION = "notification"

class WebSocketMessage(BaseModel):
    """Base WebSocket message schema"""
    type: WebSocketMessageType
    data: Dict[str, Any] = {}
    error: Optional[str] = None

class AuthMessage(WebSocketMessage):
    """Authentication message schema"""
    type: WebSocketMessageType = WebSocketMessageType.AUTH
    data: Dict[str, str] = Field(..., description="Must contain 'token' field with JWT token")

class GameStateMessage(WebSocketMessage):
    """Game state update message schema"""
    type: WebSocketMessageType = WebSocketMessageType.GAME_STATE
    data: Dict[str, Any] = Field(..., description="Complete game state")

class PlayerActionMessage(WebSocketMessage):
    """Player action message schema"""
    type: WebSocketMessageType = WebSocketMessageType.PLAYER_ACTION
    data: Dict[str, Any] = Field(..., description="Action details")

class ChatMessage(WebSocketMessage):
    """Chat message schema"""
    type: WebSocketMessageType = WebSocketMessageType.CHAT
    data: Dict[str, str] = Field(..., description="Must contain 'message' field with chat content")

class ErrorMessage(WebSocketMessage):
    """Error message schema"""
    type: WebSocketMessageType = WebSocketMessageType.ERROR
    error: str = Field(..., description="Error message")

class NotificationMessage(WebSocketMessage):
    """Notification message schema"""
    type: WebSocketMessageType = WebSocketMessageType.NOTIFICATION
    data: Dict[str, Any] = Field(..., description="Notification details")

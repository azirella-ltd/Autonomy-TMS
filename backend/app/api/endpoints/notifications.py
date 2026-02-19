"""
Notification API Endpoints

Endpoints for managing push notifications and user preferences.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.notification import PlatformType
from app.services.push_notification_service import PushNotificationService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class RegisterTokenRequest(BaseModel):
    """Request model for registering a push notification token."""
    token: str = Field(..., min_length=10, description="FCM device token")
    platform: PlatformType = Field(..., description="Platform type (ios/android)")
    device_id: Optional[str] = Field(None, max_length=255, description="Device identifier")
    device_name: Optional[str] = Field(None, max_length=255, description="Device name (e.g., 'iPhone 12')")
    app_version: Optional[str] = Field(None, max_length=50, description="Mobile app version")

class UnregisterTokenRequest(BaseModel):
    """Request model for unregistering a push notification token."""
    token: str = Field(..., min_length=10, description="FCM device token to remove")

class NotificationPreferencesUpdate(BaseModel):
    """Request model for updating notification preferences."""
    # Game notifications
    game_started: Optional[bool] = None
    round_started: Optional[bool] = None
    your_turn: Optional[bool] = None
    game_completed: Optional[bool] = None

    # Team notifications
    team_message: Optional[bool] = None
    teammate_action: Optional[bool] = None

    # System notifications
    system_announcement: Optional[bool] = None
    maintenance_alert: Optional[bool] = None

    # Analytics notifications
    performance_report: Optional[bool] = None
    leaderboard_update: Optional[bool] = None

    # Quiet hours
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="Start time in HH:MM format")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="End time in HH:MM format")

class SendTestNotificationRequest(BaseModel):
    """Request model for sending a test notification."""
    title: str = Field(default="Test Notification", max_length=100)
    body: str = Field(default="This is a test notification from The Beer Game", max_length=500)

class TokenResponse(BaseModel):
    """Response model for push token."""
    id: int
    token: str
    platform: str
    device_id: Optional[str]
    device_name: Optional[str]
    app_version: Optional[str]
    is_active: bool
    created_at: datetime
    last_used: datetime

    class Config:
        from_attributes = True

class PreferencesResponse(BaseModel):
    """Response model for notification preferences."""
    user_id: int
    game_started: bool
    round_started: bool
    your_turn: bool
    game_completed: bool
    team_message: bool
    teammate_action: bool
    system_announcement: bool
    maintenance_alert: bool
    performance_report: bool
    leaderboard_update: bool
    quiet_hours_enabled: bool
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Token Management Endpoints
# ============================================================================

@router.post("/register", response_model=Dict[str, Any])
async def register_push_token(
    req: RegisterTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a push notification token for the current user.

    This endpoint should be called when the mobile app obtains a new FCM token.
    """
    service = PushNotificationService(db)

    try:
        token = await service.register_token(
            user_id=current_user.id,
            token=req.token,
            platform=req.platform,
            device_id=req.device_id,
            device_name=req.device_name,
            app_version=req.app_version
        )

        return {
            "success": True,
            "message": "Push token registered successfully",
            "token": {
                "id": token.id,
                "platform": token.platform.value,
                "device_name": token.device_name,
                "created_at": token.created_at.isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")


@router.post("/unregister", response_model=Dict[str, Any])
async def unregister_push_token(
    req: UnregisterTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Unregister a push notification token.

    This endpoint should be called when the user logs out or uninstalls the app.
    """
    service = PushNotificationService(db)

    try:
        success = await service.unregister_token(req.token)

        if success:
            return {
                "success": True,
                "message": "Push token unregistered successfully"
            }
        else:
            return {
                "success": False,
                "message": "Token not found"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unregister token: {str(e)}")


@router.get("/tokens", response_model=Dict[str, Any])
async def list_push_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all push notification tokens for the current user.
    """
    service = PushNotificationService(db)

    try:
        tokens = await service.get_user_tokens(current_user.id, active_only=False)

        return {
            "tokens": [
                {
                    "id": token.id,
                    "platform": token.platform.value,
                    "device_id": token.device_id,
                    "device_name": token.device_name,
                    "app_version": token.app_version,
                    "is_active": token.is_active,
                    "created_at": token.created_at.isoformat(),
                    "last_used": token.last_used.isoformat()
                }
                for token in tokens
            ],
            "count": len(tokens)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tokens: {str(e)}")


# ============================================================================
# Preferences Endpoints
# ============================================================================

@router.get("/preferences", response_model=Dict[str, Any])
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get notification preferences for the current user.

    If no preferences exist, returns default values.
    """
    service = PushNotificationService(db)

    try:
        preferences = await service.get_user_preferences(current_user.id)

        if not preferences:
            # Return defaults
            return {
                "preferences": {
                    "user_id": current_user.id,
                    "game_started": True,
                    "round_started": True,
                    "your_turn": True,
                    "game_completed": True,
                    "team_message": True,
                    "teammate_action": False,
                    "system_announcement": True,
                    "maintenance_alert": True,
                    "performance_report": False,
                    "leaderboard_update": False,
                    "quiet_hours_enabled": False,
                    "quiet_hours_start": None,
                    "quiet_hours_end": None
                }
            }

        return {
            "preferences": {
                "user_id": preferences.user_id,
                "game_started": preferences.game_started,
                "round_started": preferences.round_started,
                "your_turn": preferences.your_turn,
                "game_completed": preferences.game_completed,
                "team_message": preferences.team_message,
                "teammate_action": preferences.teammate_action,
                "system_announcement": preferences.system_announcement,
                "maintenance_alert": preferences.maintenance_alert,
                "performance_report": preferences.performance_report,
                "leaderboard_update": preferences.leaderboard_update,
                "quiet_hours_enabled": preferences.quiet_hours_enabled,
                "quiet_hours_start": preferences.quiet_hours_start,
                "quiet_hours_end": preferences.quiet_hours_end,
                "created_at": preferences.created_at.isoformat(),
                "updated_at": preferences.updated_at.isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get preferences: {str(e)}")


@router.put("/preferences", response_model=Dict[str, Any])
async def update_notification_preferences(
    req: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update notification preferences for the current user.

    Only provided fields will be updated; others remain unchanged.
    """
    service = PushNotificationService(db)

    try:
        # Convert request to dict, excluding None values
        updates = {k: v for k, v in req.dict().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No preferences provided to update")

        preferences = await service.update_preferences(current_user.id, updates)

        return {
            "success": True,
            "message": "Preferences updated successfully",
            "preferences": {
                "user_id": preferences.user_id,
                "game_started": preferences.game_started,
                "round_started": preferences.round_started,
                "your_turn": preferences.your_turn,
                "game_completed": preferences.game_completed,
                "team_message": preferences.team_message,
                "teammate_action": preferences.teammate_action,
                "system_announcement": preferences.system_announcement,
                "maintenance_alert": preferences.maintenance_alert,
                "performance_report": preferences.performance_report,
                "leaderboard_update": preferences.leaderboard_update,
                "quiet_hours_enabled": preferences.quiet_hours_enabled,
                "quiet_hours_start": preferences.quiet_hours_start,
                "quiet_hours_end": preferences.quiet_hours_end,
                "updated_at": preferences.updated_at.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")


# ============================================================================
# Testing Endpoints
# ============================================================================

@router.post("/test", response_model=Dict[str, Any])
async def send_test_notification(
    req: SendTestNotificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a test notification to the current user.

    Useful for testing push notification setup.
    """
    service = PushNotificationService(db)

    try:
        result = await service.send_notification(
            user_id=current_user.id,
            title=req.title,
            body=req.body,
            notification_type="system_test",
            data={"test": "true"},
            force=True  # Bypass preferences for test notifications
        )

        return {
            "success": result["success"],
            "message": "Test notification sent" if result["success"] else "Failed to send test notification",
            "sent_count": result["sent_count"],
            "total_tokens": result["total_tokens"],
            "results": result["results"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test notification: {str(e)}")


@router.get("/status", response_model=Dict[str, Any])
async def get_notification_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get notification status for the current user.

    Returns information about registered tokens and preferences.
    """
    service = PushNotificationService(db)

    try:
        tokens = await service.get_user_tokens(current_user.id, active_only=True)
        preferences = await service.get_user_preferences(current_user.id)

        return {
            "user_id": current_user.id,
            "notifications_enabled": len(tokens) > 0,
            "active_tokens": len(tokens),
            "platforms": list(set(token.platform.value for token in tokens)),
            "preferences_configured": preferences is not None,
            "firebase_available": service._firebase_initialized if hasattr(service, '_firebase_initialized') else False
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get notification status: {str(e)}")

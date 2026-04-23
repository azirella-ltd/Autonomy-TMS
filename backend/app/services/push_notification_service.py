"""
Push Notification Service

Sends push notifications to mobile devices using Firebase Cloud Messaging (FCM).
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, time
import logging
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models.notification import PushToken, NotificationPreference, NotificationLog, PlatformType
from app.models.user import User

logger = logging.getLogger(__name__)

# Optional Firebase Admin SDK dependency
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    messaging = None


class PushNotificationService:
    """
    Service for sending push notifications via Firebase Cloud Messaging.

    Features:
    - Send notifications to individual users or groups
    - Respect user notification preferences
    - Quiet hours support
    - Delivery tracking and logging
    - Multi-platform support (iOS, Android)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._firebase_initialized = False

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK (lazy initialization)."""
        if self._firebase_initialized or not FIREBASE_AVAILABLE:
            return

        try:
            # Check if Firebase app already exists
            firebase_admin.get_app()
            self._firebase_initialized = True
            logger.info("Firebase Admin SDK already initialized")
        except ValueError:
            # Initialize Firebase with credentials
            try:
                cred = credentials.Certificate("firebase-credentials.json")
                firebase_admin.initialize_app(cred)
                self._firebase_initialized = True
                logger.info("Firebase Admin SDK initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Firebase: {e}. Push notifications will be logged but not sent.")
                self._firebase_initialized = False

    async def register_token(
        self,
        user_id: int,
        token: str,
        platform: PlatformType,
        device_id: Optional[str] = None,
        device_name: Optional[str] = None,
        app_version: Optional[str] = None
    ) -> PushToken:
        """
        Register a new push notification token for a user.

        Args:
            user_id: User ID
            token: FCM device token
            platform: Platform type (ios/android)
            device_id: Optional device identifier
            device_name: Optional device name
            app_version: Optional app version

        Returns:
            PushToken: The registered token record
        """
        # Check if token already exists
        stmt = select(PushToken).where(PushToken.token == token)
        result = await self.db.execute(stmt)
        existing_token = result.scalar_one_or_none()

        if existing_token:
            # Update existing token
            existing_token.user_id = user_id
            existing_token.platform = platform
            existing_token.device_id = device_id
            existing_token.device_name = device_name
            existing_token.app_version = app_version
            existing_token.is_active = True
            existing_token.last_used = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing_token)
            logger.info(f"Updated existing push token for user {user_id}")
            return existing_token

        # Create new token
        push_token = PushToken(
            user_id=user_id,
            token=token,
            platform=platform,
            device_id=device_id,
            device_name=device_name,
            app_version=app_version,
            is_active=True
        )

        self.db.add(push_token)
        await self.db.commit()
        await self.db.refresh(push_token)

        logger.info(f"Registered new push token for user {user_id}, platform {platform}")
        return push_token

    async def unregister_token(self, token: str) -> bool:
        """
        Unregister a push notification token.

        Args:
            token: FCM device token

        Returns:
            bool: True if token was found and removed, False otherwise
        """
        stmt = select(PushToken).where(PushToken.token == token)
        result = await self.db.execute(stmt)
        push_token = result.scalar_one_or_none()

        if push_token:
            await self.db.delete(push_token)
            await self.db.commit()
            logger.info(f"Unregistered push token for user {push_token.user_id}")
            return True

        logger.warning(f"Token not found for unregistration")
        return False

    async def get_user_tokens(self, user_id: int, active_only: bool = True) -> List[PushToken]:
        """
        Get all push tokens for a user.

        Args:
            user_id: User ID
            active_only: Only return active tokens

        Returns:
            List of push tokens
        """
        stmt = select(PushToken).where(PushToken.user_id == user_id)
        if active_only:
            stmt = stmt.where(PushToken.is_active == True)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_preferences(self, user_id: int) -> Optional[NotificationPreference]:
        """
        Get notification preferences for a user.

        Args:
            user_id: User ID

        Returns:
            NotificationPreference or None
        """
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_preferences(
        self,
        user_id: int,
        preferences: Dict[str, Any]
    ) -> NotificationPreference:
        """
        Update notification preferences for a user.

        Args:
            user_id: User ID
            preferences: Dictionary of preference fields to update

        Returns:
            Updated NotificationPreference
        """
        # Get or create preferences
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreference(user_id=user_id)
            self.db.add(prefs)

        # Update fields
        for key, value in preferences.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)

        await self.db.commit()
        await self.db.refresh(prefs)

        logger.info(f"Updated notification preferences for user {user_id}")
        return prefs

    def _check_quiet_hours(self, preferences: Optional[NotificationPreference]) -> bool:
        """
        Check if current time is within user's quiet hours.

        Args:
            preferences: User's notification preferences

        Returns:
            bool: True if in quiet hours, False otherwise
        """
        if not preferences or not preferences.quiet_hours_enabled:
            return False

        if not preferences.quiet_hours_start or not preferences.quiet_hours_end:
            return False

        try:
            now = datetime.utcnow().time()
            start = time.fromisoformat(preferences.quiet_hours_start)
            end = time.fromisoformat(preferences.quiet_hours_end)

            # Handle overnight quiet hours (e.g., 22:00 to 08:00)
            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end

        except ValueError:
            logger.warning(f"Invalid quiet hours format for user {preferences.user_id}")
            return False

    def _should_send_notification(
        self,
        preferences: Optional[NotificationPreference],
        notification_type: str
    ) -> bool:
        """
        Check if notification should be sent based on user preferences.

        Args:
            preferences: User's notification preferences
            notification_type: Type of notification

        Returns:
            bool: True if should send, False otherwise
        """
        # If no preferences, send all notifications
        if not preferences:
            return True

        # Check quiet hours
        if self._check_quiet_hours(preferences):
            logger.info(f"Notification blocked by quiet hours: {notification_type}")
            return False

        # Check notification type preference
        preference_field = notification_type.replace("-", "_")
        if hasattr(preferences, preference_field):
            enabled = getattr(preferences, preference_field)
            if not enabled:
                logger.info(f"Notification blocked by user preference: {notification_type}")
                return False

        return True

    async def send_notification(
        self,
        user_id: int,
        title: str,
        body: str,
        notification_type: str,
        data: Optional[Dict[str, str]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Send push notification to a user.

        Args:
            user_id: User ID
            title: Notification title
            body: Notification body
            notification_type: Type of notification (e.g., "your_turn", "scenario_started")
            data: Optional additional data payload
            force: Bypass preference checks if True

        Returns:
            Dict with status and results
        """
        self._initialize_firebase()

        # Get user preferences
        preferences = await self.get_user_preferences(user_id)

        # Check if should send (unless forced)
        if not force and not self._should_send_notification(preferences, notification_type):
            logger.info(f"Skipping notification for user {user_id} due to preferences")
            return {
                "success": False,
                "reason": "blocked_by_preferences",
                "sent_count": 0
            }

        # Get user's push tokens
        tokens = await self.get_user_tokens(user_id, active_only=True)

        if not tokens:
            logger.warning(f"No active push tokens for user {user_id}")
            return {
                "success": False,
                "reason": "no_tokens",
                "sent_count": 0
            }

        # Prepare notification data
        notification_data = data or {}
        notification_data["notification_type"] = notification_type
        notification_data["timestamp"] = datetime.utcnow().isoformat()

        # Convert all data values to strings (FCM requirement)
        notification_data = {k: str(v) for k, v in notification_data.items()}

        results = []
        sent_count = 0

        for push_token in tokens:
            # Log notification attempt
            log_entry = NotificationLog(
                user_id=user_id,
                push_token_id=push_token.id,
                notification_type=notification_type,
                title=title,
                body=body,
                data=json.dumps(notification_data),
                status="pending"
            )
            self.db.add(log_entry)
            await self.db.flush()  # Get log_entry.id

            if FIREBASE_AVAILABLE and self._firebase_initialized:
                try:
                    # Create FCM message
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body
                        ),
                        data=notification_data,
                        token=push_token.token,
                        android=messaging.AndroidConfig(
                            priority='high',
                            notification=messaging.AndroidNotification(
                                sound='default'
                            )
                        ),
                        apns=messaging.APNSConfig(
                            payload=messaging.APNSPayload(
                                aps=messaging.Aps(
                                    sound='default',
                                    badge=1
                                )
                            )
                        )
                    )

                    # Send message
                    response = messaging.send(message)

                    # Update log
                    log_entry.status = "sent"
                    log_entry.fcm_message_id = response
                    log_entry.delivered_at = datetime.utcnow()

                    sent_count += 1
                    results.append({
                        "token_id": push_token.id,
                        "platform": push_token.platform.value,
                        "status": "sent",
                        "message_id": response
                    })

                    logger.info(f"Sent notification to user {user_id}, token {push_token.id}, message_id {response}")

                except Exception as e:
                    # Handle send error
                    error_message = str(e)
                    log_entry.status = "failed"
                    log_entry.error_message = error_message

                    # Deactivate token if it's invalid
                    if "not-found" in error_message.lower() or "invalid" in error_message.lower():
                        push_token.is_active = False
                        logger.warning(f"Deactivated invalid token {push_token.id}")

                    results.append({
                        "token_id": push_token.id,
                        "platform": push_token.platform.value,
                        "status": "failed",
                        "error": error_message
                    })

                    logger.error(f"Failed to send notification to token {push_token.id}: {error_message}")

            else:
                # Firebase not available - log only
                log_entry.status = "logged_only"
                log_entry.error_message = "Firebase not initialized"

                results.append({
                    "token_id": push_token.id,
                    "platform": push_token.platform.value,
                    "status": "logged_only"
                })

                logger.info(f"Notification logged (Firebase unavailable): user {user_id}, type {notification_type}")

        await self.db.commit()

        return {
            "success": sent_count > 0 or not FIREBASE_AVAILABLE,
            "sent_count": sent_count,
            "total_tokens": len(tokens),
            "results": results
        }

    async def send_notification_to_multiple_users(
        self,
        user_ids: List[int],
        title: str,
        body: str,
        notification_type: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple users.

        Args:
            user_ids: List of user IDs
            title: Notification title
            body: Notification body
            notification_type: Type of notification
            data: Optional additional data payload

        Returns:
            Dict with aggregated results
        """
        total_sent = 0
        total_failed = 0
        user_results = []

        for user_id in user_ids:
            result = await self.send_notification(
                user_id=user_id,
                title=title,
                body=body,
                notification_type=notification_type,
                data=data
            )

            if result["success"]:
                total_sent += result["sent_count"]
            else:
                total_failed += 1

            user_results.append({
                "user_id": user_id,
                "success": result["success"],
                "sent_count": result["sent_count"]
            })

        return {
            "total_users": len(user_ids),
            "total_sent": total_sent,
            "total_failed": total_failed,
            "user_results": user_results
        }

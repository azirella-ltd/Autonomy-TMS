"""
Notification Models

Database models for push notifications and user preferences.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base


class PlatformType(str, enum.Enum):
    """Mobile platform types."""
    IOS = "ios"
    ANDROID = "android"


class PushToken(Base):
    """
    Push notification tokens for mobile devices.

    Stores FCM tokens for sending push notifications to mobile apps.
    """
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(500), unique=True, nullable=False, index=True)
    platform = Column(Enum(PlatformType, name="platform_type"), nullable=False)
    device_id = Column(String(255), nullable=True)  # Optional device identifier
    device_name = Column(String(255), nullable=True)  # e.g., "iPhone 12", "Pixel 6"
    app_version = Column(String(50), nullable=True)  # Mobile app version
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User")

    def __repr__(self):
        return f"<PushToken(id={self.id}, user_id={self.user_id}, platform={self.platform}, active={self.is_active})>"


class NotificationPreference(Base):
    """
    User notification preferences.

    Controls which types of notifications a user wants to receive.
    """
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Scenario notifications
    scenario_started = Column(Boolean, default=True, nullable=False)
    period_started = Column(Boolean, default=True, nullable=False)
    your_turn = Column(Boolean, default=True, nullable=False)
    scenario_completed = Column(Boolean, default=True, nullable=False)

    # Team notifications
    team_message = Column(Boolean, default=True, nullable=False)
    teammate_action = Column(Boolean, default=False, nullable=False)

    # System notifications
    system_announcement = Column(Boolean, default=True, nullable=False)
    maintenance_alert = Column(Boolean, default=True, nullable=False)

    # Analytics notifications
    performance_report = Column(Boolean, default=False, nullable=False)
    leaderboard_update = Column(Boolean, default=False, nullable=False)

    # Quiet hours (optional)
    quiet_hours_enabled = Column(Boolean, default=False, nullable=False)
    quiet_hours_start = Column(String(5), nullable=True)  # e.g., "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # e.g., "08:00"

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User")

    def __repr__(self):
        return f"<NotificationPreference(user_id={self.user_id}, your_turn={self.your_turn})>"


class NotificationLog(Base):
    """
    Log of sent notifications for debugging and analytics.

    Tracks all notifications sent to users for troubleshooting and reporting.
    """
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    push_token_id = Column(Integer, ForeignKey("push_tokens.id", ondelete="SET NULL"), nullable=True)

    # Notification content
    notification_type = Column(String(100), nullable=False, index=True)  # e.g., "your_turn", "scenario_started"
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(Text, nullable=True)  # JSON string with additional data

    # Delivery status
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, sent, delivered, failed
    error_message = Column(Text, nullable=True)
    fcm_message_id = Column(String(255), nullable=True)  # Firebase Cloud Messaging message ID

    # Timing
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<NotificationLog(id={self.id}, user_id={self.user_id}, type={self.notification_type}, status={self.status})>"

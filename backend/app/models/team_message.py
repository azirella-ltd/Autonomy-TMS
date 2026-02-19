"""
Team Messaging Database Models

Provides real-time team messaging for supply chain collaboration:
- Threaded conversations on entities (orders, plans, products, sites)
- Direct messages between team members
- Channel-based group discussions
- @mentions and notifications
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Table,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List

from app.models.base import Base


# Many-to-many association table for channel members
channel_members = Table(
    'team_channel_members',
    Base.metadata,
    Column('channel_id', Integer, ForeignKey('team_channels.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('joined_at', DateTime, default=func.now()),
    Column('role', String(50), default='member'),  # owner, admin, member
    Column('muted', Boolean, default=False),
    Column('last_read_at', DateTime),
)


class TeamChannel(Base):
    """
    Team Channel - A group messaging container

    Channels can be:
    - Entity-linked: Attached to a PO, TO, supply plan, etc.
    - Topic-based: General discussion topics
    - Direct: Private conversations between users
    """
    __tablename__ = "team_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Channel identification
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    # Channel type
    channel_type: Mapped[str] = mapped_column(
        String(50),
        default="topic",
        nullable=False,
        comment="entity, topic, direct"
    )

    # Entity linkage (for entity-based channels)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))  # purchase_order, transfer_order, supply_plan
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Visibility
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Owner
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Message count (denormalized for performance)
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    messages = relationship("TeamMessage", back_populates="channel", cascade="all, delete-orphan")
    members = relationship("User", secondary=channel_members, backref="team_channels")

    __table_args__ = (
        Index('idx_channel_entity', 'entity_type', 'entity_id'),
        Index('idx_channel_type', 'channel_type'),
        Index('idx_channel_created_by', 'created_by_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "channel_type": self.channel_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "is_private": self.is_private,
            "is_archived": self.is_archived,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "message_count": self.message_count,
        }


class TeamMessage(Base):
    """
    Team Message - Individual message in a channel

    Supports:
    - Text messages with formatting
    - @mentions
    - File attachments
    - Threaded replies
    - Reactions
    """
    __tablename__ = "team_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Channel reference
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("team_channels.id", ondelete="CASCADE"), nullable=False)

    # Sender
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(200), nullable=False)  # Denormalized

    # Threading
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("team_messages.id"))
    thread_root_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    # Message content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[Optional[str]] = mapped_column(Text)  # Rendered with mentions

    # Message type
    message_type: Mapped[str] = mapped_column(
        String(50),
        default="text",
        comment="text, system, alert, announcement"
    )

    # Status
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Priority
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Reply count (denormalized)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    channel = relationship("TeamChannel", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], backref="sent_team_messages")
    parent = relationship("TeamMessage", remote_side=[id], backref="replies")
    mentions = relationship("TeamMessageMention", back_populates="message", cascade="all, delete-orphan")
    attachments = relationship("TeamMessageAttachment", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_tm_channel', 'channel_id'),
        Index('idx_tm_sender', 'sender_id'),
        Index('idx_tm_created', 'created_at'),
        Index('idx_tm_thread', 'thread_root_id'),
    )

    def to_dict(self, include_replies: bool = False) -> dict:
        result = {
            "id": self.id,
            "channel_id": self.channel_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "parent_id": self.parent_id,
            "thread_root_id": self.thread_root_id,
            "content": self.content,
            "content_html": self.content_html,
            "message_type": self.message_type,
            "is_edited": self.is_edited,
            "is_pinned": self.is_pinned,
            "is_urgent": self.is_urgent,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reply_count": self.reply_count,
            "mentions": [m.to_dict() for m in self.mentions] if self.mentions else [],
            "attachments": [a.to_dict() for a in self.attachments] if self.attachments else [],
        }
        if include_replies and self.replies:
            result["replies"] = [r.to_dict() for r in self.replies if not r.is_deleted]
        return result


class TeamMessageMention(Base):
    """
    Team Message Mention - Tracks @mentions in messages
    """
    __tablename__ = "team_message_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("team_messages.id", ondelete="CASCADE"), nullable=False)
    mentioned_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    mentioned_username: Mapped[str] = mapped_column(String(200), nullable=False)

    # Read status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message = relationship("TeamMessage", back_populates="mentions")
    mentioned_user = relationship("User", backref="team_message_mentions")

    __table_args__ = (
        Index('idx_tmm_user', 'mentioned_user_id'),
        Index('idx_tmm_unread', 'mentioned_user_id', 'is_read'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "mentioned_user_id": self.mentioned_user_id,
            "mentioned_username": self.mentioned_username,
            "is_read": self.is_read,
        }


class TeamMessageAttachment(Base):
    """
    Team Message Attachment - File attachments to messages
    """
    __tablename__ = "team_message_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("team_messages.id", ondelete="CASCADE"), nullable=False)

    # File info
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Upload info
    uploaded_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message = relationship("TeamMessage", back_populates="attachments")
    uploader = relationship("User", backref="team_message_attachments")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "uploaded_by_id": self.uploaded_by_id,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class TeamMessageRead(Base):
    """
    Team Message Read Status - Tracks read receipts per user
    """
    __tablename__ = "team_message_reads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("team_channels.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_read_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("team_messages.id"))
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_tmr_channel_user', 'channel_id', 'user_id', unique=True),
    )

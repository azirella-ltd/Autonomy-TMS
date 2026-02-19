"""
Comment Entity Model - For Inline Comments on Orders/Plans

Provides a generic, polymorphic comment system that can attach to any entity type:
- Purchase Orders (PO)
- Transfer Orders (TO)
- Supply Plans
- Demand Plans
- Recommendations
- Production Orders
- etc.

Supports threading (replies), mentions (@user), and attachments.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List

from app.models.base import Base


class Comment(Base):
    """
    Generic Comment for Orders and Plans

    Uses polymorphic association pattern - entity_type + entity_id
    to reference any entity in the system.

    Features:
    - Threading (parent_id for replies)
    - @mentions (extracted and stored in mentions table)
    - Attachments (stored in comment_attachments table)
    - Edit history tracking
    - Soft delete
    """
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Polymorphic reference - can link to any entity type
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="purchase_order, transfer_order, supply_plan, demand_plan, recommendation, production_order, etc."
    )
    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="ID of the entity being commented on"
    )

    # Threading support
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comments.id"))
    thread_root_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # Root comment for threading

    # Comment content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[Optional[str]] = mapped_column(Text)  # Rendered HTML with mentions

    # Author info
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)  # Denormalized for display
    author_role: Mapped[Optional[str]] = mapped_column(String(100))  # Role at time of comment

    # Status and edit tracking
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    # Comment type/context
    comment_type: Mapped[str] = mapped_column(
        String(50),
        default="general",
        comment="general, question, approval, rejection, issue, resolution, status_change"
    )

    # Priority/importance
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_important: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    author = relationship("User", foreign_keys=[author_id], backref="comments")
    parent = relationship("Comment", remote_side=[id], backref="replies")
    mentions = relationship("CommentMention", back_populates="comment", cascade="all, delete-orphan")
    attachments = relationship("CommentAttachment", back_populates="comment", cascade="all, delete-orphan")

    # Composite index for efficient entity queries
    __table_args__ = (
        Index('idx_comment_entity', 'entity_type', 'entity_id'),
        Index('idx_comment_author', 'author_id'),
        Index('idx_comment_created', 'created_at'),
    )

    def __repr__(self):
        return (
            f"<Comment(id={self.id}, entity_type='{self.entity_type}', "
            f"entity_id='{self.entity_id}', author='{self.author_name}')>"
        )

    def to_dict(self, include_replies: bool = False) -> dict:
        """Convert to dictionary for API response"""
        result = {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "parent_id": self.parent_id,
            "thread_root_id": self.thread_root_id,
            "content": self.content,
            "content_html": self.content_html,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_role": self.author_role,
            "comment_type": self.comment_type,
            "is_edited": self.is_edited,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "is_pinned": self.is_pinned,
            "is_important": self.is_important,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "mentions": [m.to_dict() for m in self.mentions] if self.mentions else [],
            "attachments": [a.to_dict() for a in self.attachments] if self.attachments else [],
            "reply_count": len(self.replies) if self.replies else 0,
        }

        if include_replies and self.replies:
            result["replies"] = [r.to_dict(include_replies=True) for r in self.replies if not r.is_deleted]

        return result


class CommentMention(Base):
    """
    Tracks @mentions in comments

    When a user is mentioned in a comment, a record is created here
    to enable notifications and filtering.
    """
    __tablename__ = "comment_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("comments.id"), nullable=False)
    mentioned_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    mentioned_username: Mapped[str] = mapped_column(String(200), nullable=False)  # Denormalized

    # Has the mentioned user seen this?
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    comment = relationship("Comment", back_populates="mentions")
    mentioned_user = relationship("User", backref="comment_mentions")

    __table_args__ = (
        Index('idx_mention_user', 'mentioned_user_id'),
        Index('idx_mention_unread', 'mentioned_user_id', 'is_read'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "comment_id": self.comment_id,
            "mentioned_user_id": self.mentioned_user_id,
            "mentioned_username": self.mentioned_username,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


class CommentAttachment(Base):
    """
    File attachments for comments

    Supports documents, images, and other files attached to comments.
    """
    __tablename__ = "comment_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("comments.id"), nullable=False)

    # File info
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # Storage path
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # Bytes
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)  # MIME type

    # Upload info
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    comment = relationship("Comment", back_populates="attachments")
    uploader = relationship("User", backref="comment_attachments")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "comment_id": self.comment_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }

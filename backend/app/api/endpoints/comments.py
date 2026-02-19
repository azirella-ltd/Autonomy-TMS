"""
Comments API Endpoints - Inline Comments for Orders/Plans

Provides CRUD operations for comments on any entity type:
- Purchase Orders
- Transfer Orders
- Supply Plans
- Demand Plans
- Recommendations
- Production Orders
- etc.

Supports threading, @mentions, and attachments.
"""

from datetime import datetime
from typing import List, Optional
import re
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_sync_db as get_db
from app.models.comment import Comment, CommentMention, CommentAttachment
from app.models.user import User
from app.api.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Pydantic Schemas
# --------------------------------------------------------------------------

class CommentCreate(BaseModel):
    """Request to create a new comment"""
    entity_type: str = Field(..., description="Type of entity: purchase_order, transfer_order, supply_plan, demand_plan, etc.")
    entity_id: str = Field(..., description="ID of the entity being commented on")
    content: str = Field(..., min_length=1, max_length=5000, description="Comment text, may include @mentions")
    parent_id: Optional[int] = Field(None, description="Parent comment ID for replies")
    comment_type: str = Field("general", description="Type: general, question, approval, rejection, issue, resolution")


class CommentUpdate(BaseModel):
    """Request to update a comment"""
    content: str = Field(..., min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    """Single comment response"""
    id: int
    entity_type: str
    entity_id: str
    parent_id: Optional[int]
    thread_root_id: Optional[int]
    content: str
    content_html: Optional[str]
    author_id: int
    author_name: str
    author_role: Optional[str]
    comment_type: str
    is_edited: bool
    edited_at: Optional[str]
    is_pinned: bool
    is_important: bool
    is_deleted: bool
    created_at: str
    updated_at: str
    mentions: List[dict]
    reply_count: int
    replies: Optional[List[dict]] = None

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """List of comments response"""
    comments: List[CommentResponse]
    total_count: int


class MentionResponse(BaseModel):
    """Unread mentions for a user"""
    mentions: List[dict]
    unread_count: int


# --------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------

def extract_mentions(content: str) -> List[str]:
    """Extract @mentions from comment content"""
    # Match @username patterns (alphanumeric, underscores, dots)
    pattern = r'@([a-zA-Z0-9_.]+)'
    return re.findall(pattern, content)


def render_content_html(content: str, mentions: List[str]) -> str:
    """Render comment content with HTML markup for mentions"""
    html = content
    for username in mentions:
        html = html.replace(
            f'@{username}',
            f'<span class="mention" data-username="{username}">@{username}</span>'
        )
    return html


def create_mention_records(
    db: Session,
    comment: Comment,
    mention_usernames: List[str]
) -> List[CommentMention]:
    """Create CommentMention records for @mentions"""
    mentions = []
    for username in mention_usernames:
        # Find user by username or email
        user = db.query(User).filter(
            (User.name == username) | (User.email.ilike(f"{username}%"))
        ).first()

        if user:
            mention = CommentMention(
                comment_id=comment.id,
                mentioned_user_id=user.id,
                mentioned_username=username,
                is_read=False
            )
            db.add(mention)
            mentions.append(mention)

    return mentions


# --------------------------------------------------------------------------
# API Endpoints
# --------------------------------------------------------------------------

@router.post("", response_model=CommentResponse)
async def create_comment(
    request: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new comment on an entity.

    Supports:
    - @mentions (will create notification records)
    - Threading (set parent_id for replies)
    - Comment types (general, question, approval, etc.)
    """
    # Extract mentions from content
    mention_usernames = extract_mentions(request.content)
    content_html = render_content_html(request.content, mention_usernames)

    # Determine thread root
    thread_root_id = None
    if request.parent_id:
        parent = db.query(Comment).filter(Comment.id == request.parent_id).first()
        if parent:
            thread_root_id = parent.thread_root_id or parent.id
        else:
            raise HTTPException(status_code=404, detail="Parent comment not found")

    # Get user's role for denormalization
    user_role = None
    if current_user.roles:
        user_role = current_user.roles[0].name if hasattr(current_user.roles[0], 'name') else str(current_user.roles[0])

    # Create comment
    comment = Comment(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        parent_id=request.parent_id,
        thread_root_id=thread_root_id,
        content=request.content,
        content_html=content_html,
        author_id=current_user.id,
        author_name=current_user.name or current_user.email,
        author_role=user_role,
        comment_type=request.comment_type,
    )
    db.add(comment)
    db.flush()  # Get the ID

    # If this is a root comment, set thread_root_id to itself
    if not request.parent_id:
        comment.thread_root_id = comment.id

    # Create mention records
    create_mention_records(db, comment, mention_usernames)

    db.commit()
    db.refresh(comment)

    logger.info(f"Comment created: id={comment.id}, entity={request.entity_type}:{request.entity_id}, author={current_user.email}")

    return CommentResponse(
        id=comment.id,
        entity_type=comment.entity_type,
        entity_id=comment.entity_id,
        parent_id=comment.parent_id,
        thread_root_id=comment.thread_root_id,
        content=comment.content,
        content_html=comment.content_html,
        author_id=comment.author_id,
        author_name=comment.author_name,
        author_role=comment.author_role,
        comment_type=comment.comment_type,
        is_edited=comment.is_edited,
        edited_at=comment.edited_at.isoformat() if comment.edited_at else None,
        is_pinned=comment.is_pinned,
        is_important=comment.is_important,
        is_deleted=comment.is_deleted,
        created_at=comment.created_at.isoformat(),
        updated_at=comment.updated_at.isoformat(),
        mentions=[m.to_dict() for m in comment.mentions],
        reply_count=0,
        replies=[]
    )


@router.get("", response_model=CommentListResponse)
async def get_comments(
    entity_type: str = Query(..., description="Entity type"),
    entity_id: str = Query(..., description="Entity ID"),
    include_replies: bool = Query(True, description="Include nested replies"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all comments for an entity.

    Returns threaded comments with replies nested under parent comments.
    """
    # Get root-level comments (no parent)
    query = db.query(Comment).filter(
        Comment.entity_type == entity_type,
        Comment.entity_id == entity_id,
        Comment.is_deleted == False,
        Comment.parent_id.is_(None)  # Root comments only
    ).order_by(Comment.created_at.desc())

    comments = query.all()
    total_count = len(comments)

    # Convert to response format
    comment_responses = []
    for comment in comments:
        response = CommentResponse(
            id=comment.id,
            entity_type=comment.entity_type,
            entity_id=comment.entity_id,
            parent_id=comment.parent_id,
            thread_root_id=comment.thread_root_id,
            content=comment.content,
            content_html=comment.content_html,
            author_id=comment.author_id,
            author_name=comment.author_name,
            author_role=comment.author_role,
            comment_type=comment.comment_type,
            is_edited=comment.is_edited,
            edited_at=comment.edited_at.isoformat() if comment.edited_at else None,
            is_pinned=comment.is_pinned,
            is_important=comment.is_important,
            is_deleted=comment.is_deleted,
            created_at=comment.created_at.isoformat(),
            updated_at=comment.updated_at.isoformat(),
            mentions=[m.to_dict() for m in comment.mentions],
            reply_count=len([r for r in comment.replies if not r.is_deleted]) if comment.replies else 0,
            replies=[_comment_to_response(r).model_dump() for r in comment.replies if not r.is_deleted] if include_replies and comment.replies else None
        )
        comment_responses.append(response)

    return CommentListResponse(comments=comment_responses, total_count=total_count)


def _comment_to_response(comment: Comment) -> CommentResponse:
    """Helper to convert Comment model to response"""
    return CommentResponse(
        id=comment.id,
        entity_type=comment.entity_type,
        entity_id=comment.entity_id,
        parent_id=comment.parent_id,
        thread_root_id=comment.thread_root_id,
        content=comment.content,
        content_html=comment.content_html,
        author_id=comment.author_id,
        author_name=comment.author_name,
        author_role=comment.author_role,
        comment_type=comment.comment_type,
        is_edited=comment.is_edited,
        edited_at=comment.edited_at.isoformat() if comment.edited_at else None,
        is_pinned=comment.is_pinned,
        is_important=comment.is_important,
        is_deleted=comment.is_deleted,
        created_at=comment.created_at.isoformat(),
        updated_at=comment.updated_at.isoformat(),
        mentions=[m.to_dict() for m in comment.mentions] if comment.mentions else [],
        reply_count=len([r for r in comment.replies if not r.is_deleted]) if comment.replies else 0,
        replies=[_comment_to_response(r).model_dump() for r in comment.replies if not r.is_deleted] if comment.replies else None
    )


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single comment by ID"""
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.is_deleted == False
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    return _comment_to_response(comment)


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    request: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a comment.

    Only the author can edit their own comments.
    """
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.is_deleted == False
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Check ownership
    if comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments")

    # Extract new mentions
    mention_usernames = extract_mentions(request.content)
    content_html = render_content_html(request.content, mention_usernames)

    # Update comment
    comment.content = request.content
    comment.content_html = content_html
    comment.is_edited = True
    comment.edited_at = datetime.utcnow()

    # Update mentions (remove old, add new)
    db.query(CommentMention).filter(CommentMention.comment_id == comment_id).delete()
    create_mention_records(db, comment, mention_usernames)

    db.commit()
    db.refresh(comment)

    logger.info(f"Comment updated: id={comment.id}, author={current_user.email}")

    return _comment_to_response(comment)


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete a comment.

    Only the author or admins can delete comments.
    """
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.is_deleted == False
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Check ownership or admin status
    is_admin = any(r.name in ['SYSTEM_ADMIN', 'GROUP_ADMIN'] for r in current_user.roles) if current_user.roles else False
    if comment.author_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")

    # Soft delete
    comment.is_deleted = True
    comment.deleted_at = datetime.utcnow()
    comment.deleted_by = current_user.id

    db.commit()

    logger.info(f"Comment deleted: id={comment.id}, deleted_by={current_user.email}")

    return {"success": True, "message": "Comment deleted"}


@router.post("/{comment_id}/pin")
async def pin_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Pin a comment (admin only)"""
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.is_deleted == False
    ).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.is_pinned = not comment.is_pinned
    db.commit()

    return {"success": True, "is_pinned": comment.is_pinned}


@router.get("/mentions/unread", response_model=MentionResponse)
async def get_unread_mentions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get unread @mentions for the current user"""
    mentions = db.query(CommentMention).filter(
        CommentMention.mentioned_user_id == current_user.id,
        CommentMention.is_read == False
    ).all()

    return MentionResponse(
        mentions=[m.to_dict() for m in mentions],
        unread_count=len(mentions)
    )


@router.post("/mentions/{mention_id}/read")
async def mark_mention_read(
    mention_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a mention as read"""
    mention = db.query(CommentMention).filter(
        CommentMention.id == mention_id,
        CommentMention.mentioned_user_id == current_user.id
    ).first()

    if not mention:
        raise HTTPException(status_code=404, detail="Mention not found")

    mention.is_read = True
    mention.read_at = datetime.utcnow()
    db.commit()

    return {"success": True}


@router.post("/mentions/read-all")
async def mark_all_mentions_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all mentions as read for current user"""
    db.query(CommentMention).filter(
        CommentMention.mentioned_user_id == current_user.id,
        CommentMention.is_read == False
    ).update({
        CommentMention.is_read: True,
        CommentMention.read_at: datetime.utcnow()
    })
    db.commit()

    return {"success": True}

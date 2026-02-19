"""
Team Messaging API Endpoints

Real-time team messaging for supply chain collaboration:
- Channel management (create, join, leave)
- Message CRUD with threading
- @mentions and notifications
- Read receipts
"""

from typing import List, Optional
from datetime import datetime
import re
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from app.db.session import get_sync_db as get_db
from app.models.user import User
from app.models.team_message import (
    TeamChannel, TeamMessage, TeamMessageMention,
    TeamMessageAttachment, TeamMessageRead, channel_members
)
from app.api.endpoints.auth import get_current_user

router = APIRouter(prefix="/team-messaging", tags=["team-messaging", "collaboration"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CreateChannelRequest(BaseModel):
    """Request to create a channel"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    channel_type: str = Field("topic", description="entity, topic, direct")
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    is_private: bool = False
    member_ids: List[int] = Field(default_factory=list, description="Initial member user IDs")


class ChannelResponse(BaseModel):
    """Channel response"""
    id: int
    name: str
    description: Optional[str]
    channel_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    is_private: bool
    is_archived: bool
    created_by_id: int
    created_at: datetime
    last_message_at: Optional[datetime]
    message_count: int
    member_count: int = 0
    unread_count: int = 0

    class Config:
        from_attributes = True


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    content: str = Field(..., min_length=1, max_length=10000)
    parent_id: Optional[int] = None
    message_type: str = Field("text", description="text, system, alert, announcement")
    is_urgent: bool = False


class MessageResponse(BaseModel):
    """Message response"""
    id: int
    channel_id: int
    sender_id: int
    sender_name: str
    parent_id: Optional[int]
    thread_root_id: Optional[int]
    content: str
    content_html: Optional[str]
    message_type: str
    is_edited: bool
    is_pinned: bool
    is_urgent: bool
    is_deleted: bool
    created_at: datetime
    reply_count: int
    mentions: List[dict] = []
    replies: Optional[List[dict]] = None

    class Config:
        from_attributes = True


class ChannelListResponse(BaseModel):
    """List of channels"""
    channels: List[ChannelResponse]
    total_count: int


class MessageListResponse(BaseModel):
    """List of messages"""
    messages: List[MessageResponse]
    total_count: int
    has_more: bool


# ============================================================================
# Helper Functions
# ============================================================================

def extract_mentions(content: str) -> List[str]:
    """Extract @mentions from message content"""
    pattern = r'@([a-zA-Z0-9_.]+)'
    return re.findall(pattern, content)


def render_content_html(content: str, mentions: List[str]) -> str:
    """Render message content with HTML markup for mentions"""
    html = content
    for username in mentions:
        html = html.replace(
            f'@{username}',
            f'<span class="mention" data-username="{username}">@{username}</span>'
        )
    return html


def create_mention_records(
    db: Session,
    message: TeamMessage,
    mention_usernames: List[str]
) -> List[TeamMessageMention]:
    """Create mention records for @mentions"""
    mentions = []
    for username in mention_usernames:
        user = db.query(User).filter(
            (User.name == username) | (User.email.ilike(f"{username}%"))
        ).first()

        if user:
            mention = TeamMessageMention(
                message_id=message.id,
                mentioned_user_id=user.id,
                mentioned_username=username,
                is_read=False
            )
            db.add(mention)
            mentions.append(mention)

    return mentions


# ============================================================================
# Channel Endpoints
# ============================================================================

@router.post("/channels", response_model=ChannelResponse)
async def create_channel(
    request: CreateChannelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new messaging channel"""

    # Check if entity channel already exists
    if request.entity_type and request.entity_id:
        existing = db.query(TeamChannel).filter(
            TeamChannel.entity_type == request.entity_type,
            TeamChannel.entity_id == request.entity_id
        ).first()
        if existing:
            # Return existing channel
            member_count = db.execute(
                select(func.count()).select_from(channel_members).where(
                    channel_members.c.channel_id == existing.id
                )
            ).scalar() or 0
            return ChannelResponse(
                id=existing.id,
                name=existing.name,
                description=existing.description,
                channel_type=existing.channel_type,
                entity_type=existing.entity_type,
                entity_id=existing.entity_id,
                is_private=existing.is_private,
                is_archived=existing.is_archived,
                created_by_id=existing.created_by_id,
                created_at=existing.created_at,
                last_message_at=existing.last_message_at,
                message_count=existing.message_count,
                member_count=member_count,
            )

    # Create channel
    channel = TeamChannel(
        name=request.name,
        description=request.description,
        channel_type=request.channel_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        is_private=request.is_private,
        created_by_id=current_user.id,
    )
    db.add(channel)
    db.flush()

    # Add creator as member/owner
    db.execute(
        channel_members.insert().values(
            channel_id=channel.id,
            user_id=current_user.id,
            role='owner',
            joined_at=datetime.utcnow()
        )
    )

    # Add initial members
    for member_id in request.member_ids:
        if member_id != current_user.id:
            db.execute(
                channel_members.insert().values(
                    channel_id=channel.id,
                    user_id=member_id,
                    role='member',
                    joined_at=datetime.utcnow()
                )
            )

    db.commit()
    db.refresh(channel)

    member_count = 1 + len(request.member_ids)

    logger.info(f"Channel created: id={channel.id}, name={channel.name}, by={current_user.email}")

    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        description=channel.description,
        channel_type=channel.channel_type,
        entity_type=channel.entity_type,
        entity_id=channel.entity_id,
        is_private=channel.is_private,
        is_archived=channel.is_archived,
        created_by_id=channel.created_by_id,
        created_at=channel.created_at,
        last_message_at=channel.last_message_at,
        message_count=channel.message_count,
        member_count=member_count,
    )


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    channel_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List channels the user is a member of"""

    # Base query - channels user is a member of
    query = db.query(TeamChannel).join(
        channel_members,
        and_(
            channel_members.c.channel_id == TeamChannel.id,
            channel_members.c.user_id == current_user.id
        )
    )

    # Apply filters
    if not include_archived:
        query = query.filter(TeamChannel.is_archived == False)
    if channel_type:
        query = query.filter(TeamChannel.channel_type == channel_type)
    if entity_type:
        query = query.filter(TeamChannel.entity_type == entity_type)

    channels = query.order_by(TeamChannel.last_message_at.desc().nullslast()).all()

    # Get member counts and unread counts
    results = []
    for channel in channels:
        member_count = db.execute(
            select(func.count()).select_from(channel_members).where(
                channel_members.c.channel_id == channel.id
            )
        ).scalar() or 0

        # Get unread count
        last_read = db.query(TeamMessageRead).filter(
            TeamMessageRead.channel_id == channel.id,
            TeamMessageRead.user_id == current_user.id
        ).first()

        unread_count = 0
        if last_read and last_read.last_read_message_id:
            unread_count = db.query(func.count(TeamMessage.id)).filter(
                TeamMessage.channel_id == channel.id,
                TeamMessage.id > last_read.last_read_message_id,
                TeamMessage.is_deleted == False
            ).scalar() or 0
        elif not last_read:
            unread_count = channel.message_count

        results.append(ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            channel_type=channel.channel_type,
            entity_type=channel.entity_type,
            entity_id=channel.entity_id,
            is_private=channel.is_private,
            is_archived=channel.is_archived,
            created_by_id=channel.created_by_id,
            created_at=channel.created_at,
            last_message_at=channel.last_message_at,
            message_count=channel.message_count,
            member_count=member_count,
            unread_count=unread_count,
        ))

    return ChannelListResponse(channels=results, total_count=len(results))


@router.get("/channels/entity/{entity_type}/{entity_id}", response_model=ChannelResponse)
async def get_or_create_entity_channel(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get or create a channel for an entity (auto-join)"""

    # Check if channel exists
    channel = db.query(TeamChannel).filter(
        TeamChannel.entity_type == entity_type,
        TeamChannel.entity_id == entity_id
    ).first()

    if not channel:
        # Create channel
        entity_names = {
            'purchase_order': 'PO',
            'transfer_order': 'TO',
            'supply_plan': 'Supply Plan',
            'demand_plan': 'Demand Plan',
            'recommendation': 'Recommendation',
            'invoice': 'Invoice',
        }
        prefix = entity_names.get(entity_type, entity_type.replace('_', ' ').title())

        channel = TeamChannel(
            name=f"{prefix} #{entity_id} Discussion",
            description=f"Team discussion for {prefix} {entity_id}",
            channel_type="entity",
            entity_type=entity_type,
            entity_id=entity_id,
            is_private=False,
            created_by_id=current_user.id,
        )
        db.add(channel)
        db.flush()

    # Check if user is a member
    is_member = db.execute(
        select(func.count()).select_from(channel_members).where(
            and_(
                channel_members.c.channel_id == channel.id,
                channel_members.c.user_id == current_user.id
            )
        )
    ).scalar()

    if not is_member:
        # Auto-join user to entity channel
        db.execute(
            channel_members.insert().values(
                channel_id=channel.id,
                user_id=current_user.id,
                role='member',
                joined_at=datetime.utcnow()
            )
        )

    db.commit()
    db.refresh(channel)

    member_count = db.execute(
        select(func.count()).select_from(channel_members).where(
            channel_members.c.channel_id == channel.id
        )
    ).scalar() or 0

    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        description=channel.description,
        channel_type=channel.channel_type,
        entity_type=channel.entity_type,
        entity_id=channel.entity_id,
        is_private=channel.is_private,
        is_archived=channel.is_archived,
        created_by_id=channel.created_by_id,
        created_at=channel.created_at,
        last_message_at=channel.last_message_at,
        message_count=channel.message_count,
        member_count=member_count,
    )


@router.post("/channels/{channel_id}/join")
async def join_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Join a channel"""
    channel = db.get(TeamChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.is_private:
        raise HTTPException(status_code=403, detail="Cannot join private channel without invitation")

    # Check if already a member
    is_member = db.execute(
        select(func.count()).select_from(channel_members).where(
            and_(
                channel_members.c.channel_id == channel_id,
                channel_members.c.user_id == current_user.id
            )
        )
    ).scalar()

    if not is_member:
        db.execute(
            channel_members.insert().values(
                channel_id=channel_id,
                user_id=current_user.id,
                role='member',
                joined_at=datetime.utcnow()
            )
        )
        db.commit()

    return {"success": True, "message": "Joined channel"}


@router.post("/channels/{channel_id}/leave")
async def leave_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Leave a channel"""
    db.execute(
        channel_members.delete().where(
            and_(
                channel_members.c.channel_id == channel_id,
                channel_members.c.user_id == current_user.id
            )
        )
    )
    db.commit()

    return {"success": True, "message": "Left channel"}


# ============================================================================
# Message Endpoints
# ============================================================================

@router.post("/channels/{channel_id}/messages", response_model=MessageResponse)
async def send_message(
    channel_id: int,
    request: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a message to a channel"""

    channel = db.get(TeamChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Check membership
    is_member = db.execute(
        select(func.count()).select_from(channel_members).where(
            and_(
                channel_members.c.channel_id == channel_id,
                channel_members.c.user_id == current_user.id
            )
        )
    ).scalar()

    if not is_member:
        raise HTTPException(status_code=403, detail="You must join the channel to send messages")

    # Extract mentions
    mention_usernames = extract_mentions(request.content)
    content_html = render_content_html(request.content, mention_usernames)

    # Determine thread root
    thread_root_id = None
    if request.parent_id:
        parent = db.get(TeamMessage, request.parent_id)
        if parent:
            thread_root_id = parent.thread_root_id or parent.id
            # Update parent reply count
            parent.reply_count += 1
        else:
            raise HTTPException(status_code=404, detail="Parent message not found")

    # Create message
    message = TeamMessage(
        channel_id=channel_id,
        sender_id=current_user.id,
        sender_name=current_user.name or current_user.email,
        parent_id=request.parent_id,
        thread_root_id=thread_root_id,
        content=request.content,
        content_html=content_html,
        message_type=request.message_type,
        is_urgent=request.is_urgent,
    )
    db.add(message)
    db.flush()

    # Set thread_root_id for root messages
    if not request.parent_id:
        message.thread_root_id = message.id

    # Create mention records
    create_mention_records(db, message, mention_usernames)

    # Update channel stats
    channel.message_count += 1
    channel.last_message_at = datetime.utcnow()

    db.commit()
    db.refresh(message)

    logger.info(f"Message sent: channel={channel_id}, sender={current_user.email}")

    return MessageResponse(
        id=message.id,
        channel_id=message.channel_id,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        parent_id=message.parent_id,
        thread_root_id=message.thread_root_id,
        content=message.content,
        content_html=message.content_html,
        message_type=message.message_type,
        is_edited=message.is_edited,
        is_pinned=message.is_pinned,
        is_urgent=message.is_urgent,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        reply_count=message.reply_count,
        mentions=[m.to_dict() for m in message.mentions],
    )


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def get_messages(
    channel_id: int,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[int] = Query(None),
    after_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get messages from a channel"""

    channel = db.get(TeamChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Build query for root messages only (no parent)
    query = db.query(TeamMessage).filter(
        TeamMessage.channel_id == channel_id,
        TeamMessage.is_deleted == False,
        TeamMessage.parent_id.is_(None)
    )

    # Pagination
    if before_id:
        query = query.filter(TeamMessage.id < before_id)
    if after_id:
        query = query.filter(TeamMessage.id > after_id)

    # Order by newest first
    query = query.order_by(TeamMessage.created_at.desc())

    total_count = query.count()
    messages = query.limit(limit + 1).all()

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Update read status
    if messages:
        read_record = db.query(TeamMessageRead).filter(
            TeamMessageRead.channel_id == channel_id,
            TeamMessageRead.user_id == current_user.id
        ).first()

        newest_message_id = max(m.id for m in messages)

        if read_record:
            if not read_record.last_read_message_id or read_record.last_read_message_id < newest_message_id:
                read_record.last_read_message_id = newest_message_id
                read_record.last_read_at = datetime.utcnow()
        else:
            read_record = TeamMessageRead(
                channel_id=channel_id,
                user_id=current_user.id,
                last_read_message_id=newest_message_id
            )
            db.add(read_record)

        db.commit()

    return MessageListResponse(
        messages=[
            MessageResponse(
                id=m.id,
                channel_id=m.channel_id,
                sender_id=m.sender_id,
                sender_name=m.sender_name,
                parent_id=m.parent_id,
                thread_root_id=m.thread_root_id,
                content=m.content,
                content_html=m.content_html,
                message_type=m.message_type,
                is_edited=m.is_edited,
                is_pinned=m.is_pinned,
                is_urgent=m.is_urgent,
                is_deleted=m.is_deleted,
                created_at=m.created_at,
                reply_count=m.reply_count,
                mentions=[men.to_dict() for men in m.mentions] if m.mentions else [],
                replies=[r.to_dict() for r in m.replies if not r.is_deleted][:3] if m.replies else None,
            )
            for m in messages
        ],
        total_count=total_count,
        has_more=has_more,
    )


@router.get("/channels/{channel_id}/messages/{message_id}/thread", response_model=List[MessageResponse])
async def get_message_thread(
    channel_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all replies in a message thread"""

    # Get root message
    root = db.get(TeamMessage, message_id)
    if not root:
        raise HTTPException(status_code=404, detail="Message not found")

    # Get thread replies
    thread_root = root.thread_root_id or root.id
    replies = db.query(TeamMessage).filter(
        TeamMessage.thread_root_id == thread_root,
        TeamMessage.id != thread_root,
        TeamMessage.is_deleted == False
    ).order_by(TeamMessage.created_at.asc()).all()

    return [
        MessageResponse(
            id=m.id,
            channel_id=m.channel_id,
            sender_id=m.sender_id,
            sender_name=m.sender_name,
            parent_id=m.parent_id,
            thread_root_id=m.thread_root_id,
            content=m.content,
            content_html=m.content_html,
            message_type=m.message_type,
            is_edited=m.is_edited,
            is_pinned=m.is_pinned,
            is_urgent=m.is_urgent,
            is_deleted=m.is_deleted,
            created_at=m.created_at,
            reply_count=m.reply_count,
            mentions=[men.to_dict() for men in m.mentions] if m.mentions else [],
        )
        for m in replies
    ]


@router.delete("/channels/{channel_id}/messages/{message_id}")
async def delete_message(
    channel_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft delete a message"""
    message = db.query(TeamMessage).filter(
        TeamMessage.id == message_id,
        TeamMessage.channel_id == channel_id
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")

    message.is_deleted = True
    message.deleted_at = datetime.utcnow()

    db.commit()

    return {"success": True, "message": "Message deleted"}


@router.post("/channels/{channel_id}/messages/{message_id}/pin")
async def pin_message(
    channel_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Pin/unpin a message"""
    message = db.query(TeamMessage).filter(
        TeamMessage.id == message_id,
        TeamMessage.channel_id == channel_id
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.is_pinned = not message.is_pinned
    db.commit()

    return {"success": True, "is_pinned": message.is_pinned}


# ============================================================================
# Mention Endpoints
# ============================================================================

@router.get("/mentions/unread")
async def get_unread_mentions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get unread @mentions for the current user"""
    mentions = db.query(TeamMessageMention).filter(
        TeamMessageMention.mentioned_user_id == current_user.id,
        TeamMessageMention.is_read == False
    ).all()

    return {
        "mentions": [m.to_dict() for m in mentions],
        "unread_count": len(mentions)
    }


@router.post("/mentions/{mention_id}/read")
async def mark_mention_read(
    mention_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a mention as read"""
    mention = db.query(TeamMessageMention).filter(
        TeamMessageMention.id == mention_id,
        TeamMessageMention.mentioned_user_id == current_user.id
    ).first()

    if not mention:
        raise HTTPException(status_code=404, detail="Mention not found")

    mention.is_read = True
    mention.read_at = datetime.utcnow()
    db.commit()

    return {"success": True}


# ============================================================================
# Mark Read Endpoint
# ============================================================================

@router.post("/channels/{channel_id}/mark-read")
async def mark_channel_read(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all messages in a channel as read"""
    channel = db.get(TeamChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Get the latest message ID in the channel
    latest_message = db.query(TeamMessage).filter(
        TeamMessage.channel_id == channel_id,
        TeamMessage.is_deleted == False
    ).order_by(TeamMessage.id.desc()).first()

    if not latest_message:
        return {"success": True, "message": "No messages to mark as read"}

    # Update or create read record
    read_record = db.query(TeamMessageRead).filter(
        TeamMessageRead.channel_id == channel_id,
        TeamMessageRead.user_id == current_user.id
    ).first()

    if read_record:
        read_record.last_read_message_id = latest_message.id
        read_record.last_read_at = datetime.utcnow()
    else:
        read_record = TeamMessageRead(
            channel_id=channel_id,
            user_id=current_user.id,
            last_read_message_id=latest_message.id
        )
        db.add(read_record)

    db.commit()

    logger.info(f"Channel {channel_id} marked as read by user {current_user.id}")
    return {"success": True, "last_read_message_id": latest_message.id}


# ============================================================================
# Edit Message Endpoint
# ============================================================================

class EditMessageRequest(BaseModel):
    """Request to edit a message"""
    content: str = Field(..., min_length=1, max_length=10000)


@router.put("/channels/{channel_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    channel_id: int,
    message_id: int,
    request: EditMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit a message"""
    message = db.query(TeamMessage).filter(
        TeamMessage.id == message_id,
        TeamMessage.channel_id == channel_id
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own messages")

    if message.is_deleted:
        raise HTTPException(status_code=400, detail="Cannot edit a deleted message")

    # Extract new mentions
    mention_usernames = extract_mentions(request.content)
    content_html = render_content_html(request.content, mention_usernames)

    # Update message
    message.content = request.content
    message.content_html = content_html
    message.is_edited = True
    message.edited_at = datetime.utcnow()

    # Update mentions - remove old ones and add new ones
    db.query(TeamMessageMention).filter(
        TeamMessageMention.message_id == message_id
    ).delete()

    create_mention_records(db, message, mention_usernames)

    db.commit()
    db.refresh(message)

    logger.info(f"Message {message_id} edited by user {current_user.id}")

    return MessageResponse(
        id=message.id,
        channel_id=message.channel_id,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        parent_id=message.parent_id,
        thread_root_id=message.thread_root_id,
        content=message.content,
        content_html=message.content_html,
        message_type=message.message_type,
        is_edited=message.is_edited,
        is_pinned=message.is_pinned,
        is_urgent=message.is_urgent,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        reply_count=message.reply_count,
        mentions=[m.to_dict() for m in message.mentions] if message.mentions else [],
    )

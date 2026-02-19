from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...models import User
from ...models.user import UserTypeEnum
from ...schemas.group import Group as GroupSchema, GroupCreate, GroupUpdate, GroupSummary
from ...services.group_service import GroupService
from ...services.rbac_service import RBACService
from ...core.security import get_current_active_user

router = APIRouter()

def get_group_service(db: Session = Depends(get_db)) -> GroupService:
    return GroupService(db)

@router.get("/my", response_model=Optional[GroupSummary])
async def get_my_group(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the current user's group with mode information.

    Returns None if the user is not assigned to a group.
    This endpoint is used by the frontend to determine navigation mode.
    """
    from ...models.group import Group

    if not current_user.group_id:
        return None

    stmt = select(Group).filter(Group.id == current_user.group_id)
    result = await db.execute(stmt)
    group = result.scalar_one_or_none()

    return group


@router.get("/", response_model=List[GroupSchema])
async def list_groups(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    from ...models.group import Group

    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Only SYSTEM_ADMIN sees all groups; GROUP_ADMIN sees only their group
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        stmt = select(Group).options(joinedload(Group.admin))
        result = await db.execute(stmt)
        return result.scalars().unique().all()

    is_group_admin = user_type == UserTypeEnum.GROUP_ADMIN

    if is_group_admin and current_user.group_id:
        stmt = select(Group).options(joinedload(Group.admin)).filter(Group.id == current_user.group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()
        if group:
            return [group]
        raise HTTPException(status_code=404, detail="Group not found")

    # Regular users can see their own group if assigned
    if current_user.group_id:
        stmt = select(Group).options(joinedload(Group.admin)).filter(Group.id == current_user.group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()
        if group:
            return [group]

    raise HTTPException(status_code=403, detail="Not enough permissions")

@router.post("/", response_model=GroupSchema, status_code=status.HTTP_201_CREATED)
def create_group(group_in: GroupCreate, group_service: GroupService = Depends(get_group_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return group_service.create_group(group_in)

@router.put("/{group_id}", response_model=GroupSchema)
def update_group(group_id: int, group_update: GroupUpdate, group_service: GroupService = Depends(get_group_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return group_service.update_group(group_id, group_update)

@router.delete("/{group_id}", response_model=dict)
def delete_group(group_id: int, group_service: GroupService = Depends(get_group_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return group_service.delete_group(group_id)

@router.get("/{group_id}/users")
async def get_group_users(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all users in a specific group.

    Group admins can only view their own group's users.
    System admins can view any group's users.
    """
    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Check permissions
    is_system_admin = user_type == UserTypeEnum.SYSTEM_ADMIN
    is_group_admin = user_type == UserTypeEnum.GROUP_ADMIN

    if not is_system_admin and not is_group_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Group admins can only view their own group
    if is_group_admin and current_user.group_id != group_id:
        raise HTTPException(status_code=403, detail="You can only view users in your own group")

    # Query users in the group
    stmt = select(User).filter(User.group_id == group_id)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "user_type": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
            "is_active": user.is_active,
            "group_id": user.group_id,
        }
        for user in users
    ]

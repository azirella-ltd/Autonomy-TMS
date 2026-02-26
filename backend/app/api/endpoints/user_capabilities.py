"""
API endpoints for managing user capabilities and roles.
Allows group admins to assign capabilities to users within their customer organization.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_sync_db
from app.api import deps
from app.models.user import User, UserTypeEnum as UserType
from app.services.capability_service import (
    get_user_capabilities_list,
    user_has_capability,
)
from app.core.capabilities import Capability

router = APIRouter(prefix="/users", tags=["user-capabilities"])


class UpdateUserCapabilitiesRequest(BaseModel):
    """Request model for updating user capabilities."""
    user_type: str
    capabilities: List[str]


@router.put("/{user_id}/capabilities")
def update_user_capabilities(
    user_id: int,
    request: UpdateUserCapabilitiesRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Update user's role and custom capabilities.

    Group admins can update users within their customer organization.
    System admins can update any user (except other system admins).
    """
    # Check if current user has permission to manage capabilities
    if not user_has_capability(current_user, Capability.MANAGE_PERMISSIONS, db):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to manage user capabilities"
        )

    # Get the target user
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Tenant admins can only manage users in their customer organization
    if current_user.user_type == UserType.TENANT_ADMIN:
        if not current_user.tenant_id or target_user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You can only manage users within your group"
            )

    # Prevent modifying system admin users (unless you are system admin)
    if target_user.user_type == UserType.SYSTEM_ADMIN:
        if current_user.user_type != UserType.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify system administrator capabilities"
            )

    # Validate user_type
    try:
        new_user_type = UserType[request.user_type.upper()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid user type: {request.user_type}"
        )

    # Prevent group admins from creating system admins
    if new_user_type == UserType.SYSTEM_ADMIN:
        if current_user.user_type != UserType.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Only system administrators can assign system admin role"
            )

    # Update user type
    target_user.user_type = new_user_type

    # Store custom capabilities (if we have a capabilities field)
    # For now, capabilities are derived from user_type
    # In future, we can add a JSON field to store custom capabilities

    db.commit()
    db.refresh(target_user)

    return {
        "success": True,
        "message": "User capabilities updated successfully",
        "user": {
            "id": target_user.id,
            "email": target_user.email,
            "user_type": target_user.user_type.value,
            "capabilities": get_user_capabilities_list(target_user, db),
        }
    }


@router.get("/{user_id}/capabilities")
def get_user_capabilities(
    user_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get a user's capabilities.

    Tenant admins can view users in their customer organization.
    System admins can view any user.
    """
    # Check if current user has permission to view capabilities
    if not user_has_capability(current_user, Capability.VIEW_USERS, db):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view user capabilities"
        )

    # Get the target user
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Tenant admins can only view users in their customer organization
    if current_user.user_type == UserType.TENANT_ADMIN:
        if not current_user.tenant_id or target_user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view users within your group"
            )

    return {
        "id": target_user.id,
        "email": target_user.email,
        "full_name": target_user.full_name,
        "user_type": target_user.user_type.value,
        "capabilities": get_user_capabilities_list(target_user, db),
        "is_active": target_user.is_active,
    }


@router.get("")
def list_group_users(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    List all users that the current user can manage.

    Tenant admins see users in their customer organization.
    System admins see all users.
    """
    # Check if current user has permission to view users
    if not user_has_capability(current_user, Capability.VIEW_USERS, db):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view users"
        )

    # Build query based on user type
    query = db.query(User)
    if current_user.user_type == UserType.TENANT_ADMIN:
        # Tenant admins only see users in their tenant organization
        if not current_user.tenant_id:
            return {"users": []}
        query = query.filter(User.tenant_id == current_user.tenant_id)

    # Execute query
    users = query.all()

    return {
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "user_type": user.user_type.value,
                "capabilities": get_user_capabilities_list(user, db),
                "is_active": user.is_active,
                "tenant_id": user.tenant_id,
            }
            for user in users
        ]
    }

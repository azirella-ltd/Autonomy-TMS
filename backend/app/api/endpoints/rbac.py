"""
RBAC Management API Endpoints

Provides CRUD operations for role-based access control:
- Permission management
- Role management
- Role-permission assignments
- User-role assignments
"""

from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.user import User, UserTypeEnum
from app.models.rbac import (
    Permission, Role, RolePermissionGrant, UserRoleAssignment,
    role_permissions, user_roles
)
from app.core.deps import get_current_active_superuser
from app.api.deps import get_current_user
from app.core.permissions import PermissionChecker, RequirePermission
from app.middleware.tenant_middleware import get_current_tenant

router = APIRouter()


# ==================== Request/Response Models ====================

class PermissionPublic(BaseModel):
    """Public permission information"""
    id: int
    name: str
    resource: str
    action: str
    description: Optional[str]
    category: Optional[str]
    is_system: bool

    class Config:
        from_attributes = True


class PermissionCreate(BaseModel):
    """Create new permission"""
    name: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9._-]+$")
    resource: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)


class RolePublic(BaseModel):
    """Public role information"""
    id: int
    name: str
    slug: str
    description: Optional[str]
    is_system: bool
    tenant_id: Optional[int]
    permission_count: int
    user_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Create new role"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    description: Optional[str] = None
    tenant_id: Optional[int] = None
    permission_ids: List[int] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    """Update role"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class RolePermissionAssign(BaseModel):
    """Assign permissions to role"""
    permission_ids: List[int] = Field(..., min_items=1)


class UserRoleAssign(BaseModel):
    """Assign role to user"""
    user_id: int
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class UserRolePublic(BaseModel):
    """User role assignment information"""
    user_id: int
    role_id: int
    assigned_at: datetime
    expires_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


# ==================== Permission Endpoints ====================

@router.get("/permissions", response_model=List[PermissionPublic])
async def list_permissions(
    skip: int = 0,
    limit: int = 100,
    resource: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all permissions

    Can be filtered by resource or category
    """
    query = select(Permission)

    if resource:
        query = query.where(Permission.resource == resource)
    if category:
        query = query.where(Permission.category == category)

    query = query.offset(skip).limit(limit).order_by(Permission.category, Permission.resource, Permission.action)

    result = await db.execute(query)
    permissions = result.scalars().all()

    return permissions


@router.post("/permissions", response_model=PermissionPublic, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission_data: PermissionCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new permission (system admin only)

    Creates a new permission in the system
    """
    # Check if permission already exists
    result = await db.execute(
        select(Permission).where(Permission.name == permission_data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Permission '{permission_data.name}' already exists"
        )

    # Create permission
    permission = Permission(**permission_data.dict(), is_system=False)

    db.add(permission)
    await db.commit()
    await db.refresh(permission)

    return permission


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete permission (system admin only)

    Cannot delete system permissions
    """
    result = await db.execute(
        select(Permission).where(Permission.id == permission_id)
    )
    permission = result.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission {permission_id} not found"
        )

    if permission.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system permission"
        )

    await db.delete(permission)
    await db.commit()


# ==================== Role Endpoints ====================

@router.get("/roles", response_model=List[RolePublic])
async def list_roles(
    skip: int = 0,
    limit: int = 100,
    tenant_id: Optional[int] = None,
    include_global: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List roles

    Can be filtered by tenant. Global roles are included by default.
    """
    query = select(Role)

    # Filter by tenant
    if tenant_id is not None:
        if include_global:
            # Get tenant-specific roles and global roles
            query = query.where(
                (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))
            )
        else:
            # Get only tenant-specific roles
            query = query.where(Role.tenant_id == tenant_id)
    elif not include_global:
        # Get only non-global roles
        query = query.where(Role.tenant_id.is_not(None))

    query = query.offset(skip).limit(limit).order_by(Role.name)

    result = await db.execute(query)
    roles = result.scalars().all()

    # Compute counts for each role
    roles_with_counts = []
    for role in roles:
        # Count permissions
        perm_count = await db.scalar(
            select(func.count()).select_from(role_permissions).where(role_permissions.c.role_id == role.id)
        )
        # Count users
        user_count = await db.scalar(
            select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
        )

        role_dict = {
            "id": role.id,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "is_system": role.is_system,
            "tenant_id": role.tenant_id,
            "permission_count": perm_count or 0,
            "user_count": user_count or 0,
            "created_at": role.created_at
        }
        roles_with_counts.append(RolePublic(**role_dict))

    return roles_with_counts


@router.post("/roles", response_model=RolePublic, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new role (system admin only)

    Can optionally assign permissions during creation
    """
    # Check if role slug already exists for this tenant
    result = await db.execute(
        select(Role).where(
            Role.slug == role_data.slug,
            Role.tenant_id == role_data.tenant_id
        )
    )
    if result.scalar_one_or_none():
        scope = f"tenant {role_data.tenant_id}" if role_data.tenant_id else "global"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role with slug '{role_data.slug}' already exists in {scope} scope"
        )

    # Create role
    role = Role(
        name=role_data.name,
        slug=role_data.slug,
        description=role_data.description,
        tenant_id=role_data.tenant_id,
        is_system=False,
        created_by=current_user.id
    )

    db.add(role)
    await db.flush()  # Get role.id

    # Assign permissions if provided
    if role_data.permission_ids:
        for perm_id in role_data.permission_ids:
            # Verify permission exists
            result = await db.execute(select(Permission).where(Permission.id == perm_id))
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Permission {perm_id} not found"
                )

            # Add to association table
            await db.execute(
                role_permissions.insert().values(
                    role_id=role.id,
                    permission_id=perm_id,
                    granted=True
                )
            )

            # Create audit record
            grant = RolePermissionGrant(
                role_id=role.id,
                permission_id=perm_id,
                granted=True,
                granted_by=current_user.id
            )
            db.add(grant)

    await db.commit()
    await db.refresh(role)

    # Get counts
    perm_count = len(role_data.permission_ids)
    user_count = 0

    return RolePublic(
        id=role.id,
        name=role.name,
        slug=role.slug,
        description=role.description,
        is_system=role.is_system,
        tenant_id=role.tenant_id,
        permission_count=perm_count,
        user_count=user_count,
        created_at=role.created_at
    )


@router.get("/roles/{role_id}", response_model=RolePublic)
async def get_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get role details"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    # Get counts
    perm_count = await db.scalar(
        select(func.count()).select_from(role_permissions).where(role_permissions.c.role_id == role.id)
    )
    user_count = await db.scalar(
        select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
    )

    return RolePublic(
        id=role.id,
        name=role.name,
        slug=role.slug,
        description=role.description,
        is_system=role.is_system,
        tenant_id=role.tenant_id,
        permission_count=perm_count or 0,
        user_count=user_count or 0,
        created_at=role.created_at
    )


@router.put("/roles/{role_id}", response_model=RolePublic)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Update role (system admin only)"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system role"
        )

    # Update fields
    for field, value in role_data.dict(exclude_unset=True).items():
        setattr(role, field, value)

    role.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(role)

    # Get counts
    perm_count = await db.scalar(
        select(func.count()).select_from(role_permissions).where(role_permissions.c.role_id == role.id)
    )
    user_count = await db.scalar(
        select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
    )

    return RolePublic(
        id=role.id,
        name=role.name,
        slug=role.slug,
        description=role.description,
        is_system=role.is_system,
        tenant_id=role.tenant_id,
        permission_count=perm_count or 0,
        user_count=user_count or 0,
        created_at=role.created_at
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete role (system admin only)

    Cannot delete system roles
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system role"
        )

    await db.delete(role)
    await db.commit()


# ==================== Role-Permission Management ====================

@router.get("/roles/{role_id}/permissions", response_model=List[PermissionPublic])
async def get_role_permissions(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all permissions assigned to a role"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    # Get permissions
    result = await db.execute(
        select(Permission)
        .join(role_permissions)
        .where(role_permissions.c.role_id == role_id)
    )
    permissions = result.scalars().all()

    return permissions


@router.post("/roles/{role_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def assign_permissions_to_role(
    role_id: int,
    assignment: RolePermissionAssign,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Assign permissions to role (system admin only)

    Adds permissions to the role without removing existing ones
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system role permissions"
        )

    # Assign each permission
    for perm_id in assignment.permission_ids:
        # Verify permission exists
        result = await db.execute(select(Permission).where(Permission.id == perm_id))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Permission {perm_id} not found"
            )

        # Check if already assigned
        result = await db.execute(
            select(role_permissions).where(
                and_(
                    role_permissions.c.role_id == role_id,
                    role_permissions.c.permission_id == perm_id
                )
            )
        )
        if result.first():
            continue  # Already assigned, skip

        # Add to association table
        await db.execute(
            role_permissions.insert().values(
                role_id=role_id,
                permission_id=perm_id,
                granted=True
            )
        )

        # Create audit record
        grant = RolePermissionGrant(
            role_id=role_id,
            permission_id=perm_id,
            granted=True,
            granted_by=current_user.id
        )
        db.add(grant)

    await db.commit()


@router.delete("/roles/{role_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove permission from role (system admin only)
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system role permissions"
        )

    # Remove from association table
    await db.execute(
        role_permissions.delete().where(
            and_(
                role_permissions.c.role_id == role_id,
                role_permissions.c.permission_id == permission_id
            )
        )
    )

    # Create audit record (revocation)
    grant = RolePermissionGrant(
        role_id=role_id,
        permission_id=permission_id,
        granted=False,
        granted_by=current_user.id,
        revoked_at=datetime.utcnow(),
        revoked_by=current_user.id
    )
    db.add(grant)

    await db.commit()


# ==================== User-Role Management ====================

@router.get("/users/{user_id}/roles", response_model=List[RolePublic])
async def get_user_roles(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all roles assigned to a user

    Users can view their own roles. Admins can view any user's roles.
    """
    # Check permission
    if user_id != current_user.id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view other users' roles"
        )

    # Get roles
    result = await db.execute(
        select(Role)
        .join(user_roles)
        .where(user_roles.c.user_id == user_id)
    )
    roles = result.scalars().all()

    # Get counts for each role
    roles_with_counts = []
    for role in roles:
        perm_count = await db.scalar(
            select(func.count()).select_from(role_permissions).where(role_permissions.c.role_id == role.id)
        )
        user_count = await db.scalar(
            select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
        )

        role_dict = {
            "id": role.id,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "is_system": role.is_system,
            "tenant_id": role.tenant_id,
            "permission_count": perm_count or 0,
            "user_count": user_count or 0,
            "created_at": role.created_at
        }
        roles_with_counts.append(RolePublic(**role_dict))

    return roles_with_counts


@router.post("/roles/{role_id}/users", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_to_user(
    role_id: int,
    assignment: UserRoleAssign,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Assign role to user (system admin only)
    """
    # Verify role exists
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role {role_id} not found"
        )

    # Verify user exists
    result = await db.execute(select(User).where(User.id == assignment.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {assignment.user_id} not found"
        )

    # Check if already assigned
    result = await db.execute(
        select(user_roles).where(
            and_(
                user_roles.c.user_id == assignment.user_id,
                user_roles.c.role_id == role_id
            )
        )
    )
    if result.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {assignment.user_id} already has role {role_id}"
        )

    # Calculate expiration
    expires_at = None
    if assignment.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=assignment.expires_in_days)

    # Add to association table
    await db.execute(
        user_roles.insert().values(
            user_id=assignment.user_id,
            role_id=role_id,
            assigned_by=current_user.id,
            expires_at=expires_at
        )
    )

    # Create audit record
    user_assignment = UserRoleAssignment(
        user_id=assignment.user_id,
        role_id=role_id,
        assigned_by=current_user.id,
        expires_at=expires_at
    )
    db.add(user_assignment)

    await db.commit()


@router.delete("/roles/{role_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_user(
    role_id: int,
    user_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove role from user (system admin only)
    """
    # Remove from association table
    result = await db.execute(
        user_roles.delete().where(
            and_(
                user_roles.c.user_id == user_id,
                user_roles.c.role_id == role_id
            )
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} does not have role {role_id}"
        )

    # Update audit records (mark as revoked)
    result = await db.execute(
        select(UserRoleAssignment).where(
            and_(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.role_id == role_id,
                UserRoleAssignment.revoked_at.is_(None)
            )
        )
    )
    assignments = result.scalars().all()

    for assignment in assignments:
        assignment.revoked_at = datetime.utcnow()
        assignment.revoked_by = current_user.id

    await db.commit()

"""
Permission System

Provides permission checking and enforcement:
- Permission checking for users
- Permission decorators for endpoints
- Role-based access control helpers
"""

from typing import Optional, List, Callable
from functools import wraps
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User, UserTypeEnum
from app.models.rbac import Permission, Role
from app.api.deps import get_current_user


class PermissionChecker:
    """Service for checking user permissions"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def user_has_permission(
        self,
        user: User,
        permission_name: str
    ) -> bool:
        """
        Check if user has a specific permission

        Args:
            user: User to check
            permission_name: Permission name (e.g., "games.create")

        Returns:
            bool: True if user has permission
        """
        # System admins have all permissions
        if user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            return True

        # Check if user has any roles with this permission
        result = await self.db.execute(
            select(Permission)
            .join(Permission.roles)
            .join(Role.users)
            .where(
                User.id == user.id,
                Permission.name == permission_name
            )
        )

        return result.scalar_one_or_none() is not None

    async def user_has_resource_action(
        self,
        user: User,
        resource: str,
        action: str
    ) -> bool:
        """
        Check if user has permission for a resource.action combination

        Args:
            user: User to check
            resource: Resource name (e.g., "games")
            action: Action name (e.g., "create")

        Returns:
            bool: True if user has permission
        """
        # System admins have all permissions
        if user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            return True

        # Check if user has any roles with this resource.action
        result = await self.db.execute(
            select(Permission)
            .join(Permission.roles)
            .join(Role.users)
            .where(
                User.id == user.id,
                Permission.resource == resource,
                Permission.action == action
            )
        )

        return result.scalar_one_or_none() is not None

    async def get_user_permissions(
        self,
        user: User
    ) -> List[Permission]:
        """
        Get all permissions for a user

        Args:
            user: User to get permissions for

        Returns:
            List of Permission objects
        """
        # System admins have all permissions
        if user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            result = await self.db.execute(select(Permission))
            return result.scalars().all()

        # Get permissions through user's roles
        result = await self.db.execute(
            select(Permission)
            .join(Permission.roles)
            .join(Role.users)
            .where(User.id == user.id)
            .distinct()
        )

        return result.scalars().all()

    async def get_user_roles(
        self,
        user: User,
        tenant_id: Optional[int] = None
    ) -> List[Role]:
        """
        Get all roles for a user

        Args:
            user: User to get roles for
            tenant_id: Optional tenant ID to filter by

        Returns:
            List of Role objects
        """
        query = select(Role).join(Role.users).where(User.id == user.id)

        if tenant_id is not None:
            # Get tenant-specific roles and global roles
            query = query.where(
                (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))
            )

        result = await self.db.execute(query)
        return result.scalars().all()


# ==================== Permission Dependency ====================

class RequirePermission:
    """
    FastAPI dependency for requiring specific permissions

    Usage:
        @router.get("/games")
        async def list_games(
            user: User = Depends(RequirePermission("games.read"))
        ):
            ...
    """

    def __init__(self, permission_name: str):
        self.permission_name = permission_name

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        """
        Check if user has required permission

        Raises:
            HTTPException: 403 if user lacks permission
        """
        checker = PermissionChecker(db)

        if not await checker.user_has_permission(user, self.permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {self.permission_name} required"
            )

        return user


class RequireResourceAction:
    """
    FastAPI dependency for requiring resource.action permissions

    Usage:
        @router.post("/games")
        async def create_game(
            user: User = Depends(RequireResourceAction("games", "create"))
        ):
            ...
    """

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        """
        Check if user has required resource.action permission

        Raises:
            HTTPException: 403 if user lacks permission
        """
        checker = PermissionChecker(db)

        if not await checker.user_has_resource_action(user, self.resource, self.action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {self.resource}.{self.action} required"
            )

        return user


class RequireAnyPermission:
    """
    FastAPI dependency for requiring at least one of multiple permissions

    Usage:
        @router.get("/reports")
        async def view_reports(
            user: User = Depends(RequireAnyPermission(["reports.read", "reports.admin"]))
        ):
            ...
    """

    def __init__(self, permission_names: List[str]):
        self.permission_names = permission_names

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        """
        Check if user has at least one of the required permissions

        Raises:
            HTTPException: 403 if user lacks all permissions
        """
        checker = PermissionChecker(db)

        # Check each permission
        for permission_name in self.permission_names:
            if await checker.user_has_permission(user, permission_name):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: One of {self.permission_names} required"
        )


class RequireAllPermissions:
    """
    FastAPI dependency for requiring all of multiple permissions

    Usage:
        @router.delete("/games/{game_id}")
        async def delete_game(
            user: User = Depends(RequireAllPermissions(["games.read", "games.delete"]))
        ):
            ...
    """

    def __init__(self, permission_names: List[str]):
        self.permission_names = permission_names

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        """
        Check if user has all of the required permissions

        Raises:
            HTTPException: 403 if user lacks any permission
        """
        checker = PermissionChecker(db)

        # Check all permissions
        for permission_name in self.permission_names:
            if not await checker.user_has_permission(user, permission_name):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission_name} required"
                )

        return user


# ==================== Helper Functions ====================

async def check_permission(
    user: User,
    permission_name: str,
    db: AsyncSession
) -> bool:
    """
    Helper function to check if user has permission

    Args:
        user: User to check
        permission_name: Permission name
        db: Database session

    Returns:
        bool: True if user has permission
    """
    checker = PermissionChecker(db)
    return await checker.user_has_permission(user, permission_name)


async def check_resource_action(
    user: User,
    resource: str,
    action: str,
    db: AsyncSession
) -> bool:
    """
    Helper function to check if user has resource.action permission

    Args:
        user: User to check
        resource: Resource name
        action: Action name
        db: Database session

    Returns:
        bool: True if user has permission
    """
    checker = PermissionChecker(db)
    return await checker.user_has_resource_action(user, resource, action)


async def require_permission(
    user: User,
    permission_name: str,
    db: AsyncSession
) -> None:
    """
    Helper function to require permission (raises exception if denied)

    Args:
        user: User to check
        permission_name: Permission name
        db: Database session

    Raises:
        HTTPException: 403 if user lacks permission
    """
    if not await check_permission(user, permission_name, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission_name} required"
        )


async def require_resource_action(
    user: User,
    resource: str,
    action: str,
    db: AsyncSession
) -> None:
    """
    Helper function to require resource.action permission (raises exception if denied)

    Args:
        user: User to check
        resource: Resource name
        action: Action name
        db: Database session

    Raises:
        HTTPException: 403 if user lacks permission
    """
    if not await check_resource_action(user, resource, action, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {resource}.{action} required"
        )

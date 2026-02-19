"""
Audit Service

Provides comprehensive audit logging functionality:
- Log user actions
- Log resource operations
- Log administrative actions
- Query and search audit logs
- Generate audit reports
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.models.user import User
from app.models.audit_log import AuditLog, AuditAction, AuditStatus, AuditLogSummary


class AuditService:
    """Service for audit logging operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        action: AuditAction,
        user: Optional[User] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        resource_name: Optional[str] = None,
        description: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        status: AuditStatus = AuditStatus.SUCCESS,
        error_message: Optional[str] = None,
        tenant_id: Optional[int] = None,
        request: Optional[Request] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log an action to the audit trail

        Args:
            action: Type of action performed
            user: User who performed the action
            resource_type: Type of resource (e.g., "game", "user")
            resource_id: ID of the resource
            resource_name: Name of the resource (for readability)
            description: Human-readable description
            old_value: Previous state (for updates/deletes)
            new_value: New state (for creates/updates)
            changes: Specific fields that changed
            status: Success/failure status
            error_message: Error message if failed
            tenant_id: Tenant context
            request: FastAPI request object (for IP, user agent, etc.)
            extra_data: Additional context data

        Returns:
            Created AuditLog object
        """
        # Extract request context
        ip_address = None
        user_agent = None
        session_id = None
        correlation_id = None

        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get('user-agent')
            session_id = request.cookies.get('session_id')
            # Get correlation ID from request state (if set by middleware)
            correlation_id = getattr(request.state, 'correlation_id', None)

        # Extract user context
        user_id = user.id if user else None
        username = user.username if user else None
        user_email = user.email if user else None

        # Use tenant from user if not provided
        if not tenant_id and user:
            tenant_id = user.tenant_id

        # Create audit log entry
        audit_log = AuditLog(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=description,
            old_value=old_value,
            new_value=new_value,
            changes=changes,
            status=status,
            error_message=error_message,
            tenant_id=tenant_id,
            session_id=session_id,
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data
        )

        self.db.add(audit_log)
        await self.db.commit()
        await self.db.refresh(audit_log)

        return audit_log

    async def log_login(
        self,
        user: User,
        success: bool = True,
        request: Optional[Request] = None,
        error_message: Optional[str] = None
    ) -> AuditLog:
        """Log user login attempt"""
        return await self.log_action(
            action=AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED,
            user=user if success else None,
            description=f"User {user.email} logged in" if success else f"Failed login attempt for {user.email}",
            status=AuditStatus.SUCCESS if success else AuditStatus.FAILURE,
            error_message=error_message,
            request=request
        )

    async def log_logout(
        self,
        user: User,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Log user logout"""
        return await self.log_action(
            action=AuditAction.LOGOUT,
            user=user,
            description=f"User {user.email} logged out",
            request=request
        )

    async def log_create(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        new_value: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Log resource creation"""
        return await self.log_action(
            action=AuditAction.CREATE,
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=f"Created {resource_type} {resource_name or resource_id}",
            new_value=new_value,
            request=request
        )

    async def log_update(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        changes: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Log resource update"""
        return await self.log_action(
            action=AuditAction.UPDATE,
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=f"Updated {resource_type} {resource_name or resource_id}",
            old_value=old_value,
            new_value=new_value,
            changes=changes,
            request=request
        )

    async def log_delete(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
        resource_name: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Log resource deletion"""
        return await self.log_action(
            action=AuditAction.DELETE,
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=f"Deleted {resource_type} {resource_name or resource_id}",
            old_value=old_value,
            request=request
        )

    async def log_role_assignment(
        self,
        user: User,
        target_user_id: int,
        role_name: str,
        granted: bool = True,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Log role assignment or revocation"""
        action = AuditAction.ROLE_ASSIGN if granted else AuditAction.ROLE_REVOKE
        verb = "assigned" if granted else "revoked"

        return await self.log_action(
            action=action,
            user=user,
            resource_type="user",
            resource_id=target_user_id,
            description=f"{verb.capitalize()} role '{role_name}' {'to' if granted else 'from'} user {target_user_id}",
            extra_data={"role_name": role_name, "granted": granted},
            request=request
        )

    async def search_logs(
        self,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        status: Optional[AuditStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search_term: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[AuditLog], int]:
        """
        Search audit logs with filters

        Returns:
            Tuple of (logs, total_count)
        """
        query = select(AuditLog)

        # Apply filters
        filters = []

        if tenant_id is not None:
            filters.append(AuditLog.tenant_id == tenant_id)

        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)

        if action is not None:
            filters.append(AuditLog.action == action)

        if resource_type is not None:
            filters.append(AuditLog.resource_type == resource_type)

        if resource_id is not None:
            filters.append(AuditLog.resource_id == resource_id)

        if status is not None:
            filters.append(AuditLog.status == status)

        if start_date:
            filters.append(AuditLog.created_at >= start_date)

        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        if search_term:
            # Search in description, resource_name, username, user_email
            search_filter = or_(
                AuditLog.description.contains(search_term),
                AuditLog.resource_name.contains(search_term),
                AuditLog.username.contains(search_term),
                AuditLog.user_email.contains(search_term)
            )
            filters.append(search_filter)

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(AuditLog)
        if filters:
            count_query = count_query.where(and_(*filters))

        total_count = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        logs = result.scalars().all()

        return logs, total_count or 0

    async def get_user_activity(
        self,
        user_id: int,
        days: int = 30
    ) -> List[AuditLog]:
        """Get recent activity for a user"""
        start_date = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(AuditLog)
            .where(
                AuditLog.user_id == user_id,
                AuditLog.created_at >= start_date
            )
            .order_by(AuditLog.created_at.desc())
            .limit(100)
        )

        return result.scalars().all()

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: int
    ) -> List[AuditLog]:
        """Get full history for a specific resource"""
        result = await self.db.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id
            )
            .order_by(AuditLog.created_at.asc())
        )

        return result.scalars().all()

    async def get_statistics(
        self,
        tenant_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get audit log statistics

        Returns aggregate statistics for the given time period
        """
        query = select(AuditLog)

        filters = []
        if tenant_id is not None:
            filters.append(AuditLog.tenant_id == tenant_id)
        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        if filters:
            query = query.where(and_(*filters))

        # Total actions
        total_actions = await self.db.scalar(
            select(func.count()).select_from(AuditLog).where(and_(*filters)) if filters
            else select(func.count()).select_from(AuditLog)
        )

        # By status
        status_counts = {}
        for status_value in AuditStatus:
            count = await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    and_(AuditLog.status == status_value, *filters) if filters
                    else AuditLog.status == status_value
                )
            )
            status_counts[status_value.value] = count or 0

        # By action type
        action_counts = {}
        for action_value in AuditAction:
            count = await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    and_(AuditLog.action == action_value, *filters) if filters
                    else AuditLog.action == action_value
                )
            )
            if count and count > 0:
                action_counts[action_value.value] = count

        # Most active users
        user_activity = await self.db.execute(
            select(
                AuditLog.user_id,
                AuditLog.username,
                func.count(AuditLog.id).label('action_count')
            )
            .where(and_(*filters)) if filters else select(
                AuditLog.user_id,
                AuditLog.username,
                func.count(AuditLog.id).label('action_count')
            )
            .where(AuditLog.user_id.is_not(None))
            .group_by(AuditLog.user_id, AuditLog.username)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )

        most_active_users = [
            {"user_id": row.user_id, "username": row.username, "count": row.action_count}
            for row in user_activity
        ]

        return {
            "total_actions": total_actions or 0,
            "status_counts": status_counts,
            "action_counts": action_counts,
            "most_active_users": most_active_users,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            }
        }

"""
Audit Log API Endpoints

Provides audit log viewing and querying:
- Search audit logs
- View user activity
- View resource history
- Export audit logs
- Get audit statistics
"""

from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import csv
import io

from app.db.session import get_db
from app.models.user import User, UserTypeEnum
from app.models.audit_log import AuditLog, AuditAction, AuditStatus
from app.services.audit_service import AuditService
from app.core.deps import get_current_active_superuser
from app.api.deps import get_current_user
from app.core.permissions import RequirePermission
from app.middleware.tenant_middleware import get_current_tenant

router = APIRouter()


# ==================== Request/Response Models ====================

class AuditLogPublic(BaseModel):
    """Public audit log information"""
    id: int
    user_id: Optional[int]
    username: Optional[str]
    user_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    resource_name: Optional[str]
    description: Optional[str]
    status: str
    tenant_id: Optional[int]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogDetail(BaseModel):
    """Detailed audit log information"""
    id: int
    user_id: Optional[int]
    username: Optional[str]
    user_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    resource_name: Optional[str]
    description: Optional[str]
    old_value: Optional[dict]
    new_value: Optional[dict]
    changes: Optional[dict]
    status: str
    error_message: Optional[str]
    tenant_id: Optional[int]
    session_id: Optional[str]
    correlation_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    extra_data: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogSearchResponse(BaseModel):
    """Search response with pagination"""
    logs: List[AuditLogPublic]
    total: int
    skip: int
    limit: int


class AuditStatistics(BaseModel):
    """Audit log statistics"""
    total_actions: int
    status_counts: dict
    action_counts: dict
    most_active_users: List[dict]
    period: dict


# ==================== Audit Log Query Endpoints ====================

@router.get("/logs", response_model=AuditLogSearchResponse)
async def search_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    status: Optional[AuditStatus] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search audit logs

    Requires admin privileges to view all logs.
    Regular users can only view their own logs.
    """
    # Check permissions
    tenant_id = None
    if current_user.user_type == UserTypeEnum.SYSTEM_ADMIN:
        # System admins can see all logs
        tenant_id = None
    elif current_user.user_type == UserTypeEnum.GROUP_ADMIN:
        # Group admins can see their tenant's logs
        tenant_id = current_user.tenant_id
    else:
        # Regular users can only see their own logs
        user_id = current_user.id
        tenant_id = current_user.tenant_id

    audit_service = AuditService(db)

    logs, total = await audit_service.search_logs(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        search_term=search,
        skip=skip,
        limit=limit
    )

    return AuditLogSearchResponse(
        logs=[AuditLogPublic(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            user_email=log.user_email,
            action=log.action.value if log.action else None,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            resource_name=log.resource_name,
            description=log.description,
            status=log.status.value if log.status else None,
            tenant_id=log.tenant_id,
            ip_address=log.ip_address,
            created_at=log.created_at
        ) for log in logs],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/logs/{log_id}", response_model=AuditLogDetail)
async def get_audit_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed audit log entry

    Users can only view logs they have permission to access
    """
    from sqlalchemy import select

    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log {log_id} not found"
        )

    # Check permissions
    if current_user.user_type == UserTypeEnum.SYSTEM_ADMIN:
        # System admins can see all logs
        pass
    elif current_user.user_type == UserTypeEnum.GROUP_ADMIN:
        # Group admins can see their tenant's logs
        if log.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access logs from other tenants"
            )
    else:
        # Regular users can only see their own logs
        if log.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access other users' logs"
            )

    return AuditLogDetail(
        id=log.id,
        user_id=log.user_id,
        username=log.username,
        user_email=log.user_email,
        action=log.action.value if log.action else None,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        description=log.description,
        old_value=log.old_value,
        new_value=log.new_value,
        changes=log.changes,
        status=log.status.value if log.status else None,
        error_message=log.error_message,
        tenant_id=log.tenant_id,
        session_id=log.session_id,
        correlation_id=log.correlation_id,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        metadata=log.metadata,
        created_at=log.created_at
    )


@router.get("/users/{user_id}/activity", response_model=List[AuditLogPublic])
async def get_user_activity(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent activity for a user

    Users can view their own activity.
    Admins can view any user's activity.
    """
    # Check permissions
    if user_id != current_user.id and current_user.user_type not in [UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view other users' activity"
        )

    audit_service = AuditService(db)
    logs = await audit_service.get_user_activity(user_id, days)

    return [AuditLogPublic(
        id=log.id,
        user_id=log.user_id,
        username=log.username,
        user_email=log.user_email,
        action=log.action.value if log.action else None,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        description=log.description,
        status=log.status.value if log.status else None,
        tenant_id=log.tenant_id,
        ip_address=log.ip_address,
        created_at=log.created_at
    ) for log in logs]


@router.get("/resources/{resource_type}/{resource_id}/history", response_model=List[AuditLogPublic])
async def get_resource_history(
    resource_type: str,
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full audit history for a specific resource

    Requires appropriate permissions to view the resource
    """
    audit_service = AuditService(db)
    logs = await audit_service.get_resource_history(resource_type, resource_id)

    # Filter by tenant if not system admin
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        logs = [log for log in logs if log.tenant_id == current_user.tenant_id]

    return [AuditLogPublic(
        id=log.id,
        user_id=log.user_id,
        username=log.username,
        user_email=log.user_email,
        action=log.action.value if log.action else None,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        resource_name=log.resource_name,
        description=log.description,
        status=log.status.value if log.status else None,
        tenant_id=log.tenant_id,
        ip_address=log.ip_address,
        created_at=log.created_at
    ) for log in logs]


@router.get("/statistics", response_model=AuditStatistics)
async def get_audit_statistics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get audit log statistics

    System admins see global statistics.
    Group admins see their tenant's statistics.
    """
    # Determine scope
    tenant_id = None
    if current_user.user_type == UserTypeEnum.GROUP_ADMIN:
        tenant_id = current_user.tenant_id
    elif current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view statistics"
        )

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    audit_service = AuditService(db)
    stats = await audit_service.get_statistics(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date
    )

    return AuditStatistics(**stats)


@router.get("/export/csv")
async def export_audit_logs_csv(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Export audit logs to CSV (system admin only)

    Returns a CSV file with filtered audit logs
    """
    # Determine scope
    tenant_id = None if current_user.user_type == UserTypeEnum.SYSTEM_ADMIN else current_user.tenant_id

    audit_service = AuditService(db)

    logs, _ = await audit_service.search_logs(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        skip=0,
        limit=10000  # Max export
    )

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'ID', 'Timestamp', 'User ID', 'Username', 'Email',
        'Action', 'Resource Type', 'Resource ID', 'Resource Name',
        'Description', 'Status', 'IP Address', 'Tenant ID'
    ])

    # Data rows
    for log in logs:
        writer.writerow([
            log.id,
            log.created_at.isoformat() if log.created_at else '',
            log.user_id or '',
            log.username or '',
            log.user_email or '',
            log.action.value if log.action else '',
            log.resource_type or '',
            log.resource_id or '',
            log.resource_name or '',
            log.description or '',
            log.status.value if log.status else '',
            log.ip_address or '',
            log.tenant_id or ''
        ])

    # Return CSV file
    csv_content = output.getvalue()
    output.close()

    filename = f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# ==================== Admin Endpoints ====================

@router.delete("/logs/cleanup", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_old_logs(
    days: int = Query(90, ge=30, description="Delete logs older than this many days"),
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete old audit logs (system admin only)

    Removes logs older than specified days to manage storage
    """
    from sqlalchemy import delete

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff_date)
    )

    await db.commit()

    return {"deleted_count": result.rowcount}

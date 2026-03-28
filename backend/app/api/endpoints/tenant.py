from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...models import User
from ...models.user import UserTypeEnum
from ...models.tenant import Tenant
from ...schemas.tenant import TenantResponse, TenantCreate, TenantUpdate, TenantSummary
from ...services.tenant_service import TenantService
from ...services.rbac_service import RBACService
from ...core.security import get_current_active_user

router = APIRouter()

def get_tenant_service(db: Session = Depends(get_db)) -> TenantService:
    return TenantService(db)

@router.get("/my", response_model=Optional[TenantSummary])
async def get_my_tenant(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the current user's tenant with mode information.

    Returns None if the user is not assigned to a tenant.
    This endpoint is used by the frontend to determine navigation mode.
    """
    if not current_user.tenant_id:
        return None

    stmt = select(Tenant).filter(Tenant.id == current_user.tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    return tenant


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Only SYSTEM_ADMIN sees all tenants; TENANT_ADMIN sees only their tenant
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        stmt = select(Tenant).options(joinedload(Tenant.admin))
        result = await db.execute(stmt)
        return result.scalars().unique().all()

    is_tenant_admin = user_type == UserTypeEnum.TENANT_ADMIN

    if is_tenant_admin and current_user.tenant_id:
        stmt = select(Tenant).options(joinedload(Tenant.admin)).filter(Tenant.id == current_user.tenant_id)
        result = await db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant:
            return [tenant]
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Regular users can see their own tenant if assigned
    if current_user.tenant_id:
        stmt = select(Tenant).options(joinedload(Tenant.admin)).filter(Tenant.id == current_user.tenant_id)
        result = await db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant:
            return [tenant]

    raise HTTPException(status_code=403, detail="Not enough permissions")

@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: TenantCreate, tenant_service: TenantService = Depends(get_tenant_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return tenant_service.create_tenant(tenant_in)

@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: int, tenant_update: TenantUpdate, tenant_service: TenantService = Depends(get_tenant_service), current_user: User = Depends(get_current_active_user)):
    is_system_admin = current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
    is_own_tenant_admin = (
        current_user.user_type == UserTypeEnum.TENANT_ADMIN
        and current_user.tenant_id == tenant_id
    )
    if not is_system_admin and not is_own_tenant_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    # Tenant admins can only update session_timeout_minutes on their own tenant
    if is_own_tenant_admin:
        allowed_fields = {"session_timeout_minutes"}
        provided_fields = set(tenant_update.dict(exclude_unset=True).keys())
        disallowed = provided_fields - allowed_fields
        if disallowed:
            raise HTTPException(
                status_code=403,
                detail=f"Tenant admins can only update: {', '.join(sorted(allowed_fields))}",
            )
    return tenant_service.update_tenant(tenant_id, tenant_update)

@router.delete("/{tenant_id}", response_model=dict)
def delete_tenant(tenant_id: int, tenant_service: TenantService = Depends(get_tenant_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return tenant_service.delete_tenant(tenant_id)

@router.get("/{tenant_id}/users")
async def get_tenant_users(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all users in a specific tenant.

    Tenant admins can only view their own tenant's users.
    System admins can view any tenant's users.
    """
    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Check permissions
    is_system_admin = user_type == UserTypeEnum.SYSTEM_ADMIN
    is_tenant_admin = user_type == UserTypeEnum.TENANT_ADMIN

    if not is_system_admin and not is_tenant_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Tenant admins can only view their own tenant
    if is_tenant_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="You can only view users in your own tenant")

    # Query users in the tenant
    stmt = select(User).filter(User.tenant_id == tenant_id)
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
            "tenant_id": user.tenant_id,
        }
        for user in users
    ]

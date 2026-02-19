"""
Tenant Management API Endpoints

Provides CRUD operations for tenant management:
- List tenants (admin)
- Get tenant details
- Create tenant (system admin)
- Update tenant
- Delete tenant
- Tenant invitation management
"""

from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field, validator
import secrets

from app.db.session import get_db
from app.models.user import User, UserTypeEnum
from app.models.tenant import Tenant, TenantStatus, BillingPlan, TenantInvitation, TenantUsageLog
from app.core.deps import get_current_active_superuser
from app.api.deps import get_current_user
from app.middleware.tenant_middleware import get_current_tenant, require_tenant

router = APIRouter()


# ==================== Request/Response Models ====================

class TenantPublic(BaseModel):
    """Public tenant information"""
    id: int
    name: str
    display_name: Optional[str]
    slug: str
    subdomain: str
    logo_url: Optional[str]
    primary_color: Optional[str]
    status: TenantStatus

    class Config:
        from_attributes = True


class TenantDetail(BaseModel):
    """Detailed tenant information"""
    id: int
    name: str
    display_name: Optional[str]
    slug: str
    subdomain: str
    custom_domain: Optional[str]
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    status: TenantStatus
    billing_plan: BillingPlan
    max_users: int
    max_games: int
    max_supply_chain_configs: int
    current_user_count: int
    current_game_count: int
    current_config_count: int
    features: dict
    created_at: datetime

    class Config:
        from_attributes = True


class TenantCreate(BaseModel):
    """Create new tenant"""
    name: str = Field(..., min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    subdomain: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9-]+$")
    custom_domain: Optional[str] = Field(None, max_length=200)
    billing_plan: BillingPlan = BillingPlan.FREE
    max_users: int = Field(50, ge=1)
    max_games: int = Field(100, ge=1)
    max_supply_chain_configs: int = Field(10, ge=1)
    features: Optional[dict] = None
    owner_email: Optional[str] = None  # Email of the owner user


class TenantUpdate(BaseModel):
    """Update tenant"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    custom_domain: Optional[str] = Field(None, max_length=200)
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    secondary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    status: Optional[TenantStatus] = None
    billing_plan: Optional[BillingPlan] = None
    max_users: Optional[int] = Field(None, ge=1)
    max_games: Optional[int] = Field(None, ge=1)
    max_supply_chain_configs: Optional[int] = Field(None, ge=1)
    features: Optional[dict] = None


class InvitationCreate(BaseModel):
    """Create tenant invitation"""
    email: str
    role: str = "USER"
    expires_in_days: int = Field(7, ge=1, le=30)


class InvitationPublic(BaseModel):
    """Public invitation information"""
    id: int
    email: str
    role: str
    status: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# ==================== System Admin Endpoints ====================

@router.get("/admin/tenants", response_model=List[TenantDetail])
async def list_all_tenants(
    skip: int = 0,
    limit: int = 100,
    status: Optional[TenantStatus] = None,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    List all tenants (system admin only)

    Includes all tenants regardless of status
    """
    query = select(Tenant).where(Tenant.deleted_at.is_(None))

    if status:
        query = query.where(Tenant.status == status)

    query = query.offset(skip).limit(limit).order_by(Tenant.created_at.desc())

    result = await db.execute(query)
    tenants = result.scalars().all()

    return tenants


@router.post("/admin/tenants", response_model=TenantDetail, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new tenant (system admin only)

    Creates a new tenant organization with initial configuration
    """
    # Check if slug already exists
    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_data.slug, Tenant.deleted_at.is_(None))
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with slug '{tenant_data.slug}' already exists"
        )

    # Check if subdomain already exists
    result = await db.execute(
        select(Tenant).where(Tenant.subdomain == tenant_data.subdomain, Tenant.deleted_at.is_(None))
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subdomain '{tenant_data.subdomain}' already taken"
        )

    # Find owner user if email provided
    owner_id = None
    if tenant_data.owner_email:
        result = await db.execute(select(User).where(User.email == tenant_data.owner_email))
        owner = result.scalar_one_or_none()
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Owner user with email '{tenant_data.owner_email}' not found"
            )
        owner_id = owner.id

    # Create tenant
    tenant = Tenant(
        **tenant_data.dict(exclude={'owner_email'}),
        owner_id=owner_id,
        status=TenantStatus.TRIAL,
        trial_ends_at=datetime.utcnow() + timedelta(days=30),
        features=tenant_data.features or {}
    )

    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    return tenant


@router.get("/admin/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant_admin(
    tenant_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get tenant details (system admin only)"""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )

    return tenant


@router.put("/admin/tenants/{tenant_id}", response_model=TenantDetail)
async def update_tenant_admin(
    tenant_id: int,
    tenant_data: TenantUpdate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Update tenant (system admin only)"""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )

    # Update fields
    for field, value in tenant_data.dict(exclude_unset=True).items():
        setattr(tenant, field, value)

    tenant.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(tenant)

    return tenant


@router.delete("/admin/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_admin(
    tenant_id: int,
    hard_delete: bool = False,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete tenant (system admin only)

    By default, performs soft delete. Use hard_delete=true for permanent deletion.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )

    if hard_delete:
        await db.delete(tenant)
    else:
        tenant.deleted_at = datetime.utcnow()
        tenant.status = TenantStatus.CANCELLED

    await db.commit()


# ==================== Tenant Member Endpoints ====================

@router.get("/current", response_model=TenantDetail)
async def get_current_tenant_details(
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user)
):
    """
    Get current tenant details

    Returns details of the tenant the user belongs to
    """
    return tenant


@router.put("/current", response_model=TenantDetail)
async def update_current_tenant(
    tenant_data: TenantUpdate,
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current tenant (tenant admin only)

    Only tenant owner or GROUP_ADMIN can update tenant settings
    """
    # Check if user is owner or admin
    if tenant.owner_id != current_user.id and current_user.user_type != UserTypeEnum.GROUP_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant owner or admins can update tenant settings"
        )

    # Restrict what non-system-admins can update
    allowed_fields = {'name', 'display_name', 'logo_url', 'primary_color', 'secondary_color'}
    update_data = tenant_data.dict(exclude_unset=True)

    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        # Remove fields that only system admins can update
        restricted_fields = set(update_data.keys()) - allowed_fields
        for field in restricted_fields:
            del update_data[field]

    # Update fields
    for field, value in update_data.items():
        setattr(tenant, field, value)

    tenant.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(tenant)

    return tenant


# ==================== Tenant Invitation Endpoints ====================

@router.post("/current/invitations", response_model=InvitationPublic, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    invitation_data: InvitationCreate,
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create tenant invitation (tenant admin only)

    Invite a user to join the tenant organization
    """
    # Check if user is admin
    if current_user.user_type not in [UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can invite users"
        )

    # Check if user already exists in tenant
    result = await db.execute(
        select(User).where(User.email == invitation_data.email, User.tenant_id == tenant.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {invitation_data.email} already exists in tenant"
        )

    # Check if invitation already exists
    result = await db.execute(
        select(TenantInvitation).where(
            TenantInvitation.tenant_id == tenant.id,
            TenantInvitation.email == invitation_data.email,
            TenantInvitation.status == 'pending'
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pending invitation already exists for {invitation_data.email}"
        )

    # Generate invitation token
    token = secrets.token_urlsafe(32)

    # Create invitation
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        email=invitation_data.email,
        role=invitation_data.role,
        token=token,
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=invitation_data.expires_in_days),
        invited_by_id=current_user.id
    )

    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # TODO: Send invitation email

    return invitation


@router.get("/current/invitations", response_model=List[InvitationPublic])
async def list_invitations(
    status_filter: Optional[str] = None,
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List tenant invitations (tenant admin only)

    Returns all invitations for the current tenant
    """
    # Check if user is admin
    if current_user.user_type not in [UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view invitations"
        )

    query = select(TenantInvitation).where(TenantInvitation.tenant_id == tenant.id)

    if status_filter:
        query = query.where(TenantInvitation.status == status_filter)

    query = query.order_by(TenantInvitation.created_at.desc())

    result = await db.execute(query)
    invitations = result.scalars().all()

    return invitations


@router.delete("/current/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: int,
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke tenant invitation (tenant admin only)

    Cancels a pending invitation
    """
    # Check if user is admin
    if current_user.user_type not in [UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.GROUP_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can revoke invitations"
        )

    result = await db.execute(
        select(TenantInvitation).where(
            TenantInvitation.id == invitation_id,
            TenantInvitation.tenant_id == tenant.id
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invitation {invitation_id} not found"
        )

    if invitation.status != 'pending':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only revoke pending invitations"
        )

    invitation.status = 'revoked'
    invitation.revoked_at = datetime.utcnow()

    await db.commit()


# ==================== Tenant Statistics ====================

@router.get("/current/stats")
async def get_tenant_stats(
    tenant: Tenant = Depends(require_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get tenant usage statistics

    Returns current resource usage and quotas
    """
    # Get actual counts from database
    user_count = await db.scalar(
        select(func.count(User.id)).where(User.tenant_id == tenant.id, User.is_active == True)
    )

    # Note: Game model doesn't have tenant relationship yet, so we'll use the stored count

    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
        "status": tenant.status.value,
        "billing_plan": tenant.billing_plan.value,
        "usage": {
            "users": {
                "current": user_count or tenant.current_user_count,
                "max": tenant.max_users,
                "percentage": round((user_count or tenant.current_user_count) / tenant.max_users * 100, 1)
            },
            "games": {
                "current": tenant.current_game_count,
                "max": tenant.max_games,
                "percentage": round(tenant.current_game_count / tenant.max_games * 100, 1)
            },
            "configs": {
                "current": tenant.current_config_count,
                "max": tenant.max_supply_chain_configs,
                "percentage": round(tenant.current_config_count / tenant.max_supply_chain_configs * 100, 1)
            },
            "storage": {
                "current_mb": tenant.current_storage_mb,
                "max_mb": tenant.max_storage_mb,
                "percentage": round(tenant.current_storage_mb / tenant.max_storage_mb * 100, 1)
            }
        },
        "features": tenant.features,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "subscription_ends_at": tenant.subscription_ends_at.isoformat() if tenant.subscription_ends_at else None
    }

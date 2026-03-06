"""
SSO API Endpoints

Handles SSO authentication flows:
- OAuth2 initiation and callback
- LDAP login
- Provider management (admin only)
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, validator

from app.db.session import get_db
from app.models.user import User
from app.models.sso_provider import SSOProvider, SSOProviderType, UserSSOMapping
from app.services.sso_service import SSOService
from app.services.auth_service import AuthService, create_access_token
from app.api.deps import get_current_user
from app.core.deps import get_current_active_superuser
from app.core.config import settings

router = APIRouter()


# ==================== Request/Response Models ====================

class SSOProviderPublic(BaseModel):
    """Public SSO provider information (for login page)"""
    id: int
    name: str
    slug: str
    type: SSOProviderType

    class Config:
        from_attributes = True


class SSOProviderAdmin(BaseModel):
    """Admin SSO provider view (includes full config)"""
    id: int
    name: str
    slug: str
    type: SSOProviderType
    config: dict
    enabled: bool
    allowed_domains: Optional[List[str]] = None
    auto_create_users: bool
    default_user_type: str
    default_tenant_id: Optional[int] = None
    tenant_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SSOProviderCreate(BaseModel):
    """Create SSO provider"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50, pattern="^[a-z0-9-]+$")
    type: SSOProviderType
    config: dict = Field(..., description="Provider-specific configuration")
    enabled: bool = True
    allowed_domains: Optional[List[str]] = None
    auto_create_users: bool = True
    default_user_type: str = "USER"
    default_tenant_id: Optional[int] = None

    @validator('config')
    def validate_config(cls, v, values):
        """Validate config based on provider type"""
        provider_type = values.get('type')

        if provider_type == SSOProviderType.OAUTH2:
            required_fields = ['client_id', 'client_secret', 'authorization_url', 'token_url', 'userinfo_url']
            for field in required_fields:
                if field not in v:
                    raise ValueError(f"OAuth2 provider requires '{field}' in config")

        elif provider_type == SSOProviderType.LDAP:
            required_fields = ['server', 'base_dn']
            for field in required_fields:
                if field not in v:
                    raise ValueError(f"LDAP provider requires '{field}' in config")

        return v


class SSOProviderUpdate(BaseModel):
    """Update SSO provider"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[dict] = None
    enabled: Optional[bool] = None
    allowed_domains: Optional[List[str]] = None
    auto_create_users: Optional[bool] = None
    default_user_type: Optional[str] = None
    default_tenant_id: Optional[int] = None


class LDAPLoginRequest(BaseModel):
    """LDAP login request"""
    provider_slug: str
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    token_type: str = "bearer"
    user: dict
    is_new_user: bool = False


# ==================== Public Endpoints ====================

@router.get("/providers", response_model=List[SSOProviderPublic])
async def list_sso_providers(db: AsyncSession = Depends(get_db)):
    """
    List available SSO providers

    Public endpoint - shows enabled providers for login page
    """
    sso_service = SSOService(db)
    providers = await sso_service.list_providers()
    return [SSOProviderPublic.from_orm(p) for p in providers]


@router.get("/oauth2/{provider_slug}/authorize")
async def oauth2_authorize(
    provider_slug: str,
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate OAuth2 SSO flow

    Redirects user to provider's authorization page

    Args:
        provider_slug: Provider identifier (e.g., 'okta', 'google')
        redirect_uri: Where to redirect after authentication (defaults to frontend callback)
    """
    sso_service = SSOService(db)

    provider = await sso_service.get_provider_by_slug(provider_slug)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO provider '{provider_slug}' not found"
        )

    # Default redirect URI
    if not redirect_uri:
        redirect_uri = f"{settings.FRONTEND_URL}/auth/sso/callback/{provider_slug}"

    try:
        authorization_url = await sso_service.get_oauth_authorization_url(
            provider=provider,
            redirect_uri=redirect_uri
        )
        return RedirectResponse(url=authorization_url)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth2 flow: {str(e)}"
        )


@router.get("/oauth2/{provider_slug}/callback", response_model=TokenResponse)
async def oauth2_callback(
    provider_slug: str,
    code: str,
    redirect_uri: Optional[str] = None,
    request: Request = None,
    response: Response = None,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2 callback endpoint

    Provider redirects here after user authorization

    Args:
        provider_slug: Provider identifier
        code: Authorization code from provider
        redirect_uri: Redirect URI used in authorization request
    """
    sso_service = SSOService(db)

    provider = await sso_service.get_provider_by_slug(provider_slug)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO provider '{provider_slug}' not found"
        )

    # Default redirect URI
    if not redirect_uri:
        redirect_uri = f"{settings.FRONTEND_URL}/auth/sso/callback/{provider_slug}"

    # Get client info
    ip_address = request.client.host if request else None
    user_agent = request.headers.get('user-agent') if request else None

    try:
        user, is_new = await sso_service.authenticate_oauth2(
            provider=provider,
            code=code,
            redirect_uri=redirect_uri,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Generate tokens
        access_token = create_access_token(data={"sub": str(user.id)})

        # Create refresh token using AuthService
        auth_service = AuthService(db)
        refresh_token = await auth_service.create_refresh_token(user_id=user.id)

        # Set refresh token cookie
        if response:
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAME_SITE,
                max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            )

        return TokenResponse(
            access_token=access_token,
            user=user.to_dict(),
            is_new_user=is_new
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OAuth2 authentication failed: {str(e)}"
        )


@router.post("/ldap/login", response_model=TokenResponse)
async def ldap_login(
    login_data: LDAPLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    LDAP/Active Directory login

    Args:
        login_data: LDAP credentials
    """
    sso_service = SSOService(db)

    provider = await sso_service.get_provider_by_slug(login_data.provider_slug)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO provider '{login_data.provider_slug}' not found"
        )

    # Get client info
    ip_address = request.client.host if request else None
    user_agent = request.headers.get('user-agent') if request else None

    try:
        user, is_new = await sso_service.authenticate_ldap(
            provider=provider,
            username=login_data.username,
            password=login_data.password,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Generate tokens
        access_token = create_access_token(data={"sub": str(user.id)})

        # Create refresh token using AuthService
        auth_service = AuthService(db)
        refresh_token = await auth_service.create_refresh_token(user_id=user.id)

        # Set refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAME_SITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )

        return TokenResponse(
            access_token=access_token,
            user=user.to_dict(),
            is_new_user=is_new
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"LDAP authentication failed"
        )


# ==================== Admin Endpoints ====================

@router.post("/admin/providers", response_model=SSOProviderPublic, status_code=status.HTTP_201_CREATED)
async def create_sso_provider(
    provider_data: SSOProviderCreate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Create SSO provider (admin only)

    Requires SYSTEM_ADMIN role
    """
    # Check if slug already exists
    sso_service = SSOService(db)
    existing = await sso_service.get_provider_by_slug(provider_data.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider with slug '{provider_data.slug}' already exists"
        )

    provider = SSOProvider(
        **provider_data.dict(),
        created_by=current_user.id
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    return SSOProviderPublic.from_orm(provider)


@router.get("/admin/providers", response_model=List[SSOProviderAdmin])
async def list_all_sso_providers(
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    List all SSO providers (admin only)

    Includes disabled providers and full configuration
    """
    from sqlalchemy import select

    result = await db.execute(select(SSOProvider))
    providers = result.scalars().all()
    return providers


@router.get("/admin/providers/{provider_id}", response_model=SSOProviderAdmin)
async def get_sso_provider(
    provider_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get SSO provider details (admin only)"""
    from sqlalchemy import select

    result = await db.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )

    return provider


@router.put("/admin/providers/{provider_id}", response_model=SSOProviderAdmin)
async def update_sso_provider(
    provider_id: int,
    provider_data: SSOProviderUpdate,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Update SSO provider (admin only)"""
    from sqlalchemy import select

    result = await db.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )

    # Update fields
    for field, value in provider_data.dict(exclude_unset=True).items():
        setattr(provider, field, value)

    provider.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(provider)

    return provider


@router.delete("/admin/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sso_provider(
    provider_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Delete SSO provider (admin only)"""
    from sqlalchemy import select

    result = await db.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider_id} not found"
        )

    await db.delete(provider)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

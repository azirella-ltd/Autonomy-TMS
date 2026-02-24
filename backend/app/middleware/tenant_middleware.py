"""
Tenant Middleware

Provides automatic tenant detection and isolation:
- Extracts tenant from subdomain or custom domain
- Validates tenant status
- Enforces data isolation
- Tracks tenant context throughout request lifecycle
"""

from typing import Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantStatus
from app.db.session import get_db

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to detect and validate tenant from request

    Extracts tenant information from:
    1. Subdomain (e.g., company1.autonomy.ai)
    2. Custom domain (e.g., autonomy.company.com)
    3. X-Tenant-ID header (for API clients)
    4. Falls back to default tenant if configured
    """

    def __init__(self, app, default_subdomain: str = "default"):
        super().__init__(app)
        self.default_subdomain = default_subdomain
        self.excluded_paths = [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/sso",
        ]

    async def dispatch(self, request: Request, call_next):
        """Process request and inject tenant context"""

        # Skip tenant detection for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)

        try:
            # Get database session
            async for db in get_db():
                # Detect tenant
                tenant = await self._detect_tenant(request, db)

                if tenant:
                    # Validate tenant status
                    if not self._is_tenant_accessible(tenant):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Tenant account is {tenant.status.value}. Please contact support."
                        )

                    # Inject tenant into request state
                    request.state.tenant = tenant
                    request.state.tenant_id = tenant.id

                    # Add tenant info to response headers (for debugging)
                    response = await call_next(request)
                    response.headers["X-Tenant-ID"] = str(tenant.id)
                    response.headers["X-Tenant-Slug"] = tenant.slug
                    return response
                else:
                    # No tenant found - allow request to proceed
                    # (Some endpoints like public auth don't require tenant)
                    request.state.tenant = None
                    request.state.tenant_id = None
                    return await call_next(request)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Tenant middleware error: {str(e)}")
            # Don't block request if tenant detection fails
            request.state.tenant = None
            request.state.tenant_id = None
            return await call_next(request)

    async def _detect_tenant(self, request: Request, db: AsyncSession) -> Optional[Tenant]:
        """
        Detect tenant from request

        Priority order:
        1. X-Tenant-ID header (for API clients)
        2. Custom domain lookup
        3. Subdomain extraction
        4. Default tenant
        """

        # Method 1: X-Tenant-ID header
        tenant_id_header = request.headers.get("X-Tenant-ID")
        if tenant_id_header:
            try:
                tenant_id = int(tenant_id_header)
                tenant = await self._get_tenant_by_id(db, tenant_id)
                if tenant:
                    return tenant
            except ValueError:
                pass

        # Method 2: X-Tenant-Slug header
        tenant_slug_header = request.headers.get("X-Tenant-Slug")
        if tenant_slug_header:
            tenant = await self._get_tenant_by_slug(db, tenant_slug_header)
            if tenant:
                return tenant

        # Method 3: Host header (subdomain or custom domain)
        host = request.headers.get("host", "").lower()
        if host:
            # Remove port if present
            host = host.split(":")[0]

            # Check for custom domain
            tenant = await self._get_tenant_by_custom_domain(db, host)
            if tenant:
                return tenant

            # Extract subdomain
            subdomain = self._extract_subdomain(host)
            if subdomain:
                tenant = await self._get_tenant_by_subdomain(db, subdomain)
                if tenant:
                    return tenant

        # Method 4: Default tenant (fallback for development)
        if self.default_subdomain:
            tenant = await self._get_tenant_by_subdomain(db, self.default_subdomain)
            if tenant:
                return tenant

        return None

    def _extract_subdomain(self, host: str) -> Optional[str]:
        """
        Extract subdomain from host

        Examples:
        - company1.autonomy.ai -> company1
        - autonomy.ai -> None (root domain)
        - localhost -> None
        """
        parts = host.split(".")

        # Localhost or IP address
        if len(parts) <= 1 or host in ["localhost", "127.0.0.1"]:
            return None

        # Root domain (autonomy.ai)
        if len(parts) == 2:
            return None

        # Subdomain exists (company1.autonomy.ai)
        if len(parts) >= 3:
            return parts[0]

        return None

    async def _get_tenant_by_id(self, db: AsyncSession, tenant_id: int) -> Optional[Tenant]:
        """Get tenant by ID"""
        result = await db.execute(
            select(Tenant).where(
                Tenant.id == tenant_id,
                Tenant.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def _get_tenant_by_slug(self, db: AsyncSession, slug: str) -> Optional[Tenant]:
        """Get tenant by slug"""
        result = await db.execute(
            select(Tenant).where(
                Tenant.slug == slug,
                Tenant.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def _get_tenant_by_subdomain(self, db: AsyncSession, subdomain: str) -> Optional[Tenant]:
        """Get tenant by subdomain"""
        result = await db.execute(
            select(Tenant).where(
                Tenant.subdomain == subdomain,
                Tenant.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def _get_tenant_by_custom_domain(self, db: AsyncSession, domain: str) -> Optional[Tenant]:
        """Get tenant by custom domain"""
        result = await db.execute(
            select(Tenant).where(
                Tenant.custom_domain == domain,
                Tenant.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    def _is_tenant_accessible(self, tenant: Tenant) -> bool:
        """
        Check if tenant is accessible

        Active and trial tenants can access the system.
        Suspended and cancelled tenants cannot.
        """
        return tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]


def get_current_tenant(request: Request) -> Optional[Tenant]:
    """
    Dependency to get current tenant from request state

    Usage:
        @router.get("/games")
        async def list_games(tenant: Tenant = Depends(get_current_tenant)):
            # tenant is automatically injected
    """
    return getattr(request.state, "tenant", None)


def require_tenant(request: Request) -> Tenant:
    """
    Dependency that requires a tenant (raises 404 if not found)

    Usage:
        @router.get("/games")
        async def list_games(tenant: Tenant = Depends(require_tenant)):
            # Guaranteed to have a tenant or 404 error
    """
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found. Please access via tenant subdomain or provide X-Tenant-ID header."
        )
    return tenant


def get_current_tenant_id(request: Request) -> Optional[int]:
    """
    Dependency to get current tenant ID from request state

    Usage:
        @router.get("/games")
        async def list_games(tenant_id: int = Depends(get_current_tenant_id)):
            # tenant_id is automatically injected
    """
    return getattr(request.state, "tenant_id", None)

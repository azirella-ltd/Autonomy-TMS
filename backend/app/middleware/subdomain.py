"""
Subdomain validation for hybrid multi-tenant routing (Option C).

Extracts the subdomain from the request Host header and validates it
against the JWT tenant_slug claim. Prevents URL spoofing where a user
on tenant A navigates to tenant B's subdomain.

Flow:
  1. Extract subdomain from Host header (e.g., "acme" from "acme.azirella.com")
  2. If subdomain routing disabled or subdomain is login/default: pass through
  3. For vanity subdomains: validate JWT tenant_slug matches

Usage as a FastAPI dependency:
    @router.get("/data")
    async def get_data(user: User = Depends(verify_subdomain_tenant)):
        ...

Or as a lightweight function for middleware-style checks:
    subdomain = extract_subdomain(request, settings.APP_DOMAIN)
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request

from app.core.config import settings


def extract_subdomain(host: str, base_domain: str) -> Optional[str]:
    """Extract subdomain from a Host header value.

    Examples:
        extract_subdomain("acme.azirella.com", "azirella.com") -> "acme"
        extract_subdomain("login.azirella.com", "azirella.com") -> "login"
        extract_subdomain("azirella.com", "azirella.com") -> None
        extract_subdomain("localhost:8088", "localhost") -> None

    Returns None for bare domain or localhost.
    """
    # Strip port
    host_no_port = host.split(":")[0].lower().strip()
    base = base_domain.lower().strip()

    # Exact match = no subdomain
    if host_no_port == base:
        return None

    # Must end with .base_domain
    suffix = f".{base}"
    if not host_no_port.endswith(suffix):
        return None

    prefix = host_no_port[: -len(suffix)]
    return prefix if prefix else None


def get_request_subdomain(request: Request) -> Optional[str]:
    """Extract subdomain from the current request."""
    host = request.headers.get("host", "")
    return extract_subdomain(host, settings.APP_DOMAIN)


async def verify_subdomain_tenant(request: Request) -> None:
    """FastAPI dependency that validates the subdomain matches the JWT tenant.

    Skips validation when:
      - SUBDOMAIN_ROUTING_ENABLED is False (local dev)
      - Subdomain is login, default, or absent
      - No auth cookie/header present (public endpoints)

    Raises HTTPException 403 if a vanity subdomain doesn't match the JWT.
    """
    if not settings.SUBDOMAIN_ROUTING_ENABLED:
        return

    subdomain = get_request_subdomain(request)

    # No subdomain, login portal, or default app domain — always allowed
    if subdomain is None or subdomain in (
        settings.LOGIN_SUBDOMAIN,
        settings.DEFAULT_SUBDOMAIN,
    ):
        return

    # Vanity subdomain — must match JWT tenant_slug
    from app.core.security import decode_token

    token = _get_token_from_request(request)
    if not token:
        # No auth token — let the auth dependency handle 401
        return

    try:
        payload = decode_token(token)
    except Exception:
        # Invalid token — let the auth dependency handle it
        return

    jwt_tenant_slug = payload.get("tenant_slug")
    if jwt_tenant_slug and jwt_tenant_slug != subdomain:
        raise HTTPException(
            status_code=403,
            detail=f"Subdomain '{subdomain}' does not match your tenant '{jwt_tenant_slug}'",
        )


def _get_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT from cookie or Authorization header."""
    # Cookie first
    token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
    if token:
        return token

    # Authorization header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]

    return None

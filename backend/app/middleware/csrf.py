from fastapi import Request, Response, HTTPException, status
from fastapi.middleware import Middleware
from fastapi.responses import JSONResponse
from fastapi.routing import Match
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import secrets
import time
from typing import Callable, Optional, Any, Awaitable

from app.core.config import settings

class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.exempt_paths = {
            'GET': {
                '/api/v1/auth/login',
                '/api/v1/auth/refresh',
                '/api/v1/auth/csrf-token',
                '/api/v1/auth/me',
                '/api/v1/docs',
                '/api/v1/openapi.json',
                '/api/v1/redoc',
            },
            'POST': {
                '/api/v1/auth/login',
                '/api/v1/auth/logout',
                '/api/v1/auth/refresh-token',
            },
            'OPTIONS': {'*'},  # Always allow OPTIONS for CORS preflight
        }

    def is_exempt(self, method: str, path: str) -> bool:
        """Check if the request is exempt from CSRF protection."""
        # Check exact matches first
        if path in self.exempt_paths.get(method, set()) or \
           '*' in self.exempt_paths.get(method, set()):
            return True
        
        # Check path prefixes (for API versioning, etc.)
        for exempt_path in self.exempt_paths.get(method, set()):
            if path.startswith(exempt_path.rstrip('*')):
                return True
        
        return False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path
        
        # Skip CSRF check for exempt paths and safe methods
        if method in ('GET', 'HEAD', 'OPTIONS') or self.is_exempt(method, path):
            return await call_next(request)
        
        # Get CSRF token from header
        csrf_token = request.headers.get(settings.CSRF_HEADER_NAME)
        if not csrf_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token missing from headers"}
            )
        
        # Get CSRF token from cookie
        csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
        if not csrf_cookie:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF cookie not found"}
            )
        
        # Compare tokens
        if not secrets.compare_digest(csrf_token, csrf_cookie):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token validation failed"}
            )
        
        # Token is valid, proceed with the request
        response = await call_next(request)
        return response

def get_csrf_middleware():
    """Factory function to create CSRF middleware with app instance."""
    return CSRFMiddleware

def generate_csrf_token() -> str:
    """Generate a secure random CSRF token."""
    return secrets.token_urlsafe(settings.CSRF_TOKEN_LENGTH)

def set_csrf_cookie(
    response: Response,
    token: Optional[str] = None,
    expires_seconds: Optional[int] = None
) -> str:
    """Set CSRF token as a cookie in the response."""
    if token is None:
        token = generate_csrf_token()
    
    expires = int(time.time()) + (expires_seconds or settings.CSRF_EXPIRE_SECONDS)
    
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        max_age=expires_seconds or settings.CSRF_EXPIRE_SECONDS,
        expires=expires,
        path=settings.CSRF_COOKIE_PATH,
        domain=settings.CSRF_COOKIE_DOMAIN,
        secure=settings.CSRF_COOKIE_SECURE,
        httponly=settings.CSRF_COOKIE_HTTP_ONLY,
        samesite=settings.CSRF_COOKIE_SAME_SITE
    )
    
    return token

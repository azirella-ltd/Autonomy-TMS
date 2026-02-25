import uuid
from datetime import datetime, timedelta
from typing import Optional, Any, Union, Callable, Awaitable, Dict
from sqlalchemy import select
try:  # pragma: no cover - optional dependency shim
    from jose import JWTError, jwt  # type: ignore
except ImportError:  # pragma: no cover
    class JWTError(Exception):
        """Fallback JWT error when ``python-jose`` is unavailable."""

    class _MissingJose:
        def encode(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError(
                "python-jose is required for JWT operations; install 'python-jose' "
                "to enable token creation."
            )

        def decode(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError(
                "python-jose is required for JWT operations; install 'python-jose' "
                "to enable token decoding."
            )

    jwt = _MissingJose()  # type: ignore[assignment]

# Passlib expects the bcrypt module to expose an ``__about__`` attribute which
# newer releases no longer ship.  Patch it in once here so every importer sees a
# consistent interface and we avoid noisy warnings from the underlying handler.
try:  # pragma: no cover - best-effort compatibility shim
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover - bcrypt optional in some environments
    bcrypt = None  # type: ignore
else:  # pragma: no cover - executed when bcrypt is available
    if bcrypt is not None and not hasattr(bcrypt, "__about__"):
        from types import SimpleNamespace

        version = getattr(bcrypt, "__version__", "")
        bcrypt.__about__ = SimpleNamespace(__version__=version)  # type: ignore[attr-defined]

from passlib.context import CryptContext

try:  # pragma: no cover - optional FastAPI dependency
    from fastapi import Depends, HTTPException, status, Request, Response  # type: ignore
    from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm  # type: ignore
    from fastapi.security.utils import get_authorization_scheme_param  # type: ignore
except ImportError:  # pragma: no cover
    class _Status:
        HTTP_401_UNAUTHORIZED = 401
        HTTP_404_NOT_FOUND = 404

    class HTTPException(Exception):  # type: ignore[override]
        def __init__(self, status_code: int, detail: str, headers: Optional[Dict[str, str]] = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    def Depends(dependency):  # type: ignore[no-untyped-def]
        return dependency

    def Request(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("FastAPI Request object is unavailable in this environment")

    Response = Request  # type: ignore
    status = _Status()  # type: ignore

    class OAuth2PasswordBearer:  # type: ignore[override]
        def __init__(self, *_, **__):
            pass

    class OAuth2PasswordRequestForm:  # type: ignore[override]
        pass

    def get_authorization_scheme_param(header: Optional[str]):  # type: ignore[override]
        return "", header or ""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from sqlalchemy.future import select

from app.models.user import User, UserTypeEnum
from app.models.customer import Customer
from app.repositories.users import get_user_by_email
try:  # pragma: no cover - optional middleware dependency
    from app.middleware.csrf import set_csrf_cookie
except ModuleNotFoundError:  # pragma: no cover
    def set_csrf_cookie(*_args, **_kwargs):  # type: ignore[override]
        raise RuntimeError("CSRF middleware is unavailable in this environment")

# Password hashing
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False  # Don't auto-raise 401 for missing token
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    user_type: Optional[str] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token with standard claims.
    
    Args:
        subject: The subject of the token (usually user ID or email)
        user_type: Serialized user type string
        expires_delta: Optional timedelta for token expiration
        
    Returns:
        str: Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "user_type": user_type,
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token to decode
        
    Returns:
        dict: The decoded token payload
        
    Raises:
        HTTPException: If the token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_from_request(request: Request, auth_header_token: Optional[str] = None) -> Optional[str]:
    """
    Get the token from either the Authorization header or cookie.

    Priority:
    1. Authorization header (Bearer token) - extracted by OAuth2PasswordBearer
    2. Access token cookie

    Args:
        request: The incoming request
        auth_header_token: Token from OAuth2PasswordBearer (already extracted, without "Bearer " prefix)

    Returns:
        str or None: The JWT token if found, else None
    """
    # OAuth2PasswordBearer already extracts the token (without "Bearer " prefix)
    # If it was provided, use it directly
    if auth_header_token:
        return auth_header_token

    # Fall back to cookie
    token = request.cookies.get(settings.COOKIE_ACCESS_TOKEN_NAME)
    if token:
        # Remove quotes and "Bearer " prefix if present
        token = token.strip('"')
        if token.startswith("Bearer "):
            token = token[7:]  # Remove "Bearer " prefix
        return token

    return None


async def get_current_user(
    request: Request, 
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current user from the JWT token in either cookie or header.
    
    Args:
        request: The incoming request
        token: JWT token from header or cookie
        db: Database session
        
    Returns:
        User: The authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Get token from header or cookie
    token = get_token_from_request(request, token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Decode the token
        payload = decode_token(token)
        sub = payload.get("sub")
        email = payload.get("email")
        if not sub and not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = None

        # Try email first (explicit email field or sub is an email)
        if email:
            result = await db.execute(select(User).filter(User.email == email))
            user = result.scalars().first()

        # If sub is a numeric ID, try lookup by ID
        if not user and sub and str(sub).isdigit():
            result = await db.execute(select(User).filter(User.id == int(sub)))
            user = result.scalars().first()

        # If sub looks like an email (contains @), use it as email lookup
        if not user and sub and '@' in str(sub):
            result = await db.execute(select(User).filter(User.email == sub))
            user = result.scalars().first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
            
        # Coerce user_type: token > database > fallback
        token_user_type = payload.get("user_type")
        if token_user_type:
            try:
                user.user_type = UserTypeEnum(token_user_type)
            except ValueError:
                pass  # Fall through to check database value

        # Preserve existing database user_type if set and not yet assigned from token
        db_user_type = getattr(user, "user_type", None)
        if db_user_type is not None:
            if isinstance(db_user_type, str):
                try:
                    user.user_type = UserTypeEnum(db_user_type)
                except ValueError:
                    user.user_type = UserTypeEnum.USER
            # If already a valid enum, keep it
        elif db_user_type is None:
            # Final fallback only if no user_type is set
            user.user_type = UserTypeEnum.USER

        if (
            getattr(user, "customer_id", None) in (None, 0)
            and user.user_type == UserTypeEnum.GROUP_ADMIN
        ):
            admin_customer = getattr(user, "admin_of_customer", None)
            if not admin_customer:
                admin_customer_result = await db.execute(
                    select(Customer).filter(Customer.admin_id == user.id)
                )
                admin_customer = admin_customer_result.scalars().first()
            if admin_customer:
                user.customer_id = admin_customer.id

        return user
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def set_auth_cookies(
    response: Response, 
    access_token: str, 
    token_type: str = "Bearer"
) -> None:
    """
    Set authentication cookies on the response.
    
    Args:
        response: The FastAPI response object
        access_token: The JWT access token
        token_type: The token type (default: "Bearer")
    """
    response.set_cookie(
        key=settings.COOKIE_ACCESS_TOKEN_NAME,
        value=access_token,
        httponly=settings.COOKIE_HTTP_ONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE,
        domain=settings.COOKIE_DOMAIN,
        path=settings.COOKIE_PATH,
        max_age=settings.COOKIE_MAX_AGE,
    )
    response.set_cookie(
        key=settings.COOKIE_TOKEN_TYPE_NAME,
        value=token_type,
        httponly=False,  # Allow JavaScript to read this
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE,
        domain=settings.COOKIE_DOMAIN,
        path=settings.COOKIE_PATH,
        max_age=settings.COOKIE_MAX_AGE,
    )


def clear_auth_cookies(response: Response) -> None:
    """
    Clear authentication cookies from the response.
    
    Args:
        response: The FastAPI response object
    """
    response.delete_cookie(
        key=settings.COOKIE_ACCESS_TOKEN_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key=settings.COOKIE_TOKEN_TYPE_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
    )


def verify_password_strength(password: str) -> bool:
    """Verify that a password meets strength requirements.
    
    Args:
        password: The password to check
        
    Returns:
        bool: True if password meets requirements, False otherwise
    """
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    return True

def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token with standard claims.
    
    Args:
        user_id: The user's unique identifier
        expires_delta: Optional time delta for token expiration
        
    Returns:
        str: Encoded JWT refresh token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }
    
    return jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )

# NOTE: create_access_token is defined earlier in this file (line ~111)
# This duplicate was removed to fix auth errors

async def get_token_from_cookie_or_header(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[str]:
    """Get token from either cookie or Authorization header.
    
    Priority:
    1. Authorization header (Bearer token)
    2. Access token cookie
    
    Args:
        request: The incoming request
        token: Token from Authorization header (if any)
        
    Returns:
        str or None: The JWT token if found, else None
    """
    # Try to get token from Authorization header first
    if token:
        return token
        
    # Then try to get from cookie
    token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
    if token:
        return token
        
    return None


async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """Get the current active user."""
    # TODO: Add any additional checks for active status, etc.
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def create_auth_response(
    user_id: str,
    response: Response,
    remember_me: bool = False
) -> Dict[str, str]:
    """Create an authentication response with tokens in cookies.
    
    Args:
        user_id: The user's ID
        response: FastAPI Response object to set cookies
        remember_me: Whether to use longer expiration for the refresh token
        
    Returns:
        dict: User data to include in the response body
    """
    # Create tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    # Calculate token expiration times
    access_token_expires = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # in seconds
    refresh_token_expires = (settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)  # in seconds
    
    # Set access token cookie (httpOnly, secure)
    response.set_cookie(
        key=settings.ACCESS_TOKEN_COOKIE_NAME,
        value=f"{settings.TOKEN_PREFIX} {access_token}",
        max_age=access_token_expires,
        expires=access_token_expires,
        path="/",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=settings.COOKIE_HTTP_ONLY,
        samesite=settings.COOKIE_SAME_SITE
    )
    
    # Set refresh token cookie (httpOnly, secure, longer expiration)
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_token_expires if remember_me else None,  # Session cookie if not remember_me
        expires=refresh_token_expires if remember_me else None,
        path=f"{settings.API_V1_STR}/auth/refresh",  # Only sent for refresh endpoint
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,  # Always httpOnly for refresh token
        samesite=settings.COOKIE_SAME_SITE
    )
    
    # Set CSRF token cookie (not httpOnly, used by frontend)
    csrf_token = set_csrf_cookie(
        response=response,
        expires_seconds=settings.CSRF_EXPIRE_SECONDS
    )
    
    # Return user data (without sensitive info)
    return {
        "user": {
            "id": user_id,
            # Add other non-sensitive user fields here
        },
        "access_token": access_token,  # For clients that need it in the response body
        "token_type": "bearer"
    }

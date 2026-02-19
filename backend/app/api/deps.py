"""FastAPI dependency helpers for legacy synchronous endpoints."""

from __future__ import annotations

from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import decode_token, get_token_from_request
from app.db.session import sync_engine
from app.models.user import User, UserTypeEnum

_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)

SessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a synchronous SQLAlchemy session for endpoints that expect it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias for backward compatibility
get_sync_db = get_db


def _coerce_user_type(user: User, token_payload: dict) -> None:
    """Coerce user_type from token or database.

    Priority order:
    1. Token payload user_type (if present and valid)
    2. Database user_type (preserve existing value)
    3. Fallback to USER if nothing else
    """
    token_type = token_payload.get("user_type")
    if token_type:
        try:
            user.user_type = UserTypeEnum(token_type)
            return
        except ValueError:
            pass  # Fall through to check database value

    # Preserve existing database user_type if set
    db_user_type = getattr(user, "user_type", None)
    if db_user_type is not None:
        # Ensure it's a valid enum
        if isinstance(db_user_type, str):
            try:
                user.user_type = UserTypeEnum(db_user_type)
                return
            except ValueError:
                pass
        elif isinstance(db_user_type, UserTypeEnum):
            return  # Already valid enum, keep it

    # Final fallback only if no user_type is set
    user.user_type = UserTypeEnum.USER


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current user using the cookie/header token against the sync session."""
    raw_token = get_token_from_request(request, token)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(raw_token)
    except HTTPException:
        # re-raise FastAPI HTTP errors unchanged
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try to get email from payload (new format) or sub if it contains email (old format)
    email = payload.get("email")
    user_id = payload.get("sub")

    if not email and not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try lookup by email first, then by ID
    if email:
        user = db.query(User).filter(User.email == email).first()
    elif user_id and user_id.isdigit():
        user = db.query(User).filter(User.id == int(user_id)).first()
    else:
        # Assume user_id is actually an email (old token format)
        user = db.query(User).filter(User.email == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _coerce_user_type(user, payload)
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the resolved user account is active."""
    if not getattr(current_user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def require_group_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure user is a group admin or system admin."""
    if current_user.user_type not in (UserTypeEnum.GROUP_ADMIN, UserTypeEnum.SYSTEM_ADMIN):
        if not getattr(current_user, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires group admin privileges",
            )
    return current_user

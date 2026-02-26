"""FastAPI dependency helpers for legacy synchronous endpoints and service account auth."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generator, Optional, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import decode_token, get_token_from_request
from app.db.session import sync_engine
from app.db.session import get_db as get_async_db
from app.models.user import User, UserTypeEnum

logger = logging.getLogger(__name__)

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


async def require_tenant_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure user is a tenant admin or system admin."""
    if current_user.user_type not in (UserTypeEnum.TENANT_ADMIN, UserTypeEnum.SYSTEM_ADMIN):
        if not getattr(current_user, "is_superuser", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires tenant admin privileges",
            )
    return current_user


# ---------------------------------------------------------------------------
# Service Account Authentication (PicoClaw / OpenClaw)
# ---------------------------------------------------------------------------

@dataclass
class ServiceAccountUser:
    """Sentinel object representing an authenticated edge service account.

    Provides a User-like interface so endpoints can use
    ``Union[User, ServiceAccountUser]`` as the auth principal.
    """
    id: int
    name: str
    scope: str  # "site", "region", "global"
    site_key: Optional[str] = None
    tenant_id: Optional[int] = None
    # User-compatible attributes
    email: str = "service-account@edge"
    is_active: bool = True
    user_type: str = "SERVICE_ACCOUNT"
    is_service_account: bool = True


async def _lookup_service_account(
    raw_token: str, db: AsyncSession
) -> Optional[ServiceAccountUser]:
    """Validate a bearer token against the edge_service_accounts table.

    Tokens are stored as SHA-256 hashes. Returns a ServiceAccountUser if
    the token matches an active, non-expired service account.
    """
    from app.models.edge_agents import EdgeServiceAccount

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    result = await db.execute(
        select(EdgeServiceAccount).where(
            EdgeServiceAccount.token_hash == token_hash,
            EdgeServiceAccount.status == "active",
        )
    )
    sa = result.scalar_one_or_none()
    if sa is None:
        return None

    # Check expiry
    if sa.expires_at and sa.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None

    # Update last_used_at (fire-and-forget, don't block the request)
    await db.execute(
        update(EdgeServiceAccount)
        .where(EdgeServiceAccount.id == sa.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )

    return ServiceAccountUser(
        id=sa.id,
        name=sa.name,
        scope=sa.scope,
        site_key=sa.site_key,
        tenant_id=sa.customer_id,
    )


async def get_current_user_or_service_account(
    request: Request,
    token: Optional[str] = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> Union[User, ServiceAccountUser]:
    """Authenticate via JWT (human user) or service account token (PicoClaw/OpenClaw).

    Tries JWT first. If the token is not a valid JWT, falls back to
    looking up the raw token in edge_service_accounts.
    """
    raw_token = get_token_from_request(request, token)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Try JWT (human user) first ---
    try:
        payload = decode_token(raw_token)
        email = payload.get("email")
        user_id = payload.get("sub")

        if email or user_id:
            # Use a sync query wrapped in the async session's run_sync
            # since User is on the sync engine, we do a direct query
            from sqlalchemy import text
            if email:
                result = await db.execute(
                    select(User).where(User.email == email)
                )
            elif user_id and str(user_id).isdigit():
                result = await db.execute(
                    select(User).where(User.id == int(user_id))
                )
            else:
                result = await db.execute(
                    select(User).where(User.email == user_id)
                )
            user = result.scalar_one_or_none()
            if user:
                _coerce_user_type(user, payload)
                return user
    except Exception:
        pass  # Not a valid JWT — fall through to service account check

    # --- Try service account token ---
    sa_user = await _lookup_service_account(raw_token, db)
    if sa_user:
        return sa_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def resolve_scenario_user_id(
    scenario_id: int,
    user: User,
    db: AsyncSession,
) -> int:
    """Resolve the ScenarioUser ID for a given (scenario_id, user_id) pair.

    Raises HTTPException 404 if the user is not a participant in the scenario.
    """
    from app.models.participant import ScenarioUser

    result = await db.execute(
        select(ScenarioUser.id).where(
            ScenarioUser.scenario_id == scenario_id,
            ScenarioUser.user_id == user.id,
        )
    )
    scenario_user_id = result.scalar_one_or_none()
    if scenario_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User is not a participant in scenario {scenario_id}",
        )
    return scenario_user_id

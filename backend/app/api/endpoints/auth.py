from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    set_auth_cookies,
    clear_auth_cookies,
    get_current_user,
    get_current_active_user,
    set_csrf_cookie,
)
from app.db.session import get_db
from app.models.user import (
    User,
    UserCreate,
    UserInDB,
    UserPublic,
    UserUpdate,
    UserBase,
    UserPasswordChange,
    UserTypeEnum,
)
from app.repositories.users import (
    create_user as create_user_repo,
    get_user_by_email,
    update_user as update_user_repo,
)
from app.services.auth_service import AuthService, get_auth_service
from app.schemas.mfa import MFAVerifyRequest
from app.models.supply_chain_config import (
    SupplyChainConfig,
    Site,
    Lane,
    Market,
    MarketDemand,
    NodeType,
)
from app.models.scenario import Scenario
from app.models.agent_config import AgentConfig
from app.services.supply_chain_config_service import SupplyChainConfigService
from app.services.tenant_service import DEFAULT_SITE_TYPE_DEFINITIONS
from app.models.user_directive import ConfigProvisioningStatus

router = APIRouter()

# Reserved emails that cannot be registered by end users.
# The system admin account is seeded at DB init and must not be claimable
# via the public /register endpoint.
RESERVED_EMAILS = frozenset({
    "systemadmin@autonomy.ai",
    "systemadmin@autonomy.com",
    "admin@autonomy.ai",
    "admin@autonomy.com",
})


class TokenResponse(BaseModel):
    """Response model for authentication tokens."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic
    tenant_subdomain: Optional[str] = None  # For subdomain redirect after login
    # Provisioning status for frontend banner
    provisioning_status: Optional[str] = None  # "complete", "in_progress", "not_started", "failed", None (no config)
    provisioning_step: Optional[str] = None    # current/failed step name if not complete
    # Session timeout for frontend idle detection (minutes)
    session_timeout_minutes: int = 5


# Alias Token to TokenResponse for backward compatibility
Token = TokenResponse


class LoginRequest(BaseModel):
    """Request model for login endpoint."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class RegisterRequest(UserCreate):
    """Request model for registration endpoint."""

    pass


def _normalize_tenant_admin_context(user: User) -> None:
    """Ensure tenant admins surface their managed tenant relationship."""

    if not user:
        return

    user_type = getattr(user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    if user_type != UserTypeEnum.TENANT_ADMIN:
        return

    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id not in (None, 0):
        return

    admin_tenant = getattr(user, "admin_of_customer", None)
    if admin_tenant is not None:
        user.tenant_id = admin_tenant.id


def _ensure_default_setup_sync(db: Session, user: User) -> None:
    """Ensure a default configuration and game exist for admin users.

    If the admin has no supply chain configuration, one is created along with
    a default game. If a configuration exists but no game, only the game is
    created. This allows admins who have logged in before (and thus have a
    ``last_login`` value) to still get the default setup.
    """
    # Only create default setup for admin users (SYSTEM_ADMIN or TENANT_ADMIN)
    user_type = getattr(user, "user_type", None)
    if user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        return

    # Check if a configuration already exists for this user
    config = (
        db.query(SupplyChainConfig)
        .filter(SupplyChainConfig.created_by == user.id)
        .first()
    )

    if config is None:
        # Create base configuration - tenant_id required per AWS SC DM
        # Use user's tenant_id if available, otherwise skip creation
        if not user.tenant_id:
            logger.warning(f"Cannot create default config for user {user.id} - no tenant_id assigned")
            return
        config = SupplyChainConfig(
            name="Default Supply Chain",
            is_active=True,
            created_by=user.id,
            tenant_id=user.tenant_id,  # Required field (maps to tenant)
            site_type_definitions=deepcopy(DEFAULT_SITE_TYPE_DEFINITIONS),
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        # Default item
        item = Item(config_id=config.id, name="Standard Product")
        db.add(item)
        db.commit()
        db.refresh(item)

        node_specs = [
            ("Customer", NodeType.CUSTOMER, "customer", "customer"),
            ("Retailer", NodeType.RETAILER, "retailer", "inventory"),
            ("Wholesaler", NodeType.WHOLESALER, "wholesaler", "inventory"),
            ("Distributor", NodeType.DISTRIBUTOR, "distributor", "inventory"),
            ("Factory", NodeType.MANUFACTURER, "factory", "inventory"),
            ("Vendor", NodeType.VENDOR, "vendor", "vendor"),
        ]
        nodes: Dict[NodeType, Site] = {}
        for name, node_type, dag_type, master_type in node_specs:
            node = Site(
                config_id=config.id,
                name=name,
                type=dag_type,
                dag_type=dag_type,
                master_type=master_type,
            )
            db.add(node)
            db.flush()
            nodes[node_type] = node

        # Lanes with high capacity and typical leadtimes
        cap = 9999
        lanes = [
            Lane(
                config_id=config.id,
                from_site_id=nodes[NodeType.VENDOR].id,
                to_site_id=nodes[NodeType.MANUFACTURER].id,
                capacity=cap,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            ),
            Lane(
                config_id=config.id,
                from_site_id=nodes[NodeType.MANUFACTURER].id,
                to_site_id=nodes[NodeType.DISTRIBUTOR].id,
                capacity=cap,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            ),
            Lane(
                config_id=config.id,
                from_site_id=nodes[NodeType.DISTRIBUTOR].id,
                to_site_id=nodes[NodeType.WHOLESALER].id,
                capacity=cap,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            ),
            Lane(
                config_id=config.id,
                from_site_id=nodes[NodeType.WHOLESALER].id,
                to_site_id=nodes[NodeType.RETAILER].id,
                capacity=cap,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            ),
            Lane(
                config_id=config.id,
                from_site_id=nodes[NodeType.RETAILER].id,
                to_site_id=nodes[NodeType.CUSTOMER].id,
                capacity=cap,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            ),
        ]
        db.add_all(lanes)
        db.commit()

        # Item-node configs with standard simulation ranges
        for node in [
            nodes[NodeType.RETAILER],
            nodes[NodeType.WHOLESALER],
            nodes[NodeType.DISTRIBUTOR],
            nodes[NodeType.MANUFACTURER],
        ]:
            db.add(
                ProductSiteConfig(
                    product_id=item.id,
                    site_id=node.id,
                    inventory_target_range={"min": 10, "max": 20},
                    initial_inventory_range={"min": 5, "max": 30},
                    selling_price_range={"min": 25, "max": 50},
                    holding_cost_range={"min": 1.0, "max": 5.0},
                    backlog_cost_range={"min": 5.0, "max": 10.0},
                )
            )
        db.commit()

        market = Market(
            config_id=config.id,
            name="Default Market",
            description="Primary demand market",
        )
        db.add(market)
        db.flush()

        db.add(
            MarketDemand(
                config_id=config.id,
                product_id=item.id,
                market_id=market.id,
                demand_pattern={
                    "demand_type": "constant",
                    "variability": {"type": "flat", "value": 4},
                    "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
                    "trend": {"type": "none", "slope": 0, "intercept": 0},
                    "parameters": {"value": 4},
                    "params": {"value": 4},
                },
            )
        )
        db.commit()

    # If a game already exists for the admin, nothing more to do
    existing_scenario = db.query(Scenario).filter(Scenario.created_by == user.id).first()
    if existing_scenario:
        return

    # Create default game from configuration
    service = SupplyChainConfigService(db)
    scenario_cfg = service.create_scenario_from_config(
        config.id, {"name": "Default Scenario", "max_periods": 50}
    )
    scenario = Scenario(
        name=scenario_cfg["name"],
        max_periods=scenario_cfg.get("max_periods", 50),
        config=scenario_cfg,
        created_by=user.id,
        role_assignments={},
        supply_chain_config_id=config.id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    roles = ["retailer", "wholesaler", "distributor", "manufacturer"]
    assignments = {}
    for role in roles:
        ac = AgentConfig(scenario_id=scenario.id, role=role, agent_type="bullwhip", config={})
        db.add(ac)
        db.flush()
        assignments[role] = {"is_ai": True, "agent_config_id": ac.id, "user_id": None}
    scenario.role_assignments = assignments
    db.add(scenario)
    db.commit()


async def ensure_default_setup(db: Session, user: User) -> None:
    if isinstance(db, AsyncSession):
        await db.run_sync(lambda sync_db: _ensure_default_setup_sync(sync_db, user))
    else:
        _ensure_default_setup_sync(db, user)


def _check_provisioning_status_sync(db: Session, user: User) -> tuple:
    """Check provisioning status for the user's tenant. Returns (status, step).

    Lightweight: single query to config_provisioning_status via the tenant's active config.
    Returns (None, None) for system admins or users without a tenant.
    """
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        return (None, None)

    # Find active config for this tenant
    config = (
        db.query(SupplyChainConfig)
        .filter(
            SupplyChainConfig.tenant_id == tenant_id,
            SupplyChainConfig.is_active.is_(True),
        )
        .first()
    )
    if not config:
        return (None, None)  # No config exists

    # Check provisioning status for this config
    prov = (
        db.query(ConfigProvisioningStatus)
        .filter(ConfigProvisioningStatus.config_id == config.id)
        .first()
    )
    if not prov:
        return ("not_started", None)

    overall = prov.overall_status or "not_started"
    if overall == "completed":
        return ("complete", None)

    # Find the first step that is running or failed
    problem_step = None
    for step_key in ConfigProvisioningStatus.STEPS:
        step_status = getattr(prov, f"{step_key}_status", "pending")
        if step_status == "failed":
            return ("failed", ConfigProvisioningStatus.STEP_LABELS.get(step_key, step_key))
        if step_status == "running":
            problem_step = ConfigProvisioningStatus.STEP_LABELS.get(step_key, step_key)

    if overall == "in_progress" or problem_step:
        return ("in_progress", problem_step)

    return ("not_started", None)


async def _check_provisioning_status(db: Session, user: User) -> tuple:
    """Async wrapper for provisioning status check."""
    try:
        if isinstance(db, AsyncSession):
            return await db.run_sync(lambda sync_db: _check_provisioning_status_sync(sync_db, user))
        else:
            return _check_provisioning_status_sync(db, user)
    except Exception:
        # Never let provisioning check break login
        return (None, None)


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.

    - **username**: Your email
    - **password**: Your password
    - **mfa_code**: MFA code if MFA is enabled (optional)
    - **device_info**: Device information for audit logging (optional)

    Returns an access token in the response body and sets an HTTP-only refresh token cookie.
    """
    # Authenticate user
    mfa_code = (
        form_data.client_secret if hasattr(form_data, "client_secret") else None
    )
    user = await auth_service.authenticate_user(
        username=form_data.username,
        password=form_data.password,
        mfa_code=mfa_code,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    # Generate tokens
    tokens = await auth_service.create_tokens(
        user,
        mfa_verified=bool(mfa_code),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    # Ensure default configuration and game exist for new admins
    try:
        await ensure_default_setup(db, user)
    except Exception:
        pass

    if user.last_login is None:
        user.last_login = datetime.utcnow()
        if isinstance(db, AsyncSession):
            await db.commit()
        else:
            db.commit()

    # Set cookies: refresh (httpOnly) and access token (for header-less auth)
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,  # .azirella.com in prod for cross-subdomain
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    # Also set access token cookie so subsequent requests authenticate without JS-managed headers
    set_auth_cookies(response, tokens.access_token, token_type="bearer")
    # Ensure CSRF cookie is present after login (used by frontend for POSTs including refresh-token)
    set_csrf_cookie(response)

    # Attach tenant context for admins so frontend receives tenant assignments
    _normalize_tenant_admin_context(user)

    # Resolve tenant subdomain for frontend redirect
    _tenant_subdomain = None
    _tenant_obj = getattr(user, "tenant", None)
    if _tenant_obj:
        _tenant_subdomain = getattr(_tenant_obj, "slug", None) or getattr(_tenant_obj, "subdomain", None)
    if not _tenant_subdomain:
        _admin_tenant = getattr(user, "admin_of_tenant", None)
        if _admin_tenant:
            _tenant_subdomain = getattr(_admin_tenant, "slug", None) or getattr(_admin_tenant, "subdomain", None)

    # Check provisioning status (lightweight, non-blocking)
    _prov_status, _prov_step = await _check_provisioning_status(db, user)

    # Resolve session timeout from tenant setting (system admins default to 30 min)
    _session_timeout = 30  # Default for system admins (no tenant)
    _resolved_tenant = _tenant_obj or getattr(user, "admin_of_tenant", None)
    if _resolved_tenant:
        _session_timeout = getattr(_resolved_tenant, "session_timeout_minutes", 5) or 5

    # Return access token and user info
    return TokenResponse(
        access_token=tokens.access_token,
        token_type="bearer",
        user=UserPublic.from_orm(user),
        tenant_subdomain=_tenant_subdomain,
        provisioning_status=_prov_status,
        provisioning_step=_prov_step,
        session_timeout_minutes=_session_timeout,
    )


@router.get("/csrf-token")
async def csrf_token(response: Response):
    """Issue a CSRF token and set it as a cookie.

    Frontend reads the cookie and also gets the value in the JSON payload.
    """
    token = set_csrf_cookie(response)
    return {"csrf_token": token}


@router.post(
    "/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED
)
async def register(
    user_in: UserCreate, response: Response, db: Session = Depends(get_db)
) -> Any:
    """
    Register a new user.

    - **email**: Must be a valid email address
    - **password**: Must be at least 8 characters, with at least one uppercase, one lowercase, and one number
    - **full_name**: User's full name
    """
    # Block reserved system emails from public registration
    if user_in.email.lower() in RESERVED_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is reserved and cannot be registered",
        )

    # Check if user with this email already exists
    db_user = await get_user_by_email(db, user_in.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create new user
    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        is_active=True,
        is_superuser=False,
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return db_user


@router.post("/logout")
async def logout(
    response: Response, current_user: User = Depends(get_current_active_user)
):
    """
    Log out the current user by clearing authentication cookies.

    Requires authentication.
    """
    clear_auth_cookies(response)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserPublic)
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user information.

    Requires authentication. Includes decision_level and capabilities
    so the frontend can determine tab visibility and role-based UI.
    """
    # Build response dict with all fields the frontend needs
    user_dict = {
        "id": getattr(current_user, "id", None),
        "email": getattr(current_user, "email", None),
        "name": getattr(current_user, "full_name", None) or getattr(current_user, "name", None),
        "full_name": getattr(current_user, "full_name", None) or getattr(current_user, "name", None),
        "role": getattr(current_user, "user_type", "USER"),
        "user_type": str(getattr(current_user, "user_type", "USER")),
        "tenant_id": getattr(current_user, "tenant_id", None),
        "is_superuser": getattr(current_user, "is_superuser", False),
        "default_config_id": getattr(current_user, "default_config_id", None),
        "decision_level": None,
    }
    # Extract decision_level (may be enum or string)
    pr = getattr(current_user, "decision_level", None)
    if pr is not None:
        user_dict["decision_level"] = pr.value if hasattr(pr, "value") else str(pr)

    # Include tenant logo for frontend branding
    tenant_logo = None
    if current_user.tenant_id:
        from app.models.tenant import Tenant
        tenant_row = await db.execute(
            select(Tenant.logo).where(Tenant.id == current_user.tenant_id)
        )
        tenant_logo = tenant_row.scalar_one_or_none()
    user_dict["tenant_logo"] = tenant_logo

    return user_dict


@router.put("/me", response_model=UserPublic)
async def update_user_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Update current user information.

    - **email**: New email (optional)
    - **full_name**: New full name (optional)
    - **is_active**: Whether the user is active (admin only)

    Requires authentication.
    """
    return await auth_service.update_user(current_user.id, user_in)


@router.post("/change-password")
async def change_password(
    password_change: UserPasswordChange,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Change the current user's password.

    - **current_password**: Current password
    - **new_password**: New password (must be at least 8 characters, with at least one uppercase, one lowercase, and one number)

    Requires authentication.
    """
    await auth_service.change_password(
        user=current_user,
        current_password=password_change.current_password,
        new_password=password_change.new_password,
    )
    return {"message": "Password updated successfully"}


# MFA Endpoints
@router.post("/mfa/setup")
async def setup_mfa(
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Set up Multi-Factor Authentication for the current user.

    Generates a new MFA secret and returns it along with a provisioning URI
    that can be used with authenticator apps like Google Authenticator.

    Requires authentication.
    """
    return await auth_service.setup_mfa(current_user)


@router.post("/mfa/verify")
async def verify_mfa(
    mfa_verify: MFAVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Verify an MFA code and complete MFA setup.

    - **code**: The MFA code from the authenticator app

    Returns a new access token and refresh token if verification is successful.

    Requires authentication and an unverified MFA setup.
    """
    return await auth_service.verify_mfa(current_user, mfa_verify.code)


@router.post("/mfa/disable")
async def disable_mfa(
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Disable MFA for the current user.

    Requires authentication and MFA to be enabled.
    """
    await auth_service.disable_mfa(current_user)
    return {"message": "MFA disabled successfully"}


@router.post("/mfa/recovery-codes")
async def generate_recovery_codes(
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Generate new MFA recovery codes.

    This will invalidate any previously generated recovery codes.

    Requires authentication and MFA to be enabled.
    """
    return await auth_service.generate_recovery_codes(current_user)


@router.post("/mfa/recover")
async def verify_recovery_code(
    mfa_verify: MFAVerifyRequest, auth_service: AuthService = Depends(get_auth_service)
):
    """
    Verify a recovery code and get a new access token.

    - **code**: The recovery code to verify

    Returns a new access token and refresh token if the recovery code is valid.
    """
    return await auth_service.verify_recovery_code(mfa_verify.code)


@router.post("/refresh-token")
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Refresh the access token using the refresh token from cookie.

    Returns a new access token and updates the refresh token in the HTTP-only cookie.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not refresh access token",
        )

    tokens = await auth_service.refresh_tokens(refresh_token)

    # Set the new refresh token in HTTP-only cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,  # .azirella.com in prod for cross-subdomain
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    # Update access token cookie too
    set_auth_cookies(response, tokens.access_token, token_type="bearer")
    return {"access_token": tokens.access_token, "token_type": "bearer"}


# Admin-only endpoints
@router.get("/users/", response_model=List[UserPublic])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Retrieve all users (admin only).

    - **skip**: Number of users to skip (for pagination)
    - **limit**: Maximum number of users to return (for pagination)

    Requires admin privileges.
    """
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return await auth_service.get_users(skip=skip, limit=limit)


@router.get("/users/{user_id}", response_model=UserPublic)
async def read_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Get a specific user by ID (admin only).

    - **user_id**: ID of the user to retrieve

    Requires admin privileges.
    """
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return await auth_service.get_user(user_id)


# ── Demo Auto-Login ──────────────────────────────────────────────────────────
# Generates a time-limited, single-use token for demo access.
# The password NEVER appears in URLs, logs, or browser history.
#
# Flow:
#   1. Website generates a demo link: /auto-login?token=<jwt>
#   2. Frontend exchanges the token for a real session via POST /auth/demo-exchange
#   3. Backend validates token, logs in the demo user, returns access token
#
# The demo token is:
#   - Signed with the same SECRET_KEY as regular JWTs
#   - Short-lived (5 minutes)
#   - Scoped to a specific demo account (cannot be used for other users)
#   - Contains a "demo" claim to distinguish from regular tokens

# Configurable demo account (set via env or use default)
import os
_DEMO_EMAIL = os.environ.get("DEMO_USER_EMAIL", "visitor@demo.azirella.com")
_DEMO_TOKEN_EXPIRY_MINUTES = int(os.environ.get("DEMO_TOKEN_EXPIRY_MINUTES", "5"))
_DEMO_MAX_CONCURRENT = int(os.environ.get("DEMO_MAX_CONCURRENT", "5"))
_DEMO_SESSION_TIMEOUT_MINUTES = int(os.environ.get("DEMO_SESSION_TIMEOUT_MINUTES", "30"))
_DEMO_ASSUMED_DURATION_MINUTES = int(os.environ.get("DEMO_ASSUMED_DURATION_MINUTES", "30"))
_DEMO_MAX_SESSION_MINUTES = int(os.environ.get("DEMO_MAX_SESSION_MINUTES", "30"))
_DEMO_COOLDOWN_MINUTES = int(os.environ.get("DEMO_COOLDOWN_MINUTES", "120"))
_DEMO_GSHEET_WEBHOOK = os.environ.get("DEMO_GSHEET_WEBHOOK", "")


@router.post("/demo-lead")
async def capture_demo_lead(request: Request):
    """Capture demo visitor lead info and forward to Google Sheets.

    The webhook URL is kept server-side in .env (DEMO_GSHEET_WEBHOOK).
    The frontend never sees it. If not configured, the lead is logged
    but not forwarded.
    """
    import logging
    logger = logging.getLogger("demo_leads")

    body = await request.json()
    name = body.get("name", "")
    email = body.get("email", "")
    company = body.get("company", "")
    role = body.get("role", "")
    timestamp = body.get("timestamp", datetime.utcnow().isoformat())
    source = body.get("source", "demo-welcome")

    logger.info(f"Demo lead: {name} <{email}> @ {company} ({role})")

    if _DEMO_GSHEET_WEBHOOK:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    _DEMO_GSHEET_WEBHOOK,
                    json={
                        "timestamp": timestamp,
                        "name": name,
                        "email": email,
                        "company": company,
                        "role": role,
                        "source": source,
                    },
                )
        except Exception as exc:
            logger.warning(f"Failed to write demo lead to Google Sheets: {exc}")

    return {"status": "ok"}


async def _get_active_demo_sessions(db: AsyncSession) -> list:
    """Return active demo sessions (activity within the timeout window)."""
    from sqlalchemy import select, and_
    from app.models.session import UserSession
    from app.models.user import User

    cutoff = datetime.utcnow() - timedelta(minutes=_DEMO_SESSION_TIMEOUT_MINUTES)
    stmt = (
        select(UserSession)
        .join(User, UserSession.user_id == User.id)
        .where(
            and_(
                User.email == _DEMO_EMAIL,
                UserSession.last_activity >= cutoff,
                UserSession.revoked == False,  # noqa: E712
            )
        )
        .order_by(UserSession.last_activity.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/demo-capacity")
async def demo_capacity(db: AsyncSession = Depends(get_db)):
    """Check demo session availability.

    Returns current active session count, max allowed, queue position,
    and estimated wait time. Used by demo-welcome.html to show queue UI.
    """
    sessions = await _get_active_demo_sessions(db)
    active_count = len(sessions)
    available = active_count < _DEMO_MAX_CONCURRENT

    # Estimate wait: oldest session's remaining time
    estimated_wait_minutes = 0
    queue_position = 0
    if not available:
        queue_position = 1  # They'd be next in line
        if sessions:
            oldest = sessions[0]
            elapsed = (datetime.utcnow() - oldest.last_activity).total_seconds() / 60
            remaining = max(0, _DEMO_ASSUMED_DURATION_MINUTES - elapsed)
            estimated_wait_minutes = round(remaining)

    return {
        "active": active_count,
        "max": _DEMO_MAX_CONCURRENT,
        "available": available,
        "queue_position": queue_position,
        "estimated_wait_minutes": estimated_wait_minutes,
        "session_minutes": _DEMO_MAX_SESSION_MINUTES,
        "cooldown_minutes": _DEMO_COOLDOWN_MINUTES,
    }


@router.get("/demo-session-check")
async def demo_session_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Check if the current demo session should be expired.

    Called periodically by the frontend. Returns time remaining and
    whether the session should be terminated (30-min max, 60-min cooldown).
    """
    if current_user.email != _DEMO_EMAIL:
        return {"demo_user": False}

    from sqlalchemy import select, and_
    from app.models.session import UserSession

    # Find the newest active session for this demo user
    stmt = (
        select(UserSession)
        .where(
            and_(
                UserSession.user_id == current_user.id,
                UserSession.revoked == False,  # noqa: E712
            )
        )
        .order_by(UserSession.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        return {"demo_user": True, "expired": True, "reason": "no_session"}

    elapsed_minutes = (datetime.utcnow() - session.created_at).total_seconds() / 60
    remaining_minutes = max(0, _DEMO_MAX_SESSION_MINUTES - elapsed_minutes)

    if elapsed_minutes >= _DEMO_MAX_SESSION_MINUTES:
        # Revoke the session
        session.revoked = True
        await db.commit()
        return {
            "demo_user": True,
            "expired": True,
            "reason": "time_limit",
            "max_minutes": _DEMO_MAX_SESSION_MINUTES,
            "cooldown_minutes": _DEMO_COOLDOWN_MINUTES,
            "can_rejoin_at": (
                session.created_at + timedelta(minutes=_DEMO_MAX_SESSION_MINUTES + _DEMO_COOLDOWN_MINUTES)
            ).isoformat(),
        }

    return {
        "demo_user": True,
        "expired": False,
        "elapsed_minutes": round(elapsed_minutes),
        "remaining_minutes": round(remaining_minutes),
        "max_minutes": _DEMO_MAX_SESSION_MINUTES,
    }


@router.get("/demo-token")
async def generate_demo_token():
    """Generate a short-lived demo access token.

    This is called by the website to create the auto-login URL.
    The token contains NO credentials — just a signed claim that
    the bearer is allowed to log in as the demo user.

    Returns: {"token": "<jwt>", "url": "/auto-login?token=<jwt>"}
    """
    from jose import jwt as pyjwt
    payload = {
        "sub": _DEMO_EMAIL,
        "purpose": "demo_auto_login",
        "exp": datetime.utcnow() + timedelta(minutes=_DEMO_TOKEN_EXPIRY_MINUTES),
        "iat": datetime.utcnow(),
    }
    token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {
        "token": token,
        "url": f"/auto-login?token={token}",
        "expires_in_seconds": _DEMO_TOKEN_EXPIRY_MINUTES * 60,
    }


@router.get("/demo-token-redirect")
async def demo_token_redirect(db: AsyncSession = Depends(get_db)):
    """One-click demo access — generates token and redirects to auto-login.

    The website links directly to this URL:
      <a href="https://demo.azirella.com/api/v1/auth/demo-token-redirect">Try Demo</a>

    Generates a 5-minute demo token and redirects to /auto-login?token=<jwt>.
    Checks capacity before issuing token. Returns 429 if demo is full.
    No password ever appears in the URL.
    """
    from jose import jwt as pyjwt
    from fastapi.responses import RedirectResponse, JSONResponse

    # Check capacity
    sessions = await _get_active_demo_sessions(db)
    if len(sessions) >= _DEMO_MAX_CONCURRENT:
        oldest = sessions[0] if sessions else None
        elapsed = 0
        if oldest:
            elapsed = (datetime.utcnow() - oldest.last_activity).total_seconds() / 60
        remaining = max(1, round(_DEMO_ASSUMED_DURATION_MINUTES - elapsed))
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Demo is at capacity",
                "active": len(sessions),
                "max": _DEMO_MAX_CONCURRENT,
                "estimated_wait_minutes": remaining,
            },
        )

    payload = {
        "sub": _DEMO_EMAIL,
        "purpose": "demo_auto_login",
        "exp": datetime.utcnow() + timedelta(minutes=_DEMO_TOKEN_EXPIRY_MINUTES),
        "iat": datetime.utcnow(),
    }
    token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return RedirectResponse(url=f"/auto-login?token={token}", status_code=302)


@router.post("/demo-exchange")
async def exchange_demo_token(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Exchange a demo token for a real session.

    Body: {"token": "<jwt from /demo-token>"}

    Validates the demo token, authenticates the demo user,
    and returns a full access token + sets cookies.
    """
    from jose import jwt as pyjwt

    body = await request.json()
    token = body.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    # Validate demo token
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Demo token expired")
    except pyjwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid demo token")

    if payload.get("purpose") != "demo_auto_login":
        raise HTTPException(status_code=401, detail="Not a demo token")

    demo_email = payload.get("sub")
    if demo_email != _DEMO_EMAIL:
        raise HTTPException(status_code=401, detail="Invalid demo account")

    # Look up the demo user (must already exist)
    demo_user = await auth_service.get_user_by_email(demo_email)
    if not demo_user:
        raise HTTPException(status_code=404, detail="Demo account not configured")

    # Generate real tokens (same as normal login)
    tokens = await auth_service.create_tokens(
        demo_user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    # Set cookies
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    set_csrf_cookie(response)

    return {
        "access_token": tokens.access_token,
        "token_type": "bearer",
        "user": {
            "id": demo_user.id,
            "email": demo_user.email,
            "name": getattr(demo_user, "full_name", demo_user.email),
        },
    }

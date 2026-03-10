from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
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
    Node,
    Lane,
    Market,
    MarketDemand,
    NodeType,
)
from app.models.scenario import Scenario
from app.models.agent_config import AgentConfig
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from app.services.supply_chain_config_service import SupplyChainConfigService
from app.services.tenant_service import DEFAULT_SITE_TYPE_DEFINITIONS

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
            ("Market Demand", NodeType.MARKET_DEMAND, "market_demand", "market_demand"),
            ("Retailer", NodeType.RETAILER, "retailer", "inventory"),
            ("Wholesaler", NodeType.WHOLESALER, "wholesaler", "inventory"),
            ("Distributor", NodeType.DISTRIBUTOR, "distributor", "inventory"),
            ("Factory", NodeType.MANUFACTURER, "factory", "inventory"),
            ("Market Supply", NodeType.MARKET_SUPPLY, "market_supply", "market_supply"),
        ]
        nodes: Dict[NodeType, Node] = {}
        for name, node_type, dag_type, master_type in node_specs:
            node = Node(
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
                from_site_id=nodes[NodeType.MARKET_SUPPLY].id,
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
                to_site_id=nodes[NodeType.MARKET_DEMAND].id,
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
        config.id, {"name": "Default Scenario", "max_rounds": 50}
    )
    scenario = Scenario(
        name=scenario_cfg["name"],
        max_rounds=scenario_cfg.get("max_rounds", 50),
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
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    # Also set access token cookie so subsequent requests authenticate without JS-managed headers
    set_auth_cookies(response, tokens.access_token, token_type="bearer")
    # Ensure CSRF cookie is present after login (used by frontend for POSTs including refresh-token)
    set_csrf_cookie(response)

    # Attach tenant context for admins so frontend receives tenant assignments
    _normalize_tenant_admin_context(user)

    # Return access token and user info
    return TokenResponse(
        access_token=tokens.access_token,
        token_type="bearer",
        user=UserPublic.from_orm(user),
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
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current user information.

    Requires authentication.
    """
    _normalize_customer_admin_context(current_user)
    return current_user


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
        secure=not settings.DEBUG,
        samesite="lax",
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

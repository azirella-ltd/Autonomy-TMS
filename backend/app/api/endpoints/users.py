from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Any, Optional
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ... import models
from ...schemas.user import User, UserCreate, UserUpdate, UserInDB, UserPasswordChange
from ...models.user import UserTypeEnum
from ...models.supply_chain_config import SupplyChainConfig
from ...db.session import get_db, sync_engine
from ...core.security import get_current_active_user
from ...services.user_service import UserService
from ...services.rbac_service import RBACService

router = APIRouter()

# Create a sync session factory for UserService
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

def get_sync_db() -> Session:
    """Get a sync database session for services that aren't async yet."""
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_user_service(db: Session = Depends(get_sync_db)) -> UserService:
    """Dependency to get an instance of UserService."""
    return UserService(db)

@router.get("/", response_model=List[User])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    user_type: Optional[str] = None,
    user_service: UserService = Depends(get_user_service),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Retrieve all users (admin only).
    """
    return user_service.list_accessible_users(
        current_user=current_user,
        skip=skip,
        limit=limit,
        user_type=user_type,
    )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: dict,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create new user (admin only).
    Accepts capabilities list alongside standard user fields.
    """
    user_service = UserService(db)

    # Extract capabilities before passing to model create
    capabilities = user_in.pop("capabilities", None)

    create_data = UserCreate(**user_in)
    new_user = user_service.create_user(create_data, current_user)

    # If capabilities were provided, sync them via RBAC
    if capabilities and isinstance(capabilities, list) and new_user:
        from app.services.rbac_service import RBACService
        rbac_service = RBACService(db)
        user_id = new_user.id if hasattr(new_user, 'id') else new_user.get('id')
        tenant_id = new_user.tenant_id if hasattr(new_user, 'tenant_id') else new_user.get('tenant_id')
        if user_id:
            rbac_service.sync_user_capabilities(
                user_id=user_id,
                capability_names=capabilities,
                tenant_id=tenant_id
            )

    return new_user

@router.delete("/{user_id}", response_model=dict)
async def delete_user(
    user_id: int,
    replacement_admin_id: Optional[int] = None,
    user_service: UserService = Depends(get_user_service),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Delete a user (admin only).
    """
    return user_service.delete_user(user_id, current_user, replacement_admin_id)

@router.put("/{user_id}")
async def update_user(
    user_id: int,
    user_in: dict,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Update a user (admin or self).
    Accepts capabilities list alongside standard user fields.
    """
    user_service = UserService(db)

    # Extract capabilities before passing to model update
    capabilities = user_in.pop("capabilities", None)

    # Update model fields (email, name, decision_level, etc.)
    update_data = UserUpdate(**{k: v for k, v in user_in.items() if v is not None})
    updated_user = user_service.update_user(user_id, update_data, current_user)

    # If capabilities were provided, sync them via RBAC
    if capabilities is not None and isinstance(capabilities, list):
        from app.services.rbac_service import RBACService
        rbac_service = RBACService(db)
        target_user = user_service.get_user(user_id)
        if target_user:
            rbac_service.sync_user_capabilities(
                user_id=user_id,
                capability_names=capabilities,
                tenant_id=target_user.tenant_id
            )

    return updated_user

@router.post("/{user_id}/change-password", response_model=dict)
async def change_password(
    user_id: int,
    password_change: UserPasswordChange,
    user_service: UserService = Depends(get_user_service),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Change a user's password.
    """
    return user_service.change_password(
        user_id=user_id,
        current_password=password_change.current_password,
        new_password=password_change.new_password,
        current_user=current_user
    )

@router.get("/me", response_model=User)
async def read_user_me(
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get current user.
    """
    return current_user

@router.get("/{user_id}")
async def read_user(
    user_id: int,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get a specific user by ID (admin only).
    Returns user fields including decision_level.
    """
    user_service = UserService(db)
    user = user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission check
    allowed = (
        current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
        or current_user.id == user_id
        or (current_user.user_type == UserTypeEnum.TENANT_ADMIN and user.tenant_id == current_user.tenant_id)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Build response with decision_level and scopes
    dl = user.decision_level
    if dl and hasattr(dl, 'value'):
        dl = dl.value

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "tenant_id": user.tenant_id,
        "user_type": user.user_type.value if hasattr(user.user_type, 'value') else str(user.user_type),
        "is_active": user.is_active,
        "decision_level": dl,
        "default_config_id": user.default_config_id,
        "site_scope": user.site_scope,
        "product_scope": user.product_scope,
    }



# ===== RBAC Capability Endpoints =====

class UserCapabilitiesUpdate(BaseModel):
    """Request model for updating user capabilities."""
    capabilities: List[str]


@router.put("/{user_id}/capabilities", response_model=dict)
async def update_user_capabilities(
    user_id: int,
    payload: UserCapabilitiesUpdate,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Update a user's capabilities via RBAC roles.

    This creates or updates a custom role for the user with the specified capabilities.

    Permissions:
    - Group Admins can update users in their customer organization
    - System Admins can update any user

    Args:
        user_id: User ID to update
        payload: List of capability names
        db: Database session
        current_user: Currently authenticated user

    Returns:
        Success message with updated capabilities
    """
    # Get services
    user_service = UserService(db)
    rbac_service = RBACService(db)

    # Get target user
    target_user = user_service.get_user(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission checks
    is_system_admin = current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
    is_customer_admin = current_user.user_type == UserTypeEnum.TENANT_ADMIN

    # Group admins can only manage users in their customer organization
    if is_customer_admin:
        if not current_user.tenant_id or target_user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You can only manage users within your customer organization"
            )

        # Group admins cannot modify system admins
        if target_user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify system administrator capabilities"
            )

    # System admins can manage anyone except other system admins (without explicit permission)
    if not is_system_admin and not is_customer_admin:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to manage user capabilities"
        )

    # Sync user capabilities to RBAC
    success = rbac_service.sync_user_capabilities(
        user_id=user_id,
        capability_names=payload.capabilities,
        tenant_id=target_user.tenant_id
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to update user capabilities"
        )

    # Get updated capabilities
    updated_caps = rbac_service.get_user_capabilities(target_user)

    return {
        "success": True,
        "message": "User capabilities updated successfully",
        "user_id": user_id,
        "capabilities": updated_caps
    }


@router.get("/{user_id}/capabilities", response_model=dict)
async def get_user_capabilities_endpoint(
    user_id: int,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get a user's capabilities from RBAC roles.

    Permissions:
    - Users can view their own capabilities
    - Group Admins can view users in their customer organization
    - System Admins can view any user

    Args:
        user_id: User ID to query
        db: Database session
        current_user: Currently authenticated user

    Returns:
        List of capability names
    """
    # Get services
    user_service = UserService(db)
    rbac_service = RBACService(db)

    # Get target user
    target_user = user_service.get_user(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission checks
    is_system_admin = current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
    is_customer_admin = current_user.user_type == UserTypeEnum.TENANT_ADMIN
    is_self = current_user.id == user_id

    # Check permissions
    if not is_self and not is_system_admin:
        if is_customer_admin:
            if not current_user.tenant_id or target_user.tenant_id != current_user.tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only view users within your group"
                )
        else:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view user capabilities"
            )

    # Get capabilities
    capabilities = rbac_service.get_user_capabilities(target_user)

    return {
        "user_id": user_id,
        "email": target_user.email,
        "user_type": target_user.user_type.value,
        "capabilities": capabilities
    }


@router.patch("/{user_id}/status", response_model=dict)
async def update_user_status(
    user_id: int,
    is_active: bool,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Activate or deactivate a user.

    Args:
        user_id: User ID to update
        is_active: New active status
        db: Database session
        current_user: Currently authenticated user

    Returns:
        Success message
    """
    user_service = UserService(db)
    target_user = user_service.get_user(user_id)

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission checks
    is_system_admin = current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
    is_customer_admin = current_user.user_type == UserTypeEnum.TENANT_ADMIN

    if is_customer_admin:
        if not current_user.tenant_id or target_user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You can only manage users within your customer organization"
            )

    if not is_system_admin and not is_customer_admin:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to modify user status"
        )

    # Update status
    target_user.is_active = is_active
    db.commit()

    return {
        "success": True,
        "message": f"User {'activated' if is_active else 'deactivated'} successfully",
        "user_id": user_id,
        "is_active": is_active
    }


# ===== Config-Level Mode Endpoints =====

class ActiveConfigPayload(BaseModel):
    """Request payload for setting the current user's active config."""
    config_id: int


@router.put("/me/active-config", response_model=dict)
async def set_my_active_config(
    payload: ActiveConfigPayload,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Set the current user's preferred (default) supply chain config.

    The config must belong to the same tenant as the current user.
    After this call, GET /supply-chain-configs/active will return this config.

    Args:
        payload: { config_id: int }

    Returns:
        { default_config_id: int }
    """
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == payload.config_id
    ).first()

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")

    # Validate the config belongs to the user's tenant
    # System admins can use any config regardless of tenant
    user_type = current_user.user_type
    if user_type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Config not found",
            )

    # Fetch the actual DB user row (current_user may be a cached object)
    db_user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db_user.default_config_id = payload.config_id
    db.commit()

    return {"default_config_id": payload.config_id}


@router.put("/admin/users/{user_id}/default-config", response_model=dict)
async def set_user_default_config(
    user_id: int,
    payload: ActiveConfigPayload,
    db: Session = Depends(get_sync_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Admin endpoint: set another user's default supply chain config.

    Tenant admins can only set configs for users within their own tenant.
    System admins can set configs for any user.

    Args:
        user_id: Target user ID
        payload: { config_id: int }

    Returns:
        { user_id: int, default_config_id: int }
    """
    is_system_admin = current_user.user_type == UserTypeEnum.SYSTEM_ADMIN
    is_tenant_admin = current_user.user_type == UserTypeEnum.TENANT_ADMIN

    if not is_system_admin and not is_tenant_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin or system admin required",
        )

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Tenant admins can only manage users in their own tenant
    if is_tenant_admin:
        if target_user.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage users within your tenant",
            )

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == payload.config_id
    ).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")

    # Validate the config belongs to the target user's tenant
    if not is_system_admin and config.tenant_id != target_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found",
        )

    target_user.default_config_id = payload.config_id
    db.commit()

    return {"user_id": user_id, "default_config_id": payload.config_id}

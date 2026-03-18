"""
Capability Service

Provides utilities for checking user capabilities and filtering navigation.
Integrates with RBAC system for database-persisted capabilities.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload

from app.models.user import User, UserTypeEnum
from app.models.rbac import Role
from app.core.capabilities import (
    Capability,
    CapabilitySet,
    USER_CAPABILITIES,
    get_capabilities_for_user_type,
    get_navigation_capabilities,
)


def get_user_capabilities(user: User, db: Session) -> CapabilitySet:
    """
    Get all capabilities for a user.

    This considers:
    1. User type (SYSTEM_ADMIN, TENANT_ADMIN, USER)
    2. Assigned RBAC roles (from database)
    3. Custom capability overrides

    Args:
        user: User object
        db: Database session

    Returns:
        CapabilitySet containing all user capabilities
    """
    # System admins get all capabilities
    if user.is_superuser or user.user_type == UserTypeEnum.SYSTEM_ADMIN:
        return CapabilitySet({cap for cap in Capability})

    # Check powell_role first (more specific than user_type).
    # Without this, any USER with a powell_role (SC_VP, SOP_DIRECTOR, etc.)
    # would only get {VIEW_DASHBOARD, VIEW_SCENARIOS, PLAY_SCENARIO}.
    if hasattr(user, 'powell_role') and user.powell_role:
        role_caps = get_capabilities_for_user_type(user.powell_role.value)
        if role_caps.capabilities != USER_CAPABILITIES.capabilities:
            base_caps = role_caps
        else:
            base_caps = get_capabilities_for_user_type(user.user_type.value)
    else:
        base_caps = get_capabilities_for_user_type(user.user_type.value)

    # Get capabilities from RBAC roles if available
    try:
        # Eagerly load user's roles and their permissions
        user_with_roles = db.query(User).options(
            joinedload(User.roles).joinedload(Role.permissions)
        ).filter(User.id == user.id).first()

        if user_with_roles and user_with_roles.roles:
            # Collect all capability names from roles
            capability_names = set()
            for role in user_with_roles.roles:
                for permission in role.permissions:
                    capability_names.add(permission.name)

            # Convert permission names to Capability enums
            rbac_capabilities = set()
            for cap_name in capability_names:
                try:
                    # Try to match with Capability enum by value
                    for cap in Capability:
                        if cap.value == cap_name:
                            rbac_capabilities.add(cap)
                            break
                except (ValueError, AttributeError):
                    pass

            # Merge RBAC capabilities WITH base (user_type) capabilities.
            # RBAC roles extend the base — they don't replace it.  A TENANT_ADMIN
            # with a "Demo All Powell" role gets both the admin capabilities from
            # their user_type AND the planning capabilities from the role.
            if rbac_capabilities:
                merged = base_caps.capabilities | rbac_capabilities
                return CapabilitySet(merged)
    except Exception as e:
        # If RBAC query fails, fall back to base capabilities
        print(f"Error loading RBAC capabilities: {e}")
        pass

    # Fallback to user type capabilities
    return base_caps


def user_has_capability(user: User, capability: Capability, db: Session) -> bool:
    """
    Check if a user has a specific capability.

    Args:
        user: User object
        capability: Capability to check
        db: Database session

    Returns:
        True if user has the capability, False otherwise
    """
    if not user or not user.is_active:
        return False

    caps = get_user_capabilities(user, db)
    return caps.has(capability)


def user_has_any_capability(user: User, capabilities: List[Capability], db: Session) -> bool:
    """
    Check if a user has any of the given capabilities.

    Args:
        user: User object
        capabilities: List of capabilities to check
        db: Database session

    Returns:
        True if user has at least one capability, False otherwise
    """
    if not user or not user.is_active:
        return False

    caps = get_user_capabilities(user, db)
    return caps.has_any(*capabilities)


def user_has_all_capabilities(user: User, capabilities: List[Capability], db: Session) -> bool:
    """
    Check if a user has all of the given capabilities.

    Args:
        user: User object
        capabilities: List of capabilities to check
        db: Database session

    Returns:
        True if user has all capabilities, False otherwise
    """
    if not user or not user.is_active:
        return False

    caps = get_user_capabilities(user, db)
    return caps.has_all(*capabilities)


def get_filtered_navigation_for_user(user: User, db: Session) -> Dict[str, Any]:
    """
    Get navigation structure filtered by user capabilities.

    Only includes categories and items that the user has permission to access.

    Args:
        user: User object
        db: Database session

    Returns:
        Filtered navigation dictionary
    """
    if not user or not user.is_active:
        return {}

    caps = get_user_capabilities(user, db)
    nav_capabilities = get_navigation_capabilities()
    filtered_nav = {}

    for category_id, category_data in nav_capabilities.items():
        category_cap = category_data.get("category_capability")

        # Check if user has capability to access this category
        if not caps.has(category_cap):
            continue

        # Filter items within category
        filtered_items = {}
        for path, required_caps in category_data["items"].items():
            # Check if user has any of the required capabilities for this item
            if any(caps.has(cap) for cap in required_caps):
                filtered_items[path] = required_caps

        # Only include category if it has accessible items
        if filtered_items:
            filtered_nav[category_id] = {
                "category_capability": category_cap.value,
                "items": {path: [c.value for c in caps] for path, caps in filtered_items.items()}
            }

    return filtered_nav


def get_user_capabilities_list(user: User, db: Session) -> List[str]:
    """
    Get a list of all capability values for a user.

    Useful for frontend to check permissions client-side.

    Args:
        user: User object
        db: Database session

    Returns:
        List of capability string values
    """
    if not user or not user.is_active:
        return []

    caps = get_user_capabilities(user, db)

    # If user is system admin, return all capabilities
    if caps.has(Capability.SYSTEM_ADMIN):
        return [cap.value for cap in Capability]

    # Otherwise, return only their specific capabilities
    return [cap.value for cap in caps.capabilities]


def check_navigation_access(user: User, path: str, db: Session) -> bool:
    """
    Check if a user can access a specific navigation path.

    Args:
        user: User object
        path: Navigation path (e.g., "/admin/trm")
        db: Database session

    Returns:
        True if user can access the path, False otherwise
    """
    if not user or not user.is_active:
        return False

    caps = get_user_capabilities(user, db)

    # System admins can access everything
    if caps.has(Capability.SYSTEM_ADMIN):
        return True

    # Check against navigation capabilities
    nav_capabilities = get_navigation_capabilities()

    for category_data in nav_capabilities.values():
        if path in category_data["items"]:
            required_caps = category_data["items"][path]
            return any(caps.has(cap) for cap in required_caps)

    # Path not found in navigation - allow by default (for dynamic routes)
    return True


def enhance_user_data_with_capabilities(user_dict: Dict[str, Any], user: User, db: Session) -> Dict[str, Any]:
    """
    Enhance user dictionary with capability information.

    Args:
        user_dict: Dictionary representation of user
        user: User object
        db: Database session

    Returns:
        Enhanced user dictionary with 'capabilities' field
    """
    user_dict["capabilities"] = get_user_capabilities_list(user, db)
    return user_dict

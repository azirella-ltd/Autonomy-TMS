"""
API endpoints for user capabilities and permissions.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.api import deps
from app.db.session import get_sync_db
from app.models.user import User
from app.services.capability_service import (
    get_user_capabilities_list,
    get_filtered_navigation_for_user,
    check_navigation_access,
)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("/me", response_model=Dict[str, Any])
async def get_my_capabilities(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the current user's capabilities and Powell role.

    Returns:
        - capabilities: List of capability strings for UI visibility control
        - user_type: User classification (SYSTEM_ADMIN, GROUP_ADMIN, USER)
        - powell_role: Powell Framework role for landing page routing (optional)
          - SC_VP → /executive-dashboard
          - SOP_DIRECTOR → /sop-worklist
          - MPS_MANAGER → /insights/actions
          - DEMO_ALL → /executive-dashboard (has all capabilities)

    Note: powell_role determines the fixed landing page, while capabilities
    (which can be customized by group admin) control what the user can do.
    """
    capabilities = get_user_capabilities_list(current_user, db)

    # Get powell_role for routing (may be None for non-Powell users)
    powell_role = None
    if hasattr(current_user, 'powell_role') and current_user.powell_role:
        powell_role = current_user.powell_role.value

    return {
        "capabilities": capabilities,
        "user_type": current_user.user_type.value,
        "powell_role": powell_role,  # For landing page routing
    }


@router.get("/navigation", response_model=Dict[str, Any])
async def get_my_navigation(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the navigation structure filtered for the current user.

    Only includes categories and items that the user has access to.
    This ensures the frontend only shows navigation items the user can actually use.
    """
    filtered_nav = get_filtered_navigation_for_user(current_user, db)

    return {
        "navigation": filtered_nav,
        "user_type": current_user.user_type.value,
    }


@router.get("/check/{path:path}")
async def check_path_access(
    path: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Check if the current user can access a specific path.

    Args:
        path: The navigation path to check (e.g., "admin/trm")

    Returns:
        Dictionary with 'allowed' boolean
    """
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path

    has_access = check_navigation_access(current_user, path, db)

    return {
        "path": path,
        "allowed": has_access,
        "user_type": current_user.user_type.value,
    }


@router.post("/validate")
async def validate_capabilities(
    capabilities: List[str],
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Validate if the current user has specific capabilities.

    Request body: List of capability strings to check

    Returns:
        Dictionary mapping each capability to boolean (has/doesn't have)
    """
    user_caps = get_user_capabilities_list(current_user, db)
    user_caps_set = set(user_caps)

    validation_results = {
        cap: cap in user_caps_set for cap in capabilities
    }

    return {
        "results": validation_results,
        "user_type": current_user.user_type.value,
    }

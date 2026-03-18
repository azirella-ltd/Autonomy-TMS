"""
Tenant Display Preferences API

Lightweight endpoints for tenant-scoped UI preferences such as whether to
display entity names or raw IDs.  These are loaded once on login and cached
by the frontend DisplayPreferencesContext.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_admin
from app.db.session import get_sync_db
from app.models.bsc_config import DISPLAY_IDENTIFIER_CHOICES, TenantBscConfig
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenant-preferences", tags=["tenant-preferences"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class TenantPreferencesResponse(BaseModel):
    """Current display preferences for the tenant."""
    tenant_id: int
    display_identifiers: str = Field(
        default="name",
        description="'name' = show human-readable names, 'id' = show raw IDs",
    )

    class Config:
        from_attributes = True


class TenantPreferencesUpdate(BaseModel):
    """Update display preferences."""
    display_identifiers: Literal["name", "id"] = Field(
        ...,
        description="'name' = show human-readable names (best for demos), "
                    "'id' = show raw IDs (for experienced planners)",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=TenantPreferencesResponse)
def get_tenant_preferences(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
) -> TenantPreferencesResponse:
    """Return display preferences for the current user's tenant.

    Returns defaults if no config has been saved yet.
    Any authenticated tenant user can read preferences.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant preferences require a tenant-scoped user.",
        )

    cfg = (
        db.query(TenantBscConfig)
        .filter(TenantBscConfig.tenant_id == tenant_id)
        .first()
    )

    return TenantPreferencesResponse(
        tenant_id=tenant_id,
        display_identifiers=getattr(cfg, "display_identifiers", "name") if cfg else "name",
    )


@router.put("", response_model=TenantPreferencesResponse)
def update_tenant_preferences(
    payload: TenantPreferencesUpdate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_tenant_admin),
) -> TenantPreferencesResponse:
    """Update display preferences for the current user's tenant.

    Tenant admin role required.
    """
    cfg = (
        db.query(TenantBscConfig)
        .filter(TenantBscConfig.tenant_id == current_user.tenant_id)
        .first()
    )

    if cfg is None:
        cfg = TenantBscConfig(tenant_id=current_user.tenant_id)
        db.add(cfg)

    cfg.display_identifiers = payload.display_identifiers
    db.commit()
    db.refresh(cfg)

    return TenantPreferencesResponse(
        tenant_id=cfg.tenant_id,
        display_identifiers=cfg.display_identifiers,
    )

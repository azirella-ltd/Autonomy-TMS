"""
Tenant Configuration API

Tenant-admin endpoints for reading and updating per-tenant settings:
  - Agent autonomy thresholds (3D routing: urgency, likelihood, benefit)
  - Display preferences (names vs IDs)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_admin
from app.db.session import get_sync_db
from app.models.bsc_config import TenantBscConfig
from app.models.user import User

router = APIRouter(prefix="/bsc-config", tags=["bsc-config"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class BscWeightsResponse(BaseModel):
    """Current tenant configuration."""

    tenant_id: int
    urgency_threshold: float = 0.65
    likelihood_threshold: float = 0.70
    benefit_threshold: float = 0.0
    display_identifiers: str = "name"
    notes: Optional[str] = None
    updated_at: datetime
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class BscWeightsUpdate(BaseModel):
    """Update tenant configuration."""

    urgency_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0,
        description=(
            "Minimum urgency score to surface a decision for human review. "
            "Decisions at or above this are ALWAYS surfaced. Default 0.65 (High urgency)."
        ),
    )
    likelihood_threshold: float = Field(
        default=0.70, ge=0.0, le=1.0,
        description=(
            "Minimum agent confidence to auto-action routine decisions. "
            "For decisions below urgency_threshold, if likelihood >= this the agent acts alone. "
            "Default 0.70 (70% confident)."
        ),
    )
    benefit_threshold: float = Field(
        default=0.0, ge=0.0,
        description=(
            "Minimum expected benefit ($) for a decision to be auto-actioned. "
            "Set to 0 to disable (benefit does not gate auto-action)."
        ),
    )
    display_identifiers: str = Field(
        default="name",
        description="Display mode for entity identifiers: 'name' (human-readable) or 'id' (raw IDs).",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional note for this configuration.",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=BscWeightsResponse)
def get_bsc_config(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
) -> BscWeightsResponse:
    """
    Return the tenant configuration for the current user's tenant.

    Returns defaults if no config has been saved yet (should not happen —
    config is populated at tenant creation).
    """
    cfg = (
        db.query(TenantBscConfig)
        .filter(TenantBscConfig.tenant_id == current_user.tenant_id)
        .first()
    )

    if cfg is None:
        return BscWeightsResponse(
            tenant_id=current_user.tenant_id,
            urgency_threshold=0.65,
            likelihood_threshold=0.70,
            benefit_threshold=0.0,
            display_identifiers="name",
            notes=None,
            updated_at=datetime.utcnow(),
            updated_by_name=None,
        )

    updated_by_name = None
    if cfg.updated_by_id:
        updater = db.query(User).filter(User.id == cfg.updated_by_id).first()
        if updater:
            updated_by_name = getattr(updater, "full_name", None) or updater.email

    return BscWeightsResponse(
        tenant_id=cfg.tenant_id,
        urgency_threshold=cfg.urgency_threshold,
        likelihood_threshold=cfg.likelihood_threshold,
        benefit_threshold=getattr(cfg, "benefit_threshold", 0.0) or 0.0,
        display_identifiers=getattr(cfg, "display_identifiers", "name") or "name",
        notes=cfg.notes,
        updated_at=cfg.updated_at,
        updated_by_name=updated_by_name,
    )


@router.put("", response_model=BscWeightsResponse)
def update_bsc_config(
    payload: BscWeightsUpdate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_tenant_admin),
) -> BscWeightsResponse:
    """
    Update the tenant configuration.

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

    cfg.urgency_threshold = payload.urgency_threshold
    cfg.likelihood_threshold = payload.likelihood_threshold
    cfg.benefit_threshold = payload.benefit_threshold
    cfg.display_identifiers = payload.display_identifiers
    cfg.notes = payload.notes
    cfg.updated_by_id = current_user.id
    cfg.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(cfg)

    updated_by_name = getattr(current_user, "full_name", None) or current_user.email

    return BscWeightsResponse(
        tenant_id=cfg.tenant_id,
        urgency_threshold=cfg.urgency_threshold,
        likelihood_threshold=cfg.likelihood_threshold,
        benefit_threshold=getattr(cfg, "benefit_threshold", 0.0) or 0.0,
        display_identifiers=getattr(cfg, "display_identifiers", "name") or "name",
        notes=cfg.notes,
        updated_at=cfg.updated_at,
        updated_by_name=updated_by_name,
    )

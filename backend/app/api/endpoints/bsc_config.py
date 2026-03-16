"""
BSC Configuration API

Tenant-admin endpoints for reading and updating the per-tenant Balanced
Scorecard weights used by the CDT simulation calibration service.

Both cost weights represent costs to MINIMISE — higher values are worse
outcomes. The relative weights control how much each cost component
contributes to the aggregate CDT loss across all 11 TRM agents.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_admin
from app.db.session import get_sync_db
from app.models.bsc_config import TenantBscConfig
from app.models.user import User

router = APIRouter(prefix="/bsc-config", tags=["bsc-config"])

_WEIGHT_TOLERANCE = 1e-4  # Allow tiny float rounding errors in sum-to-1 check


# ── Schemas ──────────────────────────────────────────────────────────────────

class BscWeightsResponse(BaseModel):
    """Current BSC weights for the tenant."""

    tenant_id: int
    holding_cost_weight: float
    backlog_cost_weight: float
    # Reserved Phase 2+ pillars (always 0.0 until wired up)
    customer_weight: float
    operational_weight: float
    strategic_weight: float
    autonomy_threshold: float = 0.5
    notes: Optional[str]
    updated_at: datetime
    updated_by_name: Optional[str]

    class Config:
        from_attributes = True


class BscWeightsUpdate(BaseModel):
    """
    Update BSC weights.

    Phase 1 active components: holding_cost_weight + backlog_cost_weight.
    Both represent costs to MINIMISE; weights determine relative importance.
    They must sum to 1.0 (within floating-point tolerance).

    customer_weight, operational_weight, strategic_weight are accepted but
    must be 0.0 until the corresponding metrics are implemented.
    """

    holding_cost_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight for inventory holding cost (to minimise). Default 0.5.",
    )
    backlog_cost_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight for backlog / stockout cost (to minimise). Default 0.5.",
    )
    customer_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=0.0,
        description="Reserved — Phase 2 customer service pillar. Must be 0.0.",
    )
    operational_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=0.0,
        description="Reserved — Phase 2 operational pillar. Must be 0.0.",
    )
    strategic_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=0.0,
        description="Reserved — Phase 2 strategic pillar. Must be 0.0.",
    )
    autonomy_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Agent autonomy level. Combined urgency+likelihood threshold below which "
            "agents auto-action without human review. 0.0 = surface everything, "
            "1.0 = fully autonomous. Default 0.5."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional note for this configuration.",
    )

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "BscWeightsUpdate":
        total = (
            self.holding_cost_weight
            + self.backlog_cost_weight
            + self.customer_weight
            + self.operational_weight
            + self.strategic_weight
        )
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"BSC weights must sum to 1.0 (got {total:.4f}). "
                "Adjust holding_cost_weight and backlog_cost_weight so they sum to 1."
            )
        return self


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=BscWeightsResponse)
def get_bsc_config(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
) -> BscWeightsResponse:
    """
    Return the BSC weights for the current user's tenant.

    Returns defaults (holding=0.5, backlog=0.5) if no config has been saved yet.
    """
    cfg = (
        db.query(TenantBscConfig)
        .filter(TenantBscConfig.tenant_id == current_user.tenant_id)
        .first()
    )

    if cfg is None:
        return BscWeightsResponse(
            tenant_id=current_user.tenant_id,
            holding_cost_weight=0.5,
            backlog_cost_weight=0.5,
            customer_weight=0.0,
            operational_weight=0.0,
            strategic_weight=0.0,
            autonomy_threshold=0.5,
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
        holding_cost_weight=cfg.holding_cost_weight,
        backlog_cost_weight=cfg.backlog_cost_weight,
        customer_weight=cfg.customer_weight,
        operational_weight=cfg.operational_weight,
        strategic_weight=cfg.strategic_weight,
        autonomy_threshold=cfg.autonomy_threshold,
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
    Create or replace the BSC weights for the current user's tenant.

    Tenant admin role required.
    Both cost weights represent costs to MINIMISE — higher values are worse.
    """
    cfg = (
        db.query(TenantBscConfig)
        .filter(TenantBscConfig.tenant_id == current_user.tenant_id)
        .first()
    )

    if cfg is None:
        cfg = TenantBscConfig(tenant_id=current_user.tenant_id)
        db.add(cfg)

    cfg.holding_cost_weight = payload.holding_cost_weight
    cfg.backlog_cost_weight = payload.backlog_cost_weight
    cfg.customer_weight = payload.customer_weight
    cfg.operational_weight = payload.operational_weight
    cfg.strategic_weight = payload.strategic_weight
    cfg.autonomy_threshold = payload.autonomy_threshold
    cfg.notes = payload.notes
    cfg.updated_by_id = current_user.id
    cfg.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(cfg)

    updated_by_name = getattr(current_user, "full_name", None) or current_user.email

    return BscWeightsResponse(
        tenant_id=cfg.tenant_id,
        holding_cost_weight=cfg.holding_cost_weight,
        backlog_cost_weight=cfg.backlog_cost_weight,
        customer_weight=cfg.customer_weight,
        operational_weight=cfg.operational_weight,
        strategic_weight=cfg.strategic_weight,
        autonomy_threshold=cfg.autonomy_threshold,
        notes=cfg.notes,
        updated_at=cfg.updated_at,
        updated_by_name=updated_by_name,
    )

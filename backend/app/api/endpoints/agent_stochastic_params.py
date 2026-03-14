"""
Agent Stochastic Parameters API

CRUD endpoints for per-agent stochastic variable values.
Each TRM agent type has its own set of distribution parameters that
can be industry defaults, SAP-imported, or manually edited.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field

from ...db.session import get_db
from ...api.deps import get_current_user
from ...models.user import User
from ...models.agent_stochastic_param import (
    AgentStochasticParam,
    TRM_PARAM_MAP,
    PARAM_LABELS,
    TRM_LABELS,
)

router = APIRouter(
    prefix="/agent-stochastic-params",
    tags=["Agent Stochastic Parameters"],
)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class StochasticParamResponse(BaseModel):
    id: int
    config_id: int
    tenant_id: int
    site_id: Optional[int] = None
    trm_type: str
    trm_label: str
    param_name: str
    param_label: str
    distribution: dict
    is_default: bool
    source: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class StochasticParamUpdate(BaseModel):
    distribution: dict = Field(..., description="Distribution JSON, e.g. {'type': 'lognormal', 'mean_log': 1.5, ...}")


class StochasticParamBulkUpdate(BaseModel):
    params: List[dict] = Field(
        ...,
        description="List of {id: int, distribution: dict} entries",
    )


class TRMParamMapResponse(BaseModel):
    trm_type: str
    trm_label: str
    params: List[dict]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/metadata", response_model=List[TRMParamMapResponse])
def get_trm_param_metadata(
    current_user: User = Depends(get_current_user),
):
    """Return the TRM type → parameter mapping with labels."""
    result = []
    for trm_type, param_names in TRM_PARAM_MAP.items():
        result.append({
            "trm_type": trm_type,
            "trm_label": TRM_LABELS.get(trm_type, trm_type),
            "params": [
                {"name": p, "label": PARAM_LABELS.get(p, p)}
                for p in param_names
            ],
        })
    return result


@router.get("/", response_model=List[StochasticParamResponse])
def list_stochastic_params(
    config_id: int = Query(..., description="Supply chain config ID"),
    trm_type: Optional[str] = Query(None, description="Filter by TRM type"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all stochastic parameters for a config, optionally filtered."""
    q = db.query(AgentStochasticParam).filter(
        AgentStochasticParam.config_id == config_id,
    )
    if trm_type:
        q = q.filter(AgentStochasticParam.trm_type == trm_type)
    if site_id is not None:
        q = q.filter(AgentStochasticParam.site_id == site_id)
    else:
        # By default, return config-wide params (site_id IS NULL)
        q = q.filter(AgentStochasticParam.site_id.is_(None))

    rows = q.order_by(
        AgentStochasticParam.trm_type,
        AgentStochasticParam.param_name,
    ).all()

    return [
        StochasticParamResponse(
            id=r.id,
            config_id=r.config_id,
            tenant_id=r.tenant_id,
            site_id=r.site_id,
            trm_type=r.trm_type,
            trm_label=TRM_LABELS.get(r.trm_type, r.trm_type),
            param_name=r.param_name,
            param_label=PARAM_LABELS.get(r.param_name, r.param_name),
            distribution=r.distribution,
            is_default=r.is_default,
            source=r.source,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.put("/{param_id}", response_model=StochasticParamResponse)
def update_stochastic_param(
    param_id: int,
    update: StochasticParamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a single stochastic parameter distribution.

    Marks the parameter as manually edited (is_default=False, source='manual_edit').
    Future industry changes will NOT overwrite this value.
    """
    param = db.query(AgentStochasticParam).filter(
        AgentStochasticParam.id == param_id,
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="Stochastic parameter not found")

    param.distribution = update.distribution
    param.is_default = False
    param.source = "manual_edit"
    db.commit()
    db.refresh(param)

    return StochasticParamResponse(
        id=param.id,
        config_id=param.config_id,
        tenant_id=param.tenant_id,
        site_id=param.site_id,
        trm_type=param.trm_type,
        trm_label=TRM_LABELS.get(param.trm_type, param.trm_type),
        param_name=param.param_name,
        param_label=PARAM_LABELS.get(param.param_name, param.param_name),
        distribution=param.distribution,
        is_default=param.is_default,
        source=param.source,
        created_at=param.created_at.isoformat() if param.created_at else None,
        updated_at=param.updated_at.isoformat() if param.updated_at else None,
    )


@router.put("/bulk", response_model=dict)
def bulk_update_stochastic_params(
    payload: StochasticParamBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk update multiple stochastic parameters at once.

    Each entry in `params` must have `id` and `distribution`.
    All updated params are marked as manually edited.
    """
    updated = 0
    for entry in payload.params:
        param_id = entry.get("id")
        dist = entry.get("distribution")
        if not param_id or not dist:
            continue
        param = db.query(AgentStochasticParam).filter(
            AgentStochasticParam.id == param_id,
        ).first()
        if param:
            param.distribution = dist
            param.is_default = False
            param.source = "manual_edit"
            updated += 1

    db.commit()
    return {"updated": updated}


@router.post("/{param_id}/reset", response_model=StochasticParamResponse)
def reset_to_default(
    param_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a single parameter back to its industry default.

    Looks up the tenant's industry and regenerates the default distribution.
    """
    from ...models.tenant import Tenant
    from ...models.supply_chain_config import SupplyChainConfig
    from ...services.industry_defaults_service import get_agent_distributions

    param = db.query(AgentStochasticParam).filter(
        AgentStochasticParam.id == param_id,
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="Stochastic parameter not found")

    # Look up tenant industry
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == param.config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    tenant = db.query(Tenant).filter(Tenant.id == config.tenant_id).first()
    if not tenant or not tenant.industry:
        raise HTTPException(
            status_code=400,
            detail="Tenant has no industry set — cannot determine defaults",
        )

    agent_dists = get_agent_distributions(tenant.industry.value)
    default_dist = agent_dists.get(param.param_name)
    if not default_dist:
        raise HTTPException(
            status_code=400,
            detail=f"No default distribution for param '{param.param_name}'",
        )

    param.distribution = default_dist
    param.is_default = True
    param.source = "industry_default"
    db.commit()
    db.refresh(param)

    return StochasticParamResponse(
        id=param.id,
        config_id=param.config_id,
        tenant_id=param.tenant_id,
        site_id=param.site_id,
        trm_type=param.trm_type,
        trm_label=TRM_LABELS.get(param.trm_type, param.trm_type),
        param_name=param.param_name,
        param_label=PARAM_LABELS.get(param.param_name, param.param_name),
        distribution=param.distribution,
        is_default=param.is_default,
        source=param.source,
        created_at=param.created_at.isoformat() if param.created_at else None,
        updated_at=param.updated_at.isoformat() if param.updated_at else None,
    )

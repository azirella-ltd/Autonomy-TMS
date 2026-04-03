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
    STOCHASTIC_CONFIG_DEFAULTS,
    STOCHASTIC_CONFIG_LABELS,
    get_stochastic_config,
)
from ...models.supply_chain_config import SupplyChainConfig

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


class StochasticConfigResponse(BaseModel):
    config_id: int
    settings: dict
    labels: dict
    defaults: dict


class StochasticConfigUpdate(BaseModel):
    settings: dict = Field(..., description="Partial or full stochastic config overrides")


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
async def list_stochastic_params(
    config_id: int = Query(..., description="Supply chain config ID"),
    trm_type: Optional[str] = Query(None, description="Filter by TRM type"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all stochastic parameters for a config, optionally filtered."""
    from sqlalchemy import select, and_

    filters = [AgentStochasticParam.config_id == config_id]
    if trm_type:
        filters.append(AgentStochasticParam.trm_type == trm_type)
    if site_id is not None:
        filters.append(AgentStochasticParam.site_id == site_id)
    else:
        filters.append(AgentStochasticParam.site_id.is_(None))

    result = await db.execute(
        select(AgentStochasticParam)
        .where(and_(*filters))
        .order_by(AgentStochasticParam.trm_type, AgentStochasticParam.param_name)
    )
    branch_rows = result.scalars().all()

    # Scenario branch delta-merge: read parent params, overlay branch overrides.
    # Branch only stores deltas (params the user explicitly changed).
    # At read time: parent params + branch overrides (branch wins on key match).
    from app.models.supply_chain_config import SupplyChainConfig
    cfg_result = await db.execute(
        select(SupplyChainConfig.parent_config_id).where(SupplyChainConfig.id == config_id)
    )
    parent_id = cfg_result.scalar_one_or_none()

    if parent_id:
        # Fetch parent params
        parent_filters = [AgentStochasticParam.config_id == parent_id]
        if trm_type:
            parent_filters.append(AgentStochasticParam.trm_type == trm_type)
        if site_id is not None:
            parent_filters.append(AgentStochasticParam.site_id == site_id)
        else:
            parent_filters.append(AgentStochasticParam.site_id.is_(None))
        parent_result = await db.execute(
            select(AgentStochasticParam)
            .where(and_(*parent_filters))
            .order_by(AgentStochasticParam.trm_type, AgentStochasticParam.param_name)
        )
        parent_rows = parent_result.scalars().all()

        # Merge: branch overrides win on (trm_type, param_name, site_id) key
        branch_keys = {
            (r.trm_type, r.param_name, r.site_id): r for r in branch_rows
        }
        merged = {}
        for r in parent_rows:
            key = (r.trm_type, r.param_name, r.site_id)
            merged[key] = branch_keys.pop(key, r)  # branch wins if present
        # Add any branch-only params (new params not in parent)
        merged.update(branch_keys)
        rows = sorted(merged.values(), key=lambda r: (r.trm_type, r.param_name))
    else:
        rows = branch_rows

    def _is_override(r):
        """True if this row is a branch override (config_id matches the branch, not the parent)."""
        return parent_id is not None and r.config_id == config_id

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
            is_default=r.is_default if not _is_override(r) else False,
            source="scenario_override" if _is_override(r) else r.source,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.put("/{param_id}", response_model=StochasticParamResponse)
def update_stochastic_param(
    param_id: int,
    update: StochasticParamUpdate,
    branch_config_id: Optional[int] = Query(None, description="Branch config ID for copy-on-write"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a single stochastic parameter distribution.

    Copy-on-write for scenario branches: if the param belongs to a parent config
    and branch_config_id is provided, creates a new override record on the branch
    instead of modifying the parent. This keeps the parent pristine and the branch
    stores only deltas (Kinaxis-style scenario isolation).
    """
    param = db.query(AgentStochasticParam).filter(
        AgentStochasticParam.id == param_id,
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="Stochastic parameter not found")

    # Copy-on-write: if this param belongs to a parent and we're editing on a branch,
    # create a new record on the branch instead of modifying the parent
    if branch_config_id and param.config_id != branch_config_id:
        from app.models.supply_chain_config import SupplyChainConfig
        branch = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == branch_config_id).first()
        if branch and branch.parent_config_id == param.config_id:
            # Check if branch override already exists
            existing = db.query(AgentStochasticParam).filter(
                AgentStochasticParam.config_id == branch_config_id,
                AgentStochasticParam.trm_type == param.trm_type,
                AgentStochasticParam.param_name == param.param_name,
                AgentStochasticParam.site_id == param.site_id,
            ).first()
            if existing:
                # Update existing branch override
                param = existing
            else:
                # Create new branch override (copy-on-write)
                new_param = AgentStochasticParam(
                    config_id=branch_config_id,
                    tenant_id=param.tenant_id,
                    site_id=param.site_id,
                    trm_type=param.trm_type,
                    param_name=param.param_name,
                    distribution=update.distribution,
                    is_default=False,
                    source="scenario_override",
                )
                db.add(new_param)
                db.commit()
                db.refresh(new_param)
                param = new_param
                return StochasticParamResponse(
                    id=param.id, config_id=param.config_id, tenant_id=param.tenant_id,
                    site_id=param.site_id, trm_type=param.trm_type,
                    trm_label=TRM_LABELS.get(param.trm_type, param.trm_type),
                    param_name=param.param_name,
                    param_label=PARAM_LABELS.get(param.param_name, param.param_name),
                    distribution=param.distribution, is_default=False,
                    source="scenario_override",
                    created_at=param.created_at.isoformat() if param.created_at else None,
                    updated_at=param.updated_at.isoformat() if param.updated_at else None,
                )

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


# ============================================================================
# Pipeline Configuration Endpoints
# ============================================================================

@router.get("/pipeline-config/{config_id}", response_model=StochasticConfigResponse)
def get_pipeline_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the stochastic pipeline configuration for a supply chain config.

    Returns merged defaults + per-config overrides, along with labels and
    system defaults for UI rendering.
    """
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Supply chain config not found")

    merged = get_stochastic_config(config.stochastic_config)

    return StochasticConfigResponse(
        config_id=config_id,
        settings=merged,
        labels=STOCHASTIC_CONFIG_LABELS,
        defaults=STOCHASTIC_CONFIG_DEFAULTS,
    )


@router.put("/pipeline-config/{config_id}", response_model=StochasticConfigResponse)
def update_pipeline_config(
    config_id: int,
    payload: StochasticConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the stochastic pipeline configuration for a supply chain config.

    Only valid keys (those present in STOCHASTIC_CONFIG_DEFAULTS) are accepted.
    Pass partial updates -- only provided keys are overwritten.
    """
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Supply chain config not found")

    # Validate keys
    invalid_keys = [k for k in payload.settings if k not in STOCHASTIC_CONFIG_DEFAULTS]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid config keys: {', '.join(invalid_keys)}. "
                   f"Valid keys: {', '.join(STOCHASTIC_CONFIG_DEFAULTS.keys())}",
        )

    # Merge with existing overrides
    existing = config.stochastic_config or {}
    existing.update(payload.settings)
    config.stochastic_config = existing
    db.commit()
    db.refresh(config)

    merged = get_stochastic_config(config.stochastic_config)

    return StochasticConfigResponse(
        config_id=config_id,
        settings=merged,
        labels=STOCHASTIC_CONFIG_LABELS,
        defaults=STOCHASTIC_CONFIG_DEFAULTS,
    )

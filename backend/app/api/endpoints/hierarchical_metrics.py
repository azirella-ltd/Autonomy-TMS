"""
Hierarchical Metrics API Endpoints

Gartner-aligned supply chain metrics with hierarchy drill-down
across Geography (Company>Region>Country>Site), Product
(Category>Family>Group>Product), and Time (Year>Quarter>Month>Week).

Endpoints:
- GET /dashboard: Full 4-tier Gartner metrics with hierarchy context
- GET /config: Get metric display configuration for tenant's config
- PUT /config: Update metric display configuration
- GET /catalogue: List all available metrics with metadata
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.metrics_hierarchy import (
    GARTNER_METRICS, DEFAULT_DASHBOARD_METRICS, get_metric_config,
)
from app.services.hierarchical_metrics_service import HierarchicalMetricsService
from app.services.user_scope_service import resolve_user_scope_sync


router = APIRouter()


@router.get("/dashboard")
async def get_hierarchical_dashboard(
    site_level: str = Query("company", description="Site hierarchy level: company|region|site"),
    site_key: Optional[str] = Query(None, description="Specific node key at the site level"),
    product_level: str = Query("category", description="Product hierarchy level: category|family|product"),
    product_key: Optional[str] = Query(None, description="Specific node key at the product level"),
    time_bucket: str = Query("quarter", description="Time granularity: year|quarter|month"),
    time_key: Optional[str] = Query(None, description="Specific time key (e.g., '2026-Q1', '2026-01')"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get Gartner-aligned hierarchical metrics dashboard.

    Returns metrics organized into 4 tiers (ASSESS, DIAGNOSE, CORRECT,
    AI-as-Labor) with breadcrumb navigation and drill-down children
    for each hierarchy dimension.

    Hierarchy dimensions:
    - Site: Company > Region > Site
    - Product: Category > Product
    - Time: Year > Quarter > Month
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    # Resolve user scope to restrict site/product drill-down
    allowed_sites, allowed_products = resolve_user_scope_sync(current_user)

    service = HierarchicalMetricsService(db=db)

    data = service.get_dashboard_metrics(
        tenant_id=tenant_id,
        site_level=site_level,
        site_key=site_key,
        product_level=product_level,
        product_key=product_key,
        time_bucket=time_bucket,
        time_key=time_key,
    )

    # Filter children lists to only include sites/products within user's scope
    if data.get("children") and (allowed_sites is not None or allowed_products is not None):
        children = data["children"]
        if allowed_sites is not None and "site" in children:
            children["site"] = [
                c for c in children["site"]
                if c.get("key") in allowed_sites or c.get("key") == "ALL"
            ]
        if allowed_products is not None and "product" in children:
            children["product"] = [
                c for c in children["product"]
                if c.get("id") in allowed_products or c.get("key") == "ALL"
            ]

    return {
        "success": True,
        "data": data,
    }


@router.get("/catalogue")
async def get_metric_catalogue(
    current_user: User = Depends(get_current_user),
):
    """List all available metrics with metadata, grouped by tier."""
    tiers = {
        "tier1_assess": {},
        "tier2_diagnose": {},
        "tier3_correct": {},
    }
    for tier_key, metric_defaults in DEFAULT_DASHBOARD_METRICS.items():
        for metric_key, cfg in metric_defaults.items():
            tiers[tier_key][metric_key] = {
                "key": metric_key,
                "default_enabled": cfg.enabled,
                "default_target": cfg.target,
            }
    # Enrich with GARTNER_METRICS metadata where scor_code matches
    from app.services.hierarchical_metrics_service import _METRIC_KEY_TO_GARTNER
    for tier_key, metrics in tiers.items():
        for metric_key, info in metrics.items():
            gartner_code = _METRIC_KEY_TO_GARTNER.get(metric_key)
            if gartner_code and gartner_code in GARTNER_METRICS:
                defn = GARTNER_METRICS[gartner_code]
                info["label"] = defn.name
                info["description"] = defn.description
                info["unit"] = defn.unit
                info["higher_is_better"] = defn.higher_is_better
                info["scor_code"] = gartner_code
                info["scor_process"] = defn.scor_process
            else:
                # Provide human-readable label from key
                info["label"] = metric_key.replace("_", " ").title()
                info["description"] = ""
                info["unit"] = ""
                info["higher_is_better"] = True
                info["scor_code"] = None
                info["scor_process"] = ""
    return {"success": True, "data": tiers}


@router.get("/config")
async def get_metrics_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current metric display configuration for the tenant's config."""
    from app.models.supply_chain_config import SupplyChainConfig

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    config = (
        db.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="No supply chain config found for tenant")

    mc = get_metric_config(config.metric_config)

    # Build response: merge defaults with overrides
    result = {}
    for tier_key, metric_defaults in DEFAULT_DASHBOARD_METRICS.items():
        result[tier_key] = {}
        for metric_key, default_cfg in metric_defaults.items():
            dc = mc.get_dashboard_config(tier_key, metric_key)
            result[tier_key][metric_key] = {
                "enabled": dc.enabled,
                "target": dc.target,
            }

    return {
        "success": True,
        "data": {
            "config_id": config.id,
            "config_name": config.name,
            "dashboard": result,
        },
    }


class MetricConfigUpdate(BaseModel):
    dashboard: Dict[str, Dict[str, Dict[str, Any]]]


@router.put("/config")
async def update_metrics_config(
    payload: MetricConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update metric display configuration for the tenant's config.

    Payload format:
    {
      "dashboard": {
        "tier1_assess": {
          "perfect_order_fulfillment": {"enabled": true, "target": 92.0},
          ...
        },
        ...
      }
    }
    """
    from app.models.supply_chain_config import SupplyChainConfig

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    # Check permission — tenant admin or system admin
    user_roles = [r.name for r in current_user.roles] if current_user.roles else []
    if "SYSTEM_ADMIN" not in user_roles and "GROUP_ADMIN" not in user_roles:
        raise HTTPException(status_code=403, detail="Tenant admin or system admin required")

    config = (
        db.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="No supply chain config found for tenant")

    # Validate metric keys against known defaults
    for tier_key, metrics in payload.dashboard.items():
        if tier_key not in DEFAULT_DASHBOARD_METRICS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tier: {tier_key}. Valid: {list(DEFAULT_DASHBOARD_METRICS.keys())}",
            )
        for metric_key in metrics:
            if metric_key not in DEFAULT_DASHBOARD_METRICS[tier_key]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown metric '{metric_key}' in {tier_key}",
                )

    # Merge into existing metric_config
    existing = config.metric_config or {}
    existing["dashboard"] = payload.dashboard
    config.metric_config = existing

    # Force SQLAlchemy to detect the JSON change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(config, "metric_config")

    db.commit()

    return {
        "success": True,
        "message": "Metric configuration updated",
    }

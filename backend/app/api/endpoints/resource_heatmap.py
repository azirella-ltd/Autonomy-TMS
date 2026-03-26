"""
Resource Heatmap API Endpoints

Sites x weeks capacity utilization grid for visual heatmap rendering.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.resource_heatmap_service import ResourceHeatmapService

router = APIRouter()


@router.get("/{config_id}")
async def get_resource_heatmap(
    config_id: int,
    horizon_weeks: int = Query(12, ge=1, le=52, description="Number of weeks to project"),
    site_type: Optional[str] = Query(None, description="Filter by master_type (MANUFACTURER, INVENTORY)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Build a sites x weeks capacity utilization heatmap grid.

    Returns utilization percentages per site per week, sourced from
    resource_capacity, supply_plan (mo_request), production_orders,
    and powell_mo_decisions.
    """
    svc = ResourceHeatmapService(db)
    return svc.build_heatmap_data(config_id, horizon_weeks, site_type)


@router.get("/{config_id}/cell-detail")
async def get_heatmap_cell_detail(
    config_id: int,
    site_id: int = Query(..., description="Site ID"),
    week_start: date = Query(..., description="Week start date (ISO format YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detail for a single heatmap cell: products and orders consuming capacity.
    """
    svc = ResourceHeatmapService(db)
    return svc.get_cell_detail(config_id, site_id, week_start)

"""
Hierarchical Metrics API Endpoints

Gartner-aligned supply chain metrics with hierarchy drill-down
across Geography (Company>Region>Country>Site), Product
(Category>Family>Group>Product), and Time (Year>Quarter>Month>Week).

Endpoints:
- GET /dashboard: Full 4-tier Gartner metrics with hierarchy context
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.hierarchical_metrics_service import HierarchicalMetricsService


router = APIRouter()


@router.get("/dashboard")
async def get_hierarchical_dashboard(
    site_level: str = Query("company", description="Site hierarchy level: company|region|country|site"),
    site_key: Optional[str] = Query(None, description="Specific node key at the site level"),
    product_level: str = Query("category", description="Product hierarchy level: category|family|group|product"),
    product_key: Optional[str] = Query(None, description="Specific node key at the product level"),
    time_bucket: str = Query("quarter", description="Time granularity: year|quarter|month|week"),
    time_key: Optional[str] = Query(None, description="Specific time key (e.g., '2025-Q3', '2025-07')"),
    current_user: User = Depends(get_current_user),
):
    """
    Get Gartner-aligned hierarchical metrics dashboard.

    Returns metrics organized into 4 tiers (ASSESS, DIAGNOSE, CORRECT,
    AI-as-Labor) with breadcrumb navigation and drill-down children
    for each hierarchy dimension.

    Hierarchy dimensions:
    - Site: Company > Region > Country > Site
    - Product: Category > Family > Group > Product
    - Time: Year > Quarter > Month > Week
    """
    group_id = current_user.group_id or 1
    service = HierarchicalMetricsService()

    data = service.get_dashboard_metrics(
        group_id=group_id,
        site_level=site_level,
        site_key=site_key,
        product_level=product_level,
        product_key=product_key,
        time_bucket=time_bucket,
        time_key=time_key,
    )

    return {
        "success": True,
        "data": data,
    }

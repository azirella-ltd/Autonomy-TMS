"""
Insights & Actions API Endpoints - AIIO Framework

REST API for the insights-driven landing page with hierarchy drill-down.
Implements the Automate, Inform, Inspect, Override (AIIO) workflow.

Endpoints:
- GET  /dashboard          - Get dashboard summary at hierarchy level
- GET  /actions            - List actions with filtering
- GET  /actions/{id}       - Get action detail (INSPECT)
- POST /actions/{id}/acknowledge - Acknowledge INFORM action
- POST /actions/{id}/override    - Override action with reason
- GET  /drill-down         - Get children for drill-down navigation
- POST /record             - Record an action (internal, for agents)
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.planning_hierarchy import (
    SiteHierarchyLevel, ProductHierarchyLevel, TimeBucketType
)
from app.models.agent_action import ActionMode, ActionCategory, ExecutionResult
from app.services.insights_actions_service import (
    InsightsActionsService, create_insights_service
)
from app.schemas.insights import (
    HierarchyContext, ActionFilters, ActionCreate, ActionOverride,
    DashboardResponse, DashboardSummary,
    ActionsListResponse, ActionDetailResponse, ActionResponse,
    DrillDownResponse, ActionSummary
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["insights"])


# ============================================================================
# Dependencies
# ============================================================================

async def get_insights_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> InsightsActionsService:
    """Get insights service with user context."""
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a group"
        )
    return create_insights_service(db, current_user.customer_id, current_user)


# ============================================================================
# Dashboard
# ============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    site_level: SiteHierarchyLevel = Query(
        default=SiteHierarchyLevel.COMPANY,
        description="Site hierarchy level"
    ),
    site_key: Optional[str] = Query(
        default=None,
        description="Specific site key at the level"
    ),
    product_level: ProductHierarchyLevel = Query(
        default=ProductHierarchyLevel.CATEGORY,
        description="Product hierarchy level"
    ),
    product_key: Optional[str] = Query(
        default=None,
        description="Specific product key at the level"
    ),
    time_bucket: TimeBucketType = Query(
        default=TimeBucketType.MONTH,
        description="Time bucket granularity"
    ),
    time_key: Optional[str] = Query(
        default=None,
        description="Specific time period"
    ),
    recent_limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Number of recent actions to include"
    ),
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    Get dashboard summary at the specified hierarchy level.

    The dashboard shows:
    - Action counts by mode (Automate/Inform)
    - Action counts by category (Inventory, Procurement, etc.)
    - Action counts by status (Pending/Acknowledged/Overridden)
    - Recent actions list

    Results are filtered by the user's scope (site_scope, product_scope).
    GROUP_ADMIN users see all data.
    """
    context = HierarchyContext(
        site_level=site_level,
        site_key=site_key,
        product_level=product_level,
        product_key=product_key,
        time_bucket=time_bucket,
        time_key=time_key
    )

    summary = await service.get_dashboard_summary(context, recent_limit)
    return DashboardResponse(success=True, data=summary)


# ============================================================================
# Actions List
# ============================================================================

@router.get("/actions", response_model=ActionsListResponse)
async def get_actions(
    # Filters
    mode: Optional[ActionMode] = Query(default=None, description="Filter by action mode"),
    category: Optional[ActionCategory] = Query(default=None, description="Filter by category"),
    action_type: Optional[str] = Query(default=None, description="Filter by action type"),
    acknowledged: Optional[bool] = Query(default=None, description="Filter by acknowledged status"),
    overridden: Optional[bool] = Query(default=None, description="Filter by overridden status"),
    agent_id: Optional[str] = Query(default=None, description="Filter by agent"),
    execution_result: Optional[ExecutionResult] = Query(default=None, description="Filter by result"),
    # Hierarchy context
    site_level: SiteHierarchyLevel = Query(default=SiteHierarchyLevel.COMPANY),
    site_key: Optional[str] = Query(default=None),
    product_level: ProductHierarchyLevel = Query(default=ProductHierarchyLevel.CATEGORY),
    product_key: Optional[str] = Query(default=None),
    time_bucket: TimeBucketType = Query(default=TimeBucketType.MONTH),
    time_key: Optional[str] = Query(default=None),
    # Pagination
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    List actions with filtering and pagination.

    Supports filtering by:
    - Mode (automate/inform)
    - Category (inventory, procurement, demand, etc.)
    - Action type (rebalance, po_create, etc.)
    - Acknowledgment/override status
    - Agent ID
    - Execution result

    Results are filtered by the user's scope.
    """
    filters = ActionFilters(
        mode=mode,
        category=category,
        action_type=action_type,
        acknowledged=acknowledged,
        overridden=overridden,
        agent_id=agent_id,
        execution_result=execution_result,
        offset=offset,
        limit=limit
    )

    context = HierarchyContext(
        site_level=site_level,
        site_key=site_key,
        product_level=product_level,
        product_key=product_key,
        time_bucket=time_bucket,
        time_key=time_key
    )

    actions, total = await service.get_actions(filters, context)

    return ActionsListResponse(
        success=True,
        total=total,
        offset=offset,
        limit=limit,
        data=actions
    )


# ============================================================================
# Action Detail (INSPECT)
# ============================================================================

@router.get("/actions/{action_id}", response_model=ActionDetailResponse)
async def get_action_detail(
    action_id: int,
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    Get full action detail for INSPECT workflow.

    Returns:
    - Full explanation of why the action was taken
    - Reasoning chain (structured steps)
    - Alternatives considered and why they were not chosen
    - Before/after metrics
    - Override history if applicable

    This endpoint supports the INSPECT capability in the AIIO framework,
    allowing users to understand agent decisions.
    """
    detail = await service.get_action_detail(action_id)

    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found or not accessible"
        )

    return ActionDetailResponse(success=True, data=detail)


# ============================================================================
# Acknowledge (for INFORM actions)
# ============================================================================

@router.post("/actions/{action_id}/acknowledge", response_model=ActionResponse)
async def acknowledge_action(
    action_id: int,
    current_user: User = Depends(get_current_user),
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    Acknowledge an INFORM action.

    INFORM actions notify users about agent decisions.
    Acknowledging indicates the user has seen the action.

    No reason is required for acknowledgment.
    """
    action = await service.acknowledge_action(action_id, current_user.id)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found or not accessible"
        )

    return ActionResponse(
        success=True,
        message="Action acknowledged",
        data=ActionSummary(**action.to_summary_dict())
    )


# ============================================================================
# Override (with required reason)
# ============================================================================

@router.post("/actions/{action_id}/override", response_model=ActionResponse)
async def override_action(
    action_id: int,
    body: ActionOverride,
    current_user: User = Depends(get_current_user),
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    Override an agent action with a REQUIRED reason.

    The reason is mandatory for:
    1. Audit trail - compliance and accountability
    2. Learning - improve agent decisions over time

    Optionally, you can provide structured data about what
    the user did instead (override_action field).

    This endpoint supports the OVERRIDE capability in the AIIO framework.
    """
    try:
        action = await service.override_action(
            action_id,
            current_user.id,
            body.reason,
            body.override_action
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found or not accessible"
        )

    return ActionResponse(
        success=True,
        message="Action overridden",
        data=ActionSummary(**action.to_summary_dict())
    )


# ============================================================================
# Drill-Down Navigation
# ============================================================================

@router.get("/drill-down", response_model=DrillDownResponse)
async def get_drill_down(
    dimension: str = Query(
        ...,
        description="Dimension to drill down: site, product, or time"
    ),
    # Current context
    site_level: SiteHierarchyLevel = Query(default=SiteHierarchyLevel.COMPANY),
    site_key: Optional[str] = Query(default=None),
    product_level: ProductHierarchyLevel = Query(default=ProductHierarchyLevel.CATEGORY),
    product_key: Optional[str] = Query(default=None),
    time_bucket: TimeBucketType = Query(default=TimeBucketType.MONTH),
    time_key: Optional[str] = Query(default=None),
    service: InsightsActionsService = Depends(get_insights_service)
):
    """
    Get children for drill-down navigation.

    Pass the current hierarchy context and the dimension to drill down.
    Returns a list of children with action counts.

    Example:
    - At Company level, drill down site → returns list of Regions
    - At Region level, drill down site → returns list of Countries
    """
    if dimension not in ("site", "product", "time"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dimension must be 'site', 'product', or 'time'"
        )

    context = HierarchyContext(
        site_level=site_level,
        site_key=site_key,
        product_level=product_level,
        product_key=product_key,
        time_bucket=time_bucket,
        time_key=time_key
    )

    children = await service.get_drill_down_children(context, dimension)
    breadcrumbs = service._build_breadcrumbs(context)

    return DrillDownResponse(
        success=True,
        current_context=context,
        children=children,
        breadcrumbs=breadcrumbs
    )


# ============================================================================
# Record Action (Internal - for agents)
# ============================================================================

@router.post("/record", response_model=ActionResponse, include_in_schema=False)
async def record_action(
    body: ActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record an action taken by an agent.

    This endpoint is called by TRM, GNN, LLM agents when they make decisions.
    It requires authentication but is not typically called by end users.

    Note: This endpoint is hidden from the OpenAPI schema.
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a group"
        )

    service = create_insights_service(db, current_user.customer_id, current_user)
    action = await service.record_action(body)

    return ActionResponse(
        success=True,
        message="Action recorded",
        data=ActionSummary(**action.to_summary_dict())
    )

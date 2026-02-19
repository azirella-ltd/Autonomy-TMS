"""
Pydantic Schemas for Insights & Actions API (AIIO Framework)

These schemas support the Automate, Inform, Inspect, Override workflow
for the insights landing page with hierarchy drill-down.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator

from app.models.planning_hierarchy import (
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType
)
from app.models.agent_action import ActionMode, ActionCategory, ExecutionResult


# ============================================================================
# Hierarchy Context
# ============================================================================

class HierarchyContext(BaseModel):
    """Current hierarchy context for filtering and drill-down."""
    site_level: SiteHierarchyLevel = Field(
        default=SiteHierarchyLevel.COMPANY,
        description="Current site hierarchy level"
    )
    site_key: Optional[str] = Field(
        default=None,
        description="Specific site key at the current level"
    )
    product_level: ProductHierarchyLevel = Field(
        default=ProductHierarchyLevel.CATEGORY,
        description="Current product hierarchy level"
    )
    product_key: Optional[str] = Field(
        default=None,
        description="Specific product key at the current level"
    )
    time_bucket: TimeBucketType = Field(
        default=TimeBucketType.MONTH,
        description="Current time bucket granularity"
    )
    time_key: Optional[str] = Field(
        default=None,
        description="Specific time period at the current bucket level"
    )

    class Config:
        use_enum_values = True


class HierarchyBreadcrumb(BaseModel):
    """Single item in the hierarchy breadcrumb trail."""
    level: str
    key: str
    label: str
    is_current: bool = False


class HierarchyBreadcrumbs(BaseModel):
    """Full breadcrumb trails for all three dimensions."""
    site: List[HierarchyBreadcrumb] = Field(default_factory=list)
    product: List[HierarchyBreadcrumb] = Field(default_factory=list)
    time: List[HierarchyBreadcrumb] = Field(default_factory=list)


# ============================================================================
# Action Schemas
# ============================================================================

class ReasoningStep(BaseModel):
    """Single step in the agent's reasoning chain."""
    step: int
    description: str
    input_data: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    confidence: Optional[float] = None


class AlternativeConsidered(BaseModel):
    """An alternative option the agent evaluated."""
    description: str
    score: Optional[float] = None
    why_not_chosen: str


class EstimatedImpact(BaseModel):
    """Estimated impact metrics from an action."""
    cost_saved: Optional[float] = None
    cost_incurred: Optional[float] = None
    risk_reduced: Optional[float] = None
    service_level_improvement: Optional[float] = None
    inventory_reduction: Optional[float] = None
    lead_time_reduction: Optional[float] = None
    custom_metrics: Optional[Dict[str, float]] = None


class ActionCreate(BaseModel):
    """Schema for creating a new agent action (called by agents)."""
    action_mode: ActionMode
    action_type: str
    category: ActionCategory = ActionCategory.OTHER

    title: str
    description: Optional[str] = None
    explanation: str = Field(..., min_length=10)

    reasoning_chain: Optional[List[ReasoningStep]] = None
    alternatives_considered: Optional[List[AlternativeConsidered]] = None

    site_hierarchy_level: SiteHierarchyLevel = SiteHierarchyLevel.SITE
    site_key: str
    product_hierarchy_level: ProductHierarchyLevel = ProductHierarchyLevel.PRODUCT
    product_key: str
    time_bucket: TimeBucketType = TimeBucketType.DAY
    time_key: str

    metric_name: Optional[str] = None
    metric_before: Optional[float] = None
    metric_after: Optional[float] = None
    estimated_impact: Optional[EstimatedImpact] = None

    execution_result: ExecutionResult = ExecutionResult.SUCCESS
    execution_details: Optional[Dict[str, Any]] = None

    agent_id: str
    agent_version: Optional[str] = None

    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None

    class Config:
        use_enum_values = True


class ActionSummary(BaseModel):
    """Summary view of an action for list displays."""
    id: int
    action_mode: str
    action_type: str
    category: str
    title: str
    explanation: str  # Truncated for list view
    site_key: str
    product_key: str
    time_key: str
    metric_name: Optional[str] = None
    metric_before: Optional[float] = None
    metric_after: Optional[float] = None
    executed_at: datetime
    execution_result: str
    is_acknowledged: bool
    is_overridden: bool
    agent_id: str

    class Config:
        from_attributes = True


class ActionDetail(BaseModel):
    """Full detail view of an action (for INSPECT)."""
    id: int
    group_id: int
    action_mode: str
    action_type: str
    category: str

    title: str
    description: Optional[str] = None
    explanation: str
    reasoning_chain: Optional[List[Dict[str, Any]]] = None
    alternatives_considered: Optional[List[Dict[str, Any]]] = None

    site_hierarchy_level: str
    site_key: str
    product_hierarchy_level: str
    product_key: str
    time_bucket: str
    time_key: str

    metric_name: Optional[str] = None
    metric_before: Optional[float] = None
    metric_after: Optional[float] = None
    estimated_impact: Optional[Dict[str, Any]] = None

    executed_at: datetime
    execution_result: str
    execution_details: Optional[Dict[str, Any]] = None

    is_acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None

    is_overridden: bool
    overridden_by: Optional[int] = None
    overridden_at: Optional[datetime] = None
    override_reason: Optional[str] = None
    override_action: Optional[Dict[str, Any]] = None

    agent_id: str
    agent_version: Optional[str] = None

    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ActionAcknowledge(BaseModel):
    """Schema for acknowledging an INFORM action."""
    pass  # No additional data needed, user ID comes from auth


class ActionOverride(BaseModel):
    """Schema for overriding an action (REQUIRED reason)."""
    reason: str = Field(
        ...,
        min_length=10,
        description="Reason for override - REQUIRED for audit trail and learning"
    )
    override_action: Optional[Dict[str, Any]] = Field(
        default=None,
        description="What the user did instead (optional structured data)"
    )


# ============================================================================
# Dashboard Summary
# ============================================================================

class ActionCountsByMode(BaseModel):
    """Action counts grouped by mode."""
    automate: int = 0
    inform: int = 0
    total: int = 0


class ActionCountsByCategory(BaseModel):
    """Action counts grouped by category."""
    inventory: int = 0
    procurement: int = 0
    demand: int = 0
    production: int = 0
    logistics: int = 0
    pricing: int = 0
    risk: int = 0
    allocation: int = 0
    other: int = 0


class ActionCountsByStatus(BaseModel):
    """Action counts grouped by status."""
    pending_acknowledgment: int = 0
    acknowledged: int = 0
    overridden: int = 0


class DashboardSummary(BaseModel):
    """Summary data for the insights dashboard."""
    # Current hierarchy context
    hierarchy_context: HierarchyContext
    breadcrumbs: HierarchyBreadcrumbs

    # Counts
    total_actions: int = 0
    by_mode: ActionCountsByMode = Field(default_factory=ActionCountsByMode)
    by_category: ActionCountsByCategory = Field(default_factory=ActionCountsByCategory)
    by_status: ActionCountsByStatus = Field(default_factory=ActionCountsByStatus)

    # Recent actions (top N)
    recent_actions: List[ActionSummary] = Field(default_factory=list)

    # Time range
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    # User scope info
    user_has_full_scope: bool = True
    user_site_scope: Optional[List[str]] = None
    user_product_scope: Optional[List[str]] = None


# ============================================================================
# API Responses
# ============================================================================

class DashboardResponse(BaseModel):
    """Response for GET /insights/dashboard."""
    success: bool = True
    data: DashboardSummary


class ActionsListResponse(BaseModel):
    """Response for GET /insights/actions."""
    success: bool = True
    total: int
    offset: int
    limit: int
    data: List[ActionSummary]


class ActionDetailResponse(BaseModel):
    """Response for GET /insights/actions/{id}."""
    success: bool = True
    data: ActionDetail


class ActionResponse(BaseModel):
    """Response for action mutations (acknowledge, override)."""
    success: bool = True
    message: str
    data: ActionSummary


# ============================================================================
# Drill-Down
# ============================================================================

class DrillDownChild(BaseModel):
    """A child item in drill-down navigation."""
    key: str
    label: str
    action_count: int
    pending_count: int
    can_drill_down: bool = True


class DrillDownResponse(BaseModel):
    """Response for drill-down navigation."""
    success: bool = True
    current_context: HierarchyContext
    children: List[DrillDownChild]
    breadcrumbs: HierarchyBreadcrumbs


# ============================================================================
# Filters
# ============================================================================

class ActionFilters(BaseModel):
    """Filters for querying actions."""
    mode: Optional[ActionMode] = None
    category: Optional[ActionCategory] = None
    action_type: Optional[str] = None
    acknowledged: Optional[bool] = None
    overridden: Optional[bool] = None
    agent_id: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    # Pagination
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)

    class Config:
        use_enum_values = True

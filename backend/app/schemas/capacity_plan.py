"""
Capacity Plan Pydantic Schemas

Request/response schemas for Capacity Planning API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


# ============================================================================
# Capacity Plan Schemas
# ============================================================================

class CapacityPlanBase(BaseModel):
    """Base capacity plan schema with common fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    supply_chain_config_id: int = Field(..., gt=0)
    planning_horizon_weeks: int = Field(default=13, ge=1, le=104)
    bucket_size_days: int = Field(default=7, ge=1, le=30)
    start_date: datetime
    end_date: datetime
    is_scenario: bool = False
    scenario_description: Optional[str] = None
    base_plan_id: Optional[int] = None

    @validator('end_date')
    def end_after_start(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('End date must be after start date')
        return v


class CapacityPlanCreate(CapacityPlanBase):
    """Schema for creating a new capacity plan."""
    pass


class CapacityPlanUpdate(BaseModel):
    """Schema for updating an existing capacity plan."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    planning_horizon_weeks: Optional[int] = Field(None, ge=1, le=104)
    bucket_size_days: Optional[int] = Field(None, ge=1, le=30)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_scenario: Optional[bool] = None
    scenario_description: Optional[str] = None
    status: Optional[str] = None


class CapacityPlanResponse(CapacityPlanBase):
    """Schema for capacity plan API responses."""
    id: int
    status: str
    total_resources: Optional[int] = None
    overloaded_resources: Optional[int] = None
    avg_utilization_percent: Optional[float] = None
    max_utilization_percent: Optional[float] = None
    bottleneck_identified: bool
    is_feasible: bool
    has_bottlenecks: bool
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CapacityPlanListResponse(BaseModel):
    """Paginated list of capacity plans."""
    items: List[CapacityPlanResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CapacityPlanSummary(BaseModel):
    """Summary statistics for capacity plans."""
    total_plans: int
    active_plans: int
    scenario_plans: int
    avg_utilization: float
    feasible_plans: int
    infeasible_plans: int
    plans_with_bottlenecks: int


# ============================================================================
# Capacity Resource Schemas
# ============================================================================

class CapacityResourceBase(BaseModel):
    """Base capacity resource schema."""
    resource_name: str = Field(..., min_length=1, max_length=255)
    resource_code: Optional[str] = Field(None, max_length=50)
    resource_type: str = Field(default="MACHINE")
    site_id: int = Field(..., gt=0)
    available_capacity: float = Field(..., gt=0)
    capacity_unit: str = Field(default="hours", max_length=50)
    efficiency_percent: float = Field(default=100.0, ge=0, le=100)
    utilization_target_percent: float = Field(default=85.0, ge=0, le=100)
    cost_per_hour: Optional[float] = Field(None, ge=0)
    setup_time_hours: Optional[float] = Field(None, ge=0)
    shifts_per_day: Optional[int] = Field(None, ge=1, le=3)
    hours_per_shift: Optional[float] = Field(None, ge=1, le=24)
    working_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    notes: Optional[str] = None


class CapacityResourceCreate(CapacityResourceBase):
    """Schema for creating a new capacity resource."""
    plan_id: int = Field(..., gt=0)


class CapacityResourceUpdate(BaseModel):
    """Schema for updating an existing capacity resource."""
    resource_name: Optional[str] = Field(None, min_length=1, max_length=255)
    resource_code: Optional[str] = Field(None, max_length=50)
    resource_type: Optional[str] = None
    available_capacity: Optional[float] = Field(None, gt=0)
    capacity_unit: Optional[str] = Field(None, max_length=50)
    efficiency_percent: Optional[float] = Field(None, ge=0, le=100)
    utilization_target_percent: Optional[float] = Field(None, ge=0, le=100)
    cost_per_hour: Optional[float] = Field(None, ge=0)
    setup_time_hours: Optional[float] = Field(None, ge=0)
    shifts_per_day: Optional[int] = Field(None, ge=1, le=3)
    hours_per_shift: Optional[float] = Field(None, ge=1, le=24)
    working_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    notes: Optional[str] = None


class CapacityResourceResponse(CapacityResourceBase):
    """Schema for capacity resource API responses."""
    id: int
    plan_id: int
    effective_capacity: float
    target_capacity: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Capacity Requirement Schemas
# ============================================================================

class CapacityRequirementBase(BaseModel):
    """Base capacity requirement schema."""
    resource_id: int = Field(..., gt=0)
    period_start: datetime
    period_end: datetime
    period_number: int = Field(..., ge=1)
    required_capacity: float = Field(..., ge=0)
    available_capacity: float = Field(..., gt=0)
    source_type: Optional[str] = Field(None, max_length=50)
    source_id: Optional[int] = None
    requirement_breakdown: Optional[Dict[str, float]] = None


class CapacityRequirementCreate(CapacityRequirementBase):
    """Schema for creating a new capacity requirement."""
    plan_id: int = Field(..., gt=0)


class CapacityRequirementUpdate(BaseModel):
    """Schema for updating an existing capacity requirement."""
    required_capacity: Optional[float] = Field(None, ge=0)
    available_capacity: Optional[float] = Field(None, gt=0)
    source_type: Optional[str] = Field(None, max_length=50)
    source_id: Optional[int] = None
    requirement_breakdown: Optional[Dict[str, float]] = None


class CapacityRequirementResponse(CapacityRequirementBase):
    """Schema for capacity requirement API responses."""
    id: int
    plan_id: int
    utilization_percent: float
    is_overloaded: bool
    overload_amount: Optional[float] = None
    is_bottleneck: bool
    spare_capacity: float
    load_factor: float
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Calculation & Analysis Schemas
# ============================================================================

class CalculateCapacityRequest(BaseModel):
    """Request to calculate capacity requirements for a plan."""
    plan_id: int = Field(..., gt=0)
    source_type: str = Field(..., description="MPS, PRODUCTION_ORDER, or FORECAST")
    source_ids: Optional[List[int]] = Field(None, description="Specific source IDs to include")
    recalculate: bool = Field(default=False, description="Recalculate all requirements")


class CapacityAnalysisResponse(BaseModel):
    """Capacity analysis results."""
    plan_id: int
    is_feasible: bool
    total_periods: int
    overloaded_periods: int
    bottleneck_resources: List[Dict[str, Any]]
    utilization_by_resource: Dict[str, float]
    utilization_by_period: List[Dict[str, Any]]
    recommendations: List[str]


class BottleneckResource(BaseModel):
    """Bottleneck resource identification."""
    resource_id: int
    resource_name: str
    site_id: int
    site_name: str
    max_utilization_percent: float
    overloaded_periods: int
    avg_utilization_percent: float


class CapacityScenarioComparison(BaseModel):
    """Compare capacity scenarios."""
    base_plan_id: int
    scenario_plan_id: int
    utilization_difference: Dict[str, float]
    feasibility_change: str
    bottleneck_changes: List[str]
    cost_impact: Optional[float] = None


# ============================================================================
# Filter & Export Schemas
# ============================================================================

class CapacityPlanFilters(BaseModel):
    """Filters for capacity plan list queries."""
    status: Optional[str] = None
    config_id: Optional[int] = None
    is_scenario: Optional[bool] = None
    is_feasible: Optional[bool] = None
    has_bottlenecks: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CapacityResourceFilters(BaseModel):
    """Filters for capacity resource list queries."""
    plan_id: Optional[int] = None
    site_id: Optional[int] = None
    resource_type: Optional[str] = None
    overloaded_only: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class CapacityRequirementFilters(BaseModel):
    """Filters for capacity requirement list queries."""
    plan_id: Optional[int] = None
    resource_id: Optional[int] = None
    period_number: Optional[int] = None
    overloaded_only: bool = False
    bottleneck_only: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class CapacityExportRequest(BaseModel):
    """Request to export capacity plan data."""
    plan_id: int = Field(..., gt=0)
    format: str = Field(default="CSV", description="CSV, EXCEL, or JSON")
    include_requirements: bool = Field(default=True)
    include_resources: bool = Field(default=True)
    include_analysis: bool = Field(default=True)

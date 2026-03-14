"""
RCCP (Rough-Cut Capacity Planning) Pydantic Schemas

Request/response schemas for RCCP validation and Bill of Resources management.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Bill of Resources Schemas
# ============================================================================

class BillOfResourcesBase(BaseModel):
    """Base BoR schema."""
    config_id: int = Field(..., gt=0)
    product_id: int = Field(..., gt=0)
    site_id: int = Field(..., gt=0)
    resource_id: Optional[int] = Field(None, gt=0)
    overall_hours_per_unit: Optional[float] = Field(None, ge=0)
    hours_per_unit: Optional[float] = Field(None, ge=0)
    setup_hours_per_batch: float = Field(default=0.0, ge=0)
    typical_batch_size: float = Field(default=1.0, gt=0)
    phase: Optional[str] = None  # setup, run, teardown, queue, move
    lead_time_offset_days: int = Field(default=0, ge=0)
    phase_hours_per_unit: Optional[float] = Field(None, ge=0)
    is_critical: bool = False
    is_active: bool = True
    notes: Optional[str] = None
    production_process_id: Optional[int] = Field(None, gt=0)


class BillOfResourcesCreate(BillOfResourcesBase):
    """Schema for creating a BoR entry."""
    pass


class BillOfResourcesUpdate(BaseModel):
    """Schema for updating a BoR entry."""
    resource_id: Optional[int] = Field(None, gt=0)
    overall_hours_per_unit: Optional[float] = Field(None, ge=0)
    hours_per_unit: Optional[float] = Field(None, ge=0)
    setup_hours_per_batch: Optional[float] = Field(None, ge=0)
    typical_batch_size: Optional[float] = Field(None, gt=0)
    phase: Optional[str] = None
    lead_time_offset_days: Optional[int] = Field(None, ge=0)
    phase_hours_per_unit: Optional[float] = Field(None, ge=0)
    is_critical: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    production_process_id: Optional[int] = Field(None, gt=0)


class BillOfResourcesResponse(BillOfResourcesBase):
    """Schema for BoR API responses."""
    id: int
    effective_hours_per_unit: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BillOfResourcesBulkCreate(BaseModel):
    """Bulk create/update BoR entries."""
    entries: List[BillOfResourcesCreate]


# ============================================================================
# RCCP Validation Schemas
# ============================================================================

class RCCPValidateRequest(BaseModel):
    """Request to run RCCP validation against an MPS plan."""
    mps_plan_id: int = Field(..., gt=0)
    site_id: int = Field(..., gt=0)
    method: Optional[str] = Field(None, description="cpof, bill_of_capacity, or resource_profile. Auto-detects if omitted.")
    planning_horizon_weeks: int = Field(default=12, ge=1, le=52)
    changeover_adjusted: bool = Field(default=True, description="Use Glenday-adjusted capacity")


class ResourceLoadDetail(BaseModel):
    """Resource load for a single resource/week."""
    resource_id: int
    resource_name: str
    week: int
    required_hours: float
    available_hours: float
    utilization_pct: float
    status: str  # ok, warning, critical, underloaded


class MPSAdjustment(BaseModel):
    """Recommended MPS quantity adjustment."""
    product_id: int
    original_week: int
    adjusted_week: int
    quantity: float
    reason: str


class ChangeoverDetail(BaseModel):
    """Changeover loss detail for a resource/week."""
    resource_id: int
    week: int
    changeover_hours: float
    distinct_products: int
    green_runners: int
    adjusted_capacity: float
    original_capacity: float


class RCCPRunResponse(BaseModel):
    """Response from an RCCP validation run."""
    id: int
    config_id: int
    mps_plan_id: int
    site_id: int
    method: str
    status: str  # feasible, overloaded, levelling_recommended, escalate_to_sop
    is_feasible: bool
    planning_horizon_weeks: int
    start_date: datetime
    end_date: datetime
    max_utilization_pct: Optional[float] = None
    avg_utilization_pct: Optional[float] = None
    overloaded_resource_count: int = 0
    overloaded_week_count: int = 0
    chronic_overload_resources: List[int] = []
    overtime_required: bool = False
    variability_buffer_applied: bool = False
    mps_adjustments: List[Dict[str, Any]] = []
    resource_loads: List[Dict[str, Any]] = []
    rules_applied: List[str] = []
    demand_variability_cv: Optional[float] = None
    changeover_adjusted: bool = False
    total_changeover_hours: Optional[float] = None
    changeover_details: List[Dict[str, Any]] = []
    glenday_summary: Optional[Dict[str, Any]] = None
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RCCPRunListResponse(BaseModel):
    """Paginated list of RCCP runs."""
    items: List[RCCPRunResponse]
    total: int
    page: int
    page_size: int


class RCCPMethodDetection(BaseModel):
    """Result of auto-detecting best RCCP method."""
    recommended_method: str
    reason: str
    bor_entry_count: int
    has_resource_detail: bool
    has_phase_detail: bool

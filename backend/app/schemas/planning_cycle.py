"""
Planning Cycle Pydantic Schemas

Request/response models for planning cycle and snapshot API.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


class CycleTypeEnum(str, Enum):
    """Type of planning cycle."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    AD_HOC = "ad_hoc"


class CycleStatusEnum(str, Enum):
    """Status of planning cycle."""
    DRAFT = "draft"
    DATA_COLLECTION = "data_collection"
    PLANNING = "planning"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    CLOSED = "closed"
    ARCHIVED = "archived"


class SnapshotTypeEnum(str, Enum):
    """Type of planning snapshot."""
    BASELINE = "baseline"
    WORKING = "working"
    CHECKPOINT = "checkpoint"
    PUBLISHED = "published"
    AUTO = "auto"


class SnapshotTierEnum(str, Enum):
    """Storage tier for snapshot."""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class DeltaOperationEnum(str, Enum):
    """Type of delta operation."""
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class DeltaEntityTypeEnum(str, Enum):
    """Entity type for delta tracking."""
    DEMAND = "demand"
    SUPPLY = "supply"
    INVENTORY = "inventory"
    FORECAST = "forecast"
    DECISION = "decision"
    KPI = "kpi"


# ============================================================================
# Planning Cycle Schemas
# ============================================================================

class PlanningCycleBase(BaseModel):
    """Base schema for planning cycle."""
    name: str = Field(..., max_length=200, description="Cycle name")
    description: Optional[str] = Field(None, max_length=1000)
    cycle_type: CycleTypeEnum = Field(..., description="Type of cycle")

    period_start: date = Field(..., description="Planning period start date")
    period_end: date = Field(..., description="Planning period end date")

    planning_horizon_weeks: int = Field(
        default=52, ge=1, le=104, description="Planning horizon in weeks"
    )

    @validator("period_end")
    def validate_period_end(cls, v, values):
        """Ensure period_end is after period_start."""
        if "period_start" in values and v <= values["period_start"]:
            raise ValueError("period_end must be after period_start")
        return v


class PlanningCycleCreate(PlanningCycleBase):
    """Schema for creating a planning cycle."""
    tenant_id: int = Field(..., gt=0, description="Tenant this cycle belongs to")
    owner_id: Optional[int] = Field(None, description="User who owns this cycle")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Q1 2026 Weekly Planning",
                "description": "Weekly S&OP planning cycle for Q1",
                "cycle_type": "weekly",
                "tenant_id": 1,
                "period_start": "2026-01-01",
                "period_end": "2026-03-31",
                "planning_horizon_weeks": 26
            }
        }


class PlanningCycleUpdate(BaseModel):
    """Schema for updating a planning cycle."""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    owner_id: Optional[int] = None
    planning_horizon_weeks: Optional[int] = Field(None, ge=1, le=104)


class PlanningCycleStatusUpdate(BaseModel):
    """Schema for updating cycle status."""
    status: CycleStatusEnum
    reason: Optional[str] = Field(None, max_length=500, description="Reason for status change")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "review",
                "reason": "Planning complete, ready for management review"
            }
        }


class PlanningCycleResponse(PlanningCycleBase):
    """Schema for planning cycle response."""
    id: int
    tenant_id: int
    owner_id: Optional[int] = None
    status: CycleStatusEnum

    baseline_snapshot_id: Optional[int] = None
    current_snapshot_id: Optional[int] = None
    published_snapshot_id: Optional[int] = None
    snapshot_count: int = 0

    retention_tier: Optional[SnapshotTierEnum] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Q1 2026 Weekly Planning",
                "cycle_type": "weekly",
                "tenant_id": 1,
                "status": "planning",
                "period_start": "2026-01-01",
                "period_end": "2026-03-31",
                "snapshot_count": 5,
                "created_at": "2026-01-01T00:00:00Z"
            }
        }


# ============================================================================
# Planning Snapshot Schemas
# ============================================================================

class PlanningSnapshotBase(BaseModel):
    """Base schema for planning snapshot."""
    commit_message: str = Field(..., max_length=500, description="Description of changes")
    snapshot_type: SnapshotTypeEnum = Field(default=SnapshotTypeEnum.WORKING)


class PlanningSnapshotCreate(PlanningSnapshotBase):
    """Schema for creating a planning snapshot."""
    cycle_id: int = Field(..., gt=0, description="Cycle this snapshot belongs to")

    demand_plan_data: Optional[Dict[str, Any]] = Field(None, description="Demand plan data")
    supply_plan_data: Optional[Dict[str, Any]] = Field(None, description="Supply plan data")
    inventory_data: Optional[Dict[str, Any]] = Field(None, description="Inventory data")
    forecast_data: Optional[Dict[str, Any]] = Field(None, description="Forecast data")
    kpi_data: Optional[Dict[str, Any]] = Field(None, description="KPI metrics")

    class Config:
        json_schema_extra = {
            "example": {
                "cycle_id": 1,
                "commit_message": "Updated demand forecast based on market intelligence",
                "snapshot_type": "working",
                "kpi_data": {
                    "total_demand": 50000,
                    "fill_rate_target": 0.95,
                    "inventory_value": 1250000
                }
            }
        }


class PlanningSnapshotResponse(PlanningSnapshotBase):
    """Schema for planning snapshot response."""
    id: int
    cycle_id: int
    parent_snapshot_id: Optional[int] = None
    version: int
    storage_tier: SnapshotTierEnum

    created_at: datetime
    created_by_id: Optional[int] = None

    record_counts: Optional[Dict[str, int]] = None
    data_size_bytes: Optional[int] = None
    compressed_size_bytes: Optional[int] = None

    collapsed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 15,
                "cycle_id": 1,
                "parent_snapshot_id": 14,
                "version": 5,
                "commit_message": "Updated demand forecast",
                "snapshot_type": "working",
                "storage_tier": "hot",
                "created_at": "2026-02-01T10:30:00Z",
                "record_counts": {"demand": 1500, "supply": 800},
                "data_size_bytes": 125000
            }
        }


class PlanningSnapshotDetailResponse(PlanningSnapshotResponse):
    """Schema for detailed snapshot response including data."""
    demand_plan_data: Optional[Dict[str, Any]] = None
    supply_plan_data: Optional[Dict[str, Any]] = None
    inventory_data: Optional[Dict[str, Any]] = None
    forecast_data: Optional[Dict[str, Any]] = None
    kpi_data: Optional[Dict[str, Any]] = None


# ============================================================================
# Snapshot Delta Schemas
# ============================================================================

class SnapshotDeltaResponse(BaseModel):
    """Schema for snapshot delta response."""
    id: int
    snapshot_id: int
    entity_type: DeltaEntityTypeEnum
    entity_id: str
    operation: DeltaOperationEnum

    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None

    changed_fields: Optional[List[str]] = None
    change_reason: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Comparison Schemas
# ============================================================================

class SnapshotComparisonRequest(BaseModel):
    """Request to compare two snapshots."""
    other_version: int = Field(..., description="Version to compare against")
    include_details: bool = Field(default=False, description="Include detailed field-level changes")

    class Config:
        json_schema_extra = {
            "example": {
                "other_version": 3,
                "include_details": True
            }
        }


class SnapshotComparisonResponse(BaseModel):
    """Response from snapshot comparison."""
    snapshot_a_id: int
    snapshot_a_version: int
    snapshot_b_id: int
    snapshot_b_version: int

    changes_summary: Dict[str, int] = Field(
        description="Count of changes by entity type"
    )
    kpi_delta: Optional[Dict[str, Any]] = Field(
        None, description="KPI metric differences"
    )
    detailed_changes: Optional[Dict[str, List[Dict[str, Any]]]] = Field(
        None, description="Detailed field-level changes"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "snapshot_a_id": 15,
                "snapshot_a_version": 5,
                "snapshot_b_id": 12,
                "snapshot_b_version": 3,
                "changes_summary": {
                    "demand": {"added": 10, "modified": 45, "deleted": 2},
                    "supply": {"added": 5, "modified": 20, "deleted": 0}
                },
                "kpi_delta": {
                    "total_demand": {"old": 48000, "new": 50000, "change": 2000},
                    "fill_rate_target": {"old": 0.93, "new": 0.95, "change": 0.02}
                }
            }
        }


# ============================================================================
# Snapshot Chain Schemas
# ============================================================================

class SnapshotChainResponse(BaseModel):
    """Response showing snapshot lineage chain."""
    snapshot_id: int
    ancestors: List[PlanningSnapshotResponse]
    total_ancestors: int


# ============================================================================
# List Response Schemas
# ============================================================================

class PlanningCycleListResponse(BaseModel):
    """Response for listing planning cycles."""
    items: List[PlanningCycleResponse]
    total: int
    page: int
    page_size: int


class PlanningSnapshotListResponse(BaseModel):
    """Response for listing planning snapshots."""
    items: List[PlanningSnapshotResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Retention Stats Schema
# ============================================================================

class RetentionStatsResponse(BaseModel):
    """Response with retention statistics."""
    total_snapshots: int
    by_tier: Dict[str, int]
    by_type: Dict[str, int]
    storage_estimate: Dict[str, int]

    class Config:
        json_schema_extra = {
            "example": {
                "total_snapshots": 150,
                "by_tier": {"hot": 45, "warm": 80, "cold": 25},
                "by_type": {"baseline": 10, "working": 100, "published": 10, "auto": 30},
                "storage_estimate": {
                    "hot_bytes": 15000000,
                    "compressed_bytes": 8000000,
                    "total_bytes": 23000000
                }
            }
        }

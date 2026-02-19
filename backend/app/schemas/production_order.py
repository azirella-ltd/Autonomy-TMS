"""
Production Order Pydantic Schemas

Request/response schemas for Production Order API endpoints.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


# ==================== Component Schemas ====================

class ProductionOrderComponentBase(BaseModel):
    """Base schema for production order component."""
    component_item_id: int = Field(..., description="Component item ID from BOM")
    planned_quantity: float = Field(..., gt=0, description="Planned quantity from BOM")
    unit_of_measure: str = Field(default="EA", description="Unit of measure")


class ProductionOrderComponentCreate(ProductionOrderComponentBase):
    """Schema for creating a production order component."""
    pass


class ProductionOrderComponentUpdate(BaseModel):
    """Schema for updating component actual quantities."""
    actual_quantity: Optional[float] = Field(None, ge=0)
    scrap_quantity: Optional[float] = Field(None, ge=0)


class ProductionOrderComponent(ProductionOrderComponentBase):
    """Schema for production order component response."""
    id: int
    production_order_id: int
    actual_quantity: Optional[float]
    scrap_quantity: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Production Order Schemas ====================

class ProductionOrderBase(BaseModel):
    """Base schema for production order."""
    item_id: int = Field(..., description="Item to produce")
    site_id: int = Field(..., description="Production site (node)")
    config_id: int = Field(..., description="Supply chain configuration")
    planned_quantity: int = Field(..., gt=0, description="Quantity to produce")
    planned_start_date: datetime = Field(..., description="Planned start date")
    planned_completion_date: datetime = Field(..., description="Planned completion date")
    priority: int = Field(default=5, ge=1, le=10, description="Priority (1=highest, 10=lowest)")
    lead_time_planned: int = Field(default=1, gt=0, description="Planned lead time in days")
    notes: Optional[str] = Field(None, max_length=500, description="Order notes")

    @validator('planned_completion_date')
    def completion_after_start(cls, v, values):
        if 'planned_start_date' in values and v <= values['planned_start_date']:
            raise ValueError('Completion date must be after start date')
        return v


class ProductionOrderCreate(ProductionOrderBase):
    """Schema for creating a new production order."""
    mps_plan_id: Optional[int] = Field(None, description="Optional MPS plan reference")
    resource_hours_planned: Optional[float] = Field(None, ge=0)
    setup_cost: Optional[float] = Field(default=0.0, ge=0)
    unit_cost: Optional[float] = Field(default=0.0, ge=0)
    components: Optional[List[ProductionOrderComponentCreate]] = Field(
        default=None,
        description="Optional BOM components (auto-populated if not provided)"
    )


class ProductionOrderUpdate(BaseModel):
    """Schema for updating a production order."""
    planned_quantity: Optional[int] = Field(None, gt=0)
    planned_start_date: Optional[datetime] = None
    planned_completion_date: Optional[datetime] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = Field(None, max_length=500)
    resource_hours_planned: Optional[float] = Field(None, ge=0)


class ProductionOrderRelease(BaseModel):
    """Schema for releasing a production order."""
    release_notes: Optional[str] = Field(None, max_length=500)


class ProductionOrderStart(BaseModel):
    """Schema for starting production."""
    actual_start_date: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="Actual start date (defaults to now)"
    )
    notes: Optional[str] = Field(None, max_length=500)


class ProductionOrderComplete(BaseModel):
    """Schema for completing production."""
    actual_quantity: int = Field(..., gt=0, description="Actual quantity produced")
    scrap_quantity: int = Field(default=0, ge=0, description="Scrap quantity")
    actual_completion_date: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="Actual completion date (defaults to now)"
    )
    resource_hours_actual: Optional[float] = Field(None, ge=0)
    components: Optional[List[ProductionOrderComponentUpdate]] = Field(
        default=None,
        description="Actual component consumption"
    )
    notes: Optional[str] = Field(None, max_length=500)


class ProductionOrderClose(BaseModel):
    """Schema for closing a production order."""
    close_notes: Optional[str] = Field(None, max_length=500)


class ProductionOrderCancel(BaseModel):
    """Schema for cancelling a production order."""
    cancel_reason: str = Field(..., max_length=500, description="Reason for cancellation")


class ProductionOrder(ProductionOrderBase):
    """Schema for production order response."""
    id: int
    order_number: str
    mps_plan_id: Optional[int]
    status: str
    actual_quantity: Optional[int]
    scrap_quantity: int
    yield_percentage: Optional[float]
    planned_start_date: datetime
    planned_completion_date: datetime
    actual_start_date: Optional[datetime]
    actual_completion_date: Optional[datetime]
    released_date: Optional[datetime]
    closed_date: Optional[datetime]
    lead_time_planned: int
    lead_time_actual: Optional[int]
    priority: int
    resource_hours_planned: Optional[float]
    resource_hours_actual: Optional[float]
    setup_cost: float
    unit_cost: float
    total_cost: float
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int]
    updated_by_id: Optional[int]
    is_deleted: bool

    # Computed properties
    is_overdue: bool
    days_until_due: int
    is_on_time: bool

    class Config:
        from_attributes = True


class ProductionOrderWithComponents(ProductionOrder):
    """Schema for production order with component details."""
    components: List[ProductionOrderComponent] = Field(default_factory=list)


class ProductionOrderList(BaseModel):
    """Schema for paginated list of production orders."""
    total: int
    page: int
    page_size: int
    orders: List[ProductionOrder]


class ProductionOrderSummary(BaseModel):
    """Schema for production order summary statistics."""
    total_orders: int
    planned_orders: int
    released_orders: int
    in_progress_orders: int
    completed_orders: int
    closed_orders: int
    cancelled_orders: int
    overdue_orders: int
    avg_yield_percentage: Optional[float]
    avg_lead_time_actual: Optional[float]
    on_time_delivery_rate: Optional[float]


# ==================== Filter Schemas ====================

class ProductionOrderFilters(BaseModel):
    """Schema for filtering production orders."""
    status: Optional[str] = Field(None, description="Filter by status")
    item_id: Optional[int] = Field(None, description="Filter by item")
    site_id: Optional[int] = Field(None, description="Filter by site")
    config_id: Optional[int] = Field(None, description="Filter by config")
    mps_plan_id: Optional[int] = Field(None, description="Filter by MPS plan")
    priority_min: Optional[int] = Field(None, ge=1, le=10)
    priority_max: Optional[int] = Field(None, ge=1, le=10)
    start_date_from: Optional[datetime] = None
    start_date_to: Optional[datetime] = None
    is_overdue: Optional[bool] = None
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(
        default="planned_start_date",
        description="Sort field (planned_start_date, priority, status, etc.)"
    )
    sort_order: Optional[str] = Field(
        default="asc",
        description="Sort order (asc or desc)"
    )


# ==================== Type Aliases for API Responses ====================
# Create aliases for endpoint compatibility
ProductionOrderResponse = ProductionOrder
ProductionOrderListResponse = ProductionOrderList

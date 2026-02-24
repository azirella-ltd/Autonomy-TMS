"""
Inventory Projection Schemas - Pydantic v2

Schemas for ATP/CTP projection and order promising.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime, date
from typing import Optional, List
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class AtpRuleType(str, Enum):
    """ATP calculation rule types"""
    DISCRETE = "discrete"  # Period-by-period ATP
    CUMULATIVE = "cumulative"  # Cumulative ATP across periods
    ROLLING = "rolling"  # Rolling time window ATP


class PromiseSource(str, Enum):
    """Source of promise"""
    ATP = "ATP"  # Available-to-Promise (existing inventory)
    CTP = "CTP"  # Capable-to-Promise (future production)
    BACKORDER = "BACKORDER"  # Cannot fulfill, backorder


class FulfillmentType(str, Enum):
    """Order fulfillment strategy"""
    SINGLE = "single"  # Single shipment from one location
    PARTIAL = "partial"  # Partial quantity fulfillment
    SPLIT = "split"  # Multiple shipments over time
    SUBSTITUTE = "substitute"  # Alternative product substitution


class PromiseStatus(str, Enum):
    """Order promise status"""
    PROPOSED = "PROPOSED"  # Initial promise proposal
    CONFIRMED = "CONFIRMED"  # Customer confirmed
    FULFILLED = "FULFILLED"  # Order fulfilled
    CANCELLED = "CANCELLED"  # Promise cancelled


# ============================================================================
# Inventory Projection Schemas
# ============================================================================

class InvProjectionBase(BaseModel):
    """Base schema for inventory projection"""
    company_id: int
    product_id: int
    site_id: int
    projection_date: date

    on_hand_qty: float = Field(0.0, ge=0)
    in_transit_qty: float = Field(0.0, ge=0)
    on_order_qty: float = Field(0.0, ge=0)
    allocated_qty: float = Field(0.0, ge=0)
    available_qty: float = Field(0.0, ge=0)
    reserved_qty: float = Field(0.0, ge=0)

    supply_qty: float = Field(0.0, ge=0)
    demand_qty: float = Field(0.0, ge=0)

    opening_inventory: float = Field(0.0)
    closing_inventory: float = Field(0.0)

    atp_qty: float = Field(0.0, ge=0)
    ctp_qty: float = Field(0.0, ge=0)

    # Stochastic projections
    closing_inventory_p10: Optional[float] = None
    closing_inventory_p50: Optional[float] = None
    closing_inventory_p90: Optional[float] = None
    closing_inventory_std_dev: Optional[float] = None

    # Risk metrics
    stockout_probability: Optional[float] = Field(None, ge=0, le=1)
    days_of_supply: Optional[float] = Field(None, ge=0)

    # Scenario tracking
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None

    # Beer Game integration
    config_id: Optional[int] = None
    scenario_id: Optional[int] = None
    round_number: Optional[int] = None


class InvProjectionCreate(InvProjectionBase):
    """Schema for creating inventory projection"""
    pass


class InvProjectionUpdate(BaseModel):
    """Schema for updating inventory projection"""
    on_hand_qty: Optional[float] = Field(None, ge=0)
    in_transit_qty: Optional[float] = Field(None, ge=0)
    allocated_qty: Optional[float] = Field(None, ge=0)
    available_qty: Optional[float] = Field(None, ge=0)
    supply_qty: Optional[float] = Field(None, ge=0)
    demand_qty: Optional[float] = Field(None, ge=0)
    atp_qty: Optional[float] = Field(None, ge=0)
    ctp_qty: Optional[float] = Field(None, ge=0)


class InvProjectionResponse(InvProjectionBase):
    """Schema for inventory projection response"""
    id: int
    created_by: Optional[int]
    created_at: datetime
    updated_by: Optional[int]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class InvProjectionList(BaseModel):
    """Paginated list of inventory projections"""
    items: List[InvProjectionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# ATP Projection Schemas
# ============================================================================

class AtpProjectionBase(BaseModel):
    """Base schema for ATP projection"""
    company_id: int
    product_id: int
    site_id: int
    atp_date: date

    atp_qty: float = Field(0.0)
    cumulative_atp_qty: float = Field(0.0)

    opening_balance: float = Field(0.0)
    supply_qty: float = Field(0.0, ge=0)
    demand_qty: float = Field(0.0, ge=0)
    allocated_qty: float = Field(0.0, ge=0)

    # Customer allocation
    customer_id: Optional[str] = None
    allocation_percentage: Optional[float] = Field(None, ge=0, le=100)
    allocation_priority: Optional[int] = Field(None, ge=1)

    # ATP rules
    atp_rule: Optional[AtpRuleType] = None
    time_fence_days: Optional[int] = Field(None, ge=0)

    # Beer Game integration
    config_id: Optional[int] = None
    scenario_id: Optional[int] = None


class AtpProjectionCreate(AtpProjectionBase):
    """Schema for creating ATP projection"""
    pass


class AtpProjectionResponse(AtpProjectionBase):
    """Schema for ATP projection response"""
    id: int
    created_by: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AtpProjectionList(BaseModel):
    """Paginated list of ATP projections"""
    items: List[AtpProjectionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# CTP Projection Schemas
# ============================================================================

class CtpProjectionBase(BaseModel):
    """Base schema for CTP projection"""
    company_id: int
    product_id: int
    site_id: int
    ctp_date: date

    ctp_qty: float = Field(0.0, ge=0)
    atp_qty: float = Field(0.0, ge=0)
    production_capacity_qty: float = Field(0.0, ge=0)

    total_capacity: Optional[float] = Field(None, ge=0)
    committed_capacity: Optional[float] = Field(None, ge=0)
    available_capacity: Optional[float] = Field(None, ge=0)

    # Constraints
    component_constrained: bool = False
    constraining_component_id: Optional[int] = None
    resource_constrained: bool = False
    constraining_resource: Optional[str] = None

    # Lead time
    production_lead_time: Optional[int] = Field(None, ge=0)
    earliest_ship_date: Optional[date] = None

    # Beer Game integration
    config_id: Optional[int] = None
    scenario_id: Optional[int] = None


class CtpProjectionCreate(CtpProjectionBase):
    """Schema for creating CTP projection"""
    pass


class CtpProjectionResponse(CtpProjectionBase):
    """Schema for CTP projection response"""
    id: int
    created_by: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CtpProjectionList(BaseModel):
    """Paginated list of CTP projections"""
    items: List[CtpProjectionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# Order Promise Schemas
# ============================================================================

class OrderPromiseBase(BaseModel):
    """Base schema for order promise"""
    order_id: str = Field(..., max_length=100)
    order_line_number: int = Field(..., ge=1)

    company_id: int
    product_id: int
    site_id: int
    customer_id: Optional[str] = None

    requested_quantity: float = Field(..., gt=0)
    requested_date: date

    promised_quantity: float = Field(..., ge=0)
    promised_date: date
    promise_source: PromiseSource

    # Fulfillment strategy
    fulfillment_type: FulfillmentType = FulfillmentType.SINGLE
    partial_promise: bool = False
    backorder_quantity: Optional[float] = Field(None, ge=0)
    backorder_date: Optional[date] = None

    # Alternative options
    alternative_quantity: Optional[float] = Field(None, ge=0)
    alternative_date: Optional[date] = None
    alternative_product_id: Optional[int] = None

    # Status
    promise_status: PromiseStatus = PromiseStatus.PROPOSED
    promise_confidence: Optional[float] = Field(None, ge=0, le=1)

    @field_validator('promised_quantity')
    @classmethod
    def validate_promised_quantity(cls, v: float, info) -> float:
        """Validate promised quantity doesn't exceed requested"""
        if 'requested_quantity' in info.data and v > info.data['requested_quantity']:
            raise ValueError("Promised quantity cannot exceed requested quantity")
        return v


class OrderPromiseCreate(OrderPromiseBase):
    """Schema for creating order promise"""
    pass


class OrderPromiseUpdate(BaseModel):
    """Schema for updating order promise"""
    promised_quantity: Optional[float] = Field(None, ge=0)
    promised_date: Optional[date] = None
    promise_source: Optional[PromiseSource] = None
    fulfillment_type: Optional[FulfillmentType] = None
    backorder_quantity: Optional[float] = Field(None, ge=0)
    backorder_date: Optional[date] = None
    promise_status: Optional[PromiseStatus] = None
    promise_confidence: Optional[float] = Field(None, ge=0, le=1)


class OrderPromiseResponse(OrderPromiseBase):
    """Schema for order promise response"""
    id: int
    created_by: Optional[int]
    created_at: datetime
    updated_by: Optional[int]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class OrderPromiseList(BaseModel):
    """Paginated list of order promises"""
    items: List[OrderPromiseResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# Request/Response Schemas for ATP/CTP Calculation
# ============================================================================

class CalculateAtpRequest(BaseModel):
    """Request schema for ATP calculation"""
    product_id: int
    site_id: int
    start_date: date
    end_date: date
    atp_rule: AtpRuleType = AtpRuleType.CUMULATIVE
    customer_id: Optional[str] = None
    config_id: Optional[int] = None
    scenario_id: Optional[int] = None


class CalculateCtpRequest(BaseModel):
    """Request schema for CTP calculation"""
    product_id: int
    site_id: int
    start_date: date
    end_date: date
    include_production_capacity: bool = True
    check_component_availability: bool = True
    check_resource_capacity: bool = True
    config_id: Optional[int] = None
    scenario_id: Optional[int] = None


class OrderPromiseRequest(BaseModel):
    """Request schema for order promising"""
    order_id: str
    order_line_number: int
    product_id: int
    site_id: int
    customer_id: Optional[str] = None
    requested_quantity: float = Field(..., gt=0)
    requested_date: date
    allow_partial: bool = True
    allow_substitute: bool = False
    allow_backorder: bool = True
    config_id: Optional[int] = None


class OrderPromiseResult(BaseModel):
    """Result schema for order promising"""
    can_promise: bool
    promised_quantity: float
    promised_date: date
    promise_source: PromiseSource
    fulfillment_type: FulfillmentType

    # Partial fulfillment
    partial_promise: bool = False
    backorder_quantity: Optional[float] = None
    backorder_date: Optional[date] = None

    # Alternatives
    alternatives: List['AlternativePromise'] = []

    # Confidence
    confidence: float = Field(..., ge=0, le=1)
    confidence_factors: List[str] = []


class AlternativePromise(BaseModel):
    """Alternative promise option"""
    option_type: str  # "later_date", "partial_quantity", "substitute_product"
    product_id: int
    quantity: float
    delivery_date: date
    confidence: float


# ============================================================================
# Projection Summary Schemas
# ============================================================================

class InvProjectionSummary(BaseModel):
    """Summary statistics for inventory projections"""
    total_projections: int
    date_range: str
    total_on_hand: float
    total_available: float
    total_atp: float
    total_ctp: float
    average_dos: Optional[float]
    stockout_count: int
    high_risk_products: int


class AtpAvailability(BaseModel):
    """ATP availability for a product-site"""
    product_id: int
    site_id: int
    current_atp: float
    future_atp: List['AtpByDate']
    total_available: float


class AtpByDate(BaseModel):
    """ATP quantity by date"""
    date: date
    atp_qty: float
    cumulative_atp: float


class CtpAvailability(BaseModel):
    """CTP availability for a product-site"""
    product_id: int
    site_id: int
    current_ctp: float
    future_ctp: List['CtpByDate']
    constraints: List[str]


class CtpByDate(BaseModel):
    """CTP quantity by date"""
    date: date
    ctp_qty: float
    constrained: bool
    constraint_reason: Optional[str]


# Forward references
OrderPromiseResult.model_rebuild()

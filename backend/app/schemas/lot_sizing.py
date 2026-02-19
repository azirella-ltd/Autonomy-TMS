"""
Lot Sizing Schemas - Pydantic v2

Schemas for lot sizing calculations and comparisons.
"""

from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import List, Optional, Dict
from enum import Enum


class LotSizingAlgorithm(str, Enum):
    """Available lot sizing algorithms"""
    LFL = "LFL"  # Lot-for-Lot
    EOQ = "EOQ"  # Economic Order Quantity
    POQ = "POQ"  # Period Order Quantity
    FOQ = "FOQ"  # Fixed Order Quantity
    PPB = "PPB"  # Part Period Balancing


class LotSizingInputRequest(BaseModel):
    """Request schema for lot sizing calculation"""
    demand_schedule: List[float] = Field(..., min_length=1, description="Demand by period")
    start_date: date = Field(..., description="Start date of first period")
    period_days: int = Field(7, ge=1, le=365, description="Days per period (default: 7 for weekly)")

    # Cost parameters
    setup_cost: float = Field(0.0, ge=0, description="Fixed cost per order/setup (K)")
    holding_cost_per_unit_per_period: float = Field(0.0, ge=0, description="Holding cost per unit per period (h)")
    unit_cost: float = Field(0.0, ge=0, description="Cost per unit (c)")

    # Constraints
    min_order_quantity: Optional[float] = Field(None, ge=0, description="Minimum order quantity")
    max_order_quantity: Optional[float] = Field(None, ge=0, description="Maximum order quantity")
    order_multiple: Optional[float] = Field(None, ge=0, description="Order in multiples of this value")

    # For EOQ/POQ
    annual_demand: Optional[float] = Field(None, ge=0, description="Annual demand (optional, estimated if not provided)")

    # For FOQ
    fixed_quantity: Optional[float] = Field(None, ge=0, description="Fixed order quantity (for FOQ algorithm)")

    @field_validator('demand_schedule')
    @classmethod
    def validate_demand(cls, v: List[float]) -> List[float]:
        """Validate demand schedule has non-negative values"""
        if any(d < 0 for d in v):
            raise ValueError("Demand must be non-negative")
        return v


class LotSizingResultResponse(BaseModel):
    """Response schema for lot sizing result"""
    algorithm: str = Field(..., description="Algorithm used")
    order_schedule: List[float] = Field(..., description="Order quantities by period")
    total_cost: float = Field(..., description="Total cost (setup + holding)")
    setup_cost_total: float = Field(..., description="Total setup costs")
    holding_cost_total: float = Field(..., description="Total holding costs")
    number_of_orders: int = Field(..., description="Number of orders placed")
    average_inventory: float = Field(..., description="Average inventory level")
    service_level: float = Field(1.0, description="Percentage of demand met")
    inventory_turns: Optional[float] = Field(None, description="Inventory turnover ratio")
    details: Optional[Dict] = Field(None, description="Algorithm-specific details")


class LotSizingComparisonRequest(BaseModel):
    """Request schema for comparing multiple algorithms"""
    demand_schedule: List[float] = Field(..., min_length=1)
    start_date: date
    period_days: int = Field(7, ge=1, le=365)

    setup_cost: float = Field(0.0, ge=0)
    holding_cost_per_unit_per_period: float = Field(0.0, ge=0)
    unit_cost: float = Field(0.0, ge=0)

    min_order_quantity: Optional[float] = Field(None, ge=0)
    max_order_quantity: Optional[float] = Field(None, ge=0)
    order_multiple: Optional[float] = Field(None, ge=0)
    annual_demand: Optional[float] = Field(None, ge=0)
    fixed_quantity: Optional[float] = Field(None, ge=0)

    algorithms: List[LotSizingAlgorithm] = Field(
        default=[LotSizingAlgorithm.LFL, LotSizingAlgorithm.EOQ, LotSizingAlgorithm.POQ,
                 LotSizingAlgorithm.FOQ, LotSizingAlgorithm.PPB],
        description="Algorithms to compare"
    )


class LotSizingComparisonResponse(BaseModel):
    """Response schema for algorithm comparison"""
    results: Dict[str, LotSizingResultResponse] = Field(..., description="Results by algorithm")
    best_algorithm: str = Field(..., description="Algorithm with lowest total cost")
    best_total_cost: float = Field(..., description="Lowest total cost achieved")
    cost_savings_vs_lfl: Optional[float] = Field(None, description="Cost savings vs Lot-for-Lot (%)")


class MPSLotSizingRequest(BaseModel):
    """Request schema for applying lot sizing to MPS plan"""
    plan_id: int = Field(..., description="MPS plan ID")
    algorithm: LotSizingAlgorithm = Field(..., description="Lot sizing algorithm to apply")

    # Cost parameters (if not in MPS plan)
    setup_cost: Optional[float] = Field(None, ge=0)
    holding_cost_per_unit_per_period: Optional[float] = Field(None, ge=0)
    unit_cost: Optional[float] = Field(None, ge=0)

    # Constraints (if not in MPS plan)
    min_order_quantity: Optional[float] = Field(None, ge=0)
    max_order_quantity: Optional[float] = Field(None, ge=0)
    order_multiple: Optional[float] = Field(None, ge=0)
    fixed_quantity: Optional[float] = Field(None, ge=0)


class MPSLotSizingResponse(BaseModel):
    """Response schema for MPS lot sizing"""
    plan_id: int
    algorithm: str
    items_processed: int
    total_cost_before: float
    total_cost_after: float
    cost_savings: float
    cost_savings_percent: float
    items: List[Dict] = Field(..., description="Lot sized schedules by item")


class LotSizingVisualizationData(BaseModel):
    """Data for visualizing lot sizing results"""
    periods: List[str] = Field(..., description="Period labels (dates)")
    demand: List[float] = Field(..., description="Demand by period")
    orders: List[float] = Field(..., description="Order quantities by period")
    inventory: List[float] = Field(..., description="Ending inventory by period")
    cumulative_cost: List[float] = Field(..., description="Cumulative cost by period")


# ============================================================================
# Capacity-Constrained MPS Schemas
# ============================================================================

class ResourceRequirementRequest(BaseModel):
    """Resource requirement definition"""
    resource_id: str = Field(..., description="Unique resource identifier")
    resource_name: str = Field(..., description="Resource name")
    units_per_product: float = Field(..., ge=0, description="Resource units required per product unit")
    available_capacity: float = Field(..., ge=0, description="Available capacity per period")
    utilization_target: float = Field(0.85, ge=0, le=1, description="Target utilization (0.85 = 85%)")


class CapacityCheckRequest(BaseModel):
    """Request schema for capacity check"""
    production_plan: List[float] = Field(..., min_length=1, description="Planned production quantities by period")
    start_date: date = Field(..., description="Start date of first period")
    period_days: int = Field(7, ge=1, le=365, description="Days per period")
    resources: List[ResourceRequirementRequest] = Field(..., min_length=1, description="Resource requirements")
    strategy: str = Field("level", description="Leveling strategy (level/shift/reduce)")
    product_id: Optional[int] = Field(None, description="Product ID (optional)")
    product_name: Optional[str] = Field(None, description="Product name (optional)")


class CapacityCheckDetail(BaseModel):
    """Capacity check detail for one period-resource combination"""
    period: int
    period_date: str
    resource_id: str
    resource_name: str
    required_capacity: float
    available_capacity: float
    utilization: float
    is_constrained: bool
    is_over_target: bool
    shortage: float


class CapacityCheckResponse(BaseModel):
    """Response schema for capacity check"""
    original_plan: List[float]
    feasible_plan: List[float]
    is_feasible: bool
    capacity_checks: List[CapacityCheckDetail]
    bottleneck_resources: List[str]
    total_shortage: float
    utilization_summary: Dict[str, float]
    recommendations: List[str]


# ============================================================================
# Multi-Product Lot Sizing Schemas
# ============================================================================

class ProductLotSizingInput(BaseModel):
    """Input for a single product in multi-product lot sizing"""
    product_id: int = Field(..., description="Product ID")
    product_name: str = Field(..., description="Product name")
    demand_schedule: List[float] = Field(..., min_length=1, description="Demand by period")
    setup_cost: float = Field(0.0, ge=0, description="Setup cost per order")
    holding_cost_per_unit_per_period: float = Field(0.0, ge=0, description="Holding cost")
    unit_cost: float = Field(0.0, ge=0, description="Unit cost")
    min_order_quantity: Optional[float] = Field(None, ge=0)
    max_order_quantity: Optional[float] = Field(None, ge=0)
    order_multiple: Optional[float] = Field(None, ge=0)
    fixed_quantity: Optional[float] = Field(None, ge=0)


class MultiProductLotSizingRequest(BaseModel):
    """Request for multi-product lot sizing"""
    products: List[ProductLotSizingInput] = Field(..., min_length=1, description="Products to optimize")
    start_date: date = Field(..., description="Start date")
    period_days: int = Field(7, ge=1, le=365, description="Days per period")
    algorithm: LotSizingAlgorithm = Field(..., description="Algorithm to apply to all products")


class ProductLotSizingResult(BaseModel):
    """Result for a single product in multi-product lot sizing"""
    product_id: int
    product_name: str
    algorithm: str
    order_schedule: List[float]
    total_cost: float
    setup_cost_total: float
    holding_cost_total: float
    number_of_orders: int
    average_inventory: float


class MultiProductLotSizingResponse(BaseModel):
    """Response for multi-product lot sizing"""
    products: List[ProductLotSizingResult] = Field(..., description="Results by product")
    total_cost: float = Field(..., description="Combined total cost across all products")
    total_orders: int = Field(..., description="Total number of orders across all products")
    summary: Dict[str, float] = Field(..., description="Summary statistics")

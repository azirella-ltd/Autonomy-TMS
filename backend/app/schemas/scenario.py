"""Scenario schemas - Pydantic models for supply chain simulation scenarios.

Terminology (Feb 2026):
- Game -> Scenario
- Player -> ScenarioUser (in API/code)
- Player -> User (in UI)
- Gamification -> Simulation
- Round -> Period (in user-facing contexts)
- play_round -> execute_period
"""
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, validator, root_validator

from app.core.time_buckets import TimeBucket, DEFAULT_START_DATE
from .participant import (
    ScenarioUserAssignment, ScenarioUserResponse, ScenarioUserUpdate, ScenarioUserRole,
    ScenarioUser, ScenarioUserCreate,
    # Backward compatibility aliases
    ParticipantAssignment, ParticipantResponse, ParticipantUpdate, ParticipantRole,
    Participant, ParticipantCreate,
)


class DemandPatternType(str, Enum):
    """Type of demand pattern for scenario simulation."""
    CLASSIC = "classic"
    RANDOM = "random"
    SEASONAL = "seasonal"
    CONSTANT = "constant"
    LOGNORMAL = "lognormal"


class DemandPattern(BaseModel):
    """Configuration for demand pattern in a scenario."""
    type: DemandPatternType = Field(..., description="Type of demand pattern")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the demand pattern"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "classic",
                "params": {
                    "initial_demand": 4,
                    "change_week": 6,
                    "final_demand": 8
                }
            }
        }
    )


class ScenarioStatus(str, Enum):
    """Status of a simulation scenario."""
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"


class RolePricing(BaseModel):
    """Pricing configuration for a supply chain role."""
    selling_price: float = Field(..., gt=0, description="Selling price per unit")
    standard_cost: float = Field(..., gt=0, description="Standard cost per unit")

    @root_validator(skip_on_failure=True)
    def validate_margin(cls, values):
        selling_price = values.get('selling_price')
        standard_cost = values.get('standard_cost')
        if selling_price is not None and standard_cost is not None and selling_price <= standard_cost:
            raise ValueError('Selling price must be greater than standard cost')
        return values


class PricingConfig(BaseModel):
    """Pricing configuration for all roles in the supply chain."""
    retailer: RolePricing = Field(
        default_factory=lambda: RolePricing(selling_price=100.0, standard_cost=80.0),
        description="Pricing configuration for the retailer role"
    )
    wholesaler: RolePricing = Field(
        default_factory=lambda: RolePricing(selling_price=75.0, standard_cost=60.0),
        description="Pricing configuration for the wholesaler role"
    )
    distributor: RolePricing = Field(
        default_factory=lambda: RolePricing(selling_price=60.0, standard_cost=45.0),
        description="Pricing configuration for the distributor role"
    )
    manufacturer: RolePricing = Field(
        default_factory=lambda: RolePricing(selling_price=45.0, standard_cost=30.0),
        description="Pricing configuration for the manufacturer role"
    )


class NodePolicy(BaseModel):
    """Policy configuration for a supply chain node."""
    order_leadtime: int = Field(ge=0, le=52, default=0)
    supply_leadtime: int = Field(ge=0, le=52, default=1)
    init_inventory: int = Field(ge=0, default=12)
    price: float = Field(ge=0, default=0)
    standard_cost: float = Field(ge=0, default=0)
    variable_cost: float = Field(ge=0, default=0)
    min_order_qty: int = Field(ge=0, default=0)
    partial_order_fulfillment: bool = Field(default=True)

    model_config = ConfigDict(populate_by_name=True)


class AutonomyLLMToggles(BaseModel):
    """Toggle settings for Autonomy LLM agent features."""
    customer_demand_history_sharing: bool = Field(default=False)
    volatility_signal_sharing: bool = Field(default=False)
    downstream_inventory_visibility: bool = Field(default=False)


class AutonomyLLMConfig(BaseModel):
    """Configuration for Autonomy LLM agents."""
    toggles: AutonomyLLMToggles = Field(default_factory=AutonomyLLMToggles)
    shared_history_weeks: Optional[int] = Field(default=None, ge=0)
    volatility_window: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(extra="allow")


class ScenarioBase(BaseModel):
    """Base schema for scenario data."""
    name: str = Field(..., max_length=100)
    max_periods: int = Field(default=52, ge=1, le=1000)
    description: Optional[str] = Field(None, max_length=500)
    is_public: bool = Field(default=True, description="Whether the scenario is visible to all users")
    progression_mode: Literal['supervised', 'unsupervised'] = Field(
        default='supervised',
        description="Controls whether admin advances periods manually (supervised) or auto-progresses (unsupervised)",
    )
    supply_chain_config_id: Optional[int] = Field(
        default=None,
        description="Identifier of the linked supply chain configuration",
    )
    supply_chain_name: Optional[str] = Field(
        default=None,
        description="Friendly name of the linked supply chain configuration",
    )
    pricing_config: PricingConfig = Field(
        default_factory=PricingConfig,
        description="Pricing configuration for different roles in the supply chain"
    )
    node_policies: Optional[Dict[str, NodePolicy]] = Field(default=None)
    system_config: Optional[Dict[str, Any]] = Field(default=None)
    global_policy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional top-level policy values (lead times, inventory, costs, capacities)"
    )
    autonomy_llm: Optional[AutonomyLLMConfig] = Field(
        default=None,
        description="Configuration block for the Autonomy LLM Strategist",
    )

    model_config = ConfigDict(populate_by_name=True)


class ScenarioCreate(ScenarioBase):
    """Schema for creating a new scenario."""
    scenario_user_assignments: List[ScenarioUserAssignment] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="List of participant assignments for the scenario"
    )
    demand_pattern: DemandPattern = Field(
        default_factory=lambda: DemandPattern(
            type=DemandPatternType.CLASSIC,
            params={"initial_demand": 4, "change_week": 6, "final_demand": 8}
        ),
        description="Configuration for the demand pattern to use in the scenario"
    )

    model_config = ConfigDict(populate_by_name=True)


class ScenarioUpdate(BaseModel):
    """Schema for updating a scenario."""
    name: Optional[str] = Field(None, max_length=100)
    status: Optional[ScenarioStatus] = None
    current_period: Optional[int] = Field(None, ge=0)
    max_periods: Optional[int] = Field(None, ge=1, le=1000)
    description: Optional[str] = Field(None, max_length=500)
    is_public: Optional[bool] = None
    supply_chain_config_id: Optional[int] = None
    supply_chain_name: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)

    @validator('status')
    def validate_status_transition(cls, v, values, **kwargs):
        return v


class ScenarioInDBBase(ScenarioBase):
    """Base schema for scenario data from database."""
    id: int
    status: ScenarioStatus
    current_period: int
    demand_pattern: DemandPattern = Field(
        default_factory=lambda: DemandPattern(
            type=DemandPatternType.CLASSIC,
            params={"initial_demand": 4, "change_week": 6, "final_demand": 8}
        ),
        description="Configuration for the demand pattern used in the scenario"
    )
    pricing_config: PricingConfig = Field(
        default_factory=PricingConfig,
        description="Pricing configuration for different roles in the supply chain"
    )
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[int] = Field(None, description="User ID of the scenario creator")
    customer_id: Optional[int] = Field(None, description="Owning customer ID for the scenario")
    config: Dict[str, Any] = Field(default_factory=dict, description="Raw configuration blob")
    scenario_users: List[ScenarioUserResponse] = Field(default_factory=list)
    time_bucket: TimeBucket = Field(TimeBucket.WEEK, description="Time aggregation unit for the simulation")
    start_date: date = Field(default_factory=lambda: DEFAULT_START_DATE)
    current_period_start: Optional[date] = Field(
        None,
        description="Start date of the currently active period, if any"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Scenario(ScenarioInDBBase):
    """Complete scenario schema."""
    pass


class ScenarioInDB(ScenarioInDBBase):
    """Scenario model with database-specific fields."""
    pass


class ScenarioUserState(BaseModel):
    """Current state of a scenario user in a scenario."""
    id: int
    name: str
    role: ScenarioUserRole
    is_ai: bool
    current_stock: int
    incoming_shipments: List[Dict[str, Any]] = []
    backorders: int = 0
    total_cost: float = 0.0
    site_key: Optional[str] = Field(None, description="Canonical site key for complex supply chains")


class ScenarioState(ScenarioInDBBase):
    """Extended scenario state with scenario user states and current period information."""
    scenario_users: List[ScenarioUserState] = Field(default_factory=list)
    current_demand: Optional[int] = Field(None, description="Current period's customer demand")
    period_started_at: Optional[datetime] = Field(None, description="When the current period started")
    period_ends_at: Optional[datetime] = Field(None, description="When the current period will end")
    supply_chain_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Snapshot of the linked supply chain configuration (items, nodes, lanes)",
    )
    history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Lightweight per-period snapshots for dashboards (latest period first)",
    )

    model_config = ConfigDict(populate_by_name=True)


class OrderCreate(BaseModel):
    """Schema for creating an order."""
    quantity: int = Field(..., ge=0, description="Number of units to order")
    comment: Optional[str] = Field(None, max_length=255, description="Reason for this order")


class OrderResponse(BaseModel):
    """Schema for order response."""
    id: int
    scenario_id: int
    scenario_user_id: int
    period_number: int
    quantity: int
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class ScenarioUserPeriodBase(BaseModel):
    """Base schema for scenario user period data."""
    order_placed: int = Field(..., ge=0)
    order_received: int = Field(0, ge=0)
    inventory_before: int = Field(0, ge=0)
    inventory_after: int = Field(0, ge=0)
    backorders_before: int = Field(0, ge=0)
    backorders_after: int = Field(0, ge=0)
    holding_cost: float = Field(0.0, ge=0)
    backorder_cost: float = Field(0.0, ge=0)
    total_cost: float = Field(0.0, ge=0)
    comment: Optional[str] = Field(None, description="Scenario user's comment for this period")


class ScenarioUserPeriodCreate(ScenarioUserPeriodBase):
    """Schema for creating scenario user period data."""
    pass


class ScenarioUserPeriod(ScenarioUserPeriodBase):
    """Complete scenario user period schema."""
    id: int
    scenario_user_id: int
    period_id: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ScenarioPeriodBase(BaseModel):
    """Base schema for a scenario period."""
    period_number: int = Field(..., ge=1)
    customer_demand: int = Field(..., ge=0)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ScenarioPeriodCreate(ScenarioPeriodBase):
    """Schema for creating a scenario period."""
    pass


class ScenarioPeriod(ScenarioPeriodBase):
    """Complete scenario period schema."""
    id: int
    scenario_id: int
    created_at: datetime
    scenario_user_periods: List[ScenarioUserPeriod] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PeriodBase(BaseModel):
    """Base model for a period."""
    scenario_id: int
    period_number: int
    status: str = "pending"
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


class PeriodCreate(PeriodBase):
    """Model for creating a new period."""
    pass


class PeriodUpdate(BaseModel):
    """Model for updating a period."""
    status: Optional[str] = None
    completed_at: Optional[datetime] = None


class Period(PeriodBase):
    """Complete period model with database-specific fields."""
    id: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ScenarioUserActionBase(BaseModel):
    """Base model for scenario user actions."""
    scenario_id: int
    scenario_user_id: int
    period_id: int
    action_type: str
    quantity: int
    timestamp: datetime

    model_config = ConfigDict(populate_by_name=True)


class ScenarioUserActionCreate(ScenarioUserActionBase):
    """Model for creating a new scenario user action."""
    pass


class ScenarioUserActionUpdate(BaseModel):
    """Model for updating a scenario user action."""
    action_type: Optional[str] = None
    quantity: Optional[int] = None


class ScenarioUserAction(ScenarioUserActionBase):
    """Complete scenario user action model with database-specific fields."""
    id: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


__all__ = [
    # Core types
    'DemandPatternType',
    'DemandPattern',
    'ScenarioStatus',
    'RolePricing',
    'PricingConfig',
    'NodePolicy',
    'AutonomyLLMToggles',
    'AutonomyLLMConfig',
    # Scenario schemas
    'ScenarioBase',
    'ScenarioCreate',
    'ScenarioUpdate',
    'ScenarioInDBBase',
    'Scenario',
    'ScenarioInDB',
    'ScenarioState',
    # ScenarioUser schemas
    'ScenarioUser',
    'ScenarioUserCreate',
    'ScenarioUserAssignment',
    'ScenarioUserResponse',
    'ScenarioUserUpdate',
    'ScenarioUserRole',
    'ScenarioUserState',
    # Backward compatibility aliases
    'Participant',
    'ParticipantCreate',
    'ParticipantAssignment',
    'ParticipantResponse',
    'ParticipantUpdate',
    'ParticipantRole',
    # Period schemas
    'ScenarioUserPeriodBase',
    'ScenarioUserPeriodCreate',
    'ScenarioUserPeriod',
    'ScenarioPeriodBase',
    'ScenarioPeriodCreate',
    'ScenarioPeriod',
    'PeriodBase',
    'PeriodCreate',
    'PeriodUpdate',
    'Period',
    # Action schemas
    'ScenarioUserActionBase',
    'ScenarioUserActionCreate',
    'ScenarioUserActionUpdate',
    'ScenarioUserAction',
    # Order schemas
    'OrderCreate',
    'OrderResponse',
]


# =============================================================================
# Backward Compatibility Aliases (DEPRECATED - will be removed in future)
# =============================================================================

ParticipantState = ScenarioUserState
ParticipantPeriodBase = ScenarioUserPeriodBase
ParticipantPeriodCreate = ScenarioUserPeriodCreate
ParticipantPeriod = ScenarioUserPeriod
ParticipantActionBase = ScenarioUserActionBase
ParticipantActionCreate = ScenarioUserActionCreate
ParticipantActionUpdate = ScenarioUserActionUpdate
ParticipantAction = ScenarioUserAction

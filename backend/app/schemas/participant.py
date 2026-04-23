"""ScenarioUser schemas - Pydantic models for simulation scenario users.

Terminology (Feb 2026):
- Player -> ScenarioUser (in DB/code)
- Player -> User (in UI display)
- Scenario -> Scenario
"""
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from enum import Enum


class FunctionCategory(str, Enum):
    """Category of supply chain function."""
    PLANNING = "planning"    # Weekly/monthly horizon decisions
    EXECUTION = "execution"  # Daily/real-time horizon decisions


class ScenarioUserFunction(str, Enum):
    """Specific function a scenario user performs at a site.

    Planning functions operate on weekly/monthly horizons and set targets.
    Execution functions operate on daily/real-time (hourly/shift) horizons.
    """
    # Planning Functions (weekly/monthly)
    FORECASTING = "forecasting"
    DEMAND_PLANNING = "demand_planning"
    INVENTORY_PLANNING = "inventory_planning"
    SUPPLY_PLANNING = "supply_planning"
    ALLOCATION_PLANNING = "allocation_planning"

    # Execution Functions (hourly/shift-based)
    ATP_PROMISING = "atp_promising"
    SHIPPING = "shipping"
    PO_CREATION = "po_creation"
    RECEIVING = "receiving"

    # Legacy: Full node responsibility (backward compatibility)
    NODE_OPERATOR = "node_operator"


class AgentMode(str, Enum):
    """Agent decision mode for supply chain execution."""
    MANUAL = "manual"        # Human makes all decisions
    COPILOT = "copilot"      # AI suggests, human approves
    AUTONOMOUS = "autonomous"  # AI makes all decisions


class ScenarioUserRole(str, Enum):
    """Role of a scenario user in the supply chain simulation."""
    RETAILER = "retailer"
    WHOLESALER = "wholesaler"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    VENDOR = "vendor"


class ScenarioUserType(str, Enum):
    """Whether the scenario user is human or AI."""
    HUMAN = "human"
    AGENT = "agent"


class ScenarioUserStrategy(str, Enum):
    """Strategy used by the scenario user (human or AI)."""
    # Basic strategies
    NAIVE = "naive"
    BULLWHIP = "bullwhip"
    CONSERVATIVE = "conservative"
    RANDOM = "random"
    PID_HEURISTIC = "pid_heuristic"
    # Advanced strategies
    DEMAND_DRIVEN = "demand_driven"
    COST_OPTIMIZATION = "cost_optimization"
    # Autonomy LLM strategies
    LLM_CONSERVATIVE = "llm_conservative"
    LLM_BALANCED = "llm_balanced"
    LLM_AGGRESSIVE = "llm_aggressive"
    LLM_ADAPTIVE = "llm_adaptive"
    LLM_SUPERVISED = "llm_supervised"
    LLM_GLOBAL = "llm_global"
    # Autonomy strategies
    AUTONOMY_DTCE = "autonomy_dtce"
    AUTONOMY_DTCE_CENTRAL = "autonomy_dtce_central"
    AUTONOMY_DTCE_GLOBAL = "autonomy_dtce_global"


class ScenarioUserAssignment(BaseModel):
    """Schema for assigning a scenario user to a scenario role."""
    role: ScenarioUserRole
    scenario_user_type: ScenarioUserType = ScenarioUserType.HUMAN
    user_id: Optional[int] = None  # Required for human scenario users
    strategy: Optional[ScenarioUserStrategy] = ScenarioUserStrategy.NAIVE  # For AI scenario users
    can_see_demand: bool = False  # Whether this scenario user can see customer demand
    assignment_key: Optional[str] = Field(
        default=None,
        description="Unique identifier for this assignment; falls back to the canonical role when omitted.",
    )
    node_keys: List[str] = Field(
        default_factory=list,
        description="Canonical node identifiers covered by this scenario user assignment.",
    )
    llm_model: Optional[str] = Field(
        default="qwen3-8b", description="Selected Autonomy LLM when using Autonomy LLM strategies"
    )
    llm_config: Optional[dict] = None  # temperature, max_tokens, prompt
    basic_config: Optional[dict] = None  # heuristic params, e.g., base_stock_target, smoothing
    autonomy_override_pct: Optional[float] = Field(
        default=None,
        ge=0.05,
        le=0.5,
        description="Optional override percentage for centralized Autonomy coordination (0.05-0.5)",
    )

    # Function-specific fields (Feb 2026 expansion)
    function: Optional[ScenarioUserFunction] = Field(
        default=ScenarioUserFunction.NODE_OPERATOR,
        description="Functional responsibility (forecasting, atp_promising, etc.)"
    )
    agent_mode: Optional[AgentMode] = Field(
        default=AgentMode.MANUAL,
        description="Decision mode: MANUAL (human), COPILOT (AI suggests), AUTONOMOUS (AI decides)"
    )
    planning_horizon_weeks: Optional[int] = Field(
        default=None,
        ge=1,
        le=52,
        description="For planners: lookahead horizon in weeks (default from function)"
    )
    trm_agent_type: Optional[str] = Field(
        default=None,
        description="TRM agent type: atp_executor, po_creation_trm, etc."
    )

    @validator('user_id')
    def validate_user_id(cls, v, values):
        if values.get('scenario_user_type') == ScenarioUserType.HUMAN and v is None:
            raise ValueError("user_id is required for human scenario users")
        return v

    @validator('strategy')
    def validate_strategy(cls, v, values):
        if values.get('scenario_user_type') == ScenarioUserType.AGENT and v is None:
            raise ValueError("strategy is required for AI scenario users")
        return v


class ScenarioUserCreate(ScenarioUserAssignment):
    """Schema for creating a new scenario user (alias for ScenarioUserAssignment)."""
    pass


class ScenarioUserResponse(BaseModel):
    """Schema for scenario user response data."""
    id: int
    scenario_id: int
    user_id: Optional[int]
    role: ScenarioUserRole
    scenario_user_type: ScenarioUserType
    name: str
    strategy: Optional[ScenarioUserStrategy]
    can_see_demand: bool
    llm_model: Optional[str] = None
    is_ready: bool = False

    # Function-specific fields (Feb 2026 expansion)
    function: Optional[ScenarioUserFunction] = ScenarioUserFunction.NODE_OPERATOR
    agent_mode: Optional[AgentMode] = AgentMode.MANUAL
    planning_horizon_weeks: Optional[int] = None
    trm_agent_type: Optional[str] = None
    site_key: Optional[str] = None

    class Config:
        from_attributes = True


class ScenarioUser(ScenarioUserResponse):
    """Complete scenario user schema (alias for ScenarioUserResponse)."""
    pass


class ScenarioUserUpdate(BaseModel):
    """Schema for updating scenario user information."""
    strategy: Optional[ScenarioUserStrategy] = None
    can_see_demand: Optional[bool] = None
    llm_model: Optional[str] = None
    is_ready: Optional[bool] = None

    # Function-specific fields (Feb 2026 expansion)
    function: Optional[ScenarioUserFunction] = None
    agent_mode: Optional[AgentMode] = None
    planning_horizon_weeks: Optional[int] = None
    trm_agent_type: Optional[str] = None


# ============================================================================
# Function Assignment Schemas (Feb 2026 - expanded role architecture)
# ============================================================================

class FunctionAssignmentBase(BaseModel):
    """Base schema for function assignments."""
    site_key: str = Field(..., description="The supply chain site this function operates on")
    function: ScenarioUserFunction = Field(..., description="The planning or execution function")
    agent_mode: AgentMode = Field(
        default=AgentMode.MANUAL,
        description="Decision mode for this function"
    )
    auto_execute_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence threshold (0-1) for automatic execution in COPILOT/AUTONOMOUS"
    )
    is_active: bool = Field(default=True, description="Whether this function assignment is active")
    planning_horizon_weeks: Optional[int] = Field(
        default=None,
        ge=1,
        le=52,
        description="Override for default function horizon"
    )
    trm_agent_type: Optional[str] = Field(
        default=None,
        description="TRM agent type: atp_executor, po_creation_trm, etc."
    )


class FunctionAssignmentCreate(FunctionAssignmentBase):
    """Schema for creating a new function assignment."""
    scenario_user_id: int = Field(..., description="The scenario user assigned to this function")


class FunctionAssignmentUpdate(BaseModel):
    """Schema for updating a function assignment."""
    agent_mode: Optional[AgentMode] = None
    auto_execute_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None
    planning_horizon_weeks: Optional[int] = Field(default=None, ge=1, le=52)
    trm_agent_type: Optional[str] = None


class FunctionAssignmentResponse(FunctionAssignmentBase):
    """Schema for function assignment response data."""
    id: int
    scenario_id: int
    scenario_user_id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class FunctionAssignmentWithScenarioUser(FunctionAssignmentResponse):
    """Function assignment with nested scenario user info."""
    scenario_user_name: Optional[str] = None
    scenario_user_type: Optional[ScenarioUserType] = None


class SiteFunctionSummary(BaseModel):
    """Summary of all function assignments for a site."""
    site_key: str
    planning_functions: List[FunctionAssignmentResponse] = []
    execution_functions: List[FunctionAssignmentResponse] = []
    unassigned_functions: List[ScenarioUserFunction] = []


# =============================================================================
# Backward Compatibility Aliases (DEPRECATED - will be removed in future)
# =============================================================================

ParticipantFunction = ScenarioUserFunction
ParticipantRole = ScenarioUserRole
ParticipantType = ScenarioUserType
ParticipantStrategy = ScenarioUserStrategy
ParticipantAssignment = ScenarioUserAssignment
ParticipantCreate = ScenarioUserCreate
ParticipantResponse = ScenarioUserResponse
Participant = ScenarioUser
ParticipantUpdate = ScenarioUserUpdate
FunctionAssignmentWithParticipant = FunctionAssignmentWithScenarioUser

__all__ = [
    # Enums
    'FunctionCategory',
    'ScenarioUserFunction',
    'AgentMode',
    'ScenarioUserRole',
    'ScenarioUserType',
    'ScenarioUserStrategy',
    # ScenarioUser schemas
    'ScenarioUserAssignment',
    'ScenarioUserCreate',
    'ScenarioUserResponse',
    'ScenarioUser',
    'ScenarioUserUpdate',
    # Function assignment schemas
    'FunctionAssignmentBase',
    'FunctionAssignmentCreate',
    'FunctionAssignmentUpdate',
    'FunctionAssignmentResponse',
    'FunctionAssignmentWithScenarioUser',
    'SiteFunctionSummary',
    # Backward compatibility aliases
    'ParticipantFunction',
    'ParticipantRole',
    'ParticipantType',
    'ParticipantStrategy',
    'ParticipantAssignment',
    'ParticipantCreate',
    'ParticipantResponse',
    'Participant',
    'ParticipantUpdate',
    'FunctionAssignmentWithParticipant',
]

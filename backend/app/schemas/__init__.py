"""Schemas package with all Pydantic models.

Terminology (Feb 2026):
- Game -> Scenario
- Player -> Participant (in DB/code)
- Player -> User (in UI)
- Round -> Period
"""

from .user import Token, TokenData, User, UserCreate, UserInDB, UserUpdate

# Scenario and Participant schemas
from .scenario import (
    # Core types
    DemandPatternType, DemandPattern, ScenarioStatus,
    RolePricing, PricingConfig, NodePolicy,
    AutonomyLLMToggles, AutonomyLLMConfig,
    # Scenario schemas
    ScenarioBase, ScenarioCreate, ScenarioUpdate, ScenarioInDBBase,
    Scenario, ScenarioInDB, ScenarioState,
    # Period schemas
    ScenarioPeriodBase, ScenarioPeriodCreate, ScenarioPeriod,
    PeriodBase, PeriodCreate, PeriodUpdate, Period,
    ParticipantPeriodBase, ParticipantPeriodCreate, ParticipantPeriod,
    # Participant schemas (re-exported from participant.py)
    ParticipantState, ParticipantRole,
    ParticipantAssignment, ParticipantResponse, ParticipantUpdate,
    Participant, ParticipantCreate,
    # Action schemas
    ParticipantActionBase, ParticipantActionCreate, ParticipantActionUpdate, ParticipantAction,
    # Order schemas
    OrderCreate, OrderResponse,
)

from .participant import (
    ParticipantType, ParticipantStrategy,
    # Function-related schemas (Feb 2026 expansion)
    FunctionCategory, ParticipantFunction, AgentMode,
    FunctionAssignmentBase, FunctionAssignmentCreate, FunctionAssignmentUpdate,
    FunctionAssignmentResponse, FunctionAssignmentWithParticipant, SiteFunctionSummary,
)

from .agent_config import AgentConfig, AgentConfigCreate, AgentConfigUpdate, AgentConfigInDBBase as AgentConfigInDB
from .dashboard import DashboardResponse, ScenarioUserMetrics as ParticipantMetrics, TimeSeriesPoint
from .group import Group, GroupCreate, GroupUpdate
# AWS SC DM compliant schema imports
from .supply_chain_config import (
    SupplyChainConfig,
    SupplyChainConfigCreate,
    SupplyChainConfigUpdate,
    # Products (AWS SC DM)
    Product,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    # Sites (AWS SC DM: DB table = nodes)
    Site,
    SiteCreate,
    SiteUpdate,
    # Transportation Lanes (AWS SC DM)
    TransportationLane,
    TransportationLaneCreate,
    TransportationLaneUpdate,
    # DEPRECATED aliases
    Lane,  # Use TransportationLane
    LaneCreate,  # Use TransportationLaneCreate
    LaneUpdate,  # Use TransportationLaneUpdate
    # Markets
    Market,
    MarketCreate,
    MarketUpdate,
    MarketDemand,
    MarketDemandCreate,
    MarketDemandUpdate,
    # Product-Site configs (AWS SC DM: DB table = item_node_configs)
    ProductSiteConfig,
    ProductSiteConfigCreate,
    ProductSiteConfigUpdate,
)

# SAP Data Import Cadence & Planning Cycle Management (Feb 2026)
from .sync_job import (
    SyncDataTypeEnum, SyncStatusEnum,
    SyncJobConfigCreate, SyncJobConfigUpdate, SyncJobConfigResponse,
    SyncJobExecutionResponse, SyncTableResultResponse,
    SyncJobTriggerRequest, SyncJobTriggerResponse,
    SyncJobListResponse, SyncExecutionListResponse,
    DefaultCadenceResponse, DefaultCadencesResponse,
)
from .workflow import (
    WorkflowStatusEnum, WorkflowStepTypeEnum, WorkflowTriggerTypeEnum,
    WorkflowStepConfigSchema,
    WorkflowTemplateCreate, WorkflowTemplateUpdate, WorkflowTemplateResponse,
    WorkflowExecutionResponse, WorkflowStepExecutionResponse,
    WorkflowTriggerRequest, WorkflowTriggerResponse, WorkflowCancelResponse,
    WorkflowTemplateListResponse, WorkflowExecutionListResponse,
    DefaultWorkflowTemplateResponse, DefaultWorkflowTemplatesResponse,
)
from .planning_cycle import (
    CycleTypeEnum, CycleStatusEnum, SnapshotTypeEnum, SnapshotTierEnum,
    DeltaOperationEnum, DeltaEntityTypeEnum,
    PlanningCycleCreate, PlanningCycleUpdate, PlanningCycleResponse,
    PlanningCycleStatusUpdate, PlanningCycleListResponse,
    PlanningSnapshotCreate, PlanningSnapshotResponse, PlanningSnapshotDetailResponse,
    PlanningSnapshotListResponse, SnapshotDeltaResponse,
    SnapshotComparisonRequest, SnapshotComparisonResponse,
    SnapshotChainResponse, RetentionStatsResponse,
)
from .planning_decision import (
    DecisionActionEnum, DecisionCategoryEnum, DecisionStatusEnum, DecisionPriorityEnum,
    DECISION_REASON_CODES,
    PlanningDecisionCreate, PlanningDecisionUpdate, PlanningDecisionResponse,
    PlanningDecisionListResponse,
    DecisionHistoryResponse, DecisionHistoryListResponse,
    DecisionCommentCreate, DecisionCommentResponse,
    DecisionApprovalRequest, DecisionRejectRequest, DecisionRevertRequest,
    DecisionStatsResponse, ReasonCodeResponse, ReasonCodesResponse,
    ApprovalThresholdResponse, ApprovalThresholdsResponse,
)

# Re-export all schemas
__all__ = [
    # Auth
    'Token', 'TokenData', 'User', 'UserCreate', 'UserInDB', 'UserUpdate',

    # Core types
    'DemandPatternType', 'DemandPattern', 'ScenarioStatus',
    'RolePricing', 'PricingConfig', 'NodePolicy',
    'AutonomyLLMToggles', 'AutonomyLLMConfig',

    # Scenario schemas
    'ScenarioBase', 'ScenarioCreate', 'ScenarioUpdate', 'ScenarioInDBBase',
    'Scenario', 'ScenarioInDB', 'ScenarioState',

    # Period schemas
    'ScenarioPeriodBase', 'ScenarioPeriodCreate', 'ScenarioPeriod',
    'PeriodBase', 'PeriodCreate', 'PeriodUpdate', 'Period',
    'ParticipantPeriodBase', 'ParticipantPeriodCreate', 'ParticipantPeriod',

    # Participant schemas
    'ParticipantRole', 'ParticipantType', 'ParticipantStrategy',
    'ParticipantAssignment', 'ParticipantCreate', 'ParticipantResponse',
    'Participant', 'ParticipantUpdate', 'ParticipantState',

    # Function assignment schemas (Feb 2026 expansion)
    'FunctionCategory', 'ParticipantFunction', 'AgentMode',
    'FunctionAssignmentBase', 'FunctionAssignmentCreate', 'FunctionAssignmentUpdate',
    'FunctionAssignmentResponse', 'FunctionAssignmentWithParticipant', 'SiteFunctionSummary',

    # Action schemas
    'ParticipantActionBase', 'ParticipantActionCreate', 'ParticipantActionUpdate', 'ParticipantAction',

    # Order schemas
    'OrderCreate', 'OrderResponse',

    # Agent Config
    'AgentConfig', 'AgentConfigCreate', 'AgentConfigUpdate', 'AgentConfigInDB',

    # Dashboard
    'DashboardResponse', 'ParticipantMetrics', 'TimeSeriesPoint',

    # Group
    'Group', 'GroupCreate', 'GroupUpdate',

    # Supply chain config (AWS SC DM terminology)
    'SupplyChainConfig', 'SupplyChainConfigCreate', 'SupplyChainConfigUpdate',
    'Product', 'ProductCreate', 'ProductUpdate', 'ProductResponse',
    'Site', 'SiteCreate', 'SiteUpdate',
    'TransportationLane', 'TransportationLaneCreate', 'TransportationLaneUpdate',
    'Lane', 'LaneCreate', 'LaneUpdate',  # DEPRECATED
    'Market', 'MarketCreate', 'MarketUpdate',
    'MarketDemand', 'MarketDemandCreate', 'MarketDemandUpdate',
    'ProductSiteConfig', 'ProductSiteConfigCreate', 'ProductSiteConfigUpdate',

    # Sync Jobs
    'SyncDataTypeEnum', 'SyncStatusEnum',
    'SyncJobConfigCreate', 'SyncJobConfigUpdate', 'SyncJobConfigResponse',
    'SyncJobExecutionResponse', 'SyncTableResultResponse',
    'SyncJobTriggerRequest', 'SyncJobTriggerResponse',
    'SyncJobListResponse', 'SyncExecutionListResponse',
    'DefaultCadenceResponse', 'DefaultCadencesResponse',

    # Workflows
    'WorkflowStatusEnum', 'WorkflowStepTypeEnum', 'WorkflowTriggerTypeEnum',
    'WorkflowStepConfigSchema',
    'WorkflowTemplateCreate', 'WorkflowTemplateUpdate', 'WorkflowTemplateResponse',
    'WorkflowExecutionResponse', 'WorkflowStepExecutionResponse',
    'WorkflowTriggerRequest', 'WorkflowTriggerResponse', 'WorkflowCancelResponse',
    'WorkflowTemplateListResponse', 'WorkflowExecutionListResponse',
    'DefaultWorkflowTemplateResponse', 'DefaultWorkflowTemplatesResponse',

    # Planning Cycles
    'CycleTypeEnum', 'CycleStatusEnum', 'SnapshotTypeEnum', 'SnapshotTierEnum',
    'DeltaOperationEnum', 'DeltaEntityTypeEnum',
    'PlanningCycleCreate', 'PlanningCycleUpdate', 'PlanningCycleResponse',
    'PlanningCycleStatusUpdate', 'PlanningCycleListResponse',
    'PlanningSnapshotCreate', 'PlanningSnapshotResponse', 'PlanningSnapshotDetailResponse',
    'PlanningSnapshotListResponse', 'SnapshotDeltaResponse',
    'SnapshotComparisonRequest', 'SnapshotComparisonResponse',
    'SnapshotChainResponse', 'RetentionStatsResponse',

    # Planning Decisions
    'DecisionActionEnum', 'DecisionCategoryEnum', 'DecisionStatusEnum', 'DecisionPriorityEnum',
    'DECISION_REASON_CODES',
    'PlanningDecisionCreate', 'PlanningDecisionUpdate', 'PlanningDecisionResponse',
    'PlanningDecisionListResponse',
    'DecisionHistoryResponse', 'DecisionHistoryListResponse',
    'DecisionCommentCreate', 'DecisionCommentResponse',
    'DecisionApprovalRequest', 'DecisionRejectRequest', 'DecisionRevertRequest',
    'DecisionStatsResponse', 'ReasonCodeResponse', 'ReasonCodesResponse',
    'ApprovalThresholdResponse', 'ApprovalThresholdsResponse',
]

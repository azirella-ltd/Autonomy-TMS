"""Models package with all SQLAlchemy models.

Terminology (Feb 2026):
- Game -> Scenario
- Alternative -> Scenario (intermediate step now complete)
- Player -> ScenarioUser (in DB/code), User (in UI)
- Gamification -> Simulation
"""
import logging
from typing import List, Type, Any

# Configure logger
logger = logging.getLogger(__name__)

# Import base first - this will also import all models
from .base import Base

# Import all models here to ensure they are registered with SQLAlchemy
from sqlalchemy import inspect

# Expose relationship setup helpers for legacy import paths
from . import relationships  # noqa: F401

# Import models in dependency order to avoid circular imports
# 1. RBAC models first (User depends on these)
from .rbac import Permission, Role, user_roles, role_permissions, RolePermissionGrant, UserRoleAssignment

# 1b. Risk models (User depends on these)
from .risk import RiskAlert, Watchlist

# 2. Core models with no dependencies
from .user import RefreshToken  # Must be imported before User to avoid circular import
from .user import User, user_scenarios
from .tenant import Tenant, TenantMode, ClockMode

# 3. Models that depend on User
from .participant import (
    ScenarioUser, ScenarioUserRole, ScenarioUserType, ScenarioUserStrategy, AgentMode,
    FunctionCategory, ScenarioUserFunction,
)

# 3b. Function Assignments (Feb 2026 - expanded role architecture)
from .function_assignment import FunctionAssignment

# 3. Scenario-related models
from .supervisor_action import SupervisorAction
from .scenario import Scenario, ScenarioStatus, Round, ScenarioUserAction
from .agent_config import AgentConfig
from .auth_models import PasswordHistory, PasswordResetToken
from .session import TokenBlacklist, UserSession
# Supply chain models
from .supply_chain import (
    ScenarioUserInventory, Order, ScenarioRound, ScenarioUserPeriod, RoundPhase, UpstreamOrderType,
)
from .round_metric import RoundMetric
from app.core.time_buckets import TimeBucket

# 4. Supply chain configuration models (must be imported before MonteCarloRun)
# Temporary compatibility shims during migration
from .compatibility import Item, ItemNodeConfig, ProductSiteConfig
from .supply_chain_config import (
    NodeType,
    SupplyChainConfig,
    # AWS SC DM compliant names
    Site,
    TransportationLane,
    # Backward compatibility aliases (DEPRECATED)
    Node,  # DEPRECATED: Use Site
    Lane,  # DEPRECATED: Use TransportationLane
    Market,
    MarketDemand,
    SupplyChainTrainingArtifact,
)

# 4b. Monte Carlo Simulation models (depends on SupplyChainConfig)
from .monte_carlo import (
    MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries,
    MonteCarloRiskAlert, SimulationStatus
)

# 4c. Master Production Scheduling models
from .mps import MPSPlan, MPSPlanItem, MPSCapacityCheck, MPSStatus, MPSKeyMaterialRequirement

# 4d. Production Order models (Phase 2)
from .production_order import ProductionOrder, ProductionOrderComponent

# 4d. Capacity Planning models (Phase 2)
from .capacity_plan import (
    CapacityPlan, CapacityResource, CapacityRequirement,
    CapacityPlanStatus, ResourceType
)

# 4e. MRP models (Phase 3)
from .mrp import MRPRun, MRPRequirement, MRPException

# 4e2. Pegging models (Full-Level Pegging & Multi-Stage CTP)
from .pegging import SupplyDemandPegging, AATPConsumptionRecord

# 4f. Purchase Order models (Phase 3)
from .purchase_order import PurchaseOrder, PurchaseOrderLineItem

# 4f2. Goods Receipt models
from .goods_receipt import GoodsReceipt, GoodsReceiptLineItem

# 4f3. Invoice and 3-Way Matching models
from .invoice import Invoice, InvoiceLineItem, InvoiceMatchResult

# 4g. Transfer Order models (Phase 3)
from .transfer_order import TransferOrder, TransferOrderLineItem

# 4h. Project Order models (Sprint 6 - Phase 3)
from .project_order import ProjectOrder, ProjectOrderLineItem

# 4i. Maintenance Order models (Sprint 6 - Phase 3)
from .maintenance_order import MaintenanceOrder, MaintenanceOrderSpare

# 4j. Turnaround Order models (Sprint 6 - Phase 3)
from .turnaround_order import TurnaroundOrder, TurnaroundOrderLineItem

# 4k. Quality Order models (Sprint 7 - Powell TRM Framework)
from .quality_order import QualityOrder, QualityOrderLineItem

# 4l. Subcontracting Order models (Sprint 7 - Powell TRM Framework)
from .subcontracting_order import SubcontractingOrder, SubcontractingOrderLineItem

# 4e. SC Entities (Phase 2) - SC Canonical Models
# Import Product and other SC entities
from .sc_entities import TradingPartner, Product, ProductBom

# 4e. Supplier models (Phase 2) - SC Compliant
# VendorProduct must be imported after TradingPartner to resolve relationships
from .supplier import (
    VendorProduct, VendorLeadTime, SupplierPerformance
)

# 4f. Inventory Projection models (Phase 2) - SC Compliant ATP/CTP
from .inventory_projection import (
    InvProjection, AtpProjection, CtpProjection, OrderPromise
)

# 5. A2A Collaboration models (Phase 7 Sprint 2)
from .chat import ChatMessage, AgentSuggestion, WhatIfAnalysis, MessageType, SenderType

# 6. Simulation/Gamification models (Phase 7 Sprint 5)
from .achievement import (
    Achievement, ScenarioUserStats, ScenarioUserAchievement, Leaderboard,
    LeaderboardEntry, ScenarioUserBadge, AchievementNotification,
)

# 7. Enterprise Features - Option 1
from .sso_provider import SSOProvider, UserSSOMapping
# RBAC models already imported at top
from .audit_log import AuditLog

# 8. Mobile Push Notifications - Option 2
from .notification import PushToken, NotificationPreference, NotificationLog, PlatformType
from app.models.compatibility import Item, ItemNodeConfig, ProductSiteConfig  # Temporary compat

# 9. AWS SC Planning - Recommendations (Sprint 4)
from .recommendations import Recommendation, RecommendationDecision

# 9b. Supply Plan Requests (used by User relationship)
from .supply_plan import (
    SupplyPlanRequest, SupplyPlanResult, SupplyPlanComparison, SupplyPlanExport
)

# 10. Inline Comments for Orders/Plans
from .comment import Comment, CommentMention, CommentAttachment

# 11. Team Messaging for Collaboration
from .team_message import (
    TeamChannel, TeamMessage, TeamMessageMention,
    TeamMessageAttachment, TeamMessageRead, channel_members
)

# 12. Forecast Exception Alerts
from .forecast_exception import (
    ForecastException, ForecastExceptionRule, ForecastExceptionComment,
    ExceptionWorkflowTemplate, ExceptionEscalationLog
)

# 13. Approval Workflow Templates
from .approval_template import (
    ApprovalTemplate, ApprovalRequest, ApprovalAction
)

# 14. Forecast Adjustments
from .forecast_adjustment import (
    ForecastAdjustment, ForecastVersion, BulkAdjustmentTemplate
)

# 14b. Forecast Pipeline Runs (clustering/prediction/metrics)
from .forecast_pipeline import (
    ForecastPipelineConfig,
    ForecastPipelineRun,
    ForecastPipelineCluster,
    ForecastPipelinePrediction,
    ForecastPipelineMetric,
    ForecastPipelineFeatureImportance,
    ForecastPipelinePublishLog,
)

# 15. Consensus Planning
from .consensus_plan import (
    ConsensusPlan, ConsensusPlanVersion, ConsensusPlanVote,
    ConsensusPlanComment, ConsensusPlanStatus
)

# 16. SAP Data Import Cadence System
from .sync_job import (
    SyncJobConfig, SyncJobExecution, SyncTableResult, APSchedulerJob,
    SyncDataType, SyncStatus, DEFAULT_SYNC_CADENCES
)

# 17. Workflow System
from .workflow import (
    WorkflowTemplate, WorkflowExecution, WorkflowStepExecution,
    WorkflowStatus, WorkflowStepType, WorkflowTriggerType,
    DEFAULT_WORKFLOW_TEMPLATES
)

# 18. Planning Cycle & Snapshot Management
from .planning_cycle import (
    PlanningCycle, PlanningSnapshot, SnapshotDelta, SnapshotLineage,
    CycleType, CycleStatus, SnapshotType, SnapshotTier,
    DeltaOperation, DeltaEntityType
)

# 19. Planning Decision Tracking
from .planning_decision import (
    PlanningDecision, DecisionHistory, DecisionComment,
    DecisionAction, DecisionCategory, DecisionStatus, DecisionPriority,
    DECISION_REASON_CODES, DEFAULT_APPROVAL_THRESHOLDS
)

# 20. AIIO Framework - Agent Actions (Insights Landing Page)
from .agent_action import (
    AgentAction, ActionMode, ActionCategory, ExecutionResult
)

# 21. Powell Framework - Sequential Decision Analytics & Modeling
from .powell import (
    PowellBeliefState, PowellPolicyParameters, PowellValueFunction,
    PowellCalibrationLog, ConformalMethod, EntityType, PolicyType
)

# 21c. Powell Allocations (tGNN-generated priority allocations)
from .powell_allocation import PowellAllocation

# 21d. Powell Execution Decision Records
from .powell_decisions import (
    PowellATPDecision, PowellRebalanceDecision,
    PowellPODecision, PowellOrderException,
    PowellMODecision, PowellTODecision,
    PowellQualityDecision, PowellMaintenanceDecision,
    PowellSubcontractingDecision, PowellForecastAdjustmentDecision,
)

# 21b. Powell Training Configuration and TRM Training Data
from .powell_training_config import (
    PowellTrainingConfig, TRMTrainingConfig, TrainingRun,
    TRMType, TrainingStatus, DEFAULT_TRM_REWARD_WEIGHTS
)
from .trm_training_data import (
    ATPDecisionLog, ATPOutcome,
    RebalancingDecisionLog, RebalancingOutcome,
    PODecisionLog, POOutcome,
    OrderTrackingDecisionLog, OrderTrackingOutcome,
    TRMReplayBuffer, DecisionSource, OutcomeStatus
)

# 22. Condition Monitoring & Scenario Evaluation
from .condition_alert import (
    ConditionAlert, ScenarioEvaluation, SupplyRequest,
    ConditionType as ConditionAlertType, ConditionSeverity as ConditionAlertSeverity,
    ConditionResolution
)

# 23. Planning Cascade (S&OP → MRS → Supply Agent → Allocation Agent)
from .planning_cascade import (
    PolicyEnvelope, SupplyBaselinePack, SupplyCommit, SolverBaselinePack,
    AllocationCommit, FeedBackSignal, AgentDecisionMetrics,
    PolicySource, CandidateMethod, AllocationMethod, CommitStatus,
    IntegrityViolationType, RiskFlagType,
    LayerLicense, LayerName, LayerMode,
)

# 24. Decision Tracking - Agent Performance Metrics for Powell Framework Dashboards
from .decision_tracking import (
    AgentDecision, PerformanceMetric, SOPWorklistItem,
    DecisionType, DecisionStatus as DQSDecisionStatus, DecisionUrgency
)

# 24b. Override Effectiveness — Bayesian Posteriors & Causal Match Pairs
from .override_effectiveness import (
    OverrideEffectivenessPosterior, CausalMatchPair,
)

# 24c. GNN Directive Review — Human Override at Network Level
from .gnn_directive_review import (
    GNNDirectiveReview, PolicyEnvelopeOverride,
)

# 24d. Decision Governance — AIIO Impact-Based Gating & Executive Directives
from .decision_governance import (
    DecisionGovernancePolicy, GuardrailDirective,
)

# 25. Collaboration Scenarios (Agentic Authorization Protocol demo data)
from .collaboration_scenario import CollaborationScenario

# 26. SAP User Import (SC-filtered user provisioning)
from .sap_user_import import SAPUserImportLog, SAPRoleMapping

# 27. Executive Briefing — LLM-Synthesized Strategy Briefings
from .executive_briefing import (
    ExecutiveBriefing, BriefingFollowup, BriefingSchedule,
    BriefingType, BriefingStatus,
)

# Verify all models are properly registered
registered_tables = set(Base.metadata.tables.keys())
# Updated terminology: scenarios, scenario_users, scenario_user_actions
expected_tables = {
    'users', 'refresh_tokens', 'scenario_users', 'password_history',
    'password_reset_tokens', 'token_blacklist', 'user_sessions',
    'scenarios', 'rounds', 'scenario_user_actions', 'user_scenarios', 'tenants'
}

missing_tables = expected_tables - registered_tables
if missing_tables:
    logger.warning(f"Missing tables in metadata: {missing_tables}")

logger.info(f"Registered tables in metadata: {registered_tables}")

# Explicitly import all models to ensure they are registered with SQLAlchemy metadata
# This helps SQLAlchemy discover all models and their relationships
__all__ = [
    'Base',
    'User',
    'Tenant',
    'RefreshToken',
    'NodeType',
    'SupplyChainConfig',
    # 'Item', 'ItemNodeConfig', - REMOVED: use Product, ProductBom instead
    'Product',  # SC compliant product table
    'ProductBom',  # SC compliant BOM table
    # AWS SC DM compliant names
    'Site',
    'TransportationLane',
    # Backward compatibility aliases (DEPRECATED)
    'Node',  # DEPRECATED: Use Site
    'Lane',  # DEPRECATED: Use TransportationLane
    'Market',
    'MarketDemand',
    'SupplyChainTrainingArtifact',
    'MPSPlan',
    'MPSPlanItem',
    'MPSCapacityCheck',
    'MPSStatus',
    'MonteCarloRun',
    'MonteCarloScenario',
    'MonteCarloTimeSeries',
    'MonteCarloRiskAlert',
    'SimulationStatus',
    'ProductionOrder',
    'ProductionOrderComponent',
    'CapacityPlan',
    'CapacityResource',
    'CapacityRequirement',
    'CapacityPlanStatus',
    'ResourceType',
    'MRPRun',
    'MRPRequirement',
    'MRPException',
    'PurchaseOrder',
    'PurchaseOrderLineItem',
    'GoodsReceipt',
    'GoodsReceiptLineItem',
    'Invoice',
    'InvoiceLineItem',
    'InvoiceMatchResult',
    'TransferOrder',
    'TransferOrderLineItem',
    'TradingPartner',
    'VendorProduct',
    'VendorLeadTime',
    'SupplierPerformance',
    # Scenario terminology
    'Scenario',
    'ScenarioStatus',
    'ScenarioRound',
    # ScenarioUser terminology (was Participant)
    'ScenarioUser',
    'ScenarioUserRole',
    'ScenarioUserType',
    'ScenarioUserStrategy',
    'ScenarioUserAction',
    'ScenarioUserInventory',
    'ScenarioUserPeriod',
    'FunctionCategory',
    'ScenarioUserFunction',
    'FunctionAssignment',
    'AgentConfig',
    'PasswordHistory',
    'PasswordResetToken',
    'TokenBlacklist',
    'UserSession',
    'user_scenarios',
    'AgentMode',
    'RoundPhase',
    'UpstreamOrderType',
    'Round',
    'Order',
    'TimeBucket',
    'ChatMessage',
    'AgentSuggestion',
    'WhatIfAnalysis',
    'MessageType',
    'SenderType',
    'Achievement',
    'ScenarioUserStats',
    'ScenarioUserAchievement',
    'ScenarioUserBadge',
    'Leaderboard',
    'LeaderboardEntry',
    'AchievementNotification',
    # Option 1: Enterprise Features
    'Tenant',
    'SSOProvider',
    'UserSSOMapping',
    'Permission',
    'Role',
    'RolePermissionGrant',
    'UserRoleAssignment',
    'AuditLog',
    # Option 2: Mobile Push Notifications
    'PushToken',
    'NotificationPreference',
    'NotificationLog',
    'PlatformType',
    # Sprint 4: Recommendations
    'Recommendation',
    'RecommendationDecision',
    # Inline Comments
    'Comment',
    'CommentMention',
    'CommentAttachment',
    # Team Messaging
    'TeamChannel',
    'TeamMessage',
    'TeamMessageMention',
    'TeamMessageAttachment',
    'TeamMessageRead',
    'channel_members',
    # Forecast Exception Alerts
    'ForecastException',
    'ForecastExceptionRule',
    'ForecastExceptionComment',
    'ExceptionWorkflowTemplate',
    'ExceptionEscalationLog',
    # Approval Workflow Templates
    'ApprovalTemplate',
    'ApprovalRequest',
    'ApprovalAction',
    # Forecast Adjustments
    'ForecastAdjustment',
    'ForecastVersion',
    'BulkAdjustmentTemplate',
    # Consensus Planning
    'ConsensusPlan',
    'ConsensusPlanVersion',
    'ConsensusPlanVote',
    'ConsensusPlanComment',
    'ConsensusPlanStatus',
    # SAP Data Import Cadence
    'SyncJobConfig',
    'SyncJobExecution',
    'SyncTableResult',
    'APSchedulerJob',
    'SyncDataType',
    'SyncStatus',
    'DEFAULT_SYNC_CADENCES',
    # Workflow System
    'WorkflowTemplate',
    'WorkflowExecution',
    'WorkflowStepExecution',
    'WorkflowStatus',
    'WorkflowStepType',
    'WorkflowTriggerType',
    'DEFAULT_WORKFLOW_TEMPLATES',
    # Planning Cycle & Snapshots
    'PlanningCycle',
    'PlanningSnapshot',
    'SnapshotDelta',
    'SnapshotLineage',
    'CycleType',
    'CycleStatus',
    'SnapshotType',
    'SnapshotTier',
    'DeltaOperation',
    'DeltaEntityType',
    # Planning Decisions
    'PlanningDecision',
    'DecisionHistory',
    'DecisionComment',
    'DecisionAction',
    'DecisionCategory',
    'DecisionStatus',
    'DecisionPriority',
    'DECISION_REASON_CODES',
    'DEFAULT_APPROVAL_THRESHOLDS',
    'relationships',
    # AIIO Framework - Agent Actions
    'AgentAction',
    'ActionMode',
    'ActionCategory',
    'ExecutionResult',
    # Powell Framework - Sequential Decision Analytics
    'PowellBeliefState',
    'PowellPolicyParameters',
    'PowellValueFunction',
    'PowellCalibrationLog',
    'ConformalMethod',
    'EntityType',
    'PolicyType',
    # Quality Order models
    'QualityOrder',
    'QualityOrderLineItem',
    # Subcontracting Order models
    'SubcontractingOrder',
    'SubcontractingOrderLineItem',
    # Powell Execution Decision Records (new TRMs)
    'PowellMODecision',
    'PowellTODecision',
    'PowellQualityDecision',
    'PowellMaintenanceDecision',
    'PowellSubcontractingDecision',
    'PowellForecastAdjustmentDecision',
    # Condition Monitoring & Scenario Evaluation
    'ConditionAlert',
    'ScenarioEvaluation',
    'SupplyRequest',
    'ConditionAlertType',
    'ConditionAlertSeverity',
    'ConditionResolution',
    # Planning Cascade (S&OP → MRS → Supply Agent → Allocation Agent)
    'PolicyEnvelope',
    'SupplyBaselinePack',
    'SupplyCommit',
    'SolverBaselinePack',
    'AllocationCommit',
    'FeedBackSignal',
    'AgentDecisionMetrics',
    'PolicySource',
    'CandidateMethod',
    'AllocationMethod',
    'CommitStatus',
    'IntegrityViolationType',
    'RiskFlagType',
    'LayerLicense',
    'LayerName',
    'LayerMode',
    # Decision Tracking - Agent Performance Metrics
    'AgentDecision',
    'PerformanceMetric',
    'SOPWorklistItem',
    'DecisionType',
    'DQSDecisionStatus',
    'DecisionUrgency',
    # SAP User Import
    'SAPUserImportLog',
    'SAPRoleMapping',
    # Override Effectiveness — Bayesian Posteriors
    'OverrideEffectivenessPosterior',
    'CausalMatchPair',
    # GNN Directive Review — Human Override at Network Level
    'GNNDirectiveReview',
    'PolicyEnvelopeOverride',
    # Decision Governance — AIIO Impact-Based Gating & Executive Directives
    'DecisionGovernancePolicy',
    'GuardrailDirective',
    # Executive Briefing — LLM-Synthesized Strategy Briefings
    'ExecutiveBriefing',
    'BriefingFollowup',
    'BriefingSchedule',
    'BriefingType',
    'BriefingStatus',
]

# Note: SQLAlchemy will configure mappers lazily when first used.
# Calling configure_mappers() explicitly here can cause issues with
# back_populates relationships that may not be fully defined yet.

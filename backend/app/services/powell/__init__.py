"""
Powell Sequential Decision Analytics Framework

This package implements Warren B. Powell's Sequential Decision Analytics and Modeling (SDAM)
framework for supply chain optimization. Powell's framework provides a unified theoretical
foundation that encompasses:

- Deterministic optimization (as special case)
- Stochastic simulation (as belief state updating)
- Conformal prediction (as belief state construction)
- AI agents (TRM = VFA, GNN = CFA/VFA, LLM = meta-policy)

Key Concepts:
- State (Sₜ): Physical state + Belief state (uncertainty quantification)
- Decision (xₜ): Order quantities, production schedules
- Exogenous Information (Wₜ₊₁): Demand realizations, lead time outcomes
- Transition Function (Sᴹ): MRP netting, inventory updates
- Objective (F): Cost minimization, service maximization

Four Policy Classes:
- PFA (Policy Function Approximation): Direct S→x mapping (base-stock rules)
- CFA (Cost Function Approximation): Parameterized optimization (inventory policies)
- VFA (Value Function Approximation): Q-learning, TD learning (TRM agent)
- DLA (Direct Lookahead Approximation): Model predictive control (GNN forecasts)

References:
- Powell, W.B. (2022). Sequential Decision Analytics and Modeling. Now Publishers.
- Powell, W.B. (2011). Approximate Dynamic Programming: Solving the Curses of Dimensionality.
"""

from .value_function import (
    PostDecisionState,
    ValueFunctionApproximator,
    TRMValueFunctionWrapper,
)
from .belief_state import (
    ConformalInterval,
    BeliefState,
    AdaptiveConformalPredictor,
    BeliefStateManager,
)
from .rationing import (
    OrderRequest,
    RationingDecision,
    InventoryRationer,
    RationingPolicy,
)
from .policy_optimizer import (
    PolicyParameter,
    OptimizationResult,
    PolicyOptimizer,
    InventoryPolicyOptimizer,
)
from .exception_handler import (
    ExceptionType,
    ExceptionAction,
    MRPException,
    ExceptionHandlerVFA,
)
from .mpc_planner import (
    MPCState,
    MPCForecast,
    MPCDecision,
    MPCSupplyPlanner,
)
from .hierarchical_planner import (
    StrategicBounds,
    TacticalBounds,
    OperationalBounds,
    HierarchicalPlanner,
)
from .stochastic_program import (
    Scenario,
    StochasticSolution,
    TwoStageStochasticProgram,
    compute_expected_value_of_perfect_information,
    compute_value_of_stochastic_solution,
)

# Conformal-Stochastic Integration (Phase 6 - Conformal + SP)
from .conformal_scenario_generator import (
    ConformalScenarioConfig,
    ConformalScenarioGenerator,
    ConformalStochasticProgramBuilder,
)
from .scenario_reduction import (
    ScenarioReductionResult,
    WassersteinScenarioReducer,
    reduce_conformal_scenarios,
    select_representative_scenarios,
    AdaptiveScenarioReducer,
)
from .rolling_horizon_sop import (
    SOPPlanningCycle,
    RollingHorizonSOPConfig,
    RollingHorizonSOP,
)

# Narrow TRM Execution Services (Phase 5 - Refined Architecture)
from .allocation_service import (
    AllocationCadence,
    UnfulfillableOrderAction,
    PriorityAllocation,
    AllocationConfig,
    ConsumptionResult,
    AllocationService,
)
from .atp_executor import (
    ATPRequest,
    ATPResponse,
    ATPState,
    ATPExecutorTRM,
    MultiSiteATPExecutorTRM,
)
from .time_phased_atp import (
    WorkWeekType,
    TimePhasedAllocation,
    TimePhasedATPRequest,
    TimePhasedATPResponse,
    TimePhasedATPConfig,
    TimePhasedATPService,
)
# inventory_rebalancing_trm, order_tracking_trm, po_creation_trm retired
# 2026-04-23 — SCP-fork TRMs, not transport-plane concerns.
# TMS has EquipmentRepositionTRM (repositions empty trailers/containers,
# not SKU inventory) + ShipmentTrackingTRM (in-transit load exceptions,
# not customer-PO exception detection) + FreightProcurementTRM
# (carrier selection, not vendor PO creation) as the transport-plane
# analogs. See MIGRATION_REGISTER 1.13 for the full substrate cleanup.
from .trm_trainer import (
    TrainingMethod,
    TrainingConfig,
    TrainingRecord,
    TrainingResult,
    RewardCalculator,
    TRMTrainer,
)
from .integration_service import (
    IntegrationConfig,
    IntegrationResult,
    PowellIntegrationService,
    get_powell_integration_service,
)
from .monitoring_service import (
    MonitoringConfig,
    MonitoringResult,
    PowellMonitoringService,
    get_powell_monitoring_service,
)

# CDC Monitor (Section 5.9 - Event-Driven Replanning)
from .cdc_monitor import (
    TriggerReason,
    ReplanAction,
    SiteMetrics,
    TriggerEvent,
    CDCConfig,
    CDCMonitor,
)

# InventoryBufferTRM / SafetyStockTRM retired 2026-04-23 — SCP-fork
# TRMs (SKU-level safety-stock sizing). TMS has CapacityBufferTRM
# (lane-level carrier-capacity buffer) as the transport-plane analog.

# Deterministic Engines (Section 5.13)
from .engines import (
    MRPEngine,
    MRPConfig,
    GrossRequirement,
    NetRequirement,
    PlannedOrder,
    AATPEngine,
    AATPConfig as EngineATPConfig,
    ATPAllocation,
    Order as EngineOrder,
    ATPResult as EngineATPResult,
    Priority,
    BufferCalculator,
    BufferConfig,
    SSPolicy,
    SSResult,
    DemandStats,
    PolicyType,
    RebalancingEngine,
    RebalancingConfig,
    SiteState as EngineSiteState,
    LaneConstraints as EngineLaneConstraints,
    TransferRecommendation as EngineTransferRecommendation,
    OrderTrackingEngine,
    OrderTrackingConfig,
    OrderSnapshot,
    ExceptionResult,
)
SafetyStockCalculator = BufferCalculator
SafetyStockConfig = BufferConfig

# SiteAgent Model (Section 5.12 - Shared Encoder + Heads)
from .site_agent_model import (
    SiteAgentModelConfig,
    SharedStateEncoder,
    ATPExceptionHead,
    InventoryPlanningHead,
    POTimingHead,
    SiteAgentModel,
    create_site_agent_model,
)

# SiteAgent Trainer (Section 5.14 - Training Pipeline)
from .site_agent_trainer import (
    TrainingPhase,
    TrainingConfig as SiteAgentTrainingConfig,
    SiteAgentDataset,
    SiteAgentTrainer,
)

# SiteAgent Orchestrator (Section 5.10 - Unified Architecture)
from .site_agent import (
    SiteAgentConfig,
    ATPResponse as SiteATPResponse,
    PORecommendation as SitePORecommendation,
    SiteAgent,
)

# S&OP GraphSAGE Inference (Runtime analysis + embedding cache)
from .sop_inference_service import (
    NetworkAnalysis,
    SOPInferenceService,
)

# Integration Modules (Connecting SiteAgent to existing services)
from .integration import (
    SiteAgentSupplyPlanAdapter,
    SiteAgentATPAdapter,
    SiteAgentStrategy,
    register_site_agent_strategy,
)
from .integration.decision_integration import (
    TRMDecisionRecord,
    SiteAgentDecisionTracker,
)
from .integration.scenario_integration import (
    SiteAgentPolicy,
    create_site_agent_for_scenario,
)


__all__ = [
    # Value Function (Phase 1)
    "PostDecisionState",
    "ValueFunctionApproximator",
    "TRMValueFunctionWrapper",
    # Belief State (Phase 1)
    "ConformalInterval",
    "BeliefState",
    "AdaptiveConformalPredictor",
    "BeliefStateManager",
    # Rationing (Phase 1)
    "OrderRequest",
    "RationingDecision",
    "InventoryRationer",
    "RationingPolicy",
    # Policy Optimizer (Phase 2)
    "PolicyParameter",
    "OptimizationResult",
    "PolicyOptimizer",
    "InventoryPolicyOptimizer",
    # Exception Handler (Phase 2)
    "ExceptionType",
    "ExceptionAction",
    "MRPException",
    "ExceptionHandlerVFA",
    # MPC Planner (Phase 3)
    "MPCState",
    "MPCForecast",
    "MPCDecision",
    "MPCSupplyPlanner",
    # Hierarchical Planner (Phase 3)
    "StrategicBounds",
    "TacticalBounds",
    "OperationalBounds",
    "HierarchicalPlanner",
    # Stochastic Program (Phase 4)
    "Scenario",
    "StochasticSolution",
    "TwoStageStochasticProgram",
    "compute_expected_value_of_perfect_information",
    "compute_value_of_stochastic_solution",
    # Conformal-Stochastic Integration (Phase 6)
    "ConformalScenarioConfig",
    "ConformalScenarioGenerator",
    "ConformalStochasticProgramBuilder",
    "ScenarioReductionResult",
    "WassersteinScenarioReducer",
    "reduce_conformal_scenarios",
    "select_representative_scenarios",
    "AdaptiveScenarioReducer",
    "SOPPlanningCycle",
    "RollingHorizonSOPConfig",
    "RollingHorizonSOP",
    # Allocation Service (Phase 5 - Narrow TRM)
    "AllocationCadence",
    "UnfulfillableOrderAction",
    "PriorityAllocation",
    "AllocationConfig",
    "ConsumptionResult",
    "AllocationService",
    # ATP Executor (Phase 5 - Narrow TRM)
    "ATPRequest",
    "ATPResponse",
    "ATPState",
    "ATPExecutorTRM",
    "MultiSiteATPExecutorTRM",
    # Time-Phased ATP (Phase 5 - Date-aware ATP)
    "WorkWeekType",
    "TimePhasedAllocation",
    "TimePhasedATPRequest",
    "TimePhasedATPResponse",
    "TimePhasedATPConfig",
    "TimePhasedATPService",
    # InventoryRebalancingTRM / OrderTrackingTRM retired 2026-04-23 —
    # SCP-fork TRMs. TMS EquipmentRepositionTRM + ShipmentTrackingTRM
    # are the transport-plane analogs.
    # TRM Trainer (Phase 5 - VFA/RL Training)
    "TrainingMethod",
    "TrainingConfig",
    "TrainingRecord",
    "TrainingResult",
    "RewardCalculator",
    "TRMTrainer",
    # Integration Service (Phase 5 - Orchestration)
    "IntegrationConfig",
    "IntegrationResult",
    "PowellIntegrationService",
    "get_powell_integration_service",
    # Monitoring Service (Phase 5 - Background Checks)
    "MonitoringConfig",
    "MonitoringResult",
    "PowellMonitoringService",
    "get_powell_monitoring_service",
    # CDC Monitor (Section 5.9 - Event-Driven Replanning)
    "TriggerReason",
    "ReplanAction",
    "SiteMetrics",
    "TriggerEvent",
    "CDCConfig",
    "CDCMonitor",
    # InventoryBufferTRM retired 2026-04-23 — SCP-fork TRM.
    # TMS CapacityBufferTRM is the transport-plane analog.
    # Deterministic Engines (Section 5.13)
    "MRPEngine",
    "MRPConfig",
    "GrossRequirement",
    "NetRequirement",
    "PlannedOrder",
    "AATPEngine",
    "EngineATPConfig",
    "ATPAllocation",
    "EngineOrder",
    "EngineATPResult",
    "Priority",
    "BufferCalculator",
    "BufferConfig",
    "SSPolicy",
    "SSResult",
    "DemandStats",
    "PolicyType",
    "RebalancingEngine",
    "RebalancingConfig",
    "EngineSiteState",
    "EngineLaneConstraints",
    "EngineTransferRecommendation",
    "OrderTrackingEngine",
    "OrderTrackingConfig",
    "OrderSnapshot",
    "ExceptionResult",
    # SiteAgent Model (Section 5.12)
    "SiteAgentModelConfig",
    "SharedStateEncoder",
    "ATPExceptionHead",
    "InventoryPlanningHead",
    "POTimingHead",
    "SiteAgentModel",
    "create_site_agent_model",
    # SiteAgent Trainer (Section 5.14)
    "TrainingPhase",
    "SiteAgentTrainingConfig",
    "SiteAgentDataset",
    "SiteAgentTrainer",
    # SiteAgent Orchestrator (Section 5.10)
    "SiteAgentConfig",
    "SiteATPResponse",
    "SitePORecommendation",
    "SiteAgent",
    # S&OP GraphSAGE Inference
    "NetworkAnalysis",
    "SOPInferenceService",
    # Integration Modules
    "SiteAgentSupplyPlanAdapter",
    "SiteAgentATPAdapter",
    "SiteAgentStrategy",
    "register_site_agent_strategy",
    "TRMDecisionRecord",
    "SiteAgentDecisionTracker",
    "SiteAgentPolicy",
    "create_site_agent_for_scenario",
    # Backward-compatible aliases
    "SafetyStockTRM",
    "SafetyStockCalculator",
    "SafetyStockConfig",
    "SSAdjustmentReason",
    "SSState",
    "SSAdjustment",
]

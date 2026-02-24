"""
Deterministic Engines for Supply Chain Execution

These engines contain 100% deterministic code - no neural networks, no randomness.
They implement mathematically defined operations that are provably correct.

TRM heads sit on TOP of these engines to handle exceptions and adjustments.
The engines can run standalone without TRM for graceful degradation.
"""

from .mrp_engine import (
    MRPEngine,
    MRPConfig,
    GrossRequirement,
    NetRequirement,
    PlannedOrder,
)
from .aatp_engine import (
    AATPEngine,
    AATPConfig,
    ATPAllocation,
    Order,
    ATPResult,
    Priority,
)
from .buffer_calculator import (
    BufferCalculator,
    BufferConfig,
    BufferPolicy,
    BufferResult,
    DemandStats,
    PolicyType,
)
from .rebalancing_engine import (
    RebalancingEngine,
    RebalancingConfig,
    SiteState,
    LaneConstraints,
    TransferRecommendation,
)
from .order_tracking_engine import (
    OrderTrackingEngine,
    OrderTrackingConfig,
    OrderSnapshot,
    ExceptionResult,
)
from .mo_execution_engine import (
    MOExecutionEngine,
    MOExecutionConfig,
    MOSnapshot,
    MOExecutionResult,
    MODecisionType,
)
from .to_execution_engine import (
    TOExecutionEngine,
    TOExecutionConfig,
    TOSnapshot,
    TOExecutionResult,
    TODecisionType,
)
from .quality_engine import (
    QualityEngine,
    QualityEngineConfig,
    QualitySnapshot,
    QualityDispositionResult,
    DispositionType,
)
from .maintenance_engine import (
    MaintenanceEngine,
    MaintenanceEngineConfig,
    MaintenanceSnapshot,
    MaintenanceSchedulingResult,
    MaintenanceDecisionType,
)
from .subcontracting_engine import (
    SubcontractingEngine,
    SubcontractingEngineConfig,
    SubcontractSnapshot,
    SubcontractingResult,
    SubcontractDecisionType,
)
from .forecast_adjustment_engine import (
    ForecastAdjustmentEngine,
    ForecastAdjustmentConfig,
    ForecastSignal,
    ForecastAdjustmentResult,
    AdjustmentDirection,
)

__all__ = [
    # MRP
    'MRPEngine',
    'MRPConfig',
    'GrossRequirement',
    'NetRequirement',
    'PlannedOrder',
    # AATP
    'AATPEngine',
    'AATPConfig',
    'ATPAllocation',
    'Order',
    'ATPResult',
    'Priority',
    # Inventory Buffer
    'BufferCalculator',
    'BufferConfig',
    'BufferPolicy',
    'BufferResult',
    'DemandStats',
    'PolicyType',
    'SafetyStockCalculator',
    'SafetyStockConfig',
    'SSPolicy',
    'SSResult',
    # Rebalancing
    'RebalancingEngine',
    'RebalancingConfig',
    'SiteState',
    'LaneConstraints',
    'TransferRecommendation',
    # Order Tracking
    'OrderTrackingEngine',
    'OrderTrackingConfig',
    'OrderSnapshot',
    'ExceptionResult',
    # MO Execution
    'MOExecutionEngine',
    'MOExecutionConfig',
    'MOSnapshot',
    'MOExecutionResult',
    'MODecisionType',
    # TO Execution
    'TOExecutionEngine',
    'TOExecutionConfig',
    'TOSnapshot',
    'TOExecutionResult',
    'TODecisionType',
    # Quality
    'QualityEngine',
    'QualityEngineConfig',
    'QualitySnapshot',
    'QualityDispositionResult',
    'DispositionType',
    # Maintenance
    'MaintenanceEngine',
    'MaintenanceEngineConfig',
    'MaintenanceSnapshot',
    'MaintenanceSchedulingResult',
    'MaintenanceDecisionType',
    # Subcontracting
    'SubcontractingEngine',
    'SubcontractingEngineConfig',
    'SubcontractSnapshot',
    'SubcontractingResult',
    'SubcontractDecisionType',
    # Forecast Adjustment
    'ForecastAdjustmentEngine',
    'ForecastAdjustmentConfig',
    'ForecastSignal',
    'ForecastAdjustmentResult',
    'AdjustmentDirection',
]

# Backward-compatible aliases
SafetyStockCalculator = BufferCalculator
SafetyStockConfig = BufferConfig
SSPolicy = BufferPolicy
SSResult = BufferResult

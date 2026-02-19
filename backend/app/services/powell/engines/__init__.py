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
from .safety_stock_calculator import (
    SafetyStockCalculator,
    SafetyStockConfig,
    SSPolicy,
    SSResult,
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
    # Safety Stock
    'SafetyStockCalculator',
    'SafetyStockConfig',
    'SSPolicy',
    'SSResult',
    'DemandStats',
    'PolicyType',
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
]

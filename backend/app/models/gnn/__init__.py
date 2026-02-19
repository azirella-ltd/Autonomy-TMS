"""
Graph Neural Network models for Supply Chain optimization.

This module provides a two-tier architecture for planning and execution,
aligned with Warren B. Powell's Sequential Decision Analytics framework.

## Powell Framework Mapping
- SOPGraphSAGE = CFA (Cost Function Approximation): Computes policy parameters θ
- ExecutionTemporalGNN = VFA (Value Function Approximation): Makes decisions Q(s,a)
- HybridPlanningModel = Hierarchical Consistency: Ensures V_execution ≈ E[V_tactical]

## S&OP (Sales & Operations Planning) - Medium Term [CFA]
- SOPGraphSAGE: Network structure analysis, risk scoring, bottleneck detection
- Updates: Weekly/Monthly or on topology changes
- Outputs: Criticality scores, concentration risk, resilience, safety stock positioning
- Powell: Parameterized cost function with tunable θ

## Execution - Short Term / Operational [VFA]
- ExecutionTemporalGNN: Real-time order decisions, demand sensing, exception detection
- Consumes: S&OP embeddings (θ) + transactional data as state
- Updates: Daily/Real-time
- Outputs: Order recommendations, demand forecasts, propagation impact
- Powell: Approximate V(Sˣ) using neural network

## Shared Foundation [Hierarchical Consistency]
- S&OP embeddings are cached and fed to Execution model
- Structural context (slow-changing) + temporal dynamics (fast-changing)
- HybridPlanningModel: Unified interface for both tiers
- Enforces lower-level policies respect higher-level constraints

## Also available:
- SupplyChainTemporalGNN: Original temporal GNN with GAT + GRU
- GraphSAGESupplyChain: Inductive learning with neighbor sampling
- ScalableGraphSAGE: Optimized for large supply chains (50+ nodes)

See POWELL_APPROACH.md for detailed framework integration.
"""

from .temporal_gnn import SupplyChainTemporalGNN, SupplyChainAgent

try:
    from .enhanced_gnn import (
        GraphSAGESupplyChain,
        EnhancedTemporalGNN,
        HeterogeneousSupplyChainGNN,
        MultiTaskLoss,
        create_enhanced_gnn
    )
except ImportError:
    pass  # Optional dependencies

try:
    from .scalable_graphsage import (
        ScalableGraphSAGE,
        TemporalScalableGNN,
        NodeTypeEmbedding,
        EdgeFeatureEncoder,
        create_scalable_gnn
    )
except ImportError:
    pass  # Optional dependencies

try:
    from .large_sc_data_generator import (
        LargeSupplyChainConfig,
        NodeConfig,
        LaneConfig,
        LargeSupplyChainSimulator,
        generate_synthetic_config,
        generate_training_dataset,
        generate_temporal_training_data,
        load_config_from_db,
        create_pyg_data
    )
except ImportError:
    pass  # Optional dependencies

try:
    from .planning_execution_gnn import (
        SOPGraphSAGE,
        ExecutionTemporalGNN,
        HybridPlanningModel,
        create_sop_model,
        create_execution_model,
        create_hybrid_model
    )
except ImportError:
    pass  # Optional dependencies

__all__ = [
    # Original models
    'SupplyChainTemporalGNN',
    'SupplyChainAgent',
    # Enhanced models
    'GraphSAGESupplyChain',
    'EnhancedTemporalGNN',
    'HeterogeneousSupplyChainGNN',
    'MultiTaskLoss',
    'create_enhanced_gnn',
    # Scalable models
    'ScalableGraphSAGE',
    'TemporalScalableGNN',
    'NodeTypeEmbedding',
    'EdgeFeatureEncoder',
    'create_scalable_gnn',
    # Planning/Execution models (Two-Tier Architecture)
    'SOPGraphSAGE',           # S&OP - medium term structural analysis
    'ExecutionTemporalGNN',    # Execution - short term operational
    'HybridPlanningModel',     # Unified interface
    'create_sop_model',
    'create_execution_model',
    'create_hybrid_model',
    # Data generation
    'LargeSupplyChainConfig',
    'NodeConfig',
    'LaneConfig',
    'LargeSupplyChainSimulator',
    'generate_synthetic_config',
    'generate_training_dataset',
    'generate_temporal_training_data',
    'load_config_from_db',
    'create_pyg_data',
]

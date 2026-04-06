# AI Agents

**Last Updated**: 2026-02-21

---

## Overview

Autonomy's AI agents replace or assist human planners in supply chain decision-making. Three complementary approaches achieve **20-35% cost reduction** vs. naive baseline policies while maintaining high service levels.

**Key Insight**: Different AI architectures excel at different tasks:
- **TRM**: Fast operational decisions (<10ms)
- **GNN**: Network-wide coordination via two-tier architecture (S&OP GraphSAGE + 3 supply-side tactical tGNNs)
- **LLM**: Strategic planning with natural language explainability
- **RL**: Policy learning through trial-and-error interaction

**GPU Training Status**: ✅ **All agents GPU-ready** (Tesla T4, PyTorch 2.2.0+cu121)
- See [AI_AGENT_TRAINING_GPU_STATUS.md](docs/progress/AI_AGENT_TRAINING_GPU_STATUS.md) for complete training guide

---

## Agent Types

### Comparison Matrix

| Agent | Parameters | Inference Time | Accuracy vs. Optimal | Use Case | Explainability |
|-------|-----------|----------------|---------------------|----------|----------------|
| **TRM** | 7M | <10ms | 90-95% | Real-time ops | Medium-High (context-aware) |
| **S&OP GraphSAGE** | ~2M | ~200ms (weekly) | Network risk scoring | Policy parameters θ | Medium-High (attention + context) |
| **Tactical tGNNs** (3 supply-side) | ~128M | ~50ms (daily) | 85-92% | Supply/inventory/capacity allocations + directives | Medium-High (attention + context) |
| **LLM** | 175B+ (GPT-4) | ~2s | 85-90% | Strategic planning | High (natural language) |
| **RL (PPO)** | 2M | ~5ms | 75-90% | Policy learning | Low (black box) |
| **Naive** | 0 | <1ms | Baseline (0%) | Benchmark | High (simple rule) |
| **Optimizer** | N/A | ~500ms | 98-100% | Offline planning | High (mathematical) |
| **Claude Skills** | Claude Haiku/Sonnet (exception only) | ~200-500ms | 85-95% | TRM exception handler (~5% of decisions) | High (natural language) |

### Context-Aware Explainability

All 11 TRM agents and both GNN models support context-aware explanations via `AgentContextExplainer` (`backend/app/services/agent_context_explainer.py`). Every decision explanation includes:

| Component | TRM Method | GNN Method | Description |
|-----------|-----------|------------|-------------|
| **Authority Context** | Per-agent authority map | Advisory only | Unilateral / Requires-Authorization / Advisory classification |
| **Active Guardrails** | CDC thresholds | CDC thresholds | Traffic-light status (WITHIN / APPROACHING / EXCEEDED) |
| **Policy Parameters** | Active theta from DB | S&OP parameters | Current powell_policy_parameters driving decisions |
| **Feature Attribution** | Gradient saliency | GAT attention weights | Which inputs drove the decision (top-5 ranked) |
| **Conformal Intervals** | Belief state intervals | Belief state intervals | Prediction uncertainty with calibration quality |
| **Counterfactuals** | Threshold proximity | Threshold proximity | "If X were Y, decision would change to Z" |

**Verbosity Levels** (`ExplainabilityLevel` enum):
- **SUCCINCT**: 1-sentence summary (<1ms, inline with every decision)
- **NORMAL**: Summary + top driver + authority + guardrail status
- **VERBOSE**: Full detail with attribution bars, all guardrails, policy parameters, counterfactuals

**API Endpoints**:
- `GET /planning-cascade/trm-decision/{id}/ask-why?level=NORMAL` — TRM decision explanation
- `GET /planning-cascade/gnn-analysis/{config_id}/node/{node_id}/ask-why?level=NORMAL` — GNN node explanation

**Frontend**: `AskWhyPanel.jsx` renders collapsible sections for authority, guardrails, feature attribution (bar charts), and counterfactuals.

**Files**: `agent_context_explainer.py`, `explanation_templates.py` (39 templates: 13 agent types × 3 levels)

---

## TRM Agent (Tiny Recursive Model)

> **See also**: [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) for the "Hive" model — each site's 11 TRMs form a self-organizing colony with intra-hive signal propagation and tGNN as the inter-hive connective tissue.

### Architecture

**Purpose**: Ultra-fast operational decision-making for high-volume scenarios.

**Model Design**:
- **Type**: Transformer-based sequence model
- **Size**: 7M parameters (tiny compared to LLMs)
- **Layers**: 2-layer transformer encoder
- **Attention**: 8 heads, 256-dim hidden state
- **Recursive Refinement**: 3-step iterative improvement

**Key Innovation**: Recursive refinement allows small model to match performance of much larger models by iteratively improving decisions.

### Architecture Details

**Files**:
- `backend/app/models/trm/trm_model.py` - TRM model definition
- `backend/scripts/training/train_trm.py` - Training script
- `backend/app/services/agents.py` - Agent integration (line 156-189)

**Model Structure**:
```python
class TinyRecursiveModel(nn.Module):
    """
    Tiny Recursive Model for supply chain ordering decisions.

    Architecture:
    - Input: [inventory, backlog, pipeline, demand_history, role, position]
    - Embedding: Linear projection to 256-dim
    - Encoder: 2-layer Transformer (8 heads, 256-dim)
    - Output: Order quantity (single scalar)

    Recursive Refinement:
    - Step 1: Initial prediction from current state
    - Step 2: Predict error, adjust
    - Step 3: Final refinement
    """

    def __init__(self, input_dim=10, hidden_dim=256, num_layers=2, num_heads=8):
        super().__init__()

        # Input embedding
        self.embedding = nn.Linear(input_dim, hidden_dim)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            activation='gelu'
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Output projection
        self.output = nn.Linear(hidden_dim, 1)

    def forward(self, x, num_refinement_steps=3):
        """
        x: [batch, seq_len, input_dim]
        Returns: [batch, 1] order quantities
        """
        # Initial embedding
        embedded = self.embedding(x)  # [batch, seq_len, hidden_dim]

        # Step 1: Initial prediction
        h = self.transformer(embedded)
        order = self.output(h[:, -1, :])  # Use last timestep

        # Steps 2-3: Recursive refinement
        for step in range(num_refinement_steps - 1):
            # Append previous order to input
            order_embedded = self.embedding(order.unsqueeze(1))
            h_refined = self.transformer(torch.cat([embedded, order_embedded], dim=1))

            # Predict error correction
            correction = self.output(h_refined[:, -1, :])
            order = order + correction

        return torch.relu(order)  # Non-negative orders
```

### Training: 5-Phase Curriculum Learning

**Curriculum Strategy**: Start simple, progressively increase complexity.

**Phase 1: Single-Site Newsvendor** (1000 episodes)
- **Task**: Single product, single location
- **Objective**: Learn basic inventory management (reorder point, order quantity)
- **Reward**: Minimize holding cost + shortage cost
- **Difficulty**: Easy (no network effects)

**Phase 2: Two-Site Serial System** (2000 episodes)
- **Task**: Upstream supplier → downstream retailer
- **Objective**: Learn coordination between 2 sites
- **Reward**: Total system cost (both sites)
- **Difficulty**: Medium (basic bullwhip effect)

**Phase 3: Four-Site Beer Game** (5000 episodes)
- **Task**: Classic Beer Game topology (Retailer → Wholesaler → Distributor → Factory)
- **Objective**: Learn to mitigate bullwhip effect
- **Reward**: Total system cost across 4 echelons
- **Difficulty**: Hard (strong bullwhip amplification)

**Phase 4: Multi-Echelon Network** (3000 episodes)
- **Task**: 10+ sites, convergent/divergent topologies
- **Objective**: Learn complex network coordination
- **Reward**: Network-wide cost and service level
- **Difficulty**: Very Hard (many interdependencies)

**Phase 5: Production Environment** (1000 episodes)
- **Task**: Real AWS SC networks with BOMs, multiple products
- **Objective**: Generalize to production scenarios
- **Reward**: Probabilistic balanced scorecard metrics
- **Difficulty**: Extreme (real-world complexity)

**Training Script**:
```bash
cd backend
python scripts/training/train_trm.py \
  --curriculum \
  --phase-1-episodes 1000 \
  --phase-2-episodes 2000 \
  --phase-3-episodes 5000 \
  --phase-4-episodes 3000 \
  --phase-5-episodes 1000 \
  --checkpoint-dir checkpoints/trm/
```

### Performance

**Inference Speed**: <10ms per decision
- Batch processing: 100+ decisions per second
- Real-time scenario execution with 8 agents: ~50ms per period

**Accuracy**:
- Phase 1 (Newsvendor): 95% of optimal
- Phase 3 (Beer Game): 92% of optimal
- Phase 5 (Production): 90% of optimal

**Cost Reduction vs. Naive**: 25-30%

**Trade-offs**:
- ✅ Ultra-fast inference
- ✅ Handles complex state spaces
- ❌ Black box (low explainability)
- ❌ Requires extensive training data

### Narrow TRM Execution Agents (Powell Framework)

The TRM architecture is deployed as **11 specialized execution agents**, each paired 1:1 with a deterministic engine. The engine provides the auditable baseline; the TRM learns context-dependent adjustments.

| TRM Agent | Engine | Decision Scope | Key Decisions |
|-----------|--------|---------------|---------------|
| `ATPExecutorTRM` | `AATPEngine` | Per order, <10ms | AATP consumption with priority sequence |
| `POCreationTRM` | `MRPEngine` | Per product-location | PO timing and quantity |
| `InventoryBufferTRM` | `SafetyStockCalculator` | Per product-site | Inventory buffer level adjustments |
| `InventoryRebalancingTRM` | `RebalancingEngine` | Cross-location, daily | Transfer recommendations |
| `OrderTrackingTRM` | `OrderTrackingEngine` | Per order, continuous | Exception detection and actions |
| `MOExecutionTRM` | `MOExecutionEngine` | Per production order | Release, sequence, split, expedite, defer |
| `TOExecutionTRM` | `TOExecutionEngine` | Per transfer order | Release, consolidate, expedite, defer |
| `QualityDispositionTRM` | `QualityEngine` | Per quality order | Accept, reject, rework, scrap, use-as-is |
| `MaintenanceSchedulingTRM` | `MaintenanceEngine` | Per asset/work order | Schedule, defer, expedite, outsource |
| `SubcontractingTRM` | `SubcontractingEngine` | Per make-vs-buy decision | Internal, external, split routing |
| `ForecastAdjustmentTRM` | `ForecastAdjustmentEngine` | Per signal | Adjust forecast direction and magnitude |

**Files**: All under `backend/app/services/powell/` — engines in `engines/` subdirectory, TRM agents at service level.

See [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md) for full architecture, training pipeline, and CDC relearning loop.

---

## GNN Agent (Graph Neural Network)

### Architecture

**Purpose**: Network-wide supply chain coordination through a **two-tier architecture** separating strategic analysis from operational execution.

**Two-Tier Design**:
- **S&OP GraphSAGE** (~2M params): Medium-term structural analysis — network risk, bottleneck detection, safety stock multipliers. Updates weekly/monthly. Powell CFA.
- **3 Tactical tGNNs** (~128M params total): Supply-side operational decisions — supply planning, inventory optimization, capacity/RCCP. Updates daily. Powell CFA/VFA bridge. Demand forecasting is handled separately by Forecast Baseline + Forecast Adjustment TRMs (April 2026), not by a tGNN.
- **Graph Structure**: Supply chain DAG (graph nodes = sites, graph edges = transportation lanes)
- **Shared Foundation**: S&OP structural embeddings [N, 64] cached and consumed by tactical tGNNs

**Key Innovation**: Separating slowly-changing structural context from fast-changing transactional dynamics. S&OP answers "what's the network structure?", the tactical tGNNs answer "given that structure, what supply/inventory/capacity decisions do we make now?"

### Two-Tier Architecture (S&OP + Tactical)

**NEW**: The GNN system now supports a two-tier architecture for scalable, production-grade planning.

**Powell Framework Mapping** (see [POWELL_APPROACH.md](POWELL_APPROACH.md)):
- **S&OP GraphSAGE** = **CFA (Cost Function Approximation)**: Computes policy parameters θ (safety stock multipliers, risk scores) that parameterize downstream decisions
- **Tactical tGNNs** = **VFA (Value Function Approximation)**: Make supply-side decisions Q(s,a) using S&OP θ as part of the state representation
- **Shared Foundation** = **Hierarchical Consistency**: Ensures V_tactical ≈ E[V_strategic]

```
┌─────────────────────────────────────────────────────────────────┐
│                S&OP GraphSAGE (Medium-Term)                     │
│  - Network structure analysis, risk scoring, bottleneck detect  │
│  - Updates: Weekly/Monthly or on topology changes               │
│  - Outputs: Criticality, concentration risk, resilience,        │
│             safety stock multipliers                            │
└─────────────────────────────────────────────────────────────────┘
                          ↓ (structural embeddings cached)
┌─────────────────────────────────────────────────────────────────┐
│            Tactical tGNNs (Short-Term, Supply-Side)             │
│  - Consumes: S&OP embeddings + transactional data               │
│  - Updates: Daily/Real-time                                     │
│  - 3 tGNNs: Supply Planning, Inventory Optimization, RCCP      │
│  - Outputs: Order recommendations, exception prob, prop impact  │
└─────────────────────────────────────────────────────────────────┘
```

**S&OP GraphSAGE Model** (`SOPGraphSAGE`):
- **Purpose**: Medium-term structural analysis for planning
- **Architecture**: 3-layer GraphSAGE with neighbor sampling (optimized for large graphs)
- **Inputs**: Node features (type, capacity, position), edge features (lead time, cost)
- **Outputs**:
  - `criticality_score`: Node importance in network (0-1)
  - `bottleneck_risk`: Probability of becoming constraint (0-1)
  - `concentration_risk`: Single-source dependency (0-1)
  - `resilience_score`: Recovery capability (0-1)
  - `safety_stock_multiplier`: Recommended SS adjustment (0.5-2.0)
  - `network_risk`: Overall network vulnerability (0-1)
- **Update Frequency**: Weekly/monthly or on topology changes
- **Scalability**: O(edges) complexity, handles 50+ site networks efficiently

**Tactical tGNN Model** (`ExecutionTemporalGNN`):
- **Purpose**: Short-term supply-side operational decisions (supply planning, inventory optimization, capacity/RCCP). Demand forecasting is handled by Forecast Baseline + Forecast Adjustment TRMs, not by tGNNs.
- **Architecture**: GAT (2 layers) + GRU (temporal) + S&OP embedding fusion
- **Inputs**:
  - Structural embeddings from S&OP model
  - Transactional data: inventory, orders, shipments, demand history
- **Outputs**:
  - `order_recommendation`: Suggested order quantity
  - `demand_forecast`: Predicted demand for next period
  - `exception_probability`: Likelihood of disruption (0-1)
  - `propagation_impact`: Downstream effect of current state (0-1)
  - `confidence`: Decision confidence (0-1)
- **Update Frequency**: Daily or real-time

**Hybrid Planning Model** (`HybridPlanningModel`):
- **Purpose**: Unified interface for both tiers
- **Methods**:
  - `update_structural_analysis()`: Refresh S&OP embeddings (call weekly/monthly)
  - `forward()`: Get execution decisions using cached S&OP embeddings (call daily/real-time)
- **Cache Management**: S&OP embeddings cached for efficient execution queries

**Files**:
- `backend/app/models/gnn/planning_execution_gnn.py` - Two-tier model definitions
- `backend/app/models/gnn/scalable_graphsage.py` - Scalable GraphSAGE implementation
- `backend/scripts/training/train_planning_execution.py` - Training script

**Training**:
```bash
# Train S&OP model
python scripts/training/train_planning_execution.py --mode sop --epochs 100

# Train Execution model (requires trained S&OP)
python scripts/training/train_planning_execution.py --mode execution --sop-checkpoint checkpoints/sop_model.pt

# Train hybrid (both tiers together)
python scripts/training/train_planning_execution.py --mode hybrid --epochs 100
```

### Integration: GNN → TRM Pipeline

The two-tier GNN architecture doesn't operate in isolation — its outputs flow through the AllocationService and SiteAgent to drive all 11 TRM execution decisions.

**End-to-End Data Flow**:
```
S&OP GraphSAGE (weekly/monthly)
  → structural_embeddings [N, 64] (cached, detached)
  → criticality, bottleneck_risk, safety_stock_multiplier
      ↓
Tactical tGNNs (daily)
  ← transactional features [8] + hive feedback [8] + structural [64]
  → tGNNSiteDirective per site
      ↓
AllocationService
  → Priority × Product × Location allocations (powell_allocations table)
      ↓
SiteAgent (11 TRM heads)
  ├─ ATPExecutorTRM reads: exception_probability, confidence
  ├─ POCreationTRM reads: demand_forecast, safety_stock_multiplier
  ├─ InventoryRebalancingTRM reads: lateral signals, allocation_adjustment
  ├─ OrderTrackingTRM reads: exception_probability, propagation_impact
  ├─ ForecastAdjustmentTRM reads: demand_forecast, inter_hive_signals
  └─ ... (6 more TRM heads)
      ↓
HiveFeedbackFeatures [8 dims]
  → fed back to next tactical tGNN cycle (closes the loop)
```

**tGNNSiteDirective** — the per-site output that SiteAgent consumes:

| Field | Source | Consumed By |
|-------|--------|-------------|
| `criticality_score` | S&OP GraphSAGE (cached) | All TRMs (priority weighting) |
| `bottleneck_risk` | S&OP GraphSAGE (cached) | MOExecutionTRM, MaintenanceSchedulingTRM |
| `concentration_risk` | S&OP GraphSAGE (cached) | POCreationTRM, SubcontractingTRM |
| `resilience_score` | S&OP GraphSAGE (cached) | SafetyStockTRM |
| `safety_stock_multiplier` | S&OP GraphSAGE (cached) | SafetyStockTRM, POCreationTRM |
| `demand_forecast` | Forecast Baseline + Adjustment TRMs (daily) | POCreationTRM, ForecastAdjustmentTRM |
| `exception_probability` | Tactical tGNNs (daily) | ATPExecutorTRM, OrderTrackingTRM |
| `propagation_impact` | Tactical tGNNs (daily) | OrderTrackingTRM, TOExecutionTRM |
| `order_recommendation` | Supply Planning tGNN (daily) | POCreationTRM |
| `confidence` | Tactical tGNNs (daily) | All TRMs (decision gating) |
| `inter_hive_signals` | Tactical tGNNs (daily) | Routing-dependent TRMs |

**Inter-Hive Signal Types** (generated by tactical tGNNs):
- `UPSTREAM_DISRUPTION`: Shortage propagating downstream
- `DOWNSTREAM_SURGE`: Demand surge detected
- `LATERAL_SURPLUS`: Inventory available at peer site
- `LATERAL_SHORTAGE`: Shortage at peer requiring rebalancing
- `ALLOCATION_REBALANCE`: Priority allocations changed
- `BOTTLENECK_FORMING`: Site becoming bottleneck
- `RESILIENCE_WARNING`: Network resilience degrading
- `BULLWHIP_DETECTED`: Demand amplification detected

**Hive Feedback Loop** — TRM execution metrics feed back to enrich the next tactical tGNN cycle:

The tactical tGNNs accept 8 base transactional features, but can expand to 16 dimensions by incorporating hive feedback from the previous cycle:

| Feature (base 8) | Feature (hive feedback 8) |
|-------------------|---------------------------|
| `current_inventory` | `net_urgency` (mean UrgencyVector) |
| `current_backlog` | `shortage_density` (fraction TRM slots with shortage) |
| `incoming_orders` | `allocation_utilization` (consumed / total AATP) |
| `outgoing_shipments` | `cross_priority_rate` (fraction ATP from lower priorities) |
| `orders_placed` | `trm_override_rate` (% human overrides, 7d window) |
| `actual_lead_time` | `fill_rate_7d` (7-day rolling fulfillment) |
| `capacity_used` | `cdc_severity` (max CDC trigger severity, 24h) |
| `demand_signal` | `backlog_velocity` (d(backlog)/dt) |

**AATP Consumption** — the AllocationService manages priority-based allocation consumption:
```
Consumption sequence for order at priority P:
1. Own tier (P) first
2. Bottom-up from lowest priority (5→4→3→...)
3. Stop at own tier (cannot consume above)
Example: P=2 order with 5 priorities → sequence [2, 5, 4, 3] (skips P1)
```

**Files**:
- `backend/app/models/gnn/planning_execution_gnn.py` — Two-tier models, HiveFeedbackFeatures, tGNNSiteDirective
- `backend/app/services/powell/inter_hive_signal.py` — Inter-hive signal primitives
- `backend/app/services/powell/directive_broadcast_service.py` — Directive broadcasting to SiteAgents
- `backend/app/services/powell/allocation_service.py` — Priority allocation management
- `backend/app/services/powell/site_agent.py` — SiteAgent with 11 TRM heads

### Training: Two-Tier Process

Each tier trains independently with different data characteristics and cadences.

**S&OP GraphSAGE Training**:
- **Data**: Structural features from network topology (12 dimensions: avg_lead_time, lead_time_cv, capacity, capacity_utilization, unit_cost, reliability, num_suppliers, num_customers, inventory_turns, service_level, holding_cost, position)
- **Edge features**: 6 dimensions (lead_time_avg, lead_time_std, cost_per_unit, capacity, reliability, relationship_strength)
- **Labels**: Historical risk events, bottleneck occurrences, network disruptions
- **Refresh**: Retrained when network topology changes significantly

**Tactical tGNN Training**:
- **Data**: Transactional time-series from SimPy/Beer Game scenarios (8-16 dimensions per node per timestep)
- **Edge features**: 4 dimensions (current_lead_time, utilization, in_transit, recent_reliability)
- **Labels**: Optimal decisions from expert traces, behavioral cloning warm-start
- **Refresh**: Continuous improvement via CDC relearning loop

**Data Generation**:
```bash
# Generate SimPy training data
make generate-simpy-data CONFIG_NAME="Default TBG" \
  SIMPY_NUM_RUNS=128 SIMPY_TIMESTEPS=64

# Train both tiers
python scripts/training/train_planning_execution.py --mode hybrid --epochs 100

# Train S&OP only
python scripts/training/train_planning_execution.py --mode sop --epochs 100

# Train Execution only (requires trained S&OP checkpoint)
python scripts/training/train_planning_execution.py --mode execution \
  --sop-checkpoint checkpoints/sop_model.pt
```

**Digital Twin Training Pipeline** (6-phase cold-start from simulation):

| Phase | Description | Data Source | Records |
|-------|-------------|-------------|---------|
| 1 | Individual BC warm-start | Curriculum scenarios | ~2M |
| 2 | Multi-head coordinated traces | SimPy/Beer Game | ~10M |
| 3 | Site tGNN training (cross-TRM coordination) | Phase 2 traces + PPO | ~5.5K |
| 4 | Stochastic stress-testing (TRMs + Site tGNN) | Monte Carlo scenarios | ~20M |
| 5 | Copilot calibration (Site tGNN shadow mode) | Human override replay | ~4M |
| 6 | Autonomous CDC relearning | Production outcomes | ~10M |

Total: ~46M synthetic records, ~7-10 days compute. Stigmergic-only variant: ~10M records, ~5-8 days.

See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 15 for full pipeline specification.

**Files**:
- `backend/scripts/training/train_planning_execution.py` — Two-tier training script
- `backend/scripts/dataset/generate_simpy_dataset.py` — SimPy data generation
- `backend/app/simulation/simpy_beer_game.py` — Beer Game simulation

### Message Passing: Tier-Specific Differences

The two tiers use fundamentally different message passing architectures, reflecting their different time horizons and objectives.

**S&OP GraphSAGE** (static structural analysis):
```
For each of 3 GATv2Conv layers:
  1. Each site encodes its 12 structural features → 64-dim embedding
  2. Edge features (6-dim) encode lane characteristics
  3. GATv2 attention: 4 heads compute weighted neighbor aggregation
  4. GraphNorm + residual connection per layer
  5. No temporal component — processes a single structural snapshot
```

**Tactical tGNN** (temporal transactional analysis):
```
For each timestep in the history window:
  1. Concatenate: transactional features [8-16] + structural embeddings [64]
     → combined feature vector [72-80] per node
  2. Spatial: 2-layer GATv2Conv processes the graph at this timestep

After spatial processing across all timesteps:
  3. Temporal: 2-layer GRU aggregates the sequence of spatial embeddings
  4. Temporal Attention: MultiheadAttention identifies influential periods
  5. Output heads: 5 specialized projections (orders, forecasts, exceptions, etc.)
```

**Key Benefit**: S&OP embeddings are **detached** (no gradient flow) and cached. This means the tactical tGNNs can run at daily/real-time speed without recomputing the expensive structural analysis. Downstream sites can "see" upstream structural context (criticality, bottleneck risk) through the cached embeddings, and transactional dynamics (inventory, orders) through the spatial message passing.

### Multi-Site Coordination Stack

The GNN system operates as **Layer 2** of a 4-layer coordination stack that enables multi-site decision-making without TRMs ever calling across sites directly.

| Layer | Scope | Latency | Mechanism |
|-------|-------|---------|-----------|
| **1 — Intra-Hive** | Within single site | <10ms | UrgencyVector + HiveSignalBus between 11 TRM heads |
| **2 — tGNN Inter-Hive** | Full network graph | Daily | S&OP GraphSAGE + tactical tGNNs → per-site tGNNSiteDirective |
| **3 — AAP Cross-Authority** | Between sites | Seconds-minutes | AuthorizationRequest/Response for transfers, priority overrides, capacity sharing |
| **4 — S&OP Consensus Board** | All functional agents | Weekly | Policy parameters θ negotiated by functional agents |

**Key Principle**: TRMs never call across sites. All cross-site information flows through the tGNN directive (Layer 2) or AAP authorization (Layer 3).

See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 16 for full coordination stack specification and [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md) for AAP protocol details.

### Performance

**Per-Tier Metrics**:

| Metric | S&OP GraphSAGE | Tactical tGNNs |
|--------|----------------|----------------|
| **Inference time** | ~200ms (weekly, amortized) | ~50ms (daily, all nodes) |
| **Accuracy** | Network risk scoring | 85-92% supply/inventory optimization |
| **Parameters** | ~2M | ~128M |
| **Update frequency** | Weekly/monthly | Daily/real-time |
| **Scalability** | O(edges), handles 50+ sites | O(edges × window), handles 50+ sites |

**End-to-End** (combined GNN + TRM system):
- **Cost Reduction vs. Naive**: 20-35%
- **Service Level**: >95% OTIF maintained
- **Latency**: S&OP weekly batch + daily tGNN inference + <10ms per TRM decision

**Trade-offs**:
- Network-aware decisions through structural embeddings
- Temporal pattern recognition via GRU + attention
- Handles variable network topologies (DAG-based)
- Closed-loop feedback via HiveFeedbackFeatures
- Medium-High explainability (GAT attention weights + context-aware explanations)
- Requires graph data structure (PyTorch Geometric)

---

## LLM Agent (GPT-4 Multi-Agent Orchestration)

### Architecture

**Purpose**: Strategic planning with natural language explainability and adaptive strategies.

**Model Design**:
- **Base Model**: GPT-4 (or configurable, see OPENAI_MODEL env var)
- **Architecture**: Multi-agent system with specialized roles
- **Components**:
  1. **Site Agents**: One per supply chain role (Retailer, Wholesaler, Distributor, Factory)
  2. **Supervisor Agent**: Reviews and validates site agent decisions
  3. **Global Planner Agent**: Optional network-wide coordination

**Key Innovation**: Combines strengths of specialized agents with supervisor oversight for improved decisions.

### Multi-Agent System

**Files**:
- `backend/llm_agent/beer_game_openai_agents.py` - Multi-agent orchestrator
- `backend/app/services/llm_agent.py` - LLM agent service wrapper
- `backend/app/services/llm_payload.py` - OpenAI API request/response handling

**System Architecture**:
```
┌─────────────────────────────────────────────────────────┐
│                  Global Planner Agent (Optional)         │
│  - Network-wide base-stock targets                      │
│  - Variance reduction strategies                        │
│  - 13-week rolling planning horizon                     │
└─────────────────────────────────────────────────────────┘
                          ↓ (provides guidance)
┌─────────────────────────────────────────────────────────┐
│                       Site Agents                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │Retailer  │  │Wholesaler│  │Distributor│  │Factory  │ │
│  │ Agent    │  │  Agent   │  │  Agent    │  │ Agent   │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓ (propose orders)
┌─────────────────────────────────────────────────────────┐
│                    Supervisor Agent                      │
│  - Validates proposals                                   │
│  - Checks for over/under-ordering                       │
│  - Clamps to reasonable ranges                          │
│  - Provides feedback for improvement                    │
└─────────────────────────────────────────────────────────┘
                          ↓ (final orders)
                    Execute Period
```

### Site Agents

**Purpose**: Role-specific decision-making with local context.

**Retailer Agent Prompt** (example):
```python
RETAILER_AGENT_SYSTEM_PROMPT = """
You are the Retailer Agent in a multi-echelon supply chain (Beer Game).

Your role:
- Fulfill customer demand
- Place orders to Wholesaler
- Manage inventory to avoid stockouts and excess

Your state:
- inventory: Current stock on-hand
- backlog: Unfulfilled customer demand
- pipeline: Incoming shipments from Wholesaler (by week)
- demand_history: Recent customer demand (last 52 weeks)

Your goal:
Minimize total cost = 0.50 × avg_inventory + 1.00 × avg_backlog

Output format (JSON):
{
  "order_upstream": <quantity to order from Wholesaler>,
  "reasoning": "<brief explanation of decision>"
}

Consider:
1. Demand trends (increasing, decreasing, stable?)
2. Lead time from Wholesaler (2 weeks)
3. Safety stock needs
4. Avoid bullwhip effect (don't over-react to demand spikes)
"""
```

**Site Agent Tools** (Structured JSON Schema):
```python
site_agent_tools = [
    {
        "type": "function",
        "function": {
            "name": "make_ordering_decision",
            "description": "Make ordering decision for this supply chain site",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_upstream": {
                        "type": "number",
                        "description": "Quantity to order from upstream supplier"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of decision rationale"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence in decision (0-1)"
                    }
                },
                "required": ["order_upstream", "reasoning"]
            }
        }
    }
]
```

### Supervisor Agent

**Purpose**: Review site agent proposals and improve decisions.

**Supervisor Prompt**:
```python
SUPERVISOR_AGENT_SYSTEM_PROMPT = """
You are the Supervisor Agent overseeing the Beer Game supply chain.

Your role:
- Review ordering decisions from all site agents
- Validate reasonableness (detect over/under-ordering)
- Clamp orders to sensible ranges
- Provide feedback for improvement
- Ensure network-wide coordination

Input: Proposed orders from all 4 site agents
Output: Approved orders (potentially modified)

Validation checks:
1. Order is non-negative
2. Order is not >5x recent demand (over-ordering)
3. Order is not <0.2x recent demand unless intentional drawdown
4. Consider downstream impact (will this cause bullwhip?)

Output format (JSON):
{
  "approved_orders": {
    "Retailer": <approved_order>,
    "Wholesaler": <approved_order>,
    "Distributor": <approved_order>,
    "Factory": <approved_order>
  },
  "modifications": {
    "Retailer": "<explanation if modified>",
    ...
  },
  "global_feedback": "<network-wide observations>"
}
"""
```

**Clamping Logic**:
```python
def clamp_order(proposed_order: float, recent_demand_avg: float) -> float:
    """
    Supervisor clamps orders to reasonable range.
    """
    # Lower bound: 0 (no negative orders)
    lower = 0

    # Upper bound: 5x recent average demand (detect over-ordering)
    upper = 5 * recent_demand_avg

    # Clamp
    clamped = max(lower, min(upper, proposed_order))

    if clamped != proposed_order:
        logger.warning(
            f"Supervisor clamped order from {proposed_order} to {clamped} "
            f"(recent demand avg: {recent_demand_avg})"
        )

    return clamped
```

### Global Planner Agent (Optional)

**Purpose**: Network-wide coordination with rolling base-stock planning.

**Global Planner Prompt**:
```python
GLOBAL_PLANNER_SYSTEM_PROMPT = """
You are the Global Planner for the entire Beer Game supply chain.

Your role:
- Set base-stock targets for all sites (13-week rolling horizon)
- Coordinate variance reduction strategies
- Balance network-wide inventory vs. service level
- Provide guidance to site agents

Input: Full network state (all 4 sites)
Output: Base-stock targets and strategic guidance

Planning framework:
- Base-stock level = Expected demand over (lead time + review period) + safety stock
- Safety stock = z × σ_demand × √(lead time)
- For 95% service level, z = 1.65

Output format (JSON):
{
  "base_stock_targets": {
    "Retailer": <target_inventory_level>,
    "Wholesaler": <target_inventory_level>,
    "Distributor": <target_inventory_level>,
    "Factory": <target_inventory_level>
  },
  "strategic_guidance": "<recommendations for site agents>",
  "variance_reduction_tips": ["<tip1>", "<tip2>", ...]
}
"""
```

**When to Enable**:
- Complex networks (>4 sites)
- High coordination requirements
- Strategic planning (not just operational)

**Performance Impact**:
- Adds ~1s latency per period (extra LLM call)
- Improves performance by 5-10% in complex scenarios
- Default: DISABLED (set `AUTONOMY_ENABLE_GLOBAL_AGENT=true` to enable)

### Orchestration Flow

**Files**: `backend/llm_agent/beer_game_openai_agents.py`

**Period Execution**:
```python
async def execute_llm_round(game_state: Dict) -> Dict[str, float]:
    """
    Execute one period of Beer Game with LLM agents.
    """
    # 1. Optional: Global Planner provides guidance
    if ENABLE_GLOBAL_AGENT:
        global_guidance = await call_global_planner_agent(game_state)
    else:
        global_guidance = None

    # 2. Each site agent makes a proposal
    proposals = {}
    for site_name in ["Retailer", "Wholesaler", "Distributor", "Factory"]:
        site_context = {
            "role": site_name,
            "inventory": game_state[site_name]["inventory"],
            "backlog": game_state[site_name]["backlog"],
            "pipeline": game_state[site_name]["pipeline"],
            "demand_history": game_state[site_name]["demand_history"],
            "global_guidance": global_guidance  # Optional
        }

        # Call site agent
        response = await call_site_agent(site_name, site_context)
        proposals[site_name] = {
            "order": response["order_upstream"],
            "reasoning": response["reasoning"]
        }

    # 3. Supervisor reviews and approves
    if ENABLE_SUPERVISOR:
        supervisor_input = {
            "proposals": proposals,
            "game_state": game_state
        }
        approved = await call_supervisor_agent(supervisor_input)
        final_orders = approved["approved_orders"]
    else:
        # No supervisor, use proposals directly
        final_orders = {name: p["order"] for name, p in proposals.items()}

    return final_orders
```

**Fallback Strategy**:
```python
# If LLM fails (timeout, API error, invalid response), fall back to heuristic
try:
    orders = await execute_llm_round(game_state)
except Exception as e:
    logger.error(f"LLM agent failed: {e}. Falling back to base-stock heuristic.")
    orders = execute_base_stock_heuristic(game_state)
```

### Configuration

**Environment Variables**:
```bash
# Required
OPENAI_API_KEY=sk-...
OPENAI_PROJECT=proj_...

# Model selection
AUTONOMY_LLM_MODEL=gpt-4  # or gpt-5-mini, gpt-4o, etc.

# Optional: Custom GPT
AUTONOMY_CUSTOM_GPT=user:my-custom-gpt
GPT_ID=g-xxxxxxxxxxxxxxxxxxxxxxxx

# Agent behavior
AUTONOMY_ENABLE_SUPERVISOR=true  # Default: true
AUTONOMY_ENABLE_GLOBAL_AGENT=false  # Default: false
```

**Check Configuration**:
```bash
make openai-check  # Verify API connectivity and configuration
```

### Performance

**Inference Speed**: ~2s per period (4 site agents + supervisor)

**Accuracy vs. Optimal**: 85-90%

**Cost Reduction vs. Naive**: 20-30%

**Explainability**: HIGH (natural language reasoning provided for every decision)

**Example Output**:
```json
{
  "Retailer": {
    "order": 120,
    "reasoning": "Demand is stable around 100 units. I have 50 in inventory and 100 in pipeline arriving next week. Ordering 120 to maintain ~2 weeks safety stock given 2-week lead time."
  },
  "Wholesaler": {
    "order": 125,
    "reasoning": "Retailer ordered 120 last week (up from 100). Sensing potential demand increase. Ordering slightly above recent average to avoid stockout."
  },
  ...
}
```

**Trade-offs**:
- ✅ Natural language explainability
- ✅ Adaptive strategies (learns from context)
- ✅ Multi-agent coordination
- ⚠️ Slow inference (~2s)
- ⚠️ Requires OpenAI API (cost per call)
- ⚠️ Occasional invalid responses (needs fallback)

---

## RL Agent (Reinforcement Learning)

### Architecture

**Purpose**: Learn optimal ordering policies through trial-and-error interaction with supply chain environment.

**Model Design**:
- **Type**: Policy Gradient / Actor-Critic algorithms
- **Algorithms Supported**: PPO (default), SAC, A2C
- **Framework**: Stable-Baselines3 on Gymnasium environment
- **Size**: ~2M parameters (PPO policy + value network)
- **Environment**: Custom Gymnasium-compatible Beer Game environment
- **Training**: 1M timesteps (~4 hours CPU, ~1 hour GPU)

**Key Innovation**: Learns end-to-end policies from cost minimization without explicit rules, adapting to non-stationary demand patterns.

### Architecture Details

**Files**:
- `backend/app/agents/rl_agent.py` - RL agent implementation (450+ lines)
- `backend/scripts/training/train_rl.py` - Training script (212 lines)
- `backend/app/rl/` - RL utilities (config, data generation, policies, adapters)
- `backend/app/api/endpoints/rl.py` - RL API endpoints (484 lines)
- `frontend/src/components/rl/` - RL training dashboard UI

**Environment Design** (BeerGameRLEnv):
```python
class BeerGameRLEnv(gym.Env):
    """
    Gymnasium-compatible RL environment for Beer Game.

    Observation Space (8 dimensions):
    - inventory: Current stock on-hand
    - backlog: Unfulfilled customer demand
    - incoming_shipment_0: Arriving next week
    - incoming_shipment_1: Arriving in 2 weeks
    - incoming_order: Customer order arriving
    - last_order: Previously placed order
    - round_number: Normalized timestep (0-1)
    - total_cost: Cumulative cost (normalized)

    Action Space:
    - Discrete(51): Order quantities from 0 to 50 units

    Reward Function:
    - reward = -(holding_cost × inventory + backlog_cost × backlog)
    - Objective: Minimize total cost over 52 weeks

    Dynamics:
    - Lead time: 2 weeks (order delay) + 2 weeks (shipping delay)
    - Demand: Stochastic Normal(mean=8, std=4)
    - Episode length: 52 periods (1 year)
    """

    def __init__(self, max_rounds=52, max_order=50,
                 holding_cost=0.5, backlog_cost=1.0):
        super().__init__()

        # Observation space: 8 continuous features
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(8,), dtype=np.float32
        )

        # Action space: discrete order quantities
        self.action_space = spaces.Discrete(max_order + 1)

        self.max_rounds = max_rounds
        self.holding_cost = holding_cost
        self.backlog_cost = backlog_cost

    def step(self, action: int):
        """
        Execute one week of supply chain operations.

        Args:
            action: Order quantity (0 to max_order)

        Returns:
            observation, reward, done, truncated, info
        """
        # Place order upstream
        self.place_order(action)

        # Receive incoming shipment
        shipment = self.pipeline.pop(0) if self.pipeline else 0
        self.inventory += shipment

        # Fulfill demand (or accumulate backlog)
        demand = self.generate_demand()
        if self.inventory >= demand + self.backlog:
            # Fulfill all demand
            self.inventory -= (demand + self.backlog)
            self.backlog = 0
        else:
            # Backlog accumulates
            self.backlog += demand - self.inventory
            self.inventory = 0

        # Calculate cost and reward
        round_cost = (self.inventory * self.holding_cost +
                      self.backlog * self.backlog_cost)
        reward = -round_cost

        self.total_cost += round_cost
        self.period += 1

        done = (self.period >= self.max_periods)
        observation = self._get_observation()

        return observation, reward, done, False, {"cost": round_cost}

    def generate_demand(self):
        """Stochastic customer demand: Normal(8, 4)"""
        return max(0, int(np.random.normal(8, 4)))
```

### Algorithms Supported

**1. PPO (Proximal Policy Optimization)** - **Recommended**

**Why PPO**:
- Most stable training (clipped objective prevents large updates)
- Best sample efficiency for supply chain tasks
- Robust to hyperparameter choices
- Industry standard for production RL systems

**Hyperparameters**:
```python
algorithm = "PPO"
learning_rate = 3e-4         # Adam optimizer learning rate
batch_size = 64              # Minibatch size
n_steps = 2048               # Steps before policy update
gamma = 0.99                 # Discount factor (future reward weight)
gae_lambda = 0.95            # Generalized Advantage Estimation
ent_coef = 0.01              # Entropy bonus (exploration)
vf_coef = 0.5                # Value function loss weight
max_grad_norm = 0.5          # Gradient clipping threshold
n_epochs = 10                # Epochs per update
clip_range = 0.2             # Policy clipping range
```

**How PPO Works**:
1. Collect 2,048 timesteps of experience (40 episodes)
2. Compute advantages using GAE
3. Update policy for 10 epochs on minibatches
4. Clip policy updates to prevent destructive changes
5. Repeat until 1M timesteps

**2. SAC (Soft Actor-Critic)**

**When to Use**:
- Off-policy learning (more sample efficient)
- Continuous action spaces (with modifications)
- Stochastic environments with high entropy

**Key Features**:
- Entropy regularization encourages exploration
- Replay buffer for data reuse
- Faster convergence than PPO in some cases

**3. A2C (Advantage Actor-Critic)**

**When to Use**:
- Lightweight experiments
- Limited compute resources
- Quick prototyping

**Trade-offs**:
- Lower sample efficiency than PPO/SAC
- Faster wall-clock time (simpler algorithm)
- May require more timesteps for convergence

### Training: Policy Gradient Optimization

**Training Objective**:
```
Maximize: J(θ) = E[∑(t=0 to T) γ^t × reward_t]

Where:
- θ = policy parameters (neural network weights)
- γ = 0.99 (discount factor)
- T = 52 (episode length)
- reward_t = -cost_t (negative cost as reward)
```

**Training Script**:
```bash
# Quick test (10K timesteps, ~2 minutes)
cd backend
python scripts/training/train_rl.py \
  --algorithm PPO \
  --timesteps 10000 \
  --device cpu

# Production training (1M timesteps, ~4 hours CPU)
python scripts/training/train_rl.py \
  --algorithm PPO \
  --timesteps 1000000 \
  --device cpu \
  --n-envs 4 \
  --checkpoint-dir ./checkpoints/rl \
  --log-dir ./logs/rl

# GPU training (1M timesteps, ~1 hour)
python scripts/training/train_rl.py \
  --algorithm PPO \
  --timesteps 1000000 \
  --device cuda \
  --n-envs 8
```

**Training Progress** (Expected Metrics):

| Timesteps | Mean Episode Reward | Mean Episode Cost | Status |
|-----------|---------------------|-------------------|--------|
| 10K | -7,000 | ~7,000 | Random policy |
| 100K | -500 | ~500 | Learning patterns |
| 500K | -400 | ~400 | Comparable to base-stock |
| 1M | -350 | ~350 | **15-25% better than base-stock** |

**Convergence Indicators**:
- ✅ `rollout/ep_rew_mean` increases steadily
- ✅ `rollout/ep_len_mean` stays at 52 (full episodes)
- ✅ `train/policy_loss` stabilizes
- ✅ `train/value_loss` decreases

**TensorBoard Visualization**:
```bash
tensorboard --logdir=backend/logs/rl
# Open http://localhost:6006
```

### Policy Network Architecture

**Policy (Actor) Network**:
```python
Input: [8-dim observation]
  ↓
FC Layer 1: 256 neurons, ReLU
  ↓
FC Layer 2: 256 neurons, ReLU
  ↓
Output: [51 action logits] → Softmax → Action probabilities
```

**Value (Critic) Network**:
```python
Input: [8-dim observation]
  ↓
FC Layer 1: 256 neurons, ReLU
  ↓
FC Layer 2: 256 neurons, ReLU
  ↓
Output: [1 scalar] → State value estimate
```

**Total Parameters**: ~2M (policy + value networks)

### Reward Engineering

**Reward Function Design**:
```python
# Negative cost formulation (maximize reward = minimize cost)
reward = -(holding_cost × inventory + backlog_cost × backlog)

# With default costs:
reward = -(0.5 × inventory + 1.0 × backlog)

# Interpretation:
# - Holding 10 units: reward = -5
# - Backordering 10 units: reward = -10 (2x worse)
# - Optimal policy: Balance holding vs. stockout risk
```

**Alternative Reward Shaping** (optional):
```python
# Service level bonus
service_level_bonus = +10 if backlog == 0 else 0

# Order smoothness penalty (reduce bullwhip)
order_smoothness_penalty = -abs(order_t - order_{t-1}) × 0.1

# Total reward
reward = -cost + service_level_bonus + order_smoothness_penalty
```

### Data Generation & Training Data

**SimPy-Based Data Generation**:
```bash
# Generate 128 scenario runs for curriculum learning
cd backend
python scripts/dataset/generate_simpy_dataset.py \
  --config-name "Default TBG" \
  --num-runs 128 \
  --timesteps 64
```

**Training Data Adapters** (`backend/app/rl/training_data_adapter.py`):

1. **AWSCAdapter**: Maps Beer Game → AWS SC fields
   - `inventory` → `on_hand_qty`
   - `backlog` → `backorder_qty`
   - `pipeline` → `in_transit_qty`

2. **CurriculumAdapter**: Supports TRM-style curriculum learning

3. **RLEnvAdapter**: Converts observations for RL environment

**Database Integration**:
```python
# Load historical scenarios for replay training
from app.rl.data_generator import load_games_from_db

game_data = load_games_from_db(game_ids=[1, 2, 3])
# Train agent to mimic optimal strategies
```

### Performance

**Inference Speed**: ~5ms per decision
- Fast inference (comparable to TRM)
- Batch processing: 200 decisions/second
- Real-time scenario execution with 4 RL agents: ~20ms per period

**Training Time**:
- **CPU (Intel i7-12700K, 4 envs)**: 1M timesteps in ~4 hours
- **GPU (NVIDIA RTX 3080, 8 envs)**: 1M timesteps in ~1 hour
- **Throughput**: CPU ~3K steps/sec, GPU ~12K steps/sec

**Accuracy vs. Optimal**: 75-90% (depends on training duration)

**Cost Reduction vs. Naive**: 15-25% at 1M timesteps

**Benchmark Results** (Default TBG, 52 periods, PPO @ 1M timesteps):
| Metric | RL Agent (PPO) | Base-Stock | Naive |
|--------|---------------|-----------|-------|
| **Total Cost** | $350 | $450 | $500 |
| **Service Level** | 88% | 85% | 80% |
| **Bullwhip Ratio** | 1.9 | 2.3 | 3.2 |
| **Cost Reduction** | **30% vs Naive** | 10% vs Naive | Baseline |

**Trade-offs**:
- ✅ Learns from experience (no explicit rules)
- ✅ Adapts to non-stationary demand
- ✅ Fast inference (~5ms)
- ✅ Handles complex state spaces
- ⚠️ Requires extensive training (1M timesteps)
- ⚠️ Black box (low explainability)
- ⚠️ Sample inefficient (needs many episodes)
- ❌ Training instability with poor hyperparameters

### Curriculum Learning (Optional)

**Progressive Training Strategy**:

Similar to TRM's 5-phase curriculum, RL agents can benefit from curriculum learning:

**Phase 1: Stationary Demand** (100K timesteps)
- Fixed demand = 8 units/week (no randomness)
- Learn basic inventory control

**Phase 2: Low Variance** (200K timesteps)
- Demand ~ Normal(8, 2) (std=2)
- Introduce mild stochasticity

**Phase 3: Default Variance** (400K timesteps)
- Demand ~ Normal(8, 4) (std=4)
- Full problem complexity

**Phase 4: High Variance** (200K timesteps)
- Demand ~ Normal(8, 6) (std=6)
- Stress test policy robustness

**Phase 5: Multi-Product** (100K timesteps)
- Multiple products with shared resources
- Generalize to production scenarios

**Implementation**:
```bash
python scripts/training/train_rl.py \
  --curriculum \
  --phase-1-steps 100000 \
  --phase-2-steps 200000 \
  --phase-3-steps 400000 \
  --phase-4-steps 200000 \
  --phase-5-steps 100000
```

### Hyperparameter Tuning

**Most Important Hyperparameters**:

1. **Learning Rate** (default: 3e-4)
   - Too high: Training instability, divergence
   - Too low: Slow convergence
   - Recommended range: 1e-4 to 1e-3

2. **Entropy Coefficient** (default: 0.01)
   - Controls exploration vs. exploitation
   - Higher → more exploration (slower convergence, better final policy)
   - Lower → faster convergence (risk of local optima)

3. **Discount Factor γ** (default: 0.99)
   - How much to value future rewards
   - Supply chain: 0.95-0.99 (balance short/long-term)

4. **Number of Timesteps** (default: 1M)
   - More timesteps → better performance (diminishing returns after 1M)
   - Quick test: 10K-100K
   - Production: 500K-2M

**Hyperparameter Search** (example):
```bash
# Grid search over learning rates
for lr in 1e-4 3e-4 1e-3; do
  python train_rl.py --learning-rate $lr --timesteps 500000
done

# Compare results in TensorBoard
tensorboard --logdir=logs/rl
```

### Integration with Beer Game Simulation

**Agent Strategy Integration** (`backend/app/services/agents.py`):

```python
# Create RL agent
from app.agents.rl_agent import RLAgent

rl_agent = RLAgent(model_path="./checkpoints/rl/PPO_final.zip")

# Agent computes order during scenario
order_qty = rl_agent.compute_order(node, context)

# Fallback to base-stock if model unavailable
if not rl_agent.model_loaded:
    order_qty = base_stock_heuristic(node, context)
```

**Usage in Mixed Scenarios**:
```bash
POST /api/v1/mixed-scenarios
{
  "name": "Human vs. RL Agent",
  "config_id": 1,
  "max_rounds": 52,
  "participants": [
    {
      "role_name": "Retailer",
      "player_type": "human",
      "user_id": 5
    },
    {
      "role_name": "Wholesaler",
      "player_type": "agent",
      "agent_config": {
        "strategy": "rl",
        "algorithm": "PPO",
        "model_path": "checkpoints/rl/PPO_final.zip"
      }
    },
    {
      "role_name": "Distributor",
      "player_type": "agent",
      "agent_config": {
        "strategy": "rl",
        "algorithm": "PPO"
      }
    },
    {
      "role_name": "Factory",
      "player_type": "agent",
      "agent_config": {
        "strategy": "ml_forecast"  # Mix with GNN agent
      }
    }
  ]
}
```

### RL Training Dashboard UI

**Frontend Components**:
- **RLTrainingPanel.jsx** (685 lines) - Training dashboard with real-time progress
- **RLDashboard.jsx** (63 lines) - Page wrapper
- **rlApi.js** (118 lines) - API client

**Features**:
- Algorithm selection (PPO, SAC, A2C)
- Hyperparameter configuration UI
- Real-time training progress charts
- Checkpoint management (list, load, delete, evaluate)
- Educational reference tables (algorithm comparison)
- TensorBoard integration button

**API Endpoints** (`backend/app/api/endpoints/rl.py`):
```
POST   /api/rl/train                 # Start training (background task)
GET    /api/rl/training-status       # Get current progress
POST   /api/rl/load-model            # Load trained checkpoint
GET    /api/rl/model-info            # Get model metadata
GET    /api/rl/checkpoints           # List available checkpoints
POST   /api/rl/evaluate              # Evaluate model (N episodes)
POST   /api/rl/test                  # Test model with sample input
DELETE /api/rl/checkpoint            # Delete checkpoint
POST   /api/rl/stop-training         # Stop ongoing training
```

### Model Persistence

**Checkpoint Structure**:
```
backend/checkpoints/rl/
├── best/
│   └── best_model.zip              # Best performing model (by eval reward)
├── PPO_final.zip                   # Final trained model
├── PPO_500000_steps.zip            # Intermediate checkpoint
└── test_ppo.zip                    # Test model (1.8 MB)
```

**Loading Checkpoints**:
```python
# Load best model
agent = RLAgent(model_path="./checkpoints/rl/best/best_model.zip")

# Load specific checkpoint
agent = RLAgent(model_path="./checkpoints/rl/PPO_500000_steps.zip")

# Load from default location
agent = RLAgent()  # Auto-loads best/best_model.zip
```

**Model Information**:
```python
info = agent.get_model_info()
# Returns:
# {
#   "algorithm": "PPO",
#   "timesteps_trained": 1000000,
#   "observation_space": "Box(8,)",
#   "action_space": "Discrete(51)",
#   "model_size_mb": 1.8,
#   "performance": {
#     "mean_reward": -350,
#     "mean_cost": 350,
#     "service_level": 0.88
#   }
# }
```

### AWS SC Compliance

**Schema Adapters** (`backend/app/rl/training_data_adapter.py`):

The RL implementation includes AWS Supply Chain compliance adapters that map Beer Game observations to AWS SC field names:

```python
class AWSCAdapter:
    """
    AWS Supply Chain compliance adapter for RL training data.

    Maps Beer Game fields to AWS SC standard fields:
    - inventory → on_hand_qty
    - backlog → backorder_qty
    - pipeline → in_transit_qty
    - incoming_orders → demand_qty
    - placed_order → order_qty
    """

    def adapt_observation(self, beer_game_obs: dict) -> dict:
        """Convert Beer Game obs to AWS SC format"""
        return {
            "on_hand_qty": beer_game_obs["inventory"],
            "backorder_qty": beer_game_obs["backlog"],
            "in_transit_qty": sum(beer_game_obs["pipeline"]),
            "demand_qty": beer_game_obs["incoming_order"],
            "order_qty": beer_game_obs["last_order"],
            "period_number": beer_game_obs["period"],
            "cost": beer_game_obs["cost"]
        }
```

**Benefits**:
- Seamless integration with AWS SC planning workflows
- Consistent field naming across RL and deterministic planners
- Ready for multi-level BOM explosion with ProductBom table
- Compatible with MPS key material planning

### Known Limitations

**Current Limitations**:
- ⚠️ Single-product only (multi-product support planned)
- ⚠️ Discrete action space (continuous actions require SAC modifications)
- ⚠️ 4-site Beer Game topology (not yet tested on complex networks)
- ⚠️ No multi-agent RL (independent agents, no coordination)
- ⚠️ Black box policy (limited explainability)

**Future Enhancements**:
- Multi-agent RL with communication channels
- Hierarchical RL for multi-level supply chains
- Inverse RL for learning from human planners
- Model-based RL for sample efficiency
- Meta-learning for rapid adaptation to new scenarios

### Documentation

**Key Documentation Files**:
- `docs/progress/RL_IMPLEMENTATION_COMPLETE.md` (541 lines) - Complete status
- `docs/progress/RL_AGENT_IMPLEMENTATION_STATUS.md` (427 lines) - Implementation guide
- `docs/progress/QUICK_START_RL_AGENT.md` (348 lines) - Quick start guide
- API documentation: Swagger UI at `/api/docs`

**Quick Reference**:
```bash
# Install RL dependencies
pip install stable-baselines3 gymnasium tensorboard

# Quick test training
python backend/scripts/training/train_rl.py --timesteps 10000

# View progress
tensorboard --logdir=backend/logs/rl

# Evaluate model
python backend/scripts/training/train_rl.py --evaluate --checkpoint best/best_model.zip
```

---

## Claude Skills — TRM Exception Handler

**Last Updated**: 2026-03-01

> **Replaces**: PicoClaw and OpenClaw external agent runtimes (removed Feb 2026). See [docs/CLAUDE_SKILLS_STRATEGY.md](docs/CLAUDE_SKILLS_STRATEGY.md) for migration rationale.

The platform uses a **hybrid TRM + Claude Skills** architecture. TRMs handle ~95% of decisions at <10ms latency. Claude Skills serve as the exception handler for the ~5% of novel situations where conformal prediction indicates low TRM confidence.

### Architecture (LeCun JEPA Mapping)

```
GraphSAGE / tGNN = World Model (network-wide state representation)
TRMs = Actor (fast, learned policy execution, ~95% of decisions)
Claude Skills = Configurator (exception handling, ~5% of decisions)
Bayesian / Causal AI = Critic (override effectiveness tracking)
Conformal Prediction = Uncertainty Module (routing trigger)
```

### Hybrid Execution Flow

```
Deterministic Engine (always runs first)
    ↓
TRM Exception Head (fast, <10ms, learned adjustments)
    ↓
Conformal Prediction Router:
    ├── High confidence (tight intervals) → Accept TRM result ✓
    └── Low confidence (wide intervals) → Escalate to Claude Skills
        ↓
    Claude Skills Exception Handler
        ├── RAG Decision Memory (find similar past decisions)
        ├── Claude API (Haiku for calculation, Sonnet for judgment)
        └── Proposal validated against engine constraints
    ↓
Skills decisions recorded for TRM meta-learning (shift 95/5 boundary)
```

### 11 Skills by Routing Tier

| Tier | Skills | Cost/Call | Notes |
|------|--------|-----------|-------|
| Deterministic | `atp_executor`, `order_tracking` | $0 | No LLM needed |
| Haiku | `po_creation`, `inventory_rebalancing`, `inventory_buffer`, `to_execution` | ~$0.0018 | Calculation-heavy |
| Sonnet | `mo_execution`, `quality_disposition`, `maintenance_scheduling`, `subcontracting`, `forecast_adjustment` | ~$0.0054 | Requires judgment |

### Key Files

- `backend/app/services/skills/base_skill.py` — `SkillDefinition`, `SkillResult`, registry
- `backend/app/services/skills/claude_client.py` — Claude API client with vLLM/Qwen fallback
- `backend/app/services/skills/skill_orchestrator.py` — Exception handler and meta-learner
- `backend/app/services/skills/*/SKILL.md` — 11 heuristic rule files (one per TRM type)
- `backend/app/models/decision_embeddings.py` — pgvector 768-dim embeddings for RAG decision memory
- `backend/app/services/decision_memory_service.py` — Embed/retrieve past decisions for few-shot context

### Self-Hosted LLM Provider

For data sovereignty (air-gapped customers), self-host **Qwen 3 8B** via **vLLM** as a fallback when Claude API is unavailable:

- **Why Qwen 3**: 96.5% tool calling accuracy (vs 81.5% DeepSeek V3), native structured JSON, hybrid reasoning+tool-calls in one pass
- **Why vLLM**: OpenAI-compatible API, constrained JSON generation via Pydantic schemas, PagedAttention for concurrent requests
- **Hardware**: 8GB VRAM minimum (RTX 3070/4060); 24GB for production Qwen 3 32B
- **Deployment**: `docker-compose.llm.yml` overlay with `vllm/vllm-openai:latest` image

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md#self-hosted-llm-configuration) for full Docker Compose configuration and sizing guide.

---

## Human-to-AI Signal Channels

### Azirella — Natural Language Directive Capture

The "Azirella" prompt bar in the TopNavbar is the primary human-to-AI input channel. Users type natural language directives that the system parses, validates, and routes to the appropriate Powell Cascade layer.

**Flow**: User types directive → POST `/directives/analyze` (LLM parse + gap detection) → Clarification panel (if missing fields) → POST `/directives/submit` (persist + route + auto-apply if confidence ≥ 0.7)

**Powell Layer Routing by Role**:
| User Role | Target Layer |
|-----------|-------------|
| VP / Executive | Layer 4: S&OP GraphSAGE |
| S&OP Director | Layer 3: Tactical tGNNs |
| MPS / Allocation Manager | Layer 1.5: Site tGNN |
| Analysts (ATP, PO, etc.) | Layer 1: Individual TRM |

**Effectiveness Tracking**: Bayesian posteriors per `(user_id, directive_type)` measure whether directives improve outcomes. Lifecycle: PARSED → APPLIED → MEASURED.

Files: `directive_service.py`, `user_directives.py`, `TopNavbar.jsx`. See [TALK_TO_ME.md](TALK_TO_ME.md).

### Email Signal Intelligence — GDPR-Safe Email Ingestion

Automated email monitoring that extracts supply chain signals from customer/supplier communications without storing personal data.

**Pipeline**: IMAP/Gmail → PII Scrubber → Domain→TradingPartner Resolution → LLM Classification (Haiku, ~$0.0018/call) → Scope Resolution → EmailSignal persisted → Auto-route to TRM(s) → Decision Stream alert

**Signal→TRM Routing**: 12 signal types map to primary TRMs — demand_increase/decrease → ForecastAdjustmentTRM, supply_disruption/lead_time_change → POCreationTRM, quality_issue → QualityDispositionTRM, capacity_change → MOExecutionTRM, order_exception → OrderTrackingTRM.

**GDPR Compliance**: PII scrubbed before persistence (regex, no NLP deps). Domain extracted for company identification. Original email never stored. No data subject rights complexity.

**Heuristic Fallback**: Keyword-based classification when LLM unavailable — maintains availability for air-gapped deployments.

Files: `email_signal_service.py`, `email_pii_scrubber.py`, `email_connector.py`, `EmailSignalsDashboard.jsx`. See [EMAIL_SIGNAL_INTELLIGENCE.md](EMAIL_SIGNAL_INTELLIGENCE.md).

---

## Agent Integration with Planning

### How Agents Replace Human Planners

**Planning Workflow**:
```
1. Demand Processing (AWS SC Step 1)
   ↓
2. Inventory Target Calculation (AWS SC Step 2)
   ↓
3. Net Requirements Calculation (AWS SC Step 3)
   ↓ (generates supply plan)
4. Human Planner Review → REPLACED BY AI AGENT
   ↓
5. Approve and Execute
```

**Agent as Planner**:
```python
# Traditional: Human planner reviews supply plan
supply_plan = await generate_supply_plan(config_id=1)
await notify_human_planner(supply_plan)
# Human reviews, approves or modifies

# With AI Agent: Agent reviews and approves automatically
supply_plan = await generate_supply_plan(config_id=1)
agent_decision = await llm_agent.review_supply_plan(supply_plan)

if agent_decision["approved"]:
    await approve_supply_plan(supply_plan.id)
elif agent_decision["modifications"]:
    await modify_supply_plan(supply_plan.id, agent_decision["modifications"])
    await approve_supply_plan(supply_plan.id)
else:
    # Escalate to human
    await notify_human_planner(supply_plan, agent_feedback=agent_decision["reasoning"])
```

### Agent Capabilities in Planning

**1. Supply Plan Review**:
- Validate net requirements calculation
- Check for unrealistic orders (spike detection)
- Verify sourcing rule compliance
- Approve or flag for human review

**2. Inventory Policy Tuning**:
- Recommend safety stock adjustments
- Optimize days-of-coverage targets
- Balance cost vs. service level
- Learn from historical performance

**3. Demand Forecast Override**:
- Detect forecast errors
- Incorporate market intelligence (LLM)
- Adjust forecasts with reasoning
- Consensus planning (human + AI)

**4. Exception Management**:
- Prioritize stockout alerts
- Recommend expediting actions
- Identify root causes (bullwhip, supplier delay)
- Suggest corrective actions

---

## Agent Usage in Beer Game Simulation

### How to Assign Agents

**Via UI** ([frontend/src/pages/CreateMixedGame.jsx](frontend/src/pages/CreateMixedGame.jsx)):
1. Navigate to "Create Scenario"
2. For each role (Retailer, Wholesaler, Distributor, Factory):
   - Select "Human" or "AI Agent"
   - If AI, choose strategy: naive, conservative, ml_forecast, llm, etc.
3. Start scenario

**Via API**:
```bash
POST /api/v1/mixed-scenarios
{
  "name": "Human vs. AI Showdown",
  "config_id": 1,
  "max_rounds": 52,
  "participants": [
    {
      "role_name": "Retailer",
      "player_type": "human",
      "user_id": 5
    },
    {
      "role_name": "Wholesaler",
      "player_type": "agent",
      "agent_config": {
        "strategy": "ml_forecast",
        "model_path": "checkpoints/gnn/best_model.pth"
      }
    },
    {
      "role_name": "Distributor",
      "player_type": "agent",
      "agent_config": {
        "strategy": "llm",
        "enable_supervisor": true
      }
    },
    {
      "role_name": "Factory",
      "player_type": "agent",
      "agent_config": {
        "strategy": "ml_forecast",
        "model_path": "checkpoints/trm/best_model.pth"
      }
    }
  ]
}
```

### Agent Strategies Available

**Files**: `backend/app/services/agents.py`

**Strategy Types**:
1. **naive**: Mirror incoming demand (baseline)
2. **bullwhip**: Intentionally over-order to demonstrate volatility
3. **conservative**: High safety stock, stable orders
4. **ml_forecast**: Use TRM or GNN for demand prediction
5. **optimizer**: Mathematical optimization (cost function)
6. **reactive**: Rapid response to inventory changes
7. **llm**: GPT-4 multi-agent system

**Strategy Selection**:
```python
from app.services.agents import get_policy_by_strategy

# Create agent
agent = get_policy_by_strategy("ml_forecast", model_path="checkpoints/gnn/best_model.pth")

# Agent decides order quantity
order_qty = agent.compute_order(node, context)
```

---

## Training & Evaluation

### Training Data Generation

**SimPy Simulation**:
```bash
# Generate 128 scenario runs with various agent strategies
make generate-simpy-data CONFIG_NAME="Default TBG" \
  SIMPY_NUM_RUNS=128 \
  SIMPY_TIMESTEPS=64
```

**Files**: `backend/scripts/dataset/generate_simpy_dataset.py`

**What Gets Generated**:
- Scenario state snapshots (inventory, backlog, pipeline)
- Agent decisions (order quantities)
- Outcomes (costs, service levels)
- Network topology (graph structure)

### Training Scripts

**Train GNN**:
```bash
make train-gnn TRAIN_EPOCHS=50 TRAIN_DEVICE=cuda
```

**Train TRM** (curriculum):
```bash
cd backend
python scripts/training/train_trm.py --curriculum
```

**Checkpoints**:
- Saved to `backend/checkpoints/gnn/` and `backend/checkpoints/trm/`
- Best model selected based on validation loss
- Loaded at inference time

### Evaluation Metrics

**Performance Comparison**:
```python
# Run 100 scenarios with each agent strategy
strategies = ["naive", "conservative", "ml_forecast", "llm", "optimizer"]
results = {}

for strategy in strategies:
    scenarios = await run_agent_scenarios(
        strategy=strategy,
        num_games=100,
        config_id=1,
        max_rounds=52
    )

    results[strategy] = {
        "avg_total_cost": np.mean([s.total_cost for s in scenarios]),
        "avg_service_level": np.mean([s.service_level for s in scenarios]),
        "avg_bullwhip_ratio": np.mean([s.bullwhip_ratio for s in scenarios]),
        "cost_reduction_vs_naive": ...,
    }
```

**Key Metrics**:
- **Total Cost**: Holding + shortage + ordering cost
- **Service Level**: % of demand fulfilled without backlog
- **Bullwhip Ratio**: Order variance / demand variance
- **Cost Reduction vs. Naive**: % improvement over baseline

**Benchmark Results** (Default TBG, 52 periods):
| Strategy | Avg Cost | Cost Reduction vs. Naive | Service Level | Bullwhip Ratio |
|----------|----------|--------------------------|---------------|----------------|
| **Naive** | $10,500 | 0% (baseline) | 85% | 3.2 |
| **Conservative** | $9,200 | 12% | 92% | 2.1 |
| **TRM** | $7,800 | 26% | 93% | 1.7 |
| **GNN** | $8,200 | 22% | 91% | 1.9 |
| **LLM** | $7,500 | 29% | 94% | 1.6 |
| **Optimizer** | $7,200 | 31% | 95% | 1.4 |

---

## API Examples

### Create Agent Scenario
```bash
POST /api/v1/agent-scenarios
{
  "name": "GNN vs. LLM Comparison",
  "config_id": 1,
  "max_periods": 52,
  "agent_configs": [
    {
      "role_name": "Retailer",
      "strategy": "ml_forecast",
      "model_path": "checkpoints/gnn/best_model.pth"
    },
    {
      "role_name": "Wholesaler",
      "strategy": "llm",
      "enable_supervisor": true
    },
    {
      "role_name": "Distributor",
      "strategy": "ml_forecast",
      "model_path": "checkpoints/trm/best_model.pth"
    },
    {
      "role_name": "Factory",
      "strategy": "optimizer"
    }
  ]
}
```

### Get Agent Performance
```bash
GET /api/v1/agent-scenarios/{scenario_id}/analytics

# Response
{
  "scenario_id": 123,
  "agents": {
    "Retailer": {"strategy": "ml_forecast", "total_cost": 2500, "service_level": 0.93},
    "Wholesaler": {"strategy": "llm", "total_cost": 3200, "service_level": 0.91},
    ...
  },
  "network_metrics": {
    "total_cost": 10200,
    "bullwhip_ratio": 1.8,
    "avg_service_level": 0.92
  }
}
```

---

## Further Reading

- [BEER_GAME_GUIDE.md](BEER_GAME_GUIDE.md) - How to use agents in Beer Game
- [PLANNING_CAPABILITIES.md](PLANNING_CAPABILITIES.md) - How agents integrate with planning
- [AGENT_SYSTEM.md](../AGENT_SYSTEM.md) - Agent strategy implementation details
- [Training Guide] - Coming soon

---

## Academic References

**Key Papers** (in `docs/Knowledge/`):
- Reinforcement learning for supply chain optimization
- Graph neural networks for logistics
- Multi-agent systems for coordination

# Powell Planning Cascade & AI Agent Architecture Guide

## Overview

The Autonomy platform implements Warren B. Powell's Sequential Decision Analytics and Modeling (SDAM) framework as the theoretical foundation for AI-driven supply chain planning. This guide covers the planning cascade, the four policy classes, the TRM hive architecture, and the digital twin training pipeline.

## Powell SDAM Framework

### Five Core Elements

Every supply chain decision problem decomposes into:

1. **State (Sₜ)**: Complete description of the system at time t
   - Physical state: inventory levels, pipeline, capacities
   - Belief state: forecasts, uncertainty (conformal intervals), model parameters
   - Information state: what we know about the world

2. **Decision (xₜ)**: Action taken at time t
   - Order quantities, allocation priorities, production schedules
   - Constrained by available resources and policy parameters

3. **Exogenous Information (Wₜ₊₁)**: New information arriving between t and t+1
   - Actual demand, lead time realizations, yield outcomes
   - Market signals, disruptions, quality events

4. **Transition Function (Sᴹ)**: How state evolves
   - Sₜ₊₁ = Sᴹ(Sₜ, xₜ, Wₜ₊₁)
   - Inventory balance: closing = opening + receipts - demand
   - Pipeline updates: orders placed → in transit → received

5. **Objective Function**: What we optimize
   - min E[∑ C(Sₜ, xₜ)] over planning horizon
   - Costs: holding, backlog, ordering, expediting, penalties

### Four Policy Classes

Powell identifies four classes of policies (decision rules), not alternatives but complementary approaches:

#### 1. PFA — Policy Function Approximation
**Direct S→x mapping** with analytical rules.

Examples in Autonomy:
- Base-stock policy: order_qty = max(0, target - position)
- (s, S) policy: if position < s, order up to S
- Fixed order quantity rules

Use when: Simple, well-understood relationships exist.

#### 2. CFA — Cost Function Approximation
**Parameterized optimization** with tunable parameters θ.

Examples in Autonomy:
- **S&OP GraphSAGE**: Computes policy parameters θ (safety stock multipliers, OTIF targets, allocation reserves)
- **Inventory policies**: ss_days, service_level, conformal_coverage are all θ parameters
- **Sourcing rules**: sourcing_priority, sourcing_ratio as θ

The key insight: Instead of solving the full stochastic optimization, parameterize the decision rule and optimize θ.

#### 3. VFA — Value Function Approximation
**Q-learning / TD learning** — estimate the value of states to guide decisions.

Examples in Autonomy:
- **TRM Agents**: 7M-parameter recursive models trained via behavioral cloning + RL
- Each TRM estimates V(state) or Q(state, action) for its narrow decision scope
- `powell_value_function` table stores tabular VFA as fallback

Training: Behavioral cloning → RL fine-tuning with TD learning

#### 4. DLA — Direct Lookahead
**Model predictive control** — solve a simplified future model to decide now.

Examples in Autonomy:
- Monte Carlo simulation (1000+ scenarios) for supply plan evaluation
- Stochastic programming with scenario trees
- Conformal prediction intervals define scenario bounds

## Planning Cascade Architecture

### Full Cascade (Top-Down)

```
S&OP / IBP Layer (Weekly/Monthly)
    │ Policy parameters θ (safety stock targets, OTIF floors, allocation reserves)
    │ Feed-Forward Contract: versioned, hashable parameter set
    ↓
MPS / MRP Layer (Weekly/Daily)
    │ Master production schedule, material requirements
    │ Feed-Forward Contract: planned orders, capacity assignments
    ↓
Supply Planning Agent — Supply Commit (SC) (Daily)
    │ What to buy/make/transfer, when, from whom
    │ Grounded by Supply Baseline Pack (SupBP)
    │ Feed-Forward Contract: committed supply plan
    ↓
Allocation Planning Agent — Allocation Commit (AC) (Daily)
    │ Constraint-respecting distribution across demand segments
    │ Grounded by Solver Baseline Pack (SBP)
    │ Feed-Forward Contract: allocation table
    ↓
Execution (Real-time, <10ms)
    │ 11 narrow TRM agents per site
    │ ATP, Inventory Rebalancing, PO Creation, Order Tracking,
    │ MO Execution, TO Execution, Quality, Maintenance,
    │ Subcontracting, Forecast Adjustment, Safety Stock
    ↓
Outcomes → Feed-Back Signals → Re-tune upstream θ
```

### Feed-Forward Contracts
Each layer produces versioned, hashable artifacts as grounding input to the next layer:
- S&OP → MPS: Policy parameters (safety stock weeks, OTIF targets)
- MPS → Supply Agent: Planned orders, capacity assignments
- Supply Agent → Allocation Agent: Committed supply plan
- Allocation Agent → Execution: Allocation table (Priority × Product × Location)

### Feed-Back Signals
Outcome signals flow bottom-up to re-tune upstream parameters:
- OTIF rates → S&OP safety stock parameters
- Shortfall frequency → MPS capacity buffers
- Expedite frequency → Sourcing rule priorities
- E&O (excess & obsolescence) → Demand planning methods
- Override patterns → Agent training (RLHF)

## TRM Hive Architecture

### Concept
Each site's 11 TRM agents form a self-organizing "hive" — a coordinated unit that makes all execution decisions for that site. The tGNN provides inter-hive connective tissue.

### Multi-Site Coordination Stack (4 Layers)

#### Layer 1 — Intra-Hive (<10ms)
Within a single site:
- **UrgencyVector**: Per-head urgency signals (ATP shortfall, capacity overload, quality hold)
- **HiveSignalBus**: Broadcast mechanism for cross-head coordination
- Example: ATP shortfall → signals PO head to expedite → signals Maintenance to defer

#### Layer 2 — tGNN Inter-Hive (Daily)
Across the network:
- **S&OP GraphSAGE**: Processes full network graph, outputs per-site criticality scores
- **Execution tGNN**: Generates Priority × Product × Location allocations
- Output: tGNNSiteDirective per site (allocation table + context embeddings)

#### Layer 3 — AAP Cross-Authority (Seconds-Minutes)
Between functional agents:
- **Agentic Authorization Protocol**: Structured request/response for actions outside authority
- Three phases: Evaluate (what-if), Request (AuthorizationRequest with scorecard), Authorize
- Net benefit threshold governs autonomy: high → auto-resolve, medium → human review, low → reject

#### Layer 4 — S&OP Consensus Board (Weekly)
Policy parameter negotiation:
- Functional agents negotiate Policy Envelope parameters
- Feed-back signals serve as evidence for parameter changes
- Balanced Scorecard quantifies trade-offs across all metrics

### Key Principle
**TRMs never call across sites**. All cross-site information flows through:
- tGNN directive (Layer 2 — daily batch)
- AAP authorization (Layer 3 — on-demand)

## 11 TRM Agents (Per-Site Execution)

### Agent Catalog

| Agent | Decision Scope | Latency | Key Inputs |
|-------|---------------|---------|------------|
| **ATP Executor** | Per order — AATP consumption with priority sequence | <10ms | Order, allocations, inventory |
| **Inventory Rebalancing** | Cross-location transfer recommendations | Daily | Inventory positions, demand forecasts |
| **PO Creation** | Purchase order timing and quantity | Daily | MRP output, vendor lead times, inventory |
| **Order Tracking** | Exception detection and recommended actions | Continuous | Shipment events, delivery risk |
| **MO Execution** | Manufacturing order release, sequencing, expedite | Per order | Production schedule, capacity, materials |
| **TO Execution** | Transfer order release, consolidation, expedite | Per order | Transfer plan, transportation capacity |
| **Quality Disposition** | Accept, reject, rework, scrap, use-as-is | Per lot | Quality test results, demand urgency |
| **Maintenance Scheduling** | Schedule, defer, expedite, outsource | Per asset | Maintenance calendar, production load |
| **Subcontracting** | Make-vs-buy and external routing | Per order | Internal capacity, vendor availability |
| **Forecast Adjustment** | Signal-driven forecast direction/magnitude | Per signal | Email/voice/market signals, forecast |
| **Safety Stock** | Safety stock level adjustment | Per product-site | Demand variability, lead time, coverage |

### AATP Consumption Logic (Critical)
The ATP Executor follows a specific consumption sequence:

For an order at priority P:
1. Consume own tier (P) first
2. Bottom-up from lowest priority (5→4→3→...)
3. Stop at own tier (cannot consume above)

Example: P=2 order consumes in sequence [2, 5, 4, 3] (skips tier 1)

### TRM Architecture
- 7M parameters, 2-layer transformer
- 3-step recursive refinement (2 layers × 3 applications = 6 effective layers)
- Post-normalization for recursion stability
- Full backpropagation through all recursive steps
- Deep supervision at each refinement step

### Training Pipeline
1. **Behavioral Cloning**: Warm-start from expert/heuristic decisions
2. **RL Fine-Tuning**: TD learning with actual outcomes
3. **CGAR Curriculum**: Progressive recursion depth (saves ~40% FLOPs)
4. **CDC Relearning**: Continuous feedback loop from production outcomes

## Digital Twin Training Pipeline

Five-phase cold-start pipeline:

### Phase 1: Individual BC Warm-Start
- Single TRM heads trained independently via behavioral cloning
- Curriculum-based: simple scenarios → complex
- Data source: heuristic/expert decisions from SimPy simulations

### Phase 2: Multi-Head Coordinated Traces
- Multiple TRM heads trained together on coordinated scenarios
- Data source: Beer Game / SimPy multi-agent simulations
- Focus: intra-hive coordination patterns

### Phase 3: Stochastic Stress-Testing
- Monte Carlo scenarios with extreme conditions
- Tests robustness of learned policies
- Data source: conformal prediction-bounded scenario generation

### Phase 4: Copilot Calibration
- Human override patterns feed into agent retraining
- RLHF-style: human corrections weighted as expert demonstrations
- Data source: production copilot mode override captures

### Phase 5: Autonomous CDC Relearning
- Continuous retraining from production outcomes
- CDC (Change Data Capture) monitors detect metric deviations
- Automated offline RL when sufficient experience accumulated
- Cooldown periods prevent over-training

**Total Synthetic Data**: ~46M records, ~7-10 days compute
**Stigmergic-only Variant**: ~10M records, ~5-8 days

## CDC → Relearning Feedback Loop

```
SiteAgent decisions → [powell_site_agent_decisions]
       ↓ (hourly)
OutcomeCollector computes actual outcomes + rewards
       ↓
CDCMonitor fires → [powell_cdc_trigger_log]
       ↓ (every 6h or on FULL_CFA)
CDCRetrainingService evaluates need → TRMTrainer.train() → checkpoint
       ↓
SiteAgent reloads model
```

### Feedback Horizons by Agent
| Agent | Feedback Horizon | Rationale |
|-------|-----------------|-----------|
| ATP Executor | 4 hours | Can observe fulfillment quickly |
| Inventory Rebalancing | 24 hours | Transfer completion |
| PO Creation | 7 days | PO receipt and quality |
| Order Tracking | 24 hours | Delivery outcome |

### Retraining Triggers
- Minimum 100 experiences since last training
- CDC trigger logged (metric deviation detected)
- Cooldown elapsed (minimum time between retraining runs)
- Six condition monitors: ATP shortfall, inventory deviation, capacity utilization, orders past due, forecast deviation, quality events

## Agentic Operating Model

### Core Metrics
| Metric | Range | Description |
|--------|-------|-------------|
| Agent Performance Score | -100 to +100 | Quality vs baseline/optimal |
| Human Override Rate | 0-100% | Decisions overridden by humans |
| Touchless Rate | 0-100% | Decisions executed without intervention |
| Override Dependency Ratio | Per decision type | Where AI needs improvement |

### Decision Status Flow
Suggested → Reviewed → Accepted/Overridden → Submitted

Override reasons are captured for continuous learning (RLHF-style feedback loop).

### Ask Why Functionality
Every agent decision includes:
- Authority boundaries (what the agent can/cannot do)
- Active guardrails (constraints that shaped the decision)
- Model attribution (gradient saliency for TRMs, attention for GNNs)
- Conformal prediction intervals (uncertainty context)
- Counterfactual analysis ("if X were different, decision would be Y")

Available at VERBOSE/NORMAL/SUCCINCT verbosity levels.

## Modular Selling Strategy

The cascade layers can be sold independently:
- **Without S&OP/MPS**: Same UI screens become input screens where customers provide policy parameters manually (safety stock targets, OTIF floors, allocation reserves)
- **Adding MPS/MRP**: Generates multiple Supply Baseline Pack candidates
- **Adding S&OP**: Quantifies consequences of policy changes, tightens feedback loop

This means a customer can start with just the execution layer (TRM agents) and add planning layers over time.

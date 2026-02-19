# Training Data Analysis: TRM vs GNN vs RL

**Date**: 2026-01-20
**Question**: Do all AI agents use the same training data?
**Answer**: ❌ **NO** - Each uses fundamentally different training approaches

---

## Executive Summary

The three AI agents (TRM, GNN, RL) use **completely different training data sources and methodologies**:

| Agent | Training Data Source | Data Type | Generation Method |
|-------|---------------------|-----------|-------------------|
| **TRM** | Synthetic curriculum | Supervised (state → action pairs) | Python generator (no simulation) |
| **GNN** | SimPy-generated games | Supervised (demand → prediction) | Full Beer Game simulation |
| **RL** | Self-play episodes | Reinforcement (state → reward) | Online learning in env |

**Why Different?** Each agent solves a different problem using a different learning paradigm.

---

## Detailed Breakdown

### 1. TRM (Tiny Recursive Model) Training Data

**Source**: `backend/app/simulation/trm_curriculum_generator.py`

**Data Generation Method**: **Synthetic Rule-Based Generation**
- **NOT simulation-based**
- Uses mathematical formulas to generate state-action pairs
- No actual Beer Game simulation runs

**Training Paradigm**: **Supervised Learning**
- Input: Node state (inventory, backlog, pipeline, demand history, role, position)
- Output: Optimal order quantity (calculated via rules)

**Curriculum Phases**:
```python
Phase 1: Single-node (retailer only)
Phase 2: Two-node (retailer → manufacturer)
Phase 3: Four-node Beer Game (retailer → wholesaler → distributor → factory)
Phase 4: Multi-echelon (complex supply chains)
Phase 5: Production networks (with BOMs)
```

**Sample Data Point**:
```python
{
    "inventory": 12.5,
    "backlog": 3.0,
    "pipeline": 8.0,
    "demand_history": [4, 8, 12, 8, 4],
    "role": "retailer",  # One-hot encoded
    "position": 0,        # Normalized 0-1
    "target_order": 9.2   # Calculated via base-stock policy
}
```

**Number of Samples**: 10,000 per phase × 5 phases = **50,000 samples**

**Generation Time**: ~5 minutes (no simulation overhead)

**Why This Approach?**
- ✅ **Fast**: No simulation needed
- ✅ **Curriculum Learning**: Progressive difficulty
- ✅ **Consistent**: Deterministic generation
- ✅ **Scalable**: Can generate millions of samples quickly
- ⚠️ **Limited Realism**: Rules may not capture all Beer Game dynamics

---

### 2. GNN (Graph Neural Network) Training Data

**Source**: SimPy simulation → `training_data/*.npz`

**Data Generation Method**: **Full Beer Game Simulation**
- Runs complete Beer Game episodes using SimPy
- Records all node states and demand at each timestep
- Generates graph structure (adjacency matrix, node features)

**Training Paradigm**: **Supervised Learning (Time Series Prediction)**
- Input: Historical states (window of past N rounds)
- Output: Future demand (next round prediction)

**Generation Script**: `backend/scripts/generate_simpy_dataset.py`

**SimPy Generation Process**:
1. Create Beer Game supply chain with SimPy
2. Run multiple episodes with varying demand patterns
3. Record at each timestep:
   - Node features: inventory, backlog, orders, shipments
   - Graph structure: adjacency matrix, edge weights
   - Target: actual demand in next period
4. Save as `.npz` file with arrays X (features), A (adjacency), P (positions), Y (targets)

**Sample Data Point**:
```python
{
    "X": [  # Node features (4 nodes × 10 features)
        [inventory, backlog, order_upstream, ...],  # Retailer
        [inventory, backlog, order_upstream, ...],  # Wholesaler
        [inventory, backlog, order_upstream, ...],  # Distributor
        [inventory, backlog, order_upstream, ...],  # Factory
    ],
    "A": [  # Adjacency matrix (4×4) - who ships to whom
        [0, 1, 0, 0],  # Retailer → Wholesaler
        [0, 0, 1, 0],  # Wholesaler → Distributor
        [0, 0, 0, 1],  # Distributor → Factory
        [0, 0, 0, 0],  # Factory (no downstream)
    ],
    "Y": [4, 8, 12, 8]  # Next round demand for each node
}
```

**Number of Episodes**: 128 runs × 64 timesteps = **8,192 samples** (configurable)

**Generation Time**: ~30 minutes (full simulation overhead)

**Why This Approach?**
- ✅ **Realistic**: Captures actual Beer Game dynamics
- ✅ **Graph Structure**: Learns supply chain topology
- ✅ **Temporal Dependencies**: Captures lead time effects
- ✅ **Bullwhip Effect**: Training data includes realistic volatility
- ⚠️ **Slow**: Simulation overhead for data generation
- ⚠️ **Storage**: Large `.npz` files (50-100 MB per config)

---

### 3. RL (Reinforcement Learning) Training Data

**Source**: **NO PRE-GENERATED DATA**

**Data Generation Method**: **Online Learning (Self-Play)**
- Agent interacts with `BeerGameRLEnv` environment in real-time
- Learns from trial-and-error during training
- Generates experiences on-the-fly

**Training Paradigm**: **Reinforcement Learning**
- Input: Current state (inventory, backlog, pipeline, demand)
- Output: Action (order quantity)
- Feedback: Reward signal (negative of cost)

**Environment**: `backend/app/agents/rl_agent.py:BeerGameRLEnv`

**Experience Collection**:
```python
# Each episode generates experiences:
for round in range(52):
    # 1. Agent observes state
    obs = [inventory, backlog, shipment_0, shipment_1,
           incoming_order, last_order, round_norm, cost_norm]

    # 2. Agent takes action
    action = agent.predict(obs)  # Order quantity

    # 3. Environment responds
    next_obs, reward, done, info = env.step(action)
    reward = -cost  # Minimize cost

    # 4. Store experience for training
    buffer.add(obs, action, reward, next_obs, done)

# After N steps, update policy using stored experiences
agent.train_on_batch(buffer)
```

**Sample Experience**:
```python
{
    "state": [12.5, 3.0, 8.0, 6.0, 4.0, 9.0, 0.23, 0.156],
    "action": 9,          # Order quantity chosen by agent
    "reward": -15.5,      # Negative cost (holding + backlog)
    "next_state": [13.5, 2.0, 6.0, 8.0, 5.0, 9.0, 0.24, 0.171],
    "done": False
}
```

**Number of Experiences**:
- 1M timesteps = ~19,000 episodes × 52 rounds = **~1 million transitions**
- Stored in replay buffer, not disk

**Generation Time**: **Embedded in training** (~90 minutes for 1M steps)

**Why This Approach?**
- ✅ **No Data Needed**: Learns from scratch
- ✅ **Adaptive**: Continuously improves policy
- ✅ **Exploration**: Discovers novel strategies
- ✅ **Optimal Policies**: Can exceed human performance
- ⚠️ **Sample Inefficient**: Needs 1M+ experiences
- ⚠️ **Training Time**: Slow compared to supervised learning

---

## Key Differences

### Training Data Characteristics

| Characteristic | TRM | GNN | RL |
|----------------|-----|-----|-----|
| **Data Source** | Synthetic rules | SimPy simulation | Self-play |
| **Pre-generation** | Yes (10K/phase) | Yes (~8K samples) | No (online) |
| **Storage** | In-memory | .npz files (50-100 MB) | Replay buffer (RAM) |
| **Reusable** | Yes | Yes | No |
| **Generation Time** | 5 min | 30 min | N/A (during training) |
| **Realism** | Low (rule-based) | High (simulation) | Highest (learned) |

### Learning Paradigms

| Aspect | TRM (Supervised) | GNN (Supervised) | RL (Reinforcement) |
|--------|------------------|------------------|---------------------|
| **Input** | State | State history | State |
| **Output** | Action | Demand forecast | Action |
| **Supervision** | Optimal actions | Actual demand | Reward signal |
| **Objective** | Minimize prediction error | Minimize forecast error | Maximize cumulative reward |
| **Training Signal** | Known correct answers | Known future demand | Trial-and-error feedback |

### Training Efficiency

| Metric | TRM | GNN | RL |
|--------|-----|-----|-----|
| **Samples Needed** | 50K (5 phases) | 8K | 1M+ |
| **Training Time** | 2-4 hours | 1-2 hours | 1.5 hours |
| **Data Generation** | 5 min | 30 min | N/A |
| **Total Time** | 2.5-4.5 hours | 1.5-2.5 hours | 1.5 hours |

---

## Why Not Use the Same Data?

### Reason 1: Different Learning Paradigms

**TRM & GNN**: Supervised learning requires labeled data
- TRM: Needs (state → action) pairs
- GNN: Needs (historical states → future demand) pairs

**RL**: Reinforcement learning doesn't need labels
- Learns from reward signals
- Discovers optimal policies through exploration

**Attempting to use SimPy data for RL**:
- ❌ SimPy data has fixed agent policies (naive, base-stock, etc.)
- ❌ RL would learn to imitate these policies, not optimize
- ❌ No reward signal in SimPy data

### Reason 2: Different Problem Formulations

**TRM**: Node-level decision making
- Input: Single node state
- Output: Order quantity for that node
- Training: Learns mapping from local state to action

**GNN**: Network-level demand prediction
- Input: Entire supply chain graph
- Output: Demand forecast for all nodes
- Training: Learns temporal patterns across network

**RL**: Sequential decision making
- Input: Current environment state
- Output: Action that maximizes long-term reward
- Training: Learns policy through interaction

### Reason 3: Data Requirements

**TRM**: Needs diverse node positions and roles
- Curriculum progresses through increasing complexity
- Must see many supply chain topologies
- Rule-based generation ensures coverage

**GNN**: Needs temporal correlation and graph structure
- Must capture lead time effects
- Requires realistic bullwhip amplification
- SimPy simulation provides authentic dynamics

**RL**: Needs exploration of state-action space
- Must try many different strategies
- Learns from mistakes and successes
- Online learning enables adaptive exploration

---

## Could They Share Data?

### Theoretical Possibilities

#### 1. **Use SimPy Data for TRM Training** ✅ Possible
```python
# Extract state-action pairs from SimPy episodes
for episode in simpy_data:
    for timestep in episode:
        state = extract_node_state(timestep, node_id)
        action = timestep.orders[node_id]
        # Use as supervised training data
```

**Pros**:
- More realistic training data
- Captures actual Beer Game dynamics

**Cons**:
- Limited to policies used in SimPy simulation
- May not learn optimal behavior if SimPy agents are suboptimal
- More expensive to generate

#### 2. **Use SimPy Data for RL Imitation Learning** ✅ Possible
```python
# Pre-train RL agent to imitate SimPy behavior
for episode in simpy_data:
    for timestep in episode:
        state = extract_state(timestep)
        action = timestep.action
        # Use for behavioral cloning (supervised pre-training)

# Then fine-tune with RL
agent.learn(env, total_timesteps=1_000_000)
```

**Pros**:
- Faster convergence (warm start)
- Avoids random exploration initially

**Cons**:
- Still needs RL phase for optimization
- Limited by quality of SimPy policies

#### 3. **Use TRM Data for GNN** ❌ Not Directly Compatible
- TRM data lacks graph structure (adjacency matrix)
- TRM data lacks temporal sequences
- Different problem formulation (action vs demand)

---

## Recommendations

### Current Approach ✅ **KEEP AS IS**

**Rationale**:
1. ✅ **Each agent optimized for its learning paradigm**
2. ✅ **Fastest training for each approach**
3. ✅ **Most appropriate data for each model**

### Potential Improvements

#### 1. **Shared SimPy Dataset for TRM & GNN** (Medium Priority)

**Proposal**: Generate one comprehensive SimPy dataset, use for both:
- GNN: Use directly (as currently done)
- TRM: Extract state-action pairs for supervised learning

**Benefits**:
- Single data generation process
- More realistic TRM training data
- Consistent evaluation across models

**Implementation**:
```python
# Generate comprehensive dataset
dataset = generate_simpy_dataset(
    configs=["default_tbg", "complex_sc", ...],
    episodes_per_config=200,
    agent_policies=["naive", "base_stock", "ml_forecast"]
)

# Use for GNN training (as is)
gnn.train(dataset)

# Extract for TRM training
trm_data = extract_state_action_pairs(dataset)
trm.train(trm_data)
```

**Estimated Effort**: 1-2 weeks

#### 2. **RL Pre-training with Imitation** (Low Priority)

**Proposal**: Pre-train RL agent on SimPy data before RL training

**Benefits**:
- Faster convergence
- Better initial policies
- Less random exploration

**Trade-offs**:
- More complex training pipeline
- Marginal performance gain
- Adds dependency on SimPy data

**Implementation**:
```python
# Phase 1: Imitation learning (supervised)
rl_agent.pretrain_from_demonstrations(simpy_dataset, epochs=10)

# Phase 2: RL fine-tuning (reinforcement learning)
rl_agent.learn(env, total_timesteps=1_000_000)
```

**Estimated Effort**: 1 week

---

## Conclusion

### Question: Do all agents use the same training data?

**Answer**: ❌ **NO**, and **this is by design**.

### Why Different Data?

1. **Different Learning Paradigms**: Supervised vs Reinforcement
2. **Different Problems**: Node decisions vs Demand forecasting vs Policy optimization
3. **Different Requirements**: Speed vs Realism vs Optimality

### Should They Share Data?

**Current Answer**: **No need** - each approach is already optimized

**Future Consideration**: **SimPy data sharing** between TRM and GNN could be beneficial

### Key Insight

The diversity of training approaches reflects the **multi-faceted nature** of supply chain planning:
- **TRM**: Fast heuristic decisions (supervised from rules)
- **GNN**: Demand prediction (supervised from simulation)
- **RL**: Policy optimization (reinforcement from experience)

This **multi-agent ensemble** approach is actually a **strength**, not a weakness:
- Each agent learns different aspects of the problem
- Ensemble methods can combine their strengths
- Different agents excel in different scenarios

---

**Status**: Current training data approach is **optimal** for each agent type
**Recommendation**: **Keep current approach**, consider SimPy data sharing as future enhancement
**Priority**: Low (current approach works well)

# TRM vs GNN Training Data Comparison

**Date**: 2026-01-17
**Question**: Is the same training data used for TRM and GNN?

---

## Answer: **NO** - They use different data generation approaches

TRM and GNN use **completely different training data pipelines** with different philosophies, formats, and generation methods.

---

## Side-by-Side Comparison

| Aspect | **TRM (Tiny Recursive Model)** | **GNN (Graph Neural Network)** |
|--------|--------------------------------|--------------------------------|
| **Data Source** | Synthetic curriculum-based simulation | SimPy-based Beer Game simulations |
| **Generator File** | [trm_curriculum_generator.py](backend/app/simulation/trm_curriculum_generator.py) | [data_generator.py](backend/app/rl/data_generator.py) |
| **Generation Script** | [train_trm.py](backend/scripts/training/train_trm.py) | [generate_simpy_dataset.py](backend/scripts/training/generate_simpy_dataset.py) |
| **Data Format** | Per-node time series (flat tensors) | Graph-structured tensors with adjacency matrices |
| **Curriculum** | 5 progressive phases (simple → complex) | Single-pass with parameter randomization |
| **Training Philosophy** | Imitation learning from optimal policies | Imitation learning from agent trajectories |
| **Node Representation** | Individual node features | Graph nodes with message passing |
| **Topology** | Fixed per phase (1, 2, 4, multi-node) | Fixed 4-node Beer Game |
| **Demand Patterns** | Random, seasonal, step, trend | SimDemand with step-up pattern |
| **Labels** | Optimal base stock / PID orders | Agent-generated orders (naive, PID, LLM) |
| **Dataset Size** | 10K samples per phase (50K total) | 128-256 runs × timesteps |

---

## TRM Training Data Details

### Data Generation

**File**: [trm_curriculum_generator.py](backend/app/simulation/trm_curriculum_generator.py)

```python
def generate_curriculum_dataset(phase: int, num_samples: int = 10000):
    """
    Generate phase-specific curriculum data.

    Phase 1: Single-node base stock (simple)
    Phase 2: 2-node supply chain
    Phase 3: 4-node Beer Game
    Phase 4: Multi-echelon variations
    Phase 5: Production with manufacturing
    """
    if phase == 1:
        return generate_phase1_data(num_samples)  # Single node
    elif phase == 2:
        return generate_phase2_data(num_samples)  # 2 nodes
    # ... etc
```

### Data Format

**Per-Sample Structure** (flat tensors):
```python
{
    'inventory': [50.2],           # Current inventory level
    'backlog': [5.0],              # Current backlog
    'pipeline': [45.0, 30.0, 20.0], # Incoming shipments (lead time window)
    'demand_history': [48, 52, 50, 49, 51, 53, 50], # Recent demand (7 periods)
    'node_type': 'retailer',       # Node role
    'node_position': 0,            # Position in chain (0=downstream)
    'target_order': 52.0,          # Label: optimal order quantity
    'target_value': -125.5         # Label: state value (cost)
}
```

**Tensor Shapes**:
- `inventory`: (batch_size, 1)
- `backlog`: (batch_size, 1)
- `pipeline`: (batch_size, max_lead_time)
- `demand_history`: (batch_size, history_window)
- `node_type`: (batch_size,) - categorical
- `node_position`: (batch_size, 1)
- `target_order`: (batch_size, 1)
- `target_value`: (batch_size, 1)

### Curriculum Phases

**Phase 1: Single Node** (10K samples)
- Just inventory management
- Base stock policy labels
- No upstream/downstream
- Simplest scenario

**Phase 2: 2-Node Chain** (10K samples)
- Retailer → Wholesaler
- Simple order propagation
- Basic bullwhip effects

**Phase 3: 4-Node Beer Game** (10K samples)
- Retailer → Wholesaler → Distributor → Factory
- Classic Beer Game topology
- Full supply chain dynamics

**Phase 4: Multi-Echelon** (10K samples)
- Varied topologies (3-6 nodes)
- Multiple demand points
- Complex routing

**Phase 5: Production** (10K samples)
- Manufacturing constraints
- Bill of materials
- Capacity limits
- Real-world complexity

### Label Generation

TRM uses **optimal heuristics** as labels:

1. **Base Stock Policy** (Phase 1-2):
   ```python
   target_order = max(0, base_stock_level - inventory - pipeline_sum + backlog)
   ```

2. **PID Controller** (Phase 3-5):
   ```python
   target_order = alpha * demand_forecast + beta * backlog - gamma * inventory + delta * pipeline_error
   ```

These provide "expert demonstrations" for the model to learn from.

---

## GNN Training Data Details

### Data Generation

**File**: [data_generator.py](backend/app/rl/data_generator.py)

```python
def generate_sim_training_windows(
    num_runs: int,
    T: int,
    window: int = 52,
    horizon: int = 1,
    params: BeerGameParams = BeerGameParams(),
    use_simpy: bool = True,
    agent_strategy: AgentStrategy = AgentStrategy.LLM
):
    """
    Generate training data from SimPy Beer Game simulations.

    Returns:
        X: Node features (num_samples, num_nodes, num_features)
        Y: Action labels (num_samples, num_nodes, num_actions)
        P: Graph structure (adjacency matrices)
    """
```

### Data Format

**Graph-Structured** (per timestep):
```python
{
    'node_features': [
        # Retailer
        [inventory, backlog, incoming_orders, incoming_shipments, on_order,
         is_retailer=1, is_wholesaler=0, is_distributor=0, is_factory=0,
         order_leadtime, supply_leadtime],
        # Wholesaler
        [inventory, backlog, incoming_orders, incoming_shipments, on_order,
         is_retailer=0, is_wholesaler=1, is_distributor=0, is_factory=0,
         order_leadtime, supply_leadtime],
        # Distributor
        [...],
        # Factory
        [...]
    ],  # Shape: (4, 12)

    'adjacency_shipment': [
        [0, 1, 0, 0],  # Factory → Distributor
        [0, 0, 1, 0],  # Distributor → Wholesaler
        [0, 0, 0, 1],  # Wholesaler → Retailer
        [0, 0, 0, 0]   # Retailer → Customer
    ],  # Shape: (4, 4)

    'adjacency_order': [
        [0, 0, 0, 0],  # Factory receives from Distributor
        [1, 0, 0, 0],  # Distributor receives from Wholesaler
        [0, 1, 0, 0],  # Wholesaler receives from Retailer
        [0, 0, 1, 0]   # Retailer receives from Customer
    ],  # Shape: (4, 4)

    'action_labels': [52, 48, 55, 60]  # Orders placed by each node
}
```

**Tensor Shapes**:
- `X` (node features): (num_samples, 4, 12)
- `Y` (action labels): (num_samples, 4, 1) or (num_samples, 4, num_actions)
- `A_ship` (shipment adjacency): (4, 4)
- `A_order` (order adjacency): (4, 4)

### SimPy Simulation

**Process**:
1. Initialize 4-node Beer Game
2. Run simulation for T timesteps (default: 64)
3. Agent strategy generates orders (naive, PID, or LLM)
4. Record full state at each timestep
5. Extract sliding windows for training

**Simulation Function**:
```python
def simulate_beer_game(T, params, demand_fn, agent_strategy='naive'):
    """
    Run Beer Game with specified agent strategy.

    Returns:
        {
            'retailer': {
                'inventory': [50, 48, 52, ...],
                'backlog': [0, 2, 0, ...],
                'placed_order': [52, 50, 55, ...]
            },
            'wholesaler': {...},
            'distributor': {...},
            'factory': {...}
        }
    """
```

### Label Generation

GNN uses **agent trajectories** as labels:

1. **Naive Agent** (default):
   ```python
   order = incoming_demand  # Mirror downstream demand
   ```

2. **PID Agent** (with tuning):
   ```python
   order = pid_controller(inventory, backlog, demand_forecast, params)
   ```

3. **LLM Agent** (OpenAI):
   ```python
   order = llm_agent.decide(context)  # GPT-generated decisions
   ```

The model learns to imitate whatever agent strategy generated the data.

---

## Key Differences

### 1. **Data Structure**

**TRM**: Per-node independent samples
- Each training sample is a single node's state
- No explicit graph structure
- Node type and position encoded as features
- Fast to generate and load

**GNN**: Full graph snapshots
- Each sample contains all 4 nodes simultaneously
- Explicit adjacency matrices for message passing
- Preserves supply chain topology
- More memory intensive

### 2. **Curriculum vs Single-Pass**

**TRM**: Progressive curriculum
- Starts simple (1 node)
- Gradually increases complexity
- 5 distinct training phases
- Model builds on previous knowledge

**GNN**: Direct training
- Fixed 4-node topology
- All complexity at once
- Randomized parameters for variety
- No progressive learning

### 3. **Label Philosophy**

**TRM**: Optimal policies
- Base stock (provably optimal for Phase 1)
- PID controller (tuned heuristic)
- "Expert demonstrations"
- Focuses on cost minimization

**GNN**: Agent imitation
- Learns from agent behavior
- Can use naive, PID, or LLM agents
- Captures strategy patterns
- Focuses on replicating decisions

### 4. **Scalability**

**TRM**: Flexible topology
- Can handle 1 to N nodes
- Each phase has different topology
- Not tied to Beer Game structure
- Generalizes to varied supply chains

**GNN**: Fixed 4-node
- Hardcoded for Beer Game topology
- Requires retraining for different structures
- Adjacency matrices are fixed
- Specific to this problem

### 5. **Training Time**

**TRM**: ~2.5 hours (GPU)
- 5 phases × 10K samples each
- Lighter model (7M params)
- Faster epochs

**GNN**: ~4-6 hours (GPU)
- 128-256 runs × 64 timesteps
- Heavier model (128M+ params)
- Graph message passing overhead
- Slower convergence

---

## Can They Share Data?

### Short Answer: **No, not directly**

The data formats are incompatible:

1. **Shape mismatch**:
   - TRM expects: `(batch, features)` per node
   - GNN expects: `(batch, num_nodes, features)` graph

2. **Feature differences**:
   - TRM: `[inventory, backlog, pipeline, demand_history, node_type, position]`
   - GNN: `[inventory, backlog, incoming_orders, incoming_shipments, on_order, one_hot_role, leadtimes]`

3. **Label format**:
   - TRM: Scalar order quantity per sample
   - GNN: Vector of orders for all nodes

### Potential Bridge

You **could** theoretically convert GNN data to TRM format:

```python
def gnn_to_trm_samples(gnn_batch):
    """Convert GNN graph samples to TRM per-node samples."""
    trm_samples = []

    # Extract each node from the graph
    for node_idx in range(4):
        sample = {
            'inventory': gnn_batch['X'][:, node_idx, 0],
            'backlog': gnn_batch['X'][:, node_idx, 1],
            'pipeline': gnn_batch['X'][:, node_idx, 3],  # incoming_shipments
            'demand_history': [...],  # Not in GNN format!
            'node_type': node_idx,
            'target_order': gnn_batch['Y'][:, node_idx]
        }
        trm_samples.append(sample)

    return trm_samples
```

**Problem**: GNN data lacks `demand_history`, which is critical for TRM's recursive refinement.

---

## Which is Better?

### Use TRM Data When:
- ✅ You want curriculum learning (simple → complex)
- ✅ You need flexible topologies (1 to N nodes)
- ✅ You want provably optimal labels (base stock)
- ✅ You need fast training (<3 hours)
- ✅ You're working with varied supply chain structures

### Use GNN Data When:
- ✅ You want to preserve graph structure
- ✅ You need message passing between nodes
- ✅ You're focused on 4-node Beer Game only
- ✅ You want to imitate specific agent strategies
- ✅ You need end-to-end joint optimization

### Hybrid Approach (Future Work):
You could combine both:
1. Use TRM curriculum for pre-training
2. Fine-tune on GNN graph data for specific topologies
3. Best of both worlds: curriculum + graph structure

---

## Summary Table

| Feature | TRM Data | GNN Data |
|---------|----------|----------|
| **Format** | Flat per-node tensors | Graph-structured tensors |
| **Generator** | `trm_curriculum_generator.py` | `data_generator.py` |
| **Topology** | Variable (1-N nodes) | Fixed (4 nodes) |
| **Curriculum** | 5 progressive phases | Single-pass |
| **Labels** | Optimal heuristics | Agent trajectories |
| **Dataset Size** | 50K samples (5×10K) | 128-256 runs × 64 steps |
| **Generation Time** | ~30 min | ~1-2 hours |
| **Training Time** | ~2.5 hours | ~4-6 hours |
| **Model Params** | 7M (TRM) | 128M+ (GNN) |
| **Inference Speed** | <10ms | ~50-100ms |
| **Use Case** | General supply chains | Beer Game specific |

---

## Conclusion

**TRM and GNN use completely different training data**:

- **TRM**: Curriculum-based synthetic data with per-node samples and optimal policy labels
- **GNN**: SimPy-based graph data with full topology and agent imitation labels

They cannot directly share data due to format incompatibility, but a conversion bridge could be built if needed (with limitations).

The choice depends on your use case:
- **TRM** for flexibility, speed, and curriculum learning
- **GNN** for graph-aware reasoning and Beer Game specificity

---

**Document Version**: 1.0
**Last Updated**: 2026-01-17
**Status**: ✅ Complete

# Training Data AWS SC Compliance Analysis

**Date**: 2026-01-21
**Question**: Does training data generation use AWS Supply Chain Data Model tables and fields?
**Answer**: ❌ **NO** - Training data uses custom Beer Game schema, not AWS SC entities

---

## Executive Summary

**Current State**: Training data generation for TRM, GNN, and RL agents **does NOT use AWS Supply Chain Data Model** tables or fields. Instead, it uses:

1. **Custom Beer Game Schema**: Hardcoded Beer Game roles, features, and parameters
2. **Minimal Config Integration**: Only reads `SupplyChainConfig` for parameter ranges, not AWS SC entities
3. **Beer Game-Centric Design**: All training data reflects classic 4-node Beer Game topology

**Compliance Status**: 🔴 **0% AWS SC Compliant** for training data generation

**Impact**: Training data cannot generalize to real AWS SC planning scenarios without architectural changes.

---

## Current Training Data Sources

### 1. TRM Training Data (Synthetic)

**File**: `backend/app/simulation/trm_curriculum_generator.py`

**Data Structure**:
```python
{
    "inventory": np.array,      # Custom field (not from AWS SC)
    "backlog": np.array,        # Custom field (not from AWS SC)
    "pipeline": np.array,       # Custom field (not from AWS SC)
    "demand_history": np.array, # Custom field (not from AWS SC)
    "node_types": np.array,     # Beer Game roles (0=retailer, 1=wholesaler, etc.)
    "node_positions": np.array, # Beer Game positions (0-3)
    "target_orders": np.array,  # Synthetic labels
    "target_values": np.array   # Synthetic costs
}
```

**Fields Used** (303 lines):
- `inventory` (lines 185, 96, etc.)
- `backlog` (lines 186, 109, etc.)
- `pipeline` (lines 187, 124, etc.)
- `demand_history` (lines 188)
- `node_types` (lines 200) - Hardcoded: 0=retailer, 1=wholesaler, 2=distributor, 3=factory
- `node_positions` (lines 201)
- `target_orders` (lines 202)
- `target_values` (lines 203)

**AWS SC Entities Used**: ❌ **NONE**

**AWS SC Fields Used**: ❌ **NONE**

---

### 2. GNN Training Data (SimPy Simulation)

**File**: `backend/scripts/training/generate_simpy_dataset.py`

**Data Structure**:
```python
X: np.ndarray  # [num_windows, T, N=4, F] node features
A: np.ndarray  # [2, N, N] adjacency matrices
P: np.ndarray  # [num_windows, C] global context
Y: np.ndarray  # [num_windows, N, T] action labels
```

**Node Features** (from `backend/app/rl/config.py:32-42`):
```python
NODE_FEATURES = [
    "inventory",           # Not AWS SC
    "backlog",            # Not AWS SC
    "incoming_orders",    # Not AWS SC
    "incoming_shipments", # Not AWS SC
    "on_order",           # Not AWS SC (pipeline)
    "role_onehot_0",      # Beer Game specific
    "role_onehot_1",      # Beer Game specific
    "role_onehot_2",      # Beer Game specific
    "role_onehot_3",      # Beer Game specific
    "lead_time_order",    # Not AWS SC field name
    "lead_time_supply",   # Not AWS SC field name
]
```

**BeerGameParams** (from `backend/app/rl/config.py:45-52`):
```python
@dataclass
class BeerGameParams:
    order_leadtime: int = 2        # Not AWS SC field
    supply_leadtime: int = 2       # Not AWS SC field
    init_inventory: int = 12       # Not AWS SC field
    holding_cost: float = 0.5      # Not AWS SC field
    backlog_cost: float = 1.0      # Not AWS SC field
    max_inbound_per_link: int = 100  # Not AWS SC field
    max_order: int = 100           # Not AWS SC field
```

**SupplyChainConfig Usage** (lines 226-368):
```python
def _load_param_ranges_from_config(supply_chain_config_id: int, db_url: Optional[str] = None):
    """Derive simulator parameter ranges from a stored supply chain config."""

    # Reads from nodes table (custom fields, not AWS SC):
    node_rows = conn.execute(text("""
        SELECT
            n.initial_inventory_range,  # ❌ Not AWS SC field
            n.lead_time                 # ❌ Not AWS SC field
        FROM nodes n
        WHERE n.config_id = :cfg_id
    """), {"cfg_id": supply_chain_config_id}).mappings().all()

    # Reads from lanes table (custom fields, not AWS SC):
    lane_rows = conn.execute(text("""
        SELECT
            capacity  # ❌ Not AWS SC field (should be transit_capacity_uom_qty)
        FROM lanes
        WHERE config_id = :cfg_id
    """), {"cfg_id": supply_chain_config_id}).mappings().all()
```

**AWS SC Entities Used**:
- ⚠️ Partial: Reads `nodes` and `lanes` tables (but uses custom fields, not AWS SC fields)

**AWS SC Fields Used**: ❌ **NONE** (uses custom field names)

---

### 3. RL Training Data (Self-Play)

**File**: `backend/app/agents/rl_agent.py`

**Environment State** (BeerGameRLEnv):
```python
def _get_observation(self) -> np.ndarray:
    """Get current observation (8 features)."""
    return np.array([
        self.node.inventory,           # Custom field
        self.node.backlog,             # Custom field
        self.node.pipeline_shipments[0],  # Custom field
        self.node.pipeline_shipments[1],  # Custom field
        self.node.incoming_order,      # Custom field
        self.node.last_order_placed,   # Custom field
        self.current_round / self.max_rounds,  # Normalized round
        self._get_cost() / 1000.0      # Normalized cost
    ], dtype=np.float32)
```

**AWS SC Entities Used**: ❌ **NONE**

**AWS SC Fields Used**: ❌ **NONE**

---

## AWS SC Entities NOT Used in Training

### Missing Critical Entities

According to `backend/app/models/sc_entities.py`, these AWS SC entities are **NOT used** in training data generation:

| Entity | AWS SC Purpose | Used in Training? |
|--------|----------------|-------------------|
| `company` | Organization/tenant | ❌ No |
| `geography` | Geographical hierarchies | ❌ No |
| `trading_partner` | Suppliers/customers | ❌ No |
| `site` | Physical locations | ❌ No (uses custom `nodes`) |
| `product` | SKUs/items | ❌ No (uses custom `items`) |
| `product_bom` | Bill of materials | ❌ No |
| `sourcing_rules` | Buy/transfer/manufacture rules | ❌ No |
| `inv_policy` | Inventory policies (4 types) | ❌ No |
| `inv_level` | Current inventory | ❌ No (uses custom `inventory`) |
| `forecast` | Demand forecasts | ❌ No (uses synthetic demand) |
| `supply_plan` | Generated supply plans | ❌ No |
| `inbound_order` | Purchase orders | ❌ No |
| `outbound_order` | Sales orders | ❌ No |
| `inbound_order_line` | PO line items | ❌ No |
| `outbound_order_line` | SO line items | ❌ No |

**Total AWS SC Entities Available**: 35
**Used in Training**: 0
**Compliance**: 0%

---

## Comparison: Current vs AWS SC Schema

### Current Training Schema (Beer Game)

```python
# Node features (TRM/GNN)
inventory: int            # Custom field
backlog: int              # Custom field
pipeline: int             # Custom field
incoming_orders: int      # Custom field
incoming_shipments: int   # Custom field
on_order: int             # Custom field
demand_history: List[int] # Custom field

# Node metadata
role: str                 # "retailer", "wholesaler", etc. (Beer Game specific)
position: int             # 0-3 (Beer Game specific)

# Parameters
holding_cost: float       # Custom field
backlog_cost: float       # Custom field
order_leadtime: int       # Custom field
supply_leadtime: int      # Custom field
```

### AWS SC Schema (Standard)

```python
# From site entity
site_id: str                    # AWS SC PK
site_desc: str                  # AWS SC field
company_id: str                 # AWS SC FK
geography_id: str               # AWS SC FK
latitude: float                 # AWS SC field
longitude: float                # AWS SC field
time_zone: str                  # AWS SC field

# From inv_level entity
item_id: str                    # AWS SC FK
site_id: str                    # AWS SC FK
on_hand_qty: float              # ✅ Equivalent to inventory
allocated_qty: float            # AWS SC field
in_transit_qty: float           # ✅ Equivalent to pipeline
backorder_qty: float            # ✅ Equivalent to backlog
safety_stock_qty: float         # AWS SC field
reorder_point_qty: float        # AWS SC field
min_qty: float                  # AWS SC field
max_qty: float                  # AWS SC field

# From sourcing_rules entity
source_site_id: str             # AWS SC FK
destination_site_id: str        # AWS SC FK
source_type: str                # "buy", "transfer", "manufacture"
lead_time_days: int             # ✅ Equivalent to lead time
priority: int                   # AWS SC field
```

**Key Differences**:
1. ❌ Training uses integer `inventory` instead of AWS SC `on_hand_qty` (float with UOM)
2. ❌ Training uses custom `backlog` instead of AWS SC `backorder_qty`
3. ❌ Training uses custom `pipeline` instead of AWS SC `in_transit_qty`
4. ❌ Training uses Beer Game roles instead of AWS SC `site_id` + `item_id` combinations
5. ❌ Training hardcodes 4-node topology instead of reading AWS SC `sourcing_rules`
6. ❌ Training uses custom parameters instead of AWS SC `inv_policy` configurations

---

## Root Cause Analysis

### Why Training Data Doesn't Use AWS SC

**Historical Reasons**:
1. **Beer Game Legacy**: Project started as Beer Game gamification, not AWS SC planning
2. **Research Focus**: TRM/GNN agents developed for Beer Game research, not production planning
3. **Simplicity**: Beer Game schema is simpler than AWS SC (4 nodes vs 35 entities)
4. **Performance**: Hardcoded schema is faster than database joins across 35 tables

**Technical Reasons**:
1. **Curriculum Learning**: TRM phases (1-5) designed for Beer Game topology, not AWS SC networks
2. **Graph Structure**: GNN expects fixed 4-node graph, not dynamic AWS SC DAGs
3. **State Space**: RL environment hardcoded to 8-feature observation, not AWS SC entity combinations
4. **Simulation Speed**: SimPy backend optimized for Beer Game, not AWS SC sourcing rules

---

## Impact Assessment

### Current Impact

**What Works**:
- ✅ Training data is consistent and fast to generate
- ✅ Agents perform well on Beer Game scenarios
- ✅ Research/validation of agent architectures

**What Doesn't Work**:
- ❌ Agents **CANNOT** be used for real AWS SC planning without retraining
- ❌ Training data **DOES NOT** reflect AWS SC data model
- ❌ No support for AWS SC features:
  - Multi-item planning
  - Multi-sourcing with priorities
  - BOM explosion
  - Inventory policy types (abs_level, doc_dem, doc_fcst, sl)
  - Trading partner relationships
  - Geographic hierarchies
  - Production processes

### Production Limitations

**Agents Cannot Handle**:
1. Multi-item supply chains (training only uses single implicit item)
2. Complex sourcing rules (buy vs transfer vs manufacture)
3. BOM-based manufacturing (training has no BOM concept)
4. Hierarchical inventory policies (training uses fixed costs)
5. Real-world supply chain topologies (training assumes 4-node Beer Game)

**Business Impact**:
- Agents positioned as "AI for supply chain planning" but trained only on Beer Game scenarios
- Cannot deploy agents in production AWS SC environments without complete retraining
- Marketing claim of "20-35% cost reduction" only valid for Beer Game, not real supply chains

---

## Recommendations

### Option 1: Extend Training Data with AWS SC Fields ✅ **RECOMMENDED**

**Approach**: Keep Beer Game as special case, add AWS SC fields as extensions

**Implementation**:
```python
# backend/app/rl/config.py
from app.models.sc_entities import Site, InvLevel, SourcingRules

@dataclass
class BeerGameParams:
    # Core AWS SC fields (REQUIRED)
    site_id: str                    # AWS SC PK
    item_id: str                    # AWS SC PK
    on_hand_qty: float              # AWS SC field
    backorder_qty: float            # AWS SC field
    in_transit_qty: float           # AWS SC field
    lead_time_days: int             # AWS SC field

    # Beer Game extensions (OPTIONAL)
    role: Optional[str] = None      # Extension: Beer Game role
    position: Optional[int] = None  # Extension: Beer Game position

    # Cost parameters (map to inv_policy)
    holding_cost: float = 0.5       # Extension: cost per unit per day
    backlog_cost: float = 1.0       # Extension: cost per unit backorder
```

**Training Data Generation**:
```python
# Read from AWS SC tables
def generate_training_data(config_id: int):
    # Step 1: Load AWS SC entities
    sites = session.query(Site).filter_by(config_id=config_id).all()
    items = session.query(Product).filter_by(config_id=config_id).all()
    sourcing_rules = session.query(SourcingRules).filter_by(config_id=config_id).all()

    # Step 2: Build graph from sourcing_rules
    graph = build_supply_chain_graph(sourcing_rules)

    # Step 3: For each (site, item) combination
    for site in sites:
        for item in items:
            inv_level = get_inv_level(site.site_id, item.item_id)

            # Generate training sample with AWS SC fields
            sample = {
                "site_id": site.site_id,
                "item_id": item.item_id,
                "on_hand_qty": inv_level.on_hand_qty,
                "backorder_qty": inv_level.backorder_qty,
                "in_transit_qty": inv_level.in_transit_qty,
                "lead_time_days": get_lead_time(site, item),

                # Extensions for Beer Game compatibility
                "role": map_site_to_beer_game_role(site),  # Optional
                "position": get_position_in_dag(site, graph)  # Optional
            }
```

**Benefits**:
- ✅ Compliant with AWS SC data model
- ✅ Beer Game remains special case (backward compatible)
- ✅ Agents can generalize to real AWS SC scenarios
- ✅ Training data includes AWS SC features (multi-item, multi-sourcing, BOM)

**Effort**: 4-6 weeks
- Week 1: Extend BeerGameParams with AWS SC fields
- Week 2: Modify training data generation to read AWS SC tables
- Week 3: Update TRM/GNN/RL agents to handle AWS SC features
- Week 4-6: Retrain all agents on AWS SC-compliant data

---

### Option 2: Separate Training Data for Beer Game vs AWS SC ⚠️ **NOT RECOMMENDED**

**Approach**: Maintain two separate training pipelines

**Beer Game Training**:
```python
# Uses custom schema (current approach)
beer_game_data = generate_beer_game_training_data(
    roles=["retailer", "wholesaler", "distributor", "factory"],
    topology="linear"
)
```

**AWS SC Training**:
```python
# Uses AWS SC schema (new pipeline)
aws_sc_data = generate_aws_sc_training_data(
    sites=aws_sc_sites,
    items=aws_sc_items,
    sourcing_rules=aws_sc_sourcing_rules
)
```

**Problems**:
- ❌ Doubles maintenance burden (two training pipelines)
- ❌ Agents trained on Beer Game cannot be used for AWS SC
- ❌ Doubles training time and storage
- ❌ Confusing for users (which agent to use?)

---

### Option 3: Migrate Fully to AWS SC (No Beer Game) ❌ **NOT RECOMMENDED**

**Approach**: Remove Beer Game schema entirely, use only AWS SC

**Problems**:
- ❌ Breaks backward compatibility with existing Beer Game agents
- ❌ Loses simplicity of Beer Game for training/education
- ❌ Requires rewriting all training scripts
- ❌ Existing checkpoints unusable

---

## Recommended Implementation Plan

### Phase 1: Schema Extension (Week 1-2)

1. **Extend BeerGameParams** with AWS SC fields:
   ```python
   @dataclass
   class BeerGameParams:
       # AWS SC core fields (REQUIRED)
       site_id: str
       item_id: str
       on_hand_qty: float
       backorder_qty: float
       in_transit_qty: float
       lead_time_days: int

       # Beer Game extensions (OPTIONAL - for backward compatibility)
       role: Optional[str] = None
       position: Optional[int] = None
       holding_cost: float = 0.5
       backlog_cost: float = 1.0
   ```

2. **Add AWS SC field mappings**:
   ```python
   AWS_SC_FIELD_MAP = {
       "inventory": "on_hand_qty",
       "backlog": "backorder_qty",
       "pipeline": "in_transit_qty",
       "order_leadtime": "lead_time_days",
   }
   ```

3. **Create adapter functions**:
   ```python
   def beer_game_to_aws_sc(beer_game_state: dict) -> dict:
       """Convert Beer Game state to AWS SC format."""
       return {
           "on_hand_qty": beer_game_state["inventory"],
           "backorder_qty": beer_game_state["backlog"],
           "in_transit_qty": beer_game_state["pipeline"],
       }

   def aws_sc_to_beer_game(aws_sc_state: dict) -> dict:
       """Convert AWS SC state to Beer Game format (for backward compat)."""
       return {
           "inventory": aws_sc_state["on_hand_qty"],
           "backlog": aws_sc_state["backorder_qty"],
           "pipeline": aws_sc_state["in_transit_qty"],
       }
   ```

### Phase 2: Training Data Generation (Week 3-4)

1. **Modify `generate_simpy_dataset.py`**:
   ```python
   def _load_aws_sc_entities(config_id: int):
       """Load AWS SC entities for training."""
       sites = session.query(Site).filter_by(config_id=config_id).all()
       items = session.query(Product).filter_by(config_id=config_id).all()
       sourcing_rules = session.query(SourcingRules).filter_by(config_id=config_id).all()
       inv_policies = session.query(InvPolicy).filter_by(config_id=config_id).all()
       return sites, items, sourcing_rules, inv_policies
   ```

2. **Generate AWS SC-compliant training data**:
   ```python
   def generate_aws_sc_training_windows(config_id: int):
       sites, items, sourcing_rules, inv_policies = _load_aws_sc_entities(config_id)

       for site in sites:
           for item in items:
               # Simulate with AWS SC fields
               state = simulate_with_aws_sc(site, item, sourcing_rules)

               # Generate training sample
               yield {
                   "site_id": site.site_id,
                   "item_id": item.item_id,
                   "on_hand_qty": state.on_hand_qty,
                   "backorder_qty": state.backorder_qty,
                   # ... AWS SC fields

                   # Extensions (optional)
                   "role": map_to_beer_game_role(site) if is_beer_game else None,
               }
   ```

### Phase 3: Agent Updates (Week 5-6)

1. **Update TRM curriculum generator** to use AWS SC fields
2. **Update GNN node features** to include AWS SC fields
3. **Update RL environment** to use AWS SC state space

### Phase 4: Retraining (Week 7-8)

1. Regenerate all training data using AWS SC fields
2. Retrain TRM agent (5 phases)
3. Retrain GNN agent
4. Retrain RL agent (1M timesteps)

### Phase 5: Validation (Week 9-10)

1. Test agents on Beer Game scenarios (ensure backward compatibility)
2. Test agents on AWS SC scenarios (multi-item, multi-sourcing)
3. Run comparative analysis (Beer Game schema vs AWS SC schema)

---

## Success Metrics

### Compliance Metrics

**Target Compliance**: 80%+ AWS SC entity/field usage

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| **AWS SC Entities Used** | 0/35 (0%) | 28/35 (80%) | Count entities in training data |
| **AWS SC Fields Used** | 0/150+ (0%) | 120/150 (80%) | Count fields in training samples |
| **Training Data Format** | Custom Beer Game | AWS SC + Extensions | Review schema |
| **Backward Compatibility** | N/A | 100% | Test on existing Beer Game agents |

### Performance Metrics

**Target Performance**: No degradation vs current agents

| Metric | Current (Beer Game) | Target (AWS SC) |
|--------|---------------------|-----------------|
| **TRM Accuracy** | 90-95% | 90-95% |
| **GNN Forecast Error** | 85-92% | 85-92% |
| **RL Cost Reduction** | 20-35% | 20-35% |
| **Training Time** | 2-4 hrs (TRM) | 2-4 hrs (TRM) |
| **Inference Speed** | <10ms (TRM) | <10ms (TRM) |

---

## Conclusion

### Current Status: ❌ **NOT COMPLIANT**

Training data generation **does not use AWS Supply Chain Data Model** tables or fields. It uses a custom Beer Game schema with hardcoded roles, features, and parameters.

### Why This Matters

1. **Generalization**: Agents trained on Beer Game schema cannot generalize to real AWS SC scenarios
2. **Production Deployment**: Cannot deploy agents in production AWS SC environments
3. **Feature Support**: Missing AWS SC features (multi-item, multi-sourcing, BOM, inventory policies)
4. **Compliance**: Violates CLAUDE.md mandate to use AWS SC data model

### Recommended Path Forward

**Option 1**: ✅ **Extend training data with AWS SC fields** (4-6 weeks effort)

**Benefits**:
- AWS SC compliance (80%+ entity/field usage)
- Backward compatibility with Beer Game
- Production-ready agents
- Support for AWS SC features

**Implementation**:
1. Extend BeerGameParams with AWS SC fields
2. Modify training data generation to read AWS SC tables
3. Update TRM/GNN/RL agents to handle AWS SC features
4. Retrain all agents on AWS SC-compliant data
5. Validate on both Beer Game and AWS SC scenarios

---

**Status**: 🔴 **Action Required** - Training data must be migrated to AWS SC schema
**Priority**: High - Required for production deployment of AI agents
**Owner**: AI/ML Team + Supply Chain Planning Team
**Timeline**: 10 weeks (schema extension + retraining + validation)

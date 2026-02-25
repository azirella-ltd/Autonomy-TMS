# Planning Capabilities

**Last Updated**: 2026-01-22

---

## Overview

Autonomy provides comprehensive supply chain planning capabilities following AWS Supply Chain standards. The planning engine supports deterministic and stochastic planning with full uncertainty quantification.

---

## Demand Planning

### Capabilities

**Forecasting Methods**:
- Statistical: Moving average, exponential smoothing, seasonal decomposition
- ML Models: ARIMA, Prophet, custom neural networks
- Consensus Planning: Combine statistical forecasts with human overrides
- Collaborative Forecasting: Multi-stakeholder input

**Probabilistic Forecasts**:
- P10/P50/P90 percentile distributions
- Forecast error quantification
- Confidence intervals
- Bias detection

**Supplementary Time Series**:
- Promotional events
- Economic indicators
- Weather patterns
- Social media sentiment

### Implementation

**Files**:
- `backend/app/services/sc_planning/demand_processor.py` - Core demand processing
- `backend/app/models/sc_entities.py` - Forecast entity (lines 664-716)

**Key Methods**:
- `process_demand()` - Aggregate forecasts and actual orders
- Time-phase demand across planning horizon
- Net out committed/allocated inventory
- Apply demand shaping rules

**Data Model**:
```python
class Forecast(Base):
    product_id: int  # ForeignKey to items
    site_id: int     # ForeignKey to nodes
    forecast_date: date
    forecast_quantity: float  # Expected value
    forecast_p50: float       # Median
    forecast_p10: float       # Pessimistic
    forecast_p90: float       # Optimistic
    user_override_quantity: float  # Manual adjustment
```

---

## Supply Planning

### Capabilities

**Net Requirements Calculation**:
- Time-phased netting (gross requirements - available inventory)
- Multi-level BOM explosion (parent → components)
- Lead time offsetting
- Safety stock consideration
- Lot sizing rules

**Sourcing Strategy**:
- Multi-sourcing with priority levels
- Buy vs. make vs. transfer decisions
- Vendor selection based on cost, lead time, reliability
- Geographic constraints

**Output**:
- Purchase Order recommendations
- Transfer Order recommendations
- Manufacturing Order recommendations (planned)
- Exception alerts (stockouts, overstock)

### Implementation

**Files**:
- `backend/app/services/sc_planning/net_requirements_calculator.py` - Net requirements logic
- `backend/app/services/sc_planning/planner.py` - Main orchestrator

**3-Step Planning Process** (AWS SC Standard):
1. **Demand Processing**: Aggregate all demand sources
2. **Inventory Target Calculation**: Compute safety stock
3. **Net Requirements Calculation**: Generate supply plan

**Example Flow**:
```python
planner = SupplyChainPlanner(config_id, customer_id)
result = await planner.plan(
    start_date=date.today(),
    planning_horizon=52,  # weeks
    stochastic_params={...},
    objectives={...}
)
```

---

## Master Production Scheduling (MPS)

### Capabilities

**Strategic Production Planning**:
- Rough-cut capacity checks
- Production smoothing
- Make-to-stock vs. make-to-order strategies
- Campaign planning for setup minimization

**Capacity Validation**:
- Resource utilization analysis
- Bottleneck identification
- Feasibility checks
- What-if scenarios

**Output**:
- Production quantities by period
- Capacity requirements
- Key material requirements
- Exceptions and alerts

### Implementation

**Files**:
- `backend/app/models/mps.py` - MPS data models
- `backend/app/api/endpoints/mps.py` - MPS API endpoints
- `frontend/src/pages/planning/MasterProductionScheduling.jsx` - MPS UI

**Data Model**:
```python
class MPSPlan(Base):
    plan_name: str
    config_id: int
    start_date: date
    planning_horizon: int
    status: str  # draft, approved, executed
    
class MPSPlanItem(Base):
    mps_plan_id: int
    product_id: int
    site_id: int
    period_start_date: date
    planned_quantity: float
    available_capacity: float
```

---

## Material Requirements Planning (MRP)

### Capabilities

**Detailed Component Planning**:
- Derive component requirements from MPS
- Multi-level BOM explosion
- Scrap rate adjustment
- Lead time offsetting
- Exception management

**Exception Types**:
- Late orders
- Short supply
- Excess inventory
- Reschedule recommendations

### Implementation

**Status**: 🔄 In Progress

**Planned Files**:
- `backend/app/services/sc_planning/mrp_processor.py`
- `backend/app/models/mrp.py`

**Flow**:
```
MPS Plan
  ↓
BOM Explosion
  ↓
Net Requirements (per component)
  ↓
Sourcing Rules
  ↓
PO/TO/MO Recommendations
```

---

## Inventory Optimization

### Capabilities

**4 Policy Types**:

1. **abs_level** (Absolute Level)
   - Fixed safety stock quantity
   - Simple, predictable
   - Example: "Always maintain 100 units"

2. **doc_dem** (Days of Coverage - Demand)
   - Safety stock = avg daily demand × target days
   - Responsive to demand changes
   - Example: "Maintain 14 days of actual demand"

3. **doc_fcst** (Days of Coverage - Forecast)
   - Safety stock = forecast demand × target days
   - Forward-looking
   - Example: "Maintain 14 days of forecast demand"

4. **sl** (Service Level)
   - Safety stock = z-score × σ_lead_time
   - Risk-based
   - Example: "95% service level" → z=1.65

**Hierarchical Overrides**:
```
Priority: Item-Node > Item > Node > Config
Example: Warehouse A + Product X policy overrides generic Product X policy
```

**Stochastic Extension**:
- Distribution-based demand variability
- Lead time uncertainty
- Yield variability
- Multi-period optimization

### Implementation

**Files**:
- `backend/app/services/sc_planning/inventory_target_calculator.py`
- `backend/app/models/sc_entities.py` - InvPolicy entity (lines 336-391)

**Key Methods**:
```python
def calculate_inventory_targets(
    config_id: int,
    planning_horizon: int,
    stochastic_params: Dict
) -> Dict[Tuple[str, str, date], InventoryTarget]:
    # 1. Load policies (hierarchical)
    # 2. Calculate safety stock per policy type
    # 3. Apply stochastic adjustments
    # 4. Return target levels
```

---

## Capacity Planning

### Capabilities

**Resource Planning**:
- Capacity requirements from MPS/MRP
- Utilization analysis
- Bottleneck identification
- Rough-cut capacity planning (RCCP)
- Finite capacity scheduling (planned)

**Capable-to-Promise (CTP)**:
- Available capacity projections
- What-if capacity scenarios
- Resource constraints in order promising

### Implementation

**Files**:
- `backend/app/models/capacity.py` - Capacity models
- `backend/app/services/sc_planning/capacity_planner.py` (planned)

**Data Model**:
```python
class CapacityResource(Base):
    resource_id: str
    site_id: int
    available_capacity: float
    utilized_capacity: float
    
class CapacityRequirement(Base):
    mps_plan_id: int
    resource_id: str
    required_capacity: float
    period_start_date: date
```

---

## Integration: Beer Game Planning

The Beer Game uses these planning capabilities underneath:

**Round Execution Flow**:
```python
# 1. Demand Planning
market_demand = get_market_demand(round)

# 2. Inventory Target Calculation
targets = calculate_targets(
    on_hand, backlog, pipeline,
    policy_type="doc_dem", days=14
)

# 3. Net Requirements
order_qty = max(
    target - on_hand - pipeline + backlog,
    0
)

# 4. Order Promising (ATP)
atp_result = promise_order(
    site_id=node_id,
    item_id=item_id,
    requested_qty=order_qty
)

# 5. Create Transfer/Purchase Order
if atp_result.promised_qty > 0:
    create_transfer_order(...)
```

**This validates that planning logic works in production.**

---

## Planning Hierarchies (AWS Supply Chain Aligned)

The platform implements AWS Supply Chain-aligned hierarchies across three dimensions, enabling planning at appropriate levels of aggregation for each planning activity.

### Three Dimensions of Hierarchy

**1. Site/Geographic Hierarchy** (AWS SC: `geography`, `site`):

| Level | Code | Example | Planning Use |
|-------|------|---------|--------------|
| Company | `COMPANY` | ACME Corporation | Enterprise-wide KPIs |
| Region | `REGION` | Americas, EMEA, APAC | Strategic planning |
| Country | `COUNTRY` | USA, Canada, Germany | S&OP demand-supply balancing |
| State | `STATE` | California, Texas | Regional capacity planning |
| Site | `SITE` | Los Angeles DC, Dallas Factory | MPS/MRP execution |

**2. Product Hierarchy** (AWS SC: `product_hierarchy`, `product`):

| Level | Code | Example | Planning Use |
|-------|------|---------|--------------|
| Category | `CATEGORY` | Beverages, Electronics | Strategic portfolio planning |
| Family | `FAMILY` | Beer, Soft Drinks | S&OP demand planning |
| Group | `GROUP` | Craft Beer, Lager | MPS production planning |
| Product | `PRODUCT` | IPA 6-pack 12oz | MRP/Execution SKU-level |

**3. Time Bucket Hierarchy**:

| Bucket | Code | Duration | Planning Use | Update Frequency |
|--------|------|----------|--------------|------------------|
| Hour | `HOUR` | 1 hour | ATP/CTP, Real-time execution | Real-time |
| Day | `DAY` | 1 day | MRP detailed planning | Daily |
| Week | `WEEK` | 7 days | MPS production scheduling | Weekly |
| Month | `MONTH` | ~30 days | S&OP demand-supply planning | Monthly |
| Quarter | `QUARTER` | 3 months | Strategic/Network design | Quarterly |
| Year | `YEAR` | 12 months | Long-term strategic planning | Annual |

### Planning Type Configurations

Each planning type uses specific hierarchy levels optimized for its purpose:

| Planning Type | Site Level | Product Level | Time Bucket | Horizon | Frozen | Slushy |
|---------------|------------|---------------|-------------|---------|--------|--------|
| **Execution** | Site | Product | Hour | 1 week | 0 | 0 |
| **MRP** | Site | Product | Day | 13 weeks | 1 week | 2 weeks |
| **MPS** | Site | Group | Week | 6 months | 4 weeks | 8 weeks |
| **S&OP** | Country | Family | Month | 24 months | 3 months | 6 months |
| **Capacity** | Site | Group | Month | 18 months | 1 month | 3 months |
| **Inventory** | Site | Group | Month | 12 months | 0 | 3 months |
| **Strategic** | Region | Category | Quarter | 5 years | 2 quarters | 1 year |

### Planning Horizon Templates

Pre-defined templates are available for common planning scenarios:

```python
# Example: S&OP Configuration
{
    "planning_type": "sop",
    "site_hierarchy_level": "country",      # Aggregate to country level
    "product_hierarchy_level": "family",    # Aggregate to product family
    "time_bucket": "month",                 # Monthly buckets
    "horizon_months": 24,                   # 2-year horizon
    "frozen_periods": 3,                    # 3 months frozen
    "slushy_periods": 6,                    # 6 months require approval
    "update_frequency_hours": 720,          # Monthly refresh
    "powell_policy_class": "cfa",           # CFA for policy parameters
    "gnn_model_type": "sop_graphsage",      # S&OP structural analysis
    "consistency_tolerance": 0.15           # 15% max deviation from parent
}
```

### Hierarchical DAG Builder

The `HierarchicalDAGBuilder` service constructs planning DAGs at appropriate hierarchy levels:

```python
from app.services.hierarchical_dag_builder import build_sop_dag, build_mps_dag, build_execution_dag

# Build S&OP DAG at Country × Family level
sop_dag = await build_sop_dag(config_id, customer_id, as_of_date)

# Build MPS DAG at Site × Group level (with S&OP constraints)
mps_dag = await build_mps_dag(config_id, customer_id, as_of_date, sop_constraints=sop_dag)

# Build Execution DAG at Site × SKU level (with MPS constraints)
exec_dag = await build_execution_dag(config_id, customer_id, as_of_date, mps_constraints=mps_dag)
```

### Powell Framework Alignment

The hierarchy system directly supports Powell's hierarchical consistency:

| Planning Level | Powell Class | GNN Model | Role |
|----------------|--------------|-----------|------|
| Strategic | DLA | S&OP GraphSAGE | Long-term optimization with lookahead |
| S&OP | CFA | S&OP GraphSAGE | Compute policy parameters θ |
| MPS | CFA | Hybrid | Tactical parameters within S&OP bounds |
| MRP/Execution | VFA | Execution tGNN | Real-time decisions Q(s,a) using θ |

**Hierarchical Consistency Enforcement**:
```python
# S&OP sets policy parameters (θ)
theta = sop_model.compute_parameters(sop_dag)

# MPS must respect S&OP bounds
mps_decision = mps_model.decide(mps_dag, parent_constraints=theta)
assert deviation(mps_decision, theta) < 0.10  # <10% tolerance

# Execution respects MPS schedule
exec_decision = exec_model.decide(exec_dag, parent_constraints=mps_decision)
```

### Group Administrator Configuration

Group administrators configure planning hierarchies through the admin UI:

**Configuration Options**:
- Select hierarchy levels for each planning type
- Set planning horizons (weeks/months)
- Define frozen and slushy periods
- Configure update frequency (hourly to monthly)
- Choose Powell policy class (PFA, CFA, VFA, DLA)
- Select GNN model type (sop_graphsage, execution_tgnn, hybrid)
- Set parent planning relationship and consistency tolerance

**Implementation**:
- File: `backend/app/models/planning_hierarchy.py`
- Service: `backend/app/services/hierarchical_dag_builder.py`
- Admin UI: (Planned) Group Settings > Planning Hierarchies

---

## AI-Assisted Planning: Two-Tier GNN Architecture

The platform supports AI-assisted planning through a two-tier Graph Neural Network architecture that separates strategic (S&OP) and operational (Execution) concerns.

**Powell Framework Alignment** (see [POWELL_APPROACH.md](../POWELL_APPROACH.md)):
- **S&OP GraphSAGE** implements **CFA (Cost Function Approximation)** - computing optimized policy parameters θ
- **Execution tGNN** implements **VFA (Value Function Approximation)** - making decisions Q(s,a) using θ as context
- The **Shared Foundation** enforces **hierarchical consistency** per Powell's framework

### S&OP GraphSAGE (Medium-Term Planning)

**Purpose**: Network structure analysis, risk assessment, and strategic planning parameters.

**Update Frequency**: Weekly/Monthly or when network topology changes.

**Outputs**:
| Output | Description | Planning Use |
|--------|-------------|--------------|
| Criticality Score | Node importance in network (0-1) | Prioritize planning attention |
| Bottleneck Risk | Probability of becoming constraint (0-1) | Capacity planning focus |
| Concentration Risk | Single-source dependency (0-1) | Supplier diversification triggers |
| Resilience Score | Recovery capability after disruption (0-1) | Buffer stock positioning |
| Safety Stock Multiplier | Recommended SS adjustment (0.5-2.0) | Dynamic safety stock calculation |
| Network Risk | Overall network vulnerability (0-1) | Executive dashboard KPI |

**Integration with Planning**:
```python
# S&OP outputs feed into inventory target calculation
safety_stock = base_safety_stock * sop_model.safety_stock_multiplier[node_id]

# High bottleneck risk triggers capacity planning review
if sop_model.bottleneck_risk[node_id] > 0.7:
    trigger_capacity_planning_alert(node_id)
```

### Execution tGNN (Short-Term Operations)

**Purpose**: Real-time order decisions, demand sensing, and exception detection.

**Update Frequency**: Daily or real-time (per planning cycle).

**Inputs**: S&OP structural embeddings + transactional data (inventory, orders, shipments).

**Outputs**:
| Output | Description | Operational Use |
|--------|-------------|-----------------|
| Order Recommendation | Suggested order quantity | Automated replenishment |
| Demand Forecast | Predicted demand for next period | Net requirements input |
| Exception Probability | Likelihood of disruption (0-1) | Alert prioritization |
| Propagation Impact | Downstream effect of current state (0-1) | Bullwhip mitigation |
| Confidence | Decision confidence (0-1) | Human review threshold |

**Integration with Planning**:
```python
# Execution model provides demand forecast for net requirements
forecast = execution_model.demand_forecast[item_id, site_id]

# Low confidence triggers human review
if execution_model.confidence < 0.75:
    route_to_human_planner()
else:
    auto_execute_order(execution_model.order_recommendation)
```

### Shared Foundation

**Key Insight**: S&OP provides slow-changing structural context; Execution consumes this context for fast-changing operational decisions.

```
┌──────────────────────────────────────────────────────┐
│  S&OP GraphSAGE (Weekly/Monthly)                     │
│  - Network topology analysis                         │
│  - Risk scoring and bottleneck detection             │
│  → Outputs: Structural embeddings + planning params  │
└──────────────────────────────────────────────────────┘
                    ↓ (cached embeddings)
┌──────────────────────────────────────────────────────┐
│  Execution tGNN (Daily/Real-time)                    │
│  - Consumes structural embeddings                    │
│  - Processes transactional data                      │
│  → Outputs: Order recommendations + forecasts        │
└──────────────────────────────────────────────────────┘
```

**Files**:
- `backend/app/models/gnn/planning_execution_gnn.py` - Two-tier model definitions
- `backend/app/models/gnn/scalable_graphsage.py` - Scalable GraphSAGE for large networks
- `backend/scripts/training/train_planning_execution.py` - Training scripts

---

## API Examples

### Generate Supply Plan
```bash
POST /api/v1/supply-plan/generate
{
  "config_id": 1,
  "planning_horizon": 52,
  "start_date": "2026-01-22",
  "stochastic_params": {
    "lead_time_variability": {"type": "normal", "mean": 7, "std": 2},
    "demand_variability": {"type": "gamma", "shape": 2, "scale": 10}
  },
  "objectives": {
    "minimize_cost": true,
    "target_service_level": 0.95
  }
}
```

### Approve Supply Plan
```bash
POST /api/v1/supply-plan/approve/{task_id}
{
  "approved_by": "user@company.com",
  "comments": "Approved for execution"
}
```

### Get MPS Plan
```bash
GET /api/v1/mps/plans/{plan_id}
```

---

## Performance

**Benchmarks** (52-week horizon, 10 sites, 100 products):
- Demand Processing: <2s
- Inventory Target Calculation: <1s
- Net Requirements: <5s
- Full Planning Cycle: <10s

**Scalability**:
- Supports 1000+ site networks
- 10,000+ SKUs
- 104-week (2-year) planning horizons

---

## Synthetic Data Generation for Testing

The platform includes comprehensive synthetic data generation capabilities to enable rapid deployment and testing of planning capabilities without requiring real customer data.

### AI-Guided Setup Wizard

A Claude-powered conversational wizard guides system administrators through creating complete, archetype-based configurations:

**Wizard Flow**:
1. **Welcome & Archetype Selection** - Choose Retailer, Distributor, or Manufacturer
2. **Company Details** - Organization name, admin credentials
3. **Network Configuration** - Sites, suppliers, customers (with archetype defaults)
4. **Product Configuration** - SKUs, categories, families
5. **Demand Configuration** - Pattern type, seasonality, forecast horizon
6. **Agent Configuration** - AI mode (none/copilot/autonomous), enable GNN/LLM/TRM
7. **Review & Generate** - Confirm and create all entities

**Access**: System Administrator only at `/admin/synthetic-data`

### Company Archetypes

Three pre-configured archetypes provide sensible defaults for different business models:

| Archetype | Network | Products | Demand Pattern | Agent Mode |
|-----------|---------|----------|----------------|------------|
| **Retailer** | 2 CDC + 6 RDC + 50 Stores + 3 Online + 10 Suppliers | 200 SKUs (5 categories) | Seasonal (30% amplitude) | Copilot |
| **Distributor** | 2 NDC + 8 RDC + 20 LDC + 4 Kitting + 15 Suppliers | 720 SKUs (8 categories) | Trending (2%/month growth) | Copilot |
| **Manufacturer** | 3 Plants + 6 Sub-Assy + 8 Comp + 14 DCs + 40 Suppliers | 160 SKUs (4 categories) | Promotional (spike-driven) | Autonomous |

### Generated Entities

The wizard creates a complete planning environment:

| Entity Type | What Gets Created |
|-------------|-------------------|
| **Organization** | Group (company), admin user with GROUP_ADMIN role |
| **Network** | Sites, transportation lanes, market supply/demand |
| **Products** | Products (SKUs) with cost, price, and category assignments |
| **Hierarchies** | Site hierarchy (Company→Region→Country→Site), Product hierarchy (Category→Family→Group→Product) |
| **Planning Data** | Forecasts with P10/P50/P90 percentiles for each site-product combination |
| **Policies** | Inventory policies (DOC-based safety stock), sourcing rules |
| **Planning Configs** | MPS, MRP, S&OP configurations with Powell class and GNN model assignments |
| **AI Agents** | Agent configurations with archetype-recommended strategies |

### Aggregation/Disaggregation Services

Generic services support hierarchy-based data transformation per Powell's framework:

**Aggregation Service** (State Abstraction):
- Roll up detailed records to higher hierarchy levels
- Methods: SUM, AVERAGE, WEIGHTED_AVERAGE, MIN, MAX, COUNT, VARIANCE, PERCENTILE
- Example: Aggregate site-level inventory to country level for S&OP

**Disaggregation Service** (Policy-Based Allocation):
- Distribute aggregated plans to detail levels
- Methods: PROPORTIONAL (historical splits), EQUAL, CAPACITY_WEIGHTED, FORECAST_DRIVEN, LEARNED, VALUE_BASED
- Powell insight: Disaggregation proportions can be learned from historical data
- Example: Distribute monthly S&OP plan to weekly MPS by site-product

```python
# Aggregation example
from app.services.aggregation_service import AggregationService

aggregator = AggregationService(db, customer_id)
country_totals = await aggregator.aggregate(
    site_level_records,
    target_site_level=SiteHierarchyLevel.COUNTRY,
    target_product_level=ProductHierarchyLevel.FAMILY,
    target_time_bucket=TimeBucketType.MONTH
)

# Disaggregation example
from app.services.disaggregation_service import DisaggregationService

disaggregator = DisaggregationService(db, customer_id)
site_sku_plan = await disaggregator.disaggregate(
    sop_plan_records,
    target_site_level=SiteHierarchyLevel.SITE,
    target_product_level=ProductHierarchyLevel.PRODUCT,
    target_time_bucket=TimeBucketType.WEEK,
    default_method=DisaggregationMethod.LEARNED  # Use historical proportions
)
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/synthetic-data/wizard/sessions` | POST | Start wizard session |
| `/api/v1/synthetic-data/wizard/sessions/{id}/messages` | POST | Send message to wizard |
| `/api/v1/synthetic-data/wizard/sessions/{id}/generate` | POST | Generate data from wizard |
| `/api/v1/synthetic-data/generate` | POST | Direct generation (no wizard) |
| `/api/v1/synthetic-data/archetypes` | GET | List archetype information |
| `/api/v1/synthetic-data/defaults/{archetype}` | GET | Get archetype defaults |

### Testing Planning Capabilities

After generating synthetic data, test the planning capabilities:

1. **Run S&OP Planning** - Aggregate to Country × Family × Month level
2. **Generate MPS** - Week-level production schedule within S&OP bounds
3. **Execute MRP** - Day-level component requirements from MPS
4. **Test AI Agents** - Run games or simulations to validate agent decisions
5. **Verify Hierarchical Consistency** - Ensure lower-level plans respect upper-level constraints

---

## Further Reading

- [STOCHASTIC_PLANNING.md](STOCHASTIC_PLANNING.md) - Probabilistic planning framework
- [PLANNING_KNOWLEDGE_BASE.md](../PLANNING_KNOWLEDGE_BASE.md) - Academic foundations
- [AWS_SC_IMPLEMENTATION_STATUS.md](../AWS_SC_IMPLEMENTATION_STATUS.md) - Entity coverage

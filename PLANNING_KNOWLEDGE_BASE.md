# Planning Logic Knowledge Base

**Purpose**: Comprehensive reference for developing supply chain planning logic
**Last Updated**: 2026-01-18
**Status**: Living Document - Reference Before Implementing Planning Features

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Academic Foundations](#academic-foundations)
3. [Industry Implementations](#industry-implementations)
4. [Our Implementation Design](#our-implementation-design)
5. [Algorithms & Code Examples](#algorithms--code-examples)
6. [Best Practices](#best-practices)
7. [Testing & Validation](#testing--validation)
8. [References](#references)

---

## Quick Reference

### Key Design Documents

**Primary Planning Documents**:
- **[SUPPLY_PLAN_GENERATION_DESIGN.md](SUPPLY_PLAN_GENERATION_DESIGN.md)** - Probabilistic balanced scorecard design with Monte Carlo simulation
- **[AWS_SC_STOCHASTIC_MODELING_DESIGN.md](AWS_SC_STOCHASTIC_MODELING_DESIGN.md)** - Stochastic modeling framework (20 distribution types)
- **[AWS_SC_POLICY_TYPES_IMPLEMENTATION.md](AWS_SC_POLICY_TYPES_IMPLEMENTATION.md)** - 4 inventory policy types (abs_level, doc_dem, doc_fcst, sl)
- **[SUPPLY_PLANNING_VS_EXECUTION.md](SUPPLY_PLANNING_VS_EXECUTION.md)** - Planning vs. execution separation

**Knowledge Base PDFs** (in `docs/Knowledge/`):
- `01_MPS_Material_Requirements_Planning_Academic.pdf` (98KB) - MPS/MRP fundamentals
- `04_Kinaxis_Master_Production_Scheduling.pdf` (1.7MB) - Kinaxis MPS guide
- `06_Kinaxis_Capacity_Planning_Constraints.pdf` (1.8MB) - Capacity planning
- `08_Kinaxis_Inventory_Planning_Optimization.pdf` (832KB) - Inventory optimization
- `10_OMP_5_Planning_Strategies.pdf` (695KB) - MTO/MTS/ATO strategies
- `14_Stanford_Stochastic_Programming_Solutions.pdf` (588KB) - Stochastic programming
- `16-21_*Safety_Stock*.pdf` - Safety stock and inventory policies
- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB) - Sequential decision analytics

### Core Planning Principles

**1. Stochastic vs Deterministic Variables**:
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand
- **Control Variables** (deterministic): Inventory targets, costs, policies

**2. Hierarchical Override Logic**:
```
Item-Node > Item > Node > Config (most specific wins)
```

**3. Policy Types** (AWS SC Standard + Extensions):
- `abs_level`: Fixed safety stock quantity
- `doc_dem`: Days of coverage based on demand
- `doc_fcst`: Days of coverage based on forecast
- `sl`: Service level with z-score calculation
- `sl_fitted`: Service level with MLE-fitted distributions (Monte Carlo DDLT when non-Normal)
- `conformal`: Conformal Risk Control safety stock with distribution-free guarantee
- `sl_conformal_fitted`: Hybrid fitted + conformal
- `econ_optimal`: Marginal economic return — stock one more unit only when E[stockout_cost × P(demand>k)] > holding_cost

**4. Balanced Scorecard Perspectives**:
- **Financial**: Total cost, inventory carrying cost, cash-to-cash cycle
- **Customer**: OTIF, fill rate, backorder rate, service level
- **Operational**: Inventory turns, DOS, forecast accuracy, bullwhip ratio
- **Strategic**: Flexibility, sustainability, supplier reliability

---

## Academic Foundations

### 1. Master Production Scheduling (MPS)

**Source**: `docs/Knowledge/01_MPS_Material_Requirements_Planning_Academic.pdf`

**Key Concepts**:
- **Time Buckets**: Planning periods (daily, weekly, monthly)
- **Planning Horizon**: How far into future to plan (typically 12-52 weeks)
- **Frozen Zones**: Near-term periods where no changes allowed
- **Demand Netting**: Gross requirements - on-hand - scheduled receipts = net requirements
- **Lot Sizing Rules**:
  - EOQ (Economic Order Quantity)
  - LFL (Lot-for-Lot)
  - POQ (Periodic Order Quantity)
  - Fixed order quantity

**MRP Explosion Algorithm**:
```
For each period t in planning horizon:
    1. Calculate gross requirements (from demand + dependent demand)
    2. Calculate net requirements (gross - inventory - scheduled receipts)
    3. If net requirements > 0:
        a. Apply lot sizing rule → order quantity
        b. Offset by lead time → planned order release date
        c. Create planned order
    4. Update projected on-hand inventory
```

### 2. Stochastic Programming

**Source**: `docs/Knowledge/14_Stanford_Stochastic_Programming_Solutions.pdf`

**Key Concepts**:
- **Scenario Trees**: Represent possible future outcomes
- **Recourse Decisions**: Adaptive decisions based on realized uncertainty
- **Value of Stochastic Solution (VSS)**: Benefit of modeling uncertainty vs. deterministic
- **Two-Stage Stochastic Programming**:
  - Stage 1: Make decisions before uncertainty resolves (e.g., order quantities)
  - Stage 2: Make recourse decisions after observing outcomes (e.g., expedite, reschedule)

**Sample Average Approximation (SAA)**:
```
Minimize: E[f(x, ξ)]
where ξ is random parameter

Approximate with:
Minimize: (1/N) Σ f(x, ξ_i)  for i=1..N scenarios
```

**Chance Constraints**:
```
P(inventory ≥ demand) ≥ service_level
```

### 3. Safety Stock & Inventory Optimization

**Source**: `docs/Knowledge/17_MIT_Strategic_Safety_Stock_Placement.pdf`

**Newsvendor Model** (single-period):
```python
# Optimal order quantity
Q* = F^(-1)(Cu / (Cu + Co))

where:
  Cu = underage cost (lost profit)
  Co = overage cost (holding cost)
  F^(-1) = inverse CDF of demand distribution
```

**Multi-Echelon Safety Stock Placement**:
- **Push Strategy**: Hold safety stock upstream (cheaper holding cost)
- **Pull Strategy**: Hold safety stock downstream (better responsiveness)
- **Decoupling Points**: Strategic locations to buffer against uncertainty
- **Risk Pooling**: Aggregate demand at higher echelons reduces total safety stock

**Safety Stock Formula** (continuous review):
```python
SS = z × σ_LT × √(lead_time)

where:
  z = z-score for service level (e.g., 1.65 for 95%)
  σ_LT = standard deviation of demand during lead time
```

---

## Industry Implementations

### 1. Kinaxis RapidResponse

**Sources**:
- `docs/Knowledge/04_Kinaxis_Master_Production_Scheduling.pdf`
- `docs/Knowledge/06_Kinaxis_Capacity_Planning_Constraints.pdf`
- `docs/Knowledge/08_Kinaxis_Inventory_Planning_Optimization.pdf`

**Key Features**:
- **Real-time constraint checking**: Plans validated against capacity, material availability
- **What-if scenario analysis**: Compare multiple scenarios side-by-side
- **Constraint relaxation**: Automatically identify which constraints to relax
- **Integrated S&OP**: Demand, supply, inventory planned together
- **Planning time fence**: Near-term frozen, medium-term slushy, long-term flexible

**KPIs Tracked**:
- Forecast accuracy (MAPE, bias)
- Service level attainment (% orders filled on time)
- Inventory days of supply (DOS)
- Resource utilization (%)
- Plan nervousness (order changes per period)

**Planning Process**:
1. Load demand forecast
2. Generate MPS (master production schedule)
3. Check capacity constraints
4. Run MRP (material requirements planning)
5. Identify shortages and excesses
6. Iteratively adjust plan (orders, production, inventory targets)
7. Validate plan against constraints
8. Publish final plan

### 2. SAP IBP (Integrated Business Planning)

**Key Concepts**:
- **Consensus Forecasting**: Combine statistical forecast + sales input + market intelligence
- **S&OP Process**: Monthly cycle aligning demand, supply, finance
- **Forecast Value Added (FVA)**: Measure improvement over naive baseline
- **WMAPE (Weighted MAPE)**: Volume-weighted forecast accuracy
- **Risk Dashboard**: Identify risks in plan (low forecast accuracy, resource bottlenecks, excess CO2)

**Forecast Accuracy Metrics**:
```python
MAPE = (1/n) Σ |actual - forecast| / actual

WMAPE = Σ |actual - forecast| / Σ actual

Forecast Bias = Σ (actual - forecast) / Σ actual
```

### 3. OMP Unison Planning

**Source**: `docs/Knowledge/10_OMP_5_Planning_Strategies.pdf`

**5 Planning Strategies**:
1. **MTO (Make-to-Order)**: Produce only after customer order received
   - Low inventory, high responsiveness to custom requirements
   - Long lead times, high backlog risk

2. **MTS (Make-to-Stock)**: Produce to forecast, hold finished goods inventory
   - High inventory, low lead times
   - Risk of obsolescence if forecast inaccurate

3. **ATO (Assemble-to-Order)**: Hold component inventory, assemble after order
   - Balance inventory and responsiveness
   - Requires modular product design

4. **ETO (Engineer-to-Order)**: Custom design for each order
   - No standard inventory, longest lead times
   - Highest customization

5. **Hybrid**: Different strategies by product/customer segment
   - Fast movers: MTS
   - Slow movers: MTO
   - Configured products: ATO

**OEE (Overall Equipment Effectiveness)**:
```python
OEE = Availability × Performance × Quality

where:
  Availability = actual_runtime / planned_runtime
  Performance = actual_output / theoretical_max_output
  Quality = good_output / total_output
```

---

## Our Implementation Design

### 1. Stochastic Modeling Framework

**Document**: [AWS_SC_STOCHASTIC_MODELING_DESIGN.md](AWS_SC_STOCHASTIC_MODELING_DESIGN.md)

**21 Supported Distributions**:

| Distribution Type | Use Case | Parameters |
|-------------------|----------|------------|
| **Deterministic** | Fixed value (default) | `value` |
| **Uniform** | Equal probability in range | `min`, `max` |
| **Normal** | Symmetric variation | `mean`, `stddev` |
| **Truncated Normal** | Normal with bounds | `mean`, `stddev`, `min`, `max` |
| **Triangular** | Expert estimate | `min`, `mode`, `max` |
| **Lognormal** | Right-skewed (lead times) | `mean`, `stddev` |
| **Gamma** | Flexible right-skew | `shape`, `scale` |
| **Weibull** | Time-to-failure | `shape`, `scale` |
| **Exponential** | Memoryless events | `rate` |
| **Beta** | Bounded [0,1] for percentages | `alpha`, `beta` |
| **Poisson** | Discrete counts | `lambda` |
| **Binomial** | Successes in n trials | `n`, `p` |
| **Negative Binomial** | Overdispersed Poisson | `r`, `p` |
| **Empirical** | User-defined or historical | `values`, `probabilities` |
| **Log-Logistic** | Fat-tailed lead times | `alpha` (scale), `beta` (shape) |
| **Mixture** | Combined distributions | `distributions`, `weights` |
| **Categorical** | Named categories | `categories`, `probabilities` |

**JSON Schema Examples**:

```json
// Normal lead time with bounds
{
  "type": "normal",
  "mean": 7.0,
  "stddev": 1.5,
  "min": 3.0,
  "max": 12.0
}

// Beta yield distribution
{
  "type": "beta",
  "alpha": 95,
  "beta": 5,
  "min": 0.90,
  "max": 1.00
}

// Mixture: normal ops + disruptions
{
  "type": "mixture",
  "distributions": [
    {"type": "normal", "mean": 5, "stddev": 1},
    {"type": "normal", "mean": 15, "stddev": 2}
  ],
  "weights": [0.80, 0.20]
}

// Poisson demand
{
  "type": "poisson",
  "lambda": 4.5,
  "min": 0,
  "max": 20
}
```

**Variable Classification**:

✅ **Stochastic Operational Variables** (15):
- Material flow lead time
- Information flow lead time
- Lane capacity
- Manufacturing lead time
- Production cycle time
- Manufacturing yield
- Production capacity
- Setup time
- Changeover time
- Component scrap rate
- Sourcing lead time
- Vendor lead time
- Market demand
- Order aging/spoilage
- Demand forecast error

❌ **Deterministic Control Variables** (remain fixed):
- Inventory policies (target_qty, reorder_point, order_up_to_level)
- Financial parameters (holding_cost, backlog_cost, prices)
- Policy constraints (min_order_qty, max_order_qty)
- Planning parameters (frozen_horizon, planning_time_fence)

### 2. Policy Types (AWS SC Standard)

**Document**: [AWS_SC_POLICY_TYPES_IMPLEMENTATION.md](AWS_SC_POLICY_TYPES_IMPLEMENTATION.md)

**4 Standard Inventory Policies**:

#### Policy 1: abs_level (Absolute Level)
```python
def calculate_safety_stock_abs_level(policy):
    """Fixed safety stock quantity"""
    return policy.ss_quantity
```

**Example**: 50 units fixed safety stock
```json
{
  "ss_policy": "abs_level",
  "ss_quantity": 50.0
}
```

#### Policy 2: doc_dem (Days of Coverage - Demand)
```python
async def calculate_safety_stock_doc_dem(policy, product, site):
    """Safety stock based on historical demand"""
    avg_daily_demand = await calculate_avg_daily_demand(product, site)
    return policy.ss_days * avg_daily_demand
```

**Example**: 14 days of demand coverage
```json
{
  "ss_policy": "doc_dem",
  "ss_days": 14
}
```
If avg daily demand = 10 units → SS = 140 units

#### Policy 3: doc_fcst (Days of Coverage - Forecast)
```python
def calculate_safety_stock_doc_fcst(policy, forecast):
    """Safety stock based on forecast"""
    avg_daily_forecast = calculate_avg_daily_forecast(forecast)
    return policy.ss_days * avg_daily_forecast
```

**Example**: 21 days of forecast coverage
```json
{
  "ss_policy": "doc_fcst",
  "ss_days": 21
}
```
If avg daily forecast = 15 units → SS = 315 units

#### Policy 4: sl (Service Level)
```python
import math

async def calculate_safety_stock_sl(policy, product, site):
    """Probabilistic safety stock with z-score"""
    service_level = policy.service_level
    z_score = get_z_score(service_level)

    demand_std_dev = await calculate_demand_std_dev(product, site)
    lead_time = await get_replenishment_lead_time(product, site)

    return z_score * demand_std_dev * math.sqrt(lead_time)
```

**Z-Score Reference Table**:
| Service Level | Z-Score | Description |
|---------------|---------|-------------|
| 50% | 0.00 | Median |
| 80% | 0.84 | Standard |
| 90% | 1.28 | High |
| 95% | 1.65 | Very High |
| 98% | 2.05 | Premium |
| 99% | 2.33 | 3-sigma |
| 99.5% | 2.58 | Critical |

**Example**: 98% service level
```json
{
  "ss_policy": "sl",
  "service_level": 0.98
}
```
If σ = 20, lead_time = 7 days → SS = 2.05 × 20 × √7 = 108.5 units

### 3. Supply Plan Generation with Probabilistic Balanced Scorecard

**Document**: [SUPPLY_PLAN_GENERATION_DESIGN.md](SUPPLY_PLAN_GENERATION_DESIGN.md)

**High-Level Algorithm**:
```
Algorithm: Probabilistic Supply Plan Generation
-------------------------------------------------
Input:
  - Supply chain configuration (DAG topology)
  - Demand forecast with uncertainty
  - Lead time distributions
  - Business objectives (target cost, service level, etc.)
  - Planning horizon (e.g., 52 weeks)

Output:
  - Optimized supply plan (order quantities per node-period)
  - Probabilistic balanced scorecard

Steps:
  1. Generate N scenarios (N=1000) using Monte Carlo:
     - Sample demand from distribution
     - Sample lead times from distribution
     - Sample yields, capacities from distributions

  2. For each scenario i in 1..N:
     a. Run simulation with agent (TRM/GNN/LLM/PID)
     b. Record metrics: total_cost_i, OTIF_i, inventory_turns_i, etc.

  3. Aggregate results:
     - For each metric M:
       - Compute expected value: E[M] = mean(M_i)
       - Compute percentiles: P10, P50, P90
       - Compute probabilities: P(M > target)

  4. Optimize plan using stochastic programming:
     - Objective: Minimize E[Total Cost]
     - Constraints: P(OTIF > 95%) >= 0.90
                   P(Inventory < safety_stock) <= 0.05
     - Solve using SAA (Sample Average Approximation)

  5. Generate balanced scorecard with 4 perspectives:
     - Financial: E[Total Cost], P(Cost < Budget)
     - Customer: E[OTIF], P(OTIF > target)
     - Operational: E[Inventory Turns], E[DOS]
     - Strategic: E[Bullwhip], Supplier reliability

Return: Optimized plan + probabilistic scorecard
```

**Balanced Scorecard Metrics**:

| Perspective | Metrics | Probabilistic Output |
|-------------|---------|---------------------|
| **Financial** | • Total supply chain cost<br>• Inventory carrying cost<br>• Cash-to-cash cycle | • P(Cost < $X)<br>• Expected cost distribution<br>• Risk of exceeding budget |
| **Customer** | • OTIF (On-Time-In-Full)<br>• Fill rate<br>• Backorder rate | • P(OTIF > 95%)<br>• Expected service level<br>• Risk of stockout |
| **Operational** | • Inventory turnover<br>• Days of supply<br>• Forecast accuracy<br>• Bullwhip ratio | • P(Inventory turns > X)<br>• Expected DOS distribution<br>• P(Forecast error < Y%) |
| **Strategic** | • Supply chain flexibility<br>• Sustainability (CO2)<br>• Supplier reliability | • P(Response time < Z days)<br>• Expected CO2 emissions<br>• Supplier risk score |

**Agent Integration**:

| Agent Type | Use in Plan Generation | Speed | Accuracy |
|------------|------------------------|-------|----------|
| **TRM** | Fast scenario simulation (7M params) | <10ms/decision | 90-95% vs optimal |
| **GNN** | Deep learning inference (128M params) | ~100ms/decision | 85-92% vs optimal |
| **LLM** | Explainable AI + validation | ~2s/decision | Varies |
| **PID** | Baseline for comparison | <1ms/decision | 70-80% vs optimal |
| **Naive** | Benchmark (order = demand) | <1ms/decision | 40-50% vs optimal |

---

## Algorithms & Code Examples

### 1. Base Stock Policy

**Description**: Order up to target level every period

```python
def base_stock_policy(
    on_hand: float,
    on_order: float,
    target_inventory: float
) -> float:
    """
    Order quantity to bring inventory position to target

    Args:
        on_hand: Current inventory on hand
        on_order: Inventory already ordered (pipeline)
        target_inventory: Desired inventory position

    Returns:
        Order quantity (non-negative)
    """
    inventory_position = on_hand + on_order
    order_qty = max(0, target_inventory - inventory_position)
    return order_qty
```

**Use Case**: Products with stable demand, low ordering cost

### 2. (s,S) Policy (Min-Max)

**Description**: Order when inventory drops below reorder point s, order up to S

```python
def s_S_policy(
    on_hand: float,
    on_order: float,
    reorder_point: float,
    order_up_to_level: float
) -> float:
    """
    (s,S) policy: Order only when inventory position <= s, order up to S

    Args:
        on_hand: Current inventory on hand
        on_order: Inventory already ordered (pipeline)
        reorder_point: Reorder point (s)
        order_up_to_level: Order-up-to level (S)

    Returns:
        Order quantity (0 or positive)
    """
    inventory_position = on_hand + on_order

    if inventory_position <= reorder_point:
        order_qty = max(0, order_up_to_level - inventory_position)
        return order_qty
    else:
        return 0.0  # Don't order
```

**Use Case**: Products with high ordering cost (minimize order frequency)

### 3. Periodic Review Policy

**Description**: Review inventory at fixed intervals, order up to target

```python
def periodic_review_policy(
    on_hand: float,
    on_order: float,
    target_inventory: float,
    current_period: int,
    review_period: int = 7
) -> float:
    """
    Periodic review: Order only every review_period periods

    Args:
        on_hand: Current inventory on hand
        on_order: Inventory already ordered (pipeline)
        target_inventory: Target inventory level
        current_period: Current time period
        review_period: Review interval (e.g., 7 days = weekly)

    Returns:
        Order quantity (0 or positive)
    """
    if current_period % review_period == 0:
        # Review period: order up to target
        inventory_position = on_hand + on_order
        order_qty = max(0, target_inventory - inventory_position)
        return order_qty
    else:
        # Not a review period: don't order
        return 0.0
```

**Use Case**: Coordinated ordering (e.g., weekly truck deliveries)

### 4. Safety Stock Calculation

**Description**: Calculate safety stock for given service level

```python
import math
from scipy.stats import norm

def calculate_safety_stock(
    service_level: float,
    demand_std_dev: float,
    lead_time_days: float
) -> float:
    """
    Calculate safety stock using service level approach

    Args:
        service_level: Target service level (0.95 = 95%)
        demand_std_dev: Standard deviation of daily demand
        lead_time_days: Replenishment lead time in days

    Returns:
        Safety stock quantity
    """
    # Get z-score for service level
    z_score = norm.ppf(service_level)

    # Safety stock = z × σ_demand × √(lead_time)
    safety_stock = z_score * demand_std_dev * math.sqrt(lead_time_days)

    return max(0, safety_stock)

# Example usage
ss = calculate_safety_stock(
    service_level=0.95,      # 95% service level
    demand_std_dev=20.0,     # Daily demand std dev
    lead_time_days=7.0       # 1 week lead time
)
# Result: ss ≈ 1.65 × 20 × √7 ≈ 87.3 units
```

### 5. Distribution Sampling

**Description**: Sample from stochastic distributions

```python
import numpy as np
from scipy import stats

class DistributionSampler:
    """Sample values from JSON distribution specifications"""

    def __init__(self, dist_spec: dict, seed: int = None):
        self.dist_spec = dist_spec
        self.dist_type = dist_spec["type"]
        self.rng = np.random.default_rng(seed)

    def sample(self, size: int = 1):
        """Draw sample(s) from the distribution"""

        if self.dist_type == "deterministic":
            value = self.dist_spec["value"]
            return value if size == 1 else np.full(size, value)

        elif self.dist_type == "normal":
            mean = self.dist_spec["mean"]
            stddev = self.dist_spec["stddev"]
            samples = self.rng.normal(mean, stddev, size)

            # Apply bounds
            if "min" in self.dist_spec:
                samples = np.maximum(samples, self.dist_spec["min"])
            if "max" in self.dist_spec:
                samples = np.minimum(samples, self.dist_spec["max"])

            return samples[0] if size == 1 else samples

        elif self.dist_type == "lognormal":
            # Lognormal parameterization
            mean = self.dist_spec["mean"]
            stddev = self.dist_spec["stddev"]

            # Convert to lognormal parameters
            mu = np.log(mean**2 / np.sqrt(mean**2 + stddev**2))
            sigma = np.sqrt(np.log(1 + (stddev**2 / mean**2)))

            samples = self.rng.lognormal(mu, sigma, size)

            # Apply bounds
            if "min" in self.dist_spec:
                samples = np.maximum(samples, self.dist_spec["min"])
            if "max" in self.dist_spec:
                samples = np.minimum(samples, self.dist_spec["max"])

            return samples[0] if size == 1 else samples

        elif self.dist_type == "poisson":
            lambda_param = self.dist_spec["lambda"]
            samples = self.rng.poisson(lambda_param, size)

            # Apply bounds
            if "min" in self.dist_spec:
                samples = np.maximum(samples, self.dist_spec["min"])
            if "max" in self.dist_spec:
                samples = np.minimum(samples, self.dist_spec["max"])

            return samples[0] if size == 1 else samples

        elif self.dist_type == "beta":
            alpha = self.dist_spec["alpha"]
            beta_param = self.dist_spec["beta"]

            # Beta distribution [0,1]
            samples = self.rng.beta(alpha, beta_param, size)

            # Scale to [min, max]
            if "min" in self.dist_spec and "max" in self.dist_spec:
                min_val = self.dist_spec["min"]
                max_val = self.dist_spec["max"]
                samples = min_val + samples * (max_val - min_val)

            return samples[0] if size == 1 else samples

        elif self.dist_type == "mixture":
            # Mixture of distributions
            distributions = self.dist_spec["distributions"]
            weights = self.dist_spec["weights"]

            # Choose distribution for each sample
            choices = self.rng.choice(
                len(distributions),
                size=size,
                p=weights
            )

            samples = np.zeros(size)
            for i in range(size):
                chosen_dist = distributions[choices[i]]
                sampler = DistributionSampler(chosen_dist, seed=None)
                samples[i] = sampler.sample(1)

            return samples[0] if size == 1 else samples

        else:
            raise ValueError(f"Unknown distribution type: {self.dist_type}")

# Example usage
lead_time_dist = {
    "type": "lognormal",
    "mean": 7.0,
    "stddev": 2.0,
    "min": 3.0,
    "max": 14.0
}

sampler = DistributionSampler(lead_time_dist, seed=42)
lead_time_samples = sampler.sample(size=100)
print(f"Mean: {lead_time_samples.mean():.2f}")
print(f"Std: {lead_time_samples.std():.2f}")
```

### 6. Monte Carlo Simulation for Plan Generation

```python
import numpy as np
from typing import List, Dict

async def generate_probabilistic_plan(
    config_id: int,
    objectives: dict,
    num_scenarios: int = 1000,
    agent_strategy: str = "trm"
) -> Dict:
    """
    Generate supply plan using Monte Carlo simulation

    Args:
        config_id: Supply chain configuration ID
        objectives: Business objectives (target cost, service level, etc.)
        num_scenarios: Number of Monte Carlo scenarios
        agent_strategy: Agent type (trm, gnn, llm, pid)

    Returns:
        Dict with optimized plan and probabilistic balanced scorecard
    """
    # Load configuration
    config = await load_supply_chain_config(config_id)

    # Initialize results storage
    scenario_results = []

    # Monte Carlo simulation
    for i in range(num_scenarios):
        # 1. Sample stochastic parameters
        demand_scenario = sample_demand_distribution(config, objectives.planning_horizon)
        lead_time_scenario = sample_lead_times(config)
        yield_scenario = sample_yields(config)

        # 2. Run simulation with agent
        agent = get_agent(agent_strategy)
        simulator = SupplyChainSimulator(config, agent)

        # 3. Simulate planning horizon
        for t in range(objectives.planning_horizon):
            simulator.tick(
                demand=demand_scenario[:, t],
                lead_times=lead_time_scenario,
                yields=yield_scenario
            )

        # 4. Collect metrics
        metrics = {
            "total_cost": simulator.get_total_cost(),
            "otif": simulator.get_otif(),
            "fill_rate": simulator.get_fill_rate(),
            "inventory_turns": simulator.get_inventory_turns(),
            "bullwhip_ratio": simulator.get_bullwhip_ratio(),
            "orders": simulator.get_order_history()
        }
        scenario_results.append(metrics)

        # Update progress
        if (i+1) % 100 == 0:
            print(f"Completed {i+1}/{num_scenarios} scenarios")

    # 5. Aggregate into balanced scorecard
    balanced_scorecard = compute_balanced_scorecard(scenario_results, objectives)

    # 6. Optimize plan
    optimized_plan = optimize_plan_saa(scenario_results, objectives)

    return {
        "optimized_plan": optimized_plan,
        "balanced_scorecard": balanced_scorecard,
        "scenario_results": scenario_results
    }

def compute_balanced_scorecard(
    scenario_results: List[Dict],
    objectives: dict
) -> Dict:
    """Aggregate scenario results into probabilistic balanced scorecard"""

    # Extract metrics
    total_costs = [s["total_cost"] for s in scenario_results]
    otif_values = [s["otif"] for s in scenario_results]
    inventory_turns = [s["inventory_turns"] for s in scenario_results]

    scorecard = {
        "financial": {
            "total_cost": {
                "expected": np.mean(total_costs),
                "p10": np.percentile(total_costs, 10),
                "p50": np.percentile(total_costs, 50),
                "p90": np.percentile(total_costs, 90),
                "probability_under_budget": np.mean([
                    c < objectives.budget_limit
                    for c in total_costs
                ]),
                "distribution": total_costs
            }
        },
        "customer": {
            "otif": {
                "expected": np.mean(otif_values),
                "p10": np.percentile(otif_values, 10),
                "p50": np.percentile(otif_values, 50),
                "p90": np.percentile(otif_values, 90),
                "probability_above_target": np.mean([
                    otif > objectives.service_level_target
                    for otif in otif_values
                ]),
                "distribution": otif_values
            }
        },
        "operational": {
            "inventory_turns": {
                "expected": np.mean(inventory_turns),
                "p10": np.percentile(inventory_turns, 10),
                "p50": np.percentile(inventory_turns, 50),
                "p90": np.percentile(inventory_turns, 90),
                "distribution": inventory_turns
            }
        }
    }

    return scorecard
```

---

## Best Practices

### 1. Stochastic Modeling

**DO**:
- ✅ Use stochastic distributions for **operational variables** (lead times, yields, demand)
- ✅ Use deterministic values for **control variables** (inventory targets, costs)
- ✅ Run 100+ scenarios for reliable probability distributions
- ✅ Use variance reduction techniques (common random numbers, antithetic variates)
- ✅ Validate distribution parameters against historical data
- ✅ Document all distribution choices and assumptions

**DON'T**:
- ❌ Don't make inventory policies stochastic (they are decisions, not uncertainties)
- ❌ Don't use <50 scenarios (unreliable probabilities)
- ❌ Don't ignore bounds (negative lead times, yields >100%)
- ❌ Don't forget to set random seeds for reproducibility

### 2. Policy Selection

**DO**:
- ✅ Use `abs_level` for products with known, stable requirements
- ✅ Use `doc_dem` for mature products with stable demand history
- ✅ Use `doc_fcst` for new products or products with changing demand
- ✅ Use `sl` for critical/high-value products requiring specific service levels
- ✅ Use `sl_fitted` when demand or lead time is non-Normal (lognormal, Weibull, etc.)
- ✅ Use `econ_optimal` when explicit economic trade-off optimization is desired (requires unit_cost, holding_rate, stockout_multiplier, ≥5 demand + ≥3 lead time observations)
- ✅ Respect hierarchical override logic (Item-Node > Item > Node > Config)

**DON'T**:
- ❌ Don't use `doc_dem` for new products (no demand history)
- ❌ Don't use `doc_fcst` if forecast accuracy <70%
- ❌ Don't set service level <80% or >99.5% (impractical extremes)
- ❌ Don't use `econ_optimal` without sufficient demand and lead time history
- ❌ Don't rely on fallback/default cost values — all economic parameters must be explicitly set per tenant
- ❌ Don't forget to validate safety stock calculations

### 3. Planning Horizon

**DO**:
- ✅ Use 13 weeks (1 quarter) for operational planning
- ✅ Use 26 weeks (6 months) for tactical planning
- ✅ Use 52 weeks (1 year) for strategic planning
- ✅ Freeze near-term periods (1-2 weeks) to avoid nervousness
- ✅ Update plans weekly or bi-weekly

**DON'T**:
- ❌ Don't plan too far out (>2 years unrealistic)
- ❌ Don't plan too short (<4 weeks insufficient visibility)
- ❌ Don't update plans daily (causes nervousness)

### 4. Balanced Scorecard

**DO**:
- ✅ Track all 4 perspectives (Financial, Customer, Operational, Strategic)
- ✅ Generate confidence intervals, not just point estimates
- ✅ Highlight when probability < confidence requirement
- ✅ Provide recommendations (e.g., "Increase safety stock by 8%")
- ✅ Compare multiple scenarios side-by-side

**DON'T**:
- ❌ Don't report only expected values (ignores risk)
- ❌ Don't ignore strategic metrics (flexibility, sustainability)
- ❌ Don't overwhelm users with 100+ metrics (focus on key KPIs)

### 5. Agent Selection

**DO**:
- ✅ Use **TRM** for fast scenario generation (1000+ scenarios)
- ✅ Use **GNN** for deep learning-based optimization
- ✅ Use **LLM** for explainable AI and validation
- ✅ Use **PID** as deterministic baseline for comparison
- ✅ Compare agent performance on same scenarios (common random numbers)

**DON'T**:
- ❌ Don't use LLM for 1000+ scenarios (too slow, expensive)
- ❌ Don't use Naive agent in production (40-50% vs optimal)
- ❌ Don't deploy agents without validation against historical data

---

## Testing & Validation

### 1. Test Configurations

**Simple (4-node serial chain)**:
- Default TBG: Retailer → Wholesaler → Distributor → Factory
- Use for algorithm validation and unit tests

**Medium (9-node convergent)**:
- Three FG TBG: 3 finished goods, 3 components, 2 packaging, 1 raw material
- Use for multi-product validation

**Complex (20+ nodes)**:
- Complex SC: Manufacturing with BOMs, multiple sourcing paths
- Use for performance testing and scalability validation

### 2. Validation Metrics

**Policy Compliance**:
- Orders match policy logic (e.g., base stock orders up to target)
- Safety stock calculations correct (verify z-scores, DOS calculations)

**Constraint Satisfaction**:
- Capacity constraints respected
- Lead time feasibility (orders placed with sufficient lead time)
- Budget constraints met

**KPI Accuracy**:
- Compare simulated vs. actual (if historical data available)
- Validate probabilistic calibration: P(OTIF > 95%) should match empirical frequency

**Performance**:
- Plan generation time <5 minutes for 1000 scenarios
- UI dashboard loads in <2 seconds
- Scales to 100+ node networks

### 3. Test Scripts

**Unit Tests**:
```bash
# Test distribution sampler
pytest backend/tests/test_distribution_sampler.py

# Test policy calculations
pytest backend/tests/test_inventory_target_calculator.py

# Test safety stock logic
pytest backend/tests/test_safety_stock_calculation.py
```

**Integration Tests**:
```bash
# End-to-end planning test
docker compose exec backend python scripts/test_aws_sc_planning.py

# Supply plan generation test
docker compose exec backend python scripts/test_supply_plan_generation.py
```

**Manual Testing**:
```bash
# Play round-by-round game
cd backend
python scripts/manual_round_driver.py --max-rounds 10

# Export game history
python scripts/export_round_history.py --game-id <id>
```

### 4. Validation Checklist

Before deploying planning logic:

- [ ] All distribution types tested with unit tests
- [ ] All 4 policy types validated against examples
- [ ] Hierarchical override logic tested (Item-Node > Item > Node > Config)
- [ ] Safety stock calculations validated with z-score tables
- [ ] Monte Carlo simulation produces consistent results with fixed seed
- [ ] Balanced scorecard probabilities sum to 100%
- [ ] UI displays all 4 perspectives correctly
- [ ] Plan export formats (CSV, Excel, PDF) work
- [ ] Performance meets targets (<5 min for 1000 scenarios)
- [ ] Historical data validation (if available)

---

## References

### Key Design Documents

1. **[SUPPLY_PLAN_GENERATION_DESIGN.md](SUPPLY_PLAN_GENERATION_DESIGN.md)** - Probabilistic planning with balanced scorecard
2. **[AWS_SC_STOCHASTIC_MODELING_DESIGN.md](AWS_SC_STOCHASTIC_MODELING_DESIGN.md)** - 20 distribution types, stochastic framework
3. **[AWS_SC_POLICY_TYPES_IMPLEMENTATION.md](AWS_SC_POLICY_TYPES_IMPLEMENTATION.md)** - 4 inventory policy types
4. **[SUPPLY_PLANNING_VS_EXECUTION.md](SUPPLY_PLANNING_VS_EXECUTION.md)** - Planning vs. execution separation
5. **[DAG_Logic.md](DAG_Logic.md)** - Supply chain topology (4 master node types)
6. **[AGENT_SYSTEM.md](AGENT_SYSTEM.md)** - Agent strategies (TRM, GNN, LLM, PID)

### Academic Papers (in `docs/Knowledge/`)

- `01_MPS_Material_Requirements_Planning_Academic.pdf` - MPS/MRP fundamentals
- `14_Stanford_Stochastic_Programming_Solutions.pdf` - Stochastic optimization
- `17_MIT_Strategic_Safety_Stock_Placement.pdf` - Multi-echelon inventory
- `18_MIT_Inventory_Optimization_Simulation.pdf` - Simulation-based optimization
- `19_Vandeput_Inventory_Optimization.pdf` - Practical inventory management
- `20_Inventory_Management_Stochastic_Demand.pdf` - Demand uncertainty modeling
- `21_Stochastic_Programming_Global_Supply_Chain.pdf` - Global SC optimization

### Industry Whitepapers (in `docs/Knowledge/`)

- `04_Kinaxis_Master_Production_Scheduling.pdf` (1.7MB)
- `06_Kinaxis_Capacity_Planning_Constraints.pdf` (1.8MB)
- `08_Kinaxis_Inventory_Planning_Optimization.pdf` (832KB)
- `10_OMP_5_Planning_Strategies.pdf` (695KB)
- `11_OMP_Supply_Chain_Suite_Overview.pdf` (364KB)
- `16_Safety_Stock_Planning_Supply_Chain.pdf` (315KB)

### Books

- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB) - Sequential Decision Analytics and Modeling (comprehensive decision-making framework)

### Lokad Quantitative Supply Chain Methodology

- `docs/Knowledge/Lokad_Analysis_and_Integration_Guide.md` — Comprehensive analysis of Lokad's methodology with 12 ranked enhancement priorities

**Key Principles Adopted**:
1. **Economic loss functions**: Dollar-denominated rewards in TRM training (not heuristic proxies)
2. **CRPS**: Continuous Ranked Probability Score for probabilistic forecast evaluation
3. **Censored demand**: Detect stockout periods and exclude from distribution fitting
4. **Log-logistic distribution**: Fat-tailed distribution for lead time modeling
5. **Marginal economic return** (`econ_optimal`): Stock one more unit only when expected stockout cost exceeds holding cost
6. **Automated CFA re-optimization**: Weekly Differential Evolution search over policy parameters

### Gartner Decision Intelligence Framework

- `docs/Knowledge/Decision_Intelligence_Framework_Guide.md` — Synthesis of Gartner DI frameworks, Kozyrkov model, and Pratt CDDs

**Key Concepts Applied**:
1. **Decision-as-asset model**: Every recurring decision (stocking, ordering, rebalancing, allocation) modeled with inputs, logic, constraints, ownership, and measured outcomes — logged to `powell_*_decisions` tables
2. **Four DIP lifecycle capabilities**: Modeling (Powell SDAM) → Orchestration (TRM Hive + AAP) → Monitoring (CDC + conformal + CRPS) → Governance (override tracking + CDT)
3. **Three-level maturity**: Decision Support (manual) → Decision Augmentation (copilot) → Decision Automation (autonomous) — progression governed by override posterior, CDT confidence, and decision quality score
4. **Causal Decision Diagrams**: Decision Levers (actions) → Intermediaries (leading indicators) → Outcomes (goals), with Externals (uncertainty) influencing the causal chain
5. **Decision-centric planning**: Gartner 2025 SC Planning Hype Cycle — shift from periodic batch planning to continuous decision execution
6. **Agentic AI**: Gartner predicts 50% of SCM solutions use intelligent agents by 2030; Autonomy deploys 11 per site today

### Code Locations

**Backend Planning Services**:
- `backend/app/services/supply_plan_service.py` - Supply plan generation
- `backend/app/services/stochastic/distributions.py` - Distribution sampling
- `backend/app/services/aws_sc_planning/inventory_target_calculator.py` - Safety stock calculations
- `backend/app/services/aws_sc_planning/net_requirements_calculator.py` - MRP logic
- `backend/app/services/policy_manager.py` - Policy resolution
- `backend/app/simulation/scenario_runner.py` - Simulation orchestration

**Backend Models**:
- `backend/app/models/supply_plan.py` - Supply plan database model
- `backend/app/models/supply_chain_config.py` - Configuration models
- `backend/app/schemas/supply_plan.py` - API schemas

**Frontend Planning UI**:
- `frontend/src/pages/admin/SupplyPlanGenerator.jsx` - Plan generation UI
- `frontend/src/components/planning/BalancedScorecard.jsx` - Scorecard visualization
- `frontend/src/components/distribution-editor/` - Distribution editor components

---

**End of Planning Knowledge Base**

*For questions or clarifications, reference the source documents listed above or consult the codebase directly.*

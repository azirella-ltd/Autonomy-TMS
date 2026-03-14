# Stochastic Planning

**Last Updated**: 2026-01-22

---

## Overview

Autonomy's stochastic planning framework enables risk-aware decision-making through uncertainty quantification. Instead of planning with single-point estimates, the system uses probability distributions to model operational variability and generates likelihood distributions for all key performance indicators.

**Key Insight**: Real supply chains are inherently uncertain. Lead times vary, yields fluctuate, demand forecasts have error, and capacity constraints shift. Stochastic planning quantifies these uncertainties and optimizes decisions under risk.

---

## Why Stochastic Planning?

### Limitations of Deterministic Planning

Traditional supply chain planning uses fixed values:
- Lead time = 7 days (always)
- Yield = 95% (always)
- Demand = 1000 units (always)

**Problem**: Reality is uncertain:
- Lead time: 5-10 days (depends on supplier, weather, customs)
- Yield: 90-98% (depends on material quality, operator skill)
- Demand: 800-1200 units (depends on promotions, competitors, seasonality)

**Consequences of Ignoring Uncertainty**:
- Stockouts (underestimated demand variability)
- Excess inventory (overestimated lead time reliability)
- Poor capacity utilization (ignored yield variability)
- Missed service levels (optimistic assumptions)

### Benefits of Stochastic Planning

**1. Risk Quantification**:
- "85% chance we meet 95% service level target"
- "P90 cost is $1.2M (worst case in 90% of scenarios)"
- "50% probability of stockout in Week 8"

**2. Risk-Aware Optimization**:
- Optimize for P90 outcomes (conservative)
- Minimize worst-case cost
- Maximize probability of meeting service level
- Balance expected cost vs. cost variance

**3. Scenario Analysis**:
- What if lead times increase by 20%?
- What if demand variability doubles?
- What if yield drops to 85%?
- Quantify impact on KPIs with confidence intervals

**4. Informed Decision-Making**:
- Compare strategies with risk profiles
- Choose between low-cost-high-risk vs. high-cost-low-risk
- Set safety stock based on risk tolerance
- Justify decisions with probabilistic evidence

---

## Distribution Framework

### 20 Distribution Types

Autonomy supports 20 probability distributions to model different types of uncertainty:

**Continuous Distributions**:
1. **Normal** (Gaussian): Symmetric, unbounded (e.g., forecast error)
2. **Lognormal**: Right-skewed, positive only (e.g., lead times, costs)
3. **Beta**: Bounded [0, 1] (e.g., yields, percentages)
4. **Gamma**: Right-skewed, positive (e.g., demand, inter-arrival times)
5. **Weibull**: Flexible shape (e.g., time-to-failure, aging effects)
6. **Exponential**: Memoryless (e.g., time between events)
7. **Uniform**: Constant probability in range (e.g., equal likelihood)
8. **Triangular**: Simple with mode (e.g., three-point estimates)
9. **Cauchy**: Heavy tails (e.g., extreme events)
10. **Chi-squared**: Sum of squares (e.g., variability metrics)
11. **F-distribution**: Ratio of variances (e.g., ANOVA)
12. **Student's t**: Heavy tails, small samples (e.g., uncertain parameters)

**Discrete Distributions**:
13. **Poisson**: Count events in fixed interval (e.g., customer arrivals)
14. **Binomial**: Number of successes in n trials (e.g., defect counts)
15. **Geometric**: Trials until first success (e.g., time to first failure)
16. **Negative Binomial**: Overdispersed Poisson (e.g., lumpy demand)

**Advanced Distributions**:
17. **Mixture**: Combination of distributions (e.g., multi-modal demand)
18. **Empirical**: From historical data (e.g., actual lead time distribution)
19. **Truncated**: Limited range (e.g., lead time never < 1 day)
20. **Custom**: User-defined via piecewise functions

### Distribution Selection Guide

**Lead Times**:
- **Lognormal**: Most common (right-skewed, positive)
- **Weibull**: If aging effects (older shipments more likely delayed)
- **Empirical**: Use actual historical lead times

**Demand**:
- **Normal**: Symmetric, high volume (Central Limit Theorem applies)
- **Gamma**: Right-skewed, low volume
- **Negative Binomial**: Lumpy demand (large orders interspersed with zeros)
- **Mixture**: Multi-modal (e.g., B2B vs. B2C channels)

**Yields**:
- **Beta**: Bounded [0, 1], flexible shape
- **Truncated Normal**: If tightly controlled process

**Capacity**:
- **Uniform**: Unknown with range
- **Triangular**: Three-point estimate (min, mode, max)
- **Beta**: If historical data suggests specific shape

**Forecast Error**:
- **Normal**: Unbiased forecasts
- **Lognormal**: If systematic bias (tends to under/over-forecast)

### Data Population: SAP Operational Statistics → Distribution Parameters

Distribution parameters are **automatically extracted** from SAP S/4HANA transaction history via HANA SQL aggregation queries, eliminating manual parameter estimation.

**13 Operational Metrics Extracted**:

| Metric | SAP Source Tables | Distribution Family | Target Entity |
|--------|-------------------|--------------------|----|
| Supplier lead time | EKKO, EKBE | Lognormal (right-skewed) | `vendor_lead_times.lead_time_dist` |
| Supplier on-time rate | EKBE, EKET | Beta (0-1 bounded) | `supplier_on_time` |
| Supplier qty accuracy | EKBE, EKPO | Beta | Supplier performance |
| Manufacturing cycle time | AFKO, AFPO, AFRU | Lognormal | `production_process.operation_time_dist` |
| Manufacturing yield | AFRU, AFPO | Beta | `production_process.yield_dist` |
| Manufacturing setup time | AFRU, AFPO | Lognormal | `production_process.setup_time_dist` |
| Manufacturing run time | AFRU, AFPO | Lognormal | Production process |
| Machine MTBF | QMEL (M2 notifications) | Lognormal | `production_process.mtbf_dist` |
| Machine MTTR | QMEL (M2 notifications) | Lognormal | `production_process.mttr_dist` |
| Quality rejection rate | QALS | Beta | Quality metadata |
| Transportation lead time | LIKP, LIPS | Lognormal | `transportation_lane.supply_lead_time_dist` |
| Demand variability | VBAP (weekly aggregation) | Lognormal/Normal | Demand metadata |
| Order fulfillment time | VBAK, LIPS, LIKP | Lognormal | Fulfillment metadata |

**Distribution Fitting Heuristics** (from summary statistics only — no raw data transfer):
- **Lognormal**: Selected when median < mean (right skew) or CV > 0.5. Parameters derived via method-of-moments: `μ_log = ln(μ²/√(σ²+μ²))`, `σ_log = √(ln(1+σ²/μ²))`
- **Beta**: Selected for rate/ratio metrics bounded 0-1. Parameters via method-of-moments: `α = μ·((μ(1-μ)/σ²)-1)`, `β = (1-μ)·((μ(1-μ)/σ²)-1)`
- **Normal**: Fallback when data is roughly symmetric
- **Triangular**: Fallback when only min/mode/max available (< 5 observations)

**Truncation**: P05/P95 percentiles stored as `min`/`max` bounds to exclude outliers.

**Pipeline**: `extract_sap_hana.py --operational-stats` → HANA SQL aggregation → `operational_stats.json` → `SupplyChainMapper.map_operational_stats_to_distributions()` → `SAPDataStagingService._upsert_operational_stats()` → `*_dist` JSON columns

**Convention**: `NULL` in any `*_dist` column = use the deterministic base field value (e.g., `lead_time_days`).

### Per-Agent Stochastic Parameters

Each of the 11 TRM agent types uses a specific subset of stochastic variables. The `agent_stochastic_params` table stores per-agent distribution values with source tracking:

| TRM Agent | Stochastic Parameters |
|---|---|
| ATP Executor | demand_variability |
| Inventory Rebalancing | demand_variability, supplier_lead_time, transport_lead_time |
| PO Creation | supplier_lead_time, supplier_on_time |
| Order Tracking | supplier_lead_time, transport_lead_time |
| MO Execution | manufacturing_cycle_time, manufacturing_yield, setup_time, mtbf, mttr |
| TO Execution | transport_lead_time |
| Quality Disposition | quality_rejection_rate, manufacturing_yield |
| Maintenance Scheduling | mtbf, mttr |
| Subcontracting | manufacturing_cycle_time, supplier_lead_time |
| Forecast Adjustment | demand_variability |
| Inventory Buffer | demand_variability, supplier_lead_time |

**Source tracking**: Each parameter row carries `is_default` (boolean) and `source` (industry_default / sap_import / manual_edit):
- **industry_default**: Auto-populated based on tenant industry vertical (13 industries). Updated when industry changes — but ONLY if `is_default=True`.
- **sap_import**: Derived from SAP operational statistics extraction. Protected from industry changes.
- **manual_edit**: Set by user through the Stochastic Parameters editor UI. Protected from industry changes.

**Hierarchy**: Config-wide defaults (`site_id=NULL`) apply to all sites. Site-specific overrides (`site_id=<id>`) take precedence.

**Implementation**: Model in `agent_stochastic_param.py`, service in `industry_defaults_service.py` (`apply_agent_stochastic_defaults()`), API at `/api/v1/agent-stochastic-params/`, UI at `/admin/stochastic-params`.

---

## Operational vs. Control Variables

### Operational Variables (Stochastic)

**Definition**: Variables we cannot control but must model uncertainty for.

**Examples**:
- **Lead Times**: Transportation delays, customs clearance, supplier variability
- **Yields**: Production output, scrap rates, quality pass rates
- **Capacities**: Machine uptime, labor availability, resource constraints
- **Demand**: Customer orders (actual, not forecast)
- **Forecast Error**: Difference between forecast and actual
- **Supplier Reliability**: On-time delivery rate, fill rate

**How to Model**:
```python
# Example: Lead time distribution
lead_time_dist = {
    "type": "lognormal",
    "mean": 7,  # days
    "std": 2,   # variability
    "truncate_min": 3,  # Never less than 3 days
    "truncate_max": 21  # Never more than 3 weeks
}

# Example: Yield distribution
yield_dist = {
    "type": "beta",
    "alpha": 95,  # Shape parameter (successes)
    "beta": 5,    # Shape parameter (failures)
    # Mean = alpha / (alpha + beta) = 95%
}

# Example: Demand distribution
demand_dist = {
    "type": "gamma",
    "shape": 2,
    "scale": 500,  # Mean = shape * scale = 1000 units
}
```

### Control Variables (Deterministic)

**Definition**: Variables we directly control as decision variables.

**Examples**:
- **Inventory Targets**: Safety stock levels, reorder points
- **Policy Parameters**: Days of coverage, service level targets
- **Costs**: Holding cost, ordering cost, shortage cost (known inputs)
- **Order Quantities**: How much to order (decision output)
- **Production Schedules**: When and how much to produce (decision output)

**Why Deterministic**:
- We set these values as part of the planning process
- They are decisions, not random outcomes
- Uncertainty is in the outcomes (service levels, costs) given these decisions

**Example**:
```python
# Control variables (deterministic)
policy = {
    "type": "doc_dem",  # Days of coverage - demand-based
    "target_days": 14,  # Decision: maintain 14 days of supply
    "holding_cost": 0.25,  # $/unit/year (known)
    "shortage_cost": 10.0  # $/unit (known)
}

# Operational variables (stochastic)
operational_params = {
    "lead_time": {"type": "lognormal", "mean": 7, "std": 2},
    "demand": {"type": "gamma", "shape": 2, "scale": 500}
}

# Outcome (stochastic)
# Service level achieved = f(policy, operational_params, randomness)
# We get a DISTRIBUTION of service levels, not a single value
```

---

## Monte Carlo Simulation Engine

### How It Works

**1. Scenario Generation**:
```python
num_scenarios = 1000  # Number of Monte Carlo runs

for scenario in range(num_scenarios):
    # Sample from operational distributions
    lead_time = sample_from_distribution(lead_time_dist)
    yield_rate = sample_from_distribution(yield_dist)
    demand = sample_from_distribution(demand_dist)

    # Run planning with sampled values
    result = run_planning_scenario(
        lead_time=lead_time,
        yield_rate=yield_rate,
        demand=demand,
        policy=policy  # Deterministic
    )

    # Collect outcomes
    scenarios.append({
        "total_cost": result.total_cost,
        "service_level": result.service_level,
        "inventory_turns": result.inventory_turns,
        ...
    })
```

**2. Distribution Analysis**:
```python
# After 1000 scenarios, analyze outcomes
outcomes = {
    "total_cost": {
        "mean": np.mean([s["total_cost"] for s in scenarios]),
        "p10": np.percentile([s["total_cost"] for s in scenarios], 10),
        "p50": np.percentile([s["total_cost"] for s in scenarios], 50),
        "p90": np.percentile([s["total_cost"] for s in scenarios], 90),
        "std": np.std([s["total_cost"] for s in scenarios])
    },
    "service_level": {
        "mean": np.mean([s["service_level"] for s in scenarios]),
        "p_above_95": sum(s["service_level"] > 0.95 for s in scenarios) / len(scenarios),
        ...
    }
}
```

### Variance Reduction Techniques

**1. Common Random Numbers**:
```python
# Use same random seed for comparing strategies
np.random.seed(42)
strategy_a_results = simulate(strategy_a)

np.random.seed(42)  # Same seed
strategy_b_results = simulate(strategy_b)

# Differences are due to strategies, not random variation
```

**2. Antithetic Variates**:
```python
# For each scenario, also run its "opposite"
for i in range(num_scenarios // 2):
    u = np.random.uniform(0, 1)
    scenario_1 = inverse_cdf(u)
    scenario_2 = inverse_cdf(1 - u)  # Antithetic

    results.extend([run_planning(scenario_1), run_planning(scenario_2)])

# Reduces variance by 50% for same number of scenarios
```

**3. Latin Hypercube Sampling**:
```python
# Stratified sampling for better coverage
from scipy.stats import qmc

sampler = qmc.LatinHypercube(d=3)  # 3 dimensions (lead time, yield, demand)
samples = sampler.random(n=1000)

# Map to distributions
lead_times = lognorm.ppf(samples[:, 0], s=2, scale=7)
yields = beta.ppf(samples[:, 1], a=95, b=5)
demands = gamma.ppf(samples[:, 2], a=2, scale=500)

# Better representation of distribution space than pure random sampling
```

**Performance**: With variance reduction, 500 scenarios can achieve the same accuracy as 1000 pure random scenarios.

---

## Probabilistic Balanced Scorecard

### Framework

Traditional balanced scorecard uses point estimates. Stochastic planning provides **likelihood distributions** for all KPIs.

### 4 Perspectives with Uncertainty

#### 1. Financial Perspective

**Expected Value Metrics**:
- **E[Total Cost]**: Expected total supply chain cost
- **E[Holding Cost]**: Expected inventory carrying cost
- **E[Shortage Cost]**: Expected backorder/stockout cost
- **E[Ordering Cost]**: Expected procurement/setup cost

**Risk Metrics**:
- **Cost-at-Risk (CaR)**: P90 or P95 cost (worst case in 90% or 95% of scenarios)
- **P(Cost < Budget)**: Probability of staying within budget
- **Cost Distribution**: P10/P50/P90 percentiles
- **Cost Variance**: Spread of cost outcomes

**Example**:
```python
financial_metrics = {
    "total_cost": {
        "E": 850_000,  # Expected cost
        "P10": 750_000,  # Best case (10th percentile)
        "P50": 850_000,  # Median
        "P90": 1_100_000,  # Worst case (90th percentile)
        "CaR_95": 1_200_000,  # Cost-at-Risk at 95%
        "P(Cost < $1M)": 0.75  # 75% chance under $1M budget
    }
}
```

#### 2. Customer Perspective

**Service Level Metrics**:
- **E[OTIF]**: Expected On-Time-In-Full rate
- **E[Fill Rate]**: Expected order fill rate
- **P(Service Level > Target)**: Probability of meeting service level target

**Risk Metrics**:
- **Service Level Distribution**: P10/P50/P90 percentiles
- **P(Stockout)**: Probability of stockout in planning horizon
- **Backorder Distribution**: Expected backlog and variance

**Example**:
```python
customer_metrics = {
    "otif": {
        "E": 0.93,  # Expected OTIF
        "P10": 0.85,  # Worst case service
        "P50": 0.94,  # Median service
        "P90": 0.98,  # Best case service
        "P(OTIF > 0.95)": 0.35  # 35% chance of exceeding 95% target
    },
    "stockout_risk": {
        "P(Any Stockout)": 0.18,  # 18% chance of at least one stockout
        "E[Stockout Weeks]": 1.2,  # Expected weeks with stockout
        "E[Backlog]": 23  # Expected average backlog
    }
}
```

#### 3. Operational Perspective

**Efficiency Metrics**:
- **E[Inventory Turns]**: Expected turns
- **E[Days of Supply]**: Expected DOS
- **E[Capacity Utilization]**: Expected utilization rate

**Variability Metrics**:
- **Bullwhip Ratio Distribution**: Order variability / demand variability
- **Inventory Variance**: Spread of inventory levels
- **Utilization Variance**: Capacity constraint risk

**Example**:
```python
operational_metrics = {
    "inventory_turns": {
        "E": 8.5,  # Expected turns
        "P10": 6.2,  # Low turns (high inventory)
        "P90": 11.3  # High turns (low inventory)
    },
    "days_of_supply": {
        "E": 42,  # Expected DOS
        "P10": 32,  # Low inventory
        "P90": 58  # High inventory
    },
    "bullwhip_ratio": {
        "E": 1.8,  # Expected amplification
        "P(Bullwhip < 2.0)": 0.65  # 65% chance below threshold
    },
    "capacity_utilization": {
        "E": 0.82,  # Expected utilization
        "P(Over Capacity)": 0.05  # 5% chance of exceeding capacity
    }
}
```

#### 4. Strategic Perspective

**Flexibility Metrics**:
- **Supply Chain Agility Score**: Ability to respond to changes
- **Supplier Diversity**: Risk concentration
- **Buffer Capacity**: Available slack

**Sustainability Metrics**:
- **E[CO2 Emissions]**: Expected carbon footprint
- **E[Waste]**: Expected scrap/obsolescence
- **Circular Economy Score**: Reuse/recycle rate

**Example**:
```python
strategic_metrics = {
    "agility": {
        "response_time_p50": 5,  # Median days to respond to change
        "response_time_p90": 12,  # 90th percentile response time
        "flexibility_score": 0.72  # 0-1 scale
    },
    "sustainability": {
        "E[CO2_tons]": 1250,  # Expected emissions
        "P10": 1100,
        "P90": 1450,
        "P(Below Target)": 0.82  # 82% chance below ESG target
    },
    "supplier_risk": {
        "concentration_index": 0.35,  # Herfindahl index
        "P(Supplier Disruption)": 0.08  # 8% chance of disruption
    }
}
```

---

## Implementation

### Stochastic Sampler Service

**Files**:
- `backend/app/services/sc_planning/stochastic_sampler.py` - Distribution sampling engine

**Key Class**:
```python
class StochasticSampler:
    """
    Samples from probability distributions for operational variables.
    """

    def __init__(self, stochastic_params: Dict):
        """
        stochastic_params = {
            "lead_time_variability": {
                "type": "lognormal",
                "mean": 7,
                "std": 2
            },
            "yield_variability": {
                "type": "beta",
                "alpha": 95,
                "beta": 5
            },
            "demand_variability": {
                "type": "gamma",
                "shape": 2,
                "scale": 500
            }
        }
        """
        self.params = stochastic_params

    def sample_lead_time(self, base_lead_time: int) -> int:
        """Sample actual lead time from distribution."""
        if "lead_time_variability" not in self.params:
            return base_lead_time

        dist = self.params["lead_time_variability"]
        if dist["type"] == "lognormal":
            return int(np.random.lognormal(
                mean=np.log(dist["mean"]),
                sigma=dist["std"]
            ))
        # ... other distribution types

    def sample_yield(self, base_yield: float) -> float:
        """Sample actual yield from distribution."""
        if "yield_variability" not in self.params:
            return base_yield

        dist = self.params["yield_variability"]
        if dist["type"] == "beta":
            return np.random.beta(
                a=dist["alpha"],
                b=dist["beta"]
            )
        # ... other distribution types

    def sample_demand(self, forecast_demand: float) -> float:
        """Sample actual demand from distribution."""
        if "demand_variability" not in self.params:
            return forecast_demand

        dist = self.params["demand_variability"]
        if dist["type"] == "gamma":
            return np.random.gamma(
                shape=dist["shape"],
                scale=dist["scale"]
            )
        # ... other distribution types
```

### Monte Carlo Planning Loop

**Files**:
- `backend/app/services/sc_planning/planner.py` - Main planning orchestrator

**Key Method**:
```python
async def plan_with_uncertainty(
    config_id: int,
    planning_horizon: int,
    stochastic_params: Dict,
    num_scenarios: int = 1000
) -> ProbabilisticBalancedScorecard:
    """
    Run Monte Carlo simulation for probabilistic planning.
    """

    sampler = StochasticSampler(stochastic_params)
    scenarios = []

    for i in range(num_scenarios):
        # Sample operational variables
        sampled_params = {
            "lead_times": {},
            "yields": {},
            "demands": {}
        }

        # Sample lead times for all sourcing rules
        for rule in sourcing_rules:
            base_lt = rule.lead_time_days
            sampled_params["lead_times"][rule.id] = sampler.sample_lead_time(base_lt)

        # Sample yields for all production processes
        for process in production_processes:
            base_yield = process.yield_rate
            sampled_params["yields"][process.id] = sampler.sample_yield(base_yield)

        # Sample demand for all forecasts
        for forecast in forecasts:
            base_demand = forecast.forecast_quantity
            sampled_params["demands"][forecast.id] = sampler.sample_demand(base_demand)

        # Run deterministic planning with sampled values
        scenario_result = await run_deterministic_plan(
            config_id=config_id,
            planning_horizon=planning_horizon,
            sampled_params=sampled_params
        )

        scenarios.append(scenario_result)

    # Analyze scenario outcomes
    return analyze_scenarios(scenarios)
```

### Scenario Analysis

**Key Method**:
```python
def analyze_scenarios(scenarios: List[PlanResult]) -> ProbabilisticBalancedScorecard:
    """
    Compute probabilistic balanced scorecard from scenarios.
    """

    # Extract metrics from all scenarios
    total_costs = [s.total_cost for s in scenarios]
    service_levels = [s.service_level for s in scenarios]
    inventory_turns = [s.inventory_turns for s in scenarios]
    # ... etc

    return ProbabilisticBalancedScorecard(
        financial={
            "total_cost": {
                "E": np.mean(total_costs),
                "P10": np.percentile(total_costs, 10),
                "P50": np.percentile(total_costs, 50),
                "P90": np.percentile(total_costs, 90),
                "std": np.std(total_costs),
                "P_below_budget": sum(c < budget for c in total_costs) / len(total_costs)
            }
        },
        customer={
            "service_level": {
                "E": np.mean(service_levels),
                "P10": np.percentile(service_levels, 10),
                "P50": np.percentile(service_levels, 50),
                "P90": np.percentile(service_levels, 10),
                "P_above_95": sum(sl > 0.95 for sl in service_levels) / len(service_levels)
            }
        },
        operational={
            "inventory_turns": {
                "E": np.mean(inventory_turns),
                "P10": np.percentile(inventory_turns, 10),
                "P90": np.percentile(inventory_turns, 90)
            }
        },
        strategic={
            # ... sustainability, agility metrics
        }
    )
```

---

## Use Cases

### Use Case 1: Safety Stock Optimization

**Problem**: How much safety stock to maintain?

**Deterministic Approach**:
- Lead time = 7 days (fixed)
- Daily demand = 100 units (fixed)
- Safety stock = z × σ × √lead_time = 1.65 × 20 × √7 = 87 units

**Stochastic Approach**:
```python
stochastic_params = {
    "lead_time_variability": {
        "type": "lognormal",
        "mean": 7,
        "std": 2  # Lead time varies 5-10 days typically
    },
    "demand_variability": {
        "type": "gamma",
        "shape": 25,  # Mean = shape * scale = 100
        "scale": 4
    }
}

# Run 1000 scenarios
results = await plan_with_uncertainty(
    config_id=1,
    planning_horizon=52,
    stochastic_params=stochastic_params,
    num_scenarios=1000
)

# Output
# "With 90 units safety stock:"
# - E[Service Level] = 94.2%
# - P(Service Level > 95%) = 42%
# - E[Holding Cost] = $45,000
#
# "With 120 units safety stock:"
# - E[Service Level] = 97.8%
# - P(Service Level > 95%) = 88%
# - E[Holding Cost] = $60,000
#
# "Decision: Choose 120 units for 88% confidence of meeting 95% service level"
```

### Use Case 2: Supplier Selection Under Uncertainty

**Problem**: Choose between 2 suppliers with different cost/reliability profiles.

**Supplier A**:
- Cost: $10/unit (fixed)
- Lead time: 5 days (fixed, very reliable)

**Supplier B**:
- Cost: $8/unit (cheaper)
- Lead time: 3-12 days (lognormal, mean=7, std=3, less reliable)

**Stochastic Analysis**:
```python
# Scenario 1: Use Supplier A
scenario_a_params = {
    "lead_time_variability": None  # Deterministic
}
result_a = await plan_with_uncertainty(config_id=1, stochastic_params=scenario_a_params)

# Scenario 2: Use Supplier B
scenario_b_params = {
    "lead_time_variability": {"type": "lognormal", "mean": 7, "std": 3}
}
result_b = await plan_with_uncertainty(config_id=1, stochastic_params=scenario_b_params)

# Compare
# Supplier A:
# - E[Total Cost] = $520,000
# - P90[Total Cost] = $545,000 (low variance)
# - E[Service Level] = 98.5%
#
# Supplier B:
# - E[Total Cost] = $485,000 (lower expected cost due to cheaper price)
# - P90[Total Cost] = $620,000 (high variance due to unreliable lead time)
# - E[Service Level] = 92.1% (worse service due to variability)
#
# Decision: If risk-averse → Supplier A. If risk-neutral → Supplier B.
```

### Use Case 3: Capacity Planning with Yield Uncertainty

**Problem**: Plan production capacity when yield is uncertain.

**Scenario**:
- Target output: 10,000 units/month
- Yield: 92-98% (beta distribution, alpha=92, beta=8)
- Capacity: 11,000 units/month (fixed)

**Stochastic Analysis**:
```python
stochastic_params = {
    "yield_variability": {
        "type": "beta",
        "alpha": 92,
        "beta": 8
    }
}

results = await plan_with_uncertainty(
    config_id=1,
    stochastic_params=stochastic_params
)

# Output:
# - E[Output] = 10,450 units (92% + 8% spread)
# - P(Output < 10,000) = 22% (miss target 22% of time)
# - P90[Output] = 9,680 units (worst case)
#
# "Recommendation: Increase capacity to 11,500 to reduce P(Output < 10,000) to 5%"
```

---

## API Examples

### Generate Stochastic Supply Plan
```bash
POST /api/v1/supply-plan/generate
{
  "config_id": 1,
  "planning_horizon": 52,
  "start_date": "2026-01-22",
  "stochastic_params": {
    "lead_time_variability": {
      "type": "lognormal",
      "mean": 7,
      "std": 2
    },
    "demand_variability": {
      "type": "gamma",
      "shape": 2,
      "scale": 500
    },
    "yield_variability": {
      "type": "beta",
      "alpha": 95,
      "beta": 5
    }
  },
  "num_scenarios": 1000,
  "objectives": {
    "minimize_cost": true,
    "target_service_level": 0.95,
    "risk_tolerance": "moderate"  # conservative, moderate, aggressive
  }
}

# Response (async task ID)
{
  "task_id": "abc-123",
  "status": "PENDING"
}
```

### Get Probabilistic Balanced Scorecard
```bash
GET /api/v1/supply-plan/result/abc-123

# Response
{
  "task_id": "abc-123",
  "status": "COMPLETED",
  "result": {
    "financial": {
      "total_cost": {
        "E": 850000,
        "P10": 750000,
        "P50": 850000,
        "P90": 1100000,
        "std": 95000,
        "P_below_budget": 0.75
      }
    },
    "customer": {
      "service_level": {
        "E": 0.942,
        "P10": 0.885,
        "P50": 0.945,
        "P90": 0.982,
        "P_above_95": 0.42
      }
    },
    "operational": {
      "inventory_turns": {
        "E": 8.5,
        "P10": 6.2,
        "P90": 11.3
      },
      "days_of_supply": {
        "E": 42,
        "P10": 32,
        "P90": 58
      }
    },
    "strategic": {
      "co2_emissions": {
        "E": 1250,
        "P10": 1100,
        "P90": 1450,
        "P_below_target": 0.82
      }
    }
  }
}
```

---

## Performance

**Benchmarks** (52-week horizon, 10 sites, 100 items):
- Single deterministic plan: <10s
- 1000 scenarios with pure random sampling: ~2.5 hours (9s × 1000)
- 500 scenarios with Latin Hypercube Sampling: ~1 hour (equal accuracy to 1000 pure random)
- Parallel execution (4 cores): ~15 minutes for 500 scenarios

**Scalability**:
- Supports up to 10,000 scenarios for high-precision risk analysis
- GPU acceleration planned for Monte Carlo loops
- Distributed execution across multiple workers

---

## Further Reading

- [PLANNING_CAPABILITIES.md](PLANNING_CAPABILITIES.md) - Core planning logic that stochastic framework extends
- [PLANNING_KNOWLEDGE_BASE.md](../PLANNING_KNOWLEDGE_BASE.md) - Academic foundations for stochastic programming
- [EXECUTION_CAPABILITIES.md](EXECUTION_CAPABILITIES.md) - How uncertainty affects execution
- [AI_AGENTS.md](AI_AGENTS.md) - How AI agents handle uncertainty

---

## Academic References

**Key Papers** (in `docs/Knowledge/`):
- `14_Stanford_Stochastic_Programming_Solutions.pdf` (588KB) - Stanford course on stochastic optimization
- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB) - Sequential Decision Analytics under Uncertainty
- `01_MPS_Material_Requirements_Planning_Academic.pdf` - MPS/MRP under uncertainty

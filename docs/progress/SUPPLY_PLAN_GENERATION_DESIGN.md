# Supply Plan Generation with Probabilistic Balanced Scorecard

**Date**: 2026-01-17
**Status**: 📋 DESIGN DOCUMENT
**Purpose**: Design UI and algorithms for generating supply plans with probabilistic balanced scorecard metrics

---

## Executive Summary

This document presents a design for an advanced supply planning module that leverages The Continuous Autonomous Planning Platform's existing simulation infrastructure, AI agents (GNN, TRM, LLM), and stochastic modeling capabilities to generate optimized supply plans with probabilistic performance metrics displayed in a balanced scorecard framework.

**Key Differentiation**: Unlike traditional planning systems (Kinaxis, SAP IBP, OMP) that provide deterministic recommendations, this module will generate plans with **likelihood distributions** for achieving each balanced scorecard metric, enabling risk-informed decision-making.

---

## 1. Research Findings: Industry Balanced Scorecards

### 1.1 Balanced Scorecard Framework (Kaplan & Norton)

The [Balanced Scorecard framework](https://www.numberanalytics.com/blog/balanced-scorecard-logistics-supply-chain-management) was introduced by Robert Kaplan and David Norton in the 1990s as a strategic management framework. The [traditional BSC framework](https://balancedscorecard.org/bsc-basics-overview/) considers four key perspectives:

1. **Financial Perspective** - Traditional financial measures (cost, working capital, ROI)
2. **Customer Perspective** - Customer satisfaction and service metrics (OTIF, fill rate)
3. **Internal Processes** - Operational efficiency (inventory turns, lead time, throughput)
4. **Learning & Growth** - Innovation and adaptability (forecast accuracy improvement, process optimization)

**Application to Supply Chain**: The [BSC for SCM framework](https://www.sciencedirect.com/science/article/abs/pii/S0360835207000617) is structurally similar to corporate BSC with adaptations for supply chain operations. [Balanced scorecards can play a role in supply chain recovery strategies](https://www.scmr.com/article/balanced_scorecards_can_play_a_role_in_supply_chain_recovery_strategies) by linking operational performance improvements to customer and financial outcomes.

### 1.2 Supply Chain Planning KPIs by Category

Based on [industry research](https://www.mrpeasy.com/blog/supply-chain-kpis/), supply chain KPIs can be organized into several categories:

#### Financial Metrics
- **Total Supply Chain Cost** (% of revenue)
- **Inventory Carrying Cost** (% of inventory value)
- **Cash-to-Cash Cycle Time** (days)
- **Working Capital** ($)
- **Cost to Serve** ($ per order/customer)

#### Customer Service Metrics
- **OTIF (On-Time-In-Full)** (%)
- **Perfect Order Rate** (%)
- **Order Fill Rate** / Case Fill Rate (%)
- **Backorder Rate** (%)
- **Customer Order Cycle Time** (days)

#### Operational Efficiency Metrics
- **Inventory Turnover** (turns/year)
- **Days of Supply (DOS)** (days)
- **Supply Chain Cycle Time** (days)
- **Forecast Accuracy** (%)
- **Forecast Bias** (%)
- **OEE (Overall Equipment Effectiveness)** (%) - for manufacturing

#### Strategic/Growth Metrics
- **Supplier Performance** (score)
- **Supply Chain Flexibility** (response time to changes)
- **Sustainability Metrics** (CO2 emissions, waste reduction)
- **Forecast Value Added (FVA)** (%)

### 1.3 SAP IBP Balanced Scorecard Metrics

[SAP IBP](https://www.scplan-consulting.de/sap-ibp-forecast-improvement/) defines metrics to evaluate forecast quality and planning performance:

**Forecast Accuracy Metrics**:
- **MAPE (Mean Absolute Percentage Error)**
- **WMAPE (Weighted MAPE)** - [improved accuracy reporting](https://valuechainplanning.com/blog-details/104)
- **Forecast Bias** - systematic over/under forecasting
- **FVA (Forecast Value Added)** - incremental value from forecasting process

**Service Metrics**:
[Various customer service metrics](https://community.sap.com/t5/supply-chain-management-q-a/ibp-s-op-and-inventory-kpi-s/qaq-p/12190972) like OTIF, OTD (on-time delivery), case fill rate are tracked in IBP S&OP modules.

**Planning Cycle Metrics**:
- **Planning Cycle Time** - time to generate executable plans
- **Constraint Satisfaction** - % of plans feasible within constraints
- **Scenario Comparison** - delta between alternative plans

### 1.4 Kinaxis RapidResponse KPIs

[Kinaxis](https://www.kinaxis.com/en/sop) focuses on S&OP (Sales and Operations Planning) metrics with real-time visibility:

**Demand Planning**:
- Forecast accuracy tracked over [planning time horizon](https://demand-planning.com/2023/11/20/the-supply-chain-planning-kpis-you-need-to-know/)
- Demand sensing for 6-8 week horizons
- Statistical forecast algorithm monitoring

**Supply Planning**:
- Inventory DOS (Days of Supply)
- Service level attainment (%)
- Resource utilization (%)

**S&OP Integration**:
Operational metrics are [dovetailed into a relevant business/financial scorecard](https://demand-planning.com/2023/11/20/the-supply-chain-planning-kpis-you-need-to-know/) every month, quarter, and financial year.

### 1.5 OMP Unison Planning KPIs

[OMP Unison Planning](https://omp.com/) provides an AI-driven platform with integrated analytics:

**Role-Specific Dashboards**:
- KPIs, alerts, and scenario comparison configured per planning role
- 360° Analytics dashboards with strategic-to-operational zoom ("telescopic digital twin")

**Key Metrics** (from [general supply chain planning KPIs](https://demand-planning.com/2023/11/20/the-supply-chain-planning-kpis-you-need-to-know/)):
- **Forecast Error Metrics**: Forecast Bias, FVA
- **Supply Planning**: OEE (Overall Equipment Effectiveness) for production
- **Sourcing**: Supplier performance, lead time variability

**OMP Differentiator**: [Reviews show](https://www.gartner.com/reviews/market/supply-chain-planning-solutions/vendor/omp/product/unison-planning) integrated planning environment with scenario comparison capabilities.

### 1.6 Probabilistic Planning Approaches

[Probabilistic planning in supply chains](https://www.aimms.com/story/probabilistic-planning-supply-chain-resilence/) involves systematically analyzing multiple scenarios for each business objective to account for uncertainty and variability.

**AI/ML-Driven Forecasting**:
[Artificial intelligence and machine learning](https://www.aimms.com/story/probabilistic-planning-supply-chain-resilence/) are taking probabilistic forecasting to the next level. Real-world results show [significant benefits](https://www.aimms.com/story/probabilistic-planning-supply-chain-resilence/): supply chain planning software reduced inventory costs by 25% while improving service levels to over 99%.

**Stochastic Optimization Research** (2025-2026):

Recent [research on stochastic programming](https://www.sciencedirect.com/science/article/pii/S0957417425002088) introduces a Separated Estimation and Optimisation (SEO) approach:
1. Estimate demand uncertainty using ML-based probabilistic forecasting
2. Solve optimization using stochastic programming
3. Validated across 17 datasets with 303 products, confirming robustness

[Multi-stage stochastic programming models](https://link.springer.com/article/10.1007/s12351-025-00988-0) manage uncertainties from asset failures and variable demand using sample average approximation (SAA) to address computational complexity.

**Risk Assessment Integration**:
[Risk management platforms](https://www.z2data.com/) offer proprietary risk scoring and dashboard tools. [SAP introduced a risk dashboard](https://blogs.sap.com/2023/04/18/take-the-risk-out-of-your-supply-chain-by-planning-ahead/) based on risks within planning data itself: low forecast accuracy, inaccurate safety stock, resource bottlenecks, excess CO2 emissions.

---

## 2. Proposed Balanced Scorecard for The Continuous Autonomous Planning Platform

### 2.1 Four-Perspective Framework

| Perspective | Metrics | Probabilistic Output |
|-------------|---------|---------------------|
| **Financial** | • Total supply chain cost<br>• Inventory carrying cost<br>• Cash-to-cash cycle time<br>• Cost to serve | • P(Total cost < $X)<br>• Expected cost distribution<br>• Risk of exceeding budget |
| **Customer** | • OTIF (On-Time-In-Full)<br>• Fill rate<br>• Backorder rate<br>• Order cycle time | • P(OTIF > 95%)<br>• Expected service level<br>• Risk of stockout |
| **Operational** | • Inventory turnover<br>• Days of supply<br>• Forecast accuracy<br>• Bullwhip ratio<br>• OEE (if manufacturing) | • P(Inventory turns > X)<br>• Expected DOS distribution<br>• P(Forecast error < Y%) |
| **Strategic** | • Supply chain flexibility<br>• Sustainability (CO2)<br>• Supplier reliability<br>• Forecast Value Added | • P(Response time < Z days)<br>• Expected CO2 emissions<br>• Supplier risk score |

### 2.2 Metric Definitions for Beer Game Platform

**Financial Perspective**:
1. **Total Supply Chain Cost**: Sum of inventory holding cost + backlog penalty cost + order placement cost across all nodes
2. **Inventory Carrying Cost**: Holding cost rate × average inventory value
3. **Cash-to-Cash Cycle Time**: (Days inventory held) + (Days receivable) - (Days payable)

**Customer Perspective**:
1. **OTIF (On-Time-In-Full)**: % of customer demand fulfilled completely on the requested delivery date
2. **Fill Rate**: % of demand fulfilled immediately from inventory
3. **Backorder Rate**: % of demand not fulfilled immediately (backlog / total demand)
4. **Service Level**: Probability of fulfilling demand from stock

**Operational Perspective**:
1. **Inventory Turnover**: (Total throughput) / (Average inventory) per year
2. **Days of Supply**: (Current inventory) / (Average daily demand)
3. **Forecast Accuracy**: 100% - MAPE (Mean Absolute Percentage Error)
4. **Bullwhip Ratio**: (Variance of orders to supplier) / (Variance of demand from customer)
5. **OEE**: (Actual production) / (Maximum possible production) × 100%

**Strategic Perspective**:
1. **Supply Chain Flexibility**: Average time to adjust production/orders by ±20%
2. **Sustainability**: CO2 emissions per unit shipped
3. **Supplier Reliability**: % on-time deliveries from suppliers
4. **Forecast Value Added**: Improvement in forecast accuracy vs. naive baseline

---

## 3. Stochastic Modeling & Probabilistic Algorithms

### 3.1 Sources of Variability in The Continuous Autonomous Planning Platform

The platform already models several sources of stochasticity:

1. **Demand Variability**:
   - `MarketDemand` table defines demand patterns (constant, seasonal, stochastic)
   - Stochastic demand uses normal distribution: `N(mean, std_dev)`

2. **Lead Time Variability**:
   - `Lane` table defines lead times between nodes
   - Can be extended to stochastic: `N(mean_lead_time, std_dev_lead_time)`

3. **Supplier Reliability**:
   - Current model assumes 100% reliability
   - Can be extended to probabilistic shipment delays or shortfalls

4. **Manufacturing Variability**:
   - BOM (Bill of Materials) defines transformation ratios
   - Can be extended to stochastic yield: `N(expected_yield, yield_std_dev)`

### 3.2 Proposed Probabilistic Planning Algorithm

**High-Level Approach**: Monte Carlo Simulation with Agent-Driven Optimization

```
Algorithm: Probabilistic Supply Plan Generation
-------------------------------------------------
Input:
  - Supply chain configuration (nodes, lanes, items, BOMs)
  - Demand forecast with uncertainty (mean, std_dev, distribution)
  - Lead time distributions per lane
  - Supplier reliability distributions
  - Business objectives (target costs, service levels, inventory targets)
  - Planning horizon (e.g., 52 weeks)

Output:
  - Optimized supply plan (order quantities, production schedules per node)
  - Probabilistic balanced scorecard (P(metric > target) for each metric)

Steps:
  1. Generate N scenarios (e.g., N=1000) using Monte Carlo sampling:
     - Sample demand for each market-product-week from demand distribution
     - Sample lead times for each lane-week from lead time distribution
     - Sample supplier reliability events

  2. For each scenario i in 1..N:
     a. Initialize simulation with current inventory state
     b. Run agent-driven simulation for planning horizon:
        - Use selected agent strategy (GNN, TRM, LLM, PID, etc.)
        - Agents make ordering/production decisions each period
        - Simulate material flow based on sampled parameters
     c. Record end-state metrics for scenario i:
        - Total cost_i, OTIF_i, inventory_turns_i, bullwhip_i, etc.

  3. Aggregate scenario results to compute probability distributions:
     - For each metric M:
       - Compute empirical CDF: P(M < x) = #{scenarios where M_i < x} / N
       - Compute percentiles: P10, P50 (median), P90
       - Compute expected value: E[M] = mean(M_i)

  4. Optimize plan using stochastic programming:
     a. Define objective function:
        - Minimize: E[Total Cost]
        - Subject to: P(OTIF > 95%) >= 0.90
                     P(Inventory < safety_stock) <= 0.05
     b. Use sample average approximation (SAA) to solve:
        - Approximate expectations using scenario samples
        - Solve deterministic equivalent problem via optimization
     c. Extract optimal order quantities, production schedules

  5. Generate balanced scorecard report:
     - Financial: E[Total Cost], P(Cost < Budget), Cost distribution
     - Customer: E[OTIF], P(OTIF > 95%), Backorder risk
     - Operational: E[Inventory Turns], P(DOS within target range)
     - Strategic: E[Bullwhip], Supplier reliability impact

Return: Optimized plan + probabilistic scorecard
```

### 3.3 Integration with Existing Agent Infrastructure

The platform already has multiple agent strategies that can be leveraged:

| Agent Type | Use in Plan Generation | Probabilistic Benefit |
|------------|------------------------|----------------------|
| **GNN (Temporal Graph Neural Network)** | 128M parameter model trained on historical games; predicts optimal orders given graph state | Captures complex supply chain dynamics; generalizes across topologies |
| **TRM (Tiny Recursive Model)** | 7M parameter transformer for fast decision-making; 3-step recursive refinement | Fast inference (10-100x faster than GNN); suitable for real-time scenario generation |
| **LLM (Multi-Agent System)** | OpenAI-based node agents with supervisor; structured JSON responses | Explainable decisions; can incorporate business rules and constraints |
| **PID Controller** | Classic base-stock policy with proportional-integral-derivative control | Fast, deterministic baseline for comparison |
| **Naive Agent** | Mirrors incoming demand (order = demand) | Benchmark for measuring agent value-add |

**Recommended Approach**:
- Use **TRM or GNN** for fast scenario simulation (1000+ scenarios in reasonable time)
- Use **LLM** for final plan validation and explanation generation
- Use **PID** as baseline for comparison (measure improvement vs. traditional base-stock)

### 3.4 Stochastic Optimization Formulation

**Objective Function**:
```
Minimize: E[Total Supply Chain Cost]
        = E[Σ_t Σ_n (h_n × I_n,t + b_n × B_n,t + c_n × O_n,t)]

Where:
  I_n,t = Inventory at node n, period t
  B_n,t = Backlog at node n, period t
  O_n,t = Order quantity at node n, period t
  h_n = Holding cost rate
  b_n = Backlog penalty cost
  c_n = Order placement cost
```

**Constraints**:
```
Service Level:     P(OTIF_retailer > 95%) >= 0.90
Inventory Bounds:  P(I_n,t < 0) <= 0.05  for all n, t
Capacity:          O_n,t <= capacity_n   for all n, t
Budget:            E[Total Cost] <= Budget
```

**Solution Method**:
1. **Sample Average Approximation (SAA)**: Replace expectations with sample averages over N scenarios
2. **Mixed-Integer Linear Programming (MILP)**: If using piecewise linear approximations
3. **Gradient-Based Optimization**: If using differentiable agent policies (GNN, TRM)
4. **Genetic Algorithm / CMA-ES**: For black-box agent optimization

---

## 4. UI/UX Design for Supply Plan Generation

### 4.1 User Workflow

```
[Business Objective Definition]
         ↓
[Parameter Configuration]
         ↓
[Plan Generation (Backend Processing)]
         ↓
[Probabilistic Balanced Scorecard Dashboard]
         ↓
[Plan Comparison & Scenario Analysis]
         ↓
[Plan Approval & Export]
```

### 4.2 Screen 1: Business Objective Definition

**Purpose**: Define planning goals and constraints

**UI Components**:
- **Planning Horizon**: Dropdown (13 weeks, 26 weeks, 52 weeks)
- **Primary Objective**: Radio buttons
  - [ ] Minimize Total Cost
  - [ ] Maximize Service Level (OTIF)
  - [ ] Minimize Inventory
  - [ ] Balance Cost & Service
- **Constraints**:
  - Service Level Target: Slider (85% - 99%)
  - Service Level Confidence: Slider (P(OTIF > target) >= X%)
  - Budget Limit: $ input
  - Inventory DOS Target: min/max inputs

**Example**:
```
Primary Objective: Balance Cost & Service
Service Level Target: OTIF >= 95%
Confidence Requirement: 90% (i.e., P(OTIF >= 95%) >= 90%)
Budget Limit: $500,000
Inventory DOS Range: 10-30 days
```

### 4.3 Screen 2: Parameter Configuration

**Purpose**: Define stochastic parameters and agent selection

**UI Components**:

**Demand Variability**:
- Demand Forecast Source: [Upload CSV | Use Market Demand Config | Historical Average]
- Uncertainty Model: Dropdown [Normal | Poisson | Empirical]
- Variability (%): Slider (0% - 50%)

**Lead Time Variability**:
- Lead Time Model: Dropdown [Deterministic | Normal | Uniform]
- Mean Lead Time: Per lane (table view)
- Std Dev (%): Slider (0% - 30%)

**Supplier Reliability**:
- On-Time Delivery Rate: Per supplier (table view)
- Shortfall Risk (%): Per supplier

**Agent Selection**:
- Agent Strategy: Dropdown [GNN | TRM | LLM | PID | Naive | Custom Mix]
- Agent Parameters: Collapsible panel for advanced config

**Simulation Settings**:
- Number of Scenarios: Input (100 - 10,000)
- Random Seed: Input (for reproducibility)

### 4.4 Screen 3: Plan Generation Progress

**Purpose**: Real-time feedback during backend processing

**UI Components**:
- Progress bar: "Generating scenarios... 347/1000"
- Estimated time remaining
- Live metrics preview (updating as scenarios complete)
- "Cancel" button

**Backend Processing**:
```python
# FastAPI endpoint: POST /api/v1/supply-plan/generate
async def generate_supply_plan(
    config_id: int,
    objectives: PlanObjectives,
    parameters: StochasticParameters,
    num_scenarios: int = 1000
):
    # Launch async task
    task_id = await launch_plan_generation_task(...)
    return {"task_id": task_id, "status": "processing"}

# WebSocket for progress updates
async def stream_plan_progress(websocket, task_id):
    while not task.complete:
        progress = await get_task_progress(task_id)
        await websocket.send_json({
            "scenarios_completed": progress.scenarios,
            "estimated_time_remaining": progress.eta
        })
```

### 4.5 Screen 4: Probabilistic Balanced Scorecard Dashboard

**Purpose**: Display plan results with likelihood distributions

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Supply Plan Balanced Scorecard                         │
│  Config: Complex_SC | Horizon: 52 weeks | Agent: TRM    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Financial]    [Customer]    [Operational]  [Strategic]│  <- Tabs
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Total Supply Chain Cost                        │   │
│  │  Expected: $423,500  (P50)                      │   │
│  │  Range: $380,000 - $470,000 (P10-P90)          │   │
│  │                                                  │   │
│  │  [Cost Distribution Chart - Histogram]          │   │
│  │                                                  │   │
│  │  P(Cost < Budget $500K) = 92%  ✅              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Inventory Carrying Cost                        │   │
│  │  Expected: $85,200 (20% of inventory value)     │   │
│  │  Range: $72,000 - $98,000 (P10-P90)            │   │
│  │                                                  │   │
│  │  [Distribution Chart]                           │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Cash-to-Cash Cycle Time                        │   │
│  │  Expected: 32 days                              │   │
│  │  [CDF Chart showing P(Cycle < X days)]         │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  [Export Plan]  [Compare Scenarios]  [Approve Plan]     │
└─────────────────────────────────────────────────────────┘
```

**Customer Tab Example**:
```
┌─────────────────────────────────────────────────────────┐
│  OTIF (On-Time-In-Full)                                 │
│  Expected: 96.2%  (P50)                                 │
│  Range: 93.5% - 98.1% (P10-P90)                        │
│                                                          │
│  [CDF Chart: P(OTIF > x%)]                             │
│    y-axis: Probability (0-100%)                         │
│    x-axis: OTIF % (80%-100%)                           │
│    Highlighted: P(OTIF > 95%) = 87%  ⚠️                │
│                 (Target: 90% confidence)                │
│                                                          │
│  Risk: 13% chance of missing OTIF target               │
│  Recommendation: Increase safety stock by 8% to achieve│
│                  90% confidence                         │
└─────────────────────────────────────────────────────────┘
```

### 4.6 Visualization Components

**1. Histogram (Probability Distribution)**:
- X-axis: Metric value
- Y-axis: Probability density
- Shaded regions: P10, P50, P90 percentiles
- Vertical line: Target/budget threshold

**2. CDF (Cumulative Distribution Function)**:
- X-axis: Metric value
- Y-axis: Cumulative probability P(Metric < x)
- Highlighted point: P(Metric > target) value
- Color coding: Green (meets confidence), Yellow (marginal), Red (fails)

**3. Risk Heatmap**:
- Grid: Metrics × Nodes
- Color intensity: Risk level (probability of missing target)
- Tooltip: Detailed stats on hover

**4. Scenario Comparison Table**:
| Metric | Scenario A (TRM) | Scenario B (GNN) | Scenario C (LLM) | Best |
|--------|------------------|------------------|------------------|------|
| Total Cost (Expected) | $423K | $410K | $435K | GNN ✅ |
| OTIF (P(>95%)) | 87% | 91% | 89% | GNN ✅ |
| Inventory Turns | 12.3 | 11.8 | 12.7 | Scenario C |

### 4.7 Screen 5: Plan Approval & Export

**Purpose**: Finalize and export plan for execution

**UI Components**:
- **Plan Summary**: Key metrics and recommendations
- **Approval Workflow**: Multi-step approval for enterprise users
- **Export Options**:
  - [ ] CSV (order quantities per node-period)
  - [ ] Excel (detailed scorecard with charts)
  - [ ] API Integration (push to ERP/MES)
  - [ ] PDF Report (executive summary)

**Example Export (CSV)**:
```csv
node_name,item_name,period,order_quantity,expected_inventory,expected_backlog
Plant B1,FG-01,Week 1,120,45,0
Plant B1,FG-01,Week 2,135,52,0
DC A,FG-01,Week 1,200,180,0
...
```

---

## 5. Backend Implementation Architecture

### 5.1 New API Endpoints

**File**: `backend/app/api/endpoints/supply_plan.py` (NEW)

```python
from fastapi import APIRouter, Depends, BackgroundTasks
from app.services.supply_plan_service import SupplyPlanService
from app.schemas.supply_plan import (
    PlanObjectives,
    StochasticParameters,
    SupplyPlanResponse,
    BalancedScorecardReport
)

router = APIRouter()

@router.post("/generate")
async def generate_supply_plan(
    config_id: int,
    objectives: PlanObjectives,
    parameters: StochasticParameters,
    num_scenarios: int = 1000,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Generate optimized supply plan with probabilistic balanced scorecard.

    - Launches async task to run Monte Carlo simulation
    - Returns task_id for progress tracking
    """
    task_id = await supply_plan_service.launch_plan_generation(
        config_id=config_id,
        objectives=objectives,
        parameters=parameters,
        num_scenarios=num_scenarios,
        user_id=current_user.id
    )

    return {"task_id": task_id, "status": "processing"}

@router.get("/status/{task_id}")
async def get_plan_status(task_id: str):
    """Get plan generation progress."""
    status = await supply_plan_service.get_task_status(task_id)
    return status

@router.get("/result/{task_id}")
async def get_plan_result(task_id: str):
    """Retrieve completed plan with balanced scorecard."""
    plan = await supply_plan_service.get_plan_result(task_id)
    return plan

@router.post("/compare")
async def compare_plans(
    plan_ids: List[str],
    metrics: List[str] = None
):
    """Compare multiple plans across selected metrics."""
    comparison = await supply_plan_service.compare_plans(plan_ids, metrics)
    return comparison

@router.post("/approve/{task_id}")
async def approve_plan(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark plan as approved for execution."""
    await supply_plan_service.approve_plan(task_id, current_user.id)
    return {"status": "approved"}

@router.get("/export/{task_id}")
async def export_plan(
    task_id: str,
    format: str = "csv"  # csv, excel, pdf, json
):
    """Export plan in specified format."""
    file_path = await supply_plan_service.export_plan(task_id, format)
    return FileResponse(file_path)
```

### 5.2 New Service Layer

**File**: `backend/app/services/supply_plan_service.py` (NEW)

```python
import numpy as np
from typing import Dict, List
from app.models.supply_chain_config import SupplyChainConfig
from app.services.engine import BeerLine
from app.services.agents import get_policy_by_strategy

class SupplyPlanService:
    """Service for probabilistic supply plan generation."""

    async def launch_plan_generation(
        self,
        config_id: int,
        objectives: PlanObjectives,
        parameters: StochasticParameters,
        num_scenarios: int,
        user_id: int
    ) -> str:
        """Launch background task for plan generation."""

        # Create task record
        task_id = generate_task_id()
        task = PlanGenerationTask(
            task_id=task_id,
            config_id=config_id,
            user_id=user_id,
            num_scenarios=num_scenarios,
            status="processing"
        )
        await db.add(task)

        # Launch async processing
        asyncio.create_task(
            self._run_plan_generation(task_id, config_id, objectives, parameters, num_scenarios)
        )

        return task_id

    async def _run_plan_generation(
        self,
        task_id: str,
        config_id: int,
        objectives: PlanObjectives,
        parameters: StochasticParameters,
        num_scenarios: int
    ):
        """Execute plan generation (runs in background)."""

        # Load supply chain config
        config = await get_supply_chain_config(config_id)

        # Initialize scenario results storage
        scenario_results = []

        # Monte Carlo simulation
        for i in range(num_scenarios):
            # Sample stochastic parameters
            demand_scenarios = sample_demand(config, parameters, horizon=objectives.planning_horizon)
            lead_time_scenarios = sample_lead_times(config, parameters)

            # Run simulation with agent
            agent_policy = get_policy_by_strategy(parameters.agent_strategy)
            beer_line = BeerLine(config, agent_policy)

            # Simulate planning horizon
            for t in range(objectives.planning_horizon):
                beer_line.tick(demand_scenarios[:, t])

            # Collect metrics for this scenario
            metrics = compute_scenario_metrics(beer_line, config)
            scenario_results.append(metrics)

            # Update progress
            await update_task_progress(task_id, i+1, num_scenarios)

        # Aggregate results into probabilistic scorecard
        scorecard = compute_balanced_scorecard(scenario_results, objectives)

        # Optimize plan using stochastic programming
        optimized_plan = optimize_plan(scenario_results, objectives, parameters)

        # Save results
        await save_plan_result(task_id, optimized_plan, scorecard)

        # Mark task complete
        await update_task_status(task_id, "complete")

def compute_balanced_scorecard(
    scenario_results: List[Dict],
    objectives: PlanObjectives
) -> BalancedScorecardReport:
    """Aggregate scenario results into probabilistic balanced scorecard."""

    scorecard = BalancedScorecardReport()

    # Financial Perspective
    total_costs = [s['total_cost'] for s in scenario_results]
    scorecard.financial = {
        "total_cost": {
            "expected": np.mean(total_costs),
            "p10": np.percentile(total_costs, 10),
            "p50": np.percentile(total_costs, 50),
            "p90": np.percentile(total_costs, 90),
            "probability_under_budget": np.mean([c < objectives.budget_limit for c in total_costs]),
            "distribution": total_costs  # For histogram
        },
        "inventory_carrying_cost": {...},
        "cash_to_cash_cycle": {...}
    }

    # Customer Perspective
    otif_values = [s['otif'] for s in scenario_results]
    scorecard.customer = {
        "otif": {
            "expected": np.mean(otif_values),
            "p10": np.percentile(otif_values, 10),
            "p50": np.percentile(otif_values, 50),
            "p90": np.percentile(otif_values, 90),
            "probability_above_target": np.mean([otif > objectives.service_level_target for otif in otif_values]),
            "distribution": otif_values,
            "target": objectives.service_level_target,
            "confidence_requirement": objectives.service_level_confidence
        },
        "fill_rate": {...},
        "backorder_rate": {...}
    }

    # Operational Perspective
    inventory_turns = [s['inventory_turns'] for s in scenario_results]
    scorecard.operational = {
        "inventory_turns": {...},
        "days_of_supply": {...},
        "forecast_accuracy": {...},
        "bullwhip_ratio": {...}
    }

    # Strategic Perspective
    scorecard.strategic = {
        "supply_chain_flexibility": {...},
        "sustainability": {...},
        "supplier_reliability": {...}
    }

    return scorecard

def optimize_plan(
    scenario_results: List[Dict],
    objectives: PlanObjectives,
    parameters: StochasticParameters
) -> OptimizedPlan:
    """
    Optimize plan using stochastic programming.

    Objective: Minimize E[Total Cost]
    Constraints:
      - P(OTIF > target) >= confidence_requirement
      - Capacity constraints per node
      - Budget constraint
    """

    # Use sample average approximation (SAA)
    # Convert stochastic problem to deterministic equivalent

    # Extract order quantities from scenarios
    order_quantities = extract_order_quantities(scenario_results)

    # Define optimization problem
    # ... (use scipy.optimize, CVXPY, or custom solver)

    # Return optimized order quantities per node-period
    return OptimizedPlan(
        order_schedule=optimized_orders,
        production_schedule=optimized_production,
        expected_performance=expected_metrics
    )
```

### 5.3 Stochastic Parameter Sampling

**File**: `backend/app/services/stochastic_sampling.py` (NEW)

```python
import numpy as np
from scipy.stats import norm, poisson, uniform

def sample_demand(
    config: SupplyChainConfig,
    parameters: StochasticParameters,
    horizon: int
) -> np.ndarray:
    """
    Sample demand scenarios for planning horizon.

    Returns: [num_products, num_periods] array of demand samples
    """
    market_demands = get_market_demands(config)

    demand_samples = []
    for market_demand in market_demands:
        if parameters.demand_model == "normal":
            mean = market_demand.mean
            std_dev = mean * parameters.demand_variability
            samples = norm.rvs(loc=mean, scale=std_dev, size=horizon)
        elif parameters.demand_model == "poisson":
            lambda_param = market_demand.mean
            samples = poisson.rvs(mu=lambda_param, size=horizon)
        else:
            # Empirical distribution from historical data
            samples = sample_from_empirical(market_demand.historical_data, horizon)

        demand_samples.append(samples)

    return np.array(demand_samples)

def sample_lead_times(
    config: SupplyChainConfig,
    parameters: StochasticParameters
) -> Dict[int, float]:
    """
    Sample lead times for each lane.

    Returns: {lane_id: sampled_lead_time}
    """
    lanes = get_lanes(config)

    lead_time_samples = {}
    for lane in lanes:
        if parameters.lead_time_model == "deterministic":
            lead_time_samples[lane.id] = lane.lead_time
        elif parameters.lead_time_model == "normal":
            mean = lane.lead_time
            std_dev = mean * parameters.lead_time_variability
            sampled = norm.rvs(loc=mean, scale=std_dev)
            lead_time_samples[lane.id] = max(1, int(sampled))  # Lead time >= 1
        elif parameters.lead_time_model == "uniform":
            lower = lane.lead_time * (1 - parameters.lead_time_variability)
            upper = lane.lead_time * (1 + parameters.lead_time_variability)
            sampled = uniform.rvs(loc=lower, scale=upper-lower)
            lead_time_samples[lane.id] = max(1, int(sampled))

    return lead_time_samples
```

### 5.4 Database Models

**File**: `backend/app/models/supply_plan.py` (NEW)

```python
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Float
from app.db.base_class import Base

class PlanGenerationTask(Base):
    __tablename__ = "plan_generation_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(50), unique=True, index=True)
    config_id = Column(Integer, ForeignKey('supply_chain_configs.id'))
    user_id = Column(Integer, ForeignKey('users.id'))

    # Parameters
    objectives = Column(JSON)  # PlanObjectives
    parameters = Column(JSON)  # StochasticParameters
    num_scenarios = Column(Integer)

    # Status tracking
    status = Column(String(20))  # processing, complete, failed
    progress = Column(Integer, default=0)  # 0-100%

    # Results
    balanced_scorecard = Column(JSON)  # BalancedScorecardReport
    optimized_plan = Column(JSON)  # OptimizedPlan

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    approved = Column(Boolean, default=False)
    approved_by = Column(Integer, ForeignKey('users.id'))

class SupplyPlanScenario(Base):
    __tablename__ = "supply_plan_scenarios"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(50), ForeignKey('plan_generation_tasks.task_id'))
    scenario_number = Column(Integer)

    # Sampled parameters
    demand_samples = Column(JSON)
    lead_time_samples = Column(JSON)

    # Results
    total_cost = Column(Float)
    otif = Column(Float)
    fill_rate = Column(Float)
    inventory_turns = Column(Float)
    bullwhip_ratio = Column(Float)
    # ... other metrics
```

---

## 6. Frontend Implementation

### 6.1 New React Components

**File**: `frontend/src/pages/admin/SupplyPlanGenerator.jsx` (NEW)

```jsx
import React, { useState } from 'react';
import {
  Box, Stepper, Step, StepLabel, Button,
  Card, CardContent, Typography
} from '@mui/material';
import ObjectivesStep from '../../components/supply-plan/ObjectivesStep';
import ParametersStep from '../../components/supply-plan/ParametersStep';
import GenerationProgress from '../../components/supply-plan/GenerationProgress';
import BalancedScorecardDashboard from '../../components/supply-plan/BalancedScorecardDashboard';

const steps = ['Define Objectives', 'Configure Parameters', 'Generate Plan', 'Review Results'];

export default function SupplyPlanGenerator() {
  const [activeStep, setActiveStep] = useState(0);
  const [objectives, setObjectives] = useState({});
  const [parameters, setParameters] = useState({});
  const [taskId, setTaskId] = useState(null);
  const [planResults, setPlanResults] = useState(null);

  const handleGeneratePlan = async () => {
    const response = await api.post('/api/v1/supply-plan/generate', {
      config_id: selectedConfigId,
      objectives,
      parameters,
      num_scenarios: 1000
    });
    setTaskId(response.data.task_id);
    setActiveStep(2);
  };

  const handlePlanComplete = (results) => {
    setPlanResults(results);
    setActiveStep(3);
  };

  return (
    <Box sx={{ width: '100%', p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Supply Plan Generator
      </Typography>

      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {activeStep === 0 && (
        <ObjectivesStep
          objectives={objectives}
          onUpdate={setObjectives}
          onNext={() => setActiveStep(1)}
        />
      )}

      {activeStep === 1 && (
        <ParametersStep
          parameters={parameters}
          onUpdate={setParameters}
          onBack={() => setActiveStep(0)}
          onGenerate={handleGeneratePlan}
        />
      )}

      {activeStep === 2 && (
        <GenerationProgress
          taskId={taskId}
          onComplete={handlePlanComplete}
        />
      )}

      {activeStep === 3 && (
        <BalancedScorecardDashboard
          planResults={planResults}
          onBack={() => setActiveStep(1)}
        />
      )}
    </Box>
  );
}
```

**File**: `frontend/src/components/supply-plan/BalancedScorecardDashboard.jsx` (NEW)

```jsx
import React, { useState } from 'react';
import {
  Box, Tabs, Tab, Card, CardContent, Typography,
  Grid, Alert
} from '@mui/material';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine
} from 'recharts';

export default function BalancedScorecardDashboard({ planResults }) {
  const [selectedTab, setSelectedTab] = useState(0);
  const { balanced_scorecard } = planResults;

  const renderFinancialTab = () => (
    <Grid container spacing={3}>
      {/* Total Cost Card */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Total Supply Chain Cost
            </Typography>
            <Typography variant="h4">
              ${balanced_scorecard.financial.total_cost.expected.toLocaleString()}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Expected (P50)
            </Typography>

            <Box sx={{ mt: 2 }}>
              <Typography variant="body2">
                Range: ${balanced_scorecard.financial.total_cost.p10.toLocaleString()} -
                ${balanced_scorecard.financial.total_cost.p90.toLocaleString()} (P10-P90)
              </Typography>
            </Box>

            {/* Histogram */}
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={prepareHistogramData(balanced_scorecard.financial.total_cost.distribution)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bin" label={{ value: 'Total Cost ($)', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Frequency', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Bar dataKey="count" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>

            {/* Probability of meeting budget */}
            <Alert
              severity={
                balanced_scorecard.financial.total_cost.probability_under_budget >= 0.9
                  ? "success"
                  : "warning"
              }
              sx={{ mt: 2 }}
            >
              P(Cost &lt; Budget) = {(balanced_scorecard.financial.total_cost.probability_under_budget * 100).toFixed(1)}%
            </Alert>
          </CardContent>
        </Card>
      </Grid>

      {/* Additional financial metrics... */}
    </Grid>
  );

  const renderCustomerTab = () => (
    <Grid container spacing={3}>
      {/* OTIF Card with CDF */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              OTIF (On-Time-In-Full)
            </Typography>
            <Typography variant="h4">
              {balanced_scorecard.customer.otif.expected.toFixed(1)}%
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Expected Service Level
            </Typography>

            {/* CDF Chart */}
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={prepareCDFData(balanced_scorecard.customer.otif)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="otif_value"
                  label={{ value: 'OTIF (%)', position: 'insideBottom', offset: -5 }}
                  domain={[85, 100]}
                />
                <YAxis
                  label={{ value: 'Cumulative Probability', angle: -90, position: 'insideLeft' }}
                  domain={[0, 1]}
                />
                <Tooltip
                  formatter={(value) => `${(value * 100).toFixed(1)}%`}
                  labelFormatter={(label) => `OTIF: ${label}%`}
                />
                <Legend />
                <Line type="monotone" dataKey="probability" stroke="#82ca9d" strokeWidth={2} />
                <ReferenceLine
                  x={balanced_scorecard.customer.otif.target}
                  stroke="red"
                  label="Target"
                  strokeDasharray="3 3"
                />
              </LineChart>
            </ResponsiveContainer>

            {/* Confidence Alert */}
            <Alert
              severity={
                balanced_scorecard.customer.otif.probability_above_target >= balanced_scorecard.customer.otif.confidence_requirement
                  ? "success"
                  : "error"
              }
              sx={{ mt: 2 }}
            >
              P(OTIF &gt; {balanced_scorecard.customer.otif.target}%) = {(balanced_scorecard.customer.otif.probability_above_target * 100).toFixed(1)}%
              <br />
              {balanced_scorecard.customer.otif.probability_above_target < balanced_scorecard.customer.otif.confidence_requirement && (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  ⚠️ Does not meet {(balanced_scorecard.customer.otif.confidence_requirement * 100).toFixed(0)}% confidence requirement.
                  Recommendation: Increase safety stock by 8%.
                </Typography>
              )}
            </Alert>
          </CardContent>
        </Card>
      </Grid>

      {/* Additional customer metrics... */}
    </Grid>
  );

  return (
    <Box>
      <Tabs value={selectedTab} onChange={(e, v) => setSelectedTab(v)}>
        <Tab label="Financial" />
        <Tab label="Customer" />
        <Tab label="Operational" />
        <Tab label="Strategic" />
      </Tabs>

      <Box sx={{ mt: 3 }}>
        {selectedTab === 0 && renderFinancialTab()}
        {selectedTab === 1 && renderCustomerTab()}
        {selectedTab === 2 && renderOperationalTab()}
        {selectedTab === 3 && renderStrategicTab()}
      </Box>
    </Box>
  );
}

// Helper functions
function prepareHistogramData(distribution, numBins = 20) {
  // Convert raw distribution to histogram bins
  const min = Math.min(...distribution);
  const max = Math.max(...distribution);
  const binWidth = (max - min) / numBins;

  const bins = Array(numBins).fill(0).map((_, i) => ({
    bin: (min + i * binWidth).toFixed(0),
    count: 0
  }));

  distribution.forEach(value => {
    const binIndex = Math.min(Math.floor((value - min) / binWidth), numBins - 1);
    bins[binIndex].count++;
  });

  return bins;
}

function prepareCDFData(metric) {
  // Convert distribution to empirical CDF
  const sorted = [...metric.distribution].sort((a, b) => a - b);
  return sorted.map((value, index) => ({
    otif_value: value,
    probability: (index + 1) / sorted.length
  }));
}
```

---

## 7. Integration with Existing Infrastructure

### 7.1 Leveraging Existing Components

| Existing Component | Use in Supply Plan Generation |
|--------------------|-------------------------------|
| **BeerLine engine** (`engine.py`) | Core simulation engine for running scenarios |
| **Agent strategies** (`agents.py`, `llm_agent.py`) | Decision-making policies for each scenario |
| **GNN models** (`gnn/temporal_gnn.py`) | Fast inference for scenario generation |
| **TRM models** (`models/trm/`) | Lightweight transformer for 1000+ scenarios |
| **SimPy simulation** (`simulation/`) | Stochastic demand/lead time sampling |
| **WebSocket manager** (`websocket.py`) | Real-time progress updates to frontend |
| **Predictive analytics** (`predictive_analytics_service.py`) | Forecasting components |

### 7.2 New Dependencies

**Backend** (`requirements.txt`):
```
scipy>=1.11.0           # For statistical distributions
cvxpy>=1.4.0           # For optimization (optional)
plotly>=5.18.0         # For advanced visualizations (optional)
```

**Frontend** (`package.json`):
```json
{
  "recharts": "^2.10.0",
  "d3": "^7.8.5"
}
```

---

## 8. Success Metrics

### 8.1 Technical Performance

- **Plan Generation Speed**: < 5 minutes for 1000 scenarios (52-week horizon, 10-node network)
- **UI Responsiveness**: Dashboard loads in < 2 seconds
- **Accuracy**: Probabilistic metrics validated against true simulation outcomes (calibration check)
- **Scalability**: Support 100+ node networks, 10,000+ scenarios

### 8.2 Business Value

- **Decision Quality**: Plans generated improve total cost by 10-30% vs. naive baseline
- **Risk Awareness**: 90% of users find probabilistic metrics more useful than deterministic recommendations
- **Adoption**: 50% of enterprise users use plan generation monthly
- **ROI**: Time-to-plan reduced from weeks (manual) to hours (automated)

---

## 9. Implementation Roadmap

### Phase 1: Core Algorithm (Week 1-2)
- [ ] Implement stochastic parameter sampling (`stochastic_sampling.py`)
- [ ] Build Monte Carlo simulation loop with TRM agent
- [ ] Compute balanced scorecard aggregation
- [ ] Validate with small-scale tests (100 scenarios, 13-week horizon)

### Phase 2: Backend API (Week 2-3)
- [ ] Create `supply_plan.py` API endpoints
- [ ] Implement `SupplyPlanService` with async task management
- [ ] Add database models (`PlanGenerationTask`, `SupplyPlanScenario`)
- [ ] WebSocket progress streaming

### Phase 3: Frontend Dashboard (Week 3-4)
- [ ] Build `SupplyPlanGenerator` stepper UI
- [ ] Create `BalancedScorecardDashboard` with 4 perspectives
- [ ] Implement histogram, CDF, risk heatmap visualizations
- [ ] Plan comparison and export features

### Phase 4: Optimization (Week 4-5)
- [ ] Implement stochastic programming optimizer
- [ ] Add scenario-based optimization using SAA
- [ ] Integrate with agent strategies (GNN, TRM, LLM)
- [ ] Performance tuning (parallel scenario execution)

### Phase 5: Testing & Documentation (Week 5-6)
- [ ] End-to-end testing with Complex_SC configuration
- [ ] Validate probabilistic calibration (P(X) matches empirical frequency)
- [ ] User acceptance testing
- [ ] Documentation and training materials

**Total Estimated Time**: 5-6 weeks

---

## 10. Competitive Differentiation

### vs. Kinaxis RapidResponse

| Feature | Kinaxis | Beer Game Platform |
|---------|---------|-------------------|
| **Probabilistic Planning** | Limited scenario analysis | Native Monte Carlo with likelihood distributions |
| **AI/ML Integration** | Add-on modules | Core GNN/TRM/LLM agents |
| **Deployment Time** | 6-18 months | Days to weeks |
| **Cost** | $100K-$500K/user/year | $10K/user/year |
| **Transparency** | "Black box" recommendations | Explainable AI with scenario drill-down |

### vs. SAP IBP

| Feature | SAP IBP | Beer Game Platform |
|---------|---------|-------------------|
| **Risk Visualization** | Basic risk dashboard | Full probabilistic balanced scorecard with CDFs |
| **Stochastic Optimization** | Safety stock buffers | Monte Carlo + stochastic programming |
| **Forecast Accuracy** | MAPE, WMAPE | Probabilistic forecasting with uncertainty quantification |
| **Integration Complexity** | Requires SAP ecosystem | Standalone or integrate via API |

### vs. OMP Unison Planning

| Feature | OMP | Beer Game Platform |
|---------|-----|-------------------|
| **Scenario Analysis** | Scenario comparison dashboards | 1000+ scenarios with probability distributions |
| **Analytics** | Role-specific KPIs | Balanced scorecard with 4 perspectives |
| **Planning Horizon** | Strategic to operational | Configurable (13-104 weeks) |
| **Customization** | Requires OMP consultants | Open platform with API access |

---

## 11. References

### Industry Sources
- [Top 11 Supply Chain KPIs – Guide for 2026](https://www.mrpeasy.com/blog/supply-chain-kpis/)
- [The Supply Chain Planning KPIs you Need to Know](https://demand-planning.com/2023/11/20/the-supply-chain-planning-kpis-you-need-to-know/)
- [Kinaxis vs SAP 2026](https://www.gartner.com/reviews/market/supply-chain-planning-solutions/compare/kinaxis-vs-sap)
- [OMP Unison Planning Reviews](https://www.gartner.com/reviews/market/supply-chain-planning-solutions/vendor/omp/product/unison-planning)

### Balanced Scorecard Framework
- [Mastering Logistics with Balanced Scorecard](https://www.numberanalytics.com/blog/balanced-scorecard-logistics-supply-chain-management)
- [Balanced Scorecard Basics](https://balancedscorecard.org/bsc-basics-overview/)
- [Performance measurement of supply chain management: A balanced scorecard approach](https://www.sciencedirect.com/science/article/abs/pii/S0360835207000617)

### Stochastic Optimization
- [Machine Learning for Master Production Scheduling: Combining probabilistic forecasting with stochastic optimisation](https://www.sciencedirect.com/science/article/pii/S0957417425002088)
- [A multi-stage stochastic programming approach for overhaul and supply chain planning](https://link.springer.com/article/10.1007/s12351-025-00988-0)
- [The Impact of Probabilistic Planning to Supply Chain Resilience](https://www.aimms.com/story/probabilistic-planning-supply-chain-resilence/)
- [Advanced Supply Chain Planning with Probabilistic Forecasting](https://www.toolsgroup.com/blog/advanced-supply-chain-planning-probabilistic-forecasting/)

### SAP IBP Metrics
- [SAP IBP Forecast accuracy](https://answers.sap.com/questions/723273/ibp-forecast-accuracy.html)
- [Forecast improvement with SAP IBP](https://www.scplan-consulting.de/sap-ibp-forecast-improvement/)
- [SAP IBP- Improving accuracy reporting with WMAPE](https://valuechainplanning.com/blog-details/104)

### Risk & Dashboard Design
- [7 Key Supply Chain Dashboard Examples](https://www.gooddata.com/blog/supply-chain-dashboard-examples/)
- [Supply Chain Risk Management Platform](https://www.z2data.com/)
- [Take the Risk out of Your Supply Chain by Planning Ahead](https://blogs.sap.com/2023/04/18/take-the-risk-out-of-your-supply-chain-by-planning-ahead/)

---

**Next Steps**:
1. Review and approve this design document
2. Prioritize implementation phases
3. Allocate development resources
4. Begin Phase 1: Core algorithm implementation


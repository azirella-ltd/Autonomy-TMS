# Supply Planning vs Execution - Architectural Redesign

**Date**: 2026-01-18
**Status**: 🔄 **CRITICAL DESIGN REVISION**

---

## Problem Statement

The current prototype implementation conflates **supply chain planning** with **supply chain execution**:

- **Current Implementation**: Period-by-period simulation mimicking The Beer Game execution (order-level decisions)
- **Correct Approach**: Generate strategic plans (purchase orders, manufacturing orders, stock transfers) over longer horizons

---

## Key Distinctions

| Aspect | **Execution** (The Beer Game) | **Planning** (Supply Plan Generation) |
|--------|-------------------------------|---------------------------------------|
| **Time Horizon** | Short-term (weeks) | Medium to long-term (months, quarters) |
| **Granularity** | Individual orders, period-by-period | Aggregate demand, batched orders |
| **Decisions** | How much to order this week | When to initiate POs, MOs, STOs |
| **Inputs** | Actual customer orders | Forecasted demand distributions |
| **Outputs** | Order quantities per period | Purchase plans, production schedules, inventory targets |
| **Variability** | Reacts to actual demand | Optimizes against demand uncertainty |
| **System Type** | Execution (OMS, WMS) | Planning (APS, S&OP) |

---

## Current Prototype Issues

### What We Built (Incorrect for Planning)
```python
# Period-by-period execution simulation
for t in range(horizon):
    period_demand = get_customer_demand(t)
    for node in nodes:
        incoming_demand = downstream_orders[node]
        shipped = min(inventory, incoming_demand)
        order_quantity = policy.compute_order(...)  # Execution-level decision
```

This is **execution simulation** - it mimics how The Beer Game operates at the order level.

### What We Should Build (Correct for Planning)

**Option A: Optimization-Based Planning**
```python
# Strategic planning over entire horizon
def generate_supply_plan(demand_forecast, network, constraints):
    # Decision variables
    purchase_orders = {}  # {(supplier, item, week): quantity}
    manufacturing_orders = {}  # {(plant, item, week): quantity}
    stock_transfers = {}  # {(from_dc, to_dc, item, week): quantity}
    inventory_levels = {}  # {(node, item, week): quantity}

    # Objective: Minimize total cost
    total_cost = (
        inventory_carrying_cost(inventory_levels) +
        ordering_cost(purchase_orders, manufacturing_orders) +
        transfer_cost(stock_transfers) +
        shortage_penalty(demand_forecast, inventory_levels)
    )

    # Constraints
    # 1. Inventory flow balance
    # 2. Production capacity limits
    # 3. Service level requirements
    # 4. Lead time constraints

    # Solve optimization problem
    optimal_plan = solve_milp(total_cost, constraints)

    return {
        "purchase_orders": optimal_plan.purchase_orders,
        "manufacturing_orders": optimal_plan.manufacturing_orders,
        "stock_transfers": optimal_plan.stock_transfers,
        "inventory_targets": optimal_plan.inventory_levels
    }
```

**Option B: Policy-Based Planning (Simplified)**
```python
# Use planning policies (not execution policies)
def generate_supply_plan_policy(demand_forecast, network, params):
    plan = {}

    for item in items:
        for node in network:
            # Calculate planning parameters
            forecast = demand_forecast[item][node]
            lead_time = get_total_lead_time(node, item)

            # Determine reorder point and order quantity
            safety_stock = calculate_safety_stock(
                forecast.std_dev,
                lead_time,
                service_level=0.95
            )
            reorder_point = forecast.mean * lead_time + safety_stock
            economic_order_quantity = calculate_eoq(
                forecast.mean,
                ordering_cost,
                holding_cost
            )

            # Generate purchase/manufacturing orders for planning horizon
            inventory_position = current_inventory + pipeline_orders
            for week in planning_horizon:
                if inventory_position < reorder_point:
                    if node.type == "MANUFACTURER":
                        plan["manufacturing_orders"].append({
                            "plant": node,
                            "item": item,
                            "quantity": economic_order_quantity,
                            "week": week
                        })
                    else:
                        plan["purchase_orders"].append({
                            "supplier": node.upstream_supplier,
                            "item": item,
                            "quantity": economic_order_quantity,
                            "week": week
                        })

                    inventory_position += economic_order_quantity

                inventory_position -= forecast.weekly_demand[week]

    return plan
```

---

## Revised Architecture

### Phase 1: Core Planning Algorithm (REVISED)

**Input**:
- Supply chain network configuration
- Demand forecast distributions (mean, std dev, percentiles)
- Lead times (purchase, manufacturing, transfer)
- Cost parameters (holding, ordering, shortage)
- Service level targets

**Processing**:
1. **Demand Aggregation**: Aggregate stochastic demand forecasts by item, node, time bucket
2. **Safety Stock Calculation**: Compute safety stock levels using newsvendor model or service level formulas
3. **Replenishment Planning**: Generate purchase orders, manufacturing orders, stock transfers
4. **Monte Carlo Simulation**: Simulate plan performance across scenarios
5. **Scorecard Generation**: Aggregate probabilistic metrics

**Output**:
- **Purchase Orders**: List of {supplier, item, quantity, week}
- **Manufacturing Orders**: List of {plant, item, quantity, week}
- **Stock Transfer Orders**: List of {from_dc, to_dc, item, quantity, week}
- **Inventory Targets**: Safety stock levels, reorder points per node/item
- **Probabilistic Metrics**: Expected costs, service levels, P10/P50/P90 ranges

### Comparison with AWS Supply Chain

From [AWS Supply Planning](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/supply-planning.html):

**AWS Supply Chain Planning Outputs**:
- Recommended purchase orders
- Production plans
- Inventory positioning recommendations
- What-if scenario analysis

**Our System (Revised)**:
- ✅ Purchase orders (planned)
- ✅ Manufacturing orders (planned)
- ✅ Stock transfer orders (planned)
- ✅ Probabilistic what-if analysis (Monte Carlo)
- ✅ Balanced scorecard metrics

---

## Implementation Approaches

### Option 1: Deterministic + Monte Carlo Evaluation (RECOMMENDED)

**Approach**:
1. Generate a **deterministic plan** using classical planning policies (ROP, EOQ, safety stock formulas)
2. **Evaluate** the plan using Monte Carlo simulation with stochastic demand
3. Compute **probabilistic metrics** (P10/P50/P90, P(service > target))

**Pros**:
- Separates planning from evaluation
- Faster than stochastic optimization
- Sufficient for prototype demonstration
- Aligns with classical supply planning literature

**Cons**:
- Plan is not stochastically optimized
- May not be globally optimal

**Implementation**:
```python
# 1. Generate deterministic plan
plan = generate_deterministic_plan(
    demand_forecast,
    network,
    params={
        "service_level": 0.95,
        "review_period": 1,  # weekly
        "ordering_policy": "ROP"  # Reorder Point
    }
)

# 2. Evaluate plan with Monte Carlo
scorecard = evaluate_plan_monte_carlo(
    plan,
    stochastic_params,
    num_scenarios=1000
)
```

### Option 2: Stochastic Optimization (Phase 4)

**Approach**:
- Use **Sample Average Approximation (SAA)** or **stochastic programming**
- Directly optimize plan under uncertainty
- Generate plans that are robust to demand variability

**Pros**:
- Stochastically optimal
- Accounts for uncertainty in planning (not just evaluation)

**Cons**:
- Computationally expensive
- Requires optimization solver (Gurobi, CPLEX)
- More complex implementation

**Deferred to Phase 4** as originally designed.

### Option 3: Simulation-Based Planning (Current - INCORRECT)

**Approach**:
- Run period-by-period simulation
- Let agents make ordering decisions each period
- Aggregate results

**Assessment**:
- ❌ This is **execution**, not planning
- ❌ Outputs are execution traces, not strategic plans
- ❌ Does not align with supply planning paradigm

---

## Recommended Path Forward

### Phase 1 (REVISED): Deterministic Planning + Monte Carlo Evaluation

**Step 1**: Implement deterministic planning policies
- Calculate safety stock levels using service level formulas
- Generate reorder points for each node/item
- Create purchase orders, manufacturing orders based on ROP policy
- Output: Strategic plan over planning horizon

**Step 2**: Evaluate plan with Monte Carlo
- Sample demand scenarios
- Simulate plan execution under each scenario
- Track inventory levels, stockouts, costs
- Aggregate into balanced scorecard

**Step 3**: Generate recommendations
- Based on probabilistic metrics
- Suggest adjustments to safety stock, reorder points

### Phase 2: Backend API (NO CHANGE)
- API remains the same
- Inputs: stochastic parameters, objectives
- Outputs: plan + scorecard

### Phase 3: Frontend Dashboard (NO CHANGE)
- Display purchase orders, manufacturing orders, stock transfers
- Visualize probabilistic metrics

### Phase 4: Stochastic Optimization (AS ORIGINALLY PLANNED)
- Replace deterministic planning with SAA
- Optimize plan directly under uncertainty

### Phase 5: Execution Simulation (NEW)
- **Optional**: Add execution simulation using The Beer Game engine
- Compare planned vs actual performance
- This is **separate** from planning

---

## Key Design Corrections

### Before (Incorrect)
- **System Type**: Execution simulator
- **Output**: Order quantities per period (execution trace)
- **Paradigm**: Period-by-period reactive decisions

### After (Correct)
- **System Type**: Supply planner
- **Output**: Purchase orders, manufacturing orders, stock transfers (strategic plan)
- **Paradigm**: Horizon-wide optimization with probabilistic evaluation

---

## Impact on Existing Prototype

**Files to Modify**:
1. `backend/app/services/monte_carlo_planner.py`
   - **Before**: `run_scenario_simulation()` does period-by-period execution
   - **After**: `generate_deterministic_plan()` creates strategic plan, then `evaluate_plan()` simulates execution

2. `backend/app/services/stochastic_sampling.py`
   - **No change**: Still samples demand, lead times, reliability

3. `backend/app/schemas/supply_plan.py`
   - **Add**: Plan output schemas (PurchaseOrder, ManufacturingOrder, StockTransferOrder)

**Estimated Rework**: 2-3 days
- Day 1: Implement deterministic planning policies (safety stock, ROP, EOQ)
- Day 2: Refactor Monte Carlo to evaluate plans (not simulate execution)
- Day 3: Update schemas and test

---

## References

- [AWS Supply Chain - Supply Planning](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/supply-planning.html)
- [AWS Supply Chain - Work Orders](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/work-order.html)
- Silver, Pyke, Peterson (1998) - Inventory Management and Production Planning and Scheduling
- Simchi-Levi, Kaminsky, Simchi-Levi (2008) - Designing and Managing the Supply Chain

---

## Next Steps

1. **User Confirmation**: Approve revised architectural approach
2. **Refactor Prototype**: Implement deterministic planning + Monte Carlo evaluation
3. **Continue Phase 2**: Backend API (with updated plan output schemas)
4. **Phase 3**: Frontend to display purchase/manufacturing/transfer orders

**Status**: ⏸️ **AWAITING APPROVAL FOR ARCHITECTURAL REVISION**

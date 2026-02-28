# Monte Carlo Simulation - Quick Start Guide

Get started with probabilistic supply chain planning in under 5 minutes!

---

## Prerequisites

1. **Backend running**: `make up` or `docker compose up`
2. **Database initialized**: Tables created via `make db-bootstrap`
3. **Frontend running**: Navigate to http://localhost:8088
4. **User logged in**: Use systemadmin@autonomy.ai / Autonomy@2026

---

## Step 1: Create Your First Simulation

### Via UI (Recommended)

1. **Navigate** to Planning & Optimization → Monte Carlo Simulation
2. **Click** "New Simulation" button
3. **Fill in the form**:
   - **Name**: "My First Simulation"
   - **Description**: "Testing probabilistic planning"
   - **Supply Chain Configuration**: Select "Default TBG" (or your config)
   - **Number of Scenarios**: 1000 (good balance of accuracy and speed)
   - **Planning Horizon**: 52 weeks
   - **Random Seed**: Leave blank (or use 42 for reproducibility)
4. **Click** "Create & Run"

The simulation will start running in the background!

### Via API

```bash
curl -X POST http://localhost:8088/api/monte-carlo/runs \
  -H "Content-Type: application/json" \
  -H "Cookie: your-auth-cookie" \
  -d '{
    "name": "My First Simulation",
    "description": "Testing probabilistic planning",
    "supply_chain_config_id": 1,
    "num_scenarios": 1000,
    "planning_horizon_weeks": 52,
    "group_id": 1
  }'
```

---

## Step 2: Monitor Progress

### Via UI

The simulations list auto-refreshes every 5 seconds.

**Status Indicators**:
- 🟡 **QUEUED**: Waiting to start
- 🔵 **RUNNING**: In progress (see progress bar)
- 🟢 **COMPLETED**: Ready to view results
- 🔴 **FAILED**: Error occurred
- ⚪ **CANCELLED**: Manually stopped

**Progress Tracking**:
- Progress bar shows % completion
- "Scenarios Completed" column shows X / N

### Via API

```bash
# Get run status
curl http://localhost:8088/api/monte-carlo/runs/1

# Response includes:
# - status: "RUNNING", "COMPLETED", etc.
# - progress_percent: 45.5
# - scenarios_completed: 455
```

---

## Step 3: View Results

### Via UI

1. **Wait** for status to show "COMPLETED" (typically 5-20 minutes for 1000 scenarios)
2. **Click** the chart icon (📊) in the Actions column
3. **Explore** the three tabs:

#### **Summary Tab**

View high-level KPIs with confidence intervals:

| Metric | Mean | P5 | P95 | Interpretation |
|--------|------|----|----|----------------|
| **Total Cost** | $12,500 | $10,200 | $15,800 | 90% of scenarios fall between $10.2K-$15.8K |
| **Service Level** | 94.2% | 89.5% | 98.1% | Expected service level ~94%, worst case 89.5% |
| **Final Inventory** | 850 | 450 | 1,350 | Ending inventory ranges from 450-1350 units |
| **Final Backlog** | 120 | 0 | 380 | Some scenarios end with no backlog, others with 380 |

**Risk Metrics Cards**:
- **Stockout Probability**: 15% → Alert if >10%
- **Overstock Probability**: 22% → Alert if >20%
- **Capacity Violation Probability**: 3% → OK if <5%

#### **Time Series Tab**

Interactive charts showing week-by-week metrics with **confidence bands**:

- **Shaded Blue Area (Light)**: P5-P95 range (90% of scenarios)
- **Shaded Blue Area (Dark)**: P25-P75 range (50% of scenarios)
- **Blue Line**: Mean (expected) trajectory

**Example Interpretation**:
```
Week 20 Inventory:
- Mean: 800 units (blue line)
- P25-P75: 650-950 units (dark band) → 50% of scenarios
- P5-P95: 450-1,200 units (light band) → 90% of scenarios
```

#### **Risk Alerts Tab**

Automated risk detection with recommendations:

**Active Alerts** (need acknowledgement):
- 🔴 **CRITICAL**: Capacity violation probability 18% > 15%
  - **Recommendation**: Review production capacity and consider adding shifts or outsourcing
- 🟡 **MEDIUM**: Stockout probability 12% > 10%
  - **Recommendation**: Increase safety stock levels or expedite supplier lead times

**Acknowledged Alerts**: Historical record of past alerts

### Via API

```bash
# Get summary statistics
curl http://localhost:8088/api/monte-carlo/runs/1 | jq '.summary_statistics'

# Get time-series with confidence bands
curl "http://localhost:8088/api/monte-carlo/runs/1/time-series?metric_names=inventory,backlog"

# Get risk alerts
curl http://localhost:8088/api/monte-carlo/runs/1/risk-alerts
```

---

## Step 4: Take Action

Based on your results, you can:

### 1. **Adjust Safety Stock** (if high stockout risk)

```bash
# Update inventory policy to increase safety stock
curl -X PUT http://localhost:8088/api/sc-planning/inv-policies/1 \
  -d '{
    "ss_policy": "abs_level",
    "ss_quantity": 500,  # Increased from 300
    "ss_days": null
  }'
```

### 2. **Modify MPS Plan** (if capacity violations)

Navigate to Planning & Optimization → Master Production Scheduling:
- Reduce production quantities in constrained weeks
- Smooth out production peaks
- Re-run Monte Carlo to validate changes

### 3. **Increase Capacity** (if persistent capacity issues)

Update production capacity in supply chain configuration:
- Admin → Supply Chain Configs → Edit "Default TBG"
- Increase capacity for bottleneck resources
- Re-run simulation to see impact

### 4. **Re-run with Different Parameters**

Create a new simulation with:
- **More scenarios**: 5000 instead of 1000 for better accuracy
- **Different horizon**: 13 weeks for quarterly planning
- **Fixed seed**: 42 for reproducible comparisons

---

## Common Use Cases

### Use Case 1: MPS Plan Validation

**Objective**: Validate that a proposed production plan is feasible under uncertainty

```bash
# Step 1: Create MPS plan
curl -X POST http://localhost:8088/api/mps/plans \
  -d '{
    "name": "Q1 2026 Production Plan",
    "supply_chain_config_id": 1,
    "planning_horizon_weeks": 13
  }'

# Step 2: Run Monte Carlo on the plan
curl -X POST http://localhost:8088/api/monte-carlo/runs \
  -d '{
    "name": "Q1 Plan Risk Analysis",
    "supply_chain_config_id": 1,
    "mps_plan_id": 1,
    "num_scenarios": 2000,
    "planning_horizon_weeks": 13,
    "group_id": 1
  }'

# Step 3: Check risk alerts
# If stockout_probability > 15%, plan is too aggressive
# If overstock_probability > 25%, plan is too conservative
```

### Use Case 2: Sensitivity Analysis

**Objective**: Compare two scenarios (optimistic vs pessimistic demand)

```bash
# Scenario A: Base case with seed 100
curl -X POST http://localhost:8088/api/monte-carlo/runs \
  -d '{
    "name": "Base Case",
    "supply_chain_config_id": 1,
    "num_scenarios": 1000,
    "random_seed": 100,
    "group_id": 1
  }'

# Scenario B: High demand variant (would need to modify demand distributions first)
# Then run Monte Carlo and compare Total Cost P95 values
```

### Use Case 3: Multi-Product Planning

**Objective**: Identify which products have highest stockout risk

```bash
# Run simulation on multi-product config
curl -X POST http://localhost:8088/api/monte-carlo/runs \
  -d '{
    "name": "Multi-Product Risk Analysis",
    "supply_chain_config_id": 2,  # "Three FG TBG" config
    "num_scenarios": 2000,
    "planning_horizon_weeks": 52,
    "group_id": 1
  }'

# Check time-series data per product
curl "http://localhost:8088/api/monte-carlo/runs/2/time-series?metric_names=inventory&product_id=1"
curl "http://localhost:8088/api/monte-carlo/runs/2/time-series?metric_names=inventory&product_id=2"
curl "http://localhost:8088/api/monte-carlo/runs/2/time-series?metric_names=inventory&product_id=3"
```

---

## Understanding the Statistics

### Percentiles (P5, P50, P95)

**P5 (5th percentile)**:
- 5% of scenarios are **below** this value
- 95% of scenarios are **above** this value
- Represents an **optimistic** outcome

**P50 (50th percentile / Median)**:
- Half of scenarios are below, half above
- More robust than mean (not affected by outliers)
- Represents the **typical** outcome

**P95 (95th percentile)**:
- 95% of scenarios are **below** this value
- 5% of scenarios are **above** this value
- Represents a **pessimistic** outcome

### Example Interpretation

```
Total Cost:
  Mean: $12,500
  P5: $10,200
  P95: $15,800

Interpretation:
- Expected cost is $12,500
- There's a 90% chance cost will be between $10,200 and $15,800
- There's a 5% chance cost exceeds $15,800 (tail risk)
- Budget for ~$16,000 to be safe (P95 + buffer)
```

### Confidence Bands on Charts

**P5-P95 Band (90% Confidence Interval)**:
- 90% of all scenario paths fall within this band
- Wide band = high uncertainty
- Narrow band = low uncertainty

**P25-P75 Band (50% Confidence Interval)**:
- The "most likely" range
- Half of scenarios fall within this darker band

**Example**:
```
Week 30 Inventory Chart:
- If P5-P95 band is 300-1500 units → HIGH uncertainty
- If P25-P75 band is 700-1100 units → Typical range is 700-1100
- Mean line at 900 units → Expected inventory
```

---

## Performance Tips

### Execution Time Guidelines

| Scenarios | Horizon | Approx Time | Use Case |
|-----------|---------|-------------|----------|
| 100 | 13 weeks | 1-2 min | Quick test |
| 1000 | 13 weeks | 10-20 min | Quarterly plan validation |
| 1000 | 52 weeks | 30-60 min | Annual planning |
| 5000 | 52 weeks | 2-4 hours | High-precision analysis |

**Tips**:
- Start with 100-500 scenarios for testing
- Use 1000-2000 for production planning decisions
- Use 5000+ for critical decisions or publications
- Run long simulations overnight or on weekends

### Reducing Execution Time

1. **Shorter Horizon**: 13 weeks instead of 52
2. **Fewer Scenarios**: 500 instead of 1000 (still useful)
3. **Simpler Config**: Fewer nodes/lanes/items
4. **Background Execution**: Runs don't block other work

### When to Use Different Scenario Counts

**100-500 scenarios**:
- Quick "sanity check" tests
- Early-stage design exploration
- Rapid iteration during configuration changes

**1000-2000 scenarios**:
- Standard production planning
- MPS plan validation
- Weekly/monthly planning cycles

**5000-10000 scenarios**:
- High-stakes decisions (capacity investments)
- Regulatory/compliance reporting
- Academic research or publications
- Very rare tail event analysis (1-in-1000 risks)

---

## Troubleshooting

### Simulation Stuck at 0% Progress

**Symptoms**: Status shows "RUNNING" but progress stays at 0% for >5 minutes

**Causes**:
- Background task failed silently
- Database connection issue
- Out of memory (very large configs)

**Solutions**:
1. Check backend logs: `docker compose logs backend | tail -100`
2. Restart backend: `make restart-backend`
3. Cancel and retry: Click "Cancel" button, then create new simulation

### No Time-Series Data in Results

**Symptoms**: Completed simulation but time-series charts show "No data available"

**Cause**: Simplified simulation in `engine.py` placeholder code needs full integration

**Solution**:
- Current implementation uses placeholder simulation
- Future: Integrate with `BeerGameExecutionAdapter` for realistic data
- Workaround: Summary statistics and risk metrics still work

### Risk Alerts Not Generating

**Symptoms**: All risk probabilities show 0%

**Causes**:
- Thresholds too high for the simulation
- All scenarios performed perfectly (rare!)
- Issue with simulation logic

**Solutions**:
1. Check summary_statistics in run details
2. Verify scenarios actually have stockouts/overstock (check scenario records)
3. Adjust thresholds in `engine.py` if needed

### Out of Memory Errors

**Symptoms**: Simulation fails with FAILED status, logs show memory errors

**Causes**:
- Too many scenarios (>10,000)
- Large supply chain configuration
- `all_scenario_values` storing full arrays

**Solutions**:
1. Reduce num_scenarios to 5000 or less
2. Increase Docker memory limit in docker-compose.yml
3. Modify code to skip storing `all_scenario_values`

---

## Next Steps

**Congratulations!** You've run your first Monte Carlo simulation.

### Learn More

1. **Read** [MONTE_CARLO_IMPLEMENTATION.md](MONTE_CARLO_IMPLEMENTATION.md) for technical details
2. **Explore** [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md) for stochastic planning theory
3. **Review** Academic papers in `docs/Knowledge/` for best practices

### Advanced Topics

- **Latin Hypercube Sampling**: Better coverage with fewer scenarios
- **Importance Sampling**: Focus on high-impact tail events
- **Stochastic Optimization**: Find robust plans across scenarios
- **Scenario Reduction**: Cluster similar scenarios for faster analysis

### Integration

- **MPS Planning**: Validate production schedules under uncertainty
- **GNN Models**: Use ML-generated demand forecasts in scenarios
- **LLM Agents**: Have AI agents analyze risk alerts and recommend actions
- **Beer Game**: Run Monte Carlo on live game state for adaptive replanning

---

## Support

**Issues**: https://github.com/anthropics/the-beer-game/issues
**Documentation**: See `/docs` directory
**API Docs**: http://localhost:8000/docs (when backend running)

---

**Happy Probabilistic Planning!** 🎲📊

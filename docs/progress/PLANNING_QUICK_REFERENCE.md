# Planning Logic Quick Reference Card

**For comprehensive details, see [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md)**

---

## 🎯 Core Principles

### Variable Classification
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand
- **Control Variables** (deterministic): Inventory targets, costs, policies

### Hierarchical Override Logic
```
Item-Node > Item > Node > Config
(most specific wins)
```

---

## 📊 4 Inventory Policy Types

| Policy | Code | Calculation | Use Case |
|--------|------|-------------|----------|
| **Absolute Level** | `abs_level` | `SS = ss_quantity` | Stable products, known requirements |
| **Days of Demand** | `doc_dem` | `SS = ss_days × avg_daily_demand` | Mature products, stable history |
| **Days of Forecast** | `doc_fcst` | `SS = ss_days × avg_daily_forecast` | New products, changing demand |
| **Service Level** | `sl` | `SS = z × σ_demand × √(lead_time)` | Critical/high-value products |

### Service Level Z-Scores
| Service Level | Z-Score | Description |
|---------------|---------|-------------|
| 80% | 0.84 | Standard |
| 90% | 1.28 | High |
| 95% | 1.65 | Very High |
| 98% | 2.05 | Premium |
| 99% | 2.33 | 3-sigma |

---

## 📈 20 Distribution Types

### Basic
- `deterministic` - Fixed value
- `uniform` - Equal probability in range
- `normal` - Bell curve

### Right-Skewed (for durations)
- `lognormal` - Lead times
- `gamma` - Flexible skew
- `weibull` - Time-to-failure
- `exponential` - Memoryless

### Bounded
- `beta` - Percentages/yields [0,1]
- `truncated_normal` - Normal with hard bounds

### Discrete
- `poisson` - Demand counts
- `binomial` - Success/failure
- `negative_binomial` - Overdispersed

### Advanced
- `empirical` - Historical data
- `mixture` - Normal ops + disruptions
- `categorical` - Named categories

**Example Distribution JSON**:
```json
{
  "type": "lognormal",
  "mean": 7.0,
  "stddev": 2.0,
  "min": 3.0,
  "max": 14.0
}
```

---

## 🎲 Probabilistic Planning Workflow

```
1. Sample N scenarios (N=1000)
   ├─ Demand from distribution
   ├─ Lead times from distribution
   └─ Yields from distribution

2. For each scenario:
   ├─ Run simulation with agent (TRM/GNN/LLM/PID)
   └─ Collect metrics (cost, OTIF, inventory turns)

3. Aggregate results:
   ├─ Expected values: E[metric]
   ├─ Percentiles: P10, P50, P90
   └─ Probabilities: P(metric > target)

4. Optimize plan (stochastic programming):
   ├─ Minimize: E[Total Cost]
   └─ Subject to: P(OTIF > 95%) >= 0.90

5. Generate balanced scorecard:
   ├─ Financial: E[Cost], P(Cost < Budget)
   ├─ Customer: E[OTIF], P(OTIF > target)
   ├─ Operational: E[Inventory Turns], E[DOS]
   └─ Strategic: E[Bullwhip], Supplier risk
```

---

## 🏆 Balanced Scorecard (4 Perspectives)

| Perspective | Key Metrics |
|-------------|-------------|
| **Financial** | Total cost, Inventory carrying cost, Cash-to-cash cycle |
| **Customer** | OTIF, Fill rate, Backorder rate, Service level |
| **Operational** | Inventory turns, Days of supply, Forecast accuracy, Bullwhip |
| **Strategic** | Flexibility, Sustainability, Supplier reliability, FVA |

---

## 🤖 Agent Selection

| Agent | Speed | Accuracy | Use Case |
|-------|-------|----------|----------|
| **TRM** | <10ms | 90-95% | Fast scenario simulation (1000+) |
| **GNN** | ~100ms | 85-92% | Deep learning optimization |
| **LLM** | ~2s | Varies | Explainable AI, validation |
| **PID** | <1ms | 70-80% | Deterministic baseline |
| **Naive** | <1ms | 40-50% | Benchmark only |

---

## 📋 Common Algorithms

### Base Stock Policy
```python
order_qty = max(0, target_inventory - (on_hand + on_order))
```

### (s,S) Policy
```python
if on_hand + on_order <= reorder_point:
    order_qty = order_up_to_level - (on_hand + on_order)
else:
    order_qty = 0
```

### Safety Stock (Service Level)
```python
SS = z_score * demand_std_dev * sqrt(lead_time)
```

---

## ✅ Testing Checklist

Before deploying planning logic:

- [ ] All distribution types unit tested
- [ ] All 4 policy types validated
- [ ] Hierarchical override logic tested
- [ ] Safety stock calculations validated
- [ ] Monte Carlo produces consistent results (fixed seed)
- [ ] Balanced scorecard probabilities sum to 100%
- [ ] Performance <5 min for 1000 scenarios
- [ ] Historical data validation (if available)

---

## 📚 Key References

**Design Documents**:
- [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md) - Full knowledge base (1100+ lines)
- [SUPPLY_PLAN_GENERATION_DESIGN.md](SUPPLY_PLAN_GENERATION_DESIGN.md) - Probabilistic planning
- [AWS_SC_STOCHASTIC_MODELING_DESIGN.md](AWS_SC_STOCHASTIC_MODELING_DESIGN.md) - Stochastic framework
- [AWS_SC_POLICY_TYPES_IMPLEMENTATION.md](AWS_SC_POLICY_TYPES_IMPLEMENTATION.md) - Policy types

**Key PDFs** (`docs/Knowledge/`):
- `01_MPS_Material_Requirements_Planning_Academic.pdf` - MPS/MRP basics
- `04_Kinaxis_Master_Production_Scheduling.pdf` (1.7MB) - Industry MPS
- `14_Stanford_Stochastic_Programming_Solutions.pdf` (588KB) - Stochastic optimization
- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB) - Decision analytics bible

**Code Locations**:
- `backend/app/services/supply_plan_service.py` - Plan generation
- `backend/app/services/stochastic/distributions.py` - Distribution sampling
- `backend/app/services/aws_sc_planning/inventory_target_calculator.py` - Safety stock
- `frontend/src/pages/admin/SupplyPlanGenerator.jsx` - Planning UI

---

## 🚀 Quick Start

```bash
# Read the full knowledge base first
cat PLANNING_KNOWLEDGE_BASE.md

# Then implement your feature using the patterns shown
# Always validate against test configurations:
#   - Default TBG (4 nodes) - unit tests
#   - Three FG TBG (9 nodes) - integration tests
#   - Complex SC (20+ nodes) - performance tests
```

---

**Last Updated**: 2026-01-18

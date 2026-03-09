# Multi-Echelon Inventory Optimization (MEIO) & Safety Stock

## Comprehensive Reference Guide for Inventory Planning

---

## 1. Inventory Fundamentals

### 1.1 Types of Inventory

| Type | Purpose | Planning Approach |
|------|---------|-------------------|
| **Cycle Stock** | Regular replenishment batches | EOQ, lot sizing |
| **Safety Stock** | Buffer against demand/supply variability | Service level, cost optimization |
| **Pipeline (In-Transit)** | Material in transit between locations | Lead time × demand rate |
| **Anticipation** | Pre-build for seasonal peaks or promotions | S&OP planning |
| **Hedge** | Protection against price increases or supply disruption | Strategic decision |
| **Decoupling** | Buffers between process stages | Bottleneck management |

### 1.2 Inventory Costs

| Cost Category | Components | Typical % of Value |
|--------------|------------|-------------------|
| **Carrying/Holding** | Capital cost, storage, insurance, obsolescence, shrinkage | 15-30% per year |
| **Ordering** | Purchase order processing, inspection, freight | $50-$500 per order |
| **Shortage** | Lost sales, backorder costs, expedite, customer penalties | Highly variable |
| **Setup** | Equipment changeover, testing, first-article | Manufacturing dependent |

---

## 2. Single-Echelon Safety Stock

### 2.1 Safety Stock Formulas

**Basic Formula (Normal Distribution)**:
```
SS = z × σ_D × √LT

Where:
  z = safety factor (from service level)
  σ_D = standard deviation of demand per period
  LT = lead time in periods
```

**With Lead Time Variability**:
```
SS = z × √(LT × σ_D² + D̄² × σ_LT²)

Where:
  D̄ = average demand per period
  σ_LT = standard deviation of lead time
```

**With Demand and Lead Time Both Variable**:
```
SS = z × √(E[LT] × Var[D] + E[D]² × Var[LT])
```

### 2.2 Service Level Types

| Type | Definition | Typical Target |
|------|-----------|---------------|
| **Type 1 (α) — Cycle Service Level** | Probability of no stockout during a replenishment cycle | 90-99% |
| **Type 2 (β) — Fill Rate** | Fraction of demand filled from stock | 95-99.5% |
| **Type 3 — Ready Rate** | Fraction of time with positive inventory | 85-95% |

**z-Values for Common Service Levels**:

| Service Level | z-value (Type 1) |
|--------------|------------------|
| 50% | 0.000 |
| 80% | 0.842 |
| 85% | 1.036 |
| 90% | 1.282 |
| 95% | 1.645 |
| 97.5% | 1.960 |
| 99% | 2.326 |
| 99.5% | 2.576 |
| 99.9% | 3.090 |

### 2.3 Fill Rate (Type 2) Safety Stock

```
Fill Rate β = 1 - E[Shortage per cycle] / Q

E[Shortage] = σ_DL × L(z)

where L(z) = standard normal loss function
      σ_DL = σ_D × √LT
      Q = order quantity

Solving for z given target β:
    L(z) = Q × (1 - β) / σ_DL
    z = inverse of loss function
```

### 2.4 Inventory Policy Types

#### (s, Q) — Continuous Review, Fixed Order Quantity
```
When inventory position ≤ s: Order Q units

Reorder Point: s = D̄ × LT + SS
Order Quantity: Q = EOQ or fixed
```

#### (s, S) — Continuous Review, Order-Up-To
```
When inventory position ≤ s: Order up to S

Reorder Point: s = D̄ × LT + SS
Order-Up-To: S = s + EOQ (approximately)
```

#### (R, S) — Periodic Review, Order-Up-To
```
Every R periods: Order up to S

S = D̄ × (R + LT) + SS_periodic

SS_periodic = z × σ_D × √(R + LT)
```

#### (R, s, S) — Periodic Review, (s, S)
```
Every R periods:
  If inventory position ≤ s: Order up to S
  Otherwise: Do nothing
```

---

## 3. Multi-Echelon Inventory Optimization (MEIO)

### 3.1 Why MEIO?

Single-echelon optimization treats each location independently. This leads to:
- **Redundant safety stock**: Each echelon buffers for its own uncertainty
- **Suboptimal allocation**: Inventory positioned at wrong echelon
- **Higher total cost**: Typically 15-30% excess inventory vs. MEIO

MEIO optimizes inventory **across the entire supply network simultaneously**, recognizing that upstream safety stock protects downstream locations.

### 3.2 MEIO Problem Formulation

**Objective**: Minimize total inventory holding cost across all locations while meeting service level targets at customer-facing locations.

```
Minimize: Σᵢ hᵢ × SSᵢ

Subject to:
  Service Level at each demand node ≥ target
  SS at each node ≥ 0
  Network flow conservation constraints
  Lead time propagation constraints
```

### 3.3 Guaranteed Service Model (GSM)

Developed by Graves and Willems (2000, 2003), the GSM is the most widely used MEIO approach.

**Key Concepts**:

- **Service Time (Sᵢ)**: Time a node guarantees to fill demand from its successor
- **Net Replenishment Time (NRTᵢ)**: Time a node must cover with safety stock

```
NRTᵢ = SIᵢ + Tᵢ - SOᵢ

Where:
  SIᵢ = maximum inbound service time from predecessors
  Tᵢ = internal processing time (manufacturing or handling)
  SOᵢ = outbound service time guaranteed to successors

Safety Stock:
  SSᵢ = z × σᵢ(NRTᵢ)
  where σᵢ(NRTᵢ) = demand standard deviation over NRT horizon
```

**Decision Variables**: Choose SOᵢ (outbound service time) for each node to minimize total safety stock.

**Constraints**:
- SOᵢ ≥ 0 for all nodes
- SOᵢ ≤ SIᵢ + Tᵢ (can't promise faster than total pipeline)
- At demand nodes: SOᵢ ≤ maximum acceptable wait time

**Optimization**: Dynamic programming on spanning tree of supply network.

### 3.4 GSM Example — Serial Supply Chain

```
Supplier → Plant → DC → Customer
  T=5d     T=3d   T=1d   Target SO=0

Option A: All safety stock at DC
  NRT_DC = (5+3) + 1 - 0 = 9 days
  SS_DC = z × σ(9) = z × σ × √9 = 3z σ

Option B: Split between Plant and DC
  Plant: SO_plant = 2d → NRT_plant = 5 + 3 - 2 = 6d → SS_plant = z × σ × √6
  DC: SI_DC = 2d → NRT_DC = 2 + 1 - 0 = 3d → SS_DC = z × σ × √3
  Total SS = z × σ × (√6 + √3) = z × σ × 4.18

Option A total: 3.00 × z × σ (all at expensive DC)
Option B total: 4.18 × z × σ (higher units but split across cheaper upstream)

If h_plant = $5/unit/day and h_DC = $15/unit/day:
  Cost A: $15 × 3.00 × z × σ = $45.0 × z × σ
  Cost B: $5 × 2.45 × z × σ + $15 × 1.73 × z × σ = $38.2 × z × σ

→ Option B saves 15% despite higher total units
```

### 3.5 Stochastic Service Model (SSM)

Alternative to GSM that models service times as stochastic (probabilistic):

- Service times are random variables, not guaranteed bounds
- Captures real-world variability in upstream delivery
- More accurate for complex networks with high variability
- Computationally more demanding

```
Expected backorder at node i:
  E[BO_i] = f(demand distribution, lead time distribution, SS_i, upstream fill rates)

Optimization:
  Minimize Σ hᵢ × SSᵢ
  Subject to: E[BO_i] / E[Demand_i] ≤ (1 - target fill rate) for all customer nodes
```

### 3.6 MEIO Network Topologies

| Topology | Structure | Optimization |
|----------|-----------|-------------|
| **Serial** | Linear chain (Supplier → Plant → DC → Customer) | Dynamic programming O(n) |
| **Assembly** | Convergent (multiple components → one product) | DP on assembly tree |
| **Distribution** | Divergent (one source → multiple destinations) | DP on distribution tree |
| **Spanning Tree** | General network approximated as tree | Graves-Willems algorithm |
| **General Network** | Arbitrary with loops | Heuristics, simulation |

---

## 4. Inventory Optimization Techniques

### 4.1 ABC-XYZ Classification

**ABC (Value Classification)**:
```
A items: Top 20% of SKUs → 80% of revenue/volume
B items: Next 30% of SKUs → 15% of revenue/volume
C items: Bottom 50% of SKUs → 5% of revenue/volume
```

**XYZ (Variability Classification)**:
```
X items: CV < 0.5 (stable, predictable demand)
Y items: 0.5 ≤ CV < 1.0 (moderate variability)
Z items: CV ≥ 1.0 (erratic, unpredictable demand)
```

**Combined Policy Matrix**:

| | X (Stable) | Y (Variable) | Z (Erratic) |
|---|-----------|-------------|-------------|
| **A (High Value)** | Low SS, JIT, frequent review | Moderate SS, tight monitoring | Higher SS, demand sensing |
| **B (Medium Value)** | Standard SS, periodic review | Standard SS, exception-based | Higher SS, aggregate planning |
| **C (Low Value)** | Minimal SS, batch ordering | Aggregate, periodic review | Consider discontinue, high SS if kept |

### 4.2 Days of Supply (DOS)

```
DOS = On-Hand Inventory / Average Daily Demand

Target DOS by segment:
  Fast-moving (A-X): 7-14 days
  Medium (B-Y): 14-30 days
  Slow-moving (C-Z): 30-90 days

Working Capital Impact:
  Inventory Value = DOS × Daily COGS
  Reducing DOS by 1 day across portfolio saves: Daily COGS × 1 day
```

### 4.3 Inventory Turns

```
Inventory Turns = Annual COGS / Average Inventory Value

Benchmarks by Industry:
  Grocery/FMCG: 12-25 turns
  Electronics: 6-12 turns
  Industrial: 4-8 turns
  Aerospace: 2-4 turns
```

### 4.4 Dead Stock and Excess Analysis

```
Dead Stock: No movement for > 12 months
Excess Stock: On-Hand > (Coverage Target × Average Demand)

Excess = max(0, On-Hand - Target_DOS × Average_Daily_Demand)

Disposition Actions:
  1. Price reduction / promotion
  2. Transfer to location with demand
  3. Return to supplier
  4. Salvage / scrap
  5. Donation (tax benefit)
```

---

## 5. Stochastic Inventory Models

### 5.1 Newsvendor Model

Single-period problem (perishable, seasonal, one-time buy):

```
Optimal Order Quantity Q*:
  P(Demand ≤ Q*) = Cu / (Cu + Co)

Where:
  Cu = cost of under-ordering (lost profit per unit)
  Co = cost of over-ordering (excess cost per unit)

Critical Ratio = Cu / (Cu + Co)

For Normal Distribution:
  Q* = μ + z(CR) × σ
```

### 5.2 Base Stock Model

Continuous review, order-up-to S:

```
S* = F⁻¹(1 - h/(h+p))

Where:
  F = demand CDF over lead time + review period
  h = holding cost per unit per period
  p = shortage cost per unit per period

Or with service level target:
  S* = μ_DL + z × σ_DL
  where μ_DL, σ_DL are mean and SD of demand during LT
```

### 5.3 (Q, r) Model with Backorders

```
Minimize: TC(Q, r) = (D/Q) × K + h × [Q/2 + r - μ_L] + (p × D/Q) × n(r)

Where:
  K = fixed ordering cost
  h = holding cost
  p = backorder cost
  D = annual demand
  μ_L = mean demand during lead time
  n(r) = expected shortage per cycle

Iterative Solution:
  1. Start with EOQ for Q
  2. Compute r from service level: P(D_L > r) = Q×h / (p×D)
  3. Compute n(r) = E[max(0, D_L - r)]
  4. Update Q = √(2D(K + p×n(r))/h)
  5. Repeat until convergence
```

---

## 6. MEIO in Practice

### 6.1 Commercial MEIO Platforms

| Platform | Approach | Key Feature |
|----------|----------|-------------|
| **Llamasoft (Coupa)** | GSM + simulation | Network design integration |
| **ToolsGroup** | SSM + ML | Demand-driven, probabilistic |
| **o9 Solutions** | AI/ML-based | Knowledge graph, digital brain |
| **Kinaxis** | Concurrent MEIO | What-if analysis on safety stock |
| **SAP IBP** | Multi-echelon planning | Integrated with S/4HANA |
| **John Galt** | GSM-based | Mid-market focus |
| **Slimstock** | Statistical + ML | European market leader |

### 6.2 Implementation Challenges

1. **Data quality**: Accurate demand history, lead times, costs required
2. **Network simplification**: Real networks have cycles, need tree approximation
3. **Service time estimation**: Difficult to measure actual service times
4. **Cost allocation**: Holding costs differ significantly by echelon
5. **Change management**: Planners resist trusting algorithmic safety stock
6. **Dynamic markets**: Static MEIO needs periodic recalculation
7. **Demand non-stationarity**: Seasonal, trending demand violates stationarity assumptions

### 6.3 MEIO Benefits (Typical Results)

| Metric | Improvement |
|--------|-------------|
| **Total inventory reduction** | 15-30% |
| **Service level improvement** | +2-5 percentage points |
| **Inventory turns improvement** | +20-40% |
| **Working capital release** | 10-25% of inventory value |
| **Stockout reduction** | 30-50% fewer stockouts |

---

## 7. Inventory Optimization in AWS SC / Autonomy Platform

### 7.1 Four Policy Types

| Policy | Code | Calculation |
|--------|------|-------------|
| **Absolute Level** | `abs_level` | SS = fixed quantity (user-specified) |
| **Days of Coverage (Demand)** | `doc_dem` | SS = DOC × avg daily demand |
| **Days of Coverage (Forecast)** | `doc_fcst` | SS = DOC × avg daily forecast |
| **Service Level** | `sl` | SS = z(SL) × σ_D × √LT |

### 7.2 Hierarchical Override Logic

```
Priority (most specific wins):
  1. Product-Site level policy
  2. Product level policy
  3. Site level policy
  4. Config (global) level policy

Example:
  Config default: doc_dem, DOC=14 days
  Site "East DC": sl, SL=97%
  Product "Widget-A": abs_level, 500 units
  Product "Widget-A" at "East DC": sl, SL=99%

  → Widget-A at East DC uses SL=99% (Product-Site override)
  → Widget-A at West DC uses abs_level=500 (Product override)
  → Widget-B at East DC uses SL=97% (Site override)
  → Widget-B at West DC uses DOC=14 days (Config default)
```

---

## 8. Key Formulas Summary

| Formula | Expression | Use |
|---------|-----------|-----|
| **EOQ** | √(2DS/H) | Optimal order quantity |
| **Reorder Point** | D̄×LT + SS | When to order |
| **Safety Stock (basic)** | z × σ_D × √LT | Buffer against demand variability |
| **Safety Stock (full)** | z × √(LT×σ²_D + D̄²×σ²_LT) | Buffer against demand + LT variability |
| **Fill Rate** | 1 - E[shortage]/Q | Service measure |
| **Inventory Turns** | COGS / Avg Inventory | Efficiency measure |
| **Days of Supply** | Inventory / Daily Demand | Coverage measure |
| **Pipeline Stock** | D̄ × LT | In-transit inventory |
| **Newsvendor** | F⁻¹(Cu/(Cu+Co)) | Optimal one-time order |
| **GSM NRT** | SI + T - SO | MEIO net replenishment time |

---

*Sources: Graves & Willems (2000, 2003) "Optimizing Strategic Safety Stock Placement in Supply Networks", Snyder & Shen "Fundamentals of Inventory Management and Control", CMU MEIO Overview, MIT Strategic Safety Stock Placement, Vandeput "Inventory Optimization", ASCM CPIM Part 2*

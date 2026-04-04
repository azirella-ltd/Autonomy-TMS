# Tactical Agent Architecture — Layer 2 Planning Agents

> **Autonomy Platform — Core Architecture Reference**
>
> Defines the 5 tactical planning agents (2 demand + 3 supply-side tGNNs),
> their supply chain domain roles, technology, decision boundaries,
> training approach, and governance.

---

## Table of Contents

1. [Overview — The Tactical Planning Layer](#1-overview)
2. [Why 5 Agents (2 Demand + 3 Supply)](#2-why-5-agents)
3. [Agent 1: Forecast Baseline TRM](#3-agent-1-forecast-baseline-trm)
4. [Agent 2: Forecast Adjustment TRM](#4-agent-2-forecast-adjustment-trm)
5. [Agent 3: Supply Planning tGNN](#5-agent-3-supply-planning-tgnn)
6. [Agent 4: Inventory Optimization tGNN](#6-agent-4-inventory-optimization-tgnn)
7. [Agent 5: Capacity/RCCP tGNN](#7-agent-5-capacityrccp-tgnn)
8. [Lateral Context Exchange](#8-lateral-context-exchange)
9. [Demand-to-Supply Handshake](#9-demand-to-supply-handshake)
10. [Training & Data Requirements](#10-training--data-requirements)
11. [Governance & FVA Tracking](#11-governance--fva-tracking)
12. [Supply Chain Domain Knowledge](#12-supply-chain-domain-knowledge)
13. [TRM Count: 11 → 12](#13-trm-count-11--12)
14. [Key Files](#14-key-files)

---

## 1. Overview

The tactical planning layer (Layer 2) sits between the weekly S&OP
GraphSAGE (Layer 4) and the per-site TRM execution layer (Layer 1):

```
Layer 4 — S&OP GraphSAGE (weekly)
  │ policy parameters θ, guardrails, KPI targets
  ▼
Layer 3 — Tactical Planning (daily)                    ← THIS DOCUMENT
  │
  ├── DEMAND SIDE (2 TRMs)
  │   ├── Forecast Baseline TRM (NEW — 12th TRM)
  │   └── Forecast Adjustment TRM (EXPANDED — existing)
  │         ↓ P10/P50/P90 demand plan
  │
  ├── SUPPLY SIDE (3 tGNNs on supply network graph)
  │   ├── Supply Planning tGNN
  │   ├── Inventory Optimization tGNN
  │   └── Capacity/RCCP tGNN
  │         ↓ directives, allocations, feasibility
  │
  ▼
Layer 2 — Site tGNN (hourly, always-on)
Layer 1 — 12 TRM execution agents (<10ms)
```

### Design Principles

1. **Demand agents are TRMs, not tGNNs.** Demand forecasting is a per-product×site
   tabular regression problem. Cross-product effects enter as features, not graph
   message passing. LightGBM dominates empirically.

2. **Supply agents are tGNNs on the transportation lane graph.** Supply allocation,
   multi-echelon inventory, and capacity planning are inherently network problems
   where the answer at site A depends on state at sites B, C, D.

3. **TRM handles bulk (95%), LLM handles long tail (5%).** Deterministic heuristics
   and ML models for routine decisions. LLM escalation for cold-start NPI,
   complex cross-product reasoning, and market intelligence.

4. **Every adjustment is FVA-tracked.** Each signal source (baseline, sensing,
   promotion, NPI, consensus) is measured for Forecast Value Add. Sources that
   destroy value are automatically downweighted.

---

## 2. Why 5 Agents (2 Demand + 3 Supply)

### Why Not 4 (Current)?

The current Demand Planning tGNN operates on the **supply network graph** (sites +
transportation lanes). But demand dependencies are between **products** (basket,
cannibalization, substitution), not between sites. The Demand tGNN was learning
mostly noise from the wrong graph structure.

### Why Not 2?

Cramming inventory + RCCP + D/S balancing into one model creates multi-task loss
conflicts: buffer sizing (Tanh) vs utilization (Sigmoid) vs flow allocation (ReLU)
fight over shared parameters with different training labels.

### Why Not 5 tGNNs?

Demand-side functions don't benefit from graph message passing. Per-product
forecast is a tabular problem (LightGBM). Cross-product effects are better
captured as features than as a separate neural network on a dynamic product
affinity graph.

### Why 2 Demand TRMs (Not 1)?

The baseline forecast and forecast adjustments are **separate planning activities**
with different cadences, data sources, governance, and error profiles:

| Aspect | Baseline | Adjustment |
|--------|----------|-----------|
| **Cadence** | Weekly retrain, daily score | Continuous (CDC-triggered) |
| **Data** | Historical demand, calendar, external signals | Live POS, promotions, NPI, market intel |
| **Governance** | Locked 4-8 weeks ahead | Updated daily, FVA-gated |
| **Error type** | Systematic bias (model mis-specification) | Noise from signal quality |
| **Owner (human)** | Demand Analyst | Demand Planner / S&OP Lead |
| **FVA baseline** | Naive (repeat last year) | Statistical baseline |

Combining them into one agent conflates "what does the model think?" with "what
do we know that the model doesn't?" — exactly the separation that Forecast Value
Add is designed to measure.

---

## 3. Agent 1: Forecast Baseline TRM

### Supply Chain Domain Role

The **Demand Analyst** in a traditional S&OP process:

> Generates the unconstrained statistical demand forecast. Selects and tunes
> forecasting models. Monitors forecast accuracy. Manages the feature pipeline
> (what signals feed the model). Produces the "system forecast" that serves as
> the starting point for all downstream planning.

In supply chain practice, baseline forecasting encompasses:

- **Time-series decomposition**: Trend, seasonality, cyclicality, noise
- **Model selection**: Which algorithm fits each product×site best (intermittent
  demand vs smooth vs lumpy vs new product)
- **Feature engineering**: What external and cross-product signals improve accuracy
- **Accuracy monitoring**: MAPE, bias, tracking signal per product family
- **Hierarchy reconciliation**: Ensure product-level forecasts sum to family/category totals
- **Censored demand handling**: Detect and correct for stockout-suppressed demand

### Technology: Powell TRM + LightGBM/TFT Ensemble + Conformal

**This is a NEW TRM (12th type: `forecast_baseline`)** — not a tGNN, not a
standalone pipeline. It operates within the Powell framework with urgency,
confidence, signal context, and AIIO governance.

**What the TRM decides (deterministic, <10ms):**

| Decision | How | Output |
|----------|-----|--------|
| Model selection per product×site | MAPE comparison across models, product cluster characteristics | "Use LightGBM" or "Use Holt-Winters" or "Use naive" |
| Retrain trigger | Drift detection: CUSUM on forecast error residuals | "Retrain now" or "Keep current model" |
| Feature inclusion | Feature importance ranking + FVA per feature | Enable/disable external signals, cross-product features |
| Cluster assignment | Product demand profile characteristics (CV, ADI, intermittency) | Assign to cluster for cluster-specific model |
| Censored demand correction | Stockout detection (inventory=0 + demand>0) | Replace observed demand with estimated true demand |
| Hierarchy reconciliation | Middle-out: family-level forecast disaggregated by BOM ratios | Consistent top-down / bottom-up |
| Confidence assessment | Conformal prediction interval width | P10/P50/P90 bounds + confidence score |

**What the TRM orchestrates (ML pipeline, seconds-minutes at provisioning):**

| Step | Technology | Purpose |
|------|-----------|---------|
| Feature engineering | Pandas/NumPy | 23+ features: lags, rolling stats, calendar, external signals, cross-product |
| Model training | LightGBM quantile regression (P10/P50/P90) | Per-cluster models, 500 estimators |
| Long-horizon model | TFT (Temporal Fusion Transformer) | Family-level 3-12 month forecasts (optional) |
| Thin-history fallback | Holt-Winters / Croston | Intermittent or <26 observations |
| Conformal calibration | Conformal prediction on validation residuals | Distribution-free coverage guarantee |
| Reconciliation | Middle-out proportional | Hierarchy consistency |

**LLM escalation: NONE.** The baseline forecast is purely statistical. There is no
long-tail reasoning needed — model selection is algorithmic, not judgmental.

### Cross-Product Features (NEW — Not Currently Implemented)

The key gap in the current LightGBM pipeline: demand for product A is modeled
independently of product B. In reality:

| Effect | Feature Engineering Approach |
|--------|------------------------------|
| **Basket (complementary)** | Category-level demand as a feature. If category demand is up but this SKU is flat → losing share. |
| **Substitution** | Demand for substitutes (same category, similar price) as lagged features. Rising substitute = falling demand. |
| **Cannibalization** | Family-level demand as a feature. If family is stable but this SKU declining → demand migrating to sibling. |
| **Category trend** | Product hierarchy aggregate demand trend as a feature. Captures macro shifts. |
| **Product embeddings** | Learned embedding vector from co-purchase history (analogous to word2vec on basket transactions). Similar products get similar embeddings → transfer learning for thin-history SKUs. |

These enter as **additional LightGBM features**, not as a separate model. The TRM
decides which cross-product features to include based on FVA measurement.

### External Signal Features (NEW — Ingested But Not Modeled)

Currently in `external_signal.py` but not wired into the forecast:

| Signal | Feature | Expected FVA |
|--------|---------|-------------|
| Weather (temperature, precipitation) | 7-day rolling anomaly vs seasonal norm | +2-5% for weather-sensitive products (beverages, seasonal) |
| POS data (if available) | Daily POS vs weekly forecast ratio | +3-8% for short-horizon |
| Economic indicators (FRED) | GDP growth, consumer confidence | +1-2% for durable goods |
| Commodity prices | Raw material cost index | +1-3% for input-cost-sensitive demand |

### Output

```python
ForecastBaselineOutput:
    product_id: str
    site_id: str
    periods: List[ForecastPeriod]  # Each with:
        period_start: date
        period_end: date
        quantity_p10: float      # Downside (conformal)
        quantity_p50: float      # Point estimate
        quantity_p90: float      # Upside (conformal)
        model_used: str          # "lgbm", "tft", "holt_winters", "croston", "naive"
        confidence: float        # 0-1, from conformal interval width
    cross_product_features_used: List[str]
    external_signals_used: List[str]
    censored_demand_corrected: bool
    cluster_id: str
    retrain_recommended: bool
    hierarchy_reconciled: bool
```

### Cadence

| Trigger | What Runs |
|---------|----------|
| **Provisioning** (one-time) | Full pipeline: feature engineering → train → calibrate → reconcile |
| **Daily cascade** (5am) | Score existing models → produce fresh P10/P50/P90 → reconcile |
| **CDC trigger** (event-driven) | Drift detection: if CUSUM flags, queue retrain for next provisioning |
| **Weekly S&OP** (Monday 6am) | Compare forecast vs actuals → update accuracy metrics → report FVA |

---

## 4. Agent 2: Forecast Adjustment TRM

### Supply Chain Domain Role

The **Demand Planner** in a traditional S&OP process:

> Reviews the statistical baseline and applies business intelligence that the
> model cannot capture: upcoming promotions, new product launches, competitor
> actions, customer-specific knowledge, market shifts. Owns the "consensus
> forecast" — the final demand plan that the business operates on.

In supply chain practice, demand adjustment encompasses:

- **Promotion planning**: Estimating demand uplift from price changes, displays,
  bundles, and seasonal campaigns — including cannibalization of non-promoted items
- **NPI (New Product Introduction)**: Forecasting demand for products with no
  history by transferring patterns from similar products, applying launch curves,
  and estimating cannibalization of existing products
- **EOL (End of Life)**: Coordinating demand phase-out of retiring products with
  ramp-up of successor products, managing last-buy quantities
- **Demand sensing**: Short-horizon corrections (0-14 days) from leading indicators
  that move faster than the weekly statistical forecast
- **Demand shaping**: Intentionally influencing demand through pricing, allocation,
  and promotion to align with supply capabilities
- **Consensus forecasting**: Integrating input from Sales, Marketing, Finance, and
  Operations into a single demand plan, gated by Forecast Value Add
- **Exception management**: Identifying and resolving forecast outliers, anomalies,
  and business events that distort the baseline

### Technology: Powell TRM (95%) + LLM Escalation (5%)

**This is the EXISTING `forecast_adjustment` TRM (expanded).** Already one of the
11 TRMs. Gets significantly more capability.

### TRM Decisions (Deterministic, <10ms)

| Decision | Heuristic / ML | Data Source |
|----------|---------------|-------------|
| **Promotion uplift** | Price elasticity learned from historical promo events via regression. Applied as multiplicative adjustment to baseline. | `promotion` table: uplift_pct, actual vs expected |
| **Promotion cannibalization** | Category-level demand redistribution during historical promos. Fraction of uplift "stolen" from sibling products. | Category demand during/after promo periods |
| **EOL phase-out** | Lifecycle curve from `product_lifecycle` model: 90%→75%→50%→25%→10%→0% over defined periods. | `product_lifecycle.phase_out_schedule` |
| **NPI ramp-up (warm)** | Similar-product transfer: find k-nearest products by attributes (category, price, material), scale their demand curve by expected market share. | Product attributes + `product_lifecycle.demand_ramp_curve` |
| **Demand sensing** | Exception detection: if |actual - forecast| > threshold (learned per product cluster), apply proportional correction. | CDC events from POS/order data, last 7-14 days |
| **Short-horizon correction** | Weighted average of baseline and recent actuals: `adj = α × recent_actual + (1-α) × baseline` where α decays with horizon. | Last 2-4 weeks of actuals |
| **FVA gate** | Track accuracy contribution per signal source. If signal's FVA < 0 over trailing 8 weeks, suppress it. | `forecast_value_add_log` |
| **Consensus gate** | Accept/reject human override based on historical FVA of overrides in this category. If human overrides have destroyed value, flag for review. | Override history per (user, category) |

### LLM Escalation (5% — Long Tail)

The TRM escalates to Claude Skills when:
- Conformal interval is wide (confidence < `skill_escalation_threshold`)
- Product is in NPI stage with no similar products found (cold-start)
- Novel market event with no historical precedent
- Complex cross-product reasoning required

| Scenario | LLM Prompt Pattern | Expected Output |
|----------|-------------------|----------------|
| **NPI cold-start** | "Product X (category: organic pasta, price: $4.99, target: health-conscious millennials) launches in 6 weeks. No similar products in catalog. Industry benchmarks for organic pasta NPIs show [data]. Recommend demand curve." | `{ramp_curve: [10, 25, 50, 75, 100], weekly_base_qty: 200, confidence: 0.5, reasoning: "..."}` |
| **Competitor disruption** | "Competitor recalled product Y (30% market share in category Z). Our substitute product W currently at [volume]. Estimate demand shift." | `{adjustment_pct: +25, duration_weeks: 8, confidence: 0.6, reasoning: "..."}` |
| **Market intelligence** | "Sales team reports customer A is switching to competitor. Customer A represents 15% of product B volume. Validate against order history." | `{adjustment_pct: -12, confidence: 0.7, reasoning: "Order frequency down 30% over 4 weeks confirms trend"}` |
| **Consensus challenge** | "Sales requests +40% override for Q3. Historical FVA for sales overrides in this category: -3% (they reduce accuracy). Override size is 2× the largest historically successful override." | `{recommendation: "reject", reasoning: "...", suggested_compromise: +15}` |

### Output

```python
ForecastAdjustmentOutput:
    product_id: str
    site_id: str
    adjustment_type: str          # "promotion", "npi", "eol", "sensing", "consensus", "llm"
    baseline_p50: float           # From Forecast Baseline TRM
    adjusted_p50: float           # After this adjustment
    adjustment_pct: float         # (adjusted - baseline) / baseline
    confidence: float             # TRM confidence in adjustment
    fva_expected: float           # Expected accuracy improvement
    reasoning: str                # Structured explanation
    escalated_to_llm: bool        # Whether LLM was consulted
    llm_reasoning: Optional[str]  # LLM explanation if escalated
    signal_sources: List[str]     # Which signals contributed
    cannibalization_impact: Optional[Dict]  # {product_id: pct_impact}
```

### Cadence

| Trigger | What Runs |
|---------|----------|
| **Daily cascade** (5am, after baseline) | Apply standing adjustments (promos, lifecycle), sensing corrections |
| **CDC trigger** (event-driven) | New order data → sensing exception check → immediate adjustment |
| **Promotion activation** | Promo goes live → apply uplift + cannibalization |
| **NPI launch** | Product enters "launch" stage → activate ramp curve (or escalate to LLM) |
| **Weekly S&OP** (Monday 6am) | Consensus round: review overrides, gate by FVA |

---

## 5. Agent 3: Supply Planning tGNN

### Supply Chain Domain Role

The **Supply Planner / Sourcing Planner** in a traditional S&OP process:

> Matches demand to supply sources. Decides which vendor supplies which site,
> through which transportation lane, at what quantity. Manages lead time risk.
> Detects supply exceptions (late POs, short shipments, vendor capacity limits).
> Executes the allocation decision: given constrained supply, who gets what.

In supply chain practice, supply planning encompasses:

- **Source assignment**: Which vendor/plant for each product×site (primary, backup, split)
- **Lead time management**: Track actual vs planned lead times, detect overruns
- **Exception detection**: Late POs, partial receipts, quality rejects, vendor decommits
- **Allocation priority**: When supply is short, who gets served first (AATP priority tiers)
- **Pipeline coverage**: Days of supply in transit + on order
- **Order recommendations**: Suggested PO quantities considering MOQ, lot sizing, economies of scale
- **Vendor performance**: Track OTIF, quality, lead time variability per vendor

### Technology: GATv2 + GRU tGNN on Supply Network Graph

**Why a GNN?** Supply allocation IS the graph problem. The answer at site A
(how much to allocate) depends on supply capacity at sites B, C (manufacturers),
demand at sites D, E (other DCs/retailers), and transportation lane constraints
between them. Message passing along edges is exactly what's needed.

### Architecture

```
Input:  [batch, window_size=10, num_sites, 10] transactional features
      + [num_sites, 64] S&OP embeddings (from Layer 4 GraphSAGE)
      + [num_sites, N] demand plan (from Forecast TRMs — P10/P50/P90)
      + [num_sites, 6] lateral context (from inventory + capacity tGNNs, iteration 2)

Graph:  Sites as nodes, transportation lanes as edges
        Edge features: capacity, lead_time, cost, utilization

Spatial: 2-layer GATv2Conv (64-dim hidden, 2 attention heads)
Temporal: GRU (64-dim hidden, 1 layer)

Output Heads (5):
  exception_prob:       Sigmoid [0,1]  — probability of supply failure
  order_recommendation: ReLU   [0,∞)  — suggested order quantity
  allocation_priority:  Sigmoid [0,1]  — dynamic ATP allocation signal
  lead_time_risk:       Sigmoid [0,1]  — lead time overrun probability
  confidence:           Sigmoid [0,1]  — model confidence

~30K parameters, <8ms inference
```

### Training Labels

From **NetworkFlowOracle** (LP solver):
```
min Σ transport_cost × flows + Σ stockout_penalty × slack
s.t. flow ≤ lane_capacity, outflow ≤ supply_capacity, inflow ≥ demand - slack
```

LP-optimal flows become supervised training targets.

Also from DB:
- `inbound_order` / `inbound_order_line`: historical PO performance
- `supply_plan`: existing plan of record
- `sourcing_rules`: vendor assignments and split ratios

---

## 6. Agent 4: Inventory Optimization tGNN

### Supply Chain Domain Role

The **Inventory Analyst / S&OP Analyst** in a traditional S&OP process:

> Sets safety stock targets across the network. Balances holding cost against
> service level. Identifies rebalancing opportunities (excess at one site,
> shortage at another). Monitors days of supply. Executes demand/supply balancing
> — the core S&OP output: what to make, where, when, how much.

In supply chain practice, inventory optimization encompasses:

- **Multi-echelon safety stock**: Safety stock at a DC depends on replenishment lead
  time from its upstream manufacturer, which depends on the manufacturer's own
  inventory and production capacity. This is inherently a network optimization.
- **Rebalancing**: Detecting when one site has excess while another is short,
  and recommending lateral transfers considering transport cost and time.
- **Demand/supply balancing**: The core S&OP deliverable — given the demand plan
  (from Forecast TRMs) and supply capabilities (from Supply tGNN), produce a
  feasible production/procurement/distribution plan.
- **Days of supply monitoring**: Track on-hand + in-transit + on-order relative to
  forward demand. Flag when DOS falls below or exceeds target bands.
- **Inventory health scoring**: Composite metric combining stock availability,
  aging (SLOB — slow/obsolete), and balance across echelons.
- **Service level targeting**: Translate P10/P50/P90 demand uncertainty into
  inventory buffer requirements per conformal prediction intervals.

### Technology: GATv2 + GRU tGNN on Supply Network Graph

**Why a GNN?** Multi-echelon inventory optimization is fundamentally a network
problem. Safety stock at a downstream DC depends on replenishment variability
from the upstream site, which depends on that site's own inventory position.
Rebalancing candidates require knowing which other sites have excess — a graph
query.

### Architecture

Same GATv2+GRU structure as Supply Planning tGNN.

```
Output Heads (5):
  buffer_adjustment:    Tanh   [-1,+1] — DIRECTIONAL: reduce (-) or increase (+) safety stock
  rebalancing_urgency:  Sigmoid [0,1]  — urgency to trigger cross-site transfer
  stockout_prob:        Sigmoid [0,1]  — probability of stockout within horizon
  inventory_health:     Sigmoid [0,1]  — composite health score
  confidence:           Sigmoid [0,1]  — model confidence

~30K parameters, <8ms inference
```

The **Tanh** activation on buffer_adjustment is unique to this tGNN — it outputs a
directional signal, not a probability or quantity:
- Negative = holding cost pressure exceeds stockout risk → reduce buffer
- Positive = demand uncertainty or supply risk is high → increase buffer

### Training Labels

From DB:
- `inventory_level`: current on-hand, in-transit, allocated
- `inventory_policy`: target SS, reorder point, max stock
- Historical stockout events (inventory=0 when demand>0)

From LP oracle:
- Optimal inventory positions from network flow solution
- Demand satisfaction rates at optimum

### Demand/Supply Balancing (D/S Balance)

This tGNN owns the D/S balancing output — the core S&OP deliverable:

Given:
- Demand plan P10/P50/P90 (from Forecast TRMs)
- Supply capabilities (from Supply Planning tGNN)
- Capacity feasibility (from Capacity/RCCP tGNN)
- Inventory positions (self)

Produce:
- Net requirements per site×product×period
- Recommended production/procurement quantities
- Distribution allocation across the network

This is expressed through the `rebalancing_urgency` and `buffer_adjustment`
signals, which the Layer 1 TRMs (PO Creation, MO Release, Transfer Order,
Rebalancing) translate into executable decisions.

---

## 7. Agent 5: Capacity/RCCP tGNN

### Supply Chain Domain Role

The **Production Planner / Capacity Planner** in a traditional S&OP process:

> Validates whether the Master Production Schedule (MPS) is feasible given
> available resources. Identifies bottleneck resources. Recommends overtime,
> outsourcing, or load leveling. Ensures the supply plan is executable before
> it's committed.

In supply chain practice, RCCP encompasses:

- **Rough-Cut Capacity Planning**: Compare planned production load against
  available capacity per resource per period. Flag overloads before they hit
  the shop floor.
- **Bottleneck detection**: Identify which resource at which site will constrain
  the entire network. A bottleneck manufacturer limits what all downstream
  sites can receive.
- **Load leveling**: Smooth production load across periods to avoid peaks
  (overtime, quality risk) and valleys (idle resources, cost waste).
- **Overtime/outsourcing recommendation**: When load exceeds capacity, recommend
  whether to extend hours (overtime cost), shift to alternate resource, or
  outsource (subcontracting).
- **Capacity buffer**: Reserve capacity for unexpected demand or quality issues.
  Too much buffer = wasted capacity. Too little = stockouts from disruptions.

### Technology: GATv2 + GRU tGNN on Supply Network Graph

**Why a GNN?** Bottleneck propagation: if a manufacturer is overloaded, all
downstream sites are affected. Capacity reallocation across sites (shift
production to an alternate plant) is a network decision. Load leveling across
periods requires understanding downstream demand timing.

### Architecture

Same GATv2+GRU structure.

```
Input Features (10-dim, capacity-specific):
  [0] resource_utilization_pct     — current load / capacity
  [1] available_capacity_hours     — slack
  [2] planned_load_hours           — MPS load
  [3] overtime_cost_ratio          — premium cost factor
  [4] setup_time_ratio             — changeover overhead
  [5] efficiency_factor            — OEE
  [6] utilization_trend            — slope over past N periods
  [7] seasonal_capacity_idx        — seasonal adjustment
  [8] changeover_frequency         — transitions per period
  [9] maintenance_downtime_pct     — scheduled + unscheduled

Output Heads (5):
  planned_utilization:  Sigmoid [0,1]  — target utilization level
  capacity_buffer_pct:  Sigmoid [0,1]  — recommended reserve capacity
  feasibility_score:    Sigmoid [0,1]  — MPS plan feasibility (can we execute?)
  bottleneck_risk:      Sigmoid [0,1]  — probability this site becomes bottleneck
  confidence:           Sigmoid [0,1]  — model confidence

~30K parameters, <8ms inference
```

### RCCP Validation

The `validate_rccp()` method performs explicit feasibility checking:
1. Load MPS (`supply_plan` rows with `plan_version='live'`)
2. Group by `plan_date`, sum `planned_order_quantity`
3. Estimate hours per unit (from routing/capacity_resource tables)
4. Compare against `available_capacity_hours`
5. Return per-period feasibility + overloaded resource list + suggested adjustments

### Training Labels

From DB:
- `manufacturing_order` / `production_order`: actual load vs capacity
- `resource_capacity`: shift_count, hours_per_shift, downtime
- `resource_capacity_constraint`: day-of-week/time windows

---

## 8. Lateral Context Exchange

### Between Supply-Side tGNNs (Triangle)

The 3 supply-side tGNNs exchange lateral context via 2-iteration refinement.
Iteration 1 runs all 3 in parallel with no cross-domain context. If any signal
changes by > 0.05, iteration 2 runs all 3 again with lateral context:

```
Supply ──────────────── Inventory
  │  exception_prob       │  stockout_prob
  │  order_recs           │  buffer_adjustment
  │  pipeline_coverage    │  rebalancing_urgency
  │                       │
  └──── Capacity ─────────┘
         utilization
         bottleneck_risk
         feasibility
```

Each tGNN receives a `[num_sites, 6]` lateral context tensor from its 2 peers,
added as a residual to S&OP embeddings.

### From Demand TRMs to Supply tGNNs (One-Way)

The Forecast Baseline + Adjustment TRMs produce the demand plan **before** the
supply-side tGNNs run. Their output is injected as **node features**, not
lateral context:

```
Forecast Baseline TRM → P10/P50/P90 per product×site
                              ↓
Forecast Adjustment TRM → adjusted P10/P50/P90 + NPI/promo flags
                              ↓
                   [num_sites, N] demand features
                              ↓
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Supply tGNN    Inventory tGNN   Capacity tGNN
```

Demand features injected per site:
- `demand_p50`: Adjusted point forecast (aggregated across products at site)
- `demand_p10`, `demand_p90`: Uncertainty bounds
- `demand_volatility`: (P90 - P10) / P50
- `demand_trend`: Period-over-period change in P50
- `npi_active_count`: Number of NPI products at this site
- `promo_active_count`: Number of active promotions at this site
- `bullwhip_coefficient`: Analytical computation — upstream forecast variance /
  downstream forecast variance along each DAG path

**No lateral context flows back from supply to demand.** The demand plan is
unconstrainted — supply constraints are handled by the supply-side tGNNs and
Layer 1 TRMs (constrained planning is a supply-side responsibility).

---

## 9. Demand-to-Supply Handshake

The handshake between demand and supply is the **core S&OP interface**:

```
DEMAND SIDE produces:                SUPPLY SIDE consumes:
─────────────────────                ────────────────────
Unconstrained demand plan     ──→    Supply tGNN: allocation against sources
  P10/P50/P90 per product×site       Inventory tGNN: buffer sizing, D/S balance
  Adjustment flags (NPI, promo)       Capacity tGNN: MPS feasibility check
  Confidence per forecast
  FVA attribution

SUPPLY SIDE produces:                LAYER 1 TRMs consume:
─────────────────────                ────────────────────
Constrained supply plan       ──→    PO TRM: purchase order quantities
  Allocation per site×product         MO TRM: manufacturing order release
  Exception alerts                    TO TRM: transfer order quantities
  Rebalancing recommendations         ATP TRM: order promise confirmation
  RCCP feasibility flags              Rebalancing TRM: lateral stock moves
```

---

## 10. Training & Data Requirements

### Demand TRMs

| TRM | Training Data | Min Data | Retraining |
|-----|-------------|----------|-----------|
| **Forecast Baseline** | Historical demand (26+ weeks per product×site), calendar, external signals | 26 observations per series | Weekly (or on drift) |
| **Forecast Adjustment** | Historical promos + uplift, NPI outcomes, sensing events, override history | 10+ promo events per category for elasticity | Continuous (FVA-driven) |

### Supply tGNNs

| tGNN | Training Data | Min Data | Retraining |
|------|-------------|----------|-----------|
| **Supply Planning** | Inbound orders, supply plan, sourcing rules, LP oracle labels | 5+ sites, 10+ lanes | Provisioning + daily CDC |
| **Inventory Optimization** | Inventory levels, policies, stockout events, LP oracle labels | 5+ sites with inventory history | Provisioning + daily CDC |
| **Capacity/RCCP** | Manufacturing orders, resource capacity, downtime events | 3+ manufacturing sites | Provisioning + daily CDC |

---

## 11. Governance & FVA Tracking

### Forecast Value Add (FVA)

Every adjustment to the baseline is tracked for accuracy contribution:

```
FVA(signal) = MAPE(baseline + signal) - MAPE(baseline only)

If FVA < 0: signal is destroying value → suppress
If FVA > 0: signal is adding value → weight higher
If FVA ≈ 0: signal is noise → optional
```

FVA is tracked per:
- Signal source (promotion, NPI, sensing, consensus, LLM)
- Product category
- Time horizon (1-week, 4-week, 13-week)
- User (for consensus overrides)

### AIIO Governance

| Agent | Typical AIIO Distribution |
|-------|--------------------------|
| Forecast Baseline TRM | 90% AUTOMATE (model selection is routine), 10% INFORM (retrain triggers) |
| Forecast Adjustment TRM | 60% AUTOMATE (promos, sensing), 25% INFORM (NPI), 10% INSPECT (LLM escalations), 5% OVERRIDE |
| Supply Planning tGNN | Via Layer 1 TRMs — directive-based |
| Inventory Optimization tGNN | Via Layer 1 TRMs — directive-based |
| Capacity/RCCP tGNN | Via Layer 1 TRMs — directive-based |

The supply-side tGNNs don't have their own AIIO mode — their outputs are
**directives** consumed by Layer 1 TRMs, which have full AIIO governance.

---

## 12. Supply Chain Domain Knowledge

### Baseline Forecasting — What Real Demand Analysts Know

**Demand classification** (affects model choice):
- **Smooth**: Low CV (<0.5), regular intervals. Best: exponential smoothing, LightGBM.
- **Erratic**: High CV (>0.5), regular intervals. Best: LightGBM with volatility features.
- **Intermittent**: Low CV, irregular intervals (ADI>1.32). Best: Croston, SBA.
- **Lumpy**: High CV, irregular intervals. Best: Croston, or aggregate to family level.

**Seasonality patterns**:
- Annual (Christmas, back-to-school, summer)
- Monthly (payday effects, end-of-month stocking)
- Weekly (day-of-week patterns for retail)
- Event-driven (sports events, weather, holidays)

**Demand shaping interactions**:
- Price elasticity varies by product category (staples ≈ inelastic, discretionary ≈ elastic)
- Promotion fatigue: repeated discounts erode price sensitivity
- Forward buying: promotions shift demand in time, not create new demand
- Halo effects: premium product marketing lifts entire category

### NPI Forecasting — The Cold-Start Problem

New products have no demand history. Approaches (in order of preference):
1. **Analogous product**: Find most similar existing product by attributes. Scale its
   curve by expected market share.
2. **Category insertion**: Estimate share of category total. Apply category demand
   profile.
3. **S-curve lifecycle model**: Generic growth curve parameterized by target steady-state
   volume and time-to-peak.
4. **Expert judgment**: Sales/marketing estimate, FVA-tracked against actuals post-launch.

The Forecast Adjustment TRM uses approach 1 (attribute matching) as the default,
escalating to LLM for approach 4 when no analogous product is found.

### Cross-Product Dependencies — What Retail Planners Know

**Basket effects**: Products bought together regularly. If bread demand rises but
butter demand doesn't, the butter forecast may be wrong (or butter is out of stock
suppressing observed demand). The Forecast Baseline TRM captures this via
category-level demand as a feature.

**Assortment effects**: Total category volume may be stable while demand migrates
between SKUs within the family. The family-level forecast stays accurate but
SKU-level accuracy degrades without cannibalization modeling. The Forecast
Adjustment TRM tracks this via sibling product demand features.

**NPI cannibalization**: New product launch often takes volume from existing
products in the same category. The Forecast Adjustment TRM estimates this based
on historical NPI events in the category and the price/positioning gap between
new and existing products.

### Multi-Echelon Inventory — What Inventory Analysts Know

**Echelon stock**: Don't set safety stock independently per site. A DC's safety
stock should account for the manufacturer's reliability (lead time variability)
and the retailer's demand variability. The Inventory Optimization tGNN captures
this through graph message passing — each site's buffer_adjustment signal
incorporates information from upstream and downstream sites.

**Rebalancing cost**: Moving stock laterally (DC→DC) has transportation cost and
lead time. Only rebalance when the expected stockout cost at the receiving site
exceeds the transport cost + opportunity cost at the sending site.

### RCCP — What Production Planners Know

**Resource types**: Machines, labor, tooling, floor space. Each has different
flexibility (labor can work overtime, machines can't exceed rated capacity).

**Load leveling**: Production planners prefer smooth load profiles. Peaks cause
quality issues (rushed work), overtime costs, and equipment stress. Valleys
cause idle cost and worker dissatisfaction.

**Make-or-buy**: When internal capacity is full, the decision is overtime
(+25-50% cost), outsource (+variable quality), or delay (missed delivery).
The Capacity/RCCP tGNN's feasibility_score drives this trade-off.

---

## 13. TRM Count: 11 → 12

Adding the Forecast Baseline TRM brings the total from 11 to 12:

| # | TRM Type | Layer | Existing/New |
|---|----------|-------|-------------|
| 1 | ATP Allocation | 1 | Existing |
| 2 | PO Creation | 1 | Existing |
| 3 | MO Release | 1 | Existing |
| 4 | Transfer Order | 1 | Existing |
| 5 | Inventory Rebalancing | 1 | Existing |
| 6 | Quality Disposition | 1 | Existing |
| 7 | Maintenance Scheduling | 1 | Existing |
| 8 | Subcontracting | 1 | Existing |
| 9 | Order Tracking | 1 | Existing |
| 10 | Inventory Buffer | 1 | Existing |
| 11 | Forecast Adjustment | 2 | Existing (expanded) |
| **12** | **Forecast Baseline** | **2** | **NEW** |

### Site Capability Updates

| Site Type | Current TRMs | New TRMs |
|-----------|-------------|----------|
| Manufacturer | 11 | 12 (+ Forecast Baseline) |
| Distribution Center | 7 | 8 (+ Forecast Baseline) |
| Retailer | 6 | 7 (+ Forecast Baseline) |

The Forecast Baseline TRM runs at every site type because every site has demand
to forecast (even manufacturers forecast component demand from downstream orders).

---

## 14. Key Files

### Demand Side (TRMs)

| File | Purpose |
|------|---------|
| `services/powell/trm_forecast_baseline.py` | NEW: Forecast Baseline TRM |
| `services/powell/trm_forecast_adjustment.py` | EXPANDED: Forecast Adjustment TRM |
| `services/demand_forecasting/lgbm_forecaster.py` | LightGBM quantile regression |
| `services/demand_forecasting/feature_engineer.py` | Feature pipeline (needs cross-product features) |
| `services/demand_forecasting/lgbm_pipeline.py` | Pipeline orchestration |
| `services/forecast_pipeline_orchestrator.py` | 10-stage pipeline |
| `services/product_lifecycle_service.py` | NPI/EOL lifecycle management |
| `services/promotional_planning_service.py` | Promotion management |
| `models/external_signal.py` | External signal ingestion |
| `services/skills/SKILL_forecast_adjustment.md` | LLM skill instructions |

### Supply Side (tGNNs)

| File | Purpose |
|------|---------|
| `models/gnn/supply_planning_tgnn.py` | Supply Planning tGNN model |
| `models/gnn/inventory_optimization_tgnn.py` | Inventory Optimization tGNN model |
| `models/gnn/capacity_rccp_tgnn.py` | Capacity/RCCP tGNN model |
| `services/powell/supply_planning_tgnn_service.py` | Supply inference service |
| `services/powell/inventory_optimization_tgnn_service.py` | Inventory inference service |
| `services/powell/capacity_rccp_tgnn_service.py` | Capacity inference service |
| `services/powell/tactical_hive_coordinator.py` | 2-iteration lateral coordination |
| `services/powell/tactical_tgnn_training_service.py` | Training orchestration |
| `services/powell/network_tgnn_oracle.py` | LP oracle for training labels |

### Shared

| File | Purpose |
|------|---------|
| `services/powell/contextual_bsc.py` | Balanced Scorecard scoring |
| `models/metrics_hierarchy.py` | SCOR metric catalog (L1-L4) |
| `services/powell/trm_trainer.py` | TRM reward functions + economic config |
| `services/decision_governance_service.py` | AIIO governance + write-back delay |

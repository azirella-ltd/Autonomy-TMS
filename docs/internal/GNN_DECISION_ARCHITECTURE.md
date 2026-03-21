# GNN Decision Architecture — Site tGNN, Network tGNN, and S&OP GraphSAGE

> **Audience**: Engineers and data scientists working on the GNN layers.
> This document specifies how each GNN layer makes decisions, how urgency and
> likelihood are computed, and how the layers interact.
> For TRM heuristic algorithms see [TRM_DECISION_ALGORITHMS.md](TRM_DECISION_ALGORITHMS.md).
> For training pipeline see [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md).

---

## Layer Architecture Overview

### Current State (Implemented)

```
Layer 4: S&OP GraphSAGE (Strategic)
  Scope:   Entire supply network
  Timing:  Weekly (Sunday 04:00) + on-demand
  Output:  θ* policy parameters per site (safety_stock_multiplier,
           service_level_target, reorder_point_days, order_up_to_days,
           sourcing_split)
  Adjustment: None autonomous — upstream constraint injection + human directive

Layer 2: Supply Planning GNN [formerly "Network tGNN"]
  Scope:   Multi-site daily supply/allocation planning
  Timing:  Daily
  Output:  tGNNSiteDirective per site (allocation priority, demand forecast
           correction, exception probability, flow adjustments)
  Adjustment: None — escalation triggers DE re-run upstream

Layer 1.5: Site tGNN (Operational)                             ✅ IMPLEMENTED
  Scope:   Single site — cross-TRM coordination
  Timing:  Hourly (at :25)
  Output:  Urgency adjustments [11, 3] per TRM
  Adjustment: IS the adjustment layer — adjusts execution TRMs

Layer 1: 11 Execution TRMs                                     ✅ IMPLEMENTED
  Scope:   Per-decision execution
  Timing:  Per cycle (<10ms)
  Claude Skills: 11 skills (exception handling, ~5% of decisions)
```

### End State (Target Architecture)

```
Layer 4: S&OP GraphSAGE (Strategic)                            ✅ IMPLEMENTED
  + S&OP Adjustment Skill (Claude Sonnet)                      ⬜ PLANNED
    Trigger: new signal between weekly DE runs
    Action:  bounded θ* patch with pending_de_reconciliation flag

Layer 2: Tactical Planning — four domain GNNs (daily, sequential)

  Step 1 — Demand Planning GNN                                  ⬜ PLANNED
    Input:  historical demand, active forecasts, product lifecycle,
            promotional calendar, email signals
    Output: consensus demand plan (time-phased P10/P50/P90 per product-site)
    Oracle: statistical ensemble (ETS + ARIMA + SARIMA) + ForecastAdjustmentTRM
            decisions as BC labels
    + Demand Adjustment TRM (in-cycle)                          ⬜ PLANNED
    + Demand Planning Skill (cross-cycle)                       ⬜ PLANNED

  Step 2 — Inventory Planning GNN                               ⬜ PLANNED
    Input:  demand plan (step 1), lead time distributions,
            supplier reliability, current inventory, θ*.safety_stock_multiplier
    Output: SS targets, reorder points, order-up-to levels per product-site
    Oracle: inventory_target_calculator.py (8 policy types) as BC labels
    + Inventory Adjustment TRM (in-cycle)                       ⬜ PLANNED
    + Inventory Planning Skill (cross-cycle)                    ⬜ PLANNED

  Step 3 — Supply Planning GNN [rename of current Network tGNN] ✅ IMPLEMENTED (rename)
    Input:  demand plan, inventory targets, sourcing rules, supplier data
    Output: supply plan — PO/TO/MO requirements per product-site-week
    Oracle: LP network flow optimiser (existing)
    + Supply Adjustment TRM (in-cycle)                          ⬜ PLANNED
    + Supply Planning Skill (cross-cycle)   [SKILL.md exists]   ⬜ WIRE IN

  Step 4 — RCCP GNN                                             ⬜ PLANNED
    Input:  supply plan MPS quantities, Bill of Resources, resource capacities,
            changeover matrix, current utilisation
    Output: feasibility verdict + MPS adjustments per resource per week
    Oracle: RCCP SKILL.md rules (CPOF / BoC / Resource Profile methods)
    + RCCP Adjustment TRM (in-cycle)                            ⬜ PLANNED
    + RCCP Skill (cross-cycle)              [SKILL.md exists]   ⬜ WIRE IN

Layer 1.5: Site tGNN (Operational)                             ✅ IMPLEMENTED
  Unchanged — adjusts execution TRMs at the intra-site level

Layer 1: 11 Execution TRMs + 11 Claude Skills                  ✅ IMPLEMENTED
  Unchanged
```

**Sequential dependency**: the four domain GNNs run in order. Demand plan output
is an input to Inventory GNN. Inventory targets are an input to Supply GNN. Supply
plan (MPS) is the input to RCCP. This mirrors the standard S&OP review sequence
and means each model is responsible for a coherent, auditable planning domain.

**Implementation guide**: See [PLANNING_AGENT_IMPLEMENTATION.md](PLANNING_AGENT_IMPLEMENTATION.md)
for full specification of every new component, provisioning sequence, and training pipeline.

---

## Conceptual Frame: Baseline Plan + Contextual Adjustment

Each planning layer follows the same two-step pattern established by demand planning:

```
Demand Planning (reference pattern):
  Step 1 — ML model → baseline forecast from historical patterns
  Step 2 — ForecastAdjustmentTRM (TRM) → bounded in-cycle correction
           from recent deviations, email signals, real-time context
  Step 2b — Demand Planning Skill (Claude Skill) → cross-cycle contextual
           reasoning for novel situations (NPI, geopolitical, promotions
           not yet in training data)
  Step 3 — Human consensus sign-off

Every planning domain applies this same pattern:

  GNN           → baseline plan from structure + historical distributions
  Domain TRM    → in-cycle correction (fast, trained, bounded, 1-3 day feedback)
  Domain Skill  → cross-cycle reasoning (contextual, novel, qualitative judgment)
  Human review  → approval for material changes
```

### Why two adjustment layers (TRM and Skill) rather than one?

The TRM and Skill serve fundamentally different purposes and are not alternatives:

| | Domain TRM (in-cycle) | Claude Skill (cross-cycle) |
|---|---|---|
| **When** | Within the current planning run | Between planning runs |
| **Trigger** | Escalation signal, deviation threshold | New signal arrival, human directive, novel event |
| **Reasoning type** | Pattern-matching on learned deviations | Qualitative reasoning about novel context |
| **Feedback horizon** | 1–3 days | 1–4 weeks |
| **Learns from outcomes** | Yes — RL fine-tuning on actual vs. plan | Only via SKILL.md updates and RAG memory |
| **Example** | "Demand for SKU-X is consistently 12% above model — apply 1.12× correction" | "Competitor just discontinued product Y — our demand may spike 30–40% in 6 weeks" |

The TRM handles *recurring, learnable patterns* that the GNN missed. The Skill handles
*novel situations* the TRM has no training data for. Over time, Skill decisions are recorded
in RAG decision memory and eventually become TRM training data — the 95%/5% boundary
gradually shifts as TRMs learn what Skills currently handle.

### S&OP layer: why the mechanism differs

At Layer 4, the current adjustment mechanism is **upstream injection** rather than downstream patching:

```
Domain GNNs (Layer 2):
  GNN output → [Domain TRM patches plan] → [Skill adjusts if novel] → finalized plan

S&OP GraphSAGE (Layer 4, current state):
  New constraint → [injected into DE objective] → DE re-runs → new globally-coherent θ*
```

Upstream injection produces globally coherent θ* (DE re-optimises all cross-site
dependencies simultaneously). A downstream patch could create locally-improved but
globally-infeasible policy parameters.

The S&OP Adjustment Skill (planned) will apply **bounded local corrections** to θ*
between DE runs for time-sensitive signals, marking adjustments as
`pending_de_reconciliation=True` so the next Sunday DE run confirms or revises globally.
Full details in [PLANNING_AGENT_IMPLEMENTATION.md](PLANNING_AGENT_IMPLEMENTATION.md).

---

## Critical Design Principle: Oracle = Training Only, Not Inference

The LP solver (Network tGNN) and Differential Evolution optimizer (S&OP GraphSAGE) are
**offline oracle tools** that generate labeled training data. They are never called at
inference time. The trained GNN replaces them entirely at runtime:

```
Training (offline — runs once or periodically):
  LP / DE oracle solves the optimization problem for N synthetic scenarios
  → produces labeled (graph_state, optimal_solution) pairs
  → GNN trains on those pairs via supervised behavioral cloning

Inference (online — runs every decision cycle):
  GNN forward pass only
  No LP, no DE, no scipy
  <5ms for Site tGNN, <5ms for Network tGNN, <1ms for GraphSAGE
```

This is the **oracle amortization** pattern (same as AlphaCode: expensive search generates
labels, neural network learns to predict those labels instantly). The oracle is the teacher;
the GNN is the deployed agent.

**Why this matters for quality**: The LP computes optimal flows for point-estimate inputs.
The trained GNN generalises across distribution shifts because it was fine-tuned with PPO
against stochastic simulation outcomes — it learns to be robust to demand variance in a way
a single LP solve cannot express.

| Capability | LP / DE (oracle) | Trained GNN (inference) |
|---|---|---|
| Optimal for given inputs | ✅ exact | ~95% of oracle quality |
| Runtime speed | 30–120s | <5ms |
| Generalises to new network states | ❌ re-solve each time | ✅ forward pass |
| Captures uncertainty implicitly | ❌ point estimates only | ✅ trained on stochastic scenarios |
| Explainable via attention weights | ❌ | ✅ |
| Learns site/vendor-specific patterns | ❌ | ✅ via feature embeddings |

The ~5% quality gap vs oracle-optimal is the amortization cost. In practice the gap
closes or reverses after PPO fine-tuning on simulated stochastic outcomes.

---

## Layer 1.5 — Site tGNN (Hourly Cross-TRM Coordination)

**File**: `backend/app/services/powell/site_tgnn_inference_service.py`
**Model**: `backend/app/models/gnn/site_tgnn.py` — `SiteTGNN`
**Architecture**: GATv2 + GRU, ~25K parameters, <5ms inference, 11 TRM-type nodes, ~22 directed causal edges

### What Problem It Solves

The 11 TRM agents within a site are individually optimised but do not see each other's
state. Reactive signals (HiveSignalBus) handle same-cycle communication, but they cannot
capture learned causal relationships that span multiple cycles.

Example: an aggressive ATP fulfillment strategy consistently causes MO capacity starvation
2 cycles later. The HiveSignalBus carries the ATP_SHORTAGE signal, but the TRM has no way
to know the *causal pathway* (fill now → capacity starved → late MOs → more stockouts).
The Site tGNN learns these multi-cycle cross-TRM causal edges from historical `MultiHeadTrace`
records and applies them as urgency adjustments before the next decision cycle.

### Node Features (per TRM, 18 dimensions)

```
[0]  urgency                      Current UrgencyVector slot for this TRM (0–1)
[1]  recent_decision_count        Number of decisions in the last 1 hour (rolling)
[2]  avg_confidence               Mean TRM output confidence in the last hour
[3]  override_rate                Fraction of decisions overridden by human (rolling 24h)
[4]  reward_ema                   Exponential moving average of recent rewards
[5]  cdc_trigger_count            CDC triggers fired for this TRM in last 24h
[6]  signal_density               Mean number of bus signals read per decision cycle
[7]  signal_emission_rate         Mean number of signals emitted per decision cycle
[8]  fill_rate_contribution       This TRM's estimated contribution to site fill rate
[9]  capacity_utilization         Relevant for MO/TO-centric TRMs; 0 for others
[10] backlog_pressure             Open backlog normalised by target cycle time
[11] phase_position               Current SiteAgent decision cycle phase (0–5 normalised)
[12] hive_feedback_dim_0          First of 6 HiveFeedbackFeature dimensions
[13] hive_feedback_dim_1
[14] hive_feedback_dim_2
[15] hive_feedback_dim_3
[16] hive_feedback_dim_4          site_tgnn_adjustment_magnitude (added Mar 2026)
[17] hive_feedback_dim_5          cross_trm_conflict_rate (added Mar 2026)
```

### Graph Edges (~22 directed causal edges)

Edges encode known causal relationships between TRMs:

```
ATP Executor       → Inventory Buffer    (shortage → raise buffer)
ATP Executor       → PO Creation         (shortage → trigger order)
PO Creation        → Inventory Buffer    (order placed → reduce buffer urgency)
PO Creation        → Order Tracking      (new PO → start tracking)
Inventory Buffer   → ATP Executor        (buffer raised → more ATP available)
MO Execution       → Quality Disposition (MO released → quality check follows)
MO Execution       → Maintenance Sched   (high MO load → defer maintenance)
Maintenance Sched  → MO Execution        (maintenance urgent → block MO capacity)
TO Execution       → ATP Executor        (inbound TO → more ATP supply)
Forecast Adj       → Inventory Buffer    (demand signal → buffer reoptimization)
Forecast Adj       → PO Creation         (demand signal → procurement review)
Quality Disposition→ PO Creation         (reject lot → emergency replacement order)
Quality Disposition→ Subcontracting      (quality fail → route external)
Subcontracting     → MO Execution        (external route → release internal capacity)
Order Tracking     → PO Creation         (late PO → expedite or reorder)
Order Tracking     → TO Execution        (late TO → expedite transfer)
Inventory Buffer   → TO Execution        (buffer mismatch → trigger transfer)
MO Execution       → TO Execution        (MO output → schedule outbound transfer)
ATP Executor       → Forecast Adj        (shortage pattern → demand signal)
Inventory Rebalan  → ATP Executor        (transfer → ATP supply at destination)
Inventory Rebalan  → TO Execution        (rebalance triggers TO)
Subcontracting     → Order Tracking      (subcontract PO → new order to track)
```

### Decision Algorithm

```
Input:  node_features [11, 18]  (one row per TRM)
        edge_index [2, E]       (adjacency list of causal edges)
        hidden_state [11, H]    (GRU hidden state from previous hourly tick)

Step 1 — Graph Attention (GATv2):
  For each directed edge (u → v):
    attention_weight[u,v] = softmax(MLP([h_u || h_v]))
    message[u→v] = attention_weight × W × h_u

  For each node v:
    aggregated[v] = Σ_{u: (u→v) ∈ edges} message[u→v]
    h_v_new = LayerNorm(h_v + aggregated[v])

  (2 GATv2 layers with residual connections)

Step 2 — Temporal processing (GRU):
  hidden_new[v] = GRU(h_v_new, hidden_state[v])
  # GRU preserves site context across hourly ticks

Step 3 — Output head (per TRM):
  adjustment[v] = MLP(hidden_new[v])   # 3 outputs per TRM
  urgency_delta      = tanh(adjustment[0]) × 0.30   → [-0.30, +0.30]
  confidence_delta   = tanh(adjustment[1]) × 0.20   → [-0.20, +0.20]
  coordination_score = sigmoid(adjustment[2])        → [0, 1]
```

### Output Semantics

```
urgency_delta:      Applied to UrgencyVector slot before next decision cycle.
                    Positive: boost this TRM's urgency (system needs it to act more urgently)
                    Negative: dampen this TRM's urgency (system is over-reactive here)

confidence_delta:   Applied to TRM's decision confidence threshold.
                    Positive: raise bar (this TRM should be less likely to act autonomously)
                    Negative: lower bar (this TRM can act more autonomously)

coordination_score: Cross-TRM attention weight. High = this TRM is central to current
                    cross-TRM trade-off. Used as feature in tGNN reasoning explanation.
```

### Urgency Contribution

The Site tGNN does NOT output its own urgency score — it **modifies** TRM urgencies.
The Site tGNN's contribution to the urgency system:
```
UrgencyVector[trm] += clamp(urgency_delta[trm], -0.30, +0.30)
UrgencyVector[trm] = clamp(result, 0.0, 1.0)
```

### Likelihood / Confidence

The Site tGNN does not produce a likelihood score. Its output is a directional adjustment.
The reliability of the adjustment is implicitly captured by:
- **Training loss** on held-out MultiHeadTrace records (measured in urgency prediction error)
- **CDT calibration** on cross-TRM coordination decisions (whether urgency adjustments led
  to better site-level BSC outcomes)

### Decision Reasoning (for Ask Why)

```python
# Generated by decision_reasoning.site_tgnn_reasoning(output, active_trms):
"""
Site tGNN (hourly, {timestamp}):
  Observed high {trm_A} urgency ({urgency_A:.2f}) with low {trm_B} urgency ({urgency_B:.2f}).
  Applied urgency boost of +{delta_B:.2f} to {trm_B} and dampened {trm_A} by {delta_A:.2f}.
  Causal pathway: {trm_A} shortage signal propagated via {edge_label} edge to {trm_B}.
  Coordination score: {trm_B} is central to current cross-TRM resolution (score={score:.2f}).
  Confidence adjustment: {delta_conf:+.2f} to {trm_C} (uncertainty elevated at this site).
"""
```

### Inactive TRM Handling

For sites where some TRMs are not active (e.g., a retail site has no MO Execution):
```
inactive_trms_mask[trm_idx] = True
node_features[trm_idx] = zeros(18)       # Zero input
output adjustments[trm_idx] = zeros(3)   # Zero output — no effect
```
The same model architecture works for all site types.

### Scheduling

```
Inference: hourly at :25 (5 minutes before TRM decision cycle at :30)
Training check: every 12h at :50 (SiteTGNNTrainer.evaluate_and_train())
Training trigger: if MultiHeadTrace records available AND eval_loss > threshold
```

---

## Layer 2 — Network tGNN (Daily Tactical Planning)

**File**: `backend/app/services/powell/network_tgnn_oracle.py`
**Architecture**: GATv2 on multi-site supply chain graph, ~473K parameters

### What Problem It Solves

The Site tGNN coordinates TRMs within a site. But it has no view of cross-site
inventory imbalances, multi-site demand patterns, or optimal flow allocation across
the supply network. The Network tGNN provides **daily directives** to each site:
how much of each product to expect from upstream, how much to ship downstream,
and which sites are currently under-served or over-stocked relative to global demand.

### Node Features (per site, 12 dimensions)

```
[0]  on_hand_qty              Current inventory position (normalised)
[1]  forecast_next_period     Demand forecast for next planning period (normalised)
[2]  safety_stock_qty         Target safety stock (normalised)
[3]  holding_cost_per_unit    Economic cost of excess inventory
[4]  stockout_cost_per_unit   Economic cost of shortfall
[5]  avg_weekly_demand        Historical average weekly demand (normalised)
[6]  demand_variability_cv    Coefficient of variation of demand
[7]  capacity_units           Site throughput / supply capacity (normalised)
[8]  criticality_score        Network criticality (0–1, from S&OP GraphSAGE)
[9]  supply_risk_score        Upstream supply risk score (0–1)
[10] is_source_node           Binary: site is a MARKET_SUPPLY or MANUFACTURER
[11] is_demand_node           Binary: site is a MARKET_DEMAND node
```

### Edge Features (per lane, 4 dimensions)

```
[0]  cost_per_unit            Variable transport cost (normalised)
[1]  capacity_units           Maximum units per period (normalised)
[2]  lead_time_periods        Lead time in planning periods (normalised)
[3]  priority                 Lane priority (1=primary, 2=secondary, 0=spot)
```

### Decision Algorithm (LP Oracle for Training)

The Network tGNN is trained via supervised behavioral cloning from LP-optimal labels:

```
Input:  N sites, L lanes, T planning periods

Solve network flow LP:
  Variables:  x[lane, period]  ≥ 0     (flow on each lane in each period)
              slack[site, period] ≥ 0   (unfulfilled demand slack)

  Minimize:
    Σ_{lane,period} cost[lane] × x[lane,period]    (transport cost)
    + Σ_{site,period} stockout_cost[site] × slack[site,period]  (shortage penalty)

  Subject to:
    Supply capacity:     Σ_d x[source,d,p] ≤ supply_cap[source,p]     ∀ source, period
    Lane capacity:       x[l,p] ≤ lane_cap[l]                          ∀ lane, period
    Demand satisfaction: Σ_s x[s,dest,p] + slack[dest,p] ≥ demand[dest,p]  ∀ dest, period
    Non-negativity:      x ≥ 0, slack ≥ 0

  Solver: scipy.optimize.linprog with HiGHS backend
  Fallback: proportional heuristic allocation when LP is infeasible

Output per lane per period:
  optimal_flow:           LP-optimal flow allocation
  demand_satisfaction:    fraction of demand met at each site
```

### Inference (Trained GNN)

After training, the Network tGNN replaces the LP solve with a forward pass:

```
Input:  node_features [N, 12]
        edge_features [L, 4]
        edge_index    [2, L]

Step 1 — GATv2 message passing (2 layers):
  For each edge (u → v):
    attention[u,v] = softmax(LeakyReLU(a^T [W_s h_u || W_d h_v]))
    message = attention[u,v] × W_msg h_u

  For each node v:
    h_v = ELU(W_self h_v + Σ messages from neighbors)

Step 2 — Edge prediction head:
  For each lane (u → v):
    flow_prediction[u,v] = MLP([h_u || h_v || edge_features[u,v]])
    allocation_fraction = sigmoid(flow_prediction)   → [0, 1]
    recommended_flow = allocation_fraction × lane_capacity

Step 3 — Demand satisfaction head:
  For each demand node v:
    satisfaction[v] = sigmoid(MLP(h_v))   → [0, 1] fraction of demand met

Output per site: tGNNSiteDirective
  expected_inbound[product]    Recommended inbound flow this period
  expected_outbound[product]   Recommended outbound flow this period
  demand_satisfaction          Predicted demand fill rate (= likelihood)
  allocation_priority          {product → priority rank} for ATP consumption
  exception_probability        P(supply exception this period) → urgency input
  criticality_update           Updated criticality score from network topology
```

### Urgency Contribution

The Network tGNN provides `exception_probability` per site, which feeds into TRM
urgency initialization at the start of each decision cycle:

```python
# In SiteAgent.initialize_decision_cycle():
if tgnn_directive.exception_probability > 0.7:
    # Elevate all TRM urgencies proportionally
    base_urgency_boost = (exception_probability - 0.7) / 0.3 × 0.30
    for trm_name in active_trms:
        urgency_vector.update(trm_name,
            min(1.0, urgency_vector.read(trm_name) + base_urgency_boost))
```

### Likelihood = Demand Satisfaction Score

The Network tGNN's `demand_satisfaction` output IS its likelihood estimate:
```
likelihood = demand_satisfaction   # P(demand met this period at this site)
```
A site with `demand_satisfaction = 0.95` → the tGNN is 95% confident it will meet
demand. A site with `demand_satisfaction = 0.55` → uncertainty is high; escalation
and/or buffer review triggered.

### Decision Reasoning (for Ask Why)

```python
# Generated by decision_reasoning.execution_tgnn_reasoning(output, site):
"""
Network tGNN (daily, {timestamp}):
  Site {site_id}: demand forecast {forecast:.0f} units, exception probability {exc_prob:.0%}.
  Recommended inbound: {inbound:.0f} units across {n_lanes} active lanes.
  Allocation priority: {priority_product} → tier {priority_tier}.
  Demand satisfaction: {satisfaction:.1%} (confidence in meeting demand this period).
  Network criticality: {criticality:.2f} — {criticality_label}.
  Primary constraint: {constraint_label} (capacity/lead_time/cost/multi-source).
"""
```

---

## Layer 4 — S&OP GraphSAGE (Weekly Strategic Policy)

**File**: `backend/app/services/powell/sop_graphsage_oracle.py`
**Training**: `backend/app/models/gnn/scalable_graphsage.py` — `ScalableGraphSAGE`
**Architecture**: GraphSAGE with mean aggregation, ~500K parameters

### What Problem It Solves

Policy parameters θ (safety stock multipliers, service level targets, reorder point
and order-up-to days, sourcing split) must be set for every product-site combination.
Setting them manually requires a supply chain expert and takes weeks. Running
Differential Evolution fresh each week takes 30–120 seconds per network.

The S&OP GraphSAGE is trained to **predict θ*** from graph features alone in <1ms.
This amortises the expensive DE optimization — the oracle generates (graph, θ*) pairs
offline; the GraphSAGE infers θ* for new network states at negligible cost.

### Policy Parameters θ (per site)

| Parameter | Range | Meaning |
|-----------|-------|---------|
| `safety_stock_multiplier` | [0.5, 3.0] | Scale SS formula result up/down |
| `service_level_target` | [0.80, 0.99] | Target fill rate for SS calculation |
| `reorder_point_days` | [3, 21] | Days before stockout to place order |
| `order_up_to_days` | [7, 60] | Days-of-supply target for replenishment |
| `sourcing_split` | [0.0, 1.0] | Fraction from primary supplier vs. secondary |

### Oracle: How θ* Is Generated

The DE oracle generates labeled training data by solving the MC optimization problem
for each synthetic network:

```
DE Objective (Monte Carlo estimate of expected total cost under policy θ):

For each MC scenario (num_mc_scenarios = 30 default, 100+ for production):
  For each site i in network:
    params = PolicyParams.from_vector(θ[i])
    ss_qty = params.safety_stock_multiplier
             × site.avg_weekly_demand × site.demand_variability_cv
             × sqrt(site.avg_lead_time_weeks)
    order_up_to = params.order_up_to_days / 7 × site.avg_weekly_demand

    inventory = site.on_hand_qty
    For each week in [0, planning_horizon]:
      demand = D.realised_demand(rng, mean=site.avg_weekly_demand, cv=site.demand_variability_cv)
      lead_time = D.realised_lead_time_weeks(rng, mean=site.avg_lead_time_weeks, cv=site.lead_time_variability_cv)
      # demand ~ Normal (CLT; symmetric around forecast)
      # lead_time ~ LogLogistic (fat right tail; Lokad recommendation)

      reorder_point = params.reorder_point_days / 7 × site.avg_weekly_demand
      if inventory <= reorder_point:
        order_qty = max(0, order_up_to + ss_qty - inventory)
        if order_qty > 0: cost += site.ordering_cost
        if lead_time <= 1.0: inventory += order_qty   # simplified immediate receipt

      fulfilled = min(inventory, demand)
      shortfall = demand - fulfilled
      inventory = max(0, inventory - demand)

      cost += inventory × site.unit_cost × site.annual_holding_rate / 52   # holding
      cost += shortfall × site.stockout_cost_per_unit                      # stockout

    # Soft service-level constraint penalty:
    implied_sl = 1 - min(0.5, ss_qty / max(site.avg_weekly_demand × site.avg_lead_time_weeks, 1e-6))
    if implied_sl < params.service_level_target:
      cost += (params.service_level_target - implied_sl)
              × site.stockout_cost_per_unit × site.avg_weekly_demand × 52

Return: mean_total_cost across all MC scenarios

Optimizer:
  scipy.optimize.differential_evolution(objective, bounds=POLICY_BOUNDS × num_sites,
    maxiter=100, popsize=10, tol=0.01)
  → θ* = argmin E[total_cost]
```

### Node Features (per site, 14 dimensions)

```
[0]  avg_weekly_demand          (normalised by max demand in network)
[1]  demand_variability_cv
[2]  avg_lead_time_weeks        (normalised by max lead time)
[3]  lead_time_variability_cv
[4]  on_hand_qty                (normalised by max on-hand)
[5]  unit_cost                  (normalised by max unit cost)
[6]  annual_holding_rate
[7]  stockout_cost_per_unit     (normalised by max stockout cost)
[8]  ordering_cost              (normalised by max ordering cost)
[9]  criticality_score
[10] is_supply_node             (MARKET_SUPPLY or MANUFACTURER)
[11] is_demand_node             (MARKET_DEMAND)
[12] is_manufacturer            (MANUFACTURER)
[13] is_inventory_node          (INVENTORY / DC)
```

### Edge Features (per lane, 4 dimensions)

```
[0]  lead_time_weeks            (normalised)
[1]  transport_cost_per_unit    (normalised)
[2]  reliability                on-time delivery rate
[3]  capacity_units_per_week    (normalised)
```

### Inference Algorithm (trained GraphSAGE)

```
Input:  node_features [N, 14]
        edge_features [L, 4]
        edge_index    [2, L]

Step 1 — GraphSAGE message passing (3 layers):
  For each layer k:
    h_neighbor[v] = MEAN({h_u : u ∈ neighbors(v)})
    h_v^{k+1} = ReLU(W^k [h_v^k || h_neighbor[v]])
    h_v^{k+1} = L2_normalize(h_v^{k+1})

Step 2 — Policy head (per site):
  θ_raw[v] = MLP(h_v^K)   # K=3 dimensions × PARAM_DIM=5 = 5 outputs
  θ[v] = clamp(θ_raw[v], POLICY_BOUNDS)   # enforce parameter bounds

Output per site:
  PolicyParams(safety_stock_multiplier, service_level_target,
               reorder_point_days, order_up_to_days, sourcing_split)
```

### Training Loop (Supervised on Oracle Samples)

```
Loss = MSE(predicted_θ, oracle_θ*)   # per parameter per site

Tracked metrics:
  parameter_mae[param_name]           per-parameter accuracy
  objective_correlation               R² between predicted and oracle objective value
  de_converged_fraction               fraction of oracle samples where DE converged

Inference replaces weekly DE with:
  forward_pass(graph_features) → θ*   in ~1ms vs. 30–120s for DE
```

### Weekly CFA Re-Optimization

Each Sunday at 04:00, `_run_cfa_optimization()` in `relearning_jobs.py`:
1. Loads all active supply chain configs
2. For each config, runs `SoPGraphSAGEOracle.generate_samples(num_scenarios=50)`
3. Updates `powell_policy_parameters` table with new θ*
4. If GraphSAGE model is trained, re-trains incrementally on new samples
5. Falls back to pure DE result if GraphSAGE prediction error > 20% vs. DE

### Urgency Contribution

The S&OP GraphSAGE does not produce urgency directly. Its policy parameters θ feed into:
- `SafetyStockCalculator.compute_safety_stock()`: uses `safety_stock_multiplier` and
  `service_level_target` from θ
- `POCreationTRM`: uses `reorder_point_days` and `order_up_to_days` from θ
- `InventoryBufferTRM`: the TRM bounds `[lo, hi]` are scaled by θ `safety_stock_multiplier`

Changes in θ propagate to TRM urgency on the next decision cycle because:
- A raised `safety_stock_multiplier` → higher baseline SS → POCreationTRM triggers sooner
  → higher `trigger_reason=INVENTORY_BUFFER` frequency → higher PO Creation urgency

### Likelihood = DE Convergence + Objective Quality

```
likelihood = 1.0 if de_converged else 0.7

# For GraphSAGE inference (not DE):
prediction_error = |predicted_objective - de_objective| / de_objective
likelihood = max(0.0, 1.0 - prediction_error × 2)
```
Low likelihood → the model is uncertain about θ* → weekly DE re-run is triggered to
refresh the ground truth.

### Decision Reasoning (for Ask Why)

```python
# Generated by decision_reasoning.sop_graphsage_reasoning(output, network):
"""
S&OP GraphSAGE (weekly, {timestamp}):
  Site {site_id} ({master_type}):
    Criticality score: {criticality:.2f} — {criticality_label}.
    Bottleneck indicator: {bottleneck_score:.2f} (flow concentration {concentration:.1%}).
    Resilience score: {resilience:.2f} (sourcing diversity, lane redundancy).
    Safety stock multiplier: {ss_multiplier:.2f}× baseline
      (higher than average: {reason_label}).
    Service level target: {sl_target:.1%} (network-optimal for this cost structure).
    Reorder point: {rop_days:.0f} days (lead time {lt_weeks:.1f}w + variability buffer).
    Order-up-to: {outo_days:.0f} days.
    Primary sourcing split: {split:.0%} primary / {(1-split):.0%} secondary.
"""
```

---

## GNN Explanations — Three Mechanisms

Every GNN decision can be explained at three levels of depth. All three are available via
the Ask Why endpoint (`AgentContextExplainer`).

### Mechanism 1: Pre-Computed Reasoning Text (instant, no LLM call)

The three `*_reasoning()` functions in `decision_reasoning.py` generate human-readable
text from the GNN output dataclasses at decision time. This text is stored in the DB
(in the `proposed_reasoning` column on `gnn_directive_reviews`) so Ask Why returns it
instantly without a model call.

Each reasoning string names the active constraints, the key drivers, and the confidence
level in plain language. See the "Decision Reasoning (for Ask Why)" sections above for
the exact templates per layer.

### Mechanism 2: GATv2 Attention Weights (structural — which neighbors drove this decision)

GATv2 computes a per-edge attention weight at inference time. These are directly
interpretable without any post-hoc computation:

**Network tGNN** — which upstream sites drove the allocation decision for a demand site:

```python
attention_weights = {
    "Supplier_A → DC_West":      0.72,   # Primary: capacity + cost features dominant
    "Supplier_B → DC_West":      0.18,   # Secondary
    "DC_East  → DC_West":        0.10,   # Lateral rebalancing signal minimal
}
# "72% of DC_West's inbound allocation was driven by Supplier_A's
#  capacity, cost, and lead time features."
```

**Site tGNN** — which cross-TRM causal edges were active this cycle:

```python
attention_weights = {
    "ATP_Executor → PO_Creation":       0.68,   # Strong: shortage propagating upstream
    "MO_Execution → Quality":           0.22,   # Moderate: production batch completing
    "Forecast_Adj → Inventory_Buffer":  0.05,   # Quiet: no new demand signals
    ...
}
# "The urgency boost applied to PO_Creation was driven 68% by the
#  ATP_Executor→PO_Creation causal edge (ATP shortage active)."
```

**S&OP GraphSAGE** — which neighboring sites' properties shaped a site's θ* prediction:

```python
attention_weights = {
    "Supplier_A → DC_West":  0.61,   # Supplier risk affects DC's SS multiplier
    "DC_West → Retailer_1":  0.28,   # Downstream fill rate pressure
    "DC_West → Retailer_2":  0.11,
}
# "DC_West's safety stock multiplier of 1.6× was shaped 61% by
#  Supplier_A's high lead time variability propagating through the graph."
```

Attention weights are read directly from the GATv2 output during the forward pass —
no additional computation required.

### Mechanism 3: Gradient Saliency (feature-level — which input dimensions drove the output)

For any specific GNN output value, `torch.autograd.grad()` gives the sensitivity of that
output to each input feature. This is the most granular explanation and is computed
on-demand when a user clicks Ask Why (adds ~2ms to the response):

```python
# S&OP GraphSAGE — why is DC_West's safety_stock_multiplier = 1.6?
feature_importance = {
    "demand_variability_cv":     0.41,   # Highest driver (CV=0.47 at this site)
    "avg_lead_time_weeks":       0.28,   # Long lead time from Supplier_A
    "stockout_cost_per_unit":    0.19,   # High penalty for this product class
    "on_hand_qty":               0.07,   # Current inventory low
    "criticality_score":         0.05,   # Moderate network centrality
}
# "Your safety stock multiplier is 1.6× primarily because this site has
#  high demand variability (CV=0.47) combined with long lead times (4.2w).
#  The stockout cost for this product class ($42/unit) reinforces the
#  conservative policy."
```

```python
# Network tGNN — why is DC_West's demand_satisfaction = 0.94?
feature_importance = {
    "forecast_next_period":       0.38,
    "supply_risk_score":          0.31,   # Supplier_A disruption risk elevated
    "capacity_units":             0.18,
    "avg_lead_time_weeks":        0.09,
    "demand_variability_cv":      0.04,
}
# "94% confidence in meeting demand. Supply risk (0.31 weight) is the
#  primary uncertainty: Supplier_A's risk score is 0.68 this period."
```

### Summary: Which Mechanism Answers Which Question

| Question | Mechanism | Latency |
|---|---|---|
| "What did the agent decide and why?" | Pre-computed reasoning text | 0ms (DB read) |
| "Which sites / TRMs influenced this decision?" | GATv2 attention weights | ~1ms (forward pass read) |
| "Which input features drove the output value?" | Gradient saliency | ~2ms (autograd call) |
| "How confident is the agent?" | `demand_satisfaction` / `likelihood` / `de_converged` | 0ms (stored in DB) |

All three mechanisms are surfaced by `AgentContextExplainer` when the Ask Why endpoint
is called. The pre-computed reasoning text is shown first; attention weights and gradient
saliency are shown in the "Evidence" expandable section.

---

## How the Three Layers Interact

### Top-Down Information Flow

```
S&OP GraphSAGE (weekly)
    │ θ* per site → powell_policy_parameters table
    ▼
TRM Initialization:
    SafetyStockCalculator reads θ.safety_stock_multiplier, θ.service_level_target
    POCreationTRM reads θ.reorder_point_days, θ.order_up_to_days
    InventoryBufferTRM bounds scaled by θ.safety_stock_multiplier

Network tGNN (daily)
    │ tGNNSiteDirective per site → SiteAgent context
    ▼
TRM Decision Cycle:
    exception_probability → boosts all TRM urgencies proportionally
    allocation_priority   → ATP Executor reads tier assignment
    expected_inbound      → PO Creation reads expected receipt
    demand_satisfaction   → InventoryBufferTRM reads expected fill rate

Site tGNN (hourly)
    │ urgency_adjustment [11] per site
    ▼
UrgencyVector.adjust(trm_name, delta)
    TRM reads modulated urgency before decision
```

### Bottom-Up Feedback Flow

```
TRM Decisions (per cycle)
    │ decision + outcome → powell_*_decisions tables
    ▼
Hourly (:32) OutcomeCollector fills actual outcomes

Site tGNN Training (every 12h)
    Reads MultiHeadTrace records (cross-TRM coordination history)
    BC + PPO on cross-TRM urgency labels
    ↓
    Improved urgency_adjustments next cycle

Network tGNN Training (weekly or on-demand)
    Reads powell_*_decisions aggregate outcomes per site
    Compares actual flow vs. directed flow
    ↓
    Updated tGNNSiteDirective accuracy

S&OP GraphSAGE Training (after DE oracle runs)
    New (graph, θ*) pairs from DE optimizer
    Supervised fine-tuning on prediction loss
    ↓
    Updated θ* predictions for all sites
```

### Escalation Vertical Chain

```
If TRM CDC triggers persist after 3+ retraining cycles:
    EscalationArbiter.escalate_to_operational()
    → triggers Network tGNN re-run for affected sites
    → updates tGNNSiteDirective.exception_probability

If Network tGNN shows sustained demand forecast error > 15%:
    EscalationArbiter.escalate_to_strategic()
    → triggers S&OP GraphSAGE DE re-optimization
    → updates policy parameters θ
```

See [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md) for the full vertical
escalation protocol.

---

## Worked Example: Bottom-Up Capacity Escalation (95% OEE → Extra Shift → RCCP → S&OP)

> **Scenario**: Site XYZ has been running at 95% OEE for several days. Despite
> maximum utilisation, the production backlog is still growing. The site needs an extra
> shift. How does this observation travel from the Site tGNN all the way up to the
> RCCP layer and then the S&OP GraphSAGE?
>
> This example traces the **bottom-up feedback path** — the mirror image of the
> planned shutdown worked example above which followed the top-down path.

### What "95% OEE and still behind" means structurally

OEE (Overall Equipment Effectiveness) of 95% sounds good, but the sustainable maximum
for most manufacturing equipment is ~85%. Running above that degrades reliability over
time (increased breakdown risk) and leaves no maintenance window. If the site is at 95%
OEE and **still accumulating backlog**, two things are simultaneously true:

1. **Execution is not the problem** — the TRMs are already optimising within available
   capacity. Urgency boosts will not help. This is a capacity constraint, not an
   efficiency problem.
2. **Capacity is the binding constraint** — the production plan is infeasible at current
   capacity. The plan must either be revised (reduce commitments) or capacity must be
   expanded (extra shift, outsourcing).

This distinction is critical: if the system treats it as an execution problem it will
keep boosting TRM urgency forever without solving it. The correct response is to
**escalate to the capacity planning and S&OP layers**.

---

### Stage 1 — Detection at the Site Level (MOExecutionTRM + MaintenanceSchedulingTRM)

**`MOExecutionTRM`** tracks OEE as part of operational state:
```python
site_operational_state = {
    "oee_current":          0.95,    # measured this cycle
    "oee_sustainable_max":  0.85,    # configured threshold (above = unsustainable)
    "mo_backlog_units":     4200,    # open MOs not yet released
    "capacity_units_week":  1000,    # nameplate
    "effective_capacity":   950,     # at 95% OEE
    "planned_output_week":  1150,    # what the plan requires
    "shortfall":            200,     # planned - effective = infeasible gap
}
# Decision: release MOs in priority order, but cannot close the shortfall
# Urgency: 0.88 (HIGH — backlog persisting over 3+ cycles)
# decision_reasoning: "Capacity constrained: shortfall 200 units/week. OEE at
#   95% (above sustainable 85%) — further urgency boost will not close gap."
```

**`MaintenanceSchedulingTRM`** independently flags the OEE overshoot:
```python
# Reliability risk at 95% OEE:
# Equipment MTBF degrades — probability of unplanned breakdown rises
# Decision: recommend scheduled maintenance window soon to prevent unplanned failure
# But: maintenance window competes with the production backlog
# Urgency: 0.61 (cross-TRM conflict with MO_Execution)
```

**Site tGNN** (hourly, Layer 1.5) sees the cross-TRM conflict:
```python
cross_trm_attention = {
    "MO_Execution → Maintenance_Scheduling": 0.71,  # high conflict — compete for capacity
    "MO_Execution → Inventory_Buffer":       0.18,  # buffer depletion from backlog
    "ATP_Executor → MO_Execution":           0.11,  # commitments outstanding
}
urgency_adjustments = {
    "MO_Execution":           +0.22,   # still boosts, but...
    "Maintenance_Scheduling": +0.18,   # ...also boosts maintenance flag
    "Inventory_Buffer":       +0.15,   # buffer target needs review
}
coordination_score = 0.31   # LOW — TRMs in conflict, not cooperating
```

The low `coordination_score` and sustained cross-TRM bottleneck emit a
`CROSS_TRM_BOTTLENECK` InterHiveSignal on the inter-hive bus.

---

### Stage 2 — Escalation Arbiter Triggers (Site → Operational Layer)

After **3+ consecutive cycles** where MO CDC triggers persist despite urgency boosts,
`EscalationArbiter.escalate_to_operational()` fires:

```python
escalation_payload = {
    "site_id":          "XYZ",
    "trigger":          "PERSISTENT_MO_CDC",
    "cycles_persisted": 4,
    "root_cause":       "CAPACITY_CONSTRAINT",   # not execution — plan infeasible
    "oee_overshoot":    0.10,                    # 0.95 - 0.85
    "weekly_shortfall": 200,                     # units
    "maintenance_risk": "ELEVATED",              # breakdown risk from OEE overshoot
}
```

The arbiter writes a `PowellEscalationLog` record and triggers an **on-demand
Network tGNN re-run** for the affected sites (rather than waiting for the daily cycle).

---

### Stage 3 — RCCP Validation (Capacity Feasibility Check)

The Network tGNN re-run incorporates the capacity constraint from the escalation
payload. This triggers the **RCCP (Rough Cut Capacity Planning) validation** step —
the agent that checks whether the production plan is feasible given available capacity.

**What RCCP checks**:
```
For each site and each planning period:
  required_output[t] = MPS planned production quantity
  available_capacity[t] = nameplate × (1 - OEE_headroom_reserve)

  At XYZ: required = 1150 units/week, available = 850 units/week (at sustainable OEE)
  Infeasibility gap = 300 units/week
```

**RCCP generates three options** (ranked by net economic value):

| Option | Description | Cost | Fill Rate Impact | Net EV |
|---|---|---|---|---|
| A — Extra shift | +8h/week labour at XYZ | $12K/week | Closes gap fully | +$47K/week |
| B — Outsource gap | Subcontract 300 units/week | $18K/week | Closes gap fully | +$41K/week |
| C — Reduce commitments | Lower ATP by 300 units/week | $0 | −18% fill rate | −$28K/week (lost revenue) |

**RCCP → AAP authorization request** for Option A (extra shift):
```python
AuthorizationRequest(
    originator="RCCP_Agent",
    action="extra_shift_XYZ",
    requires_authorization_from=["HR_Agent", "Finance_Agent"],
    scorecard={
        "cost":          "$12K/week",
        "benefit":       "$59K/week (stockout avoidance + service level)",
        "net_benefit":   "$47K/week",
        "risk":          "Equipment reliability if sustained >4 weeks",
    },
    what_if_branch="scenario_branch_XYZ_extra_shift_2026W12",
)
```

If HR and Finance agents authorize within their authority thresholds, the extra
shift is approved and a directive is written back to `MOExecutionTRM` at XYZ.
If it exceeds their thresholds (e.g. >4 weeks of extra shifts = structural capacity
decision), it escalates to the human S&OP meeting.

---

### Stage 4 — Network tGNN Updates Directives for Affected Sites

Whether or not the extra shift is authorized, the Network tGNN immediately updates
its `tGNNSiteDirective` for all sites downstream of XYZ to reflect the capacity reality:

```python
# Sites served by XYZ (during the infeasibility gap):
tGNNSiteDirective(site="DC_South") = {
    "demand_satisfaction":  0.74,   # reduced — XYZ cannot meet full plan
    "exception_probability": 0.71,  # high — active capacity constraint
    "allocation_priority":   1,     # protect remaining supply
}
tGNNSiteDirective(site="DC_East") = {
    "demand_satisfaction":  0.68,
    "exception_probability": 0.66,
}
# Also: directives for alternative source sites (if sourcing_split allows):
tGNNSiteDirective(site="XYZ_ALT") = {
    "demand_forecast_correction": +18%,  # pull more from alternative site
    "allocation_priority":         1,
}
```

These directives immediately change TRM behaviour at downstream DCs: ATP tightens,
rebalancing evaluates lateral transfers, order tracking flags known-late orders.

---

### Stage 5 — S&OP GraphSAGE Re-optimises θ* (If Sustained)

If the RCCP infeasibility persists beyond a single week (structural, not transient),
`EscalationArbiter.escalate_to_strategic()` fires, triggering a CFA re-optimisation:

**What changes in the GraphSAGE DE objective**:
```python
site_xyz_features["capacity_units_per_week"] = 850   # sustainable, not nameplate 1000
# OR if extra shift authorised:
site_xyz_features["capacity_units_per_week"] = 1150  # nameplate + shift
```

**How θ* adjusts** across the network:

| Parameter | Site | Direction | Why |
|---|---|---|---|
| `service_level_target` | XYZ downstream DCs | ↓ | Honest about reduced fill rate |
| `safety_stock_multiplier` | XYZ downstream DCs | ↑ | More buffer needed (lower throughput) |
| `sourcing_split` | Downstream DCs | Shifts → alt sources | Compensate for XYZ shortfall |
| `order_up_to_days` | XYZ | ↓ (if extra shift) | Higher throughput → replenish faster |
| `service_level_target` | XYZ (if extra shift) | Restores | Gap closed |

The updated θ* propagates top-down through the same path described in the top-down
flow: Network tGNN reads new parameters → updates directives → Site tGNN adjusts
urgencies → TRMs execute under new policy.

---

### The Complete Loop

```
Site XYZ TRMs
    MOExecutionTRM: oee=0.95, backlog=4200, shortfall=200/week
    MaintenanceSchedulingTRM: breakdown_risk=ELEVATED
    ↓ (urgency boosts ineffective after 3 cycles)

Site tGNN (Layer 1.5, hourly)
    coordination_score=0.31 (TRMs in conflict)
    CROSS_TRM_BOTTLENECK InterHiveSignal emitted
    ↓

EscalationArbiter (every 2h)
    escalate_to_operational() → on-demand Network tGNN re-run
    ↓

RCCP Validation (triggered by Network tGNN re-run)
    Infeasibility confirmed: 300 units/week gap
    Options A/B/C ranked by EV
    AAP AuthorizationRequest → HR + Finance agents
    ↓

Network tGNN (re-run)
    tGNNSiteDirective updated for all XYZ downstream sites
    demand_satisfaction reduced, exception_probability raised
    ↓

S&OP GraphSAGE (if sustained → escalate_to_strategic)
    DE re-optimises θ* with corrected capacity ceiling
    θ* propagates back down to all sites
    ↓

Human S&OP Meeting (if extra shift > authority threshold)
    Probabilistic BSC shows three options with EV
    Human approves extra shift → directive written
    Override recorded → feeds OverrideEffectivenessPosterior
    → future GraphSAGE training learns to anticipate this scenario
```

### Key Design Points

1. **Urgency escalation has a ceiling**: The Site tGNN can boost urgency, but it cannot
   manufacture capacity. The escalation arbiter's job is to detect when the problem has
   moved from "execution efficiency" to "capacity feasibility" and stop wasting urgency
   boosts on an insoluble execution problem.

2. **RCCP is the capacity feasibility agent**: It sits between the Network tGNN
   (what the plan requires) and the S&OP GraphSAGE (what the policy says). Its job is
   to catch infeasibilities before they become backlog crises, and generate economically-
   ranked options for the AAP or human to authorize.

3. **The S&OP plan is adjusted, not replaced**: The extra shift is not a full S&OP
   re-run. It is a **targeted adjustment** to θ* at XYZ and its downstream sites —
   exactly analogous to a demand planner adjusting a specific SKU's forecast for a
   promotional event without re-running the full statistical model.

4. **Feedback closes the loop**: The human authorization of the extra shift (if needed)
   is an override of the RCCP agent's recommendation. It is scored via
   `OverrideEffectivenessPosterior(user_id, trm_type="rccp")` and fed back into
   future training so the system learns the organization's capacity authorization
   thresholds without having to be told explicitly.

---

## Worked Example: Planned Manufacturing Shutdown

> **Scenario**: During an S&OP meeting a planner says "manufacturing site XYZ will be down
> for one week in three months for major new equipment installation."
>
> This end-to-end walkthrough shows exactly how that statement moves from natural language
> to changed TRM decisions at every site in the network.

### Stage 1 — Capture (Azirella → DirectiveService → Layer 4)

The planner enters the statement into the Azirella input in the top navigation bar.
The two-phase directive flow runs:

1. `POST /directives/analyze` — the LLM parser extracts:
   - `metric`: capacity
   - `direction`: decrease
   - `magnitude`: 100% (total shutdown)
   - `duration`: 1 week
   - `timing_offset`: ~13 weeks from today
   - `geography`: site XYZ
   - `reason`: planned equipment installation

2. No clarification gaps (all required fields present) — user submits immediately.
   `DirectiveService` routes to **Powell Layer 4 (S&OP GraphSAGE)**: the 3-month horizon
   and single-site origin with network-wide downstream impact match the S&OP tier.

3. The directive is persisted in `user_directives`. A **constraint event record** is written
   to `powell_policy_parameters` (or its staging buffer) before the next CFA re-optimisation:
   ```python
   site_xyz_constraint = {
       "planned_shutdown_week": current_week + 13,
       "planned_shutdown_duration_weeks": 1,
       "capacity_fraction_during_shutdown": 0.0,
   }
   ```

### Stage 2 — S&OP GraphSAGE Evaluation (Constraint Injection → DE Re-optimisation → θ* Update)

#### What changes in the graph features

Site XYZ's node feature vector is augmented with the planned capacity constraint before
the next DE MC objective evaluation:

```python
# Before directive
site_xyz_features = [
    avg_weekly_demand=1500,            # dim 0
    demand_variability_cv=0.22,        # dim 1
    avg_lead_time_weeks=2.5,           # dim 2
    ...
    capacity_units_per_week=1000,      # dim 10
    criticality_score=0.72,            # dim 13
]

# After constraint injection
site_xyz_features = [
    avg_weekly_demand=1500,
    demand_variability_cv=0.22,
    avg_lead_time_weeks=2.5,
    ...
    capacity_units_per_week=1000,      # base unchanged
    planned_shutdown_fraction=1.0,     # 100% shutdown at t+13
    planned_shutdown_duration=1.0,     # weeks
    criticality_score=0.72,
]
```

#### What the DE MC objective sees

The DE re-optimizer evaluates N Monte Carlo scenarios with the constraint active.
For each scenario:

```
Sample demand trace: Normal(μ=avg_weekly_demand, σ=cv × μ) for all sites
Sample lead times:   LogLogistic(μ=avg_lead_time, σ=lt_cv × μ) for all lanes
Override for XYZ:    capacity[t+13] = 0   (full week zero production)

Production gap created = weekly_demand_downstream × 1 week
The gap must be:
  (a) Pre-built before t+13 (raise order_up_to_days so MOs run early), OR
  (b) Absorbed by safety stock buffers at downstream DCs, OR
  (c) Partially deferred (accept reduced service level for one week)

DE minimises: E[total_cost + stockout_cost] across N scenarios
```

#### How θ* changes per affected site

| Parameter | Site | Direction | Why |
|---|---|---|---|
| `safety_stock_multiplier` | XYZ | ↑ (e.g. 1.2× → 1.8×) | Need output buffer before shutdown |
| `safety_stock_multiplier` | Downstream DCs | ↑ | Need finished goods buffer during shutdown |
| `order_up_to_days` | XYZ | ↑ | Trigger pre-build MOs in weeks t-3 to t-1 |
| `reorder_point_days` | XYZ (weeks before shutdown) | ↑ | Order raw materials early enough |
| `service_level_target` | Downstream DCs | May soften slightly | Gap may not be fully bufferable |
| `sourcing_split` | Downstream DCs | Shifts toward secondary suppliers | Compensate for XYZ gap during shutdown week |

Updated θ* is written to `powell_policy_parameters` (keyed by `config_id + site_id + product_id`).

### Stage 3 — Downward Percolation (θ* → Network tGNN → Site tGNN → TRMs)

#### θ* → Network tGNN (daily)

At the next daily Network tGNN run the updated `powell_policy_parameters` are read as
graph node features. The trained GNN forward pass (no LP call — pure inference <5ms)
produces updated `tGNNSiteDirective` for every affected site:

```python
# At site XYZ, weeks t+10 through t+12 (pre-build window):
tGNNSiteDirective(site="XYZ") = {
    "demand_forecast_correction": +12%,    # signal to pre-build now
    "exception_probability":       0.68,   # high — known production gap imminent
    "allocation_priority":         1,      # elevated for upstream lanes
    "expected_inbound":            ...,    # increased raw material expected
}

# At downstream DC_South, week t+13 (during shutdown):
tGNNSiteDirective(site="DC_South") = {
    "demand_satisfaction":         0.71,   # reduced fill rate expected
    "exception_probability":       0.62,
    "allocation_priority":         1,      # elevated — protect from other demand draws
}
```

These directives are injected into the SiteAgent context for all affected sites.

#### Network tGNN → Site tGNN (hourly, Layer 1.5)

At the next hourly Site tGNN run for XYZ, the 11-node cross-TRM coordination graph
reflects the elevated `exception_probability`:

```python
# Site tGNN outputs for XYZ in pre-build window:
urgency_adjustments = {
    "MO_Execution":       +0.25,   # manufacture now — pre-build window active
    "Inventory_Buffer":   +0.20,   # buffer targets just changed — review needed
    "PO_Creation":        +0.18,   # upstream materials must arrive before t+13
    "TO_Execution":       +0.12,   # stage finished goods toward downstream DCs
    "ATP_Executor":       -0.05,   # slightly deprioritise spot commitments
}
```

The GATv2 attention over the 22 causal edges shows strong activation on:
- `MO_Execution → Inventory_Buffer` (pre-build is changing buffer levels)
- `PO_Creation → Inventory_Buffer` (raw material timing affects buffer)

#### Site tGNN → TRMs (Layer 1 — per decision cycle)

**At site XYZ (weeks t-3 to t-1 before shutdown)**:

- **`MOExecutionTRM`**: Receives `urgency = 0.87` (base 0.62 + delta +0.25). Releases
  pre-build MOs ahead of normal schedule. `decision_reasoning` text: *"Pre-build for
  planned week-t+13 shutdown: producing 1,000 additional units now to buffer downstream
  DCs. θ*.order_up_to_days raised to 28 (was 14)."*

- **`POCreationTRM`**: `order_up_to_days` now larger from θ* update. Urgency tier = CRITICAL
  (0.9). Orders enough raw material to support pre-build. PO placed 6 weeks before shutdown
  to clear lead time.

- **`InventoryBufferTRM`**: `safety_stock_multiplier` raised from 1.2× to 1.8×. Calculates
  new buffer target. Emits `BUFFER_INCREASED` HiveSignal. `decision_reasoning`: *"S&OP θ*
  update (2026-03-14): safety_stock_multiplier raised 1.2→1.8 for planned capacity event
  at t+13."*

**At downstream DCs (week t+13 — during shutdown)**:

- **`ATPExecutorTRM`**: Receives reduced `demand_satisfaction = 0.71` from Network tGNN
  directive. Tightens available-to-promise. Low-priority orders deferred. `urgency = 0.74`.

- **`InventoryRebalancingTRM`**: Evaluates lateral cross-DC transfers if one DC holds more
  pre-built stock than needed.

- **`OrderTrackingTRM`**: Flags known-late orders with reason *"planned manufacturing
  shutdown at XYZ"* rather than raising a new exception — exception_probability was
  already signalled, so no false alarm is generated.

### Stage 4 — Outcome Inference (Digital Twin Monte Carlo)

The stochastic simulation engine runs N=1000+ scenarios against the updated θ* to give
the S&OP meeting a probabilistic answer to "what will happen?":

```
For each scenario i:
  Sample 13-week demand trace (Normal per site)
  Sample lead times (LogLogistic per lane)
  Enforce capacity[t+13] = 0 at XYZ
  Execute pre-build logic with new θ*
  Record: service_level, stockout_cost, inventory_cost, backlog per DC

Aggregate outputs (Probabilistic Balanced Scorecard):
  P10/P50/P90 service level distribution for affected DCs during shutdown week
  Expected total cost increase vs. baseline (no shutdown, no pre-build)
  P(stockout = 0 during shutdown week) given optimised pre-build
```

Example output shown in the S&OP dashboard:

| Metric | Without Pre-Build θ* | With Optimised θ* |
|---|---|---|
| P(OTIF > 95%) during shutdown week | 22% | 71% |
| E[incremental stockout cost] | $84K | $19K |
| E[incremental pre-build carrying cost] | $0 | $31K |
| E[net benefit of pre-build] | — | **+$34K** |

**Conformal prediction intervals** on all numbers carry distribution-free 90% coverage
guarantees (powered by `ConformalOrchestrator`):
> "With 90% probability, incremental stockout cost is between $12K and $28K."

### Stage 5 — Ask Why at Any Level

| Question | Answer source | Latency |
|---|---|---|
| "Why did XYZ's MO get released early?" | Pre-computed reasoning text in `powell_mo_decisions` | 0ms |
| "Which downstream sites drove XYZ's higher safety stock multiplier?" | GATv2 attention weights from GraphSAGE forward pass | ~1ms |
| "What feature input mattered most to the multiplier increase?" | Gradient saliency (`planned_shutdown_fraction`=0.44, `order_up_to_days`=0.29, `criticality_score`=0.18) | ~2ms |
| "What is the probability range for stockout cost?" | Conformal prediction interval on MC simulation output | 0ms (stored) |

### Key Design Points

1. **No re-solve at runtime**: The S&OP GraphSAGE forward pass takes <1ms even with the
   constraint injection. The expensive DE re-optimisation runs once (or on the weekly CFA
   schedule) and writes θ* to the DB. All downstream layers read from `powell_policy_parameters`.

2. **Proportional response**: Each downstream layer only adjusts within its own authority.
   TRMs never call across sites — cross-site information arrives only through tGNNSiteDirective
   and θ* parameters. This is the multi-site coordination stack operating as designed.

3. **Pre-build decision is economic, not rule-based**: The DE found pre-building is worth
   +$34K EV. If the MC objective had found pre-building cost more than it saved (e.g., very
   low demand uncertainty, very short shutdown), θ* would NOT have raised `order_up_to_days`.
   The system adapts the response to the economics of each specific scenario.

4. **Graceful degradation**: If the GraphSAGE model has not been retrained recently and
   the constraint injection changes the graph distribution substantially, `de_converged` may
   be False. The system falls back to the heuristic pre-build rule (raise SS multiplier by
   `shutdown_weeks / avg_lead_time_weeks`). No silent failure.

---

## Configuration

### Site tGNN

```python
# SiteAgentConfig fields:
enable_site_tgnn: bool = False   # Feature flag — enable when MultiHeadTrace data available
```

```sql
-- Migration: 20260308_site_tgnn_config.py
ALTER TABLE site_agent_configs ADD COLUMN enable_site_tgnn BOOLEAN DEFAULT FALSE;
```

### Network tGNN

Configured via `NetworkTGNNConfig` in `SiteAgent.tgnn_directive_config`. Updated daily
by the Network tGNN inference service. Stored in `powell_allocations` table.

### S&OP GraphSAGE

Configured via `SoPGraphSAGEOracle` parameters:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `num_mc_scenarios` | 30 (dev), 100+ (prod) | MC accuracy for DE objective |
| `de_max_iter` | 100 | DE convergence budget |
| `de_popsize` | 10 | DE population multiplier |
| `de_tol` | 0.01 | DE convergence tolerance |

Policy parameters stored in `powell_policy_parameters` table, keyed by `config_id` + `site_id` + `product_id`.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/models/gnn/site_tgnn.py` | Site tGNN model definition (GATv2+GRU) |
| `backend/app/services/powell/site_tgnn_inference_service.py` | Hourly inference + urgency adjustment |
| `backend/app/services/powell/site_tgnn_trainer.py` | 3-phase training (BC → PPO → calibration) |
| `backend/app/services/powell/network_tgnn_oracle.py` | LP oracle for Network tGNN training data |
| `backend/app/models/gnn/scalable_graphsage.py` | S&OP GraphSAGE model definition |
| `backend/app/services/powell/sop_graphsage_oracle.py` | DE oracle for GraphSAGE training data |
| `backend/app/services/powell/decision_reasoning.py` | Pre-computed reasoning text for Ask Why |
| `backend/app/services/powell/relearning_jobs.py` | Schedules (Site tGNN :25, CFA Sun 04:00) |
| `backend/app/services/powell/training_distributions.py` | Shared stochastic variables across tiers |

---

## See Also

- [TRM_DECISION_ALGORITHMS.md](TRM_DECISION_ALGORITHMS.md) — Heuristic logic, urgency and likelihood for all 11 TRMs
- [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md) — Architecture, state vectors, reward functions
- [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) — Hive signal bus, decision cycle phases, multi-site coordination stack
- [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md) — Training pipeline and oracle-based data generation
- [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md) — Vertical escalation between GNN layers
- [AGENTIC_AUTHORIZATION_PROTOCOL.md](AGENTIC_AUTHORIZATION_PROTOCOL.md) — Cross-site authorization (Layer 3)

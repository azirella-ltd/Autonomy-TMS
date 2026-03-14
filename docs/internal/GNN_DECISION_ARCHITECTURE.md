# GNN Decision Architecture — Site tGNN, Network tGNN, and S&OP GraphSAGE

> **Audience**: Engineers and data scientists working on the GNN layers.
> This document specifies how each GNN layer makes decisions, how urgency and
> likelihood are computed, and how the layers interact.
> For TRM heuristic algorithms see [TRM_DECISION_ALGORITHMS.md](TRM_DECISION_ALGORITHMS.md).
> For training pipeline see [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md).

---

## Layer Architecture Overview

```
Layer 4: S&OP GraphSAGE (Strategic)
  Scope:   Entire supply network
  Timing:  Weekly (Sunday 04:00) + on-demand via provisioning
  Output:  Policy parameters θ per site (safety stock multipliers, service
           level targets, reorder point days, order-up-to days, sourcing split)
  Method:  Amortised Differential Evolution (DE oracle → supervised GraphSAGE)

Layer 2: Network tGNN (Tactical)
  Scope:   Multi-site daily planning
  Timing:  Daily
  Output:  tGNNSiteDirective per site (allocation priority, demand forecast
           correction, exception probability, recommended flow adjustments)
  Method:  Supervised BC on LP oracle labels → PPO fine-tuning

Layer 1.5: Site tGNN (Operational)
  Scope:   Single site — cross-TRM coordination
  Timing:  Hourly (at :25)
  Output:  Urgency adjustments [11, 3] per TRM per site
  Method:  BC from MultiHeadTrace → PPO with site-level BSC reward
```

All three layers feed **downward** (parameters/directives to lower layers) and the lower
layers provide **feedback upward** (outcomes/signals). No layer calls across sites directly
— all cross-site information flows through the Network tGNN directive or AAP.

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

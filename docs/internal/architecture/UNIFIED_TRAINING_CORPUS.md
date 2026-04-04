# Unified Training Corpus — Technical Architecture

> **Autonomy Platform — Core Architecture**
>
> Defines the single source of truth for all agent training data across the
> four-layer planning stack. Replaces the previous architecture of independent
> synthetic data pipelines per layer.

---

## Table of Contents

1. [Motivation and Problem Statement](#1-motivation)
2. [Design Principles](#2-design-principles)
3. [Architecture Overview](#3-architecture)
4. [The Anchor: ERP Baseline Extraction](#4-erp-baseline)
5. [Perturbation Generation](#5-perturbations)
6. [Digital Twin Simulation and TRM Decision Capture](#6-simulation)
7. [Aggregation: From TRM Decisions to Layer-Specific Samples](#7-aggregation)
8. [Per-Layer Training Pipelines](#8-per-layer-training)
9. [Continuous Learning: Real Outcomes into the Same Corpus](#9-continuous)
10. [Storage and Schema](#10-storage)
11. [Provisioning Flow](#11-provisioning)
12. [Implementation Files](#12-files)

---

## 1. Motivation and Problem Statement

Prior to this architecture, each of the four planning layers generated its own training
data in isolation:

| Layer | Training Data Source | Issue |
|-------|---------------------|-------|
| Layer 4 - S&OP GraphSAGE | `SoPGraphSAGEOracle` synthetic random networks + DE oracle | Orphan code, never actually called from production; cold-start with random weights |
| Layer 2 - Tactical tGNNs | `NetworkFlowOracle` synthetic LP on random features | Does not read real DB tables; per-period LP with no inventory carry-over |
| Layer 1.5 - Site tGNN | `_generate_synthetic_site_tgnn_samples` random matrices | No connection to real TRM outcomes at cold-start |
| Layer 1 - TRMs | Per-TRM curriculum generators + deterministic engines | Independent per TRM type; no cross-TRM interaction signal |

### The Problems

1. **No tenant specificity** - every tenant gets the same synthetic foundation.
2. **Layer disagreement** - strategic, tactical, site, and role layers learn different
   views of what "optimal" means because they trained on different data.
3. **ERP baseline ignored** - the `erp_baseline` plan_version is extracted at provisioning
   but used only for UI comparison, never as training data.
4. **Real outcomes do not propagate up** - TRM outcomes only feed TRM retraining; they
   never reach tactical or strategic layers.
5. **Orphan oracles** - `SoPGraphSAGEOracle` is fully implemented but never called,
   meaning S&OP GraphSAGE has never been trained in production; it runs with random
   weights via a "cold-start" fallback.

### The Solution

One unified training corpus, anchored on the ERP baseline, built bottom-up from TRM
decisions, aggregated upward into per-layer views. All four layers train on the same
reality.

---

## 2. Design Principles

1. **Anchor on reality**: the ERP baseline is the single source of ground truth for
   "what works today." All synthetic variations are perturbations around this anchor,
   not free-form random networks.

2. **Bottom-up generation**: TRM decisions are the finest granularity. Higher layers
   are aggregations, not independent oracles. If a TRM makes N decisions across M
   scenarios, the site tGNN, tactical tGNNs, and S&OP GraphSAGE all derive their
   training samples from those N*M decisions.

3. **Consistency across layers**: if a decision at the TRM level produces a good
   outcome, the upward aggregation reflects that as positive signal at the site,
   tactical, and strategic levels. Conversely if a decision is bad, the signal
   propagates up consistently. Layers cannot disagree because they share the corpus.

4. **No synthetic cold-start**: the ERP baseline is always available at provisioning.
   No tenant starts with generic synthetic networks.

5. **Real outcomes append to the same corpus**: post-provisioning, real decision
   outcomes are appended as new samples. The corpus grows; retraining uses the
   full history.

6. **Perturbations replace network randomness**: instead of sampling random networks,
   perturb the real network around its observed values. This gives generalization
   while keeping specificity.

7. **Age-weighted samples**: old perturbation samples decay in weight as real outcome
   samples accumulate. The corpus shifts from 95% synthetic / 5% real on day 1 to
   50/50 at month 3 to majority-real after a year.

---

## 3. Architecture

```
                    +----------------------------+
                    |    ERP Baseline Extract    |
                    |  (provisioning, live CDC)  |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |  Perturbation Generator    |
                    |  (N=500 scenarios default) |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |   Digital Twin Simulator   |
                    |  Runs each perturbation    |
                    |  with all 12 TRMs active   |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |     TRM Decision Log       |  <-- Level 1 samples
                    |  (state, action, reward)   |
                    +-------------+--------------+
                                  |
                                  v
                    +----------------------------+
                    |        Aggregator          |
                    +------+-------------+-------+
                           |             |
                 +---------+             +-----------+
                 v                                   v
        +----------------+                +--------------------+
        | Level 1.5      |                | Level 2            |  <-- Site + Tactical samples
        | (site x time)  |                | (network x domain) |
        +----------------+                +----------+---------+
                                                     |
                                                     v
                                          +------------------------+
                                          | Level 4                |  <-- Strategic samples
                                          | (network x theta*)     |
                                          +------------------------+

After provisioning, real outcomes flow back:

        TRM runs in production
             |
             v
        powell_*_decisions + outcome_collector
             |
             v
        training_corpus (append as new Level 1 samples)
             |
             v
        Aggregator re-runs on new samples
             |
             v
        All four layers retrain (CDC-driven)
```

---

## 4. The Anchor: ERP Baseline Extraction

The ERP baseline is extracted during provisioning as part of the SAP/Odoo/D365
integration. It lives in the database with `plan_version = 'erp_baseline'`:

- `supply_plan` - per-period net requirements, planned orders, safety stock targets
- `inbound_order` / `inbound_order_line` - open purchase orders
- `outbound_order` / `outbound_order_line` - open sales orders
- `manufacturing_order` - active production orders
- `inventory_level` - current on-hand, in-transit, allocated by (product, site)
- `forecast` - current demand forecast from the ERP or prior Autonomy run
- `inventory_policy` - safety stock, reorder points, max stock per (product, site)
- `sourcing_rules` - approved vendors, split ratios, lead times
- `transportation_lane` - network topology with lane-specific lead times and costs

The `ERPBaselineSnapshot` dataclass captures all of this at a point in time and serves
as the anchor for perturbation generation.

---

## 5. Perturbation Generation

For each perturbation scenario, the following parameters are varied independently
within configurable ranges:

| Parameter | Default Range | Distribution |
|-----------|--------------|--------------|
| Demand volume | [-15%, +15%] per product x site | Triangular around baseline |
| Demand CV | [0.5x, 2.0x] baseline | Log-uniform |
| Lead time mean | [-20%, +25%] per lane | Triangular, right-skewed (delays more likely) |
| Lead time CV | [0.7x, 1.8x] baseline | Log-uniform |
| Unit cost | [-10%, +10%] per product | Uniform |
| Stockout cost | [-15%, +20%] per product | Uniform |
| Ordering cost | [-10%, +15%] per (vendor, product) | Uniform |
| Lane capacity | [-20%, +10%] per lane | Triangular |
| Supplier reliability | [-10pp, +5pp] per vendor | Uniform |
| Seasonal intensity | [0.7x, 1.5x] amplitude | Uniform |

Each perturbation preserves the **topology** (same sites, same lanes, same products)
but varies the operating parameters. This way the agents learn how policies must adapt
to changes in the operating environment, not how to handle fundamentally different
networks.

**Default**: N=500 perturbations per provisioning run. Configurable via
`training_corpus.perturbation_count` tenant setting. Each perturbation runs independently.

### Deterministic Seeding

Each perturbation is generated from a deterministic seed derived from
`(config_id, perturbation_index)`. This makes the corpus reproducible: retraining
with the same seed produces the same perturbations.

---

## 6. Digital Twin Simulation and TRM Decision Capture

For each perturbation, the Digital Twin simulator runs a full planning horizon
(default 26 weeks) with all 12 TRMs active. The simulator:

1. Initializes inventory positions from the perturbed ERP baseline
2. For each period in the horizon:
   - Realizes stochastic demand (draws from perturbed distributions)
   - Realizes stochastic lead times on in-transit orders
   - Runs the 6-phase TRM decision cycle: SENSE -> ASSESS -> ACQUIRE -> PROTECT -> BUILD -> REFLECT
   - Each TRM emits HiveSignals read by downstream TRMs
   - Records every TRM decision to the corpus
3. Computes per-TRM rewards at the end of the horizon (cost savings, stockout reduction,
   service level achieved)

### TRM Decision Capture Format

Each TRM decision becomes a Level 1 training sample:

```python
{
    "sample_id": uuid,
    "corpus_id": training_corpus.id,
    "scenario_id": perturbation_id,
    "period": period_index,
    "layer": 1,
    "trm_type": "po_creation" | "atp_allocation" | ... (one of 12),
    "product_id": "SKU-123",
    "site_id": "DC-NE",
    "state_features": {
        # TRM-specific feature vector at decision time
        "inventory_level": 420,
        "days_of_supply": 5.2,
        "demand_cv": 0.35,
        "lead_time": 7,
        "signal_context": {...},
        "urgency": 0.72,
        ...
    },
    "action": {
        # TRM-specific action space
        "order_quantity": 500,
        "vendor_id": "VENDOR-02",
        "delivery_date": "2026-05-15",
        ...
    },
    "reward_components": {
        "cost_delta": -1250,
        "service_level": 0.96,
        "stockout_avoided": True,
        "holding_cost": 340,
        ...
    },
    "aggregate_reward": 0.87,
    "cycle_id": uuid,
    "cycle_phase": "ACQUIRE",
}
```

---

## 7. Aggregation: From TRM Decisions to Layer-Specific Samples

The aggregator is a pure data transformation. It reads Level 1 samples and produces
Level 1.5, Level 2, and Level 4 samples. No new simulation or oracle calls are needed.

### Level 1.5 - Site tGNN Samples

Aggregate by `(scenario_id, site_id, time_window)` where `time_window` is a
configurable bucket (default 1 week).

```python
{
    "sample_id": uuid,
    "layer": 1.5,
    "scenario_id": perturbation_id,
    "site_id": "DC-NE",
    "window": "2026-W14",
    "per_trm_features": {
        # 11 slots (one per active TRM at this site), 18 features each
        "atp_executor": {
            "avg_confidence": 0.84,
            "decision_count": 127,
            "override_rate": 0.02,
            "avg_urgency": 0.61,
            "signal_density": 0.43,
            "reward_ema": 0.78,
            ...
        },
        "po_creation": {...},
        ... 9 more TRMs
    },
    "site_aggregate_reward": 0.81,
    "cross_trm_coordination_loss": 0.12,  # measured from conflicting decisions
    "hive_signal_activity": {...},  # counts of signals emitted per type
}
```

The target for the Site tGNN is the optimal per-TRM urgency adjustment that would have
minimized the cross-TRM coordination loss, computed retrospectively from the observed
decision sequence.

### Level 2 - Tactical tGNN Samples

Aggregate by `(scenario_id, planning_period)`. One sample per perturbation per period,
containing the full network snapshot.

```python
{
    "sample_id": uuid,
    "layer": 2,
    "scenario_id": perturbation_id,
    "period": "2026-04",
    "network_graph": {
        "node_features": [[...] for each site],  # 14-dim node features
        "edge_features": [[...] for each lane],  # 4-dim edge features
        "edge_index": [[from_indices], [to_indices]],
    },
    "sop_embeddings": [[...] for each site],  # from Level 4 if available
    "demand_features": [[p50, p10, p90, volatility, bullwhip] for each site],  # from LightGBM
    "supply_outcomes": {
        # target for Supply Planning tGNN
        "exception_probability_by_site": {...},
        "order_recommendation_by_site": {...},
        "allocation_priority_by_site": {...},
        "lead_time_risk_by_site": {...},
        "pipeline_coverage_days_by_site": {...},
    },
    "inventory_outcomes": {
        # target for Inventory Optimization tGNN
        "buffer_adjustment_signal_by_site": {...},  # Tanh [-1, +1]
        "rebalancing_urgency_by_site": {...},
        "stockout_probability_by_site": {...},
        "inventory_health_by_site": {...},
    },
    "capacity_outcomes": {
        # target for Capacity/RCCP tGNN
        "planned_utilization_by_site": {...},
        "capacity_buffer_pct_by_site": {...},
        "feasibility_score_by_site": {...},
        "bottleneck_risk_by_site": {...},
    },
    "period_total_reward": 0.76,  # aggregate of all TRM rewards in this period
}
```

Targets are derived from the TRM decisions that occurred in each period:

- **exception_probability**: fraction of PO TRM decisions that were flagged as exceptions
- **order_recommendation**: average order quantity recommended by PO TRM, normalized
- **allocation_priority**: average allocation priority from ATP TRM
- **buffer_adjustment_signal**: average buffer adjustment from Inventory Buffer TRM
- **rebalancing_urgency**: fraction of Rebalancing TRM decisions that fired
- **stockout_probability**: observed stockout rate in simulation
- **planned_utilization**: average capacity utilization from MO TRM decisions
- **bottleneck_risk**: fraction of periods where MO TRM flagged capacity constraint

The tactical tGNNs learn to predict these aggregated outcomes from the network graph
and demand features alone, amortizing the TRM decision logic into a fast graph inference.

### Level 4 - S&OP GraphSAGE Samples

Aggregate by `(scenario_id)`. One sample per perturbation.

```python
{
    "sample_id": uuid,
    "layer": 4,
    "scenario_id": perturbation_id,
    "network_graph": {
        "node_features": [[...] for each site],  # 14-dim node features
        "edge_features": [[...] for each lane],  # 4-dim edge features
        "edge_index": [[...], [...]],
    },
    "theta_star": {
        # Policy parameters inferred from TRM decisions across the scenario
        "safety_stock_multiplier": {site_id: float, ...},   # from Buffer TRM actions
        "service_level_target":    {site_id: float, ...},   # from ATP fill rate achieved
        "reorder_point_days":      {site_id: float, ...},   # from PO TRM timing
        "order_up_to_days":        {site_id: float, ...},   # from PO TRM quantities
        "sourcing_split":          {site_id: float, ...},   # from sourcing decisions
    },
    "objective_value": 12450.32,  # total scenario cost (lower = better)
    "converged": True,
    "perturbation_parameters": {
        "demand_scale": 1.12,
        "lead_time_scale": 0.95,
        ...
    },
}
```

The S&OP GraphSAGE learns to predict theta_star from the network graph alone. Because
theta_star is inferred from actual TRM decisions that produced good outcomes in
simulation, this is the right target for policy parameter prediction.

### Theta_star Inference Logic

For each site and each policy parameter, theta_star is computed by backward-inferring
what the TRM decisions imply:

- **safety_stock_multiplier**: the ratio of the site's effective safety stock (derived
  from Buffer TRM's decisions across the scenario) to the formula baseline
- **service_level_target**: the observed fill rate achieved at this site in the scenario
- **reorder_point_days**: the average days-of-supply at which the PO TRM triggered orders
- **order_up_to_days**: the average days-of-supply targeted by the PO TRM's order
  quantities
- **sourcing_split**: the fraction of PO volume from the primary vendor vs backup,
  observed across the PO TRM's decisions

Only scenarios where the aggregate reward exceeds a threshold (`reward_percentile > 50`)
contribute to theta_star. Poor-reward scenarios are used as negative examples with
inverted weights rather than directly as training targets.

---

## 8. Per-Layer Training Pipelines

Each layer's training pipeline consumes its aggregated samples:

### Layer 1 - TRMs

```python
samples = corpus.get_samples(layer=1, trm_type="po_creation")
trainer = TRMTrainer("po_creation")
trainer.train(
    samples=samples,
    method="behavioral_cloning",  # Phase 1
    epochs=10,
)
trainer.train(
    samples=samples,  # same samples, different training method
    method="offline_rl_cql",  # Phase 2
    epochs=20,
)
```

Phase 1 does behavioral cloning (predict action from state). Phase 2 does offline
reinforcement learning using the observed rewards. Both use the same corpus.

### Layer 1.5 - Site tGNN

```python
samples = corpus.get_samples(layer=1.5, site_id=site_id)
trainer = SiteTGNNTrainer(site_key=site_id)
trainer.train_phase1_bc(samples)     # behavioral cloning on per-TRM features
trainer.train_phase2_ppo(samples)    # PPO using site_aggregate_reward
```

### Layer 2 - Tactical tGNNs

```python
samples = corpus.get_samples(layer=2)

supply_trainer = SupplyPlanningTGNNTrainer(config_id)
supply_trainer.train(samples, target_key="supply_outcomes")

inventory_trainer = InventoryOptimizationTGNNTrainer(config_id)
inventory_trainer.train(samples, target_key="inventory_outcomes")

capacity_trainer = CapacityRCCPTGNNTrainer(config_id)
capacity_trainer.train(samples, target_key="capacity_outcomes")
```

### Layer 4 - S&OP GraphSAGE

```python
samples = corpus.get_samples(layer=4)
trainer = SoPGraphSAGETrainer(samples)
trainer.train(epochs=100)
trainer.save(f"checkpoints/{tenant_id}/{config_id}/sop_graphsage_{config_id}.pt")
```

The GraphSAGE learns to predict theta_star from graph features. At inference time
(weekly S&OP cycle), it takes ~1ms instead of ~60s for a full DE optimization.

---

## 9. Continuous Learning: Real Outcomes into the Same Corpus

Post-provisioning, real decisions from the `powell_*_decisions` tables flow back into
the corpus as new Level 1 samples. The `OutcomeCollectorService` measures outcomes
after configurable delays (4 hours for ATP, 7 days for PO, 30 days for forecast
adjustment) and computes rewards.

### Flow

```
TRM decision -> powell_*_decisions table (immediate)
            -> OutcomeCollectorService polls (hourly)
            -> Measures actual outcome vs predicted
            -> Computes reward via RewardCalculator
            -> Appends to training_corpus as Layer 1 sample with is_real=true
            -> Aggregator re-runs on new samples
            -> Produces new Layer 1.5, 2, 4 samples
            -> CDC retraining service picks up the new samples
            -> Retrains affected layers
```

### Corpus Growth and Weighting

Each sample has `origin` in `{"perturbation", "real"}` and `created_at`. When retraining,
samples are weighted:

```
w(sample) = base_weight * decay(age) * origin_weight
decay(age) = exp(-age_days / 365)          # 1-year half-life
origin_weight = 1.0 if real else 0.5       # real outcomes count double
```

This produces the phase progression described in `HOW_AGENTS_LEARN.md`:

- Month 0: 100% perturbation, weighted 500 samples
- Month 3: 80% perturbation, 20% real, weighted 640 samples
- Month 12: 40% perturbation, 60% real, weighted 1200 samples
- Month 24: 20% perturbation, 80% real, weighted 1600 samples

Perturbation samples never fully drop out - they serve as regularization against
overfitting to recent conditions.

---

## 10. Storage and Schema

### `training_corpus` table

```sql
CREATE TABLE training_corpus (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    config_id INTEGER NOT NULL REFERENCES supply_chain_configs(id) ON DELETE CASCADE,
    layer NUMERIC(3,1) NOT NULL,  -- 1, 1.5, 2, or 4
    scenario_id VARCHAR(64),      -- perturbation UUID or "real"
    origin VARCHAR(20) NOT NULL,  -- "perturbation" | "real"
    trm_type VARCHAR(50),         -- Layer 1 only
    site_id VARCHAR(100),         -- Layer 1, 1.5
    product_id VARCHAR(100),      -- Layer 1 only
    period VARCHAR(20),           -- Layer 2 (e.g., "2026-04")
    window VARCHAR(20),           -- Layer 1.5 (e.g., "2026-W14")
    sample_data JSONB NOT NULL,   -- The full sample payload
    reward FLOAT,                 -- Aggregate reward for this sample
    weight FLOAT NOT NULL DEFAULT 1.0,
    decision_id BIGINT,           -- FK to powell_*_decisions if origin=real
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_corpus_tenant_config ON training_corpus(tenant_id, config_id);
CREATE INDEX idx_corpus_layer ON training_corpus(config_id, layer);
CREATE INDEX idx_corpus_scenario ON training_corpus(config_id, scenario_id);
CREATE INDEX idx_corpus_origin ON training_corpus(config_id, origin, created_at);
CREATE INDEX idx_corpus_trm ON training_corpus(config_id, layer, trm_type) WHERE layer = 1;
```

### Row-level security

RLS enforced on `tenant_id`. No cross-tenant corpus access.

### Retention

- Perturbation samples: retained indefinitely (low volume, ~500 per provisioning)
- Real samples: retained for 2 years, then compressed to monthly aggregates
- Decayed-weight samples with `weight < 0.05` are physically deleted to keep indexes fast

---

## 11. Provisioning Flow

The provisioning sequence is updated as follows:

```
Step 1:  warm_start              (existing — seed default config)
Step 2:  cfa_optimization        (existing — DE on initial policy params)
Step 3:  lgbm_forecast           (existing — LightGBM baseline forecast)
Step 4:  erp_baseline_snapshot   (NEW — load ERP baseline into corpus seed)
Step 5:  corpus_generation       (NEW — perturbation + simulation + TRM capture)
Step 6:  corpus_aggregation      (NEW — Level 1 -> 1.5, 2, 4)
Step 7:  sop_graphsage           (UPDATED — trains on Level 4 samples)
Step 8:  supply_tgnn             (UPDATED — trains on Level 2 samples)
Step 9:  inventory_tgnn          (UPDATED — trains on Level 2 samples)
Step 10: capacity_tgnn           (UPDATED — trains on Level 2 samples)
Step 11: site_tgnn               (UPDATED — trains on Level 1.5 samples)
Step 12: trm_training            (UPDATED — trains on Level 1 samples)
Step 13: rl_training             (UPDATED — same Level 1 samples, RL method)
Step 14: backtest_evaluation     (existing)
Step 15: supply_plan             (existing)
Step 16: rccp_validation         (existing)
Step 17: decision_seed           (existing)
Step 18: conformal               (existing)
Step 19: scenario_bootstrap      (existing)
Step 20: briefing                (existing)
```

Steps 4-13 are the new or updated training data + training pipeline. Steps 14-20
validate and deploy.

### Compute Budget

| Step | Time | Notes |
|------|------|-------|
| erp_baseline_snapshot | ~30s | Pure DB reads |
| corpus_generation | 30-90 min | 500 perturbations x ~6s simulation each, parallelizable |
| corpus_aggregation | ~5 min | Pure data transformation |
| sop_graphsage training | ~10 min | ~500 Level 4 samples |
| tactical tGNN training (x3) | ~30 min | ~500 Level 2 samples per tGNN |
| site_tgnn training | ~20 min | ~2500 Level 1.5 samples (5 sites x 500 scenarios) |
| trm_training | ~60 min | ~250K Level 1 samples (500 scenarios x 500 decisions each) |
| rl_training | ~60 min | Same samples, offline RL |

Total: 3-4 hours for provisioning (within the current budget).

---

## 12. Implementation Files

### New files

| File | Purpose |
|------|---------|
| `models/training_corpus.py` | `TrainingCorpusSample` ORM model |
| `services/training_corpus/corpus_service.py` | Main API: `create_corpus()`, `get_samples()`, `append_real_outcome()` |
| `services/training_corpus/erp_baseline_extractor.py` | Loads ERP baseline into `ERPBaselineSnapshot` |
| `services/training_corpus/perturbation_generator.py` | Generates N perturbed scenarios from baseline |
| `services/training_corpus/simulation_runner.py` | Runs Digital Twin with TRMs for each perturbation |
| `services/training_corpus/aggregator.py` | Rolls up Level 1 -> 1.5, 2, 4 |
| `services/training_corpus/theta_inference.py` | Infers theta_star from TRM decisions |
| `migrations/versions/20260404_training_corpus.py` | `training_corpus` table |

### Updated files

| File | Change |
|------|--------|
| `services/provisioning_service.py` | New steps 4-6, updated steps 7-13 |
| `services/powell/sop_graphsage_oracle.py` | `SoPGraphSAGEOracle` deleted, `SoPGraphSAGETrainer` updated to consume Level 4 samples |
| `services/powell/tactical_tgnn_training_service.py` | Consumes Level 2 samples instead of `NetworkFlowOracle` |
| `services/powell/site_tgnn_trainer.py` | Phase 1 BC consumes Level 1.5 samples instead of synthetic |
| `services/powell/trm_trainer.py` | Phase 1 BC consumes Level 1 samples; curriculum generators deprecated |
| `services/powell/outcome_collector.py` | New path: append to `training_corpus` as real Level 1 samples |
| `services/powell/cdc_retraining_service.py` | Triggers aggregator to re-roll samples upward before retraining |

### Deleted files

| File | Reason |
|------|--------|
| `services/powell/network_tgnn_oracle.py` | LP oracle no longer needed (corpus has tactical targets) |
| Per-TRM curriculum generators | Replaced by real TRM decisions in simulation |
| `services/powell/sop_graphsage_oracle.py::SoPGraphSAGEOracle` (class only, keep trainer) | Synthetic network sampler no longer needed |
| `_generate_synthetic_site_tgnn_samples` | Replaced by Level 1.5 aggregation |

---

## Summary

The unified training corpus is the single source of truth for all agent training in
Autonomy. It is:

- **Anchored** on the tenant's real ERP baseline
- **Generated** via perturbations and Digital Twin simulation
- **Bottom-up**: TRM decisions are the finest granularity
- **Aggregated** upward into Level 1.5, 2, and 4 samples
- **Continuous**: real outcomes append to the same corpus
- **Consistent**: all four layers train on the same reality

This replaces the previous architecture of four independent synthetic training pipelines
with one coherent flow from ERP baseline to strategic policy parameters.

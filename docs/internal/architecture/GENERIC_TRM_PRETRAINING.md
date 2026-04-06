# Generic TRM Pre-Training — Architecture and Deployment Plan

> **Autonomy Platform — Core Architecture**
>
> Moves the 12 Tiny Recursive Models (TRMs) from per-tenant curriculum
> training to a single, universal, pre-trained checkpoint shipped with
> Autonomy. Per-tenant structural learning is relocated entirely to the
> Site tGNN (Layer 2) which already exists for this purpose. This document
> covers the architectural rationale, the per-ERP teacher strategy, and a
> phased deployment plan.

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [What Changes](#2-what-changes)
3. [Architectural Layers](#3-architectural-layers)
4. [Per-ERP Teacher Coverage](#4-per-erp-teacher-coverage)
5. [Pre-Training Corpus Design](#5-pre-training-corpus-design)
6. [Site tGNN as the Per-Tenant Adaptation Layer](#6-site-tgnn)
7. [Provisioning Pipeline After Adoption](#7-provisioning)
8. [Checkpoint Hierarchy](#8-checkpoints)
9. [Validation and Success Metrics](#9-validation)
10. [Open Questions and Fallback Positions](#10-open-questions)
11. [Deployment Plan — Phased Rollout](#11-deployment-plan)

---

## 1. Motivation

Autonomy currently re-teaches classical MRP, ATP, DRP, buffer arithmetic
and lot-for-lot logic to every tenant from scratch during provisioning.
Each tenant runs:

- ~60–200k historical (state, action, outcome) samples extracted from
  the tenant's ERP history
- ~70k simulation samples from the Digital Twin rollouts
- Behavioral cloning per TRM type (Phase 1)
- PPO fine-tuning per TRM type (Phase 2)
- ~45–90 minutes of GPU training time per tenant

**Observation**: the rules being learned — MRP net requirements, ATP
consumption, reorder-point math, AATP priority tiering, lot-for-lot
ordering, buffer calculation, quality disposition logic — are
**universal across tenants**. "Place a PO when projected on-hand drops
below reorder point + safety stock" is the same decision whether the
tenant sells groceries, electronics, or industrial equipment. The TRMs
are re-discovering the same rulebook every time, and the per-tenant
curriculum forces them to swim in tenant-specific noise to do so.

**What is not universal** is the *intra-site structural coupling*:
which products share BOMs, which workcenters share tooling, which
customers share delivery windows, which SKUs cannibalize each other.
This variation is per-tenant and per-site, but **it is already the
Site tGNN's job to learn it.** The Site tGNN (GATv2+GRU, always-on,
one per site) sits on top of the 12 TRMs and modulates their urgency
vectors via graph attention. It is the learned intra-site coordinator.

### The disconnect

Today we train the TRMs per-tenant as if they needed to learn both the
universal rulebook AND the per-tenant coordination. This is wasteful:

- The universal rulebook is re-derived from tenant noise
- The per-tenant coordination is already handled by a dedicated layer
  above
- The TRMs end up underfitting universal rules because they have to
  spend capacity on tenant-specific variation the tGNN should be
  absorbing

### The fix

Split the training burden along the natural seam:

1. **Layer 1 TRMs become universal** — pre-trained once, frozen,
   shipped with Autonomy as weight files
2. **Layer 2 Site tGNN carries all per-tenant structural learning** —
   already designed for this, already trained per-site from historical
   coordination outcomes
3. **Layer 3 Tactical tGNNs + Layer 4 S&OP GraphSAGE remain per-tenant**
   — they always were genuinely tenant-specific

---

## 2. What Changes

### From

```
Per tenant, every provisioning:
  trm_training       (BC phase, ~15 min, 12 TRM types)
  rl_training        (PPO phase, ~15 min, 12 TRM types)
  backtest_evaluation
  site_tgnn          (one per site, ~5 min each)
  ...

Training data per tenant: 60–200k historical + 70k simulation samples
Training time per tenant: 45–90 minutes
Per-tenant artifacts: 12 TRM checkpoints + N Site tGNN checkpoints
```

### To

```
Offline (once, shipped):
  generic_trm_pretraining  (~days of GPU, done once by Autonomy team)

Per tenant, every provisioning:
  historical_corpus_extract   (for conformal + Site tGNN + backtest)
  trm_load_pretrained         (~1 second, load weights from disk)
  site_tgnn                   (one per site, ~5 min each — same as today)
  conformal_calibration       (from historical residuals)
  backtest_evaluation         (sanity check against held-out actuals)
  ...

Training data per tenant: 5–20k historical for Site tGNN + conformal
Training time per tenant: 10–20 minutes (60–70% reduction)
Per-tenant artifacts: 0 TRM checkpoints + N Site tGNN checkpoints
Global artifacts: 12 frozen TRM weight files, same across all tenants
```

### Headline numbers (projected)

| Metric | Today | After Generic Pre-Training |
|---|---|---|
| TRM training per tenant | 30 min | 0 (weights loaded from disk) |
| Total training per tenant | 45–90 min | 10–20 min |
| Training data required per tenant | 60–200k samples | 5–20k samples |
| TRM checkpoints in the system | 12 × N tenants | 12 global, 0 per tenant |
| New tenant onboarding GPU cost | ~1 GPU-hour | ~0.2 GPU-hour |
| Day-one decision quality | Depends on curriculum quality | Bounded below by universal rule coverage |

---

## 3. Architectural Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ Layer A: Pre-trained generic TRMs                                   │
│                                                                      │
│   12 TRMs, one per decision type. Joint architecture with 12        │
│   output heads (shared encoder + per-TRM head).                     │
│                                                                      │
│   Trained ONCE, offline, by the Autonomy team.                      │
│   Shipped as weight files in the Docker image.                      │
│   Same weights across all tenants. Frozen.                          │
│                                                                      │
│   Inputs are normalized: quantities log-scaled, times in hours,     │
│   demand CV in standard form, inventory as days-of-supply.          │
│                                                                      │
│   Outputs are LOCAL urgency vectors + proposed actions for this     │
│   TRM against this (product, site) state. No coordination.          │
│                                                                      │
│   Encodes:                                                           │
│     - MRP net requirements arithmetic                                │
│     - ATP consumption and AATP priority tiering                     │
│     - Lot-for-lot, fixed-lot, and POQ lot sizing                    │
│     - Reorder-point + safety-stock math (all common formulas)       │
│     - Base-stock, (s,S), (R,Q), (R,s,S) inventory policies          │
│     - DRP pull logic                                                 │
│     - Quality disposition (accept/partial-accept/reject/rework)     │
│     - Maintenance scheduling heuristics                              │
│     - Subcontracting make-vs-buy thresholds                         │
│     - Order tracking lateness prediction                            │
│     - Forecast baseline shape (MA, ES, LGBM output adapter)         │
│     - Forecast adjustment dampening and overreaction guards         │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer B: Site tGNN — the per-tenant per-site adaptation             │
│                                                                      │
│   GATv2 + GRU, one per site (manufacturer | DC | retailer),         │
│   nodes are the TRMs active at this site, edges encode intra-site   │
│   structural coupling learned from historical coordination data.    │
│                                                                      │
│   Trained per tenant per site from ~2k–20k historical samples.     │
│   Small (~10–50k params each). Fast (2–5 min per site).             │
│                                                                      │
│   Reads the frozen TRMs' urgency vectors as node features and      │
│   outputs modulated urgencies back. This is where all per-tenant   │
│   structural variation is captured:                                  │
│     - Product-product coupling (BOM, substitution, cannibalization) │
│     - Resource-resource coupling (shared workcenters, labor pools)  │
│     - Customer clusters (delivery windows, route density)          │
│     - Storage neighborhoods (shelf adjacency, cold-chain)           │
│     - Calendar idiosyncrasies (shift patterns, peak shutdowns)      │
│                                                                      │
│   Crucially: this layer is THE reason generic TRMs work. Without   │
│   it, per-tenant TRMs would be load-bearing. With it, the TRMs     │
│   can be generic and the tGNN absorbs the tenant-specific slack.   │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer C: Inference-time context (no weights, no training)           │
│                                                                      │
│   Read at each inference call:                                       │
│     - Tenant's active SC config                                      │
│     - Product hierarchy and substitution matrix                     │
│     - Policy envelope and guardrails                                │
│     - Current inventory state                                        │
│     - Open orders and forecast P10/P50/P90                          │
│     - ERP baseline plan (for conformal comparison)                  │
│                                                                      │
│   Equivalent to an LLM system prompt — tenant-specific knowledge   │
│   injected at inference, not trained into weights.                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Per-ERP Teacher Coverage

### The concern

"Per-ERP TRM checkpoints" sounds superficially reasonable because
SAP MRP, Oracle ASCP, D365 MRP, Odoo Replenishment, and generic
textbook MRP do not produce identical plans from the same inputs. The
TRM needs to understand those variations to produce BC residuals that
match each ERP's actual behaviour.

### Why per-ERP checkpoints are the wrong answer anyway

1. **Hybrid tenants exist.** Enterprises run SAP at HQ, Odoo at regional
   subsidiaries, legacy AS/400 at older sites. Per-ERP checkpoints
   force routing decisions by ERP source and create seams at every
   hybrid boundary. A universal checkpoint handles mixed networks
   naturally.

2. **ERP upgrades and version drift.** SAP ECC ≠ SAP S/4HANA ≠ SAP IBP.
   Microsoft AX ≠ D365 F&O. Per-ERP becomes per-(ERP, version, patch
   level, activation set). The checkpoint explosion is untenable.

3. **Data volume is lopsided.** SAP coverage might have 1000× the
   training signal of a long-tail ERP. Per-ERP checkpoints mean the
   long-tail ERPs get undertrained models. Pooling into one checkpoint
   lets long-tail ERPs benefit from shared knowledge.

4. **The ERP baseline is the teacher, not the student.** The TRMs' job
   is to *beat* the ERP's classical rules, not replicate them. Sharding
   by ERP reinforces "think like SAP" for SAP tenants, which defeats
   the intelligence layer.

5. **Migration is painful.** A tenant moving from Odoo to SAP has to
   re-provision from scratch if checkpoints are per-ERP. With universal
   checkpoints, the Site tGNN re-adapts to the new ERP baseline but
   the TRMs don't change.

### The correct refinement: per-ERP teacher coverage in the pre-training corpus

Instead of forking checkpoints, **fork the teacher signal during
pre-training**. The pre-training corpus is composed of synthetic
supply chains. Each synthetic sample is labeled by multiple teachers
— textbook MRPEngine, SAP-flavor MRPEngine, Odoo-flavor MRPEngine,
D365-flavor MRPEngine — and the TRM learns the *family* of policies
rather than any single one.

```
Pre-training corpus composition:
  60%  Textbook engine teachers
         - MRPEngine (lot-for-lot, POQ, fixed lot, Wagner-Whitin)
         - AATPEngine (textbook priority tiering)
         - BufferCalculator (z * sigma * sqrt(LT))
         - All the rule-book primitives with parameter sweeps

  25%  Per-ERP teacher variants
         - SAP-flavor: SAP's MRP types (PD, VB, VM, ND), SAP's lot
           sizing keys (EX, FX, ZZ, DY, PP, WB), SAP-style safety
           stock (SB/SM/MB), SAP-style ATP rules
         - D365-flavor: D365's MRP planner behaviors, D365 coverage
           groups, D365 item coverage exceptions
         - Oracle-flavor: Oracle ASCP distinct behaviours where
           they matter
         - Odoo-flavor: Odoo replenishment rules (min/max, make-to-
           order), Odoo procurement groups
         - NetSuite-flavor, Infor-flavor if demand warrants

  15%  Adversarial / edge cases
         - Constrained capacity forcing suboptimal rule-following
         - Expedited demand with partial allocation
         - Supplier reliability degradation mid-horizon
         - Stockout recovery trajectories
         - Mixed discrete + process manufacturing
```

Each sample carries an **`erp_variant` feature** as part of the input,
so the TRM can learn to condition its output on which ERP flavor
produced the teacher label. At inference time, the tenant's active
ERP is read from Layer C context and passed as this feature. A tenant
running SAP sees SAP-flavor predictions from the same universal
checkpoint that a tenant running Odoo sees Odoo-flavor predictions
from.

This is equivalent to how a multilingual LLM handles language — one
set of weights, language tag as input feature, appropriate output
style per input. It is **not** equivalent to training separate
per-language models.

### When to fork into LoRA adapters (not now, maybe later)

The fallback position, if per-ERP residuals turn out to be large and
stable after deployment:

- Keep the universal base checkpoint.
- Train **LoRA adapters per (ERP variant, TRM type)** — small delta
  weight matrices on top of the frozen base.
- Size: ~1–5 MB per adapter, vs ~40 MB per full TRM checkpoint.
- Selected at inference time by reading `erp_variant` from context.

This is a 10× cheaper fork than full per-ERP checkpoints and preserves
transfer between ERPs. We do **not** build this on day one. We build
it only if post-deployment telemetry shows per-ERP residual patterns
the base model cannot close.

---

## 5. Pre-Training Corpus Design

### Goals

1. **Cover the rule space.** Every combination of lot-sizing rule,
   inventory policy family, ATP tier logic, quality disposition rule,
   and maintenance heuristic the TRMs need to understand.
2. **Cover the structural space.** Networks with 1, 2, 3, 4, 5 tiers.
   Single vs multi-product. Single vs multi-source. Discrete vs process
   manufacturing. Cross-dock vs put-away vs flow-through. High vs low
   demand CV. Intermittent vs smooth demand. Perishable vs not.
3. **Cover the ERP variant space.** Textbook + 4–6 real ERP flavors as
   teachers, each labeled.
4. **Be reproducible.** Seeded generation so the corpus can be rebuilt
   byte-for-byte from a spec file.
5. **Be scalable.** Target 1M samples per TRM type = 12M total. Each
   sample ~2 KB = ~25 GB raw corpus. Compressed checkpoint ~50 MB per
   TRM = ~600 MB total shipped with Autonomy.

### Corpus generation pipeline

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Network Generator                                         │
│    Procedurally generates N=10,000 synthetic SC networks     │
│    spanning the structural space. Each network has a DAG,    │
│    site types, product assortment, BOM depth, lane graph,    │
│    capacity profile, calendar.                               │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Demand Scenario Generator                                 │
│    For each network, generates K=100 demand scenarios:       │
│    baseline + stochastic realizations + shock events.        │
│    Seasonal patterns, trends, promotions, stockout shocks.   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Multi-Teacher Planner                                     │
│    For each (network, scenario, week, (product, site)):      │
│      - Textbook engines compute the rule-following action    │
│      - SAP-flavor engine computes SAP's action               │
│      - D365-flavor engine computes D365's action             │
│      - Odoo-flavor engine computes Odoo's action             │
│      - Oracle-flavor engine (where modeled)                  │
│    Every teacher output is a labeled sample.                 │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Outcome Labeling                                          │
│    Roll forward N periods under each teacher's policy.       │
│    Compute realized stockout, holding cost, fill rate,       │
│    on-time delivery, yield cost, downtime. Attach to sample. │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Stratified Sampling + Balancing                          │
│    Cap per-cell sample count so no archetype dominates.      │
│    Ensure all 12 TRM types have ~1M samples each.            │
│    Ensure ERP variant balance within target ratios.          │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. Train / Val / Test Split                                  │
│    Split BY NETWORK, not by sample, to prevent leakage.      │
│    80/10/10 split. Test set held out for generalization      │
│    measurement.                                              │
└──────────────────────────────────────────────────────────────┘
```

### Corpus storage and versioning

- Stored as **Parquet shards** in object storage (S3-compatible)
- Versioned by spec hash: `corpus_v1_<spec_hash>.parquet`
- Each version is immutable once published
- Autonomy's pre-training pipeline pulls a specific corpus version
- Model checkpoints are tagged with the corpus version they were
  trained on for full reproducibility

### ERP variant encoding

Every teacher engine (`SapMrpEngine`, `D365MrpEngine`, `OdooMrpEngine`,
etc.) lives in `backend/app/services/powell/engines/variants/` as a
pure function that takes state and returns a planning action. These
are **not** used at runtime in production — they exist only to
generate training labels. They encode the documented behavior of each
ERP's planning primitives, validated against ERP output captures where
we have them (Food Dist, SAP Demo, future tenants).

---

## 6. Site tGNN as the Per-Tenant Adaptation Layer

### What it already does

The Site tGNN (GATv2 + GRU, `backend/app/services/powell/site_tgnn_trainer.py`)
is already implemented and runs per-site during provisioning. Its
current role:

- Nodes: the TRMs active at this site (11 for manufacturer, 7 for DC,
  6 for retailer)
- Edges: attention-learned from historical co-occurrence
- Input: each TRM's current state + urgency vector
- Output: modulated urgency vector routed back to the TRMs
- Training: behavioral cloning from historical decisions, supplemented
  by the unified training corpus

### What changes under generic TRMs

- **Input surface stays identical.** The frozen TRMs produce the same
  urgency vectors the Site tGNN expects. No code changes on the tGNN
  input side.
- **Training signal changes slightly.** Today the Site tGNN sometimes
  has to compensate for TRM weakness (TRM A overreacts, tGNN learns
  to dampen A). With generic TRMs that are uniformly capable, the
  tGNN can focus on actual coordination, not compensation. This
  should make the tGNN *easier* to train, not harder.
- **Sample requirements stay similar.** ~2k–20k per site is already
  what the Site tGNN needs. The pre-training shift doesn't reduce
  this because it's for a different layer.
- **What gets removed.** The Site tGNN no longer needs to work around
  under-trained TRMs on small tenants. The "day one coordination is
  bad because the TRMs haven't seen enough samples" problem goes away
  because the TRMs are fully trained on day one.

### Why this is the right place to put per-tenant learning

**Coordination is structural, not rule-based.** Whether MRP says "order
100 units for A" and simultaneously "reduce order for B by 20 units"
depends on whether A and B share a workcenter, a supplier capacity
pool, a transportation bucket. That is intra-site topology, which
is exactly what the graph attention layer learns from historical
co-occurrence. It is the natural home for this signal.

**The rulebook is not structural.** "Order when inventory drops below
reorder point" does not depend on whether any other product is
competing for the same resource. The TRM decides the local action;
the tGNN resolves the global coordination. Clean separation of
concerns.

---

## 7. Provisioning Pipeline After Adoption

### Current (~18 steps, ~45–90 min)

```
warm_start → training_corpus → sop_graphsage → cfa_optimization →
lgbm_forecast → demand_features → supply_tgnn → inventory_tgnn →
capacity_tgnn → trm_training → rl_training → backtest_evaluation →
supply_plan → rccp_validation → decision_seed → site_tgnn →
conformal → scenario_bootstrap → briefing
```

> **Note:** `demand_features` (formerly `demand_tgnn`) computes demand
> feature aggregates for the supply-side tGNNs. It does NOT train a
> demand tGNN — demand forecasting is handled by the Forecast Baseline
> TRM (LightGBM, in `lgbm_forecast` step) and Forecast Adjustment TRM.

### After (~14 steps, ~10–20 min)

```
warm_start → training_corpus → sop_graphsage → cfa_optimization →
lgbm_forecast → demand_features → supply_tgnn → inventory_tgnn →
capacity_tgnn → trm_load_pretrained (NEW, replaces trm_training +
rl_training) → backtest_evaluation → supply_plan → rccp_validation →
decision_seed → site_tgnn → conformal → scenario_bootstrap → briefing
```

**What `trm_load_pretrained` does:**

1. Loads the shipped TRM weight files from
   `/app/models/pretrained/trm_base_v<N>/<trm_type>.pt`
2. Registers them in the TRM registry against the tenant's config_id
   (by reference, not copy — multiple tenants share the same file)
3. Records the pre-training corpus version and model version in
   `config_provisioning_status.extra_data` for audit
4. Runs a 100-sample smoke test on held-out Food Dist decisions to
   verify the checkpoint loads and produces sensible outputs
5. Completes in under 30 seconds

**What disappears:**

- `trm_training` step (~15 min saved)
- `rl_training` step (~15 min saved)
- The two-phase BC → PPO pipeline per TRM type per tenant
- The need to extract 60k–200k per-TRM BC labels from tenant history
  (only 5k–20k are needed for Site tGNN + conformal)
- The RL reward curves that currently sometimes fail to converge for
  small tenants

**What stays:**

- Historical corpus extraction (reduced volume, same code path)
- Site tGNN training (unchanged)
- Tactical tGNNs (L3) — still per-tenant
- S&OP GraphSAGE (L4) — still per-tenant
- Conformal calibration (runs against frozen TRMs now, slightly
  different but simpler)
- Backtest evaluation (critical — this is how we catch cases where
  the generic TRMs are a bad fit for a particular tenant)

---

## 8. Checkpoint Hierarchy

### Before (today)

```
Per tenant:
  /app/checkpoints/tenant_{t}/config_{c}/
    trm_po_creation.pt               (~40 MB)
    trm_atp_allocation.pt            (~40 MB)
    trm_inventory_buffer.pt          (~40 MB)
    trm_mo_execution.pt              (~40 MB)
    trm_to_execution.pt              (~40 MB)
    trm_quality_disposition.pt       (~40 MB)
    trm_maintenance_scheduling.pt    (~40 MB)
    trm_subcontracting.pt            (~40 MB)
    trm_order_tracking.pt            (~40 MB)
    trm_rebalancing.pt               (~40 MB)
    trm_forecast_baseline.pt         (~40 MB)
    trm_forecast_adjustment.pt       (~40 MB)
    site_tgnn_<site_id>.pt           (~0.5 MB each × N sites)
    tactical_demand_tgnn.pt          (~10 MB)
    tactical_supply_tgnn.pt          (~10 MB)
    tactical_inventory_tgnn.pt       (~10 MB)
    tactical_capacity_tgnn.pt        (~10 MB)
    sop_graphsage.pt                 (~20 MB)

Total per tenant: ~580 MB + N × 0.5 MB
Total across 10 tenants: ~5.8 GB + site tGNNs
```

### After

```
Global (shipped with Autonomy image):
  /app/models/pretrained/trm_base_v{N}/
    metadata.json                    (corpus version, training config,
                                      validation scores per TRM type)
    trm_po_creation.pt               (~40 MB)
    trm_atp_allocation.pt            (~40 MB)
    ... 10 more TRM types
                                     Total: ~480 MB, same for all
                                     tenants

Per tenant:
  /app/checkpoints/tenant_{t}/config_{c}/
    site_tgnn_<site_id>.pt           (~0.5 MB each × N sites)
    tactical_demand_tgnn.pt          (~10 MB)
    tactical_supply_tgnn.pt          (~10 MB)
    tactical_inventory_tgnn.pt       (~10 MB)
    tactical_capacity_tgnn.pt        (~10 MB)
    sop_graphsage.pt                 (~20 MB)
    conformal_residuals.pkl          (~1 MB per TRM × 12 = ~12 MB)

Total per tenant: ~72 MB + N × 0.5 MB (88% reduction)
Total across 10 tenants: ~720 MB + ~480 MB global = ~1.2 GB
                         (79% reduction vs current 5.8 GB)
```

### Storage routing at inference

TRM inference looks up weights in this order:

1. Tenant-specific override at
   `/app/checkpoints/tenant_{t}/config_{c}/trm_<type>.pt` (only
   exists if the tenant opts into the fallback — see §10)
2. Global pre-trained at
   `/app/models/pretrained/trm_base_v{N}/trm_<type>.pt`

Default is (2). A tenant only falls back to (1) if they explicitly
opt in after backtest shows the generic model is a poor fit. This is
expected to be rare.

---

## 9. Validation and Success Metrics

### Pre-deployment (during Layer A training)

- **Rule-coverage validation**: Pre-trained TRM is evaluated on a
  held-out test set of synthetic supply chains. For each TRM type,
  measure the fraction of samples where the TRM's output agrees with
  the teacher engine's action within tolerance. Target: ≥ 95% agreement
  with the primary textbook teacher across all ERP variants.
- **ERP-variant fidelity**: For each ERP variant in the corpus,
  measure the TRM's agreement with that variant's teacher when the
  `erp_variant` feature is set correctly. Target: ≥ 90% agreement per
  variant.
- **Cross-variant transfer**: Evaluate the TRM on ERP variants it
  wasn't heavily trained on (via validation networks). Target:
  degradation ≤ 10% from in-variant performance.
- **Generalization gap**: train vs test performance gap on synthetic
  data. Target: ≤ 5%. Large gap indicates overfitting to the corpus.

### Deployment validation (per tenant, during first provisioning)

- **Backtest against ERP baseline**: run the pre-trained TRMs on the
  tenant's held-out historical period, compare cumulative cost
  (stockout + holding + ordering) vs the tenant's actual ERP baseline
  on the same period. Target: ≥ parity with ERP, typically 5–20%
  better.
- **Backtest against per-tenant trained baseline** (first 3–5 tenants
  only): train the old per-tenant curriculum TRMs in parallel as a
  validation check. Compare backtest cost. Target: generic TRMs are
  within 5% of per-tenant TRMs; acceptable if generic is slightly
  worse because Site tGNN closes the gap.
- **Site tGNN convergence**: measure how quickly the Site tGNN
  converges on top of the frozen TRMs. Target: converges in ≤ 50%
  of the training time previously needed when sitting on top of
  per-tenant-trained TRMs.
- **Conformal coverage**: measure the empirical coverage of the
  conformal intervals on held-out data. Target: within 2% of nominal
  (e.g., a 90% interval actually contains 88–92% of outcomes).

### Long-term metrics (first 30 days after tenant goes live)

- **Live decision quality**: measure the realized cost of decisions
  the generic TRMs produce vs what the ERP would have produced. Target:
  ≥ 5% improvement over ERP baseline on dollar-weighted average.
- **Per-ERP residual patterns**: if systematic per-ERP residuals
  emerge that the base model cannot close, this triggers the LoRA
  adapter fallback plan (§10).
- **Drift**: measure conformal interval coverage drift over time.
  Target: retrigger conformal calibration (hourly cron already exists)
  but do not retrigger TRM retraining.

### Failure mode detection

- **Generic-TRM backtest catastrophically worse than ERP**: the
  pre-trained TRMs produce a plan that is measurably worse than the
  ERP baseline on the tenant's history. Action: block go-live, fall
  back to per-tenant curriculum for that tenant (opt-out flag),
  investigate which corpus gap caused the failure, schedule corpus
  fix for the next pre-training cycle.
- **Per-ERP systematic bias**: one ERP variant consistently
  underperforms across multiple tenants. Action: examine the variant
  teacher, add more corpus coverage, ship an updated base model.
- **Site tGNN fails to converge**: on top of frozen TRMs, the Site
  tGNN cannot reach its target coordination score. Action: investigate
  whether the frozen TRMs are outputting urgency vectors in a range
  the tGNN expects (normalization mismatch is the usual culprit).

---

## 10. Open Questions and Fallback Positions

### Q1. Joint-encoder vs separate per-TRM models

**Option A — Joint**: one shared encoder, 12 output heads. Knowledge
shared between related TRMs (PO ↔ Buffer ↔ MO have obvious overlap).
Smaller total parameter count. Harder to update one TRM without
affecting others.

**Option B — Separate**: 12 fully independent models. No shared
parameters. Easier to update individually. Larger total footprint
(~2× params).

**Recommendation**: Start with **Option B (separate)** because it's
simpler to reason about and simpler to debug. If joint-encoder
becomes attractive later, migrate TRM-by-TRM.

### Q2. How often to retrain the base model

The base model is re-pretrained when:
1. The corpus is meaningfully expanded (new ERP variants, new
   structural archetypes, adversarial edge cases added)
2. Validation metrics reveal a systemic gap in the current base
3. New TRM types are added to the system (e.g., a 13th TRM for
   promotion planning)

**Target cadence**: quarterly, or when gaps are detected, whichever
comes first. Out-of-band emergency retrains are possible but should
be rare.

### Q3. Version compatibility during upgrades

**Problem**: if tenant A is on `trm_base_v1` and we ship `trm_base_v2`,
the Site tGNNs trained on v1's urgency distributions may not transfer
cleanly to v2.

**Solution**: Ship the base model as a versioned artifact. The tenant's
provisioning record stores which base version it is using. During
Autonomy upgrades:
- Default behavior: tenants stay on their pinned base version.
- Opt-in upgrade: tenant admin triggers a provisioning refresh that
  loads the new base and retrains the Site tGNN (fast, ~5 min per
  site). Backtest verifies the upgrade doesn't regress.
- Automatic upgrade: never, without tenant admin approval.

### Q4. What if a tenant has a weird ERP we don't pre-train against

**Example**: a custom home-grown ERP, an obscure regional system, an
older version of Infor nobody has modeled.

**Solution**: the tenant is mapped to the closest pre-trained ERP
variant by feature similarity (the variant with the most similar
default MRP lot-sizing rules, ATP logic, safety-stock formula). The
generic rulebook coverage (60% of the corpus) should be sufficient
for most cases. The Site tGNN absorbs the remainder.

**Fallback**: if the tenant's backtest is catastrophically worse, they
fall back to per-tenant curriculum training (the old path is
preserved as a safety net for ~6 months post-rollout, then
deprecated).

### Q5. The LoRA-adapter fallback

If post-deployment telemetry shows that one or more ERP variants have
large stable per-ERP residuals the base model can't close, the
mitigation is **LoRA adapters**, not full per-ERP checkpoints:

- Base model frozen.
- Train a small low-rank delta per (ERP variant, TRM type) against
  residual samples.
- Size: ~1–5 MB per adapter.
- Inference: base forward pass + adapter delta = final output.
- Selected by `erp_variant` feature.

**When to build**: only if telemetry demands it. Do not build
speculatively.

### Q6. Compliance and contractual isolation

Some enterprise customers may contractually require that their AI
model "has only been trained on their data" — a legal rather than
technical constraint.

**Solution**: offer a compliance mode that falls back to per-tenant
curriculum training for that specific tenant, priced accordingly. The
default for new tenants is generic pre-training; compliance mode is
an explicit opt-in requiring a contract amendment.

---

## 11. Deployment Plan — Phased Rollout

> This plan assumes the current architecture documented elsewhere
> (`UNIFIED_TRAINING_CORPUS.md`, `TACTICAL_AGENT_ARCHITECTURE.md`) as
> the baseline. Each phase has explicit entry criteria, exit
> criteria, and rollback path.

### Phase 0 — Prerequisites and Go/No-Go (~1 week)

**Goal**: confirm the architectural assumptions hold before committing
development effort.

**Deliverables**:
- Proof-of-concept: train a single TRM (forecast_baseline) on a
  100k-sample synthetic corpus against textbook + SAP + Odoo
  teachers. Measure accuracy on Food Dist held-out decisions.
- Compare against the current Food Dist per-tenant forecast_baseline
  TRM on the same held-out data.
- Measure Site tGNN convergence on top of the generic TRM vs
  convergence on top of the per-tenant TRM.

**Entry criteria**:
- Food Dist is provisioned and stable on the current architecture.
- Current forecast_baseline TRM checkpoint is captured for comparison.

**Exit criteria**:
- Generic TRM backtest is within 10% of per-tenant TRM backtest.
- Site tGNN convergence is not degraded by more than 20%.
- Pre-training takes ≤ 8 hours on a single A100 GPU for one TRM.

**Go decision**: if all exit criteria met, proceed to Phase 1. If any
fail, revisit architecture (likely: more corpus coverage, longer
pre-training, or reconsider joint-encoder option).

**Rollback**: delete the PoC; nothing in production changes.

---

### Phase 1 — Corpus and Engine Infrastructure (~2–3 weeks)

**Goal**: build the machinery to generate the pre-training corpus at
scale with per-ERP teacher coverage.

**Deliverables**:

1. **Synthetic Network Generator** (`backend/scripts/pretraining/network_generator.py`)
   - Procedurally generates 10,000 synthetic SC networks
   - Parameter sweep over tiers, topology, BOM depth, lane graph,
     capacity, calendar
   - Deterministic seeding for reproducibility
   - Output: Parquet dataset of network specs

2. **Demand Scenario Generator** (`backend/scripts/pretraining/demand_scenarios.py`)
   - Per network, generates 100 demand scenarios
   - Seasonal, trend, intermittent, shock patterns
   - Output: Parquet dataset of (network_id, scenario_id, demand_series)

3. **ERP Variant Teacher Engines**
   - `backend/app/services/powell/engines/variants/textbook_mrp.py`
     (wraps existing MRPEngine)
   - `backend/app/services/powell/engines/variants/sap_flavor.py`
   - `backend/app/services/powell/engines/variants/d365_flavor.py`
   - `backend/app/services/powell/engines/variants/odoo_flavor.py`
   - `backend/app/services/powell/engines/variants/oracle_flavor.py`
     (if capacity permits in phase 1, else phase 2)
   - Each is a pure function: `(state, policy_params) → action`
   - Unit tested against published ERP documentation behaviours
     where possible

4. **Multi-Teacher Planner** (`backend/scripts/pretraining/label_samples.py`)
   - Iterates every (network, scenario, week, (product, site))
   - Calls every variant teacher
   - Emits one labeled sample per (state, teacher_variant, action)
     triple
   - Parallel execution across multiple processes
   - Output: Parquet sharded dataset

5. **Outcome Labeling** (`backend/scripts/pretraining/outcome_labeling.py`)
   - Rolls forward N periods under each teacher's policy
   - Computes realized stockout, holding, fill rate, on-time,
     yield, downtime
   - Attaches to sample as the reward signal

6. **Corpus Publisher** (`backend/scripts/pretraining/publish_corpus.py`)
   - Stratified sampling and per-TRM balancing
   - Train/val/test split by network (prevents leakage)
   - Writes `corpus_v{N}_{hash}.parquet` to object storage
   - Records spec + hash + sample counts in a corpus manifest

**Entry criteria**:
- Phase 0 go decision given.
- A storage bucket (or equivalent) exists for corpus shards.

**Exit criteria**:
- Corpus v1 published with ≥ 500k samples per TRM type across all
  ERP variants.
- Corpus validation script passes: no duplicate samples, correct
  variant balance, correct TRM-type balance, no leakage between
  train/val/test splits.
- A smoke test pre-trains forecast_baseline on corpus v1 and matches
  the Phase 0 PoC quality.

**Rollback**: delete the corpus; nothing in production changes. The
per-ERP variant engines are useful on their own (for backtest
baselines) even if the pre-training initiative is paused.

**Risks**:
- ERP variant accuracy: without access to real SAP/D365/Odoo
  instances to validate against, the variant engines may be wrong.
  **Mitigation**: validate against Food Dist (SAP-flavor ERP data
  we already have) and the SAP Demo tenant (once provisioned).
- Corpus size: 25 GB raw is manageable but may require object
  storage rather than repo storage. **Mitigation**: shard and use
  Git LFS or S3-compatible bucket.

---

### Phase 2 — Pre-Training Pipeline and First Base Model (~2–3 weeks)

**Goal**: train `trm_base_v1`, the first universal TRM checkpoint set.

**Deliverables**:

1. **TRM Pre-Training Script** (`backend/scripts/pretraining/train_trm_base.py`)
   - Loads corpus v1 from object storage
   - Trains one TRM at a time (Option B, separate models)
   - Supports multi-GPU via PyTorch DDP
   - Logs to TensorBoard / Weights & Biases
   - Saves checkpoint + metadata

2. **Validation Harness** (`backend/scripts/pretraining/validate_trm_base.py`)
   - Rule-coverage validation on synthetic test set
   - ERP-variant fidelity per variant
   - Cross-variant transfer
   - Generalization gap

3. **Metadata Bundle** (`/app/models/pretrained/trm_base_v1/metadata.json`)
   - Corpus version hash
   - Training config
   - Validation scores per TRM type
   - Validation scores per ERP variant
   - Training date, model hash

4. **Checkpoint Packaging**
   - 12 TRM weight files + metadata bundled into
     `/app/models/pretrained/trm_base_v1/`
   - Included in the backend Docker image build context
   - ~500 MB impact on image size (acceptable)

5. **Loader Service** (`backend/app/services/powell/pretrained_trm_loader.py`)
   - `load_pretrained_trm(trm_type, version="latest") → TRMModel`
   - Caches loaded weights in memory (shared across tenants)
   - Resolves version from config_provisioning_status or tenant
     override

**Entry criteria**:
- Phase 1 corpus published.
- GPU budget secured: ~40 A100-hours for one pass over 12 TRM types.

**Exit criteria**:
- All 12 TRM types pre-trained and saved.
- Validation scores meet targets (§9).
- Smoke test on Food Dist: load pretrained, run inference on 100
  real Food Dist decisions, outputs match the ERP baseline within
  tolerance.

**Rollback**: checkpoints are tagged as `v1-candidate`. Production is
unchanged. A failed base model is simply not promoted to `v1`.

**Risks**:
- Pre-training cost exceeds budget: **Mitigation**: start with 8
  TRM types (excluding the least critical — subcontracting, quality,
  maintenance), expand in Phase 3.
- Base model underperforms on specific TRM types: **Mitigation**:
  iterate on corpus composition per TRM type, potentially more
  samples for struggling TRMs.

---

### Phase 3 — Provisioning Integration (~1–2 weeks)

**Goal**: wire the pre-trained base model into the provisioning
pipeline as a parallel path alongside the current per-tenant
curriculum.

**Deliverables**:

1. **New Provisioning Step** `trm_load_pretrained`
   - Added to `ConfigProvisioningStatus.STEPS`
   - Runs between `capacity_tgnn` and `backtest_evaluation`
   - Replaces `trm_training` + `rl_training` in the DAG
   - Feature flagged by `tenant.training_mode` column:
     - `'generic'`: load pretrained, skip trm_training/rl_training
     - `'curriculum'`: legacy path, retained for fallback
     - `'hybrid'`: load pretrained as warm start, fine-tune on
       tenant data for a small number of epochs (experimental,
       for Phase 5)

2. **Tenant Training Mode Flag**
   - New column `tenants.training_mode` default `'curriculum'`
   - Migration: existing tenants stay on `'curriculum'`
   - New tenants default to `'generic'` after Phase 4 validation

3. **Site tGNN Integration**
   - Verify Site tGNN loads frozen TRMs correctly
   - Verify urgency vector ranges match the tGNN's expectations
   - Add a normalization adapter if the generic TRMs output ranges
     differ from the curriculum-trained TRMs

4. **Backtest Gate**
   - Extend `backtest_evaluation` step to compare generic-TRM
     backtest against:
     - The tenant's historical ERP baseline
     - (Optional) a parallel curriculum-trained TRM set for the
       first 3–5 generic-mode tenants
   - If backtest is catastrophically worse, mark the provisioning
     status as `requires_review` and do not promote to live

5. **Rollback Path**
   - `tenant.training_mode` can be flipped from `'generic'` to
     `'curriculum'` by a tenant admin
   - On flip, the tenant's next provisioning runs the legacy path
     and writes tenant-specific TRM checkpoints that override the
     global ones

**Entry criteria**:
- Phase 2 `trm_base_v1` passes validation.
- Food Dist is available as the first test tenant.

**Exit criteria**:
- Food Dist can be re-provisioned in `'generic'` mode and all 18+
  provisioning steps complete.
- Food Dist backtest in `'generic'` mode is within 10% of the
  current curriculum-mode backtest.
- Site tGNN converges on top of generic TRMs.
- Decision Stream populates with real decisions at the expected
  rate.

**Rollback**:
- Per tenant: flip `training_mode = 'curriculum'`, re-provision.
- Global: disable the `trm_load_pretrained` step via config flag,
  everyone reverts to curriculum.

**Risks**:
- Urgency vector range mismatch between generic and curriculum TRMs
  breaks the Site tGNN: **Mitigation**: the normalization adapter
  from deliverable 3 handles this; comprehensive unit tests needed.
- `trm_load_pretrained` fails silently: **Mitigation**: step
  verifies checkpoint load with a smoke inference; fails loudly if
  output shapes are wrong.

---

### Phase 4 — Pilot Tenant Rollout (~2 weeks)

**Goal**: validate generic pre-training against 2–3 real tenants end
to end.

**Deliverables**:

1. **Food Dist Pilot**
   - Re-provision in `'generic'` mode
   - Side-by-side backtest against curriculum mode
   - 1-week observation window in a staging environment
   - Decision Stream quality review (qualitative + metrics)

2. **SAP Demo Pilot**
   - Provision fresh (no prior curriculum run)
   - Verify SAP-flavor ERP teacher transfers correctly
   - Compare backtest against SAP's historical MRP baseline

3. **A Third Tenant** (TBD, pick a tenant using a different ERP
   variant — ideally Odoo or D365 once available)
   - Fresh provisioning in generic mode
   - Cross-variant generalization validation

4. **Telemetry Dashboard**
   - Track decision quality, backtest scores, Site tGNN convergence
     time, conformal coverage per tenant
   - Aggregate per-ERP-variant residual patterns to detect systematic
     issues

**Entry criteria**: Phase 3 integration complete and Food Dist
generic-mode provisioning succeeds.

**Exit criteria**:
- All pilot tenants reach go-live quality in generic mode
- No regression vs curriculum mode in backtest scores
- No per-ERP-variant systematic bias in residuals
- 7-day stable operation in staging

**Rollback**: each tenant can flip back to curriculum independently.
Global rollback still available via the feature flag.

---

### Phase 5 — General Availability (~1 week)

**Goal**: flip the default for new tenants to `'generic'` and begin
deprecating the per-tenant curriculum path.

**Deliverables**:

1. Default `tenants.training_mode = 'generic'` for newly provisioned
   tenants
2. Documentation updated:
   - `UNIFIED_TRAINING_CORPUS.md`: add a section explaining the
     two-stream corpus is now primarily for Site tGNN + conformal,
     not primary TRM BC
   - `CLAUDE_REFERENCE.md`: update the training architecture section
   - `README.md`: brief mention of pre-training + link to this doc
3. Runbook for operators:
   - How to check which base version a tenant is using
   - How to trigger a base model upgrade
   - How to fall back to curriculum mode for a specific tenant
   - How to interpret backtest deltas vs base model
4. Retire the curriculum path from provisioning default. Keep it
   available as an explicit opt-in for ~6 months; delete thereafter.

**Entry criteria**: Phase 4 pilots all passed.

**Exit criteria**:
- New-tenant default is `'generic'`
- All pilot tenants remain stable
- Operator runbook published
- No open P0/P1 issues tied to generic mode

**Rollback**: flip the default back to `'curriculum'`. Existing
generic-mode tenants continue to work as-is.

---

### Phase 6 — Continuous Improvement (ongoing)

**Goal**: maintain and improve the base model over time without
disrupting tenants.

**Ongoing activities**:

- **Quarterly base model refresh**: collect new per-ERP teacher
  signal from newly provisioned tenants, re-publish the corpus,
  train `trm_base_v2`, validate, ship as an opt-in upgrade.
- **Residual monitoring**: aggregate per-ERP residuals across
  tenants. If systematic patterns emerge, plan a LoRA adapter pass
  (§10 Q5).
- **New TRM types**: when a 13th TRM is added, it goes straight into
  the next base model (no per-tenant curriculum).
- **New ERP variants**: when we add a new ERP integration, build its
  teacher engine, add it to the corpus, include in the next base
  model refresh.

**No exit criteria** — this phase runs indefinitely.

---

## Appendix A — Comparison Table

| Aspect | Curriculum (today) | Generic Pre-Training (proposed) |
|---|---|---|
| Universal rules learned | Re-derived per tenant | Learned once, frozen, shipped |
| Per-tenant structural learning | Mixed into TRMs + tGNN | Clean separation: Site tGNN only |
| Training data per tenant | 60–200k samples | 5–20k samples (Site tGNN + conformal only) |
| Training time per tenant | 45–90 min | 10–20 min |
| Per-tenant TRM checkpoints | 12 × N | 0 |
| Global TRM checkpoints | 0 | 12 (versioned) |
| Total checkpoint storage (10 tenants) | ~5.8 GB | ~1.2 GB |
| New-tenant onboarding GPU cost | ~1 GPU-hour | ~0.2 GPU-hour |
| Handles hybrid ERP tenants | Poorly (per-tenant TRMs overfit dominant ERP) | Naturally (single model with ERP feature) |
| Handles ERP migration | Requires full re-provisioning | Only Site tGNN re-adapts |
| Long-tail ERP coverage | Weak (insufficient samples) | Strong (benefits from pooled knowledge) |
| Cold start for new tenants | Dependent on corpus quality | Bounded below by universal rules |
| Debuggability | Per-tenant drift is invisible | Global model, residual patterns visible |
| Contract compliance ("trained on my data only") | Native | Requires opt-in curriculum fallback |

---

## Appendix B — File and Module Map

New files created during Phases 1–3:

```
backend/scripts/pretraining/
  network_generator.py               # Phase 1
  demand_scenarios.py                # Phase 1
  label_samples.py                   # Phase 1
  outcome_labeling.py                # Phase 1
  publish_corpus.py                  # Phase 1
  train_trm_base.py                  # Phase 2
  validate_trm_base.py               # Phase 2
  README.md                          # Phase 1, operator doc

backend/app/services/powell/engines/variants/
  __init__.py
  textbook_mrp.py                    # Phase 1
  sap_flavor.py                      # Phase 1
  d365_flavor.py                     # Phase 1
  odoo_flavor.py                     # Phase 1
  oracle_flavor.py                   # Phase 1 or 2

backend/app/services/powell/
  pretrained_trm_loader.py           # Phase 2

backend/app/models/pretrained/
  trm_base_v1/
    metadata.json                    # Phase 2
    trm_po_creation.pt               # Phase 2
    trm_atp_allocation.pt            # Phase 2
    ...

backend/migrations/versions/
  <date>_tenant_training_mode.py     # Phase 3
  <date>_config_prov_trm_load.py     # Phase 3

docs/internal/architecture/
  GENERIC_TRM_PRETRAINING.md         # This document
```

Modified during Phases 3–5:

```
backend/app/services/provisioning_service.py
  - Add _step_trm_load_pretrained method
  - Route between curriculum and generic based on tenant.training_mode

backend/app/models/tenant.py
  - Add training_mode column

backend/app/models/user_directive.py
  - Add trm_load_pretrained_* columns to ConfigProvisioningStatus

backend/app/services/powell/site_tgnn_trainer.py
  - Add normalization adapter for generic-TRM urgency vectors

docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md
  - Note the shift: historical corpus primary purpose becomes
    Site tGNN + conformal, not primary TRM BC
```

---

## Appendix C — Timeline Summary

| Phase | Duration | Cumulative |
|---|---|---|
| 0. PoC | 1 week | 1 week |
| 1. Corpus + engines | 2–3 weeks | 3–4 weeks |
| 2. Pre-training pipeline + v1 base | 2–3 weeks | 5–7 weeks |
| 3. Provisioning integration | 1–2 weeks | 6–9 weeks |
| 4. Pilot rollout | 2 weeks | 8–11 weeks |
| 5. General availability | 1 week | 9–12 weeks |
| 6. Continuous improvement | Ongoing | — |

**Total to GA**: 9–12 weeks.

**Critical path**: Phase 0 → 1 → 2, where corpus quality determines
everything downstream. Invest heavily in Phase 1 correctness.

**Biggest unknowns**:
- ERP variant teacher fidelity (Phase 1 risk)
- Pre-training GPU budget (Phase 2 risk)
- Site tGNN normalization compatibility (Phase 3 risk)

All three have well-defined rollback paths that preserve the
curriculum as a safety net until Phase 5.

---

## Appendix D — Success Criteria Summary

Generic TRM pre-training is considered successful when, after Phase 5:

1. **Onboarding time**: a new tenant reaches fully-provisioned state
   in ≤ 20 minutes from the current 45–90 minutes.
2. **Decision quality**: generic-mode tenants achieve backtest scores
   within 5% of curriculum-mode tenants, measured on held-out
   historical data.
3. **Operational stability**: no P0/P1 incidents tied to generic-mode
   decisions over a 30-day window with at least 5 tenants live.
4. **Storage footprint**: TRM checkpoints consume ≤ 1 GB globally
   regardless of tenant count.
5. **Per-ERP fidelity**: each ERP variant represented in the corpus
   achieves ≥ 90% teacher agreement on held-out synthetic data.
6. **Site tGNN convergence**: Site tGNN training time on top of
   generic TRMs is within 50% of training time on top of curriculum
   TRMs.

If all six are met, the architecture is adopted as the default for
all future tenants and the curriculum path enters a 6-month
deprecation window.

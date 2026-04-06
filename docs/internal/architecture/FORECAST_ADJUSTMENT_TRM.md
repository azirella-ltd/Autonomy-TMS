# Forecast Adjustment TRM — Knowledge Base and Behaviour Specification

> **Autonomy Platform — Agent Behaviour Reference**
>
> Complete specification of what the Forecast Adjustment TRM knows, how it
> behaves, what decisions it makes, and when it escalates to LLM.
>
> This document serves as both:
> 1. Architecture reference for developers
> 2. Behavioural specification that the TRM engine and LLM skill must implement

---

## Table of Contents

1. [Role and Scope](#1-role-and-scope)
2. [Position in the Agent Hierarchy](#2-position-in-the-agent-hierarchy)
3. [Decision Domains](#3-decision-domains)
4. [Domain 1: Promotion Effect Estimation](#4-domain-1-promotion-effect-estimation)
5. [Domain 2: NPI — New Product Introduction](#5-domain-2-npi--new-product-introduction)
6. [Domain 3: EOL — End of Life Coordination](#6-domain-3-eol--end-of-life-coordination)
7. [Domain 4: Demand Sensing](#7-domain-4-demand-sensing)
8. [Domain 5: Cannibalization and Substitution](#8-domain-5-cannibalization-and-substitution)
9. [Domain 6: Consensus Forecasting and FVA](#9-domain-6-consensus-forecasting-and-fva)
10. [Domain 7: External Signal Adjustment](#10-domain-7-external-signal-adjustment)
11. [TRM vs LLM Decision Boundary](#11-trm-vs-llm-decision-boundary)
12. [Hive Signal Integration](#12-hive-signal-integration)
13. [FVA (Forecast Value Add) Tracking](#13-fva-tracking)
14. [Guardrails](#14-guardrails)
15. [Output Specification](#15-output-specification)
16. [Decision Table Schema](#16-decision-table-schema)
17. [Implementation Status](#17-implementation-status)

---

## 1. Role and Scope

The Forecast Adjustment TRM is the **Demand Planner** agent. It reviews the
statistical baseline forecast (from the Forecast Baseline TRM) and applies
business intelligence that statistical models cannot capture.

**What it owns:**
- Corrections to the baseline forecast based on business events
- NPI demand curves for new products
- EOL phase-out coordination with successor products
- Promotion uplift and cannibalization estimation
- Short-horizon demand sensing corrections
- Consensus forecast gating (accept/reject human overrides)
- FVA tracking across all adjustment sources

**What it does NOT own:**
- The baseline statistical forecast (owned by Forecast Baseline TRM)
- Inventory targets or safety stock (owned by Inventory Optimization tGNN)
- Supply allocation or sourcing (owned by Supply Planning tGNN)
- Production scheduling (owned by Capacity/RCCP tGNN)

**Analogy:** In a traditional S&OP process, this is the **Demand Planner** who
sits between the Demand Analyst (statistical forecast) and the S&OP consensus
meeting. They know things the model doesn't: upcoming promotions, competitor
actions, customer-specific intelligence, and market trends.

---

## 2. Position in the Agent Hierarchy

```
Layer 4 — S&OP GraphSAGE (weekly policy parameters)
  ↓
Layer 3 — Tactical Planning (daily)
  ├── Forecast Baseline TRM (SENSE phase) → P10/P50/P90
  ├── Forecast Adjustment TRM (ASSESS phase) → adjusted forecast  ← THIS AGENT
  ├── Supply Planning tGNN → allocation, exceptions
  ├── Inventory Optimization tGNN → buffers, D/S balance
  └── Capacity/RCCP tGNN → feasibility, bottlenecks
  ↓
Layer 2 — Site tGNN (hourly, always-on)
Layer 1 — 12 TRM execution agents
```

**Phase:** ASSESS (Phase 2) — runs after the Forecast Baseline TRM (SENSE)
has produced the statistical baseline, so adjustments are always applied on
top of a fresh baseline.

**Cadence:**
- Daily cascade (5am, after baseline)
- CDC-triggered (new order data, POS exceptions)
- Promotion activation events
- NPI launch events
- Weekly S&OP consensus round (Monday 6am)

---

## 3. Decision Domains

The TRM handles 7 distinct decision domains. Each has its own heuristics,
data sources, and confidence characteristics:

| Domain | Trigger | TRM (95%) | LLM (5%) |
|--------|---------|-----------|----------|
| **Promotion** | Promo activation/completion | Learned elasticity from history | Novel promo type, no historical precedent |
| **NPI** | Product enters launch stage | Similar-product transfer (k-nearest) | Cold-start (no similar products found) |
| **EOL** | Product enters decline/eol | Phase-out curve from lifecycle model | Coordinated successor ramp timing |
| **Demand sensing** | CDC from POS/orders | Exception detection (actual vs forecast) | Anomaly with no obvious cause |
| **Cannibalization** | NPI or promo activation | Category demand redistribution | Complex multi-product interaction |
| **Consensus** | Human override submitted | FVA gate (accept/reject by track record) | Override conflicts with strong signals |
| **External signal** | Email, voice, market intel | Source reliability × signal confidence | Unreliable source, conflicting signals |

---

## 4. Domain 1: Promotion Effect Estimation

### Supply Chain Context

Promotions are the single largest source of demand variability in retail and
CPG supply chains. A typical promotion creates:
- **Direct uplift**: 20-200% volume increase on the promoted item
- **Forward buying**: Customers stock up during promo, depressing post-promo demand
- **Cannibalization**: Uplift partly "stolen" from non-promoted items in the category
- **Halo effect**: Category awareness lift benefits non-promoted items
- **Promotion fatigue**: Repeated discounting erodes baseline demand over time

### TRM Behaviour (Deterministic)

**Input:** Promotion activation from `promotion` table with `expected_uplift_pct`,
`expected_cannibalization_pct`, and historical promotion data.

**Learned Elasticity:**
```
For each (product_category, promo_type) pair:
  actual_uplift = mean(actual_uplift_pct) from past promotions
  actual_cannibalization = mean(actual_cannibalization_pct)

  If >= 5 historical promotions exist:
    Use learned actuals (weight 0.7) + expected (weight 0.3)
  Else:
    Use expected values from promotion table (with 30% dampening)
```

**Forward Buy Estimation:**
```
post_promo_demand_factor = 1.0 - (uplift_pct * forward_buy_fraction)
forward_buy_fraction = 0.3 for staples, 0.1 for perishables, 0.5 for durables

Apply to 2-4 weeks post-promotion
```

**Adjustment Application:**
```
During promo:   adjusted = baseline × (1 + learned_uplift_pct)
Post-promo:     adjusted = baseline × post_promo_demand_factor
Sibling items:  adjusted = baseline × (1 - learned_cannibalization_pct × sibling_share)
```

**Confidence:** 0.65-0.80 depending on historical promo count.

### LLM Escalation

Escalate when:
- Novel promotion type with no history (e.g., first-ever bundle offer)
- Promotion during lifecycle transition (NPI + promo simultaneously)
- Promotion in a new market/channel with no comparable data

---

## 5. Domain 2: NPI — New Product Introduction

### Supply Chain Context

New products have zero demand history. This is the cold-start problem. Industry
approaches (in order of reliability):

1. **Analogous product transfer**: Find most similar existing product by attributes,
   transfer its demand curve scaled by expected market share
2. **Category insertion**: Estimate share of category total based on positioning
3. **S-curve lifecycle model**: Generic growth curve parameterized by steady-state
   volume and time-to-peak
4. **Expert judgment**: Sales/marketing estimate, historically unreliable without
   FVA tracking

NPI also impacts **existing products** — a new premium variant typically
cannibalizes 10-30% of the base variant's demand.

### TRM Behaviour (Deterministic)

**Similar-Product Transfer (approach 1):**
```
For a new product P_new:
  1. Extract attributes: category, sub_category, price_point, material_type,
     target_segment, unit_size
  2. Find k=5 nearest mature products by attribute similarity (Jaccard on
     categorical, Euclidean on numeric — weighted by importance)
  3. For each similar product P_i:
     - Extract demand curve: first 52 weeks of history
     - Normalize to 100% at week 26 (steady-state benchmark)
  4. Weighted average of k curves → reference_curve
  5. Scale: forecast = reference_curve × expected_market_share × category_total

  expected_market_share:
    If explicitly set in product_lifecycle → use it
    Else: estimate from price positioning within category
      - Premium (>120% of category avg price): 10-15% share
      - Mainstream (80-120%): 20-30% share
      - Value (<80%): 30-40% share
```

**Ramp Curve (approach 3, fallback):**
```
Default ramp: [10%, 25%, 50%, 75%, 100%] over 5 periods
  Week 1-4:  10% of expected steady-state
  Week 5-8:  25%
  Week 9-12: 50%
  Week 13-16: 75%
  Week 17+:  100%

Adjusted by category velocity:
  Fast-moving (FMCG): compress to 3 periods
  Slow-moving (industrial): extend to 8 periods
```

**Cannibalization of Existing Products:**
```
For each sibling product P_existing in same category:
  price_gap = abs(P_new.price - P_existing.price) / P_existing.price
  position_overlap = attribute_similarity(P_new, P_existing)

  cannibalization_pct = position_overlap × (1 - price_gap) × 0.3
  # Capped at 30% — NPI rarely takes >30% of any single sibling

  P_existing.adjusted = baseline × (1 - cannibalization_pct)
```

**Confidence:** 0.40-0.60 (NPI is inherently uncertain).

### LLM Escalation

Escalate when:
- No similar products found (similarity score < 0.3 for all candidates)
- Product enters an entirely new category for this tenant
- Market share estimate is ambiguous (no price positioning data)
- Multiple simultaneous NPIs in same category (interaction effects)

**LLM prompt pattern:**
```
Product: {name}, Category: {category}, Price: {price}
No similar products found in catalog. Industry data for {category} NPIs:
- Average time to peak: {weeks}
- Typical steady-state volume in this category: {units/week}
- Cannibalization rate for new entrants: {pct}

Recommend: demand curve (week 1-52), confidence, cannibalization estimate
for existing products in category.
```

---

## 6. Domain 3: EOL — End of Life Coordination

### Supply Chain Context

Product end-of-life requires coordinating:
- **Phase-out curve**: Declining demand as product approaches discontinuation
- **Last-buy quantity**: Final procurement order (enough to serve remaining demand,
  not so much that it becomes obsolete inventory)
- **Successor ramp-up**: The replacement product's demand should mirror the
  phase-out curve inversely
- **Channel-specific timing**: Some channels discontinue earlier than others

### TRM Behaviour (Deterministic)

**Phase-out Curve (from product_lifecycle model):**
```
Default: [90%, 75%, 50%, 25%, 10%, 0%] over 6 periods
  Period -6: 90% of baseline
  Period -5: 75%
  Period -4: 50%
  Period -3: 25%
  Period -2: 10%
  Period -1: 0% (last ship date)

Adjusted by:
  - Actual demand trend (if already declining faster, steepen)
  - Substitute availability (if successor ready, steeper; if delayed, flatter)
  - Customer contractual obligations (some customers guaranteed supply)
```

**Last-Buy Calculation:**
```
remaining_demand = Σ phase_out_curve[t] × baseline[t] for t in remaining_periods
safety_buffer = remaining_demand × 0.15 (15% buffer for demand uncertainty)
existing_inventory = on_hand + in_transit + on_order
last_buy_qty = max(0, remaining_demand + safety_buffer - existing_inventory)
```

**Successor Coordination:**
```
If successor_product_id is set on product_lifecycle:
  successor_ramp = inverse of phase_out: [10%, 25%, 50%, 75%, 90%, 100%]
  Apply as NPI ramp for successor, starting when EOL product hits 50% phase-out
```

**Confidence:** 0.60-0.75 (EOL timing is usually known; demand tail is uncertain).

### LLM Escalation

Escalate when:
- Successor product is delayed (ramp timing mismatch)
- Multiple products retiring simultaneously in same category
- Customer contracts require extended supply past planned EOL

---

## 7. Domain 4: Demand Sensing

### Supply Chain Context

Demand sensing corrects the statistical forecast in the **short horizon (0-14 days)**
using leading indicators that move faster than the weekly batch forecast:

- **POS data**: Actual retail sales vs forecast — if sell-through is 30% above
  forecast midweek, next week's orders will be higher
- **Order pipeline**: Confirmed orders not yet shipped — leading indicator of demand
- **Weather events**: Heatwaves drive beverage demand; storms reduce foot traffic
- **Events/holidays**: Unmodeled events (sports finals, school breaks)
- **Stockout signals**: Zero inventory + demand → observed demand is censored

### TRM Behaviour (Deterministic)

**Exception Detection:**
```
For each product × site:
  actual_recent = demand from last 7-14 days
  forecast_recent = baseline forecast for same period
  ratio = actual_recent / forecast_recent

  If ratio > 1.0 + threshold:  → positive exception (demand above forecast)
  If ratio < 1.0 - threshold:  → negative exception (demand below forecast)
  Else: no exception

  threshold = learned per product_cluster (default 0.15 = 15%)
```

**Short-Horizon Correction:**
```
For the next 1-4 periods:
  correction = α × (actual_recent - forecast_recent)
  α = decay_by_horizon:
    Period +1: α = 0.6 (strong signal)
    Period +2: α = 0.3
    Period +3: α = 0.15
    Period +4: α = 0.05 (weak signal)

  adjusted = baseline + correction
```

**Censored Demand Detection:**
```
If inventory_level = 0 AND demand > 0:
  Observed demand is censored (true demand is higher)
  Estimate: true_demand = observed × (1 + stockout_uplift_factor)
  stockout_uplift_factor = learned from historical recovery patterns
  Default: 1.3 (30% hidden demand)
```

**Confidence:** 0.60-0.75 for POS-based; 0.40-0.55 for weather/event-based.

### LLM Escalation

Escalate when:
- Exception magnitude > 50% and no identifiable cause
- Sensing correction conflicts with another adjustment (promotion + weather + exception simultaneously)

---

## 8. Domain 5: Cannibalization and Substitution

### Supply Chain Context

Products within a category are not independent. Key effects:

- **Cannibalization**: New product or promotion takes volume from siblings.
  Family-level demand may be stable while individual SKU share shifts.
- **Substitution**: When product A is out of stock, some customers buy product B.
  Creates demand inflation on B and deflation on A.
- **Basket effects**: Products bought together (bread + butter). If one is
  unavailable, both suffer reduced demand.
- **Assortment migration**: Over time, demand shifts from older to newer variants
  within a family. Total family volume stays stable but SKU mix changes.

### TRM Behaviour (Deterministic)

**Category Share Monitoring:**
```
For each product in a family:
  current_share = product_demand / family_demand (rolling 4 weeks)
  prior_share = product_demand / family_demand (prior 4 weeks)
  share_change = current_share - prior_share

  If |share_change| > 0.05 (5pp shift):
    Flag as assortment migration
    If family_demand stable (±5%): zero-sum → adjust siblings inversely
    If family_demand growing: growth + migration → partial adjustment only
```

**Promotion Cannibalization:**
```
During active promotion on product P_promo:
  For each sibling P_sibling in same category:
    cannibalization_estimate = learned from historical promos in this category
    If no history: default = uplift_pct × 0.25 (25% of uplift is cannibalized)

    P_sibling.adjustment = -cannibalization_estimate × P_sibling.category_share
```

**Substitution During Stockout:**
```
If product A has inventory = 0 at site S:
  For each substitute B (same category, similar price ±20%):
    substitution_rate = learned from historical stockouts
    Default: 0.15-0.30 depending on price gap

    B.adjustment = A.forecast × substitution_rate
    A.adjustment = A.forecast × -stockout_demand_loss (typically 0.3-0.5 lost)
```

**Confidence:** 0.50-0.70 (cross-product effects are noisy to estimate).

### LLM Escalation

Escalate when:
- More than 3 products in a family are simultaneously affected
- Cannibalization estimate exceeds 30% of a product's baseline
- Novel category with no historical cannibalization data

---

## 9. Domain 6: Consensus Forecasting and FVA

### Supply Chain Context

Consensus forecasting is the S&OP process where Sales, Marketing, Finance,
and Operations review the statistical forecast and apply overrides. Research
shows human overrides **destroy value 60-70% of the time** — they add bias
rather than accuracy.

**Forecast Value Add (FVA)** measures whether each step in the forecasting
process improves accuracy:
```
FVA(step) = MAPE(after step) - MAPE(before step)
Positive FVA = step added value (improved accuracy)
Negative FVA = step destroyed value (worsened accuracy)
```

### TRM Behaviour (Deterministic)

**FVA-Gated Consensus:**
```
When a human override is submitted for product P in category C:
  1. Look up historical FVA for this (user, category) pair
     - Compute: mean FVA of this user's past overrides in this category
     - Require: minimum 5 historical overrides for reliable FVA

  2. Decision:
     If user_category_FVA > 0: accept override (this user adds value here)
     If user_category_FVA <= 0 AND override < 15%: accept with dampening (×0.5)
     If user_category_FVA <= 0 AND override >= 15%: reject → escalate to LLM

  3. For accepted overrides:
     adjusted = baseline × (1 + override_pct × acceptance_weight)
     acceptance_weight:
       FVA > +0.05: 1.0 (full override)
       FVA 0 to +0.05: 0.7 (dampened)
       FVA < 0 (but accepted): 0.5 (heavily dampened)
```

**Exception-Based Consensus (Glenday Sieve):**
```
Only surface for human review when:
  - Override > 15% of baseline (small overrides auto-apply if FVA positive)
  - Product is in top 20% by revenue (Glenday Green/Yellow zone)
  - Override contradicts a strong model signal

For Glenday Red zone (bottom 50% by revenue):
  - Auto-apply if FVA positive, auto-reject if FVA negative
  - Never surface for review (not worth planner time)
```

**Confidence:** Based on FVA track record. Range 0.3-0.8.

### LLM Escalation

Escalate when:
- Override conflicts with multiple corroborating signals (e.g., sales says +40%
  but weather, POS, and market data all say -10%)
- New user with no FVA history making large override (>25%)
- Override on NPI product (no FVA history for this product)

---

## 10. Domain 7: External Signal Adjustment

### Supply Chain Context

External signals (email, voice, market intelligence, competitor actions, news,
weather, economic indicators) provide information the statistical model cannot
capture. The challenge is separating signal from noise.

### TRM Behaviour (Deterministic)

This is the **existing** engine behaviour (fully implemented in
`forecast_adjustment_engine.py` and `forecast_adjustment_trm.py`):

```
1. Source reliability weight: 0.3 (social media) to 0.8 (market intelligence)
2. Time decay: signals older than 72h get discounted at 10%/day
3. Combined confidence = signal_confidence × source_reliability × time_decay
4. If combined_confidence < 0.3: ignore entirely
5. Magnitude = signal_type_base_impact × combined_confidence (capped at 15% low / 50% high)
6. Dampening for: low source accuracy, high volatility products, trend contradiction
7. Persist decision with full audit trail
```

Signal type base impacts range from 10% (price_change, competitor) to 50% (discontinuation).

### LLM Escalation

Escalate when:
- Source reliability < 0.3 (untrusted source, need reasoning)
- Multiple conflicting signals from different sources
- Signal suggests > 50% demand change (data quality concern or major event)
- Persistent trend contradiction (>4 consecutive periods)

---

## 11. TRM vs LLM Decision Boundary

The TRM handles 95% of decisions deterministically (<10ms). LLM escalation
occurs when the TRM's confidence is low or the scenario exceeds its heuristics.

### Escalation Criteria

The TRM escalates to Claude Skills (via the conformal router) when:

| Criterion | Threshold | Why |
|-----------|-----------|-----|
| Conformal interval width | > 0.5 (wide uncertainty) | Model is uncertain — need reasoning |
| NPI with no similar products | similarity_score < 0.3 | Cold-start, no heuristic basis |
| Override from new user | < 5 historical overrides | No FVA track record |
| Novel event type | First occurrence in this category | No historical precedent |
| Conflicting signals | 2+ sources disagree on direction | TRM cannot resolve disagreement |
| Extreme magnitude | > 50% adjustment | Exceeds TRM authority |
| Multi-domain interaction | NPI + promo + sensing simultaneously | Interaction effects too complex for rules |

### LLM Skill Prompt Structure

When escalated, the LLM receives:
1. **SKILL.md** system prompt (domain rules, guardrails, output format)
2. **RAG context**: 5-10 similar past decisions from decision memory (tenant-scoped)
3. **Escalation context**: Why the TRM escalated + its best-effort estimate
4. **Runtime data**: Current forecast, product attributes, category data, signals

### AIIO Governance

| Confidence | AIIO Mode |
|------------|-----------|
| TRM confidence ≥ 0.80 | AUTOMATE (but forecast adjustments always ≥ INFORM per guardrails) |
| TRM confidence 0.50-0.80 | INFORM |
| TRM confidence < 0.50 | INSPECT |
| LLM decision (any) | INSPECT (LLM decisions always require human review) |

---

## 12. Hive Signal Integration

### Signals Read (Before Decision)

| Signal | Source | What It Means for Forecast Adjustment |
|--------|--------|--------------------------------------|
| `DEMAND_SURGE` | Forecast Baseline TRM | Baseline detected significant uptick — adjustment should not double-count |
| `DEMAND_DROP` | Forecast Baseline TRM | Baseline detected decline — adjustment should confirm or contradict |
| `ORDER_EXCEPTION` | ATP Executor TRM | Unexpected order volume — may indicate demand sensing exception |
| `QUALITY_HOLD` | Quality TRM | Quality event may suppress demand (product unavailability) |
| `NETWORK_SHORTAGE` | Inter-site tGNN | Supply constraint may cause censored demand at downstream sites |

### Signals Emitted (After Decision)

| Signal | When | Consumed By |
|--------|------|------------|
| `FORECAST_ADJUSTED` | Any non-zero adjustment applied | Inventory Buffer TRM, PO Creation TRM, ATP TRM |

The emitted signal includes:
- `urgency`: proportional to `abs(adjustment_pct) × 2` (capped at 1.0)
- `direction`: "surplus" (forecast up), "shortage" (forecast down), "neutral"
- `magnitude`: `abs(adjustment_pct)`
- `payload`: signal_id, adj_direction, adj_pct, source

---

## 13. FVA (Forecast Value Add) Tracking

Every adjustment from every domain is tracked for accuracy contribution:

```
FVA(source, category, horizon) = MAPE(baseline + adjustment) - MAPE(baseline only)
```

**Tracked dimensions:**
- **Per source**: email, voice, market_intelligence, promotion, npi, sensing, consensus
- **Per category**: product hierarchy category level
- **Per horizon**: 1-week, 4-week, 13-week, 26-week
- **Per user**: for consensus overrides, track by submitting user

**Retention:** 52 weeks rolling. Updated weekly after actuals are available.

**Automated actions:**
- If FVA < -0.02 for 8 consecutive weeks → auto-suppress source for this category
- If FVA > +0.05 for 8 consecutive weeks → increase source weight
- Suppressed sources still logged but adjustment_pct set to 0

**Decision Stream visibility:** FVA scores surfaced in the Decision Stream
"Ask Why" response for any forecast adjustment decision.

---

## 14. Guardrails

### From SKILL.md (LLM Path)

1. **Mandatory human review**: All LLM-generated forecast adjustments
2. **Magnitude ceiling**: 25% max single adjustment without explicit approval
3. **Confidence ceiling**: 0.7 cap for LLM decisions
4. **Time decay**: Always applied, never skipped
5. **Conflicting signal dampening**: 30% reduction when sources disagree

### TRM-Level Guardrails

1. **Max adjustment**: 50% for high confidence, 15% for low confidence
2. **Minimum signal confidence**: 0.3 (below = ignore)
3. **Trend contradiction dampening**: 30% reduction
4. **High volatility filter**: Ignore signals < 10% on CV > 0.5 products
5. **Learned source suppression**: FVA-driven auto-suppression
6. **NPI cannibalization cap**: 30% max per sibling product
7. **Consensus FVA gate**: Reject overrides from users with negative FVA

### AIIO Override for Forecast Adjustments

Per the architecture decision: forecast adjustments always surface at minimum
INFORM level (never fully silent AUTOMATE) because forecast changes propagate
through the entire planning cascade (MPS, MRP, supply plans, ATP).

---

## 15. Output Specification

```python
ForecastAdjustmentOutput:
    product_id: str
    site_id: str
    adjustment_type: str          # promotion, npi, eol, sensing, cannibalization, consensus, signal
    baseline_p50: float           # From Forecast Baseline TRM
    adjusted_p50: float           # After this adjustment
    adjustment_pct: float         # (adjusted - baseline) / baseline
    confidence: float             # TRM confidence in adjustment
    fva_expected: float           # Expected FVA based on historical accuracy of this source
    reasoning: str                # Structured explanation
    escalated_to_llm: bool
    llm_reasoning: Optional[str]
    signal_sources: List[str]     # Which signals contributed
    cannibalization_impact: Optional[Dict[str, float]]  # {product_id: pct_impact}
    forward_buy_adjustment: Optional[float]  # Post-promo demand depression %
    lifecycle_stage: Optional[str]  # If NPI/EOL related
    fva_gate_result: Optional[str]  # For consensus: "accepted", "dampened", "rejected"
    dampening_rules_applied: List[str]  # Which guardrail rules fired
```

---

## 16. Decision Table Schema

`powell_forecast_adjustment_decisions` (existing, expanded):

| Column | Type | Purpose |
|--------|------|---------|
| product_id | String(100) | Product |
| site_id | String(100) | Site |
| signal_source | String(50) | Source of the signal |
| signal_type | String(50) | Type of signal |
| signal_text | Text | Raw signal content |
| signal_confidence | Float | Signal extraction confidence |
| current_forecast_value | Float | Baseline before adjustment |
| adjustment_direction | String(20) | up/down/no_change |
| adjustment_magnitude | Float | Absolute adjustment |
| adjustment_pct | Float | Percentage adjustment |
| adjusted_forecast_value | Float | Final value after adjustment |
| time_horizon_periods | Integer | How many periods affected |
| reason | Text | Explanation |
| confidence | Float | TRM/LLM confidence |
| state_features | JSON | Feature snapshot for replay |
| was_applied | Boolean | Whether adjustment was executed |
| actual_demand | Float | Actual demand (populated when known) |
| forecast_error_before | Float | MAPE before adjustment |
| forecast_error_after | Float | MAPE after adjustment |
| (HiveSignalMixin) | Various | status, signal_context, urgency, cycle_phase, reasoning |

---

## 17. Implementation Status

| Capability | Status | Notes |
|-----------|--------|-------|
| External signal processing | **Implemented** | Engine + TRM + SKILL.md |
| Source reliability weighting | **Implemented** | Configurable per source |
| Signal confidence scoring | **Implemented** | Combined confidence formula |
| Time decay | **Implemented** | 72h freshness, 10%/day decay |
| Trend contradiction dampening | **Implemented** | 30% reduction |
| High volatility filter | **Implemented** | CV > 0.5, signal < 10% → ignore |
| Decision persistence | **Implemented** | Full audit trail |
| Outcome tracking | **Implemented** | record_outcome() method |
| Hive signal read/emit | **Implemented** | DEMAND_SURGE/DROP → FORECAST_ADJUSTED |
| CDT risk bounds | **Implemented** | Conformal decision thresholds |
| Context explanation | **Implemented** | Inline reasoning generation |
| **Promotion elasticity** | **Not implemented** | Manual uplift_pct, no learned elasticity |
| **Promotion cannibalization** | **Not implemented** | Manual cannibalization_pct, no learned |
| **Forward buy estimation** | **Not implemented** | No post-promo demand depression |
| **NPI transfer learning** | **Not implemented** | No similar-product matching |
| **NPI cannibalization** | **Not implemented** | No cross-product impact estimation |
| **EOL phase-out curve** | **Partial** | Lifecycle model exists, not wired to TRM |
| **EOL successor coordination** | **Not implemented** | No inverse ramp on successor |
| **Demand sensing** | **Not implemented** | No POS exception detection |
| **Short-horizon correction** | **Not implemented** | No daily correction logic |
| **Category share monitoring** | **Not implemented** | No assortment migration detection |
| **Substitution estimation** | **Not implemented** | No stockout→substitute demand shift |
| **Consensus FVA gating** | **Not implemented** | Framework defined, not enforced |
| **FVA tracking** | **Not implemented** | Outcome stored but FVA not computed |
| **Source auto-suppression** | **Not implemented** | No FVA-driven suppression |
| **LLM escalation from TRM** | **Not implemented** | SKILL.md exists but not wired to TRM conformal router |

### Key Files

| File | Purpose |
|------|---------|
| `services/powell/forecast_adjustment_trm.py` | TRM class (existing) |
| `services/powell/engines/forecast_adjustment_engine.py` | Deterministic engine (existing) |
| `services/skills/forecast_adjustment/SKILL.md` | LLM skill prompt (existing) |
| `services/skills/demand_planning/SKILL.md` | Broader demand planning skill (existing; demand forecasting is handled by Forecast Baseline + Forecast Adjustment TRMs, not tGNNs) |
| `models/powell_decisions.py` | PowellForecastAdjustmentDecision table (existing) |
| `services/product_lifecycle_service.py` | NPI/EOL lifecycle management (existing) |
| `services/promotional_planning_service.py` | Promotion management (existing) |
| `models/external_signal.py` | External signal ingestion (existing) |
| `docs/internal/architecture/TACTICAL_AGENT_ARCHITECTURE.md` | Architecture context |

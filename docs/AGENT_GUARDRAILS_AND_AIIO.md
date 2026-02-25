# Agent Guardrails & AIIO Decision Governance

> **Autonomy Platform — Comprehensive Reference**
>
> How AI agents are constrained, monitored, and corrected across the entire
> decision lifecycle: from policy generation to execution.

---

## Table of Contents

1. [AIIO Framework Overview](#1-aiio-framework-overview)
2. [The Five Guardrail Layers](#2-the-five-guardrail-layers)
3. [Layer 1 — Authority Boundaries (Who Can Do What)](#3-layer-1--authority-boundaries-who-can-do-what)
4. [Layer 2 — Decision Governance (Impact-Based Gating)](#4-layer-2--decision-governance-impact-based-gating)
5. [Layer 3 — Conformal Prediction (Calibrated Uncertainty)](#5-layer-3--conformal-prediction-calibrated-uncertainty)
6. [Layer 4 — Override Effectiveness (Bayesian Learning from Corrections)](#6-layer-4--override-effectiveness-bayesian-learning-from-corrections)
7. [Layer 5 — Agent-to-Agent Authorization (AAP)](#7-layer-5--agent-to-agent-authorization-aap)
8. [GNN-Level Guardrails (Network Scope)](#8-gnn-level-guardrails-network-scope)
9. [Decision Lifecycle — End to End](#9-decision-lifecycle--end-to-end)
10. [Override Hierarchy — Four Scopes](#10-override-hierarchy--four-scopes)
11. [Feedback Loops — How Guardrails Self-Improve](#11-feedback-loops--how-guardrails-self-improve)
12. [Governance Policy Configuration](#12-governance-policy-configuration)
13. [Personas & Governance Experience](#13-personas--governance-experience)
14. [Implementation Status](#14-implementation-status)
15. [Key Files Reference](#15-key-files-reference)

---

## 1. AIIO Framework Overview

AIIO is the core principle governing how AI agent decisions interact with
human planners. Every decision falls into one of four modes:

| Mode | Agent Action | Human Action | Timing |
|------|-------------|--------------|--------|
| **Automate** | Execute immediately | None required | Real-time |
| **Inform** | Execute immediately | Acknowledge receipt | Post-execution |
| **Inspect** | Hold for review window | Accept, reject, or override before deadline | Pre-execution |
| **Override** | Already executed | Retroactively correct with mandatory reason | Post-execution |

### Core Principles

1. **Every decision is recorded** with full explanation (`AgentAction.explanation`)
2. **Every decision is explainable** via Ask Why (structured reasoning chain, alternatives considered, model attribution)
3. **Every override captures a reason** — mandatory for audit trail and learning
4. **Mode is assigned by impact**, not by decision type — a $50 safety stock tweak is AUTOMATE, a $500K PO is INSPECT
5. **Overrides are measured** — Bayesian posteriors track whether human corrections actually improve outcomes

### Key Distinction: Agent-Initiated vs User-Initiated

```
Agent-initiated (modes assigned by governance):
  AUTOMATE ─── Execute, no notification
  INFORM ───── Execute, notify planner
  INSPECT ──── Hold, wait for human review (time-gated)

User-initiated (always available on any decision):
  OVERRIDE ─── Retroactive correction of any executed decision
  ASK WHY ──── Inspect explanation, attribution, counterfactuals
```

INSPECT is the bridge between these two sides. It's the only agent-initiated
mode that requires pre-execution human involvement.

### The Decision Funnel

In production, the distribution should resemble:

```
  AUTOMATE   ████████████████████████  ~70-85%
  INFORM     ████████                  ~10-20%
  INSPECT    ████                      ~5-10%
  OVERRIDE   █                         ~1-3% (of executed decisions)
```

A healthy system has a high Touchless Rate (AUTOMATE decisions that execute
without any human involvement and produce good outcomes). The goal is for
INSPECT and OVERRIDE rates to decrease over time as the AI improves.

---

## 2. The Five Guardrail Layers

Guardrails are not a single mechanism — they are a layered defense-in-depth
architecture. Each layer catches different classes of error:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Agent-to-Agent Authorization (AAP)                 │
│   Cross-functional trade-offs between agents                │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Override Effectiveness (Bayesian Posteriors)        │
│   Did the human correction actually help?                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Conformal Prediction (Calibrated Uncertainty)       │
│   How confident is the model? Is this prediction unusual?   │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Decision Governance (Impact-Based AIIO Gating)      │
│   High-impact → INSPECT; low-impact → AUTOMATE              │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Authority Boundaries (Per-Agent Action Map)         │
│   Can this agent even request this action?                  │
└─────────────────────────────────────────────────────────────┘
```

Each layer operates independently — a decision must pass ALL layers to
execute. A TRM can have authority for an action (Layer 1), but if its
impact score is high (Layer 2), confidence is low (Layer 3), or it
requires another agent's resources (Layer 5), it will still be held.

---

## 3. Layer 1 — Authority Boundaries (Who Can Do What)

Every agent has an **authority boundary** that classifies every possible
action into one of three categories:

### Authority Categories

| Category | Meaning | Example |
|----------|---------|---------|
| **Unilateral** | Agent can execute without asking anyone | ATP agent: `partial_fill`, `substitute_product` |
| **Requires Authorization** | Agent must get approval from a target agent | ATP agent: `request_expedite` → Logistics agent |
| **Forbidden** | Agent cannot perform this action, period | ATP agent: `override_priority`, `change_policy_envelope` |

### Per-Role Boundary Definitions

The platform defines boundaries for 12 functional agent roles:

| Agent Role | Unilateral Actions | Requires Auth | Forbidden |
|------------|-------------------|---------------|-----------|
| **SO/ATP** | Reallocate within tier, partial fill, substitute | Expedite (→ Logistics), cross-tier allocation (→ Allocation), request transfer (→ Inventory) | Override priority, change policy envelope |
| **Supply** | Adjust order timing, split order | Make-vs-buy (→ Plant), expedite PO (→ Procurement), subcontracting (→ Plant) | Change sourcing rules |
| **Allocation** | Fair-share distribute, priority heuristic | Cross-channel rebalance (→ Channel), override allocation priority (→ S&OP) | Override allocation reserve |
| **Inventory** | Adjust SS within band, trigger cycle count | Cross-DC transfer (→ Logistics), write-off excess (→ Finance), SS beyond band (→ S&OP) | — |
| **Plant** | Sequence within shift, minor changeover | Rush order (→ SO/ATP), overtime (→ Finance), BOM substitution (→ Quality) | Shutdown line |
| **Quality** | Hold lot, release lot, rework | Use-as-is concession (→ SO/ATP), scrap above threshold (→ Finance), supplier escalation (→ Procurement) | — |
| **Maintenance** | Schedule PM, defer within window, emergency | Defer beyond window (→ Plant), outsource (→ Procurement) | — |
| **Procurement** | Release blanket PO, spot buy within budget | Spot buy over budget (→ Finance), new supplier qual (→ Quality), dual source (→ Supply) | Change contract terms |
| **Finance** | Approve within delegation | Budget reallocation (→ S&OP) | Capex approval |
| **S&OP** | Adjust policy parameters | Seasonal prebuild (→ Finance), product rationalization (→ Demand) | — |
| **Demand** | Adjust forecast within band, consensus override | Override statistical forecast (→ S&OP), new product forecast (→ S&OP) | — |
| **Channel** | Adjust channel priority | Cross-channel reallocation (→ Allocation), promotion surge (→ Supply) | — |

### Enforcement Point

Authority boundaries are checked in `SiteAgent.check_authority_boundary()`.
If an action is classified as REQUIRES_AUTHORIZATION, the agent must submit
an `AuthorizationRequest` (Layer 5) before proceeding.

### Implementation

```
backend/app/services/powell/authority_boundaries.py
  ├── AuthorityBoundary (dataclass) — unilateral, requires_authorization, forbidden
  ├── AuthorizationTarget (dataclass) — target_agent, sla_minutes, auto_approve_if_no_contention
  ├── AUTHORITY_BOUNDARIES dict — 12 roles, 50+ action classifications
  ├── check_action_category() — Quick lookup
  └── get_required_target() — Where to route authorization requests
```

---

## 4. Layer 2 — Decision Governance (Impact-Based Gating)

> **Status**: Planned (see `docs/plans/cheeky-gliding-panda.md`)

Decision Governance is the mechanism that assigns AIIO modes based on the
**impact** of a specific decision instance, not just its type.

### Impact Scoring

Every decision is scored on 5 dimensions (0-100 each):

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| **Financial** | 30% | Dollar value of the decision (normalized against customer revenue) |
| **Scope** | 20% | Blast radius — site-level (20), region (50), network-wide (90) |
| **Reversibility** | 20% | How hard it is to undo (see table below) |
| **Confidence** | 15% | Model uncertainty — lower confidence = higher impact score |
| **Override Rate** | 15% | Historical override frequency for this decision type — higher override rate = more scrutiny |

**Composite impact score** = weighted sum → 0-100 scale

### Reversibility Reference

| Action Type | Score | Rationale |
|-------------|-------|-----------|
| `forecast_adjustment` | 10 | Next forecast cycle overwrites |
| `order_tracking` | 15 | Exception flags, easily cleared |
| `safety_stock` | 20 | Can re-adjust immediately |
| `maintenance_scheduling` | 25 | Can reschedule easily |
| `inventory_rebalance` | 30 | Transfer reversible at cost |
| `to_execution` | 40 | In-transit, can reroute |
| `mo_execution` | 50 | Production started, partial reversal |
| `atp_execution` | 60 | Customer promise made |
| `quality_disposition` | 70 | Scrapped product is gone |
| `subcontracting` | 75 | External commitment |
| `po_creation` | 80 | Supplier commitment, cancellation penalties |

### Mode Assignment

```
Impact Score:  0 ──── 20 ──── 50 ──── 100
                │      │       │
                ▼      ▼       ▼
Mode:       AUTOMATE  INFORM  INSPECT
```

Thresholds are configurable per customer via `DecisionGovernancePolicy`:

```python
automate_below = 20.0   # Impact < 20 → AUTOMATE
inform_below = 50.0     # 20 ≤ Impact < 50 → INFORM
                         # Impact ≥ 50 → INSPECT
```

### INSPECT Hold Window

When a decision is assigned INSPECT mode:

1. `hold_until = now + policy.hold_minutes` (default: 60 min)
2. `execution_result = PENDING`
3. Decision appears in the **Governance Worklist**
4. Planner can: **Accept** (execute), **Reject** (cancel), or **Override** (modify + execute)
5. If no response by `hold_until`:
   - If `auto_apply_on_expiry = True` → auto-execute (like AUTOMATE)
   - If `auto_apply_on_expiry = False` → expire (cancel)
6. If no response by `escalate_after_minutes` → escalation notification

### Governance Policies

Policies are hierarchical and customer-specific:

```
Specificity (most specific wins):
  (customer_id, action_type, category, agent_id)  ← Most specific
  (customer_id, action_type, category)
  (customer_id, action_type)
  (customer_id)                                    ← Catch-all
  System default                                   ← Fallback
```

This allows fine-grained control: a conservative customer might INSPECT
all PO decisions above $10K, while an aggressive customer AUTOMATEs
everything except network-wide rebalances.

### Sweeper Jobs

Two background jobs enforce time-based governance:

| Job | Schedule | Purpose |
|-----|----------|---------|
| **Auto-Apply Sweeper** | Every 5 minutes | Executes decisions past their `hold_until` deadline |
| **Escalation Checker** | Every 30 minutes | Flags decisions past `escalate_after_minutes` with no response |

---

## 5. Layer 3 — Conformal Prediction (Calibrated Uncertainty)

Every `AgentAction` carries calibrated uncertainty quantification:

| Field | Purpose |
|-------|---------|
| `predicted_outcome` | Point estimate (e.g., expected service level after this decision) |
| `prediction_interval_lower` | Lower bound (P10) |
| `prediction_interval_upper` | Upper bound (P90) |
| `confidence_level` | Interval coverage (e.g., 0.80 = 80%) |
| `calibration_score` | Historical accuracy of this interval type (0-1) |
| `nonconformity_score` | How unusual this context is vs training data |

### How Conformal Prediction Acts as a Guardrail

1. **Low confidence feeds into impact scoring**: `confidence_dimension = (1 - confidence_level) * 100`. A decision with 0.60 confidence scores 40 on the confidence dimension, pushing it toward INSPECT.

2. **High nonconformity triggers caution**: If the decision context is far from anything the model was trained on, the nonconformity score is high — a signal that the model is extrapolating.

3. **Outcome tracking enables recalibration**: After execution, `actual_outcome` is measured and `outcome_within_interval` is computed. If intervals are systematically too narrow (poor calibration), the `ConformalOrchestrator` automatically widens them.

### Self-Healing Calibration Loop

```
Decision created with prediction interval
       ↓
Outcome measured (after feedback horizon)
       ↓
outcome_within_interval = True/False
       ↓
ConformalOrchestrator monitors coverage rate
       ↓
If coverage < target → widen intervals automatically
If coverage >> target → tighten (more precise)
```

Six closed loops operate across: demand, lead time, price, yield, service level, and cost.

### Implementation

```
backend/app/services/conformal_orchestrator.py  — Auto-recalibration
backend/app/models/agent_action.py              — Prediction fields on AgentAction
backend/app/models/conformal_prediction.py      — Conformal prediction suite persistence
```

---

## 6. Layer 4 — Override Effectiveness (Bayesian Learning from Corrections)

When a human overrides an agent decision, the platform doesn't blindly
trust the override. Instead, it tracks whether the human's correction
**actually led to a better outcome** than the agent's recommendation.

### Bayesian Beta Posteriors

Each `(user_id, trm_type)` pair maintains a Beta distribution:

```
Prior:     Beta(1, 1)    → E[p] = 0.50  (uninformative)
After 20 overrides:  Beta(14, 8)  → E[p] = 0.64  (beneficial trend)
```

**Update rule**: When an override outcome is observed:
- If `delta > +0.05` (beneficial): `alpha += signal_strength`
- If `delta < -0.05` (detrimental): `beta += signal_strength`
- If neutral: no update

### Three Observability Tiers

The `signal_strength` of each update depends on how reliably we can
compute the counterfactual ("what would have happened without the override"):

| Tier | Signal | Decision Types | Counterfactual Method |
|------|--------|---------------|----------------------|
| **1** | 1.0 | ATP, Forecast, Quality, GNN Allocation | Analytical — exact replay with agent's original values |
| **2** | 0.3-0.9 | MO, TO, PO, Order Tracking, GNN S&OP, GNN Execution | Statistical — propensity-score-matched pairs |
| **3** | 0.15 | Safety Stock, Inventory, Maintenance, Subcontracting | Bayesian prior only — high confounding |

Tier 2 signal strength increases with matched-pair availability:
`signal = min(0.9, 0.3 + (match_count / 50) * 0.6)`

### Training Weight Derivation

The posterior maps to a **TRM training sample weight**:

```python
weight = 0.3 + 1.7 * E[p]           # Maps [0,1] → [0.3, 2.0]
weight = min(weight, max_weight)      # Certainty discount for few observations
```

| Posterior State | E[p] | Weight | Meaning |
|----------------|------|--------|---------|
| Uninformative (new user) | 0.50 | 0.85 | Moderate trust |
| Consistently beneficial | 0.85 | 1.75 | High trust, strong learning signal |
| Consistently detrimental | 0.15 | 0.56 | Low trust, downweighted in training |
| Proven expert (many obs) | 0.95 | 2.00 | Maximum trust |

### Systemic Impact — Site-Window BSC

Overrides are measured at **two scopes** to prevent locally-good but
systemically-harmful corrections from inflating weights:

```
Composite Score = 0.4 × local_delta + 0.6 × site_bsc_delta
```

- **Local delta**: Direct counterfactual comparison (agent vs human for THIS decision)
- **Site-window BSC delta**: Balanced scorecard change across the ENTIRE site
  in a window around the override (pre vs post aggregate performance)

A planner who consistently makes good individual ATP decisions but whose
overrides create upstream supply disruptions will see their site-window
delta pull down their composite score.

### Causal Learning Pipeline (Progressive)

The system grows in sophistication as data accumulates:

```
Stage 1: Bayesian priors (from day 1)
    ↓ enough data for matching
Stage 2: Propensity-score matching (CausalMatchingService)
    ↓ enough matched pairs
Stage 3: Doubly robust estimation
    ↓ enough features
Stage 4: Causal forests (Athey & Imbens 2018)
    → Identifies WHEN overrides help vs hurt (heterogeneous treatment effects)
```

### How Override Effectiveness Acts as a Guardrail

1. **Detrimental overrides are downweighted** in TRM training (weight 0.3-0.56)
2. **Override rate feeds back into impact scoring** (Layer 2) — high override rate for a decision type increases scrutiny
3. **Per-user posteriors surface in dashboards** — managers see which planners are adding value and which need coaching
4. **System-level metrics drive trust calibration**: Override Dependency Ratio, Touchless Rate, Agent Score

### Implementation

```
backend/app/models/override_effectiveness.py         — OverrideEffectivenessPosterior, CausalMatchPair
backend/app/services/override_effectiveness_service.py — Bayesian posterior management, TIER_MAP
backend/app/services/causal_matching_service.py       — Propensity-score matching for Tier 2
backend/app/services/powell/outcome_collector.py      — _compute_site_window_bsc() for systemic impact
```

---

## 7. Layer 5 — Agent-to-Agent Authorization (AAP)

The Agentic Authorization Protocol governs **cross-functional decisions
between agents**. When one agent needs resources or permissions controlled
by another agent, it must request authorization.

### Three-Phase Protocol

```
Phase 1: EVALUATE
  Originating agent runs what-if scenarios on ALL options
  (including cross-authority actions) using the what-if engine.
  Every option produces a Balanced Scorecard.

Phase 2: REQUEST
  Agent sends AuthorizationRequest to target agent with:
  - Proposed action + parameters
  - Balanced Scorecard (all metrics, all quadrants)
  - Fallback action (what happens if denied)
  - Complementary actions (what other agents should do)

Phase 3: AUTHORIZE
  Target agent checks:
  - Resource availability (contention with other requests)
  - Net benefit vs threshold
  - Response: AUTHORIZE / DENY / COUNTER_OFFER / ESCALATE
```

### Net Benefit Threshold as Governance

The `benefit_threshold` (from the Policy Envelope) controls autonomy:

```
Net benefit well above threshold  →  Auto-resolve (agent approves)
Net benefit near threshold         →  Human reviews (escalation)
Net benefit below threshold        →  Reject
```

### Escalation with Pre-Digested Options

When a decision escalates to a human:
- Humans see **ranked alternatives** with full scorecards
- The decision is already analyzed — humans choose, not compute
- Human resolutions feed back into agent training (`is_expert=True` in replay buffer)

### Implementation

```
backend/app/services/authorization_protocol.py    — AuthorizationRequest, BalancedScorecard, AAP dataclasses
backend/app/services/authorization_service.py     — create_agent_authorization_request, escalate_to_human
backend/app/services/escalation_formatter.py      — Tier 2→3 bridge with ranked alternatives
backend/app/services/powell/authority_boundaries.py — Per-agent action classification (Layer 1 integration)
```

---

## 8. GNN-Level Guardrails (Network Scope)

TRM agents operate at the site level. GNN models operate at the network
level, producing outputs that propagate to many sites simultaneously.
GNN-level guardrails catch network-scope errors before they amplify:

### Three Review Scopes

| Scope | Model | Cadence | What's Reviewed |
|-------|-------|---------|----------------|
| **S&OP Policy** | S&OP GraphSAGE | Weekly | safety_stock_multiplier, criticality_score, bottleneck_risk, resilience_score |
| **Execution Directive** | Execution tGNN | Daily | demand_forecast, exception_probability, order_recommendation |
| **Allocation Refresh** | Execution tGNN | Daily | Priority × Product × Location allocations |

### GNN Directive Review Lifecycle

```
GNN orchestration runs
    ↓
Directive persisted as PROPOSED (GNNDirectiveReview)
    ↓
Human reviews (or expires_at reached)
    ↓
┌─── ACCEPTED ──── Apply GNN values to SiteAgent
├─── OVERRIDDEN ── Apply human's modified values
├─── REJECTED ──── Discard directive (use previous values)
├─── AUTO_APPLIED ─ Review window expired, auto-apply
└─── EXPIRED ───── Review window expired, discard
```

### Policy Envelope Overrides

The S&OP Director can override individual parameters from the S&OP
GraphSAGE output before they propagate downstream:

```
S&OP GraphSAGE produces PolicyEnvelope:
  {
    safety_stock_targets: {frozen: 2.5, chilled: 1.8, ambient: 1.2},
    otif_floors: {strategic: 98, standard: 95, economy: 90},
    expedite_caps: {frozen: 5, chilled: 3}
  }

Director overrides one parameter:
  safety_stock_targets.frozen: 2.5 → 3.0
  reason: "Hurricane season starting — need extra buffer for frozen supply chain"

Override recorded as PolicyEnvelopeOverride:
  parameter_path: "safety_stock_targets.frozen"
  original_value: 2.5
  override_value: 3.0
  reason_code: "seasonal_risk"
```

Each override feeds into the Bayesian posterior system via the `gnn_sop_policy`
scope in the TIER_MAP (Tier 2, statistical counterfactual).

### Implementation

```
backend/app/models/gnn_directive_review.py          — GNNDirectiveReview, PolicyEnvelopeOverride
backend/app/services/powell/gnn_orchestration_service.py — _persist_directive_reviews()
frontend/src/components/admin/GNNDirectiveReview.jsx — Review UI in GNN Dashboard
```

---

## 9. Decision Lifecycle — End to End

Here's how all five guardrail layers interact for a single decision:

```
1. TRM agent generates decision
   │
2. Layer 1: Authority Boundary Check
   │  ├── UNILATERAL → continue
   │  ├── REQUIRES_AUTHORIZATION → submit AAP request (Layer 5) → wait
   │  └── FORBIDDEN → reject immediately
   │
3. Layer 2: Decision Governance (Impact Scoring)
   │  ├── Impact < 20 → AUTOMATE
   │  ├── Impact 20-50 → INFORM
   │  └── Impact ≥ 50 → INSPECT (hold for review)
   │
4. Layer 3: Conformal Prediction Annotation
   │  └── Attach prediction interval, confidence, nonconformity score
   │      (feeds back into impact scoring via confidence dimension)
   │
5. Decision persisted as AgentAction
   │  ├── AUTOMATE → execute immediately
   │  ├── INFORM → execute, notify planner
   │  └── INSPECT → hold in Governance Worklist
   │
6. If INSPECT:
   │  ├── Planner accepts → execute
   │  ├── Planner rejects → cancel
   │  ├── Planner overrides → modify + execute
   │  └── Deadline expires → auto-apply or expire
   │
7. Post-Execution: Outcome Collection
   │  ├── OutcomeCollector computes actual outcome (after feedback horizon)
   │  ├── If overridden: compute counterfactual delta
   │  └── Update Bayesian posterior (Layer 4)
   │
8. Feedback Loop:
   ├── Override effectiveness → adjusts TRM training weights
   ├── Override rate → adjusts future impact scoring (Layer 2)
   ├── Conformal coverage → adjusts prediction intervals (Layer 3)
   └── AAP resolutions → adjusts authorization thresholds (Layer 5)
```

---

## 10. Override Hierarchy — Four Scopes

Overrides happen at four levels of the planning cascade, each with
different impact radius and review cadence:

```
Scope 1: S&OP / GraphSAGE (Weekly)
│   ├── Policy Envelope parameters (safety stock targets, OTIF floors)
│   ├── Reviewed by: S&OP Director
│   ├── Model: PolicyEnvelopeOverride
│   └── Tier: 2 (statistical counterfactual)
│
Scope 2: Execution tGNN (Daily)
│   ├── Site directives (demand forecast, exception probability)
│   ├── Reviewed by: MPS Manager or Supply Planner
│   ├── Model: GNNDirectiveReview
│   └── Tier: 2 (matched-pair comparison)
│
Scope 3: TRM Decisions (Real-time)
│   ├── Execution decisions (ATP, PO, MO, TO, quality, etc.)
│   ├── Reviewed by: Operational planner via Worklist
│   ├── Model: SiteAgentDecision + AgentAction
│   └── Tier: 1-3 (varies by decision type)
│
Scope 4: AAP Authorization (Seconds-minutes)
    ├── Cross-functional requests (expedite, rebalance, make-vs-buy)
    ├── Reviewed by: Target agent or human (if escalated)
    ├── Model: AuthorizationRequest/Response
    └── Tier: 2 (net benefit scorecard comparison)
```

### Cascade Effect

Overrides at higher scopes propagate downward:

- An S&OP Director overrides the safety stock multiplier for frozen products
- This changes the PolicyEnvelope parameters
- Which changes the tGNN directives for affected sites
- Which changes the TRM context for InventoryBufferTRM decisions at those sites

The system tracks the **root cause** of cascading changes via the
hierarchy context on AgentAction (site_key, product_key, time_key).

---

## 11. Feedback Loops — How Guardrails Self-Improve

The guardrail system is not static — it continuously adapts based on
observed outcomes:

### Loop 1: Override → Training Weight

```
Human overrides TRM decision
    → Outcome measured after feedback horizon
    → Bayesian posterior updated (Layer 4)
    → Training weight adjusted for TRM retraining
    → Future TRM decisions incorporate human judgment
    → Override rate decreases (if human was right)
```

**Timeline**: Feedback horizon varies by type — ATP: 4 hours, Inventory: 24 hours, PO: 7 days.

### Loop 2: Override Rate → Impact Scoring

```
High override rate observed for po_creation
    → Override Rate dimension scores higher (e.g., 60/100)
    → More PO decisions assigned INSPECT mode
    → More human review, more override data collected
    → TRM retrains with richer data
    → PO decision quality improves
    → Override rate decreases
    → Impact score decreases → more AUTOMATE
```

**Timeline**: Override rate aggregated weekly.

### Loop 3: Conformal → Prediction Quality

```
Prediction interval too narrow (coverage < 80%)
    → ConformalOrchestrator detects drift
    → Intervals widened automatically
    → Confidence dimension in impact scoring increases
    → More decisions pushed to INSPECT
    → After recalibration, coverage restored
    → Intervals tighten again
```

**Timeline**: Continuous monitoring, recalibration hourly.

### Loop 4: AAP Resolution → Authorization Threshold

```
Human consistently approves cross-DC transfers
    → Benefit threshold for this action type can be relaxed
    → More transfers auto-resolve (agent-to-agent)
    → Human only reviews edge cases
```

**Timeline**: S&OP cycle (weekly/monthly).

### Loop 5: CDC → Model Retraining

```
CDCMonitor detects metric deviation (6 thresholds)
    → CDCRetrainingService evaluates retraining need
    → TRMTrainer.train() with latest data (including weighted overrides)
    → New checkpoint deployed to SiteAgent
    → Decision quality improves across the board
```

**Timeline**: Evaluation every 6 hours, retraining when ≥100 new experiences + CDC trigger + cooldown elapsed.

### Loop 6: GNN Directive → Network Adjustment

```
Human overrides GNN directive for Site-East
    → Outcome tracked at site and network level
    → GNN retraining incorporates override as label
    → Future GNN directives reflect human insight
    → Override rate for GNN directives decreases
```

**Timeline**: GNN orchestration cycle (daily/weekly).

---

## 12. Governance Policy Configuration

### DecisionGovernancePolicy Schema

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `customer_id` | FK | Required | Which customer this policy applies to |
| `action_type` | String | NULL (all) | Filter by action type |
| `category` | String | NULL (all) | Filter by category (INVENTORY, PROCUREMENT, etc.) |
| `agent_id` | String | NULL (all) | Filter by specific agent |
| `automate_below` | Float | 20.0 | Impact score threshold for AUTOMATE |
| `inform_below` | Float | 50.0 | Impact score threshold for INFORM (above = INSPECT) |
| `hold_minutes` | Integer | 60 | Default INSPECT review window |
| `max_hold_minutes` | Integer | 1440 | Maximum hold before force-resolve (24h) |
| `auto_apply_on_expiry` | Boolean | True | Auto-execute when hold expires? |
| `escalate_after_minutes` | Integer | 480 | Escalate after 8h no response |
| `weight_financial` | Float | 0.30 | Financial dimension weight |
| `weight_scope` | Float | 0.20 | Scope dimension weight |
| `weight_reversibility` | Float | 0.20 | Reversibility dimension weight |
| `weight_confidence` | Float | 0.15 | Confidence dimension weight |
| `weight_override_rate` | Float | 0.15 | Override rate dimension weight |
| `priority` | Integer | 100 | Lower = higher priority (matches first) |

### Example Configurations

**Conservative Customer** (new to AI, learning mode):
```json
{
  "customer_id": 5,
  "action_type": null,
  "automate_below": 10.0,
  "inform_below": 30.0,
  "hold_minutes": 240,
  "auto_apply_on_expiry": false,
  "escalate_after_minutes": 120
}
```
→ Only trivial decisions auto-execute; most require review; long hold windows; no auto-apply.

**Aggressive Customer** (proven AI track record, production mode):
```json
{
  "customer_id": 12,
  "action_type": null,
  "automate_below": 40.0,
  "inform_below": 70.0,
  "hold_minutes": 30,
  "auto_apply_on_expiry": true,
  "escalate_after_minutes": 1440
}
```
→ Most decisions auto-execute; only major decisions get INSPECT; short review windows; auto-apply on expiry.

**Targeted Policy** (PO creation gets extra scrutiny):
```json
{
  "customer_id": 12,
  "action_type": "po_creation",
  "category": "procurement",
  "automate_below": 15.0,
  "inform_below": 35.0,
  "hold_minutes": 120,
  "auto_apply_on_expiry": false
}
```
→ Overrides the aggressive default for PO creation only.

---

## 13. Personas & Governance Experience

### VP Supply Chain (Executive)

**Primary view**: Governance Stats Dashboard
- Touchless Rate trend (target: >80%)
- Agent Score vs Human Override Rate by decision type
- Override Effectiveness Rate (% of overrides that were beneficial)
- Cost of INSPECT hold time (opportunity cost of delayed decisions)

**Key question**: "Is the AI earning trust? Should we relax thresholds?"

### S&OP Director (Tactical)

**Primary view**: GNN Directive Review tab
- Weekly S&OP GraphSAGE outputs → review policy parameters
- Override specific parameters (safety stock targets, OTIF floors)
- Review Execution tGNN directives before propagation to sites

**Key question**: "Are the network-level recommendations sensible for this week's demand pattern?"

### MPS Manager / Supply Planner (Operational)

**Primary view**: Governance Worklist (INSPECT decisions awaiting review)
- Sorted by: urgency (time to deadline), impact score, decision type
- Each item shows: title, explanation, impact breakdown, prediction interval, alternatives
- Actions: Accept, Reject, Override (with mandatory reason)
- Ask Why: drill into model attribution, counterfactuals, authority context

**Key question**: "Should I approve this PO for 10,000 units, or does the agent have it wrong?"

---

## 14. Implementation Status

| Component | Status | Files |
|-----------|--------|-------|
| **Layer 1: Authority Boundaries** | Implemented | `authority_boundaries.py` (12 roles, 50+ actions) |
| **Layer 2: Decision Governance** | Planned | `decision_governance.py`, `decision_governance_service.py` |
| **Layer 3: Conformal Prediction** | Implemented | `conformal_orchestrator.py`, 6 closed loops |
| **Layer 4: Override Effectiveness** | Implemented | `override_effectiveness_service.py`, Bayesian posteriors |
| **Layer 5: AAP** | Implemented | `authorization_protocol.py`, `authorization_service.py` |
| **GNN Directive Review** | Implemented | `gnn_directive_review.py`, `GNNDirectiveReview.jsx` |
| **Policy Envelope Override** | Implemented | `gnn_directive_review.py` (PolicyEnvelopeOverride model) |
| **Causal Matching** | Implemented | `causal_matching_service.py` (Tier 2 propensity matching) |
| **Context Explainability** | Implemented | `agent_context_explainer.py` (13 agent types × 3 levels) |
| **Governance Sweeper Jobs** | Planned | `governance_jobs.py` |
| **Governance Worklist API** | Planned | 5 endpoints on `site_agent.py` router |
| **Governance Frontend** | Planned | Worklist component + policy management |

---

## 15. Key Files Reference

### Models

| File | Contents |
|------|----------|
| `backend/app/models/agent_action.py` | `AgentAction`, `ActionMode`, `ActionCategory`, `ExecutionResult` |
| `backend/app/models/override_effectiveness.py` | `OverrideEffectivenessPosterior`, `CausalMatchPair` |
| `backend/app/models/gnn_directive_review.py` | `GNNDirectiveReview`, `PolicyEnvelopeOverride` |
| `backend/app/models/approval_template.py` | `ApprovalTemplate`, `ApprovalRequest`, `ApprovalAction` |
| `backend/app/models/decision_governance.py` | `DecisionGovernancePolicy` (planned) |

### Services

| File | Contents |
|------|----------|
| `backend/app/services/override_effectiveness_service.py` | Bayesian posteriors, TIER_MAP, training weights |
| `backend/app/services/causal_matching_service.py` | Propensity-score matching for Tier 2 |
| `backend/app/services/authorization_protocol.py` | AAP dataclasses, BalancedScorecard, AuthorizationRequest |
| `backend/app/services/authorization_service.py` | Authorization creation and resolution |
| `backend/app/services/escalation_formatter.py` | Tier 2→3 escalation with ranked alternatives |
| `backend/app/services/powell/authority_boundaries.py` | Per-agent action classification (12 roles) |
| `backend/app/services/powell/outcome_collector.py` | Outcome collection, site-window BSC, override delta |
| `backend/app/services/conformal_orchestrator.py` | Self-healing conformal prediction loops |
| `backend/app/services/agent_context_explainer.py` | Context-aware explanations for Ask Why |
| `backend/app/services/explanation_templates.py` | 39 Jinja2 templates (13 agents × 3 levels) |
| `backend/app/services/powell/gnn_orchestration_service.py` | GNN directive persistence with review tracking |
| `backend/app/services/decision_governance_service.py` | Impact scoring + mode assignment (planned) |
| `backend/app/services/powell/governance_jobs.py` | Auto-apply sweeper + escalation (planned) |

### Frontend

| File | Contents |
|------|----------|
| `frontend/src/components/admin/GNNDirectiveReview.jsx` | GNN directive review worklist and override UI |
| `frontend/src/pages/admin/GNNDashboard.jsx` | GNN training + Directive Review tab |
| `frontend/src/pages/admin/PowellDashboard.jsx` | Powell framework dashboard |
| `frontend/src/pages/admin/AuthorizationProtocolBoard.jsx` | AAP negotiation visualization |

### Documentation

| File | Contents |
|------|----------|
| `docs/AGENTIC_AUTHORIZATION_PROTOCOL.md` | Full AAP specification (14 sections + 3 appendices) |
| `docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md` | Bayesian methodology + mathematical appendix |
| `POWELL_APPROACH.md` | Powell SDAM framework + CDC relearning loop |
| `TRM_HIVE_ARCHITECTURE.md` | Multi-site coordination stack (4 layers) |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **AIIO** | Automate, Inform, Inspect, Override — the four modes of agent-human interaction |
| **AAP** | Agentic Authorization Protocol — cross-functional agent-to-agent decision governance |
| **Bayesian Posterior** | Beta(α,β) distribution tracking override quality per (user, trm_type) |
| **Balanced Scorecard** | Four-quadrant metric framework (Financial, Customer, Operational, Strategic) |
| **CDT** | Conformal Decision Theory — distribution-free risk bounds on every TRM decision |
| **CDC** | Change Data Capture — event-driven metric deviation detection |
| **Governance Policy** | Configurable per-customer rules for impact thresholds and hold windows |
| **Impact Score** | Composite 0-100 score (financial + scope + reversibility + confidence + override rate) |
| **Nonconformity Score** | How unusual a prediction context is vs training data |
| **Override Delta** | `human_actual_reward - agent_counterfactual_reward` |
| **Signal Strength** | How much a single observation updates the Bayesian posterior (tier-dependent) |
| **Tier** | Observability classification (1=analytical, 2=statistical, 3=prior-only) |
| **Touchless Rate** | % of decisions executed without human involvement |
| **Training Weight** | Sample weight in TRM replay buffer, derived from override posterior |

## Appendix B: API Endpoints

### Override Effectiveness

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/decision-metrics/override-posteriors` | GET | Per-user posterior summaries with 90% credible intervals |
| `/site-agent/gnn/override-effectiveness` | GET | GNN-scope override metrics |

### GNN Directive Review

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/site-agent/gnn/directives` | GET | List directives (filterable by status/scope/site) |
| `/site-agent/gnn/directives/{id}/review` | POST | Accept, override, or reject a directive |
| `/site-agent/gnn/directives/{id}/ask-why` | GET | Explain GNN directive reasoning |
| `/site-agent/gnn/policy-envelope/{id}/override-parameter` | POST | Override individual S&OP parameter |

### Decision Governance (Planned)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/site-agent/governance/pending` | GET | Decisions awaiting review |
| `/site-agent/governance/{action_id}/resolve` | POST | Approve, reject, or override held decision |
| `/site-agent/governance/policies` | GET | List governance policies |
| `/site-agent/governance/policies` | POST | Create/update governance policy |
| `/site-agent/governance/stats` | GET | Governance metrics |

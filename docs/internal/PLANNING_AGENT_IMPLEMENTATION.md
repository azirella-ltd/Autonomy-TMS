# Planning Agent Implementation Guide

> **Audience**: Engineers implementing the end-state Layer 2 tactical planning architecture.
> **Prerequisite reading**: [GNN_DECISION_ARCHITECTURE.md](GNN_DECISION_ARCHITECTURE.md)
> (end-state overview), [TRM_DECISION_ALGORITHMS.md](TRM_DECISION_ALGORITHMS.md) (TRM
> architecture), [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md) (training pipeline).

---

## What This Document Covers

The end-state Layer 2 architecture replaces the single "Network tGNN" with four
domain-specific planning GNNs, each paired with a domain TRM for in-cycle corrections
and a Claude Skill for cross-cycle contextual reasoning. It also adds a Planning Skill
Orchestrator (separate from the execution SkillOrchestrator) and an S&OP Adjustment Skill
at Layer 4.

This document specifies every new component, its implementation, how it is provisioned,
and the training pipeline required to bring it to production quality.

---

## Implementation Status

| Component | Status | Notes |
|---|---|---|
| Supply Planning GNN (Network tGNN rename) | ✅ Implemented | `supply_planning_tgnn_service.py` |
| Supply Planning SKILL.md | ✅ Implemented | Registered in `skills/__init__.py` |
| RCCP SKILL.md | ✅ Implemented | Registered in `skills/__init__.py` |
| Planning Skill Orchestrator | ✅ Implemented | `skills/planning_skill_orchestrator.py` |
| Demand Planning GNN | ✅ Implemented | `demand_planning_tgnn_service.py`, `models/gnn/demand_planning_tgnn.py` |
| Demand Adjustment TRM | ✅ Implemented | `powell/demand_adjustment_trm.py` — wired into GNNOrchestrationService Step 3.7 |
| Demand Planning SKILL.md | ✅ Implemented | `skills/demand_planning/SKILL.md` |
| Inventory Planning GNN | ✅ Implemented | `inventory_optimization_tgnn_service.py`, `models/gnn/inventory_optimization_tgnn.py` |
| Inventory Adjustment TRM | ✅ Implemented | `powell/inventory_adjustment_trm.py` — wired into GNNOrchestrationService Step 3.7 |
| Inventory Planning SKILL.md | ✅ Implemented | `skills/inventory_planning/SKILL.md` |
| Supply Adjustment TRM | ✅ Implemented | `powell/supply_adjustment_trm.py` — wired into GNNOrchestrationService Step 3.7 |
| RCCP GNN | ✅ Implemented | `models/gnn/rccp_gnn.py`, `powell/rccp_adjustment_trm.py` |
| RCCP Adjustment TRM | ✅ Implemented | `powell/rccp_adjustment_trm.py` |
| S&OP Adjustment Skill | ✅ Implemented | `skills/sop_adjustment/SKILL.md` |
| DB tables (4 planning TRM) | ✅ Implemented | `20260325_planning_trm_tables` migration |
| Outcome collection (4 planning TRM) | ✅ Implemented | `TRM_OUTCOME_DELAY` extended in `outcome_collector.py` |
| Decision Stream routing | ✅ Implemented | `DECISION_TYPE_TABLE_MAP` extended in `decision_stream_service.py` |

---

## Implementation Phases

### Phase 1 — Wire Existing Skills (1–2 days)

The `supply_planning/SKILL.md` and `rccp/SKILL.md` files exist but are not registered
in `skills/__init__.py` or invoked by any orchestrator. This phase wires them into a
minimal Planning Skill Orchestrator so they are callable.

**Files to create/modify**:
- `backend/app/services/skills/planning_skill_orchestrator.py` — new (see Phase 2 for full spec; Phase 1 creates a minimal version)
- `backend/app/services/skills/__init__.py` — add imports for `supply_planning`, `rccp`
- `backend/app/services/skills/supply_planning/__init__.py` — register skill
- `backend/app/services/skills/rccp/__init__.py` — register skill

**Migration**: None required — these skills have no DB tables yet.

**Test**: Call planning skill orchestrator with a dummy supply plan state; confirm
it invokes the Supply Planning SKILL.md and returns a SkillResult.

---

### Phase 2 — Planning Skill Orchestrator (3–5 days)

The execution `SkillOrchestrator` is tightly coupled to the TRM execution layer
(triggered by TRM conformal prediction confidence, routes by `trm_type`, persists to
`powell_*_decisions`). The Planning Skill Orchestrator is a parallel service with
different triggers, routing, and persistence targets.

#### Trigger Conditions (Planning Skill Orchestrator)

| Trigger | Domain | Threshold |
|---|---|---|
| Forecast MAPE > threshold for N consecutive periods | Demand | MAPE > 0.15, N = 3 |
| Plan fill rate shortfall | Supply | fill_rate < service_level_target × 0.90 |
| Inventory SS breach rate | Inventory | breach_rate > 0.05 over 7 days |
| RCCP returns `escalate_to_sop` | RCCP | Always |
| New email signal arrives (planning-relevant type) | Demand / Supply / Inventory | signal confidence > 0.70 |
| Human directive submitted (Layer 2 routing) | All | Always |
| GNN output conformal interval width > 0.40 | Domain-specific | Always |

#### Routing

```python
PLANNING_SKILL_ROUTES = {
    "demand":    "demand_planning",
    "inventory": "inventory_planning",
    "supply":    "supply_planning",
    "rccp":      "rccp",
}
```

#### Persistence Targets

Unlike the execution orchestrator (which writes to `powell_*_decisions`), the Planning
Skill Orchestrator writes adjustments to domain plan tables and marks them for human
review in the Decision Stream:

| Domain | Adjustment target table | Review flag |
|---|---|---|
| Demand | `forecast` (adj_quantity column) | `requires_human_review = True` if magnitude > 15% |
| Inventory | `inv_policy` (ss_quantity override) | Always flagged for S&OP review |
| Supply | `supply_plan` (adjusted quantities) | `requires_human_review = True` if affects frozen horizon |
| RCCP | `mps` quantities + capacity plan | Always flagged |

All planning skill decisions are also written to `decision_embeddings` with
`decision_source = 'planning_skill'` for RAG retrieval and future TRM training.

#### Key file

`backend/app/services/skills/planning_skill_orchestrator.py`

```python
class PlanningSkillOrchestrator:
    """
    Claude Skills exception handler for tactical planning layer (Layer 2).

    Parallel to SkillOrchestrator (execution layer) but invoked by planning
    services rather than SiteAgent. Triggered by plan deviation thresholds,
    new signal arrivals, human directives, and GNN low-confidence outputs.

    Writes adjustments to domain plan tables (forecast, supply_plan, inv_policy,
    mps) rather than powell_*_decisions.
    """

    def __init__(self, claude_client, decision_memory_service, tenant_id):
        ...

    async def execute(
        self,
        planning_domain: str,           # "demand" | "inventory" | "supply" | "rccp"
        gnn_output: dict,               # Raw GNN plan output
        trigger_reason: str,            # Why skill was invoked
        context: dict,                  # Email signals, directives, state
        tenant_id: int,
    ) -> PlanningSkillResult:
        ...
```

#### PlanningSkillResult dataclass

```python
@dataclass
class PlanningSkillResult:
    domain: str                          # "demand" | "inventory" | "supply" | "rccp"
    adjustment: dict                     # The plan modification
    confidence: float
    reasoning: str
    requires_human_review: bool
    pending_de_reconciliation: bool      # True if affects θ* indirectly
    affected_sites: list[str]
    affected_products: list[str]
    model_used: str
    token_cost: int
```

---

### Phase 3 — Demand Planning GNN + TRM + Skill (3–4 weeks)

#### 3.1 Demand Planning GNN

**Purpose**: Replace the statistical forecast pipeline (ETS + ARIMA + LightGBM) with
a graph-aware model that propagates demand signals through the product and site
hierarchies simultaneously. The statistical models become the BC oracle (they generate
training labels); the GNN learns to approximate their output at <5ms.

**Graph structure**: Bipartite graph — product hierarchy nodes (Category → Family →
Group → SKU) × site hierarchy nodes (Company → Region → Country → Site). Edges connect
each SKU to the sites where it is stocked and sold.

**Node features (SKU nodes, 16 dims)**:
```
0:  demand_last_4w_avg        — rolling 4-week average demand
1:  demand_last_4w_cv         — coefficient of variation (volatility)
2:  demand_last_52w_avg       — long-run average (seasonality baseline)
3:  week_of_year_sin          — sin encoding of week (seasonality)
4:  week_of_year_cos          — cos encoding
5:  lifecycle_stage           — 0=new, 0.33=growth, 0.67=mature, 1=end-of-life
6:  promotion_flag            — 1 if active promotion this period
7:  npi_flag                  — 1 if new product introduction active
8:  competitor_event_flag     — 1 if competitor disruption signal active
9:  forecast_bias_last_8w     — rolling bias (positive = consistently under)
10: forecast_mape_last_8w     — rolling MAPE
11: email_signal_demand_adj   — most recent demand signal adjustment factor (1.0 = none)
12: email_signal_confidence   — confidence of most recent signal (0 = no signal)
13: price_index               — relative price vs. category average
14: cannibalization_flag      — 1 if substitute product recently launched
15: criticality_score         — θ*.service_level_target mapped to [0,1]
```

**Node features (site nodes, 8 dims)**:
```
0:  on_hand_weeks_cover       — current inventory / avg weekly demand
1:  safety_stock_weeks_cover  — SS target / avg weekly demand
2:  site_type_encoded         — 0=retailer, 0.33=DC, 0.67=manufacturer, 1=supplier
3:  region_demand_index       — regional demand multiplier vs. national average
4:  channel_mix_online        — fraction of demand via online channel
5:  service_level_actual_4w   — actual fill rate last 4 weeks
6:  backlog_flag              — 1 if active backlog at this site
7:  latitude_normalised       — geographic encoding (cold/warm seasonality proxy)
```

**Output per SKU-site pair**:
```python
DemandPlanOutput(
    p10_forecast: float,      # 10th percentile weekly demand
    p50_forecast: float,      # Median (point estimate)
    p90_forecast: float,      # 90th percentile
    confidence: float,        # Model confidence [0, 1]
    horizon_weeks: int,       # Planning horizon covered
)
```

**Oracle**: Run ETS + ARIMA + SARIMA ensemble on 104 weeks of historical demand.
ForecastAdjustmentTRM corrections applied to oracle labels where available (the TRM's
historical adjustments are part of the "correct" answer the GNN learns). Generate
(graph_state, demand_plan) pairs across N=10,000+ synthetic scenarios using the
digital twin's demand simulation.

**Training**:
- Phase 1 (BC): Supervised on (graph_state, oracle_demand_plan) pairs. Target:
  CRPS < 0.15 on validation set.
- Phase 2 (RL/PPO): Fine-tune on actual demand outcomes. Reward: negative CRPS
  (lower is better) measured against realised demand.

**Key file**: `backend/app/models/gnn/demand_planning_gnn.py`
**Training script**: `backend/scripts/training/train_demand_gnn.py`
**Provisioning step**: `lgbm_forecast` (existing step — GNN replaces LightGBM)

#### 3.2 Demand Adjustment TRM

**Scope**: In-cycle corrections to the Demand Planning GNN output. Handles learnable
deviation patterns: persistent forecast bias for specific SKU-site combinations,
known seasonal effects the GNN underweights, real-time demand sensing corrections.

**State vector (12 dims)**:
```
0:  gnn_p50_forecast          — GNN point estimate for this period
1:  gnn_confidence            — GNN output confidence
2:  recent_bias               — actual - forecast over last 8 periods (normalised)
3:  recent_mape               — rolling MAPE last 8 periods
4:  inventory_weeks_cover     — current cover (high cover → demand correction less urgent)
5:  backlog_flag              — 1 if active backlog (demand > supply)
6:  email_signal_adj_factor   — most recent demand signal adjustment
7:  email_signal_age_days     — days since signal (decay)
8:  lifecycle_stage           — 0=new, 0.33=growth, 0.67=mature, 1=end-of-life
9:  promotion_active          — 1 if active promotion
10: week_of_year_normalised   — seasonality position
11: demand_trend_4w           — (avg demand weeks 1-2) / (avg demand weeks 3-4) - 1
```

**Decision**: `demand_adjustment_factor` ∈ [0.70, 1.50] applied to GNN p50 forecast.
Confidence ∈ [0, 1]. Reasoning string.

**Reward**: Negative forecast error (MAPE improvement) vs. unadjusted GNN output,
measured over next 4 weeks. Reward = `(unadjusted_MAPE - adjusted_MAPE) / unadjusted_MAPE`.

**Urgency formula**: `urgency = min(1.0, recent_mape × 3.0 + |recent_bias| × 2.0)`

**Likelihood**: TRM model confidence head. CDT overlay: `1 - risk_bound`.

**Training data requirement**: 500 (state, adjustment, 4-week-outcome) triples for
BC warm-start. 2,000+ for RL fine-tuning.

**Key file**: `backend/app/services/powell/demand_adjustment_trm.py`
**DB table**: `powell_demand_adjustment_decisions`

#### 3.3 Demand Planning SKILL.md

**Purpose**: Handle novel demand situations outside the TRM training distribution.
Invoked by Planning Skill Orchestrator when: MAPE > 0.20 AND TRM confidence < 0.50,
OR new email signal with demand implication arrives, OR human directive specifies
demand change.

Create file: `backend/app/services/skills/demand_planning/SKILL.md`

Key rules to encode:
- NPI demand ramp: if `npi_flag=1` and history < 12 weeks, apply category-average
  seasonal pattern scaled by launch trajectory
- Competitor discontinuation: if email signal indicates competitor product discontinued,
  apply +15–40% demand uplift (range depends on market share estimate)
- End-of-life transition: if `lifecycle_stage > 0.85`, apply demand decay curve
  (exponential with 0.85 decay factor per period)
- Promotion uplift: if `promotion_flag=1` with no historical precedent, apply
  category-average promotion uplift (typically 1.3–2.0×)
- Requires human review if total adjustment > 30% of current forecast

---

### Phase 4 — Inventory Planning GNN + TRM + Skill (2–3 weeks)

#### 4.1 Inventory Planning GNN

**Purpose**: Replace the rule-based `inventory_target_calculator.py` safety stock
calculation with a graph-aware model that simultaneously optimises SS targets across
the supply network, accounting for upstream lead time variance and downstream demand
propagation. The existing 8-policy calculator becomes the BC oracle.

**Graph structure**: Supply chain DAG (same topology as Supply Planning GNN).
Edges represent supply relationships (supplier → DC → retail).

**Node features (18 dims)**:
```
0:  avg_weekly_demand         — planning-horizon average
1:  demand_cv                 — coefficient of variation
2:  avg_lead_time_weeks       — mean replenishment lead time
3:  lead_time_cv              — lead time variability
4:  supplier_reliability      — on-time delivery rate [0,1]
5:  current_ss_weeks_cover    — current SS / avg weekly demand
6:  stockout_rate_4w          — stockouts per period last 4 weeks
7:  excess_inventory_flag     — 1 if on_hand > 3 × SS target
8:  unit_cost                 — product unit cost (normalised)
9:  holding_cost_rate         — annual holding rate [0,1]
10: stockout_cost_per_unit    — penalty for stockout (normalised)
11: service_level_target      — from θ*.service_level_target
12: ss_multiplier             — from θ*.safety_stock_multiplier
13: inv_policy_type_encoded   — 0=abs_level, 0.14=doc_dem, ... 1.0=econ_optimal
14: network_centrality        — graph centrality score (risk propagation importance)
15: upstream_risk_score       — aggregated upstream supplier risk
16: downstream_demand_volatility — demand volatility at sites this node serves
17: oee_actual                — site OEE (affects production fill rate for manufacturers)
```

**Output per product-site pair**:
```python
InventoryTargetOutput(
    ss_quantity: float,          # Safety stock quantity (units)
    reorder_point: float,        # Reorder point (units)
    order_up_to: float,          # Order-up-to level (units)
    recommended_policy: str,     # Which of 8 policy types is most appropriate
    confidence: float,
)
```

**Oracle**: Run all 8 policy types from `inventory_target_calculator.py` on each
synthetic scenario. Select the policy with minimum expected cost (holding + stockout)
as the training label. Generate N=5,000+ (graph_state, optimal_targets) pairs via
Monte Carlo DDLT simulation.

**Training**:
- Phase 1 (BC): Supervised on oracle labels. Target: < 5% deviation from oracle
  optimal SS quantity on validation set.
- Phase 2 (RL): Reward = negative (holding_cost + stockout_cost) measured over 4 weeks
  against realised outcomes.

**Key file**: `backend/app/models/gnn/inventory_planning_gnn.py`
**Training script**: `backend/scripts/training/train_inventory_gnn.py`
**Provisioning step**: `inventory_tgnn` (existing step in 14-step pipeline)

#### 4.2 Inventory Adjustment TRM

**Scope**: In-cycle corrections to inventory targets when the GNN output is suboptimal
given current conditions. Handles: persistent stockout patterns the GNN underweights,
supplier reliability degradation, OEE changes affecting production fill rate.

**State vector (10 dims)**:
```
0:  gnn_ss_quantity           — GNN safety stock recommendation
1:  gnn_confidence
2:  actual_stockout_rate_4w   — recent stockout frequency
3:  supplier_reliability_trend — reliability change vs. 8-week average
4:  oee_trend                 — OEE change vs. 4-week average
5:  on_hand_weeks_cover       — current cover (vs. target)
6:  lead_time_trend           — LT change vs. 8-week average
7:  demand_cv_trend           — demand variability change
8:  holding_cost_pressure     — 1 if on_hand > 2 × SS (capital pressure)
9:  ss_multiplier             — current θ*.safety_stock_multiplier
```

**Decision**: `ss_adjustment_delta` ∈ [−0.30, +0.50] applied to GNN ss_quantity
as an additive fractional delta. Confidence ∈ [0, 1].

**Reward**: Negative (holding_cost + stockout_cost) improvement vs. unadjusted GNN
target, measured over 2 weeks.

**Urgency formula**: `urgency = actual_stockout_rate_4w × 3.0 + |supplier_reliability_trend| × 2.0`

**Key file**: `backend/app/services/powell/inventory_adjustment_trm.py`
**DB table**: `powell_inventory_adjustment_decisions`

#### 4.3 Inventory Planning SKILL.md

**Purpose**: Handle novel inventory situations: new risk categories (e.g. geopolitical
disruption requiring strategic stockpile), executive capital constraints on inventory
investment, new supplier onboarding with no reliability history.

Create file: `backend/app/services/skills/inventory_planning/SKILL.md`

Key rules to encode:
- Strategic buffer: if directive indicates geopolitical/supply risk, recommend
  temporary SS increase to N weeks cover (N specified in directive)
- Capital constraint: if directive specifies WC reduction target, identify which
  SKU-sites have lowest stockout risk and reduce their SS first (prioritise by
  `stockout_cost_per_unit × demand_cv`)
- New supplier (< 12 weeks history): apply 1.5× SS multiplier until 24-week
  reliability track record established
- Product rationalisation: if NPI is cannibalising existing SKU, begin SS draw-down
  on existing SKU while NPI ramps up
- Requires human review for SS changes > 40% or affecting > 10% of total WC

---

### Phase 5 — Supply Adjustment TRM + RCCP GNN + RCCP TRM (3–4 weeks)

#### 5.1 Supply Adjustment TRM

The Supply Planning GNN (current Network tGNN) is already implemented. This phase
adds the in-cycle adjustment TRM that pairs with it.

**Scope**: Real-time corrections to the supply plan when new information arrives
between daily GNN runs: RCCP infeasibility flag, supplier confirmation changes,
PO acknowledgement deviations.

**State vector (11 dims)**:
```
0:  gnn_supply_plan_qty       — GNN planned quantity for this product-site-week
1:  gnn_confidence
2:  rccp_feasibility_flag     — 1 if RCCP returned infeasible for this site
3:  supplier_confirmation_rate — confirmed POs / planned POs (last 4 weeks)
4:  open_po_coverage          — open PO quantity / planned requirement
5:  lead_time_deviation       — actual LT vs. planned LT last 4 deliveries
6:  available_to_promise      — current ATP at source site
7:  exception_probability     — from tGNNSiteDirective (upstream site risk)
8:  demand_plan_change        — fractional change from Demand GNN this cycle
9:  inventory_target_change   — fractional change from Inventory GNN this cycle
10: frozen_horizon_flag       — 1 if order_date within 2 weeks
```

**Decision**: `supply_plan_adjustment_factor` ∈ [0.80, 1.30]. If
`frozen_horizon_flag=1`, decision is locked (no adjustment).

**Reward**: Supply plan execution rate (actual receipt / planned receipt) over next
7 days.

**Urgency formula**: `urgency = rccp_feasibility_flag × 0.5 + (1 - supplier_confirmation_rate) × 0.3 + |lead_time_deviation| × 0.2`

**Key file**: `backend/app/services/powell/supply_adjustment_trm.py`
**DB table**: `powell_supply_adjustment_decisions`

#### 5.2 RCCP GNN

**Purpose**: Replace the rule-based RCCP SKILL.md logic with a trained GNN that
validates MPS feasibility across the resource network, learns site-specific capacity
patterns, and recommends MPS adjustments. The RCCP SKILL.md rules (CPOF / BoC /
Resource Profile) become the BC oracle.

**Graph structure**: Resource network — nodes are work centres, production lines,
and shared utilities. Edges represent resource sharing constraints (e.g. a work centre
feeds two production lines; a shared utility constrains multiple lines simultaneously).

**Node features (work centre / line, 14 dims)**:
```
0:  required_hours_week       — MPS demand for this resource this week
1:  available_hours_week      — regular + overtime capacity
2:  current_utilisation       — 4-week rolling actual utilisation
3:  oee_current               — current OEE
4:  oee_sustainable_max       — 0.85 default (configured per site)
5:  changeover_hours_week     — estimated setup/changeover time from MPS mix
6:  distinct_products_week    — number of different products scheduled
7:  green_runner_fraction     — fraction of volume from top-6% SKUs (Glenday)
8:  overtime_cost_per_hour    — labour cost premium for overtime
9:  subcontract_available     — 1 if subcontracting option exists for this resource
10: subcontract_cost_premium  — cost premium vs. internal (normalised)
11: maintenance_due_flag      — 1 if preventive maintenance scheduled within 2 weeks
12: breakdown_probability     — predicted breakdown probability from OEE trend
13: demand_variability_cv     — downstream demand CV (need for capacity buffer)
```

**Output per resource per week**:
```python
RCCPOutput(
    feasibility: str,           # "feasible" | "warning" | "overloaded" | "escalate_to_sop"
    utilisation_pct: float,     # Load / capacity
    recommended_action: str,    # "none" | "overtime" | "level_mps" | "subcontract" | "escalate"
    mps_adjustment_qty: float,  # Quantity to shift (negative = defer, positive = pull forward)
    mps_adjustment_week: int,   # Target week for shifted quantity
    overtime_units: float,      # Additional capacity hours recommended
    confidence: float,
)
```

**Oracle**: Apply RCCP SKILL.md decision rules (CPOF for simple cases, BoC for
standard, Resource Profile for complex) to generate (resource_graph, feasibility_action)
labels. Generate N=3,000+ scenarios via digital twin capacity simulation (vary MPS
mix, demand variability, OEE, maintenance schedules).

**Training**:
- Phase 1 (BC): Supervised on SKILL.md oracle labels. Target: > 90% agreement
  with oracle on feasibility verdict.
- Phase 2 (RL): Reward = negative (overtime_cost + subcontract_cost + backlog_cost)
  measured over 2 weeks.

**Key file**: `backend/app/models/gnn/rccp_gnn.py`
**Training script**: `backend/scripts/training/train_rccp_gnn.py`
**Provisioning step**: `rccp_validation` (existing step in 14-step pipeline — GNN
replaces rule-based SKILL.md logic; SKILL.md becomes oracle only)

#### 5.3 RCCP Adjustment TRM

**Scope**: In-cycle corrections when the RCCP GNN output needs real-time adjustment
for conditions not captured in the last daily run: unplanned equipment downtime, rush
overtime authorisation, maintenance schedule change.

**State vector (9 dims)**:
```
0:  gnn_utilisation_pct       — RCCP GNN resource load estimate
1:  gnn_confidence
2:  oee_deviation             — actual OEE vs. planned OEE this cycle
3:  unplanned_downtime_hrs    — unplanned downtime in last 24h
4:  rush_order_flag           — 1 if AAP rush order authorization received
5:  overtime_cost_budget_used — fraction of period overtime budget consumed
6:  maintenance_emergency_flag — 1 if MaintenanceSchedulingTRM flagged critical
7:  shift_extension_authorized — 1 if HR/Finance AAP authorization approved
8:  chronic_overload_weeks    — consecutive weeks of overload (escalation trigger)
```

**Decision**:
- `overtime_delta_hours` ∈ [0, max_overtime_budget]
- `mps_defer_flag` ∈ {True, False} (defer lowest-priority MO to next week)
- `escalate_to_sop` ∈ {True, False} (trigger EscalationArbiter strategic escalation)

**Reward**: Negative (overtime_cost + backlog_cost + escalation_cost) over 2 weeks.

**Urgency formula**: `urgency = min(1.0, chronic_overload_weeks × 0.3 + unplanned_downtime_hrs / 8.0 × 0.4 + rush_order_flag × 0.3)`

**Key file**: `backend/app/services/powell/rccp_adjustment_trm.py`
**DB table**: `powell_rccp_adjustment_decisions`

---

### Phase 6 — S&OP Adjustment Skill (1–2 days)

**Purpose**: Apply bounded real-time corrections to θ* between weekly DE runs for
time-sensitive signals that cannot wait until Sunday 04:00.

**Trigger**: PlanningSkillOrchestrator routes to this skill when:
- Email signal with material supply/demand implication arrives (confidence > 0.70)
- Human directive specifies θ* parameter change directly
- RCCP returns `escalate_to_sop` for a chronic overload

**Constraints** (must be respected by skill):
- Maximum adjustment per parameter per run: ±20% of current θ* value
- Cannot simultaneously raise `service_level_target` AND raise `safety_stock_multiplier`
  at the same sites (would create plan infeasibility)
- All adjustments marked `pending_de_reconciliation = True`
- All adjustments surfaced in Decision Stream for S&OP meeting review

**Output**: Modified `powell_policy_parameters` rows with `pending_de_reconciliation=True`
and `adjustment_source='sop_skill'`.

**Create file**: `backend/app/services/skills/sop_adjustment/SKILL.md`

Key rules to encode:
- Supplier capacity reduction (email signal): adjust `sourcing_split` toward
  secondary suppliers by (1 - confirmed_capacity_fraction); raise `safety_stock_multiplier`
  by 0.1–0.3 depending on reduction magnitude
- Demand uplift directive: raise `service_level_target` by delta if on-hand cover
  allows; do not raise if on-hand < 2 weeks cover (would create impossible target)
- Chronic RCCP overload: reduce `order_up_to_days` for affected site by 10–20%
  (level the load); flag for human capacity investment decision
- NPI launch acceleration: raise `order_up_to_days` for NPI and substitute SKUs;
  lower for cannibalised SKUs; keep combined inventory flat
- Requires human review for all S&OP skill adjustments (always — this is strategic)

---

## Planning TRMs: Architectural Differences from Execution TRMs

The 11 execution TRMs (ATP, PO Creation, etc.) output **direct orders** — they decide
what action to take (place order, release MO, etc.). The 4 planning TRMs output
**plan modifiers** — they adjust the output of a GNN rather than issuing an order.

| Property | Execution TRM | Planning TRM |
|---|---|---|
| Output type | Action (order quantity, timing, routing) | Modifier (adjustment factor, delta, flag) |
| Downstream effect | Immediate operational change | Changes the plan that execution TRMs then execute |
| Feedback horizon | 4h – 7 days | 1 – 4 weeks |
| State dimensions | 8–18 dims (inventory, orders, pipeline) | 9–12 dims (plan accuracy, deviations, trends) |
| Urgency range | 0.0–1.0 (tactical escalation) | 0.0–0.6 (planning adjustment, not emergency) |
| Decision frequency | Per cycle (potentially every hour) | Once per daily planning run |
| TRM architecture | Same 7M-param transformer, 3-step recursive | Same architecture (same code) |

The neural architecture (Samsung TRM: 2-layer transformer, 3-step recursive refinement,
post-normalisation) is identical for planning TRMs. Only the state encoding, decision
head, and reward function differ.

---

## Provisioning Integration

The 14-step provisioning pipeline already has placeholders for domain GNNs:

```
warm_start → sop_graphsage → cfa_optimization → lgbm_forecast →
demand_tgnn → supply_tgnn → inventory_tgnn → trm_training →
supply_plan → rccp_validation → decision_seed → site_tgnn →
conformal → briefing
```

Mapping of pipeline steps to new components:

| Pipeline step | Current behaviour | End-state behaviour |
|---|---|---|
| `lgbm_forecast` | Runs LightGBM demand forecast | Trains Demand Planning GNN (GNN replaces LGB) |
| `demand_tgnn` | Placeholder | Demand Planning GNN BC training + Demand Adjustment TRM BC warm-start |
| `supply_tgnn` | Trains Network tGNN (existing) | Supply Planning GNN (rename + Supply Adjustment TRM BC warm-start) |
| `inventory_tgnn` | Placeholder | Inventory Planning GNN BC training + Inventory Adjustment TRM BC warm-start |
| `trm_training` | Trains 11 execution TRMs | Extends to include 4 planning TRMs |
| `rccp_validation` | Rule-based RCCP check | RCCP GNN training + RCCP Adjustment TRM BC warm-start |
| `conformal` | Conformal calibration for demand + supply | Extends to all 4 domain GNNs + 4 planning TRMs |

No new provisioning steps are needed — existing steps are extended. The
`ProvisioningService.run_step()` implementation for each step needs updating to
invoke the new training scripts.

---

## Training Pipeline and Sequence

### Dependency Order

The domain GNNs must be trained in dependency order because each GNN's output is
an input to the next:

```
1. Demand Planning GNN
   (no dependency — uses historical demand + static features only)
   ↓ outputs: consensus demand plan
2. Inventory Planning GNN
   (depends on: demand plan from step 1)
   ↓ outputs: SS targets, reorder points
3. Supply Planning GNN
   (depends on: demand plan + inventory targets from steps 1–2)
   ↓ outputs: supply plan (MPS quantities)
4. RCCP GNN
   (depends on: MPS quantities from step 3)
   ↓ outputs: feasibility verdict + MPS adjustments
```

Planning TRMs for each domain can begin BC warm-start as soon as the corresponding
GNN has generated its first set of plan-vs-actual deviation records (minimum 500).

### Digital Twin Data Generation

The platform's stochastic simulation engine (SimPy) generates training data for all
four domain GNNs:

| GNN | Simulation type | Variables sampled | N scenarios |
|---|---|---|---|
| Demand | Demand pattern simulation | Demand level, CV, seasonality, lifecycle stage, promotion effects | 10,000+ |
| Inventory | Monte Carlo DDLT | Lead time (LogLogistic), demand (Normal), OEE, supplier reliability | 5,000+ |
| Supply | Network flow simulation (existing) | Supply constraints, sourcing priorities, lead times | 5,000+ |
| RCCP | Capacity utilisation simulation | OEE, changeover mix, demand variability, maintenance schedules | 3,000+ |

All simulations use `training_distributions.py` `D` methods for stochastic variables
to ensure cross-tier distribution consistency.

### BC Warm-Start Data Requirements

| Component | Minimum for BC | Minimum for RL | Source |
|---|---|---|---|
| Demand Planning GNN | 10,000 scenarios | 5,000 real outcomes | Digital twin + historical |
| Demand Adjustment TRM | 500 (state, adjustment, outcome) | 2,000 | Historical forecast errors + ForecastAdjustmentTRM history |
| Inventory Planning GNN | 5,000 scenarios | 3,000 real outcomes | Monte Carlo DDLT + historical |
| Inventory Adjustment TRM | 500 | 2,000 | Historical SS policy changes + outcomes |
| Supply Adjustment TRM | 500 | 2,000 | Historical supply plan deviations + outcomes |
| RCCP GNN | 3,000 scenarios | 2,000 real outcomes | Capacity simulation + historical |
| RCCP Adjustment TRM | 500 | 2,000 | Historical RCCP resolutions |

### Conformal Calibration

After each domain GNN and planning TRM completes Phase 2 (RL), conformal prediction
calibration runs via `ConformalOrchestrator`:

- **Demand GNN**: Calibrate CRPS-based prediction intervals on held-out demand history
- **Inventory GNN**: Calibrate SS quantity prediction intervals on held-out DDLT simulations
- **Supply GNN**: Calibrate demand_satisfaction intervals (existing, extend scope)
- **RCCP GNN**: Calibrate feasibility probability on held-out capacity scenarios

Calibration sets must not overlap with training sets. Use the most recent 20% of
historical data as calibration set, older 80% for training.

---

## Database Schema Changes

### New tables required

```sql
-- Demand Adjustment TRM decisions
CREATE TABLE powell_demand_adjustment_decisions (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    config_id       INTEGER NOT NULL,
    product_id      VARCHAR NOT NULL,
    site_id         VARCHAR NOT NULL,
    period_week     DATE NOT NULL,
    gnn_p50_forecast NUMERIC,
    adjustment_factor NUMERIC,           -- [0.70, 1.50]
    adjusted_forecast NUMERIC,
    confidence      NUMERIC,
    urgency         NUMERIC,
    reasoning       TEXT,
    decision_source VARCHAR DEFAULT 'demand_adjustment_trm',
    -- Outcome columns (populated by OutcomeCollector at +4 weeks)
    actual_demand   NUMERIC,
    mape_before     NUMERIC,
    mape_after      NUMERIC,
    outcome_collected_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Inventory Adjustment TRM decisions
CREATE TABLE powell_inventory_adjustment_decisions (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    config_id       INTEGER NOT NULL,
    product_id      VARCHAR NOT NULL,
    site_id         VARCHAR NOT NULL,
    gnn_ss_quantity NUMERIC,
    ss_adjustment_delta NUMERIC,         -- [-0.30, +0.50]
    adjusted_ss_quantity NUMERIC,
    confidence      NUMERIC,
    urgency         NUMERIC,
    reasoning       TEXT,
    decision_source VARCHAR DEFAULT 'inventory_adjustment_trm',
    -- Outcome columns (populated at +2 weeks)
    actual_stockout_rate NUMERIC,
    holding_cost_actual  NUMERIC,
    stockout_cost_actual NUMERIC,
    outcome_collected_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Supply Adjustment TRM decisions
CREATE TABLE powell_supply_adjustment_decisions (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    config_id       INTEGER NOT NULL,
    product_id      VARCHAR NOT NULL,
    site_id         VARCHAR NOT NULL,
    period_week     DATE NOT NULL,
    gnn_supply_qty  NUMERIC,
    adjustment_factor NUMERIC,           -- [0.80, 1.30]
    adjusted_supply_qty NUMERIC,
    confidence      NUMERIC,
    urgency         NUMERIC,
    reasoning       TEXT,
    decision_source VARCHAR DEFAULT 'supply_adjustment_trm',
    -- Outcome columns (populated at +7 days)
    actual_receipt_qty   NUMERIC,
    execution_rate       NUMERIC,
    outcome_collected_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- RCCP Adjustment TRM decisions
CREATE TABLE powell_rccp_adjustment_decisions (
    id              SERIAL PRIMARY KEY,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
    config_id       INTEGER NOT NULL,
    site_id         VARCHAR NOT NULL,
    resource_id     VARCHAR NOT NULL,
    period_week     DATE NOT NULL,
    gnn_utilisation_pct  NUMERIC,
    overtime_delta_hours NUMERIC,
    mps_defer_flag  BOOLEAN,
    escalate_to_sop BOOLEAN,
    confidence      NUMERIC,
    urgency         NUMERIC,
    reasoning       TEXT,
    decision_source VARCHAR DEFAULT 'rccp_adjustment_trm',
    -- Outcome columns (populated at +2 weeks)
    actual_utilisation_pct NUMERIC,
    overtime_cost_actual   NUMERIC,
    backlog_units_actual   NUMERIC,
    outcome_collected_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

### Alembic migration

Create `backend/migrations/versions/YYYYMMDD_planning_trm_tables.py` covering all
four tables above. Name: `planning_trm_decision_tables`.

### OutcomeCollector extensions

`OutcomeCollectorService.collect_trm_outcomes()` in `outcome_collector.py` must be
extended to process all four new planning TRM tables. Feedback horizons:

| Table | Feedback horizon | Outcome metrics |
|---|---|---|
| `powell_demand_adjustment_decisions` | 4 weeks | `actual_demand`, `mape_before`, `mape_after` |
| `powell_inventory_adjustment_decisions` | 2 weeks | `actual_stockout_rate`, `holding_cost_actual`, `stockout_cost_actual` |
| `powell_supply_adjustment_decisions` | 7 days | `actual_receipt_qty`, `execution_rate` |
| `powell_rccp_adjustment_decisions` | 2 weeks | `actual_utilisation_pct`, `overtime_cost_actual`, `backlog_units_actual` |

### `DECISION_TYPE_TABLE_MAP` update

In `decision_stream_service.py`, add the four new planning decision types:

```python
DECISION_TYPE_TABLE_MAP = {
    # ... existing 11 execution TRM types ...
    "demand_adjustment":    "powell_demand_adjustment_decisions",
    "inventory_adjustment": "powell_inventory_adjustment_decisions",
    "supply_adjustment":    "powell_supply_adjustment_decisions",
    "rccp_adjustment":      "powell_rccp_adjustment_decisions",
}
```

---

## Migration Path from Current Architecture

### What stays the same

- All 11 execution TRMs: no change
- Site tGNN: no change
- S&OP GraphSAGE: no change (S&OP Adjustment Skill adds to it, does not replace it)
- `powell_policy_parameters` table: unchanged schema
- All existing provisioning steps: extended, not replaced

### What changes

- "Network tGNN" is renamed "Supply Planning GNN" in code comments, variable names,
  and API responses. No functional change.
- The `supply_tgnn` provisioning step wires to the same model under its new name.
- The Planning Skill Orchestrator is a new service; the existing execution
  `SkillOrchestrator` is unchanged.

### Rollout order

1. Rename Network tGNN → Supply Planning GNN (comments + API labels only)
2. Phase 1: Wire supply_planning and rccp skills into minimal Planning Skill Orchestrator
3. Phase 2: Full Planning Skill Orchestrator with all triggers and persistence
4. Phase 3: Demand Planning GNN + TRM + Skill
5. Phase 4: Inventory Planning GNN + TRM + Skill
6. Phase 5: Supply Adjustment TRM + RCCP GNN + RCCP Adjustment TRM
7. Phase 6: S&OP Adjustment Skill

Each phase is independently deployable. Phases 3–5 can be deployed behind a feature
flag (`ENABLE_DOMAIN_PLANNING_GNNS=false` default) while the existing Supply Planning
GNN continues to run.

---

## See Also

- [GNN_DECISION_ARCHITECTURE.md](GNN_DECISION_ARCHITECTURE.md) — End-state architecture overview
- [TRM_DECISION_ALGORITHMS.md](TRM_DECISION_ALGORITHMS.md) — TRM architecture and heuristic algorithms
- [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md) — Training pipeline and oracle patterns
- [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) — Execution-layer TRM coordination
- [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md) — Vertical escalation between layers

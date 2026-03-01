# Autonomy: Technical Overview

## How the Architecture Delivers the Operating Model

*Companion to [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md). That document describes what changes for the organization, operations, and workforce. This document describes how the technology layers make it possible.*

**Version**: 2.0
**Date**: March 1, 2026

---

## The Core Architectural Idea

The executive summary describes a system where routine planning decisions execute autonomously, disruptions are handled in minutes instead of days, and every human override teaches the system something new. Delivering this requires solving two hard coordination problems simultaneously:

1. **Vertical coordination**: Aligning decisions across planning horizons — strategic policy (months), tactical allocation (days), and operational execution (milliseconds) — so that a safety stock target set at the S&OP level correctly constrains a purchase order placed at the execution level.

2. **Horizontal coordination**: Aligning decisions across the supply chain network — so that a shortage signal at a distribution center propagates upstream to the factory, triggers a rebalancing decision at a sister DC, and adjusts ATP promises to customers downstream — all without any single agent having a global view.

The architecture solves both problems through a layered agent hierarchy (vertical) and a biologically-inspired signal propagation system (horizontal), unified by Warren Powell's Sequential Decision Analytics framework.

---

## Part 1: The Vertical Stack — From Policy to Execution

### Four Layers, Four Time Horizons

The decision architecture is a stack of four layers, each operating at a different time horizon and producing outputs that constrain the layer below. The key insight from the Powell framework is that multi-level planning is *nested optimization* — each layer optimizes within the bounds set by the layer above.

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 4: S&OP GraphSAGE                                │
│  Horizon: Weeks to months   │   Cadence: Weekly          │
│  Powell class: CFA (Cost Function Approximation)        │
│  Output: Policy parameters θ — safety stock multipliers, │
│          criticality scores, resilience ratings          │
│  Scope: Entire network                                  │
└──────────────────────┬──────────────────────────────────┘
                       │ θ parameters + 64-dim structural embeddings
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 3: Execution Temporal GNN                         │
│  Horizon: Days              │   Cadence: Daily            │
│  Powell class: CFA/VFA bridge                           │
│  Output: Per-site directives — demand forecasts,         │
│          exception probabilities, priority allocations    │
│  Scope: Network-wide, but outputs are per-site          │
└──────────────────────┬──────────────────────────────────┘
                       │ tGNNSiteDirective + inter-hive signals
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: TRM Hive (11 Narrow Decision Agents)           │
│  Horizon: Seconds           │   Cadence: Per-decision     │
│  Powell class: VFA (Value Function Approximation)       │
│  Output: Individual decisions — fulfill, order, release, │
│          expedite, hold, rebalance                       │
│  Scope: Single site                                     │
└──────────────────────┬──────────────────────────────────┘
                       │ Learned adjustments to engine baseline
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 0: Deterministic Engines (11 Specialized Engines) │
│  Horizon: Immediate         │   Cadence: Always            │
│  Output: Constraint-validated baseline decisions         │
│  Scope: Single site, single decision type               │
│  Property: 100% auditable, zero learned parameters      │
└─────────────────────────────────────────────────────────┘
```

### What Each Layer Does

**Layer 4 — S&OP GraphSAGE** analyzes the structural properties of the supply chain network. It looks at the topology — which sites are critical chokepoints, where sourcing is dangerously concentrated, which parts of the network are fragile — and produces *policy parameters* that shape how the layers below behave. For example, a site identified as a critical bottleneck might receive a safety stock multiplier of 1.4x, meaning the execution layers will maintain 40% more buffer inventory there than the default policy would suggest.

This layer uses GraphSAGE (a graph neural network designed for large networks) because the analysis is fundamentally about *network structure* — the answer to "how critical is this DC?" depends not just on the DC itself but on its position relative to every other node, the number of alternative paths, and the concentration of demand it serves. The embeddings it produces (64-dimensional vectors encoding each site's structural context) are cached and consumed by Layer 3.

**Update cadence**: Weekly or monthly. Network structure changes slowly.

**Layer 3 — Execution Temporal GNN** combines the structural embeddings from Layer 4 with real-time transactional data — current inventory levels, order backlogs, shipments in transit, demand forecasts — to produce *daily operational directives* for each site. These directives include demand forecasts for the next four periods, exception probability scores (how likely is this site to have a problem today?), and updated priority allocations (which customer orders should be fulfilled first when inventory is constrained?).

This layer uses a temporal graph attention network because the problem requires reasoning about both *network relationships* (how does a delay at Site A affect Site B downstream?) and *temporal patterns* (is this demand spike a one-time event or the beginning of a trend?). The graph attention mechanism lets the model learn which neighboring sites are most relevant for each prediction, while the temporal component (GRU layers) captures time-series dynamics.

The key output is the **tGNNSiteDirective** — a structured package of guidance that flows to each site's local agent:

```
tGNNSiteDirective:
  ├── Policy context (from Layer 4)
  │   ├── safety_stock_multiplier: 1.4    ← "hold more buffer here"
  │   ├── criticality_score: 0.82         ← "this site matters a lot"
  │   └── bottleneck_risk: 0.35           ← "moderate constraint risk"
  │
  ├── Operational context (from Layer 3)
  │   ├── demand_forecast: [120, 135, 128, 142]  ← 4-period lookahead
  │   ├── exception_probability: 0.71     ← "likely problem today"
  │   └── confidence: 0.85                ← model's self-assessed reliability
  │
  └── Inter-hive signals
      ├── NETWORK_SHORTAGE from upstream supplier  ← "your supplier is constrained"
      └── DEMAND_PROPAGATION from downstream DC    ← "demand wave coming"
```

**Update cadence**: Daily. Transactional state changes meaningfully day-to-day.

**Layer 1 — TRM Hive** is where individual decisions happen. Each site in the supply chain runs a *hive* of 11 narrow decision agents, each a Tiny Recursive Model (TRM) — a 7-million-parameter neural network with a 2-layer transformer and 3-step recursive refinement architecture. Each TRM handles one specific type of execution decision:

| TRM Agent | Decision | Example |
|-----------|----------|---------|
| ATP Executor | Should we promise this order? | "Fulfill 80 of 100 units from Tier 2 allocation" |
| PO Creation | Should we place a purchase order? | "Order 500 units from Supplier A, expedite" |
| Inventory Rebalancing | Should we transfer inventory? | "Move 200 units from DC-East to DC-West" |
| Order Tracking | Is this order at risk? | "Flag PO-4521 — supplier 3 days late, recommend expedite" |
| MO Execution | Should we release this production order? | "Release MO-892, sequence after MO-891" |
| TO Execution | Should we release this transfer? | "Consolidate TO-334 and TO-335, ship Thursday" |
| Quality Disposition | What should we do with this quality hold? | "Rework lot Q-127, yield estimate 85%" |
| Maintenance Scheduling | When should we do this maintenance? | "Defer PM-44 by 48 hours, no production impact" |
| Subcontracting | Make or buy? | "Route 30% of demand to external manufacturer" |
| Forecast Adjustment | Should we adjust the forecast? | "Increase next-month forecast by 12% — trade show signal" |
| Inventory Buffer | Should we change safety stock? | "Increase buffer by 15% — lead time variability rising" |

Each TRM is *narrow by design*. It doesn't try to understand the whole supply chain. It receives a focused state vector (14-30 features depending on the decision type), consults the hive's shared signal bus for context from other TRMs, and produces a decision in under 10 milliseconds. The recursive refinement (applying the same network weights three times in sequence) gives it computational depth without parameter bloat — effectively 6 layers of reasoning from 2 layers of weights.

**Inference speed**: <10ms per decision. 100+ decisions per second per site.

**Layer 0 — Deterministic Engines** are pure code — no learned parameters, no neural networks, no ambiguity. There are 11 engines, one for each decision type, and they implement the hard business rules: MRP netting logic, ATP allocation sequences, BOM explosion, capacity constraints. Every TRM decision is validated against the corresponding engine. If the TRM proposes something that violates a physical constraint (ordering negative units, exceeding warehouse capacity), the engine catches it.

The engines also serve as the **fallback**. If a TRM model fails to load, if the neural network produces garbage, if the entire ML stack goes down — the engines keep running. The platform degrades gracefully to deterministic planning, which is still better than no planning.

### How the Layers Connect: A Concrete Example

A customer places a rush order for 500 units of Product X at the East Coast DC.

1. **Layer 0** (Engine): The ATP engine checks current inventory (200 units), scheduled receipts (150 arriving tomorrow), and allocation buckets. Deterministic result: can fulfill 350 of 500.

2. **Layer 1** (TRM Hive): The ATP TRM receives the engine's baseline plus hive context — a `REBALANCE_INBOUND` signal indicating 100 units transferring from the West Coast DC, and an inter-hive `NETWORK_SHORTAGE` signal from the tGNN indicating the upstream supplier is constrained. The TRM decides: fulfill 350 now, promise remaining 150 for Thursday (when the rebalancing transfer arrives), flag the supplier constraint for the PO Creation TRM.

3. **Layer 3** (tGNN): Tomorrow's daily cycle incorporates today's fulfillment data. The tGNN updates the East Coast DC's demand forecast upward (rush order suggests increased demand), raises the exception probability for the constrained supplier, and adjusts allocations to prioritize this customer segment.

4. **Layer 4** (S&OP GraphSAGE): At the next weekly cycle, the network analysis detects increased concentration risk — the East Coast DC now sources 78% from a single supplier that has shown constraint signals. The safety stock multiplier increases from 1.0 to 1.3, and a sourcing diversification signal is generated.

The information flows *down* (policy → allocation → execution → constraint validation) and *back up* (outcomes → calibration → retraining → policy adjustment). This bidirectional flow is what makes the system continuously self-improving.

---

## Part 2: The Horizontal Network — Coordination Across the Supply Chain DAG

### The Problem: No Agent Sees Everything

In a supply chain with 50 sites, no single agent can or should have a global view. The computational cost would be prohibitive, the latency unacceptable, and the coupling would make the system fragile. Instead, the architecture uses a four-layer coordination stack that gives each site agent *just enough* context to make good local decisions that are globally coherent.

### Layer 1: Intra-Hive Signals (Within a Single Site, <10ms)

Within each site, the 11 TRM agents coordinate through a **stigmergic signal bus** — inspired by how ant colonies coordinate without centralized control. Instead of TRM agents calling each other directly, they emit *signals* into a shared environment (the HiveSignalBus), and other TRMs observe those signals when making their own decisions.

There are 25 signal types, organized by biological caste:

| Caste | TRM Agents | Signal Examples |
|-------|-----------|-----------------|
| **Scout** | ATP Executor, Order Tracking | `DEMAND_SURGE`, `ATP_SHORTAGE`, `ORDER_EXCEPTION` |
| **Nurse** | Inventory Buffer, Forecast Adjustment | `BUFFER_INCREASED`, `FORECAST_ADJUSTED` |
| **Forager** | PO Creation, Subcontracting | `PO_EXPEDITE`, `SUBCONTRACT_ROUTED` |
| **Guard** | Quality, Maintenance | `QUALITY_REJECT`, `MAINTENANCE_URGENT` |
| **Builder** | MO Execution, TO Execution | `MO_RELEASED`, `TO_DELAYED` |

Signals decay exponentially over time (pheromone model), with a default half-life of 30 minutes. This means recent signals carry more weight than stale ones, and the system naturally forgets outdated context without explicit cleanup.

**Why this ordering matters**: The decision cycle runs in six phases — SENSE, ASSESS, ACQUIRE, PROTECT, BUILD, REFLECT — and the sequencing is deliberate. Scout TRMs (ATP, Order Tracking) observe incoming demand *before* Forager TRMs (PO Creation) place upstream orders. Quality and Maintenance signals reach the Builder TRMs (MO, TO Execution) *before* they release production orders. The Rebalancing TRM runs last (REFLECT phase) with full visibility into everything that happened in the cycle, allowing it to detect and correct conflicting decisions.

The **UrgencyVector** provides a complementary coordination mechanism: a shared 11-slot array where each TRM writes its current urgency level (0.0 to 1.0) and direction (shortage, surplus, risk, relief). Any TRM can read any other TRM's urgency, creating an always-available snapshot of the site's overall state. When the ATP TRM reports urgency 0.9 (shortage direction), the PO Creation TRM sees this and increases its propensity to expedite orders — without any direct function call between them.

### Layer 2: Inter-Hive Signals (Across Sites, Daily)

No TRM ever calls across sites. All cross-site information flows through the tGNN layer (Layer 3 in the vertical stack), which produces **inter-hive signals** that are injected into each site's local signal bus.

The tGNN analyzes the full network graph daily and generates 9 types of inter-hive signals:

| Signal | Meaning | Effect on Receiving Site |
|--------|---------|------------------------|
| `NETWORK_SHORTAGE` | Upstream supply is constrained | Increase buffer, diversify sourcing |
| `NETWORK_SURPLUS` | Upstream has excess inventory | Reduce orders, accept transfers |
| `DEMAND_PROPAGATION` | Demand wave moving through network | Prepare capacity, pre-position inventory |
| `BOTTLENECK_RISK` | A network chokepoint is at risk | Delay non-critical production |
| `CONCENTRATION_RISK` | Sourcing too concentrated | Expedite alternate-source POs |
| `RESILIENCE_ALERT` | Network fragility detected | Increase safety stock |
| `ALLOCATION_REFRESH` | Priority allocations updated | Re-run ATP against new buckets |
| `PRIORITY_SHIFT` | Customer priority rankings changed | Adjust fulfillment sequence |
| `FORECAST_REVISION` | Network-level forecast updated | Adjust local demand expectations |

When a signal arrives at a site, the Directive Broadcast Service translates it into the local signal vocabulary (e.g., `NETWORK_SHORTAGE` becomes `ATP_SHORTAGE` on the local bus) and injects it with a `from_tgnn: True` marker so the TRMs can distinguish network-level signals from locally-generated ones.

Inter-hive signals have a 12-hour half-life (vs. 30 minutes for intra-hive), reflecting the fact that network-level conditions change more slowly than local operational state.

**The critical design principle**: TRMs are *unaware* that they're receiving network-level signals. They simply observe signals on the bus and react according to their learned policy. This means the same TRM model works identically whether the site is standalone or embedded in a 50-site network — the network context arrives as signals, not as architectural coupling.

### Layer 3: Cross-Authority Authorization (Seconds to Minutes)

Some decisions require coordination between agents that belong to different functional authorities. A PO Creation agent (procurement authority) that wants to expedite an order might need approval from a Finance agent (budget authority). A Plant agent that wants to insert a rush production order needs authorization from the SO/ATP agent (customer commitment authority).

The **Agentic Authorization Protocol (AAP)** handles this through explicit authority boundaries. Each of the 11 TRM types maps to one of 13 functional authority roles:

```
atp_executor      → SO_ATP (Sales & Operations)
po_creation        → PROCUREMENT
mo_execution       → PLANT
to_execution       → LOGISTICS
quality_disposition → QUALITY
maintenance        → MAINTENANCE
subcontracting     → PROCUREMENT
forecast_adjustment → DEMAND
inventory_buffer   → INVENTORY
inventory_rebalancing → INVENTORY
order_tracking     → SO_ATP
```

Every possible action is classified into three categories:
- **Unilateral**: The agent can execute without asking anyone (e.g., PO Creation adjusting order timing within normal bounds)
- **Requires Authorization**: The agent must request approval from another authority (e.g., PO Creation requesting expedite — needs Finance approval for the cost premium)
- **Forbidden**: The agent cannot perform this action at all (e.g., no execution agent can change sourcing rules — that's an S&OP policy decision)

When a TRM proposes an action that requires authorization, the flow is:

```
TRM proposes cross-authority action
    ↓
Check authority boundary → REQUIRES_AUTHORIZATION
    ↓
Create AuthorizationRequest:
  - Who's asking (requesting_agent)
  - Who needs to approve (target_agent)
  - What's proposed (action + parameters)
  - What's the benefit (net benefit score from what-if analysis)
    ↓
Submit to AuthorizationService
    ↓
Auto-approval check: Is the target resource available? No contention?
    ├── Yes → Auto-approve, proceed immediately
    └── No → Queue for human review with pre-digested options
```

The auto-approval path keeps latency under 500ms. The human escalation path surfaces a fully evaluated decision to the right person — not a raw alert, but ranked alternatives with trade-off analysis across the balanced scorecard.

### Layer 4: S&OP Consensus Board (Weekly)

At the top of the horizontal coordination stack, functional agents negotiate **policy parameters** — the θ values that flow down through the entire vertical stack. This is where strategic trade-offs are resolved: How much safety stock should we carry network-wide? What OTIF target should we commit to? How should we allocate capacity between product lines?

The S&OP layer consumes feedback signals from all 11 TRM types across all sites — OTIF actuals, shortfall frequencies, expedite costs, inventory turns — and uses these as evidence in the negotiation. When the execution layer consistently shows that a safety stock policy is causing excess inventory without improving service levels, that signal reaches the S&OP layer and drives a policy parameter adjustment.

**Update cadence**: Weekly, aligned with the S&OP review cycle.

---

## Part 3: The Confidence Engine — Routing Between Fast and Deep

### The 95/5 Architecture

Not every decision needs the same depth of reasoning. A straightforward ATP check against available inventory is fundamentally different from a quality disposition decision involving a novel defect pattern the system has never seen. The architecture handles this through a **confidence-based routing mechanism** that steers decisions between fast execution (TRM) and deep reasoning (Claude Skills).

```
Deterministic Engine computes baseline
    ↓
TRM produces learned adjustment + confidence score + risk bound
    ↓
Conformal Prediction Router evaluates uncertainty:
    │
    ├── High confidence (tight prediction intervals)
    │   → Accept TRM result ✓
    │   → Source: "trm_adjusted", latency: <10ms
    │
    └── Low confidence (wide intervals OR high risk bound)
        → Escalate to Claude Skills
        → Claude reasons about the novel situation
        → Proposal validated against engine constraints
        → Source: "skill:haiku" or "skill:sonnet", latency: ~200ms
        → Decision recorded for TRM meta-learning
```

Three checks govern the routing:

1. **TRM confidence** below threshold (default: 0.6) — the model itself reports low certainty
2. **CDT risk bound** above threshold — Conformal Decision Theory indicates P(loss > acceptable) is too high
3. **Prediction interval width** exceeds 50% of value range — the uncertainty band is too wide to act on

When escalation triggers, Claude Skills receives the full state context plus few-shot examples from a RAG decision memory (past similar decisions stored as 768-dimensional embeddings in pgvector). Skills proposals are validated against the deterministic engine — no Skills decision can deviate more than 30% from the engine baseline — and every Skills decision is recorded as training data for the TRM.

**The meta-learning effect**: Over time, the TRM learns to handle situations that previously required Skills escalation. The 95/5 boundary is not static — it shifts as the TRM absorbs more training examples. This is the cost-reduction flywheel described in the executive summary: early in deployment, Skills handles more decisions (higher cost); as the TRM learns, Skills handles fewer (lower cost).

---

## Part 4: The Learning Loop — How the System Gets Smarter

### Decision → Outcome → Calibration → Retraining

Every decision the system makes is tracked, and every outcome is eventually observed. The feedback loop runs on a fixed schedule:

| Time | Job | What It Does |
|------|-----|-------------|
| :30 hourly | Outcome Collection (high-level) | Computes actual outcomes for site-level decisions |
| :32 hourly | TRM Outcome Collection | Computes outcomes across all 11 decision tables |
| :33 hourly | Skills Outcome Collection | Computes outcomes for Claude Skills decisions |
| :35 hourly | CDT Calibration | Updates conformal prediction intervals from new decision-outcome pairs |
| :45 every 6h | Retraining Evaluation | Checks if enough new experience has accumulated; if so, retrains the TRM |
| 02:40 daily | Causal Matching | Builds propensity-score matched pairs for override effectiveness analysis |
| 03:00 daily | GNN Orchestration | Runs S&OP + Execution tGNN, broadcasts directives to all sites |

The feedback horizons are matched to each decision type — ATP outcomes are observable in 4 hours (did the order ship on time?), while inventory buffer adjustments take 14 days to evaluate (did the new safety stock level prevent stockouts?).

### Retraining: When and How

Retraining is not continuous — it fires when three conditions are met:

1. **Experience threshold**: At least 100 decisions with computed outcomes since the last checkpoint
2. **CDC trigger**: At least one Change Detection and Capture event in the last 24 hours (indicating the environment has shifted)
3. **Cooldown**: No training run in the last 6 hours (prevents thrashing)

When triggered, the system trains the TRM using offline reinforcement learning (Conservative Q-Learning) on the accumulated decision-outcome pairs. The new model is compared against the current one; if it regresses by more than 10%, the update is rejected. Accepted checkpoints are saved to the database and the site agent hot-reloads the new model without interrupting service.

### Override Effectiveness: Learning from Human Judgment

When a planner overrides an AI decision, the system doesn't just record the override — it *measures whether the override was beneficial*, using a Bayesian framework.

Each `(user, TRM type)` pair maintains a Beta(α, β) posterior distribution. When an override outcome is observed:
- If the human decision outperformed the AI's counterfactual → α increases (human was right)
- If the AI's decision would have been better → β increases (AI was right)
- Neutral outcomes → no update

The posterior produces a **training weight** that controls how much influence the human's decision patterns have on future TRM training:

```
training_weight = 0.3 + 1.7 × E[effectiveness]
where E[effectiveness] = α / (α + β)

E[p] = 0.0  → weight = 0.30  (AI consistently better, low weight on human pattern)
E[p] = 0.5  → weight = 0.85  (uncertain, moderate weight)
E[p] = 1.0  → weight = 2.00  (human consistently better, high weight on human pattern)
```

Critically, override effectiveness is measured at *two scopes*:

1. **Decision-local**: Did the human's choice produce a better outcome than the AI's for *this specific decision*?
2. **Site-wide**: Did the override improve the site's *aggregate balanced scorecard* (service level, inventory turns, cost, quality)?

The composite score weights site-wide impact more heavily (60/40 split) to prevent locally-optimal but systemically-harmful overrides from inflating a user's training weight. A planner who consistently optimizes their own node at the expense of the network will see their training weight decrease, not increase.

Three observability tiers determine how precisely the system can measure override quality:

| Tier | Decision Types | Method | Signal Strength |
|------|---------------|--------|-----------------|
| **1 — Analytical** | ATP, Forecast, Quality | Exact counterfactual computation | 1.0 (full update) |
| **2 — Statistical** | PO, MO, TO, Order Tracking | Propensity-score matched pairs | 0.3–0.9 (depends on match quality) |
| **3 — Prior only** | Inventory Buffer, Maintenance, Subcontracting | Bayesian prior (high confounding) | 0.15 (minimal update) |

This graduated approach means the system learns fastest from decision types where causal attribution is clearest, and most cautiously from types where confounding makes attribution unreliable.

---

## Part 5: The DAG as the Organizing Principle

### Four Master Site Types

The supply chain network is modeled as a Directed Acyclic Graph (DAG) with four master site types that govern material flow and information routing:

```
MARKET_SUPPLY (Upstream sources — suppliers, raw material origins)
       │
       ▼
MANUFACTURER (Transform sites — production, assembly, BOM explosion)
       │
       ▼
INVENTORY (Storage/fulfillment — DCs, warehouses, retailers)
       │
       ▼
MARKET_DEMAND (Terminal demand — end customers, retail points of sale)
```

Each site type determines which TRM agents are applicable. A MANUFACTURER site runs MO Execution and Subcontracting TRMs that an INVENTORY site doesn't need. A MARKET_DEMAND site generates demand signals that flow upstream through the network. The DAG topology — which sites connect to which, through which transportation lanes, with what lead times — is the structural backbone that both the S&OP GraphSAGE and the Execution tGNN reason over.

### How the DAG Constrains Agent Communication

The DAG topology is not just a data model — it governs *how information flows between agents*. Inter-hive signals propagate along the edges of the DAG:

- **Demand signals** flow *upstream* (from MARKET_DEMAND toward MARKET_SUPPLY)
- **Supply/shortage signals** flow *downstream* (from MARKET_SUPPLY toward MARKET_DEMAND)
- **Rebalancing signals** flow *laterally* (between INVENTORY sites at the same echelon)

A TRM at the East Coast DC never receives a direct signal from a factory in Asia. Instead, the factory's constraints are reflected in the tGNN's inter-hive signals, which arrive at the DC as a `NETWORK_SHORTAGE` or `BOTTLENECK_RISK` — abstracted, summarized, and actionable without requiring the DC agent to understand the factory's internal state.

This is deliberate. It means the system scales without increasing the communication complexity at each site. Adding a new site to the network adds edges to the graph that the tGNN processes, but each site's local agent remains unchanged — it still observes the same signal types on the same bus, just with potentially different values.

### Bill of Materials and Multi-Product Coordination

At MANUFACTURER sites, the DAG includes BOM relationships — a finished good requires specific components in defined ratios (e.g., 1 Case = 4 Six-Packs = 24 Bottles). The MRP engine at Layer 0 handles BOM explosion (computing component requirements from finished good demand), but the TRM hive adds learned coordination:

- The **MO Execution TRM** sequences production orders considering component availability (signaled via `ATP_SHORTAGE` from upstream component sites)
- The **Subcontracting TRM** makes make-vs-buy decisions when internal capacity (signaled via `MAINTENANCE_URGENT`) is constrained
- The **Quality Disposition TRM** decides whether to rework or scrap defective components, considering downstream production schedules (signaled via `MO_RELEASED`)

All of this coordination happens through the signal bus — no TRM directly reads another TRM's state. The manufacturing site's hive self-organizes around the current reality, responding to signals as they arrive.

---

## Part 6: Putting It Together — End-to-End Decision Flow

### A Complete Cycle

Here is a single decision flowing through every layer of the architecture:

**Event**: Supplier notifies that a shipment of 1,000 units will be 5 days late.

**Layer 0 — Engine** (immediate):
The Order Tracking engine detects the late shipment by comparing the supplier's revised delivery date against the PO's expected receipt date. It flags the exception and computes the impact: 3 downstream customer orders at risk of missing their promise dates.

**Layer 1 — TRM Hive** (within 20ms):
- **Order Tracking TRM** emits `ORDER_EXCEPTION` signal with urgency 0.8 (shortage direction)
- **ATP Executor TRM** observes the signal, rechecks affected customer promises, emits `ATP_SHORTAGE`
- **Inventory Buffer TRM** observes the shortage, recommends increasing safety stock for this product
- **PO Creation TRM** observes ATP shortage + order exception, evaluates whether to place an expedited PO with an alternate supplier
- The PO Creation TRM's expedite action *requires authorization* from Finance (cost premium)
- **AAP** creates an AuthorizationRequest → auto-approved (within budget delegation, no contention)
- Expedited PO is placed

**Layer 1 — Conformal Routing** (within decision cycle):
The PO Creation TRM's confidence on the alternate supplier routing is 0.52 (below the 0.6 threshold — this supplier has rarely been used). Conformal prediction escalates to Claude Skills (Haiku tier). Skills examines the RAG decision memory, finds 3 similar past decisions, and concurs with the PO expedite recommendation with additional context: "Supplier B has 98% on-time rate for expedited orders in the last 6 months." The proposal passes validation (quantity deviation within 30%) and is accepted.

**Layer 2 — Inter-Hive** (next daily cycle):
The tGNN incorporates yesterday's late shipment event. It generates a `NETWORK_SHORTAGE` signal for the affected supplier lane and a `DEMAND_PROPAGATION` signal for downstream sites. Sister DCs receive `REBALANCE_INBOUND` suggestions. The shortage signal raises exception probabilities at all sites sourcing from this supplier.

**Layer 4 — S&OP** (next weekly cycle):
The S&OP GraphSAGE detects increased concentration risk on this supplier lane. The safety stock multiplier for affected sites increases from 1.0 to 1.2. The policy parameter flows down through the next tGNN cycle, adjusting buffer calculations at every affected site.

**Feedback Loop** (over the following days):
- At :32, the outcome collector checks: did the expedited PO arrive on time?
- At :35, CDT calibration updates the conformal intervals for PO Creation decisions involving alternate suppliers
- At :45, the retraining evaluator checks if enough new PO decisions have accumulated for a training run
- The Skills decision is embedded in the RAG memory, available as a few-shot example for future similar situations
- If the planner had overridden the AI's decision, the override effectiveness tracker would compute the counterfactual and update the Bayesian posterior

**What the planner sees**: A prioritized worklist item — "Supplier delay: 3 customer orders at risk. System placed expedited PO with Supplier B (auto-approved, within budget). Revised promise dates sent to customers. Review recommended." The planner reviews, approves or adjusts, and moves on. Total elapsed time from supplier notification to response: under 2 minutes.

---

## Part 7: Infrastructure and Deployment

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Neural Networks** | PyTorch 2.2, PyTorch Geometric | TRM models (7M params), GNN models (GraphSAGE, GAT+GRU) |
| **Decision Memory** | PostgreSQL + pgvector (768-dim) | RAG-based few-shot retrieval for Claude Skills |
| **Exception Handling** | Claude API (Haiku/Sonnet) | ~5% of decisions that exceed TRM confidence bounds |
| **Backend** | FastAPI (Python 3.10+), SQLAlchemy 2.0 | REST API, async processing, ORM |
| **Frontend** | React 18, Material-UI 5, Recharts | Planning UI, worklists, dashboards |
| **Real-Time** | WebSocket | Live scenario updates, alert delivery |
| **Database** | PostgreSQL 15+ | 35 AWS SC entities, 11 Powell decision tables, planning data |
| **Simulation** | SimPy | Discrete event simulation for digital twin and training data generation |
| **Infrastructure** | Docker Compose, Nginx | Containerized deployment, reverse proxy |
| **GPU** (optional) | NVIDIA CUDA | GNN training acceleration (5-8x vs CPU) |

### Performance Characteristics

| Metric | Value |
|--------|-------|
| TRM inference latency | <10ms per decision |
| Full hive decision cycle | ~20ms (11 TRMs sequentially) |
| GNN daily inference | ~15s (S&OP + Execution + broadcast) |
| Skills escalation latency | ~200ms (includes API call + validation) |
| CDC outcome collection | <60s per hourly cycle |
| CDT calibration | ~30s per hourly cycle |
| Retraining (when triggered) | ~5 minutes per TRM type |
| Digital twin simulation | Days of simulated time in minutes |

### Data Model Compliance

The platform implements 100% of the AWS Supply Chain data model (35 entities) as the foundation layer. All planning logic — MRP netting, BOM explosion, inventory policy, sourcing rules — operates on AWS SC-standard tables and field names. The Powell framework tables (allocations, decisions, belief state, calibration) extend the base model without modifying it. This means data can be imported from and exported to any AWS SC-compliant system without transformation.

---

## Part 8: Distribution Fitting and Likelihood Estimation

### Why Point Estimates Break Safety Stock

Traditional planning systems assume demand and lead times follow a normal distribution. This assumption is baked into the standard safety stock formula: `SS = z × σ × √LT`. When the actual distribution is skewed (lognormal demand), heavy-tailed (lead times with occasional long delays), or multimodal (seasonal products with distinct demand regimes), the normal assumption produces safety stock levels that are systematically wrong — either too low (stockouts) or too high (excess inventory).

The platform addresses this through a **distribution fitting engine** that identifies the true statistical shape of each operational variable, and a **distribution-aware safety stock policy** that uses Monte Carlo simulation instead of closed-form z-score formulas when the data is non-Normal.

### The Distribution Fitting Engine

The `DistributionFitter` service (`backend/app/services/stochastic/distribution_fitter.py`) performs maximum likelihood estimation (MLE) across the platform's 20 supported distribution types and selects the best fit using statistical tests:

```
Historical data (demand, lead time, yield, price)
    ↓
MLE fitting across candidate distributions:
    Normal, Lognormal, Gamma, Weibull, Beta, Exponential,
    Triangular, Uniform, Poisson, NegativeBinomial,
    Empirical, Mixture, ...
    ↓
Goodness-of-fit evaluation:
    ├── Kolmogorov-Smirnov test (KS statistic + p-value)
    ├── AIC (Akaike Information Criterion) — penalizes complexity
    └── BIC (Bayesian Information Criterion) — stronger complexity penalty
    ↓
Ranked results: best-fitting distribution + parameters + confidence
```

The fitting results map back to the platform's `Distribution` constructors — a Weibull fit produces `Distribution(type="weibull", shape=k, scale=λ)` that integrates directly with the stochastic sampler, the Monte Carlo engine, and the safety stock calculator.

**API endpoint**: `POST /api/v1/stochastic/fit` accepts historical data and returns ranked distribution fits with parameters, test statistics, and confidence scores.

### Distribution-Aware Safety Stock: The `sl_fitted` Policy

The standard `sl` (service level) policy calculates safety stock as `z × σ_demand × √mean_lead_time`, which assumes both demand and lead time are normally distributed. The new `sl_fitted` policy in `inventory_target_calculator.py` removes this assumption:

1. **Fit distributions** to historical demand and lead time data using MLE
2. **If both are Normal** → use the standard z-score formula (fast, exact)
3. **If either is non-Normal** → simulate Demand-During-Lead-Time (DDLT) via Monte Carlo:
   - Sample N demand values from the fitted demand distribution
   - Sample N lead time values from the fitted lead time distribution
   - Compute DDLT = Σ(demand × lead_time) for each sample
   - Set safety stock = P(1-α) percentile of DDLT distribution − mean DDLT
4. **Result**: Safety stock that provides the *actual* target service level, regardless of the underlying distribution shape

This matters most for:
- **Lognormal demand** (common in retail): Standard formula underestimates safety stock by 15-30%
- **Weibull lead times** (common with ocean freight): Standard formula misses the long tail
- **Seasonal products**: Mixture distributions capture distinct demand regimes

### Distribution-Aware Feature Engineering

Motivated by Kravanja (2026) — *"Stop Using Average and Standard Deviation for Your Features"* — the platform extracts **distribution parameters as features** instead of relying on summary statistics that assume normality.

The `FeatureExtractor` service (`backend/app/services/stochastic/feature_extractor.py`) augments TRM state vectors with:

| Traditional Feature | Distribution-Aware Replacement | Why It Matters |
|---|---|---|
| `mean_demand` | `demand_dist_type`, `demand_shape`, `demand_scale` | Captures skewness and tail behavior |
| `std_demand` | `demand_cv`, `demand_skew`, `demand_kurtosis` | Distinguishes thin-tailed from heavy-tailed |
| `mean_lead_time` | `lt_dist_type`, `lt_shape`, `lt_scale` | Captures delay probability distribution |
| `demand_history_avg` | `demand_mad_ratio` (MAD/median) | Robust to outliers, better for non-Normal |

The `_classify_demand_robust()` function uses MAD/median ratio (instead of CV) to classify demand volatility, because MAD (Median Absolute Deviation) is robust to the outliers that make standard deviation unreliable for skewed distributions.

Distribution parameters are stored in decision metadata (JSON column on `powell_*_decisions` tables), making them available for both real-time TRM inference and offline retraining. The `AUTO` sampling mode in `DemandModel` and `LeadTimeModel` enums automatically fits the best distribution and samples from it, alongside the existing `NORMAL`, `WEIBULL`, and `LOGNORMAL` explicit modes.

---

## Part 9: The Digital Twin Training Pipeline — Cold-Start to Continuous Learning

### The Cold-Start Problem

When Autonomy deploys at a new customer site, the TRM agents have no site-specific experience. They've never seen this customer's demand patterns, supplier reliability, or seasonal dynamics. Deploying untrained models would produce decisions worse than simple rules. But waiting months for production data to accumulate before enabling AI defeats the value proposition.

The solution is a **five-phase training pipeline** that uses the platform's simulation capabilities as a digital twin — progressively building agent competence from synthetic data through to production autonomy.

### Five Phases: From Zero to Autonomous

```
Phase 1: Individual BC Warm-Start (Hours)
    ↓ Each TRM can match engine baseline within ±5%
Phase 2: Multi-Head Coordinated Traces (Days)
    ↓ 11 TRMs learn to coordinate via signal bus
Phase 3: Stochastic Stress-Testing (Hours)
    ↓ Agents survive demand spikes, supplier failures, capacity shocks
Phase 4: Copilot Calibration (Weeks)
    ↓ Human overrides refine agent behavior for this customer's context
Phase 5: Autonomous CDC Relearning (Ongoing)
    ↓ Continuous improvement from production outcomes
```

**Phase 1 — Individual Behavioral Cloning** (implemented in `hive_curriculum.py`):

Each of the 11 TRM types trains independently on curriculum-generated data. The curriculum progresses through complexity levels: single-site scenarios → 2-site chains → 4-site Beer Game → multi-echelon networks → production-scale topologies. At each level, 5,000+ scenarios generate supervised training pairs where the *engine baseline* serves as the teacher. After Phase 1, every TRM can reproduce the deterministic engine's decisions within ±5% — a safe starting point that guarantees no TRM decision is worse than the engine fallback.

**Phase 2 — Multi-Head Coordinated Simulation** (implemented in `coordinated_sim_runner.py`):

All 11 TRMs run simultaneously in SimPy and Beer Game simulations, with the signal bus active. This is where they learn *coordination* — how an ATP shortage signal should influence PO timing, how a maintenance deferral affects MO sequencing, how rebalancing decisions propagate through the network. Phase 2 generates 28.6M+ training records across 2-3 days of compute. The key difference from Phase 1: the training signal comes from *system outcomes* (total cost, service level) rather than per-decision accuracy.

**Phase 3 — Stochastic Stress-Testing** (uses Monte Carlo engine):

The trained agents face adversarial scenarios: demand spikes (3σ+), supplier failures (zero supply for 2+ weeks), capacity shocks (50% reduction), and compound disruptions. Agents that panic (massive over-ordering) or freeze (ignoring signals) are retrained with emphasis on the failure modes. This phase uses the platform's existing Monte Carlo simulation with variance reduction techniques (Latin hypercube sampling, antithetic variates).

**Phase 4 — Copilot Calibration** (production, human-in-the-loop):

The agents run in copilot mode — suggesting every decision but requiring human approval. Every override is captured with context (the override effectiveness tracking system described in Part 4). Over 2-4 weeks, the agents absorb the customer's specific judgment patterns: which suppliers they trust more than the data suggests, which customers they prioritize beyond the formal priority scheme, which forecast adjustments they routinely make based on market intelligence. The Bayesian posterior on each `(user, TRM type)` pair determines how much influence these overrides have on training.

**Phase 5 — Autonomous CDC Relearning** (continuous, no end date):

The CDC → Relearning loop takes over. Outcome collection (hourly), CDT calibration (hourly), and retraining evaluation (every 6 hours) run automatically. The agents improve continuously from their own production decisions. Skills decisions feed back into TRM training data, gradually shifting the 95/5 boundary as TRMs learn to handle situations that previously required escalation.

**Timeline**: Phase 1 completes in hours (compute-bound). Phase 2 takes 2-3 days (data generation + training). Phase 3 takes hours. Phase 4 takes 2-4 weeks (human-paced). Phase 5 begins immediately after Phase 4 and runs indefinitely. Total time from deployment to autonomous operation: 3-5 weeks.

---

## Part 10: Vertical Escalation — When Execution Anomalies Signal Policy Errors

### The Horizontal Limitation

The CDC → Relearning loop described in Part 4 is *horizontal* — when a TRM's performance degrades, the system retrains that same TRM. This handles execution-level drift: the model's weights become stale, the conformal intervals widen, the system detects it and retrains. But some problems can't be solved at the execution level.

Consider: the PO Creation TRM at every site consistently orders 20% more than the engine baseline, week after week. Retraining doesn't fix it — in fact, retraining *reinforces* it, because the 20% excess is the TRM's correct response to the current policy parameters (θ). The real problem is that the safety stock multiplier set at the S&OP level (Layer 4) is too low for current market conditions. The TRM is compensating for a strategic policy error by over-ordering at the execution level. No amount of execution-level retraining will fix a strategic-level problem.

### Dual-Process Cognition: Kahneman Meets Supply Chain

This maps directly to Daniel Kahneman's dual-process theory from *Thinking, Fast and Slow*:

| Kahneman | Platform | Characteristics |
|----------|----------|----------------|
| **System 1** (fast, intuitive) | 11 TRM Agents (<10ms) | Pattern-matched, automatic, high throughput |
| **System 2** (slow, deliberate) | tGNN (daily) + GraphSAGE (weekly) | Analytical, network-aware, resource-intensive |
| **The Lazy Controller** | Conformal Prediction Router | System 2 activates only when System 1 signals uncertainty |
| **Cognitive Strain** | Escalation Arbiter | Persistent anomalies force slow thinking |
| **WYSIATI** (What You See Is All There Is) | TRM local-only state | Each TRM sees only its site — can't diagnose network-wide issues |

Kahneman's key insight: System 1 works well most of the time through pattern matching, but it fails systematically on novel situations because it *substitutes* a simpler question for the hard one. TRMs do the same — they substitute "what does the pattern say?" for "is the policy still correct?" The Escalation Arbiter detects when this substitution is producing persistent errors.

### Nested OODA Loops: Boyd's Framework Applied

John Boyd's Observe-Orient-Decide-Act (OODA) loop maps onto three nested decision cycles at different time scales:

- **Execution OODA** (TRMs, <10ms): Observe local state → Orient via trained weights → Decide order quantity → Act immediately
- **Operational OODA** (tGNN, daily): Observe transactional data + S&OP embeddings → Orient via graph attention → Decide priority allocations → Act via site directives
- **Strategic OODA** (GraphSAGE, weekly): Observe network topology + market signals → Orient via bottleneck analysis → Decide policy parameters θ → Act via S&OP embeddings

Boyd's concept of *Schwerpunkt* (center of gravity) applies: the orientation phase is the center of gravity at each level. When orientation is wrong — stale TRM weights, outdated tGNN patterns, incorrect S&OP parameters — all downstream decisions are systematically biased. The Escalation Arbiter detects orientation failure at the execution level and triggers reorientation at the appropriate higher level.

### The Escalation Arbiter

The Arbiter (`backend/app/services/powell/escalation_arbiter.py`) runs every 2 hours (scheduled at :40) and monitors TRM decision patterns across all sites for **persistent directional drift**:

```
For each site, for each TRM type:
    Collect recent decisions (48-hour window)
    Compute:
        direction  — running mean of adjustments from baseline (+/-)
        magnitude  — running mean of |adjustment| as fraction of baseline
        consistency — fraction of adjustments in the dominant direction

    If consistency > 0.70 AND magnitude > threshold:
        Signal detected → route to appropriate level
```

**Routing logic**:

| Pattern | Diagnosis | Route |
|---------|-----------|-------|
| Single TRM, short duration | Execution noise | Horizontal → CDC retrain |
| Single TRM, long duration, high consistency | Local policy drift | Vertical → off-cadence tGNN refresh |
| Multiple TRMs at same site | Site-level policy error | Vertical → tGNN + allocation rebalance |
| Same pattern across 30%+ of sites | Network-wide shift | Strategic → S&OP GraphSAGE re-inference |
| Cross-site + demand signal correlation | Market regime change | Strategic → full S&OP consensus board |

The Arbiter extends the existing `ReplanAction` enum with two new actions: `VERTICAL_OPERATIONAL` (trigger off-cadence tGNN refresh) and `VERTICAL_STRATEGIC` (create S&OP policy review request via the AAP authorization protocol). All escalation events are logged to the `powell_escalation_log` table with full evidence (persistence signals, cross-site patterns, diagnosis) for audit and tuning.

**Cooldowns** prevent oscillation: 12 hours between operational escalations, 72 hours between strategic escalations. The system must accumulate at least 20 decisions before a pattern is considered meaningful.

See [ESCALATION_ARCHITECTURE.md](docs/ESCALATION_ARCHITECTURE.md) for the full theoretical foundation including Powell 2026 framing (three stages of decision automation, 7 levels of AI, state variable decomposition) and the SOFAI meta-cognitive architecture reference.

---

## Summary: The Architecture in One Paragraph

Autonomy operates as a four-layer decision stack — strategic network analysis (GraphSAGE, weekly), tactical allocation (temporal GNN, daily), operational execution (TRM hive, milliseconds), and deterministic validation (engines, always) — where each layer constrains the layer below through policy parameters, directives, and hard constraints. Within each site, 11 narrow decision agents coordinate through a biologically-inspired signal bus with pheromone-like decay, organized into a six-phase decision cycle that ensures scouts observe before foragers act. Across sites, information flows along the supply chain DAG through inter-hive signals generated by the network-wide GNN, preserving local autonomy while maintaining global coherence. A conformal prediction router steers ~5% of low-confidence decisions to Claude Skills for deep reasoning, and every decision feeds a closed-loop learning pipeline — outcome collection, conformal calibration, Bayesian override tracking, and periodic retraining — that makes the system measurably smarter from every planning cycle it runs. Distribution-aware feature engineering replaces normal-distribution assumptions with MLE-fitted distributions for safety stock, demand classification, and TRM state vectors. A five-phase digital twin pipeline — behavioral cloning, coordinated simulation, stochastic stress-testing, copilot calibration, and autonomous relearning — takes agents from zero experience to production autonomy in 3-5 weeks. And when execution-level anomalies signal that strategic policy parameters are wrong, the Escalation Arbiter detects persistent directional drift and routes the problem to the appropriate higher tier — operational (tGNN refresh) or strategic (S&OP policy review) — closing the vertical feedback loop that connects execution outcomes to policy correction.

# Food Distribution Demo Guide

**"Late February 2026 — A Week in the Life of CDC_WEST"**

This guide walks through a comprehensive demo of the Autonomy platform using the Food Distribution network. The demo showcases all four Adaptive Decision Hierarchy (ADH) levels — from executive strategy briefings down to individual TRM execution decisions — connected by six realistic supply chain storylines.

---

## Quick Start

**Option A — Full warm-start pipeline** (trains TRMs + Site tGNN + seeds demo data):

```bash
# Single command: trains all models, enables Site tGNN, seeds demo data
make warm-start-food-dist-full

# Or quick version (fewer epochs, skips trace generation + stress test):
make warm-start-food-dist-quick
```

**Option B — Seed only** (uses existing checkpoints, no training):

```bash
# 1. Ensure Food Dist infrastructure is seeded (if not already)
docker compose exec backend python -m scripts.seed_food_dist_demo
docker compose exec backend python -m scripts.seed_food_dist_planning_data

# 2. Seed the action layer (briefings, worklists, decisions, alerts)
docker compose exec backend python -m scripts.seed_food_dist_deep_demo

# 3. Enable Site tGNN (Layer 2 cross-TRM coordination)
make warm-start-food-dist-enable
```

**Login**:
- URL: http://localhost:8088
- Email: `admin@distdemo.com` (or any role — see User Accounts below)
- Password: `Autonomy@2026`

The seed scripts are **idempotent** — re-run anytime to reset action layer data without touching infrastructure.

### Warm-Start Pipeline (6 Phases)

The unified warm-start script (`scripts/warm_start_food_dist.py`) orchestrates the complete cold-start → warm-start pipeline:

| Phase | What | Duration | Output |
|-------|------|----------|--------|
| 1 | TRM curriculum BC (all 11 types, 2 signal phases) | ~5-10 min | `checkpoints/trm_food_dist/trm_*_site256_v*.pt` |
| 2 | Coordinated multi-head traces (CoordinatedSimRunner) | ~2-3 min | `data/hive_traces_CDC_WEST.json` |
| 3 | Site tGNN training from traces (Layer 2 BC) | ~1-2 min | `checkpoints/site_tgnn/CDC_WEST/site_tgnn_latest.pt` |
| 4 | Stochastic stress-testing (5 perturbation scenarios) | ~1-2 min | Validation results |
| 5 | Enable Site tGNN feature flag in `site_agent_configs` | instant | DB row `enable_site_tgnn=true` |
| 6 | Seed all demo data (planning, storylines, deep demo) | ~1-2 min | Demo-ready database |

Run specific phases: `python scripts/warm_start_food_dist.py --phases 3,5` (retrain Site tGNN + enable).

---

## User Accounts

Each account maps to an ADH level and lands on the appropriate dashboard:

| Email | Role | ADH Level | Landing Page |
|-------|------|-------------|-------------|
| `admin@distdemo.com` | Tenant Admin / Demo All | All levels | Executive Dashboard |
| `exec@distdemo.com` | Executive (CEO) | Strategic | Strategy Briefing |
| `scvp@distdemo.com` | VP Supply Chain | Strategic | Executive Dashboard |
| `sopdir@distdemo.com` | S&OP Director | Tactical | S&OP Worklist |
| `mpsmanager@distdemo.com` | MPS Manager | Operational | Agent Decisions |
| `atp@distdemo.com` | ATP Analyst | Execution | ATP Worklist |

**Recommended for demos**: Use `admin@distdemo.com` — it has access to every page, so you can walk through all levels without logging out.

Password for all accounts: **Autonomy@2026**

---

## The Network

Food Dist operates a hub-and-spoke distribution network:

```
10 Suppliers                    CDC_WEST                    10 Customers
 (Tyson, Kraft,     ────────►  West Valley City, UT  ────────►  (QUICKSERV, Metro
  Rich Products,                    │                             Grocery, Restaurant
  Nestle, etc.)               26 products                        Supply, etc.)
                           5 temperature categories
```

**26 products** across 5 categories: Frozen Proteins (FP), Refrigerated Dairy (RD), Dry Pantry (DP), Frozen Desserts (FD), Beverages (BV).

**To visualize the network**: Navigate to **Administration > Supply Chain Configs** (`/admin/tenant/supply-chain-configs`), select "Food Dist Distribution Network", and click the **Network** tab to see the interactive D3-Sankey diagram showing all suppliers → DC → customer flows.

> **Screenshot 1 — Network Topology**
> *Navigation: Administration > Supply Chain Configs > "Food Dist Distribution Network" > Network tab*
> Capture the Sankey diagram showing 10 suppliers → CDC_WEST → 10 customers with material flows.

---

## The Six Storylines

The demo week (Mon Feb 24 – Fri Feb 28, 2026) features six interconnected storylines. Each one flows through all four ADH levels:

### Story 1: March Madness Demand Surge

> QUICKSERV and restaurant chains pre-order frozen proteins ahead of the NCAA tournament.

- **Products**: Chicken Breast IQF (+35%), Turkey Breast Deli (+20%)
- **Trigger**: Customer pre-order signals from QUICKSERV procurement
- **Key decisions**: Forecast uplift, buffer increase (1.35x), expedited Tyson PO, priority ATP allocation
- **Revenue opportunity**: $145K incremental

### Story 2: Rich Products Weather Delay

> A winter storm over Buffalo, NY delays Rich Products dairy shipments by 3 days.

- **Products**: Cream Cheese, Greek Yogurt, Butter (all from RICHPROD supplier)
- **Trigger**: Supplier delay notification — winter storm disruption
- **Key decisions**: Split-source contingency (60/40 Rich/Land O'Lakes), emergency PO, cross-DC rebalancing
- **Service risk**: $89K if no action taken

### Story 3: Greek Yogurt Quality Hold

> 2,400 cases fail texture consistency testing. Lot placed on quality hold.

- **Products**: Greek Yogurt Plain
- **Trigger**: Quality test failure on incoming lot
- **Key decisions**: Disposition evaluation (rework vs scrap vs discount), backup PO, overflow storage transfer
- **Inventory at risk**: $36K

### Story 4: Ice Cream Spring Ramp-Up

> Seasonal models detect spring transition starting 1 week early.

- **Products**: Ice Cream Vanilla Premium, Sorbet Mango
- **Trigger**: Seasonal demand model + temperature forecast
- **Key decisions**: Buffer increase (1.25x), Kraft capacity coordination, overflow freezer transfer
- **Capacity concern**: Kraft at 88% utilization

### Story 5: QUICKSERV Arizona Expansion

> Three new Phoenix sites opening March 1 with above-average stocking orders.

- **Products**: Chicken Breast IQF
- **Trigger**: Sales team input — new store opening plan
- **Key decisions**: Forecast +25%, buffer +15%, safety stock replenishment PO
- **Auto-executed**: Agent confidence 0.88 exceeded threshold — no human approval needed

### Story 6: Dairy Cost Pressure

> Butter and cheddar spot prices jump 12% due to reduced Upper Midwest output.

- **Products**: Butter, Cheddar Block
- **Trigger**: Market intelligence — commodity price spike
- **Key decisions**: Forward contract evaluation, demand forecast adjustment (-8%)
- **Margin impact**: $23K if sustained 30 days

### How They Interconnect

The storylines are not isolated — they create cascading effects:

- Story 2 (weather delay) **compounds** Story 3 (quality hold) — both reduce dairy availability
- Story 1 (March Madness) **overlaps** Story 5 (Arizona) — both increase chicken demand
- Story 4 (ice cream ramp) is **constrained by** Story 2 — weather delay affects Kraft shipments
- Story 6 (cost pressure) **influences** Story 2 contingency — Land O'Lakes premium is now 8% on top of already-elevated prices

---

## Demo Walkthrough — By Dashboard

> **Tip**: Before starting the demo, open the **Network Topology** view (**Administration > Supply Chain Configs** → select "Food Dist Distribution Network" → **Network** tab) to orient the audience on the hub-and-spoke structure. You can also show the **Demand Planning** view (**Planning > Demand Planning**, `/planning/demand`) and **Inventory Optimization** page (**Planning > Inventory Optimization**, `/planning/inventory-optimization`) to establish the baseline state before walking through the storylines.

### Level 1: Executive Dashboard

**Navigation**: Insights & Analytics > **Executive Dashboard** (`/executive-dashboard`)

**What you see**:
- Service level: **94.2%** (above 92% target, but under pressure)
- Fill rate: **96.1%**
- Agent score: **72** (on -100 to +100 scale)
- Override rate: **18%** (humans overriding 18% of agent recommendations)
- Open exceptions: **8**

**Key visualizations**:
- KPI summary cards across the top with trend indicators
- Agent score gauge showing 72/100 with color-coded zones
- Exception count badge linking to Condition Alerts

**Talking points**:
- "The platform gives executives a real-time pulse on how AI agents are performing"
- "Agent score of 72 means the AI is making better decisions than baseline in most cases"
- "18% override rate is healthy — it means planners are engaged and the system is learning from their corrections"

> **Screenshot 2 — Executive Dashboard**
> *Navigation: Insights & Analytics > Executive Dashboard (`/executive-dashboard`)*
> Capture the KPI cards (service level, fill rate, agent score, override rate, open exceptions) and trend indicators.

**Next step**: Click the Strategy Briefing link or navigate to it directly.

---

### Level 1: Strategy Briefing

**Navigation**: Insights & Analytics > **Strategy Briefing** (`/strategy-briefing`)

**What you see**:
- Weekly briefing titled **"Weekly Strategy Briefing — Feb 24, 2026"**
- Full narrative covering all 6 storylines
- 5 scored recommendations (ranked 88 → 65)
- 3 follow-up Q&A exchanges

**Key visualizations**:
- Recommendation cards with confidence scores and impact values
- Color-coded priority ranking (88 = high confidence green, 65 = moderate amber)
- Q&A thread with expandable answers

**Talking points**:
- "Every Monday, the platform generates an executive briefing synthesized by Claude Sonnet from all platform data"
- "Recommendations are scored and ranked — the executive just reviews and approves"
- "Follow-up Q&A lets executives drill into any recommendation with natural language questions"

**Demo the Q&A**:
1. Click on the first follow-up: *"What's our exposure if Rich Products delays extend to 5 days?"*
2. Show the detailed answer with per-SKU analysis and contingency recommendation
3. Click the March Madness revenue question to show ROI analysis ($145K opportunity, 17.7x ROI)

> **Screenshot 3 — Strategy Briefing**
> *Navigation: Insights & Analytics > Strategy Briefing (`/strategy-briefing`)*
> Capture the briefing narrative with the 5 scored recommendations visible. A second screenshot showing the expanded Q&A thread is also useful.

---

### Level 2: S&OP Worklist

**Navigation**: Insights & Analytics > **S&OP Worklist** (`/sop-worklist`)

**What you see**:
- 6 items representing strategic/tactical issues for the S&OP Director
- Mixed statuses: 2 accepted (green), 3 pending (yellow), 1 auto-executed (blue)
- Impact values ranging from -$89K to +$145K
- Agent recommendations with reasoning for each

**Key visualizations**:
- Status badges (accepted/pending/auto-executed) with color coding
- Impact column with positive (green, opportunity) and negative (red, risk) dollar values
- Urgency indicators (urgent/standard/low)
- Expandable agent reasoning panels

**Talking points**:
- "This is where strategic decisions live — not individual SKU adjustments, but cross-functional trade-offs"
- "Each item has an AI recommendation with confidence level and reasoning"
- "The S&OP Director can accept, reject with a reason, or let the agent auto-execute"

**Demo flow**:
1. **Show the March Madness item** (accepted) — "The S&OP Director reviewed this Tuesday morning and approved the pre-positioning. The agent then auto-executed the downstream actions."
2. **Show the Rich Products item** (pending) — "This is still pending because the contingency involves cost trade-offs the director wants to evaluate further."
3. **Show the QUICKSERV Arizona item** (auto-executed) — "This one auto-executed because the agent confidence was 0.88, above the 0.60 threshold. No human needed."
4. **Highlight the impact column** — "Every item shows the dollar impact — positive for opportunities, negative for risks. This helps the director prioritize."

**Cross-reference**: After showing the S&OP Worklist, navigate to **Planning > S&OP** (`/planning/sop`) to show the S&OP Policy Envelope where these strategic parameters feed into the planning cascade.

> **Screenshot 4 — S&OP Worklist**
> *Navigation: Insights & Analytics > S&OP Worklist (`/sop-worklist`)*
> Capture the 6-item worklist showing the mix of accepted (green), pending (yellow), and auto-executed (blue) status badges with impact values.

---

### Level 3: Agent Decisions (Copilot Worklist)

**Navigation**: Insights & Analytics > **MPS Worklist** (`/insights/actions`) — this shows the operational copilot decisions

**What you see**:
- 15 operational-level recommendations
- Decision types: demand forecast, supply plan, ATP allocation, rebalancing, safety stock, replenishment
- Status mix: 5 pending, 4 accepted, 3 auto-executed, 2 rejected, 1 expired
- Each with confidence score, reasoning, and recommended values

**Key visualizations**:
- Decision cards with status badges and confidence gauges
- Decision type filter tabs (Demand Forecast, Supply Plan, ATP, Inventory, Replenishment)
- Override reason display on rejected decisions
- Timeline showing when each decision was created and actioned

**Talking points**:
- "This is the operational planner's inbox — the AI proposes, the human disposes"
- "Each recommendation shows the agent's confidence and detailed reasoning"
- "When a planner rejects, they provide a reason — this feeds back into agent training"

**Demo the override story**:
1. Find the **Metro Grocery cream cheese ATP** decision (REJECTED)
2. Show the override reason: *"Metro Grocery contractual minimum is 900 cases. Adjusted to 900 cases partial fill to meet contract obligation."*
3. Explain: "The agent recommended 720 cases based on priority logic, but the planner knew about a contractual minimum the agent hadn't learned yet. This override gets recorded and the agent learns from it."
4. Find the **Kraft expedite** decision (REJECTED)
5. Show: "The planner rejected the $4.5K expedite because they called Kraft directly and negotiated a 15% volume increase at no premium. Human domain knowledge still matters."

**Cross-reference**: Show the **Planning > Forecasting** page (`/planning/forecasting`) to display the demand forecast charts that underpin the forecast uplift decisions.

> **Screenshot 5 — MPS Worklist (Agent Decisions)**
> *Navigation: Insights & Analytics > MPS Worklist (`/insights/actions`)*
> Capture the 15-item operational worklist. Ideally show one expanded decision card with reasoning visible, plus the rejected Metro Grocery decision with override reason.

---

### Level 4: Condition Alerts

**Navigation**: Insights & Analytics > **Exception Detection** (`/planning/execution/order-tracking-worklist`) or via the exception count badge on the Executive Dashboard

**What you see**:
- 8 condition alerts (6 active, 2 resolved)
- Severity levels: 2 critical (red), 3 warning (amber), 3 info (blue)
- Duration tracking (how long each condition has persisted)
- Resolution tracking for resolved alerts

**Key visualizations**:
- Severity-colored alert cards (critical=red, warning=amber, info=blue)
- Duration bars showing how long each condition has been active
- Resolution status with agent/user attribution
- Linked scenario evaluations (click to see what-if analysis)

**Talking points**:
- "The condition monitor runs continuously, checking 6 types of conditions against the database"
- "Conditions escalate from info → warning → critical based on duration and severity"
- "When an agent resolves a condition, it's recorded in the audit trail"

**Highlight key alerts**:
1. **Cream Cheese ATP Shortfall** (critical, 40 hours) — "This is the Rich Products weather delay cascading into an ATP shortage. Active for 40 hours."
2. **Tenders Forecast Deviation** (resolved) — "The agent detected the QUICKSERV Arizona deviation, auto-adjusted the forecast, and the condition self-resolved."

**Cross-reference**: Navigate to **Insights & Analytics > Risk Analysis** (`/analytics/risk`) to show the risk dashboard view with aggregated risk metrics.

> **Screenshot 6 — Condition Alerts**
> *Navigation: Insights & Analytics > Exception Detection (`/planning/execution/order-tracking-worklist`)*
> Capture the 8 alerts with severity color-coding (red/amber/blue) and duration bars. Show at least one resolved alert.

---

### Level 4: Scenario Evaluations

**Navigation**: **Insights & Analytics > Scenario Comparison** (`/sc-analytics`) or accessible from Condition Alert detail links

**What you see**:
- 3 what-if scenario evaluations with ranked alternatives
- Each shows multiple scenarios with balanced scorecard scores
- Trade-off analysis and probability of success

**Key visualizations**:
- Side-by-side scenario comparison cards with balanced scorecard radar charts
- Score bars showing overall, financial, customer, and operational rankings
- Cost vs service level trade-off scatter plot
- Confidence percentage and probability of success indicators

**Demo the Rich Products contingency**:
1. Show 3 scenarios: Wait (score 62), Split source (score 88), Full switch (score 79)
2. Point out the trade-off: "Split source achieves 94.8% service level at $2.1K. Full switch gets 96.1% but costs $5.4K — diminishing returns."
3. "The agent recommended split source with 82% confidence. The human can see exactly why and decide."

> **Screenshot 7 — Scenario Evaluation**
> *Navigation: Insights & Analytics > Scenario Comparison (`/sc-analytics`)*
> Capture the Rich Products contingency showing 3 ranked scenarios with balanced scorecard scores, cost vs service trade-off, and the agent's recommendation.

---

### Level 5: Execution Agent Worklists

> **Overview**: Before diving into individual worklists, show the **Decision Cascade** dashboard (**AI & Agents > Decision Cascade**, `/admin/powell`) which provides a unified view of the Adaptive Decision Hierarchy — state, policy, decisions, and outcomes across all TRM agents.

#### ATP Worklist
**Navigation**: Planning Cascade > TRM Worklists > **ATP Worklist** (`/planning/execution/atp-worklist`)

**What you see**: 12 ATP consumption decisions showing priority-based allocation
- P1-P2 orders (QUICKSERV): all fulfilled
- P3 orders: mostly fulfilled, one partial (cream cheese shortage)
- P4-P5 orders: deferred or rationed
- Post-rebalancing fulfillments (Thursday/Friday)

**Key visualizations**:
- Priority-colored rows (P1=darkest, P5=lightest)
- Fill percentage bars showing requested vs promised quantities
- Consumption breakdown showing which priority tiers were consumed
- Timeline showing fulfillment progression across the week

**Talking point**: "ATP allocation follows strict priority rules. P1 QUICKSERV orders are always fulfilled first. Lower-priority orders get rationed when supply is constrained — but once the rebalancing resolves the shortage, they get fulfilled in the next cycle."

**Cross-reference**: Navigate to **Execution > Order Promising (ATP/CTP)** (`/execution/atp-ctp`) to show the AATP allocation buckets by priority tier.

> **Screenshot 8 — ATP Worklist**
> *Navigation: Planning Cascade > TRM Worklists > ATP Worklist (`/planning/execution/atp-worklist`)*
> Capture the priority-colored rows showing P1-P5 fulfillment with fill percentage bars. Show the cream cheese partial fill.

#### PO Worklist
**Navigation**: Planning Cascade > TRM Worklists > **PO Worklist** (`/planning/execution/po-worklist`)

**What you see**: 6 purchase order decisions across 4 suppliers
- Emergency POs (urgent): Land O'Lakes dairy, backup yogurt
- Expedited POs: Tyson chicken for March Madness
- Standard POs: Kraft ice cream, Conagra cheddar

**Key visualizations**:
- Urgency badges (urgent=red, standard=blue)
- Supplier cards with expected cost and lead time
- Confidence scores and trigger reasons
- Days-of-supply indicators showing current inventory position

**Talking point**: "The PO agent balances urgency against cost. Emergency POs to Land O'Lakes cost 8% more but prevent $89K in service failures."

**Cross-reference**: Show **Execution > Purchase Orders** (`/planning/purchase-orders`) for the full PO management view.

> **Screenshot 9 — PO Worklist**
> *Navigation: Planning Cascade > TRM Worklists > PO Worklist (`/planning/execution/po-worklist`)*
> Capture the 6 PO decisions showing emergency (red) vs standard (blue) urgency badges with supplier, cost, and lead time.

#### Rebalancing Worklist
**Navigation**: Planning Cascade > TRM Worklists > **Rebalancing Worklist** (`/planning/execution/rebalancing-worklist`)

**What you see**: 4 cross-site transfer recommendations
- Executed transfers from overflow storage
- Pre-positioning transfer to Phoenix staging
- Emergency transfer from alternate DC

**Key visualizations**:
- From/To site pairs with directional arrows
- Days-of-supply before/after comparison showing rebalancing impact
- Confidence scores and cost estimates
- Reason tags (stockout prevention, seasonal ramp, demand surge, supply disruption)

**Cross-reference**: Show **Execution > Inventory Rebalancing** (`/execution/inventory-rebalancing`) for the network-wide rebalancing view.

> **Screenshot 10 — Rebalancing Worklist**
> *Navigation: Planning Cascade > TRM Worklists > Rebalancing Worklist (`/planning/execution/rebalancing-worklist`)*
> Capture the 4 transfer recommendations with from/to arrows, days-of-supply before/after, and reason tags.

#### Order Exceptions
**Navigation**: Planning Cascade > TRM Worklists > **Order Tracking Worklist** (`/planning/execution/order-tracking-worklist`)

**What you see**: 5 order exceptions of different types
- DELAYED (Rich Products), AT_RISK (QUICKSERV), PRICE_VARIANCE (dairy), EARLY_ARRIVAL (Tyson), QUALITY_HOLD (yogurt)

**Key visualizations**:
- Exception type badges with severity colors
- Impact assessment descriptions and estimated cost
- Recommended action for each exception
- Linked orders with status tracking

> **Screenshot 11 — Order Exceptions**
> *Navigation: Planning Cascade > TRM Worklists > Order Tracking Worklist (`/planning/execution/order-tracking-worklist`)*
> Capture the 5 exceptions with type badges (DELAYED, AT_RISK, PRICE_VARIANCE, EARLY_ARRIVAL, QUALITY_HOLD) and recommended actions.

---

### Decision Performance

**Navigation**: Insights & Analytics > **Agent Performance** (`/agent-performance`)

**What you see**:
- Weekly performance metrics by category
- Agent scores: 65-81 range across categories
- Override rates: 8-24% by category
- Automation percentage: 77-92%

**Key metrics to highlight**:

| Category | Agent Score | Override Rate | Automation |
|----------|-----------|--------------|-----------|
| Overall | 72 | 18% | 82% |
| ATP Allocation | 81 | 8% | 92% |
| Demand Forecast | 78 | 12% | 92% |
| Inventory | 68 | 22% | 80% |
| Supply Plan | 65 | 24% | 77% |

**Key visualizations**:
- Agent score bar chart by category with color-coded performance zones
- Override rate trend showing progression over time
- Automation percentage gauge
- Category comparison radar chart

**Talking points**:
- "ATP has the highest agent score (81) and lowest override rate (8%) — the agent has learned this domain well"
- "Supply Plan has the lowest score (65) and highest override rate (24%) — this is where human expertise still adds the most value"
- "As the agent learns from overrides, we expect supply plan scores to climb and override rates to fall"

> **Screenshot 12 — Agent Performance**
> *Navigation: Insights & Analytics > Agent Performance (`/agent-performance`)*
> Capture the category breakdown table (ATP, Demand, Inventory, Supply) with agent scores, override rates, and automation percentages.

---

### Override Effectiveness

**Navigation**: AI & Agents > **RLHF Feedback** (`/admin/rlhf`) — Override Effectiveness tab

**What you see**: Bayesian posteriors for 3 users who override agent decisions

| User | TRM Type | Effectiveness | Observations | Training Weight |
|------|---------|--------------|-------------|----------------|
| S&OP Director | Supply Plan | 73% | 11 | 1.54 |
| MPS Manager | Demand Forecast | 56% | 9 | 1.25 |
| ATP Analyst | ATP Allocation | 86% | 14 | 1.76 |

**Key visualizations**:
- Beta distribution curves for each user showing posterior shape
- Effectiveness percentage gauges with credible intervals
- Training weight bars showing how much each user's overrides influence agent learning
- Observation count progression

**Talking points**:
- "The platform tracks whether human overrides actually lead to better outcomes"
- "The ATP Analyst has an 86% effectiveness rate — their overrides are high quality and get high training weight (1.76)"
- "The MPS Manager is at 56% — close to a coin flip. The system will gradually reduce the weight of their overrides in agent training"
- "This is the judgment capture flywheel: good overrides teach the agent, poor overrides are down-weighted"

> **Screenshot 13 — Override Effectiveness (Bayesian Posteriors)**
> *Navigation: AI & Agents > RLHF Feedback (`/admin/rlhf`) > Override Effectiveness tab*
> Capture the 3-user table with Beta distribution curves, effectiveness percentages, and training weight bars.

---

## Supporting Visualizations

These pages provide additional context you can navigate to during the demo to illustrate specific storylines:

| Page | Navigation | Route | When to Show |
|------|-----------|-------|-------------|
| **Network Topology** | Administration > Supply Chain Configs | `/admin/tenant/supply-chain-configs` | Opening — orient the audience on hub-and-spoke |
| **Demand Planning** | Planning > Demand Planning | `/planning/demand` | Story 1 & 5 — show forecast uplift data |
| **Forecast Editor** | Planning > Forecast Editor | `/planning/demand/edit` | Story 1 — drill into the March Madness forecast adjustment |
| **Forecast Exceptions** | Planning > Forecast Exceptions | `/planning/forecast-exceptions` | Story 5 — show the Arizona deviation detection |
| **Inventory Optimization** | Planning > Inventory Optimization | `/planning/inventory-optimization` | Story 3 & 4 — show safety stock policies and buffer levels |
| **Inventory Visibility** | Execution > Visibility > Inventory Visibility | `/visibility/inventory` | Story 2 & 3 — show dairy inventory under pressure |
| **Supply Planning** | Planning > Supply Planning | `/planning/supply-plan` | Story 2 — show the supply contingency plan |
| **AATP Allocations** | Planning > AATP Allocations | `/execution/atp-ctp` | Story 1 — show priority allocation buckets |
| **Sourcing & Allocation** | Planning > Sourcing & Allocation | `/planning/sourcing` | Story 2 — show sourcing rules for split-source contingency |
| **Capacity Planning** | Planning > Capacity Planning | `/planning/capacity` | Story 4 — show Kraft at 88% utilization |
| **KPI Monitoring** | Insights & Analytics > KPI Monitoring | `/planning/kpi-monitoring` | Wrap-up — show overall KPI trends |
| **Hierarchical Metrics** | Insights & Analytics > Hierarchical Metrics | `/planning/metrics` | Wrap-up — show metrics rolled up by category |
| **Risk Analysis** | Insights & Analytics > Risk Analysis | `/analytics/risk` | Story 2 & 6 — show risk exposure |
| **Decision Cascade** | AI & Agents > Decision Cascade | `/admin/powell` | Technical deep-dive — show ADH framework |
| **Execution Agents (TRM)** | AI & Agents > Execution Agents | `/admin/trm` | Technical deep-dive — show TRM training status |

---

## Advanced Demo Topics

### The Compounding Loop

Walk through how a single override creates long-term value:

1. **ATP Analyst rejects** the Metro Grocery 720-case recommendation
2. **Override reason captured**: "Contractual minimum is 900 cases"
3. **Outcome measured**: The 900-case fill met the contract and avoided a $15K penalty
4. **Bayesian posterior updated**: ATP Analyst effectiveness increases
5. **Training weight increases**: Future overrides from this analyst carry more weight
6. **Agent learns**: Next time it sees a Metro Grocery order, it checks contractual minimums
7. **Override rate drops**: The agent handles this case autonomously next time

**Where to show this**: Start at **Agent Performance** (`/agent-performance`), drill into the override detail, then navigate to **RLHF Feedback** (`/admin/rlhf`) to show the Bayesian posteriors.

### Copilot vs Autonomous Mode

Show the contrast between decisions that required human approval vs those that auto-executed:

| Decision | Mode | Why |
|----------|------|-----|
| March Madness buffer increase | Copilot (accepted) | High dollar impact ($145K), wants human sign-off |
| QUICKSERV Arizona forecast | Autonomous | Agent confidence 0.88 > threshold 0.60 |
| Cream cheese emergency PO | Copilot (pending) | Involves supplier switch, cost trade-off |
| Cheddar standard replenishment | Autonomous | Routine reorder, high confidence (0.95) |

**Where to show this**: **S&OP Worklist** (`/sop-worklist`) shows the copilot/autonomous split at the strategic level; **MPS Worklist** (`/insights/actions`) shows it at the operational level.

### The Autonomy Value Proposition

Tie back to the Autonomy value proposition:

1. **Before Autonomy**: 4 planners managing 25 SKUs each, reactive to disruptions
2. **With Autonomy**: AI handles 82% of decisions autonomously, planners focus on the 18% that need judgment
3. **Compounding effect**: Every override makes the AI better, gradually shifting the 82/18 boundary
4. **End state**: Planners become *supervisors* of AI agents, not manual decision-makers

### Site tGNN — Cross-TRM Coordination (Layer 2)

When enabled (via `make warm-start-food-dist-enable` or the full pipeline), the Site tGNN adds **learned cross-TRM causal coordination** within CDC_WEST. This is Layer 2 in the 5-layer coordination stack:

```
Layer 1   — HiveSignalBus + UrgencyVector       <10ms   (reactive, within hive)
Layer 2 — Site tGNN                           hourly  (learned cross-TRM trade-offs)
Layer 3   — Network tGNN                        daily   (inter-site allocation)
AAP Protocol   — AAP (Authorization Protocol)        ad hoc  (cross-authority negotiation)
Layer 4   — S&OP GraphSAGE                      weekly  (strategic policy parameters)
```

**What it does**: Before each 6-phase decision cycle, the Site tGNN evaluates all 7 active TRMs' state and produces urgency adjustments ([-0.3, +0.3]) that modulate the UrgencyVector. For example, if the ATP TRM has been fulfilling aggressively for several cycles, the Site tGNN learns to reduce ATP urgency to prevent downstream inventory buffer starvation.

**Architecture**: GATv2 + GRU, ~25K parameters, <5ms inference, 11 TRM-type nodes with 22 directed causal edges (inactive nodes masked to zero).

**Where to show this**: Navigate to **AI & Agents > Hive Dashboard** (`/admin/hive-dashboard`) to see urgency vector evolution, signal bus activity, and the Site tGNN adjustment magnitudes per TRM.

---

## Technical Reference: Network, Data Model, and History Generation

This section documents the Food Distribution demo's data architecture — the supply chain network topology, all seeded entity types, demand model characteristics, and operational statistics. It is the technical companion to the demo walkthrough above.

**Source files**:
- Config generator: `backend/app/services/food_dist_config_generator.py`
- History generator: `backend/app/services/food_dist_history_generator.py`
- Seed script: `backend/scripts/seed_food_dist_demo.py`
- Warm-start pipeline: `backend/scripts/warm_start_food_dist.py`

---

### Network Topology

**Type**: Hub-and-spoke distribution network (no manufacturing)

```
10 Suppliers ──► CDC_WEST (Central DC) ──┬──► RDC_NW ──► 7 NW Customers
                West Valley City, UT     └──► RDC_SW ──► 7 SW Customers
```

#### Internal Sites (3)

| Site Code | Type | Location | Master Type | Capacity |
|-----------|------|----------|-------------|----------|
| CDC_WEST | Central DC | West Valley City, UT | INVENTORY | 650K cases (150K frozen, 200K refrig, 300K dry) |
| RDC_NW | Regional DC | Seattle, WA | INVENTORY | 100K cases |
| RDC_SW | Regional DC | Riverside, CA | INVENTORY | 100K cases |

#### Suppliers (10 external trading partners)

| Code | Name | Products | Lead Time | Variability | Reliability | Min Order |
|------|------|----------|-----------|-------------|-------------|-----------|
| TYSON | Tyson Foods | FP001, FP002 | 7 days | 20% | 95% | $2,000 |
| KRAFT | Kraft Heinz | FD001, FD003 | 10 days | 15% | 97% | $1,500 |
| GENMILLS | General Mills | DP003, DP004 | 8 days | 18% | 96% | $1,200 |
| NESTLE | Nestle USA | FD002, DP005 | 12 days | 22% | 94% | $2,500 |
| TROP | Tropicana | BV001, BV003 | 5 days | 15% | 98% | $1,000 |
| SYSCOMEAT | Sysco Meat Co | FP003, FP005 | 9 days | 20% | 94% | $3,000 |
| LANDOLAKES | Land O'Lakes | RD004, RD005 | 6 days | 12% | 97% | $1,500 |
| CONAGRA | ConAgra Brands | RD001, DP001 | 8 days | 18% | 95% | $1,800 |
| RICHPROD | Rich Products | RD002, RD003 | 10 days | 20% | 95% | $2,000 |
| COCACOLA | Coca-Cola Co | BV004, BV005 | 4 days | 10% | 99% | $1,200 |

#### Customers (14 external trading partners)

| Code | Name | Segment | Size | Region | Demand Mult | Order Freq |
|------|------|---------|------|--------|-------------|------------|
| CUST_PDX | Portland Restaurant Supply | Restaurant Supply | large | NW | 1.5x | weekly |
| CUST_EUG | Eugene Organic Cooperative | Natural/Specialty | medium | NW | 1.2x | weekly |
| CUST_SAL | Salem School District | Institutional | small | NW | 1.0x | weekly |
| CUST_SEA | Seattle Metro Grocery | Retail Chain | large | NW | 0.6x | bi-weekly |
| CUST_TAC | Tacoma Fresh Foods | Retail | medium | NW | 1.1x | weekly |
| CUST_SPO | Spokane Hospitality Group | Hotel/Hospitality | medium | NW | 0.8x | weekly |
| CUST_RNO | Reno Fresh Markets | Natural/Specialty | small | NW | 0.75x | weekly |
| CUST_LAX | QUICKSERV SoCal | Quick Service Restaurant | large | SW | 2.0x | weekly |
| CUST_SFO | Bay Area Bistro Group | Fine Dining | medium | SW | 0.9x | weekly |
| CUST_SDG | San Diego Catering Co | Catering/Events | large | SW | 1.4x | weekly |
| CUST_SAC | Sacramento Valley Foods | Distributor | medium | SW | 1.0x | weekly |
| CUST_PHX | Phoenix QUICKSERV | Quick Service Restaurant | large | SW | 1.8x | weekly |
| CUST_TUS | Green Valley Markets | Natural/Specialty | small | SW | 0.7x | bi-weekly |
| CUST_MES | Mesa Convention Services | Convention/Events | medium | SW | 1.1x | weekly |

> **Customer Churn**: CUST_SAL (Salem) is lost at month 8, CUST_TUS (Tucson) at month 14. CUST_RNO (Reno) is gained at month 10. This creates realistic demand volatility that isn't visible in the static customer list.

---

### Products (25 SKUs across 5 categories)

| Group Code | Category | Temperature | SKUs | Weekly Demand Range | Shelf Life Range |
|------------|----------|-------------|------|--------------------|-----------------|
| FRZ_PROTEIN | Frozen Proteins | FROZEN | FP001-FP006 | 25-150 cases | 180-365 days |
| REF_DAIRY | Refrigerated Dairy | REFRIGERATED | RD001-RD005 | 100-300 cases | 45-180 days |
| DRY_PANTRY | Dry Pantry | AMBIENT | DP001-DP005 | 120-200 cases | 365-1,095 days |
| FRZ_DESSERT | Frozen Desserts | FROZEN | FD001-FD005 | 35-80 cases | 270-365 days |
| BEV | Beverages | CHILLED | BV001-BV005 | 60-220 cases | 45-90 days |

**Demand coefficient of variation**: 0.20 (butter, coffee) to 0.60 (Wagyu Beef NPI) — higher CV products are harder to forecast and have more safety stock requirements. The Wagyu Beef NPI (FP006) has the highest CV at 0.60 due to new product demand uncertainty.

---

### 2-Year Transactional History (16 Entity Types)

The history generator creates 730 days of realistic transactional data. All records have `source="HISTORY_GEN"` for traceability.

#### Entity Record Counts (approximate)

| Entity | Records | Purpose |
|--------|---------|---------|
| **OutboundOrderLine** | ~12,000 | Customer demand (with ~180 cancelled) |
| **FulfillmentOrder** | ~11,800 | Warehouse pick/pack/ship |
| **Shipment** (outbound) | ~2,500 | Material movement to customers |
| **ShipmentLot** | ~30,000 | Food lot traceability (batch, expiry) |
| **Backorder** | ~350 | Unfulfilled demand |
| **InboundOrder** | ~1,200 | Supplier POs + inter-DC transfers |
| **InboundOrderLine** | ~4,500 | PO/transfer line items |
| **InboundOrderLineSchedule** | ~2,500 | Split delivery schedules (promised vs actual) |
| **PurchaseOrder** | ~1,000 | Typed PO records (FK base for GR) |
| **PurchaseOrderLineItem** | ~2,500 | PO line items with pricing |
| **GoodsReceipt** | ~1,000 | Supplier receipt with inspection |
| **GoodsReceiptLineItem** | ~2,500 | Receipt lines: accepted/rejected/variance |
| **QualityOrder** | ~300 | Incoming quality inspection lots |
| **QualityOrderLineItem** | ~900 | Inspection characteristics (temp, visual, weight, micro) |
| **TransferOrder** | ~500 | CDC→RDC inter-DC transfers |
| **TransferOrderLineItem** | ~2,000 | Transfer lines with damage tracking |
| **MaintenanceOrder** | ~150 | Cold chain equipment PM/corrective/emergency |
| **InvLevel** | ~55,000 | Daily inventory snapshots (3 sites x 25 SKUs x 730 days) |
| **Forecast** | ~38,000 | Daily P10/P50/P90 forecasts |
| **ConsensusDemand** | ~1,800 | Monthly S&OP consensus |
| **SupplementaryTimeSeries** | ~600 | External signals (promos, weather, market) |
| **InventoryProjection** | ~7,800 | Weekly ATP/CTP with stochastic bands |

**Total**: ~175,000+ records

---

### Demand Model

The demand model produces realistic customer ordering patterns with multiple signal components:

#### Base Demand Formula

```
demand = base × season × trend × holiday × promo × noise
```

| Component | Description |
|-----------|-------------|
| **Base** | `weekly_demand_mean / 5 × demand_multiplier` (normalized across all customers) |
| **Seasonality** | Monthly profile per product group (e.g., frozen desserts: 0.70 in Jan → 1.40 in Jul → 1.00 in Dec) |
| **Trend** | 2% annual growth: `1.0 + 0.02 × (day_offset / 365)` |
| **Holiday spikes** | 8 holidays with category-specific multipliers and lead-in ramp windows |
| **Promotional lifts** | 3% daily probability, 15-40% lift for 5-10 days, correlated with SupplementaryTimeSeries |
| **Noise** | Log-normal (right-skewed): `lognormvariate(μ, σ)` where `σ = demand_cv × 0.4` |

#### Day-of-Week Weights

| Mon | Tue | Wed | Thu | Fri |
|-----|-----|-----|-----|-----|
| 1.30 | 1.15 | 1.05 | 0.95 | 0.55 |

#### Holiday Spike Calendar

| Holiday | Month/Day | Affected Groups | Multiplier | Lead-in Window |
|---------|-----------|----------------|------------|----------------|
| Thanksgiving | Nov 22 | FRZ_PROTEIN, REF_DAIRY, DRY_PANTRY, FRZ_DESSERT | 1.45x | 14 days |
| Christmas | Dec 25 | All 5 groups | 1.40x | 14 days |
| July 4th | Jul 4 | FRZ_PROTEIN, BEV, FRZ_DESSERT | 1.35x | 10 days |
| Super Bowl | Feb 9 | FRZ_PROTEIN, BEV, FRZ_DESSERT, REF_DAIRY | 1.30x | 7 days |
| Back-to-School | Aug 20 | DRY_PANTRY, REF_DAIRY, BEV | 1.25x | 14 days |
| Memorial Day | May 27 | FRZ_PROTEIN, BEV | 1.25x | 7 days |
| Easter | Apr 13 | REF_DAIRY, FRZ_DESSERT, FRZ_PROTEIN | 1.20x | 10 days |
| Labor Day | Sep 1 | FRZ_PROTEIN, BEV, FRZ_DESSERT | 1.20x | 7 days |

#### Basket Correlations

When one product is in a customer order, its basket partner has a pull-in probability:

| Product A | Product B | Pull-in Probability |
|-----------|-----------|-------------------|
| Chicken IQF (FP001) | Cheddar (RD001) | 60% |
| Ice Cream (FD001) | Gelato (FD003) | 70% |
| Flour (DP003) | Sugar (DP004) | 60% |
| Beef Patties (FP002) | Mozzarella (RD002) | 50% |
| OJ (BV001) | Lemonade (BV003) | 50% |
| Pasta (DP001) | Cream Cheese (RD003) | 40% |
| Pork Chops (FP003) | Rice (DP002) | 35% |
| Chicken IQF (FP001) | Iced Tea (BV004) | 30% |

#### New Product Introduction (NPI): Wagyu Beef Strips A5 (FP006)

The Frozen Proteins group includes one NPI product — **Wagyu Beef Strips A5** — launched 3 weeks before the end of the 2-year history window. This demonstrates realistic cold-start demand patterns that the TRMs and forecast models must handle.

| Attribute | Value |
|-----------|-------|
| **SKU** | FP006 |
| **Name** | Wagyu Beef Strips A5 |
| **Description** | Premium Japanese A5 Wagyu beef strips, frozen |
| **Unit Size** | 5 lb case |
| **Unit Cost / Price** | $125.00 / $169.99 (highest-margin protein) |
| **Shelf Life** | 180 days |
| **Steady-State Demand** | 25 cases/week (low volume, premium niche) |
| **Demand CV** | 0.60 (highest variability — new product uncertainty) |
| **Supplier** | SYSCOMEAT (Sysco Protein Solutions) |
| **Launch** | Day 709 of 730-day history (~3 weeks before end) |

**Ramp-up behavior**:
- **Days 1-709**: Zero demand (product does not exist)
- **Days 709-723** (2-week ramp): S-curve (smoothstep) from 0% to 100% of base demand
- **Initial stocking multiplier**: 2.5x during ramp (pipeline fill for DCs and customers)
- **Noise during ramp**: 50% higher CV than steady-state (NPI demand uncertainty)
- **Days 723-730**: Full steady-state demand at 25 cases/week base

**Basket correlation**: Wagyu has a 25% pull-in probability when Chicken IQF (FP001) is ordered — premium protein upsell opportunity.

**Why this matters for the platform**: NPI products have no forecast history, so the TRM forecast adjustment agent must rely on analogous product data and the conformal prediction bands will be wider. The initial stocking multiplier creates a demand spike that differs from steady-state, testing the inventory buffer TRM's ability to distinguish launch fills from run-rate orders.

#### Order Cancellations

1.5% of outbound order lines are cancelled — these appear with `status=CANCELLED` and zero shipped/promised quantities. Cancelled lines skip fulfillment and shipment generation.

---

### Supplier Lead Time Model

Lead times use **log-normal distributions** instead of Gaussian, producing realistic right-skewed behavior:

```python
σ = supplier.lead_time_variability
μ = ln(lead_time_days) - 0.5 × σ²
lt_actual = lognormvariate(μ, σ)
```

**Additional effects**:
- **Q4 freight slowdown** (Oct-Dec): 5-15% multiplier on all lead times
- **Extreme outlier events** (3% probability): 1.5-3.0x delay (weather, port congestion, carrier failure)

This produces lead time distributions with realistic fat tails — most deliveries are on time, but a meaningful minority have significant delays.

---

### Goods Receipt & Quality Inspection Pipeline

The GR pipeline models real-world receiving dock operations:

```
PurchaseOrder → GoodsReceipt(s) → GoodsReceiptLineItem(s) → QualityOrder(s) → QualityOrderLineItem(s)
```

#### Goods Receipt Split Deliveries

| Delivery Pattern | Probability | Split |
|-----------------|-------------|-------|
| Single delivery | 70% | 100% |
| 2-split | 25% | 60/40 |
| 3-split | 5% | 50/30/20 |

#### Inspection Outcomes (on 30% of lines requiring inspection)

| Status | Rate | Outcome |
|--------|------|---------|
| PASSED | 85% | Full acceptance |
| PARTIAL | 7% | 2-8% rejection (QUALITY or DAMAGED) |
| FAILED | 8% | 10-30% rejection (QUALITY, DAMAGED, or WRONG_ITEM) |

#### Quality Order Characteristics

Each QO has 2-4 inspection characteristics:

| Check | Type | When | Pass Criteria |
|-------|------|------|--------------|
| Temperature | QUANTITATIVE | Frozen/Refrigerated products | Within ±5°F of target |
| Visual Inspection | QUALITATIVE | All products | No visible damage |
| Weight Verification | QUANTITATIVE | All products | Within ±3% of target |
| Microbiological | QUANTITATIVE | Perishables (50% sample) | < 10,000 CFU/g |

#### Quality Disposition Decisions

| Disposition | For PASSED | For PARTIAL | For FAILED |
|-------------|-----------|-------------|------------|
| ACCEPT | 100% | 33% | — |
| CONDITIONAL_ACCEPT | — | 33% | — |
| USE_AS_IS | — | 33% | — |
| REJECT | — | — | 40% |
| RETURN_TO_VENDOR | — | — | 30% |
| REWORK | — | — | 20% |
| SCRAP | — | — | 10% |

---

### Transfer Orders (Inter-DC Movement)

Weekly CDC_WEST → RDC_NW and CDC_WEST → RDC_SW transfers with:

- **Log-normal transit time**: 1.5-day base, Q4 slowdown
- **2% damage rate**: Cold chain transit damage (1-5% of line quantity)
- **Status distribution**: 95% RECEIVED, 3% SHIPPED (in-transit), 2% CANCELLED

---

### Cold Chain Maintenance

10 equipment assets across 3 sites with realistic maintenance patterns:

| Equipment Type | Sites | PM Frequency | Corrective Rate | Emergency Rate |
|---------------|-------|-------------|----------------|---------------|
| Walk-in Freezer | CDC, NW, SW | 90 days | 4%/month | 20% of corrective |
| Compressor | CDC, NW, SW | 60 days | 4%/month | 20% of corrective |
| Dock Equipment | CDC | 120 days | 2%/month | 20% of corrective |
| Conveyor | CDC | 45 days | 2%/month | 20% of corrective |

**Downtime characteristics**:
- Preventive: 2-4 hours (log-normal variance)
- Corrective: 4-16 hours
- Emergency: can exceed 24 hours (cold chain product at risk)

**Cost ranges**:
- Preventive: $200-$500
- Corrective: $500-$5,000
- Emergency: $1,000-$15,000+

---

### Seasonality Profiles

Monthly demand multipliers by product group (1.0 = average):

| Month | FRZ_PROTEIN | REF_DAIRY | DRY_PANTRY | FRZ_DESSERT | BEV |
|-------|-------------|-----------|------------|-------------|-----|
| Jan | 0.85 | 1.05 | 0.90 | 0.70 | 0.75 |
| Feb | 0.85 | 1.00 | 0.90 | 0.75 | 0.80 |
| Mar | 0.90 | 0.95 | 0.95 | 0.85 | 0.90 |
| Apr | 0.95 | 0.95 | 0.95 | 0.95 | 1.00 |
| May | 1.05 | 1.00 | 1.00 | 1.10 | 1.15 |
| Jun | 1.15 | 1.00 | 1.00 | 1.30 | 1.30 |
| Jul | 1.25 | 1.00 | 1.00 | 1.40 | 1.40 |
| Aug | 1.15 | 1.00 | 1.00 | 1.30 | 1.35 |
| Sep | 1.00 | 0.95 | 1.00 | 1.05 | 1.10 |
| Oct | 0.90 | 0.95 | 1.05 | 0.85 | 0.90 |
| Nov | 1.10 | 1.05 | 1.10 | 0.90 | 0.80 |
| Dec | 1.20 | 1.10 | 1.15 | 1.00 | 0.75 |

Key patterns: Frozen desserts and beverages peak in summer (Jul: 1.40x). Frozen proteins peak at Thanksgiving/Christmas. Dairy is relatively stable year-round. Dry pantry ramps in Q4 (holiday baking).

---

### Comparison: Food Dist vs SAP Demo Data

| Dimension | Food Dist (Synthetic) | SAP Demo (Real S/4HANA) |
|-----------|-----------------------|------------------------|
| **Network** | 3 internal sites, 10 suppliers, 14 customers | ~50 plants, 500+ vendors, 300+ customers |
| **Products** | 25 SKUs, 5 categories | 1,100+ materials |
| **BOMs/Routings** | None (distributor) | 50+ BOMs, 30+ routings |
| **Production** | None | 1,124 orders, 1,657 confirmations |
| **Demand history** | ~12K orders (synthetic, with holidays/churn/promos) | 8,551 SO lines (real) |
| **Lead time model** | Log-normal from config params | Empirical from 17,976 goods receipts |
| **Quality inspection** | ~300 QOs with 4 characteristic types | 251 QALS lots |
| **Goods receipts** | ~1,000 GRs with inspection | 17,976 EKBE records |
| **Maintenance** | 150 cold chain orders | QMEL notifications (MTBF/MTTR) |
| **Transfers** | ~500 CDC→RDC | Inferred from EKPO/LIKP |
| **Forecasts** | 38K with P10/P50/P90, error, bias | PBIM/PBED (quantity only) |
| **Inventory snapshots** | 55K daily | MARD current only |
| **External signals** | 600 (promo, weather, market, econ) | None |

**Food Dist strengths**: Richer forecast data (probabilistic), daily inventory history, external signals, complete lot traceability, food-safety-specific quality checks (temperature, microbiological).

**SAP strengths**: Real operational data with natural variability, manufacturing/BOM depth, larger network scale, empirical (not parametric) lead time distributions.

**Demo talking point**: "Layer 1 signals are reactive — one TRM tells another 'I just did X'. Layer 2 is predictive — the graph network learns that when ATP fulfills aggressively for 3 cycles, MO capacity gets starved on cycle 4. It adjusts urgency *before* the problem manifests."

---

## Recommended Demo Flow (20 minutes)

> **For a shorter 4-5 minute video** (azirella.com, LinkedIn, YouTube), use the [Decision-First Demo Script](demos/Decision_First_Demo_Script.md) instead. It starts with the Decision Stream and focuses on decisions, reasoning, and the override learning loop — showing the traditional UI only as a "safety net."

For a concise demo, follow this path:

| Step | Duration | Page | What to Show |
|------|----------|------|-------------|
| 0 | 2 min | Decision Stream (`/decision-stream`) | **Start here.** Scroll through decision cards, click Ask Why on a PO decision, show pre-computed reasoning |
| 1 | 1 min | Network Topology (`/admin/tenant/supply-chain-configs`) | Orient: hub-and-spoke, 26 products, 10 suppliers, 10 customers |
| 2 | 2 min | Executive Dashboard (`/executive-dashboard`) | KPIs: service level 94.2%, agent score 72, override rate 18% |
| 3 | 3 min | Strategy Briefing (`/strategy-briefing`) | Weekly narrative, 5 recommendations, Q&A drill-down |
| 4 | 3 min | S&OP Worklist (`/sop-worklist`) | 6 strategic items, accepted/pending/auto-executed statuses |
| 5 | 3 min | MPS Worklist (`/insights/actions`) | 15 agent decisions, demo the override story (Metro Grocery) |
| 6 | 2 min | ATP Worklist (`/planning/execution/atp-worklist`) | Priority-based allocation, P1-P5 fulfillment |
| 7 | 2 min | PO Worklist (`/planning/execution/po-worklist`) | Emergency vs standard POs, cost trade-offs |
| 8 | 2 min | Agent Performance (`/agent-performance`) | Category scores, override rates, automation % |
| 9 | 2 min | RLHF Feedback (`/admin/rlhf`) | Bayesian posteriors, judgment capture flywheel |

---

## Troubleshooting

### "No briefings found" or empty pages
Re-run the seed script:
```bash
docker compose exec backend python -m scripts.seed_food_dist_deep_demo
```

### Tenant or config not found
Ensure the base Food Dist infrastructure is seeded:
```bash
docker compose exec backend python -m scripts.seed_food_dist_demo
docker compose exec backend python -m scripts.seed_food_dist_planning_data
```

### Users not found
The seed script will fall back to the admin user for missing role users. Ensure `seed_food_dist_demo.py` has been run to create all demo users.

### Re-running after changes
The script is idempotent — it deletes action layer data for the demo date range (Feb 24-28, 2026) before reinserting. Infrastructure data (configs, forecasts, supply plans, hierarchies) is never touched.

---

## Files Reference

| File | Purpose |
|------|---------|
| `backend/scripts/warm_start_food_dist.py` | **Unified 6-phase warm-start pipeline** (trains + seeds) |
| `backend/scripts/seed_food_dist_deep_demo.py` | Action layer seed (this demo's data) |
| `backend/scripts/seed_food_dist_demo.py` | Tenant, users, config (prerequisite) |
| `backend/scripts/seed_food_dist_planning_data.py` | Forecasts, inv policies, supply plans |
| `backend/scripts/seed_food_dist_hierarchies.py` | Site/product hierarchies |
| `backend/scripts/seed_food_dist_transactions.py` | Historical orders/shipments |
| `backend/scripts/seed_food_dist_execution_data.py` | Base Powell decisions, agent configs |
| `backend/scripts/seed_food_dist_allocation_demo.py` | Allocation demo scenarios |
| `docs/FOOD_DIST_DEMO_GUIDE.md` | This guide |

### Makefile Targets

| Target | What it does |
|--------|-------------|
| `make warm-start-food-dist-full` | Full 6-phase pipeline (train all + enable Site tGNN + seed) |
| `make warm-start-food-dist-quick` | Quick warm-start (10 epochs, phases 1,3,5,6) |
| `make warm-start-food-dist-train` | Training only (phases 1-4, no seeding) |
| `make warm-start-food-dist-enable` | Enable Site tGNN + seed demo data (phases 5-6) |

---

## Screenshot Capture Guide

To complete this document for external distribution, capture the following 13 screenshots. Login as `admin@distdemo.com` (password: `Autonomy@2026`) at `http://localhost:8088`.

**Prerequisites**: Run all three seed scripts first:
```bash
docker compose exec backend python -m scripts.seed_food_dist_demo
docker compose exec backend python -m scripts.seed_food_dist_planning_data
docker compose exec backend python -m scripts.seed_food_dist_deep_demo
```

| # | Screen | Navigation | Key Elements to Capture |
|---|--------|-----------|------------------------|
| 1 | Network Topology | Admin > SC Configs > "Food Dist" > Network tab | Sankey diagram: 10 suppliers → DC → 10 customers |
| 2 | Executive Dashboard | Insights > Executive Dashboard | KPI cards: service 94.2%, agent score 72, override 18% |
| 3 | Strategy Briefing | Insights > Strategy Briefing | Weekly narrative + 5 scored recommendations + Q&A |
| 4 | S&OP Worklist | Insights > S&OP Worklist | 6 items with accepted/pending/auto-executed badges |
| 5 | MPS Worklist (Agent Decisions) | Insights > MPS Worklist | 15 decisions, show expanded card + Metro Grocery override |
| 6 | Condition Alerts | Insights > Exception Detection | 8 alerts with severity colors and duration bars |
| 7 | Scenario Evaluation | Insights > Scenario Comparison | Rich Products 3-scenario comparison with scores |
| 8 | ATP Worklist | Cascade > ATP Worklist | Priority P1-P5 rows with fill percentage bars |
| 9 | PO Worklist | Cascade > PO Worklist | Emergency vs standard POs with urgency badges |
| 10 | Rebalancing Worklist | Cascade > Rebalancing Worklist | 4 transfers with from/to arrows and DOS impact |
| 11 | Order Exceptions | Cascade > Order Tracking Worklist | 5 exception types with badges and actions |
| 12 | Agent Performance | Insights > Agent Performance | Category scores, override rates, automation % |
| 13 | Override Effectiveness | AI & Agents > RLHF Feedback | Bayesian posteriors for 3 users |

**Optional additional screenshots** (for appendix or extended version):

| # | Screen | Navigation | When Useful |
|---|--------|-----------|------------|
| 14 | Demand Planning | Planning > Demand Planning | Show P10/P50/P90 forecast intervals |
| 15 | Inventory Optimization | Planning > Inventory Optimization | Show safety stock policies |
| 16 | Decision Cascade (ADH) | AI & Agents > Decision Cascade | Show 3-tier architecture diagram |
| 17 | TRM Training Dashboard | AI & Agents > Execution Agents | Show agent training interface |
| 18 | Risk Analysis | Insights > Risk Analysis | Show risk scoring dashboard |
| 19 | Collaboration Hub | Planning > Collaboration Hub | Show messaging and comments |
| 20 | Supply Plan | Planning > Supply Planning | Show generated PO/TO/MO requests |

![Azirella](../Azirella_Logo.jpg)

> **STRICTLY CONFIDENTIAL AND PROPRIETARY**
> Copyright © 2026 Azirella Ltd. All rights reserved worldwide.
> Unauthorized access, use, reproduction, or distribution of this document or any portion thereof is strictly prohibited and may result in severe civil and criminal penalties.

# Autonomy: Strategic Overview for Executive Leadership

**Document Classification**: Executive Summary
**Version**: 2.0
**Date**: February 9, 2026
**Prepared for**: CEO / Board Review

---

## Executive Summary

**What We Are**: An autonomous supply chain planning and execution platform that replaces manual planning workflows with AI agents operating at machine speed, governed by a comprehensive supply chain data model.

**What Makes Us Different**: Four architectural innovations that no incumbent offers as an integrated system:

| Innovation | What It Does | Why It Matters |
|-----------|-------------|----------------|
| **LLM-First UI** | Conversational interface replaces point-and-click planning | 80% of decisions automated; 10,080x faster response cycle |
| **Powell Framework** | Three-tier AI architecture (Strategic → Tactical → Execution) with formal policy optimization | Vertically integrated AI from S&OP down to individual order promising |
| **Capable-to-Promise (CTP)** | Multi-stage network traversal with full-level pegging | Every unit traceable from customer order through factory to vendor; promise dates reflect reality |
| **Agentic Authorization Protocol** | Agents negotiate cross-functional trade-offs at machine speed | Resolves conflicts (cost vs. service, allocation vs. expedite) in seconds, not days |

**Strategic Position**: We are not building a better spreadsheet or a cheaper Kinaxis. We are building the first platform where AI agents autonomously run supply chain operations, using CTP as their decision basis and the balanced scorecard as their shared language, with humans overseeing outcomes rather than making individual decisions.

---

## Part 1: Diagnosis

*Per Rumelt's framework: A good strategy starts with honest diagnosis of the challenge.*

### The Planning Software Market

**Market Structure**:
- $15B annual market for enterprise planning software
- Dominated by Kinaxis RapidResponse, SAP IBP, and OMP Plus
- License costs: $100K-$500K per user/year
- Implementation: 12-18 months, $2-5M+ consulting fees
- 60% of mid-market companies still use Excel

**Customer Pain Points**:
1. **Point-and-Click Paralysis**: Planners review 500+ exception reports weekly, manually adjusting plans in spreadsheets. 80% of time spent on routine decisions.
2. **Batch Planning Latency**: Tuesday's urgent order doesn't get addressed until Friday's plan approval. 5-day OODA loop in a world that moves in hours.
3. **Siloed Decisions**: Supply planners optimize independently of logistics, finance, and sales. Cross-functional trade-offs require emails, meetings, and days of delay.
4. **No Supply Chain Traceability**: When a customer asks "when will my order ship?", the answer requires manually checking inventory, factory capacity, vendor lead times, and component availability across multiple systems.
5. **Black Box AI**: Where AI exists, recommendations lack explainability; planners override 60%+ of suggestions because they don't understand the reasoning.

### Our Thesis

The fundamental problem is not that planners lack tools -- it's that **humans are the bottleneck**. The planning task is sequential, cross-functional, and time-sensitive. Humans do it slowly, in silos, using point estimates. The answer is not better forms and dashboards. The answer is autonomous agents that can:

1. **See the full picture** -- CTP traces every unit from customer to vendor; the balanced scorecard shows impact across all four dimensions (Financial, Customer, Operational, Strategic)
2. **Act across functions** -- The Agentic Authorization Protocol lets agents negotiate cost-vs-service trade-offs in seconds
3. **Explain their reasoning** -- LLM-first interface means every decision is inspectable in natural language
4. **Learn from humans** -- Override capture trains agents continuously; human expertise becomes a compounding asset

---

## Part 2: The Four Architectural Innovations

### Innovation 1: LLM-First UI

**Core Idea**: Replace traditional point-and-click planning with a conversational, agent-orchestrated interface.

**The AIIO Paradigm** (Automate-Inform-Inspect-Override):

| Stage | What Happens | Example |
|-------|-------------|---------|
| **Automate** | Agents detect events, analyze impact, and execute within guardrails | Supplier delay detected → backup vendor expedited ($500) → stockout prevented |
| **Inform** | Users notified of actions taken, grouped by priority | "3 high-priority actions taken this morning. Net savings: $71K." |
| **Inspect** | On-demand drill into reasoning, alternatives considered, trade-offs | "Show me why you chose Vendor-B" → full decision trace with probabilities |
| **Override** | Human reverses or modifies any decision; reason captured for learning | "Use Vendor-A instead -- strategic relationship" → override stored for RL training |

**Performance vs. Legacy**:

| Metric | Weekly Batch (Legacy) | Autonomy (LLM-First) |
|--------|----------------------|----------------------|
| Event-to-action time | 5-7 days | 60 seconds |
| Planner time on routine decisions | 80% | 20% (oversight only) |
| Cross-functional resolution | Days (emails, meetings) | Seconds (agent negotiation) |
| Actionable recommendation rate | 1.7% (single-agent) | 100% (multi-agent consensus) |
| Uncertainty handling | Point estimates | P10/P50/P90 with conformal prediction |

**How It Works in Practice**:

```
Human:  "What's happening on the authorization board right now?"

Agent:  "3 active threads:
         1. SO Agent requesting expedite ($2,400) from Logistics for order 8834.
            Net benefit: +$15,600. Status: PENDING (2 min).
         2. Allocation Agent requesting policy exception from S&OP for
            strategic over-allocation. Net benefit: +$22,000. Status: COUNTER_OFFERED.
         3. Plant Agent requesting maintenance window from Supply Agent.
            Status: AUTHORIZED, executing Saturday.

         Thread #1 expires in 28 minutes. Want me to show the scorecard?"
```

**Key Insight**: The LLM is not a chatbot bolted onto existing screens. The Board Service (authorization threads, decision records, scorecards) is the data model. The LLM chat interface, the React dashboards, and the agent-to-agent protocol are three adapters over the same substrate. A single authorization thread might be created by an agent, counter-offered by another agent, escalated to a human reviewing a dashboard, and resolved via a chat message -- all stored in the same data structure.

**Reference**: [LLM-First Execution Planning Proposal](architecture/LLM_FIRST_EXECUTION_PLANNING_PROPOSAL.md)

---

### Innovation 2: Powell Framework for Vertical Integration

**Core Idea**: A three-tier AI architecture based on Warren B. Powell's Sequential Decision Analytics framework that vertically integrates strategic, tactical, and execution planning.

**The Three Tiers**:

```
┌─────────────────────────────────────────────────────────────────┐
│  S&OP GraphSAGE (CFA - Cost Function Approximation)            │
│  ─────────────────────────────────────────────────────────────  │
│  Computes policy parameters θ: safety stock multipliers,        │
│  criticality scores, risk scores, allocation reserves           │
│  Updated: Weekly/monthly (strategic timescale)                  │
│  Powell Class: CFA -- parameterized cost function with          │
│  tunable θ, optimized over Monte Carlo scenarios                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ θ parameters flow down
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Execution tGNN (CFA/VFA Bridge)                                │
│  ─────────────────────────────────────────────────────────────  │
│  Generates Priority × Product × Location allocations            │
│  Consumes S&OP embeddings + transactional data                  │
│  Updated: Daily (operational timescale)                         │
│  Powell Class: VFA -- approximate V(S) using neural network     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Allocations + context flow down
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Narrow TRM Services (VFA - Value Function Approximation)       │
│  ─────────────────────────────────────────────────────────────  │
│  ├── ATPExecutorTRM: Priority-based order promising (<10ms)        │
│  ├── InventoryRebalancingTRM: Cross-location transfers          │
│  ├── POCreationTRM: Purchase order timing and quantity           │
│  └── OrderTrackingTRM: Exception detection and response         │
│  Updated: Real-time (execution timescale)                       │
│  Powell Class: VFA -- Q(s,a) approximation via transformer      │
└─────────────────────────────────────────────────────────────────┘
```

**Why This Matters**:

| Approach | How Decisions Are Made | Limitation |
|----------|----------------------|------------|
| **Legacy MRP** | Batch netting with point estimates | No optimization; no uncertainty; no cross-tier consistency |
| **Kinaxis** | Concurrent planning with scenario comparison | Human-mediated; scenario evaluation not optimization |
| **Single AI Agent** | One model tries to do everything | Too many variables; intractable for RL; brittle |
| **Powell 3-Tier** | Strategic AI sets policy → Tactical AI allocates → Execution AI decides | Each tier has narrow, tractable scope; hierarchical consistency enforced |

**The Key Powell Insight**: Higher planning levels (longer horizons, aggregated data) should optimize **policy parameters** (CFA). Lower levels (short horizons, detailed data) should approximate **value functions** for immediate decisions (VFA). This matches how human organizations work -- the VP sets strategy (parameters), the director translates to plans (allocations), the analyst executes individual orders (decisions) -- but at machine speed with formal consistency guarantees.

**Event-Driven Replanning**: The system doesn't just run on cadence. CDC (Change Data Capture) monitors detect metric deviations and trigger out-of-cadence replanning:

| Metric | Threshold | Trigger |
|--------|-----------|---------|
| Demand vs. Forecast | ±15% cumulative | Full CFA rerun |
| Service Level | < (Target - 5%) | Full CFA rerun |
| Inventory vs. Target | < 70% or > 150% | Allocation rerun |
| Lead Time | +30% vs. expected | Parameter adjustment |

**Reference**: [Powell Framework Integration Strategy](../POWELL_APPROACH.md)

---

### Innovation 3: Capable-to-Promise as Decision Basis

**Core Idea**: Every supply chain decision is grounded in a multi-stage traversal of the network DAG that traces every unit from customer order through factories and DCs to vendor lead times. CTP is not a feature -- it is the basis for all agent decision-making.

**How Multi-Stage CTP Works**:

```
Customer Order (Product P, 100 units, Site DC-East)
        │
        ▼
[DC-East (INVENTORY)]
  On-hand: 200, Committed: 150, Safety Stock: 30
  Available: 20 units
  Shortfall: 80 units → check upstream
        │
        ▼
[Factory-Central (MANUFACTURER)]
  BOM: Product P = 2× Component A + 1× Component B
  Capacity: 500/week, Yield: 95%
  Need: 160 of A, 80 of B
  Lead time: 3 days manufacturing
        │
        ├──→ [Vendor-Steel (MARKET_SUPPLY)]
        │     Component A available: 400 units
        │     Lead time: 5 days
        │
        └──→ [Vendor-Plastic (MARKET_SUPPLY)]
              Component B available: 100 units
              Lead time: 7 days

Result:
  CTP Qty: 100 (feasible)
  Cumulative Lead Time: max(5,7) + 3 = 10 days
  Binding Constraint: Vendor-Plastic (7-day lead time)
  Promise Date: Today + 10 days
```

**Full-Level Pegging**: Every CTP result creates a pegging chain with a unique `chain_id` that links demand to supply across all stages:

```
chain_id: "a1b2c3d4..."
depth=0: Customer Order ORD-001 → On-hand at DC-East          qty=20
depth=1: Transfer Order TO-001  → Manufacturing Order MO-001    qty=80
depth=2: Purchase Order PO-001  → Vendor PO PO-V001            qty=160 (BOM 2:1)
```

**Why CTP Is the Decision Basis**:

Every agent action -- promising an order, expediting a PO, rebalancing inventory, negotiating allocation -- begins with a CTP calculation that shows the full upstream impact:

| Agent Action | CTP Provides |
|-------------|-------------|
| **Promise an order** | Feasible quantity, promise date, binding constraint |
| **Request expedite** | Which stage is the bottleneck; cost of reducing lead time there |
| **Rebalance inventory** | Whether transferring from Site A to Site B creates a shortfall upstream |
| **Negotiate allocation** | Which customers are pegged to which supply; impact of reallocation |
| **Create purchase order** | Component requirements exploded through BOM with vendor lead times |

**CTP feeds the Balanced Scorecard**: When an agent evaluates a what-if scenario, CTP calculates the impact on promise dates, supply availability, and capacity utilization. The scorecard reflects these in real-time across all four dimensions (Customer: OTIF projection; Financial: expedite cost; Operational: capacity at binding stage; Strategic: supply concentration risk).

**Binding Constraint Resolution**: When CTP identifies a constraint, the responsible agent is determined by the constraint type:

| Binding Constraint | Responsible Agent | Resolution Options |
|--------------------|-------------------|-------------------|
| Inventory shortage at DC | Inventory Agent | Cross-DC transfer, safety stock exception |
| Capacity limit at factory | Plant Agent | Overtime, alternate line, outsource |
| Component shortage | Supply Agent | Rush PO, alternate supplier, substitution |
| Vendor lead time | Procurement Agent | Expedite fee, alternate vendor |
| Transportation delay | Logistics Agent | Mode upgrade, alternate route |

This is where CTP connects to the Agentic Authorization Protocol: the binding constraint identifies *which* agent to negotiate with, and the balanced scorecard provides the shared language for the negotiation.

**Reference**: [CTP Capabilities](CTP_CAPABILITIES.md)

---

### Innovation 4: Agentic Authorization Protocol (AAP)

**Core Idea**: When an AI agent's best option requires action in another agent's domain, a structured protocol resolves the conflict at machine speed -- with full transparency and human escalation only when agents can't agree.

**The Problem It Solves**: Supply chain decisions rarely affect a single function. An SO Agent fulfilling a strategic customer's urgent order might:

| Option | Action | Impact |
|--------|--------|--------|
| A | Reallocate from lower-priority order | Customer delayed 3 days |
| B | Expedite delivery | $2,400 cost; logistics budget at 78% |
| C | Transfer from regional DC | Safety stock depleted by 40% |

Option A is within the SO Agent's authority. Options B and C require authorization from Logistics and Inventory agents respectively. In legacy systems, this takes hours to days (emails, meetings, approvals). With AAP, it takes seconds.

**Protocol Flow**:

```
Phase 1: EVALUATE              Phase 2: REQUEST           Phase 3: AUTHORIZE
(originating agent)            (cross-authority)          (target agent)

Run what-if on all options  →  Send AuthorizationRequest  →  Check resource
(full balanced scorecard)      with scorecard + net benefit   availability + contention
                                                              │
Select best option          →  Include justification      →  AUTHORIZE or
(may cross authority)          for amber/red flags            COUNTER-OFFER or
                                                              DENY
                                                              │
                                                              If DENY and net benefit
                                                              > threshold → ESCALATE
                                                              to human
```

**The Critical Insight**: The what-if engine gives every agent visibility into consequences across *all* metrics. The SO Agent already knows the expedite costs $2,400 and the logistics budget is at 78%. **The negotiation is about authorization and resource contention, not information discovery.** Agents share the same balanced scorecard; they disagree on whether the trade-off is worth it.

**15+ Agent Types** organized across five categories:

| Category | Agents | Role |
|----------|--------|------|
| **Core Planning & Execution** | SO/ATP, Supply, Allocation, Logistics, Inventory, S&OP | Material flow decisions |
| **Manufacturing** | Plant, Quality, Maintenance | Production scheduling, holds, PM windows |
| **Procurement & Supplier** | Procurement, Supplier | Vendor selection, PO management |
| **Channel & Demand** | Channel (per channel), Demand | Allocation, forecasting |
| **S&OP / Strategic** | Finance, Service, Risk | Budget, service levels, risk mitigation |

**DAG-Based Agent Discovery**: Operational agents discover negotiation partners through the supply chain DAG (transportation lanes define who talks to whom). Cross-functional agents (Finance, Quality, Risk) subscribe to board topics and are auto-joined when relevant threads appear.

**25+ Negotiation Scenarios** across manufacturing, distribution, channel, procurement, logistics, finance, and S&OP -- each with defined originator, target, trigger, authorization surface, and counter-offer patterns.

**Emergent Behavior**: With agents continuously posting, replying, and resolving authorization threads, patterns described by Visser's "Agentic Inversion" naturally emerge: agents form coalitions, build reputation (track record of good counter-offers), and establish precedent (resolution patterns that become auto-authorization rules after 12+ similar resolutions).

**Reference**: [Agentic Authorization Protocol](AGENTIC_AUTHORIZATION_PROTOCOL.md)

---

## Part 3: How the Four Innovations Work Together

The four innovations are not independent features. They form an integrated system:

```
                    ┌─────────────────────────────┐
                    │     LLM-First UI             │
                    │  (AIIO: Automate-Inform-     │
                    │   Inspect-Override)           │
                    └──────────┬──────────────────┘
                               │ Human oversees via
                               │ conversation / dashboards
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                  Powell Framework (3-Tier AI)                 │
│                                                              │
│  S&OP (CFA)  →  Execution tGNN (VFA)  →  Narrow TRM (VFA)  │
│  θ parameters    Allocations              Order decisions    │
│                                                              │
│  Each tier uses CTP as its decision basis:                   │
│  ┌──────────────────────────────────────────────────┐        │
│  │  CTP Engine: Multi-stage DAG traversal           │        │
│  │  Full-level pegging: demand ↔ supply tracing     │        │
│  │  Balanced Scorecard: impact across all metrics   │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  When an agent's best option crosses authority boundaries:   │
│  ┌──────────────────────────────────────────────────┐        │
│  │  AAP: Request → Counter-Offer → Authorize/Deny  │        │
│  │  Resolves in seconds; escalates to human only    │        │
│  │  when agents can't agree                         │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

**Scenario: Strategic Customer Urgent Order**

1. **CTP** calculates: 100 units needed, 20 available at DC, 80 require factory production, binding constraint is Vendor-Plastic at 7 days.
2. **Powell TRM** (ATPExecutorTRM): Promises the 20 units immediately from DC inventory.
3. **Powell TRM** (POCreationTRM): Identifies need for rush PO to cover the 80-unit shortfall.
4. **AAP**: SO Agent requests authorization from Logistics Agent for expedited shipping (scorecard shows +$15,600 net benefit vs. $2,400 cost). Finance Agent auto-joined because thread tagged `expedite_cost`.
5. **AAP**: Logistics Agent counter-offers with a partial expedite ($1,200 instead of $2,400). Finance Agent approves within budget.
6. **LLM-First UI**: Planner's morning digest says: "Rush order for Customer-A resolved autonomously. Net benefit: $14,400. 3 agents collaborated. Tap to inspect reasoning."

Total time: 47 seconds. Legacy equivalent: 2-3 days.

### Underlying Capability: Stochastic Planning with Conformal Prediction

The four innovations above operate on **probabilistic** data, not point estimates. Two capabilities make this possible:

**Monte Carlo Simulation** generates thousands of scenarios by sampling from 20 distribution types across operational variables (lead times, yields, capacities, demand). The output is not "we need 100 units" but "we need 80-120 units (P10/P90), most likely 95 (P50)." The S&OP GraphSAGE (Powell Tier 1) uses these scenarios for **optimization** -- finding the policy parameters θ that perform best *across the distribution of possible futures*, not just the expected case.

**Conformal Prediction** provides formal, distribution-free uncertainty guarantees on agent outputs. When the ATPExecutorTRM promises a delivery date, conformal prediction wraps it in a calibrated interval: "99% confident this arrives by March 25; 90% confident by March 22." This eliminates the false certainty of point-estimate planning and gives agents (and the AAP negotiation protocol) a shared language for risk: an agent requesting an expedite can cite "P90 stockout probability of 85%" rather than a heuristic guess. Conformal prediction also powers adaptive guardrails -- reducing false escalations by 40% compared to fixed-threshold rules.

Together, these turn the balanced scorecard from a snapshot into a **probability distribution**: not "OTIF is 95%" but "P(OTIF > 95%) = 82%, with P10/P50/P90 of 91%/96%/99%." Every agent, every CTP result, every AAP negotiation operates on these distributions.

---

## Part 4: Competitive Positioning

### What Incumbents Offer vs. What We Offer

| Capability | Kinaxis | SAP IBP | Autonomy |
|-----------|---------|---------|----------|
| **User Interface** | Dashboards + exception lists | Forms + workflows | **LLM-first conversational + dashboards** |
| **AI Architecture** | Scenario comparison (human selects) | Statistical forecasting | **3-tier Powell: CFA → VFA → TRM** |
| **Cross-Functional Resolution** | Meetings + workflow | Approval chains | **AAP: agent-to-agent in seconds** |
| **Order Promising** | ATP with allocation | Basic ATP | **Multi-stage CTP with full-level pegging** |
| **Uncertainty** | Scenarios (manual) | Point estimates | **Conformal prediction with P10/P50/P90** |
| **Decision Latency** | Hours (human-mediated) | Days (batch) | **Seconds (autonomous)** |
| **Learning** | None | None | **Override capture → RL training** |
| **Cost** | $100K-$500K/user/year | $200K+ implementation | **~$10K/user/year** |

### Our Blue Ocean

We don't compete on the same axes as incumbents. They sell planning software that humans operate. We sell planning autonomy where humans oversee.

```
                    HUMAN-OPERATED
                        │
         Kinaxis ●      │      ● SAP IBP
                        │
    ────────────────────┼────────────────────
                        │
         OMP ●          │
                        │      ● Autonomy
              Excel ●   │        (target)
                        │
                    AI-AUTONOMOUS

        OPAQUE AI ◄─────┼─────► TRANSPARENT AI
```

**The Compounding Loop**: More autonomous decisions → Better agent training data → Higher decision quality → More trust → More autonomous decisions. Override capture is the flywheel: every human correction makes the agent better. Incumbents don't have this loop because they don't capture override reasoning.

---

## Part 5: Market Strategy

### Beachhead: Mid-Market Manufacturers

**Target**: Discrete manufacturers ($100M-$500M revenue) currently using Excel or basic ERP planning modules.

**Why This Segment**:
- Underserved by Kinaxis/SAP (too expensive)
- Pain is acute (manual processes, stockouts, excess inventory)
- Willing to try new approaches (not locked into 10-year contracts)
- Supply chains are complex enough to benefit from CTP and AAP
- 3-10 production sites, 500-5,000 SKUs

**Packaging: Modular Layers (Bottom-Up Purchase)**

The Powell cascade is designed as independently sellable layers:

| Package | Layers Included | What Customer Gets |
|---------|----------------|-------------------|
| **Foundation** | Execution only | Deterministic engines (MRP, ATP, safety stock). CTP for order promising. Manual policy inputs. |
| **AI Execution** | Execution + Supply + Allocation Agents | TRM agents + Supply & Allocation Agents. Customer provides policy parameters. AAP resolves cross-agent conflicts. |
| **Planning** | Above + MPS (candidate generation) | Multiple supply plan candidates with tradeoff frontier. Customer provides strategic policy only. |
| **Enterprise** | All 5 layers | S&OP simulation optimizes everything. Full closed-loop with feed-back signals. |

When a customer buys lower layers without upper layers, the same UI screens become **input screens** where the customer provides what the missing AI layer would have generated. This means every sale is a foot in the door for upselling upper layers.

### Pricing

| Tier | Monthly | What's Included |
|------|---------|----------------|
| **Starter** | Free | Simulation module + basic analytics |
| **Professional** | $2,500 | Foundation + AI Execution + LLM interface |
| **Enterprise** | $10,000 | Full cascade + SSO + multi-tenancy + 24/7 support |

**Competitive Position**: 90% cost reduction vs. Kinaxis at $250K/user/year.

### Enterprise Data Integration: SAP S/4HANA and APO

Most mid-market manufacturers run SAP. Autonomy includes a built-in SAP integration layer that connects to S/4HANA, APO, ECC, and BW via RFC, CSV, or OData. The critical capability is **AI-powered fuzzy matching for Z-tables and Z-fields** -- the custom SAP objects that vary by customer and make every SAP deployment unique. Rather than requiring months of manual field mapping, the platform uses semantic matching to automatically map custom SAP fields to the supply chain data model, with human review for ambiguous cases. This reduces data onboarding from weeks to days and removes the largest implementation bottleneck for SAP-centric customers.

---

## Part 6: Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AI agents underperform in production | Medium | High | Pilot program; parallel human+AI planning; measure before committing |
| LLM API costs at scale | Medium | Medium | Open-source model fallback (DeepSeek, Qwen); local inference on commodity hardware |
| CTP performance on large networks | Low | Medium | Caching, cycle detection, incremental recalculation |
| AAP over-escalation to humans | Medium | Low | Precedent learning; auto-authorization rules after 12+ similar resolutions |

### Market Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Legacy vendors add AI | High | Medium | Our advantage is architectural (vertical integration), not feature-level |
| Enterprise sales cycle too long | High | Medium | Start mid-market; demonstrate ROI in 90-day pilots |
| "AI replacing planners" resistance | Medium | High | Position as "AI handles routine; humans handle strategy" |

### The Uncomfortable Truths

1. **AI performance claims are simulation-derived**. The "20-35% cost reduction" comes from controlled environments. Until validated on real supply chains, it's a hypothesis.
2. **Zero reference customers**. Enterprise buyers require references. We need 2-3 documented successes before the sales cycle shortens.
3. **LLM agents have operational risk**. API dependency, cost variability, and model behavior changes require fallback mechanisms.

---

## Part 7: Go-to-Market

### Phase 1: Validate (Q1 2026)
- Secure 3 pilot customers (free 90-day implementation)
- Run parallel planning: human planners vs. AI recommendations
- Measure cost, service level, and planner productivity impact
- **Success**: 3 customers with measurable improvement (>10% cost reduction or >5% service level improvement)

### Phase 2: Launch (Q2 2026)
- Press release with customer quotes
- Website with case studies and demo videos
- Content marketing: "From batch planning to autonomous planning" narrative
- Attend 2 industry conferences (Gartner, CSCMP)
- **Success**: 10 qualified leads/month; 2-3 closed deals

### Phase 3: Scale (Q3-Q4 2026)
- Hire 2 account executives
- Build 2-3 SI partner relationships
- Expand to wholesale/distribution verticals
- Product-led growth: free simulation tier drives awareness
- **Success**: 10 enterprise customers, $1M ARR

---

## Part 8: Financial Projections

### Revenue Model

| Metric | Conservative | Base | Optimistic |
|--------|--------------|------|------------|
| Year 1 Customers | 5 | 10 | 20 |
| Year 1 ARR | $500K | $1M | $2M |
| Gross Margin | 70% | 75% | 80% |

### Cost Structure

- Monthly burn: ~$120K-$130K (engineering, infrastructure, sales, G&A)
- Break-even: ~12-15 customers at Professional tier
- Required runway: 18-24 months ($2.2M-$2.9M)

### Customer ROI

| Claim | Status | Evidence |
|-------|--------|----------|
| 20-35% cost reduction | Simulation-validated | Validated in Beer Game simulation environments |
| 90% cost reduction vs. legacy | Accurate | License fee comparison |
| 2-3 week deployment | Plausible | Basic setup; full integration likely 1-3 months |
| 10,080x faster OODA loop | Architectural | 60-second event-driven vs. 5-day weekly batch |

---

## Part 9: Success Metrics

### 90-Day

| Metric | Target |
|--------|--------|
| Pilot customers signed | 3 |
| Pilots in production | 2 |
| AI agent performance validated | 1+ customer |
| CTP accuracy on real data | Measured |

### 6-Month

| Metric | Target |
|--------|--------|
| Paying customers | 5 |
| ARR | $300K |
| Case studies published | 2 |
| Agent touchless rate (production) | >40% |

### 12-Month

| Metric | Target |
|--------|--------|
| Paying customers | 10 |
| ARR | $1M |
| Agent touchless rate | >60% |
| Customer churn | <20% |

---

## Conclusion

### What We Have

- **Vertically integrated AI**: Powell Framework connecting S&OP strategy to individual order decisions
- **Decision transparency**: Multi-stage CTP with full-level pegging -- every unit traceable end-to-end
- **Cross-functional autonomy**: Agentic Authorization Protocol resolving trade-offs at machine speed
- **Natural interface**: LLM-first UI where planners oversee outcomes rather than make individual decisions
- **Precision escalation**: Urgency + likelihood scoring surfaces only the decisions where human judgment creates real value — high urgency situations where the agent is least confident — while routine decisions execute autonomously
- **Learning flywheel**: Override capture trains agents continuously; human judgment compounds
- **Comprehensive data model**: 100% compliance with industry-standard supply chain entity model
- **Cost advantage**: 90% lower than legacy systems

### What We Need

- **Customer validation**: Real-world proof that autonomous agents deliver promised results
- **Reference customers**: 2-3 documented successes for sales credibility
- **Whole product completion**: Implementation playbooks, support organization, partner ecosystem

### The Strategic Choice

We are not building planning software. We are building the operating system for autonomous supply chain management. The four innovations -- LLM-first UI, Powell vertical integration, CTP decision basis, and Agentic Authorization -- are not features to be compared against competitor feature lists. They are a fundamentally different architecture for how supply chain decisions get made.

**The path to success is not building more features -- it's proving the features we have work for real customers.**

---

## Appendices

### Appendix A: Product Capability Matrix

| Capability | Status | Confidence |
|------------|--------|------------|
| Supply Chain Data Model | 100% | High |
| Demand Planning (view) | Complete | High |
| Supply Planning (MRP/MPS) | Complete | High |
| Order Management (PO/TO/MO/Project/Maintenance/Service) | 95% | High |
| Multi-Stage CTP + Full-Level Pegging | Complete | High |
| Agentic Authorization Protocol | Design complete; implementation Phase 1 | Medium |
| LLM-First UI (AIIO) | Architecture complete | Medium |
| Powell 3-Tier AI (TRM/GNN/GraphSAGE) | Functional | Medium |
| Stochastic Planning (20 distribution types, Monte Carlo) | Complete | High |
| Conformal Prediction (distribution-free uncertainty guarantees) | Complete | Medium |
| Event-Driven Replanning (CDC) | Complete | High |
| SAP Integration (S/4HANA, APO, ECC; fuzzy Z-table matching) | Complete | High |
| Simulation Module | Complete | High |
| Mobile App | Complete | High |

### Appendix B: Key Document References

| Document | Content |
|----------|---------|
| [POWELL_APPROACH.md](../POWELL_APPROACH.md) | Three-tier AI architecture, policy classes, hierarchical consistency |
| [CTP_CAPABILITIES.md](CTP_CAPABILITIES.md) | Multi-stage CTP engine, full-level pegging, agent integration |
| [AGENTIC_AUTHORIZATION_PROTOCOL.md](AGENTIC_AUTHORIZATION_PROTOCOL.md) | Cross-functional negotiation, 15+ agent types, 25+ scenarios, board architecture |
| [LLM_FIRST_EXECUTION_PLANNING_PROPOSAL.md](architecture/LLM_FIRST_EXECUTION_PLANNING_PROPOSAL.md) | AIIO paradigm, OODA loop, ReAct prompting, guardrails |
| [CONTINUOUS_PLANNING_ARCHITECTURE.md](architecture/CONTINUOUS_PLANNING_ARCHITECTURE.md) | Event-driven replanning, CDC triggers, Git-like plan versioning |
| [EXECUTION_CAPABILITIES.md](../EXECUTION_CAPABILITIES.md) | ATP/CTP formulas, order fulfillment, shipment tracking |

### Appendix C: Technology Stack

**Backend**: Python 3.10+, FastAPI, SQLAlchemy 2.0, PostgreSQL
**AI/ML**: PyTorch 2.2, PyTorch Geometric, OpenAI API (with open-source fallback)
**Frontend**: React 18, Material-UI 5, Recharts
**Mobile**: React Native 0.73
**Infrastructure**: Docker, Nginx, NVIDIA GPU support

---

*Document prepared using frameworks from:*
- *Good Strategy Bad Strategy* by Richard Rumelt (2011)
- *Crossing the Chasm, 3rd Edition* by Geoffrey A. Moore (2014)
- *Sequential Decision Analytics and Modeling* by Warren B. Powell (2022)

---


---

![Azirella](../Azirella_Logo.jpg)

> **Copyright © 2026 Azirella Ltd. All rights reserved worldwide.**
> This document and all information contained herein are the exclusive confidential and proprietary property of Azirella Ltd, 27, 25 Martiou St., #105, 2408 Engomi, Nicosia, Cyprus. No part of this document may be reproduced, stored in a retrieval system, transmitted, distributed, or disclosed in any form or by any means — electronic, mechanical, photocopying, recording, or otherwise — without the prior express written consent of Azirella Ltd. Any unauthorized use constitutes a violation of applicable intellectual property laws and may be subject to legal action.

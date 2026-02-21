# Agentic Authorization Protocol: Cross-Functional Decision-Making at Machine Speed

## Executive Summary

This document defines the **Agentic Authorization Protocol (AAP)** -- a framework for autonomous agents to evaluate cross-functional trade-offs, request authorization for actions outside their authority, and resolve resource contention -- all at machine speed with full transparency via the Probabilistic Balanced Scorecard.

**Core Insight**: The what-if engine gives every agent visibility into consequences across *all* metrics, not just its own. The balanced scorecard shows red/amber/green across Financial, Customer, Operational, and Strategic dimensions. An agent doesn't need another agent to tell it "this expedite costs $2,400" -- it can already see that. **The negotiation is about authorization and resource contention, not information discovery.**

**Inspiration**: Jordi Visser's "Agentic Inversion" (Feb 2026) describes how autonomous agents sustain continuous economic activity without per-transaction human oversight. The Kinaxis scenario comparison model -- where a planner creates an alternative scenario, evaluates impact, and brings it to a forum when net benefit crosses a threshold -- provides the UX precedent. The AAP combines these: agents run the Kinaxis workflow at machine speed, escalating to humans only when they can't resolve contention autonomously.

**Relationship to Existing Architecture**: The AAP extends the Powell Framework's planning cascade (S&OP -> MRS -> Supply Agent -> Allocation Agent -> Execution) with a *lateral* authorization channel. Feed-forward contracts become the artifacts being evaluated. Feed-back signals become the evidence basis. The what-if engine (already supporting `run_what_if()` on PolicyEnvelope) expands to evaluate any proposed action by simulating the cascade forward. The **multi-stage CTP engine** and **full-level pegging** (see [CTP_CAPABILITIES.md](CTP_CAPABILITIES.md)) provide the feasibility data that feeds into scorecard evaluations -- agents can trace every unit of supply to demand before negotiating reallocation.

---

## 1. The Problem: Cross-Functional Trade-Offs

Supply chain decisions rarely affect a single function. A Sales Order agent fulfilling a strategic customer's urgent request might consider:

| Option | Action | Owning Function | Impact |
|--------|--------|-----------------|--------|
| A | Reallocate supply from a lower-priority order | Sales/ATP (SO Agent) | Strategic order filled; standard customer delayed 3 days |
| B | Expedite delivery from a later allocation | Logistics | Strategic order filled; $2,400 expedite cost |
| C | Expedite FG from a regional DC | Inventory | Strategic order filled; DC safety stock depleted by 40% |

The SO agent can execute Option A unilaterally. Options B and C require actions in another agent's domain.

**In legacy systems**: The planner emails logistics, waits for a response, gets finance approval, circles back. Hours to days.

**With AAP**: The SO agent evaluates all three options against the full balanced scorecard in milliseconds, selects the best net outcome, and requests authorization from the owning agent. Resolution in seconds.

---

## 2. The Balanced Scorecard as Shared Language

### 2.1 Every Agent Sees Everything

The what-if engine doesn't produce a single number. It produces the **Probabilistic Balanced Scorecard** -- the same four-quadrant view used at every level of the Powell cascade:

```
SO Agent's What-If: Option B (Expedite Delivery)

  CUSTOMER                              FINANCIAL
  +-------------------------------+    +-------------------------------+
  | Strategic OTIF: 99.2%         |    | Expedite Spend: $2,400        |
  | ==================== GREEN    |    | ==============---- AMBER      |
  |                               |    | (78% of weekly budget)        |
  | Standard OTIF: 97.1%         |    |                               |
  | ==================== GREEN    |    | Transport Cost: +4.2%         |
  |                               |    | ==============---- AMBER      |
  +-------------------------------+    +-------------------------------+

  OPERATIONAL                           STRATEGIC
  +-------------------------------+    +-------------------------------+
  | Fill Rate: 100%               |    | Customer Retention Risk: $0   |
  | ==================== GREEN    |    | ==================== GREEN    |
  |                               |    |                               |
  | Inventory Impact: None        |    | Revenue at Risk: $0           |
  | ==================== GREEN    |    | ==================== GREEN    |
  +-------------------------------+    +-------------------------------+

  NET BENEFIT: +$15,600 (weighted)
  Status: 6 GREEN, 2 AMBER, 0 RED
```

The SO agent already knows the expedite costs $2,400 and pushes the weekly budget to 78%. It's amber, not green. The agent has made an informed judgment that the net benefit (+$15,600) justifies the amber flags.

### 2.2 What the Balanced Scorecard Contains

Each what-if scenario evaluation produces:

| Quadrant | Metrics | Source |
|----------|---------|--------|
| **Financial** | Total cost delta, expedite spend, inventory carrying cost, GMROI impact | Cost models + Policy Envelope parameters |
| **Customer** | OTIF by segment, fill rate, order promise reliability | Allocation model + historical performance |
| **Operational** | DOS impact, safety stock utilization, capacity utilization, bullwhip contribution | Inventory model + network state |
| **Strategic** | Revenue at risk, customer retention risk, supplier concentration impact | S&OP parameters + risk models |

Every metric carries:
- **Current value** (before proposed action)
- **Projected value** (after proposed action)
- **Delta** (change)
- **Status** (GREEN / AMBER / RED based on Policy Envelope thresholds)
- **Confidence interval** (P10/P50/P90 from stochastic evaluation)

### 2.3 The Net Benefit Calculation

Net benefit is computed as a weighted sum across all four scorecard quadrants:

```
Net Benefit = Sum over all metrics of (
    weight_i * delta_i * direction_i
)

Where:
  weight_i   = from Policy Envelope (set by S&OP layer)
  delta_i    = projected_value - current_value
  direction_i = +1 if higher is better (OTIF), -1 if lower is better (cost)
```

The weights come from the Policy Envelope -- the same parameters that govern the entire cascade. This means the net benefit calculation reflects the enterprise's stated strategic priorities, not any individual agent's preferences.

---

## 3. Authority Boundaries

### 3.1 Every Agent Has a Defined Authority Domain

Each agent type has three categories of actions:

| Category | Definition | Example |
|----------|-----------|---------|
| **Unilateral** | Agent can execute without asking anyone | SO Agent: reallocate within priority tier |
| **Requires Authorization** | Agent can evaluate but must get approval from owning agent | SO Agent: request expedite from Logistics Agent |
| **Forbidden** | Agent cannot request this action | SO Agent: change Policy Envelope parameters |

### 3.2 Authority Map

#### Core Planning & Execution Agents

| Agent | Unilateral Authority | Requires Authorization From |
|-------|---------------------|-----------------------------|
| **SO / ATP Agent** | Reallocate within priority tier, defer non-critical orders, partial fill within policy, run CTP feasibility checks, promise orders when CTP feasible | Logistics (expedite when CTP lead time exceeds target), Inventory (cross-DC transfer when CTP shows shortfall), Supply (rush PO when CTP binding constraint is vendor lead time) |
| **Supply Agent** | Select supplier within approved list, adjust PO timing within lead time window, choose from SupBP candidates | Procurement (new supplier), Logistics (freight mode change), S&OP (policy exception) |
| **Allocation Agent** | Distribute within committed supply pool, fair-share within segment | Supply (request additional supply), S&OP (priority rule exception), SO (accept partial) |
| **Logistics Agent** | Route selection, carrier assignment, consolidation, mode selection within budget | Finance (budget exception), Inventory (warehouse overtime), SO (delivery date change) |
| **Inventory Agent** | Replenishment within policy, cycle count triggers, location assignment | S&OP (safety stock exception), Logistics (emergency transfer), Supply (expedite replenishment) |
| **S&OP Agent** | Adjust parameters within guardrails, approve/reject policy changes | Executive (guardrail changes), Finance (budget reallocation) |

#### Manufacturing Agents

| Agent | Unilateral Authority | Requires Authorization From |
|-------|---------------------|-----------------------------|
| **Plant Agent** | Schedule production within approved plan, sequence within changeover rules, batch size within MOQ/max | Supply (rush order insertion), Quality (release hold), Maintenance (schedule around downtime) |
| **Quality Agent** | Place material on hold, trigger inspection, apply disposition within SOP | Plant (production rerun), Supply (return to vendor), Finance (write-off authorization) |
| **Maintenance Agent** | Schedule preventive maintenance within window, adjust PM frequency within policy | Plant (production line shutdown), Finance (capex for emergency repair), Procurement (spare parts expedite) |

#### Procurement & Supplier Agents

| Agent | Unilateral Authority | Requires Authorization From |
|-------|---------------------|-----------------------------|
| **Procurement Agent** | Select supplier from approved vendor list, negotiate price within approved bands, issue PO within budget | Finance (budget exception), Quality (new supplier qualification), Legal (contract terms deviation) |
| **Supplier Agent** (external-facing) | Confirm order, propose lead time, adjust delivery schedule | Procurement (price change), Quality (substitution approval), Logistics (delivery window change) |

#### Channel & Demand Agents

| Agent | Unilateral Authority | Requires Authorization From |
|-------|---------------------|-----------------------------|
| **Channel Agent** (per channel) | Allocate within channel-specific entitlement, accept/defer orders within channel policy | Allocation (cross-channel reallocation), Sales (priority override), Finance (promotional pricing) |
| **Demand Agent** | Adjust forecast within statistical confidence band, flag demand signal anomalies | S&OP (demand plan override), Channel (promotional volume commitment), Finance (revenue plan revision) |

#### S&OP / Strategic Agents

| Agent | Unilateral Authority | Requires Authorization From |
|-------|---------------------|-----------------------------|
| **Finance Agent** | Set budget constraints within board-approved envelope, approve/deny budget exceptions within delegation | Executive (delegation limit increase), S&OP (working capital target change) |
| **Service Agent** | Recommend service-level changes based on performance data | S&OP (OTIF floor change), Finance (cost-of-service increase), Demand (demand-shaping actions) |
| **Risk Agent** | Flag risk events, recommend mitigation actions | S&OP (policy parameter change), Procurement (supplier diversification), Finance (reserve allocation) |

### 3.3 Authority Boundaries as Authorization Surfaces

The key architectural insight: **wherever one agent's authority ends and another's begins, that is an authorization surface**. The AAP activates precisely at these boundaries.

The boundary is not about information -- both agents see the same balanced scorecard. The boundary is about **who is accountable** for the resource being consumed (budget, capacity, safety stock, etc.).

---

## 4. The Authorization Protocol

### 4.1 Protocol Flow

```
Phase 1: EVALUATE           Phase 2: REQUEST          Phase 3: AUTHORIZE
(originating agent)         (cross-authority)         (target agent)

+------------------+       +------------------+       +------------------+
| Run what-if on   |       | Send AuthRequest |       | Check resource   |
| all options      |  -->  | with scorecard   |  -->  | availability     |
| (full scorecard) |       | + net benefit    |       | + contention     |
+------------------+       +------------------+       +------------------+
        |                          |                          |
        v                          v                          v
+------------------+       +------------------+       +------------------+
| Select best      |       | Include          |       | AUTHORIZE or     |
| option (may      |       | justification    |       | COUNTER-OFFER or |
| cross authority) |       | for amber flags  |       | DENY             |
+------------------+       +------------------+       +------------------+
                                                              |
                                                              v
                                                   +------------------+
                                                   | If DENY and net  |
                                                   | benefit > thresh |
                                                   | --> ESCALATE to  |
                                                   | human            |
                                                   +------------------+
```

### 4.2 Phase 1: Evaluate (Originating Agent)

The originating agent:
1. Identifies a decision opportunity (e.g., high-priority order to fulfill)
2. Enumerates candidate actions -- **including actions outside its authority**
3. Runs what-if on each candidate against the full balanced scorecard
4. Ranks by net benefit
5. If the best option is within its unilateral authority, executes immediately (no protocol needed)
6. If the best option requires another agent's authorization, proceeds to Phase 2

**The originating agent already sees the full impact**. It knows the expedite costs $2,400, it knows the logistics budget is at 78%. It's making a judgment call that the net benefit justifies asking.

### 4.3 Phase 2: Authorization Request

The originating agent sends an `AuthorizationRequest` to the target agent:

```
AuthorizationRequest {
  id: "ar-20260209-0847-001"
  requesting_agent: "so_agent"
  target_agent: "logistics_agent"
  priority: "HIGH"           # From the triggering order's priority
  expires_at: "2026-02-09T12:00:00Z"  # SLA for response

  # What I need you to authorize
  proposed_action: {
    type: "expedite_shipment"
    order_id: 8834
    from_allocation_period: "2026-W08"
    to_delivery: "2026-02-12"
    estimated_cost: 2400
    carrier_requirement: "LTL"
  }

  # The full scorecard -- I already know the impact
  balanced_scorecard: {
    customer: {
      otif_strategic: { current: 0.94, projected: 0.992, status: "GREEN" },
      otif_standard: { current: 0.971, projected: 0.971, status: "GREEN" }
    },
    financial: {
      expedite_spend: { current: 3200, projected: 5600, status: "AMBER",
                        note: "78% of $8,000 weekly budget" },
      transport_cost_delta: { current: 0, projected: 2400, status: "AMBER" }
    },
    operational: {
      fill_rate: { current: 0.96, projected: 1.0, status: "GREEN" },
      inventory_impact: { current: 0, projected: 0, status: "GREEN" }
    },
    strategic: {
      revenue_at_risk: { current: 45000, projected: 0, status: "GREEN" },
      retention_risk: { current: "HIGH", projected: "NONE", status: "GREEN" }
    }
  }

  net_benefit: 15600
  benefit_threshold: 5000    # Configurable per decision type

  # Why I'm asking despite the amber flags
  justification: "Strategic customer (Tier 1), order 8834 at risk of
                  3-day delay. Net benefit 6.5x expedite cost. All
                  non-financial metrics improve to GREEN."

  # What I'll do on my side if you authorize
  complementary_actions: [
    "Hold allocation for order 8834 pending expedite confirmation",
    "Defer reallocation of standard order 4471 (no longer needed)"
  ]

  # My fallback if you deny
  fallback_action: {
    type: "reallocate_supply"
    description: "Reallocate from standard order 4471 (3-day delay)"
    net_benefit: 12000
    note: "Unilateral -- can execute without authorization"
  }
}
```

### 4.4 Phase 3: Authorization Decision (Target Agent)

The target agent does **not** re-run the what-if analysis. The scorecard is already in the request. The target agent evaluates three things:

**1. Can I? (Resource Availability)**
```
Expedite budget: $8,000/week, $4,800 remaining    -> PASS ($2,400 fits)
Carrier capacity: LTL slot available Wednesday     -> PASS
Lead time feasibility: Pickup today, deliver Wed   -> PASS
```

**2. Should I? (Competing Demands)**
```
Pending authorization requests:
  - AR-002: Allocation Agent, $1,800 expedite, net benefit +$22,000 -> HIGHER
  - AR-003: Supply Agent, $800 rush pickup, net benefit +$6,000     -> LOWER

Budget after all three: $4,800 - $2,400 - $1,800 - $800 = -$200    -> CONFLICT
Can approve this + AR-003, OR AR-002 alone, but not all three.
```

**3. Will I? (Authorization Decision)**

| Scenario | Decision | Reasoning |
|----------|----------|-----------|
| No contention, resources available | **AUTHORIZE** | Straightforward -- resources exist, requestor showed net benefit |
| Resource contention with lower-priority request | **AUTHORIZE** (deny the lower one) | This request's net benefit exceeds the competing one |
| Resource contention with higher-priority request | **COUNTER-OFFER** or **DENY** | Suggest modified terms or explain why the higher-priority request takes precedence |
| Policy threshold would be breached | **DENY with escalation recommendation** | "This would push expedite spend to 105% of budget -- requires Finance approval" |

### 4.5 Counter-Offers

When the target agent can't authorize as-is but can offer an alternative:

```
AuthorizationResponse {
  request_id: "ar-20260209-0847-001"
  decision: "COUNTER_OFFER"

  counter_proposal: {
    type: "expedite_shipment"
    modification: "Consolidated LTL instead of dedicated, Thursday delivery"
    estimated_cost: 1800        # $600 less
    delivery_date: "2026-02-13" # 1 day later
  }

  reason: "Competing request AR-002 from Allocation Agent has higher
           net benefit (+$22,000). Consolidated shipment fits both
           within remaining budget."

  # Updated scorecard for counter-offer
  revised_scorecard_delta: {
    financial: { expedite_spend: { projected: 5000, status: "AMBER" } },
    customer: { otif_strategic: { projected: 0.985, status: "GREEN" } }
  }
}
```

The originating agent evaluates the counter-offer against its own scorecard. If Thursday delivery still meets the customer commitment, it accepts. If not, it may fall back to its unilateral option (reallocate supply) or escalate.

### 4.6 Multi-Party Authorization

Some actions require authorization from multiple agents simultaneously:

**Example**: The SO agent wants the Inventory Agent to ship from a regional DC, but this depletes safety stock below the floor. The Inventory Agent says "I'll authorize if the Supply Agent commits to an expedited replenishment PO."

```
Phase 1: SO Agent -> Inventory Agent: "Ship 500 cases from DC West"
Phase 2: Inventory Agent -> "CONDITIONAL: Authorize if Supply Agent
          commits to replenishment within 3 days"
Phase 3: SO Agent -> Supply Agent: "Can you expedite a replenishment
          PO to DC West within 3 days?"
Phase 4: Supply Agent -> "AUTHORIZE: Supplier confirms 2-day expedite,
          $3,200 premium"
Phase 5: SO Agent -> Inventory Agent: "Supply Agent committed. Authorize?"
Phase 6: Inventory Agent -> "AUTHORIZE" (with Supply Agent commitment as condition)
```

The protocol tracks these dependency chains. All conditions must be met before any actions execute.

---

## 5. Comprehensive Negotiation Scenarios

The SO Agent expedite example in Section 1 is one instance of a much broader landscape of cross-authority negotiations in a manufacturing supply chain. This section catalogs the full range, organized by supply chain function.

Each scenario identifies the originating agent, the authorization surface crossed, and the balanced scorecard tradeoff. These are grounded in real-world patterns observed in food manufacturing/distribution (e.g., Dot Foods model), semiconductor allocation (TSMC/automotive), CPFR exception management, and the Oliver Wyman "Supply Chain Triangle" (Service, Cost, Working Capital).

### 5.1 Manufacturing Negotiations

Manufacturing introduces authorization surfaces around shared physical resources: production lines, changeover time, quality holds, and maintenance windows.

#### 5.1.1 Rush Order Insertion

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Plant Agent |
| **Trigger** | High-priority customer order can't be filled from inventory; requires unplanned production run |
| **Authorization Surface** | Supply Agent controls what to order; Plant Agent controls the production schedule |
| **Scorecard Tradeoff** | Customer (GREEN: order filled) vs. Operational (AMBER: schedule disruption, potential late delivery of existing orders) vs. Financial (AMBER: changeover cost, overtime) |
| **Counter-Offer** | Plant Agent proposes partial quantity from current run + remainder in next scheduled batch |
| **Real-World Parallel** | Every make-to-order manufacturer faces this daily; Kinaxis "concurrent planning" resolves it in minutes with human planner involvement |

#### 5.1.2 Production Changeover Optimization

| Attribute | Value |
|-----------|-------|
| **Originator** | Plant Agent |
| **Target** | Supply Agent, Allocation Agent |
| **Trigger** | Plant Agent calculates it can reduce changeover cost by $12K by resequencing production, but this changes delivery timing for 3 downstream commitments |
| **Authorization Surface** | Plant Agent controls sequence; Supply Agent owns the delivery commitment; Allocation Agent owns the allocation entitlements |
| **Scorecard Tradeoff** | Financial (GREEN: $12K savings) vs. Customer (AMBER: 2 of 3 orders delayed 1 day) vs. Operational (GREEN: better utilization) |
| **Multi-Party** | Plant -> Supply: "Can you accept 1-day delay on PO-4471 and PO-4472?" Supply -> Allocation: "Can allocation absorb a 1-day shift?" If both authorize, Plant resequences. |
| **Real-World Parallel** | Lot-sizing negotiation in multi-agent systems (Springer 2006); production routing with privacy-preserving negotiation (AAMAS 2024) where retailer agents negotiate delivery timing changes proposed by the supplier/coordinator agent |

#### 5.1.3 Quality Hold / Release

| Attribute | Value |
|-----------|-------|
| **Originator** | Quality Agent |
| **Target** | Allocation Agent, Supply Agent, Finance Agent |
| **Trigger** | Quality Agent places 2,000 cases on hold pending inspection. These cases were allocated to customers. |
| **Authorization Surface** | Quality Agent controls material disposition; Allocation Agent owns the promises made to customers |
| **Scorecard Tradeoff** | Customer (RED: 5 orders at risk) vs. Operational (GREEN: quality compliance) vs. Financial (depends on disposition) |
| **Cascading Authorization** | Quality -> Allocation: "2,000 cases on hold, release ETA 48h. Reallocate from alternative supply?" Allocation -> Supply: "Can Supply Agent expedite 2,000 cases from alternate supplier?" Supply -> Procurement: "Authorize spot buy from secondary supplier at premium?" |
| **Real-World Parallel** | Semiconductor industry; TSMC quality excursions require reallocation decisions affecting Apple, Qualcomm, and automotive customers simultaneously |

#### 5.1.4 Make-vs-Buy Decision

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Plant Agent, Procurement Agent, Finance Agent |
| **Trigger** | Demand spike exceeds internal manufacturing capacity. Supply Agent evaluates: (A) overtime production at own plant, (B) contract manufacturing at co-packer, (C) spot purchase of finished goods |
| **Authorization Surface** | Supply Agent identifies the need; Plant Agent controls overtime authorization; Procurement Agent controls external sourcing; Finance Agent controls budget |
| **Scorecard Tradeoff** | Financial (varies: overtime $8/unit vs. co-pack $12/unit vs. spot $15/unit) vs. Customer (GREEN: all options fill demand) vs. Operational (overtime risks fatigue/quality) vs. Strategic (co-pack builds dependency) |
| **Counter-Offer** | Plant Agent: "Can do 60% at overtime + 40% at co-packer" (blended cost $9.60/unit) |
| **Real-World Parallel** | Make-or-buy in multi-stage manufacturing (ScienceDirect 2023); 30-60% of new product performance comes from supplier partnerships (Fastmarkets 2026) |

#### 5.1.5 Multi-Stage BOM Component Allocation

| Attribute | Value |
|-----------|-------|
| **Originator** | Plant Agent (Assembly Stage) |
| **Target** | Plant Agent (Component Stage), Supply Agent |
| **Trigger** | Shared component needed by two finished goods. Assembly Plant A needs 5,000 units for high-margin Product X; Assembly Plant B needs 3,000 for standard Product Y. Only 6,000 available from Component Plant. |
| **Authorization Surface** | Each assembly plant controls its own schedule; Component Plant controls allocation of its output |
| **Scorecard Tradeoff** | Financial (GREEN: prioritize high-margin) vs. Customer (AMBER: one product short) vs. Strategic (RED if Product Y customer is strategic) |
| **Multi-Party** | Component Plant -> Finance: "Should I allocate by margin or by customer priority?" Finance -> S&OP: "This is a policy question -- do we prioritize margin or customer tier?" |
| **Real-World Parallel** | TSMC's 2021 allocation between Apple (high margin, large volume) and automotive (lower margin, political pressure, government intervention). The Biden administration pressured TSMC to prioritize automotive chips, demonstrating that allocation decisions can involve external authorities. |
| **CTP Integration** | The multi-stage CTP engine detects shared component contention automatically during DAG traversal. When Component A appears in multiple BOMs, committed (pegged) quantity is subtracted from available inventory to prevent double-counting. The pegging chain shows exactly which finished-good orders each component unit is earmarked for, making the allocation tradeoff transparent. See [CTP_CAPABILITIES.md](CTP_CAPABILITIES.md) Section 1.3. |

#### 5.1.6 Maintenance Window Negotiation

| Attribute | Value |
|-----------|-------|
| **Originator** | Maintenance Agent |
| **Target** | Plant Agent, Supply Agent |
| **Trigger** | Preventive maintenance due on Line 3 (critical production line). Maintenance Agent wants to schedule a 4-hour shutdown Thursday. Plant Agent has committed orders requiring Line 3 Thursday. |
| **Authorization Surface** | Maintenance Agent owns equipment reliability; Plant Agent owns production schedule |
| **Scorecard Tradeoff** | Operational (GREEN: prevent unplanned downtime) vs. Customer (AMBER: Thursday orders delayed) vs. Financial (risk calculation: 4h planned PM vs. potential 24h unplanned failure) |
| **Counter-Offer** | Plant Agent: "Shift PM to Saturday (overtime premium $2,400)" or "Split PM: 2 hours Thursday night after last run, 2 hours Friday morning before first run" |

### 5.2 Distribution & Inventory Negotiations

Distribution networks create authorization surfaces around shared warehouse capacity, cross-DC transfers, and positioning decisions.

#### 5.2.1 Cross-DC Inventory Rebalancing

| Attribute | Value |
|-----------|-------|
| **Originator** | Inventory Agent (DC East) |
| **Target** | Inventory Agent (DC West), Logistics Agent |
| **Trigger** | DC East has 3 weeks of supply but only 0.8 weeks of demand; DC West has 0.5 weeks of supply and 2.5 weeks of demand. Rebalancing 1,500 cases would optimize network inventory. |
| **Authorization Surface** | Each DC's Inventory Agent controls its own safety stock; Logistics Agent controls transfer capacity and cost |
| **Scorecard Tradeoff** | Operational (GREEN: network DOS normalized) vs. Financial (AMBER: $3,200 inter-DC transfer cost) vs. Customer (GREEN: fill rate improvement at DC West) |
| **Multi-Party** | Inventory(East) -> Inventory(West): "I can release 1,500 cases." Inventory(East) -> Logistics: "Can you transport 1,500 cases East->West by Friday?" Both must authorize. |
| **Real-World Parallel** | Every multi-DC distributor faces this; Dot Foods operates 15 DCs covering 5M sq ft with redistribution as its core business model. The "lot-rolling" negotiation in multi-echelon systems (ResearchGate 2015) formalizes exactly this pattern. |

#### 5.2.2 Forward Positioning for Promotional Event

| Attribute | Value |
|-----------|-------|
| **Originator** | Channel Agent (Retail) |
| **Target** | Inventory Agent, Supply Agent, Finance Agent |
| **Trigger** | Retail channel running a "Buy 2 Get 1 Free" promotion in 3 weeks. Requires pre-positioning 50,000 additional cases across 8 retail DCs. Normal replenishment won't cover the spike. |
| **Authorization Surface** | Channel Agent owns promotional plans; Inventory Agent controls DC capacity; Supply Agent controls procurement volume; Finance Agent controls promotional budget |
| **Scorecard Tradeoff** | Strategic (GREEN: competitive positioning) vs. Financial (AMBER: $120K promotional inventory investment + risk of E&O if promotion underperforms) vs. Operational (AMBER: DC capacity strain) |
| **Counter-Offer** | Finance Agent: "Authorize $80K pre-build, remaining $40K only if Week 1 sell-through exceeds 60% (staged commitment)" |
| **Real-World Parallel** | CPFR promotional planning (VICS 9-step model); P&G/Walmart collaboration on promotional event coordination with exception management when sell-through deviates from forecast |

#### 5.2.3 Direct-Ship Exception

| Attribute | Value |
|-----------|-------|
| **Originator** | SO Agent |
| **Target** | Logistics Agent, Inventory Agent, Finance Agent |
| **Trigger** | Customer requests next-day delivery of 200 cases. Nearest DC doesn't have stock, but a plant 150 miles away has finished goods. Direct ship from plant would fulfill the order but bypasses the normal DC flow. |
| **Authorization Surface** | SO Agent owns the customer promise; Logistics controls routing; Inventory Agent controls plant FG stock (earmarked for DC replenishment); Finance assesses the cost premium |
| **Scorecard Tradeoff** | Customer (GREEN: next-day fulfilled) vs. Financial (AMBER: direct-ship cost $800 vs. normal $200) vs. Operational (AMBER: plant FG stock reduced, DC replenishment delayed) |
| **Multi-Party** | SO -> Logistics: "Direct ship feasible?" + SO -> Inventory: "Release 200 cases from plant stock?" Both must authorize. |

#### 5.2.4 Warehouse Capacity Contention

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Inventory Agent, Finance Agent |
| **Trigger** | Supply Agent negotiated a volume discount requiring acceptance of 40,000 cases this week (normal receipt is 25,000). DC is at 92% capacity. |
| **Authorization Surface** | Supply Agent controls purchasing decisions; Inventory Agent controls warehouse operations; Finance Agent controls storage cost overruns |
| **Scorecard Tradeoff** | Financial (GREEN: $18K volume discount) vs. Operational (RED: warehouse overflow risk, must use overflow storage at $0.50/case/day) vs. Strategic (volume commitment builds supplier relationship) |
| **Counter-Offer** | Inventory Agent: "Accept 30,000 now, defer 10,000 by 5 days (after outbound wave clears capacity)" |
| **Real-World Parallel** | The Oliver Wyman Supply Chain Triangle in practice: cost savings conflict with working capital constraints and operational capacity |

### 5.3 Channel & Allocation Negotiations

Multi-channel operations create some of the most contentious authorization surfaces: when supply is constrained, which channel gets served?

#### 5.3.1 Cross-Channel Allocation Under Constraint

| Attribute | Value |
|-----------|-------|
| **Originator** | Allocation Agent |
| **Target** | Channel Agents (Retail, Foodservice, E-Commerce), S&OP Agent |
| **Trigger** | Supply shortfall: only 70% of demand can be filled this week. Retail wants 60%, Foodservice wants 25%, E-Commerce wants 15%. Policy Envelope specifies allocation reserves by channel but actual demand has shifted. |
| **Authorization Surface** | Allocation Agent controls distribution; each Channel Agent owns its customer commitments; S&OP Agent owns the allocation policy |
| **Scorecard Tradeoff** | Multiple competing Customer metrics (each channel has its own OTIF) vs. Financial (margin varies by channel: E-Commerce 35%, Retail 22%, Foodservice 18%) vs. Strategic (Foodservice has 3-year exclusive contract) |
| **Multi-Party** | Allocation -> Channel(Retail): "Propose 55% instead of 60%." Channel(Retail) -> "Reject: contractual minimum is 58%." Allocation -> Channel(E-Commerce): "Propose 12% instead of 15%." Channel(E-Commerce) -> "Counter: 13% acceptable if priority on next allocation." Allocation -> S&OP: "Request policy exception: contractual minimums exceed available supply." |
| **Real-World Parallel** | During COVID-19, food manufacturers like Dot Foods, Sysco, and US Foods had to reallocate between collapsed foodservice demand and surging retail demand. Distributors shared data with manufacturers to manage allocations. Channel conflict in foodservice is well-documented (FES Magazine): broadline distributors, big-box retailers, and specialty distributors compete for the same constrained supply. SAP S/4HANA Product Allocation (PAL) implements this with priority groups and sequence-based consumption. |

#### 5.3.2 Customer Priority Override

| Attribute | Value |
|-----------|-------|
| **Originator** | SO Agent |
| **Target** | Allocation Agent, S&OP Agent |
| **Trigger** | Standard customer places a large order that would normally be partially filled. However, this customer is in a trial period and a full fill could convert them to strategic tier ($2M annual revenue). |
| **Authorization Surface** | SO Agent sees the relationship context; Allocation Agent controls entitlements; S&OP Agent owns priority tier definitions |
| **Scorecard Tradeoff** | Strategic (GREEN: $2M potential revenue) vs. Customer (AMBER: other standard customers get less) vs. Financial (GREEN: high-margin customer) |
| **Escalation Likely** | This crosses from operational into strategic territory. Agents can propose, but priority tier changes typically require human authorization. |
| **Real-World Parallel** | E2Open's "Allocation and Order Promising" handles this with priority-based consumption sequences: priority customers fulfilled first, then intercompany, then standard. The ATP allocation conflict is one of the most common SC tradeoffs. |

#### 5.3.3 Private Label vs. Branded Allocation

| Attribute | Value |
|-----------|-------|
| **Originator** | Plant Agent |
| **Target** | Allocation Agent, Channel Agent (Retail), Channel Agent (Private Label) |
| **Trigger** | Same production line makes both branded and private-label product. Capacity constraint forces a choice: produce 40,000 branded or 40,000 private label this week, not both. |
| **Authorization Surface** | Plant Agent controls production sequencing; Allocation Agent controls demand fulfillment; each Channel Agent controls its customer promises |
| **Scorecard Tradeoff** | Financial (branded: $8/case margin vs. private label: $3/case, but PL has committed volume with penalty) vs. Customer (AMBER: whichever gets delayed loses OTIF) vs. Strategic (PL contract has $50K shortfall penalty clause) |
| **Counter-Offer** | Plant Agent: "Split production: 25,000 branded + 20,000 PL this week, remainder next week with overtime" |

#### 5.3.4 E-Commerce Surge vs. Retail Replenishment

| Attribute | Value |
|-----------|-------|
| **Originator** | Channel Agent (E-Commerce) |
| **Target** | Allocation Agent, Logistics Agent, Inventory Agent |
| **Trigger** | Flash sale drives 400% demand spike on 5 SKUs for 48 hours. E-Commerce Agent requests reallocation from retail DC buffer stock. |
| **Authorization Surface** | E-Commerce Agent owns the promotional event; Allocation Agent controls cross-channel reallocation; Inventory Agent controls retail safety stock |
| **Scorecard Tradeoff** | Financial (GREEN: e-commerce margin 35%) vs. Customer (AMBER: retail stores may stockout during reallocation window) vs. Strategic (brand reputation if e-commerce orders go unfulfilled) |
| **Time Constraint** | 48-hour event means the SLA for authorization is hours, not days |

### 5.4 Procurement & Supplier Negotiations

Procurement crosses the boundary from internal coordination to external market negotiation, adding complexity around supplier relationships, contracts, and market intelligence.

#### 5.4.1 Spot Buy vs. Contract Volume

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Procurement Agent, Finance Agent |
| **Trigger** | Contract supplier can deliver in 3 weeks (within policy). Spot market offers same material in 5 days at 20% premium. Customer order requires delivery in 2 weeks. |
| **Authorization Surface** | Supply Agent identifies the need and timing; Procurement Agent controls supplier relationships and pricing authority; Finance Agent controls premium spending |
| **Scorecard Tradeoff** | Customer (GREEN with spot buy, RED without) vs. Financial (AMBER: 20% cost premium) vs. Strategic (AMBER: spot buy doesn't build supplier relationship, may undermine contract volume commitment) |
| **Counter-Offer** | Procurement Agent: "Negotiate contract supplier to 2-week expedite for $X premium (less than spot). I'll authorize because it preserves relationship." |

#### 5.4.2 Supplier Concentration Breach

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Procurement Agent, Risk Agent |
| **Trigger** | Most cost-effective PO would increase Supplier A from 38% to 45% of total spend, breaching the 40% concentration limit in the Policy Envelope. |
| **Authorization Surface** | Supply Agent optimizes cost; Risk Agent enforces diversification policy; Procurement Agent manages supplier portfolio |
| **Scorecard Tradeoff** | Financial (GREEN: $22K savings) vs. Strategic (RED: concentration risk) vs. Operational (GREEN: Supplier A has best quality record) |
| **Escalation** | Risk Agent denies authorization. Supply Agent's net benefit ($22K) is below the escalation threshold for concentration policy violations. Falls back to splitting the PO across two suppliers at slightly higher cost. |
| **Real-World Parallel** | Post-COVID supply chain resilience strategies; Oliver Wyman recommends explicit supplier concentration limits as part of "making supply chains more resilient" |

#### 5.4.3 New Supplier Qualification

| Attribute | Value |
|-----------|-------|
| **Originator** | Supply Agent |
| **Target** | Procurement Agent, Quality Agent |
| **Trigger** | MRS generates a Min Cost supply plan requiring a supplier not on the approved vendor list. The cost savings are $45K annually. |
| **Authorization Surface** | Supply Agent wants cost optimization; Procurement Agent controls the approved vendor list; Quality Agent controls qualification standards |
| **Scorecard Tradeoff** | Financial (GREEN: $45K savings) vs. Operational (AMBER: qualification takes 8-12 weeks) vs. Strategic (risk of unknown supplier quality) |
| **Multi-Party** | Supply -> Procurement: "Qualify Supplier B?" Procurement -> Quality: "Run qualification process?" Quality: "6-week audit + 4-week trial. During trial, dual-source with existing supplier as backup." |
| **CPFR Analogy** | This mirrors CPFR's approach to new trading partner onboarding where the first step is establishing a "collaboration arrangement" with agreed criteria before any operational coordination begins |

### 5.5 Logistics & Transportation Negotiations

Logistics negotiations involve shared physical infrastructure: trucks, lanes, consolidation opportunities, and cross-border requirements.

#### 5.5.1 Consolidation Opportunity

| Attribute | Value |
|-----------|-------|
| **Originator** | Logistics Agent |
| **Target** | SO Agent (multiple), Supply Agent |
| **Trigger** | Logistics Agent identifies that 3 separate LTL shipments to the same region could consolidate into 1 FTL, saving $4,200, but requires delaying 2 of the 3 shipments by 1 day. |
| **Authorization Surface** | Logistics Agent controls routing; each SO Agent controls its customer's delivery promise |
| **Scorecard Tradeoff** | Financial (GREEN: $4,200 savings) vs. Customer (AMBER: 2 customers get delivery delayed 1 day, but both are standard tier with 3-day delivery window) |
| **Multi-Party** | Logistics -> SO Agent(order A): "Authorize 1-day delay?" + Logistics -> SO Agent(order B): "Authorize 1-day delay?" Both must authorize for consolidation to proceed. |
| **Real-World Parallel** | The production routing paper (AAMAS 2024) models exactly this: a coordinator proposes "removal" transactions (shift deliveries between periods) and affected retailers vote based on their local utility change. The key insight from that research: a delivery change that costs one party $325 in increased shipping but saves $340 in reduced inventory yields a positive delta (+$15), making it rationally acceptable. |

#### 5.5.2 Mode Selection Under Time Pressure

| Attribute | Value |
|-----------|-------|
| **Originator** | SO Agent |
| **Target** | Logistics Agent, Finance Agent |
| **Trigger** | Customer needs delivery in 2 days. Ground shipping takes 4 days. Air freight delivers in 1 day but costs $8,500 vs. $1,200 for ground. |
| **Authorization Surface** | SO Agent controls the customer promise; Logistics Agent controls mode selection and carrier relationships; Finance Agent controls the transport budget |
| **Scorecard Tradeoff** | Customer (GREEN with air, RED without) vs. Financial (RED: $7,300 premium, 425% over standard) vs. Strategic (depends on customer tier and revenue at risk) |
| **Escalation Likely** | $7,300 premium likely exceeds auto-authorize threshold. Logistics Agent counter-offers: "Next-day LTL via express lane: $3,800, delivers in 2 days." If counter-offer accepted, stays within threshold. If not, escalates to human. |

#### 5.5.3 Cross-Border Compliance

| Attribute | Value |
|-----------|-------|
| **Originator** | Logistics Agent |
| **Target** | Supply Agent, Procurement Agent, Quality Agent |
| **Trigger** | Shipment to Canada requires phytosanitary certificate that the supplier didn't provide. Shipment is at the border. Options: (A) hold shipment and get certificate (3-day delay), (B) reject and re-source domestically (5 days, premium price), (C) apply for expedited certificate ($500 fee, 1-day delay). |
| **Authorization Surface** | Logistics Agent is at the execution boundary; Quality Agent controls compliance documentation; Procurement Agent manages the supplier relationship (who should have provided the certificate) |
| **Scorecard Tradeoff** | Customer (AMBER/RED depending on option) vs. Financial (varies) vs. Operational (compliance risk) |

### 5.6 Finance & Working Capital Negotiations

Finance negotiations represent the Oliver Wyman "Supply Chain Triangle" in action: every operational improvement costs money or ties up working capital.

#### 5.6.1 Working Capital vs. Service Level

| Attribute | Value |
|-----------|-------|
| **Originator** | Risk Agent |
| **Target** | Finance Agent |
| **Trigger** | Risk Agent recommends increasing safety stock from 2.0 to 2.5 WOS across strategic SKUs. This would tie up an additional $180K in working capital but reduce revenue at risk by $500K/year. |
| **Authorization Surface** | Risk Agent identifies the need; Finance Agent controls the working capital budget |
| **Scorecard Tradeoff** | Financial (AMBER: $180K working capital increase, impacts GMROI) vs. Customer (GREEN: strategic OTIF improvement) vs. Strategic (GREEN: $500K revenue protection) |
| **Real-World Parallel** | The core tension in Oliver Wyman's Supply Chain Triangle: "higher service levels are typically accompanied by higher costs, whereas reducing costs and capital employed places pressure on service levels." Sales demands high service; finance demands low working capital; manufacturing wants large batches for utilization. |

#### 5.6.2 Expedite Budget Exhaustion

| Attribute | Value |
|-----------|-------|
| **Originator** | Logistics Agent |
| **Target** | Finance Agent |
| **Trigger** | Weekly expedite budget ($8,000) exhausted by Wednesday. Three more expedite requests pending for Thursday-Friday, combined net benefit +$45,000. |
| **Authorization Surface** | Logistics Agent controls expedites; Finance Agent controls the budget constraint |
| **Scorecard Tradeoff** | Customer (GREEN: orders fulfilled) vs. Financial (RED: budget exceeded by $6,200) vs. Operational (GREEN: capacity exists) |
| **Governance Gate** | Finance Agent policy: budget overruns >10% require human authorization. $6,200 is 77.5% over weekly budget but only 0.31% of monthly budget. Counter-offer: "Approve against next week's budget with flag to S&OP for structural review." |
| **Learning Opportunity** | If this happens 3 weeks in a row, the feed-back signal triggers an S&OP re-evaluation: "Expedite budget structurally insufficient. Recommend increase from $8K to $12K/week, net benefit over 3 weeks: +$135K." |

#### 5.6.3 Volume Discount Decision

| Attribute | Value |
|-----------|-------|
| **Originator** | Procurement Agent |
| **Target** | Finance Agent, Inventory Agent, Supply Agent |
| **Trigger** | Supplier offers 12% discount for committing to 100,000 units (normal 3-month volume is 60,000). Discount saves $48K but requires carrying $150K additional inventory for 4-6 weeks. |
| **Authorization Surface** | Procurement Agent negotiates pricing; Finance Agent controls working capital; Inventory Agent controls storage capacity |
| **Scorecard Tradeoff** | Financial (mixed: $48K savings vs. $150K working capital tie-up vs. carrying cost $5,200/month vs. E&O risk) vs. Operational (AMBER: warehouse capacity strain) vs. Strategic (builds supplier relationship) |
| **Multi-Party** | Procurement -> Finance: "Authorize $150K working capital commitment?" + Procurement -> Inventory: "Can DCs absorb 67% volume increase for 4-6 weeks?" Both must authorize. |

### 5.7 S&OP Consensus Negotiations

S&OP negotiations operate at the highest level: agents representing functional perspectives debate the Policy Envelope parameters that govern all downstream decisions. This is where the AAP's Consensus Board architecture (Section 8) operates.

#### 5.7.1 Seasonal Pre-Build Authorization

| Attribute | Value |
|-----------|-------|
| **Originator** | Demand Agent |
| **Target** | Finance Agent, Plant Agent, Inventory Agent |
| **Trigger** | Demand Agent's forecast shows 40% seasonal demand increase in Q4. Proposes pre-building 200,000 cases in Q3 to smooth production and ensure availability. |
| **Authorization Surface** | Demand Agent owns the forecast; Finance Agent controls the pre-build investment ($800K); Plant Agent controls production capacity; Inventory Agent controls storage |
| **Scorecard Tradeoff** | Customer (GREEN: seasonal availability assured) vs. Financial (AMBER: $800K investment 8 weeks before revenue; $32K carrying cost; E&O risk if forecast wrong) vs. Operational (GREEN: avoids Q4 overtime and capacity crunch) |
| **Multi-Party** | Three-way authorization: Finance (budget), Plant (capacity), Inventory (storage). Each can counter-offer. Finance: "Authorize $600K, stage the remaining $200K based on sell-through signals." |
| **CPFR Analogy** | This is directly analogous to CPFR's joint business planning step where trading partners negotiate promotional volumes and pre-build requirements. P&G and Walmart pioneered this, achieving 70% inventory reduction and service level improvement from 96% to 99%. |

#### 5.7.2 Policy Envelope Parameter Dispute

| Attribute | Value |
|-----------|-------|
| **Originator** | Service Agent |
| **Target** | Finance Agent, Supply Agent |
| **Trigger** | Strategic OTIF has been below floor (93% vs. 95% target) for 3 consecutive weeks. Service Agent proposes raising safety stock and allocation reserves. Supply Agent argues the root cause is lead time variability, not stock levels. |
| **Authorization Surface** | Three agents with different theories of the problem, each requiring different Policy Envelope changes |
| **Multi-Resolution** | Service Agent: "Increase strategic safety stock from 2.0 to 2.5 WOS." Supply Agent: "Counter-proposal: add secondary supplier to reduce lead time variability (concentration limit exception)." Risk Agent: "Support Supply Agent's proposal — diversification addresses root cause." Finance Agent: "Service Agent's proposal costs $180K. Supply Agent's proposal costs $45K setup + $8K ongoing. Authorize Supply Agent's approach." |
| **Consensus Board** | This is a full board discussion: multiple agents post proposals with scorecards, reply with analyses, and the S&OP Agent synthesizes a resolution or escalates to the VP Supply Chain. |

#### 5.7.3 Portfolio Rationalization

| Attribute | Value |
|-----------|-------|
| **Originator** | Finance Agent |
| **Target** | Channel Agents, Demand Agent, Supply Agent, Plant Agent |
| **Trigger** | Finance Agent identifies 200 SKUs (out of 2,000) with negative gross margin and <5% of revenue. Proposes discontinuation to free working capital and simplify production. |
| **Authorization Surface** | Finance controls profitability analysis; each Channel Agent controls channel-specific revenue; Demand Agent controls forecast implications; Plant Agent controls production complexity |
| **Multi-Party** | Finance -> Channel(Retail): "15 of these SKUs are in your channel. Impact?" Channel(Retail): "7 are contractually required for planogram compliance. Removing them triggers penalty clauses totaling $120K." Finance: "Net benefit after penalties: still +$280K. Propose removing 193 SKUs, keeping 7 contractual." |

### 5.8 CPFR-Style Exception Management

The CPFR (Collaborative Planning, Forecasting, and Replenishment) framework, standardized by VICS as a 9-step model, provides a well-established precedent for structured multi-party exception resolution. The AAP generalizes CPFR's exception management from a human process to an agent process.

#### 5.8.1 CPFR Exception Types as AAP Authorization Scenarios

| CPFR Exception | AAP Equivalent | Example |
|----------------|---------------|---------|
| **Sales forecast exception** | Demand Agent -> S&OP Agent | Actual sales 20% below forecast for 3 consecutive weeks. Demand Agent proposes forecast revision; S&OP Agent evaluates supply plan impact. |
| **Order forecast exception** | Supply Agent -> Procurement Agent | Supplier signals 2-week delay on a key component. Supply Agent evaluates alternatives and requests authorization for secondary sourcing. |
| **Promotional deviation** | Channel Agent -> Demand Agent, Finance Agent | Promotion sell-through at 40% of forecast. Channel Agent proposes: (A) extend promotion 1 week, (B) reduce price further, (C) accept E&O. Each requires different authorization. |
| **Capacity constraint exception** | Plant Agent -> Supply Agent, Allocation Agent | Equipment failure reduces capacity by 30% for 2 weeks. Plant Agent communicates constraint; Supply Agent evaluates emergency sourcing; Allocation Agent adjusts entitlements. |

#### 5.8.2 Key CPFR Principle Applied to AAP

The CPFR model's most important insight — which the AAP inherits — is the concept of **pre-agreed exception criteria**. Trading partners define thresholds in advance (e.g., "flag any forecast deviation >15%"). The AAP generalizes this as the `AgentAuthority` table with configurable `net_benefit_threshold` and `auto_authorize_threshold` values, allowing the governance gates to be tuned per decision type and agent pair.

---

## 6. Levels of Application

The AAP applies identically at every level of the Powell cascade. The only differences are the time horizon, the artifacts being evaluated, and the authority boundaries.

### 6.1 Strategic Level (S&OP / Policy Envelope)

**Who negotiates**: Demand Agent, Supply Agent, Finance Agent, Service Agent, Risk Agent

**What they negotiate**: Policy Envelope parameters (safety stock targets, OTIF floors, allocation reserves, expedite caps, DOS ceilings, supplier concentration limits)

**Example**: The Service Agent wants to raise the strategic segment OTIF floor from 95% to 97%. The what-if shows this requires $180K additional safety stock (Financial: AMBER) but reduces revenue at risk by $500K (Strategic: GREEN). Net benefit: +$320K.

The Finance Agent evaluates: Does the additional $180K fit within the inventory budget cap? Are there competing capital requests? If the budget allows, AUTHORIZE. If not, COUNTER-OFFER with a phased increase (96% now, 97% next quarter).

**Time horizon**: Weekly/monthly
**Artifacts**: PolicyEnvelope (hash-linked)

### 6.2 Tactical Level (MRS / Supply Baseline Pack)

**Who negotiates**: MRS candidates represent different strategies (Min Cost, Service Max, Parametric CFA). The Supply Agent evaluates the tradeoff frontier.

**Example**: The Supply Agent prefers the Service Max candidate but it requires 3 new suppliers not on the approved vendor list. The Procurement Agent must authorize new vendor qualification.

**Time horizon**: Weekly
**Artifacts**: SupplyBaselinePack (hash-linked)

### 6.3 Operational Level (Supply Commit / Allocation Commit)

**Who negotiates**: Supply Agent, Allocation Agent, Logistics Agent

**Example**: The Allocation Agent wants to over-allocate to a strategic segment (beyond the 30% reserve in the Policy Envelope). The S&OP Agent must authorize the policy exception, showing the balanced scorecard impact of the deviation.

**Time horizon**: Daily
**Artifacts**: SupplyCommit, AllocationCommit (hash-linked)

### 6.4 Execution Level (TRM Decisions)

**Who negotiates**: ATP Agent, Rebalancing Agent, PO Creation Agent, Order Tracking Agent, SO Agent

**Example**: The SO agent scenario described throughout this document. An ATP agent evaluating whether to partially fill vs. defer vs. expedite, where some options require authorization from Logistics or Inventory.

**Time horizon**: Real-time (seconds)
**Artifacts**: ATP decisions, rebalancing recommendations, PO actions

### 6.5 Unified Protocol Across Levels

The same `AuthorizationRequest` / `AuthorizationResponse` protocol works at every level. The only things that change:

| Attribute | Strategic | Tactical | Operational | Execution |
|-----------|-----------|----------|-------------|-----------|
| SLA for response | Hours | Hours | Minutes | Seconds |
| Scorecard granularity | Aggregate (category) | Product family | SKU-site | Individual order |
| Net benefit threshold | $100K+ | $10K+ | $1K+ | Configurable per TRM |
| Escalation target | Executive | S&OP Director | MPS Manager | TRM Analyst |
| Max negotiation rounds | 5 | 3 | 2 | 1 |
| Auto-escalate after | 4 hours | 1 hour | 15 minutes | 30 seconds |

---

## 7. Escalation: When Agents Can't Resolve

### 7.1 Escalation Triggers

| Trigger | Description | Example |
|---------|-------------|---------|
| **Resource deadlock** | Two or more requests compete for the same resource, equal priority | Two expedite requests for the same carrier slot |
| **Policy breach** | Authorization would exceed a hard policy limit | Expedite spend > 100% of budget |
| **Counter-offer rejected** | Originating agent rejects counter-offer, net benefit still above threshold | Thursday delivery doesn't meet customer SLA |
| **Timeout** | No response within SLA | Target agent offline or processing backlog |
| **Insufficient net benefit** | Net benefit positive but below threshold | $3,000 net benefit on a $5,000 threshold |

### 7.2 What the Human Sees

When an authorization thread escalates, the human reviewer sees a **pre-digested decision** -- not a blank screen:

```
ESCALATION: Authorization Conflict
Thread: AR-20260209-0847-001
From: SO Agent (order 8834, strategic customer)
To: Logistics Agent (expedite authorization)

SITUATION:
  SO Agent requests $2,400 expedite for strategic order 8834.
  Logistics Agent has competing request AR-002 ($1,800, net +$22K).
  Combined requests exceed weekly expedite budget by $200.

OPTIONS:
  A. Approve SO Agent's request, deny AR-002
     Net benefit: +$15,600
     Scorecard: [6 GREEN, 2 AMBER]

  B. Approve AR-002, deny SO Agent's request
     Net benefit: +$22,000
     Scorecard: [5 GREEN, 3 AMBER]

  C. Approve both, authorize $200 budget overage
     Combined net benefit: +$37,600
     Scorecard: [4 GREEN, 4 AMBER]
     Requires: Finance approval for budget exception

  D. SO Agent falls back to reallocation (unilateral)
     Net benefit: +$12,000
     Scorecard: [5 GREEN, 1 AMBER, 2 NEUTRAL]

RECOMMENDATION: Option C (approve both, request budget exception)
  Reasoning: Combined net benefit exceeds budget overage by 188x.
  The $200 overage is 2.5% above the weekly cap.
```

The human makes a judgment call with full context. They're not doing analysis -- the agents already did that. They're applying business judgment to a situation the agents couldn't resolve autonomously.

### 7.3 Human Decisions Feed Back

Every human resolution of an escalation is captured as training data:

- **Decision**: Which option the human chose
- **Reasoning**: Captured via the override reason pattern (dropdown + free text)
- **Outcome**: Tracked via feed-back signals (was the decision a good one?)
- **Training signal**: Written to replay buffer with `is_expert=True`

Over time, agents learn the human's resolution patterns. A Logistics Agent that sees humans consistently approving small budget overages for strategic customers will learn to authorize those proactively, reducing escalations.

### 7.4 Explanation of Authorization Decisions

The Ask Why pattern surfaces authorization context through `AgentContextExplainer`. When a planner reviews an escalated decision, the explanation includes:

1. **Authority Classification**: Whether the decision was UNILATERAL (auto-resolved), REQUIRES_AUTHORIZATION (escalated), or ADVISORY
2. **Approval Chain**: Which agent(s) the decision was escalated to, and why (e.g., "Cost delta $15K exceeds $10K MANAGER threshold")
3. **Balanced Scorecard Impact**: The net benefit calculation across Financial, Customer, Operational, and Strategic dimensions
4. **Counterfactual Boundaries**: "If the PO value were below $10,000, this would be auto-resolved at OPERATOR level"

This integrates with the three Board-as-Substrate adapters (Section 10):
- **React UI**: `AskWhyPanel.jsx` renders authority context, guardrails, attribution, and counterfactuals as collapsible sections
- **LLM Chat (OpenClaw)**: Agent formats authorization reasoning as natural language via explanation templates
- **Agent Adapter**: Structured `ContextAwareExplanation` JSON for agent-to-agent authorization transparency

---

## 8. The Agentic Consensus Board (S&OP Application)

At the S&OP level, the authorization protocol becomes a **continuous consensus mechanism** for Policy Envelope parameters.

### 8.1 Functional Agents

| Agent | Represents | Primary Objective | Negotiation Posture |
|-------|-----------|-------------------|---------------------|
| **Demand Agent** | VP Sales / Marketing | Maximize revenue, service levels | Push for higher OTIF floors, more safety stock |
| **Supply Agent** | VP Operations | Minimize total supply cost | Push for lower safety stock, longer lead times |
| **Finance Agent** | CFO / Controller | Maximize GMROI, control working capital | Push for inventory caps, budget discipline |
| **Service Agent** | VP Customer Success | Maximize OTIF, minimize backorders | Push for higher allocation reserves |
| **Procurement Agent** | VP Procurement | Minimize unit cost, manage supplier risk | Push for concentration limits, volume discounts |
| **Risk Agent** | Chief Risk Officer | Minimize tail risk, ensure resilience | Push for diversification, buffer capacity |

### 8.2 Continuous Parameter Negotiation

Rather than a quarterly S&OP meeting where humans debate spreadsheets, agents continuously evaluate Policy Envelope parameters using feed-back signals:

```
Feed-Back Signal: OTIF for strategic segment dropped to 93%
                  (floor: 95%) over last 2 weeks

Risk Agent observes:
  -> Runs what-if: "What if safety stock for strategic SKUs
     increases from 2.0 WOS to 2.5 WOS?"
  -> Scorecard: Customer GREEN, Financial AMBER (+$45K inventory)
  -> Net benefit: +$120K (avoided revenue loss)

Risk Agent -> Finance Agent: AuthorizationRequest
  "Authorize $45K inventory increase for strategic SKUs.
   Net benefit +$120K. Financial quadrant goes AMBER."

Finance Agent evaluates:
  Current inventory budget: $1.8M, utilized: $1.72M
  $45K increase -> $1.765M (98% of budget) -> AMBER but within cap
  No competing capital requests this week

Finance Agent -> "AUTHORIZE"

Risk Agent -> S&OP Agent: "Apply revised safety stock parameters"
S&OP Agent: Updates PolicyEnvelope, new hash generated,
            cascades to downstream layers
```

### 8.3 The Net Benefit Threshold as Governance

The threshold serves as a governance gate:

| Net Benefit vs Threshold | Outcome |
|--------------------------|---------|
| **Well above threshold** (>2x) | Agent-to-agent authorization, no human involvement |
| **Above threshold** (1-2x) | Agent-to-agent authorization, logged for review |
| **Near threshold** (0.5-1x) | Agent proposes, human reviews before execution |
| **Below threshold** (<0.5x) | Rejected -- not worth the coordination cost |
| **Negative** | Rejected -- makes things worse |

The threshold is itself a Policy Envelope parameter, tunable by the S&OP layer. A company in a growth phase might lower thresholds (more agent autonomy). A company in a cost-cutting phase might raise them (more human oversight).

---

## 9. Relationship to Existing Architecture

### 9.1 What Already Exists

| Existing Component | AAP Role |
|-------------------|----------|
| **PolicyEnvelope** (planning cascade) | The parameters being negotiated at S&OP level; the thresholds that define GREEN/AMBER/RED |
| **Balanced Scorecard** (stochastic sampler) | The evaluation framework -- already computes Financial, Customer, Operational, Strategic metrics with P10/P50/P90 |
| **Feed-back Signals** (cascade models) | The evidence basis -- outcome metrics that trigger authorization requests |
| **What-if engine** (`run_what_if()` on PolicyEnvelope) | The scenario evaluation -- already evaluates parameter changes; extend to evaluate any proposed action |
| **Override capture** (TRM worklist) | The human escalation pattern -- already captures Accept/Override/Reject with reason codes, writes to replay buffer |
| **Hash-linked artifacts** (PE -> SupBP -> SC -> SBP -> AC) | The audit trail -- every authorization request references the artifacts it would modify |
| **Agent Performance Score / Override Rate / Touchless Rate** (decision tracking) | The learning metrics -- measure whether agents are getting better at resolving without escalation |
| **Multi-Stage CTP** (`MultiStageCTPService`) | Feasibility engine -- traverses the supply chain DAG upstream to determine available quantity, cumulative lead time, and binding constraints at each stage. Agents use CTP to evaluate whether proposed actions are physically feasible before requesting authorization. See [CTP_CAPABILITIES.md](CTP_CAPABILITIES.md) |
| **Full-Level Pegging** (`PeggingService`) | Traceability engine -- every unit of supply is linked to specific demand (customer order, forecast, inter-site order). Agents can trace pegging chains to understand the downstream impact of supply reallocation or upstream impact of demand changes |
| **AATP Consumption Records** (`AATPConsumptionRecord`) | Audit trail for priority-based ATP consumption decisions with pegging links, enabling agents to see which orders consumed which supply tiers |

### 9.2 What the AAP Adds

| New Component | Purpose |
|---------------|---------|
| **AuthorizationRequest / Response** | Structured protocol for cross-authority actions |
| **AgentAuthority** | Defines what each agent can do unilaterally vs. must request |
| **AuthorizationThread** | Tracks multi-turn exchanges (request -> counter -> accept) |
| **Resource Contention Resolution** | When multiple agents compete for the same resource |
| **Escalation Router** | Determines which human role should receive escalated threads |
| **Threshold-Based Governance** | Net benefit thresholds that control agent autonomy |

### 9.3 Feed-Forward Contracts Become Authorization Surfaces

The existing cascade already defines feed-forward contracts:

```
PolicyEnvelope -> SupplyBaselinePack -> SupplyCommit -> AllocationCommit
```

Each arrow is a point where a downstream agent consumes an upstream artifact. The AAP adds *lateral* arrows at each level:

```
                   S&OP Level
    Demand <---> Supply <---> Finance <---> Risk
        \          |           /
         \         v          /
          SupplyBaselinePack
              |
              v      Logistics <--- authorization surface
          SupplyCommit <---> PO Agent
              |           (supply_pegging populated from pegging links)
              v      Inventory <--- authorization surface
         AllocationCommit <---> SO Agent
              |           (pegging_summary populated from pegging links)
              v
          AATP Engine (creates pegging links + consumption records)
              |
              v      Multi-Stage CTP <--- feasibility check
          Execution (TRM agents negotiate laterally)
              |
              v
          Full-Level Pegging (demand-to-supply traceability across all stages)
```

**CTP as Authorization Input**: When an agent evaluates a what-if scenario that involves supply reallocation, the multi-stage CTP engine calculates the impact on promise dates and upstream availability across the network. The pegging chain shows exactly which downstream orders would be affected by reallocating supply. This provides the *evidence basis* for authorization requests -- not just "this costs $2,400" but "this displaces order ORD-4471 which is pegged to this inventory, and upstream CTP shows a 3-day lead time to replenish."

---

## 10. Board-as-Substrate Architecture

### 10.1 Design Principle

The `AuthorizationThread` and `AuthorizationMessage` tables are structurally identical to a forum: threads with posts, replies, and status tracking. This is not a coincidence. Inspired by Visser's description of Moltbook -- where autonomous agents post, reply, form subcommunities, and build reputation -- the AAP data model IS the board.

Rather than building a traditional REST API consumed by a single React frontend, the AAP exposes **one shared Board Service** with **three adapter layers**:

```
                    ┌──────────────────────────┐
                    │     Board Service         │
                    │ (AuthorizationThread/Msg) │
                    │  + Contention Resolution  │
                    │  + Escalation Router      │
                    │  + Outcome Tracking       │
                    └──────┬──────┬──────┬──────┘
                           │      │      │
              ┌────────────┘      │      └────────────┐
              │                   │                    │
    ┌─────────v─────────┐ ┌──────v──────┐ ┌──────────v──────────┐
    │   React Adapter   │ │ LLM Chat    │ │   Agent Adapter     │
    │                   │ │ Adapter     │ │                     │
    │ Enterprise UX     │ │ (DeepSeek)  │ │ Structured protocol │
    │ Dashboards, forms │ │             │ │ or natural language  │
    │ Worklists, charts │ │ NL interface│ │ Agent-to-agent      │
    │                   │ │ Daily ops   │ │                     │
    │ Who: Demos,       │ │ Who: Power  │ │ Who: Autonomous     │
    │ compliance, exec  │ │ users, ops  │ │ agents at all       │
    │ review            │ │ managers    │ │ cascade levels      │
    └───────────────────┘ └─────────────┘ └─────────────────────┘
```

### 10.2 The Three Adapters

#### React UI Adapter (Enterprise)
- Traditional dashboard UI for enterprise customers who need visual oversight
- Worklist pattern: `AuthorizationInbox.jsx` shows pending threads, filterable by status/agent/priority
- Thread detail view: full exchange history with balanced scorecards at each step
- Ideal for: demos, compliance audits, executive review, initial customer onboarding
- Consumes the same Board Service API as the other adapters

#### LLM Chat Adapter (DeepSeek / Open-Source)
- Natural language interface powered by open-source models (DeepSeek, Qwen, etc.)
- Users interact via chat: "Show me the pending authorization requests for logistics this week"
- The LLM translates between natural language and the Board Service API
- Zero marginal inference cost via local deployment on commodity hardware
- Ideal for: daily operations, power users who prefer NL to forms, mobile scenarios
- Visser's thesis: open-source models have "decimated deployment costs" -- local inference on mid-range GPUs eliminates the need for expensive API calls

#### Agent Adapter (Structured + NL-Capable)
- Primary adapter for autonomous agent-to-agent authorization
- Structured mode: agents post `AuthorizationRequest` JSON directly to the Board Service
- NL-capable mode (future): agents post natural language proposals, other agents respond in NL, the board tracks the structured outcome
- This is where the Moltbook pattern emerges: agents form subcommunities (coalitions around multi-party authorizations), build reputation (track record of good counter-offers), and establish precedent (resolution patterns that become auto-authorization rules)

### 10.3 Why Not a Fork

The user asked whether both conventional (React) and agentic (Moltbook/DeepSeek) approaches should be forked. The answer is no. The data model IS the board. The three adapters are presentation layers over the same data. A single authorization thread might be:

1. **Created** by an agent via the Agent Adapter (structured `AuthorizationRequest`)
2. **Counter-offered** by another agent via the Agent Adapter
3. **Escalated** to a human who reviews it via the React Adapter (dashboard with scorecard comparison)
4. **Resolved** by the human typing a decision into the LLM Chat Adapter ("approve the SO agent's request, the net benefit is clear")

All four interactions are stored in the same `AuthorizationThread` and `AuthorizationMessage` tables. The adapter is just the interface.

### 10.4 Emergent Moltbook-Style Behavior

With the Agent Adapter, behaviors described by Visser naturally emerge:

| Moltbook Pattern | AAP Manifestation |
|-----------------|-------------------|
| **Agents post independently** | Agents post `AuthorizationRequest` when they detect a cross-authority opportunity |
| **Agents reply and debate** | Target agents respond with `AUTHORIZE`, `COUNTER_OFFER`, or `DENY` with reasoning |
| **Subcommunities form** | Multi-party authorizations create temporary coalitions (SO + Supply + Inventory) |
| **Reputation builds** | Agent track records (counter-offer acceptance rate, authorization accuracy, escalation frequency) become "reputation" |
| **Precedent establishes** | Resolution patterns are stored and matched. After 12 similar resolutions, auto-authorization rule created. |
| **Unsolicited alternatives** | An agent monitoring the board sees a pending thread and offers a better alternative the originator didn't consider |

### 10.5 LLM-First Interface Design

For the LLM Chat Adapter, the interaction model follows DeepSeek's zero-cost inference thesis:

```
Human: "What's happening on the authorization board right now?"

LLM:   "3 active threads:
        1. SO Agent requesting expedite ($2,400) from Logistics for order 8834.
           Net benefit: +$15,600. Status: PENDING (2 min).
        2. Allocation Agent requesting policy exception from S&OP for
           strategic over-allocation. Net benefit: +$22,000. Status: COUNTER_OFFERED.
        3. Plant Agent requesting maintenance window from Supply Agent.
           Status: AUTHORIZED, executing Saturday.

        Thread #1 expires in 28 minutes. Want me to show the scorecard?"
```

### 10.6 DAG-Based Agent Discovery

A critical question for any multi-agent system: **how does an agent know which other agents to negotiate with?** The AAP uses a dual-pattern architecture that combines the supply chain's physical topology with cross-functional topic subscriptions.

#### Pattern 1: DAG-Adjacent Discovery (Operational Agents)

The supply chain configuration already defines a directed acyclic graph (DAG) through the `site` and `transportation_lane` tables. Each `TransportationLane` links a `from_site_id` (upstream) to a `to_site_id` (downstream), and each `Site` exposes `upstream_lanes` and `downstream_lanes` relationships. This existing topology is the natural source for operational agent discovery.

Every operational agent is bound to one or more sites. When an agent needs authorization for a cross-authority action, the DAG tells it who to talk to:

```
                         ┌────────────┐
                         │ Supplier   │  from_site_id
                         │ Agent      │──────────────┐
                         └────────────┘              │
                                              ┌──────v──────┐
          ┌────────────┐                      │ TransLane    │
          │ Plant      │◄─────────────────────│ (from→to)   │
          │ Agent      │  to_site_id          └─────────────┘
          └─────┬──────┘
                │ downstream_lanes
                v
         ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
         │ DC / Inv     │─────>│ Wholesaler   │─────>│ Retailer /   │
         │ Agent        │      │ Agent        │      │ Channel Agent│
         └──────────────┘      └──────────────┘      └──────────────┘
```

**Discovery rule for operational agents**: An agent at site S can directly negotiate with:
- **Upstream agents**: agents at sites reachable via `upstream_lanes` (suppliers, feeder plants)
- **Downstream agents**: agents at sites reachable via `downstream_lanes` (DCs, customers, channels)
- **Sibling agents**: agents at sites sharing the same upstream or downstream site (competing for shared capacity or supply)

This leverages the existing model relationships:

```python
# Already defined in models/supply_chain_config.py (Site model):
#   upstream_lanes = relationship("TransportationLane",
#       foreign_keys="TransportationLane.to_site_id")
#   downstream_lanes = relationship("TransportationLane",
#       foreign_keys="TransportationLane.from_site_id")

class AgentDiscovery:
    """Discovers negotiation partners using the supply chain DAG
    and cross-functional board subscriptions."""

    def __init__(self, db: Session, config_id: int):
        self.db = db
        self.config_id = config_id
        self._adjacency: Dict[int, Set[int]] = {}
        self._build_adjacency()

    def _build_adjacency(self):
        """Build adjacency map from transportation_lane table."""
        lanes = (
            self.db.query(TransportationLane)
            .filter(TransportationLane.config_id == self.config_id)
            .all()
        )
        for lane in lanes:
            self._adjacency.setdefault(lane.from_site_id, set()).add(lane.to_site_id)
            self._adjacency.setdefault(lane.to_site_id, set()).add(lane.from_site_id)

    def get_dag_adjacent_agents(self, site_id: int) -> List[AgentInfo]:
        """Return agents at sites directly connected to the given site.

        Operational agents use this to find their immediate negotiation
        partners -- the agents they share material flow with."""
        neighbor_site_ids = self._adjacency.get(site_id, set())
        return self._resolve_agents(neighbor_site_ids)

    def get_sibling_agents(self, site_id: int, direction: str = "upstream") -> List[AgentInfo]:
        """Return agents at sites that share the same upstream (or downstream)
        partner -- i.e., sites competing for the same supply or capacity.

        Example: Two DCs fed by the same plant are siblings. When one DC
        requests additional supply, the Plant Agent should loop in the other
        DC's Inventory Agent because the allocation is zero-sum."""
        shared_sites: Set[int] = set()
        lanes = (
            self.db.query(TransportationLane)
            .filter(TransportationLane.config_id == self.config_id)
        )
        if direction == "upstream":
            # Find sites that share the same upstream supplier as site_id
            my_upstream = {
                l.from_site_id for l in lanes
                if l.to_site_id == site_id
            }
            for up_id in my_upstream:
                for l in lanes:
                    if l.from_site_id == up_id and l.to_site_id != site_id:
                        shared_sites.add(l.to_site_id)
        else:
            # Find sites that share the same downstream customer as site_id
            my_downstream = {
                l.to_site_id for l in lanes
                if l.from_site_id == site_id
            }
            for down_id in my_downstream:
                for l in lanes:
                    if l.to_site_id == down_id and l.from_site_id != site_id:
                        shared_sites.add(l.from_site_id)
        return self._resolve_agents(shared_sites)
```

**Why DAG-adjacent?** The authorization surface (Section 3.3) exists wherever one agent's authority ends and another's begins. For material-flow agents, that boundary is a transportation lane. A Plant Agent doesn't need to know about a Retailer three hops away -- it only needs the immediately adjacent DC or Wholesaler. If a negotiation needs to propagate further, the adjacent agent initiates its own authorization thread with *its* neighbors, creating a chain of bilateral negotiations rather than an all-to-all broadcast.

#### Pattern 2: Board Subscription (Cross-Functional Agents)

Cross-functional agents -- Finance, Quality, Risk, Service, S&OP -- are not bound to a single site. They monitor the entire network for events in their domain. These agents don't discover partners through the DAG; they **subscribe to board topics** and respond when relevant threads appear.

```python
# Cross-functional agents subscribe to authorization board topics.
# When a thread touches their domain, they are automatically included.

BOARD_SUBSCRIPTIONS: Dict[str, List[str]] = {
    "finance_agent":     ["budget_exception", "expedite_cost", "working_capital",
                          "write_off", "capex_request", "promotional_pricing"],
    "quality_agent":     ["material_hold", "supplier_qualification", "disposition",
                          "substitution_approval", "production_rerun"],
    "risk_agent":        ["concentration_breach", "single_source", "lead_time_spike",
                          "demand_anomaly", "geopolitical_flag"],
    "service_agent":     ["otif_breach", "fill_rate_drop", "service_level_exception",
                          "customer_escalation"],
    "sop_agent":         ["policy_exception", "parameter_change", "guardrail_breach",
                          "demand_plan_override", "portfolio_rationalization"],
    "maintenance_agent": ["equipment_failure", "pm_schedule_conflict",
                          "capacity_reduction", "spare_parts_expedite"],
}

class AgentDiscovery:
    # ... (continued from above)

    def get_board_subscriptions(self, agent_type: str) -> List[str]:
        """Return the board topics a cross-functional agent monitors.

        When an operational agent creates an AuthorizationThread tagged with
        one of these topics, the subscribing cross-functional agent is
        automatically added as a participant."""
        return BOARD_SUBSCRIPTIONS.get(agent_type, [])

    def get_subscribers_for_topic(self, topic: str) -> List[str]:
        """Given an authorization topic, return which cross-functional agents
        should be notified.

        Example: An AuthorizationThread tagged 'expedite_cost' will
        automatically loop in the Finance Agent."""
        return [
            agent_type
            for agent_type, topics in BOARD_SUBSCRIPTIONS.items()
            if topic in topics
        ]
```

**Why subscription?** A Finance Agent doesn't care which site initiated the expedite -- it cares that *any* expedite exceeding a budget threshold was proposed. The board topic model mirrors how real cross-functional stakeholders operate: the CFO doesn't review every PO, but gets alerted when cumulative expedite spend crosses a threshold. The subscription pattern also naturally handles the "unsolicited alternative" behavior from Section 10.4: a Risk Agent monitoring `concentration_breach` topics might proactively post a warning to a Procurement thread it was never explicitly invited to.

#### Combined Discovery: Operational Push + Cross-Functional Listen

The two patterns compose cleanly:

```
Operational Agent (Plant Agent)                Cross-Functional Agent (Finance Agent)
        │                                              │
        │ 1. "I need a rush PO for component X"       │
        │                                              │
        │ 2. AgentDiscovery.get_dag_adjacent_agents()  │
        │    → [Supplier Agent, DC Agent]              │
        │                                              │
        │ 3. Creates AuthorizationThread               │
        │    topic: "rush_po"                          │
        │    tags: ["expedite_cost", "lead_time_spike"] │
        │                                              │
        │ 4. Posts request to Supplier Agent (DAG)     │
        │    ────────────────────────────────────►     │
        │                                              │
        │                           5. Board Service matches tags
        │                              to subscriptions:
        │                              "expedite_cost" → Finance Agent
        │                              "lead_time_spike" → Risk Agent
        │                                              │
        │                           6. Finance Agent auto-joined
        │                              to thread
        │                              ◄──────────────┤
        │                                              │
        │ 7. Three-party thread:                       │
        │    Plant ↔ Supplier ↔ Finance                │
        │    resolves via standard AAP protocol        │
        │    (Section 4)                               │
```

**Step-by-step**:
1. The Plant Agent detects it needs a rush PO (e.g., from a feed-back signal showing impending stockout).
2. `AgentDiscovery.get_dag_adjacent_agents()` identifies the Supplier Agent as the direct negotiation partner (connected via `transportation_lane`).
3. The Plant Agent creates an `AuthorizationThread` with topic `rush_po` and tags `expedite_cost` and `lead_time_spike` (derived from balanced scorecard impact -- the what-if shows AMBER on financial and operational dimensions).
4. The thread is posted, targeting the Supplier Agent (DAG-adjacent partner).
5. The Board Service's tag-matching logic scans `BOARD_SUBSCRIPTIONS` and finds that `expedite_cost` maps to `finance_agent` and `lead_time_spike` maps to `risk_agent`.
6. Finance Agent and Risk Agent are auto-joined to the thread as participants.
7. The thread resolves via the standard AAP multi-party protocol: Supplier Agent may counter-offer with a partial expedite, Finance Agent approves or denies the budget exception, Risk Agent flags if this creates single-source concentration.

#### Discovery Propagation: Multi-Hop Negotiations

Some negotiations require agents beyond immediate DAG neighbors. Rather than all-to-all broadcasting, the AAP uses **propagation chains**:

```
Scenario: Retailer requests surge allocation

Retailer Agent                     DC Agent                        Plant Agent
     │                                │                                │
     │ 1. Request: 150% of           │                                │
     │    allocation entitlement     │                                │
     │ ──────────────────────────►   │                                │
     │                                │ 2. DC cannot fulfill from     │
     │                                │    current stock. Needs       │
     │                                │    upstream supply.           │
     │                                │ ──────────────────────────►   │
     │                                │                                │
     │                                │ 3. Plant Agent counter-offers │
     │                                │    partial (110%) with        │
     │                                │    remainder in 5 days        │
     │                                │ ◄────────────────────────────  │
     │                                │                                │
     │ 4. DC Agent relays to Retailer│                                │
     │    with its own adjustments   │                                │
     │ ◄──────────────────────────── │                                │
```

Each agent only talks to its DAG neighbors. The DC Agent doesn't expose the Plant Agent's internal constraints to the Retailer -- it translates the upstream counter-offer into its own response. This preserves the **information encapsulation** principle: agents share balanced scorecard impact, not internal state.

When propagation crosses more than 2 hops, the Board Service links the threads via `parent_thread_id`, maintaining full traceability without requiring a global coordinator.

#### Configuration: Agent-to-Site Binding

The `AgentDiscovery` service requires knowing which agent type is bound to which site(s). This mapping comes from two sources:

| Agent Category | Binding Source | Cardinality |
|---------------|---------------|-------------|
| **Operational** (Plant, Inventory, Channel) | `agent_authority.site_ids[]` | 1 agent : 1..N sites |
| **Functional** (Supply, Allocation, SO/ATP) | Cascade layer scope (config-wide) | 1 agent : all sites in scope |
| **Cross-Functional** (Finance, Quality, Risk) | No site binding; topic subscription only | 1 agent : all threads matching topics |

For operational agents bound to multiple sites (e.g., a regional Inventory Agent managing 3 DCs), `get_dag_adjacent_agents()` returns the union of all neighbors across all bound sites.

---

## 11. Implementation Design

### 11.1 New Models

```python
class AgentAuthority(Base):
    """Defines what actions each agent type can take and what requires authorization."""
    __tablename__ = "agent_authority"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    agent_type = Column(String(50), nullable=False)    # so_agent, logistics_agent, etc.
    action_type = Column(String(50), nullable=False)    # reallocate, expedite, transfer, etc.
    authority = Column(String(20), nullable=False)       # UNILATERAL, REQUIRES_AUTH, FORBIDDEN
    constraints = Column(JSON)                           # e.g., {"max_cost": 5000, "budget_pct": 0.1}
    authorization_target = Column(String(50))            # Which agent to request auth from

    # Governance
    net_benefit_threshold = Column(Float, default=5000)
    auto_authorize_threshold = Column(Float)             # Above this, target agent auto-approves
    escalation_role = Column(String(50))                 # Human role for escalations


class AuthorizationThread(Base):
    """Tracks a cross-authority authorization exchange."""
    __tablename__ = "authorization_thread"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

    # Participants
    requesting_agent = Column(String(50), nullable=False)
    target_agent = Column(String(50), nullable=False)

    # Status
    status = Column(String(20), nullable=False)          # OPEN, AUTHORIZED, DENIED,
                                                          # COUNTER_OFFERED, ESCALATED,
                                                          # EXPIRED, RESOLVED
    priority = Column(String(10), default="NORMAL")       # LOW, NORMAL, HIGH, CRITICAL

    # The decision context
    trigger_context = Column(JSON)                        # What situation triggered this
    proposed_action = Column(JSON, nullable=False)        # What's being requested
    balanced_scorecard = Column(JSON, nullable=False)     # Full scorecard from originator
    net_benefit = Column(Float)
    justification = Column(Text)
    fallback_action = Column(JSON)                        # What originator does if denied

    # Resolution
    resolution = Column(String(20))                       # AUTHORIZED, DENIED, COUNTER_ACCEPTED,
                                                          # FALLBACK_EXECUTED, HUMAN_RESOLVED
    resolution_details = Column(JSON)
    resolved_by = Column(String(50))                      # Agent type or user ID

    # Timing
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime)
    resolved_at = Column(DateTime)

    # Lineage
    policy_envelope_hash = Column(String(64))             # Which PE was active
    related_artifact_type = Column(String(50))            # supply_commit, allocation_commit, etc.
    related_artifact_id = Column(Integer)

    # Human escalation
    escalated_to_role = Column(String(50))
    escalated_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    human_decision = Column(String(50))
    human_reason = Column(Text)


class AuthorizationMessage(Base):
    """Individual messages within an authorization thread."""
    __tablename__ = "authorization_message"

    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("authorization_thread.id"), nullable=False)

    from_agent = Column(String(50), nullable=False)
    to_agent = Column(String(50), nullable=False)
    message_type = Column(String(20), nullable=False)    # REQUEST, AUTHORIZE, DENY,
                                                          # COUNTER_OFFER, ACCEPT_COUNTER,
                                                          # REJECT_COUNTER, ESCALATE,
                                                          # CONDITION, FULFILL_CONDITION

    # Content
    proposed_action = Column(JSON)                        # For REQUEST and COUNTER_OFFER
    scorecard_delta = Column(JSON)                        # Changes to scorecard (for counters)
    conditions = Column(JSON)                             # For conditional authorization
    reason = Column(Text)

    # Resource check results (target agent's evaluation)
    resource_check = Column(JSON)                         # {"budget": "PASS", "capacity": "PASS"}
    competing_requests = Column(JSON)                     # Other requests for same resource

    created_at = Column(DateTime, nullable=False)
```

### 11.2 Service Layer

```python
class AuthorizationService:
    """Orchestrates cross-authority authorization exchanges."""

    def __init__(self, db: Session, group_id: int):
        self.db = db
        self.group_id = group_id

    async def evaluate_options(
        self,
        agent_type: str,
        decision_context: dict,
        candidate_actions: list[dict]
    ) -> list[dict]:
        """
        Agent evaluates all candidate actions against the balanced scorecard.
        Returns ranked options with scorecard, net benefit, and authority status.

        Every option gets a full scorecard -- including actions outside the
        agent's authority. The agent sees the cross-functional consequences
        before deciding whether to request authorization.
        """
        authority_map = await self._get_authority_map(agent_type)
        results = []

        for action in candidate_actions:
            scorecard = await self._run_what_if(decision_context, action)
            net_benefit = self._compute_net_benefit(scorecard)
            authority = authority_map.get(action["type"], "FORBIDDEN")

            results.append({
                "action": action,
                "scorecard": scorecard,
                "net_benefit": net_benefit,
                "authority": authority,
                "requires_auth_from": (
                    authority_map.get(f"{action['type']}_target")
                    if authority == "REQUIRES_AUTH" else None
                ),
            })

        return sorted(results, key=lambda r: r["net_benefit"], reverse=True)

    async def request_authorization(
        self,
        requesting_agent: str,
        target_agent: str,
        proposed_action: dict,
        balanced_scorecard: dict,
        net_benefit: float,
        justification: str,
        fallback_action: dict = None,
        expires_in_seconds: int = 300,
    ) -> AuthorizationThread:
        """
        Create an authorization request. The originating agent has already
        evaluated the full scorecard and decided this is worth requesting.
        """
        ...

    async def evaluate_authorization(
        self,
        thread_id: int,
        target_agent: str,
    ) -> AuthorizationMessage:
        """
        Target agent evaluates an authorization request.

        Does NOT re-run the what-if. Instead checks:
        1. Resource availability (budget, capacity, inventory)
        2. Competing requests for the same resource
        3. Policy threshold compliance

        Returns AUTHORIZE, COUNTER_OFFER, or DENY.
        """
        ...

    async def resolve_contention(
        self,
        competing_thread_ids: list[int],
        target_agent: str,
    ) -> dict:
        """
        When multiple requests compete for the same resource,
        resolve by comparing net benefits and priorities.

        If resolution is clear (one dominates), authorize the winner
        and counter-offer or deny the others.

        If ambiguous, escalate all to human with ranked options.
        """
        ...

    async def escalate_to_human(
        self,
        thread_id: int,
        reason: str,
        recommended_option: str = None,
    ) -> AuthorizationThread:
        """
        Escalate an unresolved thread to a human reviewer.

        Presents pre-digested options with scorecards.
        Human resolution captured for RL training.
        """
        ...

    async def record_human_resolution(
        self,
        thread_id: int,
        user_id: int,
        decision: str,
        reason_code: str,
        reason_text: str = None,
    ) -> AuthorizationThread:
        """
        Record a human's resolution of an escalated thread.

        Writes to replay buffer for agent learning (is_expert=True).
        Over time, agents learn human resolution patterns and
        reduce escalation frequency.
        """
        ...
```

### 11.3 API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /authority/{group_id}/{agent_type}` | Get authority map for an agent type |
| `PUT /authority/{group_id}/{agent_type}` | Update authority boundaries (admin) |
| `POST /authorization/evaluate` | Agent evaluates candidate actions (returns ranked with scorecards) |
| `POST /authorization/request` | Create an authorization request |
| `GET /authorization/threads/{group_id}` | List authorization threads (filterable by status, agent, priority) |
| `GET /authorization/thread/{thread_id}` | Get full thread with all messages |
| `POST /authorization/thread/{thread_id}/respond` | Target agent responds (authorize/counter/deny) |
| `POST /authorization/thread/{thread_id}/accept-counter` | Originator accepts counter-offer |
| `POST /authorization/thread/{thread_id}/escalate` | Escalate to human |
| `POST /authorization/thread/{thread_id}/resolve` | Human resolves escalated thread |
| `GET /authorization/metrics/{group_id}` | Authorization metrics (resolution rate, escalation rate, avg time) |

### 11.4 Frontend Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `AuthorizationInbox.jsx` | `/planning/authorizations` | Worklist of pending authorization requests (for human review) |
| `AuthorizationThread.jsx` | Thread detail view | Full exchange history with scorecards at each step |
| `ScorecardComparison.jsx` | Shared component | Side-by-side balanced scorecard for original vs. counter-offer |
| `EscalationPanel.jsx` | Within any worklist page | Shows pre-digested options when a thread is escalated |
| `AuthorizationMetrics.jsx` | Dashboard widget | Resolution rate, avg time, escalation frequency by agent pair |
| `AuthorityConfig.jsx` | Admin page | Configure authority boundaries, thresholds, escalation roles |

---

## 12. Metrics and Learning

### 12.1 AAP-Specific Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Autonomous Resolution Rate** | % of threads resolved without human escalation | >90% (mature system) |
| **Avg Resolution Time** | Time from request to resolution | <30s (execution), <1h (operational), <4h (tactical) |
| **Escalation Rate** | % of threads escalated to humans | <10% (declining over time) |
| **Counter-Offer Acceptance Rate** | % of counter-offers accepted by originator | >70% (indicates good counter-offers) |
| **Fallback Rate** | % where originator reverts to unilateral fallback | <15% (cross-authority options should usually win) |
| **Human Agreement Rate** | % of human resolutions that match agent recommendation | >80% (indicates good recommendations) |
| **Authorization Performance Score** | Did the authorized action produce the projected net benefit? | Positive and increasing |

### 12.2 Learning Loop

```
Agent requests authorization
    -> Target agent resolves (or escalates)
    -> Action executes
    -> Feed-back signal measures actual outcome
    -> Compare actual vs. projected balanced scorecard
    -> Delta written to replay buffer
    -> Agent updates:
       - Net benefit estimation accuracy
       - Counter-offer generation quality
       - Escalation threshold calibration
       - Resource availability prediction
```

Over time:
- Agents learn to make more accurate net benefit estimates (fewer surprises)
- Target agents learn which requests to auto-authorize (fewer delays)
- Originating agents learn which counter-offers to expect (better initial proposals)
- Escalation frequency drops as agents internalize human resolution patterns

### 12.3 The Compounding Loop

This connects directly to Autonomy's core strategy (AI-as-Labor compounding loop):

```
More authorization threads resolved autonomously
    -> Better agent models (from outcome data)
    -> Fewer escalations to humans
    -> Humans focus on genuinely novel situations
    -> Human decisions on novel situations train agents
    -> Agents handle previously-novel situations autonomously
    -> More authorization threads resolved autonomously
```

The judgment layer -- the patterns humans use to resolve ambiguous situations -- becomes the moat. Every human resolution teaches the agents something new.

---

## 13. Comparison to Alternatives

### 13.1 vs. Kinaxis Scenario Comparison

| Aspect | Kinaxis | AAP |
|--------|---------|-----|
| Who creates scenarios | Human planner | Agent (automatically, triggered by feed-back signals) |
| Who evaluates | Human planner + stakeholders | Agent (balanced scorecard) + target agent (resource check) |
| Time to evaluate | Minutes to hours (human review) | Milliseconds (what-if engine) |
| Forum/discussion | Human meeting or async review | Agent-to-agent authorization protocol |
| Net benefit threshold | Implicit (human judgment) | Explicit (configurable per decision type and level) |
| Escalation | All decisions require human approval | Only unresolvable contention reaches humans |
| Learning | None (human memory) | Explicit RL training from outcomes |

**The AAP is the Kinaxis workflow at machine speed.** Agents do what planners do: evaluate alternatives, assess cross-functional impact, propose to stakeholders, negotiate when needed. But continuously, in seconds, with full auditability.

### 13.2 vs. Mathematical Multi-Objective Optimization

| Aspect | MILP/Pareto | AAP |
|--------|-------------|-----|
| Handles preferences | Fixed weights | Dynamic (Policy Envelope, adjustable) |
| Handles authority | No concept | First-class citizen |
| Handles contention | Not applicable | Resource arbitration with escalation |
| Handles institutional knowledge | Cannot | Learns from human escalation patterns |
| Explainable | Dual prices, shadow costs | Full balanced scorecard + agent justification |
| Adaptable | Re-solve from scratch | Continuous, incremental |

Multi-objective optimization finds Pareto-optimal solutions. The AAP navigates *among* those solutions using business judgment, institutional knowledge, and authority boundaries. They're complementary, not competing.

### 13.3 vs. Visser's Moltbook Agent Interaction

Visser describes agents on Moltbook forming emergent subcommunities, debating, building reputation. The Board-as-Substrate architecture (Section 10) enables these patterns natively. The AAP borrows three patterns:

1. **Reputation**: Agents build track records. A Logistics Agent that consistently provides good counter-offers (accepted 85% of the time) is "trusted" -- its counter-offers get auto-accepted more readily.

2. **Precedent**: Resolution patterns are stored and matched. "Last 12 times an SO agent requested an expedite <$3K for a strategic customer, the Logistics Agent authorized. Auto-authorize this class."

3. **Coalition**: Multi-party authorizations form temporary coalitions (SO + Supply + Inventory coordinating to fulfill a strategic order). Successful coalitions are remembered and re-formed when similar situations arise.

### 13.4 vs. CPFR Exception Management

CPFR (Collaborative Planning, Forecasting, and Replenishment) is the closest existing industry standard to the AAP. CPFR's VICS 9-step model (Strategy & Planning -> Demand & Supply Management -> Execution -> Analysis) includes structured exception management between trading partners. The AAP generalizes CPFR from a human-paced inter-company process to a machine-speed intra-enterprise agent protocol.

| Aspect | CPFR | AAP |
|--------|------|-----|
| Participants | Trading partner companies (Walmart + P&G) | Autonomous agents within one enterprise |
| Exception criteria | Pre-agreed thresholds in collaboration arrangement | `AgentAuthority` table with configurable thresholds per decision type |
| Exception detection | Compare forecast vs. actuals against criteria | Feed-back signals trigger authorization requests when metrics breach thresholds |
| Resolution process | Human collaboration via shared data, email, phone, meetings | Agent-to-agent authorization protocol (milliseconds) |
| Escalation | "Heighten the collaboration" (more senior people) | Route to human with pre-digested options and ranked alternatives |
| Outcome tracking | Promotion scorecarding | Balanced scorecard comparison: projected vs. actual |
| Learning | Manual continuous improvement loop | Automated: human resolutions train agent models, escalation rate declines |
| Speed | Days to weeks (human coordination cadence) | Seconds to minutes (machine speed) |
| Proven results | P&G/Walmart: 70% inventory reduction, 96%->99% service levels | Target: similar magnitude improvement at 1000x speed |

**Key CPFR insight adopted by AAP**: Pre-agreed exception criteria (see Section 5.8.2) allow most interactions to be handled automatically, with only genuine exceptions requiring collaborative resolution. The AAP's `net_benefit_threshold` and `auto_authorize_threshold` are the agent equivalent of CPFR's exception bounds.

### 13.5 vs. Multi-Agent Production Routing (AAMAS 2024)

Recent academic work (2024) on multi-agent negotiation for the Production Routing Problem demonstrates agent-based negotiation where a supplier agent proposes delivery schedule changes and retailer agents accept or reject based on their local utility calculations. The AAP shares the same pattern (originating agent proposes, affected agents evaluate against their own constraints) but extends it with:

- Balanced scorecard evaluation instead of single-dimension cost utility
- Authority boundaries as a first-class concept
- Escalation to humans when agents can't resolve
- Continuous learning from outcomes

### 13.6 vs. Agentic LLM Consensus-Seeking (2025)

The Taylor & Francis paper "Agentic LLMs in the Supply Chain: Towards Autonomous Multi-Agent Consensus-Seeking" (2025) introduces LLM agents that reduce bullwhip effects through negotiation around shared information. The AAP differs in that:

- AAP agents use structured protocols (not free-text LLM conversation) for the core authorization exchange, ensuring deterministic auditability
- LLM capabilities are available via the Chat Adapter (Section 10.2) for human interaction, not for agent-to-agent authorization
- AAP's balanced scorecard provides a shared quantitative basis rather than relying on emergent LLM consensus

---

## 14. Implementation Roadmap

### Phase 1: Foundation
- `AgentAuthority` model and admin configuration
- `AuthorizationThread` and `AuthorizationMessage` models
- Basic `AuthorizationService` with request/authorize/deny
- Migration script
- API endpoints for CRUD operations

### Phase 2: Execution-Level Integration
- Wire AAP into TRM worklist (SO Agent can request expedite from existing agents)
- Balanced scorecard computation for TRM-level decisions
- Counter-offer support
- Escalation to TRM analyst human role

### Phase 3: Operational-Level Integration
- Wire AAP into Supply Commit and Allocation Commit workflows
- Supply Agent <-> Logistics Agent authorization surface
- Allocation Agent <-> Inventory Agent authorization surface
- Escalation to MPS Manager

### Phase 4: Strategic-Level Consensus Board
- Functional agent personas (Demand, Supply, Finance, Service, Procurement, Risk)
- Continuous Policy Envelope negotiation via feed-back signals
- S&OP consensus dashboard (shows active threads, resolution history, parameter drift)
- Escalation to SC VP / S&OP Director

### Phase 5: Learning and Autonomy
- Outcome tracking (actual vs. projected scorecard)
- Auto-authorization rules derived from human resolution patterns
- Threshold calibration from escalation data
- Reputation and precedent matching
- Declining escalation rate monitoring

---

## Appendix A: Full SO Agent Example (Revised)

**Situation**: Strategic customer order #8834, 500 cases Product X, promised delivery Feb 12.

**Step 1: SO Agent evaluates all options**

The SO agent runs what-if on three options. The balanced scorecard is fully visible for all three, including actions outside its authority:

| | Option A: Reallocate | Option B: Expedite Delivery | Option C: Ship from DC |
|---|---|---|---|
| **Authority** | UNILATERAL | LOGISTICS | INVENTORY |
| **Customer: Strategic OTIF** | 99.2% (GREEN) | 99.2% (GREEN) | 99.2% (GREEN) |
| **Customer: Standard OTIF** | 94.1% (AMBER) | 97.1% (GREEN) | 97.1% (GREEN) |
| **Financial: Cost** | $0 | $2,400 (AMBER) | $0 |
| **Financial: Inventory** | Neutral | Neutral | -$8,500 (AMBER) |
| **Operational: Fill Rate** | 96% (GREEN) | 100% (GREEN) | 100% (GREEN) |
| **Operational: Safety Stock** | Neutral | Neutral | 60% (RED) |
| **Strategic: Revenue Risk** | $0 | $0 | $0 |
| **Net Benefit** | +$12,000 | +$15,600 | +$8,200 |

**Step 2: SO Agent decision**

Option B has the highest net benefit. The SO agent *sees* the $2,400 cost (AMBER) and the 78% budget utilization. It judges that 6 GREEN + 2 AMBER with +$15,600 net benefit justifies requesting authorization.

Option C has a RED flag (safety stock at 60%) which would likely be denied. The SO agent deprioritizes it.

**Step 3: SO Agent sends AuthorizationRequest to Logistics Agent**

The request includes the full scorecard, net benefit, justification ("strategic customer, 6.5x cost-to-benefit"), and fallback (Option A, which it can execute unilaterally).

**Step 4: Logistics Agent checks resources**

Budget: $4,800 remaining of $8,000. $2,400 fits. No competing requests. Carrier slot available.

**AUTHORIZE.**

**Step 5: Execution**

SO Agent holds allocation, Logistics Agent books carrier. Order 8834 ships Wednesday, delivers Thursday. No standard customer was delayed. $2,400 spent. Strategic OTIF maintained.

**Step 6: Outcome tracking**

Feed-back signal confirms: order delivered on-time, actual cost $2,380 (within 1% of projection), strategic customer retained. Authorization Performance Score: positive. Projected scorecard matched actual within confidence bands.

---

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **AAP** | Agentic Authorization Protocol -- the framework described in this document |
| **Authorization Surface** | The boundary between two agents' authority domains where the protocol activates |
| **Balanced Scorecard** | Four-quadrant evaluation (Financial, Customer, Operational, Strategic) with GREEN/AMBER/RED status |
| **Net Benefit** | Weighted sum of scorecard metric deltas; the single number summarizing the value of a proposed action |
| **Net Benefit Threshold** | Minimum net benefit required for an authorization request to proceed |
| **Unilateral Authority** | Actions an agent can execute without authorization from any other agent |
| **Counter-Offer** | Modified version of a proposed action that the target agent can fulfill (different cost, timing, etc.) |
| **Escalation** | Routing an unresolved thread to a human reviewer with pre-digested options |
| **Resource Contention** | When multiple authorization requests compete for the same constrained resource |
| **Fallback Action** | The originating agent's best unilateral option if authorization is denied |
| **Authorization Performance Score** | Performance score specific to authorization outcomes -- did the authorized action produce the projected benefit? |
| **Board Service** | The shared data layer (AuthorizationThread/Message tables) that functions as a Moltbook-style coordination substrate |
| **CPFR** | Collaborative Planning, Forecasting, and Replenishment -- VICS standard for multi-party exception management between trading partners |
| **Supply Chain Triangle** | Oliver Wyman framework: Service, Cost, and Working Capital as inherently conflicting objectives |
| **Channel Agent** | Agent representing a specific sales channel (Retail, Foodservice, E-Commerce, Private Label) |
| **Plant Agent** | Agent controlling production scheduling, sequencing, and capacity at a manufacturing site |
| **Quality Agent** | Agent controlling material holds, inspections, dispositions, and supplier qualification |
| **Maintenance Agent** | Agent controlling preventive and corrective maintenance scheduling |
| **Precedent** | Historical resolution pattern stored for matching similar future situations |
| **Coalition** | Temporary multi-agent group formed to coordinate multi-party authorizations |

---

## Appendix C: Research References

| Source | Key Contribution to AAP Design |
|--------|-------------------------------|
| **Visser, J. (2026)** "The Agentic Inversion: What Moltbook and Axie Infinity Reveal About the Future of Velocity." Macro-AI-Crypto Substack. | Core thesis: autonomous agents sustain continuous economic activity at machine speed. Moltbook as coordination substrate. DeepSeek as zero-cost inference. |
| **VICS CPFR Guidelines (1998, updated)** Voluntary Interindustry Commerce Solutions. 9-step model for collaborative planning. | Exception management framework with pre-agreed criteria, structured resolution, and escalation. Direct precedent for AAP's threshold-based governance. |
| **Oliva, R. & Watson, N. (2009)** "Cross-Functional Alignment in Supply Chain Planning." Harvard Business School Working Paper 07-001. | Documents how S&OP cross-functional conflicts arise from departmental specialization. AAP automates the resolution of these conflicts. |
| **Production Routing with Privacy Preserving (AAMAS 2024)** Multi-agent negotiation with removal/insertion/substitution transactions. | Demonstrates practical agent negotiation where affected parties vote on proposed changes based on local utility. Matches AAP's counter-offer pattern. |
| **Agentic LLMs in Supply Chain (2025)** Taylor & Francis, International Journal of Production Research. | LLM agents reducing bullwhip through consensus-seeking. Validates NL-capable agent interaction but AAP prefers structured protocol for auditability. |
| **Oliver Wyman (2018)** "The Supply Chain Triangle." | Formalizes Service/Cost/Working Capital tradeoffs. AAP's balanced scorecard captures all three dimensions. |
| **Powell, W.B. (2022)** Sequential Decision Analytics and Modeling. | Unified framework for sequential decision-making under uncertainty. Four policy classes (PFA, CFA, VFA, DLA) provide the foundation for agent decision architecture. |
| **Kinaxis Concurrent Planning** kinaxis.com/en/sop | Cross-functional scenario comparison with stakeholder review. AAP automates this workflow at machine speed. |
| **P&G/Walmart CPFR Case (2000s)** | 70% inventory reduction, 96%->99% service levels through collaborative exception management. Validates the AAP's exception-first approach. |
| **TSMC Semiconductor Allocation (2021-2022)** | Real-world multi-party allocation under extreme constraint. Apple priority, automotive pressure, government intervention. Demonstrates the complexity AAP must handle. |
| **Fujitsu/Rohto Pharmaceutical (2026)** Field trials for multi-agent supply chain optimization with privacy preservation. | Validates commercial viability of agent-based negotiation in manufacturing supply chains. |

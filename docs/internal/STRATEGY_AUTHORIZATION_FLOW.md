# Cross-Boundary Decision Resolution — How Autonomy Agents Negotiate at Machine Speed

## The Problem

In enterprise supply chains, no single person or system controls everything. A demand planner can't unilaterally increase production — that's the plant manager's domain. A procurement analyst can't redirect logistics — that's the logistics team's domain. Every meaningful supply chain response crosses multiple authority boundaries.

Traditional systems handle this with emails, meetings, and phone calls. A demand spike triggers a week of cross-functional coordination before anyone acts. By then, the opportunity (or the crisis) has moved on.

Autonomy solves this with **Agent-to-Agent (A2A) authorization** — autonomous agents negotiate cross-boundary decisions in seconds, with full transparency and human override.

## A Real Example: The Bigmart Rush Order

A demand planner types into Talk to Me:

> "Bigmart just called — they need 500 C900 bikes delivered to Detroit in 2 weeks. This is a new fleet deal we can't lose."

Here's what happens in the next 15 seconds:

### Step 1: Compound Intent Detection (< 1 second)

The system recognizes this as **both a demand signal** (a new customer order) **and an implicit directive** (do whatever it takes to fulfill it). It creates the order and checks feasibility.

**Result**: Current plan can only promise 320 of 500 units. Shortfall: 180 units.

### Step 2: Strategy Generation (3-5 seconds)

Claude Skills (the AI strategist) generates three candidate resolution strategies:

| Strategy | Primary Lever | Estimated Fill Rate |
|----------|--------------|-------------------|
| **A: Reprioritize ATP** | Steal allocation from lower-priority orders | 92% |
| **B: Increase Production** | Rush MO at Plant 1 US for 80 additional units | 95% |
| **C: Reprioritize + Expedite** | Raise priority AND expedite component POs | 100% |

### Step 3: Auto-Selection (< 1 second)

Strategy C wins on net benefit (highest fill rate, acceptable cost trade-off). The system selects it and records the full comparison in the Decision Stream.

### Step 4: Authority Boundary Check (< 1 second)

Strategy C has three actions. The demand planner's authority is checked for each:

| Action | Domain Owner | Demand Planner Authority? |
|--------|-------------|--------------------------|
| Raise order priority to P1 | **SO/ATP Agent** | **Unilateral** — execute immediately |
| Add 80-unit MO at Plant 1 US | **Plant Agent** | **Cross-boundary** — needs authorization |
| Expedite Frame-900 PO to 3-day delivery | **Procurement Agent** | **Cross-boundary** — needs authorization |

**Result**: Priority change executes instantly. Production increase and PO expedite require A2A authorization.

### Step 5: A2A Negotiation (2-4 seconds)

The cross-boundary actions are sent to the target domain's TRM agents for evaluation. Each agent uses its trained model plus current domain state to decide.

#### Plant Agent (MO Execution TRM) evaluates production increase:

```
Request: Add 80 units of C900 BIKE at Plant 1 US
Current state: Plant capacity at 78% utilization, 22% spare
TRM evaluation: Sufficient headroom for 80 additional units
Decision: AUTHORIZE
Reason: "Plant capacity at 78% — 22% spare capacity sufficient for 80 units."
```

#### Procurement Agent (PO Creation TRM) evaluates PO expedite:

```
Request: Expedite Frame-900 PO to 3-day delivery
Current state: 4 active expedites (threshold: 5)
TRM evaluation: Below expedite threshold, supplier can accommodate
Decision: COUNTER_OFFER
Reason: "4 active expedites — can offer 5-day delivery instead of 3-day."
Counter-proposal: { new_lead_time_days: 5 }
```

### Step 6: Execution (< 1 second)

- **Priority raised**: OutboundOrder updated to P1 — ATP re-consumption makes 320 units available immediately
- **Production order created**: MO-STRAT-20260319 for 80 units of C900 at Plant 1 US — authorized by Plant agent
- **PO expedited**: Frame-900 delivery moved to 5-day (tweaked from 3-day by Procurement agent) — counter-offer accepted

### Step 7: Decision Stream (Informed)

The entire decision — all three strategies evaluated, the winner selected, the A2A conversation, the counter-offer from Procurement — is recorded as a single decision in the Decision Stream. Any stakeholder can:

- **Inspect**: See the comparison table, the A2A conversation, the authority boundaries that were crossed
- **Override**: Select a different strategy, or reject the production increase, with a reason captured for the learning flywheel

### Total Time: ~15 seconds

What would take 3-5 days of cross-functional meetings in a traditional planning system happens in 15 seconds with full transparency, audit trail, and human override capability.

---

## The AIIO Decision Model

Every decision in Autonomy follows the **AIIO model**:

| Status | What Happens | Who Acts |
|--------|-------------|---------|
| **Actioned** | System auto-selects the best strategy and executes within-authority actions | AI agents |
| **Informed** | Decision recorded to Decision Stream with full reasoning, comparison, and A2A conversation | Stakeholders notified |
| **Inspected** | User reviews the comparison table, authority boundaries crossed, agent reasoning | Human planner |
| **Overridden** | User selects a different strategy or rejects an action, with reason captured | Human planner |

The override reason feeds back into the Bayesian effectiveness tracking system, teaching the agents which human overrides improve outcomes vs which don't.

---

## Authority Boundaries

Each agent has three categories of actions:

| Category | Description | Example |
|----------|------------|---------|
| **Unilateral** | Can execute without asking anyone | ATP analyst raises order priority |
| **Requires Authorization** | Must get approval from the domain owner | Demand planner requests production increase |
| **Forbidden** | Cannot request under any circumstances | Analyst overrides S&OP policy parameters |

15 agent roles are defined across the supply chain: SO/ATP, Supply, Allocation, Logistics, Inventory, Plant, Quality, Maintenance, Procurement, Supplier, Channel, Demand, Finance, Service, Risk.

The authority boundary map is exhaustive — every action type is mapped to exactly one domain owner. Unknown actions default to requires-authorization (pessimistic safety).

---

## A2A Authorization Responses

When an agent receives an authorization request, it evaluates using its trained TRM model and current domain state:

| Response | Meaning | What Happens |
|----------|---------|-------------|
| **AUTHORIZE** | Feasible, no contention | Action executed as-is |
| **COUNTER_OFFER** | Feasible with modifications | Modified action executed (e.g., 60 units instead of 80) |
| **DENY** | Infeasible or constraint violation | Action skipped, reason recorded |
| **ESCALATE** | Agent uncertain | Pushed to Decision Stream for human review |

Counter-offers are the most common outcome — agents rarely say "no" outright. Instead they negotiate: "I can't do 80 units at standard cost, but I can do 60 without overtime." This mirrors how real cross-functional teams work, but at machine speed.

---

## Scenario Lifecycle

Strategies are evaluated as ephemeral in-memory scenarios — no persistent database branches. The decision record is the permanent audit trail.

However, when a strategy requires cross-boundary authorization, the winning scenario is **temporarily persisted** while the A2A negotiation happens. Once all authorization threads resolve (actions approved, counter-offered, or denied), the scenario is:

1. **Promoted**: Approved/tweaked actions applied to the active config
2. **Cleaned up**: Scenario row deleted — the audit trail lives in the decision record and authorization thread records
3. **Never lingers**: No stale scenario branches accumulate in the database

---

## Technical Architecture

```
Talk to Me prompt
    ↓
Compound parsing (demand signal + directive)
    ↓
Strategy generation (Claude Skills, Sonnet)
    ↓
Strategy evaluation (ephemeral, in-memory, lightweight BSC)
    ↓
Auto-selection (highest net_benefit)
    ↓
Authority boundary check (partition: unilateral vs cross-boundary)
    ├── Unilateral → execute immediately
    └── Cross-boundary → persist scenario → fire AAP requests
            ↓
        Target TRM agents evaluate
            ├── AUTHORIZE → execute
            ├── COUNTER_OFFER → execute tweaked
            ├── DENY → skip
            └── ESCALATE → Decision Stream
            ↓
        All threads resolved → promote → cleanup
    ↓
Decision Stream: full reasoning + comparison + A2A conversation
    ↓
Human can Inspect or Override
```

### Key Services

| Service | Role |
|---------|------|
| `ScenarioStrategyService` | Orchestrates the full flow: event → baseline → strategies → evaluate → compare → execute |
| `StrategyAuthorityMapping` | Maps user roles → agent roles, action types → domain owners, partitions actions |
| `A2AAuthorizationResponder` | Routes authorization requests to target TRM agents for evaluation |
| `ScenarioEventService` | Creates orders, modifies DB records, triggers CDC |
| `DecisionStreamService` | Surfaces decisions for human review and override |

### Data Flow

All communication happens via Server-Sent Events (SSE) for real-time progressive feedback. The Talk to Me popup shows each step as it completes — strategy generation, evaluation progress, comparison table, authority check, A2A conversation, and execution results.

---

## Why This Matters

1. **Speed**: 15 seconds vs 3-5 days of meetings
2. **Transparency**: Every decision is recorded with full reasoning and alternatives considered
3. **Governance**: Authority boundaries are explicit and enforced — no agent can exceed its scope
4. **Learning**: Overrides feed back into agent training, making future decisions better
5. **Human control**: The system acts first (speed), but humans always have the final say (governance)

This is the **agentic operating model** — agents own decisions by default, humans override with reasoning captured. The more decisions flow through the system, the better the agents become, and the less human effort is required for routine decisions. The judgment layer — knowing when to override and why — becomes the organization's competitive advantage.

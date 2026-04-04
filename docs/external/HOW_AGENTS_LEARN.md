# How Autonomy Agents Learn and Improve

> **Audience**: Business leaders, supply chain executives, customer success, sales.
> Plain-language explanation of the agent learning lifecycle. No prior AI knowledge assumed.

---

## The Short Answer

Autonomy agents learn in three stages: **study** (before go-live), **on the job** (during
normal operations), and **continuous improvement** (autonomously, forever). Unlike other
AI platforms that train each layer of agents in isolation on synthetic data, Autonomy uses
a **unified training corpus** built directly from your ERP data. Every decision that every
agent learns from is anchored on your real supply chain, not a generic template.

---

## Stage 1: Study (Before Go-Live)

Before an agent makes a single live decision, it studies your supply chain.

This works the same way a skilled contractor learns your business before starting work.
You give them access to your current operating plan, your suppliers, your lead times,
your inventory policies, and your cost structure. The agent reads all of it and builds a
working model of how your supply chain behaves — specifically, how *your* supply chain
behaves, not a generic one.

### The Foundation: Your ERP's Current Plan

The starting point for all learning is **the plan your ERP is running right now**. At the
moment of provisioning, we extract:

- Every open purchase order, manufacturing order, and transfer order
- Current inventory positions at every site
- Safety stock targets, reorder points, and sourcing rules
- The forecast your business is currently operating against

This is your operating reality — what works today, what your planners have tuned over
years, what your cost structure and supplier relationships have produced. The agents
treat this as the **anchor**: the known-good reference point.

### Learning from Variations

Of course, the ERP plan reflects one version of reality — today's demand, today's lead
times, today's costs. Tomorrow's will be different. To prepare the agents for the full
range of conditions they will face, we generate **hundreds of perturbed scenarios** around
that anchor:

- Demand shifts by +/-15% (spikes and drops)
- Lead times extend by +/-20% (supplier disruptions and improvements)
- Unit costs shift by +/-10% (commodity price changes)
- Capacity tightens by up to 20% (equipment issues, labor shortages)
- Demand variability doubles or halves (stable vs volatile markets)

For each perturbed scenario, we run a full simulation of your supply chain with the
agents actively making decisions. Every decision they make — thousands per scenario —
becomes a training sample.

### One Corpus, Four Agent Layers

This is where Autonomy differs from other platforms. Every agent — from the role-level
agents making hourly decisions, through the site-level agents coordinating within a
factory, through the tactical agents running daily network plans, up to the strategic
agents setting weekly policy — **all train on the same corpus**.

The samples are aggregated upward:

```
Role agents (PO creation, ATP, rebalancing, etc.)
    Train on:  individual decisions from simulated scenarios
         |
         v  aggregated by site x time window
Site agents (cross-role coordination within a factory)
    Train on:  patterns of how role agents work together
         |
         v  aggregated by domain x planning period
Tactical agents (network-wide supply, inventory, capacity)
    Train on:  how sites perform across the network
         |
         v  aggregated to network-wide policy outcomes
Strategic agents (S&OP policy parameters)
    Train on:  which policy settings produce the best results
```

The strategic agent does not train on synthetic generic supply chain networks. It trains
on **your network**, under perturbations of your baseline, where the "optimal" policy
parameters are inferred from the actual decisions that produced the best outcomes in
simulation. This gives every layer a consistent view of reality, grounded in your data.

### Why Volume Matters

Research has shown that the *volume* of scenarios an AI studies matters more than the
complexity of its architecture (Stöckl, RANLP 2021 — studying how AI learns chess by
watching expert games). A small, efficient model that has observed hundreds of thousands
of expert decisions will outperform a much larger model that has only seen a few thousand.

Each Autonomy agent studies **at least 450,000 decisions** during warm-start. These are
not random synthetic scenarios — they are aggregated from the perturbations of your ERP
baseline, so the agents are learning the behavior of *your* supply chain under realistic
stress conditions, not a generic textbook example.

### What Warm-Start Produces

At the end of Stage 1, every agent has:

- A working mental model of your supply chain topology, cost structure, and demand patterns
- Learned behavior that replicates or exceeds what your current ERP plan produces
- Calibrated uncertainty estimates — the agent knows when it is confident and when it is not
- Consistent alignment across layers — the strategic agents and the role agents agree on
  what "good" looks like, because they trained on the same corpus

The agent is not perfect at this point, but it is competent from day one and specifically
tuned to your supply chain.

---

## Stage 2: On the Job (After Go-Live)

Once agents are live and making decisions, each decision becomes a data point for
improvement.

The agent makes a recommendation (say, create a purchase order for 500 units with delivery
in 3 weeks). The planner reviews it — accepts, adjusts, or overrides. Some time later
(hours for order promises, days for purchase orders, weeks for inventory buffer
adjustments), the actual outcome is measured: did the order arrive on time? Did it
prevent a stockout? Was inventory held too long? Did the service level improve?

The agent receives a *reward signal* — a score based on the actual business outcome (cost
reduction, service level, inventory efficiency) rather than just whether it matched what
a human would have done. Over time, the agent discovers that some decision patterns
consistently earn better outcomes than the warm-start baseline. These patterns are
reinforced. Patterns that earn poor outcomes are weakened.

### Real Outcomes Feed the Same Corpus

Here is the second key difference from other platforms: **real outcomes feed the same
unified corpus that the warm-start used**. The training pipeline does not switch from
"warm-start mode" to "live mode" and throw the warm-start data away. Instead, every new
real decision with its measured outcome is added to the corpus, and retraining uses both:
the original perturbation scenarios *and* the growing pool of real outcomes.

This means:
- Early on, the corpus is 95% warm-start perturbations and 5% real outcomes — agents
  behave close to the warm-start baseline
- After a few months, the corpus is 50% perturbations and 50% real outcomes — agents
  have adapted to your actual operational patterns
- After a year, real outcomes dominate — agents have learned behaviors that work
  specifically in your environment, and the synthetic perturbations serve as regularization
  to prevent overfitting to any particular period

The layered aggregation still applies: when retraining happens, real outcomes flow upward
the same way warm-start samples did. A purchase order decision does not just retrain the
purchasing agent — it contributes data points for the site agent, the tactical supply
agent, and the strategic S&OP agent. One real decision teaches four layers.

### Business Implications

- Agent performance improves continuously over the first 3-6 months of operation.
- The more decisions the agent handles, the faster it improves.
- Planner overrides are not wasted — they are studied. If an override consistently leads
  to better outcomes than the agent's recommendation, that override pattern is incorporated
  into the agent's future behavior.
- Agents become *specific to your supply chain*. After 6 months, your agents have learned
  patterns that are unique to your suppliers, your demand variability, your production
  constraints. A competitor could not simply copy them.
- All four layers of agents stay consistent. You never have a situation where the
  strategic agent wants one thing and the role agents do another, because they share the
  same training data.

---

## Stage 3: Continuous Improvement (Ongoing, Autonomous)

Once the on-the-job learning loop is established, the system monitors itself and
retrains automatically when it detects that agent performance is drifting.

Drift happens naturally — suppliers change lead times, demand patterns shift seasonally,
new products are introduced. An agent trained on last year's data will gradually become
less accurate as the supply chain evolves. Without continuous retraining, you would need
a data science team to periodically retrain models by hand. Autonomy does this
autonomously.

The system:

1. **Collects outcomes** every hour — comparing what the agent predicted would happen
   against what actually happened. These outcomes are added to the unified training corpus.
2. **Detects drift** when the gap between predictions and outcomes exceeds a threshold —
   for example, if order promise fill rates drop more than expected, or if purchase order
   quantities are consistently too high or too low.
3. **Retrains automatically** every 6 hours when drift thresholds are exceeded and
   enough new data has accumulated (typically 100+ new decision-outcome pairs). Retraining
   uses the full corpus: old perturbations, old real outcomes, and new real outcomes.
4. **Retrains all four layers together** when needed. If the drift is severe enough to
   shift what "optimal" looks like at a policy level, the new outcomes propagate up through
   the aggregation layers and the strategic agents retrain as well. The layers stay in sync.
5. **Guards against regression** — new model versions are only deployed if they perform
   at least as well as the current version on a held-out validation set. Bad retraining
   runs are discarded automatically.
6. **Escalates when needed** — if drift is too severe for execution-level retraining to
   fix (for example, a fundamental shift in demand seasonality), the system escalates to
   the tactical or strategic planning agents to re-optimize policy parameters, and the
   entire stack relearns together.

From a business perspective, this means the platform requires no ongoing data science
maintenance. Agents adapt to your evolving supply chain automatically, and they get
better over time rather than decaying.

---

## Why the Unified Corpus Matters

Other AI supply chain platforms train each layer of agents independently:

- The strategic agent is trained on generic synthetic networks from an optimization library
- The tactical agent is trained on a different synthetic dataset from an LP solver
- The role agents are trained on yet another synthetic dataset from a simulator
- The layers are then stitched together at inference time and hope to work consistently

This has three problems. First, none of the layers are specific to your supply chain —
they all started from generic templates. Second, the layers can disagree with each other
because they learned different views of what "optimal" means. Third, when real outcomes
arrive after go-live, there is no way to push them upward to the strategic layer, so the
strategic agent never learns from your real operations.

Autonomy's unified corpus solves all three:

| Problem | Autonomy's Approach |
|---------|-------------------|
| Layers are generic | All layers start from your ERP baseline |
| Layers disagree | All layers share the same training corpus |
| Real outcomes don't propagate up | Aggregation flows from role agents up to strategic |

The result is agents that are coherent across layers, specific to your supply chain, and
continuously improving as a unified system rather than as disconnected pieces.

---

## The Compounding Advantage

Each stage builds on the previous one:

```
Study phase     ->  agents are grounded in your ERP baseline
On the job      ->  real outcomes flow up through all four layers
Continuous      ->  all layers stay in sync and current automatically
                    + captures planner expertise as overrides
                    + gets increasingly specific to your supply chain
```

The longer the system runs, the harder this advantage is to replicate. A competitor
deploying the same platform would start at Stage 1 with your ERP's plan of today. Your
agents would already be at Stage 3, trained on years of your specific operating outcomes
and your planners' expertise. This is what makes the learning flywheel a durable
competitive advantage, not just a one-time efficiency gain.

---

## What Planners Experience

From a planner's perspective, the agent learning is largely invisible. Agents simply
get better at recommendations over time. What changes is:

- **Fewer overrides needed** — agents stop making the mistakes they made early on.
- **Better timing** — purchase order recommendations align more closely with actual
  lead time patterns for your specific suppliers.
- **Lower exception volume** — agents handle more decisions autonomously as confidence
  increases, so the worklist shrinks over time.
- **Override reasons are captured** — when planners do override, they select a reason.
  This teaches the agent *when* to defer to human judgment — for example, learning
  that demand signals from a particular sales region always warrant manual review.
- **Strategic recommendations reflect operational reality** — because the strategic
  agent trains on the same corpus as the role agents, S&OP recommendations never feel
  disconnected from what actually happens on the ground.

---

## Summary Table

| Stage | Timing | What Happens | Business Outcome |
|-------|--------|--------------|-----------------|
| **Warm-Start** | Before go-live (1-3 days) | ERP baseline extracted; perturbations generated; all four agent layers trained on the unified corpus | Agents start competent, specific to your supply chain, consistent across layers |
| **On the Job** | First 3-6 months | Real outcomes accumulate in the corpus; agents retrain as new data arrives | Agents exceed baseline; strategic, tactical, site, and role layers stay aligned |
| **Continuous** | Ongoing, autonomous | Drift detection triggers retraining across all layers simultaneously | Performance stays current; no data science team required; layers never drift apart |

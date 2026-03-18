# How Autonomy Agents Learn and Improve

> **Audience**: Business leaders, supply chain executives, customer success, sales.
> Plain-language explanation of the agent learning lifecycle. No prior AI knowledge assumed.

---

## The Short Answer

Autonomy agents learn in three stages: **study** (before go-live), **on the job** (during
normal operations), and **continuous improvement** (autonomously, forever). Each stage
makes the agents progressively better, and the whole process runs without any data science
intervention once it is set up.

---

## Stage 1: Study (Before Go-Live)

Before an agent makes a single live decision, it studies your supply chain history.

This works the same way a skilled contractor learns your business before starting work.
You give them access to two years of records — past orders, demand patterns, supplier
lead times, inventory levels, what decisions were made and what happened as a result.
The agent reads all of it and builds a working model of how your supply chain behaves.

In practice, this means:

- **Your historical demand data** is used to generate a representative sample of
  supply chain scenarios — what demand looked like, how inventory moved, when shortages
  and excesses occurred.
- **Agent roles are assigned**: each agent (demand planning, supply planning, inventory
  optimization, purchase order creation, manufacturing scheduling, etc.) studies the
  decisions that expert planners made in those scenarios, and learns to reproduce them.
- **The result is a trained agent** that can handle routine decisions from day one —
  not perfectly, but competently, at a level comparable to an experienced planner.

This stage is called **warm-start** because it produces a starting point that is already
useful, rather than an agent that has to learn everything from scratch in production (which
would cause errors during the learning period).

### Learning by Watching

The warm-start works on the same principle as a chess player who studies thousands of
grandmaster games before playing their first tournament match. Research has shown that the
*volume* of scenarios an AI studies matters more than the complexity of its architecture
(Stöckl, RANLP 2021 — studying how AI learns chess by watching expert games). A small,
efficient model that has observed hundreds of thousands of expert decisions will outperform
a much larger model that has only seen a few thousand.

This is why each Autonomy agent studies at least **450,000 synthetic supply chain scenarios**
during warm-start — covering normal operations, demand spikes, supply disruptions, capacity
constraints, and other edge cases. The scenarios are generated from your actual data
distributions (demand patterns, lead time variability, seasonal trends) using Monte Carlo
simulation, so they are representative of what the agent will encounter in production.

The volume matters because supply chain decisions have rules that must be *learned*, not just
*memorized*. An agent that has only seen 5,000 scenarios might appear trained (its error
metric looks low), but it will fail on unfamiliar situations — like a chess program that
recognizes common openings but makes illegal moves in novel positions. Our agents are trained
past this threshold to the point where they internalize the underlying decision rules.

**What this stage does NOT do**: It does not make the agent *better* than your planners.
It makes the agent *as good as* the historical patterns in your data. The next stage is
what takes performance beyond human-baseline.

---

## Stage 2: On the Job (After Go-Live)

Once agents are live and making decisions, each decision becomes a data point for
improvement.

Here is how it works: the agent makes a recommendation (say, create a purchase order for
500 units with delivery in 3 weeks). The planner reviews it — accepts, adjusts, or
overrides. Some time later (hours for ATP decisions, days for purchase orders, weeks for
inventory buffer adjustments), the actual outcome is measured: did the order arrive on
time? Did it prevent a stockout? Was inventory held too long? Did the service level improve?

The agent receives a *reward signal* — a score based on the actual business outcome (cost
reduction, service level, inventory efficiency) rather than just whether it matched what
a human would have done. Over time, the agent discovers that some decision patterns
consistently earn better outcomes than the historical baseline. These patterns are
reinforced. Patterns that earn poor outcomes are weakened.

This is the "on the job" learning phase. It is what allows agents to eventually *outperform*
historical human decisions — not because the AI is smarter in some abstract sense, but
because it has seen the outcomes of millions of decisions and can identify which patterns
actually cause better results.

**Key business implications**:
- Agent performance improves continuously over the first 3–6 months of operation.
- The more decisions the agent handles, the faster it improves.
- Planner overrides are not wasted — they are studied. If an override consistently leads
  to better outcomes than the agent's recommendation, that override pattern is incorporated
  into the agent's future behavior.
- Agents become *specific to your supply chain*. After 6 months, your agents have learned
  patterns that are unique to your suppliers, your demand variability, your production
  constraints. A competitor could not simply copy them.

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
   against what actually happened.
2. **Detects drift** when the gap between predictions and outcomes exceeds a threshold —
   for example, if ATP fill rates drop more than expected, or if purchase order quantities
   are consistently too high or too low.
3. **Retrains automatically** every 6 hours when drift thresholds are exceeded and
   enough new data has accumulated (typically 100+ new decision-outcome pairs).
4. **Guards against regression** — new model versions are only deployed if they perform
   at least as well as the current version on a held-out validation set. Bad retraining
   runs are discarded automatically.
5. **Escalates when needed** — if drift is too severe for execution-level retraining to
   fix (for example, a fundamental shift in demand seasonality), the system escalates to
   the tactical or strategic planning agents to re-optimize policy parameters.

From a business perspective, this means the platform requires no ongoing data science
maintenance. Agents adapt to your evolving supply chain automatically, and they get
better over time rather than decaying.

---

## The Compounding Advantage

Each stage builds on the previous one:

```
Study phase     → agent is as good as historical data
On the job      → agent exceeds historical performance
Continuous      → agent stays current as conditions change
                   + captures planner expertise as overrides
                   + gets increasingly specific to your supply chain
```

The longer the system runs, the harder this advantage is to replicate. A competitor
deploying the same platform would start at Stage 1. Your agents would already be at
Stage 3, trained on years of your specific supply chain dynamics and your planners'
expertise. This is what makes the learning flywheel a durable competitive advantage,
not just a one-time efficiency gain.

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

---

## Summary Table

| Stage | Timing | What Happens | Business Outcome |
|-------|--------|--------------|-----------------|
| **Warm-Start** | Before go-live (1–3 days) | Agent studies historical data and expert decisions | Agent starts at human-baseline performance |
| **On the Job** | First 3–6 months | Agent learns from actual outcomes and planner overrides | Agent exceeds human-baseline; becomes supply-chain-specific |
| **Continuous** | Ongoing, autonomous | System detects drift and retrains automatically | Performance stays current; no maintenance overhead |

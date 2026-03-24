# Scenario Engine — Machine-Speed What-If Planning

**Version**: 2.0 | **Date**: 2026-03-24 | **Status**: Implementing
**Cross-refs**: [AGENTIC_AUTHORIZATION_PROTOCOL.md](../../docs/AGENTIC_AUTHORIZATION_PROTOCOL.md), [POWELL_APPROACH.md](../../POWELL_APPROACH.md), [TRM_HIVE_ARCHITECTURE.md](../../TRM_HIVE_ARCHITECTURE.md), [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md)

---

## 0. Research Foundations

This architecture is grounded in extensive research across industry practice and academic literature.

### Industry Benchmarks

| Vendor | Scenario Approach | Key Innovation | Reference |
|--------|------------------|----------------|-----------|
| **Kinaxis** | Git-like in-memory branching, copy-on-write versioning | Instant branching (seconds), Maestro Agents auto-generate scenarios (2025) | [Technical Deep Dive](https://www.kinaxis.com/en/blog/concurrent-planning-technically-speaking) |
| **OMP** | Monte Carlo + probabilistic planning + autonomous agents | Decision-Centric Planning (March 2026): system presents decisions, not infinite scenarios | [Decision-Centric Planning](https://omp.com/news-events/news/2026/omp-unveils-decision-centric-planning-to-accelerate-supply-chain-decision-velocity) |
| **Aera Technology** | Autonomous decision intelligence | Self-assembling agent teams, learning/governance agents (2026 roadmap) | [Gartner DIP MQ Leader, Jan 2026](https://www.aeratechnology.com/) |
| **Blue Yonder** | AI generates thousands of scenario simulations automatically | Prescriptive analytics identifies problems AND suggests optimal solutions | [Luminate Platform](https://blueyonder.com/solutions/supply-chain-planning) |
| **o9 Solutions** | Unified knowledge graph, GenAI-powered what-if | Real-time cross-functional impact assessment | [Digital Brain](https://o9solutions.com/) |

### Academic Foundations

| Concept | Application | Key Paper |
|---------|------------|-----------|
| **MCTS for multi-agent planning** | Decoupled-MCTS evaluates each agent separately, then combines | MDPI 2023; C-MCTS (arXiv:2305.16209) |
| **MuZero architecture** | Policy prior (which scenarios to explore) + value network (fast evaluation) + MCTS (structured search) | DeepMind; Multiagent Gumbel MuZero (AAAI 2024) |
| **Satisficing** (Herbert Simon, 1956) | Search until acceptability threshold met, then stop | Bounded rationality — agents have time budgets |
| **Anytime algorithms** | Produce progressively better solutions, interruptible | ARA*, Budget-Aware Reasoning (arXiv:2601.11038) |
| **CVaR scenario scoring** | Expected loss in worst α% of scenarios — coherent risk measure | arXiv:2503.23561 bridges conformal prediction and scenario optimization |
| **Prospect Theory** (Kahneman) | Losses loom ~2× larger than gains; reference-dependent evaluation | Loss-averse newsvendor orders less than optimal (Springer 2023) |
| **Conformal + scenario optimization bridge** | CP coverage guarantees = scenario optimization feasibility guarantees | arXiv:2603.19396 — modular risk budgeting across planning horizon |
| **Agentic LLM consensus** | LLM agents exchange messages, propose quantities, revise based on feedback | IJPR 2025 (arXiv:2411.10184) — reduces bullwhip |

### Architectural Choice: MCTS, Not LLM

The scenario engine uses **Monte Carlo Tree Search with domain-specific evaluation**, not LLM-based reasoning:

| Approach | Speed | Determinism | Learning | Cost | Verdict |
|----------|-------|-------------|----------|------|---------|
| **LLM scenario generation** | 200-500ms/call | Non-deterministic | None (stateless) | $0.002-0.005/call | Slow, unreliable, expensive |
| **Template + random search** | <1ms/candidate | Deterministic | Beta posteriors | $0 | Fast but misses creative options |
| **MCTS + TRM evaluation** | 100-300ms/tree | Deterministic tree, stochastic rollout | Policy prior + value estimates | $0 | **Optimal**: structured search, learned priors, domain evaluation |

The MuZero mapping to Autonomy:

```
MuZero Component        → Autonomy Equivalent
Policy Network          → Template priors (Beta posteriors) + GraphSAGE embeddings
Value Network           → TRM ensemble rapid evaluation (BSC estimate without full rollout)
Dynamics Model          → Digital twin _DagChain simulation
MCTS                    → Scenario search tree with budget allocation
Simulation Budget       → Hard caps per decision level (3/5/10 candidates)
```

### Gartner Predictions (validating this direction)

- **50% of SCM solutions will include agentic AI by 2030** (Gartner, May 2025)
- **60% of supply chain disruptions resolved without human intervention by 2031** (Gartner, March 2026)
- **Decision Intelligence Platforms** inaugural Magic Quadrant published January 2026 (Leaders: SAS, FICO, Aera)

---

## 1. Executive Summary

The Scenario Engine enables Autonomy agents to **test decision cascades in simulation before committing**. When a TRM agent encounters a situation it cannot resolve within its authority (e.g., an ATP agent that needs additional supply), it creates a **scenario branch** — a lightweight fork of the digital twin — injects proposed actions, simulates the consequences, and compares alternatives using a risk-adjusted Balanced Scorecard.

This is analogous to Git branching: the Plan of Record is `main`, agents create feature branches to test alternatives, the best branch is merged (promoted), and rejected branches are deleted.

**Key principle**: Agents don't just make decisions — they **test decision cascades** and present the best option with full BSC impact analysis. The skill is not generating scenarios but knowing **when** to generate them and **when to stop**.

---

## 2. Git Analogy

| Git Concept | Autonomy Equivalent | Example |
|-------------|---------------------|---------|
| `main` branch | Plan of Record | Committed supply plan, executing orders |
| Feature branch | Agent scenario | "What if we expedite this order?" |
| Fork | Cross-site scenario | Upstream site evaluates its own alternatives |
| Pull request | AAP authorization request | ATP asks PO agent to commit a purchase order |
| PR review | Responsible agent evaluation | PO agent reviews proposal, may counter-propose |
| CI/CD checks | BSC scoring | Financial, customer, operational, strategic metrics |
| Merge | Promote scenario | All individual decisions actioned, scenario deleted |
| Branch delete | Reject scenario | Proposed actions discarded |
| Merge conflict | Resource contention | Two scenarios compete for same capacity |
| Rebase | Re-evaluation | Underlying data changed, rescore scenarios |

---

## 3. When to Create Scenarios (Scenario Trigger)

### 3.1 The Analysis Paralysis Problem

Unbounded scenario generation is worse than no scenarios. The opportunity cost of late action often exceeds the benefit of finding the optimal action. **The skill is knowing which situations deserve scenario testing and which don't.**

### 3.2 Trigger Formula

```python
scenario_value = economic_impact × uncertainty × time_available
scenario_cost  = compute_time + opportunity_cost_of_delay

CREATE scenario IF scenario_value > scenario_cost
```

Implemented as a **logistic regression** on four features already computed by the TRM + CDT pipeline:

```python
score = (
    w_uncertainty × risk_bound +        # CDT: P(loss > threshold)
    w_urgency × urgency +               # UrgencyVector: time pressure
    w_impact × log(economic_impact) -    # Order value × shortfall
    w_confidence × confidence            # TRM self-confidence
)

create_scenario = score > threshold
```

**Weights and threshold** are calibrated from historical decision-outcome pairs:
- Decisions where TRM solo action failed AND a scenario would have found better → positive signal
- Decisions where TRM solo action succeeded → negative signal (scenario would have been waste)

Calibration uses the same infrastructure as CDT (outcome collector, hourly incremental updates).

### 3.3 Trigger Conditions

| Trigger | Source | Threshold | Example |
|---------|--------|-----------|---------|
| **CDT risk bound high** | TRM confidence head | `risk_bound > 0.40` | TRM uncertain about best action |
| **Economic impact high** | Order value × shortfall | `impact > $10K` (configurable per tenant) | High-value order can't be fulfilled |
| **Authority boundary** | AAP | Action requires cross-agent authorization | ATP needs PO agent to create order |
| **Repeated escalation** | Pattern detection | Same TRM type > 5 escalations/day | Policy problem — upward signal to S&OP |
| **Human request** | Azirella directive | Explicit "test what if..." | Executive asks what-if question |

### 3.4 Hard Caps (Prevent Analysis Paralysis)

| Decision Level | Max Candidates | Max Simulation Time | Max Scenarios/Hour |
|---------------|---------------|--------------------|--------------------|
| **Execution** (TRM) | 3 | 1 second | 20 |
| **Tactical** (Site tGNN) | 5 | 5 seconds | 10 |
| **Strategic** (S&OP) | 10 | 30 seconds | 5 |
| **Human-requested** (Azirella) | 10 | 60 seconds | Unlimited |

---

## 4. Which Candidates to Generate

### 4.1 Template-Based Candidate Generation

Candidates are generated from **rule-based templates** per TRM type, not by neural network. Each template has a **Beta posterior** tracking its historical success rate:

```python
template_prior = Beta(alpha=successes+1, beta=failures+1)
prior_likelihood = template_prior.mean()  # E[p] of success
```

Templates are sorted by `prior_likelihood DESC` and tried in order.

### 4.2 ATP Shortfall Templates (Example)

When ATP detects insufficient allocation for a high-value order:

| # | Template | Description | Prior |
|---|----------|-------------|-------|
| 1 | **Split fulfillment** | Fulfill available% from stock, PO remainder | Beta(α, β) |
| 2 | **Fast supplier PO** | PO full quantity from fastest available supplier + expedite | Beta(α, β) |
| 3 | **Cheap supplier PO** | PO from cheapest supplier, accept longer lead time | Beta(α, β) |
| 4 | **Delay fulfillment** | Promise delivery at next available date | Beta(α, β) |
| 5 | **Partial + backorder** | Ship 60% now, backorder 40% | Beta(α, β) |

### 4.3 Optimal Stopping (Diminishing Returns)

```python
candidates = sorted_by_prior_likelihood(templates)
best_score = -infinity
for i, candidate in enumerate(candidates):
    if i >= max_candidates:           # Hard cap per decision level
        break
    score = simulate_and_score(candidate)
    improvement = score - best_score
    if i > 0 and improvement < min_improvement_threshold:
        break                          # Diminishing returns — stop early
    best_score = max(best_score, score)
```

---

## 5. Risk-Adjusted BSC Scoring

### 5.0 Three-Tier Anytime Execution

The scenario engine operates as an **anytime algorithm** — it produces a usable answer immediately and improves it if time allows:

```
Tier 1 — TRM Solo (<10ms):
    TRM computes action + confidence
    IF confidence > threshold → ACCEPT (no scenario needed)
    ELSE → escalate to Tier 2

Tier 2 — Template Search (100ms-1s):
    Generate top 3 candidates from template library (sorted by Beta prior)
    Simulate each via _DagChain (100-300ms per candidate)
    Score with risk-adjusted BSC
    IF best score satisfices (above aspiration threshold) → ACCEPT
    ELSE → escalate to Tier 3 (if budget allows)

Tier 3 — MCTS Deep Search (1-30s):
    Expand search tree with child scenarios (PO → TO → delivery cascades)
    MCTS with OCBA budget allocation (spend more on promising+uncertain branches)
    Secretary-problem stopping: after N/e candidates, accept first that beats all seen
    OR hard cap reached → return best found
```

This maps to **Kahneman's dual-process theory**: Tier 1 = System 1 (fast, intuitive), Tier 2 = System 2 (deliberate, bounded), Tier 3 = deep analysis (rare, expensive).

### 5.1 Core Formula

```
scenario_score = raw_bsc_value × compound_likelihood × urgency_discount
```

Where:
- **`raw_bsc_value`** = context-weighted BSC across 4 dimensions
- **`compound_likelihood`** = product of individual decision likelihoods in the scenario
- **`urgency_discount`** = time decay (scenarios that take longer to execute are worth less)

### 5.2 Compound Likelihood

Each decision in a scenario has its own CDT-derived likelihood. The scenario's compound likelihood is:

```
compound_likelihood = ∏(decision_likelihood_i)

Example:
  PO creation:       likelihood = 0.92 (reliable supplier)
  Inbound TO:        likelihood = 0.85 (lane has variance)
  Outbound expedite: likelihood = 0.78 (carrier availability uncertain)

  compound_likelihood = 0.92 × 0.85 × 0.78 = 0.61
```

### 5.3 Context-Weighted BSC

The BSC metric weights are **dynamic**, not static — they come from the business context:

| Metric Dimension | Weight Factors |
|-----------------|----------------|
| **Financial** (cost, margin) | Revenue pressure at this location/region, product margin |
| **Customer** (OTIF, fill rate) | Customer importance (top-10?), contractual penalties, relationship risk |
| **Operational** (inventory, capacity) | Current utilization, seasonal factors |
| **Strategic** (flexibility, resilience) | Product importance (core vs tail), supply risk score |

```python
weights = {
    'financial': base_weight * (1 + revenue_pressure_factor),
    'customer': base_weight * (1 + customer_importance_factor),
    'operational': base_weight * (1 + capacity_utilization_factor),
    'strategic': base_weight * (1 + product_importance_factor),
}

raw_bsc = sum(dimension_score * weights[dim] for dim in dimensions)
```

### 5.4 Scenario Comparison Example

| Scenario | Raw BSC | Likelihood | Urgency Discount | Final Score |
|----------|---------|-----------|------------------|-------------|
| A: Split 60/40 + fast supplier | $45K benefit | 0.61 | 0.95 | **$26.1K** |
| B: Cheap supplier + accept delay | $32K benefit | 0.95 | 0.85 | **$25.8K** |
| C: Delay delivery 5 days | $28K benefit | 0.98 | 0.80 | **$21.9K** |
| D: Do nothing (baseline) | $0 | 1.00 | 1.00 | **$0** |

Scenario A has the highest raw value but lowest likelihood. Scenario B wins because its high likelihood compensates for lower raw value. This is **Prospect Theory** — the certain option is preferred unless the risky upside is large enough.

### 5.5 CVaR Risk Penalty (Optional)

For Monte Carlo-evaluated scenarios (where the digital twin runs N stochastic replications per candidate), the score can incorporate **Conditional Value-at-Risk**:

```
scenario_score = E[bsc_value] × likelihood - λ × CVaR_95(bsc_cost)
```

Where `CVaR_95` = expected cost in the worst 5% of replications. The risk aversion parameter `λ` is configurable per tenant (default 0.3). This penalizes scenarios with fat-tailed downside risk even if their expected value is high.

**Connection to conformal prediction** (arXiv:2503.23561, 2603.19396): Conformal prediction's coverage guarantees and scenario optimization's feasibility guarantees are mathematically equivalent. The CDT risk bounds on individual decisions provide the building blocks for scenario-level CVaR computation without requiring full Monte Carlo. Modular risk budgeting distributes the coverage guarantee across the planning horizon.

### 5.6 Satisficing Threshold

Following Herbert Simon's satisficing principle, scenario search stops early if any candidate exceeds the **aspiration threshold**:

```
aspiration = baseline_bsc × (1 + min_improvement_pct)

IF scenario_score > aspiration → ACCEPT immediately, stop search
```

`min_improvement_pct` defaults to 5% — a scenario must be at least 5% better than doing nothing to justify the complexity of multi-agent execution. This prevents analysis paralysis for situations where the marginal value of searching further is low.

---

## 6. Scenario Lifecycle

### 6.1 States

```
CREATED → EVALUATING → SCORED → PROMOTED | REJECTED | EXPIRED
```

### 6.2 Flow

```
1. TRM detects situation requiring scenario testing
   ↓
2. ScenarioTrigger evaluates: scenario_value > scenario_cost?
   ├── No → TRM proceeds with solo decision
   └── Yes ↓
3. CandidateGenerator produces N templates (sorted by prior likelihood)
   ↓
4. ScenarioEngine creates branch for each candidate:
   a. Fork current digital twin state
   b. Inject proposed actions (PO, TO, expedite, etc.)
   c. Simulate forward 7-14 days
   d. Compute raw BSC for the scenario
   e. Compute compound likelihood from individual decision CDT bounds
   f. Score: raw_bsc × likelihood × urgency_discount
   ↓
5. Stop when diminishing returns OR hard cap reached
   ↓
6. Compare scenarios, rank by final score
   ↓
7. Best scenario surfaced to Decision Stream with:
   - Scenario comparison table
   - Individual decisions required
   - Risk-adjusted BSC delta vs baseline
   - Urgency and likelihood context
   ↓
8. Promotion:
   a. Each decision in winning scenario sent to responsible agent via AAP
   b. PO agent receives "create PO" → ACTIONED
   c. TO agent receives "expedite TO" → ACTIONED
   d. ATP agent receives "promise delivery" → ACTIONED
   ↓
9. Cleanup:
   - Promoted scenario: decisions extracted, scenario marked PROMOTED
   - Rejected scenarios: marked REJECTED, retained for training data
   - Expired scenarios: decisions timed out, marked EXPIRED
```

### 6.3 Cross-Site Scenarios

When a scenario requires action at another site:

```
Site A (ATP): "I need 400 units manufactured at Site B"
    ↓ AAP authorization request to Site B
Site B (MO): Creates its OWN scenario branch:
    ├── "Can I add this MO without disrupting existing orders?"
    ├── Simulates locally
    └── Responds: "Yes, deliverable in 8 days" OR "Counter: 300 units in 5 days"
    ↓
Site A incorporates response into its scenario scoring
```

Each site maintains its own scenario branches. Cross-site communication happens through AAP, not shared scenarios.

---

## 7. Upward Policy Signal

### 7.1 Pattern Detection

When execution-level agents generate scenarios at high rates, it signals a **policy problem**, not an execution problem:

```python
# Monitored hourly by the Escalation Arbiter
scenario_rate = count_scenarios(trm_type, last_24h)
historical_avg = avg_scenario_rate(trm_type, last_30d)

if scenario_rate > historical_avg * 3:
    # This TRM type is creating 3× more scenarios than normal
    escalate_to_sop({
        'signal': 'excessive_scenario_generation',
        'trm_type': trm_type,
        'rate': scenario_rate,
        'historical_avg': historical_avg,
        'recommendation': infer_policy_adjustment(trm_type, recent_scenarios),
    })
```

### 7.2 Policy Adjustment Recommendations

| Pattern | Signal | Recommended Adjustment |
|---------|--------|----------------------|
| ATP scenarios > 3×avg | Allocation insufficient | Increase allocation for affected priority/product |
| PO scenarios > 3×avg | Lead times too long | Qualify alternate suppliers, negotiate expedite terms |
| Rebalancing scenarios > 3×avg | Network imbalance structural | Adjust inventory positioning policy |
| MO scenarios > 3×avg | Capacity insufficient | Evaluate capacity expansion or outsourcing |

---

## 8. Learning Flywheel

### 8.1 What Learns

| Component | What It Learns | Training Data | Method |
|-----------|---------------|---------------|--------|
| **Scenario Trigger** | When to create scenarios | Decision outcomes (solo vs scenario) | Logistic regression, hourly calibration |
| **Template priors** | Which candidates work | Scenario outcomes (promoted vs rejected) | Beta posterior, updated on each outcome |
| **TRMs** | Better individual decisions | Promoted scenario decisions as training data | Offline RL (CDC loop, every 6h) |
| **CDT bounds** | Tighter confidence intervals | All decision outcomes | Conformal calibration, hourly |
| **Upward signals** | When policies are wrong | Scenario rate patterns | Deterministic threshold monitoring |

### 8.2 Convergence

Over time, the system converges:
1. TRMs learn better solo decisions → fewer scenarios needed
2. Template priors converge → better candidates tried first → fewer candidates needed
3. CDT bounds tighten → uncertainty decreases → trigger fires less often
4. Policies adjust upward → fewer structural mismatches → fewer escalations

The scenario engine should become **less active** as the system matures. High scenario rates after initial convergence indicate either changing business conditions or model drift — both legitimate reasons for increased scenario activity.

---

## 9. Database Model

### 9.1 Tables

**`agent_scenarios`** — scenario branches:
```sql
id                  SERIAL PRIMARY KEY
config_id           INTEGER REFERENCES supply_chain_configs(id)
tenant_id           INTEGER REFERENCES tenants(id)
parent_scenario_id  INTEGER REFERENCES agent_scenarios(id)  -- for child scenarios
trigger_decision_id INTEGER                                  -- the decision that triggered this
trigger_trm_type    VARCHAR(50)
trigger_context     JSONB                                    -- order details, shortfall, urgency
decision_level      VARCHAR(20)                              -- execution/tactical/strategic
status              VARCHAR(20)                              -- CREATED/EVALUATING/SCORED/PROMOTED/REJECTED/EXPIRED
raw_bsc_score       FLOAT
compound_likelihood FLOAT
urgency_discount    FLOAT
final_score         FLOAT
bsc_breakdown       JSONB                                    -- per-dimension scores
context_weights     JSONB                                    -- dynamic BSC weights used
simulation_days     INTEGER
simulation_seed     INTEGER
created_at          TIMESTAMP DEFAULT now()
scored_at           TIMESTAMP
resolved_at         TIMESTAMP
expires_at          TIMESTAMP
```

**`agent_scenario_actions`** — individual actions within a scenario:
```sql
id                  SERIAL PRIMARY KEY
scenario_id         INTEGER REFERENCES agent_scenarios(id) ON DELETE CASCADE
trm_type            VARCHAR(50)
action_type         VARCHAR(50)                              -- CREATE_PO, EXPEDITE_TO, ADJUST_FORECAST, etc.
action_params       JSONB                                    -- product_id, quantity, supplier, etc.
responsible_agent   VARCHAR(50)                              -- which TRM type must approve/execute
decision_likelihood FLOAT                                    -- CDT risk bound for this action
estimated_cost      FLOAT
estimated_benefit   FLOAT
status              VARCHAR(20)                              -- PROPOSED/ACTIONED/REJECTED
actioned_decision_id INTEGER                                 -- FK to powell_*_decisions when promoted
created_at          TIMESTAMP DEFAULT now()
```

**`scenario_templates`** — template library with Beta priors:
```sql
id                  SERIAL PRIMARY KEY
trm_type            VARCHAR(50)
template_key        VARCHAR(100)                             -- e.g., 'split_fulfillment', 'fast_supplier_po'
template_name       VARCHAR(255)
template_params     JSONB                                    -- configurable parameters
alpha               FLOAT DEFAULT 1.0                        -- Beta posterior successes
beta                FLOAT DEFAULT 1.0                        -- Beta posterior failures
uses_count          INTEGER DEFAULT 0
last_used_at        TIMESTAMP
tenant_id           INTEGER REFERENCES tenants(id)
created_at          TIMESTAMP DEFAULT now()
```

### 9.2 Indexes

```sql
CREATE INDEX ix_agent_scenarios_config ON agent_scenarios(config_id, status);
CREATE INDEX ix_agent_scenarios_trigger ON agent_scenarios(trigger_trm_type, created_at);
CREATE INDEX ix_scenario_actions_scenario ON agent_scenario_actions(scenario_id);
CREATE INDEX ix_scenario_templates_trm ON scenario_templates(trm_type, tenant_id);
```

---

## 10. Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/services/powell/scenario_engine.py` | Core: branch simulation, inject actions, BSC scoring |
| `backend/app/services/powell/scenario_trigger.py` | When to create scenarios (logistic regression) |
| `backend/app/services/powell/scenario_candidates.py` | Template library + candidate generation |
| `backend/app/services/powell/contextual_bsc.py` | Context-weighted BSC scoring |
| `backend/app/models/agent_scenario.py` | DB models: AgentScenario, AgentScenarioAction, ScenarioTemplate |
| `backend/app/api/endpoints/scenarios_engine.py` | API: create/list/compare/promote scenarios |
| `backend/app/services/powell/scenario_lifecycle.py` | State machine: promote/reject/expire/cleanup |

---

## 11. Integration Points

| System | Integration |
|--------|------------|
| **TRM SiteAgent** | Calls `ScenarioTrigger.should_create()` before solo action; if yes, delegates to ScenarioEngine |
| **AAP** | Cross-agent authorization requests carry scenario context; responses include counter-scenario proposals |
| **Decision Stream** | Scenario comparisons surfaced with BSC table, recommended action, risk assessment |
| **Azirella** | "Test what if..." directives create human-requested scenarios |
| **CDC Relearning** | Promoted scenario decisions feed into TRM training data |
| **Escalation Arbiter** | Monitors scenario rates; triggers upward policy signals |
| **Digital Twin** | `_DagChain` with pluggable policy provides the simulation environment |

---

## 12. Provisioning Integration

The scenario engine is **not a provisioning step** — it activates automatically when:
1. TRM models are trained (step 8/9 in provisioning)
2. CDT is calibrated (step 13/14)
3. Template priors are initialized (all Beta(1,1) = uninformative)

Template priors warm up from the first few promoted/rejected scenarios. After ~50 scenarios per TRM type, the priors stabilize and candidate ranking becomes effective.

---

## 13. No New Neural Networks

The entire scenario capability is built from **existing infrastructure**:

| Component | Implementation | Existing Infrastructure Used |
|-----------|---------------|------------------------------|
| Scenario trigger | Logistic regression (4 features) | CDT risk bounds, urgency vectors, economic impact |
| Candidate generation | Rule-based templates | Heuristic library, supplier data |
| Candidate ranking | Beta posteriors | Same as override effectiveness tracking |
| Simulation | Digital twin `_DagChain` | Same simulation engine used for training |
| BSC scoring | Weighted formula | Existing BSC framework + context factors |
| Likelihood | CDT compound | Existing CDT wrappers per TRM type |
| Upward signals | Threshold monitoring | Existing escalation arbiter |
| Learning | Outcome collection → recalibration | Existing CDC loop |

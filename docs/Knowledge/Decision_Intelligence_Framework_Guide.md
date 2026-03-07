# Decision Intelligence Framework Guide

**Date**: 2026-03-06
**Sources**: Gartner (2025-2026 Hype Cycles, Magic Quadrant, Market Guides), Cassie Kozyrkov (Google/Kozyr), Lorien Pratt (Decision Intelligence Handbook), Aera Technology, industry analyst reports
**Purpose**: Synthesize Decision Intelligence frameworks and map them to Autonomy's architecture for positioning and feature development

---

## Executive Summary

Decision Intelligence (DI) is a practical discipline that advances decision-making by explicitly understanding and engineering how decisions are made, and how outcomes are evaluated, managed, and improved via feedback. Gartner designated DI as a **"transformational" technology** in the 2025 AI Hype Cycle and published its **inaugural Magic Quadrant for Decision Intelligence Platforms** in January 2026 — signaling market maturity.

**Key finding**: Autonomy already implements the core DI lifecycle (decision modeling via Powell SDAM, execution via TRM agents, monitoring via CDC/conformal prediction, governance via AAP/override tracking). The primary gap is **explicit decision asset modeling as a first-class UI concept** — surfacing decisions as trackable, auditable, governable objects rather than implicit outputs of planning runs. Closing this gap positions Autonomy as a native Decision Intelligence Platform for supply chain, not merely a planning tool that happens to use AI.

---

## Part 1: Gartner's Decision Intelligence Framework

### 1.1 Definition

Gartner defines Decision Intelligence as:

> "A practical discipline that advances decision making by explicitly understanding and engineering how decisions are made, and how outcomes are evaluated, managed and improved via feedback. By digitizing and modeling decisions as assets, DI bridges the insight-to-action gap to continuously improve decision quality, actions and outcomes."

Source: Gartner IT Glossary, 2025

### 1.2 Decision Intelligence Platforms (DIPs)

Gartner defines DIPs as:

> "Software solutions designed to support, automate, and augment decision-making for humans and machines. These platforms bring together data, analytics, knowledge, and AI, while also enabling collaboration across decision modeling, execution, monitoring, and governance."

### 1.3 Four Decision Lifecycle Capabilities

Every DIP must deliver across the full decision lifecycle:

| Capability | Description | Autonomy Mapping |
|---|---|---|
| **Decision Modeling** | Explicitly define decision structure, inputs, logic, constraints, ownership | Powell SDAM five elements (State, Decision, Exogenous Info, Transition, Objective) |
| **Decision Orchestration** | Coordinate execution flows across systems and agents | TRM Hive decision cycle (6 phases), AAP cross-authority protocol |
| **Decision Monitoring** | Track outcomes, detect drift, measure quality | CDC relearning loop, conformal prediction, CRPS scoring |
| **Decision Governance** | Ensure compliance, auditability, trustworthiness | Override effectiveness tracking, CDT risk bounds, escalation arbiter |

### 1.4 Four Use Cases (Critical Capabilities Report, Jan 2026)

Gartner evaluates DIP vendors across four use cases:

1. **Decision Stewardship** — Governance, monitoring, and lifecycle management of decisions
   - *Autonomy*: Override tracking with Bayesian posteriors, CDT risk_bound on every decision, escalation log, CDC trigger audit trail

2. **Decision Analysis** — Analytical decisioning and rules-driven workflows
   - *Autonomy*: Deterministic engine (always runs first), 8 inventory policy types, probabilistic balanced scorecard

3. **Decision Engineering** — Orchestration, modeling, and execution capabilities
   - *Autonomy*: 11 TRM agents, TRM Hive with signal bus, AAP authorization protocol, Powell SDAM state/decision/transition modeling

4. **Decision Science** — Blended approaches combining analytics, ML, and logical reasoning
   - *Autonomy*: Hybrid TRM + Claude Skills architecture, conformal prediction routing, distribution-aware feature engineering, CRPS scoring

### 1.5 Inaugural Magic Quadrant (January 26, 2026)

**Leaders**: SAS, FICO, Aera Technology
**Challengers**: Decisions
**Market**: First-ever formal MQ for DIPs — market has reached sufficient maturity for structured evaluation

Key evaluation criteria:
- Decision-centric architecture combining explicit decision modeling, AI-driven augmentation/automation, and governance at scale
- Comprehensive lifecycle capabilities: modeling → orchestration → monitoring → governance
- Integration of advanced AI techniques (generative AI, agentic AI)

### 1.6 Market Statistics

- **Current penetration**: 5-20% of enterprises (2025)
- **Maturity horizon**: 2-5 years to mainstream adoption
- **Adoption prediction**: By 2026, 75% of Global 500 will apply DI practices including decision logging for subsequent analysis (Gartner CDAO Survey 2024)
- **CDAO vision shift**: By 2028, 25% of CDAO vision statements will become "decision-centric" surpassing "data-driven"

---

## Part 2: Gartner Supply Chain Technology Trends (2025)

### 2.1 Four Interdependent Technologies

From Gartner's 2025 Hype Cycle for Supply Chain Planning Technologies:

| Technology | Hype Cycle Position | Maturity | Status |
|---|---|---|---|
| **Explainable AI** | Available now | Slope of Enlightenment | Proven but underused |
| **Autonomous Planning** | Past Peak | Trough of Disillusionment → Slope | Demands cultural shift from people-centric to decision-centric |
| **Agentic AI** | Innovation Trigger | Early | 50% of SCM solutions by 2030 (Gartner prediction) |
| **Decision-Centric Planning** | Innovation Trigger | Early | Leverages all other technologies; removes data latency |

**Key insight**: These four are "interdependent levers of change, not individual trends." Decision-centric planning is the organizing principle that unifies the other three.

### 2.2 Decision-Centric Planning

> "Decision-centric planning will leverage all technology, including autonomous planning, GenAI, and agentic AI to remove the inherent data latency in today's processes."

This means:
- Shift from **periodic batch planning** to **continuous decision execution**
- Each recurring choice (how much to buy, make, move, promise) is modeled as a **repeatable decision asset** with defined inputs, logic, constraints, and ownership
- Once modeled and measured, decisions become **replicable patterns** across processes and business units

### 2.3 Agentic AI in Supply Chain

> "Autonomous agents specialized in different areas (inventory, lead time, carbon management) interact seamlessly, creating integrated supply chain views that balance cost, service, cash flow, and sustainability objectives."

Gartner prediction: By 2030, **50% of cross-functional SCM solutions** will use intelligent agents to autonomously execute decisions.

**Autonomy mapping**: 11 narrow TRM agents already do this — each specializes in one decision type, coordinates via HiveSignalBus, and produces integrated decisions through the 6-phase decision cycle.

### 2.4 Analytics & Decision Intelligence Platforms in Supply Chain

Gartner's separate Market Guide for A&DI Platforms in Supply Chain (2025) recognizes the fragmented but rapidly growing market for supply-chain-specific decision intelligence. Supply chain technology leaders need to navigate market conditions and build cohesive roadmaps adopting A&DI capabilities.

---

## Part 3: Kozyrkov Framework — Decision Intelligence as Applied Data Science

### 3.1 Origin

Cassie Kozyrkov, Google's first Chief Decision Scientist, defined Decision Intelligence as:

> "The discipline of turning information into better actions at any setting, at any scale."

Developed at Google where Kozyrkov personally trained 15,000+ Googlers in ML, statistics, and data-driven decision-making. The approach combines applied data science with social and managerial sciences.

### 3.2 Three Sub-Disciplines

DI unifies three fields that traditionally operate in silos:

| Sub-Discipline | Focus | Autonomy Equivalent |
|---|---|---|
| **Applied Data Science** | Analytics, statistics, ML for extracting insights | Distribution fitting, conformal prediction, GNN forecasting |
| **Social Science** | Group dynamics, stakeholder perspectives, bias | Override effectiveness tracking, AAP cross-authority negotiation |
| **Managerial Science** | Goal alignment, process management, org structure | Powell SDAM objectives, planning cascade hierarchy |

### 3.3 Three Types of Data Analysis

Kozyrkov classifies data analysis by the number and type of decisions:

| Type | When to Use | Decision Count | Autonomy Equivalent |
|---|---|---|---|
| **Analytics** | Explore data, find patterns, no prior decisions made | Zero (exploration) | Dashboard KPIs, probabilistic balanced scorecard |
| **Statistics** | Make a few critical decisions under uncertainty | Few (high-stakes) | S&OP policy parameter setting (CFA θ), MPS approval |
| **ML/AI** | Automate decisions at scale across large datasets | Many (routine) | TRM agents (100+ decisions/second), autonomous execution |

### 3.4 Core Principles

1. **Decision as Irrevocable Resource Commitment** — A decision represents an allocation of resources (money, time, options) that constrains future choices
2. **Outcome = Decision Quality × Luck** — Only the process is controllable; external randomness affects results. Track decision quality, not just outcomes
3. **Value of Clairvoyance** — Invest decision-making effort proportional to stakes. High-impact choices warrant deep analysis; low-stakes decisions need minimal investment
4. **Decision Responsibility** — The person in charge provides direction and defines success. Data experts inform but do not own the decision

### 3.5 Seven-Step Decision Process

1. **Listen** — Gather diverse perspectives and data
2. **Clarify** — Define goals and problem boundaries
3. **Debate** — Evaluate alternatives constructively
4. **Decide** — Make explicit, informed choice
5. **Persuade** — Communicate rationale, secure buy-in
6. **Implement** — Execute with clear role assignment
7. **Learn** — Monitor outcomes, refine future processes

### 3.6 Fourteen Complexity Factors

Decision difficulty increases with: (1) option quantity, (2) unclear boundaries, (3) vague objectives, (4) high evaluation costs, (5) irreversibility, (6) cognitive load, (7) emotional impact, (8) stress, (9) incomplete information, (10) risk/ambiguity, (11) timing conflicts, (12) multi-stakeholder involvement, (13) internal conflicts, (14) adversarial dynamics.

---

## Part 4: Pratt Framework — Causal Decision Diagrams

### 4.1 Origin

Dr. Lorien Pratt, with four decades of ML/DI experience (clients: Human Genome Project, SAP, US DoE), authored:
- **"Link: How Decision Intelligence Connects Data, Actions, and Outcomes for a Better World"** (2019) — conceptual foundation
- **"The Decision Intelligence Handbook: Practical Steps for Evidence-Based Decisions in a Complex World"** (O'Reilly, 2023) — practical implementation guide

### 4.2 Causal Decision Diagrams (CDDs)

The central framework tool: a visual representation that formally models a chain of cause-and-effect links leading from actions to business outcomes.

**Four CDD Components**:

| Component | Definition | Supply Chain Example |
|---|---|---|
| **Decision Levers** | Choices/actions that decision-makers can take | Order quantity, safety stock level, supplier selection |
| **Outcomes** | Ultimate measurable goals | Total cost, service level, OTIF, inventory turns |
| **Externals** | Factors outside decision-maker's control | Demand variability, lead time uncertainty, supplier reliability |
| **Intermediaries** | Consequences along the path to outcomes (leading indicators) | Fill rate, days of supply, backlog level |

### 4.3 Decision-as-Asset Model

Pratt's key contribution: **every recurring decision should be treated as a digital asset** with:
- Defined inputs and triggers
- Explicit logic and constraints
- Clear ownership and authority
- Measurable outcomes linked to actions
- Feedback loops for continuous improvement

This maps directly to Powell SDAM's five elements:
| Pratt | Powell | Autonomy Implementation |
|---|---|---|
| Decision Lever | Decision xₜ | TRM action space (order qty, transfer qty, etc.) |
| Externals | Exogenous Information Wₜ₊₁ | Demand, lead time, supplier status |
| Intermediaries | State Sₜ | Inventory, backlog, pipeline, belief state |
| Outcomes | Objective Function | Dollar-denominated rewards, BSC metrics |
| Feedback | Transition Sᴹ | CDC relearning loop, outcome collection |

### 4.4 DI Operating Model (Balodis Framework)

Erik Balodis proposed a four-activity operating model for embedding DI:

| Activity | Description | Autonomy Mapping |
|---|---|---|
| **Decision Design** | Define decision structure, inputs, constraints, ownership | Supply chain config, policy types, authority boundaries |
| **Decision Support** | Provide insights, scenarios, recommendations | Probabilistic BSC, what-if scenarios, Ask Why |
| **Decision Optimization** | Use AI/ML to improve decision quality | TRM agents, CFA policy optimization, Monte Carlo |
| **Decision Review** | Monitor outcomes, recalibrate, learn | CDC triggers, override tracking, CRPS scoring |

**Enabling Factors**:
- **Organizational Capabilities**: Skill development, tool access, cross-functional teams
- **Decision Culture**: Psychological safety for overrides, learning from outcomes, transparency

---

## Part 5: Three-Level DI Maturity Model

### 5.1 Aera Technology's Framework

Based on Aera Technology's DI framework (MQ Leader), organizations progress through three levels:

| Level | Label | Human Role | AI Role | Autonomy Mode |
|---|---|---|---|---|
| **Level 1** | Decision Support | In the Loop | Provides insights, scenarios | Dashboard/reporting mode |
| **Level 2** | Decision Augmentation | On the Loop | Generates recommendations with impact analysis; humans approve/modify/reject | **Copilot mode** (current default) |
| **Level 3** | Decision Automation | Out of the Loop | Executes autonomously within predefined constraints with full auditability | **Autonomous mode** (target) |

### 5.2 Mapping to Autonomy's Agent Modes

| Agent Mode | DI Level | Override Behavior |
|---|---|---|
| Manual | Level 1 | All decisions require human input |
| Copilot | Level 2 | Agent proposes, human approves/overrides |
| Autonomous | Level 3 | Agent executes within guardrails, human monitors |

The progression from Level 2 → Level 3 is governed by:
- Override effectiveness posteriors (Bayesian Beta per user/TRM type)
- CDT risk_bound confidence levels
- Conformal prediction interval width
- Cumulative decision quality scores

---

## Part 6: Mapping Autonomy to Gartner DIP Capabilities

### 6.1 Comprehensive Capability Map

| Gartner DIP Capability | Autonomy Feature | Status |
|---|---|---|
| **Decision Modeling** | Powell SDAM (State, Decision, Exogenous, Transition, Objective) | ✅ Implemented |
| **Decision Orchestration** | TRM Hive 6-phase decision cycle, AAP authorization protocol | ✅ Implemented |
| **Decision Execution** | 11 narrow TRM agents, deterministic engine | ✅ Implemented |
| **Decision Monitoring** | CDC relearning loop, conformal prediction, CRPS, BSC | ✅ Implemented |
| **Decision Governance** | Override tracking, CDT risk_bound, escalation arbiter, authority boundaries | ✅ Implemented |
| **Decision Logging** | powell_*_decisions (11 tables), decision_embeddings, escalation_log | ✅ Implemented |
| **Outcome Tracking** | OutcomeCollectorService (hourly), site BSC delta measurement | ✅ Implemented |
| **Model Recalibration** | CDT calibration (hourly), conformal recalibration, TRM retraining (6h) | ✅ Implemented |
| **Generative AI Integration** | Claude Skills for exception handling (~5% of decisions) | ✅ Implemented |
| **Agentic AI** | 11 autonomous TRM agents per site, multi-site coordination via tGNN | ✅ Implemented |
| **Explainable AI** | AgentContextExplainer, 39 templates × 3 verbosity levels, Ask Why API | ✅ Implemented |
| **Decision-as-Asset UI** | Decisions surfaced in worklists but not yet first-class trackable objects | ⚠️ Gap |
| **Cross-Functional Collaboration** | AAP + S&OP Consensus Board | ✅ Implemented |
| **Decision Culture Metrics** | Override effectiveness, training weight progression | ✅ Implemented |

### 6.2 Key Gap: Decision Asset Visualization

The primary gap is making **decisions visible as first-class objects** in the UI. Currently:
- Decisions exist in 11 powell_*_decisions tables with full metadata
- Override tracking captures human adjustments with Bayesian scoring
- CDC monitor detects drift and triggers retraining

What's missing is a **Decision Intelligence Dashboard** that:
1. Shows decisions as trackable assets (not just planning outputs)
2. Visualizes the decision lifecycle (proposed → reviewed → accepted/overridden → executed → outcome measured)
3. Displays decision quality metrics (not just operational KPIs)
4. Provides decision-level governance (who decided, why, with what confidence, what happened)

---

## Part 7: UI Enhancement Recommendations

### 7.1 Decision Intelligence Dashboard (New Page)

**Purpose**: Surface decisions as first-class organizational assets per Gartner's DI framework.

**Components**:
1. **Decision Flow Sankey** — Visual flow from Proposed → Reviewed → Accepted/Overridden → Executed → Outcome Measured
2. **Decision Quality Score** — Aggregate metric tracking decision quality over time (separate from outcome luck)
3. **Decision Catalog** — Searchable registry of all recurring decision types (11 TRM types) with metadata: frequency, automation rate, override rate, quality score
4. **Decision Audit Trail** — Per-decision lifecycle view: who proposed, who reviewed, what confidence, what outcome, what the system learned

### 7.2 Decision Lifecycle Status in Existing Worklists

**Enhancement**: Add decision lifecycle columns to existing worklist pages (ATP, PO, Rebalancing, etc.):
- **Decision Status**: Proposed | Accepted | Overridden | Executed | Outcome Measured
- **Decision Quality**: Historical quality score for this decision type at this location
- **Confidence**: CDT risk_bound visualization (green/amber/red)
- **Ask Why**: Existing — link to explanation with counterfactual

### 7.3 Maturity Progression Indicator

**Enhancement**: Dashboard widget showing DI maturity level per decision type:
- **Level 1 (Support)**: Human makes all decisions, system provides data → Manual mode
- **Level 2 (Augmentation)**: Agent proposes, human approves → Copilot mode
- **Level 3 (Automation)**: Agent executes within guardrails → Autonomous mode

Visual: Progress bar per TRM type showing current level and readiness for next level (based on override posterior, CDT confidence, decision quality score).

### 7.4 Decision Culture Metrics

**Enhancement**: Add to Powell Dashboard:
- **Override Quality Trend** — Bayesian posterior E[p] over time per user and TRM type
- **Automation Rate by Decision Type** — Percentage of decisions executed without human review
- **Decision Velocity** — Time from event detection to decision execution
- **Learning Rate** — How quickly override patterns transfer to TRM weights

### 7.5 Causal Decision Diagram Visualization

**Enhancement**: Interactive CDD editor showing:
- **Decision Levers** (actions): Order quantity, safety stock, transfer, etc.
- **Externals** (uncertainty): Demand, lead time, yield, price
- **Intermediaries** (leading indicators): Fill rate, DOS, pipeline position
- **Outcomes** (goals): Total cost, OTIF, inventory turns

This would visually map how each TRM agent's decisions flow through intermediaries to outcomes — making the causal chain transparent and editable.

### 7.6 Decision-Back Planning View

**Enhancement**: Instead of "here are your KPIs, now figure out what to do," the UI starts from:
1. **What decision needs to be made?** (e.g., "How many units of SKU-123 to order from Supplier A?")
2. **What does the system recommend?** (TRM agent output with confidence)
3. **Why?** (causal chain: demand forecast → lead time → inventory position → economic trade-off)
4. **What are the alternatives?** (scenario comparison with BSC impact)
5. **What happened last time?** (historical outcome for similar decisions)

This implements Cloverpop's "decision-back" approach: start with the critical decision, then work backward to the data and analysis required.

---

## Part 8: Competitive Positioning

### 8.1 Autonomy vs. DIP Market Leaders

| Capability | SAS/FICO/Aera (DIP Leaders) | Autonomy |
|---|---|---|
| Decision Modeling | Generic business rules | Domain-specific: Powell SDAM for supply chain |
| Decision Execution | Rules engines, workflow | Real-time neural agents (TRM, <10ms) |
| Decision Monitoring | BI dashboards | Conformal prediction + CRPS + CDC triggers |
| Decision Governance | Audit logs | Bayesian override tracking + causal inference |
| Supply Chain Domain | Bolt-on or absent | Native (35 AWS SC entities, 8 policy types) |
| Agentic AI | Early/experimental | 11 production agents per site, multi-site coordination |
| Probabilistic | Limited | 21 distributions, Monte Carlo, CRPS, censored demand |
| Learning from Overrides | Basic | Bayesian posteriors + causal forests (Athey & Imbens 2018) |

### 8.2 Positioning Statement

Autonomy is the **first purpose-built Decision Intelligence Platform for supply chain** — combining Gartner's full DI lifecycle (model → orchestrate → monitor → govern) with domain-native supply chain intelligence (AWS SC compliance, 11 specialized agents, probabilistic planning) in a single platform. Unlike horizontal DIP vendors that require extensive customization for supply chain, Autonomy delivers decision intelligence out of the box for every stocking, ordering, and allocation decision.

---

## References

### Primary Sources (Gartner — paywalled, cited for positioning)

1. **Gartner Magic Quadrant for Decision Intelligence Platforms** (January 26, 2026)
   - First-ever MQ for DIPs; Leaders: SAS, FICO, Aera Technology
   - Source: https://www.gartner.com/en/documents/7363830

2. **Gartner Critical Capabilities for Decision Intelligence Platforms** (January 2026)
   - Four use cases: Stewardship, Analysis, Engineering, Science
   - Source: https://www.gartner.com/en/documents/7367030

3. **Gartner Hype Cycle for Supply Chain Planning Technologies, 2025** (November 12, 2025)
   - Decision-centric planning and agentic AI as newest innovations
   - Source: https://www.gartner.com/en/documents/6706434

4. **Gartner Market Guide for Analytics and Decision Intelligence Platforms in Supply Chain** (2025)
   - Source: https://www.gartner.com/en/documents/4478399

5. **Gartner IT Glossary: Decision Intelligence**
   - Source: https://www.gartner.com/en/information-technology/glossary/decision-intelligence

### Secondary Sources (publicly accessible)

6. **Cassie Kozyrkov** — Google's first Chief Decision Scientist, founder of Decision Intelligence Engineering
   - Decision Intelligence Substack: https://decision.substack.com/
   - Wikipedia: https://en.wikipedia.org/wiki/Cassie_Kozyrkov

7. **Lorien Pratt** — "The Decision Intelligence Handbook" (O'Reilly, 2023)
   - Source: https://www.amazon.com/Decision-Intelligence-Handbook-Practical-Evidence-Based/dp/1098139658
   - Blog: https://www.lorienpratt.com/dihandbook/

8. **Aera Technology** — DI insights from 2025 Gartner AI Hype Cycle
   - Source: https://www.aeratechnology.com/blogs/transformational-moment-decision-intelligence-2025-gartner-ai-hype-cycle/

9. **Bluecrux/Axon** — Gartner 2025 SC technology trends: DI, simulation, agentic AI
   - Source: https://www.bluecrux.com/blog/decision-intelligence-simulation-agentic-ai-gartner-trends-axon/

10. **Cloverpop** — Decision Intelligence and the 2025 Gartner AI Hype Cycle
    - Source: https://www.cloverpop.com/blog/the-2025-gartner-ai-hype-cycle-report-recognizes-decision-intelligence-as-transformational
    - Source: https://www.cloverpop.com/blog/decision-intelligence

11. **John Galt Solutions** — DI as pillar of next-gen supply chain planning
    - Source: https://johngalt.com/learn/blog/decision-intelligence-a-key-pillar-of-next-gen-supply-chain-planning

12. **Grounded Architecture** — DI in IT Architecture (Kozyrkov framework analysis)
    - Source: https://grounded-architecture.io/decision-intelligence

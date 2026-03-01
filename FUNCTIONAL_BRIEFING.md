# Autonomy Platform: Functional Capabilities Briefing

**Version**: 1.0
**Date**: March 1, 2026

---

## 1. Platform Overview

Autonomy is an enterprise supply chain planning and execution platform that combines continuous event-driven planning, three-tier AI decision-making, stochastic uncertainty modeling, and digital twin simulation into a single operating environment.

The platform is built on the AWS Supply Chain data model (100% compliant, 35/35 entities) and uses what we call the **Adaptive Decision Hierarchy (ADH)** — a layered architecture where strategic, operational, and execution decisions are made at appropriate time scales by appropriate models, with intelligent escalation between layers.

---

## 2. Planning Capabilities

### 2.1 Event-Driven Continuous Planning

The system replans only affected products and locations when events occur, rather than running full batch recalculations on a weekly cadence.

- **Event sources**: Supplier delays, demand spikes, capacity changes, forecast updates, order exceptions
- **Response latency**: P0 critical events addressed in under 1 minute; P1 in under 5 minutes
- **Incremental replanning**: Only affected SKU-location combinations are recalculated
- **Guardrailed autonomy**: Routine decisions auto-execute within configurable bounds (max PO value, max safety stock change, min service level floor); exceptions escalate to planners

### 2.2 Demand Planning

- **Forecast management**: View, edit, import/export demand plans with P10/P50/P90 confidence intervals
- **Consensus planning**: Multi-stakeholder forecast cycles (sales, marketing, finance, operations, statistical) with voting and approval workflows
- **CPFR collaboration**: Trading partner forecast sharing with exception detection (>20% variance threshold) and accuracy tracking per partner
- **ML forecast pipeline**: Configurable pipeline with 30+ parameters, clustering-based statistical forecasting
- **Version comparison**: Side-by-side comparison of any two forecast versions with delta analysis
- **Forecast adjustment history**: Full audit trail with reason codes, source attribution, and one-click revert

### 2.3 Supply Planning (MPS/MRP)

Three-step AWS SC planning process:

1. **Demand processing**: Aggregate demand from forecasts and customer orders, net out committed inventory, time-phase across planning horizon
2. **Inventory target calculation**: Safety stock using 4 policy types (absolute level, days-of-coverage demand-based, days-of-coverage forecast-based, service level), with hierarchical overrides (Product-Site > Product > Site > Config)
3. **Net requirements calculation**: Time-phased netting, multi-level BOM explosion, sourcing rule processing (buy/transfer/manufacture with priorities), lead time offsetting, supply plan generation (PO/TO/MO)

### 2.4 Inventory Optimization

- **4 standard safety stock policies** plus a fitted distribution policy (`sl_fitted`) that uses Monte Carlo simulation when demand/lead time distributions are non-Normal
- **Hierarchical overrides**: 6-level InvPolicy, 5-level VendorLeadTime, 3-level SourcingRules
- **Distribution fitting**: Maximum likelihood estimation across 20 distribution types (Normal, Lognormal, Gamma, Weibull, Beta, Exponential, Triangular, Mixture, etc.) with Kolmogorov-Smirnov testing and AIC/BIC model selection
- **Conformal prediction**: Distribution-free prediction intervals with formal coverage guarantees — if we promise "90% coverage," actual coverage will be ≥90%

### 2.5 Capacity Planning

- Resource utilization analysis with color-coded thresholds (green <80%, amber 80-90%, red 90%+)
- Bottleneck identification and throughput analysis
- Rough-cut capacity checks for MPS feasibility
- Per-tier capacity metrics (throughput, quality, on-time delivery)

### 2.6 Order Management

Six order types (PO, TO, MO, Project, Maintenance, Turnaround) with full lifecycle management:

- **Status flow**: Draft → Submitted → Approved → Sent → Acknowledged → Confirmed → Shipped → Received → Closed
- **PO acknowledgment and goods receipt**: Supplier confirmation, partial receive support, quality inspection with reason codes, variance tracking
- **Unified dashboard**: Single view combining all order types with KPI cards, search/filter, CSV export, vendor scorecard
- **ATP/CTP promising**: Available-to-Promise and Capable-to-Promise with multi-level BOM explosion and time-phased projections

---

## 3. AI Decision Architecture (Adaptive Decision Hierarchy)

The ADH organizes decision-making into three tiers that operate at different time scales, with each tier producing parameters that constrain the tier below it.

### 3.1 Strategic Tier: S&OP GraphSAGE

- **Time scale**: Weekly/monthly updates
- **Function**: Network structure analysis, risk scoring, bottleneck detection, safety stock positioning
- **Outputs**: Criticality scores, concentration risk, resilience scores, safety stock multipliers — these become policy parameters (θ) for the operational tier
- **Architecture**: GraphSAGE with neighbor sampling, scalable to 50+ node networks with O(edges) complexity

### 3.2 Operational Tier: Execution tGNN

- **Time scale**: Daily updates
- **Function**: Generates priority allocations across Product × Location, provides context for execution agents
- **Inputs**: Strategic embeddings + transactional data (orders, shipments, inventory)
- **Outputs**: Priority × Product × Location allocations fed to each site as a directive
- **Architecture**: Temporal GNN (GAT + GRU) consuming strategic structural embeddings

### 3.3 Execution Tier: 11 Narrow Decision Agents (TRM)

Each site operates 11 specialized Tiny Recursive Models (7M parameters, <10ms inference) that handle narrow execution decisions:

| Agent | Scope | Decision |
|-------|-------|----------|
| **ATP Executor** | Per order | Priority-aware Available-to-Promise allocation |
| **PO Creation** | Per product-location | Purchase order timing and quantity |
| **Inventory Rebalancing** | Cross-location | Transfer recommendations |
| **Order Tracking** | Per order, continuous | Exception detection and recommended actions |
| **MO Execution** | Per production order | Release, sequence, split, expedite, defer |
| **TO Execution** | Per transfer order | Release, consolidate, expedite, defer |
| **Quality Disposition** | Per quality order | Accept, reject, rework, scrap, use-as-is |
| **Maintenance Scheduling** | Per asset/work order | Schedule, defer, expedite, outsource |
| **Subcontracting** | Per make-vs-buy decision | Internal, external, or split routing |
| **Forecast Adjustment** | Per signal | Adjust forecast direction and magnitude |
| **Inventory Buffer** | Per product-location | Buffer parameter adjustment and reoptimization |

**Key architectural properties**:
- Each agent carries a risk assessment on every decision: `P(loss > threshold)` with distribution-free guarantee via Conformal Decision Theory
- Agents within a site coordinate through a shared signal bus (urgency vectors, pheromone-based coordination)
- Agents never call across sites — all cross-site information flows through the operational tier directive or cross-authority authorization

### 3.4 Exception Handling: Hybrid Neural + LLM Architecture

For the ~5% of decisions where neural agent confidence is low (determined by conformal prediction interval width), the system escalates to an LLM-based exception handler:

- **Routing**: Conformal prediction intervals determine escalation — tight intervals accept the neural result; wide intervals trigger the exception handler
- **Exception handling**: Claude or self-hosted Qwen 3 reasons about novel situations using heuristic rules and past decision memory (RAG)
- **Constraint validation**: All exception handler proposals are validated against engine constraints (max 30% deviation from baseline)
- **Meta-learning**: Exception decisions feed back into neural agent training, gradually teaching them to handle previously-novel situations and shifting the 95/5 boundary

### 3.5 Vertical Escalation (Escalation Arbiter)

The system detects when execution-level anomalies indicate that *strategic policy parameters* are wrong, not that execution decisions need fine-tuning:

- **Persistence detection**: Monitors decision patterns for persistent directional drift — when agents consistently adjust in the same direction (e.g., always ordering 20% more than baseline), the policy is wrong
- **Intelligent routing**:
  - Single agent, short duration → horizontal retrain (fix the agent)
  - Multiple agents, same site, persistent → operational refresh (rerun the daily tGNN)
  - Multiple sites, same direction → strategic review (update policy parameters)
- **Automatic triggering**: Evaluated every 2 hours with configurable thresholds per tenant

---

## 4. Uncertainty Quantification

### 4.1 Stochastic Simulation Engine

- **20 distribution types** for modeling operational variability (demand, lead times, yields, capacity, pricing)
- **Monte Carlo simulation**: 1000+ scenarios with variance reduction (common random numbers, antithetic variates, Latin hypercube sampling)
- **Probabilistic Balanced Scorecard**: P10/P50/P90 distributions for Financial, Customer, Operational, and Strategic KPIs

### 4.2 Conformal Prediction

- **Distribution-free intervals**: Calibrated from historical Plan vs. Actual data without assuming any particular distribution shape
- **Formal coverage guarantees**: Mathematically proven that actual coverage meets or exceeds the specified level
- **Adaptive recalibration**: Automatic drift detection and recalibration when forecast accuracy degrades
- **Multi-entity support**: Demand, lead time, price, yield, and service level variables

### 4.3 Distribution Fitting and Likelihood Estimation

- **Automatic fitting**: MLE fitting across 20 distribution types per product-site combination
- **Model selection**: Kolmogorov-Smirnov goodness-of-fit, AIC/BIC ranking to select best-fitting distribution
- **Safety stock correction**: For non-Normal distributions (lognormal, Weibull, etc.), uses Monte Carlo DDLT simulation instead of z-score formula — correcting 15-30% safety stock miscalculation common with skewed distributions
- **Feature engineering**: Decision agent state vectors include fitted distribution parameters (shape, scale, skewness, kurtosis) and MAD/median ratios instead of mean/std

---

## 5. Digital Twin and Simulation

### 5.1 Supply Chain Digital Twin

The platform includes a complete simulation environment that uses identical planning logic, AI agents, and cost calculations as production. The only differences are time (fast-forward) and demand (synthetic or historical).

- **Policy testing**: Change safety stock levels, sourcing rules, reorder points — see downstream impact across every node with statistical confidence
- **Network redesign**: Add/remove sites, change suppliers, modify capacity — run hundreds of demand scenarios
- **Strategy comparison**: Compare current ordering approach against optimized alternatives across 500+ simulated weeks
- **Git-like plan versioning**: Branch/merge workflow for plan changes with full history, diff, and revert

### 5.2 Five-Phase Agent Training Pipeline

Takes AI agents from zero experience to production autonomy in 3-5 weeks:

1. **Behavioral Cloning** (hours): Each agent matches the deterministic engine baseline within ±5%
2. **Coordinated Simulation** (2-3 days): All 11 agents train simultaneously with signal bus active, learning inter-agent coordination from 28.6M+ training records
3. **Stochastic Stress-Testing** (hours): Agents face adversarial scenarios — 3σ demand spikes, supplier failures, capacity shocks, compound disruptions
4. **Copilot Calibration** (2-4 weeks): Agents run in copilot mode with human overrides captured and weighted by Bayesian effectiveness tracking
5. **Autonomous Relearning** (ongoing): Continuous improvement from production outcomes via autonomous feedback loop

### 5.3 Interactive Simulation (Beer Game Module)

Multi-echelon supply chain simulation for training, validation, and confidence-building:

- **Multi-user**: 2-8 participants in real-time WebSocket scenarios
- **Mixed Human-AI**: Humans compete alongside or against AI agents
- **Multiple strategies**: Naive, Conservative, Bullwhip, ML-Forecast, Optimizer, Reactive, LLM-powered
- **Confidence metrics**: Win rate, cost differential, consistency, explainability, acceptance rate

---

## 6. Cross-Functional Coordination

### 6.1 Agentic Authorization Protocol (AAP)

When an AI agent identifies an action that crosses functional boundaries (e.g., a supply agent wanting to override an allocation owned by distribution), it follows a structured protocol:

- **Three-phase process**: Evaluate (run what-if on all options), Request (send authorization with full scorecard impact), Authorize (target checks resource availability)
- **Authority boundaries**: Each agent type has unilateral, requires-authorization, and forbidden action categories
- **Net benefit threshold**: Configurable threshold controls agent autonomy — above threshold = auto-resolve, near threshold = human reviews, below = reject
- **25+ negotiation scenarios**: Manufacturing, distribution, channel allocation, procurement, logistics, finance, S&OP

### 6.2 Collaboration and Approval Workflows

- **Team messaging**: Channel-based messaging with threading, @mentions, read tracking
- **Inline comments**: Comment on purchase orders, transfer orders, supply plans, recommendations
- **Approval workflows**: Configurable single-level, multi-level, and matrix approval
- **Activity feed**: Chronological feed of all planning actions with user attribution
- **Notification system**: Configurable per-user preferences, digest emails, quiet hours, multi-channel delivery

### 6.3 Override Effectiveness Tracking

Human overrides are tracked and scored using Bayesian Beta posteriors:

- **Per-user, per-decision-type tracking**: Each override builds a statistical record of whether that person's overrides improve or worsen outcomes
- **Systemic impact measurement**: Overrides measured at both decision-local and site-window scope to prevent locally-good but systemically-harmful overrides
- **Training weight adjustment**: Override quality directly influences how much weight that user's decisions carry in future agent training
- **Causal learning pipeline**: Progresses from Bayesian priors through propensity-score matching to causal forests

---

## 7. Insights, Risk, and Explainability

### 7.1 Risk Detection and Analytics

- **ML-powered risk detection**: Stock-out and overstock risk identification with probabilistic scoring (0-100)
- **Predictive analytics**: Stock-out probability forecasts at 7/14/30/90-day horizons, lead time prediction with confidence intervals
- **Customizable watchlists**: Critical product monitoring with multi-dimensional filters and alert escalation rules
- **N-tier network visibility**: Multi-echelon visualization with inventory flow, capacity analysis, and per-tier risk assessment

### 7.2 Context-Aware Explainability

Every decision from all 11 execution agents and both network models supports multi-level explanation:

- **Authority boundaries**: What the agent is and isn't allowed to do
- **Active guardrails**: Which guardrails were checked and whether any constrained the decision
- **Model attribution**: Gradient saliency for neural agents, attention weights for graph models
- **Conformal intervals**: The uncertainty range for this specific decision
- **Counterfactual analysis**: "What would have happened if..."
- **Three verbosity levels**: Succinct (one line), Normal (key factors), Verbose (full analysis)

### 7.3 Executive Strategy Briefing

LLM-synthesized briefings that summarize system state, decisions, and recommendations for executive review with follow-up Q&A capability.

---

## 8. Integration and Deployment

### 8.1 SAP Integration

- **Connection types**: S/4HANA, APO, ECC, BW via RFC, CSV, or OData
- **Z-Table/Z-Field handling**: AI-powered fuzzy matching for custom SAP tables and fields
- **Field mapping**: Automatic and manual mapping of SAP fields to AWS SC entities
- **Data ingestion monitoring**: Real-time job tracking, quality metrics, anomaly detection
- **Bidirectional flow**: Import master data and actuals from SAP; export AI recommendations back

### 8.2 Synthetic Data Generation

AI-guided wizard for generating complete synthetic supply chain data for rapid deployment and testing:

- **Three archetypes**: Retailer (61 sites, 200 SKUs), Distributor (34 sites, 720 SKUs), Manufacturer (31 sites, 160 SKUs)
- **Complete generation**: Tenant, admin user, supply chain config, sites, lanes, products, hierarchies, forecasts, inventory policies, planning configurations, agent configurations

### 8.3 Deployment Options

- **Containerized**: Docker Compose stack (proxy, frontend, backend, database)
- **GPU support**: NVIDIA CUDA for ML training with automatic CPU fallback
- **Self-hosted LLM**: Qwen 3 8B via vLLM for air-gapped deployments (96.5% tool calling accuracy)
- **Production mode**: Gunicorn with Nginx reverse proxy

---

## 9. User Interface

### 9.1 Planning Pages (43+ pages)

Master Production Scheduling, Demand Plan View/Edit, Supply Plan Generation, Inventory Optimization, Capacity Planning, S&OP, ATP/Rebalancing/PO/Order Tracking worklists, Lot Sizing, and execution pages.

### 9.2 Administration Pages (25+ pages)

TRM Dashboard, GNN Dashboard, GraphSAGE Dashboard, Hive Dashboard, ADH Dashboard, RL/RLHF Dashboards, Knowledge Base, Signal Ingestion, Edge Security, SAP Data Management, Synthetic Data Wizard, Model Setup, User/Role/Tenant Management, Authorization Protocol Board, Governance, Exception Workflows, Approval Templates.

### 9.3 LLM-First Interaction

Natural language interface for planners to query system state, review agent actions, and interact with recommendations without needing to navigate complex ERP-style screens.

### 9.4 AIIO Decision Framework

The user interface implements **Automate-Inform-Inspect-Override**:

- **Automate**: Routine decisions execute within guardrails. Planners configure maximum bounds.
- **Inform**: Daily digest of auto-executed actions. No pop-ups — review at your pace.
- **Inspect**: Structured recommendations with drill-down, data grounding, plain-language explanation, side-by-side scenario comparison.
- **Override**: When overriding, planners provide context (reason category, explanation, supporting files). This context becomes training data.

**Measured progression**: ~45% auto-execute rate in week 1 → ~72% by week 12 → ~85% at steady state.

---

## 10. Performance and Scalability

| Metric | Value |
|--------|-------|
| Event processing capacity | 100,000 events/day |
| Agent task capacity | 50,000 tasks/day |
| TRM inference latency | <10ms per decision |
| GNN inference latency | 50-100ms per graph pass |
| P0 event response | <1 minute |
| Storage (1 year) | ~83 GB |
| AWS SC entity compliance | 100% (35/35) |
| Frontend pages | 96+ |
| TRM agent accuracy | 90-95% vs optimal |
| GNN demand prediction | 85-92% accuracy |
| Cost reduction vs naive | 20-35% |

---

*For detailed technical architecture, see [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md). For AI agent specifications, see [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md). For the decision hierarchy framework, see [POWELL_APPROACH.md](POWELL_APPROACH.md).*

![Azirella](../Azirella_Logo.jpg)

> **STRICTLY CONFIDENTIAL AND PROPRIETARY**
> Copyright © 2026 Azirella Ltd. All rights reserved worldwide.
> Unauthorized access, use, reproduction, or distribution of this document or any portion thereof is strictly prohibited and may result in severe civil and criminal penalties.

# Autonomy Platform: Functional Capabilities

**Version**: 1.1
**Date**: March 2, 2026

---

## 1. Platform Overview

Autonomy is an enterprise supply chain planning and execution platform built on four pillars: **AI agents** (three-tier decision-making at millisecond to weekly cadences), **causal AI** (counterfactual reasoning that determines which decisions actually caused positive outcomes — making the learning loop trustworthy), **conformal prediction** (distribution-free uncertainty guarantees on every agent decision, powered by stochastic simulation data), and **digital twin** (complete stochastic simulation that generates training data, calibration sets, and risk-free testing for everything else).

The platform is built on the AWS Supply Chain data model (100% compliant, 35/35 entities) and uses what we call the **Adaptive Decision Hierarchy (ADH)** — a layered architecture where strategic, operational, and execution decisions are made at appropriate time scales by appropriate models, with intelligent escalation between layers.

> **Screenshot 1 — Executive Dashboard**
> *Navigation: Insights & Analytics > Executive Dashboard*
> Shows the role-adaptive landing page with strategic KPIs, performance summary, and AI agent activity overview.

---

## 2. Planning Capabilities

### 2.1 Event-Driven Continuous Planning

The system replans only affected products and locations when events occur, rather than running full batch recalculations on a weekly cadence.

- **Event sources**: Supplier delays, demand spikes, capacity changes, forecast updates, order exceptions
- **Response latency**: P0 critical events addressed in under 1 minute; P1 in under 5 minutes
- **Incremental replanning**: Only affected SKU-location combinations are recalculated
- **Guardrailed autonomy**: Routine decisions auto-execute within configurable bounds (max PO value, max safety stock change, min service level floor); exceptions escalate to planners
- **Urgency + likelihood prioritization**: Every decision is scored on urgency (how time-sensitive?) and likelihood (how confident is the agent?). The Decision Stream surfaces high-urgency/low-likelihood decisions at the top — exactly where human expertise adds the most value. Low-urgency/low-likelihood decisions are abandoned automatically. High-likelihood decisions (regardless of urgency) execute autonomously.

> **Screenshot 2 — MPS Worklist (Exception-Driven Planning)**
> *Navigation: Insights & Analytics > MPS Worklist*
> Shows the prioritized exception worklist — the "14 items instead of 847" experience. Each item shows what happened, what the system recommends, why, and what happens if you do nothing.

### 2.2 Demand Planning

- **Forecast management**: View, edit, import/export demand plans with P10/P50/P90 confidence intervals
- **Consensus planning**: Multi-stakeholder forecast cycles (sales, marketing, finance, operations, statistical) with voting and approval workflows
- **CPFR collaboration**: Trading partner forecast sharing with exception detection (>20% variance threshold) and accuracy tracking per partner
- **ML forecast pipeline**: Configurable pipeline with 30+ parameters, clustering-based statistical forecasting
- **Version comparison**: Side-by-side comparison of any two forecast versions with delta analysis
- **Forecast adjustment history**: Full audit trail with reason codes, source attribution, and one-click revert

> **Screenshot 3 — Demand Plan View**
> *Navigation: Planning > Demand Planning*
> Shows the demand plan grid with P10/P50/P90 confidence intervals per product-location-period. Filter by product family, location, date range.

> **Screenshot 4 — Consensus Planning**
> *Navigation: Planning > Consensus Planning*
> Shows multi-stakeholder forecast cycle with submissions from sales, marketing, finance, operations. Voting mechanism and progress tracking.

### 2.3 Supply Planning (MPS/MRP)

Three-step AWS SC planning process:

1. **Demand processing**: Aggregate demand from forecasts and customer orders, net out committed inventory, time-phase across planning horizon
2. **Inventory target calculation**: Safety stock using 4 policy types (absolute level, days-of-coverage demand-based, days-of-coverage forecast-based, service level), with hierarchical overrides (Product-Site > Product > Site > Config)
3. **Net requirements calculation**: Time-phased netting, multi-level BOM explosion, sourcing rule processing (buy/transfer/manufacture with priorities), lead time offsetting, supply plan generation (PO/TO/MO)

> **Screenshot 5 — Master Production Schedule**
> *Navigation: Planning > Master Production Schedule*
> Shows the MPS plan with time-phased production quantities, frozen horizon, and approval workflow status.

### 2.4 Inventory Optimization

- **4 standard safety stock policies** plus a fitted distribution policy (`sl_fitted`) that uses Monte Carlo simulation when demand/lead time distributions are non-Normal
- **Hierarchical overrides**: 6-level InvPolicy, 5-level VendorLeadTime, 3-level SourcingRules
- **Distribution fitting**: Maximum likelihood estimation across 20 distribution types (Normal, Lognormal, Gamma, Weibull, Beta, Exponential, Triangular, Mixture, etc.) with Kolmogorov-Smirnov testing and AIC/BIC model selection
- **Conformal prediction**: Distribution-free prediction intervals with formal coverage guarantees — if we promise "90% coverage," actual coverage will be ≥90%

> **Screenshot 6 — Inventory Optimization**
> *Navigation: Planning > Inventory Optimization*
> Shows safety stock policy configuration with hierarchical overrides. The 4 policy types and their parameters are visible per product-site combination.

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

> **Screenshot 7 — Unified Order Dashboard**
> *Navigation: Execution > Order Management*
> Shows all order types (PO/TO/MO) in a single view with 8 KPI summary cards, status filters, timeline visualization, and vendor scorecard.

---

## 3. AI Decision Architecture (Adaptive Decision Hierarchy)

The ADH organizes decision-making into three tiers that operate at different time scales, with each tier producing parameters that constrain the tier below it.

> **Screenshot 8 — Decision Cascade Overview**
> *Navigation: AI & Agents > Decision Cascade*
> Shows the three-tier architecture: Strategic (S&OP GraphSAGE) → Operational (Execution tGNN) → Execution (11 TRM agents). Includes state → policy → decision → outcome pipeline visualization.

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

> **Screenshot 9 — ATP Worklist (Agent-in-the-Loop)**
> *Navigation: Planning Cascade > ATP Worklist*
> Shows agent-generated ATP decisions with the Automate-Inform-Inspect-Override pattern: each decision shows the agent's recommendation, confidence score, reasoning, and Accept/Override buttons with reason capture.

### 3.4 Exception Handling: Hybrid Neural + LLM Architecture

For the ~5% of decisions where neural agent confidence is low (determined by conformal prediction interval width), the system escalates to an LLM-based exception handler:

- **Routing**: Conformal prediction intervals determine escalation — tight intervals accept the neural result; wide intervals trigger the exception handler
- **Exception handling**: Claude or self-hosted Qwen 3 reasons about novel situations using heuristic rules and past decision memory (RAG)
- **Constraint validation**: All exception handler proposals are validated against engine constraints (max 30% deviation from baseline)
- **Meta-learning**: Exception decisions feed back into neural agent training, gradually teaching them to handle previously-novel situations and shifting the 95/5 boundary

> **Screenshot 10 — Claude Skills Monitor**
> *Navigation: AI & Agents > Claude Skills*
> Shows exception escalation rates, RAG memory cache hit ratios, LLM call costs, and decision outcomes for the ~5% of decisions handled by the LLM exception path.

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

> **Screenshot 11 — Uncertainty Quantification**
> *Navigation: Insights & Analytics > Uncertainty Quantification*
> Shows side-by-side stochastic vs. deterministic analysis with Monte Carlo simulation results, cost distribution (P10/P50/P90), and service level probability charts.

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

> **Screenshot 12 — Network Topology (Sankey Diagram)**
> *Navigation: Administration > Supply Chain Configuration > (select a config) > Sankey tab*
> Shows the DAG-based supply chain network visualization with material flow between sites. Useful for showing how the digital twin mirrors the real network.

### 5.2 Six-Phase Agent Training Pipeline

Takes AI agents from zero experience to production autonomy in 3-5 weeks:

1. **Behavioral Cloning** (hours): Each agent matches the deterministic engine baseline within ±5%
2. **Coordinated Simulation** (2-3 days): All 11 agents train simultaneously with signal bus active, learning inter-agent coordination from 28.6M+ training records
3. **Site Coordination Model Training** (~1 day): Cross-agent coordination model learns causal relationships from coordinated traces, then fine-tunes via reinforcement learning
4. **Stochastic Stress-Testing** (3-5 days): Agents + site coordination model together face adversarial scenarios — 3σ demand spikes, supplier failures, capacity shocks, compound disruptions
5. **Copilot Calibration** (2-4 weeks): Agents run in copilot mode with human overrides captured and weighted by Bayesian effectiveness tracking
6. **Autonomous Relearning** (ongoing): Continuous improvement from production outcomes via autonomous feedback loop

> **Screenshot 13 — TRM Training Dashboard**
> *Navigation: AI & Agents > Execution Agents*
> Shows the TRM training interface with curriculum phase selection, real-time loss charts, model manager, and testing tab with predefined scenarios.

### 5.3 Interactive Simulation (Beer Game Module)

Multi-echelon supply chain simulation for training, validation, and confidence-building:

- **Multi-user**: 2-8 participants in real-time WebSocket scenarios
- **Mixed Human-AI**: Humans compete alongside or against AI agents
- **Multiple strategies**: Naive, Conservative, Bullwhip, ML-Forecast, Optimizer, Reactive, LLM-powered
- **Confidence metrics**: Win rate, cost differential, consistency, explainability, acceptance rate

> **Screenshot 14 — Scenario Board (Human vs AI)**
> *Navigation: Scenarios > (open an active scenario)*
> Shows the real-time scenario board with inventory levels, order quantities, cost tracking, and bullwhip visualization. Human and AI decisions side by side.

---

## 6. Cross-Functional Coordination

### 6.1 Agentic Authorization Protocol (AAP)

When an AI agent identifies an action that crosses functional boundaries (e.g., a supply agent wanting to override an allocation owned by distribution), it follows a structured protocol:

- **Three-phase process**: Evaluate (run what-if on all options), Request (send authorization with full scorecard impact), Authorize (target checks resource availability)
- **Authority boundaries**: Each agent type has unilateral, requires-authorization, and forbidden action categories
- **Net benefit threshold**: Configurable threshold controls agent autonomy — above threshold = auto-resolve, near threshold = human reviews, below = reject
- **25+ negotiation scenarios**: Manufacturing, distribution, channel allocation, procurement, logistics, finance, S&OP

### 6.2 Talk to Me — Natural Language Directive Capture

A persistent AI prompt bar in the top navigation accepts natural language directives from any authenticated user. The system parses directives with an LLM, detects missing information via a smart clarification flow, and routes the completed directive to the appropriate Powell Cascade layer based on the user's role.

- **Two-phase flow**: Analyze (LLM parse + gap detection) → Clarify (missing field questions) → Submit (with clarifications merged)
- **Required fields**: Reason/justification (always required), direction, metric, magnitude, duration, geography, products
- **Role-based routing**: VP/Executive → S&OP GraphSAGE (Layer 4), S&OP Director → Execution tGNN (Layer 2), MPS Manager → Site tGNN (Layer 1.5), Analysts → Individual TRM (Layer 1)
- **Confidence-gated auto-apply**: ≥0.7 confidence auto-routed; below that, held for human review
- **Effectiveness tracking**: Bayesian posteriors per (user, directive type) measure whether directives actually improve outcomes

> **Screenshot 15a — Talk to Me Directive Bar**
> *Navigation: Always visible in top navigation bar*
> Shows the persistent "Talk to me..." input bar. When a directive is analyzed, a clarification panel appears with targeted questions for any missing fields.

### 6.3 Email Signal Intelligence — Automated External Signal Ingestion

GDPR-safe email ingestion that monitors customer and supplier inboxes, extracts supply chain signals, and routes them to appropriate TRM agents for action.

- **IMAP/Gmail inbox monitoring**: Configurable connections with domain allowlist/blocklist filtering
- **GDPR by design**: Personal identifiers stripped before persistence (names, emails, phones, addresses, signatures). Only the sending company is identified via domain→TradingPartner resolution. Original email never stored.
- **12 signal types**: demand_increase, demand_decrease, supply_disruption, lead_time_change, price_change, quality_issue, new_product, discontinuation, order_exception, capacity_change, regulatory, general_inquiry
- **LLM classification**: Haiku tier (~$0.0018/call) extracts signal type, direction, magnitude, urgency, confidence, product/site references
- **Automatic TRM routing**: High-confidence signals (≥0.6) auto-routed to primary TRM (e.g., demand signals → Forecast Adjustment, supply disruptions → PO Creation)
- **Heuristic fallback**: Keyword-based classification when LLM unavailable (air-gapped deployments)
- **4-tab admin dashboard**: Signals (table with expand/dismiss), Connections (IMAP config), Analytics (breakdowns), Test Ingestion (paste email to test pipeline)

> **Screenshot 15b — Email Signals Dashboard**
> *Navigation: Administration > Email Signals*
> Shows the 4-tab dashboard with classified signals, connection management, analytics breakdowns, and test ingestion interface.

### 6.4 Collaboration and Approval Workflows

- **Team messaging**: Channel-based messaging with threading, @mentions, read tracking
- **Inline comments**: Comment on purchase orders, transfer orders, supply plans, recommendations
- **Approval workflows**: Configurable single-level, multi-level, and matrix approval
- **Activity feed**: Chronological feed of all planning actions with user attribution
- **Notification system**: Configurable per-user preferences, digest emails, quiet hours, multi-channel delivery

> **Screenshot 16 — Collaboration Hub**
> *Navigation: Planning > Collaboration Hub*
> Shows team messaging with threaded conversations, @mentions, inline comments on orders/plans, and activity feed.

### 6.5 Causal AI — Decision Outcome Attribution

Determining whether an AI decision actually caused a positive outcome — not just correlated with one — is the foundational challenge of any learning system. The platform implements a full causal inference pipeline:

- **Counterfactual computation**: For every overridden decision, computes what the agent's original recommendation would have earned given the actual environment. Example: agent recommended 80 units, human chose 100, actual demand was 90 → agent fill rate 88.9%, human 100%, treatment effect +11.1%.
- **Three-tier causal inference**: Analytical counterfactuals (ATP, Forecast, Quality — full signal), propensity-score matching (MO, TO, PO — statistical controls), Bayesian priors (Inventory Buffer, Maintenance — slow accumulation from long feedback delays)
- **Systemic impact measurement**: Overrides measured at both decision-local scope (did this specific override help?) and site-window balanced scorecard scope (did it improve the broader site?). Composite: 40% local + 60% systemic — prevents locally-good but systemically-harmful overrides.
- **Bayesian training weight adjustment**: Each (user, decision type) pair carries a Beta(α, β) posterior. Override quality directly influences how much weight that user's decision patterns carry in future agent training.
- **Conformal Decision Theory**: Every TRM decision carries a calibrated risk bound P(loss > threshold) — a distribution-free guarantee derived from historical decision-outcome pairs. Governs autonomous execution vs. human escalation.
- **Causal learning progression**: Bayesian priors → propensity-score matching → doubly robust estimation → causal forests (Athey & Imbens 2018) that identify *when* overrides help vs. hurt

**Why this is a pillar, not a feature**: Without causal inference, the learning loop trains on correlation — agents learn what happened to coincide with good outcomes. With causal inference, agents learn what actually *caused* good outcomes. This is the difference between a system that degrades when conditions change and one that generalizes.

---

## 7. Insights, Risk, and Explainability

### 7.1 Risk Detection and Analytics

- **ML-powered risk detection**: Stock-out and overstock risk identification with probabilistic scoring (0-100)
- **Predictive analytics**: Stock-out probability forecasts at 7/14/30/90-day horizons, lead time prediction with confidence intervals
- **Customizable watchlists**: Critical product monitoring with multi-dimensional filters and alert escalation rules
- **N-tier network visibility**: Multi-echelon visualization with inventory flow, capacity analysis, and per-tier risk assessment

> **Screenshot 16 — N-Tier Network Visibility**
> *Navigation: Execution > N-Tier Visibility*
> Shows multi-echelon supply chain view with per-tier inventory flow, capacity utilization bars, risk scores (0-100), and mitigation action table.

> **Screenshot 17 — Risk Analysis**
> *Navigation: Insights & Analytics > Risk Analysis*
> Shows risk detection dashboard with stock-out/overstock risk scoring, watchlists, and predictive analytics charts.

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

> **Screenshot 18 — Strategy Briefing**
> *Navigation: Insights & Analytics > Strategy Briefing*
> Shows AI-generated executive briefing with key metrics, trend analysis, risk alerts, and follow-up Q&A interface.

---

## 8. Integration and Deployment

### 8.1 SAP Integration

- **Connection types**: S/4HANA, APO, ECC, BW via RFC, CSV, or OData
- **Z-Table/Z-Field handling**: AI-powered fuzzy matching for custom SAP tables and fields
- **Field mapping**: Automatic and manual mapping of SAP fields to AWS SC entities
- **Data ingestion monitoring**: Real-time job tracking, quality metrics, anomaly detection
- **Bidirectional flow**: Import master data and actuals from SAP; export AI recommendations back

> **Screenshot 19 — SAP Data Management**
> *Navigation: Administration > SAP Data Management*
> Shows SAP connection configuration, field mapping interface, ingestion job monitoring, and AI-powered insights.

### 8.2 Synthetic Data Generation

AI-guided wizard for generating complete synthetic supply chain data for rapid deployment and testing:

- **Three archetypes**: Retailer (61 sites, 200 SKUs), Distributor (34 sites, 720 SKUs), Manufacturer (31 sites, 160 SKUs)
- **Complete generation**: Tenant, admin user, supply chain config, sites, lanes, products, hierarchies, forecasts, inventory policies, planning configurations, agent configurations

> **Screenshot 20 — Synthetic Data Wizard**
> *Navigation: Administration > Synthetic Data Wizard*
> Shows the AI-guided setup wizard with archetype selection, network configuration, and generation progress.

### 8.3 Deployment Options

- **Containerized**: Docker Compose stack (proxy, frontend, backend, database)
- **GPU support**: NVIDIA CUDA for ML training with automatic CPU fallback
- **Self-hosted LLM**: Qwen 3 8B via vLLM for air-gapped deployments (96.5% tool calling accuracy)
- **Production mode**: Gunicorn with Nginx reverse proxy

---

## 9. The AIIO Decision Framework

The user interface implements **Automate-Inform-Inspect-Override** across all planning and execution workflows:

- **Automate**: Routine decisions execute within guardrails. Planners configure maximum bounds (max PO value, max safety stock change, min service level floor, cost increase ceiling).
- **Inform**: Daily digest of auto-executed actions. No pop-ups — review at your pace. Each action logged with full reasoning.
- **Inspect**: Structured recommendations with drill-down into reasoning, underlying data, alternative scenarios, and plain-language explanation accessible to non-technical stakeholders.
- **Override**: When overriding, planners provide context — reason category, free-text explanation, supporting files. This context becomes training data. The system learns not just *that* you disagreed, but *why*.

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

## Screenshot Capture Guide

To complete this document, capture the following 20 screenshots. Login as `systemadmin@autonomy.ai` (password: `Autonomy@2026`) at `http://localhost:8088`.

| # | Screen | Navigation Path |
|---|--------|----------------|
| 1 | Executive Dashboard | Insights & Analytics > Executive Dashboard |
| 2 | MPS Worklist | Insights & Analytics > MPS Worklist |
| 3 | Demand Plan View | Planning > Demand Planning |
| 4 | Consensus Planning | Planning > Consensus Planning |
| 5 | Master Production Schedule | Planning > Master Production Schedule |
| 6 | Inventory Optimization | Planning > Inventory Optimization |
| 7 | Order Management | Execution > Order Management |
| 8 | Decision Cascade (ADH) | AI & Agents > Decision Cascade |
| 9 | ATP Worklist | Planning Cascade > ATP Worklist |
| 10 | Claude Skills Monitor | AI & Agents > Claude Skills |
| 11 | Uncertainty Quantification | Insights & Analytics > Uncertainty Quantification |
| 12 | Network Topology | Administration > Supply Chain Configuration > (select config) > Sankey |
| 13 | TRM Training Dashboard | AI & Agents > Execution Agents |
| 14 | Scenario Board | Scenarios > (open active scenario) |
| 15 | Collaboration Hub | Planning > Collaboration Hub |
| 16 | N-Tier Visibility | Execution > N-Tier Visibility |
| 17 | Risk Analysis | Insights & Analytics > Risk Analysis |
| 18 | Strategy Briefing | Insights & Analytics > Strategy Briefing |
| 19 | SAP Data Management | Administration > SAP Data Management |
| 20 | Synthetic Data Wizard | Administration > Synthetic Data Wizard |

**Tip**: For the best screenshots, ensure you have a supply chain config loaded with data (run `make db-bootstrap` if needed). The Synthetic Data Wizard can generate a full manufacturer dataset for rich visuals.

---

*For detailed technical architecture, see [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md). For AI agent specifications, see [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md).*

---


---

![Azirella](../Azirella_Logo.jpg)

> **Copyright © 2026 Azirella Ltd. All rights reserved worldwide.**
> This document and all information contained herein are the exclusive confidential and proprietary property of Azirella Ltd, 27, 25 Martiou St., #105, 2408 Engomi, Nicosia, Cyprus. No part of this document may be reproduced, stored in a retrieval system, transmitted, distributed, or disclosed in any form or by any means — electronic, mechanical, photocopying, recording, or otherwise — without the prior express written consent of Azirella Ltd. Any unauthorized use constitutes a violation of applicable intellectual property laws and may be subject to legal action.

# CLAUDE_REFERENCE.md

Detailed architecture, workflows, and reference material extracted from CLAUDE.md.
Claude Code reads this file on-demand, not on every message — keeping CLAUDE.md lean.

---

## Project Overview — Four Pillars

**Autonomy Platform — Decision Intelligence for Supply Chain** - Enterprise-grade supply chain planning and execution compatible with AWS Supply Chain standards, built on four pillars:

### Core: AWS Supply Chain Compliance

**Primary Focus**: Professional supply chain planning and execution following AWS SC data model and workflows

**Key Capabilities**:
- **Demand Planning**: Statistical and ML forecasting, consensus planning, supplementary time series
- **Supply Planning**: Net requirements calculation, multi-level BOM explosion, multi-sourcing with priorities
- **Master Production Scheduling (MPS)**: Strategic production planning with rough-cut capacity checks
- **Material Requirements Planning (MRP)**: Detailed component requirements from MPS
- **Inventory Optimization**: 8 policy types (abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal), hierarchical overrides
- **Capacity Planning**: Resource utilization analysis, bottleneck identification
- **Order Management**: Inbound/outbound orders, shipment tracking, fulfillment
- **Network Design**: DAG-based supply chain topology (35 AWS SC entities)

**AWS SC Compliance**: 100% (35/35 entities implemented). See [AWS_SC_IMPLEMENTATION_STATUS.md](internal/AWS_SC_IMPLEMENTATION_STATUS.md).

**AWS SC References**:
- **Features**: https://aws.amazon.com/aws-supply-chain/features/
- **Resources**: https://aws.amazon.com/aws-supply-chain/resources/

### Pillar #1: AI Agents (Automated Planners)

**Purpose**: Replace or assist human planners with AI agents that achieve 20-35% cost reduction vs naive policies.

**Three-Tier AI Architecture** (Powell Framework):

```
S&OP GraphSAGE (CFA - Cost Function Approximation)
    ↓ policy parameters θ (weekly/monthly)
Execution tGNN (CFA/VFA - Generates allocations)
    ↓ priority allocations + context (daily)
Narrow TRMs (VFA - Value Function Approximation)
    └── 11 Engine-TRM pairs: ATP, Rebalancing, PO, OrderTracking,
        MO Execution, TO Execution, Quality, Maintenance,
        Subcontracting, Forecast Adjustment, Safety Stock
```

**Agent Types**:

1. **Narrow TRM Agents** (Tiny Recursive Model) - Execution Level
   - 7M parameters, 2-layer transformer with 3-step recursive refinement
   - <10ms inference time (100+ decisions/second)
   - 90-95% accuracy vs optimal policies
   - **Research Foundation**: Architecture inspired by Samsung SAIL Montreal's TRM ([arxiv:2510.04871](https://arxiv.org/abs/2510.04871)). See [TRM_RESEARCH_SYNTHESIS.md](../TRM_RESEARCH_SYNTHESIS.md).
   - **Architecture Principles** (from Samsung TRM research):
     - Recursion multiplies compute without multiplying parameters
     - Post-normalization essential for recursion stability
     - Full backpropagation through all recursive steps
     - Deep supervision at each refinement step
     - Fewer parameters → better generalization
   - **11 TRM Agents**:
     - **ATPExecutorTRM**: Allocated Available-to-Promise with priority consumption
     - **InventoryRebalancingTRM**: Cross-location transfer decisions
     - **POCreationTRM**: Purchase order timing and quantity
     - **OrderTrackingTRM**: Exception detection and recommended actions
     - **MOExecutionTRM**: Manufacturing order release, sequencing (Glenday Sieve + nearest-neighbor), expedite
     - **TOExecutionTRM**: Transfer order release, consolidation, expedite
     - **QualityDispositionTRM**: Quality hold/release/rework/scrap decisions
     - **MaintenanceSchedulingTRM**: Preventive maintenance scheduling and deferral
     - **SubcontractingTRM**: Make-vs-buy and external manufacturing routing
     - **ForecastAdjustmentTRM**: Signal-driven forecast adjustments (email, voice, market intel)
     - **InventoryBufferTRM**: Inventory buffer parameter adjustment and reoptimization
   - TRM does NOT do: long-term planning, network-wide optimization, policy parameters
   - **Training**: BC warm-start → RL/VFA fine-tuning → CGAR curriculum → 50K samples/sub-phase
   - **CDC → Relearning Loop**: `cdc_monitor.py`, `outcome_collector.py`, `cdt_calibration_service.py`, `cdc_retraining_service.py`, `relearning_jobs.py`, `condition_monitor_service.py`
   - **Conformal Decision Theory (CDT)**: All 11 TRM agents carry `risk_bound` and `risk_assessment` on every decision.

2. **GNN Agent** (Graph Neural Network) - Three-Tier Architecture
   - **S&OP GraphSAGE** (Medium-Term): Network structure analysis, risk scoring, bottleneck detection. Powell CFA.
   - **Execution tGNN** (Short-Term): Generates priority allocations. Powell CFA/VFA bridge.
   - **Site tGNN** (Intra-Site): 11 TRM-type nodes, GATv2+GRU, ~25K params, <5ms, hourly.

3. **LLM Agent** (Multi-Agent Orchestrator): Site agents, supervisor, global planner, NL explainability.

### Pillar #2: Conformal Prediction (Distribution-Free Uncertainty Guarantees)

Every agent decision carries a calibrated likelihood guarantee. CDT risk_bound = P(loss > threshold). 8 inventory policy types. 21 distribution types. Monte Carlo with variance reduction. Probabilistic Balanced Scorecard (Financial, Customer, Operational, Strategic).

### Pillar #3: Digital Twin (Stochastic Simulation Engine)

The digital twin replicates the customer's APS as a stochastic simulation. 9 triangular distributions per entity. Agents learn by watching heuristics fail. See [DIGITAL_TWIN.md](internal/DIGITAL_TWIN.md).

**The Beer Game** (Learning Tenant): Classic multi-echelon simulation, 2-8 users, ONLY within Learning Tenant.

### Pillar #4: Causal AI (Decision Outcome Attribution)

Three-tier causal inference: Analytical Counterfactual (ATP/Forecast/Quality), Statistical Matching (MO/TO/PO), Bayesian Prior (Buffer/Maintenance/Subcontracting).

Six systems: Counterfactual Computation, Propensity-Score Matching, Bayesian Override Effectiveness, CDT, Outcome Collection Pipeline, Experiential Knowledge Layer.

---

## Detailed Architecture

### Backend Structure (`backend/app/`)

**AWS SC Planning Services** (`services/aws_sc_planning/`):
- `planner.py`: Main AWS SC 3-step orchestrator (demand → targets → requirements)
- `demand_processor.py`: Step 1 - Demand processing and aggregation
- `inventory_target_calculator.py`: Step 2 - Safety stock and target calculation (8 policy types)
- `net_requirements_calculator.py`: Step 3 - Time-phased netting, BOM explosion, supply plan generation
- `stochastic_sampler.py`: Distribution sampling for operational variables
- `beer_game_adapter.py`: Adapter for Beer Game integration

**AI Agent Services** (`services/`):
- `agents.py`: Agent strategy implementations (naive, bullwhip, conservative, ml_forecast, optimizer, reactive)
- `llm_agent.py`: LLM agent wrapper with fallback to heuristic strategies
- `llm_payload.py`: OpenAI request/response handling for multi-agent system

**Simulation Services** (`services/`):
- `mixed_scenario_service.py`: Beer Game orchestration (handles mixed human/AI scenarios)
- `agent_game_service.py`: Pure agent scenario management
- `engine.py`: Core Beer Game simulation engine with `BeerLine` and `Node` classes

**Core Services** (`services/`):
- `supply_chain_config_service.py`: DAG-based supply chain configuration
- `tenant_service.py`: Tenant and session management
- `auth_service.py`: JWT authentication and authorization
- `conformal_orchestrator.py`: Automatic conformal prediction feedback loop
- `agent_context_explainer.py`: Context-aware explainability orchestrator for all 11 TRM agents and both GNN models
- `explanation_templates.py`: 39 Jinja2-style templates (13 agent types × 3 verbosity levels)
- `decision_stream_service.py`: Decision Stream inbox — Urgency/Likelihood/Benefit routing framework
- `pegging_service.py`: Full-Level Pegging — Kinaxis-style supply-demand tracing
- `multi_stage_ctp_service.py`: Multi-Stage Capable-to-Promise
- `powell/scenario_engine.py`: MCTS what-if planning
- `powell/simulation_rl_trainer.py`: PPO fine-tuning inside digital twin
- `powell/heuristic_library/`: ERP-aware heuristic library (11 TRM types × 3 ERP vendors)
- `scenario_event_service.py`: 24 event types across 5 categories

**API Endpoints** (`api/endpoints/`):
- `mps.py`: Master Production Scheduling
- `supply_plan.py`: Supply plan generation and approval
- `pegging.py`: Full-Level Pegging & Multi-Stage CTP
- `mixed_scenario.py`: Beer Game API
- `agent_scenario.py`: Pure agent scenario API
- `supply_chain_config.py`: Supply chain network configuration
- `model.py`: Training and dataset generation
- `auth.py`: Authentication (login, register, MFA)
- `websocket.py`: Real-time scenario updates
- `user_directives.py`: Azirella directive capture
- `provisioning.py`: Powell Cascade 16-step provisioning stepper
- `email_signals.py`: GDPR-safe email signal ingestion
- `agent_stochastic_params.py`: Per-agent stochastic parameters CRUD

**Database Models** (`models/`):
- `aws_sc_planning.py`: AWS SC planning entities
- `supply_chain_config.py`: Network topology
- `scenario.py`: Scenario, Period, ScenarioUserAction
- `participant.py`: ScenarioUser, ScenarioUserRole, ScenarioUserPeriod
- `agent_config.py`: AgentConfig, AgentScenarioConfig
- `agent_stochastic_param.py`: AgentStochasticParam
- `tenant.py`: Tenant model
- `user.py`: User, Role, Permission
- `rbac.py`: Role-Based Access Control
- `gnn/`: GNN model definitions

### Frontend Structure (`frontend/src/`)

**Two-Tier Navigation** (Mar 2026):
- CategoryBar (top-level) + PageBar (sub-pages). Capability-filtered via `getFilteredNavigation()`.
- Decision Stream pinned first for functional users. Azirella panel slides in from right.
- Files: `TwoTierNav.jsx`, `CategoryBar.jsx`, `PageBar.jsx`, `useNavStore.js`

**Planning Pages** (`pages/planning/` — 43+ pages): MPS, demand, supply, inventory, capacity, S&OP, ATP worklists, lot sizing, execution pages.

**Simulation Pages** (`pages/`): ScenarioBoard, ScenariosList, CreateMixedScenario, ScenarioReport, ScenarioVisualizations.

**Admin Pages** (`pages/admin/` — 25+ pages): TRM/GNN/GraphSAGE dashboards, Powell/Hive/RL/RLHF dashboards, SAP/ERP management, email signals, synthetic data wizard, user/role/tenant management, governance.

### Agent System Architecture

**TRM Hive Model**: Each site's TRM agents form a self-organizing hive. Site-specific composition based on `master_type` (manufacturers: 11, DCs: 7, retailers: 6, market: 1). See `site_capabilities.py`.

#### Multi-Site Coordination Stack (5 layers)

Context, guardrails, and targets flow **down** from strategic to execution. Feedback, outcomes, and escalations flow **up** from execution to strategic.

**Layer 1 — Intra-Hive (<10ms): Stigmergic Coordination**
- `hive_signal.py`: 25 typed signals across 5 castes (Scout, Forager, Nurse, Guard, Builder)
- `HiveSignalBus`: Shared ring buffer (200 signals) with exponential decay (pheromone model)
- `UrgencyVector`: 11-slot shared array (one per TRM), thread-safe, decay threshold 0.05
- Decay math: `strength(t) = urgency × exp(-0.693 × elapsed_min / half_life_min)`
- Signal half-life default 30 min (intra-hive), 12 hours (inter-hive)
- TRMs emit signals on condition detection → other TRMs read active signals when deciding

**Layer 2 — Site tGNN (hourly): Learned Cross-TRM Causal Coordination**
- `site_tgnn.py`: GATv2+GRU, ~25K params, 22 directed causal edges, <5ms inference
- Always enabled (no feature flag). Cold-start returns neutral output (zero adjustments)
- Runs BEFORE each decision cycle — modulates UrgencyVector with [-0.3, +0.3] adjustments
- Training: 3-phase (BC from oracle → PPO in digital twin [stub] → calibration from outcomes)
- Provisioning step 14. Checkpoints tenant/config/site scoped
- `site_tgnn_inference_service.py`: Loads checkpoint, persists GRU hidden state across ticks
- `site_tgnn_oracle.py`: MultiTRMCoordinationOracle generates 500+ BC samples per site

**Layer 2 — Network tGNN (daily): Inter-Site Directives**
- `inter_hive_signal.py`: 8 inter-hive signal types with 12-hour half-lives
- `directive_broadcast_service.py`: Broadcasts tGNNSiteDirective to each site's SiteAgent
- `tactical_hive_coordinator.py`: 3 parallel specialized tGNNs (demand, supply, inventory) with lateral convergence (re-run if signals deviate >5%)
- Inter-hive signals mapped to local HiveSignalTypes when injected into site bus

**Layer 3 — AAP Cross-Authority (seconds-minutes): Agentic Authorization Protocol**
- `authorization_protocol.py`: Three-phase protocol — EVALUATE → REQUEST → AUTHORIZE
- `authorization_service.py`: Production service with DB persistence (`authorization_models.py`)
- `strategy_a2a_responder.py`: Routes authorization requests to domain-specific TRM evaluators
  - MO TRM: spare capacity ≥20% → AUTHORIZE; 5-20% → COUNTER_OFFER; <5% → DENY
  - PO TRM: active expedites vs threshold
  - Rebalancing TRM: source surplus above safety stock
- Authority boundaries per TRM role: UNILATERAL / REQUIRES_AUTHORIZATION / FORBIDDEN
- Balanced Scorecard net-benefit scoring: auto-AUTHORIZE if benefit > 1.1× threshold
- Counter-offer mechanism with revised BSC for resource contention
- `negotiation_service.py`: Carrier/supplier negotiation workflow

**Layer 4 — S&OP Consensus Board (weekly): Policy Parameters**
- S&OP GraphSAGE computes network-wide policy parameters θ
- Parameters cascade: safety_stock_multiplier, criticality_score, bottleneck_risk, resilience_score, demand_forecast, exception_probability
- `site_agent.py` `apply_directive()`: Injects inter-hive signals + extracts S&OP params → pushes to TRMs via `apply_network_context()`

#### Downward Flow: Context, Targets, Guardrails

```
S&OP GraphSAGE (weekly) → policy parameters θ
    ↓
Network tGNN (daily) → tGNNSiteDirective per site
    ↓ (directive_broadcast_service.py)
SiteAgent.apply_directive():
    1. Inject inter-hive signals into local HiveSignalBus
    2. Extract S&OP params (safety_stock_multiplier, criticality, etc.)
    3. Push params to TRMs via apply_network_context()
    ↓
Site tGNN (hourly) → modulate UrgencyVector [-0.3, +0.3]
    ↓
11 TRM Agents → execution decisions (<10ms)
```

#### Upward Flow: Feedback, Escalation, Override

```
TRM detects persistent drift (48h lookback, ≥20 decisions)
    ↑ (escalation_arbiter.py)
Escalation Arbiter evaluates:
    - Direction, magnitude, consistency of adjustments
    - Cross-site pattern (>30% of sites = strategic)
    ↑
Routing:
    - Horizontal (CDC retrain): single site/TRM drift
    - Operational (tGNN refresh): magnitude 20-35%, <30% sites
    - Strategic (S&OP review): magnitude >35%, >30% sites
    ↑
Human Override → Experiential Knowledge → agent retraining
```

#### Key Implementation Files

| Component | File | Lines |
|-----------|------|-------|
| Hive signals | `services/powell/hive_signal.py` | ~250 |
| Hive feedback | `services/powell/hive_feedback.py` | |
| Site tGNN model | `models/gnn/site_tgnn.py` | ~270 |
| Site tGNN trainer | `services/powell/site_tgnn_trainer.py` | ~650 |
| Site tGNN oracle | `services/powell/site_tgnn_oracle.py` | ~630 |
| Site tGNN inference | `services/powell/site_tgnn_inference_service.py` | ~400 |
| Inter-hive signals | `services/powell/inter_hive_signal.py` | ~150 |
| Directive broadcast | `services/powell/directive_broadcast_service.py` | ~300 |
| Tactical coordinator | `services/powell/tactical_hive_coordinator.py` | |
| AAP protocol | `services/authorization_protocol.py` | ~500 |
| AAP service | `services/authorization_service.py` | |
| A2A responder | `services/strategy_a2a_responder.py` | |
| Escalation arbiter | `services/powell/escalation_arbiter.py` | ~330 |
| Site agent | `services/powell/site_agent.py` | ~1750 |

**ERP-Aware Heuristic Library**: 3,908 lines, 11 TRM types × 3 ERPs. Location: `backend/app/services/powell/heuristic_library/`.

**Scenario Engine (MCTS)**: ScenarioEngine, ScenarioTrigger, CandidateGenerator, ContextualBSC. 40 templates, Beta posterior ranking.

### Database Schema

**AWS SC Planning Tables**: forecast, supply_plan, sourcing_rules, inv_policy, inv_level, product_bom, production_process, vendor_product, vendor_lead_time, supply_planning_parameters, supply_demand_pegging, aatp_consumption_record.

**Network Configuration**: supply_chain_configs, site, transportation_lane, product, market.

**Simulation**: scenarios, scenario_users, periods, scenario_user_periods, agent_configs, agent_scenario_configs.

**Organization**: users, tenants, roles, permissions, user_roles.

**SAP Staging** (`sap_staging` schema): extraction_runs, rows, table_schemas. Also `d365_staging` and `odoo_staging`.

**Powell Framework**: powell_belief_state, powell_calibration_log, powell_policy_parameters, powell_value_function, powell_hierarchical_constraints, powell_exception_resolution, powell_stochastic_solution, powell_allocations, powell_atp_decisions, powell_rebalance_decisions, powell_po_decisions, powell_order_exceptions, powell_mo_decisions, powell_to_decisions, powell_quality_decisions, powell_maintenance_decisions, powell_subcontracting_decisions, powell_forecast_adjustment_decisions, powell_buffer_decisions, override_effectiveness_posteriors, override_causal_match_pairs, agent_scenarios, agent_scenario_actions, scenario_templates, experiential_knowledge.

**Directive & Signal**: user_directives, config_provisioning_status, email_connections, email_signals.

---

## Common Workflows

### AWS SC Planning Workflow

1. **Load Config**: GET `/api/v1/supply-chain-configs`
2. **Generate**: POST `/api/v1/supply-plan/generate` with config_id, planning_horizon, stochastic_params, objectives
3. **Monitor**: GET `/api/v1/supply-plan/status/{task_id}`
4. **Review**: GET `/api/v1/supply-plan/result/{task_id}`
5. **Approve**: POST `/api/v1/supply-plan/approve/{task_id}`

### Adding a New Agent Strategy

1. Implement in `backend/app/services/agents.py`
2. Register in `AgentStrategy` enum
3. Add to `get_policy_by_strategy()` factory
4. Update AGENT_SYSTEM.md

### Creating Synthetic Data

POST `/api/v1/synthetic-data/generate` with archetype (retailer/distributor/manufacturer). Creates tenant, config, sites, lanes, products, forecasts, policies, hierarchies.

### ERP Data Management (SAP, D365, Odoo)

Two-phase pipeline: ERP → staging schema (JSONB) → AWS SC mapping. Staging schemas: `sap_staging` (54 tables), `d365_staging` (42 entities), `odoo_staging` (27 models). See [ERP_INTEGRATION_GUIDE.md](external/ERP_INTEGRATION_GUIDE.md).

### Azirella — Natural Language Directive Capture

Two-phase flow: `POST /directives/analyze` (parse + gap detect) → clarification → `POST /directives/submit` (persist + route).

16-step provisioning pipeline: warm_start → sop_graphsage → cfa_optimization → lgbm_forecast → demand_tgnn → supply_tgnn → inventory_tgnn → trm_training → rl_training → supply_plan → rccp_validation → decision_seed → site_tgnn → conformal → scenario_bootstrap → briefing.

### Email Signal Intelligence

GDPR-safe: NO PII stored. Pipeline: Email → PII scrub → domain→TradingPartner → LLM classification → TRM routing. 12 signal types mapped to TRM agents.

### External Signal Intelligence

Outside-in planning: FRED, Open-Meteo, EIA, GDELT, Google Trends, openFDA. Daily refresh at 05:30. Injected into Azirella RAG context.

---

## Planning Knowledge Base

Consult [PLANNING_KNOWLEDGE_BASE.md](../PLANNING_KNOWLEDGE_BASE.md) for comprehensive guidance.

**Quick Reference**:
- Stochastic vs Deterministic: distributions for operational variables, fixed for control
- Hierarchical Overrides: Product-Site > Product > Site > Config
- 8 Policy Types: abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal
- Balanced Scorecard: Financial, Customer, Operational, Strategic with probability distributions

**Key PDFs** (in `docs/Knowledge/`):
- `01_MPS_Material_Requirements_Planning_Academic.pdf`
- `04_Kinaxis_Master_Production_Scheduling.pdf`
- `14_Stanford_Stochastic_Programming_Solutions.pdf`

**Lokad**: See `docs/Knowledge/Lokad_Analysis_and_Integration_Guide.md`. Key: decision-driven optimization, prioritized ordering, economic loss functions, CRPS metric, censored demand.

**Powell SDAM**: See [POWELL_APPROACH.md](../POWELL_APPROACH.md). Five elements (State, Decision, Exogenous, Transition, Objective). Four policy classes (PFA, CFA, VFA, DLA). State decomposition: Rₜ (physical), Iₜ (information), Bₜ (belief).

**Decision-Theoretic Frameworks**: Kahneman Dual-Process, Boyd OODA, SOFAI, Gartner DI, Kozyrkov DI, Pratt CDD. See [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md).

**Beer Game**: Reference materials in `docs/The_Beer_Game/`.

**Business Strategy**: Rumelt "Good Strategy Bad Strategy", Moore "Crossing the Chasm".

---

## Claude Skills Framework (Hybrid TRM + Skills)

Hybrid TRM + Claude Skills architecture. TRMs primary (~95%, <10ms), Claude Skills exception handler (~5%). LeCun JEPA mapping. Feature-flagged OFF by default (`USE_CLAUDE_SKILLS=false`).

**Docs**: [CLAUDE_SKILLS_STRATEGY.md](CLAUDE_SKILLS_STRATEGY.md), [CLAUDE_SKILLS_MIGRATION_PLAN.md](CLAUDE_SKILLS_MIGRATION_PLAN.md), [CLAUDE_SUBSCRIPTION_GUIDE.md](CLAUDE_SUBSCRIPTION_GUIDE.md).

**Execution Flow**: Engine → TRM → Conformal Router → (high confidence: accept, low confidence: escalate to Skills) → Skills decisions feed TRM meta-learning.

**Routing**: skill_escalation_threshold=0.6, risk_bound check, interval_width > 0.5.

**11 Skills**: Deterministic (atp, order_tracking), Haiku (po, rebalancing, buffer, to), Sonnet (mo, quality, maintenance, subcontracting, forecast).

**Files**: `services/skills/`, `decision_memory_service.py`, `decision_embeddings.py`.

**Env**: `CLAUDE_API_KEY`, `USE_CLAUDE_SKILLS=false`, `SKILL_ESCALATION_THRESHOLD=0.6`, `SKILL_MAX_DEVIATION=0.3`.

---

## Architectural Refactoring Status

**Status**: SUBSTANTIALLY COMPLETE (Feb 2026). See [ARCHITECTURAL_REFACTORING_PLAN.md](../ARCHITECTURAL_REFACTORING_PLAN.md).

Completed: AWS SC 100%, 96+ pages, terminology renames, TRM Hive, AAP, CDC→Relearning, SAP integration, Claude Skills, Two-Tier Navigation, User Management CRUD, 16-step provisioning, decision_level rename.

---

## MCP Live Operations Layer (Apr 2026)

**Purpose**: Bidirectional ERP communication via Model Context Protocol for ongoing operations. Bulk extraction retained for provisioning only.

**Inbound (CDC)**: MCP polls ERP every 1-5 min → DeltaClassifier → ContextEngine → HiveSignalBus (TRM signals).

**Outbound (Write-back)**: TRM decisions → adaptive delay (urgency/confidence-scaled, business-hours-aware) → MCP tool call → ERP document (PO/MO/TO/SO update).

**Key Design**: No decision is written to ERP immediately. Every decision gets an adaptive cooling period. Countdown only ticks during business hours. Humans can override pre-execution (cancel) or post-execution (compensating reversal). On-call notification for after-hours urgent decisions.

**Adapters**: SAP S/4HANA, Odoo, D365 F&O. Planned: SAP B1, NetSuite, Infor.

**Files**: `integrations/mcp/` (client, config, audit, context_engine, writeback_service, scheduler, adapters/), `models/operating_schedule.py`, `services/oversight_schedule_service.py`.

**Docs**: [AGENT_GUARDRAILS_AND_AIIO.md](internal/AGENT_GUARDRAILS_AND_AIIO.md) Section 16.

---

## Unified Training Corpus (Apr 2026)

**Purpose**: Single source of truth for all agent training data across the four planning layers (Strategic S&OP, Tactical tGNNs, Operational Site tGNN, Execution TRMs). Replaces the previous architecture of four independent synthetic data pipelines.

**Anchor**: ERP baseline extracted at provisioning (open POs, MOs, TOs, inventory, sourcing rules). This is the tenant's real operating reality.

**Generation**: ~500 perturbations around the baseline (demand +/-15%, lead times +/-20%, costs +/-10%, etc.). Each perturbation runs the Digital Twin with all 12 TRMs active. Every TRM decision is captured as a Layer 1 sample.

**Aggregation**: Pure data transformation upward:
- Layer 1 (TRM decisions) → Layer 2 (site × time window aggregates for Site tGNN) → Layer 2 (network × domain × period for Tactical tGNNs) → Layer 4 (network × theta* for S&OP GraphSAGE)

**Continuous**: Real outcomes from `powell_*_decisions` append as new Layer 1 samples post-provisioning. Aggregator re-runs on new samples. All four layers retrain together when drift is detected.

**Key property**: All four layers train on the same reality → no cross-layer disagreement.

**Files**: `services/training_corpus/` (corpus_service, erp_baseline_extractor, perturbation_generator, simulation_runner, aggregator, theta_inference), `models/training_corpus.py`, migration `20260404_training_corpus.py`.

**Docs**: [UNIFIED_TRAINING_CORPUS.md](internal/architecture/UNIFIED_TRAINING_CORPUS.md), [HOW_AGENTS_LEARN.md](external/HOW_AGENTS_LEARN.md).

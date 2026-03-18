# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL: AWS Supply Chain Data Model Compliance

**MANDATORY REQUIREMENT**: In all cases, the AWS Supply Chain Data Model MUST be used for all data. Extensions to accommodate variability of parameters are allowed, but the core tables and fields MUST be used.

**The Beer Game is only a special case of the AWS Supply Chain Data Model** and must use the AWS Supply Chain Data Model tables and fields as the foundation. Any Beer Game-specific features must be implemented as extensions to the base AWS SC model, not as replacements.

When implementing any entity:
1. First reference the AWS SC data model definition in [backend/app/models/sc_entities.py](backend/app/models/sc_entities.py)
2. Use AWS SC field names and types as the base
3. Add extensions only when necessary for Beer Game or platform-specific features
4. Document any extensions clearly as "Extension: " in model docstrings

## CRITICAL: Documentation Must Be Updated With Code Changes

**MANDATORY REQUIREMENT**: When making code changes that affect architecture, APIs, data models, or user-facing features, the relevant `.md` documentation files MUST be updated in the same work session. Do not leave documentation updates for later.

**Rules**:
1. **New features/services** → Update the relevant section in CLAUDE.md and any affected docs in `docs/`
2. **New models/tables** → Update the Database Schema section in CLAUDE.md
3. **API changes** → Update endpoint documentation in the relevant docs
4. **SAP integration changes** → Update `docs/internal/SAP_DEMO.md` and `docs/external/SAP_INTEGRATION_GUIDE.md`
5. **Architecture changes** → Update CLAUDE.md Architecture section and `docs/internal/TECHNICAL_OVERVIEW.md`
6. **New event types/capabilities** → Update catalogs and scenario docs

## CRITICAL: No Fallbacks, No Hardcoded Values

**MANDATORY REQUIREMENT**: Code must NEVER use fallback values, hardcoded defaults, or `getattr(obj, "field", <default>)` patterns that silently mask missing data. All data must come from the database schema as defined.

**Rules**:
1. **Column names must match the actual DB schema** — never guess column names; check the model or table definition first
2. **No silent fallbacks** — if data is missing, show nothing or raise an error; do not substitute fake/default values
3. **No hardcoded entity references** — product IDs, site names, config IDs, order IDs must come from the tenant's data, never hardcoded
4. **No hardcoded demo data** — all displayed data must come from DB or calculations on DB data
5. **All economic parameters** (holding_cost, stockout_cost, ordering_cost) must be explicitly set per tenant — errors raised for missing data
6. **Currency symbols, units, limits** — must be configurable via constants or environment variables, not inline literals

## Terminology Convention (Feb 2026)

**IMPORTANT**: Use consistent terminology throughout the codebase:

| Old Term (Removed) | New Term (Canonical) | Context |
|-------------------|---------------------|---------|
| Game | Scenario | Simulation scenario |
| Player/Participant | ScenarioUser | Code/API/DB level |
| Player/Participant | User | UI display |
| Round | Period | Time period |
| Gamification | Simulation | Section/feature name |
| play_round | execute_period | Function name |
| game_id | scenario_id | Database/API field |
| player_id/participant_id | scenario_user_id | Database/API field |
| Group | Tenant | Organization/tenant boundary |
| group_id | tenant_id | Database/API field |
| GroupMode | TenantMode | Operating mode enum |
| GroupService | TenantService | Backend service |
| Training Group | Learning Tenant | Tenant in education mode |
| node | site | AWS SC data model |
| nodes | site (table) | AWS SC data model |
| item | product | AWS SC data model |
| items | product (table) | AWS SC data model |
| lane | transportation_lane | AWS SC data model |
| lanes | transportation_lane (table) | AWS SC data model |
| SafetyStockTRM | InventoryBufferTRM | TRM/Powell agent layer |
| safety_stock_trm.py | inventory_buffer_trm.py | TRM source file |
| powell_safety_stock_decisions | powell_buffer_decisions | Powell decision table |
| PowellSSDecision | PowellBufferDecision | SQLAlchemy model |
| SS_INCREASED / SS_DECREASED | BUFFER_INCREASED / BUFFER_DECREASED | HiveSignalType |
| "safety_stock" (TRM type) | "inventory_buffer" | TRM type identifier |
| PENDING (DecisionStatus) | INFORMED | AIIO: user notified, awaiting action |
| ACCEPTED (DecisionStatus) | ACTIONED | AIIO: decision executed |
| AUTO_EXECUTED (DecisionStatus) | ACTIONED | AIIO: agent auto-executed |
| EXPIRED (DecisionStatus) | ACTIONED | AIIO: time expired, auto-resolved |
| REJECTED (DecisionStatus) | OVERRIDDEN | AIIO: user rejected with alternative |
| — | INSPECTED | AIIO: user reviewed, no action needed (new) |

> **Terminology Note — AIIO Decision Status (Mar 2026)**: The `DecisionStatus` enum in `decision_tracking.py` (used by `agent_decisions` and `sop_worklist_items` tables) has been renamed to the **AIIO model**: **A**ctioned, **I**nformed, **I**nspected, **O**verridden. This applies only to the agent decision workflow — the planning decision workflow (`planning_decision.py`: PENDING/APPLIED/PENDING_APPROVAL/APPROVED/REJECTED/REVERTED/SUPERSEDED) and AAP ThreadStatus are unchanged. The `commit_status` enum (PROPOSED/REVIEWED/ACCEPTED/OVERRIDDEN/SUBMITTED) used in planning commit workflows also remains unchanged.

> **Terminology Note — Inventory Buffer (Feb 2026)**: At the TRM/Powell execution layer, "SafetyStockTRM" has been renamed to **InventoryBufferTRM**. This addresses the DDMRP critique that "safety stock" as a concept causes MRP to treat it as a hard demand target, generating planned orders that compete with real customer demand for upstream capacity. At the TRM level, the inventory buffer is an **uncertainty absorber**, NOT a hard demand target for MRP. Buffer-replenishment planned orders get lower priority than demand-driven orders (soft-buffer netting). **Important**: The AWS SC data model fields (`safety_stock` column, `ss_quantity`, `inv_policy` policy types) remain unchanged for compliance — the rename applies only to TRM agent names, Powell decision tables, and hive signal types.

**Clean Rename**: The old terminology has been fully replaced. There are no backward-compatible aliases.
- Use `Scenario`, `ScenarioCreate`, `ScenarioState` (not Game*)
- Use `ScenarioUser`, `ScenarioUserRole`, `ScenarioUserResponse` (not Player*/Participant*)
- Use `Period`, `ScenarioUserPeriod` (not Round*, GameRound)
- Frontend uses `simulationApi` with methods like `createScenario()`, `getScenarioUsers()`

### Customer Tenant Model

**Every Autonomy customer receives two tenants:**

| Tenant | Mode | Data Source | Purpose |
|--------|------|-------------|---------|
| **Operational Tenant** | `TenantMode.PRODUCTION` | SAP master data extraction | Real supply chain planning and execution |
| **Learning Tenant** | `TenantMode.LEARNING` | Default TBG config + variants | Training, simulation, agent validation |

- **Operational Tenant**: Created using master data extracted from the customer's ERP system (SAP, D365, or Odoo via ERP Data Management). Data flows through ERP-specific staging schemas (`sap_staging`, `d365_staging`, `odoo_staging`) before mapping to the AWS SC data model. Contains the customer's real supply chain topology, products, BOMs, forecasts, and inventory. Full navigation, real data integration, real planning workflows.
- **Learning Tenant**: Pre-provisioned with the Default TBG (The Beer Game) config and all variants (Three FG TBG, Variable TBG, etc.). Simplified navigation, game-like clock (turn-based/timed), focused on user education and building confidence with AI agents. The Beer Game is ONLY used within the Learning Tenant — it is NOT referenced elsewhere in the platform.

**Both tenant modes support AI model training** (TRM, GNN, RL) — the tenant mode determines the **user experience**, not whether AI models can be trained.

> **Terminology Note — Tenant vs Customer (Feb 2026)**: "Tenant" is the organizational boundary term (equivalent to AWS SC `company`). Do NOT use "Customer" for this purpose — in the AWS SC Data Model, "customer" means a trading partner (demand point) via `TradingPartner` with `tpartner_type='customer'`. The `customer_id` fields in AWS SC entities (Forecast, OutboundOrderLine, CustomerCost, FulfillmentOrder, etc.) correctly reference trading partners and must NOT be confused with the tenant/organization boundary.

> **CRITICAL**: `customer_id` must ONLY be used for AWS SC data model fields that reference trading partners. All internal platform code must use `tenant_id` for organizational boundary. Any use of `customer_id` as a substitute for `tenant_id` is a bug.

---

## Project Overview

**Autonomy Platform — Decision Intelligence for Supply Chain** - An enterprise-grade supply chain planning and execution system compatible with AWS Supply Chain standards, built on four pillars:

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

**AWS SC Compliance**: ✅ 100% (35/35 entities implemented). See [AWS_SC_IMPLEMENTATION_STATUS.md](docs/internal/AWS_SC_IMPLEMENTATION_STATUS.md) for detailed status.

**AWS SC References**:
- **Features**: Target feature parity (excluding Data Lakes) with AWS Supply Chain capabilities: https://aws.amazon.com/aws-supply-chain/features/
- **Resources**: UI/UX guidance and implementation examples: https://aws.amazon.com/aws-supply-chain/resources/

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
   - **Research Foundation**: Architecture inspired by Samsung SAIL Montreal's TRM ([arxiv:2510.04871](https://arxiv.org/abs/2510.04871)), which demonstrated that a 7M-parameter recursive network outperforms 671B-parameter LLMs on structured reasoning. See [TRM_RESEARCH_SYNTHESIS.md](TRM_RESEARCH_SYNTHESIS.md) for full research context.
   - **Architecture Principles** (from Samsung TRM research):
     - Recursion multiplies compute without multiplying parameters (2 layers × N applications = 2N effective layers)
     - Post-normalization essential for recursion stability (bounds hidden state magnitude)
     - Full backpropagation through all recursive steps (no gradient approximation)
     - Deep supervision at each refinement step encourages good intermediate outputs
     - Fewer parameters → better generalization (model must learn rules, not memorize)
   - **Scope: Narrow execution decisions only**:
     - **ATPExecutorTRM**: Allocated Available-to-Promise with priority consumption
     - **InventoryRebalancingTRM**: Cross-location transfer decisions
     - **POCreationTRM**: Purchase order timing and quantity
     - **OrderTrackingTRM**: Exception detection and recommended actions
     - **MOExecutionTRM**: Manufacturing order release, sequencing (Glenday Sieve + nearest-neighbor changeover minimization), expedite
     - **TOExecutionTRM**: Transfer order release, consolidation, expedite
     - **QualityDispositionTRM**: Quality hold/release/rework/scrap decisions
     - **MaintenanceSchedulingTRM**: Preventive maintenance scheduling and deferral
     - **SubcontractingTRM**: Make-vs-buy and external manufacturing routing
     - **ForecastAdjustmentTRM**: Signal-driven forecast adjustments (email, voice, market intel)
     - **InventoryBufferTRM**: Inventory buffer parameter adjustment and reoptimization *(renamed from SafetyStockTRM — see Terminology Note below)*
   - TRM does NOT do: long-term planning, network-wide optimization, policy parameters
   - **Training**: TRM = model architecture, RL = training method (not alternatives!)
     - Behavioral cloning for warm-start (supervised from experts)
     - RL/VFA fine-tuning (TD learning with actual outcomes)
     - Narrow scope makes RL tractable (small state, fast feedback, clear reward)
     - CGAR curriculum ([arxiv:2511.08653](https://arxiv.org/abs/2511.08653)): Progressive recursion depth during training reduces FLOPs ~40%
     - Data volume scaling (Stöckl, RANLP 2021, [ACL Anthology](https://aclanthology.org/2021.ranlp-1.148/)): "Learning by watching" — data volume >> model size for structured decisions. 50K samples/sub-phase × 3 × 3 signal phases = 450K total BC samples. 3-tier evaluation (memorization/generalization/rule-learning) replaces loss-only tracking.
   - Files: `backend/app/services/powell/atp_executor.py`, `inventory_rebalancing_trm.py`, `po_creation_trm.py`, `order_tracking_trm.py`, `mo_execution_trm.py`, `to_execution_trm.py`, `quality_disposition_trm.py`, `maintenance_scheduling_trm.py`, `subcontracting_trm.py`, `forecast_adjustment_trm.py`, `inventory_buffer_trm.py`, `trm_trainer.py`
   - **CDC → Relearning Loop**: Autonomous feedback pipeline for continuous TRM improvement
     - `cdc_monitor.py`: Event-driven metric deviation detection (6 thresholds, rate limiting)
     - `outcome_collector.py`: Computes actual outcomes for decisions after feedback horizon delays (both SiteAgentDecision and all 11 powell_*_decisions tables)
     - `cdt_calibration_service.py`: Batch and incremental CDT calibration from decision-outcome pairs across all 11 TRM types
     - `cdc_retraining_service.py`: Evaluates retraining need, executes Offline RL, checkpoints model
     - `relearning_jobs.py`: APScheduler jobs — outcome collection (:30, :32), CDT calibration (:35), retraining eval (every 6h at :45)
     - `condition_monitor_service.py`: 6 real-time condition checks against DB (ATP shortfall, inventory, capacity, orders, forecast)
     - `integration/decision_integration.py`: Decision tracking and training data extraction
   - **Conformal Decision Theory (CDT)**: All 11 TRM agents carry `risk_bound` and `risk_assessment` on every decision response — P(loss > threshold) with distribution-free guarantee. Calibrated via `CDTCalibrationService` from historical decision-outcome pairs in `powell_*_decisions` tables. Batch calibration at startup, incremental hourly.

2. **GNN Agent** (Graph Neural Network) - Three-Tier Architecture
   - **S&OP GraphSAGE** (Medium-Term): Network structure analysis, risk scoring, bottleneck detection
     - Updates weekly/monthly, outputs criticality scores, concentration risk, resilience, safety stock multipliers
     - Scalable to 50+ nodes with O(edges) complexity
     - **Powell: CFA (computes policy parameters θ)**
   - **Execution tGNN** (Short-Term): Generates priority allocations, provides context for TRM
     - Consumes S&OP embeddings + transactional data, updates daily
     - **Outputs: Priority × Product × Location allocations for AATP**
     - **Powell: CFA/VFA bridge**
   - **Site tGNN** (Intra-Site): 11 TRM-type nodes with ~22 directed causal edges, GATv2+GRU, ~25K params, <5ms inference, hourly. Learns cross-TRM trade-offs (e.g., aggressive ATP fulfillment → MO capacity starvation).
   - **Shared Foundation**: S&OP embeddings cached and fed to Execution model
   - 85-92% demand prediction accuracy
   - Trained on SimPy-generated game data

3. **LLM Agent** (GPT-4 Multi-Agent Orchestrator)
   - Site agents (per supply chain role)
   - Supervisor agent (validates and improves decisions)
   - Global planner agent (network-wide coordination)
   - Natural language explainability

**Integration**: AI agents can be used in:
- Planning workflows (automated planner role)
- Simulation (as opponents or teammates)
- Validation (compare AI vs human decisions)

### Pillar #2: Conformal Prediction (Distribution-Free Uncertainty Guarantees)

**Purpose**: Every agent decision carries a calibrated likelihood guarantee — if the system says "90% confident," actual coverage will be ≥90%.

**What it provides**:
- **Distribution-free guarantees**: No assumptions about underlying data distribution. Coverage guarantees hold regardless of whether demand is Normal, Lognormal, or any other shape.
- **Conformal Decision Theory (CDT)**: Every TRM decision carries `risk_bound` = P(loss > threshold). Calibrated hourly from historical decision-outcome pairs.
- **Principled escalation**: Wide conformal intervals trigger escalation to Claude Skills or human review. Tight intervals allow autonomous execution. This replaces arbitrary fixed thresholds with statistically rigorous routing.
- **8 inventory policy types**: Including `conformal` (pure distribution-free), `sl_conformal_fitted` (hybrid), and `econ_optimal` (marginal economic return via Monte Carlo DDLT)

**Powered by the Stochastic Simulation Engine**:
- **21 Distribution Types**: Normal, lognormal, beta, gamma, Weibull, exponential, triangular, log-logistic, mixture, empirical, etc.
- **Monte Carlo Simulation**: 1000+ scenarios for full uncertainty propagation
- **Variance Reduction**: Common random numbers, antithetic variates, Latin hypercube sampling
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand, forecast error
- **Control Variables** (deterministic): Inventory targets, costs, policy parameters

**Probabilistic Balanced Scorecard**:
- **Financial**: E[Total Cost], P(Cost < Budget), P10/P50/P90 cost distribution
- **Customer**: E[OTIF], P(OTIF > 95%), fill rate likelihood
- **Operational**: E[Inventory Turns], E[DOS], bullwhip ratio distribution
- **Strategic**: Flexibility scores, supplier reliability, CO2 emissions

**Output**: Likelihood distributions for KPIs instead of single-point estimates (e.g., "85% chance service level > 95%")

### Pillar #3: Digital Twin (Stochastic Simulation Engine)

**Purpose**: A complete simulation of the supply chain that generates the training data, calibration sets, and risk-free testing environment that everything else depends on.

**What it provides**:
- **Monte Carlo scenario generation**: 1000+ stochastic scenarios sampling from 21 distribution types across demand, lead times, yields, and capacities
- **Training data pipeline**: Six-phase digital twin pipeline generates 28.6M+ training records for TRM agents, from individual behavioral cloning through coordinated multi-agent simulation
- **Conformal calibration sets**: Simulation outputs feed conformal prediction calibration — the digital twin powers the uncertainty guarantees
- **Risk-free agent validation**: Test AI agents in simulation before production deployment
- **What-if analysis**: Scenario branching at machine speed for planning decisions

**The Beer Game** (Learning Tenant):
- Classic multi-echelon supply chain simulation (Retailer → Wholesaler → Distributor → Factory)
- Demonstrates bullwhip effect and demand amplification
- 2-8 users in real-time WebSocket scenarios with mixed human-AI play
- Used for employee training (3-5x higher engagement), confidence building, and continuous improvement

**Integration**: Beer Game scenarios use core AWS SC services underneath (demand planning, supply planning, inventory management). The Beer Game is ONLY used within the Learning Tenant.

### Pillar #4: Causal AI (Decision Outcome Attribution)

**Purpose**: Rigorously determine whether decisions actually caused positive outcomes — not just correlate "we did X and Y happened" but answer "what would have happened if we hadn't done X?" (the counterfactual).

**The core problem**: When an AI agent makes 1,000 decisions per day, and outcomes improve, you cannot simply attribute the improvement to the agent. Demand may have been favorable. Suppliers may have been on time. Competing decisions from other agents may have helped. Without causal inference, you're measuring correlation, not causation — and training on correlation produces agents that learn the wrong lessons.

**Three-Tier Causal Inference Strategy**:

| Tier | Decision Types | Method | Signal Strength |
|------|---------------|--------|-----------------|
| **1 — Analytical Counterfactual** | ATP, Forecast Adjustment, Quality | Direct computation: "What reward would the agent's recommendation have earned given the actual environment outcome?" | 1.0 (full) |
| **2 — Statistical Matching** | MO, TO, PO, Order Tracking | Propensity-score matching: find similar non-overridden decisions as controls, compute treatment effect | 0.3–0.9 (scales with match availability) |
| **3 — Bayesian Prior** | Inventory Buffer, Maintenance, Subcontracting | Beta posterior only (high confounding, long feedback horizons). Future: causal forests (Athey & Imbens 2018) | 0.15 (minimal) |

**Five Causal AI Systems (all deployed and scheduled)**:

1. **Counterfactual Computation** (`outcome_collector.py`): For every overridden decision, computes what the agent's original recommendation would have earned. Four specialized counterfactual methods (ATP, inventory, PO, general) + site-window BSC for systemic impact.

2. **Propensity-Score Matching** (`causal_matching_service.py`): Daily job finds matched pairs of overridden vs. non-overridden decisions with similar state vectors (L2 distance on normalized features). Enables causal treatment effect estimation for Tier 2 decisions.

3. **Bayesian Override Effectiveness** (`override_effectiveness_service.py`): Each (user, TRM type) pair carries a Beta(α, β) posterior tracking whether that user's overrides improve outcomes. Feeds directly into TRM training weights — users with historically beneficial overrides get higher training influence.

4. **Conformal Decision Theory** (`conformal_prediction/conformal_decision.py`, `cdt_calibration_service.py`): Every TRM decision carries a distribution-free risk bound P(loss > threshold). Calibrated hourly from historical decision-outcome pairs. Governs autonomous vs. escalated execution.

5. **Outcome Collection Pipeline** (`outcome_collector.py`, `relearning_jobs.py`): Three parallel collection paths — SiteAgentDecision (:30), all 11 TRM types (:32), Claude Skills decisions (:33). Feedback horizons matched to decision type (ATP: 4h, PO: 7d, inventory buffer: 14d).

**Why this matters**: Causal AI is what makes the learning flywheel trustworthy. Without it, the system would learn from spurious correlations — an agent that happened to increase orders during a demand surge would appear successful, even though any action would have succeeded. With causal inference, the system learns *which specific decision patterns actually cause better outcomes*, producing agents that generalize to novel situations rather than overfitting to historical accidents.

**Implementation files**: `outcome_collector.py`, `override_effectiveness_service.py`, `causal_matching_service.py`, `conformal_prediction/conformal_decision.py`, `cdt_calibration_service.py`, `relearning_jobs.py`
**Database tables**: `override_effectiveness_posteriors`, `override_causal_match_pairs`, `powell_*_decisions` (11 tables with outcome columns)
**Documentation**: [OVERRIDE_EFFECTIVENESS_METHODOLOGY.md](docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md), [POWELL_APPROACH.md](POWELL_APPROACH.md) §5.9.10

---

## Tech Stack

**Backend**: FastAPI (Python 3.10+), SQLAlchemy 2.0, PyTorch 2.2.0, PyTorch Geometric
**Frontend**: React 18, Material-UI 5, Recharts, D3-Sankey
**Database**: PostgreSQL 15+
**Infrastructure**: Docker, Docker Compose, Nginx proxy
**AI/ML**: PyTorch (TRM/GNN), OpenAI API (LLM agents)

---

## Development Commands

### Starting the Application

```bash
# CPU mode (default)
make up

# GPU mode (requires NVIDIA Docker)
make up FORCE_GPU=1
# or
make gpu-up

# Development mode with overrides
make up-dev

# Remote access (HTTP)
make up-remote

# HTTPS with self-signed cert
make up-tls
```

### Service Management

```bash
# Stop containers (keeps volumes)
make down

# View logs
make logs

# Restart backend only
make restart-backend

# Restart frontend only
make restart-frontend

# Rebuild backend
make rebuild-backend

# Rebuild frontend
make rebuild-frontend
```

### Database Operations

```bash
# Initialize database (first time)
docker compose exec backend python -m app.db.init_db

# Bootstrap defaults (configs, users, games)
make db-bootstrap

# Reset games and rebuild training data
make db-reset

# Completely rebuild database
make rebuild-db

# Reseed after rebuild
make reseed-db

# Reset admin password to Autonomy@2026
make reset-admin
```

### LLM Configuration

```bash
# Check LLM endpoint connectivity
make llm-check
```

Environment variables in `.env`:
```env
# LLM Configuration (vLLM, Ollama, or any OpenAI-compatible API)
LLM_API_BASE=http://localhost:8001/v1    # vLLM or Ollama endpoint
LLM_API_KEY=not-needed                    # Only needed for hosted APIs
LLM_MODEL_NAME=qwen3-8b                  # Model name served by your provider
AUTONOMY_ENABLE_SUPERVISOR=true           # Default: true
AUTONOMY_ENABLE_GLOBAL_AGENT=false        # Default: false
```
```

### Training & Dataset Generation

```bash
# Generate SimPy training dataset
make generate-simpy-data

# Train temporal GNN (generates data + trains)
make train-gnn

# Train on GPU with custom parameters
make train-default-gpu TRAIN_EPOCHS=50 TRAIN_DEVICE=cuda

# Remote training
make remote-train REMOTE=user@host EPOCHS=50
```

Training parameters:
- `CONFIG_NAME`: Supply chain config to use (default: "Default TBG")
- `SIMPY_NUM_RUNS`: Number of simulation runs (default: 128)
- `SIMPY_TIMESTEPS`: Timesteps per run (default: 64)
- `SIMPY_WINDOW`: History window (default: 52)
- `SIMPY_HORIZON`: Forecast horizon (default: 1)
- `TRAIN_EPOCHS`: Training epochs (default: 10)
- `TRAIN_DEVICE`: cuda or cpu (default: cuda)

### Testing & Debugging

```bash
# Run backend server locally
cd backend
uvicorn main:app --reload

# Run round-by-round debugging script
cd backend
python scripts/manual_round_driver.py --max-rounds 6

# Export scenario history
cd backend
python scripts/export_round_history.py --scenario-id <id>

# Play a naive agent scenario
cd backend
python scripts/play_naive_agent_Default_Beer_Game.py
```

### Proxy Management

```bash
# Restart proxy (picks up config changes)
make proxy-restart

# Force recreate proxy container
make proxy-recreate

# View proxy logs
make proxy-logs
```

---

## Architecture

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
- `conformal_orchestrator.py`: Automatic conformal prediction feedback loop for demand, lead time, price, yield, and service level (forecast load hooks, multi-entity actuals observation, drift monitoring, scheduled recalibration, suite ↔ DB persistence)
- `agent_context_explainer.py`: Context-aware explainability orchestrator — authority boundaries, guardrails, policy parameters, conformal intervals, feature attribution, counterfactuals for all 11 TRM agents and both GNN models
- `explanation_templates.py`: 39 Jinja2-style templates (13 agent types × 3 verbosity levels) for inline decision explanations
- `decision_stream_service.py`: Decision Stream inbox — collects decisions from all 11 powell_*_decisions tables, routes via 3-dimensional framework: **Urgency** (cost_of_inaction × time_pressure), **Likelihood** (agent confidence), **Benefit** (expected $ net gain). Per-tenant thresholds in `tenant_bsc_config` (`urgency_threshold` default 0.65, `likelihood_threshold` default 0.70, `benefit_threshold` default $0). Per-TRM-type overrides in `tenant_decision_thresholds`. Queue sort is Kahneman-aligned: urgency DESC (loss prevention first — Prospect Theory: losses loom ~2× larger than gains), benefit DESC, likelihood ASC. Digest persisted to `decision_stream_digests` table. See [DECISION_ROUTING.md](docs/internal/DECISION_ROUTING.md) for full framework and [POWELL_APPROACH.md](docs/internal/POWELL_APPROACH.md) §5.21 for integration details.

- `scenario_event_service.py`: Scenario event injection — 24 event types across 5 categories (Demand: 7, Supply: 6, Capacity: 5, Logistics: 3, Macro: 3). Creates scenario branches, modifies DB records, triggers CDC. SAP S/4HANA IDES compatible. Event catalog dynamically injected into Talk to Me LLM prompt via `_build_event_catalog_for_llm()`.

**API Endpoints** (`api/endpoints/`):
- `mps.py`: Master Production Scheduling endpoints
- `supply_plan.py`: Supply plan generation and approval
- `mixed_scenario.py`: Beer Game API (human + AI scenarios)
- `agent_scenario.py`: Pure agent scenario API
- `supply_chain_config.py`: Supply chain network configuration
- `model.py`: Training and dataset generation endpoints
- `auth.py`: Authentication (login, register, MFA)
- `websocket.py`: Real-time scenario updates
- `user_directives.py`: "Talk to Me" directive capture (analyze/submit/list)
- `provisioning.py`: Powell Cascade 14-step provisioning stepper
- `email_signals.py`: GDPR-safe email signal ingestion and management
- `agent_stochastic_params.py`: Per-agent stochastic parameters CRUD, pipeline config settings

**Database Models** (`models/`):
- `aws_sc_planning.py`: AWS SC planning entities (forecast, supply_plan, sourcing_rules, inv_policy, etc.)
- `supply_chain_config.py`: Network topology (SupplyChainConfig, Node, Lane, Item, Market)
- `scenario.py`: Scenario, Period, ScenarioUserAction (simulation module)
- `participant.py`: ScenarioUser, ScenarioUserRole, ScenarioUserPeriod (simulation module)
- `agent_config.py`: AgentConfig, AgentScenarioConfig
- `agent_stochastic_param.py`: AgentStochasticParam, TRM_PARAM_MAP, STOCHASTIC_CONFIG_DEFAULTS, pipeline config helpers
- `tenant.py`: Tenant model (Autonomy organization/tenant)
- `user.py`: User, Role, Permission
- `rbac.py`: Role-Based Access Control
- `gnn/`: GNN model definitions

**Business Logic**:
- `agents/`: Agent strategy implementations
- `simulation/`: SimPy-based simulation for dataset generation
- `rl/`: Reinforcement learning components
- `data/`: Data processing utilities
- `utils/`: Helper utilities

### Frontend Structure (`frontend/src/`)

**Planning Pages** (`pages/planning/` — 43+ pages implemented):
- `MasterProductionScheduling.jsx`: MPS plan management with approval workflow
- `DemandPlanView.jsx` / `DemandPlanEdit.jsx`: Demand forecasting with versioning
- `SupplyPlanGeneration.jsx` / `SupplyWorklistPage.jsx`: Supply plan generation and worklist
- `InventoryOptimization.jsx`: Safety stock policy management (5 policy types)
- `CapacityPlanning.jsx`: Resource capacity, requirements, bottleneck analysis
- Plus: S&OP, cascade dashboard, ATP/rebalancing/PO/order tracking worklists, lot sizing, execution pages

**Simulation Pages** (`pages/`):
- `ScenarioBoard.jsx`: Main Beer Game interface
- `ScenariosList.jsx`: Scenario browser
- `CreateMixedScenario.jsx`: Scenario creation wizard
- `ScenarioReport.jsx`: Post-scenario analytics
- `ScenarioVisualizations.jsx`: Charts and metrics

**Admin Pages** (`pages/admin/` — 25+ pages implemented):
- `TRMDashboard.jsx`: TRM training interface (training/model manager/testing tabs)
- `GNNDashboard.jsx`: GNN training with config-specific models
- `GraphSAGEDashboard.jsx`: S&OP GraphSAGE medium-term model training
- `HiveDashboard.jsx`: TRM Hive visualization (urgency vectors, signal bus, decision cycle phases)
- `PowellDashboard.jsx`: Powell SDAM framework dashboard (state/policy/decision/outcomes)
- `RLDashboard.jsx` / `RLHFDashboard.jsx`: RL and RLHF training interfaces
- `KnowledgeBase.jsx`: RAG document management, vector search, embedding config
- `SkillsDashboard.jsx`: Claude Skills monitoring (stats, RAG memory, escalation metrics)
- `SAPDataManagement.jsx`: SAP integration (connections, field mapping, ingestion, insights)
- `StochasticParamsEditor.jsx`: Per-agent stochastic parameters (TRM distributions, pipeline settings, source tracking)
- `EmailSignalsDashboard.jsx`: GDPR-safe email signal ingestion (connections, signals, analytics, test)
- `SyntheticDataWizard.jsx`: AI-guided company/data generation wizard
- `ModelSetup.jsx`: Model architecture configuration
- `UserManagement.jsx` / `UserRoleManagement.jsx`: User and role administration
- `TenantManagement.jsx`: Tenant management
- `PlanningHierarchyConfig.jsx`: MPS/MRP/S&OP hierarchy configuration
- `ScenarioTreeManager.jsx`: Git-like scenario branching
- `AuthorizationProtocolBoard.jsx`: AAP cross-functional negotiation visualization
- `Governance.jsx` / `ExceptionWorkflows.jsx` / `ApprovalTemplates.jsx`: Governance and workflows

**Components** (`components/`):
- `supply-chain-config/`: Network configuration UI with D3-Sankey diagrams
- `supply-plan/`: Supply plan generation wizard components
- `scenario/`: Scenario board, inventory display, order forms
- `charts/`: Recharts-based visualizations
- `admin/`: Admin-specific components
- `common/`: Shared UI components

**Services** (`services/`):
- `api.js`: Axios-based API client
- `auth.js`: Authentication service
- `scenarioService.js`: Scenario state management

### Supply Chain DAG System

The system uses a **4-master-type DAG model**:

1. **Market Supply**: Upstream source sites (suppliers)
2. **Market Demand**: Terminal demand sink sites (customers)
3. **Inventory**: Storage/fulfillment sites (Distributor, Wholesaler, Retailer, DC, Component Supplier)
4. **Manufacturer**: Transform sites with Bill of Materials (BOM)

**Key Concepts**:
- Each site has both an SC site type (human-friendly) and master type (routing)
- Transportation lanes (edges) define material flow between sites
- BOMs define transformation ratios (e.g., Case = 4 Six-Packs)
- Products flow through the network based on DAG topology
- Supports convergent (many-to-one), divergent (one-to-many), and serial (linear) topologies

See [DAG_Logic.md](DAG_Logic.md) for detailed master site type mappings and config examples.

### Agent System Architecture

**TRM Hive Model** (✅ IMPLEMENTED): Each site's TRM agents form a self-organizing "hive" with intra-hive signal propagation (HiveSignalBus, UrgencyVector) and the tGNN as inter-hive connective tissue. **Site-specific hive composition**: The active TRM set is determined by the site's `master_type` from the DAG topology — manufacturers get all 11 TRMs, distribution centers get 7 (no MO, Quality, Maintenance, Subcontracting), retailers get 6, and market nodes get 1 (order_tracking only). See `site_capabilities.py` for the full mapping. Layer 1.5 (Site tGNN hourly) provides learned cross-TRM causal coordination within a single site, capturing trade-offs that reactive signals alone cannot model; inactive TRM nodes are masked (zero features, zero output). Integrates with the [Agentic Authorization Protocol](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md) for cross-authority negotiation and includes a Kinaxis-inspired embedded scenario architecture where agents create branched what-if scenarios at machine speed. **Neural architecture**: Three-layer hybrid — stigmergic coordination (S-MADRL pheromones), heterogeneous graph attention (HetNet), and recursive per-head refinement (Samsung TRM) — totaling ~473K params at <10ms latency. See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 14 for architecture specification, Section 15 for digital twin training pipeline, Section 16 for multi-site coordination stack, and [TRM_RESEARCH_SYNTHESIS.md](TRM_RESEARCH_SYNTHESIS.md) Section 8 for research foundations.

**Multi-Site Coordination Stack** (5 layers, see [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 16):
- **Layer 1 — Intra-Hive** (<10ms): UrgencyVector + HiveSignalBus within a single site
- **Layer 1.5 — Site tGNN** (hourly): Learned cross-TRM causal coordination within a single site (~25K params, GATv2+GRU, 11 TRM-type nodes with ~22 causal edges)
- **Layer 2 — Network tGNN** (daily): S&OP embeddings + transactional data → inter-site directives
- **Layer 3 — AAP Cross-Authority** (seconds-minutes): Authorization requests for cross-site actions
- **Layer 4 — S&OP Consensus Board** (weekly): Policy parameters θ negotiated by functional agents
- **Key principle**: TRMs never call across sites. All cross-site information flows through the tGNN directive or AAP authorization. Site tGNN (Layer 1.5) provides learned cross-TRM causal coordination within a single site, sitting between reactive signals and daily network inference.

**Digital Twin Training Pipeline** (✅ IMPLEMENTED, see [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 15): Six-phase cold-start pipeline using platform simulation capabilities as digital twin — (1) Individual BC warm-start from curriculum, (2) Multi-head coordinated traces from SimPy/Beer Game, (3) Site tGNN training from coordinated traces (BC + PPO), (4) Stochastic stress-testing via Monte Carlo (TRMs + Site tGNN active), (5) Copilot calibration from human overrides (Site tGNN in shadow mode), (6) Autonomous CDC relearning from production outcomes. Implementation files: `hive_curriculum.py` (1,126 lines), `hive_feedback.py` (6,957 lines), `inter_hive_signal.py` (7,613 lines), `coordinated_sim_runner.py` (12,314 lines), `decision_cycle.py` (7,583 lines), `site_tgnn_trainer.py`.

**Strategy Types** (see [AGENT_SYSTEM.md](AGENT_SYSTEM.md)):
- `naive`: Mirrors incoming demand (baseline)
- `bullwhip`: Intentionally over-orders to demonstrate volatility
- `conservative`: Maintains stable orders, high safety stock
- `ml_forecast`: ML-based demand prediction (uses TRM or GNN)
- `optimizer`: Cost function optimization
- `reactive`: Rapid response to inventory changes
- `llm`: Routes to OpenAI-based multi-agent system

**LLM Multi-Agent System** ([llm_agent/beer_game_openai_agents.py](backend/llm_agent/beer_game_openai_agents.py)):
- **Site Agents**: Per-role agents (retailer, wholesaler, distributor, factory) with structured JSON schemas
- **Supervisor Agent**: Reviews and validates site agent proposals, can clamp/rewrite orders
- **Global Planner Agent**: Optional rolling base-stock and variance target planning
- **BeerGameAgentsOrchestrator**: Manages agent lifecycle and tool registry

**Temporal GNN** ([backend/app/models/gnn/](backend/app/models/gnn/)):
- `SupplyChainTemporalGNN`: GAT-based message passing + temporal processing
- `SupplyChainAgent`: Per-node inference and training wrapper
- Training via `scripts/training/train_gnn.py` and `train_gpu_default.py`

**TRM Agent** (Tiny Recursive Model):
- 5-phase curriculum learning (single-site → 2-site → 4-site Beer Game → multi-echelon → production)
- Per-site state encoding (inventory, backlog, pipeline, demand history, role, position)
- 3-step recursive refinement for improved decisions
- Training via curriculum generator and dedicated training script

**Powell Framework - Narrow TRM Services** ([backend/app/services/powell/](backend/app/services/powell/)):

The Powell SDAM framework constrains TRMs to narrow execution decisions:

| Service | Scope | Decision |
|---------|-------|----------|
| `AllocationService` | Priority × Product × Location | Manages tGNN-generated allocations |
| `ATPExecutorTRM` | Per order, <10ms | AATP consumption with priority sequence |
| `InventoryRebalancingTRM` | Cross-location, daily | Transfer recommendations |
| `POCreationTRM` | Per product-location | PO timing and quantity |
| `OrderTrackingTRM` | Per order, continuous | Exception detection and actions |
| `MOExecutionTRM` | Per production order | Release, sequence (Glenday + nearest-neighbor), split, expedite, defer |
| `TOExecutionTRM` | Per transfer order | Release, consolidate, expedite, defer |
| `QualityDispositionTRM` | Per quality order | Accept, reject, rework, scrap, use-as-is |
| `MaintenanceSchedulingTRM` | Per asset/work order | Schedule, defer, expedite, outsource |
| `SubcontractingTRM` | Per make-vs-buy decision | Internal, external, split routing |
| `ForecastAdjustmentTRM` | Per signal (email/voice/market) | Adjust forecast direction and magnitude |
| `InventoryBufferTRM` | Per product-location | Inventory buffer adjustment and reoptimization |

**Context-Aware Explainability**: All 11 TRM agents and both GNN models support context-aware explanations via `AgentContextExplainer`. Every decision includes authority boundaries, active guardrails, model attribution (gradient saliency for TRMs, attention weights for GNNs), conformal prediction intervals, and counterfactual analysis. Available at VERBOSE/NORMAL/SUCCINCT levels via Ask Why API endpoints.

**AATP Consumption Logic** (critical):
```python
# Consumption sequence for order at priority P:
# 1. Own tier (P) first
# 2. Bottom-up from lowest priority (5→4→3→...)
# 3. Stop at own tier (cannot consume above)
# Example: P=2 order → [2, 5, 4, 3] (skips 1)
```

Database tables: `powell_allocations`, `powell_atp_decisions`, `powell_rebalance_decisions`, `powell_po_decisions`, `powell_order_exceptions`, `powell_mo_decisions`, `powell_to_decisions`, `powell_quality_decisions`, `powell_maintenance_decisions`, `powell_subcontracting_decisions`, `powell_forecast_adjustment_decisions`, `powell_buffer_decisions`

**CDC → Relearning Feedback Loop** (see [POWELL_APPROACH.md](POWELL_APPROACH.md) Section 5.9.9):

Autonomous closed-loop pipeline for continuous TRM improvement and CDT calibration:

```
TRM decisions → [powell_*_decisions] (11 tables)
       ↓ (hourly at :32)
OutcomeCollector.collect_trm_outcomes() fills actual outcome columns
       ↓ (hourly at :35)
CDTCalibrationService.calibrate_incremental() → DecisionOutcomePair → CDT wrappers
       ↓
All 11 TRM decisions carry risk_bound = P(loss > τ)
       ↓
CDCMonitor fires → [powell_cdc_trigger_log]
       ↓ (every 6h at :45)
CDCRetrainingService evaluates need → TRMTrainer.train() → checkpoint
       ↓
SiteAgent reloads model
```

| Component | Schedule | Purpose |
|-----------|----------|---------|
| `OutcomeCollectorService.collect_outcomes()` | Hourly (:30) | Compute outcomes for SiteAgentDecision (ATP=4h, Inv=24h, PO=7d, CDC=24h) |
| `OutcomeCollectorService.collect_trm_outcomes()` | Hourly (:32) | Compute outcomes for all 11 powell_*_decisions tables |
| `CDTCalibrationService.calibrate_incremental()` | Hourly (:35) | Feed new decision-outcome pairs into CDT wrappers |
| `CDTCalibrationService.calibrate_all()` | Startup (batch) | Batch calibrate CDT wrappers from all historical data |
| `CDCRetrainingService` | Every 6h (:45) | Evaluate & execute retraining when ≥100 experiences + CDC trigger + cooldown elapsed |
| `SiteTGNNInferenceService` | Hourly (:25) | Intra-site cross-TRM urgency modulation (Layer 1.5) |
| `SiteTGNNTrainer` | Every 12h (:50) | Evaluate & train Site tGNN from MultiHeadTrace data |
| `_run_cfa_optimization()` | Weekly (Sun 04:00) | CFA policy parameter re-optimization via Differential Evolution across all active configs |
| `ConditionMonitorService` | On-demand | 6 real-time DB condition checks (ATP shortfall, inventory, capacity, orders past due, forecast deviation) |

Database tables: `powell_cdc_trigger_log`, `powell_site_agent_decisions`, `powell_site_agent_checkpoints`, `powell_cdc_thresholds`

API endpoints:
- `GET /site-agent/cdc/triggers/{site_key}` — Trigger history
- `GET /site-agent/retraining/status/{site_key}` — Checkpoint, readiness, pending experiences
- `POST /site-agent/retraining/trigger/{site_key}` — Manual retraining (background)

**Override Effectiveness Tracking** (see [POWELL_APPROACH.md](POWELL_APPROACH.md) Section 5.9.10):

Human overrides are scored using **Bayesian Beta posteriors** per `(user_id, trm_type)` with tiered causal inference. The posterior `Beta(α, β)` starts from uninformative `Beta(1,1)` (E[p]=0.50, training_weight=0.85) and updates as outcomes are observed. Three observability tiers control signal strength: Tier 1 (analytical counterfactual for ATP/forecast/quality, signal=1.0), Tier 2 (propensity-score matching for MO/TO/PO, signal=0.3-0.9), Tier 3 (minimal for safety stock/maintenance, signal=0.15). Training weight formula: `0.3 + 1.7 × E[p]`, capped by certainty discount.

**Systemic impact**: Overrides are measured at two scopes — decision-local (counterfactual comparison) and site-window (balanced scorecard delta comparing aggregate site performance pre vs post override). Composite score = `0.4 × local_delta + 0.6 × site_bsc_delta` feeds into the Bayesian posterior to prevent locally-good but systemically-harmful overrides from inflating training weights.

**Causal learning pipeline**: Progresses from Bayesian priors → propensity-score matching → doubly robust estimation → causal forests (Athey & Imbens 2018) that identify *when* overrides help vs. hurt. See [docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md](docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md) for full methodology including mathematical appendix.

- **Model**: `backend/app/models/override_effectiveness.py` — `OverrideEffectivenessPosterior`, `CausalMatchPair`
- **Service**: `backend/app/services/override_effectiveness_service.py` — Bayesian posterior management
- **Systemic**: `backend/app/services/powell/outcome_collector.py` — `_compute_site_window_bsc()` method
- **API**: `GET /decision-metrics/override-posteriors` — Per-user posterior summaries with 90% credible intervals
- **Database tables**: `override_effectiveness_posteriors`, `override_causal_match_pairs`

See [POWELL_APPROACH.md](POWELL_APPROACH.md) for full framework documentation.

### AWS SC Planning Flow

**3-Step Planning Process** (AWS SC standard):

1. **Demand Processing** ([demand_processor.py](backend/app/services/aws_sc_planning/demand_processor.py)):
   - Aggregate demand from forecasts and customer orders
   - Net out committed/allocated inventory
   - Time-phase demand across planning horizon

2. **Inventory Target Calculation** ([inventory_target_calculator.py](backend/app/services/aws_sc_planning/inventory_target_calculator.py)):
   - Calculate safety stock using 8 policy types:
     - `abs_level`: Fixed quantity
     - `doc_dem`: Days of coverage (demand-based)
     - `doc_fcst`: Days of coverage (forecast-based)
     - `sl`: Service level with z-score
     - `sl_fitted`: Service level with MLE-fitted distributions (Monte Carlo DDLT)
     - `conformal`: Conformal Risk Control with distribution-free guarantee
     - `sl_conformal_fitted`: Hybrid fitted + conformal
     - `econ_optimal`: Marginal economic return (stock where stockout_cost × P(demand>k) > holding_cost)
   - Apply hierarchical overrides (Product-Site > Product > Site > Config)
   - Generate target inventory levels

3. **Net Requirements Calculation** ([net_requirements_calculator.py](backend/app/services/aws_sc_planning/net_requirements_calculator.py)):
   - Time-phased netting (gross - on-hand - scheduled receipts)
   - Multi-level BOM explosion (recursive component requirements)
   - Sourcing rule processing (buy/transfer/manufacture with priorities)
   - Lead time offsetting
   - Generate supply plans (PO/TO/MO requests)

### Scenario Engine Flow (Simulation Module)

1. **Initialization**: Create `BeerLine` with nodes and policies
2. **Period Tick** ([engine.py:BeerLine.tick()](backend/app/services/engine.py)):
   - Process incoming shipments → update inventory
   - Fulfill demand/backlog → calculate shipments to downstream
   - Receive orders from downstream → update node state
   - Agent decides order quantity → place order upstream
   - Update costs and metrics
3. **State Persistence**: Save `ScenarioUserPeriod` records to database
4. **Analytics**: Compute bullwhip metrics, service levels, costs

### Database Schema

**AWS SC Planning Tables**:
- `forecast`: Demand forecasts with P10/P50/P90 percentiles
- `supply_plan`: Generated supply plans (PO/TO/MO requests)
- `sourcing_rules`: Buy/transfer/manufacture rules with priorities
- `inv_policy`: Inventory policies (4 types) with hierarchical overrides
- `inv_level`: Current inventory levels
- `product_bom`: Bill of materials with scrap rates
- `production_process`: Manufacturing process definitions
- `vendor_product`: Vendor-specific product attributes
- `vendor_lead_time`: Vendor lead times
- `supply_planning_parameters`: Global planning parameters

**Network Configuration Tables**:
- `supply_chain_configs`: Network topology definitions
- `site`: Supply chain sites (AWS SC standard)
- `transportation_lane`: Transportation lanes (material flow edges)
- `product`: Products (AWS SC standard)
- `market`: Market demand/supply sites

**Simulation Tables**:
- `scenarios`: Beer Game sessions
- `scenario_users`: ScenarioUser assignments to scenarios
- `periods`: Per-period scenario state
- `scenario_user_periods`: Per-scenario-user per-period metrics
- `agent_configs`: Agent strategy configurations
- `agent_scenario_configs`: Agent-to-scenario mappings

**Organization Tables**:
- `users`: User accounts with role-based access
- `tenants`: Autonomy tenants/organizations (equivalent to AWS SC `company`)
- `roles`: RBAC roles
- `permissions`: Granular permissions
- `user_roles`: Role assignments

**SAP Data Staging Tables** (intermediate layer between SAP and AWS SC entities):
- `sap_extraction_runs`: One row per extraction batch — metadata, row counts by category, delta summary, MANIFEST
- `sap_staging_rows`: Raw SAP data preserved in JSONB — audit trail, delta detection via `row_hash`, business key indexing
- `sap_table_schemas`: Column set tracking per SAP table per tenant — schema drift detection
- `sap_connections`: SAP system connection configurations (OData, RFC, CSV, IDoc)

**SAP Data Architecture** (PostgreSQL-first, schema per ERP vendor):
- **Staging schema**: `sap_staging` — separate PostgreSQL schema for raw SAP data. Vendor is implicit from schema name (future: `oracle_staging`, `d365_staging`)
- **Three staging tables**: `sap_staging.extraction_runs` (header), `sap_staging.rows` (detail — JSONB per row), `sap_staging.table_schemas` (column tracking)
- **Two-phase loading**: Phase 1 = ERP → staging tables (raw data preservation). Phase 2 = staging → AWS SC entity tables (mapping via SAPConfigBuilder). Phases are independent — staging can succeed even if mapping fails, and mapping can be re-run from staging without re-extracting
- **CSV folder watching**: CSVs dropped into `imports/{TENANT_NAME}/{ERP_VARIANT}/` auto-ingest into staging schema. Extraction timestamp = max(file modification times). Batch completeness check before loading
- **CDC via delta detection**: `row_hash` comparison between consecutive staging snapshots gives change tracking even for CSV-only customers without native ERP CDC
- **Data categories**: Master (weekly), Transaction (daily), CDC (hourly)
- **SAP Table Registry**: `SAP_TABLE_REGISTRY` in `backend/app/models/sap_staging.py` — 60+ SAP tables with category, key fields, descriptions
- **Tenant ERP config**: `erp_vendor`, `erp_variant`, `import_base_dir`, `export_base_dir`, `erp_retention_snapshots` on Tenant model. Multi-ERP per tenant supported (different connections → different staging runs)
- **Staging repository**: `backend/app/services/sap_staging_repository.py` — `start_extraction()`, `stage_table()`, `complete_extraction()`, `get_staged_data()`, `compute_delta()`, `enforce_retention()`
- **Download failure handling**: Missing expected tables → warning. Previously-populated tables now empty → error alert. Connection failures → retry with backoff, then alert

**Directive & Signal Tables**:
- `user_directives`: Natural language directive capture, LLM parsing, Powell routing, effectiveness tracking
- `config_provisioning_status`: 14-step provisioning pipeline with dependency tracking
- `email_connections`: IMAP/Gmail inbox configurations per tenant
- `email_signals`: GDPR-safe supply chain signals extracted from emails (no PII stored)

**Powell Framework Tables** (see [POWELL_APPROACH.md](POWELL_APPROACH.md)):
- `powell_belief_state`: Uncertainty quantification via conformal prediction (auto-populated by orchestrator)
- `powell_calibration_log`: Audit trail of predicted vs actual values for conformal recalibration
- `powell_policy_parameters`: Optimized policy parameters (θ) from CFA
- `powell_value_function`: VFA state values for tabular fallback
- `powell_hierarchical_constraints`: Consistency constraints across planning levels
- `powell_exception_resolution`: Exception handling decisions for VFA learning
- `powell_stochastic_solution`: Solutions from stochastic programming
- `powell_allocations`: Priority × Product × Location allocations from tGNN
- `powell_atp_decisions`: ATP decision history for TRM training
- `powell_rebalance_decisions`: Rebalancing decision history
- `powell_po_decisions`: PO creation decision history
- `powell_order_exceptions`: Order tracking exception history
- `powell_mo_decisions`: Manufacturing order execution decisions
- `powell_to_decisions`: Transfer order execution decisions
- `powell_quality_decisions`: Quality disposition decisions
- `powell_maintenance_decisions`: Maintenance scheduling decisions
- `powell_subcontracting_decisions`: Subcontracting routing decisions
- `powell_forecast_adjustment_decisions`: Forecast adjustment decisions
- `powell_buffer_decisions`: Inventory buffer adjustment decisions
- `override_effectiveness_posteriors`: Bayesian Beta posteriors per (user, trm_type) for override quality tracking
- `override_causal_match_pairs`: Matched override vs non-override decision pairs for causal inference

---

## Key Implementation Details

### Authentication
- JWT tokens with HTTP-only cookies
- CSRF protection via double-submit cookie pattern
- Role-based access: SYSTEM_ADMIN, GROUP_ADMIN, PLAYER
- MFA support via TOTP (PyOTP)
- Capability-based permissions (view_mps, manage_mps, approve_mps, etc.)

### WebSocket Updates
Real-time scenario state broadcasting on period completion:
```python
# backend/app/api/endpoints/mixed_scenario.py
await manager.broadcast_to_scenario(scenario_id, {
    "type": "period_completed",
    "data": period_data
})
```

### Agent Decision Flow
```python
# backend/app/services/agents.py
policy = get_policy_by_strategy(strategy_name)
order_quantity = policy.compute_order(node, context)
```

For LLM agents:
```python
# backend/app/services/llm_agent.py
response = orchestrator.call_beer_game_gpt(
    node_context, supervisor=True, global_agent=False
)
order_quantity = response["order_upstream"]
```

### Training Pipeline
1. Generate synthetic data via SimPy simulation (`generate_simpy_dataset.py`)
2. Build graph tensors from scenario history
3. Train temporal GNN (`train_gpu_default.py` or `train_gnn.py`)
4. Save checkpoint to `backend/checkpoints/`
5. Load in agent service for inference

### Frontend API Integration
```javascript
// frontend/src/services/api.js
const api = axios.create({
  baseURL: '/api',
  withCredentials: true
});
```

All API calls go through the Nginx proxy which routes:
- `/api/*` → Backend (port 8000)
- `/*` → Frontend (port 3000)

---

## Docker Compose Files

- `docker-compose.yml`: Base stack (proxy, frontend, backend, db, pgadmin)
- `docker-compose.dev.yml`: Dev overrides with hot-reload
- `docker-compose.gpu.yml`: GPU-enabled backend with NVIDIA runtime
- `docker-compose.prod.yml`: Production deployment (Gunicorn)
- `docker-compose.apps.yml`: Frontend + backend only (external DB)
- `docker-compose.db.yml`: Standalone database

Layer files with `-f` flag:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

---

## Environment Setup

```bash
# Initialize .env from template
make init-env

# Key variables
DATABASE_TYPE=postgresql
POSTGRESQL_HOST=db
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=autonomy
POSTGRESQL_USER=autonomy_user
POSTGRESQL_PASSWORD=<your-password>
SECRET_KEY=<generate-random-key>
LLM_API_BASE=http://localhost:8001/v1
LLM_API_KEY=not-needed
LLM_MODEL_NAME=qwen3-8b
```

---

## Common Workflows

### AWS SC Planning Workflow

1. **Load Supply Chain Configuration**:
   - GET `/api/v1/supply-chain-configs` to list configs
   - Select config with desired network topology

2. **Generate Supply Plan**:
   ```python
   # Create supply plan
   POST /api/v1/supply-plan/generate
   {
     "config_id": 1,
     "planning_horizon": 52,
     "stochastic_params": {...},
     "objectives": {...}
   }
   # Returns task_id for async processing
   ```

3. **Monitor Progress**:
   ```python
   GET /api/v1/supply-plan/status/{task_id}
   # Check progress: PENDING → RUNNING → COMPLETED
   ```

4. **Review Results**:
   ```python
   GET /api/v1/supply-plan/result/{task_id}
   # Returns probabilistic balanced scorecard
   ```

5. **Approve and Execute**:
   ```python
   POST /api/v1/supply-plan/approve/{task_id}
   # Releases plan for execution
   ```

### Adding a New Agent Strategy

1. Implement strategy in `backend/app/services/agents.py`
2. Register in `AgentStrategy` enum
3. Add strategy to `get_policy_by_strategy()` factory
4. Update [AGENT_SYSTEM.md](AGENT_SYSTEM.md) documentation

### Creating a New Supply Chain Config

1. Use admin UI or POST to `/api/v1/supply-chain-configs`
2. Define sites with master types (MARKET_SUPPLY, MARKET_DEMAND, INVENTORY, MANUFACTURER)
3. Create transportation lanes connecting sites
4. Define products and BOMs for manufacturers
5. Validate DAG topology

### Running a Beer Game Simulation

1. Create scenario via `/api/v1/mixed-scenarios/` or `/api/v1/agent-scenarios/`
2. Assign scenario users (human or AI)
3. POST to `/start` endpoint
4. Iteratively POST to `/execute-period` for each period
5. GET `/state` or `/history` for analytics

### Debugging a Scenario Issue

1. Start backend with `uvicorn main:app --reload`
2. Run `scripts/manual_period_driver.py` to step through periods
3. Set breakpoints in `engine.py:BeerLine.tick()` or agent strategy
4. Inspect `node.inventory`, `node.backlog`, `node.pipeline_shipments`
5. Check `ScenarioUserPeriod` records in database for historical state

### Creating Synthetic Data for Testing

The platform includes an AI-guided wizard for generating complete synthetic supply chain data.

**Using the API (Direct Generation)**:
```python
POST /api/v1/synthetic-data/generate
{
    "group_name": "Test Corp",
    "company_name": "Test Company",
    "archetype": "manufacturer",  # retailer, distributor, or manufacturer
    "admin_email": "admin@test.com",
    "admin_name": "Test Admin",
    "agent_mode": "copilot"
}
```

**Using the Claude Wizard (Interactive)**:
```python
# 1. Start session
POST /api/v1/synthetic-data/wizard/sessions
# Returns session_id

# 2. Chat with wizard
POST /api/v1/synthetic-data/wizard/sessions/{session_id}/messages
{"message": "I want to create a manufacturer company called ACME"}

# 3. Generate when ready
POST /api/v1/synthetic-data/wizard/sessions/{session_id}/generate
```

**Company Archetypes**:
- **Retailer**: Multi-channel retail (CDCs → RDCs → Stores + Online), 200 SKUs, copilot mode
- **Distributor**: Wholesale distribution (NDCs → RDCs → LDCs), 720 SKUs, copilot mode
- **Manufacturer**: Multi-tier production (Plants → Sub-Assy → Component), 160 SKUs, autonomous mode

**What Gets Created**:
- Tenant (organization) and admin user
- Supply chain config with sites, transportation lanes, products
- Site and product hierarchies (Company→Region→Country→Site, Category→Family→Group→Product)
- Forecasts with P10/P50/P90 percentiles
- Inventory policies (DOC-based safety stock)
- Planning hierarchy configurations (MPS, MRP, S&OP)
- AI agent configurations

**Implementation Files**:
- `backend/app/services/synthetic_data_generator.py` - Core generation logic
- `backend/app/services/synthetic_data_wizard.py` - Claude-powered wizard
- `backend/app/api/endpoints/synthetic_data.py` - REST API endpoints
- `frontend/src/pages/admin/SyntheticDataWizard.jsx` - Admin UI

**Related Services**:
- `backend/app/services/aggregation_service.py` - Hierarchy-based aggregation (Powell state abstraction)
- `backend/app/services/disaggregation_service.py` - Policy-based disaggregation (Powell allocation)

### ERP Data Management (SAP, D365, Odoo)

The platform integrates with enterprise ERP systems to extract supply chain data. **All ERP integrations follow the same architecture** — the SAP integration is the template, D365 and Odoo replicate the pattern exactly.

**CRITICAL — ERP Staging Pattern**: All ERP data flows through a **two-phase pipeline**:
1. **Phase 1 — ERP Staging**: Raw ERP data is extracted and stored in an ERP-specific PostgreSQL schema (`sap_staging`, `d365_staging`, `odoo_staging`) as JSONB rows. This preserves the original data for audit trail, delta detection, and replay.
2. **Phase 2 — AWS SC Mapping**: Staged rows are mapped to the canonical AWS SC data model entities in the `public` schema (site, product, product_bom, inv_level, etc.) via the 3-tier field mapping service (exact → pattern → fuzzy/AI).

**PostgreSQL Schemas**:
- `sap_staging` — 54 SAP tables (T001W, MARA, STKO, EKKO, VBAK, LIKP, etc.)
- `d365_staging` — 42 D365 entities (ReleasedProductsV2, BillOfMaterialsHeaders, etc.)
- `odoo_staging` — 27 Odoo models (product.product, mrp.bom, stock.quant, etc.)

Each schema has three tables: `extraction_runs` (header per batch), `rows` (JSONB per record), `table_schemas` (column tracking for drift detection).

**Data Categories** (per ERP table/entity):
- **Master** (weekly): products, sites, BOMs, vendors, customers, work centers
- **Transaction** (daily): POs, SOs, production orders, shipments
- **CDC** (hourly): goods receipts, confirmations, status changes, inventory movements

**Supported ERPs**:

| ERP | Connection Methods | Staging Schema | Entity Count | Demo Data |
|-----|-------------------|---------------|-------------|-----------|
| SAP S/4HANA / ECC | RFC, OData, CSV, HANA DB | `sap_staging` | 54 tables | SAP FAA (IDES) |
| Microsoft D365 F&O | OData v4, DMF, CSV | `d365_staging` | 42 entities | Contoso (USMF) via ISV |
| Odoo Community/Enterprise | JSON-RPC, XML-RPC, CSV | `odoo_staging` | 27 models | Docker self-hosted |

**API Endpoints**:
```bash
# Generalized ERP endpoints
GET  /api/v1/erp/supported-erps              # List all supported ERPs
POST /api/v1/erp/field-mapping/{erp_type}    # Get field mapping for ERP model/entity
GET  /api/v1/erp/odoo/models                 # Odoo model list
GET  /api/v1/erp/d365/entities               # D365 entity list

# SAP-specific (legacy, still active)
POST /api/v1/sap-data/connections            # SAP connection management
POST /api/v1/sap-data/field-mapping/match    # SAP field mapping
```

**Implementation Files**:
- **Shared**: `erp_connection.py` (model), `erp_integration.py` (API), `ERPDataManagement.jsx` (UI)
- **SAP**: `sap_staging.py`, `sap_deployment_service.py`, `sap_field_mapping_service.py`, `sap_config_builder.py`
- **D365**: `d365_staging.py`, `integrations/d365/connector.py`, `d365/field_mapping.py`, `d365/extraction_service.py`
- **Odoo**: `odoo_staging.py`, `integrations/odoo/connector.py`, `odoo/field_mapping.py`, `odoo/config_builder.py`

**Scripts**:
- `scripts/rebuild_sap_config_disaggregated.py` — Build config from SAP CSVs
- `scripts/rebuild_d365_contoso_config.py` — Build config from D365 CSVs
- `scripts/extract_d365_contoso.py` — Extract D365 data via OData
- `scripts/translate_sap_to_d365_csvs.py` — Translate SAP IDES → D365 format for demos

**Adding a New ERP**: Follow the SAP template — create staging schema + model registry, connector, field mapping, extraction service, config builder. See [ERP_INTEGRATION_GUIDE.md](docs/external/ERP_INTEGRATION_GUIDE.md) for the full pattern.

**Access**: Navigation > Administration > ERP Data Management (Tenant Admin required)

### Talk to Me — Natural Language Directive Capture & Query Routing

A persistent "Talk to me" input in the TopNavbar accepts natural language input from any user. The system handles two modes: **directives** (actionable instructions routed to Powell layers) and **questions** (informational queries that navigate to the relevant page with pre-applied filters). Directives use a two-phase flow to ensure completeness before routing.

**Two-Phase Flow**:
1. `POST /directives/analyze` — LLM parse + gap detection (no persist). Returns structured fields + `missing_fields` list.
2. If `missing_fields` is non-empty, the UI shows a clarification panel with appropriate inputs (text/select/number). User answers are collected.
3. `POST /directives/submit` — Merges original text + clarifications, re-parses, persists, and routes to the appropriate Powell layer.

**Required Fields** (gaps trigger clarification questions):
- **Reason/justification** (ALWAYS required — a directive without "why" cannot be tracked)
- **Direction** (increase/decrease/maintain/reallocate)
- **Metric** (revenue/cost/service_level/inventory/capacity/quality/lead_time)
- **Magnitude** (by what percentage)
- **Duration** (for how long)
- **Geography** (which sites/regions — lenient for strategic layer)
- **Products** (which product families — lenient for strategic layer)

**Powell Routing** (based on user's `powell_role`):
- VP/Executive → Layer 4: S&OP GraphSAGE (network-wide policy parameters)
- S&OP Director → Layer 2: Execution tGNN (multi-site daily directives)
- MPS/Allocation Manager → Layer 1.5: Site tGNN (single-site coordination)
- Analysts → Layer 1: Individual TRM (specific execution decision)

**Provisioning Stepper** (replaces warm-start button):
14-step Powell Cascade warm-start pipeline with dependency tracking:
warm_start → sop_graphsage → cfa_optimization → lgbm_forecast → demand_tgnn → supply_tgnn → inventory_tgnn → trm_training → supply_plan → rccp_validation → decision_seed → site_tgnn → conformal → briefing

**"Learn by Watching" — Decision Seed + CDT Calibration**:
The `decision_seed` step generates realistic decisions from the digital twin simulation AND populates synthetic outcomes (was_committed, actual_cost, etc.) on every record. This implements the Stöckl (2021) "learn by watching" paradigm: deterministic heuristics execute during warm-start and outcomes are observed. The subsequent `conformal` step reads these decision-outcome pairs via `CDTCalibrationService.calibrate_all()` to calibrate all active TRM agents' risk bounds. If fewer than 11 agents are calibrated from DB outcomes, the conformal step also runs a simulation bootstrap (50 episodes × 365 days = 18,250 pairs per agent) as a second pass. After provisioning, **all active TRM agents must show as calibrated** (no "0/11 agents ready" banner).

**Topology-Aware Decision Seeding**: The seeder uses `get_active_trms(master_type)` from `site_capabilities.py` to only generate decisions valid for the config's DAG topology. A distribution network (no manufacturers) gets 7 TRM types; a network with manufacturers gets all 11. Invalid TRM types (e.g., MO/quality/maintenance for distribution-only) are never seeded.

**Config Versioning on Reprovisioning**: When `reprovision(config_id, scope)` is called, the current config is archived as a read-only snapshot (e.g., "SAP IDES 1710 (v2)") with `scenario_type=ARCHIVED`, `is_active=False`, and the original `created_at` preserved. The active config's `version` is incremented. Archived configs appear in the SC config list for audit trail.

**Provisioning Scope** (`provisioning_scope` column on `config_provisioning_status`):
- **FULL** (default): All 14 steps — required for structural changes (new sites, lanes, products, BOMs)
- **PARAMETER_ONLY**: Only 4 steps — `cfa_optimization`, `decision_seed`, `conformal`, `briefing`. Reuses existing TRM weights, GNN models, and simulation data. Use for policy/parameter changes (safety stock policy, service level targets, CFA parameters).
- API: `POST /provisioning/reprovision/{config_id}?scope=PARAMETER_ONLY`
- Frontend: Two buttons in ProvisioningStepper footer — "Parameters Only" (fast) and "Full Re-provision"

**Implementation Files**:
- `backend/app/services/directive_service.py` — LLM parsing, gap detection, routing
- `backend/app/api/endpoints/user_directives.py` — Analyze/submit/list API
- `backend/app/models/user_directive.py` — UserDirective + ConfigProvisioningStatus models
- `backend/app/services/provisioning_service.py` — 14-step pipeline orchestrator
- `backend/app/api/endpoints/provisioning.py` — Provisioning stepper API
- `frontend/src/components/TopNavbar.jsx` — Talk to me input + clarification panel
- `frontend/src/components/supply-chain-config/ProvisioningStepper.jsx` — Stepper modal
- `backend/app/services/query_router.py` — Route registry (~60 routes), TF-IDF embedding fallback for query routing
- Documentation: [docs/internal/TALK_TO_ME.md](docs/internal/TALK_TO_ME.md) (directives + query routing), [docs/internal/PROVISIONING_STEPPER.md](docs/internal/PROVISIONING_STEPPER.md) (14-step pipeline)

**Query Routing** (question mode):
- LLM classifies questions and returns `target_page` + `filters` from a route registry of ~60 pages
- TF-IDF cosine similarity fallback when LLM doesn't suggest a page
- Routes filtered by user capabilities (users only see pages they can access)
- TopNavbar shows "Go to [page]" button; target pages hydrate filters from `location.state.filters`

**API Endpoints**:
```bash
# Directive capture
POST /api/v1/directives/analyze           # Parse + gap detect (no persist)
POST /api/v1/directives/submit            # Persist + route (with clarifications)
GET  /api/v1/directives/                   # List recent directives
GET  /api/v1/directives/{id}              # Get single directive

# Provisioning stepper
GET  /api/v1/provisioning/status/{config_id}          # Get stepper state
POST /api/v1/provisioning/run/{config_id}/{step_key}  # Run single step
POST /api/v1/provisioning/run-all/{config_id}         # Run all steps
POST /api/v1/provisioning/reset/{config_id}/{step_key} # Reset failed step
```

### Email Signal Intelligence

GDPR-safe email ingestion that extracts supply chain signals from customer/supplier emails. Personal identifiers are stripped; only the sending company (resolved via domain→TradingPartner) is stored. Signals are classified by LLM and routed to existing TRMs.

**GDPR Compliance**:
- NO sender name, email address, or personal identifiers stored
- Only sender domain and resolved TradingPartner (company) persisted
- PII scrubber removes names, emails, phones, addresses, signatures before any text is stored
- Original email is NEVER persisted — only scrubbed text

**Pipeline**: Email → PII scrub → domain→TradingPartner resolution → LLM classification (Haiku) → scope resolution → TRM routing → Decision Stream alert

**Signal Types**: demand_increase, demand_decrease, supply_disruption, lead_time_change, price_change, quality_issue, new_product, discontinuation, order_exception, capacity_change, regulatory, general_inquiry

**Signal→TRM Routing**:
| Signal | Primary TRM | Secondary TRM |
|--------|-------------|---------------|
| demand_increase/decrease | forecast_adjustment | inventory_buffer |
| supply_disruption | po_creation | to_execution |
| lead_time_change | po_creation | inventory_buffer |
| price_change | po_creation | — |
| quality_issue | quality_disposition | mo_execution |
| order_exception | order_tracking | atp_executor |
| capacity_change | mo_execution | maintenance_scheduling |

**Implementation Files**:
- `backend/app/services/email_pii_scrubber.py` — PII removal (regex-based, no external NLP)
- `backend/app/services/email_signal_service.py` — Classification, routing, query methods
- `backend/app/services/email_connector.py` — IMAP connector for enterprise email
- `backend/app/api/endpoints/email_signals.py` — REST API endpoints
- `backend/app/models/email_signal.py` — EmailSignal + EmailConnection models
- `frontend/src/pages/admin/EmailSignalsDashboard.jsx` — Admin UI (signals, connections, analytics, test)

**API Endpoints**:
```bash
# Connections
POST /api/v1/email-signals/connections           # Create connection
GET  /api/v1/email-signals/connections           # List connections
POST /api/v1/email-signals/connections/{id}/test # Test connection
POST /api/v1/email-signals/connections/{id}/poll # Manual poll

# Signals
GET  /api/v1/email-signals/signals               # List signals (filterable)
GET  /api/v1/email-signals/signals/{id}          # Signal detail
POST /api/v1/email-signals/signals/{id}/dismiss  # Dismiss signal
POST /api/v1/email-signals/signals/{id}/reclassify # Re-classify

# Dashboard & testing
GET  /api/v1/email-signals/dashboard             # Summary stats
POST /api/v1/email-signals/ingest-manual         # Manual email paste
```

**Access**: Navigation > Administration > Email Signals (Tenant Admin required)

**SAP System Access**: Free S/4HANA FAA (Fully-Activated Appliance) with IDES sample data available via [cal.sap.com](https://cal.sap.com). Requires SAP ID ([register here](https://account.sap.com/core/create/register)) and a cloud provider account (AWS/Azure/GCP, ~$1-3/hr compute). See [SAP_INTEGRATION_GUIDE.md](docs/external/SAP_INTEGRATION_GUIDE.md#getting-access-to-sap-s4hana-free) for full setup instructions.

---

## Accessing Services

**Local Development**:
- Frontend: http://localhost:8088
- Backend API: http://localhost:8088/api
- API Docs: http://localhost:8000/docs
- Database Admin (pgAdmin): http://localhost:5050 (admin@autonomy.com / admin)
- Direct Backend: http://localhost:8000

**Remote Server**:
- HTTP: http://172.29.20.187:8088
- HTTPS: https://172.29.20.187:8443 (with `make up-tls`)

**Default Login**:
- Email: systemadmin@autonomy.com
- Password: Autonomy@2026

**CRITICAL — User Role Hierarchy**:

| Role | Email | Tenant | Purpose |
|------|-------|--------|---------|
| **System Admin** | systemadmin@autonomy.com | NONE (no tenant_id) | Platform-level: manage tenants and tenant admins ONLY |
| **Tenant Admin** (Food Dist) | admin@distdemo.com | Tenant 3 | Provisioning, config, user management for Food Dist |
| **Tenant Admin** (SAP Demo) | SAP_admin@autonomy.com | Tenant 20 | Provisioning, config, user management for SAP Demo |

**Rules**:
- systemadmin NEVER has a `tenant_id` or `default_config_id` — it is NOT associated with any tenant
- Provisioning can ONLY be performed by the tenant admin — never by systemadmin
- When running provisioning from code, always authenticate as the correct tenant admin
- systemadmin has NO access to the Decision Stream — it returns empty (tenant_id=0 matches nothing)
- systemadmin sees all configs across tenants in the config list (read-only observation), but cannot interact with tenant-scoped features like Decision Stream, provisioning, or agent decisions

---

## Planning Logic & Algorithms

### Planning Knowledge Base

**When developing planning logic, consult [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md) for comprehensive guidance.**

This consolidated knowledge base includes:
- Academic foundations (MPS/MRP, stochastic programming, safety stock)
- Industry implementations (Kinaxis, SAP IBP, OMP)
- Our stochastic modeling framework (21 distribution types)
- Policy types (abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal)
- Lokad quantitative supply chain methodology
- Probabilistic planning with balanced scorecard
- Code examples and algorithms
- Testing & validation procedures

**Quick Reference**:
- **Stochastic vs Deterministic**: Use distributions for operational variables (lead times, yields), fixed values for control variables (inventory targets, costs)
- **Hierarchical Overrides**: Product-Site > Product > Site > Config (most specific wins)
- **8 Policy Types**: abs_level (fixed), doc_dem (demand-based), doc_fcst (forecast-based), sl (service level), sl_fitted (MLE-fitted Monte Carlo), conformal (distribution-free), sl_conformal_fitted (hybrid), econ_optimal (marginal economic return)
- **Balanced Scorecard**: Track Financial, Customer, Operational, and Strategic metrics with probability distributions
- **No Fallbacks**: See "CRITICAL: No Fallbacks, No Hardcoded Values" section above — applies to all data, not just economic parameters

**Key PDFs** (in `docs/Knowledge/`):
- `01_MPS_Material_Requirements_Planning_Academic.pdf` - MPS/MRP fundamentals
- `04_Kinaxis_Master_Production_Scheduling.pdf` (1.7MB) - Kinaxis MPS guide
- `14_Stanford_Stochastic_Programming_Solutions.pdf` (588KB) - Stochastic optimization

**Lokad Quantitative Supply Chain Analysis** (in `docs/Knowledge/`):

- `Lokad_Analysis_and_Integration_Guide.md` - **Comprehensive analysis of Lokad's methodology and technology** (75+ pages analyzed from lokad.com). Key concepts and integration opportunities:
  - **Decision-Driven Optimization**: Output decisions (measured in $), not forecasts (measured in accuracy %). "Naked forecasts" (accuracy without decision integration) is an antipattern.
  - **Prioritized Ordering**: Replace safety stock + reorder point with global marginal ROI ranking across all products. Fill from highest ROI down until budget/capacity binds.
  - **Economic Loss Functions**: Train models with asymmetric economic losses (stockout cost ≠ holding cost), not MSE.
  - **Non-Parametric Distributions**: Quantile grids (empirical PMFs) for intermittent/lumpy demand — no distributional assumptions needed.
  - **Censored Demand**: Stockout periods censor true demand (actual was higher). Flag and handle, don't treat as real zeros.
  - **Lead Time as First-Class Citizen**: Forecast lead times with same rigor as demand. Use log-logistic (fat-tailed), handle in-transit orders as censored observations.
  - **CRPS Metric**: Continuous Ranked Probability Score as gold standard for probabilistic forecast evaluation. Same units as variable, backward-compatible with MAE.
  - **Scenario-Based CFA Optimization**: Optimize policy parameters θ over Monte Carlo scenarios (CMA-ES/Bayesian optimization) — closes the gap between MC evaluation and MC optimization.
  - **Antipatterns**: 22 named supply chain antipatterns including ABC analysis, safety stock formulas, EOQ, 100% service level targets, decoupling forecasting from optimization, S&OP resource destruction.
  - **Stochastic Discrete Descent (SDD)**: Continuous parameterization of discrete optimization problems, SGD in continuous space, project back to integers. Applicable to TRM order quantity optimization.
  - **Lokad's Gaps vs Autonomy**: No agent architecture (batch-only), no simulation/digital twin, no override learning, no conformal prediction, no multi-agent consensus, single-vendor dependency.

**Warren B. Powell - Sequential Decision Analytics Framework** (in `docs/` and `docs/Knowledge/`):

Powell's framework provides a unified theoretical foundation for sequential decision-making under uncertainty. These documents are essential references for policy optimization, belief state management, and AI agent design. See [POWELL_APPROACH.md](POWELL_APPROACH.md) for integration strategy.

- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB, in `docs/Knowledge/`) - **Sequential Decision Analytics and Modeling (SDAM), 1st Edition**: The original reference book covering the unified framework for decision-making under uncertainty. Defines the five core elements (State, Decision, Exogenous Information, Transition, Objective) and four policy classes (PFA, CFA, VFA, DLA).

- `Powell-Kindle-SDAM-2nd-ed-Feb-9-2026-w_cover.pdf` (in `docs/Knowledge/`) - **Sequential Decision Analytics and Modeling, 2nd Edition** (Feb 2026): Major update with Python modules, "Framing the Problem" sections per chapter, and refined UMF notation. State variable decomposition: Rₜ (physical), Iₜ (information), Bₜ (belief). Policy as X^π(Sₜ|θ), transition S^M(Sₜ, xₜ, Wₜ₊₁). Styles of uncertainty: fine-grained variability, shifts, bursts, spikes, spatial events, systemic events, rare events, contingencies. State/decision-dependent exogenous processes. Ch 10: Supply chain management I (two-agent newsvendor). Ch 11: Supply chain management II — Beer Game as multiagent SDP.

- `Powell-Bridging-Vol-I-Framing-Kindle-Jan-7-2026-w_cover.pdf` (in `docs/Knowledge/`) - **Bridging Reinforcement Learning and Stochastic Optimization, Vol I: Framing** (Jan 2026): The framing companion to SDAM. Three stages of decision automation (Framing → Modeling → Implementation). Three framing questions: (1) performance metrics (objectives, targets, limits), (2) types of decisions (binary, discrete, continuous, vectors; timing and who makes them), (3) sources of uncertainty (12 classes). Interaction matrices (decisions × metrics, uncertainty × metrics) for system analysis. 7 levels of AI: (1) rule-based logic, (2) statistics/ML, (3) pattern recognition, (4) LLMs, (5) deterministic optimization, (6) sequential decision problems, (7) creativity/reasoning/judgment. 3 classes of computer intelligence: human-specified, machine learning, optimization. Essential for correctly framing which tier should handle which decision.

- `Powell - Application to Supply Chain Planning.pdf` (in `docs/`) - **Platform Analysis vs Powell Framework**: Detailed gap analysis mapping current Autonomy implementation to Powell's framework. Identifies integration opportunities for each planning level (Strategic, Tactical, Operational, Execution).

- `Powell - How to teach optimization.pdf` (in `docs/Knowledge/`) - **Pedagogical Framework**: Explains how to teach the unified approach, useful for training documentation and onboarding materials.

- `Powell - Optimal Learning.pdf` (in `docs/Knowledge/`) - **Optimal Learning/Exploration**: Covers knowledge gradient, UCB, and other exploration strategies relevant to policy parameter tuning and AI agent training.

- `Powell - RL and SO.pdf` (in `docs/Knowledge/`) - **Reinforcement Learning and Stochastic Optimization**: Bridges RL terminology with operations research, clarifying how TRM/GNN agents map to Powell's VFA class.

- `Powell - RL and SO Book.pdf` (in `docs/Knowledge/`) - **Extended RL/SO Reference**: Comprehensive treatment of the relationship between reinforcement learning and stochastic optimization, with supply chain applications.

- `Powell Approach.pdf` (in `docs/Knowledge/`) - **Powell Framework Overview**: Comprehensive overview of the Powell SDAM framework as applied to supply chain planning, including the four policy classes and decision architecture.

- `Powell Approach - Condensed.pdf` (in `docs/Knowledge/`) - **Powell Framework Quick Reference**: Condensed version of the Powell approach for quick reference.

**Agentic Operating Model Strategy & UX Framework** (in `docs/Knowledge/`):

These documents define the strategic vision and UX implementation for the agentic operating model in supply chain planning. Use as primary references when implementing Powell Framework dashboards and agent interfaces.

- `Strategic Synthesis_ Agentic UX for Demand & Supply Planners.pdf` - **UX Implementation Guide**: Comprehensive UX framework for AI-agent-centric planning. Key concepts:
  - **Six UX Primitives**: (1) Scheduled Tasks & Digests (async AI work), (2) Worklist (exception triage), (3) Chat (natural language interaction), (4) Task Log (audit trail), (5) Agent Configuration (policy tuning), (6) Dashboards (KPI monitoring)
  - **Persona-Based Design**: VP Supply Chain (executive/strategic), S&OP Director (tactical/weekly), MPS Manager (operational/daily)
  - **Worklist as Primary UI**: Human-in-the-loop exception triage with Ask Why, Accept, Reject with override reason capture
  - **Ask Why Functionality**: Agent provides reasoning with evidence citations (specific orders, inventory levels, forecast data) and confidence scores
  - **Decision Status Flow**: Suggested → Reviewed → Accepted/Overridden → Submitted (captured for performance feedback loop)
  - **Key Insight**: "Planners don't want to plan; they want plans that work"

- `AUTONOMY 1 PAGE COMPANY STRATEGY MEMO .pdf` - **Company Strategy**: One-page strategic memo defining Autonomy's positioning. Key concepts:
  - **Core Belief**: Agentic operating model - agents own decisions by default, humans override with reasoning captured
  - **Compounding Loop**: More decisions → Better AI → Less human effort → More decisions handled
  - **Judgment Layer Moat**: Human expertise captured in override patterns becomes competitive advantage
  - **Target Market**: Mid-market manufacturers frustrated with Kinaxis/SAP costs and complexity

**Agentic Inversion & Machine-Speed Economics** (in `docs/`):

- `Visser_Agentic_Inversion_Moltbook_2026.pdf` - **The Agentic Inversion** (Jordi Visser, Feb 2026): Thesis on how digital economic activity transitions from human-constrained labor to machine-driven execution. Key concepts:
  - **Agentic Inversion**: Structural shift from labor→compute, human time→machine time, fatigue→continuous execution. Not automation (same tasks faster) but inversion of who performs economic work.
  - **Velocity as Critical Variable**: Nominal GDP ≈ M × V. Agents increase velocity (V) without increasing employment. Explains asset price inflation outpacing wages, declining labor share of income.
  - **Open-Source Acceleration**: Training remains centralized (capital-intensive) while inference distributes (commodity hardware). Cost of running an agent approaches zero → deploy thousands.
  - **The Overlap Moment**: Present is "unstable moment" where human and machine economies merge. Humans remain as prompters/overseers, gravitational center shifts to autonomous execution.
  - **From Paperwork to Code**: Procurement negotiations compress from months to minutes through parametric contracts. Legal/commercial coordination replaced by programmable logic.
  - **Relevance to Autonomy**: The agentic inversion maps directly to the Powell Framework's copilot→autonomous progression. Override capture during the "overlap moment" trains agents for full autonomy. The article validates Autonomy's agentic operating model thesis at the macro level.
  - Source: https://visserlabs.substack.com/p/the-agentic-inversion-what-moltbook

**Agentic Authorization Protocol** (in `docs/`):

- `AGENTIC_AUTHORIZATION_PROTOCOL.md` - **Cross-Functional Decision-Making at Machine Speed**: Defines the Agentic Authorization Protocol (AAP) for autonomous agents to evaluate cross-functional trade-offs and request authorization for actions outside their authority. 14 sections + 3 appendices covering 25+ negotiation scenarios across manufacturing, distribution, channel allocation, procurement, logistics, finance, and S&OP. Key concepts:
  - **Authorization, Not Negotiation**: The what-if engine gives every agent full visibility into consequences across ALL metrics via the Balanced Scorecard. Agents don't negotiate for information -- they request authorization for actions outside their authority domain.
  - **Authority Boundaries as Authorization Surfaces**: Each agent has unilateral, requires-authorization, and forbidden action categories. Expanded authority map covers 15+ agent types: SO/ATP, Supply, Allocation, Logistics, Inventory, S&OP, Plant, Quality, Maintenance, Procurement, Supplier, Channel, Demand, Finance, Service, Risk.
  - **Three-Phase Protocol**: Evaluate (originator runs what-if on all options including cross-authority), Request (send AuthorizationRequest with full scorecard), Authorize (target agent checks resource availability and contention).
  - **Comprehensive Negotiation Scenarios** (Section 5): 25+ scenarios by function -- Manufacturing (rush orders, changeovers, quality holds, make-vs-buy, BOM allocation, maintenance), Distribution (cross-DC rebalancing, forward positioning, direct-ship, warehouse capacity), Channel (cross-channel allocation, priority override, branded vs. PL, e-commerce surge), Procurement (spot vs. contract, concentration, qualification), Logistics (consolidation, mode selection, cross-border), Finance (working capital vs. service, budget exhaustion, volume discounts), S&OP (seasonal pre-build, parameter disputes, portfolio rationalization), CPFR exceptions.
  - **Board-as-Substrate Architecture** (Section 10): One shared Board Service with three adapters -- React UI (enterprise), LLM Chat via DeepSeek (daily ops), Agent Adapter (structured + NL). Data model IS the board (Moltbook-style). No fork needed.
  - **Net Benefit Threshold as Governance**: Configurable thresholds control agent autonomy -- well above = auto-resolve, near = human reviews, below = reject.
  - **Escalation with Pre-Digested Options**: Humans see ranked alternatives with full scorecards. Human resolutions feed back into agent training (replay buffer, is_expert=True).
  - **Multi-Level Application**: Same protocol at S&OP (policy parameters), tactical (supply baseline), operational (supply/allocation commit), and execution (TRM decisions).
  - **Agentic Consensus Board**: Functional agents continuously negotiate Policy Envelope parameters using feed-back signals as evidence.
  - **Research-Grounded**: CPFR (P&G/Walmart), multi-agent production routing (AAMAS 2024), agentic LLM consensus (2025), Oliver Wyman Supply Chain Triangle, TSMC allocation crisis.

**Decision Intelligence Framework** (in `docs/Knowledge/`):

- `Decision_Intelligence_Framework_Guide.md` - **Gartner DI Framework & Autonomy Alignment**: Comprehensive synthesis of Gartner's Decision Intelligence frameworks (2025-2026), Kozyrkov's applied data science model, and Pratt's Causal Decision Diagrams. Key concepts:
  - **Gartner DIP Definition**: "Software solutions designed to support, automate, and augment decision-making for humans and machines." Inaugural Magic Quadrant (Jan 2026): Leaders SAS, FICO, Aera Technology.
  - **Four DIP Lifecycle Capabilities**: Decision Modeling (→ Powell SDAM), Decision Orchestration (→ TRM Hive + AAP), Decision Monitoring (→ CDC + conformal + CRPS), Decision Governance (→ override tracking + CDT + escalation).
  - **Four Critical Capabilities Use Cases**: Decision Stewardship (governance), Analysis (analytical/rules), Engineering (orchestration/execution), Science (blended AI + logic).
  - **Three-Level Maturity**: Support (human in loop) → Augmentation (human on loop, copilot) → Automation (human out of loop, autonomous). Progression governed by measured decision quality, not arbitrary trust.
  - **Supply Chain Technology Convergence**: Gartner 2025 SC Planning Hype Cycle identifies decision-centric planning + agentic AI + autonomous planning + explainable AI as four interdependent technologies. Prediction: 50% of SCM solutions use intelligent agents by 2030.
  - **Decision-as-Asset**: Every recurring decision modeled with inputs, logic, constraints, ownership, measured outcomes — maps to Powell SDAM five elements and Pratt's CDD (Decision Levers, Outcomes, Externals, Intermediaries).
  - **Competitive Positioning**: Autonomy as first purpose-built Decision Intelligence Platform for supply chain.
  - **UI Enhancement Recommendations**: Decision Intelligence Dashboard, decision lifecycle status in worklists, maturity progression indicator, Causal Decision Diagram visualization, decision-back planning view.

**Powell Framework Quick Reference**:
- **Five Core Elements**: State (Sₜ), Decision (xₜ), Exogenous Information (Wₜ₊₁), Transition Function (Sᴹ), Objective Function
- **State Decomposition** (SDAM 2nd Ed): Rₜ (physical: inventory, backlog, pipeline, capacity), Iₜ (information: forecasts, lead times, supplier status), Bₜ (belief: CDT calibration, conformal intervals, TRM confidence)
- **Four Policy Classes**:
  - **PFA** (Policy Function Approximation): Direct S→x mapping (e.g., base-stock rules)
  - **CFA** (Cost Function Approximation): Parameterized optimization (e.g., inventory policies with θ)
  - **VFA** (Value Function Approximation): Q-learning/TD learning (e.g., TRM agent)
  - **DLA** (Direct Lookahead): Model predictive control (e.g., MPC with GNN forecasts)
- **Three Stages of Decision Automation** (Bridging Vol I): Framing (what metrics, what decisions, what uncertainties?) → Modeling (UMF five elements, policy class selection) → Implementation (solve, evaluate, deploy)
- **7 Levels of AI** (Bridging Vol I): (1) Rule-based logic → Deterministic engine, (2) Statistics/ML → Conformal prediction, (3) Pattern recognition → TRM agents, (4) LLMs → Claude Skills, (5) Deterministic optimization → MPS/MRP solvers, (6) Sequential decision problems → Full SDAM framework, (7) Creativity/reasoning → Escalation Arbiter, S&OP consensus
- **3 Classes of Computer Intelligence** (Bridging Vol I): Human-specified behaviors (engine rules, thresholds), Machine learning (TRM/GNN training, conformal calibration), Optimization (CFA parameter search, VFA estimation)
- **Interaction Matrices** (Bridging Vol I): Decisions × Metrics and Uncertainty × Metrics matrices determine which tier should handle which problem
- **Styles of Uncertainty** (SDAM 2nd Ed): Fine-grained variability, shifts, bursts, spikes, spatial events, systemic events, rare events, contingencies — each maps to different escalation routing
- **Key Insight**: Current platform uses Monte Carlo for **evaluation**; Powell recommends **optimization over scenarios** to extract optimal policy parameters

**Decision-Theoretic Frameworks** (cross-references):

- **Kahneman's Dual-Process Theory**: System 1 (fast/intuitive) = TRM execution (<10ms). System 2 (slow/deliberate) = tGNN (daily) + GraphSAGE (weekly). The Escalation Arbiter acts as "The Lazy Controller" — System 2 only activates when System 1 shows persistent failure. See [ESCALATION_ARCHITECTURE.md](docs/ESCALATION_ARCHITECTURE.md).

- **Boyd's OODA Loop**: Three nested Observe-Orient-Decide-Act loops at different time scales (Execution <10ms, Operational daily, Strategic weekly). "Schwerpunkt" = orientation as center of gravity (TRM trained weights). "Implicit Guidance & Control" = trained TRMs execute without explicit orders. "Mission Command" = push authority to lowest capable level, escalate only when problem exceeds local capability. See [ESCALATION_ARCHITECTURE.md](docs/ESCALATION_ARCHITECTURE.md).

- **SOFAI Architecture** (arxiv:2110.01834): Meta-Cognitive module routes between System 1 and System 2 solvers — maps to the Escalation Arbiter routing between TRMs and tGNN/GraphSAGE. See [ESCALATION_ARCHITECTURE.md](docs/ESCALATION_ARCHITECTURE.md).

- **Gartner Decision Intelligence Framework** (2025-2026): DI = "a practical discipline that advances decision making by explicitly understanding and engineering how decisions are made, and how outcomes are evaluated, managed and improved via feedback." Inaugural Magic Quadrant for DIPs published January 2026 (Leaders: SAS, FICO, Aera Technology). Four DIP lifecycle capabilities: Decision Modeling (→ Powell SDAM five elements), Decision Orchestration (→ TRM Hive + AAP), Decision Monitoring (→ CDC + conformal + CRPS), Decision Governance (→ override tracking + CDT + escalation arbiter). Four use cases: Stewardship, Analysis, Engineering, Science. Three-level maturity: Support (manual) → Augmentation (copilot) → Automation (autonomous). Gartner predicts 50% of SCM solutions will use intelligent agents by 2030. See [Decision_Intelligence_Framework_Guide.md](docs/Knowledge/Decision_Intelligence_Framework_Guide.md) and [POWELL_APPROACH.md](POWELL_APPROACH.md) §5.19.

- **Kozyrkov Decision Intelligence** (Google, 2018-2023): DI = "the discipline of turning information into better actions at any setting, at any scale." Three sub-disciplines: Applied Data Science + Social Science + Managerial Science. Three data analysis types: Analytics (exploration, zero decisions) → Statistics (few critical decisions under uncertainty) → ML/AI (many automated decisions at scale). Core principle: "Outcome = Decision Quality × Luck" — track decision quality, not just outcomes. Maps to: Analytics = BSC dashboards, Statistics = S&OP policy setting, ML/AI = TRM agents.

- **Pratt Causal Decision Diagrams** (2019-2023): Four CDD components: Decision Levers (→ Powell xₜ), Outcomes (→ Objective function), Externals (→ Exogenous Wₜ₊₁), Intermediaries (→ State Sₜ leading indicators). Key contribution: model every recurring decision as a digital asset with inputs, logic, constraints, ownership, and measured outcomes. See "The Decision Intelligence Handbook" (O'Reilly, 2023).

**Beer Game Reference Materials** (in `docs/The_Beer_Game/`):
- `Beer Game Calculations.pdf` (129KB) - Mathematical calculations and formulas
- `Beer Game Gpt – Instructions Block + Tiny Python Turn Api.pdf` (39KB) - GPT instructions and API reference
- `Rice - Beer Game Steps of Game 11-16-16.pdf` (260KB) - Detailed game steps and procedures
- `Simulating TBG.pdf` (4.2MB) - Simulation methodology and approaches
- `TBG Rules and Logic.pdf` (185KB) - Core game rules and decision logic
- `Trainign AI to play TBG.pdf` (13MB) - AI training strategies for Beer Game
- `Understanding TBG.pdf` (11MB) - Comprehensive Beer Game overview
- `Walkthrough of TBG.pdf` (5.1MB) - Step-by-step game walkthrough
- `computers-play-the-beer-game.pdf` (258KB) - Computational approaches to Beer Game

**Business Strategy References** (for documentation and positioning):

Use these books as references when writing executive summaries, competitive positioning, and go-to-market documentation:

- **Good Strategy Bad Strategy: The Difference and Why It Matters** by Richard Rumelt (2011)
  - Key concepts: Kernel of good strategy (diagnosis, guiding policy, coherent actions), avoiding "bad strategy" pitfalls
  - Public source: https://www.amazon.com/Good-Strategy-Bad-Difference-Matters/dp/0307886239
  - Summary: https://www.grahammann.net/book-notes/good-strategy-bad-strategy-richard-rumelt

- **Crossing the Chasm, 3rd Edition** by Geoffrey A. Moore (2014)
  - Key concepts: Technology adoption lifecycle, chasm between early adopters and early majority, whole product concept, target market selection
  - Public source: https://www.amazon.com/Crossing-Chasm-3rd-Disruptive-Mainstream/dp/0062292986
  - Summary: https://www.productplan.com/glossary/crossing-the-chasm/

**Application to Platform Documentation**:
- **Good Strategy**: Define clear diagnosis (legacy planning software pain points), guiding policy (AI-first with simulation validation), coherent actions (specific feature priorities)
- **Crossing the Chasm**: Target specific beachhead market (mid-market manufacturers frustrated with Kinaxis/SAP costs), develop whole product (not just features, but training, support, integration)

---

## Claude Skills Framework (Hybrid TRM + Skills Architecture)

**Status**: IMPLEMENTED (2026-02-26)

The platform uses a **hybrid TRM + Claude Skills** architecture at the execution level. TRMs (7M-parameter neural networks) are the PRIMARY decision path handling ~95% of decisions at <10ms latency. Claude Skills serve as the **exception handler** for the ~5% of novel situations where conformal prediction indicates low TRM confidence. This maps to LeCun's JEPA framework: TRMs = Actor, Claude Skills = Configurator.

Each skill encodes heuristic decision rules as a SKILL.md file, with RAG decision memory providing few-shot context from past decisions. Feature-flagged OFF by default (`USE_CLAUDE_SKILLS=false`).

**Key Documentation**:
- [docs/CLAUDE_SKILLS_STRATEGY.md](docs/CLAUDE_SKILLS_STRATEGY.md) — Full strategic analysis: PicoClaw/OpenClaw vs Claude, TRM vs Skills+RAG, cost models, IP protection
- [docs/CLAUDE_SKILLS_MIGRATION_PLAN.md](docs/CLAUDE_SKILLS_MIGRATION_PLAN.md) — Phased implementation roadmap
- [docs/CLAUDE_SUBSCRIPTION_GUIDE.md](docs/CLAUDE_SUBSCRIPTION_GUIDE.md) — Subscription setup, pricing, smart routing config
- [docs/Knowledge/LeCun_Critique_Planning_Agency_Analysis.md.pdf](docs/Knowledge/LeCun_Critique_Planning_Agency_Analysis.md.pdf) — Theoretical foundation: JEPA mapping, hybrid architecture rationale

**Architecture (LeCun JEPA Mapping)**:
```
GraphSAGE / tGNN = World Model (network-wide state representation)
TRMs = Actor (fast, learned policy execution, ~95% of decisions)
Claude Skills = Configurator (exception handling, ~5% of decisions)
Bayesian / Causal AI = Critic (override effectiveness tracking)
Conformal Prediction = Uncertainty Module (routing trigger)
```

**Hybrid Execution Flow**:
```
Deterministic Engine (always runs first)
    ↓
TRM Exception Head (fast, <10ms, learned adjustments)
    ↓
Conformal Prediction Router:
    ├── High confidence (tight intervals) → Accept TRM result ✓
    └── Low confidence (wide intervals) → Escalate to Claude Skills
        ↓
    Claude Skills Exception Handler
        ├── RAG Decision Memory (find similar past decisions)
        ├── Claude API (Haiku for calculation, Sonnet for judgment)
        └── Proposal validated against engine constraints
    ↓
Skills decisions recorded for TRM meta-learning (shift 95/5 boundary)
```

**Three Roles of Claude Skills**:
1. **Exception Handler**: Reason about novel situations TRMs haven't learned yet
2. **Orchestrator**: Assess TRM confidence, decide when to escalate (via conformal prediction)
3. **Meta-Learner**: Skills decisions feed back into TRM training data, gradually teaching TRMs to handle previously-novel situations

**Conformal Prediction Routing** (governs the TRM → Skills boundary):
- `skill_escalation_threshold` (default: 0.6): TRM confidence below this triggers escalation
- CDT `risk_bound` > (1 - threshold): High uncertainty triggers escalation
- Conformal `interval_width` > 0.5: Wide prediction intervals trigger escalation

**Constraint Validation** (all Skills proposals must pass):
- Quantity deviation < `skill_max_deviation` (default: 30%) from engine baseline
- Multipliers within [0.5, 2.0] safe range
- Confidence gate: Skills confidence must be > 0.3

**11 Skills by Routing Tier**:

| Tier | Skills | Cost/Call | Notes |
|------|--------|-----------|-------|
| Deterministic | `atp_executor`, `order_tracking` | $0 | No LLM needed |
| Haiku | `po_creation`, `inventory_rebalancing`, `inventory_buffer`, `to_execution` | ~$0.0018 | Calculation-heavy |
| Sonnet | `mo_execution`, `quality_disposition`, `maintenance_scheduling`, `subcontracting`, `forecast_adjustment` | ~$0.0054 | Requires judgment |

**Implementation Files**:
- `backend/app/services/skills/__init__.py` — Framework package
- `backend/app/services/skills/base_skill.py` — `SkillDefinition`, `SkillResult`, `SkillError`, registry
- `backend/app/services/skills/claude_client.py` — Claude API client with vLLM/Qwen fallback, prompt caching
- `backend/app/services/skills/skill_orchestrator.py` — Exception handler and meta-learner (invoked only on escalation)
- `backend/app/services/skills/*/SKILL.md` — 11 heuristic rule files (one per TRM type)
- `backend/app/models/decision_embeddings.py` — pgvector 768-dim embeddings for RAG decision memory
- `backend/app/services/decision_memory_service.py` — Embed/retrieve past decisions for few-shot context
- `backend/app/services/powell/site_agent.py` — Hybrid integration: `_should_escalate_to_skills()`, `_validate_skill_proposal()`, `_record_skill_decision_for_training()`

**RAG Decision Memory** (cost reduction flywheel):
- Cache hit (similarity > 0.95): Skip LLM entirely ($0)
- Few-shot hit (similarity > 0.70): Inject as context, cheaper Haiku model (~$0.0012)
- Novel situation: Full skill prompt to Sonnet (~$0.0054)
- Expected cost: ~$130/mo initially → ~$34/mo as decision corpus grows

**Environment Variables**:
```env
CLAUDE_API_KEY=sk-ant-...          # From console.anthropic.com
CLAUDE_MODEL_HAIKU=claude-haiku-4-5-20251001
CLAUDE_MODEL_SONNET=claude-sonnet-4-6
USE_CLAUDE_SKILLS=false            # Feature flag (enable when ready)
SKILL_ESCALATION_THRESHOLD=0.6    # TRM confidence below this → Skills
SKILL_MAX_DEVIATION=0.3           # Max allowed deviation for Skills proposals
```

**Fallback chain**: Engine → TRM → Claude Skills → Engine-only. vLLM + Qwen 3 via `LLM_API_BASE` for air-gapped customers. TRM neural networks remain as the primary execution path; Claude Skills only activates for exceptions.

**Self-Hosted LLM** (unchanged):
- Qwen 3 8B via vLLM — 96.5% tool calling accuracy, OpenAI-compatible API, 8GB VRAM minimum
- `docker-compose.llm.yml` overlay adds vLLM service to existing stack

---

## Architectural Refactoring

**Status**: ✅ **SUBSTANTIALLY COMPLETE** (Feb 2026)

The platform has been refactored from Beer Game-centric to AWS SC-first. See [ARCHITECTURAL_REFACTORING_PLAN.md](ARCHITECTURAL_REFACTORING_PLAN.md) for original plan.

**Completed**:
- ✅ AWS SC entity compliance: 100% (35/35 entities)
- ✅ Navigation: Planning (primary), Execution, AI & Agents, Simulation (secondary)
- ✅ 96+ frontend pages implemented (planning, admin, analytics, execution, visibility)
- ✅ Terminology renames: Game→Scenario, Player→User, Group→Tenant, Round→Period
- ✅ TRM Hive architecture fully implemented (30K+ lines)
- ✅ AAP (Agentic Authorization Protocol) implemented
- ✅ CDC→Relearning autonomous feedback loop
- ✅ Knowledge Base / RAG with pgvector
- ✅ SAP integration (connections, field mapping, user import, monitoring)
- ✅ Hybrid TRM + Claude Skills architecture (TRMs primary, Skills for exceptions, conformal routing)
- ✅ RAG Decision Memory (pgvector-based decision embeddings for cost reduction)
- ✅ PicoClaw/OpenClaw removed (replaced by Claude Skills ecosystem)
- ✅ Executive Strategy Briefing (LLM-synthesized briefings with follow-up Q&A). See [docs/EXECUTIVE_BRIEFING.md](docs/EXECUTIVE_BRIEFING.md)
- ✅ Beer Game repositioned as Digital Twin / Learning Tenant module (not primary focus)
- ✅ "Talk to Me" directive capture with smart clarification flow (two-phase: analyze→clarify→submit) + query routing (LLM + TF-IDF fallback → page navigation with filters)
- ✅ Provisioning Stepper (14-step Powell Cascade warm-start pipeline with dependency tracking)
- ✅ Email Signal Intelligence (GDPR-safe email ingestion, PII scrubbing, LLM classification, TRM routing)

---

## Notes

### GPU Support
- Set `FORCE_GPU=1` for GPU builds
- Requires NVIDIA Docker runtime
- Backend uses PyTorch with CUDA for GNN training
- Falls back to CPU if GPU unavailable

### Docker Compose Version
The Makefile auto-detects Compose V2 (`docker compose`) vs V1 (`docker-compose`). For V1, it sets `COMPOSE_API_VERSION=1.44` to avoid `KeyError: 'ContainerConfig'` errors.

### Backend Entry Point
The backend uses `backend/main.py` as the FastAPI application entry point. Note: this file is 62K lines and contains extensive configuration.

### Seeding Process
When running `make up` with `FORCE_GPU=1`, the system automatically runs `make db-bootstrap` which:
1. Seeds Default TBG, Three FG TBG, and Variable TBG configs
2. Creates default users and tenants
3. Generates showcase scenarios with LLM and GNN agents

### Training Hyperparameters
Admin UI exposes: epochs, device, window, horizon, data source.
Code-only: architecture (hidden dims, layers), learning rate, batch size, RL hyperparameters.
No automated hyperparameter search - requires manual orchestration.

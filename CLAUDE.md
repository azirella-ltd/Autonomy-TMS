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
| Training Group | Learning Group | Group mode for user education |
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

> **Terminology Note — Inventory Buffer (Feb 2026)**: At the TRM/Powell execution layer, "SafetyStockTRM" has been renamed to **InventoryBufferTRM**. This addresses the DDMRP critique that "safety stock" as a concept causes MRP to treat it as a hard demand target, generating planned orders that compete with real customer demand for upstream capacity. At the TRM level, the inventory buffer is an **uncertainty absorber**, NOT a hard demand target for MRP. Buffer-replenishment planned orders get lower priority than demand-driven orders (soft-buffer netting). **Important**: The AWS SC data model fields (`safety_stock` column, `ss_quantity`, `inv_policy` policy types) remain unchanged for compliance — the rename applies only to TRM agent names, Powell decision tables, and hive signal types.

**Clean Rename**: The old terminology has been fully replaced. There are no backward-compatible aliases.
- Use `Scenario`, `ScenarioCreate`, `ScenarioState` (not Game*)
- Use `ScenarioUser`, `ScenarioUserRole`, `ScenarioUserResponse` (not Player*/Participant*)
- Use `Period`, `ScenarioUserPeriod` (not Round*, GameRound)
- Frontend uses `simulationApi` with methods like `createScenario()`, `getScenarioUsers()`

### Group Modes vs AI Model Training

**CRITICAL DISTINCTION**: Do not confuse these two uses of "training":

| Term | Meaning | Examples |
|------|---------|----------|
| **Learning Group** | Group mode for end-user education | Users run scenarios to learn how AI agents work, understand supply chain dynamics |
| **AI Model Training** | Process of training ML models | TRM training, GNN training, RL training - happens in BOTH Learning and Production groups |

- **Learning Group** (`GroupMode.LEARNING`): Simplified navigation, game-like clock (turn-based/timed), focused on user education and building confidence with AI agents
- **Production Group** (`GroupMode.PRODUCTION`): Full navigation, real data integration, real planning workflows

**Both group types support AI model training**:
- Learning Groups need to train agents for educational scenarios
- Production Groups need to train agents for real-world decision making

The group mode determines the **user experience**, not whether AI models can be trained.

---

## Project Overview

**Autonomy Platform with AI & Simulation** - An enterprise-grade supply chain planning and execution system compatible with AWS Supply Chain standards, enhanced with three unique differentiators:

### Core: AWS Supply Chain Compliance

**Primary Focus**: Professional supply chain planning and execution following AWS SC data model and workflows

**Key Capabilities**:
- **Demand Planning**: Statistical and ML forecasting, consensus planning, supplementary time series
- **Supply Planning**: Net requirements calculation, multi-level BOM explosion, multi-sourcing with priorities
- **Master Production Scheduling (MPS)**: Strategic production planning with rough-cut capacity checks
- **Material Requirements Planning (MRP)**: Detailed component requirements from MPS
- **Inventory Optimization**: 4 policy types (abs_level, doc_dem, doc_fcst, sl), hierarchical overrides
- **Capacity Planning**: Resource utilization analysis, bottleneck identification
- **Order Management**: Inbound/outbound orders, shipment tracking, fulfillment
- **Network Design**: DAG-based supply chain topology (35 AWS SC entities)

**AWS SC Compliance**: 91% (32/35 entities implemented). See [AWS_SC_IMPLEMENTATION_STATUS.md](docs/progress/AWS_SC_IMPLEMENTATION_STATUS.md) for detailed status.

**AWS SC References**:
- **Features**: Target feature parity (excluding Data Lakes) with AWS Supply Chain capabilities: https://aws.amazon.com/aws-supply-chain/features/
- **Resources**: UI/UX guidance and implementation examples: https://aws.amazon.com/aws-supply-chain/resources/

### Differentiator #1: AI Agents (Automated Planners)

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
     - **MOExecutionTRM**: Manufacturing order release, sequencing, expedite
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

2. **GNN Agent** (Graph Neural Network) - Two-Tier Architecture
   - **S&OP GraphSAGE** (Medium-Term): Network structure analysis, risk scoring, bottleneck detection
     - Updates weekly/monthly, outputs criticality scores, concentration risk, resilience, safety stock multipliers
     - Scalable to 50+ nodes with O(edges) complexity
     - **Powell: CFA (computes policy parameters θ)**
   - **Execution tGNN** (Short-Term): Generates priority allocations, provides context for TRM
     - Consumes S&OP embeddings + transactional data, updates daily
     - **Outputs: Priority × Product × Location allocations for AATP**
     - **Powell: CFA/VFA bridge**
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

### Differentiator #2: Stochastic Planning (Probabilistic Outcomes)

**Purpose**: Plan with uncertainty quantification instead of point estimates, enabling risk-aware decision-making.

**Stochastic Framework**:
- **20 Distribution Types**: Normal, lognormal, beta, gamma, Weibull, exponential, triangular, mixture, empirical, etc.
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand, forecast error
- **Control Variables** (deterministic): Inventory targets, costs, policy parameters
- **Monte Carlo Simulation**: 1000+ scenarios for full uncertainty propagation
- **Variance Reduction**: Common random numbers, antithetic variates, Latin hypercube sampling

**Probabilistic Balanced Scorecard**:
- **Financial**: E[Total Cost], P(Cost < Budget), P10/P50/P90 cost distribution
- **Customer**: E[OTIF], P(OTIF > 95%), fill rate likelihood
- **Operational**: E[Inventory Turns], E[DOS], bullwhip ratio distribution
- **Strategic**: Flexibility scores, supplier reliability, CO2 emissions

**Output**: Likelihood distributions for KPIs instead of single-point estimates (e.g., "85% chance service level > 95%")

### Differentiator #3: Simulation (The Beer Game Module)

**Purpose**: Learn, validate, and build confidence through scenario-based simulation.

**The Beer Game**:
- **Classic Simulation**: Multi-echelon supply chain (Retailer → Wholesaler → Distributor → Factory)
- **Bullwhip Effect**: Demonstrates demand amplification through supply chain
- **Multi-user**: 2-8 users in real-time WebSocket scenarios
- **Mixed Human-AI**: Humans compete alongside/against AI agents

**Use Cases**:
1. **Employee Training**: Scenario-based learning (3-5x higher engagement vs traditional training)
2. **Agent Validation**: Test AI agents in risk-free environment before production deployment
3. **Confidence Building**: Human vs AI competitions demonstrate AI effectiveness
4. **Continuous Improvement**: Human decisions generate training data for AI agents (RLHF)

**Integration**: Beer Game scenarios use core AWS SC services underneath (demand planning, supply planning, inventory management).

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

# Reset admin password to Autonomy@2025
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
- `inventory_target_calculator.py`: Step 2 - Safety stock and target calculation (4 policy types)
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
- `group_service.py`: Group and session management
- `auth_service.py`: JWT authentication and authorization
- `conformal_orchestrator.py`: Automatic conformal prediction feedback loop for demand, lead time, price, yield, and service level (forecast load hooks, multi-entity actuals observation, drift monitoring, scheduled recalibration, suite ↔ DB persistence)
- `agent_context_explainer.py`: Context-aware explainability orchestrator — authority boundaries, guardrails, policy parameters, conformal intervals, feature attribution, counterfactuals for all 11 TRM agents and both GNN models
- `explanation_templates.py`: 39 Jinja2-style templates (13 agent types × 3 verbosity levels) for inline decision explanations

**API Endpoints** (`api/endpoints/`):
- `mps.py`: Master Production Scheduling endpoints
- `supply_plan.py`: Supply plan generation and approval
- `mixed_scenario.py`: Beer Game API (human + AI scenarios)
- `agent_scenario.py`: Pure agent scenario API
- `supply_chain_config.py`: Supply chain network configuration
- `model.py`: Training and dataset generation endpoints
- `auth.py`: Authentication (login, register, MFA)
- `websocket.py`: Real-time scenario updates

**Database Models** (`models/`):
- `aws_sc_planning.py`: AWS SC planning entities (forecast, supply_plan, sourcing_rules, inv_policy, etc.)
- `supply_chain_config.py`: Network topology (SupplyChainConfig, Node, Lane, Item, Market)
- `scenario.py`: Scenario, Period, ScenarioUserAction (simulation module)
- `participant.py`: ScenarioUser, ScenarioUserRole, ScenarioUserPeriod (simulation module)
- `agent_config.py`: AgentConfig, AgentScenarioConfig
- `group.py`: Group model (company equivalent)
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

**Admin Pages** (`pages/admin/`):
- `TRMDashboard.jsx`: TRM training interface
- `GNNDashboard.jsx`: GNN training interface
- `ModelSetup.jsx`: Model configuration
- `UserManagement.jsx`: User administration
- `GroupManagement.jsx`: Group/company management

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

**TRM Hive Model**: Each site's 11 TRM agents form a self-organizing "hive" with intra-hive signal propagation (HiveSignalBus, UrgencyVector) and the tGNN as inter-hive connective tissue. Integrates with the [Agentic Authorization Protocol](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md) for cross-authority negotiation and includes a Kinaxis-inspired embedded scenario architecture where agents create branched what-if scenarios at machine speed. **Recommended neural architecture**: Three-layer hybrid — stigmergic coordination (S-MADRL pheromones), heterogeneous graph attention (HetNet), and recursive per-head refinement (Samsung TRM) — totaling ~473K params at <10ms latency. **Pragmatic start**: Stigmergic layer only (Phase A, 2-3 weeks, 10M training records) captures 80% of coordination value. See [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 14 for architecture specification, Section 15 for digital twin training pipeline, Section 16 for multi-site coordination stack, and [TRM_RESEARCH_SYNTHESIS.md](TRM_RESEARCH_SYNTHESIS.md) Section 8 for research foundations.

**Multi-Site Coordination Stack** (4 layers, see [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 16):
- **Layer 1 — Intra-Hive** (<10ms): UrgencyVector + HiveSignalBus within a single site
- **Layer 2 — tGNN Inter-Hive** (daily): S&OP GraphSAGE + Execution tGNN process full network graph, produce per-site tGNNSiteDirective
- **Layer 3 — AAP Cross-Authority** (seconds-minutes): AuthorizationRequest/Response for transfers, priority overrides, capacity sharing
- **Layer 4 — S&OP Consensus Board** (weekly): Policy parameters θ negotiated by functional agents
- **Key principle**: TRMs never call across sites. All cross-site information flows through the tGNN directive or AAP authorization.

**Digital Twin Training Pipeline** (see [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) Section 15): Five-phase cold-start pipeline using platform simulation capabilities as digital twin — (1) Individual BC warm-start from curriculum, (2) Multi-head coordinated traces from SimPy/Beer Game, (3) Stochastic stress-testing via Monte Carlo, (4) Copilot calibration from human overrides, (5) Autonomous CDC relearning from production outcomes. Total synthetic data: ~46M records, ~7-10 days compute. Stigmergic-only variant: ~10M records, ~5-8 days.

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
| `MOExecutionTRM` | Per production order | Release, sequence, split, expedite, defer |
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
| `ConditionMonitorService` | On-demand | 6 real-time DB condition checks (ATP shortfall, inventory, capacity, orders past due, forecast deviation) |

Database tables: `powell_cdc_trigger_log`, `powell_site_agent_decisions`, `powell_site_agent_checkpoints`, `powell_cdc_thresholds`

API endpoints:
- `GET /site-agent/cdc/triggers/{site_key}` — Trigger history
- `GET /site-agent/retraining/status/{site_key}` — Checkpoint, readiness, pending experiences
- `POST /site-agent/retraining/trigger/{site_key}` — Manual retraining (background)

See [POWELL_APPROACH.md](POWELL_APPROACH.md) for full framework documentation.

### AWS SC Planning Flow

**3-Step Planning Process** (AWS SC standard):

1. **Demand Processing** ([demand_processor.py](backend/app/services/aws_sc_planning/demand_processor.py)):
   - Aggregate demand from forecasts and customer orders
   - Net out committed/allocated inventory
   - Time-phase demand across planning horizon

2. **Inventory Target Calculation** ([inventory_target_calculator.py](backend/app/services/aws_sc_planning/inventory_target_calculator.py)):
   - Calculate safety stock using 4 policy types:
     - `abs_level`: Fixed quantity
     - `doc_dem`: Days of coverage (demand-based)
     - `doc_fcst`: Days of coverage (forecast-based)
     - `sl`: Service level with z-score
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
- `groups`: Organizations/companies (equivalent to AWS SC `company`)
- `roles`: RBAC roles
- `permissions`: Granular permissions
- `user_roles`: Role assignments

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
POSTGRESQL_DATABASE=beer_game
POSTGRESQL_USER=beer_user
POSTGRESQL_PASSWORD=beer_password
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
- Group (organization) and admin user
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

### SAP Data Management

The platform includes comprehensive SAP integration for deploying to enterprise environments:

**Capabilities**:
1. **SAP Connection Management**: Configure connections to S/4HANA, APO, ECC, BW via RFC, CSV, or OData
2. **Z-Table/Z-Field Handling**: AI-powered fuzzy matching for custom SAP tables and fields
3. **Field Mapping**: Automatic and manual mapping of SAP fields to AWS SC entities
4. **Data Ingestion Monitoring**: Real-time job tracking, quality metrics, and anomaly detection
5. **Insights & Actions**: AI-generated recommendations with remediation workflows

**API Endpoints**:
```bash
# Connection management
POST /api/v1/sap-data/connections        # Create connection
POST /api/v1/sap-data/connections/{id}/test  # Test connection

# Table and field mapping
GET  /api/v1/sap-data/connections/{id}/tables  # Discover tables
POST /api/v1/sap-data/field-mapping/match      # Match single field
POST /api/v1/sap-data/z-table-analysis         # AI analysis of Z-table

# Ingestion monitoring
POST /api/v1/sap-data/jobs                # Create ingestion job
GET  /api/v1/sap-data/dashboard           # Dashboard summary
GET  /api/v1/sap-data/insights            # Get insights
GET  /api/v1/sap-data/actions             # Get remediation actions
```

**Implementation Files**:
- `backend/app/services/sap_deployment_service.py` - Connection and deployment configuration
- `backend/app/services/sap_field_mapping_service.py` - AI-powered field mapping with fuzzy matching
- `backend/app/services/sap_ingestion_monitoring_service.py` - Job monitoring and insights
- `backend/app/api/endpoints/sap_data_management.py` - REST API endpoints
- `frontend/src/pages/admin/SAPDataManagement.jsx` - Admin UI

**Access**: Navigation > Administration > SAP Data Management (Group Admin required)

**SAP System Access**: Free S/4HANA FAA (Fully-Activated Appliance) with IDES sample data available via [cal.sap.com](https://cal.sap.com). Requires SAP ID ([register here](https://account.sap.com/core/create/register)) and a cloud provider account (AWS/Azure/GCP, ~$1-3/hr compute). See [SAP_INTEGRATION_GUIDE.md](docs/progress/SAP_INTEGRATION_GUIDE.md#getting-access-to-sap-s4hana-free) for full setup instructions.

---

## Accessing Services

**Local Development**:
- Frontend: http://localhost:8088
- Backend API: http://localhost:8088/api
- API Docs: http://localhost:8000/docs
- Database Admin (pgAdmin): http://localhost:5050 (admin@autonomy.ai / admin)
- Direct Backend: http://localhost:8000

**Remote Server**:
- HTTP: http://172.29.20.187:8088
- HTTPS: https://172.29.20.187:8443 (with `make up-tls`)

**Default Login**:
- Email: systemadmin@autonomy.ai
- Password: Autonomy@2025

---

## Planning Logic & Algorithms

### Planning Knowledge Base

**When developing planning logic, consult [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md) for comprehensive guidance.**

This consolidated knowledge base includes:
- Academic foundations (MPS/MRP, stochastic programming, safety stock)
- Industry implementations (Kinaxis, SAP IBP, OMP)
- Our stochastic modeling framework (20 distribution types)
- Policy types (abs_level, doc_dem, doc_fcst, sl)
- Probabilistic planning with balanced scorecard
- Code examples and algorithms
- Testing & validation procedures

**Quick Reference**:
- **Stochastic vs Deterministic**: Use distributions for operational variables (lead times, yields), fixed values for control variables (inventory targets, costs)
- **Hierarchical Overrides**: Product-Site > Product > Site > Config (most specific wins)
- **4 Policy Types**: abs_level (fixed), doc_dem (demand-based), doc_fcst (forecast-based), sl (service level)
- **Balanced Scorecard**: Track Financial, Customer, Operational, and Strategic metrics with probability distributions

**Key PDFs** (in `docs/Knowledge/`):
- `01_MPS_Material_Requirements_Planning_Academic.pdf` - MPS/MRP fundamentals
- `04_Kinaxis_Master_Production_Scheduling.pdf` (1.7MB) - Kinaxis MPS guide
- `14_Stanford_Stochastic_Programming_Solutions.pdf` (588KB) - Stochastic optimization

**Warren B. Powell - Sequential Decision Analytics Framework** (in `docs/` and `docs/Knowledge/`):

Powell's framework provides a unified theoretical foundation for sequential decision-making under uncertainty. These documents are essential references for policy optimization, belief state management, and AI agent design. See [POWELL_APPROACH.md](POWELL_APPROACH.md) for integration strategy.

- `Powell-SDAM-Nov242022_final_w_frontcover.pdf` (5.9MB, in `docs/Knowledge/`) - **Sequential Decision Analytics and Modeling (SDAM)**: The primary reference book covering the unified framework for decision-making under uncertainty. Defines the five core elements (State, Decision, Exogenous Information, Transition, Objective) and four policy classes (PFA, CFA, VFA, DLA).

- `Powell - Application to Supply Chain Planning.pdf` (in `docs/`) - **Platform Analysis vs Powell Framework**: Detailed gap analysis mapping current Autonomy implementation to Powell's framework. Identifies integration opportunities for each planning level (Strategic, Tactical, Operational, Execution).

- `Powell - How to teach optimization.pdf` (in `docs/Knowledge/`) - **Pedagogical Framework**: Explains how to teach the unified approach, useful for training documentation and onboarding materials.

- `Powell - Optimal Learning.pdf` (in `docs/Knowledge/`) - **Optimal Learning/Exploration**: Covers knowledge gradient, UCB, and other exploration strategies relevant to policy parameter tuning and AI agent training.

- `Powell - RL and SO.pdf` (in `docs/Knowledge/`) - **Reinforcement Learning and Stochastic Optimization**: Bridges RL terminology with operations research, clarifying how TRM/GNN agents map to Powell's VFA class.

- `Powell - RL and SO Book.pdf` (in `docs/Knowledge/`) - **Extended RL/SO Reference**: Comprehensive treatment of the relationship between reinforcement learning and stochastic optimization, with supply chain applications.

- `Powell Approach.pdf` (in `docs/Knowledge/`) - **Powell Framework Overview**: Comprehensive overview of the Powell SDAM framework as applied to supply chain planning, including the four policy classes and decision architecture.

- `Powell Approach - Condensed.pdf` (in `docs/Knowledge/`) - **Powell Framework Quick Reference**: Condensed version of the Powell approach for quick reference.

- `FG Supply Planning as AI Labor.pdf` (in `docs/Knowledge/`) - **FG Supply Planning Agent Specification**: Defines the FG Supply Planning Agent that owns the "Supply Commit" decision, grounded by the "Supply Baseline Pack" (SupBP). Key concepts:
  - **Supply Commit (SC)**: Agent-owned decision artifact for what to buy/make/transfer, when, from whom
  - **Supply Baseline Pack (SupBP)**: Mathematical grounding with multiple candidate supply plans (MRP_STANDARD, SAFETY_STOCK_OPTIMIZED, MIN_COST_LP, SERVICE_MAXIMIZED, PARAMETRIC_CFA)
  - **UX Primitives**: Scheduled Tasks, Worklist, Chat, Task Log, Agent Configuration, Dashboards
  - **Planning Cascade**: Demand Agent (UCF) → FG Supply Agent (SC) → Allocation Agent (AC) → Execution
  - **Policy Classes**: Supply Plan Integrity (inventory balance, lead time feasibility, MOQ compliance, demand coverage) and Supply Outcome Risk (service risk, investment, concentration, expedite, E&O, stability)
  - **Key Metrics**: Touchless Rate, Agent Score, User Score, Human Override Rate, Override Dependency Ratio, Downstream Coherence

- `Integrated Supply Planning as AI Labor.pdf` (in `docs/Knowledge/`) - **Full Planning Cascade Architecture**: Extends FG Supply Planning to cover the complete cascade from S&OP through Allocation Commit. Key concepts:
  - **Full Cascade**: S&OP/IBP Layer → MPS/MRP Layer → Supply Planning Agent (SC) → Allocation Planning Agent (AC) → Execution
  - **Feed-Forward Contracts**: Each layer produces versioned, hashable artifacts as grounding input to the next layer
  - **Feed-Back Signals**: Outcome signals (OTIF, shortfalls, expedite frequency, E&O) re-tune upstream policy parameters
  - **Allocation Commit (AC)**: Agent-owned decision for constraint-respecting distribution of supply across demand segments
  - **Solver Baseline Pack (SBP)**: Non-authoritative allocation candidates (fair-share, priority heuristic, LP, MILP, hybrid)
  - **Modular Selling**: Layers can be sold independently - when S&OP/MPS not purchased, same UI screens become **input screens** where customer provides policy parameters manually
  - **Customer-Provided Inputs (when no S&OP/MPS)**: Safety stock targets (weeks-of-supply), OTIF floors by segment, allocation reserves, expedite caps, candidate supply plans (customer's MRP output), BOM/lead times
  - **Upgrade Path**: Adding MPS/MRP generates multiple SupBP candidates; adding S&OP quantifies consequences of policy changes and tightens feedback loop

**AI-as-Labor Strategy & UX Framework** (in `docs/Knowledge/`):

These documents define the strategic vision and UX implementation for AI-as-Labor in supply chain planning. Use as primary references when implementing Powell Framework dashboards and agent interfaces.

- `Strategic Synthesis_ AI Labor UX for Demand & Supply Planners.pdf` - **UX Implementation Guide**: Comprehensive UX framework for AI-agent-centric planning. Key concepts:
  - **Six UX Primitives**: (1) Scheduled Tasks & Digests (async AI work), (2) Worklist (exception triage), (3) Chat (natural language interaction), (4) Task Log (audit trail), (5) Agent Configuration (policy tuning), (6) Dashboards (KPI monitoring)
  - **Persona-Based Design**: VP Supply Chain (executive/strategic), S&OP Director (tactical/weekly), MPS Manager (operational/daily)
  - **Worklist as Primary UI**: Human-in-the-loop exception triage with Ask Why, Accept, Reject with override reason capture
  - **Ask Why Functionality**: Agent provides reasoning with evidence citations (specific orders, inventory levels, forecast data) and confidence scores
  - **Decision Status Flow**: Suggested → Reviewed → Accepted/Overridden → Submitted (captured for performance feedback loop)
  - **Key Insight**: "Planners don't want to plan; they want plans that work"

- `AUTONOMY 1 PAGE COMPANY STRATEGY MEMO .pdf` - **Company Strategy**: One-page strategic memo defining Autonomy's positioning. Key concepts:
  - **Core Belief**: AI-as-Labor operating model - agents own decisions by default, humans override with reasoning captured
  - **Compounding Loop**: More decisions → Better AI → Less human effort → More decisions handled
  - **Judgment Layer Moat**: Human expertise captured in override patterns becomes competitive advantage
  - **Target Market**: Mid-market manufacturers frustrated with Kinaxis/SAP costs and complexity

- `AI-as-Labor Operating Model_ Cross-Domain Ideation.md.pdf` - **Operating Model Metrics**: Defines key metrics for measuring AI-as-Labor success. Key concepts:
  - **Agent Performance Score**: -100 to +100 scale measuring agent decision quality vs baseline/optimal. Positive = better than baseline, negative = worse
  - **Human Override Rate**: 0-100% measuring the percentage of decisions overridden by humans. Lower = more trust in AI
  - **Touchless Rate**: Percentage of decisions executed without any human intervention
  - **Override Dependency Ratio**: Frequency of human overrides by decision type - identifies where AI needs improvement
  - **Decision Policies**: Define which decisions agents own by default vs which require human approval
  - **Feedback Loop**: Override reasons captured for continuous learning (RLHF-style)

**Agentic Inversion & Machine-Speed Economics** (in `docs/`):

- `Visser_Agentic_Inversion_Moltbook_2026.pdf` - **The Agentic Inversion** (Jordi Visser, Feb 2026): Thesis on how digital economic activity transitions from human-constrained labor to machine-driven execution. Key concepts:
  - **Agentic Inversion**: Structural shift from labor→compute, human time→machine time, fatigue→continuous execution. Not automation (same tasks faster) but inversion of who performs economic work.
  - **Velocity as Critical Variable**: Nominal GDP ≈ M × V. Agents increase velocity (V) without increasing employment. Explains asset price inflation outpacing wages, declining labor share of income.
  - **Open-Source Acceleration**: Training remains centralized (capital-intensive) while inference distributes (commodity hardware). Cost of running an agent approaches zero → deploy thousands.
  - **The Overlap Moment**: Present is "unstable moment" where human and machine economies merge. Humans remain as prompters/overseers, gravitational center shifts to autonomous execution.
  - **From Paperwork to Code**: Procurement negotiations compress from months to minutes through parametric contracts. Legal/commercial coordination replaced by programmable logic.
  - **Relevance to Autonomy**: The agentic inversion maps directly to the Powell Framework's copilot→autonomous progression. Override capture during the "overlap moment" trains agents for full autonomy. The article validates Autonomy's AI-as-Labor thesis at the macro level.
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

**Powell Framework Quick Reference**:
- **Five Core Elements**: State (Sₜ), Decision (xₜ), Exogenous Information (Wₜ₊₁), Transition Function (Sᴹ), Objective Function
- **Four Policy Classes**:
  - **PFA** (Policy Function Approximation): Direct S→x mapping (e.g., base-stock rules)
  - **CFA** (Cost Function Approximation): Parameterized optimization (e.g., inventory policies with θ)
  - **VFA** (Value Function Approximation): Q-learning/TD learning (e.g., TRM agent)
  - **DLA** (Direct Lookahead): Model predictive control (e.g., MPC with GNN forecasts)
- **Key Insight**: Current platform uses Monte Carlo for **evaluation**; Powell recommends **optimization over scenarios** to extract optimal policy parameters

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

## External Agent Runtimes & Self-Hosted LLM

**Status**: IMPLEMENTED (2026-02-24)

The platform supports integration with external agent runtimes (PicoClaw, OpenClaw) as thin orchestration layers wrapping the existing REST API. A self-hosted LLM (Qwen 3 via vLLM) eliminates dependency on external LLM providers for data sovereignty.

**Key Documentation**:
- [PICOCLAW_OPENCLAW_IMPLEMENTATION.md](PICOCLAW_OPENCLAW_IMPLEMENTATION.md) - **Implementation Roadmap**: 5-phase plan covering OpenClaw chat interface, PicoClaw edge CDC monitors, multi-agent authorization protocol, simulation swarm, and **channel context capture** (email/Slack/voice/market data signal ingestion into ForecastAdjustmentTRM). Includes comprehensive security risk matrix with CVE tracking (7+ OpenClaw CVEs documented), supply chain attack analysis (ClawHavoc), deployment checklist, and hardening requirements.
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md#external-agent-runtimes-picoclaw--openclaw) - **Integration Details**: PicoClaw/OpenClaw workspace configuration, security considerations, Docker Compose deployment
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md#self-hosted-llm-configuration) - **Self-Hosted LLM**: Qwen 3 model selection, vLLM serving, GPU sharing strategy, Docker Compose overlay
- [AI_AGENTS.md](AI_AGENTS.md#external-agent-runtimes-picoclaw--openclaw) - **Agent Comparison**: PicoClaw/OpenClaw vs built-in agents, hybrid architecture, LLM provider configuration

**Quick Reference**:
- **PicoClaw**: Ultra-lightweight Go binary (<10MB RAM, $10 hardware) for edge CDC monitoring, alert routing via Telegram/Slack, and structured market data capture (weather, economic indicators, commodity prices). **Security**: Pre-v1.0, no formal audit, deploy in read-only containers only.
- **OpenClaw**: Feature-rich agent platform for chat-based planning via WhatsApp/Slack/Teams, human escalation, and **channel context capture** (email/Slack/voice signals → ForecastAdjustmentTRM). **Security**: Minimum version v2026.2.15 required (CVE-2026-25253 critical RCE patched). Never install ClawHub marketplace skills.
- **Self-Hosted LLM**: Qwen 3 8B via vLLM — 96.5% tool calling accuracy, OpenAI-compatible API, 8GB VRAM minimum
- **Docker**: `docker-compose.llm.yml` overlay adds vLLM service to existing stack

**Deployment Commands**:
```bash
# OpenClaw (chat-based planning interface)
make openclaw-setup       # Validate workspace config
make openclaw-up          # Start OpenClaw container
make openclaw-down        # Stop OpenClaw container
make openclaw-logs        # Tail OpenClaw logs

# PicoClaw (edge CDC monitoring fleet)
make picoclaw-workspaces  # Generate per-site workspaces from config
make picoclaw-fleet       # Generate fleet docker-compose.picoclaw.yml
make picoclaw-up          # Start PicoClaw CDC fleet
make picoclaw-down        # Stop PicoClaw fleet
make picoclaw-logs        # Tail PicoClaw fleet logs
make picoclaw-status      # Show fleet container status
```

**Backend Implementation Files**:
- `backend/app/models/edge_agents.py` — 13 SQLAlchemy models (PicoClaw instances/heartbeats/alerts, service accounts, OpenClaw config/channels/skills/sessions, ingested signals, correlations, source reliability, security checklist, activity log)
- `backend/app/services/edge_agent_service.py` — Fleet management, gateway config, security checklist CRUD
- `backend/app/services/signal_ingestion_service.py` — Confidence-gated signal pipeline (sanitize → rate limit → dedup → score → gate → correlate)
- `backend/app/services/authorization_service.py` — Authorization with authority boundaries (`create_agent_authorization_request`, `escalate_to_human`)
- `backend/app/services/escalation_formatter.py` — Tier 2 (agent) → Tier 3 (human) escalation bridge with ranked alternatives
- `backend/app/services/powell/authority_boundaries.py` — Per-agent action classification (12 roles) with target routing and SLA
- `backend/app/api/deps.py` — Service account auth middleware (`get_current_user_or_service_account`)
- `backend/app/api/endpoints/edge_agents.py` — REST API: `/edge-agents/*` + `/signals/*` (40+ endpoints, service account auth)
- `backend/app/api/endpoints/planning_scenarios.py` — `POST /scenarios/what-if` for pre-authorization evaluation

**Deployment Files**:
- `deploy/openclaw/workspace/SOUL.md` — OpenClaw agent persona
- `deploy/openclaw/workspace/skills/` — 9 skills (supply-plan-query, atp-check, override-decision, ask-why, kpi-dashboard, signal-capture, escalate-authorization, voice-signal, email-signal)
- `deploy/openclaw/openclaw.json` — LLM provider config + channel stubs
- `deploy/openclaw/docker-compose.openclaw.yml` — OpenClaw container definition
- `deploy/picoclaw/templates/` — HEARTBEAT.sh, DIGEST.sh, MARKET_SIGNAL.sh, config.json.template, IDENTITY.md.template, SOUL.md, skills/
- `deploy/picoclaw/generate_workspaces.py` — Per-site workspace generator from supply chain config
- `deploy/picoclaw/generate_fleet_compose.py` — Fleet Docker Compose generator

**Frontend Files**:
- `frontend/src/pages/admin/PicoClawManagement.jsx` — Fleet dashboard, alerts, CDC config, service accounts
- `frontend/src/pages/admin/OpenClawManagement.jsx` — Gateway overview, skills, channels, LLM config
- `frontend/src/pages/admin/SignalIngestionDashboard.jsx` — Signal monitoring, review queue, source reliability, correlations
- `frontend/src/pages/admin/EdgeAgentSecurity.jsx` — Security overview, CVE tracker, deployment checklist, integration health
- `frontend/src/services/edgeAgentApi.js` — API client for all edge agent operations

**Navigation**: Administration > Edge Agents (PicoClaw Fleet, OpenClaw Gateway, Signal Ingestion, Edge Security)

---

## Architectural Refactoring

**Status**: 🔄 **IN PROGRESS** - Refactoring from Beer Game-centric to AWS SC-first

See [ARCHITECTURAL_REFACTORING_PLAN.md](ARCHITECTURAL_REFACTORING_PLAN.md) for:
- 7-phase transformation plan (25 weeks)
- Navigation restructuring (Planning becomes primary, Gamification becomes secondary)
- Database migration strategy (15 missing AWS SC entities)
- Service layer refactoring (AWS SC services + simulation module)
- Frontend page additions (Planning, Execution, AI Agent pages)

**Key Changes**:
- **Project Positioning**: AWS SC with AI → Differentiators → Simulation
- **Navigation**: Planning (primary), Execution, AI & Agents, Simulation (secondary)
- **Beer Game**: Repositioned as simulation/training module (not primary focus)

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
2. Creates default users and groups
3. Generates showcase scenarios with LLM and GNN agents

### Training Hyperparameters
Admin UI exposes: epochs, device, window, horizon, data source.
Code-only: architecture (hidden dims, layers), learning rate, batch size, RL hyperparameters.
No automated hyperparameter search - requires manual orchestration.

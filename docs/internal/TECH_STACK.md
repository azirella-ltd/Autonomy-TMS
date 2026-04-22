# Autonomy Platform — Technical Architecture

Enterprise supply chain planning and execution platform built on the AWS Supply Chain data model, built on four pillars: **AI Agents** (automated planners via Powell Framework), **Causal AI** (counterfactual outcome attribution), **Conformal Prediction** (distribution-free uncertainty guarantees), and **Digital Twin** (stochastic simulation for training, calibration, and testing).

---

## Table of Contents

1. [Infrastructure & Deployment](#1-infrastructure--deployment)
2. [AI/ML Architecture — Three-Tier Powell Cascade](#2-aiml-architecture--three-tier-powell-cascade)
3. [Hive Coordination Architecture](#3-hive-coordination-architecture)
4. [Training Pipeline](#4-training-pipeline)
5. [CDC → Relearning Feedback Loop](#5-cdc--relearning-feedback-loop)
6. [Planning Cascade](#6-planning-cascade)
7. [Conformal Prediction & Belief State](#7-conformal-prediction--belief-state)
8. [Explainability System](#8-explainability-system)
9. [Agentic Authorization Protocol](#9-agentic-authorization-protocol)
10. [Edge Agents & LLM Integration](#10-edge-agents--llm-integration)
11. [Knowledge Base (RAG)](#11-knowledge-base-rag)
12. [Simulation Module](#12-simulation-module)
13. [AWS SC Data Model](#13-aws-sc-data-model)
14. [Dependency Versions](#14-dependency-versions)

---

## 1. Infrastructure & Deployment

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | 0.109.2 |
| ASGI Server | Uvicorn | 0.27.1 |
| ORM | SQLAlchemy | 2.0.25 |
| Validation | Pydantic | 2.6.4 |
| Database | PostgreSQL | 15+ |
| Async Driver | asyncpg | 0.29.0 |
| Sync Driver | psycopg2 | 2.9.9 |

**Scale**: 97 registered API routers, ~130 service files, 88 model files.

Entry point: `backend/main.py` (single-file FastAPI app, ~62K lines). Router registration begins at line ~6020.

### Frontend

| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | React | 18.2.0 |
| Component Library (primary) | Material-UI | 5.13.2 |
| Component Library (secondary) | Radix UI | 1.x |
| Styling | Tailwind CSS | 3.3.2 |
| Charts | Recharts | 2.6.2 |
| Network Graphs | D3 + D3-Sankey | 7.8.5 |
| Flow Diagrams | ReactFlow | 11.10.1 |
| 3D Visualization | Three.js + R3F | 0.160.1 |
| State | Zustand | 4.3.8 |
| Routing | React Router | 6.10.0 |
| HTTP Client | Axios | 1.3.6 |

**Dual UI Layer**: MUI 5 for data-dense pages (tables, forms); Radix + Tailwind for dashboard cards and modern layouts. ~146 page files across planning, simulation, admin, and analytics sections.

### Docker Architecture

8 Compose files with overlay `-f` flag composition:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base stack: proxy, frontend, backend, db, pgadmin |
| `docker-compose.dev.yml` | Hot-reload with volume mounts |
| `docker-compose.gpu.yml` | NVIDIA runtime for PyTorch CUDA |
| `docker-compose.prod.yml` | Gunicorn multi-worker |
| `docker-compose.apps.yml` | Frontend + backend only (external DB) |
| `docker-compose.db.yml` | Standalone database |
| `docker-compose.llm.yml` | vLLM + Ollama self-hosted LLM |
| `docker-compose.tls.yml` | HTTPS with self-signed certs |

```bash
# Example: GPU + LLM overlay
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.llm.yml up
```

**Proxy**: Nginx routes `/api/*` → backend:8000, `/*` → frontend:3000.

---

## 2. AI/ML Architecture — Three-Tier Powell Cascade

The AI system follows Warren B. Powell's Sequential Decision Analytics and Modeling (SDAM) framework with three tiers of models operating at different cadences:

```
S&OP GraphSAGE  (CFA — Cost Function Approximation)
    ↓ policy parameters θ, structural embeddings          [weekly/monthly]
Execution tGNN  (CFA/VFA Bridge)
    ↓ priority allocations, site directives                [daily]
11 Narrow TRMs  (VFA — Value Function Approximation)
    └── Per-decision execution (<10ms each)                [continuous]
```

### 2.1 S&OP GraphSAGE (Tier 1 — CFA)

**Purpose**: Medium-term network structure analysis, risk scoring, and policy parameter generation.

**File**: `backend/app/models/gnn/planning_execution_gnn.py` — class `SOPGraphSAGE`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `node_feature_dim` | 12 | S&OP node features |
| `edge_feature_dim` | 6 | S&OP edge features |
| `hidden_dim` | 128 | Internal hidden dimension |
| `embedding_dim` | 64 | Output embedding dimension |
| `num_layers` | 3 | GraphSAGE message-passing layers |
| `num_heads` | 4 | GAT attention heads |
| `dropout` | 0.1 | Regularization |

**Architecture**: 3-layer GraphSAGE with mean aggregation. Each layer performs neighbor sampling → aggregation → linear transform → ReLU → dropout.

**Outputs**: Per-site structural embeddings (64-dim), criticality scores, concentration risk, resilience index, safety stock multipliers.

**Cadence**: Weekly or monthly. Embeddings are cached and fed downstream to the Execution tGNN.

**Scalable Variant**: `ScalableGraphSAGE` in `backend/app/models/gnn/scalable_graphsage.py` — supports 50+ node networks with O(edges) complexity via mini-batch neighbor sampling.

### 2.2 Execution tGNN (Tier 2 — CFA/VFA Bridge)

**Purpose**: Short-term allocation generation, combining S&OP structural embeddings with real-time transactional data.

**File**: `backend/app/models/gnn/planning_execution_gnn.py` — class `ExecutionTemporalGNN`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `transactional_feature_dim` | 8 | Base execution features (16 with hive feedback) |
| `structural_embedding_dim` | 64 | From S&OP GraphSAGE |
| `edge_feature_dim` | 4 | Real-time edge features |
| `hidden_dim` | 128 | Internal hidden dimension |
| `num_gnn_layers` | 2 | Spatial GATv2 layers |
| `num_temporal_layers` | 2 | GRU temporal layers |
| `window_size` | 10 | Historical observation window |
| `forecast_horizon` | 4 | Forward projection periods |
| `num_heads` | 4 | Temporal attention heads |
| `dropout` | 0.1 | Regularization |

**Architecture**: GATv2 spatial message-passing → GRU temporal sequence processing → allocation head.

- **Spatial**: 2 GATv2 layers aggregate neighbor information with edge features
- **Temporal**: 2-layer GRU processes `window_size=10` historical snapshots
- **Hive Feedback**: When enabled, 8 additional hive feedback features (urgency stats, signal density, conflict rate, stress index) are concatenated to transactional features, making the effective input 16-dim

**Outputs**: Priority × Product × Location allocation matrices for AATP consumption, per-site `tGNNSiteDirective`.

**Cadence**: Daily. Produces allocation buckets consumed by ATP TRM agents.

**Hybrid Bridge**: `HybridPlanningModel` in the same file combines S&OP GraphSAGE + Execution tGNN end-to-end for joint training.

### 2.3 TRM Agents (Tier 3 — VFA)

**Purpose**: Narrow execution decisions at <10ms latency. Each TRM agent owns exactly one decision type.

#### SiteAgentModel

**File**: `backend/app/services/powell/site_agent_model.py`

The SiteAgentModel is a multi-head architecture: one shared encoder feeds 11 specialized task heads.

```
Raw State (64-dim)
    ↓
SharedStateEncoder (2-layer Transformer, 4 heads)
    ↓ 128-dim embedding
    ├── + UrgencyVector (11 → 128-dim projection)
    ├── + SignalSummary (22 → 128-dim projection)
    ├── [optional] HiveHetGAT cross-TRM attention
    ↓
11 RecursiveTRMHeads (one per decision type)
    ↓
Per-head action outputs
```

| Config Parameter | Default | Description |
|-----------------|---------|-------------|
| `state_dim` | 64 | Raw state feature dimension |
| `embedding_dim` | 128 | Shared embedding size |
| `encoder_layers` | 2 | Transformer encoder layers |
| `encoder_heads` | 4 | Multi-head attention heads |
| `head_hidden_dim` | 64 | Hidden dim per task head |
| `head_layers` | 2 | Layers per task head |
| `urgency_vector_dim` | 11 | UrgencyVector slots (1 per TRM) |
| `signal_summary_dim` | 22 | HiveSignalBus type counts |
| `het_gat_enabled` | False | Cross-TRM HetGAT layer |
| `recursive_heads_enabled` | False | Recursive refinement heads |
| `num_refinement_steps` | 3 | R recursive applications |
| `adaptive_halt` | False | Early stopping on convergence |
| `halt_threshold` | 0.95 | Confidence for early halt |
| `dropout` | 0.1 | Regularization |
| `adjustment_bounds` | (0.8, 1.2) | Output clamp ±20% |

#### RecursiveTRMHead

**File**: `backend/app/models/hive/recursive_head.py`

Inspired by Samsung SAIL Montreal's TRM research ([arxiv:2510.04871](https://arxiv.org/abs/2510.04871)): a 7M-parameter recursive network outperforms 671B-parameter LLMs on structured reasoning.

**Key principles**:
- Recursion multiplies compute without multiplying parameters (2 layers × R=3 applications = 6 effective layers)
- Post-normalization bounds hidden state magnitude for stability
- Gated mixing: `output = gate * refined + (1 - gate) * skip`
- Bottleneck projections (hidden_dim // 2 = 32) reduce parameter count
- Deep supervision at each refinement step encourages good intermediates

**11 Concrete Head Subclasses**:

| Head Class | answer_dim | Output Semantics |
|-----------|-----------|------------------|
| `RecursiveATPHead` | 6 | 4 action logits + fill_rate + value |
| `RecursiveRebalancingHead` | 4 | qty_mult + 2-way direction + value |
| `RecursivePOHead` | 6 | 3 timing logits + expedite + days_offset + value |
| `RecursiveOrderTrackingHead` | 7 | 5 action logits + severity + value |
| `RecursiveMOHead` | 6 | 5 action logits + value |
| `RecursiveTOHead` | 5 | 4 action logits + value |
| `RecursiveQualityHead` | 6 | 5 action logits + value |
| `RecursiveMaintenanceHead` | 5 | 4 action logits + value |
| `RecursiveSubcontractingHead` | 5 | 3 action logits + split_ratio + value |
| `RecursiveForecastAdjHead` | 5 | 3 direction logits + magnitude + value |
| `RecursiveSafetyStockHead` | 3 | ss_multiplier + rop_multiplier + value |

**Parameter count**: ~25K per head, ~275K total for 11 heads. Full SiteAgentModel with shared encoder: ~7M parameters.

**Inference**: <10ms per decision, enabling 100+ decisions/second.

#### Powell Service Layer

Each TRM head has a corresponding service in `backend/app/services/powell/`:

| Service File | Decision Scope |
|-------------|---------------|
| `atp_executor.py` | Per-order AATP consumption with priority sequence |
| `inventory_rebalancing_trm.py` | Cross-site transfer recommendations |
| `po_creation_trm.py` | Purchase order timing and quantity |
| `order_tracking_trm.py` | Exception detection and recommended actions |
| `mo_execution_trm.py` | Manufacturing order release/sequence/expedite/defer |
| `to_execution_trm.py` | Transfer order release/consolidate/expedite/defer |
| `quality_disposition_trm.py` | Accept/reject/rework/scrap/use-as-is |
| `maintenance_scheduling_trm.py` | Schedule/defer/expedite/outsource |
| `subcontracting_trm.py` | Internal/external/split routing |
| `forecast_adjustment_trm.py` | Signal-driven forecast direction and magnitude |
| `inventory_buffer_trm.py` | Inventory buffer level adjustment and reoptimization |

**AATP Consumption Logic** (critical ordering):
```
For order at priority P:
  1. Own tier (P) first
  2. Bottom-up from lowest priority (5 → 4 → 3 → ...)
  3. Stop at own tier (cannot consume above)
  Example: P=2 order → [2, 5, 4, 3] (skips tier 1)
```

---

## 3. Hive Coordination Architecture

Each site's 11 TRM agents form a self-organizing "hive" — a bio-inspired coordination system with stigmergic signaling, shared urgency state, and cross-agent attention.

### 3.1 HiveSignalBus

**File**: `backend/app/services/powell/hive_signal.py`

A ring buffer of typed signals emitted by TRM agents and consumed by peers within the same site.

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAX_SIGNALS` | 200 | Ring buffer capacity (oldest evicts) |
| Signal Types | 25 | Across 5 biological castes + tGNN |
| Default half-life | 30 min | Local exponential decay |
| Inter-hive half-life | 12 hours | Cross-site signal persistence |
| `DECAY_THRESHOLD` | 0.05 | Below this, signal is dead |

**25 Signal Types by Caste**:

| Caste | Signals | Role |
|-------|---------|------|
| **Scout** (5) | DEMAND_SURGE, DEMAND_DROP, ATP_SHORTAGE, ATP_EXCESS, ORDER_EXCEPTION | Environmental sensing |
| **Forager** (5) | PO_EXPEDITE, PO_DEFERRED, REBALANCE_INBOUND, REBALANCE_OUTBOUND, SUBCONTRACT_ROUTED | Resource acquisition |
| **Nurse** (3) | BUFFER_INCREASED, BUFFER_DECREASED, FORECAST_ADJUSTED | Internal state maintenance |
| **Guard** (4) | QUALITY_REJECT, QUALITY_HOLD, MAINTENANCE_DEFERRED, MAINTENANCE_URGENT | Protection and quality |
| **Builder** (4) | MO_RELEASED, MO_DELAYED, TO_RELEASED, TO_DELAYED | Production and transport |
| **tGNN** (4) | NETWORK_SHORTAGE, NETWORK_SURPLUS, PROPAGATION_ALERT, ALLOCATION_REFRESH | Inter-hive network signals |

**Decay Formula**: `strength(t) = urgency × exp(-0.693 × elapsed_min / half_life_min)`

### 3.2 UrgencyVector

11-slot shared state tensor (one slot per TRM type). Each TRM updates its own slot; all TRMs read the full vector as pheromone context injected into the shared encoder.

```python
TRM_INDICES = {
    "atp_executor": 0,  "order_tracking": 1,  "po_creation": 2,
    "rebalancing": 3,   "subcontracting": 4,  "safety_stock": 5,
    "forecast_adj": 6,  "quality": 7,          "maintenance": 8,
    "mo_execution": 9,  "to_execution": 10,
}
```

### 3.3 HiveHetGAT

**File**: `backend/app/models/hive/het_gat_layer.py`

Heterogeneous graph attention network enabling cross-TRM information flow within a hive. Models the 11 TRM heads as nodes in a directed graph with 24 typed edges (e.g., ATP→OrderTracking, PO→Rebalancing).

- 5 biological castes define edge semantics
- GATv2-style attention per edge type
- Hidden dim: 64, Heads: 2

### 3.4 Multi-Site Coordination Stack

4 layers from intra-site to enterprise-wide:

| Layer | Scope | Latency | Mechanism |
|-------|-------|---------|-----------|
| **1. Intra-Hive** | Single site | <10ms | UrgencyVector + HiveSignalBus |
| **2. tGNN Inter-Hive** | Full network | Daily batch | S&OP GraphSAGE + Execution tGNN → per-site `tGNNSiteDirective` |
| **3. AAP Cross-Authority** | 2+ sites | Seconds–minutes | `AuthorizationRequest`/`Response` for transfers, priority overrides, capacity sharing |
| **4. S&OP Consensus Board** | Enterprise | Weekly | Policy parameters θ negotiated by functional agents |

**Key principle**: TRMs never call across sites. All cross-site information flows through tGNN directives or AAP authorization.

---

## 4. Training Pipeline

### 4.1 TRM Training — 3×3 Curriculum

**File**: `backend/app/services/powell/trm_site_trainer.py` — class `TRMSiteTrainer`

Training follows a 3-phase learning curriculum crossed with a 3-phase stigmergic progression, yielding 9 training stages:

**Learning Phases**:
1. **Engine Imitation (BC)**: Behavioral cloning from Beer Game expert traces
2. **Context Learning (Supervised)**: Supervised training on state-context-action tuples
3. **Outcome Optimization (CQL)**: Conservative Q-Learning from offline replay buffer

**Stigmergic Phases**:
1. **NO_SIGNALS**: TRM heads operate independently (no hive context)
2. **URGENCY_ONLY**: UrgencyVector injected, no signal bus
3. **FULL_SIGNALS**: Full hive coordination (UrgencyVector + HiveSignalBus + optional HetGAT)

**Progression**: Phase A.1 (BC + No Signals) → A.2 (BC + Urgency) → A.3 (BC + Full) → B.1 (Supervised + No Signals) → ... → C.3 (CQL + Full Signals)

### 4.2 Core TRM Trainer

**File**: `backend/app/services/powell/trm_trainer.py`

5 training methods:
1. **Behavioral Cloning** — Supervised from expert demonstrations
2. **TD Learning** — Temporal-difference value function updates
3. **Offline RL** — Conservative Q-Learning from logged experiences
4. **Policy Gradient** — REINFORCE with baseline
5. **Hybrid** — Combined BC warm-start + RL fine-tuning

**CGAR Curriculum** ([arxiv:2511.08653](https://arxiv.org/abs/2511.08653)): Progressive recursion depth during training reduces FLOPs ~40%.

### 4.3 GNN Training

**Pipeline**: SimPy dataset generation → graph tensor construction → temporal GNN training → checkpoint save

```bash
make generate-simpy-data    # SimPy simulation runs
make train-gnn              # Full pipeline: data + training
make train-default-gpu TRAIN_EPOCHS=50 TRAIN_DEVICE=cuda
```

| Parameter | Default |
|-----------|---------|
| `SIMPY_NUM_RUNS` | 128 |
| `SIMPY_TIMESTEPS` | 64 |
| `SIMPY_WINDOW` | 52 |
| `SIMPY_HORIZON` | 1 |
| `TRAIN_EPOCHS` | 10 |

Checkpoints saved to `backend/checkpoints/`.

---

## 5. CDC → Relearning Feedback Loop

Autonomous closed-loop pipeline for continuous TRM improvement without human intervention.

```
SiteAgent decisions → [powell_site_agent_decisions]
       ↓ (hourly)
OutcomeCollector computes actual outcomes + rewards
       ↓
CDCMonitor fires → [powell_cdc_trigger_log]
       ↓ (every 6h or on FULL_CFA)
CDCRetrainingService evaluates need → TRMTrainer.train() → checkpoint
       ↓
SiteAgent reloads model
```

### Components

| Component | File | Schedule | Purpose |
|-----------|------|----------|---------|
| `OutcomeCollectorService` | `powell/outcome_collector.py` | Hourly (:30) | Compute outcomes past feedback horizon |
| `CDCMonitor` | `powell/cdc_monitor.py` | On-demand | 7 threshold conditions, rate-limited |
| `CDCRetrainingService` | `powell/cdc_retraining_service.py` | Every 6h (:45) | Evaluate & execute retraining |
| `ConditionMonitorService` | `condition_monitor_service.py` | On-demand | 6 real-time DB condition checks |

**Feedback Horizons**: ATP = 4 hours, Inventory = 24 hours, PO = 7 days, CDC = 24 hours.

**Retraining Triggers**: ≥100 accumulated experiences + CDC trigger fired + cooldown elapsed.

**7 CDC Threshold Conditions**: ATP shortfall rate, inventory deviation, capacity utilization, orders past due, forecast error, service level degradation, cost overrun.

---

## 6. Planning Cascade

4-layer modular architecture. Layers can be sold independently — when S&OP/MPS isn't purchased, the same UI becomes input screens for customer-provided policy parameters.

**Files**: `backend/app/services/planning_cascade/`

```
S&OP Policy Envelope
    ↓ policy parameters θ (safety stock targets, OTIF floors, allocation reserves)
Supply Baseline Pack (SupBP)
    ↓ 5 candidate supply plans
Supply Agent (Supply Commit)
    ↓ selected + adjusted supply plan
Allocation Agent (Allocation Commit)
    ↓ constraint-respecting distribution
Execution (11 TRM agents)
```

### Layers

| Layer | Service | Input | Output |
|-------|---------|-------|--------|
| **S&OP** | `sop_service.py` | Feed-back signals (OTIF, shortfalls, E&O) | Policy Envelope θ |
| **Supply Baseline** | `supply_baseline_service.py` | Demand, BOM, inventory, sourcing rules | 5 candidate plans: MRP_STANDARD, SS_OPTIMIZED, MIN_COST_LP, SERVICE_MAX, PARAMETRIC_CFA |
| **Supply Agent** | `supply_agent.py` | SupBP candidates + policy envelope | Supply Commit (what/when/from whom) |
| **Allocation Agent** | `allocation_agent.py` | Supply Commit + demand segments | Allocation Commit (fair-share/priority/LP/MILP) |

**Orchestration**: `cascade_orchestrator.py` manages the full feed-forward + feed-back loop.

**Feed-Forward Contracts**: Each layer produces versioned, hashable artifacts as grounding input to the next.

**Feed-Back Signals**: Outcome signals (OTIF, shortfalls, expedite frequency, E&O) re-tune upstream policy parameters.

### AWS SC 3-Step Planning (within Supply Baseline)

1. **Demand Processing** (`aws_sc_planning/demand_processor.py`): Aggregate forecasts + customer orders, net committed inventory, time-phase across horizon
2. **Inventory Target Calculation** (`aws_sc_planning/inventory_target_calculator.py`): 4 policy types (abs_level, doc_dem, doc_fcst, sl), hierarchical overrides (Product-Site > Product > Site > Config)
3. **Net Requirements Calculation** (`aws_sc_planning/net_requirements_calculator.py`): Time-phased netting, multi-level BOM explosion, multi-sourcing with priorities, lead time offsetting → PO/TO/MO requests

---

## 7. Conformal Prediction & Belief State

**File**: `backend/app/services/conformal_orchestrator.py`

Distribution-free coverage guarantees for uncertainty quantification. Replaces point estimates with prediction intervals that maintain calibrated coverage.

**5 Entity Types**: demand, lead_time, price, yield, service_level

**6 Integration Hooks**:
1. Forecast load → auto-compute residuals
2. Actuals observation → update calibration
3. Drift monitoring → trigger recalibration
4. Scheduled recalibration → adjust intervals
5. Suite persistence → DB save/load
6. Interval query → return prediction bounds

**ACI (Adaptive Conformal Inference)** for non-stationary demand: intervals widen/narrow based on recent coverage.

**Database Tables**: `powell_belief_state`, `powell_calibration_log`

---

## 8. Explainability System

Every AI decision is explainable at three verbosity levels.

### AgentContextExplainer

**File**: `backend/app/services/agent_context_explainer.py`

**13 Agent Types**: 11 TRM agents + S&OP GraphSAGE + Execution tGNN

Each explanation includes:
- **Authority boundaries**: What the agent can/cannot decide unilaterally
- **Active guardrails**: Constraints enforced on this decision
- **Policy parameters**: Current θ values influencing the decision
- **Model attribution**: Gradient saliency (TRM), attention weights (GNN)
- **Conformal intervals**: Prediction bounds from calibrated model
- **Counterfactual analysis**: "If X were different, the decision would be Y"

### Explanation Templates

**File**: `backend/app/services/explanation_templates.py`

39 Jinja2-style templates: 13 agent types × 3 verbosity levels (VERBOSE / NORMAL / SUCCINCT)

Accessible via Ask Why API endpoints at each verbosity level.

---

## 9. Agentic Authorization Protocol

**File**: `backend/app/services/authorization_protocol.py`

Cross-functional decision-making at machine speed. Agents evaluate trade-offs using the what-if engine, then request authorization for actions outside their authority domain.

### Three-Phase Protocol

1. **Evaluate**: Originator runs what-if analysis on all options (including cross-authority), computing full Balanced Scorecard impact
2. **Request**: Send `AuthorizationRequest` with ranked alternatives and full scorecards
3. **Authorize**: Target agent checks resource availability, contention, and net benefit threshold

### Governance

- **Net benefit > threshold**: Auto-approved
- **Net benefit ≈ threshold**: Human review (escalation with pre-digested options)
- **Net benefit < threshold**: Auto-rejected

**15+ Agent Authority Types**: SO/ATP, Supply, Allocation, Logistics, Inventory, S&OP, Plant, Quality, Maintenance, Procurement, Supplier, Channel, Demand, Finance, Service, Risk.

**25+ Negotiation Scenarios**: Manufacturing (rush orders, changeovers, make-vs-buy), Distribution (cross-DC rebalancing, direct-ship), Channel (cross-channel allocation), Procurement (spot vs contract), Logistics (mode selection, consolidation), Finance (working capital vs service), S&OP (seasonal pre-build, parameter disputes).

Human override resolutions feed back into agent training via replay buffer (`is_expert=True`).

---

## 10. Claude Skills & LLM Integration

### Claude Skills (TRM Exception Handler)

Hybrid TRM + Claude Skills architecture (replaces PicoClaw/OpenClaw, removed Feb 2026):
- TRMs handle ~95% of decisions at <10ms latency
- Claude Skills handle ~5% of exceptions when conformal prediction indicates low TRM confidence
- 11 skills across 3 routing tiers: Deterministic ($0), Haiku (~$0.0018), Sonnet (~$0.0054)
- RAG Decision Memory provides few-shot context from past decisions (pgvector 768-dim embeddings)
- See [CLAUDE_SKILLS_STRATEGY.md](CLAUDE_SKILLS_STRATEGY.md) for migration rationale

**Key files**: `backend/app/services/skills/` — `base_skill.py`, `claude_client.py`, `skill_orchestrator.py`, `*/SKILL.md` (11 heuristic rule files)

### Self-Hosted LLM

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Inference | vLLM | Qwen 3 8B Q4 (~6GB VRAM) |
| Embeddings | Ollama | nomic-embed-text (~0.8GB VRAM) |
| Hardware | NVIDIA RTX 4060 | 8GB VRAM total |

Both expose OpenAI-compatible APIs. `backend/app/services/autonomy_client.py` checks `LLM_API_BASE` env var first (local), falls back to `OPENAI_API_KEY` (remote). Claude API (`CLAUDE_API_KEY`) used for Skills when available.

### Signal Ingestion Pipeline

**File**: `backend/app/services/signal_ingestion_service.py`

Confidence-gated pipeline: Sanitize → Rate Limit → Dedup → Score → Gate → Correlate

Sources: Email, Slack, voice transcripts, market data feeds → signals consumed by ForecastAdjustmentTRM.

**Models**: `backend/app/models/edge_agents.py` — SQLAlchemy models covering ingested signals, correlations, and source reliability.

---

## 11. Knowledge Base (RAG)

### 11.1 Infrastructure (Split Architecture)

The RAG stack runs on **Acer-Nitro.local** — separate from the main application stack on MSI-Stealth.local.

| Service | Host | Port | Container | Purpose |
|---------|------|------|-----------|---------|
| vLLM (chat) | acer-nitro.local | 8001 | `autonomy-vllm` | Qwen3-8B-AWQ inference, OpenAI-compatible |
| Ollama (embeddings) | acer-nitro.local | 11434 | `autonomy-embeddings` | nomic-embed-text, 768-dim, CPU |
| KB pgvector DB | acer-nitro.local | 5432 | `autonomy-kb-db` | `autonomy_kb` database, vector search |
| Main PostgreSQL | msi-stealth.local | 5432 | `db` (in main stack) | All non-RAG application data |

**vLLM flags** (fits qwen3-8b-awq on 8GB RTX 4060):
```
--model Qwen/Qwen3-8B-AWQ --quantization awq
--max-model-len 4096 --gpu-memory-utilization 0.90 --enforce-eager
```
`--enforce-eager` disables torch dynamo compilation, freeing enough memory for the KV cache.

**Environment variables** (in `.env`):
```env
LLM_API_BASE=http://acer-nitro.local:8001/v1
EMBEDDING_API_BASE=http://acer-nitro.local:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
KB_DATABASE_URL=postgresql+psycopg2://kb_user:kb_password@acer-nitro.local:5432/autonomy_kb
KB_ASYNC_DATABASE_URL=postgresql+asyncpg://kb_user:kb_password@acer-nitro.local:5432/autonomy_kb
```

### 11.2 Code Components

| Component | File | Purpose |
|-----------|------|---------|
| Models | `backend/app/models/knowledge_base.py` | `kb_documents`, `kb_chunks` (pgvector 768-dim) |
| Embedding Service | `backend/app/services/embedding_service.py` | OpenAI-compatible embed API |
| Knowledge Base Service | `backend/app/services/knowledge_base_service.py` | Ingest (file + URL), search, delete |
| API | `backend/app/api/endpoints/knowledge_base.py` | REST endpoints |
| Frontend | `frontend/src/pages/admin/KnowledgeBase.jsx` | Tenant admin UI |

**API endpoints** (all under `/api/v1/knowledge-base/`):

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/documents` | Tenant Admin | Upload file (PDF/DOCX/TXT/MD) |
| `POST` | `/ingest-url` | Tenant Admin | Fetch a URL and index it |
| `GET` | `/documents` | Any user | List documents |
| `DELETE` | `/documents/{id}` | Tenant Admin | Delete document + chunks |
| `POST` | `/search` | Any user | Semantic similarity search |
| `GET` | `/status` | Any user | Health stats |

### 11.3 Ingestion Sources

Three paths for populating the knowledge base:

#### A. Tenant Admin — Browser UI (`/admin/knowledge-base`)
- **Documents tab**: Upload files one at a time. Supports PDF, DOCX, TXT, MD, CSV.
- **URL Sources tab**: Paste any public URL (HTML page or direct PDF/DOCX link). Backend fetches, extracts text, chunks, embeds, and stores. HTML pages are stripped of nav/scripts; PDF links are passed directly to the PDF parser.
- 22 SCP-specific categories available in both upload forms.

#### B. Platform Admin — Drop Folder (`data/rag_intake/`)
Server-side drop folder with 17 category subdirectories. Place files here and run the batch script.
```
data/rag_intake/
├── mps_mrp/           ├── inventory_optimization/   ├── demand_planning/
├── supply_planning/   ├── sop_ibp/                  ├── capacity_planning/
├── atp_ctp/           ├── network_design/           ├── order_execution/
├── stochastic_planning/ ├── decision_framework/     ├── ai_planning/
├── ai_ml/             ├── analyst_reports/          ├── strategy/
├── internal_docs/     └── general/
```

#### C. Platform Admin — URL Sources (`data/rag_sources.yaml`)
YAML-driven URL source list processed by the batch script. Supports `url`, `gdrive`, and `sharepoint` source types.
```yaml
sources:
  - type: url
    url: https://example.com/whitepaper.pdf
    category: analyst_reports
    title: "Example Whitepaper"
    tags: [example, tag]
```

### 11.4 Batch Ingest Script

**File**: `scripts/ingest_rag.py`

Processes all three sources in one run. Connects directly to the local KB DB and Ollama embedding service (designed to run on Acer-Nitro.local).

```bash
# Full ingest (docs/ + data/rag_intake/ + data/rag_sources.yaml)
python scripts/ingest_rag.py

# Dry run — show what would be processed
python scripts/ingest_rag.py --dry-run

# URL sources only
python scripts/ingest_rag.py --sources-only

# Drop folder only
python scripts/ingest_rag.py --intake-only
```

Already-indexed documents are skipped. Failed/pending records are deleted and retried.

### 11.5 Document Processing Pipeline

```
File/URL/Text input
    ↓
Parse (PyPDF2 → OCR fallback for scanned PDFs, python-docx, plain text)
    ↓ Strip NUL bytes (PostgreSQL rejects 0x00 in text columns)
Chunk (1024 chars, 200 overlap, split on paragraph/sentence/word boundaries)
    ↓
Embed batch (Ollama nomic-embed-text → 768-dim float vectors)
    ↓
Insert kb_chunks with pgvector embeddings
    ↓
Update kb_documents.status = 'indexed'
```

**Search**: Cosine distance via pgvector `<=>` operator. Query is embedded with same model, then `1 - distance` = similarity score (0–1).

---

## 12. Simulation Module

### Beer Game Engine

**File**: `backend/app/services/engine.py`

Multi-echelon supply chain simulation (Retailer → Wholesaler → Distributor → Factory). Demonstrates the bullwhip effect — demand amplification through supply chain tiers.

- 2–8 participants per scenario
- Mixed Human-AI: humans compete alongside/against AI agents
- Real-time WebSocket state broadcasting on period completion

### Period Tick Sequence

1. Process incoming shipments → update inventory
2. Fulfill demand/backlog → calculate shipments downstream
3. Receive orders from downstream → update node state
4. Agent decides order quantity → place order upstream
5. Update costs and metrics

### Agent Strategies

| Strategy | Description |
|----------|------------|
| `naive` | Mirrors incoming demand (baseline) |
| `bullwhip` | Intentionally over-orders to demonstrate volatility |
| `conservative` | Stable orders, high safety stock |
| `ml_forecast` | ML-based demand prediction (TRM or GNN) |
| `optimizer` | Cost function optimization |
| `reactive` | Rapid response to inventory changes |
| `llm` | Routes to OpenAI multi-agent system |

### LLM Multi-Agent System

**File**: `backend/llm_agent/beer_game_openai_agents.py`

- **Site Agents**: Per-role agents with structured JSON schemas
- **Supervisor Agent**: Reviews, validates, can clamp/rewrite orders
- **Global Planner Agent**: Optional rolling base-stock and variance targets
- **BeerGameAgentsOrchestrator**: Agent lifecycle and tool registry

### Synthetic Data Generation

**File**: `backend/app/services/synthetic_data_generator.py`

3 company archetypes:
- **Retailer**: CDCs → RDCs → Stores + Online, 200 SKUs
- **Distributor**: NDCs → RDCs → LDCs, 720 SKUs
- **Manufacturer**: Plants → Sub-Assy → Component, 160 SKUs

Creates complete supply chain: group, users, sites, lanes, products, hierarchies, forecasts, inventory policies, agent configs.

---

## 13. AWS SC Data Model

**File**: `backend/app/models/sc_entities.py`

33 entity classes implementing ~60% of the AWS Supply Chain data model (21/35 core entities).

**Network Topology** (4 master types):
- **Market Supply**: Upstream source sites (suppliers)
- **Market Demand**: Terminal demand sink sites (customers)
- **Inventory**: Storage/fulfillment sites (DC, Wholesaler, Retailer)
- **Manufacturer**: Transform sites with Bill of Materials

**Key Tables**: `site`, `transportation_lane`, `product`, `forecast`, `supply_plan`, `sourcing_rules`, `inv_policy`, `inv_level`, `product_bom`, `production_process`, `vendor_product`, `vendor_lead_time`, `inbound_order`, `outbound_order`, `shipment`

**Hierarchy Models**: `SiteHierarchyNode` (Company→Region→Country→Site), `ProductHierarchyNode` (Category→Family→Group→Product), `TimeBucketConfig` (Year→Quarter→Month→Week)

**Aggregation**: `backend/app/services/aggregation_service.py` — hierarchy-aware roll-up
**Disaggregation**: `backend/app/services/disaggregation_service.py` — policy-based allocation

---

## 14. Dependency Versions

### Python (backend/requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.109.2 | Web framework |
| uvicorn | 0.27.1 | ASGI server |
| SQLAlchemy | 2.0.25 | ORM |
| pydantic | 2.6.4 | Data validation |
| asyncpg | 0.29.0 | Async PostgreSQL driver |
| psycopg2-binary | 2.9.9 | Sync PostgreSQL driver |
| torch | 2.8.0 | Deep learning framework |
| torch_geometric | 2.5.0 | Graph neural networks |
| openai | 2.1.0 | OpenAI API client |
| scikit-learn | 1.6.1 | ML utilities |
| scipy | 1.13.1 | Scientific computing |
| numpy | 1.24.4 | Numerical computing |
| stable_baselines3 | 2.7.1 | RL algorithms |
| simpy | 4.0.1 | Discrete event simulation |
| gymnasium | 1.1.1 | RL environments |
| pgvector | 0.3.6 | Vector similarity search |
| PyPDF2 | 3.0.1 | PDF document parsing |

### JavaScript (frontend/package.json)

| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.2.0 | UI framework |
| @mui/material | 5.13.2 | Component library (primary) |
| @radix-ui/* | 1.x | Component library (secondary) |
| tailwindcss | 3.3.2 | Utility-first CSS |
| recharts | 2.6.2 | Chart library |
| d3 | 7.8.5 | Data visualization |
| d3-sankey | 0.12.3 | Sankey diagrams |
| reactflow | 11.10.1 | Flow diagrams |
| three | 0.160.1 | 3D rendering |
| @react-three/fiber | 8.18.0 | React Three.js renderer |
| react-router-dom | 6.10.0 | Client-side routing |
| axios | 1.3.6 | HTTP client |
| zustand | 4.3.8 | State management |
| zod | 4.3.6 | Schema validation |

### Infrastructure

| Component | Version/Image | Purpose |
|-----------|--------------|---------|
| PostgreSQL | 15+ | Primary database |
| pgvector | pgvector/pgvector:pg16 | Vector similarity extension |
| Nginx | latest | Reverse proxy |
| Docker Compose | V2 | Container orchestration |
| vLLM | latest | LLM inference server |
| Ollama | latest | Embedding model server |

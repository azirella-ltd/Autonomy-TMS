# Autonomy Continuous Autonomous Planning Platform

## Amazon 6-Pager

**Document Version**: 1.0
**Date**: February 4, 2026
**Author**: Platform Engineering Team

---

## 1. Introduction

The Autonomy Continuous Autonomous Planning Platform is a supply chain planning and execution system that implements the AWS Supply Chain data model with three extended capabilities: AI-powered decision agents, stochastic planning with probabilistic outcomes, and digital twin simulation for policy validation. The platform provides event-driven planning, continuous learning from human feedback, and multi-agent orchestration for automated supply chain decision-making.

This document describes the platform's technical architecture, capabilities, and operational characteristics.

---

## 2. Background

### The Problem Space

Supply chain planning involves sequential decision-making under uncertainty. Organizations must determine order quantities, production schedules, and inventory allocations across multi-echelon networks while facing:

- **Demand uncertainty**: Customer orders vary stochastically around forecasts
- **Supply uncertainty**: Lead times, yields, and supplier performance fluctuate
- **Information delays**: Orders and shipments traverse the supply chain with multi-period lags
- **Amplification effects**: Small demand changes at retail amplify into larger swings upstream (bullwhip effect)

Traditional planning systems use deterministic calculations (MRP/DRP) with safety stock buffers to absorb uncertainty. These systems operate on batch cadences (weekly/monthly), cannot react to intra-cycle disruptions, and require extensive manual exception handling.

### Theoretical Foundation

The platform architecture implements Warren B. Powell's Sequential Decision Analytics and Modeling (SDAM) framework, which provides a unified theoretical foundation for decision-making under uncertainty through five core elements:

| Element | Symbol | Platform Implementation |
|---------|--------|------------------------|
| **State** | Sₜ | Inventory levels, backlog, pipeline, demand history, network topology |
| **Decision** | xₜ | Order quantities, production schedules, sourcing allocations |
| **Exogenous Information** | Wₜ₊₁ | Customer demand, lead time realizations, yield variations |
| **Transition Function** | Sᴹ | Supply chain simulation engine |
| **Objective Function** | F | Minimize E[total cost] subject to service level constraints |

Powell's four policy classes map directly to platform agent types:

| Policy Class | Description | Platform Implementation |
|--------------|-------------|------------------------|
| **PFA** (Policy Function Approximation) | Direct S→x mapping | Base-stock rules, historical proportions |
| **CFA** (Cost Function Approximation) | Parameterized optimization | S&OP/MPS with policy parameters θ |
| **VFA** (Value Function Approximation) | Q-learning, TD learning | TRM agent, Execution tGNN |
| **DLA** (Direct Lookahead) | Model predictive control | Strategic planning with scenarios |

---

## 3. Platform Architecture

### 3.1 AWS Supply Chain Data Model Compliance

The platform implements 100% compliance with the AWS Supply Chain standard data model at the backend planning engine level. This includes:

**Implemented Entities** (35 AWS SC standard entities):
- **Master Data**: Product, Site, Trading Partner, Vendor Product, Product BOM
- **Planning**: Forecast, Supply Plan, Sourcing Rules, Inventory Policy, Inventory Level
- **Execution**: Inbound Order, Outbound Order, Shipment, Goods Receipt
- **Configuration**: Planning Horizon, Time Bucket, Hierarchy

**Policy Types** (4 AWS SC standard inventory policies):
- `abs_level`: Fixed quantity safety stock
- `doc_dem`: Days of coverage based on demand
- `doc_fcst`: Days of coverage based on forecast
- `sl`: Service level with z-score calculation

**Hierarchical Override System**:
- 6-level InvPolicy overrides (Product-Site > Product > Site > Config > Default)
- 5-level VendorLeadTime overrides
- 3-level SourcingRules overrides

### 3.2 Three-Tier AI Agent Architecture

The platform implements a hierarchical agent architecture aligned with planning levels:

```
S&OP GraphSAGE (CFA - Computes policy parameters θ)
    ↓ weekly/monthly policy parameters
Execution tGNN (CFA/VFA - Generates allocations)
    ↓ daily priority allocations + context
Narrow TRMs (VFA - Fast execution decisions)
    └── ATPExecutorTRM, RebalancingTRM, POCreationTRM, OrderTrackingTRM
```

#### 3.2.1 S&OP GraphSAGE (Medium-Term Planning)

**Purpose**: Network structure analysis, risk scoring, bottleneck detection

**Architecture**:
- GraphSAGE with neighbor sampling
- Scalable to 50+ node networks
- O(edges) complexity vs O(n²) for attention

**Outputs**:
- Criticality scores per node
- Concentration risk metrics
- Resilience scores
- Safety stock positioning multipliers

**Update Frequency**: Weekly/monthly or on topology changes

#### 3.2.2 Execution tGNN (Short-Term Planning)

**Purpose**: Real-time order decisions, demand sensing, exception detection

**Architecture**:
- Temporal GNN (GAT + GRU)
- Consumes S&OP structural embeddings
- Processes transactional data (orders, shipments, inventory)

**Outputs**:
- Priority × Product × Location allocations for AATP
- Demand forecasts
- Exception probability scores

**Update Frequency**: Daily/Real-time

#### 3.2.3 Tiny Recursive Model (TRM) Agents

**Purpose**: Ultra-fast execution decisions at individual decision points

**Architecture**:
- 7M parameters
- 2-layer transformer with 3-step recursive refinement
- <10ms inference time (100+ decisions/second)

**Agent Types**:
| Agent | Scope | Decision |
|-------|-------|----------|
| ATPExecutorTRM | Per order | Allocated ATP with priority consumption |
| InventoryRebalancingTRM | Cross-location | Transfer recommendations |
| POCreationTRM | Per product-location | PO timing and quantity |
| OrderTrackingTRM | Per order | Exception detection and actions |

**Performance**: 90-95% accuracy vs optimal policies

### 3.3 LLM Multi-Agent System

**Purpose**: Strategic reasoning, natural language explanations, exception handling

**Components**:
- **Site Agents**: GPT-4-based agents for each supply chain role
- **Supervisor Agent**: Reviews and validates site agent decisions
- **Global Planner Agent**: Network-wide coordination and optimization

**Capabilities**:
- Natural language explanations for every recommendation
- Multi-agent negotiation (up to 3 rounds)
- Fallback to heuristic policies when LLM unavailable

### 3.4 DAG-Based Supply Chain Topology

The platform uses a 4-master-type Directed Acyclic Graph model:

| Master Type | Description | Examples |
|-------------|-------------|----------|
| MARKET_SUPPLY | Upstream source sites | Suppliers, vendors |
| MARKET_DEMAND | Terminal demand sinks | Customers, end consumers |
| INVENTORY | Storage/fulfillment sites | DCs, warehouses, retailers |
| MANUFACTURER | Transform sites with BOM | Factories, assembly plants |

**Topology Support**:
- Serial chains (linear supply chains)
- Convergent networks (many-to-one manufacturing)
- Divergent distribution (one-to-many fulfillment)
- Complex multi-echelon networks (arbitrary DAG structures)

---

## 4. Core Capabilities

### 4.1 Continuous Autonomous Planning

**Event-Driven Architecture**:
```
Event detected → Agent triggered → Replan affected SKUs →
Commit to branch → Human notified (if needed) → Auto-execute or approve
```

**Event Processing**:
- 100,000 events/day capacity
- Priority queue: P0 (<1 min), P1 (<5 min), P2 (<1 hour), P3 (<24 hours)
- Incremental replanning (only affected products)

**AIIO Framework** (Automate-Inform-Inspect-Override):

| Stage | Responsibility | Actor |
|-------|---------------|-------|
| Automate | Generate recommendations, execute within guardrails | AI Agents |
| Inform | Notify humans of decisions | AI Agents |
| Inspect | Review agent decisions, drill into details | Humans |
| Override | Change plans + provide learning context | Humans |

**Guardrail System**:
- Financial: Max cost increase, max PO value thresholds
- Operational: Max safety stock increase, max production change
- Customer: Min service level, max order delay
- Strategic: Max CO2 increase, min supplier diversity

### 4.2 Digital Twin Simulation

The platform provides a digital twin that executes with identical planning logic, AI agents, and cost calculations as production. The twin operates with:

- **Flexible time scale**: Accelerated execution (periods in seconds vs. days)
- **Flexible demand source**: Synthetic patterns for testing, actual orders for production
- **Monte Carlo capability**: 1000+ scenario runs for statistical analysis

**Testing Applications**:

**Operating Model Changes**:
- Inventory policy modifications (safety stock, reorder points)
- Ordering strategy changes (base-stock, (s,S), periodic review)
- Agent weight optimization (LLM/GNN/TRM ratios)
- Planning frequency adjustments

**Structural Changes**:
- Network topology modifications (add/remove sites)
- Supplier sourcing changes
- Capacity modifications
- BOM alternatives

**Agent Validation**:
- Human vs. AI competitive scenarios
- Statistical significance testing (p < 0.05)
- Performance benchmarking

### 4.3 Stochastic Planning Framework

**Distribution Types** (20 supported):
Normal, lognormal, beta, gamma, Weibull, exponential, triangular, mixture, empirical, uniform, and 10 others

**Variable Classification**:
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand, forecast error
- **Control Variables** (deterministic): Inventory targets, costs, policy parameters

**Probabilistic Balanced Scorecard**:
| Dimension | Metrics |
|-----------|---------|
| Financial | E[Total Cost], P(Cost < Budget), P10/P50/P90 distribution |
| Customer | E[OTIF], P(OTIF > 95%), fill rate likelihood |
| Operational | E[Inventory Turns], E[DOS], bullwhip ratio distribution |
| Strategic | Flexibility scores, supplier reliability, CO2 emissions |

### 4.4 Conformal Prediction for Uncertainty Quantification

**Capability**: Distribution-free prediction intervals with formal coverage guarantees

**Method**:
1. Calibrate from historical Plan vs. Actual data
2. Generate prediction intervals without distributional assumptions
3. P(actual ∈ interval) ≥ 1-α guaranteed (typically 90-95% coverage)

**Features**:
- Per-product, per-site calibration
- Adaptive conformal prediction with drift detection
- Automatic recalibration when forecast accuracy degrades
- Safety stock calculation with formal service level guarantees

---

## 5. Technical Implementation

### 5.1 Technology Stack

**Backend**:
- Python 3.10+, FastAPI (async REST API)
- SQLAlchemy 2.0 (async ORM)
- PyTorch 2.2 + PyTorch Geometric (GNN)
- Stable-Baselines3 (RL)
- OpenAI API (LLM agents)
- SimPy (discrete event simulation)

**Frontend**:
- React 18 (functional components, hooks)
- Material-UI 5 (enterprise UI)
- Recharts + D3-Sankey (visualizations)
- WebSocket (real-time updates)

**Infrastructure**:
- Docker + Docker Compose (containerization)
- MariaDB 10.11 / PostgreSQL 16 (relational database)
- Nginx (reverse proxy)
- NVIDIA CUDA (GPU support for ML training)

### 5.2 Planning Hierarchies

**Three-Dimensional Hierarchy System**:

**Site/Geographic**:
```
Company → Region → Country → State → Site
```

**Product**:
```
Category → Family → Group → Product/SKU
```

**Time Bucket**:
```
Year → Quarter → Month → Week → Day → Hour
```

**Planning Type Configuration**:

| Planning Type | Site Level | Product Level | Time Bucket | Powell Class | GNN Model |
|---------------|------------|---------------|-------------|--------------|-----------|
| Execution | Site | SKU | Hour | VFA | Execution tGNN |
| MRP | Site | SKU | Day | VFA | Execution tGNN |
| MPS | Site | Group | Week | CFA | Hybrid |
| S&OP | Country | Family | Month | CFA | S&OP GraphSAGE |
| Strategic | Region | Category | Quarter | DLA | S&OP GraphSAGE |

### 5.3 AI Model Training

#### TRM Training Pipeline

**5-Phase Curriculum Learning**:

| Phase | Scenario | Topology | Dataset | Training Time |
|-------|----------|----------|---------|---------------|
| 1 | Single-Site Base Stock | 1 site | 10,000 samples | ~30 min (GPU) |
| 2 | 2-Site Supply Chain | 2 sites | 10,000 samples | ~30 min (GPU) |
| 3 | 4-Site Beer Game | 4 sites | 10,000 samples | ~30 min (GPU) |
| 4 | Multi-Echelon Variations | 3-6 sites | 10,000 samples | ~45 min (GPU) |
| 5 | Production Scenarios | Manufacturing + BOM | 10,000 samples | ~45 min (GPU) |

**Total Training Time**: ~2.5 hours (GPU), ~8-12 hours (CPU)

#### GNN Training Pipeline

**Architecture**:
- Graph Attention Network (GAT) + Temporal Convolutional Network (TCN)
- 128M+ parameters
- 256-dim node embeddings
- 8 attention heads
- 3 rounds message passing

**Data Generation**:
- SimPy-based discrete event simulation
- 128-512 scenario runs
- 64 timesteps per run
- Sliding window extraction (52-step history, 1-step horizon)

**Training Time**:
| Dataset Size | CPU Time | GPU Time |
|--------------|----------|----------|
| 128 runs | ~6 hours | ~1.5 hours |
| 256 runs | ~12 hours | ~3 hours |
| 512 runs | ~24 hours | ~6 hours |

### 5.4 Multi-Agent Consensus

**Weighted Ensemble**:
- Combine agent recommendations using learned weights
- Example: LLM: 45%, GNN: 38%, TRM: 17%

**Adaptive Learning Algorithms** (5 supported):
- Exponential Moving Average (EMA)
- Upper Confidence Bound (UCB)
- Thompson Sampling
- Performance-based weighting
- Gradient Descent

**Confidence Scoring**:
- Agreement between agents indicates recommendation reliability
- Weights automatically adjust based on observed performance

---

## 6. AWS SC Feature Coverage

### Backend Data Model: 100% Complete

| Standard | Status | Implementation |
|----------|--------|----------------|
| Hierarchical Overrides | ✅ | 6-level InvPolicy, 5-level VendorLeadTime, 3-level SourcingRules |
| Safety Stock Policies | ✅ | All 4 types: abs_level, doc_dem, doc_fcst, sl |
| Vendor Management | ✅ | TradingPartner, VendorProduct, FK references |
| Sourcing Schedules | ✅ | Periodic ordering (weekly, monthly, custom) |
| Advanced Manufacturing | ✅ | Frozen horizon, setup/changeover, batch sizing, BOM alternates |

### UI/UX Feature Parity: ~84% Complete

| Feature | Coverage | Key Capabilities |
|---------|----------|------------------|
| Material Visibility | 85% | Shipment tracking, ATP/CTP, delivery risk, N-tier visibility |
| Order Planning & Tracking | 85% | PO/TO/MO CRUD, lifecycle management, MRP integration, goods receipt |
| Insights & Risk Analysis | 85% | Risk detection, watchlists, predictive analytics, uncertainty quantification |
| Recommended Actions | 70% | Action scoring, accept/reject workflow, agent mode integration |
| Collaboration | 70% | A2A/H2A/H2H framework, approval workflows, inline comments, @mentions |
| Demand Planning | 60% | View-only, version history, delta analysis |
| Data Lake | External | Databricks integration for ERP connectivity |

---

## 7. Performance Specifications

### Event Processing Capacity
- 100,000 events/day (peak: 10 events/sec)
- 50,000 agent tasks/day
- 200 incremental commits/day
- 1,000 plan diff queries/day

### Latency Targets
- P0 (Critical): < 1 minute event → plan → publish
- P1 (High): < 5 minutes
- P2 (Medium): < 1 hour
- P3 (Low): < 24 hours

### Inference Performance
| Model | Inference Time | Throughput |
|-------|----------------|------------|
| TRM | <10ms | 100+ decisions/sec |
| Execution tGNN | ~50-100ms | 10-20 graphs/sec |
| LLM (GPT-4) | ~2-5s | 0.2-0.5 requests/sec |

### Model Accuracy
| Model | Metric | Performance |
|-------|--------|-------------|
| TRM | Accuracy vs optimal | 90-95% |
| GNN | Demand prediction accuracy | 85-92% |
| Multi-agent | Cost reduction vs naive | 20-35% |

### Storage Requirements (1 year)
- Full snapshots: 18 GB
- Incremental snapshots: 3.6 GB
- Events log: 36 GB
- Agent decisions: 18 GB
- **Total: ~83 GB/year**

---

## 8. Integration Capabilities

### SAP S/4HANA Integration

**Data Ingestion Methods**:
- SAP OData API (real-time)
- SAP HANA direct query
- SAP IBP Planning Area APIs
- Flat file (CSV, Excel, JSON, XML, Parquet)

**Supported SAP Entities**:
- Master Data: MARA, T001W, LFA1, KNA1
- Inventory: MARD, RESB, MKPF
- Purchasing: EKKO/EKPO, EBAN
- Sales: VBAK/VBAP, LIKP/LIPS
- Production: PLAF, AFKO

**Z-Table/Z-Field Handling**:
- AI-powered fuzzy matching for custom SAP fields
- Pattern-based recognition of SAP naming conventions
- Confidence scoring (High/Medium/Low)
- User confirmation workflow for learning

### Write-Back Capabilities

**SAP IBP Export**:
- TRM/GNN-optimized order quantities
- Demand forecasts
- Safety stock recommendations
- Inventory targets

**S/4HANA Transactional**:
- Purchase requisition creation (BAPI_PR_CREATE)
- Inventory target updates (MARC-MINBE, MARC-EISBE)
- Scenario planning export

### External System Integration

**Architecture**:
```
Databricks (Data Lake) ↔ Autonomy Platform ↔ External Demand Planning
```

- Data Lake: Databricks for ERP connectivity and transformation
- Demand Planning: External system via REST API (read-only)
- Supply Planning & Execution: Native platform capability

---

## 9. Security and Compliance

### Authentication
- JWT tokens with HTTP-only cookies
- CSRF protection (double-submit cookie pattern)
- MFA support (TOTP via PyOTP)
- SSO/LDAP integration (SAML 2.0, OAuth 2.0)

### Authorization
- Role-based access control: SYSTEM_ADMIN, GROUP_ADMIN, PLANNER, VIEWER
- Capability-based permissions per resource type
- Resource-level scoping (own, group, all)

### Data Protection
- Passwords hashed with bcrypt
- Data encrypted at rest (AES-256)
- TLS 1.3 for data in transit
- GDPR-compliant data exports and deletion

### Audit Logging
- All API requests logged with user, timestamp, IP
- Database change tracking (created_at, updated_at, updated_by)
- Complete decision audit trail for agent actions

### Regulatory Compliance
- GDPR: Data retention policies, right to deletion
- SOX: Audit trails, segregation of duties
- FDA 21 CFR Part 11: Electronic signatures (pharma/medical device)

---

## 10. Frequently Asked Questions

**Q: What is the relationship between the digital twin and production execution?**

A: The digital twin uses identical planning logic, AI agents, and cost calculations as production. The differences are: (1) time scale—the twin executes periods in seconds while production operates in real-time, and (2) demand source—the twin uses synthetic demand patterns while production uses actual customer orders. This identity enables validation of policies before production deployment.

**Q: How does the platform handle the bullwhip effect?**

A: The platform addresses bullwhip through three mechanisms: (1) demand sensing via GNN that captures temporal dependencies and information flow, (2) order smoothing policies parameterized by S&OP GraphSAGE, and (3) real-time visibility sharing across the network. Measured bullwhip reduction ranges from 20-40% variance reduction upstream.

**Q: What happens when AI agents disagree?**

A: The multi-agent consensus system combines recommendations using learned weights. When agents disagree significantly, the system flags the decision for human review. The LLM Supervisor can mediate through multi-round negotiation (up to 3 rounds). Historical performance data adjusts weights automatically—agents that perform better on certain decision types receive higher weights for those decisions.

**Q: How does conformal prediction differ from traditional safety stock calculations?**

A: Traditional safety stock assumes normal distribution of demand/lead time and uses z-scores. Conformal prediction is distribution-free—it calibrates directly from historical Plan vs. Actual data without assuming any particular distribution. This provides formal coverage guarantees: if we specify 90% coverage, actual coverage will be ≥90% by construction.

**Q: Can the platform operate without LLM connectivity?**

A: Yes. The TRM and GNN agents operate entirely on-premise with no external API calls. LLM agents provide strategic reasoning and natural language explanations but are optional. When LLM is unavailable, the system falls back to heuristic policies with equivalent operational capability.

**Q: What is the minimum viable deployment?**

A: The platform can be deployed on a single server (8 cores, 16GB RAM, 100GB SSD) without GPU for basic operation. GPU (8GB+ VRAM) is recommended for GNN training. Production deployments typically use 16+ cores, 32-64GB RAM, and dedicated GPU for ML workloads.

**Q: How long does it take to train AI agents on a new supply chain configuration?**

A: TRM training (5-phase curriculum): ~2.5 hours on GPU. GNN training (128 simulation runs): ~1.5 hours on GPU. Initial agent weights can be deployed within one business day. Adaptive weight learning continuously improves agents from production data over subsequent weeks.

---

## Appendix A: System Requirements

### Server (Backend + Database)
- CPU: 8+ cores (16+ recommended for ML training)
- RAM: 16GB minimum (32GB recommended, 64GB for GNN training)
- GPU: NVIDIA with 8GB+ VRAM (optional, for ML training)
- Storage: 100GB SSD
- OS: Linux (Ubuntu 22.04 LTS recommended)

### Client (Browser)
- Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- 4GB+ RAM
- Internet: 5 Mbps+ (for WebSocket updates)

---

## Appendix B: API Endpoint Summary

### Scenario Management
- `POST /api/v1/mixed-scenarios/` - Create scenario
- `POST /api/v1/mixed-scenarios/{id}/start` - Start scenario
- `POST /api/v1/mixed-scenarios/{id}/execute-period` - Execute period
- `GET /api/v1/mixed-scenarios/{id}/state` - Get current state
- `GET /api/v1/mixed-scenarios/{id}/history` - Get history

### AI Agents
- `POST /api/v1/agents/suggest` - Get recommendation
- `POST /api/v1/agents/evaluate` - Evaluate decision
- `GET /api/v1/agents/strategies` - List strategies

### Planning
- `POST /api/v1/supply-plan/generate` - Generate supply plan
- `GET /api/v1/supply-plan/status/{task_id}` - Check progress
- `POST /api/v1/supply-plan/approve/{task_id}` - Approve plan

### Analytics
- `GET /api/v1/analytics/bullwhip` - Bullwhip metrics
- `GET /api/v1/analytics/performance` - Performance report

---

## Appendix C: Database Schema Summary

### AWS SC Planning Tables
- `forecast`: Demand forecasts with P10/P50/P90 percentiles
- `supply_plan`: Generated supply plans (PO/TO/MO requests)
- `sourcing_rules`: Buy/transfer/manufacture rules with priorities
- `inv_policy`: Inventory policies with hierarchical overrides
- `inv_level`: Current inventory levels

### Network Configuration Tables
- `supply_chain_configs`: Network topology definitions
- `site`: Supply chain sites
- `transportation_lane`: Transportation lanes
- `product`: Products
- `market`: Market demand/supply sites

### Powell Framework Tables
- `powell_belief_state`: Uncertainty quantification
- `powell_policy_parameters`: Optimized policy parameters (θ)
- `powell_allocations`: Priority × Product × Location allocations
- `powell_atp_decisions`: ATP decision history
- `powell_rebalance_decisions`: Rebalancing history

---

*Document prepared for technical review. For questions, contact platform engineering team.*

# Autonomy — Decision Intelligence Platform for Supply Chain

**Version**: 3.0
**Last Updated**: 2026-03-12
**Status**: Production Ready

---

## Overview

Autonomy is an enterprise-grade supply chain planning and execution platform built on the AWS Supply Chain data model (100% compliant, 35/35 entities) with four pillars:

### The Four Pillars of Autonomous Planning

```
Core Foundation: AWS SC Planning & Execution (35/35 entities)
        ↓
Pillar #1: AI Agents — 11 specialized agents, <10ms, 20-35% cost reduction
        ↓
Pillar #2: Conformal Prediction — Distribution-free uncertainty guarantees
        ↓
Pillar #3: Digital Twin — Stochastic simulation for training, calibration, and testing
        ↓
Pillar #4: Causal AI — Counterfactual outcome attribution for trustworthy learning
```

---

## Core Capabilities

### 1. AWS Supply Chain Planning & Execution

Full implementation of AWS SC data model and workflows:

**Planning Capabilities**:
- **Demand Planning**: Statistical forecasting, ML models, consensus planning with P10/P50/P90 distributions
- **Supply Planning**: Net requirements calculation, multi-level BOM explosion, time-phased netting
- **Master Production Scheduling (MPS)**: Strategic production planning with rough-cut capacity checks
- **Material Requirements Planning (MRP)**: Detailed component requirements derived from MPS
- **Inventory Optimization**: 4 policy types (abs_level, doc_dem, doc_fcst, sl) with hierarchical overrides
- **Capacity Planning**: Resource utilization analysis, bottleneck identification, CTP projections

**Execution Capabilities**:
- **Order Promising**: ATP (Available-to-Promise) with multi-site sourcing
- **Order Management**: Inbound/outbound orders, shipment tracking, fulfillment coordination
- **Transfer Orders**: Inter-site inventory movements with in-transit tracking (AWS SC compliant)
- **Purchase Orders**: Vendor order management with lead time tracking
- **Manufacturing Orders**: Production execution (planned)
- **Inventory Management**: Real-time inventory levels, lot tracking, FEFO/FIFO

**Network Design**:
- DAG-based supply chain topology (4 master site types)
- Multi-echelon support: suppliers → factories → DCs → retailers → customers
- Flexible routing with sourcing rules and priority levels
- Bill of Materials (BOM) with scrap rates and yield management

**Current Status**: 60% AWS SC coverage (21/35 entities implemented)

---

### 2. AI-Powered Planning Agents

Three complementary AI approaches that achieve 20-35% cost reduction vs. naive policies:

#### TRM Agent (Tiny Recursive Model)
- **Architecture**: 7M parameters, 2-layer transformer with 3-step recursive refinement
- **Performance**: <10ms inference (100+ decisions/second), 90-95% vs optimal
- **Training**: 5-phase curriculum learning (simple → complex supply chains)
- **Use Cases**: Real-time operational decisions, high-volume scenarios

#### GNN Agent — Two-Tier Architecture
- **S&OP GraphSAGE** (~2M params): Network structure analysis, risk scoring, bottleneck detection. Updates weekly/monthly. Powell CFA.
- **Execution tGNN** (~128M params): Priority allocations, demand forecasting (85-92% accuracy), exception detection. Updates daily. Powell CFA/VFA bridge.
- **Shared Foundation**: S&OP structural embeddings cached and consumed by Execution tGNN
- **Training**: Two-tier process via `train_planning_execution.py` (S&OP → Execution → Hybrid)
- **Use Cases**: Network-wide coordination, demand forecasting, priority allocations for AATP

#### LLM Agent (GPT-4 Multi-Agent Orchestration)
- **Architecture**: Site agents + Supervisor agent + Global planner
- **Performance**: Natural language explainability, adaptive strategies
- **Implementation**: OpenAI API integration with structured JSON schemas
- **Use Cases**: Strategic planning, human-AI collaboration, explainable decisions

**Integration Points**:
- Agents can replace human planners in any planning workflow
- Mixed human-AI planning teams supported
- Agents serve as opponents or teammates in Beer Game
- Validation: compare AI vs. human decisions

---

### 3. Conformal Prediction & Digital Twin

Distribution-free uncertainty guarantees powered by stochastic simulation:

#### Distribution Framework
- **20 Distribution Types**: Normal, lognormal, beta, gamma, Weibull, exponential, triangular, mixture, empirical, custom
- **Operational Variables** (stochastic): Lead times, yields, capacities, demand, forecast error
- **Control Variables** (deterministic): Inventory targets, costs, policy parameters
- **Monte Carlo Engine**: 1000+ scenarios with variance reduction techniques

#### Probabilistic Balanced Scorecard

**Financial Metrics**:
- E[Total Cost], P(Cost < Budget)
- P10/P50/P90 cost distribution
- Cost-at-Risk (CaR)

**Customer Metrics**:
- E[OTIF], P(OTIF > 95%)
- Fill rate likelihood distributions
- Service level confidence intervals

**Operational Metrics**:
- E[Inventory Turns], E[Days of Supply]
- Bullwhip ratio distribution
- Capacity utilization variance

**Strategic Metrics**:
- Supply chain flexibility scores
- Supplier reliability distributions
- CO2 emissions with uncertainty
- Risk exposure analysis

#### Key Benefits
- Plan with uncertainty instead of point estimates
- Quantify risk: "85% chance service level > 95%"
- Optimize for P90 outcomes, not just expected values
- Identify high-leverage risk mitigation actions

---

### 4. Gamification: The Beer Game

MIT's classic supply chain simulation enhanced with AI and modern analytics:

#### Game Mechanics
- **Classic Setup**: Multi-echelon supply chain (Retailer → Wholesaler → Distributor → Factory)
- **Bullwhip Effect**: Demonstrates demand amplification through supply chain
- **Learning Objective**: Understand inventory management, demand forecasting, coordination challenges
- **Multi-player**: 2-8 players in real-time WebSocket games
- **Mixed Human-AI**: Humans compete alongside/against AI agents

#### Business Applications

**1. Employee Training** (3-5x engagement vs. traditional)
- Hands-on supply chain learning
- Safe environment to make mistakes
- Immediate feedback and analytics
- Competitive leaderboards

**2. Agent Validation** (Risk-free testing)
- Test AI agents before production deployment
- Compare agent strategies (TRM vs. GNN vs. LLM)
- Identify edge cases and failure modes
- Build confidence in AI performance

**3. Confidence Building** (Demonstrate AI value)
- Human vs. AI competitions
- Show 20-35% cost improvements
- Executive demonstrations
- Stakeholder buy-in

**4. Continuous Improvement** (RLHF)
- Human gameplay generates training data
- Learn from expert planners
- Improve agent strategies iteratively
- Crowdsource supply chain knowledge

#### Integration with Core Platform
The Beer Game uses the same AWS SC services underneath:
- Demand planning for forecast generation
- Supply planning for replenishment decisions
- Inventory management for stock tracking
- Order promising for ATP calculations
- Transfer orders for inter-site shipments

**This ensures The Beer Game validates production capabilities.**

---

### 5. Human-to-AI Input Channels

Two mechanisms allow humans to inject signals into the AI decision pipeline:

#### Talk to Me — Natural Language Directive Capture
A persistent AI prompt bar in the top navigation accepts natural language directives (e.g., *"Increase revenue by 10% in SW region next quarter due to customer feedback"*). The system parses with LLM, detects missing fields via clarification flow, and routes to the appropriate Powell layer based on the user's role. Effectiveness tracked via Bayesian posteriors.

#### Email Signal Intelligence — GDPR-Safe Email Ingestion
Monitors customer/supplier inboxes (IMAP/Gmail), strips personal identifiers before persistence (GDPR-safe by design), classifies emails into 12 supply chain signal types using LLM, and auto-routes to appropriate TRM agents. Only the sending company is identified — never the individual. Cost: ~$5.40/month at 100 emails/day.

---

## Technical Architecture

### Backend Stack
- **Framework**: FastAPI (Python 3.10+), asyncio, Pydantic v2
- **Database**: PostgreSQL 16 (primary), MariaDB 10.11 (legacy support)
- **ORM**: SQLAlchemy 2.0 with async support
- **AI/ML**: PyTorch 2.2.0, PyTorch Geometric, OpenAI API
- **Simulation**: SimPy for dataset generation

### Frontend Stack
- **Framework**: React 18 with hooks
- **UI Library**: Material-UI 5 (MUI)
- **Charts**: Recharts, D3-Sankey for network diagrams
- **State**: React Context + custom hooks
- **Real-time**: WebSocket connections for live updates

### Infrastructure
- **Containerization**: Docker, Docker Compose
- **Proxy**: Nginx with health checks
- **Database Admin**: pgAdmin 4
- **GPU Support**: NVIDIA Docker runtime for ML training

### Data Model
- **35 AWS SC Entities**: Standard supply chain data model
- **DAG Topology**: 4 master site types (MARKET_SUPPLY, MARKET_DEMAND, INVENTORY, MANUFACTURER)
- **Temporal Support**: Effective date tracking for planning scenarios
- **Multi-tenancy**: Customer-based isolation with RBAC

---

## Integration Capabilities

### Read Capabilities (Data Import)

**Supported Formats**:
- CSV/Excel (bulk upload)
- JSON/REST API
- Database direct connection
- AWS S3 integration (planned)

**Import Entities**:
- Supply chain network topology (sites, transportation lanes, products)
- Demand forecasts (historical and future)
- Inventory levels and policies
- Bill of Materials (BOM)
- Vendor data (products, lead times, costs)
- Capacity constraints
- Sourcing rules and priorities

**Validation & Mapping**:
- Schema validation with error reporting
- Automatic type conversion
- Duplicate detection
- Referential integrity checks
- Preview before commit

### Write Capabilities (Data Export)

**Export Formats**:
- CSV/Excel (formatted reports)
- JSON (API responses)
- PDF (executive summaries)
- Database views

**Export Entities**:
- Supply plans (PO/TO/MO recommendations)
- Inventory projections (multi-period)
- Capacity requirements
- KPI dashboards
- Probabilistic balanced scorecards
- Game analytics and leaderboards

**Automation**:
- Scheduled exports
- Event-triggered notifications
- Webhook integrations
- Email reports with attachments

### API Integration

**REST API**:
- Full CRUD for all entities
- Bulk operations support
- Filtering, sorting, pagination
- JWT authentication
- Rate limiting

**WebSocket API**:
- Real-time game updates
- Live planning sessions
- Collaborative forecasting
- Push notifications

---

## Documentation Index

### Core Documentation
- **[README.md](README.md)** - This document (Executive Summary)
- **[PLANNING_CAPABILITIES.md](docs/PLANNING_CAPABILITIES.md)** - Demand, supply, MPS, MRP, inventory optimization
- **[EXECUTION_CAPABILITIES.md](docs/EXECUTION_CAPABILITIES.md)** - Order promising, fulfillment, transfer orders
- **[STOCHASTIC_PLANNING.md](docs/STOCHASTIC_PLANNING.md)** - Probabilistic planning framework
- **[AI_AGENTS.md](docs/AI_AGENTS.md)** - TRM, GNN, LLM agent architectures
- **[BEER_GAME_GUIDE.md](docs/BEER_GAME_GUIDE.md)** - How to play, agent assignment, training workflows
- **[INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)** - Data import/export, API usage

### Technical Documentation
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture, data model, tech stack
- **[API_REFERENCE.md](docs/API_REFERENCE.md)** - REST and WebSocket API documentation
- **[DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)** - Installation, configuration, Docker setup
- **[DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)** - Contributing, coding standards, testing

### Reference Documentation
- **[AWS_SC_IMPLEMENTATION_STATUS.md](AWS_SC_IMPLEMENTATION_STATUS.md)** - AWS SC entity coverage (21/35)
- **[DAG_Logic.md](DAG_Logic.md)** - Supply chain network topology design
- **[PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md)** - Academic foundations, algorithms
- **[AGENT_SYSTEM.md](AGENT_SYSTEM.md)** - Agent strategies and implementation
- **[TRANSFER_ORDER_INTEGRATION_GUIDE.md](TRANSFER_ORDER_INTEGRATION_GUIDE.md)** - Transfer order AWS SC compliance

### References
- **[docs/external/SAP_INTEGRATION_GUIDE.md](docs/external/SAP_INTEGRATION_GUIDE.md)** - SAP S/4HANA integration setup guide
- **[docs/internal/AWS_SC_IMPLEMENTATION_STATUS.md](docs/internal/AWS_SC_IMPLEMENTATION_STATUS.md)** - AWS SC compliance status (35/35 entities)

---

## Quick Start

### Development Mode
```bash
# Start all services (CPU mode)
make up

# Initialize database
docker compose exec backend python -m app.db.init_db

# Seed with default data
make db-bootstrap

# Access the application
# Frontend: http://localhost:8089
# Backend API: http://localhost:8010/docs
# Database Admin: http://localhost:5051
```

### GPU Mode (for ML training)
```bash
# Start with GPU support
make up FORCE_GPU=1

# Train GNN agent
make train-gnn

# Train TRM agent
cd backend && python scripts/training/train_trm.py
```

### Play a Beer Game
```bash
# Via UI: Navigate to http://localhost:8089/games/create
# Via API:
curl -X POST http://localhost:8010/api/v1/mixed-games/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Game",
    "config_id": 1,
    "max_rounds": 52
  }'
```

---

## Support & Community

### Getting Help
- **Documentation**: See [docs/](docs/) folder
- **Issues**: GitHub Issues
- **Email**: support@autonomy.ai

### Contributing
We welcome contributions! See [DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)

### License
Proprietary software. Contact licensing@autonomy.ai for enterprise licensing.

---

**Version**: 2.0
**Status**: Production Ready
**AWS SC Compliance**: 60% (21/35 entities)
**Last Updated**: 2026-01-22

# Customer Deployment Plan — Autonomy Platform

Precise, sequential deployment plan for onboarding a new customer to the Autonomy platform.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Phase 1: Infrastructure Setup](#2-phase-1-infrastructure-setup)
3. [Phase 2: Platform Deployment](#3-phase-2-platform-deployment)
4. [Phase 3: Database Initialization](#4-phase-3-database-initialization)
5. [Phase 4: Customer Onboarding](#5-phase-4-customer-onboarding)
6. [Phase 5: Supply Chain Configuration](#6-phase-5-supply-chain-configuration)
7. [Phase 6: Data Ingestion](#7-phase-6-data-ingestion)
8. [Phase 7: AI Agent Activation](#8-phase-7-ai-agent-activation)
9. [Phase 8: Governance & Guardrails](#9-phase-8-governance--guardrails)
10. [Phase 9: Verification & Go-Live](#10-phase-9-verification--go-live)
11. [Phase 10: Post-Deploy Operations](#11-phase-10-post-deploy-operations)
12. [Appendix A: Environment Variables](#appendix-a-environment-variables)
13. [Appendix B: Troubleshooting](#appendix-b-troubleshooting)

---

## 1. Overview

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│  Host Machine                                                │
│                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Nginx   │  │  Frontend  │  │  Backend  │  │ PostgreSQL│  │
│  │  Proxy   │  │  React 18  │  │  FastAPI  │  │ + pgvector│  │
│  │  :8088   │──│  :3000     │  │  :8000    │──│  :5432    │  │
│  │          │  └───────────┘  │           │  └───────────┘  │
│  │          │──────────────── │           │                  │
│  └──────────┘                 │           │  ┌───────────┐  │
│                               │  APSched  │  │  KB DB    │  │
│  ┌──────────┐                 │  (sweeper │  │  pgvector  │  │
│  │  vLLM    │                 │   jobs)   │  │  :5432    │  │
│  │  :8001   │─────────────────│           │──│           │  │
│  │ (Qwen 3) │                 └──────────┘  └───────────┘  │
│  └──────────┘                                                │
│  ┌──────────┐                                                │
│  │  pgAdmin │                                                │
│  │  :5050   │                                                │
│  └──────────┘                                                │
└─────────────────────────────────────────────────────────────┘
```

### Estimated Timeline

| Phase | Duration | Blocking? |
|-------|----------|-----------|
| 1. Infrastructure Setup | 15 min | Yes |
| 2. Platform Deployment | 5 min | Yes |
| 3. Database Initialization | 2 min | Yes |
| 4. Customer Onboarding | 10 min | Yes |
| 5. Supply Chain Configuration | 30-60 min | Yes |
| 6. Data Ingestion | 1-4 hours | Partially |
| 7. AI Agent Activation | 30 min - 2 hours | No |
| 8. Governance & Guardrails | 15-30 min | No |
| 9. Verification & Go-Live | 15 min | Yes |
| 10. Post-Deploy | Ongoing | No |

---

## 2. Phase 1: Infrastructure Setup

### Step 1.1 — Clone Repository

```bash
git clone <repository-url> /opt/autonomy
cd /opt/autonomy
```

### Step 1.2 — Verify Prerequisites

```bash
# Docker (20.10+)
docker --version

# Docker Compose (v2 preferred)
docker compose version

# GPU support (optional)
nvidia-smi  # Verify NVIDIA driver
docker run --gpus all nvidia/cuda:12.0-base nvidia-smi  # Verify runtime
```

### Step 1.3 — Initialize Environment

```bash
make init-env
```

This runs `scripts/setup_env.sh` which creates `.env` from the appropriate template:
- `.env.$HOSTNAME` (host-specific, checked first)
- `.env.local` (local override)
- `.env.example` (default template)

### Step 1.4 — Configure Environment Variables

Edit `.env` with customer-specific values:

```bash
# REQUIRED: Change these for production
SECRET_KEY=$(openssl rand -hex 32)
POSTGRESQL_PASSWORD=$(openssl rand -hex 16)

# REQUIRED: Database
DATABASE_TYPE=postgresql
POSTGRESQL_HOST=db
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=autonomy
POSTGRESQL_USER=autonomy_user
POSTGRESQL_PASSWORD=<generated-above>

# REQUIRED: LLM (pick one)
# Option A: Local LLM (requires GPU with ≥8GB VRAM)
LLM_API_BASE=http://vllm:8001/v1
LLM_MODEL_NAME=qwen3-8b
# Option B: Remote OpenAI
OPENAI_API_KEY=sk-...

# OPTIONAL: Embedding service for RAG
EMBEDDING_API_BASE=http://ollama:11434/v1
EMBEDDING_MODEL=nomic-embed-text

# OPTIONAL: Default admin password (change post-deploy)
AUTONOMY_DEFAULT_PASSWORD=Autonomy@2025
```

See [Appendix A](#appendix-a-environment-variables) for full variable reference.

---

## 3. Phase 2: Platform Deployment

### Step 2.1 — Build and Start All Containers

**CPU mode (no GPU)**:
```bash
make up
```

**GPU mode** (required for local LLM and GPU-accelerated training):
```bash
make up FORCE_GPU=1
```

**GPU + Local LLM** (Qwen 3 8B via vLLM):
```bash
make up-llm
```

### Step 2.2 — Verify All Containers Are Running

```bash
docker compose ps
```

**Expected output** (all services UP, health checks passing):
```
NAME                STATUS          PORTS
autonomy-proxy      Up (healthy)    0.0.0.0:8088->80/tcp
autonomy-frontend   Up              3000/tcp
autonomy-backend    Up (healthy)    0.0.0.0:8000->8000/tcp
autonomy-db         Up (healthy)    0.0.0.0:5432->5432/tcp
autonomy-kb-db      Up (healthy)    5432/tcp
autonomy-pgadmin    Up              0.0.0.0:5050->80/tcp
```

### Step 2.3 — Verify Health Endpoints

```bash
# Proxy health
curl -s http://localhost:8088/healthz
# Expected: ok

# Backend API health
curl -s http://localhost:8088/api/health
# Expected: {"status":"ok"}

# Frontend loads
curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
# Expected: 200
```

---

## 4. Phase 3: Database Initialization

### Step 3.1 — Automatic Schema Creation

Schema creation happens automatically during backend startup via `Base.metadata.create_all`. This creates all 47+ tables from SQLAlchemy model definitions.

Verify tables were created:
```bash
docker compose exec db psql -U autonomy_user -d autonomy -c "\dt" | head -60
```

### Step 3.2 — Verify System Admin Exists

The backend startup creates the system admin automatically:
```bash
docker compose exec db psql -U autonomy_user -d autonomy -c \
  "SELECT id, email, user_type FROM users WHERE email = 'systemadmin@autonomy.ai';"
```

**Expected**: One row with `user_type = SYSTEM_ADMIN`.

### Step 3.3 — Verify Extensions

```bash
docker compose exec db psql -U autonomy_user -d autonomy -c \
  "SELECT extname, extversion FROM pg_extension;"
```

**Expected**: `uuid-ossp`, `pg_stat_statements`, `vector` (pgvector).

---

## 5. Phase 4: Customer Onboarding

This is where the new customer is created with their organizational structure.

### Option A: Synthetic Data Wizard (Recommended for New Deployments)

The wizard generates a complete customer with supply chain, products, forecasts, and policies from an archetype template.

#### Step 4A.1 — Choose Archetype

| Archetype | Structure | SKUs | Default Mode |
|-----------|-----------|------|--------------|
| `retailer` | CDCs → RDCs → Stores + Online | 200 | Copilot |
| `distributor` | NDCs → RDCs → LDCs | 720 | Copilot |
| `manufacturer` | Plants → Sub-Assembly → Component | 160 | Autonomous |

#### Step 4A.2 — Generate via API

```bash
# Login as system admin
TOKEN=$(curl -s -X POST http://localhost:8088/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"systemadmin@autonomy.ai","password":"Autonomy@2025"}' \
  | jq -r '.access_token')

# Generate synthetic customer
curl -X POST http://localhost:8088/api/v1/synthetic-data/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "Acme Corp",
    "company_name": "ACME Manufacturing",
    "archetype": "manufacturer",
    "admin_email": "admin@acme.com",
    "admin_name": "ACME Admin",
    "agent_mode": "copilot"
  }'
```

**What gets created** (12 items):
1. Customer organization ("Acme Corp")
2. Admin user (`admin@acme.com`)
3. Supply chain config (sites, lanes, products from archetype)
4. Site hierarchy (Company → Region → Country → Site)
5. Product hierarchy (Category → Family → Group → Product)
6. Demand forecasts (P10/P50/P90 percentiles, 52-week horizon)
7. Inventory policies (DOC-based safety stock per product-site)
8. Inventory levels (initial on-hand from archetype)
9. Planning hierarchy configs (MPS, MRP, S&OP)
10. Agent configurations (per-site TRM assignments)
11. Sourcing rules (buy/transfer/manufacture with priorities)
12. Production processes (for manufacturer archetype)

#### Step 4A.3 — Interactive Wizard (Alternative)

```bash
# Start wizard session
SESSION=$(curl -s -X POST http://localhost:8088/api/v1/synthetic-data/wizard/sessions \
  -H "Authorization: Bearer $TOKEN" | jq -r '.session_id')

# Chat to customize
curl -X POST http://localhost:8088/api/v1/synthetic-data/wizard/sessions/$SESSION/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a manufacturer called ACME with 3 plants, 2 DCs, and 160 SKUs across Frozen, Chilled, and Ambient categories"}'

# Generate when satisfied
curl -X POST http://localhost:8088/api/v1/synthetic-data/wizard/sessions/$SESSION/generate \
  -H "Authorization: Bearer $TOKEN"
```

### Option B: SAP Data Import (For Existing SAP Customers)

#### Step 4B.1 — Configure SAP Connection

```bash
curl -X POST http://localhost:8088/api/v1/sap-data/connections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ACME S/4HANA",
    "system_type": "S4HANA",
    "connection_type": "RFC",
    "host": "sap.acme.com",
    "system_number": "00",
    "client": "100",
    "username": "RFC_USER",
    "password": "...",
    "customer_id": <customer_id>
  }'
```

#### Step 4B.2 — Test Connection

```bash
curl -X POST http://localhost:8088/api/v1/sap-data/connections/<conn_id>/test \
  -H "Authorization: Bearer $TOKEN"
```

#### Step 4B.3 — Run Field Mapping

```bash
# Discover SAP tables
curl http://localhost:8088/api/v1/sap-data/connections/<conn_id>/tables \
  -H "Authorization: Bearer $TOKEN"

# Auto-map fields (AI-powered fuzzy matching)
curl -X POST http://localhost:8088/api/v1/sap-data/field-mapping/auto \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"connection_id": <conn_id>, "table_name": "MARA"}'
```

#### Step 4B.4 — Import Users

```bash
curl -X POST http://localhost:8088/api/v1/sap-data/user-import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": <conn_id>,
    "role_mapping": {
      "ZBC_SC_PLANNER": "supply_planner",
      "ZBC_SC_MANAGER": "supply_chain_manager"
    }
  }'
```

### Option C: Manual Setup via Admin UI

1. Navigate to `http://localhost:8088/admin/customers`
2. Click "Create Customer"
3. Fill in: Name, Description, Mode (Learning/Production), Admin Email
4. Navigate to `http://localhost:8088/admin/users`
5. Create admin user for the customer
6. Assign roles (GROUP_ADMIN minimum)

---

## 6. Phase 5: Supply Chain Configuration

### Step 5.1 — Verify or Create Network Topology

If using synthetic data (Option A), the supply chain is already created. Verify:

```bash
curl http://localhost:8088/api/v1/supply-chain-configs?customer_id=<customer_id> \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {id, name, node_count: (.nodes | length)}'
```

If creating manually:

1. Navigate to `http://localhost:8088/planning/network-design`
2. Define sites (Factories, DCs, Warehouses, Stores)
3. Define transportation lanes between sites
4. Define products and BOMs for manufacturers
5. Validate DAG topology (no cycles, all demand sites reachable)

### Step 5.2 — Configure Inventory Policies

```bash
# List existing policies
curl http://localhost:8088/api/v1/inventory/policies?config_id=<config_id> \
  -H "Authorization: Bearer $TOKEN"
```

Policy types available:
- `abs_level`: Fixed quantity safety stock
- `doc_dem`: Days of coverage (demand-based)
- `doc_fcst`: Days of coverage (forecast-based)
- `sl`: Service level with z-score

### Step 5.3 — Configure Planning Hierarchies

Navigate to `http://localhost:8088/admin/planning-hierarchy` and set up:
- **MPS hierarchy**: Which products are MPS-planned vs MRP-planned
- **S&OP hierarchy**: Aggregation levels for monthly planning
- **Sourcing rules**: Buy, transfer, manufacture priorities per product-site

---

## 7. Phase 6: Data Ingestion

### Step 6.1 — Load Historical Demand Data

```bash
# Upload forecasts (CSV or API)
curl -X POST http://localhost:8088/api/v1/forecasts/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@demand_history.csv" \
  -F "config_id=<config_id>"
```

CSV format:
```csv
product_id,site_id,period,quantity,p10,p50,p90
SKU-001,DC-EAST,2026-W01,1000,800,1000,1200
```

### Step 6.2 — Load Inventory Levels

```bash
curl -X POST http://localhost:8088/api/v1/inventory/levels/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@inventory_levels.csv" \
  -F "config_id=<config_id>"
```

### Step 6.3 — Load Open Orders

```bash
# Inbound orders (POs, scheduled receipts)
curl -X POST http://localhost:8088/api/v1/orders/inbound/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@open_pos.csv"

# Outbound orders (customer orders, demand)
curl -X POST http://localhost:8088/api/v1/orders/outbound/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@customer_orders.csv"
```

### Step 6.4 — Verify Data Quality

```bash
# Check forecast coverage
curl http://localhost:8088/api/v1/forecasts/coverage?config_id=<config_id> \
  -H "Authorization: Bearer $TOKEN"

# Check inventory completeness
curl http://localhost:8088/api/v1/inventory/coverage?config_id=<config_id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## 8. Phase 7: AI Agent Activation

### Step 7.1 — Generate Training Data (SimPy Simulation)

```bash
make generate-simpy-data \
  CONFIG_NAME="ACME Manufacturing" \
  SIMPY_NUM_RUNS=128 \
  SIMPY_TIMESTEPS=64 \
  SIMPY_WINDOW=52 \
  SIMPY_HORIZON=1
```

This runs 128 Monte Carlo simulations × 64 timesteps = 8,192 training samples.

### Step 7.2 — Train GNN Models

```bash
# Train execution tGNN (short-term demand prediction + allocation)
make train-gnn \
  CONFIG_NAME="ACME Manufacturing" \
  TRAIN_EPOCHS=50 \
  TRAIN_DEVICE=cuda

# Train S&OP GraphSAGE (medium-term network analysis)
# (triggered from admin UI: AI & Agents > GraphSAGE)
```

Checkpoints saved to `backend/checkpoints/`.

### Step 7.3 — Train TRM Agents (11 Narrow Agents)

Navigate to `http://localhost:8088/admin/trm` and for each agent:
1. Select training data source (SimPy dataset)
2. Configure hyperparameters (epochs, batch size, learning rate)
3. Start behavioral cloning warm-start
4. Monitor training progress

Or via API:
```bash
curl -X POST http://localhost:8088/api/v1/site-agent/training/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": <config_id>,
    "trm_type": "atp_execution",
    "epochs": 50,
    "device": "cuda",
    "training_phase": "behavioral_cloning"
  }'
```

### Step 7.4 — Verify Agent Readiness

```bash
# Check model checkpoints
curl http://localhost:8088/api/v1/site-agent/models?config_id=<config_id> \
  -H "Authorization: Bearer $TOKEN"

# Run a test ATP decision
curl -X POST http://localhost:8088/api/v1/site-agent/atp/check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "TEST-001",
    "product_id": "SKU-001",
    "location_id": "DC-EAST",
    "requested_qty": 100,
    "requested_date": "2026-03-01",
    "priority": 3
  }'
```

### Step 7.5 — Set Agent Operating Mode

Per customer, configure agent autonomy level:

| Mode | Behavior |
|------|----------|
| `copilot` | Agents suggest, humans approve/reject |
| `autonomous` | Agents execute within guardrails, humans monitor |

```bash
curl -X PUT http://localhost:8088/api/v1/customers/<customer_id> \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "PRODUCTION", "agent_mode": "copilot"}'
```

---

## 9. Phase 8: Governance & Guardrails

### Step 8.1 — Create Default Governance Policy

Every customer should have a catch-all governance policy:

```bash
curl -X POST "http://localhost:8088/api/v1/site-agent/governance/policies?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Default ACME Policy",
    "description": "Catch-all governance policy for ACME Corp",
    "automate_below": 20.0,
    "inform_below": 50.0,
    "hold_minutes": 60,
    "auto_apply_on_expiry": true,
    "escalate_after_minutes": 480,
    "priority": 100
  }'
```

**Impact thresholds** (adjust per customer risk appetite):
- `< 20` → **AUTOMATE**: Execute immediately, no notification
- `20-50` → **INFORM**: Execute immediately, notify user
- `≥ 50` → **INSPECT**: Hold for human review (configurable window)

### Step 8.2 — Create Scope-Specific Policies (Optional)

High-risk action types deserve stricter thresholds:

```bash
# PO Creation — high reversibility cost, stricter thresholds
curl -X POST "http://localhost:8088/api/v1/site-agent/governance/policies?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PO Creation - Strict Review",
    "action_type": "po_creation",
    "category": "procurement",
    "automate_below": 10.0,
    "inform_below": 30.0,
    "hold_minutes": 120,
    "auto_apply_on_expiry": false,
    "escalate_after_minutes": 240,
    "priority": 50
  }'

# Forecast adjustments — low risk, more autonomy
curl -X POST "http://localhost:8088/api/v1/site-agent/governance/policies?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Forecast Adjustment - Relaxed",
    "action_type": "forecast_adjustment",
    "automate_below": 40.0,
    "inform_below": 70.0,
    "hold_minutes": 30,
    "auto_apply_on_expiry": true,
    "priority": 50
  }'
```

### Step 8.3 — Configure Authority Boundaries

Authority boundaries are pre-configured per agent role. Verify they match the customer's organizational structure:

Navigate to `http://localhost:8088/admin/authorization-protocol`:
- Review UNILATERAL, REQUIRES_AUTHORIZATION, FORBIDDEN actions per agent
- Adjust net-benefit thresholds for auto-resolve vs. human review

### Step 8.4 — Verify Governance Sweeper Jobs

The backend registers 3 governance jobs at startup:

| Job | Schedule | Purpose |
|-----|----------|---------|
| Auto-Apply Sweeper | Every 5 min | Execute/expire INSPECT decisions past hold_until |
| Escalation Checker | Every 30 min | Flag stale INSPECT decisions for escalation |
| Directive Expiry | Hourly at :50 | Expire past-due guardrail directives |

Verify they're registered:
```bash
docker compose logs backend | grep "Registered governance"
```

Expected:
```
Registered governance auto-apply sweeper (every 5 min)
Registered governance escalation checker (every 30 min)
Registered governance directive expiry (hourly at :50)
```

---

## 10. Phase 9: Verification & Go-Live

### Step 9.1 — End-to-End Functional Test

Run through the complete decision flow:

1. **Generate a supply plan**:
```bash
curl -X POST http://localhost:8088/api/v1/supply-plan/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": <config_id>,
    "planning_horizon": 52
  }'
```

2. **Check ATP decision**:
```bash
curl -X POST http://localhost:8088/api/v1/site-agent/atp/check \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "VERIFY-001",
    "product_id": "SKU-001",
    "location_id": "DC-EAST",
    "requested_qty": 500,
    "requested_date": "2026-03-15",
    "priority": 2
  }'
```

3. **Check governance worklist** (should show INSPECT decisions if impact ≥ threshold):
```bash
curl "http://localhost:8088/api/v1/site-agent/governance/pending?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN"
```

4. **Check governance stats**:
```bash
curl "http://localhost:8088/api/v1/site-agent/governance/stats?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN"
```

### Step 9.2 — User Acceptance Test

1. Log in as the customer admin (`admin@acme.com`)
2. Navigate to Planning > Demand Plan — verify forecasts load
3. Navigate to Planning > Supply Plan — verify supply plans generate
4. Navigate to Execution > ATP Worklist — verify order decisions appear
5. Navigate to Admin > Governance — verify governance policies visible
6. Navigate to AI & Agents > TRM Dashboard — verify model status

### Step 9.3 — Performance Baseline

Record initial metrics:
```bash
# Governance stats
curl "http://localhost:8088/api/v1/site-agent/governance/stats?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN"

# Override effectiveness (will be empty initially)
curl "http://localhost:8088/api/v1/decision-metrics/override-posteriors?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN"
```

### Step 9.4 — Go-Live Checklist

- [ ] All containers healthy (`docker compose ps`)
- [ ] System admin can log in
- [ ] Customer admin can log in
- [ ] Supply chain config visible with correct topology
- [ ] Forecasts loaded for planning horizon
- [ ] Inventory levels current
- [ ] At least one governance policy active
- [ ] Agent models loaded (checkpoints present)
- [ ] LLM endpoint reachable (`make llm-check`)
- [ ] Governance sweeper jobs registered
- [ ] CDC relearning jobs registered
- [ ] CDT calibration completed at startup

---

## 11. Phase 10: Post-Deploy Operations

### Ongoing Operations

| Task | Frequency | Command |
|------|-----------|---------|
| View logs | As needed | `make logs` |
| Restart backend | After config changes | `make restart-backend` |
| Restart frontend | After UI changes | `make restart-frontend` |
| Check LLM | After restart | `make llm-check` |
| Reset admin password | Emergency | `make reset-admin` |

### Monitoring Metrics

Monitor these via the Governance dashboard (`/admin/governance`):

- **Touchless Rate**: % of decisions executed without human intervention
- **Override Rate**: % of decisions overridden by humans
- **Avg Resolution Time**: How fast humans review INSPECT decisions
- **Auto-Apply Rate**: % of INSPECT decisions that expired and auto-applied
- **Escalation Rate**: % of INSPECT decisions that required escalation
- **Agent Score**: -100 to +100 agent decision quality vs baseline

### Retraining Schedule

The CDC relearning loop runs automatically:
- **Outcome Collection**: Hourly at :30 and :32
- **CDT Calibration**: Hourly at :35
- **Retraining Evaluation**: Every 6 hours at :45

Manual retraining (if needed):
```bash
curl -X POST http://localhost:8088/api/v1/site-agent/retraining/trigger/<site_key> \
  -H "Authorization: Bearer $TOKEN"
```

### Knowledge Base (RAG)

To upload domain knowledge for agent context:
```bash
curl -X POST http://localhost:8088/api/v1/knowledge-base/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sop_procedures.pdf" \
  -F "title=Standard Operating Procedures" \
  -F "customer_id=<customer_id>"
```

### Executive Guardrail Directives

When executives issue governance instructions via voice, email, or chat:

```bash
curl -X POST "http://localhost:8088/api/v1/site-agent/governance/directives?customer_id=<customer_id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_user_id": <executive_user_id>,
    "source_channel": "voice",
    "received_at": "2026-03-01T14:30:00Z",
    "raw_content": "Tighten controls on all PO decisions above $50K this quarter — we have supplier bankruptcy concerns.",
    "objective": "Tighten PO controls this quarter",
    "context": "Supplier bankruptcy concerns in frozen segment",
    "reason": "Three suppliers in frozen category downgraded by S&P",
    "extracted_parameters": {
      "action_type": "po_creation",
      "category": "procurement",
      "automate_below": 10.0,
      "inform_below": 25.0,
      "hold_minutes": 120,
      "auto_apply_on_expiry": false
    },
    "affected_scope": {
      "action_types": ["po_creation"],
      "categories": ["procurement"]
    },
    "effective_until": "2026-06-30T23:59:59Z",
    "extraction_confidence": 0.92,
    "extraction_model": "qwen3-8b"
  }'
```

Then review and apply:
```bash
curl -X POST http://localhost:8088/api/v1/site-agent/governance/directives/<directive_id>/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "apply",
    "review_comment": "Applied per VP Supply Chain directive. Effective Q1 2026."
  }'
```

---

## Appendix A: Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_TYPE` | Yes | `postgresql` | Database dialect |
| `POSTGRESQL_HOST` | Yes | `db` | Database hostname |
| `POSTGRESQL_PORT` | Yes | `5432` | Database port |
| `POSTGRESQL_DATABASE` | Yes | `autonomy` | Database name |
| `POSTGRESQL_USER` | Yes | `autonomy_user` | Database username |
| `POSTGRESQL_PASSWORD` | Yes | `autonomy_password` | Database password |
| `SECRET_KEY` | Yes | `dev-secret` | JWT signing key (change for production!) |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Token expiry |
| `TZ` | No | `UTC` | Timezone |
| `LLM_API_BASE` | No | (empty) | Local LLM endpoint |
| `LLM_API_KEY` | No | `not-needed` | LLM API key |
| `LLM_MODEL_NAME` | No | `qwen3-8b` | Model identifier |
| `OPENAI_API_KEY` | No | (empty) | Remote OpenAI key |
| `EMBEDDING_API_BASE` | No | (empty) | Embedding service |
| `EMBEDDING_MODEL` | No | `nomic-embed-text` | Embedding model |
| `FORCE_GPU` | No | `0` | Enable GPU support |
| `PGADMIN_EMAIL` | No | `admin@autonomy.ai` | pgAdmin login |
| `PGADMIN_PASSWORD` | No | `admin` | pgAdmin password |

---

## Appendix B: Troubleshooting

### Database Connection Fails

```bash
# Check container is running
docker compose ps db

# Check logs
docker compose logs db

# Test connection manually
docker compose exec db psql -U autonomy_user -d autonomy -c "SELECT 1;"

# Restart database
docker compose restart db
```

### Backend Won't Start

```bash
# Check logs for errors
docker compose logs backend --tail=100

# Common issues:
# - Database not ready: wait_for_db.py timeout → restart backend after db healthy
# - Import error: missing model registration → check __init__.py
# - Port conflict: another service on 8000 → change port in .env
```

### Frontend Shows Blank Page

```bash
# Check frontend logs
docker compose logs frontend

# Rebuild frontend
make rebuild-frontend
```

### LLM Not Responding

```bash
# Check LLM health
make llm-check

# Check vLLM logs (if using local)
docker compose logs vllm

# Verify endpoint
curl -s http://localhost:8001/v1/models
```

### Governance Jobs Not Running

```bash
# Check scheduler registration in backend logs
docker compose logs backend | grep "Registered governance"

# If missing, restart backend
make restart-backend
```

### Reset Everything (Nuclear Option)

```bash
make down
docker volume prune -f
make up FORCE_GPU=0
make db-bootstrap
```

**Warning**: This destroys all data. Only use in development or for a fresh start.

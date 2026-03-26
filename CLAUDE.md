# CLAUDE.md

Project rules for Claude Code. Detailed architecture and reference material in [docs/CLAUDE_REFERENCE.md](docs/CLAUDE_REFERENCE.md).

## CRITICAL: AWS Supply Chain Data Model Compliance

All data MUST use the AWS Supply Chain Data Model. Extensions allowed, core tables/fields required.

When implementing any entity:
1. Reference the AWS SC data model in [backend/app/models/sc_entities.py](backend/app/models/sc_entities.py)
2. Use AWS SC field names and types as the base
3. Add extensions only when necessary, documented as "Extension: " in docstrings

## CRITICAL: Documentation Must Be Updated With Code Changes

When code changes affect architecture, APIs, data models, or features, update relevant `.md` files in the same session.

## CRITICAL: SOC II Compliance

**Database Security**: Tenant isolation via RLS on all tenant-scoped tables. `pgaudit` for DDL/ROLE/WRITE. SSL/TLS enforced. Column-level encryption for high-sensitivity fields.

**Model & Training Data Security**: Tenant-scoped checkpoints (`/{tenant_id}/{config_id}/`). No cross-tenant training. Right to deletion for all tenant data.

**Access Control**: Least privilege PostgreSQL roles. `SET LOCAL` for tenant context in connection pooling.

**Change Management**: Schema changes via Alembic only. No direct production SQL.

## CRITICAL: No Fallbacks, No Hardcoded Values

- Column names must match the actual DB schema — check model definitions first
- No silent fallbacks — missing data shows nothing or raises error
- No hardcoded entity references — IDs, names come from tenant data
- No hardcoded demo data — all data from DB or calculations on DB data
- Economic parameters explicitly set per tenant — errors for missing data

## Terminology Convention

| Old Term | New Term | Context |
|----------|----------|---------|
| Game | Scenario | Simulation |
| Player/Participant | ScenarioUser (code) / User (UI) | Code/UI |
| Round | Period | Time period |
| Group / group_id | Tenant / tenant_id | Organization boundary |
| node | site | AWS SC data model |
| item | product | AWS SC data model |
| lane | transportation_lane | AWS SC data model |
| SafetyStockTRM | InventoryBufferTRM | TRM agent layer |
| PENDING/ACCEPTED/AUTO_EXECUTED/EXPIRED | ACTIONED | AIIO: agent executed |
| REJECTED | OVERRIDDEN | AIIO: user rejected with reasoning |
| powell_role | decision_level | User model field |

> **AIIO Model**: Agent always acts → ACTIONED. Decision Stream surfaces → INFORMED. User reviews → INSPECTED. User overrides → OVERRIDDEN. No approval workflow.

> **customer_id**: ONLY for AWS SC trading partners. Use `tenant_id` for organization boundary. Mixing these is a bug.

### Customer Tenant Model

Every customer gets two tenants:
- **Operational** (`TenantMode.PRODUCTION`): Real SC data from ERP extraction
- **Learning** (`TenantMode.LEARNING`): Default TBG config, training/simulation

---

## Tech Stack

**Backend**: FastAPI (Python 3.10+), SQLAlchemy 2.0, PyTorch 2.2.0, PyTorch Geometric
**Frontend**: React 18, Material-UI 5, Recharts, D3-Sankey
**Database**: PostgreSQL 15+
**Infrastructure**: Docker, Docker Compose, Nginx proxy
**AI/ML**: PyTorch (TRM/GNN), OpenAI-compatible API (LLM agents)

---

## Development Commands

```bash
# Start
make up                    # CPU mode
make up FORCE_GPU=1        # GPU mode
make up-dev                # Dev with hot-reload

# Services
make down                  # Stop (keeps volumes)
make logs                  # View logs
make restart-backend       # Restart backend
make rebuild-backend       # Rebuild backend
make rebuild-frontend      # Rebuild frontend

# Database
make db-bootstrap          # Seed defaults
make db-reset              # Reset games + training data
make rebuild-db            # Drop and recreate
make reseed-db             # Re-seed after rebuild
make reset-admin           # Reset password to Autonomy@2026

# Training
make generate-simpy-data   # Generate training dataset
make train-gnn             # Train temporal GNN
make train-default-gpu TRAIN_EPOCHS=50 TRAIN_DEVICE=cuda

# Proxy
make proxy-restart         # Restart proxy
make proxy-logs            # View proxy logs

# LLM
make llm-check             # Check LLM connectivity
```

**LLM env vars**: `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL_NAME` (default: qwen3-8b)

---

## Architecture (Brief)

> Full details: [docs/CLAUDE_REFERENCE.md](docs/CLAUDE_REFERENCE.md)

**Four Pillars**: AI Agents (TRM/GNN/LLM), Conformal Prediction, Digital Twin, Causal AI

**Three-Tier AI**:
- S&OP GraphSAGE → policy parameters θ (weekly)
- Execution tGNN → priority allocations (daily)
- 11 Narrow TRMs → execution decisions (<10ms): ATP, Rebalancing, PO, OrderTracking, MO, TO, Quality, Maintenance, Subcontracting, ForecastAdjustment, InventoryBuffer

**Key Backend Paths**:
- Planning: `services/aws_sc_planning/` (planner, demand, inventory targets, net requirements)
- Powell agents: `services/powell/` (11 TRM services, heuristic library, scenario engine, RL trainer)
- Skills: `services/skills/` (Claude Skills exception handler, feature-flagged OFF)
- Models: `models/` (sc_entities, aws_sc_planning, supply_chain_config, user, tenant, rbac)
- API: `api/endpoints/` (mps, supply_plan, pegging, provisioning, auth, websocket)

**Key Frontend Paths**:
- Navigation: `components/TwoTierNav.jsx`, `CategoryBar.jsx`, `PageBar.jsx`
- Planning: `pages/planning/` (43+ pages)
- Admin: `pages/admin/` (25+ pages)
- Services: `services/api.js` (Axios, baseURL=/api, withCredentials)

**DAG Model**: 4 master types — Market Supply, Market Demand, Inventory, Manufacturer. Sites connected by transportation lanes.

**AATP Consumption**: Priority P order consumes: own tier first, then bottom-up from lowest (5→4→3→...), stops at own tier.

---

## Key Implementation Details

- **Auth**: JWT + HTTP-only cookies, CSRF double-submit, capability-based permissions
- **Routing**: Nginx proxy — `/api/*` → backend:8000, `/*` → frontend:3000
- **Backend entry**: `backend/main.py` (~62K lines). SC config routes registered in main.py, NOT endpoints file.
- **Migrations**: `backend/migrations/versions/` (NOT `backend/alembic/versions/`)
- **Sessions**: `SessionLocal` is async; use `sync_session_factory` for sync access
- **Docker Compose**: Base `docker-compose.yml` + overlays (dev, gpu, prod, apps, db). Layer with `-f`.
- **Env setup**: `make init-env` to create `.env` from template

---

## Accessing Services

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8088 |
| Backend API | http://localhost:8088/api |
| API Docs | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 (admin@autonomy.com / admin) |
| Remote HTTP | http://172.29.20.187:8088 |
| Remote HTTPS | https://172.29.20.187:8443 |

**Default Login**: systemadmin@autonomy.com / Autonomy@2026

**User Role Hierarchy**:
- **System Admin** (systemadmin@autonomy.com): No tenant. Manages tenants and tenant admins ONLY. No Decision Stream access.
- **Tenant Admin** (admin@distdemo.com, SAP_admin@autonomy.com): Owns provisioning, config, user management for their tenant.
- systemadmin NEVER has a `tenant_id` or `default_config_id`.

---

## Provisioning (16 steps)

warm_start → sop_graphsage → cfa_optimization → lgbm_forecast → demand_tgnn → supply_tgnn → inventory_tgnn → trm_training → rl_training → supply_plan → rccp_validation → decision_seed → site_tgnn → conformal → scenario_bootstrap → briefing

- **FULL scope**: All 16 steps (structural changes)
- **PARAMETER_ONLY scope**: 4 steps — cfa_optimization, decision_seed, conformal, briefing (policy changes)
- Only tenant admin can provision (never systemadmin)

---

## Notes

- GPU: `FORCE_GPU=1`, requires NVIDIA Docker, falls back to CPU
- Makefile auto-detects Compose V2 vs V1
- `.env` changes need `docker compose up -d --force-recreate backend`
- Seeding (`make db-bootstrap`): Default TBG configs, users, tenants, showcase scenarios

# CLAUDE.md — Autonomy TMS

Project rules for Claude Code. Detailed architecture and reference material in [docs/CLAUDE_REFERENCE.md](docs/CLAUDE_REFERENCE.md).

## CRITICAL: TMS is a Sibling Product, Not a Fork

> **Architecture Pivot (2026-04-10)**: Autonomy SCP and Autonomy TMS are **two separate products**, not parent and fork. They share patterns and integrate via MCP, but have **independent tech stacks from the database up**. The current state of this repo (mixed SCP code from a fork) is being unwound.

**Target architecture:**

```
github.com/azirella-ltd/
├── Autonomy-Core/             ← Shared monorepo: packages/ui-core (frontend),
│                                  packages/data-model (Python — AWS SC DM, AIIO governance,
│                                  tenant/RBAC), packages/powell-core (Python — TRM base,
│                                  hive signals, conformal framework). Published to
│                                  GitHub Packages as @azirella-ltd/autonomy-frontend etc.
├── Autonomy-SCP/              ← SCP product (own DB, own backend, own frontend)
└── Autonomy-TMS/              ← TMS product (own DB, own backend, own frontend)
```

**What is shared, and how:**

| Layer | Sharing mechanism |
|-------|-------------------|
| **Frontend components** (Decision Stream, navigation, common UI) | `@azirella-ltd/autonomy-frontend` npm package (published to GitHub Packages from `azirella-ltd/Autonomy-Core` monorepo), consumed by both apps |
| **Decision types** (TMS agent types, SCP agent types) | Plugin registry in `@azirella-ltd/autonomy-frontend` — each app registers its own types at boot |
| **Backend patterns** (Powell framework, AIIO model, governance pipeline) | Concept-shared today, will be extracted to `@azirella-ltd/data-model` and `@azirella-ltd/powell-core` Python packages from the same monorepo |
| **Cross-app data exchange** | MCP (Model Context Protocol) — each app exposes domain tools that the other (or an executive console) can call |
| **DB schemas** | **Independent.** TMS has its own `tms-db` PostgreSQL container. No shared tables. |
| **Migrations** | Independent. TMS has its own alembic chain, never references SCP migrations. |
| **Models / SQLAlchemy Base** | Independent. TMS has its own `Base = declarative_base()`. No `Shipment` collisions. |

**What this means in practice:**

- Do NOT copy code from `Autonomy-SCP` into this repo as "shared core"
- Do NOT add `git remote upstream` references to the SCP repo
- Do NOT share SQLAlchemy `Base`, models, or DB tables with SCP
- DO use the `@azirella-ltd/autonomy-frontend` package for shared frontend components
- DO use MCP for any TMS↔SCP integration (e.g., TMS asking SCP for ATP constraints when sizing carrier capacity)
- DO consider: a separate "executive console" app that aggregates Decision Streams from both via MCP

## Prerequisite: GitHub PAT for `@azirella-ltd/autonomy-frontend`

The frontend Docker image installs `@azirella-ltd/autonomy-frontend` from GitHub Packages, which requires a personal access token. Setup:

1. Create a **classic** PAT (not fine-grained — fine-grained PATs don't support `packages` permissions as of 2026) at https://github.com/settings/tokens with the **`read:packages`** scope on the `azirella-ltd` org
2. Save it to `~/.config/autonomy/gh_token_packages` with `chmod 600` (no trailing newline)
3. `make rebuild-frontend` will pick it up automatically via the BuildKit secret mount

Verify with `wc -c ~/.config/autonomy/gh_token_packages` — should be 40 (classic PATs are 40 chars). Override the path with `NPM_TOKEN_FILE=...` if needed.

The token never lands in any image layer — it's mounted as a tmpfs secret only during the `npm install` step in `frontend/Dockerfile`.

**Current state vs target:**

The repo currently contains a lot of SCP code from the original fork. See [docs/internal/plans/TMS_INDEPENDENCE_PLAN.md](docs/internal/plans/TMS_INDEPENDENCE_PLAN.md) for the 5-phase migration to the target architecture.
- **Demo Data**: Transportation network generators, freight history generators
- **Frontend Pages**: Transportation-specific views replacing SC planning pages

## CRITICAL: Autonomy-Core Consumer Adoption Log

**When ANY change is made to `Autonomy-Core` (packages/autonomy-frontend, packages/data-model, or docs), the author MUST update `Autonomy-Core/CONSUMER_ADOPTION_LOG.md`** so that SCP and TMS can discover and adopt the change.

This applies to:
- New or changed exports in `@azirella-ltd/autonomy-frontend` (components, hooks, registries, types)
- New or changed entities in `azirella-data-model` (models, enums, relationships)
- New architecture decisions in `docs/ARCHITECTURE_DECISIONS.md`
- Any change that affects the contract between Core and consuming apps

**The log is the discovery mechanism.** Without it, a change to Core sits unpicked until someone happens to `git pull` and notices. Both products check `CONSUMER_ADOPTION_LOG.md` as part of their sync workflow (see [Core Sync Workflow](docs/internal/plans/AUTONOMY_DATA_MODEL_PLAN.md)).

## CRITICAL: Data Model — Transportation Entities

The TMS data model extends the AWS SC foundation where applicable but introduces transportation-specific entities. The DAG network model is shared but nodes and edges have different semantics.

### SC → TMS Entity Mapping

| SC Planning Entity | TMS Equivalent | Notes |
|---|---|---|
| Product | Commodity / Freight Class | What's being shipped, not manufactured |
| Site (MANUFACTURER) | Origin / Shipper | Loading point |
| Site (INVENTORY) | Terminal / Cross-Dock / Yard | Intermediate handling |
| Site (MARKET_DEMAND) | Destination / Consignee | Delivery point |
| Site (MARKET_SUPPLY) | Carrier / Broker | Capacity provider |
| Transportation Lane | Lane | Shared concept — origin-destination pair with mode |
| Purchase Order | Shipment / Load | Unit of freight movement |
| Manufacturing Order | Consolidation / Deconsolidation | Combining/splitting loads |
| Transfer Order | Drayage / Intermodal Transfer | Movement between modes/terminals |
| BOM | Load Plan / Packing Spec | How freight fills equipment |
| Demand Plan | Shipping Demand Forecast | Expected freight volumes by lane |
| Supply Plan | Capacity Plan | Carrier capacity by lane/mode |
| MPS | Transportation Plan | Which loads move when, on what |
| Inventory Level | Yard/Dock Inventory | Trailers, containers at facility |
| ATP | Available Capacity to Promise | Carrier/lane capacity commitment |

### Transportation Modes
- **Road**: FTL (Full Truckload), LTL (Less-than-Truckload), Parcel
- **Ocean**: FCL (Full Container), LCL (Less-than-Container), Bulk
- **Air**: Standard, Express, Charter
- **Rail**: Carload, Intermodal, Unit Train
- **Intermodal**: Combinations (truck-rail, truck-ocean, etc.)

### Key TMS Entities (to be implemented)
- **Shipment**: Unit of freight from origin to destination
- **Load**: Physical grouping of shipments on equipment
- **Carrier**: Transportation provider with rates, lanes, capacity
- **FreightRate**: Rate per lane/mode/carrier with validity period
- **Equipment**: Trailer, container, railcar types and availability
- **Appointment**: Dock door scheduling (pickup/delivery windows)
- **BOL**: Bill of Lading — legal shipping document
- **POD**: Proof of Delivery — confirmation record
- **Exception**: Shipment exception (delay, damage, refused, rolled)

## CRITICAL: Documentation Must Be Updated With Code Changes

When code changes affect architecture, APIs, data models, or features, update relevant `.md` files in the same session.

## CRITICAL: SOC II Compliance

**Database Security**: Tenant isolation via RLS on all tenant-scoped tables. `pgaudit` for DDL/ROLE/WRITE. SSL/TLS enforced. Column-level encryption for high-sensitivity fields.

**Model & Training Data Security**: Tenant-scoped checkpoints (`/{tenant_id}/{config_id}/`). No cross-tenant training. Right to deletion for all tenant data.

**Access Control**: Least privilege PostgreSQL roles. `SET LOCAL` for tenant context in connection pooling.

**Change Management**: Schema changes via Alembic only. No direct production SQL.

## CRITICAL: No Fallbacks, No Hardcoded Values

**Fallbacks are dangerous.** A fabricated metric value (e.g., `|| 94.2`) hides missing data and creates false confidence in system state. This is a safety issue — transportation decisions based on phantom numbers can cause real operational harm.

- **No fallback values for metrics, KPIs, or business data.** If a metric cannot be calculated or found, surface the absence clearly (show "No data", an alert, or raise an error). Never substitute a hardcoded number.
- **No `|| <number>` patterns for business data.** Only `|| 0` is acceptable for counters where zero is the truthful default. Never for rates, scores, costs, or percentages.
- Column names must match the actual DB schema — check model definitions first
- No hardcoded entity references — IDs, names come from tenant data
- No hardcoded demo data — all data from DB or calculations on DB data
- Economic parameters explicitly set per tenant — errors for missing data
- **Frontend rule:** When API data is unavailable, show an `<Alert>` explaining what's missing and how to fix it (e.g., "Run provisioning" or "Check metric configuration"). Never render a chart or card with invented numbers.

## Terminology Convention

| SC Term | TMS Term | Context |
|---------|----------|---------|
| Product | Commodity / Freight Class | What moves |
| Site | Location / Facility | Where it moves |
| node | location | Network topology |
| item | commodity | Freight classification |
| lane | lane | Shared — origin-destination pair |
| Purchase Order | Shipment | Freight movement unit |
| Manufacturing Order | Load Build | Load consolidation |
| Transfer Order | Intermodal Transfer | Mode change |
| Demand Plan | Shipping Forecast | Volume prediction |
| Supply Plan | Capacity Plan | Carrier availability |
| MPS | Transportation Plan | Execution schedule |
| ATP | Available Capacity to Promise | Lane capacity |
| BOM | Load Plan | Equipment utilization spec |
| Safety Stock | Buffer Capacity | Reserve carrier capacity |
| Inventory Buffer | Yard Buffer | Equipment/trailer buffer at facility |
| Game | Scenario | Simulation |
| Group / group_id | Tenant / tenant_id | Organization boundary |
| PENDING/ACCEPTED/AUTO_EXECUTED/EXPIRED | ACTIONED | AIIO: agent executed |
| REJECTED | OVERRIDDEN | AIIO: user rejected with reasoning |

> **AIIO Model**: Agent always acts → ACTIONED. Decision Stream surfaces → INFORMED. User reviews → INSPECTED. User overrides → OVERRIDDEN. No approval workflow.

> **customer_id**: ONLY for trading partners (carriers, brokers, consignees). Use `tenant_id` for organization boundary. Mixing these is a bug.

### Customer Tenant Model

Every customer gets two tenants:
- **Operational** (`TenantMode.PRODUCTION`): Real transportation data from TMS/ERP extraction
- **Learning** (`TenantMode.LEARNING`): Demo config, training/simulation

---

## Tech Stack

**Backend**: FastAPI (Python 3.10+), SQLAlchemy 2.0, PyTorch 2.2.0, PyTorch Geometric
**Frontend**: React 18, Material-UI 5, Recharts, D3-Sankey, Mapbox/Leaflet (geo)
**Database**: PostgreSQL 15+
**Infrastructure**: Docker, Docker Compose, Nginx proxy
**AI/ML**: PyTorch (TRM/GNN), OpenAI-compatible API (LLM agents)
**External Data**: project44 API (visibility), weather APIs, port/terminal APIs

---

## Agent Mapping: SC Planning → TMS

The Powell framework and agent architecture are shared. The 11 TRM agent slots map to transportation equivalents:

| SC TRM Agent | TMS TRM Agent | Phase | Function |
|---|---|---|---|
| ATPExecutorTRM | **CapacityPromiseTRM** | SENSE | Available capacity to promise on lane/carrier |
| OrderTrackingTRM | **ShipmentTrackingTRM** | SENSE | In-transit visibility, ETA prediction, exceptions |
| ForecastAdjustmentTRM | **DemandSensingTRM** | SENSE | Shipping volume forecast adjustments from signals |
| InventoryBufferTRM | **CapacityBufferTRM** | ASSESS | Reserve carrier capacity, surge planning |
| QualityDispositionTRM | **ExceptionManagementTRM** | ASSESS | Delay, damage, refusal, rolled container resolution |
| POCreationTRM | **FreightProcurementTRM** | ACQUIRE | Carrier waterfall tendering, rate optimization |
| SubcontractingTRM | **BrokerRoutingTRM** | ACQUIRE | Broker vs. asset carrier decision, overflow routing |
| MaintenanceSchedulingTRM | **DockSchedulingTRM** | PROTECT | Appointment scheduling, dock door optimization |
| MOExecutionTRM | **LoadBuildTRM** | BUILD | Load consolidation, optimization, sequencing |
| TOExecutionTRM | **IntermodalTransferTRM** | BUILD | Cross-mode transfers, drayage coordination |
| InventoryRebalancingTRM | **EquipmentRepositionTRM** | REFLECT | Empty container/trailer repositioning |

**Implementation Status**: Capability declarations, hive signals (50+ TMS-specific signal types), site capability mapping (6 facility types), and heuristic library (all 11 TRMs with deterministic fallback rules) are complete. Files:
- `services/powell/tms_agent_capabilities.py` — 11 TRM declarations with signal reads/emits
- `services/powell/tms_hive_signals.py` — 50+ TMS signal types (carrier, tracking, dock, load, equipment, intermodal, network)
- `services/powell/tms_site_capabilities.py` — facility type → active TRM mapping (shipper, terminal, cross_dock, consignee, carrier_yard, port)
- `services/powell/tms_heuristic_library/` — state dataclasses (11) + dispatch with industry-standard rules

### TMS-Specific GNN Layers
- **S&OP GraphSAGE**: Network-wide lane optimization, carrier portfolio balance, mode mix
- **Execution tGNN**: Daily load assignments, carrier allocations, priority routing
- **Site tGNN**: Intra-facility cross-TRM coordination (dock, yard, staging)

### TMS-Specific Agent Scenarios
- **Freight Tender Scenario**: Carrier bidding simulation (shipper vs. carrier agents)
- **Network Disruption Scenario**: Port strike, weather event, capacity crunch response
- **Mode Selection Scenario**: Intermodal vs. direct routing optimization

---

## Architecture (Brief)

> Full details: [docs/CLAUDE_REFERENCE.md](docs/CLAUDE_REFERENCE.md)

**Four Pillars**: AI Agents (TRM/GNN/LLM), Conformal Prediction, Digital Twin, Causal AI

**Five-Layer Agent Coordination** (shared with SC Planning):
- Layer 4 — S&OP GraphSAGE → carrier portfolio, lane strategy, mode mix (weekly)
- Layer 2 — Network tGNN → inter-facility directives, priority allocations (daily)
- Layer 1.5 — Site tGNN → intra-facility cross-TRM coordination (hourly, always on)
- Layer 1 — 11 TRMs → execution decisions (<10ms): CapacityPromise, EquipmentReposition, FreightProcurement, ShipmentTracking, LoadBuild, IntermodalTransfer, ExceptionMgmt, DockScheduling, BrokerRouting, DemandSensing, CapacityBuffer
- AAP (Layer 3) — cross-authority agent negotiation (seconds-minutes)
- Escalation Arbiter — persistent drift detection routes up

**Key Backend Paths** (evolving — some still carry SC naming):
- Planning: `services/aws_sc_planning/` → will become `services/transportation_planning/`
- Powell agents: `services/powell/` (11 TRM services, heuristic library, scenario engine, RL trainer)
- Models: `models/` (transportation entities, network config, user, tenant, rbac)
- API: `api/endpoints/` (loads, shipments, carriers, rates, appointments, provisioning, auth, websocket)
- Integrations: `integrations/project44/` (OAuth connector, tracking service, webhook handler, data mapper, config service)
- API — p44: `api/endpoints/p44_integration.py` (webhook receiver, config, tracking ops)

**Key Frontend Paths**:
- Navigation: `components/TwoTierNav.jsx`, `CategoryBar.jsx`, `PageBar.jsx`
- Planning: `pages/planning/` → TMS views (load board, shipment tracker, lane analytics, dock schedule)
- Admin: `pages/admin/` (carrier management, rate management, network config, governance)
- Services: `services/api.js` (Axios, baseURL=/api, withCredentials)

**DAG Model**: 4 master types — Carrier (capacity providers), Shipper (origins), Terminal (intermediate), Consignee (destinations). Facilities connected by lanes.

---

## Key Implementation Details

- **Auth**: JWT + HTTP-only cookies, CSRF double-submit, capability-based permissions
- **Routing**: Nginx proxy (host port `8089`) — `/api/*` → backend:8000, `/*` → frontend:3000 (container-internal ports unchanged; host ports shifted from SCP to avoid conflicts)
- **Backend entry**: `backend/main.py`
- **Migrations**: `backend/migrations/versions/` (NOT `backend/alembic/versions/`)
- **Sessions**: `SessionLocal` is async; use `sync_session_factory` for sync access
- **Docker Compose**: Base `docker-compose.yml` + overlays (dev, gpu, prod, apps, db). Layer with `-f`.
- **Env setup**: `make init-env` to create `.env` from template

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
make db-reset              # Reset scenarios + training data
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

## Accessing Services

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8089 |
| Backend API | http://localhost:8089/api |
| API Docs | http://localhost:8010/docs |
| pgAdmin | http://localhost:5051 (admin@autonomy.com / admin) |
| MCP server | http://localhost:8011 |

> **Port allocation:** TMS host ports are deliberately offset from SCP so both can run on the same machine. SCP uses 8088 / 3000 / 8000 / 5050 / 8001 / 8443; TMS uses 8089 / 3001 / 8010 / 5051 / 8011 / 8444. Container-internal ports are unchanged on both sides.
>
> All host ports are env-driven (`PROXY_HOST_PORT`, `BACKEND_HOST_PORT`, `MCP_HOST_PORT`, ...). To override at deploy time, copy `deployments/.env.example` to `.env` (Compose auto-loads). See [Autonomy-Core/docs/DEPLOYMENT_PORTS.md](../Autonomy-Core/docs/DEPLOYMENT_PORTS.md) for the full convention.

**Default Login**: systemadmin@autonomy.com / Autonomy@2026

---

## Provisioning (TMS — evolving)

The 17-step provisioning pipeline adapts for transportation:

warm_start → sop_graphsage → cfa_optimization → lgbm_forecast → demand_tgnn → supply_tgnn → inventory_tgnn → trm_training → rl_training → backtest_evaluation → transportation_plan → capacity_validation → decision_seed → site_tgnn → conformal → scenario_bootstrap → briefing

Key changes from SC Planning:
- `supply_plan` → `transportation_plan` (load assignments, carrier allocations)
- `rccp_validation` → `capacity_validation` (carrier capacity vs. demand)
- Forecast targets shipping volumes, not product demand
- TRM training data from freight execution history, not manufacturing/inventory

---

## Architecture Decisions (April 2026)

### AIIO Model — Agents Always Act

**Core principle:** Every alert triggers an agent action. Humans inspect and override — they do not initiate.

**The AIIO Flow:**
1. **Signal/Alert detected** → Hive signal emitted (e.g., `EXCEPTION_DETECTED`, `CAPACITY_GAP`, `TENDER_REJECTED`)
2. **TRM agent evaluates** → Calculates urgency (0-1), makes a decision with defined confidence/likelihood
3. **Decision enters governance** → Impact scoring determines AIIO mode:
   - **AUTOMATE**: Agent executes, no human review needed
   - **INFORM**: Agent executes, decision appears in Decision Stream for awareness
   - **INSPECT**: Agent proposes, human must review before execution
4. **Decision surfaces in Decision Stream** → User sees agent's action with urgency + likelihood + reasoning
5. **User response** → INSPECTED (reviewed, agent action stands) or OVERRIDDEN (user changes with reasoning)
6. **Learning loop** → Override reasoning feeds back to TRM replay buffer for agent improvement

**What this means for the UI:**
- No "Create Load Plan" or "Assign Carriers" buttons — agents do this
- Alerts are never just informational — they always have an associated agent action
- The Exception Dashboard, Dock Schedule, Load Board show agent-generated state, not user-created state
- Users inspect, override (with reasoning), and scenario-test
- Governance pipeline controls WHAT agents can do autonomously

### Plan Separation (Strict)
| plan_version | Purpose | Who creates |
|--|--|--|
| `live` | Plan of Record — active transportation plan | Transportation Planning Agent (conformal P50) |
| `tms_baseline` | Current TMS plan — comparison baseline | Extracted from TMS/ERP |
| `decision_action` | User overrides from Decision Stream | Human via AIIO override |

### Planning Cascade (Auto-Execution)
- **S&OP** (weekly Monday 6am): GraphSAGE network/carrier portfolio optimization
- **Transportation Plan** (daily 5am): Plan of Record refresh — load builds, carrier assignments
- **Execution** (every 4h): TRM decision cycle at each facility
- **Exceptions** (continuous): Shipment exception detection via project44 + carrier feeds

### Hierarchy Drilldown (All Views)
- **Geography**: Facility hierarchy with serving lanes
- **Commodity**: Freight class hierarchy (Class → Subclass → Commodity)
- **Carrier**: Carrier portfolio hierarchy (Mode → Carrier → Service Level)
- **Both** use breadcrumb navigation with drilldown

### Governance Pipeline
- Step 0: Planning envelope (lane/mode constraints via Glenday Sieve)
- Step 1: Impact scoring (5 dimensions: cost, service, capacity, risk, sustainability)
- Step 2: AIIO mode assignment (AUTOMATE/INFORM/INSPECT)
- Step 3: Guardrail directive override
- Controls are per-facility with "apply to all facilities" option

### External Integrations (TMS-Specific)
- **project44**: Real-time visibility, ETA, exception detection (primary)
- **Carrier APIs**: EDI 204/214/990, API-based tender/track
- **Weather**: NOAA, Weather.com — disruption prediction
- **Port/Terminal**: AIS data, terminal operating systems
- **Rate Sources**: DAT, Greenscreens, Freightwaves SONAR

### Frontend Navigation
**Admin**: Network Config → Carrier Management → Rate Management → Decision Governance → User Management → Role Management → Context Engine → TMS Data Management → Stochastic Parameters → Metric Configuration → BSC Configuration

**Tactical Planning**: Load Planning → Shipment Management → Carrier Procurement → Dock Scheduling → Lane Analytics → Exception Management

---

## Upstream Sync Process

To pull shared core changes from Autonomy:
```bash
git fetch upstream
git merge upstream/main
# Resolve any conflicts in TMS-specific files
# Test thoroughly before pushing
```

To propose shared core changes:
```bash
# Shared frontend / data-model / powell-core changes go to the monorepo:
#   azirella-ltd/Autonomy-Core
# Shared changes are NOT made in this TMS repo — open a PR against
# Autonomy-Core, ship a new package version, and TMS picks it up via
# `@azirella-ltd/autonomy-frontend` (or `@azirella-ltd/data-model`,
# `@azirella-ltd/powell-core`) on the next dependency bump.
```

# TMS Independence Plan — Unwinding the Fork

**Created:** 2026-04-10
**Status:** Phase 1 starting
**Goal:** Transform Autonomy-TMS from a fork-of-SCP into a sibling product with its own tech stack from the DB up. UI sharing via `autonomy-ui-core` npm package. Cross-app integration via MCP.

---

## Why this plan exists

The original premise — "TMS is a fork of SCP that shares core infrastructure" — has been replaced. The two products are sibling business solutions:

- **Autonomy SCP** = Supply Chain Planning (manufacturing, inventory, demand, MRP)
- **Autonomy TMS** = Transportation Management (loads, carriers, dock, freight)

They share **architectural patterns** (Powell framework, AIIO, conformal prediction, Decision Stream UX) but **not code**. They are deployed independently, scale independently, and can be sold to customers independently.

The current state of `Autonomy-TMS/` contains massive amounts of SCP code from the original fork. Validating TMS keeps hitting conflicts (duplicate `Shipment` classes, broken upstream Alembic chains, model registry collisions) because we've been treating SCP code as "infrastructure to merge from upstream" instead of "code that doesn't belong here."

---

## Target Architecture

```
github.com/MilesAheadToo/
├── autonomy-ui-core/          ← NEW shared frontend package
│   ├── src/
│   │   ├── components/
│   │   │   ├── decision-stream/    (DecisionStream, DecisionCard, AskWhy, ...)
│   │   │   ├── common/             (Card, Button, Badge, Modal, Alert, ...)
│   │   │   ├── navigation/         (TwoTierNav, CategoryBar, PageBar)
│   │   │   └── azirella/           (AzirellaAvatar, voice hook)
│   │   ├── hooks/                  (useCapabilities, useDecisionStream, useTabStore)
│   │   ├── registries/             (decisionTypeRegistry, iconRegistry)
│   │   ├── contexts/               (DecisionStreamContext, ThemeContext)
│   │   └── theme/                  (Tailwind tokens, color system)
│   ├── package.json
│   └── README.md
│
├── autonomy-scp-core/         ← OPTIONAL Python package for shared backend patterns
│   ├── src/autonomy_scp_core/
│   │   ├── powell/                 (TRM base classes, hive signals, AAP)
│   │   ├── conformal/              (Conformal prediction framework)
│   │   ├── governance/             (AIIO model, decision governance pipeline)
│   │   └── decision_stream/        (Decision tracking, status lifecycle)
│   └── pyproject.toml
│
├── Autonomy/                  ← SCP product
│   ├── backend/                    (FastAPI, SCP-specific models, MRP, inventory)
│   ├── frontend/                   (React, imports @autonomy/ui-core, registers SCP types)
│   └── (own DB: autonomy-scp-db)
│
├── Autonomy-TMS/              ← TMS product (this repo, eventually slimmed)
│   ├── backend/                    (FastAPI, TMS-specific models, freight, carriers)
│   ├── frontend/                   (React, imports @autonomy/ui-core, registers TMS types)
│   └── (own DB: autonomy-tms-db)
│
└── autonomy-executive/        ← OPTIONAL aggregated executive console
    └── (Reads from both via MCP, presents unified view)
```

---

## 5-Phase Migration

### Phase 1 — Extract `autonomy-ui-core` package
**Goal:** Create the shared frontend package with plugin registries. No app changes yet.

**Deliverables:**
- New repo `MilesAheadToo/autonomy-ui-core` with package skeleton
- Decision Stream components (DecisionStream, DecisionCard, AskWhyPanel, DigestMessage, AlertBanner) — **stripped of all domain-specific decision type knowledge**
- Common components (Card, Button, Badge, Input, Modal, Alert, Spinner, Table)
- Navigation framework (TwoTierNav, CategoryBar, PageBar)
- AI assistant (Azirella) panel and voice hook
- `useCapabilities`, `useTabStore`, `useDecisionStream` hooks
- `decisionTypeRegistry` API (registerDecisionType, getDecisionType, getAllDecisionTypes)
- `DecisionStreamContext` for backend client injection
- `package.json` with peer deps on React, Tailwind, lucide-react
- Basic Storybook for component preview
- Initial tag `v0.1.0`

**Key design contracts:**

```typescript
// decisionTypeRegistry contract
interface DecisionTypeConfig {
  id: string;                          // e.g., 'freight_procurement'
  label: string;                       // e.g., 'Freight Procurement Agent'
  icon: ComponentType;                 // lucide-react icon
  phase?: string;                      // 'SENSE' | 'ASSESS' | 'ACQUIRE' | 'PROTECT' | 'BUILD' | 'REFLECT'
  editableFields: EditableField[];     // For override dialog
  renderContext?: (decision) => ReactNode;  // Custom context panel
  reasonCodes?: string[];              // App-specific override reason codes
}
```

```typescript
// Backend client contract (injected via context)
interface DecisionStreamClient {
  getDigest(opts?): Promise<DigestResponse>;
  actOnDecision(id: number, action: ActDecisionRequest): Promise<void>;
  refresh(): Promise<DigestResponse>;
  chat(message: string, context?): Promise<ChatResponse>;
  askWhy(decisionId: number): Promise<AskWhyResponse>;
}
```

**Estimated effort:** 1-2 weeks for first usable version

---

### Phase 2 — TMS adopts `autonomy-ui-core`
**Goal:** Replace duplicated UI code in TMS with the shared package.

**Steps:**
1. `npm install github:MilesAheadToo/autonomy-ui-core#v0.1.0` in `Autonomy-TMS/frontend`
2. Delete from TMS: `frontend/src/components/decision-stream/`, `components/common/`, `components/navigation/`, `components/azirella/`, related hooks
3. Create `frontend/src/decisionTypes/` directory:
   - `capacityPromise.js`, `shipmentTracking.js`, `demandSensing.js`
   - `capacityBuffer.js`, `exceptionManagement.js`
   - `freightProcurement.js`, `brokerRouting.js`
   - `dockScheduling.js`
   - `loadBuild.js`, `intermodalTransfer.js`
   - `equipmentReposition.js`
   - `index.js` (registers all 11 at app boot)
4. Create `frontend/src/services/tmsDecisionStreamClient.js` implementing the client contract
5. Wire `<DecisionStreamProvider client={tmsDecisionStreamClient}>` in App.js
6. Update all imports across TMS pages to use `@autonomy/ui-core` instead of local paths
7. Verify the 11 worklists, executive dashboard, governance page still work

**Acceptance criteria:**
- Zero duplicated UI code between TMS and `autonomy-ui-core`
- All 11 TMS decision types render correctly via the registry
- Decision Stream chat, Ask Why, override flow all work
- No imports from `frontend/src/components/decision-stream/` (deleted)

**Estimated effort:** 3-5 days

---

### Phase 3 — SCP adopts `autonomy-ui-core` (parallel to Phase 2)
**Goal:** Same pattern in the SCP repo. This is work in the upstream Autonomy repo, not here.

**Coordination:** Phase 3 happens in a different repo. This plan doc tracks the TMS side; the SCP side has its own corresponding plan.

---

### Phase 4 — TMS detaches from SCP fork
**Goal:** Strip all SCP code out of `Autonomy-TMS/`. TMS becomes a self-contained product.

**Steps:**
1. **Inventory SCP code in TMS repo:**
   - `backend/app/models/sc_entities.py` (huge, ~2000 lines)
   - `backend/app/models/supply_chain_config.py`
   - `backend/app/models/sc_planning.py`, `mps.py`, `mrp.py`, etc.
   - `backend/app/services/aws_sc_planning/`
   - All SC worklist endpoints
   - All SC migrations (200+ files)
2. **Identify TMS-only code:**
   - `backend/app/models/tms_entities.py`, `tms_planning.py`, `transportation_config.py`
   - `backend/app/services/powell/tms_*.py`, `tms_heuristic_library/`
   - `backend/app/integrations/project44/`
   - `backend/app/api/endpoints/p44_integration.py`, `tms_api.py`
2. **Identify shared concept code that needs reimplementation:**
   - Powell framework (`services/powell/`) — port to use TMS-only data sources
   - Conformal prediction — port or use as Python package dependency
   - Decision tracking (`models/decision_tracking.py`) — TMS needs its own version
   - Governance pipeline — TMS needs its own version
   - User/tenant/RBAC — TMS needs its own
3. **Create new TMS backend skeleton:**
   - Fresh `backend/` with only TMS-relevant files
   - New `Base = declarative_base()` in `backend/app/db/base.py`
   - Fresh alembic chain starting from `0001_initial.py`
   - Single migration creating all TMS tables + tenants + users + supply_chain_configs (TMS scoping)
4. **New `tms-db` PostgreSQL container:**
   - `docker-compose.yml` adds `tms-db` service
   - New connection string `TMS_DATABASE_URL`
5. **Migration script:** for existing data (when TMS gets actual customers), provide a one-time data export from old SC fork DB to new TMS DB
6. **Delete SCP code:** Once TMS backend boots cleanly against `tms-db`, delete all SCP files from this repo

**Acceptance criteria:**
- `docker compose up` starts only `tms-db` and `tms-backend` and `tms-frontend`
- `alembic upgrade head` runs cleanly with one head
- TMS backend imports zero modules from SCP-named files
- All 11 TMS worklists work end-to-end against the new TMS backend
- Repo size drops by 50%+

**Estimated effort:** 2-3 weeks (this is the big one)

---

### Phase 5 — MCP integration points
**Goal:** Enable cross-product communication via MCP.

**Steps:**
1. **TMS MCP server** exposes tools:
   - `get_active_exceptions(facility_id, severity_min)`
   - `get_carrier_capacity(lane_id, date_range)`
   - `get_dock_availability(facility_id, time_window)`
   - `tender_load(load_id, carrier_id)` (with approval)
2. **SCP MCP server** exposes tools (in SCP repo):
   - `get_atp_constraints(product_id, site_id, date)`
   - `get_demand_forecast(product_id, lane_id)`
   - `get_supply_plan(product_id, site_id)`
3. **TMS calls SCP** for context:
   - `FreightProcurementTRM` calls `get_atp_constraints` before tendering
   - `DemandSensingTRM` calls `get_demand_forecast` for shipping volume
4. **SCP calls TMS** for context:
   - `POCreationTRM` calls `get_carrier_capacity` before placing PO
   - Inventory rebalancing calls `get_dock_availability` before scheduling transfers
5. **Executive console app** (separate repo) reads from both via MCP and aggregates Decision Streams

**Estimated effort:** 1-2 weeks per direction

---

## Tracking

| Phase | Owner | Status | Started | Completed |
|-------|-------|--------|---------|-----------|
| 1 — Extract autonomy-ui-core | TBD | Planning | — | — |
| 2 — TMS adopts package | TBD | Blocked on Phase 1 | — | — |
| 3 — SCP adopts package | TBD (SCP repo) | Blocked on Phase 1 | — | — |
| 4 — TMS detaches from fork | TBD | Blocked on Phase 2 | — | — |
| 5 — MCP integration | TBD | Blocked on Phase 4 | — | — |

---

## What is paused / parked

- **TMS backend validation** — was hitting endless conflicts because of the wrong premise. Will resume after Phase 4.
- **TMS Alembic migration debugging** — irrelevant once TMS has its own clean migration chain
- **TMS demo data seeding** — parked, will be redone against the clean TMS-only DB
- **TMS decision seeding** — parked, will be redone with TMS-only decision tables (no SCP `decision_type_enum` to extend)
- **Tier 0-3 backend wiring work** (commit `72dc30e4`, `7f8dbc4d`) — code is committed but parked. Some pieces (`tms_api.py`, the migration, the seeders) will be reused as-is in Phase 4. The path-mismatch fixes in `planning_cascade.py` will become irrelevant when TMS has its own decision endpoint.

---

## Why we keep the work that's already committed

Even though we're pivoting, the existing TMS frontend (11 worklists, 4 planning pages, map, dashboards) and the TMS-specific backend modules (tms_entities, tms_api, seeders, heuristic library) **remain useful**. They define the TMS domain model and UX. Phase 4 will lift them out of the SCP-mixed environment into a clean TMS-only environment.

The work that becomes obsolete:
- Anything in `tms_provisioning_adapter.py` that maps to SCP provisioning steps (will be replaced with native TMS provisioning)
- The `decision_type_enum` extension migration (will be replaced with a TMS-only enum)
- Hacks added to make sc_entities and tms_entities coexist (model name disambiguation, table renames)

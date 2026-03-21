# D365-FORK.md — Dynamics 365 Native Fork Analysis

**Date**: 2026-03-21
**Status**: Investigation / Decision Document
**Author**: Claude Code analysis of Autonomy codebase (528K LOC, 1,144 files)
**Cross-references**: [DIGITAL_TWIN.md §0](docs/internal/DIGITAL_TWIN.md) (in-memory heuristic mirror architecture — applies to all ERP forks)

---

## Executive Summary

This document assesses the effort to create a **Dynamics 365 Finance & Operations native fork** of the Autonomy platform. "Native" means:

1. **Data model**: Replace AWS Supply Chain Data Model with D365 F&O native tables (`ReqItemTable`, `InventTable`, `BOMTable`, etc.)
2. **UI**: Replace React + Material-UI with React + Fluent UI 9 via PCF controls embedded in D365/Power Apps
3. **Database**: Replace PostgreSQL with Azure SQL + Dataverse + Microsoft Fabric
4. **AI/LLM**: Replace Claude API / vLLM with Azure OpenAI Service + Copilot Studio
5. **Deployment**: Azure-native (AKS, Azure ML, AppSource listing)

**Bottom line**: ~40% of the codebase (the AI/ML engine) can remain common across both forks. ~60% requires D365-specific rewrite. The fork is a **6-9 month effort for a team of 4-6 engineers** with D365 F&O and Azure expertise.

---

## Table of Contents

1. [Codebase Anatomy](#1-codebase-anatomy)
2. [Data Model: AWS SC vs D365 F&O](#2-data-model-aws-sc-vs-d365-fo)
3. [Fork Architecture](#3-fork-architecture)
4. [Layer-by-Layer Analysis](#4-layer-by-layer-analysis)
5. [Technology Stack Migration](#5-technology-stack-migration)
6. [Microsoft Cloud Deployment](#6-microsoft-cloud-deployment)
7. [AI Migration: Claude → Azure OpenAI](#7-ai-migration-claude--azure-openai)
8. [D365 Native Planning Overlap](#8-d365-native-planning-overlap)
9. [Common vs Fork Code Matrix](#9-common-vs-fork-code-matrix)
10. [Effort Estimates](#10-effort-estimates)
11. [Risk Analysis](#11-risk-analysis)
12. [Recommendation](#12-recommendation)

---

## 1. Codebase Anatomy

### Current Size

| Layer | Lines of Code | Files | % of Total |
|-------|--------------|-------|------------|
| **Backend — Models** | 36,029 | 138 | 6.8% |
| **Backend — Services** | 199,816 | 320 | 37.8% |
| **Backend — API Endpoints** | 75,112 | 132 | 14.2% |
| **Backend — Integrations** | 14,232 | 20 | 2.7% |
| **Backend — main.py** | 6,598 | 1 | 1.2% |
| **Frontend — Pages** | 97,243 | 176 | 18.4% |
| **Frontend — Components** | 71,733 | 198 | 13.6% |
| **Frontend — Services/Utils** | 10,857 | 56 | 2.1% |
| **Docs / Config** | ~17,000 | ~100 | 3.2% |
| **TOTAL** | **~528,000** | **~1,144** | **100%** |

### Key Subsystems

| Subsystem | LOC | Coupling to AWS SC |
|-----------|-----|-------------------|
| Powell Framework (TRM/GNN/Hive) | 56,927 | **LOW** (dataclass abstractions) |
| SC Planning Services | 6,424 | **CRITICAL** (deep field coupling) |
| Deterministic Engines | ~5,000 | **CRITICAL** (AWS SC entities) |
| Simulation / Digital Twin | ~8,000 | **CRITICAL** (AWS SC topology) |
| Conformal Prediction | ~3,500 | **MEDIUM** (outcome columns) |
| Causal AI / Override Tracking | ~4,000 | **MEDIUM** (decision tables) |
| ERP Integrations (SAP/D365/Odoo) | 14,232 | **CRITICAL** (mapping layer) |
| Skills Framework | 1,593 | **ZERO** (generic handlers) |

---

## 2. Data Model: AWS SC vs D365 F&O

### Fundamental Difference

| Aspect | AWS SC Data Model | D365 F&O Data Model |
|--------|------------------|---------------------|
| **Philosophy** | Flat, denormalized, 35 entities | Traditional ERP, normalized, 2,000+ tables |
| **Identity** | `product_id`, `company_id` | `ItemId`, `DataAreaId` (legal entity) |
| **Dimensions** | Embedded in entity fields | Separate `InventDim` table (site, warehouse, batch, serial, color, size, config) |
| **Planning Params** | `inv_policy` + `supply_planning_parameters` | `ReqItemTable` per item-site (coverage code, time fences, lead times) |
| **BOM** | `product_bom` (single table) | `BOMTable` + `BOMVersion` + `BOMLine` (versioned) |
| **Multi-company** | `tenant_id` (platform concept) | `DataAreaId` partition on every table (ERP-native) |
| **Inventory** | `inv_level.on_hand_qty` | `InventSum` by `InventDim` (multidimensional) |
| **Orders** | `inbound_order` / `outbound_order` | `PurchTable`/`PurchLine`, `SalesTable`/`SalesLine` |
| **Manufacturing** | `production_process`, `process_operation` | `ProdTable`, `ProdBOM`, `ProdRoute`, `RouteOpr` |
| **Suppliers** | `trading_partner` (type=supplier) | `VendTable` + `VendPurchOrderJour` |

### Entity Mapping (35 AWS SC → D365 Equivalents)

| AWS SC Entity | D365 F&O Table/Entity | Complexity |
|---------------|----------------------|------------|
| `Product` | `InventTable` / `ReleasedProductsV2` | Medium (dimension handling) |
| `ProductHierarchy` | `EcoResProductCategory` | Low |
| `ProductBom` | `BOMTable` + `BOMVersion` + `BOMLine` | High (versioning adds complexity) |
| `Site` | `InventSite` + `InventLocation` | Medium (site vs warehouse split) |
| `TransportationLane` | `TMSRoute` / custom | High (no direct equivalent) |
| `TradingPartner` | `VendTable` / `CustTable` | Medium (split into two tables) |
| `Forecast` | `ForecastSales` / `ReqDemPlanForecast` | Medium |
| `InvPolicy` | `ReqItemTable` (coverage codes, SS) | High (different paradigm) |
| `InvLevel` | `InventSum` by `InventDim` | High (dimensional inventory) |
| `SourcingRules` | `ReqItemTable.CoverageGroup` + `InventItemPurchSetup` | High (spread across tables) |
| `SupplyPlan` | `ReqPO` / `ReqTrans` (planned orders) | Medium |
| `InboundOrder` | `PurchTable` + `PurchLine` | Low |
| `OutboundOrder` | `SalesTable` + `SalesLine` | Low |
| `Shipment` | `WHSShipmentTable` + `TMSFreightBillDetail` | Medium |
| `Company` | `CompanyInfo` / `DataAreaId` | Low |
| `Geography` | `LogisticsAddressCountryRegion` | Low |
| `ConsensusDemand` | Custom (no native equivalent) | High |
| `SupplementaryTimeSeries` | Custom (no native equivalent) | High |

**Key Challenge**: D365's `InventDim` dimensional model has no AWS SC equivalent. Every inventory query in D365 must specify dimensions (site, warehouse, batch, serial). This affects **every service that touches inventory**.

### What Stays, What Changes

```
AWS SC Data Model (35 entities, 1,832 LOC in sc_entities.py)
    └── COMPLETE REWRITE required for D365 fork
        └── New: d365_entities.py mapping to D365 F&O tables
        └── New: InventDim handling throughout
        └── New: DataAreaId (legal entity) scoping everywhere
```

---

## 3. Fork Architecture

### Proposed Repository Structure

```
autonomy/                          # Shared monorepo with build-time selection
├── core/                          # COMMON — data-model-agnostic
│   ├── ai/                        # TRM neural networks, GNN models
│   │   ├── trm/                   # 7M-param recursive models
│   │   ├── gnn/                   # GraphSAGE, tGNN, Site tGNN
│   │   ├── conformal/             # CDT calibration, risk bounds
│   │   └── training/              # BC, RL, curriculum pipelines
│   ├── powell/                    # Powell SDAM framework (abstract)
│   │   ├── site_agent.py          # Decision cycle orchestration
│   │   ├── hive_signal.py         # Stigmergic coordination
│   │   ├── escalation_arbiter.py  # Vertical routing
│   │   ├── decision_cycle.py      # 6-phase execution
│   │   └── authorization_protocol.py  # AAP
│   ├── skills/                    # Claude Skills / Azure OpenAI Skills
│   ├── causal/                    # Override effectiveness, matching
│   └── stochastic/                # Distribution fitting, Monte Carlo
│
├── adapters/                      # FORK POINT — data model specific
│   ├── aws_sc/                    # Current: AWS SC data model adapter
│   │   ├── models/                # SQLAlchemy models (sc_entities.py)
│   │   ├── engines/               # AATP, MRP, Buffer engines
│   │   ├── planning/              # 3-step planning services
│   │   ├── simulation/            # Digital twin (AWS SC topology)
│   │   └── integrations/          # SAP/D365/Odoo staging → AWS SC
│   │
│   └── d365/                      # NEW: D365 F&O native adapter
│       ├── models/                # D365 table mappings (X++ entities or OData)
│       ├── engines/               # MRP/AATP/Buffer using D365 tables
│       ├── planning/              # Own planning engine reading D365 tables (cannot delegate MC to Planning Optimization)
│       ├── simulation/            # Digital twin (D365 topology)
│       └── connector/             # Direct D365 OData/Dataverse integration
│
├── frontends/                     # FORK POINT — UI framework specific
│   ├── react-mui/                 # Current: React + Material-UI
│   └── react-fluent/              # NEW: React + Fluent UI 9 (PCF controls)
│
└── deployment/                    # FORK POINT — infrastructure specific
    ├── docker-compose/            # Current: Docker + PostgreSQL
    └── azure/                     # NEW: AKS + Azure SQL + Azure ML
```

### Data Flow in D365 Fork

```
D365 F&O (Azure SQL) — Source of Truth for master data
    ↓ OData v4 / Virtual Entities / Dual-Write (READ)
Autonomy D365 Adapter
    ├── Caches D365 master data (InventTable, ReqItemTable, BOMTable, etc.)
    ├── Runs own planning engine (1,000 MC sims — cannot use Planning Optimization)
    ├── Builds stochastic distributions from D365 ReqItemTable parameters
    ↓ (extracts state → dataclass abstractions)
┌─────────────────────────────────────────┐
│         COMMON ENGINE (unchanged)        │
│  Monte Carlo Planning Engine (own)       │
│  TRM Agents → GNN Models → Conformal    │
│  Hive Signals → Decision Cycle → AAP    │
│  Skills → Causal AI → Override Tracking  │
└─────────────────────────────────────────┘
    ↓ (decisions as dataclass outputs)
D365 Adapter (writes back to D365)
    ↓ OData / Business Events / Custom Service
D365 F&O (executes: PO release, production order, transfer order)

Note: D365 Planning Optimization runs INDEPENDENTLY for deterministic MRP.
Autonomy does NOT call Planning Optimization — it runs its own stochastic
engine in parallel, reading the same master data inputs.
```

---

## 4. Layer-by-Layer Analysis

### Layer 1: Data Models (36,029 LOC, 138 files)

| Component | LOC | Fork Status | Effort |
|-----------|-----|-------------|--------|
| `sc_entities.py` (34 AWS SC classes) | 1,832 | **REWRITE** — new `d365_entities.py` | High |
| `supply_chain_config.py` (DAG topology) | 685 | **REWRITE** — use D365 Sites/Warehouses | High |
| `powell_decisions.py` (11 decision tables) | 853 | **COMMON** — string IDs, no FKs | None |
| `planning_cascade.py` | 726 | **ADAPT** — map to D365 planning hierarchy | Medium |
| `planning_hierarchy.py` | 709 | **ADAPT** — D365 has native hierarchy | Medium |
| `decision_tracking.py` | 521 | **COMMON** — generic decision flow | None |
| `decision_embeddings.py` | 386 | **COMMON** — pgvector/Azure AI Search | Low |
| `sap_staging.py` / `d365_staging.py` / `odoo_staging.py` | 1,200 | **DROP** — no staging needed (native access) | None |
| All other models | ~29,000 | Mixed (60% common, 40% adapt) | Medium |

**Summary**: ~15,000 LOC rewrite, ~10,000 LOC adapt, ~11,000 LOC common.

### Layer 2: Planning Services (6,424 LOC, 12 files)

This is the **highest-coupling layer**. Every file directly references AWS SC field names.

| File | LOC | Fork Status | Notes |
|------|-----|-------------|-------|
| `demand_processor.py` | 417 | **REWRITE** | D365 uses `ForecastSales`, not `Forecast` |
| `inventory_target_calculator.py` | 1,319 | **PARTIAL REWRITE** | 8 policy types stay; field access changes to `ReqItemTable` |
| `net_requirements_calculator.py` | 1,152 | **REWRITE** | Must rewrite against D365 tables (see note below) |
| `planner.py` | 265 | **REWRITE** | Orchestrator changes for D365 planning flow |
| `stochastic_sampler.py` | 685 | **COMMON** | Distribution math is data-model-agnostic |
| `execution_cache.py` | 619 | **REWRITE** | Cache D365 entities instead of AWS SC |
| Others | ~1,967 | Mixed | |

> **CRITICAL — Digital Twin as In-Memory Heuristic Mirror (Not API Client)**
>
> D365's Planning Optimization is a **deterministic, single-run, stateful MRP engine**. It runs in 1-2 minutes per execution and **writes planned orders back to D365 tables** (`ReqPO`, `ReqTrans`). Running it 1,000 times for Monte Carlo would take 17-33 hours and pollute production data. There is no dry-run/sandbox API.
>
> **But this is not the right framing.** The question is not "how do we call D365's planner 1,000 times?" — it's "how do we replicate D365's planning heuristics as pure in-memory math?"
>
> **The digital twin architecture (same pattern as Odoo and SAP forks):**
>
> 1. **D365 Planning Optimization runs once** — produces the deterministic baseline plan (standard customer workflow, unchanged)
> 2. **Autonomy reads D365's planning config once** — extracts `ReqItemTable` parameters (coverage codes, time fences, min/max levels, lead times, safety stock), `BOMTable`/`BOMLine` (component ratios, scrap %), `InventTable` (product master), `InventSum` (on-hand by dimension)
> 3. **Autonomy's simulation engine replicates the heuristics as numpy operations** — coverage code logic (period, min/max, lot-for-lot), net requirements netting, BOM explosion, lead time offsetting — all as vectorized in-memory math, not ORM queries or API calls
> 4. **Runs 1,000 stochastic trials in 2-5 minutes** — each trial applies stochastic perturbations (demand variability, lead time variability, yield loss, capacity fluctuation) to the deterministic heuristic rules, observing where they fail under uncertainty
> 5. **TRMs train on the gap** — the difference between heuristic outcomes and optimal outcomes under uncertainty is what agents learn to compensate for
>
> **The simulation engine never calls back to D365 during Monte Carlo.** It is a lightweight mathematical mirror of D365's `ReqItemTable` logic, not an API client. This is identical to how the SAP fork mirrors `MARC`/`MDLV` parameters and the Odoo fork mirrors `stock.warehouse.orderpoint` rules.
>
> **Performance comparison:**
>
> | Approach | Time for 1,000 trials | Feasible? |
> |----------|----------------------|-----------|
> | Call D365 Planning Optimization 1,000× | 17-33 hours | No (also pollutes prod data) |
> | Autonomy in-memory heuristic mirror | **2-5 minutes** | Yes |
>
> **What this means for the fork:**
>
> The planning services (`net_requirements_calculator.py`, `demand_processor.py`, `inventory_target_calculator.py`) are **REWRITE** — but the rewrite is a **config extraction + heuristic mirroring** task, not a full MRP reimplementation. The engine reads D365's `ReqItemTable` coverage parameters once, then runs its own vectorized simulation loop. The core mathematical operations (netting, BOM explosion, lead time offsetting) are already implemented and are largely **data-model-agnostic** — what changes is the config extraction layer that reads D365-specific table structures instead of AWS SC entities.
>
> **D365-specific heuristics to mirror from `ReqItemTable`:**
>
> | D365 Coverage Code | Logic | Autonomy Mirror |
> |-------------------|-------|-----------------|
> | `0` — Manual | No automatic planning | Skip (no reorder trigger) |
> | `1` — Period | Consolidate requirements within `CoverageTimeFence` | Group demand by fence, single planned order per period |
> | `2` — Requirement (lot-for-lot) | Plan exactly what's needed | 1:1 demand → planned order |
> | `3` — Min/Max | Reorder to max when below min | `if on_hand < min: order(max - on_hand)` |
> | `4` — DDMRP (buffer) | Net flow equation against green/yellow/red zones | `net_flow = on_hand + on_order - qualified_demand` |
>
> These are simple mathematical rules — trivial to replicate as numpy operations. The complexity is in reading D365's dimensional model (`InventDim`) correctly, not in the planning math itself.

### Layer 3: Powell Framework — TRM Agents (56,927 LOC, 94 files)

**This is where the good news is.** The Powell framework was designed with clean abstraction boundaries.

| Component | LOC | Fork Status | Why |
|-----------|-----|-------------|-----|
| 11 TRM neural networks | ~7,000 | **COMMON** | Consume `np.ndarray`, not ORM objects |
| 3 GNN models | ~5,000 | **COMMON** | PyTorch Geometric tensors, zero entity coupling |
| Training pipeline | ~8,000 | **COMMON** | `TrainingRecord` tuples, abstract |
| Site Agent orchestration | ~4,000 | **COMMON** | Config-driven, uses string IDs |
| Hive signals / coordination | ~8,000 | **COMMON** | Pure signal propagation, no entity access |
| Decision cycle / AAP | ~3,000 | **COMMON** | Abstract agent roles and actions |
| Decision reasoning | 1,094 | **ADAPT** | Display strings reference Product.description |
| Deterministic engines | ~5,000 | **REWRITE** | AATP, MRP, Buffer directly query AWS SC entities |
| Outcome collector | 1,255 | **ADAPT** | Joins with entity tables for actual outcomes |
| Simulation / seeder | ~5,000 | **REWRITE** | Digital twin replicates AWS SC topology |
| CDC / relearning | ~3,000 | **ADAPT** | Schedule and trigger logic stays; data queries change |
| Other services | ~6,500 | Mixed | |

**Summary**: ~35,000 LOC common (62%), ~10,000 LOC adapt (17%), ~12,000 LOC rewrite (21%).

### Layer 4: API Endpoints (75,112 LOC, 132 files)

| Category | LOC (est.) | Fork Status | Notes |
|----------|-----------|-------------|-------|
| Planning endpoints | ~15,000 | **REWRITE** | Response shapes change for D365 entities |
| Powell/Decision endpoints | ~20,000 | **COMMON** | Decision stream, worklists are entity-agnostic |
| Auth/Admin endpoints | ~10,000 | **ADAPT** | Azure AD replaces JWT; Dataverse roles |
| Config endpoints | ~8,000 | **REWRITE** | D365 Sites/Warehouses replace SC config DAG |
| Simulation endpoints | ~5,000 | **ADAPT** | Same concepts, different entity backing |
| ERP integration endpoints | ~5,000 | **DROP** | Not needed (D365 is the ERP) |
| Other endpoints | ~12,000 | Mixed | |

**Summary**: ~25,000 LOC common (33%), ~22,000 LOC adapt (29%), ~23,000 LOC rewrite (31%), ~5,000 LOC drop (7%).

### Layer 5: Frontend (179,833 LOC, 430 files)

| Category | LOC (est.) | Fork Status | Notes |
|----------|-----------|-------------|-------|
| Planning pages (66) | 36,229 | **REWRITE** (UI framework + field names) | Fluent UI 9 + D365 field names |
| Admin pages (40) | ~22,000 | **PARTIAL REWRITE** | ERP mgmt pages drop; TRM/GNN dashboards adapt |
| Decision Stream / Worklists | ~15,000 | **ADAPT** | Entity-agnostic; just restyle to Fluent |
| Common components (32) | ~8,000 | **REWRITE** | MUI → Fluent UI 9 component library |
| Scenario / Beer Game | ~18,000 | **ADAPT** | Learning tenant concept stays |
| Charts / Visualization | ~12,000 | **ADAPT** | Recharts works with Fluent; D3 unchanged |
| Supply chain config UI | ~10,000 | **REWRITE** | D365 topology replaces DAG builder |
| API services | ~3,000 | **ADAPT** | Endpoint URLs change; patterns stay |
| Other | ~55,000 | Mixed | |

**Summary**: ~20,000 LOC common (11%), ~85,000 LOC adapt (47%), ~65,000 LOC rewrite (36%), ~10,000 LOC drop (6%).

**Frontend is the largest rewrite area** — not because of logic changes, but because of the MUI → Fluent UI 9 component swap across 430 files.

---

## 5. Technology Stack Migration

### Database: PostgreSQL → Azure SQL + Dataverse

| Current | D365 Fork | Migration Complexity |
|---------|-----------|---------------------|
| PostgreSQL 15+ (transactional) | **Azure SQL Database** (Autonomy's own tables) + **D365 F&O Azure SQL** (ERP tables) | **HIGH** |
| SQLAlchemy 2.0 ORM | SQLAlchemy 2.0 (Azure SQL dialect) or **direct OData** for D365 tables | **MEDIUM** |
| pgvector (RAG embeddings) | **Azure AI Search** or Azure SQL vector type (2025 GA) | **MEDIUM** |
| pgaudit (SOC II) | Azure SQL Auditing + Microsoft Defender for SQL | **LOW** (better tooling) |
| RLS (tenant isolation) | Azure SQL RLS + D365 `DataAreaId` partitioning | **LOW** (native support) |
| Alembic migrations | Alembic (for Autonomy tables) + D365 extension model (for D365 tables) | **MEDIUM** |
| TimescaleDB extensions | Azure Data Explorer (Kusto) or Fabric Real-Time Intelligence | **MEDIUM** |

**Key architectural decision**: The D365 fork would have **two databases**:
1. **D365 F&O Azure SQL** — managed by Microsoft, contains ERP data. Read via OData or virtual entities. Cannot modify schema.
2. **Autonomy Azure SQL** — managed by us, contains Powell decisions, TRM checkpoints, embeddings, audit logs. Full schema control.

This is fundamentally different from the current architecture where PostgreSQL holds everything.

### ORM Strategy

```python
# Current (AWS SC fork): Everything via SQLAlchemy
product = db.query(Product).filter_by(product_id="SKU-001").first()

# D365 fork: Hybrid approach
# Autonomy's own tables → SQLAlchemy (Azure SQL)
decision = db.query(PowellATPDecision).filter_by(id=decision_id).first()

# D365 tables → OData client (read/write via D365 API)
product = d365_client.get("ReleasedProductsV2", filter=f"ItemNumber eq 'SKU-001'")
inventory = d365_client.get("InventOnhandV2", filter=f"ItemId eq 'SKU-001' and InventSiteId eq 'SITE-1'")
```

### Frontend: Material-UI → Fluent UI 9

| Current | D365 Fork | Migration Notes |
|---------|-----------|----------------|
| `@mui/material` 5.13 | `@fluentui/react-components` 9.x | Component-by-component swap |
| `@mui/icons-material` | `@fluentui/react-icons` | Icon name mapping |
| `@mui/x-charts` | Fluent UI + Recharts (Recharts is framework-agnostic) | Charts stay |
| `@radix-ui/*` (common/) | Drop — Fluent UI 9 replaces this layer | Simplifies stack |
| `@chakra-ui/react` | Drop — Fluent UI 9 replaces | Removes dependency |
| Tailwind CSS | Drop or keep (Fluent has its own tokens) | Optional |
| `@emotion/react` (CSS-in-JS) | Griffel (Fluent's CSS-in-JS, built on Stylex) | Different API |

**Effort multiplier**: The current codebase uses **three UI frameworks** (MUI, Radix, Chakra). The D365 fork consolidates to **one** (Fluent UI 9), which is actually cleaner. But every component import across 430 files must change.

**PCF Control Packaging**: For D365 embedded experience, key pages would be packaged as **PowerApps Component Framework (PCF) controls**:
- Decision Stream worklist → PCF control in D365 workspace
- Planning dashboards → PCF controls in D365 planning module
- TRM/GNN dashboards → Standalone Power App (admin-only)
- Azirella directive input → PCF control in D365 navigation bar

### Deployment: Docker/Compose → Azure Native

| Current | D365 Fork |
|---------|-----------|
| Docker Compose (proxy, frontend, backend, db, pgadmin) | **Azure Kubernetes Service** (backend) + **Azure SQL** (db) + **Azure Static Web Apps** or **Power Apps** (frontend) |
| Nginx proxy | **Azure Front Door** or **Azure Application Gateway** |
| PostgreSQL container | **Azure SQL Database** (managed) |
| pgAdmin | **Azure Data Studio** / **SSMS** |
| vLLM container (GPU) | **Azure ML Managed Endpoint** or **AKS GPU node pool** |
| Let's Encrypt TLS | **Azure Key Vault** + managed certificates |

---

## 6. Microsoft Cloud Deployment

### Reference Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure Front Door (CDN + WAF)              │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────────┐
        ↓              ↓                  ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Power Apps  │ │  AKS Cluster │ │  Azure ML        │
│  (Fluent UI) │ │  (Backend)   │ │  (Model Serving)  │
│              │ │              │ │                    │
│  - PCF       │ │  - FastAPI   │ │  - TRM endpoints  │
│  - Model-    │ │  - Powell    │ │  - GNN endpoints   │
│    Driven    │ │  - Engines   │ │  - Training jobs   │
│    App       │ │  - CDC jobs  │ │                    │
└──────┬───────┘ └──────┬───────┘ └────────┬───────────┘
       │                │                   │
       ↓                ↓                   ↓
┌──────────────────────────────────────────────────────────────┐
│                     Azure Virtual Network                     │
│                                                               │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Azure SQL  │  │ Azure SQL   │  │ Azure OpenAI Service │  │
│  │ (Autonomy  │  │ (D365 F&O   │  │ (GPT-4o / GPT-4)     │  │
│  │  tables)   │  │  read-only) │  │                      │  │
│  └────────────┘  └─────────────┘  └──────────────────────┘  │
│                                                               │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Azure AI   │  │ Dataverse   │  │ Azure Key Vault      │  │
│  │ Search     │  │ (Virtual    │  │ (secrets, certs)     │  │
│  │ (RAG)      │  │  Entities)  │  │                      │  │
│  └────────────┘  └─────────────┘  └──────────────────────┘  │
│                                                               │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Microsoft  │  │ Azure       │  │ Azure Monitor        │  │
│  │ Fabric     │  │ Blob        │  │ + Log Analytics      │  │
│  │ (Analytics)│  │ Storage     │  │ (SOC II audit)       │  │
│  └────────────┘  └─────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Cost Estimate (Monthly, Production)

| Service | SKU | Est. Cost/mo |
|---------|-----|-------------|
| AKS (backend, 3 nodes) | D4s v5 (4 vCPU, 16GB) | $440 |
| AKS GPU node (inference) | NC4as T4 v3 (1 T4 GPU) | $530 |
| Azure SQL (Autonomy DB) | S3 (100 DTU) | $150 |
| Azure AI Search (RAG) | S1 (15M docs) | $250 |
| Azure OpenAI (Skills exceptions) | GPT-4o, ~50K calls/mo | $200 |
| Azure ML (training, spot) | NC6s v3 (V100), ~20h/mo | $80 |
| Azure Front Door | Standard tier | $35 |
| Azure Key Vault | Standard | $5 |
| Azure Monitor + Log Analytics | 10GB/day ingest | $70 |
| Microsoft Fabric (analytics) | F2 capacity | $260 |
| Azure Blob (checkpoints, exports) | 100GB hot | $2 |
| **TOTAL** | | **~$2,020/mo** |

*Note: D365 F&O license costs are borne by the customer, not Autonomy. This is the ISV infrastructure cost only.*

### SOC II Compliance on Azure

| Current (PostgreSQL) | Azure Equivalent | Status |
|---------------------|-----------------|--------|
| RLS policies | Azure SQL RLS (native) + D365 DataAreaId | Better |
| pgaudit | Azure SQL Auditing + Defender for SQL | Better |
| SSL/TLS (pg_hba.conf) | Enforced by default on Azure SQL | Better |
| dm-crypt/LUKS (encryption at rest) | Azure SQL TDE (transparent, always on) | Better |
| pgcrypto (column encryption) | Azure SQL Always Encrypted | Better |
| Alembic migrations (change mgmt) | Alembic + Azure DevOps pipelines | Same |
| Manual audit log shipping | Azure Monitor → Log Analytics (automatic) | Better |

**Assessment**: Azure provides **stronger SOC II tooling** out of the box than self-managed PostgreSQL.

---

## 7. AI Migration: Claude → Azure OpenAI

### LLM Usage Points in Codebase

| Usage | Current | D365 Fork | Effort |
|-------|---------|-----------|--------|
| **Claude Skills** (exception handler) | Claude API (Haiku/Sonnet) | Azure OpenAI (GPT-4o-mini / GPT-4o) | **LOW** — same OpenAI-compatible API |
| **Azirella** (directive parsing) | vLLM + Qwen 3 8B | Azure OpenAI GPT-4o-mini | **LOW** — same API format |
| **Query Router** (question routing) | vLLM + Qwen 3 8B | Azure OpenAI GPT-4o-mini | **LOW** |
| **Email Signal Classification** | vLLM + Qwen 3 8B | Azure OpenAI GPT-4o-mini | **LOW** |
| **Executive Briefing** | vLLM + Qwen 3 8B | Azure OpenAI GPT-4o | **LOW** |
| **Synthetic Data Wizard** | vLLM + Qwen 3 8B | Azure OpenAI GPT-4o | **LOW** |
| **Decision Memory RAG** | pgvector + cosine similarity | Azure AI Search + embeddings | **MEDIUM** |
| **Knowledge Base RAG** | pgvector + chunk embeddings | Azure AI Search | **MEDIUM** |

### API Compatibility

The existing codebase already uses **OpenAI-compatible API format** for all LLM calls (via `LLM_API_BASE`). Azure OpenAI uses the same format with different auth:

```python
# Current (vLLM / Qwen)
client = OpenAI(base_url="http://localhost:8001/v1", api_key="not-needed")

# Azure OpenAI (drop-in replacement)
client = AzureOpenAI(
    azure_endpoint="https://autonomy.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version="2024-10-21"
)
```

**Migration effort for LLM calls**: ~50 LOC changes (auth wrapper). All prompt templates, tool schemas, and response parsing remain identical.

### Claude Skills → Azure OpenAI Skills

| Current Skill Tier | Claude Model | Azure Equivalent | Cost Change |
|--------------------|-------------|-----------------|-------------|
| Deterministic | None (no LLM) | None | $0 |
| Calculation-heavy | Claude Haiku (~$0.0018/call) | GPT-4o-mini (~$0.0015/call) | -17% |
| Judgment-requiring | Claude Sonnet (~$0.0054/call) | GPT-4o (~$0.0060/call) | +11% |

**Net cost impact**: Roughly equivalent. GPT-4o-mini is slightly cheaper than Haiku; GPT-4o is slightly more expensive than Sonnet.

### PyTorch Models (TRM, GNN) — No Change

TRM and GNN models are **pure PyTorch**. They have zero dependency on any LLM provider. They run identically on:
- CPU (any cloud)
- NVIDIA GPU via CUDA (any cloud with NVIDIA hardware)
- Azure ML managed endpoints
- AKS with GPU node pools

**No migration needed** for the core AI engine.

### Copilot Studio Integration (Optional Enhancement)

For the D365 fork, Autonomy could optionally integrate with **Microsoft Copilot Studio** to surface TRM decisions and Decision Stream items within the native D365 Copilot experience:

```
User asks D365 Copilot: "What inventory decisions need my attention?"
    ↓
Copilot Studio → Custom Connector → Autonomy Decision Stream API
    ↓
Returns top-5 decisions with urgency/likelihood/benefit scores
    ↓
Copilot renders in D365 Copilot panel with Accept/Override actions
```

This is an **additive enhancement**, not a requirement. Estimated effort: ~2 weeks.

---

## 8. D365 Native Planning Overlap

### What D365 SCM Already Does

| Capability | D365 Native | Quality | Autonomy Adds |
|-----------|------------|---------|---------------|
| MRP / Net Requirements | Planning Optimization (cloud-native, 1-2 min, deterministic single-run) | Excellent for single-run | **In-memory heuristic mirror** — reads `ReqItemTable` config once, replicates coverage code logic as numpy, 1,000 MC trials in 2-5 min (never calls D365 during sim) |
| MPS | Planning Optimization | Good for deterministic | **In-memory mirror** — same pattern: read D365 config, replicate as math, simulate stochastically |
| Safety Stock | Fixed qty, DOC, service level | Basic | +5 advanced policies (sl_fitted, conformal, sl_conformal_fitted, econ_optimal, conformal) |
| DDMRP | Full implementation (free) | Good | Buffer optimization via InventoryBufferTRM |
| Demand Forecasting | Statistical + Azure ML | Good | Conformal intervals, censored demand handling |
| ATP | Standard ATP | Good | Allocated ATP with priority consumption |
| CTP | Capacity-to-promise | Good | Multi-stage CTP with pegging chains |
| Capacity Planning | Rough-cut + finite scheduling | Good | Stochastic capacity with bottleneck GNN |
| BOM Explosion | Multi-level, phantom, co-product | Excellent | Same (no advantage) |

### Where Autonomy's Value-Add is Unique (No D365 Native Equivalent)

| Capability | Description | D365 Has? |
|-----------|-------------|-----------|
| **11 TRM Agents** | Autonomous execution decisions at <10ms | No |
| **GNN Network Optimization** | Graph-based S&OP + execution + site coordination | No |
| **Conformal Prediction** | Distribution-free uncertainty on every decision | No |
| **Causal AI** | 3-tier counterfactual + propensity matching + Bayesian | No |
| **Override Learning** | Bayesian posteriors on human override quality | No |
| **Decision Stream** | Urgency/Likelihood/Benefit prioritized inbox | No (basic workflow only) |
| **Hive Coordination** | Stigmergic multi-agent signal propagation | No |
| **Digital Twin** | Stochastic APS replication with 9 distributions per entity | No |
| **AAP** | Cross-functional authorization at machine speed | No |
| **Escalation Arbiter** | Kahneman System 1/2 vertical routing | No |
| **Skills Exception Handling** | LLM-powered novel situation reasoning | Copilot (surface-level only) |

### Strategic Positioning in D365 Fork

The D365 fork positions as: **"Decision Intelligence layer for D365 SCM"** — running its own stochastic planning engine **alongside** (not on top of) D365's Planning Optimization.

**The digital twin is an in-memory heuristic mirror, not an API client.** D365's Planning Optimization runs once for the deterministic baseline. Autonomy reads D365's `ReqItemTable` config once, replicates the coverage code logic (period, min/max, lot-for-lot, DDMRP) as pure numpy operations, and runs 1,000 stochastic trials in 2-5 minutes. It never calls back to D365 during Monte Carlo.

```
┌─────────────────────────────────────────────────────────────────┐
│                    D365 F&O (Source of Truth)                    │
│  Master Data: InventTable, ReqItemTable, BOMTable, VendTable    │
│  Transactions: PurchTable, SalesTable, ProdTable                │
└────────┬───────────────────────────────────────┬────────────────┘
         │ (standard workflow)                   │ (one-time config read)
         ↓                                       ↓
┌────────────────────────┐       ┌────────────────────────────────┐
│  D365 Planning         │       │  Autonomy Digital Twin         │
│  Optimization          │       │                                │
│                        │       │  1. Read ReqItemTable config   │
│  • Runs once           │       │  2. Mirror heuristics as numpy │
│  • Deterministic MRP   │       │     (coverage codes, min/max,  │
│  • Writes ReqPO        │       │      BOM explosion, netting)   │
│  • 1-2 min runtime     │       │  3. Run 1,000 MC trials        │
│                        │       │     (2-5 min, in-memory)       │
│  Customer's standard   │       │  4. Observe where heuristics   │
│  production planner    │       │     fail under uncertainty     │
└────────┬───────────────┘       │  5. TRMs train on the gap     │
         │                       │                                │
         ↓                       │  NO callbacks to D365 during   │
┌────────────────────────┐       │  Monte Carlo — pure math       │
│  D365 Planned Orders   │       └────────────────┬───────────────┘
│  (deterministic)       │                        │
│                        │                        ↓
│  Standard D365         │       ┌────────────────────────────────┐
│  approval workflow     │       │  Autonomy Decisions            │
│                        │       │  • Probabilistic BSC           │
└────────────────────────┘       │  • Conformal intervals         │
                                 │  • 11 TRM agents (<10ms)       │
                                 │  • GNN network optimization    │
                                 │  • Decision Stream + Override  │
                                 │    learning feedback loop      │
                                 └────────────────────────────────┘
```

**Key insight**: This is the same architecture across all ERP forks — SAP (mirrors `MARC`/`MDLV` parameters), D365 (mirrors `ReqItemTable` coverage codes), Odoo (mirrors `stock.warehouse.orderpoint` rules). The digital twin is ERP-agnostic in concept — only the **config extraction layer** changes per ERP. The in-memory simulation math (netting, BOM explosion, coverage code logic, lead time offsetting) is the same regardless of source ERP.

Over time, as trust builds, customers shift decision authority from D365's deterministic plans to Autonomy's agent-driven plans. The deterministic baseline becomes a safety net, not the primary decision path.

---

## 9. Common vs Fork Code Matrix

### Summary Table

| Layer | Total LOC | Common | Adapt | Rewrite | Drop |
|-------|----------|--------|-------|---------|------|
| **Models** | 36,029 | 11,000 (31%) | 10,000 (28%) | 15,000 (41%) | 0 |
| **Planning Services** | 6,424 | 685 (11%) | 1,500 (23%) | 4,239 (66%) | 0 |
| **Powell / TRM / GNN** | 56,927 | 35,000 (62%) | 10,000 (17%) | 12,000 (21%) | 0 |
| **Other Services** | 136,465 | 60,000 (44%) | 40,000 (29%) | 30,000 (22%) | 6,465 (5%) |
| **API Endpoints** | 75,112 | 25,000 (33%) | 22,000 (29%) | 23,000 (31%) | 5,112 (7%) |
| **Integrations** | 14,232 | 0 (0%) | 0 (0%) | 3,000 (21%) | 11,232 (79%) |
| **Frontend** | 179,833 | 20,000 (11%) | 85,000 (47%) | 65,000 (36%) | 10,000 (6%) |
| **main.py + config** | 23,598 | 5,000 (21%) | 10,000 (42%) | 8,598 (37%) | 0 |
| **TOTAL** | **528,620** | **156,685 (30%)** | **178,500 (34%)** | **160,837 (30%)** | **32,809 (6%)** |

### Interpretation

| Category | LOC | % | Meaning |
|----------|-----|---|---------|
| **Common** (shared across forks) | 156,685 | **30%** | AI engine, decision framework, training pipelines |
| **Adapt** (minor changes, same logic) | 178,500 | **34%** | Field name swaps, API URL changes, component restyling |
| **Rewrite** (new implementation) | 160,837 | **30%** | Data model, engines, planning, UI framework |
| **Drop** (not needed in D365 fork) | 32,809 | **6%** | ERP integrations, staging schemas |

### What "Adapt" Really Means

"Adapt" work ranges from trivial to moderate:
- **Trivial** (~40% of adapt): Import path changes, field name renames, component prop swaps
- **Moderate** (~40% of adapt): API response shape changes, query rewrites for D365 entities
- **Significant** (~20% of adapt): Logic changes for D365 dimensional model (`InventDim`), auth flow changes

Realistically, "adapt" work takes ~30% of the effort of "rewrite" work. So effective new-code effort is:

```
Effective effort = Rewrite (160K LOC) + 0.3 × Adapt (178K LOC) = ~214K LOC equivalent
```

---

## 10. Effort Estimates

### Team Composition

| Role | Count | Focus |
|------|-------|-------|
| D365 F&O Developer (X++) | 1 | D365 extension package, data entities, virtual entities |
| Backend Engineer (Python) | 2 | Data model rewrite, engine adaptation, API changes |
| Frontend Engineer (React + Fluent) | 1-2 | MUI → Fluent UI 9, PCF control packaging |
| Azure DevOps / Infra | 1 | AKS, Azure SQL, Azure ML, CI/CD |

### Phase Breakdown

| Phase | Duration | Deliverable |
|-------|----------|------------|
| **Phase 0 — Architecture** | 2 weeks | Adapter interface design, D365 entity mapping document, Azure architecture finalized |
| **Phase 1 — Core Adapter** | 6 weeks | `d365_entities.py`, OData client, Azure SQL schema, D365 extension package |
| **Phase 2 — Config Extraction + Heuristic Mirror** | 7 weeks | D365 config reader (extracts `ReqItemTable` coverage codes, `BOMTable` structures, `InventSum` positions once). Rewrite heuristic mirror to replicate D365's 5 coverage codes as numpy operations. Adapt deterministic engines (AATP, Buffer) to D365 table structures. Core MC math (netting, BOM explosion, lead time offsetting) is largely data-model-agnostic — rewrite is config extraction, not planning algorithm. |
| **Phase 3 — Frontend** | 8 weeks | Fluent UI 9 component library, PCF controls for key pages (Decision Stream, Planning, Admin) |
| **Phase 4 — AI/ML on Azure** | 3 weeks | Azure ML endpoints for TRM/GNN, Azure OpenAI integration, Azure AI Search for RAG |
| **Phase 5 — Digital Twin** | 4 weeks | Simulation engine reading D365 topology, stochastic distributions from D365 `ReqItemTable` |
| **Phase 6 — Integration Testing** | 4 weeks | End-to-end with D365 Contoso (USMF), provisioning pipeline, decision flow |
| **Phase 7 — AppSource Prep** | 3 weeks | Packaging, certification, documentation, security review |
| **TOTAL** | **~37 weeks (~9 months)** | |

### Effort by LOC Category

| Work Type | LOC | Engineer-Weeks | Notes |
|-----------|-----|---------------|-------|
| Common code (extract to `core/`) | 156,685 | 4 | Reorganize, not rewrite |
| Adapt code | 178,500 | 24 | ~30% of rewrite effort |
| Rewrite code | 160,837 | 64 | New implementation |
| Drop code | 32,809 | 1 | Delete and verify |
| Azure infrastructure | N/A | 12 | AKS, Azure SQL, CI/CD, monitoring |
| D365 extension package | ~3,000 (X++) | 8 | Data entities, virtual entities, business events |
| Testing & certification | N/A | 16 | Integration tests, AppSource cert |
| Documentation | ~5,000 | 4 | Updated CLAUDE.md, user guides, API docs |
| **TOTAL** | | **~133 engineer-weeks** | **~33 engineer-months** |

With a team of 5: **~7 months**. With a team of 4: **~8-9 months**.

---

## 11. Risk Analysis

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Heuristic mirroring fidelity** | Autonomy's digital twin must faithfully replicate D365's 5 coverage codes + DDMRP buffer logic + BOM explosion + time fence rules as in-memory numpy operations. If the mirror diverges from D365's actual behavior, TRM training data is poisoned. D365's Planning Optimization is a black box — coverage code edge cases (phantom BOMs, co-products, intercompany planning) may have undocumented behavior. | Start with the 3 most common coverage codes (min/max, lot-for-lot, period). Validate mirror output against Planning Optimization's deterministic run for the same inputs. Add coverage codes incrementally with regression tests. Budget 2 extra weeks for validation. |
| **D365 F&O API limitations** | OData has 10K row limits, no streaming, limited filter expressions. High-volume planning queries may be slow. | Use Dual-Write to Dataverse for hot data; batch extractions for cold data. Cache aggressively. |
| **D365 version fragmentation** | Customers on different D365 update waves (10.0.x). Data entities may differ. | Pin to minimum supported version; use feature detection, not version detection. |
| **InventDim complexity** | Every inventory query needs dimensional context. Pervasive impact across engines, simulation, planning. | Build a robust `InventDimResolver` utility used everywhere. Budget 2 extra weeks. |
| **PCF control packaging** | PCF has bundle size limits, runtime restrictions, and sandboxing. Complex React pages may not fit. | Build PCF for key surfaces only; full admin UI as standalone Power App. |
| **Two-database architecture** | Joins across D365 Azure SQL and Autonomy Azure SQL are impossible. All cross-DB data must be materialized. | Design clean API boundaries. No cross-DB joins. Dual-Write for sync. |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Azure OpenAI capacity** | Regional quota limits; GPT-4o may have queue delays during peak. | Use PTU (Provisioned Throughput Units) for production; GPT-4o-mini for high-volume Skills calls. |
| **D365 extension model constraints** | Cannot override standard D365 behavior (sealed model). May limit deep integration. | Work within extension points; use business events for triggers; PCF for UI. |
| **SOC II on Azure** | Different audit tooling, different evidence collection. | Azure has strong SOC II tooling (Compliance Manager, Defender). May be easier, not harder. |
| **Skill transfer** | Team needs D365 F&O + X++ expertise (rare skill set). | Hire one dedicated D365 developer; others work in Python/React (transferable). |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **PyTorch on Azure** | Azure ML fully supports PyTorch. No risk. | Standard deployment. |
| **PostgreSQL → Azure SQL** | SQLAlchemy supports MSSQL dialect natively. | `pip install pyodbc`; change connection string. Most queries work as-is. |
| **Claude → Azure OpenAI** | OpenAI-compatible API already used everywhere. | Change auth wrapper (~50 LOC). |

---

## 12. Recommendation

### Should You Fork?

**Yes, but not yet.** The analysis reveals that:

1. **The AI engine is well-abstracted** — 62% of the Powell framework is common code. This is the core IP and it transfers cleanly.

2. **The data model coupling is deep but concentrated** — ~160K LOC of rewrite is significant, but it's in well-understood layers (models, engines, planning services).

3. **The frontend is the biggest cost** — MUI → Fluent UI 9 across 430 files is labor-intensive but mechanically straightforward. AI-assisted code migration could accelerate this.

4. **The digital twin is an in-memory heuristic mirror** — D365's Planning Optimization runs once for the deterministic baseline. Autonomy reads `ReqItemTable` config once, replicates coverage code logic as numpy operations, and runs 1,000 MC trials in 2-5 minutes (never calling back to D365). The planning layer (~6,400 LOC) rewrites are a **config extraction + heuristic mirroring** task — the core math (netting, BOM explosion) is data-model-agnostic; only the D365 table reading layer changes. This is the same architecture as the Odoo fork (mirrors `stock.warehouse.orderpoint`) and SAP fork (mirrors `MARC`/`MDLV`).

5. **Microsoft cloud is a better SOC II story** — Azure's built-in compliance tooling is stronger than self-managed PostgreSQL.

### Recommended Approach

**Phase 0 (Now, 2 weeks)**: Extract `core/` — refactor the Powell framework, TRM/GNN models, conformal prediction, and causal AI into a data-model-agnostic package. This benefits both forks and de-risks the eventual split.

**Phase 1 (When ready, 9 months)**: Execute the D365 fork with a team of 4-6.

**Phase 2 (Post-launch)**: Maintain both forks from a shared `core/` monorepo. Common AI improvements benefit both.

### Alternative: D365 Integration (Not Fork) — Cheaper Path

Before committing to a full fork, consider the **existing D365 integration architecture** already in the codebase (42 entities mapped, OData connector built, field mapping service complete). This provides:

- D365 data flows into Autonomy via staging → AWS SC mapping
- Autonomy runs its full AI stack on the AWS SC model
- Decisions flow back to D365 via OData writes

**Cost**: Already ~80% built. Remaining: ~2-3 weeks of backend + 1 week frontend.
**Trade-off**: Not "D365 native" — it's an external app that integrates with D365, not an embedded experience.

The fork provides the **embedded D365 experience** (PCF controls, Fluent UI, AppSource listing, Azure-native deployment). The integration provides the **same AI value** at 1/20th the cost. The business question is: does the D365 native UX justify the 9-month investment?

---

## Appendix A: D365 Entity Registry (Already Implemented)

The codebase already contains a complete D365 entity registry in `backend/app/models/d365_staging.py` with 42 entities:

**Master (24)**: LegalEntities, Sites, Warehouses, StorageLocations, ReleasedProductsV2, ProductUnitConversions, ProductCategories, Vendors, CustomersV3, CustomerSalesAreas, VendorPurchasePrices, ApprovedVendorList, BillOfMaterialsHeaders, BillOfMaterialsLines, WorkCenters, RoutingHeaders, RoutingOperations, CapacityData, InventWarehouseOnHandEntity, ItemCoverageSettings, BatchMaster, DemandForecastEntries, TransportationRoutes, CalendarTable

**Transaction (11)**: PurchaseOrderHeadersV2, PurchaseOrderLinesV2, PurchaseOrderScheduleLines, PurchaseRequisitionLines, SalesOrderHeadersV2, SalesOrderLinesV2, SalesOrderDeliverySchedules, ProductionOrderHeaders, ProductionOrderItems, ProductionOrderBOMLines, ProductionRouteOperations, PlannedOrders, ShipmentHeaders, ShipmentLines

**CDC (7)**: PurchaseOrderReceiptJournal, ProductionOrderConfirmations, QualityOrders, QualityTestResults, QualityNotifications, MaintenanceAssets, ObjectStatusHistory

## Appendix B: Existing D365 Code Assets

| Asset | File | LOC | Status |
|-------|------|-----|--------|
| D365 Staging Model | `backend/app/models/d365_staging.py` | 194 | Complete |
| D365 OData Connector | `backend/app/integrations/d365/connector.py` | 471 | Complete |
| D365 Field Mapping (227 mappings) | `backend/app/integrations/d365/field_mapping.py` | 361 | Complete |
| D365 Extraction Service | `backend/app/integrations/d365/extraction_service.py` | 584 | Complete |
| D365 Config Builder | `backend/app/integrations/d365/config_builder.py` | ~400 | Complete |
| Contoso Extraction Script | `scripts/extract_d365_contoso.py` | 256 | Complete |
| Contoso Config Rebuild Script | `scripts/rebuild_d365_contoso_config.py` | 703 | Complete |
| SAP → D365 Translator | `scripts/translate_sap_to_d365_csvs.py` | ~500 | Complete |
| D365 Integration Guide | `docs/external/D365_INTEGRATION_GUIDE.md` | 100+ | Complete |
| D365 Auth Guide | `docs/internal/D365_USER_AUTHORIZATION_GUIDE.md` | 100+ | Complete |
| Migration (staging tables) | `backend/migrations/versions/20260318_d365_odoo_staging.py` | ~200 | Complete |
| Frontend ERP Management | `frontend/src/pages/admin/ERPDataManagement.jsx` | ~800 | D365 tab exists |
| **TOTAL EXISTING** | | **~4,000** | **Ready to build on** |

## Appendix C: Azure OpenAI Model Mapping

| Current Usage | Current Model | Azure OpenAI Equivalent | API Change |
|--------------|--------------|------------------------|------------|
| Skills (calculation) | Claude Haiku | **GPT-4o-mini** | Auth only |
| Skills (judgment) | Claude Sonnet | **GPT-4o** | Auth only |
| Azirella parsing | Qwen 3 8B (vLLM) | **GPT-4o-mini** | Auth only |
| Email classification | Qwen 3 8B (vLLM) | **GPT-4o-mini** | Auth only |
| Executive briefing | Qwen 3 8B (vLLM) | **GPT-4o** | Auth only |
| Synthetic data wizard | Qwen 3 8B (vLLM) | **GPT-4o** | Auth only |
| Embeddings (RAG) | pgvector + local | **Azure AI Search** + `text-embedding-3-large` | Medium rewrite |
| TRM agents | PyTorch (local) | **PyTorch (Azure ML)** | Deploy config only |
| GNN models | PyTorch (local) | **PyTorch (Azure ML)** | Deploy config only |

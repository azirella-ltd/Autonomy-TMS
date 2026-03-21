# SAP-S4HANA-FORK.md — SAP S/4HANA Native Fork Analysis

**Date**: 2026-03-21
**Status**: Investigation / Decision Document
**Author**: Claude Code analysis of Autonomy codebase (528K LOC, 1,144 files)
**Cross-references**: [DIGITAL_TWIN.md §0](docs/internal/DIGITAL_TWIN.md) (in-memory heuristic mirror architecture), [D365-FORK.md](D365-FORK.md) (companion analysis)

---

## Executive Summary

This document assesses the effort to create an **SAP S/4HANA native fork** of the Autonomy platform. "Native" means:

1. **Data model**: Replace AWS Supply Chain Data Model with S/4HANA native tables (`MARC`, `MARA`, `STKO`, `EKKO`, `VBAK`, etc.) and CDS Views
2. **UI**: Replace React + Material-UI with React + `@ui5/webcomponents-react` (Fiori-compliant, SAP Horizon theme)
3. **Database**: Replace PostgreSQL with SAP HANA Cloud (for S/4HANA data) + PostgreSQL or HANA for Autonomy's own tables
4. **AI/LLM**: Replace Claude API / vLLM with SAP AI Core Generative AI Hub (which supports Anthropic, OpenAI, Mistral)
5. **Deployment**: SAP BTP Kyma (Kubernetes) + SAP AI Core, listed on SAP Store

**Bottom line**: Autonomy already has **16,671 LOC of SAP-specific integration code** (connector, data mapper, field mapping, config builder) — more than any other ERP. The SAP fork benefits from this head start but still requires ~35% rewrite for native data model conversion. The fork is a **7-8 month effort for a team of 4-5 engineers**.

**Key advantage over D365 fork**: SAP officially supports React via `@ui5/webcomponents-react`, making the frontend migration a component-library swap rather than a framework rewrite. And SAP AI Core's Gen AI Hub already supports Anthropic (Claude), so the LLM migration is trivial.

---

## Table of Contents

1. [Existing SAP Code Assets](#1-existing-sap-code-assets)
2. [Data Model: AWS SC vs S/4HANA](#2-data-model-aws-sc-vs-s4hana)
3. [Fork Architecture](#3-fork-architecture)
4. [Layer-by-Layer Analysis](#4-layer-by-layer-analysis)
5. [Technology Stack Migration](#5-technology-stack-migration)
6. [SAP BTP Deployment](#6-sap-btp-deployment)
7. [AI Migration: Claude → SAP AI Core](#7-ai-migration-claude--sap-ai-core)
8. [SAP IBP Competitive Overlap](#8-sap-ibp-competitive-overlap)
9. [In-Memory Heuristic Mirror (Digital Twin)](#9-in-memory-heuristic-mirror-digital-twin)
10. [Common vs Fork Code Matrix](#10-common-vs-fork-code-matrix)
11. [Effort Estimates](#11-effort-estimates)
12. [Risk Analysis](#12-risk-analysis)
13. [Recommendation](#13-recommendation)

---

## 1. Existing SAP Code Assets

Autonomy already has the most mature ERP integration for SAP. This is a significant head start.

### Code Inventory

| Asset | File | LOC | Status |
|-------|------|-----|--------|
| SAP S/4HANA RFC Connector | `backend/app/integrations/sap/s4hana_connector.py` | 1,707 | Complete |
| SAP Data Mapper (8 entity types) | `backend/app/integrations/sap/data_mapper.py` | 3,169 | Complete |
| SAP APO Connector (40+ tables) | `backend/app/integrations/sap/apo_connector.py` | 841 | Complete |
| SAP ATP Bridge (bidirectional) | `backend/app/integrations/sap/sap_atp_bridge.py` | 1,159 | Complete |
| SAP Plan Writer (MO/TO/PO write-back) | `backend/app/integrations/sap/plan_writer.py` | 656 | Complete |
| SAP Schema Validator (Claude AI) | `backend/app/integrations/sap/schema_validator.py` | 650 | Complete |
| SAP Delta Loader (hash/date-based CDC) | `backend/app/integrations/sap/delta_loader.py` | 540 | Complete |
| SAP Intelligent Loader (unified) | `backend/app/integrations/sap/intelligent_loader.py` | 511 | Complete |
| SAP CSV Loader (folder watching) | `backend/app/integrations/sap/csv_loader.py` | 465 | Complete |
| OData/HANA/RFC Extractors | `backend/app/integrations/sap/extractors.py` | 1,242 | Complete |
| SAP Config Builder (8-step pipeline) | `backend/app/services/sap_config_builder.py` | 3,762 | Complete |
| SAP Field Mapping (3-tier, AI-assisted) | `backend/app/services/sap_field_mapping_service.py` | 1,823 | Complete |
| SAP Staging Model (62 tables) | `backend/app/models/sap_staging.py` | ~500 | Complete |
| HANA Extraction Script | `scripts/extract_sap_hana.py` | ~400 | Complete |
| IDES Extraction Script | `scripts/extract_sap_ides.py` | ~400 | Complete |
| CSV Ingestion Script | `scripts/ingest_sap_csvs.py` | ~300 | Complete |
| Config Rebuild Script | `scripts/rebuild_sap_config_disaggregated.py` | ~700 | Complete |
| SAP Integration Guide | `docs/external/SAP_INTEGRATION_GUIDE.md` | 77KB | Complete |
| SAP Demo Guide | `docs/internal/SAP_DEMO.md` | 55KB | Complete |
| SAP AI Integration Guide | `docs/internal/SAP_AI_INTEGRATION_GUIDE.md` | 21KB | Complete |
| SAP Authorization Guide | `docs/internal/SAP_USER_AUTHORIZATION_GUIDE.md` | 36KB | Complete |
| Frontend ERP Management | `frontend/src/pages/admin/ERPDataManagement.jsx` | ~800 | SAP tab exists |
| **TOTAL EXISTING** | | **~19,600** | **Production-ready** |

### Connection Methods (All Implemented)

| Method | Library | Use Case | Status |
|--------|---------|----------|--------|
| RFC | pyrfc (NW RFC SDK) | Real-time S/4HANA extraction | ✅ |
| OData v2/v4 | httpx (async) | REST API extraction | ✅ |
| Direct SQL | hdbcli | SAP HANA native queries | ✅ |
| CSV | pandas | Batch file-based extraction | ✅ |
| Cloud Connector | — | On-prem to BTP bridge | ⚠️ Referenced, not integrated |

### SAP Table Registry (62 Tables)

- **Master Data (30)**: T001, T001W, T001L, ADRC, MARA, MAKT, MARC, MARD, MARM, MBEW, MVKE, MAST, KNA1, KNVV, LFA1, STKO, STPO, EORD, EINA, EINE, EBAN, CRHD, EQUI, PLKO, PLPO, PBIM, PBED, PLAF, T179, KAKO
- **Transaction Data (21)**: VBAK, VBAP, VBEP, VBUK, VBUP, EKKO, EKPO, EKET, AFKO, AFPO, AFVC, AUFK, LIKP, LIPS, LTAK, LTAP, RESB, QMEL, QALS, QASE, KONV
- **CDC (11)**: MSEG, MKPF, EKBE, AFRU, JEST, TJ02T, MCH1, MCHA, CDHDR, CDPOS, CRCO

---

## 2. Data Model: AWS SC vs S/4HANA

### S/4HANA Simplified Data Model (vs ECC)

S/4HANA introduced significant data model changes from ECC:

| Change | ECC | S/4HANA |
|--------|-----|---------|
| Material Documents | `MKPF` (header) + `MSEG` (items) | **`MATDOC`** (single table, INSERT-only) |
| Financial Postings | 20+ aggregate tables | **`ACDOCA`** (Universal Journal) |
| MRP Results | `MDKP` + `MDTB` (batch MRP) | **`PPH_*`** tables (MRP Live, real-time) |
| Stock Aggregates | `MARD`, `MCHB` stored quantities | CDS Views compute on-the-fly from `MATDOC` |
| API Layer | Direct table SELECT | **CDS Views** (e.g., `I_MaterialDocument`) |

**Implication**: The existing `sap_staging` schema with 62 ECC-compatible tables needs extension for S/4HANA-specific tables (`MATDOC`, `PPH_*`) and CDS View extraction.

### Entity Mapping (35 AWS SC → S/4HANA Equivalents)

| AWS SC Entity | S/4HANA Table(s) | Complexity |
|---------------|------------------|------------|
| `Product` | `MARA` + `MAKT` + `MARM` | Low (well-mapped already) |
| `ProductHierarchy` | `T179` (product hierarchy) | Low |
| `ProductBom` | `STKO` + `STPO` (versioned) | Medium (BOM versioning) |
| `Site` | `T001W` (plants) + `T001L` (storage locations) | Low (already mapped) |
| `TransportationLane` | Custom / `LTAK` + transport planning tables | High (no direct SAP equivalent) |
| `TradingPartner` | `KNA1` (customers) + `LFA1` (vendors) | Medium (split into two tables) |
| `Forecast` | `PBIM` + `PBED` (PIR) / IBP export | Medium |
| `InvPolicy` | **`MARC`** (MRP fields: DISMM, DISLS, MINBE, EISBE, etc.) | **HIGH** (critical for heuristic mirror) |
| `InvLevel` | `MARD` or `MATDOC_EXTRACT` (S/4HANA) | Medium (dimensional stock) |
| `SourcingRules` | `EORD` (source list) + `EINA`/`EINE` (purchase info) | Medium |
| `SupplyPlan` | `PLAF` (planned orders) / `PPH_*` (MRP Live) | High (different for ECC vs S/4HANA) |
| `InboundOrder` | `EKKO` + `EKPO` | Low (already mapped) |
| `OutboundOrder` | `VBAK` + `VBAP` | Low (already mapped) |
| `Shipment` | `LIKP` + `LIPS` | Low (already mapped) |
| `Company` | `T001` (company codes) | Low |
| `Geography` | `ADRC` (addresses) | Low |
| `ProductionProcess` | `PLKO` + `PLPO` (routings) | Medium |
| `ConsensusDemand` | Custom (no native SAP table) | High |

### MARC — The Critical Table for Heuristic Mirroring

`MARC` is the per-material-plant configuration table that controls all MRP behavior. These fields define the heuristics that the digital twin must mirror:

| MARC Field | Meaning | Current Status in Autonomy |
|-----------|---------|---------------------------|
| `DISMM` | MRP Type (VB=reorder point, VM=forecast-based, PD=deterministic, ND=no planning) | ❌ Extracted but NOT persisted to `inv_policy` |
| `DISLS` | Lot Sizing (EX=lot-for-lot, FX=fixed, HB=replenish-to-max, WB=weekly) | ❌ Extracted but NOT persisted |
| `MINBE` | Reorder Point | ✅ Mapped to `inv_policy.reorder_point` |
| `EISBE` | Safety Stock | ✅ Mapped to `inv_policy.ss_quantity` |
| `MABST` | Order-Up-To Level | ✅ Mapped to `inv_policy.order_up_to_level` |
| `LOSGR` | Fixed Lot Size | ❌ Extracted but NOT persisted |
| `BSTMI`/`BSTMA` | Min/Max Lot Size | ❌ Extracted but NOT persisted |
| `PLIFZ` | Planned Delivery Time | ✅ Mapped to lead time |
| `DZEIT` | In-House Production Time | ✅ Mapped to lead time |
| `VRMOD` | Consumption Mode (forward/backward/both) | ❌ Extracted but NOT persisted |
| `VINT1`/`VINT2` | Forward/Backward Consumption Periods | ❌ Extracted but NOT persisted |
| `FXHOR` | Planning Time Fence | ❌ Extracted but NOT persisted |
| `BESKZ` | Procurement Type (E=in-house, F=external) | ✅ Used for make-vs-buy |
| `SHZET` | Safety Time (days) | ❌ Extracted but NOT persisted |

**Gap**: The data mapper extracts these fields into a DataFrame, but `inv_policy` doesn't have columns to store `mrp_type`, `lot_size_procedure`, `consumption_mode`, or `planning_time_fence`. The digital twin therefore runs **generic ROP logic** regardless of what SAP's MARC says.

**For the S/4HANA fork**: These fields would be stored natively on the S/4HANA data model entities (no mapping needed — they ARE the native tables). The heuristic mirror would read `MARC.DISMM` directly and branch on MRP type.

---

## 3. Fork Architecture

### Proposed Repository Structure

```
autonomy/                          # Shared monorepo with build-time selection
├── core/                          # COMMON — data-model-agnostic
│   ├── ai/                        # TRM neural networks, GNN models
│   ├── powell/                    # Powell SDAM framework (abstract)
│   ├── skills/                    # Claude Skills / SAP AI Core Skills
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
│   └── s4hana/                    # NEW: S/4HANA native adapter
│       ├── models/                # S/4HANA table mappings (CDS Views or RFC)
│       ├── engines/               # MRP/AATP/Buffer reading MARC/MARD/STKO directly
│       ├── planning/              # Own planning engine mirroring MARC heuristics as numpy
│       ├── simulation/            # Digital twin (S/4HANA topology via MARC)
│       └── connector/             # RFC/OData/HANA connector (ALREADY EXISTS — 11,086 LOC)
│
├── frontends/
│   ├── react-mui/                 # Current: React + Material-UI
│   └── react-fiori/              # NEW: React + @ui5/webcomponents-react (Fiori Horizon theme)
│
└── deployment/
    ├── docker-compose/            # Current: Docker + PostgreSQL
    └── sap-btp/                   # NEW: Kyma (K8s) + HANA Cloud + AI Core
```

### Data Flow in S/4HANA Fork

```
S/4HANA (HANA DB) — Source of Truth for master data
    ↓ RFC / OData / CDS Views / HANA SQL (READ — already implemented)
Autonomy S/4HANA Adapter
    ├── Reads MARC config once (DISMM, DISLS, MINBE, EISBE, VRMOD, etc.)
    ├── Mirrors MRP heuristics as in-memory math:
    │   ├── DISMM=VB → Reorder Point logic
    │   ├── DISMM=VM → Forecast-based netting
    │   ├── DISMM=PD → Deterministic MRP
    │   ├── DISLS=EX → Lot-for-lot
    │   ├── DISLS=FX → Fixed lot size (LOSGR)
    │   ├── DISLS=HB → Replenish-to-max (MABST)
    │   └── DISLS=WB → Weekly batching
    ├── Runs 1,000 MC trials in 2-5 min (never calls SAP during sim)
    ↓ (extracts state → dataclass abstractions)
┌─────────────────────────────────────────┐
│         COMMON ENGINE (unchanged)        │
│  Monte Carlo Planning Engine (own)       │
│  TRM Agents → GNN Models → Conformal    │
│  Hive Signals → Decision Cycle → AAP    │
│  Skills → Causal AI → Override Tracking  │
└─────────────────────────────────────────┘
    ↓ (decisions as dataclass outputs)
S/4HANA Adapter (writes back to SAP)
    ↓ RFC / OData — plan_writer.py (ALREADY EXISTS)
S/4HANA (executes: PO via EKKO, MO via AFKO, TO via LTAK)

Note: SAP's native MRP (MD01/MD02 or MRP Live) runs INDEPENDENTLY.
Autonomy mirrors MARC heuristics in-memory for stochastic simulation.
See DIGITAL_TWIN.md §0 for the cross-ERP architectural principle.
```

---

## 4. Layer-by-Layer Analysis

### Layer 1: Data Models (36,029 LOC, 138 files)

| Component | LOC | Fork Status | Notes |
|-----------|-----|-------------|-------|
| `sc_entities.py` (34 AWS SC classes) | 1,832 | **REWRITE** — new `s4hana_entities.py` using MARC/MARA/STKO/etc. | High |
| `supply_chain_config.py` (DAG topology) | 685 | **ADAPT** — S/4HANA plants/warehouses map well to DAG | Medium |
| `powell_decisions.py` (11 decision tables) | 853 | **COMMON** — string IDs, no FKs | None |
| `sap_staging.py` (62 SAP tables) | ~500 | **ADAPT** — add S/4HANA-specific tables (MATDOC, PPH_*) | Low |
| `planning_cascade.py` | 726 | **ADAPT** — S/4HANA has native planning hierarchy | Medium |
| `decision_tracking.py` | 521 | **COMMON** — generic decision flow | None |
| `decision_embeddings.py` | 386 | **COMMON** | None |
| `d365_staging.py` / `odoo_staging.py` | ~700 | **DROP** — not needed in SAP fork | None |
| All other models | ~30,000 | Mixed (55% common, 35% adapt, 10% rewrite) | Medium |

**Summary**: ~12,000 LOC rewrite, ~12,000 LOC adapt, ~12,000 LOC common.

### Layer 2: Planning Services (6,424 LOC, 12 files)

| File | LOC | Fork Status | Notes |
|------|-----|-------------|-------|
| `demand_processor.py` | 417 | **REWRITE** | S/4HANA uses `PBIM`/`PBED` (PIR), not `Forecast` |
| `inventory_target_calculator.py` | 1,319 | **PARTIAL REWRITE** | 8 policy types stay; field access changes to MARC fields |
| `net_requirements_calculator.py` | 1,152 | **REWRITE** | Heuristic mirror of MARC.DISMM/DISLS logic (see §9) |
| `planner.py` | 265 | **REWRITE** | Orchestrator changes for S/4HANA planning flow |
| `stochastic_sampler.py` | 685 | **COMMON** | Distribution math is data-model-agnostic |
| `execution_cache.py` | 619 | **REWRITE** | Cache S/4HANA entities via RFC/CDS |
| Others | ~1,967 | Mixed | |

> **In-Memory Heuristic Mirror** (see [DIGITAL_TWIN.md §0](docs/internal/DIGITAL_TWIN.md)):
>
> SAP's native MRP (`MD01`/`MD02` or MRP Live) runs in 30-120 seconds per run and writes to production tables (`MDKP`/`MDTB` or `PPH_*`). Running it 1,000 times for Monte Carlo is impossible (8-33 hours + data pollution).
>
> Instead, Autonomy reads `MARC` config once and mirrors the MRP heuristics as pure in-memory math:
>
> | SAP MRP Type (DISMM) | Heuristic Logic | Mirror Implementation |
> |---------------------|-----------------|----------------------|
> | VB (Reorder Point) | If inventory_position < MINBE: order(MABST - inventory_position) | `if inv_pos < rop: order(out_level - inv_pos)` |
> | VM (Forecast-Based) | Net forecast against stock, create planned orders for shortfall | `shortfall = max(0, forecast - inv_pos); order(shortfall)` |
> | VV (Forecast + Consumption) | VM + forward/backward consumption per VRMOD/VINT1/VINT2 | `consume_within_fence(fwd=VINT1, bwd=VINT2)` |
> | PD (Deterministic MRP) | Full net requirements: gross - on_hand - scheduled_receipts | `net_req = gross_demand - available` |
> | ND (No Planning) | Skip — no automatic replenishment | `order(0)` |
>
> | SAP Lot Sizing (DISLS) | Logic | Mirror |
> |------------------------|-------|--------|
> | EX (Lot-for-lot) | Order exactly what's needed | `order_qty = net_requirement` |
> | FX (Fixed lot) | Order LOSGR quantity | `order_qty = ceil(net_req / LOSGR) * LOSGR` |
> | HB (Replenish-to-max) | Order up to MABST | `order_qty = MABST - inv_pos` |
> | WB (Weekly lot) | Consolidate daily requirements into weekly orders | `order_qty = sum(daily_req[mon:fri])` |
> | TB (Daily lot) | Each day's requirement is a separate order | `order_qty = daily_req` |
>
> These are simple mathematical rules — trivial to replicate as numpy operations. The simulation engine never calls back to SAP during Monte Carlo. 1,000 trials complete in 2-5 minutes.

### Layer 3: Powell Framework — TRM Agents (56,927 LOC, 94 files)

Same analysis as D365 fork — the Powell framework is well-abstracted:

| Component | LOC | Fork Status | Why |
|-----------|-----|-------------|-----|
| 11 TRM neural networks | ~7,000 | **COMMON** | Consume `np.ndarray`, not ORM objects |
| 3 GNN models | ~5,000 | **COMMON** | PyTorch Geometric tensors |
| Training pipeline | ~8,000 | **COMMON** | `TrainingRecord` tuples, abstract |
| Site Agent orchestration | ~4,000 | **COMMON** | Config-driven, string IDs |
| Hive signals / coordination | ~8,000 | **COMMON** | Pure signal propagation |
| Decision cycle / AAP | ~3,000 | **COMMON** | Abstract agent roles |
| Deterministic engines | ~5,000 | **REWRITE** | Must query MARC/MARD/STKO instead of AWS SC |
| Outcome collector | 1,255 | **ADAPT** | Join with S/4HANA entities for actual outcomes |
| Simulation / seeder | ~5,000 | **REWRITE** | Digital twin reads MARC topology |
| Decision reasoning | 1,094 | **ADAPT** | Display strings reference MARA.MAKTX instead of Product.description |
| Other | ~9,500 | Mixed | |

**Summary**: ~35,000 LOC common (62%), ~10,000 LOC adapt (17%), ~12,000 LOC rewrite (21%).

### Layer 4: API Endpoints (75,112 LOC, 132 files)

| Category | LOC (est.) | Fork Status | Notes |
|----------|-----------|-------------|-------|
| Planning endpoints | ~15,000 | **REWRITE** | Response shapes change for S/4HANA entities |
| Powell/Decision endpoints | ~20,000 | **COMMON** | Entity-agnostic |
| Auth/Admin endpoints | ~10,000 | **ADAPT** | SAP IAS / XSUAA replaces JWT |
| Config endpoints | ~8,000 | **ADAPT** | S/4HANA plants/warehouses map to existing DAG concepts |
| Simulation endpoints | ~5,000 | **ADAPT** | Same concepts, different entity backing |
| ERP integration endpoints | ~5,000 | **ADAPT** | Already SAP-native (RFC/OData) — just expose directly |
| Other endpoints | ~12,000 | Mixed | |

### Layer 5: Frontend (179,833 LOC, 430 files)

**Key advantage**: SAP officially provides `@ui5/webcomponents-react` — a React wrapper around Fiori web components. This means the frontend migration is a **component library swap within React**, not a framework rewrite.

| Current | SAP Fork | Notes |
|---------|----------|-------|
| `@mui/material` 5.13 | `@ui5/webcomponents-react` 2.x | Component-by-component swap |
| `@mui/icons-material` | `@ui5/webcomponents/icons` | Icon set change |
| `@radix-ui/*` (common/) | Drop — UI5 Web Components replaces | Simplifies stack |
| `@chakra-ui/react` | Drop — UI5 replaces | Removes dependency |
| `@emotion/react` (CSS-in-JS) | UI5 CSS custom properties (Horizon theme) | Simpler theming |
| Recharts | Recharts (stays — framework-agnostic) | No change |
| D3 / D3-Sankey | D3 (stays — framework-agnostic) | No change |

| Category | LOC (est.) | Fork Status | Notes |
|----------|-----------|-------------|-------|
| Planning pages (66) | 36,229 | **ADAPT** | Swap MUI → UI5 Web Components + S/4HANA field names |
| Admin pages (40) | ~22,000 | **PARTIAL REWRITE** | SAP Data Management already has UI; others adapt |
| Decision Stream / Worklists | ~15,000 | **ADAPT** | Entity-agnostic; restyle to Fiori Horizon |
| Common components (32) | ~8,000 | **REWRITE** | MUI → UI5 Web Components library |
| Scenario / Beer Game | ~18,000 | **ADAPT** | Learning tenant concept stays |
| Charts / Visualization | ~12,000 | **COMMON** | Recharts/D3 unchanged |
| Supply chain config UI | ~10,000 | **ADAPT** | S/4HANA plants/warehouses map to existing DAG builder |
| API services | ~3,000 | **ADAPT** | Endpoint URLs change slightly |
| Other | ~55,000 | Mixed | |

**Summary**: ~27,000 LOC common (15%), ~100,000 LOC adapt (56%), ~43,000 LOC rewrite (24%), ~10,000 LOC drop (5%).

**Frontend is easier than D365** because React→React (just component library swap) vs React→PCF controls (framework packaging change).

---

## 5. Technology Stack Migration

### Database: PostgreSQL → HANA Cloud + PostgreSQL Hybrid

| Current | SAP Fork | Migration Complexity |
|---------|----------|---------------------|
| PostgreSQL (transactional) | **HANA Cloud** (S/4HANA data) + **PostgreSQL on BTP** (Autonomy tables) | **MEDIUM** |
| SQLAlchemy 2.0 ORM | SQLAlchemy (PostgreSQL dialect for Autonomy) + RFC/CDS for S/4HANA | **LOW** (keep Autonomy tables on PG) |
| pgvector (RAG embeddings) | **HANA Vector Engine** (2024 GA) or keep pgvector | **MEDIUM** |
| pgaudit (SOC II) | HANA audit logging + SAP Data Custodian | **LOW** |
| RLS (tenant isolation) | HANA analytic privileges + existing RLS on PG | **LOW** |

**Pragmatic recommendation**: SAP's own CAP framework validates PostgreSQL as a development and even production database. Keep Autonomy's own tables (Powell decisions, embeddings, TRM checkpoints, audit logs) on PostgreSQL. Read S/4HANA data via RFC/OData/CDS Views. Write back decisions via `plan_writer.py` (already implemented).

This avoids the cost and complexity of a full HANA migration while still being "S/4HANA native" in terms of data model and UI.

### Frontend: Material-UI → UI5 Web Components for React

```jsx
// Current (MUI)
import { Button, Card, Table } from '@mui/material';

// SAP Fork (UI5 Web Components for React)
import { Button, Card, Table } from '@ui5/webcomponents-react';
```

The API is similar but not identical — props and event handling differ. This is mechanical work across 430 files.

---

## 6. SAP BTP Deployment

### Reference Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      SAP Fiori Launchpad                         │
│                 (Tile: "Autonomy Decision Intelligence")         │
└──────────────────────┬───────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────────┐
        ↓              ↓                  ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  React App   │ │  BTP Kyma    │ │  SAP AI Core         │
│  (UI5 Web    │ │  (K8s)       │ │  (ML Platform)       │
│  Components) │ │              │ │                      │
│              │ │  - FastAPI   │ │  - TRM inference     │
│  Hosted on   │ │  - Powell    │ │  - GNN inference     │
│  BTP static  │ │  - Engines   │ │  - Training jobs     │
│  content     │ │  - CDC jobs  │ │  - Gen AI Hub        │
│              │ │              │ │    (Claude/GPT)      │
└──────┬───────┘ └──────┬───────┘ └────────┬─────────────┘
       │                │                   │
       ↓                ↓                   ↓
┌──────────────────────────────────────────────────────────────────┐
│                     SAP BTP Services                             │
│                                                                  │
│  ┌────────────┐  ┌─────────────┐  ┌────────────────────────┐   │
│  │ PostgreSQL │  │ S/4HANA     │  │ SAP Cloud Connector    │   │
│  │ on BTP     │  │ Cloud       │  │ (on-prem S/4HANA)     │   │
│  │ (Autonomy  │  │ or          │  │                        │   │
│  │  tables)   │  │ On-Premise  │  │  RFC + OData tunnel    │   │
│  └────────────┘  └─────────────┘  └────────────────────────┘   │
│                                                                  │
│  ┌────────────┐  ┌─────────────┐  ┌────────────────────────┐   │
│  │ SAP IAS    │  │ SAP Event   │  │ Object Store           │   │
│  │ (Identity) │  │ Mesh        │  │ (checkpoints, exports) │   │
│  └────────────┘  └─────────────┘  └────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### SAP Cloud Connector (Critical for On-Premise)

Many S/4HANA customers still run on-premise. SAP Cloud Connector provides a secure tunnel from BTP to on-prem systems:

```
SAP BTP (Kyma) → SAP Cloud Connector → Customer's On-Prem S/4HANA
                 (TLS tunnel, no inbound firewall rules needed)
```

This is already referenced in `SAP_DEMO.md` but not yet implemented. It would be a critical component of the SAP fork.

### Cost Estimate (Monthly, Production)

| Service | SKU | Est. Cost/mo |
|---------|-----|-------------|
| BTP Kyma (backend, 3 pods) | Standard plan | $400 |
| SAP AI Core (inference) | Standard plan | $300 |
| SAP AI Core (training, on-demand) | GPU hours | $100 |
| SAP AI Core Gen AI Hub (LLM calls) | Token-based | $200 |
| PostgreSQL on BTP (Hyperscaler) | Standard | $150 |
| SAP Cloud Connector | Included with BTP | $0 |
| Object Store (checkpoints) | 100GB | $5 |
| SAP IAS (identity) | Included with BTP | $0 |
| **TOTAL** | | **~$1,155/mo** |

*Cheaper than Azure (~$2,020/mo) because BTP bundles many services. S/4HANA license is the customer's cost.*

---

## 7. AI Migration: Claude → SAP AI Core

### SAP AI Core Gen AI Hub

SAP AI Core's Generative AI Hub provides a **unified API** for multiple LLM providers:

| Provider | Models Available | Status |
|----------|-----------------|--------|
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Haiku | ✅ GA |
| OpenAI | GPT-4o, GPT-4o-mini | ✅ GA |
| Google | Gemini 1.5 Pro | ✅ GA |
| Mistral | Mistral Large, Mistral Medium | ✅ GA |
| Meta | Llama 3.1 | ✅ GA |

**Key finding**: Anthropic (Claude) is already available on SAP AI Core. The SAP fork could **keep using Claude** — no LLM provider change needed. Just different auth:

```python
# Current (direct Claude API or vLLM)
client = OpenAI(base_url="http://localhost:8001/v1", api_key="not-needed")

# SAP AI Core Gen AI Hub (Claude via SAP)
from gen_ai_hub.proxy import GenAIHubProxyClient
client = GenAIHubProxyClient(model_name="anthropic--claude-3.5-sonnet")
```

**Migration effort**: ~100 LOC (auth wrapper change). Prompts, tool schemas, response parsing all stay identical.

### PyTorch Models on SAP AI Core

| Model | Size | SAP AI Core Approach |
|-------|------|---------------------|
| TRM agents (7M params, <10ms) | Small | Custom Docker container — **CPU sufficient** |
| Site tGNN (25K params, <5ms) | Tiny | Custom Docker container — CPU |
| Execution tGNN | Medium | Custom Docker container — GPU for training, CPU for inference |
| S&OP GraphSAGE | Medium | Custom Docker container — batch weekly |
| Training workloads | Variable | GPU jobs via AI Core (T4/A100) |

TRM models are small enough that inference runs on CPU, avoiding GPU cost entirely for production serving.

---

## 8. SAP IBP Competitive Overlap

### What SAP IBP Provides Natively

| IBP Module | Quality | Autonomy's Value-Add |
|-----------|---------|---------------------|
| Demand Planning | Good (statistical + ML, Croston for intermittent) | Conformal intervals, censored demand handling |
| Supply Planning | Good (LP/MIP solvers, constraint-based) | Stochastic planning with Monte Carlo |
| Inventory Optimization | Good (**MEIO** — multi-echelon, mathematically optimal) | 8 policy types including conformal and econ_optimal |
| S&OP | Good (consensus workflows, Joule Q&A) | Agent-based autonomous S&OP with AAP negotiation |
| Response & Supply | Good (short-term execution) | 11 TRM agents at <10ms, Decision Stream |
| DDMRP | Good (native in S/4HANA, free) | InventoryBufferTRM for buffer optimization |

### Where Autonomy is Unique (No IBP Equivalent)

| Capability | IBP Has? |
|-----------|----------|
| 11 autonomous TRM agents (<10ms execution) | No (Joule is advisory, not autonomous) |
| GNN network optimization (GraphSAGE + tGNN + Site tGNN) | No |
| Conformal prediction (distribution-free uncertainty) | No (traditional confidence intervals only) |
| 3-tier causal inference (counterfactual, propensity matching, Bayesian) | No |
| Override learning (Bayesian posteriors on human decisions) | No |
| Urgency/Likelihood/Benefit decision routing | No (basic workflow approvals only) |
| Stigmergic Hive coordination (signal bus, urgency vectors) | No |
| In-memory digital twin (2-5 min for 1,000 MC trials) | No |
| AAP cross-functional authorization at machine speed | No |

### Positioning

**Complement, not compete**: Position Autonomy as the **probabilistic/agentic layer** that sits alongside S/4HANA + IBP. Customers keep their SAP planning for deterministic MRP; Autonomy adds the uncertainty quantification, autonomous agents, and causal learning that SAP doesn't provide.

For customers **without IBP** (majority of mid-market S/4HANA): Autonomy provides advanced planning capabilities at a fraction of IBP's cost.

---

## 9. In-Memory Heuristic Mirror (Digital Twin)

See [DIGITAL_TWIN.md §0](docs/internal/DIGITAL_TWIN.md) for the full cross-ERP architectural principle.

**SAP-specific summary**: The digital twin reads `MARC` config once via RFC/OData, replicates the MRP heuristics (5 MRP types × 6 lot sizing procedures = 30 combinations) as pure in-memory math, runs 1,000 stochastic trials in 2-5 minutes, and never calls SAP during simulation.

**Current gap**: The simulation (`_SimSite.compute_replenishment_order()`) uses generic ROP logic regardless of `MARC.DISMM`. The S/4HANA fork would implement all 5 MRP types and 6 lot sizing procedures as separate math functions, selectable per material-plant based on the extracted MARC config.

**Validation strategy**: Run the mirror with deterministic inputs (zero variance) and compare output against SAP's deterministic MRP run (`MD04` stock/requirements list) for the same material-plant. Discrepancies indicate mirror bugs.

---

## 10. Common vs Fork Code Matrix

| Layer | Total LOC | Common | Adapt | Rewrite | Drop |
|-------|----------|--------|-------|---------|------|
| **Models** | 36,029 | 12,000 (33%) | 12,000 (33%) | 12,000 (33%) | 0 |
| **Planning Services** | 6,424 | 685 (11%) | 1,500 (23%) | 4,239 (66%) | 0 |
| **Powell / TRM / GNN** | 56,927 | 35,000 (62%) | 10,000 (17%) | 12,000 (21%) | 0 |
| **Other Services** | 136,465 | 65,000 (48%) | 38,000 (28%) | 27,000 (20%) | 6,465 (4%) |
| **API Endpoints** | 75,112 | 25,000 (33%) | 30,000 (40%) | 15,000 (20%) | 5,112 (7%) |
| **Integrations** | 14,232 | 11,086 (78%) | 3,146 (22%) | 0 (0%) | 0 |
| **Frontend** | 179,833 | 27,000 (15%) | 100,000 (56%) | 43,000 (24%) | 10,000 (5%) |
| **main.py + config** | 23,598 | 5,000 (21%) | 12,000 (51%) | 6,598 (28%) | 0 |
| **TOTAL** | **528,620** | **180,771 (34%)** | **206,646 (39%)** | **119,837 (23%)** | **21,577 (4%)** |

### Comparison with D365 Fork

| Metric | D365 Fork | SAP Fork | Why Different |
|--------|-----------|----------|---------------|
| Common code | 30% | **34%** | SAP integration code (16K LOC) already exists |
| Rewrite code | 30% | **23%** | S/4HANA connector, plan writer, field mapping all exist |
| Frontend effort | 36% rewrite | **24% rewrite** | React→React (UI5 Web Components) vs React→PCF controls |
| Integration LOC to write | ~3,000 new | **~0 new** | SAP connector already complete |
| LLM migration | Claude→Azure OpenAI (different auth) | **Claude stays** (via SAP AI Core Gen AI Hub) |
| Total effort | 33 engineer-months | **~27 engineer-months** | SAP head start is significant |

**The SAP fork is ~20% less effort than the D365 fork** because of the existing 16K LOC SAP integration, the React-compatible Fiori components, and the ability to keep Claude via SAP AI Core.

---

## 11. Effort Estimates

### Team Composition

| Role | Count | Focus |
|------|-------|-------|
| SAP ABAP / BTP Developer | 1 | SAP Cloud Connector, CDS View extraction, Fiori Launchpad integration |
| Backend Engineer (Python) | 2 | Data model rewrite, heuristic mirror (MARC logic), engine adaptation |
| Frontend Engineer (React + UI5) | 1 | MUI → UI5 Web Components swap |
| DevOps / BTP | 0.5 | Kyma deployment, AI Core setup, CI/CD |

### Phase Breakdown

| Phase | Duration | Deliverable |
|-------|----------|------------|
| **Phase 0 — Architecture** | 2 weeks | Adapter interface design, MARC heuristic mirror spec, BTP architecture |
| **Phase 1 — S/4HANA Adapter** | 5 weeks | `s4hana_entities.py`, CDS View extraction (extend existing connector), S/4HANA-specific staging tables (MATDOC, PPH_*) |
| **Phase 2 — Heuristic Mirror** | 6 weeks | In-memory mirror of 5 MRP types × 6 lot sizing procedures from MARC. Validation against MD04 output. Digital twin reading S/4HANA topology. |
| **Phase 3 — Frontend** | 7 weeks | UI5 Web Components library (common/), swap across key pages, Fiori Launchpad integration |
| **Phase 4 — AI/ML on BTP** | 2 weeks | SAP AI Core for TRM/GNN serving, Gen AI Hub for Claude Skills, training pipeline |
| **Phase 5 — BTP Deployment** | 3 weeks | Kyma cluster, Cloud Connector integration, PostgreSQL on BTP, monitoring |
| **Phase 6 — Integration Testing** | 3 weeks | End-to-end with S/4HANA FAA (IDES), provisioning pipeline, decision flow, MD04 validation |
| **Phase 7 — SAP Store Prep** | 2 weeks | Packaging, ARC compliance, documentation, security review |
| **TOTAL** | **~30 weeks (~7.5 months)** | |

### Effort by Category

| Work Type | Engineer-Weeks | Notes |
|-----------|---------------|-------|
| Common code (extract to `core/`) | 4 | Reorganize, not rewrite |
| Adapt code (field swaps, restyling) | 22 | ~30% of rewrite effort |
| Rewrite code (new implementation) | 48 | New heuristic mirror, entity models, UI components |
| Drop code | 1 | Delete D365/Odoo integration code |
| BTP infrastructure | 8 | Kyma, AI Core, Cloud Connector |
| SAP BTP integration | 6 | CDS Views, Fiori Launchpad tile, XSUAA auth |
| Testing & certification | 12 | Integration tests, MD04 validation, ARC |
| Documentation | 3 | Updated guides |
| **TOTAL** | **~104 engineer-weeks** | **~26 engineer-months** |

With a team of 4.5: **~6 months**. With a team of 4: **~7-8 months**.

---

## 12. Risk Analysis

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Heuristic mirroring fidelity** | If mirror diverges from SAP's actual MRP behavior (edge cases: phantom BOMs, co-products, intercompany, special procurement keys), TRM training data is poisoned | Start with 3 most common MRP types (VB, PD, VM). Validate against MD04. Add incrementally with regression tests. |
| **S/4HANA vs ECC fragmentation** | Customers on ECC (MDKP/MDTB) vs S/4HANA (PPH_*, MATDOC). Must support both | Feature detection at runtime; existing staging already handles ECC. Add S/4HANA-specific tables. |
| **On-premise access** | Many SAP customers are on-premise. SAP Cloud Connector required for BTP access | Implement Cloud Connector integration (referenced but not yet built). Also support direct RFC for air-gapped customers. |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **SAP AI Core maturity** | GPU pricing opaque, newer platform than Azure ML | Train externally (AWS/Azure), deploy inference on AI Core. TRMs are CPU-viable. |
| **SAP Store certification** | ARC compliance process may require changes | New simplified certification framework Q3 2026. Low annual cost (~EUR 2K). |
| **BTP cost predictability** | BTP pricing is complex (service units, credits) | Start with pay-as-you-go, optimize after baseline established. |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **React + UI5 Web Components** | Officially supported by SAP. Active community. | Standard migration path. |
| **Claude on SAP AI Core** | Already GA via Gen AI Hub. | No provider change needed. |
| **Existing SAP connector** | 11,086 LOC already production-tested. | Major head start. |

---

## 13. Recommendation

### SAP Fork vs D365 Fork — Which First?

| Factor | SAP Fork | D365 Fork |
|--------|----------|-----------|
| **Existing code** | 16,671 LOC SAP integration ready | 4,000 LOC D365 integration ready |
| **Total effort** | ~26 engineer-months | ~33 engineer-months |
| **Timeline** | ~7.5 months | ~9 months |
| **Frontend** | Easier (React→React via UI5 WC) | Harder (React→PCF controls) |
| **LLM migration** | None (Claude stays via Gen AI Hub) | Required (Claude→Azure OpenAI) |
| **Market size** | Larger (S/4HANA installed base) | Growing (D365 gaining share) |
| **Competitive overlap** | IBP is strong competitor | D365 SCM less mature |
| **BTP infra maturity** | Medium (newer, less documented) | High (Azure is mature) |

**Recommendation**: Do the **SAP fork first**. It's cheaper (7.5 vs 9 months), has a larger market, and benefits from 16K LOC of existing SAP code. The shared `core/` extraction (Phase 0) benefits both forks.

### Recommended Sequence

1. **Phase 0 (Now, 2 weeks)**: Extract `core/` — refactor the Powell framework, TRM/GNN models, conformal prediction, and causal AI into a data-model-agnostic package. Benefits both forks.

2. **Phase 1 (Month 1-8)**: SAP S/4HANA fork. Team of 4-5.

3. **Phase 2 (Month 6-15, overlapping)**: D365 fork. Second team of 4-5. Starts as SAP fork nears completion, reuses `core/` and lessons learned.

4. **Ongoing**: Maintain three variants (AWS SC, S/4HANA, D365) from shared `core/` monorepo.

### Alternative: Keep Integration Architecture

The existing SAP integration (16K LOC) already provides:
- Full S/4HANA data extraction via 4 connection methods
- 62 SAP table support
- 3-tier field mapping (AI-assisted)
- Bidirectional sync (ATP bridge, plan writer)

**Cost**: Already built.
**Trade-off**: Not "SAP native" UX. No Fiori Launchpad tile. No SAP Store listing. External app feel.

The fork provides the **embedded SAP experience** (Fiori UI, Launchpad tile, SAP Store, BTP-native deployment). The integration provides the **same AI value** at near-zero additional cost. The business question: does the SAP native UX and distribution channel (SAP Store) justify the 7.5-month investment?

---

## Appendix A: SAP Table Registry (62 Tables, Already Implemented)

**Master (30)**: T001, T001W, T001L, ADRC, MARA, MAKT, MARC, MARD, MARM, MBEW, MVKE, MAST, KNA1, KNVV, LFA1, STKO, STPO, EORD, EINA, EINE, EBAN, CRHD, EQUI, PLKO, PLPO, PBIM, PBED, PLAF, T179, KAKO

**Transaction (21)**: VBAK, VBAP, VBEP, VBUK, VBUP, EKKO, EKPO, EKET, AFKO, AFPO, AFVC, AUFK, LIKP, LIPS, LTAK, LTAP, RESB, QMEL, QALS, QASE, KONV

**CDC (11)**: MSEG, MKPF, EKBE, AFRU, JEST, TJ02T, MCH1, MCHA, CDHDR, CDPOS, CRCO

## Appendix B: SAP AI Core Gen AI Hub — Model Access

| Provider | Model | Use Case |
|----------|-------|----------|
| **Anthropic** | Claude 3.5 Sonnet | Skills (judgment), Executive Briefing |
| **Anthropic** | Claude 3 Haiku | Skills (calculation), Email classification |
| OpenAI | GPT-4o | Alternative for Skills |
| OpenAI | GPT-4o-mini | Alternative for classification |
| Meta | Llama 3.1 | Self-hosted alternative (air-gapped) |

No LLM provider migration required for the SAP fork.

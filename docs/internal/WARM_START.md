# Warm-Start Deployment System

## Overview

Every deployment of the Autonomy platform requires AI models (GraphSAGE, tGNN, TRMs) to be warm-started with behavioral data before they can make useful decisions. This document describes the end-to-end pipeline that generates training data from heuristic policies, trains all three tiers of the Powell AI architecture, and produces SAP-formatted CSV files for enterprise integration testing.

This is **permanent deployment infrastructure** -- not throwaway code. It ships as a first-class "Deployment" section in the UI and generalizes to any `SupplyChainConfig`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Deployment Pipeline                        │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐               │
│  │ 1. Seed  │───>│ 2. Det.  │───>│ 3. Stoch │               │
│  │  Config  │    │   Sim    │    │   Sim    │               │
│  └──────────┘    └──────────┘    └──────────┘               │
│                        │               │                     │
│                        └───────┬───────┘                     │
│                                ▼                             │
│                       ┌──────────────┐                       │
│                       │ 4. Convert   │                       │
│                       │ Training Data│                       │
│                       └──────┬───────┘                       │
│                              ▼                               │
│              ┌───────────────────────────────┐               │
│              │        5. Train Models        │               │
│              │  S&OP GraphSAGE → tGNN → TRMs│               │
│              └───────────────┬───────────────┘               │
│                              ▼                               │
│              ┌───────────────────────────────┐               │
│              │     6. Export SAP CSVs         │               │
│              │  Day 1 (master) + Day 2 (delta)│               │
│              └───────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## The Three-Tier AI Architecture (Powell Framework)

The warm-start must produce trained checkpoints for all three tiers:

| Tier | Model | Update Frequency | Warm-Start Method |
|------|-------|------------------|-------------------|
| **S&OP** | GraphSAGE | Weekly/Monthly | Structural analysis of DAG topology |
| **Execution** | tGNN | Daily | Supervised on simulation state transitions |
| **Narrow TRM** | Transformer (7M params) | Continuous (CDC) | Behavioral cloning from heuristic policies |

### Why Heuristic Warm-Start?

Without warm-start, TRMs start with random weights and make nonsensical decisions (e.g., ordering 10,000 units when 10 are needed). Heuristic policies provide a reasonable behavioral baseline:

- **BASE_STOCK**: Order up to target inventory level (simple, stable)
- **CONSERVATIVE**: Smoothed ordering using 4-period moving average (low bullwhip)
- **PID**: Proportional-integral-derivative controller on inventory error (responsive)
- **EOQ**: Economic order quantity with reorder point (cost-optimized)

These produce 85-90% of optimal performance. TRMs then improve via online RL (TD learning with actual outcomes from the CDC feedback loop).

---

## Phase 1: Simulation

### DAG-Aware Deterministic Simulator

**File**: `backend/app/services/dag_simulator.py`

Reads any `SupplyChainConfig` from the database and simulates period-by-period using the existing Powell deterministic engines. Unlike the original 4-node Beer Game simulator, this supports arbitrary DAG topologies (the Food Dist config has 21 nodes in a hub-and-spoke layout: 10 suppliers → 1 DC → 10 customers, with 25 SKUs).

**Per-Period Flow** (topological order through DAG):

1. Receive arriving shipments (advance pipeline)
2. Generate demand at MARKET_DEMAND sites (Forecast P50 + Gaussian noise)
3. Process in reverse topological order:
   - **INVENTORY sites** (DCs): Fulfill downstream demand, compute order via heuristic
   - **MARKET_SUPPLY sites**: Fulfill upstream orders with lead-time delay
4. Record period state (on_hand, backlog, in_transit, costs)
5. Run `OrderTrackingEngine` on in-flight shipments → detect exceptions
6. Record ALL decisions for TRM behavioral cloning

**Engines Reused**:

| Engine | Role in Simulation | Source |
|--------|--------------------|--------|
| `MRPEngine` | Net requirements, BOM explosion | `powell/engines/mrp_engine.py` |
| `AATPEngine` | Priority-based allocation | `powell/engines/aatp_engine.py` |
| `SafetyStockCalculator` | Dynamic SS updates (4 policy types) | `powell/engines/safety_stock_calculator.py` |
| `RebalancingEngine` | Cross-location DOS-based transfers | `powell/engines/rebalancing_engine.py` |
| `OrderTrackingEngine` | Exception detection (6 types) | `powell/engines/order_tracking_engine.py` |

**Output**: `SimulationResult` containing:
- `period_states`: Per-site per-product snapshots (on_hand, backlog, in_transit, demand, fulfilled, costs)
- `decisions`: Every ordering, ATP, rebalancing, and exception decision with full context
- `shipments`: All pipeline shipments with lane, timing, quantities
- `kpis`: Fill rate, OTIF, inventory turns, holding/backlog cost, bullwhip ratio, DOS
- `site_product_history`: Time-series dict for training data extraction

### DAG-Aware Stochastic Simulator (SimPy)

**File**: `backend/app/services/dag_simpy_simulator.py`

Wraps the same DAG topology but introduces stochastic elements via SimPy discrete-event simulation:

| Stochastic Element | Source | Distribution |
|--------------------|--------|--------------|
| Lead times | `VendorLeadTime` CV | Triangular(min, mode, max) |
| Demand | Forecast P10/P50/P90 | LogNormal or Triangular |
| Supplier reliability | `TradingPartner.reliability` | Bernoulli per shipment |
| Capacity disruptions | Configurable | Uniform probability per period |

**Purpose**: Monte Carlo runs (128 runs × 52 weeks) produce robust training data with variance across scenarios. The deterministic simulator produces one "expected" trajectory; the stochastic simulator explores the space of possible outcomes.

**Key Difference**: SimPy manages event scheduling (shipment arrivals, demand events, disruptions) as a proper discrete-event simulation rather than period-by-period stepping. This captures timing effects that the deterministic simulator misses.

---

## Phase 2: S&OP GraphSAGE Inference Service

**File**: `backend/app/services/powell/sop_inference_service.py`

**Gap Closed**: The S&OP GraphSAGE model trains and saves checkpoints, but no runtime inference service existed. This service:

1. Loads the trained checkpoint (`sop_graphsage_{config_id}.pt`)
2. Runs a forward pass on the current network topology
3. Produces per-site scores: criticality, bottleneck_risk, concentration_risk, resilience, safety_stock_multiplier
4. Produces structural embeddings (64-dim) consumed by the Execution tGNN
5. Caches results in `powell_sop_embeddings` DB table

**Integration Points**:
- `AllocationService`: Weight allocation priorities by criticality
- `AATPEngine`: Pass structural embeddings as context to tGNN
- `RebalancingEngine`: Prioritize transfers to bottleneck sites
- `SiteAgent`: Encode S&OP embeddings into TRM state vector

---

## Phase 3: Training Data Conversion

**File**: `backend/app/services/simulation_data_converter.py`

Bridges the gap between simulation output and model training input:

### For GNN (S&OP GraphSAGE + Execution tGNN)

```
SimulationResult → NPZ / PyG Data objects
  Adjacency:      A[2, N, N]    from TransportationLane edges
  Node features:  X[B, W, N, F] inventory, backlog, demand, supply, ...
  Targets:        Y[B, N, H]    order quantities (discretized)
```

### For TRM (Behavioral Cloning)

```
SimulationResult.decisions → TRMReplayBuffer entries
  Per decision type:
    ATP decisions      → ATPExecutorTRM training data
    Rebalancing        → InventoryRebalancingTRM training data
    PO timing/qty      → POCreationTRM training data
    Exception handling → OrderTrackingTRM training data
```

### Training Orchestration

**File**: `backend/scripts/training/train_food_dist_models.py`

Runs the full 3-tier training sequence:

1. **S&OP GraphSAGE**: `powell_training_service.train_sop_graphsage()` on aggregated data
2. **Execution tGNN**: `powell_training_service.train_execution_tgnn()` with S&OP embeddings
3. **TRMs**: `TRMTrainer` with behavioral cloning (method=`BEHAVIORAL_CLONING`, then `HYBRID`)

Saves checkpoints: `sop_graphsage_{config_id}.pt`, `execution_tgnn_{config_id}.pt`, `trm_{type}_{site_key}.pt`

---

## Phase 4: Decision Persistence + CDC

### Decision Persistence

Five stubs in `integration_service.py` must be completed to close the TRM feedback loop:

| Stub | DB Table | Purpose |
|------|----------|---------|
| `_load_allocations()` | `powell_allocations` | Load existing allocations |
| `_log_atp_decision()` | `powell_atp_decisions` | Record ATP outcomes |
| `_log_po_decision()` | `powell_po_decisions` | Record PO timing/qty |
| `_log_exception_detection()` | `powell_order_exceptions` | Record exceptions |
| `_log_rebalance_decision()` | `powell_rebalance_decisions` | Record transfers |

### CDC Trigger

The CDC (Change Data Capture) monitor detects metric deviations and triggers TRM retraining:

```
Day 2 CSVs imported → DB state changes
    → CDCMonitor detects: DEMAND_DEVIATION, INVENTORY_LOW, etc.
    → CDCRetrainingService evaluates need (≥100 experiences + cooldown)
    → TRMTrainer.train() with Offline RL
    → New checkpoint saved
    → SiteAgent reloads model
```

**Trigger Thresholds**:
- `DEMAND_DEVIATION`: ±15% from forecast
- `INVENTORY_LOW`: <70% of safety stock
- `INVENTORY_HIGH`: >150% of target
- `SERVICE_LEVEL_DROP`: >5% below target
- `LEAD_TIME_INCREASE`: +30% vs expected
- `BACKLOG_GROWTH`: 2+ consecutive days growing
- `SUPPLIER_RELIABILITY`: <80% on-time rate

---

## Phase 5: SAP CSV Export

**File**: `backend/app/services/sap_csv_exporter.py`

Reverse maps AWS SC entities → SAP table format for all 19 standard tables:

| SAP Table | Source | Content |
|-----------|--------|---------|
| MARA | Product | Material master |
| MARC | Product + Site | Plant-level material |
| MARD | InvLevel | Stock by storage location |
| T001W | Site | Plant master |
| LFA1 | TradingPartner (vendor) | Vendor master |
| KNA1 | TradingPartner (customer) | Customer master |
| EKKO | InboundOrderLine (PO header) | Purchase order header |
| EKPO | InboundOrderLine (PO item) | Purchase order item |
| VBAK | OutboundOrderLine (SO header) | Sales order header |
| VBAP | OutboundOrderLine (SO item) | Sales order item |
| LIKP | Shipment (header) | Delivery header |
| LIPS | Shipment (item) | Delivery item |
| AFKO | InboundOrderLine (MO header) | Production order header |
| AFPO | InboundOrderLine (MO item) | Production order item |
| STPO | ProductBOM | BOM components |
| EKET | SupplyPlan (schedule lines) | PO schedule lines |
| RESB | Allocation/Reservation | Material reservations |
| /SAPAPO/LOC | Site (APO) | APO location master |
| /SAPAPO/SNPFC | Forecast (APO) | APO forecast data |

### Two Modes

**Day 1 (Full Export)**: Complete master data + current inventory state. Used for initial system setup.

**Day 2 (Delta Export)**: Changed records designed to trigger specific CDC events:

| Scenario Profile | SAP Tables | CDC Trigger |
|-----------------|------------|-------------|
| Demand Spike | VBAK/VBAP (+40% qty) | `DEMAND_DEVIATION` |
| Lead Time Increase | EKET (delayed dates) | `LEAD_TIME_INCREASE` |
| Rush Orders | VBAK/VBAP (Priority 1) | ATP exception |
| Inventory Shrink | MARD (reduced LABST) | `INVENTORY_LOW` |

---

## Phase 6: Pipeline Orchestration

**File**: `backend/app/services/deployment_pipeline_service.py`

Chains all phases into a resumable background pipeline:

| Step | Action | Duration (est.) |
|------|--------|-----------------|
| 1 | Seed Config | ~5s |
| 2 | Deterministic Simulation (52 weeks) | ~30s |
| 3 | Stochastic Simulation (128 runs × 52 weeks) | ~10min |
| 4 | Convert Training Data | ~30s |
| 5 | Train Models (GraphSAGE → tGNN → TRMs) | ~15min (CPU) |
| 6 | Generate Day 1 CSVs | ~10s |
| 7 | Generate Day 2 CSVs | ~10s |

Each step reports progress. Pipeline is resumable from any failed step.

### API Endpoints

```
POST   /api/v1/deployment/pipelines              → Start pipeline
GET    /api/v1/deployment/pipelines/{id}          → Status + progress
GET    /api/v1/deployment/pipelines/{id}/steps/{n} → Step detail
POST   /api/v1/deployment/pipelines/{id}/cancel   → Cancel
GET    /api/v1/deployment/csvs/{pipeline_id}      → List CSVs
GET    /api/v1/deployment/csvs/{id}/{table}       → Download CSV
POST   /api/v1/deployment/import-day2/{id}        → Import Day 2 + trigger CDC
```

---

## Phase 7: Frontend

New top-level **Deployment** section in navigation (between "AI & Agents" and "Administration"):

### Demo System Builder (`/deployment/builder`)

MUI Stepper wizard with 7 steps:

1. **Config**: Select template (Food Dist, etc.) + preview network topology
2. **Simulation**: Configure periods, demand pattern, heuristic strategy
3. **Training**: Configure epochs, device (cpu/cuda)
4. **SAP Export**: Configure Day 2 scenario profile (which disruptions)
5. **Review**: Summary of all choices
6. **Execute**: Start pipeline + live progress (poll every 2s)
7. **Results**: Download CSVs, view training metrics, trigger Day 2 import

### Pipeline Status (`/deployment/pipelines`)

Table of all pipeline runs with expandable step detail, timing, and error messages.

### CSV Downloads (`/deployment/csvs`)

List generated CSV ZIPs with download buttons per table.

---

## Food Distribution Config

The first warm-start template is the Food Distribution config:

- **21 sites**: 10 suppliers → 1 DC (West Valley City, UT) → 10 customers
- **25 SKUs** across 5 temperature-aware product groups (Frozen, Refrigerated, Dry)
- **Hub-and-spoke topology**: All material flows through the central DC
- **Real supplier/customer names**: US-based food distribution companies and restaurants

### Network Topology

```
Suppliers (MARKET_SUPPLY)          DC (INVENTORY)          Customers (MARKET_DEMAND)
┌──────────────────────┐     ┌─────────────────┐     ┌───────────────────────┐
│ Sysco Corp           │────>│                 │────>│ Restaurant Group A    │
│ US Foods             │────>│                 │────>│ Restaurant Group B    │
│ Performance Food     │────>│   DC West       │────>│ Hospital Network      │
│ Tyson Foods          │────>│   Valley City   │────>│ School District       │
│ Kraft Heinz          │────>│   (UT)          │────>│ Hotel Chain           │
│ General Mills        │────>│                 │────>│ Grocery Chain NW      │
│ Conagra Brands       │────>│                 │────>│ Grocery Chain SW      │
│ McCormick            │────>│                 │────>│ Convenience Stores    │
│ TreeTop Inc          │────>│                 │────>│ Corporate Cafeterias  │
│ Bob's Red Mill       │────>│                 │────>│ Food Service Co       │
└──────────────────────┘     └─────────────────┘     └───────────────────────┘
```

---

## Verification

| Test | Criteria |
|------|----------|
| **DAG Simulator** | Run 4 periods. Mass balance: total inventory + backlog + in-transit = initial + inbound - fulfilled. Same seed → identical output. |
| **SimPy Simulator** | 128 runs. KPI std dev > 0. Lead time samples match VendorLeadTime params. |
| **S&OP Inference** | Load checkpoint, run on Food Dist. 21 criticality scores, all in [0,1]. DC has highest criticality (hub node). |
| **CSV Export** | All 19 CSVs present with correct SAP headers. Referential integrity (EKPO.EBELN → EKKO.EBELN). Round-trip: export → import via CSVDataLoader → compare counts. |
| **Day 2 CDC** | Import Day 2 → CDC triggers fire (DEMAND_DEVIATION, INVENTORY_LOW). Retraining evaluates. New TRM checkpoint saved. |
| **Pipeline E2E** | Start from API → all 7 steps complete. Checkpoints exist. CSVs downloadable. |
| **Frontend** | Deployment section visible with `manage_deployment` capability. Wizard completes all steps. Progress updates during execution. |

---

## Files

### New Files (12)

| File | Purpose |
|------|---------|
| `backend/app/services/dag_simulator.py` | Deterministic DAG-aware simulator |
| `backend/app/services/dag_simpy_simulator.py` | Stochastic SimPy DAG simulator |
| `backend/app/services/simulation_data_converter.py` | Simulation → training format converter |
| `backend/app/services/sap_csv_exporter.py` | SAP CSV export (all 19 tables) |
| `backend/app/services/deployment_pipeline_service.py` | Pipeline orchestration |
| `backend/app/services/powell/sop_inference_service.py` | S&OP GraphSAGE runtime inference |
| `backend/app/models/deployment_pipeline.py` | Pipeline run DB model |
| `backend/app/api/endpoints/deployment.py` | Deployment REST API |
| `backend/scripts/training/train_food_dist_models.py` | 3-tier training orchestrator |
| `frontend/src/pages/deployment/DemoSystemBuilder.jsx` | Wizard UI |
| `frontend/src/pages/deployment/PipelineStatus.jsx` | Pipeline monitoring |
| `frontend/src/pages/deployment/CSVDownloads.jsx` | CSV download page |

### Modified Files (7)

| File | Changes |
|------|---------|
| `backend/app/services/powell/integration_service.py` | Complete 5 TODO stubs |
| `backend/app/services/powell/site_agent.py` | Inject S&OP embeddings, wire manual CDC |
| `backend/app/core/capabilities.py` | Add `manage_deployment` capability |
| `backend/scripts/training/generate_simpy_dataset.py` | Add `--config-name` N-node path |
| `frontend/src/config/navigationConfig.js` | Add Deployment section |
| `frontend/src/App.jsx` | Add Deployment routes |
| `backend/main.py` | Register deployment router |

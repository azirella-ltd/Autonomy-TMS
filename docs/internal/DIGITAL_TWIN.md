# Digital Twin Architecture

**Version**: 2.0 | **Date**: 2026-03-21 | **Cross-refs**: [D365-FORK.md](../../D365-FORK.md), [SAP-S4HANA-FORK.md](../../SAP-S4HANA-FORK.md)

The digital twin is the foundation of the Autonomy platform's AI agent training. It is NOT a separate system — it IS the customer's current supply chain planning system, replicated as a stochastic simulation. All AI agents learn by watching this simulation run and observing where the existing planning heuristics fail.

---

## 0. In-Memory Heuristic Mirror — Core Architectural Principle

**The digital twin is a lightweight mathematical mirror of the customer's ERP planning heuristics, not an API client.**

Every ERP (SAP, D365, Odoo) has a built-in MRP/MPS engine. These engines are deterministic, stateful, and slow (30 seconds to 2 minutes per run). They write results to production tables. They cannot be called 1,000 times for Monte Carlo simulation.

| ERP Engine | Time per Run | 1,000 Runs | Writes to Prod? |
|-----------|-------------|-----------|-----------------|
| SAP MRP (`MD01`/`MD02`) | 30-120 sec | 8-33 hours | Yes (`MDKP`, `MDTB`) |
| D365 Planning Optimization | 60-120 sec | 17-33 hours | Yes (`ReqPO`, `ReqTrans`) |
| Odoo MRP Scheduler | 30-120 sec (ORM) | 8-33 hours | Yes (`stock.move`, `procurement.order`) |
| frePPLe (Odoo add-on) | ~10 sec | 2.7 hours | Yes |
| **Autonomy in-memory mirror** | **0.1-0.3 sec** | **2-5 minutes** | **No (pure math)** |

**The architecture is the same for every ERP:**

1. **Read config once** — extract the customer's planning parameters from the ERP (SAP `MARC`, D365 `ReqItemTable`, Odoo `stock.warehouse.orderpoint`)
2. **Mirror heuristics as pure math** — replicate the ERP's coverage code / MRP type / orderpoint logic as vectorized in-memory operations. No ORM, no API calls, no database writes
3. **Run 1,000 stochastic trials in 2-5 minutes** — each trial perturbs demand, lead times, yield, quality, availability with calibrated distributions per entity in the DAG
4. **Observe where heuristics fail** — stockouts, excess inventory, late deliveries, expediting costs
5. **TRMs train on the gap** — the difference between heuristic outcomes and optimal is what agents learn to close
6. **The simulation engine never calls back to the ERP during Monte Carlo**

This principle applies uniformly:
- **SAP fork**: mirrors `MARC` fields (`DISMM`/`DISLS`/`MINBE`/`EISBE`/`VRMOD`)
- **D365 fork**: mirrors `ReqItemTable` fields (`CoverageCode`/`MinInventOnhand`/`SafetyStockQuantity`)
- **Odoo fork**: mirrors `stock.warehouse.orderpoint` fields (`trigger`/`product_min_qty`/`product_max_qty`)
- **AWS SC fork** (current): mirrors `inv_policy` fields (`ss_policy`/`reorder_point`/`order_up_to_level`)

Only the **config extraction layer** changes per ERP. The in-memory simulation math (netting, BOM explosion, coverage code logic, lead time offsetting) is data-model-agnostic.

### Current Implementation Status

| Heuristic | SAP Source | D365 Source | Odoo Source | Implemented? |
|-----------|-----------|------------|------------|-------------|
| **Reorder Point (ROP)** | `MARC.MINBE` | `ReqItemTable.MinInventOnhand` | `orderpoint.product_min_qty` | ✅ Yes — `_SimSite.compute_replenishment_order()` |
| **Order-Up-To (s,S)** | `MARC.MABST` | `ReqItemTable.MaxInventOnhand` | `orderpoint.product_max_qty` | ✅ Yes — `order_up_to - inventory_position` |
| **Safety Stock** | `MARC.EISBE` | `ReqItemTable.SafetyStockQuantity` | `orderpoint.product_min_qty` | ✅ Yes — via `inv_policy.ss_quantity` |
| **Fixed Lot Size** | `MARC.LOSGR` (DISLS=FX) | `ReqItemTable.StandardOrderQuantity` | `orderpoint.qty_multiple` | ❌ No — orders unconstrained |
| **Lot-for-Lot** | `MARC.DISLS=EX` | `CoverageCode=2` | Default orderpoint | ❌ No — always uses ROP/s,S |
| **Period Batching** | `MARC.DISLS=WB` (weekly) | `CoverageCode=1` | N/A | ❌ No — daily buckets only |
| **Min/Max Lot** | `MARC.BSTMI/BSTMA` | `ReqItemTable.MinimumOrderQuantity/MaximumOrderQuantity` | N/A | ❌ No — no lot bounds enforced |
| **Replenish-to-Max** | `MARC.DISLS=HB` | `CoverageCode=3` (Min/Max) | `orderpoint` default behavior | ❌ No — uses ROP not min/max |
| **DDMRP Buffers** | N/A (external) | `CoverageCode=4` | `ddmrp` module | ❌ No — no green/yellow/red zone logic |
| **MRP Type Routing** | `MARC.DISMM` (VB/VM/PD/ND) | `CoverageCode` (0-4) | `trigger` (auto/manual) | ❌ No — all products use same logic |
| **Forecast Consumption** | `MARC.VRMOD/VINT1/VINT2` | `ForecastTimeFence` | N/A | ❌ No — uses max(forecast, actuals) |
| **Time Fences** | `MARC.FXHOR` | `FrozenTimeFence` / `LockingTimeFence` | N/A | ❌ No — no frozen/flexible periods |
| **BOM Explosion** | `STKO`/`STPO` | `BOMTable`/`BOMLine` | `mrp.bom`/`mrp.bom.line` | ✅ Yes — recursive netting |
| **Lead Time Offsetting** | `MARC.PLIFZ` | `LeadTimePurchase` | `produce_delay`/`purchase_delay` | ✅ Yes — pipeline delay |

**Current state**: The simulation mirrors **ROP/order-up-to + BOM explosion + lead time offsetting**. This covers the most common heuristic pattern but does NOT differentiate between ERP-specific MRP types, lot sizing procedures, or forecast consumption modes.

**Target state**: Mirror all 5 D365 coverage codes, all 6 SAP lot sizing procedures, and Odoo's orderpoint/DDMRP logic as separate mathematical functions selectable per product-site based on the extracted ERP config.

### Heuristic Mirroring Fidelity Risk

The primary engineering risk is **divergence between the mirror and the real ERP behavior**. If the simulation doesn't faithfully replicate what SAP/D365/Odoo actually does, TRM training data is poisoned — agents learn to compensate for phantom failures that don't occur in production.

**Mitigation**: For each ERP, validate the mirror's output against the ERP's deterministic run for the same inputs. Run both with identical demand and compare planned orders. Discrepancies indicate mirror bugs or undocumented ERP behavior (phantom BOMs, co-products, intercompany transfers).

---

## 1. Core Concept

Traditional APS (Advanced Planning Systems) use deterministic heuristics: fixed reorder points, fixed safety stocks, fixed lead times, fixed lot sizes. These rules are configured per product-site in the ERP (SAP MARC, D365 ReqItemTable, Odoo orderpoint).

The digital twin runs these exact heuristics against **stochastic reality** — the same demand variability, lead time uncertainty, yield losses, quality events, and machine breakdowns that the real supply chain experiences. The gap between heuristic performance and optimal is what AI agents learn to close.

```
┌──────────────────────────────────────────────────────────┐
│                    DIGITAL TWIN                          │
│                                                          │
│   Customer's APS Heuristics (deterministic)              │
│   ├── Reorder Point per (product, site)                  │
│   ├── Safety Stock per (product, site)                   │
│   ├── Fixed Lot Size per (product, vendor)               │
│   ├── MRP Type per (product, site)                       │
│   └── Procurement Type per (product, site)               │
│                      ↓ runs against ↓                    │
│   Stochastic Reality (per entity in DAG)                 │
│   ├── Customer demand per (customer, product, site)      │
│   ├── Supplier lead time per (vendor, product, site)     │
│   ├── Inter-plant transfer time per (from, to)           │
│   ├── Customer delivery time per (site, customer)        │
│   ├── Production yield per (product, site)               │
│   ├── Throughput rate per (product, site, resource)       │
│   ├── Quality pass rate per (product, site)              │
│   ├── Machine availability per (resource, site)          │
│   └── Changeover time per (from_product, to_product)     │
│                      ↓ produces ↓                        │
│   Decisions + Outcomes                                   │
│   ├── PO creation, ATP allocation, MO release            │
│   ├── Inventory position, stockouts, excess              │
│   ├── OTIF, fill rate, cycle time, backorder rate        │
│   └── Cost: holding, backlog, ordering, expediting       │
│                      ↓ observed by ↓                     │
│   AI Agents (learn by watching)                          │
│   ├── TRM agents: "what would I have decided?"           │
│   ├── GNN agents: "what network-level patterns emerge?"  │
│   └── Conformal: "how uncertain is each prediction?"     │
└──────────────────────────────────────────────────────────┘
```

---

## 2. What Is Static vs Stochastic During Training

| Category | Variables | Source | During Training |
|----------|----------|-------|----------------|
| **Guardrails** | Authority limits, approval thresholds, budget caps | Tenant config + GNN heuristic equivalents | **STATIC** |
| **Metric Targets** | OTIF ≥ 95%, fill rate ≥ 98%, max backorder ≤ 5% | Tenant config | **STATIC** |
| **APS Parameters** | ROP, SS, lot size, MRP type, procurement type | ERP (MARC/ReqItemTable/orderpoint) per (product, site) | **STATIC** (these ARE the heuristic being evaluated) |
| **Demand** | Customer order quantities | Historical outbound_order or triangular fallback | **STOCHASTIC** per (customer, product, site) |
| **Lead Times** | Supplier inbound, inter-plant, customer delivery | Historical inbound_order or triangular fallback | **STOCHASTIC** per lane |
| **Operations** | Yield, throughput, quality, availability, changeover | Historical production data or triangular fallback | **STOCHASTIC** per (product, site, resource) |

Every stochastic variable is instantiated **per entity in the DAG**, not per tenant. A config with 9 finished goods, 81 components, 27 customers, 8 vendors, and 2 plants has thousands of unique distribution instances.

---

## 3. Stochastic Distributions

All stochastic variables use **triangular distributions** fitted from historical data when available (≥5 observations), with principled fallbacks when not.

### 3.1 Fitting from History

When historical data exists (from ERP staging tables), the triangular parameters are estimated:
- **min** = P5 (5th percentile — robust lower bound, excludes outliers)
- **mode** = median (robust central tendency)
- **max** = P95 (95th percentile — robust upper bound)

### 3.2 Nine Distribution Classes

| # | Variable | Class | History Source | Fallback |
|---|----------|-------|---------------|----------|
| 1 | Customer demand | `HistoricalTriangularDemand` | `outbound_order_line` daily quantities | Min closer to mode, right-skewed, industry CoV |
| 2 | Supplier inbound LT | `HistoricalTriangularLeadTime` | `inbound_order` PO date → GR date | Skewed to min, long upper tail (2.5× mode) |
| 3 | Inter-plant transfer LT | `HistoricalTriangularTransferLeadTime` | Site-to-site lane configs | Tighter (1.8× mode), faster min (0.6×) |
| 4 | Customer delivery LT | `HistoricalTriangularDeliveryLeadTime` | `outbound_order` actual/promised/assumed | Moderate right skew (2× mode) |
| 5 | Production yield | `HistoricalTriangularYield` | Production order actual vs planned qty | 0.90 / 0.97 / 0.995 |
| 6 | Throughput rate | `HistoricalTriangularThroughput` | AFRU confirmation times vs planned | 0.80 / 0.95 / 1.05 |
| 7 | Quality pass rate | `HistoricalTriangularQualityRate` | Inspection lot results (QALS) | 0.92 / 0.98 / 0.999 |
| 8 | Machine availability | `HistoricalTriangularMachineAvailability` | Maintenance order data | 0.80 / 0.92 / 0.98 |
| 9 | Changeover time | `HistoricalTriangularChangeoverTime` | Routing setup times (PLPO) | 15 / 30 / 90 minutes |

### 3.3 Demand Fallback — Industry CoV Benchmarks

When no demand history exists, the coefficient of variation is set by product category:

| Category | CoV | Examples |
|----------|-----|---------|
| Staple | 0.15 | Food staples, utilities |
| Automotive | 0.20 | Automotive components |
| Industrial | 0.25 | Pumps, valves, motors |
| Default / Bikes | 0.30 | General manufacturing |
| Seasonal | 0.35 | Seasonal products, fashion |
| Electronics | 0.40 | Consumer electronics |
| Promotional | 0.50 | Promotional items, launches |
| Intermittent | 0.80 | Spare parts, MRO |

---

## 4. Simulation Parameters

### 4.1 Trials

Each trial is an independent Monte Carlo replication of the supply chain operating over the simulation horizon. The number of trials determines the statistical reliability of the training data.

| Industry | Default Trials | Rationale |
|----------|---------------|-----------|
| 3PL / Wholesale | 50 | Short cycles, lower variance |
| Food & Beverage / CPG / Building | 50 | Standard |
| Electronics / Chemical / Metals | 60 | Component shortage risk, batch variability |
| Automotive / Industrial / Textile | 75 | Complex BOMs, JIT sensitivity, fashion risk |
| Pharmaceutical / Aerospace | 100 | Long tails, regulatory variance, certification delays |

### 4.2 Simulation Days

Set to **2× the industry end-to-end supply chain lead time** — enough to see one full replenishment cycle complete plus variability.

| Industry | SC Lead Time (days) | Simulation Days |
|----------|-------------------|-----------------|
| 3PL | 7 | 14 |
| Wholesale Distribution | 14 | 28 |
| Food & Beverage | 21 | 42 |
| Consumer Goods | 30 | 60 |
| Building Materials | 35 | 70 |
| Chemical | 42 | 84 |
| Electronics | 45 | 90 |
| Automotive | 60 | 120 |
| Metals & Mining | 75 | 150 |
| Industrial Equipment / Textile | 90 | 180 |
| Pharmaceutical | 120 | 240 |
| Aerospace & Defense | 180 | 360 |

### 4.3 Time Bucket

Always **daily**. Weekly and monthly buckets lose the granularity needed for work week effects, lead time variability, and demand pattern detection.

Weekly demand forecasts are spread uniformly over work days. Monthly forecasts are spread over ~22 work days per month (varies by work week pattern).

### 4.4 Work Week

Each site has its own work calendar. Work days are determined by (in priority order):

1. **ERP site calendar**: SAP factory calendar (`T001W.FABKL`), D365 `WorkCalendar`, Odoo `resource.calendar`
2. **Historical transaction pattern**: days with zero goods movements / production confirmations = non-work days
3. **Country default**: Sun-Thu for Middle East (AE, SA, IL), Mon-Sat for India/China manufacturing, Mon-Fri for Americas/Europe/Japan

Lead times count **work days only**. A 2 work-day lead time starting Friday arrives Tuesday (skipping Saturday and Sunday). The simulation starts from the current real date for calendar alignment.

### 4.5 Warmup Period

First 10% of simulation days (minimum 5 days) are warmup — data is not collected during this period to avoid early transient effects.

---

## 5. Measured Outcomes (Customer Service Metrics)

These are **outcomes**, not inputs. They measure how well the APS heuristics performed against stochastic reality.

| Metric | Definition | Computation |
|--------|-----------|-------------|
| **OTIF %** | On Time In Full | Orders delivered by requested date AND in full quantity |
| **Fill Rate %** | Quantity fulfillment | Total qty fulfilled / total qty ordered |
| **On-Time %** | Delivery timeliness | Orders delivered ≤ requested delivery date |
| **Perfect Order %** | Complete execution | On time + in full + no quality issues + correct documentation |
| **Backorder Rate %** | Unfulfilled demand | Orders with remaining unfulfilled quantity |
| **Avg Cycle Time** | Order-to-delivery | Days from order placement to delivery |

Delivery date resolution: actual delivery > promised delivery > assumed (order_date + lane lead time mode).

Metric **targets** (e.g., OTIF ≥ 95%) are static tenant configuration. Metric **actuals** are computed from simulation results and compared against targets.

---

## 6. Guardrails

Guardrails are the **only static variables** during training (besides APS parameters and metric targets). They constrain what TRM agents can decide.

Sources (in priority order):
1. **Trained GNN output** (`powell_policy_parameters`): safety stock multiplier, service level target, reorder point days, sourcing split
2. **GNN heuristic equivalent**: computed from network topology when no trained GNN exists — concentration risk from supplier count, bottleneck risk from downstream lane count
3. **Tenant context** (`tenant_bsc_config`, `authority_definitions`): max autonomous order value, approval thresholds, autonomy confidence threshold

---

## 7. Learning Sequence

1. **Load APS parameters** from ERP staging (per product-site deterministic values)
2. **Instantiate stochastic distributions** per entity in the DAG (per customer-product-site, per vendor-product-site, etc.)
3. **Load guardrails** from tenant context + GNN heuristics
4. **Run N trials** of the digital twin simulation (each trial = independent Monte Carlo replication)
5. **Collect decisions and outcomes** at each simulation day (what the heuristic decided + what happened)
6. **Compute customer service metrics** (OTIF, fill rate, cycle time) for each trial
7. **Score the gap** between heuristic outcomes and metric targets
8. **Feed to agents**: TRMs learn from individual decisions, GNNs learn from network patterns, conformal prediction learns from prediction-outcome pairs

The agents learn **where the heuristic fails** — stockouts it didn't prevent, excess inventory it accumulated, late deliveries it caused, expediting costs it incurred. The trained agents then make better decisions in the same stochastic environment.

---

## 8. APS Parameter Sources by ERP

The digital twin replicates the customer's actual planning parameters. These come from:

### SAP S/4HANA (MARC table, per material-plant)

| MARC Field | Meaning | How Twin Uses It |
|-----------|---------|-----------------|
| `DISMM` | MRP Type (PD, VB, ND) | Planning method selection |
| `DISLS` | Lot Sizing (EX, FX, WB) | Order quantity rule |
| `MINBE` | Reorder Point | When to trigger replenishment |
| `EISBE` | Safety Stock | Buffer quantity |
| `BESKZ` | Procurement Type (E, F) | Make vs Buy decision |
| `PLIFZ` | Planned Delivery Time | Expected lead time |
| `LOSGR` | Fixed Lot Size | Order quantity |
| `BSTMI`/`BSTMA` | Min/Max Lot | Order bounds |
| `FXHOR` | Planning Time Fence | Frozen zone |

### D365 F&O (ReqItemTable + InventItemOrderSetups)

| D365 Field | SAP Equivalent | Meaning |
|-----------|---------------|---------|
| `CoverageCode` | `DISMM` | MRP type (Manual/Period/Lot-for-lot/Min-Max) |
| `PlannedOrderType` | `BESKZ` | Purchase/Production/Transfer |
| `MinInventOnhand` | `MINBE` | Reorder point |
| `SafetyStockQuantity` | `EISBE` | Safety stock |
| `StandardOrderQuantity` | `LOSGR` | Fixed lot size |
| `LeadTimePurchasing` | `PLIFZ` | Planned lead time |

### Odoo (stock.warehouse.orderpoint + product.template)

| Odoo Field | SAP Equivalent | Meaning |
|-----------|---------------|---------|
| `trigger` | `DISMM` | auto (MRP) / manual (no planning) |
| `route_id` | `BESKZ` | Buy / Manufacture / Resupply route |
| `product_min_qty` | `MINBE` | Reorder point |
| `product_max_qty` | Max inventory | Order-up-to level |
| `produce_delay` | Routing LT | Manufacturing lead time |
| `qty_multiple` | `BSTRF` | Rounding quantity |

---

## 9. Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/services/powell/training_distributions.py` | 9 stochastic distributions, guardrails, industry defaults, work calendars, OTIF computation |
| `backend/app/services/powell/simulation_decision_seeder.py` | Digital twin execution — runs APS heuristics, generates decisions |
| `backend/app/services/powell/simulation_calibration_service.py` | DAG chain simulation engine (`_DagChain`, `_SimSite`) |
| `backend/app/services/provisioning_service.py` | Orchestrates digital twin as provisioning step |
| `backend/app/models/tenant.py` | Tenant-level simulation parameters (`sim_trials`, `sim_days`, etc.) |
| `frontend/src/pages/admin/TenantManagement.jsx` | Admin UI for simulation parameters |

---

## 10. Relationship to Other Platform Components

| Component | How It Uses the Digital Twin |
|-----------|----------------------------|
| **TRM Agents** | Phase 1 (BC) training data from digital twin decisions |
| **S&OP GraphSAGE** | Network risk scores calibrated from digital twin outcomes |
| **Conformal Prediction** | CDT calibration from digital twin decision-outcome pairs |
| **Decision Stream** | Seeded with digital twin decisions for demo readiness |
| **Scenario Events** | What-if branches run the digital twin with injected disruptions |
| **SAP Change Simulator** | Extends digital twin with ongoing change events after initial extraction |

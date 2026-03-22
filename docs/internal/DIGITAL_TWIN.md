# Digital Twin Architecture

**Version**: 3.0 | **Date**: 2026-03-22 | **Cross-refs**: [D365-FORK.md](../../D365-FORK.md), [SAP-S4HANA-FORK.md](../../SAP-S4HANA-FORK.md)

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

## 8A. ERP/APS-Specific Deterministic Heuristic Library

The digital twin must faithfully replicate what the customer's ERP actually does — not a generic MRP, but the **specific algorithms and parameters** configured in their system. This section defines the complete heuristic library organized at two levels: **site-level** (MRP netting, lot sizing, consumption) and **network-level** (DRP, S&OP allocation, multi-echelon).

### Design Principles

1. **Each heuristic is a pure function**: `f(state, config) → (decision, new_state)`. No database access, no API calls, no side effects.
2. **Config-driven dispatch**: The ERP config (SAP `MARC.DISMM`, D365 `CoverageCode`, Odoo `orderpoint.trigger`) selects which function runs per product-site. Not hardcoded — the same simulation engine runs any ERP's heuristics by reading a config map.
3. **Composable pipeline**: Netting → Lot Sizing → Scrap Adjustment → Rounding → Min/Max → Lead Time Offset → BOM Explosion. Each step is a separate function; steps can be swapped per ERP.
4. **Validation against ERP output**: Every heuristic must be validated by comparing its deterministic output (zero stochastic variance) against the real ERP's MRP run for the same data. Discrepancies are bugs.

### 8A.1 Site-Level MRP Heuristics

These run per product-site, per simulation day. They determine **when and how much to order**.

#### 8A.1.1 Netting Methods (MRP Type / Coverage Code / Trigger)

The netting method determines **what demand triggers replenishment**. This is the first branch in the heuristic dispatch.

**SAP MRP Types (`MARC.DISMM`)**:

| Type | Name | Algorithm |
|------|------|-----------|
| **PD** | Deterministic MRP | `net_req[t] = gross_req[t] + safety_stock - available[t] - scheduled_receipts[t]`. Plans against PIR (planned independent requirements) and/or sales orders. Standard time-phased netting. |
| **VB** | Manual Reorder Point | `if (available_stock - reserved) < reorder_point: order_qty = reorder_point + safety_stock - available_stock - scheduled_receipts`. No forecast. Trigger is pure inventory position vs MINBE. |
| **V1** | Reorder Point + External Req | Like VB but external requirements (sales orders, reservations) reduce available stock in the trigger check: `if (available - external_req) < reorder_point`. |
| **VM** | Auto Reorder Point | Same as VB but reorder point and safety stock are auto-calculated by SAP's forecasting module (exponential smoothing on historical consumption). Mirror uses the resulting MINBE/EISBE values. |
| **V2** | Auto Reorder Point + External | Combines VM auto-calculation with V1 external requirements check. |
| **VV** | Forecast-Based | Plans against forecast values consumed by actuals. Deprecated — SAP recommends PD with strategy groups. Mirror implements for legacy ECC customers. |
| **ND** | No Planning | Skip entirely. `order_qty = 0`. |

**D365 Coverage Codes (`ReqItemTable.CoverageCode`)**:

| Code | Name | Algorithm |
|------|------|-----------|
| **0** | Manual | No planned orders. Manual creation only. `order_qty = 0`. |
| **1** | Period | Combine all demand within `CoverageTimeFence` into one planned order. `order_qty = sum(demand[t..t+period_length])`. Order placed at first day of consolidation period. |
| **2** | Requirement (Lot-for-lot) | One planned order per demand. `order_qty = demand[t]` exactly. |
| **3** | Min/Max | `if projected_on_hand < MinInventOnhand: order_qty = MaxInventOnhand - projected_on_hand`. Single order to bring stock to max level. |
| **4** | DDMRP | Net flow equation against buffer zones. See §8A.1.4. |

**Odoo Orderpoint (`stock.warehouse.orderpoint`)**:

| Trigger | Algorithm |
|---------|-----------|
| **auto** | `virtual_available = on_hand + incoming - outgoing - reserved`. If `virtual_available < product_min_qty: order_qty = product_max_qty - virtual_available`. Apply `qty_multiple` rounding. |
| **manual** | No automatic planning. |

**Unified Dispatch Function** (pseudocode):
```python
def compute_replenishment(state: SiteState, config: ERPConfig) -> float:
    """Pure function: selects and executes the correct netting heuristic."""
    match config.erp_type, config.mrp_type:
        case "sap", "PD":  return sap_deterministic_mrp(state, config)
        case "sap", "VB":  return sap_reorder_point(state, config)
        case "sap", "V1":  return sap_reorder_point_external(state, config)
        case "sap", "VM":  return sap_reorder_point(state, config)  # same logic, auto params
        case "sap", "VV":  return sap_forecast_based(state, config)
        case "sap", "ND":  return 0.0
        case "d365", 0:    return 0.0  # Manual
        case "d365", 1:    return d365_period_coverage(state, config)
        case "d365", 2:    return d365_lot_for_lot(state, config)
        case "d365", 3:    return d365_min_max(state, config)
        case "d365", 4:    return ddmrp_net_flow(state, config)
        case "odoo", "auto": return odoo_orderpoint(state, config)
        case "odoo", "manual": return 0.0
```

#### 8A.1.2 Lot Sizing Procedures

After netting determines the **net requirement**, lot sizing determines the **order quantity**. Lot sizing takes the raw net requirement and adjusts it per the configured policy.

**Static Lot Sizes** (simple, no optimization):

| Key | Name | Logic | SAP | D365 | Odoo |
|-----|------|-------|-----|------|------|
| **L4L** | Lot-for-lot | `order_qty = net_requirement` | DISLS=EX | CoverageCode=2 | Default |
| **FX** | Fixed lot | `order_qty = ceil(net_req / fixed_lot) * fixed_lot` | DISLS=FX, LOSGR | StandardOrderQty | qty_multiple |
| **HB** | Replenish-to-max | `order_qty = max_stock - available` | DISLS=HB, MABST | CoverageCode=3 | product_max_qty |
| **TB/WB/MB** | Period batching | Aggregate demand over 1 day / 1 week / 1 month | DISLS=TB/WB/MB | CoverageCode=1 | N/A |

**Dynamic Lot Sizes** (optimize setup vs holding cost):

These require `setup_cost` (K) and `holding_cost_per_unit_per_period` (h) from the ERP config. They operate on a demand vector `d[1..T]` over the planning horizon.

| Key | Name | Algorithm | Complexity |
|-----|------|-----------|-----------|
| **EOQ** | Economic Order Quantity | `EOQ = sqrt(2 * D * K / h)` where D = annual demand. Static — same qty every order. | O(1) |
| **SM** | Silver-Meal | Minimize average cost per period. Start accumulating periods; stop when `C(T) = (K + h * Σ i*d[s+i]) / T` increases. | O(T) |
| **PPB** | Part Period Balancing | Accumulate part-periods `PP = Σ (i-1)*d[s+i]` until PP ≥ EPP where `EPP = K/h`. | O(T) |
| **GR** | Groff Procedure | Similar to PPB but compares incremental holding cost to amortized setup cost. Stop when `h * d[j] * (j-start) > K / periods_covered`. | O(T) |
| **WW** | Wagner-Whitin (Optimal) | Dynamic programming: `F[t] = min over j of F[j-1] + K + h * Σ (k-j)*d[k]`. Backtrack for optimal lot boundaries. Planning Horizon Theorem reduces to O(T) amortized. | O(T) amortized |
| **LUC** | Least Unit Cost | Like Silver-Meal but divides by total units, not periods: `UC(T) = (K + h * Σ i*d[s+i]) / Σ d[s..s+T]`. | O(T) |

**Post-Lot-Sizing Adjustments** (applied after lot sizing, before BOM explosion):

```python
def apply_adjustments(order_qty: float, config: ERPConfig) -> float:
    # 1. Scrap adjustment (assembly-level)
    if config.assembly_scrap_pct > 0:
        order_qty = order_qty / (1.0 - config.assembly_scrap_pct)

    # 2. Rounding
    if config.rounding_value > 0:
        order_qty = math.ceil(order_qty / config.rounding_value) * config.rounding_value

    # 3. Min/Max enforcement
    order_qty = max(order_qty, config.min_lot_size)
    if config.max_lot_size > 0:
        order_qty = min(order_qty, config.max_lot_size)

    return order_qty
```

#### 8A.1.3 Forecast Consumption (SAP-Specific)

SAP's forecast consumption is the most complex demand-side heuristic. It determines how actual demand (sales orders) "eats into" planned independent requirements (PIR/forecast).

**Configuration**: `MARC.VRMOD` (mode) + `MARC.VINT1` (backward periods) + `MARC.VINT2` (forward periods)

| VRMOD | Mode | Behavior |
|-------|------|----------|
| 1 | Backward only | Search backward up to VINT1 work days from requirement date to find PIRs to consume |
| 2 | Backward then forward | Search backward (VINT1), then if unmatched, forward (VINT2) |
| 3 | Forward only | Search forward up to VINT2 work days |
| 4 | Forward then backward | Search forward (VINT2), then backward (VINT1) |
| 5 | Period-based | Consume only within the same forecast period bucket |

```python
def consume_forecast(
    actual_demand: float,
    demand_date: int,  # simulation day
    pir_schedule: Dict[int, float],  # day → remaining PIR qty
    vrmod: int,
    vint1: int,  # backward fence (work days)
    vint2: int,  # forward fence (work days)
    work_calendar: WorkCalendar,
) -> Tuple[float, Dict[int, float]]:
    """
    Returns (unconsumed_demand, updated_pir_schedule).
    Unconsumed demand becomes net additional requirement for MRP.
    """
    remaining = actual_demand

    # Always try same-day first
    if demand_date in pir_schedule and pir_schedule[demand_date] > 0:
        consumed = min(remaining, pir_schedule[demand_date])
        pir_schedule[demand_date] -= consumed
        remaining -= consumed

    if remaining <= 0:
        return 0.0, pir_schedule

    # Build search sequence based on VRMOD
    search_days = []
    bwd_days = work_calendar.offset_backward(demand_date, vint1)
    fwd_days = work_calendar.offset_forward(demand_date, vint2)

    if vrmod == 1:    search_days = bwd_days
    elif vrmod == 2:  search_days = bwd_days + fwd_days
    elif vrmod == 3:  search_days = fwd_days
    elif vrmod == 4:  search_days = fwd_days + bwd_days
    elif vrmod == 5:  search_days = [d for d in pir_schedule if same_period(d, demand_date)]

    # Consume in search order
    for day in search_days:
        if remaining <= 0:
            break
        if day in pir_schedule and pir_schedule[day] > 0:
            consumed = min(remaining, pir_schedule[day])
            pir_schedule[day] -= consumed
            remaining -= consumed

    return remaining, pir_schedule  # remaining becomes uncovered net demand
```

**D365 and Odoo** do not have native forecast consumption. D365 uses `ForecastTimeFence` to separate forecast from actual demand horizons. Odoo uses pure orderpoint (no forecast netting).

#### 8A.1.4 DDMRP Buffer Management

DDMRP (Demand-Driven MRP) replaces traditional safety stock + reorder point with dynamically sized buffer zones. Available natively in both D365 and S/4HANA (and via OCA module for Odoo).

**Buffer Zone Calculation**:

```python
def compute_ddmrp_buffers(
    adu: float,          # Average Daily Usage
    dlt: float,          # Decoupled Lead Time (days)
    lt_factor: float,    # 0.2 (long LT) to 0.8 (short LT)
    var_factor: float,   # 0.2 (low variability) to 1.0 (high variability)
    moq: float,          # Minimum Order Quantity
    order_cycle: float,  # Days between orders (imposed)
    daf: float = 1.0,    # Demand Adjustment Factor (seasonal multiplier)
) -> DDMRPBuffers:
    adj_adu = adu * daf
    ltu = adj_adu * dlt

    red_base = ltu * lt_factor
    red_safety = red_base * var_factor
    red_zone = red_base + red_safety           # "Top of Red"

    yellow_zone = ltu                           # "Top of Yellow" = Red + Yellow

    green_zone = max(ltu * lt_factor, moq, order_cycle * adj_adu)

    return DDMRPBuffers(
        top_of_red=red_zone,
        top_of_yellow=red_zone + yellow_zone,   # = reorder point
        top_of_green=red_zone + yellow_zone + green_zone,  # = max stock
    )
```

**Net Flow Equation** (run daily):

```python
def ddmrp_net_flow(state: SiteState, config: DDMRPConfig) -> float:
    """Determine order quantity using DDMRP net flow equation."""
    qualified_demand = (
        state.past_due_demand
        + state.todays_demand
        + sum(d for d in state.future_demand[:config.spike_horizon]
              if d > config.spike_threshold)
    )

    net_flow = state.on_hand + state.on_order - qualified_demand

    if net_flow < config.buffers.top_of_yellow:
        return config.buffers.top_of_green - net_flow
    return 0.0
```

#### 8A.1.5 Time Fences

Time fences divide the planning horizon into zones with different rules. The mirror must respect these to match ERP behavior.

**SAP Planning Time Fence (`MARC.FXHOR`)**:

```python
def apply_time_fence(
    order_qty: float,
    order_date: int,      # simulation day for the planned order
    today: int,           # current simulation day
    fxhor: int,           # planning time fence (work days)
    work_calendar: WorkCalendar,
) -> Tuple[float, int]:
    """
    Within the fence: do NOT create new orders; generate exception message.
    Outside the fence: normal MRP.
    Returns (adjusted_qty, adjusted_date).
    """
    fence_date = work_calendar.offset_forward_single(today, fxhor)

    if order_date <= fence_date:
        # Inside frozen zone — suppress automatic order creation
        # In production: this generates an exception message for the planner
        return 0.0, order_date  # No order; TRM can decide to override

    return order_qty, order_date
```

**D365 Three-Fence Model**:

| Fence | Effect | Config Field |
|-------|--------|-------------|
| **Frozen** | No new orders, no changes to existing | `FrozenTimeFence` |
| **Firming** | New orders get "firmed" flag (no auto-reschedule) | `FirmingTimeFence` |
| **Coverage** | Maximum planning horizon — no orders beyond this | `CoverageTimeFence` |

**D365 Positive/Negative Days**:

```python
def d365_supply_matching(
    demand_date: int,
    supply_date: int,
    max_negative_days: int,  # How late supply can be and still cover demand
    max_positive_days: int,  # How early supply can be accepted
) -> bool:
    """Can this supply cover this demand?"""
    days_late = supply_date - demand_date  # positive = late supply
    days_early = demand_date - supply_date  # positive = early supply

    if days_late > 0 and days_late <= max_negative_days:
        return True   # Late but within tolerance
    if days_early > 0 and days_early <= max_positive_days:
        return True   # Early but within tolerance
    if days_late == 0:
        return True   # Exact date match
    return False       # Out of tolerance — create new order
```

#### 8A.1.6 BOM Explosion with Scrap

After determining the planned order quantity at a parent level, BOM explosion creates dependent demand at component levels.

```python
def explode_bom(
    parent_qty: float,
    parent_order_date: int,
    bom: List[BOMComponent],  # component_id, qty_per, scrap_pct
    assembly_scrap_pct: float,
    lead_time: int,
    work_calendar: WorkCalendar,
) -> List[DependentDemand]:
    """Create dependent demand for all BOM components."""
    # Adjust parent for assembly scrap
    adjusted_parent = parent_qty / (1.0 - assembly_scrap_pct)

    # Schedule: components needed at order_start = order_date - lead_time
    component_need_date = work_calendar.offset_backward_single(
        parent_order_date, lead_time
    )

    demands = []
    for comp in bom:
        comp_qty = adjusted_parent * comp.qty_per * (1.0 + comp.scrap_pct)
        demands.append(DependentDemand(
            product_id=comp.component_id,
            quantity=comp_qty,
            need_date=component_need_date,
            parent_order_id=None,  # linked during execution
        ))
    return demands
```

**Processing Order**: Materials processed by **low-level code** (LLC). LLC 0 (finished goods) first, then LLC 1 (sub-assemblies), then LLC 2+ (components). This guarantees all dependent demand from all parents is accumulated before a component is planned. Materials at the same LLC can be processed in parallel.

### 8A.2 Network-Level Planning Heuristics

These operate across the supply chain DAG, determining **how requirements flow between sites**.

#### 8A.2.1 DRP (Distribution Requirements Planning)

DRP is the inverse of MRP — it processes **bottom-up** from demand points to supply sources.

```python
def run_drp(
    network: DAGNetwork,
    demand_forecasts: Dict[Tuple[str, str], List[float]],  # (site, product) → daily demand
    configs: Dict[Tuple[str, str], ERPConfig],
) -> Dict[str, List[PlannedShipment]]:
    """
    DRP: Process sites bottom-up (demand sinks first, then upstream).
    Each site's planned order releases become gross requirements
    for its supplying site.
    """
    # Topological sort: demand sites first, supply sites last
    site_order = network.topological_sort(reverse=True)  # leaf → root

    all_shipments = {}
    upstream_requirements = defaultdict(lambda: defaultdict(float))

    for site_id in site_order:
        for product_id in network.products_at(site_id):
            config = configs[(site_id, product_id)]

            # Gross requirement = local demand + requirements from downstream
            gross_req = [
                demand_forecasts.get((site_id, product_id), [0.0] * horizon)[t]
                + upstream_requirements[(site_id, product_id)].get(t, 0.0)
                for t in range(horizon)
            ]

            # Run site-level MRP (netting + lot sizing)
            planned_orders = run_site_mrp(gross_req, config)

            # Lead-time offset: planned order releases become
            # gross requirements at the supplying site
            supplier_id = network.supplier_for(site_id, product_id)
            if supplier_id:
                transit_lt = network.transit_lead_time(supplier_id, site_id)
                for order in planned_orders:
                    release_date = order.date - transit_lt
                    upstream_requirements[(supplier_id, product_id)][release_date] += order.qty

            all_shipments[site_id] = planned_orders

    return all_shipments
```

#### 8A.2.2 S&OP Disaggregation / Allocation

When the S&OP process sets family-level or regional-level plans, they must be disaggregated to SKU-site level. The digital twin mirrors whatever method the customer uses.

**Proportional Disaggregation** (most common):

```python
def disaggregate_proportional(
    family_plan: float,
    sku_history: Dict[str, float],  # sku_id → historical demand over N periods
) -> Dict[str, float]:
    """Disaggregate family-level plan to SKU level using historical proportions."""
    total_history = sum(sku_history.values())
    if total_history == 0:
        # Equal split if no history
        return {sku: family_plan / len(sku_history) for sku in sku_history}

    return {
        sku: family_plan * (hist / total_history)
        for sku, hist in sku_history.items()
    }
```

**Priority-Based Allocation** (for constrained supply):

```python
def allocate_constrained_supply(
    available_supply: float,
    demands: List[Tuple[str, float, int]],  # (customer_id, qty, priority)
) -> Dict[str, float]:
    """Allocate scarce supply to demands sorted by priority (lower = higher)."""
    sorted_demands = sorted(demands, key=lambda d: d[2])  # sort by priority
    allocations = {}
    remaining = available_supply

    for customer_id, qty, priority in sorted_demands:
        allocated = min(qty, remaining)
        allocations[customer_id] = allocated
        remaining -= allocated
        if remaining <= 0:
            break

    return allocations
```

**Fair-Share Allocation** (equitable distribution):

```python
def allocate_fair_share(
    available_supply: float,
    demands: Dict[str, float],  # customer_id → requested qty
) -> Dict[str, float]:
    """Allocate proportionally when supply < total demand."""
    total_demand = sum(demands.values())
    if total_demand <= available_supply:
        return dict(demands)  # No rationing needed

    ratio = available_supply / total_demand
    return {cust: qty * ratio for cust, qty in demands.items()}
```

#### 8A.2.3 Capacity Scheduling Heuristics

**RCCP (Rough-Cut Capacity Planning)**:

```python
def compute_rccp(
    planned_production: Dict[Tuple[str, int], float],  # (product, period) → qty
    resource_profiles: Dict[str, Dict[str, float]],    # product → {resource: hours_per_unit}
    available_capacity: Dict[Tuple[str, int], float],   # (resource, period) → hours
) -> Dict[Tuple[str, int], float]:
    """Returns utilization % per resource per period."""
    load = defaultdict(float)
    for (product, period), qty in planned_production.items():
        for resource, hours_per_unit in resource_profiles.get(product, {}).items():
            load[(resource, period)] += qty * hours_per_unit

    utilization = {}
    for (resource, period), hours in load.items():
        cap = available_capacity.get((resource, period), 0)
        utilization[(resource, period)] = hours / cap if cap > 0 else float('inf')

    return utilization
```

**Production Scheduling Priority Rules**:

| Rule | Sort Key | Optimizes |
|------|----------|-----------|
| SPT | `processing_time ASC` | Avg flow time, WIP |
| EDD | `due_date ASC` | Max lateness |
| CR | `(due_date - now) / remaining_time ASC` | Dynamic urgency |
| SLACK | `(due_date - now - remaining_time) ASC` | Lateness |
| WSPT | `weight / processing_time DESC` | Weighted flow time |

**Glenday Sieve** (for repetitive manufacturing):

```python
def glenday_classify(
    products: Dict[str, float],  # product_id → annual volume
) -> Dict[str, str]:
    """Classify products into Glenday categories."""
    sorted_prods = sorted(products.items(), key=lambda x: x[1], reverse=True)
    total_volume = sum(products.values())

    cumulative = 0.0
    classifications = {}
    for prod_id, volume in sorted_prods:
        cumulative += volume
        pct = cumulative / total_volume
        if pct <= 0.50:
            classifications[prod_id] = "GREEN"   # Fixed repeating cycle
        elif pct <= 0.95:
            classifications[prod_id] = "YELLOW"  # Fill remaining capacity
        else:
            classifications[prod_id] = "BLUE"    # Make-to-order only

    return classifications
```

### 8A.3 Creating New ERP-Specific Heuristics

To add support for a new ERP or APS system, follow this process:

**Step 1 — Document the ERP's algorithm**:
- Read the ERP vendor's documentation for MRP processing logic, lot sizing, and demand processing
- For open-source ERPs (Odoo): read the actual source code (e.g., `stock_orderpoint.py`)
- For closed-source ERPs (SAP, D365): use vendor documentation + validated test cases
- Document the algorithm as pseudocode with explicit parameter references

**Step 2 — Identify the config parameters**:
- Map ERP config fields to the heuristic function's inputs
- Example: SAP `MARC.DISMM` → `config.mrp_type`, `MARC.DISLS` → `config.lot_sizing`
- Ensure these fields are extracted by the ERP connector and persisted (or accessible via the staging layer)

**Step 3 — Implement as a pure function**:
- Input: `SiteState` (inventory, pipeline, backlog, demand history) + `ERPConfig` (all parameters)
- Output: `order_qty` (float) and any side-effect records (exception messages, action messages)
- No database access inside the function — all data passed as arguments

**Step 4 — Register in the dispatch map**:
- Add the new heuristic to `compute_replenishment()` dispatch (§8A.1.1)
- Add the new lot sizing to the lot sizing dispatch (§8A.1.2)
- Register any ERP-specific post-processing (scrap, rounding, time fences)

**Step 5 — Validate against ERP output**:
- Extract a test scenario from the ERP: demand, supply, on-hand, MRP parameters
- Run the ERP's MRP deterministically and capture planned orders
- Run the mirror with identical inputs (zero stochastic variance)
- Compare planned order quantities, dates, and types
- Discrepancies are bugs in the mirror — fix until output matches
- Maintain this as a regression test

**Step 6 — Configure for tenant**:
- During provisioning (step `decision_seed`), the config extraction layer reads the customer's ERP config
- Each product-site gets its specific netting method, lot sizing, time fences, and consumption mode
- The simulation engine dispatches to the correct heuristic per product-site

### 8A.4 Implementation Roadmap

| Priority | Heuristic | ERP | Status | Effort |
|----------|-----------|-----|--------|--------|
| **P0** | Reorder Point (s,S) | All | ✅ Implemented | Done |
| **P0** | BOM Explosion (no scrap) | All | ✅ Implemented | Done |
| **P0** | Lead Time Offsetting | All | ✅ Implemented | Done |
| **P1** | BOM Explosion with scrap | SAP, D365 | ❌ Schema exists, not applied | 2 days |
| **P1** | Lot-for-lot (EX/CoverageCode=2) | SAP, D365 | ❌ | 1 day |
| **P1** | Fixed lot (FX) + Min/Max enforcement | SAP, D365, Odoo | ❌ | 2 days |
| **P1** | Period batching (WB/MB/CoverageCode=1) | SAP, D365 | ❌ | 2 days |
| **P1** | Min/Max (HB/CoverageCode=3) | SAP, D365, Odoo | ❌ | 1 day |
| **P2** | Deterministic MRP (PD) netting | SAP | ❌ | 3 days |
| **P2** | D365 Positive/Negative Days | D365 | ❌ | 1 day |
| **P2** | DDMRP buffer zones + net flow | D365, SAP, Odoo | ❌ | 5 days |
| **P2** | Planning Time Fence (FXHOR) | SAP | ❌ | 2 days |
| **P2** | D365 Three-Fence Model | D365 | ❌ | 2 days |
| **P3** | Forecast Consumption (VRMOD 1-5) | SAP | ❌ | 5 days |
| **P3** | Silver-Meal / PPB / Wagner-Whitin | SAP (DISLS=SP/SM/OP) | ❌ | 3 days |
| **P3** | Groff Procedure | SAP (DISLS=GR) | ❌ | 2 days |
| **P3** | EOQ lot sizing | SAP, generic | ❌ | 1 day |
| **P4** | DRP bottom-up network planning | All | ❌ | 5 days |
| **P4** | RCCP capacity check | All | ❌ | 3 days |
| **P4** | Glenday Sieve + changeover minimization | Manufacturing | ❌ (exists in MOExecutionTRM, not in sim) | 2 days |
| **P4** | Proportional disaggregation | All | ❌ | 1 day |
| **Total P1** | | | | **~8 days** |
| **Total P1+P2** | | | | **~22 days** |
| **Total P1+P2+P3** | | | | **~33 days** |
| **Total All** | | | | **~44 days** |

### 8A.5 Validation Strategy

For each implemented heuristic:

1. **Unit test with known inputs**: Fixed demand vector, known parameters, compare against hand-calculated expected output
2. **Regression test against ERP**: Extract a representative scenario from the customer's ERP (via staging). Run both the ERP's MRP and the mirror. Compare planned orders (qty, date, type) — they must match within rounding tolerance
3. **Stochastic divergence test**: Run 100 MC trials with the mirror. Verify that the mean of stochastic outcomes converges to the deterministic output (law of large numbers check)
4. **Cross-ERP consistency**: For equivalent configurations (SAP DISLS=EX ≡ D365 CoverageCode=2 ≡ Odoo default), verify identical outputs

---

## 9. Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/services/powell/training_distributions.py` | 9 stochastic distributions, guardrails, industry defaults, work calendars, OTIF computation |
| `backend/app/services/powell/simulation_decision_seeder.py` | Digital twin execution — runs APS heuristics, generates decisions |
| `backend/app/services/powell/simulation_calibration_service.py` | DAG chain simulation engine (`_DagChain`, `_SimSite`, `_ConfigLoader`) |
| `backend/app/services/powell/engines/mrp_engine.py` | MRP netting engine (lot-for-lot, fixed, EOQ — extend for §8A lot sizing) |
| `backend/app/services/sc_planning/net_requirements_calculator.py` | Time-phased netting, BOM explosion, sourcing — extend for §8A scrap + multi-sourcing |
| `backend/app/services/sc_planning/demand_processor.py` | Demand processing — extend for §8A forecast consumption (VRMOD) |
| `backend/app/services/sc_planning/inventory_target_calculator.py` | 8 safety stock policy types (extend for DDMRP buffer zones) |
| `backend/app/services/provisioning_service.py` | Orchestrates digital twin as provisioning step |
| `backend/app/models/tenant.py` | Tenant-level simulation parameters (`sim_trials`, `sim_days`, etc.) |
| `frontend/src/pages/admin/TenantManagement.jsx` | Admin UI for simulation parameters |
| **Planned** `backend/app/services/powell/heuristic_library.py` | ERP-specific heuristic dispatch (§8A — to be implemented) |

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

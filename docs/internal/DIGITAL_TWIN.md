# Digital Twin Architecture

**Version**: 5.0 | **Date**: 2026-03-22 | **Cross-refs**: [D365-FORK.md](../../D365-FORK.md), [SAP-S4HANA-FORK.md](../../SAP-S4HANA-FORK.md)

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

### 8A.3 Constrained Supply Allocation

When supply is insufficient to meet all demand, the allocation method determines who gets what. The method varies by ERP, by customer, and by DAG level.

#### 8A.3.1 Allocation Methods (12 Methods)

| # | Method | Algorithm | SAP | D365 | Odoo |
|---|--------|-----------|-----|------|------|
| 1 | **Fair Share / Proportional** | `A_i = S × (D_i / ΣD)` — each customer gets supply in proportion to their demand | APO Fair Share Rule A; IBP finite heuristic | Via allocation keys on demand forecast | OCA `stock_available_to_promise_release` |
| 2 | **Equal Target Stock %** | Raise all destinations to the same % of their target stock: `target_pct = (S - deficit_correction) / Σ(target_stock)` | APO Fair Share Rule B | Not native | Not native |
| 3 | **Quota-Based** | `A_i = S × quota_pct_i` — pre-agreed percentage per customer/region | APO Fair Share Rule C; PAL allocation objects | Allocation keys | Not native |
| 4 | **Priority / Waterfall** | Serve highest priority fully first: `A_i = min(D_i, remaining); remaining -= A_i` — lower priorities get leftovers | aATP BOP (WIN/GAIN/REDISTRIBUTE/FILL/LOSE); APO Rule D | Native: planning priority 0-100 | OCA priority date module |
| 5 | **Tiered / Fill Rate Target** | `Target_A = D_A × 95%, Target_B = D_B × 80%, Target_C = D_C × 60%`. Scale down proportionally if insufficient. | aATP PAL allocation groups per customer tier | Coverage groups with differentiated parameters | Not native |
| 6 | **Profit / Margin-Weighted** | LP: maximize `Σ(A_i × margin_i)` subject to `ΣA_i ≤ S, 0 ≤ A_i ≤ D_i` | IBP Optimizer mode | Not native (custom) | Not native |
| 7 | **Revenue-Weighted** | `A_i = S × (Revenue_i / ΣRevenue)` — simpler than profit (no cost data needed) | Custom | Custom | Not native |
| 8 | **Committed-First** | Serve firm orders before forecast: firm > scheduled > safety stock > forecast | Native in ATP (forecast consumption priority) | Native (priority defaults: SO > TO > forecast) | Standard reservation |
| 9 | **FCFS** | Sort by `order_entry_date ASC`, serve in chronological order | Default without allocation config | Default without priority-based planning | Default reservation behavior |
| 10 | **Customer Quota Agreement** | `A_i = S × Q_i / 100` with redistribution of unclaimed surplus | Quota arrangements (ME01); PAL with allocation objects per customer | Allocation keys | Not native |
| 11 | **Backlog Priority** | Oldest backlog first, then new orders: sort by `original_promise_date ASC` | aATP BOP REDISTRIBUTE/FILL strategies | Priority on overdue demands (priority 0) | Manual |
| 12 | **Geographic Proximity** | Transportation Problem LP: minimize `Σ(x_ij × cost(SP_j, C_i))` — or greedy nearest supplier | APO SNP deployment with lane costs | Sourcing rules with preferred warehouse | Route-based |

**SAP aATP Backorder Processing (BOP) — the most sophisticated allocation engine:**

Six confirmation strategies, processed in rank order:

| Strategy | Behavior | Typical Use |
|----------|----------|------------|
| **WIN** | Full confirmation on requested date. Never loses quantity. | VIP / rush orders |
| **GAIN** | Retains current confirmation; improves if possible. Never reduced. | Key accounts |
| **IMPROVE** | Like GAIN with additional optimization rules (S/4HANA 2022+) | Mid-tier |
| **REDISTRIBUTE** | May lose some quantity to WIN/GAIN. Gets remainder. | Standard orders |
| **FILL** | Like REDISTRIBUTE but cannot gain new confirmations | Low priority |
| **LOSE** | All confirmed quantities forfeit to higher strategies | Credit-blocked |

**SAP Product Allocation (PAL)**:
1. Define allocation sequence (top-level object)
2. Within sequence: allocation steps checked in order (e.g., step 1 = by customer, step 2 = by region)
3. Each step has constraints referencing allocation objects with per-period quantities
4. Confirmed qty = **minimum across all steps** (most restrictive wins)
5. Consumption can be discrete (unused expires) or cumulative (unused rolls forward)

**D365 Priority-Based Planning**:
```
Priority = 100 × (1 - projected_available / max_inventory_qty)
```
Near-zero stock → priority 100 (urgent). Near-max stock → priority 0. Planned orders inherit the priority of the demand that triggered them. Supply at priority P can only satisfy demand at priority P or lower.

#### 8A.3.2 Allocation at DAG Levels

Allocation happens at **every level** of the supply chain DAG, not just at the customer-facing tier:

| DAG Level | Allocation Context | Typical Method |
|-----------|-------------------|---------------|
| **Supplier → Plant** | Multiple plants competing for scarce raw material from a shared supplier | Quota-based (SAP EQUK) or priority (strategic plant first) |
| **Plant → DC** | Factory output pushed to DCs (§8A.5 push deployment) | Fair share by demand (APO Rule A) or target stock % (Rule B) |
| **DC → DC** | Rebalancing between distribution centers | Geographic proximity + target stock equalization |
| **DC → Customer** | Final allocation of finished goods to customer orders | Priority/waterfall (aATP BOP) or committed-first |
| **Component → Parent** | Scarce component allocated across multiple parent items that need it | Fair share by parent demand, or priority by parent margin |
| **Resource → Product** | Scarce production capacity allocated across products | Glenday (GREEN products first) or margin-weighted |

### 8A.4 Alternate Sourcing / Multi-Sourcing

When multiple suppliers or supply routes exist for a product, the sourcing method determines which source is selected and how volume is split.

#### 8A.4.1 Sourcing Methods (9 Methods)

| # | Method | Algorithm | SAP | D365 | Odoo |
|---|--------|-----------|-----|------|------|
| 1 | **Fixed (Single Source)** | All volume to one predetermined vendor | Source List (EORD) with one entry | Approved Vendor List, single vendor | Single vendor on Purchase tab |
| 2 | **Priority-Based** | Try vendor A first; if can't supply, try B | Info Records (EINE) with purchasing priority; Source List with fixed indicator | Preferred vendor on item coverage; trade agreement price fallback | Vendor sequence on Purchase tab |
| 3 | **Quota-Based (Ratio Split)** | `Quota Rating = (Allocated + Base) / Quota`. Assign to vendor with lowest rating. | Quota Arrangement tables EQUK/EQIA (ME01/ME03). Running total converges to target split. | Multisource policy: `Current% = Vendor_Sourced / Total_Accumulated × 100`. Assign to vendor deviating most below target. | Not native |
| 4 | **Cost-Based (TCO)** | `total_cost = unit_price + freight + duties + handling + quality_cost`. Select min. | Info Records (EINE) net price; Conditions (KONP) for freight/duties | Trade agreements with qty breaks; vendor price comparison | Vendor pricelists: lowest price matching qty/date |
| 5 | **Lead-Time-Based** | Select vendor with shortest lead time that meets required date | EINE planned delivery time; MARC-PLIFZ | Trade agreement lead times | `delay` field per vendor on Purchase tab |
| 6 | **Capacity-Based** | Allocate based on available supplier capacity: `allocate = min(remaining, available_cap)` | Quota arrangement with max release qty | Min/max order qty per vendor in trade agreements | Min quantity on vendor pricelist |
| 7 | **Geographic / Regional** | Prefer nearest supplier or same-region vendor | Plant-specific source lists | Site-specific item coverage with different preferred vendors | Warehouse-specific reorder rules |
| 8 | **Risk-Based / Diversification** | No single vendor > X% of total volume; spread across regions | Quota arrangements enforcing splits; SAP Ariba risk scores | Multisource policies with min/max shares | Not native |
| 9 | **Dual Sourcing (Primary/Backup)** | Normal: 80/20 split. Disruption: 0/100 to backup. Recovery: gradual restore. | Quota arrangement (80/20). Vendor block → auto-shift to backup. | Multisource policy. Vendor hold → allocate to remaining. | Two vendors by sequence; archive primary → falls to secondary |

**SAP Quota Arrangement Rating Algorithm** (critical to implement faithfully):

```python
def sap_quota_rating(allocated_qty: float, base_qty: float, quota: float) -> float:
    """Lower rating = gets the next order. Tie-break: highest quota value wins."""
    return (allocated_qty + base_qty) / quota

# Example: Vendors A(60%), B(30%), C(10%)
# Initially all at 0 allocated → ratings: A=0/60=0, B=0/30=0, C=0/10=0
# Tie broken by highest quota → A wins first order (100 units)
# After: A rating = 100/60=1.67, B=0/30=0, C=0/10=0 → B wins
# After: B rating = 100/30=3.33, C=0/10=0 → C wins
# Converges toward 60/30/10 split over many orders
```

#### 8A.4.2 Transportation Lane Selection (Regular / Expedite / Consolidation)

Multiple transportation options typically exist per lane. The mode selection algorithm:

```python
def select_transport_mode(
    weight: float, volume: float, distance: float,
    required_date: int, today: int,
    standard_transit: int, expedite_transit: int,
    standard_rate: float, expedite_rate: float,
    ftl_threshold: float, ltl_min: float,
    stockout_penalty: float,
) -> TransportMode:
    """Select shipping mode based on urgency, cost, and load."""
    slack = required_date - today - standard_transit

    # Step 1: Urgency check
    if slack < 0:
        return AIR_EXPRESS  # Already late — fastest available
    if slack < 2:
        return EXPEDITE_TRUCK

    # Step 2: Load-based mode selection
    if weight >= ftl_threshold:
        mode = FTL_TRUCK
    elif weight >= ltl_min:
        mode = LTL_TRUCK
    else:
        mode = PARCEL

    # Step 3: Cost vs speed evaluation
    cost_of_expedite = expedite_rate - standard_rate
    cost_of_late = stockout_penalty  # lost margin + penalty + churn risk
    if cost_of_expedite < cost_of_late and slack < 5:
        return EXPEDITE_TRUCK

    return mode
```

**Consolidation logic**: Group orders within a configurable window (e.g., 3 days) by destination zone. If combined weight ≥ FTL threshold, create consolidated FTL shipment at lower per-unit cost.

**ERP specifics**:
- **SAP TM**: Carrier selection strategy (cost, priority, cost+priority). Condition type `MTRVT_DET` for rule-based mode/vehicle determination. Freight order types: standard vs express.
- **D365 TMS**: Rating profiles with tariffs per carrier-mode-lane. Rate shopping via Rate/Route workbench. Routing guides with rules on weight, volume, destination, service level.
- **Odoo**: Delivery methods with fixed or rule-based pricing. Third-party carrier integration (FedEx/UPS/DHL) for rate quotes. No native TMS optimizer.

### 8A.5 Push-Based Deployment (Production-Driven Distribution)

When manufacturing sites have limited FG storage (dairy, cement, chemicals, continuous production lines), they must **push** output downstream even when downstream demand hasn't explicitly pulled it.

#### 8A.5.1 SAP APO SNP Deployment Heuristic

The most fully documented push deployment algorithm in enterprise software:

**Step 1 — Calculate Available-to-Deploy (ATD)** at source:
```
ATD(t) = Σ(ATR receipts from period 0..t) - Σ(ATI issues within checking horizon)
  ATR = stock + confirmed production + PO receipts + planned receipts
  ATI = sales orders + reservations + dependent demands + existing deployments
```

**Step 2 — Compare ATD to total downstream demand:**
- If **ATD < Demand**: → **Fair Share mode** (shortage allocation, §8A.3)
- If **ATD ≥ Demand**: → **Push mode** (surplus distribution)

**Step 3 — Push Distribution Methods:**

| Rule | Name | Algorithm |
|------|------|-----------|
| **A** | Push by Demands | `push(i) = surplus × (demand(i) / Σdemand)`. Surplus distributed proportionally. |
| **D** | Push by Priority | Surplus to highest-priority transportation lane first, then next priority. |
| **Q** | Push by Quota | All supply distributed by quota arrangement. Demand at destinations **ignored** — pure push. |
| **S** | Push to Target Stock | Push to bring destinations up to target stock level. Only deploys when destination projected stock < target AND meets minimum lot size. |

**Three Horizons**:
- **Deployment Horizon**: Total days over which stock transfers are planned
- **Pull Horizon**: Days over which downstream demands are visible (pull-based)
- **Push Horizon**: Days over which source receipts are pushed immediately

**Pull/Push Hybrid** (most common config): Cover all demand within pull horizon immediately. Beyond pull horizon, no push. This prevents over-deployment while ensuring near-term coverage.

#### 8A.5.2 Storage-Constrained Production Push

When factory FG storage is the binding constraint:

```python
def push_from_factory(
    production_output: float,
    local_storage_available: float,
    downstream_locations: List[Location],  # sorted by push priority
    push_method: str,  # "demand_proportional" | "target_stock" | "nearest_first" | "cost_min"
) -> Dict[str, float]:
    """Push excess production to downstream locations."""
    surplus = max(0, production_output - local_storage_available)
    if surplus <= 0:
        return {}

    pushes = {}
    remaining = surplus

    if push_method == "demand_proportional":
        total_demand = sum(loc.forecast_demand for loc in downstream_locations)
        for loc in downstream_locations:
            push_qty = min(remaining, surplus * loc.forecast_demand / total_demand, loc.available_capacity)
            pushes[loc.id] = push_qty
            remaining -= push_qty

    elif push_method == "target_stock":
        # Push to equalize target stock percentage across all DCs
        deficits = [(loc, loc.target_stock - loc.current_inventory) for loc in downstream_locations]
        deficits.sort(key=lambda x: x[1], reverse=True)  # largest deficit first
        for loc, deficit in deficits:
            push_qty = min(remaining, max(0, deficit), loc.available_capacity)
            pushes[loc.id] = push_qty
            remaining -= push_qty

    elif push_method == "nearest_first":
        for loc in sorted(downstream_locations, key=lambda l: l.distance_from_factory):
            push_qty = min(remaining, loc.available_capacity)
            pushes[loc.id] = push_qty
            remaining -= push_qty

    return pushes
```

**Critical principle for continuous production**: The deployment plan must be solved **before or simultaneously with** the production plan. Production is gated by `min(equipment_capacity, Σ downstream_storage_available + outbound_shipments_scheduled)`.

#### 8A.5.3 ERP-Specific Push Mechanisms

| ERP | Push Mechanism | Config |
|-----|---------------|--------|
| **SAP APO/IBP** | SNP Deployment Heuristic (Rules A/D/Q/S) | Product-Location master SNP2 tab: ATR/ATI category groups, push/pull horizons, fair share rule |
| **SAP S/4HANA** (without APO) | Cross-plant MRP with Special Procurement Key → Stock Transport Orders (STO) | Material master: special procurement key; Shipping: replenishment delivery |
| **D365** | Planned Transfer Orders via warehouse refilling; Planned Cross-Docking | Item coverage: refilling checkbox + main warehouse; Cross-docking template |
| **D365 Intercompany** | Planned intercompany purchase/sales orders | Master plan: "Include planned downstream demand" across legal entities |
| **Odoo** | Push Rules (`stock.rule` with `action='push'`) — event-driven on stock arrival | Route definition: source location → destination location + delay |

#### 8A.5.4 Push-Pull Boundary / Decoupling Point

The decoupling point is the strategic position where push (forecast-driven) transitions to pull (demand-driven):

```
Suppliers → Component Mfg → [DECOUPLING POINT] → Assembly → Distribution → Customer
     PUSH (forecast/MPS)          BUFFER          PULL (actual orders)
```

- **DDMRP** formalizes this: buffers at decoupling points absorb variability and prevent bullwhip upstream
- **Postponement**: Push generic product to decoupling point; pull customized product downstream (e.g., paint base pushed to DC, tinting at point of sale)
- **VMI**: Supplier pushes replenishment within agreed min/max bounds based on customer's real-time inventory
- **Consignment**: Product pushed to customer warehouse but ownership retained until consumption (SAP special stock indicator W)

### 8A.6 Order Modification Rules

After netting and lot sizing determine the raw order quantity, order modification rules adjust it to comply with vendor, packaging, and logistics constraints.

**Processing sequence** (order matters — each step feeds the next):

```
Raw net requirement
  → Lot sizing (§8A.1.2)
  → MOQ enforcement
  → Order multiple / rounding
  → Rounding profile (SAP-specific)
  → Max order qty (split if exceeded)
  → Pack size / container fill
  → Order frequency constraint
  → Order aggregation window
  → Final planned order(s)
```

#### 8A.6.1 Order Constraints

| Constraint | Algorithm | SAP Config | D365 Config | Odoo Config |
|-----------|-----------|-----------|------------|------------|
| **MOQ (Minimum Order Qty)** | `if qty < MOQ: qty = MOQ` | `MARC-BSTMI` | `Min. order quantity` on item coverage | `Minimum Quantity` on vendor pricelist |
| **MOV (Minimum Order Value)** | `if qty × price < MOV: qty = ceil(MOV / price)` | Not native (purchasing BAdI) | Min order amount on trade agreement | Not native |
| **Maximum Order Qty** | `if qty > max: split into ceil(qty/max) orders` | `MARC-BSTMA` | `Max. order quantity` on item coverage | Not native |
| **Order Multiple** | `qty = ceil(qty / multiple) × multiple` | `MARC-BSTRF` | `Multiple` on item coverage | `qty_multiple` on reorder rule |
| **Rounding Profile** | Scaled rounding by threshold: find threshold T where qty > T, round to corresponding multiple | `MARC-RDPRF` (Customizing OMI4) | Not native | Not native |
| **Pack/Case/Pallet** | `qty = ceil(qty / pack_size) × pack_size` — driven by UoM conversion | MARM (UoM conversion); purchase UoM | Unit conversion; purchase UoM on trade agreement | UoM categories with conversion |
| **FCL/FTL Fill** | If fill_rate ≥ 85%: round up to full container. `savings = LCL_rate × qty - FCL_rate`. If savings > extra holding cost: round up. | SAP TM optimization | D365 TMS rate shopping | Not native |
| **Order Frequency** | Can only order on allowed days (e.g., weekly on Monday). Aggregate requirements within review period. | Lot sizing WB/MB/PB (period-based) | `Order period` on coverage group | Daily scheduler (not fine-grained) |
| **Aggregation Window** | Combine requirements within X days into one order | Implicit in period lot sizing (WB/MB) | Coverage time fence consolidation | Reorder rule cycle |

### 8A.7 Reorder Triggers Beyond ROP

The current simulation only implements Reorder Point (s,S). These additional trigger methods must be mirrored per the customer's ERP config.

| # | Trigger | Algorithm | SAP | D365 | Odoo |
|---|---------|-----------|-----|------|------|
| 1 | **(s,S) Min-Max** | If `inv_pos ≤ s: order(S - inv_pos)` — variable order size | ✅ Implemented (VB + HB) | CoverageCode=3 | Default orderpoint |
| 2 | **(s,Q) Fixed Qty** | If `inv_pos ≤ s: order(Q)` — fixed order regardless of deficit | DISMM=VB + DISLS=FX | Not native as named policy | Not native |
| 3 | **(R,S) Periodic Review** | Every R days: `order(S - inv_pos)`. SS covers R+L, not just L. | DISMM=R1 (time-phased planning) | CoverageCode=1 (period) | Scheduler runs daily |
| 4 | **TPOP (Time-Phased OP)** | ROP + forward demand visibility: `if projected_inv[t] < ROP: order at t-LT` | DISMM=R1 with planning cycle | Standard MRP netting with coverage fence | Not native |
| 5 | **DDMRP Net Flow** | `net_flow = on_hand + on_order - qualified_demand`. If net_flow < top_of_yellow: order. | IBP / third-party | CoverageCode=4 | OCA DDMRP module |
| 6 | **Kanban / Pull Signal** | Downstream consumption triggers upstream replenishment of fixed container qty. N = `D×L×(1+α)/C` | PP kanban control | Lean Manufacturing kanban rules | Not native |
| 7 | **Event-Driven** | Large order, promotion, disruption, forecast revision → immediate replan | Net Change (NETCH) replans changed materials only | Net change planning mode | Manual "Run Scheduler" |
| 8 | **Consumption-Based Auto** | System auto-calculates ROP from historical consumption (exponential smoothing) | DISMM=VM/V2 (automatic reorder point) | Not native (manual SS calc) | Not native |

### 8A.8 Additional Safety Stock / Buffer Methods

Beyond the 8 policies already implemented in `inventory_target_calculator.py`:

| # | Method | Algorithm | Status |
|---|--------|-----------|--------|
| 1 | **Dynamic SS (Forecast-Error)** | `MAD_t = (1/n) × Σ|actual-forecast|`. `SS_t = z × 1.25 × MAD_t × √L`. Recalculated every period. | ❌ Not implemented. SAP VM auto-recalculates. |
| 2 | **Seasonal SS** | `SS_t = base_SS × seasonal_multiplier[month(t)]`. Pre-build buffer before peak. | ❌ Not implemented. SAP: period indicator. D365: minimum key. DDMRP: DAF. |
| 3 | **ABC/XYZ Differentiated** | A items: SL=99% (z=2.33). B: 95% (z=1.65). C: 90% (z=1.28). Combined with XYZ (CoV): AZ items need largest SS or DDMRP. CZ → make-to-order. | ❌ Not implemented. All ERPs support per-product SL. |
| 4 | **Multi-Echelon (MESSO / Graves-Willems)** | DP on spanning tree: `F[t] = min_j(F[j-1] + h_j × SS_j(SI_j, S_j))`. Optimizes WHERE in the network to hold SS. 20-40% inventory reduction typical. | ❌ Not implemented. SAP IBP native. Kinaxis native. `stockpyl` open-source lib. |
| 5 | **Demand-Weighted (Downstream Criticality)** | `SS_j = z × σ_j × √L_j × w_j` where `w_j = Σ(revenue(c) × demand_share(c))` for downstream customers c | ❌ Not implemented. Custom in all ERPs. |
| 6 | **Censored-Demand-Adjusted** | Stockout periods → observed demand < true demand. Use survival analysis / Tobit model to estimate true σ. `SS_corrected > SS_observed` always. | ❌ Not implemented (Lokad methodology). Censored demand detection exists in `demand_processor.py`. |

### 8A.9 Per-Site ERP/APS Configuration Model

**CRITICAL ARCHITECTURAL REQUIREMENT**: In the real world, companies that have grown through acquisition often run **different ERP and APS systems at different sites** or for different product families. A single customer's supply chain may include:

- Plant A runs SAP S/4HANA (acquired 2019, migrated from ECC)
- Plant B runs D365 F&O (acquired 2022, came with the acquisition)
- DC Network runs SAP IBP for demand/supply planning
- Plant C uses Kinaxis for production scheduling
- Legacy products still planned in spreadsheets (effectively manual MRP)

The digital twin must mirror the **correct heuristic at each site**, not assume a single ERP across the network.

#### Data Model Extension

The `site` table (or a new `site_planning_config` table) must carry:

```
site_planning_config:
  site_id              FK → site
  product_group_id     FK → product_hierarchy (nullable — site-wide if null)
  erp_system           ENUM: SAP_S4HANA, SAP_ECC, SAP_IBP, D365_FO, D365_SCM,
                             ODOO_CE, ODOO_EE, KINAXIS, O9, BLUE_YONDER,
                             MANUAL, SPREADSHEET
  erp_version          VARCHAR (e.g., "S/4HANA 2023", "10.0.39", "17.0")
  planning_method      ENUM: MRP, DDMRP, KANBAN, ROP, MANUAL, EXTERNAL_APS
  mrp_type             VARCHAR (e.g., "PD", "VB", "VM" for SAP; "2", "3" for D365 coverage code)
  lot_sizing           VARCHAR (e.g., "EX", "FX", "WB", "GR" for SAP; "Period", "MinMax" for D365)
  forecast_consumption VARCHAR (e.g., "VRMOD=2,VINT1=30,VINT2=15" for SAP; null for D365/Odoo)
  allocation_method    VARCHAR (e.g., "fair_share_A", "priority_waterfall", "quota_60_30_10")
  push_deployment      VARCHAR (e.g., "push_by_demand", "push_to_target_stock", null for pull-only)
  sourcing_method      VARCHAR (e.g., "priority", "quota", "cost_based")
  time_fence_config    JSON (e.g., {"fxhor": 14, "firming": 7, "frozen": 3})
  effective_from       DATE
  effective_to         DATE (nullable — current if null)
```

**Key design principles**:
- **Per product-group at a site**: Different product families at the same plant may use different planning methods (e.g., A-items use DDMRP, C-items use basic ROP)
- **Temporal versioning**: When a site migrates from ECC to S/4HANA, the effective dates capture which heuristic to use for historical simulation vs current
- **Sub-network grouping**: Sites sharing the same ERP/APS form a "planning domain". Cross-domain interactions (e.g., SAP plant supplying D365 DC) are handled via the DAG's transportation lanes — each side runs its own heuristic, but the demand signal propagates via DRP/deployment

#### Dispatch Logic

```python
def simulate_site(site_id: str, product_id: str, state: SiteState, day: int):
    """Dispatch to the correct heuristic based on site's ERP/APS config."""
    config = get_site_planning_config(site_id, product_id, day)

    # 1. Netting method (which demand triggers replenishment)
    net_req = dispatch_netting(state, config)

    # 2. Lot sizing (how much to order)
    order_qty = dispatch_lot_sizing(net_req, config)

    # 3. Order modifications (MOQ, rounding, max, pack size)
    order_qty = apply_order_modifications(order_qty, config)

    # 4. Time fence check (suppress if inside frozen zone)
    order_qty, order_date = apply_time_fences(order_qty, day, config)

    # 5. Source selection (which supplier / which lane)
    source = dispatch_sourcing(order_qty, site_id, product_id, config)

    # 6. Transport mode (regular vs expedite)
    transport = dispatch_transport(order_qty, source, site_id, config)

    return PlannedOrder(qty=order_qty, date=order_date, source=source, transport=transport)
```

#### Why This Matters for Training

TRM agents must learn **per-site** because the heuristic they're compensating for differs by site. An agent trained on SAP VB (reorder point) failures will make bad decisions at a D365 DDMRP site — the failure modes are completely different. The per-site ERP config ensures:

1. **Training data fidelity**: Each site's simulation runs the correct heuristic
2. **Agent specialization**: TRMs can learn site-specific failure patterns
3. **Transfer learning**: Sites with the same ERP/config can share training data
4. **Migration support**: When a site changes ERP (e.g., ECC→S/4HANA), the new heuristic is used from the migration date; agents retrain on the new failure patterns

### 8A.10 Updated Implementation Roadmap

| Priority | Heuristic | Category | Effort |
|----------|-----------|----------|--------|
| **P0** | Reorder Point (s,S) + BOM + Lead Time | Site MRP | ✅ Done |
| **P1** | Lot sizing (L4L, FX, HB, WB/MB) | Site MRP | 6 days |
| **P1** | BOM explosion with scrap | Site MRP | 2 days |
| **P1** | MOQ + order multiple + max qty | Order Modification | 2 days |
| **P1** | Fair share + priority allocation | Allocation | 3 days |
| **P1** | Per-site ERP config data model | Architecture | 3 days |
| **P2** | Deterministic MRP (PD) + forecast consumption (VRMOD) | Site MRP (SAP) | 8 days |
| **P2** | DDMRP buffer zones + net flow | Site MRP (D365/SAP) | 5 days |
| **P2** | Time fences (SAP FXHOR + D365 three-fence) | Site MRP | 3 days |
| **P2** | Quota-based sourcing (SAP rating algorithm) | Sourcing | 3 days |
| **P2** | Push deployment (ATD + 4 push rules) | Network | 5 days |
| **P2** | D365 positive/negative days | Site MRP (D365) | 1 day |
| **P3** | Dynamic lot sizing (Silver-Meal, PPB, Wagner-Whitin, Groff) | Site MRP | 5 days |
| **P3** | Transportation mode selection (regular/expedite/consolidation) | Network | 3 days |
| **P3** | Rounding profiles + pack size + FCL/FTL fill | Order Modification | 3 days |
| **P3** | DRP bottom-up network planning | Network | 5 days |
| **P3** | RCCP capacity + scheduling priority rules | Capacity | 4 days |
| **P4** | Multi-echelon safety stock (Graves-Willems DP) | Network SS | 8 days |
| **P4** | Seasonal SS + dynamic SS + ABC/XYZ differentiation | Site SS | 4 days |
| **P4** | Kanban trigger + TPOP + event-driven replan | Reorder Triggers | 4 days |
| **P4** | Storage constraint logic (overflow routing, production gating) | Capacity | 4 days |
| **P4** | Glenday Sieve in simulation (exists in TRM, not in sim) | Production | 2 days |
| **P4** | S&OP disaggregation (proportional + priority + fair share) | Network | 2 days |
| **Total P0+P1** | | | **~16 days** |
| **Total P0-P2** | | | **~41 days** |
| **Total P0-P3** | | | **~57 days** |
| **Total All** | | | **~79 days** |

### 8A.11 Validation Strategy

For each implemented heuristic:

1. **Unit test with known inputs**: Fixed demand vector, known parameters, compare against hand-calculated expected output
2. **Regression test against ERP**: Extract a representative scenario from the customer's ERP (via staging). Run both the ERP's MRP and the mirror. Compare planned orders (qty, date, type) — they must match within rounding tolerance
3. **Stochastic divergence test**: Run 100 MC trials with the mirror. Verify that the mean of stochastic outcomes converges to the deterministic output (law of large numbers check)
4. **Cross-ERP consistency**: For equivalent configurations (SAP DISLS=EX ≡ D365 CoverageCode=2 ≡ Odoo default), verify identical outputs
5. **Allocation regression**: For shortage scenarios, verify that the allocation method produces the same customer-level quantities as the ERP's native allocation engine (SAP BOP, D365 priority planning)
6. **Push deployment regression**: For surplus scenarios, verify push quantities match SAP APO deployment output for the same ATD and fair share rule

### 8A.12 Creating New ERP-Specific Heuristics

To add support for a new ERP or APS system, follow this process:

**Step 1 — Document the ERP's algorithm**: Read vendor docs (closed-source) or source code (Odoo). Document as pseudocode with explicit parameter references.

**Step 2 — Identify config parameters**: Map ERP config fields to heuristic function inputs. Ensure extraction by connector and persistence.

**Step 3 — Implement as pure function**: Input `SiteState` + `ERPConfig` → Output `order_qty` + side-effect records. No database access.

**Step 4 — Register in dispatch map**: Add to `compute_replenishment()`, lot sizing, and post-processing dispatchers.

**Step 5 — Validate against ERP output**: Zero-variance mirror vs ERP deterministic run. Discrepancies are bugs.

**Step 6 — Configure per tenant**: Provisioning reads customer's ERP config → per product-site heuristic dispatch via `site_planning_config`.

---

---

## 8B. Baseline Data Creation from ERP/APS

The digital twin cannot run without a **baseline** — the complete set of topology, planning parameters, inventory positions, demand patterns, and cost data that define the customer's supply chain. This section defines how baselines are created from each ERP/APS, and what to do when no ERP instance is available.

### 8B.1 What the Baseline Must Contain

| Category | Data | Minimum Viable | Full Fidelity |
|----------|------|----------------|---------------|
| **Topology** | Sites, transportation lanes, master types | ≥1 internal site + connectivity | All sites with geographic coordinates, capacities, calendars |
| **Products** | Product master, UoM, unit cost | ≥1 product per site | Full catalog with ABC classification, product hierarchy |
| **BOMs** | Bill of materials (parent → component) | Flat BOM for manufacturers | Multi-level with scrap rates, alternates, yield factors |
| **Planning Parameters** | MRP type, lot sizing, ROP, SS, time fences | ROP + SS + order-up-to per product-site | Full MARC/ReqItemTable/orderpoint per product-site (see §8C gap audit) |
| **Inventory Positions** | On-hand qty, reserved, in-transit | On-hand per product-site | Dimensional inventory (site/warehouse/batch/serial) |
| **Open Orders** | POs, SOs, MOs with quantities and dates | Current open POs and SOs | Full order book with schedule lines, confirmations, delivery status |
| **Demand History** | Historical demand for stochastic fitting | ≥12 months outbound order history | 24-36 months with seasonal decomposition, promotional flags |
| **Lead Time History** | Actual vs planned lead times | Vendor lead times from master | Historical PO-to-GR actuals for distribution fitting (P5/median/P95) |
| **Forecasts** | Demand forecasts with uncertainty | P50 per product-site | P10/P50/P90 with forecast method, version, horizon |
| **Costs** | Holding, stockout, ordering | Unit cost (holding = 25%/yr) | Full cost-to-serve: holding, backlog, ordering, expediting, transport |
| **Sourcing Rules** | Vendor/source assignments | Primary vendor per product | Multi-source with priorities, quotas, lead times, MOQs |
| **Capacity** | Production and storage limits | Infinite (no constraint) | Finite capacity per resource with calendars, efficiency rates |

### 8B.2 Baseline Creation by Source

#### Path 1: Live ERP Connection (Preferred)

```
Customer's ERP Instance (SAP/D365/Odoo)
    ↓ RFC / OData / JSON-RPC / HANA SQL
ERP Connector (already implemented: 11K LOC SAP, D365, Odoo)
    ↓
Staging Schema (sap_staging / d365_staging / odoo_staging)
    ↓ JSONB rows preserved for audit trail + delta detection
Config Builder (SAP: 3,762 LOC / D365: ~400 LOC / Odoo: ~400 LOC)
    ↓ 8-step pipeline: company → sites → products → lanes → partners → BOMs → planning data
AWS SC Data Model (public schema)
    ↓
Provisioning Pipeline (14 steps)
    ↓
Digital Twin Ready
```

**Data extraction frequencies**: Master (weekly), Transaction (daily), CDC (hourly).

**What each ERP connector extracts**:

| | SAP | D365 | Odoo |
|---|---|---|---|
| **Tables/Entities** | 62 (30 master, 21 txn, 11 CDC) | 42 (24 master, 11 txn, 7 CDC) | 27 models |
| **Connection Methods** | RFC, OData, HANA SQL, CSV | OData v4, DMF, CSV | JSON-RPC, XML-RPC, CSV |
| **Planning Params** | MARC (23 fields mapped) | ItemCoverageSettings (19 fields mapped) | orderpoint (10 fields mapped) |
| **Config Builder** | Complete 8-step | Partial (inventory method incomplete) | Partial |

#### Path 2: CSV Export (No Live Connection)

When the customer can't provide live ERP access (security, firewall, on-premise without Cloud Connector):

```
Customer exports CSV files from ERP
    ↓ Drop into imports/{TENANT_NAME}/{ERP_VARIANT}/{YYYY-MM-DD}/
Folder watcher (APScheduler every 6h or manual trigger)
    ↓ Filename normalization, pandas dtype=str, column uppercase
Staging Schema (same JSONB format as live extraction)
    ↓
Config Builder (same pipeline)
    ↓
AWS SC Data Model → Provisioning → Digital Twin
```

**Requirements**: One CSV per table (MARA.csv, EKKO.csv, etc.). Optional MANIFEST.json with metadata. Column names must match ERP field names (the field mapping service handles translation).

#### Path 3: Synthetic Data Generator (No ERP at All)

When no customer ERP data exists (demos, trials, POCs, new implementations):

```
Admin selects company archetype (Retailer / Distributor / Manufacturer)
    ↓ POST /api/v1/synthetic-data/generate  OR  Claude Wizard chat
Synthetic Data Generator (already implemented)
    ↓ Generates complete: sites, products, lanes, BOMs, forecasts, policies, hierarchies
AWS SC Data Model → Provisioning → Digital Twin
```

**Three archetypes**:
- **Retailer**: 2 CDCs → 6 RDCs → 50 stores, 200 SKUs, seasonal demand
- **Distributor**: 2 NDCs → 8 RDCs → 20 LDCs, 720 SKUs, trending demand
- **Manufacturer**: 3 plants → sub-assembly → FG DCs → RDCs, 160 SKUs, promotional spikes

**Limitation**: Synthetic data uses generic heuristics (ROP/order-up-to), not ERP-specific MRP types or coverage codes. The digital twin will learn from generic heuristic failures, not the customer's specific ERP failures. Useful for demos and initial training, not for production deployment.

#### Path 4: Manual Parameter Entry (Hybrid)

When partial ERP data exists but planning parameters must be entered manually:

```
Customer provides spreadsheet with planning parameters
    ↓ Upload via Admin UI (TenantManagement or StochasticParamsEditor)
Manual entry to InvPolicy / SourcingRules / TransportationLane
    ↓
Provisioning → Digital Twin
```

**When this is needed**: New ERP implementation (planning parameters haven't been configured yet), migration between ERPs (old system decommissioned, new not yet live), or APS overlay (planning done in Kinaxis/o9/Blue Yonder, not in the base ERP).

#### Path 5: Industry Templates (Cold Start Without Customer Data)

When no customer data exists AND the archetype generator is too generic:

```
Select industry template (e.g., "Pharmaceutical Manufacturer" or "FMCG Distributor")
    ↓
Industry-calibrated parameters:
  - Demand CoV by product category (§3.3 industry benchmarks)
  - Lead time distributions (§3.2 nine distribution classes)
  - Safety stock policies (service level by ABC class)
  - Typical network topology (plants/DCs/warehouses)
  - Industry-standard lot sizing (MOQ, pack sizes, container fill)
    ↓
Synthetic generator with industry-specific overrides
    ↓
AWS SC Data Model → Provisioning → Digital Twin
```

### 8B.3 What to Do Without an ERP Instance

| Scenario | Recommended Path | Quality | Limitation |
|----------|-----------------|---------|-----------|
| **Customer has live ERP, grants access** | Path 1 (live connection) | Highest — real parameters, real history | None |
| **Customer has ERP, no live access** | Path 2 (CSV export) | High — real parameters, possibly stale | No CDC, manual refresh |
| **Customer has ERP, only partial access** | Path 2 + Path 4 (CSV + manual) | Medium — real topology, estimated parameters | Parameters may not match actual ERP config |
| **New implementation, no ERP yet** | Path 5 (industry template) | Low-Medium — industry-calibrated but not customer-specific | TRM agents train on generic heuristics |
| **Demo / POC / Trial** | Path 3 (synthetic) | Low — demo quality | Not representative of any specific customer |
| **Customer uses external APS** (Kinaxis/o9/Blue Yonder) | Path 2 (CSV from APS) + Path 4 (manual planning params) | Medium — depends on what APS exports | APS planning logic is proprietary and hard to mirror |

**Key principle**: The digital twin's value is proportional to how faithfully it mirrors the customer's actual planning heuristics. A synthetic baseline demonstrates the platform's capabilities. A live ERP baseline delivers measurable improvement.

---

## 8C. ERP Planning Parameter Gap Audit

**CRITICAL**: This section documents the gap between what the heuristic library (§8A) needs and what the platform currently extracts and stores. Many parameters are **extracted from ERPs but never persisted** to the Autonomy database — they exist in staging JSONB but are lost when the config builder runs.

### 8C.1 SAP MARC Field Audit (23 Fields)

| # | MARC Field | Meaning | Extracted? | Stored in DB? | Used by Sim? | Gap |
|---|-----------|---------|:---:|:---:|:---:|-----|
| 1 | `DISMM` | MRP Type (PD/VB/VM/VV/ND) | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 2 | `DISPO` | MRP Controller | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 3 | `DISLS` | Lot Sizing (EX/FX/HB/WB/GR/SP/OP) | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 4 | `BESKZ` | Procurement Type (E/F) | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 5 | `SOBSL` | Special Procurement Key | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 6 | `MINBE` | Reorder Point | ✅ | ✅ `reorder_point` | ✅ | ✓ Complete |
| 7 | `EISBE` | Safety Stock | ✅ | ✅ `ss_quantity` | ✅ | ✓ Complete |
| 8 | `MABST` | Order-Up-To / Max Stock | ✅ | ✅ `order_up_to_level` | ✅ | ✓ Complete |
| 9 | `LOSGR` | Fixed Lot Size | ✅ | ✅ `lot_size` | ❌ | Stored but UNUSED |
| 10 | `BSTMI` | Min Lot Size | ✅ | ✅ `min_order_quantity` | ❌ | Stored but UNUSED |
| 11 | `BSTMA` | Max Lot Size | ✅ | ✅ `max_order_quantity` | ❌ | Stored but UNUSED |
| 12 | `BSTRF` | Rounding Value | ✅ | ✅ `fixed_order_quantity` | ❌ | Stored but UNUSED |
| 13 | `RDPRF` | Rounding Profile | ❌ | ❌ | ❌ | **NOT EXTRACTED** |
| 14 | `PLIFZ` | Planned Delivery Time | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 15 | `DZEIT` | In-House Production Time | ❌ | ❌ | ❌ | **NOT EXTRACTED** |
| 16 | `WEBAZ` | GR Processing Time | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 17 | `SHZET` | Safety Time (days) | ❌ | ❌ | ❌ | **NOT EXTRACTED** |
| 18 | `VRMOD` | Consumption Mode (1-5) | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 19 | `VINT1` | Backward Consumption Period | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 20 | `VINT2` | Forward Consumption Period | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 21 | `FXHOR` | Planning Time Fence | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 22 | `STRGR` | Planning Strategy Group | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 23 | `AUSSS` | Assembly Scrap % | ❌ | ❌ | ❌ | **NOT EXTRACTED** |

**BOM-level**: `STPO.AUSCH` (component scrap %) → ✅ Extracted, ✅ Stored as `ProductBom.scrap_percentage`, ❌ NOT used by simulation.

**Summary**: 15/23 extracted, 7/23 stored, 3/23 used by simulation. **12 fields are mapped for extraction but never persisted.**

### 8C.2 D365 ItemCoverageSettings Audit (19 Fields)

| # | D365 Field | Meaning | Extracted? | Stored? | Used? | Gap |
|---|-----------|---------|:---:|:---:|:---:|-----|
| 1 | `CoverageCode` | MRP type (0-4) | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 2 | `PlannedOrderType` | Purchase/Production/Transfer | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 3 | `MinInventOnhand` | Reorder Point | ✅ | ✅ `reorder_point` | ✅ | ✓ Complete |
| 4 | `MaxInventOnhand` | Max Stock | ✅ | ✅ `order_up_to_level` | ✅ | ✓ Complete |
| 5 | `SafetyStockQuantity` | Safety Stock | ✅ | ✅ `ss_quantity` | ✅ | ✓ Complete |
| 6 | `StandardOrderQuantity` | Fixed Lot Size | ✅ | ✅ `fixed_order_quantity` | ❌ | Stored but UNUSED |
| 7 | `MinimumOrderQuantity` | MOQ | ✅ | ✅ `min_order_quantity` | ❌ | Stored but UNUSED |
| 8 | `MaximumOrderQuantity` | Max Order Qty | ✅ | ✅ `max_order_quantity` | ❌ | Stored but UNUSED |
| 9 | `Multiple` | Order Rounding | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 10 | `LeadTimePurchase` | Purchase LT Override | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 11 | `LeadTimeProduction` | Production LT Override | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 12 | `LeadTimeTransfer` | Transfer LT Override | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 13 | `CoverageTimeFence` | Planning Horizon | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 14 | `LockingTimeFence` | Firming Fence | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 15 | `FrozenTimeFence` | Frozen Fence | ❌ | ❌ | ❌ | **NOT EXTRACTED** |
| 16 | `MaxPositiveDays` | Early Supply Tolerance | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 17 | `MaxNegativeDays` | Late Supply Tolerance | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 18 | `FulfillMinimum` | Min Fill Policy | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 19 | `PreferredVendor` | Primary Source | ✅ | ❌ | ❌ | MAPPED but NOT STORED |

**Summary**: 18/19 extracted, 6/19 stored, 3/19 used by simulation.

### 8C.3 Odoo Orderpoint Audit (10 Fields)

| # | Odoo Field | Meaning | Extracted? | Stored? | Used? | Gap |
|---|-----------|---------|:---:|:---:|:---:|-----|
| 1 | `trigger` | auto/manual | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 2 | `product_min_qty` | Reorder Point | ✅ | ✅ `reorder_point` | ✅ | ✓ Complete |
| 3 | `product_max_qty` | Order-Up-To | ✅ | ✅ `order_up_to_level` | ✅ | ✓ Complete |
| 4 | `qty_multiple` | Order Multiple | ✅ | ❌ | ❌ | **MAPPED but NOT STORED** |
| 5 | `route_id` | Buy/Manufacture/Resupply | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 6 | `produce_delay` | Manufacturing LT | ✅ | ❌ | ❌ | MAPPED but NOT STORED |
| 7 | `purchase_delay` | Purchase LT (via supplierinfo) | ✅ | ✅ `vendor_lead_time` | ✅ | ✓ Complete |
| 8 | `seller_ids` | Vendor priority list | ⚠️ Partial | ✅ via `SourcingRules` | ✅ | Partial |
| 9 | `bom_id` | BOM reference | ✅ | ✅ `ProductBom` | ✅ | ✓ Complete |
| 10 | DDMRP fields | OCA buffer params | ❌ | ❌ | ❌ | **NOT EXTRACTED** |

**Summary**: 8/10 extracted, 4/10 stored, 5/10 used.

### 8C.4 The Data Loss Pipeline

The root problem: parameters flow through a **three-stage pipeline** where most are lost at stage 2:

```
Stage 1: ERP → Staging (JSONB)     ← Most parameters ARE extracted here
Stage 2: Staging → AWS SC Model    ← LOSS: config builders only persist ~6 core fields
Stage 3: AWS SC → Simulation       ← Only 3-4 fields actually used
```

**12 SAP fields, 12 D365 fields, and 5 Odoo fields** are extracted and staged but **never persisted** to any Autonomy table. They exist in `sap_staging.rows` / `d365_staging.rows` / `odoo_staging.rows` as JSONB, but the config builders don't read them.

### 8C.5 Storage Approach Options

The InvPolicy table currently has **no columns** for MRP type, lot sizing procedure, forecast consumption mode, time fences, or other ERP-specific planning control fields. Three approaches:

#### Option A: Add Columns to InvPolicy (Simple, ERP-Agnostic)

Add generic columns that map across all ERPs:

```sql
ALTER TABLE inv_policy ADD COLUMN planning_method VARCHAR(20);
    -- SAP: DISMM (PD/VB/VM/ND) | D365: CoverageCode (0-4) | Odoo: trigger (auto/manual)

ALTER TABLE inv_policy ADD COLUMN lot_sizing_procedure VARCHAR(20);
    -- SAP: DISLS (EX/FX/HB/WB/GR/SP/OP) | D365: implicit from CoverageCode | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN procurement_type VARCHAR(20);
    -- SAP: BESKZ (E/F) | D365: PlannedOrderType | Odoo: route_id

ALTER TABLE inv_policy ADD COLUMN rounding_quantity DOUBLE PRECISION;
    -- SAP: BSTRF | D365: Multiple | Odoo: qty_multiple

ALTER TABLE inv_policy ADD COLUMN planning_time_fence_days INTEGER;
    -- SAP: FXHOR | D365: CoverageTimeFence | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN firming_time_fence_days INTEGER;
    -- SAP: N/A (implicit in FXHOR) | D365: LockingTimeFence | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN frozen_time_fence_days INTEGER;
    -- SAP: N/A | D365: FrozenTimeFence | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN safety_time_days INTEGER;
    -- SAP: SHZET | D365: N/A | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN positive_days INTEGER;
    -- SAP: N/A | D365: MaxPositiveDays | Odoo: N/A

ALTER TABLE inv_policy ADD COLUMN negative_days INTEGER;
    -- SAP: N/A | D365: MaxNegativeDays | Odoo: N/A
```

**Pros**: Simple, queryable, type-safe, works with existing SQLAlchemy patterns.
**Cons**: Many NULL columns per ERP (SAP doesn't use positive_days; D365 doesn't use VRMOD). Schema grows with each new ERP.

#### Option B: JSONB Extension Column per Entity (Flexible, ERP-Specific)

Add a single JSONB column to each entity that stores ERP-specific parameters:

```sql
ALTER TABLE inv_policy ADD COLUMN erp_planning_params JSONB DEFAULT '{}';
-- SAP example:
-- {"dismm": "PD", "disls": "WB", "vrmod": 2, "vint1": 30, "vint2": 15,
--  "fxhor": 14, "strgr": "40", "beschz": "F", "shzet": 5, "ausss": 0.02}

-- D365 example:
-- {"coverage_code": 2, "planned_order_type": 0, "lt_purchase": 5,
--  "lt_production": 3, "coverage_fence": 90, "firming_fence": 14,
--  "positive_days": 7, "negative_days": 3, "preferred_vendor": "V001"}

-- Odoo example:
-- {"trigger": "auto", "qty_multiple": 12, "route_id": 5,
--  "produce_delay": 3, "ddmrp_lt_mul": 0.5, "ddmrp_ss_mul": 0.3}

ALTER TABLE product_bom ADD COLUMN erp_bom_params JSONB DEFAULT '{}';
-- {"assembly_scrap_pct": 0.02, "phantom": false, "alternate_bom_id": "BOM-002"}

ALTER TABLE production_process ADD COLUMN erp_process_params JSONB DEFAULT '{}';
-- {"gr_processing_time": 1, "scheduling_margin_key": "001"}

ALTER TABLE transportation_lane ADD COLUMN erp_lane_params JSONB DEFAULT '{}';
-- {"transit_mode": "TRUCK", "expedite_available": true, "expedite_lt_factor": 0.5}
```

**Pros**: Infinitely extensible — new ERP fields added without schema migration. Each ERP stores only its relevant fields. One column per entity regardless of ERP count. The heuristic library reads from this JSONB at simulation time.
**Cons**: Not type-safe (JSONB is untyped). Not queryable with standard ORM patterns (requires `->` operators). No referential integrity on values.

#### Option C: Separate Per-ERP Planning Config Table (Normalized, Clean)

Create `site_planning_config` (already proposed in §8A.9) as a dedicated table:

```sql
CREATE TABLE site_planning_config (
    id SERIAL PRIMARY KEY,
    config_id INTEGER REFERENCES supply_chain_configs(id),
    site_id VARCHAR REFERENCES site(id),
    product_id VARCHAR REFERENCES product(id),
    product_group_id VARCHAR,  -- nullable, site-wide if null

    -- ERP identification
    erp_system VARCHAR(30) NOT NULL,  -- SAP_S4HANA, D365_FO, ODOO_CE, etc.
    erp_version VARCHAR(30),

    -- Universal planning control (cross-ERP)
    planning_method VARCHAR(20),      -- PD/VB/VM/ND (SAP) or 0-4 (D365) or auto/manual (Odoo)
    lot_sizing VARCHAR(20),           -- EX/FX/HB/WB/GR/SP/OP (SAP) or implicit (D365)
    procurement_type VARCHAR(20),     -- E/F (SAP), Purchase/Production/Transfer (D365), route (Odoo)

    -- ERP-specific parameters (all optional)
    erp_params JSONB DEFAULT '{}',    -- Everything else in a single JSONB

    effective_from DATE,
    effective_to DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Pros**: Clean separation of concerns — AWS SC entities stay pure; ERP planning logic isolated to its own table. Supports per-site-per-product-group config (§8A.9 multi-ERP requirement). Temporal versioning for ERP migrations. Combines typed columns for universal fields with JSONB for ERP-specific fields.
**Cons**: Additional JOIN required when simulation loads config. Must be populated by config builders (new code).

### 8C.6 Recommended Approach

**Option C (hybrid table)** is recommended because:

1. **Preserves AWS SC compliance** — the 35 core entities remain untouched
2. **Supports multi-ERP per network** — different ERPs at different sites (§8A.9)
3. **Typed where it matters** — `planning_method`, `lot_sizing`, `procurement_type` are typed columns (queryable, validated)
4. **Flexible where needed** — `erp_params` JSONB holds SAP VRMOD/VINT, D365 positive/negative days, Odoo DDMRP fields
5. **Temporally versioned** — when a site migrates from ECC to S/4HANA, both configs coexist with date ranges
6. **Single JOIN** — simulation `_ConfigLoader` joins `site_planning_config` to get the complete heuristic dispatch config

**Additionally**: Add `erp_planning_params JSONB` to `InvPolicy` (Option B) as a **secondary store** for parameters that are tightly coupled to the inventory policy record (like rounding_quantity, safety_time). This avoids forcing a JOIN for simple per-product-site lookups.

### 8C.7 Extraction Gaps to Close

Fields that need to be **added to extraction** (currently NOT extracted):

| ERP | Field | Why Needed |
|-----|-------|-----------|
| SAP | `RDPRF` (Rounding Profile) | Scaled rounding by threshold — needed for order modification rules (§8A.6) |
| SAP | `DZEIT` (In-House Production Time) | Manufacturing lead time for backward scheduling |
| SAP | `SHZET` (Safety Time in days) | Safety lead time buffer — adds to effective lead time |
| SAP | `AUSSS` (Assembly Scrap %) | Assembly-level yield loss for BOM explosion (§8A.1.6) |
| D365 | `FrozenTimeFence` | Most restrictive fence — needed for §8A.1.5 time fence logic |
| Odoo | DDMRP fields (`ddmrp_lt_mul`, `ddmrp_ss_mul`, `ddmrp_po_mul`) | Buffer profile params if OCA DDMRP installed |

### 8C.8 Config Builder Updates Required

Each config builder must be updated to persist ERP planning parameters to the new `site_planning_config` table:

| Config Builder | Current State | Update Needed |
|---------------|--------------|---------------|
| **SAP** (`sap_config_builder.py`) | Extracts 15/23 MARC fields; persists only 7 to InvPolicy | Read all MARC fields from staging → populate `site_planning_config.erp_params` |
| **D365** (`d365/config_builder.py`) | Extracts 18/19 fields; persists only 6 to InvPolicy | Read ItemCoverageSettings from staging → populate `site_planning_config` |
| **Odoo** (`odoo/config_builder.py`) | Extracts 8/10 fields; persists only 4 | Read orderpoint + supplierinfo → populate `site_planning_config` |
| **Synthetic** (`synthetic_data_generator.py`) | Generates generic ROP/s,S only | Add ERP profile selection → generate `site_planning_config` with realistic MRP type + lot sizing |

### 8C.9 Simulation _ConfigLoader Update

The `_ConfigLoader` in `simulation_calibration_service.py` must be extended to:

1. **JOIN** `site_planning_config` when loading site configs
2. **Pass** `erp_system`, `planning_method`, `lot_sizing`, and `erp_params` to each `_SiteSimConfig`
3. **Dispatch** to the correct heuristic function based on these fields (§8A.1.1 unified dispatch)

Currently `_SimSite.compute_replenishment_order()` has a hardcoded ROP check. After the update, it calls `compute_replenishment(state, config)` which dispatches based on `config.planning_method`.

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

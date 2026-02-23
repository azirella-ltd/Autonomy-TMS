# Order Execution & Supply Chain Execution Management

## Comprehensive Reference Guide

---

## 1. Overview

### Supply Chain Execution (SCE)

Supply Chain Execution encompasses all processes that convert plans into actions — purchasing materials, manufacturing products, fulfilling orders, and managing the physical flow of goods. SCE bridges the gap between planning (what to do) and operations (doing it).

```
Planning Layer:  S&OP → MPS → MRP → DRP
                          ↓
Execution Layer: Purchase Orders → Manufacturing Orders → Transfer Orders
                          ↓
Physical Layer:  Receiving → Production → Warehousing → Shipping → Delivery
```

---

## 2. Purchase Order Execution

### 2.1 PO Lifecycle

```
Planned Order (MRP output)
    ↓ Release
Purchase Requisition
    ↓ Approve
Purchase Order
    ↓ Send to Supplier
PO Acknowledgment (Supplier confirms)
    ↓ Track
Advanced Shipping Notice (ASN)
    ↓ Receive
Goods Receipt (GR)
    ↓ Inspect
Quality Check (if required)
    ↓ Accept/Reject
Put-Away → Inventory Update
    ↓ Match
Invoice Verification (3-way match: PO, GR, Invoice)
    ↓ Pay
Payment
```

### 2.2 PO Exception Types

| Exception | Detection | Resolution |
|-----------|-----------|------------|
| **Late delivery** | PO due date < today, no GR | Expedite, find alternate supplier |
| **Quantity variance** | GR qty ≠ PO qty (outside tolerance) | Accept partial, reorder, reject |
| **Quality rejection** | QC inspection fails | Return to vendor, accept with concession |
| **Price variance** | Invoice price ≠ PO price | Negotiate, accept with approval |
| **Wrong item** | GR item ≠ PO item | Return, re-ship correct item |
| **Early delivery** | GR date significantly before need date | Accept (storage cost) or refuse |
| **ASN mismatch** | ASN contents ≠ actual shipment | Reconcile, adjust receipt |

### 2.3 Supplier Performance Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **On-Time Delivery (OTD)** | POs received on/before due date / Total POs | > 95% |
| **Quality Rate** | Accepted lots / Total received lots | > 99% |
| **Quantity Accuracy** | POs with correct quantity / Total POs | > 98% |
| **Lead Time Reliability** | Std dev of actual lead time / Mean lead time | < 0.2 |
| **Perfect Receipt** | OTD × Quality × Quantity Accuracy | > 90% |
| **Fill Rate** | Units received on-time / Units ordered | > 97% |
| **DIFOT** | Delivered In Full On Time | > 93% |

---

## 3. Manufacturing Order Execution

### 3.1 Manufacturing Order Lifecycle

```
Planned Production Order (MPS/MRP output)
    ↓ Convert/Release
Manufacturing Order (MO)
    ↓ Schedule
Detailed Scheduling (finite capacity, sequencing)
    ↓ Issue Materials
Material Staging / Picking
    ↓ Start
Shop Floor Execution
    ↓ Track
Operation Reporting (quantity, time, scrap)
    ↓ Complete
Quality Inspection
    ↓ Accept
Goods Receipt to Finished Goods
    ↓ Close
MO Settlement (cost allocation)
```

### 3.2 Shop Floor Control

**Dispatching Rules** (for job sequencing at work centers):

| Rule | Logic | Best For |
|------|-------|----------|
| **FIFO** | First In, First Out | Fairness, simple |
| **SPT** | Shortest Processing Time first | Minimize avg flow time |
| **EDD** | Earliest Due Date first | Minimize maximum lateness |
| **CR** | Critical Ratio = time remaining / work remaining | Balance urgency |
| **SLACK** | Minimum slack = due date - current date - remaining processing | Minimize tardiness |
| **WSPT** | Weighted SPT (weight = priority / processing time) | Weighted completion time |

**Critical Ratio (CR)**:
```
CR = (Due Date - Current Date) / Remaining Processing Time

CR < 1.0: Behind schedule — expedite
CR = 1.0: On schedule
CR > 1.0: Ahead of schedule — could defer

Priority: Process jobs with lowest CR first
```

### 3.3 Production Reporting

| Report Type | Content | Frequency |
|------------|---------|-----------|
| **Operation Start** | Actual start time, setup time | Per operation |
| **Operation Complete** | Actual finish, quantity good, quantity scrapped | Per operation |
| **Material Consumption** | Actual material used vs planned (backflush or manual) | Per MO |
| **Labor Reporting** | Hours worked, crew size | Per shift/operation |
| **Downtime Reporting** | Reason code, duration | Per occurrence |
| **Quality Reporting** | Inspection results, defect types | Per inspection point |

### 3.4 MO Exception Types

| Exception | Detection | Action Options |
|-----------|-----------|---------------|
| **Material shortage** | Staged qty < required qty | Substitute, partial release, wait |
| **Capacity conflict** | Schedule vs available hours | Overtime, re-sequence, outsource |
| **Quality hold** | In-process QC failure | Rework, scrap, use-as-is (with concession) |
| **Equipment breakdown** | Machine down notification | Maintenance, alternate machine, outsource |
| **Behind schedule** | CR < 0.8 | Expedite, overtime, split order |
| **Yield loss** | Actual yield < planned | Relaunch, add to next batch |
| **Engineering change** | BOM/routing change during production | Evaluate impact, adjust or complete as-is |

---

## 4. Transfer Order Execution

### 4.1 Transfer Order Types

| Type | Description | Use Case |
|------|-------------|----------|
| **Inter-plant** | Between manufacturing plants | Semi-finished goods transfer |
| **Plant-to-DC** | Factory to distribution center | Finished goods deployment |
| **DC-to-DC** | Between distribution centers | Inventory rebalancing |
| **DC-to-Store** | Distribution center to retail store | Store replenishment |
| **Return-to-DC** | Customer/store to returns center | Reverse logistics |

### 4.2 Transfer Order Lifecycle

```
Planned Transfer (DRP/deployment output)
    ↓ Release
Transfer Order (TO)
    ↓ Pick
Warehouse Pick and Pack at source location
    ↓ Ship
Goods Issue at source → In-Transit inventory
    ↓ Track
Transportation and tracking
    ↓ Receive
Goods Receipt at destination
    ↓ Put-Away
Inventory update at destination
```

### 4.3 Consolidation Decisions

```
Multiple small TOs → Consolidate into full truck load

TO-1: 500 units to East DC (partial truck)
TO-2: 300 units to East DC (partial truck)
TO-3: 200 units to East DC (partial truck)

Consolidate → One full truck: 1000 units to East DC
Savings: 2 × truck cost avoided
Trade-off: TO-1 may wait 1-2 days for consolidation window
```

---

## 5. Warehouse Execution

### 5.1 Core Warehouse Processes

| Process | Description | Key Metrics |
|---------|-------------|-------------|
| **Receiving** | Unload, inspect, record goods receipt | Dock-to-stock time |
| **Put-Away** | Move goods to storage location | Put-away accuracy, time |
| **Storage** | Hold inventory in optimized locations | Space utilization, accessibility |
| **Picking** | Select items for outbound orders | Pick accuracy, lines/hour |
| **Packing** | Pack items for shipment | Pack rate, damage rate |
| **Shipping** | Load and dispatch | On-time dispatch rate |
| **Cycle Counting** | Periodic inventory verification | Count accuracy, IRA |

### 5.2 Picking Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| **Discrete** | One order at a time, one picker | Low volume, simple |
| **Batch** | Multiple orders picked together | Medium volume |
| **Zone** | Picker assigned to zone, orders pass through | Large warehouse |
| **Wave** | Batch + zone + timing coordination | High volume, complex |
| **Cluster** | Pick multiple orders into compartmented cart | E-commerce, many small orders |

### 5.3 Storage Strategies

| Strategy | Logic | Trade-off |
|----------|-------|-----------|
| **Random** | Any available location | Max space utilization, complex picking |
| **Fixed** | Dedicated location per SKU | Easy picking, poor space utilization |
| **Class-Based** | ABC zones (fast movers near dock) | Balanced approach |
| **Velocity-Based** | Dynamic slotting by pick frequency | Optimal pick efficiency |
| **FIFO/FEFO** | First-In/First-Expired first out | Required for perishables, lot-tracked |

### 5.4 Inventory Record Accuracy (IRA)

```
IRA = Locations with correct count / Total locations counted × 100%

Target: > 99% for A items, > 97% for B items, > 95% for C items

Causes of Inaccuracy:
  - Receiving errors (wrong qty recorded)
  - Picking errors (wrong item/qty picked)
  - Put-away errors (wrong location)
  - Unrecorded transactions (informal moves)
  - Shrinkage (theft, damage, loss)
  - System timing (transactions not posted)
```

---

## 6. Order Management

### 6.1 Order-to-Cash Process

```
1. Order Entry / EDI / E-Commerce
    ↓
2. Order Validation (credit check, product availability)
    ↓
3. ATP / AATP Check (see ATP guide)
    ↓
4. Order Promising (confirm date, price, qty)
    ↓
5. Order Fulfillment Assignment (which DC/plant)
    ↓
6. Warehouse Execution (pick, pack, ship)
    ↓
7. Shipment / Transportation
    ↓
8. Delivery Confirmation (POD)
    ↓
9. Invoicing
    ↓
10. Cash Collection
```

### 6.2 Order Types

| Order Type | Trigger | Fulfillment |
|-----------|---------|-------------|
| **Standard** | Customer order | Ship from stock |
| **Rush/Expedite** | Urgent customer need | Prioritized fulfillment, possible overnight |
| **Backorder** | Insufficient stock at order time | Ship when available |
| **Drop Ship** | Customer order, supplier ships direct | Supplier → Customer (no warehouse touch) |
| **Blanket/Contract** | Long-term agreement | Release against contract |
| **Intercompany** | Between legal entities in same org | Plant → affiliate |
| **Return** | Customer return authorization | Reverse flow |
| **Sample/Free** | Marketing/sales | No charge, special handling |

### 6.3 Order Prioritization

When multiple orders compete for limited supply:

| Method | Logic | Typical Use |
|--------|-------|-------------|
| **FIFO** | First order received gets served first | Fair, simple |
| **Priority-based** | Customer tier determines priority | Strategic accounts |
| **Revenue/Margin** | Highest revenue/margin served first | Profit maximization |
| **Contractual** | Committed orders before spot | Contract compliance |
| **Penalty-based** | Orders with highest penalty for miss | Risk minimization |
| **AATP** | Pre-allocated by segment | Balanced allocation |

---

## 7. Exception Management

### 7.1 Exception-Based Management

Modern execution systems operate on an **exception basis** — planners/operators focus on anomalies rather than reviewing all transactions.

```
Normal Flow (90-95% of transactions):
    System auto-processes → No human intervention needed

Exception Flow (5-10% of transactions):
    System detects anomaly → Creates alert/worklist item →
    Planner reviews → Takes action → Resolves or escalates
```

### 7.2 Common Exception Categories

| Category | Examples | Severity |
|----------|---------|----------|
| **Supply exceptions** | Late PO, short shipment, quality reject | High |
| **Demand exceptions** | Rush order, cancellation, demand spike | Medium-High |
| **Inventory exceptions** | Stockout, excess, obsolescence, cycle count variance | Medium |
| **Production exceptions** | Machine down, yield loss, material shortage | High |
| **Transport exceptions** | Delayed shipment, damaged goods, carrier no-show | Medium |
| **Quality exceptions** | Hold, recall, non-conformance | Critical |
| **Financial exceptions** | Credit hold, price discrepancy, payment delay | Medium |

### 7.3 Exception Resolution Framework

```
1. DETECT: System identifies deviation from plan
    → Threshold-based (qty, time, cost)
    → Pattern-based (trend, frequency)
    → ML-based (anomaly detection)

2. CLASSIFY: Assign severity and category
    → Critical: Immediate action (customer impact imminent)
    → High: Same-day resolution required
    → Medium: Resolve within planning cycle
    → Low: Monitor, batch resolution

3. DIAGNOSE: Root cause identification
    → What happened?
    → Why did it happen?
    → What is the impact?

4. RESOLVE: Take corrective action
    → Expedite, substitute, reallocate
    → Reschedule, cancel, split
    → Escalate to management

5. LEARN: Feedback for prevention
    → Update parameters (lead times, yields, safety stock)
    → Improve processes (supplier management, quality)
    → Train AI models (exception patterns)
```

---

## 8. Supply Chain Control Tower

### 8.1 Definition

A Supply Chain Control Tower provides **end-to-end visibility** and **proactive exception management** across the supply chain. It integrates data from multiple systems and uses analytics/AI to detect issues early and recommend actions.

### 8.2 Control Tower Capabilities

| Capability | Description |
|-----------|-------------|
| **Visibility** | Real-time view of orders, inventory, shipments across network |
| **Monitoring** | Automated tracking of KPIs against thresholds |
| **Alerting** | Proactive notification of exceptions and risks |
| **Analytics** | Root cause analysis, trend detection, pattern recognition |
| **Simulation** | What-if scenarios for resolution options |
| **Collaboration** | Cross-functional communication and escalation |
| **Automation** | Auto-resolution of low-severity exceptions |
| **Prediction** | ML-based early warning of potential issues |

### 8.3 Control Tower Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Exception Rate** | % of transactions with exceptions | < 5% |
| **Mean Time to Detect (MTTD)** | Time from occurrence to detection | < 1 hour |
| **Mean Time to Resolve (MTTR)** | Time from detection to resolution | < 4 hours (critical) |
| **Auto-Resolution Rate** | % of exceptions resolved without human | > 50% |
| **Escalation Rate** | % of exceptions requiring management | < 10% |
| **Repeat Exception Rate** | Same exception recurring within 30 days | < 5% |

---

## 9. Execution Systems Landscape

### 9.1 System Types

| System | Scope | Key Functions |
|--------|-------|---------------|
| **ERP** | Enterprise-wide | Order management, financials, master data |
| **WMS** | Warehouse | Receiving, storage, picking, shipping |
| **TMS** | Transportation | Route planning, carrier management, tracking |
| **MES** | Manufacturing | Shop floor control, quality, labor tracking |
| **OMS** | Order Management | Order capture, promising, routing, tracking |
| **YMS** | Yard | Dock scheduling, trailer tracking |
| **LMS** | Labor | Workforce planning, performance tracking |

### 9.2 Integration Architecture

```
Planning Systems (IBP, APO, ASCP)
    ↓ Plans, Schedules
ERP (S/4HANA, Oracle, etc.)
    ↓ Orders (PO, MO, TO, SO)
    ├── WMS → Warehouse operations
    ├── TMS → Transportation operations
    ├── MES → Manufacturing operations
    └── OMS → Customer order operations
    ↓ Transactions, Confirmations
Control Tower → Visibility, Exceptions, Analytics
```

---

## 10. Execution KPIs Summary

### Customer-Facing

| KPI | Formula | World-Class |
|-----|---------|------------|
| **OTIF** | On-Time × In-Full | > 95% |
| **Order Cycle Time** | Order receipt to delivery | < 48 hrs |
| **Order Accuracy** | Correct orders / Total orders | > 99% |
| **Customer Complaint Rate** | Complaints / Orders | < 1% |

### Operational

| KPI | Formula | World-Class |
|-----|---------|------------|
| **Inventory Accuracy** | Correct locations / Total counted | > 99% |
| **Dock-to-Stock** | Receipt to available for picking | < 4 hrs |
| **Perfect Order** | OTIF × Damage-free × Doc-accurate | > 90% |
| **Schedule Adherence** | Actual vs planned production | > 95% |
| **OEE** | Availability × Performance × Quality | > 85% |
| **Warehouse Productivity** | Lines picked per labor hour | Industry benchmark |
| **Transportation Cost/Unit** | Total transport cost / Units shipped | Declining trend |

### Financial

| KPI | Formula | Target |
|-----|---------|--------|
| **Days Sales Outstanding** | Receivables / Daily revenue | < 45 days |
| **Days Inventory Outstanding** | Inventory / Daily COGS | < 30 days |
| **Cash-to-Cash Cycle** | DIO + DSO - DPO | < 30 days |
| **Cost to Serve** | Total SC cost / Revenue | < 8% |

---

*Sources: ASCM CPIM Part 2 (Execution & Control Module), ASCM CSCP Learning System, Bartholdi & Hackman "Warehouse & Distribution Science", GS1 Standards, APICS Dictionary (17th ed)*

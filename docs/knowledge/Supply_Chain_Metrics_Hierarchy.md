# Supply Chain Metrics Hierarchy

## Comprehensive Metric Framework Mapped to Powell Cascade & TRM Hive

---

## 1. The Metrics Pyramid

### Gartner Hierarchy of Supply Chain Metrics

The industry-standard framework organizes supply chain metrics into three tiers that cascade from strategic assessment to operational correction:

```
                    ┌─────────────┐
                    │   ASSESS    │  ← Tier 1: Executive health check (3 KPIs)
                    │  Strategic  │     "Is our supply chain healthy?"
                    ├─────────────┤
                    │  DIAGNOSE   │  ← Tier 2: Cash-flow diagnostics (3 KPIs)
                    │  Tactical   │     "Where is value leaking?"
                    ├─────────────┤
                    │   CORRECT   │  ← Tier 3: Operational root cause (11+ KPIs)
                    │ Operational │     "What specific action fixes it?"
                    └─────────────┘
```

### Mapping to SCOR Performance Attributes

| SCOR Attribute | Code | Direction | Customer/Internal |
|---------------|------|-----------|-------------------|
| **Reliability** | RL | Higher = better | Customer-facing |
| **Responsiveness** | RS | Lower = better | Customer-facing |
| **Agility** | AG | Higher = better | Customer-facing |
| **Cost** | CO | Lower = better | Internal |
| **Asset Management** | AM | Higher = better | Internal |
| **Profit** | PR | Higher = better | Internal |
| **Environmental** | EV | Lower = better | External |
| **Social** | SC | Higher = better | External |

### Mapping to Powell Cascade Levels

```
┌──────────────────────────────────────────────────────────────────────────┐
│  S&OP GraphSAGE (CFA) — Weekly/Monthly — Policy Parameters θ           │
│  ────────────────────────────────────────────────────────────────        │
│  ASSESS Tier: Revenue Growth, EBIT Margin, ROCS                        │
│  DIAGNOSE Tier: Inventory Turns, C2C, OTIF                             │
│  Outputs: safety_stock_multiplier, criticality_score, bottleneck_risk   │
├──────────────────────────────────────────────────────────────────────────┤
│  Execution tGNN (CFA/VFA) — Daily — Allocations & Context              │
│  ────────────────────────────────────────────────────────────────        │
│  DIAGNOSE → CORRECT bridge: Exception probability, demand forecast      │
│  Outputs: Priority × Product × Location allocations                     │
│  Metrics: Forecast accuracy (WMAPE), allocation utilization             │
├──────────────────────────────────────────────────────────────────────────┤
│  11 Narrow TRMs (VFA) — Per-Decision — <10ms Execution                  │
│  ────────────────────────────────────────────────────────────────        │
│  CORRECT Tier: Per-agent execution metrics                              │
│  Each TRM emits signals → HiveSignalBus → aggregated in REFLECT phase  │
│  Metrics: Decision accuracy, throughput, override rate, touchless rate   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tier 1 — ASSESS (Strategic Level)

### Purpose
Enable executives to quickly evaluate overall supply chain health and see trade-offs in strategy execution. These 3 KPIs answer: **"Is our supply chain competitive?"**

### 2.1 Revenue Growth

| Metric | Formula | Benchmark |
|--------|---------|-----------|
| **Revenue Growth Rate** | (Revenue_current - Revenue_prior) / Revenue_prior × 100% | Industry dependent |
| **Market Share** | Company revenue / Total market revenue × 100% | Gaining = healthy |
| **New Product Revenue %** | Revenue from products < 2 years old / Total revenue | > 15-25% |

**Powell Mapping**: S&OP GraphSAGE — portfolio management, demand forecast accuracy drives revenue attainment.

### 2.2 Profitability (EBIT Margin)

| Metric | Formula | Benchmark |
|--------|---------|-----------|
| **EBIT Margin** | EBIT / Revenue × 100% | 8-15% manufacturing |
| **Gross Margin** | (Revenue - COGS) / Revenue × 100% | 30-50% manufacturing |
| **Total Cost to Serve** | Total SC costs / Revenue × 100% | 4-12% |
| **SC Cost as % COGS** | SC planning + execution costs / COGS | 2-5% |

**Powell Mapping**: CFA policy parameters (θ) optimize the cost-service-cash trade-off triangle.

### 2.3 Return on Capital / Assets

| Metric | Formula | Benchmark |
|--------|---------|-----------|
| **ROCS** (Return on Capital Employed in SC) | SC Operating Profit / SC Capital Employed | 15-40% |
| **Return on SC Fixed Assets** | (Revenue - COGS - SC Cost) / SC Fixed Assets | 20-50% |
| **Return on Working Capital** | (Revenue - COGS - SC Cost) / Working Capital | 10-30% |
| **EVA** (Economic Value Added) | NOPAT - (Capital × WACC) | Positive = value creation |

**Powell Mapping**: Balance between inventory investment (AM) and service (RL) — directly tuned by S&OP safety stock multipliers.

---

## 3. Tier 2 — DIAGNOSE (Tactical Level)

### Purpose
Provide mid-level view of supply chain performance with focus on cash flow. These metrics serve as diagnostic bridges between strategic outcomes and operational root causes.

### 3.1 Perfect Order Fulfillment (SCOR RL.1.1)

```
Perfect Order = On-Time × In-Full × Damage-Free × Documentation Accurate

POF = % On-Time × % In-Full × % Damage-Free × % Correct Documentation
```

| Component | Formula | World-Class |
|-----------|---------|-------------|
| **On-Time Delivery (OTD)** | Orders delivered ≤ promised date / Total orders | > 95% |
| **In-Full (IF)** | Orders with complete quantity / Total orders | > 97% |
| **Damage-Free** | Orders without damage / Total orders | > 99% |
| **Documentation Accuracy** | Orders with correct docs / Total orders | > 98% |
| **Perfect Order (composite)** | OTD × IF × DF × DA | > 90% |

**Powell Mapping**:
- **S&OP GraphSAGE**: Sets service level targets that cascade to AATP allocation
- **Execution tGNN**: Generates allocations that protect POF for priority segments
- **ATPExecutorTRM**: Per-order promising accuracy (direct impact on OTD)
- **OrderTrackingTRM**: Exception detection prevents POF degradation
- **TOExecutionTRM**: Shipment timing and consolidation (OTD component)

### 3.2 Cash-to-Cash Cycle Time (SCOR AM.1.1)

```
C2C = Days Inventory Outstanding + Days Sales Outstanding - Days Payable Outstanding

DIO = Average Inventory / COGS per day
DSO = Average Receivables / Revenue per day
DPO = Average Payables / COGS per day
```

| Component | Formula | Benchmark |
|-----------|---------|-----------|
| **DIO (Days Inventory)** | Avg Inventory Value / Daily COGS | 20-60 days |
| **DSO (Days Sales Outstanding)** | Avg Receivables / Daily Revenue | 30-50 days |
| **DPO (Days Payable Outstanding)** | Avg Payables / Daily COGS | 30-60 days |
| **C2C Cycle** | DIO + DSO - DPO | 20-60 days |

**Powell Mapping**:
- **InventoryBufferTRM**: Direct lever on DIO (inventory buffer = largest component)
- **POCreationTRM**: Payment timing decisions affect DPO
- **InventoryRebalancingTRM**: Redistributes inventory to reduce total DIO
- **S&OP GraphSAGE**: Sets target DIO via safety_stock_multiplier

### 3.3 Order Fulfillment Cycle Time (SCOR RS.1.1)

```
OFCT = Order receipt → Customer delivery (total elapsed time)

Decomposition:
  Source Cycle Time: Order → Supplier ships
  + Make Cycle Time: Materials → Finished goods
  + Deliver Cycle Time: Ship → Customer receipt
  = Total OFCT
```

| Metric | Formula | Benchmark |
|--------|---------|-----------|
| **OFCT** | Avg time from order to delivery | 1-30 days (industry dependent) |
| **Order Processing Time** | Order entry to release | < 4 hours |
| **Promise Accuracy** | Deliveries on promised date / Total | > 95% |
| **Manufacturing Cycle Time** | Release to completion | Industry dependent |

**Powell Mapping**:
- **ATPExecutorTRM**: Promise date accuracy (order processing component)
- **MOExecutionTRM**: Manufacturing cycle time component
- **TOExecutionTRM**: Delivery cycle time component
- **Execution tGNN**: Demand forecast drives pre-positioning (reduces OFCT)

---

## 4. Tier 3 — CORRECT (Operational Level)

### Purpose
Operational metrics that enable root-cause analysis and surgical corrective action. These are the **direct observables** that the TRM hive agents monitor, react to, and optimize.

---

### 4.1 Demand Planning Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **Forecast Accuracy (WMAPE)** | Σ\|Actual-Forecast\| / ΣActual × 100 | < 25% | ForecastAdjustmentTRM |
| **Forecast Bias** | Σ(Forecast-Actual) / ΣActual × 100 | \|Bias\| < 5% | ForecastAdjustmentTRM |
| **Forecast Value Added (FVA)** | Accuracy_after_step - Accuracy_before_step | Positive | ForecastAdjustmentTRM |
| **Demand Sensing Improvement** | Short-term WMAPE improvement vs statistical | > 30% reduction | ForecastAdjustmentTRM |
| **Signal Response Latency** | Time from demand signal to forecast adjustment | < 4 hours | ForecastAdjustmentTRM |

**Powell Cascade**:
- S&OP GraphSAGE consumes aggregate forecast accuracy as CFA input
- ForecastAdjustmentTRM adjusts forecasts based on channel signals (email/voice/market)
- CDC trigger: `DEMAND_DEVIATION` fires when actual vs forecast drifts > ±15%

**Hive Signal Types**: `DEMAND_SURGE`, `DEMAND_DROP` (Scout signals from ATPExecutorTRM/OrderTrackingTRM)

---

### 4.2 Inventory Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **Inventory Turns** | Annual COGS / Avg Inventory | Industry dependent | InventoryBufferTRM |
| **Days of Supply (DOS)** | On-Hand / Avg Daily Demand | Per segment | InventoryBufferTRM |
| **Inventory Accuracy (IRA)** | Correct counts / Total counted | > 99% | — (warehouse) |
| **Safety Stock Coverage** | SS On-Hand / SS Target × 100% | 90-110% | InventoryBufferTRM |
| **Excess Inventory %** | Excess value / Total value | < 5% | InventoryRebalancingTRM |
| **Dead Stock %** | No-movement value / Total value | < 2% | InventoryRebalancingTRM |
| **Inventory by Zone** | % of SKUs in Red/Yellow/Green buffer zone | Green > 70% | InventoryBufferTRM |
| **Rebalance Efficiency** | Transferred units that reduced stockouts / Total transferred | > 80% | InventoryRebalancingTRM |

**Powell Cascade**:
- S&OP GraphSAGE sets `safety_stock_multiplier` (0.5-2.0) per site
- InventoryBufferTRM adjusts inventory buffer levels within this policy envelope
- InventoryRebalancingTRM cross-location transfers when DOS imbalance detected
- CDC trigger: `INVENTORY_LOW` (<70% target), `INVENTORY_HIGH` (>150% target)

**Hive Signal Types**: `BUFFER_INCREASED`, `BUFFER_DECREASED` (Nurse), `REBALANCE_INBOUND`, `REBALANCE_OUTBOUND` (Forager)

---

### 4.3 Supply / Procurement Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **Supplier OTD** | POs on-time / Total POs | > 95% | POCreationTRM |
| **Supplier Quality Rate** | Accepted lots / Total received | > 99% | QualityDispositionTRM |
| **PO Lead Time Reliability** | σ(actual LT) / μ(actual LT) | < 0.2 | POCreationTRM |
| **PO Cycle Time** | Requisition to PO release | < 24 hours | POCreationTRM |
| **Supplier Fill Rate** | Units received on-time / Units ordered | > 97% | POCreationTRM |
| **Material Availability** | % of materials available at MRP need date | > 98% | POCreationTRM |
| **Procurement Cost Variance** | (Actual - Standard) / Standard × 100% | < ±5% | POCreationTRM |
| **Subcontract Delivery Accuracy** | On-time subcontract receipts / Total | > 90% | SubcontractingTRM |

**Powell Cascade**:
- S&OP GraphSAGE provides `concentration_risk` per supplier (triggers dual-sourcing)
- POCreationTRM decides PO timing, quantity, and supplier selection
- SubcontractingTRM makes make-vs-buy decisions when internal capacity constrained
- CDC trigger: `SUPPLIER_RELIABILITY` fires when OTD drops 15% below target
- CDC trigger: `LEAD_TIME_INCREASE` fires at +30% vs expected

**Hive Signal Types**: `PO_EXPEDITE`, `PO_DEFERRED` (Forager), `SUBCONTRACT_ROUTED` (Forager)

---

### 4.4 Manufacturing Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **OEE** | Availability × Performance × Quality | > 85% | MOExecutionTRM, MaintenanceTRM |
| **Schedule Adherence** | Actual vs planned production | > 95% | MOExecutionTRM |
| **First Pass Yield (FPY)** | Good units first time / Total produced | > 95% | QualityDispositionTRM |
| **Manufacturing Cycle Time** | Release to completion | Declining trend | MOExecutionTRM |
| **Changeover Time** | Setup time between product runs | Minimizing | MOExecutionTRM |
| **Capacity Utilization** | Actual output / Available capacity | 75-90% | MOExecutionTRM |
| **Scrap Rate** | Scrapped units / Total produced | < 2% | QualityDispositionTRM |
| **Rework Rate** | Reworked units / Total produced | < 3% | QualityDispositionTRM |
| **Planned Maintenance Compliance** | PM tasks completed on-time / PM tasks due | > 90% | MaintenanceSchedulingTRM |
| **MTBF** (Mean Time Between Failures) | Total run time / # failures | Increasing | MaintenanceSchedulingTRM |
| **MTTR** (Mean Time to Repair) | Total downtime / # failures | < 4 hours | MaintenanceSchedulingTRM |

**Powell Cascade**:
- S&OP GraphSAGE identifies `bottleneck_risk` — triggers capacity expansion signals
- MOExecutionTRM decides sequence, split, expedite, defer for each production order
- MaintenanceSchedulingTRM balances PM compliance against production throughput
- QualityDispositionTRM decides accept/reject/rework/scrap — direct impact on FPY, scrap rate
- CDC monitor checks: capacity_remaining, upcoming_maintenance, quality_holds

**Hive Signal Types**: `MO_RELEASED`, `MO_DELAYED` (Builder), `QUALITY_REJECT`, `QUALITY_HOLD` (Guard), `MAINTENANCE_DEFERRED`, `MAINTENANCE_URGENT` (Guard)

**Decision Cycle**: MOExecutionTRM and TOExecutionTRM fire in BUILD phase (5) — after PROTECT phase (4) where MaintenanceSchedulingTRM has already signaled equipment status.

---

### 4.5 Order Promising / ATP Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **Order Promise Rate** | Orders promised / Orders received | > 95% | ATPExecutorTRM |
| **Promise Accuracy** | Delivered as promised / Total promised | > 98% | ATPExecutorTRM |
| **ATP Coverage** | ATP qty / Expected demand | > 1.0 | ATPExecutorTRM |
| **AATP Utilization** | Allocated consumed / Allocated total | 70-90% | ATPExecutorTRM |
| **CTP Conversion Rate** | CTP orders fulfilled / CTP orders triggered | > 80% | ATPExecutorTRM |
| **Promise Lead Time** | Order receipt to promise confirmation | < 10ms (TRM) | ATPExecutorTRM |
| **Rescheduling Rate** | Promised orders rescheduled / Total promised | < 5% | OrderTrackingTRM |
| **Exception Rate** | Orders with exceptions / Total orders | < 5% | OrderTrackingTRM |
| **Exception Resolution Time** | Detection to resolution | < 4 hours | OrderTrackingTRM |
| **Exception Auto-Resolution %** | Exceptions resolved without human / Total | > 50% | OrderTrackingTRM |

**Powell Cascade**:
- Execution tGNN generates Priority × Product × Location allocations (AATP input)
- ATPExecutorTRM consumes allocations using priority consumption sequence
- OrderTrackingTRM continuously monitors exceptions and recommends actions
- CDC trigger: `ATP_SHORTAGE` signal when order cannot be fulfilled from any tier

**Hive Signal Types**: `ATP_SHORTAGE`, `ATP_EXCESS` (Scout), `ORDER_EXCEPTION` (Scout)

**AATP Consumption Sequence**: Own tier (P) first → bottom-up from lowest priority → never consume above own priority

---

### 4.6 Fulfillment / Distribution Metrics

| Metric | Formula | Target | TRM Agent |
|--------|---------|--------|-----------|
| **OTIF** | On-Time × In-Full | > 95% | TOExecutionTRM |
| **Delivery Lead Time** | Ship date to delivery date | Per SLA | TOExecutionTRM |
| **Transportation Cost per Unit** | Total transport / Units shipped | Declining | TOExecutionTRM |
| **Truck/Container Utilization** | Load weight or cube / Capacity | > 85% | TOExecutionTRM |
| **Consolidation Rate** | Consolidated shipments / Total possible | > 60% | TOExecutionTRM |
| **Dock-to-Stock Time** | Receipt to put-away completion | < 4 hours | — (warehouse) |
| **Pick Accuracy** | Correct picks / Total picks | > 99.5% | — (warehouse) |
| **Return Rate** | Returns / Shipments | < 5% | QualityDispositionTRM |

**Powell Cascade**:
- Execution tGNN allocation_refresh triggers redistribution when demand shifts
- TOExecutionTRM decides release timing, consolidation, expedite for each transfer order
- InventoryRebalancingTRM recommends cross-DC transfers to maintain service levels

**Hive Signal Types**: `TO_RELEASED`, `TO_DELAYED` (Builder), `REBALANCE_INBOUND`, `REBALANCE_OUTBOUND` (Forager)

---

### 4.7 Financial Supply Chain Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Total SC Cost** | Sum of all SC costs / Revenue × 100% | 4-12% |
| **COGS Variance** | (Actual COGS - Standard COGS) / Standard × 100% | < ±3% |
| **Inventory Investment** | Total inventory value at cost | Declining trend |
| **Working Capital** | Inventory + Receivables - Payables | Minimizing |
| **Expedite Cost %** | Expedite costs / Total logistics cost | < 5% |
| **E&O Provision** | Excess & obsolescence write-off / Revenue | < 0.5% |
| **Cost Per Order** | Total fulfillment cost / Orders shipped | Declining |
| **Cost of Quality** | Prevention + Appraisal + Internal failure + External failure | < 2% of revenue |

**Powell Mapping**: S&OP GraphSAGE CFA directly optimizes the cost-service-cash triangle (Oliver Wyman). Financial metrics are the ultimate ASSESS-level scoreboard.

---

## 5. Tier 4 — AGENT PERFORMANCE (Agentic Operating Model Metrics)

### Purpose
Metrics unique to AI-agent-driven supply chains. These measure the quality, trust, and autonomy of the TRM hive — not just supply chain outcomes, but **how well the agents produce those outcomes**.

### 5.1 Decision Quality Metrics (Per TRM Agent)

| Metric | Formula | Target | Scope |
|--------|---------|--------|-------|
| **Agent Performance Score** | Decision quality vs baseline/optimal (-100 to +100) | Positive (>0) | Per TRM |
| **Decision Accuracy** | Correct decisions / Total decisions | > 90% | Per TRM |
| **Regret** | (Optimal outcome - Actual outcome) / Optimal | < 10% | Per TRM |
| **Confidence Calibration** | % of outcomes within predicted confidence interval | 90-95% | Per TRM (conformal) |
| **Decision Latency** | Time from state observation to decision output | < 10ms | Per TRM |
| **Inference Throughput** | Decisions per second | > 100/sec | Per TRM |

### 5.2 Autonomy & Trust Metrics

| Metric | Formula | Target | Scope |
|--------|---------|--------|-------|
| **Touchless Rate** | Decisions executed without human intervention / Total | > 80% | Per TRM, Aggregate |
| **Human Override Rate** | Decisions overridden by humans / Total | < 20% | Per TRM |
| **Override Dependency Ratio** | Overrides per decision type → identifies weak areas | Declining per TRM | Per TRM × Decision Type |
| **Escalation Rate** | Decisions escalated to management / Total | < 10% | Per TRM |
| **Auto-Resolution Rate** | Exceptions resolved autonomously / Total exceptions | > 50% | OrderTrackingTRM |
| **Override Quality** | Human overrides that improved outcome / Total overrides | > 60% | Per TRM (RLHF input) |

### 5.3 Hive Coordination Metrics

| Metric | Formula | Target | Scope |
|--------|---------|--------|-------|
| **Hive Mean Urgency** | Mean across 11 UrgencyVector slots | < 0.4 (healthy) | Per Site |
| **Hive Max Urgency** | Peak urgency across any TRM | < 0.8 (non-critical) | Per Site |
| **Signal Bus Activity** | Active (non-decayed) signals in ring buffer | 5-30 (moderate) | Per Site |
| **Conflict Rate** | % of cycles with opposing shortage/surplus signals | < 10% | Per Site |
| **Hive Stress Index** | mean_urgency > 0.6 OR has_conflict | < 15% of cycles | Per Site |
| **Signal-Decision Ratio** | Signals consumed / Decisions made | 2-5 (information-rich) | Per Site |
| **Inter-Hive Coherence** | Local hive signals align with tGNN predictions | > 70% alignment | Cross-Site |
| **CDC Trigger Frequency** | CDC events per site per day | < 3 (stable) | Per Site |
| **Retraining Frequency** | Model retraining events per TRM per month | 1-4 (learning) | Per TRM |

### 5.4 Downstream Coherence Metrics

| Metric | Formula | Target | Scope |
|--------|---------|--------|-------|
| **Planning Cascade Consistency** | MPS adherence to S&OP / MRP adherence to MPS | > 85% | Cross-layer |
| **Plan Stability (Nervousness)** | % change in plan period-over-period | < 15% (frozen zone) | Per planning level |
| **Feed-Forward Accuracy** | % of upstream artifacts consumed without override | > 75% | S&OP → MPS → MRP |
| **Feed-Back Response Time** | Time from outcome signal to policy parameter update | < 1 week | OTIF → S&OP θ |
| **Allocation vs Actual** | Allocated quantity consumed / Total allocated | 70-90% | Per priority tier |

---

## 6. Metrics by TRM Agent (Cross-Reference)

### Per-Agent Metric Ownership

| TRM Agent | Phase | Primary Metrics Owned | Secondary Metrics Influenced |
|-----------|-------|----------------------|------------------------------|
| **ATPExecutorTRM** | SENSE | Promise rate, promise accuracy, ATP coverage, AATP utilization | OTIF, OFCT, customer satisfaction |
| **OrderTrackingTRM** | SENSE | Exception rate, exception resolution time, auto-resolution % | POF, rescheduling rate |
| **POCreationTRM** | ACQUIRE | Supplier OTD, PO cycle time, material availability | DIO, manufacturing schedule adherence |
| **SubcontractingTRM** | ACQUIRE | Subcontract delivery accuracy, cost variance | Capacity utilization, OFCT |
| **InventoryBufferTRM** | ASSESS | DOS, inventory turns, safety stock coverage, inventory by zone | C2C, DIO, service level |
| **ForecastAdjustmentTRM** | ASSESS | Forecast accuracy (WMAPE), bias, FVA, signal response latency | All downstream metrics (forecast drives everything) |
| **QualityDispositionTRM** | ASSESS | FPY, scrap rate, rework rate, cost of quality | OEE quality component, return rate, POF |
| **MaintenanceSchedulingTRM** | PROTECT | PM compliance, MTBF, MTTR | OEE availability, schedule adherence |
| **MOExecutionTRM** | BUILD | Schedule adherence, manufacturing cycle time, capacity utilization | OEE, OFCT, COGS variance |
| **TOExecutionTRM** | BUILD | OTIF, delivery lead time, truck utilization, consolidation rate | OFCT, transport cost, C2C |
| **InventoryRebalancingTRM** | REFLECT | Rebalance efficiency, excess inventory reduction | DIO, service level balance across sites |

---

## 7. CDC Trigger Thresholds → Metric-Based Replanning

The CDC (Change-Detect-Correct) monitor maps operational metrics directly to replanning actions:

| Trigger | Metric Watched | Threshold | Replan Action |
|---------|---------------|-----------|---------------|
| `DEMAND_DEVIATION` | Actual vs Forecast (cumulative) | ±15% | TGNN_REFRESH or FULL_CFA |
| `INVENTORY_LOW` | On-Hand / Target Inventory | < 70% | PARAM_ADJUSTMENT (+SS) |
| `INVENTORY_HIGH` | On-Hand / Target Inventory | > 150% | PARAM_ADJUSTMENT (-SS) |
| `SERVICE_LEVEL_DROP` | Actual Service Level - Target | > 5% gap | FULL_CFA |
| `LEAD_TIME_INCREASE` | Actual LT / Expected LT | > 130% | ALLOCATION_ONLY |
| `BACKLOG_GROWTH` | Consecutive days of backlog increase | > 2 days | TGNN_REFRESH |
| `SUPPLIER_RELIABILITY` | Supplier OTD vs Target OTD | > 15% below | PARAM_ADJUSTMENT |
| `SIGNAL_DIVERGENCE` | Local hive urgency vs tGNN prediction | > 30% divergence | TGNN_REFRESH |

**Replan Action Hierarchy**:
```
NONE → PARAM_ADJUSTMENT (±10% light tweak)
     → ALLOCATION_ONLY (rerun allocations)
     → TGNN_REFRESH (off-cadence inference)
     → FULL_CFA (complete policy re-optimization)
```

---

## 8. Probabilistic Balanced Scorecard

The Autonomy platform expresses all metrics probabilistically rather than as point estimates:

### Financial Perspective

| Metric | Point Estimate | Probabilistic Form |
|--------|---------------|-------------------|
| Total Cost | $1.2M | P10=$1.05M, P50=$1.2M, P90=$1.45M |
| Budget Adherence | 98% | P(Cost < Budget) = 85% |
| Working Capital | $3.5M | E[WC] = $3.5M, σ = $0.4M |

### Customer Perspective

| Metric | Point Estimate | Probabilistic Form |
|--------|---------------|-------------------|
| OTIF | 95% | E[OTIF] = 95%, P(OTIF > 95%) = 72% |
| Fill Rate | 97% | E[Fill] = 97%, P10 = 93%, P90 = 99% |
| Order Cycle Time | 3.2 days | E[OCT] = 3.2d, P90 = 4.8d |

### Operational Perspective

| Metric | Point Estimate | Probabilistic Form |
|--------|---------------|-------------------|
| Inventory Turns | 8.5 | E[Turns] = 8.5, P(Turns > 8) = 78% |
| DOS | 28 days | E[DOS] = 28d, P10 = 22d, P90 = 35d |
| OEE | 87% | E[OEE] = 87%, P(OEE > 85%) = 80% |
| Bullwhip Ratio | 1.8 | E[BWR] = 1.8, P(BWR < 2.0) = 65% |

### Agent Perspective (Unique to Agentic Operating Model)

| Metric | Point Estimate | Probabilistic Form |
|--------|---------------|-------------------|
| Touchless Rate | 82% | E[TR] = 82%, trending +3%/month |
| Agent Score | +15 | E[Score] = +15, P(Score > 0) = 95% |
| Override Rate | 18% | E[OR] = 18%, trending -2%/month |
| Hive Stress % | 12% | P(stressed cycles) = 12%, target < 15% |

---

## 9. Metric Diagnostic Trees

### OTIF Root Cause Analysis

```
OTIF < 95% target
├── On-Time component low?
│   ├── Manufacturing late? → Check MOExecutionTRM: schedule adherence, OEE
│   ├── Transport late? → Check TOExecutionTRM: delivery LT, carrier performance
│   ├── Promise too aggressive? → Check ATPExecutorTRM: promise accuracy
│   └── Supplier late? → Check POCreationTRM: supplier OTD
└── In-Full component low?
    ├── Inventory shortage? → Check InventoryBufferTRM: DOS, buffer coverage
    ├── Allocation mismatch? → Check AATP utilization, allocation vs actual
    ├── Quality rejection? → Check QualityDispositionTRM: FPY, rejection rate
    └── Forecast miss? → Check ForecastAdjustmentTRM: WMAPE, bias
```

### C2C Root Cause Analysis

```
C2C > target
├── DIO too high?
│   ├── Excess inventory? → InventoryRebalancingTRM: excess %, dead stock
│   ├── Buffer too high? → InventoryBufferTRM: buffer multiplier vs actual service
│   ├── Slow movers? → ABC-XYZ segmentation review
│   └── Forecast over-bias? → ForecastAdjustmentTRM: positive bias
├── DSO too high?
│   └── (Outside SC scope — A/R collections)
└── DPO too low?
    └── POCreationTRM: payment terms, supplier negotiations
```

### Agent Performance Root Cause

```
Agent Score declining
├── Decision accuracy dropping?
│   ├── Data quality issue? → Check input data freshness, completeness
│   ├── Distribution shift? → CDC SIGNAL_DIVERGENCE → trigger retraining
│   └── Policy parameters stale? → FULL_CFA refresh
├── Override rate increasing?
│   ├── Specific TRM? → Check override_dependency_ratio by TRM
│   ├── Specific decision type? → Curriculum learning gap
│   └── User behavior change? → Update override quality scoring
└── Hive stress increasing?
    ├── External shock? → DEMAND_SURGE/DROP signals, tGNN directive
    ├── Conflicting signals? → Conflict resolution in REFLECT phase
    └── Equipment issue? → MAINTENANCE_URGENT, check MTBF trend
```

---

## 10. Industry Benchmarks

### By Industry Vertical

| Metric | Consumer Products | High Tech | Industrial | Pharma |
|--------|------------------|-----------|-----------|--------|
| **POF** | 85-92% | 80-90% | 75-88% | 90-95% |
| **OFCT** | 3-7 days | 5-14 days | 7-30 days | 5-10 days |
| **WMAPE** | 20-35% | 25-40% | 30-45% | 15-30% |
| **Inventory Turns** | 8-15 | 6-12 | 4-8 | 3-6 |
| **C2C** | 30-60 days | 40-80 days | 50-90 days | 60-100 days |
| **OEE** | 75-85% | 70-80% | 65-80% | 80-90% |
| **SC Cost % Rev** | 6-10% | 5-8% | 8-15% | 4-8% |

### By Maturity Level

| Metric | Reactive (Stage 1) | Anticipate (Stage 2) | Integrate (Stage 3) | Orchestrate (Stage 5) |
|--------|-------------------|---------------------|---------------------|----------------------|
| **Touchless Rate** | 0% | 10-20% | 40-60% | 80-95% |
| **WMAPE** | 40-50% | 30-40% | 20-30% | 10-20% |
| **POF** | 60-75% | 75-85% | 85-92% | 92-98% |
| **C2C** | 80-120 days | 60-80 | 40-60 | 20-40 |
| **Agent Score** | N/A | -10 to +5 | +5 to +20 | +20 to +40 |

---

## 11. Implementation: Metric-to-Dashboard Mapping

### Executive Dashboard (S&OP GraphSAGE Level)

```
┌─────────────────────────────────────────────────────────────┐
│  Revenue Growth ↑   │  EBIT Margin    │  ROCS             │
│  +8.2% vs LY        │  12.4%          │  28%              │
├──────────────────────┼─────────────────┼───────────────────┤
│  POF                 │  C2C            │  OFCT             │
│  91.3% → 95% target │  42 days        │  4.2 days avg     │
├──────────────────────┴─────────────────┴───────────────────┤
│  Agent Status: 82% touchless │ Score: +15 │ Overrides: 18% │
└─────────────────────────────────────────────────────────────┘
```

### Planning Dashboard (Execution tGNN Level)

```
┌──────────────────────────────────────────────────────────────┐
│  Forecast Accuracy: WMAPE 23% │ Bias: +2.1%  │ FVA: +4.2%  │
├──────────────────────────────────────────────────────────────┤
│  Inventory: DOS 28d │ Turns 8.5 │ Excess 3.2% │ Dead 0.8%  │
├──────────────────────────────────────────────────────────────┤
│  Supplier OTD: 94.2% │ Material Avail: 97.8% │ LT CV: 0.18 │
├──────────────────────────────────────────────────────────────┤
│  Allocation Util: 78% │ Exception Rate: 4.1% │ CDC: 2/day  │
└──────────────────────────────────────────────────────────────┘
```

### Site Agent Dashboard (TRM Hive Level)

```
┌──────────────────────────────────────────────────────────────┐
│  Site: East DC │ Hive Health: ● Healthy │ Stress: 8%        │
├──────────────────────────────────────────────────────────────┤
│  TRM          │ Score │ Touchless │ Overrides │ Urgency     │
│  ATP          │  +22  │    94%    │     6%    │ 0.12 ●      │
│  OrderTrack   │  +18  │    88%    │    12%    │ 0.25 ●      │
│  PO Creation  │  +15  │    82%    │    18%    │ 0.31 ●      │
│  Rebalancing  │  +12  │    76%    │    24%    │ 0.18 ●      │
│  Safety Stock │  +19  │    91%    │     9%    │ 0.08 ●      │
│  Forecast Adj │  +11  │    79%    │    21%    │ 0.22 ●      │
│  Quality      │  +25  │    95%    │     5%    │ 0.05 ●      │
│  Maintenance  │  +14  │    85%    │    15%    │ 0.15 ●      │
│  MO Execution │  +16  │    83%    │    17%    │ 0.28 ●      │
│  TO Execution │  +13  │    80%    │    20%    │ 0.20 ●      │
│  Subcontract  │  +10  │    72%    │    28%    │ 0.35 ●      │
├──────────────────────────────────────────────────────────────┤
│  Signal Bus: 18 active │ Conflicts: 0 │ Cycle: #4,217     │
└──────────────────────────────────────────────────────────────┘
```

---

*Sources: [Gartner Hierarchy of Supply Chain Metrics](https://www.gartner.com/en/supply-chain/research/hierarchy-supply-chain-metrics-tool), [SCOR Digital Standard](https://www.ascm.org/globalassets/ascm_website_assets/docs/intro-and-front-matter-scor-digital-standard2.pdf), [Benchmarking Success: Hierarchy of Metrics](https://www.benchmarkingsuccess.com/the-hierarchy-of-metrics-for-supply-chain-success/), [SCMR: Agentic AI in Supply Chain](https://www.scmr.com/article/how-agentic-ai-changes-supply-chain-operations), [Kinaxis Maestro Agent Studio](https://www.traxtech.com/ai-in-supply-chain/kinaxis-maestro-agent-studio-composable-ai-supply-chain), ASCM CPIM/CSCP Learning System, Oliver Wyman Supply Chain Triangle, Autonomy Platform Powell Framework Documentation*

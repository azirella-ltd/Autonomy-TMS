# Demand Driven Material Requirements Planning (DDMRP)

## Comprehensive Reference Guide

---

## 1. Overview

### What is DDMRP?

DDMRP (Demand Driven MRP) is a multi-echelon planning and execution methodology developed by Carol Ptak and Chad Smith through the Demand Driven Institute (DDI). It combines elements of MRP, Distribution Requirements Planning (DRP), Lean, Six Sigma, and Theory of Constraints (TOC) into a demand-driven approach that uses strategically placed decoupling points with dynamically managed buffers.

**Core Thesis**: Traditional MRP is fundamentally forecast-driven and generates the bullwhip effect because every change in forecast or order propagates through the entire BOM. DDMRP decouples the supply chain at strategic points, absorbing variability and responding to actual demand rather than forecasts.

### DDMRP vs Traditional MRP

| Aspect | Traditional MRP | DDMRP |
|--------|----------------|-------|
| **Demand signal** | Forecast-driven (push) | Actual demand-driven (pull) |
| **Nervousness** | High (small changes cascade) | Low (buffers absorb variability) |
| **Visibility** | Dependent demand calculated | Visible independent demand at each buffer |
| **Lead times** | Full cumulative lead time | Decoupled lead times (shorter segments) |
| **Inventory** | Safety stock as a hedge | Strategic buffers as designed system feature |
| **Planning** | Net requirements explosion | Buffer status-based priorities |
| **Replanning** | Regenerative or net change | Continuous, real-time buffer monitoring |

---

## 2. The Five Components of DDMRP

### Component 1: Strategic Inventory Positioning

**Purpose**: Determine WHERE to place decoupling point buffers in the BOM and distribution network.

**Positioning Factors**:

| Factor | Description | Impact on Positioning |
|--------|-------------|----------------------|
| **Customer Tolerance Time (CTT)** | How long customers will wait | Buffers must be downstream of CTT boundary |
| **Market Potential Lead Time (MPLT)** | Longest unprotected lead time the market will tolerate | Shorter MPLT → more buffers needed |
| **Demand Variability** | Coefficient of variation of demand | Higher variability → buffer closer to demand |
| **Supply Variability** | Reliability of supply lead times | Higher variability → buffer downstream of unreliable supply |
| **Inventory Leverage** | Impact of buffer position on overall inventory investment | Place buffers where they protect the most BOM levels |
| **Critical Operation Protection** | Key constraints or bottlenecks | Buffer before and/or after constraints |

**Decoupling Point Types**:
```
Type 1: Purchased Raw Material Buffer
  → Buffer raw materials to decouple from supplier lead times

Type 2: WIP Buffer (Semi-Finished)
  → Buffer at intermediate BOM level to reduce manufacturing lead time

Type 3: Finished Goods Buffer
  → Buffer at FG level to provide immediate customer availability

Type 4: Distribution Buffer
  → Buffer at distribution points to decouple from transportation lead time
```

### Component 2: Buffer Profiles and Levels

**Purpose**: Determine HOW MUCH to buffer at each position.

**Buffer Zones**:
```
┌──────────────────────────────────────────────┐
│              TOP OF GREEN (TOG)               │ ← Max buffer level
├──────────────────────────────────────────────┤
│                                              │
│              GREEN ZONE                      │ ← Order generation zone
│                                              │
├──────────────────────────────────────────────┤
│              TOP OF YELLOW (TOY)             │ ← Reorder trigger
├──────────────────────────────────────────────┤
│                                              │
│              YELLOW ZONE                     │ ← Working stock / lead time zone
│                                              │
├──────────────────────────────────────────────┤
│              TOP OF RED (TOR)                │ ← Safety zone trigger
├──────────────────────────────────────────────┤
│     RED ZONE BASE + RED ZONE SAFETY          │ ← Emergency buffer
└──────────────────────────────────────────────┘
```

**Buffer Calculation**:

```
Red Zone Base = Average Daily Usage (ADU) × Decoupled Lead Time (DLT) × Lead Time Factor

Red Zone Safety = Red Zone Base × Variability Factor

Yellow Zone = ADU × DLT

Green Zone = max(ADU × DLT × Lead Time Factor, MOQ, Imposed Order Cycle × ADU)

Top of Red (TOR) = Red Zone Base + Red Zone Safety
Top of Yellow (TOY) = TOR + Yellow Zone
Top of Green (TOG) = TOY + Green Zone
```

**Buffer Profiles**:

| Profile Attribute | Short LT | Medium LT | Long LT |
|------------------|----------|-----------|---------|
| **Lead Time Factor** | 0.2-0.4 | 0.4-0.6 | 0.6-1.0 |
| **Variability Factor** (Low) | 0.1-0.2 | 0.2-0.3 | 0.3-0.5 |
| **Variability Factor** (Med) | 0.2-0.4 | 0.4-0.5 | 0.5-0.7 |
| **Variability Factor** (High) | 0.4-0.6 | 0.6-0.8 | 0.8-1.0 |

### Component 3: Dynamic Adjustments

**Purpose**: Adapt buffer levels to planned and known future events.

**Demand Adjustment Factor (DAF)**:
```
Adjusted ADU = ADU × DAF

DAF > 1.0: Increase buffer (seasonal peak, promotion, new product ramp)
DAF < 1.0: Decrease buffer (seasonal trough, phase-out, slow period)
DAF = 1.0: No adjustment

Example:
  Base ADU = 100 units/day
  Holiday season DAF = 1.5
  Adjusted ADU = 150 units/day
  All buffer zones recalculated with new ADU
```

**Types of Dynamic Adjustments**:

| Adjustment | Trigger | Direction | Duration |
|-----------|---------|-----------|----------|
| **Seasonal** | Calendar/season change | Up or down | Weeks to months |
| **Promotional** | Planned promotion | Up | Days to weeks |
| **Ramp-up** | New product introduction | Up (gradual) | Weeks to months |
| **Phase-out** | Product end-of-life | Down (gradual) | Weeks to months |
| **Supply risk** | Known supply disruption | Up (red zone) | Duration of risk |
| **Market event** | External market factors | Up or down | Event duration |

### Component 4: Demand Driven Planning

**Purpose**: Generate supply orders based on buffer status (net flow position).

**Net Flow Position (NFP)**:
```
NFP = On-Hand + On-Order − Qualified Demand

Where:
  On-Hand = Current physical inventory
  On-Order = Open supply orders (POs, MOs, TOs) not yet received
  Qualified Demand = Demand due today + Past due demand + Qualified spikes

Qualified Spike = Demand in a future period that exceeds the
                  spike threshold (typically 50% of red zone)
```

**Order Generation Logic**:
```
If NFP ≤ TOY (Top of Yellow):
    Order Quantity = TOG − NFP
    (Order up to Top of Green)

If NFP > TOY:
    No order needed

Priority = NFP / TOG × 100%
    Red:    0-33% (Critical — expedite)
    Yellow: 34-66% (Normal — plan)
    Green:  67-100% (Healthy — no action)
```

**Visual Planning Board**:
```
Buffer Status:  [█████████████░░░░░░░░] 65% — Yellow
                 Red      Yellow    Green

Priority Color Coding:
  🔴 Red (0-33%):    Immediate action required
  🟡 Yellow (34-66%): Normal planning, generate orders
  🟢 Green (67-100%): No action needed
  ⬛ Black (>100%):   Over-buffered, consider reduction
```

### Component 5: Visible and Collaborative Execution

**Purpose**: Manage open orders using buffer status alerts.

**Execution Alerts**:

| Alert | Condition | Action |
|-------|-----------|--------|
| **Current On-Hand Alert** | On-Hand in red zone | Expedite incoming supply |
| **Projected On-Hand Alert** | Projected stock will enter red zone | Prepare to expedite |
| **Synchronization Alert** | Upstream buffer in red zone | Warn downstream buffers |
| **Material Synchronization** | Non-buffered material shortage | Coordinate with supply |
| **Lead Time Alert** | Supply order past due or at risk | Escalate to supplier |

**Execution Priority = On-Hand / TOR (Top of Red)**:
```
< 50%: Critical — immediate expedite action
50-100%: Warning — monitor closely
> 100%: OK — no execution concern
```

---

## 3. Decoupled Lead Time (DLT)

### DLT vs Cumulative Lead Time (CLT)

```
Traditional MRP uses Cumulative Lead Time:
  CLT = Sum of ALL lead times through the longest path in the BOM

DDMRP uses Decoupled Lead Time:
  DLT = Longest lead time path BETWEEN decoupled buffer points

Example BOM:
  Raw Material A (LT=20 days) → [BUFFER] → Sub-Assembly (LT=5 days) →
  → [BUFFER] → Final Assembly (LT=3 days) → [BUFFER]

  CLT = 20 + 5 + 3 = 28 days
  DLT for Final Assembly = 3 days (only to nearest upstream buffer)
  DLT for Sub-Assembly = 5 days
  DLT for Raw Material = 20 days
```

**Impact**: Shorter DLTs mean:
- Smaller buffers needed (less safety stock)
- Faster response to demand changes
- Less forecast dependency
- Reduced bullwhip effect

---

## 4. DDMRP Metrics

### Buffer Performance

| Metric | Calculation | Target |
|--------|------------|--------|
| **Buffer Status** | NFP / TOG × 100% | 50-80% average |
| **Time in Red** | % of time on-hand in red zone | < 10% |
| **Time Over Green** | % of time inventory > TOG | < 15% |
| **Buffer Compliance** | On-hand within green-red range / Total time | > 75% |

### Flow Metrics

| Metric | Calculation | Meaning |
|--------|------------|---------|
| **Flow Index** | Actual throughput / Planned throughput | > 0.95 |
| **Demand Latency** | Time from demand signal to supply action | Hours (not days) |
| **Decoupled Lead Time Ratio** | DLT / CLT | Lower = more decoupled |

---

## 5. DDMRP Implementation Approach

### Phase 1: Education and Environment Assessment
- Train key stakeholders on DDMRP methodology
- Map current BOM structure and lead times
- Identify current pain points (bullwhip, stockouts, excess)

### Phase 2: Strategic Positioning Workshop
- Analyze BOM levels and cumulative lead times
- Apply 6 positioning factors
- Select initial decoupling points (start simple, expand later)

### Phase 3: Buffer Sizing
- Assign buffer profiles (lead time category × variability category)
- Calculate initial buffer zones
- Set dynamic adjustment factors for known events

### Phase 4: System Configuration
- Configure DDMRP logic in ERP/planning system
- Set up net flow position calculations
- Configure alerts and visual priority board
- Parallel run with existing MRP

### Phase 5: Go-Live and Continuous Improvement
- Switch from MRP to DDMRP for selected items
- Monitor buffer performance daily
- Adjust profiles and positions based on actual performance
- Expand to additional items and locations

---

## 6. DDMRP Software Platforms

| Platform | Type | Notes |
|----------|------|-------|
| **Demand Driven Technologies** | Native DDMRP | Built by DDI founders |
| **Replenishment+** | Overlay for SAP/Oracle | DDMRP add-on for existing ERP |
| **Kinaxis** | Integrated | DDMRP capabilities within RapidResponse |
| **o9 Solutions** | Integrated | DDMRP as part of digital brain |
| **SAP IBP** | Partial | DDMRP concepts in S/4HANA MRP |
| **Orkestra (Ploutos)** | Native | Cloud-native DDMRP |
| **Intuiflow (Demand Driven Technologies)** | Native | Flagship DDMRP platform |

---

## 7. DDMRP Criticisms and Limitations

| Criticism | Counter-Argument |
|-----------|-----------------|
| **Buffer sizing is heuristic, not optimal** | Simplicity enables adoption; near-optimal in practice |
| **Ignores capacity constraints** | True — DDMRP focuses on material flow; capacity needs separate check |
| **Not suitable for engineer-to-order** | Correct — designed for repetitive/semi-repetitive manufacturing |
| **Requires significant buffer inventory** | Total inventory typically decreases 30-45% vs MRP due to positioning |
| **Limited academic validation** | Growing body of research; mostly practitioner-validated |
| **Doesn't replace S&OP** | Correct — DDMRP is execution method, S&OP is strategic alignment |

---

## 8. Demand Driven Operating Model (DDOM)

DDMRP is part of the broader Demand Driven Operating Model:

```
┌──────────────────────────────────────────────┐
│     Demand Driven S&OP (DDS&OP)              │ ← Strategic range
│     Adaptive S&OP with projected buffer status│
├──────────────────────────────────────────────┤
│     Demand Driven MRP (DDMRP)                │ ← Tactical range
│     Buffer positioning, sizing, planning      │
├──────────────────────────────────────────────┤
│     Demand Driven Execution                   │ ← Operational range
│     Visual alerts, priority management        │
└──────────────────────────────────────────────┘
```

### DDS&OP
- Projects buffer status 6-24 months forward
- Uses projected ADU from S&OP demand plan
- Identifies future resource requirements and constraints
- Validates strategic buffer positions
- Links strategic planning to operational execution

---

## 9. DDMRP vs Other Methodologies

| Feature | MRP | Lean/Kanban | TOC/DBR | DDMRP |
|---------|-----|------------|---------|-------|
| **Demand signal** | Forecast | Consumption | Drum schedule | Actual + qualified spikes |
| **Inventory approach** | Minimize | Eliminate WIP | Buffer constraint | Strategic buffers |
| **Lead time** | Cumulative | Takt time | Constraint-based | Decoupled |
| **Variability handling** | Safety stock | Reduce variation | Buffer rope | Dynamic buffers |
| **Planning horizon** | Full BOM | Kanban signal | Drum schedule | Buffer zones |
| **Complexity** | High | Low | Medium | Medium |
| **Best for** | Complex BOM, MTO | High volume, repetitive | Bottleneck environments | Variable demand, multi-echelon |

---

*Sources: Ptak & Smith "Demand Driven Material Requirements Planning" (3rd ed, 2020), Demand Driven Institute (DDI), "Orlicky's MRP" (3rd ed), ASCM DDPP (Demand Driven Planner Professional) certification body of knowledge*

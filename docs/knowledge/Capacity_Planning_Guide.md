# Capacity Planning & Management

## Comprehensive Reference Guide for Supply Chain Capacity Planning

---

## 1. Overview

### Definition

Capacity planning is the process of determining the production capacity needed to meet changing demand. It ensures that sufficient resources (equipment, labor, space, materials) are available to execute the production plan while avoiding both excess capacity (waste) and insufficient capacity (missed deliveries).

### Capacity Planning Hierarchy

```
Resource Planning (RP) — Strategic (1-5 years)
    ↓ Aggregate resource requirements from S&OP
Rough-Cut Capacity Planning (RCCP) — Tactical (3-18 months)
    ↓ Validates MPS against critical resources
Capacity Requirements Planning (CRP) — Operational (1-6 months)
    ↓ Validates MRP planned orders against all work centers
Finite Capacity Scheduling (FCS) — Execution (days-weeks)
    ↓ Detailed sequence and timing on specific machines
Input/Output Control (I/O) — Real-time monitoring
    ↓ Monitor actual vs planned capacity usage
```

---

## 2. Capacity Concepts

### 2.1 Capacity Definitions

| Term | Definition | Formula |
|------|-----------|---------|
| **Theoretical Capacity** | Maximum possible output (24/7, no stops) | Hours/day × Days/year × Machines |
| **Rated Capacity** | Expected output considering planned downtime | Theoretical × Availability |
| **Demonstrated Capacity** | Actual historical average output | Average of last N periods |
| **Effective Capacity** | Realistic sustainable output | Rated × Efficiency × Utilization |
| **Available Capacity** | Capacity available for production in a period | Scheduled hours × # resources × efficiency |
| **Required Capacity** | Capacity needed to meet the plan | Σ(planned qty × time per unit) |

### 2.2 Key Capacity Metrics

```
Utilization = Actual Output / Available Capacity × 100%

Efficiency = Standard Hours Produced / Actual Hours Worked × 100%

OEE = Availability × Performance × Quality

Where:
  Availability = Run Time / Planned Production Time
  Performance = (Ideal Cycle Time × Total Count) / Run Time
  Quality = Good Count / Total Count
```

### 2.3 Capacity Units

| Unit | Description | Example |
|------|-------------|---------|
| **Machine hours** | Time available on equipment | 16 hours/day × 5 days = 80 hrs/week |
| **Labor hours** | Time available from workers | 10 operators × 8 hrs = 80 hrs/day |
| **Units/period** | Output quantity | 500 widgets per day |
| **Tons/period** | Weight-based output | 100 tons per week |
| **Throughput** | Flow rate through bottleneck | 200 orders per hour |

---

## 3. Resource Planning (Strategic Level)

### 3.1 Purpose

Resource Planning validates the S&OP/IBP plan against aggregate resources:

```
S&OP Demand Plan (product families, monthly)
    × Resource Profile (hours per family per resource)
    = Required Resource Hours

Compare vs Available Resource Hours:
    Gap = Required - Available

If Gap > 0:
    → Add shifts, overtime, outsource, invest in capacity
If Gap < 0:
    → Reduce shifts, consolidate, reassign
```

### 3.2 Resource Profile (Bill of Resources)

| Product Family | Assembly (hrs/unit) | Machining (hrs/unit) | Packaging (hrs/unit) |
|---------------|---------------------|---------------------|---------------------|
| Family A | 0.5 | 1.2 | 0.3 |
| Family B | 0.3 | 0.8 | 0.5 |
| Family C | 0.8 | 2.0 | 0.2 |

```
Example: S&OP plan calls for:
  Family A: 10,000 units/month
  Family B: 8,000 units/month
  Family C: 5,000 units/month

Required Machining Hours:
  = 10,000 × 1.2 + 8,000 × 0.8 + 5,000 × 2.0
  = 12,000 + 6,400 + 10,000
  = 28,400 hours/month

Available Machining: 30 machines × 160 hrs/month × 85% utilization = 4,080 hrs/machine
  Total = 30 × 136 hrs = 4,080 hrs available... WAIT — recalculate
  30 machines × 160 hrs × 0.85 = 4,080 hrs/month total available

28,400 required > 4,080 available → CAPACITY GAP of 24,320 hours!

Resolution options:
  1. Add machines (capital investment)
  2. Add shifts (2→3 shifts: +50% capacity)
  3. Outsource Family C machining
  4. Reduce S&OP plan
```

---

## 4. Rough-Cut Capacity Planning (RCCP)

### 4.1 Purpose

RCCP validates the MPS against **critical (bottleneck) resources** only — not all work centers. It provides a quick feasibility check before running detailed MRP.

### 4.2 RCCP Methods

#### Bill of Resources Method (Most Common)
```
For each MPS item and critical resource:
    Required Hours = MPS Quantity × Hours per Unit (from BOR)

Total Load on Resource = Σ (all MPS items)
```

#### Capacity Planning Using Overall Factors (CPOF)
```
Total Hours = MPS Units × Overall Factor (historical hours/unit)
Distribute across resources using historical percentages:
    Resource A: Total × 40%
    Resource B: Total × 35%
    Resource C: Total × 25%
```

#### Resource Profile Approach
```
Like BOR but with lead time offset:
    Resource load placed in the period the resource is actually used
    (not when the MPS receipt occurs)
```

### 4.3 RCCP Output

```
Work Center: CNC Machining
Available Capacity: 2,000 hrs/week

| Week | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|------|---|---|---|---|---|---|---|---|
| Required | 1800 | 1600 | 2200 | 2400 | 1900 | 2100 | 1700 | 2300 |
| Available | 2000 | 2000 | 2000 | 2000 | 2000 | 2000 | 2000 | 2000 |
| Load % | 90% | 80% | 110% | 120% | 95% | 105% | 85% | 115% |
| Status | ✅ | ✅ | ⚠️ | ❌ | ✅ | ⚠️ | ✅ | ❌ |

Weeks 3, 4, 6, 8 are over-capacity → MPS needs adjustment
```

---

## 5. Capacity Requirements Planning (CRP)

### 5.1 Purpose

CRP uses detailed routing information from MRP planned orders to calculate capacity requirements at **every work center** in the production process.

### 5.2 CRP Calculation

```
For each MRP planned order:
    For each routing operation:
        Setup Time = Fixed setup per batch
        Run Time = Quantity × Run time per unit
        Total Time = Setup + Run

        Load this time onto the work center in the correct period
        (based on backward scheduling from order due date)

Work Center Load = Σ (all planned orders using this work center)
```

### 5.3 CRP vs RCCP

| Aspect | RCCP | CRP |
|--------|------|-----|
| **Input** | MPS (aggregate) | MRP planned orders (detailed) |
| **Detail** | Critical resources only | All work centers |
| **Routing** | Bill of Resources (simplified) | Full routing with operations |
| **Time** | MPS period (weekly) | Operation-level scheduling |
| **Purpose** | Quick feasibility check | Detailed capacity validation |
| **Speed** | Fast (few resources) | Slower (all work centers) |

---

## 6. Finite Capacity Scheduling (FCS)

### 6.1 Infinite vs Finite Capacity

```
Infinite Capacity (MRP/CRP assumption):
    All orders are scheduled regardless of capacity
    Overloads are flagged as exceptions
    Planner resolves overloads manually

Finite Capacity Scheduling:
    Orders are scheduled respecting capacity limits
    If capacity is full, order is moved to next available slot
    Automatic resolution of capacity conflicts
```

### 6.2 Scheduling Approaches

| Approach | Logic | Result |
|----------|-------|--------|
| **Forward scheduling** | Start from today, schedule earliest possible | Earliest completion date |
| **Backward scheduling** | Start from due date, schedule latest possible | Latest start date |
| **Bottleneck scheduling** | Schedule bottleneck first, then others | Maximize bottleneck utilization |
| **Drum-Buffer-Rope (DBR)** | Bottleneck is drum, others subordinate | TOC-based approach |

### 6.3 Scheduling Objectives

| Objective | Minimize | Best Dispatch Rule |
|-----------|----------|-------------------|
| **Average flow time** | Mean time in system | SPT (Shortest Processing Time) |
| **Maximum lateness** | Worst-case delay | EDD (Earliest Due Date) |
| **Number of tardy jobs** | Count of late orders | Modified Due Date |
| **Makespan** | Total completion time | LPT (Longest Processing Time) |
| **Setup time** | Changeover waste | Family sequencing |
| **WIP** | Work-in-process inventory | CONWIP limit |

---

## 7. Theory of Constraints (TOC)

### 7.1 Five Focusing Steps

```
1. IDENTIFY the system's constraint (bottleneck)
2. EXPLOIT the constraint (maximize its output)
3. SUBORDINATE everything else to the constraint
4. ELEVATE the constraint (add capacity)
5. REPEAT — if constraint moves, go back to step 1
```

### 7.2 Drum-Buffer-Rope (DBR)

```
Drum: Bottleneck resource sets the pace
  → Schedule the bottleneck at maximum sustainable rate
  → This is the "drum beat" of the factory

Buffer: Time buffer before bottleneck
  → Ensure bottleneck is NEVER starved
  → Buffer = lead time protection (not inventory)

Rope: Pull signal from bottleneck to material release
  → Release materials only at the rate the bottleneck can process
  → Prevents WIP buildup at non-bottleneck resources
```

### 7.3 Bottleneck Identification

```
Method 1: Highest Utilization
  → Resource with utilization closest to 100% is likely bottleneck

Method 2: Largest Queue
  → Resource with most WIP waiting is likely bottleneck

Method 3: Sensitivity Analysis
  → Adding 10% capacity at each resource:
     Which addition most increases total throughput?
     → That resource is the bottleneck

Method 4: Throughput Analysis
  → Calculate throughput of each resource
  → Lowest throughput = bottleneck (if demand exceeds it)
```

---

## 8. Capacity Strategies

### 8.1 Lead, Lag, Match

| Strategy | Description | Risk | Best For |
|----------|-------------|------|----------|
| **Lead** | Add capacity BEFORE demand materializes | Over-investment if demand doesn't come | Growth markets, competitive advantage |
| **Lag** | Add capacity AFTER demand exceeds current capacity | Lost sales, service failures | Risk-averse, mature markets |
| **Match** | Add capacity incrementally as demand grows | Balanced risk | Most common approach |

### 8.2 Capacity Flexibility Options

| Option | Speed | Cost | Duration |
|--------|-------|------|----------|
| **Overtime** | Immediate | Medium (1.5-2x labor) | Weeks |
| **Extra shifts** | 1-2 weeks | Medium (hiring, training) | Months |
| **Temporary workers** | 1-4 weeks | Medium | Weeks-Months |
| **Outsourcing/CMO** | 4-12 weeks | High per unit, low capital | Months-Years |
| **New equipment** | 3-12 months | High capital, low operating | Years |
| **New facility** | 12-36 months | Very high capital | Decades |
| **Process improvement** | Weeks-Months | Low | Permanent |

### 8.3 Level vs Chase Capacity Strategy

```
Level Strategy:
  → Maintain constant production rate regardless of demand
  → Build inventory in low-demand periods, deplete in high-demand periods
  → + Stable workforce, efficient operations
  → − High inventory costs, risk of obsolescence

Chase Strategy:
  → Adjust production rate to match demand
  → Hire/fire, overtime/idle, outsource/insource
  → + Low inventory costs
  → − High workforce costs, quality/morale issues

Hybrid:
  → Level base production + chase for peaks
  → Use seasonal workforce, overtime, outsourcing for demand spikes
```

---

## 9. Overall Equipment Effectiveness (OEE)

### 9.1 OEE Calculation

```
OEE = Availability × Performance × Quality

Availability = (Planned Production Time − Downtime) / Planned Production Time
  Losses: Breakdowns, changeovers, material shortages

Performance = (Ideal Cycle Time × Total Pieces) / Run Time
  Losses: Minor stops, reduced speed, idling

Quality = Good Pieces / Total Pieces
  Losses: Defects, rework, startup losses
```

### 9.2 OEE Benchmarks

| Level | OEE | Interpretation |
|-------|-----|---------------|
| **World Class** | ≥ 85% | Best-in-class manufacturing |
| **Good** | 70-84% | Above average, room for improvement |
| **Average** | 55-69% | Typical manufacturing plant |
| **Poor** | < 55% | Significant improvement needed |

### 9.3 Six Big Losses

| Loss Category | OEE Component | Examples |
|--------------|---------------|---------|
| **Breakdowns** | Availability | Equipment failure, unplanned maintenance |
| **Setup/Changeover** | Availability | Product changeover, material change |
| **Minor Stops** | Performance | Jams, cleaning, minor adjustments |
| **Reduced Speed** | Performance | Worn tooling, operator inefficiency |
| **Startup Rejects** | Quality | Defects during warmup/stabilization |
| **Production Rejects** | Quality | In-process defects, rework |

---

## 10. Input/Output Control (I/O)

### 10.1 Purpose

I/O control monitors actual work center performance against planned input and output rates. It detects capacity imbalances before they become critical.

### 10.2 I/O Report

```
Work Center: Assembly Line 3
Planned Input: 160 hrs/week
Planned Output: 160 hrs/week

| Week | Planned In | Actual In | Planned Out | Actual Out | Queue |
|------|-----------|-----------|-------------|------------|-------|
| 1 | 160 | 170 | 160 | 155 | 215 |
| 2 | 160 | 165 | 160 | 150 | 230 |
| 3 | 160 | 175 | 160 | 160 | 245 |
| 4 | 160 | 160 | 160 | 145 | 260 |

Queue is growing! Actual output < actual input
→ Work center falling behind
→ Actions: overtime, reduce input (hold releases), add capacity
```

### 10.3 I/O Rules

```
If Queue growing (Input > Output):
    1. Reduce input (hold planned order releases)
    2. Increase output (overtime, additional resources)
    3. Both

If Queue shrinking (Output > Input):
    1. Work center may run out of work (starving)
    2. Increase input or accept lower utilization
    3. Use freed capacity for maintenance/training

Target: Stable queue at desired level (queue = lead time buffer)
```

---

## 11. Capacity Planning in Major Systems

### SAP S/4HANA
- **PP-CRP**: Capacity Requirements Planning against work centers
- **PP-SFC**: Shop Floor Control with capacity leveling
- **APO/IBP PP/DS**: Advanced finite capacity scheduling
- **Resources**: Work centers with available capacity, shifts, calendars

### Oracle Cloud SCM
- **Production Scheduling**: Finite capacity scheduling
- **Supply Planning**: Capacity-constrained supply planning
- **Manufacturing**: Shop floor capacity tracking

### Kinaxis RapidResponse
- **Capacity Planning**: Concurrent capacity analysis
- **What-If**: Real-time capacity scenario modeling
- **Bottleneck Analysis**: Identify and resolve constraints

---

## 12. Key Capacity Formulas

| Formula | Expression | Use |
|---------|-----------|-----|
| **Available Capacity** | # Resources × Hours/Period × Efficiency | What's available |
| **Required Capacity** | Σ(Setup + Qty × Run Time) | What's needed |
| **Utilization** | Required / Available × 100% | How busy |
| **Efficiency** | Standard Hours / Actual Hours × 100% | How productive |
| **OEE** | Availability × Performance × Quality | Equipment effectiveness |
| **Throughput** | Output / Time Period | Flow rate |
| **Cycle Time** | 1 / Throughput | Time per unit |
| **Takt Time** | Available Time / Customer Demand | Required pace |
| **Queue Time** | WIP / Throughput Rate | Little's Law |

---

*Sources: ASCM CPIM Part 2 (MPR Module), Vollmann et al. "Manufacturing Planning and Control", Goldratt "The Goal", ASCM Dictionary (17th ed), Nakajima "Introduction to TPM", Toyota Production System*

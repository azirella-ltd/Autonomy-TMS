# Material Requirements Planning (MRP) Logic & Lot Sizing

## Comprehensive Reference Guide for MRP and MPS

---

## 1. Planning Hierarchy

```
Strategic Plan (3-5 years)
    ↓
Sales & Operations Planning / IBP (18-36 months, monthly)
    ↓ Aggregate demand plan, capacity authorization
Master Production Schedule (MPS) (3-18 months, weekly)
    ↓ Product-level production schedule
Material Requirements Planning (MRP) (1-6 months, daily/weekly)
    ↓ Component-level purchase/production requirements
Execution (Purchase Orders, Manufacturing Orders, Transfer Orders)
```

---

## 2. Master Production Scheduling (MPS)

### 2.1 Definition

The MPS is a statement of what the company plans to **produce** (not what it wants to sell). It is expressed in specific products, quantities, and dates. The MPS sits between aggregate S&OP planning and detailed MRP execution.

### 2.2 MPS Inputs

| Input | Source | Purpose |
|-------|--------|---------|
| **Demand forecast** | Demand planning | Expected future demand |
| **Customer orders** | Order management | Committed demand |
| **Safety stock** | Inventory policy | Buffer against uncertainty |
| **Beginning inventory** | Inventory management | Current stock |
| **Production capacity** | Capacity planning | Resource constraints |
| **Lot sizing rules** | Planning parameters | Order quantity constraints |

### 2.3 MPS Calculation

```
For each time bucket t:

Projected Available Balance (PAB):
    PAB(t) = PAB(t-1) + MPS(t) - max(Forecast(t), Customer Orders(t))

When PAB(t) < Safety Stock:
    Schedule MPS receipt to bring PAB back above safety stock
    MPS quantity determined by lot sizing rule

Available-to-Promise (ATP):
    ATP = MPS receipts - Customer orders (not yet shipped)
```

### 2.4 MPS Example

| Period | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|--------|---|---|---|---|---|---|---|---|
| **Forecast** | 30 | 30 | 30 | 40 | 40 | 40 | 40 | 40 |
| **Customer Orders** | 35 | 20 | 10 | 5 | 0 | 0 | 0 | 0 |
| **PAB** | 25 | 55 | 25 | 45 | 5 | 25 | 45 | 5 |
| **MPS** | 0 | 60 | 0 | 60 | 0 | 60 | 60 | 0 |
| **ATP** | 5 | 40 | | 55 | | 60 | 60 | |

*Lot size = 60, Safety stock = 5, Beginning inventory = 60*

### 2.5 Time Fences

| Fence | Horizon | What Changes | Who Approves |
|-------|---------|-------------|--------------|
| **Demand Time Fence (DTF)** | 0 to DTF | Only customer orders (no forecast) | Planner |
| **Planning Time Fence (PTF)** | DTF to PTF | MPS changes require approval | Supervisor/Manager |
| **Beyond PTF** | PTF to horizon | System can auto-plan | Automated |

**Inside DTF**: MPS is driven by customer orders only (forecast ignored). This prevents nervousness from forecast changes in the execution horizon.

**Between DTF and PTF**: MPS is driven by the greater of forecast or customer orders. Changes require authorization.

**Beyond PTF**: MPS is driven by forecast. System auto-generates planned orders.

### 2.6 Rough-Cut Capacity Planning (RCCP)

RCCP validates that the MPS is feasible at the resource level:

```
For each critical resource r:
    Required Capacity(r) = Σ (MPS(product_i) × Time_per_unit(r, product_i))
    Available Capacity(r) = Working_hours × Efficiency × Utilization

If Required > Available:
    → Adjust MPS (level-load, reduce quantity)
    → Add capacity (overtime, outsource, shift)
    → Escalate to S&OP for resolution
```

**Bill of Resources (BOR)**: Simplified capacity model mapping product families to critical resources:

| Product Family | Resource A (hrs/unit) | Resource B (hrs/unit) | Resource C (hrs/unit) |
|---------------|----------------------|----------------------|----------------------|
| Family X | 0.5 | 0.3 | 0.1 |
| Family Y | 0.2 | 0.6 | 0.4 |
| Family Z | 0.8 | 0.1 | 0.2 |

---

## 3. MRP Logic

### 3.1 MRP Inputs

| Input | Description |
|-------|-------------|
| **MPS** | Master production schedule (independent demand) |
| **BOM** | Bill of materials (product structure) |
| **Inventory records** | On-hand, allocated, on-order quantities |
| **Lead times** | Purchase, manufacturing, transit lead times |
| **Lot sizing rules** | Minimum order, lot size, multiple rules |
| **Safety stock** | Buffer inventory requirements |
| **Scrap/yield factors** | Expected loss rates |

### 3.2 MRP Calculation (Net Requirements)

For each component at each BOM level (starting from Level 0):

```
Step 1: Gross Requirements
    GR(t) = Σ (Parent_Planned_Orders(t) × BOM_Quantity)
    + Independent_Demand(t)  # if service parts

Step 2: Scheduled Receipts
    SR(t) = Open POs + Open MOs due in period t

Step 3: Projected Available (PAB)
    PAB(t) = PAB(t-1) + SR(t) + Planned_Receipts(t) - GR(t)

Step 4: Net Requirements
    NR(t) = max(0, Safety_Stock + GR(t) - PAB(t-1) - SR(t))

Step 5: Planned Order Receipts (apply lot sizing)
    POR(t) = Lot_Size_Rule(NR(t))

Step 6: Planned Order Releases (offset by lead time)
    PORL(t - Lead_Time) = POR(t)
```

### 3.3 MRP Example — Single Level

**Product A** — Lead time = 2 weeks, Lot size = 50, Safety stock = 10

| Period | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|--------|---|---|---|---|---|---|---|---|
| **Gross Req** | 20 | 25 | 30 | 25 | 35 | 20 | 30 | 25 |
| **Sched Receipts** | | 50 | | | | | | |
| **PAB** | 30 | 55 | 25 | 50 | 15 | 45 | 15 | 40 |
| **Net Req** | | | | 10 | | | 20 | |
| **Planned Receipt** | | | | 50 | | | 50 | |
| **Planned Release** | | 50 | | | 50 | | | |

*Beginning inventory = 50, Safety stock = 10*

### 3.4 Multi-Level BOM Explosion

```
Level 0: Finished Good A
    ├── Level 1: Subassembly B (qty 2)
    │       ├── Level 2: Component C (qty 3)
    │       └── Level 2: Component D (qty 1)
    └── Level 1: Component E (qty 4)
```

**Low-Level Coding**: Each item is assigned to the lowest level in any BOM where it appears. MRP processes level by level (0, 1, 2, ...) to ensure all gross requirements for a component are accumulated before netting.

**Pegging**: Links dependent demand back to parent orders:
- **Full pegging**: Traces requirement to original customer order
- **Single-level pegging**: Links to immediate parent only
- **Where-used**: Shows all parents that use a component

### 3.5 Scrap and Yield Adjustment

```
Adjusted_Gross_Req = Gross_Req / (1 - Scrap_Rate)

Example: Need 100 units, 5% scrap rate
  Adjusted = 100 / 0.95 = 106 units (plan to produce/order 106)

For cumulative yield through BOM levels:
  Adjusted = Required / (Yield_level1 × Yield_level2 × ... × Yield_levelN)
```

---

## 4. Lot Sizing Rules

### 4.1 Static Lot Sizing

| Rule | Description | When to Use |
|------|-------------|-------------|
| **Lot-for-Lot (L4L)** | Order exactly what's needed | Expensive items, perishable, pull systems |
| **Fixed Order Quantity (FOQ)** | Order a fixed quantity each time | Standard pack sizes, supplier minimums |
| **Fixed Period (FP)** | Cover N periods of demand | Periodic review systems |
| **Min/Max** | Order up to Max when below Min | Simple inventory policies |

### 4.2 Dynamic Lot Sizing

#### Economic Order Quantity (EOQ)
```
EOQ = √(2 × D × S / H)

Where:
  D = Annual demand
  S = Setup/ordering cost per order
  H = Holding cost per unit per year

Total Cost = (D/Q) × S + (Q/2) × H
```

#### Period Order Quantity (POQ)
```
POQ = EOQ / Average_Period_Demand (rounded to nearest integer)
```
Covers POQ periods of demand per order.

#### Part Period Balancing (PPB)
```
Accumulate demand until:
  Cumulative Carrying Cost ≈ Setup Cost

Carrying Cost for period t = Demand(t) × t × h
where h = holding cost per unit per period
```

#### Wagner-Whitin Algorithm (Optimal)
```
Dynamic programming approach:
  f(t) = min over all j<t [f(j) + Setup_Cost + Σ(k=j+1 to t) Holding_Cost(k)]

Finds globally optimal lot sizing for entire horizon.
Computationally intensive: O(T²) where T = # periods.
```

#### Silver-Meal Heuristic
```
Accumulate demand until:
  Average Cost per Period starts increasing

ACP(T) = (Setup_Cost + Σ(t=1 to T) t × h × D(t)) / T

Order when ACP(T+1) > ACP(T)
```

#### Least Unit Cost (LUC)
```
Similar to Silver-Meal but minimizes cost per unit:
  UC(T) = (Setup_Cost + Σ(t=1 to T) t × h × D(t)) / Σ(t=1 to T) D(t)

Order when UC(T+1) > UC(T)
```

### 4.3 Lot Sizing Comparison

| Method | Optimality | Complexity | Holding Cost | Setup Cost | Best For |
|--------|-----------|------------|-------------|------------|----------|
| **L4L** | N/A | O(1) | Minimal | High (many setups) | Expensive items |
| **EOQ** | Near-optimal (constant demand) | O(1) | Moderate | Moderate | Stable demand |
| **POQ** | Near-optimal | O(1) | Moderate | Moderate | Stable demand |
| **PPB** | Good heuristic | O(T) | Balanced | Balanced | Variable demand |
| **Silver-Meal** | Good heuristic | O(T) | Balanced | Balanced | Variable demand |
| **LUC** | Good heuristic | O(T) | Balanced | Balanced | Variable demand |
| **Wagner-Whitin** | Optimal | O(T²) | Optimal | Optimal | When optimality matters |

### 4.4 Lot Sizing Modifiers

| Modifier | Description |
|----------|-------------|
| **Minimum Order Quantity (MOQ)** | Supplier or production minimum |
| **Maximum Order Quantity** | Storage, handling, or capacity limit |
| **Order Multiple** | Round up to nearest multiple (pallet, case) |
| **Scrap Allowance** | Increase order by scrap percentage |
| **Rounding Rule** | Round up/down/nearest to order multiple |

---

## 5. MRP Nervousness and Dampening

### 5.1 Causes of MRP Nervousness

- Small changes in demand → large changes in planned orders (bullwhip)
- Rolling horizon: as time advances, new data shifts plans
- Lot sizing amplification (especially fixed-quantity rules)
- BOM explosion cascading changes through levels

### 5.2 Dampening Techniques

| Technique | Description |
|-----------|-------------|
| **Firm planned orders** | Freeze orders inside planning fence |
| **Time fences** | Limit automated changes in near-term |
| **Lot sizing stability** | Use fixed periods vs L4L to smooth orders |
| **Safety stock buffers** | Absorb small variations without replanning |
| **Exception filtering** | Suppress messages below threshold |
| **Periodic review** | Plan weekly instead of daily to reduce churn |

---

## 6. MRP Action Messages

| Message | Meaning | Action Required |
|---------|---------|----------------|
| **Release** | Planned order ready for release | Create PO/MO/TO |
| **Expedite** | Existing order needed sooner | Move receipt date earlier |
| **De-expedite** | Existing order needed later | Move receipt date later |
| **Cancel** | Order no longer needed | Cancel PO/MO/TO |
| **Increase** | Need more than ordered | Increase order quantity |
| **Decrease** | Need less than ordered | Reduce order quantity |
| **Reschedule In** | Move order to earlier date | Pull forward |
| **Reschedule Out** | Move order to later date | Push back |

---

## 7. Capacity Requirements Planning (CRP)

CRP validates MRP planned orders against detailed capacity:

```
For each work center and period:
    Required Hours = Σ (Planned_Order_Qty × Setup_Time + Planned_Order_Qty × Run_Time)
    Available Hours = # Shifts × Hours/Shift × # Days × Efficiency

Load % = Required Hours / Available Hours × 100

If Load % > 100%:
    → Overtime, subcontracting
    → Reschedule orders
    → Escalate capacity constraint
```

### CRP vs RCCP

| Aspect | RCCP | CRP |
|--------|------|-----|
| **Input** | MPS (aggregate) | MRP (detailed) |
| **Level** | Critical resources only | All work centers |
| **BOM** | Bill of Resources (simplified) | Full routing and BOM |
| **Horizon** | Medium-term (weekly) | Short-term (daily/shift) |
| **Purpose** | Validate MPS feasibility | Validate MRP feasibility |

---

## 8. Advanced MRP Concepts

### 8.1 Multi-Plant MRP

```
For each product at each plant:
    1. Check sourcing rules (buy/make/transfer)
    2. Net requirements at each location
    3. Generate appropriate order type:
       - Buy → Purchase Requisition → Purchase Order
       - Make → Planned Production Order → Manufacturing Order
       - Transfer → Planned Transfer → Transfer Order
    4. Cascade through supply network (plant-to-plant)
```

### 8.2 MRP with Multi-Sourcing

When a component can be sourced from multiple suppliers:

```
Sourcing Rules:
    Supplier A: 60% share, LT = 14 days, MOQ = 500
    Supplier B: 30% share, LT = 21 days, MOQ = 200
    Supplier C: 10% share, LT = 7 days, MOQ = 100 (emergency)

Net Requirement = 1000 units
    → Supplier A: 600 units
    → Supplier B: 300 units
    → Supplier C: 100 units

Lead time offset per supplier (different release dates)
```

### 8.3 Phantom Assemblies

Phantoms (or blow-through items) are subassemblies that are never stocked:

```
BOM Level 0: Finished Good A
    BOM Level 1: *Phantom* Subassembly B (qty 1)
        BOM Level 2: Component C (qty 3)
        BOM Level 2: Component D (qty 2)

MRP treats Phantom as if its components belong directly to parent:
    Gross Req for C = MPS(A) × 1 × 3 = MPS(A) × 3
    Gross Req for D = MPS(A) × 1 × 2 = MPS(A) × 2
```

### 8.4 Planning BOM

For products sold as families but produced as variants:

```
Product Family: Widget
    Variant A: 40% of family forecast
    Variant B: 35% of family forecast
    Variant C: 25% of family forecast

Planning BOM distributes family forecast to variants:
    If Family forecast = 1000:
        MPS(A) = 400
        MPS(B) = 350
        MPS(C) = 250
```

### 8.5 Super BOM (Modular BOM)

For configure-to-order products:

```
Base Module: Common to all configurations (100%)
Option Module 1: Engine Type (Diesel 60%, Electric 40%)
Option Module 2: Color (Red 30%, Blue 50%, White 20%)
Option Module 3: Package (Standard 70%, Premium 30%)
```

---

## 9. MRP II (Manufacturing Resource Planning)

MRP II extends MRP to include:

| MRP Component | MRP II Extension |
|---------------|-----------------|
| Material planning | + Capacity planning |
| Production scheduling | + Shop floor control |
| Inventory management | + Financial integration |
| Purchase planning | + Cost accounting |
| | + What-if simulation |
| | + Performance measurement |

**Closed-Loop MRP**: Adds feedback from execution to planning:
```
MPS → MRP → CRP → Capacity OK?
    → YES: Release orders → Execute → Feedback
    → NO: Adjust MPS or capacity → Re-run MRP
```

---

## 10. MRP in Modern ERP Systems

### SAP S/4HANA MRP
- **MRP Live**: In-memory MRP running on HANA for real-time planning
- **Planning strategies**: MTS, MTO, ATO, ETO with different MRP logic
- **MRP types**: PD (full MRP), VB (consumption-based), V1/V2 (reorder point)
- **Planning run modes**: NETCH (net change), NEUPL (regenerative), NETPL (net change in planning horizon)

### Oracle Cloud MRP
- Concurrent MRP processing
- Integrated with Oracle Supply Planning
- Exception-based management
- Multi-organization planning

### Kinaxis MRP
- Concurrent planning (supply + demand simultaneously)
- Real-time what-if on MRP changes
- Integrated with ATP and S&OP
- Machine learning for parameter tuning

---

*Sources: ASCM CPIM Part 2 (MPR Module), Vollmann et al. "Manufacturing Planning and Control for Supply Chain Management", Orlicky's Material Requirements Planning (3rd ed), ASCM CPIM Learning System*

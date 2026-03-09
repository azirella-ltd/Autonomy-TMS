# Distribution Requirements Planning (DRP) & Network Planning

## Comprehensive Reference Guide for Distribution and Logistics Planning

---

## 1. Definition

### Distribution Requirements Planning (DRP)
DRP is the process of determining the need to replenish inventory at distribution centers (DCs), warehouses, and branch locations. DRP uses the same time-phased logic as MRP but applies it to the distribution network rather than the manufacturing BOM.

**DRP answers**: "When and how much inventory should be shipped from each supply point to each demand point across the distribution network?"

### Relationship to MRP
```
Demand → DRP (distribution network) → MPS/MRP (manufacturing) → Purchasing

MRP explodes PRODUCT structure (BOM)
DRP explodes NETWORK structure (distribution topology)
```

---

## 2. DRP Calculation Logic

### 2.1 DRP Record (Per Product, Per Location)

DRP uses the same netting logic as MRP, applied at each stocking location:

```
For each location and product:

Gross Requirements = Forecast demand + Dependent demand from downstream
Scheduled Receipts = In-transit shipments (open transfer orders)
Projected Available = Beginning Inventory + SR - GR
Net Requirements = max(0, Safety Stock - Projected Available)
Planned Receipts = Lot_Size_Rule(Net Requirements)
Planned Shipments = Planned Receipts offset by transit lead time
```

### 2.2 DRP Example — Regional DC

**Product X at East DC** — Transit LT = 3 days, Lot size = 200, Safety Stock = 50

| Period (Week) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|--------------|---|---|---|---|---|---|---|---|
| **Forecast** | 80 | 70 | 90 | 85 | 75 | 95 | 80 | 70 |
| **Scheduled Receipts** | | 200 | | | | | | |
| **PAB** | 120 | 250 | 160 | 75 | 200 | 105 | 225 | 155 |
| **Planned Receipt** | | | | | 200 | | 200 | |
| **Planned Shipment** | | | | 200 | | 200 | | |

*Beginning inventory = 200*

### 2.3 Multi-Echelon DRP

DRP cascades through the network from customer-facing locations back to source:

```
Level 1 (Demand):   Stores / Customers
    ↑ Planned Shipments
Level 2 (Regional): Regional DCs
    ↑ Planned Shipments
Level 3 (Central):  Central DC / Plant Warehouse
    ↑ Manufacturing Orders
Level 4 (Supply):   Manufacturing Plant
```

**Dependent Demand**: Each level's planned shipments become gross requirements for the upstream level.

```
Gross Requirements at Central DC =
    Σ (Planned Shipments from all Regional DCs it serves)
```

---

## 3. Distribution Network Design

### 3.1 Network Topologies

| Topology | Structure | Trade-offs |
|----------|-----------|------------|
| **Direct Ship** | Factory → Customer | Low inventory, high transport cost, long lead time |
| **Single Echelon** | Factory → DC → Customer | Moderate inventory, moderate transport, moderate lead time |
| **Two Echelon** | Factory → CDC → RDC → Customer | Higher inventory, lower transport, faster delivery |
| **Hub and Spoke** | Factory → Hub → Spoke → Customer | Consolidation benefits, flexible routing |
| **Cross-Dock** | Factory → Cross-Dock → Customer | Minimal inventory, fast flow-through |

### 3.2 Number of Distribution Centers

The optimal number of DCs balances:

```
Total Cost = Transportation Cost + Inventory Cost + Facility Cost + Service

As # DCs increases:
  ✅ Transportation cost decreases (closer to customers)
  ✅ Service level increases (faster delivery)
  ❌ Inventory cost increases (more safety stock = √n effect)
  ❌ Facility cost increases (more buildings, staff)
```

**Square Root Law of Inventory**:
```
SS_n = SS_1 × √n

Where:
  SS_n = total safety stock with n locations
  SS_1 = safety stock with 1 centralized location
  n = number of locations

Example: 1 DC with SS = 1000 units
  4 DCs: SS = 1000 × √4 = 2000 units (100% more inventory)
  9 DCs: SS = 1000 × √9 = 3000 units (200% more inventory)
```

**Caveat**: The square root law assumes demand is identical and uncorrelated across locations. With correlated demand, the effect is less dramatic.

### 3.3 Facility Location Models

#### Center of Gravity
```
X* = Σ(wᵢ × xᵢ) / Σwᵢ
Y* = Σ(wᵢ × yᵢ) / Σwᵢ

Where:
  (xᵢ, yᵢ) = coordinates of demand point i
  wᵢ = weight (volume or cost) at demand point i
```

#### P-Median Problem
```
Minimize: Σᵢ Σⱼ dᵢⱼ × xᵢⱼ

Subject to:
  Open exactly P facilities
  Each customer assigned to exactly one facility
  Customers only assigned to open facilities
```

#### Mixed-Integer Programming (MIP) for Network Design
```
Minimize: Σⱼ fⱼ×yⱼ + Σᵢ Σⱼ cᵢⱼ×xᵢⱼ + Σⱼ hⱼ×Iⱼ

Subject to:
  Demand coverage: Σⱼ xᵢⱼ = dᵢ for all customers i
  Capacity: Σᵢ xᵢⱼ ≤ Cⱼ×yⱼ for all facilities j
  Binary: yⱼ ∈ {0,1} (open/close)
  Non-negative: xᵢⱼ ≥ 0 (flow)

Where:
  fⱼ = fixed cost of opening facility j
  cᵢⱼ = transportation cost per unit from j to i
  hⱼ = inventory holding cost at facility j
  dᵢ = demand at customer i
  Cⱼ = capacity of facility j
```

---

## 4. Transportation Planning

### 4.1 Transportation Modes

| Mode | Speed | Cost/Unit | Capacity | Best For |
|------|-------|-----------|----------|----------|
| **Air** | Very fast | Very high | Low | High-value, urgent, perishable |
| **Road (TL)** | Fast | Moderate | Medium | Domestic, full-load, flexible |
| **Road (LTL)** | Moderate | Higher/unit | Low-Medium | Smaller shipments, mixed |
| **Rail** | Moderate | Low | Very high | Bulk, heavy, long-distance |
| **Ocean** | Slow | Very low | Very high | International, bulk, non-urgent |
| **Intermodal** | Moderate | Low-Moderate | High | Containers, long-distance |
| **Pipeline** | Continuous | Very low | High | Liquids, gases, continuous flow |

### 4.2 Transportation Optimization

**Vehicle Routing Problem (VRP)**:
```
Minimize: Total distance/cost of all vehicle routes

Subject to:
  Each customer visited exactly once
  Each route starts and ends at depot
  Vehicle capacity not exceeded
  Time windows respected (VRPTW)
```

**Consolidation Strategies**:
| Strategy | Description | Savings |
|----------|-------------|---------|
| **Temporal** | Accumulate orders over time, ship together | 10-20% |
| **Spatial** | Combine shipments for nearby destinations | 15-25% |
| **Product** | Combine different products on same truck | 5-15% |
| **Mode** | Shift from LTL to TL by consolidating | 20-40% |
| **Cross-dock** | Break bulk and reconsolidate at hub | 10-30% |

### 4.3 Milk Run vs Direct Shipping

```
Direct Shipping:
  Supplier A → Plant (full truck)
  Supplier B → Plant (full truck)
  Supplier C → Plant (full truck)
  Cost: 3 × full truck cost

Milk Run:
  Truck picks up: Supplier A → Supplier B → Supplier C → Plant
  Cost: 1 × route cost (lower per-supplier, but longer route)

Break-even: Use milk run when individual supplier volumes < truck capacity
```

---

## 5. Inventory Deployment

### 5.1 Push vs Pull Distribution

| Aspect | Push | Pull |
|--------|------|------|
| **Driver** | Forecast/plan | Actual demand/consumption |
| **Replenishment** | Scheduled shipments | Triggered by stock level |
| **Inventory** | Higher (anticipation) | Lower (demand-driven) |
| **Responsiveness** | Slower (batch) | Faster (continuous) |
| **Risk** | Excess/obsolescence | Stockout if supply disruption |
| **Best for** | Seasonal, promotional | Stable demand, short lead times |

### 5.2 Fair Share Allocation

When supply is constrained, allocate proportionally:

```
Allocation_i = Available_Supply × (Demand_i / Total_Demand)

Example: 800 units available, 3 DCs need 1000 total
  DC East (demand 400): 800 × 400/1000 = 320
  DC West (demand 350): 800 × 350/1000 = 280
  DC Central (demand 250): 800 × 250/1000 = 200
```

### 5.3 Needs-Based Allocation

Allocate based on urgency (days of supply):

```
Priority = Days_of_Supply = Inventory / Daily_Demand

Allocate to location with LOWEST days of supply first

Example:
  DC East: 200 units / 40/day = 5 DOS ← Highest priority
  DC West: 300 units / 35/day = 8.6 DOS
  DC Central: 150 units / 25/day = 6 DOS ← Second priority

Allocate to East first, then Central, then West
```

### 5.4 Vendor Managed Inventory (VMI)

```
Traditional:
  Customer forecasts → Customer orders → Supplier ships

VMI:
  Customer shares POS/inventory data → Supplier plans → Supplier ships

Benefits:
  - Reduced bullwhip effect (supplier sees actual demand)
  - Lower inventory (supplier optimizes across all customers)
  - Better fill rates (continuous monitoring)
  - Reduced ordering costs (no PO processing)

Risks:
  - Trust and data sharing requirements
  - Customer loses control over inventory
  - Supplier may prioritize profitable customers
```

---

## 6. Postponement and Delayed Differentiation

### 6.1 Types of Postponement

| Type | Description | Example |
|------|-------------|---------|
| **Form** | Delay final assembly/configuration | Build-to-order PCs (Dell model) |
| **Time** | Delay production until orders received | Fast fashion (Zara) |
| **Place** | Delay geographic deployment | Regional packaging/labeling |
| **Price** | Delay pricing decision | Dynamic pricing (airlines) |

### 6.2 Decoupling Point

```
Push ←──────── Decoupling Point ────────→ Pull
(Forecast-driven)                    (Demand-driven)

Make-to-Stock:     [Raw Mat → Fab → Assembly → Pack → Ship] → Customer
                                                      ↑DP

Assemble-to-Order: [Raw Mat → Fab → Assembly] → [Pack → Ship] → Customer
                                       ↑DP

Make-to-Order:     [Raw Mat → Fab] → [Assembly → Pack → Ship] → Customer
                              ↑DP

Engineer-to-Order: [Design → Raw Mat → Fab → Assembly → Pack → Ship] → Customer
                    ↑DP
```

**Moving DP upstream**:
- Reduces finished goods inventory
- Increases customization capability
- Increases lead time to customer
- Requires more flexible manufacturing

---

## 7. Reverse Logistics

### 7.1 Returns Management Process

```
1. Return Authorization → Verify eligibility, issue RMA number
2. Collection → Customer ships back or scheduled pickup
3. Receiving → Inspect, verify against RMA
4. Disposition → Determine action:
   a. Restock (resellable condition)
   b. Refurbish (minor repair, repackage)
   c. Remanufacture (restore to like-new)
   d. Recycle (recover materials)
   e. Dispose (waste, landfill)
5. Credit/Replace → Process customer credit or replacement
6. Feedback → Root cause analysis for quality improvement
```

### 7.2 Circular Supply Chain

```
Forward Flow:  Raw Material → Manufacturing → Distribution → Customer
                    ↑                                           ↓
Reverse Flow:  Recycling ← Remanufacturing ← Collection ← Return
```

---

## 8. Distribution Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **OTIF** | % orders delivered On-Time AND In-Full | > 95% |
| **Delivery Lead Time** | Order date to receipt date | Industry dependent |
| **Transportation Cost %** | Transport cost / Revenue | 3-8% |
| **Warehouse Utilization** | Space used / Total space | 80-90% |
| **Order Cycle Time** | Order entry to delivery | < 48 hours (domestic) |
| **Dock-to-Stock Time** | Receipt to put-away | < 4 hours |
| **Pick Accuracy** | Correct picks / Total picks | > 99.5% |
| **Lines Shipped per Hour** | Productivity measure | Industry benchmark |
| **Truck Utilization** | Weight or cube used / Capacity | > 85% |
| **Cost per Order** | Total distribution cost / Orders shipped | Industry dependent |
| **Return Rate** | Returns / Shipments | < 5% (varies by industry) |

---

## 9. DRP in Major Platforms

### SAP S/4HANA
- **MRP with Multi-Plant**: DRP run across distribution network
- **Deployment**: Push-based allocation from central to regional
- **TLB (Transportation Load Builder)**: Consolidation optimization
- **SNP (Supply Network Planning in APO/IBP)**: Network-level optimization

### Kinaxis RapidResponse
- **Distribution planning**: Multi-echelon DRP with concurrent planning
- **Deployment optimization**: Needs-based and fair-share allocation
- **Transportation planning**: Load building and consolidation
- **What-if**: Test distribution strategy changes instantly

### Oracle Cloud SCM
- **Global Order Promising**: Network-wide ATP/sourcing
- **Inventory Organization**: Multi-site inventory management
- **Shipping Execution**: Transportation management
- **Distribution Planning**: Network-aware replenishment

---

## 10. Supply Network Design Optimization

### 10.1 Key Design Decisions

| Decision | Options | Factors |
|----------|---------|---------|
| **Number of facilities** | Centralize vs. decentralize | Cost, service, risk |
| **Facility locations** | Geographic positioning | Demand proximity, labor, taxes |
| **Facility roles** | CDC, RDC, Cross-dock, Factory | Volume, product mix, velocity |
| **Sourcing strategy** | Single vs. multi-source | Risk, cost, lead time |
| **Transportation network** | Direct, hub-spoke, milk run | Volume, frequency, cost |
| **Inventory positioning** | Where to hold safety stock | Lead time, variability, cost |
| **Postponement point** | MTS, ATO, MTO, ETO | Customization, lead time |

### 10.2 Total Cost of Distribution

```
Total Cost = Transportation + Warehousing + Inventory + Fixed Facility + Service Penalties

Minimize total cost subject to:
  Service level ≥ target (e.g., 95% OTIF)
  Capacity constraints at each facility
  Minimum/maximum throughput at facilities
  Geographic coverage requirements
```

---

*Sources: ASCM CPIM Part 2 (SMR Module), Martin Christopher "Logistics & Supply Chain Management", Ballou "Business Logistics/Supply Chain Management", Chopra & Meindl "Supply Chain Management", Simchi-Levi et al. "Designing and Managing the Supply Chain"*

# Supply Chain Network Design & Optimization

## Comprehensive Reference Guide

---

## 1. Overview

### Definition

Supply Chain Network Design (SCND) is the strategic process of determining the optimal configuration of a supply chain network — including the number, location, capacity, and role of facilities; transportation lanes; sourcing relationships; and inventory positioning — to minimize total cost while meeting service level requirements.

### Strategic Planning Horizon

Network design decisions are **long-term** (3-10 year horizon) and **capital-intensive** (facility investments, long-term contracts). They set the structural foundation that constrains all tactical and operational planning.

```
Network Design (Strategic, 3-10 years)
    ↓ Network structure, facility capacities
S&OP / IBP (Tactical, 1-3 years)
    ↓ Demand-supply balance, aggregate plans
MPS / MRP / DRP (Operational, weeks-months)
    ↓ Detailed schedules, material plans
Execution (Operational, days)
    ↓ Purchase orders, production orders, shipments
```

---

## 2. Key Network Design Decisions

### 2.1 Decision Categories

| Decision | Question | Time Horizon | Reversibility |
|----------|----------|-------------|---------------|
| **Number of facilities** | How many plants, DCs, warehouses? | 5-10 years | Very low |
| **Facility locations** | Where geographically? | 5-10 years | Very low |
| **Facility capacity** | How much capacity at each? | 3-7 years | Low |
| **Facility role** | What does each facility do? | 2-5 years | Medium |
| **Sourcing strategy** | Who supplies what to whom? | 1-3 years | Medium |
| **Transportation network** | What lanes, modes, carriers? | 1-2 years | Medium-High |
| **Inventory positioning** | Where to hold buffer stock? | Months-1 year | High |
| **Production allocation** | Which products at which plants? | 6-12 months | High |

### 2.2 Facility Types

| Type | Abbreviation | Function | Typical Size |
|------|-------------|----------|-------------|
| **Manufacturing Plant** | Plant/MFG | Transform raw materials into products | Large, specialized |
| **Central Distribution Center** | CDC/NDC | Primary distribution hub | Very large |
| **Regional Distribution Center** | RDC | Regional stock point, fast delivery | Large |
| **Local Distribution Center** | LDC | Last-mile delivery point | Medium |
| **Cross-Dock** | XD | Flow-through, minimal storage | Medium |
| **Forward Stocking Location** | FSL | Small stock points near customers | Small |
| **Returns Center** | RC | Reverse logistics processing | Medium |
| **Co-Manufacturing / 3PL** | 3PL | Outsourced warehousing/manufacturing | Variable |

---

## 3. Network Design Optimization

### 3.1 Total Cost Model

```
Total Supply Chain Cost =
    Fixed Facility Costs (rent, depreciation, overhead)
  + Variable Facility Costs (labor, utilities, handling)
  + Inbound Transportation (supplier → facility)
  + Outbound Transportation (facility → customer)
  + Inter-facility Transportation (transfers)
  + Inventory Carrying Costs (cycle + safety stock)
  + Production Costs (manufacturing, conversion)
  + Procurement Costs (raw material, components)
  + Duties and Taxes (import/export, local taxes)
  + Service Penalty Costs (stockouts, late deliveries)
```

### 3.2 Mixed-Integer Programming (MIP) Formulation

**Sets**:
- I = set of potential facility locations
- J = set of customer demand zones
- K = set of products
- S = set of suppliers
- T = set of time periods

**Decision Variables**:
- y_i = 1 if facility i is open, 0 otherwise (binary)
- x_ijk = quantity of product k shipped from facility i to customer j (continuous)
- z_sik = quantity of product k sourced from supplier s to facility i (continuous)
- I_ikt = inventory of product k at facility i in period t (continuous)

**Objective**: Minimize total cost

```
Min Σᵢ fᵢyᵢ                           (fixed facility costs)
  + Σᵢ Σⱼ Σₖ cᵢⱼₖ × xᵢⱼₖ            (outbound transportation)
  + Σₛ Σᵢ Σₖ dₛᵢₖ × zₛᵢₖ            (inbound transportation)
  + Σᵢ Σₖ hᵢₖ × Iᵢₖ                  (inventory holding)
  + Σᵢ Σₖ pᵢₖ × Σⱼ xᵢⱼₖ             (production/handling)
```

**Constraints**:
```
Demand:    Σᵢ xᵢⱼₖ = Dⱼₖ              (all demand met)
Capacity:  Σⱼ Σₖ xᵢⱼₖ ≤ Cᵢ × yᵢ      (facility capacity)
Supply:    Σᵢ zₛᵢₖ ≤ Sₛₖ              (supplier capacity)
Balance:   Σₛ zₛᵢₖ ≥ Σⱼ xᵢⱼₖ          (flow conservation)
Service:   LeadTime(i,j) ≤ MaxLT(j)   (service level)
Binary:    yᵢ ∈ {0,1}
Non-neg:   xᵢⱼₖ, zₛᵢₖ, Iᵢₖ ≥ 0
```

### 3.3 Multi-Objective Optimization

Real network design often involves conflicting objectives:

| Objective | Metric | Direction |
|-----------|--------|-----------|
| **Cost** | Total supply chain cost | Minimize |
| **Service** | % demand within target lead time | Maximize |
| **Risk** | Supply chain resilience | Maximize |
| **Sustainability** | CO2 emissions, waste | Minimize |
| **Flexibility** | Ability to handle demand shifts | Maximize |
| **Working Capital** | Inventory investment | Minimize |

**Trade-offs**: More DCs → better service but higher cost and inventory. More suppliers → more resilience but higher complexity and cost.

---

## 4. Greenfield vs Brownfield Analysis

### 4.1 Greenfield Analysis

Design network from scratch (no existing constraints):
- Center-of-gravity analysis for optimal locations
- Unconstrained optimization for facility count and capacity
- Provides theoretical optimum as benchmark

### 4.2 Brownfield Analysis

Optimize within existing network constraints:
- Existing facilities have sunk costs (can't easily close)
- Lease terms, workforce, community commitments
- Evaluate incremental changes: add/close/resize facilities
- More realistic for established companies

### 4.3 Scenario Analysis

Evaluate network under multiple futures:

| Scenario | Variable | Impact on Network |
|----------|----------|-------------------|
| **Demand growth** | +20% demand in new region | Add RDC in growth area |
| **Demand decline** | -15% demand in mature market | Consolidate to fewer DCs |
| **Nearshoring** | Move manufacturing closer to demand | New plant, shorter lanes |
| **Tariff change** | Import duty increase 15% | Local sourcing, 3PL |
| **E-commerce growth** | 50% of sales online | More FSLs, last-mile optimization |
| **Sustainability target** | -30% CO2 by 2030 | Mode shift, shorter lanes |
| **Supply disruption** | Key supplier region unavailable | Dual sourcing, safety stock |

---

## 5. Sourcing Strategy

### 5.1 Single vs Multi-Sourcing

| Strategy | Pros | Cons |
|----------|------|------|
| **Single Source** | Volume leverage, deep relationship, lower complexity | High risk, dependency |
| **Dual Source** | Risk mitigation, competitive pricing | Split volumes, higher complexity |
| **Multi-Source** | Maximum flexibility, risk spread | Highest complexity, diluted volumes |
| **Hybrid** | Primary (70%) + backup (30%) | Balanced risk-cost trade-off |

### 5.2 Make-vs-Buy Framework

```
Total Cost of Internal Production:
  Variable cost + Fixed cost + Capital cost + Opportunity cost

Total Cost of External Sourcing:
  Purchase price + Logistics + Quality + Transaction + Risk premium

Decision: Internal if TC_make < TC_buy AND capacity available AND strategic fit
```

**Strategic Considerations**:
| Factor | Favor Make | Favor Buy |
|--------|-----------|-----------|
| **Core competency** | Yes | No |
| **Volume** | High, stable | Low, variable |
| **Quality control** | Critical | Acceptable |
| **IP protection** | Essential | Not sensitive |
| **Capacity** | Available | Unavailable |
| **Speed to market** | Established | Faster externally |
| **Capital availability** | Available | Constrained |

---

## 6. Transportation Network Design

### 6.1 Hub-and-Spoke vs Direct

```
Direct Network:
  Each origin ships directly to each destination
  Routes: O × D (many lanes)
  Cost: Low per-shipment, but many partial loads

Hub-and-Spoke:
  Origins ship to hub → Hub sorts → Hub ships to destinations
  Routes: O + D (fewer lanes)
  Cost: Higher handling, but full truck consolidation
```

**Break-even**: Hub-and-spoke wins when volumes per lane are too small for full trucks.

### 6.2 Zone Skipping

For parcel/LTL networks:
```
Standard: Ship to local hub → Zone 1 hub → Zone 2 hub → Destination hub → Delivery
Zone Skip: Consolidate → Skip directly to Zone 2 hub → Delivery

Saves: Per-package zone charges
Cost: Requires volume and consolidation time
```

### 6.3 Pool Distribution

```
Full truck from plant → Pool point (near market)
    ↓ Break-bulk and local delivery
Multiple customers in market area

Combines TL economics with local LTL delivery
```

---

## 7. Risk and Resilience in Network Design

### 7.1 Supply Chain Risk Types

| Risk Type | Examples | Mitigation |
|-----------|---------|------------|
| **Demand risk** | Demand volatility, forecast error | Safety stock, flexible capacity |
| **Supply risk** | Supplier failure, quality issues | Dual sourcing, qualification |
| **Operational risk** | Equipment failure, labor shortage | Maintenance, cross-training |
| **Environmental risk** | Natural disasters, pandemics | Geographic diversification |
| **Geopolitical risk** | Tariffs, trade wars, sanctions | Nearshoring, multi-country |
| **Cyber risk** | System outage, ransomware | Redundancy, backup systems |
| **Transportation risk** | Port congestion, carrier failure | Multi-mode, buffer inventory |

### 7.2 Resilience Strategies

| Strategy | Description | Cost |
|----------|-------------|------|
| **Redundancy** | Backup capacity, dual sourcing | Medium-High |
| **Flexibility** | Multi-purpose facilities, flexible labor | Medium |
| **Visibility** | Real-time tracking, control tower | Medium |
| **Agility** | Fast response, postponement | Medium |
| **Inventory buffers** | Strategic pre-positioning | High (carrying cost) |
| **Nearshoring** | Regional manufacturing | High (restructuring) |
| **Digital twin** | Simulation-based risk assessment | Medium |

### 7.3 Risk-Adjusted Network Design

Incorporate risk into optimization:
```
Standard: Minimize E[Total Cost]
Risk-adjusted: Minimize E[Total Cost] + λ × CVaR[Total Cost]

Where:
  CVaR = Conditional Value at Risk (expected cost in worst α% of scenarios)
  λ = risk aversion parameter (higher = more conservative)
```

---

## 8. Network Design Software

| Platform | Key Capability | Strength |
|----------|---------------|----------|
| **Coupa (Llamasoft)** | Supply Chain Guru | Most widely used, comprehensive |
| **AIMMS SC Navigator** | Mathematical optimization | Strong solver, flexible modeling |
| **o9 Solutions** | AI-driven design | Knowledge graph, rapid scenarios |
| **Kinaxis** | Concurrent design | Integrated with tactical planning |
| **Optilogic** | Cloud-native | Modern UI, fast scenario analysis |
| **anyLogistix (anyLogic)** | Simulation + optimization | Combines network design with simulation |
| **SAP IBP** | Integrated planning | Embedded in SAP ecosystem |
| **Oracle SCM** | Supply Chain Design | Oracle cloud integration |

---

## 9. Network Design Process

### Phase 1: Data Collection (2-4 weeks)
- Demand data by customer location, product, time
- Supply data (supplier locations, capacities, costs)
- Current network costs (facility, transport, inventory)
- Service requirements by customer/channel
- Constraints (labor, regulations, leases)

### Phase 2: Baseline Model (2-3 weeks)
- Build current-state model in network design tool
- Validate against actual costs (within 5% tolerance)
- Establish baseline metrics

### Phase 3: Analysis (3-6 weeks)
- Greenfield analysis (unconstrained optimal)
- Brownfield scenarios (incremental changes)
- Sensitivity analysis (demand growth, cost changes)
- Risk scenarios (disruption, policy changes)

### Phase 4: Recommendations (2-3 weeks)
- Quantify benefits of top scenarios
- Assess implementation feasibility and timeline
- Capital requirements and ROI analysis
- Risk assessment of recommended changes

### Phase 5: Implementation Planning (2-4 weeks)
- Detailed transition plan
- Site selection and lease negotiation
- Workforce planning
- System and process changes
- Phased rollout schedule

---

## 10. Key Formulas

| Formula | Expression | Use |
|---------|-----------|-----|
| **Center of Gravity** | X* = Σ(wᵢxᵢ)/Σwᵢ | Initial facility location |
| **Square Root Law** | SS_n = SS_1 × √n | Inventory impact of # DCs |
| **Total Landed Cost** | Product + Transport + Duties + Handling + Inventory | Sourcing comparison |
| **Weighted Distance** | Σ(dᵢⱼ × wᵢ) | Service coverage metric |
| **Utilization** | Throughput / Capacity | Facility sizing |
| **ROI** | (Annual savings − Annual cost) / Investment | Investment justification |

---

*Sources: Simchi-Levi et al. "Designing and Managing the Supply Chain", Chopra & Meindl "Supply Chain Management: Strategy, Planning, and Operation", Ballou "Business Logistics/Supply Chain Management", Watson et al. "Supply Chain Network Design", ASCM CSCP Learning System*

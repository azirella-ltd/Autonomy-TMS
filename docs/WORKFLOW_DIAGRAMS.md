# Workflow Diagrams for Functional Areas

This document provides detailed workflow diagrams for all 21 functional areas in the Autonomy Platform. Each diagram shows the step-by-step process, user roles involved, decision points, and system interactions.

**Legend:**
- 🟦 **User Action**: Action performed by a user
- 🟨 **System Process**: Automated system processing
- 🟩 **Decision Point**: User approval or choice required
- 🟥 **Multi-User Interaction**: Requires coordination between multiple users
- ⚡ **AI Agent**: AI-powered automation available

---

## Table of Contents

### Strategic Planning
1. [Network Design](#1-network-design)
2. [Demand Forecasting](#2-demand-forecasting)
3. [Inventory Optimization](#3-inventory-optimization)
4. [Stochastic Planning](#4-stochastic-planning)

### Tactical Planning
5. [Master Production Scheduling (MPS)](#5-master-production-scheduling-mps)
6. [Lot Sizing Analysis](#6-lot-sizing-analysis)
7. [Capacity Check](#7-capacity-check)
8. [Material Requirements Planning (MRP)](#8-material-requirements-planning-mrp)

### Operational Planning
9. [Supply Plan Generation](#9-supply-plan-generation)
10. [Available-to-Promise / Capable-to-Promise (ATP/CTP)](#10-available-to-promise--capable-to-promise-atpctp)
11. [Sourcing & Allocation](#11-sourcing--allocation)
12. [Order Planning](#12-order-planning)

### Execution & Monitoring
13. [Order Management](#13-order-management)
14. [Shipment Tracking](#14-shipment-tracking)
15. [Inventory Visibility](#15-inventory-visibility)
16. [N-Tier Visibility](#16-n-tier-visibility)

### Analytics & Insights
17. [Supply Chain Analytics](#17-supply-chain-analytics)
18. [KPI Monitoring](#18-kpi-monitoring)
19. [Scenario Comparison](#19-scenario-comparison)
20. [Risk Analysis](#20-risk-analysis)

### AI & Multi-Agent Orchestration (Phase 4)
22. [AI Multi-Agent Decision-Making](#22-ai-multi-agent-decision-making-phase-4)
23. [Agent Mode Switching](#23-agent-mode-switching)
24. [A/B Testing for Learning Algorithms](#24-ab-testing-for-learning-algorithms)

### Other
21. [Group Admin User Management](#21-group-admin-user-management)

---

## 1. Network Design

**Purpose**: Design and configure supply chain network topology with nodes, lanes, and products.

**Primary Users**: Supply Chain Architect, Network Planner

**Multi-User**: Yes - Requires approval from SC Director

```mermaid
graph TD
    A[🟦 START: Open Network Design] --> B[🟦 Select/Create Configuration]
    B --> C[🟦 Add Nodes Sites]
    C --> D{More Nodes?}
    D -->|Yes| C
    D -->|No| E[🟦 Define Products/Items]
    E --> F[🟦 Create Lanes Material Flow]
    F --> G[🟦 Configure BOMs for Manufacturers]
    G --> H[🟨 System: Validate DAG Topology]
    H --> I{Valid Network?}
    I -->|No - Cycles Detected| J[🟥 Display Errors]
    J --> C
    I -->|Yes| K[🟦 Visualize Network Sankey Diagram]
    K --> L[🟦 Preview Simulation Parameters]
    L --> M[🟩 APPROVAL: Submit for Review]
    M --> N{SC Director Approval}
    N -->|Rejected| O[🟥 Review Comments]
    O --> C
    N -->|Approved| P[🟨 System: Activate Network]
    P --> Q[🟨 System: Initialize Inventory Levels]
    Q --> R[✅ END: Network Active]

    style M fill:#90EE90
    style N fill:#90EE90
    style O fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Network Architect** → Designs topology
2. **Data Analyst** → Validates historical data alignment
3. **SC Director** → Approves network for production use

---

## 2. Demand Forecasting

**Purpose**: Generate statistical and ML-based demand forecasts with confidence intervals.

**Primary Users**: Demand Planner, Data Scientist

**Multi-User**: Yes - Collaboration with Sales for consensus planning

```mermaid
graph TD
    A[🟦 START: Open Demand Forecasting] --> B[🟦 Select Product-Location]
    B --> C[🟦 Choose Forecast Method]
    C --> D{Method Type?}
    D -->|Statistical| E[🟦 Configure ARIMA/ETS]
    D -->|ML| F[🟦 Configure TRM/GNN Model]
    D -->|Consensus| G[🟥 Invite Sales Team]

    E --> H[🟨 System: Generate Base Forecast]
    F --> H
    G --> I[🟥 Sales: Provide Market Intelligence]
    I --> H

    H --> J[🟦 View Forecast with P10/P50/P90]
    J --> K{Adjust Forecast?}
    K -->|Yes| L[🟦 Manual Adjustments]
    L --> H
    K -->|No| M[🟩 Submit for Consensus]

    M --> N{Sales Approval?}
    N -->|Override| O[🟥 Sales: Adjust Forecast]
    O --> H
    N -->|Approve| P[🟨 System: Finalize Forecast]

    P --> Q[🟨 System: Feed to Supply Planning]
    Q --> R[✅ END: Forecast Active]

    style G fill:#FF6B6B
    style I fill:#FF6B6B
    style M fill:#90EE90
    style N fill:#90EE90
    style O fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Demand Planner** → Generates statistical forecast
2. **Sales Team** → Provides market intelligence and overrides
3. **Supply Planner** → Consumes forecast for supply planning

---

## 3. Inventory Optimization

**Purpose**: Calculate optimal safety stock and reorder points using 4 policy types.

**Primary Users**: Inventory Analyst, Supply Planner

**Multi-User**: No - Individual planner workflow

```mermaid
graph TD
    A[🟦 START: Open Inventory Optimization] --> B[🟦 Select Scope]
    B --> C{Scope Level?}
    C -->|Config-Wide| D[🟦 Set Global Policy]
    C -->|By Node| E[🟦 Set Node-Level Policy]
    C -->|By Item| F[🟦 Set Item-Level Policy]
    C -->|Item-Node Specific| G[🟦 Set Item-Node Policy]

    D --> H[🟦 Choose Policy Type]
    E --> H
    F --> H
    G --> H

    H --> I{Policy Type?}
    I -->|abs_level| J[🟦 Set Fixed Quantity]
    I -->|doc_dem| K[🟦 Set Days of Demand]
    I -->|doc_fcst| L[🟦 Set Days of Forecast]
    I -->|sl| M[🟦 Set Service Level %]

    J --> N[🟨 System: Calculate Safety Stock]
    K --> N
    L --> N
    M --> N

    N --> O[🟦 View Hierarchical Overrides]
    O --> P[🟨 System: Apply Most Specific Policy]
    P --> Q[🟦 Preview Impact on Inventory Levels]
    Q --> R{Satisfactory?}
    R -->|No| H
    R -->|Yes| S[🟦 Save Policy]
    S --> T[🟨 System: Update Inv Targets]
    T --> U[✅ END: Policy Active]
```

**Hierarchical Override Logic**:
```
Item-Node (most specific)
  ↓
Item
  ↓
Node
  ↓
Config (least specific/default)
```

---

## 4. Stochastic Planning

**Purpose**: Run Monte Carlo simulations with probabilistic inputs for risk-aware planning.

**Primary Users**: Risk Analyst, Strategic Planner

**Multi-User**: No - Individual analyst workflow

```mermaid
graph TD
    A[🟦 START: Open Stochastic Planning] --> B[🟦 Select Scenario]
    B --> C[🟦 Define Operational Variables]
    C --> D[🟦 Assign Distributions]
    D --> E{Distribution Type?}
    E -->|Normal| F[🟦 Set μ, σ]
    E -->|LogNormal| G[🟦 Set μ, σ]
    E -->|Beta| H[🟦 Set α, β]
    E -->|Triangular| I[🟦 Set min, mode, max]
    E -->|Empirical| J[🟦 Upload Historical Data]

    F --> K[🟦 Configure Monte Carlo]
    G --> K
    H --> K
    I --> K
    J --> K

    K --> L[🟦 Set # Scenarios 1000+]
    L --> M[🟨 System: Run Simulation]
    M --> N[⚡ AI: Variance Reduction]
    N --> O[🟨 System: Generate Balanced Scorecard]
    O --> P[🟦 View Probabilistic KPIs]
    P --> Q[🟦 Analyze Distribution Curves]
    Q --> R{Acceptable Risk?}
    R -->|No| S[🟦 Adjust Parameters]
    S --> C
    R -->|Yes| T[🟦 Export Results]
    T --> U[✅ END: Stochastic Analysis Complete]

    style N fill:#FFD700
```

**Probabilistic Balanced Scorecard**:
- **Financial**: E[Total Cost], P(Cost < Budget), P10/P50/P90
- **Customer**: E[OTIF], P(OTIF > 95%), Fill Rate Distribution
- **Operational**: E[Inventory Turns], E[DOS], Bullwhip Ratio
- **Strategic**: Flexibility Scores, CO2 Emissions Distribution

---

## 5. Master Production Scheduling (MPS)

**Purpose**: Create strategic production plans with rough-cut capacity checks.

**Primary Users**: Master Scheduler, Production Planner

**Multi-User**: Yes - Collaboration with capacity planner and approval from operations manager

```mermaid
graph TD
    A[🟦 START: Open MPS] --> B[🟦 Select Planning Horizon 52 weeks]
    B --> C[🟦 Load Demand Forecast]
    C --> D[🟨 System: Calculate Gross Requirements]
    D --> E[🟨 System: Net Against On-Hand]
    E --> F[🟦 View Time-Phased MPS Grid]
    F --> G[🟦 Adjust Production Quantities]
    G --> H[🟨 System: Calculate Capacity Load]
    H --> I{Capacity OK?}
    I -->|Overloaded| J[🟥 Alert: Capacity Exceeded]
    J --> K[🟥 Capacity Planner: Review]
    K --> L{Can Increase Capacity?}
    L -->|Yes| M[🟥 Capacity Planner: Adjust Resources]
    M --> H
    L -->|No| N[🟦 Adjust MPS Down]
    N --> G

    I -->|Within Capacity| O[🟦 Review Cost Trade-offs]
    O --> P[🟨 System: Calculate Total Cost]
    P --> Q{Acceptable?}
    Q -->|No| G
    Q -->|Yes| R[🟩 APPROVAL: Submit MPS]
    R --> S{Operations Manager Approval}
    S -->|Rejected| T[🟥 Review Comments]
    T --> G
    S -->|Approved| U[🟨 System: Release MPS]
    U --> V[🟨 System: Trigger MRP]
    V --> W[✅ END: MPS Active]

    style J fill:#FF6B6B
    style K fill:#FF6B6B
    style M fill:#FF6B6B
    style R fill:#90EE90
    style S fill:#90EE90
    style T fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Master Scheduler** → Creates MPS plan
2. **Capacity Planner** → Validates capacity constraints
3. **Operations Manager** → Approves for execution

---

## 6. Lot Sizing Analysis

**Purpose**: Analyze EOQ, POQ, and LFL lot sizing methods with cost trade-offs.

**Primary Users**: Inventory Analyst, Purchasing Manager

**Multi-User**: No - Individual analyst workflow

```mermaid
graph TD
    A[🟦 START: Open Lot Sizing Analysis] --> B[🟦 Select Product-Location]
    B --> C[🟦 Input Cost Parameters]
    C --> D[🟦 Set Holding Cost $/unit/year]
    D --> E[🟦 Set Ordering Cost $/order]
    E --> F[🟨 System: Calculate EOQ]
    F --> G[🟨 System: Calculate POQ]
    G --> H[🟨 System: Simulate LFL]
    H --> I[🟦 View Cost Comparison Chart]
    I --> J[🟦 Compare Total Costs]
    J --> K[🟦 Compare Avg Inventory]
    K --> L[🟦 Compare Order Frequency]
    L --> M{Best Method?}
    M -->|EOQ| N[🟦 Set Fixed Order Quantity]
    M -->|POQ| O[🟦 Set Order Period]
    M -->|LFL| P[🟦 Set Lot-for-Lot]

    N --> Q[🟨 System: Apply to Item]
    O --> Q
    P --> Q
    Q --> R[✅ END: Lot Sizing Policy Set]
```

**Cost Trade-off Analysis**:
- **EOQ**: Balances ordering cost vs holding cost
- **POQ**: Fixed period ordering
- **LFL**: Minimal inventory but high ordering frequency

---

## 7. Capacity Check

**Purpose**: Validate resource capacity against production requirements.

**Primary Users**: Capacity Planner, Operations Manager

**Multi-User**: Yes - Requires operations manager approval for capacity expansion

```mermaid
graph TD
    A[🟦 START: Open Capacity Check] --> B[🟦 Select Time Horizon]
    B --> C[🟨 System: Load MPS Requirements]
    C --> D[🟨 System: Calculate Resource Load]
    D --> E[🟦 View Capacity Utilization Gauges]
    E --> F{Any Bottlenecks?}
    F -->|Yes| G[🟥 Alert: Bottleneck Detected]
    G --> H[🟦 Identify Critical Resources]
    H --> I{Resolution Strategy?}
    I -->|Add Capacity| J[🟩 APPROVAL: Request Expansion]
    J --> K{Operations Manager Approval}
    K -->|Rejected| L[🟥 Review Alternatives]
    L --> I
    K -->|Approved| M[🟨 System: Update Capacity]
    M --> D

    I -->|Shift Load| N[🟦 Adjust MPS Schedule]
    N --> D
    I -->|Outsource| O[🟦 Create External Sourcing]
    O --> D

    F -->|No| P[🟦 Review Utilization Metrics]
    P --> Q[🟨 System: Generate Capacity Report]
    Q --> R[✅ END: Capacity Validated]

    style G fill:#FF6B6B
    style J fill:#90EE90
    style K fill:#90EE90
    style L fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Capacity Planner** → Analyzes utilization
2. **Operations Manager** → Approves capacity expansion requests
3. **Finance** → Validates capex budget for new resources

---

## 8. Material Requirements Planning (MRP)

**Purpose**: Explode BOM and calculate time-phased component requirements.

**Primary Users**: Material Planner, Buyer

**Multi-User**: No - Individual planner workflow with AI agent support

```mermaid
graph TD
    A[🟦 START: Open MRP] --> B[🟨 System: Load MPS]
    B --> C[🟨 System: Multi-Level BOM Explosion]
    C --> D[🟨 System: Calculate Gross Requirements]
    D --> E[🟨 System: Net Against On-Hand]
    E --> F[🟨 System: Lead Time Offsetting]
    F --> G[🟦 View MRP Tree]
    G --> H[🟦 Review Planned Orders]
    H --> I{Exceptions Detected?}
    I -->|Yes| J[🟥 Review Exceptions]
    J --> K{Exception Type?}
    K -->|Shortage| L[🟦 Expedite Orders]
    K -->|Excess| M[🟦 Reschedule/Cancel]
    K -->|Past Due| N[🟦 Re-plan]

    L --> O[🟦 Update Order Dates]
    M --> O
    N --> O
    O --> H

    I -->|No| P[⚡ AI: Validate with ML Agent]
    P --> Q{AI Recommendations?}
    Q -->|Yes| R[🟦 Review AI Suggestions]
    R --> S{Accept AI Changes?}
    S -->|Yes| T[🟨 System: Apply AI Orders]
    S -->|No| U[🟦 Manual Override]
    U --> H

    Q -->|No| V[🟦 Generate Purchase Requisitions]
    T --> V
    V --> W[🟨 System: Create POs/TOs/MOs]
    W --> X[✅ END: MRP Complete]

    style P fill:#FFD700
    style Q fill:#FFD700
    style R fill:#FFD700
```

**AI Agent Support**:
- TRM Agent can validate MRP orders and suggest optimizations
- Reduces manual exception handling by 30-40%

---

## 9. Supply Plan Generation

**Purpose**: Generate comprehensive supply plan with PO/TO/MO recommendations.

**Primary Users**: Supply Planner, Procurement Manager

**Multi-User**: Yes - Requires procurement manager approval before release

```mermaid
graph TD
    A[🟦 START: Generate Supply Plan] --> B[🟦 Set Planning Horizon]
    B --> C[🟦 Select Stochastic Parameters]
    C --> D[🟨 System: Run 3-Step Planning]
    D --> E[🟨 Step 1: Demand Processing]
    E --> F[🟨 Step 2: Inventory Target Calc]
    F --> G[🟨 Step 3: Net Requirements]
    G --> H[🟨 System: Apply Sourcing Rules]
    H --> I[🟨 System: Generate Supply Plan]
    I --> J[🟦 View Probabilistic Scorecard]
    J --> K[🟦 Review Financial Metrics]
    K --> L[🟦 Review Customer Metrics]
    L --> M[🟦 Review Operational Metrics]
    M --> N{Acceptable KPIs?}
    N -->|No| O[🟦 Adjust Parameters]
    O --> C
    N -->|Yes| P[🟦 Review Orders List]
    P --> Q[🟦 View PO/TO/MO Details]
    Q --> R[🟩 APPROVAL: Submit for Review]
    R --> S{Procurement Manager Approval}
    S -->|Rejected| T[🟥 Review Comments]
    T --> O
    S -->|Approved| U[🟨 System: Release Orders]
    U --> V[🟨 System: Notify Suppliers]
    V --> W[✅ END: Supply Plan Active]

    style R fill:#90EE90
    style S fill:#90EE90
    style T fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Supply Planner** → Generates plan
2. **Procurement Manager** → Approves order release
3. **Suppliers** → Receive PO notifications

---

## 10. Available-to-Promise / Capable-to-Promise (ATP/CTP)

**Purpose**: Real-time inventory availability and production capability checks for sales orders.

**Primary Users**: Order Fulfillment Specialist, Sales Rep

**Multi-User**: No - Real-time query workflow

```mermaid
graph TD
    A[🟦 START: Customer Order Inquiry] --> B[🟦 Input Order Details]
    B --> C[🟦 Specify Product, Quantity, Date]
    C --> D[🟨 System: Check On-Hand Inventory]
    D --> E{Inventory Available?}
    E -->|Yes| F[🟨 System: Calculate ATP]
    F --> G[🟦 View Available Qty & Date]
    G --> H[🟦 Confirm Order]
    H --> I[🟨 System: Reserve Inventory]
    I --> J[✅ END: Order Confirmed]

    E -->|No| K[🟨 System: Run CTP Check]
    K --> L[🟨 System: Check Production Capacity]
    L --> M[🟨 System: Check Material Availability]
    M --> N{Can Produce?}
    N -->|Yes| O[🟦 View CTP Date & Qty]
    O --> P[🟦 Communicate Lead Time]
    P --> Q{Customer Accepts?}
    Q -->|Yes| R[🟨 System: Create Production Order]
    R --> J
    Q -->|No| S[✅ END: Order Declined]

    N -->|No| T[🟦 Suggest Alternative Products]
    T --> U{Alternative Accepted?}
    U -->|Yes| C
    U -->|No| S
```

**Real-Time Checks**:
1. **ATP**: On-hand + scheduled receipts - allocated
2. **CTP**: Production capacity + material availability

---

## 11. Sourcing & Allocation

**Purpose**: Configure multi-sourcing rules with priorities and allocate inventory across demand.

**Primary Users**: Sourcing Manager, Supply Planner

**Multi-User**: No - Configuration workflow

```mermaid
graph TD
    A[🟦 START: Configure Sourcing] --> B[🟦 Select Product-Location]
    B --> C[🟦 Define Sourcing Rules]
    C --> D{Source Type?}
    D -->|Buy| E[🟦 Add Vendor with Priority]
    D -->|Transfer| F[🟦 Add Source Location]
    D -->|Manufacture| G[🟦 Add Production Site]

    E --> H[🟦 Set Lead Time]
    F --> H
    G --> H

    H --> I[🟦 Set MOQ/Batch Size]
    I --> J[🟦 Assign Priority 1-N]
    J --> K{Add More Sources?}
    K -->|Yes| D
    K -->|No| L[🟨 System: Validate Rules]
    L --> M[🟦 Test Allocation Logic]
    M --> N[🟦 View Example Allocation]
    N --> O{Correct Behavior?}
    O -->|No| C
    O -->|Yes| P[🟦 Save Sourcing Rules]
    P --> Q[🟨 System: Apply to Planning]
    Q --> R[✅ END: Sourcing Configured]
```

**Multi-Sourcing Logic**:
1. Sort sources by priority (1 = highest)
2. Allocate to highest priority until capacity exhausted
3. Overflow to next priority level

---

## 12. Order Planning

**Purpose**: Plan and track purchase orders, transfer orders, and manufacturing orders.

**Primary Users**: Buyer, Material Planner

**Multi-User**: No - Individual planner workflow

```mermaid
graph TD
    A[🟦 START: Open Order Planning] --> B[🟦 Select Order Type]
    B --> C{Order Type?}
    C -->|Purchase Order| D[🟦 Create PO]
    C -->|Transfer Order| E[🟦 Create TO]
    C -->|Manufacturing Order| F[🟦 Create MO]

    D --> G[🟦 Select Vendor]
    E --> H[🟦 Select Source Location]
    F --> I[🟦 Select Production Site]

    G --> J[🟦 Specify Product & Qty]
    H --> J
    I --> J

    J --> K[🟦 Set Requested Date]
    K --> L[🟨 System: Calculate Lead Time]
    L --> M[🟨 System: Determine Due Date]
    M --> N[🟦 Review Order Details]
    N --> O{Correct?}
    O -->|No| J
    O -->|Yes| P[🟦 Submit Order]
    P --> Q[🟨 System: Send to Supplier/Factory]
    Q --> R[🟨 System: Track Status]
    R --> S[✅ END: Order In Progress]
```

---

## 13. Order Management

**Purpose**: Manage lifecycle of purchase and transfer orders from creation to receipt.

**Primary Users**: Buyer, Receiving Clerk

**Multi-User**: Yes - Requires buyer and receiving clerk collaboration

```mermaid
graph TD
    A[🟦 START: View Orders] --> B[🟦 Filter by Status]
    B --> C{Order Status?}
    C -->|Planned| D[🟦 Review Planned Orders]
    C -->|Released| E[🟦 Track In-Transit]
    C -->|Received| F[🟦 View Receipts]

    D --> G[🟦 Select Order to Release]
    G --> H[🟩 APPROVAL: Release Order]
    H --> I{Manager Approval?}
    I -->|Rejected| J[🟥 Review Comments]
    J --> G
    I -->|Approved| K[🟨 System: Release to Supplier]
    K --> E

    E --> L[🟦 Monitor Shipment Status]
    L --> M{Shipment Arrived?}
    M -->|No| N[🟦 Check ETA]
    N --> L
    M -->|Yes| O[🟥 Receiving Clerk: Inspect Goods]
    O --> P{Quality OK?}
    P -->|No| Q[🟥 Receiving: Create Rejection]
    Q --> R[🟨 System: Notify Supplier]
    R --> S[🟦 Buyer: Handle Return]
    S --> L

    P -->|Yes| T[🟥 Receiving: Confirm Receipt]
    T --> U[🟨 System: Update Inventory]
    U --> V[🟨 System: Close Order]
    V --> W[✅ END: Order Complete]

    style H fill:#90EE90
    style I fill:#90EE90
    style J fill:#FF6B6B
    style O fill:#FF6B6B
    style T fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Buyer** → Releases orders and handles exceptions
2. **Receiving Clerk** → Inspects goods and confirms receipt
3. **Manager** → Approves order release

---

## 14. Shipment Tracking

**Purpose**: Track inbound and outbound shipments with real-time status updates.

**Primary Users**: Logistics Coordinator, Customer Service Rep

**Multi-User**: No - Individual tracking workflow

```mermaid
graph TD
    A[🟦 START: View Shipments] --> B[🟦 Select Direction]
    B --> C{Direction?}
    C -->|Inbound| D[🟦 View Incoming Shipments]
    C -->|Outbound| E[🟦 View Outgoing Shipments]

    D --> F[🟦 Select Shipment]
    E --> F

    F --> G[🟦 View Shipment Details]
    G --> H[🟦 View Tracking Events]
    H --> I[🟨 System: Show Timeline]
    I --> J[🟦 View Current Location]
    J --> K[🟨 System: Calculate ETA]
    K --> L{Delayed?}
    L -->|Yes| M[🟥 Alert: Shipment Delayed]
    M --> N[🟦 Notify Customer]
    N --> O[🟦 Adjust Downstream Plans]
    O --> P[✅ END: Tracking Updated]

    L -->|No| Q{Delivered?}
    Q -->|No| R[🟦 Monitor Progress]
    R --> H
    Q -->|Yes| S[🟨 System: Update Inventory]
    S --> P

    style M fill:#FF6B6B
```

---

## 15. Inventory Visibility

**Purpose**: View real-time inventory levels across all nodes in the supply chain.

**Primary Users**: Inventory Controller, Supply Planner

**Multi-User**: No - Read-only visibility workflow

```mermaid
graph TD
    A[🟦 START: Open Inventory Visibility] --> B[🟦 Select View Type]
    B --> C{View Type?}
    C -->|By Location| D[🟦 View Node Inventory]
    C -->|By Product| E[🟦 View Item Inventory]
    C -->|Network-Wide| F[🟦 View Total Inventory]

    D --> G[🟨 System: Load Inventory Levels]
    E --> G
    F --> G

    G --> H[🟦 View On-Hand Quantities]
    H --> I[🟦 View In-Transit Quantities]
    I --> J[🟦 View Allocated Quantities]
    J --> K[🟨 System: Calculate Available]
    K --> L[🟦 View Days of Supply]
    L --> M{Alert Conditions?}
    M -->|Low Stock| N[🟥 Alert: Below Safety Stock]
    M -->|Excess Stock| O[🟥 Alert: Excess Inventory]
    M -->|Normal| P[🟦 Review Metrics]

    N --> Q[🟦 Trigger Replenishment]
    O --> R[🟦 Consider Redistribution]
    P --> S[✅ END: Inventory Reviewed]
    Q --> S
    R --> S

    style N fill:#FF6B6B
    style O fill:#FF6B6B
```

---

## 16. N-Tier Visibility

**Purpose**: View multi-tier supply chain visibility including suppliers' suppliers.

**Primary Users**: Supply Chain Risk Manager, Procurement Manager

**Multi-User**: No - Visibility and monitoring workflow

```mermaid
graph TD
    A[🟦 START: Open N-Tier Visibility] --> B[🟦 Select Product]
    B --> C[🟨 System: Build Supply Network Tree]
    C --> D[🟦 View Tier 1 Suppliers]
    D --> E[🟦 Expand to Tier 2]
    E --> F[🟦 Expand to Tier 3+]
    F --> G[🟦 View Supplier Status]
    G --> H{Risk Detected?}
    H -->|Yes| I[🟥 Alert: Supplier Risk]
    I --> J{Risk Type?}
    J -->|Financial| K[🟦 Review Credit Score]
    J -->|Capacity| L[🟦 Review Utilization]
    J -->|Geographic| M[🟦 Review Location Risk]

    K --> N[🟦 Identify Alternative Suppliers]
    L --> N
    M --> N

    N --> O[🟦 Develop Mitigation Plan]
    O --> P[✅ END: Risk Mitigated]

    H -->|No| Q[🟦 Monitor Supplier Health]
    Q --> R[🟨 System: Track KPIs]
    R --> P

    style I fill:#FF6B6B
```

---

## 17. Supply Chain Analytics

**Purpose**: Comprehensive analytics dashboard for SC KPIs and performance metrics.

**Primary Users**: SC Analyst, SC Director

**Multi-User**: No - Read-only analytics workflow

```mermaid
graph TD
    A[🟦 START: Open SC Analytics] --> B[🟦 Select Dashboard]
    B --> C{Dashboard Type?}
    C -->|Financial| D[🟦 View Cost Metrics]
    C -->|Customer| E[🟦 View Service Metrics]
    C -->|Operational| F[🟦 View Efficiency Metrics]
    C -->|Strategic| G[🟦 View Long-Term Metrics]

    D --> H[🟨 System: Load Financial KPIs]
    E --> I[🟨 System: Load Service KPIs]
    F --> J[🟨 System: Load Operational KPIs]
    G --> K[🟨 System: Load Strategic KPIs]

    H --> L[🟦 Apply Filters]
    I --> L
    J --> L
    K --> L

    L --> M[🟦 Set Date Range]
    M --> N[🟦 Set Comparison Period]
    N --> O[🟨 System: Calculate Trends]
    O --> P[🟦 View Charts & Graphs]
    P --> Q[🟦 Export Report]
    Q --> R[✅ END: Analytics Reviewed]
```

**Key KPIs**:
- **Financial**: Total Cost, Cost per Unit, Inventory Carrying Cost
- **Customer**: OTIF %, Fill Rate %, Perfect Order %
- **Operational**: Inventory Turns, DOS, Lead Time
- **Strategic**: Carbon Footprint, Supplier Diversity, Resilience Score

---

## 18. KPI Monitoring

**Purpose**: Real-time KPI monitoring with alerts and threshold-based notifications.

**Primary Users**: Operations Manager, SC Director

**Multi-User**: No - Monitoring workflow

```mermaid
graph TD
    A[🟦 START: Open KPI Monitoring] --> B[🟦 View KPI Dashboard]
    B --> C[🟨 System: Refresh Real-Time Data]
    C --> D[🟦 View Current KPIs]
    D --> E{Threshold Breached?}
    E -->|Yes| F[🟥 Alert: KPI Out of Range]
    F --> G{Alert Type?}
    G -->|Critical| H[🟨 System: Send SMS/Email]
    G -->|Warning| I[🟨 System: Dashboard Notification]

    H --> J[🟦 Investigate Root Cause]
    I --> J

    J --> K[🟦 Drill Down to Details]
    K --> L[🟦 Identify Issue]
    L --> M[🟦 Take Corrective Action]
    M --> N[🟨 System: Update KPI]
    N --> C

    E -->|No| O[🟦 Review Trends]
    O --> P[🟦 Identify Improvements]
    P --> Q[✅ END: KPIs Healthy]

    style F fill:#FF6B6B
```

**Alert Thresholds**:
- **Critical**: Requires immediate action (service level < 85%)
- **Warning**: Attention needed (service level 85-95%)
- **Normal**: No action required (service level > 95%)

---

## 19. Scenario Comparison

**Purpose**: Compare multiple planning scenarios side-by-side to evaluate alternatives.

**Primary Users**: Strategic Planner, SC Director

**Multi-User**: Yes - Requires director approval for scenario selection

```mermaid
graph TD
    A[🟦 START: Create Scenarios] --> B[🟦 Define Baseline Scenario]
    B --> C[🟦 Create Alternative Scenario 1]
    C --> D[🟦 Modify Parameters]
    D --> E[🟦 Create Alternative Scenario 2]
    E --> F[🟦 Modify Different Parameters]
    F --> G[🟨 System: Run All Scenarios]
    G --> H[🟨 System: Generate Results]
    H --> I[🟦 View Side-by-Side Comparison]
    I --> J[🟦 Compare Financial Impact]
    J --> K[🟦 Compare Service Levels]
    K --> L[🟦 Compare Operational Metrics]
    L --> M[🟦 Identify Trade-offs]
    M --> N{Best Scenario?}
    N -->|Unclear| O[🟦 Create Hybrid Scenario]
    O --> D
    N -->|Clear Winner| P[🟩 APPROVAL: Recommend Scenario]
    P --> Q{Director Approval?}
    Q -->|Rejected| R[🟥 Review Alternatives]
    R --> N
    Q -->|Approved| S[🟨 System: Implement Scenario]
    S --> T[✅ END: Scenario Active]

    style P fill:#90EE90
    style Q fill:#90EE90
    style R fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Strategic Planner** → Designs and analyzes scenarios
2. **SC Director** → Selects winning scenario for implementation

---

## 20. Risk Analysis

**Purpose**: Identify and quantify supply chain risks with mitigation strategies.

**Primary Users**: Risk Manager, SC Director

**Multi-User**: Yes - Cross-functional risk assessment team

```mermaid
graph TD
    A[🟦 START: Risk Assessment] --> B[🟦 Identify Risk Categories]
    B --> C{Risk Category?}
    C -->|Supplier| D[🟦 Assess Supplier Risks]
    C -->|Demand| E[🟦 Assess Demand Volatility]
    C -->|Operational| F[🟦 Assess Process Risks]
    C -->|External| G[🟦 Assess External Risks]

    D --> H[🟨 System: Calculate Risk Score]
    E --> H
    F --> H
    G --> H

    H --> I[🟦 View Risk Heat Map]
    I --> J[🟦 Prioritize High-Risk Areas]
    J --> K{Risk Level?}
    K -->|High| L[🟥 Alert: High Risk Detected]
    K -->|Medium| M[🟨 Warning: Medium Risk]
    K -->|Low| N[🟩 Monitor: Low Risk]

    L --> O[🟥 Cross-Functional Team: Develop Mitigation]
    M --> O

    O --> P[🟦 Define Mitigation Strategy]
    P --> Q{Strategy Type?}
    Q -->|Diversify| R[🟦 Add Alternative Suppliers]
    Q -->|Buffer| S[🟦 Increase Safety Stock]
    Q -->|Dual-Source| T[🟦 Add Backup Source]

    R --> U[🟨 System: Implement Strategy]
    S --> U
    T --> U

    U --> V[🟨 System: Re-calculate Risk]
    V --> W{Risk Reduced?}
    W -->|No| P
    W -->|Yes| X[🟦 Document Mitigation Plan]
    X --> Y[✅ END: Risk Mitigated]

    N --> Z[🟦 Continue Monitoring]
    Z --> Y

    style L fill:#FF6B6B
    style O fill:#FF6B6B
```

**Key Multi-User Interactions**:
1. **Risk Manager** → Identifies and assesses risks
2. **Procurement** → Develops supplier diversification strategies
3. **Operations** → Implements buffering and dual-sourcing
4. **SC Director** → Approves mitigation budgets

---

## 21. Group Admin User Management

**Purpose**: Manage users within a group and assign granular functional area capabilities.

**Primary Users**: Group Admin

**Multi-User**: No - Administrative workflow

```mermaid
graph TD
    A[🟦 START: Open User Management] --> B[🟦 View Users List]
    B --> C{Action?}
    C -->|Create| D[🟦 Click Create User]
    C -->|Edit| E[🟦 Select User to Edit]
    C -->|Delete| F[🟦 Select User to Delete]

    D --> G[🟦 User Editor: Basic Info Tab]
    E --> G

    G --> H[🟦 Enter Email Required]
    H --> I[🟦 Enter Username Optional]
    I --> J[🟦 Enter Full Name]
    J --> K[🟦 Enter Password]
    K --> L[🟦 Select User Type]
    L --> M{Creating New?}
    M -->|Yes| N[🟨 System: Validate Email]
    M -->|No| O[🟦 Switch to Capabilities Tab]

    N --> P{Email Valid?}
    P -->|No| Q[🟥 Error: Invalid/Duplicate Email]
    Q --> H
    P -->|Yes| O

    O --> R[🟦 View Capability Tree]
    R --> S[🟦 Expand Functional Area]
    S --> T{Select Method?}
    T -->|Category| U[🟦 Check Category Box]
    T -->|Individual| V[🟦 Check Individual Capabilities]
    T -->|Bulk| W[🟦 Click Select All]

    U --> X[🟨 System: Select All in Category]
    V --> Y[🟦 View Selection Count]
    W --> Z[🟨 System: Select All 59 Capabilities]

    X --> Y
    Z --> Y

    Y --> AA{Satisfied with Selection?}
    AA -->|No| S
    AA -->|Yes| AB[🟦 Click Save]

    AB --> AC[🟨 System: Validate Form]
    AC --> AD{Valid?}
    AD -->|No| AE[🟥 Show Validation Errors]
    AE --> G
    AD -->|Yes| AF[🟨 System: Save User]
    AF --> AG[🟨 System: Create/Update RBAC Entries]
    AG --> AH[🟨 System: Refresh User List]
    AH --> AI[✅ END: User Saved]

    F --> AJ[🟨 System: Confirm Delete]
    AJ --> AK{Confirm?}
    AK -->|No| B
    AK -->|Yes| AL[🟨 System: Delete User]
    AL --> AH

    style Q fill:#FF6B6B
    style AE fill:#FF6B6B
```

**Capability Categories (59 Total)**:
1. **Strategic Planning** (8): Network Design, Demand Forecasting, Inventory Optimization, Stochastic Planning
2. **Tactical Planning** (9): MPS, Lot Sizing, Capacity Check, MRP
3. **Operational Planning** (9): Supply Plan, ATP/CTP, Sourcing, Order Planning
4. **Execution** (8): Order Management, Shipment Tracking, Inventory Visibility, N-Tier
5. **Analytics** (7): SC Analytics, KPI Monitoring, Scenario Comparison, Risk Analysis
6. **AI & Agents** (8): AI Agents, TRM Training, GNN Training, LLM Agents
7. **Gamification** (5): View Games, Create Games, Play Games, Manage Games, Analytics
8. **Administration** (5): View Users, Create Users, Edit Users, Manage Permissions, Manage Groups

---

## Implementation Notes

### Workflow Execution Patterns

**Synchronous Workflows** (Real-time response):
- ATP/CTP checks
- Inventory visibility queries
- KPI monitoring dashboards
- Shipment tracking

**Asynchronous Workflows** (Background processing):
- Supply plan generation (can take 5-10 minutes)
- Monte Carlo simulation (1000+ scenarios)
- MRP explosion (large BOMs)
- Stochastic planning (high computational load)

**Multi-User Collaboration Patterns**:
1. **Sequential Approval Chain**: User A → Manager B → Director C
2. **Parallel Review**: Multiple stakeholders review simultaneously
3. **Consensus Planning**: Sales + Demand Planner collaborate on forecast
4. **Exception Handling**: Receiving Clerk escalates to Buyer

### AI Agent Integration Points

The following workflows can be enhanced with AI agents:

1. **Demand Forecasting** - TRM/GNN agents provide ML-based forecasts
2. **MRP** - Validate planned orders and suggest optimizations
3. **Risk Analysis** - Predict supplier failures and recommend mitigations
4. **Capacity Planning** - Optimize resource allocation
5. **Order Planning** - Automated order quantity optimization
6. **Multi-Agent Orchestration** (Phase 4) - LLM + GNN + TRM ensemble with adaptive weight learning

---

## 22. AI Multi-Agent Decision-Making (Phase 4)

**Purpose**: Generate AI-recommended actions through multi-agent consensus with adaptive weight learning and RLHF.

**Primary Users**: Supply Planner, Operations Manager

**Multi-User**: No - Agent orchestration with human oversight (copilot mode)

```mermaid
graph TD
    A[🟦 START: Decision Required] --> B[🟨 System: Load Current Agent Weights]
    B --> C{Agent Weights Source?}
    C -->|Game| D[🟨 Load from game context]
    C -->|Production| E[🟨 Load from company context]
    C -->|New| F[🟨 Initialize equal weights 33%/33%/33%]

    D --> G[⚡ LLM Agent: Analyze & Recommend]
    E --> G
    F --> G

    G --> H[⚡ GNN Agent: Analyze & Recommend]
    H --> I[⚡ TRM Agent: Analyze & Recommend]

    I --> J[🟨 System: Apply Consensus Method]
    J --> K{Consensus Method?}
    K -->|Voting| L[🟨 Majority vote with confidence]
    K -->|Averaging| M[🟨 Weighted average decision]
    K -->|Confidence-Based| N[🟨 Highest confidence wins]
    K -->|Median| O[🟨 Median value selected]

    L --> P[🟨 System: Calculate Agreement Score]
    M --> P
    N --> P
    O --> P

    P --> Q{Operating Mode?}
    Q -->|Autonomous| R[🟨 System: Execute Decision]
    Q -->|Copilot| S[🟦 Human: Review Recommendation]
    Q -->|Manual| T[🟦 Human: Full Manual Decision]

    R --> U[🟨 System: Execute Action]

    S --> V[🟦 View All 3 Agent Recommendations]
    V --> W[🟦 View Ensemble Consensus]
    W --> X[🟦 View Confidence & Agreement]
    X --> Y{Human Decision?}
    Y -->|Accept| U
    Y -->|Modify| Z[🟦 Human: Override with Reasoning]
    Y -->|Reject| AA[🟦 Human: Full Override]

    Z --> AB[🟨 System: Record RLHF Data]
    AA --> AB
    AB --> AC[🟨 System: Store AI vs Human Decision]
    AC --> U

    T --> AD[🟦 Human: Manual Decision]
    AD --> U

    U --> AE[🟨 System: Track Performance Metrics]
    AE --> AF{Round Complete?}
    AF -->|No| AG[✅ END: Decision Executed]
    AF -->|Yes| AH[🟨 System: Calculate Outcome Metrics]

    AH --> AI[🟨 System: Evaluate Agent Performance]
    AI --> AJ{Learning Enabled?}
    AJ -->|Yes| AK[🟨 System: Update Agent Weights]
    AJ -->|No| AG

    AK --> AL{Learning Algorithm?}
    AL -->|EMA| AM[🟨 Exponential Moving Average Update]
    AL -->|UCB| AN[🟨 Upper Confidence Bound Exploration]
    AL -->|Thompson| AO[🟨 Bayesian Sampling Update]
    AL -->|Performance| AP[🟨 Direct Performance Mapping]
    AL -->|Gradient| AQ[🟨 Gradient Descent Optimization]

    AM --> AR[🟨 System: Persist New Weights]
    AN --> AR
    AO --> AR
    AP --> AR
    AQ --> AR

    AR --> AS{Weights Converged?}
    AS -->|Yes| AT[🟨 System: Mark Converged]
    AS -->|No| AU[🟨 System: Continue Learning]

    AT --> AV{Transfer to Production?}
    AU --> AG

    AV -->|Yes| AW[🟨 System: Deploy to Production Context]
    AV -->|No| AG
    AW --> AG

    style G fill:#FFD700
    style H fill:#FFD700
    style I fill:#FFD700
    style AB fill:#FFD700
    style AK fill:#FFD700
```

**Multi-Agent Ensemble Process**:
1. **LLM Agent**: Strategic reasoning, complex trade-offs, natural language explanations
2. **GNN Agent**: Temporal pattern recognition, demand prediction, network dependencies
3. **TRM Agent**: Fast inference (<10ms), consistent policies, base-stock optimization

**Adaptive Weight Learning (5 Algorithms)**:
- **EMA**: Smooth gradual updates based on performance
- **UCB**: Multi-armed bandit with exploration bonus
- **Thompson Sampling**: Bayesian probabilistic exploration
- **Performance-Based**: Direct mapping from performance to weights
- **Gradient Descent**: Cost function optimization with gradients

**RLHF (Reinforcement Learning from Human Feedback)**:
- Records all human overrides in copilot mode
- Captures AI suggestion, human decision, reasoning, game state
- Tracks outcomes: who was right (AI vs. human)?
- Preference labels: PREFER_AI, PREFER_HUMAN, NEUTRAL
- Builds training dataset for future agent fine-tuning (50,000+ examples)

**Weight Evolution Example**:
```
Initial:   LLM: 33%, GNN: 33%, TRM: 33%  (equal start)
Round 10:  LLM: 30%, GNN: 42%, TRM: 28%  (GNN performing best)
Round 20:  LLM: 38%, GNN: 41%, TRM: 21%  (LLM improving)
Round 30:  LLM: 45%, GNN: 38%, TRM: 17%  (CONVERGED)
```

**Transfer Learning (Games → Production)**:
1. Train weights in games (100+ games, synthetic demand)
2. Validate statistical significance (p < 0.05, A/B testing)
3. Deploy learned weights to production (context_type: company)
4. Continue adapting to real demand (lower learning rate)

**Context-Agnostic Design**:
- Same code works for games and production
- Only difference: context_type (game, company, config) + time scale + demand source
- Agent weights learned in games transfer to production with pre-optimization

---

## 23. Agent Mode Switching

**Purpose**: Dynamically switch between Manual, Copilot, and Autonomous agent modes during gameplay or operations.

**Primary Users**: Supply Planner, Operations Manager

**Multi-User**: No - Individual mode switching workflow

```mermaid
graph TD
    A[🟦 START: Current Mode Active] --> B{Current Mode?}
    B -->|Manual| C[🟦 Human: Full Control]
    B -->|Copilot| D[🟦 Human: Review AI Recommendations]
    B -->|Autonomous| E[⚡ AI: Full Automation]

    C --> F{Switch Request?}
    D --> F
    E --> F

    F -->|No| G[Continue in Current Mode]
    G --> H[✅ END: Mode Active]

    F -->|Yes| I[🟦 Human: Select New Mode]
    I --> J{New Mode?}

    J -->|To Copilot| K[🟩 CONFIRM: Enable AI Assistance]
    J -->|To Autonomous| L[🟩 CONFIRM: Enable Full Automation]
    J -->|To Manual| M[🟩 CONFIRM: Disable AI]

    K --> N[🟨 System: Switch to Copilot]
    L --> O[🟨 System: Switch to Autonomous]
    M --> P[🟨 System: Switch to Manual]

    N --> Q[🟨 System: Record Mode Change]
    O --> Q
    P --> Q

    Q --> R{Trigger Type?}
    R -->|Manual Request| S[🟨 Reason: user requested]
    R -->|Confidence Threshold| T[🟨 Reason: agent confidence low]
    R -->|Override Rate| U[🟨 Reason: high human override rate]
    R -->|System Suggestion| V[🟨 Reason: system recommended]

    S --> W[🟨 System: Update agent_mode_history]
    T --> W
    U --> W
    V --> W

    W --> X[🟨 System: Activate New Mode]
    X --> H
```

**Mode Switch Triggers**:
1. **Manual Request**: User explicitly switches mode
2. **Confidence Threshold**: Agent confidence < 70% → switch from Autonomous to Copilot
3. **Override Rate**: >30% human overrides → switch from Copilot to Manual
4. **System Suggestion**: AI suggests mode change based on performance

**Mode Switching History Tracking**:
- All mode changes recorded in `agent_mode_history` table
- Tracks: player_id, game_id, round_number, previous_mode, new_mode, reason, timestamp
- Analytics: mode switching frequency, mode dwell time, optimal mode per player

---

## 24. A/B Testing for Learning Algorithms

**Purpose**: Compare different weight learning algorithms and consensus methods through statistical A/B testing.

**Primary Users**: Data Scientist, AI Engineer

**Multi-User**: No - Automated testing workflow

```mermaid
graph TD
    A[🟦 START: Create A/B Test] --> B[🟦 Define Test Configuration]
    B --> C[🟦 Set Test Name & Type]
    C --> D{Test Type?}
    D -->|Learning Algorithm| E[🟦 Select Algorithms to Compare]
    D -->|Consensus Method| F[🟦 Select Methods to Compare]
    D -->|Manual vs Adaptive| G[🟦 Configure Weight Strategies]
    D -->|Agent Comparison| H[🟦 Select Agent Types]

    E --> I[🟦 Define Control: EMA]
    F --> I
    G --> I
    H --> I

    I --> J[🟦 Define Variant A: UCB]
    J --> K[🟦 Define Variant B: Thompson Sampling]
    K --> L[🟦 Set Success Metric: total_cost]
    L --> M[🟦 Set Min Samples: 30 games per variant]
    M --> N[🟦 Set Confidence Level: 95%]

    N --> O[🟨 System: Create A/B Test]
    O --> P[🟨 System: Start Test]

    P --> Q[🟨 System: Assign Next Game to Variant]
    Q --> R{Assignment Method?}
    R -->|Round Robin| S[🟨 Rotate: Control → A → B → Control...]
    R -->|Random| T[🟨 Random assignment]

    S --> U[🟨 System: Run Game with Assigned Config]
    T --> U

    U --> V[🟨 System: Record Observation]
    V --> W{Minimum Samples Met?}
    W -->|No| X[🟨 Continue Assigning Games]
    X --> Q

    W -->|Yes| Y[🟨 System: Analyze Results]
    Y --> Z[🟨 Calculate Mean & StdDev per Variant]
    Z --> AA[🟨 Perform Statistical Test]
    AA --> AB{p-value < 0.05?}

    AB -->|No| AC[🟥 Result: No Significant Difference]
    AC --> AD[🟦 Data Scientist: Review & Iterate]
    AD --> AE[✅ END: Test Inconclusive]

    AB -->|Yes| AF[🟩 Result: Statistically Significant]
    AF --> AG[🟨 Determine Winner]
    AG --> AH{Best Variant?}

    AH -->|Control| AI[🟨 Winner: EMA baseline]
    AH -->|Variant A| AJ[🟨 Winner: UCB 8% better]
    AH -->|Variant B| AK[🟨 Winner: Thompson 12% better]

    AI --> AL[🟦 Data Scientist: Review Results]
    AJ --> AL
    AK --> AL

    AL --> AM{Deploy Winner?}
    AM -->|Yes| AN[🟨 System: Deploy to Production]
    AM -->|No| AO[🟦 Run Additional Tests]

    AN --> AP[🟨 Update Default Learning Algorithm]
    AP --> AQ[✅ END: Algorithm Deployed]

    AO --> AD

    style AF fill:#90EE90
    style AC fill:#FF6B6B
```

**A/B Test Configuration Example**:
```
Test Name: "EMA vs UCB Learning Algorithm"
Test Type: learning_algorithm
Control: EMA (learning_rate=0.1)
Variant A: UCB (exploration_factor=2.0)
Success Metric: total_cost (lower is better)
Min Samples: 50 games per variant (100 total)
Confidence Level: 95% (p < 0.05)
```

**Statistical Analysis**:
- **Mean Cost**: Average total cost per variant
- **Standard Deviation**: Measure of variance
- **p-value**: Probability difference is due to chance
- **Improvement %**: (Control - Variant) / Control * 100
- **Confidence Intervals**: P10/P50/P90 cost distribution

**Test Results Example**:
```
Control (EMA):  $52,340 ± $8,200  (50 games)
Variant A (UCB): $48,120 ± $9,100  (50 games)
p-value: 0.003 (< 0.05, statistically significant)
Winner: UCB with 8.1% cost reduction
Recommendation: Deploy UCB to production
```

### Frontend Component Mapping

Each workflow maps to specific frontend components:

| Workflow | Primary Page | Key Components |
|----------|-------------|----------------|
| Network Design | /planning/network-design | SupplyChainConfigForm, D3-Sankey |
| Demand Forecasting | /planning/demand | ForecastChart, ConfidenceBands |
| MPS | /planning/mps | MPSGrid, CapacityGauge |
| Supply Plan | /planning/supply | SupplyPlanGenerator, BalancedScorecard |
| Order Management | /planning/orders | OrderTable, StatusTimeline |
| User Management | /admin/group/users | UserEditor, CapabilitySelector |

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-22 | 1.0 | Initial workflow diagrams for all 21 functional areas |
| 2026-01-28 | 1.1 | Added Phase 4 Multi-Agent Orchestration workflows (#22-24): AI Multi-Agent Decision-Making, Agent Mode Switching, A/B Testing for Learning Algorithms |

---

**End of Workflow Diagrams Document**

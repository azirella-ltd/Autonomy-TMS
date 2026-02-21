# UI/UX Requirements for Autonomy Platform

**Last Updated**: 2026-01-22
**Status**: Planning Phase

---

## Overview

This document outlines the comprehensive UI/UX requirements for all functional areas of the Autonomy Platform, based on AWS Supply Chain standards and industry best practices from SAP IBP, Oracle, and Kinaxis RapidResponse.

### Research Sources

**AWS Supply Chain**:
- [AWS Supply Chain Documentation](https://docs.aws.amazon.com/aws-supply-chain/)
- [Enhanced UI for AWS Supply Chain Demand Planning](https://aws.amazon.com/about-aws/whats-new/2023/07/ui-aws-supply-chain-demand-planning/)
- [AWS Supply Chain Test Drive](https://aws.amazon.com/blogs/supply-chain/aws-supply-chain-test-drive-simplifies-adoption-to-explore-business-benefits/)

**Industry Best Practices**:
- [SAP IBP Integrated Business Planning](https://www.sap.com/products/scm/integrated-business-planning.html)
- [Oracle MRP Strategic Guide](https://www.suretysystems.com/insights/oracle-mrp-your-strategic-guide-for-enhanced-planning-efficiency/)
- [Supply Chain Planning Process Flow](https://www.wolterskluwer.com/en/expert-insights/mps-mrp-drp-help-supply-chains)

---

## Table of Contents

1. [Strategic Planning](#strategic-planning)
2. [Tactical Planning](#tactical-planning)
3. [Operational Planning](#operational-planning)
4. [Execution](#execution)
5. [AI & Agents](#ai--agents)
6. [Cross-Cutting Concerns](#cross-cutting-concerns)
7. [User Administration](#user-administration)

---

## Strategic Planning

### 1. Network Design

**Purpose**: Define and manage supply chain network topology (nodes, lanes, BOMs)

**User Roles**: Supply Chain Architect, Network Planner

**Workflow**:
1. **View Network** → Sankey diagram showing all nodes and material flows
2. **Create/Edit Nodes** → Form with master type, capacity, lead times
3. **Define Lanes** → Connect nodes with transportation routes
4. **Configure BOMs** → Define product transformation ratios
5. **Validate Network** → Check for cycles, disconnected nodes
6. **Publish Configuration** → Make active for planning

**UI Components**:
- **Network Visualizer**: Interactive Sankey diagram (D3.js)
  - Node types colored by master type (MARKET_SUPPLY, INVENTORY, MANUFACTURER, MARKET_DEMAND)
  - Lane widths represent flow volume
  - Hover shows node/lane details
  - Drag-and-drop to reposition nodes
- **Node Editor**: Drawer panel with forms
  - Master type dropdown
  - Capacity input with unit selection
  - Lead time configuration
  - Cost parameters
- **BOM Matrix**: Spreadsheet-style editor
  - Parent product (rows) × Component (columns)
  - Quantity per assembly
  - Scrap rate %
  - Yield rate %
- **Validation Panel**: Alert list
  - Critical issues (red): Network cycles, missing connections
  - Warnings (yellow): High scrap rates, unusual lead times
  - Info (blue): Configuration suggestions

**Key Visualizations**:
- Sankey diagram for network flow
- Capacity utilization heat map
- Lead time waterfall chart
- BOM explosion tree view

**Multi-User Interaction**: Network Architect designs → Supply Chain Director approves → System publishes

**Status**: 🔄 Partially implemented (existing `supply-chain-config` components)

---

### 2. Demand Forecasting

**Purpose**: Generate statistical and ML-based demand forecasts with P10/P50/P90 percentiles

**User Roles**: Demand Planner, Category Manager, Marketing Analyst

**Workflow**:
1. **Select Products/Sites** → Multi-select with filters
2. **Choose Forecast Method** → Statistical (MA, ES, Seasonal) or ML (ARIMA, Prophet)
3. **Configure Parameters** → History window, seasonality, external factors
4. **Run Forecast** → Submit async job
5. **Review Results** → Charts with confidence intervals
6. **Apply Overrides** → Manual adjustments for promotions/events
7. **Approve Forecast** → Lock for downstream planning
8. **Monitor Accuracy** → Compare forecast vs. actual over time

**UI Components**:
- **Product/Site Selector**: Multi-select tree
  - Hierarchy: Category → Product Family → SKU
  - Geography: Region → DC → Store
  - Bulk select by attributes
- **Forecast Configuration Panel**:
  - Method tabs (Statistical | ML | Consensus)
  - Parameter sliders (history window: 4-52 weeks)
  - Seasonality toggles (weekly, monthly, yearly)
  - External factors checkboxes (promotions, weather, events)
- **Forecast Review Dashboard**:
  - **Time Series Chart**: Line chart with Recharts
    - Historical actuals (solid line)
    - Forecast P50 (dashed line)
    - P10/P90 confidence band (shaded area)
    - User overrides (dotted line)
  - **Accuracy Metrics Table**:
    - MAPE (Mean Absolute Percentage Error)
    - Bias (over/under-forecast tendency)
    - MAD (Mean Absolute Deviation)
  - **Comparison View**: Actual vs. Forecast
    - Month-over-month comparison
    - Forecast error breakdown by product
- **Override Editor**: Spreadsheet grid
  - Columns: Product | Site | Week | Forecast | Override | Reason
  - Inline editing with validation
  - Bulk override tools (% increase/decrease)
- **Approval Workflow**:
  - Status badges (Draft | Pending Approval | Approved)
  - Comment thread for collaboration
  - Audit trail of changes

**Key Visualizations**:
- Time series line chart with confidence bands
- Forecast vs. actual scatter plot
- Error distribution histogram
- Product contribution Pareto chart

**Multi-User Interaction**:
- Demand Planner generates forecast
- Category Manager reviews and overrides
- Marketing provides promotional input
- Demand Planning Director approves

**Status**: 🆕 Coming (referenced in PLANNING_CAPABILITIES.md)

---

### 3. Inventory Optimization

**Purpose**: Calculate optimal safety stock levels using 4 policy types with hierarchical overrides

**User Roles**: Inventory Planner, Supply Chain Manager

**Workflow**:
1. **Select Scope** → Products, sites, or network-wide
2. **Choose Policy Type** → abs_level, doc_dem, doc_fcst, or sl
3. **Set Parameters** → Target days, service level %, fixed quantity
4. **Apply Hierarchical Rules** → Item-Node > Item > Node > Config
5. **Run Optimization** → Calculate targets considering demand/lead time variability
6. **Review Recommendations** → Compare current vs. optimal inventory
7. **Simulate Impact** → What-if analysis (cost, service level, turns)
8. **Approve Targets** → Publish for MRP/Supply Planning

**UI Components**:
- **Policy Configuration Matrix**:
  - Rows: Products/Nodes
  - Columns: Policy Type | Target Value | Priority Level
  - Cell coloring: Green (direct assignment), Blue (inherited), Gray (default)
- **Optimization Dashboard**:
  - **Current State Panel**:
    - Avg inventory level
    - Inventory turns
    - Stockout frequency
    - Holding cost
  - **Optimized State Panel** (side-by-side):
    - Projected inventory level
    - Projected turns
    - Projected stockout rate
    - Projected cost savings
  - **Impact Waterfall Chart**: Δ from current to optimized by product group
- **Policy Simulator**:
  - Slider controls for policy parameters
  - Real-time recalculation of targets
  - Service level vs. cost trade-off curve
- **Hierarchical Override Visualizer**:
  - Tree view showing override cascade
  - Highlight which level sets effective policy
  - Override conflicts flagged

**Key Visualizations**:
- Inventory level time series
- Service level vs. cost scatter plot
- Policy coverage heat map (products × sites)
- Safety stock recommendations bar chart

**Multi-User Interaction**:
- Inventory Planner runs optimization
- Category Managers review product-specific policies
- Supply Chain Manager approves network-wide targets

**Status**: 🆕 Coming

---

### 4. Stochastic Planning

**Purpose**: Run Monte Carlo simulations for risk-aware planning with probabilistic outcomes

**User Roles**: Supply Chain Analyst, Risk Manager, VP Supply Chain

**Workflow**:
1. **Define Scenario** → Select config, planning horizon
2. **Configure Distributions** → Lead time, yield, demand variability
3. **Set Control Variables** → Inventory targets, costs (deterministic)
4. **Run Simulation** → 1000+ scenarios with variance reduction
5. **Analyze Results** → Probabilistic Balanced Scorecard
6. **Explore Scenarios** → What-if analysis (supplier change, capacity increase)
7. **Export Report** → PDF with P10/P50/P90 metrics for executives

**UI Components**:
- **Distribution Builder**:
  - 20 distribution types (Normal, Lognormal, Beta, Gamma, etc.)
  - Interactive parameter sliders
  - PDF/CDF preview charts
  - Historical data fitting tool
- **Monte Carlo Configuration Panel**:
  - Number of scenarios (100-10,000)
  - Random seed for reproducibility
  - Variance reduction techniques checkboxes
  - Parallel execution toggle
- **Probabilistic Balanced Scorecard**:
  - **4 Quadrants** (Financial | Customer | Operational | Strategic)
  - Each metric shows:
    - E[Value] (expected value)
    - P10/P50/P90 percentiles
    - Distribution histogram (sparkline)
    - P(Target Met) indicator
  - Example Financial Metrics:
    - E[Total Cost] = $850,000
    - P90[Total Cost] = $1,100,000 (Cost-at-Risk)
    - P(Cost < $1M Budget) = 75%
  - Example Customer Metrics:
    - E[OTIF] = 93%
    - P(OTIF > 95%) = 42%
- **Scenario Comparison Table**:
  - Columns: Base Case | Scenario A | Scenario B | Best Case | Worst Case
  - Rows: All key metrics
  - Color coding: Green (improvement), Red (degradation)
- **Risk Exposure Charts**:
  - Cost distribution violin plot
  - Service level likelihood curve
  - Inventory turns box plot

**Key Visualizations**:
- Distribution PDF/CDF curves
- Probabilistic balanced scorecard (4-quadrant)
- Scenario waterfall charts
- Risk heat maps
- Monte Carlo convergence plots

**Multi-User Interaction**:
- Supply Chain Analyst configures and runs simulations
- Risk Manager reviews P90 outcomes
- VP Supply Chain makes strategic decisions based on risk appetite

**Status**: ✅ Backend complete, 🆕 Frontend coming

---

## Tactical Planning

### 5. Master Production Schedule (MPS)

**Purpose**: Strategic production planning with rough-cut capacity checks

**User Roles**: Production Planner, Plant Manager

**Workflow**:
1. **Create MPS Plan** → Select config, planning horizon (13-52 weeks)
2. **Load Demand** → Import forecasts and customer orders
3. **Generate Production Schedule** → Time-phased production quantities
4. **Check Capacity** → RCCP (Rough-Cut Capacity Planning)
5. **Resolve Conflicts** → Adjust production or capacity
6. **Approve MPS** → Lock plan for MRP explosion
7. **Release to Manufacturing** → Generate Manufacturing Orders
8. **Monitor Execution** → Track MPS vs. actuals

**UI Components**:
- **MPS Plan List**: Card grid
  - Plan name, status (Draft | Approved | In Execution)
  - Date range, product count
  - Capacity utilization badge
  - Actions: View | Edit | Approve | Generate Orders
- **MPS Planning Grid**: Spreadsheet
  - Rows: Products
  - Columns: Weeks (scrollable timeline)
  - Cells: Planned production quantity
  - Cell coloring:
    - Green: Within capacity
    - Yellow: Approaching capacity limit
    - Red: Exceeds capacity
  - Inline editing with auto-save
- **Capacity Check Panel** (right sidebar):
  - **Resource Utilization Chart**: Stacked bar chart
    - Available capacity (gray bar)
    - Required capacity (colored segments by product)
    - Overload indicator (red overflow)
  - **Bottleneck Alert List**:
    - Resource name
    - Week number
    - Overload %
    - Suggested actions
- **Demand vs. Supply Chart**: Dual-axis line chart
  - Demand (line): Forecast + customer orders
  - Supply (bars): Planned production + inventory
  - Cumulative ATP (area chart)

**Key Visualizations**:
- Production timeline Gantt chart
- Capacity utilization stacked bar chart
- Demand vs. supply dual-axis chart
- Bottleneck heat map

**Multi-User Interaction**:
- Production Planner creates MPS
- Plant Manager reviews capacity constraints
- Operations Director approves
- Manufacturing receives released orders

**Status**: ✅ Implemented ([MasterProductionScheduling.jsx](frontend/src/pages/MasterProductionScheduling.jsx))

---

### 6. Lot Sizing Analysis

**Purpose**: Determine optimal order/production quantities considering setup costs and holding costs

**User Roles**: Production Planner, Purchasing Manager

**Workflow**:
1. **Select Products** → Multi-select with filters
2. **Configure Cost Parameters** → Setup cost, holding cost, ordering cost
3. **Choose Lot Sizing Rule** → EOQ, POQ, LFL, FOQ, Min/Max
4. **Run Analysis** → Calculate optimal lot sizes
5. **Review Trade-Offs** → Setup cost vs. holding cost
6. **Apply Lot Sizes** → Update item master or MPS/MRP parameters
7. **Monitor Performance** → Track inventory turns and setup frequency

**UI Components**:
- **Lot Sizing Configuration Panel**:
  - Product selector with search/filter
  - Cost inputs (setup, holding, ordering)
  - Demand rate input
  - Lead time input
- **Lot Sizing Rule Tabs**:
  - **EOQ (Economic Order Quantity)**: Classic square root formula
  - **POQ (Period Order Quantity)**: Order for multiple periods
  - **LFL (Lot-for-Lot)**: Match net requirements exactly
  - **FOQ (Fixed Order Quantity)**: User-defined fixed lot
  - **Min/Max**: Reorder when below min, order up to max
- **Analysis Results Table**:
  - Columns: Product | Current Lot Size | Recommended Lot Size | Savings | Frequency
  - Sortable and filterable
- **Trade-Off Chart**: Cost curve visualization
  - X-axis: Lot size
  - Y-axis: Total cost
  - Curves: Setup cost (decreasing), Holding cost (increasing), Total cost (U-shaped)
  - Optimal point marked with star

**Key Visualizations**:
- Cost trade-off curve (EOQ U-curve)
- Lot size comparison bar chart
- Setup frequency calendar heat map
- Savings waterfall chart

**Multi-User Interaction**:
- Production Planner analyzes and recommends
- Purchasing Manager reviews for procurement
- CFO approves changes with significant cost impact

**Status**: 🔄 Partially implemented ([LotSizingAnalysis.jsx](frontend/src/pages/planning/LotSizingAnalysis.jsx))

---

### 7. Capacity Check

**Purpose**: Validate production/distribution capacity against planned orders

**User Roles**: Capacity Planner, Plant Manager, Distribution Manager

**Workflow**:
1. **Load Plan** → Import MPS or supply plan
2. **Load Capacity Data** → Resource availability by period
3. **Run Capacity Check** → Calculate utilization %
4. **Identify Bottlenecks** → Resources with >90% utilization or overload
5. **Drill Down** → View orders consuming capacity
6. **Propose Solutions** → Add shifts, outsource, reschedule
7. **Approve Feasible Plan** → Mark capacity-validated

**UI Components**:
- **Capacity Overview Dashboard**:
  - **Utilization Gauge Cards**: One per resource type
    - Machine capacity: 87% (green)
    - Labor hours: 102% (red - overload!)
    - Warehouse space: 65% (blue)
  - **Timeline Gantt Chart**:
    - Rows: Resources
    - Columns: Time periods
    - Bars: Orders/operations
    - Background shading: Capacity level (green → yellow → red)
- **Bottleneck Alert Panel**:
  - List of resources with issues
  - Click to drill down to specific orders
- **Order Detail View** (modal):
  - Order number and product
  - Required capacity by resource
  - Scheduled date
  - Actions: Reschedule | Split | Cancel
- **What-If Simulator**:
  - Add capacity slider (temp workers, overtime, new equipment)
  - See real-time impact on utilization

**Key Visualizations**:
- Resource utilization Gantt chart
- Capacity vs. requirement stacked bar chart
- Bottleneck heat map (resources × time periods)
- Load profile line chart

**Multi-User Interaction**:
- Capacity Planner runs checks
- Plant Manager reviews manufacturing bottlenecks
- Distribution Manager reviews warehouse constraints
- Operations Director approves capacity expansions

**Status**: 🔄 Partially implemented ([CapacityCheck.jsx](frontend/src/pages/planning/CapacityCheck.jsx))

---

### 8. MRP (Material Requirements Planning)

**Purpose**: Derive component requirements from MPS with multi-level BOM explosion

**User Roles**: Material Planner, Buyer, Production Control

**Workflow**:
1. **Load MPS Plan** → Select approved MPS
2. **Configure MRP Run** → Planning horizon, low-level codes
3. **Run MRP** → Multi-level BOM explosion with lead time offsetting
4. **Review Planned Orders** → PO/TO/MO recommendations
5. **Manage Exceptions** → Late orders, short supply, excess inventory
6. **Adjust and Rerun** → Modify parameters and re-explode
7. **Release Orders** → Convert planned orders to firm orders
8. **Track Execution** → Monitor order status

**UI Components**:
- **MRP Run Configuration**:
  - MPS plan dropdown
  - Planning horizon slider (1-52 weeks)
  - Exception thresholds (late orders, excess inventory)
  - BOM explosion options (consider scrap, yield, lead time)
- **MRP Results Dashboard**:
  - **Planned Orders Table**: Filterable/sortable grid
    - Columns: Order Type (PO/TO/MO) | Part Number | Quantity | Due Date | Supplier/Source | Status
    - Actions: Release | Reschedule | Cancel
  - **Exception Manager**: Alert list
    - Late orders (past due date)
    - Short supply (insufficient ATP)
    - Excess inventory (>120% of target)
    - Reschedule recommendations
  - **BOM Pegging Viewer**: Tree view
    - Parent MPS item
    - └─ Component 1 (Qty × BOM ratio)
      - └─ Sub-component A
      - └─ Sub-component B
    - └─ Component 2
    - Expand/collapse multi-level structure
- **Order Release Wizard**:
  - Batch select planned orders
  - Set release date
  - Add comments/instructions
  - Confirm and release

**Key Visualizations**:
- BOM explosion tree diagram
- Planned order timeline (Gantt)
- Exception dashboard with counts
- Lead time waterfall chart
- Supply/demand balance chart by component

**Multi-User Interaction**:
- Material Planner runs MRP and reviews recommendations
- Buyer releases purchase orders to suppliers
- Production Control releases manufacturing orders to shop floor
- Expeditor manages exception orders

**Status**: ✅ Phase 3 complete ([MRPRun.jsx](frontend/src/pages/planning/MRPRun.jsx), backend in `backend/app/services/mrp/`)

---

## Operational Planning

### 9. Supply Planning

**Purpose**: Generate supply plan (PO/TO/MO recommendations) using AWS SC 3-step process

**User Roles**: Supply Planner, Purchasing Manager

**Workflow**:
1. **Step 1: Demand Processing** → Aggregate forecasts and customer orders
2. **Step 2: Inventory Target Calculation** → Compute safety stock using 4 policy types
3. **Step 3: Net Requirements Calculation** → Time-phased netting and sourcing
4. **Review Supply Plan** → PO/TO/MO recommendations by week
5. **Approve Supply Plan** → Lock plan for execution
6. **Release Orders** → Send to purchasing/production
7. **Monitor Execution** → Track order status and exceptions

**UI Components**:
- **Supply Plan Generation Wizard** (stepper):
  - Step 1: Select config and planning horizon
  - Step 2: Configure stochastic parameters (optional)
  - Step 3: Set objectives (minimize cost, target service level)
  - Step 4: Review and submit
- **Supply Plan Results Dashboard**:
  - **Summary Cards**:
    - Total POs: 152
    - Total TOs: 87
    - Total MOs: 43
    - Total Cost: $1.2M
    - Expected Service Level: 94%
  - **Recommendations Table**: Filterable grid
    - Columns: Order Type | Part | Quantity | Source | Due Date | Cost
    - Color coding: Green (normal), Yellow (late), Red (critical shortage)
  - **Timeline View**: Gantt chart of all recommendations
- **Probabilistic Balanced Scorecard** (if stochastic):
  - Financial: E[Cost], P90[Cost], P(Cost < Budget)
  - Customer: E[OTIF], P(OTIF > 95%)
  - Operational: E[Inventory Turns], E[Days of Supply]

**Key Visualizations**:
- Supply plan timeline (Gantt)
- Order mix pie chart (PO/TO/MO)
- Cost breakdown stacked bar chart
- Service level distribution (if stochastic)
- Network flow Sankey diagram

**Multi-User Interaction**:
- Supply Planner generates and reviews plan
- Purchasing Manager reviews PO recommendations
- Production Manager reviews MO recommendations
- Supply Chain Director approves plan

**Status**: 🔄 Partially implemented (backend complete, frontend in progress)

---

## Execution

### 10. Production Orders

**Purpose**: Manage manufacturing orders from release through completion

**User Roles**: Production Supervisor, Shop Floor Manager, Quality Inspector

**Workflow**:
1. **View Production Orders** → List of MOs in various statuses
2. **Release Order** → Start production
3. **Report Progress** → Update completion %
4. **Record Material Consumption** → Component usage
5. **Report Scrap/Yield** → Actual vs. planned yield
6. **Complete Order** → Finish and put away finished goods
7. **Close Order** → Financial close and variance analysis

**UI Components**:
- **Production Order List**: Card grid with status badges
  - Order number
  - Product and quantity
  - Status: Planned | Released | In Progress | Completed | Closed
  - Start date and due date
  - Progress bar
  - Actions: Release | Report | Complete
- **Production Order Detail** (modal):
  - **Header**: Order info and status
  - **BOM Tab**: Component list
    - Component name
    - Required quantity (per BOM)
    - Issued quantity
    - Remaining to issue
    - Issue button
  - **Operations Tab**: Routing steps
    - Operation sequence
    - Resource
    - Estimated time
    - Actual time
    - Status (Pending | In Progress | Complete)
  - **Quality Tab**: Inspection checkpoints
    - Checkpoint name
    - Pass/Fail status
    - Inspector and timestamp
  - **Scrap Tab**: Scrap reporting
    - Scrap quantity
    - Scrap reason
    - Rework available?
- **Production Schedule Gantt Chart**:
  - Rows: Work centers/machines
  - Bars: Production orders
  - Color by status
  - Drag-and-drop to reschedule

**Key Visualizations**:
- Production schedule Gantt chart
- Order status funnel chart
- Yield performance trend line
- Resource utilization heat map

**Multi-User Interaction**:
- Production Planner releases orders
- Shop Floor Manager assigns to work centers
- Operators report progress and material consumption
- Quality Inspector records inspections
- Production Supervisor completes orders

**Status**: ✅ Implemented ([ProductionOrders.jsx](frontend/src/pages/production/ProductionOrders.jsx))

---

### 11. Purchase Orders

**Purpose**: Manage procurement from suppliers (vendors)

**User Roles**: Buyer, Purchasing Manager, Receiving Clerk

**Workflow**:
1. **View Purchase Requisitions** → From supply plan or MRP
2. **Create Purchase Order** → Convert requisition to PO
3. **Submit to Supplier** → Send via EDI/email/portal
4. **Track Status** → Acknowledged, Shipped, In Transit
5. **Receive Goods** → Record receipt and inspect
6. **Process Invoice** → 3-way match (PO, Receipt, Invoice)
7. **Close PO** → Mark complete

**UI Components**:
- **PO List**: Data grid with filters
  - PO number
  - Supplier
  - Total value
  - Due date
  - Status (Draft | Submitted | Acknowledged | Shipped | Received)
  - Actions: View | Edit | Send | Receive
- **PO Detail View**:
  - **Header**: PO number, supplier, dates
  - **Lines Table**:
    - Item number and description
    - Ordered quantity
    - Received quantity
    - Remaining quantity
    - Unit price
    - Total line amount
  - **Terms Section**:
    - Payment terms (Net 30, 2/10 Net 30)
    - Incoterms (FOB, CIF, DDP)
    - Delivery address
  - **Document Attachments**:
    - Upload/download PO PDF
    - Packing list
    - Certificate of Analysis
- **Receiving Interface**:
  - Scan barcode or enter PO number
  - Select line items to receive
  - Enter received quantity
  - Record lot/serial numbers
  - Quality check pass/fail
  - Put away location
- **Supplier Performance Dashboard**:
  - On-time delivery rate (%)
  - Fill rate (%)
  - Quality rate (%)
  - Average lead time (actual vs. promised)

**Key Visualizations**:
- PO status funnel chart
- Supplier performance scorec card
- Receiving timeline
- Cost variance chart (PO value vs. invoice)

**Multi-User Interaction**:
- Buyer creates and submits POs to suppliers
- Supplier acknowledges and ships
- Receiving Clerk records receipt
- Accounts Payable processes invoices

**Status**: ✅ Phase 3 complete ([PurchaseOrders.jsx](frontend/src/pages/planning/PurchaseOrders.jsx))

---

### 12. Transfer Orders

**Purpose**: Manage inter-site inventory movements with in-transit tracking (AWS SC compliant)

**User Roles**: Distribution Planner, Warehouse Manager, Logistics Coordinator

**Workflow**:
1. **Create Transfer Order** → From supply plan or manually
2. **Release TO** → Authorize shipment
3. **Pick Inventory** → Source warehouse picks items
4. **Ship TO** → Create shipment and update status to in-transit
5. **Track Shipment** → Monitor carrier status
6. **Receive TO** → Destination warehouse receives and puts away
7. **Close TO** → Mark complete

**UI Components**:
- **TO List**: Data grid
  - TO number
  - Origin site → Destination site
  - Product and quantity
  - Ship date and expected arrival date
  - Status (Draft | Released | Picked | Shipped | In Transit | Received)
  - Actions: View | Ship | Receive
- **TO Detail View**:
  - **Header**: TO number, sites, dates
  - **Lines Table**:
    - Product
    - Ordered quantity
    - Shipped quantity
    - Received quantity
    - Variance
  - **Shipment Tracking Section**:
    - Carrier and tracking number
    - Current location (if GPS enabled)
    - Estimated arrival date
    - Shipment events timeline
- **Transfer Order Timeline** (visual):
  - Horizontal timeline showing:
    - Created (dot)
    - Released (dot)
    - Shipped (dot)
    - In Transit (current, animated)
    - Expected Arrival (future dot)
  - Progress bar between milestones
- **Network Flow Visualizer**:
  - Sankey diagram of all active TOs
  - Node size = inventory level
  - Lane width = TO quantity in transit

**Key Visualizations**:
- TO status pipeline chart
- In-transit inventory map (geographic)
- Lead time performance (actual vs. planned)
- Network flow Sankey diagram

**Multi-User Interaction**:
- Distribution Planner creates TOs from supply plan
- Source Warehouse Manager picks and ships
- Logistics Coordinator tracks shipments
- Destination Warehouse Manager receives

**Status**: ✅ Phase 3 complete ([TransferOrders.jsx](frontend/src/pages/planning/TransferOrders.jsx), AWS SC compliant with Integer FKs)

---

### 13. Inventory Management

**Purpose**: Real-time inventory visibility, adjustments, and lot tracking

**User Roles**: Warehouse Manager, Inventory Control, Auditor

**Workflow**:
1. **View Inventory Levels** → By site, product, lot
2. **Adjust Inventory** → Cycle count corrections, damage, theft
3. **Transfer Inventory** → Internal movements within site
4. **Reserve Inventory** → ATP consumption for orders
5. **Release Reservation** → Unallocate inventory
6. **Manage Lots** → FEFO/FIFO, expiration tracking
7. **Run ABC Analysis** → Classify items by value/volume

**UI Components**:
- **Inventory Dashboard**:
  - **Summary Cards**:
    - Total inventory value
    - Inventory turns (last 12 months)
    - Stockout items count
    - Excess inventory value
  - **Inventory Levels Table**: Sortable/filterable grid
    - Site
    - Product
    - On-hand quantity
    - Available quantity (on-hand - reserved)
    - Reserved quantity
    - In-transit quantity
    - Days of supply
    - Status indicator (Good | Low | Stockout | Excess)
  - **Inventory Projection Chart**: Line chart
    - Historical on-hand (past 12 weeks)
    - Projected on-hand (future 12 weeks)
    - Safety stock line (dotted)
    - Reorder point line (dotted)
- **Inventory Adjustment Form**:
  - Site selector
  - Product selector
  - Current quantity (read-only)
  - Adjustment quantity (+/-)
  - Reason dropdown (Cycle Count, Damage, Theft, Found, Other)
  - Comments text area
  - Submit button
- **Lot Management Table**:
  - Lot number
  - Product
  - Site
  - Quantity
  - Received date
  - Expiration date
  - Days to expiration
  - Quality status (Approved | Quarantine | Rejected)
  - Actions: Release | Hold | Dispose
- **ABC Classification Chart**:
  - Pareto chart (bar + line)
  - X-axis: Items (sorted by value)
  - Left Y-axis: Item value
  - Right Y-axis: Cumulative % of total value
  - A items (red): 70% of value
  - B items (yellow): 20% of value
  - C items (green): 10% of value

**Key Visualizations**:
- Inventory level timeline
- ABC Pareto chart
- Lot expiration calendar heat map
- Stockout risk heat map (products × sites)

**Multi-User Interaction**:
- Warehouse Manager views and adjusts inventory
- Inventory Control audits and runs cycle counts
- Production Planner checks availability
- Purchasing reviews reorder points

**Status**: 🆕 Coming

---

### 14. Order Management

**Purpose**: Manage customer orders from promise through fulfillment

**User Roles**: Customer Service, Order Fulfillment, Shipping

**Workflow**:
1. **Create Customer Order** → Enter order lines
2. **Check ATP** → Promise delivery date
3. **Reserve Inventory** → Allocate stock
4. **Release to Warehouse** → Create pick wave
5. **Pick Order** → Warehouse picks items
6. **Pack Order** → Box and label
7. **Ship Order** → Create shipment and carrier label
8. **Confirm Delivery** → Mark delivered

**UI Components**:
- **Order List**: Data grid
  - Order number
  - Customer name
  - Order date
  - Requested delivery date
  - Promised delivery date
  - Status (Open | Promised | Released | Picked | Packed | Shipped | Delivered)
  - Total value
  - Actions: View | Edit | Release | Ship
- **Order Detail View**:
  - **Header**: Order info, customer, dates
  - **Lines Table**:
    - Item
    - Ordered quantity
    - Promised quantity
    - Picked quantity
    - Shipped quantity
    - Backorder quantity
    - Unit price
    - Line total
  - **ATP Check Button**: Calculate promise date for each line
  - **Reservation Status**: Show allocated inventory by site
  - **Shipment Section**:
    - Carrier
    - Service level (Ground, 2-Day, Overnight)
    - Tracking number
    - Ship date
    - Delivered date
- **Pick Wave Management**:
  - Create wave (batch multiple orders)
  - Assign to picker
  - Print pick list
  - Scan items
  - Confirm picks
- **Packing Station Interface**:
  - Scan order number
  - Display items to pack
  - Select box size
  - Print shipping label
  - Confirm packed

**Key Visualizations**:
- Order status funnel
- OTIF (On-Time-In-Full) trend chart
- Order cycle time histogram
- Backorder aging chart

**Multi-User Interaction**:
- Customer Service creates orders and checks ATP
- Order Fulfillment Manager releases to warehouse
- Warehouse Picker picks items
- Packer packs and labels
- Shipping Clerk creates shipments

**Status**: 🆕 Coming

---

### 15. Shipment Tracking

**Purpose**: Track shipments from origin to destination with carrier integration

**User Roles**: Logistics Coordinator, Customer Service, Warehouse Manager

**Workflow**:
1. **Create Shipment** → From PO, TO, or customer order
2. **Select Carrier** → UPS, FedEx, freight forwarder
3. **Generate Label** → Carrier API integration
4. **Ship Package** → Scan and tender to carrier
5. **Track Shipment** → Real-time status updates
6. **Handle Exceptions** → Delays, damage, lost packages
7. **Confirm Delivery** → Update order/transfer status

**UI Components**:
- **Shipment Dashboard**:
  - **Summary Cards**:
    - In Transit: 234
    - Out for Delivery: 45
    - Delivered Today: 128
    - Exceptions: 7
  - **Shipment Map**: Geographic visualization
    - Pins for shipment locations
    - Lines connecting origin → destination
    - Color by status (blue=transit, green=delivered, red=exception)
  - **Shipment List**: Data grid
    - Tracking number
    - Order/TO number
    - Origin → Destination
    - Carrier and service
    - Ship date
    - Expected delivery
    - Status
    - Actions: Track | Details
- **Shipment Detail View**:
  - **Header**: Tracking number, order reference
  - **Progress Timeline**: Horizontal stepper
    - Picked Up (timestamp, location)
    - In Transit (timestamp, location)
    - Out for Delivery (timestamp, location)
    - Delivered (timestamp, location, signature)
  - **Package Contents**: List of items
  - **Delivery Proof**: Signature image or photo
- **Exception Manager**:
  - List of shipments with issues
  - Exception type (Delay, Damaged, Lost, Refused, Address Unknown)
  - Recommended actions
  - Contact carrier button
  - Reship button

**Key Visualizations**:
- Shipment status map (geographic)
- Delivery timeline (Gantt)
- On-time delivery % trend
- Carrier performance scorecard

**Multi-User Interaction**:
- Warehouse ships packages
- Logistics Coordinator monitors all shipments
- Customer Service answers delivery inquiries
- Receiving confirms delivery

**Status**: 🆕 Coming

---

### 16. ATP/CTP Projection

**Purpose**: Project Available-to-Promise and Capable-to-Promise over planning horizon

**User Roles**: Customer Service, Sales, Order Fulfillment Manager

**Workflow**:
1. **Select Product and Site** → Item to check availability
2. **View ATP Timeline** → Week-by-week ATP projection
3. **View CTP Timeline** → Include production capacity
4. **Simulate Order** → What-if: "If I promise 500 units on Week 5, what happens?"
5. **Export ATP Report** → Share with sales/customers

**UI Components**:
- **ATP/CTP Query Form**:
  - Product selector
  - Site selector (or multi-site search)
  - Horizon selector (4-52 weeks)
  - Include CTP checkbox
- **ATP Projection Chart**: Waterfall chart
  - Starting inventory (bar)
  - + Scheduled receipts (green bars)
  - − Reserved demand (red bars)
  - = ATP (net bar)
  - Repeated for each week
  - Negative ATP shown in red (stockout)
- **CTP Projection Chart** (if enabled):
  - ATP (from above)
  - + Available capacity × production rate (blue bars)
  - − BOM component constraints (yellow reduction)
  - = CTP (final net bar)
- **ATP Table**: Spreadsheet grid
  - Columns: Week | On-Hand | Scheduled Receipts | Reserved | ATP | CTP
  - Sortable and exportable to Excel
- **What-If Simulator**:
  - Add hypothetical order (quantity, week)
  - Instantly see impact on ATP/CTP
  - Save scenario for comparison

**Key Visualizations**:
- ATP waterfall chart (week-over-week)
- CTP stacked bar chart
- Multi-site ATP comparison (if multi-site search)

**Multi-User Interaction**:
- Customer Service checks ATP for order promising
- Sales uses projections for customer negotiations
- Order Fulfillment Manager monitors ATP across network

**Status**: 🆕 Coming

---

## AI & Agents

### 17. AI Agent Configuration

**Purpose**: Configure, train, and deploy AI planning agents (TRM, GNN, LLM)

**User Roles**: Data Scientist, AI Engineer, Supply Chain Architect

**Workflow**:
1. **Select Agent Type** → TRM, GNN, or LLM
2. **Configure Training Data** → Historical game data or SimPy-generated data
3. **Set Hyperparameters** → Epochs, batch size, learning rate, device (CPU/GPU)
4. **Start Training** → Submit training job
5. **Monitor Training** → Real-time loss curves and metrics
6. **Evaluate Agent** → Run benchmark games (vs. naive, vs. optimal)
7. **Deploy Agent** → Make available for game assignment or planning workflows

**UI Components**:
- **Agent Type Selector**: Card grid
  - **TRM Agent Card**:
    - Icon: neural network
    - Description: "7M parameters, <10ms inference"
    - Use case: "Real-time operational decisions"
    - Select button
  - **GNN Agent Card**:
    - Icon: graph
    - Description: "128M parameters, network coordination"
    - Use case: "Multi-node supply chain planning"
    - Select button
  - **LLM Agent Card**:
    - Icon: chat bubble
    - Description: "GPT-4 based, natural language explainability"
    - Use case: "Strategic planning with human collaboration"
    - Select button
- **Ask Why Requirements** (all agent types):
  - **Trigger**: "Ask Why" button on any agent decision in worklist or decision history
  - **Verbosity**: Toggle between SUCCINCT / NORMAL / VERBOSE levels
  - **Sections** (collapsible accordion in `AskWhyPanel.jsx`):
    1. **Authority Context** (Shield icon): Classification chip (UNILATERAL green / REQUIRES_AUTH amber / ADVISORY blue), authority level badge, statement text, approval info if escalated
    2. **Active Guardrails** (Gauge icon): Traffic-light indicators per guardrail (green=WITHIN, yellow=APPROACHING, red=EXCEEDED), threshold vs actual values, margin percentage
    3. **Feature Attribution** (BarChart icon): Horizontal bar chart of top-5 features by importance, neighbor attention chips for GNN models
    4. **Conformal Interval**: Prediction uncertainty range (lower, estimate, upper) with coverage and calibration quality
    5. **Counterfactuals** (CompareArrows icon): 1-3 "If X were Y, decision changes to Z" statements
  - **API**: `GET /planning-cascade/trm-decision/{id}/ask-why?level=NORMAL`, `GET /planning-cascade/gnn-analysis/{config_id}/node/{node_id}/ask-why`
- **Training Configuration Panel**:
  - **Data Source**:
    - Dropdown: Historical Games | SimPy Generated | Custom Dataset
    - If SimPy: Number of runs, timesteps, scenario variety
  - **Hyperparameters**:
    - Epochs: Slider (1-1000)
    - Batch size: Dropdown (16, 32, 64, 128)
    - Learning rate: Input (1e-5 to 1e-1)
    - Device: Toggle (CPU | GPU)
  - **Advanced Options** (collapsible):
    - Optimizer (Adam, SGD, RMSprop)
    - Loss function
    - Regularization (L1, L2, dropout)
  - Start Training button
- **Training Monitor Dashboard**:
  - **Loss Curve Chart**: Line chart (Recharts)
    - X-axis: Epochs
    - Y-axis: Loss (log scale)
    - Lines: Training loss (blue), Validation loss (orange)
  - **Metrics Table**:
    - Epoch
    - Training loss
    - Validation loss
    - Accuracy (if classification)
    - Time per epoch
  - **Live Console**: Scrolling log of training progress
  - Stop button (graceful shutdown)
- **Agent Evaluation Panel**:
  - **Benchmark Results Table**:
    - Agent name
    - Avg total cost
    - Avg service level
    - Bullwhip ratio
    - Cost reduction vs. naive (%)
    - Rank
  - **Performance Chart**: Radar chart
    - Axes: Cost, Service Level, Inventory Turns, Bullwhip, Response Time
    - Compare multiple agents
- **Deployment Panel**:
  - Agent name and description
  - Status: Training | Ready | Deployed | Archived
  - Deploy button → Makes agent available for selection in games/planning
  - Version control (checkpoints)

**Key Visualizations**:
- Training loss curves
- Performance radar chart (agent comparison)
- Benchmark results bar chart
- Confusion matrix (for classification agents)

**Multi-User Interaction**:
- Data Scientist configures and trains agents
- AI Engineer evaluates performance
- Supply Chain Architect deploys to production
- Planners use deployed agents in workflows

**Status**: ✅ TRM implemented ([TRMDashboard.jsx](frontend/src/pages/admin/TRMDashboard.jsx)), GNN implemented ([GNNDashboard.jsx](frontend/src/pages/admin/GNNDashboard.jsx))

---

## Cross-Cutting Concerns

### 18. Analytics & Reporting

**Purpose**: Pre-built and custom reports/dashboards for decision support

**User Roles**: All users (role-specific views)

**Key Dashboards**:
- **Executive Dashboard**:
  - KPI cards (OTIF, Inventory Turns, Cost Variance, Service Level)
  - Trend charts (13-week rolling)
  - Exception alerts
  - Top 10 issues requiring attention
- **Supply Chain Performance Dashboard**:
  - Balanced scorecard (Financial, Customer, Operational, Strategic)
  - Comparative period analysis (YoY, MoM)
  - Drill-down capability
- **Network Health Dashboard**:
  - Node status heat map
  - Lane congestion indicators
  - Inventory coverage map
  - Risk exposure summary

**Report Types**:
- **Standard Reports** (pre-built):
  - Demand Forecast Accuracy Report
  - MPS vs. Actuals Report
  - Supplier Performance Report
  - Inventory Aging Report
  - Order Fulfillment Report
  - Cost Variance Report
- **Custom Reports** (user-defined):
  - Report builder with drag-and-drop
  - Select data source, filters, grouping, sorting
  - Choose visualizations (table, chart types)
  - Schedule and email delivery

**Key Visualizations**:
- Executive KPI dashboard
- Drill-down hierarchy charts
- Period comparison charts
- Report builder interface

**Multi-User Interaction**:
- Executives view high-level dashboards
- Planners drill down to details
- Analysts create custom reports
- System auto-emails scheduled reports

**Status**: 🔄 Partially implemented (various dashboard components exist)

---

### 19. Collaboration & Notifications

**Purpose**: Enable multi-user collaboration with comments, approvals, and notifications

**User Roles**: All users

**Features**:
- **Comment Threads**: On plans, orders, forecasts
- **Approval Workflows**: Submit → Review → Approve/Reject
- **Push Notifications**: Browser, mobile, email
- **Activity Feed**: Recent actions by team members
- **@Mentions**: Tag users in comments
- **File Attachments**: Upload supporting documents

**UI Components**:
- **Comment Panel** (sidebar or modal):
  - Comment thread (chronological)
  - Reply/Quote functionality
  - @Mention dropdown
  - File upload button
  - Submit button
- **Approval Workflow** (stepper):
  - Current status (Draft | Pending | Approved | Rejected)
  - Approver list with status badges
  - Approve/Reject buttons (for approvers)
  - Comment required on rejection
- **Notification Center** (dropdown from bell icon):
  - Unread count badge
  - List of notifications (newest first)
  - Click to navigate to relevant page
  - Mark as read
  - Notification types:
    - Plan approved
    - Order released
    - Exception alert
    - @Mention
    - Task assigned
- **Activity Feed** (sidebar widget):
  - User avatar, action, timestamp
  - Example: "Jane Smith approved MPS Plan Q1-2026"

**Multi-User Interaction**:
- Planner submits plan and @mentions manager
- Manager receives notification
- Manager reviews, adds comment, and approves
- Planner receives notification of approval
- Team sees activity in activity feed

**Status**: 🔄 Partially implemented (notification system exists, collaboration features partial)

---

### 20. System Configuration & Administration

**Purpose**: Configure system settings, manage integrations, monitor health

**User Roles**: System Administrator, IT Operations

**Features**:
- **System Settings**:
  - Time zone, locale, currency
  - Default planning horizons
  - Cost calculation methods
  - Email server (SMTP)
- **Integration Management**:
  - ERP connectors (SAP, Oracle, etc.)
  - Data import/export schedules
  - API keys and webhooks
  - File transfer protocols (SFTP, S3)
- **System Health Monitoring**:
  - Service status (API, database, background jobs)
  - Resource utilization (CPU, memory, disk)
  - Error logs and alerts
  - Audit trail (user actions)

**UI Components**:
- **Settings Tabs**:
  - General | Planning | Costs | Email | Integrations | Security | Audit
- **Integration Manager**:
  - List of configured integrations
  - Add New button
  - Test Connection button
  - Logs/history for each integration
- **System Health Dashboard**:
  - Service status indicators (green/yellow/red)
  - Resource utilization gauges
  - Error log table (sortable by severity)
- **Audit Trail**:
  - User, action, timestamp, IP address, resource
  - Filterable and exportable

**Status**: 🔄 Partially implemented

---

## User Administration

### 21. Group Admin User Management

**Purpose**: Group Admins manage users within their organization and assign granular functional area permissions

**User Roles**: Group Admin, System Admin (for cross-group management)

**Workflow**:
1. **View Users** → List of users in group
2. **Create User** → Add new user with email/password
3. **Assign Capabilities** → Select functional areas user can access
4. **Assign Roles** → Planner, Manager, Viewer, Admin
5. **Manage Roles** → Create custom roles with specific permissions
6. **Deactivate/Reactivate** → Suspend user access
7. **Audit User Activity** → View login history and actions

**Capability-Based Access Control**:

Based on the sidebar screenshot, the following functional area capabilities should be available:

**Strategic Planning**:
- `view_network_design` - View supply chain network
- `manage_network_design` - Create/edit network configurations
- `view_demand_forecasting` - View demand forecasts
- `manage_demand_forecasting` - Create/edit forecasts
- `view_inventory_optimization` - View safety stock policies
- `manage_inventory_optimization` - Configure safety stock policies
- `view_stochastic_planning` - View Monte Carlo results
- `manage_stochastic_planning` - Run stochastic planning

**Tactical Planning**:
- `view_mps` - View Master Production Schedules
- `manage_mps` - Create/edit MPS plans
- `approve_mps` - Approve MPS for execution
- `view_lot_sizing` - View lot sizing analysis
- `manage_lot_sizing` - Run lot sizing optimization
- `view_capacity_check` - View capacity utilization
- `manage_capacity_check` - Run capacity checks
- `view_mrp` - View MRP results
- `manage_mrp` - Run MRP explosion
- `view_supply_planning` - View supply plans
- `manage_supply_planning` - Generate supply plans
- `approve_supply_planning` - Approve supply plans for execution

**Operational Planning**:
- `view_production_orders` - View manufacturing orders
- `manage_production_orders` - Create/release MOs
- `view_purchase_orders` - View purchase orders
- `manage_purchase_orders` - Create/release POs
- `view_transfer_orders` - View transfer orders
- `manage_transfer_orders` - Create/release TOs
- `view_inventory_management` - View inventory levels
- `manage_inventory_management` - Adjust inventory
- `view_atp_ctp` - View ATP/CTP projections
- `run_atp_ctp` - Calculate ATP/CTP

**Execution**:
- `view_order_management` - View customer orders
- `manage_order_management` - Create/edit customer orders
- `view_shipment_tracking` - View shipments
- `manage_shipment_tracking` - Create/edit shipments
- `view_manufacturing_execution` - View shop floor status
- `manage_manufacturing_execution` - Report production
- `view_supplier_management` - View supplier data
- `manage_supplier_management` - Manage supplier relationships

**AI & Agents**:
- `view_ai_agents` - View agent configurations
- `manage_ai_agents` - Configure AI agents
- `train_ai_agents` - Train models
- `deploy_ai_agents` - Deploy agents to production

**Gamification**:
- `view_beer_game` - View games
- `play_beer_game` - Participate in games
- `create_beer_game` - Create new games
- `manage_beer_game` - Configure game settings

**Analytics**:
- `view_analytics` - View dashboards and reports
- `create_custom_reports` - Build custom reports
- `export_data` - Export data to Excel/CSV

**Administration**:
- `view_users` - View user list
- `manage_users` - Create/edit users
- `assign_capabilities` - Grant functional area access
- `manage_roles` - Create custom roles
- `view_audit_logs` - View user activity logs
- `system_config` - Configure system settings

**UI Components**:
- **User List**: Data grid
  - Name, email, role, status (Active/Inactive)
  - Last login timestamp
  - Actions: Edit | Deactivate | Reset Password
- **User Editor** (modal or page):
  - **Profile Tab**:
    - Full name, email, username
    - Password (masked, with "Reset" button)
    - Status toggle (Active/Inactive)
  - **Capabilities Tab**: Checkbox tree
    - **Strategic Planning** (expandable)
      - ☐ Network Design
        - ☐ View
        - ☐ Manage
      - ☐ Demand Forecasting
        - ☐ View
        - ☐ Manage
      - ☐ Inventory Optimization
        - ☐ View
        - ☐ Manage
      - ☐ Stochastic Planning
        - ☐ View
        - ☐ Manage
    - **Tactical Planning** (expandable)
      - ☐ Master Production Schedule
        - ☐ View
        - ☐ Manage
        - ☐ Approve
      - ☐ Lot Sizing Analysis
      - ☐ Capacity Check
      - ☐ MRP (Material Requirements)
        - ☐ View
        - ☐ Manage
      - ☐ Supply Planning
        - ☐ View
        - ☐ Manage
        - ☐ Approve
    - **Operational** (expandable)
      - ☐ Production Orders
      - ☐ Purchase Orders
      - ☐ Transfer Orders
      - ☐ Inventory Management
      - ☐ ATP/CTP Projection
    - **Execution** (expandable)
      - ☐ Order Management
      - ☐ Shipment Tracking
      - ☐ Manufacturing Execution
      - ☐ Supplier Management
    - **AI & Agents** (expandable)
      - ☐ View Agents
      - ☐ Configure Agents
      - ☐ Train Models
      - ☐ Deploy Agents
    - **Select All / Deselect All** buttons at each level
  - **Roles Tab** (optional, for role-based grouping):
    - Pre-defined roles: Supply Chain Planner, Production Manager, Buyer, Warehouse Manager, Analyst, Admin
    - Assign role (automatically checks all capabilities for that role)
  - **Activity Tab**:
    - Recent user actions
    - Login history
- **Role Management** (for Group Admin to create custom roles):
  - Role list with names and user counts
  - Create Role button
  - Role editor (same capability checkbox tree)
  - Assign users to role

**Key Visualizations**:
- User capability matrix (users × capabilities heat map)
- Role assignment pie chart
- User activity timeline
- Login frequency histogram

**Multi-User Interaction**:
- Group Admin creates user accounts
- Group Admin assigns capabilities based on job function
- System Admin (if needed) helps troubleshoot access issues
- Users see only menu items for which they have capabilities
- Audit logs track capability changes

**Implementation Approach**:

**Backend** (Existing RBAC models in `backend/app/models/rbac.py`):
- `Permission` model: Granular permissions (resource.action)
- `Role` model: Collections of permissions
- `user_roles` table: Many-to-many user-role assignments

**Frontend** (New components needed):
- `GroupAdminUserManagement.jsx`: Main user management page
- `UserEditor.jsx`: User creation/editing modal
- `CapabilitySelector.jsx`: Checkbox tree component
- `RoleManager.jsx`: Role creation/editing interface
- `useCapabilities()` hook: Check if current user has a capability
- Sidebar: Use `useCapabilities()` to conditionally render menu items

**Example Integration**:
```jsx
// In Sidebar.jsx
import { useCapabilities } from '../hooks/useCapabilities';

const Sidebar = () => {
  const { hasCapability } = useCapabilities();

  return (
    <>
      {hasCapability('view_mps') && (
        <MenuItem icon={<CalendarIcon />} onClick={() => navigate('/mps')}>
          Master Production Schedule
        </MenuItem>
      )}
      {hasCapability('view_mrp') && (
        <MenuItem icon={<MRPIcon />} onClick={() => navigate('/mrp')}>
          MRP (Material Requirements)
        </MenuItem>
      )}
      {/* ... */}
    </>
  );
};
```

**Status**: 🔄 RBAC models exist, frontend implementation needed

---

## Summary Status

| Functional Area | Backend | Frontend | Status |
|----------------|---------|----------|--------|
| Network Design | ✅ Complete | ✅ Complete | Implemented |
| Demand Forecasting | 🔄 Partial | 🆕 Coming | Planned |
| Inventory Optimization | 🔄 Partial | 🆕 Coming | Planned |
| Stochastic Planning | ✅ Complete | 🔄 Partial | In Progress |
| Master Production Schedule | ✅ Complete | ✅ Complete | Implemented |
| Lot Sizing Analysis | 🔄 Partial | 🔄 Partial | In Progress |
| Capacity Check | 🔄 Partial | 🔄 Partial | In Progress |
| MRP | ✅ Complete | ✅ Complete | Implemented |
| Supply Planning | ✅ Complete | 🔄 Partial | In Progress |
| Production Orders | ✅ Complete | ✅ Complete | Implemented |
| Purchase Orders | ✅ Complete | ✅ Complete | Implemented |
| Transfer Orders | ✅ Complete | ✅ Complete | Implemented |
| Inventory Management | 🔄 Partial | 🆕 Coming | Planned |
| Order Management | 🔄 Partial | 🆕 Coming | Planned |
| Shipment Tracking | 🆕 Planned | 🆕 Coming | Planned |
| ATP/CTP Projection | 🔄 Partial | 🆕 Coming | Planned |
| AI Agent Config | ✅ Complete | ✅ Complete | Implemented |
| Analytics & Reporting | 🔄 Partial | 🔄 Partial | In Progress |
| Collaboration | 🔄 Partial | 🔄 Partial | In Progress |
| User Administration | ✅ Complete | 🔄 Partial | In Progress |

**Legend**:
- ✅ Complete
- 🔄 Partial
- 🆕 Coming (planned)

---

## Next Steps

### Phase 1: Documentation Enhancement (Current)
1. ✅ Create comprehensive UI/UX requirements document (this document)
2. Create detailed workflow diagrams for each functional area
3. Create wireframes/mockups for new pages
4. Document multi-user interaction patterns

### Phase 2: Group Admin User Management (Priority)
1. Implement `GroupAdminUserManagement.jsx` page
2. Implement `CapabilitySelector.jsx` component
3. Implement `useCapabilities()` hook
4. Integrate capability checks into Sidebar navigation
5. Test with multiple user types and permission combinations

### Phase 3: Missing Functional Areas (High Priority)
1. Demand Forecasting UI
2. Inventory Optimization UI
3. Stochastic Planning Results UI (extend existing)
4. Order Management UI
5. ATP/CTP Projection UI
6. Shipment Tracking UI

### Phase 4: Enhancement of Existing Areas (Medium Priority)
1. Enhance Supply Planning UI (complete wizard)
2. Enhance Analytics & Reporting (custom report builder)
3. Enhance Collaboration features (comment threads, @mentions)

### Phase 5: Polish & Integration (Lower Priority)
1. Consistent styling across all pages
2. Responsive design for tablets
3. Accessibility (WCAG 2.1 AA compliance)
4. Performance optimization
5. End-to-end workflow testing

---

## Sources

- [AWS Supply Chain Documentation](https://docs.aws.amazon.com/aws-supply-chain/)
- [Enhanced UI for AWS Supply Chain Demand Planning](https://aws.amazon.com/about-aws/whats-new/2023/07/ui-aws-supply-chain-demand-planning/)
- [AWS Supply Chain Test Drive](https://aws.amazon.com/blogs/supply-chain/aws-supply-chain-test-drive-simplifies-adoption-to-explore-business-benefits/)
- [SAP IBP Integrated Business Planning](https://www.sap.com/products/scm/integrated-business-planning.html)
- [SAP IBP User Interface and Dashboard Features](https://learning.sap.com/learning-journeys/mastering-the-main-features-and-function-in-sap-supply-chain-control-tower/creating-dashboards-and-analytics)
- [Oracle MRP Strategic Guide](https://www.suretysystems.com/insights/oracle-mrp-your-strategic-guide-for-enhanced-planning-efficiency/)
- [Supply Chain Planning Process Flow: MPS, MRP, and DRP](https://www.wolterskluwer.com/en/expert-insights/mps-mrp-drp-help-supply-chains)
- [Microsoft Dynamics 365 DDMRP Overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/ddmrp-overview)

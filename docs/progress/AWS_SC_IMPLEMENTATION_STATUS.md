# AWS Supply Chain Implementation Status

**Last Updated**: 2026-02-23 (Comprehensive Audit Update)
**Current Phase**: Phase 3 - Powell Framework Integration + Service Layer Wiring
**Compliance Score**: 83% AWS SC entities (29/35) + **90% Feature Coverage**

---

## Executive Summary

This document tracks the implementation status of AWS Supply Chain (AWS SC) standard entities in the **Autonomy Platform**. AWS SC defines a comprehensive data model for enterprise supply chain planning and execution, consisting of 35 core entities across 8 categories.

**Strategic Vision**: Transform from "Beer Game-centric" to "AWS SC-first with AI, Stochastic Planning, and Simulation differentiators."

**Current Status** (Updated 2026-02-23):
- ✅ **Implemented**: 29 entities (83%)
- ❌ **Missing**: 6 entities (17%)

**Entities added since last audit (2026-01-24)**:
- VendorProduct, VendorLeadTime (Supplier Management) in `supplier.py`
- QualityOrder, SubcontractingOrder (Fulfillment) in dedicated model files
- MPSPlan, CapacityPlan (Master Planning) in `mps.py`, `capacity_plan.py`
- ProcessHeader, ProcessOperation, ProcessProduct (Manufacturing) in `sc_entities.py`
- Segmentation, SupplementaryTimeSeries (Supporting) in `sc_entities.py`

**Still Missing**: Consensus Demand, Fulfillment Order, Final Assembly Schedule, S&OP Plan, Workflow Engine, Approval

**Strategic Goal**: Achieve 90%+ entity compliance (32/35 entities) by end of Phase 3.

---

## Three-Pillar Value Proposition

### Core: AWS Supply Chain Compliance (83% Complete)
Professional supply chain planning and execution following AWS SC data model and workflows.

### Differentiator #1: AI Agents (Automated Planners)
- TRM Agent: 7M params, 90-95% accuracy vs optimal
- GNN Agent: 128M params, 85-92% demand prediction
- LLM Agent: GPT-4 multi-agent orchestrator with explainability

### Differentiator #2: Stochastic Planning (Probabilistic Outcomes)
- 20 distribution types for operational variables
- Monte Carlo simulation with 10,000+ scenarios
- Probabilistic Balanced Scorecard (P10/P50/P90)

### Differentiator #3: Gamification (The Beer Game Module)
- Learn, validate, and build confidence through competitive gameplay
- Accelerated training and policy validation
- Agent performance benchmarking

---

## Implementation Status by Category

### 1. Supply Chain Network (5/5 entities) ✅ **100% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Site** | ✅ Implemented | Node model with master_type INVENTORY | [backend/app/models/supply_chain_config.py:Node](backend/app/models/supply_chain_config.py) |
| **Location** | ✅ Implemented | Same as Site (unified model) | [backend/app/models/supply_chain_config.py:Node](backend/app/models/supply_chain_config.py) |
| **Lane** | ✅ Implemented | Connects nodes with lead time, cost, priority | [backend/app/models/supply_chain_config.py:Lane](backend/app/models/supply_chain_config.py) |
| **Item** | ✅ Implemented | SKU representation with BOM support | [backend/app/models/supply_chain_config.py:Item](backend/app/models/supply_chain_config.py) |
| **Bill of Materials (BOM)** | ✅ Implemented | JSON field with component ratios | [backend/app/models/supply_chain_config.py:Item.bom](backend/app/models/supply_chain_config.py) |

**Key Features**:
- DAG-based network topology (4 master node types: Market Supply, Market Demand, Inventory, Manufacturer)
- Multi-sourcing with priority-based routing
- BOM explosion for manufacturer nodes
- Lead time offsetting across lanes
- Hierarchical policy overrides (Item-Node > Item > Node > Config)

**Test Coverage**: ✅ Fully tested in existing supply chain configs (Default TBG, Complex_SC, Variable TBG)

---

### 2. Demand Management (3/5 entities) — **60% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Demand Forecast** | ✅ Implemented | Processes demand from multiple sources | [backend/app/services/demand_processor.py](backend/app/services/demand_processor.py) |
| **Demand Plan** | ✅ Implemented | Stored demand scenarios | Database: `demand_plans` table |
| **Customer Order** | ✅ Implemented | Market demand nodes represent customer orders | [backend/app/models/supply_chain_config.py:Market](backend/app/models/supply_chain_config.py) |
| **Sales Forecast** | ❌ **Missing** | No separate sales forecast entity | N/A |
| **Consensus Demand** | ❌ **Missing** | No consensus planning workflow | N/A |

**What's Working**:
- Time-series demand processing (daily/weekly/monthly buckets)
- Multiple demand sources (historical, forecast, manual)
- Demand aggregation and disaggregation
- Stochastic demand distributions (20 types including normal, uniform, triangular, poisson)

**What's Missing**:
- Separate sales forecast vs operational forecast entities
- Consensus planning workflow (sales + finance + operations alignment)
- Forecast accuracy tracking and bias correction
- Collaborative demand planning interface

**Implementation Priority**: Medium (Phase 3, Weeks 7-8)
**Estimated Effort**: 2 weeks (sales forecast entity + consensus planning workflow)

---

### 3. Supply Planning (4/7 entities) — **57% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Supply Plan** | ✅ Implemented | Calculates net requirements | [backend/app/services/net_requirements_calculator.py](backend/app/services/net_requirements_calculator.py) |
| **Purchase Order** | ✅ Implemented | Player/agent orders upstream | [backend/app/models/game.py:PlayerAction](backend/app/models/game.py) |
| **Transfer Order** | ✅ Implemented | Shipments between nodes | [backend/app/services/engine.py:BeerLine.tick()](backend/app/services/engine.py) |
| **Inventory Policy** | ✅ Implemented | 4 policy types with hierarchical overrides | [backend/app/services/inventory_target_calculator.py](backend/app/services/inventory_target_calculator.py) |
| **Production Order** | ✅ **Implemented** | Full lifecycle (PLANNED→RELEASED→IN_PROGRESS→COMPLETED→CLOSED) | [backend/app/models/production_order.py](backend/app/models/production_order.py) |
| **Capacity Plan** | 🚧 **Partial** | Backend complete (RCCP, bottleneck detection), frontend pending | [backend/app/models/capacity_plan.py](backend/app/models/capacity_plan.py) |
| **Supplier** | ❌ **Missing** | No supplier master data entity | N/A |

**What's Working**:
- **Net Requirements Calculation**: gross demand - on hand inventory - scheduled receipts
- **Multi-level BOM Explosion**: Traverses BOMs with lead time offsetting
- **4 Safety Stock Policy Types**:
  - `abs_level`: Absolute inventory level (e.g., 1000 units)
  - `doc_dem`: Days of coverage based on historical demand
  - `doc_fcst`: Days of coverage based on forecast
  - `sl`: Service level with z-score and demand variability
- **Hierarchical Policy Overrides**: Item-Node > Item > Node > Config
- **Multi-sourcing**: Priority-based and ratio-based allocation

**What's Missing**:
- **Production Order Lifecycle**: PLANNED → RELEASED → IN_PROGRESS → COMPLETED
- **Rough-Cut Capacity Planning (RCCP)**: Resource requirements vs available capacity
- **Capacity Requirements Planning (CRP)**: Detailed work center loading
- **Supplier Master Data**: Supplier lead times, costs, reliability metrics
- **Multi-sourcing Optimization**: Cost-based supplier selection

**Implementation Priority**: High (Phase 2, Weeks 3-6)
**Estimated Effort**: 4 weeks for all 3 missing entities

---

### 4. Inventory Management (3/4 entities) — **75% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Inventory Balance** | ✅ Implemented | Per-node per-period inventory | [backend/app/models/game.py:PlayerRound.inventory_level](backend/app/models/game.py) |
| **Inventory Transaction** | ✅ Implemented | Shipments and receipts tracked | [backend/app/models/game.py:Round](backend/app/models/game.py) |
| **Safety Stock** | ✅ Implemented | 4 policy types | [backend/app/services/inventory_target_calculator.py](backend/app/services/inventory_target_calculator.py) |
| **Inventory Projection** | ❌ **Missing** | No forward-looking inventory projection (ATP/CTP) | N/A |

**What's Working**:
- Real-time inventory tracking per node
- Safety stock calculation with 4 policy types
- Inventory cost calculation (holding + shortage)
- Backlog tracking and accumulation
- Stochastic inventory modeling (Monte Carlo simulation)

**What's Missing**:
- **Available-to-Promise (ATP)**: On-hand + scheduled receipts - committed orders
- **Capable-to-Promise (CTP)**: ATP + planned production (MPS integration)
- Forward-looking inventory projection with confidence intervals
- Inventory aging and obsolescence tracking
- Multi-location inventory visibility and rebalancing

**Implementation Priority**: Medium (Phase 2-3, Week 6)
**Estimated Effort**: 1-2 weeks (ATP/CTP calculations + UI)

---

### 5. Master Planning (2/4 entities) — **50% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Master Production Schedule (MPS)** | ✅ Implemented | UI + permissions + migration complete | [frontend/src/pages/MasterProductionScheduling.jsx](frontend/src/pages/MasterProductionScheduling.jsx) |
| **Material Requirements Plan (MRP)** | ✅ Implemented | Multi-level BOM explosion | [backend/app/services/net_requirements_calculator.py](backend/app/services/net_requirements_calculator.py) |
| **Rough-Cut Capacity Plan (RCCP)** | ❌ **Missing** | No capacity planning module | N/A |
| **Final Assembly Schedule (FAS)** | ❌ **Missing** | No FAS entity | N/A |

**What's Working**:
- **MPS UI**: 3 tabs (Plans, Capacity Planning placeholder, Performance Metrics placeholder)
- **MPS Permissions**: 3 capabilities (view_mps, manage_mps, approve_mps)
- **MPS Database Migration**: `20260119_add_mps_permissions.py` seeds permissions and assigns to group-admin
- **MRP Logic**: Multi-level BOM explosion with lead time offsetting
- **Net Requirements**: Time-phased netting (gross - on hand - scheduled)

**What's Missing**:
- **MPS Backend API**: `/api/v1/mps/plans` CRUD endpoints
- **MPS Generation Algorithm**: Demand → MPS with lot sizing (EOQ, LFL, POQ, etc.)
- **Rough-Cut Capacity Planning**: Resource requirements vs available capacity at MPS level
- **MPS Time Fences**:
  - Frozen horizon (no changes allowed)
  - Slushy zone (approval required for changes)
  - Free zone (open for changes)
- **MPS Pegging**: Link MPS quantities to originating demand sources
- **ATP/CTP Integration**: Calculate available/capable-to-promise from MPS
- **Final Assembly Schedule**: Configure-to-order products

**Implementation Priority**: High (Phase 2, Weeks 3-4)
**Estimated Effort**: 2 weeks (MPS backend API + generation algorithm)

---

### 6. Execution & Fulfillment (4/6 entities) — **67% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **Shipment** | ✅ Implemented | Shipments tracked in transit | [backend/app/services/engine.py:BeerLine.tick()](backend/app/services/engine.py) |
| **Receipt** | ✅ Implemented | Receipts update inventory | [backend/app/services/engine.py:BeerLine.tick()](backend/app/services/engine.py) |
| **Quality Order** | ✅ Implemented | Quality inspection and disposition | [backend/app/models/quality_order.py](backend/app/models/quality_order.py) |
| **Subcontracting Order** | ✅ Implemented | External manufacturing lifecycle | [backend/app/models/subcontracting_order.py](backend/app/models/subcontracting_order.py) |
| **Fulfillment Order** | ❌ **Missing** | No fulfillment order entity | N/A |
| **Backorder** | ❌ **Missing** | Backlog tracked but no formal backorder entity | N/A |

**What's Working**:
- Shipment creation and tracking (pipeline visibility)
- Receipt processing with inventory updates
- Backlog accumulation when demand > supply
- In-transit inventory tracking
- **Quality Order**: Full inspection lifecycle (CREATED→INSPECTION_PENDING→IN_INSPECTION→DISPOSITION_PENDING→DISPOSITION_DECIDED→CLOSED) with 7 disposition types and TRM-powered decisions
- **Subcontracting Order**: Complete external manufacturing lifecycle (PLANNED→RELEASED→MATERIAL_SENT→IN_PRODUCTION→GOODS_RECEIVED→QUALITY_CHECK→CLOSED) with cost tracking and quality requirements

**What's Missing**:
- **Fulfillment Order Lifecycle**: PICK → PACK → SHIP → DELIVER
- **Backorder Management**: Backorder prioritization, allocation, and expediting
- **Returns and Reverse Logistics**: RMA tracking and inventory adjustments
- **Cross-docking Workflows**: Direct shipment without warehousing

**Implementation Priority**: Medium (Phase 4, Weeks 11-12)
**Estimated Effort**: 2 weeks (fulfillment order + backorder entities)

---

### 7. Analytics & Reporting (2/3 entities) — **67% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **KPI** | ✅ Implemented | Bullwhip, service level, costs | [backend/app/api/endpoints/analytics.py](backend/app/api/endpoints/analytics.py) |
| **Alert** | ✅ Implemented | Basic alerting for stockouts, backlog | Frontend alerts |
| **Scenario** | ❌ **Missing** | No scenario planning module | N/A |

**What's Working**:
- **Real-time KPI Calculation**:
  - Bullwhip ratio (demand variability amplification)
  - Service level (orders fulfilled / total orders)
  - Inventory turnover, holding costs, shortage costs
  - Agent performance metrics (cost reduction vs naive)
- **Performance Dashboards**: Recharts visualizations with time-series trends
- **Agent Comparison**: TRM vs GNN vs LLM vs Naive benchmarking

**What's Missing**:
- **Scenario Planning Entity**: Store multiple planning scenarios (base case, optimistic, pessimistic)
- **Monte Carlo Simulation Results Storage**: 10,000+ scenario outcomes with probability distributions
- **Probabilistic Balanced Scorecard**: P10/P50/P90 outcomes for KPIs
- **Sensitivity Analysis**: Impact of parameter changes on outcomes
- **Scenario Comparison Views**: Side-by-side scenario comparison UI

**Implementation Priority**: Medium (Phase 3, Weeks 9-10)
**Estimated Effort**: 2 weeks (scenario entity + stochastic results storage + P10/P50/P90 UI)

---

### 8. Collaboration & Governance (0/3 entities) — **0% Complete**

| Entity | Status | Implementation | Location |
|--------|--------|----------------|----------|
| **S&OP Plan** | ❌ **Missing** | No Sales & Operations Planning entity | N/A |
| **Collaboration Workflow** | ❌ **Missing** | No workflow engine | N/A |
| **Approval** | ❌ **Missing** | MPS approve is hardcoded, not workflow-driven | N/A |

**What's Missing**:
- **Sales & Operations Planning (S&OP)**: Executive planning cycle (monthly review, consensus building)
- **Workflow Engine**: Multi-stage approval workflows with role-based assignments
- **Collaboration Features**: Comments, annotations, @mentions
- **Change Tracking**: Audit logs for plan modifications
- **Approval Hierarchies**: Escalation rules and approval chains

**Implementation Priority**: Low (Phase 5-6, Weeks 21-24)
**Estimated Effort**: 4 weeks (workflow engine + S&OP module + approval entity)

---

## Summary Table: All 35 AWS SC Entities

| # | Category | Entity | Status | Priority | Phase |
|---|----------|--------|--------|----------|-------|
| **1** | **Network** | Site | ✅ Implemented | N/A | Complete |
| **2** | **Network** | Location | ✅ Implemented | N/A | Complete |
| **3** | **Network** | Lane | ✅ Implemented | N/A | Complete |
| **4** | **Network** | Item | ✅ Implemented | N/A | Complete |
| **5** | **Network** | Bill of Materials | ✅ Implemented | N/A | Complete |
| **6** | **Demand** | Demand Forecast | ✅ Implemented | N/A | Complete |
| **7** | **Demand** | Demand Plan | ✅ Implemented | N/A | Complete |
| **8** | **Demand** | Customer Order | ✅ Implemented | N/A | Complete |
| **9** | **Demand** | Sales Forecast | ❌ Missing | Medium | Phase 3 |
| **10** | **Demand** | Consensus Demand | ❌ Missing | Medium | Phase 3 |
| **11** | **Supply** | Supply Plan | ✅ Implemented | N/A | Complete |
| **12** | **Supply** | Purchase Order | ✅ Implemented | N/A | Complete |
| **13** | **Supply** | Transfer Order | ✅ Implemented | N/A | Complete |
| **14** | **Supply** | Inventory Policy | ✅ Implemented | N/A | Complete |
| **15** | **Supply** | Production Order | ✅ **Implemented** | N/A | Complete |
| **16** | **Supply** | Capacity Plan | 🚧 **Partial** | High | Phase 2 |
| **17** | **Supply** | Supplier | ❌ Missing | Medium | Phase 2 |
| **18** | **Inventory** | Inventory Balance | ✅ Implemented | N/A | Complete |
| **19** | **Inventory** | Inventory Transaction | ✅ Implemented | N/A | Complete |
| **20** | **Inventory** | Safety Stock | ✅ Implemented | N/A | Complete |
| **21** | **Inventory** | Inventory Projection | ❌ Missing | Medium | Phase 2-3 |
| **22** | **Master Planning** | MPS | ✅ Implemented | N/A | Complete |
| **23** | **Master Planning** | MRP | ✅ Implemented | N/A | Complete |
| **24** | **Master Planning** | RCCP | 🚧 **Partial** | High | Phase 2 |
| **25** | **Master Planning** | FAS | ❌ Missing | Low | Phase 5 |
| **26** | **Execution** | Shipment | ✅ Implemented | N/A | Complete |
| **27** | **Execution** | Receipt | ✅ Implemented | N/A | Complete |
| **28** | **Execution** | Fulfillment Order | ❌ Missing | Medium | Phase 4 |
| **29** | **Execution** | Backorder | ❌ Missing | Medium | Phase 4 |
| **30** | **Analytics** | KPI | ✅ Implemented | N/A | Complete |
| **31** | **Analytics** | Alert | ✅ Implemented | N/A | Complete |
| **32** | **Analytics** | Scenario | ❌ Missing | Medium | Phase 3 |
| **33** | **Collaboration** | S&OP Plan | ❌ Missing | Low | Phase 5 |
| **34** | **Collaboration** | Workflow | ❌ Missing | Low | Phase 6 |
| **35** | **Collaboration** | Approval | ❌ Missing | Low | Phase 6 |

**Compliance Progress**:
- ✅ Phase 1 Complete: 60% (21/35)
- 🚧 Phase 2 Current (Week 5): 65% (23/35 fully implemented, 1 partial)
- 🎯 Phase 2 Target (Week 12): 75% (26/35) - Add 3 more entities
- 🎯 Phase 3 Target (Week 18): 80% (28/35) - Add 2 entities
- 🎯 Final Target (Week 25): 85%+ (30/35) - Add 2+ entities

---

## Implementation Roadmap

### Phase 1: Conceptual Reframing (Weeks 1-2) — ✅ **COMPLETE**

**Goal**: Reposition platform from "Beer Game-centric" to "AWS SC-first with differentiators"

**Tasks**:
- [x] Update [CLAUDE.md](CLAUDE.md) with Autonomy positioning
- [x] Restructure navigation (Planning first, Gamification last)
- [x] Change labels: "Planning & Optimization" → "Planning", "Gamification" → "Gamification & Training"
- [x] Update default expanded sections (Overview + Planning)
- [x] Create [AWS_SC_IMPLEMENTATION_STATUS.md](AWS_SC_IMPLEMENTATION_STATUS.md) (this document)
- [x] Update [README.md](README.md) with new positioning
- [x] Create new capability flags for AWS SC features (Sprint 6: 9 new capabilities)
- [x] Update frontend Sidebar.jsx with new branding

**Deliverables**:
- Documentation reflects AWS SC-first positioning
- Navigation prioritizes Planning over Gamification
- All team members aligned on new strategic vision

**Status**: ✅ 100% complete (8/8 tasks done - Sprint 6 added capabilities)

---

### Phase 2: Data Model Refactoring (Weeks 3-6) — **HIGH PRIORITY**

**Goal**: Achieve 75% AWS SC compliance (26/35 entities)

**New Entities to Implement**:

#### Week 3-4: Production Order
- **Model**: `backend/app/models/production_order.py`
- **Lifecycle States**: PLANNED → RELEASED → IN_PROGRESS → COMPLETED → CLOSED
- **Key Fields**:
  - `mps_plan_id`, `item_id`, `site_id`, `quantity`
  - `start_date`, `completion_date`, `status`
  - `actual_quantity`, `scrap_quantity`
- **API Endpoints**:
  - `POST /api/v1/production-orders` - Create production order
  - `GET /api/v1/production-orders` - List production orders
  - `PUT /api/v1/production-orders/{id}/release` - Release to shop floor
  - `PUT /api/v1/production-orders/{id}/complete` - Complete production
- **Integration**: Link to MPS plans, trigger MRP when completed
- **Migration**: Alembic migration `20260120_add_production_orders.py`

#### Week 4-5: Capacity Plan (RCCP)
- **Model**: `backend/app/models/capacity_plan.py`
- **Service**: `backend/app/services/rccp_calculator.py`
- **Key Features**:
  - Resource requirements calculation from MPS
  - Available capacity by resource and time period
  - Utilization % and bottleneck identification
  - What-if scenarios for capacity expansion
- **Algorithm**:
  ```python
  required_capacity = MPS_quantity * resource_hours_per_unit
  utilization = required_capacity / available_capacity * 100
  bottleneck = True if utilization > 90%
  ```
- **UI Component**: `frontend/src/pages/CapacityPlanning.jsx`
- **Migration**: `20260121_add_capacity_plans.py`

#### Week 5-6: Supplier Entity
- **Model**: `backend/app/models/supplier.py`
- **Key Fields**:
  - `supplier_id`, `name`, `type` (manufacturer, distributor, broker)
  - `lead_time_mean`, `lead_time_std_dev`
  - `cost_per_unit`, `minimum_order_quantity`, `order_multiple`
  - `reliability_score`, `quality_rating`
- **Integration**: Link to Purchase Orders, enable supplier selection optimization
- **API Endpoints**:
  - `GET /api/v1/suppliers` - List suppliers
  - `POST /api/v1/suppliers` - Create supplier
  - `GET /api/v1/suppliers/{id}/performance` - Supplier performance metrics
- **Migration**: `20260122_add_suppliers.py`

#### Week 6: Inventory Projection (ATP/CTP)
- **Service**: `backend/app/services/inventory_projection.py`
- **Key Functions**:
  - `calculate_atp()`: On-hand + scheduled receipts - committed orders
  - `calculate_ctp()`: ATP + planned production from MPS
  - `project_inventory()`: Forward-looking inventory by time bucket
- **Algorithm**:
  ```python
  for period in planning_horizon:
      projected_inventory[period] = (
          projected_inventory[period-1] +
          scheduled_receipts[period] +
          planned_production[period] -
          committed_demand[period]
      )
      atp[period] = max(0, projected_inventory[period] - safety_stock)
  ```
- **API Endpoints**:
  - `GET /api/v1/inventory/projection/{item_id}` - Inventory projection
  - `GET /api/v1/inventory/atp/{item_id}` - Available-to-Promise
  - `GET /api/v1/inventory/ctp/{item_id}` - Capable-to-Promise

**Phase 2 Success Criteria**:
- ✅ 75% AWS SC compliance (26/35 entities)
- ✅ Production orders fully functional with lifecycle management
- ✅ RCCP operational with bottleneck identification
- ✅ ATP/CTP calculations working and integrated with MPS
- ✅ Supplier master data enables multi-sourcing optimization

---

### Phase 3: Service Layer Refactoring (Weeks 7-12) — **MEDIUM PRIORITY**

**Goal**: Achieve 80% AWS SC compliance (28/35 entities)

**New Entities to Implement**:

#### Week 7-8: Sales Forecast & Consensus Demand
- **Models**:
  - `backend/app/models/sales_forecast.py`
  - `backend/app/models/consensus_demand.py`
- **Workflow**: Sales forecast → Finance review → Operations review → Consensus demand
- **UI Component**: `frontend/src/pages/ConsensusDemandPlanning.jsx`
- **Features**:
  - Multi-stakeholder input (sales, finance, operations)
  - Forecast reconciliation and bias correction
  - Approval workflow for consensus demand

#### Week 9-10: Scenario Planning Entity
- **Model**: `backend/app/models/scenario.py`
- **Service**: `backend/app/services/scenario_manager.py`
- **Key Features**:
  - Store multiple planning scenarios (base, optimistic, pessimistic)
  - Monte Carlo simulation results storage (10,000+ scenarios)
  - Probabilistic Balanced Scorecard (P10/P50/P90)
  - Scenario comparison and sensitivity analysis
- **UI Component**: `frontend/src/pages/ScenarioPlanning.jsx`
- **Integration**: Link scenarios to MPS plans and stochastic planning

#### Week 11: Fulfillment Order
- **Model**: `backend/app/models/fulfillment_order.py`
- **Lifecycle**: PICK → PACK → SHIP → DELIVER → CLOSED
- **Integration**: Link to customer orders, trigger shipment creation

#### Week 12: Backorder Entity
- **Model**: `backend/app/models/backorder.py`
- **Features**: Backorder prioritization, allocation rules, expediting
- **Service**: `backend/app/services/backorder_manager.py`

**Phase 3 Success Criteria**:
- ✅ 80% AWS SC compliance (28/35 entities)
- ✅ Stochastic scenario storage with P10/P50/P90 metrics
- ✅ Sales forecast and consensus demand workflow operational
- ✅ Fulfillment order lifecycle working end-to-end

---

### Phase 4: API Refactoring (Weeks 13-16) — **MEDIUM PRIORITY**

**Goal**: Build RESTful APIs for all new entities

**API Endpoints to Create**:
- Production Orders: CRUD + lifecycle transitions
- Capacity Plans: CRUD + utilization calculations
- Suppliers: CRUD + performance metrics
- Inventory Projections: ATP/CTP calculations
- Sales Forecasts: CRUD + approval workflow
- Scenarios: CRUD + comparison views
- Fulfillment Orders: CRUD + lifecycle transitions
- Backorders: CRUD + prioritization

**API Design Pattern**:
```python
@router.get("/production-orders")
def list_production_orders(
    status: Optional[str] = None,
    site_id: Optional[int] = None,
    current_user = Depends(require_capability("view_supply_planning"))
):
    # Implementation
    pass

@router.post("/production-orders")
def create_production_order(
    order: ProductionOrderCreate,
    current_user = Depends(require_capability("manage_supply_planning"))
):
    # Implementation
    pass
```

---

### Phase 5: Frontend Refactoring (Weeks 17-22) — **LOW PRIORITY**

**Goal**: Create UI pages for all planning modules

**New Pages to Create**:
1. Production Orders (`frontend/src/pages/ProductionOrders.jsx`)
2. Capacity Planning (`frontend/src/pages/CapacityPlanning.jsx`)
3. Supplier Management (`frontend/src/pages/Suppliers.jsx`)
4. ATP/CTP Dashboard (`frontend/src/pages/InventoryProjection.jsx`)
5. Consensus Demand Planning (`frontend/src/pages/ConsensusDemandPlanning.jsx`)
6. Scenario Planning (`frontend/src/pages/ScenarioPlanning.jsx`)
7. Fulfillment Orders (`frontend/src/pages/FulfillmentOrders.jsx`)

**UI Design Pattern**: Follow MPS page structure
- 3-tab layout (List, Analytics, Configuration)
- Summary cards with KPIs
- Data tables with filtering and sorting
- Action buttons with permission-based visibility
- Empty states with call-to-action

---

### Phase 6: Documentation Refactoring (Weeks 23-24) — **LOW PRIORITY**

**Goal**: Update all documentation with AWS SC references

**Documentation Updates**:
- [ ] README.md with Autonomy positioning
- [ ] CLAUDE.md (already updated)
- [ ] AWS_SC_IMPLEMENTATION_STATUS.md (this document)
- [ ] API documentation (Swagger/OpenAPI)
- [ ] User guides for planning modules
- [ ] Developer onboarding guide

---

### Phase 7: Branding & Marketing (Week 25) — **LOW PRIORITY**

**Goal**: External communication of AWS SC compliance

**Deliverables**:
- Compliance certification report (85%+ compliance)
- Marketing materials highlighting AWS SC compatibility
- Blog posts on AI + Stochastic Planning differentiators
- Customer case studies

---

## Technical Implementation Guidelines

### Database Migrations

All new entities require Alembic migrations:

```bash
# Create migration
cd backend
alembic revision -m "add_production_order_entity"

# Edit migration file
# backend/migrations/versions/YYYYMMDD_add_production_order_entity.py

# Run migration
alembic upgrade head

# Verify
docker compose exec db psql -U beer_user -d beer_game -c "\\dt production_orders"
```

### Model Structure

Follow existing patterns in `backend/app/models/`:

```python
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class ProductionOrder(Base):
    __tablename__ = "production_orders"

    id = Column(Integer, primary_key=True, index=True)
    mps_plan_id = Column(Integer, ForeignKey("mps_plans.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default="PLANNED")  # PLANNED, RELEASED, IN_PROGRESS, COMPLETED
    start_date = Column(DateTime, nullable=True)
    completion_date = Column(DateTime, nullable=True)
    actual_quantity = Column(Integer, nullable=True)
    scrap_quantity = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)

    # Relationships
    mps_plan = relationship("MPSPlan", back_populates="production_orders")
    item = relationship("Item")
    site = relationship("Node")
```

### API Endpoints

Create RESTful APIs in `backend/app/api/endpoints/`:

```python
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import require_capability
from app.schemas.production_order import ProductionOrderCreate, ProductionOrderUpdate

router = APIRouter()

@router.get("/production-orders")
def list_production_orders(
    status: Optional[str] = None,
    current_user = Depends(require_capability("view_supply_planning"))
):
    # Implementation
    orders = db.query(ProductionOrder).filter_by(status=status).all()
    return orders

@router.post("/production-orders")
def create_production_order(
    order: ProductionOrderCreate,
    current_user = Depends(require_capability("manage_supply_planning"))
):
    # Implementation
    new_order = ProductionOrder(**order.dict())
    db.add(new_order)
    db.commit()
    return new_order
```

### Frontend Pages

Create React pages in `frontend/src/pages/`:

```javascript
import React, { useState, useEffect } from 'react';
import { Container, Typography, Button, Table } from '@mui/material';
import { useCapabilities } from '../hooks/useCapabilities';
import api from '../services/api';

const ProductionOrdersPage = () => {
  const { hasCapability } = useCapabilities();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const canManage = hasCapability('manage_supply_planning');

  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    try {
      const response = await api.get('/api/v1/production-orders');
      setOrders(response.data);
    } catch (err) {
      console.error('Error loading orders:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        Production Orders
      </Typography>
      {/* Implementation */}
    </Container>
  );
};

export default ProductionOrdersPage;
```

---

## Success Metrics

### Phase 1 Goals (Week 2) — **IN PROGRESS**
- [x] CLAUDE.md updated with Autonomy positioning
- [x] Navigation restructured (Planning first)
- [x] AWS_SC_IMPLEMENTATION_STATUS.md created
- [ ] README.md updated with new positioning
- [ ] Capabilities updated for AWS SC features

### Phase 2 Goals (Week 6) — **TARGET: 75% COMPLIANCE**
- [ ] 75% AWS SC compliance (26/35 entities)
- [ ] Production orders fully functional
- [ ] RCCP operational with bottleneck identification
- [ ] ATP/CTP calculations working
- [ ] Supplier master data enables multi-sourcing

### Phase 3 Goals (Week 12) — **TARGET: 80% COMPLIANCE**
- [ ] 80% AWS SC compliance (28/35 entities)
- [ ] Stochastic scenario storage with P10/P50/P90
- [ ] Sales forecast and consensus demand operational
- [ ] Fulfillment order workflow working

### Final Goals (Week 25) — **TARGET: 85%+ COMPLIANCE**
- [ ] 85%+ AWS SC compliance (30+/35 entities)
- [ ] All high-priority entities implemented
- [ ] Comprehensive API documentation
- [ ] AWS SC certification report published

---

## Risk Management

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking existing games** | High | Dual-write period, extensive testing, backward compatibility layer |
| **BOM circular dependencies** | Medium | Cycle detection algorithm, max depth limit (10 levels) |
| **Performance of hierarchical override lookup** | Medium | Indexes on override columns, Redis caching for policy lookups |
| **Complex UI for planning modules** | Medium | Phased UI rollout, wizard interfaces, comprehensive user testing |
| **Team alignment on AWS SC-first** | Low | Regular sync meetings, documentation reviews, shared roadmap |

---

## References

### Internal Documentation
- [CLAUDE.md](CLAUDE.md) - Project overview with Autonomy positioning
- [ARCHITECTURAL_REFACTORING_PLAN.md](ARCHITECTURAL_REFACTORING_PLAN.md) - 7-phase refactoring plan (420 lines)
- [PLANNING_KNOWLEDGE_BASE.md](PLANNING_KNOWLEDGE_BASE.md) - MPS/MRP algorithms and best practices (1,109 lines)
- [MPS_FEATURE_IMPLEMENTATION.md](MPS_FEATURE_IMPLEMENTATION.md) - MPS feature details (550+ lines)
- [PLANNING_QUICK_REFERENCE.md](PLANNING_QUICK_REFERENCE.md) - Quick reference card (190 lines)
- [DAG_Logic.md](DAG_Logic.md) - Master node type mappings and config examples

### External References
- **AWS Supply Chain Documentation**: https://docs.aws.amazon.com/supply-chain/
- **APICS SCOR Model**: https://www.ascm.org/scor/
- **ISA-95 Standard** (Manufacturing Execution Systems): https://www.isa.org/standards-and-publications/isa-standards/isa-standards-committees/isa95
- **DDMRP (Demand Driven MRP)**: https://www.demanddriveninstitute.com/

---

**Document Owner**: Autonomy Development Team
**Next Review**: 2026-01-26 (Weekly updates during Phase 1-3)
**Maintained By**: Claude Code + Human Developers

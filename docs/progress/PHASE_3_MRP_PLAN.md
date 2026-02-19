# Phase 3: Material Requirements Planning (MRP) Implementation Plan

**Date**: January 20, 2026
**Phase**: 3 of 7 (Architectural Refactoring)
**Focus**: MRP Implementation + Supply Planning Integration
**Duration Estimate**: 3-4 weeks
**Status**: 🎯 **READY TO START**

---

## Overview

Phase 3 implements **Material Requirements Planning (MRP)**, the natural next step after MPS (Phase 2). MRP explodes MPS plans into detailed component requirements using Bill of Materials (BOM), calculates time-phased material needs, and generates purchase orders, transfer orders, and manufacturing orders.

**MRP Relationship to MPS**:
```
MPS (Phase 2)
  ↓ (BOM Explosion)
MRP (Phase 3)
  ↓ (Procurement/Manufacturing)
Production Orders (Completed)
```

---

## Phase 3 Objectives

### Primary Goals

1. **MRP Core Engine** ✅ (Already partially implemented)
   - Time-phased netting
   - Multi-level BOM explosion
   - Lead time offsetting
   - Lot sizing for components
   - Sourcing rule processing

2. **MRP UI/Frontend**
   - MRP Run page (trigger MRP from MPS)
   - MRP Results page (view planned orders)
   - Exception handling and alerts
   - Pegging/Where-Used traceability

3. **Integration with MPS**
   - Automatic MRP triggering after MPS approval
   - MPS → MRP → Production Orders flow
   - Real-time status updates

4. **Supply Planning Enhancement**
   - Purchase Order generation
   - Transfer Order generation
   - Manufacturing Order generation
   - Supplier selection logic

---

## What Already Exists (From Phase 2)

### Backend Services ✅

1. **[backend/app/services/aws_sc_planning/net_requirements_calculator.py](backend/app/services/aws_sc_planning/net_requirements_calculator.py)**
   - `NetRequirementsCalculator` class
   - Time-phased netting logic
   - Multi-level BOM explosion
   - Lead time offsetting
   - Sourcing rule processing (buy/transfer/manufacture)
   - Generates `SupplyPlan` entries

2. **[backend/app/services/aws_sc_planning/planner.py](backend/app/services/aws_sc_planning/planner.py)**
   - `AWSSupplyChainPlanner` orchestrator
   - 3-step process: Demand → Targets → Requirements
   - Step 3 calls `NetRequirementsCalculator`

3. **Database Models**:
   - `SupplyPlan` - Generated supply plans (PO/TO/MO requests)
   - `ProductBOM` - Bill of materials
   - `SourcingRules` - Buy/transfer/manufacture rules
   - `VendorProduct`, `VendorLeadTime` - Supplier data

### What's Missing

1. **MRP UI**:
   - No MRP run page
   - No MRP results page
   - No exception management UI
   - No pegging/traceability UI

2. **MRP-specific API Endpoints**:
   - Run MRP for MPS plan
   - View MRP results
   - Handle exceptions
   - Approve/reject planned orders

3. **Integration Features**:
   - Automatic MRP trigger after MPS approval
   - Status tracking (MPS → MRP → Orders)
   - Real-time progress updates

4. **Order Generation**:
   - Convert SupplyPlan to PurchaseOrder
   - Convert SupplyPlan to TransferOrder
   - Already have ProductionOrder generation ✅

---

## Implementation Plan

### Sprint 1: MRP API Endpoints (3-5 days)

**Goal**: Create backend API for MRP operations

**Tasks**:

1. **MRP Run Endpoint** (1 day)
   - `POST /api/v1/mrp/plans/{mps_plan_id}/run`
   - Triggers MRP for approved MPS plan
   - Calls `AWSSupplyChainPlanner` Step 3
   - Returns `SupplyPlan` entries
   - Async with progress tracking

2. **MRP Results Endpoint** (1 day)
   - `GET /api/v1/mrp/plans/{mps_plan_id}/results`
   - Returns planned orders grouped by type (PO/TO/MO)
   - Filters: order type, item, supplier, due date
   - Pagination support

3. **MRP Exception Endpoint** (1 day)
   - `GET /api/v1/mrp/plans/{mps_plan_id}/exceptions`
   - Identifies issues:
     - Late orders (past due date)
     - No sourcing rule found
     - Insufficient capacity
     - No supplier available

4. **Order Generation Endpoints** (2 days)
   - `POST /api/v1/mrp/supply-plans/{id}/generate-po` - Create Purchase Order
   - `POST /api/v1/mrp/supply-plans/{id}/generate-to` - Create Transfer Order
   - `POST /api/v1/mrp/supply-plans/bulk-generate` - Bulk order creation

**Deliverables**:
- 5 new API endpoints
- Schemas for MRP requests/responses
- Integration with existing planner service

### Sprint 2: MRP UI Pages (4-6 days)

**Goal**: Create frontend interface for MRP

**Tasks**:

1. **MRP Run Page** (2 days)
   - Path: `/planning/mrp/run`
   - Select MPS plan dropdown
   - "Run MRP" button with options:
     - Full regeneration vs net change
     - Planning horizon override
     - Exception handling mode
   - Progress indicator during execution
   - Results summary after completion

2. **MRP Results Page** (2 days)
   - Path: `/planning/mrp/results/{mps_plan_id}`
   - Three tabs:
     - **Purchase Orders** (external procurement)
     - **Transfer Orders** (internal moves)
     - **Manufacturing Orders** (production)
   - Table for each type with:
     - Order number, Item, Quantity, Due Date, Supplier/Source, Status
   - Summary cards: Total orders, Total qty, Total cost
   - Filter panel: Order type, Item, Supplier, Date range
   - Bulk actions: Generate, Approve, Reject

3. **MRP Exceptions Page** (1 day)
   - Path: `/planning/mrp/exceptions/{mps_plan_id}`
   - Alert list with severity levels:
     - **Critical**: No sourcing rule, No capacity
     - **Warning**: Late order, Low inventory
     - **Info**: Expedite recommended
   - Resolution actions for each exception
   - Auto-refresh on MRP run

4. **MPS → MRP Integration** (1 day)
   - Add "Run MRP" button to MPS page (for APPROVED plans)
   - Confirmation dialog
   - Navigate to MRP Results after completion

**Deliverables**:
- 3 new pages (Run, Results, Exceptions)
- Integration with MPS page
- ~1,200 lines of React code

### Sprint 3: Order Generation & Integration (3-4 days)

**Goal**: Complete end-to-end MPS → MRP → Orders flow

**Tasks**:

1. **Purchase Order Generation** (1 day)
   - Backend: Create PurchaseOrder from SupplyPlan
   - Model: PurchaseOrder entity (if not exists)
   - API: `POST /api/v1/purchase-orders`
   - Fields: vendor, item, quantity, due date, price

2. **Transfer Order Generation** (1 day)
   - Backend: Create TransferOrder from SupplyPlan
   - Model: TransferOrder entity (if not exists)
   - API: `POST /api/v1/transfer-orders`
   - Fields: from_site, to_site, item, quantity, ship date

3. **Bulk Order Generation** (1 day)
   - UI: "Generate All Orders" button on MRP Results page
   - Backend: Bulk create PO/TO/MO from SupplyPlan
   - Progress tracking with WebSocket
   - Summary dialog after completion

4. **Status Tracking** (1 day)
   - MPS Plan status: DRAFT → APPROVED → MRP_RUNNING → MRP_COMPLETE → ORDERS_GENERATED
   - Status chips on MPS page
   - Status timeline view
   - Automatic state transitions

**Deliverables**:
- PurchaseOrder and TransferOrder models/APIs
- Bulk order generation
- End-to-end status tracking

### Sprint 4: Testing & Polish (2-3 days)

**Goal**: Validate MRP functionality and polish UX

**Tasks**:

1. **Integration Tests** (1 day)
   - End-to-end test: MPS → MRP → Orders
   - Test multi-level BOM explosion (3+ levels)
   - Test sourcing rule priorities
   - Test lead time offsetting

2. **UI Polish** (1 day)
   - Loading states and error handling
   - Empty states and placeholders
   - Responsive design verification
   - Accessibility improvements

3. **Documentation** (1 day)
   - MRP user guide
   - API documentation
   - BOM setup guide
   - Sourcing rules configuration guide

**Deliverables**:
- Integration test suite
- Polished UI
- Comprehensive documentation

---

## Technical Architecture

### MRP Data Flow

```
MPS Plan (APPROVED)
  ↓
Trigger MRP Run
  ↓
AWS Supply Chain Planner
  ├─ Step 1: Demand Aggregation (from MPS items)
  ├─ Step 2: Inventory Targets (safety stock)
  └─ Step 3: Net Requirements Calculator
      ├─ Time-phased netting (gross - on-hand - scheduled)
      ├─ Multi-level BOM explosion (recursive)
      ├─ Lead time offsetting (due date - lead time)
      ├─ Lot sizing (for components)
      └─ Sourcing rule processing (buy/transfer/make)
  ↓
SupplyPlan Entries Created
  ├─ Type: PURCHASE (external procurement)
  ├─ Type: TRANSFER (internal move)
  └─ Type: MANUFACTURE (production)
  ↓
User Reviews MRP Results
  ↓
Generate Orders (bulk or individual)
  ├─ PURCHASE → PurchaseOrder
  ├─ TRANSFER → TransferOrder
  └─ MANUFACTURE → ProductionOrder ✅ (already implemented)
  ↓
Orders Executed in System
```

### Database Schema

**Already Exists**:
- `supply_plans` - Planned orders from MRP
- `product_bom` - Bill of materials
- `sourcing_rules` - Buy/transfer/manufacture rules
- `production_orders` - Manufacturing orders ✅

**Need to Create**:
- `purchase_orders` - External procurement orders
- `transfer_orders` - Internal movement orders
- `mrp_runs` - Track MRP execution history
- `mrp_exceptions` - Track planning issues

### API Endpoints Summary

**New Endpoints** (5):
1. `POST /api/v1/mrp/plans/{mps_plan_id}/run` - Execute MRP
2. `GET /api/v1/mrp/plans/{mps_plan_id}/results` - View results
3. `GET /api/v1/mrp/plans/{mps_plan_id}/exceptions` - View exceptions
4. `POST /api/v1/purchase-orders` - Create purchase order
5. `POST /api/v1/transfer-orders` - Create transfer order

**Enhanced Endpoints**:
- `POST /api/v1/mrp/supply-plans/bulk-generate` - Bulk order creation

---

## User Stories

### Story 1: Run MRP from MPS Plan

**As a** Supply Planner
**I want to** run MRP after approving an MPS plan
**So that** I can see detailed component requirements

**Acceptance Criteria**:
- [x] "Run MRP" button appears on APPROVED MPS plans
- [x] Confirmation dialog shows MRP options
- [x] Progress indicator during MRP execution
- [x] Navigate to MRP Results page after completion
- [x] MPS status updates to MRP_COMPLETE

### Story 2: Review MRP Results

**As a** Material Planner
**I want to** review planned orders by type (PO/TO/MO)
**So that** I can validate procurement needs

**Acceptance Criteria**:
- [x] Three tabs for order types
- [x] Summary cards show totals
- [x] Filters work correctly
- [x] Can view order details
- [x] Can navigate to source MPS plan

### Story 3: Handle MRP Exceptions

**As a** Supply Chain Manager
**I want to** see MRP exceptions with severity levels
**So that** I can resolve planning issues

**Acceptance Criteria**:
- [x] Exceptions page shows critical/warning/info alerts
- [x] Each exception has resolution actions
- [x] Can filter by severity
- [x] Auto-refreshes after MRP run

### Story 4: Generate Orders from MRP

**As a** Procurement Manager
**I want to** generate purchase/transfer orders from MRP results
**So that** I can execute the supply plan

**Acceptance Criteria**:
- [x] "Generate All Orders" button creates orders in bulk
- [x] Progress indicator during generation
- [x] Summary dialog shows created orders
- [x] Can view orders in respective modules

---

## Success Metrics

### Functional Metrics
- **MRP Execution Time**: <5 seconds for 1000 items, 3-level BOM
- **Order Generation**: <10 seconds for 500 orders
- **Exception Detection**: 100% coverage of known issues
- **Data Accuracy**: 100% match between MRP and manual calculation

### User Experience Metrics
- **Time to Complete MRP**: <2 minutes (vs 30+ minutes manual)
- **Error Rate**: <1% of MRP runs fail
- **User Satisfaction**: 4.5/5 stars
- **Adoption Rate**: 80% of planners use MRP within 1 month

---

## Risks & Mitigation

### Risk 1: Performance with Large BOMs
**Risk**: MRP slow for complex BOMs (10+ levels, 10,000+ items)
**Mitigation**:
- Implement BOM caching
- Use async processing with progress updates
- Add database indexes on key fields

### Risk 2: Data Quality Issues
**Risk**: Incomplete BOMs or sourcing rules cause MRP failures
**Mitigation**:
- Validation before MRP run
- Clear error messages
- Exception management UI

### Risk 3: Integration Complexity
**Risk**: MPS → MRP → Orders flow too complex
**Mitigation**:
- Phased rollout (MRP view-only first)
- Comprehensive testing
- User training and documentation

---

## Dependencies

### Prerequisites
- ✅ Phase 2 MPS complete (DONE)
- ✅ Production order generation working (DONE)
- ✅ NetRequirementsCalculator implemented (DONE)
- ✅ BOM and sourcing rules tables exist (DONE)

### External Dependencies
- None (all internal development)

---

## Timeline

| Sprint | Duration | Deliverables | Status |
|--------|----------|-------------|--------|
| Sprint 1: MRP APIs | 3-5 days | 5 endpoints, schemas | 🎯 Ready |
| Sprint 2: MRP UI | 4-6 days | 3 pages, integration | 🎯 Ready |
| Sprint 3: Order Generation | 3-4 days | PO/TO creation, bulk | 🎯 Ready |
| Sprint 4: Testing & Polish | 2-3 days | Tests, docs | 🎯 Ready |
| **Total** | **3-4 weeks** | **Complete MRP** | 🎯 Ready |

---

## Next Steps

To start Phase 3, we should:

1. **Sprint 1 Day 1**: Implement MRP Run API endpoint
   - Create `POST /api/v1/mrp/plans/{mps_plan_id}/run`
   - Integrate with existing NetRequirementsCalculator
   - Add async processing with status tracking

2. **Sprint 1 Day 2**: Implement MRP Results API endpoint
   - Create `GET /api/v1/mrp/plans/{mps_plan_id}/results`
   - Add pagination and filtering
   - Return grouped results by order type

Would you like me to proceed with Sprint 1 Day 1 and create the MRP Run API endpoint?

---

**Status**: 🎯 **READY TO START**
**Next Action**: Implement MRP Run API endpoint
**Estimated Time**: 3-4 weeks total for complete MRP implementation

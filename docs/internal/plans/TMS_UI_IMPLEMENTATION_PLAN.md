# TMS UI Implementation Plan

**Created:** 2026-04-09
**Status:** Phases 1-6 COMPLETE — Ready for Phase 7
**Tracking:** Checkboxes updated as each item completes

---

## Overview

Convert the SC Planning frontend to a TMS-native UI across all personas (Executive, Planner, Admin, Training) and all 11 TMS TRM agent types. The backend agent framework is complete; the frontend has zero TMS agent representation.

### Personas Served

| Persona | Primary Surfaces | Current State | Target State |
|---------|-----------------|---------------|--------------|
| **Executive** | Dashboard, Briefings, Agent Performance | SC KPIs (Revenue, EBIT, POF) | TMS KPIs (OTD, cost/mile, carrier score) |
| **Planner** | Decision Stream, Worklists, Planning Pages | 11 SC worklists, SC decision types | 11 TMS worklists, TMS decision types |
| **Admin** | Governance, User Mgmt, AI Training | SC agent types in governance | TMS agent types, carrier/rate mgmt |
| **Training** | Scenario Board, Reports | SC Planning Scenarios | Freight Tender, Disruption, Mode Selection |

### Agent Type Coverage

| # | TMS TRM Agent | Backend | Frontend Worklist | Decision Card | Nav Item |
|---|---|---|---|---|---|
| 1 | CapacityPromise | done | [x] done | [x] done | [x] done |
| 2 | ShipmentTracking | done | [x] done | [x] done | [x] done |
| 3 | DemandSensing | done | [x] done | [x] done | [x] done |
| 4 | CapacityBuffer | done | [x] done | [x] done | [x] done |
| 5 | ExceptionManagement | done | [x] done | [x] done | [x] done |
| 6 | FreightProcurement | done | [x] done | [x] done | [x] done |
| 7 | BrokerRouting | done | [x] done | [x] done | [x] done |
| 8 | DockScheduling | done | [x] done | [x] done | [x] done |
| 9 | LoadBuild | done | [x] done | [x] done | [x] done |
| 10 | IntermodalTransfer | done | [x] done | [x] done | [x] done |
| 11 | EquipmentReposition | done | [x] done | [x] done | [x] done |

---

## Session Continuity (S0)

- [x] **S0.1** Fix handoff/resume skill paths to `-home-trevor-Autonomy-TMS`
- [x] **S0.2** Create memory directory and index (MEMORY.md, project_current_focus.md)
- [x] **S0.3** Create this tracking document

---

## Phase 1: Foundation — Decision Types & Navigation

**Goal:** Register all 11 TMS agent types so Decision Stream and worklist infrastructure can consume them.

### 1.1 — DecisionCard.jsx TMS Types
- [x] Add 11 entries to `TYPE_LABELS` constant (~line 127)
- [x] Add 11 entries to `EDITABLE_FIELDS` constant (~line 62)
- [x] Add TMS-specific icons/colors for each agent type

**File:** `frontend/src/components/decision-stream/DecisionCard.jsx`

**Type Mapping:**

| TRM Type String | Display Label | Phase |
|---|---|---|
| `capacity_promise` | Capacity Promise Agent | SENSE |
| `shipment_tracking` | Shipment Tracking Agent | SENSE |
| `demand_sensing` | Demand Sensing Agent | SENSE |
| `capacity_buffer` | Capacity Buffer Agent | ASSESS |
| `exception_management` | Exception Mgmt Agent | ASSESS |
| `freight_procurement` | Freight Procurement Agent | ACQUIRE |
| `broker_routing` | Broker Routing Agent | ACQUIRE |
| `dock_scheduling` | Dock Scheduling Agent | PROTECT |
| `load_build` | Load Build Agent | BUILD |
| `intermodal_transfer` | Intermodal Transfer Agent | BUILD |
| `equipment_reposition` | Equipment Reposition Agent | REFLECT |

**Editable Fields Per Type:**

| Type | Fields |
|---|---|
| `capacity_promise` | available_loads (number), promised_date (date), carrier_id (text) |
| `shipment_tracking` | eta_override (date), exception_action (select: REROUTE/RETENDER/HOLD) |
| `demand_sensing` | adjusted_forecast_loads (number), adjustment_reason (select) |
| `capacity_buffer` | buffer_loads (number), buffer_policy (select: FIXED/PCT_FORECAST/CONFORMAL) |
| `exception_management` | resolution_action (select: RETENDER/REROUTE/PARTIAL/ESCALATE/WRITE_OFF), cost_authorization (number) |
| `freight_procurement` | carrier_id (text), rate_override (number), action (select: TENDER/DEFER/SPOT/BROKER) |
| `broker_routing` | broker_id (text), max_rate (number) |
| `dock_scheduling` | dock_door_id (text), appointment_time (datetime), priority (select: EXPEDITE/STANDARD/DEFER) |
| `load_build` | action (select: CONSOLIDATE/SPLIT/HOLD/EXPEDITE), equipment_type (select: DRY_VAN/REEFER/FLATBED/CONTAINER) |
| `intermodal_transfer` | target_mode (select: ROAD/RAIL/OCEAN/AIR), accept_transit_penalty (select: YES/NO) |
| `equipment_reposition` | quantity (number), target_facility (text), action (select: REPOSITION/HOLD/DEFER) |

### 1.2 — Navigation Config TMS Worklists
- [x] Replace SC "AI AGENT WORKLISTS" section with TMS equivalents
- [x] Group by decision cycle phase (SENSE/ASSESS/ACQUIRE/PROTECT/BUILD/REFLECT)
- [x] Add phase section headers

**File:** `frontend/src/config/navigationConfig.js` (lines ~411-495)

### 1.3 — App.js TMS Routes
- [x] Add 11 import statements for new worklist pages
- [x] Add 11 `<Route>` elements with `CapabilityProtectedRoute`
- [ ] Remove or comment out SC worklist routes (keep for reference initially)

**File:** `frontend/src/App.js` (lines ~136-150 imports, ~745-796 routes)

### 1.4 — Documentation Update
- [x] Update `docs/CLAUDE_REFERENCE.md` frontend section (~line 166)
- [x] Update `docs/SHARED_VS_TMS_BOUNDARIES.md` implementation status

---

## Phase 2: TMS Worklist Pages (11 Pages)

**Goal:** One worklist page per TMS TRM agent. Each ~120-180 lines.

**Shared pattern (reuse, do not duplicate):**
- `TRMDecisionWorklist` component — table, actions, override dialog
- `getTRMDecisions(configId, { trm_type })` — fetch decisions
- `submitTRMAction(payload)` — submit accept/override/reject
- `RoleTimeSeries` — time series chart at top
- `LayerModeIndicator` — AIIO mode badge
- `useCapabilities` → `manage_[role]_worklist` check

### SENSE Phase

- [x] **2.1** `CapacityPromiseWorklistPage.jsx` — Lane capacity commitment decisions
- [x] **2.2** `ShipmentTrackingWorklistPage.jsx` — In-transit exception and ETA decisions
- [x] **2.3** `DemandSensingWorklistPage.jsx` — Shipping volume forecast adjustments

### ASSESS Phase

- [x] **2.4** `CapacityBufferWorklistPage.jsx` — Reserve carrier capacity decisions
- [x] **2.5** `ExceptionMgmtWorklistPage.jsx` — Delay/damage/refusal resolution

### ACQUIRE Phase

- [x] **2.6** `FreightProcurementWorklistPage.jsx` — Carrier waterfall tendering
- [x] **2.7** `BrokerRoutingWorklistPage.jsx` — Broker vs asset carrier routing

### PROTECT Phase

- [x] **2.8** `DockSchedulingWorklistPage.jsx` — Appointment and dock door optimization

### BUILD Phase

- [x] **2.9** `LoadBuildWorklistPage.jsx` — Load consolidation and optimization
- [x] **2.10** `IntermodalTransferWorklistPage.jsx` — Cross-mode transfer decisions

### REFLECT Phase

- [x] **2.11** `EquipmentRepositionWorklistPage.jsx` — Empty container/trailer repositioning

### Phase 2 Documentation
- [x] Update CLAUDE_REFERENCE.md with 11 new page paths
- [x] Update SHARED_VS_TMS_BOUNDARIES.md checkboxes

---

## Phase 3: Executive Dashboard TMS KPIs

- [x] **3.1** Replace Tier 1 ASSESS metrics with TMS KPIs (OTD, cost/unit, carrier index, utilization, cost/mile)
- [x] **3.2** Replace Tier 2 DIAGNOSE metrics (tender performance, asset efficiency, delivery cycle time)
- [x] **3.3** Update Sankey diagram node types (Shipper/Terminal/Cross-Dock/Consignee/Carrier_Yard/Port)
- [x] **3.4** Update AgentPerformancePage.jsx (already data-driven, no hardcoded SC types)
- [x] **3.5** Remove all hardcoded fallback values — show Alert when metrics unavailable
- [x] **3.6** Update CLAUDE.md no-fallback rule with expanded guidance

**Files:** `ExecutiveDashboard.jsx`, `AgentPerformancePage.jsx`, `SupplyChainConfigSankey.jsx`, `CLAUDE.md`

---

## Phase 4: Governance & Admin

- [x] **4.1** Update Governance.jsx to show 11 TMS agent types for AIIO threshold config
- [x] **4.2** Create CarrierManagementPage.jsx (onboarding, scorecard, lane coverage)
- [x] **4.3** Create RateManagementPage.jsx (contract rates, spot quotes, rate cards)
- [x] **4.4** Create P44IntegrationSettingsPage.jsx (project44 config, webhook status)
- [x] **4.5** Update Admin navigation section
- [x] **4.6** Documentation update

---

## Phase 5: TMS Planning Pages

- [x] **5.1** LoadBoard.jsx — Visual board by load status, carrier assignment
- [x] **5.2** LaneAnalytics.jsx — Lane performance, cost, OTD, carrier mix trends
- [x] **5.3** DockSchedule.jsx — Calendar/timeline, door utilization heat map
- [x] **5.4** ExceptionDashboard.jsx — Real-time exception monitoring, resolution workflow
- [x] **5.5** Update Planning navigation section
- [x] **5.6** Documentation update

---

## Phase 6: TMS Scenarios

- [x] **6.1** Freight Tender Scenario — Carrier bidding simulation
- [x] **6.2** Network Disruption Scenario — Port strike, weather, capacity crunch
- [x] **6.3** Mode Selection Scenario — Intermodal vs direct routing optimization
- [x] **6.4** Scenario templates page and config
- [ ] **6.4** Documentation update

---

## Phase 7: Map Visualization & p44 Dashboard

- [ ] **7.1** Shipment map view (Mapbox/Leaflet) — real-time positions, risk coloring
- [ ] **7.2** project44 integration dashboard — webhook status, tracking coverage, data freshness
- [ ] **7.3** Documentation update

---

## Session Execution Plan

| Session | Phases | Commit Message Pattern |
|---------|--------|----------------------|
| 1 | S0 + Phase 1 | `Add TMS decision types, navigation, and routes for 11 agent worklists` |
| 2 | Phase 2 (SENSE + ASSESS) | `Add 5 TMS worklist pages: capacity promise, tracking, demand, buffer, exception` |
| 3 | Phase 2 (ACQUIRE + PROTECT + BUILD + REFLECT) | `Add 6 TMS worklist pages: procurement, broker, dock, load, intermodal, equipment` |
| 4 | Phase 3 | `Update executive dashboard with TMS KPIs and freight flow Sankey` |
| 5 | Phase 4 | `Add TMS governance config and carrier/rate management admin pages` |
| 6 | Phase 5 | `Add TMS planning pages: load board, lane analytics, dock schedule, exceptions` |
| 7 | Phase 6 | `Add TMS scenario games: freight tender, network disruption, mode selection` |
| 8 | Phase 7 | `Add shipment map visualization and project44 integration dashboard` |

---

## Key File Reference

| File | What to Change |
|------|---------------|
| `frontend/src/components/decision-stream/DecisionCard.jsx` | TYPE_LABELS, EDITABLE_FIELDS |
| `frontend/src/config/navigationConfig.js` | AI AGENT WORKLISTS section |
| `frontend/src/App.js` | Imports + Routes |
| `frontend/src/components/cascade/TRMDecisionWorklist.jsx` | Reuse as-is |
| `frontend/src/services/planningCascadeApi.js` | Reuse as-is |
| `frontend/src/hooks/useCapabilities.js` | Add TMS capability fallbacks |
| `backend/app/services/powell/tms_heuristic_library/base.py` | Read-only: field definitions |
| `backend/app/services/powell/tms_agent_capabilities.py` | Read-only: type strings |
| `docs/CLAUDE_REFERENCE.md` | Frontend section updates |
| `docs/SHARED_VS_TMS_BOUNDARIES.md` | Status checkboxes |

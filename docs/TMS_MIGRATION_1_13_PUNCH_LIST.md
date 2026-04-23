# TMS Migration 1.13 Punch List — SCP-Fork Substrate Extraction

**Status:** open
**Started:** 2026-04-23 (first-pass TRM file expunge shipped in commit TBD)
**Register item:** Autonomy-Core `docs/MIGRATION_REGISTER.md` §1.13
**Owner:** TMS team

---

## Context

The TMS backend was forked from SCP and built a thin transport-plane layer (the 11 canonical TMS TRMs) on top of ~70% of the SCP codebase. The 11 canonical TMS TRMs are all clean
transport-plane concerns:

| Phase | TRM |
|---|---|
| SENSE | CapacityPromise, ShipmentTracking, DemandSensing |
| ASSESS | ExceptionManagement, CapacityBuffer |
| ACQUIRE | FreightProcurement, BrokerRouting |
| PROTECT | DockScheduling |
| BUILD | LoadBuild, IntermodalTransfer |
| REFLECT | EquipmentReposition |

Everything **below** those TRMs — infrastructure, other TRMs, most endpoints, services, training pipeline — is SCP-domain code that needs rescoping or extraction per
MIGRATION_REGISTER 1.13.

---

## Completed in first-pass (2026-04-23)

- ✓ Deleted 15 SCP-fork TRM service files in `backend/app/services/powell/`:
  `inventory_buffer_trm.py`, `inventory_rebalancing_trm.py`, `inventory_adjustment_trm.py`, `safety_stock_trm.py`, `mo_execution_trm.py`, `to_execution_trm.py`, `order_tracking_trm.py`, `forecast_baseline_trm.py`, `forecast_adjustment_trm.py`, `demand_adjustment_trm.py`, `supply_adjustment_trm.py`, `quality_disposition_trm.py`, `rccp_adjustment_trm.py`, `subcontracting_trm.py`, `maintenance_scheduling_trm.py`
- ✓ Deleted SCP-fork TRM test files: `test_decision_cycle.py`, `test_hive_integration.py`, `test_inter_hive.py`, `test_remaining_trm_services.py`, `test_trm_services.py`, 9 TRM-specific validation scripts, `scripts/generate_cascade_demo.py`
- ✓ Removed `_build_trm_instances` + `_build_trm_executors` + 3 per-TRM evaluator helpers in `provisioning_service.py` (dead code, never called)
- ✓ Stubbed SCP-fork TRM imports in `integration_service.py`, `email_signal_service.py`, `slack_signal_service.py`, `signal_ingestion_service.py`, `gnn_orchestration_service.py`, `agent_orchestrator_service.py`
- ✓ Deleted `api/endpoints/powell.py` (1412-line SCP-fork endpoint: inventory rebalancing, PO creation, order tracking, allocation on SKUs) and unwired its router from `main.py`
- ✓ Unwired `powell_training_router` registration
- ✓ Removed deleted TRM exports from `services/powell/__init__.py` `__all__`

The TMS backend boots cleanly with the 11 canonical TMS TRMs serving their endpoints under `/api/v1/*-trm/*` or `/api/v1/{phase}/*`.

---

## Deferred to item 1.13 (this doc)

### A. SCP-fork API endpoints still wired

The following endpoint files still exist and are wired in `backend/main.py` but are SCP-domain concerns. Each needs wholesale deletion OR rescoping to a transport-plane equivalent:

| Endpoint file | SCP concern | TMS equivalent (if any) | Action |
|---|---|---|---|
| `mps.py` | Master Production Schedule | — (manufacturing is not TMS) | Delete |
| `mrp.py` | MRP exception dashboard | — | Delete |
| `rccp.py` | Rough-Cut Capacity Planning | — | Delete |
| `production_orders.py` | Manufacturing Orders | — | Delete |
| `purchase_orders.py` | Supplier POs | — (FreightTender is the TMS analog) | Delete or rescope to PO→freight-tender lookups |
| `transfer_orders.py` | Inter-site stock moves | Load (the TMS load↔shipment concept) | Delete |
| `invoices.py` | Invoice 3-way matching | — (AP is SCP/ERP) | Delete |
| `suppliers.py` | Supplier master + performance | `Carrier` is the TMS analog | Delete |
| `inventory_projection.py` / `inventory_visibility.py` | SKU-level ATP projection | — | Delete |
| `lot_sizing.py` | MRP lot sizing | — | Delete |
| `sourcing_rules.py` | SCP sourcing priority rules | TMS carrier-selection rules (different shape) | Delete |
| `demand_plan.py` | SKU-level demand planning | `DemandSensingTRM` (volume-level) | Delete |
| `planning_decisions.py` | SCP decision stream proxy | `/decision-stream/*` is the canonical | Delete or rescope |
| `planning_cascade.py` | SCP daily cascade (S&OP + TRM sweep) | TMS daily cascade is different shape | Rescope |
| `forecast_pipeline.py` / `forecast_runs.py` / `forecast_config.py` / `forecast_analytics.py` / `forecast_adjustments.py` / `forecast_exceptions.py` | SKU demand forecast pipeline | `ShippingForecast` pipeline (doesn't exist yet in TMS) | Rescope to freight-volume forecast |
| `conformal_prediction.py` | SCP conformal prediction on SKUs | Transport conformal (ETA bounds, lane-time P10/P90) — different shape | Rescope |
| `trm.py` | Generic TRM dispatcher | Per-TRM endpoints now exist; this is duplicate surface | Delete |
| `powell_training.py` | SCP-era TRM training harness | TRM training belongs in Core per item 3.5; this endpoint is likely dead | Rescope or delete |
| `maintenance_orders.py` | Plant maintenance (CMMS) | Fleet maintenance is different table; rename/rescope | Rescope or delete |
| `consensus_planning.py` | S&OP consensus planning | — | Delete |
| `promotional_planning.py` | Trade-promotion planning (SCP or Demand Shaping plane) | — | Delete |
| `scenario_planning.py` | Scenario modeling on SCP state | Shared simulation infra; keep if transport-plane scenarios | Audit |
| `planning_hierarchy.py` | SCP strategic/tactical/operational layers | — | Delete |
| `planning_cycles.py` | SCP planning-cycle metadata | — | Delete |
| `planning_board.py` | SCP planning board UI | — | Delete |

### B. SCP-fork services woven through TMS runtime

Files with heavy SCP-TRM switch/case or SCP-entity reliance (partial list; full audit pending):

- `backend/app/services/decision_stream_service.py` — dispatches by `decision_type` across all 11 original SCP TRM types
- `backend/app/services/decision_governance_service.py` — governance policies per SCP TRM type
- `backend/app/services/hierarchical_metrics_service.py` — per-SCP-TRM KPI aggregation
- `backend/app/services/agent_orchestrator_service.py` — `AgentType` enum + handler registration
- `backend/app/services/directive_service.py` — directive dispatch by trm_type
- `backend/app/services/recommendations_engine.py`
- `backend/app/services/override_effectiveness_service.py`
- `backend/app/services/experiential_knowledge_service.py`
- `backend/app/services/powell/simulation_decision_seeder.py` — generates SCP-fork Decision Stream seed decisions
- `backend/app/services/powell/outcome_collector.py`
- `backend/app/services/powell/tactical_hive_coordinator.py`
- `backend/app/services/powell/monitoring_service.py` — background checks on SCP TRM types
- `backend/app/services/powell/integration_service.py` — stubbed in first-pass; full rescope pending
- `backend/app/services/training_corpus/` — whole subpackage (site_level_runner, teacher, simulation_runner, topology, historical/*) generates SCP-fork TRM training data
- `backend/app/services/conformal_prediction/` — conformal on SCP SKU forecasts
- `backend/app/services/food_dist_history_generator.py` — Food Distribution SCP demo
- `backend/app/services/simulation_data_converter.py` — converts SCP sim output to TMS; may or may not be salvageable
- `backend/app/services/assistant_write_tools.py` — assistant can write to SCP TRM tables
- `backend/app/services/email_signal_service.py` / `slack_signal_service.py` / `signal_ingestion_service.py` — SCP-fork forecast_adjustment routing stubbed; TMS DemandSensing wiring pending
- `backend/main.py` line ~1499 references `round_metric` string literal (legacy), and routes many SCP endpoints

### C. SCP-fork models still on TMS `Base.metadata`

TMS imports from `app.models` register SCP-domain tables on the shared SQLAlchemy metadata. Candidates for extraction/rescope:

- `app/models/mps.py` (MPSPlan, MPSPlanItem, MPSCapacityCheck, MPSKeyMaterialRequirement)
- `app/models/mrp.py` (MRPRun, MRPRequirement, MRPException)
- `app/models/production_order.py`
- `app/models/purchase_order.py`
- `app/models/transfer_order.py`
- `app/models/invoice.py`
- `app/models/goods_receipt.py`
- `app/models/supplier.py` (VendorProduct, VendorLeadTime, SupplierPerformance)
- `app/models/pegging.py` (SupplyDemandPegging, AATPConsumptionRecord)
- `app/models/inventory_projection.py`
- `app/models/forecast_pipeline.py`
- `app/models/rccp.py` (BillOfResources, RCCPRun)
- `app/models/quality_order.py`
- `app/models/maintenance_order.py`
- `app/models/subcontracting_order.py`
- `app/models/turnaround_order.py`
- `app/models/project_order.py`

### D. SCP-fork scripts

- `backend/scripts/seed_default_tenant.py` (large Default / Beer Scenario seeding)
- `backend/scripts/seed_default_tenant_fixed.py`
- `backend/scripts/setup_food_dist_demo.py`
- `backend/scripts/prepare_powell_demo.py`
- `backend/scripts/seed_food_dist_execution_data.py`
- `backend/scripts/migrate_to_execution_engine.py`
- `backend/scripts/validation/` — likely half SCP-fork

### E. SCP-fork permission/capability surface

- `backend/app/core/capabilities.py` — slugs like `view_mps`, `view_production_orders`, `view_forecasts`, `edit_supply_plan`, etc.
- Role definitions referencing SCP-era permissions

### F. Frozen historical migrations (no action)

`backend/migrations/versions/20260416_d_backfill_agent_decisions_from_powell.py` and similar pre-2026-04-23 migrations reference the deleted TRM tables and types. These are frozen historical migrations — do NOT modify them. They replay cleanly against a point-in-time DB snapshot.

---

## Recommended execution order for item 1.13

1. **Audit + triage B** (services) — surface-wide map of what's salvageable vs delete. ~1 day.
2. **Delete A endpoints + unwire routers** — largest line-count impact, unblocks downstream cleanup. ~0.5 day.
3. **Rescope B services** — most surgical work; each file gets its own PR. ~3-5 days.
4. **Trim C models** — ~1 day; needs coordination with Core DB schema (some of these are canonical in `azirella-data-model` and should just be removed from TMS-side imports, not deleted wholesale).
5. **Delete D scripts + E permission slugs** — ~0.5 day.
6. **Full runtime test + green container restart** on a rebuilt DB volume. ~0.5 day.

Total: ~7-8 days of focused work, probably spread across 2-3 weeks given the need for thoughtful decisions per file.

---

## Non-goals for item 1.13

- **Do NOT** rewrite `powell/__init__.py` or other broadly-imported Powell framework files to add fresh TMS functionality. Item 1.13 is pure extraction/rescope. New TMS substrate lands in other register items.
- **Do NOT** touch `services/powell/hive_signals.py` / `site_capabilities.py` / `agent_capabilities.py` / `agent_contract.py` — these ARE canonical TMS-facing infra (see `azirella_data_model.powell.tms.*`).
- **Do NOT** delete the canonical 11 TMS TRMs' services, endpoints, or training data.

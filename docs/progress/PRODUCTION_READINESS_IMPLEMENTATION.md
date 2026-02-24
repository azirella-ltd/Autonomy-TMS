# Production Readiness Implementation Plan

**Created**: 2026-02-24
**Status**: Items 1-10 Complete + Stub Removal Batches 1-2 Complete
**Priority Items**: 1-3 of 10 identified production gaps

---

## Overview

This document tracks the implementation of the top 3 production-readiness gaps identified during code audit. These are features that appear functional in the UI but execute placeholder/mock logic underneath.

---

## Item 1: Monte Carlo Simulation — Wire Real SC Planning Engine

**Priority**: Critical
**Impact**: Core differentiator (Stochastic Planning) is non-functional

### Problem

Three files generate fake random numbers instead of running actual supply chain simulations:

| File | Issue |
|------|-------|
| `backend/app/services/parallel_monte_carlo.py` | `_run_single_simulation()` sleeps 10ms, draws from `np.random.lognormal` — no engine execution |
| `backend/app/services/scenario_evaluation_service.py` | `_run_monte_carlo()` uses `random.gauss()` with hardcoded means |
| `backend/app/api/endpoints/stochastic_analytics.py` | `start_monte_carlo` never queues a task; `get_monte_carlo_status` returns hardcoded results |

### Solution

**A. `parallel_monte_carlo.py` — `_run_single_simulation()`** (lines 166-208)

Replace fake random draws with real simulation execution:
1. Load `SupplyChainConfig` + nodes + lanes + products from DB using `config_id`
2. Instantiate `StochasticSampler(game_id=seed)` for this iteration's random draws
3. Run `SupplyChainPlanner.run_planning(start_date, game_id=seed)` — the 3-step AWS SC planning engine which internally uses the sampler for lead times, yields, demand variability
4. Extract real metrics (total cost, service level, inventory, backlog) from the generated `SupplyPlan` records
5. Remove the `time.sleep(0.01)` stub

The `summarize_results()` method is already correct — it delegates to `StochasticAnalyticsService` which uses `scipy.stats`.

**B. `scenario_evaluation_service.py` — `_run_monte_carlo()`** (lines 568-635)

Replace `random.gauss()` loop with real engine calls:
1. Load current inventory state from `InvLevel` for the config
2. For each simulation iteration, use `StochasticSampler` to perturb demand/lead times
3. Apply the scenario's `action` as a parameter modification (e.g., `expedite_po` reduces lead time)
4. Run a simplified planning cycle to compute the resulting cost/service/inventory metrics
5. Fix `_calculate_overall_score()` normalization (lines 729-738) — use actual min/max ranges from the simulation results instead of dividing by arbitrary 1000

**C. `stochastic_analytics.py` — API endpoints** (lines 309-382)

Wire the existing `ParallelMonteCarloRunner` to the endpoints:
1. `start_monte_carlo`: Uncomment `background_tasks.add_task()`, implement `run_monte_carlo_task()` that instantiates `ParallelMonteCarloRunner` and persists results
2. `get_monte_carlo_status`: Add an in-memory task store (dict with `task_id` → status/result) to track background tasks
3. Return real progress and results instead of hardcoded data

### Key Integration Points

```
StochasticSampler (seeds per iteration)
    ↓
SupplyChainPlanner.run_planning() (3-step AWS SC engine)
    ├── DemandProcessor.process_demand()
    ├── InventoryTargetCalculator.calculate_targets()
    └── NetRequirementsCalculator.calculate_requirements()
    ↓
Real metrics extracted from SupplyPlan results
    ↓
StochasticAnalyticsService.analyze() (P10/P50/P90 — already real)
```

### Files Modified

- `backend/app/services/parallel_monte_carlo.py`
- `backend/app/services/scenario_evaluation_service.py`
- `backend/app/api/endpoints/stochastic_analytics.py`

---

## Item 2: Recommendations — Wire Accept/Execute to Real Order Creation

**Priority**: High
**Impact**: Worklist "Accept" button does nothing — core AI-as-Labor UX is broken

### Problem

The recommendations endpoint (`backend/app/api/endpoints/recommendations.py`) uses a mock helper `_get_mock_recommendation_details()` (line 876) that returns hardcoded data for 3 fake recommendation IDs. All execution/rollback paths return success without creating any database records.

| Endpoint | Issue |
|----------|-------|
| `POST /{id}/accept` (line 218) | Returns fake `execution_id`, no orders created |
| `POST /{id}/execute` (line 504) | Uses mock helper, no DB writes |
| `POST /{id}/rollback` (line 560) | Uses mock helper, no state reversal |
| `POST /batch/execute` (line 337) | Uses mock helper for each recommendation |
| `POST /batch/rollback` (line 416) | Uses mock helper for each recommendation |
| `GET /{id}/execution-history` (line 609) | Returns hardcoded event list |

### Solution

1. **Create `Recommendation` DB model** (or reuse `powell_site_agent_decisions`):
   - Fields: `id`, `recommendation_type`, `product_id`, `source_site_id`, `target_site_id`, `quantity`, `estimated_cost`, `status` (pending/approved/executed/rolled_back), `execution_snapshot`, `created_order_id`, `config_id`
   - This replaces `_get_mock_recommendation_details()`

2. **Wire accept/execute to real order creation**:
   - For `REBALANCE` type: Create `TransferOrder` + `TransferOrderLineItem` via existing models
   - For `EXPEDITE_PO` type: Create `PurchaseOrder` + `PurchaseOrderLineItem` via existing models
   - For `SAFETY_STOCK_ADJUSTMENT` type: Update `InvPolicy` safety stock target
   - Capture pre-execution inventory snapshot from `InvLevel`

3. **Wire rollback to reverse operations**:
   - Load `execution_snapshot`, create reverse transfer/cancel PO
   - Set `recommendation.is_rolled_back = True`

4. **Replace `_generate_recommendations_from_risks()` cost estimates**:
   - Use actual transportation lane costs from DB instead of hardcoded `$4/unit`
   - Use `InventoryRebalancingTRM.decide()` for optimal transfer quantity when available

### Files Modified

- `backend/app/api/endpoints/recommendations.py`
- `backend/app/models/sc_entities.py` (add Recommendation model if needed)

---

## Item 3: Agent Orchestrator — Wire Real TRM/GNN Handlers

**Priority**: High
**Impact**: All 11 TRM agents and both GNN models are disconnected from the orchestration layer

### Problem

`backend/app/services/agent_orchestrator_service.py` line 1101 registers a single `placeholder_handler` for every `AgentType` except LLM agents. The real TRM imports are commented out. When the orchestrator fires a trigger, every agent returns `"action_type": "placeholder"`.

Additionally:
- `run_planning_cycle()` (line 544): tGNN daily trigger is constructed but never dispatched
- `_process_conditions()` (line 743): Current state is hardcoded instead of queried from DB

### Solution

**A. Wire TRM handlers** (lines 1101-1131):

Each TRM service in `backend/app/services/powell/` has a `decide()` or equivalent method. Create real async handlers:

| AgentType | Powell Service | Handler Logic |
|-----------|---------------|---------------|
| `TRM_ATP` | `atp_executor.py:ATPExecutorTRM` | Build state from order + inventory, call `decide()` |
| `TRM_REBALANCE` | `inventory_rebalancing_trm.py:InventoryRebalancingTRM` | Build state from cross-location inventory, call `decide()` |
| `TRM_PO_CREATION` | `po_creation_trm.py:POCreationTRM` | Build state from inventory position + demand, call `decide()` |
| `TRM_ORDER_TRACKING` | `order_tracking_trm.py:OrderTrackingTRM` | Build state from order status + exceptions, call `decide()` |
| `TRM_MO_EXECUTION` | `mo_execution_trm.py:MOExecutionTRM` | Build state from MO + capacity, call `decide()` |
| `TRM_TO_EXECUTION` | `to_execution_trm.py:TOExecutionTRM` | Build state from TO + transit, call `decide()` |
| `TRM_QUALITY` | `quality_disposition_trm.py:QualityDispositionTRM` | Build state from quality order, call `decide()` |
| `TRM_MAINTENANCE` | `maintenance_scheduling_trm.py:MaintenanceSchedulingTRM` | Build state from work order, call `decide()` |
| `TRM_SUBCONTRACTING` | `subcontracting_trm.py:SubcontractingTRM` | Build state from make-vs-buy context, call `decide()` |
| `TRM_FORECAST_ADJ` | `forecast_adjustment_trm.py:ForecastAdjustmentTRM` | Build state from signal, call `decide()` |
| `TRM_SAFETY_STOCK` | `safety_stock_trm.py:SafetyStockTRM` | Build state from inventory policy, call `decide()` |
| `GNN_EXECUTION` | `allocation_service.py:AllocationService` | Run tGNN inference, generate allocations |
| `GNN_SOOP` | `sop_inference_service.py:SOPInferenceService` | Run S&OP GraphSAGE, output policy parameters |

**B. Fix `run_planning_cycle()`** (line 544):
- Actually dispatch the tGNN trigger via `process_trigger()`
- Chain TRM triggers from allocation results

**C. Fix `_process_conditions()` current state** (line 743):
- Query `InvLevel`, `supply_plan`, `forecast` from DB
- Build real current_state dict

### Files Modified

- `backend/app/services/agent_orchestrator_service.py`

---

## Verification Plan

1. **Monte Carlo**: `POST /api/v1/stochastic-analytics/monte-carlo/start` returns a real `task_id` → `GET /monte-carlo/{task_id}` returns real P10/P50/P90 distributions after computation completes
2. **Recommendations**: `POST /api/v1/recommendations/{id}/accept` creates a real `TransferOrder` or `PurchaseOrder` in the database
3. **Orchestrator**: `orchestrator.process_trigger(atp_trigger)` calls `ATPExecutorTRM.decide()` and returns a real decision (not `"action_type": "placeholder"`)

### Test Commands

```bash
# Monte Carlo tests
docker compose exec -T backend python -m pytest tests/ -k "monte_carlo or stochastic" -v

# Recommendation tests
docker compose exec -T backend python -m pytest tests/ -k "recommendation" -v

# Orchestrator tests
docker compose exec -T backend python -m pytest tests/ -k "orchestrator" -v

# Full regression
docker compose exec -T backend python -m pytest tests/ --ignore=tests/test_beer_game_execution_services.py --ignore=tests/integration/ --ignore=tests/test_scenario_branching_service.py -q
```

---

## Items 4-10

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4 | Analytics KPIs hardcoded | **Complete** | Replaced hardcoded trends, multipliers, and demo data with real computed values |
| 5 | CTP uses hardcoded zero commitments | **Complete** | Wired to ProductionOrder + ProductionProcess tables, multi-period projections query real data |
| 6 | TRM training does no gradient descent | **N/A** | Already implemented — real PyTorch training with loss.backward(), optimizer.step() |
| 7 | Supply plan result response incomplete | **Complete** | Persist orders + inventory_targets; added cost P10/P90 and OTIF probability to response |
| 8 | Forecast pipeline missing algorithms | **Complete** | Added SES, Holt, Holt-Winters, Croston; demand classification (smooth/erratic/intermittent/lumpy); 9 clustering methods |
| 9 | Negotiation execution is a no-op | **Complete** | Wired inventory_share (transfer) and order_adjustment (modify order) to game state |
| 10 | S&OP Plan entity partial | **N/A** | Already implemented as PolicyEnvelope + SOPService + S&OP GraphSAGE |

### Item 4 Changes
- **analytics.py**: Replaced `transportation_cost = total_cost * 0.25` with real cost decomposition; replaced all hardcoded trends with `_pct_trend()` computed from first-half vs second-half data; real per-week OTIF/inventory from data; computed capacity_utilization, risk_score, network_flexibility, forecast_accuracy from actual metrics; removed demo strategic KPI defaults
- **decision_metrics.py**: Removed `_get_demo_agent_decisions()` fallback — returns empty list when no real agent decisions exist

### Item 5 Changes
- **ctp_service.py**: `_get_production_commitments()` now queries `ProductionOrder` table for PLANNED/RELEASED/IN_PROGRESS orders; `_get_production_capacity()` checks site attributes and `ProductionProcess` table before falling back to defaults; multi-period `project_ctp_multi_period()` queries future ProductionOrder by planned_start_date and component ATP via BOM explosion

### Item 7 Changes
- **supply_plan.py (model)**: Added `orders` and `inventory_targets` JSON columns
- **supply_plan.py (endpoint)**: Persist `orders` and `inventory_targets` from result_data; return `total_cost_p10`, `total_cost_p90`, `otif_probability_above_target`, `orders`, `inventory_targets` in response
- **supply_plan.py (schema)**: Added all missing fields to `SupplyPlanResultResponse`

### Item 8 Changes
- **forecast_pipeline_service.py**: Added `_classify_demand()` (Syntetos-Boylan CV²/ADI classification); `_forecast_by_pattern()` selects algorithm by demand type; `_ses_forecast()` (Simple Exponential Smoothing); `_holt_forecast()` (Double ES — level + trend); `_holtwinters_forecast()` (Triple ES via statsmodels — auto seasonal); `_croston_forecast()` (intermittent demand); all 9 clustering methods wired (KMeans, Agglomerative, Birch, GaussianMixture, MeanShift, Spectral, AffinityPropagation, OPTICS, HDBSCAN)

### Item 9 Changes
- **negotiation_service.py**: `_execute_negotiation()` now modifies game state: `inventory_share` transfers inventory between participant_rounds; `order_adjustment` updates order_upstream; `lead_time`/`price_adjustment` logged as informational agreements

---

## Stub Removal Batch 1

Additional mock/stub code removed after Items 1-10:

| # | Stub | Status | Notes |
|---|------|--------|-------|
| S1 | Forecast snapshot capture returns hardcoded mock | **Complete** | Queries real Forecast table; restore updates DB records |
| S2 | Agent historical performance returns hardcoded 87% | **Complete** | Queries `powell_site_agent_decisions` for real accuracy, overrides, regret rate |
| S3 | ATP demand forecast returns hardcoded 100 | **Complete** | Falls back to MarketDemand baseline when no history; returns 0 instead of fake data |
| S4 | Inventory risk falls back to mock data | **Complete** | Removed `_generate_mock_inventory_risks()` and `_generate_mock_recommendations()`; returns empty list when no data |
| S5 | S&OP simulation returns hardcoded results | **Complete** | Wired to SupplyPlanService.generate_supply_plan() with 200 MC scenarios |

### S1 Changes
- **forecast_adjustments.py**: `_capture_forecast_snapshot()` queries Forecast table with config/product/site filters; `restore_version()` iterates snapshot and updates Forecast records in DB

### S2 Changes
- **agent_recommendation_service.py**: `_get_historical_performance()` queries SiteAgentDecision table — counts decisions, overrides (human_feedback not null), accuracy from reward_signal, regret rate from low human_rating; returns zeros when no history

### S3 Changes
- **atp_service.py**: `_forecast_demand_for_period()` fallback queries MarketDemand for config's base demand (final_demand/initial_demand); returns 0 as last resort

### S4 Changes
- **recommendations.py**: Removed `_generate_mock_inventory_risks()` (hardcoded Atlanta/Denver mock data) and `_generate_mock_recommendations()` (hardcoded transfer/expedite mock recs); both fallbacks replaced with empty list

### S5 Changes
- **sop_service.py**: `_run_sop_simulation()` now instantiates SupplyPlanService, runs 200-scenario Monte Carlo, extracts OTIF/inventory/cost metrics from balanced scorecard; added `_empty_simulation_result()` for graceful failure

---

## Stub Removal Batch 2

Additional mock/stub/placeholder code replaced with real DB-backed logic:

| # | Stub | Status | Notes |
|---|------|--------|-------|
| S6 | Recommendation impact uses placeholder data | **Complete** | Queries real InvLevel for excess/deficit sites; product weight/cost from Product table |
| S7 | Sustainability/cost scoring uses hardcoded weights | **Complete** | Looks up product `unit_weight_kg` and `unit_cost` from DB before falling back to defaults |
| S8 | Business impact uses hardcoded formulas | **Complete** | Wired to SupplyPlanService.generate_supply_plan() with real MC; falls back to heuristic model |
| S9 | Simulation demand returns hardcoded 4/8 | **Complete** | Queries MarketDemand for config demand pattern (initial/change_week/final); falls back to classic |
| S10 | Deterministic planner source node returns None | **Complete** | Queries TransportationLane for upstream connection |
| S11 | Cost calculator record_round_cost is pass | **Complete** | Updates ParticipantRound holding/backorder/total cost via ScenarioRound lookup |
| S12 | Scenario branching products/BOMs empty | **Complete** | Loads from Product and ProductBom tables via `_load_products()` and `_load_boms()` helpers |
| S13 | Recommendation decision tracking not persisted | **Complete** | Creates SiteAgentDecision record with human_feedback and human_rating for RL training |
| S14 | RoundMetric player_id always None | **Complete** | Looks up Participant by scenario_id + node_id via `_get_participant_for_site()` |

### S6-S7 Changes
- **recommendations_engine.py**: `simulate_recommendation_impact()` now builds rec dict from real InvLevel data via `_build_rec_from_id()`; `_score_sustainability()` and `_score_cost()` look up product weight and unit cost from Product table

### S8 Changes
- **business_impact_service.py**: `_simulate_scenario()` tries SupplyPlanService with 200 MC scenarios using config_id; falls back to simplified heuristic model on failure

### S9 Changes
- **simulation_execution_engine.py**: `_get_market_demand()` queries MarketDemand for scenario's config demand pattern; falls back to classic Beer Game pattern

### S10 Changes
- **deterministic_planner.py**: `_get_source_node()` queries TransportationLane where to_site_id matches, returns from_site_id

### S11 Changes
- **cost_calculator.py**: `record_round_cost()` finds ScenarioRound, updates ParticipantRound cost fields, commits

### S12 Changes
- **scenario_branching_service.py**: `_serialize_config()` calls `_load_products()` and `_load_boms()` which query Product and ProductBom tables by config_id

### S13 Changes
- **recommendations_engine.py**: `track_recommendation_decision()` creates SiteAgentDecision with human_feedback (reason), human_rating (5=accepted, 1=rejected, 3=modified)

### S14 Changes
- **simulation_execution_engine.py**: Added `_get_participant_for_site()` to look up participant by scenario+site; RoundMetric now uses `scenario_id` instead of `game_id` and populates `participant_id`

# TRM Agents Explained

## Overview

The Autonomy platform uses Warren B. Powell's **Sequential Decision Analytics and Modeling (SDAM)** framework to structure its AI agents. At the execution layer, **Tiny Recursive Models (TRMs)** make narrow, fast decisions (< 10ms) that augment deterministic engine baselines.

Each TRM is paired 1:1 with a **deterministic engine**. The engine provides the auditable, formula-based baseline. The TRM learns context-dependent adjustments the engine's fixed rules cannot capture.

```
┌────────────────────────────────────────────────────────────┐
│  S&OP GraphSAGE  (CFA - Cost Function Approximation)      │
│  Updates: weekly/monthly                                    │
│  Outputs: policy parameters θ, criticality scores           │
└──────────────────────────┬─────────────────────────────────┘
                           │ θ + network embeddings
┌──────────────────────────▼─────────────────────────────────┐
│  Execution tGNN  (CFA/VFA Bridge)                          │
│  Updates: daily                                             │
│  Outputs: Priority × Product × Location allocations         │
└──────────────────────────┬─────────────────────────────────┘
                           │ allocations + context
┌──────────────────────────▼─────────────────────────────────┐
│  Narrow TRMs  (VFA - Value Function Approximation)         │
│  Updates: per-decision (< 10ms)                            │
│  11 Engine-TRM pairs:                                       │
│    ┌─────────────────────────┬──────────────────────────┐   │
│    │ Deterministic Engine     │ Learned TRM              │   │
│    ├─────────────────────────┼──────────────────────────┤   │
│    │ AATPEngine               │ ATPExecutorTRM           │   │
│    │ MRPEngine                │ POCreationTRM            │   │
│    │ SafetyStockCalculator    │ SafetyStockTRM           │   │
│    │ RebalancingEngine        │ InventoryRebalancingTRM  │   │
│    │ OrderTrackingEngine      │ OrderTrackingTRM         │   │
│    │ MOExecutionEngine        │ MOExecutionTRM           │   │
│    │ TOExecutionEngine        │ TOExecutionTRM           │   │
│    │ QualityEngine            │ QualityDispositionTRM    │   │
│    │ MaintenanceEngine        │ MaintenanceSchedulingTRM │   │
│    │ SubcontractingEngine     │ SubcontractingTRM        │   │
│    │ ForecastAdjustmentEngine │ ForecastAdjustmentTRM    │   │
│    └─────────────────────────┴──────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

### Graceful Degradation

The layered architecture ensures the system works at every level of capability:

| Level | Available | Behavior |
|-------|-----------|----------|
| **Full** | Engine + trained TRM | Engine baseline + learned adjustments |
| **Heuristic** | Engine only (TRM untrained) | Engine baseline = TRM heuristic fallback |
| **Minimal** | Neither | Hard-coded defaults (safe but suboptimal) |

---

## The 5 Engine-TRM Pairs

### 1. AATP Engine → ATP Executor

**Purpose**: Allocated Available-to-Promise. Given a customer order, determine what can be fulfilled from priority-based allocation buckets.

**Engine**: `engines/aatp_engine.py` — `AATPEngine`

The AATP engine implements priority-based consumption with a specific sequence:

```
Consumption sequence for order at priority P:
  1. Own tier (P) first
  2. Bottom-up from lowest priority (5 → 4 → 3 → ...)
  3. Stop at own tier (cannot consume above)

Example: P=2 order → tries [2, 5, 4, 3] (skips 1)
```

| Component | Detail |
|-----------|--------|
| Input | `Order(order_id, product_id, location_id, requested_qty, priority)` |
| Output | `ATPResult(can_fulfill_full, available_qty, shortage_qty, consumption_detail)` |
| Config | `AATPConfig(num_priority_tiers=5, allow_borrowing_up=False)` |
| Deterministic? | 100% — same allocations + same order = same result |

**TRM**: `atp_executor.py` — `ATPExecutorTRM`

The TRM adds:
- Exception handling for partial fills (substitute? backorder? split?)
- Dynamic priority adjustment based on customer context
- Cross-site availability checks when local stock insufficient

| Component | Detail |
|-----------|--------|
| State vector | inventory, pipeline, backlog, allocated, available_atp, demand_forecast, pending_orders, priority |
| Action space | Discrete: fulfill (0), partial (1), defer (2), reject (3) + continuous: qty_fulfilled |
| Reward | `fill_rate * 0.4 + on_time_bonus * 0.2 + priority_weight * 0.2 + fairness * 0.2` |

**Delegation**: `ATPExecutorTRM._heuristic_decision()` builds an `EngineOrder`, calls `self._engine.check_availability()`, and maps the result to an `ATPResponse`.

---

### 2. MRP Engine → PO Creation TRM

**Purpose**: Purchase order timing and quantity decisions. When should we order, how much, from which supplier?

**Engine**: `engines/mrp_engine.py` — `MRPEngine`

The MRP engine implements standard netting, BOM explosion, and lot sizing:

```
Net Requirements = Gross Requirements - On Hand - Scheduled Receipts + Safety Stock
Planned Orders  = Lot-size(Net Requirements, policy) offset by Lead Time
```

| Component | Detail |
|-----------|--------|
| Input | `GrossRequirement(product_id, period, quantity)` + BOM + inventory |
| Output | `List[PlannedOrder(product_id, period, quantity, order_type)]` |
| Config | `MRPConfig(planning_horizon=52, lot_sizing='lot_for_lot')` |
| Lot sizing | `lot_for_lot`, `fixed_order_qty`, `eoq`, `period_order_qty` |
| Deterministic? | 100% |

**TRM**: `po_creation_trm.py` — `POCreationTRM`

The TRM wraps order-up-to logic with context-aware adjustments:
- Expedite decisions when below critical thresholds
- Supplier selection considering reliability and cost
- Forecast-driven anticipatory ordering

| Component | Detail |
|-----------|--------|
| State vector | on_hand, in_transit, on_order, committed, backlog, safety_stock, reorder_point, dos, demand_forecast, lead_time, supplier_reliability, supply_risk, demand_volatility |
| Action space | Discrete: order (1), defer (0), expedite (2), cancel (3) + continuous: order_qty |
| Reward | `stockout_penalty * 0.4 + dos_target * 0.3 + cost_efficiency * 0.2 + timing_accuracy * 0.1` |

**Delegation**: `POCreationTRM` stores `self._engine = mrp_engine` in `__init__`. The heuristic fallback uses order-up-to-level logic with safety stock from the SS calculator. The MRP engine is available for gross-to-net planning at the orchestration level.

---

### 3. Safety Stock Calculator → Safety Stock TRM

**Purpose**: Adjust safety stock levels beyond what deterministic formulas compute, capturing context the formulas miss (seasonality, regime changes, recent stockouts).

**Engine**: `engines/safety_stock_calculator.py` — `SafetyStockCalculator`

Implements the 4 AWS SC policy types:

| Policy Type | Formula |
|-------------|---------|
| `abs_level` | SS = fixed quantity |
| `doc_dem` | SS = avg_daily_demand × days_of_coverage |
| `doc_fcst` | SS = avg_daily_forecast × days_of_coverage |
| `sl` (service level) | SS = z(SL) × √(LT × σ²_d + d² × σ²_LT) |

| Component | Detail |
|-----------|--------|
| Input | `DemandStats(avg_daily_demand, std_daily_demand, avg_lead_time, std_lead_time)` + `SSPolicy(policy_type, service_level)` |
| Output | `SSResult(safety_stock, reorder_point, order_up_to_level, policy_type)` |
| Deterministic? | 100% |

**TRM**: `safety_stock_trm.py` — `SafetyStockTRM`

The TRM learns a **multiplier ∈ [0.5, 2.0]** on top of the engine baseline:

```
adjusted_ss = baseline_ss × multiplier
```

Heuristic rules (used before training):
| Condition | Multiplier | Reason |
|-----------|-----------|--------|
| stockout_count ≥ 3 | 1.4× | RECENT_STOCKOUT |
| stockout_count ≥ 1 | 1.2× | RECENT_STOCKOUT |
| demand_cv > 0.5 | 1.3× | HIGH_VOLATILITY |
| seasonal_index > 1.3 | 1.2× | SEASONAL_PEAK |
| seasonal_index < 0.7 | 0.85× | SEASONAL_TROUGH |
| demand_trend > 0.1 | 1.1× | TREND_UP |
| demand_trend < -0.1 | 0.9× | TREND_DOWN |
| excess_days > 60 | 0.85× | EXCESS_INVENTORY |
| \|forecast_bias\| > 0.1 | 1.0 + bias | FORECAST_BIAS |

| Component | Detail |
|-----------|--------|
| State vector | baseline_ss, current_dos, demand_cv, demand_trend, seasonal_index, recent_stockout_count, recent_excess_days, forecast_bias, lead_time_days, lead_time_cv |
| Action space | Continuous: multiplier ∈ [0.5, 2.0] |
| Reward | `stockout_penalty * 0.4 + dos_target * 0.3 + excess_cost * 0.2 + stability_bonus * 0.1` |

**Delegation**: `SafetyStockTRM._heuristic_evaluate()` calls `self._ss_calculator.compute_safety_stock()` for the baseline, then applies context-dependent multiplier rules.

---

### 4. Rebalancing Engine → Inventory Rebalancing TRM

**Purpose**: Cross-location inventory transfers. Identify excess/deficit sites and recommend transfers.

**Engine**: `engines/rebalancing_engine.py` — `RebalancingEngine`

```
Excess sites:   DOS > target_dos × 1.5
Deficit sites:  DOS < target_dos × 0.75

Transfer qty = min(source_excess, dest_deficit)
             where source_excess = available - safety_stock
                   dest_deficit  = safety_stock - available

Apply lane constraints: qty = max(min_qty, min(qty, max_qty))
```

| Component | Detail |
|-----------|--------|
| Input | `Dict[str, SiteState]` + `List[LaneConstraints]` |
| Output | `List[TransferRecommendation]` sorted by urgency |
| Config | `RebalancingConfig(excess_threshold=1.5, deficit_threshold=0.75, stockout_risk_threshold=0.5)` |
| Reason classification | stockout_risk (dest risk > 0.5), excess_inventory (source DOS > 2× target), service_level (default) |
| Deterministic? | 100% |

**TRM**: `inventory_rebalancing_trm.py` — `InventoryRebalancingTRM`

The TRM adds:
- Demand-shift detection and proactive rebalancing
- Cost-optimization transfers (reduce holding costs)
- tGNN-informed criticality weighting

| Component | Detail |
|-----------|--------|
| State vector | Per-site: on_hand, in_transit, committed, backlog, demand_forecast, demand_uncertainty, safety_stock, target_dos, criticality, supply_risk, dos, stockout_risk + lane features + network features (30 dims) |
| Action space | Binary: transfer (1) / hold (0) + continuous: transfer_qty |
| Reward | `service_improvement * 0.5 + transfer_cost_penalty * 0.3 + balance_improvement * 0.2` |

**Delegation**: `InventoryRebalancingTRM._heuristic_evaluate_pair()` converts TRM's `SiteInventoryState` → engine's `SiteState`, calls `self._engine.evaluate_pair()`, and maps the engine's `TransferRecommendation` back to the TRM's `RebalanceRecommendation`.

---

### 5. Order Tracking Engine → Order Tracking TRM

**Purpose**: Detect order exceptions and recommend actions. Continuous monitoring of POs, TOs, and customer orders.

**Engine**: `engines/order_tracking_engine.py` — `OrderTrackingEngine`

Six threshold-based detection rules evaluated in priority order:

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| Stuck in transit | status=in_transit AND days > typical × 2.0 | critical | escalate |
| Missing confirmation | status=created AND days > 2.0 | high | contact_supplier |
| Late delivery | days_until_expected < -2.0 | warning/high/critical | expedite/find_alternate |
| Early delivery | days_until_expected > 3.0 | info | adjust_schedule |
| Quantity shortage | fill_rate < 0.95 | warning/high | find_alternate |
| Price variance | \|price_delta\| > 10% | warning/high | review_pricing |

| Component | Detail |
|-----------|--------|
| Input | `OrderSnapshot(order_id, order_type, status, days_until_expected, quantities, prices, partner_metrics)` |
| Output | `ExceptionResult(exception_type, severity, recommended_action, description, impact_assessment)` |
| Config | `OrderTrackingConfig(late_threshold_days=2.0, early_threshold_days=3.0, quantity_variance_threshold=0.05, price_variance_threshold=0.10)` |
| Deterministic? | 100% |

**TRM**: `order_tracking_trm.py` — `OrderTrackingTRM`

The TRM adds:
- Severity refinement based on customer impact and inventory context
- Pattern recognition (recurring issues with specific suppliers)
- Escalation judgment (when to involve humans)

| Component | Detail |
|-----------|--------|
| State vector | exception_type, severity, days_from_expected, qty_variance, inventory_position, pending_orders, customer_impact |
| Action space | Discrete: accept (0), expedite (1), reorder (2), escalate (3), cancel (4) |
| Reward | `correct_exception * 0.4 + resolution_speed * 0.3 + escalation_appropriateness * 0.3` |

**Delegation**: `OrderTrackingTRM._heuristic_evaluate()` builds an `OrderSnapshot` from the TRM's `OrderState`, calls `self._engine.evaluate_order()`, and maps the engine's string-based results back to TRM enum types.

---

## Training Pipeline

### Data Generation

`synthetic_trm_data_generator.py` generates training data for all 5 TRM types. The generator **calls the actual engines** for expert labels, ensuring training data matches the deterministic baselines:

```python
# ATP: AATP engine check_availability() → expert action
# Rebalancing: RebalancingEngine.evaluate_pair() → expert action
# PO Creation: SafetyStockCalculator.compute_safety_stock() → ROP/order-up-to
# Order Tracking: OrderTrackingEngine.evaluate_order() → expert action
# Safety Stock: SafetyStockCalculator.compute_safety_stock() → baseline + heuristic multiplier
```

Each decision generates:
1. **Decision Log** — full state + action + context (per-type table)
2. **Outcome** — measured results after the decision period
3. **Replay Buffer Entry** — `(state, action, reward, next_state, done)` tuple for RL

### Training Methods

`trm_trainer.py` supports 4 methods:

| Method | Description | When to Use |
|--------|-------------|-------------|
| **Behavioral Cloning (BC)** | Supervised learning from engine/expert decisions | Fast warm-start, limited to expert performance |
| **TD Learning** | Q-learning with target network | Online improvement beyond expert |
| **Offline RL (CQL)** | Conservative Q-learning from logs | Learning from historical data safely |
| **Hybrid** | BC warm-start (20 epochs) + Offline RL fine-tune (80 epochs) | **Default** — best of both |

### Reward Functions

Each TRM type has a dedicated reward calculator in `RewardCalculator`:

| TRM Type | Key Reward Components |
|----------|----------------------|
| `atp` | fill_rate, on_time_bonus, priority_weight |
| `rebalancing` | service_improvement, transfer_cost_penalty |
| `po_creation` | stockout_penalty, dos_target, cost_efficiency, timing_accuracy |
| `order_tracking` | correct_exception, resolution_speed, escalation_appropriateness |
| `safety_stock` | stockout_penalty, dos_target, excess_cost, stability_bonus |
| `mo_execution` | on_time_completion, yield_variance, sequence_efficiency, resource_utilization |
| `to_execution` | transit_time_accuracy, consolidation_savings, stockout_prevention |
| `quality_disposition` | correct_disposition, rework_success_rate, complaint_avoidance |
| `maintenance` | breakdown_prevention, cost_efficiency, production_impact_avoidance |
| `subcontracting` | quality_pass_rate, on_time_delivery, cost_savings_vs_internal |
| `forecast_adjustment` | forecast_error_reduction, signal_accuracy, adjustment_stability |

### Per-Site Learning-Depth Curriculum

Training is organized **per site x per TRM type** with a 3-phase progressive curriculum based on data availability (not topology complexity):

| Phase | Name | Data Source | Prerequisite |
|-------|------|-------------|--------------|
| 1 | **Engine Imitation (BC)** | Curriculum generator + deterministic engines | Always available |
| 2 | **Context Learning (Supervised)** | Human expert override decision logs | ≥500 expert decisions for the site |
| 3 | **Outcome Optimization (RL/VFA)** | Replay buffer with measured outcomes | ≥1000 outcome records for the site |

**Phase 1** uses the `CURRICULUM_REGISTRY` with 3 sub-phases (simple → moderate → full complexity) and behavioral cloning to match engine baselines. Every site-TRM pair runs Phase 1.

**Phase 2** trains on human expert overrides filtered by `site_id`. A DC with 200K frozen capacity develops different ATP patterns than a small regional warehouse — per-site training captures these differences.

**Phase 3** uses TD learning + Conservative Q-Learning (CQL) from the replay buffer filtered by `site_id` to discover policies that outperform both engines and human experts.

#### TRM Applicability by Site Master Type

| TRM Type | `inventory` | `manufacturer` | `market_*` |
|----------|-------------|----------------|------------|
| ATPExecutorTRM | Yes | Yes | No |
| POCreationTRM | Yes | Yes | No |
| SafetyStockTRM | Yes | Yes | No |
| InventoryRebalancingTRM | Yes | No | No |
| OrderTrackingTRM | Yes | Yes | No |
| MOExecutionTRM | No | Yes | No |
| TOExecutionTRM | Yes | Yes | No |
| QualityDispositionTRM | Yes | Yes | No |
| MaintenanceSchedulingTRM | Yes | Yes | No |
| SubcontractingTRM | No | Yes | No |
| ForecastAdjustmentTRM | Yes | Yes | No |

#### Checkpoint Naming & Fallback

Checkpoints follow the naming convention `trm_{type}_site{site_id}_v{N}.pt`. When loading a model for inference, the system tries a fallback chain:

1. **Site-specific**: `trm_{type}_site{site_id}_v*.pt` (best match)
2. **Base model**: `trm_{type}_base_{master_type}.pt` (cold-start for new sites)
3. **Legacy**: `trm_{type}_{config_id}.pt` (backward compatibility)

#### Key Files

- `trm_site_trainer.py` — `TRMSiteTrainer` class + `find_best_checkpoint()` fallback
- `powell_training_service.py` — `train_trm_per_site()` orchestrator
- `powell_training_config.py` — `TRMSiteTrainingConfig` model (per-phase status tracking)

---

## SiteAgent Orchestration

The `SiteAgent` (`site_agent.py`) wires engines and TRMs together at the per-site execution level:

```
SiteAgent (per site)
  ├── SharedStateEncoder (common feature extraction)
  ├── ATPExecutorTRM (engine: AATPEngine)
  ├── POCreationTRM (engine: MRPEngine)
  ├── SafetyStockTRM (engine: SafetyStockCalculator)
  ├── InventoryRebalancingTRM (engine: RebalancingEngine)
  ├── OrderTrackingTRM (engine: OrderTrackingEngine)
  ├── MOExecutionTRM (engine: MOExecutionEngine)
  ├── TOExecutionTRM (engine: TOExecutionEngine)
  ├── QualityDispositionTRM (engine: QualityEngine)
  ├── MaintenanceSchedulingTRM (engine: MaintenanceEngine)
  ├── SubcontractingTRM (engine: SubcontractingEngine)
  └── ForecastAdjustmentTRM (engine: ForecastAdjustmentEngine)
```

The SiteAgent:
1. Receives state updates (inventory, orders, forecasts)
2. Encodes state through the shared encoder
3. Dispatches to appropriate TRM based on decision type
4. Records outcomes for continuous learning

---

## File Reference

### Deterministic Engines (100% auditable)

| File | Class | Purpose |
|------|-------|---------|
| `engines/aatp_engine.py` | `AATPEngine` | Priority-based ATP consumption |
| `engines/mrp_engine.py` | `MRPEngine` | Netting, BOM explosion, lot sizing |
| `engines/safety_stock_calculator.py` | `SafetyStockCalculator` | 4 AWS SC policy types |
| `engines/rebalancing_engine.py` | `RebalancingEngine` | Cross-location transfer rules |
| `engines/order_tracking_engine.py` | `OrderTrackingEngine` | Threshold-based exception detection |
| `engines/mo_execution_engine.py` | `MOExecutionEngine` | MO release readiness, sequencing, expedite |
| `engines/to_execution_engine.py` | `TOExecutionEngine` | TO release, consolidation, expedite |
| `engines/quality_engine.py` | `QualityEngine` | Quality disposition rule cascade |
| `engines/maintenance_engine.py` | `MaintenanceEngine` | Maintenance scheduling, breakdown risk |
| `engines/subcontracting_engine.py` | `SubcontractingEngine` | Make-vs-buy decision cascade |
| `engines/forecast_adjustment_engine.py` | `ForecastAdjustmentEngine` | Signal processing, confidence gating |
| `engines/__init__.py` | — | Package exports |

### Narrow TRM Services (learned adjustments)

| File | Class | Engine Dependency |
|------|-------|-------------------|
| `atp_executor.py` | `ATPExecutorTRM` | `AATPEngine` |
| `po_creation_trm.py` | `POCreationTRM` | `MRPEngine` |
| `safety_stock_trm.py` | `SafetyStockTRM` | `SafetyStockCalculator` |
| `inventory_rebalancing_trm.py` | `InventoryRebalancingTRM` | `RebalancingEngine` |
| `order_tracking_trm.py` | `OrderTrackingTRM` | `OrderTrackingEngine` |
| `mo_execution_trm.py` | `MOExecutionTRM` | `MOExecutionEngine` |
| `to_execution_trm.py` | `TOExecutionTRM` | `TOExecutionEngine` |
| `quality_disposition_trm.py` | `QualityDispositionTRM` | `QualityEngine` |
| `maintenance_scheduling_trm.py` | `MaintenanceSchedulingTRM` | `MaintenanceEngine` |
| `subcontracting_trm.py` | `SubcontractingTRM` | `SubcontractingEngine` |
| `forecast_adjustment_trm.py` | `ForecastAdjustmentTRM` | `ForecastAdjustmentEngine` |

### Training & Data

| File | Purpose |
|------|---------|
| `synthetic_trm_data_generator.py` | Generates training data using engines for expert labels |
| `trm_trainer.py` | BC / TD / Offline RL / Hybrid training pipeline |
| `site_agent_trainer.py` | SiteAgent multi-phase curriculum training |
| `site_agent_model.py` | Shared encoder + per-task heads architecture |

### Models & Config

| File | Purpose |
|------|---------|
| `models/trm_training_data.py` | Decision logs, outcomes, replay buffer (all 11 types) |
| `models/powell_training_config.py` | `TRMType` enum, `DEFAULT_TRM_REWARD_WEIGHTS` |
| `models/powell_decisions.py` | Production decision persistence tables |

### Orchestration

| File | Purpose |
|------|---------|
| `site_agent.py` | Per-site orchestrator wiring engines + TRMs |
| `allocation_service.py` | Manages tGNN-generated allocation buckets |
| `integration_service.py` | Powell framework integration orchestration |

All files are under `backend/app/services/powell/` unless noted otherwise.

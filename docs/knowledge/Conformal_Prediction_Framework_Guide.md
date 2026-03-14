# Conformal Prediction Framework for Supply Chain Planning

## Overview

Conformal prediction provides **distribution-free uncertainty quantification** for supply chain planning decisions. Unlike traditional statistical methods that assume specific distributions (normal, Poisson, etc.), conformal prediction offers **guaranteed prediction intervals** using only exchangeability of data points.

**Core Guarantee**: If we say "90% coverage", the actual coverage will be ≥90% regardless of the underlying distribution.

## Theory

### Traditional vs Conformal Approach

| Aspect | Traditional Forecasting | Conformal Prediction |
|--------|------------------------|---------------------|
| Interval basis | Assumed distribution (often wrong) | Data-driven (distribution-free) |
| Coverage guarantee | Only if distribution is correct | Always valid (exchangeability only) |
| Calibration needed | Parametric estimation | Nonparametric — residuals only |
| Adaptivity | Fixed once fitted | Online recalibration possible |

### Algorithm

1. **Calibration Phase**: Given historical plan-vs-actual pairs, compute nonconformity scores (absolute residuals)
2. **Quantile Computation**: Calculate the ⌈(1-α)(n+1)/n⌉ quantile of residuals
3. **Prediction**: For new point forecast, interval = point ± quantile
4. **Guarantee**: P(actual ∈ interval) ≥ 1-α (requires only exchangeability)

### Mathematical Foundation

Given calibration residuals R₁, R₂, ..., Rₙ and miscoverage rate α:
- Sort residuals: R₍₁₎ ≤ R₍₂₎ ≤ ... ≤ R₍ₙ₎
- Compute quantile index: q = ⌈(n+1)(1-α)⌉
- Prediction interval: [ŷ - R₍q₎, ŷ + R₍q₎]

## Platform Implementation

### Components

#### 1. ConformalPredictor (Base Class)
Location: `backend/app/services/conformal_prediction.py`

Core conformal predictor supporting:
- Calibration from historical plan-vs-actual data
- Split conformal prediction (calibration + prediction sets)
- Adaptive conformal prediction with drift detection
- Multiple nonconformity score functions

#### 2. ConformalDemandForecaster
Specialized for demand forecasting:
- Calibrates on forecast_quantity vs actual demand
- Produces P10/P50/P90-like intervals but with formal guarantees
- Integrates with `Forecast` entity's `forecast_error` field

#### 3. ConformalLeadTimePredictor
Specialized for lead time prediction:
- Calibrates on planned vs actual lead times
- Feeds into safety stock calculation
- Integrates with `VendorLeadTime` entity

#### 4. ConformalDecisionMaker
Supply chain decisions with risk bounds:
- **Safety Stock**: Uses conformal demand + lead time intervals for guaranteed service level
- **Order Promising (ATP/CTP)**: Promised dates with formal confidence bounds
- **Reorder Points**: Distribution-free reorder point calculation

#### 5. AdaptiveConformalPredictor
Online conformal prediction:
- Sliding window calibration (adapts to non-stationarity)
- Drift detection via coverage monitoring
- Emergency recalibration when coverage deviates >5%

### Conformal Orchestrator
Location: `backend/app/services/conformal_orchestrator.py`

Singleton wiring layer connecting all conformal prediction components into an automatic feedback loop:

**Six Capabilities**:
1. **Forecast Load Hook**: Apply/trigger calibration on forecast import
2. **Actuals Observation Hook**: Match forecast to actual, compute error, feed calibration
3. **Drift Monitoring**: Emergency recalibration when coverage drifts >5%
4. **Scheduled Recalibration**: Daily APScheduler job (1:30 AM)
5. **Planning Staleness Check**: Verify freshness before using intervals (7-day warning, 14-day error)
6. **Suite ↔ DB Persistence**: Persist calibration to `powell_belief_state`, hydrate on startup

**Multi-Entity Observation Hooks**:
- `on_actual_demand_observed()` — from customer order creation
- `on_lead_time_observed()` — from TO/PO receipt
- `on_yield_observed()` — from manufacturing execution
- `on_price_observed()` — from PO receipt vs catalog price
- `on_service_level_observed()` — from order fulfillment

### Database Integration

#### powell_belief_state Table
Stores conformal calibration state per entity:
- `entity_type`: demand, lead_time, yield, price, service_level
- `product_id`, `site_id`: Granularity of calibration
- `recent_residuals`: JSON array of recent nonconformity scores
- `observation_count`: Number of calibration observations
- `conformal_quantile`: Current quantile for prediction intervals
- `coverage_target`: Target coverage (e.g., 0.90)
- `empirical_coverage`: Actual observed coverage
- `last_calibrated`: Timestamp of last calibration

#### powell_calibration_log Table
Audit trail of predicted vs actual values:
- `entity_type`, `product_id`, `site_id`
- `predicted_value`, `actual_value`
- `residual`: Computed nonconformity score
- `within_interval`: Boolean — was actual within predicted interval?

### Conformal Inventory Policy (ss_policy = 'conformal')

The `inv_policy` table supports a fifth policy type `conformal`:
- `conformal_demand_coverage`: Target coverage for demand intervals (default 0.90)
- `conformal_lead_time_coverage`: Target coverage for lead time intervals (default 0.90)
- Safety stock = upper bound of (demand × lead time) conformal interval - expected demand

## Integration with Powell Framework

### Belief State (Sₜ)
Conformal prediction quantifies the **belief state** in Powell's framework:
- Traditional: Point estimate + assumed variance
- Conformal: Point estimate + guaranteed interval width
- The interval width IS the uncertainty measure for decision-making

### Policy Parameters (θ)
Conformal intervals feed into CFA policy parameters:
- Safety stock multiplier derived from conformal quantile (not z-score)
- Order-up-to level includes conformal interval width
- ATP promising uses conformal lead time intervals

### Value Function Approximation (VFA)
TRM agents receive conformal intervals as input features:
- `demand_interval_width`: Uncertainty signal for order decisions
- `lead_time_interval_width`: Uncertainty signal for timing decisions
- `coverage_deviation`: Signal for when model confidence is degrading

## Conformal Prediction for Stochastic Programming

### Integration with Monte Carlo
- Conformal intervals provide **distribution-free bounds** for scenario generation
- Instead of assuming normal(μ, σ), sample from conformal interval [lower, upper]
- Guaranteed coverage means scenarios cover actual outcomes with known probability

### Scenario Generation
Location: `backend/app/services/powell/conformal_scenario_generator.py`

Uses conformal intervals to generate scenarios:
1. For each uncertain variable (demand, lead time, yield)
2. Get conformal interval at target coverage
3. Generate scenarios spanning the interval
4. Weight scenarios by empirical distribution within interval

## Key Metrics

- **Empirical Coverage**: Actual fraction of observations within intervals (should ≥ target)
- **Interval Width**: Narrower = more precise; too narrow = coverage violation
- **Adaptivity Rate**: How quickly intervals adjust to distribution shifts
- **Staleness**: Time since last calibration (>7 days = warning, >14 days = error)
- **Coverage Drift**: Deviation of empirical coverage from target (>5% = emergency recalibration)

## API Endpoints

- `POST /api/v1/conformal/calibrate` — Trigger calibration for a variable
- `GET /api/v1/conformal/intervals/{entity_type}` — Get current intervals
- `POST /api/v1/conformal/observe` — Feed actual observation for calibration
- `GET /api/v1/conformal/status` — Coverage, staleness, drift metrics
- `POST /api/v1/conformal/recalibrate` — Force emergency recalibration

## Two-Level Conformal Prediction Architecture

Conformal prediction operates at **two complementary levels** across the platform:

### Level 1 — Forecast-Level Conformal Prediction (Intervals)

**Scope**: Demand, lead time, yield, price, service level forecasts
**Component**: `ConformalOrchestrator` + `SupplyChainConformalSuite`
**Output**: Prediction intervals with formal coverage guarantee (e.g., "demand will be 80-120 units with 90% coverage")
**Used by**: Inventory target calculation (`conformal` and `sl_conformal_fitted` policies), supply plan generation, ATP promising, scenario generation

This level provides distribution-free bounds on **input variables** that feed into planning decisions. It replaces assumed-Normal z-score intervals with empirically calibrated intervals.

### Level 2 — Decision-Level CDT (Risk Bounds)

**Scope**: All 11 TRM execution-level decisions
**Component**: `ConformalDecisionWrapper` + `CDTCalibrationService`
**Output**: Risk bound per decision: `risk_bound = P(loss > threshold)` with distribution-free guarantee
**Used by**: TRM decision responses, escalation routing (Skills vs autonomous), Decision Stream urgency ranking

CDT requires a **measurable binary outcome** (decision good or bad) with a **computable loss function**. It applies specifically to execution-level decisions where:
- Each decision has a discrete, observable outcome
- Loss can be computed after a feedback horizon (ATP: 4h, PO: 7d, buffer: 14d)
- Calibration pairs accumulate from `powell_*_decisions` outcome columns

### Why CDT Does NOT Apply to Upper Planning Layers

| Layer | Decision Type | Why Forecast-Level CP (not CDT) |
|-------|--------------|--------------------------------|
| S&OP GraphSAGE (weekly) | Policy parameters θ | Optimization outputs, not discrete decisions. CFA uses Differential Evolution over Monte Carlo scenarios — uncertainty handled by scenario ensemble. |
| Execution tGNN (daily) | Priority allocations | Continuous-valued vectors, not binary accept/reject. tGNN outputs confidence scores instead. |
| Site tGNN (hourly) | Urgency modulation | Intermediate signals, not final decisions. Downstream TRM carries CDT bound. |
| MPS/MRP/Supply Plan | Planning decisions | Use forecast-level CP intervals on inputs. Planning commit workflow has own status model (PROPOSED→REVIEWED→ACCEPTED). |

### CDT Cold Start Behavior

When a TRM type lacks sufficient calibration data (< 30 decision-outcome pairs):
- `risk_bound` defaults to **0.50** (maximum uncertainty)
- `escalation_recommended` is set to **True**
- This forces escalation to Claude Skills or human review
- Conservative behavior ensures safety during ramp-up

The CDT Readiness Banner (`CDTReadinessBanner.jsx`) shows calibration status on the Decision Stream page. The Provisioning Stepper shows per-TRM calibration status after the conformal step completes.

### CDT Calibration Thresholds

Three thresholds govern different calibration stages:

| Component | Threshold | Purpose |
|-----------|-----------|---------|
| `ConformalOrchestrator` | 10 observations | Minimum for hydrating forecast-level suites from `powell_belief_state` |
| `CDTCalibrationService` | 30 pairs | Full CDT calibration for a TRM type |
| `ConformalDecisionWrapper` | 5 losses | Conservative bounds computation (pre-calibration fallback) |

## Multi-Tenant Isolation

**Critical requirement**: Conformal prediction calibration data MUST be tenant-scoped.

### Forecast-Level (ConformalOrchestrator)

- `hydrate_from_db(db, tenant_id)` filters `PowellBeliefState` by `tenant_id`
- `on_forecasts_loaded()` queries `Forecast` with `tenant_id` filter
- `_match_forecast()` filters by `tenant_id`
- `get_conformal_suite(tenant_id)` returns tenant-specific suite instances (NOT global singletons)

### Decision-Level (CDT)

- `get_cdt_registry(tenant_id)` returns per-tenant `ConformalDecisionRegistry` — isolated calibration data
- `CDTCalibrationService(db, tenant_id)` extracts pairs only from configs belonging to that tenant
- `_run_cdt_calibration()` in relearning_jobs runs per-tenant (iterates all tenants)
- `SiteAgent.connect_trm()` replaces global CDT wrapper with tenant-scoped wrapper

### Implementation Files

| File | Tenant Scoping |
|------|---------------|
| `conformal_prediction/conformal_decision.py` | Per-tenant CDT registries via `get_cdt_registry(tenant_id)` |
| `conformal_prediction/suite.py` | Per-tenant suite via `get_conformal_suite(tenant_id)` |
| `conformal_orchestrator.py` | `tenant_id` parameter on `hydrate_from_db()`, forecast queries |
| `powell/cdt_calibration_service.py` | `tenant_id` in constructor, `_get_tenant_config_ids()` for filtering |
| `powell/relearning_jobs.py` | `_run_cdt_calibration()` iterates all tenants |
| `powell/site_agent.py` | `connect_trm()` wires tenant-scoped CDT wrapper |
| `provisioning_service.py` | `_step_conformal()` resolves tenant_id, passes to hydration and CDT batch |

## Relationship to Other Concepts

- **Safety Stock Calculation**: Conformal intervals replace z-score × σ with distribution-free bounds
- **ATP/CTP Promising**: Delivery date intervals have formal confidence guarantees
- **Demand Planning**: Forecast intervals replace assumed-normal P10/P50/P90
- **Powell Belief State**: Conformal quantile IS the belief state uncertainty measure
- **TRM Input Features**: Interval widths feed into TRM decision context
- **Stochastic Programming**: Conformal bounds define scenario generation ranges
- **Admin Overrides**: `agent_stochastic_params` distributions (SAP-imported or manual) can override fitted distributions in `sl_fitted` safety stock policy

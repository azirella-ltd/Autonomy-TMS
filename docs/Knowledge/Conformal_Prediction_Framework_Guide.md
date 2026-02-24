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

## Relationship to Other Concepts

- **Safety Stock Calculation**: Conformal intervals replace z-score × σ with distribution-free bounds
- **ATP/CTP Promising**: Delivery date intervals have formal confidence guarantees
- **Demand Planning**: Forecast intervals replace assumed-normal P10/P50/P90
- **Powell Belief State**: Conformal quantile IS the belief state uncertainty measure
- **TRM Input Features**: Interval widths feed into TRM decision context
- **Stochastic Programming**: Conformal bounds define scenario generation ranges
